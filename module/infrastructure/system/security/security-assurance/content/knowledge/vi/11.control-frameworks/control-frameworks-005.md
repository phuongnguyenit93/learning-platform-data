# Control Evidence: Bằng chứng kiểm soát trong Security Assurance

## 1. Vì sao một security control cần bằng chứng?

Hãy xem ba tuyên bố mà đội kỹ thuật thường đưa ra trong một cuộc đánh giá bảo mật:

- “Mọi tài khoản quản trị đã bật MFA.”
- “Dữ liệu khách hàng không thể bị truy cập xuyên tenant.”
- “Hệ thống có backup nên có thể phục hồi sau ransomware.”

Các phát biểu nghe có vẻ tích cực, nhưng **chưa đủ để kết luận**. Chúng chưa trả lời tài khoản nào thuộc phạm vi, cấu hình đang hoạt động ở môi trường nào, đường truy cập nào được kiểm tra, khả năng khôi phục được đo khi nào và ai xác nhận kết quả.

Giả sử doanh nghiệp đã bật MFA cho tài khoản quản trị thông thường nhưng bỏ sót tài khoản break-glass; integration test phân quyền chỉ kiểm tra GET API, không kiểm tra export; job backup hằng ngày báo thành công nhưng lần diễn tập restore gần nhất thất bại vì thiếu khóa giải mã. Sự hiện diện của controls không bảo đảm **mục tiêu bảo mật được đáp ứng trong phạm vi cần bảo vệ**.

**Control evidence (bằng chứng kiểm soát)** là những thông tin, bản ghi, kết quả kiểm thử, cấu hình, tài liệu hoặc hiện vật có nguồn gốc xác định, được sử dụng để **hỗ trợ hoặc bác bỏ kết luận** về thiết kế, việc triển khai và hiệu lực vận hành của một security control.

Trong chương **Control framework** thuộc module **SECURITY_SECURITY_ASSURANCE**, control evidence là điểm nối giữa:

1. **Risk scenario** và mục tiêu bảo mật cần đạt.
2. **Security requirements** và controls được lựa chọn theo framework hoặc baseline.
3. **Testing, monitoring và audit** để đánh giá thiết kế/vận hành.
4. **Findings, remediation, retest** và đánh giá rủi ro còn lại.
5. **Security assurance liên tục** trong phát triển và vận hành.

> **Control được ghi trong tài liệu khác với control được triển khai; control được triển khai khác với control có bằng chứng hoạt động hiệu quả.** Một hồ sơ assurance đáng tin phải phân biệt rõ ba trạng thái đó.

### Câu hỏi cốt lõi

Không hỏi chỉ “có screenshot MFA bật màu xanh không?”, mà hỏi: “**Tất cả danh tính có đặc quyền thuộc phạm vi nào đã được bảo vệ MFA bằng cơ chế và phiên bản nào, trong thời kỳ nào, có ngoại lệ gì, và cách kiểm tra nào cho thấy không còn đường truy cập bỏ qua?**”

## 2. Phân biệt control, assertion, artifact, evidence và conclusion

Các từ này có liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ với MFA |
| --- | --- | --- |
| **Security control** | Biện pháp tổ chức, kỹ thuật hoặc quy trình để xử lý một rủi ro/mục tiêu. | MFA bắt buộc với truy cập quản trị. |
| **Control objective** | Kết quả bảo vệ cần đạt, có phạm vi và điều kiện. | Tài khoản quản trị không thể truy cập tương tác qua đường thường chỉ bằng mật khẩu. |
| **Claim / assertion** | Tuyên bố đang cần chứng minh. | “Tất cả tài khoản quản trị tương tác trong phạm vi đều qua MFA theo chính sách.” |
| **Artifact / hiện vật** | Tệp, cấu hình, báo cáo, log hoặc bản ghi được thu thập. | Export policy từ Identity Provider, báo cáo đăng nhập, danh sách tài khoản. |
| **Control evidence** | Artifact được **đặt trong ngữ cảnh claim**, có nguồn gốc và được đánh giá mức hỗ trợ. | Policy export đối chiếu population admin, ngoại lệ và thử đăng nhập từ đường thực. |
| **Test of control** | Phương pháp kiểm tra thiết kế hoặc vận hành với tiêu chí trước. | Kiểm thử người dùng có quyền nhưng thiếu MFA, gồm đường bypass. |
| **Assessment finding** | Phát hiện điều kiện không đạt hoặc thiếu bằng chứng. | Một admin account không thuộc policy, hoặc evidence không đủ thời gian. |
| **Assurance conclusion** | Nhận định có phạm vi dựa trên lập luận và evidence. | “MFA hoạt động trên 27/28 tài khoản được kiểm tra; 1 ngoại lệ đang mở.” |

**Một file có thể là artifact nhưng chưa đủ làm evidence cho claim đang xét.** Ví dụ ảnh giao diện “MFA enabled” không chứng minh tài khoản dịch vụ, tài khoản break-glass hoặc đường truy cập legacy cũng được bảo vệ.

Ngược lại, evidence có thể **bác bỏ claim**: một kiểm thử truy cập không có MFA thành công là bằng chứng bất lợi cần ghi vào đánh giá, không phải lỗi báo cáo cần loại bỏ.

### Trạng thái cần phân biệt trong báo cáo

- **Implemented:** có biện pháp đã triển khai theo thông tin hiện có.
- **Design assessed:** thiết kế được đánh giá đối với yêu cầu và kịch bản.
- **Operating tested:** control đã được kiểm tra vận hành theo thời kỳ và phạm vi cụ thể.
- **Effective within scope:** kết luận đạt tiêu chí trong phần được kiểm chứng, với giới hạn được nêu.
- **Partially effective / failed:** có bằng chứng control không đạt một phần hoặc toàn bộ.
- **Not tested / insufficient evidence:** không đủ cơ sở kết luận, **không được tự chuyển thành PASS**.
- **Not applicable:** có lập luận hợp lệ rằng yêu cầu không áp dụng cho phạm vi xác định.
- **Exception:** có quyết định ngoại lệ được phê duyệt theo thẩm quyền; **không đồng nghĩa control đã đạt**.

## 3. Framework cung cấp yêu cầu; evidence chứng minh việc áp dụng

Một **control framework** cung cấp cấu trúc chọn, tổ chức và theo dõi các mục tiêu hoặc biện pháp bảo vệ. Tùy mục đích, tổ chức có thể tham chiếu:

| Nguồn tham chiếu | Cách sử dụng điển hình | Lưu ý khi lập evidence |
| --- | --- | --- |
| **ISO/IEC 27001** | Quản lý an toàn thông tin ở cấp hệ thống quản lý, lựa chọn và vận hành controls phù hợp. | Xác định phạm vi ISMS, rủi ro, controls được chọn và các hồ sơ vận hành; không mặc định mỗi tài liệu chứng minh mọi control hoạt động. |
| **ISO/IEC 27002** | Hướng dẫn thực hành controls an toàn thông tin. | Chuyển hướng dẫn thành requirement có thể kiểm tra theo hệ thống và dữ liệu thực. |
| **NIST SP 800-53** | Danh mục security/privacy controls hỗ trợ thiết kế và đánh giá hệ thống. | Chọn đúng control, enhancement và tham số theo baseline/tailoring của tổ chức; truy vết phạm vi test. |
| **NIST Cybersecurity Framework (CSF)** | Tổ chức quản trị và kết quả an ninh mạng theo chức năng/nhóm kết quả. | Một outcome thường cần nhiều controls/evidence; outcome không tự là cấu hình công nghệ cụ thể. |
| **CIS Controls / Benchmarks** | Các thực hành và hướng dẫn hardening hoặc safeguards có cấu trúc. | Kết quả scan phải gắn với phiên bản benchmark, hệ điều hành/tài sản, profile và ngoại lệ. |
| **SOC 2** | Hoạt động đánh giá báo cáo của tổ chức dịch vụ theo tiêu chí tin cậy trong phạm vi xác định. | Evidence phải phù hợp mô tả hệ thống, control và **thời kỳ** đánh giá; không coi report của nhà cung cấp là bằng chứng tất cả cấu hình khách hàng đều đúng. |
| **PCI DSS** | Yêu cầu bảo vệ dữ liệu thanh toán trong phạm vi áp dụng. | Trước tiên xác định data flow và phạm vi liên quan; đối chiếu yêu cầu và phương pháp kiểm tra theo phiên bản thực sự áp dụng. |

Các phiên bản, điều khoản, quyền sử dụng tài liệu và nghĩa vụ áp dụng phải được xác minh từ tài liệu được tổ chức phê duyệt. Bảng trên nhằm **phân biệt vai trò của framework**, không khẳng định một chuẩn tự động bắt buộc với mọi hệ thống.

### Mapping phải có lập luận, không chỉ gắn nhãn

Ví dụ một control “Object-level authorization cho Invoice API” có thể hỗ trợ nhiều yêu cầu về kiểm soát truy cập và bảo vệ dữ liệu. Tuy nhiên:

- Mapping một control tới framework **không chứng minh** control đã triển khai.
- Một test thành công cho GET invoice **không chứng minh** quyền sửa, xóa, export hoặc batch đã được xử lý.
- Một control có thể hỗ trợ **nhiều requirements**, nhưng mỗi claim cần kiểm tra phạm vi và phần chưa bao phủ.
- Một yêu cầu có thể cần **nhiều controls**: IAM policy, kiểm tra quyền nghiệp vụ, review định kỳ và monitoring.

Do đó cần giữ **control mapping register** có lý do liên kết, owner và phiên bản. Không nên dùng bảng ánh xạ checkbox làm bằng chứng duy nhất.

## 4. Mô hình Claim – Argument – Evidence (CAE)

Một cách trình bày assurance là **Claim – Argument – Evidence**:

- **Claim:** tổ chức khẳng định điều gì, trong phạm vi/phiên bản/thời kỳ nào?
- **Argument:** vì sao các cơ chế kiểm soát và phép kiểm tra đủ hỗ trợ claim?
- **Evidence:** những hiện vật thực tế nào cho thấy từng bước lập luận là đúng hoặc sai?

### Ví dụ claim về truy cập dữ liệu

**Claim:** “Trong release 2.8, các endpoint đọc hóa đơn thuộc phạm vi cho phép người dùng truy xuất **chỉ hóa đơn của tenant mình có quyền**, kể cả khi biết ID của tenant khác.”

**Argument:** “Tenant của principal lấy từ thông tin danh tính đã xác minh; truy vấn và authorization kiểm tra tenant/object; positive và negative tests bao phủ các vai trò và các endpoint được liệt kê; bản đã kiểm tra trùng với bản triển khai.”

**Evidence:**

1. API inventory có version và danh sách endpoint trong phạm vi.
2. Ma trận role/tenant/action được business/data owner duyệt.
3. Code/config của điểm kiểm soát authorization.
4. Integration test được phép và **không được phép**, kèm assertion trạng thái dữ liệu không bị tiết lộ.
5. Kết quả CI gắn commit, artifact/release và bằng chứng triển khai.
6. Các trường hợp chưa kiểm tra, exception và findings còn mở.

Nếu endpoint export chưa được kiểm tra, không mở rộng claim thành “**toàn bộ dữ liệu hóa đơn** được bảo vệ khỏi mọi đường truy cập” chỉ vì các test ở đường GET đã PASS.

~~~mermaid
flowchart LR
    A["Risk scenario + security objective"] --> B["Requirement / control"]
    B --> C["Claim có scope và thời kỳ"]
    C --> D["Argument về cơ chế bảo vệ"]
    D --> E["Test / observation / artifact"]
    E --> F["Assessment: đủ, thiếu, trái chiều"]
    F --> G["Finding / remediation / residual risk"]
    G --> H["Re-test + decision"]
    H --> E
~~~

**Phân biệt bằng chứng gốc và ý kiến đánh giá:** một báo cáo kiểm thử có kết quả PASS là dữ liệu quan sát; kết luận **toàn bộ control hiệu quả** là nhận định bổ sung, chỉ hợp lệ khi coverage, kỳ kiểm tra và các trường hợp bất lợi được xem xét.

## 5. Design effectiveness và operating effectiveness

Một control có thể thiết kế tốt nhưng không chạy, hoặc chạy đều nhưng **không xử lý đúng rủi ro**.

### 5.1. Design effectiveness: kiểm soát có được thiết kế đúng?

Đánh giá:

1. Control có giải quyết **đúng security objective và threat scenario** không?
2. Phạm vi của control có bao gồm tài sản, tài khoản và đường dữ liệu liên quan?
3. Có **đầu vào đáng tin**, logic quyết định rõ, fail-safe và tách quyền thích hợp?
4. Có owner, operator, tần suất thực hiện và quy trình xử lý ngoại lệ?
5. Có cách **phát hiện control không hoạt động** và cách xử lý khi phát hiện?

Ví dụ thiết kế “review quyền truy cập hằng quý” có thể thiếu bước thu hồi quyền không còn cần thiết. Dù nhân sự hoàn thành cuộc họp đúng hạn, thiết kế này chưa đủ bảo đảm quyền đã được xử lý.

### 5.2. Operating effectiveness: control có thực sự hoạt động?

Đánh giá:

- Trạng thái và hành vi **trong thời kỳ cần xác nhận**, không chỉ một thời điểm.
- Các population liên quan có được bao phủ đầy đủ không?
- Người có thẩm quyền có thực hiện hoạt động, đúng tần suất và phản ứng với ngoại lệ không?
- Kết quả có thể tái tạo và được kiểm tra độc lập ở mức phù hợp không?
- Có bằng chứng kiểm tra cả **đường thất bại và điều kiện không an toàn** không?

Ví dụ hệ thống yêu cầu MFA cho toàn bộ admin nhưng còn đường đăng nhập legacy: policy đúng trên giao diện chính không đủ chứng minh operating effectiveness của yêu cầu bảo vệ **mọi đường đăng nhập thuộc phạm vi**.

### 5.3. Control configuration khác control outcome

| Tình huống | Bằng chứng về thiết kế/cấu hình | Bằng chứng về vận hành/kết quả |
| --- | --- | --- |
| MFA quản trị | Chính sách, danh sách nhóm/tài khoản, sơ đồ login flows. | Test từng đường quan trọng, event xác thực và review ngoại lệ. |
| Authorization đa tenant | Đặc tả access matrix, code review, policy. | Negative test tenant B, xuất/sửa/batch và kết quả production phù hợp. |
| Backup | Lịch backup, lưu trữ, encryption và retention. | Restore drill đo RTO/RPO, đối soát dữ liệu sau phục hồi. |
| Log bảo mật | Event contract và sơ đồ pipeline. | Thử event nguồn→SIEM, alert, xử lý mất log và kiểm tra quyền truy xuất. |
| Quản lý lỗ hổng | Chính sách scan, SLA sửa, coverage scanner. | Báo cáo scope, finding/trạng thái, bản vá được xác minh và retest. |
| Kiểm soát thay đổi | Quy trình phê duyệt và yêu cầu review. | Mẫu thay đổi trong kỳ với approval, test, deploy và hậu kiểm. |

Không nên coi “tồn tại dashboard” là bằng chứng đủ cho **cả thiết kế lẫn vận hành**.

## 6. Các loại control evidence thường gặp

Evidence cần phù hợp loại control và mục đích kiểm tra. Một bộ evidence có thể kết hợp:

| Loại | Hiện vật điển hình | Giá trị | Giới hạn cần ghi |
| --- | --- | --- | --- |
| **Documentary** – tài liệu | Policy, standard, runbook, risk register, role matrix. | Chứng minh quy tắc thiết kế, trách nhiệm và phê duyệt. | Không tự chứng minh hoạt động đã diễn ra. |
| **Configuration** – cấu hình | IAM policy, cloud config, KMS settings, network rule, IaC. | Xác định trạng thái thiết kế hoặc triển khai tại thời điểm cụ thể. | Có thể không bao phủ effective access, đường bypass hoặc drift theo thời gian. |
| **Transaction / audit record** | Log cấp quyền, thay đổi chính sách, deployment event, request log. | Hỗ trợ truy vết hành động, thời điểm và kết quả. | Log có thể thiếu, sai đồng hồ hoặc không đủ nguồn gốc. |
| **Test evidence** | Integration/security tests, pen test, restore drill, failover exercise. | Thể hiện hành vi khi điều kiện kiểm tra xảy ra. | Chỉ trong phạm vi, phiên bản, dữ liệu và môi trường đã thử. |
| **Monitoring / operating record** | SIEM alert, telemetry, ingestion health, SLI, dashboard history. | Kiểm tra hoạt động liên tục và khả năng phát hiện sai lệch. | Chỉ có tín hiệu thu được nếu nguồn giám sát còn hoạt động. |
| **Review/approval evidence** | Biên bản review quyền, ký duyệt thay đổi, audit review, quyết định risk. | Chứng minh một quy trình quản trị đã được thực hiện. | Một chữ ký chưa chứng minh nội dung được review chính xác. |
| **Independent assessment** | Báo cáo kiểm toán/pentest của bên đủ năng lực, attestations. | Bổ sung mức tin cậy tùy phạm vi, phương pháp và tính độc lập. | Phải xét thời kỳ, ngoại lệ, hệ thống nằm trong/ngoài báo cáo. |
| **Physical / operational observation** | Quan sát thao tác có kiểm soát, thử kích hoạt cảnh báo, diễn tập. | Có thể xác nhận control đang vận hành. | Một lần quan sát không đại diện cho toàn bộ thời gian. |

### Direct evidence và indirect evidence

**Direct evidence** kiểm tra gần nhất với điều cần chứng minh. Ví dụ test người dùng tenant A không tải được file tenant B.

**Indirect evidence** chỉ hỗ trợ gián tiếp. Ví dụ chính sách tổ chức quy định phải kiểm tra phân quyền hoặc kết quả training cho developer. Hai loại có thể bổ sung nhau nhưng evidence gián tiếp khó thay thế một bài test hành vi đúng mục tiêu.

Khi lựa chọn bằng chứng, hãy hỏi **điều gì còn có thể sai ngay cả khi artifact này hoàn toàn đúng?** Câu hỏi đó thường bộc lộ khoảng trống cần kiểm tra thêm.

## 7. Chất lượng bằng chứng: đủ, đúng, đáng tin và còn hiệu lực

Một evidence repository lớn không đồng nghĩa mức assurance cao. Chất lượng cần được xem theo tiêu chí rõ ràng:

| Tiêu chí | Câu hỏi đánh giá | Ví dụ không đạt |
| --- | --- | --- |
| **Relevance** – liên quan | Artifact có hỗ trợ đúng claim và rủi ro được nêu? | Dùng log đăng nhập để chứng minh quyền đọc từng hóa đơn. |
| **Sufficiency** – đủ cơ sở | Tập evidence có đủ để kết luận, xét cả loại nguồn và phạm vi? | Một ảnh màn hình MFA cho hàng trăm tài khoản. |
| **Completeness** – bao phủ | Đã xét đầy đủ population, endpoint, vùng và exception? | Bỏ qua API export và service account. |
| **Accuracy** – chính xác | Trường dữ liệu, phép đo, kết quả và phạm vi có đúng? | Báo cáo “restore thành công” nhưng chỉ khởi động máy, chưa kiểm tra dữ liệu. |
| **Reliability** – đáng tin | Nguồn, cơ chế thu và khả năng giả mạo có được kiểm soát? | CSV tự chỉnh sửa không có truy vết nguồn. |
| **Freshness** – còn hiệu lực | Phù hợp phiên bản, thời gian, môi trường và trạng thái sau thay đổi? | Test trước khi đổi Identity Provider được dùng cho production mới. |
| **Repeatability** – tái hiện | Có input, bước chạy, tiêu chí kỳ vọng và môi trường? | “Đã thử thủ công, kết quả ổn” không có bước ghi lại. |
| **Integrity** – nguyên vẹn | Hiện vật có được bảo vệ chống sửa trái phép và truy vết khi chuyển giao? | Báo cáo bị sửa trực tiếp mà không lưu lịch sử. |
| **Independence** – độc lập phù hợp | Reviewer có đủ năng lực và mức tách biệt theo rủi ro? | Người sửa lỗi nghiêm trọng tự ký duyệt không có review bắt buộc. |
| **Confidentiality** – bảo mật evidence | Tài liệu có lộ secret, PII hay đường tấn công cho người không được phép? | Upload log có token khách hàng vào kho dùng chung. |

### Evidence gap khác control failure

Nếu bản kiểm thử chưa được lưu hoặc hệ thống logging lỗi, **không đủ bằng chứng** có thể là phát hiện assurance dù control thực tế có thể vẫn hoạt động. Nếu test xác nhận một người dùng đọc được dữ liệu ngoài quyền, đó là **bằng chứng control thất bại**. Hai trường hợp cần hành động khác nhau:

- **Evidence gap:** bổ sung phép kiểm tra/giám sát/thu thập bằng chứng; thận trọng với kết luận.
- **Control failure:** xử lý trạng thái không an toàn, đánh giá hậu quả, khắc phục nguyên nhân, retest và cập nhật risk.

Không “vá” một control failure bằng cách chỉ tăng số lượng tài liệu hoặc đổi trạng thái dashboard sang PASS.

## 8. Phạm vi, population, thời kỳ và tần suất kiểm tra

Khi auditor hỏi về control trong một quý, một cấu hình ở ngày cuối quý có thể không đủ chứng minh điều đã xảy ra **trong suốt quý**.

### 8.1. Point-in-time vs period-of-time

- **Point-in-time:** kiểm chứng trạng thái tại một mốc, ví dụ quyền bucket lúc 16:00 ngày đánh giá.
- **Period-of-time:** xem control đã vận hành qua một khoảng, ví dụ toàn bộ đợt cấp/thu hồi quyền trong quý.

Một **snapshot** phù hợp để chứng minh trạng thái ở mốc xác định. Để chứng minh kiểm soát diễn ra đều trong quý, có thể cần audit changes, job history, event logs, periodic observations và hồ sơ xử lý ngoại lệ.

### 8.2. Population và sample

**Population** là toàn bộ đơn vị thuộc phạm vi mà claim nói tới: tài khoản quản trị, các lần cấp quyền, endpoints, job backup, bucket, thay đổi production hoặc cảnh báo. **Sample** là phần được chọn để kiểm tra chi tiết.

Ví dụ bộ phận IAM có 600 lần thay đổi đặc quyền trong quý. Việc xem 30 thay đổi và thấy tất cả đều có phê duyệt có thể là evidence hữu ích **cho mẫu 30 trường hợp**, nhưng **không tự chứng minh 600/600 đều tuân thủ**. Phương pháp chọn mẫu, quy tắc đánh giá ngoại lệ và mức tin cậy phải phù hợp với mục đích kiểm toán.

Nếu dùng mẫu, cần ghi:

1. **Nguồn population** được kiểm tra tính đầy đủ như thế nào.
2. **Tiêu chí chọn mẫu**: ngẫu nhiên, rủi ro cao, bao phủ theo thời gian/đội hoặc chọn có mục đích.
3. **Kích thước mẫu và lý do**, không bịa một con số chung cho mọi control.
4. **Thuộc tính cần kiểm tra**, tiêu chí PASS/FAIL và cách xử lý thiếu artifact.
5. **Ngoại lệ và sai lệch** phát hiện; cách mở rộng đánh giá khi có dấu hiệu vấn đề hệ thống.
6. **Giới hạn kết luận**, không phóng đại kết quả mẫu thành toàn bộ population.

Không coi dữ liệu từ dashboard là population đầy đủ nếu chính dashboard bỏ sót các thay đổi ngoài pipeline hoặc tài khoản ở một Identity Provider phụ.

### 8.3. Tần suất của control và evidence

Một control hoạt động **mỗi lần giao dịch** cần bằng chứng khác với control **duyệt quyền định kỳ**. Một tài liệu review hằng quý có thể phù hợp để chứng minh một lần review trong quý, nhưng không chứng minh mọi access request đều được phê duyệt trước khi cấp.

Hãy gắn evidence với **tần suất control, thời gian phơi lộ chấp nhận được, mức rủi ro và độ biến động của hệ thống**.

## 9. Quy trình quản lý vòng đời control evidence

Bằng chứng không nên được thu gom ngẫu nhiên một tuần trước cuộc kiểm toán. Một chương trình trưởng thành quản trị từ lúc xác định yêu cầu đến khi evidence hết hiệu lực.

~~~mermaid
flowchart TD
    A["Control objective + framework mapping"] --> B["Định nghĩa claim, scope, period"]
    B --> C["Evidence plan + owner + criteria"]
    C --> D["Collect / generate safely"]
    D --> E["Validate completeness, origin, freshness"]
    E --> F{"Đủ hỗ trợ claim?"}
    F -- "Không" --> G["Finding / evidence gap / escalation"]
    G --> C
    F -- "Có" --> H["Protect, index, link to control"]
    H --> I["Review và assurance conclusion"]
    I --> J["Monitor changes, expiry, retention"]
    J --> K{"Thay đổi làm mất hiệu lực?"}
    K -- "Có" --> C
    K -- "Không" --> J
~~~

### Bước 1 — Định nghĩa control và câu hỏi kiểm chứng

Lấy security requirement và framework mapping làm đầu vào. Viết rõ **claim**, scope, tần suất, người sở hữu và điều kiện nào khiến claim bị bác bỏ.

Ví dụ control “Backup được phục hồi được” phải ghi kịch bản phục hồi, loại dữ liệu, môi trường, RTO/RPO và kết quả xác minh, thay vì chỉ có trường “Backup enabled”.

### Bước 2 — Lập evidence plan

Chọn hiện vật cần lấy, người chịu trách nhiệm, nguồn hệ thống, cách kiểm tra, thời điểm và cách bảo vệ. Nếu evidence chứa dữ liệu nhạy cảm, thiết kế redaction và quyền từ trước.

### Bước 3 — Thu thập đúng nguồn

Ưu tiên API export hoặc kết quả kiểm tra có **timestamp, source, scope, run ID và version**. Có thể dùng screenshots nếu phù hợp, nhưng ảnh không mang provenance có kiểm chứng có thể yếu hơn cấu hình và test report được quản lý phiên bản.

### Bước 4 — Kiểm tra và đối chiếu

Xác minh population, so trạng thái với tiêu chí, kiểm tra trường hợp không đạt và các ngoại lệ. Với pipeline tự động, theo dõi lỗi collector, permission, schema drift và dữ liệu quá hạn.

### Bước 5 — Lưu và liên kết

Gắn evidence vào control ID, asset, risk, release, period và người đánh giá. Bảo vệ quyền sửa/xóa, cấp quyền truy cập theo nhu cầu và bảo đảm người kiểm toán có thể xem **bản phù hợp đã được phép**.

### Bước 6 — Kết luận có giới hạn

Kết luận nêu **PASS/FAIL/PARTIAL/NOT TESTED**, cơ sở, phần đã bao phủ, thời kỳ và các phát hiện. Nếu kết quả thiếu tin cậy, giảm mức assurance; không tự hợp thức hóa bằng một nhãn “Complete”.

### Bước 7 — Làm mới, lưu giữ và kết thúc

Khi có thay đổi phiên bản/cấu hình/nguồn dữ liệu hoặc hết hạn giữ, evidence phải được xem lại. Chính sách retention quyết định khi nào hủy hoặc giữ theo nghĩa vụ/hồ sơ sự cố; không lưu vô thời hạn toàn bộ log nhạy cảm chỉ vì sợ mất bằng chứng.

## 10. Evidence metadata: hồ sơ phải có thể truy vết

Một bản ghi evidence có thể gồm:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **evidence_id** | ID ổn định giúp tham chiếu và phiên bản hóa. |
| **control_id / requirement_id** | Điều khoản cụ thể đang được chứng minh. |
| **claim và test_objective** | Phát biểu và điều kiện kiểm tra rõ ràng. |
| **scope** | Hệ thống, tài sản, môi trường, vai trò, tenant, API, vùng và phần ngoài phạm vi. |
| **assessment_period / collected_at** | Kỳ đánh giá và thời điểm thu thập. |
| **source / producer** | Hệ thống, người/công cụ tạo evidence và cơ chế truy xuất. |
| **methodology / population / sample** | Cách kiểm tra và mẫu/đơn vị được xét. |
| **expected vs observed** | Tiêu chí phải đạt và kết quả đã quan sát. |
| **result / limitations** | PASS/FAIL/PARTIAL/NOT TESTED và điều kiện giới hạn. |
| **artifact_ref / integrity_info** | Đường dẫn được quản lý quyền, phiên bản và cơ chế kiểm tra tính toàn vẹn khi cần. |
| **owner / reviewer** | Người chịu trách nhiệm control, người thu và người đánh giá. |
| **finding_id / remediation_ref** | Liên kết tới sai lệch, kế hoạch sửa và retest. |
| **retention / classification** | Nhóm bảo vệ và thời hạn lưu evidence. |

### YAML minh họa evidence record

Ví dụ dưới đây chỉ mô tả cấu trúc hồ sơ học tập, **không phải metadata của bài học hay schema của một công cụ bắt buộc**:

~~~yaml
evidence_id: EVID-AUTHZ-INVOICE-2026-011
control_id: CTRL-INVOICE-OBJECT-AUTHZ
requirement_id: REQ-DATA-TENANT-ISOLATION
framework_mappings:
  - "Internal access control standard"
claim: >
  In-scope invoice read operations reject principals
  from an unauthorized tenant.
scope:
  service: "invoice-api"
  release: "2.8"
  environment: "test and verified production deployment"
  endpoints:
    - "GET /api/invoices/{id}"
  exclusions:
    - "Bulk export is assessed under a separate test"
assessment_period:
  from: "2026-11-20"
  to: "2026-11-28"
collection:
  timestamp: "2026-11-28T02:00:00Z"
  producer: "authorized-ci-security-test"
  test_run: "run-8421"
  source_revision: "example-commit-id"
test_method:
  positive: "Tenant A reads authorized invoice A"
  negative: "Tenant A cannot read invoice B"
  expected: "No unauthorized invoice content returned"
observed:
  positive: "PASS"
  negative: "PASS"
result: "PASS within stated scope"
artifact_ref: "restricted-evidence-repo/authz/run-8421"
integrity_reference: "Managed artifact version, validated by repository"
limitations:
  - "Export endpoints have separate open assessment"
control_owner_role: "Invoice Service Owner"
assessor_role: "Security Assurance"
review_status: "Reviewed for stated scope"
reassessment_triggers:
  - "Authorization logic or tenant model changes"
  - "New invoice data access path"
~~~

Tất cả ID, thời gian, đường dẫn, kết quả và đối tượng trong mẫu là **giả định minh họa**, không phải báo cáo test có thật. Trong dự án thực tế, phải lưu hiện vật thực, test run, phiên bản deploy và quyết định review tương ứng.

### Đường dẫn file không đủ làm bằng chứng

Một URI đến kho evidence có thể hỏng, bị thay nội dung hoặc không còn quyền truy xuất. Hệ thống quản lý evidence nên xác nhận tồn tại, phiên bản, nguồn và tình trạng của artifact, đồng thời có cách cho phép reviewer đủ quyền xem nội dung theo chính sách.

## 11. Bảo toàn tính toàn vẹn, provenance và chain of custody

Khi security control bị nghi thất bại, evidence có thể được sử dụng trong điều tra sự cố, đánh giá nội bộ, kiểm toán độc lập hoặc tranh chấp. **Nguồn gốc và tính toàn vẹn** trở nên đặc biệt quan trọng.

### 11.1. Provenance: evidence đến từ đâu?

Nên xác định:

- Hệ thống nào đã phát sinh hiện vật, ở môi trường/phiên bản nào.
- Người hoặc danh tính dịch vụ nào thu thập và bằng cơ chế gì.
- Dữ liệu gốc đã trải qua các bước lọc, masking, parse, chuyển định dạng nào.
- Cách phân biệt thời điểm **sự kiện xảy ra** với thời điểm **thu thập/tải lên**.
- Evidence có thể được tái tạo bằng truy vấn hoặc test method nào.

Nếu log được trích từ SIEM, cần hiểu SIEM có nhận đầy đủ từ các nguồn hay không; một bảng xuất CSV không tự chứng minh đường upstream đầy đủ.

### 11.2. Integrity: evidence có bị sửa không?

Các biện pháp có thể gồm phân quyền viết/xóa, versioning, retention protection, lưu bản gốc và bản đã redacted riêng, kiểm tra hash/chữ ký trong trường hợp phù hợp và audit khi có người truy xuất hoặc chỉnh sửa.

**Hash không chứng minh provenance hoặc completeness chỉ bằng bản thân nó.** Nếu giá trị hash tham chiếu được tạo sau khi tệp đã bị sửa hoặc không được bảo vệ, so khớp hash không giúp chứng minh tệp ban đầu đúng. Muốn có giá trị, phải quản lý thời điểm và nguồn tạo giá trị tham chiếu.

### 11.3. Chain of custody

Với hiện vật điều tra cần mức tin cậy cao, ghi **ai thu thập, thời gian, công cụ, phạm vi, cách bảo quản, ai được truy cập, mọi lần sao chép/chuyển giao và kiểm tra integrity**. Không mặc định mọi screenshot phục vụ audit đều phải có chain-of-custody pháp chứng đầy đủ; mức bảo vệ phải **tương xứng rủi ro và mục đích sử dụng**.

### 11.4. Bảo vệ dữ liệu trong evidence

Evidence có thể chứa PII, secret, topology, đường khai thác và log của khách hàng. Phải:

- Giới hạn quyền truy cập theo vai trò và nhu cầu công việc.
- Giảm thiểu nội dung, dùng mẫu/synthetic data, masking hoặc pseudonymization nếu phù hợp.
- Không đưa mật khẩu, access token, private key hoặc nội dung dữ liệu nhạy cảm không cần thiết vào bằng chứng.
- Lưu bản gốc có bảo vệ riêng khi phải giữ để điều tra, bản chia sẻ đã redacted phải có ghi nhận biến đổi.
- Quản lý retention, backup, export và việc chia sẻ cho assessor hoặc nhà cung cấp.

Redaction giúp giảm lộ dữ liệu nhưng cũng có thể **làm mất thuộc tính cần thiết để đánh giá**. Cần xác định reviewer cần thấy những trường nào, và một nguồn được bảo vệ để đối chiếu khi cần.

## 12. Case study A: bằng chứng phân quyền SaaS đa tenant

### Bối cảnh

Nền tảng hóa đơn SaaS phục vụ nhiều doanh nghiệp. Một security requirement quy định: **chủ thể của tenant A không được đọc, sửa hoặc xuất hóa đơn của tenant B**.

Đội phát triển nói “Authorization đã triển khai tại API Gateway”; kiểm thử bảo mật phát hiện một endpoint bulk export dùng service account có quyền rộng và không kiểm tra lại tenant.

### Bước 1 — Xác định claim và phạm vi

**Claim rộng chưa được chứng minh:** “Không tồn tại truy cập xuyên tenant trong toàn hệ thống.”

**Claim có thể kiểm tra:** “Đối với các endpoint GET/PATCH invoice được liệt kê trong bản phát hành, authorization từ chối yêu cầu từ tenant không có quyền; export được đánh giá theo đường riêng.”

Scope phải nêu release, môi trường, actor/roles, endpoint, dữ liệu, cache, batch/worker và các đường ngoài phạm vi. Chỉ dựa vào test gateway sẽ bỏ sót **đường gọi trực tiếp tới service, tác vụ nền hoặc object storage**.

### Bước 2 — Tạo phép kiểm chứng

| Test ID | Điều kiện | Kỳ vọng | Evidence cần có |
| --- | --- | --- | --- |
| **TEN-01** | User A đọc invoice A đúng quyền. | Thành công, dữ liệu trong phạm vi. | Test run và dữ liệu kỳ vọng đã kiểm soát. |
| **TEN-02** | User A đọc invoice B khác tenant. | Bị từ chối, không lộ nội dung B. | Negative test, response đã redacted. |
| **TEN-03** | User A sửa invoice B. | Không sửa dữ liệu; sự kiện được audit nếu yêu cầu. | Test, đối soát DB và audit log. |
| **TEN-04** | User thiếu quyền export tạo job. | Từ chối; không có file được tạo. | API/job test và object store state. |
| **TEN-05** | Worker nhận event có tenant bị thay. | Không xuất dữ liệu ngoài scope. | Test event replay/tamper, service account permissions. |
| **TEN-06** | Người B biết URL file export của A. | Không tải được file; quyền được áp tại đường thực. | Test CDN/storage/link và log truy cập. |
| **TEN-07** | Token/permission hết hiệu lực. | Không tiếp tục được cấp quyền trái chính sách. | Test phiên, cache và chính sách thu hồi. |

**Bằng chứng kết luận:** kết quả tests theo đúng phiên bản, coverage inventory, code review điểm authorization, quyền của service accounts, cấu hình môi trường và xác nhận release đã triển khai.

### Bước 3 — Đánh giá kết quả trái chiều

Nếu TEN-02 PASS nhưng TEN-04 FAIL, kết luận không được là “Authorization PASS” cho toàn bộ dữ liệu. Phải phân tách:

- Control ở GET đã có evidence hiệu quả trong scope đã thử.
- Đường bulk export có **control failure** và rủi ro tiết lộ dữ liệu.
- Cần containment/remediation, test toàn bộ đường tương tự và đánh giá dữ liệu đã bị ảnh hưởng.

### Bước 4 — Retest và cập nhật residual risk

Engineering sửa export authorization tại service/worker, bổ sung negative tests và giới hạn quyền service account. Assessor xác nhận commit/release, deployment và chạy lại các case liên quan. **Likelihood** của kịch bản truy cập sai có thể giảm khi control được chứng minh hoạt động; **impact nếu vẫn xảy ra rò rỉ** chưa chắc giảm trừ khi có bằng chứng giới hạn phạm vi/hậu quả.

Không tự coi ticket “Done” hoặc PR merge là evidence hiệu quả vận hành; phải **đọc kết quả đúng phiên bản môi trường đích**.

## 13. Case study B: Cloud storage và bằng chứng cấu hình

Một tổ chức có nhiều bucket chứa dữ liệu khách hàng. Control objective: “Không có bucket nhạy cảm thuộc phạm vi production cho phép public read ngoài ngoại lệ đã được phê duyệt”.

### Evidence plan

1. **Population:** danh sách bucket từ cloud inventory, đối chiếu account/project/region và data classification.
2. **Control design:** policy và baseline xác định cấu hình không công khai và quy trình ngoại lệ.
3. **Point-in-time test:** đọc effective public access settings và IAM/bucket policy trên mỗi bucket trong scope.
4. **Period test:** log thay đổi policy, IaC deployment và config drift alerts để đánh giá trong khoảng liên quan.
5. **Negative test:** dùng danh tính không có quyền để xác minh không tải được object thử hợp lệ ở môi trường được phép.
6. **Evidence of response:** nếu phát hiện public access, có finding, correction, readback và đánh giá khoảng phơi lộ.

### Vì sao “Bucket private = PASS” có thể sai?

- Inventory thiếu một project chứa dữ liệu nhạy cảm.
- Bucket chính không public nhưng một CDN, signed link hoặc IAM grant tạo đường truy cập khác.
- Snapshot kiểm tra lúc audit diễn ra sau khi bucket vừa được sửa; **không chứng minh cả tháng trước**.
- Control chỉ có thể chứng minh **trạng thái hiện tại**, không kết luận dữ liệu không từng bị exfiltrate.
- Evidence về nơi lưu không tự chứng minh dữ liệu nhạy cảm đã được phân loại đúng ở data catalog.

### Claim có giới hạn

“Các bucket production đã được đối chiếu trong inventory tại thời điểm đánh giá không cho phép public read theo đường cấu hình được kiểm tra; đường CDN và thay đổi trong kỳ được đánh giá riêng.” Câu này hẹp nhưng đáng tin hơn “cloud đã hoàn toàn an toàn”.

## 14. Case study C: Backup và restore evidence

**Control objective:** dữ liệu giao dịch trọng yếu có thể được phục hồi sau kịch bản mất dữ liệu hoặc ransomware trong mục tiêu phục hồi được business owner phê duyệt.

Đội vận hành đưa ra một báo cáo “Backup job SUCCESS 100%”. Đây là bằng chứng **backup job đã báo hoàn tất**, chưa phải bằng chứng **restore được và dữ liệu còn nhất quán**.

### Kịch bản kiểm tra

| Thành phần | Câu hỏi | Evidence |
| --- | --- | --- |
| **RPO** | Dữ liệu có thể lùi tối đa bao xa theo điểm phục hồi? | Recovery point thực tế, các giao dịch cuối, đối soát. |
| **RTO** | Mất bao lâu để phục hồi dịch vụ theo định nghĩa nghiệp vụ? | Timeline diễn tập từ mốc khởi đầu đến khi giao dịch hoạt động lại. |
| **Integrity** | Dữ liệu sau restore có nhất quán với trạng thái hợp lệ? | So sánh số lượng, checksum/tổng kiểm soát nghiệp vụ, test giao dịch. |
| **Secrets/keys** | Bản sao có thể giải mã và sử dụng khi tài khoản chính bị mất không? | Diễn tập truy cập khóa, phục hồi quyền theo quy trình. |
| **Isolation** | Backup có thể bị xóa/mã hóa cùng sự cố chính không? | Kiểm tra quyền, miền lỗi, immutable setting nếu áp dụng, test quyền xóa. |
| **Recovery repeatability** | Có hướng dẫn, owner và evidence từ nhiều lần diễn tập? | Runbook version, lịch sử drills, vấn đề chưa khắc phục. |

### Khi test thất bại

Giả sử restore bị lỗi do thiếu secret decryption key. Control bảo vệ dữ liệu sao lưu có thể đang hoạt động, nhưng claim “có thể phục hồi” **chưa đạt**. Nhóm phải mở finding, sửa quản lý khóa/quy trình, diễn tập lại và xác nhận dữ liệu dùng được.

**Không đổi báo cáo thành PASS** chỉ vì backup đã chạy lại. Phần rủi ro còn lại về mất dữ liệu/gián đoạn phải được cập nhật dựa trên khả năng phục hồi thực tế.

## 15. Evidence automation và security assurance liên tục

Thu thập bằng tay theo đợt có thể làm evidence nhanh cũ, mất ngữ cảnh và gây gánh nặng cho đội vận hành. **Evidence-as-code / continuous control monitoring** biến phép kiểm tra có phạm vi thành công việc lặp lại, truy vết theo lần chạy và cảnh báo khi điều kiện thay đổi.

### Kiến trúc tham khảo

~~~mermaid
flowchart LR
    A["Risk + Control register"] --> B["Control tests / evidence contracts"]
    C["CI/CD + IaC"] --> B
    D["Cloud/IAM/DB/Logs"] --> E["Evidence collectors"]
    B --> E
    E --> F["Normalize + validate provenance"]
    F --> G[("Protected evidence repository")]
    G --> H["Control dashboards / Review"]
    H --> I["Finding / remediation / risk decision"]
    I --> B
    J["Change events / expiry monitor"] --> E
~~~

### Yêu cầu với một automated evidence collector

- Chỉ dùng **quyền truy cập cần thiết** để lấy evidence, tránh thu secret thừa.
- Ghi **source, timestamp, environment, account/region, API version và collector version**.
- Kiểm soát **missing source / failed query / partial pagination** thay vì mặc định coi kết quả rỗng là PASS.
- Đảm bảo inventory và mapping không mất nguồn mới; theo dõi drift về số lượng assets.
- Tách **observed state** khỏi **expected policy**, tạo result cùng lý do.
- Có cơ chế retry, alert và hậu kiểm khi collector ngừng hoạt động.
- Lưu bằng chứng theo retention, truy xuất theo quyền, redaction và lịch sử phiên bản.
- Cung cấp cách **replay hoặc tái kiểm tra** khi auditor đặt câu hỏi về kết quả.

### Ví dụ pseudocode kiểm tra quyền public

Đoạn này minh họa logic điều khiển, **không phải đoạn script cloud có thể dùng ngay**:

~~~text
assets = inventory.list_in_scope(classification="Confidential")
if assets.status != COMPLETE:
    record("INSUFFICIENT_EVIDENCE", reason="Inventory not complete")
    stop_assessment()

for asset in assets:
    response = cloud.read_effective_access_policy(asset)
    if response.failed or response.incomplete:
        record(asset, "NOT_TESTED", reason=response.error)
        continue

    exception = exceptions.find_active_for(asset)
    if response.public_read_enabled and not exception.valid:
        record(asset, "FAIL", observed=response.safe_summary)
        create_finding(asset, owner=asset.control_owner)
    elif response.public_read_enabled and exception.valid:
        record(asset, "EXCEPTION", approval=exception.reference)
    else:
        record(asset, "PASS", checked_at=response.timestamp)

publish_results_with_scope_version_and_artifact_refs()
~~~

Điều quan trọng không phải cú pháp công cụ, mà là **không tự biến lỗi thu thập thành PASS** và phải giữ được mối liên kết giữa population, result, exception và bằng chứng gốc.

### CI/CD và production là hai nguồn evidence khác nhau

Một policy-as-code test trong pull request có thể xác minh IaC không chứa cấu hình public trong phần đã kiểm tra. Nó **không tự chứng minh** production không bị sửa bằng tay, không có tài sản nằm ngoài IaC hoặc các đường cấp quyền khác không mở truy cập.

Nên kết hợp **shift-left kiểm thử trước deploy** và **kiểm tra trạng thái thực trong vận hành**, tùy mức rủi ro và quyền quan sát.

## 16. Phương pháp đánh giá mẫu và sai lệch

Khi một control được vận hành hàng nghìn lần trong kỳ, kiểm tra tất cả có thể khó. Tổ chức cần phương pháp chọn mẫu tương xứng rủi ro, hoặc kiểm tra tự động 100% cho những thuộc tính khả thi.

### Ví dụ: cấp quyền đặc quyền

Population ban đầu: 600 sự kiện cấp quyền trong quý. Chọn kiểm tra 30 sự kiện trên nhiều tuần, nhóm ứng dụng và mức quyền. Kết quả: 28 có phê duyệt đầy đủ, 2 không có bằng chứng phê duyệt trước khi cấp.

**Không nên kết luận:** “Chỉ 2/30 thất bại, vậy tỷ lệ lỗi toàn hệ thống chính xác là 6,67%.”

**Nên kết luận:** “Trong 30 sự kiện được chọn theo phương pháp đã nêu, 2 trường hợp không đáp ứng bằng chứng phê duyệt; cần đánh giá mức độ hệ thống của sai lệch và tác động tới kết luận cho population.”

Các hành động kế tiếp có thể:

1. Xác minh hai trường hợp có thực sự không được phê duyệt hay artifact bị thất lạc.
2. Kiểm tra quyền hiện tại và hậu quả nếu có quyền được cấp sai.
3. Mở rộng mẫu hoặc kiểm tra toàn bộ nhóm có đặc tính tương tự theo đánh giá rủi ro.
4. Đánh giá nguyên nhân của process/automation, sửa và retest.
5. Không đưa mức kết luận vượt bằng chứng và tiêu chí kiểm toán được áp dụng.

### Đừng nhầm coverage với quality

Kiểm tra 100% bucket bằng một scanner cấu hình **không đồng nghĩa** đã kiểm tra tất cả đường chia sẻ dữ liệu nếu scanner không hiểu CDN hoặc signed URL. Kiểm tra 30 trường hợp theo phương pháp chọn mẫu đúng và có thêm test hiệu lực có thể cung cấp bằng chứng mạnh cho claim cụ thể hơn một bảng 100% dựa trên dữ liệu sai.

## 17. Audit evidence request và evidence pack

Một cuộc audit thường yêu cầu giải trình **control nào, trong hệ thống nào, qua thời gian nào và vì sao kết luận phù hợp**. Chuẩn bị evidence pack theo control sẽ hiệu quả hơn khi mỗi đội gửi một thư mục không có metadata.

### Cấu trúc evidence pack khuyến nghị

1. **Cover sheet:** scope, kỳ đánh giá, control ID và owner, framework mapping.
2. **Control narrative:** mục tiêu, cơ chế, trách nhiệm, tần suất và điểm kiểm soát.
3. **Evidence index:** danh sách artifact, thời gian, nguồn, phiên bản và quyền truy xuất.
4. **Population/method:** nguồn population, tiêu chí chọn mẫu và kiểm tra completeness.
5. **Results:** phép test, đối chiếu expected/observed, các ngoại lệ và tình huống không đạt.
6. **Findings/remediation:** phát hiện, impact, kế hoạch, người chịu trách nhiệm và retest.
7. **Assurance conclusion:** kết luận có giới hạn và residual risk/approval liên quan.

### Ví dụ evidence request

**Yêu cầu:** “Chứng minh quy trình thu hồi quyền của nhân viên nghỉ việc đã hoạt động trong quý 3 trên các hệ thống thuộc phạm vi.”

**Không đủ:** gửi chính sách HR “phải thu hồi trong 24 giờ” và một screenshot user bị vô hiệu hóa hôm nay.

**Cần xem:** population nhân viên nghỉ việc và thay đổi trạng thái danh tính trong kỳ, danh sách ứng dụng/quyền liên quan, thời gian yêu cầu/thu hồi thực tế, test hoặc đối chiếu theo phương pháp được chấp thuận, trường hợp trễ/ngoại lệ, bằng chứng xử lý và quyền vẫn còn sau khi nghỉ.

Nếu một SaaS không có log lịch sử thu hồi hoặc nằm ngoài hệ thống IAM tập trung, **phải nêu khoảng trống** và đánh giá phần tác động thay vì chỉ tuyên bố “HR đã duyệt”.

### Evidence không phải chứng nhận

Một evidence pack tốt giúp assessor đưa ra kết luận **trong phạm vi được kiểm tra**; nó không tự tạo chứng nhận ISO, báo cáo SOC 2 hay chứng minh tuân thủ mọi nghĩa vụ. Những kết luận chính thức phụ thuộc chuẩn áp dụng, tư cách người đánh giá, phương pháp và quy trình tương ứng.

## 18. Quản lý findings, ngoại lệ và retest

Evidence không chỉ làm đẹp báo cáo. Nếu nó cho thấy control thiếu, hoạt động sai hoặc không đủ bằng chứng, cần **đường xử lý tới khi vấn đề được giải quyết hoặc rủi ro được quyết định đúng thẩm quyền**.

### Phân loại vấn đề

| Tình huống | Cách ghi | Hướng xử lý |
| --- | --- | --- |
| Control chưa tồn tại nhưng requirement áp dụng. | Control design/implementation gap. | Thiết kế/triển khai, đánh giá rủi ro và test. |
| Control có nhưng không hoạt động đúng. | Operating effectiveness failure. | Khoanh vùng, sửa, kiểm chứng lại, tìm nguyên nhân. |
| Không đủ evidence kết luận. | Evidence gap / NOT TESTED. | Kiểm tra thu thập, nguồn, coverage, thực hiện test thích hợp. |
| Đạt trong scope nhỏ nhưng chưa xét đường khác. | Partial coverage. | Thu hẹp claim hoặc mở rộng đánh giá. |
| Có ngoại lệ được phê duyệt hợp lệ. | Exception with risk decision. | Kiểm tra scope, hạn, bù đắp, trigger review. |
| Test đã đạt sau sửa nhưng sản xuất chưa cập nhật. | Remediation pending deployment/verification. | Xác nhận release production và retest phạm vi thực tế. |

### Quy trình khép kín

**Finding → Owner → Priority → Treatment plan → Implementation → Re-test → Evidence review → Residual risk decision → Monitoring.**

Mốc **“code merged”** không đồng nghĩa **“rủi ro đã giảm trên production”**. Một lần test ở staging không chứng minh bản phát hành đích đã chạy đúng. Kết luận sau sửa nên giữ kết quả test cũ (FAIL), kết quả mới (PASS), **phiên bản và thời điểm** để bảo đảm truy vết lịch sử.

### Quyền chấp nhận rủi ro

**Control owner** giải trình thiết kế và vận hành control. **Risk owner** hoặc người có thẩm quyền theo governance quyết định xử lý/chấp nhận residual risk trong phạm vi và điều kiện được giao. **Assessor** kiểm tra evidence và cung cấp kết luận, không tự động có quyền phê duyệt ngoại lệ.

Không coi acceptance là control đã hiệu quả: nó là **quyết định quản trị** về rủi ro còn lại, có thể có hạn và điều kiện. Những nghĩa vụ pháp lý hoặc hợp đồng bắt buộc không tự được miễn trừ bằng việc ký một form nội bộ.

## 19. Vai trò và RACI trong quản trị evidence

| Vai trò | Đóng góp chính |
| --- | --- |
| **Control owner** | Định nghĩa mục tiêu, phạm vi, tần suất, trách nhiệm cung cấp evidence và xử lý sai lệch. |
| **Control operator** | Vận hành biện pháp, ghi sự kiện, cung cấp thông tin về kết quả và lỗi thực tế. |
| **Service/system owner** | Xác nhận kiến trúc, phiên bản và hiệu quả control trên dịch vụ. |
| **Data/business owner** | Đánh giá hậu quả nghiệp vụ, mức nhạy cảm dữ liệu và quyền được phép. |
| **Evidence platform owner** | Quản lý thu thập, lưu trữ, integrity, quyền và retention của evidence. |
| **Security assurance / assessor** | Thiết kế cách kiểm tra độc lập khi phù hợp, đánh giá chất lượng và đưa ra kết luận có giới hạn. |
| **Risk owner** | Quyết định rủi ro còn lại theo thẩm quyền và điều kiện áp dụng. |
| **Internal/external auditor** | Đánh giá theo phạm vi, chuẩn và chương trình kiểm toán được giao. |
| **Privacy/legal/compliance** | Xác nhận nghĩa vụ xử lý và chia sẻ evidence nhạy cảm, retention và điều kiện pháp lý khi cần. |

### Ví dụ RACI cho kiểm soát IAM

**R** = trực tiếp thực hiện, **A** = chịu trách nhiệm cuối cùng, **C** = tham vấn, **I** = được thông báo. Bảng minh họa:

| Hoạt động | IAM/control owner | IAM operator | Assurance | Risk owner | Business/data owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Xác định mục tiêu và control evidence plan | **A/R** | C | C | I | C |
| Export population và vận hành quy trình kiểm tra quyền | **A** | **R** | C | I | C |
| Đánh giá completeness/evidence và test độc lập | C | C | **A/R** | I | C |
| Khắc phục quyền sai và retest vận hành | **A** | **R** | C | I | C |
| Quyết định chấp nhận residual risk có điều kiện | C | I | C | **A/R** | C |

RACI thật cần được phê duyệt theo tổ chức; các tình huống có nhiều chủ thể kinh doanh hoặc nghĩa vụ riêng phải bổ sung cấp quyết định phù hợp.

## 20. Bảng scorecard assurance và chỉ số

Một dashboard evidence có thể giúp biết controls nào **đã được kiểm tra**, nhưng tránh biến số lượng artifact thành mục tiêu cuối.

| Chỉ số | Câu hỏi quản trị | Bẫy cần tránh |
| --- | --- | --- |
| **Control coverage** | Bao nhiêu control/requirement thuộc phạm vi có evidence plan và owner? | Mẫu số inventory thiếu và mapping sai. |
| **Evidence freshness** | Bao nhiêu evidence còn hợp lệ với thay đổi và kỳ đánh giá? | Dùng tuổi tệp thay cho việc kiểm tra có thay đổi làm mất hiệu lực không. |
| **Operating test pass rate** | Kiểm thử có kết quả như kỳ vọng ở scope nào? | Loại bỏ NOT TESTED/FAIL khỏi mẫu số để làm đẹp tỷ lệ. |
| **Evidence gap count/age** | Những claim nào chưa đủ bằng chứng và tồn tại bao lâu? | Coi evidence gap là không có rủi ro. |
| **Finding remediation/retest** | Sai lệch đã được xác minh khắc phục hay mới đóng ticket? | Đếm merged PR như verified fix. |
| **Exception expiry and scope** | Có ngoại lệ hết hạn hoặc vượt phạm vi được duyệt không? | Coi ngoại lệ là PASS. |
| **Collector health** | Có nguồn im lặng, mất ingestion, lỗi quyền/pagination hoặc schema? | “Không alert” bị hiểu thành “không sự cố”. |
| **Residual risk beyond tolerance** | Rủi ro nào vẫn vượt ngưỡng dù có controls? | Tối ưu số controls thay vì kết quả giảm rủi ro. |

### Ví dụ status có thể giải trình

| Control | Design | Operating | Evidence quality | Kết luận minh họa |
| --- | --- | --- | --- | --- |
| AUTHZ-INVOICE | Đạt trên API GET | Có test GET; export chưa test | Một phần | PARTIAL – chỉ claim GET có evidence. |
| MFA-ADMINS | Đạt với policy chính | 1 tài khoản break-glass ngoài scope test | Thiếu | NOT FULLY VERIFIED – mở finding/giới hạn. |
| RESTORE-ORDERS | Runbook đủ | Restore drill lỗi khóa | Có bằng chứng FAIL | FAIL – cần sửa và diễn tập lại. |
| LOG-SECURITY | Event catalog được duyệt | Collector lỗi 2 ngày | Gaps lịch sử | INSUFFICIENT – chưa thể kết luận về cả kỳ. |

**Scorecard phải giữ chi tiết**, không gộp “Design PASS” và “Operating FAIL” thành “50% secure”. Mức assurance và rủi ro còn lại phải được đánh giá theo từng claim và hệ quả thực.

## 21. Các sai lầm phổ biến cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Có policy rồi nghĩa là control có evidence.” | Policy là thiết kế/quy tắc; phải chứng minh việc triển khai và vận hành trong phạm vi. |
| “Screenshot màu xanh là bằng chứng tốt nhất.” | Cần provenance, scope, thời điểm, cấu hình/effective behavior và khả năng kiểm tra lại. |
| “Test một endpoint là chứng minh tất cả API.” | Chỉ kết luận trong các luồng, vai trò và phiên bản đã được kiểm tra. |
| “100% assets scan nghĩa là 100% hệ thống an toàn.” | Inventory, scanner coverage và threat scenarios có thể còn khoảng trống. |
| “Không có log sự cố nghĩa là control hoạt động.” | Có thể lỗi phát log, thu thập, giám sát hoặc retention. |
| “Bằng chứng càng nhiều file càng mạnh.” | Chất lượng, tính liên quan và bao phủ quan trọng hơn số lượng. |
| “Đã merge code thì lỗi được khắc phục.” | Cần deployment verification, retest và xem hậu quả đã xảy ra. |
| “Control có chứng nhận nghĩa là không còn residual risk.” | Kết luận có phạm vi/điều kiện; rủi ro không tự về 0. |
| “Evidence từ nhà cung cấp đủ chứng minh cấu hình khách hàng.” | Shared responsibility và phạm vi tài liệu phải được xác minh. |
| “Mẫu 30 PASS chứng minh 600/600 PASS.” | Cần population đầy đủ, phương pháp sampling và kết luận đúng giới hạn. |
| “Hash chứng minh artifact đến từ nguồn hợp pháp.” | Hash hỗ trợ kiểm tra integrity khi có tham chiếu tin cậy; provenance cần bằng chứng riêng. |
| “Không có evidence thì điền PASS vì chưa phát hiện vấn đề.” | Thiếu evidence phải ghi rõ, xem xét ảnh hưởng tới mức assurance và rủi ro. |
| “Chia sẻ evidence nội bộ không cần bảo vệ dữ liệu.” | Bản ghi có thể chứa bí mật, định danh hoặc chi tiết lỗ hổng; phải quản lý truy cập/retention. |

## 22. Checklist đánh giá một control evidence

Trước khi chấp nhận một hiện vật cho cuộc audit hoặc security assurance review, có thể hỏi:

1. **Claim:** phát biểu đang kiểm tra rõ, đo được và có giới hạn?
2. **Mapping:** requirement/control ID và rủi ro liên quan đã được xác định?
3. **Scope:** bao gồm dịch vụ, tài sản, environment, release, roles, tenant và thời kỳ nào?
4. **Population:** nguồn population được đối chiếu completeness chưa?
5. **Method:** control được đánh giá thiết kế hay vận hành; phép test có kịch bản thành công/thất bại?
6. **Result:** expected và observed đã được phân biệt; có lỗi, ngoại lệ và vấn đề chưa kiểm thử?
7. **Provenance:** evidence đến từ nguồn/công cụ nào; có mốc thời gian, version, run ID?
8. **Integrity:** hiện vật được bảo vệ khỏi sửa/xóa sai và có thể kiểm tra lịch sử?
9. **Sensitivity:** dữ liệu có chứa secret/PII; quyền xem và retention có phù hợp?
10. **Independence:** người đánh giá có mức tách biệt và năng lực tương xứng?
11. **Conclusion:** kết luận không vượt phạm vi, ghi rõ limits và mức tin cậy?
12. **Action:** findings, remediation, retest, risk decision và review triggers có owner/hạn?

## 23. Bài tập thực hành và gợi ý

### Bài tập A — MFA đã bật nhưng không biết phạm vi

Đội IAM cung cấp một screenshot policy “Enforce MFA” và cho biết đã áp dụng cho toàn tổ chức. Auditor hỏi về tài khoản break-glass và ứng dụng cũ có đường đăng nhập riêng.

**Gợi ý:** Screenshot chỉ chứng minh một cấu hình tại thời điểm xác định. Cần population tài khoản, mapping policy, đường đăng nhập, ngoại lệ, test/bản ghi áp dụng MFA và kỳ đánh giá. Nếu chưa kiểm tra break-glass thì kết luận phải giới hạn phạm vi hoặc ghi evidence gap.

### Bài tập B — Báo cáo scan phát hiện zero issues

Pipeline security scan báo “0 critical findings” trên ứng dụng hóa đơn. Nhóm dùng kết quả để khẳng định không có lỗi phân quyền xuyên tenant.

**Gợi ý:** Scanner có thể không kiểm tra logic tenant/object. Kết quả có giá trị cho rule và scope đã chạy nhưng không chứng minh claim authorization. Cần threat model, access matrix và negative tests với user/tenant khác nhau.

### Bài tập C — Restore báo thành công nhưng không có dữ liệu nghiệp vụ

Diễn tập phục hồi báo hệ thống khởi động được sau 45 phút, nhưng không có kiểm tra số dư giao dịch hoặc tình trạng đơn hàng.

**Gợi ý:** Đây có thể là evidence cho khôi phục một số thành phần hạ tầng; **không đủ cho claim data integrity hoặc giao dịch đầu cuối phục hồi đúng**. Cần đối soát dữ liệu, RPO/RTO được định nghĩa theo dịch vụ và test nghiệp vụ sau restore.

### Bài tập D — Evidence từ 30 mẫu

Một control review thay đổi có 200 deployment trong kỳ. Assessor kiểm tra 30 deployment và phát hiện ba trường hợp thiếu bằng chứng phê duyệt. Đội engineering báo đạt 90%, đề nghị đóng control.

**Gợi ý:** Tỷ lệ 27/30 mô tả **mẫu kiểm tra**, không tự đại diện chính xác population. Cần xem loại thay đổi, mức nghiêm trọng, cách chọn mẫu, liệu có sai lệch hệ thống, và mở findings/đánh giá mở rộng. Kết luận “PASS” không phù hợp khi có trường hợp vi phạm tiêu chí chưa được xử lý.

### Bài tập E — Artifact đã hết hiệu lực vì thay đổi kiến trúc

Test quyền storage đạt trước khi thêm CDN mới. Sau release, ứng dụng cho phép tải file qua CDN nhưng claim vẫn dùng kết quả test cũ.

**Gợi ý:** Phạm vi đường truy cập đã đổi; evidence cũ không hỗ trợ claim mới. Cần cập nhật data flow, trust boundary, tiêu chí quyền và test ở CDN/đường đích; thực hiện retest và cập nhật risk.

### Bài tập F — Thu thập bằng chứng có chứa token thật

Một audit request yêu cầu log sự kiện xác thực. Nhân viên xuất nguyên văn request headers, gồm access token và session cookie, rồi đưa vào thư mục chia sẻ cho nhiều người.

**Gợi ý:** Evidence đang tạo rủi ro lộ thông tin xác thực. Phải quản lý an toàn artifact, giới hạn quyền, redaction/giảm thiểu dữ liệu theo yêu cầu kiểm chứng và đánh giá khả năng token đã bị lộ. Cần chính sách riêng cho bản gốc phục vụ điều tra nếu bắt buộc giữ, cùng audit truy cập.

### Bài tập G — Control test PASS, collector bị lỗi

Các test IAM chạy thành công tại staging nhưng nền tảng evidence collector không nhận log từ production trong bốn ngày. Dashboard vẫn báo “Compliant 100%”.

**Gợi ý:** “Test PASS ở staging” khác “production operating effectiveness trong kỳ”. Phải phát hiện nguồn im lặng, ghi evidence gap, xác minh trạng thái production bằng phương pháp phù hợp, sửa collector, kiểm tra sự kiện bỏ sót và điều chỉnh dashboard để phân biệt PASS với NOT TESTED.

## Kết luận

**Control evidence** là nền tảng của một chương trình **security assurance có thể giải trình**. Framework cho biết các mục tiêu và controls cần xem xét; evidence cho phép đánh giá **thiết kế đúng hay không, control có thật sự vận hành trong phạm vi và thời kỳ liên quan hay không, sai lệch đã được phát hiện và khắc phục chưa**. Bằng chứng phải gắn với claim cụ thể, có nguồn gốc, tính toàn vẹn, độ bao phủ, phương pháp kiểm tra, giới hạn và người chịu trách nhiệm. Trong **SECURITY_SECURITY_ASSURANCE**, chu trình đáng tin không dừng ở thu thập screenshot hay báo cáo xanh: nó đi từ risk và requirements tới control, test, evidence, finding, remediation, retest và quyết định residual risk, rồi được đánh giá lại mỗi khi hệ thống thay đổi. **Chỉ kết luận điều mà bằng chứng thực sự hỗ trợ, trong đúng phạm vi đã kiểm tra**.
