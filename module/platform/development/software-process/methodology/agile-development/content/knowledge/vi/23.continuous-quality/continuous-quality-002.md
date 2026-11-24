# Xác định chất lượng cần đạt từ nhu cầu và mức độ rủi ro

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **chất lượng cần đạt** phải xuất phát từ nhu cầu người dùng, mục tiêu sản phẩm, nghĩa vụ và rủi ro thực tế, thay vì chỉ từ một danh sách kiểm thử mặc định.
2. Phân biệt **chất lượng chức năng**, các thuộc tính chất lượng phi chức năng, **tiêu chí chấp nhận**, **Definition of Done**, chỉ báo/mục tiêu mức dịch vụ và điều kiện phát hành.
3. Xác định các **kịch bản rủi ro** gồm nguyên nhân, sự kiện không mong muốn, ảnh hưởng, khả năng xảy ra, bằng chứng và điều chưa biết; ưu tiên xử lý có lý do.
4. Chuyển nhu cầu mơ hồ như “nhanh”, “an toàn”, “ổn định”, “dễ dùng” thành **điều kiện kiểm chứng được** với phạm vi, ngưỡng, môi trường, dữ liệu và phương pháp đo.
5. Thiết kế chiến lược kiểm thử và bằng chứng chất lượng **theo mức độ rủi ro**, đồng thời giữ nguyên các yêu cầu bảo mật, pháp lý, dữ liệu và chất lượng bắt buộc.
6. Phối hợp Product Owner, Developers, tester, vận hành và các bên liên quan để ra quyết định **làm tiếp, giới hạn phạm vi, thử nghiệm có kiểm soát hoặc chưa phát hành**.

## 1. Chất lượng là mức phù hợp với mục đích, không chỉ là “ít lỗi”

Một sản phẩm có thể vượt toàn bộ unit test nhưng vẫn không phục vụ được người dùng: nút quá khó tìm, phản hồi quá chậm, dữ liệu sai tài khoản hoặc dịch vụ không hoạt động khi nhu cầu cao. Ngược lại, một sản phẩm được quảng bá “chất lượng cao nhất” nhưng mất quá lâu để triển khai những việc không cần thiết cũng có thể đánh mất cơ hội tạo giá trị.

Trong phát triển Agile, chất lượng cần được hiểu bằng **kết quả mà sản phẩm phải cung cấp** và **rủi ro phải kiểm soát** ở thời điểm giao:

- **Đúng nhu cầu:** Người dùng giải quyết được vấn đề thật, không chỉ nhận một chức năng đã được viết code.
- **Đúng hành vi:** Kết quả nghiệp vụ và các tình huống ngoại lệ quan trọng hoạt động như đã thống nhất.
- **Đủ an toàn:** Không gây nguy cơ không thể chấp nhận đối với quyền truy cập, dữ liệu, giao dịch hay nghĩa vụ bắt buộc.
- **Đủ tin cậy và khả dụng:** Người dùng có thể thực hiện công việc trong điều kiện sử dụng được xác nhận.
- **Có thể vận hành và thay đổi:** Đội có thể quan sát lỗi, xử lý sự cố, bảo trì và thích nghi khi học được điều mới.

> **Nguyên tắc cốt lõi:** Không hỏi “Cần chất lượng bao nhiêu là đủ?” một cách tách rời. Hãy hỏi **“Ai cần điều gì, điều gì có thể gây hại nếu sai, và bằng chứng nào cho thấy mức chất lượng đã đáp ứng?”**

### Ví dụ mở đầu

Một nền tảng học trực tuyến có chức năng **“Tiếp tục học”**. Người học muốn mở lại bài gần nhất, đội kinh doanh muốn tăng tỷ lệ quay lại học, còn đội vận hành muốn tránh lỗi mất tiến độ.

Nếu chỉ ghi “Tính năng chạy tốt” thì các bên có thể hiểu khác nhau:

- Người học: bấm nút là mở **đúng bài** mà không phải tìm kiếm.
- Bộ phận hỗ trợ: khi không có tiến độ, hệ thống phải **nói rõ**, không trả thông báo gây hiểu lầm.
- Đội kỹ thuật: dữ liệu phải thuộc **đúng tài khoản**, quyền truy cập được kiểm tra phía dịch vụ và request lỗi không gây mất dữ liệu.
- Vận hành: có tín hiệu để phát hiện lỗi đọc/ghi tiến độ và hỗ trợ người bị ảnh hưởng.

Chất lượng cần đạt phải bao gồm những điều kiện phù hợp với **từng nhu cầu và tác động rủi ro**, không chỉ một tuyên bố chung.

## 2. Chất lượng liên tục không phải kiểm thử dồn vào cuối

**Chất lượng liên tục (continuous quality)** là cách cả nhóm xây dựng, kiểm chứng và quan sát chất lượng **trong suốt quá trình** hiểu yêu cầu, thiết kế, phát triển, tích hợp, phát hành và vận hành.

Điều này gắn với các giá trị Agile:

- **Cộng tác** để làm rõ nhu cầu và ví dụ trước khi viết quá nhiều.
- **Giao phần mềm tăng dần** nhưng mỗi phần phải dùng được và đạt tiêu chuẩn chất lượng.
- **Phản hồi sớm** qua test, review, môi trường tích hợp và người dùng.
- **Thích nghi** chất lượng cần kiểm tra khi xuất hiện rủi ro hoặc kiến thức mới.
- **Cải tiến liên tục** hệ thống giao hàng thay vì chỉ tăng số kiểm thử.

### Vòng phản hồi chất lượng

~~~mermaid
flowchart TD
    N["Nhu cầu người dùng + mục tiêu sản phẩm"] --> R["Nhận diện rủi ro và ràng buộc"]
    R --> Q["Diễn đạt tiêu chí chất lượng kiểm chứng được"]
    Q --> P["Chọn thiết kế + chiến lược kiểm tra phù hợp"]
    P --> T["Xây Increment và thu bằng chứng"]
    T --> G{"Đạt chất lượng và điều kiện sử dụng?"}
    G -- "Chưa" --> A["Sửa lỗi, giảm phạm vi an toàn hoặc làm rõ yêu cầu"]
    A --> Q
    G -- "Đạt" --> D["Giao/triển khai theo chính sách"]
    D --> M["Quan sát vận hành và phản hồi"]
    M --> R
~~~

Sơ đồ không có nghĩa mọi thay đổi phải qua cùng một chuỗi phê duyệt thủ công. Các bước có thể diễn ra song song và lặp lại. Một lỗi bảo mật phát hiện trong production cần được phản ứng **ngay**, không chờ đến cuối Sprint hay buổi họp định kỳ.

## 3. Phân biệt các lớp yêu cầu và bằng chứng chất lượng

Những thuật ngữ dưới đây liên quan nhưng **không thể dùng thay nhau**:

| Khái niệm | Câu hỏi trả lời | Ví dụ với “Tiếp tục học” |
| --- | --- | --- |
| **Nhu cầu / outcome** | Người dùng hoặc tổ chức muốn đạt kết quả gì? | Học viên tìm lại bài nhanh và tin rằng tiến độ được lưu đúng. |
| **Yêu cầu chức năng** | Hệ thống phải thực hiện hành vi nào? | Trả bài hợp lệ gần nhất của tài khoản đang đăng nhập. |
| **Thuộc tính chất lượng** | Hành vi cần nhanh, an toàn, ổn định, dễ dùng ở mức nào? | Không đọc được dữ liệu của tài khoản khác; phản hồi đủ nhanh trong điều kiện xác định. |
| **Tiêu chí chấp nhận (Acceptance Criteria)** | Với một backlog item cụ thể, những ví dụ nào xác nhận hành vi mong đợi? | Nếu bài mới nhất đã hết quyền, không mở trái quyền. |
| **Definition of Done (DoD)** | Điều kiện chất lượng chung nào để phần sản phẩm được xem là Increment hoàn thành? | Đã tích hợp, kiểm thử phù hợp đạt, không vi phạm các tiêu chuẩn chung của sản phẩm. |
| **Chỉ báo mức dịch vụ (SLI)** | Đo lường thực tế nào thể hiện chất lượng dịch vụ? | Tỷ lệ yêu cầu đọc tiến độ hợp lệ thành công. |
| **Mục tiêu mức dịch vụ (SLO)** | Mức mong muốn của chỉ báo đó trong phạm vi/khoảng đo nào? | Một ngưỡng tỷ lệ thành công trong kỳ quan sát đã định nghĩa. |
| **Thỏa thuận mức dịch vụ (SLA)** | Có nghĩa vụ dịch vụ được thỏa thuận với bên liên quan không? | Cam kết theo hợp đồng, nếu tổ chức thực sự có. |
| **Điều kiện phát hành (release criteria)** | Có thể đưa phiên bản tới người dùng, trong điều kiện và phạm vi nào? | DoD đạt, migration và khôi phục an toàn, giám sát sẵn sàng, phê duyệt bắt buộc đã có. |

**SLI, SLO và SLA** hữu ích khi sản phẩm cần quản lý mức dịch vụ; **Scrum không bắt buộc mọi backlog item đều có một SLO hoặc SLA riêng**. Không tự bịa ngưỡng hay nghĩa vụ hợp đồng khi chưa có nguồn thẩm quyền.

### Acceptance Criteria và Definition of Done không đồng nhất

Tiêu chí chấp nhận mô tả **hành vi riêng của item**. DoD là **mô tả chung về trạng thái Increment khi đáp ứng những tiêu chuẩn chất lượng của sản phẩm**.

Một story có thể đúng luồng chính nhưng **chưa đạt DoD** nếu thay đổi chưa tích hợp hoặc thiếu kiểm tra bảo mật bắt buộc. Ngược lại, pipeline xanh và tuân thủ DoD không tự chứng minh một chức năng giải quyết **đúng vấn đề người dùng**: còn cần phản hồi và đánh giá outcome.

## 4. Tìm nhu cầu chất lượng từ đúng nguồn thông tin

Muốn xác định mức cần đạt, đội nên lắng nghe **nhiều góc nhìn**:

| Nguồn thông tin | Câu hỏi thực hành | Dấu vết có thể tạo |
| --- | --- | --- |
| **Người dùng cuối** | Khi nào họ cần tính năng? Điều gì khiến họ mất tin tưởng? | Kịch bản sử dụng, phản hồi, mức ưu tiên theo tác động. |
| **Product Owner / bên quản lý sản phẩm** | Product Goal là gì? Lát cắt giá trị nào đáng làm trước? | Kết quả kỳ vọng, Product Backlog, giả thuyết giá trị. |
| **Developers / kiến trúc** | Hệ thống hiện có ràng buộc gì, điểm nào khó thay đổi? | Phụ thuộc, giả định, rủi ro thiết kế và dữ liệu. |
| **Tester / chuyên gia chất lượng** | Hành vi nào có thể sai, làm sao phát hiện sớm? | Ví dụ biên, chiến lược test, vùng thiếu bằng chứng. |
| **Vận hành / hỗ trợ khách hàng** | Khi lỗi xảy ra ai biết, ai chịu tác động, khôi phục ra sao? | Runbook, tín hiệu giám sát, kế hoạch phục hồi. |
| **Bảo mật / pháp chế / tuân thủ khi áp dụng** | Nghĩa vụ và rủi ro nào không thể bỏ qua? | Yêu cầu kiểm soát, đánh giá cần thiết và người có thẩm quyền. |
| **Dữ liệu sản phẩm / sự cố trước đây** | Lỗi nào lặp lại? Người dùng bỏ dở ở đâu? | Bằng chứng, baseline, nhóm nguyên nhân cần điều tra. |
| **Đối tác hoặc hệ thống phụ thuộc** | Hợp đồng API, giới hạn, khả năng thất bại nào đã biết? | Contract test, cơ chế tương thích, retry và timeout phù hợp. |

Không cần mời tất cả mọi người vào mọi cuộc họp. Có thể sử dụng **trao đổi ngắn theo đúng rủi ro**, ghi quyết định cần thiết và làm rõ trách nhiệm giải trình.

### Chuyển phát biểu mơ hồ thành câu hỏi hữu ích

| Phát biểu ban đầu | Điều cần hỏi tiếp |
| --- | --- |
| “Màn hình phải nhanh.” | Người dùng nào, thao tác nào, thiết bị/mạng nào, đo từ đâu đến đâu, ngưỡng nào chấp nhận được? |
| “Phải bảo mật.” | Tài sản cần bảo vệ là gì, ai được quyền làm gì, mối đe dọa và yêu cầu kiểm soát cụ thể nào? |
| “Không được mất dữ liệu.” | Dữ liệu nào, khi mạng lỗi hoặc gửi lại request thì quy tắc ghi/khôi phục là gì? |
| “Sẵn sàng 24/7.” | Phạm vi dịch vụ, lịch hỗ trợ, yêu cầu availability, bảo trì và tình huống mất phụ thuộc ra sao? |
| “Dễ dùng cho mọi người.” | Nhóm người dùng, thiết bị, hỗ trợ tiếp cận và nhiệm vụ nào cần đo? |
| “Có thể mở rộng vô hạn.” | Dung lượng, tải, thời gian tăng trưởng, giới hạn ngân sách và rủi ro đã biết là gì? |

Nhu cầu người dùng quan trọng, nhưng **không đủ để tự xác định tiêu chuẩn an toàn tối thiểu** nếu có nghĩa vụ hoặc rủi ro không thể chấp nhận. Đội phải kết hợp cả hai.

## 5. Các chiều chất lượng cần xem xét theo bối cảnh

Không phải mọi hệ thống cần đầu tư bằng nhau vào mọi thuộc tính. Hãy dùng các nhóm sau như **bản đồ tìm câu hỏi**, không phải checklist bắt buộc để tạo 50 mục tiêu.

| Chiều chất lượng | Tình huống cần quan tâm | Ví dụ bằng chứng |
| --- | --- | --- |
| **Functional suitability / correctness** | Chọn đúng bài học, đúng quy tắc đăng ký, tính toán đúng. | Acceptance test, ví dụ nghiệp vụ, đối soát dữ liệu. |
| **Security / privacy** | Tránh đọc chéo tài khoản, lộ dữ liệu và lạm dụng quyền. | Kiểm thử phân quyền server-side, review thiết kế, kiểm soát truy cập, audit thích hợp. |
| **Reliability / resilience** | Mạng chập chờn, đối tác lỗi, xử lý retry và phục hồi. | Kiểm tra timeout, failure injection phù hợp, khả năng khôi phục. |
| **Performance efficiency** | Phản hồi quá chậm làm người dùng bỏ thao tác. | Phân vị latency theo tải và môi trường đã xác định. |
| **Usability / accessibility** | Người học không tìm thấy nút, không sử dụng được bằng bàn phím. | Usability test, tiêu chí tiếp cận áp dụng, kiểm thử với người dùng phù hợp. |
| **Compatibility / interoperability** | API thay đổi khiến client cũ không hoạt động. | Contract test, test phiên bản và môi trường tích hợp. |
| **Maintainability / testability** | Sửa lỗi chậm, quy tắc trùng lặp hoặc chỉ một người hiểu. | Unit/integration test có ích, code review, khả năng sửa đổi an toàn. |
| **Observability / operability** | Sự cố xảy ra nhưng không biết ai bị ảnh hưởng. | Metric, log không lộ bí mật, trace và diễn tập runbook. |
| **Portability / deployability** | Chuyển môi trường, rollback/migration có rủi ro. | Kiểm tra cấu hình, migration, quy trình triển khai an toàn. |
| **Data integrity / consistency** | Ghi tiến độ bị lặp, sai thứ tự, mất dữ liệu. | Test idempotency, concurrency, đối soát và phục hồi dữ liệu. |

Các nhóm trên có thể giao thoa. **Tính toàn vẹn dữ liệu** đồng thời liên quan correctness, reliability và security. Không nên tạo nhiều tài liệu trùng chỉ vì cùng một rủi ro được đặt dưới ba nhãn.

## 6. Phân tích rủi ro: điều gì có thể xảy ra và ảnh hưởng ra sao?

Một **rủi ro chất lượng** là khả năng một sự kiện hoặc điều kiện không mong muốn xảy ra, gây ảnh hưởng đến người dùng, sản phẩm hoặc tổ chức. Có thể ghi một **kịch bản rủi ro** bằng các yếu tố:

1. **Tài sản hoặc nhu cầu cần bảo vệ:** Ví dụ tiến độ học của mỗi tài khoản.
2. **Nguyên nhân/điều kiện kích hoạt:** Cache không tách theo phiên, hai request ghi gần đồng thời, API đối tác lỗi.
3. **Sự kiện không mong muốn:** Trả sai tiến độ, ghi đè dữ liệu hợp lệ hoặc báo đã lưu khi thực tế chưa lưu.
4. **Tác động:** Lộ thông tin cá nhân, mất công sức học, tăng hỗ trợ, vi phạm nghĩa vụ.
5. **Khả năng xảy ra:** Đánh giá dựa trên dữ liệu, cơ chế và mức bất định; không chỉ cảm giác.
6. **Cách phát hiện và ứng phó:** Test, giám sát, cảnh báo, khôi phục, chặn phát hành hoặc giới hạn rollout.
7. **Rủi ro còn lại:** Sau biện pháp kiểm soát vẫn còn điều gì chưa biết hoặc chưa kiểm chứng?

### Ví dụ bảng rủi ro ban đầu

| ID | Kịch bản rủi ro | Tác động có thể có | Dấu hiệu/bằng chứng cần thu | Hướng kiểm soát ban đầu |
| --- | --- | --- | --- | --- |
| R1 | Tài khoản B đọc tiến độ của A khi đổi phiên đăng nhập | Vi phạm quyền riêng tư và niềm tin | Kiểm thử phân quyền, cache, request đến muộn | Thực thi quyền phía server; test chuyển phiên và truy cập trực tiếp API |
| R2 | Request lưu tiến độ gửi lại làm ghi sai thứ tự | Mất/đảo tiến độ đã học | Test retry, concurrency và quy tắc phiên bản | Xác định idempotency/xung đột theo nghiệp vụ; bảo vệ dữ liệu |
| R3 | Trang chủ tải chậm trên mạng yếu | Người học khó tìm bài, bỏ thao tác | Quan sát trên thiết bị/mạng đại diện, latency phân vị | Tối ưu có đo, fallback rõ và tải dữ liệu phù hợp |
| R4 | API đọc tiến độ không phản hồi | Học viên không thể tiếp tục, hỗ trợ tăng | Tỷ lệ lỗi và timeout, mô phỏng lỗi phụ thuộc | Timeout, thông báo đúng và phục hồi/giám sát |
| R5 | Nút “Tiếp tục học” không điều khiển được bằng bàn phím | Một nhóm người dùng bị loại khỏi luồng | Kiểm thử tiếp cận, thao tác bàn phím, phản hồi người dùng | Điều kiện khả năng truy cập được xác nhận và test |

Đây là **rủi ro giả định trong ví dụ học tập**. Không coi bảng là kết quả kiểm toán hoặc kết luận các lỗi thực sự đã tồn tại trong một hệ thống cụ thể.

## 7. Ưu tiên rủi ro: tác động, khả năng xảy ra và độ bất định

Không phải mọi rủi ro đều cần cùng lượng kiểm thử, nhưng không được “xếp hạng thấp” để lờ đi một **yêu cầu bắt buộc**.

### 7.1. Thang đánh giá định tính minh họa

| Mức | Tác động | Khả năng xảy ra |
| --- | --- | --- |
| **Thấp** | Bất tiện nhỏ, khắc phục dễ, ít người bị ảnh hưởng | Hiếm gặp theo cơ chế và bằng chứng hiện có |
| **Trung bình** | Cản trở một tác vụ quan trọng, cần hỗ trợ/khôi phục | Có điều kiện kích hoạt đã biết nhưng chưa phổ biến |
| **Cao** | Có thể làm lộ dữ liệu, mất dữ liệu, mất khả năng sử dụng hoặc vi phạm nghĩa vụ quan trọng | Có dấu hiệu lặp lại hoặc cơ chế làm lỗi dễ xuất hiện |

Đây không phải thang xác suất thống kê chính xác. Nếu thiếu dữ liệu, hãy ghi **“chưa biết”** thay vì ép một con số chính xác giả tạo.

### 7.2. Ma trận thảo luận ưu tiên

| Khả năng \ Tác động | Thấp | Trung bình | Cao |
| --- | --- | --- | --- |
| **Thấp** | Theo dõi theo phạm vi | Kiểm tra có mục tiêu | Phân tích kỹ và có biện pháp an toàn phù hợp |
| **Trung bình** | Kiểm tra thích hợp | Ưu tiên điều tra/kiểm soát | Ưu tiên cao, bằng chứng mạnh trước phát hành |
| **Cao** | Tăng khả năng phát hiện và giảm lỗi | Ưu tiên cao | Cần kiểm soát/chặn rủi ro không chấp nhận |

**Giới hạn của ma trận:** Từ “cao/trung bình/thấp” là **thứ bậc định tính**; nhân hai con số đại diện không tự tạo ra xác suất, thiệt hại tiền tệ hay thứ tự khách quan. Hai rủi ro cùng ô có thể cần xử lý rất khác nhau.

### 7.3. Ba yếu tố cần bổ sung

- **Khả năng phát hiện:** Lỗi có dễ nhận ra trước khi ảnh hưởng người dùng không, hay chỉ lộ ra sau nhiều tuần?
- **Khả năng khôi phục:** Nếu xảy ra, có thể rollback, đối soát và phục hồi dữ liệu hay không?
- **Mức chắc chắn của đánh giá:** Kịch bản đã tái hiện được hay chỉ là giả định, thiếu telemetry hoặc phụ thuộc đối tác chưa rõ?

Một rủi ro **khả năng xảy ra chưa rõ nhưng tác động không thể khôi phục** có thể cần spike, test hoặc biện pháp phòng ngừa ngay, không được xem nhẹ vì chưa có lỗi trong log.

### 7.4. Phân biệt mức độ nghiêm trọng và thứ tự xử lý

**Severity** mô tả hậu quả nếu lỗi xảy ra. **Priority** mô tả thứ tự xử lý trong bối cảnh rủi ro, nghĩa vụ, người bị ảnh hưởng và khả năng khắc phục. Chúng liên hệ nhưng không đồng nghĩa.

Một lỗi giao diện dễ thấy có thể được xử lý sớm vì ảnh hưởng nhiều người; một lỗ hổng có hậu quả đặc biệt nghiêm trọng có thể phải được chặn phát hành dù chưa tái hiện thường xuyên.

## 8. Từ yêu cầu mơ hồ đến điều kiện chất lượng có thể kiểm chứng

Một mục tiêu chất lượng hữu ích nên nêu đủ:

1. **Đối tượng hoặc luồng** cần bảo vệ.
2. **Điều kiện sử dụng hoặc kịch bản lỗi** cần xét.
3. **Hành vi/kết quả quan sát được**.
4. **Ngưỡng hoặc tiêu chí chấp nhận**, khi có cơ sở để đặt.
5. **Môi trường, dữ liệu và cách đo/kiểm tra**.
6. **Ngoại lệ hoặc ràng buộc bắt buộc**, gồm điều gì khiến không được gọi Done.
7. **Nguồn quyết định và người chịu trách nhiệm** xác nhận mục tiêu.

### Mẫu câu

> **Trong [điều kiện đại diện], khi [người dùng/hệ thống] thực hiện [hành động], [kết quả cần có] và [điều không được xảy ra]. Kiểm chứng bằng [test/dữ liệu/quan sát], trong [phạm vi hoặc môi trường], theo [mục tiêu đã thống nhất].**

Không phải mọi yêu cầu đều phải dùng số. “Không cho tài khoản B đọc dữ liệu riêng của A” là một điều kiện an toàn có thể kiểm thử theo các kịch bản đã xác định, không cần đặt mục tiêu “99,9% yêu cầu không lộ dữ liệu”.

### Chuyển đổi từng ví dụ

| Nói chung chung | Cách diễn đạt kiểm chứng được hơn |
| --- | --- |
| “Mở bài đúng.” | Với tài khoản đã xác thực, chỉ xét bản ghi thuộc tài khoản và khóa còn quyền; nếu không có bản ghi hợp lệ, trả trạng thái rõ, không mở dữ liệu người khác. |
| “Không mất tiến độ.” | Trong các trường hợp retry và mất mạng đã xác định, không xác nhận lưu thành công khi máy chủ chưa chấp nhận; bản ghi đã xác nhận không bị ghi đè trái quy tắc. |
| “Giao diện nhanh.” | Với thiết bị, dataset và profile mạng đã thống nhất, đo thời gian từ thao tác tới hiển thị nội dung có thể sử dụng; đánh giá phân vị latency theo mục tiêu đã phê duyệt. |
| “Chạy ổn định.” | Với một số lỗi phụ thuộc đã chọn, dịch vụ timeout/fallback đúng, không hiển thị dữ liệu sai và ghi tín hiệu để vận hành phát hiện. |
| “Dễ tiếp cận.” | Các thao tác trọng yếu có thể thực hiện bằng bàn phím, trạng thái điều khiển được truyền đạt và thứ tự focus có thể hiểu theo tiêu chuẩn áp dụng. |
| “Dễ bảo trì.” | Một developer khác có thể chạy test, xác định quy tắc và thay đổi một lát cắt có review, không cần hỏi một chuyên gia duy nhất cho bước thông thường. |

Mức **đạt yêu cầu** phải được xác định theo nhu cầu và rủi ro, không áp đặt một ngưỡng quá cụ thể thiếu căn cứ.

## 9. Yêu cầu định lượng: nêu cả cách đo và giới hạn của con số

Những thuộc tính như latency, availability hoặc độ trễ đồng bộ thường cần ngưỡng. Một con số đứng riêng không đủ.

### 9.1. Ví dụ hiệu năng có điều kiện

Thay vì:

> “API trả kết quả dưới 500 ms.”

Đề xuất một bản nháp **cần được xác nhận**:

> “Trong bài đo trên môi trường đại diện, với dữ liệu của quy mô sản phẩm đã thống nhất và tải đọc tiến độ bình thường, **95% yêu cầu hợp lệ** đến API đọc bài gần nhất có thời gian phản hồi từ server không quá **600 ms**, đo trong khoảng thử có đủ mẫu. Các trường hợp lỗi và retry được đo riêng.”

**600 ms và phân vị 95% chỉ là số minh họa**, không phải tiêu chuẩn của Scrum, Agile hay một nền tảng cụ thể. Cần đánh giá từ nhu cầu người dùng, baseline, chi phí tài nguyên và mục tiêu vận hành thực tế.

Còn phải hỏi:

- Đo **server latency** hay **thời gian người dùng nhìn thấy nội dung**, gồm mạng và render?
- Tải có phản ánh giờ cao điểm và phân bố người dùng thực không?
- Dataset có bao gồm tài khoản học nhiều khóa và lịch sử dài không?
- Mức tin cậy, cỡ mẫu và phương pháp tính phân vị là gì?
- Có tách lỗi timeout khỏi phép đo latency thành công không để tránh kết quả đẹp giả?

### 9.2. Ví dụ reliability và availability

Thay vì:

> “Hệ thống phải online 100%.”

Hãy làm rõ dịch vụ nào, khoảng thời gian nào, loại request nào được tính là thành công, phạm vi bảo trì và cách đo. Nếu tổ chức dùng SLO, cần thỏa thuận **SLI, cửa sổ đo và mục tiêu** tương ứng.

Không nên tự suy ra một mức availability chỉ vì “dịch vụ lớn nên phải như vậy”. Một mục tiêu cao hơn có thể yêu cầu kiến trúc dư thừa và chi phí cao; ngược lại, dịch vụ ảnh hưởng dữ liệu quan trọng có thể cần giới hạn rủi ro nghiêm ngặt hơn.

### 9.3. Phân biệt target và bằng chứng

Một ngưỡng được ghi trong tài liệu là **mục tiêu**. Chạy load test trên một máy phát triển chưa đại diện không chứng minh hệ thống đạt mục tiêu ở production. Cần minh bạch **môi trường, tải, cấu hình, cỡ mẫu, công cụ và giới hạn phép đo**.

## 10. Yêu cầu chức năng đúng đắn và tính toàn vẹn dữ liệu

Chất lượng nghiệp vụ thường phụ thuộc vào các quy tắc mà không thể kiểm chứng chỉ bằng màn hình “trông đúng”.

### Bốn lớp quy tắc cho “Tiếp tục học”

1. **Danh tính:** Đọc dữ liệu cho tài khoản đang xác thực, không phải một accountId tự do do client khai báo.
2. **Quyền:** Chỉ cho mở bài mà người dùng còn quyền; có thể cần kiểm tra lại quyền khi thao tác mở xảy ra.
3. **Tính đúng đắn của lựa chọn:** Định nghĩa “gần nhất” theo dữ liệu nào, thời điểm do ai xác nhận, tie-break khi bằng nhau.
4. **Tính toàn vẹn khi ghi:** Request gửi lại hoặc hai thiết bị cập nhật gần nhau phải xử lý theo quy tắc đã xác nhận.

### Các câu hỏi phải xác minh

- Người dùng đang học một bài nhưng chưa đồng bộ: hiển thị **đã lưu** hay **chưa xác nhận**?
- Máy chủ nhận request cũ sau request mới: có được ghi lùi tiến độ không?
- Nếu một bài đã hết quyền, hệ thống chọn bài hợp lệ tiếp theo hay yêu cầu chọn lại?
- Bản ghi có cùng thời điểm lưu: quy tắc ưu tiên có quyết định được không?
- Nếu dịch vụ phụ thuộc lỗi, ứng dụng trả “chưa học bao giờ” hay trạng thái không thể tải?

Đội **không nên tự bịa quy tắc nghiệp vụ** chỉ để test xanh. Phải nêu ví dụ và xác nhận với người có trách nhiệm quyết định.

### Idempotency không đồng nghĩa bỏ qua mọi request trùng

Một thao tác có tính chất **idempotent** khi lặp lại cùng một yêu cầu theo ngữ nghĩa đã xác định không làm thay đổi kết quả ngoài ý muốn. Nhưng cách dùng idempotency key, version check hoặc quy tắc gộp dữ liệu tùy hệ thống.

Ví dụ với lưu tiến độ, cần kiểm tra:

| Kịch bản | Câu hỏi chất lượng |
| --- | --- |
| Client gửi lại request vì timeout | Có tạo tiến độ trùng hoặc thông báo thành công sai không? |
| Laptop và điện thoại cùng cập nhật | Có ghi đè dữ liệu mới bằng dữ liệu cũ không? |
| Request thành công nhưng phản hồi bị mất | Client có thể retry an toàn không? |
| Bài học hoặc khóa học vừa bị thu hồi quyền | Server có còn cho cập nhật trái quyền không? |
| Request có dữ liệu lỗi hoặc thiếu trường | Hệ thống từ chối an toàn và ghi tín hiệu phù hợp không? |

Đây là rủi ro cần giải thích bằng **ví dụ và test**, không nên chỉ ghi khẩu hiệu “không mất dữ liệu”.

## 11. Bảo mật và quyền riêng tư là điều kiện chất lượng không thể “giảm mức”

Khi sản phẩm xử lý thông tin học viên hoặc tổ chức, rủi ro sai quyền truy cập có thể nghiêm trọng dù xác suất theo một vài test là thấp.

### Điều kiện cần xem ngay từ đầu

- **Xác thực:** Nguồn danh tính có thẩm quyền, vòng đời phiên và kiểm soát truy cập phù hợp.
- **Phân quyền:** Không chỉ ẩn nút ở UI; API và dữ liệu phía server phải chặn truy cập trái quyền.
- **Cô lập dữ liệu:** Tránh đọc/ghi chéo tài khoản hoặc tenant.
- **Truyền và lưu dữ liệu:** Bảo vệ dữ liệu theo yêu cầu sản phẩm/tổ chức và nghĩa vụ áp dụng.
- **Log và telemetry:** Không ghi token, bí mật hoặc dữ liệu cá nhân quá mức vào log.
- **Lạm dụng và lỗi:** Thử request tùy chỉnh, session hết hạn, request đến muộn, replay và dữ liệu bất thường theo rủi ro.
- **Thay đổi quyền:** Khi quyền học bị thu hồi hoặc tài khoản đổi, cache/phiên có thể trả dữ liệu cũ không?

### “Không có lỗi bảo mật trong kiểm thử” chưa phải bằng chứng tuyệt đối

Một bộ test chỉ bao phủ các đường đi đã nghĩ đến. Đội cần **threat modeling phù hợp, review độc lập khi rủi ro cao, kiểm thử ở ranh giới có thẩm quyền và giám sát**. Nếu có nghĩa vụ đánh giá hoặc phê duyệt chuyên biệt, không bỏ qua chỉ vì Sprint sắp kết thúc.

Không đặt mục tiêu “chấp nhận 1% request đọc sai tài khoản” để tối ưu tốc độ. Những rủi ro vi phạm quyền và nghĩa vụ có thể có **ngưỡng chấp nhận khác** so với lỗi giao diện ít tác động.

### Phân biệt kiểm soát và bằng chứng

**Kiểm soát:** API xác thực danh tính từ session và kiểm tra quyền trước khi trả tiến độ.

**Bằng chứng:** Integration/security test cho truy cập chéo tài khoản, thay phiên, hết quyền; review thiết kế và tín hiệu vận hành theo chính sách.

Không được nói “bảo mật đã xong” chỉ vì đã thêm một điều kiện if mà chưa kiểm chứng đường đi thực tế.

## 12. Độ tin cậy, phục hồi và lỗi phụ thuộc

Sản phẩm không chỉ phải chạy khi mọi dịch vụ khỏe mạnh. Mức chất lượng cần đạt cũng phụ thuộc **người dùng cần điều gì khi một thành phần thất bại**.

### Bốn kịch bản lỗi

| Sự kiện | Nguy cơ | Hành vi có thể yêu cầu |
| --- | --- | --- |
| API đọc tiến độ timeout | Người học không thể tìm lại bài; ứng dụng có thể treo | Giới hạn chờ, phản hồi lỗi phù hợp và cho phép thử lại có kiểm soát |
| Lưu tiến độ thất bại | Mất công sức học, thông báo sai | Không báo đã lưu khi chưa được xác nhận; có tín hiệu hỗ trợ |
| Mạng chập chờn | Request lặp hoặc response đến không theo thứ tự | Retry và xử lý thứ tự theo quy tắc đã xác nhận |
| Dịch vụ quyền truy cập không sẵn sàng | Có nguy cơ cho phép mở nhầm bài | Không đoán quyền dựa vào dữ liệu không đủ tin; áp dụng hành vi an toàn theo chính sách |

**Fallback** không phải lúc nào cũng là tiếp tục cho người dùng truy cập. Nếu không xác minh được quyền, ứng dụng có thể cần **từ chối an toàn** thay vì hiển thị dữ liệu nhạy cảm.

### Mục tiêu phục hồi cần dựa trên hậu quả

Hỏi:

- Có thể chấp nhận gián đoạn bao lâu trước khi ảnh hưởng nghiêm trọng?
- Có dữ liệu nào được phép mất, có dữ liệu nào **không thể**?
- Backup/restore, rollback hoặc cơ chế đối soát nào thực sự được diễn tập?
- Hệ thống phụ thuộc có hợp đồng timeout, retry và giới hạn tải không?
- Người hỗ trợ có biết ai bị ảnh hưởng để liên hệ và khôi phục không?

Các mục tiêu như **Recovery Time Objective (RTO)** hoặc **Recovery Point Objective (RPO)** chỉ nên được định nghĩa nếu bối cảnh cần và có người xác nhận. Một con số RPO bằng 0 không tự trở thành khả thi nếu kiến trúc và quy trình chưa hỗ trợ.

## 13. Khả năng sử dụng và tiếp cận

Một sản phẩm đúng logic nhưng người dùng không hoàn thành được thao tác vẫn chưa đạt mục đích.

### Ví dụ cần làm rõ

> “Học viên dễ dàng tìm lại bài đang học.”

Để biến thành điều kiện chất lượng, cần xác định:

- **Nhóm người dùng:** Học viên mới, học viên học nhiều khóa, người sử dụng công nghệ hỗ trợ.
- **Nhiệm vụ:** Đăng nhập → tìm nút → mở đúng bài hợp lệ.
- **Bối cảnh:** Điện thoại, desktop, tốc độ mạng, kích thước màn hình.
- **Thành công:** Người dùng tìm được tính năng và hiểu trạng thái khi không có tiến độ hoặc lỗi.
- **Cản trở:** Nút bị ẩn, ngôn ngữ không rõ, focus sai, thông báo lỗi khó hiểu.

### Cách kiểm tra phù hợp

| Rủi ro | Kiểm tra có thể làm |
| --- | --- |
| Không tìm thấy nút “Tiếp tục học” | Usability test với tác vụ thực và người dùng đại diện |
| Không dùng được bằng bàn phím | Kiểm tra thứ tự focus, kích hoạt điều khiển và trạng thái được truyền đạt |
| Màn hình đọc không hiểu tên nút | Kiểm tra nhãn, cấu trúc ngữ nghĩa và công cụ hỗ trợ khi phù hợp |
| Người dùng nhầm “chưa có tiến độ” với “lỗi mạng” | Thử thông điệp trong hai trạng thái với ví dụ rõ |
| Trải nghiệm trên mạng yếu | Kiểm tra loading, timeout và khả năng phục hồi theo profile được chọn |

Khi có **tiêu chuẩn accessibility bắt buộc** từ tổ chức, pháp luật hoặc hợp đồng, phải dùng đúng tiêu chuẩn đó và phương pháp kiểm chứng phù hợp. Không tự đặt một điểm kiểm tra tùy ý thay cho nghĩa vụ.

## 14. Chọn chiến lược kiểm thử theo rủi ro

**Risk-based testing** là sử dụng thông tin rủi ro để quyết định **kiểm tra điều gì trước, sâu đến đâu, bằng loại kiểm tra nào và cần bằng chứng gì**. Nó không có nghĩa bỏ kiểm thử bắt buộc ở phần có vẻ ít rủi ro.

### Các cấp kiểm chứng bổ sung nhau

| Cấp hoặc hình thức | Phù hợp với loại rủi ro | Điểm hạn chế |
| --- | --- | --- |
| **Unit test** | Quy tắc chọn bản ghi, định dạng, tính toán, xử lý biên thuần | Không tự chứng minh phân quyền tại API hay hợp đồng dữ liệu thật |
| **Contract test** | Bên gọi và bên cung cấp API hiểu khác về field, lỗi, phiên bản | Không thay kiểm chứng hành vi end-to-end |
| **Integration test** | Tương tác auth–API–database–cache, idempotency, transaction | Có thể chậm/phức tạp; cần dữ liệu và môi trường đáng tin |
| **End-to-end test** | Một số luồng kinh doanh trọng yếu qua hệ thống thật | Dễ chậm hoặc flaky nếu ôm mọi trường hợp |
| **Exploratory testing** | Trường hợp chưa được nghĩ đến, thao tác bất thường, khả năng dùng | Phụ thuộc kỹ năng và ghi nhận bằng chứng rõ |
| **Security testing / review** | Quyền, phiên, dữ liệu nhạy cảm, thay đổi bề mặt tấn công | Một kỹ thuật đơn lẻ không bao phủ mọi mối đe dọa |
| **Performance/load testing** | Độ trễ, tải cao, điểm nghẽn tài nguyên | Kết quả chỉ đại diện nếu môi trường và profile phù hợp |
| **Resilience/recovery testing** | Mất mạng, retry, đối tác lỗi, rollback và khôi phục | Cần cô lập an toàn tác động lên dữ liệu và dịch vụ |
| **Usability/accessibility testing** | Khả năng hoàn thành tác vụ và tiếp cận | Không thể suy ra hoàn toàn từ test logic tự động |
| **Production monitoring/feedback** | Rủi ro chỉ lộ dưới dữ liệu, lưu lượng và cách dùng thực | Không thay kiểm chứng trước phát hành, nhất là lỗi gây hại lớn |

### Ma trận rủi ro → bằng chứng

| Rủi ro | Kiểm tra sớm | Kiểm tra tích hợp / trước phát hành | Sau phát hành |
| --- | --- | --- | --- |
| Truy cập chéo tài khoản | Làm rõ quy tắc, test logic quyền | Integration/security test truy cập trực tiếp API, đổi phiên | Giám sát tín hiệu bất thường và phản ứng sự cố |
| Ghi sai tiến độ do retry | Unit test chính sách phiên bản/idempotency | Concurrent/integration test với DB và lỗi mạng | Đối soát, theo dõi ghi lỗi và báo cáo hỗ trợ |
| Chậm khi tải cao | Đo baseline, tối ưu truy vấn có căn cứ | Load test trên profile đại diện | Latency phân vị, lỗi và năng lực thực tế |
| Nút khó dùng | Prototype và thử tác vụ sớm | Kiểm tra khả năng tiếp cận, thử thiết bị | Phản hồi và quan sát tác vụ |
| API đối tác thay đổi | Contract examples và test | Compatibility/integration test phiên bản | Giám sát lỗi giao tiếp và quy trình phối hợp |

**Không nên đưa lỗi có tác động nghiêm trọng vào production chỉ để “đo thực tế”** khi có phương án kiểm thử an toàn trước phát hành. Quan sát sau phát hành là **lớp bổ sung**, không phải giấy phép bỏ bảo vệ.

## 15. Chọn độ sâu kiểm tra và thứ tự ưu tiên

Để phân bổ thời gian hợp lý, nhóm có thể đặt câu hỏi:

1. **Nếu lỗi xảy ra, hậu quả là gì?** Có mất dữ liệu, lộ quyền hoặc ảnh hưởng khả năng học không?
2. **Lỗi có khả năng xuất hiện qua cơ chế nào?** Dữ liệu mới, race condition, API không tương thích, thiết bị cũ?
3. **Có kiểm tra nhanh và đáng tin nào phát hiện sớm?** Unit test, ví dụ nghiệp vụ, contract test?
4. **Có cần kiểm tra ở ranh giới thật?** Auth, database, network, client cũ?
5. **Nếu test không phát hiện, khi lỗi xảy ra có quan sát và khôi phục không?**
6. **Phần nào được yêu cầu bắt buộc?** DoD, bảo mật, tuân thủ, cam kết hợp đồng?

### Ví dụ lựa chọn theo mức tác động

**Lỗi chính tả trên nhãn không ảnh hưởng thao tác:** Có thể đủ kiểm tra giao diện và review phù hợp với chính sách, không cần chạy một đợt performance stress test chỉ vì sửa nhãn.

**Thay logic xác thực và quyền học:** Cần xem thiết kế, integration/security test phù hợp, kiểm tra các trường hợp chéo tài khoản và tuân thủ mọi phê duyệt bắt buộc; không chỉ unit test một hàm lọc.

**Thay migration dữ liệu tiến độ:** Cần kiểm tra dữ liệu cũ/mới, tính tương thích, phương án rollback hoặc khôi phục và điều kiện chuyển đổi, vì lỗi có thể khó đảo ngược.

Chất lượng nên được quản lý theo **mức cần thiết để dùng được và an toàn**, không theo số lượng test bằng nhau ở mọi khu vực.

## 16. Dữ liệu kiểm thử, môi trường và bằng chứng đáng tin

Một test đúng về mặt câu lệnh vẫn có thể tạo **cảm giác an toàn giả** nếu dữ liệu hoặc môi trường không phản ánh rủi ro.

### Chọn dữ liệu theo kịch bản

Với tiến độ học, nên cân nhắc bộ dữ liệu thử:

- Tài khoản A/B với khóa và bài khác nhau.
- Người dùng chưa có tiến độ.
- Khóa học hết quyền sau khi dữ liệu đã lưu.
- Hai request có thời điểm gần nhau hoặc cùng timestamp.
- Dữ liệu cũ đã migration và dữ liệu mới.
- Request gửi lại, response đến muộn và phiên đăng nhập hết hạn.
- Trường hợp dữ liệu dài, tải nhiều và trạng thái lỗi phụ thuộc.

Không dùng dữ liệu cá nhân thật **không được cấp phép** chỉ vì “test chính xác hơn”. Ưu tiên dữ liệu tổng hợp hoặc đã được xử lý theo chính sách; quản lý tài khoản thử và môi trường thích hợp.

### Đánh giá môi trường

| Đặc điểm | Câu hỏi cần ghi |
| --- | --- |
| Phiên bản ứng dụng | Client/backend/schema có tương thích với production không? |
| Dữ liệu | Dung lượng và phân bố trường hợp có đại diện rủi ro không? |
| Tải | Có peak, retry và đa thiết bị như thực tế cần xem không? |
| Dịch vụ ngoài | Đang dùng mock, sandbox hay đối tác thật; mỗi lựa chọn kiểm chứng được gì? |
| Bảo mật | Quyền, secrets, audit và giới hạn truy cập có tương ứng? |
| CI | Test có ổn định, có chống flaky và quản lý trường hợp test bị bỏ không? |

**Mock không xấu**, nhưng test toàn mock không đủ chứng minh hệ thống sẽ tích hợp đúng với một API thật. Cần chọn lớp kiểm chứng dựa trên rủi ro và chi phí, không chỉ chọn test dễ viết.

### Một bản ghi bằng chứng tối thiểu

~~~text
Quality concern: Không lộ tiến độ giữa tài khoản
Scenario: A đăng xuất, B đăng nhập cùng thiết bị, response cũ của A đến muộn
Expected: B không thấy/đọc được tiến độ riêng của A
Verification: Integration test auth + cache + API; kiểm tra truy cập trực tiếp
Environment: Tích hợp với chính sách phiên tương đương sản phẩm
Result: PASS/FAIL kèm phiên bản build và điều kiện thử
Remaining risk: Hành vi với client cũ chưa được kiểm tra (nếu có)
Decision owner: Người có thẩm quyền chất lượng/phát hành theo chính sách
~~~

Bản ghi nên ngắn gọn và có thể tìm lại. Không cần tạo một tài liệu thủ công riêng cho mọi unit test; có thể dùng test report, PR, pipeline và hồ sơ quyết định hiện có.

## 17. Definition of Done và điều kiện phát hành theo rủi ro

Trong Scrum, **Definition of Done (DoD)** mô tả trạng thái Increment khi đáp ứng các tiêu chuẩn chất lượng của sản phẩm. Một Product Backlog Item chưa đáp ứng DoD **không được coi là phần của Increment hoàn thành**.

- Nếu tổ chức có chuẩn DoD bắt buộc, Scrum Team phải tuân theo tối thiểu chuẩn đó.
- Nếu tổ chức chưa có, Scrum Team cần định nghĩa DoD phù hợp cho sản phẩm.
- Khi nhiều Scrum Team cùng làm một sản phẩm, họ phải cùng định nghĩa và tuân thủ một DoD chung.

**DoD không phải danh sách được nới lỏng tùy ngày cuối Sprint.**

### Ví dụ DoD minh họa theo sản phẩm

- Chức năng đã tích hợp với sản phẩm hiện có và các tiêu chí chấp nhận được kiểm chứng.
- Những kiểm thử và review bắt buộc theo rủi ro liên quan đạt; không che test quan trọng thất bại.
- Phân quyền, bảo vệ dữ liệu và các nghĩa vụ chất lượng được đáp ứng.
- Thay đổi API/schema có đánh giá tương thích, migration hoặc khôi phục khi liên quan.
- Các tín hiệu vận hành, tài liệu và quy trình hỗ trợ cần thiết được cập nhật.

**Đây chỉ là DoD ví dụ**, không phải checklist tiêu chuẩn cho mọi sản phẩm.

### DoD và release criteria không đồng nghĩa

Một Increment đạt DoD là **phần sản phẩm dùng được**. Phát hành tới người dùng còn có thể phụ thuộc quyết định kinh doanh, lịch bảo trì, nghĩa vụ hợp đồng, kiểm định hoặc điều kiện rollout đã quy định.

Ví dụ:

| Tình huống | Trạng thái phù hợp |
| --- | --- |
| Code merge nhưng test phân quyền quan trọng thất bại | **Chưa Done**, không phải Increment hoàn thành |
| Increment đạt DoD, nhưng migration cần lịch triển khai được phê duyệt | **Done nhưng chưa release**, cần giữ rõ điều kiện phát hành |
| Increment đạt DoD và đủ điều kiện phát hành, muốn thử trên nhóm người dùng nhỏ | Có thể phát hành có kiểm soát, theo chính sách và cơ chế giám sát |
| Tính năng có lỗi lộ dữ liệu dù demo đẹp | Không được gọi đạt chất lượng; cần xử lý rủi ro trước khi tiếp tục |

Sprint Review **không phải cổng bắt buộc để phát hành Increment** trong Scrum. Increment có thể được giao trước Sprint Review khi đáp ứng DoD và điều kiện áp dụng.

### Người nào có quyền chấp nhận rủi ro còn lại?

Không nên để một developer tự tuyên bố “rủi ro chấp nhận được” cho dữ liệu cá nhân hoặc một nghĩa vụ hợp đồng. Đội cần làm rõ **vai trò quyết định theo chính sách**: Product Owner về giá trị/thứ tự backlog, Developers về cách xây và đáp ứng DoD, và các bên có thẩm quyền bảo mật, vận hành hoặc phát hành khi thực sự được yêu cầu.

**Không thể dùng sự chấp thuận nội bộ để vô hiệu hóa một yêu cầu pháp lý hoặc tiêu chuẩn bắt buộc.**

## 18. Bảng truy vết từ nhu cầu đến kiểm chứng

Không nhất thiết cần một công cụ truy vết lớn. Một bảng nhỏ giúp nhóm biết **vì sao kiểm tra tồn tại và thiếu bằng chứng ở đâu**.

| Nhu cầu / mục tiêu | Rủi ro | Điều kiện chất lượng | Bằng chứng | Trạng thái |
| --- | --- | --- | --- | --- |
| Học viên mở đúng bài | Chọn bản ghi không hợp lệ | Chọn bài gần nhất còn quyền theo quy tắc đã xác nhận | Acceptance/integration test | Chờ kiểm chứng |
| Giữ riêng tư | B xem dữ liệu A | Không đọc/hiển thị tiến độ ngoài quyền phía server | Test auth, cache, đổi phiên, API trực tiếp | Chờ kiểm chứng |
| Không mất tiến độ | Retry ghi trùng/lùi dữ liệu | Cập nhật theo quy tắc phiên bản/idempotency đã xác nhận | Concurrent test, test lỗi mạng/DB | Cần chốt quy tắc |
| Người dùng hiểu trạng thái | API lỗi bị hiển thị như chưa từng học | Phân biệt không có dữ liệu với không thể tải dữ liệu | UI/acceptance/usability test | Chờ kiểm chứng |
| Vận hành phản ứng kịp | Không biết ghi tiến độ thất bại | Tín hiệu lỗi, đối tượng ảnh hưởng và cách khôi phục phù hợp | Log/metric, thử runbook | Cần xác nhận |

Trạng thái trong bảng chỉ mang tính minh họa, không phải kết quả của một sản phẩm đang vận hành.

### Truy vết hai chiều

- Từ **nhu cầu** đến **rủi ro, điều kiện và test**: bảo đảm có đủ bằng chứng.
- Từ **test** về **rủi ro hoặc yêu cầu**: tránh duy trì một bộ kiểm thử tốn chi phí mà không ai hiểu nó bảo vệ điều gì.
- Từ **lỗi production** về **điều kiện bị bỏ sót**: bổ sung hiểu biết, thay đổi cách thiết kế/test nếu cần.

Không phải mọi dòng test phải được liên kết thủ công. Mục tiêu là **quyết định có thể giải thích**, không phải tăng số lượng biểu mẫu.

## 19. Tình huống xuyên suốt: xác định chất lượng cho “Tiếp tục học”

### 19.1. Bối cảnh

Scrum Team xây nền tảng học trực tuyến với **Product Goal**:

> “Học viên có thể học liên tục trên thiết bị thường dùng mà không mất tiến độ đã được xác nhận.”

Product Owner đề xuất lát cắt:

> “Học viên đã đăng nhập có thể mở bài gần nhất từ trang chủ.”

Nhóm gồm người phụ trách sản phẩm, Developers, tester và người có kiến thức vận hành/bảo mật phù hợp. Họ chưa biết cần đồng bộ video theo từng giây hay chưa, nhưng biết hệ thống lưu tiến độ theo tài khoản và quyền truy cập khóa học có thể thay đổi.

### 19.2. Phân tích nhu cầu và rủi ro

| Góc nhìn | Nhu cầu / lo ngại | Quyết định ban đầu |
| --- | --- | --- |
| Học viên | Tìm lại đúng bài nhanh, hiểu trạng thái nếu không có tiến độ | Ưu tiên luồng mở bài hợp lệ và trạng thái rỗng/lỗi |
| Product Owner | Giảm thao tác tìm lại bài và nhận phản hồi sớm | Lát cắt đầu chưa cần đồng bộ vị trí video từng giây |
| Developers | API và quyền phải rõ, không thể tin accountId do client gửi | Kiểm tra contract và ranh giới xác thực |
| Tester | Dữ liệu chéo tài khoản, hết quyền, retry dễ bị bỏ sót | Có kịch bản âm tính và tích hợp ngay từ đầu |
| Vận hành | Lỗi đọc/lưu tiến độ khó phát hiện | Tín hiệu và hướng xử lý theo mức rủi ro |

### 19.3. Đặt tiêu chí chấp nhận bằng ví dụ

~~~gherkin
Feature: Tiếp tục bài học đã lưu

  Scenario: Mở bài gần nhất còn quyền
    Given học viên A đã xác thực và còn quyền với khóa X
    And bản ghi hợp lệ mới nhất của A là bài 4 thuộc khóa X
    When A chọn "Tiếp tục học"
    Then ứng dụng mở bài 4 thuộc khóa X

  Scenario: Không truy cập chéo tài khoản
    Given tài khoản A đã lưu tiến độ ở khóa X
    And tài khoản B đã xác thực trên thiết bị từng được A sử dụng
    When B mở trang chủ hoặc gọi API đọc tiến độ
    Then dữ liệu riêng của A không được trả về cho B

  Scenario: Không nhầm lỗi mạng với chưa từng học
    Given học viên A đã có tiến độ được xác nhận
    And dịch vụ đọc tiến độ tạm thời không phản hồi
    When A mở trang chủ
    Then ứng dụng hiển thị trạng thái không thể tải phù hợp
    And không khẳng định rằng A chưa từng học bài nào
~~~

Những kịch bản này minh họa hành vi, **không thay thế** test về xác thực/ủy quyền phía server hoặc yêu cầu phi chức năng.

### 19.4. Lập kế hoạch bằng chứng theo mức rủi ro

| Ưu tiên thảo luận | Kịch bản | Bằng chứng cần thu |
| --- | --- | --- |
| **An toàn bắt buộc** | Không lộ dữ liệu chéo tài khoản hoặc trái quyền | Review thiết kế auth, integration/security test, test trực tiếp API |
| **Cao** | Ghi tiến độ bị lặp hoặc sai thứ tự | Test concurrency/retry sau khi chốt quy tắc dữ liệu |
| **Cao** | Luồng mở bài trả sai dữ liệu khi quyền thay đổi | Acceptance + API integration test |
| **Theo ngưỡng đã xác nhận** | Trang chủ tải chậm trong profile mục tiêu | Performance test/quan sát với môi trường đại diện |
| **Theo nhu cầu người dùng** | Nút khó tìm hoặc không dùng được bằng bàn phím | Usability/accessibility test |
| **Phù hợp vận hành** | Lỗi đọc/lưu không được phát hiện | Metric/log/runbook thử theo phạm vi |

Thứ tự này là **minh họa để trao đổi**. Khi có sự cố đã được quan sát, nhu cầu hoặc nghĩa vụ mới, nhóm phải điều chỉnh, không cứng nhắc giữ bảng.

### 19.5. Sprint Planning và Sprint Goal

Scrum Team có thể xác định **Sprint Goal**:

> “Học viên đã đăng nhập có thể mở lại đúng bài gần nhất còn quyền từ trang chủ mà không nhìn thấy tiến độ của tài khoản khác.”

Developers chọn backlog items và lập kế hoạch dựa trên **khả năng hoàn tất với DoD**. Nếu rủi ro đồng bộ qua thiết bị chưa được hiểu, có thể để nó sang lát cắt tiếp theo hoặc làm một spike giới hạn để giảm bất định.

**Không được bỏ phân quyền** chỉ để Sprint Goal “đạt đúng hạn”. Phạm vi có thể thương lượng, nhưng chất lượng và nghĩa vụ bắt buộc không bị giảm.

### 19.6. Trong Sprint: minh bạch tiến triển và thiếu bằng chứng

Ngày thứ tư, kiểm thử tích hợp phát hiện response của tài khoản A đến muộn sau khi B đăng nhập và làm cache hiển thị sai tiến độ.

- Developers ghi lại tình trạng, mức ảnh hưởng và test tái hiện.
- Daily Scrum kiểm tra rủi ro đối với Sprint Goal, điều chỉnh Sprint Backlog để ưu tiên khắc phục.
- Product Owner được thông tin nếu cần thay đổi phạm vi tính năng ít quan trọng.
- Người có chuyên môn bảo mật/dữ liệu tham gia nếu chính sách yêu cầu.
- Test được bổ sung và chạy trên luồng tích hợp; không chỉ sửa điều kiện hiển thị UI.

### 19.7. Cuối Sprint: nói thật về trạng thái

Ba tình huống:

| Thực tế | Cách kết luận có trách nhiệm |
| --- | --- |
| Chức năng hoạt động, test quyền và chất lượng liên quan đạt DoD | Có Increment hoàn thành; có thể kiểm tra tại Review và xem điều kiện release. |
| UI demo được nhưng test chéo tài khoản thất bại | **Chưa có Increment hoàn thành** cho phạm vi này; không gọi Done. |
| Increment đạt DoD nhưng thiếu bằng chứng tác động lên tỷ lệ quay lại học | Có bằng chứng về **khả năng sản phẩm**, chưa đủ kết luận **outcome dài hạn**. |

Ở Sprint Review, Scrum Team và các bên liên quan kiểm tra Increment, phản hồi và bối cảnh. Tại Sprint Retrospective, nhóm có thể cải tiến thói quen thử trường hợp đổi tài khoản, hợp đồng cache hoặc kiểm thử cạnh tranh.

## 20. Chất lượng liên tục sau phát hành: quan sát và học hỏi

Kiểm thử trước phát hành là cần thiết, nhưng production có những tổ hợp dữ liệu, hành vi và tải mà môi trường thử có thể chưa phản ánh. Đội cần **quan sát và phản ứng**, không coi việc release là kết thúc trách nhiệm chất lượng.

### Những tín hiệu hữu ích

- **Tính đúng đắn:** Lỗi chọn sai bài hoặc sai tài khoản, số trường hợp dữ liệu cần đối soát.
- **Bảo mật:** Tín hiệu truy cập bị từ chối bất thường, sự kiện liên quan tài khoản/quyền theo chính sách giám sát.
- **Độ tin cậy:** Tỷ lệ lỗi đọc/ghi, timeout, retry và trường hợp chưa xác nhận lưu.
- **Hiệu năng:** Latency phân vị theo profile, thiết bị và vùng ảnh hưởng phù hợp.
- **Khả năng sử dụng:** Người dùng có tìm thấy và hoàn thành luồng “Tiếp tục học” không?
- **Vận hành:** Thời gian phát hiện, phân loại, khôi phục và mức ảnh hưởng của sự cố.

Các tín hiệu cần được thiết kế để **không rò rỉ dữ liệu cá nhân** hoặc tạo dữ liệu giám sát quá mức không có mục đích rõ.

### Triển khai theo mức rủi ro

Một khả năng đã đạt DoD có thể được phát hành theo phạm vi có kiểm soát nếu sản phẩm và tổ chức cho phép:

1. Xác nhận điều kiện kỹ thuật và phê duyệt cần thiết.
2. Triển khai với chiến lược theo rủi ro như canary hoặc feature flag khi có ích.
3. Theo dõi tín hiệu lỗi, latency và ảnh hưởng người dùng.
4. Có cơ chế rollback/khôi phục được đánh giá; đặc biệt cẩn thận với migration dữ liệu.
5. Quyết định tiếp tục/mở rộng/tạm dừng dựa trên bằng chứng.

**Feature flag không khiến code chưa đạt DoD tự động trở thành Increment.** Không nên sử dụng rollout hạn chế để bỏ qua một lỗ hổng phân quyền đã biết.

## 21. Cân bằng chất lượng, thời gian, chi phí và phạm vi

“Chất lượng phù hợp” không phải chọn thấp nhất để giao nhanh. Đội cần phân biệt:

- **Điều không được thương lượng:** Quyền truy cập, nghĩa vụ pháp lý/bảo mật, tính toàn vẹn thiết yếu và tiêu chuẩn DoD áp dụng.
- **Mức mục tiêu được thỏa thuận:** Ví dụ latency hoặc khả năng phục hồi theo điều kiện và nhu cầu đã xác nhận.
- **Phần phạm vi có thể điều chỉnh:** Hoạt ảnh, khả năng chưa được xác nhận, biến thể ít ưu tiên.
- **Kiến thức còn thiếu:** Có thể cần một spike, prototype an toàn hoặc thử nghiệm dữ liệu trước khi chốt giải pháp.

### Bảng lựa chọn khi thời gian bị giới hạn

| Phương án | Khi có thể phù hợp | Điều kiện |
| --- | --- | --- |
| **Thu hẹp lát cắt giá trị** | Chưa đủ năng lực làm mọi biến thể | Phần còn lại vẫn dùng được, an toàn và đáp ứng DoD. |
| **Hoãn khả năng tùy chọn** | Không phục vụ trực tiếp mục tiêu ưu tiên | Product Owner hiểu tác động giá trị; backlog minh bạch. |
| **Đổi giải pháp kỹ thuật** | Phương án hiện tại có rủi ro hoặc chi phí quá lớn | Kiểm tra lại hành vi, khả năng vận hành và chất lượng. |
| **Thử nghiệm khám phá** | Thiếu thông tin để quyết định kiến trúc hoặc quy tắc | Timebox, câu hỏi rõ; không gọi prototype chưa đạt chuẩn là Increment. |
| **Chưa phát hành** | Có rủi ro bắt buộc chưa được xử lý, thiếu bằng chứng trọng yếu | Minh bạch lý do và hành động cần để đạt điều kiện. |
| **Giới hạn rollout** | Increment đã đạt DoD và được phép phát hành có kiểm soát | Có mục tiêu quan sát và khả năng ứng phó khi phát sinh lỗi. |

Không nên chọn “bỏ test quan trọng” như một lựa chọn cân bằng phạm vi. Việc đó **thay đổi mức rủi ro và trạng thái Done**, không chỉ tiết kiệm thời gian.

## 22. Những sai lầm thường gặp

| Sai lầm | Tác hại | Cách khắc phục |
| --- | --- | --- |
| **“Chất lượng cao nghĩa là không có bug.”** | Mục tiêu bất khả thi và bỏ qua usability, dữ liệu, vận hành | Xác định các chiều chất lượng liên quan, rủi ro và bằng chứng. |
| **Đặt một ngưỡng latency tùy ý** | Có thể vừa tốn chi phí vừa không giải quyết trải nghiệm người dùng | Đo đúng tác vụ, thiết bị, tải và baseline trước khi chốt. |
| **Chỉ viết tiêu chí happy path** | Không phát hiện quyền, retry, lỗi mạng hoặc trạng thái không có dữ liệu | Dùng ví dụ ngoại lệ và kịch bản âm tính theo rủi ro. |
| **Coi acceptance criteria là toàn bộ DoD** | Item đạt hành vi riêng nhưng thiếu chất lượng chung | Tách AC và DoD; kiểm tra cả hai. |
| **Đếm số test như chỉ báo chất lượng duy nhất** | Test trùng, flaky hoặc ít liên quan rủi ro | Ưu tiên bằng chứng có ý nghĩa và coverage kịch bản. |
| **Dùng ma trận rủi ro như phép tính xác suất chính xác** | Tạo cảm giác khách quan giả | Công khai giả định, bất định và ràng buộc bắt buộc. |
| **Đánh giá “chưa từng xảy ra” là không cần kiểm tra** | Có thể bỏ lọt hậu quả nghiêm trọng khó phát hiện | Xem cơ chế, tác động, thiếu telemetry và khả năng khôi phục. |
| **Hoãn phân quyền hoặc tính toàn vẹn dữ liệu** | Tạo nguy cơ gây hại trong Increment đầu | Đưa kiểm soát bắt buộc vào mỗi lát cắt. |
| **Mock mọi thứ và coi test xanh là đủ** | Sai hợp đồng, phiên, schema hoặc phụ thuộc thật | Kết hợp contract/integration test và môi trường đại diện. |
| **Chỉ đo trung bình latency** | Che đuôi chậm ảnh hưởng một nhóm người dùng | Xem phân vị, lỗi và phân bố theo profile. |
| **SLO được trình bày như SLA** | Hứa quá mức và gây hiểu nhầm nghĩa vụ | Phân biệt mục tiêu nội bộ, dữ liệu đo và hợp đồng. |
| **Gọi Done để đẹp Sprint report** | Chuyển lỗi và nợ chất lượng cho người dùng | Chỉ ghi nhận Increment đạt DoD; minh bạch điều chưa hoàn thành. |
| **Dùng feature flag để che lỗi nghiêm trọng đã biết** | Rủi ro vẫn tồn tại ở cấu hình khác hoặc khi bật | Kiểm tra các trạng thái cần thiết và giữ điều kiện an toàn. |
| **Chỉ hỏi tester về chất lượng ở cuối Sprint** | Lỗi thiết kế được phát hiện muộn, khó sửa | Làm rõ rủi ro và ví dụ cùng sản phẩm/dev/test từ đầu. |
| **Đo mọi thứ nhưng không quyết định gì** | Dashboard tăng chi phí mà không giảm rủi ro | Mỗi tín hiệu phải phục vụ một quyết định hoặc hành động. |
| **Bỏ việc theo dõi sau release** | Không biết chất lượng thực tế và lỗi lặp | Quan sát theo rủi ro, phản hồi và đưa học hỏi về backlog/DoD. |

## 23. Mẫu thực hành: phiếu chất lượng theo nhu cầu và rủi ro

Đội có thể dùng một phiếu ngắn trong refinement, Sprint Planning hoặc trước khi chọn một hạng mục rủi ro cao:

~~~text
Tên lát cắt / thay đổi:
Người dùng / mục tiêu sản phẩm:
Kết quả phải có (hành vi):
Những điều không được xảy ra:

Rủi ro:
  - Tình huống kích hoạt:
  - Tác động/người bị ảnh hưởng:
  - Khả năng xảy ra và mức chắc chắn của đánh giá:
  - Khả năng phát hiện/khôi phục:
  - Nghĩa vụ hoặc chính sách bắt buộc:

Điều kiện chất lượng:
  - Hành vi và ngoại lệ:
  - Thuộc tính phi chức năng có liên quan:
  - Ngưỡng/môi trường/cách đo nếu cần định lượng:
  - Điều kiện Done và phát hành:

Bằng chứng cần thu:
  - Trước khi code nhiều:
  - Trong CI/tích hợp:
  - Trước phát hành:
  - Sau phát hành:

Người xác nhận quyết định:
Giả định/câu hỏi còn mở:
Rủi ro còn lại:
Hành động tiếp theo và ngày xem lại:
~~~

**Không biến phiếu thành thủ tục lớn cho mọi việc nhỏ.** Mục đích là giúp đội nhìn rõ **điều gì phải đúng, vì sao và làm thế nào biết được**. Thông tin có thể nằm trong user story, test, pull request hoặc hệ thống quản lý rủi ro hiện có.

## 24. Bài tập thực hành

### Bài tập 1 — Từ nhu cầu mơ hồ đến tiêu chí có thể kiểm chứng

Cho ba phát biểu:

1. “Trang chủ phải nhanh.”
2. “Tiến độ học phải an toàn.”
3. “Tính năng dễ dùng với mọi học viên.”

**Yêu cầu:** Với mỗi phát biểu, viết ít nhất hai câu hỏi làm rõ, một kịch bản chất lượng có thể kiểm chứng và phương pháp thu bằng chứng.

**Gợi ý:** Với “nhanh”, cần thiết bị/mạng/tải và mốc đo. Với “an toàn”, cần danh tính/quyền và dữ liệu. Với “dễ dùng”, cần tác vụ cụ thể và nhóm người dùng đại diện. Không tự đặt một con số mà không nêu đó là giả định.

### Bài tập 2 — Lập risk register nhỏ

Sản phẩm có chức năng “Tiếp tục học” và dữ liệu qua thiết bị. Hãy lập ít nhất năm kịch bản rủi ro gồm:

- Nguyên nhân hoặc điều kiện kích hoạt.
- Sự kiện lỗi và tác động.
- Bằng chứng về khả năng xảy ra, hoặc ghi “chưa biết”.
- Cách phát hiện/khôi phục.
- Một kiểm soát hoặc test ưu tiên.

**Gợi ý:** Đừng quên truy cập chéo tài khoản, request ghi lặp, quyền hết hạn, timeout và khó sử dụng trên thiết bị di động.

### Bài tập 3 — Nhận diện AC, DoD, SLO và release criteria

Phân loại:

A. “Khi không có tiến độ hợp lệ, hiển thị trạng thái bắt đầu học.”

B. “Increment tích hợp và đáp ứng tiêu chuẩn kiểm thử/bảo mật chung.”

C. “Trong cửa sổ đo đã chọn, tỷ lệ yêu cầu đọc tiến độ thành công đạt ngưỡng được phê duyệt.”

D. “Migration được diễn tập, người có thẩm quyền xác nhận kế hoạch phát hành.”

**Gợi ý:** A thường là **acceptance criterion**; B là phần của **DoD**; C là **SLO** với SLI và phạm vi rõ; D là **release criterion**. Một tiêu chí có thể liên quan nhiều lớp nhưng không nên trộn tên gọi.

### Bài tập 4 — Ưu tiên bằng rủi ro, không chỉ đếm test

Đội có ít thời gian trước khi giao hai thay đổi:

- Thay nhãn nút “Học tiếp” thành “Tiếp tục học”.
- Thay cơ chế cache và quyền truy cập khi người dùng đổi tài khoản.

**Yêu cầu:** Đề xuất chiến lược test khác nhau, giải thích tại sao. Nếu phát hiện test phân quyền thất bại, hãy nêu quyết định Done/release có trách nhiệm.

**Gợi ý:** Không có nghĩa thay đổi nhãn không cần kiểm tra khả năng dùng; chỉ là **độ sâu và loại bằng chứng** phải tương xứng rủi ro. Không cho phép lỗi lộ dữ liệu vượt cổng chất lượng.

### Bài tập 5 — Thiết kế mục tiêu hiệu năng có điều kiện

Product Owner nói: “Mở bài phải phản hồi dưới 300 ms.” Không có dữ liệu nền, chưa rõ đo ở server hay điện thoại và chưa biết thiết bị của học viên.

**Yêu cầu:** Viết lại thành bản đề xuất **cần xác nhận**, gồm phép đo, môi trường, profile tải, dữ liệu, phân vị và nguồn quyết định. Nêu thông tin còn thiếu trước khi coi mục tiêu là cam kết.

**Gợi ý:** Không khẳng định 300 ms đúng hoặc sai chỉ vì đây là con số đẹp; phải xét nhu cầu và điều kiện kỹ thuật.

### Bài tập 6 — Hai thiết bị gửi tiến độ cùng lúc

Laptop A lưu bài 5 lúc 10:00; điện thoại B đang offline và gửi một bản ghi cũ khi có mạng lại. Đội chưa thống nhất “bản ghi nào thắng”.

**Yêu cầu:** Liệt kê ít nhất ba lựa chọn quy tắc nghiệp vụ để thảo luận, rủi ro của từng lựa chọn và test cần có. Không tự coi một cơ chế như last-write-wins là luôn đúng.

**Gợi ý:** Có thể dùng phiên bản máy chủ, quy tắc thời điểm đã xác nhận hoặc hòa giải theo loại nội dung. Mỗi cách cần xem tính đúng đắn, dữ liệu người dùng và khả năng khôi phục.

### Bài tập 7 — Kiểm tra trạng thái Done

Một story có UI hoàn chỉnh và demo được, nhưng:

- Integration test chéo tài khoản thất bại.
- Chưa xác nhận cách API timeout được hiển thị.
- CI có một test dữ liệu quan trọng bị bỏ qua.
- Không có thông tin vận hành về lỗi lưu tiến độ.

**Yêu cầu:** Phân biệt điều đã hoàn thành, điều thiếu theo AC/DoD và điều kiện release. Viết cập nhật Sprint Review ngắn, trung thực về trạng thái.

**Gợi ý:** Demo đẹp không tạo Increment Done khi tiêu chuẩn bắt buộc chưa đạt. Làm rõ thông tin thiếu với người có thẩm quyền và không hạ chất lượng.

### Bài tập 8 — Thiết kế ma trận kiểm thử theo rủi ro

Chọn một lát cắt nhỏ của “Tiếp tục học”. Lập bảng gồm **ít nhất bốn rủi ro**, test cấp unit/contract/integration/E2E hoặc exploratory thích hợp và bằng chứng quan sát sau phát hành.

**Yêu cầu nâng cao:** Chỉ ra một test ít hữu ích nên bỏ hoặc giảm trùng lặp, **nhưng không loại bỏ nghĩa vụ hoặc kiểm soát bắt buộc**.

### Bài tập 9 — Đánh giá số liệu trước và sau

Sau khi bổ sung test tích hợp và quan sát lỗi, đội thấy số lỗi production được ghi nhận **tăng** trong hai tuần đầu, nhưng thời gian phát hiện giảm và nhiều lỗi trước đây không có telemetry.

**Yêu cầu:** Giải thích vì sao số lỗi được ghi nhận tăng chưa tự chứng minh chất lượng xấu đi; cần thêm dữ liệu nào về mức nghiêm trọng, tác động, tỷ lệ người dùng, khả năng phát hiện và xu hướng?

**Gợi ý:** Thay đổi năng lực quan sát làm thay đổi số lỗi **nhìn thấy được**. Cần phân biệt sản phẩm xấu hơn với đo lường tốt hơn.

### Bài tập 10 — Mô phỏng ra quyết định phát hành

Một đội có Increment đã đạt test nghiệp vụ và performance target trong môi trường thử. Tuy nhiên, việc thu hồi quyền của người dùng chưa được kiểm thử đầy đủ; rollout có thể làm ảnh hưởng dữ liệu cá nhân.

Đóng vai Product Owner, Developers, tester, bảo mật và vận hành. **Yêu cầu:** Đưa ra quyết định có căn cứ: bổ sung test, giới hạn phạm vi, chưa phát hành hay phương án an toàn khác. Nêu ai có thẩm quyền, bằng chứng còn thiếu và điều kiện xem lại.

**Tiêu chí:** Không dùng áp lực thời hạn để “chấp nhận” một rủi ro vi phạm quyền chưa được xử lý, không gọi thiếu bằng chứng là thành công.

## 25. Checklist xác định chất lượng cần đạt

Trước khi bắt đầu một lát cắt quan trọng hoặc trước khi tuyên bố Done, Scrum Team/đội Agile có thể hỏi:

- [ ] Nhu cầu người dùng và **kết quả sản phẩm** đã được diễn đạt rõ?
- [ ] Các bên liên quan quan trọng về sản phẩm, kỹ thuật, chất lượng và vận hành đã được tham vấn đúng mức?
- [ ] Đã phân biệt **yêu cầu chức năng, thuộc tính chất lượng, acceptance criteria và DoD**?
- [ ] Rủi ro đã mô tả bằng kịch bản cụ thể thay vì chỉ ghi “bảo mật” hoặc “hiệu năng”?
- [ ] Tác động, khả năng xảy ra, mức bất định và khả năng khôi phục đã được xem xét?
- [ ] Có ghi “chưa biết” khi bằng chứng không đủ, thay vì tạo mức rủi ro chính xác giả?
- [ ] Những nghĩa vụ an toàn, dữ liệu, bảo mật và tuân thủ bắt buộc đã được giữ?
- [ ] Những yêu cầu như “nhanh”, “ổn định”, “dễ dùng” đã có phạm vi và cách kiểm chứng?
- [ ] Ngưỡng định lượng có nguồn quyết định, môi trường, đơn vị, profile và cách đo?
- [ ] Test đã bao gồm những trường hợp lỗi, ngoại lệ và dữ liệu âm tính có tác động lớn?
- [ ] Chọn test unit, contract, integration, E2E, security, performance và usability dựa trên rủi ro?
- [ ] Dữ liệu và môi trường test có đại diện cho những rủi ro được tuyên bố kiểm chứng?
- [ ] Có phân biệt **test đã chạy**, **test đã đạt** và **rủi ro còn lại**?
- [ ] Những kiểm tra bị skip, flaky hoặc thiếu bằng chứng đã được minh bạch?
- [ ] Increment được gọi Done chỉ khi **Definition of Done** thực sự đáp ứng?
- [ ] Điều kiện phát hành, rollout và khôi phục đã được xem xét theo rủi ro?
- [ ] Đã phân biệt mục tiêu SLO với nghĩa vụ SLA, không hứa vượt bằng chứng?
- [ ] Quyết định chấp nhận rủi ro còn lại có đúng người có thẩm quyền và không vi phạm nghĩa vụ bắt buộc?
- [ ] Sau release có tín hiệu quan sát và cơ chế phản ứng khi phát hiện lỗi?
- [ ] Phản hồi sản phẩm/sự cố được đưa trở lại backlog và thử nghiệm cải tiến?

Checklist là công cụ **thảo luận có trọng tâm**, không yêu cầu mọi story đều tạo đủ mọi tài liệu. Cấp độ chi tiết phải phù hợp với **giá trị, độ phức tạp, tác động và mức bất định**, nhưng không được bỏ những điều kiện chất lượng bắt buộc.

## 26. Tổng kết

- **Chất lượng cần đạt xuất phát từ nhu cầu và rủi ro**, không phải từ số lượng test, cảm giác “đã đủ tốt” hoặc một checklist chép từ dự án khác.
- **Chức năng đúng và thuộc tính chất lượng đi cùng nhau:** Dùng được, đúng nghiệp vụ, bảo mật, toàn vẹn dữ liệu, tin cậy, hiệu năng, tiếp cận và vận hành tùy bối cảnh.
- **Rủi ro cần được diễn đạt bằng kịch bản và bằng chứng:** Xem tác động, khả năng xảy ra, mức chưa biết và khả năng phục hồi; không biến ma trận định tính thành xác suất giả.
- **Yêu cầu chất lượng cần kiểm chứng được:** Nêu đối tượng, điều kiện, hành vi, ngưỡng có căn cứ, môi trường và cách đo. Không tự tạo SLA hoặc SLO tùy ý.
- **Test theo rủi ro không có nghĩa bớt an toàn:** Phân bổ đúng loại kiểm tra, nhưng giữ mọi nghĩa vụ, bảo mật, chất lượng và Definition of Done bắt buộc.
- **Chỉ gọi Increment Done khi đạt DoD:** Demo, merge code và test một luồng không thay thế bằng chứng tích hợp và chất lượng sản phẩm.
- **Chất lượng liên tục kéo dài qua phát hành:** Quan sát trải nghiệm và sự cố thật, học hỏi, điều chỉnh backlog, kỹ thuật và tiêu chuẩn khi xuất hiện kiến thức mới.

Khi có người nói “Tính năng này đã đạt chất lượng”, câu hỏi nên là: **“Đạt chất lượng nào, cho ai, trong điều kiện gì, nhằm kiểm soát rủi ro nào và chúng ta có bằng chứng nào để tin điều đó?”**
