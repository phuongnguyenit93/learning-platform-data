# Khảo sát quy trình bán hàng và xây dựng bảng thuật ngữ

Đây là bài thuộc chương **Thực hành tổng hợp**, kết nối kỹ năng khảo sát yêu cầu với việc mô hình hóa và kiểm chứng dữ liệu.

## 1. Bài thực hành tổng hợp: bắt đầu từ nghiệp vụ, không bắt đầu từ bảng

Trong module **DATABASE_DATA_MODELING**, mục tiêu là biến yêu cầu nghiệp vụ thành mô hình dữ liệu có thể giải thích, tiến hóa và kiểm chứng: thực thể, quan hệ, ràng buộc, chuẩn hóa, khóa, chỉ mục, lược đồ vật lý; đồng thời so sánh mô hình quan hệ, document, graph và phân tích. Để thực hiện các bước ấy đúng, người thiết kế phải hiểu **quy trình tạo và sử dụng dữ liệu** trước khi vẽ ERD hoặc viết SQL.

Chủ đề của bài là **khảo sát quy trình bán hàng và xây dựng bảng thuật ngữ (business glossary)**. Đây là bài thực hành đầu vào cho các bước mô hình hóa tiếp theo, không phải bài yêu cầu triển khai ngay một schema hoàn chỉnh.

Một câu nói tưởng đơn giản như:

> “Mỗi đơn hàng có một thanh toán, doanh thu tính theo đơn đã giao.”

có thể chứa ba giả định chưa được xác nhận:

- Một đơn hàng có thật chỉ một lần thanh toán, hay có thể trả tiền thành nhiều đợt?
- “Đơn đã giao” có nghĩa tất cả kiện hàng được giao, hay chỉ một phần?
- “Doanh thu” là giá trị đơn đặt, tiền đã thu, giá trị hàng đã giao, hay số tiền sau hoàn trả?

Nếu ghi ba câu trên thành thuộc tính và quan hệ trước khi khảo sát, mô hình dữ liệu có thể **đúng cú pháp nhưng sai nghiệp vụ**. Bảng thuật ngữ tốt làm rõ nghĩa và phạm vi của từng thuật ngữ trước khi chọn khóa, lực lượng quan hệ và các công thức.

### Kết quả học tập

Sau bài này, người học có thể:

1. Xác định phạm vi khảo sát và những quyết định dữ liệu cần chốt.
2. Lập danh sách người liên quan, vai trò và câu hỏi phỏng vấn theo từng bước bán hàng.
3. Vẽ quy trình **as-is**, phân biệt thực tế đang vận hành với quy trình **to-be** mong muốn.
4. Ghi nhận luồng chính, ngoại lệ, trạng thái, tác nhân, thời gian và nguồn dữ liệu.
5. Xây bảng thuật ngữ có **định nghĩa, ranh giới áp dụng, ví dụ, phản ví dụ, owner và nguồn chứng cứ**.
6. Phân biệt các từ dễ lẫn: sản phẩm/SKU, đơn hàng/giao hàng, thanh toán/thu tiền, trả hàng/hoàn tiền, doanh số/doanh thu, số lượng tồn/khả dụng.
7. Chuyển kết quả khảo sát thành danh sách **ứng viên thực thể, grain, khóa, quan hệ và bất biến nghiệp vụ** mà chưa chốt vật lý quá sớm.
8. Kiểm chứng các khái niệm bằng tình huống cụ thể, đối soát nguồn và phiên review.

## 2. Bối cảnh giả định: cửa hàng bán lẻ đa kênh

Bài thực hành dùng một doanh nghiệp giả định tên **An Nhiên Retail**. Đây là tình huống tự tạo để học cách khảo sát, không đại diện cho quy trình của một doanh nghiệp có thật.

Doanh nghiệp bán sản phẩm chăm sóc gia đình qua ba kênh:

- **POS tại cửa hàng:** nhân viên có thể tạo giao dịch bán trực tiếp; khách không nhất thiết có tài khoản.
- **Website:** khách thêm giỏ, xác nhận đơn, chọn thanh toán và giao hàng.
- **Sàn đối tác:** đối tác gửi đơn vào hệ thống qua API hoặc tệp đồng bộ; mã đơn của đối tác có không gian định danh riêng.

Các bộ phận cùng tham gia:

| Bộ phận | Công việc thực tế | Dữ liệu quan trọng |
|---|---|---|
| Kinh doanh/POS | Tiếp nhận và xác nhận nhu cầu mua | Giỏ, giao dịch, dòng hàng, kênh |
| Chăm sóc khách hàng (CSKH) | Đổi địa chỉ, hủy đơn, nhận yêu cầu trả hàng | Tình trạng đơn, yêu cầu, lý do |
| Kho | Giữ hàng, nhặt, đóng gói, xuất kho | Tồn thực tế, giữ chỗ, phiếu xuất |
| Giao vận | Bàn giao, giao từng kiện, hoàn kiện | Kiện, vận đơn, lần giao, kết quả |
| Thanh toán | Nhận/đối soát thanh toán | Ủy quyền, thu tiền, giao dịch, hoàn tiền |
| Kế toán | Ghi nhận hóa đơn và nghiệp vụ tài chính | Chứng từ, số tiền, thuế, kỳ |
| Marketing | Theo dõi bán hàng và ưu đãi | Chiến dịch, mã giảm giá, phân đoạn |
| Dữ liệu/BI | Tạo báo cáo, thống nhất định nghĩa KPI | Grain, fact, dimension, thời gian |
| Bảo mật/quyền riêng tư | Kiểm tra dữ liệu khách được dùng ra sao | Danh mục PII, quyền, retention |

**Ràng buộc mẫu:** có thể giao một đơn thành nhiều kiện, thanh toán nhiều lần, trả một phần hàng và hoàn tiền theo nhiều giao dịch. Mã đơn nguồn có thể trùng giữa các kênh. Những giả định này cần được nhóm học viên xác minh như thể đang làm một dự án thật.

### 2.1. Người học đóng vai ai?

Người học đóng vai **data analyst/data architect** phối hợp với product owner. Nhiệm vụ không phải chỉ hỏi “cần những cột nào?”, mà phải khám phá:

- Người dùng đang làm **việc gì**?
- Khi nào dữ liệu được **tạo, sửa, chốt, hủy, lưu lịch sử**?
- Một thuật ngữ có mang nghĩa khác nhau ở các bộ phận không?
- Bản ghi nào là **nguồn có thẩm quyền**?
- Điều kiện nào phải đúng trong mọi trường hợp?
- Cần giữ gì để giải thích một báo cáo hoặc giao dịch trong quá khứ?

## 3. Đầu vào, đầu ra và tiêu chí nghiệm thu

Đầu vào giả định:

1. Mô tả tình huống của An Nhiên Retail trong bài.
2. Bản phỏng vấn mô phỏng hoặc ghi chú khảo sát từ từng vai trò.
3. Một số đơn, thanh toán, giao hàng và hoàn trả mẫu được cung cấp ở các phần sau.
4. Các giả định chưa xác minh; phải gắn nhãn thay vì tự coi là sự thật.

Bộ đầu ra cần hoàn thành:

| Mã | Sản phẩm bàn giao | Câu hỏi nó trả lời |
|---|---|---|
| D01 | **Scope & discovery brief** | Khảo sát để chốt quyết định gì; phạm vi nào? |
| D02 | **Stakeholder map** | Ai hiểu và có quyền xác nhận từng phần? |
| D03 | **Quy trình as-is** | Việc bán hàng thực sự xảy ra theo đường nào? |
| D04 | **Exception & lifecycle matrix** | Khi thất bại, hủy, tách kiện, hoàn hàng thì sao? |
| D05 | **Business glossary** | Mỗi thuật ngữ có nghĩa gì, bao gồm/loại trừ gì? |
| D06 | **Data source/ownership inventory** | Dữ liệu phát sinh, được quản lý và được dùng ở đâu? |
| D07 | **Business rule catalog** | Những bất biến nào phải bảo vệ? |
| D08 | **Open questions & decision log** | Điều gì còn tranh luận, ai chốt và bằng chứng nào? |
| D09 | **Candidate model handoff** | Những thực thể, grain, khóa và quan hệ nào cần phân tích tiếp? |
| D10 | **Review & evidence record** | Ai đã kiểm tra và các trường hợp biên đã được bao phủ chưa? |

**Chưa cần viết toàn bộ DDL, chọn tất cả index hoặc chia partition.** Những quyết định vật lý chỉ hợp lý sau khi hiểu rõ grain, nguồn dữ liệu và workload. Có thể đưa ví dụ khóa/SQL để thử giả thuyết, nhưng phải ghi rõ chúng là **ứng viên**.

### 3.1. Ranh giới hoàn thành

Bài được xem là hoàn thành khi người khác đọc D01–D10 có thể:

- Phân biệt “đơn được đặt”, “hàng được giao”, “tiền đã thu” và “hàng đã trả”.
- Giải thích **một** ví dụ giao dịch từ đầu tới cuối.
- Biết dùng mã nào để truy vết giữa hệ thống và mã nào chỉ là nhãn hiển thị.
- Biết phần nào đã được duyệt và phần nào còn là giả thuyết.
- Chỉ ra dữ liệu nào sẽ tạo **nhiều hàng** khi một đơn có nhiều lần giao hoặc thanh toán.
- Không đưa ra một công thức doanh thu mâu thuẫn giữa các báo cáo mà không ghi rõ sự khác biệt.

## 4. Khoanh vùng khảo sát và định nghĩa câu hỏi quyết định

Không nên khảo sát “toàn bộ quy trình bán lẻ” trong một workshop duy nhất. Hãy viết một bản scope ngắn.

~~~text
Tên bài toán:
  Khảo sát dữ liệu bán hàng đa kênh và đồng bộ thuật ngữ.

Điểm bắt đầu:
  Khách hoặc nhân viên tạo yêu cầu mua có thể trở thành đơn hàng.

Điểm kết thúc:
  Đơn được hoàn tất/hủy; có thể có trả hàng và hoàn tiền.

Trong phạm vi:
  Giỏ/đơn/dòng đơn; ưu đãi tại đơn; phân bổ thanh toán;
  giữ hàng; xuất kho; kiện giao; trả hàng; hoàn tiền;
  danh tính kênh/nguồn; các mốc trạng thái.

Ngoài phạm vi vòng khảo sát đầu:
  Kế toán sổ cái tổng hợp, định giá tồn kho, dự báo nhu cầu,
  quản trị nhà cung cấp, chiến lược thuế đa quốc gia.

Điều cần chốt:
  Danh tính đơn/dòng; grain event thanh toán/giao hàng;
  trạng thái và thời gian; định nghĩa số đo; business glossary.
~~~

Một phần “ngoài phạm vi” không có nghĩa là không tồn tại. Ví dụ **thuế và hóa đơn** có thể là phụ thuộc trọng yếu của doanh thu; phải ghi rõ ai chịu trách nhiệm và khi nào cần khám phá tiếp.

### 4.1. As-is và to-be là hai nguồn thông tin khác nhau

- **As-is:** nhân viên và hệ thống thực tế đang làm gì, kể cả xử lý thủ công hoặc workaround.
- **To-be:** quy trình doanh nghiệp muốn áp dụng sau cải tiến.
- **Policy:** quy tắc được công bố, có thể khác thực tế vận hành.
- **System behavior:** API/schema hiện hỗ trợ gì, có thể khác cả as-is lẫn policy.

Đừng vẽ to-be rồi ghi nhãn as-is. Một trường “giao hàng hoàn tất” có thể đang được cập nhật thủ công dù tài liệu chính sách mô tả cập nhật tự động từ hãng vận chuyển.

### 4.2. Định nghĩa ranh giới miền

Ví dụ:

~~~mermaid
flowchart LR
    C["Khách / nhân viên"] --> SALES["Sales: đơn hàng"]
    SALES --> PAY["Payments: thu tiền"]
    SALES --> WH["Warehouse: xuất hàng"]
    WH --> SHIP["Delivery: giao kiện"]
    SHIP --> SERVICE["CSKH: trả hàng"]
    PAY --> SERVICE
    SALES --> BI["Analytics: báo cáo"]
    PAY --> BI
    SHIP --> BI
~~~

Đây là sơ đồ **ngữ cảnh**, chưa chứng minh có foreign key giữa các database. Các quan hệ xuyên dịch vụ có thể được giữ bằng ID nghiệp vụ, API, event hoặc đối soát; điều này cần khảo sát riêng.

## 5. Lập bản đồ stakeholder trước khi phỏng vấn

Người biết một hoạt động đang diễn ra không nhất thiết có thẩm quyền quyết định nghĩa KPI hoặc quy tắc tài chính.

| Vai trò | Thông tin cần thu thập | Quyền xác nhận dự kiến |
|---|---|---|
| Sales owner | Ý nghĩa của đơn, trạng thái và đổi/hủy | Quy trình bán hàng |
| Nhân viên POS | Bước thực tế, ngoại lệ và sửa lỗi | Bằng chứng thực tế ở quầy |
| Product owner website | Checkout, giỏ, giá hiển thị | Hành vi web được phê duyệt |
| Kho | Giữ hàng, đóng gói, chia kiện | Vận động hàng và số lượng |
| Payment specialist | Authorization, capture, refund, retry | Ngữ nghĩa giao dịch thanh toán |
| Kế toán | Chứng từ, thời điểm ghi nhận, đối soát | Chỉ tiêu tài chính có thẩm quyền |
| CSKH | Hoàn, đổi, hủy, xử lý ngoại lệ | Quy tắc xử lý yêu cầu khách |
| BI analyst | KPI đang tính và bất đồng giữa báo cáo | Định nghĩa metric được trình phê duyệt |
| Backend/data engineer | Nguồn sự thật, ID, event, schema | Hành vi hệ thống hiện tại |
| Privacy/security | PII, retention, quyền truy cập | Chính sách bảo vệ phù hợp |

### 5.1. RACI rút gọn cho tài liệu

Trong mỗi artefact, có thể ghi:

~~~text
R – Responsible: người ghi chép, tổng hợp và sửa tài liệu.
A – Accountable: người phê duyệt nội dung nghiệp vụ.
C – Consulted: vai trò có chuyên môn được tham vấn.
I – Informed: nhóm phải được thông báo khi thay đổi.
~~~

Ví dụ định nghĩa **Captured Payment Amount** có thể do chuyên gia payment và kế toán cùng tham vấn, nhưng cần một owner cuối được thống nhất. Tránh để ba nhóm cùng có ba cách tính mà không xác định ai có thẩm quyền.

### 5.2. Mâu thuẫn là tín hiệu cần khảo sát

Khi Sales nói “đơn thành công nghĩa là giao xong”, Payment nói “thành công nghĩa là thu tiền”, BI nói “thành công nghĩa là không hủy”, **không chọn đại một định nghĩa**. Ghi ba khái niệm khác nhau, lấy ví dụ minh họa và tổ chức buổi chốt thuật ngữ.

## 6. Chuẩn bị trước buổi khảo sát: câu hỏi, bằng chứng, giả định

Trước phỏng vấn, chuẩn bị:

- Mục đích và câu hỏi cần chốt.
- Bản workflow hiện có, nếu được cung cấp chính thức.
- Danh sách hệ thống nguồn và báo cáo liên quan.
- Một vài transaction giả lập đặc trưng.
- Danh sách **giả định chưa chứng minh**.
- Quy tắc ghi biên bản, owner và cách xác nhận sau buổi phỏng vấn.

### 6.1. Gắn nhãn mức độ chắc chắn

| Nhãn | Nghĩa | Cách xử lý |
|---|---|---|
| **CONFIRMED** | Được owner xác nhận và có căn cứ | Có thể dùng làm yêu cầu thiết kế |
| **OBSERVED** | Nhìn thấy trong dữ liệu/log/thao tác | Cần biết có đại diện quy tắc chung không |
| **HYPOTHESIS** | Giả thuyết do người thiết kế đề xuất | Hỏi lại, không coi là invariant |
| **DISPUTED** | Hai bên đưa định nghĩa khác nhau | Giao owner giải quyết |
| **OPEN** | Chưa có câu trả lời | Ghi hạn xử lý và tác động |
| **OUT_OF_SCOPE** | Không thuộc vòng này | Ghi phụ thuộc nếu quan trọng |

Ví dụ câu “mỗi order chỉ có một payment” nếu mới nhìn thấy hai mẫu thì chỉ là **OBSERVED**, không được nâng thành **CONFIRMED** mà không hỏi đường thanh toán nhiều lần, thất bại và partial capture.

### 6.2. Chuẩn bị ví dụ âm

Hãy đưa các câu hỏi dạng:

- Điều gì xảy ra nếu thanh toán thất bại sau khi giữ hàng?
- Nếu một SKU tạm hết ở kho A nhưng còn ở kho B?
- Nếu hủy đơn sau khi một kiện đã bàn giao?
- Nếu khách trả một phần số lượng của dòng?
- Nếu API sàn gửi lại cùng mã đơn hai lần?
- Nếu đơn được tạo lúc 23:55 nhưng đồng bộ sau 00:00?
- Nếu hàng đã giao nhưng khách thanh toán COD chưa đối soát?

Những trường hợp âm thường làm lộ grain, trạng thái và mốc thời gian mà luồng “happy path” che khuất.

## 7. Bộ câu hỏi phỏng vấn theo bước quy trình

Không hỏi chung chung “Hệ thống có những bảng nào?”. Hãy yêu cầu người tham gia **kể lại một giao dịch có thật hoặc được ẩn danh**.

### 7.1. Sales/POS/website

1. Điều kiện nào tạo **đơn hàng**, và điều kiện nào chỉ tạo **giỏ hàng**?
2. Mã đơn được cấp từ khi draft hay khi xác nhận?
3. POS có nhận khách vãng lai không?
4. Giá và khuyến mại được chốt ở thời điểm nào?
5. Có thể sửa số lượng, địa chỉ, kênh nhận hàng sau khi xác nhận không?
6. Có thể tách đơn/gộp đơn không? Bản ghi nguồn nào giữ quan hệ?
7. Một đơn có thể đặt nhiều lần cùng một SKU với ưu đãi khác nhau không?
8. Có loại đơn đặt trước, đặt cọc, mua hàng không có tồn sẵn không?

### 7.2. Kho/giao vận

1. “Đặt giữ hàng” khác “xuất kho” thế nào?
2. Số lượng khả dụng tính từ nguồn nào?
3. Một dòng đơn có thể được chia cho nhiều kho/kiện không?
4. Một kiện có thể chứa hàng của nhiều đơn không?
5. Có thử giao nhiều lần không? “Đã giao” do ai xác nhận?
6. Khi giao thất bại, hàng đang ở trạng thái nào và bao giờ quay về khả dụng?
7. Khi trả hàng, hàng có nhập lại tồn ngay không?

### 7.3. Thanh toán/kế toán

1. Sự khác nhau giữa **ủy quyền**, **thu tiền**, **đối soát**, **hoàn tiền**?
2. Có payment attempt thất bại nhưng vẫn lưu không?
3. Một order có thể được thanh toán qua hai phương thức không?
4. Có thể payment cho nhiều order hoặc một đơn được nhiều payment cấp tiền không?
5. COD khi giao hàng có cùng nghĩa với capture qua cổng thanh toán không?
6. Hoàn tiền có thể xảy ra nhiều lần, có thể hoàn một phần không?
7. Báo cáo doanh thu dùng order date, capture date, fulfillment date hay ngày ghi sổ?
8. Thuế, phí vận chuyển, discount và returns được tính thế nào?

### 7.4. CSKH và BI

1. Phân biệt hủy trước giao, trả sau giao và đổi hàng?
2. Tình trạng trả hàng được ghi theo **request**, **dòng hàng**, hay **kiện**?
3. Khách trả hàng nhưng chưa hoàn tiền thì báo cáo ra sao?
4. Dashboard “đơn thành công” hiện đang dùng status nào?
5. Báo cáo hôm qua có được điều chỉnh khi một refund đến muộn không?
6. Có bảng dữ liệu ngoài luồng chính như Excel/phiếu tay không?
7. Chủ thể nào có quyền xem thông tin liên hệ và lịch sử mua?
8. Những phép đối soát nào giúp phát hiện dữ liệu trùng, thiếu hoặc cập nhật muộn?

## 8. Cách điều hành buổi phỏng vấn: đi từ hành vi đến dữ liệu

Một khung thực hành 45–60 phút có thể:

| Giai đoạn | Câu hỏi dẫn dắt | Đầu ra |
|---|---|---|
| Mở đầu | “Hôm nay chốt điều gì?” | Scope và mục tiêu |
| Kể chuyện | “Hãy đi qua một đơn cụ thể từ đầu tới cuối.” | Timeline nghiệp vụ |
| Kiểm tra ngoại lệ | “Trường hợp ngược lại đã xảy ra chưa?” | Luồng rẽ nhánh |
| Truy nguồn | “Ai nhập trạng thái này? Ở hệ thống nào?” | Ownership/data flow |
| Định nghĩa thuật ngữ | “Khi nói thanh toán, anh/chị đang chỉ attempt, capture hay tiền đối soát?” | Glossary |
| Kiểm tra quy tắc | “Điều gì không bao giờ được phép xảy ra?” | Invariants |
| Chốt | “Điều gì đã xác nhận; điều gì cần hỏi tiếp?” | Decision/open issue |

### 8.1. Mẫu biên bản không suy đoán

~~~text
OBS-001
Nguồn: Phỏng vấn chuyên viên thanh toán; 2026-11-22.
Phát biểu: "Một đơn có thể có nhiều lần thử thanh toán."
Bằng chứng: Transaction demo T-01 (đã loại PII).
Diễn giải tạm: PaymentAttempt có grain riêng.
Trạng thái: OBSERVED.
Câu hỏi mở: Một order có thể có nhiều CAPTURE thành công không?
Owner xác minh: Payment lead.
~~~

Phân biệt **trích lời người dùng**, **diễn giải của analyst** và **quyết định đã duyệt**. Nếu không, một giả thuyết sẽ bị trích thành sự thật trong các tài liệu sau.

### 8.2. Không ghi dữ liệu cá nhân không cần thiết

Khi khảo sát thật, ví dụ đơn cần được ẩn danh/tokenize. Không sao chép mật khẩu, token cổng thanh toán, số thẻ, địa chỉ giao chi tiết hoặc dữ liệu khách không cần thiết vào bảng thuật ngữ hay biên bản. Tài liệu mô hình có thể có phân loại nhạy cảm và link tới hệ an toàn, không cần chứa giá trị thực.

## 9. Vẽ quy trình as-is theo các điểm tạo dữ liệu

Một sơ đồ luồng chính giả định:

~~~mermaid
flowchart TD
    A["Khách chọn hàng / POS ghi nhu cầu"] --> B["Giỏ hoặc yêu cầu mua"]
    B --> C{"Xác nhận đặt đơn?"}
    C -->|Không| D["Giỏ lưu hoặc bỏ"]
    C -->|Có| E["Tạo đơn và các dòng đơn"]
    E --> F["Kiểm tra ưu đãi, giá, nguồn hàng"]
    F --> G{"Có thể thực hiện?"}
    G -->|Không| H["Đợi hàng / hủy theo chính sách"]
    G -->|Có| I["Đặt giữ hàng / chuẩn bị fulfillment"]
    I --> J["Ủy quyền hoặc thu tiền theo phương thức"]
    J --> K{"Thanh toán phù hợp?"}
    K -->|Không| L["Chờ retry / hủy / giải phóng giữ hàng"]
    K -->|Có| M["Pick, pack, tạo kiện"]
    M --> N["Giao hàng / nhận tại quầy"]
    N --> O{"Có yêu cầu trả hàng?"}
    O -->|Có| P["Yêu cầu trả → nhận hàng → kiểm tra"]
    P --> Q["Quyết định và thực hiện hoàn tiền"]
    O -->|Không| R["Kết thúc vòng đời nghiệp vụ"]
    Q --> R
~~~

Sơ đồ **minh họa thứ tự thường gặp**, không áp đặt “mọi đơn phải thanh toán trước giao”: COD, đặt cọc, trả sau và POS có thể có thứ tự khác. Khi khảo sát, cần tạo các lane/phân nhánh theo phương thức.

### 9.1. Gắn sự kiện dữ liệu vào bước

| Bước | Sự kiện hoặc thay đổi có thể ghi | Không nên đồng nhất với |
|---|---|---|
| Khách thêm hàng | CartItemAdded | OrderLineCreated |
| Khách đặt đơn | OrderPlaced | PaymentCaptured |
| Giữ hàng | StockReserved | StockDispatched |
| Tạo kiện | ShipmentPacked | ShipmentDelivered |
| Chấp nhận thanh toán | PaymentAuthorized | PaymentCaptured |
| Thu tiền thành công | PaymentCaptured | ProviderSettled |
| Giao kiện | DeliveryConfirmed | OrderFullyFulfilled |
| Khách yêu cầu trả | ReturnRequested | ItemReceived |
| Kho nhận hàng trả | ReturnItemReceived | RefundCompleted |
| Tiền hoàn xong | RefundSucceeded | ReturnApproved |

Những tên event là **ứng viên mô hình**. Cần hỏi nguồn có thực sự phát sự kiện như vậy hay chỉ cập nhật trạng thái hiện hành. Không tự coi tên event minh họa là hợp đồng hiện có.

## 10. Ghi hai nhánh quy trình chi tiết: web và POS

Hai kênh cùng bán sản phẩm nhưng có thể có điểm chốt khác nhau.

### 10.1. Luồng website giả định

~~~text
Cart
 -> CheckoutStarted
 -> OrderPlaced
 -> InventoryReserved
 -> PaymentAuthorized/Captured (tùy phương thức)
 -> Shipment(s)
 -> DeliveryConfirmed
 -> OrderCompleted
~~~

Câu hỏi:

- Giỏ và đơn có cùng ID không?
- Giá được chốt ở CheckoutStarted hay OrderPlaced?
- Đơn có thể tồn tại khi inventory reservation thất bại không?
- Nếu payment timeout nhưng thực sự được capture, hệ thống kiểm tra lại ra sao?
- Nếu shipment giao một phần, order status thể hiện gì?

### 10.2. Luồng POS giả định

~~~text
POS transaction started
 -> Scan item lines
 -> Apply discount
 -> Collect payment / record COD if policy permits
 -> Issue receipt
 -> Release goods at counter
 -> Transaction finalized
~~~

Câu hỏi:

- POS transaction có phải một SalesOrder cùng loại với website order không?
- Nếu khách trả hàng nhưng không có tài khoản, identity nào dùng để tìm giao dịch?
- In biên lai trước hay sau capture?
- POS offline có cấp local ID không? Cần namespace khi đồng bộ?
- Một lần quét SKU hai lần tạo hai line hay tăng quantity của một line?

### 10.3. Tách điều “đã xảy ra” và điều “được phép”

Ví dụ dữ liệu quan sát thấy POS đã tạo giao dịch không có khách đăng ký. Điều này chứng minh **thực tế có guest sale**, chưa đủ chứng minh mọi loại sản phẩm và phương thức đều được phép guest sale. Cần xác nhận rule theo kênh, loại đơn và giai đoạn áp dụng.
## 11. Tình huống xuyên suốt để kiểm tra thuật ngữ

Nhóm khảo sát nhận một tình huống minh họa từ hệ thống bán lẻ. Tất cả số tiền được giả định bằng **VND**, chưa xét thuế và phí thanh toán của bên thứ ba để bài tập tập trung vào cấu trúc dữ liệu.

~~~text
Order: WEB-O145
Tenant: RETAIL-VN
Channel: WEB
Customer: C501

Line L1: SKU-A × 2, đơn giá 120.000
Line L2: SKU-B × 1, đơn giá  80.000

Tổng giá hàng trước giảm:            320.000
Giảm giá trên L1: 10.000 × 2 =       -20.000
Giá trị hàng sau giảm:               300.000
Phí giao hàng:                        30.000
Số tiền khách phải trả cho đơn:      330.000
~~~

Hệ thống ghi nhận:

~~~text
Payment P1: captured 200.000
Payment P2: captured 130.000
Tổng captured:      330.000

Shipment S1: SKU-A × 1, SKU-B × 1
Shipment S2: SKU-A × 1

Return R1:  SKU-A × 1 (từ một shipment xác định)
Refund F1:  110.000 (120.000 - 10.000 giảm giá phân bổ)

Giả định phí giao hàng không được hoàn.
Sau refund, số captured trừ refund: 220.000
~~~

Đây là **một** order, **hai** order lines, **hai** payment captures, **hai** shipments, **một** return request/line và **một** refund. Nếu thiết kế bảng Order có các cột payment_id, shipment_id và refund_id đơn trị, mô hình có thể mất thông tin hoặc phải cập nhật đè.

### 11.1. Công thức kiểm tra số học

| Giá trị | Phép tính | Kết quả |
|---|---|---:|
| Gross merchandise | 2 × 120.000 + 1 × 80.000 | 320.000 |
| Item discount | 2 × 10.000 | 20.000 |
| Net merchandise trước trả hàng | 320.000 − 20.000 | 300.000 |
| Order payable | 300.000 + 30.000 | 330.000 |
| Captured amount | 200.000 + 130.000 | 330.000 |
| Return-adjusted merchandise | 300.000 − 110.000 | 190.000 |
| Net captured sau refund | 330.000 − 110.000 | 220.000 |

**220.000** ở dòng cuối không mặc nhiên là **doanh thu kế toán**: đó là **captured minus refunded** trong tình huống ví dụ, có cả phí vận chuyển 30.000, và chưa xét thuế, thời điểm ghi nhận hoặc chính sách kế toán.

### 11.2. Hai kiểu số lượng khác nhau

- **Ordered quantity** của SKU-A: 2.
- **Shipped quantity** của SKU-A: 2 qua S1 và S2.
- **Returned quantity** của SKU-A: 1.
- **Retained quantity** của SKU-A sau trả: 1, nếu không có mất mát/đổi hàng và hai shipment đã giao thực tế.

Không nên đặt một cột **quantity** ở bảng Order rồi dùng cho mọi truy vấn. Quantity phải gắn **grain** và loại hoạt động.

## 12. Khảo sát thanh toán: attempt, authorization, capture và refund

Từ “thanh toán” có thể chỉ các đối tượng khác nhau:

| Thuật ngữ | Grain | Mốc nghiệp vụ | Câu hỏi cần hỏi |
|---|---|---|---|
| **Payment intent** | Một ý định trả một khoản | Khách chọn cách trả | Có bao nhiêu intent cho một order? |
| **Payment attempt** | Một lần thử với cổng/phương thức | Gửi yêu cầu tới provider | Retry có cùng attempt ID không? |
| **Authorization** | Một khoản được cho phép giữ/chấp thuận | Provider phản hồi | Có thể hết hạn hoặc bị hủy? |
| **Capture** | Một lần thu tiền được provider ghi nhận | Captured/succeeded | Có partial/multiple capture không? |
| **Settlement** | Một lần đối soát/chuyển tiền theo quy tắc provider | Ngày đối soát | Có khác ngày capture không? |
| **Refund request** | Một yêu cầu hoàn | CSKH/khách đề nghị | Có bị từ chối không? |
| **Refund transaction** | Một lần thực hiện trả tiền về | Provider thực hiện | Một request có thể tạo nhiều lần hoàn? |

Câu hỏi quyết định: “Một Payment có thể có nhiều transaction hay không?” Nếu có, **Payment** có thể là aggregate chứa attempts/captures/refunds; còn từng transaction cần **ID riêng và thời gian riêng**.

### 12.1. Trường hợp thất bại rồi retry

~~~text
Attempt A1: timeout, trạng thái chưa xác định
Attempt A2: succeeded, captured 130.000
Callback muộn của A1: provider báo captured 130.000
~~~

Nếu hệ thống không đối chiếu transaction ID và idempotency, có thể thu hai lần. Glossary phải định nghĩa rõ **successful capture**, **unresolved attempt**, **duplicate callback** và quy trình reconciliation. Không dùng cột paid=true làm bằng chứng duy nhất.

### 12.2. Điều tra khi nghiệp vụ nói “đã thanh toán”

Hỏi:

- Đã **ủy quyền** hay đã **capture**?
- Đã có tiền vào tài khoản chưa, hay provider chỉ xác nhận capture?
- Có reversal/refund không?
- “Đã thanh toán” áp dụng cho cả đơn hay chỉ một khoản?
- Khi COD, thông tin nào chứng minh đã nhận tiền?
- Thời gian nào được dùng cho đối soát?

Khi câu trả lời không giống nhau giữa các bộ phận, không gộp thành một trạng thái duy nhất không có ngữ nghĩa rõ.

## 13. Khảo sát giao hàng và trả hàng: dòng, kiện, lần giao

Một đơn có hai shipment trong ví dụ là cơ hội tìm **quan hệ nhiều-nhiều**:

~~~mermaid
erDiagram
    SALES_ORDER ||--|{ ORDER_LINE : "gồm"
    SALES_ORDER ||--o{ SHIPMENT : "được thực hiện qua"
    SHIPMENT ||--|{ SHIPMENT_LINE : "chứa"
    ORDER_LINE ||--o{ SHIPMENT_LINE : "được phân bổ tới"
    ORDER_LINE ||--o{ RETURN_LINE : "có thể trả"
    RETURN_REQUEST ||--|{ RETURN_LINE : "gồm"
    SHIPMENT ||--o{ DELIVERY_ATTEMPT : "có thể giao nhiều lần"
~~~

Đây là **sơ đồ ứng viên logic**, không phải kết luận mọi shipment chỉ chứa dòng từ một order. Một hệ thống gom kiện xuyên order cần quan hệ Shipment–Order phức tạp hơn và phải được xác nhận.

### 13.1. Những trạng thái cần định nghĩa riêng

- **Shipment packed:** kiện đã được đóng gói.
- **Dispatched:** kho đã bàn giao cho đơn vị vận chuyển.
- **In transit:** kiện đang trên đường.
- **Delivered:** kiện được ghi nhận giao thành công theo nguồn có thẩm quyền.
- **Delivery attempt failed:** một lần giao thất bại, chưa chắc shipment bị hủy.
- **Returned to sender:** kiện quay về kho do không giao thành công.
- **Return requested:** khách yêu cầu trả một số lượng.
- **Return received:** hàng trả đã được nhận.
- **Return accepted:** quyết định chấp thuận trả, có thể kèm kiểm định.
- **Refund succeeded:** dòng tiền hoàn đã thành công.

**Return received** chưa chắc là **refund succeeded**. Một trong các công việc khảo sát là tìm xem hệ thống hiện đang gộp hai mốc này thành một status hay không.

### 13.2. Nhiều sự kiện không đồng nghĩa nhiều đối tượng

Một kiện có thể có ba **DeliveryAttempt**: giao thất bại hai lần rồi thành công. Cần phân biệt **shipment identity** và **attempt identity**, tránh biến một kiện thành ba shipment khi đếm.

## 14. Khảo sát tồn kho: stock on hand, reserved và available

Nhân viên Sales nói “hết hàng” nhưng Kho nói “còn 15 chiếc”. Có thể cả hai đều đúng nếu đang nói hai loại số lượng.

Một công thức mô hình hóa khả dĩ:

~~~text
Available-to-promise
= On-hand
- Reserved
- Blocked
+ nguồn cung khả dụng đã được chính sách chấp nhận (nếu có)
~~~

Các thành phần phải được định nghĩa trong **phạm vi kho, lô, SKU và thời điểm**, không mặc định lấy công thức đơn giản cho mọi doanh nghiệp.

| Thuật ngữ | Ý nghĩa cần khảo sát |
|---|---|
| On-hand | Số lượng vật lý được ghi nhận đang ở kho |
| Reserved | Số lượng đã được giữ cho nhu cầu/đơn cụ thể |
| Blocked | Số lượng bị chặn do kiểm định, hỏng hoặc lý do khác |
| Available-to-promise | Số lượng có thể hứa đáp ứng theo rule nguồn |
| Picked | Đã nhặt hàng nhưng chưa chắc xuất kho |
| Dispatched | Đã rời kho theo chứng từ xuất |
| In-transit | Đang ở giao vận |
| Returned-not-inspected | Đã về kho nhưng chưa được chấp nhận bán lại |

### 14.1. Một order reservation có thể bị tách

SKU-A qty 2 được giữ ban đầu tại kho W1. Sau đó chỉ giao 1 từ W1, giao 1 từ W2. Vậy **reservation** không nhất thiết là một số duy nhất trên order; có thể cần (orderLine, warehouse, reservationId, quantity, status).

Nếu người khảo sát chỉ hỏi “có quantity tồn không?” rồi mô hình hóa một cột product.stock, các tình huống đa kho và giữ chỗ sẽ làm thiết kế sai.

## 15. Trạng thái là vòng đời, không chỉ một enum dài

Một Order có thể có nhiều chiều trạng thái độc lập:

- **Order lifecycle:** draft, placed, confirmed, cancelled, completed.
- **Payment state:** unpaid, partially captured, captured, partially refunded.
- **Fulfillment state:** unallocated, reserved, partially shipped, fully shipped.
- **Delivery state:** not dispatched, in transit, partially delivered, delivered.
- **Return state:** none, requested, partially returned, returned.

Đừng cố đưa tất cả vào một enum:

~~~text
ORDER_PAID_SHIPPED_PARTIAL_DELIVERED_REFUND_PENDING
~~~

Số tổ hợp bùng nổ và nhiều state không hợp lệ khó kiểm soát. Khảo sát cần xác định **nguồn của từng chiều trạng thái** và khi nào một màn hình hiển thị trạng thái tổng hợp.

### 15.1. Ma trận một vài tổ hợp

| Order | Payment | Fulfillment | Có thể xảy ra? |
|---|---|---|---|
| Placed | Unpaid | Unreserved | Có thể, tùy kênh |
| Confirmed | PartiallyCaptured | Reserved | Có thể nếu trả nhiều đợt |
| Confirmed | Captured | PartiallyShipped | Có thể |
| Cancelled | Refunded | PartiallyShipped | Cần làm rõ xử lý kiện đã xuất |
| Completed | Captured | Returned | Cần định nghĩa completed có được tái mở không |
| Draft | FullyShipped | — | Thường bất thường, cần kiểm tra ngoại lệ |

**“Có thể”** trong bảng là giả thuyết của bài tập. Nhóm học viên phải gắn CONFIRMED/REJECTED/OPEN theo quyết định của stakeholder.

### 15.2. Lưu chuyển trạng thái có cần lịch sử không?

Nếu chỉ giữ current_status, hệ thống có thể trả lời “đơn hiện đang gì?” nhưng khó trả lời “đơn được xác nhận lúc nào?” và “đã từng trở về trạng thái nào?”.

Khảo sát cần quyết định có cần:

- Event log với event_id, actor, timestamp.
- State history với [valid_from, valid_to).
- Bitemporal history nếu phải phân biệt thời gian hiệu lực và lúc hệ thống biết.
- Audit trail cho chỉnh sửa thủ công.

Không thêm event sourcing chỉ vì cần lịch sử; có thể dùng bảng history hoặc audit đủ nhu cầu. Nhưng nếu cần tái dựng timeline, mỗi mốc quan trọng phải có nghĩa và nguồn tin cậy.

## 16. Khảo sát thời gian: mỗi hệ thống dùng mốc nào?

Một đơn có thể có:

| Mốc thời gian | Câu hỏi | Nguồn dự kiến |
|---|---|---|
| cart_created_at | Giỏ được tạo lúc nào? | Web/POS |
| order_placed_at | Khách xác nhận đặt lúc nào? | Sales |
| order_accepted_at | Đơn được hệ thống chấp nhận lúc nào? | Sales |
| payment_authorized_at | Provider chấp nhận giữ tiền lúc nào? | Payment |
| captured_at | Khoản tiền được ghi nhận capture lúc nào? | Payment/provider |
| shipment_dispatched_at | Hàng rời kho lúc nào? | Warehouse |
| delivered_at | Hãng vận chuyển ghi giao thành công khi nào? | Delivery |
| return_requested_at | Khách yêu cầu trả khi nào? | CSKH |
| return_received_at | Kho nhận lại hàng khi nào? | Warehouse |
| refunded_at | Tiền hoàn thành công khi nào? | Payment |
| source_event_at | Nguồn nói sự kiện xảy ra lúc nào? | Hệ nguồn |
| ingested_at | Hệ thống tích hợp nhận dữ liệu lúc nào? | Data pipeline |

Không tự coi **order_placed_at = row_created_at**. Nếu sàn đối tác gửi dữ liệu muộn, hai timestamp có thể cách nhau nhiều giờ.

### 16.1. Ví dụ qua nửa đêm

~~~text
23:55 ngày 30/06 (giờ Việt Nam):
  Khách đặt đơn trên sàn đối tác.

00:15 ngày 01/07 (giờ Việt Nam):
  Hệ thống nội bộ nhận và lưu đơn.
~~~

Báo cáo “đơn được khách đặt ngày 30/06” khác báo cáo “đơn được hệ thống nhận ngày 01/07”. Cả hai có thể có ích nếu **định nghĩa thời gian** rõ ràng.

Khi viết glossary, các thuật ngữ **Order Date**, **Ingestion Date** và **Payment Date** phải có công thức, timezone và phạm vi.

### 16.2. Điểm cắt thời gian của các số đo

Nếu báo cáo doanh số “tính đến 23:59 ngày cuối tháng”, hãy hỏi:

- Theo **ngày giờ địa phương nào**?
- Dữ liệu đến muộn có được backfill không?
- Báo cáo có được restate khi refund tháng sau không?
- Có snapshot đóng kỳ hay truy vấn live?
- Mốc cuối cùng là **[start, next_start)** để tránh mất microsecond hay không?

Những câu hỏi này ảnh hưởng mô hình temporal và phân tích sau này.

## 17. Lập bản đồ nguồn dữ liệu và hệ thống sở hữu

Không thể tạo glossary đáng tin nếu không biết dữ liệu nào đến từ nguồn có thẩm quyền.

| Khái niệm | Nguồn tạo dự kiến | Nguồn có thẩm quyền cần xác nhận | Người dùng downstream |
|---|---|---|---|
| Order | POS/Web/Marketplace | Sales order service hoặc nguồn ngoài theo scope | Kho, payment, BI |
| Product/SKU | Catalog/PIM | Catalog owner | Sales, kho, BI |
| Price snapshot | Checkout/POS | Sales transaction | Kế toán, BI |
| Inventory reservation | Inventory service | Inventory | Kho, Sales |
| Payment attempt/capture | Payment provider/adapter | Payment ledger/integration | Sales, kế toán, BI |
| Shipment/attempt | WMS/TMS/carrier | Fulfillment/delivery theo event | CSKH, BI |
| Return request | CSKH/web | Return management | Kho, Payment |
| Refund transaction | Payment provider/finance | Payment/refund service | CSKH, kế toán |
| Customer/account | Identity/CRM | Theo loại identity | Sales, marketing |
| KPI doanh số | BI/finance | Metric owner được duyệt | Lãnh đạo |

Đây là **bảng giả định** cho bài tập; không được coi tên hệ thống là source of truth mặc định ở doanh nghiệp thật.

### 17.1. Một khái niệm có thể có nhiều khóa

Ví dụ:

~~~text
sales_order_id: UUID nội bộ
marketplace_order_id: mã do sàn cấp
external_source_system: tên/ID nguồn
pos_transaction_number: số chứng từ POS
~~~

Cần hỏi:

- Mã ngoài unique trong **toàn sàn, từng cửa hàng hay từng ngày**?
- Nếu order được import lại, dùng khóa nào dedup?
- Nếu sàn thay đổi mã, có crosswalk không?
- Nếu một order được tách thành hai fulfillment units, có bao nhiêu ID?
- Có mối quan hệ one-to-one, one-to-many hay many-to-many giữa các mã không?

### 17.2. Data lineage bản giản lược

~~~mermaid
flowchart LR
    WEB["Web/POS/Marketplace"] --> S["Sales - Order/Line"]
    CAT["Catalog"] --> S
    S --> WH["Warehouse - Reservation/Shipment"]
    S --> PAY["Payment - Attempts/Captures"]
    WH --> RET["Returns"]
    PAY --> REF["Refunds"]
    S --> FACT["Fact Sales Line"]
    WH --> FACT
    PAY --> MET["Finance / Metrics"]
    REF --> MET
    FACT --> MET
~~~

Sơ đồ là **lineage khái niệm**, không có nghĩa một bảng fact nên JOIN đồng thời toàn bộ shipment và payment thô theo order_id; làm như vậy có thể tạo fanout và nhân số liệu.

## 18. Thu thập dữ liệu mẫu mà không rút kết luận sai

Một mẫu khảo sát nên có cả luồng thường, ngoại lệ và các biên.

| Mẫu | Trường hợp | Điều cần học |
|---|---|---|
| T01 | Đơn một dòng, một lần thu tiền, một kiện | Baseline |
| T02 | Đơn hai dòng, hai lần capture | Payment cardinality |
| T03 | Một dòng phân hai shipment | ShipmentLine grain |
| T04 | Hủy trước giao, đã capture | Hủy vs refund |
| T05 | Trả một phần hàng sau giao | ReturnLine, refund allocation |
| T06 | Marketplace retry cùng mã đơn | Idempotency/source namespace |
| T07 | Guest POS không có Customer account | Optional identity |
| T08 | Giao COD, đối soát sau một ngày | Payment vs delivery time |
| T09 | Dữ liệu sàn gửi chậm qua biên ngày | Event time vs ingestion time |
| T10 | Cùng SKU trong hai warehouse | Stock scope |
| T11 | Một sản phẩm đổi category giữa kỳ | Temporal relationship |
| T12 | Refund được tạo nhưng provider thất bại | Refund lifecycle |

**Dữ liệu mẫu là bằng chứng quan sát, không phải toàn bộ quy tắc.** Nếu 100 mẫu đều chỉ có một payment/order, vẫn phải hỏi liệu partial payment có được phép và có thể xuất hiện trong tương lai hay không.

### 18.1. Đối chiếu ba lớp bằng chứng

Với một phát biểu như “một order luôn có một payment”, hãy đối chiếu:

1. **Nghiệp vụ:** người có thẩm quyền chấp nhận quy tắc nào?
2. **Hành vi hệ thống:** luồng API, trạng thái, database đang cho phép điều gì?
3. **Dữ liệu quan sát:** có bản ghi nào bác bỏ hoặc chứng minh giới hạn không?

Khi ba lớp mâu thuẫn, ghi **DISPUTED** và nguyên nhân. Đừng chọn SQL schema làm “sự thật nghiệp vụ” chỉ vì hiện nó có một FK đơn trị.

## 19. Business glossary khác data dictionary như thế nào?

**Business glossary** định nghĩa **khái niệm** được tổ chức sử dụng. **Data dictionary** định nghĩa **cấu trúc dữ liệu cụ thể** như bảng, cột, kiểu dữ liệu, nullability, default, constraints và lineage.

Ví dụ:

~~~text
Business glossary:
  "Đơn hàng" = cam kết mua hàng được ghi nhận với danh tính,
  các dòng hàng và điều kiện thương mại tại một mốc xác nhận.

Data dictionary:
  sales_order.order_id UUID NOT NULL PRIMARY KEY
  sales_order.placed_at TIMESTAMPTZ NULL
  sales_order.status_code VARCHAR(...) NOT NULL
~~~

Một khái niệm có thể được triển khai qua nhiều bảng. Một bảng vật lý có thể chứa dữ liệu của nhiều khái niệm nếu denormalize. Vì vậy glossary và dictionary cần **liên kết**, không phải là một danh sách cột đổi tên.

### 19.1. Kết cấu của một định nghĩa tốt

Một định nghĩa nên:

- Dùng ngôn ngữ nghiệp vụ, tránh định nghĩa bằng đúng tên thuật ngữ.
- Chỉ rõ **sự kiện hoặc điều kiện hình thành**.
- Chỉ rõ **phạm vi bao gồm và loại trừ**.
- Nêu **grain/danh tính** khi khái niệm có bản ghi.
- Phân biệt với những thuật ngữ gần nghĩa.
- Có ví dụ và phản ví dụ.
- Có chủ sở hữu, nguồn bằng chứng, trạng thái và phiên bản.

Ví dụ kém:

> “Đơn hàng là một đơn được tạo trong hệ thống.”

Ví dụ tốt hơn:

> “Đơn hàng là một yêu cầu mua đã được ghi nhận có ID bền vững, gồm các dòng hàng và điều kiện thương mại tại thời điểm chấp nhận. Giỏ hàng chưa xác nhận không được tính là đơn; việc đã thanh toán hoặc giao đủ không phải điều kiện bắt buộc để một đơn tồn tại.”

Định nghĩa sau là **một ứng viên cho tình huống này**; owner còn phải xác nhận chính xác mốc “đã được ghi nhận” và có cho phép draft order không.

## 20. Mẫu cấu trúc một dòng business glossary

| Trường | Ý nghĩa |
|---|---|
| **term_id** | ID ổn định của thuật ngữ |
| **preferred_term_vi** | Tên tiếng Việt chuẩn |
| **preferred_term_en** | Tên tiếng Anh nếu cần |
| **aliases** | Từ đồng nghĩa/tên màn hình cũ |
| **definition** | Định nghĩa nghiệp vụ không vòng vo |
| **scope/context** | Bounded context, tenant, thị trường, kênh |
| **grain** | Một bản ghi/đơn vị đo đại diện cho gì |
| **identity_rule** | Quy tắc định danh, uniqueness scope |
| **inclusions** | Trường hợp được tính |
| **exclusions** | Trường hợp không được tính |
| **example** | Ví dụ đạt định nghĩa |
| **counterexample** | Phản ví dụ giúp phân biệt |
| **related_terms** | Các khái niệm gắn với nó |
| **system_mapping** | Bảng, API, event, field hiện liên quan |
| **owner** | Người có thẩm quyền duyệt |
| **source/evidence** | Policy, phỏng vấn, data profiling, quyết định |
| **status/version** | Draft/Disputed/Approved, ngày/version |

Không nhất thiết mỗi thuật ngữ phải có đủ 17 trường khi xuất bản bản tóm tắt. Nhưng **glossary có thẩm quyền** phải có nơi lưu những thông tin cần thiết để truy vết và tránh tranh luận lặp lại.

### 20.1. Dạng YAML tham khảo cho một thuật ngữ

~~~yaml
term_id: TERM-SALES-ORDER
preferred_term_vi: "Đơn hàng"
preferred_term_en: "Sales Order"
scope: "Sales / đa kênh"
definition: >-
  Một yêu cầu mua đã được hệ thống có thẩm quyền ghi nhận,
  có định danh bền vững và các điều kiện thương mại;
  việc thanh toán hoặc giao hàng có thể xảy ra sau.
grain: "Một order được tạo, không phải một dòng sản phẩm"
identity_rule: "Global order ID; mã nguồn có namespace"
inclusions: "Đơn đã đặt dù chưa được thanh toán"
exclusions: "Giỏ chưa xác nhận, payment attempt, shipment"
status: "DRAFT"
owner: "Sales domain owner"
evidence: "OBS-001 / workshop Sales"
~~~

Đây là **ví dụ mẫu của một dòng glossary**, không phải metadata cần ghi vào YAML bài học. Trong ứng dụng thật, nên tách inclusions/exclusions thành danh sách/quan hệ có cấu trúc nếu cần tìm kiếm và quản lý phiên bản.
## 21. Bảng thuật ngữ mẫu: từ khách hàng tới đơn hàng

Bảng sau là **bản nháp tham khảo** để người học đem vào workshop. Trạng thái của tất cả định nghĩa là **DRAFT** cho tới khi owner xác nhận.

| ID | Thuật ngữ chuẩn | Định nghĩa nghiệp vụ dự kiến | Không đồng nhất với |
|---|---|---|---|
| TERM-001 | **Chủ thể mua / Buyer** | Người hoặc tổ chức thực hiện yêu cầu mua theo định danh mà kênh cung cấp | Tài khoản đăng nhập |
| TERM-002 | **Tài khoản khách / Customer Account** | Hồ sơ dùng để xác thực, quản lý quyền và liên hệ khách | Mọi người mua vãng lai |
| TERM-003 | **Khách vãng lai / Guest Buyer** | Người mua không gắn tài khoản đăng nhập trong giao dịch hiện tại | Khách không có danh tính ở mọi hệ thống |
| TERM-004 | **Giỏ hàng / Cart** | Tập lựa chọn hàng và điều kiện dự kiến trước mốc xác nhận | Đơn hàng đã ghi nhận |
| TERM-005 | **Đơn hàng / Sales Order** | Yêu cầu mua có ID bền vững, các điều kiện thương mại và trạng thái vòng đời | Payment/Shipment |
| TERM-006 | **Dòng đơn / Order Line** | Một vị trí thương mại được ghi trong một đơn, gồm SKU, quantity, giá chốt và ưu đãi liên quan | SKU hoặc một kiện giao |
| TERM-007 | **Sản phẩm / Product** | Đối tượng catalog có identity và thuộc tính nghiệp vụ; có thể gồm nhiều biến thể | Một SKU ở mọi tình huống |
| TERM-008 | **SKU / Stock Keeping Unit** | Đơn vị sản phẩm/biến thể được quản lý theo mã trong namespace catalog/kho đã xác định | Tên sản phẩm |
| TERM-009 | **Giá chốt dòng / Captured Unit Price** | Đơn giá dùng để tính giao dịch tại mốc được xác định | Giá niêm yết hiện tại |
| TERM-010 | **Ưu đãi / Promotion** | Quy tắc khuyến mại có điều kiện và kỳ áp dụng | Số tiền giảm của một dòng |
| TERM-011 | **Giảm giá / Discount Amount** | Khoản giảm được phân bổ cho đơn hoặc dòng theo quy tắc chốt | Phí hoàn, hoàn tiền |
| TERM-012 | **Phí giao hàng / Shipping Charge** | Khoản phí khách phải trả cho dịch vụ giao trong đơn | Chi phí vận chuyển thực của doanh nghiệp |

### 21.1. Tình huống kiểm tra định nghĩa đầu tiên

**Một Order Line có thể chứa SKU trùng một Order Line khác hay không?**

Ví dụ:

~~~text
Line 1: SKU-A, qty 1, ưu đãi thành viên.
Line 2: SKU-A, qty 1, ưu đãi khác.
~~~

Nếu nghiệp vụ cho phép, không thể dùng **UNIQUE(order_id, sku_id)** như bất biến chung. Có thể dùng **UNIQUE(order_id, line_no)** hoặc line_id riêng. Đây là một hệ quả mô hình xuất phát từ **khái niệm dòng đơn**, không phải từ kiểu database.

### 21.2. Cần chốt grain của Product và SKU

Một Product có thể là mô hình sản phẩm chung, còn SKU là biến thể bán/lưu kho. Ví dụ áo “Model A” có SKU cho từng size/màu. Nhưng ở một số doanh nghiệp, Product và SKU được dùng một-một. Không áp một cấu trúc không cần thiết nếu stakeholder xác nhận ngữ nghĩa khác.

**Glossary phải mô tả đúng nghiệp vụ**, không sao chép định nghĩa chung rồi ép dữ liệu khớp.

## 22. Bảng thuật ngữ mẫu: thanh toán, kho, giao hàng và trả hàng

| ID | Thuật ngữ chuẩn | Grain/ngữ nghĩa dự kiến | Điểm dễ nhầm |
|---|---|---|---|
| TERM-013 | **Lần thử thanh toán / Payment Attempt** | Một lần tương tác thanh toán với phương thức/provider | Không chắc đã thu tiền |
| TERM-014 | **Ủy quyền / Authorization** | Phản hồi cho phép giữ/chấp nhận khoản dự kiến | Không đồng nghĩa capture |
| TERM-015 | **Thu tiền / Capture** | Một transaction ghi nhận thành công việc thu khoản được xác định | Không mặc nhiên là settlement |
| TERM-016 | **Đối soát / Settlement** | Bước xác nhận/chuyển tiền theo hợp đồng với provider | Không cùng timestamp capture |
| TERM-017 | **Giữ hàng / Inventory Reservation** | Một phân bổ khả dụng cho nhu cầu tại kho và thời điểm | Không phải xuất kho |
| TERM-018 | **Tồn kho ghi nhận / On-hand** | Số lượng đang được quản lý tại vị trí/kho theo nguồn WMS | Không luôn bán được |
| TERM-019 | **Số lượng khả dụng / Available-to-promise** | Kết quả tính theo chính sách từ tồn, giữ chỗ và trạng thái khác | Không chỉ on-hand |
| TERM-020 | **Kiện giao / Shipment** | Đơn vị fulfillment/giao có ID riêng, chứa các dòng giao | Không phải toàn bộ order |
| TERM-021 | **Dòng kiện / Shipment Line** | Một phân bổ số lượng OrderLine vào Shipment | Không phải một OrderLine mới |
| TERM-022 | **Lần giao / Delivery Attempt** | Một lần hãng vận chuyển thử giao kiện | Không phải Shipment mới |
| TERM-023 | **Yêu cầu trả / Return Request** | Một hồ sơ đề nghị trả hàng, có quyết định và trạng thái | Không phải Refund |
| TERM-024 | **Dòng trả / Return Line** | Một số lượng trả gắn dòng bán/nguồn giao theo chính sách | Không phải SKU tổng hợp |
| TERM-025 | **Hoàn tiền / Refund Transaction** | Một lần trả tiền về phương thức/đích theo phương án duyệt | Không chắc đã nhận lại hàng |
| TERM-026 | **Đơn hủy / Cancelled Order** | Đơn được chuyển sang trạng thái hủy theo chính sách | Không đồng nhất returned order |
| TERM-027 | **Hàng trả đã nhận / Received Return Item** | Hàng trả về đã được ghi nhận tại điểm tiếp nhận | Không tự trở thành hàng bán lại được |
| TERM-028 | **Lượng giao thành công / Delivered Quantity** | Số lượng có bằng chứng giao thành công tại mốc cắt | Không phải shipped quantity |

### 22.1. Định nghĩa một metric phải có công thức và thời gian

Một số mục trong glossary là **entity**, số khác là **measure/metric**. Với metric, chỉ một câu mô tả là chưa đủ. Nên ghi:

~~~text
TERM-METRIC-GROSS-MERCH
Tên: Giá trị hàng trước giảm (Gross Merchandise Amount)
Grain tính: các dòng đơn được chọn trong kỳ
Định nghĩa: SUM(ordered_quantity × captured_unit_price)
Bao gồm: giá trị hàng trước discount
Không bao gồm: phí vận chuyển, hoàn tiền, thuế theo
  phạm vi ví dụ chưa xét thuế
Time axis: order_placed_at theo timezone được duyệt
Owner: Sales/Finance (chờ xác nhận)
Status: DRAFT
~~~

**Đừng tự gọi đại lượng trên là “doanh thu kế toán”.** Để tính doanh thu tài chính còn cần cơ sở ghi nhận, thuế, hoàn trả, kỳ, chính sách tài chính và người duyệt.

### 22.2. Bốn số dễ bị đặt cùng tên “doanh số”

Với mẫu order O145:

| Tên kỹ thuật đề xuất | Công thức trong ví dụ | Giá trị |
|---|---|---:|
| **gross_merchandise_amount** | Giá hàng trước giảm | 320.000 |
| **net_merchandise_before_returns** | Gross trừ item discount | 300.000 |
| **order_payable_amount** | Net merchandise cộng phí giao | 330.000 |
| **net_captured_after_refunds** | Tổng capture trừ refund thành công | 220.000 |

Nếu dashboard A gọi 330.000 là doanh số, dashboard B gọi 300.000 là doanh số, cả hai có thể đang có metric đúng cho mục đích riêng, nhưng **nhãn chung gây hiểu sai**. Cần tên chuẩn, công thức và chú thích phạm vi.

## 23. Từ đồng nghĩa, đồng âm và những xung đột thuật ngữ

Một glossary không chỉ là từ điển định nghĩa. Nó là **cơ chế phát hiện bất đồng và thống nhất ngôn ngữ**.

### 23.1. Từ đồng nghĩa khác định nghĩa

Ví dụ nhân viên POS nói “phiếu bán”, web nói “đơn”, ERP nói “sales document”. Ba từ có thể cùng chỉ SalesOrder hoặc ba loại chứng từ khác nhau tùy thời điểm chốt.

Hãy tạo:

~~~text
Preferred term: Sales Order / Đơn hàng
Aliases được xác nhận: "Đơn web", "Đơn POS" (theo phạm vi cụ thể)
Không đồng nghĩa: Cart, Invoice, Receipt, Shipment
~~~

Không tự khai báo **invoice** là alias của order: hóa đơn và đơn hàng có thể có quan hệ nhiều-một hoặc điều kiện ghi nhận khác.

### 23.2. Một từ mang nhiều nghĩa theo bounded context

| Từ đang dùng | Sales hiểu | Kho hiểu | Finance hiểu | Hướng xử lý |
|---|---|---|---|---|
| Thành công | Khách đặt đơn | Hàng giao đủ | Tiền ghi nhận/đối soát | Đặt tên OrderAccepted, Delivered, Captured/Settled |
| Hoàn | Trả hàng | Hàng quay kho | Hoàn tiền | Return vs Refund |
| Tồn | Có thể bán | On-hand | Giá trị tồn kho | ATP, QuantityOnHand, InventoryValue |
| Khách | Tài khoản | Người nhận hàng | Đối tượng trên chứng từ | Buyer, Account, Recipient, BillingParty |
| Doanh số | Giá trị đơn | Số hàng xuất | Chỉ tiêu tài chính | Metric contract riêng |
| Hủy | Hủy đơn | Hủy xuất kho | Đảo giao dịch/void | Tách lifecycle |

### 23.3. Quy trình giải quyết tranh chấp

1. Ghi đúng **hai hoặc nhiều định nghĩa** đang dùng, kèm người phát biểu.
2. Tìm **giao dịch phản ví dụ** khiến chúng cho kết quả khác.
3. Xác định **bounded context**: có thật cần cùng một thuật ngữ chung không?
4. Nếu là hai khái niệm, đặt **hai tên rõ** và quan hệ giữa chúng.
5. Nếu cần một metric chung, chỉ định owner, công thức, thời gian, đối tượng và mức trễ dữ liệu.
6. Cập nhật glossary, rule catalog, API/data contract và ví dụ.
7. Ghi decision ID, ngày hiệu lực và những dashboard phải sửa.
8. Yêu cầu owner phê duyệt; không để analyst tự quyết vấn đề kế toán hay chính sách kinh doanh.

**Mục tiêu không phải buộc mọi phòng ban dùng cùng một con số cho mọi mục đích**, mà là mỗi thuật ngữ đủ rõ để không mâu thuẫn trong cùng phạm vi.

## 24. Chuyển glossary thành danh sách ứng viên thực thể và grain

Sau khảo sát, có thể lập bảng **candidate model**. Đây là cầu nối sang thiết kế logic, chưa phải lời tuyên bố mỗi dòng là một bảng bắt buộc.

| Ứng viên | Grain | Khóa ứng viên | Quan hệ cần xác minh |
|---|---|---|---|
| **SalesOrder** | Một đơn | global_order_id | Đơn có N lines/payments/shipments |
| **OrderLine** | Một dòng của đơn | line_id hoặc (order_id, line_no) | Thuộc một Order, tham chiếu SKU snapshot |
| **ProductIdentity** | Một sản phẩm logic | tenant/source/product_code | Có N SKU/version |
| **SkuIdentity** | Một mã SKU trong namespace | tenant/catalog/sku_code | Thuộc Product theo policy |
| **PaymentAttempt** | Một lần thử trả | attempt_id hoặc provider ref có namespace | Thuộc intent/order/payment |
| **PaymentCapture** | Một lần thu thành công | capture_id | Có thể gắn order qua allocation |
| **PaymentAllocation** | Một phần tiền capture phân bổ cho order | allocation_id hoặc composite | Cần nếu capture trả nhiều order |
| **InventoryReservation** | Một phân bổ giữ số lượng tại kho | reservation_id | Gắn orderLine/SKU/warehouse |
| **Shipment** | Một kiện/fulfillment unit | shipment_id | Có N shipment lines |
| **ShipmentLine** | Một quantity được phân bổ vào kiện | shipment_line_id | Gắn OrderLine và Shipment |
| **DeliveryAttempt** | Một lần giao kiện | attempt_id | Gắn Shipment |
| **ReturnRequest** | Một yêu cầu trả | return_request_id | Có N return lines |
| **ReturnLine** | Một quantity trả từ dòng đã mua | return_line_id | Gắn OrderLine/ShipmentLine theo rule |
| **RefundTransaction** | Một lần hoàn tiền | refund_id | Gắn payment capture/return theo policy |
| **CustomerIdentity** | Một hồ sơ chủ thể có scope | canonical_id | Guest vs account/crosswalk |
| **OrderStatusEvent** | Một chuyển trạng thái có thời điểm | event_id | Thuộc Order, có thứ tự |
| **SalesLineFact** | Một dòng fact ở mốc được định nghĩa | source_line_id + snapshot/cutoff | Gắn dimensions/metrics |

### 24.1. Grain phải được viết bằng câu đơn giản

Ví dụ:

> “Một ShipmentLine là một số lượng của một OrderLine được phân bổ vào đúng một Shipment.”

Từ câu này, có thể suy một OrderLine có nhiều ShipmentLines nếu tách kiện. Ngược lại, một record ShipmentLine không được đồng thời đại diện cho ba dòng order vì sẽ khó quy trách nhiệm số lượng.

### 24.2. Khóa nguồn phải kèm namespace

~~~text
Marketplace A:
  source_order_id = 1001

POS Store HN-01:
  local_transaction_id = 1001
~~~

Hai số **1001** có thể hợp lệ đồng thời. Một khóa nguồn có thể cần **(source_system, store_id, local_id)**; chỉ chốt sau khi hỏi hệ phát mã có tái sử dụng trong scope nào.

Dùng UUID làm internal ID hữu ích nhưng không thay thế **source identity** hoặc idempotency key.

### 24.3. Một quan hệ trên sơ đồ chưa chứng minh có FK vật lý

Sales và Payment có thể thuộc hai database. Diagram có đường nối Order–Payment nói về **quan hệ nghiệp vụ**, không tự chứng minh có FOREIGN KEY vật lý xuyên hệ thống.

Phải ghi rõ liên kết được đảm bảo bởi DB constraint, API validation, outbox/CDC hay reconciliation để các nhóm hiểu đúng mức nhất quán.

## 25. Business-rule catalog: từ lời nói thành điều kiện kiểm chứng

Nhiều quy tắc không thể thấy qua ERD hay một row dữ liệu. Dùng rule ID ổn định và ghi **nguồn, phạm vi, trạng thái**.

| Rule ID | Quy tắc dự kiến | Nơi cần xác minh |
|---|---|---|
| BR-001 | OrderLine bắt buộc thuộc một SalesOrder hợp lệ | Sales owner, DB |
| BR-002 | Trong một order, line_no không trùng | Sales, import |
| BR-003 | Order CONFIRMED có ít nhất một dòng hợp lệ | Sales, workflow |
| BR-004 | Ordered quantity của dòng > 0 đối với dòng bán thông thường | Sales, returns exceptions |
| BR-005 | ShipmentLine phải gắn dòng đơn và có quantity > 0 | Kho |
| BR-006 | Tổng shipment quantity không vượt ordered quantity trừ khi có policy riêng | Kho, Sales |
| BR-007 | Capture/refund phải có ID giao dịch chống retry | Payment |
| BR-008 | Tổng refund thành công không vượt captured amount có thể hoàn | Finance, Payment |
| BR-009 | Cùng source order identity không tạo hai order khi retry | Integration |
| BR-010 | ReturnLine cần nguồn mua/dòng đủ điều kiện trả | CSKH, Returns |
| BR-011 | Returned quantity không vượt quantity đã nhận hợp lệ, theo policy | Returns |
| BR-012 | Giá chốt của dòng giữ tính lịch sử khi catalog đổi giá | Sales, Finance |
| BR-013 | Tồn khả dụng phải theo warehouse/SKU/time cụ thể | Kho |
| BR-014 | Giao một phần không được tự đánh dấu toàn đơn fully delivered | Delivery |
| BR-015 | Báo cáo có mốc thời gian, timezone và trạng thái dữ liệu rõ | BI, Finance |
| BR-016 | Dữ liệu nhiều tenant phải giữ đúng scope của mọi FK/identity | Security, DB |

Các rule có thể được sửa sau workshop. Không vội gắn BR-008 vào một CHECK một hàng: tổng refund cần xét **nhiều transaction**, có thể đòi giao dịch có khóa/version hoặc cơ chế reservation.

### 25.1. Mẫu hồ sơ rule đầy đủ

~~~text
rule_id: BR-008
Tên: Giới hạn tiền hoàn thành công
Phạm vi: Một khoản capture hoặc phần tiền có thể hoàn
Mô tả:
  Tổng khoản refund đã thành công không vượt số có thể hoàn
  sau các điều chỉnh/void và phân bổ hợp lệ.
Nguồn: Payment lead + Finance owner
Giả định: Refund chỉ dựa trên captured amount
Trường hợp biên:
  Hai refund chạy song song; một refund failed; retry callback.
Enforcement candidate:
  Transaction/version check + ledger invariant.
Test:
  Hai refund concurrent không cùng vượt số còn lại.
Trạng thái: OPEN – cần xác nhận chính sách.
~~~

**Owner phê duyệt có thể thay đổi rule**, nhưng nếu rule đã được dùng trong code hoặc metric, thay đổi phải có version và phân tích tác động.

## 26. Kiểm chứng bằng một giao dịch, không chỉ bằng định nghĩa trên giấy

Với order WEB-O145, hãy lần theo:

~~~text
SalesOrder O145
 ├─ OrderLine L1: SKU-A, qty 2
 └─ OrderLine L2: SKU-B, qty 1

Payment Captures
 ├─ P1: 200.000
 └─ P2: 130.000

Shipments
 ├─ S1: L1 qty 1; L2 qty 1
 └─ S2: L1 qty 1

Return
 └─ R1: L1 qty 1

Refund
 └─ F1: 110.000
~~~

### 26.1. Tại sao join thô theo order_id dễ nhân số liệu?

Giả sử JOIN bảng SalesOrder với hai PaymentCaptures và hai Shipments theo order_id:

~~~text
O145 × 2 PaymentCaptures × 2 Shipments = 4 hàng kết quả.
~~~

Nếu sau đó tính **SUM(payment.amount)** trực tiếp trên bốn hàng, hai payment có thể bị lặp theo shipment, tạo **660.000** thay vì **330.000**. Nếu JOIN thêm hai order lines, số hàng có thể nhân tiếp.

Đây là **fanout**, không phải bằng chứng order có bốn khoản tiền.

### 26.2. Hướng truy vấn đúng cho từng grain

Tổng captured theo order nên tính **ở grain payment capture** trước:

~~~sql
SELECT
    order_id,
    SUM(captured_amount) AS captured_total
FROM payment_capture
WHERE capture_status = 'SUCCEEDED'
GROUP BY order_id;
~~~

Đây là SQL minh họa sau khi xác nhận rằng mỗi capture row thuộc đúng một order. Nếu payment có thể phân bổ cho nhiều order, cần tính theo **payment_allocation** và không cộng toàn bộ capture vào mọi order.

Tương tự, tổng shipped quantity theo order line phải tính từ ShipmentLine, không lấy COUNT(Shipment) làm số sản phẩm giao.

### 26.3. Cách kiểm chứng một metric

Với metric “Net merchandise before returns”:

1. Viết **grain nguồn**: một OrderLine.
2. Viết **công thức**: quantity × capturedUnitPrice − allocatedItemDiscount.
3. Viết **bộ lọc trạng thái**: những order/line nào được tính.
4. Viết **trục thời gian**: order placed, shipped hoặc ngày khác.
5. Viết **timezone** và quy tắc late data.
6. Xác định **return adjustments** có nằm trong cùng metric hay metric khác.
7. Đối soát ví dụ O145 cho kết quả 300.000.
8. Đưa vào glossary với status và owner.

Nếu bỏ một bước, hai pipeline khác nhau có thể cho ra hai con số đều trông hợp lý.

## 27. Workshop giải quyết xung đột và chốt glossary

Một tình huống thường gặp:

- Sales: “Đơn thành công ngay khi khách xác nhận đặt.”
- Kho: “Đơn thành công khi mọi kiện được giao.”
- Payment: “Đơn thành công khi đủ tiền capture.”
- BI: “Dashboard đang đếm order không hủy.”

Các định nghĩa không thể cùng là một thuộc tính **order_success** nếu không có scope/phân biệt.

### 27.1. Dùng tình huống đối chiếu

| Tình huống | Đã đặt | Đã thu đủ | Đã giao đủ | Không bị hủy |
|---|---|---|---|---|
| O1 vừa đặt, chưa thu tiền | Có | Không | Không | Có |
| O2 đã capture, chưa giao | Có | Có | Không | Có |
| O3 giao đủ, COD chưa đối soát | Có | Chưa chắc | Có | Có |
| O4 giao một phần, sau đó hủy phần còn lại | Có | Tùy | Không | Tùy quy tắc |
| O5 đã giao đủ rồi hoàn tiền một phần | Có | Có trước refund | Có | Có thể |

Nhóm có thể thống nhất các tên riêng:

- **OrderPlacedCount**: số order đạt mốc đặt.
- **FullyCapturedOrderCount**: số order được ghi nhận đủ capture theo policy.
- **FullyDeliveredOrderCount**: số order có đủ lượng giao theo policy.
- **NonCancelledOrderCount**: số order không thuộc trạng thái hủy tại mốc cắt.

Đây là **bốn KPI khác nhau**, không phải bốn cách viết của cùng một KPI.

### 27.2. Mẫu decision log

~~~text
DEC-007
Vấn đề:
  Thuật ngữ "đơn thành công" có 4 cách hiểu.

Quyết định:
  Không dùng thuật ngữ chung trong metric mới.
  Dùng 4 tên khác biệt như trong glossary.

Tác động:
  Dashboard Sales, Finance, Delivery và API metric.
  Yêu cầu người dùng chọn đúng metric.

Owner: Product + Finance + BI
Status: PROPOSED (chờ phê duyệt)
Effective version: sau khi được duyệt
Evidence: Workshop W-02, ví dụ O1–O5
~~~

**Đừng tự ghi APPROVED** khi mới có một người phát biểu. Trường status giúp reader biết điều gì thật sự có thẩm quyền.

## 28. Hướng dẫn thực hành theo phiên: nhóm 4–6 người

Bài có thể tổ chức thành các phiên thực hành có người đóng vai stakeholder và người phản biện. Nếu tự học, hãy tự trả lời cả hai phía rồi kiểm tra với dữ liệu mẫu.

| Phiên | Nhiệm vụ | Đầu ra |
|---|---|---|
| **Phiên 1** | Đọc tình huống; chọn scope; tạo stakeholder map | D01, D02 |
| **Phiên 2** | Phỏng vấn mô phỏng Sales, Payment, Kho, CSKH | Ghi chú OBS/HYPOTHESIS/OPEN |
| **Phiên 3** | Vẽ as-is, luồng chính và ngoại lệ | D03, D04 |
| **Phiên 4** | Xây 20–30 thuật ngữ, thêm alias và phản ví dụ | D05 |
| **Phiên 5** | Tìm nguồn có thẩm quyền, grain và identity | D06, D09 |
| **Phiên 6** | Viết business rules, tranh chấp và quyết định | D07, D08 |
| **Phiên 7** | Review chéo với transaction O145 và 12 mẫu biên | D10 |
| **Phiên 8** | Chốt glossary phiên đầu, chuẩn bị handoff logical modeling | Bộ hồ sơ có version |

### 28.1. Nhiệm vụ phỏng vấn mô phỏng

Mỗi nhóm chọn bốn vai: Sales owner, Payment lead, Warehouse lead và Data analyst. Người làm analyst phải hỏi cho đến khi giải thích được:

1. Khi nào một Cart trở thành Order?
2. Có những loại Order nào?
3. Một OrderLine có thể xuất hiện trong hai Shipment không?
4. Một order có thể có hai capture thành công không?
5. Điều gì tạo ReturnRequest và khi nào hàng đã nhận?
6. Refund thất bại khác Return bị từ chối thế nào?
7. Khi nào một SKU được xem là bán được tại kho cụ thể?
8. Kênh nào cấp mã nguồn và namespace unique của nó?
9. Dữ liệu đến muộn làm thay đổi KPI nào?
10. Người nào duyệt công thức “doanh thu”?
11. Hệ thống đang dùng công thức nào, policy muốn công thức nào?
12. Các mốc có timezone và đơn vị đo thống nhất không?

Mọi câu chưa có đủ bằng chứng phải được lưu **OPEN**, không điền bằng giả định.

### 28.2. Nhiệm vụ tự hoàn thành

- Vẽ một flowchart as-is có ít nhất ba nhánh ngoại lệ.
- Lập bảng 25 thuật ngữ có tối thiểu definition, scope, examples, exclusions, owner, status.
- Chọn 10 rule có mã BR-xxx và gắn với ít nhất một test case.
- Xây 6 ví dụ phản biện cho các thuật ngữ dễ nhầm.
- Tạo candidate model gồm ít nhất Order, OrderLine, PaymentCapture, ShipmentLine, ReturnLine.
- Viết một data lineage từ order web tới dashboard BI.
- Giải thích vì sao JOIN thô payment và shipment có thể tạo fanout.
- Phân biệt bốn mốc order date, capture date, delivered date và ingestion date.
- Ghi ít nhất 5 câu hỏi mở thực sự quan trọng.
- Tổ chức review: một người khác phải đọc tài liệu và giải thích được giao dịch O145.

## 29. Đáp án định hướng và những điều chưa nên chốt

Đây là **hướng dẫn đánh giá**, không phải một schema chuẩn duy nhất cho mọi nhà bán lẻ.

### 29.1. Sơ đồ ứng viên sau khảo sát

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : "có thể đặt"
    SALES_ORDER ||--o{ ORDER_LINE : "gồm"
    ORDER_LINE ||--o{ SHIPMENT_LINE : "được phân bổ"
    SHIPMENT ||--o{ SHIPMENT_LINE : "chứa"
    SHIPMENT ||--o{ DELIVERY_ATTEMPT : "được giao qua"
    SALES_ORDER ||--o{ PAYMENT_CAPTURE : "có thể được thu"
    SALES_ORDER ||--o{ RETURN_REQUEST : "có yêu cầu trả"
    RETURN_REQUEST ||--o{ RETURN_LINE : "gồm"
    ORDER_LINE ||--o{ RETURN_LINE : "là nguồn mua"
    PAYMENT_CAPTURE ||--o{ REFUND_TRANSACTION : "có thể hoàn"
~~~

**Chú thích quan trọng:**

- Quan hệ CUSTOMER–SALES_ORDER được vẽ 0..N theo hướng khách có thể chưa đặt đơn, nhưng **một order có bắt buộc có customer account hay không vẫn là câu hỏi mở** (guest buyer).
- PAYMENT_CAPTURE gắn trực tiếp một order chỉ đúng nếu nghiệp vụ xác nhận không có thanh toán phân bổ cho nhiều order; nếu có, cần **PaymentAllocation**.
- Một ReturnLine có thể cần liên kết ShipmentLine để chứng minh nguồn hàng đã giao, tùy policy.
- Shipment có thể chứa dòng từ nhiều order nếu nghiệp vụ cho phép; sơ đồ giả định shipment theo một order để đơn giản, cần xác minh.
- Những đường nối là **quan hệ nghiệp vụ**; trong hệ đa dịch vụ có thể không có FK vật lý.

### 29.2. Một hàng glossary tốt hơn mười tên cột

Ví dụ thuật ngữ **“Giá chốt dòng”**:

~~~text
term_id: TERM-009
definition:
  Đơn giá trên một OrderLine được ghi cố định theo mốc
  chốt giao dịch do Sales owner xác định.
grain:
  Một đơn giá trên một dòng đơn hoặc phiên bản dòng đã chốt.
scope:
  Một tenant, một currency, một kênh/nguồn.
example:
  SKU-A có captured_unit_price 120.000 tại O145.
counterexample:
  Catalog hiện hiển thị 130.000 cho SKU-A.
business_rule:
  Không viết lại giá dòng lịch sử chỉ vì catalog đổi giá.
owner:
  Sales owner; Finance consulted.
status:
  DRAFT cho đến khi owner duyệt mốc chốt chính xác.
~~~

### 29.3. Tính được bốn giá trị ở tình huống O145

- Giá hàng trước giảm: **320.000 VND**.
- Giảm giá hàng: **20.000 VND**.
- Giá hàng sau giảm, trước trả: **300.000 VND**.
- Tổng khách phải trả gồm phí giao: **330.000 VND**.
- Hai capture: **200.000 + 130.000 = 330.000 VND**.
- Một return/refund mẫu: **110.000 VND**.
- Captured trừ refunded: **220.000 VND**.

Không coi **220.000** tự động là “doanh thu thuần được ghi nhận” vì chưa xác định các quy tắc kế toán, phí và thuế. Đây là bài toán **đặt tên metric và chốt quyền phê duyệt**, không chỉ làm số học.

### 29.4. Các câu hỏi vẫn hợp lệ nếu chưa có đáp án

Một nhóm làm bài tốt có thể nêu rõ:

- “Chưa có nguồn xác nhận guest order có customer_id bắt buộc hay không.”
- “Chưa chốt payment capture có thể phân bổ cho nhiều order.”
- “Chưa chốt policy tính phí giao khi return một phần.”
- “Chưa chốt return item có thể nhận lại ở kho khác.”
- “Chưa chốt việc dùng order_placed_at hay captured_at cho KPI tài chính.”

**Ghi đúng một câu hỏi mở quan trọng tốt hơn bịa một ràng buộc sai.**

## 30. Thang đánh giá bài thực hành

Tổng điểm tham khảo **100**, nhấn mạnh tính rõ ràng và khả năng kiểm chứng thay vì số lượng hình vẽ.

| Tiêu chí | Điểm tối đa | Điều kiện đạt tốt |
|---|---:|---|
| **Phạm vi và stakeholder** | 10 | Có mục tiêu, owner, boundary và vai trò đúng |
| **As-is + ngoại lệ** | 15 | Các nhánh thanh toán, giao, hủy, trả, late data không bị bỏ sót |
| **Bảng thuật ngữ** | 25 | Định nghĩa rõ, không vòng vo, có scope/grain/alias và phản ví dụ |
| **Identity, source và thời gian** | 15 | Namespace, nguồn có thẩm quyền và các timestamp được phân biệt |
| **Business rules và test cases** | 15 | Bất biến được viết kiểm chứng được, không lẫn giả định với fact |
| **Xử lý xung đột** | 10 | Có decision log, owner và các định nghĩa metric không mâu thuẫn |
| **Tài liệu và trình bày** | 10 | Tài liệu dễ đọc, có version, evidence, privacy và handoff |
| **Tổng** | **100** | Không có sai lầm nghiêm trọng về grain hoặc số đo |

### 30.1. Các lỗi trừ điểm mạnh

- Coi Cart là Order mà không nêu mốc chuyển đổi.
- Coi một Order chỉ có một Payment/Shipment dù mẫu O145 bác bỏ.
- Dùng từ “thành công” không chỉ rõ order, payment hay delivery.
- Gộp Return và Refund thành cùng một entity không có lý do.
- Tính SUM(amount) sau JOIN nhiều quan hệ 1–N mà không bảo vệ grain.
- Lấy mã local ID làm ID toàn cục khi nhiều nguồn có thể trùng.
- Không ghi nguồn/owner cho metric doanh thu.
- Dùng captured amount làm doanh thu kế toán mà không xác định chính sách.
- Tự gọi giả thuyết là đã APPROVED.
- Sao chép thông tin khách/thanh toán thật vào tài liệu khảo sát.

### 30.2. Một rubric kiểm tra chất lượng glossary

Với từng thuật ngữ, hỏi:

1. **Unique meaning:** cùng phạm vi có đúng một định nghĩa chính?
2. **Non-circular:** không chỉ lặp lại tên thuật ngữ?
3. **Scope:** biết tenant/kênh/bounded context và thời gian áp dụng?
4. **Grain:** biết một record/giá trị đại diện cho điều gì?
5. **Counterexample:** phân biệt được với thuật ngữ gần nghĩa?
6. **Traceable:** có nguồn và owner xác minh?
7. **Testable:** có ví dụ giao dịch xác nhận hoặc bác bỏ?
8. **Governed:** có trạng thái review và version?

Nếu không đáp ứng, glossary vẫn là nháp, không nên dùng làm hợp đồng dữ liệu chốt để triển khai.

## 31. Checklist bàn giao và bước tiếp theo của mô hình hóa

Trước khi gửi kết quả khảo sát sang bước tạo mô hình logic:

- **Scope:** điểm bắt đầu/kết thúc và các hệ thống ngoài phạm vi được ghi rõ?
- **As-is:** luồng thực tế khác policy/to-be ở điểm nào?
- **Stakeholder:** ai chịu trách nhiệm mỗi nhóm thuật ngữ/rule?
- **Evidence:** có ID cho phỏng vấn, transaction mẫu và dữ liệu quan sát?
- **Glossary:** Order, Line, SKU, Capture, Shipment, Return, Refund và các metric không bị nhập nhằng?
- **Identity:** internal ID, source ID và idempotency key có namespace đúng?
- **Grain:** mỗi entity ứng viên có một câu mô tả “một hàng là một gì”?
- **Cardinality:** đã khảo sát một đơn nhiều payment/shipments và một line nhiều shipments?
- **State:** vòng đời order/payment/fulfillment/return không bị gộp tùy tiện?
- **Temporal:** order time, capture time, delivery time, event time và ingestion time riêng?
- **Metrics:** số đo có công thức, trạng thái lọc, đơn vị, timezone và owner?
- **History:** những biến đổi cần lưu lịch sử đã được nhận diện?
- **Sources:** hệ thống có thẩm quyền, downstream và cơ chế đối soát được ghi?
- **Constraints:** các rule quan trọng có test cases nhưng chưa áp schema thiếu bằng chứng?
- **Disputes:** các định nghĩa mâu thuẫn có decision log/open issue?
- **Privacy:** tài liệu không chứa PII và token/thông tin thanh toán không cần thiết?
- **Version:** biết glossary và quy trình nào đã duyệt, cái nào còn nháp?
- **Next step:** có danh sách candidate entities, relationships, grains và open questions để bắt đầu ERD logic?

### 31.1. Chuỗi công việc sau khảo sát

~~~mermaid
flowchart TD
    A["Khảo sát quy trình as-is"] --> B["Glossary + business rules"]
    B --> C["Chốt entity grain & identity"]
    C --> D["Mô hình logic: PK/FK/cardinality"]
    D --> E["Ràng buộc, chuẩn hóa, temporal history"]
    E --> F["Chọn relational/document/graph/analytical model"]
    F --> G["Lược đồ vật lý, index, partition, migration"]
    G --> H["Test dữ liệu, query và concurrency"]
    H --> I["Review mô hình & cập nhật glossary"]
~~~

**Kết luận:** một mô hình dữ liệu đáng tin phải bắt đầu từ **điều hoạt động kinh doanh thật sự làm**, không từ những tên cột sẵn có. Khảo sát quy trình làm lộ các điểm tạo dữ liệu, chuyển trạng thái, nhiều-một, nhiều-nhiều và ngoại lệ; bảng thuật ngữ làm rõ **một đối tượng hoặc số đo có nghĩa gì, ở phạm vi nào và theo nguồn nào**. Khi thuật ngữ, grain, thời gian và bất biến đã được diễn giải và xác minh bằng ví dụ, việc thiết kế ERD, chọn khóa, chuẩn hóa, tạo fact/dimension và tối ưu truy vấn mới có nền tảng chính xác, tiến hóa được và có thể kiểm chứng.
