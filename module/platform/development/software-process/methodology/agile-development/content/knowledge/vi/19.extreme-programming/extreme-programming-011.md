# Tích hợp liên tục để phát hiện xung đột sớm

## 1. Vì sao tích hợp muộn trở thành vấn đề lớn?

Một nhóm phát triển nền tảng học trực tuyến có ba Developers cùng tham gia chức năng đăng ký khóa học:

- **An** sửa API đăng ký để hỗ trợ thông báo lỗi chi tiết.
- **Bình** phát triển giao diện, dựa trên cấu trúc phản hồi API cũ.
- **Chi** thay đổi cấu trúc dữ liệu để tránh một người đăng ký cùng khóa nhiều lần.

Nếu mỗi người làm việc riêng trong nhiều ngày và chỉ ghép mã vào cuối Sprint, nhóm có thể gặp một chuỗi vấn đề cùng lúc: tên trường API không khớp, migration dữ liệu khiến ứng dụng cũ lỗi, kiểm thử chạy trên máy từng người nhưng thất bại khi ghép, và có hai cách xử lý đăng ký trùng mâu thuẫn nhau. Việc sửa lúc đó rất khó vì nhiều giả định đã được xây thêm trên mã chưa tích hợp.

**Continuous Integration (CI) — tích hợp liên tục** giúp giảm khoảng thời gian giữa lúc một thay đổi được tạo ra và lúc nó được kiểm chứng trong hệ thống chung. Nhóm thường xuyên hợp nhất các thay đổi **nhỏ**, dùng quy trình **build và kiểm thử tự động** để nhận phản hồi nhanh, rồi **ưu tiên xử lý lỗi tích hợp ngay** thay vì tiếp tục xây trên trạng thái không ổn định.

CI là một thực hành kỹ thuật nổi bật của **Extreme Programming (XP)**. Nó kết nối các giá trị và nguyên tắc của Agile với công việc mỗi ngày:

- **Nhận phản hồi sớm:** Biết sự thay đổi vừa thực hiện có phá hợp đồng API hay hành vi cũ không.
- **Giao tăng dần:** Mỗi phần thay đổi nhỏ tiến gần hơn tới Increment có thể dùng được.
- **Cộng tác:** Không coi việc “chạy trên máy tôi” là đủ; cả nhóm cùng chịu trách nhiệm cho mã chung.
- **Thích ứng:** Khi giả định sai được phát hiện, nhóm sửa ở quy mô nhỏ trước khi lỗi lan rộng.
- **Cải tiến liên tục:** Đo và cải thiện thời gian phản hồi, độ tin cậy của pipeline và chất lượng tích hợp.

Trong module **AGILE_DEVELOPMENT**, thực hành này có thể được kết hợp với **user story, product backlog, Scrum, Kanban, XP** và các chỉ số dòng công việc. CI không phải một sự kiện Scrum bắt buộc, cũng không đồng nghĩa có thể phát hành ngay mọi bản build.

**Thông điệp chính:** *Tích hợp càng thường xuyên và phản hồi càng đáng tin cậy, nhóm càng có cơ hội phát hiện sai khác khi phạm vi thay đổi còn nhỏ và dễ sửa.*

## 2. CI trong XP thực chất gồm những gì?

Trong XP, CI là **thói quen phối hợp và kiểm chứng liên tục**, không chỉ là một máy chủ tự chạy lệnh khi nhận commit. Một chu trình tích hợp hữu ích có các yếu tố:

1. **Tạo thay đổi nhỏ:** Một lát cắt mã có mục đích rõ, dễ review và dễ kiểm chứng.
2. **Đồng bộ trạng thái mã chung:** Biết phiên bản nào đang là cơ sở tích hợp, tránh phát triển quá lâu trên giả định cũ.
3. **Chạy kiểm tra tự động:** Biên dịch, kiểm thử và kiểm tra hợp đồng liên quan càng sớm càng tốt.
4. **Hợp nhất thường xuyên:** Đưa thay đổi đã được kiểm chứng vào dòng mã tích hợp chung.
5. **Kiểm tra sau hợp nhất:** Bảo đảm kết quả hợp nhất thực tế vẫn đạt kiểm tra cần thiết.
6. **Xử lý thất bại ngay:** Khi build chung lỗi, nhóm ưu tiên khôi phục trạng thái đáng tin cậy.

Một số nhóm dùng **trunk-based development** với nhánh ngắn và tích hợp nhiều lần mỗi ngày. Nhóm khác dùng pull request và các kiểm tra bắt buộc; cách này vẫn có thể hỗ trợ CI **nếu thay đổi được tích hợp thường xuyên và vòng phản hồi đủ ngắn**. Một pull request tồn tại nhiều tuần với nhánh tách biệt dù có chạy pipeline cũng chưa giải quyết tốt rủi ro tích hợp muộn.

### 2.1. Cần phân biệt các chữ “continuous”

| Khái niệm | Câu hỏi trọng tâm | Có bắt buộc phát hành cho người dùng không? |
| --- | --- | --- |
| **Continuous Integration (CI)** | Thay đổi được hợp nhất và kiểm chứng thường xuyên trên mã chung không? | **Không** |
| **Continuous Delivery** | Phiên bản đã kiểm chứng có thể được đưa tới môi trường sử dụng bằng quy trình đáng tin cậy khi quyết định phát hành không? | **Không**, quyết định phát hành có thể chủ động |
| **Continuous Deployment** | Thay đổi đủ điều kiện có được tự động triển khai tới production theo chính sách không? | **Có**, đối với luồng được tự động hóa theo định nghĩa này |

Ba khái niệm liên hệ nhưng không đồng nhất. Một nhóm có thể làm CI tốt nhưng vẫn phát hành thủ công theo đợt vì yêu cầu kinh doanh hoặc tuân thủ. Ngược lại, tự động triển khai một hệ thống thiếu kiểm thử tích hợp đáng tin không có nghĩa thực hành CI đã tốt.

### 2.2. CI là công cụ phát hiện, không phải bằng chứng toàn diện về chất lượng

Pipeline xanh chỉ nói rằng **những kiểm tra đã được cấu hình** đã đạt dưới **điều kiện chạy của pipeline**. Nó không chứng minh:

- Mọi yêu cầu nghiệp vụ đều đúng.
- Không tồn tại lỗ hổng bảo mật hoặc lỗi hiếm.
- Người dùng thấy giao diện dễ hiểu.
- Hệ thống đáp ứng tải production chưa từng được thử.
- Một thay đổi đã đáp ứng toàn bộ **Definition of Done (DoD)** nếu DoD còn tiêu chuẩn khác.

Do vậy, CI hỗ trợ chất lượng và phản hồi sớm nhưng **không thay thế** hoạt động khám phá yêu cầu, kiểm thử theo rủi ro, quan sát vận hành và phản hồi người dùng.

## 3. “Xung đột” khi tích hợp không chỉ là merge conflict

Nhóm thường nghĩ xung đột là hai Developer cùng sửa một dòng và Git yêu cầu chọn phiên bản nào giữ lại. Đó chỉ là một loại xung đột.

| Loại xung đột | Tình huống trên nền tảng học | Dấu hiệu phát hiện | Cách phòng ngừa / xử lý |
| --- | --- | --- | --- |
| **Xung đột văn bản (merge conflict)** | Hai người sửa cùng đoạn mã xử lý đăng ký | Công cụ quản lý phiên bản không thể tự hợp nhất | Nhánh ngắn, đồng bộ thường xuyên, trao đổi khi đụng khu vực mã chung |
| **Xung đột ngữ nghĩa** | Hai thay đổi đều merge được nhưng cùng sửa quy tắc đăng ký theo hai giả định khác nhau | Kiểm thử nghiệp vụ hoặc review phát hiện hành vi sai | Ví dụ chấp nhận chung, kiểm thử hành vi, review tập trung quy tắc |
| **Xung đột hợp đồng (contract)** | API đổi trường trạng thái, giao diện vẫn chờ giá trị cũ | Contract test hoặc integration test thất bại | Hợp đồng rõ, thay đổi tương thích, kiểm tra consumer/provider |
| **Xung đột dữ liệu/schema** | Migration đổi tên cột trước khi mọi dịch vụ sử dụng trường mới | Kiểm thử migration hoặc chạy ứng dụng phiên bản khác thất bại | Migration theo giai đoạn, thử tương thích cũ–mới |
| **Xung đột phụ thuộc** | Nâng phiên bản thư viện gây thay đổi cách cấu hình | Build hoặc test trên môi trường sạch thất bại | Quản lý phiên bản, khóa phụ thuộc, nâng cấp từng phần nhỏ |
| **Xung đột môi trường** | Máy cá nhân có cấu hình khác CI hoặc môi trường tích hợp | Pass cục bộ nhưng fail CI, hoặc ngược lại | Môi trường tái lập được, cấu hình và secret quản lý rõ |
| **Xung đột hành vi song song** | Hai yêu cầu đăng ký đồng thời tạo dữ liệu trùng | Kiểm thử tính đồng thời, kiểm thử dịch vụ hoặc lỗi production | Kiểm tra ràng buộc dữ liệu, tính idempotent và giao dịch theo yêu cầu |
| **Xung đột triển khai** | Dịch vụ mới được deploy nhưng phiên bản giao diện cũ còn được phục vụ | Smoke test / giám sát sau deploy | Tương thích tiến/lùi khi cần, phát hành theo giai đoạn, rollback có kế hoạch |

Một xung đột ngữ nghĩa nguy hiểm vì **công cụ merge không cảnh báo**. Mã có thể biên dịch, kiểm thử đơn vị của từng phần đều xanh, nhưng hành vi kết hợp lại không đúng.

### 3.1. Ví dụ hợp đồng API thay đổi

Phiên bản API ban đầu trả:

~~~json
{
  "courseId": "java-basic",
  "status": "success"
}
~~~

Developer backend đổi thành:

~~~json
{
  "courseId": "java-basic",
  "status": "enrolled"
}
~~~

Developer frontend vẫn dùng giả định:

~~~javascript
// Ví dụ rút gọn: giao diện đang dựa trên hợp đồng cũ.
if (response.status === "success") {
  showConfirmation("Đã đăng ký");
}
~~~

Hai thay đổi có thể **không sửa cùng tệp**, vì vậy Git không tạo merge conflict. Tuy nhiên, sau khi tích hợp, người học đăng ký thành công nhưng giao diện không hiển thị xác nhận. Một **kiểm thử hợp đồng hoặc kiểm thử tích hợp từ giao diện tới dịch vụ** có thể phát hiện sai khác này khi còn rẻ để sửa.

Giải pháp không phải luôn “đổi frontend theo backend”. Nhóm phải xác định **hợp đồng mong muốn**, khả năng tương thích với các client đang hoạt động, chiến lược chuyển đổi và quyền quyết định về hành vi.

### 3.2. Tại sao càng để lâu càng khó giải quyết?

Khi nhiều thay đổi dựa trên những phiên bản khác nhau:

- **Khó cô lập nguyên nhân:** Lỗi có thể do A, B, C hoặc sự tương tác giữa chúng.
- **Khó xác định người hiểu bối cảnh:** Mỗi người đã tiếp tục xây trên giả định của mình.
- **Nhiều bài kiểm thử mới dựa trên hành vi sai:** Sửa lỗi có thể khiến các thay đổi khác bị tác động.
- **Phạm vi làm lại tăng:** Hợp đồng, dữ liệu và giao diện cùng phải chỉnh.
- **Phản hồi nghiệp vụ tới muộn:** Có thể chỉ phát hiện sai yêu cầu khi cả một luồng lớn đã được xây.

CI giảm khoảng thời gian cho các giả định lệch nhau tồn tại, nhưng không xóa hoàn toàn xung đột. Nhóm vẫn cần làm rõ yêu cầu, review và kiểm thử ở mức phù hợp.

## 4. Chu trình tích hợp liên tục của một thay đổi nhỏ

Một quy trình CI dễ hiểu:

~~~mermaid
flowchart TD
    A["Chọn thay đổi nhỏ có mục đích rõ"] --> B["Đồng bộ từ nhánh chung"]
    B --> C["Viết mã và kiểm thử liên quan"]
    C --> D["Chạy kiểm tra nhanh cục bộ"]
    D --> E["Đẩy thay đổi / tạo PR theo chính sách"]
    E --> F["CI chạy build, test và các kiểm tra bắt buộc"]
    F --> G{"Đạt chất lượng để tích hợp?"}
    G -->|"Chưa"| H["Điều tra và sửa trên thay đổi nhỏ"]
    H --> C
    G -->|"Có"| I["Hợp nhất vào dòng mã chung"]
    I --> J["Kiểm tra trạng thái sau hợp nhất"]
    J --> K{"Nhánh chung vẫn xanh?"}
    K -->|"Không"| L["Ưu tiên sửa hoặc hoàn nguyên theo chính sách"]
    L --> J
    K -->|"Có"| M["Tiếp tục lát cắt tiếp theo và nhận phản hồi"]
    M --> A
~~~

### Bước 1 — Chọn phạm vi thay đổi có thể kiểm chứng

Thay vì “xây toàn bộ hệ thống đăng ký”, một thay đổi có thể là “bổ sung kiểm tra tài khoản đã đăng ký khóa”. Kích thước nên đủ nhỏ để người review hiểu và pipeline kiểm tra được, nhưng không nhỏ tới mức làm mất ý nghĩa nghiệp vụ.

### Bước 2 — Đồng bộ với mã chung

Trước khi bắt đầu hoặc trước khi hợp nhất, Developer cần biết trạng thái mã chung mới nhất. Nếu nhánh đã tách lâu, cần đánh giá xung đột và cập nhật. Không nên chờ tới cuối tuần mới xử lý một loạt thay đổi cơ sở.

### Bước 3 — Bổ sung kiểm thử hoặc điều kiện kiểm chứng

Với bug “đăng ký trùng”, nhóm có thể viết kiểm thử tái hiện lỗi trước, rồi sửa hành vi. Với khả năng mới, chuẩn bị ví dụ chấp nhận và kiểm thử phù hợp để tránh merge một thay đổi chưa rõ hành vi.

### Bước 4 — Chạy kiểm tra cục bộ đủ nhanh

Ví dụ, biên dịch và unit test liên quan trước khi đẩy. Mục tiêu là tránh gửi lên CI những lỗi cơ bản mà Developer có thể phát hiện rất nhanh. Tuy nhiên, **không lấy việc pass trên máy cá nhân để thay thế kiểm tra trong môi trường chung**.

### Bước 5 — CI kiểm tra thay đổi

Pipeline chạy trên môi trường được định nghĩa, sử dụng mã và phụ thuộc tương ứng, báo kết quả cụ thể. Một quy trình tốt giúp trả lời: **lỗi ở bước nào, bằng chứng ở đâu, có khả năng tái hiện không và ai sẽ chủ động xử lý?**

### Bước 6 — Hợp nhất và bảo vệ trạng thái chung

Các kiểm tra trên PR giúp sàng lọc thay đổi, nhưng trạng thái **sau merge** vẫn cần được xác minh. Nếu nhiều PR cùng pass dựa trên một commit gốc nhưng khi hợp nhất lại tương tác sai, kiểm tra trạng thái tích hợp hoặc cơ chế kiểm tra tổ hợp trước merge là cần thiết.

### Bước 7 — Phản hồi và lặp lại

Khi dòng mã chung ổn định, Developers tiếp tục lát cắt nhỏ kế tiếp; nhóm không cần đợi một “ngày tích hợp” đặc biệt vào cuối Sprint.

## 5. Tích hợp thường xuyên với Git và nhánh ngắn

CI không đòi mọi người phải commit trực tiếp vào một nhánh duy nhất mà không review. Nhóm cần chọn **chiến lược hợp nhất** phù hợp với chất lượng, bảo mật và cách phối hợp.

### 5.1. Hai cách tổ chức phổ biến

| Cách tổ chức | Cách hoạt động | Rủi ro cần quản lý |
| --- | --- | --- |
| **Nhánh chính (trunk) và thay đổi nhỏ** | Developer tích hợp những bước đã kiểm chứng vào nhánh chung rất thường xuyên | Cần kiểm thử nhanh và cơ chế bảo vệ thay đổi chưa sẵn sàng cho người dùng |
| **Nhánh tính năng ngắn và PR** | Developer làm thay đổi nhỏ, tạo PR, kiểm tra tự động, review và hợp nhất nhanh | PR kéo dài nhiều ngày có thể tăng xung đột; CI trước merge không tự chứng minh trạng thái sau merge |

Tránh mô hình trong đó mỗi người giữ một nhánh nhiều tuần, cuối đợt mới hợp nhất. Pipeline vẫn có thể chạy trên từng nhánh nhưng **xung đột giữa các nhánh chưa được phát hiện đầy đủ**.

### 5.2. Một chu trình thao tác mang tính minh họa

~~~text
1. Đồng bộ trạng thái mã chung phù hợp chính sách repository.
2. Chọn một thay đổi nhỏ và viết kiểm thử phù hợp.
3. Chạy kiểm tra nhanh trên máy phát triển.
4. Commit với mô tả mục đích thay đổi.
5. Đẩy PR hoặc tích hợp qua quy trình nhóm đã thống nhất.
6. Xem kết quả CI và review; sửa khi phát hiện vấn đề.
7. Hợp nhất sớm sau khi thỏa điều kiện; xác nhận trạng thái chung.
8. Tiếp tục lát cắt tiếp theo, không giữ nhánh mở vô hạn.
~~~

Quy trình cụ thể phụ thuộc công cụ, quyền hợp nhất và yêu cầu tổ chức. Với hệ thống có kiểm soát thay đổi nghiêm ngặt, quyền phê duyệt vẫn phải được tôn trọng; mục tiêu là **giảm thời gian phản hồi trong ranh giới an toàn**, không bỏ quy trình cần thiết.

### 5.3. Feature flag giúp tích hợp mã chưa mở cho người dùng

Khi một chức năng chưa hoàn tất ở cấp sản phẩm nhưng các phần mã nhỏ cần tích hợp sớm, nhóm có thể dùng **feature flag**:

- Tách việc **mã đã được tích hợp** khỏi việc **tính năng đã được bật cho người dùng**.
- Giữ giao diện/luồng cũ hoạt động trong khi triển khai từng lát cắt mới.
- Thử trên môi trường hoặc nhóm người dùng phù hợp theo chính sách.
- Có cơ chế làm sạch flag sau khi không còn cần thiết.

**Feature flag không cho phép đánh dấu một PBI chưa đạt DoD là Done.** Nếu quy tắc Done của một PBI yêu cầu một hành vi đã được kiểm chứng, việc chỉ merge mã sau flag không tự chứng minh điều kiện đó đã đạt. Nhóm có thể chia PBI hợp lý hoặc đánh giá trạng thái Done theo tiêu chuẩn được thống nhất.

Flag cũng có chi phí: nhiều tổ hợp bật/tắt, cấu hình sai, đường mã cũ và rủi ro vận hành. Không nên giữ vô hạn.

## 6. Thiết kế pipeline CI để phản hồi nhanh nhưng đủ tin cậy

Một pipeline tốt **có trình tự kiểm tra theo rủi ro**, không nhất thiết chạy mọi kiểm thử nặng ngay sau từng lần gõ phím.

| Tầng kiểm tra | Ví dụ | Vấn đề có thể phát hiện | Gợi ý bố trí |
| --- | --- | --- | --- |
| **Kiểm tra cấu trúc nhanh** | Định dạng, lint, kiểm tra tệp cấu hình | Sai cú pháp, lỗi đơn giản | Chạy sớm, phản hồi nhanh |
| **Build / biên dịch** | Biên dịch Java, đóng gói thành phần | Lỗi kiểu dữ liệu, thiếu phụ thuộc, mã không biên dịch | Gate cơ bản trước hợp nhất |
| **Unit test** | Quy tắc đăng ký trùng, điều kiện hợp lệ | Lỗi logic cục bộ | Chạy thường xuyên, ưu tiên tính ổn định |
| **Component test** | Dịch vụ đăng ký với dữ liệu thử | Sai ở ranh giới một thành phần | Chạy trong pipeline khi khả thi |
| **Contract test** | API provider trả dữ liệu consumer cần | Sai khác hợp đồng giữa các thành phần | Hữu ích khi nhiều nhóm hoặc dịch vụ phối hợp |
| **Integration test** | UI/API/database cùng hoạt động | Xung đột khi các thành phần kết hợp | Cần môi trường và dữ liệu có kiểm soát |
| **Security / dependency checks** | Phân tích phụ thuộc, secret scan, kiểm tra quyền | Rủi ro bảo mật, lộ thông tin | Theo mức rủi ro và chính sách bắt buộc |
| **System/end-to-end test** | Người học đăng ký, thấy xác nhận và danh sách | Sai ở hành trình xuyên hệ thống | Chọn ít trường hợp trọng yếu, tránh bộ E2E quá chậm và chập chờn |
| **Packaging / smoke test** | Tạo artifact, khởi chạy và kiểm tra chức năng lõi | Artifact không triển khai được hoặc cấu hình sai | Theo rủi ro môi trường và quy trình phát hành |

**Không phải mọi dự án phải có cùng danh sách lệnh, số tầng hoặc công cụ.** Quan trọng là các kiểm tra cần thiết để đạt Definition of Done và chính sách chất lượng được thực hiện, có kết quả đáng tin cậy. Kiểm thử rất chậm có thể tách theo lịch hoặc môi trường khác nếu chính sách chấp nhận, nhưng **không được tạo khoảng mù nguy hiểm** trước khi coi một thay đổi là đủ điều kiện tích hợp hoặc phát hành.

### 6.1. Phản hồi nhanh và phản hồi đầy đủ có thể nhiều tầng

Một cách tổ chức:

~~~mermaid
flowchart LR
    A["Thay đổi nhỏ"] --> B["Kiểm tra nhanh: cú pháp, build, unit test"]
    B --> C{"Đạt?"}
    C -->|"Không"| D["Sửa ngay"]
    D --> A
    C -->|"Có"| E["Contract / integration / kiểm tra chính sách"]
    E --> F{"Đạt điều kiện hợp nhất?"}
    F -->|"Không"| D
    F -->|"Có"| G["Hợp nhất và kiểm tra trạng thái chung"]
    G --> H["Kiểm tra sâu và quan sát theo chính sách"]
~~~

Một pipeline nhanh **không phải pipeline chạy ít kiểm tra nhất**, mà là pipeline cung cấp **phản hồi cần thiết sớm và có thể hành động**. Nếu thời gian chờ kiểm thử khiến Developers chuyển sang quá nhiều việc khác, WIP tăng và lỗi được phát hiện muộn hơn.

### 6.2. Ví dụ script kiểm chứng của dự án Java dùng Maven

Giả sử một repository Java **đã có Maven Wrapper**, cấu hình plugin kiểm thử phù hợp và các bài kiểm tra được gắn vào vòng đời Maven. Một lệnh có thể là:

~~~bash
./mvnw -B -ntp verify
~~~

Lệnh trên minh họa việc dùng **Maven Wrapper** và chạy tới pha verify; **những kiểm tra nào thật sự chạy còn phụ thuộc cấu hình dự án**, plugin, profile và test suite. Nó không tự động chứng minh kiểm thử tích hợp, kiểm thử hợp đồng hoặc rà soát bảo mật đã tồn tại. Trên Windows, script tương ứng có thể là Maven Wrapper dành cho Windows nếu repository cung cấp.

Không có Maven Wrapper hoặc dự án dùng Gradle, Node.js hay ngôn ngữ khác thì phải dùng lệnh phù hợp. **Không chép lệnh mẫu thành yêu cầu của mọi nhóm XP.**

### 6.3. Pipeline khái niệm, không phụ thuộc nhà cung cấp CI

~~~yaml
# GIẢ MÃ YAML minh họa chính sách; không phải cấu hình chạy được nguyên văn.
on_change:
  - pull_request_to_shared_branch
  - change_integrated_into_shared_branch

quality_gate:
  - checkout_exact_revision
  - restore_declared_dependencies
  - compile_and_check_format
  - run_unit_tests
  - run_contract_tests
  - run_required_integration_tests
  - run_organization_security_checks

on_failure:
  - publish_logs_and_test_results
  - notify_responsible_team
  - block_merge_or_release_as_policy_requires

on_success:
  - publish_versioned_build_artifact
  - report_revision_and_quality_evidence
~~~

Quy trình thực tế cần thay các bước trên bằng công cụ hợp lệ, cấu hình quyền truy cập, môi trường, dữ liệu và tiêu chuẩn chất lượng phù hợp. Đặc biệt, **kiểm tra trước merge và sau merge** cần được phối hợp để tránh hai thay đổi cùng xanh riêng rẽ nhưng làm hỏng trạng thái chung khi ghép.

## 7. Kiểm thử trong CI phải đáng tin cậy

Pipeline báo đỏ liên tục vì lỗi kiểm thử không ổn định khiến nhóm dễ bắt đầu **bỏ qua cảnh báo**, gây mất ý nghĩa của CI.

### 7.1. Kiểm thử xác định và kiểm thử chập chờn

Một kiểm thử **deterministic** cho cùng mã, dữ liệu và điều kiện môi trường được kiểm soát cần có kết quả nhất quán.

Một kiểm thử **flaky** có thể lúc đạt, lúc thất bại dù không có thay đổi liên quan, do:

- Phụ thuộc thời gian thực hoặc múi giờ.
- Dữ liệu dùng chung bị sửa bởi kiểm thử khác.
- Test phụ thuộc thứ tự chạy.
- Môi trường dịch vụ ngoài không ổn định.
- Chờ bất đồng bộ bằng một khoảng sleep cố định quá ngắn.
- Điều kiện tranh chấp giữa nhiều luồng hoặc tiến trình.

Khi có test flaky, không nên chỉ bấm “rerun cho xanh” rồi quên. Nhóm cần phân loại nguyên nhân, sửa hoặc cách ly kiểm thử theo chính sách minh bạch, đồng thời bảo đảm không che lấp rủi ro quan trọng. Một bài kiểm thử bị cách ly phải có người theo dõi và điều kiện đưa trở lại, không trở thành vùng không kiểm chứng vĩnh viễn.

### 7.2. Dữ liệu và môi trường kiểm thử

Để CI phát hiện xung đột sớm, môi trường cần **tái lập được ở mức phù hợp**:

- Phiên bản công cụ và thư viện rõ ràng, tránh “trên máy tôi dùng phiên bản khác”.
- Dữ liệu kiểm thử nhỏ, hợp lệ, có khả năng đặt lại trạng thái.
- Tài nguyên bên ngoài được mô phỏng có chủ đích cho kiểm thử phù hợp, nhưng vẫn có kiểm thử hợp đồng/tích hợp thật ở các ranh giới rủi ro.
- Secret được cấp qua cơ chế an toàn, không commit vào repository hoặc ghi vào log.
- Có khả năng quan sát log, report, artifacts và nguyên nhân thất bại.
- Môi trường dùng chung được quản lý để các test không vô tình làm ảnh hưởng lẫn nhau.

**Mock không thay thế mọi integration test.** Nếu mô phỏng API trả một cấu trúc không giống dịch vụ thật, unit test có thể xanh trong khi hệ thống thật sai. Cần chọn kiểm thử cho **đúng ranh giới có nguy cơ xung đột**.

### 7.3. Tốc độ pipeline phải phục vụ quyết định

Thay vì đặt một ngưỡng thời gian giống nhau cho mọi hệ thống, nhóm nên xem:

1. Bao lâu từ commit/push tới phản hồi đầu tiên có ích?
2. Bao lâu tới khi biết thay đổi đủ điều kiện hợp nhất?
3. Bao nhiêu thời gian nằm trong hàng đợi runner, bao nhiêu là chạy kiểm thử?
4. Kiểm tra nào phát hiện lỗi quan trọng và kiểm tra nào chỉ gây nhiễu?
5. Lỗi báo ra có đủ thông tin để sửa ngay không?

Một pipeline mất mười phút nhưng báo lỗi rõ ràng có thể hữu ích hơn pipeline mất ba phút nhưng bỏ qua hợp đồng tích hợp quan trọng. Nhóm cần cân bằng **độ nhanh, chất lượng tín hiệu và chi phí vận hành**.

## 8. Khi build chung đỏ: trách nhiệm của cả nhóm

Trong XP, trạng thái tích hợp chung cần được giữ đáng tin cậy. Khi build chung thất bại, nhóm không nên tiếp tục ghép thêm thay đổi không liên quan và hy vọng “người khác sẽ sửa sau”.

### 8.1. Quy trình phản ứng gợi ý

1. **Xác nhận thất bại:** Build thật sự lỗi hay môi trường/runner bị sự cố? Có tái hiện được không?
2. **Xác định thay đổi và phạm vi:** Commit hoặc tổ hợp thay đổi nào liên quan, kiểm tra nào thất bại?
3. **Thông báo minh bạch:** Người có liên quan biết dòng mã chung đang không đạt chuẩn.
4. **Ưu tiên khôi phục:** Sửa nhanh nếu có thể, hoặc hoàn nguyên thay đổi theo chính sách nếu cần để bảo vệ trạng thái chung.
5. **Chạy lại đúng bộ kiểm tra:** Xác nhận đã khôi phục, không chỉ “thấy UI có vẻ ổn”.
6. **Ghi bài học phù hợp:** Thêm kiểm thử hoặc thay đổi quy trình nếu đây là kiểu lỗi thường xuyên.

Không phải mọi lần build đỏ đều do commit gần nhất; có thể do dịch vụ kiểm thử, dữ liệu hoặc thư viện từ bên ngoài. **Điều tra nguyên nhân trước khi quy trách nhiệm cho cá nhân**.

### 8.2. Khi nào nên sửa, khi nào nên hoàn nguyên?

| Tình huống | Hướng xử lý có thể hợp lý |
| --- | --- |
| Lỗi đơn giản, nguyên nhân rõ, sửa được nhanh | Phối hợp sửa ngay và kiểm tra lại |
| Lỗi ảnh hưởng nhiều thành phần, chưa hiểu rõ | Cân nhắc revert thay đổi gây lỗi để giữ dòng mã chung xanh |
| Môi trường CI không sẵn sàng | Khắc phục hạ tầng và ghi trạng thái “chưa có bằng chứng kiểm tra”, không tuyên bố mã đạt |
| Flaky test | Tái hiện, điều tra và xử lý theo chính sách, không bỏ cảnh báo vĩnh viễn |
| Lỗi bảo mật hoặc dữ liệu có nguy cơ gây hại | Áp dụng quy trình an toàn và quyền hạn phù hợp, có thể dừng tích hợp/phát hành |

“Build luôn xanh” là mục tiêu giúp nhóm nhận tín hiệu đáng tin, **không phải lý do để xóa test khó hoặc đổi tiêu chuẩn Done**. Cần phân biệt lỗi thật, lỗi do môi trường và kiểm tra chưa đủ dữ liệu.

## 9. Ví dụ sâu: phát hiện xung đột ở luồng đăng ký khóa học

### 9.1. Các yêu cầu được thống nhất ban đầu

User story:

> **Là** người học đã đăng nhập, **tôi muốn** đăng ký một khóa miễn phí, **để** thấy khóa xuất hiện trong danh sách học và biết đăng ký đã thành công.

Các quy tắc nghiệp vụ minh họa:

- Chỉ tài khoản hợp lệ được đăng ký.
- Đăng ký cùng khóa nhiều lần không tạo các bản ghi đăng ký đang có hiệu lực trùng nhau.
- Không báo thành công nếu hệ thống chưa ghi nhận kết quả.
- Người học chỉ xem được danh sách đăng ký của mình.

Đây là các quy tắc **giả định của ví dụ đào tạo**, không phải quy định áp dụng cho mọi nền tảng.

### 9.2. Ba thay đổi độc lập nhưng có liên hệ

| Developer | Thay đổi dự kiến | Lỗi có thể gặp nếu tích hợp muộn |
| --- | --- | --- |
| **An — Backend** | Đổi phản hồi trạng thái từ success sang enrolled | Giao diện vẫn kiểm tra giá trị success |
| **Bình — Frontend** | Hiển thị thông báo đăng ký theo phản hồi API | Không hiện xác nhận dù bản ghi đã lưu |
| **Chi — Dữ liệu** | Bổ sung ràng buộc duy nhất cho người học và khóa | Migration thất bại trên dữ liệu trùng cũ hoặc dịch vụ xử lý ngoại lệ sai |

Nếu ba nhánh tồn tại độc lập đến cuối Sprint, nhóm có thể phải sửa đồng thời frontend, backend, schema, dữ liệu và kiểm thử.

### 9.3. Tích hợp sớm bằng lát cắt nhỏ

Một cách làm tốt hơn:

| Lượt tích hợp | Phạm vi nhỏ | Kiểm tra bắt buộc cần cân nhắc |
| --- | --- | --- |
| **1** | Thống nhất hợp đồng API mới và tương thích cần thiết | Contract test, đơn vị dữ liệu và cách biểu diễn lỗi |
| **2** | Backend trả kết quả đúng cho đăng ký hợp lệ | Unit/component test và một integration test |
| **3** | Frontend đọc đúng trạng thái và thông báo kết quả | Kiểm thử hành vi UI–API |
| **4** | Ràng buộc dữ liệu chống bản ghi trùng | Kiểm thử migration, xử lý lỗi và tính đồng thời |
| **5** | Luồng đăng ký xuyên hệ thống | Acceptance/integration test và kiểm tra DoD liên quan |

Không nhất thiết mỗi lượt tương ứng một ngày hoặc một PR; mục tiêu là **thay đổi nhỏ, tích hợp sớm và có kiểm chứng đáng tin**. Nếu một lát cắt chưa đủ giá trị độc lập, nhóm có thể tích hợp mã an toàn trước qua feature flag hoặc kế hoạch chia PBI phù hợp.

### 9.4. Ví dụ acceptance test xuyên hệ thống

~~~gherkin
Tính năng: Đăng ký khóa miễn phí

  Tình huống: Đăng ký một lần thành công
    Cho trước An đã đăng nhập hợp lệ
    Và khóa "Java nhập môn" cho phép đăng ký miễn phí
    Và An chưa đăng ký khóa đó
    Khi An chọn đăng ký "Java nhập môn"
    Thì hệ thống ghi nhận một đăng ký hợp lệ
    Và An thấy trạng thái "Đã đăng ký"
    Và khóa "Java nhập môn" xuất hiện trong danh sách khóa của An

  Tình huống: Gửi lại yêu cầu không tạo đăng ký trùng
    Cho trước An đã đăng ký "Java nhập môn"
    Khi An gửi lại yêu cầu đăng ký khóa này
    Thì hệ thống không tạo thêm một đăng ký đang có hiệu lực trùng nhau
    Và giao diện phản ánh đúng trạng thái đã đăng ký

  Tình huống: Lỗi khi ghi đăng ký không được báo thành công
    Cho trước dịch vụ không thể xác nhận việc lưu đăng ký
    Khi An yêu cầu đăng ký một khóa miễn phí
    Thì hệ thống không xác nhận đăng ký thành công giả
    Và giao diện hiển thị trạng thái lỗi phù hợp để người học biết bước tiếp theo
~~~

Các tình huống diễn đạt hành vi mong muốn; muốn chạy tự động cần có bước thực thi kiểm thử, chuẩn bị dữ liệu và môi trường phù hợp. **Viết Gherkin không tự biến thành một bộ kiểm thử chạy được.**

### 9.5. Khác biệt giữa kiểm thử đơn vị và kiểm thử tích hợp

Một unit test của backend có thể chứng minh hàm đăng ký trả trạng thái enrolled. Một unit test của frontend được mock với status success có thể chứng minh thông báo hiện với status success. **Cả hai đều xanh nhưng hệ thống ghép lại sai hợp đồng**.

Contract test hoặc integration test đúng chỗ sẽ kiểm tra frontend thực sự hiểu phản hồi backend cung cấp. Tương tự, một unit test chỉ kiểm tra truy vấn dữ liệu có thể bỏ sót migration chứa dữ liệu trùng từ trước.

**Bài học:** Không hỏi “Có bao nhiêu test xanh?”, mà hỏi **“Những ranh giới có thể xung đột đã được kiểm chứng bằng cách phù hợp chưa?”**

## 10. Tích hợp thay đổi cơ sở dữ liệu an toàn

Thay đổi schema dễ gây lỗi khi hai phiên bản ứng dụng cùng tồn tại trong lúc triển khai. Ví dụ, nếu dịch vụ mới đổi trường customer_id thành learner_id mà giao diện hoặc dịch vụ cũ còn dùng tên cũ, hệ thống có thể lỗi dù mã trên nhánh mới đã pass unit test.

Một chiến lược thường dùng cho thay đổi tương thích là **expand–migrate–contract**:

1. **Expand:** Bổ sung cấu trúc mới mà không xóa ngay cấu trúc cũ; duy trì khả năng tương thích cần thiết.
2. **Migrate:** Chuyển dần dữ liệu và cập nhật cách đọc/ghi của các thành phần; kiểm tra tính nhất quán.
3. **Contract:** Chỉ loại bỏ cấu trúc cũ sau khi chắc rằng các phiên bản liên quan không còn phụ thuộc, dữ liệu đã được chuyển và phương án khôi phục được xem xét.

~~~mermaid
flowchart TD
    A["Schema hiện tại"] --> B["Mở rộng tương thích"]
    B --> C["Ứng dụng hỗ trợ chuyển đổi"]
    C --> D["Chuyển dữ liệu và kiểm tra"]
    D --> E{"Còn client hoặc dịch vụ phụ thuộc schema cũ?"}
    E -->|"Có"| F["Tiếp tục duy trì tương thích / chuyển đổi"]
    F --> D
    E -->|"Không"| G["Loại bỏ phần cũ theo kế hoạch và kiểm chứng"]
~~~

Chiến lược này là một mẫu thiết kế cần điều chỉnh theo database, công cụ migration, khả năng rollback và cách triển khai của hệ thống; **không phải quy tắc mọi migration đều phải có ba deploy riêng**.

### 10.1. Kiểm thử migration phải xem dữ liệu thật có thể chứa gì

Nếu bổ sung ràng buộc duy nhất cho cặp (learner_id, course_id), dữ liệu hiện tại có thể đã tồn tại bản ghi trùng. Migration có thể thất bại hoặc cần chiến lược làm sạch dữ liệu đúng nghiệp vụ. Không nên tự xóa dữ liệu production vì thấy trùng; phải xác minh ý nghĩa bản ghi và quyền quyết định về dữ liệu.

Trong CI, có thể thử migration trên bộ dữ liệu đại diện đã được phép sử dụng và có khả năng đặt lại. Với thay đổi rủi ro cao, cần thêm đánh giá vận hành và phương án khôi phục.

### 10.2. Tương thích trong triển khai từng phần

Khi rolling deployment, có thể tồn tại đồng thời phiên bản cũ và mới. Hợp đồng API và schema cần được thiết kế tương thích theo khoảng chuyển đổi nếu kiến trúc yêu cầu. Kiểm thử **chỉ một phiên bản mới hoàn chỉnh** chưa chắc phát hiện sai khác giữa các phiên bản cùng tồn tại.

CI giúp kiểm tra các cấu hình và tổ hợp quan trọng, còn quyết định deploy/rollback phải có chính sách và công cụ phù hợp. Không nhất thiết mọi thay đổi CI đều được deploy ngay.

## 11. CI và bảo mật của chuỗi cung ứng phần mềm

Pipeline có quyền đọc repository, lấy dependency, chạy script và có thể tạo artifact. Vì thế **CI vừa là công cụ bảo vệ chất lượng vừa là một bề mặt cần bảo vệ**.

Một số nguyên tắc:

- **Quyền tối thiểu:** Job chỉ có quyền repository, artifact và môi trường mà nó thực sự cần.
- **Bảo vệ secret:** Không đưa token, mật khẩu, khóa riêng vào mã, dữ liệu test hoặc log; dùng cơ chế quản lý secret được phê duyệt.
- **Cẩn trọng với mã không tin cậy:** PR từ người chưa được tin cậy không nên tự động nhận secret hoặc quyền triển khai production.
- **Nguồn phụ thuộc rõ ràng:** Dùng phiên bản, kiểm tra lỗ hổng và nguồn gói theo chính sách.
- **Artifact truy vết được:** Biết build ứng với revision, cấu hình và bằng chứng kiểm tra nào.
- **Kiểm soát thay đổi cấu hình pipeline:** Review khi sửa cách chạy test, quyền runner hoặc điều kiện bỏ qua kiểm tra.
- **Cập nhật runner và công cụ:** Giảm rủi ro từ hạ tầng CI lỗi thời.

Không nên coi “pipeline xanh” là lý do để bỏ kiểm tra thủ công hoặc chuyên môn đối với thay đổi dữ liệu, bảo mật hay quyền sản phẩm có hậu quả lớn.

## 12. Kết hợp CI với Scrum, Kanban và các thực hành XP

### 12.1. Trong XP: CI bổ trợ TDD, refactoring và làm việc cặp

XP khuyến khích các vòng phản hồi ngắn:

- **TDD (Test-Driven Development):** Khi phù hợp, viết kiểm thử thể hiện hành vi trước, thực hiện đủ để pass và cải thiện cấu trúc mã.
- **Refactoring:** Cải thiện thiết kế mà không cố ý thay đổi hành vi đã được kiểm chứng.
- **Pair programming:** Giúp chia sẻ hiểu biết và phát hiện lỗi sớm ngay khi làm.
- **Simple design:** Giảm độ phức tạp không cần thiết, giữ mã dễ đổi.
- **Small releases:** Giao tăng dần để nhận phản hồi sản phẩm.
- **Continuous Integration:** Ghép và kiểm tra thay đổi thường xuyên để nhận biết xung đột.

CI không thay thế các thực hành còn lại; chính việc kiểm thử và thiết kế có thể thay đổi giúp tích hợp thường xuyên ít rủi ro hơn.

### 12.2. Trong Scrum: Increment và Definition of Done

Scrum không bắt buộc sử dụng một máy chủ CI hoặc công cụ cụ thể. Tuy nhiên, CI hỗ trợ Developers tạo **Increment có thể sử dụng, đáp ứng Definition of Done**, tránh đẩy kiểm thử/tích hợp tới ngày cuối Sprint.

Tại **Sprint Planning**, Developers cần tính công việc review, kiểm thử và tích hợp vào kế hoạch để đạt Sprint Goal. Trong **Daily Scrum**, họ có thể xem build đỏ, PR chờ review và lỗi tích hợp đang cản trở Sprint Goal; rồi điều chỉnh Sprint Backlog.

Tại **Sprint Review**, nhóm kiểm tra Increment và nhận phản hồi của stakeholder, không chỉ trình bày biểu đồ build. **Sprint Retrospective** có thể xem lại nguyên nhân nghẽn review, build flaky hoặc nhánh tích hợp quá lâu để chọn cải tiến.

Điểm cần nhớ:

> **CI xanh là bằng chứng hữu ích cho DoD, nhưng DoD có thể còn tiêu chuẩn khác. Một PBI chưa đạt DoD không được tính là phần Increment hoàn tất.**

### 12.3. Trong Kanban: giảm tuổi công việc chờ tích hợp

Một bảng Kanban có thể cho thấy:

| Cột | Công việc ví dụ | Vấn đề cần quan sát |
| --- | --- | --- |
| Sẵn sàng | Lưu khóa yêu thích | Có đủ thông tin để bắt đầu không? |
| Đang phát triển | Sửa API đăng ký | Có bao nhiêu hạng mục đang mở? |
| Chờ review / CI | Tích hợp giao diện và API | PR đã chờ bao lâu? Pipeline có đáng tin? |
| Kiểm thử tích hợp | Kiểm tra đăng ký trùng | Có môi trường, dữ liệu và quyền cần thiết? |
| Done | Luồng đăng ký đã đạt chuẩn | Kết quả có thực sự thỏa chất lượng? |

Nhóm có thể theo dõi **WIP, work item age, cycle time và throughput**. Nếu cột review/CI là nút nghẽn, kéo thêm nhiều việc vào phát triển thường không làm hệ thống giao nhanh hơn. Hành động phù hợp có thể là cùng review, giảm kích thước PR, sửa test flaky hoặc tăng khả năng chạy kiểm tra.

Giảm cycle time không tự chứng minh người học nhận nhiều giá trị hơn; cần xem cả chất lượng, yêu cầu và phản hồi thực tế.

### 12.4. Bảng so sánh vai trò của các cách tiếp cận

| Cách tiếp cận | Đóng góp trong chủ đề tích hợp sớm | Không nên nhầm |
| --- | --- | --- |
| **XP** | CI, kiểm thử, refactoring, đơn giản hóa thiết kế, giao nhỏ | Không phải chỉ “có một server build” |
| **Scrum** | Sprint Goal, Sprint Backlog, Developers tự quản, DoD và nhịp inspect/adapt | Scrum Guide không quy định bắt buộc dùng một CI tool |
| **Kanban** | Nhìn hàng chờ tích hợp, WIP, tuổi công việc, chính sách kéo | Có bảng công việc không đảm bảo CI tự động |
| **Lean** | Giảm chờ đợi và làm lại, tăng phản hồi, tối ưu dòng giá trị | Không được bỏ kiểm tra chất lượng để làm nhanh giả |

## 13. Đo chất lượng của CI mà không tạo KPI sai

Một nhóm có pipeline không cần cố đạt một con số “xanh” bằng mọi giá. Hãy chọn số liệu giúp **phát hiện nghẽn, giảm thời gian phản hồi và nâng độ tin cậy**.

| Chỉ số | Câu hỏi cần trả lời | Cảnh báo khi diễn giải |
| --- | --- | --- |
| **Tần suất tích hợp** | Mã được ghép vào nhánh chung thường xuyên tới đâu? | Nhiều commit không tự tạo nhiều giá trị |
| **Tuổi nhánh/PR** | Thay đổi thường tồn riêng trước merge bao lâu? | PR lớn có thể do phụ thuộc hoặc chính sách phê duyệt |
| **Thời gian phản hồi CI** | Bao lâu từ push đến khi biết thay đổi đạt/chưa đạt? | Cần xem cả queue time và chất lượng kiểm tra |
| **Tỷ lệ build thất bại** | Kiểu lỗi nào xảy ra thường xuyên? | Thấp giả nếu bỏ test hoặc chỉ chạy kiểm tra nông |
| **Thời gian khôi phục build chung** | Build đỏ tồn tại bao lâu trước khi được xử lý? | Phân biệt lỗi mã và lỗi hạ tầng |
| **Flaky test rate** | Bao nhiêu thất bại không ổn định, làm nhóm mất niềm tin? | Rerun tự động có thể che lỗi nếu không theo dõi |
| **Thời gian chờ review** | Code đã sẵn sàng nhưng đợi phản hồi bao lâu? | Chỉ đẩy tốc độ review mà giảm chất lượng là phản tác dụng |
| **Lỗi tích hợp thoát qua CI** | Những lỗi nào chỉ bị phát hiện ở staging/production? | Xem rủi ro và mức nghiêm trọng, không chỉ số lượng |
| **Cycle time tới Done** | Lát cắt giá trị thực sự hoàn tất nhanh hơn không? | Cần cùng định nghĩa Done và loại công việc |
| **Chất lượng sau phát hành** | Có tăng lỗi vận hành hoặc giảm sự tin cậy không? | Không dùng tốc độ merge làm kết luận sản phẩm tốt |

### 13.1. Ví dụ về thời gian feedback

Giả sử một PR có lịch sử:

| Thành phần | Thời lượng giả định |
| --- | ---: |
| Chờ runner có sẵn | 6 phút |
| Build và kiểm thử nhanh | 4 phút |
| Kiểm thử tích hợp bắt buộc | 8 phút |
| **Tổng thời gian tới phản hồi cuối** | **18 phút** |

Nếu tối ưu riêng build từ 4 xuống 3 phút, tổng còn **17 phút**. Nhưng giảm hàng đợi runner từ 6 xuống 1 phút sẽ cho tổng **13 phút** theo giả định các bước không đổi. Cần xem **toàn bộ thời gian từ push đến kết quả**, không chỉ tối ưu một lệnh biên dịch.

Đây là phép tính minh họa, không phải ngưỡng thời gian CI chuẩn áp dụng cho mọi dự án. Trong hệ thống phức tạp, các bước có thể chạy song song, khiến cách tính tổng cần xét thời gian thực trên đường găng.

### 13.2. Đo ở cấp hệ thống, không thưởng/phạt số lần commit

Nếu cá nhân bị thưởng theo số commit hoặc số PR merge, họ có thể chia thay đổi thành những mảnh vô nghĩa, bỏ review hoặc tránh các công việc bảo trì khó. CI là **năng lực chung của đội**, không phải thước đo năng suất của một người.

Một chỉ số có ích phải dẫn đến câu hỏi cải tiến cụ thể: “Tại sao review chờ lâu?”, “Những test nào không đáng tin?”, “Đường tích hợp nào chưa được kiểm chứng?”.

## 14. Những sai lầm phổ biến khi áp dụng CI

**1. Có pipeline nhưng vẫn tích hợp một lần cuối Sprint.** Kiểm tra trên các nhánh riêng không tự phát hiện mọi xung đột khi hợp nhất. Cần đổi nhịp tích hợp.

**2. Coi CI đồng nghĩa với continuous deployment.** CI giúp hợp nhất và kiểm chứng mã; phát hành tự động là quyết định và năng lực khác.

**3. Chỉ chạy build, bỏ các kiểm thử hành vi quan trọng.** Biên dịch thành công không có nghĩa API, database và giao diện phối hợp đúng.

**4. Chạy unit test toàn bộ nhưng không kiểm tra hợp đồng giữa thành phần.** Mock có thể dựa trên giả định cũ; cần kiểm thử ranh giới thích hợp.

**5. Đợi cuối Sprint mới tích hợp database migration.** Schema, dữ liệu và các phiên bản ứng dụng có thể trở nên không tương thích.

**6. Giữ nhánh lớn nhiều tuần vì “sợ merge nhiều lần”.** Xung đột và chi phí làm lại có thể tăng; nên tìm cách chia lát cắt và tích hợp an toàn hơn.

**7. Bỏ qua build đỏ rồi tiếp tục đẩy việc mới.** Trạng thái chung mất tin cậy; nhóm khó biết thay đổi sau gây lỗi gì.

**8. Rerun test flaky vô hạn cho tới lúc xanh.** Kết quả không ổn định vẫn là vấn đề chất lượng pipeline cần xử lý.

**9. Hạ điều kiện DoD để làm biểu đồ CI đẹp.** Việc chưa đạt chuẩn không được gọi là Done chỉ vì bỏ bước kiểm tra.

**10. Dùng feature flag như lời biện hộ cho mã chưa được kiểm chứng.** Flag giảm phạm vi hiển thị tính năng nhưng không miễn kiểm thử, quản lý tổ hợp và bảo mật.

**11. Mỗi Developer một môi trường độc lập không tái lập được.** Môi trường chung có thể phát hiện lỗi khác; cần cấu hình và dependency nhất quán.

**12. Đưa secret thật vào log hoặc test fixture.** CI không được đánh đổi an toàn dữ liệu để tiện chạy test.

**13. Tất cả kiểm thử chạy nối tiếp dù không cần thiết.** Pipeline quá chậm làm feedback muộn; nên chọn các bước bắt buộc và tổ chức song song khi an toàn.

**14. Chỉ tối ưu thời gian chạy, bỏ độ tin cậy.** Pipeline cực nhanh mà không phát hiện lỗi hợp đồng trọng yếu không đạt mục tiêu.

**15. Coi mọi lỗi CI là lỗi của Developer vừa commit.** Cần phân biệt code, dữ liệu, runner, dịch vụ ngoài và trạng thái tích hợp.

**16. Không kiểm tra trạng thái sau merge.** Hai PR riêng đều xanh có thể tương tác gây lỗi ở nhánh chung.

**17. Tăng số lượng test mà không xem chất lượng tín hiệu.** Kiểm tra trùng lặp và không ổn định có thể tăng chi phí mà ít phát hiện lỗi mới.

**18. Chỉ quan tâm “test xanh”, không nhìn người dùng.** CI giúp đảm bảo hành vi đã kiểm tra; vẫn cần xác nhận sản phẩm giải quyết đúng nhu cầu.

## 15. Bài tập tình huống: ba nhánh mã chuẩn bị hợp nhất

Một Scrum Team sử dụng thực hành XP đang tạo khả năng đăng ký khóa học miễn phí. Sprint Goal là **“người học đã đăng nhập có thể đăng ký khóa miễn phí và thấy trạng thái đăng ký đáng tin cậy”**.

Nhóm có ba PR:

| PR | Nội dung | Kiểm tra hiện tại |
| --- | --- | --- |
| **PR-A** | Backend đổi giá trị status từ success thành enrolled | Unit test backend xanh |
| **PR-B** | Frontend hiện xác nhận nếu status là success | Unit test frontend dùng mock cũ xanh |
| **PR-C** | Migration thêm ràng buộc duy nhất cho đăng ký | Test trên cơ sở dữ liệu sạch xanh |

Các PR tồn tại riêng **sáu ngày**, dự kiến sẽ hợp nhất vào cuối Sprint. Bộ kiểm thử CI hiện chỉ có build và unit test độc lập. Môi trường staging chứa vài đăng ký trùng được tạo từ phiên bản cũ.

### Câu hỏi

1. Vì sao cả ba PR xanh riêng lẻ mà luồng đăng ký sau merge vẫn có thể lỗi?
2. Có những loại xung đột nào trong tình huống này? Phân biệt merge conflict với semantic/contract/data conflict.
3. Developers cần bổ sung **ít nhất bốn kiểm tra hoặc hành động** để nhận phản hồi sớm hơn?
4. Làm thế nào để hợp nhất từng lát cắt nhỏ mà không buộc người dùng thấy tính năng chưa hoàn chỉnh?
5. Nếu migration thất bại vì dữ liệu trùng, có nên xóa ngay tất cả bản ghi trùng không? Vì sao?
6. Nếu CI trên nhánh chung đỏ, nhóm nên làm gì trước khi tiếp tục hợp nhất việc mới?
7. Trong Daily Scrum, nhóm nên dùng thông tin CI để điều chỉnh kế hoạch hướng Sprint Goal như thế nào?
8. Đề xuất hai chỉ số giúp biết cách làm mới có cải thiện khả năng tích hợp không.

### Gợi ý lời giải

**Câu 1:** Unit test frontend chỉ kiểm tra mock cũ; backend dùng hợp đồng mới. Khi ghép, giao diện có thể không hiện xác nhận. Migration được thử trên database sạch nên chưa gặp bản ghi trùng tồn tại thật. Xanh riêng lẻ không chứng minh hành vi tích hợp đã đúng.

**Câu 2:** Không nhất thiết có merge conflict vì ba PR có thể sửa những tệp khác nhau. **Contract/semantic conflict** là không khớp trạng thái success và enrolled; **data/schema conflict** là migration áp ràng buộc lên dữ liệu cũ chưa được xử lý. Còn có rủi ro tương thích giữa các phiên bản khi triển khai.

**Câu 3:** Có thể:

1. Thống nhất và kiểm thử hợp đồng API giữa frontend/backend.
2. Chạy integration test xuyên luồng đăng ký và hiển thị xác nhận.
3. Thử migration trên bộ dữ liệu được phép dùng có các trường hợp trùng có chủ đích.
4. Kiểm tra tính idempotent và quyền dữ liệu ở mức dịch vụ/DB cần thiết.
5. Giảm kích thước PR, đồng bộ nhánh chung, hợp nhất từng thay đổi tương thích thường xuyên hơn.
6. Kiểm tra trạng thái sau merge hoặc dùng cơ chế kiểm tra tổ hợp thay đổi trước merge khi phù hợp.

**Câu 4:** Có thể dùng **nhánh ngắn**, chia lát cắt có thể kiểm chứng, giữ hợp đồng tương thích và dùng **feature flag** theo chính sách để tránh bật sớm phần giao diện chưa hoàn chỉnh. Flag vẫn cần kiểm thử và dọn bỏ khi không còn cần.

**Câu 5:** Không. Cần làm rõ ý nghĩa các bản ghi trùng, quy tắc nghiệp vụ và quyền xử lý dữ liệu. Có thể cần migration theo giai đoạn, xử lý dữ liệu có kiểm soát, đo tác động và phương án khôi phục; không tự xóa dữ liệu production chỉ để build xanh.

**Câu 6:** Minh bạch trạng thái, tìm nguyên nhân, ưu tiên sửa hoặc hoàn nguyên theo chính sách, sau đó chạy lại kiểm tra phù hợp. Không được bỏ test quan trọng hoặc chấp nhận nhánh chung đỏ vô thời hạn.

**Câu 7:** Developers nên thấy PR chờ sáu ngày và rủi ro tới Sprint Goal; thay vì mở tính năng mới, họ có thể cùng kiểm tra hợp đồng, chuẩn bị dữ liệu tích hợp, review, sửa migration và ưu tiên tạo Increment đáp ứng DoD. Nếu phạm vi cần thay đổi, cộng tác với Product Owner.

**Câu 8:** Ví dụ **tuổi PR/thời gian chờ review** và **thời gian từ push tới kết quả CI**; bổ sung **thời gian khôi phục build chung** hoặc **số lỗi tích hợp thoát sang staging** sẽ cho góc nhìn toàn diện hơn. Không dùng số commit của cá nhân làm thước đo giá trị.

## 16. Bài tập thiết kế CI cho một lát cắt mới

Nhóm chuẩn bị tạo user story:

> “Là người học đã đăng nhập, tôi muốn lưu khóa học yêu thích để có thể quay lại trước khi quyết định đăng ký.”

Hãy tự thiết kế:

1. **Lát cắt đầu tiên:** Chức năng nhỏ nhất tạo giá trị gì và sẽ được tích hợp ra sao?
2. **Một hợp đồng API:** Dữ liệu đầu vào, phản hồi thành công và trường hợp lỗi nào cần được các bên thống nhất?
3. **Hai unit test:** Quy tắc cục bộ nào phải được bảo vệ?
4. **Hai integration/acceptance test:** Ranh giới nào cần kiểm tra khi UI, API và dữ liệu kết hợp?
5. **Điểm phát hiện xung đột:** Test nào sẽ phát hiện nếu backend đổi hợp đồng nhưng frontend chưa cập nhật?
6. **Điều kiện hợp nhất:** Kiểm tra nào phải đạt trước merge và kiểm tra gì sau merge?
7. **Khi build đỏ:** Nhóm phản ứng, thông báo và khôi phục ra sao?

### Gợi ý đối chiếu

| Thành phần | Ví dụ đáp án |
| --- | --- |
| Lát cắt đầu tiên | Người học đã đăng nhập lưu một khóa và thấy trạng thái đã lưu |
| Hợp đồng API | Yêu cầu chứa courseId hợp lệ; phản hồi xác nhận trạng thái; lỗi quyền/trạng thái dịch vụ được mô tả |
| Unit test 1 | Lưu lại khóa đã lưu không tạo mục trùng theo quy tắc nghiệp vụ |
| Unit test 2 | Tài khoản không hợp lệ bị từ chối theo cơ chế phân quyền |
| Integration test 1 | UI gửi yêu cầu qua API, dữ liệu được ghi và UI hiện đúng trạng thái |
| Integration test 2 | Lỗi lưu không khiến UI báo thành công giả; dữ liệu không bị cập nhật sai |
| Phát hiện đổi hợp đồng | Contract test hoặc integration test từ consumer tới provider |
| Gate | Build, unit test, contract/integration test liên quan và các kiểm tra bắt buộc theo DoD |
| Phục hồi build | Điều tra, sửa hoặc revert, kiểm tra trạng thái chung và thông báo kết quả |

Đáp án là **một cách thiết kế**, không phải bắt buộc mọi nhóm phải có đúng số loại test hoặc cấu trúc pipeline như vậy.

## 17. Checklist áp dụng CI trong nhóm XP

**Trước khi tạo thay đổi:**

1. **Giá trị:** Thay đổi đang phục vụ user story, lỗi hoặc rủi ro nào?
2. **Kích thước:** Có thể tách thành phần đủ nhỏ để review và tích hợp sớm không?
3. **Hợp đồng:** Có API, dữ liệu hoặc phiên bản khác đang dựa trên giả định liên quan không?
4. **Kiểm chứng:** Hành vi cốt lõi và trường hợp lỗi cần kiểm thử là gì?
5. **Ranh giới an toàn:** Có dữ liệu nhạy cảm, quyền truy cập hoặc nghĩa vụ cần tôn trọng không?

**Trong khi phát triển và hợp nhất:**

6. **Đồng bộ:** Nhánh làm việc có cập nhật với dòng mã chung đủ thường xuyên không?
7. **Kiểm tra cục bộ:** Các kiểm tra nhanh có chạy được trước khi gửi thay đổi không?
8. **Pipeline:** CI có build từ revision rõ ràng, chạy test đáng tin và báo kết quả dễ hiểu không?
9. **Tích hợp thật:** Có kiểm tra hợp đồng và hành vi ở ranh giới nhiều thành phần không?
10. **Sau hợp nhất:** Trạng thái chung có được xác minh và vẫn đáng tin cậy không?
11. **Phản ứng:** Khi build đỏ, nhóm có xử lý sớm thay vì tiếp tục chất thay đổi không?
12. **Chất lượng:** Có giữ Definition of Done và yêu cầu an toàn khi chia lát cắt không?

**Khi cải tiến:**

13. **Hàng chờ:** PR, review và CI có đang làm work item age tăng không?
14. **Tốc độ:** Từ push tới phản hồi hữu ích mất bao lâu, nghẽn ở đâu?
15. **Độ tin cậy:** Flaky test và lỗi môi trường đã được theo dõi, khắc phục chưa?
16. **Dữ liệu:** Kiểm thử migration và tương thích khi nhiều phiên bản cùng chạy có phù hợp không?
17. **Bảo mật:** Secret, quyền runner, mã PR và artifact có được bảo vệ không?
18. **Outcome:** Các phần tăng dần sau khi tích hợp có thực sự giúp người dùng đạt kết quả mong muốn không?

## 18. Tổng kết: tích hợp nhỏ, phản hồi nhanh, chất lượng chung

Tích hợp liên tục trong XP đem lại lợi ích quan trọng nhất khi **nhóm thay đổi hành vi làm việc**, chứ không phải chỉ bật một dịch vụ CI:

| Khi tích hợp muộn | Khi tích hợp liên tục có kỷ luật |
| --- | --- |
| Các nhánh phát triển xa nhau nhiều ngày hoặc nhiều tuần | Thay đổi nhỏ được đồng bộ và hợp nhất thường xuyên |
| Phát hiện xung đột khi gần hết Sprint | Phát hiện xung đột gần thời điểm tạo ra |
| Không biết lỗi đến từ sự kết hợp thay đổi nào | Phạm vi thay đổi nhỏ giúp tìm và sửa dễ hơn |
| API, schema và UI dựa trên giả định khác nhau | Hợp đồng và luồng tích hợp được kiểm chứng liên tục |
| Review và kiểm thử dồn cuối kỳ | Kiểm thử, review và tích hợp diễn ra xuyên suốt |
| “Chạy trên máy tôi” là căn cứ chính | Mã chung có bằng chứng build và kiểm thử đáng tin |
| Build đỏ tồn tại lâu, nhóm tiếp tục mở việc | Cả nhóm ưu tiên khôi phục trạng thái chung |
| Báo “code xong” dù chưa tạo Increment | Đo lường hướng tới phần sản phẩm đáp ứng DoD và giá trị |

**Ghi nhớ:** CI giúp **phát hiện xung đột sớm bằng tích hợp thường xuyên, kiểm tra tự động đáng tin và xử lý nhanh khi trạng thái chung lỗi**. Xung đột có thể nằm ở mã, hành vi, hợp đồng API, dữ liệu, phụ thuộc hoặc môi trường — không chỉ ở Git merge. Kết hợp CI với kiểm thử, refactoring, cộng tác và các phần giao nhỏ của XP giúp nhóm giảm làm lại, bảo vệ chất lượng và tạo Increment sớm hơn. Khi liên hệ với Scrum, Kanban và backlog, hãy đo tiến độ bằng **giá trị hoàn tất và phản hồi thật**, không chỉ số commit hay số đèn xanh của pipeline.
