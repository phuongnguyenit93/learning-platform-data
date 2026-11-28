# Subprocessor: Đánh giá và bảo đảm an toàn cho bên xử lý phụ

Một công ty thuê nền tảng SaaS quản lý khách hàng có thể tưởng rằng dữ liệu chỉ được xử lý bởi nhà cung cấp SaaS đó. Trên thực tế, nhà cung cấp có thể dùng dịch vụ cloud để lưu trữ, nhà cung cấp email để gửi thông báo, đơn vị hỗ trợ để xử lý ticket và dịch vụ phân tích để đo hiệu năng. Nếu các đơn vị đó xử lý **dữ liệu cá nhân thay mặt nhà cung cấp chính**, chúng có thể là **subprocessor** (*bên xử lý phụ*). Việc nhà cung cấp chính có báo cáo kiểm toán tốt không tự động chứng minh tất cả mắt xích xử lý phía sau đều đáp ứng yêu cầu.

Trong chương **Third-party assurance** thuộc module **SECURITY_SECURITY_ASSURANCE**, học về subprocessor là học cách **xác nhận có bằng chứng** rằng chuỗi nhà cung cấp thực hiện xử lý dữ liệu đúng phạm vi, có cơ sở cho phép sử dụng, có biện pháp bảo mật phù hợp, có trách nhiệm hợp đồng và được giám sát xuyên suốt vòng đời. Công việc này liên kết đánh giá rủi ro, các security controls, thẩm định hợp đồng, kiểm thử, audit và khắc phục phát hiện; không dừng ở việc kiểm tra một danh sách tên công ty.

Sau bài học, người học có thể nhận diện đúng vai trò subprocessor, lập bản đồ các luồng dữ liệu và chuỗi xử lý, thiết lập quy trình cho phép/thông báo thay đổi, thẩm định và theo dõi rủi ro, đánh giá chứng cứ kiểm soát bảo mật, phản ứng khi có sự cố và quản lý rút lui/xóa dữ liệu.

## 1. Subprocessor là ai? Phân biệt với các vai trò liên quan

Trong ngữ cảnh bảo vệ dữ liệu cá nhân, **controller** (bên kiểm soát dữ liệu) xác định mục đích và phương tiện thiết yếu của hoạt động xử lý; **processor** (bên xử lý) xử lý dữ liệu cá nhân thay mặt controller theo chỉ dẫn được phép. **Subprocessor** là một bên xử lý khác được processor thuê để thực hiện một phần hoạt động xử lý đó.

~~~mermaid
flowchart LR
    C["Controller: tổ chức quyết định mục đích"] -->|Hợp đồng xử lý dữ liệu / chỉ dẫn| P["Processor: nhà cung cấp chính"]
    P -->|Hợp đồng xử lý phụ / flow-down| S1["Subprocessor A: hạ tầng lưu trữ"]
    P -->|Hợp đồng xử lý phụ / flow-down| S2["Subprocessor B: gửi thông báo"]
    S1 -->|Nếu có ủy quyền và điều kiện phù hợp| S3["Bên xử lý ở tầng tiếp theo"]
    C -.->|Quyền phê duyệt, nhận thông tin, giám sát| S1
    C -.->|Quyền phê duyệt, nhận thông tin, giám sát| S2
~~~

Đây là **sơ đồ trách nhiệm minh họa**, không mặc định controller ký hợp đồng trực tiếp với từng subprocessor. Controller thường có quan hệ hợp đồng với processor chính; processor chính chịu trách nhiệm ràng buộc và quản lý các bên xử lý phụ theo luật và hợp đồng áp dụng.

### 1.1. Vai trò quyết định theo từng hoạt động xử lý

| Vai trò | Đặc điểm | Ví dụ cần đánh giá |
|---|---|---|
| **Controller** | Quyết định vì sao và các phương tiện thiết yếu để xử lý dữ liệu cá nhân. | Doanh nghiệp bán lẻ xác định mục đích lưu thông tin khách hàng để xử lý đơn hàng. |
| **Processor** | Xử lý dữ liệu cá nhân thay mặt controller và theo chỉ dẫn phù hợp. | Dịch vụ CRM vận hành lưu trữ và tác vụ xử lý danh sách khách hàng cho doanh nghiệp. |
| **Subprocessor** | Được processor thuê để thực hiện một phần xử lý thay mặt controller. | Nhà cung cấp hạ tầng mà CRM dùng để lưu bản ghi khách hàng; dịch vụ gửi email theo yêu cầu CRM. |
| **Independent controller** | Tự quyết định mục đích/phương tiện cho hoạt động xử lý của mình. | Một tổ chức khác nhận dữ liệu để cung cấp dịch vụ riêng theo vai trò pháp lý của chính họ. |
| **Joint controllers** | Hai hoặc nhiều bên cùng quyết định mục đích/phương tiện xử lý trong phạm vi liên quan. | Phải phân tích thực chất vai trò và trách nhiệm; không tự gọi là subprocessor chỉ vì có tích hợp kỹ thuật. |
| **Bên thứ ba không xử lý dữ liệu cá nhân** | Cung cấp hàng hóa/dịch vụ nhưng không nhận hoặc xử lý dữ liệu cá nhân trong phạm vi đang xem xét. | Nhà cung cấp phần cứng không có quyền truy cập dữ liệu; vẫn có thể là rủi ro chuỗi cung ứng khác. |

**Nhãn trong hợp đồng không thay thế phân tích hoạt động thực tế.** Cùng một công ty có thể là processor đối với dịch vụ lưu hộ dữ liệu nhưng là controller độc lập đối với một hoạt động khác mà họ tự xác định mục đích. Cần kiểm tra dữ liệu, mục đích, quyền quyết định, chỉ dẫn, cấu hình và hành vi thực tế thay vì chỉ đọc tên vai trò.

### 1.2. Không phải mọi vendor là subprocessor

Để nhận diện, lần lượt hỏi:

1. Có **dữ liệu cá nhân** thuộc hoạt động của controller đi vào/được truy cập bởi bên thứ ba không?
2. Bên thứ ba có thực hiện **xử lý thay mặt processor chính** không (lưu trữ, chuyển tiếp, phân tích, hỗ trợ, xóa, sao lưu...)?
3. Bên thứ ba có tự chọn mục đích độc lập cho dữ liệu trong hoạt động này hay không?
4. Phạm vi xử lý, quyền truy cập, người quyết định và chỉ dẫn được ghi ở tài liệu nào?
5. Có nhiều tầng thuê lại, hỗ trợ từ xa hoặc dịch vụ tự động khác tham gia không?

Ví dụ nhà cung cấp logging chỉ nhận telemetry đã được loại bỏ hoàn toàn dữ liệu cá nhân có thể không thuộc quan hệ subprocessor về dữ liệu cá nhân ở phạm vi đó, nhưng vẫn phải được đánh giá như một nhà cung cấp bảo mật hoặc dữ liệu hạ tầng. Ngược lại, một log chứa địa chỉ IP, user ID hoặc email có thể vẫn là dữ liệu cá nhân tùy bối cảnh; không mặc định rằng “chỉ là metadata” thì nằm ngoài phạm vi.

### 1.3. Phân biệt bên xử lý phụ và tầng nhà cung cấp sâu hơn

Từ **fourth party** đôi khi được dùng trong quản trị rủi ro nhà cung cấp để chỉ bên mà nhà cung cấp trực tiếp thuê. “Fourth party” là cách gọi theo vị trí quan hệ thương mại; **subprocessor** là cách gọi theo vai trò xử lý dữ liệu. Một subprocessor có thể thuê tiếp đơn vị khác; cần theo dõi **chuỗi xử lý nhiều tầng** trong phạm vi hợp đồng và quy định, không dừng ở một cấp bất kể tên gọi.

## 2. Tại sao subprocessor là một chủ đề Security Assurance?

Sự phụ thuộc vào subprocessor tạo ra những rủi ro mà một cuộc đánh giá duy nhất với processor chính có thể không nhìn thấy:

- **Mất kiểm soát luồng dữ liệu:** dữ liệu được chuyển tới vùng, dịch vụ hoặc đơn vị hỗ trợ không nằm trong phạm vi đã được phê duyệt.
- **Đặc quyền gián tiếp:** nhân viên vận hành hoặc tài khoản dịch vụ của bên xử lý phụ có thể truy cập dữ liệu hoặc quyền quản trị có ảnh hưởng rộng.
- **Khoảng trống hợp đồng:** processor cam kết một biện pháp bảo mật nhưng chưa ràng buộc bên xử lý phụ thực hiện nghĩa vụ tương ứng.
- **Thiếu khả năng điều tra:** processor không thu được log, timestamp, nguồn gốc hoặc thông tin đầy đủ khi sự cố xảy ra ở subprocessor.
- **Gián đoạn dây chuyền:** bên xử lý phụ bị lỗi làm processor mất khả dụng; dữ liệu dự phòng hoặc kênh khôi phục có thể phụ thuộc cùng một nhà cung cấp.
- **Chuyển dữ liệu xuyên biên giới:** hoạt động lưu trữ, truy cập từ xa hoặc hỗ trợ quốc tế có thể kích hoạt nghĩa vụ bổ sung theo luật áp dụng.
- **Thiếu minh bạch về thay đổi:** processor thay đơn vị lưu trữ hoặc thêm dịch vụ AI/analytics mà controller không được thông báo theo cơ chế đã cam kết.
- **Rủi ro khi kết thúc dịch vụ:** dữ liệu tồn tại ở bản sao lưu, hệ thống hỗ trợ và các tầng xử lý mà không có kế hoạch hoàn trả/xóa phù hợp.

### 2.1. Mô hình assurance nhiều lớp

~~~text
Mục tiêu bảo mật và quyền dữ liệu của controller
      ↓
Đánh giá rủi ro và yêu cầu đối với processor chính
      ↓
Điều kiện sử dụng subprocessor + hợp đồng chuyển tiếp nghĩa vụ
      ↓
Kiểm soát thực tế của subprocessor và các tầng liên quan
      ↓
Bằng chứng: phạm vi, kỳ đánh giá, ngoại lệ, hoạt động kiểm chứng
      ↓
Theo dõi thay đổi, sự cố, findings, hành động khắc phục
      ↓
Chứng minh kết quả và rủi ro còn lại có người chịu trách nhiệm
~~~

Không thể dựa vào câu “subprocessor đã được vendor phê duyệt” để kết luận **PASS**. Phải biết đã phê duyệt theo tiêu chí nào, khi nào, cho loại dữ liệu/mục đích gì và có bằng chứng cập nhật hay không.

## 3. Lập bản đồ dữ liệu và danh mục Subprocessor

**Inventory** là đầu vào bắt buộc của assurance. Tài liệu phải xác định cả subprocessor đã biết, dịch vụ tích hợp có thể được bật theo cấu hình, sự tham gia của support/vendor operations, và các bên xử lý ở tầng tiếp theo trong phạm vi cần thiết.

### 3.1. Bộ thuộc tính tối thiểu

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| **Processor chính và dịch vụ** | Quan hệ thương mại/hợp đồng nào tạo ra hoạt động xử lý? |
| **Tên pháp nhân subprocessor** | Bên nào thực tế xử lý? Có nhiều công ty thuộc tập đoàn hoặc pháp nhân theo khu vực không? |
| **Mục đích xử lý** | Lưu trữ, vận chuyển, support, email, analytics, backup, monitoring hay chức năng khác? |
| **Loại dữ liệu và chủ thể dữ liệu** | Dữ liệu tài khoản, liên hệ, giao dịch, dữ liệu nhạy cảm, trẻ em hoặc nhóm đối tượng đặc biệt nếu liên quan? |
| **Luồng và hình thức truy cập** | Dữ liệu được truyền đi, lưu trữ, xử lý tại chỗ hay được truy cập từ xa? Có dữ liệu gốc hay chỉ pseudonymized? |
| **Địa điểm** | Khu vực lưu trữ/xử lý, vị trí truy cập từ xa, địa điểm bên hỗ trợ và bên nhận tiếp theo. |
| **Ngày bắt đầu và trạng thái cho phép** | Đã thông báo/được phê duyệt theo cơ chế áp dụng chưa; có hiệu lực từ khi nào? |
| **Contract/DPA và điều khoản liên quan** | Nghĩa vụ bảo mật, xử lý theo chỉ dẫn, thông báo sự cố, hợp tác audit và return/delete được chuyển tiếp thế nào? |
| **Bằng chứng kiểm soát** | Báo cáo kiểm toán, chứng nhận, assessment, bài kiểm tra, finding và hạn khắc phục. |
| **Chủ sở hữu và mức rủi ro** | Ai quản trị quan hệ, theo dõi thay đổi, chấp nhận ngoại lệ và chịu trách nhiệm khi xảy ra sự cố? |
| **Tầng xử lý tiếp theo** | Subprocessor có thuê thêm bên khác cho dữ liệu trong phạm vi không; cơ chế quản lý là gì? |
| **Exit/deletion** | Dữ liệu được hoàn trả/xóa ra sao, bao gồm backup, log hoặc ticket trong giới hạn áp dụng? |

Không nên dùng một cột “vendor approved = yes” cho mọi mục đích. Việc phê duyệt một công ty để gửi email giao dịch không mặc nhiên cho phép dùng dữ liệu đó để huấn luyện mô hình hoặc chia sẻ với một dịch vụ phân tích mới.

### 3.2. Ánh xạ dữ liệu theo nguồn–đích–mục đích

Ví dụ giả định:

~~~mermaid
flowchart TD
    A["Doanh nghiệp bán lẻ (controller)"] -->|Thông tin khách hàng cho chăm sóc| B["CRM SaaS (processor)"]
    B -->|Lưu bản ghi trong vùng được phê duyệt| C["Cloud hosting (subprocessor)"]
    B -->|Gửi email phục vụ ticket| D["Email delivery (subprocessor)"]
    B -.->|Nếu được bật, phải đánh giá lại| E["Analytics add-on mới"]
    C -->|Vận hành/backup theo phạm vi cần rà soát| F["Tầng dịch vụ bổ sung"]
~~~

Từ bản đồ, người đánh giá cần làm rõ: CRM gửi những trường dữ liệu nào cho email delivery; cloud hosting ở đâu; ai có quyền truy cập từ xa; analytics add-on được bật mặc định hay lựa chọn; và nếu CRM thuê đơn vị hỗ trợ ngoài giờ thì đơn vị đó có truy cập ticket chứa dữ liệu khách hàng hay không.

### 3.3. Danh sách công khai và danh mục thực tế có thể khác nhau

Một trang “Subprocessors” do vendor công bố có giá trị khởi đầu, nhưng có thể ghi các đơn vị **có thể** dùng, không nhất thiết tất cả đều xử lý dữ liệu của tenant cụ thể. Ngược lại, một dịch vụ hỗ trợ được kích hoạt theo hợp đồng riêng có thể không hiển thị trên danh sách chung. Assurance cần **đối chiếu** danh sách được công bố, DPA/hợp đồng, cấu hình tenant, sơ đồ luồng dữ liệu, tài liệu sản phẩm, lịch sử thay đổi và xác nhận có bằng chứng từ nhà cung cấp.

Nếu không thể xác minh một mắt xích đang xử lý dữ liệu hay không, ghi **INCONCLUSIVE** cho tiêu chí tương ứng; không tự coi không có vì danh sách thiếu thông tin.

## 4. Nguồn nghĩa vụ: Hợp đồng, quy định và quyền quyết định

Vai trò, quyền và nghĩa vụ cụ thể phụ thuộc luật áp dụng, loại dữ liệu, địa điểm, mục đích, hợp đồng và mô hình dịch vụ. Những điểm dưới đây là nguyên tắc khái quát, không thay thế tư vấn pháp lý cho một giao dịch cụ thể.

### 4.1. Nếu GDPR áp dụng

Đối với hoạt động xử lý thuộc phạm vi **GDPR**, Điều 28 đặt ra những yêu cầu quan trọng về việc processor sử dụng processor khác. Các nguyên tắc thường cần được đối chiếu gồm:

- Processor **không được thuê processor khác** cho hoạt động xử lý liên quan nếu không có **ủy quyền bằng văn bản trước** của controller, theo hình thức cụ thể hoặc chung tùy thỏa thuận.
- Khi dùng **ủy quyền chung bằng văn bản**, processor phải thông tin về các thay đổi dự định liên quan thêm/thay subprocessor, tạo cơ hội để controller phản đối theo cơ chế áp dụng.
- Processor cần ràng buộc subprocessor bằng các nghĩa vụ bảo vệ dữ liệu về cơ bản tương ứng với nghĩa vụ processor phải thực hiện với controller, bao gồm bảo đảm áp dụng biện pháp kỹ thuật và tổ chức phù hợp.
- Nếu subprocessor không thực hiện được nghĩa vụ bảo vệ dữ liệu, **processor ban đầu vẫn chịu trách nhiệm đối với controller** về việc subprocessor thực hiện nghĩa vụ theo Điều 28(4).
- Các điều kiện về chỉ dẫn xử lý, bảo mật, an toàn, hỗ trợ controller, kết thúc dịch vụ và khả năng cung cấp thông tin/audit phải được xử lý trong cấu trúc hợp đồng phù hợp.

**Lưu ý:** quyền phản đối, thời hạn thông báo, xử lý hậu quả khi phản đối và quyền chấm dứt theo cách cụ thể cần đọc điều khoản hợp đồng và quy định áp dụng. Không tự khẳng định mọi controller có quyền phủ quyết tuyệt đối trong mọi trường hợp hoặc mọi hợp đồng đều phải dùng một thời hạn thông báo cố định.

Với các luật bảo vệ dữ liệu khác, khái niệm và yêu cầu có thể khác; phải kiểm tra nghĩa vụ tại các khu vực dữ liệu được thu thập, xử lý hoặc chuyển đến. Một chứng nhận bảo mật không tự bảo đảm tuân thủ tất cả yêu cầu về vai trò, cơ sở pháp lý hoặc chuyển dữ liệu.

### 4.2. Checklist điều khoản hợp đồng/điều khoản xử lý dữ liệu

| Nhóm điều khoản | Câu hỏi assurance | Bằng chứng cần đối chiếu |
|---|---|---|
| **Mục đích và chỉ dẫn** | Có quy định rõ subprocessor chỉ xử lý dữ liệu cần thiết theo hoạt động được cho phép không? | DPA, service description, data flow và cấu hình sử dụng. |
| **Ủy quyền sử dụng** | Hình thức cho phép là cụ thể hay chung; ai phê duyệt; quy trình thay đổi thế nào? | Điều khoản hợp đồng, approval record, thông báo và phản hồi. |
| **Flow-down obligations** | Nghĩa vụ bảo mật, kiểm soát và hỗ trợ có được ràng buộc xuống subprocessor không? | Cam kết hợp đồng, bản tóm tắt điều khoản tương ứng, legal attestation phù hợp. |
| **Security measures** | Có baseline an ninh tương xứng với dữ liệu/rủi ro và quyền audit phù hợp? | Security schedule, assessment, control evidence, findings. |
| **Incident assistance** | Bên xử lý phụ phải báo cho processor khi nào, cung cấp dữ kiện gì và hỗ trợ điều tra/ứng phó ra sao? | Incident clause, contact path, thử quy trình và cam kết SLA nếu có. |
| **International transfer** | Có phân loại đường chuyển quốc tế và cơ chế hợp pháp áp dụng không? | Đánh giá chuyển dữ liệu, phụ lục/biện pháp bổ sung khi cần. |
| **Return/delete** | Kết thúc hợp đồng có hoàn trả/xóa dữ liệu và quản trị bản sao theo điều kiện áp dụng? | Điều khoản xóa, lộ trình dữ liệu, chứng cứ xác nhận và ngoại lệ pháp lý. |
| **Audit/transparency** | Controller/processor có thể nhận thông tin cần thiết để chứng minh kiểm soát không? | Báo cáo audit, phạm vi quyền đánh giá, thông tin sẵn có và hạn chế. |
| **Liability và remedies** | Trách nhiệm và phương án khắc phục khi vi phạm đã được pháp lý/kinh doanh xem xét? | Điều khoản trách nhiệm, cơ chế xử lý tranh chấp và chấm dứt. |

Không nhất thiết controller được đọc nguyên văn mọi hợp đồng thương mại giữa processor và subprocessor; có thể dùng thông tin, xác nhận, mẫu điều khoản, báo cáo assurance hoặc quyền audit được thỏa thuận. Nhưng **không tiếp cận được hợp đồng** không cho phép người đánh giá suy đoán rằng mọi nghĩa vụ đã được chuyển tiếp đầy đủ.

## 5. Quy trình cho phép và thay đổi Subprocessor

Subprocessor có thể được bổ sung khi nhà cung cấp đổi hạ tầng, mở tính năng, thêm công ty hỗ trợ hoặc thuê đơn vị khác. **Change management** là trọng tâm của assurance liên tục.

~~~mermaid
flowchart TD
    A["Processor đề xuất thêm hoặc thay subprocessor"] --> B["Thông tin: pháp nhân, mục đích, dữ liệu, nơi xử lý, ngày dự kiến"]
    B --> C["Đối chiếu hợp đồng và phạm vi ủy quyền"]
    C --> D["Đánh giá rủi ro và yêu cầu kiểm soát"]
    D --> E{"Đủ bằng chứng và đúng cơ chế cho phép?"}
    E -->|Không| F["Yêu cầu bổ sung / phản đối / dừng theo quyền áp dụng"]
    F --> G["Đánh giá lại hoặc xác định phương án thay thế"]
    G --> C
    E -->|Có| H["Phê duyệt hoặc ghi nhận kết quả theo quy trình"]
    H --> I["Cập nhật inventory, DPA/record và trạng thái thực thi"]
    I --> J["Giám sát, kiểm thử và xem xét định kỳ"]
    J --> A
~~~

### 5.1. Dữ liệu cần có trong thông báo thay đổi

Một thông báo hữu ích cần nêu danh tính pháp nhân, dịch vụ, mục đích và tính năng liên quan, loại dữ liệu và chủ thể dữ liệu bị ảnh hưởng, địa điểm xử lý/lưu trữ/truy cập từ xa, tầng xử lý tiếp theo khi liên quan, ngày dự kiến sử dụng, biện pháp kiểm soát và sự khác biệt so với danh sách cũ.

**Một email chỉ ghi “chúng tôi đã cập nhật danh sách subprocessor” có thể không đủ** nếu không thể xác định thay đổi thực tế và tác động đến tenant của tổ chức.

### 5.2. Phân nhánh theo hình thức ủy quyền

- **Ủy quyền cụ thể:** xác minh bên xử lý phụ/hoạt động xử lý được controller cho phép bằng văn bản trước khi sử dụng theo cơ chế áp dụng.
- **Ủy quyền chung:** xác minh thay đổi dự kiến được thông báo theo điều kiện hợp đồng/luật áp dụng và controller có cơ hội thực hiện quyền phản đối; lưu bằng chứng ngày nhận, nội dung, phản hồi, thời hạn và quyết định.
- **Thay đổi ngoài phạm vi đã cho phép:** cần đánh giá lại hoặc giải quyết theo hợp đồng trước khi mở quyền truy cập dữ liệu mới.
- **Chưa đủ thông tin:** không mặc định đồng ý về mặt assurance; ghi khoảng trống, yêu cầu bổ sung và áp dụng giới hạn theo mức rủi ro.

### 5.3. Tránh “phê duyệt bằng im lặng” không được kiểm soát

Dù thỏa thuận cho phép cơ chế thông báo và phản hồi trong một khoảng thời gian, tổ chức vẫn cần quy trình **nhận thông báo, phân công người xem, theo dõi deadline, đánh giá rủi ro và lưu quyết định**. Hộp thư không ai quản lý hoặc trang web không được theo dõi có thể khiến một thay đổi có tác động lớn bị bỏ sót.

Giao diện có nút “Accept” không tự chứng minh người bấm có đúng thẩm quyền chấp nhận rủi ro. Lưu record gồm người phê duyệt, phạm vi, rủi ro, bằng chứng, điều kiện/ngoại lệ và thời điểm hiệu lực.

## 6. Thẩm định Subprocessor theo rủi ro

Không phải mọi subprocessor cần cùng mức đánh giá. Một đơn vị chỉ xử lý pseudonymous event đã được giới hạn có thể khác với nhà cung cấp lưu toàn bộ dữ liệu nhận diện khách hàng, có quyền quản trị, xử lý nhiều quốc gia và là điểm lỗi duy nhất của dịch vụ trọng yếu.

### 6.1. Những tiêu chí ưu tiên

| Yếu tố rủi ro | Cần đánh giá |
|---|---|
| **Độ nhạy cảm dữ liệu** | Dữ liệu cá nhân gì, quy mô bao nhiêu, có thể gây thiệt hại gì khi lộ/sửa/mất? |
| **Quyền truy cập** | Subprocessor có khả năng đọc plaintext, giải mã, export hoặc thực hiện hành động đặc quyền không? |
| **Khối lượng và tần suất** | Dữ liệu liên tục, batch định kỳ, chỉ khi support hay khi bật tính năng? |
| **Vị trí và luồng chuyển** | Lưu ở đâu, ai có thể truy cập từ xa, các luật/giới hạn địa lý nào có thể áp dụng? |
| **Tính thiết yếu** | Dịch vụ chính có dừng nếu subprocessor lỗi không; có phương án thay thế không? |
| **Phụ thuộc chung** | Nhiều processor sử dụng cùng hạ tầng hoặc cùng key/identity provider không? |
| **Bề mặt tấn công** | API, quyền quản trị, tích hợp webhook, agent, token hay pipeline nào được cấp? |
| **Lịch sử và maturity** | Incident, findings, ngoại lệ kiểm toán, kết quả khắc phục và khả năng hỗ trợ. |
| **Độ minh bạch** | Có thể cung cấp danh sách, scope, control evidence, thông báo thay đổi và hỗ trợ điều tra không? |
| **Khả năng exit** | Trả/xóa dữ liệu, thay thế nhà cung cấp, chuyển đổi workload và quyền truy cập ra sao? |

### 6.2. Một ví dụ đánh giá phân tầng

- **Rủi ro cao:** lưu dữ liệu khách hàng ở quy mô lớn; có khả năng truy cập rõ dạng; hỗ trợ xuyên biên giới; ảnh hưởng tới nghiệp vụ trọng yếu. Yêu cầu due diligence sâu, đánh giá nghĩa vụ pháp lý và control evidence, phê duyệt bởi các vai trò phù hợp, giám sát chặt và thử điều kiện exit.
- **Rủi ro trung bình:** xử lý một tập dữ liệu hạn chế và chịu ảnh hưởng vận hành có thể thay thế được. Cần xác nhận cơ chế cho phép, kiểm soát an ninh thiết yếu, thông tin xử lý và chu kỳ review tương xứng.
- **Rủi ro thấp theo phạm vi đã chứng minh:** dữ liệu đã được tối thiểu hóa, quyền hạn hẹp, xử lý không trọng yếu. Có thể dùng chứng cứ tiêu chuẩn và review định kỳ phù hợp, nhưng **không bỏ** yêu cầu ủy quyền/hợp đồng khi luật áp dụng vẫn đòi hỏi.

Các nhãn rủi ro ở đây là ví dụ. Quyết định phải gắn với ngưỡng nội bộ và kết quả có bằng chứng; không chỉ dựa vào số lượng chứng nhận.

## 7. Kiểm soát kỹ thuật và tổ chức cần xem xét

Đây là bộ control mẫu để đánh giá subprocessor trong phạm vi xử lý thực tế. Không phải mọi biện pháp đều thích hợp với mọi dịch vụ, nhưng mọi ngoại lệ quan trọng cần được giải thích.

| Nhóm kiểm soát | Câu hỏi thực tế | Bằng chứng tiềm năng |
|---|---|---|
| **Identity & access** | Có quyền tối thiểu, MFA/SSO cho quản trị, joiner–mover–leaver, access review, giới hạn hỗ trợ tạm thời? | Chính sách IAM, role matrix, kết quả access review, record truy cập hỗ trợ. |
| **Data minimization** | Chỉ chuyển các trường cần thiết cho mục đích được phê duyệt? | API payload schema đã ẩn dữ liệu nhạy cảm, DFD, cấu hình export/field mapping. |
| **Encryption & key management** | Dữ liệu được bảo vệ khi truyền/lưu; ai kiểm soát khóa và có thể giải mã? | TLS/config, encryption design, KMS policy, key rotation và scope. |
| **Segregation** | Dữ liệu của các controller/tenant được cô lập logic hoặc vật lý phù hợp? | Kiến trúc đa tenant, kiểm thử phân quyền, audit scope và kết quả đánh giá. |
| **Logging & monitoring** | Hành động quản trị, truy cập dữ liệu và thay đổi cấu hình quan trọng có thể truy vết? | Log sample an toàn, chính sách retention, cảnh báo và kiểm thử pipeline. |
| **Vulnerability management** | Có cơ chế theo dõi bản vá, kiểm soát cấu hình, phát hiện và khắc phục lỗ hổng? | Chính sách, đánh giá độc lập, finding sample, thời gian khắc phục đã kiểm tra. |
| **Secure development** | Quy trình thay đổi, bảo vệ CI/CD, dependency, review và kiểm thử bảo mật phù hợp? | SDLC policy, chứng cứ build/release, kiểm soát truy cập repo, review mẫu. |
| **Incident response** | Có kênh báo sự cố, escalation, thông tin cung cấp và thời hạn theo hợp đồng? | IR plan, contact list, tabletop report, mẫu thông báo và ticket thử. |
| **BC/DR** | Có backup, redundancy, recovery/restore test và kế hoạch khi phụ thuộc khác lỗi? | BIA, RTO/RPO theo thỏa thuận, kết quả DR test, exceptions. |
| **Privacy governance** | Có ghi mục đích, hạn lưu, xóa/hoàn trả, hỗ trợ yêu cầu chủ thể dữ liệu và thay đổi subprocessor? | DPA, retention schedule, deletion process, policy và evidence thử. |
| **Supplier chain** | Subprocessor có cơ chế kiểm soát các bên mà họ thuê lại? | Supplier policy, danh mục phụ thuộc, cơ chế flow-down và notification. |

**Các bảo vệ không thể thay thế lẫn nhau.** Mã hóa at rest không giúp giữ bí mật nếu tài khoản support được phép giải mã đã bị chiếm. Audit report sạch không thay thế khả năng thu hồi quyền khi nhân viên rời công ty. Một RTO thấp không chứng minh nguồn phục hồi không chứa dữ liệu sai.

### 7.1. Kiểm soát hỗ trợ từ xa và truy cập đặc quyền

Một nhà cung cấp có thể cam kết dữ liệu được lưu trong vùng A nhưng đội hỗ trợ ở vùng khác có quyền đọc log, ticket hoặc dữ liệu sản xuất. Assurance cần tách ba trục: **nơi lưu**, **nơi xử lý/truy cập** và **ai có quyền**. Kiểm tra yêu cầu phân quyền và giới hạn dữ liệu thực tế, có cơ chế phê duyệt theo ca, audit, redaction và thu hồi quyền hỗ trợ.

### 7.2. Kiểm soát bản sao, log và dữ liệu phát sinh

Dữ liệu có thể xuất hiện trong backup, telemetry, log debug, hệ thống tìm kiếm, queue, ticket hỗ trợ hoặc kho đối soát. Nếu chỉ kiểm tra primary database, có thể bỏ các bản sao ngoài phạm vi. Cần xác định dữ liệu nào là **derived data** có thể liên kết trở lại cá nhân, mục đích xử lý và thời hạn lưu của từng kho.

## 8. Đánh giá chứng cứ: Báo cáo, chứng nhận và kiểm thử

Bên xử lý phụ không nhất thiết cho phép khách hàng cuối kiểm tra trực tiếp toàn bộ hệ thống. Mức assurance thường là tổ hợp các nguồn:

- **Tài liệu hợp đồng:** DPA, security schedule, mô tả xử lý, danh sách subprocessor, điều khoản audit/incident/deletion.
- **Chứng nhận và báo cáo độc lập:** ví dụ phạm vi chứng nhận ISO/IEC 27001 hoặc báo cáo SOC 2 khi thực sự phù hợp.
- **Câu trả lời thẩm định:** phương pháp vận hành control, bằng chứng được phép chia sẻ, hạn chế và người xác nhận.
- **Bằng chứng vận hành:** access review, audit configuration, vulnerability remediation, BC/DR test, incident drill và kết quả xử lý finding.
- **Kiểm tra của processor chính:** cách processor đánh giá, lựa chọn, ký hợp đồng, giám sát và phát hiện thay đổi đối với subprocessor.
- **Kiểm thử của controller trong phần mình được phép:** kiểm tra cấu hình tenant, quyền tích hợp, synthetic event, log export hoặc thử quy trình hỗ trợ với dữ liệu giả.

### 8.1. Đọc báo cáo đúng phạm vi

Một chứng nhận hoặc báo cáo không thể được dùng như một con dấu “an toàn cho mọi trường hợp”. Người đánh giá cần xác định:

1. **Tên pháp nhân/đơn vị và dịch vụ** trong báo cáo có đúng bên xử lý dữ liệu không?
2. **Phạm vi hệ thống, khu vực và các control** có bao phủ dịch vụ/tính năng liên quan không?
3. **Thời kỳ đánh giá và ngày hiệu lực** có phù hợp với thời điểm ra quyết định không?
4. Có **ngoại lệ, ý kiến hạn chế, phát hiện hoặc phần loại trừ** nào liên quan đến rủi ro này không?
5. Nếu có **subservice organizations**, báo cáo đã bao gồm chúng hay loại trừ; ai chịu trách nhiệm kiểm tra phần bị loại trừ?
6. Có **customer/user entity controls** hoặc shared responsibility yêu cầu controller/processor chính phải tự thực hiện không?
7. Đã có thay đổi lớn, incident hoặc phạm vi mới kể từ kỳ đánh giá cần cập nhật bằng chứng chưa?

Ví dụ **SOC 2 Type 2** có thể cung cấp thông tin về thiết kế và hoạt động của control trong một kỳ được kiểm toán, nhưng không tự bảo đảm dữ liệu của tenant cụ thể đã được cấu hình đúng hoặc tất cả subprocessor bên dưới đều nằm trong phạm vi. **ISO/IEC 27001** xác nhận hệ thống quản lý an toàn thông tin theo phạm vi chứng nhận, không phải chứng nhận rằng mọi luồng dữ liệu và nghĩa vụ quyền riêng tư được đáp ứng tuyệt đối.

### 8.2. Không kiểm thử ngoài phạm vi được phép

Assurance có thể yêu cầu bằng chứng từ nhà cung cấp, nhưng không mặc định có quyền quét mạng, pentest, truy cập log người dùng khác hoặc chạy payload trên hạ tầng của subprocessor. Các kiểm tra kỹ thuật phải có **phạm vi, quyền và biện pháp bảo vệ dữ liệu được phê duyệt**. Khi không có quyền kiểm thử, dùng bằng chứng độc lập hoặc đánh giá gián tiếp phù hợp; ghi rõ mức tin cậy và giới hạn.

## 9. Luồng dữ liệu xuyên biên giới và nơi lưu trữ

Một subprocessor có thể tác động đến nghĩa vụ chuyển dữ liệu cá nhân qua biên giới ngay cả khi hạ tầng ứng dụng của controller vẫn đặt ở một quốc gia. Cần phân tích **dòng dữ liệu thực tế**: transfer API, backup, replication, log, support access, system administration và cả trường hợp bên xử lý phụ ở nhiều khu vực.

### 9.1. Những câu hỏi quan trọng

- Dữ liệu phát sinh ở đâu và bên nào kiểm soát hoạt động xử lý?
- Có **chuyển hoặc truy cập từ quốc gia/vùng pháp lý khác** theo định nghĩa của luật áp dụng không?
- Loại dữ liệu, chủ thể dữ liệu và mức nhạy cảm nào nằm trong luồng đó?
- Ai là bên gửi/nhận dữ liệu, trong vai trò controller/processor/subprocessor nào?
- Cơ chế chuyển dữ liệu hợp pháp cần áp dụng là gì (ví dụ quyết định adequacy, điều khoản hợp đồng mẫu hoặc cơ chế khác, **nếu luật áp dụng yêu cầu**)? Có cần đánh giá/bảo vệ bổ sung không?
- Biện pháp mã hóa, quyền quản trị, quản lý khóa và truy cập của nhân sự ở các vị trí khác nhau có phù hợp không?
- Luồng dữ liệu có thể thay đổi khi vendor bổ sung region, đội hỗ trợ hoặc dịch vụ mới không?

Không được tuyên bố rằng chọn một **data residency region** là đã giải quyết mọi nghĩa vụ: nơi lưu dữ liệu và nơi được phép truy cập/xử lý có thể khác nhau. Ngược lại, cũng không tự suy luận mọi kết nối quốc tế đều là chuyển dữ liệu bị cấm; cần xác định luật và điều kiện thực tế.

### 9.2. Phân biệt cơ sở pháp lý và control bảo mật

Mã hóa/TLS làm giảm rủi ro bảo mật trên đường truyền, nhưng **không tự tạo cơ chế pháp lý hợp lệ** cho transfer. Ngược lại, có giấy tờ chuyển dữ liệu hợp lệ không chứng minh hệ thống đã giới hạn quyền hoặc mã hóa đúng. Assessment nên ghi riêng **legal/contractual outcome** và **technical security outcome** để tránh dùng một kết quả thay thế cho kết quả khác.

## 10. Quy trình assurance từ onboarding đến offboarding

~~~mermaid
flowchart TD
    A["Nhận diện subprocessor và dữ liệu xử lý"] --> B["Lập inventory, purpose, data flow, địa điểm"]
    B --> C["Đánh giá pháp lý/hợp đồng và rủi ro"]
    C --> D["Thẩm định controls và bằng chứng"]
    D --> E{"Đủ điều kiện sử dụng?"}
    E -->|Chưa| F["Bổ sung bằng chứng, giảm phạm vi hoặc tìm phương án khác"]
    F --> C
    E -->|Có| G["Phê duyệt/ghi nhận ủy quyền đúng cơ chế"]
    G --> H["Cấp truy cập tối thiểu, cập nhật sơ đồ và kiểm tra vận hành"]
    H --> I["Giám sát thay đổi, chứng cứ, sự cố và findings"]
    I --> J{"Có thay đổi hoặc hết hợp đồng?"}
    J -->|Thay đổi| C
    J -->|Exit| K["Thu hồi quyền, hoàn trả/xóa dữ liệu, kiểm chứng"]
    K --> L["Đóng hồ sơ và ghi rủi ro còn lại"]
~~~

### Bước 1 — Xác định applicability

Nhận mô tả từ processor chính, đối chiếu luồng dữ liệu và vai trò. Không đánh giá mọi vendor giống nhau: nếu không phải subprocessor, vẫn có thể yêu cầu đánh giá rủi ro third-party khác, nhưng ghi nhận phân loại chính xác.

### Bước 2 — Bảo đảm phạm vi ủy quyền và điều khoản hợp đồng

Xem các yêu cầu pháp lý/hợp đồng áp dụng, kiểu ủy quyền, danh mục được phép, cách thông báo và phản đối. Lưu decision record theo người, thời điểm, phạm vi, điều kiện và bản hợp đồng hiệu lực.

### Bước 3 — Thẩm định rủi ro và security controls

Chọn mức sâu của đánh giá theo loại dữ liệu, quyền, quốc gia, tác động nghiệp vụ và mối phụ thuộc. So sánh bằng chứng với baseline đã phê duyệt, phân loại findings, điều kiện bù trừ và quyết định rủi ro còn lại.

### Bước 4 — Kích hoạt tích hợp có kiểm soát

Cấu hình data minimization, API scopes, IAM, keys, lưu lượng, audit, retention và quyền support. Với chức năng tùy chọn, cần xác định rõ khi nào dữ liệu thực sự được chia sẻ; không mở mặc định một tính năng chưa phê duyệt chỉ vì vendor mới cung cấp.

### Bước 5 — Theo dõi liên tục

Đối chiếu định kỳ danh sách subprocessor với inventory, thông báo thay đổi, chứng cứ audit mới, sự cố, SLA và tình trạng khắc phục. Kiểm tra cả **khả năng phát hiện khi vendor ngừng cung cấp thông tin**, không chỉ khi vendor chủ động báo lỗi.

### Bước 6 — Xử lý thay đổi, thay thế và exit

Đánh giá lại khi subprocessor đổi công ty, thay quyền hỗ trợ, mở region, bật analytics/AI hoặc phân chia trách nhiệm cho đơn vị khác. Khi chấm dứt, kiểm chứng xóa/hoàn trả dữ liệu, quyền truy cập, backup và các bản sao trong giới hạn hợp đồng/pháp luật.

## 11. Sự cố bảo mật trong chuỗi Subprocessor

Một sự cố tại subprocessor có thể bắt đầu ở tầng thấp nhất nhưng ảnh hưởng trực tiếp tới controller. Chuỗi thông tin cần rõ ràng, có đường liên lạc dự phòng và nghĩa vụ hỗ trợ điều tra.

~~~text
Subprocessor phát hiện sự cố
  -> Thông báo cho processor chính theo hợp đồng và nghĩa vụ áp dụng
  -> Processor đánh giá, cô lập và thông tin cho controller khi cần
  -> Controller đánh giá tác động, nghĩa vụ báo cáo/thông báo và biện pháp bảo vệ
  -> Các bên phối hợp điều tra, phục hồi, bằng chứng và khắc phục
~~~

### 11.1. Nội dung thông báo hữu ích

| Thông tin | Vì sao cần |
|---|---|
| Thời điểm phát hiện, mốc bắt đầu nghi ngờ và cập nhật gần nhất | Hỗ trợ timeline và xác định thời hạn áp dụng. |
| Dịch vụ, tenant, subprocessor, hệ thống, vùng bị ảnh hưởng | Khoanh phạm vi và chuỗi trách nhiệm. |
| Loại dữ liệu/chủ thể dữ liệu và số lượng ước tính với mức tin cậy | Đánh giá tác động và nghĩa vụ quyền riêng tư. |
| Bản chất sự cố: truy cập trái phép, mất, sửa, rò rỉ hoặc gián đoạn | Xác định CIA impact và hành động cần ưu tiên. |
| Biện pháp containment, khắc phục và bằng chứng hiện có | Đánh giá đường tấn công còn hoạt động và khả năng lan rộng. |
| Người liên lạc, lịch cập nhật và hỗ trợ điều tra | Điều phối đúng nhóm và bảo toàn chứng cứ. |
| Những điều chưa biết và kế hoạch xác minh tiếp | Tránh trình bày giả thuyết như kết luận. |

**Thời hạn thông báo phụ thuộc luật và hợp đồng áp dụng.** Không được áp một mốc cố định cho tất cả các tầng vendor. Ví dụ, khi GDPR áp dụng, processor có nghĩa vụ thông báo cho controller **không chậm trễ không cần thiết** sau khi biết xảy ra vi phạm dữ liệu cá nhân theo Điều 33(2); nghĩa vụ và mốc thông báo cho cơ quan giám sát của controller cần được phân biệt. Điều khoản với subprocessor nên hỗ trợ processor và controller đáp ứng đúng thời hạn của mình, không đợi đủ mọi chi tiết điều tra mới có thông báo ban đầu khi quy trình yêu cầu.

### 11.2. Kịch bản có thể ảnh hưởng nhiều bên

Nếu hạ tầng của subprocessor bị tấn công, nhiều processor khác nhau có thể cùng bị tác động. Controller cần xác định dữ liệu của mình có nằm trong phần bị ảnh hưởng, đường truyền hoặc backup bị lộ không, biện pháp tạm thời có khả thi và có phải tạm dừng một tích hợp để bảo vệ dữ liệu không. Không mặc định “nhà cung cấp có sự cố” đồng nghĩa mọi dữ liệu của khách hàng bị lộ; cũng không tuyên bố an toàn khi thiếu bằng chứng phân loại tenant.

## 12. Theo dõi, đo lường và xử lý findings

Một chương trình assurance cần chỉ số phản ánh **khả năng kiểm chứng thực tế**, không chỉ số lượng vendor đã điền biểu mẫu.

| Chỉ số | Cách đo / ý nghĩa | Giới hạn |
|---|---|---|
| **Subprocessor inventory coverage** | Số subprocessor đã xác minh đang tham gia xử lý / số subprocessor thuộc phạm vi đã đối chiếu. | Mẫu số có thể chưa đầy đủ nếu chuỗi ẩn hoặc thiếu thông tin vendor. |
| **Authorization coverage** | Tỷ lệ hoạt động xử lý có bằng chứng cho phép/thông báo hợp lệ theo cơ chế áp dụng. | Không đồng nghĩa mọi control an ninh đã đạt. |
| **Data-flow completeness** | Tỷ lệ luồng/nhóm dữ liệu bắt buộc có điểm nguồn, đích, mục đích và địa điểm được xác nhận. | Phải có kiểm tra support access, log và backup. |
| **Evidence freshness** | Tuổi của control evidence so với chu kỳ đánh giá rủi ro. | Chứng nhận còn hạn nhưng dịch vụ vừa đổi có thể vẫn thiếu bằng chứng. |
| **Critical findings overdue** | Số findings rủi ro cao quá thời hạn, mức ảnh hưởng và owner. | Không chỉ đếm; cần đánh giá tác động thực tế. |
| **Change notification effectiveness** | Tỷ lệ thay đổi được xử lý đúng quy trình và thời hạn theo hợp đồng. | Cần biết những thay đổi đã diễn ra nhưng chưa được báo. |
| **Incident notification readiness** | Khả năng liên lạc, nhận đủ dữ kiện và phối hợp xử lý trong diễn tập. | Thử contact tree không tương đương điều tra thật. |
| **Exit/deletion assurance** | Tỷ lệ lần exit có bằng chứng thu hồi quyền, xử lý dữ liệu và ngoại lệ backup. | Giấy xác nhận xóa chung chung có thể không đủ cho từng loại bản sao. |

Ví dụ: danh mục xác định 20 hoạt động xử lý phụ cần đánh giá. Trong đó 16 hoạt động có danh sách subprocessor, phạm vi và bằng chứng cho phép đã xác minh; 2 thiếu thông tin địa điểm hỗ trợ, 1 chưa có bằng chứng flow-down và 1 bị phát hiện chia sẻ dữ liệu ngoài mục đích đã duyệt. Không được công bố “80% vendor an toàn” chỉ từ 16/20; cần báo **16/20 đã có dữ liệu cho phép/phạm vi đủ theo tiêu chí**, đồng thời phân loại chính xác các phát hiện còn lại.

### 12.1. Quản lý ngoại lệ

Một exception register nên có: processor/subprocessor, dữ liệu, mục đích, lý do chưa đáp ứng, đánh giá rủi ro, biện pháp bù trừ, chủ sở hữu, người phê duyệt, thời hạn, điều kiện hủy và mốc retest. Một ngoại lệ nghiệp vụ được phê duyệt **không tự biến kết quả kỹ thuật hoặc pháp lý FAIL thành PASS**.

Nếu hoạt động xử lý không thể tiếp tục hợp lệ vì thiếu điều kiện bắt buộc, chấp nhận rủi ro nội bộ không nhất thiết có khả năng thay thế nghĩa vụ luật. Phải phối hợp bộ phận pháp lý/quyền riêng tư để quyết định dừng, thay đổi luồng dữ liệu hoặc khắc phục hợp lệ.

## 13. Kết thúc quan hệ: Offboarding, Return và Deletion

Khi đổi subprocessor hoặc kết thúc hợp đồng, rủi ro còn tồn tại ở dữ liệu và quyền truy cập chưa được thu hồi.

### 13.1. Kế hoạch exit cần bao phủ

1. **Scope:** loại dữ liệu, backup, log, support tickets, bản sao, derived data và các tầng xử lý có liên quan.
2. **Return/export:** phương thức xuất dữ liệu, định dạng, khả năng kiểm tra tính đầy đủ, mã hóa đường truyền và người nhận hợp lệ.
3. **Cutover:** thời điểm ngừng chia sẻ dữ liệu mới, tắt connector, thu hồi token, service accounts, webhook, network allowlist và quyền support.
4. **Deletion:** yêu cầu xóa phù hợp hợp đồng/pháp luật, gồm vòng đời backup và các ngoại lệ bắt buộc giữ theo luật nếu có.
5. **Evidence:** xác nhận xóa/hoàn trả với phạm vi, ngày và nguồn phù hợp; kết quả kiểm tra cấu hình của controller/processor.
6. **Residual risk:** dữ liệu còn lưu theo nghĩa vụ pháp lý, thời hạn hết backup, quyền giám sát còn lại và đầu mối xử lý.

### 13.2. Phân biệt delete live data với hết toàn bộ bản sao

Một vendor có thể xóa dữ liệu sản xuất ngay nhưng bản backup không thể sửa từng bản ghi, được xóa theo chu kỳ. Không tuyên bố “đã xóa tuyệt đối mọi bản sao” nếu chưa có bằng chứng. Phải ghi chu kỳ lưu backup, cơ chế cô lập bản sao, điều kiện khôi phục, việc áp dụng yêu cầu xóa sau restore, thời điểm dự kiến hết hạn và căn cứ giữ dữ liệu còn lại.

**Trả dữ liệu** cũng phải có kết quả kiểm tra được: số bản ghi, schema, tính đầy đủ, khả năng giải mã, dữ liệu liên kết và cơ chế thông báo các phần không thể xuất. Một file export có tồn tại không đồng nghĩa migration đã thành công.

## 14. Thiết kế hồ sơ bằng chứng Subprocessor

Có thể dùng một control register gắn rủi ro, mục tiêu và kết quả thẩm định.

| Control ID minh họa | Mục tiêu | Tiêu chí đạt và evidence |
|---|---|---|
| **TP-SUB-01** | Xác định đầy đủ subprocessor và hoạt động xử lý. | Inventory pháp nhân, data flow, purpose, địa điểm, tenant applicability và review. |
| **TP-SUB-02** | Mỗi hoạt động có cơ chế cho phép sử dụng đúng yêu cầu. | DPA, authorization, change notice, phản hồi, ngày hiệu lực và approver. |
| **TP-SUB-03** | Nghĩa vụ xử lý/bảo mật được chuyển tiếp phù hợp. | Contract mapping, xác nhận flow-down, scope và phần không được kiểm tra. |
| **TP-SUB-04** | Rủi ro và controls kỹ thuật được đánh giá theo dữ liệu thực tế. | Risk assessment, evidence phạm vi phù hợp, findings và kết quả khắc phục. |
| **TP-SUB-05** | Luồng chuyển dữ liệu quốc tế đáp ứng điều kiện áp dụng. | Legal transfer mapping, cơ chế/đánh giá và biện pháp kỹ thuật khi cần. |
| **TP-SUB-06** | Thay đổi được phát hiện và đánh giá trước khi tác động. | Monitoring nguồn thông báo, change ticket, đánh giá khác biệt và quyết định. |
| **TP-SUB-07** | Chuỗi vendor hỗ trợ ứng phó sự cố đúng thời hạn áp dụng. | Contact/incident clauses, bài thử thông báo, timeline và dữ liệu điều tra. |
| **TP-SUB-08** | Exit không để lại quyền hoặc dữ liệu ngoài phạm vi cho phép. | Revoke token, tắt connector, export/delete evidence, backup retention exception. |
| **TP-SUB-09** | Những điểm không đạt được theo dõi liên tục. | Exception/finding register, owner, due date, status, retest và báo cáo. |

**Cách kết luận:** `PASS` khi có bằng chứng đủ mới và đúng phạm vi chứng minh đạt tiêu chí; `FAIL` khi có bằng chứng không đạt; `INCONCLUSIVE` khi thiếu dữ liệu hoặc phạm vi không rõ; `NOT_APPLICABLE` khi kiểm soát thực sự không áp dụng và có lý do xác nhận. Phải phân biệt **kết quả theo từng control** với **quyết định phê duyệt kinh doanh**.

### 14.1. Bản ghi minh họa dạng YAML

Đây là **mẫu minh họa phục vụ bài học**, không phải schema chính thức hay cấu hình có thể áp dụng trực tiếp:

~~~yaml
assessment:
  id: "TP-SUB-ASSESS-EXAMPLE-008"
  assessed_at_utc: "2026-11-28T05:00:00Z"
  service: "crm-saas-example"
  controller: "example-retailer"
  processor: "example-crm-provider"
  subprocessor:
    legal_entity: "example-email-service"
    purpose: "Transactional support notifications"
    data_categories:
      - "Customer contact email"
      - "Support ticket reference"
    processing_location: "region-example"
    remote_support_locations: "TO_BE_CONFIRMED"
  scope:
    tenant: "retail-production"
    processing_enabled: false

authorization:
  mode: "general-written"
  notice_received_at_utc: "2026-11-20T08:00:00Z"
  notice_content_reviewed: true
  contractual_notice_window_verified: true
  decision: "PENDING_ASSESSMENT"

controls:
  data_minimization_verified: true
  encryption_evidence_reviewed: true
  flow_down_obligations_verified: true
  remote_access_locations_verified: false
  incident_notification_path_verified: true
  deletion_procedure_verified: false

findings:
  - id: "TP-SUB-FINDING-01"
    severity: "HIGH"
    issue: "Chưa xác định phạm vi support access và bằng chứng deletion"
    owner: "Third-Party Risk Owner"
    remediation: "Yêu cầu bổ sung hồ sơ, đánh giá lại trước khi bật tích hợp"

decision:
  outcome: "INCONCLUSIVE"
  production_enablement: "NO_GO"
  reviewer: "Security Assurance"
  accountable: "Business Service Owner"
  next_review: "After evidence completion"

evidence:
  - "restricted/tp-assurance/assessment-008/dpa-review"
  - "restricted/tp-assurance/assessment-008/data-flow"
  - "restricted/tp-assurance/assessment-008/security-evidence"
  - "restricted/tp-assurance/assessment-008/change-notice"
~~~

Ở đây, việc đã nhận thông báo và kiểm tra một số control **không đủ để bật tích hợp**: địa điểm/quyền support và quy trình xóa dữ liệu chưa có bằng chứng. Kết luận `INCONCLUSIVE` và `NO_GO` là lựa chọn của kịch bản giả định; quyết định thực tế còn phụ thuộc chính sách tổ chức, luật, hợp đồng và rủi ro cụ thể. Không gọi đây là PASS chỉ vì một số ô chứng cứ đánh dấu `true`.

### 14.2. Quy tắc lưu bằng chứng

Mọi artifact cần gắn assessment/control ID, tên bên liên quan, phạm vi tenant/dịch vụ, phiên bản, nguồn tài liệu, người thu thập, ngày hiệu lực/thời kỳ được đánh giá, giới hạn và kết quả. Báo cáo SOC 2, hợp đồng và danh sách dữ liệu có thể bị hạn chế chia sẻ; lưu ở kho được phân quyền và tham chiếu qua liên kết được kiểm soát, không sao chép vô hạn vào ticket công khai.

## 15. Tình huống thực hành: CRM bổ sung dịch vụ phân tích mới

Một doanh nghiệp thương mại điện tử dùng CRM SaaS để quản lý yêu cầu hỗ trợ khách hàng. CRM là processor đối với dữ liệu xử lý theo chỉ dẫn của doanh nghiệp. DPA cho phép sử dụng subprocessor theo cơ chế **ủy quyền chung bằng văn bản**, có quy trình thông báo thay đổi và cơ hội phản đối.

CRM thông báo sẽ bổ sung một **dịch vụ phân tích hội thoại** để tự động gợi ý câu trả lời cho nhân viên hỗ trợ. Dịch vụ này có thể nhận nội dung ticket, email, mã đơn và các thông tin cá nhân do khách hàng tự nhập. Nhà cung cấp CRM nói rằng dữ liệu được mã hóa khi truyền và bên mới “có chứng nhận bảo mật”. Họ dự định bật tính năng mặc định cho mọi tenant. Danh sách subprocessor mới ghi địa điểm hosting tại vùng A, nhưng chưa nêu nơi đội hỗ trợ của bên phân tích có thể truy cập dữ liệu. Hợp đồng chưa làm rõ liệu nội dung ticket có thể được dùng cho mục đích độc lập như huấn luyện mô hình.

### 15.1. Câu hỏi

1. Bên phân tích có chắc chắn là subprocessor cho toàn bộ hoạt động của mình không?
2. Chỉ có thông báo và chứng nhận bảo mật đã đủ cho kết luận assurance PASS chưa?
3. Trước khi bật mặc định, cần những bằng chứng và quyết định nào?
4. Nếu phát hiện bên phân tích muốn dùng dữ liệu cho mục đích riêng, phải đánh giá lại điều gì?
5. Nếu doanh nghiệp phản đối, những lựa chọn thực tế nào cần được xem xét theo hợp đồng?

### 15.2. Hướng phân tích

**Bước 1 — Phân loại vai trò theo từng mục đích.** Nếu dịch vụ chỉ xử lý ticket thay mặt CRM để phục vụ mục đích của controller theo chỉ dẫn, nó có thể là subprocessor. Nếu tự quyết định dùng dữ liệu cho mục đích độc lập (ví dụ huấn luyện sản phẩm riêng) thì cần **phân tích vai trò khác đối với hoạt động đó**; không gộp mọi xử lý vào một nhãn subprocessor hoặc coi mọi mục đích đều đã được controller cho phép.

**Bước 2 — Kiểm tra dữ liệu và luồng truy cập.** Lập danh sách trường ticket, file đính kèm, nội dung tự do, tài khoản liên quan, thời hạn lưu, vùng xử lý và đường hỗ trợ từ xa. Xác định tính năng có thể được tắt, giới hạn field, loại bỏ dữ liệu nhạy cảm trước khi gửi hoặc sử dụng phương án thay thế.

**Bước 3 — Kiểm tra quyền thông báo/phản đối.** Đối chiếu DPA và luật áp dụng về thời điểm thông báo, cơ hội phản đối và hệ quả xử lý khi phản đối. Ghi thời gian và quyết định. Không chấp thuận tự động chỉ vì email không được phản hồi; cũng không tự tuyên bố có quyền từ chối vô điều kiện nếu hợp đồng quy định cơ chế khác.

**Bước 4 — Đánh giá security/privacy evidence.** Xác định phạm vi chứng nhận có bao phủ dịch vụ phân tích mới không; quyền truy cập plaintext; encryption và key ownership; logging; tenant isolation; incident response; retention/deletion; flow-down; nơi truy cập; và các nghĩa vụ transfer có thể áp dụng. Một chứng nhận chung không trả lời hết các điểm này.

**Bước 5 — Ra quyết định theo rủi ro.** Khi còn thiếu thông tin về mục đích độc lập, support access và deletion, nên đặt trạng thái **chưa đủ bằng chứng** theo control tương ứng; xem xét tạm không bật tính năng hoặc giới hạn luồng dữ liệu theo quyền hợp đồng. Nếu phải thay đổi dịch vụ, đánh giá giải pháp không dùng tính năng mới, một processor khác hoặc điều chỉnh hợp đồng.

**Bước 6 — Giám sát sau quyết định.** Cập nhật danh mục subprocessor, data flow, quyền tích hợp, version DPA, bằng chứng review, owner và thời điểm đánh giá lại. Nếu có incident hoặc thêm bên xử lý tiếp theo, khởi động quy trình change/risk assessment tương ứng.

### 15.3. Đáp án cốt lõi

**Không nên mặc định PASS.** Đây là trường hợp cần kiểm tra cả **vai trò pháp lý theo mục đích**, **cơ chế ủy quyền/thông báo**, **phạm vi dữ liệu thực tế**, **các security controls** và **đường xử lý/transfer**. Việc nhà cung cấp tuyên bố “đã mã hóa” và “có chứng nhận” không đủ chứng minh rằng tính năng mới được phép sử dụng dữ liệu khách hàng cho mọi mục đích.

## 16. Sai lầm thường gặp khi đánh giá Subprocessor

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Gọi mọi vendor là subprocessor. | Xác định sai vai trò và nghĩa vụ xử lý dữ liệu. | Phân loại theo dữ liệu, mục đích, chỉ dẫn và quyền quyết định thực tế. |
| Chỉ theo dõi processor chính, không theo tầng thuê lại. | Bỏ sót nơi dữ liệu được lưu hoặc truy cập thực tế. | Data flow và inventory theo chuỗi trong phạm vi rủi ro. |
| Xem danh sách subprocessor công khai là inventory đầy đủ của tenant. | Thiếu add-on tùy chọn hoặc dịch vụ hỗ trợ riêng. | Đối chiếu hợp đồng, cấu hình, vendor attestation và thực tế. |
| Chỉ nhìn data residency mà bỏ nơi truy cập từ xa. | Bỏ sót rủi ro support access và transfer. | Phân biệt storage, processing, remote access và luật áp dụng. |
| Coi chứng nhận ISO hoặc SOC là bảo đảm tuyệt đối. | Bỏ ngoại lệ, giới hạn phạm vi và shared responsibility. | Đọc scope, kỳ kiểm toán, findings, subservice và user controls. |
| Không quản lý thời hạn phản hồi thông báo thay đổi. | Mất cơ hội đánh giá/phản đối theo cơ chế đã ký. | Tạo owner, kênh tiếp nhận và change ticket tự động/định kỳ. |
| Dùng phê duyệt một mục đích cho mục đích mới. | Xử lý dữ liệu ngoài phạm vi đã cho phép. | Đánh giá lại khi tính năng, dữ liệu hoặc mục đích đổi. |
| Xem mã hóa là thay thế hợp đồng/transfer assessment. | Có thể thiếu điều kiện pháp lý dù kênh bảo mật. | Tách legal, contractual và technical controls. |
| Chỉ hỏi vendor có IR plan không. | Không có thông báo kịp thời hoặc thông tin phục vụ đánh giá tác động. | Thử contact path, format thông báo, escalation và cam kết hợp đồng. |
| Xóa dữ liệu nguồn nhưng quên backup/log/ticket. | Dữ liệu còn tồn tại ngoài phạm vi sử dụng đã duyệt. | Kế hoạch deletion/retention theo loại bản sao, kiểm chứng và theo dõi ngoại lệ. |
| Chấp nhận rủi ro vô thời hạn. | Finding kéo dài không được khắc phục. | Owner, expiry, điều kiện review, kiểm soát bù trừ và retest. |
| Giám sát chỉ vào kỳ tái ký hợp đồng. | Thay đổi subprocessor hoặc incident không được phát hiện kịp. | Theo dõi sự kiện thay đổi và bằng chứng liên tục theo rủi ro. |

## 17. Checklist dành cho Security Assurance

Trước khi phê duyệt hoặc tái đánh giá một subprocessor, kiểm tra:

1. **Vai trò:** Đã phân loại theo hoạt động xử lý thực tế, phân biệt processor, subprocessor, controller độc lập và các tầng tiếp theo chưa?
2. **Inventory:** Có tên pháp nhân, dịch vụ, mục đích, dữ liệu, chủ thể dữ liệu, nơi xử lý và đường truy cập từ xa đúng phạm vi tenant chưa?
3. **Ủy quyền:** Hình thức cho phép sử dụng đã đáp ứng hợp đồng/luật áp dụng; thay đổi được thông báo và xử lý theo đúng quy trình chưa?
4. **Flow-down:** Nghĩa vụ xử lý dữ liệu, bảo mật, hỗ trợ, audit, incident và deletion đã được ràng buộc xuống bên xử lý phụ phù hợp chưa?
5. **Rủi ro:** Đã đánh giá độ nhạy cảm, quy mô, quyền truy cập, quốc gia, điểm lỗi chung và khả năng exit chưa?
6. **Bằng chứng:** Chứng nhận/báo cáo có đúng pháp nhân, scope, thời kỳ và control liên quan; ngoại lệ và phần loại trừ đã được xem xét chưa?
7. **Kỹ thuật:** IAM, encryption, key management, tenant isolation, logging, patch, BC/DR và data minimization có đáp ứng yêu cầu theo phạm vi không?
8. **Transfer:** Các luồng xử lý/chuyển dữ liệu quốc tế đã được phân loại, đánh giá cơ chế và biện pháp cần thiết chưa?
9. **Change:** Có kênh nhận thông báo, người phụ trách, thời hạn, trigger đánh giá lại và lịch sử quyết định không?
10. **Incident:** Có đường báo sự cố từ subprocessor qua processor tới controller, thông tin tối thiểu và khả năng phối hợp đúng thời hạn áp dụng không?
11. **Exit:** Có thể ngừng truyền dữ liệu, thu hồi quyền, xuất/xóa dữ liệu và kiểm chứng backup/log/ngoại lệ không?
12. **Kết luận:** Mỗi control có PASS/FAIL/INCONCLUSIVE/NOT_APPLICABLE, bằng chứng, chủ sở hữu và retest; risk acceptance được quản lý riêng chưa?
13. **Liên tục:** Đã theo dõi ngày hết hiệu lực của chứng cứ, thay đổi sản phẩm/nhà cung cấp và findings chưa hoàn tất chưa?

**Assurance cho subprocessor không phải cuộc kiểm tra tên nhà cung cấp một lần. Đó là khả năng truy vết toàn bộ chuỗi xử lý theo dữ liệu và mục đích được phép, xác minh nghĩa vụ và controls thực tế bằng bằng chứng, phát hiện thay đổi kịp thời, xử lý sự cố đúng trách nhiệm và chứng minh rằng dữ liệu cùng quyền truy cập được quản lý đến tận khi kết thúc quan hệ.**
