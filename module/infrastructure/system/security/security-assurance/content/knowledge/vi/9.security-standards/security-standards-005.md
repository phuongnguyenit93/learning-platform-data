# Chuẩn theo dữ liệu (Data-Based Security Standards) trong Security Assurance

## 1. Vì sao security standard cần bắt đầu từ dữ liệu?

Một hệ thống SaaS có thể chứa cùng lúc trang giới thiệu sản phẩm công khai, hồ sơ khách hàng, hóa đơn, bí mật tích hợp và báo cáo quản trị. Nếu tất cả được áp dụng cùng một nhóm quy tắc bảo mật, tổ chức có thể gặp hai sai lầm:

- **Bảo vệ chưa đủ:** dữ liệu nhạy cảm bị đưa vào môi trường thử nghiệm, log hoặc kho phân tích có quyền truy cập rộng vì mọi nguồn dữ liệu được đối xử như nhau.
- **Bảo vệ không phù hợp:** dành cùng chi phí, độ phức tạp và quy trình phê duyệt cho nội dung công khai và dữ liệu giao dịch quan trọng, trong khi những rủi ro thực sự khác nhau.

**Chuẩn theo dữ liệu** là cách tổ chức quy định **các yêu cầu bảo vệ tối thiểu cho dữ liệu dựa trên loại, độ nhạy, mục đích sử dụng, hậu quả khi bị xâm hại, vòng đời và bối cảnh xử lý**. Chuẩn trả lời:

1. Dữ liệu nào thuộc phạm vi và ai chịu trách nhiệm phân loại?
2. Các mức phân loại hoặc thuộc tính dữ liệu được định nghĩa như thế nào?
3. Với từng nhóm dữ liệu, **điều gì bắt buộc** khi thu thập, lưu trữ, truy cập, chia sẻ, sao chép, sao lưu và xóa?
4. Control nào phải bảo đảm từng yêu cầu, tại đâu và do ai vận hành?
5. Phép kiểm tra và bằng chứng nào cho phép kết luận yêu cầu đã được đáp ứng?
6. Khi dữ liệu, mục đích, hệ thống hoặc nghĩa vụ thay đổi, chuẩn được áp dụng và đánh giá lại ra sao?

Trong chương **Security standard** thuộc module **SECURITY_SECURITY_ASSURANCE**, trọng tâm không chỉ là viết quy tắc. Mục tiêu của module là **đánh giá có bằng chứng** rằng hệ thống đáp ứng mục tiêu bảo mật qua phân tích rủi ro, requirements, controls, kiểm thử, audit và khắc phục phát hiện. Vì thế chuẩn theo dữ liệu phải tạo được đường truy vết:

**Data asset → Phân loại/tác động → Yêu cầu bảo mật → Control → Kiểm chứng → Evidence → Phát hiện/quyết định rủi ro.**

> Một nhãn “Confidential” trên bảng dữ liệu không tự bảo vệ dữ liệu. Nhãn chỉ có giá trị nếu được chuyển thành **quy tắc có thể triển khai, kiểm tra và thực thi** trên mọi đường dữ liệu liên quan.

## 2. Phân biệt policy, standard, baseline, procedure và regulation

Các khái niệm dưới đây thường bị dùng lẫn nhau:

| Khái niệm | Vai trò | Ví dụ trong bảo vệ dữ liệu |
| --- | --- | --- |
| **Security policy – Chính sách** | Nguyên tắc và nghĩa vụ cấp tổ chức, được phê duyệt bởi cấp có thẩm quyền. | “Dữ liệu nhạy cảm chỉ được xử lý cho mục đích được phép và phải được bảo vệ phù hợp với rủi ro.” |
| **Security standard – Chuẩn nội bộ** | Các yêu cầu cụ thể, nhất quán, thường mang tính bắt buộc trong phạm vi được xác định. | “Dataset nhãn Restricted phải có quyền truy cập theo vai trò/ngữ cảnh, log hoạt động nhạy cảm và cơ chế kiểm tra định kỳ.” |
| **Security baseline – Cấu hình/kiểm soát tối thiểu** | Bộ kiểm soát cơ sở để triển khai đồng nhất cho một loại tài sản hoặc mức nhạy cảm. | Baseline đối với object storage chứa dữ liệu Restricted: mặc định không công khai, mã hóa, logging, kiểm tra drift. |
| **Procedure / runbook – Quy trình** | Ai làm gì, thứ tự nào, khi nào, theo cách nào. | Quy trình duyệt quyền truy cập, xoay vòng khóa, thu hồi quyền và xử lý yêu cầu xóa. |
| **Guideline – Hướng dẫn** | Khuyến nghị hoặc phương án triển khai khi có nhiều lựa chọn hợp lệ. | Cách cấu hình mã hóa trên một nền tảng cloud cụ thể. |
| **Regulation / legal obligation – Nghĩa vụ pháp lý** | Quy định bắt buộc theo phạm vi pháp luật có hiệu lực, không do tổ chức tự chọn. | Nghĩa vụ về dữ liệu cá nhân hoặc báo cáo sự cố khi thực sự áp dụng. |
| **External standard / industry framework** | Chuẩn hoặc bộ yêu cầu bên ngoài, có thể được áp dụng theo chứng nhận, hợp đồng, ngành hoặc nghĩa vụ. | ISO/IEC 27001, ISO/IEC 27701, PCI DSS trong phạm vi liên quan. |

**Không đồng nhất một chuẩn với việc đã được chứng nhận hay tuân thủ pháp luật.** Ví dụ ISO/IEC 27001 là chuẩn yêu cầu đối với hệ thống quản lý an toàn thông tin; PCI DSS là tập yêu cầu chuyên biệt bảo vệ dữ liệu thanh toán trong phạm vi áp dụng. Chỉ nhắc tên một framework trong chính sách không chứng minh hệ thống đã đáp ứng nó. Các phiên bản, nghĩa vụ và phạm vi áp dụng cụ thể phải được xác minh từ văn bản có hiệu lực và tư vấn chuyên môn tương ứng.

### Hai cách hiểu của “chuẩn theo dữ liệu”

Trong quản trị bảo mật, cụm này có thể bao gồm hai lớp bổ trợ:

1. **Data-centric internal standards:** chuẩn nội bộ thay đổi theo phân loại, loại dữ liệu và mức ảnh hưởng của từng data asset.
2. **Data-type-specific obligations:** các bộ yêu cầu chuyên biệt do pháp luật, hợp đồng, quy tắc ngành hoặc cam kết với đối tác áp đặt đối với **một loại dữ liệu cụ thể**.

Tổ chức cần kết hợp hai lớp đó. **Chuẩn nội bộ không được hạ thấp yêu cầu bắt buộc**, nhưng cũng không nên giả định mọi dữ liệu thuộc cùng một quy định.

## 3. Định nghĩa tài sản dữ liệu và phạm vi áp dụng

Muốn áp chuẩn, trước hết phải biết dữ liệu đang ở đâu. Một **data asset** có thể là bảng, collection, object, bộ dữ liệu, luồng event hoặc sản phẩm dữ liệu có mục đích và owner được xác định.

### Thông tin tối thiểu của data inventory

| Thuộc tính | Câu hỏi quản trị | Ví dụ |
| --- | --- | --- |
| **Data asset ID / tên** | Đâu là định danh ổn định của tập dữ liệu? | CUSTOMER-CONTACT-001 |
| **Data owner / steward** | Ai định nghĩa yêu cầu và ai duy trì metadata? | Customer Operations / Customer Data Steward |
| **Mục đích sử dụng** | Vì sao thu thập, xử lý hoặc chia sẻ dữ liệu? | Hỗ trợ giao hàng và giải quyết yêu cầu khách hàng |
| **Loại, trường, chủ thể** | Dữ liệu là gì; có dữ liệu cá nhân, thanh toán hay bí mật kinh doanh không? | Tên, email, số điện thoại, địa chỉ |
| **Nhãn phân loại** | Độ nhạy và hậu quả CIA thế nào? | Confidential; tính bí mật cao, sẵn sàng trung bình |
| **Nơi lưu và bản sao** | Dữ liệu nằm ở đâu, đi qua đâu? | CRM production, search index, cache, analytics, backup |
| **Bên nhận và nhà cung cấp** | Ai xử lý dữ liệu bên ngoài hệ thống gốc? | Dịch vụ gửi thông báo, đơn vị vận chuyển |
| **Controls và evidence** | Yêu cầu bảo vệ nào áp dụng, kiểm tra bằng gì? | AUTHZ-CUST-01, ENC-CUST-02, audit evidence |
| **Retention và vòng đời** | Được lưu tới khi nào, xóa bằng cơ chế nào? | Lịch lưu được phê duyệt theo mục đích/nghĩa vụ |
| **Phiên bản và trigger** | Khi nào dữ liệu hoặc bối cảnh thay đổi? | Thêm trường, đối tác, vùng lưu, mục đích mới |

Các data asset nên gắn với **data lineage**: nguồn tạo → biến đổi → kho tạm → ứng dụng tiêu thụ → xuất/chia sẻ → bản sao lưu. Nếu chỉ gắn nhãn vào database gốc, file CSV xuất ra email hoặc object storage có thể không được áp cùng mức kiểm soát.

### Data owner khác system owner

**Data owner** chịu trách nhiệm giải trình về cách dữ liệu được phân loại, sử dụng, bảo vệ theo quyền được giao; **system owner** chịu trách nhiệm đối với dịch vụ xử lý dữ liệu; **control owner** chịu trách nhiệm về một security control. Ba vai trò có thể phối hợp trên cùng một dữ liệu nhưng không tự thay thế nhau. Chủ sở hữu dữ liệu không mặc nhiên là người có quyền thực thi truy vấn production hoặc phê duyệt mọi ngoại lệ pháp lý.

## 4. Phân loại theo độ nhạy và hậu quả CIA

Một cách thông dụng là dùng các lớp **Public – Internal – Confidential – Restricted**. Đây là **ví dụ phân loại nội bộ**, không phải một hệ nhãn bắt buộc với mọi tổ chức.

| Lớp minh họa | Mô tả | Ví dụ | Hướng bảo vệ |
| --- | --- | --- | --- |
| **Public – Công khai** | Được phê duyệt để công bố rộng rãi. | Bảng giá đã đăng, tài liệu quảng bá công khai. | Bảo vệ tính toàn vẹn, nguồn công bố và sẵn sàng phù hợp; không mặc định “không cần bảo mật”. |
| **Internal – Nội bộ** | Chỉ phục vụ nội bộ hoặc bên được phép, hậu quả khi tiết lộ thường có giới hạn. | Quy trình vận hành, tài liệu dự án thông thường. | Kiểm soát truy cập cơ bản, hạn chế chia sẻ ra ngoài, bảo vệ lưu trữ phù hợp. |
| **Confidential – Mật** | Tiết lộ hoặc sửa đổi có thể gây thiệt hại đáng kể. | Hồ sơ khách hàng, thông tin hợp đồng chưa công khai, báo cáo kinh doanh nhạy cảm. | Quyền tối thiểu, giới hạn chia sẻ, mã hóa phù hợp, audit hoạt động nhạy cảm và review. |
| **Restricted – Hạn chế cao** | Tác động nghiêm trọng khi lộ, sửa sai hoặc mất; phạm vi và quy tắc sử dụng chặt. | Khóa ký quan trọng, dữ liệu đặc biệt nhạy cảm hoặc hồ sơ nghiệp vụ trọng yếu theo tiêu chí tổ chức. | Quyền chặt theo nhu cầu, tách nhiệm vụ, bảo vệ khóa, giám sát và kiểm chứng mức cao, xử lý ngoại lệ có thẩm quyền. |

**Mức nhạy cảm không chỉ là bí mật.** Một bảng giá đã công khai có thể có **Confidentiality thấp** nhưng **Integrity cao** nếu thay đổi sai gây thiệt hại lớn. Dữ liệu điều khiển thiết bị an toàn có thể có **Availability/Integrity rất cao** dù không chứa dữ liệu cá nhân.

### Ma trận CIA có thể tách biệt với nhãn tổng

Ví dụ một data asset được đánh giá như sau:

| Data asset | Confidentiality | Integrity | Availability | Giải thích |
| --- | :---: | :---: | :---: | --- |
| Trang giới thiệu công khai | Thấp | Trung bình | Trung bình | Nội dung công khai nhưng thay đổi trái phép gây hiểu nhầm và giảm uy tín. |
| Hồ sơ liên hệ khách hàng | Cao | Cao | Trung bình | Lộ và thay đổi địa chỉ có hậu quả; một số chức năng có thể tạm gián đoạn. |
| Trạng thái đơn/thanh toán | Trung bình–cao | Rất cao | Cao | Sai lệch và không sẵn sàng ảnh hưởng giao dịch và đối soát. |
| Private signing key | Rất cao | Rất cao | Theo hệ thống sử dụng | Lộ khóa có thể giả chữ ký; sửa/mất khóa cũng gây hậu quả lớn. |

Các mức trên chỉ để học. Tổ chức phải định nghĩa **tiêu chí hậu quả, ví dụ tham chiếu, quy tắc tổng hợp, thẩm quyền phê duyệt và chu kỳ xem lại**. Không nên chọn nhãn chỉ theo tên bảng hoặc theo cảm nhận của kỹ sư.

### Phân loại phải xét ngữ cảnh và kết hợp dữ liệu

Một trường có vẻ ít nhạy cảm có thể trở nên nhạy cảm khi liên kết với các nguồn khác. Báo cáo tổng hợp có thể làm lộ thông tin của một nhóm quá nhỏ; dữ liệu đã loại định danh trực tiếp vẫn có thể bị liên kết để nhận diện lại. Khi **tập dữ liệu được kết hợp, chuyển mục đích hoặc đưa sang môi trường có quyền khác**, Data owner cần đánh giá lại độ nhạy và mức kiểm soát.

## 5. Xây dựng baseline từ phân loại thay vì khẩu hiệu chung

Chuẩn có thể tạo **ma trận yêu cầu tối thiểu** theo nhóm dữ liệu. Bảng dưới đây là mẫu định hướng, **không phải tiêu chuẩn bắt buộc hay mức tuân thủ pháp luật**. Các điều kiện cụ thể phải được phê duyệt trong chính sách của tổ chức.

| Lĩnh vực | Public | Internal | Confidential | Restricted |
| --- | --- | --- | --- | --- |
| **Truy cập** | Công khai sau phê duyệt công bố; quyền sửa hạn chế. | Danh tính nội bộ/bên được phép. | Quyền tối thiểu, phân quyền theo vai trò/ngữ cảnh, review. | Quyền theo nhu cầu nghiêm ngặt, hạn chế đặc quyền và phê duyệt phù hợp. |
| **Mã hóa/khóa** | Bảo vệ kênh và integrity phù hợp. | Mã hóa phù hợp nền tảng/đường truyền. | Mã hóa khi truyền/lưu theo tiêu chuẩn đã duyệt, quản lý khóa tách biệt. | Mã hóa và quyền khóa được kiểm soát chặt, kiểm chứng cả key lifecycle. |
| **Logging** | Log thay đổi công bố và hành vi ảnh hưởng tính toàn vẹn. | Log truy cập/thay đổi theo rủi ro. | Audit các hành động nhạy cảm và truy xuất dữ liệu quan trọng. | Audit và giám sát chặt hơn, bảo vệ bằng chứng, review phù hợp rủi ro. |
| **Chia sẻ** | Chỉ công bố phiên bản được phép. | Chia sẻ có giới hạn và đúng mục đích. | Phê duyệt bên nhận, trường dữ liệu, kênh và mục đích. | Chia sẻ theo quy trình hạn chế riêng; hạn chế sao chép và truy xuất. |
| **Test/analytics** | Kiểm tra nguồn và tính toàn vẹn. | Dữ liệu giả lập nếu không cần dữ liệu thật. | Giảm thiểu, masking/pseudonymization khi phù hợp; kiểm chứng ở đích. | Ưu tiên synthetic; dùng dữ liệu thật chỉ khi được phê duyệt và kiểm soát đặc biệt. |
| **Backup/khôi phục** | Phụ thuộc yêu cầu availability/integrity. | Theo BIA của dịch vụ. | Kết hợp yêu cầu bảo mật dữ liệu backup và phục hồi. | Diễn tập với phạm vi rủi ro cao, bảo vệ bản sao và khóa, kiểm tra integrity. |
| **Retention/xóa** | Theo mục đích, hợp đồng và nghĩa vụ. | Lịch lưu được phê duyệt. | Giới hạn lưu giữ, xử lý bản sao và bằng chứng xóa. | Quản trị chặt thời hạn, ngoại lệ/hold, quyền xóa và dấu vết. |

**Không được dùng bảng này như một checklist có/không thiếu ngữ cảnh.** Ví dụ dữ liệu Public vẫn cần backup nếu nó phục vụ quy trình thiết yếu; một bản ghi Confidential có thể cần phục hồi trong vài phút trong khi một bản ghi Restricted ít được truy cập có yêu cầu sẵn sàng khác. Baseline phải có **những phần bắt buộc chung** và **phần điều chỉnh theo tác động CIA, rủi ro và nghĩa vụ**.

### Yêu cầu phải có tiêu chí kiểm chứng

**Yêu cầu mơ hồ:** “Dữ liệu Restricted phải được bảo vệ tốt.”

**Yêu cầu kiểm chứng được:** “Tập dữ liệu thuộc phạm vi Restricted không được cấu hình truy cập công khai; mọi quyền đọc và xuất dữ liệu phải được cấp theo danh tính/quyền đã phê duyệt, có thời hạn hoặc được review theo quy tắc áp dụng; mọi thay đổi policy phải có audit event và phát hiện sai lệch.”

Để hỗ trợ claim này cần **inventory tài sản, cấu hình quyền thực tế, test truy cập không có quyền, log thay đổi, hồ sơ phê duyệt và bằng chứng xử lý sai lệch**.

## 6. Chuẩn theo từng loại dữ liệu và nghĩa vụ chuyên biệt

Phân loại chung không thay thế các yêu cầu chuyên ngành hoặc nghĩa vụ riêng của một loại dữ liệu.

| Loại dữ liệu/bối cảnh | Câu hỏi cần rà soát | Hệ quả đối với chuẩn nội bộ |
| --- | --- | --- |
| **Dữ liệu cá nhân** | Có dữ liệu liên quan tới cá nhân được nhận diện/có thể nhận diện không? Mục đích, quyền, chia sẻ và thời hạn nào áp dụng? | Cần phối hợp privacy/legal về mục đích xử lý, giới hạn truy cập, lưu giữ, bên nhận và quyền của chủ thể khi áp dụng. |
| **Dữ liệu thanh toán** | Hệ thống có lưu, xử lý hoặc truyền dữ liệu tài khoản thanh toán thuộc phạm vi tiêu chuẩn/chương trình của bên liên quan không? | Đánh giá phạm vi áp dụng bộ yêu cầu thanh toán như PCI DSS khi liên quan, hạn chế data flow và tránh lưu dữ liệu không cần thiết. |
| **Dữ liệu sức khỏe/y tế** | Có thông tin sức khỏe nhạy cảm và nghĩa vụ riêng theo địa bàn/ngành hay không? | Phân loại chặt, giới hạn mục đích/quyền, audit, lưu giữ và tư vấn chuyên môn pháp lý theo phạm vi. |
| **Bí mật thương mại và tài sản trí tuệ** | Mức hậu quả nếu thiết kế, mô hình hoặc dữ liệu nghiên cứu bị sao chép trái phép? | Hạn chế tải/xuất hàng loạt, kiểm soát cộng tác với bên thứ ba, theo dõi thay đổi. |
| **Khóa mật mã/secret/credential** | Lộ khóa có thể giả danh, giải mã hoặc truy cập tài nguyên khác không? | Không xử lý như dữ liệu nghiệp vụ thông thường; cần secret/key management chuyên biệt, quyền sử dụng hạn chế và vòng đời khóa. |
| **Dữ liệu vận hành trọng yếu** | Sai lệch hoặc mất dữ liệu có gây gián đoạn chuỗi cung ứng, thanh toán hoặc ảnh hưởng an toàn không? | Integrity, khả năng phục hồi và đối soát có thể được ưu tiên cao hơn nhãn bí mật. |

Các tên như **ISO/IEC 27001**, **ISO/IEC 27701**, **PCI DSS** hoặc quy định về dữ liệu cá nhân chỉ giúp **nhận diện nguồn yêu cầu cần xem xét**; chúng không có cùng phạm vi và không tự động áp dụng cho mọi hệ thống. Việc xác định chính xác phiên bản, nghĩa vụ, điều khoản và bằng chứng tuân thủ phải theo văn bản hiện hành của tổ chức, hợp đồng và khu vực pháp lý liên quan.

### Một tập dữ liệu chịu nhiều nguồn yêu cầu

Nếu một file xuất chứa cả thông tin giao dịch và dữ liệu cá nhân, tổ chức phải xét:

1. Baseline nội bộ theo mức phân loại.
2. Yêu cầu của hệ thống và hợp đồng với khách hàng.
3. Nghĩa vụ pháp lý/chuyên ngành trong phạm vi thực sự áp dụng.
4. Yêu cầu risk assessment bổ sung nếu hậu quả cao.

Khi các yêu cầu có vẻ mâu thuẫn (ví dụ cần giữ dữ liệu để đáp ứng nghĩa vụ nhưng cũng phải giới hạn lưu giữ), **không tự chọn yêu cầu dễ nhất**. Cần làm rõ mục đích, cơ sở áp dụng, dữ liệu và thời hạn với bên được ủy quyền, rồi ghi quyết định và giới hạn.

## 7. Vòng đời dữ liệu: áp chuẩn ở mọi điểm

Dữ liệu thường di chuyển qua nhiều hệ thống và biến đổi định dạng. Một chuẩn theo dữ liệu cần được áp tại **đầu vào, khi lưu/truy cập, khi chuyển/chia sẻ, khi sao lưu và lúc xóa**.

~~~mermaid
flowchart LR
    A["Thu thập / tạo"] --> B["Phân loại + Catalog"]
    B --> C["Lưu / xử lý"]
    C --> D["Sao chép / chia sẻ"]
    D --> E["Lưu giữ / Archive"]
    E --> F["Xóa / Hủy / Ẩn danh"]
    C --> G["Review + Evidence"]
    D --> G
    E --> G
    G --> B
~~~

| Giai đoạn | Quy tắc theo dữ liệu cần trả lời | Bằng chứng phù hợp |
| --- | --- | --- |
| **Thu thập/tạo** | Trường dữ liệu nào thật sự cần? Nguồn, mục đích và quyền sử dụng đã được xác định? | Schema, data inventory, đánh giá mục đích, thiết kế API/biểu mẫu. |
| **Phân loại/catalog** | Nhãn và hậu quả CIA được duyệt chưa? Dữ liệu mới/biến đổi được gắn nhãn ra sao? | Catalog, quyết định owner, kiểm tra mẫu hoặc luật tự động. |
| **Lưu trữ/xử lý** | Quyền, mã hóa, khóa, logging và toàn vẹn có đáp ứng baseline? | Config, IAM, encryption/KMS, tests phân quyền, audit log. |
| **Sao chép/xuất/chia sẻ** | Bản sao có kế thừa yêu cầu? Bên nhận, mục đích, trường và thời hạn được phê duyệt? | Data transfer register, export tests, hợp đồng/quyết định, cấu hình đích. |
| **Backup/khôi phục** | Bản sao có được bảo vệ, có thử restore đúng mục tiêu không? | Backup config, restore drill, đo RTO/RPO, đối soát dữ liệu. |
| **Lưu giữ/archival** | Thời hạn, cấp lưu và các ngoại lệ/hold có đúng quy tắc? | Retention schedule, kết quả job, hồ sơ giữ bằng chứng. |
| **Xóa/hủy/ẩn danh** | Dữ liệu nguồn, bản sao và bên nhận được xử lý đúng phạm vi nào? | Bản ghi yêu cầu, kết quả xóa, kiểm tra ở đích, giới hạn backup. |

### Nhãn có thể cần kế thừa hoặc được đánh giá lại

Khi dữ liệu Confidential được trích một số trường để làm báo cáo, **không mặc định** đầu ra trở thành Public. Cần xem xét thông tin còn lại, khả năng suy diễn và đối tượng sử dụng. Ngược lại, một tài liệu đã được duyệt công bố có thể thay đổi mức phân loại khi bản công khai được tạo theo quy trình được phép.

Quy tắc kế thừa không nhất thiết chỉ là “lấy nhãn cao nhất” trong mọi trường hợp; nếu muốn hạ nhãn sau biến đổi hoặc tổng hợp, phải có **tiêu chí chứng minh kết quả thực sự không còn các rủi ro tương ứng**, owner có thẩm quyền và bằng chứng kiểm chứng.

## 8. Chuẩn kiểm soát truy cập theo dữ liệu

Quyền truy cập không nên chỉ dựa trên việc “đã đăng nhập” hoặc “nằm trong mạng nội bộ”. Chuẩn cần xác định **chủ thể, hành động, dữ liệu, mục đích và ngữ cảnh**.

### Phân biệt Authentication, Authorization và mục đích

- **Authentication:** yêu cầu đến từ danh tính nào theo nguồn tin cậy?
- **Authorization:** danh tính đó được thực hiện thao tác cụ thể trên tài nguyên nào?
- **Purpose/need-to-know:** thao tác có phù hợp với mục đích được phê duyệt không?
- **Accountability:** có thể biết ai yêu cầu, ai cấp, khi nào và kết quả thế nào không?

Ví dụ nhân viên support có thể xem địa chỉ giao hàng của đơn mình đang xử lý nhưng không có quyền **xuất toàn bộ hồ sơ khách hàng**. Một token hợp lệ không đồng nghĩa có quyền đọc mọi object hay bỏ qua tenant boundary.

### RBAC, ABAC và object-level authorization

**RBAC** cấp quyền dựa trên vai trò; **ABAC** xét thuộc tính như phân loại dữ liệu, tenant, môi trường, mục đích, trạng thái phiên hoặc thiết bị; **object-level authorization** kiểm tra quyền trên từng đối tượng. Chúng có thể bổ trợ nhau.

Ví dụ quy tắc ở mức khái niệm, **không phải policy engine chạy thực tế**:

~~~text
ALLOW READ(customer_contact) IF
    principal.authenticated
    AND principal.tenant_id == customer_contact.tenant_id
    AND principal.role IN approved_roles
    AND customer_contact.classification <= role.allowed_classification
    AND request.purpose IN approved_purposes
ELSE DENY
~~~

Ký hiệu so sánh phân loại chỉ có nghĩa nếu tổ chức xác định **thứ tự nhãn và các điều kiện bổ sung**. Thực tế, kiểm tra “mức phân loại thấp hơn” **chưa đủ** để cấp quyền: vẫn phải ràng buộc tenant, đối tượng, hành động, mục đích và các hạn chế bắt buộc khác.

### Kiểm chứng chuẩn phân quyền

Cần thử cả **tình huống hợp lệ** và **tình huống phải bị từ chối**:

- Người dùng tenant A được đọc đúng đối tượng thuộc phạm vi A nhưng không được đọc đối tượng B.
- Người có vai trò chỉ đọc không được sửa, xóa hoặc export.
- Tài khoản dịch vụ chỉ có quyền cần cho job, không kế thừa quyền của operator vô hạn.
- Quyền hết hạn hoặc bị thu hồi không còn cho phép truy cập qua session, cache, link tải hoặc API khác theo yêu cầu áp dụng.
- Đường truy cập qua GraphQL, batch, file export, broker và object storage không bypass chính sách.

**Bằng chứng:** permission matrix được duyệt, cấu hình IAM, kết quả negative tests theo đối tượng/tenant, review quyền định kỳ, audit cấp/thu hồi quyền và bằng chứng deployment.

## 9. Mã hóa, quản lý khóa và bảo vệ dữ liệu khi sử dụng

Chuẩn theo dữ liệu phải chỉ rõ **mã hóa bảo vệ rủi ro nào** và ai quản trị khóa, không chỉ yêu cầu “bật encryption”.

### 9.1. Dữ liệu khi truyền (in transit)

Dữ liệu nhạy cảm qua mạng không đáng tin cần được bảo vệ bằng **giao thức và cấu hình được tổ chức duyệt**, xác minh peer khi phù hợp và hạn chế đường truyền không được phép. Với traffic nội bộ, phải đánh giá ranh giới tin cậy, không mặc định an toàn chỉ vì chạy cùng cluster.

**Evidence:** cấu hình endpoints, kiểm thử đường truyền, chứng chỉ/khóa và quy trình thay đổi. Kiểm tra cả luồng event, backup, chuyển file cho đối tác và các đường phụ.

### 9.2. Dữ liệu khi lưu (at rest)

Mã hóa cơ sở dữ liệu, volume hoặc object storage có thể giảm hậu quả khi mất phương tiện lưu trữ hoặc truy cập trái phép ở lớp nhất định. Tuy nhiên:

- Một ứng dụng có quyền giải mã vẫn có thể **trả dữ liệu cho người không có quyền** nếu authorization sai.
- Mã hóa volume không ngăn người có quyền đọc database qua API hợp lệ.
- Bản sao, snapshot, cache và file export có thể dùng lớp bảo vệ khác nếu không được quản trị.

Cần gắn yêu cầu mã hóa với **threat scenario**, dữ liệu và ranh giới thực tế.

### 9.3. Vòng đời khóa và secret

Đối với dữ liệu có mức nhạy cảm cao, phải xét: quyền tạo/sử dụng/xoay vòng/thu hồi khóa, phân tách nhiệm vụ, kiểm toán thao tác với khóa, sao lưu/phục hồi khóa khi phù hợp, cách xử lý mất quyền truy cập và ảnh hưởng của việc xóa khóa. Một cấu hình “encrypted: true” chưa chứng minh **quyền giải mã** được kiểm soát.

### 9.4. Dữ liệu khi xử lý (in use)

Dữ liệu thường cần xuất hiện ở dạng có thể xử lý trong bộ nhớ hoặc trong logic ứng dụng. Mã hóa khi lưu và khi truyền không tự bảo vệ dữ liệu khỏi bug tại endpoint, query sai quyền, dump bộ nhớ hoặc log lộ. Cần kiểm soát truy cập, hardening, data minimization, giới hạn quyền xử lý, kiểm thử logic nghiệp vụ và biện pháp bổ sung theo rủi ro.

## 10. Masking, pseudonymization, tokenization và ẩn danh

Những thuật ngữ này liên quan nhưng không tương đương:

| Kỹ thuật | Mục đích điển hình | Giới hạn |
| --- | --- | --- |
| **Masking / che dữ liệu** | Loại bỏ hoặc thay một phần thông tin hiển thị/đầu ra. | Masking chỉ ở UI không bảo vệ bản gốc trong API, log hoặc database. |
| **Pseudonymization / giả định danh** | Thay định danh trực tiếp bằng mã, giữ khả năng liên kết khi có thông tin bổ sung được bảo vệ. | Có thể vẫn nhận diện lại khi có bảng ánh xạ hoặc dữ liệu liên kết. |
| **Tokenization** | Thay giá trị nhạy cảm bằng token, kiểm soát cơ chế ánh xạ hoặc sử dụng token. | Kho token/vault và API giải token trở thành tài sản cần bảo vệ. |
| **Anonymization / ẩn danh** | Xử lý để dữ liệu không còn gắn được với cá nhân theo tiêu chí/bối cảnh liên quan. | Khả năng tái nhận diện phụ thuộc dữ liệu bổ sung, phương pháp và khả năng của bên nhận; không nên tuyên bố tuyệt đối khi chưa đánh giá. |
| **Synthetic data** | Dùng dữ liệu được tạo ra cho kiểm thử/phân tích thay vì bản sao thật khi phù hợp. | Nếu tạo từ dữ liệu thật, vẫn phải kiểm tra nguy cơ ghi nhớ/tiết lộ; dữ liệu giả không luôn đại diện đầy đủ cho phân phối thực. |

Ví dụ môi trường staging cần kiểm tra hiệu năng tìm kiếm khách hàng. Thay vì sao chép toàn bộ hồ sơ production, nhóm nên hỏi **có dùng dữ liệu synthetic được không**, chỉ giữ trường cần thiết hay không và nếu phải dùng dữ liệu thật thì điều kiện phê duyệt và kiểm chứng ra sao.

**Bằng chứng:** tài liệu phép biến đổi, sample kiểm chứng ở đầu ra, test trường nhạy cảm bị loại, review nguy cơ liên kết/tái nhận diện, cấu hình quyền ở môi trường đích.

## 11. Chia sẻ dữ liệu, đối tác và shared responsibility

Chuẩn theo dữ liệu phải **đi cùng dữ liệu khi vượt ranh giới hệ thống hoặc tổ chức**. Khi chia sẻ cho API bên thứ ba, kho phân tích, dịch vụ gửi email hoặc SaaS, các câu hỏi cần có:

1. Bên nhận là ai, có vai trò và mục đích xử lý đã được xác định không?
2. Những trường dữ liệu nào thật sự cần chuyển, với thời gian sử dụng bao lâu?
3. Data owner và bên privacy/legal có phải tham gia phê duyệt theo phạm vi không?
4. Kênh truyền, danh tính nhận, quyền truy cập và khóa do ai quản lý?
5. Bên nhận có thể sao chép, phân phối tiếp hoặc lưu dữ liệu ở nơi khác không?
6. Log và evidence nào có thể chứng minh hoạt động chuyển, sử dụng và xóa?
7. Khi phát hiện sự cố hoặc yêu cầu hủy dữ liệu, ai liên hệ và cơ chế kiểm tra kết quả là gì?

### Cloud/SaaS không xóa trách nhiệm của bên sử dụng

Nhà cung cấp có thể vận hành hạ tầng lưu trữ, tính sẵn sàng nền tảng và một số security controls; tổ chức sử dụng dịch vụ thường vẫn chịu trách nhiệm xác định **dữ liệu được tải lên, quyền truy cập, mục đích, thời hạn và cấu hình dịch vụ thuộc phần của mình**. Phải có **bản đồ trách nhiệm theo từng control** và người chịu trách nhiệm nội bộ kiểm tra thông tin nhà cung cấp.

Hợp đồng, báo cáo đánh giá của bên thứ ba hoặc chứng nhận có thể là một nguồn evidence, nhưng phải kiểm tra **phạm vi, kỳ đánh giá, hệ thống và các ngoại lệ**; không thể thay thế mọi kiểm thử cấu hình do chính khách hàng thực hiện.

## 12. Retention, xóa và khả năng phục hồi theo yêu cầu dữ liệu

Hai mục tiêu dễ xung đột là **không lưu dữ liệu quá lâu** và **có thể khôi phục dữ liệu khi gặp sự cố**. Chuẩn phải làm rõ từng loại dữ liệu, nghĩa vụ và vòng đời kỹ thuật.

### 12.1. Retention

Data owner phối hợp pháp chế/privacy, records management và vận hành xác định **mục đích, nghĩa vụ, thời hạn, điều kiện archive, tình huống hold và cơ chế kết thúc lưu giữ**. Thời hạn retention không nên do developer tự chọn hoặc mặc định “vô hạn để phòng trường hợp cần”.

### 12.2. Xóa khỏi các bản sao

Khi xóa dữ liệu, cần xác định các điểm lưu: database, search index, cache, queue, warehouse, file export, bản sao đối tác, log, snapshot và backup. Không tự hứa “xóa ngay tất cả backup” nếu kiến trúc thực tế không hỗ trợ; có thể cần cơ chế hết hạn bản sao, ngăn phục hồi ngoài mục đích cho phép và quy trình xử lý khi restore, tương ứng nghĩa vụ áp dụng.

### 12.3. Backup và restore

Mã hóa backup và chạy job thành công **chưa chứng minh dữ liệu phục hồi được**. Cần:

- BIA và yêu cầu nghiệp vụ xác định mức mất dữ liệu/chậm phục hồi có thể chấp nhận.
- Mục tiêu **RPO (Recovery Point Objective)** và **RTO (Recovery Time Objective)** cho kịch bản liên quan.
- Diễn tập restore, đo thời gian, xác minh tính đầy đủ và toàn vẹn của dữ liệu phục hồi.
- Kiểm tra quyền khôi phục, khả năng truy cập khóa, điểm lỗi chung và khả năng bị xóa bản sao trái phép.

Phân loại theo bí mật cần đi cùng phân tích integrity/availability; không thể thay thế BIA bằng cách chỉ nhìn nhãn “Restricted”.

## 13. Từ chuẩn giấy tờ đến thực thi tự động

Với quy mô nhiều tài sản, kiểm tra thủ công từng bucket, tài khoản, bảng và quyền là không đủ. **Policy-as-code** có thể biến một số yêu cầu thành kiểm tra máy đọc được trong CI/CD hoặc giám sát cấu hình production.

### Ví dụ điều khoản chuẩn dạng YAML

Mẫu sau **minh họa một mô hình nội bộ**, không phải cấu hình có thể nạp trực tiếp vào công cụ nào:

~~~yaml
standard_id: DATA-PROTECTION-01
title: "Data-centric protection baseline"
version: "1.0-example"
owner_role: "Security Governance"
scope: "Organizational data assets in managed systems"
classification_levels:
  - Public
  - Internal
  - Confidential
  - Restricted
rules:
  - requirement_id: DATA-ACCESS-01
    applies_when:
      classification: [Confidential, Restricted]
    must:
      - "Use approved authorization for data access"
      - "Deny unauthorized cross-tenant access"
      - "Record approved sensitive operations"
    evidence:
      - "Approved access matrix"
      - "Negative authorization test report"
      - "Production access configuration"
  - requirement_id: DATA-STORAGE-02
    applies_when:
      classification: [Restricted]
      storage_type: "object"
    must:
      - "Disable unauthorized public access"
      - "Use approved encryption and key controls"
    evidence:
      - "Object storage policy test"
      - "Key access review"
exceptions:
  approval: "According to authorized risk governance"
  expiry_required: true
reassessment_triggers:
  - "Data classification changes"
  - "New copy or receiving party"
  - "Change in applicable obligations"
~~~

**Tính đúng đắn của schema và quy tắc triển khai** phải được kiểm tra. Một cấu hình chứa chuỗi “deny public access” nhưng không được pipeline áp dụng hoặc chỉ quét staging thì chưa chứng minh production phù hợp. Cần đối chiếu inventory, nguồn chính sách, phiên bản triển khai, kết quả kiểm tra và phản ứng khi phát hiện drift.

### Công việc nào có thể tự động hóa?

| Hoạt động | Khả năng tự động hóa | Giới hạn |
| --- | --- | --- |
| Kiểm tra bucket không public. | Kiểm tra cấu hình cloud tại deploy và production. | Chưa chứng minh danh sách tất cả bucket đã đầy đủ hoặc các đường cấp quyền tạm đúng. |
| Gắn nhãn tài sản và lọc dữ liệu nhạy cảm. | Scanner/classifier, metadata tagging, DLP rules. | Có false positive/false negative, đặc biệt dữ liệu phi cấu trúc và dữ liệu mới kết hợp. |
| Rà quyền service account. | Tự động xuất ma trận quyền, phát hiện quyền rộng. | Chưa hiểu hết nhu cầu nghiệp vụ, cần owner xác nhận quyền tối thiểu. |
| Kiểm tra mã hóa. | IaC policy và config scanning. | Chưa chứng minh quyền sử dụng khóa hoặc dữ liệu khi xử lý an toàn. |
| Theo dõi audit event. | Event-schema test, collector monitoring, SIEM rule. | Không có alert chưa chứng minh không có sự cố; có thể mất nguồn log. |
| Retention/xóa. | Job, lifecycle policy và kiểm tra các nơi lưu đã biết. | Bản sao ngoài inventory, bên thứ ba, hold và backup có thể cần quy trình riêng. |

## 14. Assurance: chứng minh chuẩn theo dữ liệu thực sự được đáp ứng

Một security standard chỉ có ý nghĩa vận hành khi có **kế hoạch đánh giá thiết kế và hiệu quả hoạt động**.

**Design effectiveness:** Nếu control được triển khai đúng, thiết kế có giải quyết yêu cầu và rủi ro đã nêu không?

**Operating effectiveness:** Control có hoạt động đúng, đủ phạm vi và đủ ổn định trong **thời kỳ được đánh giá** không?

Áp dụng mô hình **Claim – Argument – Evidence (CAE)**:

- **Claim:** “Các object chứa dữ liệu Restricted thuộc phạm vi production không bị truy cập công khai và chỉ chủ thể được phê duyệt mới có quyền đọc.”
- **Argument:** “Mọi object được phát hiện bằng inventory, được áp baseline mặc định từ policy; quyền IAM và đường download được kiểm soát, các thay đổi policy bị phát hiện.”
- **Evidence:** inventory đối chiếu với dữ liệu nhạy cảm, policy trên production, thử truy cập không có quyền, log thay đổi, báo cáo phát hiện drift, kết quả retest và các ngoại lệ đã phê duyệt.

### Ma trận requirements – controls – evidence

| Requirement | Security control | Thiết kế phép kiểm chứng | Evidence |
| --- | --- | --- | --- |
| **DATA-INV-01:** tài sản chứa dữ liệu nhạy cảm được nhận diện. | Data catalog + discovery + owner review. | Đối chiếu nguồn thực tế với catalog, lấy mẫu bản sao và nguồn phi cấu trúc. | Inventory, report discovery, danh sách khoảng trống. |
| **DATA-CLASS-02:** phân loại được duyệt và cập nhật. | Data classification workflow. | Chọn mẫu data asset, kiểm tra quyết định owner và các sự kiện tái phân loại. | Hồ sơ phê duyệt, lịch sử nhãn, báo cáo review. |
| **DATA-AUTHZ-03:** quyền đọc/xuất đúng đối tượng và mục đích. | IAM + object-level authorization. | Negative tests theo vai trò/tenant, kiểm tra quyền đã cấp/thu hồi. | Test report theo release, ma trận quyền, production config. |
| **DATA-ENC-04:** dữ liệu được bảo vệ bằng mã hóa/khóa phù hợp. | Encryption + KMS/secret governance. | Kiểm tra cấu hình từng nơi lưu/luồng và quyền khóa, ngoại lệ. | Config snapshot, access test, key review. |
| **DATA-LOG-05:** hành động nhạy cảm có audit trail. | Structured audit event + protected log pipeline. | Thử event thành công, bị từ chối và lỗi; đối chiếu nguồn–đích. | Event mẫu đã che bí mật, kiểm tra pipeline, log access. |
| **DATA-SHARE-06:** dữ liệu chia sẻ đúng phạm vi. | Approval + transfer controls + data minimization. | Đối chiếu trường được duyệt với file/API thực tế, kiểm tra bên nhận. | Data transfer record, sample validation, contract/decision. |
| **DATA-RET-07:** lưu giữ/xóa theo lịch. | Retention workflow + deletion verification. | Kiểm tra các bản sao, job, archive và ngoại lệ hold. | Job result, inventory, hồ sơ hold và kiểm tra đích. |
| **DATA-REST-08:** dữ liệu trọng yếu phục hồi được. | Backup + independent restore exercises. | Thử restore theo kịch bản, đo RTO/RPO và tính nhất quán. | Restore drill, log, đối soát dữ liệu, issue tracker. |

### Bằng chứng phải có nguồn gốc và giới hạn

Một artifact tốt nên xác định **requirement/control ID, phạm vi tài sản, thời điểm, phiên bản, nguồn, người/công cụ thực hiện, phương pháp, kết quả và giới hạn**. Tuyên bố tự ký “đã bật mã hóa” chỉ là một đầu vào; không thay thế kiểm tra cấu hình và quyền khóa. Test trên staging không mặc nhiên chứng minh production. Báo cáo quét một tuần trước khi có tài khoản mới cần được xét lại.

**Không có phát hiện không đồng nghĩa đã kiểm chứng hết**: cần phân biệt PASS, FAIL, NOT TESTED, NOT APPLICABLE (có lý do), EXCEPTION (được duyệt theo thẩm quyền) và EVIDENCE MISSING. Không được tự chuyển EVIDENCE MISSING thành PASS.

## 15. Tình huống xuyên suốt: chuẩn dữ liệu khách hàng trong SaaS

Một nền tảng quản lý đơn hàng có các tập dữ liệu:

1. **Product catalog công khai:** tên và mô tả sản phẩm.
2. **Customer contact:** email, điện thoại, địa chỉ giao hàng.
3. **Order transaction:** danh sách hàng, trạng thái đơn, tổng tiền.
4. **Payment integration secrets:** bí mật gọi dịch vụ thanh toán.
5. **Analytics export:** bản sao dữ liệu phục vụ phân tích.

### 15.1. Nhận diện dữ liệu và quyết định chuẩn

Data owner phối hợp nhóm ứng dụng và security xác định hậu quả CIA, mục đích, bản sao và luồng dữ liệu. Ví dụ:

| Data asset | Nhãn minh họa | Mối quan tâm chính | Yêu cầu cần kiểm tra |
| --- | --- | --- | --- |
| Product catalog | Public | Integrity và availability. | Chỉ người được phép được sửa/công bố; theo dõi nguồn bản phát hành. |
| Customer contact | Confidential | Confidentiality và integrity. | Tenant/object authorization, giới hạn export, truy vết và retention. |
| Order transaction | Confidential | Integrity và availability; có thông tin nhạy cảm. | Kiểm soát cập nhật trạng thái, audit giao dịch, phục hồi/đối soát. |
| Payment secrets | Restricted | Confidentiality và khả năng giả mạo dịch vụ. | Secret manager, quyền sử dụng, không log, kiểm soát xoay vòng. |
| Analytics export | Phân loại lại có căn cứ | Rủi ro kết hợp/tái nhận diện và chia sẻ. | Giới hạn trường, xử lý định danh, kiểm tra ở đích và quyền truy cập. |

Các nhãn là **giả định của bài học**, không phải kết luận về một sản phẩm thực. Dữ liệu payment card thực tế (nếu có) cần đánh giá phạm vi tiêu chuẩn thanh toán riêng; các bí mật tích hợp không được đồng nhất với dữ liệu thẻ.

### 15.2. Vẽ data flow và ranh giới

~~~mermaid
flowchart LR
    U["Customer / User"] --> API["Order & Customer APIs"]
    API --> DB[("Production Database")]
    API --> MQ[("Event Bus")]
    MQ --> AN["Analytics Transform"]
    AN --> WH[("Analytics Warehouse")]
    API --> EXT["Shipping Partner"]
    DB --> BK[("Managed Backup")]
    SEC["Secret Manager"] --> API
    POL["Data Catalog / Classification"] -. "Rules & review" .-> DB
    POL -. "Rules & review" .-> WH
    POL -. "Rules & review" .-> EXT
~~~

Đường **API → đối tác vận chuyển** cần xác định đúng trường dữ liệu; **event bus → analytics** cần kiểm tra dữ liệu được đưa vào event và biến đổi ở đích; **database → backup** cần kế thừa yêu cầu bảo vệ và khôi phục; **secret manager → API** cần kiểm soát danh tính dịch vụ và đường dùng khóa.

### 15.3. Threat scenario: export dữ liệu vượt mục đích

Nhóm marketing đề xuất tải toàn bộ Customer Contact sang kho phân tích để tính tỷ lệ khách quay lại. Nhưng mục đích này có thể chỉ cần ID giả định danh và thông tin giao dịch tối thiểu.

**Kịch bản rủi ro:** luồng ETL sao chép cả email, địa chỉ, điện thoại và lịch sử mua hàng sang warehouse có quyền rộng, tạo khả năng lộ dữ liệu cá nhân vượt nhu cầu.

**Security requirement:** “Chỉ các trường cần thiết cho mục đích phân tích được chuyển, với biến đổi và kiểm soát quyền đã được phê duyệt; các trường không được phép không xuất hiện trong dataset đích.”

**Controls:** schema allowlist, transformation/masking theo thiết kế đã được duyệt, kiểm tra quyền warehouse, log job, chính sách retention và phê duyệt của Data owner cùng bên chuyên trách khi áp dụng.

### 15.4. Kiểm thử và phát hiện

Nhóm assurance đối chiếu schema nguồn với dataset đích, chạy test với bản ghi synthetic đại diện, kiểm tra tài khoản không có quyền, kiểm tra job logs và kiểm tra quyền export. Kết quả phát hiện: **cột email vẫn xuất hiện do ETL lấy wildcard sau một lần cập nhật schema nguồn**.

Phát hiện này cho thấy yêu cầu **data minimization chưa đạt**. Không thể kết luận “đã mã hóa warehouse nên compliant”; mã hóa at rest không chứng minh dữ liệu được thu thập/xử lý đúng phạm vi.

### 15.5. Khắc phục và xác nhận

Engineering thay truy vấn wildcard bằng allowlist có kiểm soát phiên bản, bổ sung schema contract test, xử lý dữ liệu đã được chuyển trước đó theo quy trình và ghi ảnh hưởng. Data owner xác nhận mục đích/trường cần thiết, platform team điều chỉnh quyền kho dữ liệu và assessor kiểm thử lại trên phiên bản thực tế.

**Evidence sau sửa:** schema diff, test report, đối chiếu dataset đã xử lý, cấu hình quyền và chính sách retention ở warehouse, hồ sơ xử lý bản sao cũ, các giới hạn chưa kiểm tra.

Nếu còn các bản sao ở đối tác hoặc backup chưa được xác minh, kết luận phải **giới hạn phạm vi** và chuyển phần còn lại thành phát hiện hoặc rủi ro cần quyết định theo thẩm quyền.

## 16. Xử lý ngoại lệ và rủi ro còn lại

Đôi khi hệ thống cũ không hỗ trợ đầy đủ tiêu chuẩn, một dữ liệu cần được chia sẻ tạm thời, hoặc có xung đột giữa yêu cầu nghiệp vụ và khả năng kỹ thuật. Cần **quy trình ngoại lệ minh bạch**, không âm thầm bỏ qua.

Một ngoại lệ nên có:

- **Requirement ID và data asset ID** bị ảnh hưởng, môi trường, thời hạn và bên nhận nếu có.
- **Lý do** và nguy cơ khi không áp chuẩn, gồm hậu quả với confidentiality, integrity, availability và nghĩa vụ liên quan.
- **Biện pháp bù đắp**: kiểm soát quyền chặt hơn, giới hạn scope, giám sát tạm, giảm thời gian tồn tại dữ liệu, hoặc kiến trúc thay thế.
- **Owner khắc phục, kế hoạch và deadline**, tiêu chí kết thúc và kiểm tra lại.
- **Data owner, control owner, risk owner** và người có thẩm quyền phê duyệt theo quy trình.
- **Quyết định risk acceptance** có phạm vi, lý do, thời hạn, điều kiện xem lại và bằng chứng.

**Không phải yêu cầu nào cũng có thể được miễn trừ.** Nếu một nghĩa vụ pháp lý hoặc hợp đồng bắt buộc áp dụng, một chữ ký nội bộ không tự tạo quyền bỏ qua. Cần phân biệt **current residual risk** (mức sau controls hiện hành) với **target residual risk** (mục tiêu sau kế hoạch chưa hoàn thành). Kế hoạch khắc phục chưa được kiểm chứng không làm giảm rủi ro hiện tại.

## 17. Quản trị thay đổi và assurance liên tục

Chuẩn theo dữ liệu không phải bảng phân loại được duyệt một lần rồi bỏ quên. Dữ liệu và hệ thống thay đổi liên tục, khiến **claim và evidence có thể hết hiệu lực**.

Các trigger cần thiết:

- Thêm trường dữ liệu nhạy cảm, mở endpoint hoặc tạo data product mới.
- Thay đổi mục đích xử lý, kết hợp dataset, dùng dữ liệu cho AI/analytics hoặc chuyển sang môi trường test.
- Tạo bản sao mới trong cache, warehouse, backup, file export hoặc bên thứ ba.
- Thay IAM, key management, policy-as-code, cấu hình storage hoặc cơ chế logging.
- Thay nhà cung cấp, khu vực lưu trữ, điều khoản hợp đồng hoặc nghĩa vụ áp dụng.
- Phát hiện sai nhãn, công cụ DLP bỏ sót, data leakage, incident hoặc kết quả audit không đạt.
- Owner chuyển vị trí, ngoại lệ hết hạn hoặc quy tắc retention bị thay đổi.

~~~mermaid
flowchart TD
    A["Nhận diện dữ liệu + owner"] --> B["Phân loại, tác động CIA, obligations"]
    B --> C["Security standard + requirements"]
    C --> D["Controls trong design / deployment"]
    D --> E["Test + audit + evidence"]
    E --> F{"Đủ bằng chứng và đạt tiêu chí?"}
    F -- "Không" --> G["Finding + remediation / risk decision"]
    G --> D
    F -- "Có, trong phạm vi" --> H["Ghi kết luận + residual risk"]
    H --> I["Theo dõi thay đổi và reassessment"]
    I --> A
~~~

### Dùng thay đổi để kích hoạt kiểm chứng chọn lọc

Không cần đánh giá lại mọi control khi chỉ sửa giao diện không liên quan. Nhưng nếu thêm một trường cá nhân vào event, cần rà **data classification, event payload, logging, warehouse, retention và bên nhận**. Phạm vi kiểm thử phải phù hợp với **đường dữ liệu bị ảnh hưởng**, không chỉ với file mã nguồn thay đổi.

### Các chỉ số theo dõi hữu ích

| Chỉ số | Giá trị quản trị | Hạn chế |
| --- | --- | --- |
| Tỷ lệ data asset quan trọng có owner và phân loại hiện hành. | Phát hiện tài sản không ai quản trị hoặc metadata cũ. | Nhãn được gán không chứng minh nhãn chính xác. |
| Tỷ lệ bản sao/luồng dữ liệu được đưa vào lineage và baseline. | Phát hiện đường dữ liệu chưa có kiểm soát. | Inventory thiếu sẽ khiến mẫu số sai. |
| Tỷ lệ controls có evidence đúng phiên bản/phạm vi. | Đo khả năng chứng minh yêu cầu. | Nhiều evidence không đồng nghĩa chất lượng cao. |
| Số phát hiện quá hạn, ngoại lệ hết hạn và kết quả retest. | Theo dõi khả năng khắc phục. | Đóng ticket chưa chắc sửa đúng dữ liệu đã chia sẻ. |
| Mức drift giữa chuẩn đã duyệt và cấu hình production. | Phát hiện sai lệch vận hành. | Scanner có thể bỏ sót nghiệp vụ, không chứng minh authorization đầu cuối. |
| Số thay đổi data schema/đối tác chưa được đánh giá impact. | Phát hiện rủi ro mới xuất hiện. | Phụ thuộc khả năng quan sát luồng thay đổi. |

## 18. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Mọi dữ liệu dùng cùng một chuẩn là đơn giản nhất.” | Yêu cầu cần điều chỉnh theo phân loại, tác động CIA, mục đích và nghĩa vụ để tránh thiếu hoặc thừa bảo vệ. |
| “Nhãn Confidential nghĩa là đã mã hóa đúng.” | Nhãn chỉ mô tả yêu cầu; cần kiểm tra mã hóa, quyền khóa và bản sao thực tế. |
| “Dữ liệu Public không cần security control.” | Tính toàn vẹn, nguồn công bố và sẵn sàng có thể rất quan trọng. |
| “Dùng mã hóa thì không cần object-level authorization.” | Mã hóa không ngăn ứng dụng có quyền giải mã trả dữ liệu cho người không có quyền. |
| “Pseudonymized đồng nghĩa đã ẩn danh.” | Dữ liệu vẫn có thể nhận diện lại qua bảng ánh xạ hoặc kết hợp nguồn khác. |
| “Data owner duyệt thì mọi nghĩa vụ đều được miễn.” | Data owner chỉ quyết định trong thẩm quyền; pháp luật, hợp đồng và risk governance vẫn phải được tuân thủ. |
| “Chạy scanner một lần là đủ kiểm tra baseline.” | Cần đối chiếu coverage, release, cấu hình production và theo dõi drift. |
| “Có backup tức là đã đạt yêu cầu availability.” | Phải kiểm thử phục hồi, RTO/RPO và tính nhất quán trong kịch bản phù hợp. |
| “Data đã xóa ở database thì không còn bản sao.” | Cần xét cache, export, warehouse, log, đối tác, backup và quy trình giữ/xóa. |
| “Hợp đồng nhà cung cấp thay thế toàn bộ kiểm chứng.” | Phải xác định shared responsibility, phạm vi evidence của nhà cung cấp và cấu hình do khách hàng quản lý. |
| “Policy-as-code triển khai thành công nghĩa là dữ liệu an toàn.” | Cần kiểm tra luật đúng, inventory đầy đủ, không bypass và có phép test theo nghiệp vụ. |
| “Không có evidence cũng có thể ghi PASS vì chưa thấy incident.” | Thiếu bằng chứng là trạng thái cần xử lý, không phải kết quả kiểm tra đạt. |

## 19. Checklist xây dựng chuẩn theo dữ liệu

1. **Data scope:** những tập dữ liệu, môi trường, bản sao, luồng và đối tác nào nằm trong phạm vi?
2. **Ownership:** mỗi miền dữ liệu có Data owner, steward, system/control owner và đầu mối rủi ro rõ chưa?
3. **Classification:** nhãn được định nghĩa theo hậu quả CIA, có cơ chế kết hợp dữ liệu và review khi thay đổi không?
4. **Requirements:** với mỗi loại/mức dữ liệu có chuẩn truy cập, chia sẻ, mã hóa, logging, backup, retention và xóa đủ cụ thể không?
5. **Applicable obligations:** pháp luật, hợp đồng, ngành và yêu cầu tổ chức có được xác định đúng phạm vi, phiên bản và người tư vấn không?
6. **Data lineage:** các đường đi qua API, queue, ETL, log, cache, warehouse, object storage, backup và bên thứ ba có được tính không?
7. **Controls:** quy tắc được triển khai ở điểm nào, bởi ai; có phần nào chỉ là kế hoạch chưa kiểm chứng?
8. **Verification:** các negative tests, config checks, restore drills, access reviews và event tests có đúng yêu cầu không?
9. **Evidence:** có bản phát hành, thời điểm, nguồn, phương pháp, kết quả, giới hạn và dữ liệu bảo vệ thích hợp không?
10. **Findings/decisions:** sai lệch, ngoại lệ, khắc phục, retest và residual risk có owner, thẩm quyền, thời hạn không?
11. **Continuous review:** thay đổi dữ liệu, mục đích, nhà cung cấp và kiến trúc có tự kích hoạt đánh giá lại phần liên quan không?

## 20. Bài tập tự kiểm tra

### Tình huống A — Bảng giá công khai bị sửa trái phép

Nhóm sản phẩm gán Public cho bảng giá nên không bật audit thay đổi hoặc bảo vệ quyền chỉnh sửa. Một tài khoản bị lộ có thể tăng giá tùy ý.

**Gợi ý:** Nhãn Public chỉ có thể phản ánh yêu cầu về bí mật; **integrity** vẫn có thể cao. Cần chuẩn quyền sửa/công bố, review thay đổi, lịch sử phiên bản, kiểm tra nguồn và cảnh báo sai lệch. Đánh giá tác động nghiệp vụ trước khi chọn baseline.

### Tình huống B — Dữ liệu Confidential bị copy sang staging

Developer tải toàn bộ hồ sơ khách hàng từ production sang staging để test chức năng tìm kiếm; staging có nhiều người dùng và retention không rõ.

**Gợi ý:** Kiểm tra liệu synthetic data có đủ không; nếu cần dữ liệu thật, phải phê duyệt mục đích và phạm vi, giảm thiểu hoặc xử lý định danh thích hợp, kiểm soát quyền staging, retention/xóa và kiểm chứng bản sao. Không tự hạ mức phân loại chỉ vì môi trường không phải production.

### Tình huống C — Scanner báo tất cả object storage đều được mã hóa

Nhóm cloud tuyên bố đã đáp ứng chuẩn bảo vệ Restricted. Tuy nhiên, một service account có quyền đọc mọi bucket và export dữ liệu ra ngoài.

**Gợi ý:** Mã hóa at rest chỉ đáp ứng một phần. Cần test IAM/object-level authorization, quyền export, key usage, logging và tính đúng đắn của data inventory. Báo cáo “encrypted” không chứng minh yêu cầu về phạm vi quyền.

### Tình huống D — Dữ liệu đã pseudonymize được chia sẻ cho đối tác

Đội phân tích thay email bằng ID mới nhưng vẫn giữ ngày sinh, vị trí chi tiết và bảng ánh xạ ở một dịch vụ nội bộ. Đội cho rằng dữ liệu đã ẩn danh hoàn toàn.

**Gợi ý:** Phải phân biệt pseudonymization với anonymization, đánh giá khả năng liên kết/tái nhận diện và nghĩa vụ áp dụng. Cần xem mục đích chia sẻ, quyền nhận, retention, kiểm soát bảng ánh xạ và evidence về phương pháp biến đổi.

### Tình huống E — Đã đổi chuẩn nhưng chưa đánh giá lại

Một API thêm trường thông tin nhạy cảm vào event gửi sang analytics. Tài liệu phân loại vẫn là Internal và CI/CD policy-as-code báo PASS vì chỉ kiểm tra bucket không public.

**Gợi ý:** Phải cập nhật data asset, event schema, lineage, độ nhạy ở đích, mục đích và controls. Test cấu hình bucket không đủ để chứng minh data minimization và authorization. Đây là **khoảng trống coverage** cần đánh giá và khắc phục.

### Tình huống F — Retention và backup mâu thuẫn

Ứng dụng xóa hồ sơ tại database sau thời hạn được duyệt, nhưng snapshot có thể lưu lâu hơn và được phục hồi nguyên trạng. Có thể khẳng định đã xóa hết?

**Gợi ý:** Chưa. Cần phân tích nghĩa vụ, thời hạn lưu backup, quyền restore, xử lý dữ liệu sau phục hồi và khả năng hủy theo thiết kế thực tế. Kết luận assurance phải ghi rõ phạm vi và giới hạn; không tự giả định xóa database là xóa mọi bản sao.

## Kết luận

**Chuẩn theo dữ liệu** làm cho bảo mật phản ánh **giá trị, mục đích, độ nhạy và hậu quả thực tế của từng loại dữ liệu**, thay vì chỉ áp một checklist công nghệ chung. Để chuẩn có giá trị, tổ chức cần data inventory và lineage đầy đủ, ownership rõ, phân loại có căn cứ CIA, yêu cầu kiểm soát đo được, nghĩa vụ đúng phạm vi, controls được triển khai xuyên vòng đời, và **bằng chứng kiểm chứng cả thiết kế lẫn hiệu quả vận hành**. Trong chương trình **SECURITY_SECURITY_ASSURANCE**, mỗi thay đổi dữ liệu hoặc luồng chia sẻ phải có khả năng truy ngược tới requirement, control, test, evidence, phát hiện và residual risk. Chính khả năng truy vết, kiểm tra và đánh giá lại liên tục mới cho phép kết luận một chuẩn bảo mật đã được đáp ứng trong phạm vi nào.
