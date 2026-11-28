# NIST Risk Management Framework

## 1. RMF giúp biến rủi ro thành quyết định có căn cứ

NIST Risk Management Framework (RMF) là quy trình quản lý rủi ro gắn với vòng đời hệ thống. Bài học này dùng **NIST SP 800-37 Revision 2** làm tài liệu nền và đặt RMF trong chương **Risk management và compliance** của module **SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS**. RMF kết nối lựa chọn, triển khai, đánh giá biện pháp kiểm soát với quyết định chấp nhận rủi ro và giám sát tiếp diễn. [NIST SP 800-37 Rev. 2](https://csrc.nist.gov/pubs/sp/800/37/r2/final)

Trọng tâm thực hành là chuyển mục tiêu an toàn thông tin và mô hình đe dọa thành yêu cầu bảo mật cụ thể, đo được và kiểm chứng được. Người học sẽ liên kết xác thực, phân quyền, bảo vệ dữ liệu, logging và phục hồi với rủi ro nghiệp vụ, kiến trúc, bằng chứng kiểm thử và người có thẩm quyền quyết định.

Ví dụ, câu “hệ thống phải an toàn theo NIST” chưa giúp kỹ sư biết cần xây gì hoặc giúp người đánh giá biết cần kiểm tra gì. Một chuỗi rõ hơn là:

~~~text
Hồ sơ khách hàng phải được giữ bí mật
  -> Rủi ro người dùng đọc hồ sơ của tenant khác
  -> Yêu cầu phân quyền đối tượng ở backend
  -> Quyết định kiến trúc về tenant context và truy vấn dữ liệu
  -> Kiểm thử với hai tenant, API trực tiếp và luồng export
  -> Bằng chứng trên phiên bản triển khai xác định
  -> Quyết định vận hành và điều kiện giám sát
~~~

Các mã yêu cầu, bảng biểu, ngưỡng thời gian và tình huống trong bài là **ví dụ do dự án giả định đặt ra**. Chúng không phải biểu mẫu bắt buộc của NIST hoặc các giá trị mặc định mà mọi hệ thống phải dùng.

## 2. Phân biệt quy trình, danh mục kiểm soát và yêu cầu sản phẩm

Các tài liệu liên quan phục vụ những mục đích khác nhau:

| Thành phần | Câu hỏi chính | Cách dùng trong đặc tả yêu cầu |
| --- | --- | --- |
| RMF trong SP 800-37 Rev. 2 | Ai làm gì để quản lý rủi ro trong vòng đời hệ thống? | Tổ chức hoạt động, đầu ra và quyết định |
| FIPS 199 | Thiệt hại tiềm tàng khi mất bí mật, toàn vẹn hoặc sẵn sàng là gì? | Cung cấp căn cứ phân loại tác động khi áp dụng mô hình này |
| SP 800-53 Rev. 5 | Có những biện pháp kiểm soát bảo mật và quyền riêng tư nào? | Tra cứu kiểm soát phù hợp và xác định tham số cần cụ thể hóa |
| SP 800-53B | Những baseline nào là điểm xuất phát lựa chọn kiểm soát? | Chọn baseline phù hợp rồi tailoring theo bối cảnh |
| SP 800-53A Rev. 5 | Đánh giá kiểm soát bằng cách nào? | Xây mục tiêu, phương pháp và bằng chứng đánh giá |

FIPS 199 phân loại theo tác động tiềm tàng đối với confidentiality, integrity và availability. SP 800-53 là danh mục kiểm soát; SP 800-53B cung cấp các security baseline theo mức tác động và một privacy baseline không phụ thuộc mức tác động; SP 800-53A cung cấp phương pháp cùng thủ tục đánh giá. Cần ghi rõ phiên bản và các cập nhật được dự án áp dụng. [FIPS 199](https://csrc.nist.gov/pubs/fips/199/final), [SP 800-53 Rev. 5](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final), [SP 800-53B](https://csrc.nist.gov/pubs/sp/800/53/b/upd1/final), [SP 800-53A Rev. 5](https://csrc.nist.gov/pubs/sp/800/53/a/r5/final)

Một kiểm soát trong danh mục thường cần nhiều yêu cầu sản phẩm để triển khai đầy đủ. Ngược lại, một yêu cầu sản phẩm có thể hỗ trợ nhiều kiểm soát. Vì vậy, ghi mã tham chiếu vào ticket chỉ tạo liên kết; phạm vi đáp ứng còn phải được giải thích và chứng minh.

Ví dụ, yêu cầu “ghi log thao tác export” cần nêu người thực hiện, tenant, loại đối tượng, kết quả, thời điểm, nơi lưu và quyền đọc log. Việc chọn một họ kiểm soát về audit chưa trả lời các chi tiết đó.

RMF có thể được sử dụng bởi tổ chức ngoài khu vực liên bang Hoa Kỳ. Khi học hoặc áp dụng trong doanh nghiệp, phải xác định yêu cầu quản trị, hợp đồng và nghĩa vụ thực sự áp dụng cho hệ thống; việc dùng RMF tự nó không tạo ra một chứng nhận sản phẩm do NIST cấp. [NIST RMF: About the framework](https://csrc.nist.gov/Projects/risk-management/about-rmf)

## 3. Các khái niệm cần giữ riêng

| Khái niệm | Ý nghĩa thực hành | Ví dụ trong bài |
| --- | --- | --- |
| Tài sản và mục tiêu | Điều tổ chức cần bảo vệ hoặc duy trì | Hồ sơ đúng chủ thể; quyết định duyệt không bị sửa trái phép |
| Kịch bản rủi ro | Điều kiện, sự kiện và hậu quả có thể xảy ra | Người dùng đổi ID để tải hồ sơ tenant khác do thiếu kiểm tra quyền |
| Kiểm soát | Biện pháp tổ chức hoặc kỹ thuật để xử lý rủi ro | Cưỡng chế quyền truy cập ở lớp dịch vụ |
| Yêu cầu bảo mật | Phát biểu cụ thể về hành vi hoặc thuộc tính cần có | Mọi thao tác đọc, sửa, export phải kiểm tra tenant từ danh tính đã xác thực |
| Bằng chứng | Dữ liệu làm căn cứ đánh giá một tuyên bố | Kết quả test API, cấu hình, bản ghi quyết định quyền và phiên bản build |
| Rủi ro còn lại | Rủi ro sau khi xem xét kiểm soát thực tế và hiệu lực đã được chứng minh | Nhân viên đúng quyền vẫn có thể sử dụng sai dữ liệu đã export |
| Chấp nhận rủi ro | Quyết định quản trị bởi người có thẩm quyền | Cho phép vận hành trong phạm vi xác định kèm điều kiện theo dõi |

Trong cách tổ chức hồ sơ của bài, “đã triển khai”, “đã đánh giá đạt” và “đã được phép vận hành” là ba trạng thái khác nhau. Nhóm kỹ thuật có thể hoàn thành cơ chế phân quyền nhưng chưa đánh giá luồng export; người quyết định cần thấy rõ khoảng trống đó.

Một điểm rủi ro nội bộ cũng không thay bằng chứng. Nếu nhóm dùng thang định tính hoặc ma trận điểm, phải ghi ý nghĩa các mức và giả định. Không chuyển “impact cao” thành một xác suất định lượng tùy ý, hoặc giảm điểm chỉ vì ticket đã đóng.

## 4. Bảy bước và vòng phản hồi

RMF có bảy bước: **Prepare, Categorize, Select, Implement, Assess, Authorize, Monitor**. Việc thực hiện gắn với SDLC và có thể quay lại các bước cần thiết khi bối cảnh thay đổi. [NIST: Các bước RMF](https://csrc.nist.gov/Projects/risk-management)

| Bước | Câu hỏi mà nhóm dự án cần trả lời | Đầu ra sử dụng trong ví dụ |
| --- | --- | --- |
| Prepare | Mục tiêu, ranh giới, vai trò và cách ra quyết định là gì? | Bối cảnh, owner, phạm vi, nguyên tắc xử lý rủi ro |
| Categorize | Thiệt hại tiềm tàng đối với thông tin và hệ thống là gì? | Hồ sơ phân loại tác động và căn cứ |
| Select | Cần bộ kiểm soát nào để đáp ứng nhu cầu và rủi ro? | Bộ kiểm soát được lựa chọn, tailoring, yêu cầu cụ thể |
| Implement | Kiểm soát được thực hiện ở đâu và bằng cách nào? | Thiết kế, cấu hình, triển khai và mô tả thực tế |
| Assess | Kiểm soát có được triển khai đúng và có hiệu lực không? | Kế hoạch đánh giá, kết quả, phát hiện, hành động khắc phục |
| Authorize | Rủi ro khi vận hành có chấp nhận được không? | Quyết định của người có thẩm quyền và điều kiện |
| Monitor | Căn cứ của quyết định còn đúng trong vận hành không? | Thông tin giám sát, thay đổi, cập nhật rủi ro và hồ sơ |

~~~mermaid
flowchart LR
    P["Prepare"] --> C["Categorize"]
    C --> S["Select"]
    S --> I["Implement"]
    I --> A["Assess"]
    A --> R["Authorize"]
    R --> M["Monitor"]
    A -->|"Khắc phục phát hiện"| I
    M -->|"Đổi dữ liệu hoặc nghiệp vụ"| C
    M -->|"Đổi kiểm soát"| S
    M -->|"Đổi triển khai"| I
    M -->|"Cần bằng chứng mới"| A
~~~

Sơ đồ minh họa các hướng phản hồi thường gặp; dự án chọn bước cần quay lại dựa trên tác động của thay đổi. Một lần thay thư viện xác thực có thể chỉ cần cập nhật thiết kế và đánh giá lại; thêm loại dữ liệu nhạy cảm mới có thể buộc xem xét lại cả phân loại và lựa chọn kiểm soát.

## 5. Tình huống xuyên suốt: cổng xử lý hồ sơ theo tenant

Giả định doanh nghiệp xây cổng tiếp nhận và phê duyệt hồ sơ khách hàng. Mỗi tenant là một tổ chức khách hàng độc lập. Người nộp tạo hồ sơ; chuyên viên của tenant xem và duyệt; quản trị viên quản lý quyền. Hệ thống có chức năng export phục vụ nghiệp vụ.

Kiến trúc giả định gồm:

- Web client và API tiếp nhận yêu cầu.
- Nhà cung cấp danh tính dùng chung của doanh nghiệp.
- Dịch vụ hồ sơ và worker xử lý export.
- Cơ sở dữ liệu lưu metadata, kho đối tượng lưu tài liệu đính kèm.
- Nền tảng audit tập trung và hệ thống backup.

~~~mermaid
flowchart LR
    U["Người dùng theo tenant"] --> G["Web và API"]
    G --> IDP["Dịch vụ danh tính dùng chung"]
    G --> H["Dịch vụ hồ sơ"]
    H --> DB["Metadata"]
    H --> O["Tài liệu đính kèm"]
    H --> W["Worker export"]
    W --> O
    H --> L["Audit tập trung"]
    W --> L
    DB --> B["Backup và khôi phục"]
    O --> B
~~~

Nhóm ghi nhận bốn kịch bản để minh họa toàn bộ chuỗi đặc tả:

| Mã | Kịch bản | Hậu quả cần quan tâm |
| --- | --- | --- |
| R-01 | Tài khoản quản trị bị chiếm hoặc phiên đã thu hồi vẫn dùng được | Thay đổi quyền, truy cập trái phép, che giấu thao tác |
| R-02 | API, worker hoặc đường tải file không kiểm tra tenant đúng | Lộ hoặc sửa hồ sơ của khách hàng khác |
| R-03 | Export và log thu thập dữ liệu vượt mục đích nghiệp vụ | Mở rộng người được thấy dữ liệu, khó điều tra nguồn phát tán |
| R-04 | Backup có tồn tại nhưng khôi phục thiếu file hoặc sai quyền | Hồ sơ không dùng được hoặc bị truy cập sai sau phục hồi |

Các kịch bản trên là đầu vào làm việc, chưa phải kết quả đánh giá rủi ro hoàn chỉnh. Dự án còn phải xác định điều kiện khai thác, tác động nghiệp vụ, kiểm soát hiện có và mức tin cậy của thông tin.

## 6. Prepare: đặt bối cảnh trước khi chọn kiểm soát

Prepare bao gồm hoạt động ở cấp tổ chức và cấp hệ thống. Các kết quả quan trọng gồm xác định vai trò, chiến lược quản lý rủi ro, mức chấp nhận rủi ro, chiến lược giám sát và các common control có thể sử dụng. [NIST: Prepare](https://csrc.nist.gov/Projects/risk-management/about-rmf/prepare-step)

### 6.1. Xác định ranh giới và phụ thuộc

Với cổng hồ sơ, nhóm cần thống nhất những gì thuộc phạm vi quyết định vận hành:

| Đối tượng | Nội dung cần ghi trong bối cảnh của ví dụ |
| --- | --- |
| Chức năng | Nộp, xem, duyệt, export, quản lý quyền, phục hồi |
| Dữ liệu | Hồ sơ, tệp đính kèm, danh tính, audit, bản sao dự phòng |
| Thành phần | API, worker, kho dữ liệu, cấu hình tenant, điểm tích hợp |
| Phụ thuộc bên ngoài | Dịch vụ danh tính, hạ tầng lưu trữ, dịch vụ giám sát dùng chung |
| Giả định | Tenant được xác định từ danh tính tin cậy; môi trường đánh giá đại diện cho triển khai |
| Điều kiện thay đổi | Mở export cho đối tác, thêm dữ liệu mới, thay dịch vụ danh tính |

Một dịch vụ nằm ngoài ranh giới triển khai vẫn có thể là phụ thuộc ảnh hưởng trực tiếp đến rủi ro. Ví dụ, dịch vụ danh tính thuộc đội nền tảng nhưng cách ứng dụng kiểm tra token và áp dụng quyền vẫn cần nằm trong mô tả hệ thống.

### 6.2. Gắn công việc với người chịu trách nhiệm

RMF phân biệt người sở hữu hệ thống, người cung cấp kiểm soát dùng chung, người đánh giá và authorizing official. Khi áp dụng vào đội dự án, cần ánh xạ các vai trò này tới cá nhân hoặc chức danh cụ thể, đồng thời xác định mức độc lập của người đánh giá phù hợp bối cảnh. [NIST: RMF Roles and Responsibilities](https://csrc.nist.gov/Projects/risk-management/about-rmf)

Trong ví dụ, nhóm có thể tổ chức như sau:

| Vai trò của dự án | Trách nhiệm cụ thể |
| --- | --- |
| Chủ hệ thống | Duy trì phạm vi, nguồn lực, hồ sơ và kế hoạch khắc phục |
| Chủ nghiệp vụ và dữ liệu | Giải thích tác động của lộ, sai hoặc mất hồ sơ |
| Kiến trúc sư và nhóm phát triển | Chuyển yêu cầu thành thiết kế và triển khai |
| Nhóm nền tảng | Cung cấp thông tin hiệu lực của danh tính, logging, hạ tầng dùng chung |
| Người đánh giá | Thu thập bằng chứng, nêu giới hạn và báo cáo phát hiện |
| Người được giao thẩm quyền chấp nhận rủi ro | Quyết định việc vận hành trong phạm vi được giao |
| Người phụ trách quyền riêng tư | Xem xét mục đích, lượng dữ liệu, khả năng truy cập và hậu quả đối với cá nhân |

Không mặc định trưởng nhóm phát triển hoặc người đóng ticket có quyền chấp nhận mọi rủi ro. Ngay trong tổ chức nhỏ, một người có thể đảm nhiệm nhiều việc nhưng vẫn cần chỉ rõ họ đang thực hiện trách nhiệm nào và ai xem xét xung đột lợi ích.

### 6.3. Đặt nguyên tắc ra quyết định cho ví dụ

Nhóm dự án giả định thống nhất: thiếu kiểm soát tenant trên bất kỳ luồng sản xuất nào là điều kiện chặn vận hành luồng đó; một thiếu sót báo cáo vận hành có thể được xử lý bằng kế hoạch khắc phục nếu đã có bằng chứng cơ chế bảo vệ chính hoạt động.

Đây là quy tắc quản trị của tình huống học tập. Điểm cần học là phải có tiêu chí trước khi gặp áp lực phát hành, để quyết định sau này dựa trên rủi ro và thẩm quyền thay vì dựa trên việc còn bao nhiêu ngày đến hạn.

## 7. Categorize: phân tích tác động của mất bảo vệ

Categorize xem xét thông tin hệ thống xử lý, lưu trữ và truyền đi. Khi dùng FIPS 199, đánh giá tác động đối với bí mật, toàn vẹn và sẵn sàng; phân loại của hệ thống xem xét mức cao nhất phù hợp cho từng mục tiêu thay vì lấy trung bình. Đây là phân tích hậu quả tiềm tàng, không phải điểm số mức độ dễ khai thác lỗ hổng. [NIST: Categorize](https://csrc.nist.gov/Projects/risk-management/about-rmf/categorize-step), [FIPS 199, toàn văn](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.199.pdf)

Bảng sau giả định đã được chủ nghiệp vụ phân tích và giải thích; các mức chỉ phục vụ minh họa:

| Loại thông tin | Bí mật C | Toàn vẹn I | Sẵn sàng A | Căn cứ nghiệp vụ giả định |
| --- | --- | --- | --- | --- |
| Hồ sơ và tài liệu khách hàng | Moderate | Moderate | Moderate | Lộ hoặc sai hồ sơ gây thiệt hại đáng kể |
| Quyết định phê duyệt quan trọng | Moderate | High | Moderate | Sửa trái phép có thể tạo quyết định nghiệp vụ gây thiệt hại nghiêm trọng |
| Nội dung hướng dẫn công khai | Low | Low | Low | Tác động hạn chế khi xử lý riêng trong phạm vi này |

Nếu áp dụng quy tắc trên vào ví dụ, kết quả hệ thống là C = Moderate, I = High, A = Moderate; mức tác động tổng thể là High. Không dùng “đa số thành phần là Moderate” để làm mất mức High của toàn vẹn.

Nhóm cần ghi thêm phạm vi thông tin, giả định về nghiệp vụ và người phê duyệt căn cứ. Từ “High” mà không có diễn giải hậu quả sẽ khó dùng khi kiến trúc thay đổi hoặc khi cần tranh luận về mức đầu tư.

Những điều không thể suy trực tiếp từ bảng:

- Mức tác động High không tự xác định thời gian timeout, retention hay RTO.
- Đã có mã hóa không tự làm hậu quả tiềm tàng của mất bí mật trở thành Low.
- Nhãn “dữ liệu cá nhân” chưa thay cho phân tích cách xử lý dữ liệu có thể gây hại.
- Mức tác động an toàn thông tin chưa bao quát mọi vấn đề quyền riêng tư.

Ví dụ, export chỉ được thực hiện bởi người đúng quyền vẫn có thể chứa quá nhiều trường dữ liệu so với mục đích đã thống nhất. Nhóm phải đặt yêu cầu giới hạn trường và kiểm soát việc sử dụng, bên cạnh yêu cầu ngăn truy cập trái phép.

## 8. Select: lựa chọn và cụ thể hóa kiểm soát

Select bắt đầu từ bộ kiểm soát phù hợp rồi điều chỉnh theo bối cảnh, rủi ro và yêu cầu áp dụng. Baseline cung cấp điểm xuất phát; tailoring cần có căn cứ và hồ sơ về cách áp dụng, các tham số và trách nhiệm. [NIST: Select](https://csrc.nist.gov/Projects/risk-management/about-rmf/select-step), [SP 800-53B](https://csrc.nist.gov/pubs/sp/800/53/b/upd1/final)

### 8.1. Từ họ kiểm soát đến việc phải thực hiện

Bảng dưới dùng tên họ kiểm soát của SP 800-53 để định hướng tra cứu. Đây không phải kết luận rằng đã chọn đủ các control hoặc control enhancement cho một baseline cụ thể. [SP 800-53 Rev. 5: Control families](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)

| Rủi ro | Họ kiểm soát cần xem xét | Câu hỏi cần chuyển thành yêu cầu |
| --- | --- | --- |
| R-01 | Identification and Authentication; Access Control | Tài khoản quản trị xác thực thế nào? Thu hồi quyền có hiệu lực khi nào? |
| R-02 | Access Control; System and Communications Protection | Backend xác minh tenant và quyền đối tượng ở những đường nào? |
| R-03 | Audit and Accountability; PII Processing and Transparency | Ghi những sự kiện, trường dữ liệu nào? Ai được truy cập và vì mục đích gì? |
| R-04 | Contingency Planning; Configuration Management | Có khôi phục được dữ liệu, quyền và cấu hình nhất quán không? |

Khi hoàn thiện bộ kiểm soát thực tế, nhóm phải lưu mã control, enhancement nếu có, phiên bản danh mục và nội dung áp dụng. Chỉ ghi tên họ kiểm soát như bảng trên sẽ chưa đủ cho một assessment cụ thể.

### 8.2. Phân bổ common, system-specific và hybrid control

Common control là kiểm soát có thể được nhiều hệ thống kế thừa; system-specific control được thực hiện riêng cho hệ thống; hybrid control có phần dùng chung và phần hệ thống phải tự đảm nhiệm. Hồ sơ phải chỉ ra trách nhiệm của từng bên. [NIST SP 800-37 Rev. 2, phần common controls](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-37r2.pdf)

Ví dụ về phân bổ trong cổng hồ sơ:

| Năng lực | Phần nền tảng cung cấp | Phần ứng dụng vẫn phải làm |
| --- | --- | --- |
| Danh tính dùng chung | Xác thực và cung cấp thông tin danh tính theo thỏa thuận | Kiểm tra token, ánh xạ tài khoản, cưỡng chế quyền và tenant |
| Logging tập trung | Vận chuyển, lưu trữ, giới hạn truy cập nền tảng | Sinh đúng sự kiện, loại bỏ secret, cung cấp tenant và kết quả |
| Lưu trữ và backup | Hạ tầng sao lưu, khả năng khôi phục thành phần | Kiểm chứng hồ sơ đầy đủ, liên kết file đúng và quyền sau phục hồi |
| Bảo vệ mạng | Các khả năng bảo vệ theo phạm vi dịch vụ | Cấu hình luồng ứng dụng và kiểm tra danh tính đầu cuối theo thiết kế |

Kế thừa cần gắn với dịch vụ, phạm vi, cấu hình và bằng chứng còn phù hợp. Trong ví dụ, báo cáo của dịch vụ danh tính không tự chứng minh worker export đã kiểm tra quyền đúng.

### 8.3. Lưu quyết định tailoring

Một bản ghi tailoring hữu ích của dự án trả lời:

1. Kiểm soát hoặc phần kiểm soát nào đang được xem xét?
2. Nó được áp dụng ở đâu, ai thực hiện và cần điền tham số nào?
3. Có phần nào không áp dụng hoặc được thay bằng biện pháp khác? Căn cứ là gì?
4. Rủi ro và nghĩa vụ liên quan được xử lý bằng cách nào?
5. Ai chấp thuận quyết định và điều kiện nào làm nó cần xem xét lại?

“Chưa kịp triển khai” là một thiếu hụt cần quản lý, không phải căn cứ tự động để ghi “không áp dụng”. Với phương án thay thế, nhóm phải mô tả hiệu quả mong đợi và cách kiểm chứng hiệu quả đó.

## 9. Implement: biến lựa chọn thành yêu cầu và triển khai có thể truy vết

Implement thực hiện kiểm soát đã lựa chọn và mô tả cách triển khai thực tế. Khi đặc tả yêu cầu, nhóm cần phân biệt kết quả phải đạt với giải pháp kiến trúc được chọn để đạt kết quả đó. [NIST: Implement](https://csrc.nist.gov/Projects/risk-management/about-rmf/implement-step)

Trong ví dụ, nhóm dùng mẫu: **phạm vi + chủ thể + hành vi bắt buộc + điều kiện + kết quả khi thất bại + tiêu chí kiểm chứng**. Mỗi yêu cầu có owner, liên kết rủi ro và phiên bản áp dụng.

### 9.1. REQ-AUTH-01: bảo vệ thao tác quản trị

**Yêu cầu của dự án giả định:** Người dùng thực hiện thao tác quản trị quyền phải có phiên đáp ứng chính sách xác thực đa yếu tố đã được phê duyệt. Backend phải kiểm tra điều kiện này cùng quyền quản trị trước khi thay đổi dữ liệu. Khi không đáp ứng, yêu cầu bị từ chối và không phát sinh thay đổi quyền.

Chính sách được tham chiếu cần nêu phương thức được chấp nhận, thời gian hiệu lực và cách xử lý khôi phục tài khoản. Danh tính máy dùng cho tự động hóa có profile riêng được phê duyệt; không dùng ngoại lệ đó để cho tài khoản người bỏ qua xác thực.

**Quyết định kiến trúc minh họa:** Dịch vụ danh tính cung cấp thông tin mức xác thực theo hợp đồng; backend xác minh tính tin cậy và kiểm tra thông tin cần thiết trước thao tác.

**Tiêu chí nghiệm thu:**

- Phiên phù hợp chính sách và có quyền quản trị thực hiện được thao tác trong phạm vi được giao.
- Phiên chỉ có xác thực cơ bản, token không hợp lệ hoặc người thiếu quyền không đổi được quyền.
- Gọi API trực tiếp cho cùng kết quả cưỡng chế như đi qua giao diện.
- Luồng khôi phục tài khoản không tạo đường quản trị bỏ qua điều kiện đã đặc tả.

Bằng chứng cần gắn với cấu hình danh tính và bản triển khai ứng dụng đang được đánh giá. Một ảnh chụp màn hình đăng nhập không đủ chứng minh kiểm tra tại backend.

### 9.2. REQ-AUTHZ-02: cô lập tenant trên mọi luồng dữ liệu

**Yêu cầu của dự án giả định:** Trước mỗi thao tác đọc, sửa, tải file hoặc export hồ sơ, thành phần xử lý phải xác minh chủ thể có quyền với tenant, hành động và đối tượng cụ thể. Tenant dùng để quyết định quyền phải được suy ra hoặc đối chiếu từ ngữ cảnh đã xác thực; giá trị do client cung cấp không tự tạo quyền truy cập.

Khi không đủ quyền, hệ thống không trả nội dung hồ sơ và không thay đổi đối tượng. Hợp đồng API phải quy định phản hồi phù hợp, đồng thời giới hạn khả năng suy ra sự tồn tại của hồ sơ thuộc tenant khác.

**Quyết định kiến trúc minh họa:** Lớp dịch vụ nhận tenant context tin cậy; truy vấn và truy cập kho file ràng buộc với tenant. Worker export kiểm tra danh tính yêu cầu, quyền hiện hành và phạm vi đối tượng theo chính sách được đặc tả.

**Tiêu chí nghiệm thu:**

- Dùng ít nhất hai tenant độc lập và các vai trò khác nhau để kiểm thử.
- Thử thay ID hồ sơ, ID file, tenant trong payload và tham số export.
- Kiểm tra API trực tiếp, cache, xử lý nền và đường tải kết quả export.
- Có ca hợp lệ chứng minh người đúng quyền vẫn hoàn thành nghiệp vụ.

Kiểm thử chỉ ở màn hình danh sách sẽ bỏ sót đường đọc trực tiếp bằng ID. Việc tạo một job hợp lệ cũng chưa chứng minh nơi nhận file export được bảo vệ.

### 9.3. REQ-SESSION-03: thu hồi quyền có thời hạn xác định

**Yêu cầu của dự án giả định:** Sau khi hệ thống ghi nhận thành công việc khóa tài khoản hoặc thu hồi quyền quản trị tại thời điểm t0, chậm nhất tại t0 + 60 giây, mọi yêu cầu quản trị mới bằng phiên hoặc token đã cấp của chủ thể phải bị từ chối. Thời điểm bắt đầu xử lý yêu cầu và kết quả quyết định quyền phải quan sát được trong thử nghiệm.

“60 giây” là ngưỡng minh họa do dự án lựa chọn. Nhóm cần đánh giá chi phí, tính sẵn sàng và mô hình nhất quán trước khi cam kết ngưỡng thực tế.

**Quyết định kiến trúc minh họa:** Dùng trạng thái phiên hoặc phiên bản quyền được kiểm tra với thời hạn cache hữu hạn. Thiết kế phải giải thích cách duy trì giới hạn khi nút ứng dụng mất kết nối với nguồn quyền; không chỉ dựa vào thời hạn dài của token.

**Tiêu chí nghiệm thu:** Thực hiện khóa tài khoản rồi thử lại token cũ qua nhiều nút ứng dụng, các đường quản trị và trạng thái cache khác nhau. Ghi t0, thời điểm thử, kết quả và sai số đồng hồ cho phép. Kiểm tra cả trường hợp nguồn quyền không truy cập được.

Yêu cầu này nói về yêu cầu mới sau thời hạn thu hồi. Việc hủy thao tác đã chạy, job nền hoặc phiên tải file dài cần hợp đồng riêng nếu rủi ro đòi hỏi; không mặc nhiên coi chúng đã được bao phủ.

### 9.4. REQ-DATA-04 và REQ-AUDIT-05: dữ liệu và logging phục vụ đúng mục đích

**REQ-DATA-04:** Mỗi loại export phải dùng danh sách trường dữ liệu đã được chủ nghiệp vụ và người phụ trách quyền riêng tư phê duyệt. Mặc định không bổ sung trường mới vào export khi schema nguồn thay đổi. Quyền tạo và tải export phải được xác minh riêng theo REQ-AUTHZ-02.

**REQ-AUDIT-05:** Hệ thống phải ghi nhận thay đổi quyền và các lần tạo, tải export với các trường tối thiểu: mã sự kiện, thời điểm, chủ thể, tenant, loại thao tác, tham chiếu đối tượng, kết quả và correlation ID. Không ghi mật khẩu, token, khóa bí mật hoặc nguyên văn nội dung hồ sơ. Quyền đọc, sửa và xóa dữ liệu audit phải theo chính sách riêng được phê duyệt.

Dự án còn phải quy định thời gian lưu, cách bảo vệ, xử lý lỗi gửi log và khả năng phát hiện mất sự kiện. Các giá trị đó được chọn theo nhu cầu điều tra và yêu cầu áp dụng, không suy ra chỉ từ việc dùng RMF.

**Tiêu chí nghiệm thu:**

- Thêm trường nhạy cảm vào dữ liệu thử; export chỉ chứa trường đã được phép.
- Thực hiện thao tác hợp lệ và bị từ chối; kiểm tra sự kiện có đủ trường cần thiết.
- Thử quyền của người dùng thông thường với kho audit và file export.
- Kiểm tra dữ liệu log để phát hiện secret hoặc nội dung hồ sơ ngoài đặc tả.
- Làm gián đoạn nơi nhận log; kiểm tra hành vi đã thỏa thuận và cảnh báo tương ứng.

Bản ghi sự kiện cần đủ để điều tra mà vẫn giới hạn dữ liệu. Ghi toàn bộ request body có thể làm kho audit trở thành một nơi phát tán thông tin mới.

### 9.5. REQ-REC-06: phục hồi đạt mục tiêu và giữ đúng quyền

**Yêu cầu của dự án giả định:** Trong kịch bản mất kho dữ liệu sản xuất đã xác định, hệ thống phải khôi phục dịch vụ hồ sơ trong RTO không quá 4 giờ, với RPO không quá 15 phút. Hồ sơ sau phục hồi phải có metadata, tệp đính kèm và quan hệ tenant nhất quán; các kiểm tra quyền trong REQ-AUTHZ-02 vẫn phải đạt.

Trong ví dụ, RTO được đo từ thời điểm công bố bắt đầu kịch bản gián đoạn t0 đến khi bộ kiểm tra phục hồi được phê duyệt đạt. RPO được xác minh bằng dữ liệu đánh dấu đã commit trước t0 và điểm dữ liệu khôi phục nhất quán. Dự án thực tế phải định nghĩa rõ cách đo, phụ thuộc, phạm vi sự cố và tiêu chí hoàn tất tương ứng.

**Quyết định kiến trúc minh họa:** Backup cả metadata và file theo thiết kế nhất quán; có cách khôi phục cấu hình quyền, phụ thuộc khóa và kết nối cần thiết. Quy trình không được giả định rằng chỉ khôi phục database là hoàn thành dịch vụ.

**Tiêu chí nghiệm thu:** Chạy khôi phục vào môi trường cô lập từ bản sao được chỉ định, đo thời gian, xác minh dữ liệu đánh dấu, tải thử file và thực hiện kiểm thử hai tenant. Báo cáo phải ghi rõ các thành phần chưa được thử và điều kiện khác môi trường sản xuất.

Một job backup báo thành công là bằng chứng về hoạt động sao lưu. Để kết luận đạt yêu cầu phục hồi ở trên, cần thêm kết quả khôi phục và kiểm tra nghiệp vụ.

## 10. Assess: đánh giá tuyên bố bằng bằng chứng phù hợp

Assess xác định kiểm soát có được triển khai đúng, hoạt động như dự kiến và tạo ra kết quả bảo vệ mong muốn hay không. Hoạt động gồm kế hoạch, thực hiện đánh giá, báo cáo phát hiện và quản lý khắc phục. [NIST: Assess](https://csrc.nist.gov/Projects/risk-management/about-rmf/assess-step)

SP 800-53A sử dụng các phương pháp **examine, interview, test**. Độ sâu và phạm vi đánh giá cần phù hợp mục tiêu, mức bảo đảm và bối cảnh của tổ chức. [NIST SP 800-53A Rev. 5, toàn văn](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53Ar5.pdf)

### 10.1. Kết hợp phương pháp trong ví dụ

| Phương pháp | Cách thực hiện với REQ-AUTHZ-02 | Giới hạn cần ghi nhận |
| --- | --- | --- |
| Examine | Xem thiết kế tenant context, cấu hình kho file, truy vấn và policy của worker | Tài liệu có thể chưa phản ánh bản đang chạy |
| Interview | Hỏi người phát triển và vận hành cách xử lý tenant trong export và phục hồi | Lời mô tả chưa chứng minh hành vi thực tế |
| Test | Gọi API và tải export với hai tenant, thử ID chéo, cache và xử lý nền | Kết quả chỉ bao phủ phạm vi và điều kiện đã thử |

Một assessment plan của dự án nên ghi tuyên bố cần chứng minh, đối tượng đánh giá, bản build và cấu hình, dữ liệu thử, phương pháp, tiêu chí đạt, người đánh giá và giới hạn truy cập.

Tự động hóa hỗ trợ đánh giá thường xuyên, nhưng chỉ có giá trị trong phạm vi mà nó kiểm tra. Ví dụ, test chứng minh API trả phản hồi từ chối chưa chứng minh kho đối tượng không thể tải trực tiếp bằng một đường khác.

### 10.2. Bằng chứng phải trả lời được câu hỏi “đã kiểm tra cái gì?”

Mỗi bằng chứng trong ví dụ được gắn với:

- Yêu cầu và kịch bản rủi ro liên quan.
- Thời điểm, môi trường, phiên bản triển khai và cấu hình liên quan.
- Điều kiện thử, dữ liệu thử và chủ thể thực hiện.
- Kết quả mong đợi, kết quả thực tế và các sai khác.
- Nguồn tạo bằng chứng, người xem xét và giới hạn kết luận.

Nếu môi trường đánh giá dùng quyền kho file khác sản xuất, cần xác minh sai khác đó trước khi dùng kết quả để hỗ trợ quyết định sản xuất. Nếu không tái hiện được cấu hình đã thử, mức tin cậy của bằng chứng giảm.

### 10.3. Từ phát hiện đến hành động khắc phục

Giả sử kiểm thử cho thấy API đã chặn truy cập chéo tenant nhưng worker export chỉ dùng tenant trong payload. Nhóm ghi một phát hiện với đường ảnh hưởng, điều kiện tái hiện, yêu cầu không đạt và owner khắc phục.

Hành động phù hợp có thể gồm tạm đóng export bị ảnh hưởng, bổ sung kiểm tra quyền của worker, sửa dữ liệu job và đánh giá lại toàn bộ đường tạo/tải export. Đóng ticket sau khi merge code chưa đủ: cần chạy lại kiểm thử tương ứng trên bản triển khai đã sửa và cập nhật rủi ro còn lại.

Không ghi “đạt” cho phần chưa thử. Nếu thiếu quyền truy cập để đánh giá kho file, báo cáo cần nêu thiếu bằng chứng, phạm vi chưa kết luận và tác động của thiếu hụt đó đối với quyết định.

## 11. Authorize: quyết định vận hành thuộc về người có thẩm quyền

Authorize yêu cầu người có thẩm quyền xác định liệu rủi ro bảo mật và quyền riêng tư khi vận hành hệ thống hoặc sử dụng common control có chấp nhận được hay không. Hồ sơ hỗ trợ thường có executive summary, security/privacy plans, assessment reports và plan of action and milestones, viết tắt **POA&M**. [NIST: Authorize](https://csrc.nist.gov/Projects/risk-management/about-rmf/authorize-step)

**Authorization ở đây là quyết định quản trị rủi ro của hệ thống.** Nó khác với quyết định phân quyền cho một người dùng gọi API trong REQ-AUTHZ-02.

### 11.1. Hồ sơ giúp người quyết định hiểu rủi ro

Trong tình huống học tập, phần trình bày cho người quyết định cần làm rõ:

1. Phạm vi hệ thống, chức năng, dữ liệu và môi trường được xem xét.
2. Kiểm soát nào đã được triển khai, đánh giá và có thể kế thừa.
3. Các phát hiện còn mở, thiếu bằng chứng và bất định quan trọng.
4. Hậu quả còn có thể xảy ra, phương án xử lý và chi phí liên quan.
5. Điều kiện vận hành, trách nhiệm, thời hạn hoặc chu kỳ xem xét.
6. Các sự kiện buộc phải xem xét lại quyết định.

Người đánh giá cung cấp kết luận và giới hạn; chủ hệ thống tổ chức khắc phục; người có thẩm quyền quyết định rủi ro. Không suy quyền ký chấp nhận rủi ro từ quyền sửa code hoặc quyền quản trị hạ tầng.

### 11.2. Ví dụ quyết định có phạm vi rõ

Sau khi sửa worker, REQ-AUTHZ-02 đã đạt trên các luồng được kiểm tra. Tuy nhiên, cuộc diễn tập mới chứng minh database phục hồi được; kho file chưa được diễn tập đầy đủ.

Người có thẩm quyền không nên nhận một kết luận chung “recovery đã pass”. Các lựa chọn của dự án có thể gồm yêu cầu hoàn tất diễn tập trước khi vận hành, giảm phạm vi nghiệp vụ theo một thiết kế được đánh giá phù hợp, hoặc chấp nhận rủi ro còn lại trong điều kiện và thời hạn xác định nếu chính sách cho phép.

Việc ghi vào POA&M tạo kế hoạch xử lý. Nó không tự cấp phép vận hành hoặc tự biến một yêu cầu chưa đạt thành yêu cầu đã đạt.

Quyết định quản trị cũng không tự thay đổi nghĩa vụ bắt buộc. Nếu phát hiện liên quan một yêu cầu không được phép miễn trừ trong phạm vi áp dụng, cần xử lý theo thẩm quyền và quy trình tương ứng; không dùng một phiếu chấp nhận rủi ro nội bộ để giả định nghĩa vụ đã biến mất.

### 11.3. Ví dụ bản ghi rủi ro và POA&M liên kết

Cấu trúc dưới đây là mẫu học tập do dự án đặt ra, không phải schema chính thức của NIST:

~~~yaml
risk_id: R-04
scope: "Khôi phục metadata và tài liệu đính kèm của cổng hồ sơ"
requirement_ids:
  - REQ-REC-06
  - REQ-AUTHZ-02
finding: "Chưa có bằng chứng diễn tập khôi phục đầy đủ kho file"
evidence_reference: "REC-DRILL-01, bản triển khai được đánh giá"
residual_risk: "Có thể khôi phục metadata nhưng hồ sơ thiếu file hoặc sai quyền"
remediation_owner: "Chủ hệ thống phối hợp nhóm lưu trữ"
milestones:
  - "Xác nhận thiết kế nhất quán của bản sao"
  - "Thực hiện diễn tập khôi phục database và kho file"
  - "Đo RTO, RPO và kiểm tra quyền sau khôi phục"
due_rule: "Hoàn tất trước mốc quyết định vận hành được phê duyệt"
closure_criteria: "Có bằng chứng đạt REQ-REC-06 và kiểm thử quyền liên quan"
risk_acceptance:
  decision: "Chưa quyết định"
  authority: "Người được giao thẩm quyền cho phạm vi hệ thống"
  conditions: "Phải được ghi rõ nếu cho phép vận hành"
review_trigger: "Diễn tập thất bại, đổi kiến trúc backup hoặc thêm kho dữ liệu"
~~~

Thông tin về phát hiện, hành động, mốc thời gian và trạng thái cần được cập nhật khi bằng chứng thay đổi. Hồ sơ quyết định cần duy trì sự nhất quán với những cập nhật đó. [NIST RMF: Authorize Step FAQs](https://csrc.nist.gov/CSRC/media/Projects/risk-management/documents/06-Authorize%20Step/NIST%20RMF%20Authorize%20Step-FAQs.pdf)

## 12. Monitor: giữ cho căn cứ chấp nhận rủi ro còn hiệu lực

Monitor theo dõi trạng thái kiểm soát, thay đổi của hệ thống và môi trường, thực hiện các đánh giá cần thiết, xử lý phát hiện và cập nhật hồ sơ rủi ro. Thông tin này hỗ trợ việc tiếp tục ra quyết định trong vận hành. [NIST: Monitor](https://csrc.nist.gov/Projects/risk-management/about-rmf/monitor-step)

### 12.1. Đặt chỉ số có phạm vi và người xử lý

Bảng dưới là chiến lược minh họa cho cổng hồ sơ. Tần suất thực tế phải được chọn theo rủi ro, khả năng vận hành và yêu cầu áp dụng.

| Nội dung theo dõi | Phạm vi và cách đo của ví dụ | Tần suất minh họa | Hành động khi có vấn đề |
| --- | --- | --- | --- |
| Mức bảo vệ quản trị | Đối chiếu toàn bộ đường quản trị đã inventory với policy xác thực được áp dụng | Mỗi lần thay đổi danh tính hoặc đường quản trị | Chặn đường sai chính sách và đánh giá ảnh hưởng |
| Cô lập tenant | Chạy các ca bắt buộc trên API, worker, file và export thuộc phạm vi phiên bản | Mỗi bản phát hành liên quan | Dừng phát hành hoặc vô hiệu hóa chức năng ảnh hưởng |
| Độ trễ thu hồi quyền | Đo từ t0 đến lần từ chối tại các nút và điều kiện được chọn | Theo lịch và sau đổi cache/quyền | Điều tra vượt giới hạn, xem xét rủi ro của phiên đang tồn tại |
| Khả năng điều tra | Đối chiếu sự kiện mẫu với trường dữ liệu bắt buộc, phát hiện secret và khoảng trống thu thập | Theo lịch và sau đổi schema log | Sửa pipeline, giới hạn truy cập dữ liệu đã lộ nếu có |
| Phục hồi | Diễn tập với phạm vi dữ liệu, mốc thời gian và kiểm tra quyền đã đặc tả | Theo lịch được phê duyệt và sau thay đổi lớn | Cập nhật phát hiện, kế hoạch và quyết định liên quan |
| Kiểm soát kế thừa | Kiểm tra thông tin dịch vụ và bằng chứng của nhà cung cấp còn phù hợp | Theo lịch và khi nhận thông báo thay đổi | Đánh giá lại phần phụ thuộc và phần ứng dụng |

Một chỉ số “100% test pass” cần mẫu số rõ: tập yêu cầu nào, các đường nào đã kiểm, phiên bản nào và có phần nào bị bỏ qua. Tỷ lệ đạt trên một tập test không tự chứng minh đã bao phủ mọi rủi ro.

### 12.2. Các thay đổi buộc quay lại chuỗi yêu cầu

Ví dụ, đội sản phẩm thêm khả năng chia sẻ file export cho đối tác. Đây là thay đổi luồng dữ liệu và người nhận; nhóm cần xem lại phạm vi, mục đích dữ liệu, phân loại tác động nếu liên quan, lựa chọn kiểm soát, yêu cầu tải file và bằng chứng đánh giá.

Nếu đổi nhà cung cấp danh tính, cần kiểm tra lại giả định về thông tin xác thực, khóa, thu hồi, cache và các kiểm soát đang kế thừa. Nếu nâng cấp thư viện hoặc thay policy kho file, cần xác định yêu cầu và bằng chứng nào bị ảnh hưởng trước khi kết luận quyết định cũ vẫn đủ căn cứ.

Giám sát tiếp diễn hỗ trợ ongoing authorization khi tổ chức thiết lập cơ chế phù hợp; một dashboard xanh không tự thay vai trò chấp nhận rủi ro. Khi điều kiện chấp nhận không còn đúng, phải chuyển thông tin đến người có thẩm quyền để xem xét phản ứng cần thiết. [NIST SP 800-37 Rev. 2](https://csrc.nist.gov/pubs/sp/800/37/r2/final)

### 12.3. Xử lý khi kết thúc sử dụng hệ thống

Trong ví dụ, kế hoạch vòng đời còn phải bao phủ việc ngừng cung cấp cổng hồ sơ: đóng luồng truy cập, thu hồi danh tính dịch vụ, xử lý dữ liệu và bản sao theo chính sách áp dụng, cập nhật inventory và chuyển trách nhiệm với hồ sơ phải lưu.

Nếu database đã xóa nhưng file export công khai hoặc credential của worker vẫn còn hiệu lực, công việc xử lý rủi ro chưa kết thúc. Bằng chứng đóng hệ thống cần phản ánh các phụ thuộc và luồng dữ liệu đó.

## 13. Ma trận truy vết từ rủi ro đến bằng chứng

Bảng minh họa dưới đây nối các phần của bài. “Đã liên kết” và “đã đáp ứng” cần được theo dõi riêng: một yêu cầu có bằng chứng tham chiếu nhưng bằng chứng có thể cho kết quả không đạt hoặc đã hết phù hợp.

| Rủi ro | Yêu cầu của dự án | Vị trí kiến trúc chính | Bằng chứng cần có | Căn cứ xem xét trong vận hành |
| --- | --- | --- | --- | --- |
| R-01 | REQ-AUTH-01, REQ-SESSION-03 | Dịch vụ danh tính, kiểm tra phiên và quyền ở backend | Test MFA, API trực tiếp, token cũ sau thu hồi, các trạng thái cache | Policy thay đổi; độ trễ thu hồi vượt giới hạn |
| R-02 | REQ-AUTHZ-02 | API, lớp truy cập dữ liệu, worker, kho file | Test hai tenant ở mọi luồng được inventory; cấu hình tương ứng | Có đường dữ liệu mới hoặc thay đổi policy/quyền |
| R-03 | REQ-DATA-04, REQ-AUDIT-05 | Export, sinh sự kiện, pipeline và kho audit | Đối chiếu schema export; mẫu log; kiểm tra quyền đọc và rò secret | Schema thay đổi; thiếu sự kiện; mở rộng người nhận |
| R-04 | REQ-REC-06, REQ-AUTHZ-02 | Backup database, kho file, cấu hình và khóa phụ thuộc | Báo cáo khôi phục có đo thời gian, dữ liệu đánh dấu và test quyền | Diễn tập không đạt; thêm kho dữ liệu; đổi kiến trúc backup |

Có thể dùng một công cụ quản lý công việc để lưu ma trận này, nhưng điều cần giữ là khả năng đi hai chiều:

- Từ một rủi ro, tìm được yêu cầu, giải pháp, bằng chứng và quyết định liên quan.
- Từ một thay đổi code hoặc cấu hình, tìm được những yêu cầu, rủi ro và kết luận đánh giá cần xem xét lại.

Nếu không có liên kết ngược, đội vận hành có thể biết một test thất bại nhưng không biết chức năng nào cần dừng hoặc ai phải nhận thông tin.

## 14. Gắn RMF với nhịp phát triển phần mềm

Dự án không cần chờ hoàn thành mọi chức năng mới bắt đầu thu bằng chứng. Cách tổ chức dưới đây là ví dụ tích hợp công việc vào SDLC của cổng hồ sơ:

| Thời điểm | Công việc yêu cầu bảo mật | Đầu ra phục vụ RMF |
| --- | --- | --- |
| Khởi tạo và phân tích nghiệp vụ | Xác định dữ liệu, tác động, ranh giới, chủ thể và kịch bản rủi ro | Bối cảnh và căn cứ phân loại |
| Thiết kế | Chọn kiểm soát, phân bổ trách nhiệm, cụ thể hóa yêu cầu và failure behavior | Bộ kiểm soát, yêu cầu, quyết định kiến trúc |
| Phát triển | Thực hiện cơ chế, kiểm tra ở mức phù hợp, lưu liên kết thay đổi | Mô tả triển khai và bằng chứng kỹ thuật ban đầu |
| Đánh giá trước vận hành | Thử các luồng đại diện trên cấu hình xác định, ghi giới hạn và phát hiện | Báo cáo đánh giá và kế hoạch khắc phục |
| Ra quyết định | Cung cấp rủi ro còn lại, điều kiện và phương án xử lý | Quyết định của người có thẩm quyền |
| Vận hành và thay đổi | Theo dõi chỉ số, đánh giá lại khi cần, giữ hồ sơ phù hợp | Bằng chứng mới và cập nhật quyết định |
| Ngừng sử dụng | Thu hồi truy cập, xử lý dữ liệu và phụ thuộc | Hồ sơ kết thúc phạm vi vận hành |

Đối với thay đổi nhỏ, dự án có thể tái sử dụng bằng chứng còn phù hợp và chỉ đánh giá phần bị ảnh hưởng. Muốn làm được điều đó, phải giải thích vì sao phạm vi, phiên bản, cấu hình và giả định liên quan vẫn tương ứng; không dùng tuổi của tài liệu làm tiêu chí duy nhất.

Trong ví dụ, thay màu nút giao diện có thể không ảnh hưởng kiểm tra tenant. Thay cách truyền tenant context tới worker lại ảnh hưởng trực tiếp REQ-AUTHZ-02, kể cả khi chức năng nhìn trên màn hình không đổi.

## 15. Những sai lầm làm đứt chuỗi rủi ro — yêu cầu — bằng chứng

| Sai lầm | Vì sao kết luận không đủ căn cứ | Cách xử lý trong tình huống học tập |
| --- | --- | --- |
| Sao chép toàn bộ danh mục kiểm soát vào backlog | Chưa xác định phạm vi, tham số và trách nhiệm | Chọn bộ kiểm soát có căn cứ rồi cụ thể hóa thành yêu cầu |
| Ghi “compliant” chỉ vì có bảng mapping | Mapping chưa chứng minh triển khai hoặc hiệu lực | Liên kết với bằng chứng và kết quả đánh giá thực tế |
| Hạ mức tác động vì đã triển khai mã hóa | Trộn thiệt hại tiềm tàng với hiệu quả kiểm soát hiện có | Giữ căn cứ phân loại; đánh giá hiệu quả bảo vệ ở phần tương ứng |
| Ghi “không áp dụng” cho công việc chưa làm | Che khuất thiếu hụt và rủi ro còn lại | Ghi phát hiện, owner, mốc khắc phục và quyết định cần thiết |
| Coi dịch vụ dùng chung đã bảo vệ trọn ứng dụng | Bỏ sót trách nhiệm của API, worker và cấu hình hệ thống | Chỉ rõ phần kế thừa và phần ứng dụng phải thực hiện |
| Dùng test pass trên môi trường khác cấu hình | Bằng chứng không đại diện cho đối tượng quyết định | Xác minh sai khác và thu thêm bằng chứng cần thiết |
| Đồng nhất assessment pass với quyền vận hành | Bỏ qua thẩm quyền và việc xem xét rủi ro còn lại | Giữ riêng báo cáo đánh giá và quyết định quản trị |
| Dùng POA&M như giấy miễn trừ tự động | Kế hoạch chưa phải hành động hoàn tất hay quyết định chấp nhận | Theo dõi khắc phục và ghi quyết định đúng thẩm quyền |
| Chỉ giám sát lỗ hổng phần mềm | Bỏ sót mất hiệu lực của quyền, log, phụ thuộc và phục hồi | Theo dõi các mục tiêu và điều kiện đã dùng để chấp nhận rủi ro |

## 16. Cách thực hành với một chức năng mới

Giả sử cổng hồ sơ bổ sung chức năng “duyệt hàng loạt”. Người học có thể áp dụng chuỗi công việc sau trên giấy hoặc trong công cụ quản lý yêu cầu đang dùng:

1. Mô tả chủ thể, tenant, dữ liệu đầu vào và hậu quả của một lần duyệt sai hàng loạt.
2. Kiểm tra việc bổ sung này có thay đổi căn cứ phân loại, ranh giới hoặc phụ thuộc không.
3. Chọn các kiểm soát liên quan và phân bổ trách nhiệm giữa dịch vụ danh tính, API, worker và audit.
4. Viết yêu cầu cho quyền thực hiện, phạm vi đối tượng, trạng thái lỗi, dữ liệu audit và khả năng khôi phục nghiệp vụ.
5. Xác định bằng chứng cần có cho các trường hợp đúng quyền, sai tenant, quyền bị thu hồi và xử lý thành công một phần.
6. Ghi các giới hạn chưa có bằng chứng, phương án xử lý và người cần quyết định.
7. Đặt điều kiện giám sát cùng các thay đổi làm yêu cầu hoặc kết luận cũ cần được xem xét lại.

Đầu ra cần đọc được như một lập luận: mục tiêu nào đang được bảo vệ, rủi ro nào khiến yêu cầu đó cần thiết, hệ thống thực hiện ở đâu, bằng chứng chứng minh điều gì và ai chịu trách nhiệm với rủi ro còn lại. Khi chuỗi này rõ ràng, RMF trở thành cách quản lý công việc bảo mật trong vòng đời sản phẩm.
