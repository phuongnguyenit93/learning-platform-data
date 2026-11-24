# Start date trong nguồn dữ liệu nhân sự: ngày bắt đầu và thời điểm kích hoạt danh tính IAM

Trong quản lý danh tính và truy cập (*Identity and Access Management* — **IAM**), **Start date** là thông tin nhân sự thể hiện **ngày bắt đầu có hiệu lực của một quan hệ làm việc, hợp đồng hoặc đợt phân công** theo định nghĩa của nguồn dữ liệu có thẩm quyền. Đối với nhân viên mới, trường này thường được dùng để chuẩn bị và kích hoạt quyền truy cập đúng thời điểm. Tuy nhiên, **có Start date không có nghĩa một người đã được xác minh, đủ điều kiện bắt đầu làm việc hoặc được phép truy cập tất cả hệ thống**.

Bài học thuộc chương **Nguồn dữ liệu nhân sự** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, nghiên cứu cách dùng thuộc tính Start date trong vòng đời danh tính **Joiner–Mover–Leaver (JML)**: từ xác minh hồ sơ, tạo tài khoản trước ngày làm việc, cấp quyền có kiểm soát, cập nhật khi thay đổi vai trò đến thu hồi khi quan hệ không còn hiệu lực. Nội dung kết nối **HRIS**, **IdP**, **SSO**, **SCIM**, **RBAC/ABAC**, tài khoản dịch vụ, truy vết kiểm toán và biện pháp hạn chế quyền tồn dư.

Sau bài học, người học có thể:

- Giải thích ý nghĩa nghiệp vụ của Start date, nguồn dữ liệu có thẩm quyền và những khái niệm ngày dễ bị nhầm.
- Phân biệt **ngày bắt đầu quan hệ**, **ngày tạo danh tính**, **ngày cấp tài khoản**, **thời điểm kích hoạt** và **thời điểm cấp quyền**.
- Chọn cách biểu diễn ngày/giờ và múi giờ nhất quán để tránh kích hoạt sai sớm hoặc muộn.
- Thiết kế xử lý Start date cho Joiner, Mover, thay đổi lịch tuyển dụng, tái tuyển dụng và chuyển loại quan hệ.
- Đề xuất quy tắc xử lý sự kiện, đối soát, kiểm toán và các chỉ số chất lượng dữ liệu Start date.

## 1. Start date là gì?

Trong bối cảnh HRIS, Start date thường trả lời: **“Quan hệ lao động hoặc đợt làm việc này bắt đầu có hiệu lực từ ngày nào?”** Đây là một **thuộc tính có nguồn gốc nghiệp vụ**, do bộ phận nhân sự hoặc nguồn quản lý hợp đồng được ủy quyền xác nhận. Nó không nhất thiết chính là ngày nhận được hồ sơ tuyển dụng, ngày ký hợp đồng, ngày đầu tiên nhân viên đăng nhập hay ngày cấp tài khoản.

Ví dụ:

- Ngày **20/11**, HRIS ghi nhận tuyển dụng An.
- **Start date = 01/12** là ngày hợp đồng và quá trình làm việc bắt đầu theo hồ sơ.
- Ngày **25/11**, hệ thống IAM có thể chuẩn bị tài khoản IdP, email và thiết bị theo quy định.
- Lúc **08:00 ngày 01/12** tại múi giờ được tổ chức quy định, IAM kích hoạt quyền nghiệp vụ.

Trong ví dụ này, bốn mốc thời gian có ý nghĩa khác nhau. Nếu hệ thống IAM đánh đồng “đã có hồ sơ” với “đã bắt đầu làm việc”, người dùng có thể nhận quyền quá sớm.

### 1.1. Phân biệt các trường ngày

| Trường hoặc mốc | Ý nghĩa chính | Ảnh hưởng IAM |
| --- | --- | --- |
| **Start date** | Ngày quan hệ công việc/đợt làm việc có hiệu lực theo nguồn có thẩm quyền. | Cơ sở cho quy tắc kích hoạt danh tính và quyền. |
| **Hire date** | Ngày tuyển dụng được định nghĩa bởi HR; có nơi trùng Start date, có nơi mang ý nghĩa lịch sử khác. | Không tự thay Start date nếu chưa thống nhất định nghĩa. |
| **Contract signed date** | Ngày ký hợp đồng. | Không tự động chứng minh người dùng được truy cập ngay ngày ký. |
| **Record created date** | Lúc hồ sơ được tạo tại HRIS. | Có thể khởi động chuẩn bị cấp tài khoản, không mặc định kích hoạt. |
| **Onboarding date / orientation date** | Lịch tiếp nhận hoặc đào tạo; có thể sớm hơn Start date. | Có thể cần quyền preboarding giới hạn, được phê duyệt riêng. |
| **Account provisioned at** | Lúc tài khoản IdP/ứng dụng được tạo. | Tài khoản có thể tồn tại ở trạng thái chờ hoặc bị khóa. |
| **Account enabled at** | Thời điểm một tài khoản được phép xác thực. | Phải tuân thủ chính sách về ngày bắt đầu và điều kiện kích hoạt. |
| **Entitlement effective at** | Lúc một quyền cụ thể bắt đầu có hiệu lực. | Có thể khác thời điểm mở tài khoản; quyền nhạy cảm cần phê duyệt. |
| **End date / termination effective at** | Mốc kết thúc quan hệ làm việc. | Điều khiển thu hồi quyền trong Leaver. |

**Quy tắc thiết kế:** mỗi hệ thống phải thống nhất “Start date” đang chỉ **quan hệ nào**, **loại ngày nào**, **múi giờ nào** và **điều kiện nào** khiến mốc đó đủ tin cậy để tự động kích hoạt.

## 2. Nguồn dữ liệu có thẩm quyền đối với Start date

Đối với **Employee**, HRIS thường là **nguồn có thẩm quyền (authoritative source)** của Start date. Đối với **Contractor**, nguồn có thể là hệ thống quản lý nhà cung cấp, hợp đồng hoặc thông tin do người bảo trợ (sponsor) xác nhận. Với khách mời, đối tác hoặc thực thể phi con người, cách xác định hiệu lực có thể khác và không nên gán máy móc trường Start date của nhân viên.

Một bản ghi Start date đáng tin cậy cần đi kèm các dữ liệu định danh và ngữ cảnh tối thiểu:

| Dữ liệu liên quan | Vì sao cần |
| --- | --- |
| **Person/subject ID ổn định** | Xác định đúng con người/chủ thể; tránh nhầm người trùng tên. |
| **Employee/engagement ID** | Xác định đúng đợt làm việc, đặc biệt khi tái tuyển dụng hoặc chuyển hợp đồng. |
| **Worker type** | Phân biệt Employee, Contractor và nhóm cần chính sách khác. |
| **Start date** | Ngày bắt đầu của quan hệ tương ứng. |
| **Employment/engagement status** | Biết hồ sơ đã được xác nhận, còn chờ, bị hủy hay đã có hiệu lực. |
| **Source system và record version** | Kiểm chứng nguồn và xử lý sự kiện đến trễ/sai thứ tự. |
| **Effective date/time, timezone policy** | Chuyển ngày nghiệp vụ thành thời điểm kích hoạt kỹ thuật. |
| **Department/job code/manager** | Tính quyền khởi tạo và xác định người phê duyệt. |
| **Event ID, event time, recorded time** | Truy vết sự thay đổi và lý do cập nhật. |

Không dùng **email, họ tên** làm khóa duy nhất để áp dụng Start date. Email có thể thay đổi hoặc được tái sử dụng, còn hai nhân viên có thể trùng tên. Trường Start date phải được gắn với đúng **quan hệ làm việc** của đúng **chủ thể**.

### 2.1. Nguồn sự thật không đồng nghĩa trạng thái đã sẵn sàng

HRIS có thể gửi một hồ sơ ở trạng thái **DRAFT**, **OFFER_ACCEPTED**, **PENDING_VERIFICATION** hoặc **CANCELLED**. Tên trạng thái phụ thuộc hệ thống, nhưng luồng IAM phải có bảng ánh xạ rõ ràng:

- **Hồ sơ đã được phê duyệt và đủ điều kiện**: có thể chuẩn bị cấp tài khoản và lên lịch kích hoạt.
- **Hồ sơ chưa được xác minh hoặc thiếu phê duyệt**: không tự cấp quyền nghiệp vụ.
- **Hồ sơ bị hủy trước ngày bắt đầu**: hủy lịch kích hoạt, vô hiệu hóa tài khoản đã chuẩn bị và đối soát quyền còn sót.
- **Start date thay đổi**: tính lại lịch và kiểm tra những tài khoản/quyền đã được kích hoạt.

Start date là **một điều kiện quan trọng**, nhưng phải được đánh giá cùng **trạng thái hồ sơ, kết quả xác minh, chính sách phân quyền và các điều kiện kiểm soát khác**.

## 3. Biểu diễn Start date và múi giờ

Một lỗi phổ biến là đồng nhất **ngày theo lịch** với **thời điểm (instant) trong UTC**.

### 3.1. Date-only khác timestamp

Giả sử nguồn nhân sự gửi:

~~~json
{
  "subjectId": "person-1042",
  "employmentId": "EMP-5812",
  "startDate": "2026-12-01",
  "startDateType": "LOCAL_DATE",
  "businessTimeZone": "Asia/Ho_Chi_Minh",
  "status": "CONFIRMED"
}
~~~

Giá trị **2026-12-01** chỉ là **ngày trên lịch**, không tự xác định giờ và múi giờ. Nếu chính sách yêu cầu kích hoạt **08:00 giờ Việt Nam** vào ngày này thì mốc kích hoạt tương ứng là **2026-12-01T08:00:00+07:00**, tức **2026-12-01T01:00:00Z**. Đây là ví dụ quy tắc kỹ thuật, **không phải quy định mặc định của IAM**.

Tùy tổ chức, thời điểm được phép truy cập có thể là:

- Đầu ngày làm việc tại địa điểm của nhân viên.
- Thời điểm bắt đầu ca làm việc hoặc ca trực đã xác nhận.
- Mốc chung theo múi giờ doanh nghiệp.
- Thời điểm có hiệu lực riêng do nguồn nhân sự cung cấp.

**Không tự giả định Start date là 00:00 UTC.** Nếu lấy ngày “01/12” và quy đổi theo UTC một cách máy móc, có thể mở quyền trước hoặc sau lịch làm việc tại địa phương.

### 3.2. Định nghĩa trường dữ liệu rõ ràng

Một thiết kế thường nên tách:

| Trường ví dụ | Kiểu logic | Ý nghĩa |
| --- | --- | --- |
| **startDate** | LocalDate / chuỗi ISO 8601 dạng ngày | Ngày quan hệ có hiệu lực theo nguồn. |
| **businessTimeZone** | IANA time zone | Múi giờ dùng để hiểu ngày theo lịch. |
| **activationPolicy** | ID quy tắc nghiệp vụ | Quy tắc chuyển ngày thành thời điểm kích hoạt. |
| **activationAt** | Instant có offset hoặc UTC | Thời điểm hệ thống đã tính để kích hoạt. |
| **sourceUpdatedAt** | Timestamp | Lúc nguồn sửa hồ sơ. |
| **lastReconciledAt** | Timestamp | Lúc xác minh trạng thái thực tế. |

IANA time zone như **Asia/Ho_Chi_Minh**, **Europe/Berlin** giúp xử lý quy tắc múi giờ lịch sử và thay đổi giờ mùa hè tại những nơi có áp dụng. Với ngày rơi vào thời điểm chuyển giờ mùa hè, hệ thống phải xác định cách xử lý giờ **không tồn tại** hoặc **lặp lại**; tránh tự động chọn tùy tiện.

Đối với cùng một Employee có hợp đồng tại quốc gia A nhưng làm việc tại quốc gia B, cần quy định **múi giờ của quan hệ nào có thẩm quyền**. Không nên tự suy ra từ IP hoặc vị trí thiết bị của người đang đăng nhập.

## 4. Start date trong Joiner: chuẩn bị sớm, kích hoạt đúng hạn

### 4.1. Hai giai đoạn kỹ thuật quan trọng

Trong vòng đời Joiner, IAM nên phân biệt:

1. **Pre-provisioning (chuẩn bị):** khi hồ sơ đã hợp lệ, hệ thống có thể tạo danh tính và tài khoản, chuẩn bị thiết bị, email, nhóm theo chính sách. Những tài khoản này có thể **chưa cho phép đăng nhập** hoặc chỉ có phạm vi truy cập trước ngày bắt đầu.
2. **Activation (kích hoạt):** đến mốc được phép và sau khi kiểm tra các điều kiện bắt buộc, hệ thống bật khả năng xác thực và cấp quyền nghiệp vụ tương ứng.

Ví dụ lịch:

| Mốc | Sự kiện | Hành động IAM |
| --- | --- | --- |
| **20/11** | HRIS xác nhận nhân viên Minh bắt đầu ngày 01/12. | Xác minh hồ sơ, nhận định danh ổn định, tạo yêu cầu onboarding. |
| **25/11** | Chính sách cho phép chuẩn bị trước sáu ngày. | Tạo tài khoản IdP và ứng dụng, ở trạng thái chờ; đối soát và xử lý lỗi. |
| **30/11** | Nhân sự đổi ngày bắt đầu thành 05/12. | Hủy lịch cũ, tính lại lịch mới; không kích hoạt theo mốc 01/12. |
| **05/12** | Quan hệ bắt đầu có hiệu lực và các điều kiện đạt yêu cầu. | Kích hoạt tài khoản, cấp quyền phù hợp, yêu cầu MFA/khôi phục tài khoản an toàn. |
| **05/12 sau kích hoạt** | Ứng dụng phản hồi việc cấp quyền. | Kiểm tra quyền thực tế, ghi bằng chứng và xử lý chênh lệch. |

Lưu ý rằng **ngày chuẩn bị tài khoản** và **thời gian truy cập được phép** có thể khác nhau; không nên đặt tài khoản ở trạng thái hoạt động chỉ vì connector SCIM đã tạo tài khoản thành công.

### 4.2. Một chính sách kích hoạt an toàn

Ở mức ý tưởng, điều kiện có thể là:

~~~text
eligibleForActivation(employee, now):
    return
        employee.identityVerified == true
        AND employee.engagementStatus == CONFIRMED
        AND employee.startDate is valid
        AND now >= activationAt(employee.startDate, approvedPolicy)
        AND employee.engagementCancelled == false
        AND employee.hasRequiredApprovals == true
~~~

Đây là **giả mã minh họa**, không phải tiêu chuẩn IAM hoặc chính sách áp dụng chung. Trong triển khai thực tế, điều kiện còn phải tính đến quy định nhân sự, bảo mật, đào tạo bắt buộc, vai trò rủi ro cao hoặc tình huống ngoại lệ được phê duyệt.

### 4.3. Quyền truy cập trước Start date

Một số tổ chức cần nhân viên mới hoàn tất biểu mẫu, đào tạo nội quy hoặc xác nhận thiết bị trước ngày làm việc. Nếu có preboarding:

- Tạo **phạm vi quyền riêng**, giới hạn vào tài nguyên cần cho chuẩn bị; không kế thừa toàn bộ quyền của Employee đang hoạt động.
- Chỉ cho phép truy cập sau khi người nhận tài khoản được xác minh qua kênh phù hợp.
- Quy định thời hạn tự kết thúc của quyền preboarding khi chuyển sang Active, khi hoãn hoặc hủy tuyển dụng.
- Ghi nhận cơ sở phê duyệt, tài nguyên được phép và kết quả thu hồi quyền preboarding.

**Không mặc định cấp quyền sản xuất hoặc dữ liệu nhạy cảm trước Start date** chỉ để quá trình onboarding thuận tiện hơn.

## 5. Start date đi qua HRIS, IGA, IdP, SSO và SCIM

~~~mermaid
flowchart LR
    HR["HRIS<br/>Start date + trạng thái hồ sơ"] -->|"Sự kiện có phiên bản"| IGA["IGA / JML workflow"]
    IGA -->|"Xác minh + tính activationAt"| JOB["Bộ điều phối lịch"]
    JOB -->|"Đến hạn + kiểm tra lại điều kiện"| IDP["IdP / Directory"]
    IDP -->|"SSO"| APP["Ứng dụng nghiệp vụ"]
    JOB -->|"SCIM / API cấp và kích hoạt"| APP
    HR --> AUD["Audit / đối soát"]
    IGA --> AUD
    IDP --> AUD
    APP --> AUD
    AUD -->|"Lỗi / lệch trạng thái"| IGA
~~~

Các vai trò cần phân định:

- **HRIS** phát Start date, thay đổi ngày, trạng thái quan hệ và mã hồ sơ có thẩm quyền.
- **IGA/lifecycle workflow** đối chiếu danh tính, quyết định trạng thái phù hợp và tính kế hoạch cấp quyền.
- **Bộ điều phối** lên lịch, hủy lịch cũ, đánh giá lại hồ sơ khi đến hạn và quản lý retry.
- **IdP** kích hoạt/khóa tài khoản, thực thi xác thực và các chính sách MFA.
- **SSO** hỗ trợ đăng nhập tập trung; nhưng việc tồn tại tài khoản SSO không tự đồng nghĩa ứng dụng đã áp dụng đúng quyền.
- **SCIM/API** tạo, cập nhật hoặc vô hiệu hóa tài khoản/nhóm tại hệ thống đích; với hệ thống không hỗ trợ, cần tích hợp hoặc quy trình bù trừ phù hợp.
- **Audit/đối soát** xác minh thay đổi trên từng hệ thống, phát hiện tài khoản kích hoạt sớm hoặc quyền chưa được thu hồi.

Trong các ứng dụng dùng OIDC, việc mở truy cập phải dựa trên chính sách tại IdP và ứng dụng; ứng dụng có thể còn phiên hoặc tài khoản cục bộ, nên **khóa IdP không bảo đảm mọi đường truy cập đã chấm dứt**. Đối với ngày bắt đầu bị hủy hoặc lùi lại, phải xử lý cả những phiên/token đã phát hành nếu tài khoản từng được kích hoạt.

## 6. Thay đổi Start date: hoãn, đẩy sớm, hủy và sửa sai

Start date thường bị điều chỉnh trước ngày làm việc thực tế vì thủ tục, thị thực, thiết bị, nhu cầu dự án hoặc quyết định tuyển dụng. Một quy trình tự động chỉ có thao tác “tạo lịch kích hoạt” mà không hỗ trợ **sửa/hủy lịch** sẽ dễ mở quyền sai thời điểm.

### 6.1. Hoãn ngày bắt đầu

**Ví dụ:** HRIS ban đầu ghi 01/12, sau đó đổi thành 15/12.

Hệ thống IAM phải:

1. Xác minh sự kiện sửa ngày xuất phát từ nguồn có thẩm quyền, có mã hồ sơ/phiên bản hợp lệ.
2. Hủy lịch kích hoạt cũ hoặc làm lịch cũ trở nên không hợp lệ.
3. Tính lại **activationAt** theo múi giờ/chính sách đã chọn.
4. Nếu tài khoản đã kích hoạt theo ngày cũ, đánh giá lại và **khóa/hạn chế quyền** nếu chưa đủ điều kiện.
5. Ghi dấu vết ngày trước/sau, nguyên nhân, tác vụ đã thay đổi và kết quả tại hệ thống đích.

**Không chỉ sửa Start date trong database rồi cho lịch chạy cũ tiếp tục**. Tác vụ lên lịch cần kiểm tra lại phiên bản hồ sơ và điều kiện trước khi thực thi.

### 6.2. Đẩy ngày bắt đầu lên sớm

**Ví dụ:** ngày bắt đầu được đổi từ 15/12 về 05/12, khi ngày 05/12 đã tới hoặc chỉ còn vài giờ.

Hệ thống cần ưu tiên tính lại lịch, hoàn thành xác minh/duyệt, cấp tài khoản, kiểm tra MFA và đối soát; nếu chưa đạt các điều kiện bảo mật, phải ghi nhận lý do chậm thay vì bỏ qua kiểm soát để “kịp ngày”.

### 6.3. Hủy tuyển dụng trước ngày bắt đầu

Hủy Joiner là một **sự kiện vòng đời có tác động thu hồi**, dù người đó chưa thực sự bắt đầu làm việc. Cần:

- Hủy kích hoạt đã lên lịch.
- Vô hiệu hóa các tài khoản chuẩn bị trước tại IdP và ứng dụng, xử lý quyền preboarding.
- Thu hồi invitation link, thông tin xác thực/tokens đã phát hành nếu có.
- Đối soát tài khoản/phân quyền đích và giữ bằng chứng theo chính sách.

Không chỉ xóa hồ sơ HRIS và hy vọng tài khoản tự biến mất; ứng dụng có thể đã tạo tài khoản độc lập.

### 6.4. Sửa lịch sử và sự kiện đến trễ

HRIS có thể gửi một bản sửa dữ liệu đã có hiệu lực trong quá khứ. IAM cần phân biệt:

- **Cập nhật có hiệu lực từ trước**: đánh giá hậu quả truy cập trong khoảng thời gian liên quan và điều chỉnh trạng thái hiện tại.
- **Sự kiện cũ đến trễ**: không cho nó ghi đè Start date mới hơn.
- **Sự kiện gửi lặp**: không tạo nhiều tài khoản, nhiều lịch kích hoạt hoặc cấp quyền trùng.

Nên xử lý **idempotent** dựa trên ID sự kiện; dùng phiên bản bản ghi/chuỗi thời gian nghiệp vụ và quy tắc xung đột thay vì chỉ so sánh thời điểm hệ thống nhận thông điệp.

## 7. Start date trong Mover, tái tuyển dụng và nhiều quan hệ

### 7.1. Start date của nhân viên và ngày bắt đầu vai trò mới

Một Employee có thể gia nhập công ty ngày **01/03/2024**, rồi chuyển sang bộ phận khác từ **01/12/2026**. Không nên ghi đè **ngày gia nhập tổ chức** bằng **ngày hiệu lực vai trò mới**.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Employment start date** | Ngày bắt đầu quan hệ lao động. | 2024-03-01 |
| **Role assignment start date** | Ngày có hiệu lực của nhiệm vụ/vai trò hiện tại. | 2026-12-01 |
| **Project assignment start date** | Ngày bắt đầu tham gia một dự án. | 2026-11-25 |
| **Entitlement start date** | Ngày quyền ứng dụng được phép có hiệu lực. | 2026-12-01 |

Trong **Mover**, chính sách cần biết ngày nào điều khiển **cấp quyền mới** và ngày nào bắt buộc **thu hồi quyền cũ**. Nếu quyền vai trò cũ bị giữ vô thời hạn sau khi role mới bắt đầu, Employee có nguy cơ tích lũy quyền (*privilege creep*).

### 7.2. Tái tuyển dụng (rehire)

Khi một người đã nghỉ việc được tuyển lại, có thể tồn tại:

- Một **Person ID** ổn định đại diện cho cùng người.
- Hai **employment/engagement ID** tương ứng hai giai đoạn quan hệ.
- Hai Start date khác nhau và các quyết định cấp quyền độc lập.

Ví dụ, Hòa làm việc từ 2023 đến 2025 và được tuyển trở lại từ 10/12/2026. IAM cần xác minh hai hồ sơ thuộc cùng một người nhưng **không tự khôi phục** toàn bộ quyền/tài khoản cũ. Quyền hiện tại phải được tính từ vai trò, trạng thái và phê duyệt của **đợt làm việc mới**. Có thể tái sử dụng tài khoản theo chính sách, song các phiên cũ, thông tin xác thực và quyền dư phải được kiểm soát.

### 7.3. Employee chuyển thành Contractor hoặc ngược lại

Một người có thể kết thúc hợp đồng dịch vụ ngày 30/11 rồi trở thành Employee từ 01/12. Hai quan hệ này có thể có hai nguồn có thẩm quyền và bộ quyền khác nhau. Tránh đồng nhất Start date của quan hệ mới với việc **tiếp tục vô điều kiện** quan hệ cũ:

1. Xác minh danh tính người thật và nối các engagement có căn cứ.
2. Xác định rõ quan hệ nào chấm dứt, quan hệ nào bắt đầu và thời điểm hiệu lực.
3. Thu hồi những quyền thuộc loại quan hệ cũ, rồi cấp quyền mới theo chính sách.
4. Đối soát các ứng dụng để tránh hai tài khoản/nhóm cùng hoạt động ngoài ý muốn.

## 8. Start date và phân quyền RBAC/ABAC

Một Start date hợp lệ là **điều kiện thời gian**; quyền cụ thể còn phụ thuộc vai trò, thuộc tính và phê duyệt.

### 8.1. RBAC

Với **Role-Based Access Control (RBAC)**, Employee có thể nhận các vai trò như **support-agent**, **finance-analyst** hoặc **developer-basic** sau khi đủ điều kiện bắt đầu công việc.

Ví dụ:

~~~text
HRIS: workerType = EMPLOYEE
      engagementStatus = CONFIRMED
      startDate = 2026-12-01
      jobCode = SUPPORT_AGENT

At approved activation time:
    => Enable IdP account
    => Assign IAM role: support-agent
    => Provision approved application entitlements
~~~

Không nên áp dụng role mặc định ngay khi hồ sơ được tạo nếu chưa đến thời gian được phép.

### 8.2. ABAC

**Attribute-Based Access Control (ABAC)** có thể dùng trạng thái quan hệ và thời gian trong điều kiện truy cập. Ví dụ quy tắc khái niệm:

~~~text
ALLOW if
    subject.workerType == "EMPLOYEE"
    AND subject.engagementStatus == "ACTIVE"
    AND request.time >= subject.approvedActivationAt
    AND subject.departmentId == resource.ownerDepartment
    AND action == "read"
~~~

Đây là **mẫu minh họa**, không phải cú pháp chuẩn được mọi công cụ ABAC hỗ trợ. Trong triển khai thực tế, cần kiểm soát độ tin cậy và độ tươi của thuộc tính. Nếu Start date bị dời mà bộ đệm thuộc tính tại ứng dụng chưa cập nhật, chính sách đúng về logic vẫn có thể quyết định sai vì sử dụng dữ liệu cũ.

Quyền **đặc quyền**, dữ liệu nhạy cảm hoặc quyền ngoài vai trò thường cần phê duyệt tăng cường và mốc hiệu lực riêng, thay vì phụ thuộc duy nhất Start date của Employee.

## 9. Mẫu xử lý sự kiện và lịch kích hoạt

Giả sử HRIS phát sự kiện xác nhận ngày bắt đầu:

~~~json
{
  "eventId": "hr-evt-9344",
  "eventType": "ENGAGEMENT_START_DATE_UPDATED",
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "workerType": "EMPLOYEE",
  "startDate": "2026-12-05",
  "businessTimeZone": "Asia/Ho_Chi_Minh",
  "engagementStatus": "CONFIRMED",
  "recordVersion": 12,
  "occurredAt": "2026-11-30T03:00:00Z",
  "sourceSystem": "HRIS"
}
~~~

Một luồng xử lý bảo vệ việc sửa lịch và sự kiện đến muộn:

~~~text
onHrisEvent(event):
    validateTrustedSourceAndSchema(event)
    if alreadyProcessed(event.eventId): return

    engagement = resolveByStableEngagementId(event.engagementId)
    if engagement is ambiguous:
        createManualReview(event)
        return

    if event.recordVersion < engagement.latestVersion:
        ignoreStaleEvent(event)
        return

    saveAuthorizedEngagementState(event)
    invalidatePreviousActivationSchedule(engagement.id)

    if event.engagementStatus == "CANCELLED":
        deprovisionPreHireAccountsAndPrivileges(engagement)
        reconcileTargetSystems(engagement)
        return

    if not engagement.identityVerified:
        placeOnHoldForVerification(engagement)
        return

    when = calculateActivationInstant(
        event.startDate,
        event.businessTimeZone,
        approvedActivationPolicy
    )
    scheduleActivation(engagement.id, event.recordVersion, when)

onActivationDue(engagementId, scheduledVersion):
    engagement = reloadFromAuthoritativeSource(engagementId)
    if engagement.version != scheduledVersion: return
    if not allActivationConditionsSatisfied(engagement): return

    provisionOrEnableRequiredAccounts(engagement)
    provisionApprovedEntitlements(engagement)
    verifyActualTargetState(engagement)
    recordAuditEvidence(engagement)
~~~

Đây là giả mã để giải thích thiết kế, chưa bao gồm mọi chi tiết vận hành. Hệ thống thực tế cần xác thực thông điệp, xử lý lỗi tạm thời, số lần retry, giao dịch từng phần, giám sát tác vụ quá hạn và quy trình can thiệp khi hệ thống nguồn không thể truy cập đúng lúc.

**Điểm quyết định:** tác vụ đến hạn phải **tải lại dữ liệu hợp lệ hiện tại và kiểm tra phiên bản**, không chỉ dùng Start date đã chụp tại thời điểm lịch được tạo. Đây là cách ngăn lịch cũ kích hoạt nhầm khi ngày bắt đầu đã được thay đổi hoặc hủy.

## 10. Các tình huống dễ gây lỗi

| Tình huống | Rủi ro | Hướng kiểm soát |
| --- | --- | --- |
| Start date là ngày địa phương nhưng bị hiểu như UTC. | Kích hoạt sớm hoặc muộn nhiều giờ. | Quy định rõ kiểu ngày, múi giờ và chính sách chuyển sang thời điểm. |
| Hồ sơ được tạo trước Start date và tự kích hoạt ngay. | Employee có quyền sản xuất trước ngày hợp lệ. | Tách pre-provision khỏi activation; kiểm tra trạng thái và phê duyệt. |
| Start date hoãn nhưng lịch cũ còn chạy. | Mở quyền dù onboarding bị dời. | Hủy/vô hiệu lịch cũ; kiểm tra version nguồn lúc chạy. |
| Tuyển dụng bị hủy nhưng tài khoản đã cấp phát tồn tại. | Tài khoản mồ côi và quyền preboarding còn hiệu lực. | Vô hiệu hóa, thu hồi và đối soát từng ứng dụng. |
| Sự kiện HRIS đến sai thứ tự. | Start date mới bị ghi đè bởi dữ liệu cũ. | Xử lý idempotent và dựa trên phiên bản/hiệu lực. |
| HRIS ghi Start date hợp lệ nhưng chưa xác minh người thật. | Kích hoạt sai danh tính. | Yêu cầu xác minh, định danh ổn định, kiểm tra trùng. |
| Employee trở lại làm việc, hệ thống khôi phục quyền cũ. | Có quyền không phù hợp vai trò mới. | Tạo quan hệ mới có kiểm chứng, tính lại quyền. |
| App hỗ trợ SSO nhưng còn tài khoản cục bộ. | Truy cập tồn dư khi lịch bị hủy. | Inventory, SCIM/API và đối soát tài khoản/phiên/token đích. |
| Thay đổi ngày có hiệu lực trong quá khứ. | Sai lịch sử quyền, khó xác định khoảng truy cập không hợp lệ. | Lưu lịch sử sửa, đánh giá tác động và đối soát hiện tại. |

## 11. Kiểm toán Start date: chứng minh vì sao tài khoản được kích hoạt

Để giải trình một trường hợp Employee được phép truy cập từ lúc nào, hệ thống IAM nên truy vết **chuỗi quyết định và kết quả**, không chỉ giá trị Start date hiện tại.

### Những bằng chứng nên giữ

1. **Thông tin nguồn:** HRIS/nguồn có thẩm quyền, subject/engagement ID, Start date cũ và mới, trạng thái quan hệ, phiên bản bản ghi.
2. **Ngữ cảnh thời gian:** timezone dùng để tính, chính sách kích hoạt và thời điểm kỹ thuật **activationAt**.
3. **Điều kiện xác minh:** danh tính đã được xác minh hay chưa, nguồn xác nhận và trạng thái phê duyệt cần thiết.
4. **Lịch điều phối:** lịch tạo mới, lịch bị hủy, lý do thay đổi và phiên bản dữ liệu mà tác vụ sử dụng.
5. **Lệnh thực thi:** ID yêu cầu tạo tài khoản, enable/disable IdP, cấp/thu hồi quyền qua SCIM/API.
6. **Trạng thái đích:** xác nhận tài khoản có thực sự bật hay chưa, quyền nào được cấp và kết quả đối soát.
7. **Ngoại lệ:** yêu cầu truy cập sớm, người có thẩm quyền phê duyệt, thời hạn và kết quả xử lý.

Ví dụ chuỗi sự kiện:

~~~text
2026-11-20  HRIS: Start date = 2026-12-01, status CONFIRMED
2026-11-21  IGA: identity verified; activation scheduled
2026-11-25  IdP: account provisioned, disabled pending start
2026-11-30  HRIS: Start date changed to 2026-12-05
2026-11-30  IGA: old schedule invalidated; new schedule created
2026-12-05  IGA: source and approvals revalidated
2026-12-05  IdP: account enabled; app role assigned
2026-12-05  Reconciliation: target access verified
~~~

Các mốc trên chỉ mang tính minh họa; để dùng cho điều tra phải ghi **thời điểm chính xác kèm múi giờ**. Một dấu vết tốt giúp trả lời: tài khoản vì sao được tạo trước ngày bắt đầu, vì sao chưa thể đăng nhập, ai đổi Start date và vì sao kích hoạt diễn ra vào ngày mới.

### Bảo vệ dữ liệu và tính toàn vẹn

Start date và trạng thái lao động là dữ liệu nhân sự, cần được xử lý theo quyền truy cập và chính sách bảo vệ thông tin cá nhân. Nhật ký nên giữ đủ ID, mốc thời gian và lý do thay đổi nhưng không sao chép toàn bộ hồ sơ nhân sự hoặc bí mật xác thực như mật khẩu, token, mã OTP.

Giới hạn người được sửa/xóa lịch sử, chuẩn hóa thời gian, lưu bản ghi có thể đối chiếu và giám sát thiếu log. Kho log bất biến giúp bảo vệ bằng chứng nhưng không tự bảo đảm HRIS đã nhập đúng ngày; cần quy trình xác minh và sửa dữ liệu tại nguồn.

## 12. Đo chất lượng dữ liệu Start date và hiệu quả IAM

| Chỉ số | Cách đo gợi ý | Mục tiêu vận hành |
| --- | --- | --- |
| **Tỷ lệ Start date hợp lệ** | Hồ sơ có ngày đúng định dạng, nguồn, múi giờ/quy tắc áp dụng ÷ hồ sơ trong phạm vi. | Phát hiện lỗi dữ liệu trước khi chạy tự động. |
| **Tỷ lệ hồ sơ kích hoạt đúng hạn** | Joiner có quyền thực tế được xác minh trong khoảng thời gian mục tiêu ÷ tổng Joiner đủ điều kiện. | Đảm bảo sẵn sàng công việc. |
| **Số tài khoản kích hoạt trước mốc cho phép** | Đếm trường hợp account/entitlement có hiệu lực sớm ngoài ngoại lệ đã duyệt. | Phát hiện rủi ro truy cập sớm. |
| **Tỷ lệ sửa Start date xử lý đầy đủ** | Thay đổi Start date đã cập nhật lịch và đối soát thành công ÷ tổng thay đổi hợp lệ. | Ngăn lịch kích hoạt cũ và sai quyền. |
| **Thời gian xử lý ngày bị đẩy sớm** | Khoảng từ lúc nhận sửa ngày đến khi sẵn sàng quyền theo chính sách. | Nhận diện độ trễ quy trình cấp phát. |
| **Số Joiner hủy còn tài khoản hoạt động** | Tài khoản/phiên/quyền còn hiệu lực sau sự kiện hủy và thời hạn xử lý. | Đo truy cập tồn dư. |
| **Tỷ lệ hệ thống đích đã đối soát** | Hệ thống đã xác minh tài khoản/quyền đúng trạng thái ÷ tổng hệ thống phải kiểm tra. | Kiểm tra kết quả thay vì chỉ log gửi lệnh. |

Mỗi tổ chức phải xác định ngưỡng theo độ nhạy hệ thống, thỏa thuận vận hành và chính sách nhân sự. Khi báo cáo tỷ lệ, cần công bố phạm vi ứng dụng và cách xử lý các ngoại lệ được phê duyệt.

## 13. Bài tập tình huống

**Bối cảnh:** một công ty có ba hồ sơ cùng ngày 28/11:

| Hồ sơ | Dữ liệu HRIS | Trạng thái IAM hiện tại |
| --- | --- | --- |
| **A – Nhân viên mới** | Start date 05/12, CONFIRMED, đã xác minh. | Tài khoản IdP đã tạo, đang khóa chờ ngày bắt đầu. |
| **B – Nhân viên bị hoãn** | Start date đổi từ 01/12 sang 15/12, CONFIRMED. | Lịch kích hoạt 01/12 vẫn tồn tại. |
| **C – Tuyển dụng bị hủy** | Start date 01/12, status CANCELLED. | Tài khoản ứng dụng preboarding đang hoạt động. |

**Phân tích:**

- **A:** trạng thái chờ là phù hợp với cơ chế pre-provision. Cần bảo đảm quyền và thời gian kích hoạt đã được tính theo múi giờ/chính sách, rồi xác minh khi đến hạn.
- **B:** phải vô hiệu hóa lịch 01/12, lập lịch 15/12, kiểm tra xem tài khoản hoặc quyền nào đã mở quá sớm và lưu lịch sử sửa ngày.
- **C:** phải hủy lịch kích hoạt, khóa/thu hồi tài khoản preboarding và các đường truy cập liên quan; sau đó xác minh trạng thái tại ứng dụng đích.

**Câu hỏi mở rộng:** Nếu sự kiện B đổi sang 15/12 đến *sau* khi lịch 01/12 đã kích hoạt tài khoản, hệ thống cần làm gì? Cần xác minh thời điểm và nguồn sửa ngày, đánh giá quyền đã có hiệu lực, khóa/hạn chế quyền khi không còn đủ điều kiện, xử lý phiên/token còn hoạt động và ghi lại khoảng thời gian có thể đã truy cập sai. Chỉ cập nhật một dòng Start date trong HRIS là chưa đủ.

## 14. Checklist triển khai Start date trong nguồn dữ liệu nhân sự

1. Đã thống nhất Start date là **ngày bắt đầu của quan hệ nào**, lấy từ nguồn có thẩm quyền nào và đi kèm ID nhân sự/engagement ổn định chưa?
2. Đã phân biệt **ngày theo lịch**, **thời điểm UTC**, **múi giờ nghiệp vụ**, **ngày tạo tài khoản** và **ngày kích hoạt quyền** chưa?
3. Joiner có được xác minh, phê duyệt và kiểm tra trạng thái trước khi kích hoạt không?
4. Có tách **pre-provisioning** khỏi **quyền đăng nhập/quyền nghiệp vụ**, giới hạn truy cập trước Start date không?
5. Khi Start date hoãn, đẩy sớm hoặc bị hủy, hệ thống có hủy lịch cũ, xử lý tài khoản đã kích hoạt và cập nhật quyền thực tế không?
6. Tác vụ đến hạn có tải lại phiên bản dữ liệu hợp lệ, chống sự kiện trùng/cũ và có retry/giám sát lỗi không?
7. Mover và rehire có dùng đúng Start date của vai trò/đợt lao động, tránh khôi phục quyền cũ ngoài chính sách không?
8. Có thể truy vết từ HRIS đến IGA, IdP, SCIM/API, ứng dụng, phiên/token và kết quả đối soát không?
9. Có phát hiện được tài khoản kích hoạt sớm, hồ sơ bị hủy còn tài khoản và quyền truy cập tồn dư không?

**Ghi nhớ:** **Start date là tín hiệu thời gian nghiệp vụ từ nguồn dữ liệu nhân sự, không phải lệnh cấp quyền độc lập.** IAM cần gắn trường này với đúng danh tính và quan hệ làm việc, xác định rõ múi giờ và chính sách hiệu lực, kiểm tra điều kiện trước kích hoạt, xử lý mọi thay đổi ngày và xác minh kết quả tại IdP/ứng dụng. Làm đúng giúp Joiner sẵn sàng đúng hạn, Mover/rehire không thừa quyền và hạn chế tài khoản tồn dư khi lịch làm việc thay đổi hoặc bị hủy.
