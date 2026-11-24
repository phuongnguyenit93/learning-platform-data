# Kết hợp cách lập kế hoạch dự báo và thích ứng khi có ràng buộc cụ thể

## 1. Một dự án, hai nhu cầu lập kế hoạch tưởng như đối lập

Một đơn vị đào tạo muốn đưa nền tảng học trực tuyến vào sử dụng trước ngày khai giảng. Dự án có ba điều kiện:

- **Ngày khai giảng đã công bố:** Luồng đăng ký và mở bài phải đủ tin cậy trước mốc đó.
- **Ngân sách và hợp đồng có giới hạn:** Có danh mục đầu ra, tiêu chí nghiệm thu và người được phép phê duyệt thay đổi.
- **Hành vi người học chưa được hiểu hết:** Chưa rõ người học có cần email xác nhận, dashboard gợi ý hay đường dẫn trực tiếp tới bài đầu.

Nếu lập chi tiết mọi màn hình, API và task cho toàn bộ 12 tuần từ ngày đầu rồi từ chối mọi phản hồi, nhóm có thể giao đúng những gì đã đoán nhưng **người học vẫn không bắt đầu được khóa học**. Nếu ngược lại, nhóm cho phép thay đổi liên tục mà không theo dõi mốc, chi phí và nghĩa vụ, **ngày khai giảng hoặc điều kiện nghiệm thu có thể bị vi phạm**.

Vậy chọn cách nào?

**Không nhất thiết phải chọn một cực.** Có thể giữ kế hoạch dự báo đối với **điều đã biết, phụ thuộc quan trọng và cam kết bắt buộc**, đồng thời dùng kế hoạch thích ứng đối với **giải pháp còn bất định, phạm vi có thể ưu tiên và các giả thuyết cần thử**.

Trong chương **Lựa chọn cách tiếp cận** thuộc module **AGILE_DEVELOPMENT**, bài này hướng dẫn phối hợp các kỹ thuật lập kế hoạch mà vẫn giữ các nguyên tắc Agile: phản hồi sớm, giao tăng dần, hợp tác với khách hàng và cải tiến liên tục. Các công cụ **user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc** được dùng để thực hiện kế hoạch có khả năng thích ứng; kế hoạch dự báo hỗ trợ quản trị những ràng buộc không thể làm ngơ.

**Nguyên tắc cốt lõi:** *Cố định những điều thực sự bắt buộc, dự báo những điều có thể ước lượng, kiểm chứng những điều chưa biết và thay đổi trong đúng thẩm quyền.*

## 2. Ba cách lập kế hoạch: dự báo, thích ứng và kết hợp

### 2.1. Lập kế hoạch dự báo (predictive planning)

**Predictive** thường bắt đầu bằng việc làm rõ đáng kể phạm vi, đầu ra, chuỗi phụ thuộc, nguồn lực, mốc và kế hoạch thực hiện trước khi triển khai. Kế hoạch được cập nhật có kiểm soát khi có thay đổi.

Phù hợp hơn khi:

- Đầu ra ổn định và được mô tả đủ rõ.
- Phụ thuộc bên ngoài có lịch và thủ tục cố định.
- Thiết bị, hạ tầng, phê duyệt hoặc kiểm tra cần đặt lịch từ sớm.
- Bằng chứng nghiệm thu phải truy vết theo một baseline.
- Việc thử sai tốn chi phí hoặc tác động lớn, cần đánh giá trước.

**Ưu điểm:** Minh bạch mốc, trách nhiệm, ngân sách và quan hệ phụ thuộc; thuận lợi để báo cáo nghĩa vụ.

**Hạn chế:** Nếu giả định về nhu cầu hoặc giải pháp còn sai, kế hoạch chi tiết có thể nhanh chóng lỗi thời. Dự báo chi tiết không tự tạo ra sự chắc chắn.

### 2.2. Lập kế hoạch thích ứng (adaptive planning)

**Adaptive** dùng các vòng phản hồi và lập kế hoạch theo mức thông tin hiện có. Nhóm giữ **mục tiêu rõ**, hoàn tất những lát cắt nhỏ, quan sát kết quả rồi điều chỉnh thứ tự và cách thực hiện.

Phù hợp hơn khi:

- Nhu cầu người dùng cần được kiểm chứng bằng trải nghiệm thật.
- Cách triển khai hoặc thiết kế còn nhiều lựa chọn.
- Thay đổi có thể được tích hợp, kiểm thử và phát hành tăng dần.
- Chi phí thử nghiệm nhỏ và khả năng sửa hướng tương đối tốt.
- Product Backlog có phần linh hoạt trong phạm vi thẩm quyền.

**Ưu điểm:** Học sớm, giảm đầu tư lớn vào giải pháp sai, nhận giá trị từng phần.

**Hạn chế:** Nếu không quản trị mốc, chi phí, phụ thuộc và chuẩn bắt buộc, nhóm có thể tạo nhiều thí nghiệm nhưng không đáp ứng một nghĩa vụ quan trọng.

### 2.3. Lập kế hoạch kết hợp (hybrid planning)

**Hybrid** là cách phối hợp có chủ đích giữa:

1. Kế hoạch ở **cấp cam kết, giới hạn và sự kiện bắt buộc**.
2. Kế hoạch tăng dần ở **cấp giải pháp, thứ tự thực hiện và học hỏi**.
3. Cơ chế **quyết định, đồng bộ và kiểm soát thay đổi** kết nối hai cấp.

Hybrid **không phải tên một framework Scrum chính thức** và cũng không có một công thức áp dụng cho mọi dự án. Một tổ chức có thể dùng kế hoạch mốc theo tháng, Product Backlog có thứ tự, Sprint hai tuần, Kanban cho hỗ trợ vận hành và CI/XP cho kỹ thuật mà không cần tạo thêm hàng loạt nghi lễ.

| Câu hỏi | Predictive | Adaptive | Kết hợp hợp lý |
| --- | --- | --- | --- |
| **Đích và nghĩa vụ** | Xác định baseline và mốc | Xác định outcome, điều chỉnh theo học hỏi | Giữ nghĩa vụ thật, học về cách đạt outcome |
| **Phạm vi chi tiết** | Xác định sớm khi đủ thông tin | Làm rõ dần theo ưu tiên | Cố định phần bắt buộc, làm rõ dần phần còn bất định |
| **Dự báo** | Theo lịch, nguồn lực, phụ thuộc | Theo throughput/cycle time và dữ liệu thực | Đối chiếu dự báo thực tế với mốc/budget |
| **Kiểm tra** | Theo mốc kiểm soát | Liên tục qua Increment/feedback | Bằng chứng chất lượng thường xuyên cho cả hai |
| **Thay đổi** | Change control theo baseline | Backlog inspection/adaptation | Phân loại thay đổi theo quyền, không đồng nhất hai loại |
| **Rủi ro chính** | Cứng nhắc trước thông tin mới | Chệch khỏi nghĩa vụ cứng | Tạo hai hệ báo cáo mâu thuẫn hoặc nhiều tầng duyệt |

## 3. Đừng lựa chọn bằng nhãn “dự án Agile hay không Agile”

Câu hỏi “dự án nên dùng Waterfall hay Agile?” thường quá rộng. **Các phần khác nhau của cùng một dự án có thể có mức bất định và ràng buộc khác nhau**.

Ví dụ nền tảng học:

| Hạng mục | Tính chất | Cách lập kế hoạch nên cân nhắc |
| --- | --- | --- |
| Ngày khai giảng đã công bố | Ràng buộc thời gian | Kế hoạch mốc và phương án ứng phó rõ |
| Quyền truy cập dữ liệu người học | Kiểm soát an toàn bắt buộc | Yêu cầu, kiểm thử, phê duyệt theo quyền và bằng chứng |
| Mua máy chủ chuyên biệt | Lead time nhà cung cấp và thủ tục | Lập lịch, đặt hàng, theo dõi mốc từ sớm |
| Trải nghiệm sau đăng ký | Nhu cầu/chọn giải pháp chưa chắc | Prototype, user story, phản hồi sớm |
| Cơ chế chống đăng ký trùng | Bất biến nghiệp vụ và rủi ro kỹ thuật | Thử nghiệm kỹ thuật sớm + test giao dịch |
| Báo cáo quản trị theo hợp đồng | Đầu ra được mô tả | Truy vết baseline, chia lát cắt Done, kiểm tra mốc |
| Gợi ý khóa cá nhân hóa | Giá trị chưa được kiểm chứng | Thử nhỏ nếu trong phạm vi/quyền; không cam kết lớn |
| Hỗ trợ lỗi production | Nhu cầu đến không đều | Kanban, phân loại mức độ khẩn và giới hạn WIP |

**Chọn cách lập kế hoạch theo đặc tính công việc**, không theo danh tiếng của một phương pháp hay áp lực “phải Agile 100%”.

## 4. Hai trục quyết định: mức bất định và mức ràng buộc

Một bản đồ hai chiều hữu ích khi quyết định:

- **Bất định:** Ta hiểu nhu cầu và giải pháp đến đâu? Có khả năng học từ phản hồi không?
- **Ràng buộc:** Thời gian, giá, phạm vi, quy định, công nghệ hoặc bên ngoài có thể điều chỉnh tới đâu?

| | **Ràng buộc ít/có thể điều chỉnh** | **Ràng buộc cao/khó điều chỉnh** |
| --- | --- | --- |
| **Bất định thấp** | Có thể lập kế hoạch đơn giản, giao nhanh; tránh nghi thức thừa | Dự báo và kiểm soát mốc, vẫn tích hợp/kiểm thử sớm |
| **Bất định cao** | Thử nghiệm, discovery, backlog thích ứng | **Hybrid có kiểm soát:** làm rõ giả định sớm, bảo vệ mốc bắt buộc, giữ cửa quyết định và dự báo minh bạch |

### 4.1. Tách bất định nhu cầu và bất định kỹ thuật

**Bất định nhu cầu:** Người học có muốn email hay chỉ cần xác nhận trong app?

**Bất định kỹ thuật:** API của hệ thống tài khoản khách hàng có chịu được retry và luồng phân quyền mới?

Hai loại cần cách học khác nhau:

- Với nhu cầu: phỏng vấn, usability test, đo activation, prototype.
- Với kỹ thuật: spike, contract/integration test, thử dữ liệu, proof of concept trên môi trường cho phép.

Nếu không phân biệt, nhóm có thể làm prototype giao diện để giải vấn đề **tính nhất quán dữ liệu**, hoặc dùng spike kỹ thuật để quyết định **giá trị người dùng**.

### 4.2. Cần nhìn độ đảo ngược của quyết định

Một thay đổi câu chữ giao diện có thể dễ hoàn nguyên. Một migration phá cấu trúc dữ liệu hàng triệu bản ghi hoặc một hợp đồng mua máy chủ có thể rất khó đảo ngược.

Với quyết định khó đảo ngược, nên đầu tư thêm **kiểm chứng và bằng chứng trước khi cam kết**, dù nhóm đang dùng Scrum và giao tăng dần.

### 4.3. Bản đồ là công cụ thảo luận, không là máy chọn phương pháp

Không nên cho mỗi trục điểm 1–5 rồi kết luận “3,8 điểm = phải dùng hybrid”. Đánh giá định tính giúp phát hiện giả định; quyết định cuối cần xét con người, kỹ năng, hệ thống, chi phí thử, quyền phê duyệt và hậu quả sai.

## 5. Phân loại ràng buộc trước khi đặt kế hoạch

Một ràng buộc có thể là **bất biến bắt buộc**, một mục tiêu có thể thương lượng hoặc chỉ là giả định chưa được xác minh. Nhầm ba loại khiến kế hoạch bị cứng không cần thiết hoặc vi phạm điều không thể đổi.

| Ràng buộc | Ví dụ | Điều nên xác minh |
| --- | --- | --- |
| **Thời hạn ngoài nhóm** | Ngày khai giảng đã công bố | Có thể ra mắt từng phần? Hậu quả nếu không đạt? |
| **Ngân sách trần** | Tổng chi phí đã được duyệt | Phạm vi điều chỉnh bên trong, cơ chế xin bổ sung? |
| **Phạm vi hợp đồng** | Báo cáo quản trị là đầu ra bắt buộc | Điều khoản nào được phép hoán đổi? Ai duyệt? |
| **An toàn và quyền dữ liệu** | Không cho tài khoản A xem đăng ký của B | Kiểm tra và quyền phê duyệt bắt buộc nào? |
| **Công nghệ/kiến trúc** | Phải tích hợp với hệ thống tài khoản hiện hữu | Tài liệu, API, môi trường và quyền tiếp cận thực tế? |
| **Nhà cung cấp thứ ba** | Chờ sandbox hoặc thiết bị | Lead time, rủi ro trễ, phương án dự phòng? |
| **Năng lực nhóm** | Một người có quyền migration production | Kế hoạch hỗ trợ, học kỹ năng và kiểm soát phù hợp? |
| **Chất lượng sản phẩm** | Increment phải đạt DoD | Bằng chứng chất lượng cần trong từng lát cắt? |
| **Mục tiêu kinh doanh** | Muốn tăng activation người học | Là kết quả mong muốn hay điều khoản bất biến? |

### 5.1. Khác biệt giữa mục tiêu, dự báo và cam kết

- **Mục tiêu:** Điều tổ chức muốn đạt, ví dụ tăng tỷ lệ người học bắt đầu bài đầu.
- **Dự báo:** Kết quả có thể xảy ra theo dữ liệu, giả định và bất định hiện tại.
- **Cam kết/nghĩa vụ:** Điều phải thực hiện theo thỏa thuận, trách nhiệm hoặc luật/quy định áp dụng.

Không được sửa dự báo cho đẹp mốc mục tiêu. Cũng không được mặc định một dự báo quá hạn **tự cho phép** điều chỉnh nghĩa vụ.

### 5.2. “Không thương lượng được” cần có căn cứ

Nếu một stakeholder nói “phạm vi phải giữ nguyên”, nhóm nên hỏi **phạm vi nào, theo điều khoản hoặc quyền nào**. Một số thứ không thể đổi; một số khác có thể điều chỉnh bằng thủ tục. Hỏi để hiểu ranh giới **khác với tìm cách lách ràng buộc**.

## 6. Thiết kế ba tầng kế hoạch thay vì một lịch chi tiết duy nhất

Một mô hình thực hành là **kế hoạch ba tầng**:

1. **Tầng cam kết/governance:** Mục tiêu, giới hạn, mốc, nghĩa vụ, quyền và tiêu chí chất lượng.
2. **Tầng định hướng/rolling-wave:** Các khả năng sản phẩm, phụ thuộc, rủi ro và dự báo theo khoảng thời gian.
3. **Tầng thực thi/thích ứng:** Product Backlog, Sprint Backlog, Kanban workflow, kiểm thử và phản hồi hằng ngày.

~~~mermaid
flowchart TD
    A["Tầng 1: Nghĩa vụ, mốc, ngân sách, quyền"] --> B["Tầng 2: Roadmap, phụ thuộc, dự báo theo đợt"]
    B --> C["Tầng 3: User stories, Sprint/Kanban, kiểm thử"]
    C --> D["Increment Done và phản hồi sử dụng"]
    D --> E["Dữ liệu thực: chất lượng, throughput, rủi ro"]
    E --> B
    E --> F{"Có thay đổi vượt quyền/baseline?"}
    F -->|"Không"| C
    F -->|"Có"| G["Change control và quyết định có thẩm quyền"]
    G --> A
~~~

Các tầng cần trao đổi hai chiều. Nếu tầng thực thi phát hiện API bên ngoài không hoạt động, **kế hoạch mốc** phải nhận thông tin mới. Nếu mốc chính thức được điều chỉnh hợp lệ, **roadmap và backlog** phải được cập nhật.

### 6.1. Không tạo ba “nguồn sự thật” mâu thuẫn

Một lỗi thường gặp là có ba bảng:

- Hợp đồng nói phải giao báo cáo A.
- Roadmap ghi sẽ làm dashboard B.
- Product Backlog chỉ chứa các task xây API C.

Không ai biết A đã bị thay thế hợp lệ chưa. Cần **truy vết mức đủ dùng**, người có quyền quyết định rõ và ghi lại khi baseline thay đổi.

### 6.2. Mỗi tầng cần độ chi tiết khác nhau

Không cần liệt kê mọi unit test cho sáu tháng tới. Nhưng cần biết **mốc xin quyền dữ liệu ở tuần nào**, vì chậm quyền có thể ảnh hưởng toàn bộ kiểm thử tích hợp.

**Chi tiết ở nơi quyết định khó đảo ngược và rủi ro lớn; linh hoạt ở nơi thông tin sẽ tăng nhờ thực hiện.**

## 7. Rolling-wave planning: chi tiết gần, định hướng xa

**Rolling-wave planning** nghĩa là lập kế hoạch chi tiết cho phần công việc gần và đủ rõ, trong khi những phần xa hơn giữ ở mức khả năng, phụ thuộc, giả định và khoảng dự báo. Sau mỗi vòng học, cập nhật kế hoạch kế tiếp.

Ví dụ dự án 12 tuần:

| Khoảng | Mức thông tin hợp lý | Ví dụ |
| --- | --- | --- |
| **Tuần 1–2** | PBI rõ, acceptance examples, test, phụ thuộc gần | Đăng ký miễn phí và xác nhận đúng |
| **Tuần 3–4** | Những lát cắt dự kiến; làm rõ dần | Mở bài đầu, kiểm thử quyền |
| **Tuần 5–8** | Khả năng dự kiến, mốc chất lượng, phụ thuộc | Tiến độ học, báo cáo cơ bản |
| **Tuần 9–12** | Mốc nghiệm thu, rủi ro và contingency; chi tiết sẽ tới sau | Kiểm thử hệ thống, tài liệu, bàn giao |

**Lưu ý:** Nếu hợp đồng đã cố định toàn bộ các đầu ra, rolling-wave **không có nghĩa đầu ra ở tuần 9–12 là tùy chọn**. Nó chỉ cho phép chưa quyết định cách thực hiện chi tiết cho tới khi có đủ thông tin.

### 7.1. Cửa sổ kế hoạch dịch chuyển

Sau Sprint đầu tiên, nhóm đã biết:

- Trạng thái timeout khó hơn dự kiến.
- Người học khó tìm nút mở bài.
- API xác thực ngoài nhóm cần thêm kiểm tra.

Kế hoạch gần được chỉnh: ưu tiên sửa lỗi và kiểm chứng quyền. Kế hoạch xa được **đánh giá lại về tác động tới mốc**, không giữ biểu đồ cũ như thể thông tin chưa thay đổi.

### 7.2. Tránh “kế hoạch không bao giờ được cập nhật”

Nếu mọi người đã biết luồng tích hợp mất thêm hai tuần nhưng roadmap vẫn ghi xanh theo ngày ban đầu, kế hoạch đã mất chức năng hỗ trợ quyết định. Giữ baseline gốc để **truy vết nghĩa vụ**, nhưng cập nhật **forecast mới** và phân tích chênh lệch.

### 7.3. Cũng tránh “tuần nào cũng làm lại toàn bộ kế hoạch”

Không phải thông tin mới nào cũng cần tái lập mọi mốc. Chỉ cập nhật nơi có tác động đến quyết định, rủi ro, phạm vi hoặc nguồn lực; tránh chi phí quản trị lớn hơn lợi ích.

## 8. Baseline, forecast và backlog: ba dữ liệu không được nhầm

| Khái niệm | Dùng để làm gì | Ví dụ |
| --- | --- | --- |
| **Baseline được chấp thuận** | Xác định nghĩa vụ/giới hạn và điểm đối chiếu | Hợp đồng phải có H-01 đến H-06 trước mốc cuối |
| **Forecast hiện thời** | Dự kiến có thể đạt gì/khi nào theo thông tin hiện có | H-04 có nguy cơ chậm nếu môi trường chưa sẵn |
| **Product Backlog** | Danh sách có thứ tự điều cần để cải thiện sản phẩm | Lát cắt đăng ký, mở bài, tiến độ, báo cáo |
| **Sprint Backlog** | Sprint Goal, PBI đã chọn và kế hoạch do Developers quản lý | Lát cắt đăng ký và test chống trùng |
| **Risk/decision log** | Theo dõi giả định, blocker, chủ thể quyết định | Chờ quyền API, CR đổi báo cáo |

### 8.1. Ví dụ một chênh lệch kế hoạch

Baseline: “Bàn giao tích hợp tài khoản trước cuối tuần 6”.

Forecast tuần 3: “Với API hiện có và lịch cấp sandbox, kiểm thử tích hợp có thể hoàn tất **sau tuần 6**; độ bất định còn lớn.”

Hành động đúng: Làm rõ phụ thuộc, thử contract test, cập nhật kế hoạch và **escalate** theo quyền. Không sửa baseline thành “tuần 8” rồi coi như không có vấn đề.

### 8.2. Backlog có thể thích ứng mà vẫn truy vết phạm vi

Một bảng liên kết gọn:

| Mã nghĩa vụ | Hành vi/đầu ra | PBI liên quan | Tình trạng theo DoD | Rủi ro mốc |
| --- | --- | --- | --- | --- |
| H-01 | Đăng ký và xác nhận | STORY-01, STORY-03 | Một PBI chưa đạt test timeout | Trung bình |
| H-02 | Quyền mở bài và tiến độ | STORY-05, STORY-07 | Đang làm rõ API | Cao |
| H-03 | Báo cáo quản trị | STORY-09, STORY-10 | Chưa bắt đầu | Cần dự báo |
| H-04 | Bằng chứng bảo mật/bàn giao | TEST-01, DOC-02 | Một phần đã có | Cần phối hợp |

Các mã chỉ là dữ liệu minh họa, không phải mẫu Scrum bắt buộc. Mục tiêu là **minh bạch trạng thái nghĩa vụ mà không biến Product Backlog thành bản sao từng dòng hợp đồng**.

### 8.3. Khi thay đổi có hiệu lực

Nếu một change request được phê duyệt theo quyền, cập nhật:

1. Văn bản/baseline có hiệu lực và ngày áp dụng.
2. Product Backlog, ví dụ chấp nhận và kiểm thử.
3. Forecast mốc, chi phí, phụ thuộc và nguồn lực.
4. Bằng chứng nghiệm thu và trách nhiệm liên quan.

Không nên có một bảng “đã đồng ý” nhưng nhóm kỹ thuật vẫn chạy theo tiêu chí cũ.

## 9. Lập kế hoạch từ kết quả cần đạt về các lát cắt dọc

**Vertical slice** là phần nhỏ đủ đi qua những lớp cần thiết để tạo hành vi có giá trị, thay vì giao một tầng kỹ thuật chưa dùng được.

### 9.1. Ví dụ sai: chia kế hoạch theo phòng ban

~~~text
Tuần 1-3: hoàn tất toàn bộ UI.
Tuần 4-6: hoàn tất toàn bộ backend.
Tuần 7-8: viết toàn bộ bảng database.
Tuần 9-10: kiểm thử tích hợp.
Tuần 11-12: sửa lỗi và nghiệm thu.
~~~

Kế hoạch như vậy dễ tạo hàng chờ và phát hiện xung đột ở tuần 9. Phần “UI Done” chưa có nghĩa người học đăng ký được.

### 9.2. Ví dụ tốt hơn: phân kỳ theo khả năng sử dụng

| Lát cắt | Hành vi có ích | Bằng chứng cần có |
| --- | --- | --- |
| **A — Đăng ký miễn phí** | Người học lưu đăng ký và nhận xác nhận chính xác | API + DB + UI + test retry/concurrency |
| **B — Xem khóa đã đăng ký** | Người học thấy danh sách đúng theo tài khoản | Test dữ liệu và phân quyền |
| **C — Mở bài đầu** | Người học có quyền mở bài và phản hồi lỗi phù hợp | Integration/authorization tests |
| **D — Tiếp tục học** | Tiến độ được lưu và khôi phục | Test đồng bộ, không ghi đè sai |
| **E — Báo cáo bắt buộc** | Quản trị xem báo cáo đáp ứng tiêu chí đã ký | Đối soát dữ liệu và test nghiệm thu |

### 9.3. Lát cắt nhỏ không được bỏ chất lượng

Không nên gọi PBI A Done nếu chỉ có UI mock chạy nhưng backend chưa bảo vệ đăng ký trùng. Với Scrum, **Definition of Done là commitment của Increment**; phần chưa đạt DoD chưa là Increment Done.

### 9.4. Lát cắt theo giá trị không thay quyền thay scope

Nếu H-03 báo cáo quản trị là nghĩa vụ cứng, tách PBI A–D và nhận phản hồi sớm **không làm H-03 biến thành tùy chọn**. Nếu cần thay hạng mục, phải xử lý quyền và hồ sơ liên quan.

## 10. Phân biệt kế hoạch công việc, kế hoạch rủi ro và kế hoạch quyết định

Một kế hoạch dự án tốt không chỉ hỏi “ai viết chức năng nào vào ngày nào?” mà còn hỏi:

- **Rủi ro nào phải giảm sớm?**
- **Điều gì chỉ biết sau khi thử?**
- **Quyết định của ai có thể chặn tất cả việc còn lại?**
- **Bằng chứng nào là điều kiện để tiếp tục?**

| Loại kế hoạch | Ví dụ | Tác động tới luồng |
| --- | --- | --- |
| **Work plan** | Xây chức năng đăng ký, mở bài, báo cáo | Hiển thị khả năng cần giao |
| **Risk-reduction plan** | Thử race condition, quyền dữ liệu, API không chắc | Giảm nguy cơ phát hiện thất bại muộn |
| **Decision plan** | Xác nhận mẫu báo cáo, thẩm quyền đổi phạm vi | Ngăn chờ quyết định ở cuối kỳ |
| **Dependency plan** | Xin sandbox, review hợp đồng tích hợp, mua thiết bị | Quản lý công việc nằm ngoài nhóm |
| **Evidence/acceptance plan** | Test, tài liệu, đánh giá security, hồ sơ nghiệm thu | Chuẩn bị chứng cứ thay vì dồn cuối |

### 10.1. Đưa rủi ro lớn lên đầu kế hoạch

Giả sử API xác thực từ bên ngoài có nguy cơ trả quyền không đúng. Nếu để tuần 10 mới thử tích hợp, lúc đó **phương án sửa ít hơn**. Nên xây một lát cắt tích hợp nhỏ, thử quyền và làm rõ hợp đồng từ sớm.

### 10.2. Discovery không phải giấy phép trì hoãn giao hàng

Spike hay prototype có thể làm giảm bất định, nhưng cần có:

- Câu hỏi rõ.
- Phạm vi/thời gian thử phù hợp.
- Kết quả học cụ thể.
- Tiêu chí quyết định tiếp theo.
- Quyền sử dụng dữ liệu, môi trường và ngân sách.

Không để mọi Sprint chỉ làm nghiên cứu mà không cải thiện khả năng giao Increment khi đó là mục tiêu cần đạt.

## 11. Mốc và cổng kiểm soát: thêm bằng chứng, không thêm lớp báo cáo

Một kế hoạch dự báo có thể có **milestone** (mốc) và **governance gate** (điểm quyết định dựa trên điều kiện). Chúng không nhất thiết đồng nghĩa:

- **Mốc:** Một ngày hoặc trạng thái cần đạt, ví dụ có môi trường tích hợp trước tuần 4.
- **Gate:** Một quyết định được đưa ra sau khi xem bằng chứng, ví dụ chỉ triển khai dữ liệu thật khi quyền và kiểm thử an toàn đáp ứng yêu cầu.

### 11.1. Gate tốt đặt trên rủi ro thực

| Gate tham khảo | Câu hỏi cần quyết định | Bằng chứng có ích |
| --- | --- | --- |
| **Trước tích hợp đối tác** | Hợp đồng API/phiên bản đã đủ rõ? | Contract tests, môi trường và người chịu trách nhiệm |
| **Trước migration dữ liệu** | Có phương án thử, backup/khôi phục và quyền đúng? | Kịch bản migration, kết quả thử, phê duyệt |
| **Trước rollout người học** | Luồng đăng ký/mở bài đạt DoD và điều kiện release? | Integration/security tests, giám sát, kế hoạch khôi phục |
| **Trước nghiệm thu hợp đồng** | Bằng chứng đáp ứng điều khoản và thủ tục? | Test reports, traceability, người có thẩm quyền |

Những gate này là **ví dụ**, không tự trở thành yêu cầu pháp luật hoặc Scrum event bắt buộc. Gate không có giá trị nếu chỉ kiểm tra “đã gửi slide” mà không xem bằng chứng đúng.

### 11.2. Gate và Sprint Review khác nhau

**Sprint Review** giúp Scrum Team và stakeholders kiểm tra kết quả Sprint, cộng tác xem bước tiếp theo. **Gate** có thể dùng một phần bằng chứng từ Review nhưng có **quyền phê duyệt và nghĩa vụ riêng**. Không nên mặc định một buổi demo hoàn tất thủ tục nghiệm thu pháp lý.

### 11.3. Tránh stage-gate tuần tự làm nghẹt phản hồi

Nếu mỗi lát cắt nhỏ cần chờ hội đồng họp tháng một lần dù chỉ thay copy trong phạm vi đã cho phép, tổ chức đang tạo hàng chờ không cần thiết. Hãy phân quyền **điều chỉnh thường ngày** và giữ gate cho **rủi ro/ nghĩa vụ thực sự**.

## 12. Lập kế hoạch phụ thuộc: đường găng và luồng công việc

Những phụ thuộc cứng có thể chi phối ngày hoàn tất nhiều hơn tốc độ viết mã.

### 12.1. Khi nào cần nhìn đường găng?

**Critical path** trong lập lịch phụ thuộc chỉ ra chuỗi công việc có khả năng xác định thời lượng toàn kế hoạch theo **mạng công việc và thời lượng giả định**. Nó đặc biệt hữu ích khi:

- Cần mua thiết bị hoặc chờ chứng nhận ngoài nhóm.
- Phải hoàn tất bước hạ tầng trước khi kiểm thử tích hợp.
- Quyền dữ liệu/approval có thứ tự bắt buộc.
- Nhiều công việc có ràng buộc trước–sau khó tránh.

**Đường găng không phải quy luật bất biến**: thời lượng, logic phụ thuộc và nguồn lực thay đổi có thể làm đường găng thay đổi. Cần theo dõi dự báo, không chỉ một sơ đồ lúc lập kế hoạch ban đầu.

### 12.2. Ví dụ phụ thuộc minh họa

~~~mermaid
flowchart LR
    A["Thống nhất hợp đồng tích hợp<br/>3 ngày"] --> B["Cấp sandbox đối tác<br/>8 ngày"]
    B --> C["Tích hợp API<br/>4 ngày"]
    C --> D["Kiểm thử quyền và retry<br/>3 ngày"]
    D --> E["Đánh giá phát hành<br/>2 ngày"]
    F["Làm rõ trải nghiệm người học<br/>4 ngày"] --> G["UI + acceptance tests<br/>5 ngày"]
    G --> D
~~~

Trong mô hình đơn giản với các công việc có thể chạy song song theo mũi tên, nhánh **A–B–C–D–E** có tổng thời lượng:

\[
3+8+4+3+2=20\ \text{ngày}
\]

Nhánh **F–G** mất \(4+5=9\) ngày trước khi vào D. Nếu cả hai bắt đầu cùng lúc, D chỉ có thể bắt đầu khi **hai nhánh đã sẵn sàng**, theo mô hình này là sau 15 ngày của nhánh A–B–C. Đường A–B–C–D–E đang dài hơn.

**Đây là ví dụ số học không xét lịch nghỉ, tranh chấp nguồn lực, biến động thời lượng hoặc những công việc khác.** Đừng coi kết quả 20 ngày là cam kết thực tế.

### 12.3. Kết hợp tư duy critical path với Kanban

Trong kế hoạch, nhánh sandbox 8 ngày đáng chú ý. Trong thực thi, Kanban có thể cho biết **item tích hợp hiện đã chờ bao lâu**, ai có thể xử lý và WIP có bị tắc.

- **Lịch phụ thuộc:** Cho biết rủi ro mốc nếu một chuỗi chậm.
- **Dữ liệu dòng công việc:** Cho biết những item đang thực sự già đi và nơi đang nghẽn.

Hai góc nhìn bổ sung nhau. Nếu cứ cập nhật biểu đồ Gantt nhưng không nhìn trạng thái blocked thực, kế hoạch có thể đẹp mà không đúng thực tế.

## 13. Ước lượng, dự báo và phân tích bất định: đừng dùng một con số để hứa mọi thứ

Lập kế hoạch không cần dự đoán chính xác từng giờ làm, nhưng cần đủ thông tin để quyết định **phạm vi khả thi, mốc có rủi ro và phương án giảm rủi ro**.

### 13.1. Phân biệt estimate, forecast và commitment

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Ước lượng (estimate)** | Một việc có thể cần bao nhiêu năng lực hoặc công sức? | Test tích hợp yêu cầu 3–5 ngày thực hiện nếu sandbox sẵn |
| **Dự báo (forecast)** | Dựa trên trạng thái, năng lực và biến động, điều gì có thể hoàn tất khi nào? | Với dữ liệu hiện có, nguy cơ mốc tuần 6 tăng |
| **Mục tiêu (target)** | Chúng ta muốn điều gì xảy ra? | Có Increment đăng ký trước đợt học thử |
| **Cam kết/nghĩa vụ (commitment/obligation)** | Điều gì phải được tuân theo? | Hợp đồng yêu cầu bàn giao hạng mục đúng điều kiện |

Một estimate hợp lý vẫn có thể sai vì rủi ro chưa biết. Một forecast có thể thay đổi khi học thêm. Một nghĩa vụ hợp đồng **không tự thay đổi** theo forecast mới.

### 13.2. Vì sao story points không phải ngày công hay tiền?

Story points nếu được một nhóm lựa chọn thường phản ánh **ước lượng tương đối** trong ngữ cảnh của nhóm, không phải phép đổi tự động thành giờ hoặc tiền.

Không nên lấy “1 point = 8 giờ” rồi suy giá trị hợp đồng hoặc **so sánh velocity giữa nhiều nhóm**. Nếu cần ước lượng chi phí, phải dùng **năng lực, đơn giá, lịch, phụ thuộc và điều kiện tổ chức** phù hợp.

### 13.3. Dự báo có thể bắt đầu từ throughput

Giả sử một nhóm có throughput của **sáu tuần đã qua**, mỗi tuần đếm số PBI tương đối đồng nhất thật sự đạt DoD:

~~~text
Tuần 1: 3 PBI Done
Tuần 2: 5 PBI Done
Tuần 3: 4 PBI Done
Tuần 4: 2 PBI Done
Tuần 5: 6 PBI Done
Tuần 6: 4 PBI Done
~~~

Throughput trung bình:

\[
\frac{3+5+4+2+6+4}{6}=\frac{24}{6}=4\ \text{PBI/tuần}
\]

Nếu còn 16 PBI tương tự, phép chia \(16/4=4\) tuần là **điểm tham khảo thô**, không phải ngày chắc chắn hoàn tất. Sáu tuần có mức biến động 2–6 PBI; còn có vấn đề thay đổi phạm vi, phụ thuộc, năng lực, loại item và khoảng nghiệm thu.

### 13.4. Monte Carlo có thể giúp nhìn khoảng bất định

Khi có dữ liệu đủ đại diện, một cách dự báo là:

1. Chọn throughput lịch sử từ các kỳ có thể so sánh.
2. Xác định số PBI còn lại theo phạm vi dự báo.
3. Lấy mẫu nhiều kịch bản throughput tương lai từ phân bố quan sát, với giả định được nêu rõ.
4. Mỗi kịch bản cộng dồn số item hoàn tất đến khi đủ phạm vi.
5. Tổng hợp phân bố số kỳ cần thiết để đưa ra khoảng và mức tin cậy **theo mô hình**, không tạo vẻ chắc chắn giả.

**Không tự tuyên bố “85% chắc kịp tuần X” chỉ từ trung bình 4 PBI/tuần.** Mẫu ít và công việc tương lai khác công việc quá khứ có thể làm kết quả mô phỏng thiếu ổn định. Phải công bố giả định và giới hạn.

### 13.5. Dự báo theo mốc cố định

Nếu ngày khai giảng không đổi, câu hỏi phù hợp có thể là:

> “Với năng lực thực tế, DoD và yêu cầu bắt buộc, những khả năng nào có thể chứng minh đạt trước ngày khai giảng? Phần nào có nguy cơ, và ai có quyền quyết định cách ứng phó?”

**Nếu một đầu ra cứng có nguy cơ không đạt, cần đưa rủi ro lên thẩm quyền; không tự cắt hạng mục khỏi hợp đồng.**

## 14. Cycle Time, Work Item Age và SLE giúp phát hiện rủi ro trước khi quá hạn

Trong Kanban, bốn chỉ số dòng công việc thường dùng là:

- **Work in Progress (WIP):** Số item đã bắt đầu nhưng chưa Done tại một thời điểm.
- **Throughput:** Số item đạt Done trong một khoảng thời gian.
- **Work Item Age:** Thời gian đã trôi qua từ lúc bắt đầu của item còn dở.
- **Cycle Time:** Thời gian từ bắt đầu đến Done của item hoàn tất.

Điều kiện quan trọng là **định nghĩa workflow, mốc bắt đầu, mốc Done, đơn vị thời gian và loại item** rõ. Một PBI mới code xong nhưng chưa đạt DoD không thể được đếm là Increment Done chỉ để tăng throughput.

### 14.1. Tập Cycle Time minh họa

Giả sử 20 PBI đã Done thuộc nhóm công việc tương tự có Cycle Time theo **ngày làm việc**, xếp tăng:

~~~text
2, 3, 3, 4, 4, 5, 5, 5, 6, 6,
6, 7, 7, 8, 8, 9, 10, 11, 13, 18
~~~

| Thống kê | Giá trị | Cách hiểu |
| --- | ---: | --- |
| Số item | 20 | Cỡ mẫu minh họa |
| Trung vị | 6 ngày | Vị trí 10 và 11 đều là 6 |
| P85 nearest-rank | 10 ngày | \(\lceil0{,}85\times20\rceil=17\), giá trị 10 |
| P95 nearest-rank | 13 ngày | \(\lceil0{,}95\times20\rceil=19\), giá trị 13 |
| Giá trị lớn nhất | 18 ngày | Có đuôi dài cần hiểu bối cảnh |

Trong mẫu có 17/20 item hoàn tất **không quá 10 ngày**, tức 85% quan sát. Nhóm có thể cân nhắc **Service Level Expectation (SLE)** ở dạng:

> “Với loại PBI và ranh giới workflow đã xác định, kỳ vọng khoảng 85% item được hoàn tất trong không quá 10 ngày làm việc.”

SLE là **kỳ vọng theo phân bố**, không phải SLA hợp đồng hoặc lời hứa tất cả item phải Done trong 10 ngày. Mẫu nhỏ chỉ đủ học phương pháp và đưa ra giả thuyết; cần kiểm tra độ đại diện, thay đổi điều kiện và cách tính phân vị.

### 14.2. Nhìn công việc chưa Done

| Item | Work Item Age | Trạng thái | Câu hỏi cần đặt |
| --- | ---: | --- | --- |
| A — Đăng ký khóa | 9 ngày | Chờ review | Có thể gỡ hàng chờ không? |
| B — Đồng bộ tài khoản | 12 ngày | Blocked sandbox | Có cần escalate phụ thuộc? |
| C — Nhãn thông báo | 3 ngày | Kiểm thử | Có rủi ro đặc biệt không? |

Item B đã **vượt mốc SLE tham khảo** và cần xem lý do. Không được suy “quá SLE 2 ngày nên chỉ còn -2 ngày” hoặc “đã làm xong 120%”.

**Cycle Time chỉ gồm item đã Done có thể che giấu các item chưa Done đang tồn lâu**. Khi theo dõi mốc, cần đọc đồng thời Work Item Age và tình trạng blocked.

### 14.3. Little's Law là quan hệ trung bình, không phải lịch giao hàng

Trong hệ thống đủ ổn định và đo nhất quán:

\[
\overline{\text{WIP}}
\approx
\overline{\text{Throughput}}
\times
\overline{\text{Cycle Time}}
\]

Ví dụ độc lập: WIP trung bình 8 item, throughput 4 item/tuần thì Cycle Time trung bình liên hệ khoảng **2 tuần**, theo điều kiện áp dụng.

Điều này giúp thảo luận **giảm việc mở mới để hoàn tất phần đang dở**, nhưng không chứng minh giảm WIP một nửa sẽ tự động tăng tốc gấp đôi, cũng không cho P85 hay xác suất đúng hạn của một item.

## 15. Năng lực, lịch làm việc và buffer: rủi ro không biến mất chỉ vì kế hoạch đầy kín

Một kế hoạch dự báo có thể xác định nguồn lực theo người/ngày hoặc ngân sách; một kế hoạch thích ứng thường nhìn **khả năng hoàn tất thực tế**. Cả hai cần tránh giả định rằng tất cả thời gian trên lịch đều dành cho phát triển tính năng.

### 15.1. Ví dụ capacity theo hai tuần

Nhóm 5 Developers có Sprint hai tuần, mỗi người dự kiến 10 ngày làm việc, tức **50 person-days danh nghĩa**. Giả định trước Sprint:

| Nhu cầu công suất | Person-days minh họa |
| --- | ---: |
| Tổng danh nghĩa | 50 |
| Nghỉ và lịch không thể thay đổi | -5 |
| Hỗ trợ vận hành và incident dự kiến | -6 |
| Review/CI/tích hợp, hỗ trợ chéo | -7 |
| Bảo trì và công việc chất lượng bắt buộc | -7 |
| **Công suất còn lại để lên kế hoạch PBI mới** | **25** |

\[
50-5-6-7-7=25\ \text{person-days}
\]

Đây là **mô hình minh họa**, không phải cách tính bắt buộc của Scrum. Nếu kiểm thử tích hợp đã nằm trong ước lượng của PBI, **không nên trừ thêm cùng phần đó lần thứ hai**. Cần thống nhất phạm vi các hạng mục capacity.

### 15.2. Buffer khác “giấu năng lực”

Kế hoạch cần có cách ứng phó rủi ro, nhưng không nên tự ý tạo dự phòng kinh phí ngoài quyền. Có thể dùng:

- **Dự phòng năng lực hợp lệ** cho biến động và sự cố.
- **Mốc cảnh báo sớm** để xem lại forecast.
- **Phương án kỹ thuật thay thế** đã đánh giá rủi ro.
- **Công việc giảm rủi ro** trước những điểm không thể đảo ngược.
- **Thứ tự ưu tiên** giúp phần giá trị thiết yếu được Done sớm.

Nếu ngân sách bị khóa và điều khoản không có dự phòng, nhóm phải **minh bạch bất định và đưa lựa chọn lên người có quyền**, không coi buffer ẩn là nguồn lực mặc định.

### 15.3. Không tối ưu lịch bận 100%

Nếu tất cả chuyên gia bảo mật, dữ liệu hoặc reviewer đều được lên lịch kín 100%, một câu hỏi phụ thuộc nhỏ có thể xếp hàng nhiều ngày. **Tối ưu mức bận của cá nhân có thể làm luồng tổng thể chậm hơn**.

Nên quan sát thời gian chờ, WIP và độ ổn định của throughput, không chỉ số giờ mỗi người ghi vào timesheet.

### 15.4. Công việc phát sinh không phải lỗi lập kế hoạch bằng mọi giá

Lỗi production, thay đổi quyền API hoặc thông tin mới từ người học có thể xuất hiện. Kế hoạch tốt cần:

1. Ghi loại việc phát sinh và mức ảnh hưởng.
2. Quy định ai có thể xử lý ngay và ai cần duyệt.
3. Cập nhật khả năng hoàn tất PBI và rủi ro Sprint Goal/mốc.
4. Xem xu hướng để điều chỉnh capacity kỳ sau.

Không nên dùng forecast mới để xóa dấu vết chênh lệch so với baseline.

## 16. Scrum trong kế hoạch kết hợp: commitments không phải bản sao hợp đồng

Scrum cung cấp **accountabilities, events, artifacts và commitments** cho việc giao giá trị qua các Sprint. Nó **không bắt buộc Gantt, story points, velocity hoặc một bộ chứng từ nghiệm thu cụ thể**.

Ba commitments:

| Scrum artifact | Commitment | Vai trò trong hybrid |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Giữ hướng kết quả sản phẩm khi thông tin thay đổi |
| **Sprint Backlog** | **Sprint Goal** | Tập trung vào giá trị phải tạo trong Sprint |
| **Increment** | **Definition of Done** | Bảo đảm phần được gọi Done đạt chuẩn chất lượng |

### 16.1. Kế hoạch Sprint khác baseline hợp đồng

**Sprint Goal** được toàn Scrum Team tạo trong Sprint Planning; **Developers** lựa chọn PBI với sự trao đổi cùng Product Owner và lập kế hoạch cách thực hiện. Trong Sprint, Developers **điều chỉnh Sprint Backlog** khi học thêm.

Nhưng nếu một quyết định đổi phạm vi đã ký, cần **đi qua quyền và change control áp dụng**. Product Owner không mặc nhiên có quyền sửa hợp đồng, và hợp đồng không tự cho phép người mua can thiệp chi tiết cách Developers thực hiện.

### 16.2. Những điều không được thay đổi tùy tiện trong Sprint

Scrum nêu:

- Không thực hiện thay đổi có thể làm nguy hiểm Sprint Goal.
- Chất lượng không được giảm.
- Product Backlog có thể được làm rõ khi cần.
- Phạm vi có thể được làm rõ và thương lượng lại với Product Owner khi học thêm.

Nếu một PBI chưa đáp ứng DoD khi Sprint kết thúc, nó **không phải Increment Done**. Không nên chạy “Sprint tích hợp và kiểm thử” ở cuối dự án như cách cố định để né việc đạt DoD thường xuyên.

### 16.3. Sprint Review và nghiệm thu hợp đồng

**Sprint Review** là dịp kiểm tra kết quả và thảo luận thích ứng Product Backlog với stakeholders, không tự thay chữ ký nghiệm thu pháp lý. Có thể sử dụng bằng chứng Increment từ Review để hỗ trợ nghiệm thu theo thủ tục, nhưng **hai quyết định có ý nghĩa khác nhau**.

### 16.4. Khi mốc hợp đồng không trùng Sprint

Ví dụ hợp đồng có mốc tuần 7 nhưng Sprint kéo dài hai tuần. Không cần mặc định dời mốc hợp đồng sang cuối Sprint nếu không được phép. Nhóm có thể:

- Lập kế hoạch các lát cắt đủ điều kiện trước tuần 7.
- Hoàn tất và tích hợp Increment trước mốc nếu có thể.
- Xem rủi ro ngày theo tiến độ thật.
- Chuẩn bị thủ tục nghiệm thu theo quyền, ngoài nhịp Review nếu cần.

**Scrum không bảo đảm mọi mốc cố định đều khả thi.** Nhịp Sprint hỗ trợ kiểm tra và thích ứng, không thay thế quản trị cam kết.

## 17. Kanban khi có nhiều luồng và ràng buộc

Kanban hữu ích khi ngoài phát triển sản phẩm còn có **incident, hỗ trợ khách hàng, change request và phụ thuộc được xử lý theo luồng**.

### 17.1. Một workflow phát triển

~~~text
Ready -> Development -> Review -> Integration Test -> Done
             WIP           WIP            WIP

Blocked: ghi rõ nguyên nhân; item đã bắt đầu vẫn là WIP
trừ khi chính sách workflow định nghĩa khác và báo cáo minh bạch.
~~~

### 17.2. Một workflow quyết định độc lập

~~~text
Đề xuất thay đổi
 -> Kiểm tra phạm vi/quyền
 -> Phân tích tác động
 -> Chờ quyết định chính thức
 -> Được duyệt / Không được duyệt
 -> Nếu được duyệt: cập nhật baseline và backlog
~~~

Đừng gộp hai luồng thành một cột “Done” rồi suy rằng **CR đã duyệt = phần mềm đã giao xong**.

### 17.3. WIP limits và chính sách kéo

Nếu nhiều PBI nằm ở cột Review chờ một người, giới hạn WIP có thể giúp nhóm ngừng khởi động thêm và cùng hoàn tất việc đang dở. Khi có sự cố ưu tiên cao, cần **chính sách class of service/expedite rõ** để không làm mất minh bạch những item khác bị hoãn.

Không phải cứ đặt giới hạn WIP 2 là phù hợp. Cần thử dựa trên năng lực và dòng việc thực, rồi quan sát Work Item Age, Cycle Time, throughput và chất lượng.

### 17.4. SLE khác deadline hợp đồng

**Service Level Expectation (SLE)** mô tả kỳ vọng thời gian hoàn tất loại item theo mức xác suất/định nghĩa; **deadline hợp đồng** là một ràng buộc có thể có hậu quả pháp lý. Không dùng mốc P85 để tự thay ngày đã ký.

## 18. XP và kỹ thuật để thực thi phần thích ứng an toàn

Một dự án có lịch cứng càng cần **phản hồi kỹ thuật sớm**, vì sửa lỗi tích hợp vào cuối mốc thường đắt hơn.

| Thực hành XP/kỹ thuật | Giúp giảm bất định gì? | Điều phải giữ |
| --- | --- | --- |
| **Test-Driven Development** | Sai quy tắc nghiệp vụ được phát hiện sớm | Test mô tả đúng hành vi, không chỉ chạy xanh |
| **Continuous Integration** | Merge muộn và xung đột hợp đồng | CI phản hồi nhanh, test bắt buộc không bị bỏ |
| **Refactoring** | Kiến trúc làm thay đổi mới rủi ro | Hành vi đã xác định được bảo vệ |
| **Pair programming/review** | Kiến thức rủi ro tập trung một người | Quyền review/chuyên gia bắt buộc khi áp dụng |
| **Small releases** | Phản hồi người dùng đến muộn | DoD và điều kiện release/approval |
| **Collective code ownership theo chính sách** | Chờ một người duy nhất sửa phần mã | Bảo mật, quy trình merge và ownership rõ |
| **Contract/integration testing** | Sai khác UI–API–DB hoặc tích hợp đối tác | Cần dữ liệu và môi trường đại diện |

### 18.1. Ví dụ “đăng ký trùng” và rủi ro cuối mốc

Nếu chỉ thử một request thành công, luồng đăng ký có thể hỏng khi mạng timeout và client retry. Một kiểm tra tốt phải xem:

- Hai yêu cầu gần đồng thời có tạo hai đăng ký Active?
- Retry có tuân chính sách idempotency?
- Khi kết quả lưu chưa chắc chắn, UI có báo thành công giả?
- Người dùng khác có thể xem dữ liệu đăng ký không?
- Kết quả test có phản ánh DB/hệ thống thực cần dùng?

### 18.2. Gherkin cho một lát cắt phù hợp

~~~gherkin
Tính năng: Đăng ký khóa học và xác nhận trạng thái

  Tình huống: Đăng ký thành công
    Cho trước người học đã đăng nhập hợp lệ
    Và khóa "Java nhập môn" đang cho phép đăng ký miễn phí
    Khi người học gửi yêu cầu đăng ký
    Thì hệ thống lưu đăng ký hợp lệ
    Và người học thấy xác nhận đúng trạng thái

  Tình huống: Hai yêu cầu gần đồng thời
    Cho trước người học chưa có đăng ký Active cho khóa này
    Khi hai yêu cầu đăng ký cùng khóa tới gần đồng thời
    Thì hệ thống không tạo hai đăng ký Active trùng nhau
    Và mỗi phản hồi tuân hợp đồng API đã thống nhất

  Tình huống: Timeout nhưng chưa xác nhận được kết quả lưu
    Cho trước client chưa nhận được kết quả chắc chắn từ dịch vụ
    Khi người học thử đăng ký khóa
    Thì giao diện không báo chắc chắn rằng đã lưu thành công
    Và người học có cách kiểm tra trạng thái hoặc thử lại an toàn

  Tình huống: Tài khoản khác không được xem dữ liệu
    Cho trước tài khoản A đang đăng nhập
    Và đăng ký thuộc về tài khoản B
    Khi A cố truy cập dữ liệu đăng ký của B
    Thì hệ thống từ chối theo chính sách phân quyền
    Và không tiết lộ thông tin riêng của B
~~~

Đây là **ví dụ acceptance criteria**, không phải chương trình test chạy được ngay. Cần bước kiểm thử, môi trường và dữ liệu phù hợp; kiểm tra đồng thời thực sự phải chạy qua ranh giới xử lý/DB có nguy cơ.

### 18.3. Kỹ thuật tốt là khoản đầu tư vào khả năng dự báo

CI ổn định, PR nhỏ và test tích hợp đáng tin giúp các thay đổi ít xếp hàng, lỗi được phát hiện sớm và **dữ liệu Cycle Time phản ánh công việc thật tốt hơn**. Vì vậy thực hành XP không chỉ giúp chất lượng; nó còn giúp **dự báo kế hoạch có căn cứ hơn**.

## 19. Điều chỉnh phạm vi: linh hoạt ở đâu và cần duyệt ở đâu?

Trong hybrid, cần phân loại trước khi thay kế hoạch:

| Phát hiện/thay đổi | Phạm vi ảnh hưởng | Cách xử lý có thể phù hợp |
| --- | --- | --- |
| Sửa thông báo đăng ký gây hiểu lầm | Có thể nằm trong hành vi đã cam kết | Làm rõ, ưu tiên và kiểm thử trong quyền |
| Chia PBI thành hai lát cắt nhỏ | Thay cách thực hiện | Developers/PO trao đổi, không đổi đầu ra bắt buộc |
| Tái cấu trúc API không đổi hành vi | Giải pháp kỹ thuật | Theo quy tắc kiến trúc/DoD và quyền |
| Đổi thứ tự PBI trong kỳ | Kế hoạch thực thi | PO và Developers xem ảnh hưởng Sprint Goal/mốc |
| Bỏ một báo cáo đã ghi trong hợp đồng | Baseline phạm vi | Phân tích tác động, change control nếu cần |
| Thêm hệ thống chứng chỉ mới | Có thể là đầu ra mới | Xác minh phạm vi, quyền và phê duyệt trước |
| Dời mốc thanh toán | Nghĩa vụ tài chính | Quy trình hợp đồng/ủy quyền |
| Bỏ kiểm tra phân quyền để kịp ngày | Chất lượng/an toàn bắt buộc | **Không tự làm**; bảo vệ dữ liệu và xử lý rủi ro đúng quyền |

### 19.1. Thay đổi “nằm trong backlog” không đồng nghĩa được duyệt hợp đồng

Product Backlog là công cụ sắp xếp và làm rõ việc cần để cải thiện sản phẩm. Một ý tưởng được ghi thành PBI **chưa chứng minh nhà cung cấp đã được phép triển khai, thanh toán hoặc bỏ deliverable khác**.

### 19.2. Có thể giữ cùng mức giá nhưng vẫn cần phê duyệt

Việc đổi báo cáo A lấy dashboard B có thể không tăng giá, nhưng làm đổi **đầu ra và tiêu chí nghiệm thu**. Khi baseline cố định, cần xác nhận cơ chế đổi hợp lệ.

### 19.3. Không dùng Agile để “đi vòng” quy trình mua sắm

Nếu quy định áp dụng yêu cầu phê duyệt chính thức, không nên làm trước rồi xin ký sau. Trường hợp khẩn cấp phải dùng **quy trình khẩn có ủy quyền**, không tự tạo ngoại lệ.

## 20. Kế hoạch kết hợp trong hợp đồng cố định thời gian, giá và phạm vi

Đây là tình huống khó vì **mọi biến lớn đều có thể bị ràng buộc**. Không nên hứa rằng chỉ cần Scrum thì mọi nghĩa vụ chắc chắn hoàn tất.

### 20.1. Trình tự có trách nhiệm

1. Xác định **đầu ra bắt buộc** và điều kiện nghiệm thu.
2. Đánh giá năng lực, phụ thuộc và rủi ro với bằng chứng hiện có.
3. Giao những lát cắt giá trị **đạt DoD** càng sớm càng hợp lý.
4. Giảm WIP, tích hợp và kiểm thử liên tục để tránh dồn chất lượng cuối kỳ.
5. Dự báo lại khi xuất hiện thông tin mới, ghi chênh lệch với baseline.
6. Nếu mốc hoặc đầu ra có nguy cơ không đạt, chuẩn bị **phương án có tác động và người có quyền quyết định**.
7. Chỉ thay nghĩa vụ khi có quyết định hợp lệ.

### 20.2. Ba nhóm lựa chọn khi kế hoạch không còn khả thi

**A. Cải thiện trong phạm vi:** Tăng chất lượng phối hợp, gỡ hàng chờ, chia lát cắt, giảm rủi ro tích hợp, cải thiện CI và test.

**B. Điều chỉnh trong quyền hiện có:** Đổi thứ tự, hoán đổi lịch công việc nội bộ, dùng năng lực đã được phép, thay cách chứng minh nếu không đổi nghĩa vụ/tiêu chí.

**C. Đề xuất thay đổi chính thức:** Dời mốc, đổi giá, thay đầu ra hoặc điều kiện nghiệm thu nếu quy trình và người có thẩm quyền cho phép. Đề xuất có thể được duyệt, bị từ chối hoặc yêu cầu bổ sung.

Không tồn tại lựa chọn hợp lệ **“đánh dấu Done khi chưa đạt DoD để đủ chỉ tiêu”**.

### 20.3. Ví dụ so sánh hai cách báo cáo rủi ro

**Chưa tốt:**

> “Đội đã hoàn thành 87% task nên chắc chắn sẽ giao đúng hạn.”

Task percentage không phản ánh chất lượng tích hợp, PBI chưa Done, blocker hoặc nghĩa vụ.

**Tốt hơn:**

> “Hai lát cắt đăng ký đã đạt DoD, nhưng mở bài đầu đang chờ sandbox và có ba kịch bản phân quyền chưa đạt. Với trạng thái hiện tại, mốc nghiệm thu có rủi ro; nhóm đề xuất gỡ quyền môi trường trước ngày X, ưu tiên kiểm thử tích hợp và trình các lựa chọn nếu phụ thuộc không được giải quyết. Baseline hợp đồng chưa thay đổi.”

### 20.4. Phải nói rõ điều không thể trade-off

Nếu hệ thống có dữ liệu người học, “kịp hạn” không thể được tạo bằng cách bỏ kiểm soát truy cập cần thiết. Phần có thể trao đổi là **phạm vi được phép, thứ tự ưu tiên, lịch, năng lực và phương án**, theo đúng người có quyền.

## 21. Khi có một thành phần predictive nằm trên đường găng

Dự án có thể gồm một nhánh phải lập kế hoạch chặt, ví dụ triển khai cổng xác thực do cơ quan/tổ chức khác cấp phép.

### 21.1. Cách tổ chức hai nhịp

- **Nhịp predictive:** Theo dõi ngày nộp hồ sơ, kiểm tra hợp đồng tích hợp, cấp sandbox, thời hạn chứng nhận và người có quyền ký.
- **Nhịp adaptive:** Thiết kế các lát cắt đăng ký và trải nghiệm người học, dùng mock/contract tests được phép để học và giảm bất định.

**Điểm giao:** Khi sandbox thật sẵn sàng, nhóm thay mock bằng kiểm chứng thực theo kế hoạch; nếu sandbox trễ, forecast phải cập nhật.

### 21.2. Không coi mock là bằng chứng tích hợp cuối

Mock giúp phát triển trước và kiểm tra hợp đồng dự kiến, nhưng **không chứng minh dịch vụ thật tương thích**. Nếu DoD hoặc nghiệm thu yêu cầu tích hợp thật, PBI không đạt chuẩn chỉ dựa vào mock.

### 21.3. Giữ minh bạch blocker

| Điều cần theo dõi | Cách dùng |
| --- | --- |
| Ngày phụ thuộc được yêu cầu | Truy vết thời điểm nhóm bắt đầu cần hỗ trợ |
| Người/nhóm có quyền xử lý | Tránh đẩy việc vòng quanh |
| Điều kiện “phụ thuộc đã xong” | Sandbox + tài liệu + quyền, không chỉ email “đã cấp” |
| Work Item Age/blocked time | Biết item nào đang già và tác động ra sao |
| Mốc dự kiến và forecast mới | Nhìn rủi ro đường găng |
| Phương án giảm rủi ro được phép | Contract tests, dữ liệu giả, thiết kế tương thích |

Không nên dùng một metric blocked time để đánh giá năng lực một cá nhân: nguyên nhân có thể nằm ở thủ tục và bên ngoài nhóm.

## 22. Release planning trong môi trường có gate và nhiều nhóm

Kế hoạch phát hành không đồng nhất với kế hoạch Sprint hay ngày nghiệm thu.

| Khái niệm | Khi nào được coi là đạt? |
| --- | --- |
| **Task hoàn tất** | Công việc kỹ thuật cụ thể được thực hiện theo cách nhóm tổ chức |
| **PBI/Increment Done** | Đáp ứng Definition of Done của sản phẩm |
| **Sẵn sàng phát hành** | Đáp ứng chính sách vận hành, an toàn, dữ liệu, rollout, rollback và phê duyệt áp dụng |
| **Đã phát hành** | Có thay đổi được triển khai theo chính sách |
| **Người dùng nhận giá trị** | Hành vi sử dụng/outcome được quan sát phù hợp |
| **Đã nghiệm thu hợp đồng** | Có quyết định/chứng từ theo điều khoản và người có quyền |

### 22.1. Một kế hoạch release theo lát cắt

| Đợt | Mục tiêu minh họa | Điều kiện chính |
| --- | --- | --- |
| **Nội bộ 1** | Đăng ký miễn phí trên môi trường thử | DoD, test dữ liệu giả, quyền |
| **Pilot 2** | Nhóm người học được phép mở bài đầu | Gate bảo mật/vận hành, giám sát, hỗ trợ |
| **Mở rộng 3** | Nhiều người học sử dụng ổn định | Kiểm tra lỗi, dữ liệu, khả năng tải |
| **Nghiệm thu mốc** | Đáp ứng đầu ra hợp đồng | Bộ bằng chứng và người ký theo quyền |

Đây là kế hoạch tham khảo, không khuyến nghị luôn phải có ba đợt hoặc đủ điều kiện pháp lý chỉ vì pilot thành công.

### 22.2. Feature flag là công cụ, không là giấy miễn kiểm thử

Một feature flag có thể giúp giới hạn người dùng được thấy chức năng và hỗ trợ rollback, nhưng:

- Mã vẫn phải đáp ứng chuẩn chất lượng áp dụng.
- Không dùng flag để che lỗi dữ liệu đang gây hại.
- Phải xác định trạng thái cấu hình, telemetry và đường khôi phục.
- Gate nghiệm thu và quyền dữ liệu vẫn có thể cần đáp ứng riêng.

### 22.3. Nhiều Scrum Teams cùng sản phẩm

Nếu nhiều Scrum Teams cùng một sản phẩm theo Scrum, chúng phải **chia sẻ Product Goal, Product Backlog, Product Owner và Definition of Done**. Mỗi Scrum Team có Sprint Goal và Sprint Backlog riêng; công việc cần tích hợp thành Increment sản phẩm.

Không nên để mỗi nhóm báo “Done phần API/UI” rồi đến gần ngày release mới phát hiện các phần không thể dùng cùng nhau.

## 23. Quản trị theo bằng chứng, không theo số phần trăm hoàn thành cảm tính

Một báo cáo hybrid thường cần phục vụ **hai câu hỏi khác nhau**:

1. **Trách nhiệm cam kết:** Nghĩa vụ, mốc, chi phí, tiêu chí và phê duyệt có nguy cơ gì?
2. **Khả năng giao giá trị:** Phần nào đã đạt DoD, người dùng có nhận giá trị, dòng việc đang nghẽn ở đâu?

### 23.1. Dashboard tối thiểu theo quyết định

| Khối | Câu hỏi | Dữ liệu cần thiết |
| --- | --- | --- |
| **Nghĩa vụ** | Hạng mục bắt buộc nào chưa có bằng chứng? | Baseline, traceability, acceptance status |
| **Mốc và rủi ro** | Điều kiện nào có thể làm trễ gate? | Dependency, đường găng giả định, forecast mới |
| **Dòng việc** | Công việc nào đang già, WIP ở đâu? | Work Item Age, Cycle Time, WIP, throughput |
| **Chất lượng** | Có Increment Done và test rủi ro đạt không? | DoD, lỗi tích hợp, phân quyền, CI |
| **Giá trị người dùng** | Người học có đăng ký và bắt đầu học? | Activation, task success, nghiên cứu |
| **Quyết định** | Ai cần phê duyệt hoặc gỡ blocker? | Decision log, tuổi CR, ngày cần trả lời |

### 23.2. Dự báo không được trình bày thành status xanh giả

Nếu một gate yêu cầu security review nhưng chưa có lịch và môi trường, status “90% task done” dễ che rủi ro mốc. Nên ghi:

> “Phát triển chức năng đã tiến triển, nhưng yêu cầu đánh giá bảo mật chưa có bằng chứng và là điều kiện trước rollout. Kế hoạch hiện có nguy cơ; cần người có quyền xác nhận lịch và phương án.”

### 23.3. Chỉ số phải có ranh giới đo và nguồn dữ liệu

“Cycle Time 6 ngày” phải biết từ khi nào đến khi nào, tính ngày lịch hay làm việc, loại PBI nào, DoD có đổi không. “Activation tăng 10%” phải biết số người/cohort, tử số/mẫu số và khác biệt nguồn người dùng.

Khi ranh giới hoặc định nghĩa đổi, cần ghi lịch sử và tránh so trực tiếp hai chuỗi không đồng nhất.

### 23.4. Đừng dùng số liệu để thưởng phạt cá nhân

WIP, Cycle Time hoặc throughput chịu ảnh hưởng của phụ thuộc, review, môi trường, phê duyệt và chất lượng. Dùng để **cải thiện hệ thống**, không xếp hạng Developers, PO hay nhóm chuyên môn bằng một số đơn lẻ.

## 24. Nhịp cập nhật kế hoạch và cơ chế ra quyết định

Một cách phối hợp nhẹ là dùng **các nhịp kiểm tra khác nhau theo mục đích**, không tạo một cuộc họp lớn xử lý mọi loại việc.

| Nhịp tham khảo | Vấn đề cần xem | Hành động có ích |
| --- | --- | --- |
| **Hằng ngày/theo luồng** | Blocker, CI đỏ, Work Item Age cao | Gỡ chặn, cùng hoàn tất, ứng cứu khi cần |
| **Trong Sprint** | Tiến độ tới Sprint Goal, DoD, thay đổi kỹ thuật | Developers thích ứng Sprint Backlog |
| **Mỗi Sprint Review** | Increment, phản hồi và Product Goal | PO/nhóm thảo luận điều chỉnh Product Backlog |
| **Mỗi Sprint Retrospective** | Cách làm, phối hợp, chất lượng | Chọn một vài cải tiến có thể kiểm chứng |
| **Hằng tuần hoặc theo mốc** | Phụ thuộc ngoài nhóm, baseline vs forecast, CR | Người có quyền quyết định hoặc escalation |
| **Trước governance gate** | Điều kiện an toàn/khả năng phát hành/ nghiệm thu | Trình bằng chứng và nhận quyết định hợp lệ |

Nhịp là **gợi ý**, không phải Scrum events mới hoặc thời hạn phê duyệt pháp lý. Một incident nghiêm trọng không được đợi tới cuộc họp hằng tuần.

### 24.1. Phân biệt hai loại quyết định

**Quyết định vận hành sản phẩm trong quyền:** PO điều chỉnh thứ tự, Developers quyết định How, nhóm thay chính sách WIP.

**Quyết định thay đổi nghĩa vụ/rủi ro bắt buộc:** Contract manager, procurement, legal, security, sponsor hoặc chủ thể có quyền theo tài liệu thực tế.

Người tham gia Sprint Review không mặc nhiên được ký thay chủ thể hợp đồng.

### 24.2. Một Decision Brief ngắn

~~~text
Câu hỏi cần quyết định:
  Có thể mở pilot đăng ký trước mốc khai giảng không?

Bằng chứng đã có:
  Increment đăng ký đạt DoD trong môi trường được phép.
  Test tích hợp quyền học ở sandbox đối tác còn chờ.

Điều chưa biết/rủi ro:
  Ngày sandbox sẵn; kết quả kiểm tra trên dịch vụ thật.

Baseline/mốc liên quan:
  H-01/H-02 và điều kiện an toàn trước rollout.

Các lựa chọn:
  A. Giữ mốc, ưu tiên tháo phụ thuộc và kiểm chứng.
  B. Pilot phạm vi nhỏ nếu gate cho phép, không dùng dữ liệu ngoài quyền.
  C. Đề xuất thay đổi mốc/nghĩa vụ theo quy trình nếu cần.

Người quyết định:
  Product Owner cho thứ tự backlog;
  chủ thể release/security/hợp đồng cho phần thuộc quyền.

Mốc kiểm tra lại và điều kiện:
  Khi sandbox và bằng chứng test được xác minh.
~~~

### 24.3. Escalation sớm không phải thừa nhận thất bại

Khi dự báo trễ xuất hiện, đem thông tin lên đúng người **trước khi hết lựa chọn** thể hiện trách nhiệm. Giấu forecast để đến hạn mới báo là làm mất cơ hội thích ứng hợp lệ.

## 25. Tình huống xuyên suốt: 12 tuần ra mắt nền tảng học trực tuyến

Hãy xem một dự án **giả định** đang phải phối hợp kế hoạch dự báo và thích ứng:

- Có **12 tuần** trước một đợt khai giảng.
- Tổng ngân sách và hạng mục hợp đồng được phê duyệt.
- Phải có luồng đăng ký, quyền mở bài, theo dõi tiến độ, báo cáo quản trị và bằng chứng bảo mật/bàn giao theo tiêu chí đã xác định.
- API xác thực của đối tác chưa có sandbox ổn định.
- Khảo sát ban đầu chưa rõ người học muốn email xác nhận hay hướng dẫn trực tiếp trong ứng dụng.
- Nhóm phát triển có 5 Developers và người có chuyên môn hỗ trợ theo cơ chế đã thống nhất.

**Các số liệu và mã ở toàn bộ tình huống là dữ liệu minh họa**, không phải dự án hoặc hợp đồng thực.

### 25.1. Tách cái cố định và cái cần học

| Điều kiện | Loại | Phương án kế hoạch |
| --- | --- | --- |
| Đợt khai giảng và mốc nghiệm thu | Ràng buộc có hậu quả | Lập mốc, kiểm tra phụ thuộc, chuẩn bị phương án |
| Bảo vệ tài khoản và dữ liệu | Chuẩn chất lượng bắt buộc | Threat modeling, test, đánh giá theo quyền |
| Danh mục báo cáo trong hợp đồng | Baseline nghĩa vụ | Truy vết PBI, change control nếu thay |
| Cách người học tìm bài đầu | Nhu cầu còn bất định | Prototype/usability test, phân tích activation |
| Cách API xử lý timeout | Bất định kỹ thuật | Spike/contract test, kiểm tra lỗi sớm |
| Trình tự triển khai UI/API/DB | Lựa chọn kỹ thuật | Vertical slice, CI và self-service test |
| Chi tiết giao diện báo cáo | Cần làm rõ mức tự do thiết kế | Refinement với người có thẩm quyền |

### 25.2. Product Goal và các nghĩa vụ không đồng nhất

Product Goal tham khảo:

> “Người học mới có thể đăng ký khóa và bắt đầu học thuận lợi, với trạng thái và quyền truy cập đáng tin.”

Đây là **hướng kết quả sản phẩm**. Hợp đồng có thể còn yêu cầu báo cáo quản trị hoặc tài liệu bàn giao. Những nghĩa vụ ấy **không tự mất hiệu lực** khi Product Goal đạt.

### 25.3. Dự kiến kế hoạch ba tầng

| Tầng | Nội dung minh họa |
| --- | --- |
| **Cam kết** | Mốc 12 tuần, H-01 đăng ký, H-02 quyền học, H-03 tiến độ, H-04 báo cáo, H-05 bảo mật/bàn giao |
| **Rolling wave** | Tháng đầu tích hợp/rủi ro và luồng đăng ký; tháng hai tiến độ/báo cáo; tháng ba kiểm chứng/migration/bàn giao |
| **Thực thi** | Sprint Goal, PBI có giá trị, CI/test, WIP, feedback và làm rõ hằng ngày |

### 25.4. Một roadmap có điều kiện

| Giai đoạn | Kết quả muốn có | Điều kiện phụ thuộc và kiểm chứng |
| --- | --- | --- |
| **Tuần 1–2** | Increment đăng ký cơ bản có thể dùng trên môi trường cho phép | DoD, test duplicate/retry, contract xác thực ban đầu |
| **Tuần 3–4** | Mở bài đầu theo quyền + phản hồi người học | Sandbox đối tác, authorization tests, trải nghiệm |
| **Tuần 5–6** | Tiến độ học và đồng bộ | Bất biến cập nhật, migration thử, integration tests |
| **Tuần 7–8** | Báo cáo quản trị theo tiêu chí | Đối soát dữ liệu, test báo cáo, phản hồi nghiệp vụ |
| **Tuần 9–10** | Kiểm tra tích hợp rộng và rủi ro phát hành | Performance, quyền, rollback, hỗ trợ vận hành |
| **Tuần 11–12** | Hồ sơ nghiệm thu/bàn giao theo quyền | Bằng chứng, tài liệu, quyết định được ủy quyền |

**Đây là roadmap dự kiến, không phải lịch hứa chắc chắn.** Nếu hợp đồng có một gate sớm hơn hoặc cần chạy đánh giá security nhiều tuần, phải điều chỉnh trình tự. Không nên dồn toàn bộ kiểm thử tới tuần 9–10: những kiểm thử tương ứng phải diễn ra trong từng lát cắt để đạt DoD.

### 25.5. Sprint đầu: kiểm tra rủi ro lớn trước

Một Sprint Goal có thể là:

> “Người học có thể đăng ký khóa miễn phí và thấy trạng thái nhất quán trong những trường hợp sử dụng quan trọng.”

PBI được lựa chọn qua Sprint Planning có thể gồm lưu đăng ký, xử lý retry, xác nhận UI và kiểm thử phân quyền. Developers lập kế hoạch UI/API/DB và test **xuyên suốt một lát cắt**, thay vì giao theo tầng rồi đợi cuối.

Các câu hỏi cần học:

- Contract đối tác cho quyền đăng nhập có đủ rõ?
- DB có bảo vệ không tạo đăng ký Active trùng?
- Người học có hiểu thành công, thất bại và trạng thái chưa chắc?

### 25.6. Thông tin mới xuất hiện sau hai Sprint

Giả sử:

1. Người học không cần email như nhóm từng dự đoán; họ quan tâm nút mở bài đầu hơn.
2. API đối tác trễ cấp sandbox hai tuần.
3. Báo cáo quản trị bắt buộc vẫn chưa được làm rõ đầu ra chi tiết.
4. Những PBI liên quan đăng ký đang có Work Item Age cao do chờ test tích hợp.

Phân loại phản ứng:

| Phát hiện | Thích ứng trong quyền | Phần cần quản trị ràng buộc |
| --- | --- | --- |
| Không cần email trong hành trình | Ưu tiên đường dẫn tới bài đầu, kiểm chứng UX | Kiểm tra email có là đầu ra bắt buộc không trước khi bỏ |
| Sandbox bị trễ | Test contract với mock, gỡ blocker, chuẩn bị dữ liệu | Cập nhật forecast mốc, escalation đối tác |
| Báo cáo chưa rõ | Làm refinement với ví dụ nghiệp vụ | Xác nhận cách hiểu tiêu chí nghiệm thu |
| Age tăng vì chờ test | Giảm WIP, cùng gỡ review và dữ liệu test | Nếu ảnh hưởng mốc nghĩa vụ, thông báo rủi ro sớm |

### 25.7. Báo cáo kế hoạch dự báo và thích ứng cùng lúc

> “Sau hai Sprint, nhóm đã có Increment đăng ký đạt một phần kiểm chứng trong môi trường được phép; tuy nhiên, kiểm thử quyền học qua sandbox đối tác chưa hoàn tất nên chức năng phụ thuộc chưa đạt DoD. Phản hồi người dùng cho thấy cần ưu tiên đường dẫn tới bài đầu trong phạm vi phù hợp. Sandbox trễ làm mốc tích hợp có nguy cơ; nhóm đề xuất gỡ phụ thuộc, duy trì contract tests với mock và xin xác nhận ảnh hưởng đến nghĩa vụ nếu cần. Baseline hợp đồng chưa thay đổi; forecast sẽ cập nhật khi có ngày sandbox được xác minh.”

Không gọi phần chưa đạt DoD là Done, không nhận lời đổi nghĩa vụ trước phê duyệt và không che rủi ro.

## 26. Quản lý kịch bản: điều gì xảy ra nếu giả định sai?

Một kế hoạch kết hợp tốt không chỉ có “kịch bản kỳ vọng”; nó có **điều kiện cảnh báo và lựa chọn ứng phó**.

### 26.1. Ba kịch bản cho sandbox xác thực

| Kịch bản | Điều kiện xảy ra | Ứng phó có thể phù hợp |
| --- | --- | --- |
| **A — Đúng lịch** | Sandbox dùng được trước mốc theo thỏa thuận | Tích hợp/test sớm, giữ kế hoạch nếu rủi ro khác cho phép |
| **B — Trễ ngắn** | Sandbox trễ vài ngày, hợp đồng API vẫn rõ | Mock/contract tests, ưu tiên PBI ít phụ thuộc, cập nhật forecast |
| **C — Trễ lớn/không ổn định** | Không có môi trường đủ tin cậy nhiều tuần | Escalation, đề xuất phương án hợp lệ, đánh giá tác động mốc/nghĩa vụ |

Không được kết luận “mock chạy là đủ nghiệm thu tích hợp thật” trong kịch bản C. Nếu môi trường thật là điều kiện bắt buộc, cần thẩm quyền quyết định.

### 26.2. Trigger thay vì cảnh báo chung chung

Ví dụ các **điều kiện kích hoạt hành động** do nhóm tự thống nhất:

- Chưa nhận API contract đủ kiểm thử trước ngày đã xác định → liên hệ đối tác và cập nhật risk log.
- Work Item Age của PBI phụ thuộc tiến gần mức SLE tham khảo → ưu tiên gỡ blocker và báo nguy cơ.
- Một kiểm tra phân quyền quan trọng thất bại → không coi PBI đạt DoD, ứng cứu theo mức rủi ro.
- Forecast đầu ra bắt buộc vượt mốc → chuẩn bị Decision Brief cho người có quyền.
- Người học thử nghiệm không hoàn tất đăng ký → kiểm tra UX và lỗi API trước khi đầu tư thêm gợi ý khóa.

**Ngày và ngưỡng cụ thể phải dựa trên bối cảnh**, không thể áp chung cho mọi sản phẩm.

### 26.3. Biện pháp dự phòng không phải công việc bất kỳ

Một contingency hợp lý phải **giảm rủi ro cần thiết** và nằm trong quyền. Ví dụ xây contract test trong lúc chờ sandbox có thể giảm thời gian tích hợp sau này. Viết thêm giao diện không liên quan chỉ để “giữ mọi người bận” có thể tăng WIP mà không cải thiện khả năng đạt mốc.

## 27. Mẫu quy trình xử lý thay đổi khi baseline và Product Backlog gặp nhau

Khi có đề nghị ngoài kế hoạch, có thể đi theo chuỗi:

~~~mermaid
flowchart TD
    A["Phản hồi/yêu cầu/rủi ro mới"] --> B["Mô tả hành vi, bằng chứng và tác động"]
    B --> C{"Có ảnh hưởng nghĩa vụ/giá/mốc/chất lượng?"}
    C -->|"Chưa rõ"| D["Xác minh baseline và thẩm quyền"]
    D --> C
    C -->|"Không"| E["PO/Developers làm rõ và ưu tiên trong quyền"]
    C -->|"Có"| F["Phân tích phương án, chi phí, mốc, rủi ro"]
    F --> G["Trình người có quyền theo change control"]
    G --> H{"Được phê duyệt?"}
    H -->|"Có"| I["Cập nhật baseline, forecast, backlog, tests"]
    H -->|"Không"| J["Giữ cam kết hiện hành, chọn cách hợp lệ"]
    E --> K["Lập kế hoạch Increment và kiểm tra DoD"]
    I --> K
    J --> K
    K --> L["Phản hồi, đo lường và kiểm tra tiếp"]
    L --> A
~~~

### 27.1. Một Change/Decision Brief ngắn

~~~text
Mã quyết định:
  ...

Tình huống và bằng chứng:
  ...

Hành vi người dùng hoặc nghĩa vụ bị tác động:
  ...

Baseline/mốc/điều kiện nghiệm thu liên quan:
  ...

Giải pháp A trong phạm vi hiện tại:
  Giá trị, chi phí, rủi ro, thời gian ...

Giải pháp B cần thay đổi hợp đồng (nếu có):
  Phạm vi, giá, mốc, chất lượng, quyền ...

Giả định/độ bất định:
  ...

Forecast và ảnh hưởng tới Sprint Goal/Product Goal:
  ...

Người có thẩm quyền quyết định:
  ...

Trạng thái: đang làm rõ / chờ duyệt / được duyệt / không duyệt

Quyết định, căn cứ, ngày hiệu lực:
  ...

Phần cần cập nhật: baseline / backlog / tests / roadmap ...

Người theo dõi và điểm xem lại:
  ...
~~~

Đây là mẫu làm việc; **không thay mẫu pháp lý hoặc quy trình mua sắm đã được quy định**.

### 27.2. Đừng đánh đồng ý kiến với quyết định có hiệu lực

Một đại diện nghiệp vụ nói “thêm email nhé” là phản hồi đáng quan tâm. Nó chưa nhất thiết là **đề nghị có phê duyệt ngân sách, thay scope hoặc điều kiện nghiệm thu**. Ghi lại và phân loại là hành động cộng tác; triển khai ngay có thể tạo nghĩa vụ không được cho phép.

## 28. Những hiểu lầm khi kết hợp dự báo và thích ứng

**1. “Predictive luôn chống lại Agile.”** Kế hoạch mốc và phụ thuộc hữu ích khi rủi ro cần dự báo; vấn đề là không thích ứng khi có bằng chứng mới.

**2. “Adaptive nghĩa là không lập kế hoạch.”** Có Product Goal, Sprint Planning, backlog và dự báo được cập nhật.

**3. “Hybrid nghĩa là dùng mọi nghi lễ của mọi framework.”** Cần chọn thực hành phục vụ mục tiêu, tránh chồng thủ tục.

**4. “Có Gantt thì không được dùng Scrum.”** Công cụ lịch có thể phục vụ ràng buộc; không quyết định Scrum Team có tạo Increment và thích ứng hiệu quả hay không.

**5. “Có Sprint thì hợp đồng có thể thay đổi tự động.”** Quyền Product Backlog khác quyền sửa hợp đồng.

**6. “Đã cố định giá và ngày thì phạm vi luôn linh hoạt.”** Phạm vi cũng có thể là điều khoản cứng.

**7. “Đã cố định cả ba biến thì Agile bảo đảm sẽ giao đủ.”** Một phương pháp không tạo thêm thời gian hoặc xóa rủi ro.

**8. “Ngày mốc là forecast.”** Mốc cam kết và dự báo theo bằng chứng phải phân biệt.

**9. “Forecast có nguy cơ trễ nghĩa là được tự dời hạn.”** Cần quyết định theo thẩm quyền.

**10. “Chi tiết mọi task cho 12 tuần sẽ làm rủi ro biến mất.”** Chi tiết giả định chưa kiểm chứng có thể tạo cảm giác chắc chắn giả.

**11. “Rolling wave nghĩa là hạng mục xa chưa cần quan tâm.”** Vẫn phải giữ nghĩa vụ, phụ thuộc và mốc; chỉ chưa cần chi tiết giả tạo.

**12. “Roadmap thay Product Backlog.”** Roadmap là định hướng; backlog là danh sách công việc sản phẩm có thứ tự và được làm rõ.

**13. “Backlog thay được baseline pháp lý.”** Nó không tự là văn bản thay đổi nghĩa vụ.

**14. “Mọi công việc nên thực hiện theo cột frontend, backend, database nối tiếp.”** Lát cắt dọc có thể giảm hàng chờ và cho phản hồi sớm.

**15. “Một giao diện chạy mock được coi là Increment Done.”** Chưa đủ nếu DoD yêu cầu tích hợp và kiểm chứng khác.

**16. “Cuối dự án có Sprint để kiểm thử tích hợp là ổn.”** Dồn test muộn làm rủi ro phát hiện lỗi lớn; tích hợp thường xuyên cần được duy trì.

**17. “Scrum bắt buộc ước lượng story points hoặc dùng velocity.”** Không có yêu cầu như vậy trong Scrum.

**18. “Velocity của các nhóm dùng để xếp hạng năng suất.”** Điểm ước lượng phụ thuộc nhóm và bối cảnh; không so trực tiếp.

**19. “Throughput trung bình là ngày hoàn tất chắc chắn.”** Biến động, loại item và phụ thuộc tạo bất định.

**20. “Có thể dùng P85 của cycle time như SLA hợp đồng.”** SLE và nghĩa vụ hợp đồng khác nhau.

**21. “Work Item Age 9/10 SLE tức hoàn thành 90%.”** Tuổi là thời gian đã trôi qua, không phải tiến độ công việc.

**22. “Little's Law cho biết P85 của từng PBI.”** Quan hệ trung bình không cho phân vị hoặc deadline cá nhân.

**23. “Giảm WIP bằng cách đổi tên cột.”** Ranh giới đo phải phản ánh công việc thật.

**24. “Một gate chỉ cần slide báo cáo đẹp.”** Gate có ích khi dựa trên bằng chứng và quyền quyết định rõ.

**25. “Sprint Review tự là nghiệm thu hợp đồng.”** Review Scrum và nghiệm thu pháp lý là hai việc có thể chia sẻ bằng chứng nhưng khác trách nhiệm.

**26. “Bộ phận mua sắm phải duyệt từng cách chia PBI.”** Phân quyền đúng có thể cho nhóm thích ứng trong phạm vi mà không thêm hàng chờ vô ích.

**27. “Product Owner được tự giảm DoD để kịp mốc.”** Chất lượng không được giảm trong Sprint; nghĩa vụ an toàn còn phải đáp ứng.

**28. “Prototype và mock cho phép bỏ test dịch vụ thật.”** Nếu tích hợp thật là điều kiện DoD/release, mock không thay thế.

**29. “Capacity danh nghĩa là toàn bộ thời gian dành cho chức năng mới.”** Cần xét nghỉ, hỗ trợ, test, CI, chất lượng và sự cố.

**30. “Buffer là phần tiền được tùy ý chi thêm.”** Dự phòng phải phù hợp ngân sách và thẩm quyền thực.

**31. “Chạy càng nhiều dự án song song, mỗi người càng hiệu quả.”** WIP và hàng chờ có thể làm luồng chậm.

**32. “Mọi thay đổi nhỏ đều không cần phê duyệt.”** Một nút nhỏ có thể làm đổi nghĩa vụ dữ liệu/tiêu chí nghiệm thu.

**33. “Không làm CR vì điều đó không Agile.”** Change control đúng nơi có thể bảo vệ sự hợp tác và tính minh bạch.

**34. “Nếu báo cáo 90% task Done thì 90% kết quả người dùng đã đạt.”** Tỷ lệ task không chứng minh Increment hoặc outcome.

**35. “Người dùng bấm nút đăng ký nghĩa là đã bắt đầu học.”** Cần định nghĩa activation và quan sát hành vi thực.

**36. “Chỉ cần một dashboard tổng hợp là đủ ra quyết định.”** Phải xem câu hỏi, ngữ cảnh, dữ liệu, rủi ro và quyền.

**37. “Đổi mô hình quản trị chỉ cần đổi công cụ.”** Vai trò, thẩm quyền, chính sách và hành vi phối hợp mới là trọng tâm.

**38. “Càng nhiều cuộc họp đồng bộ càng kiểm soát tốt.”** Cuộc họp không giúp quyết định/gỡ blocker có thể tạo thêm hàng chờ.

**39. “Rủi ro cao nghĩa phải bỏ hết phản hồi để tập trung làm.”** Thường cần nhận thông tin sớm hơn, nhưng trong phạm vi an toàn và quyền.

**40. “Dùng dữ liệu trước–sau là chứng minh quan hệ nhân quả.”** Phải xét độ khác biệt công việc, cỡ mẫu và các yếu tố khác.

**41. “Hybrid là một chứng chỉ bảo đảm thành công.”** Kết quả phụ thuộc thiết kế vận hành, con người và cách xử lý rủi ro thực.

## 29. Bài tập tình huống A: chọn cách lập kế hoạch cho từng loại công việc

Nhóm chuẩn bị phát triển một nền tảng học trực tuyến trong 12 tuần. Các công việc:

| Mã | Công việc | Đặc điểm |
| --- | --- | --- |
| A | Tích hợp SSO với hệ thống đối tác | Sandbox và thủ tục cấp quyền có mốc ngoài nhóm |
| B | Thiết kế màn hình sau đăng ký | Người học chưa thống nhất cách nhận xác nhận |
| C | Chống đăng ký trùng | Cần bảo vệ bất biến dữ liệu và test concurrent |
| D | Báo cáo quản trị bắt buộc theo SOW | Tiêu chí có trong hợp đồng nhưng cần ví dụ chi tiết |
| E | Tính năng gợi ý khóa cá nhân hóa | Outcome chưa được xác minh, chưa chắc trong scope |
| F | Migration dữ liệu người học | Rủi ro cao, rollback và quyền dữ liệu cần kiểm tra |
| G | Hỗ trợ lỗi production đang phát sinh | Không biết trước chính xác lượng việc |

### Câu hỏi

1. Với mỗi mã A–G, lựa chọn thiên về predictive, adaptive hay hybrid và giải thích.
2. Công việc nào nên có mốc/điều kiện rõ trước khi phát triển lớn?
3. Công việc nào cần một discovery hoặc spike nhỏ để giảm bất định?
4. Nếu E được nhiều người dùng yêu cầu nhưng không nằm trong SOW, có thể làm ngay không?
5. Vì sao C và F không thể kết luận hoàn tất từ unit test xanh đơn thuần?
6. Nêu hai việc có thể **chạy song song** trong khi chờ SSO mà không tạo báo cáo Done giả.
7. Ai quyết định thứ tự Product Backlog, ai có quyền sửa hợp đồng và ai tổ chức cách thực hiện?
8. Hãy thiết kế **một roadmap có điều kiện** cho bốn tuần đầu.

### Gợi ý lời giải

**Câu 1:** A thiên predictive ở phụ thuộc/gate, nhưng kiểm thử hợp đồng có thể làm tăng dần. B thiên adaptive vì cần thử UX. C hybrid: quy tắc bất biến/DoD cố định, thử kỹ thuật sớm và chia lát cắt. D hybrid: nghĩa vụ cứng nhưng refinement và thực hiện tăng dần. E adaptive nếu được phép nghiên cứu, có thể chưa được phép triển khai. F predictive về kế hoạch an toàn/migration, kết hợp test tự động và diễn tập tăng dần. G phù hợp Kanban, có chính sách ưu tiên theo mức rủi ro và capacity.

**Câu 2:** A cần mốc sandbox/quyền; D cần mốc và bằng chứng nghiệm thu; F cần kiểm tra dữ liệu, backup, rollback và phê duyệt; C cần điều kiện chất lượng trước khi dùng thật.

**Câu 3:** B cần usability/prototype; A cần thử hợp đồng API; C cần thử concurrency và retry; E cần kiểm chứng giá trị sản phẩm và phạm vi.

**Câu 4:** Không mặc nhiên. Đưa ý tưởng vào Product Backlog/decision log, xác minh quyền nghiên cứu và triển khai; nếu ảnh hưởng nghĩa vụ/giá/mốc thì cần phê duyệt tương ứng.

**Câu 5:** C đòi kiểm thử đồng thời qua tầng dữ liệu và idempotency; F cần test migration, dữ liệu lịch sử, quyền và phương án phục hồi. Unit test có thể không đại diện tình trạng thực.

**Câu 6:** Làm contract tests với mock được phép; xây luồng UX trên dữ liệu giả và thử tính khả dụng; chuẩn bị test data hoặc làm rõ quy tắc quyền. **Không gọi tích hợp thật Done khi chưa đạt điều kiện DoD.**

**Câu 7:** Trong Scrum, Product Owner chịu trách nhiệm Product Backlog; Developers tự quản cách thực hiện; thay nghĩa vụ hợp đồng thuộc người được ủy quyền theo quy trình thực.

**Câu 8:** Tuần 1–2 thử đăng ký và kịch bản lỗi trong môi trường cho phép, làm rõ quyền/API; tuần 3–4 thử mở bài đầu và tích hợp thật **nếu sandbox sẵn**, nếu không cập nhật forecast và thực hiện công việc giảm rủi ro. Bất kỳ mốc nghĩa vụ nào vẫn cần theo dõi riêng.

## 30. Bài tập tình huống B: tính toán và dự báo có giới hạn

Một nhóm có throughput sáu tuần gần nhất:

~~~text
3, 5, 4, 2, 6, 4 PBI Done/tuần
~~~

Một nhóm item Done khác có Cycle Time theo ngày làm việc:

~~~text
2, 3, 3, 4, 4, 5, 5, 5, 6, 6,
6, 7, 7, 8, 8, 9, 10, 11, 13, 18
~~~

Còn 16 PBI tương đối đồng nhất theo kế hoạch, trong đó một item tích hợp đang có Work Item Age **12 ngày** và bị chặn ở sandbox. Baseline yêu cầu một mốc giao trước ngày đã thống nhất.

### Câu hỏi

1. Throughput trung bình sáu tuần là bao nhiêu?
2. Từ trung bình ấy, phép chia tham khảo cho 16 PBI là bao nhiêu tuần? Có thể hứa chắc mốc này không?
3. Tính trung vị Cycle Time và P85/P95 nearest-rank.
4. Có thể diễn đạt một SLE tham khảo như thế nào?
5. Item Age 12 ngày có ý nghĩa gì đối với SLE P85 là 10 ngày?
6. Vì sao một item chưa Done không có trong mẫu Cycle Time của những item đã Done?
7. Có thể dùng Little's Law để dự báo P95 của một item không?
8. Nếu Product Owner muốn thay 4 PBI bắt buộc bằng 4 PBI mới cùng số lượng, cần hỏi gì?
9. Nêu một báo cáo rủi ro mốc vừa trung thực vừa có phương án.

### Gợi ý lời giải

**Câu 1:** \((3+5+4+2+6+4)/6=24/6=4\) PBI/tuần.

**Câu 2:** \(16/4=4\) tuần là **tham khảo thô**, không phải lời hứa. Dữ liệu biến động 2–6 item/tuần; backlog, năng lực, phụ thuộc và phân bố loại việc có thể thay đổi.

**Câu 3:** Trung vị **6 ngày**; P85 nearest-rank ở vị trí \(\lceil0{,}85\times20\rceil=17\) là **10 ngày**, P95 ở vị trí 19 là **13 ngày**.

**Câu 4:** “Với loại PBI và ranh giới từ bắt đầu tới DoD đã xác định, kỳ vọng khoảng 85% item hoàn tất trong không quá 10 ngày làm việc.” Nêu rõ đây là giả thuyết dựa trên mẫu minh họa, cần cập nhật khi có thêm dữ liệu.

**Câu 5:** Item đã quá mốc SLE và cần gỡ blocker, xem rủi ro mốc. Không kết luận xác suất trễ riêng là 85%, và không lấy \(10-12=-2\) làm thời gian còn lại.

**Câu 6:** Cycle Time chỉ được biết đầy đủ khi item đạt Done. Các item dở có thể kéo dài và làm phân bố của riêng những item Done trông lạc quan; cần xem Work Item Age.

**Câu 7:** Không. Little's Law liên hệ **trung bình** WIP, throughput, cycle time trong điều kiện phù hợp, không cho P95 hay deadline của một item.

**Câu 8:** Bốn PBI mới có nghĩa vụ/hành vi/chi phí tương đương không? Có ảnh hưởng Product Goal, phạm vi đã ký, chất lượng, thời hạn hoặc nghiệm thu không? Ai có quyền phê duyệt thay đổi? **Đếm bốn đổi bốn không chứng minh hợp lệ.**

**Câu 9 — Mẫu báo cáo:**

> “Throughput lịch sử trung bình là 4 PBI/tuần, nên 16 PBI còn lại có điểm tham khảo thô 4 tuần nhưng chưa tính hết phụ thuộc. Một item tích hợp đã có Age 12 ngày và chờ sandbox, vượt mốc kỳ vọng tham khảo P85 10 ngày. Nhóm đề xuất gỡ phụ thuộc với đối tác, ưu tiên kiểm thử tích hợp và cập nhật forecast tại điểm nhận sandbox; nếu mốc nghĩa vụ có nguy cơ, sẽ trình các phương án theo thẩm quyền thay vì tự thay baseline.”

## 31. Bài tập tình huống C: chất lượng và hợp đồng cùng gây áp lực

Trong Sprint trước ngày khai giảng:

| Hạng mục | Tình trạng giả định |
| --- | --- |
| Đăng ký bình thường | UI/API chạy được trong thử nghiệm |
| Retry sau timeout | Chưa bảo đảm không tạo dữ liệu trùng |
| Phân quyền | Có test thất bại với dữ liệu tài khoản khác |
| Mở bài đầu | Chưa tích hợp thật với API quyền học |
| Báo cáo quản trị | Còn thiếu bằng chứng theo hợp đồng |
| Release gate | Chưa có phê duyệt an toàn bắt buộc |

Một bên đề nghị:

> “Để kịp ngày, tạm bỏ kiểm tra phân quyền, chuyển tất cả ticket sang Done, khai giảng trước rồi vá.”

### Câu hỏi

1. Đề nghị ấy sai ở đâu xét theo DoD và rủi ro người dùng?
2. Sprint Goal đã đạt chưa nếu chỉ có UI chạy?
3. Điều gì có thể thay đổi trong quyền Developers/PO mà không vi phạm nghĩa vụ?
4. Có thể mở pilot hạn chế hoặc dùng feature flag không? Điều kiện nào cần kiểm tra?
5. Khi nào cần người có thẩm quyền hợp đồng, security hoặc release quyết định?
6. Tạo một Decision Brief ngắn gồm **ba lựa chọn hợp lệ hoặc cần duyệt**.
7. Sau Sprint, chỉ số nào giúp dự báo cải thiện thay vì đổ lỗi cá nhân?
8. Nêu cách xử lý nếu có sự cố đang ảnh hưởng dữ liệu thật.

### Gợi ý lời giải

**Câu 1:** Không thể đánh dấu Done nếu chưa đáp ứng DoD; bỏ kiểm tra quyền khi đã phát hiện lỗi có thể gây hại dữ liệu. Chất lượng không được giảm trong Sprint.

**Câu 2:** Chưa đủ bằng chứng. Sprint Goal tập trung kết quả có giá trị, không phải tỷ lệ màn hình/code. Nếu quyền học và xác nhận chưa đáng tin, cần minh bạch phần chưa đạt.

**Câu 3:** Chia lại kế hoạch kỹ thuật, ưu tiên sửa lỗi, giảm WIP, cùng tích hợp, điều chỉnh Sprint Backlog theo Sprint Goal; trao đổi phạm vi với PO và kiểm tra ranh giới hợp đồng.

**Câu 4:** Chỉ khi phần được pilot **đã đạt DoD và tất cả điều kiện an toàn/release liên quan được đáp ứng**. Feature flag không làm an toàn một đường dữ liệu có lỗ hổng.

**Câu 5:** Khi thay đổi mốc, đầu ra, giá, nghiệm thu, quyền dữ liệu hoặc điều kiện release bắt buộc; cần người có quyền theo tài liệu thực.

**Câu 6:** (A) Giữ mốc và tập trung khắc phục rủi ro/cung cấp bằng chứng nếu còn khả thi. (B) Chỉ mở một phần Done được phê duyệt và không lộ dữ liệu, nếu chính sách và hợp đồng cho phép. (C) Trình điều chỉnh mốc hoặc nghĩa vụ qua quy trình nếu không thể đạt trong quyền hiện có. Không trình một phương án “tự bỏ DoD”.

**Câu 7:** Work Item Age, blocked time theo nguyên nhân, Cycle Time, throughput thật sự Done, lỗi hồi quy, thời gian phản hồi CI, kết quả sử dụng và độ ổn định; không xếp hạng Developers.

**Câu 8:** Ưu tiên bảo vệ người dùng và dữ liệu, ứng cứu theo quyền, ghi sự kiện và bằng chứng, khôi phục an toàn; sau đó điều tra và phòng ngừa lặp. Không đợi Sprint Retrospective mới xử lý sự cố.

## 32. Mẫu kế hoạch kết hợp một trang

Nhóm có thể tạo **Hybrid Planning Brief** ngắn để bảo đảm các tầng kế hoạch tương thích nhau. Đây là **mẫu học tập**, không phải hồ sơ pháp lý hay artifact Scrum bắt buộc.

~~~text
Tên sản phẩm/dòng giá trị:
  ...

Product Goal / outcome:
  ...

Người dùng và vấn đề:
  ...

Baseline nghĩa vụ / nguồn căn cứ:
  - Đầu ra bắt buộc: ...
  - Ngân sách/thời hạn: ...
  - DoD/chất lượng và quy định: ...
  - Người có quyền phê duyệt: ...

Các giả định và bất định cần kiểm chứng:
  - Nhu cầu người dùng: ...
  - Tích hợp/kỹ thuật: ...
  - Nguồn lực/đối tác: ...

Các mốc và governance gates:
  - Mốc: ...  Điều kiện: ...  Người quyết định: ...

Đường phụ thuộc quan trọng:
  - Phụ thuộc: ...  Người xử lý: ...  Deadline/trigger: ...

Rolling-wave plan:
  - Gần: PBI/acceptance examples cần Done trong 1-2 Sprint
  - Trung hạn: khả năng và phụ thuộc cần làm rõ
  - Xa: nghĩa vụ, rủi ro và khoảng forecast, chưa giả chi tiết

Dữ liệu dự báo:
  - Workflow và ranh giới đo: ...
  - Throughput/Cycle Time/Work Item Age/WIP: ...
  - Phạm vi và giả định: ...
  - Kịch bản/rủi ro: ...

Phản hồi và kiểm chứng:
  - Usability/research/outcome: ...
  - CI/contract/integration tests: ...
  - Chứng cứ DoD: ...

Thay đổi và quyết định:
  - Việc được làm rõ trong quyền: ...
  - Việc cần change control: ...

Guardrails:
  - Dữ liệu, bảo mật, chất lượng, quyền, nhịp bền vững: ...

Nhịp và mốc xem lại:
  - Daily/Sprint/Review: ...
  - Governance gate/contract check: ...
  - Trigger cảnh báo sớm: ...

Người phối hợp và hành động tiếp:
  ...
~~~

### 32.1. Cách dùng mẫu

Không biến brief thành tài liệu 30 trang cần ký trước mỗi Sprint. Cần **đủ thông tin để quyết định** và cập nhật khi:

- Baseline được sửa hợp lệ.
- Forecast thay đổi đáng kể.
- Phụ thuộc phát sinh hoặc hết hiệu lực.
- Có dữ liệu người dùng mới làm đổi ưu tiên.
- Một gate, DoD hoặc tiêu chuẩn chất lượng bị ảnh hưởng.

### 32.2. Một họp xem kế hoạch ngắn

Gợi ý trao đổi:

1. **Mục tiêu và nghĩa vụ:** Điều gì vẫn không thay đổi?
2. **Đã Done:** Lát cắt giá trị nào đã đạt DoD?
3. **Bằng chứng mới:** Người dùng và hệ thống đã cho thấy điều gì?
4. **Forecast:** Chỗ nào có rủi ro mốc, độ bất định ra sao?
5. **Phụ thuộc:** Ai có thể tháo gỡ và theo quyền nào?
6. **Quyết định:** Điều gì nhóm có thể làm ngay, điều gì cần phê duyệt?
7. **Guardrail:** Có rủi ro chất lượng/dữ liệu nào đang xấu đi?

Kết thúc bằng **hành động và điểm xem lại**, không chỉ cập nhật status.

## 33. Checklist lựa chọn và vận hành kế hoạch kết hợp

### A. Hiểu bối cảnh

1. **Product Goal:** Có kết quả người dùng rõ hơn danh sách chức năng?
2. **Nghĩa vụ:** Những điều gì thật sự cố định theo hợp đồng/quy định?
3. **Quyền:** Ai có thể thay thứ tự backlog, ai thay baseline?
4. **Bất định:** Điều chưa biết là nhu cầu, kỹ thuật hay phụ thuộc?
5. **Đảo ngược:** Quyết định nào khó sửa và cần kiểm chứng trước?
6. **Mức thử được phép:** Có dữ liệu, môi trường và quyền cho discovery/spike?
7. **Tính khả thi:** Có rủi ro kế hoạch không thể thỏa đồng thời mọi điều kiện?

### B. Thiết kế kế hoạch

8. **Ba tầng:** Đã phân biệt cam kết, roadmap/forecast và thực thi?
9. **Baseline:** Có lưu nghĩa vụ gốc và thay đổi hợp lệ?
10. **Rolling-wave:** Chi tiết gần, xa giữ định hướng và giả định?
11. **Vertical slices:** PBI có giá trị sử dụng, không chỉ task từng tầng?
12. **Dependencies:** Ai chịu trách nhiệm, điều kiện xong và ngày cần?
13. **Đường găng:** Những chuỗi không thể song song đã được nhận diện?
14. **Risk work:** Có xử lý bất định lớn trước điểm khó đảo ngược?
15. **Quality work:** Test, CI, data, security nằm trong capacity/DoD?
16. **Buffer:** Nguồn dự phòng có trong quyền ngân sách và kế hoạch?
17. **Gates:** Điều kiện và người có thẩm quyền được xác định?

### C. Dữ liệu và dự báo

18. **Workflow:** Start/Done, đơn vị thời gian và loại item rõ?
19. **WIP:** Có biết việc đang mở và hàng chờ?
20. **Work Item Age:** Có nhìn item chưa Done và blocker?
21. **Cycle Time:** Có xem phân bố, đuôi dài và cỡ mẫu?
22. **Throughput:** Chỉ đếm item thật sự đạt DoD?
23. **SLE:** Không nhầm kỳ vọng dịch vụ với deadline hợp đồng?
24. **Uncertainty:** Dự báo có giả định và khoảng bất định?
25. **Scope change:** Có cập nhật forecast khi số loại PBI thay đổi?
26. **Baseline gap:** Có ghi khác biệt giữa cam kết và forecast?
27. **Không lạm dụng metric:** Không xếp hạng cá nhân bằng velocity/Cycle Time?

### D. Scrum, Kanban và kỹ thuật

28. **Sprint Goal:** Có mục tiêu chung cho Sprint và được kiểm tra hàng ngày?
29. **Sprint Backlog:** Developers có quyền điều chỉnh How trong Sprint?
30. **DoD:** Không gọi chưa đạt chuẩn là Done?
31. **Review:** Có nhận phản hồi thật, không nhầm với nghiệm thu?
32. **Kanban:** WIP và chính sách xử lý blocker có phù hợp?
33. **XP/CI:** Thay đổi được tích hợp và kiểm thử thường xuyên?
34. **Contract tests:** Ranh giới với nhóm/đối tác được kiểm chứng?
35. **Release:** Quyền, gate, rollback và quan sát được làm rõ?

### E. Quản trị thay đổi và cải tiến

36. **Phân loại:** Yêu cầu mới là lỗi, làm rõ, thay cách thực hiện hay đổi nghĩa vụ?
37. **Change control:** Việc vượt quyền có được trình đúng nơi?
38. **Không làm trước xin ký sau:** Thay đổi ràng buộc chưa được triển khai nếu chưa cho phép?
39. **Traceability:** Nghĩa vụ, PBI, test và nghiệm thu liên kết đủ dùng?
40. **Security:** Không bỏ kiểm soát bắt buộc để đúng hạn?
41. **Decision latency:** Các quyết định chờ có người phụ trách và ngày xem lại?
42. **Early warning:** Điều kiện báo rủi ro mốc được thống nhất?
43. **Product outcome:** Người dùng thực sự nhận được giá trị hay chỉ có code?
44. **Guardrail:** Tốc độ không làm xấu dữ liệu, lỗi và nhịp làm việc?
45. **Retrospective:** Có dùng dữ liệu để cải tiến chính sách kế hoạch?
46. **Học hỏi:** Khi giả định sai, nhóm có thay kế hoạch trong quyền thay vì che dữ liệu?

## 34. Tổng kết: dự báo cho điều cần cam kết, thích ứng cho điều cần học

Không có một tỷ lệ “70% predictive, 30% adaptive” đúng cho mọi dự án. Sự kết hợp có chất lượng bắt đầu từ **tính chất của từng quyết định và ràng buộc thực**, không từ nhãn phương pháp.

| Lựa chọn dễ sai | Lựa chọn có căn cứ hơn |
| --- | --- |
| Cố định mọi task ngay từ ngày đầu | Cố định nghĩa vụ cần thiết, làm rõ dần giải pháp |
| Không theo dõi hợp đồng vì nhóm làm Agile | Giữ baseline và thẩm quyền song song với Product Backlog |
| Chỉ theo biểu đồ kế hoạch, bỏ trạng thái thực | Cập nhật forecast từ WIP, age, throughput, chất lượng |
| Dùng velocity như cam kết chắc chắn | Dự báo với dữ liệu, phân bố và giả định rõ |
| Chỉ có đầu ra kỹ thuật từng tầng | Giao lát cắt dọc thực sự đạt DoD |
| Đợi gần cuối mới tích hợp và kiểm thử | Dùng CI, XP, contract tests và giảm rủi ro sớm |
| Mốc thời gian lấn át mọi chất lượng | Bảo vệ DoD, security và điều kiện bắt buộc |
| Sprint Review được coi là nghiệm thu pháp lý | Phân biệt phản hồi sản phẩm và quyết định theo hợp đồng |
| Khách hàng đề nghị là lập tức thêm scope | Phân loại, đánh giá và phê duyệt theo quyền |
| Kế hoạch không bao giờ được cập nhật | Giữ baseline, cập nhật forecast và xử lý chênh lệch |
| Mọi thứ đều cần một hội đồng duyệt | Phân quyền thay đổi thường ngày, giữ gate cho rủi ro thật |
| Hàng chờ quyết định bị gọi là “Developer chậm” | Đo blocked time và gỡ đúng phụ thuộc |
| Chỉ nhìn số task Done | Kiểm tra Increment, outcome người dùng và chất lượng |
| Dự báo trễ được giấu tới ngày cuối | Escalation sớm với bằng chứng và phương án |

**Ghi nhớ:** Một cách phối hợp hữu ích là **Nhận diện nghĩa vụ và bất định → Lập mốc/điều kiện có căn cứ → Chia lát cắt giá trị → Kiểm chứng rủi ro sớm → Giao Increment đạt DoD → Đo dòng công việc và phản hồi → Cập nhật forecast → Điều chỉnh trong quyền hoặc đề xuất thay đổi chính thức → Lặp lại**. Trong **AGILE_DEVELOPMENT**, Scrum giúp giữ Product Goal, Sprint Goal và Increment rõ ràng; Kanban giúp nhìn WIP, tuổi công việc, throughput và hàng chờ; XP giúp thay đổi an toàn qua kiểm thử và tích hợp thường xuyên; Lean nhắc tối ưu toàn dòng thay vì làm bận từng bộ phận. **Dự báo có trách nhiệm không chống lại tính thích ứng; tính thích ứng có kỷ luật giúp dự báo tốt hơn, đồng thời không đánh đổi những ràng buộc và nghĩa vụ phải được tôn trọng.**
