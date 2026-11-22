# Chẩn đoán lỗi đăng nhập bằng sign-in log và audit log

Một người dùng báo rằng họ không đăng nhập được vào ứng dụng chạy trên Microsoft Azure. Trang đăng nhập có thể chỉ hiển thị thông báo chung như “Access denied”, “Sign-in failed” hoặc mã lỗi AADSTS. Để tìm nguyên nhân, nhóm vận hành cần biết **yêu cầu đăng nhập của ai, đến ứng dụng nào, từ đâu, vào lúc nào, trải qua chính sách nào và thất bại ở bước nào**. Microsoft Entra ID cung cấp **sign-in logs** để trả lời những câu hỏi đó; **audit logs** giúp kiểm tra những thay đổi danh tính hoặc cấu hình có thể dẫn đến sự cố.

Bài học thuộc chương **Danh tính với Microsoft Entra ID**, nằm trong module `CLOUD_PROVIDERS_AZURE`. Trong hệ sinh thái Azure, bạn sẽ làm việc với tenant, subscription, resource group, mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Chẩn đoán đúng sự cố danh tính giúp duy trì khả năng truy cập ứng dụng, bảo vệ tài nguyên và hỗ trợ vận hành, giám sát, kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## 1. Phân biệt sign-in log, audit log và Activity Log

Ba loại log dễ bị nhầm khi điều tra một sự cố đăng nhập:

| Nguồn nhật ký | Ghi nhận chủ yếu | Câu hỏi thường trả lời |
|---|---|---|
| **Microsoft Entra sign-in logs** | Hoạt động xác thực và đăng nhập của người dùng hoặc danh tính ứng dụng. | Ai đăng nhập vào ứng dụng nào? Thành công hay thất bại? MFA và Conditional Access được xử lý ra sao? |
| **Microsoft Entra audit logs** | Hoạt động thay đổi đối tượng hoặc cấu hình trong thư mục Entra ID. | Ai thay đổi nhóm, tài khoản, ứng dụng, phương thức xác thực hoặc chính sách, và khi nào? |
| **Azure Activity Log** | Sự kiện ở lớp quản lý tài nguyên (control plane) của Azure subscription. | Ai tạo, sửa, xóa tài nguyên hoặc thay đổi Azure RBAC? |

Ví dụ: đăng nhập thất bại do một chính sách Conditional Access → xem **sign-in log** để biết điều kiện nào tác động. Nếu nghi ngờ chính sách vừa bị thay đổi → xem **audit log** để xác định hoạt động cập nhật. Nếu đăng nhập thành công nhưng không đủ quyền tạo virtual machine → kiểm tra **Azure RBAC** và **Azure Activity Log** của subscription; đó có thể là lỗi phân quyền tài nguyên thay vì lỗi xác thực.

**Không phải mỗi lần đăng nhập đều tạo một sự kiện audit.** Sign-in log ghi nhận lần thử đăng nhập; audit log ghi lại các thay đổi trong thư mục. Hai nguồn có thể liên quan nhưng phục vụ mục đích khác nhau.

### Các loại sign-in cần phân biệt

| Loại sign-in | Chủ thể và tình huống | Khi nào nên kiểm tra |
|---|---|---|
| **Interactive user sign-ins** | Người dùng tham gia luồng đăng nhập, ví dụ nhập thông tin và thực hiện MFA. | Người dùng không mở được Portal hoặc ứng dụng. |
| **Non-interactive user sign-ins** | Ứng dụng dùng phiên, token hoặc cơ chế làm mới mà không cần người dùng tương tác trực tiếp. | Ứng dụng liên tục yêu cầu đăng nhập hoặc làm mới token thất bại. |
| **Service principal sign-ins** | Ứng dụng hoặc tác vụ tự động đăng nhập bằng danh tính ứng dụng. | Pipeline, daemon hoặc service-to-service authentication lỗi. |
| **Managed identity sign-ins** | Workload Azure dùng managed identity để xin token tới dịch vụ khác. | Một App Service, VM hoặc Function không truy cập được tài nguyên bằng managed identity. |

Không nên chỉ xem interactive sign-ins nếu ứng dụng sử dụng phiên làm mới token, service principal hoặc managed identity. Loại luồng xác thực quyết định nhóm nhật ký cần mở.

## 2. Điều kiện và dữ liệu cần chuẩn bị

Để truy cập nhật ký, tài khoản phải có quyền đọc phù hợp trong **đúng Microsoft Entra tenant**. Các vai trò như **Reports Reader**, **Security Reader** hoặc vai trò quản trị có quyền tương ứng có thể xem những phần log được phép. Một số thông tin nhạy cảm, đánh giá rủi ro hoặc kết quả Conditional Access có thể yêu cầu vai trò hoặc gói tính năng bổ sung. Quyền xem nhật ký trong Entra ID và quyền truy vấn Log Analytics workspace là hai cơ chế cấp quyền riêng.

Trước khi bắt đầu, thu thập tối thiểu:

- **Tenant:** tên và Tenant ID của tổ chức hoặc môi trường xảy ra sự cố.
- **Người dùng hoặc workload:** UPN/email, object ID, application/service principal ID nếu có.
- **Ứng dụng/tài nguyên đích:** tên ứng dụng hoặc App ID/Resource ID.
- **Thời điểm:** thời gian xảy ra lỗi và múi giờ người dùng; quy đổi sang UTC khi đối chiếu.
- **Dấu vết:** thông báo lỗi, mã `AADSTS`, **Correlation ID**, **Request ID**, ảnh chụp màn hình đã che thông tin nhạy cảm nếu cần.
- **Bối cảnh:** đăng nhập tương tác hay tự động, thiết bị/trình duyệt, mạng công ty hay mạng ngoài, có VPN, có MFA hay không.

Sử dụng **thời điểm chính xác** thay vì “sáng nay”. Ví dụ, nếu người dùng ở Việt Nam (UTC+7) báo lỗi lúc 15:30 ngày 20/11/2026, thời điểm tương ứng là 08:30 UTC cùng ngày. Dữ liệu nhật ký có thể đến trễ; khi tìm kiếm, nên mở rộng khoảng thời gian xung quanh mốc được báo.

Không yêu cầu người dùng cung cấp mật khẩu, mã OTP, token truy cập hoặc client secret để chẩn đoán. Các thông tin đó không cần thiết để đọc sign-in log.

## 3. Các trường quan trọng trong sign-in log

Trong Azure Portal, các trường có thể xuất hiện ở tab hoặc tên nhãn khác nhau tùy loại sign-in và giao diện. Bảng dưới đây là bộ thông tin thường dùng:

| Trường/nhóm thông tin | Ý nghĩa | Cách sử dụng |
|---|---|---|
| **Date/Time** | Thời điểm sự kiện đăng nhập. | So sánh với giờ sự cố và các log liên quan. |
| **User / Identity** | Người dùng, service principal hoặc managed identity. | Xác định đúng chủ thể. |
| **Application** | Ứng dụng client yêu cầu đăng nhập. | Phân biệt Portal, ứng dụng nội bộ và ứng dụng SaaS. |
| **Resource** | API hoặc tài nguyên mà token được yêu cầu truy cập. | Tìm đúng dịch vụ đích khi có nhiều thành phần. |
| **Status** | Success, Failure hoặc trạng thái gián đoạn/yêu cầu bước tiếp theo tùy giao diện và luồng. | Khoanh vùng lần thử có vấn đề. |
| **Error code / Failure reason** | Mã lỗi và mô tả nguyên nhân mà dịch vụ nhận diện được. | Tạo giả thuyết chẩn đoán ban đầu. |
| **Correlation ID / Request ID** | Mã truy vết cho yêu cầu hoặc luồng đăng nhập. | Liên kết với thông báo lỗi, log ứng dụng và hỗ trợ kỹ thuật. |
| **IP address / Location** | Địa chỉ mạng và vị trí suy đoán từ mạng. | Kiểm tra điều kiện mạng hoặc Conditional Access. |
| **Device info** | Hệ điều hành, trình duyệt, trạng thái thiết bị khi dữ liệu có sẵn. | Xác định tác động của chính sách thiết bị. |
| **Authentication Details** | Các bước/phương thức xác thực, kết quả MFA nếu được ghi nhận. | Xem yêu cầu MFA đã được đáp ứng hay chưa. |
| **Conditional Access** | Kết quả áp dụng các chính sách có liên quan. | Xác định policy nào chặn hoặc yêu cầu thêm điều kiện. |

**Correlation ID và Request ID không thay thế nhau.** Cả hai đều hữu ích khi liên hệ đội ứng dụng hoặc bộ phận hỗ trợ Microsoft; nên lưu chính xác giá trị mà lỗi đăng nhập hiển thị. Khi ghép các nguồn khác nhau, phải xác minh mã nào thực sự xuất hiện ở mỗi nguồn, không giả định mọi audit event có cùng correlation ID với một sign-in.

Vị trí địa lý dựa trên IP là thông tin suy đoán; VPN, proxy, mạng di động hoặc NAT có thể khiến vị trí không giống vị trí vật lý. Không dùng riêng trường Location để kết luận người dùng có hành vi bất thường.

## 4. Đọc sign-in logs trong Microsoft Entra admin center

### Bước 1: Mở đúng tenant

1. Mở [Microsoft Entra admin center](https://entra.microsoft.com/).
2. Xác nhận tài khoản và **directory/tenant** đang hoạt động.
3. Trong **Microsoft Entra ID** → **Monitoring & health** → **Sign-in logs**, mở danh sách nhật ký. Tên mục và cách nhóm menu có thể thay đổi theo giao diện.
4. Chọn đúng nhóm log: interactive user, non-interactive user, service principal hoặc managed identity tùy luồng xác thực cần điều tra.

Nếu người dùng thuộc tenant đối tác dưới dạng guest, hãy xác định tenant của ứng dụng và tenant nơi yêu cầu đăng nhập đang được xử lý. Đừng mặc định đăng nhập vào home tenant là đủ để xem mọi log ở resource tenant.

### Bước 2: Lọc đúng sự kiện

1. Đặt khoảng thời gian bao phủ thời điểm lỗi, tính đến sai lệch múi giờ và độ trễ ghi log.
2. Lọc theo **User**, **Application**, **Status** hoặc các trường có sẵn.
3. Nếu có Request ID hoặc Correlation ID, dùng bộ lọc hoặc thông tin chi tiết để tìm bản ghi trùng khớp.
4. Khi một người dùng thử lại nhiều lần, so sánh các bản ghi trước và sau, thay vì chỉ mở bản ghi mới nhất.

### Bước 3: Phân tích bản ghi

Mở bản ghi phù hợp rồi xem:

- **Basic info / Status:** ứng dụng, resource, thời điểm, mã lỗi và failure reason.
- **Authentication Details:** bước xác thực nào thành công, bước nào không đạt, đã có yêu cầu MFA hay chưa.
- **Conditional Access:** chính sách nào được áp dụng, kết quả Success/Failure/Not applied hoặc report-only theo dữ liệu hiển thị.
- **Device info:** thiết bị có được nhận diện hoặc đáp ứng điều kiện cần thiết không.
- **Location / Network:** IP nguồn, network location và các điều kiện mạng liên quan.

Không nên diễn giải **sign-in success** là người dùng chắc chắn đã sử dụng ứng dụng thành công. Xác thực thành công vẫn có thể bị chặn ở lớp phân quyền ứng dụng, Azure RBAC, dữ liệu hoặc mạng. Ngược lại, một lần đăng nhập có trạng thái gián đoạn do cần MFA không nhất thiết là sự cố hệ thống.

### Bước 4: Ghi lại bằng chứng

Dùng biểu mẫu nhất quán để người khác có thể tiếp tục điều tra:

| Trường | Ví dụ giả định |
|---|---|
| Tenant | `contoso.onmicrosoft.com` |
| User | `user@contoso.example` |
| Application | `Sales Portal` |
| Event time (UTC) | `2026-11-20T08:30:00Z` |
| Status | `Failure` |
| Error code | `53003` |
| Correlation ID | `<CORRELATION_ID>` |
| Device / IP | Dữ liệu quan sát được, đã giới hạn chia sẻ |
| Conditional Access | Tên policy và kết quả hiển thị |
| Nhận định ban đầu | Kiểm tra điều kiện policy chặn truy cập |

Các giá trị trên chỉ là minh họa. Bản ghi thật có thể có thông tin bổ sung hoặc trường trống.

## 5. Chẩn đoán các nhóm nguyên nhân phổ biến

Mã AADSTS giúp thu hẹp nguyên nhân, nhưng **mã lỗi không phải toàn bộ kết luận**. Cần đọc thêm failure reason, authentication details, Conditional Access và cấu hình thực tế.

| Dấu hiệu/mã thường gặp | Giả thuyết ban đầu | Hướng kiểm tra |
|---|---|---|
| `AADSTS50034` | Tài khoản không tồn tại trong thư mục được chỉ định. | Kiểm tra UPN, Tenant ID, tài khoản khách, home realm và cấu hình ứng dụng. |
| `AADSTS50020` | Danh tính đăng nhập không có trong tenant mà ứng dụng yêu cầu, hoặc ngữ cảnh tổ chức không phù hợp. | Kiểm tra tenant của ứng dụng, invitation/guest account, lựa chọn tài khoản. |
| `AADSTS50076` | Yêu cầu MFA vì chính sách hoặc điều kiện xác thực. | Kiểm tra Authentication Details, đăng ký phương thức và Conditional Access. |
| `AADSTS53003` | Truy cập bị chặn bởi Conditional Access. | Mở tab Conditional Access, tìm policy bị fail và điều kiện liên quan. |
| `AADSTS50105` | Người dùng chưa được gán quyền truy cập ứng dụng yêu cầu assignment. | Kiểm tra enterprise application, user/group assignment. |
| `AADSTS50011` | Reply/redirect URI không khớp cấu hình ứng dụng. | Đối chiếu redirect URI của yêu cầu với App registration. |
| `AADSTS700016` | Không tìm thấy ứng dụng với App ID đã gửi trong directory đang dùng. | Kiểm tra client ID, tenant, việc đăng ký và consent ứng dụng. |
| `AADSTS7000215` | Client secret không hợp lệ. | Kiểm tra cấu hình credential của ứng dụng và quy trình xoay vòng secret an toàn. |

Thông báo lỗi có thể thay đổi theo luồng xác thực, phiên bản giao thức và cấu hình. Để xác định nguyên nhân, hãy ưu tiên **thông tin của chính sign-in event** và cấu hình hiện tại ở tenant có liên quan.

### Nhóm A: Sai tenant hoặc tài khoản

Dấu hiệu: người dùng đăng nhập được vào ứng dụng A nhưng thất bại ở ứng dụng B; lỗi nhắc đến user không tồn tại trong directory; hoặc ứng dụng thuộc tổ chức đối tác.

Hướng xử lý:

1. Xác minh Tenant ID được yêu cầu và tài khoản đang chọn trên màn hình đăng nhập.
2. Kiểm tra người dùng đã được mời hoặc tạo trong đúng tenant chưa.
3. Nếu là B2B guest, kiểm tra tình trạng invitation và khả năng truy cập resource tenant.
4. Đối chiếu app registration/enterprise application với tenant dự kiến; không đổi cấu hình đa tenant khi chưa hiểu mô hình truy cập.

### Nhóm B: MFA hoặc Conditional Access

Dấu hiệu: người dùng được yêu cầu thêm bước xác thực, nhận `AADSTS53003`, hoặc chỉ lỗi trên một loại thiết bị hay mạng.

Hướng xử lý:

1. Mở đúng sign-in event rồi kiểm tra **Authentication Details**.
2. Mở **Conditional Access** để tìm policy bị áp dụng, thất bại, hoặc chỉ ở chế độ **report-only**.
3. Kiểm tra các điều kiện liên quan: ứng dụng, danh tính, nhóm, địa chỉ mạng, trạng thái thiết bị và mức xác thực yêu cầu.
4. Đối chiếu với thời điểm thay đổi chính sách trong audit log.
5. Nếu có quyền và tính năng phù hợp, dùng công cụ **Conditional Access What If** để mô phỏng các điều kiện; kết quả mô phỏng chỉ hỗ trợ đánh giá, không thay thế sign-in event thực.

Không nên tắt MFA hoặc vô hiệu hóa toàn bộ Conditional Access chỉ để “xem có hết lỗi không”. Khi cần điều chỉnh, hãy xác định chính xác điều kiện, phạm vi ảnh hưởng và làm theo quy trình thay đổi của tổ chức.

### Nhóm C: Thiếu quyền vào ứng dụng

Dấu hiệu: xác thực có vẻ đã thành công nhưng người dùng vẫn không vào được ứng dụng hoặc gặp lỗi liên quan đến assignment/consent.

Kiểm tra **Enterprise applications** → ứng dụng liên quan → **Users and groups** hoặc thiết lập assignment phù hợp. Xác định nhóm/người dùng có được gán chưa, ứng dụng yêu cầu role nào và việc đồng bộ nhóm có hoàn tất không. Nếu người dùng vào được ứng dụng nhưng không dùng được chức năng cụ thể, tiếp tục kiểm tra **phân quyền trong chính ứng dụng**.

### Nhóm D: Lỗi cấu hình OAuth/OIDC hoặc workload

Dấu hiệu: chỉ lỗi khi chuyển hướng đăng nhập, pipeline thất bại hoặc tiến trình nền không lấy được token.

Kiểm tra App ID, Tenant ID, redirect URI, loại luồng xác thực và cấu hình app registration. Đối với service principal, kiểm tra hạn dùng credential hoặc chứng chỉ nhưng không sao chép secret vào phiếu hỗ trợ. Đối với managed identity, đối chiếu identity đã được gán và quyền ở resource đích; xem **managed identity sign-in logs**. Nếu vấn đề là quyền Azure RBAC sau khi lấy token thành công, hãy kiểm tra role assignment của tài nguyên.

## 6. Dùng audit log để tìm thay đổi dẫn đến sự cố

Sign-in log thường cho biết **sự cố phát sinh thế nào tại thời điểm xác thực**. Audit log giúp trả lời câu hỏi tiếp theo: **điều gì đã được thay đổi trước đó?**

Ví dụ một tài khoản hôm qua đăng nhập bình thường nhưng hôm nay bị yêu cầu MFA hoặc bị chặn. Audit log có thể giúp xác định xem gần thời điểm đó có thay đổi nào trong:

- **Conditional Access policy:** tạo, cập nhật, xóa hoặc đổi trạng thái chính sách.
- **User và group membership:** tạo, vô hiệu hóa tài khoản, thêm/xóa khỏi nhóm hoặc thay đổi thuộc tính liên quan.
- **Authentication methods:** đăng ký, xóa hoặc thay đổi thông tin phương thức xác thực.
- **Application configuration:** cấu hình enterprise application, app registration, permission, credential hoặc assignment.
- **Directory role assignment:** thay đổi quyền quản trị trong Microsoft Entra ID.

### Xem audit logs trong Portal

1. Vào [Microsoft Entra admin center](https://entra.microsoft.com/) và xác nhận tenant.
2. Mở **Microsoft Entra ID** → **Monitoring & health** → **Audit logs**.
3. Đặt khoảng thời gian **trước và trong lúc phát sinh lỗi**; một thay đổi cấu hình có thể xuất hiện trước sự cố nhiều giờ hoặc nhiều ngày.
4. Lọc theo **Activity**, **Category**, **Status**, **Target** hoặc **Initiated by** nếu có.
5. Mở audit event để xem target resources, actor, operation, trạng thái và các thuộc tính thay đổi được ghi nhận.

Các trường quan trọng:

| Trường | Mục đích |
|---|---|
| **Activity / Operation** | Xác định thao tác thay đổi gì. |
| **Date** | Xác định thời điểm thay đổi. |
| **Initiated by** | Xác định người dùng hoặc ứng dụng thực hiện. |
| **Target(s)** | Đối tượng bị thay đổi: user, group, application, policy… |
| **Result** | Cho biết thao tác thành công, thất bại hoặc kết quả khác. |
| **Modified properties** | Thông tin thuộc tính thay đổi khi nguồn log có cung cấp. |
| **Correlation ID** | Hỗ trợ liên hệ các sự kiện trong hoạt động thay đổi cấu hình. |

Một audit event ghi nhận thay đổi đã xảy ra, nhưng không tự chứng minh thay đổi đó **gây ra** lỗi đăng nhập. Để kết luận quan hệ nhân quả, phải xác nhận chính sách hoặc cấu hình liên quan thật sự được áp dụng trong sign-in event có vấn đề.

### Đọc kết hợp hai nguồn

```text
Sign-in log: người dùng bị chặn lúc 08:30 UTC
            │
            ├── Error: 53003
            ├── Conditional Access: policy "Require compliant device"
            └── Device: không đáp ứng điều kiện
                            │
                            ▼
Audit log: policy liên quan được sửa lúc 07:55 UTC
            │
            ├── Initiated by: administrator / automation
            └── Changed properties: điều kiện thiết bị / nhóm
                            │
                            ▼
Kiểm tra cấu hình hiện tại, phạm vi áp dụng và phê duyệt thay đổi
                            │
                            ▼
Kết luận có bằng chứng, xử lý và xác nhận bằng sign-in mới
```

Sơ đồ minh họa một chuỗi điều tra, không phải kết quả của tenant thật.

## 7. Xuất log sang Log Analytics để truy vấn bằng KQL

Nếu tổ chức cần phân tích dài hạn, đối chiếu nhiều lần đăng nhập hoặc dựng dashboard, quản trị viên có thể cấu hình **Diagnostic settings** tại Microsoft Entra để gửi sign-in logs và audit logs tới **Log Analytics workspace**, Storage account hoặc Event Hubs (tùy loại log, giấy phép và cấu hình được hỗ trợ).

Việc lưu giữ log mặc định trong Entra có thể phụ thuộc gói giấy phép, loại nhật ký và chính sách hiện hành. **Không nên giả định nhật ký luôn tồn tại vô thời hạn.** Hãy xác minh thời gian lưu hiện có và cấu hình xuất trước khi điều tra sự cố cũ. Xuất log cần được bật sớm; không khôi phục hồi tố những sự kiện đã hết thời gian lưu trong nguồn ban đầu.

Các bảng thường dùng trong Log Analytics:

| Loại dữ liệu | Bảng KQL thường gặp |
|---|---|
| Đăng nhập tương tác của người dùng | `SigninLogs` |
| Đăng nhập không tương tác của người dùng | `AADNonInteractiveUserSignInLogs` |
| Đăng nhập của service principal | `AADServicePrincipalSignInLogs` |
| Đăng nhập của managed identity | `AADManagedIdentitySignInLogs` |
| Audit log Microsoft Entra ID | `AuditLogs` |

Tên bảng và tập cột phụ thuộc loại dữ liệu đã cấu hình xuất và schema sẵn có trong workspace. Một workspace không có bảng hoặc không có dữ liệu chưa chắc có nghĩa không xảy ra sự kiện; có thể diagnostic setting chưa bật, sai tenant hoặc log chưa được ingest.

### Truy vấn 1: Các lần đăng nhập tương tác thất bại

```kusto
SigninLogs
| where TimeGenerated >= ago(24h)
| where ResultType != "0"
| project TimeGenerated, UserPrincipalName, AppDisplayName,
          IPAddress, ResultType, ResultDescription, CorrelationId
| order by TimeGenerated desc
```

`ResultType` bằng `"0"` thường thể hiện lần xác thực thành công; các giá trị khác có thể là mã lỗi. Truy vấn trên chỉ xem bảng đăng nhập tương tác; phải đổi bảng nếu đang điều tra non-interactive hoặc workload identity.

### Truy vấn 2: Điều tra một người dùng và một ứng dụng

```kusto
SigninLogs
| where TimeGenerated between (ago(7d) .. now())
| where UserPrincipalName =~ "user@contoso.example"
| where AppDisplayName has "Sales Portal"
| project TimeGenerated, AppDisplayName, ResultType,
          ResultDescription, ConditionalAccessStatus,
          IPAddress, CorrelationId
| order by TimeGenerated desc
```

Thay UPN và tên ứng dụng bằng giá trị thực tế. Truy vấn giúp so sánh các lần thành công/thất bại quanh thời điểm đổi chính sách.

### Truy vấn 3: Thay đổi thư mục liên quan đến ứng dụng hoặc chính sách

```kusto
AuditLogs
| where TimeGenerated >= ago(7d)
| where Category in ("Policy", "ApplicationManagement", "UserManagement")
| extend Actor = coalesce(
    tostring(InitiatedBy.user.userPrincipalName),
    tostring(InitiatedBy.app.displayName))
| project TimeGenerated, Category, ActivityDisplayName,
          Result, Actor, TargetResources, CorrelationId
| order by TimeGenerated desc
```

Các category có thể khác tùy hoạt động thực tế. Để tìm một sự kiện cụ thể, trước tiên xem những category và activity thực tế xuất hiện trong workspace rồi thu hẹp điều kiện. `TargetResources` là trường phức hợp; khi cần tên đối tượng, có thể tách dữ liệu bằng `mv-expand` hoặc truy cập phần tử phù hợp sau khi kiểm tra schema.

### Truy vấn 4: Tìm audit event theo từ khóa thao tác

```kusto
AuditLogs
| where TimeGenerated >= ago(7d)
| where ActivityDisplayName contains "Conditional Access"
| project TimeGenerated, ActivityDisplayName, Result,
          InitiatedBy, TargetResources, CorrelationId
| order by TimeGenerated desc
```

Nếu truy vấn không trả bản ghi, hãy kiểm tra thêm từ khóa, bảng dữ liệu, quyền, khoảng thời gian và cấu hình xuất. Truy vấn KQL chỉ đọc dữ liệu đã đến workspace, không thay thế việc mở bản ghi gốc trong Entra Portal khi cần phân tích Authentication Details.

## 8. Quy trình xử lý sự cố từng bước

Khi tiếp nhận yêu cầu “tôi không đăng nhập được”, áp dụng chuỗi kiểm tra sau:

1. **Xác nhận đúng tenant và ứng dụng.** Ghi Tenant ID, App ID nếu có, người dùng hoặc workload và mốc thời gian UTC.
2. **Phân loại luồng xác thực.** Interactive, non-interactive, service principal hay managed identity?
3. **Tìm sign-in event phù hợp.** Lọc bằng UPN/identity, ứng dụng, khoảng thời gian, Request ID hoặc Correlation ID.
4. **Đọc trạng thái và lỗi.** Ghi error code, failure reason, resource và context mạng/thiết bị.
5. **Kiểm tra bước xác thực.** Authentication Details có cho thấy MFA, phương thức hoặc điều kiện bổ sung chưa đáp ứng?
6. **Kiểm tra Conditional Access.** Xác định policy thực sự được áp dụng và nguyên nhân chặn nếu có.
7. **Tìm thay đổi trước sự cố.** Trong audit log, kiểm tra thay đổi liên quan đến user, group, application, phương thức xác thực hoặc policy.
8. **Phân biệt xác thực và phân quyền.** Nếu token được cấp nhưng ứng dụng vẫn báo 403, hãy kiểm tra app roles, API permissions, Azure RBAC hoặc quyền riêng của ứng dụng.
9. **Xử lý theo quyền hạn.** Sửa cấu hình chính xác, gán quyền theo quy trình phê duyệt hoặc chuyển đến người quản lý tenant/policy.
10. **Xác minh lại.** Yêu cầu thử đăng nhập mới, xác nhận event mới và ghi kết quả trước/sau.

Cũng nên ghi **những điều đã kiểm tra nhưng không thấy bằng chứng**, chẳng hạn “không có audit event thay đổi Conditional Access trong 48 giờ” sau khi đã xác nhận retention và bộ lọc. Điều này giúp tránh lặp lại bước điều tra và làm rõ giới hạn của kết luận.

## 9. Tình huống thực tế

### Tình huống A: Người dùng bị chặn sau thay đổi Conditional Access

**Hiện tượng:** Người dùng đăng nhập được hôm trước, nhưng hôm nay ứng dụng báo `AADSTS53003`.

**Điều tra:** Sign-in event cho thấy kết quả Failure và Conditional Access policy yêu cầu thiết bị compliant. Audit log ghi nhận policy vừa được cập nhật, thêm nhóm của người dùng vào phạm vi áp dụng.

**Kết luận có căn cứ:** Thay đổi policy có khả năng gây lỗi nếu điều kiện thiết bị từ sign-in event đúng là điều kiện mới được thêm. Nhóm quản trị cần xác nhận mục tiêu chính sách và trạng thái tuân thủ thiết bị, sau đó điều chỉnh phạm vi hoặc khắc phục thiết bị theo quy trình. Sau khi xử lý, kiểm tra sign-in event mới để xác nhận.

### Tình huống B: Người dùng B2B không truy cập được ứng dụng

**Hiện tượng:** Đối tác có tài khoản công ty nhưng nhận lỗi liên quan đến tenant hoặc tài khoản.

**Điều tra:** Sign-in log chỉ ra resource tenant khác home tenant hoặc tài khoản không tồn tại trong tenant được yêu cầu. Audit log cho thấy lời mời guest chưa được chấp nhận, hoặc tài khoản guest bị xóa.

**Hướng giải quyết:** Kiểm tra quy trình B2B invitation, tình trạng guest, enterprise application assignment và lựa chọn tài khoản khi đăng nhập. Không cấp quyền quá rộng chỉ để vượt qua lỗi truy cập.

### Tình huống C: Pipeline ngừng lấy được token

**Hiện tượng:** Ứng dụng chạy nền gặp lỗi `AADSTS7000215` sau khi một credential được thay đổi.

**Điều tra:** Mở service principal sign-in logs, đối chiếu app ID và mốc thời gian. Audit log có thể cho thấy thao tác thay đổi credential của ứng dụng.

**Hướng giải quyết:** Xác định pipeline dùng credential nào, kiểm tra cấu hình trong kho bí mật và quy trình xoay vòng. Ưu tiên managed identity hoặc workload identity federation nếu phù hợp để giảm rủi ro quản lý secret. Tuyệt đối không đưa client secret vào bản ghi sự cố.

### Tình huống D: Đăng nhập thành công nhưng API từ chối truy cập

**Hiện tượng:** Sign-in log báo Success nhưng API trả HTTP 403.

**Điều tra:** Xác thực Entra thành công, nên tiếp tục kiểm tra claim/role, quyền ứng dụng, consent, role assignment ở tài nguyên hoặc authorization trong API. Audit log hữu ích nếu có thay đổi user assignment hoặc app permission; Azure Activity Log hữu ích nếu Azure RBAC vừa thay đổi.

**Kết luận:** Đây có thể là lỗi **authorization** sau đăng nhập, không phải lỗi xác thực. Không nên sửa MFA hay Conditional Access khi chưa có bằng chứng các cơ chế đó gây ra 403.

## 10. Cảnh báo, lưu giữ và bảo vệ dữ liệu

Với hệ thống quan trọng, nhóm vận hành có thể tạo truy vấn định kỳ, workbook hoặc log alert trên dữ liệu được gửi vào Log Analytics để phát hiện xu hướng như số lượng lỗi tăng bất thường, cùng một ứng dụng liên tục thất bại hoặc thay đổi cấu hình nhạy cảm.

Khi triển khai, chú ý:

- **Quyền tối thiểu:** chỉ người có trách nhiệm mới được xem thông tin đăng nhập, IP, danh tính và audit event.
- **Bảo vệ dữ liệu cá nhân:** ẩn bớt UPN, IP hoặc thông tin người dùng khi chia sẻ ảnh chụp và báo cáo ngoài nhóm có thẩm quyền.
- **Thời gian lưu giữ:** kiểm tra chính sách và giấy phép Entra; đặt retention phù hợp cho workspace hoặc đích lưu trữ.
- **Độ trễ dữ liệu:** sign-in logs và log xuất sang workspace có thể không xuất hiện ngay lập tức.
- **Khác biệt dữ liệu:** các loại sign-in khác nhau có schema, điều kiện hiển thị và độ chi tiết riêng.
- **Chất lượng cảnh báo:** phân biệt lỗi người dùng nhập sai, yêu cầu MFA bình thường và tình huống cần can thiệp; tránh tạo cảnh báo gây nhiễu.
- **Giới hạn suy luận:** không kết luận xâm nhập tài khoản chỉ dựa vào vị trí IP, một lần thất bại hoặc một audit event đơn lẻ.

## 11. Bài thực hành: chẩn đoán một lần đăng nhập thất bại

Giả sử người dùng `user@contoso.example` báo lỗi khi truy cập `Sales Portal` lúc 15:30 giờ Việt Nam. Bạn là người vận hành có quyền đọc sign-in logs và audit logs trong tenant của tổ chức.

**Yêu cầu:**

1. Xác định đúng tenant; quy đổi giờ xảy ra lỗi sang **08:30 UTC**.
2. Trong interactive sign-in logs, lọc user, ứng dụng và khoảng thời gian quanh 08:30 UTC.
3. Tìm lần thử có trạng thái thất bại; ghi Error code, Failure reason, Correlation ID, IP và thông tin thiết bị.
4. Mở Authentication Details và Conditional Access để xác định có bước MFA hoặc policy nào tác động.
5. Trong audit logs, kiểm tra các thay đổi liên quan đến user, group, app và policy trước thời điểm lỗi.
6. Phân biệt giả thuyết được bằng chứng ủng hộ với giả thuyết chưa xác nhận.
7. Đề xuất một bước xử lý tương ứng với nguyên nhân thực tế và nêu cách xác minh bằng sign-in event mới.

**Mẫu báo cáo:**

| Mục | Cần điền |
|---|---|
| Tenant ID / ứng dụng | ID và tên ứng dụng đã xác nhận |
| User hoặc workload identity | Định danh phù hợp |
| Event time (UTC) | Thời điểm lỗi theo nhật ký |
| Sign-in type | Interactive, non-interactive, service principal hoặc managed identity |
| Status / Error code | Kết quả và mã lỗi |
| Authentication / Conditional Access | Bước hoặc policy liên quan |
| Audit evidence | Event thay đổi, thời điểm và actor nếu có |
| Root cause | Nguyên nhân đã xác minh hoặc cần điều tra tiếp |
| Hành động | Điều chỉnh được phê duyệt hoặc chuyển xử lý |
| Kết quả xác minh | Sign-in event mới và trạng thái sau xử lý |

Một bài thực hành hoàn chỉnh phải chỉ ra **bằng chứng trong sign-in log** cho triệu chứng, **bằng chứng trong audit log** nếu có thay đổi liên quan, và giải thích rõ lý do lựa chọn hướng xử lý. Nếu không có audit event liên quan, vẫn có thể hoàn thành điều tra bằng kết luận có giới hạn thay vì tự gán một thay đổi chưa quan sát được.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Người dùng bị `AADSTS53003`. Nguồn nào nên xem trước để hiểu điều kiện chặn?

A. Azure Activity Log của một storage account  
B. Sign-in event và tab Conditional Access  
C. Chỉ audit log của một resource group

**Đáp án: B.** Sign-in event cho biết chính sách và kết quả của lần thử đăng nhập cụ thể.

**Câu 2.** Người dùng báo lỗi ngay sau khi bị xóa khỏi nhóm ứng dụng. Cần nguồn nào để xác minh thay đổi nhóm?

A. Microsoft Entra audit logs  
B. Chỉ nhật ký truy cập blob  
C. Chỉ metric CPU của App Service

**Đáp án: A.** Audit logs có thể ghi lại việc thay đổi membership và chủ thể thực hiện.

**Câu 3.** Pipeline dùng service principal không lấy được token, nhưng bạn chỉ kiểm tra interactive user sign-ins. Bạn đã bỏ sót điều gì?

**Đáp án:** Cần mở nhóm **service principal sign-ins** và kiểm tra App ID, credential, tenant, quyền và luồng xác thực của ứng dụng.

**Câu 4.** Sign-in log báo Success, nhưng ứng dụng trả 403. Điều này có nghĩa MFA bị lỗi không?

**Đáp án:** Không. Token có thể đã được cấp thành công; cần kiểm tra authorization của API, app role, consent, Azure RBAC hoặc phân quyền riêng của ứng dụng.

**Câu 5.** Audit log có một thay đổi policy ngay trước khi sign-in thất bại. Có thể kết luận policy là nguyên nhân ngay không?

**Đáp án:** Chưa. Cần đối chiếu chính sách nào thực sự áp dụng cho sign-in event, các điều kiện bị thất bại và thời điểm có hiệu lực của thay đổi.

**Câu 6.** Vì sao phải kiểm tra loại sign-in và thời gian lưu giữ trước khi kết luận “không có log”?

**Đáp án:** Sự kiện có thể nằm trong non-interactive, service principal hoặc managed identity logs; dữ liệu có thể đến trễ, đã hết retention hoặc chưa được xuất sang workspace.

Kỹ năng quan trọng nhất khi chẩn đoán lỗi đăng nhập là **liên kết lần thử xác thực với thay đổi cấu hình có liên quan và kết luận dựa trên bằng chứng**. Sign-in log cho biết điều gì xảy ra trong luồng đăng nhập; audit log cho biết điều gì đã thay đổi trong tenant. Kết hợp chúng với thông tin ứng dụng, Conditional Access và quyền tài nguyên giúp xử lý sự cố chính xác hơn.
