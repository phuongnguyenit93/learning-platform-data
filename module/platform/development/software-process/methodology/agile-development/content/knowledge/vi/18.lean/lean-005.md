# Tăng cường học hỏi và giữ các phương án khi còn bất định

## 1. Tại sao Lean không khuyên quyết định mọi thứ ngay từ đầu?

Một nhóm đang xây dựng nền tảng học trực tuyến cần giúp người học chọn khóa phù hợp. Tại thời điểm bắt đầu, có ba hướng giải pháp:

1. Gợi ý khóa theo **quy tắc đơn giản** dựa trên trình độ và mục tiêu học.
2. Gợi ý dựa trên **đặc điểm nội dung khóa học** và lịch sử tương tác.
3. Dùng **dịch vụ mô hình học máy bên ngoài** để cá nhân hóa sâu hơn.

Nếu nhóm ngay lập tức chọn phương án 3 và dành nhiều tuần tích hợp, họ có thể phát hiện quá muộn rằng người dùng chủ yếu cần hiểu **điều kiện tiên quyết** của khóa, chứ không cần một hệ thống gợi ý phức tạp. Nhưng nếu nhóm chỉ tổ chức họp để tranh luận vô hạn mà không làm thử điều gì, cơ hội nhận phản hồi cũng bị bỏ lỡ.

Lean đưa ra hai nguyên tắc có quan hệ mật thiết:

- **Amplify Learning — Tăng cường học hỏi:** Tổ chức công việc để kiểm tra giả định, nhận phản hồi và cập nhật hiểu biết càng sớm, càng có ích càng tốt.
- **Decide as Late as Possible — Quyết định muộn nhất có trách nhiệm:** Giữ những phương án khả thi khi còn bất định có ý nghĩa, rồi cam kết khi đã đủ bằng chứng hoặc trước khi việc chờ thêm gây tổn thất lớn.

Hai nguyên tắc này không khuyên nhóm “đừng quyết định”. Chúng khuyên **không khóa giải pháp quá sớm chỉ vì muốn cảm thấy chắc chắn**, đồng thời **không trì hoãn vượt thời điểm cần hành động**.

Trong module **AGILE_DEVELOPMENT**, chúng hỗ trợ giá trị Agile: cộng tác với khách hàng, nhận phản hồi sớm, giao sản phẩm tăng dần, thích ứng trước thay đổi và cải tiến liên tục. Các thực hành **user story, product backlog, Scrum, Kanban, XP** có thể được sử dụng để biến tư duy học hỏi thành hoạt động cụ thể.

**Câu hỏi cốt lõi:** *Ta đang thiếu thông tin nào có thể làm thay đổi quyết định, học thông tin đó bằng cách nào và đến lúc nào thì cần cam kết?*

## 2. “Học hỏi” trong phát triển sản phẩm nghĩa là gì?

Học hỏi không đơn thuần là đọc tài liệu, dự họp hoặc ghi lại điều đã biết. Trong Lean, học hỏi có giá trị khi **giảm bất định ảnh hưởng tới hành động** hoặc giúp nhóm tránh tạo ra sản phẩm không đáp ứng nhu cầu.

| Loại bất định | Câu hỏi ví dụ | Cách học phù hợp | Quyết định có thể thay đổi |
| --- | --- | --- | --- |
| **Nhu cầu người dùng** | Người học thực sự gặp khó khăn khi chọn khóa ở đâu? | Quan sát hành trình, phỏng vấn theo tình huống, usability test | Ưu tiên bộ lọc, nhãn trình độ hay gợi ý cá nhân hóa |
| **Giá trị** | Khả năng mới có giúp người học bắt đầu học nhiều hơn không? | Thử bản mẫu, beta, đo hành vi và phản hồi | Làm tiếp, điều chỉnh hay dừng sáng kiến |
| **Khả thi kỹ thuật** | Dịch vụ gợi ý có đáp ứng độ trễ và tính sẵn sàng cần thiết không? | Spike kỹ thuật, proof of concept, thử tích hợp | Tự xây, dùng dịch vụ hay chọn cách đơn giản hơn |
| **Khả năng sử dụng** | Người học có hiểu nhãn “Trung cấp” không? | Thử nghiệm thao tác với người dùng mục tiêu | Cách diễn đạt và thiết kế giao diện |
| **Vận hành** | Đội hỗ trợ có giải thích được gợi ý sai không? | Thử quy trình, phỏng vấn vận hành, chạy pilot | Quy tắc giải thích, giám sát và xử lý lỗi |
| **Tuân thủ và rủi ro** | Dữ liệu nào được phép dùng để cá nhân hóa? | Rà soát quyền riêng tư và yêu cầu pháp lý với người có thẩm quyền | Kiến trúc dữ liệu, lựa chọn nhà cung cấp, phạm vi thử |
| **Chi phí và thời gian** | Phương án nào có tổng chi phí thay đổi và vận hành phù hợp? | Dự báo chi phí, đo thử, phân tích kịch bản | Chọn thiết kế và thứ tự phát hành |

Một kết quả học hỏi tốt thường được diễn đạt thành:

> “Chúng ta từng giả định rằng người học cần gợi ý bằng AI. Qua quan sát và thử nghiệm nhỏ, trở ngại phổ biến là họ không hiểu trình độ đầu vào. Nhóm sẽ kiểm tra khả năng giải quyết bằng thông tin trình độ trước khi đầu tư mô hình cá nhân hóa.”

Ở đây, **việc loại bỏ một phương án không cần thiết cũng là kết quả có giá trị**. Nhóm đã tránh chi phí xây sai, dù chưa giao thêm một tính năng lớn.

### 2.1. Đầu ra, kết quả sử dụng và học hỏi

Ba cách nhìn cần phân biệt:

- **Output (đầu ra):** Có trang gợi ý, API và mô hình đã triển khai.
- **Outcome (kết quả sử dụng):** Người học chọn khóa phù hợp hơn, giảm thao tác tìm kiếm lại.
- **Learning (hiểu biết mới):** Xác định được nguyên nhân khiến người học chọn sai và điều gì có khả năng cải thiện.

Output có thể là công cụ để đạt outcome; learning giúp quyết định nên đầu tư output nào. **Hoàn thành nhiều chức năng không tự chứng minh đã học đúng hoặc đã tạo giá trị**.

### 2.2. Tốc độ học hỏi không đồng nghĩa số lượng thử nghiệm

Mười thí nghiệm thiếu câu hỏi rõ, không có người dùng phù hợp hoặc đo sai chỉ số có thể cung cấp ít hiểu biết hơn một thí nghiệm được thiết kế tốt. Nên tối ưu **thời gian tới một quyết định được cải thiện**, thay vì tối ưu số cuộc họp, số ticket nghiên cứu hoặc số prototype được tạo.

## 3. Vòng lặp học hỏi: từ bất định tới bằng chứng

Một vòng lặp thực dụng:

~~~mermaid
flowchart TD
    A["Nhận diện quyết định và điều chưa biết"] --> B["Nêu giả thuyết có thể kiểm chứng"]
    B --> C["Chọn cách học ít tốn kém nhưng đủ tin cậy"]
    C --> D["Thực hiện thử nghiệm hoặc lát cắt nhỏ"]
    D --> E["Thu thập kết quả và giới hạn bằng chứng"]
    E --> F{"Bằng chứng đã đủ cho quyết định?"}
    F -->|"Chưa"| G["Điều chỉnh câu hỏi hoặc thí nghiệm"]
    G --> C
    F -->|"Đủ"| H["Cam kết, thay đổi hướng hoặc loại phương án"]
    H --> I["Giao Increment, đo outcome và học tiếp"]
    I --> A
~~~

**Bước 1 — Gọi tên quyết định.** Ví dụ “Có nên chọn kiến trúc gợi ý phụ thuộc nhà cung cấp bên ngoài?” khác với câu mơ hồ “Nên nghiên cứu AI”.

**Bước 2 — Viết giả thuyết.** Ví dụ: “Nếu trình độ và điều kiện đầu vào được hiển thị rõ, người học mới sẽ chọn đúng khóa dễ hơn.”

**Bước 3 — Xác định bằng chứng cần có.** Có thể quan sát người dùng thực hiện nhiệm vụ hoặc thử một phiên bản nhỏ, thay vì viết toàn bộ hệ thống gợi ý.

**Bước 4 — Giới hạn phạm vi và thời gian học.** Chọn một nhóm người dùng phù hợp, một tập khóa có đại diện và một phương án thử vừa đủ. Nếu cần quyền truy cập hoặc phê duyệt, xử lý trước.

**Bước 5 — Ghi kết quả và điểm còn bất định.** Phân biệt điều quan sát được với suy đoán về nguyên nhân.

**Bước 6 — Quyết định bước tiếp theo.** Tiếp tục, thay đổi, bỏ một lựa chọn hoặc thiết kế thêm thử nghiệm khi giá trị thông tin còn lớn.

Không phải mọi quyết định đều cần A/B test. Nếu một lỗi bảo mật nghiêm trọng có bằng chứng rõ, nhóm phải khắc phục theo yêu cầu an toàn thay vì trì hoãn để “thu thập thêm học hỏi”.

## 4. Giữ phương án mở là giữ điều gì?

**Phương án (option)** trong ngữ cảnh thiết kế là một con đường hành động vẫn có thể chọn ở tương lai. Khi mức bất định còn lớn, nhóm có thể tạo hệ thống và kế hoạch sao cho chưa phải khóa một lựa chọn không dễ đảo ngược.

Ví dụ, trước khi quyết định nhà cung cấp dịch vụ gợi ý, nhóm có thể:

- Thống nhất một **hợp đồng API nội bộ nhỏ**, mô tả dữ liệu đầu vào/đầu ra thật sự cần.
- Tạo một triển khai **quy tắc đơn giản** dùng làm baseline.
- Thử tích hợp hai lựa chọn có rủi ro lớn trên dữ liệu giả lập hoặc dữ liệu được phép sử dụng.
- Ghi rõ điều kiện kích hoạt một lựa chọn: chi phí, quyền dữ liệu, độ trễ, khả năng giải thích.
- Chưa thực hiện migration tốn kém sang một cấu trúc đặc thù nhà cung cấp.

Như vậy, nhóm **vẫn tiến hành công việc có ích** trong khi giữ khả năng chuyển hướng.

Tuy nhiên, mỗi phương án có chi phí duy trì. Nếu cố xây hai kiến trúc sản xuất hoàn chỉnh song song chỉ để “giữ lựa chọn”, nhóm có thể tăng WIP, chi phí kiểm thử và gánh nặng bảo trì mà không thu thêm thông tin có ý nghĩa.

### 4.1. Ba mức giữ phương án

| Mức | Ví dụ | Chi phí và thời điểm phù hợp |
| --- | --- | --- |
| **Giữ trong suy nghĩ/thiết kế** | Ghi lựa chọn, giả định và tiêu chí quyết định | Rẻ; hữu ích ở giai đoạn khám phá ban đầu |
| **Thử trong phạm vi nhỏ** | Proof of concept, prototype hoặc thử tích hợp tối thiểu | Tốn vừa phải; tốt khi thiếu bằng chứng kỹ thuật |
| **Duy trì khả năng đổi hướng trong sản phẩm** | Cấu trúc mô-đun, ranh giới API, cờ tính năng, khả năng thay thế nhà cung cấp | Tốn công thiết kế/bảo trì; hợp lý khi rủi ro khóa chặt cao |

**Không phải lúc nào cũng cần mức thứ ba.** Giữ phương án chỉ có ích khi giá trị của khả năng lựa chọn trong tương lai lớn hơn chi phí duy trì nó.

### 4.2. Quyết định dễ đảo ngược và khó đảo ngược

| Loại quyết định | Ví dụ | Cách tiếp cận gợi ý |
| --- | --- | --- |
| **Dễ đảo ngược, chi phí thay đổi thấp** | Cách đặt tên nút trong bản mẫu, thứ tự hai bộ lọc nhỏ | Chọn một phương án hợp lý, thử nhanh, thay đổi theo phản hồi |
| **Có thể đảo ngược nhưng tốn chi phí** | Thay thư viện hiển thị, thay dịch vụ email, đổi API nội bộ lớn | Giữ ranh giới thiết kế phù hợp, kiểm tra rủi ro trước cam kết |
| **Khó đảo ngược** | Chuyển dữ liệu nhạy cảm cho đối tác, hợp đồng dài hạn, migration khó rollback | Tìm bằng chứng quan trọng, phê duyệt đúng thẩm quyền, có kế hoạch dự phòng |
| **Không thể chờ vì an toàn/tuân thủ** | Khắc phục điểm yếu bị khai thác, đáp ứng thời hạn pháp lý | Hành động theo nghĩa vụ và rủi ro; không viện cớ “quyết định muộn” |

Quyết định dễ đảo ngược có thể được chọn sớm để học nhanh. Nhóm nên dành nhiều nỗ lực học hỏi hơn cho quyết định có **chi phí sai cao và khả năng đảo ngược thấp**.

## 5. Quyết định muộn nhất có trách nhiệm (*last responsible moment*)

“Quyết định càng muộn càng tốt” thường bị hiểu sai thành “đợi đến phút cuối”. Ý đúng là **chờ tới thời điểm hợp lý nhất khi thông tin thêm vẫn có giá trị, nhưng không để sự chờ đợi gây mất lựa chọn, trễ hạn hoặc tăng rủi ro không thể chấp nhận**.

Một quyết định nên được chốt khi một trong các điều sau xảy ra:

1. **Đã đủ bằng chứng** để chọn một phương án đáp ứng mục tiêu và ràng buộc.
2. **Bằng chứng tiếp theo ít có khả năng thay đổi quyết định**, trong khi chi phí nghiên cứu tiếp tăng.
3. **Đến ngưỡng cam kết kỹ thuật hoặc lịch**, nếu chờ sẽ làm mất khả năng giao phần giá trị cần thiết.
4. **Ràng buộc an toàn, pháp lý hoặc hợp đồng** yêu cầu hành động hoặc phê duyệt.
5. **Chi phí giữ các lựa chọn mở** bắt đầu lớn hơn lợi ích kỳ vọng.

### 5.1. Xác định điểm quyết định bằng cách đi ngược từ hạn chót

Giả sử một lớp học mới sẽ khai giảng sau **sáu tuần**, và để có tính năng gợi ý trên hệ thống thật cần:

| Hoạt động tối thiểu sau khi chốt phương án | Thời lượng giả định |
| --- | ---: |
| Triển khai và cấu hình phương án đã chọn | 2 tuần |
| Kiểm thử tích hợp và quyền dữ liệu | 1 tuần |
| Thử nghiệm vận hành, xử lý lỗi và chuẩn bị phát hành | 1 tuần |
| **Tổng thời gian tối thiểu cần bảo vệ** | **4 tuần** |

Với giả định các bước không thể rút ngắn hoặc chồng lắp thêm, quyết định cần được chốt **không muộn hơn cuối tuần thứ hai**:

\[
\text{Thời điểm chốt muộn nhất theo kế hoạch}
=6-4=2\ \text{tuần kể từ khi bắt đầu}
\]

Đây là **phép tính minh họa có điều kiện**, không phải công thức bảo đảm cho mọi dự án. Nếu có phụ thuộc chưa chắc chắn hoặc xác suất làm lại cao, nhóm cần chốt sớm hơn hoặc thêm khoảng dự phòng hợp lý. Nếu có thể giảm phạm vi hoặc làm việc song song an toàn, thời điểm có thể khác.

Từ ngày đầu đến cuối tuần thứ hai, nhóm nên chọn những hoạt động **tạo bằng chứng có thể ảnh hưởng quyết định**: kiểm tra quyền dữ liệu, đo độ trễ tích hợp, thử nhu cầu với người học. Không nên lãng phí khoảng này cho tranh luận thiếu thí nghiệm.

### 5.2. Một bảng “quyết định chưa khóa” hữu ích

| Quyết định | Những phương án còn sống | Điều chưa biết quan trọng | Hoạt động học tiếp | Điểm phải quyết định |
| --- | --- | --- | --- | --- |
| Cách gợi ý khóa | Quy tắc, nội dung, dịch vụ ngoài | Người học cần mức cá nhân hóa nào? | Thử bản mẫu và luồng tìm khóa | Trước khi bắt đầu tích hợp chính thức |
| Dữ liệu dùng để gợi ý | Chỉ metadata khóa; thêm tương tác đã được phép dùng | Quyền sử dụng và khả năng giải thích | Rà soát quyền dữ liệu và thử baseline | Trước thu thập/xử lý dữ liệu mới |
| Tổ chức tính năng trong UI | Gợi ý trên trang tìm kiếm; gợi ý ở trang chi tiết | Người học có nhận thấy và hiểu không? | Usability test với nhiệm vụ cụ thể | Trước chốt thiết kế cho lát cắt đầu tiên |

Mỗi dòng nên có **người chịu trách nhiệm điều phối quyết định** và thời điểm xem lại. Nếu không, “giữ phương án” dễ trở thành một danh sách ý tưởng tồn mãi.

## 6. Set-based design: khám phá nhiều phương án trước khi thu hẹp

**Set-based design** hay cách thiết kế theo tập phương án là phương thức không khóa ngay một thiết kế duy nhất; thay vào đó, nhóm tìm hiểu một **tập phương án khả thi**, xác định ranh giới và từng bước loại bỏ phương án khi có bằng chứng.

Ví dụ nền tảng học trực tuyến cần cải thiện tìm kiếm khóa:

| Lựa chọn | Điểm mạnh giả định | Rủi ro cần kiểm tra | Trạng thái ban đầu |
| --- | --- | --- | --- |
| **A — Lọc theo trình độ và chủ đề** | Đơn giản, dễ giải thích, dữ liệu ít | Có đủ hữu ích khi danh mục lớn? | Giữ để thử |
| **B — Gợi ý dựa metadata nội dung** | Phù hợp nội dung khóa hơn, ít phụ thuộc bên ngoài | Dữ liệu mô tả khóa có chất lượng không? | Giữ để thử |
| **C — Dịch vụ AI bên ngoài** | Có thể cá nhân hóa sâu hơn | Chi phí, quyền dữ liệu, độ trễ, giải thích | Thử kỹ thuật rất nhỏ trước |

Sau các thử nghiệm, nhóm có thể thấy A đáp ứng nhu cầu người mới và dễ vận hành; B chỉ tốt khi metadata được chuẩn hóa; C không đáp ứng yêu cầu quyền dữ liệu hiện tại. Khi ấy, tập lựa chọn được **thu hẹp dựa trên bằng chứng**, không phải dựa vào người phát biểu tự tin nhất.

### 6.1. Khám phá song song không đồng nghĩa xây mọi phương án đến production

Nhóm có thể chạy **thử nghiệm nhỏ có mục đích khác nhau** song song, nhưng không nên duy trì ba hệ thống đầy đủ:

- Prototype A giúp đánh giá **khả năng sử dụng**.
- Thử metadata cho B giúp đánh giá **chất lượng dữ liệu và độ phù hợp**.
- Spike ngắn cho C giúp đánh giá **khả thi và ràng buộc**.

Sau đó quyết định nên đầu tư vào phương án nào. Nếu một phương án thất bại ở điều kiện bắt buộc, có thể loại nó ngay mà không cần thử thêm mọi khía cạnh.

### 6.2. Quy tắc loại bỏ và giữ phương án

Nên thống nhất trước:

1. **Tiêu chí bắt buộc:** An toàn, quyền riêng tư, tuân thủ, chuẩn chất lượng.
2. **Tiêu chí tạo giá trị:** Giải quyết trở ngại của người học tốt đến đâu?
3. **Tiêu chí chi phí:** Công sức xây dựng, vận hành, chuyển đổi và bảo trì.
4. **Tiêu chí thích ứng:** Nếu nhu cầu đổi, có thể điều chỉnh nhanh hay bị khóa chặt?
5. **Điểm dừng:** Bằng chứng nào đủ để loại hoặc cam kết một phương án?

Nếu phương án vi phạm ràng buộc bắt buộc, **không nên giữ nó như “lựa chọn mở” chỉ vì có tiềm năng kinh doanh**.

## 7. Giữ lựa chọn có chi phí: tư duy giá trị thông tin

Học hỏi và duy trì nhiều phương án không miễn phí. Nhóm cần so sánh:

- **Lợi ích kỳ vọng từ thông tin mới:** Có thể tránh một quyết định sai tốn kém hoặc phát hiện giải pháp tốt hơn?
- **Chi phí học hỏi:** Prototype, dữ liệu, người tham gia nghiên cứu, môi trường thử nghiệm, thời gian chờ.
- **Chi phí duy trì phương án:** Trừu tượng hóa quá mức, hai nhánh mã, nhiều nhà cung cấp, thêm kiểm thử/bảo trì.
- **Chi phí trì hoãn (cost of delay):** Mất cơ hội kinh doanh, chậm phản hồi người dùng, tăng rủi ro an toàn hoặc bỏ lỡ thời hạn.
- **Khả năng đảo ngược:** Nếu chốt sai, đổi lại dễ hay khó?

### 7.1. Một phép so sánh minh họa

Giả sử có hai cách tiếp cận chức năng gợi ý:

- **Chốt ngay một dịch vụ ngoài:** Tốn 20 người-ngày tích hợp; nếu không phù hợp có thể cần thêm 12 người-ngày để thay đổi.
- **Làm thử hai ngày để học về quyền dữ liệu và khả năng sử dụng:** Tốn 2 người-ngày, có thể giúp phát hiện sớm rằng giải pháp đơn giản phù hợp hơn.

Nếu nhóm *giả định* xác suất chọn sai khi chưa thử là 30% và chi phí làm lại 12 người-ngày, thì **tổn thất làm lại kỳ vọng** theo mô hình đơn giản là:

\[
0{,}30 \times 12 = 3{,}6\ \text{người-ngày}
\]

So với **2 người-ngày** thử nghiệm, có lý do để cân nhắc học trước. Tuy nhiên:

- **30% chỉ là giả định minh họa**, không phải số liệu thực nghiệm.
- Thí nghiệm phải thực sự có khả năng làm giảm rủi ro chọn sai.
- Quyết định có thể còn các chi phí và tác động khác chưa được mô hình hóa.
- Nếu chờ hai ngày làm mất một mốc bắt buộc, chi phí trì hoãn phải được tính vào.

Không được suy ra “2 nhỏ hơn 3,6 nên luôn phải làm thí nghiệm”. Phương pháp này giúp **nêu rõ giả định và đánh đổi** để thảo luận, không cung cấp đáp án tự động.

### 7.2. Khi giá trị thông tin thấp

Nếu hai cách bố trí nút có tác động nhỏ, dễ đổi trong vài phút và không tạo rủi ro đáng kể, việc tổ chức nghiên cứu kéo dài nhiều tuần có thể lãng phí. Chọn một phương án hợp lý, giao lát cắt nhỏ rồi học từ phản hồi thực tế thường tốt hơn.

Ngược lại, với quyết định chuyển dữ liệu cá nhân sang nhà cung cấp bên ngoài, **chi phí sai và ràng buộc quyền dữ liệu lớn hơn nhiều**. Cần bằng chứng, đánh giá rủi ro và quyết định đúng thẩm quyền trước khi thực hiện.

## 8. Các kỹ thuật tăng cường học hỏi trong phát triển phần mềm

| Kỹ thuật | Dùng để học điều gì? | Đầu ra có ích | Sai lầm cần tránh |
| --- | --- | --- | --- |
| **Phỏng vấn người dùng** | Mục tiêu và khó khăn trong bối cảnh thật | Mẫu nhu cầu, giả thuyết mới | Chỉ hỏi “Bạn có thích ý tưởng này không?” |
| **Usability testing** | Người dùng có thực hiện được nhiệm vụ không? | Quan sát vướng mắc, lỗi hiểu và cơ hội cải thiện | Dẫn dắt người dùng tới câu trả lời mong muốn |
| **Prototype / bản mẫu** | Luồng và cách tương tác có hợp lý không? | Bằng chứng nhanh trước khi xây sâu | Coi bản mẫu là hệ thống production đã đủ chất lượng |
| **Technical spike** | Công nghệ hoặc tích hợp có khả thi không? | Kết quả thử, rủi ro, giới hạn kỹ thuật | Biến spike thành dự án không có thời hạn |
| **Walking skeleton** | Các thành phần đầu-cuối có kết nối được không? | Một lát cắt rất mỏng chạy xuyên hệ thống | Tuyên bố đã giao giá trị đầy đủ nếu chỉ là khung kỹ thuật |
| **Trải nghiệm beta / pilot** | Sản phẩm hoạt động thế nào với một nhóm người dùng phù hợp? | Dữ liệu vận hành, phản hồi sử dụng | Mở rộng khi chưa có phương án xử lý lỗi |
| **A/B test** | Hai biến thể tác động khác nhau thế nào dưới phân bổ hợp lệ? | Ước lượng tác động có điều kiện | Kết luận nhân quả từ nhóm tự chọn không ngẫu nhiên |
| **Feature flag** | Có thể bật/tắt hoặc triển khai dần an toàn không? | Giảm rủi ro phát hành, thu phản hồi theo phạm vi | Để cờ tồn tại vô hạn, tạo nhiều tổ hợp phức tạp |
| **Phân tích dữ liệu sản phẩm** | Người dùng thực sự đi qua luồng nào? | Chỉ số hành trình, điểm rơi, phân khúc | Đồng nhất tương quan với nguyên nhân |
| **Review/retrospective** | Cách phối hợp và kỹ thuật đã hỗ trợ/hạn chế điều gì? | Thử nghiệm cải tiến cụ thể | Chỉ nêu cảm nhận mà không thực hiện thay đổi |

Lựa chọn kỹ thuật theo **quyết định cần hỗ trợ**. Không cần sử dụng mọi công cụ trước mỗi PBI. Một prototype có thể trả lời câu hỏi về cách người dùng hiểu giao diện, nhưng không đủ để chứng minh hiệu năng dịch vụ ở tải cao. Một spike kỹ thuật có thể chứng minh API kết nối được, nhưng không chứng minh người dùng muốn tính năng.

### 8.1. Viết spike như một hạng mục học hỏi có điểm kết thúc

Một spike tốt có thể có cấu trúc:

> **Câu hỏi:** Dịch vụ gợi ý bên ngoài có đáp ứng giới hạn độ trễ và quyền dữ liệu được phép không?  
> **Giới hạn:** Thử trên tập dữ liệu được phê duyệt, không đưa thông tin nhạy cảm thật vào dịch vụ thử.  
> **Cách thử:** Tích hợp tối thiểu, đo độ trễ và kiểm tra các giới hạn API; rà soát với người có thẩm quyền dữ liệu.  
> **Thời gian:** Một khoảng timebox do nhóm thống nhất để kiểm soát chi phí học.  
> **Đầu ra:** Bảng kết quả, rủi ro còn lại và khuyến nghị giữ hoặc loại phương án.  
> **Không được hiểu là:** Đã hoàn thành hệ thống gợi ý sẵn sàng production.

### 8.2. Học hỏi bằng phần tăng dần có thể dùng

Khi có thể, nhóm nên giao một **lát cắt giá trị nhỏ** thay vì chỉ xây các thành phần kỹ thuật riêng lẻ:

1. Hiển thị nhãn trình độ và điều kiện tiên quyết cho một nhóm khóa.
2. Quan sát người học có chọn đúng khóa dễ hơn không.
3. Cải thiện bộ lọc nếu vẫn có khó khăn.
4. Chỉ xem xét hệ thống gợi ý phức tạp nếu còn nhu cầu có bằng chứng.

Lát cắt nhỏ giúp vừa **giao giá trị thật** vừa **tạo học hỏi**. Nhưng khi phát hành cho người dùng, phải bảo vệ an toàn, quyền riêng tư, khả năng truy cập và tiêu chuẩn chất lượng.

## 9. Viết giả thuyết và quyết định bằng bằng chứng

Một giả thuyết tốt cho biết **người dùng nào, thay đổi nào, kết quả dự kiến nào và cần quan sát ra sao**.

### 9.1. Mẫu giả thuyết

> “Đối với [người dùng/bối cảnh], nếu chúng ta [thay đổi nhỏ], thì [kết quả có thể quan sát] sẽ được cải thiện vì [giả định cơ chế]. Chúng ta sẽ đo [tín hiệu chính], theo dõi [rủi ro/guardrail] và xem lại sau [khoảng học hỏi hợp lý].”

Ví dụ:

> “Đối với người học mới tìm khóa Java, nếu hiển thị rõ trình độ và điều kiện tiên quyết ngay trong danh sách, người học sẽ ít chọn khóa vượt năng lực hơn vì họ có thông tin trước khi mở chi tiết. Chúng ta sẽ quan sát nhiệm vụ tìm khóa phù hợp, tỷ lệ chọn đúng trong bài thử và phản hồi về mức dễ hiểu; đồng thời kiểm tra khả năng tiếp cận.”

**Đừng đặt toàn bộ kế hoạch thử nghiệm bằng một chỉ số duy nhất nếu hành vi phức tạp.** Tỷ lệ nhấp có thể tăng vì tiêu đề gây tò mò, nhưng tỷ lệ bắt đầu học thành công không tăng.

### 9.2. Tạo bản ghi quyết định ngắn

| Trường | Ví dụ |
| --- | --- |
| Vấn đề | Người học mới chọn khóa quá khó |
| Giả thuyết | Thiếu thông tin trình độ và điều kiện tiên quyết |
| Các phương án còn mở | A: nhãn trình độ; B: bộ lọc; C: hệ thống gợi ý |
| Bằng chứng ban đầu | Phỏng vấn và quan sát cho thấy người học bỏ qua mô tả dài |
| Thử nghiệm tiếp theo | Prototype hiển thị điều kiện đầu vào trong danh sách |
| Tín hiệu chính | Hoàn thành nhiệm vụ chọn đúng khóa trong thử nghiệm |
| Guardrail | Khả năng tiếp cận, không hiển thị thông tin sai hoặc gây hiểu lầm |
| Điểm xem lại | Khi có đủ phiên thử có chất lượng để nhận diện vấn đề lớn |
| Người tham gia quyết định | Product Owner cùng Developers, thiết kế, nghiên cứu và bên liên quan theo thẩm quyền |

Kết luận có thể là **giữ A, điều chỉnh B và loại C ở giai đoạn này**. Không cần chứng minh một phương án là tốt nhất cho mọi thời điểm tương lai.

## 10. Ví dụ trọn vẹn: chọn phương án giúp người học tìm đúng khóa

### 10.1. Bối cảnh

Nền tảng học trực tuyến ghi nhận một số người học mới đăng ký khóa nâng cao rồi bỏ học sớm. Product Owner đề xuất “xây hệ thống gợi ý thông minh”. Developers và người thiết kế nhận thấy giả thuyết cạnh tranh: **vấn đề có thể nằm ở cách diễn giải trình độ**, không phải thiếu thuật toán.

Nhóm thống nhất **chưa cam kết xây hệ thống AI**, nhưng không dừng phát triển. Họ chọn ba hoạt động học hỏi:

1. Quan sát người dùng mới chọn khóa trong danh mục hiện tại.
2. Thử prototype có nhãn trình độ và điều kiện đầu vào.
3. Kiểm tra kỹ thuật, dữ liệu và quyền riêng tư của phương án gợi ý phức tạp ở mức tối thiểu.

### 10.2. Một tập dữ liệu thử nghiệm giả định

Trong bài tập minh họa, nhóm tiến hành **hai vòng usability testing riêng** với tổng 20 lượt thực hiện nhiệm vụ, **mỗi vòng 10 lượt**. Cách tuyển chọn, mức độ độc lập và tính tương đồng giữa hai vòng chưa đủ để xem đây là A/B test ngẫu nhiên.

| Tín hiệu quan sát | Giao diện hiện tại (10 lượt) | Prototype có nhãn trình độ (10 lượt) |
| --- | ---: | ---: |
| Chọn được khóa phù hợp theo tiêu chí nhiệm vụ | 4 | 7 |
| Chọn sai hoặc cần trợ giúp | 6 | 3 |
| Tỷ lệ hoàn thành nhiệm vụ | 40% | 70% |

Trong hai nhóm thử có tỷ lệ hoàn thành khác nhau **30 điểm phần trăm**:

\[
70\%-40\%=30\ \text{điểm phần trăm}
\]

Tuy nhiên, **không thể từ dữ liệu nhỏ và không ngẫu nhiên này kết luận prototype gây tăng 30 điểm phần trăm cho toàn bộ người dùng**. Những người tham gia có thể khác kinh nghiệm; thứ tự nhiệm vụ, độ khó khóa và cách điều phối cũng ảnh hưởng.

Kết quả hợp lý là: prototype **có tín hiệu đáng thử tiếp**, đặc biệt nếu người dùng nêu rõ nhãn trình độ giúp họ quyết định. Nhóm nên tiếp tục xác minh trên dữ liệu thực tế, phân khúc liên quan hoặc thử nghiệm được thiết kế phù hợp trước khi tuyên bố tác động định lượng lớn.

### 10.3. Học được gì và nên cam kết gì?

- Dữ liệu định tính cho biết người học thường không đọc mô tả dài nhưng chú ý nhãn ngắn.
- Prototype đơn giản có tín hiệu hữu ích và chi phí triển khai thấp hơn.
- Phương án AI có thêm ràng buộc dữ liệu và chi phí vận hành chưa được giải quyết.
- Thay vì đầu tư toàn bộ hệ thống gợi ý, nhóm **chốt một lát cắt nhỏ**: hiển thị nhãn trình độ và điều kiện đầu vào cho những khóa có dữ liệu đã được xác nhận.
- Nhóm **chưa loại vĩnh viễn** ý tưởng gợi ý: đưa nó vào Product Backlog như một lựa chọn có thể xem lại nếu bằng chứng sau này cho thấy nhu cầu lớn hơn.

Đây là ví dụ của **học hỏi dẫn tới cam kết vừa đủ**. Nhóm không để bất định làm tê liệt, nhưng cũng không biến một ý tưởng hấp dẫn thành quyết định kiến trúc khó đảo ngược quá sớm.

### 10.4. Acceptance criteria cho lát cắt đầu tiên

~~~gherkin
Tính năng: Thông tin trình độ trước khi chọn khóa

  Tình huống: Khóa có trình độ được xác nhận
    Cho trước khóa "Java nhập môn" có trình độ "Cơ bản"
    Và khóa có điều kiện đầu vào đã được xác minh
    Khi người học xem thẻ khóa trong danh sách tìm kiếm
    Thì thẻ khóa hiển thị trình độ "Cơ bản"
    Và cung cấp cách xem điều kiện đầu vào

  Tình huống: Khóa chưa được phân loại trình độ
    Cho trước khóa "Java thực hành" chưa có dữ liệu trình độ xác nhận
    Khi người học xem khóa trong danh sách
    Thì hệ thống không tự gắn nhãn "Cơ bản" hoặc "Nâng cao"
    Và sử dụng cách diễn đạt chưa phân loại theo quy tắc đã thống nhất
~~~

Tiêu chí chấp nhận giúp kiểm chứng **hành vi của lát cắt**. Nhóm vẫn phải đáp ứng **Definition of Done** và yêu cầu chất lượng, bảo mật, khả năng tiếp cận liên quan. Việc đạt tiêu chí không tự chứng minh outcome dài hạn đã tăng.

## 11. Học nhanh nhưng giữ chất lượng và an toàn

Các khẩu hiệu “fail fast”, “thử nhanh”, “đẩy bản mẫu ra người dùng” dễ gây hiểu nhầm nếu không phân biệt môi trường và hậu quả.

| Ngữ cảnh | Có thể thử nhanh như thế nào? | Giới hạn cần bảo vệ |
| --- | --- | --- |
| Bản phác thảo UI | Cho người dùng mục tiêu thử thao tác giả lập | Không lừa họ rằng giao dịch thật đã diễn ra |
| Spike tích hợp | Thử trên sandbox, dùng dữ liệu giả hoặc được phép | Không chuyển dữ liệu nhạy cảm sang dịch vụ chưa được phê duyệt |
| Thử tính năng beta | Phát hành giới hạn với thông tin và hỗ trợ phù hợp | Quyền riêng tư, khả năng rollback và giám sát |
| A/B test | Phân nhóm hợp lệ, định trước chỉ số chính/guardrail | Không dùng thử nghiệm gây hại hoặc vi phạm quyền người dùng |
| Thay đổi thanh toán | Kiểm thử ở môi trường được kiểm soát, tiến tới rollout an toàn | Không bỏ qua tính đúng đắn, phân quyền và nghĩa vụ pháp lý |
| Sự cố bảo mật | Khoanh vùng, khắc phục theo quy trình đã phê duyệt | Không chờ “tích lũy bằng chứng thị trường” trước khi bảo vệ người dùng |

**Phản hồi sớm không đồng nghĩa phát hành mã chưa đủ chất lượng.** Nhóm có thể học bằng prototype hoặc thử nghiệm được kiểm soát, sau đó chỉ giao Increment đáp ứng chuẩn hoàn tất và nghĩa vụ tương ứng.

### 11.1. “Thử thất bại” khác “gây lỗi không cần thiết”

Một giả thuyết bị bác bỏ có thể là **thành công về học hỏi**: nhóm đã biết không nên xây một hướng tốn kém. Nhưng phát hành tính năng không kiểm thử làm mất dữ liệu hoặc gây giao dịch sai không phải thất bại tích cực để cổ vũ. Lean ưu tiên **thử nghiệm có mục đích và giới hạn rủi ro**.

### 11.2. Chất lượng kỹ thuật giúp giữ lựa chọn

Thiết kế mô-đun vừa đủ, kiểm thử tự động, tích hợp liên tục, refactoring và các phần giao nhỏ giúp chi phí đổi hướng thấp hơn. Tuy vậy, thiết kế trừu tượng quá sớm chỉ để hỗ trợ mọi tương lai tưởng tượng có thể tạo **complexity waste**. Nên xây khả năng thay đổi tương ứng với **rủi ro đã nhận diện**, không biến “linh hoạt” thành yêu cầu vô hạn.

## 12. Lean, Scrum, Kanban và XP bổ sung nhau như thế nào?

### 12.1. Lean: nguyên tắc chọn cách học và thời điểm cam kết

Lean giúp nhìn toàn bộ dòng tạo giá trị: hạn chế công việc không cần thiết, học nhanh, giữ lựa chọn khi có ý nghĩa và tối ưu kết quả cho người dùng. Hai nguyên tắc trong bài là **định hướng ra quyết định**, không phải một bộ sự kiện hoặc vai trò bắt buộc.

### 12.2. Scrum: inspection và adaptation theo mục tiêu

Trong Scrum:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả **Product Backlog**, có thể điều chỉnh thứ tự sau phản hồi.
- **Product Backlog refinement** là cơ hội làm rõ, chia nhỏ PBI và giảm bất định trước khi lựa chọn công việc; đây là hoạt động liên tục, không phải event bắt buộc có thời lượng cố định.
- **Sprint Planning** giúp Scrum Team tạo Sprint Goal; Developers chọn PBI thông qua trao đổi với Product Owner và lên kế hoạch tạo Increment.
- **Daily Scrum** hỗ trợ Developers điều chỉnh kế hoạch dựa trên tiến độ hướng Sprint Goal.
- **Sprint Review** giúp kiểm tra kết quả và điều chỉnh Product Backlog theo thông tin mới.
- **Sprint Retrospective** giúp kiểm tra và cải tiến cách làm việc.

**Cam kết Sprint Goal không có nghĩa mọi chi tiết phương án phải được khóa cứng ở Sprint Planning.** Developers có thể điều chỉnh cách làm và cùng Product Owner làm rõ, thương lượng phạm vi khi học thêm, miễn giữ chất lượng và không làm nguy hiểm Sprint Goal.

Nếu một quyết định khiến Sprint Goal thực sự lỗi thời, chỉ **Product Owner** có quyền hủy Sprint. Không nên dùng “quyết định muộn” để biện minh cho việc liên tục đổi mục tiêu bất chấp cam kết Scrum.

### 12.3. Kanban: giới hạn WIP để học nhanh hơn

Một hệ thống có quá nhiều việc đang làm thường kéo dài thời gian đến lúc có **phản hồi thật**:

~~~mermaid
flowchart LR
    A["Quá nhiều công việc đang làm"] --> B["Chờ review, kiểm thử, quyết định"]
    B --> C["Cycle time tăng"]
    C --> D["Phản hồi thực tế đến muộn"]
    D --> E["Giả định sai được duy trì lâu hơn"]
    F["Giới hạn WIP và cùng hoàn tất"] --> G["Lát cắt Done sớm hơn"]
    G --> H["Nhận phản hồi và điều chỉnh sớm"]
~~~

Kanban có thể hỗ trợ:

- **Trực quan hóa WIP** và công việc bị chặn.
- Theo dõi **cycle time, work item age, throughput** để thấy phản hồi bị chậm ở đâu.
- Làm rõ **chính sách kéo việc**, ưu tiên hoàn tất trước khi bắt đầu thêm.
- Đưa các thí nghiệm nhỏ vào luồng với tiêu chí hoàn tất là **bằng chứng và quyết định**, không chỉ “đã làm nghiên cứu”.

Giảm WIP không tự đảm bảo tăng chất lượng học hỏi; nhóm vẫn cần đo **đúng câu hỏi** và trao đổi với người dùng phù hợp.

### 12.4. XP: phản hồi kỹ thuật nhanh và chi phí thay đổi thấp

XP có thể hỗ trợ Lean qua:

- **Test-driven development** và kiểm thử tự động để biết thay đổi có phá hành vi đã cam kết không.
- **Continuous integration** để phát hiện vấn đề tích hợp sớm.
- **Refactoring** để cải thiện thiết kế khi đã học thêm mà vẫn bảo vệ hành vi.
- **Small releases** để giao các lát cắt dùng được, nhận phản hồi nhanh.
- **Pair programming** và trao đổi thường xuyên với người hiểu nhu cầu để phát hiện giả định sai.

Không phải thực hành XP nào cũng bắt buộc cho mọi Scrum Team hoặc hệ thống Kanban. Chọn kỹ thuật theo mục tiêu giảm rủi ro, cải thiện phản hồi và đảm bảo chất lượng.

| Cách tiếp cận | Câu hỏi trọng tâm | Điểm đóng góp vào học hỏi và giữ phương án |
| --- | --- | --- |
| **Lean** | Học điều gì, khi nào cam kết, đâu là lãng phí? | Khung tư duy ra quyết định trong bất định |
| **Scrum** | Hướng giá trị nào trong Sprint, kiểm tra và thích ứng ra sao? | Sprint Goal, Product Backlog, Sprint Review, Retrospective |
| **Kanban** | Công việc đang chảy thế nào, chờ ở đâu? | WIP, cycle time, tuổi việc, chính sách luồng |
| **XP** | Thay đổi mã và tích hợp an toàn bằng cách nào? | Kiểm thử, CI, refactoring, phần giao nhỏ |

## 13. Đo xem nhóm có thực sự học và giữ phương án tốt hơn không

Không có **một chỉ số duy nhất** đo đầy đủ học hỏi. Nên kết hợp tín hiệu về quyết định, dòng công việc, chất lượng và giá trị sử dụng.

| Tín hiệu | Câu hỏi cần trả lời | Cách tránh ngộ nhận |
| --- | --- | --- |
| **Thời gian từ câu hỏi đến bằng chứng** | Nhóm có học đủ nhanh để hỗ trợ quyết định? | Nhanh mà bằng chứng yếu chưa chắc tốt |
| **Thời gian từ bắt đầu PBI đến Done** | Các lát cắt có đến tay người dùng đủ sớm? | Phân biệt Done và phát hành |
| **Work item age / WIP** | Công việc học hỏi bị tồn lâu ở đâu? | Không biến chỉ số thành mục tiêu cá nhân |
| **Tỷ lệ giả thuyết được kiểm chứng có kết luận** | Thử nghiệm có dẫn tới hành động? | Không ép mọi giả thuyết đều “được xác nhận” |
| **Số quyết định phải làm lại do thiếu bằng chứng có thể biết sớm** | Có khóa phương án quá sớm? | Phân biệt học hợp lý với lỗi dự đoán rõ ràng |
| **Chi phí giữ phương án** | Việc hỗ trợ nhiều lựa chọn có gây bảo trì phức tạp? | Không tối ưu độ linh hoạt mà bỏ giá trị |
| **Sự cố, lỗi hồi quy** | Thử nhanh có đang tạo rủi ro quá mức? | Bảo vệ DoD và quy tắc an toàn |
| **Outcome người dùng** | Giải pháp đã chọn có cải thiện vấn đề thật? | Không đồng nhất số tính năng với giá trị |
| **Khả năng giải thích quyết định** | Người mới có biết vì sao chọn phương án A? | Quyết định cần ngữ cảnh, không phải tài liệu dài |

### 13.1. Đừng thưởng cho “số thí nghiệm thất bại”

Nếu nhóm đặt KPI “mỗi Sprint phải có mười thí nghiệm”, các thành viên có thể tạo thí nghiệm nhỏ thiếu tác động để đạt chỉ tiêu. Tương tự, thưởng cho việc “xác nhận nhiều giả thuyết” dễ khiến người thử chọn câu hỏi dễ đúng và bỏ qua rủi ro lớn.

Thay vào đó hãy hỏi: **Bằng chứng nào đã thay đổi một quyết định quan trọng? Nhóm đã tránh làm điều gì không cần thiết? Người dùng đã nhận giá trị tốt hơn thế nào?**

### 13.2. Khi chưa thể đo outcome dài hạn

Một Sprint hoặc một đợt thử nhỏ có thể chỉ chứng minh người dùng hiểu nhãn trình độ hơn. Chưa có đủ thời gian để chứng minh tỷ lệ hoàn thành khóa học trong ba tháng tăng. Nhóm nên:

1. Ghi rõ **tín hiệu ngắn hạn** đã được kiểm tra.
2. Nêu **giả thuyết liên kết** tín hiệu đó với outcome dài hạn.
3. Lập kế hoạch theo dõi sau phát hành trong phạm vi dữ liệu được phép.
4. Tránh biến tín hiệu tạm thời thành lời khẳng định thành công kinh doanh chắc chắn.

## 14. Vai trò, thẩm quyền và cộng tác trong quyết định

“Giữ nhiều phương án” không có nghĩa không ai chịu trách nhiệm chốt hướng đi. Những người liên quan cần biết ai làm rõ giá trị, ai chịu trách nhiệm kỹ thuật và ai phê duyệt ràng buộc ngoài nhóm.

| Loại quyết định | Người cần tham gia | Câu hỏi chính |
| --- | --- | --- |
| Ưu tiên giá trị và Product Backlog trong Scrum | Product Owner, có ý kiến Developers và stakeholder | Học gì tiếp để tối đa hóa giá trị sản phẩm? |
| Cách triển khai trong Sprint | Developers, tham vấn Product Owner về giá trị/phạm vi | Phương án nào đáp ứng mục tiêu, DoD và rủi ro? |
| Thiết kế trải nghiệm người dùng | Developers/chuyên môn thiết kế, người dùng phù hợp, Product Owner | Trải nghiệm nào có thể kiểm chứng tốt nhất? |
| Quyền dữ liệu và bảo mật | Người có trách nhiệm an toàn, pháp lý hoặc quyền phê duyệt theo tổ chức | Phương án nào được phép và có thể kiểm soát rủi ro? |
| Hợp đồng nhà cung cấp dài hạn | Người có thẩm quyền mua sắm/hợp đồng và chuyên gia liên quan | Điểm cam kết, chi phí đổi nhà cung cấp, nghĩa vụ là gì? |
| Thử nghiệm sản phẩm | Nhóm sản phẩm, người phụ trách dữ liệu/chất lượng và các bên liên quan | Đo gì, đối tượng nào, rủi ro chấp nhận được, khi nào dừng? |

**Trao đổi sớm với người có thẩm quyền giúp giữ phương án thực sự khả thi.** Nếu pháp lý không cho phép dữ liệu cá nhân đi qua dịch vụ ngoài, việc âm thầm xây một tích hợp trước rồi mới xin phép không phải “học nhanh”.

### 14.1. Trách nhiệm quyết định và trách nhiệm tạo bằng chứng

Một người có thể chịu trách nhiệm cuối cùng về ưu tiên sản phẩm, nhưng bằng chứng cần được cùng tạo ra. Product Owner không phải tự thiết kế mọi thử nghiệm; Developers không nên tự kết luận về giá trị người dùng chỉ dựa trên hiệu năng mã; người thiết kế không thể tự thay quy tắc pháp lý.

**Cộng tác** giúp phát hiện giả định ẩn; **thẩm quyền rõ** giúp quyết định được đưa ra đúng lúc.

## 15. Dấu hiệu nên quyết định ngay, nên học thêm hay nên dừng

Một bảng lựa chọn đơn giản:

| Tình huống | Hướng hợp lý | Lý do |
| --- | --- | --- |
| Thay đổi nhỏ, dễ đảo ngược, giá trị học qua sử dụng cao | **Chọn và thử sớm** | Không đáng tốn nhiều công phân tích trước |
| Quyết định khó đảo ngược, dữ liệu chưa đủ, còn thời gian học | **Giữ lựa chọn, thiết kế thử nghiệm** | Có khả năng tránh quyết định sai tốn kém |
| Thông tin mới khó có thể thay đổi lựa chọn | **Chốt và triển khai** | Học thêm có ít giá trị biên |
| Điểm cam kết lịch hoặc kỹ thuật đang đến gần | **Chốt theo bằng chứng tốt nhất có thể** | Tránh để việc chờ làm mất lựa chọn |
| Phương án vi phạm yêu cầu an toàn/tuân thủ | **Loại hoặc sửa phương án** | Ràng buộc bắt buộc không phải tùy chọn |
| Thí nghiệm liên tục không tạo ra câu trả lời | **Dừng, sửa câu hỏi hoặc phương pháp** | Tránh “nghiên cứu mãi” |
| Giữ nhiều phương án khiến chi phí và WIP tăng mạnh | **Thu hẹp có chủ đích** | Chi phí duy trì đã vượt lợi ích học hỏi |
| Nhu cầu người dùng không còn hiện hữu | **Dừng sáng kiến** | Không tiếp tục vì đã đầu tư quá khứ |

Không nên dùng một nhãn “nên quyết định” cho mọi vấn đề. Hai yếu tố có tính quyết định thường là **khả năng đảo ngược** và **giá trị của thông tin bổ sung so với chi phí trì hoãn**.

## 16. Những ngộ nhận phổ biến

**1. “Quyết định muộn” nghĩa là trì hoãn càng lâu càng tốt.** Điểm đúng là *muộn nhất có trách nhiệm*: phải chốt trước khi chờ thêm gây rủi ro không chấp nhận được.

**2. “Giữ phương án” nghĩa là xây tất cả phương án song song.** Nhiều phương án chỉ cần được ghi lại hoặc thử ở quy mô nhỏ; xây nhiều hệ thống production có thể là lãng phí.

**3. “Tăng học hỏi” nghĩa là tổ chức nhiều cuộc họp.** Họp chỉ có ích nếu làm rõ câu hỏi, tạo hiểu biết có thể hành động hoặc giúp quyết định.

**4. “Thí nghiệm thất bại là công việc vô ích.”** Bằng chứng bác bỏ một lựa chọn tốn kém có thể tiết kiệm nhiều công sức sau này.

**5. “Fail fast cho phép thử bất kỳ điều gì trên người dùng thật.”** Thử nghiệm phải bảo vệ an toàn, quyền riêng tư, khả năng tiếp cận và các nghĩa vụ áp dụng.

**6. “Prototype đã hoạt động nên có thể phát hành.”** Prototype thường chưa đáp ứng mọi tiêu chuẩn chất lượng, bảo mật và vận hành của sản phẩm.

**7. “Thử càng nhiều càng học càng nhiều.”** Thiết kế đo lường, tính đại diện và khả năng ảnh hưởng quyết định quan trọng hơn số lượng thử.

**8. “Người dùng nói thích tính năng nên chắc chắn cần xây.”** Lời nói, hành vi thực tế, nhu cầu và bối cảnh có thể khác nhau; cần kiểm chứng đúng câu hỏi.

**9. “A/B test có kết quả cao hơn thì nguyên nhân đã rõ.”** Cần thiết kế phân bổ, cỡ mẫu, thời gian, guardrail và phân tích phù hợp; tương quan không tự chứng minh nhân quả.

**10. “Giữ lựa chọn mở luôn rẻ hơn quyết định sớm.”** Cấu trúc trừu tượng, nhiều nhà cung cấp hoặc hai hệ thống song song có thể rất tốn chi phí.

**11. “Kiến trúc linh hoạt là kiến trúc dự đoán được mọi tương lai.”** Trừu tượng hóa quá mức tạo độ phức tạp không cần thiết; nên bảo vệ khả năng thay đổi ở những ranh giới có rủi ro thật.

**12. “Một mẫu dữ liệu nhỏ chứng minh chắc chắn toàn bộ người dùng sẽ hành động như vậy.”** Kết quả cần được diễn giải theo cỡ mẫu, cách tuyển chọn và mức bất định.

**13. “Đã ước lượng thì không cần học thêm.”** Ước lượng là giả định; phản hồi sớm giúp cập nhật kế hoạch và phạm vi.

**14. “Scrum bắt buộc khóa mọi yêu cầu từ Sprint Planning.”** Trong Scrum, Developers có thể điều chỉnh cách làm và thương lượng phạm vi với Product Owner khi học thêm, đồng thời giữ Sprint Goal và DoD.

**15. “Số story hoàn tất càng nhiều là tốc độ học càng nhanh.”** Throughput đo công việc Done; muốn biết học nhanh cần xem thời gian tới bằng chứng và chất lượng quyết định.

**16. “Khi đã đầu tư nhiều thì phải chọn phương án đó.”** Chi phí đã bỏ ra là *sunk cost*; quyết định tiếp theo cần dựa trên giá trị và chi phí tương lai, không chỉ vì tiếc công.

**17. “Quyết định sớm luôn sai.”** Với lựa chọn dễ đảo ngược hoặc nghĩa vụ bắt buộc, hành động sớm có thể tốt hơn trì hoãn.

**18. “Học hỏi là công việc của Product Owner, kỹ thuật chỉ làm theo.”** Developers, kiểm thử, thiết kế, vận hành và người hiểu nghiệp vụ đều đóng góp bằng chứng và hiểu biết, với thẩm quyền quyết định rõ ràng.

## 17. Bài tập tình huống: ba phương án cho chức năng gợi ý khóa

Một nhóm phát triển nền tảng học trực tuyến muốn tăng khả năng người học mới chọn đúng khóa. Họ có **sáu tuần** trước thời điểm khai giảng quan trọng. Có ba phương án:

| Phương án | Thời gian triển khai giả định | Rủi ro chính | Khả năng đổi hướng |
| --- | ---: | --- | --- |
| **A — Nhãn trình độ và bộ lọc cơ bản** | 1–2 tuần | Nhãn chưa phản ánh điều kiện thật của khóa | Cao |
| **B — Gợi ý từ metadata nội dung** | 3–4 tuần | Metadata thiếu hoặc không nhất quán | Trung bình |
| **C — Dịch vụ AI bên ngoài** | 4 tuần sau khi chốt | Quyền dữ liệu, chi phí, độ trễ, lệ thuộc nhà cung cấp | Thấp hơn nếu tích hợp sâu |

Nhóm có thể dành **tối đa hai tuần đầu** cho việc học, nếu vẫn đủ thời gian làm các bước triển khai/kiểm thử/phát hành bắt buộc sau quyết định. Trong tuần đầu, nhóm đã:

- Phỏng vấn và quan sát một nhóm nhỏ người học; nhiều người không hiểu nhãn “Nâng cao”.
- Xác nhận dữ liệu trình độ có thể chuẩn hóa, nhưng metadata mô tả kỹ năng còn thiếu.
- Nhận thấy phương án C phải qua đánh giá quyền dữ liệu chưa hoàn tất.
- Có bản mẫu A hoạt động cho một nhóm khóa.

### Câu hỏi

1. Nhóm đang có các loại bất định nào? Hãy phân biệt **nhu cầu, kỹ thuật, dữ liệu và tuân thủ**.
2. Nếu chọn C ngay ngày đầu, nhóm có thể chịu những chi phí quyết định sớm nào?
3. Vì sao “giữ cả A, B, C” không có nghĩa phải xây đồng thời cả ba tính năng hoàn chỉnh?
4. Đề xuất **ba hoạt động học hỏi nhỏ** trong thời gian còn cho phép, và chỉ rõ câu hỏi mỗi hoạt động trả lời.
5. Khi nào nhóm nên **loại** C khỏi tập phương án, thay vì tiếp tục thử nghiệm?
6. Với thời gian sáu tuần và bốn tuần tối thiểu để triển khai C sau khi chốt, điểm chốt muộn nhất theo giả định là khi nào?
7. Nếu phương án A đã giúp người học hiểu trình độ tốt hơn nhưng chưa có bằng chứng về outcome dài hạn, nên nói kết quả thế nào?
8. Tạo một Product Backlog gồm vài lát cắt nhỏ có thể giao giá trị hoặc học hỏi; ghi rõ đầu ra của từng lát cắt.

### Gợi ý lời giải

**Câu 1:** Bất định về nhu cầu: người học cần gợi ý phức tạp hay thông tin trình độ rõ hơn? Về dữ liệu: metadata và nhãn trình độ có đủ chính xác không? Về kỹ thuật: độ trễ và tích hợp phương án C ra sao? Về tuân thủ: dữ liệu cá nhân có được phép chuyển tới bên thứ ba không?

**Câu 2:** C có thể khiến nhóm phụ thuộc nhà cung cấp, phát sinh chi phí tích hợp và vận hành, phải thay kiến trúc nếu dữ liệu không được phép sử dụng hoặc người học thực ra chỉ cần bộ lọc đơn giản. Sự đầu tư sớm làm **tăng chi phí đổi hướng**.

**Câu 3:** Giữ tập phương án có thể là ghi điều kiện chọn, prototype một màn hình, thử tích hợp tối thiểu và rà soát dữ liệu. Mục tiêu là **mua thêm thông tin với chi phí hợp lý**, không phải nhân ba tổng công việc sản xuất.

**Câu 4:** Ví dụ:

- Thử nhiệm vụ chọn khóa với prototype A để xem người học hiểu trình độ hơn không.
- Kiểm tra chất lượng metadata của một mẫu khóa để xác định B có dữ liệu cần thiết không.
- Rà soát quyền dữ liệu và chạy spike sandbox cho C để biết nó có thể hợp lệ và đáp ứng giới hạn kỹ thuật không.

**Câu 5:** Nếu C không đáp ứng ràng buộc quyền dữ liệu bắt buộc và không có cách khắc phục hợp lệ trước thời điểm phải chốt, hoặc chi phí/rủi ro rõ ràng vượt lợi ích, nên loại hoặc hoãn C. Không giữ C chỉ vì công nghệ hấp dẫn.

**Câu 6:** \(6-4=2\) tuần kể từ lúc bắt đầu là điểm chốt **muộn nhất theo giả định đơn giản**, trước khi tính thêm rủi ro và khoảng dự phòng. Nếu chưa đủ bằng chứng tới điểm này, phải chọn phương án khả thi nhất hoặc điều chỉnh phạm vi/mốc theo thẩm quyền; không tiếp tục chờ vô hạn.

**Câu 7:** Nêu rằng thử nghiệm **có tín hiệu người học hiểu nhãn tốt hơn trong điều kiện mẫu hiện có**, chưa khẳng định tác động dài hạn hoặc quan hệ nhân quả cho toàn bộ người dùng. Cần theo dõi sau phát hành nếu muốn kết luận về chọn đúng khóa hoặc mức hoàn thành khóa học.

**Câu 8:** Backlog minh họa:

| PBI hoặc hoạt động | Giá trị / câu hỏi học hỏi | Dấu hiệu hoàn tất |
| --- | --- | --- |
| Chuẩn hóa trình độ cho nhóm khóa đầu tiên | Người học thấy thông tin nhất quán | Nhãn đúng theo quy tắc đã duyệt, có kiểm tra dữ liệu |
| Hiển thị nhãn và điều kiện đầu vào | Người học biết khóa phù hợp trước khi đăng ký | Lát cắt đạt acceptance criteria và DoD |
| Thử tính dễ hiểu với người học | Nhãn có giúp chọn đúng khóa? | Có ghi nhận quan sát, giới hạn và quyết định tiếp |
| Đánh giá metadata phục vụ gợi ý | B có khả thi với dữ liệu hiện có? | Có tỷ lệ thiếu/không nhất quán và phương án xử lý |
| Spike rủi ro dịch vụ ngoài | C có đáp ứng ràng buộc kỹ thuật và dữ liệu? | Có kết luận kỹ thuật/tuân thủ; không coi spike là production |

## 18. Danh sách kiểm tra trước một quyết định quan trọng

Hãy dùng như **câu hỏi gợi mở**, không phải cổng phê duyệt bắt buộc cho mọi story:

1. **Quyết định:** Ta thực sự sắp cam kết điều gì?
2. **Giá trị:** Người dùng hoặc mục tiêu sản phẩm sẽ được lợi thế nào?
3. **Bất định:** Điều chưa biết nào có thể đảo ngược lựa chọn?
4. **Độ đảo ngược:** Nếu chọn sai, đổi lại tốn bao nhiêu công, tiền và rủi ro?
5. **Phương án:** Có ít nhất một phương án đơn giản hơn hoặc có thể học sớm hơn không?
6. **Bằng chứng:** Ta đang có quan sát thực tế hay chỉ có giả định và ý kiến?
7. **Thử nghiệm:** Cách nhỏ nhất, hợp lệ và an toàn để lấy thêm bằng chứng là gì?
8. **Chi phí:** Giữ các lựa chọn mở cần bao nhiêu thời gian, độ phức tạp và công bảo trì?
9. **Điểm chốt:** Khi nào chờ thêm sẽ làm mất khả năng giao hoặc vượt ràng buộc?
10. **An toàn:** Có nghĩa vụ bảo mật, pháp lý, chất lượng hoặc khả năng tiếp cận cần giữ không?
11. **Thẩm quyền:** Ai phải tham gia và ai có quyền chốt?
12. **Đầu ra học hỏi:** Sau thử nghiệm, quyết định cụ thể nào sẽ thay đổi?
13. **Minh bạch:** Các giả định, phương án bị loại và lý do lựa chọn đã được ghi đủ rõ chưa?
14. **Thích ứng:** Sau khi cam kết, nhóm còn khả năng nhận phản hồi và điều chỉnh hợp lý không?
15. **Outcome:** Có kế hoạch quan sát tác động thực tế sau khi giao Increment không?

## 19. Tổng kết: nhanh ở vòng học, có trách nhiệm khi cam kết

Hai nguyên tắc **“tăng cường học hỏi”** và **“quyết định muộn nhất có trách nhiệm”** bổ sung cho nhau:

| Tăng cường học hỏi | Giữ phương án và cam kết có trách nhiệm |
| --- | --- |
| Đặt câu hỏi đúng và kiểm tra giả thuyết | Không khóa một giải pháp khó đảo ngược trước khi có lý do |
| Giao lát cắt nhỏ hoặc thử nghiệm có giới hạn | Giữ đủ lựa chọn có giá trị, không duy trì vô hạn |
| Nhận phản hồi từ người dùng, hệ thống và vận hành | So sánh giá trị thông tin với chi phí học và chi phí trì hoãn |
| Phân biệt bằng chứng với suy đoán | Chốt trước điểm không thể chờ thêm, đúng thẩm quyền |
| Điều chỉnh Product Backlog và phương án kỹ thuật | Bảo vệ DoD, an toàn và cam kết sản phẩm có liên quan |

**Ghi nhớ:** Lean không nói “hãy chậm quyết định để có vẻ linh hoạt” hay “thử thật nhiều bằng mọi giá”. Lean khuyến khích **tăng tốc quá trình tạo hiểu biết có ích**, duy trì những lựa chọn còn giá trị khi tương lai chưa rõ, rồi **cam kết tại thời điểm thích hợp dựa trên bằng chứng, rủi ro và chi phí trì hoãn**. Khi kết hợp với product backlog, Scrum, Kanban và kỷ luật kỹ thuật XP, nhóm có thể học nhanh từ phần mềm tăng dần, tránh khóa sớm các giải pháp sai và giữ khả năng thích ứng liên tục.
