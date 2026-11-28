# Data owner: vai trò chủ sở hữu dữ liệu trong security assurance

## 1. Vì sao dữ liệu cần người chịu trách nhiệm?

Một hệ thống có thể đã bật mã hóa, xác thực đa yếu tố, sao lưu, phân quyền và ghi log. Tuy nhiên, các biện pháp đó chưa trả lời trọn vẹn những câu hỏi cốt lõi:

- **Dữ liệu nào là quan trọng hoặc nhạy cảm?** Có phải tất cả bảng, file, bản sao và luồng xuất dữ liệu đều được xác định?
- **Ai được phép sử dụng dữ liệu, nhằm mục đích gì?** Quyền truy cập nào là cần thiết cho công việc và quyền nào đã không còn phù hợp?
- **Dữ liệu được chia sẻ, lưu giữ và xóa theo nguyên tắc nào?** Ai phê duyệt trường hợp ngoại lệ?
- **Khi một kiểm soát bảo vệ dữ liệu không đạt**, ai có trách nhiệm đánh giá tác động, phối hợp xử lý và cung cấp bằng chứng?
- **Ai đủ thẩm quyền xác nhận** dữ liệu và cách sử dụng đáp ứng yêu cầu nghiệp vụ, đồng thời chuyển các vấn đề vượt thẩm quyền cho bộ phận có trách nhiệm?

**Data owner (chủ sở hữu dữ liệu)** là vai trò nghiệp vụ được giao **trách nhiệm giải trình về cách một tập dữ liệu hoặc một miền dữ liệu được phân loại, sử dụng, bảo vệ và quản lý trong phạm vi tổ chức**. Data owner xác định nhu cầu bảo vệ và quy tắc sử dụng theo thẩm quyền, điều phối những người thực hiện, theo dõi sự tuân thủ và bảo đảm các quyết định quan trọng có cơ sở rõ ràng.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là đánh giá **có bằng chứng** rằng hệ thống đáp ứng các mục tiêu bảo mật, từ rủi ro và yêu cầu tới security controls, kiểm thử, audit và khắc phục phát hiện. Vai trò Data owner đặc biệt quan trọng vì các kiểm soát kỹ thuật chỉ có thể được đánh giá đầy đủ khi biết **dữ liệu nào cần bảo vệ, cần bảo vệ đến mức nào và ai chịu trách nhiệm với yêu cầu đó**.

> “Owner” ở đây là **vai trò quản trị được tổ chức giao trách nhiệm**, không mặc nhiên là người sở hữu hợp pháp mọi quyền đối với dữ liệu, người trực tiếp quản trị cơ sở dữ liệu hay người có quyền tự ý bỏ qua các nghĩa vụ pháp lý và chính sách.

### Ví dụ mở đầu

Một sàn thương mại lưu hồ sơ khách hàng, lịch sử mua hàng và các báo cáo thống kê. Nhóm hạ tầng triển khai mã hóa cơ sở dữ liệu; nhóm phát triển tạo API xuất báo cáo; nhóm phân tích muốn tải danh sách khách hàng về máy cá nhân. Nếu thiếu Data owner, mỗi nhóm có thể đưa ra quyết định riêng dựa trên quyền truy cập kỹ thuật. Khi có Data owner của miền dữ liệu khách hàng, tổ chức có đầu mối chịu trách nhiệm xác định **mục đích sử dụng được phép**, **mức nhạy cảm**, **điều kiện truy cập/xuất dữ liệu** và **bằng chứng kiểm chứng** các quy tắc đó.

## 2. Phạm vi và ranh giới trách nhiệm của Data owner

### 2.1. Data owner sở hữu trách nhiệm đối với *tập dữ liệu*, không nhất thiết sở hữu hệ thống

Một hệ thống có thể chứa dữ liệu của nhiều miền nghiệp vụ. Ví dụ cơ sở dữ liệu của nền tảng bán hàng bao gồm khách hàng, đơn hàng, thanh toán và tồn kho. Những miền này có yêu cầu sử dụng, hậu quả rủi ro và người quyết định nghiệp vụ khác nhau. Ngược lại, dữ liệu khách hàng có thể tồn tại ở CRM, kho dữ liệu phân tích, bản sao lưu và file chia sẻ. Trách nhiệm Data owner phải theo **dữ liệu trong phạm vi**, kể cả khi dữ liệu được sao chép sang hệ thống khác theo quy trình được phép.

Phạm vi ownership có thể được xác định theo:

- **Data domain:** khách hàng, nhân sự, đơn hàng, tài chính, nhà cung cấp.
- **Data product/dataset:** kho dữ liệu khách hàng đã chuẩn hóa, bộ dữ liệu phân tích hoặc nguồn dữ liệu báo cáo.
- **Độ nhạy và mục đích:** dữ liệu định danh, bí mật kinh doanh, thông tin giao dịch hoặc hồ sơ cần lưu giữ đặc biệt.
- **Phạm vi tổ chức:** một đơn vị, sản phẩm hoặc miền dùng chung trên toàn doanh nghiệp.

Tổ chức phải quyết định đơn vị quản trị phù hợp, ghi rõ **ranh giới** và xử lý trường hợp nhiều miền dữ liệu cùng xuất hiện trong một sản phẩm. Nếu dữ liệu được kết hợp có thể làm tăng độ nhạy hoặc tạo mục đích sử dụng mới, cần xác định các owner có liên quan và một đầu mối quyết định theo chính sách.

### 2.2. Các loại trách nhiệm cần phân biệt

| Vai trò | Trọng tâm trách nhiệm | Ví dụ với dữ liệu khách hàng |
| --- | --- | --- |
| **Data owner** | Quyết định trong thẩm quyền về phân loại, quy tắc sử dụng, quyền truy cập theo nghiệp vụ, yêu cầu bảo vệ và giám sát dữ liệu. | Trưởng bộ phận phụ trách miền dữ liệu khách hàng. |
| **Data steward** | Thực hiện quản trị dữ liệu hằng ngày: metadata, chuẩn dữ liệu, kiểm tra chất lượng, quy trình xử lý vấn đề. | Chuyên viên duy trì danh mục trường dữ liệu, chất lượng và mô tả nguồn. |
| **Data custodian / platform operator** | Lưu trữ, xử lý và bảo vệ dữ liệu bằng các biện pháp kỹ thuật theo yêu cầu đã phê duyệt. | DBA, nhóm cloud/platform thực thi backup, encryption, retention job. |
| **System/service owner** | Chịu trách nhiệm ứng dụng và vận hành dịch vụ xử lý dữ liệu. | Người phụ trách CRM hoặc Order Service. |
| **Control owner** | Chịu trách nhiệm giải trình về hiệu quả một security control đã xác định. | Chủ sở hữu kiểm soát mã hóa lưu trữ hoặc kiểm soát cấp quyền truy cập. |
| **Risk owner** | Quản lý và quyết định xử lý/chấp nhận rủi ro trong thẩm quyền được giao. | Lãnh đạo được ủy quyền xử lý rủi ro lộ dữ liệu. |
| **Security assurance / assessor** | Kiểm tra lập luận và bằng chứng rằng các yêu cầu/controls đang được đáp ứng. | Nhóm kiểm thử quyền truy cập, đánh giá logs và hồ sơ ngoại lệ. |
| **Privacy/legal/compliance** | Xác định, tư vấn hoặc giám sát nghĩa vụ pháp lý, hợp đồng và chính sách có liên quan. | Tư vấn giới hạn mục đích, thời hạn lưu giữ, chuyển dữ liệu và quyền của chủ thể dữ liệu khi áp dụng. |

Tùy quy mô tổ chức, một người có thể đảm nhận nhiều vai trò. Tuy nhiên, **chức năng phê duyệt, thực hiện và kiểm chứng** vẫn phải được làm rõ để hạn chế xung đột lợi ích. Data owner không tự động có quyền quản trị production hoặc quyền phê duyệt ngoại lệ pháp lý.

### 2.3. Phân biệt với “data controller” và “data processor”

Trong một số quy định về bảo vệ dữ liệu cá nhân, các khái niệm như **bên kiểm soát dữ liệu**, **bên xử lý dữ liệu** hoặc chức danh chuyên trách bảo vệ dữ liệu có định nghĩa và nghĩa vụ pháp lý riêng. **Data owner là vai trò quản trị nội bộ**, không đương nhiên tương đương với các tư cách pháp lý đó. Khi quản lý dữ liệu cá nhân, tổ chức phải phối hợp với pháp chế/privacy để xác định nghĩa vụ áp dụng; việc gán tên Data owner không thay thế trách nhiệm của pháp nhân hay các vai trò pháp lý được quy định.

## 3. Những quyết định Data owner cần chịu trách nhiệm giải trình

Data owner thường là người ra quyết định nghiệp vụ hoặc bảo đảm quyết định đúng thẩm quyền được thực hiện. Các nhóm công việc trọng yếu gồm:

### 3.1. Xác định dữ liệu và mục đích sử dụng

Trước khi bảo vệ dữ liệu, phải biết **dữ liệu nào tồn tại, được tạo ở đâu, di chuyển như thế nào, ai sử dụng và để làm gì**. Owner phối hợp với data steward, kiến trúc sư và system owner để duy trì data inventory, catalog và data lineage (đường đi/phụ thuộc của dữ liệu).

Một cột email có thể xuất hiện trong bảng khách hàng, cache, công cụ phân tích, file CSV và backup. Nếu chỉ nhìn database gốc, phạm vi kiểm soát bảo mật có thể bỏ sót các bản sao.

### 3.2. Phân loại và đặt yêu cầu bảo vệ

Owner xác định mức nhạy cảm theo chính sách được phê duyệt: ví dụ **công khai**, **nội bộ**, **mật** hoặc **hạn chế cao**. Tiêu chí phân loại cần xem xét hậu quả nếu dữ liệu bị **tiết lộ, sửa sai, mất hoặc không truy cập được**.

Việc gán nhãn chỉ có giá trị khi kéo theo yêu cầu cụ thể: người được phép đọc, hình thức chia sẻ, mã hóa, ghi log, kiểm tra truy cập, lưu giữ hoặc cách xử lý môi trường test. Owner tham gia xác định tiêu chí; đội kỹ thuật chịu trách nhiệm triển khai biện pháp tương ứng.

### 3.3. Quy định mục đích sử dụng và quyền truy cập

Data owner xác định **ai cần loại truy cập nào vì công việc gì**. Thẩm quyền phê duyệt phải tuân thủ chính sách, nguyên tắc quyền tối thiểu và phân tách nhiệm vụ (*segregation of duties*).

Ví dụ đội chăm sóc khách hàng chỉ cần tra cứu một số trường thông tin để hỗ trợ yêu cầu; đội marketing chỉ cần dữ liệu phù hợp với mục đích được phép; đội phát triển không nên được cấp truy cập rộng tới production chỉ vì có quyền deploy. Owner phê duyệt nhu cầu nghiệp vụ; hệ thống IAM và người vận hành thực thi kiểm soát kỹ thuật.

### 3.4. Quy định vòng đời, lưu giữ và loại bỏ dữ liệu

Data owner phối hợp với pháp chế, privacy, records management và vận hành để xác định thời hạn lưu giữ, điều kiện xóa/ẩn danh/lưu trữ lâu dài theo nghĩa vụ và nhu cầu đã phê duyệt. Khi cần xóa, phải biết dữ liệu còn ở **bản sao, backup, hàng đợi, cache, log, hệ thống phân tích hoặc nhà cung cấp** hay không.

Data owner không tự ý rút ngắn thời hạn lưu giữ bắt buộc hay cam kết xóa mọi bản sao ngay lập tức khi kiến trúc backup không hỗ trợ. Cần mô tả rõ quy tắc xóa, ngoại lệ và cách kiểm chứng; một số dữ liệu trong backup có thể được xóa theo vòng đời backup và được ngăn phục hồi ngoài mục đích cho phép theo cơ chế áp dụng.

### 3.5. Xác định yêu cầu về toàn vẹn và sẵn sàng

Data owner không chỉ quan tâm tính bí mật. Dữ liệu tồn kho sai có thể tạo đơn vượt số hàng thực; đơn hàng bị sửa nhầm có thể ảnh hưởng giao dịch; hồ sơ quan trọng không thể phục hồi có thể làm ngừng vận hành.

Owner phải nêu rõ **quy tắc chất lượng/toàn vẹn có ý nghĩa bảo mật** và nhu cầu nghiệp vụ về khả năng truy cập hoặc phục hồi. Đội vận hành chuyển chúng thành kiểm soát như validation, audit trail, backup, replication và mục tiêu RTO/RPO theo quy trình quản trị rủi ro.

### 3.6. Tham gia ứng phó sự cố và xử lý phát hiện

Khi nghi ngờ lộ, thay đổi trái phép hoặc mất dữ liệu, Data owner cung cấp bối cảnh về loại dữ liệu, quy mô, người bị ảnh hưởng, hậu quả nghiệp vụ và các nhóm cần phối hợp. Nhóm ứng cứu chủ trì hoạt động kỹ thuật theo quy trình sự cố; pháp chế/privacy chịu trách nhiệm hoặc tư vấn nghĩa vụ thông báo khi áp dụng. Owner theo dõi hành động khắc phục liên quan tới dữ liệu của mình và kiểm tra lại phạm vi bảo vệ.

## 4. Dữ liệu, rủi ro và security requirements: liên kết từ đầu

Quản trị tốt cần nối rõ **tài sản dữ liệu → kịch bản rủi ro → yêu cầu bảo mật → kiểm soát → bằng chứng**. Một control có thể được triển khai đúng kỹ thuật nhưng vẫn không giải quyết nhu cầu của dữ liệu được quản lý.

| Dữ liệu / tình huống | Rủi ro | Yêu cầu có thể kiểm chứng | Control và bằng chứng điển hình |
| --- | --- | --- | --- |
| Hồ sơ khách hàng chứa số điện thoại, email. | Người không có quyền tải bản đầy đủ. | Chỉ vai trò nghiệp vụ có thẩm quyền được truy cập trường nhạy cảm; truy xuất hàng loạt có kiểm soát. | Authorization, kiểm tra role/tenant, đánh giá log xuất dữ liệu, access review. |
| Dữ liệu bán hàng dùng tính doanh thu. | Kết quả bị sửa trái phép hoặc sai lệch. | Mọi sửa đổi quan trọng có người thực hiện, lý do và lịch sử truy xuất; dữ liệu đầu vào được kiểm tra. | Validation, audit trail, quy tắc đối soát, kiểm thử tính toàn vẹn. |
| Dữ liệu đơn hàng cần phục hồi sau sự cố. | Mất trạng thái đơn hoặc gián đoạn xử lý. | Khôi phục dữ liệu ở mức mất dữ liệu và thời gian đã phê duyệt cho kịch bản cụ thể. | Backup/restore drill, kết quả đo RPO/RTO, kiểm tra nhất quán sau restore. |
| Bản sao dữ liệu cho phân tích. | Dữ liệu nhạy cảm bị sao chép sang môi trường yếu hơn. | Dữ liệu test/analytics chỉ chứa trường được phép; dữ liệu nhạy cảm được loại bỏ, che hoặc xử lý phù hợp trước khi chuyển. | Data minimization, masking test, đối chiếu dataset, kiểm tra quyền và đường truyền. |
| File xuất cho đối tác. | Sử dụng sai mục đích hoặc chia sẻ tiếp. | Chỉ xuất trường, đối tượng nhận và thời gian sử dụng được phê duyệt; có hồ sơ chuyển giao. | Phê duyệt nghiệp vụ, hợp đồng/quy định áp dụng, log xuất file, cơ chế hạn chế truy cập. |

Ví dụ yêu cầu mơ hồ: **“Dữ liệu khách hàng phải được bảo mật.”**

Yêu cầu rõ hơn: **“Trong môi trường production của ứng dụng CRM, các endpoint xuất danh sách liên hệ chỉ được dùng bởi vai trò được Data owner phê duyệt theo mục đích nghiệp vụ; các trường nhạy cảm bị hạn chế theo chính sách, mọi lần xuất đều có bản ghi audit với người thực hiện, phạm vi và thời điểm.”**

Để kiểm chứng tuyên bố, cần có **danh sách endpoint đầy đủ**, **ma trận quyền được phê duyệt**, **bài test trường hợp được/không được phép**, **bằng chứng cấu hình production** và **mẫu log thực tế**. Một tài liệu phê duyệt mà không có bằng chứng thực thi chưa đủ cho kết luận assurance.

## 5. Quy trình phân loại dữ liệu và quyết định mức bảo vệ

Một quy trình phân loại có thể đi từ câu hỏi thực tế, thay vì chỉ gắn nhãn tùy ý:

1. **Nhận diện tập dữ liệu và bản sao.** Ghi nguồn, nơi lưu, đường truyền, bên nhận và mục đích.
2. **Xác định hậu quả CIA.** Điều gì xảy ra nếu dữ liệu bị lộ, thay đổi hoặc không sẵn sàng?
3. **Đối chiếu chính sách và nghĩa vụ.** Kiểm tra quy định nội bộ, hợp đồng và yêu cầu pháp lý có liên quan với các bộ phận chuyên trách.
4. **Gán nhãn và tiêu chí xử lý.** Xác định mức phân loại, trường/đối tượng cần giới hạn và yêu cầu về lưu trữ, truyền, chia sẻ, log, backup, hủy bỏ.
5. **Phê duyệt và truyền đạt yêu cầu.** Data owner quyết định trong phạm vi được ủy quyền; hệ thống lưu nhãn và metadata để các đội triển khai đúng.
6. **Kiểm tra hiệu lực và đánh giá lại.** Xem xét khi dữ liệu kết hợp với tập khác, thêm mục đích sử dụng, mở hệ thống mới hoặc phát hiện thiếu sót.

| Tình huống | Phân tích của owner | Hành động tiếp theo |
| --- | --- | --- |
| Tập dữ liệu chỉ gồm giá sản phẩm công khai. | Rủi ro lộ thấp, nhưng sửa trái phép có thể gây hậu quả lớn. | Ưu tiên kiểm soát tính toàn vẹn, nguồn thay đổi, phê duyệt công bố. |
| Hồ sơ lương nhân sự. | Tiết lộ có thể gây hậu quả nghiêm trọng; lưu giữ theo nghĩa vụ. | Phân loại hạn chế, quyền theo nhu cầu công việc, log truy cập, chính sách lưu giữ. |
| Báo cáo doanh thu tổng hợp. | Có thể suy ra thông tin nhạy cảm nếu nhóm quá nhỏ hoặc kết hợp dữ liệu khác. | Đánh giá rủi ro tái nhận diện/suy diễn trước khi chia sẻ rộng. |
| Bản sao production sang staging. | Cùng dữ liệu nhưng môi trường và quyền khác nhau. | Đánh giá nhu cầu, thực hiện minimization/masking phù hợp, kiểm chứng trước khi cấp sử dụng. |

Không có một nhãn cố định phù hợp mọi tổ chức. Quan trọng là **định nghĩa nhất quán, quyết định có căn cứ và kiểm soát áp dụng thực tế**.

## 6. Phân quyền dữ liệu: từ yêu cầu nghiệp vụ đến quyết định kỹ thuật

Data owner thường tham gia phê duyệt quyền truy cập dựa trên **nhu cầu nghiệp vụ**. Tuy nhiên, một yêu cầu được owner đồng ý vẫn phải qua các chốt về chính sách, tính hợp lệ của chủ thể, phạm vi dữ liệu, quyền hạn và nghĩa vụ khác.

~~~mermaid
flowchart TD
    A["Yêu cầu truy cập dữ liệu"] --> B["Xác thực chủ thể, mô tả mục đích, phạm vi và thời hạn"]
    B --> C{"Có đúng chính sách và nhu cầu nghiệp vụ?"}
    C -- "Không" --> D["Từ chối hoặc yêu cầu bổ sung"]
    C -- "Có" --> E["Data owner phê duyệt theo thẩm quyền"]
    E --> F["IAM / hệ thống thực thi quyền tối thiểu"]
    F --> G["Ghi log, giám sát và lưu bằng chứng cấp quyền"]
    G --> H["Rà soát định kỳ hoặc theo sự kiện"]
    H --> I{"Quyền còn cần thiết?"}
    I -- "Không" --> J["Thu hồi quyền, xác nhận kết quả"]
    I -- "Có" --> G
~~~

### Một hồ sơ yêu cầu quyền nên có gì?

- Người hoặc dịch vụ được yêu cầu cấp quyền, danh tính được quản lý và đơn vị liên quan.
- **Tập dữ liệu**, trường, thao tác (đọc/sửa/xuất/xóa), môi trường và đối tượng khách hàng/tenant nếu có.
- Mục đích sử dụng, lý do nghiệp vụ, thời hạn và hình thức truy cập.
- Xác nhận chính sách, kiểm soát liên quan và các phê duyệt theo thẩm quyền.
- Người thực thi, thời điểm cấp quyền, kết quả kiểm tra và lịch hết hạn/rà soát.

Ví dụ, cấp quyền **đọc bảng khách hàng** có thể rộng hơn nhu cầu thực tế là “xem địa chỉ giao hàng của khách trong một đơn cụ thể”. Data owner phải giúp giảm quyền xuống **mức dữ liệu và thao tác cần thiết**, sau đó nhóm kỹ thuật triển khai bằng RBAC/ABAC, object-level authorization, view, API hoặc cơ chế tương đương.

### Thu hồi quyền và rà soát định kỳ

Một hệ thống có thể cấp đúng quyền tại thời điểm ban đầu nhưng thiếu thu hồi khi nhân viên đổi vị trí, dự án kết thúc hoặc đối tác ngừng hợp đồng. Data owner phối hợp system owner/IAM xác định danh sách truy cập cần đánh giá lại. **Bằng chứng review** cần có tập người dùng/nhóm quyền được xét, quyết định giữ/thu hồi, thời điểm, người phê duyệt và kết quả thu hồi. Chỉ gửi email “đề nghị kiểm tra quyền” không chứng minh việc rà soát đã hoàn tất.

Với truy cập khẩn cấp (*break-glass*), quyền và quy trình cần quy định rõ điều kiện kích hoạt, thời hạn, lưu log, hậu kiểm và phê duyệt theo chính sách. Không biến quyền khẩn cấp thành đường truy cập thường xuyên.

## 7. Ma trận RACI cho Data owner

RACI giúp tránh việc Data owner bị gán mọi thao tác kỹ thuật hoặc có thể ra quyết định ngoài thẩm quyền:

- **R (Responsible):** trực tiếp thực hiện công việc.
- **A (Accountable):** chịu trách nhiệm cuối cùng cho kết quả hoặc quyết định của hoạt động.
- **C (Consulted):** được tham vấn.
- **I (Informed):** nhận thông tin.

Ví dụ phân công cho một miền dữ liệu khách hàng (cần điều chỉnh theo cấu trúc và chính sách của từng tổ chức):

| Hoạt động | Data owner | Data steward | Platform/IAM | Security assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Chốt phân loại và yêu cầu bảo vệ dữ liệu theo chính sách | **A** | **R** | C | C | I |
| Duy trì catalog, metadata và data lineage | **A** | **R** | C | C | I |
| Phê duyệt nhu cầu truy cập nghiệp vụ trong thẩm quyền | **A/R** | C | C | I | I |
| Thi hành và thu hồi quyền kỹ thuật | C | I | **A/R** | I | I |
| Thực hiện kiểm thử độc lập yêu cầu bảo mật dữ liệu | C | C | C | **A/R** | I |
| Phối hợp điều tra và khắc phục vi phạm quy tắc dữ liệu | **A** | **R** | **R** | C | I |
| Chấp nhận rủi ro còn lại theo thẩm quyền | C | I | C | C | **A/R** |

Mỗi dòng nên có **một đầu mối A** cho đúng hoạt động. Nếu hoạt động có phạm vi không rõ, hãy chia thành các quyết định/đầu việc cụ thể thay vì gán nhiều A mà không xác định bên cuối cùng chịu trách nhiệm. Với dữ liệu cá nhân, pháp chế/privacy hoặc chức danh pháp lý phù hợp cần tham gia theo quy trình của tổ chức, dù bảng ví dụ chưa thể hiện hết.

### Giao trách nhiệm phải đi cùng thẩm quyền và nguồn lực

Một Data owner khó thực hiện đúng nhiệm vụ nếu không xem được catalog, không có báo cáo quyền, không có operator hợp tác hoặc không có cách leo thang phát hiện. Vì vậy, ngoài tên người, hồ sơ còn cần đơn vị, vai trò thay thế, hệ thống/phạm vi được phụ trách, quyền yêu cầu bằng chứng, cơ chế phê duyệt và đầu mối escalations.

## 8. Data owner cần tạo và duy trì bằng chứng nào cho assurance?

Điểm đặc trưng của **security assurance** là **khẳng định phải có lập luận và bằng chứng**. Đối với trách nhiệm dữ liệu, áp dụng mô hình **Claim – Argument – Evidence (CAE)**:

- **Claim:** Tuyên bố cụ thể về yêu cầu bảo vệ, phạm vi dữ liệu, môi trường và thời gian.
- **Argument:** Giải thích tại sao chính sách, các security controls và quy trình được thiết kế đủ để hỗ trợ claim; nêu giả định.
- **Evidence:** Hồ sơ, kết quả kiểm thử, cấu hình và số liệu vận hành có thể xác minh, bao gồm cả phát hiện chưa xử lý.

### Ví dụ liên kết mục tiêu, trách nhiệm và bằng chứng

| Claim | Trách nhiệm của Data owner | Bằng chứng cần kiểm tra | Giới hạn có thể còn |
| --- | --- | --- | --- |
| Dữ liệu khách hàng được phân loại đúng. | Định nghĩa tiêu chí, phê duyệt nhãn và phạm vi. | Data catalog, quyết định phân loại, đối chiếu trường dữ liệu với nguồn. | Bản sao và dữ liệu phi cấu trúc chưa được rà soát. |
| Chỉ người có nhu cầu hợp lệ được đọc trường nhạy cảm. | Xác định quyền cần thiết, phê duyệt theo chính sách, tham gia review. | Access matrix, logs cấp/thu hồi, kiểm tra phân quyền, access recertification. | Endpoint xuất dữ liệu hoặc tài khoản dịch vụ chưa kiểm tra. |
| Bản sao phục vụ thử nghiệm không lộ dữ liệu ngoài phạm vi. | Quy định dữ liệu được phép chuyển và tiêu chí xử lý. | Quy trình masking, kết quả test, kiểm tra dataset thực tế, danh sách bên nhận. | Dữ liệu có khả năng tái nhận diện sau kết hợp. |
| Dữ liệu được lưu giữ và xóa theo quy tắc. | Xác định nhu cầu nghiệp vụ, phối hợp chính sách/ nghĩa vụ và kiểm tra ngoại lệ. | Chính sách retention, lịch job, kết quả xóa, xử lý backup, hồ sơ ngoại lệ. | Nhà cung cấp hoặc bản sao ngoài inventory chưa được kiểm chứng. |
| Dữ liệu quan trọng có thể phục hồi. | Xác định ảnh hưởng nghiệp vụ và yêu cầu phục hồi. | Backup/restore drill, đối soát tính nhất quán, báo cáo đo RTO/RPO trong kịch bản. | Chỉ kiểm thử một vùng hoặc chưa bao phủ phụ thuộc. |

Một bằng chứng có chất lượng phải chỉ ra **nguồn, phiên bản/cấu hình, môi trường, phạm vi, thời điểm, phương pháp kiểm tra, người thực hiện, kết quả và giới hạn**. Ví dụ ảnh chụp “encryption enabled” chỉ hỗ trợ một phần claim về mã hóa, chưa chứng minh mọi bản sao thuộc phạm vi đã được bảo vệ hoặc rằng quyền giải mã được kiểm soát.

### Hồ sơ Data owner nên có các trường gì?

Có thể lưu trong data catalog hoặc governance register. Ví dụ YAML dưới đây chỉ mô phỏng cấu trúc hồ sơ nghiệp vụ, **không phải yêu cầu thay đổi metadata của module**:

~~~yaml
data_asset_id: CUSTOMER-CORE-001
name: "Customer contact records"
domain: "Customer"
business_owner_role: "Head of Customer Operations"
data_steward_role: "Customer Data Steward"
technical_custodian_role: "Customer Platform Team"
risk_owner_role: "Customer Data Risk Owner"
classification: "Confidential"
purpose:
  - "Customer support for active orders"
  - "Permitted operational reporting"
locations:
  - "crm-production"
  - "analytics-curated"
  - "managed-backup"
allowed_access:
  - "Support role: scoped read via CRM"
  - "Reporting role: approved aggregate views"
controls:
  - "AUTHZ-CUST-01"
  - "LOG-CUST-02"
  - "RETENTION-CUST-03"
evidence:
  - "access-review/2026-Q4"
  - "authz-test/customer-api-release-2.8"
open_findings:
  - "FIND-CUST-014"
review_trigger:
  - "New export endpoint"
  - "New receiving third party"
  - "Change to data classification"
~~~

Các giá trị, đường dẫn và ID trong ví dụ là **minh họa**, không phản ánh hiện vật đã được thu thập. Khi áp dụng thực tế, owner cần liên kết chính xác tới artifacts, version và kết quả kiểm chứng.

## 9. Vòng đời dữ liệu và điểm kiểm soát theo từng giai đoạn

Ownership không dừng lại ở việc cấp quyền đọc. Data owner cần đảm bảo các yêu cầu vẫn được duy trì **trong toàn bộ vòng đời**:

~~~mermaid
flowchart LR
    A["Thu thập / tạo"] --> B["Phân loại / ghi catalog"]
    B --> C["Lưu trữ / sử dụng"]
    C --> D["Chia sẻ / xử lý / sao chép"]
    D --> E["Lưu giữ / lưu trữ dài hạn"]
    E --> F["Xóa / ẩn danh / hủy"]
    C --> G["Kiểm tra và đánh giá lại"]
    D --> G
    E --> G
    G --> B
~~~

| Giai đoạn | Câu hỏi Data owner cần làm rõ | Bằng chứng assurance |
| --- | --- | --- |
| **Thu thập/tạo** | Có cần các trường này không? Mục đích và nguồn có hợp lệ, được mô tả? | Data inventory, schema review, xác nhận mục đích và chính sách thu thập. |
| **Phân loại** | Dữ liệu có nhạy cảm không? Tập nào và bản sao nào phải được gắn nhãn? | Nhãn/catalog, biên bản review, kiểm tra phân loại theo mẫu hoặc tự động. |
| **Lưu trữ và sử dụng** | Ai cần quyền nào? Có mã hóa, kiểm tra toàn vẹn, backup và audit trail? | Access matrix, test phân quyền, cấu hình, log, restore report. |
| **Chia sẻ và sao chép** | Bên nhận, mục đích, trường dữ liệu, hợp đồng và yêu cầu bảo vệ đã được phê duyệt? | Hồ sơ duyệt, data transfer record, masking test, kết quả kiểm tra bên nhận. |
| **Lưu giữ/archival** | Thời hạn lưu giữ nào áp dụng? Có ngoại lệ hoặc lệnh giữ dữ liệu bắt buộc? | Retention schedule, job report, exception record, kiểm tra bản sao. |
| **Xóa/ẩn danh/hủy** | Dữ liệu đã được loại bỏ hoặc vô hiệu hóa đúng phạm vi và phương pháp? | Log/job result, xác nhận kiểm tra, chứng cứ từ nhà cung cấp khi phù hợp. |
| **Thay đổi/sự cố** | Phân loại, phạm vi và controls còn đúng? Ai kiểm chứng lại? | Change assessment, incident report, retest, quyết định rủi ro. |

### Đối với data lineage

Data owner cần biết **nguồn → các bước biến đổi → nơi tiêu thụ** ở mức đủ để đưa ra quyết định. Một dữ liệu gốc được xóa nhưng vẫn còn trong data lake, bảng tổng hợp hoặc tệp do hệ thống bên ngoài nhận có thể tiếp tục mang rủi ro. Data lineage không nhất thiết phải theo đến từng dòng mã, nhưng phải giúp tìm **các điểm dữ liệu đi ra khỏi biên kiểm soát ban đầu**.

## 10. Tình huống xuyên suốt: xuất dữ liệu khách hàng sang môi trường phân tích

Giả sử ứng dụng SaaS cho phép đội chăm sóc khách hàng xử lý đơn hàng. Product team đề xuất bổ sung tính năng export để nhóm phân tích theo dõi tỷ lệ khách quay lại.

Dữ liệu gốc gồm mã khách hàng, tên, email, địa chỉ giao hàng, lịch sử mua hàng và thông tin liên hệ. Kho phân tích dự kiến có nhiều nhà phân tích cùng truy cập. Nếu không có Data owner, lập luận “phân tích cần dữ liệu khách hàng” có thể dẫn tới việc chuyển **mọi trường và mọi bản ghi** từ production vào kho phân tích.

### Bước 1 — Xác định mục tiêu nghiệp vụ và dữ liệu tối thiểu

Data owner của miền khách hàng làm rõ mục đích là **phân tích tỷ lệ quay lại theo nhóm**, thay vì liên hệ trực tiếp từng cá nhân. Cùng data steward, nhóm này đề xuất chỉ dùng mã giả định danh, thời điểm mua, phân nhóm và các trường thực sự cần thiết; rà soát nguy cơ suy diễn/re-identification khi kết hợp các tập dữ liệu.

Quy tắc áp dụng: dữ liệu chỉ được đưa sang môi trường phân tích khi **mục đích, trường dữ liệu, nhóm nhận và thời hạn** đã được phê duyệt theo chính sách và nghĩa vụ liên quan.

### Bước 2 — Xác định security requirements

Ví dụ các yêu cầu có thể kiểm chứng:

1. Export chỉ được kích hoạt bởi dịch vụ hoặc vai trò được phép; token người dùng thông thường không tự động có quyền xuất toàn bộ dữ liệu.
2. Luồng phân tích nhận đúng các cột và bản ghi cần thiết; trường nhạy cảm ngoài phạm vi không xuất hiện trong đầu ra.
3. Dữ liệu được truyền và lưu trữ theo tiêu chuẩn bảo vệ đã duyệt, được quản lý quyền tại đích.
4. Các lần export có mã job, người/yêu cầu kích hoạt, dataset, thời điểm và trạng thái để điều tra khi cần.
5. Có lịch lưu giữ và phương pháp xóa phù hợp cho dữ liệu ở đích; thay đổi schema hoặc bên nhận phải kích hoạt review.

### Bước 3 — Giao trách nhiệm

| Hoạt động | Người/bên chủ trì |
| --- | --- |
| Xác định mục đích, tập trường và quy tắc sử dụng dữ liệu | **Data owner** phối hợp data steward, privacy và đơn vị sử dụng dữ liệu. |
| Thiết kế API/export job và kiểm soát kỹ thuật | **Service owner / engineering** và **platform team**. |
| Cấu hình quyền ở kho phân tích, giám sát vận hành | **Data platform/IAM operator**. |
| Đánh giá độc lập bằng chứng kiểm soát | **Security assurance**, tùy mức rủi ro và chính sách. |
| Xem xét chấp nhận rủi ro ngoài tiêu chí | **Risk owner hoặc cấp có thẩm quyền**; Data owner cung cấp tác động nghiệp vụ. |

### Bước 4 — Thu bằng chứng và thử nghiệm

Nhóm kiểm chứng không thể chỉ dựa vào lời xác nhận “dữ liệu đã được ẩn danh”. Cần có:

- **Đối chiếu schema** giữa dữ liệu gốc và dữ liệu xuất; kiểm tra không chứa các trường bị cấm trong tập test đại diện.
- **Kiểm tra quyền**: tài khoản không được phép không gọi được export hoặc đọc dataset đích; vai trò có quyền chỉ truy cập đúng phạm vi.
- **Kiểm tra dữ liệu mẫu và quy tắc biến đổi**: phát hiện trường nhạy cảm bị lẫn, dữ liệu có thể suy ra danh tính ngoài dự kiến.
- **Kiểm tra logging và retention**: bản ghi xuất, quyền, thời hạn và hành vi xóa có kết quả theo phạm vi.
- **Đối chiếu phiên bản triển khai**: bài test và cấu hình thực sự tương ứng với release, schema và môi trường đang được đánh giá.

Trong ngữ cảnh này, **data masking/pseudonymization** có thể giảm rủi ro nhưng không tự động biến dữ liệu thành **ẩn danh không thể nhận diện lại**. Nhận định như vậy cần đánh giá dựa trên bối cảnh, khả năng liên kết và phương pháp xử lý thực tế.

### Bước 5 — Xử lý phát hiện

Giả sử kiểm tra thấy file xuất vẫn chứa **email** do một mapping cũ chưa cập nhật, dù yêu cầu chỉ cho phép dữ liệu tổng hợp. Kết luận assurance phải ghi rõ **claim về minimization/chia sẻ chưa đạt**.

Data owner tham gia xác định mức nhạy cảm, dữ liệu bị ảnh hưởng, bên nhận và tác động. Nhóm ứng cứu/bảo mật quyết định các bước xử lý theo quy trình như dừng export hoặc hạn chế truy cập, kiểm tra dữ liệu đã sao chép, khắc phục mapping, đánh giá có cần kích hoạt quy trình sự cố/thông báo theo nghĩa vụ hay không. Engineering bổ sung test để ngăn trường email trở lại. Người kiểm chứng chạy lại test trên release sửa và lưu bằng chứng.

Không được đánh dấu “đã xử lý” chỉ vì sửa mã nguồn; phải kiểm tra cả **dữ liệu đã xuất, phạm vi truy cập, bản sao tại đích và kết quả thực tế sau sửa**. Nếu tồn tại phần rủi ro chưa thể loại bỏ, chuyển tới người có thẩm quyền quyết định theo quy trình.

### Bước 6 — Đánh giá lại theo thay đổi

Khi thêm cột dữ liệu mới, tích hợp đối tác phân tích, đổi vùng lưu trữ hoặc cho nhóm mới quyền truy cập, Data owner cùng các nhóm liên quan phải xem lại **mục đích, phân loại, các quyền và bằng chứng cũ còn phù hợp không**. Đó chính là assurance liên tục.

## 11. Data owner và xử lý ngoại lệ, phát hiện, sự cố

Một quyết định Data owner phải nằm trong **cơ chế quản trị rủi ro chung**, không nên trở thành phê duyệt tùy tiện.

~~~mermaid
flowchart TD
    A["Phát hiện: kiểm soát dữ liệu không đạt"] --> B["Xác định dữ liệu, phạm vi, tác động và ưu tiên"]
    B --> C["Giao owner xử lý, hạn và biện pháp tạm thời"]
    C --> D{"Có thể khắc phục theo yêu cầu?"}
    D -- "Có" --> E["Sửa lỗi, giới hạn ảnh hưởng, kiểm thử lại"]
    D -- "Chưa" --> F["Lập hồ sơ rủi ro / ngoại lệ có thời hạn"]
    F --> G["Risk owner / cấp có thẩm quyền quyết định"]
    G --> H["Theo dõi điều kiện và ngày hết hiệu lực"]
    H --> E
    E --> I["Cập nhật evidence, kết luận và báo cáo"]
~~~

Một ngoại lệ hợp lệ thường cần ghi: **dữ liệu và phạm vi bị ảnh hưởng**, lý do, kịch bản rủi ro, biện pháp thay thế, người xử lý, người có thẩm quyền chấp nhận, ngày hết hạn và điều kiện đánh giá lại. Data owner nên được tham vấn hoặc đề xuất phương án liên quan dữ liệu trong phạm vi, nhưng **không mặc nhiên là risk owner hoặc người có quyền phê duyệt mọi ngoại lệ**.

Nếu có dấu hiệu sự cố thực tế, phải tuân thủ quy trình ứng cứu và thông báo theo nghĩa vụ áp dụng. Quyết định bảo tồn bằng chứng, cô lập hệ thống, thông báo đối tác/chủ thể dữ liệu hay cơ quan có thẩm quyền phụ thuộc quy trình và pháp luật, không do Data owner tự quyết ngoài thẩm quyền.

## 12. Bàn giao và đánh giá lại ownership

Data owner có thể thay đổi khi sáp nhập bộ phận, ra sản phẩm mới, tách miền dữ liệu, thay công nghệ hoặc thay nhân sự. Để không mất trách nhiệm, quá trình bàn giao nên gồm:

1. Danh sách các **data assets/data domains** thuộc phạm vi, người phụ trách cũ và mới.
2. Mức phân loại, quy tắc sử dụng và những yêu cầu chưa được làm rõ.
3. Hệ thống/bản sao, data lineage, bên thứ ba và hệ thống phụ thuộc.
4. Ma trận phân quyền đã phê duyệt, nhóm người dùng quan trọng và lịch rà soát.
5. Controls, owner kỹ thuật, nguồn bằng chứng, các kết quả đánh giá gần nhất.
6. Phát hiện, ngoại lệ, sự cố đang xử lý, người có thẩm quyền quyết định và hạn tồn đọng.
7. Quyền truy cập của owner mới tới catalog, báo cáo, hệ thống phê duyệt và đầu mối liên hệ.
8. Xác nhận bàn giao, ngày hiệu lực và kế hoạch kiểm tra lại những phần rủi ro cao.

Quản trị nên phát hiện **dữ liệu không có owner**, owner không còn làm việc tại tổ chức, hoặc owner không còn thẩm quyền với hệ thống đã chuyển nhóm. Một hệ thống có quá nhiều owner cùng ký mà không có người ra quyết định cuối cùng cũng cần được làm rõ.

## 13. Theo dõi hiệu quả vai trò Data owner

Không nên đánh giá Data owner chỉ bằng số tài liệu đã ký. Một số thước đo hữu ích:

| Chỉ số | Mục đích | Cách tránh hiểu sai |
| --- | --- | --- |
| Tỷ lệ data assets quan trọng có owner và phạm vi rõ | Phát hiện tài sản dữ liệu chưa được quản trị. | Tên owner trên catalog chưa chứng minh quyền hạn hoặc khả năng hành động. |
| Tỷ lệ dataset có phân loại được rà soát còn hiệu lực | Đánh giá độ đầy đủ của yêu cầu bảo vệ. | Cần kiểm tra chất lượng nhãn và dữ liệu ngoài inventory. |
| Tỷ lệ quyền truy cập được review đúng hạn và hành động thu hồi hoàn tất | Phát hiện quyền dư thừa/tồn đọng. | Review “đã ký” cần đi kèm quyết định và bằng chứng thu hồi. |
| Tỷ lệ controls dữ liệu có bằng chứng gần nhất hợp lệ | Theo dõi khả năng chứng minh yêu cầu. | Evidence phải đúng claim, phạm vi, phiên bản; nhiều hiện vật không đồng nghĩa bảo vệ tốt. |
| Tuổi các phát hiện/ngoại lệ chưa đóng và tỷ lệ retest đạt | Đo khả năng phối hợp khắc phục. | Đóng ticket không đủ nếu chưa xác minh kết quả. |
| Số thay đổi schema, đối tác hoặc hệ thống thiếu đánh giá ảnh hưởng | Phát hiện mất dấu rủi ro khi dữ liệu di chuyển. | Chỉ số phụ thuộc khả năng nhận diện thay đổi thực tế. |

Khi thiết kế dashboard, nên cho phép xem từ chỉ số tổng quan tới **data asset, owner, claim, control, evidence, phát hiện và quyết định**. Mục tiêu là giúp phát hiện lỗ hổng trong trách nhiệm và mức bảo vệ thực tế, tránh tối ưu một chỉ số hình thức.

## 14. Những ngộ nhận cần tránh

| Ngộ nhận | Điều cần hiểu đúng |
| --- | --- |
| “Data owner là người quản trị database.” | DBA/custodian quản lý kỹ thuật; Data owner chịu trách nhiệm nghiệp vụ và yêu cầu bảo vệ trong phạm vi. |
| “Ai tạo file thì người đó sở hữu toàn bộ quyết định về dữ liệu.” | Ownership phải do tổ chức phân công dựa trên miền nghiệp vụ, thẩm quyền và chính sách. |
| “Data owner có thể cấp quyền bất kỳ nếu đồng ý.” | Quyết định truy cập phải tuân thủ nghĩa vụ, chính sách, quyền tối thiểu và phân tách nhiệm vụ. |
| “Data owner là bên kiểm soát dữ liệu theo luật.” | Hai khái niệm có bối cảnh khác nhau; vai trò quản trị nội bộ không tự thay thế nghĩa vụ pháp lý. |
| “Đã mã hóa dữ liệu thì không cần phân loại.” | Phân loại định hướng cả truy cập, chia sẻ, sử dụng, retention, toàn vẹn và sẵn sàng. |
| “Có backup nghĩa là dữ liệu luôn phục hồi được.” | Phải kiểm thử restore, xác minh tính nhất quán và thời gian/điểm phục hồi theo mục tiêu. |
| “Đã phê duyệt quyền một lần thì quyền tiếp tục hợp lệ.” | Cần thu hồi khi mất nhu cầu, hết hạn hoặc thay đổi vai trò; có bằng chứng rà soát. |
| “Data steward và Data owner luôn là một.” | Steward thường vận hành dữ liệu hằng ngày; owner chịu trách nhiệm giải trình và quyết định theo thẩm quyền. |
| “Dữ liệu đã pseudonymize thì không thể nhận diện lại.” | Mức rủi ro phụ thuộc khả năng liên kết, thông tin bổ sung, phương pháp và bối cảnh. |
| “Audit báo pass nghĩa là mọi bản sao dữ liệu đều an toàn.” | Kết luận audit phụ thuộc phạm vi, phương pháp và thời điểm; cần theo dõi các thay đổi và điểm chưa được kiểm chứng. |

## 15. Bài tập tự kiểm tra

### Tình huống A — Không ai chịu trách nhiệm đối với dữ liệu xuất

Một API xuất báo cáo được team ứng dụng xây dựng. Platform chỉ quản lý bucket nhận dữ liệu; phòng phân tích có nhu cầu nghiệp vụ nhưng không có người phê duyệt trường nào được xuất. Ai phải nhận vai trò Data owner và bằng chứng gì cần có?

**Gợi ý:** Tổ chức nên giao Data owner cho **miền dữ liệu liên quan**, thường là đơn vị có quyền nghiệp vụ đối với dữ liệu, kèm quyền hạn rõ. Owner xác định mục đích, trường, đối tượng nhận, thời hạn, phân loại; engineering/platform thực thi. Bằng chứng gồm phê duyệt, data inventory, test schema và quyền, log export, kiểm chứng ở đích và kết quả đánh giá lại.

### Tình huống B — Quyền được phê duyệt nhưng quá rộng

Data owner duyệt cho nhân viên hỗ trợ quyền “tra cứu hồ sơ khách hàng theo đơn”; đội IAM lại cấp quyền đọc toàn bộ database CRM. Có thể tuyên bố quy trình phân quyền đạt không?

**Gợi ý:** Không. Phải đối chiếu **quyền kỹ thuật thực tế** với nhu cầu/phạm vi được phê duyệt. Data owner xác nhận yêu cầu nghiệp vụ; operator thu hẹp quyền theo tiêu chí; assessor kiểm tra lại trường hợp được phép và không được phép. Bằng chứng phê duyệt riêng lẻ không đủ chứng minh control vận hành đúng.

### Tình huống C — Sao lưu đạt nhưng không xóa được dữ liệu

Dữ liệu thử nghiệm lấy từ production đã hết thời hạn sử dụng ở staging. Job xóa bảng thành công nhưng backup vẫn lưu thêm sáu tháng. Kết luận “đã xóa hoàn toàn” có phù hợp?

**Gợi ý:** Không thể khẳng định nếu chưa xem chính sách, kiến trúc backup, nghĩa vụ và cách cô lập/bảo vệ dữ liệu còn lưu. Owner phối hợp privacy/legal và custodian xác định cơ chế lưu giữ/xóa có thể kiểm chứng, hạn chế dùng lại bản backup và ghi rõ các giới hạn của claim.

### Tình huống D — Thay đổi người sở hữu dữ liệu

Tập dữ liệu khách hàng chuyển từ nhóm Sales sang Customer Operations. Một số quyền truy cập của Sales vẫn được duy trì; danh sách ngoại lệ chưa chuyển giao. Những bước nào phải hoàn tất?

**Gợi ý:** Phân công owner mới; bàn giao inventory, phân loại, ma trận quyền, controls, evidence và ngoại lệ; rà soát lại quyền dựa vào nhu cầu hiện tại; giao việc thu hồi và retest; cập nhật catalog, owner dự phòng và lịch đánh giá lại.

## Kết luận

**Data owner** giúp biến quản lý dữ liệu thành trách nhiệm có thể giải trình: **biết dữ liệu nào cần bảo vệ, vì sao, ai được sử dụng, quy tắc nào phải được thực thi và bằng chứng nào chứng minh quy tắc đang có hiệu lực**. Vai trò này kết nối nghiệp vụ với data steward, kỹ thuật, security assurance, audit và quản trị rủi ro. Để chương trình **SECURITY_SECURITY_ASSURANCE** liên tục và đáng tin cậy, cần giao owner đúng phạm vi và thẩm quyền, duy trì đường truy vết từ dữ liệu đến controls và evidence, kiểm tra hoạt động thực tế, xử lý phát hiện có người chịu trách nhiệm và đánh giá lại mọi khi dữ liệu hoặc cách sử dụng thay đổi.
