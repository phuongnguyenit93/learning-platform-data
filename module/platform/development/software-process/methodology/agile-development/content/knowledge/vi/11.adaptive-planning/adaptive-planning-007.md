# Dành năng lực cho kiểm thử, tích hợp, bảo trì và việc phát sinh

## 1. Vì sao kế hoạch Agile phải tính cả công việc không tạo tính năng mới?

Một nhóm phát triển nền tảng học trực tuyến vừa chọn các user story cho hai tuần tới: tìm khóa học, đăng ký khóa và nhận email xác nhận. Nếu chỉ tính thời gian viết mã cho ba tính năng, nhóm dễ cho rằng toàn bộ năng lực đã được sử dụng hết và mọi việc còn lại có thể xử lý “khi rảnh”. Nhưng để người học sử dụng ổn định, nhóm còn phải kiểm thử hành vi, tích hợp các thành phần, sửa lỗi, vận hành hệ thống, cập nhật phụ thuộc và xử lý những sự cố không thể dự đoán chính xác.

Nếu không dành năng lực cho các công việc này, những điều sau thường xuất hiện:

- Phần lập trình được báo “xong”, nhưng kiểm thử và tích hợp phải dồn về cuối đợt.
- Nhiều hạng mục chưa đạt **Definition of Done** (DoD), dù báo cáo tiến độ có vẻ tốt.
- Mỗi lỗi production hoặc yêu cầu hỗ trợ lại kéo thành viên khỏi công việc đã lên kế hoạch.
- Nhóm thường xuyên làm thêm giờ để bù phần việc vốn đã biết là sẽ xảy ra.
- Việc bảo trì phòng ngừa bị hoãn, khiến thay đổi về sau chậm, đắt và rủi ro hơn.

**Lập kế hoạch thích ứng** (*adaptive planning*) là cách tạo kế hoạch đủ rõ để phối hợp, đồng thời giữ khả năng điều chỉnh khi có phản hồi mới hoặc thông tin ngoài dự kiến. Với module **AGILE_DEVELOPMENT**, mục tiêu là giao sản phẩm có giá trị theo từng phần tăng dần, nhận phản hồi sớm và liên tục cải tiến. Muốn làm được điều đó, kế hoạch phải phản ánh **toàn bộ năng lực cần để giao giá trị an toàn**, không chỉ thời gian gõ mã cho chức năng mới.

Một nguyên tắc thực dụng:

> **Lập kế hoạch cho công việc hoàn tất từ đầu đến cuối, bảo trì có chủ đích và phần bất định có khả năng xuất hiện; khi thực tế thay đổi, điều chỉnh phạm vi và thứ tự ưu tiên một cách minh bạch.**

Điều này không có nghĩa dự trữ một tỷ lệ phần trăm giống nhau cho mọi đội, cũng không có nghĩa kiểm thử hay sửa lỗi chỉ được thực hiện khi còn phần dự phòng. **Kiểm thử và tích hợp cần thiết để đạt DoD là một phần của chính công việc phải hoàn thành.**

## 2. Phân loại công việc để không bị bỏ sót

Một kế hoạch đáng tin cậy bắt đầu bằng việc nhìn thấy các loại nhu cầu đang dùng chung năng lực.

| Loại công việc | Ví dụ trên nền tảng học trực tuyến | Cách phản ánh trong kế hoạch |
| --- | --- | --- |
| **Tạo năng lực sản phẩm** | Người học đăng ký được khóa học | Ước lượng lát cắt hoàn chỉnh, gồm triển khai, review, kiểm thử và tích hợp theo DoD |
| **Kiểm thử và bảo đảm chất lượng** | Kiểm tra đăng ký trùng, phân quyền, các luồng thanh toán lỗi | Tính trong công việc liên quan hoặc công việc chất lượng riêng khi có mục tiêu độc lập |
| **Tích hợp và phát hành** | Tích hợp API với giao diện, kiểm tra dữ liệu và pipeline, chuẩn bị triển khai | Tính rõ trong từng phần tăng dần hoặc trong hoạt động phát hành có phạm vi xác định |
| **Bảo trì khắc phục** | Sửa lỗi gửi email xác nhận bị thất bại | Xếp ưu tiên theo tác động; dự kiến phần năng lực nếu thường xuyên xảy ra |
| **Bảo trì phòng ngừa / nâng cấp** | Cập nhật thư viện hết hỗ trợ, nâng cấp chứng chỉ, cải thiện cảnh báo | Đặt vào backlog hoặc kế hoạch vận hành, cấp năng lực có chủ đích |
| **Hỗ trợ và vận hành thường kỳ** | Hỗ trợ sự cố tài khoản, trả lời yêu cầu bộ phận chăm sóc khách hàng | Dựa trên lịch trực, thống kê và tải công việc thực tế |
| **Khám phá và giảm rủi ro** | Thử với người dùng, làm rõ quy tắc hoàn tiền, thử tích hợp bên thứ ba | Nêu kết quả cần học, giới hạn thời gian và quyết định tiếp theo |
| **Việc phát sinh khó dự đoán** | Đứt kết nối dịch vụ, lỗi nghiêm trọng, yêu cầu pháp lý khẩn | Có chính sách phân loại, phần năng lực dự phòng và cách điều chỉnh ưu tiên |
| **Phối hợp và cải tiến** | Review, lập kế hoạch, retrospective, đào tạo cần thiết | Tính vào tính sẵn có và năng lực thực tế, không giả định là thời gian miễn phí |

Hai lưu ý khi sử dụng bảng:

1. **Tránh tính hai lần.** Nếu kiểm thử tích hợp của story đã nằm trong ước lượng hoàn tất story, không trừ lại toàn bộ thời gian đó dưới một khoản “kiểm thử chung”. Ngược lại, nếu có đợt nâng cấp hạ tầng độc lập thì cần thể hiện công việc ấy rõ ràng.
2. **Phân loại để quản lý, không để dựng rào cản.** Một lỗi nghiêm trọng có thể liên quan chất lượng, vận hành và bảo trì cùng lúc. Điều quan trọng là biết ai xử lý, ảnh hưởng đến mục tiêu nào và nguồn năng lực đến từ đâu.

## 3. Năng lực, khối lượng công việc và cam kết là ba khái niệm khác nhau

**Năng lực (capacity)** là nguồn lực thực sự có thể dành cho công việc trong một khoảng thời gian, có xét nghỉ phép, trách nhiệm vận hành, phối hợp và những giới hạn khác.

**Khối lượng công việc (workload/demand)** là toàn bộ nhu cầu đang chờ hoặc có khả năng xuất hiện.

**Cam kết hoặc dự báo phạm vi** là quyết định nhóm và các bên liên quan thống nhất trên cơ sở mục tiêu, năng lực, rủi ro và điều còn chưa chắc chắn. Trong Scrum, **Sprint Goal** là cam kết của Sprint Backlog; danh sách Product Backlog Item được chọn là phần dự báo và kế hoạch có thể làm rõ hoặc thương lượng lại theo các quy tắc Scrum, chứ không phải lời cam kết cứng từng chi tiết bất kể thông tin mới.

Ba đại lượng không được coi là đồng nhất:

~~~text
Nhu cầu công việc: có thể lớn hơn rất nhiều năng lực
        ↓ ưu tiên + chia nhỏ + xử lý phụ thuộc
Năng lực thực tế: bị giới hạn bởi con người, thời gian và hệ thống
        ↓ lựa chọn với mức bất định hợp lý
Kế hoạch: mục tiêu, phạm vi dự kiến, chất lượng và cơ chế thích ứng
~~~

Một nhóm “bận 100%” không đồng nghĩa có dòng giao hàng tốt. Khi mọi người đều làm quá nhiều hạng mục, công việc chờ review và kiểm thử có thể tăng, thời gian hoàn thành kéo dài. Mục tiêu nên là **hoàn tất các lát cắt giá trị theo chất lượng đã thống nhất với nhịp có thể duy trì**, không phải làm đầy lịch của từng người.

### 3.1. Ước lượng công việc đến khi thật sự Done

Giả sử story “Người học đăng ký một khóa miễn phí” có các hoạt động:

| Hoạt động cần thiết | Ước lượng minh họa |
| --- | ---: |
| Làm rõ điều kiện đăng ký và ví dụ chấp nhận | 0,5 người-ngày |
| Thực hiện giao diện, xử lý nghiệp vụ và dữ liệu | 2 người-ngày |
| Review, điều chỉnh và tích hợp với hệ thống hiện có | 1 người-ngày |
| Kiểm thử hành vi, lỗi, phân quyền và hồi quy phù hợp | 1,5 người-ngày |
| Kiểm tra sẵn sàng vận hành và phần tài liệu cần thiết theo DoD | 0,5 người-ngày |
| **Tổng công sức tham khảo để hoàn tất** | **5,5 người-ngày** |

Đây là ví dụ ước lượng **công sức**, không phải khẳng định story sẽ hoàn thành sau đúng 5,5 ngày theo lịch. Một người kiểm thử có thể chỉ sẵn sàng ở một số thời điểm; hệ thống tích hợp có thể bị chặn; một số hoạt động diễn ra song song. Thời gian giao hàng thực tế chịu ảnh hưởng của phụ thuộc, hàng đợi và mức bất định.

Nhóm không nhất thiết phải tách mọi story thành bảng ngày công như trên. Nếu dùng story point hoặc throughput để dự báo, vẫn phải đảm bảo dữ liệu quá khứ và cách xác định Done **đã bao gồm công việc chất lượng**, không chỉ phần lập trình.

### 3.2. Năng lực không hoàn toàn hoán đổi giữa các vai trò

Ví dụ năm thành viên có tổng 25 người-ngày khả dụng không có nghĩa người kiểm thử, chuyên gia bảo mật hoặc người có quyền triển khai đều có thể được thay thế bởi những thành viên khác ngay lập tức.

Nhóm nên xem thêm:

- Ai hiểu quy tắc nghiệp vụ cần xác nhận?
- Người nào có quyền truy cập môi trường hoặc phê duyệt thay đổi?
- Luồng công việc đang nghẽn ở review, kiểm thử hay tích hợp?
- Việc hỗ trợ khẩn cấp có kéo đúng chuyên gia then chốt khỏi một phần tăng dần không?
- Cộng tác cặp, học chéo hoặc tự động hóa có thể giảm phụ thuộc trong tương lai không?

Chính vì thế, cộng tổng số ngày công chỉ là **điểm khởi đầu**. Kế hoạch còn cần kiểm tra ràng buộc kỹ năng, thời điểm sẵn sàng và khả năng tích hợp thực tế.

## 4. Một ví dụ phân bổ năng lực trong hai tuần

Giả sử nhóm có **5 người** trong giai đoạn **10 ngày làm việc**. Các số liệu sau hoàn toàn giả định để minh họa phương pháp:

| Khoản tính năng lực | Người-ngày |
| --- | ---: |
| Tổng thời gian theo lịch: 5 × 10 | 50 |
| Nghỉ phép và vắng mặt đã biết | −4 |
| Phối hợp định kỳ, lập kế hoạch, làm rõ và cải tiến ngoài hạng mục riêng | −6 |
| Hỗ trợ vận hành thường kỳ có thể dự đoán | −6 |
| Dự phòng cho sự cố hoặc việc phát sinh chưa biết | −6 |
| **Năng lực dự kiến có thể phân cho công việc đã lên kế hoạch** | **28** |

Nhóm có thể phân bổ **28 người-ngày** như sau:

| Nhóm công việc đã lên kế hoạch | Người-ngày | Định nghĩa hoàn tất |
| --- | ---: | --- |
| Lát cắt giá trị mới, bao gồm toàn bộ review, kiểm thử, tích hợp cần thiết | 18 | Các hạng mục đáp ứng tiêu chí và DoD |
| Bảo trì phòng ngừa và nâng cấp cần thiết | 7 | Rủi ro hoặc vấn đề bảo trì được xử lý, có bằng chứng kiểm tra |
| Khám phá nhu cầu và giảm rủi ro kỹ thuật | 3 | Có kết luận và quyết định tiếp theo có thể hành động |
| **Tổng** | **28** | |

**Giải thích quan trọng:**

- **6 ngày dự phòng** là năng lực dành cho sự không chắc chắn, **không phải 6 ngày mặc định phải tiêu hết**. Nếu việc phát sinh ít hơn dự kiến, nhóm có thể kéo thêm hạng mục nhỏ có giá trị hoặc cải tiến đã chuẩn bị, phù hợp mục tiêu và chính sách làm việc.
- **18 ngày cho năng lực mới đã bao gồm kiểm thử và tích hợp cần thiết**. Không được lên kế hoạch 18 ngày viết mã rồi hy vọng kiểm thử làm vào thời gian khác.
- **7 ngày bảo trì** thể hiện phần công việc đã biết có mục đích rõ, khác với 6 ngày dự phòng sự cố khó dự đoán. Nếu đợt đó có lỗi nghiêm trọng cần sửa, việc ưu tiên lại phải xét tác động thực tế.
- **3 ngày khám phá** có thể tạo giá trị bằng cách giúp tránh đầu tư sai hướng, nhưng cần mô tả câu hỏi học hỏi và kết quả bàn giao.
- Nếu một chuyên gia cần thiết không có thời gian đúng lúc, dù tổng 28 người-ngày vẫn còn, kế hoạch có thể phải thay đổi.

**Không có tỷ lệ dự phòng chuẩn áp dụng cho mọi nhóm.** Phần 6/50 trong ví dụ chỉ minh họa tính toán. Nhóm cần điều chỉnh từ dữ liệu thực tế: số lần sự cố, phân bố công việc hỗ trợ, mùa cao điểm, thay đổi sản phẩm và mức độ rủi ro.

### 4.1. Công thức tư duy và giới hạn

Có thể biểu diễn ở mức đơn giản:

\[
\text{Năng lực lập kế hoạch}
= \text{Năng lực theo lịch}
- \text{Vắng mặt}
- \text{Trách nhiệm cố định}
- \text{Công việc hỗ trợ dự kiến}
- \text{Dự phòng biến động}
\]

Đây là **công thức quản lý năng lực**, không phải phương trình dự báo chính xác năng suất. Các khoản trừ phải được định nghĩa sao cho **không trùng lặp**, và công việc hoàn tất vẫn phải được ước lượng từ đầu đến cuối.

Nếu nhóm đã dùng dữ liệu throughput lịch sử có bao gồm công việc hỗ trợ và ngày nghỉ, không nên máy móc trừ toàn bộ các khoản đó thêm lần nữa. Có thể sử dụng một trong hai cách nhất quán: **dự báo theo năng lực phân bổ** hoặc **dự báo theo hiệu quả giao hàng thực tế**, rồi điều chỉnh khi bối cảnh thay đổi.

## 5. Dành năng lực cho kiểm thử từ sớm

Kiểm thử là hoạt động đưa ra thông tin về rủi ro, chất lượng và sự phù hợp của sản phẩm. Kiểm thử không chỉ diễn ra sau khi lập trình viên thông báo hoàn tất.

### 5.1. Kiểm thử trong toàn bộ vòng đời story

| Thời điểm | Hoạt động có thể làm | Lợi ích |
| --- | --- | --- |
| **Khi làm rõ backlog** | Đặt ví dụ Given–When–Then, trường hợp biên, dữ liệu và rủi ro cần kiểm tra | Giảm hiểu nhầm yêu cầu |
| **Khi thiết kế giải pháp** | Xem khả năng kiểm thử, xử lý lỗi, quyền truy cập và khả năng quan sát | Tránh tạo kiến trúc khó kiểm chứng |
| **Khi triển khai** | Kiểm thử đơn vị, kiểm thử thành phần, kiểm tra thay đổi mã | Phát hiện lỗi gần nơi phát sinh |
| **Khi tích hợp** | Kiểm tra hợp đồng API, dữ liệu, phân quyền và các luồng xuyên hệ thống | Tìm sai khác giữa các thành phần |
| **Trước khi coi là Done** | Đối chiếu acceptance criteria, hồi quy và tiêu chuẩn DoD | Bảo đảm Increment đủ chất lượng |
| **Sau khi phát hành** | Giám sát lỗi, phản hồi người dùng, số liệu sử dụng | Phát hiện rủi ro chỉ lộ ra trong môi trường thật |

Ví dụ story đăng ký khóa học cần được kiểm tra cả trường hợp nhấn “Đăng ký” hai lần, mất kết nối khi gửi yêu cầu, người dùng không đủ quyền và hệ thống báo thành công khi dữ liệu chưa được lưu. Đợi đến cuối Sprint mới nghĩ tới những tình huống này có thể khiến kiến trúc và UI phải sửa gấp.

### 5.2. Ưu tiên kiểm thử theo rủi ro

Không phải mọi thay đổi cần cùng một số bộ kiểm thử. Cần cân nhắc:

- Mức thiệt hại nếu lỗi xảy ra, như thanh toán trùng hoặc lộ dữ liệu người học.
- Tần suất người dùng thực hiện hành vi.
- Độ phức tạp tích hợp và mức thay đổi của các thành phần phụ thuộc.
- Lịch sử lỗi, mức độ dễ quan sát và khả năng khôi phục.
- Yêu cầu an toàn, bảo mật, tiếp cận và tiêu chuẩn tổ chức.

**Kiểm thử theo rủi ro không đồng nghĩa bỏ kiểm thử để chạy kịp tiến độ.** Mục tiêu là chọn cách kiểm chứng phù hợp; những chuẩn bắt buộc trong DoD và ràng buộc bên ngoài vẫn phải được đáp ứng.

### 5.3. Nếu kiểm thử bị nghẽn thì thay đổi dòng làm việc

Giả sử cuối Sprint có tám story “code xong” nhưng một người kiểm thử chỉ có thể kiểm tra đầy đủ hai story. Gọi tám story này là “gần Done” không tạo ra Increment hoàn tất.

Nhóm có thể:

1. Giảm số story mở đồng thời, ưu tiên **cùng hoàn tất** các story đang chờ.
2. Chia story theo **lát cắt dọc**, tích hợp và kiểm thử từng phần nhỏ.
3. Để Developers cùng chịu trách nhiệm chất lượng, hỗ trợ thiết lập kiểm thử và sửa lỗi sớm; không xem kiểm thử là việc riêng một chức danh.
4. Tự động hóa các kiểm tra lặp lại khi chi phí bảo trì hợp lý.
5. Làm rõ thời điểm cần người có chuyên môn kiểm thử, thay vì dồn yêu cầu review vào một ngày cuối.

**Không nên giải quyết nghẽn bằng cách tự ý hạ DoD** hoặc tuyên bố kiểm thử hồi quy cần thiết là “việc sau Sprint”.

## 6. Tích hợp liên tục và phát hành cũng cần năng lực

Một tính năng có thể chạy trên máy của người phát triển nhưng thất bại khi kết nối cơ sở dữ liệu thật, dịch vụ email hoặc tính năng do nhóm khác xây. Tích hợp muộn làm tăng số giả định chưa kiểm chứng và khó xác định thay đổi nào gây lỗi.

### 6.1. Hoạt động tích hợp thường bị đánh giá thiếu

- Đồng bộ giao diện, API và mô hình dữ liệu khi quy tắc nghiệp vụ đổi.
- Chuẩn bị môi trường, cấu hình, quyền truy cập và dữ liệu kiểm thử.
- Xử lý tương thích ngược của API hoặc migration.
- Review thay đổi mã, xử lý xung đột và kiểm tra pipeline CI.
- Kiểm thử luồng xuyên dịch vụ, quan sát log và hành vi lỗi.
- Chuẩn bị cách triển khai, quan sát sau phát hành và phương án khôi phục khi rủi ro yêu cầu.

Nhóm cần đưa các hoạt động này vào **cách đánh giá năng lực hoàn tất**, hoặc thành hạng mục rõ ràng khi chúng là công việc dùng chung. Tránh tình trạng nhiều thành viên làm xong nhánh riêng nhưng không ai còn thời gian tích hợp.

### 6.2. Ví dụ luồng làm việc giảm dồn việc cuối đợt

~~~mermaid
flowchart LR
    A["Làm rõ lát cắt nhỏ"] --> B["Phát triển và kiểm thử sớm"]
    B --> C["Review, tích hợp, kiểm tra CI"]
    C --> D{"Đạt tiêu chí và DoD?"}
    D -->|"Chưa"| B
    D -->|"Có"| E["Increment có thể sử dụng"]
    E --> F["Phát hành theo quyết định phù hợp"]
    F --> G["Giám sát và nhận phản hồi"]
~~~

Đây là một cách minh họa luồng liên tục. **Increment đáp ứng DoD có thể sử dụng** không đồng nghĩa **bắt buộc phát hành công khai ngay tại thời điểm Done**. Việc phát hành phụ thuộc quyết định sản phẩm, vận hành, quyền truy cập và những yêu cầu hiện hành.

Các thực hành như tích hợp thường xuyên, kiểm thử tự động, phân nhỏ thay đổi, quản lý cấu hình và theo dõi lỗi giúp kiểm soát rủi ro. Chúng cũng cần năng lực thiết lập và bảo trì; một pipeline CI có kiểm thử chập chờn sẽ tiêu hao thời gian nếu không được cải thiện.

### 6.3. Đo chi phí chờ tích hợp

Có thể quan sát:

- Thời gian từ pull request sẵn sàng đến khi được review.
- Số lần pipeline CI thất bại và nguyên nhân.
- Số hạng mục đang chờ tích hợp.
- Số lỗi chỉ phát hiện khi chạy luồng xuyên hệ thống.
- Thời gian từ mã được tích hợp đến khi phần sản phẩm đủ điều kiện sử dụng.

Những số liệu này giúp tìm nút nghẽn. Không nên dùng số lần commit hoặc dòng mã làm thước đo trực tiếp cho giá trị của cá nhân.

## 7. Dành năng lực cho bảo trì và giảm rủi ro dài hạn

Bảo trì phần mềm gồm nhiều loại công việc:

| Loại | Ví dụ | Lý do không thể bỏ qua |
| --- | --- | --- |
| **Khắc phục (corrective)** | Sửa lỗi hiển thị sai giá hoặc tạo đơn đăng ký trùng | Bảo vệ trải nghiệm và tính đúng đắn |
| **Thích ứng (adaptive)** | Điều chỉnh hệ thống cho phiên bản API mới của nhà cung cấp | Giữ phần mềm hoạt động khi môi trường đổi |
| **Hoàn thiện (perfective)** | Cải thiện tốc độ tìm kiếm, đơn giản hóa luồng xử lý | Tăng khả năng sử dụng và khả năng bảo trì |
| **Phòng ngừa (preventive)** | Nâng cấp phụ thuộc có rủi ro, cải thiện kiểm thử, dọn mã khó thay đổi | Giảm xác suất và chi phí của vấn đề về sau |

Không phải mọi việc “nợ kỹ thuật” đều khẩn như nhau. Khi xếp ưu tiên, nhóm nên mô tả **tác động thực tế**:

> “Pipeline kiểm thử đăng ký khóa học thường thất bại không ổn định, khiến mỗi lần sửa lỗi phải chạy lại nhiều lần và chậm tích hợp. Chúng ta muốn ổn định bộ kiểm thử này để giảm thời gian chờ và phát hiện lỗi thật đáng tin cậy hơn.”

Mô tả này hữu ích hơn câu “Cần dành 20% thời gian sửa technical debt” nếu không biết sẽ sửa gì và đạt được điều gì.

### 7.1. Bảo trì đã biết và sự cố chưa biết

Cần tách:

- **Bảo trì đã biết:** Hạng mục có thể xếp ưu tiên và dự báo, như nâng cấp thư viện trước khi hết hỗ trợ.
- **Sự cố chưa biết:** Nhu cầu không thể đoán chính xác hạng mục và thời điểm, nhưng có thể ước lượng mức tải từ lịch sử.
- **Rủi ro đã biết nhưng chưa chắc xảy ra:** Ví dụ tích hợp dịch vụ mới có khả năng phát sinh lỗi môi trường; có thể dành thời gian giảm rủi ro sớm.

Không nên dùng “phần dự phòng” làm nơi chứa tất cả bảo trì đã biết, vì như vậy nhóm không nhìn thấy chi phí cơ hội và không thể chủ động ưu tiên.

### 7.2. Bảo trì cũng có giá trị sản phẩm

Việc nâng cấp thư viện bảo mật không trực tiếp tạo thêm nút bấm cho người học, nhưng có thể bảo vệ dữ liệu và giảm khả năng gián đoạn. Cải thiện khả năng triển khai giúp các increment sau được giao an toàn hơn. Vì thế, Product Owner và nhóm cần cân nhắc giá trị của bảo trì **cùng với** tính năng mới, thay vì mặc định bảo trì không mang lại giá trị.

Một số công việc bắt buộc theo chính sách bảo mật, pháp lý hoặc thời hạn hỗ trợ cần được thực hiện dù có ít lượt bình chọn trong backlog. Những ràng buộc này nên được thể hiện minh bạch.

## 8. Việc phát sinh: có dự phòng nhưng vẫn cần chính sách rõ

Không kế hoạch nào biết trước chính xác tất cả sự cố, yêu cầu hỗ trợ và thay đổi cần thực hiện. **Năng lực dự phòng** giúp nhóm tránh phải giả định rằng mọi thứ luôn diễn ra lý tưởng.

Tuy nhiên, chỉ ghi “10% buffer” không giải quyết được câu hỏi quan trọng: **khi việc mới xuất hiện, ai đánh giá, làm thế nào để chọn ưu tiên và hạng mục nào chịu tác động?**

### 8.1. Phân loại mức ưu tiên của việc phát sinh

| Nhóm tình huống | Ví dụ | Cách phản ứng |
| --- | --- | --- |
| **Sự cố khẩn, ảnh hưởng nghiêm trọng** | Rò rỉ dữ liệu, thanh toán sai diện rộng, dịch vụ cốt lõi không hoạt động | Thực hiện quy trình ứng cứu/phê duyệt và ưu tiên an toàn; thông báo tác động lên kế hoạch |
| **Lỗi quan trọng nhưng không khẩn** | Một nhóm thiết bị có lỗi hiển thị có cách khắc phục tạm | Đánh giá mức độ, ghi backlog và xếp ưu tiên phù hợp |
| **Yêu cầu thay đổi sản phẩm** | Thêm bộ lọc khóa học theo phản hồi mới | Làm rõ giá trị, chi phí và điều phải hoãn hoặc đổi thứ tự |
| **Hỗ trợ thường kỳ** | Tra cứu trạng thái đăng ký, xử lý tài khoản hợp lệ | Theo chính sách dịch vụ và tải dự kiến |
| **Cơ hội cải tiến** | Giảm thời gian chạy pipeline từ 20 xuống 8 phút | Cân nhắc giá trị và tác động, đưa vào công việc đã lên kế hoạch |

Nếu dùng **class of service** hoặc làn ưu tiên đặc biệt trong Kanban, phải định nghĩa tiêu chí “khẩn” nghiêm ngặt để không biến mọi yêu cầu của người có chức vụ thành việc khẩn. Cần nhìn rõ chi phí của việc ưu tiên: khi kéo một hạng mục khẩn vào, hạng mục nào sẽ bị trì hoãn?

### 8.2. Quy trình xử lý một việc ngoài kế hoạch

~~~mermaid
flowchart TD
    A["Xuất hiện yêu cầu / sự cố"] --> B["Đánh giá tác động, mức khẩn và người có thẩm quyền"]
    B --> C{"Cần ứng cứu ngay?"}
    C -->|"Có"| D["Thực hiện quy trình sự cố và ưu tiên an toàn"]
    C -->|"Không"| E["Đưa vào backlog / hàng đợi và xếp ưu tiên"]
    D --> F["Ước lượng tác động đến năng lực và mục tiêu"]
    E --> F
    F --> G["Điều chỉnh phạm vi, WIP hoặc kế hoạch minh bạch"]
    G --> H["Kiểm tra kết quả và cập nhật dữ liệu dự báo"]
~~~

Một công việc khẩn có thể vượt qua một số bước chuẩn bị thông thường, nhưng **không được miễn các kiểm soát an toàn bắt buộc**. Nhóm cần thực hiện xử lý sự cố theo cơ chế được phê duyệt và đưa những công việc đang làm bị ảnh hưởng trở lại kế hoạch.

### 8.3. Khi phần dự phòng không đủ

Giả sử trong bảng ở mục 4, nhóm dành **6 người-ngày** cho việc phát sinh, nhưng thực tế một sự cố nghiêm trọng tiêu tốn **8 người-ngày**.

- Mức phát sinh vượt dự phòng là **8 − 6 = 2 người-ngày** theo giả định công sức đơn giản.
- Nhóm cần đánh giá tác động thật đến những người đang xử lý, chuỗi phụ thuộc và hạng mục đã chọn.
- Nếu không còn năng lực, nên **điều chỉnh ít nhất một phần phạm vi có công sức/rủi ro tương ứng**, thống nhất lại kế hoạch với người liên quan, hoặc có phương án hỗ trợ phù hợp.
- **Không nên tự ý bỏ kiểm thử hoặc DoD để “tiết kiệm 2 ngày”.**

Việc cân đối thực tế không luôn đơn giản bằng phép trừ 2 người-ngày: sự cố có thể lấy mất thời gian của người duy nhất biết cách tích hợp cổng thanh toán, khiến một hạng mục trì hoãn dài hơn. Vì vậy cần xem **nút nghẽn và khả năng sẵn sàng của vai trò**, không chỉ tổng số giờ.

Nếu ít việc phát sinh hơn dự kiến, nhóm có thể chọn thêm công việc có giá trị đã được làm rõ. Nhưng cần tránh lấp kín mọi khoảng trống bằng nhiều việc dở dang; hoàn thiện kiểm thử, bảo trì và giảm WIP thường mang lại ích lợi lớn hơn.

## 9. Cân bằng công việc trong Scrum, Kanban và XP

### 9.1. Scrum: năng lực hỗ trợ Sprint Goal và Increment

Trong Scrum, Sprint Planning cần cân nhắc **năng lực hiện tại, hiệu suất trước đó và Definition of Done** khi Developers dự báo PBI có thể hoàn thành. Công việc kiểm thử, tích hợp và bảo trì cần thiết không thể để ngoài kế hoạch chỉ vì không trực tiếp tạo UI.

Điểm cần nhớ:

- **Sprint Goal** là cam kết của Sprint Backlog; **DoD** là cam kết của Increment.
- Developers lập kế hoạch công việc cần thiết để tạo Increment đáp ứng DoD, và cập nhật Sprint Backlog khi học được thông tin mới.
- Product Owner chịu trách nhiệm về giá trị và thứ tự Product Backlog; Developers cùng trao đổi để điều chỉnh phạm vi trong Sprint mà không làm nguy hại Sprint Goal.
- Nếu sự cố nghiêm trọng đe dọa Sprint Goal hoặc nhu cầu sản phẩm thay đổi, phải xử lý qua cơ chế Scrum phù hợp; không giả định Sprint là hợp đồng cố định mọi PBI.
- Sprint Retrospective là cơ hội xem lại chất lượng kế hoạch, số việc phát sinh, nghẽn kiểm thử/tích hợp và các cải tiến cho Sprint tiếp.

**Scrum không quy định tỷ lệ cố định “bao nhiêu phần trăm cho bảo trì” hay “bao nhiêu phần trăm buffer”.** Nhóm cần ra quyết định dựa trên sản phẩm, năng lực, rủi ro và dữ liệu thực tế.

### 9.2. Kanban: quản lý công việc đến liên tục

Với Kanban, nhóm thường làm việc theo luồng liên tục, có thể phân loại công việc và trực quan hóa những hạng mục đang chờ/đang làm. Các chính sách như **WIP limits, quy tắc kéo công việc, class of service, cách xử lý hạng mục bị chặn** có thể giúp cân bằng công việc kế hoạch và việc đột xuất.

Ví dụ, nhóm hỗ trợ sản phẩm học trực tuyến có thể duy trì bảng:

| Hàng đợi | Ví dụ | Nguyên tắc phối hợp |
| --- | --- | --- |
| Phát triển giá trị mới | Lưu khóa yêu thích | Chỉ kéo khi còn khả năng xử lý trong các bước tiếp theo |
| Bảo trì đã biết | Nâng cấp thư viện hoặc sửa lỗi phân quyền | Xếp ưu tiên theo tác động và rủi ro, không để tồn vô hạn |
| Hỗ trợ thường kỳ | Xử lý yêu cầu tài khoản | Phân công luân phiên hoặc theo năng lực đã thống nhất |
| Khẩn cấp | Sự cố thanh toán diện rộng | Chính sách ứng cứu riêng, giới hạn và theo dõi chi phí gián đoạn |

Các chỉ số **work item age, cycle time, throughput, WIP, thời gian bị chặn** giúp nhóm nhận ra nơi công việc chậm lại. Không cần tổ chức Sprint nếu luồng công việc và bối cảnh không phù hợp.

### 9.3. Extreme Programming (XP): chất lượng là một phần của tốc độ bền vững

XP khuyến khích **kiểm thử tự động, phát triển hướng kiểm thử, tích hợp liên tục, tái cấu trúc mã và các đợt giao nhỏ**. Những thực hành này giúp nhóm giảm lỗi và duy trì khả năng đổi hướng khi học thêm.

Nhưng chúng không miễn phí: thời gian thiết lập kiểm thử, bảo trì pipeline và cải thiện thiết kế cần nằm trong cách quản lý năng lực. Bỏ các hoạt động chất lượng để tăng số story hoàn tất trong ngắn hạn có thể làm giảm khả năng giao thay đổi ở những đợt sau.

### 9.4. Không có một cách phân bổ chung cho mọi framework

| Vấn đề | Scrum | Kanban | XP |
| --- | --- | --- | --- |
| Lập kế hoạch công việc | Sprint Planning, Sprint Goal, dự báo trong Sprint | Quyết định kéo việc và quản lý luồng liên tục | Lựa chọn story nhỏ, phản hồi thường xuyên |
| Xử lý việc phát sinh | Đánh giá tác động tới Sprint Goal, thương lượng phạm vi phù hợp | Chính sách class of service, WIP và hàng đợi | Giao nhỏ, tích hợp và kiểm thử để thay đổi an toàn |
| Chất lượng | Increment đáp ứng Definition of Done | Chính sách hoàn tất và tiêu chuẩn chất lượng phù hợp hệ thống | Kỷ luật kỹ thuật, kiểm thử và tích hợp thường xuyên |
| Cải tiến | Sprint Retrospective | Xem lại luồng, chính sách và dữ liệu | Phản hồi nhanh về sản phẩm lẫn kỹ thuật |

Nhóm có thể kết hợp các kỹ thuật phù hợp, nhưng cần phân biệt đâu là yêu cầu của framework, đâu là working agreement tự chọn và đâu là ràng buộc tổ chức.

## 10. Dùng dữ liệu nào để điều chỉnh mức dự phòng?

Dự phòng quá ít khiến nhóm dễ vỡ kế hoạch; dự phòng quá nhiều có thể làm chậm việc giao tính năng có giá trị nếu khả năng đang bị để không. Điều quan trọng không phải chọn “con số đẹp” mà là **liên tục học từ mức biến động thực tế**.

| Tín hiệu | Câu hỏi cần tìm hiểu | Cách tránh diễn giải sai |
| --- | --- | --- |
| **Số người-ngày hỗ trợ / sự cố mỗi giai đoạn** | Nhu cầu hỗ trợ thường xuyên ở mức nào, biến động ra sao? | Phân biệt sự cố bất thường với mức tải thông thường |
| **Số lần thay đổi ưu tiên khẩn** | Điều gì khiến nhiều việc đang làm bị gián đoạn? | Không gọi mọi thay đổi backlog là sự cố |
| **WIP và tuổi công việc** | Có nhiều việc đang dở, việc nào đang già đi vì chờ? | Hạng mục lớn và hạng mục bị chặn có hành vi khác nhau |
| **Cycle time / throughput** | Luồng hoàn tất có ổn định hơn không? | Xem phân bố và loại công việc, tránh chỉ lấy trung bình |
| **Lỗi sau phát hành** | Cắt giảm kiểm thử có tạo rủi ro không? | Đọc cùng mức nghiêm trọng, phạm vi và khả năng phát hiện |
| **Thời gian chờ CI, review, môi trường** | Đang mất năng lực ở đâu? | Không quy mọi chờ đợi thành thiếu trách nhiệm cá nhân |
| **Công việc bảo trì tồn đọng** | Có rủi ro nền tảng ngày càng tăng? | Phân biệt việc mang giá trị thực với mong muốn làm sạch mã chủ quan |
| **Mức làm thêm ngoài kế hoạch** | Tải công việc có còn bền vững? | Xem ở cấp nhóm, tôn trọng quyền riêng tư và bối cảnh |
| **Kết quả người dùng** | Các phần tăng dần có cải thiện hành trình người học? | Số tính năng giao không tự chứng minh giá trị |

### 10.1. Không dùng một trung bình che giấu biến động

Giả sử số người-ngày dành cho sự cố ở sáu giai đoạn gần nhất là: **2, 3, 2, 11, 3, 3**. Trung bình là **4 người-ngày**, nhưng năm trong sáu giai đoạn có mức **không quá 3**, trong khi có một giai đoạn vọt lên **11**.

Nếu chỉ dành đúng 4 người-ngày cho mọi giai đoạn mà không có chính sách xử lý sự cố lớn, nhóm vẫn có nguy cơ thiếu năng lực trong đợt bất thường. Ngược lại, dành 11 người-ngày cho mọi giai đoạn có thể không hiệu quả nếu cơ chế xử lý sự cố lớn cho phép điều chỉnh kế hoạch minh bạch.

Nhóm nên xem **phân bố, nguyên nhân, tính thời vụ và mức rủi ro chấp nhận được**. Với dữ liệu ít, không nên tuyên bố một mức dự phòng bảo đảm xác suất hoàn thành nào đó; hãy thử và điều chỉnh cùng các bên liên quan.

### 10.2. Đo cải tiến, không xếp hạng cá nhân

Velocity, số story hoàn tất hoặc thời gian xử lý lỗi không nên được dùng như thước đo trực tiếp năng suất từng người. Chúng chịu ảnh hưởng của kích thước hạng mục, mức rủi ro, năng lực theo vai trò và các công việc không nhìn thấy.

Số liệu nên giúp trả lời **“Điều gì đang làm giảm khả năng giao giá trị và cách nào cải thiện được?”**. Khi nhóm bắt đầu tối ưu số task đóng mà bỏ qua kiểm thử và bảo trì, chỉ số có thể đẹp lên trong khi chất lượng và sự tin cậy giảm.

## 11. Quy trình sáu bước để lập kế hoạch thích ứng

### Bước 1 — Xác định mục tiêu và tiêu chuẩn không được đánh đổi

Làm rõ Product Goal, Sprint Goal nếu dùng Scrum, mức dịch vụ cần duy trì, các tiêu chuẩn chất lượng và điều kiện bắt buộc về dữ liệu, bảo mật, vận hành. Mục tiêu giúp nhóm quyết định công việc nào tạo giá trị lớn nhất; DoD và các ràng buộc bắt buộc giúp tránh “giao cho kịp” bằng cách hạ chất lượng.

### Bước 2 — Thu thập dữ liệu nhu cầu và năng lực

Xem công việc các giai đoạn trước: bao nhiêu thời gian bị hút vào hỗ trợ, sửa lỗi, phối hợp và tích hợp; người nào sẽ vắng mặt; khi nào có phụ thuộc ngoài nhóm. Phân biệt công việc đã biết với rủi ro chưa biết.

### Bước 3 — Dành năng lực cho hoạt động cần thiết

Xác định phần năng lực cho công việc vận hành dự kiến, bảo trì đã biết và mức dự phòng phù hợp. **Kiểm thử, review, tích hợp cần để Done phải nằm trong ước lượng của công việc hoàn tất**, không để thành “việc dư”.

### Bước 4 — Chọn lát cắt nhỏ theo giá trị và khả năng hoàn tất

Chọn những hạng mục có lợi ích và mức rủi ro phù hợp, làm rõ acceptance criteria, phụ thuộc và quyền quyết định. Chia nhỏ theo hành vi người dùng có thể sử dụng, thay vì chỉ chia theo tầng kỹ thuật.

### Bước 5 — Theo dõi và điều chỉnh khi thực tế thay đổi

Quan sát WIP, sự cố, chất lượng và việc bị chặn. Khi phát sinh nhu cầu, làm rõ điều gì bị ảnh hưởng; thương lượng lại thứ tự/phạm vi hoặc cách tổ chức công việc. Thông báo sớm khi mục tiêu có rủi ro; không đợi đến ngày cuối mới công bố rằng không thể hoàn tất.

### Bước 6 — Nhìn lại và cải tiến khả năng dự báo

So sánh dự kiến với thực tế, nhận diện vì sao khác biệt, cập nhật giả định về năng lực, DoD, sự cố và phụ thuộc. Mục đích là **quyết định kế hoạch lần sau tốt hơn**, không tìm người để quy lỗi khi môi trường thay đổi.

## 12. Những sai lầm thường gặp

**1. Chỉ ước lượng thời gian lập trình.** Review, kiểm thử, tích hợp và các điều kiện Done bị bỏ sót. Hãy nhìn công việc từ làm rõ nhu cầu tới Increment hoàn chỉnh.

**2. Dồn kiểm thử vào cuối Sprint.** Khi lỗi xuất hiện muộn, nhóm phải làm lại gấp và dễ vi phạm DoD. Kiểm tra sớm, chia story nhỏ, tích hợp thường xuyên.

**3. Cho rằng bảo trì là việc “không có giá trị”.** Bảo mật, độ ổn định và khả năng thay đổi là điều kiện để sản phẩm tiếp tục phục vụ người dùng.

**4. Gộp mọi thứ vào buffer.** Công việc bảo trì đã biết, hỗ trợ thường kỳ và sự cố bất định cần cách quản lý khác nhau. Gộp hết vào “dự phòng” che khuất ưu tiên.

**5. Áp dụng tỷ lệ dự phòng cứng cho mọi đội.** Mỗi sản phẩm, môi trường vận hành và giai đoạn phát triển có mức biến động khác nhau. Dùng dữ liệu lịch sử và đánh giá rủi ro.

**6. Cộng hai lần cùng một công sức.** Ước lượng story đã gồm kiểm thử nhưng tiếp tục trừ kiểm thử thêm lần nữa sẽ làm số liệu không nhất quán. Xác định ranh giới chi phí và ghi rõ giả định.

**7. Coi mọi việc từ bên ngoài là khẩn cấp.** Khi tất cả đều được ưu tiên cao nhất, dòng công việc không còn ưu tiên thực chất. Dùng tiêu chí phân loại và quyền quyết định rõ.

**8. Vẫn giữ nguyên mọi phạm vi sau sự cố lớn.** Nếu năng lực đã bị dùng để xử lý sự cố, cần điều chỉnh kế hoạch hoặc thảo luận nguồn lực và thời hạn; không mặc định làm thêm giờ để bù.

**9. Giảm kiểm thử hoặc hạ Definition of Done để “đạt tiến độ”.** Cách này biến phần việc chưa đủ chất lượng thành tiến độ giả và đẩy rủi ro sang người dùng/đợt sau.

**10. Lập kế hoạch 100% năng lực và nghĩ như vậy là tối ưu.** Không còn chỗ xử lý công việc phát sinh, học hỏi và gỡ nghẽn; nhiều việc đang làm có thể khiến thời gian hoàn thành tăng.

**11. Tối ưu số lượng story thay vì kết quả người dùng.** Một Increment mang lại giá trị và hoạt động ổn định có thể quan trọng hơn nhiều hạng mục mã chưa tích hợp.

**12. Quên phản hồi sau phát hành.** Tính năng đã triển khai vẫn cần quan sát lỗi, khả năng sử dụng và tác động. Phản hồi thực tế cung cấp thông tin cho kế hoạch thích ứng tiếp theo.

## 13. Bài tập tình huống: Sprint bị sự cố chiếm mất năng lực

Một Scrum Team xây dựng hệ thống đăng ký khóa học có **5 người** trong Sprint gồm **10 ngày làm việc**. Nhóm dự kiến:

| Khoản | Số người-ngày |
| --- | ---: |
| Tổng theo lịch | 50 |
| Nghỉ phép đã biết | 5 |
| Hoạt động phối hợp cố định ngoài PBI | 6 |
| Hỗ trợ thường kỳ | 7 |
| Dự phòng việc phát sinh | 8 |
| **Năng lực cho backlog đã lên kế hoạch** | **24** |

Nhóm dự kiến sử dụng 24 người-ngày cho:

- **17 người-ngày**: Các user story cho phép đăng ký và quản lý khóa học; đã tính kiểm thử, review và tích hợp để đạt DoD.
- **5 người-ngày**: Nâng cấp thư viện bảo mật và sửa cảnh báo vận hành đã biết.
- **2 người-ngày**: Thử bản mẫu giao diện chọn khóa với người dùng.

Đến giữa Sprint, hệ thống có một sự cố nghiêm trọng cần **11 người-ngày**, thay cho 8 ngày dự phòng. Người có quyền xử lý môi trường tích hợp cũng phải tham gia sự cố.

### Câu hỏi

1. Tính tổng năng lực theo lịch và năng lực dành cho backlog; phép tính có nhất quán không?
2. Sự cố vượt dự phòng bao nhiêu người-ngày?
3. Nhóm nên làm gì với phạm vi Sprint để vẫn bảo vệ DoD và Sprint Goal?
4. Nếu người phụ trách tích hợp bị kéo sang xử lý sự cố, vì sao không thể chỉ lấy tổng người-ngày còn lại để khẳng định công việc sẽ hoàn thành?
5. Trong Sprint Retrospective, nên xem lại những dữ liệu và thỏa thuận nào để lập kế hoạch tốt hơn lần sau?

### Gợi ý lời giải

**Câu 1:** Tổng theo lịch là \(5 \times 10 = 50\) người-ngày. Năng lực dự kiến cho backlog là \(50 - 5 - 6 - 7 - 8 = 24\) người-ngày. Phân bổ \(17 + 5 + 2 = 24\) nhất quán, với giả định các khoản không bị đếm trùng.

**Câu 2:** Sự cố vượt dự phòng \(11 - 8 = 3\) người-ngày.

**Câu 3:** Nhóm cần xử lý sự cố theo cơ chế đã thống nhất, đánh giá tác động tới Sprint Goal và các hạng mục. Developers cùng Product Owner có thể làm rõ và thương lượng phạm vi trong Sprint phù hợp với Scrum; ưu tiên lát cắt giá trị quan trọng và công việc bảo mật bắt buộc, hoãn phần ít cấp thiết nếu cần. Thảo luận sớm với các bên liên quan về rủi ro, không tự rút ngắn kiểm thử bắt buộc.

**Câu 4:** Công việc có **phụ thuộc năng lực theo vai trò và thời điểm**. Ba người-ngày hao hụt ở đúng người có quyền tích hợp có thể chặn nhiều story, ngay cả khi người khác còn thời gian. Nhóm nên tìm phương án hỗ trợ hoặc đổi thứ tự công việc phù hợp thay vì giả định tất cả ngày công thay thế được nhau.

**Câu 5:** Xem lịch sử sự cố và thời gian khắc phục; cách phân loại mức khẩn; thời gian chờ môi trường, review và kiểm thử; WIP; tỷ lệ đạt DoD; mức làm thêm; mức phù hợp của dự phòng; và liệu có thể đào tạo chéo hoặc giảm phụ thuộc vào một cá nhân. Các thay đổi nên trở thành thử nghiệm cải tiến có người thúc đẩy và thời điểm đánh giá.

### Bài tập mở rộng

Giả sử giai đoạn sau không có sự cố lớn và chỉ dùng **2 trong 8 người-ngày dự phòng**. Nhóm có thể làm gì với năng lực còn lại? Hãy cân nhắc giữa:

- Kéo thêm một lát cắt giá trị nhỏ, đã được làm rõ và có khả năng hoàn tất đúng chất lượng.
- Cải thiện kiểm thử tự động hoặc pipeline tích hợp đang gây chờ đợi.
- Xử lý bảo trì phòng ngừa có rủi ro rõ.
- Duy trì khả năng ứng phó nếu vẫn còn thời gian trong giai đoạn và bất định chưa kết thúc.

Không có đáp án “phải lấp đầy 6 ngày còn lại”. Quyết định phù hợp phụ thuộc mục tiêu, mức rủi ro và khả năng tạo ra **kết quả hoàn tất**.

## 14. Danh sách kiểm tra trước khi chốt kế hoạch

Trước Sprint Planning hoặc kỳ bổ sung công việc tiếp theo, nhóm có thể tự hỏi:

1. **Mục tiêu:** Phần giá trị nào quan trọng nhất với người dùng và mục tiêu sản phẩm?
2. **Năng lực:** Ai thực sự sẵn sàng, có nghỉ phép, trực vận hành hoặc phụ thuộc kỹ năng nào?
3. **Công việc hoàn tất:** Ước lượng đã bao gồm review, kiểm thử, tích hợp, bảo mật và DoD chưa?
4. **Bảo trì:** Những vấn đề đã biết cần xử lý trong kỳ này là gì, rủi ro nếu hoãn?
5. **Việc phát sinh:** Tải hỗ trợ và sự cố có lịch sử ra sao, cần chính sách ứng cứu nào?
6. **Dự phòng:** Mức dự phòng có lý do và tránh đếm trùng với công việc đã lên kế hoạch không?
7. **Dòng công việc:** WIP, hàng chờ review/kiểm thử và việc bị chặn có thể ảnh hưởng kết quả như thế nào?
8. **Giới hạn:** Có yêu cầu bắt buộc nào về chất lượng, quyền truy cập, hợp đồng hoặc thời hạn không?
9. **Thích ứng:** Khi năng lực giảm hoặc ưu tiên đổi, ai cần tham gia quyết định thay đổi phạm vi?
10. **Phản hồi:** Sau khi giao phần tăng dần, nhóm đo giá trị và cải tiến cách làm bằng cách nào?

**Ghi nhớ:** **Kiểm thử và tích hợp là một phần của công việc để tạo Increment hoàn tất; bảo trì đã biết cần được ưu tiên và cấp năng lực rõ ràng; việc phát sinh cần mức dự phòng cùng chính sách xử lý; kế hoạch phải được điều chỉnh khi thực tế đổi khác.** Nhóm Agile hiệu quả không cố dùng hết mọi phút cho tính năng mới, mà duy trì khả năng giao giá trị đáng tin cậy, bảo vệ chất lượng, nhận phản hồi sớm và cải tiến liên tục.
