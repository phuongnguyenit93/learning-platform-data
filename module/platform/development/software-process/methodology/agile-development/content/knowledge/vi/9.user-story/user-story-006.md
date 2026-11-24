# Chia lát dọc để tạo kết quả có thể kiểm chứng

Một nhóm nhận yêu cầu: “Người học có thể tiếp tục xem video từ vị trí đã dừng”. Nhóm chia việc thành ba mục: **xây giao diện**, **viết API**, **tạo bảng lưu tiến độ**. Sau một tuần, từng mục đều có thể báo “xong”, nhưng người học vẫn không tiếp tục được bài học: giao diện chưa gọi API đúng, API chưa được tích hợp với dữ liệu thật và hành vi khôi phục chưa được kiểm tra.

Nếu nhóm chia thành một phần nhỏ hơn nhưng **đi xuyên qua các lớp cần thiết** — từ thao tác của người học đến logic nghiệp vụ, lưu trữ và phản hồi trên màn hình — họ có thể kiểm chứng một hành vi hoàn chỉnh sớm hơn. Cách chia này được gọi là **chia lát dọc (vertical slicing)**.

Trong chương **User story** của module **AGILE_DEVELOPMENT**, mục tiêu không phải đơn thuần “chia ticket nhỏ để làm nhanh”. Nhóm cần tạo ra từng phần sản phẩm có thể dùng và kiểm chứng, từ đó nhận phản hồi sớm, điều chỉnh backlog, giao sản phẩm tăng dần và cải tiến liên tục. Các thực hành Scrum, Kanban, XP và số đo dòng công việc đều hỗ trợ mục tiêu ấy.

Sau bài học này, bạn có thể:

- Phân biệt **lát dọc tạo hành vi đầu cuối** với **cắt ngang theo thành phần kỹ thuật**.
- Chọn ranh giới một lát dọc theo người dùng, tình huống, quy tắc nghiệp vụ và kết quả mong đợi.
- Tách một story lớn thành nhiều story nhỏ có giá trị, có tiêu chí chấp nhận và có thể kiểm chứng độc lập.
- Phân biệt bằng chứng **đã làm đúng** với bằng chứng **thật sự tạo giá trị**.
- Nhận diện các nguy cơ khi “chia nhỏ” bằng cách trì hoãn kiểm thử, phân quyền, tích hợp hoặc chất lượng cần thiết.
- Dùng phản hồi, backlog, Sprint Goal, WIP và các chỉ số dòng công việc để cải thiện cách chia lát.

## 1. Lát dọc là gì?

**Lát dọc (vertical slice)** là một phần chức năng nhỏ thực hiện được **một hành vi có ý nghĩa từ đầu đến cuối**, đi qua những thành phần hệ thống cần thiết cho hành vi đó. Chẳng hạn, trong một hệ thống web, lát dọc có thể bao gồm:

1. Một điểm vào cho người dùng như màn hình, nút hoặc API dành cho ứng dụng khách.
2. Kiểm tra đầu vào, phân quyền và quy tắc nghiệp vụ cần thiết.
3. Xử lý và lưu/đọc dữ liệu nếu hành vi cần dữ liệu bền vững.
4. Một kết quả mà người dùng hoặc hệ thống gọi có thể quan sát, kể cả trường hợp lỗi quan trọng.
5. Kiểm thử, tích hợp và các điều kiện chất lượng liên quan để phần đó thực sự có thể sử dụng.

Đây là cách **chia phạm vi chức năng**, không phải yêu cầu mọi story đều phải tạo đủ giao diện, backend và database mới. Nếu hành vi chỉ cần thay đổi một thành phần đã có, lát dọc có thể chỉ chạm một thành phần. Điều quan trọng là **hành vi đầu cuối hoạt động được**, chứ không phải số lượng lớp code được sửa.

Ngược lại, **lát ngang (horizontal slice)** phân chia theo bộ phận hoặc lớp kỹ thuật: “hoàn thành toàn bộ database”, “hoàn thành toàn bộ API”, “hoàn thành toàn bộ UI”. Những hạng mục này có thể là công việc kỹ thuật hợp lệ, nhưng thường **không tự mình tạo ra một kết quả người dùng có thể kiểm chứng**.

### Minh họa

~~~mermaid
flowchart LR
    subgraph Horizontal["Chia ngang: hoàn thành từng lớp"]
        direction TB
        U1["Toàn bộ UI"]
        A1["Toàn bộ API"]
        D1["Toàn bộ cơ sở dữ liệu"]
        U1 --- A1
        A1 --- D1
    end

    subgraph Vertical["Chia dọc: hoàn thành từng hành vi"]
        direction TB
        V1["Lát A: lưu và khôi phục tiến độ cơ bản"]
        V2["Lát B: đồng bộ nhiều thiết bị"]
        V3["Lát C: xử lý mất mạng"]
        V1 --> V2
        V2 --> V3
    end
~~~

Sơ đồ thể hiện **hai cách tổ chức phạm vi**, không ngụ ý hệ thống thực tế chỉ có ba lớp hay ba lát. Ở cách chia dọc, mỗi lát có những thay đổi UI/API/dữ liệu cần thiết cho chính hành vi của nó và được tích hợp trước khi xem là hoàn tất.

### Bảng so sánh

| Câu hỏi | Chia ngang theo kỹ thuật | Chia dọc theo hành vi |
| --- | --- | --- |
| Đơn vị công việc chính là gì? | Một lớp, thành phần hoặc hoạt động chuyên môn. | Một trường hợp sử dụng nhỏ từ đầu đến cuối. |
| Sau khi xong một mục, người dùng làm được gì mới? | Có thể chưa làm được gì mới. | Có thể thực hiện một hành vi có ý nghĩa trong phạm vi đã chọn. |
| Khi nào kiểm chứng tích hợp? | Dễ bị dồn về cuối sau khi các lớp hoàn tất. | Tích hợp và kiểm chứng trong từng lát. |
| Khi nào nhận phản hồi về sản phẩm? | Thường phải chờ nhiều hạng mục. | Có cơ hội nhận phản hồi sau từng phần đủ dùng. |
| Có còn các task UI/API/database không? | Thường là các mục giao hàng tách rời. | **Có**, nhưng là task hỗ trợ hoàn thành một story đầu cuối. |
| Rủi ro thường gặp | Nhiều việc báo “xong” nhưng luồng chưa chạy. | Lát được đặt tên quá nhỏ, thiếu chất lượng hoặc chưa có giá trị. |

**Phép thử đơn giản:** sau khi một lát được hoàn tất, nhóm có thể **biểu diễn một hành vi thật**, kiểm tra kết quả và giải thích ai được lợi hay chưa? Nếu câu trả lời chỉ là “đã dựng bảng dữ liệu” hoặc “API trả 200 với dữ liệu giả” thì thường chưa phải một lát tạo giá trị.

## 2. Vì sao chia lát dọc quan trọng trong Agile?

### 2.1. Phản hồi sớm kiểm tra giả định, không chỉ kiểm tra code

Mỗi story chứa nhiều giả định: người dùng có cần hành vi không, hiểu giao diện không, quy tắc nghiệp vụ có hợp lý không, hệ thống có thể triển khai an toàn không. Chia dọc cho phép kiểm tra các giả định này qua một phần chạy được, trước khi hoàn thiện toàn bộ tính năng lớn.

Ví dụ, nếu người học không tìm được vị trí nút “Học tiếp”, nhóm cần điều chỉnh điều hướng. Nếu chỉ xây xong backend trước, vấn đề tương tác này bị phát hiện quá muộn. Ngược lại, nếu mới có màn hình bấm thử mà chưa lưu tiến độ thật, nhóm chưa thể xác nhận trải nghiệm “quay lại từ vị trí đã xem” hoạt động.

### 2.2. Giảm lượng việc đang làm dở và chi phí tích hợp

Khi làm đồng thời “toàn bộ UI”, “toàn bộ API” và “toàn bộ database”, nhóm có thể tích lũy nhiều thay đổi chưa tích hợp. Bất tương thích giao diện, tên trường dữ liệu, xử lý lỗi hoặc quyền truy cập thường lộ ra khi ghép chúng lại.

Một lát dọc nhỏ thúc đẩy nhóm giải quyết tích hợp ngay trong phạm vi hẹp. Số mục công việc đang dở (*work in progress* — WIP) có thể giảm, vòng review ngắn hơn và khả năng hoàn thành thực tế được nhìn thấy sớm.

### 2.3. Tạo lựa chọn để thay đổi ưu tiên

Sau lát đầu tiên, phản hồi có thể cho thấy người dùng rất cần tiếp tục bài học trên **cùng thiết bị**, nhưng chưa cần đồng bộ qua nhiều thiết bị. Nhóm có thể trì hoãn phần đồng bộ để tập trung vào nội dung hoặc tốc độ phát video. Nếu tính năng chỉ được chia thành một gói kỹ thuật lớn, quyết định đổi hướng sẽ khó hơn.

### 2.4. Giao phần tăng trưởng một cách bền vững

Trong Scrum, **Increment** phải có thể sử dụng, tích hợp với các Increment trước và đáp ứng **Definition of Done (DoD)**. Một lát dọc là một **cách tổ chức phạm vi** có thể giúp tạo Increment; hai khái niệm không đồng nhất. Một story dọc chưa đạt DoD vẫn chưa được coi là hoàn tất, còn một Increment đã Done chưa nhất thiết được phát hành ra người dùng.

Lát dọc có ích khi nhóm duy trì cùng lúc **giá trị, tính đúng đắn và khả năng thay đổi tiếp**.

## 3. “Kết quả có thể kiểm chứng” gồm hai cấp độ

Một nhầm lẫn phổ biến là gộp **kiểm chứng hành vi đã làm đúng** và **kiểm tra giá trị thực của hành vi** thành một.

### 3.1. Kiểm chứng giải pháp hoạt động đúng (verification)

Nhóm có thể kiểm chứng:

- Người dùng đủ quyền bấm “Lưu tiến độ” thì dữ liệu được lưu chính xác.
- Mở lại bài học hiển thị đúng vị trí đã lưu trong mức sai số được thỏa thuận.
- Người dùng khác không xem hoặc ghi đè tiến độ của tài khoản không thuộc quyền mình.
- Nếu lưu không thành công, giao diện không nói sai rằng đã lưu xong.
- Thay đổi mới không làm hỏng những luồng học tập quan trọng đã tồn tại.

Đây là kiểm tra **hành vi và chất lượng đã thống nhất**, thường thể hiện bằng acceptance criteria, kiểm thử tự động, kiểm thử tích hợp và DoD.

### 3.2. Kiểm tra giải pháp có giải quyết nhu cầu (validation)

Khi phần chức năng được sử dụng trong phạm vi thử phù hợp, nhóm cần xem:

- Người học có tìm và sử dụng “Học tiếp” không?
- Họ có quay lại học trong khoảng thời gian mong đợi không?
- Việc học tiếp có giảm thời gian tìm vị trí cũ không?
- Tỷ lệ hoàn tất bài có cải thiện hay vẫn bị cản trở bởi nguyên nhân khác?

Đây là câu hỏi về **giá trị sản phẩm**. Một tính năng đạt mọi bài kiểm thử vẫn có thể không giải quyết đúng vấn đề. Để kết luận tác động, nhóm cần xét mẫu quan sát, hành vi nền và các thay đổi bối cảnh; không coi hai giai đoạn trước/sau đơn giản là bằng chứng nhân quả.

### Bảng kết nối mục tiêu với bằng chứng

| Lớp câu hỏi | Công cụ minh họa | Ví dụ bằng chứng |
| --- | --- | --- |
| **Giá trị kỳ vọng** | Product Goal, outcome statement, giả thuyết. | Người học muốn giảm công sức tìm lại bài đang xem. |
| **Hành vi của lát** | User story và acceptance criteria. | Mở lại bài tại vị trí đã lưu khi đủ quyền truy cập. |
| **Chất lượng hoàn tất** | Definition of Done, kiểm thử và vận hành. | Phần mềm tích hợp, kiểm thử trọng yếu đạt, không lộ tiến độ tài khoản khác. |
| **Hiệu quả sản phẩm** | Demo, thử với người dùng, chỉ số kết quả. | Người dùng tiếp tục học dễ hơn và quay lại bài thường xuyên hơn. |

Một lát dọc nên được thiết kế sao cho **bước kiểm chứng kỹ thuật có thể thực hiện ngay** và **bước kiểm chứng giá trị có cách thu tín hiệu phù hợp khi được sử dụng**.

## 4. Từ story lớn đến những lát dọc nhỏ: quy trình thực hành

Không có một công thức chia story đúng cho mọi hệ thống. Quy trình sau giúp nhóm trao đổi với Product Owner, người dùng và các chuyên môn liên quan để tìm những phần nhỏ nhưng có ý nghĩa.

~~~mermaid
flowchart TD
    A["1. Làm rõ người dùng và kết quả mong đợi"] --> B["2. Vẽ hành trình/thao tác đầu cuối"]
    B --> C["3. Tìm luồng đơn giản nhất có giá trị"]
    C --> D["4. Cắt theo biến thể, quy tắc, dữ liệu hoặc nhóm người dùng"]
    D --> E["5. Viết tiêu chí chấp nhận và ràng buộc chất lượng"]
    E --> F{"Có thể chạy, kiểm chứng và tạo giá trị?"}
    F -->|Chưa| G["Điều chỉnh ranh giới hoặc kết hợp lát"]
    G --> C
    F -->|Có| H["6. Sắp thứ tự backlog theo mục tiêu và rủi ro"]
    H --> I["7. Hoàn thành, lấy phản hồi và chia tiếp nếu cần"]
    I --> A
~~~

### Bước 1 — Mô tả vấn đề và kết quả, đừng mặc định giải pháp

Bắt đầu bằng câu hỏi:

> “Ai gặp trở ngại gì, và kết quả nào chứng minh họ được hỗ trợ tốt hơn?”

Ví dụ: “Người học bỏ dở video phải tự tìm lại đoạn đang xem; chúng ta muốn họ tiếp tục học nhanh mà không dò lại nội dung.”

Đừng bắt đầu ngay bằng danh sách “tạo bảng progress, thêm API, thêm nút” vì đó là **công việc triển khai**, chưa chỉ ra kết quả của người học.

### Bước 2 — Vẽ hành trình người dùng từ đầu đến cuối

Một hành trình cơ bản có thể gồm:

1. Người học mở bài đã được cấp quyền.
2. Xem một đoạn video.
3. Tạm dừng hoặc rời bài.
4. Hệ thống lưu vị trí xem.
5. Người học quay lại.
6. Hệ thống khôi phục đúng vị trí đã lưu và phản hồi rõ ràng.

Từng bước là **hoạt động trong hành trình**; không nên tự động biến từng bước thành một story độc lập. Nếu chỉ làm “lưu tiến độ” mà chưa có cách khôi phục, người học có thể chưa nhận giá trị trọn vẹn.

### Bước 3 — Chọn một luồng mỏng nhất có giá trị

Lát đầu tiên có thể giới hạn:

- Chỉ dành cho người đã đăng nhập.
- Một bài video mà người học có quyền xem.
- Thiết bị có kết nối mạng tại thời điểm lưu/đọc.
- Khôi phục vị trí đã lưu ở lần mở bài sau.
- Có trạng thái rõ khi chưa từng lưu hoặc lưu thất bại.

Giới hạn về **phạm vi hỗ trợ** giúp lát nhỏ; các điều kiện đúng đắn và an toàn quan trọng vẫn phải được đáp ứng.

### Bước 4 — Tách các biến thể cho các lát kế tiếp

Sau luồng cơ bản, có thể cân nhắc:

- Học tiếp trên thiết bị khác.
- Đồng bộ khi mất mạng rồi kết nối lại.
- Xem danh sách các bài đang học dở.
- Chọn giữa nhiều vị trí lưu nếu người học mở cùng bài trên nhiều thiết bị.

Mỗi lát tiếp theo cần đặt câu hỏi: **người dùng đạt được khả năng mới nào, và nhóm kiểm chứng điều đó ra sao?**

### Bước 5 — Xác định acceptance criteria và DoD

Acceptance criteria mô tả các trường hợp chức năng; DoD là tiêu chuẩn chất lượng chung mà phần hoàn tất phải đáp ứng. Không dồn mọi trường hợp nâng cao vào lát đầu tiên, nhưng cũng không bỏ các ràng buộc không thể trì hoãn như phân quyền hay tính đúng đắn dữ liệu.

### Bước 6 — Sắp thứ tự để giảm rủi ro và học sớm

Lát đầu thường là luồng có tần suất cao, ít phụ thuộc và tạo giá trị dễ kiểm tra. Tuy nhiên, nếu rủi ro lớn nhất là **khả năng lưu dữ liệu chính xác ở tải thực tế**, nhóm có thể ưu tiên một thử nghiệm kỹ thuật ngắn trước hoặc trong lát đầu để giảm rủi ro.

### Bước 7 — Hoàn thành và kiểm tra lại kế hoạch

Sau khi demo hoặc phát hành trong phạm vi thích hợp, nhóm quan sát hành vi và quyết định: giữ nguyên, sửa, mở rộng hay bỏ các lát còn lại. **Sơ đồ lát dọc là kế hoạch có thể thay đổi**, không phải cam kết phải xây mọi biến thể từ ngày đầu.

## 5. Các mẫu chia lát dọc thường dùng

Có thể chia một story lớn theo **phạm vi hành vi**, **quy tắc nghiệp vụ**, **nhóm người dùng**, **dữ liệu**, **kênh sử dụng** hoặc **tình huống cần xử lý**. Các mẫu dưới đây là gợi ý để tạo một lát đầu cuối; chúng không phải bước tuần tự bắt buộc.

| Mẫu chia | Story lớn | Lát đầu minh họa | Lát tiếp theo có thể cân nhắc |
| --- | --- | --- | --- |
| **Theo thao tác đầu cuối** | Quản lý toàn bộ lịch hẹn. | Xem giờ trống và đặt một lịch hợp lệ. | Đổi lịch, hủy lịch, nhắc lịch. |
| **Theo quy tắc nghiệp vụ** | Áp dụng mọi loại giảm giá. | Áp dụng một mã giảm giá phần trăm theo điều kiện rõ. | Mã giá trị cố định, giới hạn mỗi người, kết hợp khuyến mãi. |
| **Theo nhóm người dùng** | Mọi vai trò xem báo cáo. | Giáo viên xem báo cáo lớp mình được phân quyền. | Quản trị viên xem nhiều lớp, người học xem tiến độ cá nhân. |
| **Theo biến thể dữ liệu** | Nhập mọi định dạng danh sách học viên. | Nhập tệp CSV với bộ cột đã thống nhất và báo lỗi hợp lệ. | XLSX, ánh xạ cột tùy chỉnh, xử lý tệp lớn. |
| **Theo kênh truy cập** | Đặt lịch trên mọi nền tảng. | Đặt lịch qua web cho người dùng đã đăng nhập. | Ứng dụng di động hoặc kênh hỗ trợ khác. |
| **Theo khả năng tìm kiếm** | Tìm kiếm nâng cao. | Tìm theo từ khóa chính và thấy kết quả phù hợp. | Lọc đa điều kiện, gợi ý, sắp xếp đặc thù. |
| **Theo mức độ tự động hóa** | Đề xuất khóa học tự động. | Chọn danh sách gợi ý theo một quy tắc rõ và có thể đánh giá. | Mô hình gợi ý phức tạp khi có bằng chứng cần thiết. |
| **Theo kết quả/đầu ra** | Xuất mọi loại báo cáo. | Xuất một loại báo cáo có dữ liệu đúng và quyền phù hợp. | Mẫu báo cáo khác và cấu hình tùy biến. |

Một mẫu chỉ thực sự tạo **lát dọc** khi hoàn thành được hành vi từ điểm bắt đầu đến kết quả. Ví dụ, “chỉ tạo bảng dữ liệu cho mã giảm giá phần trăm” vẫn là nhiệm vụ kỹ thuật dù áp dụng mẫu **theo quy tắc nghiệp vụ**.

### 5.1. Luồng cơ bản trước, biến thể sau — với giới hạn rõ ràng

Nhóm thường chọn **happy path** đầu tiên: trường hợp hợp lệ, phổ biến, có giá trị. Nhưng không được hiểu thành “bỏ hết lỗi và kiểm soát quyền truy cập”.

Trong tính năng đặt lịch, luồng cơ bản vẫn phải kiểm tra **khung giờ còn chỗ tại thời điểm xác nhận**, không cho phép đặt trùng nếu nghiệp vụ cấm và phản hồi đúng khi có lỗi. Một tính năng đặt lịch thỉnh thoảng tạo lịch trùng không phải “phiên bản đủ dùng” chỉ vì giao diện đơn giản.

Có thể trì hoãn **biến thể nâng cao** như đặt lịch theo nhóm nhiều người hoặc tùy chỉnh nhắc lịch; không trì hoãn điều kiện đúng đắn của hành vi đang cung cấp.

### 5.2. Quy tắc nghiệp vụ đơn giản trước

Một hệ thống tính phí có thể hỗ trợ nhiều quy tắc thuế, khuyến mại và đổi trả. Nhóm có thể bắt đầu bằng một trường hợp đã được doanh nghiệp cho phép triển khai, với cách tính chính xác và đủ kiểm soát. Các biến thể được thêm khi thực sự cần.

Nhưng nếu một quy tắc pháp lý áp dụng ngay cho **mọi giao dịch** ở phạm vi dự kiến, không được “để Sprint sau” rồi cho người dùng thật giao dịch sai.

### 5.3. Một nhóm người dùng trước

Nếu một nền tảng có học viên, giảng viên và quản trị viên, nhóm có thể làm trước hành vi tạo giá trị cho một nhóm. Điều này giúp giảm số trường hợp giao diện và phân quyền phải triển khai.

**Phân quyền của nhóm đầu tiên vẫn cần đúng.** “Chỉ hỗ trợ giảng viên trong giai đoạn đầu” không đồng nghĩa mọi tài khoản được phép xem dữ liệu giảng viên.

### 5.4. Một tích hợp hoặc định dạng trước

Khi sản phẩm cần xuất dữ liệu ra nhiều hệ thống, có thể bắt đầu với một định dạng có người sử dụng và kiểm chứng rõ. Hệ thống cần xử lý lỗi, dữ liệu sai và quyền truy cập theo phạm vi hỗ trợ. Không nên chọn một định dạng chỉ vì dễ làm nếu người dùng mục tiêu không sử dụng được.

### 5.5. Từ thủ công có kiểm soát tới tự động khi phù hợp

Ở giai đoạn khám phá, một thao tác nội bộ thủ công có thể là cách nhanh để kiểm chứng giá trị trước khi xây tự động hóa lớn. Tuy nhiên, nếu phần đó là sản phẩm sử dụng thật, nhóm phải minh bạch giới hạn, có năng lực vận hành và bảo vệ dữ liệu. Cách tiếp cận này gần với tư duy MVP, nhưng **không biến một task thủ công tùy ý thành Increment đã Done**.

### 5.6. Lát dọc không đồng nghĩa chỉ làm “mặt trước”

Một prototype bấm được giúp nhóm kiểm tra giao diện; nó chưa chắc là lát sản phẩm có thể sử dụng thật. Nếu story hứa “người học có thể lưu và xem lại tiến độ”, lát đầu phải có cách lưu và khôi phục đáng tin cậy theo phạm vi đã nêu. Không báo story Done chỉ dựa trên dữ liệu giả, trừ khi story ngay từ đầu có mục tiêu là **thử nghiệm nguyên mẫu**, với kết quả học hỏi và tiêu chí hoàn thành riêng.

## 6. Ví dụ xuyên suốt: chia tính năng “Học tiếp” thành những lát dọc

Giả sử nhóm phát triển nền tảng học lập kế hoạch cho yêu cầu ban đầu:

> “Hệ thống phải ghi nhớ tiến độ của mọi video trên mọi thiết bị, hoạt động cả khi mất mạng, có nhắc học và báo cáo cho giáo viên.”

Đây là một phạm vi lớn chứa nhiều hành vi, điều kiện và đối tượng. Nếu làm toàn bộ trước khi lấy phản hồi, nhóm có thể xây những tính năng chưa thật sự cần.

### 6.1. Tìm mục tiêu sản phẩm

Sau trao đổi, nhóm thống nhất vấn đề cần giải quyết trước:

> **Người học đã xem dở một video khó tìm lại đoạn đang học; nhóm muốn họ có thể tiếp tục bài nhanh và có cơ sở kiểm chứng việc quay lại học có thuận tiện hơn không.**

Nhóm chưa khẳng định tính năng chắc chắn tăng tỷ lệ hoàn tất khóa học. Đó là giả thuyết cần thu bằng chứng sau khi người dùng thử.

### 6.2. Vẽ story map đơn giản

| Bước trong hành trình | Khởi đầu | Đang xem | Rời bài | Quay lại | Tiếp tục |
| --- | --- | --- | --- | --- | --- |
| **Lát V1: một bài, có mạng** | Mở bài được cấp quyền. | Phát video và thấy vị trí hiện tại. | Lưu vị trí gần nhất. | Mở lại chính bài đó. | Khôi phục vị trí đã lưu. |
| **Lát V2: nhiều bài** | Mở một trong các bài được cấp quyền. | Theo dõi vị trí từng bài. | Lưu riêng từng bài. | Xem danh sách bài đang học. | Chọn đúng bài để tiếp tục. |
| **Lát V3: đa thiết bị** | Đăng nhập trên thiết bị khác. | Có quy tắc cập nhật tiến độ. | Lưu an toàn giữa các thiết bị. | Đọc tiến độ dùng chung. | Giải quyết trường hợp tiến độ xung đột. |
| **Lát V4: mất mạng** | Mở bài có chế độ hỗ trợ. | Có cơ chế ghi nhận cục bộ nếu phù hợp. | Lưu khi offline. | Kết nối trở lại. | Đồng bộ và báo lỗi rõ khi cần. |

Các hàng là **lát ứng viên** xuyên qua hành trình; các cột là **bước trong hành vi**. Đây là một công cụ thảo luận. Tùy sản phẩm thực tế, V1 và V2 có thể gộp hoặc một lát phải tách thêm nếu vẫn quá lớn.

### 6.3. Viết story cho lát V1

> **Là** người học đã đăng nhập và có quyền xem một video, **tôi muốn** mở lại video tại vị trí đã lưu gần nhất trong lần học trước, **để** không phải tự tìm lại đoạn đang xem.

Giới hạn được thỏa thuận:

- Hỗ trợ khi thiết bị có kết nối mạng.
- Có quyền truy cập bài học theo quy tắc hiện tại.
- Vị trí được lưu cho tài khoản và bài học tương ứng, đủ để khôi phục ở lần mở sau.
- Các tình huống chưa có tiến độ hoặc lưu lỗi được phản hồi đúng.
- Chưa cam kết đồng bộ xung đột nhiều thiết bị hoặc chế độ offline trong lát này.

Câu chuyện trên gắn với **một kết quả người học thực hiện được**, thay vì danh sách công việc “tạo database, API, UI”.

### 6.4. Tiêu chí chấp nhận có thể thực thi

~~~gherkin
Feature: Tiếp tục xem video từ vị trí đã lưu

Scenario: Khôi phục vị trí của người học có quyền truy cập
  Given người học đã đăng nhập và có quyền xem video "Bài A"
  And hệ thống đã lưu vị trí 05:40 của người học cho "Bài A"
  When người học mở lại "Bài A"
  Then video có thể tiếp tục tại vị trí 05:40 trong sai số được thỏa thuận
  And màn hình thể hiện đúng tên bài học

Scenario: Chưa có vị trí được lưu
  Given người học đã đăng nhập và có quyền xem video "Bài A"
  And chưa có vị trí đã lưu cho người học và "Bài A"
  When người học mở "Bài A"
  Then video bắt đầu ở đầu bài
  And hệ thống không báo sai rằng đã khôi phục tiến độ

Scenario: Không được xem tiến độ của tài khoản khác
  Given tài khoản "Học viên B" không có quyền xem tiến độ của "Học viên A"
  When "Học viên B" yêu cầu tiến độ thuộc "Học viên A"
  Then hệ thống từ chối yêu cầu theo chính sách phân quyền
  And không tiết lộ dữ liệu tiến độ riêng của "Học viên A"

Scenario: Không thể lưu tiến độ
  Given người học đang xem video có quyền truy cập
  And thao tác lưu vị trí gặp lỗi máy chủ
  When ứng dụng nhận kết quả thất bại
  Then ứng dụng không hiển thị xác nhận lưu thành công sai sự thật
  And cung cấp phản hồi hoặc cách thử lại theo trải nghiệm đã thống nhất
~~~

Đây là ví dụ diễn đạt hành vi. Khi thực hiện thật, nhóm còn phải thống nhất điều kiện lưu (khi tạm dừng, khi rời trang, theo chu kỳ...), sai số cho phép, thời gian xử lý và cách phát lại khi vị trí gần cuối video. Không nên đưa những chi tiết chưa quyết định vào code chỉ bằng suy đoán.

### 6.5. Những task kỹ thuật nằm **bên trong** V1

| Task triển khai | Vì sao cần | Ai có thể thực hiện |
| --- | --- | --- |
| Tạo cấu trúc lưu vị trí theo tài khoản và video nếu hệ thống chưa có. | Có dữ liệu bền vững để quay lại. | Thành viên có chuyên môn dữ liệu/backend. |
| Bổ sung điểm đọc/ghi tiến độ có xác thực và kiểm tra quyền. | Cho phép thực hiện hành vi đúng phạm vi. | Developers phối hợp với người hiểu bảo mật/nghiệp vụ. |
| Kết nối thao tác trên giao diện xem video với hành vi lưu/khôi phục. | Người học thực sự thao tác được. | Developers có chuyên môn giao diện. |
| Kiểm thử hành vi, lỗi, phân quyền và tích hợp. | Bảo đảm hoạt động đáng tin, đáp ứng tiêu chuẩn hoàn tất. | Developers và các chuyên môn kiểm thử phù hợp. |
| Đo tín hiệu sử dụng được phép và quan sát phản hồi. | Kiểm tra giá trị giả thuyết sau khi triển khai thử. | Product Owner, nhóm sản phẩm và kỹ thuật phối hợp. |

Các task có thể được giao cho người khác nhau nhưng **cùng phục vụ một story có hành vi đầu cuối**. Chúng chưa tự động là những user story độc lập. Nhóm tránh đóng V1 khi mới hoàn tất ba task đầu mà chưa kiểm chứng phần cuối.

### 6.6. Tính thế nào là hoàn tất?

**Acceptance criteria** xác nhận hành vi V1 đúng phạm vi. **Definition of Done** có thể yêu cầu kiểm thử tự động phù hợp, tích hợp vào nhánh chung, kiểm soát thay đổi, rà soát chất lượng, tài liệu vận hành cần thiết và điều kiện bảo mật của tổ chức.

Nếu một phần chưa đạt DoD thì chưa nên gọi là Done trong Scrum. Nếu đã Done nhưng chưa phát hành cho nhóm người học, nhóm đã có Increment có thể sử dụng, **chưa có bằng chứng người dùng thật đã nhận giá trị**.

### 6.7. Thu phản hồi trước khi chọn V2

Sau khi phát hành V1 có kiểm soát, nhóm có thể quan sát:

- Tỷ lệ lần mở video có tiến độ được khôi phục thành công.
- Tỷ lệ người đã dừng học quay lại bài trong khung thời gian đã chọn.
- Thời gian để người học tiếp tục đúng đoạn so với cách cũ.
- Các lỗi lưu/đọc hoặc phản ánh về việc mất tiến độ.
- Người học có thực sự cần “danh sách tất cả bài đang xem dở” hay không.

Nếu phản hồi chỉ ra việc người học không tìm được đường dẫn vào bài đang học dở, V2 có thể ưu tiên **đường quay lại từ trang chủ** thay vì đồng bộ đa thiết bị. Nếu dữ liệu cho thấy nhiều người chuyển điện thoại/máy tính, V3 có thể lên cao hơn. **Thứ tự các lát phải phản ánh điều nhóm học được**, không cố định từ lúc viết story map.

## 7. Story đủ nhỏ nhưng vẫn có giá trị: kiểm tra bằng INVEST

INVEST là một bộ gợi ý để thảo luận chất lượng user story:

| Chữ | Ý nghĩa | Câu hỏi với lát dọc |
| --- | --- | --- |
| **I – Independent** | Tương đối độc lập. | Lát này có thể được ưu tiên, thử hoặc giao với ít phụ thuộc nhất có thể không? |
| **N – Negotiable** | Có thể thương lượng. | Nhóm có thể thay đổi cách hiện thực hoặc ranh giới mà vẫn giữ mục tiêu không? |
| **V – Valuable** | Có giá trị. | Người dùng/bên liên quan được hưởng kết quả cụ thể nào? |
| **E – Estimable** | Có thể ước lượng hợp lý. | Nhóm đã đủ hiểu phạm vi và bất định để lập kế hoạch chưa? |
| **S – Small** | Đủ nhỏ. | Có thể hoàn thành và kiểm chứng trong nhịp làm việc phù hợp không? |
| **T – Testable** | Có thể kiểm thử. | Có ví dụ đầu vào, hành vi và kết quả quan sát được không? |

**Independent** không có nghĩa không có phụ thuộc thực tế nào. Trong một sản phẩm, V2 có thể phát triển trên V1. Mục tiêu là giảm phụ thuộc làm nhóm phải chờ nhiều story mới tạo được giá trị.

**Small** không có một con số story point tuyệt đối. Lát nhỏ là lát nhóm có khả năng hoàn tất, tích hợp và kiểm chứng trong nhịp giao hàng phù hợp. Nếu story vẫn quá lớn, hãy quay lại xem có biến thể nào có thể tách mà vẫn tạo kết quả.

**Valuable** không đòi hỏi mọi lát đều hiện ra một màn hình mới. Một thay đổi về tốc độ tải, quyền truy cập, độ ổn định hoặc khả năng phục hồi có thể mang giá trị đo được cho người dùng và vận hành.

### Ba câu hỏi kiểm tra nhanh

1. **Demo được gì?** Trình diễn tác vụ hoặc kết quả có ý nghĩa, không chỉ file code hay endpoint đơn lẻ.
2. **Kiểm thử được gì?** Có trường hợp đúng và sai quan trọng, có tiêu chí chấp nhận quan sát được.
3. **Học được gì?** Sau khi hoàn thành, nhóm có thể nhận tín hiệu nào để quyết định tiếp tục hay đổi hướng?

Một lát đáp ứng tốt cả ba câu hỏi thường là ứng viên đáng để ưu tiên.

## 8. Khi cần việc kỹ thuật nền tảng, phải xử lý thế nào?

Có những công việc cần thiết nhưng **không dễ chia ngay thành giá trị người dùng độc lập**, chẳng hạn tạo cơ chế xác thực ban đầu, nâng cấp cơ sở hạ tầng, chuyển dữ liệu, thay chứng chỉ hoặc xử lý rủi ro bảo mật.

Không nên gắn nhãn “user story dọc” cho mọi task để đẹp backlog. Hãy phân biệt:

- **Story tạo giá trị đầu cuối:** người dùng hoặc hệ thống gọi được một hành vi có ý nghĩa.
- **Enabler/technical task:** công việc hỗ trợ hoặc mở đường, có tiêu chí hoàn tất và lý do rõ ràng.
- **Spike/PoC có giới hạn:** điều tra nhằm giải đáp một câu hỏi chưa biết, đầu ra là bằng chứng hoặc quyết định, không giả vờ đã có tính năng sản phẩm.

### Ưu tiên kỹ thuật nền tảng theo nhu cầu gần

Ví dụ, để lưu tiến độ video, hệ thống cần nơi lưu dữ liệu. Thay vì “thiết kế kho tiến độ hỗ trợ mọi loại bài, mọi thiết bị, mọi hoạt động tương lai”, nhóm có thể chọn cấu trúc đáp ứng V1 với tiêu chuẩn chất lượng cần thiết, ghi rõ giả định và mở rộng khi xuất hiện nhu cầu.

Tuy nhiên, nếu yêu cầu pháp lý, khả năng phục hồi hay giới hạn dữ liệu đã biết đòi hỏi một thiết kế nền tảng cụ thể, đó là điều **cần giải quyết ngay**, không phải cấu trúc “thừa” có thể bỏ qua.

### Walking skeleton và lát giá trị

**Walking skeleton** là một đường đi mỏng qua các thành phần cần thiết, thường dùng để chứng minh hệ thống có thể kết nối và triển khai. Nó có ích để giảm rủi ro tích hợp, nhưng nếu chỉ hiển thị “Hello world” thì chưa có giá trị người dùng đáng kể.

Để biến nó thành lát dọc sản phẩm, hãy bổ sung **hành vi tối thiểu có ích**, ví dụ người dùng xem được một danh sách khóa học thật có quyền truy cập, thay vì chỉ chứng minh frontend gọi được backend.

### Feature flag không biến một phần chưa xong thành Done

Feature flag có thể giúp kiểm soát người được dùng một tính năng đã hoàn thiện. Nó không thay thế DoD, kiểm thử hay an toàn. Nếu phần mềm còn lỗi nghiêm trọng nhưng được giấu sau flag, nhóm chưa thể mặc nhiên coi hành vi đó đạt chất lượng.

## 9. Những cách chia sai cần tránh

| Cách chia chưa tốt | Rủi ro | Cách cải thiện |
| --- | --- | --- |
| **“UI story”, “backend story”, “database story”** cùng một hành vi. | Story báo xong nhưng chưa có luồng dùng được. | Tạo một story theo kết quả, chia UI/API/data thành task bên trong. |
| **Một story quá lớn ôm mọi biến thể.** | Chờ lâu mới tích hợp; khó nhận phản hồi. | Chọn một luồng có ích, sau đó tách theo vai trò, quy tắc và trường hợp. |
| **Chỉ xây màn hình với dữ liệu giả rồi gọi Done.** | Người dùng không thể thực hiện chức năng thật; hiểu sai tiến độ. | Nếu là prototype, ghi mục tiêu học hỏi; nếu là story sản phẩm, bổ sung xử lý đầu cuối. |
| **“Happy path trước, bảo mật và lỗi sau”.** | Tạo rủi ro dữ liệu, kết quả sai và mất tin cậy. | Chỉ trì hoãn biến thể phạm vi; giữ kiểm soát và trường hợp lỗi thiết yếu. |
| **Chia theo nút giao diện rất nhỏ.** | Mỗi ticket “nhỏ” nhưng không có kết quả độc lập. | Nhóm các thao tác đủ hình thành hành vi có ích. |
| **Mỗi story phụ thuộc bốn story khác mới chạy được.** | Nhiều việc chờ nhau và khó đổi ưu tiên. | Chọn ranh giới hẹp hơn nhưng hoàn chỉnh; giảm phụ thuộc bằng thiết kế và phối hợp. |
| **Chia lát nhưng trì hoãn tích hợp tới cuối Sprint.** | Mất lợi ích phản hồi sớm, xuất hiện xung đột tích hợp. | Tích hợp, chạy kiểm thử và demo từng lát khi hoàn thành. |
| **Đo thành công bằng số story đóng.** | Có thể tạo nhiều story rất nhỏ nhưng không tăng giá trị. | Đo thời gian hoàn tất, chất lượng và kết quả người dùng bên cạnh throughput. |

**Lưu ý:** cùng một hạng mục có thể là story hợp lệ ở một hệ thống và chỉ là task ở hệ thống khác. Ví dụ “API tra cứu giờ trống” có thể là sản phẩm đầu cuối với khách hàng là hệ thống đối tác sử dụng API. Nếu API chỉ phục vụ màn hình của ứng dụng hiện tại, một endpoint đơn lẻ thường chưa đủ tạo kết quả.

## 10. Chia lát dọc trong Scrum, Kanban và XP

### 10.1. Scrum: chọn phần việc có thể hoàn tất trong Sprint

Trong Scrum, Product Owner chịu trách nhiệm tối đa hóa giá trị và sắp thứ tự **Product Backlog**. Developers chịu trách nhiệm tạo kế hoạch thực hiện, chất lượng và Increment có thể sử dụng. Product Backlog refinement giúp các bên làm rõ, chia nhỏ và cải thiện hiểu biết về các mục ưu tiên cao.

Ở **Sprint Planning**, nhóm thảo luận một **Sprint Goal** rõ, sau đó lựa chọn phạm vi khả thi. Chia lát dọc giúp Developers chọn phần hành vi có thể hoàn tất trong Sprint thay vì nhận toàn bộ tính năng lớn chưa rõ. Trong Sprint, Developers có thể điều chỉnh **Sprint Backlog** khi học thêm, trao đổi với Product Owner nếu cần làm rõ hoặc thương lượng phạm vi mà vẫn giữ Sprint Goal.

Ở **Sprint Review**, một Increment đã Done được xem xét trong bối cảnh mục tiêu sản phẩm và các bên trao đổi phản hồi. Đây là dịp đánh giá lát tiếp theo có còn đáng ưu tiên không.

**Không nên ép story phải tách để mỗi người có một ticket.** Nhóm có thể cộng tác trên cùng một lát; hoàn tất kết quả chung quan trọng hơn tối đa hóa số người “bận”.

### 10.2. Kanban: bớt việc dở, hoàn tất đầu cuối

Kanban dùng trực quan hóa luồng công việc, chính sách rõ ràng, giới hạn WIP và các số đo dòng chảy để phát hiện điểm nghẽn. Chia dọc giúp một mục đi qua các bước với phạm vi nhỏ hơn, từ đó dễ quan sát thời gian chờ giữa phát triển, review, kiểm thử và phát hành.

Ví dụ: nếu nhiều lát đang chờ kiểm thử, nhóm có thể **tập trung xử lý các lát đang dở** trước khi kéo thêm story mới. Như vậy, giảm WIP có thể rút ngắn thời gian có kết quả thực sự được kiểm chứng.

Kanban không yêu cầu mọi mục đều là user story. Các công việc vận hành, lỗi và cải tiến kỹ thuật cũng cần chính sách thực hiện rõ, nhưng khi có thể, vẫn nên tìm cách tạo **giá trị hoàn chỉnh thay vì tích trữ đầu việc nửa chừng**.

### 10.3. XP: giữ khả năng chia nhỏ mà không làm hỏng phần mềm

Các thực hành của **Extreme Programming (XP)** giúp các lát dọc nhỏ có thể được giao liên tục:

- **TDD và kiểm thử tự động:** diễn đạt hành vi mong đợi dưới dạng kiểm tra có thể chạy lại, phát hiện sai sớm.
- **Continuous Integration:** tích hợp thay đổi thường xuyên, giảm việc ghép những nhánh tồn tại quá lâu.
- **Refactoring:** giữ cấu trúc code dễ sửa khi thêm lát mới.
- **Pair Programming:** hỗ trợ chia sẻ hiểu biết và xử lý những phần tích hợp phức tạp.
- **Simple Design:** giải quyết yêu cầu hiện tại bằng thiết kế rõ ràng, tránh xây trước mọi khả năng tưởng tượng.

Không phải mọi đội bắt buộc phải áp dụng toàn bộ thực hành XP, nhưng nhóm muốn chia lát nhỏ liên tục cần một nền tảng kỹ thuật đủ tin cậy để **mỗi thay đổi không làm tăng chi phí sửa phần cũ quá nhanh**.

## 11. Đo hiệu quả chia lát dọc bằng gì?

Chia nhỏ story là phương tiện. Mục tiêu là tạo giá trị sớm, giảm rủi ro và duy trì chất lượng. Vì thế, không nên đánh giá thành công chỉ bằng **story point hoàn tất** hoặc **số ticket đóng**.

### 11.1. Số đo dòng công việc

| Chỉ số | Cách hiểu | Câu hỏi khi chia lát |
| --- | --- | --- |
| **Lead time** | Thời gian từ khi yêu cầu được ghi nhận đến khi hoàn tất, theo mốc do nhóm quy ước. | Những yêu cầu nào phải chờ quá lâu trước khi có giá trị? |
| **Cycle time** | Thời gian từ lúc bắt đầu thực hiện đến khi mục hoàn tất. | Lát có quá lớn, bị chặn hay tích hợp quá muộn không? |
| **Throughput** | Số mục hoàn thành trong một khoảng thời gian. | Các mục có kích cỡ tương đối ổn định hay số lượng tăng chỉ vì chia quá vụn? |
| **WIP** | Số mục đã bắt đầu nhưng chưa hoàn thành. | Có quá nhiều lát đang dở ở nhiều bước cùng lúc không? |
| **Work item age** | Thời gian đã trôi qua của mục vẫn đang thực hiện. | Lát nào tồn quá lâu cần hỗ trợ hoặc chia lại? |

Một câu chuyện lớn giảm từ 20 ngày xuống hai lát mỗi lát 6 ngày có thể đem lại phản hồi sớm hơn. Tuy nhiên, không nên tự kết luận cách chia đã **tăng năng suất** nếu mỗi lát còn nhiều lỗi, kiểm thử bị bỏ qua hoặc người dùng không nhận lợi ích.

### 11.2. Số đo chất lượng

- Tỷ lệ các lát hoàn tất thực sự đạt DoD.
- Lỗi xuất hiện ở tích hợp hoặc production, phân loại theo mức nghiêm trọng.
- Công việc phải sửa lại do hiểu sai acceptance criteria.
- Thời gian phát hiện và xử lý lỗi ảnh hưởng người dùng.
- Mức độ ổn định của hành vi đã có sau các lát mới.

Nếu cycle time giảm nhưng lỗi nghiêm trọng tăng, nhóm cần xem liệu phạm vi đã bị cắt theo cách thiếu kiểm soát.

### 11.3. Số đo giá trị

Với tính năng “Học tiếp”, nhóm có thể dùng:

- Tỷ lệ người học có thể khôi phục thành công vị trí.
- Thời gian từ mở bài tới tiếp tục học đúng đoạn.
- Tỷ lệ quay lại bài sau khi tạm dừng.
- Tỷ lệ hoàn tất bài/khóa học nếu đây là mục tiêu sản phẩm.
- Phản hồi trực tiếp về việc tìm lại nội dung có dễ hơn không.

**Phân biệt:** khôi phục thành công là một kết quả chức năng; người học quay lại và hoàn tất bài là kết quả sản phẩm rộng hơn. Hai nhóm chỉ số bổ sung cho nhau.

### 11.4. Đánh giá thay đổi một cách thận trọng

Giả sử sau khi chia story và giao lát đầu, thời gian từ nhận việc tới Done giảm từ trung vị 14 ngày xuống 6 ngày. Có thể xem đây là **tín hiệu đáng kiểm tra**, nhưng cần xét số lượng mục, độ khó, biến động thành viên, định nghĩa Done và cùng giai đoạn đo. Không khẳng định thay đổi cách chia là nguyên nhân duy nhất nếu chưa đủ bằng chứng.

## 12. Một buổi refinement để tìm lát dọc

Có thể tổ chức buổi thảo luận ngắn với Product Owner, Developers và các bên chuyên môn liên quan. Mục tiêu là rời cuộc họp với **một vài lát có thể kiểm chứng**, không phải hoàn thành toàn bộ thiết kế hệ thống.

### Đầu vào cần có

- Một vấn đề/người dùng/kết quả mong đợi.
- Story hoặc epic đang quá lớn và các ví dụ nghiệp vụ tiêu biểu.
- Các ràng buộc đã biết: quyền truy cập, dữ liệu, vận hành, pháp lý, phụ thuộc.
- Phản hồi, dữ liệu sử dụng hoặc giả định còn thiếu.

### Các bước gợi ý

1. **Thống nhất mục tiêu:** “Khi xong lát đầu, ai làm được việc gì?”
2. **Vẽ hành trình:** từ hành động mở đầu tới kết quả người dùng quan sát.
3. **Tìm đường mỏng:** chọn một nhóm người dùng, một quy tắc và một trường hợp giá trị cao.
4. **Liệt kê biến thể:** ngoại lệ nghiệp vụ, nhóm khác, định dạng khác, quy mô lớn, tích hợp nâng cao.
5. **Đặt ranh giới an toàn:** xác định những kiểm soát và trường hợp lỗi không được bỏ.
6. **Viết tiêu chí chấp nhận:** ít nhất một trường hợp thành công, các trường hợp thất bại quan trọng.
7. **Kiểm tra tính độc lập:** mỗi lát có thể demo, tích hợp và quyết định ưu tiên riêng không?
8. **Sắp thứ tự:** chọn lát giảm rủi ro/lấy phản hồi tốt nhất, ghi rõ câu hỏi chưa biết.

### Mẫu ghi chép lát dọc

~~~text
Tên lát:
Người dùng hoặc bên hưởng lợi:
Vấn đề và kết quả mong đợi:
Hành vi đầu cuối trong phạm vi:
Biến thể/nhóm đối tượng CHƯA hỗ trợ:
Ràng buộc chất lượng bắt buộc:
Ví dụ thành công:
Ví dụ thất bại cần xử lý:
Tiêu chí chấp nhận:
Cách demo/kiểm chứng kỹ thuật:
Phản hồi hoặc số đo giá trị có thể thu:
Phụ thuộc và giả định cần xác minh:
Lát tiếp theo chỉ xem xét khi:
~~~

Mẫu này là công cụ trao đổi. Không cần tạo thủ tục điền đầy đủ mọi trường cho mọi sửa lỗi nhỏ; hãy dùng lượng thông tin **đủ để mọi người hiểu cùng một kết quả**.

## 13. Bài tập: chia story lớn thành ba lát dọc

Một nhóm phát triển nền tảng học trực tuyến có yêu cầu:

> “Giảng viên cần xem tiến độ của tất cả người học trong mọi khóa, lọc theo bất kỳ tiêu chí nào, xuất báo cáo PDF và Excel, nhận cảnh báo học viên có nguy cơ bỏ học và dự báo kết quả bằng AI.”

Giả sử nhu cầu đã quan sát được là: **giảng viên muốn biết ai chưa hoàn thành bài đến hạn để hỗ trợ sớm**. Dữ liệu hoàn thành bài hiện có, quyền truy cập theo lớp học đã được định nghĩa. Nhóm chưa có bằng chứng đủ để ưu tiên AI hay báo cáo tùy biến toàn diện.

### Yêu cầu

1. Viết lại **kết quả mong đợi** dưới góc nhìn giảng viên thay vì liệt kê tính năng.
2. Chọn một **lát V1** từ giao diện đến dữ liệu và phân quyền, có thể demo và kiểm chứng.
3. Đề xuất **V2, V3** mở rộng theo nhu cầu có khả năng được xác nhận. Nêu các hạng mục có thể trì hoãn.
4. Viết ít nhất **ba tiêu chí chấp nhận** cho V1: trường hợp có người quá hạn, không có người quá hạn và không có quyền xem lớp.
5. Liệt kê các task kỹ thuật của V1 nhưng giải thích vì sao chúng **không phải ba story ngang độc lập**.
6. Chọn một chỉ số kết quả người dùng và hai số đo dòng công việc để kiểm tra hiệu quả chia lát.
7. Nêu một bằng chứng khiến nhóm **không tiếp tục xây V3** như kế hoạch ban đầu.

### Một cách giải tham khảo

**Kết quả mong đợi:** Giảng viên biết đúng học viên nào trong lớp mình phụ trách chưa hoàn thành bài đến hạn, để có thể hỗ trợ đúng người.

| Lát | Hành vi đầu cuối | Điều kiểm chứng |
| --- | --- | --- |
| **V1** | Giảng viên đăng nhập, chọn lớp được phân quyền và xem danh sách học viên có bài quá hạn. | Dữ liệu đúng theo lớp, bài và hạn; không lộ dữ liệu lớp khác. |
| **V2** | Giảng viên lọc danh sách theo bài học hoặc thời gian đến hạn trong lớp mình. | Kết quả lọc chính xác, giúp tìm nhóm cần hỗ trợ nhanh hơn. |
| **V3** | Giảng viên xuất danh sách học viên quá hạn theo định dạng thật sự cần dùng để liên hệ. | Dữ liệu xuất khớp danh sách, phân quyền được giữ và người dùng sử dụng được đầu ra. |

**Chưa ưu tiên:** dự báo AI, báo cáo tùy chỉnh mọi tiêu chí, xuất nhiều định dạng khi chưa xác nhận nhu cầu. Nếu dữ liệu sau V1 cho thấy giảng viên chỉ cần xem và liên hệ trực tiếp trong ứng dụng, V3 “xuất báo cáo” có thể không cần thiết; nhóm nên điều chỉnh backlog thay vì xây theo kế hoạch cũ.

**Tiêu chí chấp nhận V1 minh họa:**

~~~gherkin
Feature: Xem học viên có bài quá hạn trong lớp mình phụ trách

Scenario: Lớp có người chưa hoàn thành bài đến hạn
  Given giảng viên đã đăng nhập và có quyền xem lớp "Java cơ bản"
  And lớp có người chưa hoàn thành một bài đã quá hạn
  When giảng viên mở danh sách học viên quá hạn của lớp
  Then hệ thống hiển thị đúng người học và bài quá hạn thuộc lớp đó
  And mỗi dòng thể hiện thông tin tối thiểu cần để hỗ trợ người học

Scenario: Không có học viên quá hạn
  Given giảng viên có quyền xem lớp "Java cơ bản"
  And không có học viên nào quá hạn trong lớp
  When giảng viên mở danh sách học viên quá hạn
  Then hệ thống hiển thị trạng thái không có người quá hạn

Scenario: Giảng viên không có quyền xem lớp
  Given giảng viên không có quyền xem lớp "Lớp B"
  When giảng viên yêu cầu danh sách học viên quá hạn của "Lớp B"
  Then hệ thống từ chối truy cập theo chính sách
  And không tiết lộ dữ liệu của lớp đó
~~~

**Task của V1:** truy vấn dữ liệu quá hạn, API có xác thực/phân quyền, giao diện danh sách, kiểm thử trường hợp có/không có dữ liệu và truy cập sai quyền. Các task này cùng phục vụ **một kết quả “xem được danh sách đúng của lớp mình”**; nếu tách chúng thành story riêng có thể báo Done nhưng chưa giúp giảng viên sử dụng tính năng.

**Đo lường:** thời gian giảng viên tìm được người cần hỗ trợ hoặc tỷ lệ giảng viên thực hiện hành động hỗ trợ sau khi xem danh sách; kết hợp **cycle time** và **WIP** của nhóm. Cần theo dõi chất lượng dữ liệu và phản hồi khi danh sách chưa chính xác.

## 14. Tự kiểm tra nhanh

**Câu 1.** Story “Tạo bảng lưu tiến độ trong database” có phải lát dọc vì nó nhỏ và ước lượng được không?

**Đáp án:** Thông thường không. Nó là task kỹ thuật hỗ trợ một hành vi. Một lát dọc nên tạo kết quả đầu cuối có thể sử dụng hoặc kiểm chứng theo nhu cầu của người dùng/hệ thống gọi.

**Câu 2.** Có bắt buộc mỗi lát dọc phải sửa UI, API và database không?

**Đáp án:** Không. Số lớp phải sửa phụ thuộc thiết kế hiện tại. Lát dọc được xác định bởi **hành vi hoàn chỉnh và kết quả có ý nghĩa**, không phải bởi đủ số tầng công nghệ.

**Câu 3.** Có thể chia lát đầu chỉ hỗ trợ một loại giảm giá rồi làm các loại khác sau không?

**Đáp án:** Có, nếu loại giảm giá đầu tiên có giá trị, các điều kiện áp dụng được xác định và tính phí đúng trong phạm vi cho phép. Không được bỏ các ràng buộc bắt buộc đối với giao dịch thật.

**Câu 4.** Một màn hình với dữ liệu giả đã được người dùng bấm thử. Có thể coi là lát sản phẩm đã Done không?

**Đáp án:** Nếu mục tiêu là kiểm tra tương tác thì đó có thể là prototype đạt mục tiêu nghiên cứu; nó chưa chứng minh chức năng sản phẩm dùng dữ liệu thật đã tích hợp và đạt DoD.

**Câu 5.** Vì sao tỷ lệ test đạt 100% chưa chứng minh một lát có giá trị?

**Đáp án:** Kiểm thử xác nhận hành vi triển khai đúng theo những điều đã đặc tả. Giá trị đòi hỏi quan sát nhu cầu và kết quả thực của người dùng, có thể khác với giả định ban đầu.

**Câu 6.** Story nhỏ tới mức một người làm trong một ngày có chắc tốt không?

**Đáp án:** Không. Nếu mỗi story chỉ là một nút hoặc một lớp code và không tạo giá trị độc lập thì đó là chia vụn theo công việc, không phải chia lát dọc hữu ích.

**Câu 7.** Sau V1, người dùng phản hồi không cần V2 mà muốn cải thiện hiệu năng. Nhóm có nên giữ kế hoạch V2 vì đã ước lượng xong không?

**Đáp án:** Không nên mặc định. Hãy đánh giá giá trị, rủi ro và tác động của phản hồi; Product Owner có thể điều chỉnh thứ tự backlog. Điều kiện chất lượng và hiệu năng cần thiết có thể được ưu tiên.

**Câu 8.** Vì sao giới hạn WIP hỗ trợ chia lát dọc?

**Đáp án:** Nó giúp nhóm tập trung hoàn tất, tích hợp và kiểm chứng các lát đang làm trước khi nhận thêm nhiều việc, giảm nút thắt và thời gian chờ phản hồi.

## 15. Ghi nhớ trọng tâm

- **Chia lát dọc là chia theo hành vi có kết quả đầu cuối**, không chỉ chia theo UI, backend, database hay số giờ công.
- **Một lát tốt có thể demo, kiểm thử và tạo cơ sở học hỏi.** Nó đủ nhỏ để hoàn tất nhưng vẫn có ý nghĩa với người dùng hoặc hệ thống tiêu thụ.
- **User story nêu người hưởng lợi và mục tiêu; acceptance criteria mô tả hành vi; DoD bảo đảm chất lượng hoàn tất.** Ba yếu tố có vai trò khác nhau và cần hỗ trợ lẫn nhau.
- **Chọn luồng đơn giản, biến thể ít trước** nhưng giữ đúng phân quyền, xử lý lỗi cần thiết, tính toàn vẹn dữ liệu và ràng buộc vận hành trong phạm vi đã hỗ trợ.
- **Các task kỹ thuật có thể nằm bên trong một story dọc.** Hoàn thành từng task không đồng nghĩa đã hoàn thành kết quả người dùng.
- **Lát dọc khác prototype, MVP và Increment:** prototype khám phá ý tưởng, MVP kiểm chứng giả thuyết giá trị, còn Increment trong Scrum phải đạt DoD; lát dọc là cách chọn phạm vi chức năng có thể giúp tạo Increment và phục vụ MVP.
- **Scrum, Kanban và XP** giúp chia rõ giá trị, giảm WIP, tích hợp thường xuyên và giữ phần mềm dễ thay đổi.
- **Đo cả luồng công việc, chất lượng và kết quả sản phẩm.** Đóng nhiều ticket hơn không tự động có nghĩa người dùng nhận giá trị sớm hơn.
- **Sau mỗi lát, học từ phản hồi rồi xem lại backlog.** Không cần xây mọi lát đã nghĩ ra nếu mục tiêu hoặc bằng chứng thay đổi.

Khi nhóm làm chủ cách chia lát dọc, một yêu cầu lớn không còn là khối công việc phải hoàn thành toàn bộ mới biết đúng hay sai. Nó trở thành chuỗi những **bước tiến nhỏ có thể sử dụng, kiểm chứng và điều chỉnh**, phù hợp với tinh thần Agile: giao sản phẩm tăng dần, học từ phản hồi sớm và cải tiến liên tục.
