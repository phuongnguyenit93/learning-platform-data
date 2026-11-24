# Đo kết quả toàn luồng và bảo toàn khả năng thích ứng ở quy mô lớn

Ba nhóm phát triển nền tảng học trực tuyến đều báo cáo Sprint thành công. Nhóm tài khoản hoàn thành API xác thực, nhóm bài học hoàn thành giao diện, nhóm tiến độ hoàn thành cơ chế lưu dữ liệu. Mỗi nhóm đều tăng số hạng mục hoàn tất và giảm cycle time nội bộ. Nhưng học viên vẫn **không thể tiếp tục bài học từ tiến độ đã lưu**, vì hợp đồng API chưa tương thích, kiểm thử tích hợp phải chờ một môi trường dùng chung và việc mở tính năng cho người dùng còn phải qua nhiều vòng phê duyệt.

**Tối ưu từng nhóm không nhất thiết tối ưu giá trị toàn sản phẩm.** Khi nhiều nhóm cùng đóng góp vào một sản phẩm, đơn vị cần kiểm chứng không chỉ là ticket hay Increment cục bộ, mà là **dòng chảy từ nhu cầu người dùng đến khả năng hoạt động thật, kết quả sử dụng và phản hồi tiếp theo**.

Tuy nhiên, giải quyết vấn đề bằng cách tăng số lớp quản lý, chuẩn hóa mọi việc hoặc ép mọi nhóm theo một kế hoạch cố định cũng có thể gây hại. **Phối hợp ở quy mô lớn phải đồng thời bảo vệ hai khả năng: tạo kết quả end-to-end và thích ứng nhanh khi có bằng chứng mới.**

Bài học thuộc chương **Phối hợp nhiều nhóm** của mô-đun **AGILE_DEVELOPMENT**. Nội dung gắn với Agile qua phản hồi sớm, giao sản phẩm tăng dần, cải tiến liên tục; thực hành Product Goal, user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc để lựa chọn cách phối hợp phù hợp.

**Mục tiêu học tập:** Sau bài này, bạn có thể:

- Xác định **ranh giới của một dòng giá trị toàn sản phẩm** thay vì cộng cơ học báo cáo của các nhóm.
- Phân biệt **output từng nhóm, tích hợp kỹ thuật, kết quả người dùng và tác động sản phẩm**.
- Định nghĩa và diễn giải các thước đo **end-to-end lead time, throughput, cycle time, Work in Progress, Work Item Age, thời gian chờ, thời gian tới phản hồi**.
- Quan sát và giảm **phụ thuộc xuyên nhóm, hàng đợi, chuyển giao và việc tích hợp muộn**.
- Dùng **chỉ số chất lượng, độ tin cậy và guardrail** để không tăng tốc bằng cách dời lỗi về sau.
- Giữ **mục tiêu sản phẩm chung và quyền tự quản có trách nhiệm của từng nhóm** khi yêu cầu thay đổi.
- Thiết kế các vòng kiểm tra và thích ứng từ cấp nhóm, dòng giá trị tới sản phẩm mà không tạo những cuộc họp vô ích.
- Dùng ví dụ, số liệu giả định và bài tập để quyết định **nên tối ưu nút thắt nào, đo như thế nào và khi nào xem lại**.

## 1. Vì sao quy mô lớn dễ tạo “thành công cục bộ, thất bại toàn cục”?

Một nhóm có thể hoàn thành phần được giao đúng hạn trong khi sản phẩm chưa mang lại giá trị. Điều này xảy ra khi nhiều đơn vị tối ưu các chỉ số của riêng mình:

| Tín hiệu cấp nhóm | Có thể tốt ở cấp nhóm | Vấn đề có thể bị che ở cấp sản phẩm |
| --- | --- | --- |
| Số ticket hoàn thành tăng | Nhóm xử lý nhiều hạng mục hơn | Các hạng mục chưa ghép thành hành trình người dùng |
| Cycle time nhóm giảm | Một bước kỹ thuật nhanh hơn | Chờ API, bảo mật, vận hành và phê duyệt vẫn kéo dài |
| Velocity ổn định | Có ích cho planning nội bộ nếu cách ước lượng nhất quán | Story points không so được giữa các nhóm và không đo giá trị |
| Tỷ lệ kiểm thử đơn vị cao | Quy tắc cục bộ có thể được bảo vệ | Hợp đồng liên nhóm hoặc đường người dùng chưa được kiểm chứng |
| Nhiều bản triển khai thành công | Pipeline chạy nhanh và ít lỗi triển khai | Chức năng có thể vẫn tắt, không dùng được hoặc không tạo outcome |
| Mỗi nhóm đạt kế hoạch riêng | Có phối hợp trong phạm vi nhóm | Một phụ thuộc quan trọng không thuộc trách nhiệm rõ ràng của ai |

**Sai lầm cốt lõi:** Lấy đơn vị quản lý công việc làm đơn vị đo giá trị. Người học chỉ quan tâm **“Tôi có tiếp tục học đúng chỗ không?”**, không quan tâm API đã được nhóm nào đánh dấu Done.

### Một câu hỏi thay đổi cuộc thảo luận

Thay vì hỏi riêng:

> “Nhóm A đã hoàn thành bao nhiêu story trong tuần?”

Hãy bổ sung:

> “Từ lúc nhu cầu được ưu tiên đến khi học viên có thể dùng khả năng đó và chúng ta có phản hồi đáng tin, **toàn hệ thống mất bao lâu, chờ ở đâu và còn rủi ro gì?**”

Không cần bỏ chỉ số cấp nhóm. Chúng giúp chẩn đoán nguyên nhân. Nhưng **chúng phải phục vụ mục tiêu và kết quả chung**, không biến thành cuộc thi giữa các nhóm.

## 2. Xác định sản phẩm, Product Goal và dòng giá trị trước khi đo

Trước khi xây dashboard nhiều nhóm, cần làm rõ **những nhóm đang cùng phục vụ sản phẩm nào**, người dùng là ai và kết quả nào được xem là có giá trị.

### Product Goal như điểm định hướng

Trong Scrum, **Product Goal** mô tả trạng thái tương lai của sản phẩm và là mục tiêu dài hạn của Scrum Team; **Product Backlog** là danh sách có thứ tự những điều cần cải thiện sản phẩm. Nếu nhiều Scrum Team cùng làm **một sản phẩm**, Scrum Guide 2020 yêu cầu chia sẻ **một Product Goal, một Product Backlog và một Product Owner**; các nhóm cũng phải tuân thủ cùng một Definition of Done cho sản phẩm đó.

Điều này **không có nghĩa** mọi người làm một nhóm khổng lồ hay mọi quyết định kỹ thuật phải xin Product Owner. Nó giúp tránh từng nhóm tối ưu một backlog cục bộ trong khi không ai chịu trách nhiệm tổng thể về giá trị của sản phẩm chung.

### Dòng giá trị là gì?

**Dòng giá trị (value stream)** là chuỗi hoạt động và quyết định cần để biến một nhu cầu thành kết quả mà người dùng hoặc khách hàng nhận được.

Ví dụ với chức năng tiếp tục học:

~~~mermaid
flowchart LR
    A["Nhu cầu học viên"] --> B["Làm rõ outcome và quy tắc"]
    B --> C["Thiết kế và phát triển lát cắt"]
    C --> D["Tích hợp và kiểm chứng"]
    D --> E["Phát hành cho người dùng"]
    E --> F["Học viên tiếp tục học thành công"]
    F --> G["Quan sát phản hồi và thích ứng"]
~~~

Một phần có thể do nhiều nhóm cùng thực hiện; một nhóm cũng có thể tham gia nhiều phần. **Không nên mặc định mỗi bước trong sơ đồ tương ứng với một phòng ban riêng**. Nếu biến mọi bước thành một tổ chức chuyên trách, nhóm có thể vô tình tạo thêm điểm chuyển giao.

### Ba ranh giới cần thống nhất

| Ranh giới | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Sản phẩm** | Người dùng nhận một trải nghiệm thống nhất nào? | Nền tảng học trực tuyến |
| **Dòng giá trị** | Từ nhu cầu đến kết quả phải qua hoạt động nào? | Yêu cầu tiếp tục học → sử dụng thật → phản hồi |
| **Hạng mục đo** | Đơn vị nào đủ nhỏ để theo dõi nhưng vẫn có ý nghĩa? | Lát cắt end-to-end khôi phục tiến độ, không chỉ một task API |

Nếu sản phẩm chưa được định nghĩa rõ hoặc nhiều đơn vị độc lập đang cung cấp dịch vụ cho nhau, cần **xác nhận thực tế tổ chức** trước khi áp quy tắc “một sản phẩm, một backlog” theo Scrum.

## 3. Phân biệt đầu ra, tích hợp, kết quả và tác động

Ở quy mô nhiều nhóm, một yêu cầu có thể đi qua hàng chục task. Các task **không cộng lại một cách tự động thành giá trị**.

| Mức | Ví dụ | Câu hỏi quan trọng |
| --- | --- | --- |
| **Hoạt động** | Số giờ họp liên nhóm, số PR, số lần lập kế hoạch | Có đang tốn năng lực không? |
| **Output** | API xác thực, màn hình tiếp tục học, bảng tiến độ | Có tạo thành phần dự kiến không? |
| **Integrated Increment** | Hành trình đăng nhập → đọc tiến độ → tiếp tục bài hoạt động và đạt DoD | Người dùng **có thể** thực hiện tác vụ chưa? |
| **Release/exposure** | Khả năng được bật cho nhóm học viên đủ điều kiện | Người dùng có **cơ hội thực** sử dụng chưa? |
| **Outcome** | Tỷ lệ học viên quay lại đúng vị trí trong bảy ngày tăng | Hành vi và kết quả người dùng có cải thiện? |
| **Impact** | Hoàn thành khóa học bền vững hơn, ít bỏ học | Mục tiêu sản phẩm dài hạn có tiến triển? |

Một Increment **đạt Definition of Done** vẫn chưa tự chứng minh người dùng đã được tiếp xúc hay đạt outcome. Tương tự, **nhiều lần deploy** chưa chắc là nhiều lần release có ích.

### Ví dụ hiểu sai ở cấp quy mô

- Nhóm A báo **20 endpoint hoàn thành**.
- Nhóm B báo **15 màn hình hoàn thành**.
- Nhóm C báo **99% unit tests xanh**.
- Người dùng vẫn không thể quay lại đúng tiến độ.

Không có phép cộng **20 + 15 + 99%** nào hợp lệ để suy ra mức giá trị người học nhận được.

**Cách làm tốt hơn:** Xác định vài **hành trình người dùng xuyên nhóm**, kiểm chứng chúng như một Increment tích hợp và đo outcome sau sử dụng.

## 4. Lập bản đồ dòng công việc end-to-end

**Value Stream Mapping** giúp đội nhìn cả **thời gian làm việc thực sự lẫn thời gian chờ**, chứ không chỉ thời gian một nhóm đang code. Đây là một phương pháp phân tích, không nhất thiết là một framework quản lý mới.

### Các bước thực hiện

1. Chọn **một loại nhu cầu người dùng** cụ thể, ví dụ học viên tiếp tục bài dở.
2. Xác định **điểm bắt đầu** đo: lúc nhu cầu được ưu tiên, lúc nhóm cam kết phát triển hay lúc người dùng gửi yêu cầu?
3. Xác định **điểm kết thúc**: Increment đạt DoD, đã phát hành, người dùng sử dụng thành công hay đã thu đủ phản hồi?
4. Liệt kê các bước **thực tế** mà hạng mục đã đi qua, không chỉ quy trình viết trong tài liệu.
5. Ghi cả **thời gian xử lý và chờ đợi**, bao gồm chuyển giao, phê duyệt và bị chặn.
6. Xem vị trí nào tạo chờ lớn, làm lại hoặc rủi ro mà người dùng không nhận giá trị thêm.
7. Chọn **một cải tiến có thể thử** và đo lại cùng ranh giới.

### Một ví dụ timeline giả định

Đây là **số liệu minh họa**, dùng cùng một đơn vị **ngày lịch** và giả định các giai đoạn đi tuần tự:

| Hoạt động | Đang xử lý (ngày) | Chờ (ngày) |
| --- | ---: | ---: |
| Xác nhận vấn đề và mục tiêu | 2 | 0 |
| Chờ quyết định ưu tiên/đầu vào | 0 | 5 |
| Làm rõ ví dụ và thiết kế lát cắt | 4 | 0 |
| Chờ hợp đồng API liên nhóm | 0 | 6 |
| Phát triển chức năng | 3 | 0 |
| Chờ môi trường/tích hợp | 0 | 4 |
| Tích hợp, kiểm chứng end-to-end | 2 | 0 |
| Phát hành có kiểm soát | 1 | 0 |
| **Tổng đến khi có thể sử dụng** | **12** | **15** |

Tổng **end-to-end delivery lead time** theo định nghĩa trên:

\[
12+15=27\ \text{ngày lịch}.
\]

Tỷ lệ thời gian xử lý so với tổng thời gian trôi qua trong mô hình tuần tự minh họa:

\[
\frac{12}{27}\times100\%\approx44{,}4\%.
\]

Tỷ lệ chờ là khoảng **55,6%**. Đây là **flow efficiency theo một định nghĩa minh họa dựa trên thời gian**, không đồng nghĩa 44,4% thời gian công sức lao động và không phải benchmark bắt buộc cho mọi sản phẩm.

Nếu cần thêm **7 ngày quan sát** để học viên có đủ cửa sổ sử dụng và phản hồi, **time to validated feedback** từ cùng điểm bắt đầu thành **34 ngày lịch**. Hai phép đo có điểm kết thúc **khác nhau**:

- **27 ngày:** Có khả năng phát hành/sử dụng theo phạm vi đã định.
- **34 ngày:** Đủ thời gian quan sát outcome theo giả định, chưa chắc chứng minh nhân quả.

### Đừng tối ưu nhầm nút

Nếu nhóm giảm thời gian code từ 3 xuống 2 ngày nhưng vẫn chờ **15 ngày** ở các điểm chuyển giao, total lead time chỉ từ **27 xuống 26 ngày**. Trong khi đó, giảm các lần chờ hợp đồng/tích hợp có thể thay đổi lớn hơn.

**Không nên mặc định mọi thời gian chờ đều vô ích**: một bước kiểm tra pháp lý, bảo mật hoặc quan sát an toàn có thể bắt buộc. Câu hỏi là **thời gian đó có tạo kiểm soát thực, được lên kế hoạch phù hợp và có cách phản hồi nhanh hơn không**.

## 5. Những thước đo dòng công việc xuyên nhóm

Kanban cung cấp bốn phép đo dòng công việc cốt lõi có thể áp dụng khi ranh giới được thống nhất: **Work in Progress (WIP), throughput, cycle time và Work Item Age**.

| Đại lượng | Định nghĩa thực hành end-to-end | Nguy cơ nếu chỉ đo cục bộ |
| --- | --- | --- |
| **WIP** | Số hạng mục đã vào workflow chung nhưng chưa đạt mốc Done | Mỗi nhóm mở việc riêng khiến tổng tồn kho lớn |
| **Throughput** | Số hạng mục **end-to-end** hoàn thành trong kỳ theo cùng định nghĩa | Cộng task của các nhóm thành nhiều “giá trị” giả |
| **Cycle time** | Thời gian từ Started tới Done theo ranh giới đã chọn | Bỏ thời gian chờ giữa các nhóm hoặc trước tích hợp |
| **Work Item Age** | Tuổi của hạng mục **đang mở** kể từ khi bắt đầu | Việc bị kẹt chưa Done biến mất khỏi trung bình cycle time |

### Định nghĩa một đơn vị hạng mục

Giả sử một giá trị người dùng đòi:

- Nhóm A sửa hợp đồng xác thực.
- Nhóm B sửa giao diện tiếp tục học.
- Nhóm C sửa trạng thái tiến độ.

Đếm **ba task** là hợp lý cho điều phối nội bộ, nhưng nếu đang đo **throughput dòng giá trị**, có thể cần theo dõi **một lát cắt end-to-end** hoàn thành. **Không được cộng ba throughput nội bộ để tuyên bố có ba khả năng người dùng hoàn tất.**

### WIP cao không phải dấu hiệu mọi người đang hiệu quả

Nếu ba nhóm đồng thời mở 20 hạng mục xuyên nhóm nhưng phần lớn phải chờ nhau, tổng WIP tăng, thời gian chờ và chuyển ngữ cảnh có thể tăng. Dùng **WIP limit và chính sách ưu tiên giúp hạng mục gần Done hoàn tất** thường đáng thử hơn việc liên tục bắt đầu thêm việc.

Tuy vậy, WIP limit cần xét **loại công việc, rủi ro, mức hỗ trợ vận hành và năng lực thực**. Một giới hạn chung đặt tùy tiện có thể gây tắc nghẽn mới.

### Phân phối quan trọng hơn trung bình đơn độc

Ví dụ cycle time của năm lát cắt hoàn thành là **4, 5, 6, 8, 22 ngày**:

- Trung bình = (4 + 5 + 6 + 8 + 22)/5 = **9 ngày**.
- Trung vị = **6 ngày**.
- Một lát cắt mất **22 ngày** có thể chỉ ra phụ thuộc nghiêm trọng.

Mẫu năm quan sát **quá nhỏ để đặt kỳ vọng dự báo đáng tin**. Cần xem phân phối và Work Item Age của những hạng mục chưa hoàn thành, không chỉ báo cáo số trung bình đẹp.

## 6. Little's Law ở cấp dòng giá trị: dùng đúng điều kiện

Với một hệ thống dòng công việc có **ranh giới thống nhất, quan sát đủ dài và điều kiện gần trạng thái ổn định**, định luật Little thể hiện:

\[
\text{WIP trung bình}
=\text{Throughput trung bình}
\times\text{Cycle time trung bình}.
\]

Ví dụ giả định: trung bình có **18 lát cắt end-to-end đang dở**, throughput trung bình **3 lát cắt/tuần**; quan hệ tương ứng với cycle time trung bình **6 tuần**, nếu các đại lượng được đo tương thích và hệ thống đủ ổn định.

Nếu WIP giảm còn 12 mà **throughput vẫn 3/tuần**, quan hệ tương ứng **4 tuần**. Đây không phải lời hứa mọi hạng mục xong sau bốn tuần và **không chứng minh** chỉ hạ WIP limit là throughput sẽ giữ nguyên.

### Những trường hợp làm phép tính sai nghĩa

- WIP đo **task của ba nhóm**, throughput đo **story cấp sản phẩm**.
- Cycle time tính **ngày làm việc**, throughput tính trên **tuần lịch** mà không quy đổi.
- Hạng mục được chia/gộp/hủy mà không có chính sách dữ liệu nhất quán.
- Tồn kho tăng liên tục, hệ thống chưa ổn định.
- Một kỳ có quá ít mẫu hoặc thay đổi workflow giữa chừng.
- Một nhóm chuyển từ tính năng đơn giản sang migration dữ liệu rất lớn nhưng vẫn so các kỳ như nhau.

Định luật Little mô tả **quan hệ trung bình của hệ thống**, không là thước đo năng suất cá nhân hay dự báo ngày giao chính xác cho từng PBI.

## 7. Đo thời gian chờ, chuyển giao và phụ thuộc

**Phụ thuộc xuyên nhóm** là một nguyên nhân chính làm end-to-end lead time dài hơn cycle time cục bộ. Cần mô tả cụ thể phụ thuộc để tìm cách giảm, không chỉ đếm “số cuộc họp phối hợp”.

### Những loại phụ thuộc thường gặp

| Loại | Ví dụ | Phản ứng có thể thử |
| --- | --- | --- |
| **Kiến thức/quy tắc** | B chưa biết khi nào API báo lưu thành công | Ví dụ nghiệp vụ chung, hợp đồng có ngữ nghĩa rõ |
| **Thứ tự triển khai** | UI mới cần API mới có tương thích | Lát cắt dọc, contract-first, expand–migrate–contract |
| **Môi trường/tài nguyên chung** | Chỉ một môi trường tích hợp, nhóm phải xếp hàng | Môi trường thử độc lập khi khả thi, automation, lịch chia sẻ |
| **Quyết định** | Chờ người xác nhận quy tắc dữ liệu qua ba cấp | Nêu rõ quyền quyết định và điều kiện cần tham vấn |
| **Chuyên gia khan hiếm** | Một người duy nhất có thể sửa module quan trọng | Pairing, lan tỏa kiến thức, giảm điểm nghẽn |
| **Phê duyệt bắt buộc** | Kiểm soát bảo mật hoặc pháp lý thật | Làm rõ tiêu chí sớm, tự động hóa phần có thể |
| **Nhóm ngoài/supplier** | Đối tác chưa cung cấp API hoặc SLA | Contract test, rủi ro, phương án tương thích |
| **Tích hợp/hợp đồng kỹ thuật** | Hai đội hiểu khác định dạng sự kiện | Test contract, fixture và CI xuyên ranh giới |

### Bản đồ phụ thuộc đơn giản

~~~mermaid
flowchart LR
    A["Lát cắt: tiếp tục học"] --> B["Điều kiện truy cập"]
    A --> C["Đọc/ghi tiến độ"]
    A --> D["Giao diện tiếp tục"]
    B --> E["Hợp đồng API tích hợp"]
    C --> E
    D --> E
    E --> F["Kiểm thử hành trình"]
    F --> G["Increment có thể phát hành"]
~~~

Sơ đồ thể hiện **điều kiện để hoàn thành một lát cắt**, không phải danh sách cuộc họp hoặc sơ đồ tổ chức. Một vài hạng mục có thể làm song song, nhưng những điểm hợp nhất phải được kiểm chứng sớm.

### Đo phụ thuộc có trách nhiệm

Các tín hiệu hữu ích gồm:

- **Thời gian blocked** theo nguyên nhân đã định nghĩa.
- **Tuổi những quyết định còn mở**, không chỉ số email đã gửi.
- **Số lần chờ tích hợp hoặc sửa vì hiểu sai hợp đồng**.
- **Tỷ lệ lát cắt đạt Done không cần chuyển giao muộn** trong phạm vi tương tự.
- **Work Item Age tại điểm nghẽn** và mức độ tồn kho theo cột.

Đừng dùng “nhóm A có nhiều blockers gửi cho nhóm B” để xếp hạng nhóm. Nút thắt có thể do **kiến trúc, lịch phát hành, quyền hạn hoặc cách phân chia công việc**, không phải thiếu cố gắng của bên bị chờ.

## 8. Tích hợp sớm và lát cắt dọc để giảm phụ thuộc

**Lát cắt dọc (vertical slice)** là phần hành vi đủ đi từ giao diện/đầu vào tới xử lý nghiệp vụ, dữ liệu và kiểm chứng, để người dùng hoặc stakeholder có thể kiểm tra một khả năng có nghĩa. Nó khác chia hạng mục thành “làm xong backend”, “làm xong frontend”, “làm xong database” rồi tới cuối mới ghép.

### So sánh hai cách chia

| Cách chia | Ví dụ | Rủi ro/ưu điểm |
| --- | --- | --- |
| **Chia ngang theo thành phần** | Sprint 1: toàn bộ API; Sprint 2: toàn bộ UI; Sprint 3: toàn bộ kiểm thử | Dễ tạo backlog cục bộ và tích hợp muộn |
| **Chia dọc theo hành vi** | Lát cắt 1: học viên lưu và khôi phục tiến độ một bài tuyến tính; lát cắt 2: xử lý tình huống lỗi | Có cơ hội kiểm tra hành vi và tích hợp sớm |
| **Thử nghiệm kỹ thuật giới hạn** | Spike để xác minh hợp đồng lưu bền vững | Giảm bất định; không tự đồng nghĩa Increment người dùng |

Một lát cắt vẫn có thể cần nhiều nhóm hợp tác. Điểm quan trọng là **định nghĩa giá trị và mục tiêu tích hợp chung**, thay vì các nhóm chỉ chịu trách nhiệm về artifact riêng.

### Ba mức tích hợp

1. **Tích hợp mã thường xuyên:** CI phát hiện lỗi merge, build và unit/integration test.
2. **Tích hợp hợp đồng và dữ liệu:** Các API/event có ngữ nghĩa chung, tương thích và kiểm chứng được giữa producer/consumer.
3. **Tích hợp hành trình người dùng:** Một đường end-to-end có giá trị đạt Definition of Done và có thể kiểm chứng.

**CI xanh chỉ chứng minh những điều CI đang kiểm tra.** Nó không tự chứng minh quyền truy cập, tính bền vững của dữ liệu, giá trị người học hay trải nghiệm khi mất mạng.

### Ví dụ tiêu chí chấp nhận xuyên nhóm

~~~gherkin
Feature: Tiếp tục từ tiến độ đã xác nhận

  Scenario: Đọc đúng tiến độ sau khi học viên quay lại
    Given học viên A đã hoàn thành bước 4 và được xác nhận lưu
    When học viên A đăng nhập và mở lại bài học
    Then hệ thống hiển thị vị trí tiếp tục phù hợp với bước 4
    And học viên B không được truy cập dữ liệu tiến độ của A

  Scenario: Không hiểu nhầm yêu cầu đang chờ là đã lưu
    Given học viên vừa yêu cầu lưu tiến độ mới
    And dịch vụ chưa xác nhận thao tác đã hoàn tất
    When học viên xem trạng thái tiến độ
    Then hệ thống không thông báo đã lưu thành công
~~~

Ví dụ cần được Product Owner/những người hiểu nghiệp vụ xác nhận trước khi dùng làm acceptance criteria chính thức. Các test còn phải bảo vệ **trường hợp đồng thời, lỗi mạng và quyền truy cập** phù hợp với rủi ro.

## 9. Một Increment tích hợp và Definition of Done chung

Nếu nhiều Scrum Team cùng làm **một sản phẩm**, kết quả cần được xem như **một sản phẩm tích hợp**, không phải một tập các Increment không thể hoạt động cùng nhau. Scrum Guide 2020 yêu cầu những Scrum Team cùng sản phẩm tuân thủ **cùng một Definition of Done**; công việc chưa đạt DoD **không được coi là một phần Increment hoàn thành**.

### Một số rủi ro tại ranh giới nhóm

| Ranh giới | Ví dụ “Done cục bộ” | Điều phải kiểm chứng toàn sản phẩm |
| --- | --- | --- |
| **Client ↔ API** | UI và endpoint chạy riêng | Cùng hiểu nghĩa của trạng thái lưu và lỗi |
| **API ↔ cơ sở dữ liệu** | API trả thành công trong test giả lập | Đọc lại dữ liệu đúng, bền vững theo hợp đồng |
| **Đăng nhập ↔ tiến độ** | Hai service đạt unit test | Không đọc được dữ liệu tài khoản khác |
| **Triển khai ↔ vận hành** | Pipeline deploy thành công | Có quan sát, phục hồi và xử lý thay đổi dữ liệu phù hợp |
| **Sản phẩm ↔ người dùng** | Tính năng bật trên môi trường thử | Học viên thực sự có thể dùng và hiểu đúng trạng thái |

**Không nên nâng số lượng test end-to-end thành KPI tuyệt đối.** Kiểm thử ở nhiều lớp cần cân bằng giữa phản hồi nhanh, khả năng chẩn đoán và mức rủi ro. Một số kiểm tra có thể được thực hiện bằng unit/domain tests, contract tests, integration tests; chỉ các hành trình quan trọng nhất cần đi qua giao diện đầy đủ.

### Mẫu Definition of Done chung (chỉ để trao đổi)

~~~text
Với Increment của sản phẩm học trực tuyến:
  - Quy tắc nghiệp vụ và acceptance examples quan trọng được kiểm chứng.
  - Hợp đồng API và tích hợp giữa các thành phần liên quan phù hợp.
  - Quyền truy cập và dữ liệu người học được bảo vệ theo yêu cầu.
  - Không còn lỗi nghiêm trọng chưa được xử lý theo chính sách.
  - CI và kiểm thử phù hợp với rủi ro đạt.
  - Mọi thay đổi schema/API có đường chuyển đổi an toàn khi cần.
  - Có thông tin vận hành, phát hiện và xử lý sự cố phù hợp.
  - Phần Increment có thể sử dụng và đáp ứng tiêu chuẩn chung.
~~~

Đây **không phải một danh sách DoD chuẩn do Scrum Guide ban hành**. DoD thực cần tuân thủ tiêu chuẩn tổ chức/sản phẩm và được các Scrum Team cùng sản phẩm áp dụng nhất quán. Không tự tạo thêm một “DoD riêng của cấp chương trình” làm mờ tiêu chuẩn thực.

## 10. Đo chất lượng xuyên ranh giới và độ tin cậy dịch vụ

Tăng end-to-end throughput nhưng giảm chất lượng có thể chỉ là **đưa chi phí về sau**. Khi nhiều nhóm cùng xây một trải nghiệm, cần quan sát:

- **Lỗi tích hợp:** Các thành phần riêng lẻ đúng nhưng phối hợp sai.
- **Lỗi hồi quy:** Thay đổi của một nhóm phá hành vi đang dùng ở nhóm khác.
- **Lỗi lọt sau phát hành:** Người dùng phát hiện điều test nội bộ chưa bắt được.
- **Sự cố độ tin cậy:** Dịch vụ không đáp ứng đúng hoặc đủ nhanh.
- **Khả năng phục hồi:** Khi một thay đổi gây sự cố, có phát hiện và khôi phục nhanh, an toàn không?

### Tín hiệu cấp sản phẩm

| Tín hiệu | Câu hỏi quan trọng | Cách đọc có trách nhiệm |
| --- | --- | --- |
| **Defect escape/severity** | Lỗi nào chỉ được phát hiện khi đã đến người dùng? | Xem mức nghiêm trọng, mức sử dụng và nguồn báo |
| **Integration failure** | Những thay đổi nào liên tục phá hợp đồng chung? | Tìm nguyên nhân kiến trúc/quy trình, không đổ lỗi nhóm |
| **Change failure rate** | Bao nhiêu thay đổi triển khai gây suy giảm dịch vụ theo định nghĩa? | Định nghĩa thay đổi và sự cố phải ổn định |
| **Recovery time** | Khi sự cố xảy ra, mất bao lâu để khôi phục mức dịch vụ? | Xem phân phối, tác động và trường hợp đuôi dài |
| **SLI/SLO** | Dịch vụ có đáp ứng mục tiêu đo theo trải nghiệm? | SLI phải phản ánh điều người dùng thực sự nhận |
| **Rework share** | Bao nhiêu năng lực bị chiếm bởi sửa sai hoặc tích hợp lại? | Không coi mọi refactor hoặc thay đổi yêu cầu là lỗi |

### Ví dụ SLI gắn với hành trình thực

**SLI:** Tỷ lệ yêu cầu khôi phục tiến độ hợp lệ có thể trả **đúng trạng thái đã xác nhận** trong ngưỡng thời gian đã thống nhất.

**SLO:** Một mục tiêu đã được xác định cho SLI trong cửa sổ quan sát; cần có nguồn dữ liệu và tiêu chí hợp lệ rõ ràng.

Không nên chỉ dùng **HTTP 200** làm bằng chứng thành công nếu mã trạng thái ấy chỉ xác nhận đã nhận yêu cầu. Một người học có thể nhận HTTP 200 nhưng hệ thống vẫn khôi phục **sai bước**.

### Guardrail phải đi cùng outcome

Nếu phiên bản mới tăng tỷ lệ tiếp tục học nhưng đồng thời làm tăng sự cố mất dữ liệu, đội **không nên tự động mở rộng** theo chỉ số sử dụng. Có thể cần dừng, sửa hoặc giảm phạm vi phát hành theo chính sách.

**Sự cố bảo mật hoặc vi phạm quyền truy cập không thể được hợp thức hóa bằng một “error budget” còn dư.** Các ràng buộc bắt buộc không được đánh đổi lấy throughput.

## 11. Kết quả người dùng: thống nhất một metric contract xuyên nhóm

Một chỉ số outcome toàn sản phẩm có thể liên quan dữ liệu do nhiều nhóm phát ra. Nếu nhóm UI đếm “click tiếp tục”, nhóm tiến độ đếm “API success” và nhóm dữ liệu đếm “người quay lại trong bảy ngày” mà không thống nhất định nghĩa, dashboard sẽ có nhiều con số **đúng theo từng phép đếm nhưng không cùng câu hỏi**.

### Mẫu định nghĩa chỉ số

| Trường | Ví dụ thống nhất |
| --- | --- |
| **Outcome chính** | Tỷ lệ học viên tiếp tục thành công trong bảy ngày |
| **Nhóm đủ điều kiện** | Học viên có bài dở trước khi được tiếp xúc với tính năng |
| **Tử số** | Số người đủ điều kiện có ít nhất một lần khôi phục đúng và tiếp tục học trong cửa sổ |
| **Mẫu số** | Tổng số người đủ điều kiện trong cohort đã đủ thời gian quan sát |
| **Mốc bắt đầu** | Thời điểm người dùng được đưa vào cohort theo quy tắc |
| **Cửa sổ** | Bảy ngày hoàn chỉnh cho mỗi người, không tính người mới vào mẫu chưa đủ ngày |
| **Ranh giới** | Product, nền tảng, phiên bản và điều kiện chọn người dùng |
| **Nguồn** | Sự kiện tiếp xúc, kết quả khôi phục được xác minh và hoạt động học |
| **Guardrails** | Lỗi mất tiến độ, phân quyền, độ trễ, trải nghiệm người dùng mạng yếu |
| **Định nghĩa dữ liệu thiếu** | Quy tắc xử lý sự kiện trùng, đến muộn hoặc không ghi được |

Một công thức minh họa:

\[
\text{Successful Resume Rate}
=\frac{\text{Số học viên đủ điều kiện tiếp tục thành công trong 7 ngày}}
{\text{Số học viên đủ điều kiện trong cohort đầy đủ}}
\times100\%.
\]

**Đơn vị đo là người dùng**, không phải số lượt gọi API. Đếm người đã bấm nút mới rồi chỉ so với người trong control có thể gây **thiên lệch tự chọn** nếu đang thử nghiệm thay đổi trải nghiệm.

### “Một nguồn sự thật” có nghĩa gì?

Không nhất thiết dữ liệu vật lý nằm trong một cơ sở dữ liệu. Nó nghĩa là **có định nghĩa được chia sẻ, nguồn và trách nhiệm làm rõ khi phép đo mâu thuẫn**.

Nếu mỗi nhóm tự tạo một bảng có tên “active learners” nhưng khác ngưỡng hoạt động và mốc thời gian, quyết định sản phẩm có thể trở thành tranh luận về phép đếm thay vì kết quả thực.

## 12. Thiết kế telemetry và tính toàn vẹn dữ liệu xuyên nhóm

Instrumentation cần giúp đội quan sát **hành trình thật** mà không thu thập dữ liệu cá nhân không cần thiết.

### Sự kiện minh họa

| Sự kiện | Điều phải có nghĩa rõ | Sai lầm thường gặp |
| --- | --- | --- |
| **resume_feature_exposed** | Người học thực sự có cơ hội thấy chức năng | Ghi khi tải config nhưng UI không hiện |
| **resume_selected** | Người học chủ động chọn tiếp tục | Double click hoặc retry làm đếm trùng |
| **progress_save_requested** | Bắt đầu yêu cầu lưu | Nhầm yêu cầu với đã lưu |
| **progress_save_confirmed** | Lưu được xác nhận theo hợp đồng có nghĩa | Chỉ kiểm tra transport success |
| **resume_verified** | Vị trí khôi phục khớp dữ liệu tiến độ hợp lệ | Ghi khi trang mở nhưng dữ liệu chưa khớp |
| **progress_mismatch_detected** | Phát hiện sai lệch có ảnh hưởng | Không phân biệt lỗi đã xác nhận và lỗi nghi ngờ |

### Dữ liệu nối hành trình qua nhiều service

~~~json
{
  "event_name": "resume_verified",
  "event_schema_version": 1,
  "occurred_at_utc": "2026-10-12T08:30:00Z",
  "correlation_id": "illustrative-correlation",
  "pseudonymous_subject": "illustrative-subject-key",
  "product_area": "learning-progress",
  "verification_result": "matched_confirmed_progress"
}
~~~

**Payload trên hoàn toàn giả định.** Correlation ID giúp lần theo một hành trình kỹ thuật, nhưng không đồng nghĩa được phép ghi trực tiếp tài khoản, nội dung học riêng tư hoặc token. Pseudonymous ID **không tự động là dữ liệu ẩn danh hoàn toàn** nếu vẫn có thể liên kết tới người dùng; phải tuân thủ mục đích, phân quyền, lưu giữ và chính sách quyền riêng tư phù hợp.

### Khi hai nhóm ghi dữ liệu khác nhau

1. Xác định **sự kiện và hợp đồng đo** nào đang được dùng.
2. Kiểm tra xử lý retry, trùng, time zone và sự kiện đến muộn.
3. Kiểm tra phiên bản tính năng và điều kiện exposure.
4. Đối chiếu với dữ liệu test hoặc trường hợp nghiệp vụ đã biết.
5. Sửa instrumentation hoặc ghi rõ khoảng dữ liệu không đáng tin trước khi ra quyết định.

Một dashboard có thể có phép tính chính xác nhưng vẫn **sai thực tế vì sự kiện sai ngữ nghĩa**.

## 13. Phân biệt tương quan và tác động nhân quả ở quy mô lớn

Giả sử sau khi ba nhóm phát hành, tỷ lệ học viên quay lại học tăng từ **43% lên 50%**. Đây là **tăng 7 điểm phần trăm**, tương đối khoảng **16,3% so với mức 43%**. Nhưng **không thể khẳng định toàn bộ thay đổi do khả năng mới** chỉ từ hai con số trước/sau.

Những điều khác có thể xảy ra đồng thời:

- Chiến dịch nhắc học hoặc ưu đãi mới.
- Đầu năm học, kỳ thi hoặc thay đổi lịch nội dung.
- Phiên bản ứng dụng khác nhau được sử dụng ở hai giai đoạn.
- Người dùng mới có động lực khác người dùng cũ.
- Việc ghi telemetry được sửa ở cùng thời điểm.
- Một sự cố trước đó được khắc phục độc lập với tính năng.

### Các cách kiểm chứng

| Cách tiếp cận | Có ích để | Giới hạn |
| --- | --- | --- |
| **Trước/sau với bối cảnh** | Quan sát thay đổi và nêu giả thuyết | Nhiều yếu tố nhiễu |
| **Cohort/segment phù hợp** | Nhìn sự khác biệt người dùng, thiết bị, loại bài | Thiên lệch mẫu và yếu tố chưa quan sát |
| **Phỏng vấn/usability study** | Hiểu cơ chế, điều chưa rõ hoặc rào cản | Mẫu nhỏ không suy rộng về tỷ lệ |
| **A/B ngẫu nhiên khi phù hợp** | Ước lượng tác động trong phạm vi thử nghiệm hợp lệ | Cần randomization, sample size, telemetry, guardrails |
| **Canary/gradual rollout** | Giảm rủi ro và phát hiện vấn đề vận hành sớm | Không tự động là thí nghiệm nhân quả |
| **Điều tra sự cố và log kỹ thuật** | Xác định lỗi, ảnh hưởng và cách phục hồi | Chưa chứng minh outcome sản phẩm |

Không phải mọi trường hợp đều nên A/B: một lỗi đã biết gây lộ thông tin người học **cần xử lý theo chính sách an toàn**, không cố ý giữ nhóm đối chứng tiếp tục chịu lỗi để đo tác động.

### Khả năng thích ứng cần bằng chứng có giới hạn rõ

Một nhóm trưởng thành có thể kết luận: “Tính năng **có dấu hiệu** giúp người học quay lại, nhưng còn bất định về mạng yếu và ảnh hưởng của chiến dịch.” Họ sẽ ưu tiên kiểm chứng tiếp. Đây là tư duy Agile thực dụng, không phải thiếu quyết đoán.

## 14. Dự báo toàn luồng: dùng phân phối, không cộng cam kết cục bộ

Khi nhiều nhóm cùng làm một lát cắt, việc cộng **ngày ước lượng từng nhóm** thường tạo dự báo thiếu tin cậy vì:

- Có hoạt động **song song**, nên cộng tổng có thể quá dài.
- Có **hàng đợi/chuyển giao**, nên cộng thời gian làm việc có thể quá ngắn.
- Hạng mục có mức bất định không đồng đều.
- Sự cố, đổi thứ tự ưu tiên và phụ thuộc có thể thay đổi theo thời gian.
- Định nghĩa “Done” của từng nhóm khác với Increment tích hợp.

### Dùng dữ liệu throughput end-to-end có điều kiện

Giả sử một dòng giá trị giao được các lát cắt có kích thước tương đối nhất quán trong bốn tuần:

| Tuần | Lát cắt end-to-end hoàn tất |
| --- | ---: |
| 1 | 8 |
| 2 | 10 |
| 3 | 9 |
| 4 | 12 |

Thông lượng trung bình minh họa:

\[
\frac{8+10+9+12}{4}=9{,}75\ \text{lát cắt/tuần}.
\]

Nếu còn **24 lát cắt tương tự**, phép chia đơn giản:

\[
\frac{24}{9{,}75}\approx2{,}46\ \text{tuần}.
\]

**2,46 tuần không phải ngày cam kết chính xác.** Mẫu bốn tuần rất nhỏ, tính độc lập của lát cắt có thể thay đổi, backlog có thể mở rộng và phụ thuộc tích hợp có thể làm throughput biến động. Một dự báo hữu ích phải **nêu khoảng và giả định**, có thể dùng mô phỏng kịch bản hoặc Monte Carlo khi có đủ dữ liệu lịch sử thích hợp.

### Tránh cộng velocity giữa các nhóm

Nếu nhóm A hoàn thành 20 points và nhóm B 30 points, **không có cơ sở kết luận sản phẩm giao “50 points giá trị”**: story point tương đối, thang điểm có thể khác, và cả hai phần có thể cùng cần cho một hành trình người dùng.

Để dự báo toàn luồng, nên dùng **mốc Done chung, throughput end-to-end, phân phối thời gian hoàn thành, dữ liệu phụ thuộc và rủi ro**, còn velocity có thể tiếp tục là công cụ planning **nội bộ của từng đội** nếu hữu ích.

### SLE và hạng mục đang già đi

**Service Level Expectation (SLE)** trong Kanban có thể diễn đạt một kỳ vọng thời gian với độ tin cậy dựa trên dữ liệu, ví dụ:

> “Trong các lát cắt tương tự đã hoàn thành, khoảng 85% mất không quá 15 ngày từ Started tới Done, theo workflow hiện tại.”

Đây là một **mô tả lịch sử có điều kiện**, không phải bảo đảm mọi việc sẽ xong trước ngày 15. **Work Item Age** của những hạng mục đang mở giúp phát hiện nguy cơ trước khi chúng tới Done; không nên bỏ các việc đang kẹt khỏi báo cáo chỉ vì chúng chưa có cycle time cuối cùng.

## 15. Giữ một hướng sản phẩm chung, không tạo nhiều backlog cạnh tranh

Ở quy mô nhiều nhóm, mỗi team rất dễ có một danh sách “ưu tiên số 1”. Khi cùng một sản phẩm phải phục vụ nhiều mục tiêu không được làm rõ, công việc sẽ tranh năng lực chung và chuyển giao nhiều lần.

### Product Goal, Product Backlog và quyền quyết định

Trong Scrum cho **một sản phẩm do nhiều Scrum Team cùng xây**:

- **Một Product Goal** giúp các nhóm hiểu hướng tạo giá trị.
- **Một Product Backlog có thứ tự** giúp minh bạch các lựa chọn, thay vì nhiều backlog sản phẩm tranh nhau.
- **Một Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog; trách nhiệm này không biến thành hội đồng phê duyệt vô hạn.
- **Developers** chịu trách nhiệm lên kế hoạch và chất lượng thực hiện, phối hợp để tạo Increment tích hợp.
- **Scrum Master** hỗ trợ Scrum Team và tổ chức sử dụng Scrum hiệu quả, giải quyết trở ngại phù hợp.

Một công cụ có thể vẫn hiển thị **những view chuyên biệt của cùng Product Backlog**; điều quan trọng là chúng không trở thành các nguồn thứ tự ưu tiên không tương thích.

### Tách quyết định giá trị khỏi quyết định kỹ thuật

| Câu hỏi | Ai cần có trách nhiệm rõ? | Vì sao? |
| --- | --- | --- |
| Vấn đề sản phẩm nào đáng giải quyết trước? | Product Owner, có trao đổi stakeholder và Developers | Tối đa hóa giá trị, quản lý thứ tự Product Backlog |
| Sprint Goal có ý nghĩa thế nào? | Scrum Team trong Sprint Planning | Có mục tiêu cùng hướng và khả thi |
| Làm thế nào để đạt Sprint Goal? | Developers | Bảo vệ năng lực tự quản và kỹ thuật |
| Quy tắc nào phải giống nhau trong tích hợp? | Các nhóm liên quan, trong giới hạn DoD và hợp đồng chung | Tránh mâu thuẫn khi phần mềm chạy chung |
| Khi nào cần dừng phát hành vì sự cố? | Vai trò/quy trình xử lý sự cố đã được tổ chức giao quyền | An toàn, phản ứng kịp thời |
| Có nên mở rộng tính năng sau kết quả thử? | Product Owner và người có quyền theo chính sách sản phẩm, dựa trên bằng chứng | Không mặc định mọi tín hiệu tăng là an toàn |

Đừng biến nguyên tắc **cộng tác** thành “mọi quyết định đều chờ tất cả nhóm đồng ý”; ngược lại, cũng không để một cấp điều phối **quyết định hộ chi tiết kỹ thuật của Developers** khi không có lý do cần thiết.

## 16. Phối hợp mà không xóa khả năng tự quản của các nhóm

**Tự quản** không có nghĩa nhóm làm mọi thứ độc lập. Khi cùng tạo một sản phẩm, các nhóm phải đồng thuận về **ranh giới giao tiếp và chất lượng**, nhưng vẫn cần quyền chủ động về cách thực hiện trong giới hạn đó.

### Những điều thường nên thống nhất ở cấp sản phẩm

- Product Goal và ưu tiên giá trị.
- Hợp đồng API/event và định nghĩa dữ liệu quan trọng.
- Definition of Done và yêu cầu bảo mật/chất lượng áp dụng.
- Ranh giới tích hợp, tiêu chí tương thích và đường phát hành.
- Những chỉ số outcome/guardrail và cách đo đủ nhất quán.
- Quy trình ứng phó sự cố liên quan nhiều nhóm.

### Những điều có thể do nhóm tự quyết theo bối cảnh

- Chi tiết thiết kế bên trong không phá hợp đồng chung.
- Cách chia task, pairing, phương pháp kiểm thử cụ thể phù hợp DoD.
- Cách tổ chức review mã và đồng bộ kỹ thuật khi không làm nghẽn toàn luồng.
- Thử cải tiến nhỏ để giảm WIP hoặc giảm thời gian build.
- Cách trực quan hóa công việc địa phương nếu vẫn phản ánh được dòng giá trị chung.

### Nguyên tắc “ít ràng buộc nhất đủ an toàn”

Hãy đặt **ràng buộc ở nơi sự khác biệt có thể gây hại cho người dùng hoặc nhóm khác**. Không cần bắt mọi nhóm dùng chung một thiết kế lớp, một framework nội bộ hoặc thời gian họp giống hệt nhau nếu chúng không ảnh hưởng kết quả.

| Ràng buộc | Lý do thực | Không nên mở rộng thành |
| --- | --- | --- |
| Contract API có version và test tương thích | Chống phá hệ thống tích hợp | Buộc mọi nhóm dùng cùng internal class |
| Tiêu chuẩn phân quyền người học | Bảo vệ dữ liệu | Mỗi thay đổi nhỏ phải qua hội đồng thủ công |
| DoD thống nhất cho sản phẩm | Increment có chất lượng chung | Coi mọi công cụ và kỹ thuật phải hoàn toàn giống nhau |
| Một định nghĩa outcome chính | Cùng đo giá trị | Cấm các nhóm đo tín hiệu chẩn đoán khác |

**Khả năng thích ứng quy mô lớn phụ thuộc vào việc giảm số quyết định phải phối hợp**, không chỉ làm cuộc họp phối hợp nhanh hơn.

## 17. Kiến trúc và hợp đồng: giảm phụ thuộc thay vì chỉ họp nhiều hơn

Nếu mỗi thay đổi trong sản phẩm đều buộc bốn nhóm sửa đồng thời, vấn đề có thể nằm ở **ranh giới kiến trúc và quyền sở hữu thay đổi**, không chỉ do lịch họp thiếu khoa học.

### Câu hỏi thiết kế giúp giảm chi phí phối hợp

1. Một thay đổi hành vi nhỏ có phải sửa nhiều hệ thống **không liên quan**?
2. Có thể xác định **hợp đồng ổn định** giữa các thành phần, để mỗi nhóm tiến hóa bên trong mà không phá nhóm khác không?
3. Những quy tắc nghiệp vụ có bị **sao chép** ở nhiều service với ý nghĩa khác nhau?
4. Thay đổi schema/API có đường chuyển đổi tương thích không?
5. CI có thể chạy **contract tests** ở ranh giới mà không cần chờ tích hợp thủ công?
6. Có phụ thuộc nào tồn tại chỉ vì **cơ cấu đội chia theo lớp kỹ thuật**?

### Lựa chọn kỹ thuật theo nhu cầu

| Kỹ thuật | Giúp giảm điều gì? | Giới hạn |
| --- | --- | --- |
| **Consumer-driven contract test** | Phát hiện thay đổi producer phá kỳ vọng consumer | Cần quản lý version và ví dụ thực, không thay test hành trình |
| **API/schema versioning hợp lý** | Cho client và server chuyển đổi từng bước | Không cứu được thay đổi ngữ nghĩa không rõ |
| **Expand–migrate–contract** | Giảm rủi ro đổi dữ liệu giữa nhiều phiên bản | Cần kiểm tra migration, rollback/roll-forward |
| **CI tích hợp thường xuyên** | Giảm tích lũy thay đổi chưa kiểm chứng | Pipeline xanh chỉ có giá trị theo test đang chạy |
| **Feature flag có quản lý** | Tách deploy khỏi exposure, hỗ trợ rollout có kiểm soát | Flag lâu ngày không dọn gây nhánh phức tạp |
| **Tách miền rõ** | Giảm số nhóm phải cùng thay một quy tắc | Đừng chia service chỉ vì muốn “microservice” |
| **Môi trường thử có thể tạo lại** | Giảm hàng đợi chờ môi trường chung | Có chi phí vận hành và dữ liệu mẫu cần bảo vệ |

### Tránh giải pháp kỹ thuật theo mốt

Một **monolith có cấu trúc rõ, CI tốt và ranh giới module hợp lý** đôi khi giúp nhiều nhóm phát triển nhanh hơn một hệ microservice phân tán thiếu hợp đồng và năng lực vận hành. Ngược lại, sản phẩm rất lớn có yêu cầu độc lập triển khai thực sự có thể phù hợp với chia service.

**Đơn vị ra quyết định là nhu cầu và rủi ro hiện tại**, không phải số nhóm hay xu hướng công nghệ. YAGNI/KISS vẫn hữu ích ở quy mô lớn: **chỉ tổng quát hóa khi có lý do đủ rõ**, nhưng không bỏ chuẩn bảo mật, dữ liệu và khả năng tương thích.

## 18. Lập kế hoạch và phối hợp xuyên nhóm mà không nhân số nghi thức

Khi tăng số nhóm, tổ chức thường bổ sung “họp đồng bộ”, “họp đồng bộ của các cuộc họp” và nhiều tầng báo cáo. Điều này có thể giúp lộ phụ thuộc trong ngắn hạn, nhưng nếu **không giảm nguyên nhân phụ thuộc**, thời gian phối hợp vẫn tăng.

### Bốn câu hỏi cho một nhịp phối hợp

- **Điều gì cần mọi nhóm hiểu chung?** Product Goal, Increment tích hợp, tiêu chuẩn chất lượng.
- **Điều gì cần một số nhóm liên quan trao đổi?** Hợp đồng API, điểm tích hợp và những quyết định ảnh hưởng nhiều nơi.
- **Điều gì có thể cập nhật không đồng bộ?** Trạng thái công việc, dữ liệu flow, quyết định đã có lý do.
- **Điều gì đang bị chặn và ai có quyền tháo?** Phụ thuộc kỹ thuật, chất lượng, chính sách hoặc quyết định ưu tiên.

### Một mô hình trao đổi vừa đủ

| Mức | Mục đích | Cách tránh biến thành hội họp |
| --- | --- | --- |
| **Trong từng nhóm** | Kiểm tra Sprint Goal/công việc và điều chỉnh kế hoạch | Dùng workflow và mục tiêu, không đọc báo cáo từng người |
| **Những người có phụ thuộc thực** | Giải quyết hợp đồng, chia lát cắt, tích hợp | Mời đúng người, ghi quyết định và kết thúc khi đã giải quyết |
| **Cùng một sản phẩm** | Xem Product Goal, Increment, outcome, rủi ro | Tập trung kết quả người dùng, không tổng hợp slide từng nhóm |
| **Cải tiến toàn dòng** | Xem hàng đợi, DoD, sự cố, độ ổn định và nút thắt | Chọn một hoặc hai thử nghiệm có người theo dõi |

### Scrum ở quy mô nhiều nhóm

Các Scrum event như Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective **giữ mục đích gốc** cho mỗi Scrum Team. Khi nhiều nhóm cùng sản phẩm, họ cần **phối hợp để có một Increment tích hợp** và cùng hướng Product Goal; cách phối hợp cụ thể tùy sản phẩm và mức phụ thuộc.

Không nên:

- Biến Daily Scrum của Developers thành cuộc họp báo cáo của đại diện mỗi phòng ban.
- Thay Sprint Review bằng một hội nghị xem dashboard mà không thể kiểm tra sản phẩm.
- Đòi mọi team dùng một Sprint Goal giống hệt nếu công việc của họ khác nhau; cần **tương thích với Product Goal và tích hợp**.
- Cho rằng thêm một ban điều phối tự động tạo ra quyền quyết định tốt hơn.

### Framework quy mô lớn có thể hỗ trợ nhưng không phải đích đến

Một số tổ chức cân nhắc **Nexus, LeSS, SAFe hoặc mô hình riêng** để hỗ trợ tổ chức nhiều nhóm. Chúng có cấu trúc và quy ước khác nhau; không nên **trộn tên các vai trò/ceremony rồi khẳng định đó là Scrum bắt buộc**. Trước khi chọn bất kỳ cách mở rộng nào, hãy kiểm tra: **nó giảm thời gian tới Increment tích hợp và phản hồi không, hay chỉ tạo một tầng lập kế hoạch mới?**

## 19. Bảng dòng giá trị chung: nhìn việc đang già đi, không chỉ báo cáo hoàn thành

Một workflow end-to-end cần hiển thị được **việc nào đang đi tới giá trị, chờ ở đâu và có nguy cơ trễ**, ngay cả khi các nhóm quản lý task bằng công cụ khác nhau.

### Một bảng cấp dòng giá trị minh họa

~~~text
Nhu cầu đã xác định
       |
       v
Sẵn sàng cho lát cắt
       |
       v
Đang phát triển   [WIP limit theo bối cảnh]
       |
       v
Tích hợp / xác minh hợp đồng
       |
       v
Kiểm chứng hành trình và chất lượng
       |
       v
Increment Done
       |
       v
Phát hành / tiếp xúc người dùng
       |
       v
Theo dõi outcome / guardrails / học hỏi
~~~

Không nhất thiết phải tạo một cột Kanban cho mọi nhóm hay mọi công cụ. **Một lát cắt có thể có nhiều task nội bộ**, nhưng bảng chung nên trả lời “nó đang ở đâu trên đường tới giá trị?”.

### Nhìn đồng thời hạng mục Done và đang mở

Một dashboard chỉ có cycle time của những việc đã hoàn thành có thể trông ngày càng đẹp trong khi **các hạng mục khó nhất đang già đi**. Vì thế:

- Xem **Work Item Age** cho tất cả hạng mục đang mở.
- Nêu rõ trạng thái **blocked** và nguyên nhân chờ.
- Không ẩn công việc chờ nhóm khác để WIP nội bộ giảm giả.
- Xem phân phối cycle time đã hoàn thành cùng loại, không chỉ trung bình.
- Thảo luận chính sách kéo việc mới khi các hạng mục gần Done đang bị nghẽn.

### Chính sách với việc khẩn

Khi có sự cố production nghiêm trọng, tổ chức có thể cần **expedite** theo quy trình đã định. Nhưng nếu mọi stakeholder được đặt P0, hạng mục thông thường sẽ luôn bị ngắt. Cần:

1. Tiêu chí severity/rủi ro thật rõ.
2. Người có thẩm quyền xác định việc khẩn.
3. Cách thông báo **việc nào tạm dừng** và ảnh hưởng dự báo.
4. Cơ chế đưa công việc trở lại workflow sau khắc phục.
5. Học từ số lần expedite lặp lại, không đổ lỗi đội phải xử lý.

## 20. Quyết định lớn nên có vòng phản hồi ngắn, không phải kế hoạch bất biến

Ở quy mô lớn, kế hoạch thường bao gồm nhiều nhóm, ngân sách và rủi ro. Điều này không có nghĩa mọi chi tiết phải được **khóa cứng từ đầu quý**.

### Ba lớp quyết định

| Lớp | Ví dụ | Tính chất và cách xem lại |
| --- | --- | --- |
| **Định hướng sản phẩm** | Giúp học viên tiếp tục và hoàn thành bài | Có thể ổn định lâu hơn, điều chỉnh khi bằng chứng/chiến lược đổi |
| **Lựa chọn năng lực và thứ tự** | Ưu tiên sửa độ tin cậy lưu trước offline | Xem theo outcome, sự cố và cơ hội mới |
| **Cách hiện thực/lát cắt** | API contract, giao diện trạng thái, cách chia story | Điều chỉnh thường xuyên khi hiểu biết kỹ thuật thay đổi |

Định hướng dài hạn có thể tạo sự nhất quán; **chi tiết cách làm nên được mở để thích ứng** trong những ràng buộc đã thống nhất.

### Rolling-wave planning

Một cách làm là lập kế hoạch:

- **Chi tiết cho khoảng gần:** Story đủ rõ để triển khai, test, tích hợp.
- **Mức lựa chọn cho khoảng trung bình:** Capability hoặc giả thuyết giá trị, phụ thuộc và rủi ro nổi bật.
- **Mức định hướng cho khoảng xa:** Product Goal, outcome mong muốn, khả năng lớn và bất định chưa được giải quyết.

Không phải tất cả việc xa đều vô định. Với **hợp đồng pháp lý, migration khó đảo ngược hoặc yêu cầu an toàn đã biết**, có thể cần chuẩn bị sớm hơn. Nhưng đừng triển khai đầy đủ các khả năng chưa có bằng chứng chỉ vì một kế hoạch cố định dự đoán.

### Chi phí thay đổi của quyết định

| Loại quyết định | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Rẻ khi đảo ngược** | Bố trí một component nội bộ, lời nhắc UI | Chọn giải pháp vừa đủ, kiểm chứng sớm |
| **Tốn khi đổi** | Schema tiến độ, API công khai, định danh tài khoản | Làm rõ hợp đồng, phiên bản/migration và kiểm thử |
| **Rủi ro cho người dùng** | Phân quyền, bảo vệ dữ liệu, tính đúng lưu trữ | Đưa kiểm soát vào ngay, không hoãn theo YAGNI |
| **Chưa có bằng chứng nhưng rủi ro cao** | Giải quyết xung đột offline đa thiết bị | Spike giới hạn, thử nghiệm nhỏ và quyết định ưu tiên |

**Tính thích ứng không phải khả năng đổi hướng tùy tiện mỗi ngày**. Nó là khả năng thay đổi **dựa trên thông tin mới**, có kiểm chứng chất lượng, cập nhật dự báo và minh bạch chi phí cơ hội.

## 21. Cấu trúc nhóm ảnh hưởng số lượng phụ thuộc

Khi nhiều nhóm chia theo **các tầng kỹ thuật** (một nhóm UI, một nhóm API, một nhóm dữ liệu), gần như mọi tính năng người dùng đều cần chuyển qua nhiều nơi. Chia nhóm theo **năng lực phục vụ dòng giá trị** có thể giảm chuyển giao, nhưng không phải lúc nào cũng phù hợp.

### Hai mô hình cực đoan

| Cách chia | Có thể có lợi | Rủi ro |
| --- | --- | --- |
| **Theo thành phần** | Chuyên môn sâu, chuẩn hóa một năng lực dùng chung | Tính năng dọc cần nhiều nhóm, hàng đợi và phụ thuộc |
| **Theo dòng giá trị/end-to-end** | Nhóm có năng lực giao lát cắt người dùng | Có thể trùng lặp chuyên môn hoặc gặp ràng buộc chia sẻ hạ tầng |

Nhiều tổ chức cần **kết hợp**: nhóm trực tiếp tạo giá trị và nhóm cung cấp năng lực nền tảng/hạ tầng có hợp đồng dịch vụ rõ. Điều cần tránh là mọi nhóm sản phẩm **phải xin lịch một nhóm nền tảng** cho mỗi thay đổi nhỏ.

### Phân biệt chuyên môn và điểm nghẽn

Một chuyên gia bảo mật hoặc dữ liệu không nên bị loại khỏi quyết định cần thiết chỉ vì muốn giảm dependency count. Thay vào đó, nhóm có thể:

- Đưa tiêu chuẩn an toàn và ví dụ sớm vào Definition of Done/hợp đồng.
- Tự động hóa các kiểm tra lặp lại có thể tự động hóa.
- Cung cấp khả năng **self-service** với guardrails.
- Sắp xếp tư vấn sớm cho quyết định khó đảo ngược.
- Chia sẻ kiến thức để không phụ thuộc một cá nhân duy nhất.

### Khi nào nên xem lại ranh giới đội?

Nếu qua nhiều chu kỳ, **phần lớn hạng mục** bị chặn cùng một chuyển giao, mọi tiến bộ đều cần năm nhóm, chất lượng tích hợp yếu và quyền quyết định mơ hồ, có thể cần điều chỉnh cấu trúc đội hoặc kiến trúc. Đừng chỉ tăng nhịp họp phối hợp để che một vấn đề có tính hệ thống.

## 22. Một nhịp phản hồi nhiều cấp nhưng vẫn nhanh

Quy mô lớn cần những vòng phản hồi phục vụ **những câu hỏi khác nhau**, không phải cùng một báo cáo lặp ở nhiều cấp.

| Vòng phản hồi | Điều cần học | Ví dụ |
| --- | --- | --- |
| **Trong phát triển** | Build, test, contract có hỏng không? | CI, PR review, test tích hợp |
| **Trong dòng công việc** | Việc nào đang bị chặn hoặc già đi? | WIP, Work Item Age, blocked time |
| **Trên Increment** | Sản phẩm có hoạt động end-to-end và đạt DoD? | Thử hành trình lưu/khôi phục |
| **Sau phát hành** | Người dùng có thấy và sử dụng khả năng? | Exposure, task success, lỗi vận hành |
| **Outcome sản phẩm** | Người học có đạt kết quả tốt hơn? | Tiếp tục học trong bảy ngày, bỏ học, phản hồi |
| **Chiến lược và tổ chức** | Đầu tư/cấu trúc nhóm có còn hợp lý? | Time to feedback, chi phí phụ thuộc, rủi ro dài hạn |

### Nhịp xem lại gợi ý, không bắt buộc

- **Liên tục/trong ngày:** CI, cảnh báo sự cố, việc blocked nghiêm trọng.
- **Hằng ngày hoặc thường xuyên:** Điều phối trong nhóm và giữa những người có phụ thuộc thực.
- **Theo Sprint/chặng ngắn:** Kiểm tra Increment, Sprint Goal, chất lượng và phản hồi stakeholder.
- **Theo cửa sổ outcome:** Cohort đã đủ thời gian quan sát; điều chỉnh Product Backlog.
- **Theo chu kỳ chiến lược:** Xem Product Goal, ranh giới nhóm, chính sách đầu tư và năng lực tích hợp.

Không ép **mọi outcome phải chứng minh hoàn tất trước Sprint Review** nếu người dùng cần 28 ngày mới có thể quan sát. Cũng không trì hoãn sửa sự cố nghiêm trọng tới cuộc họp chiến lược tháng sau.

### “Fast feedback” khác “nhiều báo cáo”

Nếu việc kiểm chứng contract bị lỗi nhưng nhóm phải chờ ba tuần để hội đồng họp, vòng phản hồi không nhanh dù đã có 10 dashboard. Cải tiến có thể là **trao quyền xử lý gần nơi có thông tin**, giữ kiểm soát bắt buộc và ghi lại quyết định.

## 23. Chất lượng dữ liệu và Goodhart ở cấp đa nhóm

Khi số liệu được dùng để so nhóm, mỗi nhóm có động lực làm cho con số đẹp theo cách riêng. **Một thước đo bị biến thành chỉ tiêu cứng có thể không còn phản ánh hiện thực tốt**.

### Phản ứng làm số liệu đẹp nhưng giảm giá trị

| Chỉ tiêu bị ép | Hành vi có thể xảy ra | Tác hại |
| --- | --- | --- |
| Throughput mỗi nhóm phải tăng | Chia PBI thành nhiều task nhỏ để đếm | Cộng output thay vì value |
| Cycle time mỗi nhóm phải giảm | Kéo Started muộn hoặc chuyển việc chờ sang nhóm khác | Giấu thời gian chờ end-to-end |
| “Không được có blocker” | Không gắn nhãn blocked | Không ai thấy nút thắt thật |
| “Không có lỗi production” | Đổi nhãn bug thành cải tiến hoặc ngừng báo lỗi | Mất khả năng học và phục hồi |
| Velocity phải tăng | Nâng story points | Phá khả năng dự báo nội bộ |
| Phát hành càng nhiều càng tốt | Deploy thay đổi không có giá trị và tăng rủi ro | Tần suất không chứng minh outcome |
| Tỷ lệ sử dụng tính năng phải cao | Thiết kế tạo nhiều click hoặc nhắc quá mức | Trải nghiệm xấu, đo sai kết quả |

### Bảo vệ tính trung thực của phép đo

1. Thống nhất **đơn vị đo và ranh giới** trước khi so sánh.
2. Ghi **khi nào cách chia ticket, workflow hoặc instrumentation thay đổi**.
3. Không lấy **story points của các nhóm** làm thang chung.
4. Xem dữ liệu **phân phối và phân khúc có ý nghĩa**, không chỉ trung bình.
5. Không dùng số liệu flow/quality làm hệ thống **thưởng phạt cá nhân**.
6. Tổ chức có văn hóa cho phép **báo lỗi, báo blocker và nói “chưa biết”**.
7. Kết hợp số liệu với **phản hồi người dùng và giải thích của người trực tiếp làm việc**.
8. Không tạo **một composite score bí ẩn** che sự đánh đổi giữa giá trị, chất lượng và nhịp làm việc.

### So sánh các đội có công bằng không?

Nhóm xử lý sự cố nền tảng, nhóm phát triển tính năng UI và nhóm migration dữ liệu có **loại công việc, rủi ro và phân phối thời gian khác nhau**. So throughput hoặc velocity thô để xếp hạng có thể vô nghĩa.

Nên dùng số liệu đội để **hiểu và cải tiến hệ thống**, và số liệu toàn luồng để **xem kết quả sản phẩm**, không tạo giải đấu mà mỗi đội giấu blocker của mình.

## 24. Bộ câu hỏi điều hành dòng giá trị thay vì chỉ nhìn dashboard

Một buổi xem lại end-to-end có thể đi theo sáu câu hỏi:

1. **Người dùng:** Hành trình quan trọng nào đã cải thiện, nhóm người dùng nào chưa hưởng lợi?
2. **Flow:** Lát cắt nào đang già đi, đang chờ ở đâu và tác động tới time to value?
3. **Chất lượng:** Những lỗi tích hợp/sự cố nào phát sinh và mức nghiêm trọng ra sao?
4. **Phụ thuộc:** Điều gì làm nhiều nhóm phải chờ nhau; có thể giảm bằng hợp đồng, thay đổi ranh giới hay quyết định rõ hơn?
5. **Thích ứng:** Bằng chứng mới làm thay đổi Product Backlog, mục tiêu hay cách tổ chức thế nào?
6. **Hành động:** Một đến hai thử nghiệm ưu tiên, ai hỗ trợ và khi nào nhìn lại?

### Mẫu scorecard gọn theo dòng giá trị

| Góc nhìn | Câu hỏi/metric | Định hướng quyết định |
| --- | --- | --- |
| **Outcome** | Học viên có quay lại đúng tiến độ hơn? | Giữ, cải thiện, mở rộng hay dừng tính năng |
| **End-to-end flow** | Lead time, cycle time distribution, Work Item Age | Giảm hàng đợi và phụ thuộc |
| **Delivery** | Integrated Increment, release và time to feedback | Giảm lô lớn, phát hành có kiểm soát |
| **Chất lượng** | Lỗi tích hợp, lỗi dữ liệu, incident severity | Đầu tư test và phục hồi |
| **Reliability** | SLI/SLO, change failure và recovery | Cân bằng thay đổi với độ tin cậy |
| **Sustainability** | WIP, on-call load, sự cố ngoài giờ | Điều chỉnh năng lực, giảm công việc lặp |
| **Khả năng thích ứng** | Thời gian làm rõ/đổi thứ tự khi có phản hồi mới | Giảm cấp phê duyệt không cần thiết |

**Không cần phải có một cuộc họp riêng cho mỗi dòng trong bảng.** Số liệu có thể được xem trên tài liệu chung trước, dành tương tác trực tiếp cho **bất đồng, quyết định và giải quyết nút thắt**.

## 25. Case study xuyên suốt: bốn nhóm, một hành trình người học

**Bối cảnh giả định:** Một nền tảng học trực tuyến có bốn nhóm cùng đóng góp vào **một sản phẩm**:

- **Nhóm Access:** Đăng nhập và phân quyền.
- **Nhóm Learning:** Giao diện và hành trình học.
- **Nhóm Progress:** Quy tắc lưu/khôi phục và dữ liệu tiến độ.
- **Nhóm Platform:** Năng lực chung về CI, môi trường và quan sát vận hành.

Việc phân nhóm này mô tả **hiện trạng giả định cần cải tiến**, không phải cấu trúc đội được khuyến nghị cho mọi tổ chức. Ba nhóm đầu có những phụ thuộc theo lớp kỹ thuật; nhóm Platform hỗ trợ nhiều dòng công việc, có nguy cơ trở thành hàng đợi chung.

**Product Goal:** Giúp người học tiếp tục và hoàn thành nội dung đã bắt đầu mà không bị mất tiến độ hoặc hiểu sai trạng thái lưu.

### 25.1. Khi mỗi nhóm đều “xanh”

Nhóm Access triển khai xác thực mới, Learning hoàn thiện nút “Tiếp tục”, Progress có API ghi/đọc và Platform hoàn tất một pipeline mới. Các báo cáo cục bộ cho thấy lượng công việc hoàn thành tốt. Tuy nhiên:

1. UI hiểu **HTTP success** là dữ liệu đã lưu, nhưng hợp đồng của Progress mới chỉ xác nhận **đã tiếp nhận yêu cầu**.
2. Kiểm thử tích hợp đợi môi trường Platform trong một hàng đợi dùng chung.
3. Product Owner nhận phản hồi người dùng mạng yếu nhưng không có hạng mục end-to-end nào cho hành trình này.
4. Mỗi nhóm có kế hoạch riêng, trong khi bản phát hành có ích phụ thuộc vào **cả bốn**.

**Vấn đề không phải bốn nhóm chưa chăm chỉ**. Vấn đề là **đơn vị ưu tiên và hoàn tất không nối liền kết quả người dùng**, cộng với điểm chờ ở hợp đồng và tích hợp.

### 25.2. Bắt đầu từ một outcome và metric contract

Scrum Team và stakeholder thống nhất một outcome:

> Học viên có bài đang dở **tiếp tục được từ tiến độ đã xác nhận** trong cửa sổ bảy ngày, với tỷ lệ lỗi lưu và truy cập trái phép không vượt tiêu chuẩn chất lượng.

Họ làm rõ cohort đủ điều kiện, sự kiện khôi phục thành công và giới hạn bảo mật. Đây là **kết quả sản phẩm**, không phải “nút UI nhận click”.

Họ cũng tạo một số ví dụ nghiệp vụ chung:

~~~gherkin
Feature: Tiếp tục học đáng tin cậy

  Scenario: Đọc lại đúng dữ liệu đã lưu
    Given học viên A có tiến độ bước 4 đã được xác nhận
    When học viên A mở lại bài trên cùng tài khoản
    Then vị trí khôi phục phù hợp với tiến độ bước 4

  Scenario: Trạng thái lưu chưa được xác nhận
    Given yêu cầu lưu tiến độ đang chờ kết quả
    When học viên xem màn hình trạng thái
    Then hệ thống không tuyên bố dữ liệu đã lưu thành công

  Scenario: Bảo vệ quyền truy cập
    Given học viên A có dữ liệu tiến độ riêng
    When học viên B cố truy cập tiến độ của A
    Then hệ thống từ chối truy cập trái phép
~~~

### 25.3. Lập value stream map và tìm nút thắt

Nhóm sử dụng ví dụ **27 ngày tới bản phát hành có thể dùng** ở mục 4:

| Thành phần thời gian | Trước cải tiến | Nguồn vấn đề chính |
| --- | ---: | --- |
| Thời gian xử lý thực | 12 ngày | Thiết kế, phát triển, tích hợp, phát hành |
| Chờ thứ tự ưu tiên | 5 ngày | Câu hỏi chưa có đường quyết định |
| Chờ hợp đồng API | 6 ngày | Hai nhóm hiểu khác trạng thái |
| Chờ tích hợp | 4 ngày | Môi trường dùng chung là nút thắt |
| **Tổng lead time** | **27 ngày** | 12 ngày xử lý + 15 ngày chờ |

Nếu chỉ yêu cầu nhóm Learning code nhanh hơn 1 ngày, tác động end-to-end rất hạn chế. Nhóm chọn **giảm thời gian chờ hợp đồng và tích hợp**, đồng thời giữ kiểm chứng quyền truy cập và dữ liệu.

### 25.4. Thiết kế một lát cắt và một cách phối hợp tốt hơn

Đội chọn một lát cắt có thể dùng:

> “Học viên đã đăng nhập lưu một bước hoàn thành, được xác nhận đúng trạng thái và khôi phục khi quay lại.”

Các thay đổi:

- Product Owner cùng Developers làm rõ **kết quả và ưu tiên trong cùng Product Backlog**.
- Nhóm liên quan thống nhất **ngữ nghĩa của trạng thái accepted/pending/confirmed** bằng ví dụ và contract tests.
- Learning và Progress ghép cặp ở điểm tích hợp thay vì chờ xong toàn bộ code.
- Platform giảm nút thắt môi trường bằng một phương án test phù hợp, không tự tạo framework lớn chưa cần.
- Cùng kiểm tra **Definition of Done và một Increment tích hợp**.
- Có **feature flag/rollout có kiểm soát** nếu phù hợp rủi ro và khả năng phát hành.
- Các nhóm giữ quyền quyết định nội bộ về chi tiết hiện thực không phá hợp đồng.

### 25.5. Dữ liệu sau một số chu kỳ (giả định)

Giả sử sau thay đổi nhóm quan sát được các kết quả:

| Tín hiệu | Trước | Sau | Cách diễn giải thận trọng |
| --- | ---: | ---: | --- |
| Lead time end-to-end của lát cắt tương tự | 27 ngày | 20 ngày | Có dấu hiệu giao giá trị nhanh hơn theo cùng ranh giới |
| Tổng thời gian xử lý trong mô hình | 12 ngày | 12 ngày | Không cần ép thời gian code giảm để cải thiện dòng |
| Tổng thời gian chờ | 15 ngày | 8 ngày | Nút thắt chuyển giao có dấu hiệu giảm |
| Chờ hợp đồng API | 6 ngày | 2 ngày | Làm rõ sớm có thể giúp giảm chờ |
| Chờ môi trường tích hợp | 4 ngày | 1 ngày | Khả năng thử sớm được cải thiện |
| Chờ ưu tiên/đầu vào | 5 ngày | 5 ngày | Một nút thắt khác vẫn còn |
| Tỷ lệ học viên tiếp tục thành công | 43% | 48% | Cần kiểm tra cohort, nguồn dữ liệu và yếu tố đồng thời |
| Lỗi tích hợp được xác nhận sau phát hành | 7 | 4 | Xem severity và mức sử dụng trước khi kết luận |

Phép tính mới:

\[
12+(5+2+1)=20\ \text{ngày}.
\]

Giả sử các giai đoạn vẫn tuần tự theo cùng cách đo, tỷ lệ xử lý so với tổng thời gian:

\[
\frac{12}{20}\times100\%=60\%.
\]

Sự cải thiện từ khoảng **44,4% lên 60% flow efficiency** trong ví dụ này **không có nghĩa Developers nhanh hơn hay bận hơn**. Nó cho thấy **ít thời gian chờ hơn** trong ranh giới được đo.

**Không suy ra quan hệ nhân quả từ một bảng trước/sau**. Cần xét loại công việc, số người dùng, dữ liệu đo, chiến dịch nhắc học, sự cố và các thay đổi khác.

### 25.6. Một rủi ro chưa được giải quyết

Chờ ưu tiên/đầu vào vẫn là **5 ngày**. Đây có thể do câu hỏi nghiệp vụ chưa được xác nhận, quy trình quyết định mơ hồ hoặc việc chờ phản hồi người dùng có lý do. Nhóm nên phân loại nguyên nhân:

- Nếu chỉ là **chờ một cuộc họp định kỳ**, có thể tạo đường quyết định linh hoạt hơn.
- Nếu đang **đợi dữ liệu người dùng quan trọng** để tránh đầu tư sai, việc chờ có thể có ích nhưng cần hạn định và lựa chọn tiếp theo.
- Nếu phải qua **kiểm soát bắt buộc**, có thể làm rõ tiêu chí sớm và giảm làm lại.

Không nên xóa một bước bảo mật hoặc tuân thủ chỉ để lead time “đẹp”.

### 25.7. Phản hồi mới và khả năng thích ứng

Sau khi dùng thật, học viên báo **không rõ trạng thái “Đang đồng bộ”**. Nhóm không nhất thiết tiếp tục làm offline multi-device như kế hoạch ban đầu; Product Owner xem lại giá trị và rủi ro, có thể ưu tiên trải nghiệm thông điệp và độ tin cậy.

Để xử lý mà không huy động cả bốn nhóm cho mọi thay đổi:

- Learning có thể điều chỉnh câu chữ/giao diện trong hợp đồng hiện hành.
- Progress chỉ tham gia nếu cần sửa ngữ nghĩa hoặc logic trạng thái.
- Platform không phải phê duyệt mọi thay đổi UI nếu không có rủi ro hạ tầng.
- Vẫn có kiểm thử và kiểm soát chất lượng cần thiết.

**Đây là khả năng thích ứng ở quy mô lớn:** Nhiều nhóm cùng hướng tới outcome, nhưng **không bắt buộc cùng di chuyển mỗi khi có một thay đổi nhỏ**.

### 25.8. Câu hỏi kết thúc case study

1. Giá trị nào chỉ xuất hiện khi các thành phần tích hợp?
2. Vì sao 12 ngày xử lý không phải vấn đề lớn nhất trong ví dụ?
3. Rủi ro nào khiến một phương án “cắt giảm mọi bước chờ” thiếu an toàn?
4. Chỉ số nào giúp thấy hạng mục **chưa Done** đang kẹt?
5. Khi người dùng phản hồi mới, Product Backlog và các quyết định kỹ thuật nên thích ứng thế nào?

## 26. Các phản mẫu khi đo và phối hợp nhiều nhóm

| Phản mẫu | Vì sao có hại? | Cách cải thiện |
| --- | --- | --- |
| **Cộng velocity nhiều nhóm** | Điểm ước lượng tương đối không cùng thang, không đo outcome | Dùng outcome và throughput end-to-end theo ranh giới |
| **Mọi nhóm đạt KPI nên sản phẩm chắc chắn đạt** | Các phần rời nhau chưa tạo hành trình dùng được | Kiểm tra Increment tích hợp và kết quả người dùng |
| **Đếm task thành throughput sản phẩm** | Ba task của một tính năng bị tính như ba kết quả | Định nghĩa đơn vị lát cắt có giá trị |
| **Mỗi nhóm một Product Goal cạnh tranh cho cùng sản phẩm** | Xung đột ưu tiên và phụ thuộc | Làm rõ sản phẩm, Product Goal và Product Backlog chung trong Scrum |
| **Xây kế hoạch rất chi tiết cho tương lai xa** | Khó điều chỉnh theo phản hồi | Rolling-wave planning, giả thuyết và mốc học |
| **Tăng người để giải quyết mọi nút thắt** | Có thể tăng giao tiếp và tồn kho | Phân tích nguồn chờ, cơ cấu đội và hợp đồng |
| **Tối ưu giờ code riêng lẻ** | Không giảm thời gian chờ lớn | Value stream map tới người dùng |
| **Định nghĩa Done khác nhau giữa các nhóm** | Không biết Increment tích hợp đã hoàn tất chưa | DoD sản phẩm chung khi cùng một sản phẩm Scrum |
| **Kiểm thử hợp đồng cuối kỳ** | Lỗi tích hợp tích lũy, làm lại lớn | Contract tests và CI sớm |
| **Phê duyệt mọi thay đổi qua nhiều cấp** | Dòng công việc chậm, tự quản mất | Rõ quyền quyết định, rủi ro và guardrails |
| **Giải quyết mọi việc bằng cuộc họp liên nhóm** | Tiêu tốn năng lực, chưa giảm phụ thuộc gốc | Thiết kế hợp đồng, giảm WIP, cải thiện kiến trúc |
| **Một bảng cấp chương trình chỉ có trạng thái xanh** | Che blocked work và Work Item Age | Nhìn cả việc đang mở và thời gian chờ |
| **Ẩn thời gian chờ ở ranh giới nhóm** | Cycle time cục bộ đẹp giả | Đo toàn luồng từ Started tới Done |
| **Dùng trung bình để hứa mốc chắc chắn** | Bỏ qua phân phối và phụ thuộc | Forecast range có điều kiện và dữ liệu đủ |
| **Coi Little's Law là công thức cam kết từng story** | Không xét điều kiện ổn định và biến thiên | Dùng như quan hệ trung bình có giới hạn |
| **SLI dựa duy nhất vào HTTP 200** | Có thể trả thành công nhưng dữ liệu sai | SLI gắn với hành vi người dùng |
| **Mở rộng release khi outcome tăng nhưng lỗi dữ liệu tăng** | Đánh đổi an toàn lấy một metric | Guardrails và quyền dừng rõ |
| **Biến mọi bug thành việc “của nhóm khác”** | Không ai bảo vệ trải nghiệm end-to-end | Sản phẩm chịu trách nhiệm tổng thể, học nguyên nhân |
| **Coi số lượng dependency là KPI xếp hạng** | Khuyến khích giấu vấn đề | Xem thời gian chờ và điều kiện hệ thống |
| **Đổi schema không có đường tương thích** | Nhiều phiên bản chạy cùng lúc có thể phá nhau | Contract và migration có kiểm soát |
| **Tách microservice vì số nhóm lớn** | Tăng vận hành, mạng và tích hợp | Chọn kiến trúc theo nhu cầu, không theo mốt |
| **Mọi nhóm phải dùng cùng chi tiết code** | Mất tính tự quản không cần thiết | Chuẩn hóa giao diện và ràng buộc quan trọng |
| **Dùng bảng xếp hạng nhóm/cá nhân** | Goodhart, giấu lỗi, cạnh tranh thay cộng tác | Đo hệ thống để cải tiến, không trừng phạt |
| **Đóng story rồi quên outcome** | Không có vòng học hỏi sau sử dụng | Theo dõi exposure, guardrail và quyết định tiếp |
| **Thấy số đẹp rồi ngừng kiểm tra dữ liệu** | Instrumentation sai dẫn tới quyết định sai | Metric contract, kiểm tra telemetry và bối cảnh |
| **Nhận mọi yêu cầu khẩn là P0** | WIP bị ngắt liên tục, mất tính dự báo | Chính sách expedite theo severity |
| **Không thay đổi tổ chức dù nút thắt lặp mãi** | Chỉ tăng nhịp họp, chi phí phối hợp vẫn cao | Xem ranh giới đội và khả năng self-service |
| **Đổi hướng sản phẩm mà không cập nhật dự báo** | Stakeholder tin vào mốc không còn hợp lý | Công khai thay đổi phạm vi, rủi ro và điều kiện |

## 27. Bài thực hành: đo toàn luồng và bảo vệ khả năng thích ứng

Các ví dụ dưới đây sử dụng **số liệu giả định**. Với mỗi bài tính, cần nêu rõ **đơn vị, mẫu số, điểm bắt đầu và điểm kết thúc**; với mỗi quyết định, cần nêu **bằng chứng, rủi ro và điều chưa biết**.

### Bài 1 — Phân biệt kết quả cục bộ và kết quả end-to-end

Ba nhóm cùng làm tính năng tiếp tục học:

1. Nhóm A hoàn thành 6 API.
2. Nhóm B hoàn thành 4 màn hình.
3. Nhóm C hoàn thành 8 bảng dữ liệu/logic.
4. Tính năng vẫn chưa thể dùng vì các hợp đồng chưa tương thích.
5. Một tuần sau, sau khi tích hợp và phát hành, học viên bắt đầu thử chức năng.

**Yêu cầu:**

- Sự kiện nào là output nội bộ?
- Tại thời điểm nào mới có **Increment tích hợp**?
- Điều gì phải xảy ra để có **outcome**?
- Vì sao không thể kết luận có “18 tính năng hoàn thành”?

**Gợi ý:** Đếm thành phần khác với đếm lát cắt có giá trị. Increment có thể được xác nhận trước khi người dùng sử dụng thật; outcome cần quan sát hành vi phù hợp.

### Bài 2 — Value stream map và flow efficiency

Một hạng mục có thời gian tuần tự theo ngày lịch:

| Bước | Thời gian |
| --- | ---: |
| Làm rõ vấn đề | 2 ngày xử lý |
| Chờ ưu tiên | 5 ngày chờ |
| Thiết kế/làm rõ | 4 ngày xử lý |
| Chờ hợp đồng API | 6 ngày chờ |
| Phát triển | 3 ngày xử lý |
| Chờ tích hợp | 4 ngày chờ |
| Tích hợp và kiểm chứng | 2 ngày xử lý |
| Phát hành | 1 ngày xử lý |

**Tính:**

1. Tổng thời gian xử lý.
2. Tổng thời gian chờ.
3. Delivery lead time.
4. Tỷ lệ thời gian xử lý/tổng thời gian.
5. Nếu giảm chờ API từ 6 xuống 2 và chờ tích hợp từ 4 xuống 1, lead time mới bao nhiêu?

**Đáp án tham khảo:** Xử lý **12 ngày**, chờ **15 ngày**, tổng **27 ngày**, flow efficiency khoảng **44,4%**; sau giảm chờ, tổng **20 ngày** và tỷ lệ xử lý **60%** theo mô hình giả định. Không tự áp dụng như mục tiêu chuẩn mọi đội.

### Bài 3 — Phân biệt lead time tới release và time to feedback

Với ví dụ trên, tính năng phát hành được sau **27 ngày**. Muốn quan sát học viên đủ bảy ngày cần thêm **7 ngày**.

**Câu hỏi:**

1. Time to validated feedback trong ví dụ là bao nhiêu?
2. Có thể gọi toàn bộ 34 ngày là “cycle time của công việc đã hoàn thành” không nếu Done = Increment đạt DoD trước release?
3. Nếu người dùng chưa thực sự tiếp xúc, bảy ngày quan sát có chứng minh outcome không?

**Đáp án gợi ý:** **34 ngày** từ cùng mốc bắt đầu tới khi đủ cửa sổ giả định. Phải phân biệt các điểm kết thúc. Có đủ bảy ngày trên lịch nhưng **không có exposure** thì vẫn không chứng minh tác động của tính năng.

### Bài 4 — Chọn đơn vị throughput end-to-end

Một PBI về tiếp tục học gồm 3 task backend, 2 task UI và 4 task kiểm thử, tất cả cần nhau để tạo một hành trình. Sau khi các task hoàn tất, hành trình mới đạt DoD.

**Yêu cầu:**

- Nếu tính throughput theo **task**, đội đã hoàn thành bao nhiêu?
- Nếu tính theo **một lát cắt có giá trị**, throughput tương ứng bao nhiêu?
- Số nào phù hợp hơn để đo **khả năng giao giá trị** trong bối cảnh này?
- Khi nào đơn vị task vẫn hữu ích cho điều phối nội bộ?

**Gợi ý:** **9 task** và **1 lát cắt end-to-end**. Không so sánh các chu kỳ nếu cách chia lát cắt thay đổi quá nhiều mà không ghi chú.

### Bài 5 — Little's Law ở cấp toàn luồng

Một workflow được giả định gần ổn định, có WIP trung bình **18 lát cắt**, throughput **3 lát cắt/tuần**.

1. Tính cycle time trung bình tương ứng.
2. Nếu WIP giảm còn 12 và throughput vẫn 3/tuần, cycle time trung bình tương ứng?
3. Nêu ba điều kiện làm phép tính không còn đáng tin.
4. Tại sao đây không phải cam kết thời gian cho từng story?

**Đáp án tham khảo:** **6 tuần**, sau đó **4 tuần**, chỉ khi cùng đơn vị, ranh giới và điều kiện ổn định đủ hợp lý. Không suy ra mọi hạng mục xong trong đúng bốn tuần.

### Bài 6 — Phân tích cycle time và việc đang kẹt

Năm lát cắt hoàn thành có cycle time **4, 5, 6, 8, 22 ngày**. Một hạng mục khác đã mở **25 ngày** và vẫn blocked.

**Yêu cầu:**

- Tính mean và median của năm lát cắt hoàn thành.
- Vì sao hạng mục 25 ngày không được cộng thẳng vào cycle time của những việc đã hoàn thành?
- Tín hiệu nào cần dùng để không bỏ quên nó?
- Nêu một hành động có thể thực hiện **trước khi** hạng mục đạt Done.

**Đáp án tham khảo:** Mean **9 ngày**, median **6 ngày**. Hạng mục chưa Done có **Work Item Age 25 ngày**; cần điều tra blocker và quyết định phối hợp, không chỉ chờ nó hoàn thành mới ghi nhận.

### Bài 7 — Dự báo thay vì cộng velocity

Hai nhóm cùng xây sản phẩm:

- Nhóm A báo 20 story points trong Sprint.
- Nhóm B báo 30 story points trong Sprint.
- Dòng end-to-end có throughput bốn tuần là **8, 10, 9, 12 lát cắt/tuần**.
- Product Backlog còn **24 lát cắt tương tự** theo phạm vi hiện tại.

**Nhiệm vụ:**

1. Vì sao không nên báo “tổng sản phẩm đạt 50 points giá trị”?
2. Tính throughput trung bình theo tuần.
3. Phép chia đơn giản 24 cho throughput cho kết quả gì?
4. Cần thêm thông tin nào để đưa ra **dự báo có điều kiện và khoảng bất định**?

**Đáp án tham khảo:** Throughput trung bình **9,75/tuần**; phép chia khoảng **2,46 tuần** nhưng không phải ngày cam kết. Cần phân phối đủ dài, độ tương đồng của hạng mục, phụ thuộc, WIP, lịch, rủi ro, thay đổi phạm vi.

### Bài 8 — Lập bản đồ phụ thuộc thay vì thêm cuộc họp

Ba nhóm liên tục phải chờ hợp đồng API, môi trường tích hợp và quyết định về trạng thái lưu.

**Hãy lập một bảng** gồm:

| Phụ thuộc | Người/nhóm liên quan | Thời gian chờ | Rủi ro | Can thiệp nên thử |
| --- | --- | --- | --- | --- |
| Ngữ nghĩa API | ... | ... | ... | ... |
| Môi trường tích hợp | ... | ... | ... | ... |
| Quy tắc trạng thái lưu | ... | ... | ... | ... |

**Yêu cầu:** Có ít nhất một biện pháp giúp **giảm nguyên nhân phụ thuộc** và một biện pháp giúp **minh bạch quyết định**. Không được chỉ trả lời “tổ chức thêm cuộc họp”.

### Bài 9 — Chọn ràng buộc chung và quyền tự chủ

Một tổ chức đề xuất buộc mọi nhóm:

1. Dùng cùng DoD cho một sản phẩm.
2. Dùng cùng cấu trúc thư mục Java.
3. Có contract test cho API dùng chung.
4. Xin ban quản lý phê duyệt mọi thay đổi UI.
5. Dùng định nghĩa outcome người học nhất quán.
6. Tự chọn cách ghép cặp/review code miễn đáp ứng chất lượng.
7. Có quy trình ứng phó rò rỉ dữ liệu rõ.

**Nhiệm vụ:** Phân loại thành **ràng buộc cần giữ, việc nên để nhóm tự quyết, việc cần xem lại theo rủi ro**. Giải thích vì sao tính tự quản không phải làm việc tùy ý và chuẩn hóa không phải điều khiển mọi chi tiết.

### Bài 10 — Chẩn đoán data quality

Nhóm UI báo 1.200 lượt click “Tiếp tục”, nhóm Progress báo 950 kết quả thành công, nhóm Analytics báo 600 người dùng hoạt động duy nhất.

**Yêu cầu:**

- Vì sao ba số này **không nhất thiết mâu thuẫn**?
- Định nghĩa nào cần hỏi trước khi vẽ một biểu đồ chuyển đổi?
- Retry, sự kiện đến muộn và người dùng dùng nhiều thiết bị làm méo số thế nào?
- Dữ liệu nào **không được thu thập vô hạn** chỉ vì muốn nối hành trình?

**Gợi ý:** Các đơn vị **lượt click, lượt thành công và người dùng duy nhất** khác nhau. Bảo vệ quyền riêng tư ngay trong thiết kế telemetry.

### Bài 11 — Tổ chức một vòng phối hợp không quan liêu

Một sản phẩm có bốn nhóm, lịch họp xuyên nhóm tổng cộng gần một ngày mỗi tuần. Hầu hết cuộc họp chỉ đọc tình trạng ticket. Vẫn có nhiều hạng mục blocked vì thiếu hợp đồng chung.

**Thiết kế lại hoạt động phối hợp**:

- Thông tin nào nên được chia sẻ không đồng bộ?
- Vấn đề nào cần người liên quan trao đổi trực tiếp?
- Khi nào Scrum Team cần kiểm tra Increment và Product Goal cùng stakeholder?
- Làm sao người khác tìm được **quyết định, lý do, trạng thái và người phụ trách**?
- Một thử nghiệm hai Sprint nào có thể đo được tác dụng?

**Giới hạn:** Không tạo vai trò phê duyệt mới hoặc thêm sự kiện chỉ để có “quy mô lớn”.

### Bài 12 — Quyết định khi outcome tăng nhưng guardrail xấu

Trong một thử nghiệm phát hành, tỷ lệ học viên tiếp tục đúng tiến độ tăng từ **43% lên 50%**, nhưng sự cố sai dữ liệu tăng và một nhóm người mạng yếu bị ảnh hưởng rõ.

**Yêu cầu:**

1. Tính thay đổi theo **điểm phần trăm** và tương đối.
2. Có thể khẳng định tính năng gây ra toàn bộ tăng trưởng không?
3. Quyết định hợp lý về rollout và Product Backlog là gì?
4. Người nào chịu trách nhiệm về ưu tiên sản phẩm, ai thực hiện kỹ thuật và ai cần tham gia xử lý sự cố?
5. Nêu tín hiệu nào chứng minh có thể mở rộng an toàn hơn sau khi sửa.

**Đáp án gợi ý:** Tăng **7 điểm phần trăm**, tương đối khoảng **16,3%**. Không bỏ qua an toàn hoặc tuyên bố nhân quả từ trước/sau; cần điều tra, kiểm soát rollout, sửa lỗi và kiểm chứng lại.

### Bài 13 — Thử nghiệm giảm thời gian chờ end-to-end

Trong hai đến bốn Sprint, nhóm muốn giảm thời gian chờ API và môi trường tích hợp.

~~~text
VẤN ĐỀ:
  Nhiều lát cắt bị blocked trước khi có Increment tích hợp.

BASELINE:
  ...

GIẢ THUYẾT:
  Nếu thống nhất hợp đồng sớm và kiểm thử tích hợp
  liên tục, thời gian chờ sẽ giảm mà lỗi không tăng.

THỬ NGHIỆM:
  ...

CHỈ SỐ CHÍNH:
  End-to-end lead time của lát cắt cùng loại.

CHỈ SỐ CHẨN ĐOÁN:
  Blocked time theo nguyên nhân, Work Item Age,
  số lỗi hợp đồng, WIP tại điểm tích hợp.

GUARDRAILS:
  Bảo mật, lỗi sau phát hành, sự cố dữ liệu,
  gánh nặng on-call và nhịp làm việc bền vững.

XEM LẠI:
  ...
~~~

**Yêu cầu:** Điền baseline, thay đổi và điều kiện xem lại; giải thích vì sao **cycle time giảm nhưng lỗi hồi quy tăng** chưa phải thành công.

### Bài 14 — Viết bản ghi quyết định sau một Sprint Review toàn sản phẩm

Các stakeholder quan sát rằng chức năng khôi phục tiến độ đã hoạt động nhưng thông báo “Đang đồng bộ” khó hiểu. Một đề xuất lớn là xây offline trên mọi thiết bị, trong khi lỗi trạng thái lưu vẫn chưa được giải quyết triệt để.

Hãy viết **bản ghi quyết định 150–250 từ** gồm:

- Product Goal và vấn đề học viên.
- Bằng chứng đã thấy; điều chưa biết.
- Rủi ro chất lượng và khả năng tiếp cận.
- Hai lựa chọn đầu tư cùng chi phí cơ hội.
- Quyết định thứ tự Product Backlog có trách nhiệm.
- Phần kỹ thuật các Developers có thể tự tổ chức.
- Tín hiệu và thời điểm xem lại.

**Điểm đánh giá:** Không tự động ưu tiên công nghệ phức tạp chỉ vì “scale”; đưa phản hồi vào vòng học hỏi và giữ ranh giới quyết định.

## 28. Checklist đo kết quả toàn luồng và giữ khả năng thích ứng

### Sản phẩm, giá trị và ranh giới đo

- [ ] Các nhóm biết **mình đang đóng góp vào sản phẩm, người dùng và Product Goal nào**.
- [ ] Ranh giới sản phẩm và **value stream** được xác định theo hành trình người dùng, không chỉ sơ đồ phòng ban.
- [ ] Nếu nhiều Scrum Team cùng làm **một sản phẩm**, trách nhiệm Product Owner, Product Goal, Product Backlog và Definition of Done được giữ nhất quán.
- [ ] **Output kỹ thuật**, Increment tích hợp, release/exposure, outcome và impact được phân biệt rõ.
- [ ] Một **lát cắt end-to-end** có nghĩa được theo dõi bên cạnh các task nội bộ.
- [ ] Có cách đo **thời gian từ nhu cầu đến giá trị**, cùng định nghĩa Started/Done hoặc release rõ ràng.
- [ ] Nếu đo **time to validated feedback**, cửa sổ quan sát và đối tượng đủ điều kiện được nêu rõ.
- [ ] Không cộng story points hoặc task của các nhóm thành “giá trị toàn sản phẩm”.

### Dòng công việc, phụ thuộc và dự báo

- [ ] WIP, throughput, cycle time và Work Item Age dùng **đơn vị và ranh giới tương thích**.
- [ ] Thời gian **chờ, blocked, chuyển giao và chờ tích hợp** được nhìn thấy, không bị ẩn trong báo cáo cục bộ.
- [ ] Đội xem những việc **đang mở và già đi**, không chỉ cycle time của việc đã Done.
- [ ] Có phân tích **phân phối, hạng mục rất chậm và độ biến thiên**, không chỉ trung bình.
- [ ] Little's Law chỉ được áp dụng khi điều kiện hệ thống và đơn vị đo phù hợp.
- [ ] SLE hoặc forecast là **kỳ vọng có điều kiện**, không cam kết chính xác giả tạo.
- [ ] Phụ thuộc được phân loại theo **kiến thức, kỹ thuật, môi trường, quyết định, chất lượng và supplier**.
- [ ] Việc phối hợp ưu tiên **giảm nguồn phụ thuộc**, không mặc định thêm người họp.
- [ ] Có chính sách **giới hạn WIP và điều phối việc khẩn**, không coi mọi yêu cầu là P0.

### Tích hợp, chất lượng và độ tin cậy

- [ ] Có **Definition of Done chung** cho sản phẩm và những tiêu chuẩn bắt buộc được bảo vệ.
- [ ] Các API/event/schema dùng chung có **hợp đồng và kiểm thử phù hợp**.
- [ ] Có kiểm chứng những **hành trình người dùng xuyên nhóm** quan trọng.
- [ ] Những thay đổi dữ liệu/API khó đảo ngược có **kế hoạch tương thích/migration**.
- [ ] CI, contract tests và kiểm thử tích hợp tạo **phản hồi sớm**.
- [ ] Lỗi tích hợp, lỗi sau phát hành và sự cố được xem theo **mức nghiêm trọng**, không chỉ tổng số.
- [ ] SLI/SLO và guardrail phản ánh **độ tin cậy người dùng nhận được**, không chỉ HTTP 200.
- [ ] Tốc độ hoặc outcome tăng **không được biện minh** cho rò rỉ dữ liệu, mất tiến độ hoặc vi phạm bảo mật.
- [ ] Quy trình xử lý sự cố có quyền hạn rõ và không phải đợi họp định kỳ.

### Quyền tự quản và khả năng thay đổi

- [ ] Product Backlog có thứ tự phản ánh **giá trị và rủi ro sản phẩm**, không chỉ áp lực riêng của từng nhóm.
- [ ] Phân biệt quyền quyết định về **giá trị, cách thực hiện và điều kiện an toàn**.
- [ ] Chỉ chuẩn hóa những ranh giới thực sự cần **khả năng tích hợp, dữ liệu và chất lượng**.
- [ ] Developers có quyền tự tổ chức thực hiện trong các ràng buộc đã rõ, không chờ duyệt mọi task.
- [ ] Những quyết định ảnh hưởng nhiều nhóm có **cơ chế tham vấn và ghi lý do** đủ nhẹ.
- [ ] Có thể điều chỉnh backlog và lát cắt khi **phản hồi người dùng hoặc rủi ro** thay đổi.
- [ ] Kế hoạch gần đủ chi tiết, kế hoạch xa nêu **giả thuyết, mục tiêu và bất định** thích hợp.
- [ ] Có xem lại **ranh giới nhóm/kiến trúc** nếu một phụ thuộc lặp lại qua nhiều chu kỳ.
- [ ] Cách phối hợp giúp người ở nhiều địa điểm/múi giờ **tiếp cận cùng thông tin và phản biện**.

### Dữ liệu, con người và cải tiến liên tục

- [ ] Metric contract có **tử số/mẫu số, cohort, cửa sổ, nguồn và quy tắc dữ liệu thiếu**.
- [ ] Telemetry được kiểm tra trùng, đến muộn, đổi schema và **quyền riêng tư**.
- [ ] Không gọi quan sát trước/sau là **bằng chứng nhân quả chắc chắn**.
- [ ] Các thử nghiệm có **guardrail và tiêu chí dừng/điều chỉnh**.
- [ ] Không dùng velocity, số commit, giờ online hoặc throughput thô để **xếp hạng cá nhân/đội**.
- [ ] Tải on-call, sự cố và làm ngoài giờ không bị giấu trong con số giao tính năng.
- [ ] Cải tiến có **giả thuyết, baseline, hành động, người hỗ trợ và thời điểm xem lại**.
- [ ] Buổi xem lại kết thúc bằng **một vài quyết định có thể thực hiện**, không chỉ dashboard nhiều màu.
- [ ] Thành công được xác định là **outcome có giá trị, chất lượng đáng tin cậy và khả năng thích ứng có thể duy trì**.

## 29. Câu hỏi ôn tập

1. Vì sao nhiều nhóm đều đạt mục tiêu nội bộ nhưng sản phẩm vẫn có thể không mang lại giá trị?
2. Dòng giá trị (value stream) khác sơ đồ tổ chức hoặc danh sách team như thế nào?
3. Khi nhiều Scrum Team cùng phát triển một sản phẩm, Product Goal, Product Backlog, Product Owner và Definition of Done cần được nhìn nhận ra sao?
4. Product Goal giúp giảm tình trạng các nhóm có ưu tiên xung đột như thế nào?
5. Output, integrated Increment, release, exposure, outcome và impact khác nhau ra sao?
6. Vì sao không thể cộng số lượng API, màn hình và test case thành một phép đo giá trị cho người học?
7. Một value stream map end-to-end nên ghi những giai đoạn và khoảng thời gian nào?
8. Vì sao thời gian chờ giữa các nhóm có thể quan trọng hơn thời gian code cục bộ?
9. Trong ví dụ 12 ngày xử lý và 15 ngày chờ, tổng lead time và tỷ lệ xử lý là bao nhiêu?
10. Vì sao flow efficiency không đồng nghĩa phần trăm thời gian một Developer đang làm việc?
11. Delivery lead time và time to validated feedback khác nhau như thế nào?
12. WIP, throughput, cycle time và Work Item Age đo điều gì trong workflow xuyên nhóm?
13. Tại sao các task của ba nhóm có thể tương ứng chỉ một lát cắt có giá trị?
14. Vì sao chỉ nhìn cycle time của những hạng mục đã Done có thể che một hạng mục bị kẹt rất lâu?
15. Little's Law phát biểu gì và những điều kiện nào cần có để áp dụng?
16. Khi WIP giảm, có thể chắc chắn throughput giữ nguyên và mọi hạng mục hoàn thành nhanh hơn không?
17. Những phụ thuộc nào thường gặp khi UI, API, dữ liệu và môi trường tích hợp do nhiều nhóm xây?
18. Làm sao phân biệt **giảm phụ thuộc** với **thêm cuộc họp để theo dõi phụ thuộc**?
19. Lát cắt dọc giúp giảm rủi ro tích hợp muộn thế nào?
20. Những lớp kiểm thử nào cần phối hợp để bảo vệ một hành trình người dùng end-to-end?
21. Tại sao CI xanh chưa đủ chứng minh Increment đã an toàn và đúng nghiệp vụ?
22. Definition of Done chung giúp hạn chế “Done cục bộ” như thế nào?
23. Những dấu hiệu chất lượng nào cần đặt cạnh throughput hoặc lead time?
24. Tại sao SLI dựa vào HTTP 200 có thể không phản ánh đúng khả năng lưu/khôi phục tiến độ?
25. Một guardrail xấu nên ảnh hưởng thế nào tới quyết định mở rộng rollout?
26. Những trường nào của metric contract giúp nhiều nhóm tính cùng một chỉ số outcome?
27. Khi nối telemetry xuyên nhiều service, cần chú ý điều gì về trùng sự kiện, thời gian và quyền riêng tư?
28. Vì sao cohort trước/sau không tự chứng minh một tính năng tạo ra toàn bộ thay đổi?
29. A/B ngẫu nhiên và canary rollout khác mục đích thế nào?
30. Tại sao cộng velocity của hai nhóm không tạo ra forecast sản phẩm đáng tin?
31. Phân phối throughput end-to-end có thể hỗ trợ dự báo như thế nào và giới hạn là gì?
32. Vì sao một phép chia backlog còn lại cho throughput trung bình không phải cam kết ngày giao?
33. Đâu là ranh giới giữa Product Owner quyết định ưu tiên sản phẩm và Developers quyết định cách thực hiện?
34. Những quy tắc nào nên thống nhất để tích hợp, và những việc nào nên giữ quyền tự chủ của nhóm?
35. Vì sao phối hợp hiệu quả ở quy mô lớn có thể cần **ít cuộc họp hơn** chứ không phải nhiều?
36. Những vấn đề nào nên được xem xét khi chọn Nexus, LeSS, SAFe hoặc cách tổ chức riêng?
37. Một bảng cấp dòng giá trị nên thể hiện những tín hiệu gì ngoài trạng thái “đã xong”?
38. Rolling-wave planning giúp giữ hướng đi dài hạn mà vẫn thích ứng với thông tin mới thế nào?
39. Khi nào cần đánh giá lại cấu trúc đội hoặc kiến trúc thay vì chỉ tăng nhịp phối hợp?
40. Vì sao tốc độ phản hồi không phải số lượng cuộc họp hoặc dashboard?
41. Goodhart's Law cảnh báo điều gì khi throughput hoặc velocity trở thành chỉ tiêu cứng?
42. Vì sao không nên dùng số lượng dependency để xếp hạng các nhóm?
43. Trong case study, hai loại thời gian chờ nào được giảm và tổng lead time thay đổi ra sao?
44. Tại sao tăng flow efficiency từ khoảng 44,4% lên 60% không chứng minh Developers làm việc nhiều giờ hơn?
45. Nếu outcome người học tăng nhưng lỗi dữ liệu tăng theo, nên chọn hành động nào?
46. Vì sao một thay đổi nhỏ về thông điệp UI không nhất thiết phải kéo cả bốn nhóm vào một kế hoạch mới?
47. Một thử nghiệm cải tiến end-to-end nên có baseline, giả thuyết và guardrail như thế nào?
48. Thông tin nào phải được chia sẻ để stakeholder hiểu **đã học gì, còn chưa biết gì và quyết định tiếp theo là gì**?
49. Làm sao phân biệt cải thiện luồng công việc thật với thay đổi cách chia ticket hoặc cách ghi dữ liệu?
50. Điều kiện nào giúp nói tổ chức đã **bảo toàn khả năng thích ứng ở quy mô lớn**, không chỉ tăng quy mô báo cáo?

**Ghi nhớ:** **Phối hợp nhiều nhóm chỉ có ý nghĩa khi người dùng nhận được kết quả toàn sản phẩm nhanh hơn và đáng tin cậy hơn.** Đừng cộng các báo cáo cục bộ để suy ra giá trị. Hãy xác định Product Goal và dòng giá trị, đo **outcome, end-to-end lead time, WIP, throughput, Work Item Age, thời gian chờ/phụ thuộc, chất lượng tích hợp và thời gian tới phản hồi**, luôn dùng ranh giới và định nghĩa dữ liệu nhất quán. Giảm chuyển giao bằng lát cắt dọc, hợp đồng rõ và kiểm thử tích hợp sớm; giữ **Definition of Done và các guardrail an toàn**; chỉ phối hợp ở nơi có phụ thuộc thực và để Developers tự chủ trong những quyết định kỹ thuật phù hợp. **Quy mô lớn không nên đồng nghĩa kế hoạch bất biến, nhiều tầng phê duyệt và nhiều cuộc họp hơn.** Một hệ thống Agile trưởng thành giữ định hướng sản phẩm chung nhưng vẫn có thể **nhận phản hồi, điều chỉnh ưu tiên, thay đổi thiết kế và giao Increment có giá trị** mà không phải huy động tất cả các nhóm cho từng thay đổi nhỏ.
