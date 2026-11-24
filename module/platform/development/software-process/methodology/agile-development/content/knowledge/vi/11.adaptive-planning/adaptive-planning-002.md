# Lập kế hoạch cuốn chiếu theo mức độ hiểu biết

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **lập kế hoạch cuốn chiếu** (*rolling-wave planning*) và lý do mức chi tiết nên tăng khi công việc tiến gần thời điểm thực hiện.
2. Phân biệt mục tiêu dài hạn, định hướng phát hành, Product Backlog, kế hoạch Sprint và kế hoạch hằng ngày; nhận diện những quyết định cần thiết ở mỗi chân trời.
3. Chuyển giả định và mức bất định thành kế hoạch có điều kiện, làm rõ **dự báo** khác **cam kết** và biết khi nào nên lập kế hoạch lại.
4. Dùng phản hồi khách hàng, increment, dữ liệu dòng công việc và khả năng thực hiện thực tế để điều chỉnh thứ tự ưu tiên và phạm vi.
5. Thực hành xây dựng một kế hoạch cuốn chiếu cho dự án phần mềm, kết hợp Scrum, Kanban và các thực hành XP phù hợp, có quản lý rủi ro và tiêu chuẩn chất lượng.

## 1. Kế hoạch cuốn chiếu là gì?

Trong phát triển phần mềm, nhóm thường biết tương đối rõ **mục tiêu muốn đạt**, nhưng chưa biết chính xác tất cả tính năng, thiết kế, phụ thuộc và chi phí để đi đến mục tiêu đó. Người dùng có thể thay đổi ưu tiên sau khi trải nghiệm sản phẩm; đội kỹ thuật có thể phát hiện ràng buộc mới khi tích hợp hoặc kiểm thử.

**Lập kế hoạch cuốn chiếu** là cách lập kế hoạch theo nhiều khoảng thời gian: **công việc sắp thực hiện được làm rõ ở mức đủ chi tiết**, còn công việc xa hơn giữ ở mức định hướng, giả thuyết, mục tiêu hoặc nhóm hạng mục; khi đến gần, nhóm cập nhật bằng thông tin mới và triển khai kế hoạch chi tiết hơn.

Đây không phải cách “làm đến đâu tính đến đó”. Nhóm vẫn cần mục tiêu, ưu tiên, giới hạn ngân sách, nghĩa vụ, cột mốc quan trọng và cách đo tiến triển. Điểm khác là **không đối xử với mọi dự đoán tương lai như thể chắc chắn ngang nhau**.

Một mô hình dễ hình dung:

| Chân trời | Mức hiểu biết thường có | Độ chi tiết kế hoạch phù hợp |
| --- | --- | --- |
| **Xa** — hướng sản phẩm vài quý tới | Hiểu vấn đề lớn, cơ hội và ràng buộc; giải pháp còn có thể thay đổi | Product Goal, outcome, nhóm sáng kiến, mốc bắt buộc, rủi ro và giả định lớn |
| **Trung hạn** — một hoặc vài đợt giao tiếp theo | Biết những nhu cầu ưu tiên và phụ thuộc quan trọng; một số phương án cần kiểm chứng | Thứ tự backlog, phạm vi tối thiểu, kế hoạch phụ thuộc, dự báo có điều kiện |
| **Gần** — Sprint hoặc các hạng mục chuẩn bị kéo vào dòng việc | Có ví dụ người dùng, tiêu chí chấp nhận, lựa chọn kỹ thuật, năng lực và trở ngại rõ hơn | Lát cắt giá trị, Sprint Goal hoặc mục tiêu dòng việc, kế hoạch thực hiện, kiểm thử và chất lượng |
| **Ngay hiện tại** — trong ngày/đang xử lý | Có kết quả build, test, phản hồi và tình trạng công việc mới nhất | Phối hợp hoàn thành việc đang làm, gỡ chặn, điều chỉnh cách triển khai |

Các khoảng thời gian ở đây chỉ minh họa. Chân trời thực tế phụ thuộc vòng đời sản phẩm, tốc độ phản hồi, mức rủi ro và nghĩa vụ bên ngoài. Một hệ thống cần chứng nhận có thể phải làm rõ yêu cầu pháp lý từ sớm dù việc xây dựng cụ thể còn ở phía trước.

### Ví dụ xuyên suốt

Đội phát triển nền tảng học trực tuyến có **Product Goal** là “Học viên có thể bắt đầu và tiếp tục khóa học thuận tiện, đáng tin cậy trên thiết bị thường dùng”. Ban đầu, họ nghĩ cần tải toàn bộ khóa học để xem offline. Sau khi quan sát người dùng, họ phát hiện vấn đề lớn hơn là khó tìm lại bài đang học.

Nếu đã đặc tả đầy đủ và cam kết toàn bộ chức năng offline từ đầu, nhóm sẽ mất nhiều chi phí để đổi hướng. Với lập kế hoạch cuốn chiếu, nhóm giữ mục tiêu học tập ở tầm dài hạn nhưng **điều chỉnh các lát cắt gần**: trước mắt thử nút “Tiếp tục học”, kiểm tra tiến độ liên thiết bị và đo tỷ lệ quay lại; việc tải offline tiếp tục được nghiên cứu khi có bằng chứng về nhu cầu.

## 2. Vì sao kế hoạch cần phản ánh mức độ hiểu biết?

Kế hoạch đưa ra ở các thời điểm khác nhau có độ tin cậy khác nhau. Dữ liệu mới có thể xuất hiện qua phỏng vấn người dùng, phân tích hành vi, spike kỹ thuật, kiểm thử tích hợp hoặc vận hành sản phẩm thật.

### 2.1. Bốn loại thông tin cần tách bạch

| Loại | Cách hiểu | Ví dụ |
| --- | --- | --- |
| **Dữ kiện quan sát** | Điều đã xảy ra, có nguồn và phạm vi rõ | “Trong sáu tuần vừa qua, throughput theo tuần của nhóm là 3, 4, 4, 5, 3, 5 hạng mục theo cùng quy ước đếm.” |
| **Giả định** | Điều chưa xác minh đang được dùng để lập kế hoạch | “API tiến độ của đối tác sẽ hỗ trợ phát hiện cập nhật trùng.” |
| **Dự báo** | Ước lượng kết quả tương lai dựa trên dữ liệu và điều kiện | “Nếu các hạng mục tương đương và không có phụ thuộc mới, 12 hạng mục có thể cần khoảng 3–4 tuần ở nhịp gần đây.” |
| **Cam kết** | Quyết định hoặc nghĩa vụ đã được người có thẩm quyền xác nhận | “Nhóm sẽ kiểm thử quyền truy cập trước khi đề xuất phát hành.” |

Dự báo không phải lời hứa tuyệt đối. Một kế hoạch đáng tin cậy nêu rõ **điều kiện có thể làm dự báo thay đổi** và người có quyền điều chỉnh phạm vi hoặc mốc giao.

### 2.2. Những điều có thể thay đổi

- **Hiểu biết về nhu cầu:** Người dùng cần một kết quả khác với giả định ban đầu.
- **Kiến thức kỹ thuật:** Khả năng của API, độ phức tạp đồng bộ hoặc ràng buộc dữ liệu chỉ lộ ra sau thử nghiệm.
- **Năng lực thực hiện:** Có thành viên tham gia xử lý sự cố, nghỉ phép hoặc phụ thuộc đội khác.
- **Điều kiện thị trường và tổ chức:** Mốc hợp đồng, yêu cầu pháp lý hay cơ hội kinh doanh mới.
- **Chất lượng và vận hành:** Lỗi hồi quy, hiệu năng, bảo mật hoặc tình trạng tải làm thay đổi mức rủi ro.

**Lập kế hoạch chi tiết sớm không làm các bất định này biến mất.** Nó chỉ có thể khiến nhóm nhầm phần chưa biết thành phần đã chốt.

### 2.3. Khi nào cần chuẩn bị sớm hơn?

Không phải mọi quyết định đều nên chờ. Những việc khó đảo ngược hoặc có lịch ngoài dự án cần được nghiên cứu trước:

- Ký hợp đồng, chuẩn bị hồ sơ kiểm định hoặc xin cấp phép.
- Chuyển đổi dữ liệu lớn và các thay đổi kiến trúc khó rollback.
- Đặt môi trường thử nghiệm với đối tác hoặc mua thiết bị có thời gian cung ứng dài.
- Các nghĩa vụ về bảo mật, dữ liệu cá nhân, an toàn và khả năng khôi phục.

Lập kế hoạch cuốn chiếu có nghĩa là **đặt đúng mức chi tiết đúng lúc**, không trì hoãn thông tin quan trọng chỉ vì công việc còn xa.

## 3. Các tầng lập kế hoạch trong một sản phẩm Agile

Các tầng kế hoạch bổ sung nhau, nhưng không nhất thiết tạo thành một hệ thống giấy tờ phức tạp.

### 3.1. Tầng chiến lược: mục tiêu sản phẩm và giới hạn

Trước hết cần thống nhất **vấn đề**, **người dùng**, **kết quả mong muốn** và **ranh giới**:

> **Product Goal:** Trong định hướng phát triển tiếp theo, học viên có thể tiếp tục bài đang học từ thiết bị thường dùng một cách đáng tin cậy.

Kết quả có thể theo dõi là tỷ lệ học viên mở lại đúng bài, thời gian tìm lại bài và những lỗi mất tiến độ. Ranh giới có thể gồm bảo vệ dữ liệu cá nhân, nghĩa vụ hợp đồng và ngân sách vận hành.

Không cần định nghĩa tất cả màn hình và endpoint ở tầng này. Tuy nhiên, mục tiêu phải đủ rõ để dùng khi so sánh những cơ hội cạnh tranh nguồn lực.

### 3.2. Tầng định hướng phát hành: các kết quả và lựa chọn

Một **release plan/roadmap** có thể mô tả những khả năng dự kiến cung cấp theo đợt, thứ tự phụ thuộc và cột mốc bên ngoài. Roadmap nên cho thấy **ý định và mức chắc chắn**, thay vì vẽ một lịch cố định cho mọi tính năng chưa được nghiên cứu.

Ví dụ:

| Đợt dự kiến | Kết quả hướng đến | Phạm vi có thể cân nhắc | Điểm chưa chắc chắn |
| --- | --- | --- | --- |
| Đợt gần nhất | Giảm việc tìm lại bài đã học | Nút “Tiếp tục học” và dữ liệu bài gần nhất | Hành vi trên điện thoại, quyền truy cập vào khóa cũ |
| Đợt tiếp theo | Tiến độ nhất quán khi chuyển thiết bị | Đồng bộ, xử lý gửi lặp và lỗi mạng | Quy tắc xung đột, khả năng API hiện tại |
| Đợt xa hơn | Hỗ trợ học trong điều kiện mạng yếu | Một loại nội dung offline được phép | Nhu cầu, bản quyền, bảo mật, chi phí lưu trữ |

“Đợt xa hơn” có thể bị thay thế nếu dữ liệu cho thấy cơ hội khác đem lại giá trị cao hơn. Ngược lại, mốc kiểm định hoặc phát hành theo hợp đồng cần được ghi như **ràng buộc**, không được âm thầm thay đổi.

### 3.3. Tầng Product Backlog: chọn điều đáng làm tiếp

Trong Scrum, **Product Backlog** là danh sách có thứ tự, phát triển liên tục chứa những việc cần để cải tiến sản phẩm; **Product Owner** chịu trách nhiệm quản lý Product Backlog và tối đa hóa giá trị. Các hạng mục gần thực hiện thường được làm rõ kỹ hơn.

Ví dụ:

| Thứ tự hiện tại | Product Backlog Item | Loại bằng chứng | Mức chuẩn bị |
| --- | --- | --- | --- |
| 1 | Sửa lỗi tiến độ bị ghi sai khi gửi lại request | Lỗi đã tái hiện, ảnh hưởng trực tiếp giá trị | Đủ ví dụ, tiêu chí chấp nhận và phương án test để bắt đầu |
| 2 | Nút “Tiếp tục học” trên trang chủ | Có phản hồi người dùng; phạm vi có thể chia nhỏ | Cần chốt một số ví dụ UI và quyền truy cập |
| 3 | Đồng bộ khi hai thiết bị cập nhật đồng thời | Rủi ro được nhận diện, quy tắc chưa thống nhất | Cần trao đổi nghiệp vụ và thử nghiệm kỹ thuật |
| 4 | Tải video offline | Giả thuyết về nhu cầu; chi phí chưa rõ | Chỉ giữ mức ý tưởng và kế hoạch khám phá |

Đây là **thứ tự minh họa**, không phải quy tắc ưu tiên phổ quát. Nếu lỗi sản xuất nghiêm trọng hoặc hạn bắt buộc mới xuất hiện, Product Backlog và kế hoạch liên quan cần được xem lại.

### 3.4. Tầng Sprint: mục tiêu ngắn hạn và kế hoạch thực hiện

Trong Scrum, **Sprint Planning** tạo ra Sprint Goal và kế hoạch ban đầu hướng tới mục tiêu đó. **Sprint Backlog** bao gồm Sprint Goal, các Product Backlog Item được chọn và kế hoạch để giao Increment; **Developers** điều chỉnh kế hoạch khi có kiến thức mới.

Ví dụ Sprint Goal:

> “Học viên đã có tiến độ hợp lệ có thể mở lại đúng bài gần nhất trên thiết bị khác.”

Đội có thể chọn lát cắt, tiêu chí chấp nhận, hoạt động kiểm thử, phụ thuộc cần gỡ và cách phối hợp để đạt mục tiêu. Không nhất thiết hoàn tất toàn bộ backlog hoặc cố nhồi thêm tính năng khi đã thấy rủi ro vượt năng lực.

**Sprint Goal là điểm tựa cho việc thích nghi trong Sprint.** Các chi tiết có thể được làm rõ và thương lượng với Product Owner khi học được điều mới miễn là không gây nguy hiểm cho mục tiêu. Một yêu cầu mới không liên quan thường nên được đánh giá trong Product Backlog thay vì tự động chen vào giữa Sprint.

### 3.5. Tầng hằng ngày: điều chỉnh cách làm từ trạng thái thực

Đội thường xuyên kiểm tra:

- Việc nào đang chờ review, kiểm thử hoặc quyết định?
- Có lỗi mới làm thay đổi thứ tự thực hiện không?
- Phụ thuộc nào phải liên hệ ngay để không chặn mục tiêu?
- Có thể giúp hoàn thành việc đang làm trước khi bắt đầu việc mới không?

Trong Scrum, **Daily Scrum** giúp Developers kiểm tra tiến độ hướng Sprint Goal và điều chỉnh Sprint Backlog khi cần. Với Kanban, việc quan sát dòng công việc và giới hạn WIP giúp thấy điểm nghẽn, có thể phối hợp theo nhịp phù hợp mà không nhất thiết có Sprint.

## 4. Mức chi tiết tăng dần: làm rõ việc nào trước?

Một cách để lập kế hoạch hiệu quả là chia hạng mục theo **độ gần** và **rủi ro**.

| Loại hạng mục | Nội dung làm rõ nên có | Chưa cần cố định |
| --- | --- | --- |
| Ý tưởng dài hạn | Người dùng, vấn đề, giả thuyết giá trị, nghĩa vụ lớn, cách học thêm | Mọi bước thao tác và thiết kế màn hình |
| Hạng mục đang xét ưu tiên | Giá trị, độ khẩn, kích thước tương đối, phụ thuộc lớn, độ chắc chắn | Chi tiết kỹ thuật nhỏ chưa ảnh hưởng quyết định |
| Hạng mục sắp bắt đầu | User story hoặc mô tả tương đương, ví dụ nghiệp vụ, tiêu chí chấp nhận, rủi ro quan trọng, người xác nhận | Chi tiết của phần việc khác chưa làm |
| Hạng mục đang thực hiện | Quy tắc và ngoại lệ liên quan, thiết kế, test, tích hợp, trở ngại, phương án an toàn | Những cải tiến ngoài Sprint Goal/phạm vi đã chọn |
| Hạng mục chuẩn bị phát hành | Chất lượng, bằng chứng kiểm thử, giám sát/khôi phục, hồ sơ và phê duyệt bắt buộc | Các ý tưởng dự kiến cho bản sau |

**Product Backlog refinement** là hoạt động liên tục để làm rõ và phân rã hạng mục khi cần. Scrum không quy định refinement là một sự kiện bắt buộc với thời lượng cố định. Đội có thể dùng trao đổi giữa Product Owner, Developers, Tester và những người liên quan, tạo ví dụ cụ thể hoặc tổ chức technical spike để xử lý điều chưa biết.

### Ví dụ thay đổi mức làm rõ

Ý tưởng đầu: “Cho phép học viên tiếp tục bài cũ”.

Sau một vòng trao đổi: “Học viên cần nhìn thấy bài gần nhất còn quyền truy cập”.

Trước Sprint: “Khi tài khoản A có tiến độ bài 2 và bài 4, hệ thống chọn bài hợp lệ mới nhất theo quy tắc đã chốt; tài khoản B không thấy dữ liệu A.”

Trong lúc thực hiện: “Nếu API không xác nhận lưu thành công, giao diện phải hiển thị trạng thái chưa lưu và áp dụng cách thử lại đã thống nhất.”

Trước phát hành: “Kịch bản trên đã qua test, không có lỗi phân quyền đã biết, đạt Definition of Done và các yêu cầu vận hành áp dụng.”

Mỗi vòng bổ sung **thông tin cần cho quyết định kế tiếp**. Nếu một quy tắc bảo mật là điều kiện sống còn, cần làm rõ ngay trước khi triển khai phần có rủi ro; không chờ đến sát ngày phát hành.

## 5. Một vòng lặp lập kế hoạch cuốn chiếu

Lập kế hoạch thích ứng có thể thực hiện theo vòng:

~~~mermaid
flowchart TD
    A["Xác định Product Goal, kết quả và ranh giới"] --> B["Xem bằng chứng, ưu tiên, phụ thuộc và năng lực"]
    B --> C["Chọn chân trời cần quyết định và lát cắt gần nhất"]
    C --> D["Làm rõ vừa đủ, xác định tiêu chí và rủi ro"]
    D --> E["Thực hiện, tích hợp và kiểm thử"]
    E --> F["Xem Increment, phản hồi và dữ liệu dòng việc"]
    F --> G{"Giả định hay điều kiện kế hoạch thay đổi?"}
    G -- "Có" --> H["Điều chỉnh thứ tự, phạm vi, dự báo và cách làm"]
    G -- "Chưa" --> I["Giữ định hướng, cập nhật tình trạng và tiến triển"]
    H --> B
    I --> B
~~~

Để vòng lặp không trở thành họp hành hình thức, mỗi lần xem lại kế hoạch nên có **quyết định cụ thể**: giữ mục tiêu, đổi thứ tự, sửa phạm vi, gỡ phụ thuộc, tăng kiểm thử, hoãn phát hành hay mở rộng thử nghiệm.

### Bảy bước thực tế

1. **Đặt mục tiêu:** Thống nhất outcome của sản phẩm và ranh giới không thể vi phạm.
2. **Thu thập bằng chứng:** Phản hồi người dùng, Increment hiện có, xu hướng lỗi, năng lực, phụ thuộc và nghĩa vụ.
3. **Xếp ưu tiên theo giá trị và rủi ro:** Chọn hạng mục gần nhất giúp học hoặc giao giá trị; xử lý việc bắt buộc trước khi nó chặn cả kế hoạch.
4. **Chia nhỏ và làm rõ vừa đủ:** Chọn user story/lát cắt có thể kiểm chứng; làm rõ tiêu chí chấp nhận và Definition of Done.
5. **Lập dự báo có điều kiện:** Nêu phạm vi, dữ liệu sử dụng, năng lực dự kiến và những điều có thể thay đổi.
6. **Thực hiện và lấy phản hồi:** Tích hợp, kiểm thử, trình diễn kết quả thực chất; đo giá trị và chất lượng.
7. **Quyết định lại:** Cập nhật Product Backlog, Sprint Backlog hoặc dự báo theo quyền và thời điểm thích hợp; ghi lý do thay đổi.

Một vòng lặp tốt vừa có **nhịp kiểm tra thường xuyên** vừa tránh đổi thứ tự liên tục theo cảm tính. Các yêu cầu khẩn như mất dữ liệu hoặc lỗ hổng bảo mật cần cơ chế xử lý phù hợp, kể cả phải thay đổi kế hoạch đã lập.

## 6. Lập kế hoạch theo giá trị thay vì chỉ theo danh sách tính năng

Một roadmap chứa đầy tên tính năng và ngày dự kiến có thể khiến mọi người hiểu rằng chỉ cần hoàn thành đủ mục là đã đạt mục tiêu. Agile nhấn mạnh **phản hồi sớm và sản phẩm tăng dần**, vì việc hoàn tất một chức năng chưa chứng minh người dùng được cải thiện.

### Từ output sang outcome

| Mức | Ví dụ | Cách kiểm tra |
| --- | --- | --- |
| **Output** — thứ được giao | Nút “Tiếp tục học” xuất hiện trên trang chủ | Có chức năng chạy được và thỏa tiêu chí chấp nhận |
| **Outcome** — kết quả người dùng | Học viên tìm lại bài nhanh hơn | Đo thao tác, mức thành công, phản hồi và dữ liệu phù hợp |
| **Impact** — tác động dài hạn | Nhiều học viên hoàn thành khóa học | Theo dõi trong thời gian đủ dài, xét những yếu tố gây nhiễu khác |

Thay vì cam kết ngay “thêm offline, gamification và báo cáo” trong một quý, đội có thể đặt mục tiêu “giảm khó khăn khi tiếp tục việc học” rồi dùng các thử nghiệm nhỏ để tìm ra cách tạo kết quả đó.

### Lập kế hoạch cho cả hoạt động học hỏi

Không phải mọi việc gần nhất đều là lập trình tính năng. Có thể cần:

- Phỏng vấn học viên để xác định nguyên nhân bỏ dở.
- Prototype luồng trên điện thoại và thử khả năng nhận biết nút.
- Technical spike để kiểm tra đồng bộ và giải quyết xung đột API.
- Thử tải để biết độ trễ và giới hạn trước mốc sử dụng đông.
- Kiểm thử tự động hoặc cải thiện pipeline để giảm thời gian nhận phản hồi kỹ thuật.

Các hoạt động học hỏi cần có **câu hỏi, giới hạn thời gian hợp lý và quyết định sau kết quả**; nếu không, chúng dễ trở thành nghiên cứu không có điểm dừng.

### Ví dụ một giả thuyết có thể kiểm chứng

> “Nếu đặt nút ‘Tiếp tục học’ ở vùng dễ thấy trên trang chủ, học viên dùng điện thoại sẽ tìm lại bài nhanh hơn; nhóm sẽ theo dõi tỷ lệ tìm được đúng bài và thời gian thao tác trong thử nghiệm, đồng thời kiểm tra lỗi phân quyền và hiệu năng.”

Kết quả thử nghiệm có thể khiến nhóm mở rộng, điều chỉnh hoặc bỏ giải pháp. **Đó là thông tin làm kế hoạch tốt hơn**, không phải sự “phá vỡ kế hoạch” theo nghĩa tiêu cực.

## 7. Dự báo với dữ liệu thực thay vì ngày hoàn thành chắc chắn giả

Lập kế hoạch cuốn chiếu vẫn cần trả lời câu hỏi **“Bao lâu nữa có thể giao?”**. Câu trả lời nên dựa trên năng lực gần đây và những điều kiện có thể ảnh hưởng dự báo, kèm mức bất định phù hợp.

### 7.1. Các tín hiệu từ dòng công việc

| Tín hiệu | Ý nghĩa | Điểm cần lưu ý |
| --- | --- | --- |
| **Throughput** | Số hạng mục hoàn tất trong một khoảng thời gian | Phải có quy tắc đếm và loại hạng mục tương đối nhất quán. |
| **Cycle time** | Thời gian từ lúc bắt đầu thực hiện đến khi hoàn thành theo mốc của đội | Xem phân bố và ngoại lệ, không chỉ trung bình. |
| **Lead time** | Thời gian từ lúc yêu cầu được ghi nhận theo quy ước đến khi giao xong | Nêu rõ điểm bắt đầu/kết thúc; thường gồm thời gian chờ trước thực hiện. |
| **Work in Progress (WIP)** | Số hạng mục đã bắt đầu nhưng chưa xong | WIP quá cao có thể làm tăng chuyển ngữ cảnh và thời gian chờ. |
| **Work item age** | Tuổi của một việc vẫn đang được thực hiện | Giúp phát hiện công việc mắc kẹt trước khi nó hoàn tất. |
| **Velocity** | Story point hoàn thành trong Sprint theo cách ước lượng của riêng đội | Hữu ích cho một số dự báo nội bộ; không dùng so sánh năng suất giữa các đội. |

Các tín hiệu này hỗ trợ dự báo **khả năng giao**, không đo trực tiếp giá trị sản phẩm. Cần theo dõi song song lỗi, chất lượng và kết quả người dùng.

### 7.2. Ví dụ tính throughput đơn giản

Giả sử một nhóm có dữ liệu sáu tuần liên tiếp (minh họa, không phải dự án có thật):

| Tuần | Số hạng mục hoàn thành |
| --- | ---: |
| 1 | 3 |
| 2 | 4 |
| 3 | 4 |
| 4 | 5 |
| 5 | 3 |
| 6 | 5 |
| **Tổng** | **24** |

Throughput trung bình bằng **24 / 6 = 4 hạng mục/tuần**, nhưng các tuần thực tế dao động **3–5**. Nếu còn 12 hạng mục có kích thước và loại tương tự, ước lượng sơ bộ theo các nhịp này là:

- Ở nhịp **4 hạng mục/tuần**: khoảng **3 tuần**.
- Ở nhịp **3 hạng mục/tuần**: khoảng **4 tuần**.
- Ở nhịp **5 hạng mục/tuần**: khoảng **2,4 tuần**, thực tế cần xét lịch hoàn tất theo ngày hoặc tuần.

Khoảng này chỉ là **kịch bản minh họa**, không phải khoảng tin cậy thống kê hay lời hứa hoàn thành. Dự báo sẽ sai nếu backlog đổi mạnh, các hạng mục còn lại lớn hơn, năng lực đội thay đổi, xuất hiện lỗi hoặc có công việc bị chặn.

Nếu có nhiều dữ liệu lịch sử phù hợp, nhóm có thể xem **phân vị cycle time** hoặc thử mô phỏng theo phân bố throughput để thảo luận xác suất hoàn thành trước một mốc. Những phương pháp đó chỉ hữu ích khi công khai giả định, độ phù hợp của dữ liệu và giới hạn mô hình.

### 7.3. Forecast khác commitment

| Phát biểu | Loại | Cách cải thiện |
| --- | --- | --- |
| “Chắc chắn giao hết 12 story vào thứ Sáu sau ba tuần.” | Cam kết cứng thiếu căn cứ nếu còn bất định | Làm rõ điều kiện và phần phạm vi tối thiểu thực sự quan trọng. |
| “Nếu throughput gần đây giữ ổn định và các việc tương tự, đội ước tính cần khoảng ba tuần.” | Dự báo có điều kiện | Nêu phụ thuộc, rủi ro và thời điểm cập nhật lại. |
| “Đội cam kết kiểm thử luồng phân quyền và không phát hành khi chưa đạt tiêu chí an toàn.” | Cam kết hành động/chất lượng | Gắn với Definition of Done và quyền quyết định phát hành. |
| “Ngày 30/6 là mốc pháp lý bắt buộc.” | Ràng buộc ngoài dự án | Lập phương án phạm vi, dự phòng và các cổng phê duyệt đáp ứng mốc đó. |

Người quản lý có thể cần mốc giao để phối hợp đối tác; đội có trách nhiệm cung cấp **dự báo minh bạch** và lựa chọn đánh đổi, không thay ngày đã dự báo một cách tùy hứng hoặc tạo con số chính xác hơn dữ liệu cho phép.

## 8. Giữ ngày, phạm vi và chất lượng trong một kế hoạch thực tế

Khi thời gian, ngân sách và phạm vi đều bị giới hạn, đội phải thể hiện cách xử lý rủi ro.

### 8.1. Mốc giao cố định, phạm vi có thể điều chỉnh

Ví dụ một đối tác cần thử nền tảng học vào cuối tháng. Nhóm có thể thỏa thuận **phạm vi tối thiểu**:

1. Học viên đăng nhập và mở lại đúng bài đã lưu.
2. Dữ liệu tiến độ và quyền truy cập được bảo vệ.
3. Có cách phát hiện lỗi và khôi phục khi phát hành.

Các tính năng như gợi ý khóa học thông minh hoặc hoạt ảnh có thể chuyển sang đợt sau nếu không trực tiếp phục vụ mục tiêu. Chất lượng cốt lõi vẫn là **điều kiện**, không phải phần có thể cắt chỉ để giữ ngày.

### 8.2. Phạm vi bắt buộc hoặc nghĩa vụ cố định

Khi các yêu cầu là bắt buộc theo hợp đồng, an toàn hoặc quy định, nhóm cần phân tích sớm, nhận diện phụ thuộc, chuẩn bị bằng chứng và bàn về thời gian, nguồn lực hoặc phương án chuyển đổi. Scrum/Kanban vẫn có thể dùng để làm rõ dòng việc và nhận phản hồi nội bộ, nhưng không thay thế những cổng kiểm định bắt buộc.

### 8.3. Chất lượng là giới hạn của sự thích ứng

Nếu bản chạy được chưa đạt **Definition of Done** hoặc yêu cầu an toàn, nó chưa thể được xem là increment hoàn thành trong Scrum. Trong thực tế, nhóm có thể demo một nguyên mẫu để học hỏi, nhưng cần nói rõ **nguyên mẫu** khác với **phần mềm đủ điều kiện phát hành**.

Các thực hành XP như kiểm thử tự động, tích hợp liên tục, refactor và pair programming giúp rút ngắn phản hồi kỹ thuật, giữ chi phí thay đổi ở mức có thể kiểm soát.

### Minh họa “tam giác” quyết định

| Điều kiện cứng | Điều có thể điều chỉnh | Cách diễn đạt với bên liên quan |
| --- | --- | --- |
| Ngày sự kiện cố định và tiêu chuẩn an toàn bắt buộc | Phạm vi tính năng tùy chọn | “Sẽ ưu tiên luồng cốt lõi trước, tính năng chưa thiết yếu chuyển đợt sau.” |
| Phạm vi tuân thủ phải đủ | Ngày đưa vào dùng hoặc nguồn lực, trong giới hạn được duyệt | “Cần xác minh phụ thuộc và đánh giá lại mốc; không bỏ bước kiểm định.” |
| Ngân sách không tăng | Phạm vi hoặc thời gian, sau khi đánh giá hợp đồng và chi phí cơ hội | “Chọn giá trị cao nhất trong nguồn lực đã cấp; nêu rõ phần chưa thể giao.” |

Đừng tự động giả định tăng nhân lực sẽ làm thời gian giảm tỷ lệ thuận. Thời gian hướng dẫn, phụ thuộc và chi phí phối hợp cũng cần được tính.

## 9. Quản lý rủi ro và phụ thuộc trong từng làn kế hoạch

Một kế hoạch chỉ gồm tên tính năng và ngày bắt đầu/kết thúc dễ bỏ sót các điểm cản trở chính. Hãy làm rõ **điều kiện thành công** và **tín hiệu cho thấy cần điều chỉnh**.

### Ví dụ risk/assumption log tối giản

| Vấn đề | Loại | Tác động nếu sai | Hành động trước mắt | Điểm kiểm tra |
| --- | --- | --- | --- | --- |
| API của đối tác có cơ chế phát hiện request trùng | Giả định kỹ thuật | Có thể ghi tiến độ không nhất quán | Contract test và trao đổi với đội API | Trước khi chọn story đồng bộ |
| Học viên thực sự cần xem offline | Giả thuyết giá trị | Đầu tư nhiều nhưng ít sử dụng | Phỏng vấn và thử một loại nội dung | Trước khi mở rộng phạm vi offline |
| Hệ thống chịu được tải giờ cao điểm | Rủi ro vận hành | Ảnh hưởng trải nghiệm và nghĩa vụ với đối tác | Kiểm thử tải theo kịch bản phù hợp | Trước đợt dùng đông |
| Hồ sơ phê duyệt phải có trước phát hành | Ràng buộc bắt buộc | Không thể phát hành đúng mốc | Làm rõ hồ sơ, trách nhiệm và lịch duyệt | Tại các mốc kiểm soát đã thống nhất |

Một bản ghi hữu ích cần có **người chịu trách nhiệm, điều cần xác minh và thời điểm quyết định**. Rủi ro xa có tác động cao cần được điều tra sớm; vấn đề nhỏ dễ đảo ngược có thể đợi đến gần thời điểm triển khai.

### Không đợi đến Sprint cuối mới phát hiện phụ thuộc

Nếu chức năng tích hợp cần API đối tác, môi trường kiểm thử và phê duyệt bảo mật, đội có thể lập kế hoạch thử tích hợp một lát cắt từ sớm. Mốc nhận API có thể xuất hiện trong định hướng phát hành dù giao diện cụ thể chưa được chốt.

**Lập kế hoạch cuốn chiếu không loại bỏ kế hoạch phụ thuộc**. Nó chỉ tránh đặc tả quá chi tiết những phần còn chưa cần quyết định.

## 10. Khi nào cần lập kế hoạch lại?

Một đội Agile không cần xáo trộn kế hoạch mỗi khi có ý tưởng mới. Hãy phân biệt **thông tin mới có tác động thực** với **nhiễu ưu tiên**.

### Các tín hiệu nên kiểm tra lại

- Giả thuyết về giá trị bị phản hồi thực tế bác bỏ.
- Lỗi nghiêm trọng hoặc rủi ro bảo mật làm thay đổi khả năng phát hành.
- Một phụ thuộc quan trọng bị trễ hoặc có thay đổi kỹ thuật khó đảo ngược.
- Throughput/cycle time lệch đáng kể khỏi dự báo trong nhiều chu kỳ.
- Mục tiêu tổ chức, hợp đồng hoặc thời hạn bắt buộc thực sự thay đổi.
- Nhóm phát hiện hạng mục lớn hơn nhiều so với hiểu biết ban đầu.
- Việc kiểm tra Increment cho thấy cần điều chỉnh giải pháp hoặc phạm vi.

### Quy trình xử lý thay đổi

1. **Nêu dữ kiện mới** cùng nguồn, thời điểm và tác động.
2. **Xác định mục tiêu nào bị ảnh hưởng** và điều kiện nào vẫn phải giữ.
3. **Đưa ra lựa chọn**: đổi thứ tự, chia nhỏ, giảm phạm vi, tăng hỗ trợ, lùi mốc hoặc xử lý khẩn.
4. **Làm rõ người có quyền quyết định** về Product Backlog, phát hành, ngân sách và rủi ro.
5. **Cập nhật dự báo và thông tin cho các bên liên quan**; không âm thầm thay cam kết.
6. **Xác định lần kiểm tra tiếp theo** để xem thay đổi có hiệu quả không.

Nếu công việc thuộc một Sprint đang chạy, cần bảo vệ Sprint Goal và tuân thủ cơ chế minh bạch của Scrum. Đối với Kanban, nhóm có thể dùng chính sách chọn việc và mức độ khẩn rõ ràng để điều chỉnh dòng việc mà không cần chờ ranh giới Sprint.

### Ví dụ: phản hồi mới giữa Sprint

Sprint Goal là “Học viên mở được bài gần nhất đã lưu”. Giữa Sprint, đội kinh doanh muốn thêm biểu đồ huy hiệu thành tích. Thông tin này đáng ghi vào Product Backlog, nhưng chưa đủ lý do để ngắt công việc hướng Sprint Goal.

Ngược lại, nếu phát hiện tài khoản B có thể xem tiến độ của A, đội phải xử lý lỗi phân quyền theo mức rủi ro thực tế và trao đổi ngay về tác động kế hoạch. **Không giữ kế hoạch bằng cách bỏ qua điều kiện an toàn.**

## 11. Kết hợp Scrum, Kanban và XP cho lập kế hoạch cuốn chiếu

Agile là hệ giá trị và nguyên tắc thích ứng; Scrum, Kanban và XP hỗ trợ những phần khác nhau của công việc lập kế hoạch.

| Cách tiếp cận | Vai trò trong lập kế hoạch cuốn chiếu | Khi cần lưu ý |
| --- | --- | --- |
| **Scrum** | Product Goal định hướng dài hạn; Product Backlog làm rõ theo thứ tự; Sprint Planning lập mục tiêu và kế hoạch gần; Sprint Review và Retrospective giúp điều chỉnh | Sprint Goal giúp giữ tập trung; Sprint không phải cam kết giao cố định mọi item được dự đoán đầu kỳ. |
| **Kanban** | Nhìn thấy trạng thái dòng việc, chính sách kéo việc, WIP, thời gian chờ và throughput; bổ sung dữ liệu để điều chỉnh cam kết/dự báo | Không cố dùng throughput của công việc quá khác nhau như thước đo chắc chắn; làm rõ quy tắc đếm. |
| **XP** | Kiểm thử tự động, CI, refactor và lập trình cặp giúp phản hồi kỹ thuật sớm, hỗ trợ giảm chi phí đổi kế hoạch | Không coi tăng tốc code là đủ nếu thiếu phản hồi giá trị từ người dùng. |

### Một cách phối hợp thực tế

Một đội dùng Scrum để tập trung vào Sprint Goal cho luồng học tiếp; theo dõi bảng Kanban và WIP để thấy ticket chờ review; dùng CI và test tự động để tạo increment đáng tin. Sau Sprint Review, Product Owner điều chỉnh thứ tự backlog theo phản hồi. Ở mức xa hơn, nhóm cập nhật dự báo cho đợt phát hành khi có thêm dữ liệu thực hiện.

Nếu đội vận hành nhận yêu cầu liên tục, có thể dùng **Kanban như cách chính** để dự báo công việc theo năng lực và tuổi hạng mục. Không cần đưa mọi việc vào Sprint giả tạo chỉ để gọi đó là Agile.

### Kế hoạch có thể thay đổi nhưng tiêu chuẩn chất lượng nhất quán

Khi điều chỉnh phạm vi, nhóm cần rà lại tác động lên:

- Tiêu chí chấp nhận của user story và Definition of Done.
- Các bài kiểm thử hồi quy, tính toàn vẹn dữ liệu và bảo mật.
- Phương án triển khai, monitoring, hỗ trợ và rollback khi áp dụng.
- Hợp đồng, phê duyệt hoặc tài liệu bắt buộc.

Khả năng thay đổi an toàn phụ thuộc vào năng lực kỹ thuật và sự minh bạch, không phải chỉ ở việc đổi lịch Sprint Planning.

## 12. Tình huống đầy đủ: từ định hướng một quý đến hai Sprint tiếp theo

### 12.1. Bối cảnh giả định

Một đội phát triển nền tảng học trực tuyến có mục tiêu trong quý: “Giảm khó khăn khi học viên quay lại và hoàn thành bài học trên thiết bị thường dùng”. Có giới hạn nhân lực và một mốc review với đối tác ở cuối giai đoạn. Trong buổi lập kế hoạch đầu quý, các đề xuất gồm:

- Tính năng “Tiếp tục học” từ trang chủ.
- Đồng bộ vị trí học trên hai thiết bị.
- Tải video offline.
- Báo cáo tiến độ cho quản trị viên doanh nghiệp.
- Cải thiện độ trễ trang học vào giờ cao điểm.

Các đề xuất chưa có mức hiểu biết như nhau. Nhóm biết nhiều học viên khó tìm lại bài, nhưng chưa rõ tỷ lệ cần offline; hệ thống có dấu hiệu chậm, song nút thắt chưa xác định.

### 12.2. Kế hoạch xa: xác định outcome và rủi ro

| Nội dung | Quyết định ban đầu |
| --- | --- |
| Product Goal | Học viên có thể trở lại bài đã học một cách đơn giản, tin cậy |
| Outcome cần theo dõi | Tỷ lệ học viên mở lại đúng bài; thời gian tìm bài; dấu hiệu hoàn thành học phần |
| Guardrail | Không tăng lỗi mất tiến độ, phân quyền sai hoặc độ trễ vượt mức chấp nhận |
| Mốc bên ngoài | Review với đối tác cuối giai đoạn; giới hạn nội dung phải trình diễn và quyền dữ liệu |
| Giả định cần kiểm chứng | Nhu cầu offline có đáng đầu tư; API tiến độ hỗ trợ đồng bộ an toàn |
| Chưa quyết định | Toàn bộ giao diện cuối cùng, công nghệ lưu offline và số lượng tính năng cố định |

**Mục tiêu và ranh giới rõ**, nhưng các giải pháp xa được giữ mở để học hỏi.

### 12.3. Kế hoạch gần: chọn lát cắt đầu

Sau khi trao đổi với học viên, nhóm chọn thử lát cắt:

> **User story:** Là học viên đã đăng nhập, tôi muốn nhìn thấy bài học gần nhất đã lưu trên trang chủ để mở lại bài mà không phải tìm kiếm.

Tiêu chí chấp nhận ban đầu:

1. Nếu có tiến độ hợp lệ, hệ thống hiển thị đúng bài gần nhất theo quy tắc đã xác nhận.
2. Học viên chỉ xem được tiến độ và nội dung mình có quyền truy cập.
3. Khi không có tiến độ hợp lệ, giao diện không hiển thị bài giả.
4. Nếu dịch vụ đọc tiến độ lỗi, giao diện thông báo phù hợp, không khẳng định dữ liệu không tồn tại.

Nhóm xác định Sprint Goal xoay quanh **khả năng mở lại đúng bài**, còn hai câu hỏi kỹ thuật về xung đột đồng bộ được ghi để tìm hiểu sớm trước khi nhận story đồng bộ chi tiết.

### 12.4. Phản hồi sau Sprint đầu

Trong Sprint Review, người dùng thử nhận biết nút tốt hơn nhưng một số người trên điện thoại muốn mở đúng vị trí video đã dừng. Cùng lúc, kiểm thử tích hợp phát hiện request cập nhật tiến độ gửi lặp có thể tạo thứ tự không nhất quán.

Nhóm có hai loại thông tin mới:

- **Phản hồi sản phẩm:** Có nhu cầu cần khảo sát thêm về vị trí video, chưa chắc phải đồng bộ từng giây.
- **Rủi ro kỹ thuật:** Cần giải quyết tính nhất quán trước khi mở rộng đồng bộ.

Kế hoạch cuốn chiếu cho phép Product Owner điều chỉnh ưu tiên: xử lý an toàn dữ liệu và thử một lát cắt mở đúng vị trí đã được xác nhận; đề xuất video offline vẫn ở mức khám phá.

### 12.5. Kế hoạch Sprint tiếp theo

| Ưu tiên gần | Việc dự kiến | Điều kiện để nhận/giao | Cách kiểm chứng |
| --- | --- | --- | --- |
| 1 | Sửa xử lý yêu cầu cập nhật tiến độ gửi lại | Thống nhất quy tắc phiên bản và dữ liệu | Test tích hợp gửi lặp và trường hợp đồng thời |
| 2 | Mở vị trí đã lưu trên một luồng video có mạng | Chốt hành vi khi dữ liệu không hợp lệ, quyền truy cập | Test luồng người dùng và phỏng vấn ngắn |
| 3 | Thử prototype học khi mất mạng | Giới hạn ở học hỏi, chưa hứa phát hành | Quan sát nhu cầu và chi phí/rủi ro dự kiến |

Đây là **dự kiến về thứ tự**, còn Sprint Goal cụ thể và kế hoạch sẽ được tạo khi Sprint Planning dựa trên năng lực và tình trạng thực tế. Không phải tất cả ba việc nhất thiết được đưa vào cùng Sprint.

### 12.6. Giao tiếp với đối tác

Một cập nhật phù hợp:

> “Mục tiêu của đợt review vẫn là cho học viên tiếp tục bài đang học thuận tiện và an toàn. Hiện luồng mở đúng bài đã hoạt động trong bản thử, còn đồng bộ tiến độ có một rủi ro nhất quán dữ liệu cần xử lý trước khi mở rộng. Nhóm ưu tiên khắc phục rủi ro và kiểm chứng nhu cầu mở đúng vị trí video. Tải offline đang ở giai đoạn nghiên cứu, chưa nằm trong phạm vi cam kết phát hành. Chúng tôi sẽ cập nhật dự báo sau lần kiểm thử tích hợp kế tiếp.”

Thông điệp nêu được **kết quả đã quan sát**, **điều chưa chắc**, **quyết định ưu tiên** và **điểm kiểm tra lại**, giúp đối tác hiểu thực tế thay vì tưởng roadmap cũ là lời hứa không thay đổi.

## 13. Phản ví dụ: khi kế hoạch cuốn chiếu bị hiểu sai

### Trường hợp A — “Không cần kế hoạch dài hạn”

Đội chỉ chọn ticket nóng nhất trong ngày, không có Product Goal hoặc chuẩn ưu tiên. Kết quả có thể là nhiều việc ngắn hạn đã xong nhưng sản phẩm thiếu định hướng.

**Cách cải thiện:** Giữ mục tiêu sản phẩm, giới hạn và các mốc lớn; cho phép thay đổi chi tiết thực hiện khi có dữ liệu mới.

### Trường hợp B — “Thay kế hoạch liên tục mới là Agile”

Mỗi ý kiến mới của người quản lý lập tức thay công việc đang làm. Đội tăng WIP, chuyển ngữ cảnh nhiều và hiếm khi hoàn thành một lát cắt.

**Cách cải thiện:** Thiết lập quyền quyết định backlog, tiêu chí mức khẩn, giới hạn WIP và nhịp xem xét. Trong Scrum, dùng Sprint Goal làm điểm tựa; trong Kanban, dùng chính sách kéo việc và xử lý khẩn minh bạch.

### Trường hợp C — “Mọi thứ xa đều mơ hồ, kể cả nghĩa vụ bắt buộc”

Dự án cần kiểm thử bảo mật và phê duyệt pháp lý trước ngày công bố nhưng chỉ chuẩn bị hồ sơ ở tuần cuối.

**Cách cải thiện:** Xác định cổng phê duyệt, dữ liệu, phụ thuộc và thời gian kiểm định từ sớm; cập nhật kế hoạch chi tiết cho phần phát triển theo từng đợt.

### Trường hợp D — “Ước lượng càng chi tiết càng chính xác”

Đội chia mọi việc xa thành hàng trăm task, gán ngày cố định nhưng không kiểm chứng nhu cầu hoặc rủi ro tích hợp. Khi xuất hiện thay đổi, phải sửa toàn bộ kế hoạch.

**Cách cải thiện:** Phân biệt độ gần và độ chắc chắn. Ở mức xa, dùng outcome, giả thuyết và khoảng dự báo; ở mức gần, làm rõ lát cắt và tiêu chí cụ thể.

### Trường hợp E — “Giảm phạm vi đồng nghĩa giảm chất lượng”

Để giữ ngày giao, đội bỏ test phân quyền hoặc ghi nhãn “Done” khi chưa đáp ứng Definition of Done.

**Cách cải thiện:** Cắt tính năng tùy chọn hoặc thương lượng mốc, giữ yêu cầu an toàn và chất lượng bắt buộc. Một bản demo chưa đạt điều kiện sử dụng cần được gọi đúng là bản thử.

## 14. Mẫu kế hoạch cuốn chiếu có thể dùng ngay

Không cần tạo một bộ tài liệu đồ sộ. Một bản ghi gọn có thể là:

~~~text
PRODUCT GOAL:
  Học viên mở lại bài đang học thuận tiện, dữ liệu tiến độ đáng tin cậy.

KẾT QUẢ CẦN ĐO:
  Tỷ lệ mở lại đúng bài; thời gian tìm lại bài; lỗi mất tiến độ.

GIỚI HẠN:
  Quyền truy cập dữ liệu; Definition of Done; mốc review với đối tác.

CHÂN TRỜI XA (ý định, giả thuyết):
  Đồng bộ tiến độ, học trong điều kiện mạng yếu.
  Chưa chốt toàn bộ giải pháp hoặc ngày giao từng tính năng.

CHÂN TRỜI GẦN (ưu tiên, sẵn sàng):
  1. Sửa lỗi ghi tiến độ trùng.
  2. Mở lại đúng bài trên thiết bị khác.
  3. Thử prototype vị trí nút trên điện thoại.

KẾ HOẠCH HIỆN TẠI:
  Sprint Goal hoặc mục tiêu dòng việc; lát cắt; tiêu chí chấp nhận;
  các phụ thuộc, người phụ trách, kiểm thử và cách phát hành an toàn.

GIẢ ĐỊNH/RỦI RO:
  API đối tác hỗ trợ phát hiện cập nhật trùng -> cần contract test.
  Nhu cầu offline chưa rõ -> cần quan sát nhóm người học mạng yếu.

DỰ BÁO:
  Khoảng thời gian và điều kiện dựa trên dữ liệu thực hiện gần đây;
  không chuyển dự báo thành cam kết tuyệt đối khi chưa đủ căn cứ.

ĐIỂM KIỂM TRA TIẾP:
  Sau buổi review increment và kết quả test đồng bộ.

QUYỀN QUYẾT ĐỊNH:
  Product Owner quyết định thứ tự Product Backlog;
  Developers xây và điều chỉnh kế hoạch thực hiện trong Scrum;
  người có thẩm quyền xử lý phát hành, hợp đồng và rủi ro bắt buộc.
~~~

Mẫu này chỉ hữu ích nếu được cập nhật theo bằng chứng và dẫn đến quyết định thực tế; không nên điền cho đủ mục mà bỏ qua các vấn đề người dùng đang gặp.

## 15. Bài tập thực hành

### Bài tập 1 — Chọn mức chi tiết ở từng chân trời

Đội có một Product Goal: “Học viên hoàn thành khóa học thuận tiện trên nhiều thiết bị”. Các ý tưởng gồm: tiếp tục học, đồng bộ tiến độ, tải offline, gợi ý bài học và huy hiệu thành tích.

**Yêu cầu:** Chia thông tin thành ba chân trời: định hướng xa, backlog chuẩn bị trong vài tuần tới, và hạng mục bắt đầu ngay. Cho mỗi chân trời, viết thông tin **phải biết**, **có thể chưa biết** và **bằng chứng cần lấy tiếp**.

**Gợi ý:** Đừng viết API chi tiết cho cả năm tính năng khi chưa rõ tính năng nào mang giá trị. Với hạng mục sắp làm, cần ví dụ nghiệp vụ, rủi ro phân quyền và tiêu chí chấp nhận.

### Bài tập 2 — Dự báo với throughput

Một nhóm hoàn tất số hạng mục theo tuần: 4, 3, 5, 4, 2, 6. Có 16 hạng mục tương đối tương tự còn lại.

**Yêu cầu:** Tính throughput trung bình; cho một dự báo sơ bộ có điều kiện; liệt kê ít nhất bốn yếu tố có thể làm dự báo thay đổi. Giải thích vì sao không được ghi ngày chắc chắn chỉ dựa trên trung bình.

**Gợi ý đáp án:** Tổng 24 hạng mục trong sáu tuần, trung bình **4 hạng mục/tuần**; 16 hạng mục tương tự có thể tương ứng khoảng **4 tuần** ở nhịp trung bình đó. Các yếu tố gồm thay đổi phạm vi, lỗi sản xuất, kích thước hạng mục, nghỉ phép, phụ thuộc và chất lượng dữ liệu lịch sử. Đây là phép tính minh họa, không phải xác suất hoàn thành.

### Bài tập 3 — Một yêu cầu mới giữa Sprint

Sprint Goal của nhóm là “Học viên mở lại đúng bài gần nhất”. Sau ba ngày, người đại diện kinh doanh đề nghị làm thêm chatbot hỗ trợ, trong khi Tester phát hiện lỗi truy cập dữ liệu của tài khoản khác.

**Yêu cầu:** Nêu cách xử lý từng thông tin: ai quyết định, điều gì phải minh bạch, kế hoạch nào cần cập nhật và cần kiểm chứng gì trước khi giao Increment.

**Gợi ý:** Chatbot có thể được Product Owner đánh giá trong Product Backlog; lỗi quyền truy cập cần xử lý theo rủi ro thực tế và tiêu chuẩn chất lượng. Không tự nhận cả hai vào Sprint và bỏ qua Sprint Goal.

### Bài tập 4 — Xây dựng kế hoạch cho mốc cố định

Một tổ chức cần chạy kỳ thi trực tuyến sau sáu tuần. Phần mềm phải bảo vệ bài nộp và đáp ứng số người dự thi dự kiến; đội còn muốn bổ sung giao diện báo cáo đẹp.

**Yêu cầu:** Thiết kế kế hoạch cuốn chiếu cho sáu tuần: mốc phụ thuộc và kiểm thử nào phải chuẩn bị ngay, phạm vi tối thiểu nào cần trước ngày thi, phần nào có thể lùi, và trigger nào buộc xem lại dự báo.

**Gợi ý:** Đề xuất test tải, thử luồng nộp bài và khôi phục dữ liệu sớm; không chờ tuần cuối. Báo cáo trang trí có thể xếp sau nếu không thuộc nghĩa vụ bắt buộc. Không rút gọn kiểm thử an toàn chỉ vì ngày cố định.

### Bài tập 5 — Chọn Scrum, Kanban và XP phù hợp

Một nhóm vừa phát triển tính năng mới theo mục tiêu quý, vừa nhận nhiều yêu cầu hỗ trợ và lỗi gấp. Các lần tích hợp thường xuyên gây lỗi hồi quy.

**Yêu cầu:** Đề xuất một cách phối hợp Scrum, Kanban và thực hành XP. Giải thích cách duy trì mục tiêu, giới hạn WIP, nhận công việc khẩn và cải thiện kiểm thử. Chọn hai chỉ số dòng việc, một chỉ số chất lượng và một outcome để đánh giá sau vài tuần.

**Gợi ý:** Không chỉ tăng số cuộc họp. Xác định chính sách ưu tiên, năng lực thực tế, CI/test và cách phản hồi người dùng. Kiểm tra xem thay đổi có giảm thời gian chờ hoặc lỗi mà vẫn tạo giá trị không.

## 16. Checklist kiểm tra kế hoạch thích ứng

Trước một lần lập kế hoạch hoặc cập nhật dự báo, nhóm có thể tự hỏi:

- [ ] **Product Goal và outcome** cần đạt đã rõ, có người chịu trách nhiệm?
- [ ] Có phân biệt mốc bắt buộc, cam kết và dự báo có điều kiện?
- [ ] Công việc gần được làm rõ đủ để triển khai an toàn; việc xa không bị đặc tả quá mức?
- [ ] Các giả định quan trọng và rủi ro khó đảo ngược đã có cách kiểm chứng sớm?
- [ ] Product Backlog phản ánh giá trị, phụ thuộc, rủi ro và thông tin mới nhất?
- [ ] Đội đã tính đến năng lực thực tế, công việc vận hành, nghỉ phép và trở ngại?
- [ ] Có sử dụng dữ liệu throughput/cycle time hoặc bằng chứng khác với định nghĩa và giới hạn rõ?
- [ ] Các lát cắt có thể giao tăng dần, kiểm thử và nhận phản hồi?
- [ ] Definition of Done, bảo mật, dữ liệu và nghĩa vụ chất lượng vẫn được giữ?
- [ ] Có quy tắc xem lại và thay đổi kế hoạch khi xuất hiện tín hiệu đủ mạnh?
- [ ] Ai có quyền quyết định phạm vi, thứ tự backlog, mốc phát hành và xử lý rủi ro đã rõ?
- [ ] Sau kỳ kiểm tra tiếp theo, nhóm có biết sẽ **giữ, sửa hay loại** giả thuyết nào không?

Không cần dùng checklist như cổng phê duyệt cứng cho mọi ticket. Nó hữu ích nhất khi phải cân nhắc giữa một dự báo đẹp trên giấy và tình hình thực tế.

## 17. Ghi nhớ

- **Lập kế hoạch cuốn chiếu** là làm rõ phần gần theo mức cần thiết, giữ phần xa ở mức mục tiêu và giả thuyết, rồi tiếp tục bổ sung chi tiết từ bằng chứng mới.
- **Có định hướng không đồng nghĩa có đặc tả cố định:** Product Goal và ranh giới giúp nhóm tập trung, còn Product Backlog và phương án thực hiện có thể điều chỉnh.
- **Dự báo khác cam kết:** Hãy công khai dữ liệu, điều kiện, độ bất định và thời điểm xem lại; đừng trình bày phép tính trung bình như lời hứa chắc chắn.
- **Phản hồi và Increment tạo thông tin mới:** Scrum giúp kiểm tra mục tiêu và điều chỉnh backlog, Kanban giúp thấy dòng công việc, các thực hành XP giúp thay đổi phần mềm an toàn hơn.
- **Đầu tư sớm cho rủi ro khó đảo ngược:** Phụ thuộc, an toàn dữ liệu, bảo mật, kiểm định và mốc ngoài dự án vẫn cần kế hoạch từ sớm.
- **Thích nghi có kỷ luật:** Chỉ điều chỉnh khi có căn cứ, quyền quyết định và hành động tiếp theo; bảo vệ chất lượng dù phạm vi hay thứ tự thay đổi.

Khi lập kế hoạch cho một dự án Agile, hãy hỏi: **“Chúng ta cần quyết định điều gì ngay bây giờ, đã biết chắc điều gì, còn giả định nào cần kiểm chứng và khi nào kế hoạch phải được cập nhật từ thực tế?”**
