# Privacy risk

Trong chương **Privacy assurance**, **privacy risk** (rủi ro về quyền riêng tư) là khả năng một hoạt động xử lý dữ liệu, một đặc tính của hệ thống hoặc một sự kiện liên quan đến thông tin về con người gây ra **tác động bất lợi đối với cá nhân hoặc nhóm người**. Tác động có thể bao gồm tiết lộ thông tin ngoài mong đợi, mất quyền kiểm soát, bị theo dõi quá mức, phân biệt đối xử, suy luận nhạy cảm, bị từ chối cơ hội hoặc phải chịu những hậu quả khó sửa chữa do dữ liệu bị dùng sai bối cảnh.

Ví dụ, một nền tảng học trực tuyến hoàn toàn không bị tấn công vẫn có thể tạo privacy risk nếu thu thập lịch sử tương tác học tập chi tiết hơn mức cần thiết, tự động đánh dấu “nguy cơ bỏ học cao”, rồi hiển thị dự đoán này cho người không có nhu cầu biết. Mọi truy cập có thể được cấp quyền về mặt kỹ thuật nhưng **mục đích, mức độ thu thập, thông báo, tính chính xác và hậu quả đối với học viên vẫn có vấn đề về quyền riêng tư**.

Bài học thuộc module **SECURITY_SECURITY_ASSURANCE**, với mục tiêu xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật: từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit, khắc phục finding và duy trì assurance trong phát triển, vận hành. Vì thế, trọng tâm không chỉ là định nghĩa privacy risk mà là **biến một kịch bản ảnh hưởng đến con người thành yêu cầu bảo vệ, control có owner, phép kiểm tra, bằng chứng và một kết luận có giới hạn rõ ràng**.

> **Nguyên tắc xuyên suốt:** bảo mật thông tin là điều kiện rất quan trọng của quyền riêng tư, nhưng **một hệ thống được bảo vệ tốt trước tấn công vẫn có thể xử lý dữ liệu theo cách xâm phạm quyền riêng tư**. Privacy assurance phải đánh giá cả xử lý dữ liệu **được phép về mặt kỹ thuật** lẫn hành vi trái phép.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích privacy risk, privacy event, privacy harm và phân biệt chúng với information security risk, compliance risk, business risk.
2. Nhận diện privacy risk ở **mọi hoạt động xử lý dữ liệu**, không chỉ khi bị rò rỉ hoặc tấn công.
3. Phân tích **dữ liệu, mục đích, actor, cá nhân bị ảnh hưởng, data flow, bên nhận và vòng đời dữ liệu**.
4. Phác thảo threat/privacy modeling bằng cách đặt câu hỏi về khả năng liên kết, định danh, nhận biết, tiết lộ, bị theo dõi hoặc thiếu minh bạch.
5. Xây privacy risk scenario có nguyên nhân, hoạt động/sự kiện, cơ chế tác động, nhóm bị ảnh hưởng và hậu quả.
6. Phân tích khả năng xảy ra và mức độ nghiêm trọng với những giả định rõ, tránh điểm số “khách quan” giả tạo.
7. Chọn controls theo các nguyên tắc data minimization, purpose limitation, transparency, access control, retention, accuracy, user choice và vendor governance khi áp dụng.
8. Xây **Claim–Argument–Evidence** và kiểm chứng design, implementation, operating effectiveness.
9. Phối hợp Data Owner, Privacy/Legal, Product, Engineering, Security Assurance và risk owner trong risk treatment.
10. Viết risk register, assessment, finding, remediation và retest cho một chức năng nền tảng học trực tuyến.

## 2. Privacy risk là gì?

### 2.1. Từ hoạt động xử lý đến tác động con người

Một privacy risk thường xuất phát từ sự tương tác giữa:

- **Hoạt động xử lý:** thu thập, tạo, gắn nhãn, sử dụng, lưu, đối chiếu, chia sẻ, suy luận, quyết định, xóa.
- **Bối cảnh:** tại sao xử lý, quan hệ giữa tổ chức và người có dữ liệu, quyền lực hoặc kỳ vọng hợp lý của họ.
- **Đối tượng dữ liệu:** thông tin nhận dạng trực tiếp, dữ liệu có khả năng liên kết, dữ liệu nhạy cảm, dữ liệu dẫn xuất.
- **Điều kiện bất lợi:** không tương xứng mục đích, không được nhận biết/kiểm soát, sai lệch, chia sẻ quá rộng, retention quá lâu, mô hình suy luận sai.
- **Harm:** ảnh hưởng tiêu cực lên cá nhân hoặc nhóm, kể cả hậu quả chưa xảy ra ngay.
- **Mức độ không chắc chắn:** các giả định và giới hạn về việc sự kiện có thể xảy ra và hậu quả ra sao.

Có thể mô tả một kịch bản ở mức khái niệm:

~~~text
Privacy risk scenario =
  Processing context
  + Data and affected population
  + Privacy event or problematic processing
  + Mechanism leading to adverse effects
  + Potential individual/group harms
  + Likelihood, severity and uncertainty
~~~

Đây là **cấu trúc phân tích** chứ không phải công thức định lượng được chuẩn hóa. Không nên cộng một cách máy móc các mục trên rồi tuyên bố có “điểm rủi ro chính xác”.

### 2.2. Ví dụ: chức năng phân tích hành vi học tập

Một ứng dụng ghi nhận thời điểm học viên mở từng bài, thời gian xem video, số lần làm lại bài tập và kết quả kiểm tra. Product muốn tìm người cần hỗ trợ.

**Mục đích tốt có thể có:** hỗ trợ học viên học hiệu quả.

**Những privacy risks cần phân tích:**

- Người học không biết mức độ theo dõi chi tiết, cảm thấy phải thay đổi hành vi.
- Kết quả dự đoán suy ra đặc điểm nhạy cảm hoặc tình trạng cá nhân không được yêu cầu.
- Một chỉ số sai khiến giảng viên mặc định học viên thiếu năng lực.
- Báo cáo được chia sẻ cho người hoặc vendor ngoài phạm vi mục đích.
- Dữ liệu được giữ nhiều năm rồi sử dụng trong bối cảnh tuyển sinh/tuyển dụng khác.
- Nhóm nhỏ bị nhận dạng dù dashboard chỉ hiện số tổng hợp.

**Điều cần kiểm chứng:** mục đích và giới hạn được duyệt; dữ liệu thu thập tối thiểu; quyền, độ chính xác, thông báo, retention, kiểm soát chia sẻ và quy trình xem xét tác động. Chỉ bật TLS/MFA chưa đủ.

### 2.3. Privacy event là gì?

**Privacy event** là một sự kiện hoặc điều kiện trong quá trình xử lý có thể dẫn đến tác động riêng tư, ví dụ:

- Hệ thống tiết lộ học viên đang học khóa hỗ trợ tâm lý dù người nhận không có nhu cầu biết.
- Hồ sơ người dùng từ hai nguồn được liên kết thành profile chi tiết hơn kỳ vọng.
- Một thuật toán xếp loại làm cá nhân bị đối xử bất lợi vì dữ liệu sai.
- Cơ chế hủy tham gia thu thập dữ liệu không được thực thi.
- Thời hạn lưu dữ liệu kết thúc nhưng bản sao vẫn dùng được.
- Biểu đồ công khai một nhóm rất nhỏ cho phép suy ra thành viên.
- Một bên thứ ba xử lý dữ liệu cho mục đích mới mà chưa được xem xét.

Sự kiện có thể do **lỗi, lạm dụng, thay đổi hoạt động, sử dụng theo thiết kế hoặc quyết định tổ chức**. Vì vậy phải phỏng vấn nghiệp vụ và xem data flow, không chỉ đọc vulnerability scanner.

## 3. Privacy risk khác security risk như thế nào?

| Chiều phân tích | Information security risk | Privacy risk |
|---|---|---|
| **Đối tượng chính** | Tài sản, dịch vụ, thông tin và tổ chức chịu ảnh hưởng | Cá nhân/nhóm bị ảnh hưởng bởi xử lý dữ liệu |
| **Mục tiêu** | Confidentiality, integrity, availability và những thuộc tính bảo mật liên quan | Kiểm soát phù hợp, hạn chế tác động riêng tư, xử lý đúng bối cảnh và nghĩa vụ |
| **Nguồn rủi ro** | Threat actor, vulnerability, lỗi control, sự cố | Cả xử lý hợp lệ nhưng quá mức, suy luận, sai mục đích, thiếu minh bạch, sai dữ liệu |
| **Ví dụ** | API bị truy cập không có quyền; database bị mã hóa tống tiền | Thu thập tracking quá sâu; chia sẻ dự đoán nhạy cảm; profiling thiếu cơ chế xem lại |
| **Control thường gặp** | AuthN/AuthZ, encryption, patching, monitoring, backup | Data minimization, purpose limits, transparency, user choice, accuracy, retention và security controls |
| **Bằng chứng** | Negative tests, IAM export, logs, incident/recovery records | Data map, mục đích, notice, kiểm thử data flow, choice, deletion, review tác động, security tests |
| **Tác động** | Có thể là mất CIA, ngừng dịch vụ, tiền và uy tín | Có thể là mất tự chủ, bị phán xét bất công, tổn thương danh dự, kỳ thị, xâm phạm đời sống riêng |
| **Quan hệ** | Vi phạm bảo mật có thể dẫn đến privacy harm | Privacy risk có thể tồn tại ngay khi CIA controls hoạt động đúng |

Ba điểm không nên nhầm:

1. **Không phải mọi sự cố bảo mật đều tự động là sự cố dữ liệu cá nhân**: cần xác định dữ liệu, đối tượng và nghĩa vụ.
2. **Không phải mọi privacy risk cần có hacker**: hệ thống được thiết kế để giám sát có thể tạo ảnh hưởng ngay khi mọi quyền kỹ thuật hợp lệ.
3. **Không phải mọi privacy risk đều được “giải quyết” bằng mã hóa**: mã hóa không sửa mục đích xử lý sai hoặc dự đoán bất công khi người dùng hệ thống đã được phép xem dữ liệu.

### 3.1. Privacy risk và compliance risk

**Compliance risk** phản ánh nguy cơ tổ chức không đáp ứng nghĩa vụ luật, quy định, hợp đồng hoặc chính sách. **Privacy risk** tập trung vào những tác động bất lợi lên con người do hoạt động xử lý. Chúng có vùng giao nhau nhưng không đồng nhất.

Một tổ chức có thể đáp ứng một checklist tài liệu nhưng vẫn cần đánh giá privacy harms theo bối cảnh. Ngược lại, mức privacy harm được đánh giá thấp **không phải lý do để bỏ qua yêu cầu pháp luật bắt buộc**. Phân tích nghĩa vụ phải do Legal/Privacy hoặc bộ phận được giao xem xét theo khung pháp lý áp dụng.

### 3.2. Privacy impact và organizational impact

Một privacy incident có thể gây phạt, kiện tụng, mất uy tín và chi phí cho tổ chức. Tuy nhiên, khi chấm privacy risk, đừng để các thiệt hại doanh nghiệp **che lấp ảnh hưởng đối với cá nhân**. Ví dụ dữ liệu một nhóm nhỏ người học bị suy đoán tình trạng sức khỏe có thể có tác động nghiêm trọng lên nhóm đó, dù doanh nghiệp không bị thiệt hại tài chính lớn.

Risk register có thể lưu **cả individual impact và organizational impact**, nhưng phương pháp ưu tiên phải minh bạch thay vì trộn chúng thành một điểm duy nhất không giải thích.

## 4. Các loại privacy harms cần nhận diện

Privacy harm không chỉ là “lộ dữ liệu”.

| Nhóm harm | Biểu hiện | Ví dụ trong nền tảng học |
|---|---|---|
| **Mất kiểm soát/tự chủ** | Cá nhân không thể lựa chọn, hiểu hoặc giới hạn việc xử lý có tác động | Theo dõi hành vi học tập vượt mục đích đã nêu |
| **Tiết lộ ngoài mong đợi** | Thông tin tới người hoặc bối cảnh không phù hợp | Phụ huynh/giảng viên xem ghi chú riêng tư không có quyền |
| **Liên kết và suy luận** | Ghép nhiều nguồn để suy ra thuộc tính cá nhân | Ghép vị trí, lịch học và bài làm để dự đoán hoàn cảnh riêng |
| **Đánh giá sai/profiling** | Phân loại hoặc suy đoán kém chính xác tạo hậu quả bất lợi | Học viên bị gắn nhãn “thiếu nỗ lực” do lỗi dữ liệu |
| **Phân biệt đối xử/cơ hội** | Dữ liệu được dùng để đối xử không công bằng | Chỉ một nhóm bị hạn chế cơ hội từ mô hình suy luận |
| **Theo dõi và hiệu ứng răn đe** | Người dùng thay đổi hành vi vì cảm thấy mọi hoạt động bị giám sát | Không dám mở tài liệu hỗ trợ cá nhân |
| **Thao túng/lạm dụng mục đích** | Dùng dữ liệu để nhắm mục tiêu hoặc gây áp lực | Nội dung cá nhân hóa khai thác điểm yếu của người học |
| **Rủi ro an toàn hoặc danh dự** | Dữ liệu làm lộ nơi ở, lịch trình hoặc thông tin nhạy cảm | Rò rỉ lịch học kèm chi tiết liên hệ |
| **Khó sửa sai** | Cá nhân không thể biết, yêu cầu sửa, tranh luận hoặc cải chính quyết định | Thông tin sai lan qua nhiều dữ liệu dẫn xuất |
| **Hậu quả tích lũy** | Nhiều xử lý nhỏ kết hợp tạo bức tranh đời sống rất chi tiết | Dữ liệu điểm, video, chat và lượt truy cập được hợp nhất |

Mức tác động phụ thuộc **ngữ cảnh, loại dữ liệu, nhóm người, quy mô, khả năng lạm dụng, thời hạn tồn tại và khả năng đảo ngược**, không chỉ dựa trên “có tên hay email hay không”.

### 4.1. Nhóm có khả năng chịu tác động nặng hơn

Trong một số trường hợp, trẻ em, người ít khả năng tự quyết, người có quan hệ phụ thuộc hoặc những nhóm dễ bị kỳ thị có thể chịu tác động nghiêm trọng hơn từ cùng một hoạt động xử lý. Cần xem điều kiện thực tế, tránh suy diễn đặc điểm nhạy cảm của từng người khi không có căn cứ.

Một dữ liệu có vẻ thông thường như thời gian học hoặc lượt nhấp có thể trở nên nhạy cảm nếu suy luận ra vấn đề sức khỏe, tôn giáo, mức sống hoặc hoàn cảnh gia đình. Bản thân việc suy luận và độ chính xác của kết luận cần được đánh giá như một phần của privacy risk.

## 5. Dữ liệu cá nhân, nhận dạng và khả năng liên kết

### 5.1. Không chỉ dữ liệu có tên hoặc số định danh

Các nguồn rủi ro có thể gồm:

- **Định danh trực tiếp:** tên, tài khoản, email, số điện thoại hoặc các mã có thể gắn trực tiếp với cá nhân tùy ngữ cảnh.
- **Định danh gián tiếp/quasi-identifiers:** tổ hợp lớp học, năm sinh, địa bàn, lịch hoạt động, thiết bị, mã phiên.
- **Dữ liệu hành vi:** lịch truy cập, lượt xem, điểm, lịch sử làm bài, tương tác.
- **Nội dung tự do:** bài luận, tin nhắn, yêu cầu hỗ trợ; có thể chứa thông tin nhạy cảm khó dự đoán.
- **Dữ liệu vị trí/thiết bị:** địa chỉ mạng, định vị hoặc dấu vân tay thiết bị khi thu thập.
- **Dữ liệu suy luận:** nhãn, nhóm, chỉ số nguy cơ, dự đoán năng lực.
- **Dữ liệu quan hệ:** ai thuộc lớp nào, nhóm nào, tương tác với ai.

Đánh giá tính nhận dạng phải xét **những dữ liệu khác mà bên sử dụng có thể kết hợp một cách hợp lý**, không chỉ một cột dữ liệu đứng riêng.

### 5.2. Pseudonymization khác anonymization

**Pseudonymization** thay hoặc tách các định danh trực tiếp bằng mã, trong khi vẫn có thể liên kết lại qua khóa/bảng mapping hoặc thông tin bổ sung. Nó có thể giúp giảm phơi bày nhưng **không mặc nhiên làm dữ liệu mất tính cá nhân**.

**Anonymization** hướng tới làm dữ liệu không còn liên kết tới cá nhân theo tiêu chí và bối cảnh đánh giá tương ứng. Không thể khẳng định đã ẩn danh chỉ bằng cách:

- Xóa trường fullName.
- Hash email không có biện pháp chống dò đoán.
- Thay tên bằng sequential IDs.
- Tổng hợp dữ liệu trong nhóm quá nhỏ.
- Loại vài cột nhưng giữ dữ liệu hành vi rất đặc trưng.

Với mỗi kỹ thuật, cần phân tích **linkability, singling out, inference và khả năng tái nhận dạng** theo bối cảnh, mục tiêu, quyền truy cập và sự thay đổi của dữ liệu phụ trợ. Không có một kỹ thuật đơn lẻ bảo đảm ẩn danh tuyệt đối trong mọi tình huống.

### 5.3. Dữ liệu dẫn xuất vẫn có rủi ro

Một thuật toán dự đoán khả năng bỏ học có thể dùng dữ liệu đã loại tên, nhưng output được gắn lại learnerId để hiển thị cho tư vấn viên. Lúc này kết quả dự đoán rõ ràng ảnh hưởng tới cá nhân. Assurance phải đánh giá **toàn bộ luồng: nguồn → biến đổi → mô hình → kết quả → người nhận → quyết định**, không chỉ tính riêng tư của dữ liệu đầu vào.

## 6. Data lifecycle và privacy risk

Privacy risk thay đổi theo từng giai đoạn:

~~~mermaid
flowchart TD
    A["Xác định mục đích và dữ liệu cần dùng"] --> B["Thu thập / nhận dữ liệu"]
    B --> C["Lưu trữ, định danh, liên kết"]
    C --> D["Sử dụng, suy luận, ra quyết định"]
    D --> E["Chia sẻ, xuất, tích hợp vendor"]
    E --> F["Lưu giữ, sao lưu, tái sử dụng"]
    F --> G["Hết mục đích, archive/xóa"]
    B --> H["Thông báo, lựa chọn, quyền của cá nhân"]
    D --> H
    E --> H
    G --> I["Bằng chứng và review xuyên vòng đời"]
    I --> A
~~~

| Giai đoạn | Privacy questions | Evidence gợi ý |
|---|---|---|
| **Design/purpose** | Vì sao phải xử lý? Có mục tiêu thay thế ít xâm phạm hơn? | Purpose specification, risk assessment, design decision |
| **Collection** | Có quá nhiều dữ liệu hoặc thu thập ngầm không? | Input schema, instrumentation inventory, test payload |
| **Linking/storage** | Đã gắn dữ liệu đúng người, đúng tenant; kiểm soát khả năng kết hợp? | Data mapping, IAM, partition tests, key controls |
| **Use/inference** | Mô hình hoặc quy tắc sử dụng có gây hậu quả không mong muốn? | Model/data review, use-case test, human review workflow |
| **Disclosure/sharing** | Bên nhận và dữ liệu có đúng phạm vi, có kiểm soát downstream? | Contract, API scopes, export tests, access logs |
| **Retention** | Có giữ quá lâu, nhân bản nhiều nơi hoặc tiếp tục dùng ngoài mục đích? | Retention schedule, system/backup/vendor inventory |
| **Deletion/exit** | Có ngừng xử lý, xóa/giữ hợp lệ và kiểm chứng được không? | Deletion requests, job logs, data return/erasure evidence |
| **Operation/change** | Quyền, data flow, model, mục đích hoặc luật đã thay chưa? | Change records, reassessments, incident/finding history |

Một điểm đặc biệt: **privacy harm có thể phát sinh trước khi lưu dữ liệu** (ví dụ việc quan sát quá mức), hoặc sau khi đã xóa bản gốc (ví dụ kết luận sai được chia sẻ trước đó). Vì vậy deletion là một control quan trọng nhưng không xóa tất cả hậu quả đã xảy ra.

## 7. Xác định bối cảnh và ranh giới đánh giá

### 7.1. Mục đích trước, công nghệ sau

Một privacy risk assessment nên bắt đầu bằng:

1. **Business purpose:** kết quả mong muốn và lợi ích cho ai?
2. **Necessity:** cần xử lý loại dữ liệu này không, có lựa chọn ít xâm phạm hơn?
3. **Proportionality:** quy mô, độ chi tiết, thời gian và phạm vi chia sẻ có tương xứng?
4. **Data subjects:** những cá nhân/nhóm nào bị ảnh hưởng?
5. **Roles and responsibilities:** data owner, product owner, controller/processor theo luật áp dụng, vendor, assessor.
6. **Processing operations:** thu thập, biến đổi, suy luận, kết hợp, xuất, lưu, xóa.
7. **Trust boundaries:** client/backend, các tenant, cloud, vendor, con người với hệ thống.
8. **Decision and remedies:** dữ liệu có tác động tới quyền lợi hoặc quyết định nào, cá nhân có thể biết hoặc yêu cầu xem xét ra sao?
9. **Assumptions:** điều chưa biết, hạn chế của data map và đánh giá pháp lý.

### 7.2. Data inventory là điều kiện để đánh giá

Một data inventory/cataloɡ có thể ghi:

- Dataset/data product ID, mục đích, data owner, system owner.
- Source và loại dữ liệu, mức nhạy cảm, vùng lưu/xử lý.
- Người dùng hợp lệ, nhóm cá nhân liên quan, data subjects/tenants.
- Data flows: nguồn, ETL, logs, cache, storage, backup, recipients.
- Third parties/subprocessors và shared responsibility.
- Legal/policy references trong phạm vi áp dụng.
- Data minimization, retention, deletion, access requirements.
- Bằng chứng về quyền, thông báo, lựa chọn và các yêu cầu của cá nhân khi áp dụng.
- Change triggers, findings và scope gaps.

Một hệ thống ít rủi ro vẫn cần biết **dữ liệu nào đang được xử lý**. Tuy nhiên nên giữ metadata và liên kết nguồn, tránh tạo một catalog chứa bản sao toàn bộ dữ liệu cá nhân không cần thiết.

### 7.3. Hidden processing và shadow data

Lỗ hổng inventory thường xuất hiện ở:

- SDK analytics tự gửi sự kiện không có trong yêu cầu ban đầu.
- Application logs chứa payload cá nhân.
- Dataset thử nghiệm sao chép từ production.
- Công cụ hỗ trợ hoặc chatbot lưu nội dung trò chuyện.
- Job ETL cũ tiếp tục đồng bộ sau khi tính năng bị ngừng.
- Third-party service được nhóm sản phẩm tự đăng ký.
- Dữ liệu mà người dùng nhập tự do nhưng hệ thống coi là “không nhạy cảm”.
- Bản tóm tắt/dự đoán từ mô hình được sao chép sang bảng khác.

Nếu chưa nhìn thấy các đường này, kết luận privacy assurance cần ghi **độ bao phủ chưa đủ** thay vì tự loại trừ chúng để báo “đạt toàn diện”.

## 8. Sơ đồ data flow cho tình huống học tập

~~~mermaid
flowchart LR
    U["Học viên"] --> WEB["Web / Mobile client"]
    WEB --> API["Learning API (Java)"]
    API --> DB[("Learner records")]
    WEB --> SDK["Analytics SDK"]
    API --> EVT["Learning events"]
    EVT --> PIPE["ETL / feature pipeline"]
    PIPE --> WH[("Analytics warehouse")]
    WH --> MODEL["Progress / dropout model"]
    MODEL --> DASH["Counselor dashboard"]
    WH --> VENDOR["External analytics provider"]
    DB --> BACKUP[("Backup")]
    API --> LOG["Audit / app logs"]
    VENDOR --> SUB["Vendor subprocessors"]
~~~

### 8.1. Trust boundary và câu hỏi trọng yếu

- **Web/mobile → API:** dữ liệu nào được gửi, có user control, event tracking và mục đích rõ không?
- **API → DB:** có bảo vệ quyền theo tenant, class và loại dữ liệu không?
- **Client → SDK:** SDK có tự thu thập IP, thiết bị, nội dung hoặc định danh vượt scope không?
- **ETL → warehouse:** mã ID có thể liên kết với hồ sơ gốc; quyền truy vấn được giới hạn tới đâu?
- **Warehouse → model:** dữ liệu được chọn có cần thiết, có khả năng tạo suy luận nhạy cảm không?
- **Model → dashboard:** ai thấy nhãn cá nhân, họ hiểu giới hạn và có cơ chế phản hồi/sửa sai không?
- **Warehouse → vendor → subprocessor:** dữ liệu gì được chia sẻ, sử dụng/giữ ở đâu, vào mục đích nào?
- **DB/ETL → logs/backups:** dữ liệu cá nhân còn trong log/backup lâu hay không?
- **Kết thúc:** dữ liệu dẫn xuất, model artifacts, export và vendor copies được xử lý thế nào?

Sơ đồ DFD giúp **phát hiện nơi có thể phát sinh privacy event**, nhưng **không chứng minh** scope/cấu hình runtime hiện tại. Cần đối chiếu với event payloads, SDK settings, network/integration inventory, DB schema, policy và kết quả kiểm tra.

## 9. Phương pháp đặt câu hỏi phát hiện privacy risks

### 9.1. Phân tích theo chiều dữ liệu

Đối với mỗi hoạt động xử lý, hỏi:

- Dữ liệu **có cần thiết** để đạt mục tiêu đã định không?
- Có đang thu quá **nhiều trường, người, thời gian, tần suất** không?
- Người có dữ liệu có thể **biết, hiểu và dự đoán** cách sử dụng không?
- Dữ liệu được **kết hợp** với nguồn nào, có thể nhận ra một người dù xóa tên không?
- Kết quả xử lý có thể được **suy luận sai** hoặc gây đánh giá bất công không?
- **Bên nhận và quyền** nào có thể tiếp cận dữ liệu đầu ra?
- Người bị tác động có **cách phát hiện, khiếu nại, sửa lỗi hoặc yêu cầu xử lý** theo điều kiện áp dụng không?
- Dữ liệu có được **giữ hoặc dùng lại** ngoài kỳ/mục đích không?
- Nếu chức năng lỗi, ảnh hưởng tới cá nhân là gì?
- Dữ liệu đã xuất/bị suy luận có thể **thu hồi hoặc sửa hậu quả** tới đâu?

### 9.2. LINDDUN như gợi ý phân tích

Một phương pháp thường được tham khảo trong privacy threat modeling là **LINDDUN** với các nhóm mối đe dọa về quyền riêng tư:

| Nhóm | Câu hỏi cho hệ thống học |
|---|---|
| **Linkability** | Các sự kiện học tập tưởng như rời rạc có thể được liên kết thành profile một học viên không? |
| **Identifiability** | Có thể xác định cá nhân từ một bộ dữ liệu hay tổ hợp dữ liệu không? |
| **Non-repudiation** | Việc ghi và giữ bằng chứng hành vi có khiến cá nhân không thể chối bỏ hoạt động theo cách gây rủi ro privacy không? |
| **Detectability** | Người khác có thể nhận biết việc một học viên tồn tại trong một tập dữ liệu, khóa học hoặc nhóm nhạy cảm không? |
| **Disclosure of information** | Dữ liệu có được tiết lộ ngoài người/phạm vi hợp lệ không? |
| **Unawareness** | Người có dữ liệu có nhận biết và hiểu hoạt động xử lý có ý nghĩa không? |
| **Non-compliance** | Hoạt động xử lý có không đáp ứng các yêu cầu áp dụng không? |

Đây là **công cụ gợi ý cách suy nghĩ**, không phải checklist cố định bảo đảm đầy đủ mọi privacy harm. Nhóm *non-repudiation* trong LINDDUN cần hiểu theo **khía cạnh mất khả năng phủ nhận hành vi gây ảnh hưởng riêng tư**, khác với mục tiêu an ninh thông tin nơi non-repudiation có thể được coi là thuộc tính tích cực.

### 9.3. Dùng abuse case và stakeholder journey

Có thể bổ sung:

- **Abuse case:** một nhân viên hợp lệ xuất profile học viên cho mục đích riêng.
- **Unintended use case:** đội Product dùng lịch học để suy đoán khả năng tham gia một hoạt động nhạy cảm.
- **User journey:** một học viên muốn học riêng tư nhưng bị bật công khai tiến độ do default.
- **Data lifecycle walk-through:** người dùng yêu cầu xóa dữ liệu, nhưng export và model feature vẫn tồn tại.
- **Change review:** SDK cập nhật thêm loại thông tin thu thập hoặc vendor đổi mục đích.

Không phải mọi kịch bản phải do đối thủ độc hại thực hiện. **Xử lý được thiết kế và thực thi đúng chức năng vẫn có thể tạo privacy risk**.

## 10. Cấu trúc một privacy risk scenario

Một kịch bản đủ kiểm chứng nên mô tả:

1. **Risk ID** và nguồn phát hiện.
2. **Activity/purpose:** chức năng và lý do xử lý.
3. **System and data scope:** môi trường, dataset, trường, luồng, vùng xử lý.
4. **Affected people:** cá nhân/nhóm và yếu tố bối cảnh cần xem.
5. **Privacy event/problematic processing:** điều có thể xảy ra hoặc đang diễn ra.
6. **Causes/conditions:** thiết kế, thiếu control, dữ liệu sai, vendor change.
7. **Path to harm:** bằng cách nào xử lý dẫn đến hậu quả cho người thật.
8. **Harms:** tác động tiềm năng và độ khó sửa.
9. **Likelihood, impact, uncertainty:** đánh giá có cơ sở, không đoán chắc.
10. **Existing controls/evidence:** control đã có, đã kiểm chứng tới đâu.
11. **Treatment options:** giảm scope, thay thiết kế, ngừng xử lý, bổ sung quyền lựa chọn/kiểm soát.
12. **Owner, approval, due date, review triggers**.

### 10.1. So sánh ghi nhận yếu và tốt

**Chưa đủ:** “Có thể vi phạm quyền riêng tư vì dùng AI.”

**Rõ hơn:**

> Hệ thống dùng lịch truy cập và bài nộp của học viên để dự đoán nguy cơ bỏ học. Nhãn dự đoán hiển thị cho người hỗ trợ ở nhiều đơn vị, dù chỉ một số người cần biết. Nếu dự đoán sai hoặc người xem sử dụng ngoài mục đích tư vấn, học viên có thể bị đánh giá bất lợi, chịu áp lực hoặc mất cơ hội. Hiện chưa có bằng chứng về giới hạn role, độ chính xác theo nhóm và cơ chế điều chỉnh dữ liệu.

Kịch bản này giúp xác định **test cụ thể**: kiểm tra role/purpose, field minimization, giải thích giới hạn của dự đoán, xử lý dữ liệu sai, logging và quy trình review.

## 11. Phân tích privacy risk với khả năng xảy ra và tác động

### 11.1. Phân biệt inherent và residual risk

- **Inherent risk:** mức rủi ro trước khi xét hiệu quả các controls đã được chứng minh.
- **Residual risk:** mức rủi ro còn lại sau khi xét controls thực sự được triển khai và kiểm tra.
- **Target risk:** mức mong muốn hoặc ngưỡng xử lý theo chính sách, được tổ chức xác định.

Không thể giảm inherent risk xuống residual risk chỉ vì một control được **đề xuất** hoặc có policy PDF. Phải kiểm tra control ở scope tương ứng. Nếu evidence thiếu, cần ghi mức bất định, có thể hạn chế kết luận thay vì gán điểm residual thấp.

### 11.2. Likelihood cần xét điều gì?

- Số lượng và tần suất các hoạt động xử lý.
- Khả năng dữ liệu được liên kết hoặc tái nhận dạng.
- Số người/role/vendor có khả năng truy cập.
- Bề mặt chia sẻ, đường export, quyền mặc định, khả năng cấu hình sai.
- Lịch sử vấn đề/complaints, incident và finding tương tự.
- Mức độ tự động hóa, quy mô và độ khó phát hiện.
- Có biện pháp ngăn, hạn chế, phát hiện và sửa hậu quả nào đã được kiểm chứng?

Với kịch bản **xử lý mặc định gây ảnh hưởng** (như tracking quá mức), “khả năng xảy ra” có thể gần như chắc chắn vì chức năng hoạt động theo thiết kế. Khi đó trọng tâm cần chuyển sang **tần suất, mức độ phơi bày, phạm vi và tác động**, không áp cùng logic với xác suất hacker khai thác CVE.

### 11.3. Severity/impact cần xét điều gì?

- Mức nhạy cảm của thông tin và mức bất ngờ khi bị sử dụng/tiết lộ.
- Mức độ can thiệp vào quyết định, cơ hội, danh dự, an toàn hoặc đời sống riêng.
- Quy mô cá nhân/nhóm chịu tác động, kể cả thiệt hại của **một người** ở mức nghiêm trọng.
- Thời gian tồn tại và khả năng lan truyền của dữ liệu/nhãn.
- Có thể sửa sai, xóa hoặc giảm tác động thực tế tới đâu?
- Bối cảnh mất cân bằng quyền lực và khả năng tự quyết.
- Mức độ không chắc chắn về độ chính xác, cách các bên downstream sẽ dùng dữ liệu.
- Khả năng kết hợp với các nguồn khác tạo thông tin mới.

**Quy mô nhỏ không mặc định rủi ro thấp** nếu tác động lên một cá nhân có thể nặng.

### 11.4. Ma trận minh họa, không phải kết luận tự động

Có thể dùng phân loại định tính:

| Likelihood \\ Impact | Thấp | Vừa | Cao |
|---|---|---|---|
| **Thấp** | Thấp | Thấp/Vừa | Vừa/Cao, cần xem tác động |
| **Vừa** | Thấp/Vừa | Vừa | Cao |
| **Cao** | Vừa | Cao | Cao/Rất cao |

Bảng trên chỉ **minh họa cách tổ chức thảo luận**, không phải một chuẩn chấm điểm hay phép tính chắc chắn. Ranh giới mức độ, ngưỡng escalation, loại risk appetite và nghĩa vụ phải được tổ chức định nghĩa. Khi tác động khó đo, tốt hơn là ghi **khoảng bất định và những giả định có thể thay đổi quyết định**.

### 11.5. Risk matrix không thay đánh giá ethics và pháp lý

Một điểm rủi ro “Vừa” không cho phép tự động sử dụng dữ liệu cá nhân nếu hoạt động bị hạn chế theo luật/hợp đồng hoặc xung đột với nguyên tắc nội bộ bắt buộc. Đánh giá risk treatment phải có cổng **legal/policy constraints** riêng. Ngược lại, chỉ tick các điều kiện pháp lý cũng không tự chứng minh privacy harms đã được giảm đủ.

## 12. Privacy risk assessment theo từng bước

Một quy trình dễ vận hành:

1. **Define scope:** xác định sản phẩm, tính năng, dữ liệu, mục đích, người bị ảnh hưởng, môi trường, lifecycle.
2. **Identify obligations:** làm rõ quy tắc nội bộ, hợp đồng và luật áp dụng cùng Privacy/Legal.
3. **Map processing:** vẽ DFD, data inventory, lineage, vendor/subprocessor, data subjects, retention.
4. **Find privacy events:** brainstorming các harms kể cả khi truy cập được phép; dùng LINDDUN hoặc các prompts tương đương.
5. **Estimate risks:** ghi nguyên nhân, likelihood, severity, uncertainty và assumptions.
6. **Inspect existing controls:** phân biệt design, implementation, operating evidence.
7. **Choose treatments:** tránh, giảm, giới hạn, sửa thiết kế, chuyển phương thức, dừng hoạt động, bổ sung control.
8. **Assign responsibility:** business/product/data owner, privacy/security, engineer, vendor, risk decision authority.
9. **Verify and decide:** kiểm thử, evidence review, ghi residual risk, findings, quyết định có thẩm quyền.
10. **Monitor and reassess:** kích hoạt review khi thay data flow, model, recipient, SDK, vendor, purpose hoặc incident.

~~~mermaid
flowchart TD
    A["Mục đích và bối cảnh xử lý"] --> B["Data inventory / DFD / người bị ảnh hưởng"]
    B --> C["Privacy events và harms"]
    C --> D["Likelihood + severity + uncertainty"]
    D --> E["Chọn requirements / controls"]
    E --> F["Triển khai, kiểm thử và evidence"]
    F --> G{"Đã đủ bằng chứng và phù hợp?"}
    G -->|"Có"| H["Residual risk / assurance claim"]
    G -->|"Fail"| I["Finding + fix + retest"]
    G -->|"Thiếu"| J["Evidence gap / thu hẹp scope"]
    I --> F
    J --> B
    H --> K["Quyết định đúng thẩm quyền"]
    K --> L["Monitoring, change, complaints, incidents"]
    L --> B
~~~

### 12.1. Khi nào cần một đánh giá tác động riêng?

Tùy pháp luật, loại xử lý và rủi ro, tổ chức có thể cần **đánh giá tác động bảo vệ dữ liệu hoặc privacy impact assessment**, đôi khi được gọi DPIA/PIA. Việc có bắt buộc không, nội dung tối thiểu, ai phê duyệt và khi nào thực hiện phụ thuộc **khung pháp lý áp dụng**, không thể kết luận chỉ bằng tên công nghệ “AI”, “cloud” hoặc “analytics”.

Một PIA/DPIA tốt có thể gồm mục đích, sự cần thiết/tương xứng, data flow, các bên, rủi ro đối với con người, biện pháp giảm thiểu, tham vấn và residual risk. **Nó không tự thay kiểm thử runtime**; những biện pháp ghi trong đánh giá vẫn phải được triển khai và kiểm tra.

## 13. Risk owners và quyền quyết định

| Vai trò | Trách nhiệm điển hình |
|---|---|
| **Business/Product owner** | Mục tiêu, tính năng, giá trị, rủi ro đối với người dùng và các lựa chọn thiết kế |
| **Data owner** | Phạm vi dữ liệu, classification, mục đích được giao, retention và chia sẻ |
| **Privacy/Legal/DPO khi áp dụng** | Diễn giải nghĩa vụ, tư vấn đánh giá tác động, quy trình quyền cá nhân/incident, giám sát phù hợp |
| **Security/GRC/Assurance** | Phương pháp rủi ro, yêu cầu bảo mật, evidence standards, test/assessment, escalation |
| **Engineering/Architecture** | Data minimization, API/data flow, controls kỹ thuật, tests và remediation |
| **Data Science/Analytics** | Feature selection, mô hình, chất lượng/sai lệch dữ liệu, theo dõi tác động đầu ra |
| **Platform/Operations** | Access, cloud, logging, encryption, backup, retention execution |
| **Vendor/Procurement owner** | Due diligence, hợp đồng, subprocessor, data-sharing conditions và offboarding |
| **Risk owner/cấp được ủy quyền** | Quyết định xử lý và residual risk trong phạm vi thẩm quyền |
| **Independent reviewer/auditor** | Kiểm tra claim/evidence độc lập theo nhiệm vụ được giao |

**Không nên giao “mọi privacy risk” cho nhóm Legal một cách mặc định.** Product/Data phải chịu trách nhiệm về cách dữ liệu được sử dụng, Engineering phải thực thi controls và các bộ phận chuyên trách phối hợp đánh giá nghĩa vụ. Một lời xác nhận của Product “đây là mục đích có ích” không tự thay thế review về tác động lên cá nhân.

### 13.1. Chấp nhận rủi ro là quyết định có giới hạn

Risk owner có thể có thẩm quyền chấp nhận một **residual risk nội bộ** khi chính sách cho phép, với phạm vi, điều kiện, thời hạn và cơ chế theo dõi. Nhưng **acceptance không cho phép vi phạm nghĩa vụ bắt buộc hoặc biến một control failure thành pass**. Nếu một hoạt động xử lý không được phép theo điều kiện áp dụng, tổ chức phải thay đổi hoặc dừng hoạt động đó theo tư vấn và quyết định đúng thẩm quyền.

## 14. Từ privacy risk sang security và privacy requirements

### 14.1. Những yêu cầu phải kiểm chứng được

Một yêu cầu “tôn trọng quyền riêng tư” có giá trị định hướng nhưng chưa đủ để kiểm thử. Nên nêu rõ:

- Dữ liệu nào thuộc scope và vì sao được xử lý?
- Ai được truy cập hoặc nhận kết quả, theo vai trò và mục đích nào?
- Mức độ chi tiết, tần suất, thời gian lưu tối đa và các trường bị loại?
- Có cơ chế thông báo/lựa chọn/yêu cầu xử lý nào áp dụng?
- Khi dữ liệu sai, đã bị xóa, đã rút lựa chọn hoặc account chấm dứt thì hệ thống làm gì?
- Có những đường **bulk export, logs, backups, analytics, vendor** cần kiểm soát không?
- Phép test cụ thể và bằng chứng runtime nào chứng minh đã đạt?

### 14.2. Ma trận risk → requirement

| Privacy risk | Requirement có thể kiểm tra | Control owner | Verification |
|---|---|---|---|
| Tracking vượt mục đích | Chỉ phát sự kiện trong danh mục được duyệt, không chứa trường không cần thiết | Product + Frontend/Data | Event-schema/payload inspection, SDK/network tests |
| Liên kết hồ sơ không cần thiết | Dữ liệu nguồn khác nhau chỉ được join theo mục đích/khóa được phê duyệt | Data Engineering | Query review, lineage, permission tests |
| Dữ liệu cá nhân lộ qua API | Object/tenant/field-level authorization trên mọi đường export | Backend | Negative tests, worker/file traces |
| Dự đoán sai gây quyết định bất lợi | Quy trình xem xét giới hạn mô hình, độ chính xác, quyền phản hồi/sửa sai khi áp dụng | Product + Data Science | Validation report, workflow test, review logs |
| Người dùng không biết scope xử lý | Thông tin và tương tác hiển thị đúng bản đang chạy, theo yêu cầu áp dụng | Product + Privacy | Notice/version mapping, UI tests |
| Lựa chọn của người dùng không được thực thi | Preference cập nhật và ngừng hoạt động thuộc scope theo policy | App/Data | Choice-to-actual-data-flow test |
| Dữ liệu quá hạn còn sử dụng | Retention/deletion có phạm vi tới primary, cache, warehouse, vendor theo chính sách | Operations + Vendor owner | Job records, spot checks, exception review |
| Tái nhận dạng từ nhóm nhỏ | Quy tắc công bố tổng hợp có ngưỡng và đánh giá rủi ro cụ thể | Analytics | Aggregation/edge tests, inference review |
| Chia sẻ ngoài mục đích vendor | Contract/data flow/permission chỉ cho phép dataset cần thiết | Vendor owner + Backend | Data mapping, token scope, payload test |
| Không thể điều tra tác động | Audit events đủ, log health được kiểm tra, không lưu PII quá mức | SecOps | Synthetic event, pipeline health, incident drills |

Đây là các **ví dụ control nội bộ**, không mặc định có hiệu lực của một tiêu chuẩn pháp luật ở mọi nơi. Từng yêu cầu cần tiêu chí, ngưỡng, người phê duyệt và tần suất theo risk/context.

## 15. Privacy by design và privacy by default

### 15.1. Privacy by design

**Privacy by design** là đưa privacy requirements vào giai đoạn xác định nhu cầu, thiết kế, dữ liệu, giao diện, kiểm thử và vận hành; tránh xử lý privacy như một tài liệu duyệt sau khi hệ thống đã triển khai rộng.

Ví dụ trước khi thêm analytics SDK:

- Data owner xác định mục đích và loại sự kiện cần thiết.
- Product xem liệu dữ liệu tổng hợp đủ đạt mục tiêu hay phải theo dõi cá nhân.
- Privacy/Legal xem nghĩa vụ và kỳ vọng của người học trong bối cảnh.
- Engineering quyết định schema, quyền, biến đổi và loại trừ PII.
- QA/Security Assurance xây event tests và evidence collection.
- Vendor owner đánh giá bên nhận, retention và subprocessor.
- Release governance kiểm tra thay đổi đã có phê duyệt và test phù hợp.

### 15.2. Privacy by default

**Privacy by default** hướng tới cấu hình mặc định giảm rủi ro và không xử lý/chia sẻ quá mức khi người dùng chưa chủ động lựa chọn hoặc không có điều kiện phù hợp khác. Ví dụ:

- Không công khai tiến độ/điểm của học viên cho người dùng khác mặc định.
- Không bật những trường tracking không cần cho chức năng cơ bản.
- Không cấp quyền export hàng loạt cho mọi người có role TEACHER.
- Không giữ file export không giới hạn mà không có mục đích.
- Không tự chia sẻ profile chi tiết với vendor chỉ vì tích hợp đã kết nối.

Điều kiện cụ thể cho mặc định, lựa chọn và thông báo phải theo **policy, hợp đồng và pháp luật áp dụng**; không phải mọi hoạt động xử lý đều có cùng cơ chế consent hoặc opt-out. Đặc biệt, không nên coi một checkbox là bằng chứng mọi nghĩa vụ privacy đã được đáp ứng.

## 16. Data minimization: giảm rủi ro ngay từ thiết kế

### 16.1. Ba câu hỏi về tính cần thiết

**Data minimization** yêu cầu xét liệu loại dữ liệu, độ chi tiết và số lượng thông tin xử lý có thật sự cần cho mục đích xác định hay không.

1. **Cần thu thập không?** Nếu chỉ đo số học viên hoàn thành bài, có cần ghi từng giây xem video hoặc nội dung tin nhắn không?
2. **Cần gắn danh tính không?** Nếu chỉ xem tỷ lệ hoàn thành, có cần gửi learnerId hoặc email thật cho đối tác không?
3. **Cần giữ và chia sẻ bao lâu?** Có thể tính toán tại nguồn, gửi số tổng hợp thay vì raw events và xóa sự kiện sớm hơn không?

Lập luận “thu hết vì lưu trữ rẻ và sau này có thể dùng” **không thay thế mục đích đã được phê duyệt**. Dữ liệu tồn đọng làm tăng khả năng bị liên kết, tái sử dụng, lộ hoặc dùng sai bối cảnh.

### 16.2. Giảm dữ liệu ở mọi điểm xử lý

| Vị trí | Cách giảm rủi ro | Bằng chứng cần kiểm tra |
|---|---|---|
| **Frontend/SDK** | Không thu event/field ngoài danh mục mục đích | Network payload, SDK config, schema tests |
| **API** | Dùng allowlist DTO, kiểm tra role/tenant và field | Response/request tests, authorization |
| **ETL** | Loại trường thừa trước khi sao chép hoặc xuất | Transform version, lineage, output compare |
| **Analytics** | Dùng mức tổng hợp thay vì cá nhân khi đủ mục đích | Query review, group-size/inference test |
| **Vendor API** | Gửi tập nhỏ nhất, giới hạn scope và thời gian | Token permissions, data contract, actual payload |
| **Logs** | Truy vết hoạt động mà không lưu nội dung bài làm, secret | Synthetic event, log inspection |
| **Backup/archive** | Áp dụng phạm vi và kỳ lưu phù hợp | Backup inventory, retention/test |
| **ML/features** | Chọn thuộc tính phục vụ mục tiêu, review suy luận | Feature registry, model review, version |

### 16.3. Minimization không đồng nghĩa xóa mọi log

Để có security assurance, tổ chức vẫn có thể cần lưu event metadata giúp điều tra truy cập và thực thi policy. Ví dụ log export có thể ghi actor ID, tenant, dataset ID, quyết định, request ID, thời điểm, outcome; không cần ghi bảng điểm thật hoặc bearer token.

Mục tiêu là **đủ để truy vết và phát hiện nhưng không tạo thêm kho dữ liệu nhạy cảm**. Privacy và Security nên cùng kiểm tra cả tính hữu ích của telemetry lẫn nguy cơ ghi quá mức.

## 17. Transparency, user expectations và lựa chọn

### 17.1. Thông báo có ý nghĩa

Một liên kết tới văn bản Privacy Policy rất dài không tự chứng minh người dùng có thể **hiểu hoạt động xử lý đang ảnh hưởng tới mình**. Cần xét:

- Mục đích xử lý được diễn đạt đúng với chức năng và data flow thật không?
- Loại dữ liệu, mức suy luận, người nhận và giới hạn sử dụng có được mô tả phù hợp?
- Thông tin có xuất hiện ở thời điểm người dùng cần hiểu, theo nghĩa vụ áp dụng?
- Tính năng mới đã được phản ánh vào notice/version đúng release chưa?
- Người dùng có kênh đặt câu hỏi hoặc thực hiện những quyền/yêu cầu hợp lệ theo quy trình không?
- Giao diện có làm người dùng hiểu sai mức độ giám sát hoặc cách chia sẻ không?

### 17.2. Không đồng nhất mọi xử lý với consent

Các khung pháp luật có thể quy định **những cơ sở hoặc điều kiện xử lý khác nhau**. Không phải hoạt động nào cũng dựa trên một checkbox đồng ý; lựa chọn cơ chế phù hợp thuộc phạm vi Privacy/Legal theo luật, hợp đồng và bối cảnh áp dụng.

Tuy nhiên, nếu sản phẩm cung cấp cơ chế lựa chọn hoặc rút lại đối với một hoạt động xác định, **hệ thống phải thực thi trạng thái đó thật**. Chẳng hạn preference báo “off” nhưng SDK vẫn gửi event thuộc loại phải dừng là sai lệch control, dù UI đã đổi màu.

### 17.3. Kiểm chứng giao diện và data flow

Một privacy assurance test có thể:

1. Ghi phiên bản notice/choice tương ứng với bản phát hành.
2. Cho người dùng giả lập thay lựa chọn trong môi trường kiểm soát.
3. Quan sát browser/mobile SDK, API, queue, warehouse và vendor theo scope.
4. Đối chiếu event loại nào phải ngừng, loại nào có điều kiện xử lý riêng.
5. Kiểm tra propagation, retry và trường hợp sử dụng nhiều thiết bị.
6. Lưu expected/actual và giới hạn, không chỉ screenshot trang cài đặt.

Thiết kế giao diện có thể chứa **dark patterns**: gây khó khi từ chối, dùng từ ngữ mơ hồ hoặc che tác động. UX/Product/Privacy cần đánh giá khả năng hiểu và lựa chọn thực tế, không chỉ tồn tại một nút bấm.

## 18. Accuracy, profiling và quyết định ảnh hưởng cá nhân

### 18.1. Rủi ro khi dữ liệu đúng kỹ thuật nhưng sai ngữ cảnh

Một hệ thống có MFA, mã hóa và access control tốt vẫn có thể gây hại nếu mô hình dự đoán dựa trên dữ liệu thiếu hoặc người sử dụng hiểu kết quả như sự thật chắc chắn.

Ví dụ học viên xem video offline nên telemetry thiếu. Mô hình nhận định “không tham gia học” và dashboard hiển thị nhãn “nguy cơ bỏ học cao”. Tư vấn viên dùng nhãn này để đánh giá học viên thiếu nỗ lực. Privacy risk nằm ở **độ chính xác, bối cảnh sử dụng và hậu quả của kết luận**.

### 18.2. Câu hỏi cho profiling

- Dự đoán có ảnh hưởng tới cơ hội, cách đối xử hoặc quyền lợi của người học không?
- Có missing data hoặc nhóm hành vi chưa được phản ánh đúng không?
- Mục đích và giới hạn của mô hình có được mô tả rõ cho người sử dụng output không?
- Một chỉ số có bị dùng như sự thật thay vì tín hiệu cần xem xét?
- Có yêu cầu review bởi con người, giải thích hoặc sửa dữ liệu khi phù hợp?
- Model, features hoặc recipient thay đổi có kích hoạt đánh giá privacy mới?
- Có dấu hiệu tác động khác nhau giữa các nhóm mà cần đánh giá một cách hợp lệ không?

### 18.3. Các controls và evidence

| Risk | Control | Evidence |
|---|---|---|
| Dữ liệu đầu vào thiếu/sai | Data quality và coverage checks | Quality report, validation tests |
| Dự đoán bị sử dụng quá mức | Policy giới hạn mục đích và review workflow | Workflow review, decision records |
| Nhãn cá nhân hiển thị rộng | Role/object/tenant/purpose access | Effective permissions, negative tests |
| Không có cách sửa dữ liệu nguồn | Correction/request process theo điều kiện áp dụng | Test request và audit trail |
| Nhãn giữ quá lâu | Retention/deletion và lineage | Data map, deletion tests |
| Thêm feature nhạy cảm không review | Change gate và feature registry | Approval, diff, model review |

Không suy ra “không có tác động privacy” từ một chỉ số accuracy tổng thể cao. Cần xem **mức độ nghiêm trọng của trường hợp mô hình sai**, mục đích và người chịu ảnh hưởng.

## 19. Retention, deletion và giới hạn tái sử dụng

### 19.1. Retention gắn với mục đích

Một retention schedule cần mô tả **dữ liệu gì, tại sao giữ, giữ bao lâu, ở đâu, ai phê duyệt, làm gì khi hết kỳ và ngoại lệ nào được phép**. Các mốc cụ thể phải dựa trên nhu cầu và nghĩa vụ áp dụng, không có số ngày mặc định cho mọi dataset.

Dữ liệu quá hạn có thể tồn tại trong primary DB, cache, log, object storage, analytics warehouse, feature store, backup, file export hoặc vendor/subprocessor. Thiếu data lineage làm khó phát hiện những bản sao đó.

### 19.2. Deletion khác deactivation

Ngừng hiển thị profile hoặc disable account **không mặc nhiên** xóa mọi bản sao hoặc thu hồi mọi chia sẻ trước đây. Ngược lại, có dữ liệu phải giữ theo nghĩa vụ hợp lệ trong một kỳ, với quyền truy cập và mục đích giới hạn.

Nên tách:

- **Request được phép:** xác minh người yêu cầu và phạm vi dữ liệu.
- **Execution:** xác định hệ thống nguồn/đích và thực hiện theo quy tắc.
- **Exceptions:** dữ liệu cần giữ, backup theo chu kỳ, legal hold hoặc giới hạn kỹ thuật hợp lệ.
- **Verification:** đối chiếu hành động, downstream acknowledgments và kiểm tra trạng thái.
- **Communication/record:** báo kết quả và phần chưa hoàn tất theo quy trình, bảo vệ hồ sơ yêu cầu.

### 19.3. Bằng chứng xóa dữ liệu

Một record có thể liên kết **request ID → subject mapping → datasets → primary/warehouse/vendor targets → results → exceptions → reviewer**. Nếu vendor không phản hồi hoặc job báo lỗi, không tự gắn kết quả thành “đã xóa mọi dữ liệu”; phải mở evidence gap/finding tùy tiêu chí, retry và escalation.

## 20. Privacy-enhancing controls và giới hạn

| Kỹ thuật/biện pháp | Giúp giảm rủi ro | Giới hạn |
|---|---|---|
| **Access control** | Hạn chế người hoặc service truy cập ngoài quyền | Người được phép vẫn có thể dùng sai mục đích |
| **Encryption** | Giảm phơi bày khi dữ liệu lưu/truyền bị truy cập ngoài ý muốn | Người có quyền giải mã vẫn đọc được; không sửa purpose |
| **Data minimization** | Giảm khối lượng và chi tiết dữ liệu | Cần kiểm tra mọi nguồn/đích |
| **Pseudonymization** | Giảm lộ định danh trực tiếp | Có thể tái liên kết; mapping cần bảo vệ |
| **Aggregation** | Tránh báo cáo mức cá nhân khi đủ mục tiêu | Nhóm nhỏ và filter có thể tiết lộ người |
| **Differential privacy (khi thích hợp)** | Giới hạn một số rủi ro suy luận thống kê theo mô hình hình thức | Cần chọn tham số/budget, threat model và kiểm chứng; không là giải pháp mọi trường hợp |
| **Purpose-based controls** | Giới hạn sử dụng ngoài mục tiêu | Cần enforcement và audit |
| **Transparency/choice workflows** | Cải thiện khả năng nhận biết, lựa chọn, sửa sai khi áp dụng | UI không đủ nếu pipeline không thực thi |
| **Retention/deletion** | Giảm thời gian/bản sao có thể bị dùng lại | Không đảo ngược hậu quả đã phát sinh |
| **Data accuracy/human review** | Giảm sai lệch hoặc dùng nhãn sai ngữ cảnh | Đánh giá vẫn có thể thiếu coverage |
| **Vendor governance** | Giảm rủi ro chia sẻ/giữ dữ liệu ở bên thứ ba | Hợp đồng/chứng nhận chưa chứng minh runtime |
| **Monitoring/incident response** | Phát hiện, giới hạn tác động khi có sai lệch | Phát hiện muộn không tự sửa harm |

### 20.1. Tại sao mã hóa không đủ?

Một database có thể được mã hóa hoàn chỉnh nhưng Product vẫn cho phép nhân viên không có nhiệm vụ tư vấn xem các nhãn tâm lý suy luận về học viên. Dữ liệu được truy cập qua quyền hợp lệ kỹ thuật nhưng xử lý vượt mục đích. Encryption không giải quyết vấn đề đó; cần giới hạn mục đích, role, field-level controls, minimization và review.

### 20.2. Kiểm chứng pseudonymization

Khi thay email bằng mã giả, cần hỏi:

- Bảng mapping hoặc khóa liên kết ở đâu, ai được truy cập?
- Mã có dễ đoán hoặc đảo ngược bằng dữ liệu phổ biến không?
- Course, timestamp và event pattern có đủ để nhận diện không?
- Vendor có dữ liệu phụ trợ hoặc khả năng join không?
- Dữ liệu dẫn xuất có được gắn lại learnerId ở bước sau không?
- Chính sách retention/deletion có áp dụng tới các bản dẫn xuất không?

Không được tuyên bố “ẩn danh” từ việc bỏ tên. Kết luận nên mô tả **thuộc tính rủi ro được giảm và những khả năng còn tồn tại**.

## 21. Privacy risk từ nhà cung cấp và bên thứ tư

### 21.1. Cần kiểm tra toàn bộ data-sharing relationship

Một vendor SaaS có chứng nhận vẫn có thể nhận dữ liệu vượt mục đích nếu bên mua cấp OAuth scope quá rộng hoặc gửi toàn bộ entity qua API.

Các câu hỏi quan trọng:

1. **Purpose:** vendor xử lý để làm gì; có tự sử dụng để phát triển sản phẩm/đào tạo mô hình không?
2. **Data:** trường, khối lượng, tần suất, khả năng liên kết và nhạy cảm.
3. **Location:** nơi lưu/xử lý và nghĩa vụ chuyển dữ liệu khi áp dụng.
4. **Subprocessors:** những bên nào được tiếp cận dữ liệu, cơ chế thay đổi và flow-down requirements.
5. **Controls:** authorization, tenant isolation, encryption, logging, minimization.
6. **Retention/deletion:** thời hạn, bản sao và phương pháp xử lý khi kết thúc.
7. **Incident:** kênh liên hệ, điều kiện thông báo và phối hợp theo hợp đồng/nghĩa vụ.
8. **Rights/requests:** cách hỗ trợ những yêu cầu của người có dữ liệu trong phạm vi áp dụng.
9. **Assurance evidence:** scope, kỳ, ngoại lệ của báo cáo, phần trách nhiệm bên mua.
10. **Exit:** cách ngắt dữ liệu, thu hồi token, hoàn trả và kiểm chứng xóa/giữ.

### 21.2. Shared responsibility

| Lĩnh vực | Bên mua thường làm | Vendor thường làm theo điều khoản |
|---|---|---|
| Mục đích và dữ liệu gửi | Quyết định necessity/scope, cấu hình API và quyền | Chỉ xử lý trong mục đích/thỏa thuận phù hợp |
| Credential/tích hợp | Bảo vệ token, scope, job, network | Bảo vệ endpoint, hạ tầng và control phía vendor |
| User access | Cấu hình tenant và quyền bên mua | Quản lý quyền hỗ trợ, isolation và dịch vụ phía vendor |
| Retention/deletion | Xác định mục tiêu, yêu cầu, đối chiếu | Thực hiện xử lý/trả/xóa theo nghĩa vụ |
| Incident | Xác định tác động, đối tượng bị ảnh hưởng | Thông báo và hợp tác theo thỏa thuận |
| Assurance | Kiểm tra payload/config phía bên mua | Cung cấp bằng chứng trong phần trách nhiệm vendor |

Bảng chỉ mô tả mô hình thường gặp. **Vai trò pháp lý và ranh giới thực phải được xác định theo dịch vụ, hợp đồng và quy định áp dụng**. Báo cáo kiểm toán của vendor không thay kiểm thử luồng dữ liệu mà ứng dụng tự gửi.

## 22. Risk register: lưu kịch bản và căn cứ quyết định

### 22.1. Các trường cần có

Một privacy risk record nên ghi **risk ID, processing purpose, datasets, affected people, recipients, event, causes, path to harm, likelihood, severity, uncertainty, existing controls, evidence, treatment, owner, residual risk, findings, review triggers**.

### 22.2. Ví dụ YAML

Đây là **mẫu quản trị nội bộ**, không phải kết quả kiểm toán thực tế hay biểu mẫu pháp lý bắt buộc.

~~~yaml
risk_id: PRIV-LEARN-001
title: "Nhãn nguy cơ bỏ học hiển thị ngoài nhóm hỗ trợ"
system: "Learning Analytics"
processing:
  purpose: "Hỗ trợ học viên gặp khó khăn"
  datasets: ["learning-events", "progress-summary"]
  derived_data: "dropout-risk-label"
  recipients: ["approved-counselors", "analytics-provider"]
affected_people:
  groups: ["learners-in-scope"]
privacy_event: >
  Nhãn dự đoán bị xem hoặc dùng ngoài mục đích tư vấn,
  hoặc bị coi là kết luận chắc chắn.
possible_harms:
  - "Đánh giá bất lợi do suy luận sai"
  - "Mất kiểm soát thông tin học tập"
  - "Kỳ thị hoặc ảnh hưởng cơ hội"
inherent_risk:
  likelihood: "Pending assessment"
  severity: "Pending assessment"
  uncertainty: "Chưa có dữ liệu đủ về recipients và cách sử dụng"
required_controls:
  - id: PRIV-CTRL-01
    owner: "Product and Backend"
    statement: "Role/purpose restriction for individual labels"
  - id: PRIV-CTRL-02
    owner: "Data Science and Product"
    statement: "Model limitations and review process"
  - id: PRIV-CTRL-03
    owner: "Data Owner"
    statement: "Approve purpose, retention and sharing scope"
evidence_expected:
  - "Access policy and negative tests"
  - "Model validation and review records"
  - "Data flow, notice and retention verification"
  - "Vendor scope and export payload tests"
assessment:
  status: "Insufficient evidence until reviewed"
  limitations: ["No inference on unknown recipients"]
residual_risk:
  level: "Pending control effectiveness assessment"
  authority: "Authorized risk owner"
actions:
  - "Inventory recipients and export paths"
  - "Run role, tenant and data-minimization tests"
review_triggers:
  - "New feature, vendor, recipient or purpose"
  - "Complaint, incident or control finding"
~~~

Không sao chép trạng thái placeholder thành “Pass”. Khi triển khai thật phải nối ID với data catalog, risk register, test report và quyết định có bằng chứng.

## 23. Privacy assurance: từ rủi ro đến claim có bằng chứng

### 23.1. Risk assessment khác assurance

**Privacy risk assessment** tìm và đánh giá khả năng các hoạt động xử lý gây ảnh hưởng. **Privacy assurance** xác minh yêu cầu/controls đã thiết kế có **được thực hiện và duy trì hiệu quả trong scope** hay không.

Một bản PIA được ký có thể chứng minh đã diễn ra quá trình thẩm định; nó **không tự chứng minh** SDK đã ngừng gửi trường không cần thiết, nhãn mô hình chỉ tới đúng người hoặc vendor đã xử lý deletion.

### 23.2. Claim–Argument–Evidence

**Claim:**

> Trong phạm vi pipeline phân tích tiến độ production đã xác định, dữ liệu được thu thập và chia sẻ theo danh mục được duyệt; nhãn dự đoán cấp cá nhân chỉ hiển thị cho vai trò có nhiệm vụ, còn retention và dữ liệu bên nhận được quản lý theo yêu cầu trong kỳ đánh giá.

**Argument:**

1. Data Owner/Product/Privacy đã xác định mục đích, loại dữ liệu và các đối tượng nhận.
2. Event/schema allowlist được thi hành tại SDK, API và ETL.
3. Role/tenant/object/purpose restrictions bảo vệ nhãn ở dashboard, API và export.
4. Model output có giới hạn sử dụng và cách đánh giá độ chính xác/sửa lỗi.
5. Vendor scope và retention/deletion được kiểm soát qua các đường liên quan.
6. Controls được kiểm thử, theo dõi và bất thường được ghi, xử lý, retest.

**Evidence:**

- Data map, purpose review, threat/privacy assessment.
- Event catalog, capture tests của web/mobile SDK, backend schema tests.
- Effective permissions, negative tests cho dashboard, API, export.
- Model validation và user/support review workflows.
- Vendor contract, token scopes, actual payload.
- Retention/deletion evidence, backup/vendor exception.
- Log health, change records, complaints/findings/retest.
- Reviewer conclusion có scope, period, provenance và limitations.

### 23.3. Phân biệt ba lớp effectiveness

| Lớp | Câu hỏi | Evidence | Không tự suy ra |
|---|---|---|---|
| **Design** | Requirements được thiết kế để giảm đúng harms? | Data flow, risk assessment, policy, architecture review | Chưa chắc đã triển khai |
| **Implementation** | Controls có trên bản và các đường xử lý đang xét? | SDK/API config, payload tests, IAM/retention rules | Chưa chắc hoạt động suốt kỳ |
| **Operating** | Controls tiếp tục hoạt động qua release, yêu cầu người dùng, vendor changes? | Access/deletion/choice history, periodic tests, monitoring | Không chứng minh ngoài scope và kỳ |

Nếu bản mobile cũ chưa được kiểm tra, kết luận không nên bao phủ nó. Nếu vendor retention chưa có evidence, phải ghi **insufficient evidence** cho phần liên quan, dù API nội bộ pass.

## 24. Evidence quality và tiêu chí chấp nhận

| Thuộc tính | Câu hỏi | Ví dụ chưa đạt |
|---|---|---|
| **Relevance** | Artifact chứng minh claim về mục đích, dữ liệu, quyền hay retention nào? | Báo cáo TLS để chứng minh purpose limitation |
| **Scope** | Đã xét web, mobile, batch, tenant, vendor và môi trường cần thiết? | Chỉ kiểm tra staging |
| **Completeness** | Population, datasets và downstream có đầy đủ? | Bỏ logs, backups, feature store |
| **Freshness/period** | Evidence khớp release/kỳ đang kết luận? | Notice version cũ |
| **Provenance** | Nguồn, công cụ, người thu thập, time, query có rõ? | File không xác định nguồn |
| **Integrity** | Có thể đối chiếu bản gốc và phát hiện sửa trái phép? | Bảng Excel bị chỉnh không lịch sử |
| **Reliability** | Tool/collector có hoạt động và đúng scope? | SDK monitor ngừng nhưng dashboard xanh |
| **Representativeness** | Samples có bao phủ nhóm và các đường rủi ro? | Chọn toàn user đã opt-in |
| **Repeatability** | Reviewer khác có thể kiểm tra lại cách thực hiện? | “Đã xem bằng mắt” không có method |
| **Confidentiality** | Evidence có làm lộ thêm PII hoặc secret? | Đính kèm raw learner profiles vào ticket mở |

### 24.1. Metadata tối thiểu

- Evidence ID, risk/requirement/control/claim IDs.
- Purpose, dataset, affected people, recipients trong scope.
- Environment, tenant, app/SDK/vendor version và build/deployment.
- Data-flow path, systems được kiểm tra.
- Event time, collection time, assessment period, timezone khi cần.
- Method, fixtures, samples, population, tool/query/version.
- Expected/actual, limits, errors, exceptions.
- Control owner, evidence producer, reviewer.
- Nơi bảo quản, classification, retention, integrity/provenance.
- Finding/remediation/retest và trigger đánh giá lại.

Tự động hóa thu thập metadata là hữu ích nhưng pipeline evidence cần kiểm tra **độ phủ, độ tin cậy và tình trạng hoạt động**.

## 25. Ma trận kiểm thử privacy controls

| Test ID | Requirement | Test/inspection | Kỳ vọng |
|---|---|---|---|
| PR-T01 | Chỉ thu event được duyệt | Quan sát web/mobile network và SDK | Không gửi trường/event ngoài allowlist |
| PR-T02 | Không ghi nội dung bài làm vào analytics | Submit fixture chứa trường nhạy cảm | Payload/log không lộ nội dung không cần |
| PR-T03 | Nhãn dự đoán chỉ người có nhiệm vụ xem | Counselor và actor thường gọi API | Role/object/tenant restriction đúng |
| PR-T04 | Vendor chỉ nhận dữ liệu đã duyệt | So payload và data contract | Không có trường ngoài scope |
| PR-T05 | Không join nguồn trái purpose | Thử query không được phép | Data policy/enforcement từ chối |
| PR-T06 | Lựa chọn được thực thi | Đổi preference rồi quan sát SDK/queue | Ngừng/điều chỉnh đúng data flow thuộc scope |
| PR-T07 | Thông báo khớp xử lý | Đối chiếu notice, release và data map | Mục đích/recipient phù hợp thực tế |
| PR-T08 | Retention thực thi | Tạo fixture hết hạn và chạy job | Xóa/giữ theo policy, có log |
| PR-T09 | Yêu cầu xử lý qua downstream | Thử workflow hợp lệ | Target ack, xử lý hoặc exception đúng |
| PR-T10 | Dashboard tránh nhóm quá nhỏ | Query và filter edge cases | Hạn chế suy luận theo tiêu chí |
| PR-T11 | Model output không bị lạm dụng | Dùng nhãn ngoài workflow được phép | Bị chặn hoặc review theo thiết kế |
| PR-T12 | Data correction hoạt động | Gửi yêu cầu sửa thông tin theo scope | Được tiếp nhận/xử lý/truy vết |
| PR-T13 | Exit vendor dừng truyền dữ liệu | Revoke token, thử scheduled job | Không còn gửi dữ liệu mới |
| PR-T14 | Logging hữu ích mà không lộ PII | Tạo synthetic event | Có audit cần thiết, không raw secret/PII |
| PR-T15 | SDK change kích hoạt review | Thêm test field bị cấm | Gate/assessment phát hiện thay đổi |
| PR-T16 | Evidence health có kiểm tra | Tắt collector trong test | Báo lỗi thay vì pass giả |
| PR-T17 | User đã mất quyền không truy cập nhãn | Revoke rồi gọi API session cũ | Hành vi theo policy và thời hạn phù hợp |
| PR-T18 | Feature store không bị bỏ quên | Review lineage sau deletion event | Dẫn xuất xử lý hoặc có lý do ngoại lệ |

### 25.1. Giới hạn test và lấy mẫu

Một HTTP 403 chưa chứng minh worker không xuất file; một deletion status Success chưa chứng minh backups/vendor đã xử lý; một event-schema test chỉ hỗ trợ bản SDK được kiểm tra. Vì vậy evidence cần **fixtures, method, version, build, environment, scope, side effects và expected/actual**.

Với tác động từ mô hình hoặc choice workflow, mẫu chỉ gồm người dùng thường xuyên có thể bỏ sót nhóm dùng thiết bị cũ hoặc có dữ liệu thiếu. Sampling phải có **population và giả định**, không được suy rộng toàn bộ khi chưa đủ độ phủ. Không có tỷ lệ mẫu cố định đúng cho mọi risk assessment.

## 26. Ví dụ Java: giảm dữ liệu xuất sang analytics

### 26.1. Anti-pattern: gửi toàn bộ entity

Một sai lầm phổ biến là chuyển nguyên entity học viên sang vendor để tránh phải chọn field:

~~~java
// Anti-pattern: gửi toàn bộ entity chứa dữ liệu cá nhân.
analyticsClient.send(learnerEntity);
~~~

Nếu model bổ sung email, số điện thoại hoặc ghi chú hỗ trợ ở phiên bản sau, vendor có thể nhận dữ liệu mới dù mục đích chỉ là thống kê tiến độ. Việc “API dùng HTTPS” không giải quyết **data minimization và purpose limitation**.

### 26.2. Phác thảo allowlist DTO và scope

Đoạn mã minh họa sau diễn đạt một cách thiết kế. Đây **không phải mẫu production đầy đủ** vì còn thiếu auth framework, transaction, outbox implementation, monitoring và các bước đánh giá luật/chính sách.

~~~java
public record ProgressAnalyticsEvent(
        String pseudonymousLearnerId,
        String courseId,
        int completedLessons,
        Instant observedAt
) {}

public void publishProgress(
        AuthenticatedPrincipal actor,
        long learnerId,
        long courseId) {

    // Quyết định phải dựa trên identity và quan hệ
    // được kiểm chứng ở phía server.
    if (!analyticsPolicy.canPublishProgress(
            actor, learnerId, courseId)) {
        throw new AccessDeniedException(
                "Analytics sharing not permitted");
    }

    var progress = progressService.findApprovedSummary(
            learnerId, courseId, actor.tenantId());

    // Chỉ dùng các trường đã được duyệt trong data contract.
    // Pseudonymization không đồng nghĩa anonymization.
    var event = new ProgressAnalyticsEvent(
            pseudonymService.forPurpose(
                    learnerId, "learning-progress"),
            progress.publicCourseId(),
            progress.completedLessons(),
            Instant.now()
    );

    analyticsOutbox.enqueue(event);
}
~~~

### 26.3. Những điều đoạn code chưa chứng minh

- **Necessity:** mục đích có thật sự cần pseudonymous learner ID và timestamp không?
- **Policy:** analyticsPolicy có kiểm tra mục đích/quyền từ nguồn được phê duyệt không?
- **Completeness:** còn đường frontend SDK, batch job hoặc logging nào gửi raw data không?
- **Linkability:** mã giả có dễ liên kết với tài khoản hoặc nguồn phụ trợ không?
- **Revocation/choice:** khi điều kiện dùng dữ liệu thay đổi, những event queued được xử lý thế nào?
- **Vendor:** API và đối tác có giới hạn đúng trường, scope, retention và downstream sharing?
- **Event time:** Instant.now có đúng ý nghĩa thời điểm cần ghi hay phải lấy nguồn event time đáng tin?
- **Monitoring:** những sai lệch data schema hoặc quyền có thể được phát hiện không?

Để kết luận privacy control hiệu quả, không thể chỉ code review một hàm. Cần xác nhận dữ liệu đã gửi ở **web, mobile, backend, outbox, worker, warehouse và vendor** trong phạm vi.

### 26.4. Pseudo-unit tests

~~~java
@Test
void analyticsPayloadUsesOnlyApprovedFields() {
    var event = fixtures.approvedProgressEvent();
    String json = analyticsSerializer.toJson(event);

    assertTrue(json.contains("completedLessons"));
    assertFalse(json.contains("email"));
    assertFalse(json.contains("phoneNumber"));
    assertFalse(json.contains("privateSupportNotes"));
}

@Test
void unrelatedActorCannotPublishLearnerData() {
    var outsider = fixtures.actorOutsideLearnerScope();
    var learner = fixtures.learnerInAnotherTenant();

    assertThrows(AccessDeniedException.class,
        () -> analyticsService.publishProgress(
            outsider, learner.id(), learner.courseId()));

    assertFalse(analyticsOutbox.hasEventFor(learner.id()));
}
~~~

Những tên fixture/service chỉ minh họa, không phải mã có thể chạy độc lập. Test kiểm tra vài từ khóa JSON không chứng minh schema đầy đủ; test trong production-grade pipeline cần so **field allowlist và payload thực**, kiểm tra side effects, log, build/deployment mapping và các trường hợp đổi schema.

## 27. Case study: dự đoán học viên cần hỗ trợ

### 27.1. Bối cảnh

Một nền tảng học trực tuyến muốn tìm sớm học viên có thể gặp khó khăn. Đội Product đề xuất:

1. Thu thời gian xem video, lịch làm bài, số lần nộp lại và kết quả kiểm tra.
2. Kết hợp dữ liệu lịch học và thông tin liên hệ.
3. Tạo một risk score/nhãn “cần hỗ trợ”.
4. Hiển thị nhãn trên dashboard của cố vấn học tập và một số giảng viên.
5. Chia sẻ dữ liệu sang vendor để cải thiện mô hình.
6. Giữ raw events nhiều năm để phục vụ sản phẩm tương lai.

Mục đích có thể tạo lợi ích thật, nhưng không tự chứng minh mọi trường, người nhận và cách sử dụng đều cần thiết.

### 27.2. Các risk scenarios

| Risk ID | Privacy event | Harm |
|---|---|---|
| PR-01 | Theo dõi học tập quá chi tiết | Cảm giác bị giám sát, mất tự chủ |
| PR-02 | Dữ liệu offline thiếu, score không chính xác | Học viên bị đánh giá bất lợi |
| PR-03 | Nhãn hiển thị cho người không có nhiệm vụ | Xấu hổ, kỳ thị, tiết lộ ngoài bối cảnh |
| PR-04 | Nhóm báo cáo quá nhỏ và bộ lọc chi tiết | Suy ra cá nhân hoặc thuộc tính của họ |
| PR-05 | Vendor nhận cả email và nội dung bài nộp | Rò rỉ/khai thác thứ cấp và quá mức |
| PR-06 | Raw events giữ vô thời hạn | Tăng rủi ro liên kết và tái sử dụng ngoài mục đích |
| PR-07 | Người học không biết nhãn, không thể sửa dữ liệu sai | Thiếu minh bạch và khả năng phản hồi |
| PR-08 | Events liên kết với nguồn bên ngoài | Profile sâu hơn kỳ vọng |
| PR-09 | Risk score trở thành căn cứ quyết định tự động | Ảnh hưởng cơ hội và đối xử thiếu công bằng |
| PR-10 | Deletion chỉ xóa DB, feature store giữ dữ liệu | Xử lý tiếp sau mốc được phép |

### 27.3. Đánh giá kỹ một kịch bản

**PR-03 — Nhãn cá nhân hiển thị quá rộng**

- **Data:** derived risk label gắn learner ID.
- **People:** người học trong scope, nhất là trường hợp bị suy luận sai và chịu hậu quả.
- **Event:** role TEACHER hoặc support rộng đọc nhãn ngoài mục đích tư vấn.
- **Cause:** dashboard role thô, API thiếu object/purpose condition, export chứa trường nhạy cảm.
- **Harm:** ảnh hưởng đánh giá, cơ hội, lòng tin và đời sống riêng.
- **Likelihood:** xem số actor thực sự có quyền, khối lượng truy cập, đường export và hiệu quả controls.
- **Severity:** xét tính khó đảo ngược của nhãn bị lan truyền, hậu quả trong quan hệ học tập, độ nhạy và độ tin cậy.
- **Controls:** role/object/purpose access, giới hạn trường, review mô hình, mục đích, logging và correction.
- **Evidence:** effective permissions, negative API tests, dashboard/export test, model limitations, review records.
- **Unknowns:** còn bao nhiêu recipients, vendor có lưu nhãn hoặc ghép nguồn không?

Không nên đánh giá “rủi ro thấp vì nhãn chỉ là một số” nếu con số đó có thể dẫn tới hậu quả đáng kể đối với học viên.

### 27.4. So sánh phương án thiết kế

| Phương án | Giá trị nghiệp vụ | Trade-off privacy | Điều cần xác minh |
|---|---|---|---|
| A. Thu raw events gắn định danh | Có nhiều tín hiệu phân tích | Theo dõi sâu, khả năng liên kết và retention cao | Necessity, use restrictions, access, model harms |
| B. Dùng chỉ số tổng hợp có thời hạn | Giảm phơi bày và dữ liệu thừa | Có thể mất một số tín hiệu | Hiệu quả mục đích và re-identification risk |
| C. Hiển thị gợi ý cho chính người học | Giảm chia sẻ kết quả suy luận cho nhân viên | Có thể giảm can thiệp chủ động | UX, understanding, privacy choice |
| D. Hạn chế nhãn cho counselor có review | Cân bằng hỗ trợ với bảo vệ | Vẫn giữ nhãn cấp cá nhân | Role/purpose access, validation, monitoring |
| E. Không triển khai hoặc trì hoãn | Loại bớt đường xử lý mới | Không đạt một phần mục tiêu hỗ trợ | Lựa chọn thay thế, risk decision |

Cần **đánh giá rủi ro và lợi ích thực tế**, không giả định phương án thu nhiều dữ liệu nhất là cần thiết chỉ vì mô hình có thể chính xác hơn.

### 27.5. Kế hoạch evidence

1. Xác nhận purpose, lawful/policy requirements theo đơn vị phụ trách.
2. Inventory events, features, raw and derived datasets, recipients và vendors.
3. Test actual data capture trên web/mobile, không chỉ dựa trên tài liệu SDK.
4. Kiểm tra minimization ở API, ETL, warehouse và vendor payload.
5. Negative tests cho role, tenant, object, field và bulk export.
6. Review validation và hậu quả mô hình sai, cùng quy trình cho người dùng phản hồi.
7. Test retention, correction, deletion qua feature store và bên nhận theo scope.
8. Kiểm tra logs/monitoring có ý nghĩa mà không thu thừa PII.
9. Liên kết bản triển khai với code/data contracts và approval của control owners.
10. Ghi limitations và mở finding khi có sai lệch.

### 27.6. Một kết luận assurance có giới hạn

> **Claim:** Các tuyến analytics được đánh giá chỉ gửi trường được duyệt; nhãn suy luận cá nhân chỉ hiển thị cho nhóm counselor có quyền theo policy.
>
> **Evidence:** event/schema tests, runtime access controls, design review và data map cho bản phát hành được xác định.
>
> **Giới hạn:** Mobile SDK cũ và retention của vendor chưa đủ bằng chứng; đánh giá không bao phủ những đường này.
>
> **Hành động:** kiểm tra SDK, nhận evidence từ vendor, cập nhật residual risk và reassess trước khi mở rộng.

Một kết luận có giới hạn như trên có giá trị hơn tuyên bố “100% private” không có phương pháp và scope rõ.

## 28. Incident, complaints và privacy harms thực tế

### 28.1. Privacy issue có thể bắt đầu ngoài SOC

Một số dấu hiệu phát sinh từ:

- Học viên phản ánh có người biết thông tin họ không mong muốn.
- Cố vấn phát hiện nhãn dự đoán sai và gây hậu quả.
- Yêu cầu sửa/xóa dữ liệu không được xử lý đúng.
- Product biết SDK thu thêm trường khi cập nhật.
- Vendor đổi subprocessor hoặc báo có sự cố.
- Data Engineering phát hiện dataset phái sinh còn lưu sau retention.
- Security phát hiện API truy cập chéo tenant.
- Auditor nhận thấy mục đích mới không được review.

Vì vậy cần **nhiều kênh phát hiện và tiếp nhận**, không chỉ vulnerability scans.

### 28.2. Quy trình phản ứng

1. **Triage:** ghi tín hiệu, loại dữ liệu, scope và người bị ảnh hưởng có thể.
2. **Preserve evidence:** bảo vệ log, config, schema, data flow; không sao chép PII quá mức.
3. **Contain:** tắt event, thu hồi token, hạn chế quyền, tạm dừng mô hình/dashboard nếu cần.
4. **Assess harms:** Product/Data Owner/Privacy/Security đánh giá bối cảnh, tác động và bất định.
5. **Review obligations:** Legal/Privacy xác định nghĩa vụ pháp lý, hợp đồng, thông báo và phối hợp khi áp dụng.
6. **Remediate:** sửa nguyên nhân, xử lý dữ liệu đã chuyển, cải thiện mục đích/choice/quality.
7. **Retest:** kiểm tra runtime, downstream và tác động ngoài dự kiến.
8. **Learn:** cập nhật requirements, risk register, tests, vendor controls và trigger.

Không có log ghi nhận truy cập **không chứng minh không xảy ra truy cập** khi log coverage chưa được xác minh. Có một vulnerability **không tự chứng minh dữ liệu thật đã bị lộ**. Kết luận phải trình bày điều đã biết và chưa biết.

## 29. Finding, evidence gap và residual risk

### 29.1. Phân loại trạng thái đánh giá

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| **Pass/Supported** | Control đáp ứng tiêu chí trong scope/kỳ, evidence hợp lệ | Không có event ngoài allowlist trong phiên bản kiểm thử |
| **Fail/Unsupported** | Có sai lệch được chứng minh | SDK gửi ghi chú riêng tư ngoài mục đích |
| **Insufficient evidence** | Thiếu dữ liệu hoặc coverage để kết luận | Vendor chưa có evidence xóa/subprocessor |
| **Not applicable** | Không liên quan tới scope có căn cứ | Không có chuyển vendor trong phạm vi đã xác minh |
| **Exception/risk acceptance** | Sai lệch nội bộ có quyết định điều kiện và thời hạn hợp lệ | Một đường legacy được giới hạn tạm trong thẩm quyền |

Một ngoại lệ/acceptance **không tự biến fail thành pass hoặc miễn nghĩa vụ bắt buộc**. Các quy tắc của chương trình audit hoặc khung pháp lý áp dụng phải được tuân thủ.

### 29.2. Ví dụ finding về SDK

**Finding:** Mobile SDK gửi trường support-note-text từ màn hình hỗ trợ tới analytics, trong khi data contract chỉ cho phép tiến độ.

**Evidence:** network payload với fixture, app/SDK version, schema, data map, expected/actual, timestamps. Không cần đưa ghi chú thật của học viên vào ticket.

**Privacy harm:** thông tin riêng tư được truyền tới vendor không đúng bối cảnh, có thể bị giữ hoặc dùng lại.

**Actions:** xác minh affected versions và data flow; tắt trường, vá SDK; điều tra dữ liệu đã gửi/đã giữ tại vendor; đánh giá nghĩa vụ; retest event capture, logs, queue và vendor API; cập nhật data map, risk, regression tests.

Nếu chưa biết thực tế vendor đã lưu hoặc sử dụng dữ liệu ra sao, phải báo **uncertainty**, không tự khẳng định mọi dữ liệu đã bị lộ hoặc hoàn toàn chưa ảnh hưởng.

### 29.3. Residual risk và giới hạn thẩm quyền

Một risk acceptance record cần **purpose, data, affected people, harms, likelihood/impact/uncertainty, controls và evidence, lựa chọn thay thế, thời hạn, giám sát, người có thẩm quyền, điều kiện pháp lý/chính sách và trigger review**.

Chi phí khắc phục cao không tự đủ để chấp nhận tác động nghiêm trọng lên con người. Không nên chỉ dựa trên thiệt hại tài chính của doanh nghiệp.

## 30. Continuous privacy assurance trong SDLC và vận hành

### 30.1. Triggers tái đánh giá

- Thêm event tracking, SDK, identifier hoặc trường dữ liệu.
- Dùng lại data cũ cho mục đích mới.
- Thêm API bulk export, báo cáo, dashboard hoặc quyền mới.
- Đổi model AI, features, độ chi tiết dữ liệu hoặc người xem output.
- Mở rộng nhóm người dùng, tenant, khu vực hoặc recipients.
- Đổi vendor, subprocessor, chính sách sharing hoặc vùng lưu dữ liệu.
- Thay retention, deletion workflow, backup hoặc nơi chứa dữ liệu dẫn xuất.
- Có incident, complaint, data quality issue hoặc privacy finding.
- Khung nghĩa vụ/hợp đồng có thay đổi liên quan.
- Evidence pipeline mất khả năng quan sát hoặc các control bị drift.

### 30.2. Đặt privacy vào vòng đời triển khai

| Giai đoạn | Hoạt động | Evidence |
|---|---|---|
| Discovery | Purpose, affected people, lựa chọn ít xâm phạm | Product decision, initial risk record |
| Architecture | Data flow, trust boundaries, data contracts, vendor review | DFD, schema, architecture review |
| Development | Minimization, safe logging, purpose checks | Code/schema review, tests |
| CI/CD | SDK payload checks, AuthZ, schema/drift tests | Test result theo build và artifact |
| Release | Review changes, notice/choice nếu áp dụng, residual risk | Approval, deployment mapping |
| Operations | Monitoring, access review, retention/deletion, vendor checks | Events, jobs, audit/review |
| Complaints/incidents | Assess harms, contain, correct và retest | Case record, affected datasets, action |
| Periodic assurance | Review evidence freshness, scope và findings | Assessment report, limitations |
| Decommission | Dừng processing, thu hồi và xử lý bản sao | Exit/retention/deletion records |

**Continuous assurance** không có nghĩa phải chạy mọi test mỗi phút. Tần suất theo độ biến động, tác động, nhu cầu và nghĩa vụ; trigger quan trọng cần kích hoạt lại đánh giá.

### 30.3. Health checks cho chính đường evidence

Một dashboard báo “không có dữ liệu ngoài scope” có thể sai nếu collector ngừng hoạt động. Cần:

- Xác minh các nguồn đã inventory đang gửi dữ liệu kiểm tra.
- Phát hiện output rỗng hoặc schema lỗi bất thường.
- Chạy synthetic disallowed-field tests theo môi trường kiểm soát.
- So version SDK/build với tập test hiện hành.
- Kiểm tra false negatives và data loss trong pipeline.
- Bảo vệ evidence chứa PII/secret và lịch sử thay đổi.
- Không kết luận Pass từ số 0 khi không chứng minh collector hoạt động.

## 31. Chỉ số đánh giá chương trình privacy risk

| Metric | Giá trị quản trị | Cách có thể hiểu sai |
|---|---|---|
| % processing activities có purpose/owner/data map | Độ phủ quản trị | Mẫu số bỏ shadow data |
| % high-impact processing được đánh giá | Độ phủ risk assessment | Hoàn thành form chưa chứng minh control |
| % privacy requirements có evidence hợp lệ | Mức assurance | Evidence cũ/sai scope vẫn có thể bị tính |
| Số privacy findings trọng yếu quá hạn | Rủi ro tồn đọng | Không kiểm tra thì cũng ít finding |
| % releases thay data có privacy review | Change governance | Đường deploy ngoài quy trình bị bỏ sót |
| % choice/deletion workflows test end-to-end | Khả năng thực thi quyền/lựa chọn | API success không nói về vendor/backup |
| % vendor data flows có scope/retention evidence | Độ rõ trách nhiệm và chia sẻ | Vendor report không chứng minh bên mua |
| Số datasets ngoài retention hoặc không owner | Data lifecycle hygiene | Discovery chưa đủ có thể báo ít |
| % fixes có retest đúng bản/môi trường | Chất lượng remediation | Ticket Done không thay test |
| Thời gian triage privacy complaint/incident | Năng lực phản ứng | Nhanh chưa chắc giảm harm |
| Số data minimization drift phát hiện | Phát hiện schema/SDK thay đổi | 0 drift khi scanner lỗi gây hiểu nhầm |
| % model changes có human-impact review | Độ phủ tác động suy luận | Review trên giấy không thay runtime |
| Số evidence gaps high risk quá hạn | Độ bất định cần xử lý | Không được coi gap như Pass |

Báo cáo lãnh đạo cần **privacy harms quan trọng, affected groups, scope, period, confidence, findings và residual risk**, thay vì một nhãn “100% privacy compliant” chỉ dựa trên số form hoàn tất.

## 32. Vai trò và RACI minh họa

R = thực hiện, A = chịu trách nhiệm cuối theo phân quyền, C = tham vấn, I = được thông báo.

| Hoạt động | Product/Data owner | Privacy/Legal | Engineering/Data | Security Assurance | Risk owner |
|---|---|---|---|---|---|
| Mục đích và dữ liệu cần thiết | A/R | C | C | C | I |
| Nhận diện harms và risk scenarios | R | A hoặc C theo tổ chức | R hỗ trợ | C | I |
| Xác định yêu cầu pháp lý | C | A/R | C | C | I |
| Thiết kế minimization/retention/choice | A về mục đích | C | R kỹ thuật | C | I |
| Triển khai controls API/SDK/pipeline | C | C | A/R | C | I |
| Thu thập evidence và thực hiện test | C | C | A/R phần kỹ thuật | C/review | I |
| Kết luận assurance | C | C | C | A/R hoặc assessor độc lập | I |
| Sửa failure và retest | A về tác động | C | A/R với phần kỹ thuật | R kiểm chứng | I |
| Chấp nhận residual risk nội bộ | C | C về điều kiện bắt buộc | C | C | A/R |
| Điều phối privacy incident/obligations | C | A/R theo quy trình | R cung cấp kỹ thuật | C | I |
| Giám sát và review | A về mục đích | C | R | A/R về chương trình | I |

Bảng là **minh họa**, không thay RACI của tổ chức. Cần người accountable rõ cho từng quyết định; **risk acceptance không thay legal review**, và người vận hành control không tự được coi là assessor độc lập.

## 33. Những sai lầm thường gặp

**“Privacy risk chỉ có khi hacker tấn công.”** Xử lý được phép vẫn có thể theo dõi quá mức, suy luận nhạy cảm hoặc gây đánh giá bất lợi.

**“Dữ liệu được mã hóa nên privacy đã được bảo đảm.”** Mã hóa không giải quyết purpose sai, role quá rộng hoặc nhãn dự đoán không chính xác.

**“Không có tên thì dữ liệu đã ẩn danh.”** Cần kiểm tra liên kết, tái nhận dạng và dữ liệu phụ trợ.

**“Một checkbox đồng ý là đủ cho mọi processing.”** Nghĩa vụ tùy bối cảnh; choice phải thật sự được thực thi nếu áp dụng.

**“Privacy Notice có trong web nghĩa mọi luồng dữ liệu đã minh bạch.”** Phải đối chiếu SDK, vendor, release và mục đích thật.

**“DPIA hoặc PIA được ký nghĩa hệ thống đạt.”** Tài liệu đánh giá không thay tests triển khai/vận hành.

**“Ít người bị ảnh hưởng tức rủi ro thấp.”** Một cá nhân có thể chịu tác động nghiêm trọng.

**“Analytics chỉ là thông tin kỹ thuật.”** Event, timestamp, device và hành vi có thể tạo profile rất chi tiết.

**“Nhãn do AI tạo không phải dữ liệu cá nhân.”** Nếu gắn/ảnh hưởng cá nhân, dữ liệu suy luận vẫn cần đánh giá theo ngữ cảnh.

**“Hash ID bảo đảm không thể nhận dạng.”** Hash có thể bị dò hoặc liên kết; phải đánh giá threat model.

**“Vendor có chứng chỉ nên được nhận mọi dữ liệu.”** Chứng nhận có scope, bên mua vẫn phải giới hạn việc gửi.

**“Đã xóa account là mọi bản sao đều biến mất.”** Cần kiểm tra warehouse, vendor, backup, log và ngoại lệ lưu giữ.

**“Không ai phàn nàn thì không có harm.”** Người bị ảnh hưởng có thể không biết hoặc không có khả năng khiếu nại.

**“Pass ở staging chứng minh production đạt.”** Cần version/build, config, paths và runtime evidence.

**“Thiếu bằng chứng tức chắc chắn control fail.”** Đây là trạng thái riêng nhưng cũng không được báo Pass.

**“Risk owner đã ký thì không cần theo dõi.”** Acceptance không xóa nghĩa vụ hoặc findings.

**“Chỉ Legal chịu trách nhiệm privacy.”** Product, Data, Engineering, Vendor, Security và quản trị đều có vai trò.

**“Thu thập và giữ dữ liệu nhiều nhất luôn có lợi.”** Dữ liệu quá mức làm tăng rủi ro và chi phí, đồng thời có thể vượt mục đích.

## 34. Bài tập thực hành

### Bài tập A — Privacy risk không cần security breach

Một ứng dụng có SSO, MFA và mã hóa tốt. Hệ thống theo dõi từng giây xem video, gửi phân tích cho cố vấn và dùng để gắn nhãn “thiếu tập trung”; học viên không hiểu cách xử lý.

Hãy:

1. Nêu ba privacy harms không cần hacker.
2. Phân biệt security controls có sẵn và privacy controls còn thiếu.
3. Xác định data flow, purposes, subjects, recipients và retention.
4. Đề xuất hai phương án thiết kế ít xâm phạm hơn.
5. Viết claim, test và evidence.
6. Nêu các nghĩa vụ cần Privacy/Legal kiểm tra.

**Gợi ý:** AuthN và encryption không chứng minh mức tracking và suy luận là phù hợp.

### Bài tập B — Privacy modeling với LINDDUN

Vendor nhận pseudonymous learner ID, courseId, timestamp và completion events, đồng thời có một nguồn dữ liệu khác về truy cập.

Hãy phân tích khả năng linkability, identifiability, detectability, disclosure và unawareness. Đề xuất data minimization, giới hạn thời gian, bảo vệ mapping, role, transparency và kiểm thử inference. Nêu assumptions và cách tránh tuyên bố “đã ẩn danh” thiếu căn cứ.

### Bài tập C — Risk register cho AI

Product muốn dự đoán khả năng bỏ học dựa trên điểm, số lần học, chat support và dữ liệu học phí; nhãn được gửi cho giảng viên và vendor.

Lập risk register có purpose, population, data types, harms, risk likelihood/severity/uncertainty, existing controls, missing evidence, treatment choices, owners, approval và reassessment triggers. Cân nhắc ít nhất hai phương án giảm dữ liệu hoặc hạn chế chia sẻ.

### Bài tập D — User choice end-to-end

Ứng dụng có nút tắt tracking tùy chọn. Người dùng chọn off, API trả đúng trạng thái, nhưng SDK vẫn gửi một số events sau đó.

Thiết kế test xác định event được phép/không phép theo policy, web/mobile, SDK, queue, retries, vendor, timing/consistency; ghi expected/actual và evidence. Nêu cách phân biệt analytics tùy chọn với event cần để bảo mật theo điều kiện áp dụng.

### Bài tập E — Deletion với dữ liệu dẫn xuất

Một yêu cầu xử lý dữ liệu hợp lệ làm primary DB xóa profile, nhưng warehouse còn feature vectors, vendor còn events và backup đang trong chu kỳ giữ.

Hãy mô tả workflow từ request tới downstream, phân biệt xóa/giữ hợp lệ, evidence trên từng target, exceptions, điều chưa được xác minh và cách báo trạng thái trung thực. Đặt owner và trigger kiểm tra lại.

### Bài tập F — Assurance report với findings và gaps

Một cuộc review giả định có:

- 40 processing activities trong inventory, chỉ 30 có owner/purpose được review.
- 15/20 hoạt động được đánh giá high impact đã có privacy assessment.
- Mobile SDK được chứng minh gửi trường ghi chú hỗ trợ ngoài scope.
- Vendor chưa cung cấp thông tin đủ về subprocessor và deletion.
- API production đều dùng TLS, nhưng web cũ chưa được kiểm tra payload.
- 12 negative access tests pass tại API mới.

Hãy phân loại **control failure, evidence gap, governance gap**, nêu privacy harms, đề xuất containment/remediation/retest và kết luận claim có scope/kỳ. Có được báo “100% privacy compliant” không? Ai phải duyệt residual risk và xem xét pháp lý?

### Bài tập G — Tổng hợp dữ liệu nhóm nhỏ

Dashboard công khai tỷ lệ hoàn thành theo lớp, trong đó có lớp một hoặc hai học viên. Bộ lọc có thể thay ngày và kết quả.

Hãy phân tích khả năng suy ra cá nhân bằng tổ hợp filters và nguồn bên ngoài; đề xuất aggregation controls, suppress nhóm nhỏ theo risk, test inference, data owner review và evidence cần có trước khi gọi dữ liệu “anonymous”.

### Bài tập H — Go/no-go với vendor AI

Vendor chào dịch vụ phân tích bài luận học viên. Báo cáo assurance của vendor chỉ bao phủ hạ tầng, chưa có đánh giá tính năng AI mới. Product muốn triển khai ngay.

Hãy phân tích scope report, data necessity, purpose, tác động mô hình, retention/subprocessor, quyền bên mua, các điều kiện hợp đồng/luật cần review, phép thử payload và quyền, khả năng triển khai giới hạn hoặc trì hoãn, cùng trách nhiệm các vai trò.

## 35. Checklist triển khai privacy risk assurance

Checklist dùng để kiểm tra **độ hoàn chỉnh của chương trình**, không tự chứng minh rằng mọi privacy risk đã được xử lý.

- [ ] Có purpose, scope, data subjects, affected groups, owner và processing context.
- [ ] Có data inventory/lineage cho việc thu, liên kết, suy luận, chia sẻ, lưu và xóa.
- [ ] SDK, API, logs, caches, backups, data lake và vendor thuộc data flow khi liên quan.
- [ ] Đã phân biệt privacy harms với information security/compliance/business risk.
- [ ] Đã xem harms ngay cả khi xử lý được cấp quyền kỹ thuật.
- [ ] Có phân tích linkability, inference, re-identification và dữ liệu dẫn xuất.
- [ ] Risk scenarios có causes, events, affected people, harms và uncertainty.
- [ ] Likelihood/severity có lập luận, không coi điểm số là sự thật tuyệt đối.
- [ ] Có xét necessity, proportionality và thiết kế ít xâm phạm hơn.
- [ ] Nghĩa vụ pháp luật, hợp đồng được review bởi bộ phận có thẩm quyền.
- [ ] Data minimization được test tại client, backend, ETL và vendor.
- [ ] Transparency/choice khi áp dụng được test với actual data flows.
- [ ] Có yêu cầu accuracy, profiling, human-impact review và correction phù hợp.
- [ ] Có object/tenant/role/purpose access và negative tests.
- [ ] Giảm định danh/tổng hợp có threat model, không mặc định là ẩn danh.
- [ ] Retention/deletion có rules, owner, downstream evidence và exceptions.
- [ ] Vendor có scope, shared responsibility, assessment và exit controls.
- [ ] Mỗi risk quan trọng có treatment owner, requirements, controls và test.
- [ ] Claim–Argument–Evidence nối privacy harms với control effectiveness.
- [ ] Có design, implementation và operating evidence đúng scope/kỳ.
- [ ] Evidence có provenance, completeness, reliability, integrity và limitations.
- [ ] Có build/config/SDK version/deployment mapping khi kết luận kỹ thuật.
- [ ] Phân biệt Pass, Fail, Insufficient evidence, N/A, exception.
- [ ] Finding có impact, containment, remediation, retest và đúng risk decision.
- [ ] Risk acceptance không xóa control failure hoặc nghĩa vụ bắt buộc.
- [ ] Có incident/complaint channels và trigger review khi thay data/purpose/vendor/model.
- [ ] Có metrics về privacy harms, evidence gaps, findings và xử lý theo risk.
- [ ] Báo cáo cho lãnh đạo chỉ rõ **đã chứng minh gì, chưa chứng minh gì, và residual risk nào còn mở**.

## 36. Ghi nhớ

- **Privacy risk là nguy cơ tác động bất lợi tới cá nhân/nhóm do hoạt động xử lý dữ liệu**, không chỉ là sự cố tấn công hay lộ thông tin.
- Bảo mật thông tin hỗ trợ quyền riêng tư nhưng **security controls đạt không tự bảo đảm privacy processing phù hợp**.
- Phân tích phải xét **purpose, dữ liệu, con người bị ảnh hưởng, bối cảnh, data flow, khả năng liên kết/suy luận, recipients, retention và hậu quả**.
- Pseudonymization hay hashing **không tự biến dữ liệu thành ẩn danh**.
- Privacy impact đối với cá nhân và organizational impact cần được làm rõ riêng; **nhóm nhỏ vẫn có thể chịu tác động lớn**.
- Một risk scenario tốt mô tả **sự kiện/xử lý → đường tạo harm → khả năng xảy ra, tác động, bất định → controls và residual risk**.
- PIA/DPIA và các nghĩa vụ pháp lý cần xem theo **khung thực tế áp dụng**; hồ sơ được duyệt chưa phải bằng chứng runtime.
- Controls có thể gồm minimization, purpose restrictions, transparency, choice, accuracy, access, retention, security và vendor management **tùy risk scenario**.
- Assurance cần **Claim–Argument–Evidence** và kiểm tra design, implementation, operating effectiveness với nguồn, scope, kỳ và limitations rõ.
- **Control failure và evidence gap là hai tình trạng khác nhau**; đều cần xử lý minh bạch, không tự chuyển thành Pass.
- Một chương trình trưởng thành duy trì vòng lặp **processing context → privacy harms → requirements/controls → tests/evidence → assessment → decision → continuous monitoring/reassessment** trong phát triển và vận hành.



