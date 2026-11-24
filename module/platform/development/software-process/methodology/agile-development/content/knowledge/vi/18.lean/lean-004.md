# Giảm kích thước lô và rút ngắn thời gian tạo giá trị

Một đội phát triển có thể làm việc liên tục trong nhiều tuần nhưng người dùng vẫn chưa nhận được cải tiến nào. Họ đã phân tích, thiết kế, viết mã và chuẩn bị nhiều tính năng; tuy nhiên tất cả phải đợi tích hợp, kiểm thử và phát hành cùng một lần. Trong khi đó, giả định về nhu cầu chưa được kiểm chứng, lỗi tích tụ và công việc tiếp tục xếp hàng.

**Lean** nhìn vào **dòng giá trị từ nhu cầu đến kết quả sử dụng**, không chỉ mức độ bận rộn của từng cá nhân. Một cách cải tiến quan trọng là **giảm kích thước lô (reduce batch size)**: đưa những phần công việc nhỏ, có ý nghĩa, qua các bước của hệ thống với thời gian chờ và rủi ro có thể quản lý. Mục tiêu không phải làm thật nhiều ticket nhỏ, mà là **rút ngắn thời gian để người dùng nhận được giá trị và nhóm nhận được phản hồi đáng tin cậy**.

Bài này thuộc chương **Lean** của mô-đun **AGILE_DEVELOPMENT**, gắn với Agile qua phản hồi sớm, phần mềm tăng dần, cải tiến liên tục, user story, Product Backlog, Scrum, Kanban, XP và phép đo dòng công việc.

Sau bài học, bạn có thể:

- Phân biệt **kích thước lô, WIP, hàng đợi, thời gian xử lý, cycle time, lead time và time to value**.
- Giải thích vì sao lô lớn làm chậm phát hiện sai, tạo công việc dở dang và tăng rủi ro tích hợp.
- Chia một yêu cầu lớn thành **lát cắt dọc có thể bàn giao và kiểm chứng**.
- Kết hợp giới hạn WIP, cơ chế kéo việc, kiểm thử tự động và phát hành nhỏ để giảm thời gian chờ.
- Sử dụng Value Stream Mapping và dữ liệu dòng công việc để tìm nút thắt.
- Cân nhắc chi phí chuẩn bị mỗi lô, phụ thuộc, chất lượng và an toàn để không cực đoan hóa việc chia nhỏ.

## 1. Bắt đầu từ giá trị và thời điểm người dùng nhận được giá trị

Ví dụ một nền tảng học trực tuyến muốn giúp học viên **quay lại đúng vị trí đã học**. Nhóm có thể lập kế hoạch cả một gói gồm:

- Hiển thị tiến độ trên mọi màn hình.
- Đồng bộ nhiều thiết bị.
- Học offline.
- Gửi thông báo nhắc học.
- Báo cáo tiến độ cho người quản trị.

Các khả năng này có liên quan nhưng **không nhất thiết phải hoàn thành cùng lúc** mới giúp người học giải quyết một vấn đề. Nếu nhóm có thể bàn giao trước khả năng **lưu và khôi phục tiến độ đáng tin cậy trên một thiết bị**, họ đã có thể kiểm tra giá trị thực và nhận phản hồi về những phần cần cải thiện.

### Đầu ra, giá trị và phản hồi không phải một

| Khái niệm | Ví dụ nền tảng học | Ý nghĩa |
| --- | --- | --- |
| **Hoạt động** | Viết API lưu tiến độ | Công việc đang thực hiện, chưa chắc có phần mềm dùng được |
| **Đầu ra (output)** | Có màn hình và API lưu/đọc tiến độ | Khả năng đã được xây, cần xác minh chất lượng |
| **Increment có chất lượng** | Luồng lưu và khôi phục đạt tiêu chuẩn hoàn thành | Có phần sản phẩm tích hợp, hữu ích và có thể dùng |
| **Giá trị / outcome** | Người học không phải học lại phần đã hoàn thành | Kết quả mong muốn cho người dùng |
| **Phản hồi** | Người học báo rằng trạng thái “đang lưu” gây nhầm lẫn | Bằng chứng để điều chỉnh sản phẩm |

**Rút ngắn thời gian tạo giá trị** không được hiểu là “đẩy mã lên môi trường thật càng nhanh càng tốt”. Một lần phát hành làm mất dữ liệu học viên có thể nhanh về lịch nhưng phá hủy giá trị. Lean cần đồng thời quan tâm **thời gian, chất lượng, rủi ro và kết quả người dùng**.

## 2. Kích thước lô là gì trong phát triển phần mềm?

**Lô (batch)** là một nhóm đơn vị công việc được tích lũy rồi xử lý, chuyển giao hoặc phát hành cùng nhau. Khái niệm này có thể xuất hiện ở nhiều bước khác nhau:

| Loại lô | Ví dụ lô lớn | Ví dụ lô nhỏ hơn | Điều cần quan sát |
| --- | --- | --- | --- |
| **Lô phạm vi sản phẩm** | Làm toàn bộ hệ thống quản lý tiến độ mới thử | Làm một hành trình lưu/khôi phục có ích trước | Bao lâu mới kiểm chứng nhu cầu? |
| **Lô triển khai** | Thay đổi hàng chục module trong một nhánh dài ngày | Các thay đổi nhỏ tích hợp thường xuyên | Lỗi tích hợp phát hiện sớm hay muộn? |
| **Lô review** | Dồn nhiều thay đổi lớn rồi gửi review | Review những thay đổi có phạm vi dễ hiểu | Hàng đợi review và lỗi bị bỏ sót ra sao? |
| **Lô kiểm thử** | Đợi xong mọi tính năng mới kiểm thử tích hợp | Kiểm thử các lát cắt tích hợp theo từng bước | Lỗi đến tay nhóm khi nào? |
| **Lô triển khai/phát hành** | Gộp hàng tháng thay đổi vào một đợt | Phát hành các thay đổi đủ điều kiện thành từng phần | Rủi ro, thời gian phục hồi và phản hồi ra sao? |
| **Lô quyết định** | Chờ cuộc họp phê duyệt tất cả yêu cầu cuối tháng | Giải quyết câu hỏi cụ thể khi cần | Bao lâu công việc bị chặn do chờ quyết định? |

Không nên nhầm **số story trong một Sprint**, **số commit**, **số thay đổi triển khai** và **số chức năng người dùng nhìn thấy** thành cùng một loại lô. Nhóm có thể tích hợp mã thường xuyên nhưng chỉ cho người dùng thấy tính năng mới theo đợt; hoặc phát hành thường xuyên nhưng mỗi lần vẫn mang hàng chục thay đổi lớn.

### Giảm lô không đồng nghĩa chia nhỏ mọi thứ một cách máy móc

Một task “tạo bảng cơ sở dữ liệu” có thể rất nhỏ nhưng chưa tạo giá trị riêng. Một lát cắt như “học viên quay lại vị trí đã lưu trên cùng thiết bị” có thể đòi hỏi giao diện, API, dữ liệu và kiểm thử nhưng tạo ra **hành vi có thể kiểm chứng**.

Nguyên tắc là **giảm phạm vi phải hoàn thành cùng lúc trước khi nhận được giá trị hoặc phản hồi**, không chỉ tăng số dòng trên bảng công việc.

## 3. Vì sao lô lớn thường làm thời gian tới giá trị kéo dài?

### 3.1. Giá trị phải chờ hạng mục cuối cùng

Nếu một nhóm chỉ phát hành khi cả tám chức năng trong gói hoàn thành, chức năng xong đầu tiên vẫn phải chờ bảy chức năng sau. Thời điểm bàn giao được quyết định bởi **phần cuối cùng và các bước tích hợp, kiểm thử, phê duyệt sau đó**.

Nếu có thể phát hành các lát cắt độc lập đủ chất lượng, giá trị của phần đầu **không cần chờ** toàn bộ phạm vi lớn.

### 3.2. Phản hồi đến muộn làm tăng chi phí sửa sai

Giả sử nhóm thiết kế tính năng nhắc học qua SMS vì tin rằng học viên thường quên quay lại. Sau hai tháng mới phát hành, họ có thể phát hiện phần lớn học viên bỏ dở do **tiến độ không được lưu**. Công sức đầu tư vào kênh nhắc học chưa giải quyết vấn đề gốc.

Nếu nhóm sớm đưa ra một lát cắt có thể thử và quan sát, họ có cơ hội thay đổi thứ tự backlog **trước khi mở rộng đầu tư vào giả định sai**.

### 3.3. Lô lớn làm lỗi tích hợp và nguyên nhân khó truy tìm

Khi một đợt phát hành chứa nhiều thay đổi liên quan, nếu xuất hiện lỗi, nhóm cần kiểm tra nhiều khả năng gây ra lỗi hơn. Những thay đổi nhỏ, được tích hợp và kiểm chứng thường xuyên, thường giúp **thu hẹp phạm vi điều tra**.

Điều này không tự động đúng cho mọi hệ thống: một thay đổi nhỏ nhưng liên quan tới dữ liệu nhạy cảm hoặc cấu trúc nền tảng vẫn có rủi ro lớn. Kích thước lô cần đi cùng **kiểm soát chất lượng, khả năng quan sát và kế hoạch khôi phục**.

### 3.4. Nhiều công việc dở dang làm tăng chuyển ngữ cảnh

Nhóm mở nhiều tính năng đồng thời nhưng mỗi tính năng đang chờ một người, một quyết định hoặc một môi trường. Chuyển liên tục giữa các hạng mục làm mất ngữ cảnh và tăng khả năng bỏ sót. Quan trọng hơn, **người dùng chỉ nhận giá trị khi phần hữu ích thực sự hoàn thành**, không phải khi mười story đều đạt 80%.

### 3.5. Lô lớn có thể làm hàng đợi tích tụ

Khi nhiều thay đổi cùng đến một bước review hoặc kiểm thử, năng lực bước sau có thể không xử lý kịp. Các hạng mục chờ nhau. **Thời gian chờ** có thể lớn hơn rất nhiều so với **thời gian chủ động làm việc** trên từng hạng mục.

~~~mermaid
flowchart TD
    A["Lô lớn: nhiều hạng mục được bắt đầu"] --> B["Tích tụ WIP và phụ thuộc"]
    B --> C["Hàng đợi review, kiểm thử, quyết định"]
    C --> D["Phản hồi và giá trị đến muộn"]
    D --> E["Lỗi và giả định sai được phát hiện muộn"]
    E --> F["Làm lại và tăng thêm thời gian chờ"]
    F --> B
~~~

Đây là **cơ chế có thể xảy ra**, không phải định luật mọi lô lớn đều xấu. Một quá trình có chi phí thiết lập lớn đôi khi xử lý lô lớn hiệu quả hơn; nhóm cần kiểm tra cả hai phía của đánh đổi.

## 4. Tách thời gian xử lý khỏi thời gian chờ

Để cải tiến theo Lean, cần hiểu công việc dành thời gian ở đâu.

| Loại thời gian | Ví dụ | Điều cần xem xét |
| --- | --- | --- |
| **Thời gian xử lý chủ động** | Viết, review, chạy kiểm thử và phân tích kết quả | Hoạt động có thật sự cần thiết và tạo thông tin/giá trị không? |
| **Thời gian xếp hàng** | PR đợi người review, bản build đợi môi trường | Điều gì tạo hàng chờ và năng lực bước sau ra sao? |
| **Thời gian bị chặn** | Chưa có quyết định nghiệp vụ hoặc quyền truy cập | Ai có thể tháo gỡ và rào cản có lặp lại không? |
| **Thời gian sửa lại** | Sửa sai do phát hiện yêu cầu hiểu khác hoặc lỗi tích hợp | Làm sao nhận phản hồi sớm hơn? |
| **Thời gian chờ phát hành** | Chức năng đã hoàn thành nhưng chờ đợt phát hành tháng sau | Có thể phát hành phần nhỏ, an toàn và độc lập không? |

**Flow efficiency** là một góc nhìn có thể tính như sau, khi các mốc đo rõ ràng:

\[
\text{Flow efficiency} =
\frac{\text{thời gian xử lý chủ động}}{\text{tổng thời gian trong luồng}}
\times 100\%.
\]

Ví dụ một hạng mục mất 3 ngày xử lý và 9 ngày chờ trong tổng 12 ngày thì flow efficiency là **25%**. Chỉ số này **không nói nhân viên chỉ làm việc 25% thời gian**: họ có thể xử lý việc khác trong lúc hạng mục này chờ.

### Ví dụ thời gian của một lát cắt

Giả sử một user story đã được chọn thực hiện đi qua các bước không chồng lấn, tính theo **ngày làm việc**:

| Bước | Xử lý trực tiếp | Chờ |
| --- | ---: | ---: |
| Làm rõ quy tắc | 0,5 ngày | 2 ngày |
| Phát triển và tích hợp | 1,5 ngày | 3 ngày |
| Kiểm thử, xác nhận hành vi | 0,5 ngày | 2 ngày |
| Triển khai theo chính sách | 0,5 ngày | 2 ngày |
| **Tổng** | **3 ngày** | **9 ngày** |

Tổng thời gian theo mô hình tuần tự là **12 ngày**. Nếu chỉ yêu cầu lập trình viên viết mã nhanh hơn 20%, hiệu quả lên tổng thời gian có thể rất nhỏ; **giảm hàng chờ và thời gian chờ quyết định** có thể đáng đầu tư hơn.

Những con số trên là **giả định minh họa**. Trong thực tế, một số hoạt động có thể chồng lấn; cần thống nhất thời điểm bắt đầu, kết thúc và cách tính ngày làm việc hoặc ngày lịch để không cộng trùng.

## 5. Value Stream Mapping: nhìn toàn bộ hành trình từ nhu cầu tới giá trị

**Value Stream Mapping (VSM)** là cách phác họa các hoạt động, chuyển giao, hàng đợi và thông tin cần để đưa một yêu cầu từ đầu vào tới kết quả. Trong phần mềm, bản đồ có thể bắt đầu từ **phản hồi người dùng**, trải qua làm rõ, phát triển, kiểm thử, phát hành và quan sát sử dụng.

### Các bước lập bản đồ hiện trạng

1. **Chọn một loại công việc điển hình:** Ví dụ sửa lỗi mất tiến độ, không trộn với một dự án nền tảng nhiều tháng.
2. **Xác định mốc đầu/cuối:** Từ khi Product Backlog Item được chọn đến khi có thay đổi sử dụng được, hoặc từ lúc khách gửi yêu cầu đến khi nhận giá trị.
3. **Vẽ các bước và hàng đợi thật:** Bao gồm việc chờ review, chờ nghiệp vụ, chờ môi trường và chờ phát hành.
4. **Thu thập thời gian xử lý và chờ:** Dùng mẫu công việc thực tế, không chỉ ước lượng cảm tính.
5. **Đánh dấu rào cản và việc làm lại:** Ví dụ API thay đổi, lỗi test, hồ sơ phê duyệt thiếu.
6. **Chọn một thay đổi thử:** Giảm lô ở bước phù hợp, giới hạn WIP, chia story hoặc tự động hóa kiểm tra.
7. **Đo lại và xem kết quả sử dụng:** Đảm bảo cải tiến không chỉ chuyển hàng đợi sang bộ phận khác.

~~~mermaid
flowchart LR
    A["Nhu cầu người học"] --> B["Làm rõ: xử lý 0,5 ngày"]
    B --> C["Chờ 2 ngày"]
    C --> D["Phát triển: 1,5 ngày"]
    D --> E["Chờ 3 ngày"]
    E --> F["Kiểm thử: 0,5 ngày"]
    F --> G["Chờ 2 ngày"]
    G --> H["Triển khai: 0,5 ngày"]
    H --> I["Chờ 2 ngày"]
    I --> J["Người dùng nhận thay đổi"]
~~~

Với ví dụ này, nhóm có thể phát hiện **nút thắt không nằm chủ yếu ở thời gian viết mã**. Một hướng cải tiến là để người hiểu nghiệp vụ trao đổi trực tiếp khi cần, tích hợp và kiểm thử những thay đổi nhỏ thường xuyên, đồng thời giảm phụ thuộc vào đợt phát hành lớn.

### Đừng loại bỏ các bước tạo chất lượng chỉ vì chúng “tốn thời gian”

Kiểm thử bảo mật, bảo vệ dữ liệu người học và kiểm chứng trạng thái lưu thành công có thể không hiển thị trực tiếp trên màn hình, nhưng chúng **bảo vệ giá trị sản phẩm**. Lean không có nghĩa loại bỏ kiểm soát cần thiết. Thay vào đó, hãy hỏi **có thể đưa kiểm soát sớm hơn, rõ hơn hoặc tự động hóa có trách nhiệm không**, thay vì dồn vào cuối một lô lớn.

## 6. Một phép so sánh: lô lớn và lô nhỏ có cùng năng lực thực hiện

Giả sử nhóm có **bốn lát cắt độc lập**, mỗi lát cắt cần:

- **2 ngày** phát triển.
- **1 ngày** tích hợp và kiểm chứng.
- Nếu phát hành riêng, thêm **0,5 ngày** chi phí thực hiện phát hành.
- Nếu gộp cả bốn lát cắt, công tác phát hành chung mất **1 ngày**.

Để dễ so sánh, giả sử cùng một luồng thực hiện **tuần tự**, không có ngày nghỉ, không có công việc chen ngang và mỗi lát cắt đều có chất lượng đủ để sử dụng. Đây là một mô hình minh họa, không phải dự báo dự án thật.

| Phương án | Cách tính | Khi nào lát cắt đầu tiên tới người dùng? | Khi nào cả bốn tới người dùng? |
| --- | --- | ---: | ---: |
| **Lô lớn, một đợt** | 4 × (2 + 1) + 1 ngày phát hành | **Ngày 13** | **Ngày 13** |
| **Lô nhỏ, bốn đợt** | Mỗi lát cắt 2 + 1 + 0,5 ngày | **Ngày 3,5** | **Ngày 14** |

**Bài học chính:** Lô nhỏ giúp **giá trị và phản hồi đầu tiên xuất hiện sớm hơn rất nhiều**, nhưng trong ví dụ **không làm toàn bộ gói hoàn thành nhanh hơn** vì bốn lần phát hành có tổng chi phí lớn hơn một lần phát hành chung. Vì vậy, không nên tuyên bố “chia nhỏ luôn làm mọi thứ nhanh hơn”.

Điều đáng giá là sau ngày 3,5, nhóm có thể học điều người dùng thực sự cần. Nếu hai lát cắt còn lại dựa trên một giả định sai, họ có cơ hội **đổi hướng trước khi tiêu tốn toàn bộ công sức**. Khi đội cải thiện tự động hóa và giảm chi phí phát hành riêng, lợi thế kinh tế của lô nhỏ có thể tăng.

### Nhận biết “lát cắt độc lập” thật

Nếu bốn phần trên chỉ là **cơ sở dữ liệu, API, frontend và tài liệu** mà phần đầu không có hành vi sử dụng được, ngày 3,5 chưa chắc đem lại giá trị người dùng. Để nhận phản hồi về sản phẩm, mỗi lát cắt cần **đủ thành phần đầu-cuối** và có giới hạn sử dụng rõ ràng.

## 7. Chia tính năng lớn thành các lát cắt dọc có ý nghĩa

Một lát cắt dọc (**vertical slice**) đi qua những lớp kỹ thuật cần thiết để tạo ra **một hành vi có thể kiểm chứng**, thay vì chia việc chỉ theo bộ phận.

### Từ một epic lớn tới các lát cắt

**Epic ban đầu:** “Hệ thống quản lý tiến độ học tập đa thiết bị, có học offline, nhắc học và báo cáo”.

Nhóm có thể chia:

| Lát cắt | Người dùng nhận được gì? | Giả định hoặc rủi ro được kiểm chứng |
| --- | --- | --- |
| **A. Xem tiến độ đang học** | Học viên biết bước gần nhất đã hoàn thành | Trạng thái hiển thị có dễ hiểu không? |
| **B. Khôi phục tiến độ trên cùng thiết bị** | Học viên quay lại đúng vị trí đã lưu | Dữ liệu có được lưu/đọc tin cậy không? |
| **C. Thông báo rõ khi lưu thất bại** | Học viên không tưởng dữ liệu đã được bảo toàn khi chưa lưu | Giao diện có giảm hiểu nhầm không? |
| **D. Đồng bộ khi đổi thiết bị** | Học viên tiếp tục ở thiết bị thứ hai | Quy tắc đồng bộ và xung đột có đúng không? |
| **E. Học offline trong phạm vi giới hạn** | Học viên học một nội dung được hỗ trợ khi không có mạng | Quyền truy cập, dữ liệu và đồng bộ sau kết nối ra sao? |
| **F. Nhắc học theo lựa chọn của người học** | Học viên nhận nhắc khi muốn | Nhắc học có cải thiện việc quay lại hay gây phiền? |

**Thứ tự là ví dụ, không phải kế hoạch bắt buộc.** Nếu lỗi lưu tiến độ có thể làm mất dữ liệu, xử lý tính đúng đắn và bảo vệ dữ liệu là điều kiện của những lát cắt liên quan; không được trì hoãn an toàn để “ra phiên bản nhỏ nhanh hơn”.

### Dùng user story làm đầu mối hội thoại

Ví dụ:

> Là học viên đang học dở, tôi muốn mở lại bài tại tiến độ đã lưu thành công, để không phải tìm và học lại những phần đã hoàn thành.

Tiêu chí chấp nhận minh họa:

1. Sau khi hệ thống xác nhận lưu thành công ở bước 4, tải lại bài hiển thị đúng bước 4.
2. Khi kết nối ngắt trước khi hệ thống xác nhận, giao diện không báo “đã lưu thành công”.
3. Học viên nhận thông báo phù hợp để kiểm tra hoặc thử lại khi cần.
4. Các kiểm soát truy cập và chất lượng được áp dụng theo yêu cầu hệ thống.

Một story như vậy có thể cần UI, API, lưu trữ, kiểm thử và một đường phát hành, nhưng giúp nhóm **học từ một khả năng có ý nghĩa**, không chỉ từ những task kỹ thuật.

### INVEST hỗ trợ nhưng không thay mục tiêu

INVEST là cách xem story có tương đối **độc lập, có thể thương lượng, có giá trị, ước lượng được, đủ nhỏ và có thể kiểm chứng** không. Một story nhỏ mà không có người hưởng lợi hay khó nhận phản hồi có thể không phải lát cắt phù hợp. Một Product Backlog Item kỹ thuật giảm rủi ro cũng có thể quan trọng dù không viết tự nhiên bằng mẫu user story.

## 8. Giảm WIP để tránh nhiều lô công việc dở dang

Giảm kích thước lô **không có nhiều tác dụng** nếu nhóm bắt đầu quá nhiều lát cắt cùng lúc và không hoàn tất được cái nào. **WIP (work in progress)** là số hạng mục đã bắt đầu nhưng chưa kết thúc trong ranh giới workflow đã thống nhất.

Nhóm có thể dùng Kanban để:

- Trực quan hóa các hàng đợi và trạng thái **blocked**.
- Đặt **giới hạn WIP** ở các bước cần thiết và toàn luồng.
- Sử dụng chính sách **pull**: chỉ kéo việc mới khi có năng lực phù hợp.
- Ưu tiên giúp việc **gần hoàn thành** đến Done trước khi mở việc mới.
- Theo dõi tuổi hạng mục để thấy việc cũ bị bỏ quên.

### Little's Law giúp suy nghĩ về WIP và thời gian

Trong một hệ thống dòng công việc **ổn định** với ranh giới và cách đo nhất quán, định luật Little cho quan hệ trung bình:

\[
\text{WIP trung bình} =
\text{Throughput trung bình} \times \text{Cycle time trung bình}.
\]

Suy ra:

\[
\text{Cycle time trung bình} =
\frac{\text{WIP trung bình}}{\text{Throughput trung bình}}.
\]

**Ví dụ minh họa:** Nếu trung bình có **12 hạng mục đang thực hiện** và hoàn tất **3 hạng mục/tuần**, quan hệ trên cho cycle time trung bình khoảng **4 tuần**. Nếu nhóm quản lý WIP còn **6** trong khi **thông lượng vẫn duy trì 3 hạng mục/tuần**, cycle time trung bình tương ứng khoảng **2 tuần**.

Đây là **quan hệ có điều kiện**, không phải lời hứa: chỉ giảm WIP từ 12 xuống 6 **không tự bảo đảm throughput giữ nguyên**. Nếu giảm bằng cách để nhân sự hoặc thiết bị nút thắt thiếu việc, thông lượng có thể giảm. Nếu loại các thẻ blocked ra khỏi bảng chỉ để đẹp số liệu, phép tính cũng mất ý nghĩa.

### Điều kiện quan trọng khi áp dụng

- Hệ thống được quan sát đủ lâu ở trạng thái tương đối ổn định, không có xu hướng tồn đọng tăng vô hạn.
- **WIP, throughput và cycle time** dùng cùng ranh giới, loại đơn vị công việc và kỳ đo tương thích.
- Hạng mục bị bỏ, tách hoặc gộp được xử lý nhất quán trong dữ liệu.
- Thời gian và số lượng phản ánh **hạng mục thực sự hoàn thành**, không phải số ticket được đổi trạng thái vì mục đích báo cáo.

Định luật Little **không giải thích nguyên nhân**, phân phối độ trễ hay xác suất hoàn thành từng hạng mục. Cần xem thêm hàng đợi, độ biến động, công việc bị chặn và phân phối cycle time.

## 9. Lô nhỏ đi cùng chính sách pull và quản lý nút thắt

Nếu kiểm thử chỉ xử lý được hai lát cắt trong một kỳ nhưng phát triển đẩy tới sáu lát cắt, hàng đợi kiểm thử sẽ tăng. Thay vì yêu cầu mọi Developer cứ tiếp tục lập trình tính năng mới, đội có thể:

1. Làm rõ **năng lực và điều kiện nhận việc** ở bước kiểm thử.
2. Chia lát cắt đủ nhỏ để có thể **kiểm thử tích hợp sớm**.
3. Giới hạn số hạng mục đang phát triển và chờ kiểm thử.
4. Hỗ trợ nhóm kiểm thử bằng dữ liệu mẫu, kiểm thử tự động, sửa lỗi nhanh hoặc làm việc cặp phù hợp.
5. Theo dõi thời gian chờ và chất lượng sau thay đổi.

~~~mermaid
flowchart LR
    A["Backlog ưu tiên"] --> B["Sẵn sàng"]
    B --> C["Phát triển WIP giới hạn"]
    C --> D["Chờ kiểm thử"]
    D --> E["Kiểm thử và tích hợp"]
    E --> F["Done / bàn giao"]
    G["Pull theo năng lực bước sau"] -.-> C
    G -.-> E
~~~

Trong Lean, tối ưu **mỗi người bận 100%** không nhất thiết tối ưu **thời gian để một hạng mục đi hết hệ thống**. Một Developer giúp hoàn thiện kiểm thử của story đang chờ có thể đem lại giá trị sớm hơn so với việc bắt đầu story mới.

### Khi nút thắt nằm ngoài nhóm

Nếu hàng đợi kéo dài vì phải chờ môi trường, bảo mật, quyết định nghiệp vụ hoặc một API từ đối tác, nhóm cần **hợp tác với người có thẩm quyền để giảm rào cản**. Chỉ chuyển thẻ sang cột khác hoặc cắt nhỏ story sẽ không tự giải quyết phụ thuộc ấy.

## 10. Tích hợp và kiểm thử theo lô nhỏ để phản hồi kỹ thuật sớm

Trong phát triển phần mềm, một **lô thay đổi mã lớn** thường khó review, khó kiểm thử, khó xác định nguyên nhân lỗi và khó khôi phục hơn. Các thực hành kỹ thuật hỗ trợ Lean gồm:

### 10.1. Continuous Integration

**Tích hợp liên tục (CI)** khuyến khích tích hợp những thay đổi nhỏ thường xuyên vào nhánh chung theo quy trình nhóm, chạy build và kiểm tra tự động để phát hiện lỗi nhanh. Một PR chứa thay đổi của nhiều tuần thường tạo khoảng cách lớn giữa **lúc phát sinh lỗi** và **lúc phát hiện lỗi**.

Ví dụ quy trình:

~~~text
Chọn lát cắt nhỏ -> Thực hiện thay đổi nhỏ
       -> Kiểm thử cục bộ -> Review phù hợp
       -> Tích hợp vào nhánh chung
       -> Build + kiểm thử tự động
       -> Phản hồi nhanh nếu có lỗi
       -> Hoàn thiện lát cắt theo Definition of Done
~~~

Chạy CI không có nghĩa mọi thay đổi đều được phép phát hành ngay. **Tích hợp mã, triển khai và bật tính năng cho người dùng là các quyết định khác nhau.**

### 10.2. TDD và kiểm thử theo ví dụ

**Test-Driven Development (TDD)** và kiểm thử dựa trên các ví dụ nghiệp vụ giúp nhóm kiểm chứng hành vi khi thay đổi còn nhỏ. Nếu một quy tắc “không xác nhận lưu khi chưa ghi được dữ liệu” được biểu diễn thành kiểm thử, việc thay đổi xử lý lưu có tín hiệu lỗi sớm hơn.

Kiểm thử tự động có phạm vi và chất lượng phù hợp giúp giảm **chi phí chuẩn bị kiểm tra mỗi lô**, tạo điều kiện phát hành các lát cắt nhỏ mà vẫn đáng tin cậy. Nó không thay thế kiểm thử khả dụng với người dùng, kiểm soát bảo mật hoặc đánh giá rủi ro cần chuyên môn.

### 10.3. Review các thay đổi có mục đích rõ

Một thay đổi nhỏ, mô tả rõ mục tiêu và tình huống kiểm chứng thường dễ review hơn một thay đổi gồm nhiều vấn đề không liên quan. Nhóm nên:

- Giữ thay đổi đủ nhỏ để người review hiểu ngữ cảnh.
- Tách việc tái cấu trúc không liên quan khi có thể.
- Cung cấp bằng chứng kiểm thử phù hợp.
- Theo dõi tuổi PR đang chờ review và hạng mục blocked.
- Đảm bảo việc chia PR **không tạo trạng thái sản phẩm thiếu an toàn**.

Không nên đo hiệu quả chỉ bằng số PR đóng mỗi ngày. Một PR nhiều dòng đôi khi vẫn là phần thay đổi cần thiết, trong khi nhiều PR nhỏ phụ thuộc chặt chẽ có thể chỉ tạo thêm overhead.

## 11. Triển khai nhỏ và phát hành nhỏ không hoàn toàn giống nhau

**Triển khai (deployment)** là đưa một phiên bản hoặc thay đổi vào môi trường. **Phát hành (release)** là cho người dùng hoặc nhóm người dùng được sử dụng khả năng ấy. Trong một số hệ thống, hai việc diễn ra cùng lúc; trong hệ thống khác, chúng có thể tách rời.

| Kỹ thuật | Cách hỗ trợ lô nhỏ | Giới hạn cần quản lý |
| --- | --- | --- |
| **Tự động hóa pipeline triển khai** | Giảm thời gian và thao tác thủ công lặp lại mỗi lần triển khai | Quyền truy cập, kiểm soát bảo mật và khả năng phục hồi |
| **Feature flag** | Có thể triển khai mã nhưng bật tính năng theo nhóm hoặc điều kiện | Nợ flag, tổ hợp trạng thái khó kiểm thử, quyền điều khiển |
| **Canary / rollout giới hạn** | Quan sát thay đổi với một phạm vi người dùng trước khi mở rộng | Khả năng giám sát, điều kiện dừng, tính đại diện của mẫu |
| **Backward-compatible change** | Hỗ trợ thay đổi API và dữ liệu từng bước | Tương thích trong quá trình chuyển đổi |
| **Rollback / roll-forward plan** | Giảm thời gian phục hồi nếu thay đổi gặp sự cố | Chuyển đổi dữ liệu có thể không đảo ngược đơn giản |
| **Quan sát vận hành** | Phát hiện lỗi hoặc ảnh hưởng ngay sau khi bật thay đổi | Cần đo đúng chỉ số, thiết lập cảnh báo đáng tin |

### Một ví dụ bật tính năng theo phạm vi

Nhóm triển khai mã cho khả năng **tiếp tục bài học từ tiến độ đã lưu**, nhưng chỉ bật cho một nhóm thí điểm được lựa chọn phù hợp, với:

1. Điều kiện chất lượng và bảo mật đạt yêu cầu.
2. Phạm vi tính năng được giới hạn rõ.
3. Tín hiệu quan sát: lỗi lưu, tỷ lệ khôi phục thành công, phản hồi học viên.
4. Điều kiện mở rộng hoặc tạm dừng.
5. Quy trình xử lý nếu kết quả không như mong đợi.

Như vậy, nhóm có thể nhận phản hồi thực tế **trước khi phát hành rộng**, nhưng không được đánh đồng một thử nghiệm nhỏ với bằng chứng đầy đủ về mọi nhóm người dùng.

### Feature flag không thay Definition of Done

Nếu phần tính năng có rủi ro lớn, không nên dùng cờ tắt để bỏ qua kiểm thử thiết yếu rồi tuyên bố hoàn thành. Kỹ thuật cờ giúp **quản lý phạm vi tiếp cận**, không tự chứng minh chất lượng.

## 12. Giảm lô nhưng không bỏ qua kiểm soát an toàn và phụ thuộc

Một số công việc không thể chia tùy ý. Ví dụ:

- Thay đổi schema dữ liệu cần bảo đảm ứng dụng đọc/ghi tương thích qua các phiên bản.
- Hệ thống thanh toán phải xử lý giao dịch nhất quán.
- Tính năng liên quan dữ liệu cá nhân cần quyền truy cập và kiểm soát phù hợp.
- Phát hành trong lĩnh vực có quy định có thể cần bằng chứng và phê duyệt chính thức.
- Một nâng cấp nền tảng đòi hỏi thay đổi theo thứ tự, không thể bật một nửa mà vẫn an toàn.

**Lean không khuyến khích bỏ những kiểm soát bắt buộc**, mà khuyến khích hỏi liệu có thể thực hiện chúng **sớm, thường xuyên và tiết kiệm hơn** mà vẫn bảo vệ hệ thống.

### Chia nhỏ theo hướng tương thích

Ví dụ thay đổi cấu trúc tiến độ học:

1. **Mở rộng (expand):** Bổ sung cấu trúc mới tương thích, giữ luồng cũ hoạt động.
2. **Chuyển đổi từng phần:** Ứng dụng đọc/ghi phù hợp, kiểm chứng dữ liệu, triển khai cho nhóm thí điểm khi an toàn.
3. **Theo dõi:** Kiểm tra lỗi, chênh lệch và các trường hợp ngoại lệ.
4. **Thu hẹp (contract):** Chỉ loại bỏ cấu trúc cũ khi các thành phần phụ thuộc đã chuyển thành công và có kế hoạch dự phòng.

Trình tự là **một mẫu kỹ thuật gợi ý**, cần thiết kế cụ thể theo hệ thống. Nó cho thấy đôi khi phải **đầu tư vào tương thích và kiểm soát** mới có khả năng phát hành những lô nhỏ đáng tin cậy về sau.

### Không nhầm “ít bước” với “ít lãng phí”

Một bước kiểm thử quan trọng có thể ngăn nhiều ngày sửa lỗi và tránh mất dữ liệu. Ngược lại, việc chờ chữ ký qua nhiều tầng mà không thêm bằng chứng hoặc giảm rủi ro có thể là ứng viên cải tiến. Phải đánh giá **giá trị của hoạt động**, không chỉ tên gọi hoặc thời lượng của nó.

## 13. Lean và các loại lãng phí trong dòng giá trị phần mềm

Lean khuyến khích nhận biết những hoạt động sử dụng nguồn lực nhưng **không đóng góp tương xứng vào giá trị hoặc bảo vệ giá trị**. Trong phát triển phần mềm, có thể quan sát:

| Dạng lãng phí / tổn thất | Ví dụ | Cách liên hệ với kích thước lô |
| --- | --- | --- |
| **Chờ đợi** | PR đợi review, yêu cầu đợi quyết định | Lô lớn và WIP cao có thể tăng thời gian xếp hàng |
| **Công việc dở dang / tồn kho** | Nhiều story 80% chưa đạt DoD | Bắt đầu quá nhiều phần cùng lúc khiến giá trị đến muộn |
| **Làm lại** | Đổi giải pháp sau khi người dùng thử muộn | Lô nhỏ giúp kiểm chứng giả định trước khi mở rộng đầu tư |
| **Chuyển giao và chuyển ngữ cảnh** | Công việc đi qua nhiều bộ phận, thiếu ngữ cảnh | Lát cắt dọc và phối hợp liên chức năng giảm một số lần chờ |
| **Chức năng không tạo giá trị** | Xây toàn bộ hệ thống đề xuất phức tạp trước khi xác nhận nhu cầu | Giảm phạm vi ban đầu để học xem điều gì đáng làm |
| **Lỗi và sửa lỗi** | Nhiều thay đổi tích hợp cùng lúc tạo xung đột | Tích hợp/kiểm thử nhỏ và sớm làm lỗi dễ phát hiện hơn |
| **Quy trình thừa không giảm rủi ro** | Nhiều lần nhập lại cùng dữ liệu để xin duyệt | Tối ưu thông tin và kiểm soát theo mục đích, không chỉ cắt thời gian |

Không nên coi mọi **tài liệu, review hoặc chuẩn hóa** là lãng phí. Có loại công việc không tạo giá trị trực tiếp nhưng **bắt buộc để hệ thống an toàn, tin cậy và duy trì được**.

### Điểm quan trọng: tối ưu toàn hệ thống

Nếu bộ phận phát triển tăng tốc viết mã 30% nhưng kiểm thử vẫn là nút thắt, tổng thời gian bàn giao có thể không giảm. Hàng đợi kiểm thử thậm chí tăng. Lean khuyến khích nhìn **dòng giá trị end-to-end** thay vì thưởng cho từng bộ phận chỉ vì họ đã xử lý nhiều ticket hơn.

## 14. Chi phí chuyển lô và lựa chọn kích thước phù hợp

Giảm lô có lợi cho phản hồi và thời gian tới giá trị, nhưng mỗi lần chuyển giao hoặc phát hành có thể có **chi phí cố định**:

- Chuẩn bị môi trường và dữ liệu kiểm thử.
- Review, phối hợp vận hành và thông báo thay đổi.
- Kiểm soát phát hành bắt buộc.
- Giám sát sau khi bật tính năng.
- Giao tiếp với stakeholder và người dùng.

Nếu chia 100 thay đổi thành 100 đợt nhưng mỗi đợt cần một ngày thao tác thủ công, tổng overhead có thể không chấp nhận được. Ngược lại, nếu tự động hóa giúp mỗi lần triển khai chỉ cần thao tác nhỏ và kiểm soát phù hợp, lô nhỏ trở nên khả thi hơn.

### Một cách nhìn về đánh đổi kinh tế

Có thể suy nghĩ đơn giản:

\[
\text{Tổng chi phí liên quan đến lô}
\approx
\text{chi phí thiết lập/chuyển lô}
+\text{chi phí chờ}
+\text{chi phí rủi ro và làm lại}.
\]

Đây là **mô hình tư duy**, không phải công thức định lượng luôn áp dụng được. Khi **giảm kích thước lô**, số lần thiết lập có thể tăng nhưng thời gian chờ và phạm vi rủi ro có thể giảm. **Kích thước lô hợp lý** là mức mang lại **giá trị và phản hồi sớm** mà vẫn duy trì chất lượng, an toàn và chi phí vận hành phù hợp.

### Khi nào không nên ép lô nhỏ hơn nữa?

- Mảnh công việc không tạo được một hành vi có ý nghĩa để kiểm chứng.
- Tách ra làm tăng phụ thuộc giữa các mảnh đến mức khó tích hợp.
- Chi phí phê duyệt hoặc triển khai riêng vượt xa lợi ích phản hồi, trong khi chưa có cách giảm overhead an toàn.
- Một giao dịch nghiệp vụ hoặc thay đổi dữ liệu cần điều kiện nhất quán chung.
- Nhóm thiếu công cụ quan sát hoặc phục hồi nên chưa thể triển khai thay đổi nhỏ thường xuyên một cách an toàn.

Khi gặp những ràng buộc này, câu hỏi Lean là **“rào cản nào cần cải tiến để lô nhỏ hơn khả thi?”**, không phải “cứ chia nhỏ bằng mọi giá”.

## 15. Rút ngắn time to value và time to feedback bằng cách nào?

Các nhóm thường sử dụng nhiều khái niệm thời gian:

| Khái niệm | Một cách định nghĩa hợp lý | Cần làm rõ |
| --- | --- | --- |
| **Cycle time** | Từ lúc bắt đầu xử lý một hạng mục đến lúc kết thúc workflow được định nghĩa | Mốc bắt đầu/kết thúc, ngày lịch hay ngày làm việc |
| **Lead time** | Từ lúc yêu cầu được tiếp nhận hoặc cam kết theo chính sách đến khi được bàn giao | Mỗi tổ chức có thể chọn mốc đầu khác nhau |
| **Time to feedback** | Từ lúc một giả định được đưa ra kiểm chứng đến khi có bằng chứng dùng được | Phản hồi từ kiểm thử kỹ thuật khác phản hồi về giá trị người dùng |
| **Time to value** | Từ mốc nhu cầu/cơ hội được xác định đến khi người dùng nhận kết quả có ích | Phải xác định “giá trị” và nhóm người dùng |
| **Deployment lead time** | Từ mốc thay đổi mã theo quy ước đến khi triển khai vào môi trường đích | Không đồng nghĩa người dùng đã dùng hay có outcome |

Không có một mốc mặc định áp dụng cho mọi đội. Điều cần là **định nghĩa nhất quán để so sánh theo thời gian và tránh nhầm output với outcome**.

### Chỉ số để kiểm chứng cải tiến lô nhỏ

| Chỉ số / tín hiệu | Câu hỏi | Cảnh báo khi diễn giải |
| --- | --- | --- |
| **Throughput** | Có bao nhiêu hạng mục hoàn thành trong một khoảng? | Có thể tăng vì chia ticket nhỏ hơn; cần giữ đơn vị đo nhất quán |
| **WIP và Work Item Age** | Có quá nhiều việc dở hoặc tồn đọng lâu không? | Không ẩn thẻ blocked để làm đẹp bảng |
| **Phân phối cycle time** | Thời gian đi hết workflow có bớt kéo dài và biến động không? | Không chỉ xem trung bình, cần nhìn những hạng mục chậm |
| **Thời gian chờ theo bước** | Đang mất thời gian ở review, test, nghiệp vụ hay phát hành? | Chú ý các bước có thể chồng lấn |
| **Tần suất tích hợp/phát hành** | Có giảm kích thước lô kỹ thuật và cơ hội phản hồi không? | Nhiều lần phát hành không tự chứng minh chất lượng |
| **Lỗi sau thay đổi / thời gian phục hồi** | Lô nhỏ có đi cùng rủi ro vận hành có thể kiểm soát không? | Không hy sinh chất lượng để tăng tốc |
| **Outcome người dùng** | Khả năng hoàn thành nhiệm vụ có cải thiện không? | Cần mẫu, thời gian và bối cảnh đáng tin |

### Không dùng kết quả một Sprint để kết luận chắc chắn

Một lần triển khai nhỏ thành công là tín hiệu tích cực, nhưng chưa chứng minh phương pháp phù hợp cho mọi tình huống. Nên xem **nhiều vòng lặp**, ghi rõ thay đổi ở quy trình, độ phức tạp hạng mục và điều kiện vận hành trước khi kết luận.

## 16. Tình huống xuyên suốt: giảm lô cho nền tảng học trực tuyến

**Bối cảnh giả định:** Một nhóm phát triển sản phẩm học trực tuyến đang xây khả năng lưu, khôi phục và đồng bộ tiến độ. Người học phàn nàn phải học lại khi kết nối mạng chập chờn. Nhóm hiện tập hợp mọi khả năng vào một đợt phát hành lớn.

### Trạng thái ban đầu

| Quan sát | Tác động |
| --- | --- |
| Một epic gồm giao diện, lưu tiến độ, offline, đồng bộ đa thiết bị và thông báo | Không có phần nhỏ để người dùng thử sớm |
| Nhánh tính năng tồn tại nhiều tuần | Lỗi tích hợp và xung đột thay đổi được phát hiện muộn |
| Review và kiểm thử chỉ được lên lịch cuối đợt | Hàng đợi lớn, phản hồi kỹ thuật chậm |
| Môi trường kiểm thử dùng chung và phải chờ cấp quyền | Công việc bị chặn kể cả khi đã viết mã xong |
| Không phân biệt “đã gửi yêu cầu lưu” với “đã lưu thành công” | Người học có thể hiểu sai trạng thái dữ liệu |

### Vòng cải tiến thứ nhất — Chọn lát cắt giá trị tối thiểu

Nhóm cùng Product Owner làm rõ vấn đề. Họ ưu tiên khả năng:

> “Khi hệ thống đã xác nhận lưu tiến độ, học viên có thể tải lại bài và tiếp tục đúng vị trí; khi lưu thất bại, giao diện không thông báo thành công sai.”

Hạng mục này đi qua UI, API, dữ liệu và kiểm thử. Chức năng offline, đồng bộ nhiều thiết bị và nhắc học được tách thành những giả thuyết hoặc khả năng riêng để xem xét sau. Ràng buộc chống mất dữ liệu và quyền truy cập vẫn phải được giữ trong lát cắt đầu.

### Vòng cải tiến thứ hai — Giảm lô kỹ thuật

Developers:

1. Chia phần thay đổi thành các bước mã nhỏ có thể tích hợp an toàn.
2. Bổ sung kiểm thử cho lưu thành công, lưu thất bại, tải lại và dữ liệu cũ.
3. Thiết lập kiểm tra tự động phù hợp sau thay đổi.
4. Review sớm, không đợi hoàn thành cả epic.
5. Phối hợp với nhóm môi trường để giảm thời gian chờ kiểm thử tích hợp.

Họ **không** mặc định mỗi commit là một chức năng đã có giá trị: chỉ một lát cắt có hành vi đầu-cuối và đạt điều kiện chất lượng mới đủ để bàn giao.

### Vòng cải tiến thứ ba — Bàn giao nhỏ và nhận phản hồi

Sau khi lát cắt đạt tiêu chuẩn chất lượng, nhóm đưa nó đến phạm vi sử dụng thí điểm theo quy tắc phát hành. Họ kiểm tra:

- Tỷ lệ tải lại đúng vị trí đã được lưu.
- Trường hợp hiển thị sai “đã lưu” khi API thất bại.
- Lỗi ghi đè hoặc mất dữ liệu tiến độ.
- Phản hồi học viên về ý nghĩa của trạng thái “đang lưu”.
- Thời gian từ lúc chọn story đến khi người học dùng được khả năng.

Giả sử người học nói “tôi không biết trạng thái đang đồng bộ có nghĩa là đã an toàn để đóng trang chưa”. Product Owner có thể ưu tiên cải thiện câu chữ và cách hiển thị **trước khi đầu tư vào tính năng nhắc học**. Đây là lợi ích của phản hồi sớm: **thứ tự backlog được điều chỉnh bằng bằng chứng**, không chỉ dựa trên kế hoạch đầu tiên.

### Vòng cải tiến thứ tư — Quan sát dòng công việc

Nhóm nhận thấy dù story nhỏ hơn, các thẻ vẫn chờ kiểm thử lâu. Họ dùng bảng Kanban để phân biệt **Chờ kiểm thử** với **Đang kiểm thử**, đánh dấu những hạng mục **blocked** bởi môi trường, rồi thử thay đổi chính sách kéo việc và phối hợp kiểm thử sớm.

Họ xem lại cycle time, Work Item Age, số blocker, lỗi sau bàn giao và outcome người dùng. Nếu thời gian chuyển giao giảm nhưng lỗi dữ liệu tăng, nhóm phải **dừng hoặc điều chỉnh cách làm**; đó không phải thành công của Lean.

### Tóm tắt các quyết định

| Giai đoạn | Quyết định | Điều học được |
| --- | --- | --- |
| Làm rõ giá trị | Tách lưu/khôi phục trên một thiết bị khỏi offline và nhắc học | Không phải mọi khả năng phải đi cùng một đợt |
| Giảm lô triển khai | Tích hợp và kiểm thử theo thay đổi nhỏ | Lỗi và phụ thuộc có thể phát hiện sớm hơn |
| Bàn giao thí điểm | Cho người học thử khả năng hoàn chỉnh, an toàn | Trạng thái giao diện cần rõ hơn |
| Giảm WIP/hàng chờ | Ưu tiên hoàn tất, tháo gỡ nghẽn kiểm thử | Chia story nhỏ chưa đủ nếu hàng đợi vẫn dài |
| Cải tiến liên tục | Đo chất lượng, thời gian và outcome | Tốc độ có ý nghĩa khi đi cùng giá trị và độ tin cậy |

## 17. Lean bổ trợ Scrum, Kanban và XP như thế nào?

### Scrum: nhịp kiểm tra/thích ứng và Sprint Goal

Scrum Team có thể dùng **Sprint Planning** để chọn một Sprint Goal có giá trị và các Product Backlog Item đủ nhỏ, **Daily Scrum** để kiểm tra tiến độ hoàn tất Increment, **Sprint Review** để xem sản phẩm và nhận phản hồi, **Sprint Retrospective** để cải tiến thời gian chờ và chất lượng.

Scrum không quy định một Sprint chỉ được có một đợt phát hành. **Một Increment đáp ứng Definition of Done có thể được chuyển giao trước Sprint Review**. Chia lát cắt nhỏ giúp nhóm duy trì khả năng nhận phản hồi trong Sprint mà không cần đợi toàn bộ phạm vi hoàn tất.

### Kanban: lộ hàng đợi và giới hạn công việc dở dang

Kanban hỗ trợ trực quan hóa, giới hạn WIP, cơ chế pull, theo dõi Work Item Age, cycle time, throughput và blocked work. Đây là công cụ quan trọng để **ngăn lợi ích của lô nhỏ bị mất vì quá nhiều việc mở đồng thời**.

### XP: giảm chi phí và rủi ro cho mỗi thay đổi

Các thực hành XP như TDD, lập trình cặp, tích hợp liên tục, tái cấu trúc và trao đổi gần với nghiệp vụ giúp **giảm khoảng cách giữa lúc thay đổi và lúc phát hiện vấn đề**. Khi các kiểm tra tin cậy và quy trình tích hợp nhẹ hơn, lô nhỏ thường khả thi hơn về kỹ thuật lẫn kinh tế.

**Điểm chung của ba cách tiếp cận:** Tập trung vào **phần mềm có chất lượng, phản hồi sớm và điều chỉnh dựa trên bằng chứng**, không coi số ticket, story point hay số lần triển khai là mục tiêu tự thân.

## 18. Phản mẫu khi cố giảm lô

| Phản mẫu | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| **Chia story thành database, backend, frontend** | Mỗi phần nhỏ nhưng chưa tạo giá trị và vẫn phải đợi nhau | Tách lát cắt dọc có hành vi kiểm chứng được |
| **Mở nhiều lát cắt nhỏ đồng thời** | WIP và hàng đợi tăng, không có việc hoàn tất | Giới hạn WIP và ưu tiên hoàn thành trước khi bắt đầu |
| **Phát hành nhiều nhưng bỏ kiểm thử** | Lỗi và rủi ro người dùng tăng | Duy trì DoD, tự động hóa và kiểm soát phù hợp |
| **Dùng feature flag để che tính năng chưa an toàn** | Rủi ro khi bật cờ, trạng thái khó theo dõi | Kiểm thử các trạng thái quan trọng, chính sách bật/tắt rõ |
| **Dồn review và kiểm thử về cuối Sprint** | Lô kiểm chứng vẫn lớn, phản hồi muộn | Review và kiểm thử tích hợp theo thay đổi nhỏ |
| **Chỉ tối ưu thời gian code** | Hàng đợi nghiệp vụ, môi trường, test không cải thiện | Lập bản đồ dòng giá trị end-to-end |
| **Đếm commit hoặc PR là giá trị** | Chỉ số đầu ra tăng nhưng người dùng không hưởng lợi | Đo lát cắt sử dụng được và outcome |
| **Giảm WIP bằng cách ẩn việc blocked** | Dữ liệu đẹp giả, công việc cũ vẫn tồn | Giữ ranh giới và chính sách WIP minh bạch |
| **Tự động đẩy việc tới bước sau đang quá tải** | Tồn kho tăng tại nút thắt | Dùng pull và hỗ trợ năng lực bước nghẽn |
| **Ép mỗi thay đổi phải triển khai riêng dù overhead cao** | Chi phí phát hành tăng, thao tác thủ công khó kiểm soát | Đánh giá kinh tế lô và đầu tư giảm chi phí thiết lập |
| **Cắt giảm kiểm soát nghiệp vụ bắt buộc** | Sai dữ liệu, bảo mật hoặc tuân thủ | Giữ tiêu chuẩn; tối ưu thời điểm và cách thực hiện |
| **Không đo hậu quả sau khi giảm lô** | Khó biết cải tiến có thực chất hay không | Theo dõi flow, chất lượng, phản hồi và giá trị |
| **Tin rằng lô nhỏ luôn nhanh hơn tổng thể** | Dự báo sai khi chi phí chuyển lô lớn | So cả thời gian giá trị đầu tiên và thời gian hoàn thành toàn phạm vi |
| **Chỉ dùng dữ liệu một Sprint để kết luận** | Nhầm biến động ngẫu nhiên thành cải tiến | Theo dõi nhiều vòng và ghi rõ bối cảnh |

## 19. Bài thực hành: giảm lô một cách có căn cứ

### Bài 1 — Phân loại các loại lô

Nhóm phát triển một sản phẩm có các tình huống:

1. Chỉ tích hợp mã sau khi nhánh tính năng đã tồn tại bốn tuần.
2. Chờ hoàn thành mọi tính năng của quý mới cho người dùng thử.
3. Gom mười hai PR vào một buổi review cuối tuần.
4. Đẩy tính năng lên production mỗi ngày nhưng chỉ bật cho người dùng một lần mỗi quý.
5. Đợi một cuộc họp phê duyệt nghiệp vụ hằng tháng mới quyết định ngoại lệ quan trọng.

**Nhiệm vụ:** Chỉ rõ đang có **lô phát triển, tích hợp, review, phát hành hay quyết định** ở đâu. Đề xuất **một thay đổi nhỏ có thể thử** cho hai tình huống đáng lo nhất. Với mỗi thay đổi, xác định **rủi ro và chỉ số bảo vệ chất lượng**.

### Bài 2 — Phác họa dòng giá trị

Một story giả định có:

| Bước | Xử lý | Chờ |
| --- | ---: | ---: |
| Làm rõ | 0,5 ngày | 2 ngày |
| Phát triển | 1,5 ngày | 3 ngày |
| Kiểm thử | 0,5 ngày | 2 ngày |
| Triển khai | 0,5 ngày | 2 ngày |

Hãy tính:

1. Tổng **thời gian xử lý**.
2. Tổng **thời gian chờ**.
3. Tổng **thời gian dòng công việc** trong giả định tuần tự.
4. **Flow efficiency**.
5. Nếu chỉ cải tiến tốc độ viết mã, nút thắt nào vẫn còn?

**Đáp án tham khảo:** 3 ngày xử lý, 9 ngày chờ, 12 ngày tổng, flow efficiency 25%. Đừng tự cộng lại khoảng thời gian bị chặn nếu nó đã nằm trong thời gian chờ.

### Bài 3 — So sánh lô lớn và nhỏ

Cho bốn lát cắt độc lập; mỗi lát cắt cần 2 ngày phát triển và 1 ngày tích hợp/kiểm chứng. Nếu phát hành chung, thêm 1 ngày; nếu phát hành từng phần, mỗi lần thêm 0,5 ngày. Giả sử thực hiện tuần tự, không bị gián đoạn.

1. Khi nào người dùng nhận lát cắt đầu trong phương án phát hành một lần?
2. Khi nào người dùng nhận lát cắt đầu trong phương án phát hành bốn lần?
3. Khi nào cả bốn lát cắt hoàn tất ở mỗi phương án?
4. Vì sao phương án lô nhỏ có thể giúp học hỏi sớm dù hoàn thành toàn bộ gói muộn hơn?
5. Tự động hóa hoạt động phát hành có thể thay đổi đánh đổi này thế nào?

**Đáp án tham khảo:** Lô lớn: giá trị đầu tiên và toàn bộ ở ngày 13. Lô nhỏ: giá trị đầu tiên ngày 3,5; toàn bộ ngày 14. Nếu người dùng phát hiện một giả định sai sớm, nhóm có thể điều chỉnh các lát cắt tiếp theo.

### Bài 4 — Áp dụng Little's Law một cách cẩn trọng

Giả sử WIP trung bình là 12 hạng mục và throughput trung bình là 3 hạng mục/tuần trong một hệ thống ổn định.

1. Tính cycle time trung bình theo quan hệ Little.
2. Nếu WIP trung bình còn 6 và throughput **vẫn giữ** 3, cycle time trung bình tương ứng là bao nhiêu?
3. Vì sao không thể bảo đảm chỉ đặt WIP limit = 6 sẽ khiến mọi story xong sau hai tuần?
4. Nếu một đội đổi cách chia story hoặc loại blocked khỏi WIP, kết quả đo bị ảnh hưởng ra sao?

**Đáp án tham khảo:** 4 tuần và 2 tuần tương ứng. Quan hệ dựa trên **các đại lượng trung bình của cùng hệ thống**, không dự báo chắc chắn cho từng story hoặc bảo đảm thông lượng giữ nguyên.

### Bài 5 — Thiết kế một lát cắt có giá trị

**Epic:** “Học viên có thể học và đồng bộ tiến độ ở mọi nơi, trên mọi thiết bị, kể cả không có mạng.”

Hãy:

- Viết một **user story** cho khả năng nhỏ đầu tiên mang giá trị.
- Nêu ba **tiêu chí chấp nhận**, gồm ít nhất một tình huống lỗi.
- Chỉ rõ điều **chưa bao gồm** trong lát cắt.
- Liệt kê những kiểm soát **không thể trì hoãn** vì chất lượng hoặc bảo vệ dữ liệu.
- Chọn cách nhận phản hồi từ người dùng và phần mềm sau khi bàn giao.

**Gợi ý:** Khởi đầu bằng lưu/khôi phục tiến độ trên một thiết bị có kết nối, với thông báo đúng khi lưu thất bại, có thể hợp lý hơn triển khai offline toàn diện ngay. Nhưng lựa chọn cuối cùng phải dựa trên vấn đề thực tế và rủi ro.

### Bài 6 — Chọn một thử nghiệm cải tiến hai Sprint

Nhóm có hàng đợi review và kiểm thử ngày càng dài. Hãy thiết kế thử nghiệm:

~~~text
Vấn đề:
  Lát cắt đã phát triển xong nhưng chờ review/test quá lâu.

Giả thuyết:
  Nếu nhóm giảm số hạng mục mở đồng thời, review thay đổi nhỏ
  và kiểm thử tích hợp sớm, thời gian tới một Increment đạt DoD sẽ giảm.

Thay đổi thử:
  Giới hạn WIP theo năng lực thật;
  ưu tiên thẻ gần Done và blocked;
  chuẩn bị ví dụ kiểm thử trước khi gửi review.

Đo lường:
  Queue age, cycle time, throughput, lỗi tích hợp,
  lỗi sau bàn giao, phản hồi người dùng.

Điểm xem lại:
  Cuối mỗi Sprint và sau đủ dữ liệu để đánh giá xu hướng.
~~~

**Yêu cầu thêm:** Nêu điều kiện phải **dừng, điều chỉnh hoặc mở rộng** thử nghiệm. Ví dụ nếu cycle time giảm nhưng lỗi dữ liệu tăng, không được coi là cải tiến thành công.

## 20. Checklist giảm lô mà vẫn bảo vệ giá trị

- [ ] Đã nêu **người dùng, vấn đề và kết quả mong muốn**, không chỉ liệt kê việc kỹ thuật.
- [ ] Đã xác định **lô nào đang lớn**: phạm vi, tích hợp, review, kiểm thử, triển khai, phát hành hay quyết định.
- [ ] Lát cắt đầu tiên **có thể dùng hoặc kiểm chứng ý nghĩa**, không chỉ là một lớp kỹ thuật tách rời.
- [ ] Những ràng buộc **chất lượng, bảo mật và dữ liệu** bắt buộc vẫn được thực hiện.
- [ ] Nhóm đã vẽ hoặc mô tả **workflow end-to-end**, gồm hàng đợi và công việc bị chặn.
- [ ] Có dữ liệu **thời gian xử lý và thời gian chờ** thay vì chỉ ước lượng cảm giác.
- [ ] Đã xem xét **WIP và năng lực của bước nút thắt**, không mở vô hạn nhiều story nhỏ.
- [ ] Có chính sách **pull và ưu tiên hoàn tất** trước khi kéo việc mới.
- [ ] Các thay đổi mã có thể **tích hợp, review và kiểm thử sớm** ở quy mô phù hợp.
- [ ] Chi phí triển khai/phát hành lặp lại đã được đánh giá và giảm bằng tự động hóa khi hợp lý.
- [ ] Phát hành theo phạm vi nhỏ có **quan sát, điều kiện dừng và kế hoạch phục hồi** phù hợp.
- [ ] Định nghĩa **Done, cycle time, lead time và time to value** được dùng nhất quán.
- [ ] Đo cả **chất lượng và outcome người dùng**, không chỉ commit, PR hoặc số lần phát hành.
- [ ] Dự báo và kết luận cải tiến nêu rõ **giả định, dữ liệu và giới hạn**.
- [ ] Phản hồi mới được dùng để **điều chỉnh Product Backlog và cách làm**, thay vì duy trì kế hoạch lớn bất biến.

## 21. Câu hỏi ôn tập

1. Vì sao việc mọi thành viên đều bận không chứng minh dòng giá trị đang hiệu quả?
2. Kích thước lô có thể xuất hiện ở những bước nào ngoài phát triển mã?
3. Một user story nhỏ khác thế nào với một task kỹ thuật nhỏ?
4. Vì sao lô lớn có thể làm tăng thời gian chờ, lỗi tích hợp và chi phí làm lại?
5. Value Stream Mapping giúp phát hiện điều gì mà báo cáo “phát triển 90%” không nói được?
6. Flow efficiency 25% có nghĩa mỗi thành viên chỉ làm việc 25% thời gian không? Vì sao?
7. Trong ví dụ bốn lát cắt, vì sao lô nhỏ đem lại giá trị đầu tiên sớm nhưng tổng gói lại hoàn tất muộn hơn?
8. Thế nào là một vertical slice có giá trị và có thể kiểm chứng?
9. Vì sao giảm lô phải kết hợp giới hạn WIP và cơ chế pull?
10. Nêu định luật Little, những điều kiện cần cẩn trọng và ý nghĩa của nó trong dự báo cycle time.
11. Tích hợp liên tục và TDD hỗ trợ giảm kích thước lô bằng cơ chế nào?
12. Deployment, release và outcome người dùng khác nhau thế nào?
13. Feature flag có cho phép bỏ qua Definition of Done không? Vì sao?
14. Những trường hợp nào làm chi phí chuyển lô trở nên đáng kể hoặc buộc phải giữ tính nhất quán chung?
15. Làm sao chứng minh việc giảm lô thực sự giúp người dùng thay vì chỉ làm tăng số ticket hoặc số lần phát hành?
16. Khi một bước kiểm thử là nút thắt, vì sao chỉ tăng tốc viết mã có thể khiến tình hình xấu hơn?

**Ghi nhớ:** Trong Lean, **lô nhỏ là phương tiện để dòng giá trị chảy nhanh và tạo cơ hội học hỏi**, không phải mục tiêu tăng số task hoặc số lần triển khai. Chia thành **lát cắt dọc có ích**, kiểm soát WIP, làm rõ hàng đợi, tích hợp và kiểm thử sớm, giảm chi phí chuyển lô và bàn giao an toàn giúp nhóm đưa giá trị tới người dùng sớm hơn. Hãy đánh giá bằng **thời gian tới giá trị, phản hồi, chất lượng và kết quả sử dụng**, đồng thời chấp nhận rằng kích thước lô phù hợp là một **đánh đổi thực nghiệm** cần đo và điều chỉnh theo bối cảnh.
