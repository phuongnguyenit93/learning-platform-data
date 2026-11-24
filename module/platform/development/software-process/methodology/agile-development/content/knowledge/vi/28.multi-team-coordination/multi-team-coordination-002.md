# Tổ chức nhóm theo khả năng tạo giá trị xuyên suốt

## 1. Khi nhiều nhóm cùng bận nhưng người dùng vẫn chờ

Một doanh nghiệp đang xây dựng nền tảng học trực tuyến. Để phát hành chức năng **đăng ký khóa học miễn phí và bắt đầu học ngay**, họ chia công việc theo ba nhóm chuyên môn:

- **Nhóm Giao diện:** Thiết kế màn hình, nút đăng ký và thông báo.
- **Nhóm Dịch vụ:** Xây API đăng ký, kiểm tra điều kiện nghiệp vụ.
- **Nhóm Dữ liệu:** Tạo bảng đăng ký, migration và truy vấn.

Từng nhóm báo cáo tiến độ khá tốt. Nhóm Giao diện hoàn tất màn hình, nhóm Dịch vụ đã có endpoint, nhóm Dữ liệu cũng tạo xong schema. Nhưng người học vẫn **không thể đăng ký rồi mở bài đầu tiên** vì:

1. API trả trạng thái khác với giả định của giao diện.
2. Tài khoản chưa được liên kết chính xác với dữ liệu đăng ký.
3. Kiểm thử tích hợp phải chờ cả ba nhóm.
4. Khi lỗi xuất hiện, không rõ nhóm nào có trách nhiệm theo tới kết quả cuối.
5. Một thay đổi nhỏ về thông báo lại phải đi qua nhiều backlog và nhiều lần ưu tiên.

Vấn đề không nhất thiết nằm ở chuyên môn hay nỗ lực cá nhân. **Cấu trúc phối hợp có thể khiến công việc phải chờ và bàn giao nhiều lần trước khi tạo giá trị thật.**

Tổ chức nhóm theo khả năng tạo giá trị xuyên suốt (*end-to-end value delivery*) nghĩa là thiết kế ranh giới và năng lực nhóm sao cho một nhóm, hoặc một tập nhóm có phối hợp tối thiểu và rõ ràng, có thể đưa một nhu cầu người dùng từ **ý tưởng → kiểm chứng → phát triển → tích hợp → kết quả có thể sử dụng → phản hồi**.

Trong chương **Phối hợp nhiều nhóm** của module **AGILE_DEVELOPMENT**, cách tư duy này liên hệ với các giá trị và nguyên tắc Agile: phản hồi sớm, giao Increment tăng dần, thiết kế thích ứng, phát huy cộng tác và cải tiến liên tục. Các thực hành **user story, Product Backlog, Scrum, Kanban, XP** sẽ giúp tổ chức và vận hành các nhóm sao cho công việc tới người dùng thật sự chảy.

**Thông điệp của bài:** *Không chỉ hỏi mỗi nhóm làm xong phần kỹ thuật của mình chưa; hãy hỏi người dùng đã nhận được kết quả nào và có bao nhiêu ranh giới tổ chức còn cản kết quả đó.*

## 2. Hiểu đúng “giá trị xuyên suốt” và “năng lực đa chức năng”

### 2.1. Giá trị là kết quả của một hành trình, không phải một tầng kỹ thuật

Đối với người học, những kết quả có thể có giá trị là:

- Tìm được khóa phù hợp.
- Đăng ký khóa miễn phí thành công và nhận xác nhận đáng tin cậy.
- Mở được bài đầu tiên bằng đúng tài khoản.
- Tiếp tục học trên thiết bị khác mà không mất tiến độ.
- Nhận biết và giải quyết được lỗi hoặc tình trạng chưa đồng bộ.

Người dùng hiếm khi cần riêng một API, một bảng database hay một thành phần giao diện. Những phần ấy là **phương tiện tạo ra hành vi có giá trị**.

### 2.2. Chuỗi giá trị (*value stream*) là gì?

Trong bài này, **dòng giá trị** là chuỗi các bước và quyết định cần thiết để biến một nhu cầu thành kết quả người dùng có thể trải nghiệm. Dòng này có thể gồm nghiên cứu nhu cầu, ưu tiên backlog, thiết kế, xây dựng, kiểm thử, tích hợp, phát hành, vận hành và thu nhận phản hồi.

Một dòng giá trị có thể kéo qua nhiều hệ thống và chuyên môn. **Ranh giới dòng giá trị không nhất thiết trùng ranh giới repository, microservice hay phòng ban**.

### 2.3. “Cross-functional” không có nghĩa ai cũng làm mọi việc

Một **nhóm đa chức năng** có tổng thể các kỹ năng và năng lực cần thiết để tạo Increment có giá trị theo trách nhiệm của nhóm. Không yêu cầu từng cá nhân đồng thời là chuyên gia giao diện, backend, dữ liệu, bảo mật, kiểm thử và vận hành.

Ví dụ một Scrum Team tạo luồng đăng ký có thể có những thành viên với chuyên môn sâu khác nhau, cùng làm rõ công việc, thiết kế giải pháp và đạt Definition of Done. Họ có thể được hỗ trợ bởi nhóm nền tảng hoặc chuyên gia bảo mật, nhưng **không biến mỗi chuyên môn thành một hàng chờ bàn giao mặc định**.

### 2.4. Năng lực tạo giá trị xuyên suốt là thuộc tính của hệ thống

| Điều cần có | Biểu hiện thực tế | Khi còn yếu |
| --- | --- | --- |
| **Mục tiêu người dùng rõ** | Nhóm biết kết quả cần tạo và kiểm chứng | Tối ưu số task thay vì giá trị |
| **Năng lực liên chức năng** | UI, API, test, dữ liệu và vận hành phối hợp từ đầu | Bàn giao tuần tự |
| **Quyền quyết định phù hợp** | Quyết định kỹ thuật gần nơi có thông tin | Mọi việc đều chờ phê duyệt mơ hồ |
| **Hợp đồng và ranh giới kỹ thuật rõ** | Thay đổi không phá dịch vụ khác bất ngờ | Tích hợp cuối kỳ mới phát hiện xung đột |
| **Chuẩn chất lượng chung** | Increment đạt Definition of Done | Nhiều phần “xong” nhưng chưa dùng được |
| **Quan sát outcome** | Nhìn thấy hành vi người dùng và lỗi | Giao hàng nhưng không biết kết quả |
| **Năng lực cải tiến** | Giảm lặp lại dependency, blocker và làm lại | Mỗi Sprint tái diễn cùng trở ngại |

**Nhóm tạo giá trị không đồng nghĩa được tự ý bỏ các điều kiện về an toàn, pháp lý hoặc quyền dữ liệu.** Quyền và trách nhiệm phải được thiết kế sao cho vừa có tốc độ thích ứng, vừa giữ kiểm soát cần thiết.

## 3. Vì sao cơ cấu theo thành phần thường làm tăng chờ đợi?

Một cách chia theo công nghệ có thể phù hợp với một số hệ thống, nhưng khi một chức năng người dùng phải đi qua nhiều nhóm, **số bước chuyển giao (handoff)** và **hàng chờ** có thể tăng.

### 3.1. Mô hình bàn giao tuần tự

~~~mermaid
flowchart LR
    A["Nhu cầu người học"] --> B["Nhóm UI<br/>Thiết kế và xây màn hình"]
    B --> C["Chờ nhóm API"]
    C --> D["Nhóm API<br/>Nghiệp vụ"]
    D --> E["Chờ nhóm dữ liệu"]
    E --> F["Nhóm dữ liệu<br/>Schema/transaction"]
    F --> G["Chờ kiểm thử tích hợp"]
    G --> H["Nhóm kiểm thử/triển khai"]
    H --> I["Người học dùng được"]
~~~

Sơ đồ chỉ mô tả **một hệ thống tổ chức điển hình có nhiều handoff**, không có nghĩa mọi nhóm chuyên môn đều luôn làm việc tuần tự hoặc thiếu năng lực.

### 3.2. Ví dụ tính thời gian một lát cắt

Giả sử một user story đăng ký khóa đi qua các bước **không chồng lắp**, với số ngày làm việc giả định:

| Bước | Thực hiện | Chờ/bàn giao |
| --- | ---: | ---: |
| Làm rõ hành vi và thiết kế UI | 2 | 1 |
| Xây và kiểm chứng API | 3 | 3 |
| Thay đổi dữ liệu và migration thử | 2 | 2 |
| Tích hợp, kiểm thử và sửa khác biệt | 3 | 2 |
| **Tổng** | **10** | **8** |

Nếu các khoảng được đo nối tiếp và cùng ranh giới, **Cycle Time minh họa là 18 ngày làm việc**. Tỷ lệ thời gian chờ trong trường hợp này:

\[
\frac{8}{18}\times100\%\approx44{,}4\%
\]

Đây là **tỷ trọng thời gian của một item**, không phải tỷ lệ nhân sự nhàn rỗi hay bằng chứng có thể tiết kiệm chính xác 44,4% ngân sách. Trong thực tế, hoạt động có thể song song, phải sửa lại hoặc chờ ở nhiều trạng thái chồng lắp.

Giảm thời gian gõ mã từ 10 xuống 9 ngày chỉ giúp tối đa một ngày trong mô hình này; **xử lý hàng chờ, vòng tích hợp và quyền ra quyết định** có thể tạo cơ hội lớn hơn. Cần đo thực tế trước khi kết luận nút nghẽn nào quan trọng nhất.

### 3.3. “Local optimization” làm kết quả toàn dòng kém hơn

Nếu nhóm UI được đánh giá bằng **số màn hình hoàn tất**, họ có thể đẩy nhiều giao diện mới sang hàng chờ API. Nhóm API tăng hiệu suất riêng bằng cách ưu tiên endpoint dễ, còn nhóm Dữ liệu gom migration vào một đợt. Mỗi nhóm đều trông bận rộn nhưng **luồng hoàn tất đến người dùng chậm**.

Nguyên tắc Lean hữu ích: **tối ưu toàn dòng giá trị thay vì tối ưu mức sử dụng từng bộ phận**. Phải xét thời gian người dùng chờ và chất lượng Increment, không chỉ số output địa phương.

## 4. Bắt đầu thiết kế tổ chức bằng bản đồ dòng giá trị

Đừng quyết định sơ đồ tổ chức chỉ từ danh sách kỹ năng hiện có. Trước hết hãy quan sát **người dùng cần gì, công việc đi qua đâu, các bước nào tạo giá trị và bước nào chờ**.

### 4.1. Bảy câu hỏi bản đồ hóa

1. **Ai là người nhận giá trị?** Người học, giảng viên, quản trị chương trình hay bộ phận vận hành?
2. **Kết quả cụ thể là gì?** Đăng ký xong, mở bài, nhận đánh giá, hoàn thành bài kiểm tra?
3. **Dòng công việc bắt đầu và kết thúc ở đâu?** Từ nhu cầu được chấp nhận vào backlog tới Increment Done hay tới người dùng sử dụng?
4. **Các bước thực tế là gì?** Nghiên cứu, thiết kế, mã, review, test, tích hợp, phê duyệt, phát hành?
5. **Những chỗ chờ nằm đâu?** Review, dữ liệu thử, CI, quyền API, thiết kế chung, quyết định sản phẩm?
6. **Ai có quyền quyết định ở mỗi điểm?** Có ranh giới thẩm quyền nào cần giữ?
7. **Kết quả được đo thế nào?** Người dùng có thành công và hệ thống có đủ an toàn?

### 4.2. Value Stream Map tối giản

| Giai đoạn | Chủ thể đang làm | Tín hiệu thường gặp | Điểm điều tra |
| --- | --- | --- | --- |
| Làm rõ nhu cầu | Product Owner, Developers, người dùng | User story chưa đủ ví dụ | Đã hiểu outcome và rủi ro? |
| Thiết kế lát cắt | Nhóm UI/API/data | Nhiều giao thức chưa thống nhất | Có thể thiết kế xuyên ranh giới sớm? |
| Phát triển | Developers | Nhiều nhánh dài | Có PR nhỏ và CI thường xuyên? |
| Review | Người có quyền review | PR tồn lâu | Có quyền dự phòng và giới hạn WIP? |
| Kiểm thử tích hợp | Developers/kiểm thử | Test flaky, môi trường chung | Có thể tự phục vụ test data và môi trường? |
| Đạt DoD | Scrum Team | “Code xong” bị nhầm với Done | Bằng chứng chất lượng đã đủ? |
| Phát hành và quan sát | Vận hành/nhóm sản phẩm | Chờ cấu hình, rollback khó | Có đường phát hành rõ và an toàn? |
| Phản hồi người dùng | Nhóm sản phẩm | Không biết người học đã mở bài | Có outcome metric và nghiên cứu? |

Đây là **bản đồ quan sát**, không phải quy trình bắt buộc cho mọi nhóm. Một nhóm có thể tích hợp, kiểm thử, triển khai song song; hãy vẽ theo cách công việc thật diễn ra.

### 4.3. Phân loại bước chờ để tránh chẩn đoán sai

- **Chờ năng lực:** Người review hoặc chuyên gia không đủ thời gian.
- **Chờ quyết định:** Chưa rõ ưu tiên, tiêu chí nghiệp vụ hoặc quyền phê duyệt.
- **Chờ kỹ thuật:** CI, dữ liệu test, môi trường, hợp đồng API.
- **Chờ phụ thuộc:** Nhóm khác phải giao một phần hoặc thay đổi hợp đồng.
- **Chờ an toàn bắt buộc:** Kiểm soát bảo mật, quyền dữ liệu hay phê duyệt pháp lý theo chính sách.

Không phải mọi chờ đợi đều là lãng phí cần xóa. **Một phê duyệt an toàn thực sự bắt buộc phải được đáp ứng**; cơ hội cải tiến có thể là chuẩn bị sớm, làm rõ yêu cầu và tự động hóa các bước được phép, không bỏ kiểm soát.

## 5. Phân biệt nhóm thành phần và nhóm theo dòng giá trị

### 5.1. Component team

**Component team** thường tập trung sở hữu một lớp hoặc một thành phần kỹ thuật cụ thể: frontend, backend, database hoặc một thư viện chung.

**Điểm mạnh có thể có:**

- Chuyên môn sâu về khu vực kỹ thuật khó.
- Quản trị và nâng cấp thành phần dùng chung nhất quán.
- Phù hợp khi hệ thống có công nghệ chuyên biệt, rủi ro cao hoặc cần kiểm soát tập trung.

**Rủi ro khi áp dụng máy móc:**

- Hầu hết user story cần qua nhiều backlog.
- Nhóm bàn giao “phần mình xong” trước khi người dùng có thể dùng.
- Thứ tự ưu tiên khác nhau giữa các nhóm.
- Chờ người có quyền tích hợp hoặc kiểm thử.
- Trách nhiệm với outcome và lỗi xuyên hệ thống bị mờ.

### 5.2. Nhóm theo dòng giá trị, tính năng hoặc miền sản phẩm

**Value-stream/feature-aligned team** được tổ chức để hoàn tất một lớp nhu cầu người dùng/khả năng sản phẩm với đủ kỹ năng hỗ trợ, thay vì chỉ sở hữu một tầng công nghệ.

Ví dụ:

- **Nhóm Tiếp cận và Đăng ký:** Tìm khóa, xem thông tin, đăng ký, xác nhận và quyền bắt đầu.
- **Nhóm Trải nghiệm học:** Mở bài, theo dõi tiến độ, tiếp tục học và tình trạng offline.
- **Nhóm Đánh giá học tập:** Nộp bài, kiểm tra kết quả và phản hồi cho người học.

Mỗi nhóm có thể có UI, API, dữ liệu, test và khả năng vận hành tương ứng **trong phạm vi hợp lý**. Các nhóm vẫn dùng những nền tảng và tiêu chuẩn chung; không phải nhóm nào cũng xây hạ tầng của riêng mình.

### 5.3. So sánh theo mục đích

| Tiêu chí | Nhóm theo thành phần | Nhóm theo giá trị xuyên suốt |
| --- | --- | --- |
| Đầu ra dễ được theo dõi | Thành phần, API, schema, giao diện | Hành vi người dùng và Increment |
| Phụ thuộc của một user story | Có thể nhiều nhóm | Nỗ lực giảm phụ thuộc thường kỳ |
| Năng lực được phát triển | Chuyên sâu một thành phần | Chuyên sâu theo miền + cộng tác nhiều kỹ năng |
| Điều dễ tối ưu sai | Mức bận và output riêng từng lớp | Tự chủ cục bộ nhưng tách khỏi tiêu chuẩn chung |
| Rủi ro chính | Handoff, hàng chờ và ưu tiên lệch | Trùng năng lực, ranh giới miền chưa rõ |
| Phù hợp nhất khi | Thành phần đặc thù, chuyên môn hoặc hạ tầng chung khó chia | Dòng giá trị đủ ổn định để giao end-to-end |

**Không có nghĩa component team luôn sai, feature team luôn đúng.** Mục tiêu là chọn cấu trúc làm giảm chi phí phối hợp và rủi ro cho những dòng giá trị quan trọng.

## 6. Những loại nhóm hỗ trợ khi sản phẩm lớn

Khi sản phẩm và tổ chức phát triển, một nhóm đa chức năng không thể tự vận hành mọi nền tảng, công nghệ chuyên sâu và chính sách tuân thủ. Có thể tham khảo các khái niệm trong **Team Topologies** để phân biệt mục đích hỗ trợ.

| Kiểu nhóm tham khảo | Mục đích chính | Ví dụ | Điều phải tránh |
| --- | --- | --- | --- |
| **Stream-aligned team** | Giao và cải tiến một dòng giá trị với phản hồi trực tiếp | Tiếp cận và Đăng ký | Biến nhóm thành tập hợp frontend/backend rời rạc bên trong |
| **Platform team** | Cung cấp năng lực chung tự phục vụ, giảm gánh nặng cho nhóm dòng giá trị | Môi trường CI, đăng nhập, quan sát vận hành, công cụ phát hành | Trở thành đội ticket trung gian phê duyệt mọi thao tác |
| **Enabling team** | Giúp các nhóm khác học năng lực khó, giảm khoảng trống kỹ thuật | Hỗ trợ test hợp đồng, performance, accessibility | Giữ nhóm phụ thuộc chuyên gia mãi mãi |
| **Complicated-subsystem team** | Sở hữu một phần chuyên môn phức tạp mà các nhóm khác không nên phải hiểu hết | Công cụ xử lý video chuyên sâu, thuật toán chấm phức tạp khi thực sự cần | Tách tùy tiện mọi backend thành “subsystem” mới |

**Đây là một mô hình thiết kế tổ chức có thể tham khảo, không phải những vai trò hoặc nhóm bắt buộc của Scrum Guide.** Cần kiểm tra tải nhận thức, ranh giới sản phẩm và mức phụ thuộc thực tế.

### 6.1. Platform team thành công khi giảm chờ, không tạo hàng chờ mới

Ví dụ nhóm Đăng ký thường mất ba ngày để xin môi trường tích hợp. Nhóm Platform có thể xây **môi trường test tự phục vụ** với dữ liệu giả, cấu hình phù hợp và hướng dẫn rõ. Khi đó nhóm sản phẩm không cần chờ ticket cho mỗi lần kiểm thử.

Nhưng nếu Platform biến việc chạy pipeline thành quy trình xin phép thủ công, nhóm sản phẩm có thể còn chậm hơn. **Giá trị của nền tảng phải được đánh giá qua hiệu quả của các nhóm dùng nó**, không chỉ số ticket Platform đóng.

### 6.2. Enabling team khác bộ phận làm hộ

Chuyên gia security hỗ trợ nhóm sản phẩm xây threat model, thêm kiểm tra quyền và hiểu cách giữ secret. Sau giai đoạn phối hợp, nhóm sản phẩm cần **tự thực hiện phần thường ngày trong năng lực được cho phép**, còn chuyên gia tập trung rủi ro khó.

Nếu mọi thay đổi nhỏ vẫn phải chờ chuyên gia “làm thay”, khả năng tự chủ chưa được hình thành. Ngược lại, các phê duyệt bảo mật/pháp lý bắt buộc vẫn phải ở đúng thẩm quyền; “trao quyền” không đồng nghĩa bỏ kiểm soát.

### 6.3. Nhóm chuyên môn sâu chỉ nên tạo ở nơi thực sự cần

Một hệ thống mã hóa video chuyên sâu, xử lý chống gian lận hoặc một mô hình tính toán phức tạp có thể cần nhóm chuyên gia riêng vì tải nhận thức quá lớn. Ranh giới dịch vụ/hợp đồng phải rõ, mức tương tác với các nhóm dòng giá trị được xác định và mục tiêu phục vụ toàn sản phẩm được minh bạch.

Không nên biến mỗi thư viện, microservice hay bảng dữ liệu thành một nhóm có backlog riêng.

## 7. Thiết kế ranh giới nhóm theo kết quả, miền và tải nhận thức

Tổ chức theo dòng giá trị không chỉ là đổi tên “Frontend Team” thành “Learner Journey Team”. Cần xem **quyết định, kỹ năng, kiến trúc và khả năng hoàn tất** có thật sự nằm gần nhau không.

### 7.1. Ba tiêu chí đầu tiên

**Giá trị rõ:** Nhóm có thể nói người dùng nào hưởng lợi, outcome mong muốn và phản hồi có thể đo.

**Ranh giới miền tương đối ổn định:** Những quy tắc liên quan nên có điểm sở hữu rõ. Ví dụ đăng ký khóa và quyền bắt đầu có quan hệ mật thiết, còn tính toán điểm thi chuyên sâu có thể là miền khác.

**Tải nhận thức hợp lý:** Một nhóm không thể đồng thời hiểu mọi lớp của sản phẩm lớn. Ranh giới phải cho phép nhóm nắm đủ kiến thức để ra quyết định nhanh và an toàn mà không quá tải.

### 7.2. Những câu hỏi kiểm tra ranh giới

1. Bao nhiêu PBI của nhóm có thể đạt DoD mà **không cần chờ một nhóm khác viết mã cho cùng lát cắt**?
2. Những thay đổi nào thường phải sửa đồng thời ở hai nhóm?
3. Câu hỏi nghiệp vụ nào liên tục bị chuyển qua lại?
4. Nhóm có tiếp cận được kết quả sử dụng và lỗi sản phẩm trong phạm vi mình chịu trách nhiệm?
5. Những năng lực nào nên được **chia sẻ bằng nền tảng tự phục vụ**?
6. Có thành phần kỹ thuật chuyên sâu nào cần nhóm chuyên gia riêng?
7. Các yêu cầu bảo mật, vận hành và dữ liệu có thể được đáp ứng trong cấu trúc mới?
8. Nhân sự có đủ hiểu biết và thời gian học cách làm mới hay chỉ thay sơ đồ nhân sự?

### 7.3. Ranh giới nhóm và kiến trúc tác động qua lại

Cấu trúc giao tiếp tổ chức có ảnh hưởng tới thiết kế hệ thống; đây là ý tưởng thường được thảo luận dưới tên **Conway's Law**. Không nên coi nó là phép dự đoán cứng hoặc cho rằng cứ đổi sơ đồ tổ chức là kiến trúc tự tốt lên.

Nếu hai nhóm liên tục phải cùng sửa một bảng dữ liệu và chung nhiều quy tắc, đó có thể là tín hiệu:

- Ranh giới nhóm chưa khớp với ranh giới miền nghiệp vụ.
- Ranh giới dịch vụ/API đang quá chặt.
- Cần một hợp đồng rõ hoặc tái thiết kế dữ liệu.
- Một nhóm nên sở hữu trọn luồng thay đổi, nhóm khác tiêu thụ qua giao diện ổn định.

**Cơ cấu nhóm và cấu trúc mã nên được cải tiến cùng nhau theo bằng chứng**, không cần tái kiến trúc lớn chỉ để làm đúng một mẫu tổ chức.

## 8. Tính tự chủ của nhóm có những giới hạn cần thiết

**Tự chủ** nghĩa là nhóm có khả năng ra quyết định trong phạm vi trách nhiệm để tạo giá trị, không phải mỗi nhóm được tự đặt mọi chuẩn riêng.

| Quyền tự chủ hữu ích | Tiêu chuẩn hoặc trách nhiệm cần phối hợp |
| --- | --- |
| Chọn cách chia lát cắt và thực hiện kỹ thuật | Product Goal, ưu tiên Product Backlog và giá trị sản phẩm |
| Thiết kế bên trong ranh giới sở hữu | Hợp đồng API/dữ liệu dùng chung, tương thích consumer |
| Tổ chức review, pair, test theo năng lực | Definition of Done và những chuẩn tổ chức áp dụng |
| Đo và cải tiến workflow | Cách biểu diễn dữ liệu đo nhất quán khi cần so sánh |
| Phát hành theo cơ chế được phê duyệt | Quyền production, security, privacy, release policy |
| Quyết định refactoring trong phạm vi | Các thay đổi kiến trúc làm ảnh hưởng nhiều nhóm |

Một nhóm độc lập quá mức có thể tự chọn API, cơ chế đăng nhập và tiêu chuẩn dữ liệu riêng, khiến việc tích hợp thành sản phẩm chung khó hơn. Một tổ chức tập trung quá mức lại khiến mọi thay đổi nhỏ phải chờ nhiều cấp phê duyệt.

Mục tiêu là **có quyền quyết định gần nơi có kiến thức, cùng các ranh giới an toàn rõ và hợp đồng phối hợp ổn định**.

### 8.1. Ownership khác độc quyền mã

Nhóm chịu trách nhiệm một khả năng sản phẩm nghĩa là họ theo dõi chất lượng, hành vi, kết quả và cải tiến của khả năng đó. **Không nhất thiết là chỉ thành viên nhóm mới được phép đọc hoặc đóng góp mã.**

Chính sách review, quyền truy cập, bảo mật và quy trình đóng góp cần rõ để tránh hai cực đoan:

- **Không ai chịu trách nhiệm:** Lỗi xuyên hệ thống bị đẩy vòng quanh.
- **Silo tuyệt đối:** Mọi thay đổi nhỏ đều phải chờ nhóm sở hữu, dù nhóm khác có đủ năng lực và quyền hỗ trợ.

### 8.2. “You build it, you run it” cần điều chỉnh đúng bối cảnh

Nhóm tạo thay đổi nên hiểu khả năng vận hành và quan sát kết quả. Nhưng điều đó không có nghĩa mọi Developer được cấp quyền production hoặc trực hệ thống 24/7. Tổ chức có thể có SRE, vận hành hoặc cơ chế bảo mật chuyên trách; điều quan trọng là **đường phối hợp và trách nhiệm với chất lượng không bị đứt gãy**.

## 9. Scrum khi nhiều nhóm cùng làm một sản phẩm

Scrum Guide định nghĩa Scrum Team nhỏ, tự quản và đa chức năng. Khi **nhiều Scrum Teams cùng làm trên một sản phẩm**, chúng **cùng chia sẻ Product Goal, Product Backlog và Product Owner**, và cần **cùng xác định, tuân thủ một Definition of Done** của sản phẩm.

Đây là điểm then chốt: cấu trúc nhiều nhóm không được làm biến sản phẩm thành một tập backlog kỹ thuật rời rạc, mỗi nhóm “Done theo chuẩn của mình”.

### 9.1. Điều gì chung và điều gì thuộc từng Scrum Team?

| Yếu tố Scrum | Khi nhiều Scrum Teams cùng sản phẩm |
| --- | --- |
| **Product Goal** | Chung, thể hiện hướng giá trị dài hạn của sản phẩm |
| **Product Backlog** | Chung và minh bạch, được Product Owner quản lý hiệu quả |
| **Product Owner** | Một Product Owner chịu trách nhiệm cho sản phẩm |
| **Definition of Done** | Chung cho sản phẩm, mọi Scrum Team tuân thủ |
| **Sprint Goal** | Mỗi Scrum Team có Sprint Goal của mình trong Sprint |
| **Sprint Backlog** | Mỗi Scrum Team có kế hoạch do Developers của nhóm tạo/điều chỉnh |
| **Increment** | Công việc của các nhóm phải tích hợp thành Increment đáp ứng DoD của sản phẩm |
| **Scrum events** | Được tổ chức phục vụ mục đích Scrum; có thể thêm cách đồng bộ khi hữu ích |

Không nên ép tất cả nhóm phải có **một Sprint Goal chung duy nhất** vì như vậy dễ lẫn cam kết của Sprint Backlog từng Scrum Team với Product Goal của sản phẩm. Các Sprint Goals có thể **căn chỉnh về một hướng sản phẩm** nhưng vẫn thuộc từng Scrum Team.

### 9.2. Một sản phẩm không biến thành nhiều Product Backlogs vì có nhiều nhóm

Trong ví dụ nền tảng học, nhóm Đăng ký và nhóm Trải nghiệm học có thể cùng đóng góp một sản phẩm theo một Product Goal. Nếu mỗi nhóm duy trì một Product Backlog không liên hệ và một người “Product Owner của tầng kỹ thuật” riêng, nhóm có thể tạo sự ưu tiên xung đột.

Có thể dùng các **góc nhìn lọc** backlog theo vùng sản phẩm để hỗ trợ thực hiện, nhưng không nên nhầm chúng với các Product Backlogs độc lập cho **cùng một sản phẩm** trong cách áp dụng Scrum.

Nếu tổ chức có **nhiều sản phẩm thực sự khác nhau**, mỗi sản phẩm có ranh giới giá trị và trách nhiệm riêng. Không nên áp công thức “mọi hệ thống đều một PO” mà không xác định sản phẩm.

### 9.3. Tích hợp là trách nhiệm chung, không phải việc làm ở “Sprint tích hợp”

Nếu nhóm A đã hoàn tất UI, nhóm B hoàn tất API nhưng hai phần chưa chạy cùng nhau, **không có Increment người dùng sử dụng được cho luồng ấy**. Công việc chưa đạt DoD không trở thành Done vì mỗi nhóm đã hoàn thành task địa phương.

Nhiều Scrum Teams cùng sản phẩm cần **tích hợp thay đổi thường xuyên**, có tiêu chuẩn chung và kiểm chứng ảnh hưởng xuyên ranh giới. Không nên tạo một “Sprint tích hợp” cố định ở cuối chuỗi như giải pháp mặc định cho việc nhiều nhóm không ghép mã sớm.

### 9.4. Scrum of Scrums là lựa chọn phối hợp, không phải sự kiện bắt buộc

Một số tổ chức dùng **Scrum of Scrums** hoặc đồng bộ đại diện các nhóm để xem phụ thuộc, integration và trở ngại. Đây là **cách phối hợp có thể hữu ích**, không phải Scrum event bắt buộc.

Nếu cuộc họp chỉ tạo thêm báo cáo tầng lớp mà không làm giảm phụ thuộc, tăng khả năng ra quyết định hay khôi phục build chung, nên điều chỉnh nó.

## 10. Product Backlog theo giá trị, không theo phòng ban

Một Product Backlog hữu ích thể hiện **nhu cầu, giá trị, rủi ro và thứ tự ưu tiên** hơn là tập các yêu cầu chuyển giao giữa nhóm công nghệ.

### 10.1. Cách viết backlog gây chia cắt

~~~text
Frontend: xây màn hình đăng ký.
Backend: tạo API đăng ký.
Database: tạo bảng enrollment.
QA: kiểm thử sau khi các nhóm khác hoàn thành.
Operations: triển khai khi được yêu cầu.
~~~

Những việc trên có thể là **technical tasks**, nhưng nếu mỗi task được coi là PBI độc lập để báo Done, Product Backlog dễ mất liên hệ với kết quả người học.

### 10.2. Cách thể hiện nhu cầu xuyên suốt

> “Là người học đã đăng nhập, tôi muốn đăng ký khóa miễn phí và thấy xác nhận đáng tin, để có thể bắt đầu học mà không phải đoán trạng thái.”

Các nhiệm vụ UI, API, database, test và triển khai có thể thuộc kế hoạch thực hiện PBI đó. **PBI là đơn vị hướng tới kết quả có giá trị; technical tasks giúp Developers tổ chức How.**

### 10.3. Một tập hạng mục theo lát cắt

| PBI | Kết quả người dùng | Phụ thuộc cần giảm | Ví dụ kiểm chứng |
| --- | --- | --- | --- |
| A — Đăng ký khóa miễn phí | Lưu đăng ký hợp lệ và xác nhận đúng | UI/API/DB được phối hợp trong một lát cắt | Không tạo đăng ký Active trùng; lỗi không báo thành công giả |
| B — Xem khóa đã đăng ký | Người học thấy danh sách đúng | Hợp đồng với dữ liệu đăng ký | Truy cập đúng tài khoản |
| C — Mở bài đầu | Người học bắt đầu bài sau đăng ký | Quyền truy cập nội dung và tiến độ | Link bài hợp lệ, phân quyền đúng |
| D — Tiếp tục học | Giữ và khôi phục tiến độ | Đồng bộ nhiều thiết bị, dữ liệu | Không ghi đè âm thầm cập nhật mới |

Việc chia thực tế cần xét **DoD, dependency, năng lực và rủi ro**. Một lát cắt nhỏ vẫn phải đáp ứng những điều kiện chất lượng áp dụng; không tách “bảo mật để làm sau” nếu đó là ranh giới bắt buộc cho chức năng hiện tại.

## 11. Chia nhóm theo outcome nhưng đừng bỏ qua kiến trúc

Thay cơ cấu tổ chức có thể cải thiện phối hợp, nhưng nếu thiết kế phần mềm vẫn tạo phụ thuộc chặt thì các nhóm tiếp tục chờ nhau.

### 11.1. Dấu hiệu ranh giới kiến trúc đang cản giao hàng

- Một thay đổi ở luồng đăng ký luôn yêu cầu sửa nhiều dịch vụ do nhóm khác sở hữu.
- Hợp đồng API không được phiên bản hóa hoặc kiểm chứng với consumer.
- Nhiều nhóm ghi trực tiếp vào cùng dữ liệu nhưng không có quy tắc quyền sở hữu.
- Không thể tạo môi trường tích hợp độc lập hoặc thử dữ liệu an toàn.
- Cấu hình chung khiến một nhóm triển khai làm hỏng luồng nhóm khác.
- Release phải gom tất cả thay đổi vào một đợt lớn dù phần người dùng đã sẵn sàng.

### 11.2. Thiết kế cải tiến theo từng bước

1. Xác định **ranh giới nghiệp vụ**: đăng ký, quyền học, nội dung, đánh giá.
2. Làm rõ **trách nhiệm dữ liệu** và hợp đồng giữa ranh giới.
3. Bổ sung **contract/integration tests** ở nơi nhiều nhóm phụ thuộc.
4. Khuyến khích **PR nhỏ và CI thường xuyên**, tránh nhánh dài.
5. Chọn refactoring hoặc migration theo rủi ro, có kế hoạch tương thích và phục hồi.
6. Tạo dịch vụ tự phục vụ cho những phụ thuộc vận hành chung.
7. Quan sát kết quả và điều chỉnh ranh giới nhóm hoặc kiến trúc khi có bằng chứng.

**Không có yêu cầu rằng tổ chức Agile phải dùng microservices.** Một modular monolith với ranh giới rõ có thể dễ thay đổi và tích hợp hơn nhiều microservice phụ thuộc chặt.

### 11.3. API contract là điểm phối hợp, không phải giấy phép bỏ giao tiếp

Hợp đồng API rõ có thể giảm nhu cầu đồng bộ liên tục. Tuy nhiên, khi thay đổi hành vi hoặc ý nghĩa dữ liệu, chỉ kiểm tra kiểu trường chưa đủ. Nhóm cần trao đổi về **semantics**: khi đăng ký lại sau hủy thì trạng thái nào, lỗi timeout có chắc đã ghi dữ liệu chưa, quyền truy cập bị từ chối thể hiện ra sao.

### 11.4. Dữ liệu chung là ranh giới nhạy cảm

Một bảng dữ liệu do nhiều nhóm ghi trực tiếp dễ gây thay đổi lan truyền. Có thể thiết kế quyền sở hữu rõ hơn hoặc API/service boundary phù hợp. Nhưng tái cấu trúc dữ liệu phải xét giao dịch, dữ liệu lịch sử, tính nhất quán và rollback. **Không tự cắt một database thành nhiều database chỉ vì muốn mỗi nhóm có “database riêng”**.

## 12. CI, kiểm thử và Definition of Done tạo nền tảng cho nhiều nhóm

Khi nhiều nhóm cùng sản phẩm, **tích hợp liên tục** là điều kiện quan trọng để giảm việc “các phần đều xanh nhưng ghép lại thất bại”.

### 12.1. Vòng tích hợp cho một lát cắt xuyên nhóm

~~~mermaid
flowchart TD
    A["PBI theo giá trị, acceptance criteria rõ"] --> B["Các chuyên môn thiết kế ranh giới sớm"]
    B --> C["Thay đổi nhỏ và kiểm thử tại nguồn"]
    C --> D["CI: build, unit, contract, integration phù hợp"]
    D --> E{"Có tương thích và đạt chuẩn?"}
    E -->|"Chưa"| F["Sửa hoặc hoàn nguyên sớm"]
    F --> C
    E -->|"Có"| G["Tích hợp vào Increment sản phẩm"]
    G --> H{"Đáp ứng Definition of Done chung?"}
    H -->|"Chưa"| I["Làm rõ phần chất lượng còn thiếu"]
    I --> C
    H -->|"Có"| J["Có thể sử dụng và nhận phản hồi theo chính sách"]
~~~

Một pipeline xanh **không thay toàn bộ DoD**: kiểm thử bảo mật, trải nghiệm, dữ liệu hoặc yêu cầu vận hành có thể cần bằng chứng ngoài CI. Nhưng CI đáng tin giúp phát hiện sớm nhiều xung đột.

### 12.2. Rủi ro của “mỗi nhóm có DoD riêng”

Giả sử:

- Nhóm UI gọi Done khi màn hình hiển thị theo mock.
- Nhóm API gọi Done khi unit tests xanh.
- Nhóm Dữ liệu gọi Done khi migration chạy trên máy phát triển.

Không điều kiện nào riêng lẻ chứng minh **người học có thể đăng ký thành công, không tạo dữ liệu trùng và được phân quyền đúng**. Nếu là nhiều Scrum Teams cùng sản phẩm, cần **DoD chung** và công việc đạt chuẩn của Increment sản phẩm.

### 12.3. Kiểm thử cần tập trung vào ranh giới gây rủi ro

| Ranh giới | Kiểm tra nên cân nhắc | Điều không thể suy ra |
| --- | --- | --- |
| UI–API | Contract tests, kiểm thử luồng thành công/thất bại | UI mock xanh nghĩa API thật đúng |
| API–DB | Integration/concurrency tests, migration thử | Unit test nghĩa DB không có race |
| Đăng ký–quyền học | Kiểm thử phân quyền, hành vi sau đăng ký | API trả 200 nghĩa người học có quyền đúng |
| Client–mạng | Timeout/retry/idempotency phù hợp | Chặn double-click nghĩa không có request trùng |
| CI–môi trường | Test data cô lập, kết quả đáng tin | Rerun xanh nghĩa không còn flaky |
| Runtime–vận hành | Metrics/logs/alert theo rủi ro và quyền dữ liệu | Deploy thành công nghĩa người dùng đạt outcome |

**Không bắt buộc mỗi thay đổi chạy cùng một bộ kiểm tra**, nhưng các yêu cầu bắt buộc và chuẩn chất lượng không được giảm chỉ vì muốn giao nhanh.

## 13. Quản lý phụ thuộc giữa nhóm như một phần của dòng công việc

Khi nhiều nhóm cùng sản phẩm, **không thể loại bỏ mọi phụ thuộc**. Cần phân biệt:

- **Phụ thuộc nội tại của sản phẩm:** Tính năng mở bài cần quyền đăng ký hợp lệ.
- **Phụ thuộc kỹ thuật do cấu trúc:** UI phải đợi một nhóm khác sửa hợp đồng API.
- **Phụ thuộc nguồn lực:** Mọi migration đều chờ một chuyên gia duy nhất.
- **Phụ thuộc quyết định:** Chưa rõ Product Owner muốn quy tắc nào.
- **Phụ thuộc kiểm soát:** Phê duyệt dữ liệu hoặc bảo mật bắt buộc.

Mỗi loại cần cách xử lý khác nhau. Một số có thể **giảm bằng thiết kế**, một số cần **phối hợp sớm**, và những kiểm soát bắt buộc cần đáp ứng đúng quy trình.

### 13.1. Ma trận phụ thuộc gọn

| Nhu cầu | Nhóm/khả năng phụ thuộc | Tại sao cần | Bước giảm chờ |
| --- | --- | --- | --- |
| Đăng ký khóa miễn phí | Xác thực dùng chung | Xác nhận tài khoản | Hợp đồng rõ, môi trường test tự phục vụ |
| Xác nhận đăng ký | Dịch vụ enrollment | Trạng thái ghi dữ liệu | Contract test và kịch bản lỗi chung |
| Mở bài đầu | Quyền truy cập nội dung | Kiểm tra quyền học | Định nghĩa sớm bất biến và dữ liệu thử |
| Gửi email | Dịch vụ thông báo | Kênh liên lạc thêm | Quyết định email có là phần cốt lõi không |
| Phát hành | Nền tảng/Operations | Pipeline, quyền production | Release policy, tự động hóa bước được phép |

Nên ghi **người phối hợp, thời điểm cần và điều kiện kết thúc phụ thuộc**, không chỉ vẽ đường nối giữa hai nhóm.

### 13.2. Dependency Board không chỉ để báo cáo

~~~text
Phụ thuộc: CONTRACT-17 — trạng thái đăng ký sau timeout
Luồng người dùng: Đăng ký -> Xác nhận -> Mở bài
Người/nhóm cần quyết định: Product Owner + đại diện kỹ thuật liên quan
Nhóm cần kết quả: Tiếp cận & Đăng ký
Giới hạn thời gian: Trước khi hoàn thiện contract test của lát cắt A
Rủi ro nếu chậm: UI có thể báo thành công giả
Bằng chứng cần có: Ví dụ hành vi + contract test + phản hồi API
Phương án tạm an toàn: Hiển thị trạng thái chưa xác nhận,
                    chưa gọi feature Done nếu chưa đạt DoD
Tình trạng: Đang làm rõ; thời điểm xem lại được thống nhất
~~~

**Đừng biến dependency board thành một tầng phê duyệt mới.** Nó phải giúp tìm người ra quyết định, hành động tiếp theo và giảm hàng chờ.

### 13.3. Giảm phụ thuộc theo thứ tự chi phí hợp lý

1. **Làm rõ sớm:** Thống nhất contract và quy tắc nghiệp vụ trước khi code nhiều.
2. **Chia lát cắt:** Có thể hoàn tất phần giá trị ít phụ thuộc trước?
3. **Tăng tự phục vụ:** Test data, CI, môi trường, tài liệu/hướng dẫn phù hợp.
4. **Chia sẻ kỹ năng:** Pair, trao đổi chuyên môn, reviewer dự phòng.
5. **Cải thiện giao diện kỹ thuật:** API ổn định, contract tests, versioning.
6. **Đổi ownership hoặc ranh giới:** Khi một loại phụ thuộc lặp lại và chi phí đủ lớn.
7. **Tái tổ chức đội:** Chỉ sau khi hiểu ảnh hưởng tới con người, sản phẩm và tổ chức.

Không nên bắt đầu bằng sơ đồ tổ chức mới khi **một contract test hoặc chính sách review phù hợp** đã có thể xử lý phần lớn trở ngại.

## 14. Phối hợp giữa nhóm: đủ đồng bộ, ít bàn giao

Một tổ chức nhiều nhóm thường cần cả **cơ chế làm rõ chung** lẫn **quyền tự quyết trong nhóm**.

### 14.1. Những hoạt động phối hợp có thể hữu ích

| Hoạt động | Mục đích | Khi nên dùng |
| --- | --- | --- |
| **Refinement nhiều chuyên môn** | Làm rõ một lát cắt xuyên nhóm, rủi ro và dependencies | Trước khi bắt đầu PBI có tích hợp |
| **Technical design hẹp** | Chốt hợp đồng API, dữ liệu, tương thích | Khi ranh giới có nguy cơ phá nhau |
| **Đồng bộ tích hợp ngắn** | Xem CI đỏ, PR chờ và blockers liên nhóm | Khi dòng chung đang nghẽn |
| **Review Increment có tích hợp** | Nhận phản hồi từ stakeholder về kết quả thật | Khi có phần sản phẩm đạt DoD |
| **Platform feedback** | Biết self-service đang tạo hay loại hàng chờ | Khi nhiều nhóm dùng dịch vụ chung |
| **Retrospective liên nhóm có chọn lọc** | Xử lý nguyên nhân lặp ở ranh giới nhóm | Khi một vấn đề không nhóm nào tự giải được |

Không nhất thiết tất cả nhóm tham gia mọi cuộc họp. **Đúng người, đúng rủi ro và có quyết định/hành động** thường tốt hơn nhiều lịch họp cố định.

### 14.2. Dấu hiệu cuộc họp đang tạo thêm hàng chờ

- Đại diện về báo cáo nhưng không có quyền quyết định.
- Câu hỏi lặp lại vì không có contract hoặc nguồn thông tin chung.
- Mỗi nhóm chỉ đọc status; không ai gỡ dependency.
- Cuộc họp xuất hiện sau khi thay đổi đã viết xong và không còn dễ điều chỉnh.
- Các vấn đề phải đợi họp tuần kế tiếp dù đang chặn CI hoặc gây lỗi dữ liệu.

**Cải tiến:** Giao tiếp trực tiếp giữa những người chịu trách nhiệm cho quyết định cụ thể; dùng tài liệu/hợp đồng/ticket minh bạch; chỉ họp khi cần tháo gỡ điều không giải quyết được bất đồng bộ.

## 15. Trường hợp xuyên suốt: từ ba nhóm chức năng tới dòng giá trị học tập

### 15.1. Hiện trạng giả định

Doanh nghiệp có 18 người làm sản phẩm:

- 6 người tập trung giao diện và ứng dụng.
- 7 người tập trung dịch vụ và tích hợp API.
- 5 người tập trung dữ liệu, kiểm thử tích hợp và hạ tầng.

**Con số chỉ là giả định để làm bài học**, không phải tỷ lệ nhân sự đề nghị hay mô hình nhân sự chuẩn của Scrum.

Trong một đợt phát hành:

| Luồng người dùng | Số nhóm phải sửa mã | Trở ngại đáng chú ý |
| --- | ---: | --- |
| Tìm và đăng ký khóa | 3 | Hợp đồng UI/API lệch; migration chờ |
| Mở bài đầu | 3 | Quyền học phụ thuộc dữ liệu đăng ký |
| Xem tiến độ học | 3 | Client/backend không thống nhất phiên bản |
| Báo cáo quản trị | 2 | Truy vấn cần phê duyệt dữ liệu |

Tổ chức nhận thấy các hành trình người học phải đi qua nhiều nhóm và deadline của từng nhóm khác nhau.

### 15.2. Đề xuất thử mô hình theo khả năng sản phẩm

Thay vì ngay lập tức thay toàn bộ tổ chức, có thể **thử một lát cắt xuyên suốt** trước. Mô hình đích tham khảo:

~~~mermaid
flowchart TD
    U["Người học và Product Goal"] --> T1["Nhóm Tiếp cận và Đăng ký<br/>Tìm khóa → đăng ký → xác nhận"]
    U --> T2["Nhóm Trải nghiệm học<br/>Mở bài → học → tiếp tục"]
    U --> T3["Nhóm Đánh giá và kết quả<br/>Kiểm tra → phản hồi"]
    P["Nền tảng chung<br/>CI, xác thực, quan sát, môi trường"] --> T1
    P --> T2
    P --> T3
    E["Chuyên gia hỗ trợ có mục tiêu<br/>Bảo mật, dữ liệu, accessibility"] -.-> T1
    E -.-> T2
    E -.-> T3
    T1 <-->|"Hợp đồng và dữ liệu rõ"| T2
    T2 <-->|"Hợp đồng nghiệp vụ rõ"| T3
~~~

Sơ đồ là **phương án giả định cần thử và điều chỉnh**, không phải khuyến nghị luôn phải chia thành đúng ba nhóm. Nếu 18 người không đủ duy trì ba nhóm cross-functional ổn định, cần chọn cấu trúc nhỏ hơn hoặc lộ trình phát triển năng lực phù hợp.

### 15.3. Dòng giá trị đầu tiên được thử

Chọn:

> “Người học đã đăng nhập đăng ký khóa miễn phí, thấy xác nhận chính xác và mở bài đầu tiên theo quyền truy cập hợp lệ.”

Thử giao một **PBI/lát cắt có giá trị** với nhóm gồm các kỹ năng cần thiết, thay vì gửi ba “ticket bàn giao” cho UI, API và dữ liệu.

**Hành vi quan trọng:**

~~~gherkin
Tính năng: Đăng ký khóa và bắt đầu học

  Tình huống: Đăng ký hợp lệ và mở bài đầu
    Cho trước người học đã đăng nhập
    Và khóa "Java nhập môn" đang cho phép đăng ký miễn phí
    Khi người học gửi yêu cầu đăng ký khóa
    Thì hệ thống lưu một đăng ký hợp lệ
    Và giao diện hiển thị đúng trạng thái đã đăng ký
    Và người học có thể mở bài đầu theo quyền hợp lệ

  Tình huống: Hai yêu cầu đăng ký gần đồng thời
    Cho trước người học đã đăng nhập
    Và người học chưa có đăng ký đang có hiệu lực cho khóa
    Khi hai yêu cầu đăng ký cùng khóa đến gần đồng thời
    Thì hệ thống không tạo hai đăng ký đang có hiệu lực trùng nhau
    Và phản hồi mỗi yêu cầu tuân theo hợp đồng đã thống nhất

  Tình huống: Không xác nhận được kết quả lưu
    Cho trước dịch vụ chưa thể xác nhận đăng ký đã được ghi
    Khi người học yêu cầu đăng ký khóa
    Thì giao diện không báo chắc chắn rằng đăng ký thành công
    Và có cách kiểm tra trạng thái hoặc thử lại phù hợp

  Tình huống: Truy cập dữ liệu của tài khoản khác
    Cho trước người học A đã đăng nhập
    Và dữ liệu khóa đã đăng ký thuộc tài khoản B
    Khi A cố xem hoặc sử dụng dữ liệu đăng ký của B
    Thì hệ thống từ chối theo chính sách phân quyền
    Và không tiết lộ thông tin riêng của B
~~~

Các bước Gherkin là **mô tả hành vi minh họa**. Cần mã kiểm thử, dữ liệu, môi trường và kiểm tra phân quyền, tính đồng thời thực tế để biến chúng thành bằng chứng đạt DoD.

### 15.4. Quy tắc nào thuộc nhóm nào?

Nhóm Đăng ký có thể chịu trách nhiệm quy tắc enrollment và xác nhận, nhóm Trải nghiệm học có thể sở hữu cách mở nội dung và tiến độ. **Quyền học** là ranh giới hai nhóm cần làm rõ sớm: hợp đồng nào cho biết người học được mở bài, cách xử lý khi đăng ký bị hủy hoặc dữ liệu chậm đồng bộ?

Không nên để cả hai nhóm viết riêng một quy tắc quyền học rồi tự cho rằng sẽ thống nhất. Cần **một nguồn trách nhiệm và hợp đồng tiêu thụ rõ** theo kiến trúc/bối cảnh đã chọn.

### 15.5. Vai trò của nền tảng và kiểm soát chuyên môn

Nhóm nền tảng có thể cung cấp CI, môi trường thử tự phục vụ và xác thực dùng chung; chuyên gia bảo mật hỗ trợ các trường hợp nhạy cảm. Nhóm tạo luồng người dùng **vẫn phải tích hợp, kiểm chứng và sở hữu chất lượng của phần mình**.

Đặc biệt, nếu có dữ liệu cá nhân hoặc quyền học, không được tự ý bỏ phê duyệt bắt buộc để “làm nhóm end-to-end hơn”.

## 16. Chuyển đổi có trách nhiệm: thử một dòng giá trị trước khi đổi cả tổ chức

Tái tổ chức là một thay đổi lớn đối với con người, kiến thức miền, hệ thống và các mối quan hệ. **Không nên đổi tên hàng loạt team, chuyển repository và đổi sơ đồ quản lý cùng lúc** rồi kỳ vọng phụ thuộc biến mất.

Một lộ trình thử nghiệm có thể đi theo sáu giai đoạn:

### 16.1. Giai đoạn 1 — Lấy đường cơ sở

Trong những tuần đầu, quan sát một số PBI xuyên nhóm:

- **Cycle Time:** Từ khi bắt đầu đến khi đạt Done theo cùng ranh giới.
- **Work Item Age:** Các item chưa Done đang già đi ở đâu?
- **WIP:** Có bao nhiêu việc cùng mở?
- **Blocked Time:** Chờ review, dữ liệu, môi trường và nhóm khác bao lâu?
- **Số và loại handoff:** Chuyển trách nhiệm vì kỹ năng, quyền hay thiết kế?
- **Defect sau tích hợp/phát hành:** Có lỗi hợp đồng, phân quyền hoặc dữ liệu không?
- **Outcome người dùng:** Đăng ký có thành công và người học có mở bài đầu không?

Chỉ đếm số handoff chưa đủ: một handoff có thể cần thiết để kiểm soát an toàn, trong khi một thay đổi hợp đồng kéo dài nhiều ngày mới đáng ưu tiên giải quyết.

### 16.2. Giai đoạn 2 — Chọn một lát cắt giá trị

Chọn luồng có giá trị rõ, đủ nhỏ để thử và có những trở ngại thực tế cần học. Ví dụ đăng ký khóa miễn phí và mở bài đầu. Không bắt đầu từ một dự án kiến trúc nội bộ không có người dùng hay quyết định sản phẩm rõ ràng, trừ khi rủi ro kỹ thuật chính là vấn đề cần giải quyết.

### 16.3. Giai đoạn 3 — Gom đủ năng lực trong nhóm thử

Chọn những người cần thiết cho UI, API, dữ liệu, kiểm thử và hiểu biết vận hành để cùng hoàn tất lát cắt. Có thể **pairing, trao đổi chuyên môn, hỗ trợ theo thời gian ngắn** khi chưa thể tạo nhóm ổn định ngay.

Đừng biến thử nghiệm thành “đội dự án tạm mượn người” kéo dài mà mọi thành viên vẫn bị đánh giá và ưu tiên theo phòng ban cũ. Nếu nhân sự chỉ được cấp 10% thời gian và luôn bị gọi về, hàng chờ vẫn còn.

### 16.4. Giai đoạn 4 — Làm rõ quyền và hợp đồng

Trước khi bắt đầu, cần rõ:

- Ai làm rõ Product Backlog và thứ tự ưu tiên?
- Ai có quyền thay đổi API/dữ liệu và ai review?
- Những tiêu chí DoD chung áp dụng?
- Khi có incident, ai ứng cứu và ai phối hợp?
- Dịch vụ platform nào tự phục vụ, dịch vụ nào bắt buộc cần phê duyệt?
- Quy tắc nào được chia sẻ giữa nhóm Đăng ký và nhóm Trải nghiệm học?

Những câu trả lời này có thể ghi trong **working agreement/Team API** ngắn. Đó là công cụ tự chọn, không phải một artifact bắt buộc của Scrum.

### 16.5. Giai đoạn 5 — Giao một vài lát cắt và đo

Thực hiện PR nhỏ, tích hợp thường xuyên, xem blocker sớm, thu phản hồi của người học và đối chiếu DoD. Không cần chờ tái tổ chức hoàn tất mới đưa một Increment đủ chất lượng vào sử dụng theo chính sách.

### 16.6. Giai đoạn 6 — Quyết định mở rộng, điều chỉnh hoặc dừng

Sau một vài chu kỳ phù hợp:

- **Giữ/mở rộng** nếu nhóm giảm chờ và đạt chất lượng/outcome tốt mà không tạo thêm rủi ro.
- **Điều chỉnh** nếu thiếu kỹ năng hoặc ranh giới product khiến phụ thuộc chưa giảm.
- **Dừng hoặc đổi cách thử** nếu chi phí chuyển đổi quá lớn, tác dụng phụ xấu hoặc giả định ban đầu không đúng.

Không nên xem việc dừng một mô hình tổ chức chưa hiệu quả là “Agile thất bại”. **Học từ thử nghiệm và thay đổi quyết định theo bằng chứng chính là tính thích ứng**.

## 17. Working agreement và Team API giảm chi phí phối hợp

Khi tổ chức có nhiều nhóm, một **Team API** hoặc thỏa thuận cộng tác ngắn có thể giúp người khác biết nhóm phục vụ luồng nào, cung cấp gì và tương tác thế nào. Đây là **kỹ thuật quản lý tự chọn**.

### 17.1. Mẫu Team API cho nhóm Đăng ký

~~~text
Nhóm: Tiếp cận và Đăng ký

Người dùng/luồng giá trị:
  Người học tìm khóa -> đăng ký -> xác nhận trạng thái.

Kết quả đang theo đuổi:
  Người học có thể đăng ký hợp lệ, không thấy thành công giả,
  và biết cách bắt đầu bài đầu tiên.

Ranh giới chịu trách nhiệm:
  Quy tắc enrollment, trạng thái đăng ký, hợp đồng API liên quan;
  phối hợp với nhóm Trải nghiệm học về quyền mở nội dung.

Những gì nhóm cung cấp cho nhóm khác:
  Hợp đồng đăng ký, trạng thái theo quyền phù hợp;
  tài liệu ví dụ nghiệp vụ và contract tests.

Phụ thuộc nền tảng:
  Xác thực, CI, môi trường test, quan sát và phát hành chung.

Chất lượng:
  Tuân thủ DoD của sản phẩm và chuẩn tổ chức áp dụng.

Cách yêu cầu hỗ trợ:
  Nêu câu hỏi/đầu ra cần, mức khẩn, người liên quan;
  trao đổi trực tiếp khi quyết định xuyên ranh giới.

Chính sách thay đổi hợp đồng:
  Đánh giá consumer, kiểm thử tương thích;
  thống nhất migration khi có dữ liệu hoặc API thay đổi.

Ứng cứu và escalation:
  Theo quy trình incident, quyền vận hành và người chịu trách nhiệm.

Điểm xem lại:
  Khi thay đổi ranh giới sản phẩm hoặc phát sinh dependency lặp lại.
~~~

### 17.2. Team API không được biến thành hàng rào

Nếu nhóm sản phẩm phải tạo ticket chờ ba ngày chỉ để hỏi nghĩa một trạng thái API, bản thỏa thuận có thể đang tạo thêm bureaucracy. Team API nên làm **liên hệ dễ hơn và giới hạn kỳ vọng rõ hơn**, không thay thế cộng tác trực tiếp khi cần.

### 17.3. Thống nhất chính sách “hỗ trợ hay bàn giao?”

| Tình huống | Cách tương tác nên cân nhắc |
| --- | --- |
| Một lần làm rõ hợp đồng API nhỏ | Trao đổi trực tiếp với người liên quan, cập nhật contract test |
| Thiếu kỹ năng test đồng thời | Pair/enablement có thời hạn và chuyển giao kiến thức |
| Nền tảng cung cấp môi trường | Self-service có tài liệu và hỗ trợ khi lỗi |
| Vấn đề bảo mật nghiêm trọng | Phối hợp chuyên gia và quy trình có thẩm quyền |
| Thay đổi schema dùng chung nhiều nhóm | Thiết kế tương thích, migration và kiểm thử phối hợp |
| Một thay đổi phải chờ đi chờ lại cùng nhóm | Phân tích ranh giới sở hữu và quyết định tổ chức/kỹ thuật |

## 18. Quản lý năng lực và kỹ năng trong nhóm đa chức năng

Một nhóm hướng giá trị cần đủ năng lực, nhưng không thể biến mọi người thành chuyên gia mọi thứ trong một Sprint.

### 18.1. Lập bản đồ năng lực thay vì chỉ đếm chức danh

| Năng lực | Có người thực hiện ổn định? | Có người hỗ trợ/học tiếp? | Rủi ro |
| --- | --- | --- | --- |
| Trải nghiệm và accessibility | Có | Cần tăng kỹ năng kiểm thử tự động | Người mới gặp rào cản sử dụng |
| API và quy tắc đăng ký | Có | Có người học qua pairing | Phụ thuộc một người với logic khó |
| Tính nhất quán dữ liệu | Có nhưng phân tán | Chuyên gia DB hỗ trợ theo rủi ro | Migration và concurrency test chờ |
| Kiểm thử tích hợp | Chưa đủ ổn định | Cần test fixtures và CI | Bug lộ muộn |
| Quan sát vận hành | Có công cụ chung | Cần hiểu tín hiệu sản phẩm | Không biết kết quả sau deploy |
| Bảo mật/quyền dữ liệu | Có chính sách tổ chức | Chuyên gia hỗ trợ và phê duyệt | Rủi ro truy cập trái phép |

Đây là bảng **đánh giá giả định** để thảo luận, không phải chấm điểm cá nhân. Không nên lưu thông tin năng lực nhạy cảm ngoài phạm vi được phép hoặc dùng ma trận để công khai xếp hạng con người.

### 18.2. Phát triển kỹ năng hình chữ T

**T-shaped skills** thường được hiểu là một người có chuyên môn sâu ở một vùng và đủ hiểu biết rộng để phối hợp với các lĩnh vực lân cận.

Ví dụ Developer backend có thể hiểu cách chạy integration test và đọc lỗi giao diện, nhưng không cần thay thế chuyên gia thiết kế trải nghiệm trong mọi tình huống.

Cách phát triển năng lực:

1. Pair ở những thay đổi xuyên ranh giới.
2. Tham gia review và thiết kế API cùng nhau.
3. Ghi tài liệu ngắn về bất biến dữ liệu quan trọng.
4. Luân phiên xử lý công việc phù hợp dưới sự hỗ trợ.
5. Dùng enabling team trong thời gian giới hạn.
6. Đầu tư công cụ self-service để giảm lệ thuộc chuyên môn không cần thiết.

### 18.3. Tránh tối ưu mức sử dụng 100% của mọi chuyên gia

Nếu một chuyên gia data luôn có 100% lịch đầy, mọi thay đổi cần dữ liệu sẽ phải chờ. Nhóm có thể cần **năng lực dự phòng cho review, sự cố và hỗ trợ**.

Điều này không có nghĩa cố ý để người khác nhàn rỗi; mục tiêu là **dòng giá trị có khả năng phản hồi**, không chỉ tối đa hóa thời gian bận của từng cá nhân.

### 18.4. Nhóm ổn định thường thuận lợi cho học hỏi lâu dài

Luân chuyển nhân sự liên tục qua các dự án có thể khiến tri thức sản phẩm, quan hệ cộng tác và khả năng làm việc chung không tích lũy được. Nhóm tương đối ổn định có thể cải thiện việc dự báo, hiểu người dùng và chất lượng. Tuy nhiên, không nên giữ cấu trúc bất biến khi sản phẩm đã thay đổi hướng lớn.

**Ưu tiên ổn định đủ để học, linh hoạt đủ để thích ứng** thay vì xem một trong hai là mục tiêu tuyệt đối.

## 19. Phụ thuộc nào cần loại bỏ, phụ thuộc nào cần quản lý?

Không phải mọi dạng chia sẻ đều xấu. Một nhóm tự xây lại xác thực, pipeline và observability sẽ tạo trùng lặp và rủi ro lớn.

### 19.1. Bốn lựa chọn ứng xử

| Phụ thuộc | Cách xử lý có thể hợp lý | Bằng chứng để đánh giá |
| --- | --- | --- |
| **Có thể loại bỏ bằng ranh giới nhóm** | Đưa kỹ năng và trách nhiệm gần cùng dòng giá trị | Handoff và blocked time giảm |
| **Có thể loại bỏ bằng nền tảng tự phục vụ** | Xây khả năng dùng chung qua API/tool rõ | Ít yêu cầu hỗ trợ thủ công hơn |
| **Cần phối hợp tạm thời** | Pair/collaboration để học hoặc chuyển đổi | Sau một thời gian nhóm có thể tự xử lý phần thường ngày |
| **Bắt buộc vì rủi ro/quy định** | Làm sớm, chuẩn hóa đầu vào và dùng quyền đúng | Tuân thủ mà không tạo chờ đợi không cần thiết |

### 19.2. Đừng dùng “không phụ thuộc nhóm khác” làm KPI tuyệt đối

Một nhóm dòng giá trị tốt vẫn phụ thuộc nền tảng xác thực, mạng, dữ liệu hoặc bên cung cấp dịch vụ ngoài. Mục tiêu là **giảm những tương tác chờ đợi gây cản trở việc giao giá trị**, đồng thời quản trị đúng các phụ thuộc cần thiết.

### 19.3. Đặt câu hỏi về chi phí phối hợp

Với mỗi dependency lặp lại:

- Nó xảy ra bao nhiêu lần một tháng?
- Mỗi lần gây chờ bao lâu và chặn bao nhiêu item?
- Nếu loại bỏ cần thay kiến trúc hoặc quyền sở hữu bao nhiêu?
- Rủi ro an toàn hoặc dữ liệu khi phân tán trách nhiệm là gì?
- Có giải pháp trung gian rẻ hơn, ví dụ contract test hay training?
- Khi nào chi phí tổ chức thay đổi sẽ được bù bởi giá trị tăng?

Không nên bịa **ROI chắc chắn** từ vài số liệu rời rạc. Có thể lập giả thuyết, thử nhỏ rồi đo trước/sau.

## 20. Đo hiệu quả tổ chức theo giá trị xuyên suốt

Nếu nhóm chỉ được thưởng theo **số PBI mỗi nhóm Done**, họ có thể chia việc thành nhiều phần nhỏ để tăng số. Nếu được thưởng theo **số deploy**, họ có thể deploy những thay đổi không có giá trị. Chỉ số phải hướng tới kết quả sản phẩm, dòng công việc và chất lượng.

### 20.1. Nhóm chỉ số theo câu hỏi

| Câu hỏi | Chỉ số/tín hiệu nên cân nhắc | Guardrail |
| --- | --- | --- |
| Người học có nhận giá trị sớm hơn? | Lead time từ nhu cầu được chọn tới Increment Done hoặc sử dụng theo ranh giới rõ | Chất lượng, giá trị thật |
| Công việc có bớt chờ? | Blocked time, Work Item Age, Cycle Time theo loại PBI | Không đổi nhãn để loại WIP |
| Phụ thuộc giữa nhóm đã giảm? | Số lần chờ nhóm khác, thời gian chờ, tỷ lệ PBI cần handoff | Không bỏ kiểm soát bắt buộc |
| Khả năng hoàn tất có ổn định? | Throughput, phân bố Cycle Time, WIP | DoD được giữ nhất quán |
| Tích hợp có đáng tin? | CI lead time, contract test failures, integration defects | Không bỏ test bắt buộc |
| Người dùng có bắt đầu học? | Activation 7 ngày theo cohort phù hợp | Lỗi mở bài, dữ liệu, quyền truy cập |
| Có tạo rủi ro vận hành? | Incident, thời gian phát hiện/khôi phục, lỗi dữ liệu | Không giảm nghĩa vụ an toàn |
| Nhóm có năng lực bền vững? | Nút nghẽn chuyên gia, phản hồi định tính, mức gián đoạn | Không biến metric thành giám sát cá nhân |

### 20.2. Ví dụ so sánh một thử nghiệm theo dòng giá trị

Giả sử nhóm chọn **10 PBI tương đồng trước** và **10 PBI tương đồng sau** khi thử cách phối hợp, với cách tính ngày làm việc và DoD giống nhau.

| Chỉ số minh họa | Trước | Sau | Giới hạn diễn giải |
| --- | ---: | ---: | --- |
| Trung vị Cycle Time | 12 ngày | 8 ngày | Cần kiểm tra kích thước/loại item và WIP còn dở |
| Trung vị thời gian chờ nhóm khác | 5 ngày | 2 ngày | Kiểm tra trạng thái blocked được ghi nhất quán |
| Số nhóm phải cùng sửa mã cho một PBI điển hình | 3 | 1–2 | Số nhóm không tự biểu thị độ phức tạp |
| PBI đã Done trong mẫu | 10 | 10 | Không chứng minh throughput tăng nếu kỳ quan sát khác |
| Lỗi tích hợp được phát hiện muộn | 4 | 1 | Mẫu nhỏ; cần kiểm tra mức độ nghiêm trọng |
| Activation người học sau đăng ký | Chưa đo | Chưa đo | Không thể kết luận đã tăng giá trị người dùng |

**Các số chỉ là giả định phục vụ bài học**, không phải kết quả đo trong hệ thống thực. Dù Cycle Time giảm 4 ngày và thời gian chờ giảm 3 ngày, chưa thể tuyên bố việc đổi mô hình nhóm là **nguyên nhân duy nhất**. Đồng thời, chưa có outcome người dùng thì chưa khẳng định giá trị sản phẩm tăng.

### 20.3. Từ đo tốc độ tới học hỏi sản phẩm

Giả sử sau thay đổi, người học đăng ký dễ hơn nhưng không mở bài đầu. Nhóm có thể đã tối ưu luồng phát triển mà **giải quyết sai vấn đề người dùng**. Product Owner và Developers cần xem activation, phản hồi và lỗi mở bài để điều chỉnh Product Backlog.

Đo end-to-end nghĩa là nhìn **cả kết quả giao phần mềm lẫn kết quả sử dụng**, không nhầm một trong hai với toàn bộ giá trị.

### 20.4. Cẩn trọng khi dùng flow metrics

Work Item Age và Cycle Time cần định nghĩa **điểm bắt đầu, Done, loại item, đơn vị thời gian và trạng thái Blocked**. Nếu trước/sau tổ chức lại làm thay đổi workflow, có thể không so sánh trực tiếp.

**SLE** là kỳ vọng thời gian hoàn tất theo cách định nghĩa, không phải SLA hợp đồng hoặc lời hứa mọi item xong đúng hạn. **Little's Law** nối các đại lượng trung bình trong điều kiện phù hợp, không dự báo chắc chắn một item cụ thể hoặc phần trăm hoàn thành.

## 21. Theo dõi kết quả sản phẩm để kiểm tra ranh giới nhóm

Tổ chức theo dòng giá trị nên giúp nhóm nhận phản hồi về phần họ tạo ra.

### 21.1. Ví dụ hành trình và tín hiệu

~~~text
Xem danh mục khóa
  -> Xem chi tiết
  -> Đăng ký hợp lệ
  -> Mở bài đầu
  -> Tiếp tục học
  -> Hoàn thành mục tiêu học
~~~

| Giai đoạn | Câu hỏi outcome | Tín hiệu có thể dùng |
| --- | --- | --- |
| Tìm khóa | Người học có tìm đúng khóa phù hợp? | Task success/usability test |
| Đăng ký | Có hoàn tất đăng ký hợp lệ, không báo sai? | Conversion và lỗi đăng ký |
| Mở bài | Người học đã bắt đầu học thực sự? | Activation trong khoảng đã định nghĩa |
| Tiếp tục học | Trải nghiệm có ổn định qua nhiều thiết bị? | Lỗi khôi phục tiến độ, phản hồi |
| Hoàn thành mục tiêu | Người học có đạt kết quả mong muốn? | Retention/learning outcome theo bối cảnh |

**Một nhóm có thể góp phần vào nhiều outcome và một outcome có thể chịu ảnh hưởng từ nhiều nhóm.** Không nên biến attribution thành trò chơi phân chia điểm công.

### 21.2. Tránh chia chỉ số khiến trải nghiệm bị cắt đoạn

Nếu nhóm Đăng ký chỉ theo conversion và nhóm Trải nghiệm học chỉ theo số lượt mở bài, khoảng giữa hai bước có thể bị bỏ quên: người học đăng ký xong nhưng không biết mở bài ở đâu.

Giải pháp có thể là **cùng nhìn một hành trình** và thống nhất hợp đồng giữa nhóm, thay vì ép một metric chung để xếp hạng. Product Goal và nghiên cứu người dùng giúp giữ hướng.

## 22. Quy trình phối hợp khi một user story thực sự cần nhiều nhóm

Dù tổ chức đã theo giá trị, vẫn có PBI trải qua hai hoặc ba nhóm. Ví dụ thay đổi quy tắc **đăng ký lại sau khi hủy** có thể ảnh hưởng dịch vụ enrollment, quyền mở bài và thông báo.

Một quy trình phối hợp gọn:

~~~mermaid
flowchart TD
    A["PBI và kết quả người dùng"] --> B["Làm rõ ví dụ nghiệp vụ chung"]
    B --> C["Nhận diện ranh giới, quyền và rủi ro"]
    C --> D["Thống nhất hợp đồng nhỏ/đường tích hợp"]
    D --> E["Các thay đổi tương thích được tích hợp sớm"]
    E --> F{"Kiểm thử ranh giới và DoD đạt?"}
    F -->|"Chưa"| G["Cùng điều tra, sửa phần tương tác"]
    G --> E
    F -->|"Có"| H["Increment có thể dùng"]
    H --> I["Quan sát outcome và cải tiến"]
~~~

### 22.1. Bước 1 — Cùng hiểu hành vi

Tổ chức trao đổi ngắn với người hiểu nghiệp vụ, Developers ở các ranh giới cần thiết và kiểm thử. Dùng ví dụ cụ thể:

- Người học hủy rồi đăng ký lại: quyền mở bài phải phản ánh trạng thái nào?
- Hai yêu cầu gần đồng thời: dữ liệu có tạo đăng ký trùng?
- Dịch vụ chậm xác nhận: UI có báo thành công giả không?
- Một tài khoản có đọc dữ liệu của tài khoản khác không?

Đây là lúc **giảm bất định trước khi mỗi nhóm xây theo giả định riêng**.

### 22.2. Bước 2 — Chọn một đường tích hợp có thể kiểm tra

Có thể xác định contract API, phiên bản trạng thái, test data và môi trường chung. Các nhóm làm thay đổi nhỏ theo thiết kế tương thích, không đợi mọi phần xong rồi mới thử.

### 22.3. Bước 3 — Một nơi minh bạch trạng thái end-to-end

Dù có subtask theo nhóm, vẫn nên nhìn trạng thái **PBI/lát cắt giá trị**: đang làm, blocked, kiểm chứng, Done. Đừng cộng ba task Done thành một Increment nếu luồng chưa hoạt động.

### 22.4. Bước 4 — Giải quyết phụ thuộc ngay khi phát hiện

Nếu contract test thất bại, người liên quan nên cùng xem thay vì tạo ticket rồi chờ cuộc họp hai tuần tới. Nếu liên quan dữ liệu nhạy cảm hoặc quyết định ngoài quyền, cần escalation đúng thẩm quyền.

### 22.5. Bước 5 — Bài học quay lại cấu trúc nhóm

Nếu nhiều PBI liên tiếp cần cùng hai nhóm sửa quy tắc quyền học, cần hỏi **ranh giới trách nhiệm có hợp lý không**. Một vài cuộc đồng bộ có thể giải quyết tạm, nhưng nguyên nhân cấu trúc nên được xem xét.

## 23. Chia sẻ nền tảng và kỹ thuật mà không làm tăng coupling

Nhiều nhóm thường cần tái sử dụng những năng lực chung như xác thực, telemetry, CI, môi trường và dịch vụ gửi thông báo.

### 23.1. “Dùng chung” có nhiều hình thức

| Hình thức | Khi hữu ích | Rủi ro |
| --- | --- | --- |
| **Thư viện chung** | Logic kỹ thuật ổn định và dễ version | Nâng version đồng loạt, coupling |
| **Dịch vụ chung/API** | Chức năng được nhiều luồng dùng và cần ownership rõ | Mạng, SLA, team phụ thuộc |
| **Nền tảng tự phục vụ** | Pipeline, môi trường test, secrets policy, observability | Đầu tư ban đầu và vận hành nền tảng |
| **Chuẩn/hướng dẫn dùng chung** | Hợp đồng, DoD, security, data governance | Quy định quá chi tiết gây khó đổi |
| **Cộng đồng thực hành (community of practice)** | Chia sẻ kỹ năng test, UX, bảo mật, kiến trúc | Họp nhiều nhưng ít hành động |

### 23.2. Tránh “shared everything”

Nếu mọi nhóm viết trực tiếp vào cùng một module và database mà không có ranh giới, việc đổi một quy tắc có thể cần kiểm tra cả sản phẩm. Phân tách đúng mức giúp giảm ảnh hưởng lan truyền.

Nhưng “tách hết thành service” cũng có thể làm giao dịch và tương thích phức tạp. **Ưu tiên ranh giới phù hợp nghiệp vụ và khả năng kiểm chứng**, không chạy theo số lượng microservice.

### 23.3. Dịch vụ nền tảng nên có trải nghiệm người dùng nội bộ

Một Platform Team có thể theo dõi:

- Nhóm sản phẩm có tự tạo môi trường thử được không?
- Từ yêu cầu hợp lệ tới môi trường sẵn mất bao lâu?
- Tỷ lệ thao tác tự phục vụ và lỗi của công cụ?
- Thời gian phản hồi hỗ trợ ở những trường hợp cần người?
- Các nhóm có tin tưởng và muốn dùng nền tảng không?
- Có giảm thời gian từ PBI bắt đầu tới DoD mà không giảm chất lượng?

Không nên chỉ đo **số endpoint nền tảng được viết** hoặc **số ticket nội bộ đóng**, vì mục tiêu là **giảm gánh nặng và chờ đợi của nhóm tạo giá trị**.

## 24. Tổ chức bảo mật, chất lượng và vận hành trong dòng giá trị

“End-to-end” không có nghĩa một nhóm được tùy ý cấp quyền, bỏ review bảo mật hoặc triển khai production ngoài chính sách.

### 24.1. Shift-left đúng nghĩa

Các yêu cầu chất lượng và an toàn nên được đưa vào quá trình làm rõ PBI và thiết kế:

- Quyền truy cập dữ liệu và tài nguyên người học.
- Xác thực, phân quyền và bảo vệ secret.
- Tính nhất quán dữ liệu, idempotency và migration.
- Bằng chứng kiểm thử tích hợp và hợp đồng.
- Accessibility và hành vi lỗi trên giao diện.
- Quan sát vận hành, phản ứng khi có sự cố.
- Những nghĩa vụ hợp đồng/pháp lý khi áp dụng.

Điều này giảm việc “cuối Sprint mới biết không được phát hành”. **Không chuyển hết trách nhiệm chuyên môn lên một Developer không được đào tạo**, mà thiết kế cơ chế hỗ trợ/đánh giá phù hợp.

### 24.2. Chuyên gia hỗ trợ và quyền phê duyệt

| Hoạt động | Nhóm dòng giá trị có thể tự làm? | Khi cần hỗ trợ/ủy quyền |
| --- | --- | --- |
| Kiểm thử quy tắc nghiệp vụ | Có, với năng lực phù hợp | Khi rủi ro đặc thù vượt chuyên môn |
| Chạy CI và môi trường test được cấp phép | Nên tự phục vụ khi có thể | Platform hỗ trợ hạ tầng lỗi |
| Review thay đổi dịch vụ | Theo quyền và chính sách | Chuyên gia khi có ảnh hưởng phức tạp |
| Thay đổi dữ liệu production | Không tự suy đoán quyền | DBA/operations và người có thẩm quyền |
| Đánh giá quyền dữ liệu pháp lý | Không tự kết luận bằng code | Chuyên gia privacy/legal khi cần |
| Khôi phục incident | Theo runbook và quyền được cấp | Incident commander/operations khi bắt buộc |

### 24.3. “Chất lượng chung” cần giữ nghĩa của DoD

Với nhiều Scrum Teams cùng sản phẩm, tất cả phải dùng **DoD chung**. Khi một luồng đăng ký chưa đạt kiểm thử phân quyền hoặc còn lỗi dữ liệu, không được gọi “Done phần nhóm A” rồi tính nó như Increment sản phẩm.

Các hoạt động kỹ thuật có thể hoàn tất ở mức task, nhưng **trạng thái sản phẩm** phải trung thực.

### 24.4. Vận hành tạo phản hồi, không chỉ là bước cuối

Nhóm sản phẩm nên biết sau khi phát hành:

- Tỷ lệ đăng ký thất bại thực và nguyên nhân.
- Người học có mở bài được không?
- Dữ liệu có bị trùng hoặc mất tính nhất quán?
- Khi có sự cố, thời gian phát hiện và khôi phục?
- Những phản hồi nào cần đổi Product Backlog?

**Một pipeline deploy thành công không chứng minh người dùng nhận giá trị.** Observability và nghiên cứu người dùng bổ sung nhau.

## 25. Phản ví dụ: chia nhóm “theo tính năng” nhưng vẫn giữ silo

Tổ chức đổi tên:

- Frontend Team → “Learner Experience Team”.
- Backend Team → “Core Learning Team”.
- Database Team → “Learning Data Team”.

Nhưng mỗi nhóm vẫn sở hữu đúng tầng kỹ thuật cũ; mọi user story đăng ký vẫn đi qua cả ba nhóm. Mỗi nhóm có backlog và ưu tiên riêng, giao nhau ở cuối Sprint.

**Tên mới không đổi flow.** Một cách kiểm tra đơn giản:

> “Nếu Product Owner chọn PBI đăng ký khóa miễn phí ngay hôm nay, nhóm nào có khả năng đưa nó tới DoD mà không cần xếp hàng chờ nhóm khác thực hiện phần cốt lõi?”

Nếu câu trả lời vẫn là “không nhóm nào”, cần xem cơ cấu năng lực, quyền quyết định, ranh giới kiến trúc và policy, chứ không chỉ sửa sơ đồ.

### 25.1. Khi tất cả nhóm đều “end-to-end” trên giấy

Có tổ chức tuyên bố mọi nhóm đều đầy đủ kỹ năng nhưng thực tế:

- Chỉ một chuyên gia biết migration dữ liệu.
- Chỉ một reviewer có quyền merge.
- Chỉ một tester có môi trường cần thiết.
- Chỉ một người chịu trách nhiệm phối hợp với Product Owner.

Khi những người này vắng, mọi nhóm dừng. Cần **đầu tư học hỏi, tự phục vụ và quyền hạn phù hợp**, không chỉ tuyên bố cross-functional.

### 25.2. Khi tự chủ làm mất tiêu chuẩn sản phẩm

Mỗi nhóm xây hệ thống log, trạng thái API và cơ chế đăng nhập riêng. Người học nhận trải nghiệm rời rạc và security phải rà soát nhiều cách. Trong trường hợp ấy, một nền tảng/chuẩn chung có thể **tăng** khả năng thích ứng, miễn không biến thành điểm chặn mọi thay đổi.

## 26. Các hiểu lầm thường gặp khi phối hợp nhiều nhóm

**1. “Mọi nhóm theo thành phần đều sai.”** Có thành phần đặc thù cần chuyên môn sâu; câu hỏi là chi phí phụ thuộc và giá trị toàn dòng.

**2. “Chỉ cần đổi tên nhóm thành feature team.”** Quyền, kỹ năng, backlog và kiến trúc không đổi thì handoff vẫn tồn tại.

**3. “Cross-functional nghĩa là mỗi người biết tất cả.”** Cần đủ năng lực ở cấp nhóm và mạng hỗ trợ, không đòi cá nhân đa năng tuyệt đối.

**4. “End-to-end nghĩa là không cần bảo mật hoặc vận hành chuyên trách.”** Chuyên gia và quyền phê duyệt vẫn cần ở rủi ro thích hợp.

**5. “Cứ chia thành càng nhiều microservice càng dễ lập nhiều nhóm.”** Ranh giới kỹ thuật sai có thể làm tích hợp khó hơn.

**6. “Một repository phải tương ứng đúng một nhóm.”** Repo là lựa chọn kỹ thuật; ranh giới giá trị và ownership cần xem riêng.

**7. “Một nhóm phải tự xây mọi năng lực chung để gọi là độc lập.”** Nền tảng tự phục vụ và dịch vụ chung ổn định thường giúp giảm trùng lặp.

**8. “Platform team đóng nhiều ticket nghĩa là thành công.”** Cần xem nó giảm chờ và gánh nặng cho nhóm sản phẩm hay chưa.

**9. “Enabling team làm hộ mọi việc khó vĩnh viễn.”** Mục tiêu là phát triển năng lực của nhóm khác; hỗ trợ có điểm kết thúc.

**10. “Mỗi tầng công nghệ là một complicated-subsystem team.”** Chỉ tách khi có chuyên môn phức tạp thực sự và chi phí nhận thức rõ.

**11. “Tự chủ nghĩa mỗi nhóm tự đặt DoD và tiêu chuẩn bảo mật.”** Nhiều Scrum Teams cùng sản phẩm cần DoD chung và tuân chuẩn tổ chức.

**12. “Mỗi nhóm cùng sản phẩm có Product Owner riêng.”** Trong Scrum, các Scrum Teams cùng sản phẩm chia sẻ một Product Owner và một Product Backlog.

**13. “Mọi Scrum Teams phải có cùng một Sprint Goal.”** Mỗi Scrum Team có Sprint Goal; cần căn chỉnh với Product Goal và tích hợp sản phẩm.

**14. “Scrum bắt buộc Scrum of Scrums.”** Đây là hình thức đồng bộ tự chọn, không phải Scrum event bắt buộc.

**15. “Đến cuối Sprint mới tích hợp là bình thường khi nhiều nhóm.”** Tích hợp muộn làm tăng rủi ro; cần kiểm chứng trạng thái sản phẩm thường xuyên.

**16. “Frontend/API/DB mỗi phần Done tức user story Done.”** Nếu luồng chưa đạt DoD, không được tính là Increment hoàn tất.

**17. “Hợp đồng API có kiểu dữ liệu đúng là đủ.”** Ý nghĩa nghiệp vụ, xử lý lỗi, quyền và trạng thái cần thống nhất.

**18. “Tách database cho mỗi nhóm luôn tốt.”** Migration, giao dịch và dữ liệu lịch sử có thể làm điều này rủi ro, tốn kém.

**19. “Không được có bất kỳ dependency nào.”** Phụ thuộc bắt buộc và dịch vụ nền tảng có ích; mục tiêu là giảm chờ/làm lại không cần thiết.

**20. “Mọi quyết định phải đưa lên cuộc họp liên nhóm.”** Nên phân quyền rõ, chỉ phối hợp khi ranh giới hoặc rủi ro cần.

**21. “Nhiều họp đồng bộ nghĩa là phối hợp tốt.”** Nếu không gỡ blocker hoặc giảm dependency, chúng có thể thành hàng chờ mới.

**22. “Số nhóm chạm một PBI giảm thì outcome chắc tăng.”** Cần nhìn giá trị người dùng, chất lượng và kết quả giao hàng.

**23. “Cycle Time giảm nghĩa cấu trúc mới chắc chắn tốt hơn.”** Phải kiểm tra loại việc, cách đo, WIP, lỗi và nhân quả.

**24. “Story points giữa các nhóm so được trực tiếp.”** Cách ước lượng, context và DoD khác nhau; không dùng để xếp hạng nhóm.

**25. “Người ta phải bận 100% để tối ưu tổ chức.”** Thiếu năng lực phản hồi và hỗ trợ làm hàng chờ có thể tăng.

**26. “Có thể tái tổ chức toàn công ty cùng lúc mà không cần thử.”** Cần xét chi phí chuyển đổi và phản hồi; thử nhỏ thường an toàn hơn.

**27. “Cứ luân chuyển nhân sự nhiều là chia sẻ kiến thức.”** Thay đổi người liên tục có thể làm nhóm mất ngữ cảnh; cần cách học ổn định.

**28. “Quyền sở hữu nghĩa nhóm khác không được đọc hoặc đóng góp mã.”** Ownership và chính sách đóng góp có thể cùng rõ ràng mà không tạo silo tuyệt đối.

**29. “DevOps nghĩa Developer phải có mọi quyền production.”** Trách nhiệm vận hành phải phù hợp security, quyền và quy trình.

**30. “Chúng ta đã có Product Goal nên không cần đo người dùng.”** Product Goal cần được kiểm tra và thích ứng theo phản hồi thật.

**31. “Mỗi nhóm đo conversion riêng là đủ.”** Các bước rơi giữa nhóm có thể bị bỏ quên; cần nhìn hành trình tổng thể.

**32. “Trở ngại nhiều là do một nhóm chậm.”** Cần nhìn workflow, hàng chờ, sự phụ thuộc và cơ chế hệ thống trước khi kết luận.

## 27. Bài tập tình huống A: Chuyển một tổ chức theo tầng thành nhóm theo giá trị

Một doanh nghiệp có ba nhóm cố định:

- **UI Team:** 6 người, chịu trách nhiệm toàn bộ giao diện.
- **API Team:** 7 người, chịu trách nhiệm toàn bộ backend.
- **Data & Testing Team:** 5 người, chịu trách nhiệm migration và kiểm thử tích hợp.

Một PBI “đăng ký khóa miễn phí và thấy xác nhận” thường mất 18 ngày làm việc, gồm **10 ngày thực hiện** và **8 ngày chờ** theo các khoảng không chồng lắp. Các nhóm tự theo dõi số ticket Done, nhưng không có đo lường từ PBI bắt đầu tới Increment dùng được.

Product Owner muốn giảm thời gian đưa cải tiến tới người học. Tổ chức cân nhắc tạo các nhóm giá trị “Tiếp cận & Đăng ký”, “Trải nghiệm học”, và một nền tảng hỗ trợ. Tuy nhiên, chỉ một người hiểu migration và chỉ nhóm API có quyền review service enrollment.

### Câu hỏi

1. Vấn đề là **thiếu người** hay có thể là **thiết kế dòng công việc**? Cần thêm bằng chứng gì?
2. Tính tỷ trọng thời gian chờ trong ví dụ 18 ngày. Có được coi đó là tỷ lệ nhân sự nhàn rỗi không?
3. Chọn một dòng giá trị đầu tiên để thử và viết **outcome** rõ.
4. Những kỹ năng nào cần cùng hiện diện để lát cắt đăng ký đạt DoD?
5. Phụ thuộc nào có thể giảm bằng **self-service platform**, phụ thuộc nào cần **quyết định nghiệp vụ**?
6. Nếu chỉ đổi tên ba nhóm, điều gì vẫn khiến handoff tồn tại?
7. Phân biệt **Product Goal, Sprint Goal, Product Backlog và DoD** khi nhiều Scrum Teams cùng sản phẩm.
8. Chọn ít nhất **ba chỉ số** để theo dõi thử nghiệm, gồm một guardrail.
9. Nếu chuyên gia migration vẫn là nút nghẽn, đề xuất hai biện pháp không bỏ yêu cầu an toàn dữ liệu.
10. Khi nào nên mở rộng mô hình và khi nào cần điều chỉnh?

### Gợi ý lời giải

**Câu 1:** Chưa đủ kết luận thiếu người. Cần bản đồ dòng giá trị, WIP, thời gian chờ review/dữ liệu, lượng PBI chạm nhiều nhóm, trạng thái kỹ năng và chất lượng tích hợp. Tăng nhân sự mà không đổi dependency có thể chỉ làm hàng chờ dài hơn.

**Câu 2:** \(8/18\times100\%\approx44{,}4\%\) Cycle Time của item là chờ. **Không** được suy thành tỷ lệ nhân sự không làm việc, vì người có thể đang làm PBI khác và tạo thêm WIP.

**Câu 3:** Thử “người học đã đăng nhập đăng ký khóa miễn phí, thấy xác nhận đúng và có thể mở bài đầu theo quyền hợp lệ”. Outcome có thể là **hoàn tất thao tác đăng ký và bắt đầu học thành công**, được định nghĩa bằng sự kiện và phản hồi người dùng đáng tin.

**Câu 4:** Cần năng lực hiểu nghiệp vụ, UX/frontend, API, dữ liệu/giao dịch, kiểm thử tích hợp, phân quyền và vận hành phù hợp. Không phải một cá nhân phải thực hiện tất cả; chuyên gia và nền tảng có thể hỗ trợ có chủ đích.

**Câu 5:** Platform có thể cung cấp CI, môi trường test, dữ liệu giả và công cụ deploy được phép tự phục vụ. Quy tắc đăng ký lại sau hủy hoặc khi nào được mở bài cần Product Owner/người hiểu nghiệp vụ làm rõ.

**Câu 6:** Nếu mỗi người vẫn làm tầng cũ, mọi ticket vẫn chuyển qua nhiều backlog và quyền review không đổi, luồng người dùng không được tự hoàn tất. Tên nhóm không xóa cơ chế chờ.

**Câu 7:** Cùng sản phẩm: **một Product Goal, một Product Backlog, một Product Owner và một DoD chung**; mỗi Scrum Team có Sprint Goal và Sprint Backlog riêng, nhưng Increment cần tích hợp và đạt DoD sản phẩm.

**Câu 8:** Cycle Time của PBI xuyên luồng, thời gian blocked theo dependency, Work Item Age, WIP hoặc số PBI cần chờ nhóm khác. Guardrail: lỗi tích hợp, chất lượng dữ liệu, sự cố phân quyền và DoD. Nên theo dõi outcome người học để tránh chỉ tối ưu nội bộ.

**Câu 9:** Pair/chia sẻ kỹ năng migration với người đủ năng lực; xây môi trường thử và hướng dẫn migration có kiểm chứng. Với production data, vẫn giữ review/phê duyệt và kế hoạch khôi phục theo chính sách.

**Câu 10:** Mở rộng nếu sau nhiều chu kỳ tương đồng, chờ giảm, DoD giữ, lỗi không tăng và kết quả người dùng cải thiện hoặc có bằng chứng phù hợp. Điều chỉnh nếu tăng tải nhận thức, trùng quyền sở hữu, mất chuyên gia hay phải chờ nhiều như trước.

## 28. Bài tập tình huống B: Hai Scrum Teams cùng phát triển một sản phẩm

Một sản phẩm học trực tuyến có:

- **Scrum Team A — Đăng ký:** Đang cải thiện đăng ký khóa và trạng thái xác nhận.
- **Scrum Team B — Học tập:** Đang cải thiện mở bài đầu và lưu tiến độ.
- Cả hai cùng cần xác thực, quyền học và một API enrollment.

Hiện mỗi nhóm có một backlog riêng, một người gọi là “Product Owner của nhóm”, một DoD riêng. Nhóm A coi Done khi API trả thành công; nhóm B coi Done khi giao diện hoạt động với mock. Sau Sprint, khi ghép lại, người học đăng ký xong nhưng vẫn không mở được bài đầu.

### Câu hỏi

1. Những điểm nào chưa phù hợp nếu **đây là nhiều Scrum Teams cùng một sản phẩm**?
2. Cần chia sẻ những commitments/artifacts nào? Cái gì vẫn có ở từng Scrum Team?
3. Vì sao cả hai nhóm có nhiều task Done mà chức năng người học vẫn chưa Done?
4. Đề xuất cách làm rõ **hợp đồng quyền học** trước khi nhiều mã được viết.
5. Có nhất thiết lập Scrum of Scrums hằng ngày không? Khi nào một cuộc đồng bộ kỹ thuật hữu ích hơn?
6. Nếu Team A phải đổi trạng thái API, nên dùng những kiểm tra nào để giảm xung đột ngữ nghĩa?
7. Nếu Team B phải đợi Team A một tuần, nhóm cần làm gì trước khi thêm cuộc họp mới?
8. Nếu Team A đã đạt một Sprint Goal riêng nhưng Team B chưa, Product Goal và DoD chung giúp đánh giá thế nào?
9. Khi Product Owner cần ưu tiên khắc phục lỗi phân quyền, việc này được xử lý trong backlog ra sao?
10. Viết một **working agreement 5 dòng** cho việc tích hợp hai nhóm.

### Gợi ý lời giải

**Câu 1:** Với cùng sản phẩm Scrum, hai nhóm nên dùng chung **Product Owner, Product Backlog, Product Goal và DoD**. Có thể có các góc nhìn backlog theo nhóm, nhưng không tạo hai nguồn ưu tiên sản phẩm độc lập. Một định nghĩa Done chỉ cho mock hoặc unit test riêng là chưa đủ cho Increment chung nếu những kiểm tra chất lượng áp dụng chưa đạt.

**Câu 2:** Product Goal, Product Backlog, Product Owner và DoD chung; mỗi Scrum Team có Sprint Goal, Sprint Backlog và cách tự quản riêng. Những phần sản phẩm phải tích hợp thành Increment đạt DoD.

**Câu 3:** Task UI/API đã xong không chứng minh quyền học hoạt động xuyên hệ thống. Acceptance criteria, kiểm thử hợp đồng, integration và DoD cần được đánh giá trên phần kết quả thật.

**Câu 4:** Làm rõ trạng thái đăng ký, quy tắc quyền mở bài sau khi đăng ký/hủy, lỗi timeout và phân quyền. Viết ví dụ hành vi, contract tests và phân định nguồn dữ liệu đáng tin.

**Câu 5:** Không. Scrum of Scrums là lựa chọn. Một cuộc đồng bộ nhỏ giữa người liên quan tới contract, CI hoặc quyết định sản phẩm có thể hữu ích hơn một tầng báo cáo cố định.

**Câu 6:** Contract tests consumer–provider, integration tests với dữ liệu thật ở môi trường thử, kiểm tra semantic status, các điều kiện lỗi và tương thích phiên bản; phối hợp review trước khi merge.

**Câu 7:** Xem dependency có thể giảm bằng contract rõ, feature slicing, hỗ trợ trực tiếp hoặc thay đổi ownership. Minh bạch blocked time và người quyết định, không chỉ đặt họp để đọc status.

**Câu 8:** Sprint Goal từng nhóm phản ánh mục tiêu cục bộ có giá trị; Product Goal giữ hướng sản phẩm. Nếu một hành trình xuyên nhóm còn thiếu và chưa đạt DoD, không được mô tả nó như Increment hoàn tất dù một nhóm đạt nhiều task.

**Câu 9:** Product Owner quản lý thứ tự ưu tiên Product Backlog bằng thông tin rủi ro. Developers nêu tác động và phương án kỹ thuật; nếu có sự cố đang gây hại, áp dụng ứng cứu và quyền bảo mật ngay, không chờ chu kỳ ưu tiên thông thường.

**Câu 10 — Thỏa thuận minh họa:**

> 1. Chúng tôi làm rõ hành vi xuyên nhóm và ranh giới dữ liệu trước khi triển khai lớn.  
> 2. Contract API thay đổi phải có ví dụ nghiệp vụ và kiểm tra tương thích.  
> 3. Các nhóm tích hợp thường xuyên và cùng xử lý build chung đỏ.  
> 4. Phần chưa đạt DoD chung không được báo là Increment Done.  
> 5. Dependency bị chặn được báo sớm với người có quyền xử lý và mốc kiểm tra lại.

## 29. Bài tập thiết kế Team API và thử nghiệm 2 Sprint

Hãy chọn luồng **“Đăng ký → Xác nhận → Mở bài đầu”** và tự đề xuất:

1. Tên nhóm và **outcome** mà nhóm chịu trách nhiệm theo đuổi.
2. Ranh giới nghiệp vụ/dữ liệu của nhóm và những dịch vụ dùng chung.
3. Kỹ năng tối thiểu phải có trong nhóm hoặc đường hỗ trợ tin cậy.
4. Ba loại dependency lặp lại mà nhóm muốn giảm.
5. Hai chính sách cộng tác liên nhóm, ví dụ contract tests và review khi đổi schema.
6. Cách giữ **DoD chung** khi nhiều Scrum Teams cùng sản phẩm.
7. Metric chính cho việc giảm chờ, metric outcome người dùng và guardrail chất lượng.
8. Thời gian thử và thời điểm nhìn lại.
9. Tiêu chí quyết định giữ, sửa hoặc dừng mô hình.

### Một ví dụ thử nghiệm minh họa

| Thành phần | Phương án |
| --- | --- |
| **Vấn đề** | PBI đăng ký mất nhiều ngày do phải chờ nhóm khác thực hiện UI/API/DB |
| **Giả thuyết** | Nếu nhóm thử có năng lực xuyên ranh giới và contract rõ, blocked time giảm |
| **Phạm vi thử** | Hai Sprint, một chuỗi PBI đăng ký tương đồng; không chuyển toàn tổ chức cùng lúc |
| **Can thiệp** | Pair UI–API–data, PR nhỏ, CI/contract tests, reviewer dự phòng |
| **Metric dòng công việc** | Age, Cycle Time và blocked time theo cùng định nghĩa |
| **Outcome** | Đăng ký và mở bài thành công theo cohort/luồng đủ điều kiện |
| **Guardrails** | DoD, lỗi phân quyền, dữ liệu trùng, incident và tải của thành viên |
| **Điểm xem lại** | Sau mỗi Sprint và sau khi có dữ liệu người dùng đủ điều kiện |
| **Quyết định** | Giữ, điều chỉnh hoặc mở rộng theo bằng chứng và rủi ro |

**Không có tỷ lệ cải thiện cố định được bảo đảm.** Hai Sprint có thể đủ để thấy nút nghẽn ban đầu, nhưng chưa đủ chứng minh outcome dài hạn; tiếp tục theo dõi khi cần.

## 30. Checklist thiết kế và vận hành nhóm theo dòng giá trị

### A. Xác định giá trị và ranh giới

1. **Người dùng:** Có biết ai nhận giá trị và nhu cầu nào được giải quyết?
2. **Outcome:** Có kết quả quan sát được ngoài số task kỹ thuật?
3. **Dòng giá trị:** Có bản đồ từ nhu cầu tới Increment và phản hồi?
4. **Handoff:** Đã thấy nơi chờ và bàn giao lặp lại?
5. **Miền nghiệp vụ:** Ranh giới nhóm có khớp với những quy tắc cần thay đổi cùng nhau?
6. **Cognitive load:** Phạm vi có vừa năng lực hiểu và vận hành của nhóm?
7. **Đổi cấu trúc:** Có bằng chứng thực tế trước khi tái tổ chức lớn?

### B. Năng lực và trách nhiệm

8. **Đa chức năng:** Nhóm có đủ kỹ năng để đưa lát cắt tới DoD?
9. **Học hỏi:** Có cơ chế pairing và hỗ trợ để giảm phụ thuộc một chuyên gia?
10. **Ownership:** Ai theo dõi chất lượng và kết quả xuyên hệ thống?
11. **Quyền:** Các quyết định kỹ thuật, dữ liệu, bảo mật và production có thẩm quyền rõ?
12. **Platform:** Năng lực nào có thể dùng chung theo self-service?
13. **Enabling:** Chuyên gia hỗ trợ có giúp nhóm khác tự chủ dần?
14. **Ổn định nhóm:** Có đủ ổn định để tích lũy hiểu biết sản phẩm?
15. **Bền vững:** Review, vận hành và cải tiến có năng lực thực tế, không ép 100% bận rộn?

### C. Scrum và phối hợp nhiều nhóm

16. **Product Goal:** Nếu nhiều Scrum Teams cùng sản phẩm, có mục tiêu sản phẩm chung?
17. **Product Backlog:** Có một nguồn ưu tiên sản phẩm minh bạch, do Product Owner chịu trách nhiệm?
18. **Sprint Goal:** Mỗi Scrum Team có mục tiêu riêng căn chỉnh về giá trị?
19. **Definition of Done:** Các Scrum Teams cùng sản phẩm đã dùng DoD chung?
20. **Increment:** Có tích hợp thành phần sử dụng được, không chỉ task mỗi nhóm?
21. **Dependency:** Có chủ sở hữu trao đổi, điều kiện kết thúc và mốc xem lại?
22. **Đồng bộ:** Cuộc họp có giúp ra quyết định và gỡ blocker hay chỉ thêm báo cáo?
23. **Hợp đồng:** API, dữ liệu, lỗi và hành vi xuyên nhóm đã được làm rõ?

### D. Kỹ thuật và an toàn

24. **CI:** Có tích hợp thay đổi nhỏ thường xuyên vào trạng thái chung?
25. **Tests:** Ranh giới UI/API/DB và dữ liệu quan trọng được kiểm chứng?
26. **Dữ liệu:** Migration và phân quyền có người chịu trách nhiệm và kế hoạch an toàn?
27. **Release:** Có đường phát hành/khôi phục phù hợp quyền và chính sách?
28. **Observability:** Nhóm biết chức năng có hoạt động trong sử dụng thật?
29. **Không lạm quyền:** “End-to-end” không bị dùng để bỏ kiểm soát bắt buộc?

### E. Đo lường và cải tiến

30. **Flow metrics:** WIP, Work Item Age, Cycle Time, Throughput có được định nghĩa đúng?
31. **Blocked time:** Có biết nhóm chờ đâu và vì sao, không đếm trùng?
32. **Chất lượng:** Tốc độ có được đọc cùng lỗi và DoD?
33. **Outcome:** Có đo kết quả người dùng theo cohort/định nghĩa phù hợp?
34. **Guardrail:** Có quan sát tác dụng phụ về dữ liệu, bảo mật, vận hành, con người?
35. **Thử nghiệm nhỏ:** Có thể thay chính sách một luồng trước khi đổi toàn tổ chức?
36. **Điểm xem lại:** Có điều kiện giữ, điều chỉnh hoặc dừng mô hình?
37. **Nhân quả:** Có tránh khẳng định tái tổ chức là nguyên nhân duy nhất của một kết quả trước/sau?

## 31. Tổng kết: tối ưu khả năng hoàn tất giá trị, không tối ưu sơ đồ tổ chức

Phối hợp nhiều nhóm trong Agile không chỉ là tăng số cuộc họp, liên kết kế hoạch hay yêu cầu các nhóm gửi status đều hơn. Vấn đề sâu hơn là **cách tổ chức năng lực, quyền quyết định và kiến trúc có giúp tạo một kết quả người dùng xuyên suốt hay không**.

| Khi cấu trúc tạo nhiều handoff | Khi tổ chức hướng dòng giá trị |
| --- | --- |
| Nhiều nhóm hoàn tất từng tầng nhưng người dùng chưa làm được việc | Nhóm theo dõi PBI/Increment tới kết quả có thể sử dụng |
| Mỗi nhóm tối ưu output riêng | Cả hệ thống quan tâm lead time, chất lượng và outcome |
| API và dữ liệu được làm rõ sau khi code | Các ranh giới được làm rõ và kiểm chứng sớm |
| Quyền review, test, deployment thành hàng chờ | Tự phục vụ ở nơi phù hợp, chuyên gia hỗ trợ đúng rủi ro |
| Mỗi nhóm có mục tiêu và DoD tách biệt cho cùng sản phẩm | Chung Product Goal, Product Backlog, Product Owner và DoD khi áp dụng Scrum |
| Tích hợp chỉ diễn ra cuối kỳ | CI, contract test và Increment tích hợp thường xuyên |
| Nhiều lịch họp để báo phụ thuộc | Người liên quan cùng giải quyết những phụ thuộc có tác động |
| Cải tiến chỉ là đổi tên hoặc sơ đồ nhân sự | Thử nhỏ ranh giới mới, quan sát và điều chỉnh theo bằng chứng |
| Chỉ đo số ticket hoặc story points | Đo dòng giá trị, chất lượng, người dùng và năng lực bền vững |
| “Độc lập” bị hiểu là bỏ chuẩn chung | Tự chủ trong ranh giới minh bạch và giữ an toàn sản phẩm |

**Ghi nhớ:** Bắt đầu từ **người dùng và hành trình tạo giá trị**, quan sát những lần chuyển giao, hàng chờ và phụ thuộc, rồi xây năng lực **đa chức năng ở cấp nhóm** đủ để đưa lát cắt nhỏ tới **Definition of Done**. Khi nhiều Scrum Teams cùng một sản phẩm, **Product Goal, Product Backlog, Product Owner và DoD chung** giữ sự thống nhất; mỗi Scrum Team vẫn tự quản việc thực hiện và Sprint Goal của mình. Nhóm nền tảng, enabling và chuyên gia phức tạp có thể hỗ trợ khi thực sự giảm tải nhận thức và chờ đợi, không phải trở thành tầng bàn giao mới. Kết hợp Kanban để nhìn WIP/age, XP để tích hợp và kiểm thử sớm, Lean để tối ưu toàn dòng, và phản hồi người dùng để điều chỉnh Product Backlog sẽ giúp tổ chức **giao phần mềm tăng dần đáng tin, giảm chi phí phối hợp và thích ứng tốt hơn trước thay đổi**.

