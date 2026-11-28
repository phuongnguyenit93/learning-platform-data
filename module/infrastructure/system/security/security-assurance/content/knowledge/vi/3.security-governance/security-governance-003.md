# Hội đồng bảo mật (Security Steering Committee)

## 1. Hội đồng bảo mật là gì?

**Hội đồng bảo mật** (Security Steering Committee, đôi khi gọi là *Information Security Committee* hoặc *Cybersecurity Steering Committee*) là cơ chế **quản trị và điều phối liên chức năng** để tổ chức định hướng, giám sát và đưa ra quyết định về những vấn đề an ninh thông tin ảnh hưởng nhiều bộ phận hoặc vượt quá quyền của một nhóm kỹ thuật.

Thành viên có thể là đại diện kinh doanh, công nghệ, an ninh thông tin, quản trị rủi ro, pháp chế và các bộ phận liên quan. Tùy quy mô, hội đồng có thể hoạt động độc lập hoặc là tiểu ban của một cơ chế quản trị rủi ro hiện hữu. Tên gọi và cơ cấu có thể khác nhau, nhưng cần làm rõ **ai có quyền quyết định, ai chịu trách nhiệm và bằng chứng nào hỗ trợ quyết định**.

Trong chương **Quản trị bảo mật** của module **SECURITY_SECURITY_ASSURANCE**, hội đồng là cầu nối giữa:

- **Mục tiêu kinh doanh và mức chấp nhận rủi ro:** điều gì cần bảo vệ, hậu quả nào tổ chức có thể hoặc không thể chấp nhận.
- **Yêu cầu bảo mật và security controls:** các quy tắc và biện pháp như phân quyền, bảo vệ dữ liệu, quản lý bí mật, giám sát, phục hồi.
- **Security assurance:** bằng chứng từ phân tích rủi ro, rà soát kiến trúc, kiểm thử, audit và vận hành cho thấy control có đáp ứng mục tiêu hay chưa.
- **Quyết định và khắc phục:** xử lý phát hiện, điều phối nguồn lực, chấp thuận ngoại lệ khi có thẩm quyền, chuyển cấp rủi ro vượt ngưỡng và kiểm tra lại kết quả.

Ví dụ: một API chuẩn bị phát hành nhưng kết quả kiểm thử cho thấy người dùng có thể xem dữ liệu của tài khoản khác. Đội kỹ thuật tìm nguyên nhân và phương án sửa; CISO đánh giá rủi ro và chất lượng bằng chứng; chủ sản phẩm cân nhắc tác động kinh doanh. Hội đồng bảo mật giúp các bên sử dụng **cùng một bộ thông tin**, xác định hành động và chuyển quyết định đến đúng người có thẩm quyền.

> Hội đồng bảo mật không phải đội SOC, nhóm kiểm thử xâm nhập hay đơn vị trực tiếp vá lỗi. Hội đồng quản trị quyết định và theo dõi; các nhóm chuyên môn triển khai, kiểm chứng và vận hành control.

## 2. Vì sao tổ chức cần hội đồng bảo mật?

Một quyết định bảo mật có thể ảnh hưởng đồng thời đến bảo vệ dữ liệu, thời điểm phát hành, chi phí, trải nghiệm người dùng, tính sẵn sàng và nghĩa vụ tuân thủ. Khi mỗi nhóm tối ưu mục tiêu riêng, có thể phát sinh các vấn đề:

1. Nhóm sản phẩm muốn triển khai đúng lịch, trong khi một lỗ hổng nghiêm trọng chưa có chủ sở hữu và phương án xử lý.
2. Một security control đã được cài đặt, nhưng chưa ai kiểm chứng nó hoạt động đúng với hệ thống và phiên bản thực tế.
3. Một ticket ghi “chấp nhận rủi ro” dù không có risk owner đủ quyền phê duyệt.
4. Phát hiện từ audit tồn đọng nhiều kỳ vì các phòng ban chưa thống nhất ngân sách và thứ tự ưu tiên.
5. Các bộ phận dùng tiêu chí đánh giá, thời hạn xử lý và cách báo cáo rủi ro không thống nhất.

Hội đồng tạo một nơi **điều phối các quyết định vượt ranh giới chức năng**. Những lợi ích trực tiếp gồm:

| Lợi ích | Hội đồng tạo ra bằng cách nào? | Dấu hiệu kiểm chứng |
| --- | --- | --- |
| Gắn bảo mật với mục tiêu kinh doanh | Xem tác động, ưu tiên và ngưỡng chấp nhận rủi ro trong cùng cuộc thảo luận | Quyết định gắn với mục tiêu, mức rủi ro và người chịu trách nhiệm |
| Minh bạch trách nhiệm | Phân biệt risk owner, control owner, người thực hiện và người phê duyệt | Ma trận trách nhiệm và nhật ký quyết định |
| Tăng giá trị security assurance | Đòi hỏi bằng chứng cho các claim trọng yếu trước khi kết luận | Hồ sơ yêu cầu–control–bằng chứng–phát hiện |
| Giảm tồn đọng liên phòng ban | Gỡ các vướng mắc về nguồn lực, ưu tiên và quyền hạn | Hành động có hạn xử lý và kiểm tra lại |
| Hỗ trợ audit và giải trình | Lưu quyết định, ngoại lệ, lý do và rủi ro còn lại | Biên bản, risk register và báo cáo kiểm chứng |
| Cải tiến liên tục | Đưa bài học từ sự cố, kiểm thử và audit vào chính sách và kế hoạch | Giảm lỗi tái diễn, cập nhật control và quy trình |

Số buổi họp hoặc số văn bản phát hành **không phải** thước đo trực tiếp của hiệu quả bảo mật. Giá trị thực tế là quyết định có căn cứ và kết quả đã được kiểm chứng.

## 3. Nhiệm vụ và phạm vi quyền hạn

### 3.1. Định hướng chiến lược và chính sách

Hội đồng có thể:

- Xem xét hoặc kiến nghị chiến lược bảo mật gắn với mục tiêu kinh doanh.
- Thảo luận chính sách, tiêu chuẩn và baseline bảo mật dùng chung.
- Xác định ưu tiên cho những chương trình như quản lý danh tính, giám sát, bảo vệ dữ liệu, an ninh ứng dụng và chuỗi cung ứng phần mềm.
- Đề xuất hoặc phân bổ nguồn lực trong giới hạn được ủy quyền.
- Theo dõi mức trưởng thành của các năng lực bảo mật và nhu cầu cải tiến.

**Thẩm quyền phải được ghi trong điều lệ.** Một hội đồng có thể được quyền phê duyệt một chính sách nội bộ nhưng chỉ được kiến nghị khoản ngân sách lớn lên ban lãnh đạo.

### 3.2. Giám sát rủi ro

Hội đồng theo dõi các rủi ro quan trọng, tác động kinh doanh, khả năng khai thác, mức rủi ro còn lại sau kiểm soát và tiến độ xử lý. Những việc thường gặp:

- Đặt yêu cầu trình bày rủi ro theo cách thống nhất giữa các sản phẩm.
- Kiểm tra từng rủi ro có **risk owner** và phương án xử lý.
- Giám sát ngoại lệ, kiểm soát bù trừ, thời hạn hiệu lực và kế hoạch khắc phục.
- Chuyển cấp các trường hợp vượt mức chấp nhận rủi ro hoặc thẩm quyền.
- Điều phối khi các biện pháp giảm rủi ro đòi hỏi nhiều đội cùng tham gia.

**Risk owner** là người có trách nhiệm đối với tác động và phương án xử lý rủi ro trong phạm vi được giao. CISO có thể cung cấp ý kiến chuyên môn, cảnh báo và bằng chứng đánh giá; điều đó không mặc định khiến CISO chịu trách nhiệm cuối cùng cho mọi rủi ro kinh doanh. Hội đồng cũng không mặc định có quyền chấp nhận mọi loại rủi ro.

### 3.3. Giám sát security controls và security assurance

Security assurance có nhiệm vụ xây dựng **niềm tin có bằng chứng** rằng hệ thống đáp ứng các yêu cầu bảo mật trong phạm vi được đánh giá. Hội đồng có thể yêu cầu:

- Truy vết từ rủi ro đến yêu cầu, control, kiểm thử, kết quả và hành động khắc phục.
- Có tiêu chí kiểm chứng rõ ràng cho những control trọng yếu.
- Kết quả rà soát thiết kế, phân tích phụ thuộc, kiểm thử phân quyền, pentest, audit hoặc kiểm tra cấu hình khi phù hợp.
- Đánh giá tính **phù hợp, đầy đủ, đáng tin và còn hiệu lực** của bằng chứng.
- Ghi rõ những điểm chưa được chứng minh; không xem “chưa tìm thấy lỗi” là bằng chứng an toàn tuyệt đối.
- Chỉ đóng phát hiện khi có xác minh bản sửa hoặc kết quả xử lý phù hợp đã được chấp nhận theo quy định.

Hội đồng không trực tiếp thay thế người đánh giá chuyên môn. Hội đồng sử dụng kết luận đánh giá, đặt câu hỏi về giới hạn và chuyển chúng thành quyết định quản trị.

### 3.4. Giám sát sự cố và khả năng phục hồi

Hội đồng có thể xem xu hướng sự cố, bài học từ điều tra, kết quả diễn tập và đầu tư phòng ngừa. Trong **sự cố đang xảy ra**, đội ứng cứu hoặc người chỉ huy sự cố được chỉ định phải hành động theo kế hoạch ứng cứu. Không được trì hoãn việc cô lập, điều tra hay khôi phục chỉ vì chưa đến lịch họp hội đồng.

Sau sự cố, hội đồng có thể yêu cầu sửa control, thay đổi chính sách, bổ sung giám sát hoặc xử lý nguyên nhân gốc ở cấp nhiều bộ phận.

## 4. Thành phần và phân vai

Hội đồng cần đủ đại diện để đưa ra quyết định khả thi, nhưng không nhất thiết càng đông càng tốt.

| Vai trò | Đóng góp chính | Giới hạn cần làm rõ |
| --- | --- | --- |
| **Chủ tịch** (lãnh đạo được ủy quyền) | Điều phối, kết luận, bảo đảm chuyển cấp và theo dõi hành động | Chỉ phê duyệt trong phạm vi điều lệ |
| **CISO / phụ trách an ninh thông tin** | Cung cấp bức tranh rủi ro, yêu cầu control và đánh giá bằng chứng assurance | Cần nêu được ý kiến chuyên môn độc lập khi có bất đồng |
| **Chủ sản phẩm / đại diện kinh doanh** | Xác định giá trị, tác động kinh doanh và phương án xử lý rủi ro | Có thể giữ vai trò risk owner của sản phẩm |
| **CTO / kiến trúc / phát triển** | Phân tích giải pháp, công sức sửa, khả năng thay đổi thiết kế | Triển khai hoặc điều phối triển khai kỹ thuật |
| **Vận hành / SRE / hạ tầng** | Cung cấp trạng thái thực tế, cấu hình, nhật ký, tính sẵn sàng, khôi phục | Phải đánh giá tác động lên môi trường chạy |
| **Quản trị rủi ro, pháp chế, bảo vệ dữ liệu, compliance** | Giải thích mức rủi ro, nghĩa vụ và điều kiện ngoại lệ | Tham gia theo mức độ liên quan của vấn đề |
| **Thư ký/điều phối hội đồng** | Tổng hợp hồ sơ, ghi quyết định, giám sát lịch và đầu mối | Bảo đảm tài liệu được truy vết và bảo vệ phù hợp |
| **Kiểm toán nội bộ hoặc đánh giá độc lập** (nếu có) | Cung cấp phát hiện và quan sát độc lập | Thường cần giới hạn quyền phê duyệt để giữ tính độc lập |

Trong doanh nghiệp nhỏ, một người có thể đảm nhiệm nhiều vai trò. Khi có xung đột lợi ích (ví dụ cùng một người triển khai và đánh giá control trọng yếu), tổ chức nên có cơ chế rà soát chéo hoặc đánh giá độc lập tương xứng rủi ro.

### 4.1. Khác biệt với các nhóm khác

| Đơn vị | Mục đích chính | Hoạt động điển hình |
| --- | --- | --- |
| Hội đồng bảo mật | Quản trị và điều phối ưu tiên, quyền hạn, rủi ro | Xem bằng chứng, giao trách nhiệm, quyết định/chuyển cấp |
| CISO và nhóm bảo mật | Chuyên môn an ninh, tư vấn, xác minh control | Đánh giá rủi ro, rà soát thiết kế, kiểm thử, kiến nghị |
| Nhóm phát triển/vận hành | Xây dựng và duy trì sản phẩm | Triển khai control, sửa lỗi, vận hành và thu thập bằng chứng |
| Đội ứng cứu sự cố | Xử lý sự cố theo thời gian thực | Phát hiện, cô lập, điều tra, khôi phục |
| Quản trị rủi ro doanh nghiệp / ban lãnh đạo | Chịu trách nhiệm quản lý rủi ro ở cấp được giao | Phê duyệt rủi ro vượt ngưỡng, ngân sách hoặc ưu tiên lớn |
| Kiểm toán nội bộ | Đánh giá độc lập thiết kế và hiệu lực kiểm soát | Thực hiện audit, báo cáo phát hiện, theo dõi kiến nghị |

Hội đồng **không nên tự xem mình là nguồn bảo đảm độc lập** đối với những control do chính thành viên của hội đồng quản lý và triển khai.

## 5. Điều lệ (committee charter) làm rõ thực quyền

Một hội đồng hoạt động cần một **điều lệ** quy định ít nhất:

1. **Mục đích và phạm vi:** bao phủ doanh nghiệp, đơn vị, nền tảng hay chương trình nào?
2. **Quyền hạn:** được phê duyệt điều gì, chỉ được kiến nghị điều gì và phải chuyển cấp điều gì?
3. **Cơ cấu:** thành viên chính thức, người chủ trì, người có quyền quyết định, chuyên gia tư vấn và thư ký.
4. **Lịch và triệu tập:** tần suất định kỳ, cuộc họp đột xuất, cách xử lý quyết định khẩn cấp.
5. **Quorum và cách quyết định:** điều kiện đủ thành viên, cách ghi ý kiến khác biệt và xử lý xung đột.
6. **Trách nhiệm:** risk owner, control owner, action owner, người kiểm chứng và người phê duyệt.
7. **Nguyên tắc chuyển cấp:** mức rủi ro, tác động, ngân sách hoặc nghĩa vụ vượt thẩm quyền.
8. **Hồ sơ:** mẫu tài liệu, biên bản, quyền truy cập, thời hạn và cách lưu giữ.
9. **Đánh giá hiệu quả:** chỉ số và lịch xem xét lại chính điều lệ.

Quorum, ngưỡng rủi ro hay số ngày cần khắc phục **không có một con số đúng cho tất cả tổ chức**. Các ngưỡng này phải dựa trên phân quyền, quy định áp dụng và mức rủi ro đã được phê duyệt.

### 5.1. Ma trận thẩm quyền minh họa

| Vấn đề | Người chuẩn bị hồ sơ | Vai trò hội đồng | Khi nào cần chuyển cấp |
| --- | --- | --- | --- |
| Chuẩn kiểm soát dùng chung | CISO và chuyên gia kỹ thuật | Xem xét, phê duyệt nếu được ủy quyền | Thay đổi ngoài ngân sách hoặc phạm vi chính sách |
| Khắc phục phát hiện trọng yếu | Control owner, risk owner | Ưu tiên và theo dõi cam kết | Thiếu nguồn lực, quá hạn hoặc vượt mức chấp nhận |
| Xin ngoại lệ có thời hạn | Risk owner, CISO, pháp chế (nếu cần) | Kiểm tra bằng chứng và điều kiện; quyết định trong quyền hạn | Rủi ro hoặc nghĩa vụ vượt quyền |
| Phát hành khi còn rủi ro | Chủ sản phẩm, kỹ thuật, CISO | Đánh giá và quyết định hoặc kiến nghị theo charter | Quyền chấp nhận rủi ro thuộc cấp khác |
| Phát hiện audit lặp lại | Chủ sở hữu control, quản trị rủi ro | Yêu cầu xử lý nguyên nhân gốc, giám sát tiến độ | Vấn đề hệ thống hoặc không đủ nguồn lực |

**Lưu ý:** một cuộc biểu quyết không thể tự hợp thức hóa ngoại lệ trái nghĩa vụ pháp lý hoặc vượt quyền phê duyệt. Nếu không có căn cứ để chấp nhận, phải khắc phục, giảm phạm vi hoặc điều chỉnh kế hoạch.

## 6. Chu trình làm việc gắn với bằng chứng assurance

~~~mermaid
flowchart TD
    A["Rủi ro và yêu cầu bảo mật"] --> B["Thiết kế, triển khai security controls"]
    B --> C["Đánh giá: kiểm thử, review, audit, bằng chứng vận hành"]
    C --> D["CISO/quản trị rủi ro tổng hợp kết luận và giới hạn"]
    D --> E["Hội đồng đánh giá phương án và thẩm quyền"]
    E --> F{"Đủ bằng chứng và đúng thẩm quyền?"}
    F -- "Thiếu bằng chứng" --> G["Yêu cầu bổ sung hoặc kiểm thử lại"]
    G --> C
    F -- "Vượt thẩm quyền" --> H["Chuyển cấp quyết định"]
    H --> I["Ghi nhận quyết định, căn cứ và điều kiện"]
    F -- "Đủ điều kiện" --> I
    I --> J["Giao chủ sở hữu, hành động và hạn"]
    J --> K["Thực thi, kiểm chứng, cập nhật risk register"]
    K --> D
~~~

### 6.1. Hồ sơ đầu vào của một vấn đề cần quyết định

Trước cuộc họp, tài liệu nên trình bày ngắn gọn:

- Hệ thống, phiên bản, môi trường, dữ liệu và chủ sở hữu liên quan.
- Mục tiêu/yêu cầu bảo mật; các security controls đang được dùng.
- Mô tả rủi ro ban đầu và rủi ro còn lại, tác động kinh doanh, giả định và mức độ chưa chắc chắn.
- Phát hiện đã xác minh; nguồn, thời gian và phạm vi bằng chứng.
- Phương án: sửa, giảm thiểu, hoãn, thay đổi phạm vi, chuyển cấp hoặc chấp nhận rủi ro trong quyền hạn.
- Ý kiến của nhóm kỹ thuật, CISO, risk owner và các bên liên quan; bất đồng nếu có.
- Quyết định cần đưa ra, người có thẩm quyền, thời hạn và đề xuất tiêu chí kiểm chứng.

Bằng chứng cần **đúng phiên bản và phù hợp với claim**. Ví dụ, báo cáo quét dependency không tự chứng minh tính đúng đắn của phân quyền nghiệp vụ.

### 6.2. Chương trình họp định kỳ

| Chủ đề | Câu hỏi hướng tới quyết định |
| --- | --- |
| Hành động kỳ trước | Việc nào hoàn thành, đã xác minh hay đang trễ? |
| Rủi ro mới hoặc thay đổi | Rủi ro nào tăng, giảm và vì sao? |
| Trạng thái control quan trọng | Có bằng chứng còn hiệu lực trên môi trường phù hợp không? |
| Phát hiện từ audit, pentest, kiểm thử | Vấn đề nào cần phối hợp nhiều phòng ban? |
| Ngoại lệ và rủi ro còn lại | Ai có thẩm quyền; có thời hạn và biện pháp bù trừ không? |
| Đầu tư và ưu tiên | Có cần điều chỉnh nguồn lực hay kế hoạch phát hành không? |
| Quyết định cần chuyển cấp | Nội dung nào vượt thẩm quyền hội đồng? |

Tùy rủi ro và quy mô, hội đồng có thể họp hằng tháng hoặc hằng quý, có phiên bất thường khi cần. Các nhóm chuyên môn vẫn có thể xử lý lỗ hổng, kiểm tra và ứng cứu thường xuyên hơn nhịp họp hội đồng.

### 6.3. Đầu ra một quyết định có thể kiểm toán

Một quyết định cần ít nhất:

1. **Nội dung:** phương án đã chọn và phạm vi tác dụng.
2. **Căn cứ:** bằng chứng nào được xem, giới hạn nào vẫn còn.
3. **Thẩm quyền:** cá nhân/vai trò phê duyệt và cơ sở phân quyền.
4. **Trách nhiệm:** risk owner và action owner là ai.
5. **Điều kiện, thời hạn:** bao gồm biện pháp bù trừ, thời điểm hết hiệu lực ngoại lệ.
6. **Tiêu chí đóng:** kiểm thử hoặc đánh giá nào phải thành công để coi là đã khắc phục.
7. **Theo dõi:** hạn báo cáo lại và dấu hiệu cần chuyển cấp ngay.

Một bản sửa mã nguồn được triển khai **chưa đồng nghĩa** một phát hiện đã được đóng: cần xác minh hành vi trên phiên bản/môi trường thích hợp.

## 7. Ví dụ: Java/Spring Boot gặp lỗi phân quyền trước khi ra mắt

Một API xuất dữ liệu khách hàng sử dụng **Java/Spring Boot** chuẩn bị triển khai. Kiểm thử tích hợp phát hiện rằng người dùng A chỉ cần thay đổi mã khách hàng trong URL để xem dữ liệu của B, dù đã đăng nhập hợp lệ. Đây là trường hợp **broken object-level authorization** (lỗ hổng phân quyền cấp đối tượng).

### 7.1. Hồ sơ trình hội đồng

| Thành phần | Dữ liệu cần cung cấp |
| --- | --- |
| Tài sản | Hồ sơ và dữ liệu xuất của khách hàng |
| Mục tiêu bảo mật | Chỉ tài khoản có quyền trên tài nguyên mới được truy xuất |
| Phát hiện | Test A/B cho thấy truy cập chéo ngoài ý muốn |
| Bằng chứng | ID test run, phiên bản build, thời điểm, kết quả API đã che dữ liệu nhạy cảm |
| Nguyên nhân dự kiến | Có xác thực nhưng thiếu xác minh quyền sở hữu tài nguyên |
| Tác động | Nguy cơ lộ dữ liệu và vi phạm cam kết bảo mật |
| Phương án A | Bổ sung kiểm tra quyền và chạy kiểm thử hồi quy trước phát hành |
| Phương án B | Tạm vô hiệu hóa endpoint xuất dữ liệu bị ảnh hưởng |
| Phương án C | Hoãn phạm vi phát hành nếu rủi ro không thể giảm đến ngưỡng cho phép |
| Trách nhiệm | Chủ sản phẩm/risk owner, kỹ thuật, CISO, người có quyền phê duyệt phát hành |

Hội đồng cần xem xét tác động, độ tin cậy của bằng chứng, phương án và thời gian xử lý. Hội đồng **không thể coi lỗi đã an toàn** chỉ vì có lời hứa sửa sau phát hành.

Giả sử hội đồng có quyền điều phối ưu tiên nhưng **không có quyền chấp nhận rủi ro lộ dữ liệu nghiêm trọng**, hội đồng có thể:

1. Kiến nghị vô hiệu hóa endpoint hoặc hoãn phần tính năng bị ảnh hưởng.
2. Giao nhóm phát triển sửa kiểm tra phân quyền tại tầng nghiệp vụ/dữ liệu.
3. Yêu cầu kiểm thử phủ nhiều tài khoản, role, endpoint và trường hợp bị từ chối.
4. Giao nhóm an ninh thông tin kiểm tra lại kết quả, hoặc bổ sung rà soát độc lập nếu rủi ro cao.
5. Chuyển quyết định thay đổi phạm vi phát hành cho cấp có thẩm quyền kèm hồ sơ và các phương án.

Luồng tạo assurance có thể truy vết: **rủi ro → yêu cầu → control → phát hiện → quyết định → khắc phục → xác minh → cập nhật kết luận**.

### 7.2. Mẫu bản ghi quyết định (hoàn toàn giả định)

~~~yaml
decision_id: "SEC-GOV-DEMO-001"
title: "Phat hanh API xuat du lieu khach hang"
system: "customer-export-api"
risk_owner: "Chu so huu san pham"
action_owner: "Nhom phat trien API"
security_reviewer: "Nhom an ninh thong tin"
security_claim: "Chi nguoi co quyen moi truy cap du lieu"
finding:
  type: "Broken object-level authorization"
  evidence_ref: "TEST-DEMO-ACCESS-017"
  affected_version: "Ban build truoc phat hanh"
  status: "OPEN"
decision:
  outcome: "Tam vo hieu hoa endpoint bi anh huong"
  basis: "Kiem thu cho thay truy cap cheo tai khoan"
  authority: "Cap phe duyet theo quy che to chuc"
  condition: "Chi mo lai sau khi sua va kiem thu lai dat"
verification:
  required: "User A khong xem duoc tai nguyen User B"
  evidence_ref: "CHUA_CO"
  status: "PENDING"
follow_up: "Tai danh gia khi co ket qua kiem thu tren ban sua"
~~~

Đây là **mẫu cấu trúc**, không phải kết quả kiểm thử có thật. Hồ sơ thực tế cần có người phê duyệt, ngày giờ, phiên bản, môi trường, liên kết ticket và test run, thời hạn và nơi lưu được phân quyền. Trạng thái **PENDING** cho biết chưa có bằng chứng hoàn tất xác minh.

## 8. Dùng RACI để làm rõ trách nhiệm

**RACI** là cách thể hiện ai thực hiện (*Responsible*), ai chịu trách nhiệm cuối cùng (*Accountable*), ai được tham vấn (*Consulted*) và ai được thông báo (*Informed*).

| Hoạt động | Hội đồng | CISO / security | Chủ sản phẩm / risk owner | Kỹ thuật / vận hành | Kiểm toán độc lập |
| --- | --- | --- | --- | --- | --- |
| Định hướng ưu tiên bảo mật trong phạm vi hội đồng | A | R | C | C | I |
| Đánh giá hiệu quả control | I | A/R | C | C | C |
| Triển khai bản sửa lỗ hổng | I | C | A | R | I |
| Xác minh bản sửa | I | A/R | C | C | C |
| Chấp nhận rủi ro trong thẩm quyền của risk owner | C | C | A/R | C | I |
| Theo dõi phát hiện trọng yếu liên phòng ban | A | R | R | R | I |

Đây là **ma trận minh họa**, không phải quy tắc bắt buộc. Trong thực tế, ô **A** phải tương ứng với người có thẩm quyền thật, thường là một chủ thể chịu trách nhiệm cuối cùng cho mỗi quyết định. Nếu rủi ro thuộc quyền cấp lãnh đạo khác, ma trận phải thay đổi để thể hiện đúng thẩm quyền đó.

## 9. Đo hiệu quả hội đồng theo kết quả

| Chỉ số tham khảo | Đo điều gì? | Cẩn trọng khi diễn giải |
| --- | --- | --- |
| Tỷ lệ quyết định có đầy đủ chủ sở hữu, hạn và điều kiện | Khả năng truy vết và tổ chức thực hiện | Có biểu mẫu chưa có nghĩa hành động hiệu quả |
| Tỷ lệ hành động đến hạn đã **xác minh hoàn tất** | Khả năng biến quyết định thành kết quả | Không tính ticket đóng mà thiếu kiểm thử lại |
| Thời gian tồn tại của phát hiện trọng yếu | Rủi ro kéo dài và tắc nghẽn nguồn lực | Phải xem cùng mức phơi nhiễm và biện pháp bù trừ |
| Tỷ lệ ngoại lệ hết hạn chưa tái đánh giá | Khả năng kiểm soát chấp nhận rủi ro | Không xem ngoại lệ “đang gia hạn” như quyết định hợp lệ |
| Tỷ lệ control quan trọng có bằng chứng phù hợp | Năng lực đưa ra kết luận dựa trên assurance | Bằng chứng cũ hoặc sai phiên bản không được tính |
| Tỷ lệ vấn đề được chuyển cấp đúng hạn | Đường chuyển cấp có hoạt động không? | Không nâng cấp mọi vấn đề nhỏ một cách máy móc |
| Tỷ lệ phát hiện tái diễn | Hiệu quả sửa nguyên nhân gốc | Chịu ảnh hưởng bởi phạm vi và chất lượng kiểm thử |

Ví dụ giả định: có **12** hành động đến hạn; **9** hành động đã được xác minh, **2** hành động báo hoàn thành nhưng chưa kiểm thử lại và **1** hành động quá hạn. Tỷ lệ hoàn tất có xác minh là **9/12 = 75%**, không phải 11/12. Con số này đo trạng thái xử lý, **không có nghĩa hệ thống an toàn 75%**.

### 9.1. Dấu hiệu hội đồng hoạt động hình thức

- Biên bản chỉ ghi “đã thảo luận” mà không có quyết định, chủ sở hữu hoặc hạn.
- Ngoại lệ bảo mật được ghi nhận nhưng thiếu thẩm quyền phê duyệt hoặc thời điểm hết hạn.
- Báo cáo chỉ có nhãn xanh/đỏ, thiếu bằng chứng, phạm vi, xu hướng và giả định.
- Phát hiện lặp lại qua nhiều kỳ nhưng không có hành động xử lý nguyên nhân gốc.
- Người tạo control tự cung cấp kết luận độc lập đối với control rủi ro cao mà không có rà soát phù hợp.
- Kết quả audit, sự cố hoặc kiểm thử không được chuyển thành thay đổi ở chính sách, kiến trúc và quy trình.

Những dấu hiệu đó gợi ý cần sửa mẫu hồ sơ, quyền quyết định, tiêu chí đóng hoặc cơ chế giám sát, thay vì chỉ tăng tần suất họp.

## 10. Bắt đầu triển khai trong một tổ chức nhỏ

Một hội đồng gọn nhưng rõ trách nhiệm thường hiệu quả hơn cấu trúc phức tạp thiếu quyền và bằng chứng. Có thể tiến hành:

1. **Chọn người bảo trợ và chủ trì:** xác định đường báo cáo và quyền hạn.
2. **Viết điều lệ ngắn:** phạm vi, thành viên, cách ra quyết định, điều kiện chuyển cấp, quản lý hồ sơ.
3. **Chọn rủi ro trọng yếu:** tập trung hệ thống chứa dữ liệu nhạy cảm, phơi nhiễm Internet hoặc tác động kinh doanh lớn.
4. **Chuẩn hóa hồ sơ assurance:** cùng một cách thể hiện rủi ro, yêu cầu, control, bằng chứng, phát hiện và đề xuất xử lý.
5. **Chọn nhịp làm việc:** họp định kỳ cho ưu tiên và xu hướng; có kênh nhanh cho vấn đề vượt ngưỡng.
6. **Theo dõi tới kết quả:** mỗi hành động có chủ sở hữu, hạn, bằng chứng kiểm chứng và quyết định kết thúc.
7. **Rà soát hiệu quả:** kiểm tra xem hội đồng có gỡ tắc nghẽn, giảm phát hiện tồn đọng và cải thiện chất lượng quyết định không.

Nếu tổ chức đã có cơ chế quản trị rủi ro doanh nghiệp, kiểm soát thay đổi hoặc đánh giá tuân thủ, cần liên kết báo cáo và chuyển cấp để tránh quyết định bị phân tán hay mâu thuẫn.

## 11. Câu hỏi tự kiểm tra

1. Một công cụ quét trả kết quả “PASS”. Hội đồng cần biết thêm điều gì trước khi kết luận yêu cầu phân quyền của hệ thống đã đạt?
2. Khi CISO cảnh báo rủi ro nhưng chủ sản phẩm muốn phát hành, những vai trò nào có quyền khuyến nghị, xử lý và chấp nhận rủi ro?
3. Khi một phát hiện vượt thẩm quyền, hội đồng có thể hành động thế nào mà không trì hoãn biện pháp giảm thiểu?
4. Vì sao một ngoại lệ bảo mật cần chủ sở hữu, thời hạn, điều kiện bù trừ và lịch tái đánh giá?
5. Hội đồng có nên báo cáo một hành động là hoàn tất khi đã triển khai bản sửa nhưng chưa có bằng chứng kiểm thử lại? Vì sao?

## 12. Ghi nhớ

Hội đồng bảo mật giúp **kết nối mục tiêu kinh doanh, trách nhiệm quản trị rủi ro và bằng chứng security assurance**. Hội đồng hiệu quả khi có điều lệ, thẩm quyền, thành phần và quy trình chuyển cấp rõ ràng; có bằng chứng đáng tin cho kết luận; và giám sát hành động **đến khi được kiểm chứng**. Giá trị nằm ở **quyết định đúng người, đúng quyền và có căn cứ**, không nằm ở số cuộc họp hay số văn bản đã tạo.
