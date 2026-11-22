# Chọn một miền nhỏ cho dự án DSL thực hành

Một dự án ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) thành công thường bắt đầu từ một vấn đề đủ cụ thể. Nếu chọn miền quá rộng, nhóm sẽ phải mô hình hóa quá nhiều khái niệm, quy tắc và ngoại lệ trước khi có thể tạo ra một chương trình chạy được. Nếu chọn miền quá hẹp hoặc không có quy tắc lặp lại, DSL có thể không mang lại lợi ích so với cấu hình hoặc một vài hàm thông thường.

**Chọn một miền nhỏ** là xác định một phạm vi nghiệp vụ có ranh giới rõ, có người dùng cụ thể, có thuật ngữ và quy tắc đủ ổn định để biểu diễn bằng ngôn ngữ chuyên biệt. Phạm vi nhỏ giúp nhóm học cách biến khái niệm miền thành cú pháp, kiểu dữ liệu, semantics và runtime mà không phải giải quyết toàn bộ hệ thống nghiệp vụ ngay từ đầu.

Miền phù hợp cho dự án thực hành thường có đầu vào và đầu ra nhận diện được, một số quy tắc có thể diễn đạt, ví dụ thực tế và cách xác minh kết quả. Chẳng hạn, thay vì xây DSL cho toàn bộ thương mại điện tử, có thể bắt đầu bằng DSL xác định điều kiện miễn phí vận chuyển cho một đơn hàng. Thay vì mô hình hóa toàn bộ ngân hàng, có thể chọn một DSL kiểm tra điều kiện phê duyệt hạn mức mẫu.

Chọn miền nhỏ không có nghĩa là chọn một bài toán tùy tiện. Cần hiểu vấn đề, người dùng, dữ liệu, ranh giới và tiêu chí thành công trước khi bắt đầu thiết kế ngôn ngữ.

## 1. Miền nghiệp vụ là gì?

### 1.1. Khái niệm domain

Domain là phạm vi kiến thức và hoạt động mà một hệ thống hoặc nhóm người dùng quan tâm. Một miền có:
- Khái niệm và thuật ngữ riêng.
- Đối tượng và quan hệ.
- Quy tắc và ràng buộc.
- Quy trình hoặc sự kiện.
- Vai trò người tham gia.
- Dữ liệu đầu vào và kết quả.

Ví dụ, miền quản lý đặt lịch có khái niệm Appointment, Resource, TimeSlot, Availability và CancellationPolicy. Miền định giá có Product, Price, Discount, CustomerTier và EffectiveDate.

### 1.2. Bounded context

Bounded context là ranh giới trong đó một mô hình miền và thuật ngữ có ý nghĩa nhất quán. Một thuật ngữ có thể mang nghĩa khác ở context khác.

Ví dụ, Status trong miền đơn hàng có thể là PENDING, PAID hoặc CANCELLED; Status trong miền vận chuyển có thể là CREATED, IN_TRANSIT hoặc DELIVERED. Không nên gộp mọi trạng thái vào một enum chung nếu semantics khác nhau.

### 1.3. Miền nhỏ trong dự án thực hành

Miền nhỏ là một phần bounded context có thể được mô tả và kiểm chứng trong thời gian dự án. Nó không nhất thiết là một ngành nghề hoàn chỉnh. Ví dụ:
- Tính điều kiện miễn phí vận chuyển.
- Kiểm tra hồ sơ có đủ giấy tờ.
- Phân loại ticket hỗ trợ.
- Xác định quyền truy cập theo vai trò.
- Chọn bước tiếp theo trong một workflow.
- Kiểm tra điều kiện áp dụng khuyến mãi.

### 1.4. Vấn đề nghiệp vụ và miền

Vấn đề nghiệp vụ là điều người dùng muốn giải quyết. Miền là phạm vi khái niệm và quy tắc liên quan. Một DSL tốt xuất phát từ vấn đề lặp lại trong miền, không xuất phát từ mong muốn tạo một cú pháp mới.

### 1.5. Domain expert

Domain expert là người hiểu quy tắc và ngoại lệ thực tế. Người này có thể là chuyên viên nghiệp vụ, nhân viên vận hành, analyst hoặc người dùng giàu kinh nghiệm. Nhóm xây DSL cần trao đổi với họ để tránh tự suy đoán semantics.

## 2. Vì sao nên bắt đầu bằng miền nhỏ?

### 2.1. Giảm phạm vi cần mô hình hóa

Một miền nhỏ giới hạn số entity, type, rule và workflow. Nhóm có thể tập trung vào chất lượng mô hình và semantics thay vì liên tục mở rộng phạm vi.

### 2.2. Dễ kiểm chứng

Miền có đầu vào và đầu ra rõ giúp tạo ví dụ và test. Ví dụ, một đơn hàng có tổng tiền, khu vực giao hàng và hạng khách hàng; kết quả là phí vận chuyển và lý do áp dụng.

### 2.3. Dễ trao đổi với người dùng

Người dùng có thể xác nhận một quy tắc cụ thể dễ hơn một tuyên bố chung như "tự động hóa toàn bộ hoạt động bán hàng".

### 2.4. Hạn chế thiết kế quá mức

Nếu bắt đầu bằng một miền lớn, nhóm dễ thêm abstraction cho những use case chưa biết. Phạm vi nhỏ giúp chỉ tạo cú pháp và type cần thiết cho bài toán hiện tại.

### 2.5. Có thể mở rộng sau

Một miền nhỏ có thể trở thành hạt nhân cho dự án lớn hơn. Khi có bằng chứng về nhu cầu, nhóm mới mở rộng sang miền liền kề hoặc tạo plugin.

### 2.6. Hoàn thành được một vòng end-to-end

Dự án thực hành nên đi qua toàn bộ vòng:
1. Mô tả vấn đề.
2. Chọn thuật ngữ.
3. Thiết kế DSL.
4. Parse và validate.
5. Evaluate hoặc generate.
6. Kiểm thử.
7. Thử với ví dụ thực tế.

Miền nhỏ giúp hoàn thành vòng này trong phạm vi có thể quản lý.

## 3. Tiêu chí chọn miền phù hợp

### 3.1. Có vấn đề cụ thể

Mô tả được người dùng đang gặp khó khăn gì. Ví dụ: nhân viên phải đọc nhiều điều kiện để xác định đơn hàng có được miễn phí vận chuyển hay không.

### 3.2. Có quy tắc lặp lại

DSL phù hợp khi nhiều quyết định có cấu trúc tương tự và thay đổi theo dữ liệu hoặc policy. Nếu chỉ có một thao tác đơn giản, một hàm hoặc cấu hình có thể đủ.

### 3.3. Có thuật ngữ ổn định

Người dùng có thể thống nhất tên và ý nghĩa của các khái niệm. Nếu mỗi người dùng một thuật ngữ khác nhau, cần làm rõ domain vocabulary trước.

### 3.4. Có input và output rõ

Có thể liệt kê dữ liệu đầu vào và kết quả:
- Input: customer tier, order total, region.
- Output: shipping decision, fee, reason.

### 3.5. Có ranh giới

Có thể nói rõ điều gì nằm trong và ngoài dự án. Ví dụ DSL chỉ quyết định phí vận chuyển, không xử lý thanh toán, tạo vận đơn hoặc quản lý kho.

### 3.6. Có ví dụ thực tế

Domain expert có thể cung cấp các trường hợp:
- Bình thường.
- Biên.
- Ngoại lệ.
- Xung đột.
- Dữ liệu thiếu.
- Quy tắc thay đổi.

### 3.7. Có cách xác minh

Có thể xác định expected result cho một tập ví dụ hoặc so sánh với quyết định đã được người có chuyên môn xác nhận.

### 3.8. Có thể lấy dữ liệu mẫu an toàn

Nhóm có thể dùng dữ liệu tổng hợp hoặc dữ liệu đã ẩn danh. Không nên để dự án phụ thuộc vào dữ liệu cá nhân hoặc hệ thống production mà không có quyền phù hợp.

### 3.9. Có quy mô phù hợp

Số khái niệm, rule và loại dữ liệu phải phù hợp thời gian, kỹ năng và công cụ của nhóm. Không cần chọn miền có hàng trăm trạng thái để chứng minh khả năng của DSL.

### 3.10. Có giá trị so với cách làm hiện tại

DSL nên làm cho việc mô tả, review, kiểm tra hoặc thay đổi quy tắc dễ hơn. Nếu một bảng cấu hình đơn giản đã đủ, DSL có thể không phải lựa chọn tốt.

## 4. Phân biệt miền phù hợp và không phù hợp

| Dấu hiệu | Miền phù hợp | Miền chưa phù hợp |
|---|---|---|
| Quy tắc | Có nhiều rule lặp lại | Chỉ có một điều kiện đơn giản |
| Thuật ngữ | Được người dùng hiểu chung | Mỗi người định nghĩa khác nhau |
| Input/output | Xác định được | Phụ thuộc nhiều hệ thống chưa rõ |
| Phạm vi | Có thể giới hạn | Bao trùm cả tổ chức |
| Kiểm chứng | Có ví dụ và expected result | Không có oracle hoặc dữ liệu |
| Thay đổi | Có policy cần người dùng quản lý | Logic thay đổi liên tục và chưa hiểu |
| Giá trị DSL | Dễ đọc và review hơn code/config | Cú pháp mới làm việc khó hơn |

### 4.1. Miền quá rộng

Ví dụ "quản lý doanh nghiệp" gồm bán hàng, kế toán, nhân sự, kho, mua hàng và báo cáo. Đây là nhiều bounded context khác nhau, không phù hợp làm một miền đầu tiên.

### 4.2. Miền quá mơ hồ

"AI ra quyết định thông minh" không mô tả được input, output, rule hay tiêu chí đúng. Cần thu hẹp thành một quyết định cụ thể.

### 4.3. Miền không có quy tắc ổn định

Nếu quyết định hoàn toàn dựa vào đánh giá chủ quan và không thể mô tả điều kiện, DSL rule có thể không phù hợp. Có thể cần workflow, form hoặc công cụ hỗ trợ quyết định khác.

### 4.4. Miền phụ thuộc quá nhiều vào bên ngoài

Một bài toán cần hàng chục dịch vụ, dữ liệu thời gian thực và quyền truy cập production có thể quá lớn cho dự án đầu tiên. Có thể mô phỏng dependency hoặc chọn một phần độc lập.

## 5. Bắt đầu từ người dùng và công việc

### 5.1. Xác định persona

Ghi rõ ai sẽ viết, đọc, review hoặc vận hành DSL:
- Domain analyst.
- Business operator.
- Developer.
- Administrator.
- Auditor.

Mỗi persona có mức hiểu kỹ thuật và nhu cầu khác nhau.

### 5.2. Xác định công việc

Mô tả công việc theo dạng:
- Người dùng nhận input gì?
- Họ phải đưa ra quyết định nào?
- Họ dựa vào quy tắc hoặc dữ liệu nào?
- Họ tạo ra output gì?
- Ai sử dụng output tiếp theo?

### 5.3. Quan sát quy trình hiện tại

Tìm hiểu cách người dùng đang làm:
- Spreadsheet.
- Form.
- Rule engine.
- Code.
- Checklist.
- Tài liệu hướng dẫn.
- Trao đổi thủ công.

Ghi nhận chỗ nào lặp lại, dễ sai hoặc khó review.

### 5.4. Thu thập ví dụ và ngoại lệ

Hỏi domain expert về một số trường hợp thật đã được ẩn danh:
- Trường hợp dễ.
- Trường hợp sát ngưỡng.
- Trường hợp thiếu dữ liệu.
- Trường hợp hai quy tắc cùng áp dụng.
- Trường hợp ngoại lệ được phê duyệt.

### 5.5. Xác định người xác nhận

Một dự án cần biết ai có quyền xác nhận rule đúng về nghiệp vụ. Developer không nên tự quyết định semantics chỉ vì implementation dễ hơn.

## 6. Xây dựng domain vocabulary

### 6.1. Thuật ngữ cốt lõi

Liệt kê danh từ, động từ, trạng thái và điều kiện thường dùng. Ví dụ miền miễn phí vận chuyển:
- Order.
- Customer.
- Region.
- ShippingMethod.
- OrderTotal.
- Eligibility.
- ShippingFee.

### 6.2. Định nghĩa thuật ngữ

Mỗi thuật ngữ cần định nghĩa ngắn, ví dụ và đơn vị nếu có. "Total" có thể là tổng trước thuế, sau thuế hoặc sau giảm giá; cần xác định rõ.

### 6.3. Từ đồng nghĩa

Nếu người dùng dùng nhiều từ cho cùng một khái niệm, chọn canonical term và ghi lại alias. Tránh để cùng một từ mang hai nghĩa.

### 6.4. Thuật ngữ trùng tên giữa miền

Nếu OrderStatus và PaymentStatus khác nhau, dùng tên riêng hoặc namespace. Không gộp chỉ vì cả hai đều là trạng thái.

### 6.5. Glossary

Một glossary nhỏ có thể gồm:

| Term | Định nghĩa | Ví dụ |
|---|---|---|
| OrderTotal | Tổng giá trị đơn hàng theo policy đã chọn | 1.200.000 VND |
| CustomerTier | Hạng khách hàng | GOLD |
| Region | Khu vực giao hàng | INNER_CITY |
| Eligible | Đủ điều kiện theo rule set | true |
| ShippingFee | Phí vận chuyển cuối cùng | 0 VND |

### 6.6. Kiểm tra vocabulary với người dùng

Đưa glossary cho domain expert đọc và yêu cầu họ sửa. Nếu không thể thống nhất từ ngữ, chưa nên khóa syntax.

## 7. Xác định đối tượng, thuộc tính và quan hệ

### 7.1. Entity

Entity là đối tượng có identity trong miền, ví dụ Customer, Order hoặc Shipment.

### 7.2. Value object

Value object được xác định bởi giá trị, ví dụ Money, Percentage, DateRange hoặc Address. Kiểu miền giúp tránh nhầm lẫn giữa các scalar cùng hình thức.

### 7.3. Attribute

Liệt kê field cần thiết cho quyết định. Không lấy toàn bộ database schema nếu DSL chỉ cần vài trường.

### 7.4. Relationship

Xác định quan hệ:
- Một Order thuộc một Customer.
- Một Order có nhiều OrderItem.
- Một Region có nhiều ShippingZone.
- Một Customer có một Tier tại thời điểm quyết định.

### 7.5. Cardinality và nullability

Ghi rõ quan hệ one-to-one, one-to-many, optional và required. Field có thể null cần có semantics cụ thể.

### 7.6. Data ownership

Xác định nguồn dữ liệu nào là nguồn sự thật. DSL có thể nhận snapshot input thay vì truy cập trực tiếp nhiều hệ thống trong dự án đầu tiên.

## 8. Xác định quy tắc và quyết định

### 8.1. Rule inventory

Lập danh sách rule bằng ngôn ngữ tự nhiên trước khi viết DSL:
- Đơn hàng đạt ngưỡng được miễn phí vận chuyển.
- Khách hàng VIP được giảm phí.
- Một số khu vực có phụ phí.
- Hàng cồng kềnh không áp dụng miễn phí.

### 8.2. Condition và action

Mỗi rule cần:
- Điều kiện kích hoạt.
- Kết quả hoặc hành động.
- Mức ưu tiên nếu có.
- Lý do nghiệp vụ.
- Trạng thái bật/tắt.
- Owner.

### 8.3. Decision table

Bảng quyết định giúp phát hiện tổ hợp thiếu:

| VIP | Total đạt ngưỡng | Hàng cồng kềnh | Kết quả |
|---|---|---|---|
| No | No | No | Tính phí chuẩn |
| No | Yes | No | Miễn phí |
| Yes | No | No | Giảm phí |
| Yes | Yes | No | Miễn phí |
| Any | Any | Yes | Phụ phí cồng kềnh |

Bảng chỉ là ví dụ; người sở hữu policy cần xác nhận ưu tiên giữa các điều kiện.

### 8.4. Conflict và precedence

Nếu hai rule cùng khớp, cần quyết định:
- Cộng kết quả.
- Chọn rule ưu tiên cao nhất.
- Chạy tất cả action.
- Báo conflict.
- Dùng một resolver được công bố.

Không để hành vi phụ thuộc thứ tự file một cách ngẫu nhiên.

### 8.5. Boundary case

Với ngưỡng 1.000.000 VND, kiểm tra 999.999, 1.000.000 và 1.000.001. Với ngày hiệu lực, kiểm tra trước, đúng và sau thời điểm chuyển.

### 8.6. Default behavior

Xác định kết quả khi không có rule nào khớp. Không nên mặc định approve hoặc allow nếu policy yêu cầu fail closed.

### 8.7. Side effect

Với miền đầu tiên, ưu tiên mô tả quyết định thuần nếu có thể. Gửi email, thanh toán hoặc cập nhật hệ thống có thể được mô phỏng thành command output để giới hạn phạm vi.

## 9. Xác định input và output contract

### 9.1. Input

Liệt kê field cần thiết và kiểu:
~~~text
OrderInput {
    total: Money
    region: RegionCode
    bulky: Boolean
    customerTier: CustomerTier
}
~~~

### 9.2. Output

Kết quả nên cụ thể:
~~~text
ShippingDecision {
    eligible: Boolean
    fee: Money
    reasonCodes: List<ReasonCode>
}
~~~

### 9.3. Context

Có thể cần evaluation time, tenant, policy version hoặc locale. Chỉ đưa vào context những giá trị thực sự ảnh hưởng semantics.

### 9.4. Error

Xác định lỗi do:
- Input thiếu hoặc sai kiểu.
- Không có dữ liệu tham chiếu.
- Không có rule phù hợp.
- Nhiều rule xung đột.
- Dependency lỗi.
- Policy version không tương thích.

### 9.5. Explainability

Nếu người dùng cần biết vì sao có kết quả, output nên chứa reason code hoặc decision trace, không chỉ một Boolean.

## 10. Đặt ranh giới scope

### 10.1. In-scope

Viết danh sách chức năng sẽ làm. Ví dụ:
- Nhận OrderInput.
- Đánh giá rule vận chuyển.
- Trả ShippingDecision.
- Giải thích rule đã áp dụng.
- Hỗ trợ một bộ dữ liệu mẫu.

### 10.2. Out-of-scope

Ghi rõ những gì chưa làm:
- Tạo vận đơn thật.
- Thanh toán.
- Quản lý kho.
- Tính phí từ hãng vận chuyển trực tiếp.
- Quản lý tài khoản khách hàng.
- Tích hợp production.

### 10.3. Non-goals

Non-goal giúp tránh mở rộng vô tình. Một dự án chọn miền vận chuyển không cần trở thành nền tảng thương mại điện tử.

### 10.4. Interface với hệ thống ngoài

Nếu cần dữ liệu từ hệ thống khác, xác định contract và dùng fixture hoặc fake adapter trong giai đoạn đầu.

### 10.5. Scope change

Yêu cầu mới cần được đánh giá theo giá trị, chi phí và ảnh hưởng thời gian. Không tự thêm mọi trường hợp ngoại lệ vào giữa dự án.

## 11. Đánh giá quy mô và tính khả thi

### 11.1. Số khái niệm

Đếm entity, value object, enum và relationship cần thiết. Nếu có quá nhiều khái niệm, thu hẹp use case.

### 11.2. Số rule

Ước lượng số rule và số điều kiện. Một tập nhỏ nhưng có nhiều tương tác có thể khó hơn nhiều rule độc lập.

### 11.3. Độ phức tạp semantics

Đánh giá:
- Có stateful behavior không?
- Có side effect không?
- Có thời gian hoặc concurrency không?
- Có transaction không?
- Có nhiều nguồn dữ liệu không?
- Có cần authorization không?

### 11.4. Data availability

Xác định có thể tạo fixture và expected output hay không. Nếu không có dữ liệu hoặc domain expert, rủi ro dự án tăng.

### 11.5. Skill và toolchain

Đánh giá nhóm có thể triển khai parser, runtime và test harness trong thời gian không. Không cần chọn miền đòi hỏi công nghệ mà nhóm chưa thể vận hành.

### 11.6. Feasibility spike

Thử một rule đơn giản từ source DSL đến output. Nếu không thể hoàn thành vertical slice nhỏ, cần điều chỉnh scope trước khi mở rộng.

## 12. Ma trận chấm điểm miền ứng viên

### 12.1. Tiêu chí

Có thể chấm mỗi miền từ 1 đến 5 theo:
- Vấn đề cụ thể.
- Tính lặp lại của rule.
- Độ ổn định vocabulary.
- Input/output rõ.
- Khả năng có dữ liệu.
- Khả năng xác minh.
- Phạm vi có thể giới hạn.
- Giá trị DSL so với code/config.
- Mức rủi ro và dependency.
- Mức độ quan tâm của người dùng.

### 12.2. Ma trận minh họa

| Tiêu chí | Miễn phí vận chuyển | Phân loại ticket | Toàn bộ ERP |
|---|---:|---:|---:|
| Vấn đề cụ thể | 5 | 4 | 2 |
| Rule lặp lại | 5 | 4 | 4 |
| Vocabulary ổn định | 4 | 4 | 2 |
| Input/output rõ | 5 | 4 | 2 |
| Dữ liệu mẫu | 5 | 4 | 2 |
| Scope giới hạn | 5 | 4 | 1 |
| Khả năng kiểm chứng | 5 | 3 | 2 |
| Tổng minh họa | 34 | 27 | 15 |

Điểm số chỉ giúp so sánh có cấu trúc. Cần ghi lý do cho từng điểm và không coi tổng điểm là quyết định tự động.

### 12.3. Trọng số

Nếu tiêu chí có mức quan trọng khác nhau, có thể dùng trọng số. Ví dụ với dự án học tập, khả năng kiểm chứng và scope có thể quan trọng hơn tích hợp production.

### 12.4. Rủi ro loại trừ

Một miền có thể bị loại dù tổng điểm cao nếu thiếu domain expert, không có dữ liệu hợp pháp hoặc không thể xác định expected result.

## 13. Các miền nhỏ phù hợp để thực hành

### 13.1. Chính sách miễn phí vận chuyển

Input:
- Tổng đơn.
- Hạng khách hàng.
- Khu vực.
- Loại hàng.

Output:
- Đủ điều kiện miễn phí.
- Phí cuối cùng.
- Reason code.

Ưu điểm: rule rõ, có ngưỡng, enum và conflict.

### 13.2. Điều kiện áp dụng khuyến mãi

Input:
- Customer tier.
- Product category.
- Order total.
- Thời gian.
- Coupon.

Output:
- Eligible.
- Discount amount.
- Reason.

Cần giới hạn số loại promotion và quy tắc cộng dồn.

### 13.3. Kiểm tra hồ sơ

Input:
- Loại hồ sơ.
- Tài liệu đã nộp.
- Ngày hết hạn.
- Nhóm khách hàng.

Output:
- Complete/incomplete.
- Missing documents.
- Reason code.

Phù hợp để thực hành validation và decision table.

### 13.4. Phân loại ticket hỗ trợ

Input:
- Category.
- Severity.
- Customer tier.
- Keywords hoặc metadata đã được chuẩn hóa.

Output:
- Queue.
- Priority.
- SLA class.

Có thể bắt đầu bằng rule tường minh, chưa cần machine learning.

### 13.5. Workflow phê duyệt chi phí

Input:
- Amount.
- Department.
- Request type.
- Approver role.

Output:
- Approval path.
- Required approvals.
- Terminal status.

Phù hợp với state transition nhưng cần giới hạn số trạng thái.

### 13.6. Policy truy cập tài nguyên

Input:
- Principal role.
- Resource type.
- Action.
- Context.

Output:
- Allow/deny.
- Reason.

Miền này có giá trị nhưng cần chú ý security semantics và default deny.

## 14. Các miền thường quá lớn cho dự án đầu tiên

### 14.1. ERP tổng thể

ERP chứa nhiều bounded context và workflow liên kết. Có thể chọn một phần như quy tắc duyệt mua hàng.

### 14.2. Banking core

Giao dịch, ledger, compliance, fraud và settlement có yêu cầu cao. Có thể chọn một policy minh họa với dữ liệu giả lập, không triển khai nghiệp vụ thật.

### 14.3. Healthcare record platform

Dữ liệu nhạy cảm và semantics lâm sàng phức tạp. Có thể chọn rule kiểm tra tính đầy đủ của một biểu mẫu giả lập nếu có domain review.

### 14.4. General automation language

Một ngôn ngữ làm mọi thứ dễ trở thành general-purpose language. Nên chọn một loại automation cụ thể như routing ticket hoặc phê duyệt workflow.

### 14.5. AI policy cho mọi trường hợp

"AI quyết định tất cả" không có input/output và oracle rõ. Hãy chọn một decision nhỏ có thể đánh giá được.

## 15. Viết project brief cho miền đã chọn

### 15.1. Problem statement

Mô tả:
- Ai gặp vấn đề?
- Công việc nào đang khó?
- Tại sao cách hiện tại chưa tốt?
- Kết quả mong muốn là gì?

### 15.2. Domain boundary

Ghi rõ context, actor, entity, rule và dependency.

### 15.3. Glossary

Đưa các thuật ngữ và định nghĩa được domain expert xác nhận.

### 15.4. Rule catalog

Liệt kê rule ID, condition, result, priority và source of truth.

### 15.5. Input/output schema

Định nghĩa field, type, required, nullability, unit và error.

### 15.6. Example set

Chuẩn bị:
- Happy path.
- Boundary.
- Invalid input.
- No-match.
- Conflict.
- Exception.

### 15.7. Scope và non-goals

Nêu in-scope, out-of-scope và dependency được mô phỏng.

### 15.8. Success criteria

Ví dụ:
- Domain expert đọc được rule.
- Compiler phát hiện field sai.
- Runtime trả quyết định xác định.
- Mỗi quyết định có reason code.
- Bộ test bao phủ rule và boundary.
- Có thể thêm rule mới mà không sửa runtime core.

## 16. Ví dụ hoàn chỉnh: chọn miền miễn phí vận chuyển

### 16.1. Vấn đề

Nhân viên vận hành phải kiểm tra nhiều điều kiện để xác định đơn hàng có được miễn phí vận chuyển. Quy tắc được lưu trong bảng và thường khó biết rule nào quyết định kết quả.

### 16.2. Người dùng

- Operations analyst viết policy.
- Developer tích hợp runtime.
- Support staff đọc reason code.
- Domain owner xác nhận điều kiện.

### 16.3. Vocabulary

- Order.
- CustomerTier.
- Region.
- BulkyItem.
- ShippingFee.
- FreeShippingEligibility.

### 16.4. Input

~~~text
OrderInput {
    orderTotal: Money
    customerTier: CustomerTier
    region: RegionCode
    containsBulkyItem: Boolean
}
~~~

### 16.5. Output

~~~text
ShippingDecision {
    eligible: Boolean
    fee: Money
    reasons: List<ReasonCode>
}
~~~

### 16.6. Rule mẫu

~~~text
rule FreeShippingByTotal {
    when order.orderTotal >= 1000000 VND
      and not order.containsBulkyItem
    then shippingFee = Money.zero(VND)
}

rule PremiumShippingBenefit {
    when order.customerTier == PREMIUM
      and not order.containsBulkyItem
    then shippingFee = Money.zero(VND)
}

rule BulkySurcharge {
    when order.containsBulkyItem
    then shippingFee = 50000 VND
}
~~~

Ví dụ này còn cần policy resolver nếu nhiều rule cùng khớp. Người sở hữu nghiệp vụ phải xác nhận ưu tiên và cách cộng phí.

### 16.7. Out-of-scope

Dự án không:
- Gọi hãng vận chuyển.
- Tạo nhãn giao hàng.
- Thanh toán phí.
- Quản lý kho.
- Cập nhật đơn hàng production.

### 16.8. Success criteria

Một analyst có thể viết policy; compiler kiểm tra kiểu và tên field; runtime đánh giá input; kết quả có fee và reason; test xác nhận các ngưỡng và xung đột.

## 17. Kiểm tra miền trước khi khóa scope

### 17.1. Domain walkthrough

Mời domain expert đi qua các ví dụ và yêu cầu họ giải thích từng quyết định. Ghi lại nơi họ không đồng thuận.

### 17.2. Counterexample

Hỏi: "Có trường hợp nào dữ liệu giống thế này nhưng kết quả phải khác không?" Câu hỏi này giúp tìm thuộc tính còn thiếu hoặc ranh giới chưa rõ.

### 17.3. Rule conflict workshop

Đặt hai hoặc nhiều điều kiện cùng đúng. Xác định resolver và lý do nghiệp vụ.

### 17.4. Missing data workshop

Thảo luận field thiếu, null, default và dữ liệu stale. Không tự giả định missing bằng false hoặc zero.

### 17.5. Boundary workshop

Xác định ngưỡng, ngày hiệu lực, timezone, đơn vị và precision.

### 17.6. Feasibility prototype

Viết một rule từ đầu đến cuối. Nếu cần nhiều workaround hoặc dependency ngoài, đánh giá lại miền.

### 17.7. Scope freeze

Khi brief được xác nhận, ghi version và người phê duyệt. Yêu cầu mới đi qua change process.

## 18. Những sai lầm thường gặp

### 18.1. Chọn miền vì nghe thú vị

Một ý tưởng hấp dẫn nhưng không có người dùng, quy tắc hoặc dữ liệu sẽ khó hoàn thành. Bắt đầu từ vấn đề có thật.

### 18.2. Chọn toàn bộ một ngành

Một ngành không phải một bounded context. Thu hẹp về một quyết định hoặc quy trình cụ thể.

### 18.3. Bỏ qua domain expert

Developer có thể hiểu cấu trúc dữ liệu nhưng không biết ngoại lệ nghiệp vụ. Cần người xác nhận semantics.

### 18.4. Viết cú pháp trước khi hiểu miền

Nếu bắt đầu từ grammar, nhóm dễ ép nghiệp vụ vào cú pháp đã nghĩ sẵn. Hãy hiểu vocabulary và rule trước.

### 18.5. Không xác định output

Nếu không biết DSL phải trả gì, khó định nghĩa type system, runtime và test.

### 18.6. Không xác định default và no-match

Một tập rule không khớp cần kết quả có chủ đích. Không nên vô tình cho phép thao tác.

### 18.7. Đưa side effect vào quá sớm

Gửi email hoặc cập nhật production làm dự án phức tạp. Bắt đầu bằng decision output và command mô phỏng.

### 18.8. Dùng dữ liệu thật không cần thiết

Dữ liệu nhạy cảm làm tăng rủi ro và chi phí. Dùng synthetic hoặc anonymized fixture.

### 18.9. Không có success criteria

Không có tiêu chí thành công thì nhóm dễ tiếp tục thêm tính năng mà không biết dự án đã hoàn thành chưa.

### 18.10. Scope creep

Mỗi yêu cầu mới có vẻ nhỏ nhưng tổng thể có thể biến dự án thành một platform lớn. Ghi nhận và đánh giá thay đổi trước khi nhận.

## 19. Quy trình chọn miền nhỏ

Một quy trình thực tế có thể gồm:
1. **Thu thập vấn đề:** phỏng vấn người dùng và quan sát công việc lặp lại.
2. **Đưa ra candidate domain:** liệt kê vài phạm vi cụ thể.
3. **Xác định bounded context:** chọn một vocabulary và mục tiêu thống nhất.
4. **Xác định người dùng:** ai viết, đọc, review và vận hành DSL.
5. **Lập glossary:** định nghĩa entity, value object, trạng thái và thuật ngữ.
6. **Lập rule catalog:** điều kiện, kết quả, priority và ngoại lệ.
7. **Định nghĩa input/output:** schema, type, nullability, unit và error.
8. **Vẽ scope boundary:** in-scope, out-of-scope và external dependency.
9. **Thu thập ví dụ:** normal, boundary, invalid, conflict và no-match.
10. **Chấm tính khả thi:** dữ liệu, kiểm chứng, thời gian, kỹ năng và rủi ro.
11. **Làm vertical slice:** một source DSL chạy đến kết quả.
12. **Viết project brief:** problem, scope, rules, schema và success criteria.
13. **Xác nhận với domain owner:** chốt semantics và phạm vi.
14. **Quản lý thay đổi:** mọi mở rộng scope có review.

## 20. Câu hỏi tự đánh giá

1. Domain và bounded context khác nhau như thế nào?
2. Vì sao dự án DSL nên bắt đầu bằng một miền nhỏ?
3. Những dấu hiệu nào cho thấy miền phù hợp với DSL?
4. Khi nào một cấu hình hoặc hàm thông thường đủ tốt hơn DSL?
5. Domain expert đóng vai trò gì trong việc chọn miền?
6. Vì sao cần glossary trước khi thiết kế syntax?
7. Entity, value object và relationship giúp xác định data model ra sao?
8. Decision table giúp tìm rule conflict như thế nào?
9. In-scope và out-of-scope giúp kiểm soát scope creep ra sao?
10. Làm thế nào đánh giá khả năng kiểm chứng của một miền?
11. Một project brief cần chứa những phần nào?
12. Vì sao cần thử một vertical slice trước khi mở rộng?
13. Những miền nào thường quá rộng cho dự án đầu tiên?
14. Làm thế nào xác định success criteria có thể đo được?

## Kết luận

Chọn một miền nhỏ là bước nền tảng của dự án DSL thực hành. Miền cần có vấn đề cụ thể, người dùng nhận diện được, vocabulary nhất quán, rule lặp lại, input/output rõ và cách xác minh kết quả. Ranh giới bounded context giúp nhóm tránh gộp những khái niệm có semantics khác nhau, còn project brief xác định điều gì nằm trong và ngoài phạm vi.

Quy trình hiệu quả bắt đầu bằng quan sát công việc và trao đổi với domain expert, sau đó lập glossary, rule catalog, schema, decision table và tập ví dụ. Nhóm đánh giá tính khả thi bằng dữ liệu, độ phức tạp, dependency và một vertical slice nhỏ trước khi khóa scope. Khi miền được chọn đúng, DSL có thể giải quyết một vấn đề thực tế, thể hiện rõ giá trị của ngôn ngữ chuyên biệt và tạo nền tảng có thể mở rộng khi có nhu cầu được chứng minh.
