# Recovery trong Incident Response: Khôi phục an toàn, có bằng chứng

Khi một sự cố bảo mật làm gián đoạn hệ thống, doanh nghiệp cần nhanh chóng phục hồi dịch vụ. Tuy nhiên, **dịch vụ hoạt động trở lại chưa đồng nghĩa sự cố đã được xử lý an toàn**. Máy chủ được khởi động lại có thể vẫn chứa mã độc; bản sao lưu có thể đã bị thay đổi; khóa truy cập bị lộ có thể vẫn còn hiệu lực; dữ liệu phục hồi có thể bị thiếu hoặc không nhất quán. Nếu vội đưa tài nguyên vào production, tổ chức có thể tái nhiễm, mất chứng cứ hoặc gây ra sự cố thứ hai.

**Recovery** là giai đoạn đưa hệ thống, dữ liệu và quy trình nghiệp vụ bị ảnh hưởng trở lại trạng thái hoạt động được chấp nhận sau sự cố, dựa trên biện pháp loại trừ/giảm thiểu mối đe dọa, kiểm tra tính toàn vẹn và quyết định rủi ro có thẩm quyền. Trong chương **Incident response** của module **SECURITY_SECURITY_ASSURANCE**, trọng tâm là xây dựng một quy trình **security assurance dựa trên bằng chứng**: biết chính xác điều gì được khôi phục, điều kiện an toàn nào phải đạt, ai xác nhận, bằng chứng được tạo ra ở đâu và khi nào có thể mở lại lưu lượng.

Sau bài học, người học có thể phân biệt recovery với các giai đoạn ứng phó khác; xác định mục tiêu khôi phục theo mức độ quan trọng và rủi ro; lựa chọn nguồn phục hồi đáng tin cậy; triển khai khôi phục từng bước; kiểm chứng an toàn, dữ liệu và chức năng; cũng như lập hồ sơ kết quả, giới hạn và các hành động tiếp tục giám sát.

## 1. Recovery nằm ở đâu trong vòng đời xử lý sự cố?

Một chuỗi công việc thường gặp:

~~~mermaid
flowchart TD
    A["Phát hiện và phân tích"] --> B["Khoanh vùng / containment"]
    B --> C["Loại trừ hoặc giảm mối đe dọa / eradication"]
    C --> D["Recovery theo từng giai đoạn"]
    D --> E["Xác minh và giám sát tăng cường"]
    E --> F{"Đạt điều kiện trở lại bình thường?"}
    F -->|Có| G["Nghiệm thu, bàn giao và cải tiến"]
    F -->|Chưa| H["Khoanh vùng, điều tra hoặc khắc phục tiếp"]
    H --> B
~~~

Các bước có thể diễn ra **song song hoặc lặp lại**. Với hệ thống khẩn cấp, tổ chức có thể phục hồi dịch vụ tối thiểu trong môi trường được cô lập, ngay cả khi điều tra hệ thống cũ chưa hoàn tất. Trường hợp đó phải có quyết định chấp nhận rủi ro, đường kết nối được hạn chế và giám sát tăng cường. Không được xem sơ đồ là yêu cầu rằng mọi loại sự cố phải hoàn thành hoàn toàn một giai đoạn rồi mới bắt đầu giai đoạn kế tiếp.

| Hoạt động | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Containment** | Làm thế nào hạn chế sự cố lan rộng hoặc tiếp tục gây hại? | Cô lập VM, thu hồi phiên, vô hiệu hóa token bị lộ, chặn đường kết nối nguy hiểm. |
| **Eradication** | Làm thế nào loại bỏ nguyên nhân và khả năng tiếp tục bị khai thác? | Xóa cơ chế duy trì truy cập, vá lỗ hổng gốc, tái tạo tài nguyên sạch, sửa policy quyền. |
| **Recovery** | Làm thế nào đưa dịch vụ và dữ liệu trở lại trạng thái được chấp nhận, an toàn và đo được? | Dựng workload từ image đáng tin, khôi phục dữ liệu đã xác minh, kiểm thử rồi mở traffic dần. |
| **Business Continuity (BCP)** | Làm thế nào duy trì hoạt động kinh doanh tối thiểu trong lúc dịch vụ chính chưa trở lại? | Quy trình nhận đơn thủ công hoặc dịch vụ thay thế có giới hạn. |
| **Disaster Recovery (DR)** | Làm thế nào khôi phục công nghệ sau gián đoạn lớn theo kịch bản dự phòng? | Failover qua vùng dự phòng, phục hồi cơ sở dữ liệu từ backup, chuyển DNS. |
| **Post-incident review** | Vì sao sự cố xảy ra, biện pháp nào hiệu quả và phải cải tiến gì? | Phân tích nguyên nhân, cập nhật runbook, kiểm soát, bài kiểm thử và backlog khắc phục. |

**Failover không mặc nhiên là recovery an toàn.** Nếu tài khoản quản trị chung đã bị xâm phạm, vùng dự phòng dùng cùng quyền truy cập hoặc bản sao dữ liệu có thể cũng bị ảnh hưởng. **Restore không mặc nhiên là sạch.** Nếu backup được tạo sau khi mã độc thiết lập persistence, quá trình restore có thể mang chính điểm yếu trở lại.

## 2. Mục tiêu phục hồi: Nghiệp vụ, an toàn và tính toàn vẹn

Recovery cần được quyết định dựa trên dịch vụ nào phải hoạt động, dữ liệu nào cần bảo vệ, và rủi ro còn lại nào có thể chấp nhận. Ba nhóm mục tiêu phải được xác định đồng thời:

1. **Khả năng hoạt động:** nghiệp vụ quan trọng phục hồi tới mức dịch vụ tối thiểu hoặc đầy đủ theo cam kết.
2. **Tính an toàn và tin cậy:** nguyên nhân gây sự cố được loại trừ hoặc ngăn tái diễn ở phạm vi đủ để mở lại hoạt động.
3. **Tính chính xác của dữ liệu:** dữ liệu được phục hồi nhất quán, có nguồn gốc hợp lệ, không phát sinh mất mát hoặc sai lệch vượt mức được phê duyệt.

### Các chỉ số thường dùng

| Chỉ số | Diễn giải | Phân biệt cần thiết |
|---|---|---|
| **RTO — Recovery Time Objective** | Khoảng thời gian gián đoạn tối đa mà tổ chức đặt mục tiêu chịu được trước khi chức năng cần thiết phải được khôi phục. | Là **mục tiêu**, không phải thời gian đã đo. Cần định nghĩa điểm bắt đầu/kết thúc cho từng dịch vụ. |
| **RPO — Recovery Point Objective** | Mức mất dữ liệu theo thời gian mà tổ chức đặt mục tiêu chấp nhận, tính từ thời điểm phục hồi về mốc dữ liệu an toàn. | Là **mục tiêu**; chưa chứng minh dữ liệu thực tế đã khôi phục đủ. |
| **Actual recovery time** | Thời gian thực tế từ mốc kích hoạt được quy định đến khi dịch vụ đạt tiêu chí nghiệm thu. | Cần ghi timestamp và phạm vi; không đồng nhất việc máy chạy với nghiệp vụ đã sẵn sàng. |
| **Actual data loss / restore point** | Khoảng dữ liệu thiếu hoặc chưa đối soát sau khôi phục. | Chỉ có thể kết luận sau khi kiểm tra tính nhất quán và giao dịch liên quan. |
| **Minimum viable service** | Các luồng nghiệp vụ tối thiểu phải đạt trước khi mở lại từng phần. | Phải có chủ sở hữu nghiệp vụ phê duyệt; không thay thế mục tiêu khôi phục đầy đủ. |
| **Recovery confidence** | Mức độ bằng chứng hỗ trợ rằng nền tảng, dữ liệu và kiểm soát đã sẵn sàng. | Cần nêu tiêu chí kỹ thuật, phép kiểm tra và giới hạn, không gán theo cảm tính. |

Ví dụ: ứng dụng đặt hàng có **RTO = 4 giờ** và **RPO = 15 phút** theo chính sách nội bộ. Nếu gián đoạn được tính từ 08:00, dịch vụ tối thiểu cần đạt tiêu chí trước 12:00. Nếu chọn điểm khôi phục dữ liệu 07:50, mức lùi dữ liệu so với mốc gián đoạn là 10 phút, nhưng vẫn phải kiểm tra những giao dịch sau điểm khôi phục: đơn nào có thể thiếu, đã thanh toán chưa, có thể replay an toàn không. Những con số này chỉ là tình huống minh họa, không phải chuẩn bắt buộc.

**RTO/RPO không phải giới hạn bảo mật**: đạt RTO nhưng vẫn còn khóa bị chiếm quyền hoặc chưa xác minh dữ liệu không đủ để kết luận recovery an toàn. Ngược lại, đôi khi cần kéo dài phục hồi để tránh tái xâm nhập; quyết định đó phải được ghi nhận cùng đánh giá tác động nghiệp vụ.

## 3. Điều kiện đầu vào trước khi đưa hệ thống trở lại

Trước khi cho phép recovery, Incident Commander và các nhóm liên quan cần có câu trả lời dựa trên bằng chứng cho những điểm sau:

- **Phạm vi đã biết đến đâu?** Tài khoản, máy chủ, container, database, network, credential, thiết bị và bên thứ ba nào bị ảnh hưởng hoặc có thể bị ảnh hưởng?
- **Mối đe dọa đã được chặn hoặc giảm thế nào?** Đã cô lập hệ thống nghi nhiễm, thu hồi phiên/token, sửa lỗ hổng hoặc hạn chế đường khai thác đến mức đủ an toàn chưa?
- **Môi trường phục hồi có đáng tin?** Image, template, IaC, artifact, identity provider, khóa và kênh quản trị có được kiểm chứng trước khi dùng lại không?
- **Nguồn dữ liệu phục hồi có đáng tin?** Backup/snapshot được tạo lúc nào, có thể đã bị xâm phạm từ trước không, có hash hoặc kiểm tra toàn vẹn không, có thể giải mã không?
- **Bằng chứng điều tra đã được bảo toàn phù hợp?** Log, snapshot, cấu hình, timeline và dữ liệu cần cho forensics/tuân thủ đã được giữ theo phạm vi được phép chưa?
- **Ai có quyền cho phép?** Đã có owner nghiệp vụ, incident lead, platform/security và người chấp nhận rủi ro còn lại theo quy trình chưa?
- **Có phương án thất bại?** Nếu khôi phục tái phát dấu hiệu xâm nhập, biết dừng ở đâu, ai quyết định, cách quay lại trạng thái cô lập và truyền thông không?

Không phải mọi câu hỏi đều có thể trả lời hoàn toàn ngay khi sự cố diễn ra. **Điều chưa xác định phải được ghi thành giả định, giới hạn hoặc rủi ro còn lại** kèm người xử lý. Một tình trạng “chưa có bằng chứng xâm nhập” khác với “có bằng chứng hệ thống sạch”.

### Recovery gate (điểm quyết định cho phép)

| Gate | Tiêu chí cần xác nhận | Loại bằng chứng |
|---|---|---|
| **G1 — Containment** | Đường tấn công đang biết đã bị cô lập/khắc phục đủ để thử phục hồi. | Firewall/IAM diff, bằng chứng revoke token, trạng thái cô lập, retest an toàn. |
| **G2 — Trusted foundation** | Nguồn image, IaC, quản trị và khóa dùng để phục hồi đã được kiểm tra. | Artifact digest/signature nếu áp dụng, provenance, cấu hình baseline và quyền hiệu lực. |
| **G3 — Trusted data** | Có điểm khôi phục được chọn, tính toàn vẹn có thể kiểm tra và tác động mất dữ liệu được đánh giá. | Backup job, snapshot metadata, kết quả restore thử, kiểm tra dữ liệu. |
| **G4 — Functional readiness** | Luồng nghiệp vụ thiết yếu và phụ thuộc dịch vụ hoạt động theo điều kiện đã chốt. | Smoke/integration test, health, error rate, kết quả đối soát. |
| **G5 — Security readiness** | Kiểm soát danh tính, logging, monitoring và biện pháp phát hiện hoạt động. | Quyền mới, MFA, audit ingest, synthetic detection, scan và review cấu hình. |
| **G6 — Go-live approval** | Người có thẩm quyền phê duyệt phạm vi mở lại, kế hoạch rollback và giám sát. | Biên bản quyết định, danh sách giới hạn, owner, mốc thời gian và kế hoạch theo dõi. |

Mỗi gate có thể mang trạng thái **PASS**, **FAIL**, **INCONCLUSIVE** hoặc **NOT_APPLICABLE** với lý do. Một ngoại lệ được chấp nhận về rủi ro cần ghi riêng, không đổi một FAIL thành PASS. Nếu chấp nhận phục hồi hạn chế khi chưa đủ bằng chứng, phải ghi rõ phần nào được phép hoạt động, biện pháp bảo vệ và điều kiện nâng cấp/thu hồi quyết định.

## 4. Lập kế hoạch recovery theo mức ưu tiên

Không thể khôi phục mọi tài nguyên cùng lúc khi nguồn lực hạn chế. Xác định mức ưu tiên bằng **business impact analysis**, sự phụ thuộc giữa các hệ thống, mức rủi ro bảo mật và tính khả thi của từng bước.

| Nhóm dịch vụ | Cân nhắc | Ưu tiên minh họa |
|---|---|---|
| **Identity/DNS/PKI/secret management** | Là nền tảng để xác thực, truy cập và hoạt động an toàn của các dịch vụ khác. | Phải bảo đảm tin cậy trước khi phụ thuộc vào chúng để khôi phục workload. |
| **Logging và detection** | Cần quan sát sự cố, phát hiện tái xâm nhập và ghi bằng chứng khi mở lại. | Khôi phục hoặc thiết lập giám sát thay thế sớm, trước khi mở traffic rộng. |
| **Data platform** | Có thể là điểm hợp nhất dữ liệu và yêu cầu nhất quán giao dịch. | Khôi phục theo dependency và xác minh schema, transaction, quyền trước ứng dụng. |
| **Ứng dụng lõi** | Chức năng đem lại giá trị trực tiếp cho nghiệp vụ. | Mở lại theo luồng quan trọng và tiêu chí minimum viable service. |
| **Hệ thống phụ trợ/batch** | Có thể đợi thêm nếu không ảnh hưởng dây chuyền. | Thực hiện sau khi hệ thống nền tảng và luồng nghiệp vụ chính đạt gate. |

Ví dụ đơn hàng phụ thuộc IdP, API gateway, kho khóa, database và hệ thống thanh toán. Nếu database đã phục hồi nhưng credentials dùng cho API chưa an toàn, bật lại API có thể gây tái xâm nhập; nếu hệ thống thanh toán không được đối soát, phát lại đơn hàng có thể tạo giao dịch kép. Từng bước phải có **thứ tự phụ thuộc, owner, tiêu chí đạt và điều kiện dừng**.

### Mô hình kịch bản khôi phục

- **Rebuild sạch (*clean rebuild*):** dựng lại VM/container hoặc service từ image và IaC đáng tin, nhập lại dữ liệu đã xác minh; thường phù hợp khi không thể bảo đảm host cũ sạch.
- **Restore backup/snapshot:** khôi phục dữ liệu hoặc cấu hình từ điểm được chọn, có kiểm tra tính toàn vẹn, an toàn và nhất quán.
- **Failover:** chuyển sang site/region/cluster dự phòng sau khi xác minh môi trường dự phòng không bị chung đường xâm nhập.
- **Reprovision credentials/identities:** thay và thu hồi khóa, token, chứng chỉ, mật khẩu khi liên quan đến sự cố.
- **Degraded mode:** chỉ cung cấp chức năng tối thiểu, giảm quyền và đường truy cập trong khi các phần khác tiếp tục điều tra.
- **Manual fallback:** quy trình thủ công được nghiệp vụ chấp nhận, có ghi nhận giao dịch để đối soát sau.

Chọn phương án bằng đánh giá rủi ro. Không ưu tiên restore nhanh nhất nếu nó đưa mã độc hoặc quyền bị chiếm đoạt quay lại.

## 5. Quy trình recovery từ môi trường cô lập đến nghiệm thu

~~~mermaid
flowchart TD
    A["Xác định phạm vi, RTO/RPO, ưu tiên"] --> B["Đánh giá containment, nguồn sạch và bằng chứng"]
    B --> C{"Đủ điều kiện khôi phục thử?"}
    C -->|Không| D["Khắc phục, bảo toàn chứng cứ hoặc cấp phép ngoại lệ có hạn"]
    D --> B
    C -->|Có| E["Dựng môi trường cô lập từ nền tảng đáng tin"]
    E --> F["Phục hồi dữ liệu / secrets / cấu hình đã kiểm chứng"]
    F --> G["Kiểm thử toàn vẹn, nghiệp vụ, quyền và log"]
    G --> H{"Đạt tiêu chí kỹ thuật và bảo mật?"}
    H -->|Không| I["Giữ cô lập, điều tra và sửa"]
    I --> E
    H -->|Có| J["Canary, mở traffic dần, giám sát tăng cường"]
    J --> K{"Ổn định và không có dấu hiệu tái nhiễm?"}
    K -->|Không| L["Dừng mở rộng, rollback/cô lập, điều tra"]
    L --> I
    K -->|Có| M["Nghiệm thu, bàn giao, theo dõi rủi ro còn lại"]
~~~

### Bước 1 — Khoanh phạm vi và bảo toàn chứng cứ

Gắn recovery plan với incident ID, timeline, asset inventory, phạm vi dữ liệu, triệu chứng và kết quả điều tra hiện tại. Trước khi xóa/reimage nguồn bị nghi ngờ, phối hợp nhóm incident response/forensics để bảo toàn log, snapshot, memory/disk image hoặc artifact cần thiết theo kế hoạch và thẩm quyền. Cần ghi người thu thập, thời điểm, nguồn gốc, cách bảo quản và kiểm soát truy cập.

Việc chụp snapshot **không tự chứng minh** chứng cứ đã hợp lệ hay đủ. Có thể phải giữ dữ liệu từ API, control plane, SIEM, EDR và nhà cung cấp; chọn phương pháp không làm mất chứng cứ quan trọng. Sự cần thiết và cách lưu phụ thuộc vào ngữ cảnh điều tra và nghĩa vụ pháp lý áp dụng.

### Bước 2 — Xác nhận đường tái xâm nhập đã được xử lý

Nếu nguyên nhân là secret bị lộ, phải thu hồi khóa, token và phiên còn hiệu lực; nếu nguyên nhân là lỗ hổng phần mềm, cần vá hoặc chặn đường khai thác đã biết; nếu nguyên nhân là IAM role bị cấp sai, phải sửa quyền và kiểm tra liên kết trust policy; nếu nguyên nhân là tài khoản quản trị bị chiếm, cần xác minh các identity và cấu hình có thể đã bị sửa.

Không thể chỉ kiểm tra một host “không còn thấy file mã độc” và kết luận toàn bộ môi trường sạch. Kẻ tấn công có thể đã tạo tài khoản, thay scheduled task, đổi key policy, thêm OAuth grant hoặc thiết lập persistence tại nơi khác. Phải rà soát theo kết quả điều tra, threat model và phạm vi tài sản liên quan.

### Bước 3 — Dựng nền tảng sạch và cô lập

Nếu không thể tin cậy host cũ, ưu tiên dựng mới từ image đáng tin và cấu hình đã được review. Tạo môi trường khôi phục hạn chế kết nối đầu vào/đầu ra, phân tách tài khoản quản trị và chỉ cho phép kênh cần để kiểm tra. Xác minh cấu hình hệ điều hành, patch, IAM, network, secret injection, logging và deployment artifacts.

Giữ vùng cô lập cho tới khi các gate cần thiết đạt; **không kết nối mặc định** hệ thống vừa restore với mạng production hoặc nguồn backup dùng chung có thể bị ảnh hưởng.

### Bước 4 — Phục hồi dữ liệu với điểm khôi phục xác định

Chọn điểm khôi phục dựa trên mốc bắt đầu ảnh hưởng đáng tin cậy nhất, lịch sử thay đổi và mức mất dữ liệu có thể chấp nhận. Khôi phục vào môi trường cách ly để kiểm tra tính toàn vẹn, cấu trúc và nội dung trọng yếu. Với database, cần xét consistency của transaction, snapshot giữa nhiều dịch vụ, replication lag và các bản ghi chưa đồng bộ.

Nếu chỉ có backup sau thời điểm nghi bị xâm nhập, không mặc định backup sạch. Có thể phục hồi chọn lọc dữ liệu, tái tạo hệ thống từ nền tảng sạch và kiểm tra dữ liệu trước khi đưa sang môi trường mới. Quy trình phải có owner nghiệp vụ xác nhận tính đúng đắn của dữ liệu, không chỉ người vận hành database.

### Bước 5 — Xác minh chức năng và bảo mật

Thực hiện smoke test, integration test và các bài thử nghiệp vụ thiết yếu. Đồng thời đánh giá cấu hình bảo mật, runtime version, quyền hiệu lực, secrets, audit log và detection rule. Kiểm tra rằng sự kiện thử được phép đi từ nguồn đến hệ thống giám sát, và người trực có thể nhận cảnh báo.

Một health check HTTP trả 200 chỉ cho thấy một endpoint hoạt động; không chứng minh giao dịch nghiệp vụ, xác thực, phân quyền hoặc sự bảo toàn dữ liệu đã đạt.

### Bước 6 — Mở dịch vụ theo từng giai đoạn

Chọn canary, traffic shifting, vùng người dùng giới hạn hoặc tính năng đọc trước khi mở chức năng ghi nếu phù hợp. Đặt giới hạn về lưu lượng, độ trễ, lỗi, bất thường IAM, integrity anomaly và số cảnh báo. Có người quyết định dừng/rollback khi vượt ngưỡng. Nếu hạ tầng cũ còn nghi nhiễm, tuyệt đối không tự động chuyển traffic ngược về vùng đó khi rollback.

### Bước 7 — Nghiệm thu và bàn giao vận hành

Chỉ chuyển sang vận hành bình thường sau khi có bằng chứng đáp ứng các tiêu chí đã phê duyệt và người có thẩm quyền chấp nhận giới hạn còn lại. Lưu trạng thái cuối của tài sản, kết quả kiểm thử, mốc thời gian, rủi ro mở, quyền truy cập được cấp lại, tình trạng giám sát và lịch đánh giá tiếp theo.

Recovery có thể hoàn tất về mặt vận hành trong khi **incident investigation, nghĩa vụ thông báo hoặc post-incident review vẫn tiếp tục**. Tránh nhầm nghiệm thu dịch vụ với tuyên bố mọi công việc sự cố đã đóng.

## 6. Độ tin cậy của backup và điểm khôi phục

Backup là công cụ hỗ trợ phục hồi, nhưng khả năng an toàn phải được chứng minh cả **trước**, **trong** và **sau** sự cố.

| Câu hỏi kiểm chứng | Bằng chứng có thể dùng |
|---|---|
| Backup có tồn tại, bao phủ đúng dữ liệu và được tạo thành công? | Backup catalog, job status, asset ID, lịch, bản kê tập dữ liệu. |
| Backup có thể đã bị thay đổi hoặc mã hóa bởi kẻ tấn công? | Quyền truy cập, retention lock nếu có, audit thao tác xóa/sửa, dấu thời gian và điều tra phạm vi xâm nhập. |
| Có thể đọc và giải mã backup không? | Thử restore, tình trạng khóa, quyền giải mã và nguồn khóa được bảo vệ phù hợp. |
| Điểm khôi phục được chọn có đủ sạch? | Timeline sự cố, sự kiện audit, kết quả phân tích mẫu dữ liệu/artefact, baseline tin cậy. |
| Dữ liệu có nhất quán? | Transaction check, integrity constraint, checksum ở phạm vi thích hợp, đối chiếu số lượng và nghiệp vụ. |
| Backup có khôi phục đủ các phụ thuộc? | Cấu hình, schema, certificate, secret, metadata, deployment manifests và hạ tầng cần thiết. |
| Có thể đáp ứng mục tiêu khôi phục? | Thử restore có đo thời gian, dung lượng, lỗi, phụ thuộc và điều kiện của kịch bản thực tế. |

**Immutable backup** hoặc lưu trữ khóa xóa theo thời hạn có thể giảm khả năng kẻ tấn công sửa/xóa dữ liệu đã lưu, nhưng không bảo đảm toàn bộ backup sạch: nguồn có thể bị nhiễm trước khi ghi, quyền/khóa khác có thể bị chiếm, hoặc dữ liệu đã bị xóa/sai từ trước. Cần đánh giá toàn chuỗi tạo, lưu, giải mã và khôi phục.

### Ví dụ mất dữ liệu và đối soát

Giả sử hệ thống ghi đơn hàng tới 10:20, nhưng bản snapshot an toàn cuối cùng ở 10:05. Nếu RPO được phê duyệt là 15 phút, khoảng lùi dữ liệu danh nghĩa bằng 15 phút. Tuy nhiên, không được kết luận ngay đã đáp ứng RPO nếu đồng hồ giữa các hệ thống lệch hoặc giao dịch trong khoảng đó chưa được xác định.

Cần đối chiếu đơn hàng, sự kiện trong message queue, trạng thái thanh toán từ nhà cung cấp bên ngoài và idempotency key. Việc replay các message có thể tạo giao dịch lặp nếu bộ xử lý không idempotent; phải xác định thứ tự và điều kiện tái xử lý. Chủ nghiệp vụ cần xác nhận số lượng bản ghi mất, lỗi cần sửa thủ công, nghĩa vụ với khách hàng và quy trình reconciliation.

### Backup và bằng chứng pháp lý

Nếu dữ liệu trong backup là nguồn chứng cứ liên quan điều tra, việc phục hồi, xóa hoặc ghi đè có thể ảnh hưởng đến khả năng phân tích. Phối hợp trước với nhóm điều tra và chủ thể có thẩm quyền về bản sao chứng cứ, quyền truy cập, retention và việc xử lý dữ liệu nhạy cảm. Không mặc định một bản backup phục vụ vận hành cũng đáp ứng toàn bộ yêu cầu chain of custody.

## 7. Tránh tái nhiễm khi khôi phục tài sản và định danh

### 7.1. Máy chủ, VM và workload

Với host có khả năng bị xâm nhập, làm sạch tại chỗ có thể bỏ sót persistence hoặc cấu hình bị sửa. Khi phù hợp, dựng lại từ image được kiểm chứng và cập nhật, sau đó nhập **dữ liệu cần thiết** theo danh sách cho phép. Đừng phục hồi nguyên trạng toàn bộ scheduled task, tài khoản cục bộ, script khởi động hoặc cấu hình chưa xác minh.

Khi sử dụng golden image, kiểm tra image ID/digest, lịch sử build, signature/provenance nếu tổ chức áp dụng, phiên bản patch và scanner phù hợp. Kiểm tra rằng auto-scaling template, serverless artifact hoặc deployment manifest không tiếp tục tạo ra tài sản từ bản lỗi thời.

### 7.2. Identity và secrets

Đối với sự cố chiếm quyền, phải xác định tất cả principal và session chịu ảnh hưởng: người dùng, workload identity, service account, API key, OAuth consent, federation trust, chứng chỉ, CI/CD token và break-glass account. Các bước có thể gồm revoke session, rotate token/secret, buộc xác thực lại, sửa quyền, tăng kiểm soát MFA và review quyền cấp cho bên thứ ba.

**Đổi một mật khẩu chưa chắc thu hồi được các token hoặc phiên đang tồn tại**; cần kiểm tra cơ chế hiệu lực của từng nền tảng. Khi rotate khóa mã hóa, cân nhắc dữ liệu/backup cũ còn dùng khóa nào, phương án giải mã và khả năng ngừng dịch vụ. Tránh vô hiệu hóa khóa trước khi xác nhận hậu quả và khả năng khôi phục.

### 7.3. Cloud, Kubernetes và dịch vụ managed

Trong IaaS, nhóm khách hàng thường quản lý guest OS, ứng dụng và phần lớn cấu hình tenant; CSP bảo vệ lớp hạ tầng thuộc trách nhiệm nhà cung cấp. Với managed Kubernetes, cần xác định ai quản lý control plane, node pool, add-on, secret, workload image và chính sách truy cập. Với PaaS/SaaS, khách hàng thường phụ trách tenant settings, identity, tích hợp và dữ liệu trong phạm vi được hỗ trợ, trong khi nhà cung cấp vận hành những lớp dịch vụ đã cam kết.

Nếu cần bằng chứng cho lớp khách hàng không quan sát được, dùng tài liệu dịch vụ, hợp đồng, báo cáo assurance hoặc trao đổi hỗ trợ chính thức trong phạm vi liên quan. **Không suy luận một chứng nhận CSP chứng minh tenant hoặc ứng dụng của khách hàng đã phục hồi an toàn.**

### 7.4. Hệ thống phụ trợ và chuỗi cung ứng

Một hệ thống mới dựng có thể bị tái xâm nhập qua runner CI/CD cũ, kho artifact bị chiếm, DNS bị sửa, webhook hoặc plugin không tin cậy, hoặc endpoint của đối tác chưa được kiểm tra. Danh sách dependency của recovery phải bao gồm đường cung cấp mã, secret, network egress, backup agent, quản trị từ xa và các tài khoản bên thứ ba có quyền truy cập.

## 8. Recovery assurance: Bộ kiểm tra trước khi mở lại traffic

Nên tổ chức kiểm tra theo cả **tính an toàn** và **khả năng phục vụ**, với kết quả được ghi riêng.

| Nhóm kiểm tra | Tiêu chí ví dụ | Phương pháp / evidence |
|---|---|---|
| **Nền tảng sạch** | Asset được tạo từ image, IaC hoặc bản phát hành đã phê duyệt; không còn đường persistence đã biết. | Resource list, artifact digest, diff cấu hình, kết quả review và quét kỹ thuật. |
| **Lỗ hổng và root cause** | Đường khai thác liên quan đã được khắc phục hoặc ngăn chặn có hiệu lực. | Patch/build, config, thử lại an toàn, change ticket. |
| **Danh tính/đặc quyền** | Token bị lộ đã vô hiệu hóa; quyền cần thiết được cấp tối thiểu; MFA/SSO phù hợp. | Identity inventory, session revoke, policy diff, access review, test quyền. |
| **Dữ liệu** | Restore đúng điểm đã chọn; các kiểm tra nhất quán và đối soát đạt điều kiện nghiệp vụ. | Backup catalog, result restore, checksums, integrity query, business sign-off. |
| **Networking** | Chỉ có đường kết nối được phê duyệt; không còn kết nối quản trị hoặc trust path đáng ngờ. | Network policy/firewall diff, route, flow log và thử reachability được phép. |
| **Logging/detection** | Audit quan trọng đến nơi tập trung, rule phát hiện hoạt động, có người trực. | Synthetic event, SIEM query, alert/ticket, ingestion lag. |
| **Ứng dụng** | Các luồng nghiệp vụ chủ yếu đáp ứng điều kiện chức năng và hiệu năng. | Integration test, smoke test, error rate, latency, trace/log. |
| **Khả năng phục hồi** | Backup và đường quay lui/khôi phục phù hợp kế hoạch. | Diễn tập/kiểm tra restore, rollback rehearsal, runbook đã duyệt. |
| **Giới hạn còn lại** | Các trạng thái chưa hoàn tất được ghi, phê duyệt và theo dõi. | Exception/risk register, owner, due date, điều kiện chấp nhận. |

Cần hiểu **giới hạn của phép kiểm tra**. Một bản quét không có phát hiện không chứng minh toàn bộ hệ thống sạch; một truy vấn checksum không chứng minh mọi giao dịch nghiệp vụ đều đúng; một synthetic alert thành công không chứng minh mọi kỹ thuật tấn công đều có thể phát hiện. Kết luận phải ghi phạm vi, thời điểm và nguồn bằng chứng.

### Kiểm thử quyền ở trạng thái phục hồi

Đừng chỉ xác minh người quản trị đăng nhập được. Hãy kiểm tra người dùng bình thường không có quyền mới ngoài dự kiến, service account chỉ có quyền cần, kết nối liên vùng/tài khoản tuân theo trust policy, và các API nhạy cảm từ chối truy cập không hợp lệ. Có thể dùng tài khoản thử và phép thử an toàn đã được phê duyệt để xác minh hành vi.

### Kiểm thử logging khi mở lại

Cần xác nhận telemetry vẫn chạy khi workload mới được cấp phát hoặc thay region/cluster. Một hệ thống có thể phục hồi chức năng nhưng mất audit vì agent chưa cài, connector thiếu quyền hoặc log sink còn trỏ tới account bị cô lập. Nên phát sinh sự kiện thử không nhạy cảm, theo dõi từ nguồn đến đích và kiểm tra cảnh báo cho các hành vi trọng yếu.

## 9. Phục hồi theo giai đoạn và quyết định go/no-go

Với hệ thống quan trọng, chia thành các mức:

1. **Isolation validation:** môi trường sạch vẫn cách ly; thực hiện scan, kiểm tra secret, dữ liệu và chức năng bằng đầu vào an toàn.
2. **Restricted service:** cho phép nhân viên/nhóm thử nghiệm đã xác định truy cập; hạn chế external integration, quyền ghi và lưu lượng nếu cần.
3. **Controlled release:** mở một phần traffic, theo dõi error rate, dữ liệu, authentication, latency, hành vi mạng và cảnh báo tái xâm nhập.
4. **Full service:** tăng lưu lượng và cho phép các chức năng đã được duyệt; tiếp tục giám sát tăng cường theo kế hoạch.
5. **Operational handover:** giao cho nhóm vận hành thông thường khi incident lead và chủ nghiệp vụ chấp thuận các điều kiện kết thúc giai đoạn tăng cường.

Các ngưỡng cho go/no-go phải được xác định phù hợp với từng dịch vụ. Một ví dụ có thể yêu cầu: 100% luồng thanh toán thử trong phạm vi đạt, không có alert bảo mật nghiêm trọng chưa giải thích trong thử nghiệm, mọi dịch vụ logging bắt buộc có event xác minh, backlog message queue được đối soát và người trực xác nhận sẵn sàng. Đây là tiêu chí **minh họa**, cần được đơn vị vận hành phê duyệt.

### Khi phát hiện dấu hiệu tái xâm nhập

Nếu xuất hiện kết nối độc hại, quyền lạ hoặc lỗi integrity liên quan sự cố trong giai đoạn mở lại: **dừng tăng traffic, đưa tài nguyên liên quan về chế độ hạn chế/cô lập theo runbook, bảo toàn bằng chứng mới, đánh giá lại phạm vi và nguyên nhân**. Quyết định quay lui phải kiểm tra độ tin cậy của điểm quay lui, không tự động phục hồi lại hệ thống cũ đã bị xâm nhập.

Quy trình escalation phải có tên vai trò và đầu mối trực. Trong khẩn cấp, nhóm kỹ thuật cần biết ai có thể thực hiện hành động bảo vệ ngay và ai phải được thông báo/phê duyệt theo chính sách.

## 10. RACI và truyền thông trong recovery

Recovery thường là công việc liên nhóm. Một người chịu trách nhiệm giải trình rõ ràng cho mỗi quyết định giúp tránh tình trạng nhiều đội cho rằng đội khác sẽ xác nhận rủi ro.

| Vai trò | Trách nhiệm thường gặp |
|---|---|
| **Incident Commander / Incident Lead** | Điều phối, chốt tình hình, quản lý quyết định, kênh truyền thông và giai đoạn chuyển tiếp. |
| **Security/Incident Response** | Đánh giá nguy cơ tái xâm nhập, điều kiện containment/eradication, kiểm tra an ninh và bảo toàn bằng chứng. |
| **Platform/Cloud Operations** | Dựng hạ tầng sạch, restore, thay đổi cấu hình, theo dõi runtime, triển khai rollback. |
| **Application Owner / Engineering** | Xác nhận chức năng, dependency, transaction, phiên bản triển khai và điều kiện nghiệp vụ. |
| **Data Owner / DBA** | Chọn/kiểm tra điểm khôi phục, tính toàn vẹn, đối soát dữ liệu và mức mất dữ liệu. |
| **Business Service Owner** | Xác định ưu tiên, minimum viable service, chấp nhận kết quả vận hành và tác động nghiệp vụ. |
| **Risk/Legal/Privacy/Communications** | Tham gia khi có nghĩa vụ báo cáo, bảo vệ dữ liệu, pháp lý hoặc truyền thông tới các bên liên quan. |
| **CSP/MSP/Third party** | Hỗ trợ hoặc thực hiện phần trách nhiệm theo hợp đồng, cung cấp dữ liệu/kết quả cần thiết. |

Với một hệ thống có nhiều chủ sở hữu, có thể tạo ma trận **Responsible, Accountable, Consulted, Informed (RACI)** riêng cho restore database, rotate credential, mở traffic, nghiệm thu và quyết định chấp nhận rủi ro. Gán chính xác người *accountable* theo quy trình thực tế, không mặc định mọi quyết định chỉ thuộc đội security.

### Thông tin tới các bên liên quan

Thông báo recovery nên phân biệt: dịch vụ nào đang hoạt động, chức năng nào còn giới hạn, dữ liệu/giao dịch nào chưa đối soát, mức độ tin cậy về việc ngăn tái xâm nhập, thời điểm đánh giá tiếp theo và đầu mối hỗ trợ. Tránh tuyên bố "đã khôi phục hoàn toàn" chỉ dựa trên việc ứng dụng trả lời request, hoặc thông báo mất dữ liệu bằng con số chưa được xác minh.

Nếu sự cố có liên quan dữ liệu cá nhân, khách hàng, nhà cung cấp hoặc nghĩa vụ thông báo, cần phối hợp đúng bộ phận phụ trách và căn cứ pháp lý/hợp đồng thực tế. Việc khôi phục kỹ thuật không tự kết thúc trách nhiệm báo cáo hoặc bảo toàn chứng cứ.

## 11. Hồ sơ bằng chứng của một lần recovery

Một hồ sơ recovery có thể dùng trong hệ thống incident management hoặc GRC. Mẫu sau là **YAML minh họa** để liên kết tình trạng, kiểm thử, quyết định và bằng chứng; không phải cấu hình trực tiếp cho một công cụ cụ thể:

~~~yaml
incident:
  id: "IR-RECOVERY-EXAMPLE-026"
  service: "orders-api"
  environment: "production"
  incident_class: "suspected_compromised_workload"
  scope_confirmed_at_utc: "2026-11-28T02:30:00Z"

objectives:
  rto_minutes: 240
  rpo_minutes: 15
  minimum_viable_service:
    - "Xem trạng thái đơn hàng"
    - "Tạo đơn hàng thử theo quy trình an toàn"

recovery:
  strategy: "clean-rebuild-and-verified-restore"
  target_environment: "isolated-orders-recovery"
  source_image_digest: "sha256:example-not-a-real-digest"
  backup_restore_point_utc: "2026-11-28T02:15:00Z"
  backup_integrity_verified: true
  data_reconciliation_complete: false
  credentials_rotated: true
  suspicious_sessions_revoked: true

verification:
  platform_baseline_pass: true
  required_security_logs_verified: true
  identity_access_test_pass: true
  application_smoke_test_pass: true
  business_data_integrity_pass: false
  monitoring_owner_acknowledged: true
  production_traffic_enabled: false

assessment:
  result: "FAIL"
  reason: "Chưa hoàn tất đối soát dữ liệu đơn hàng"
  remediation_owner: "Orders Data Owner"
  next_action: "Đối soát payment events và retry queue trước khi mở ghi"

evidence:
  - "secure-evidence/IR-RECOVERY-EXAMPLE-026/asset-inventory"
  - "secure-evidence/IR-RECOVERY-EXAMPLE-026/restore-report"
  - "secure-evidence/IR-RECOVERY-EXAMPLE-026/identity-checks"
  - "secure-evidence/IR-RECOVERY-EXAMPLE-026/transaction-reconciliation"

approval:
  incident_lead: "Incident Commander"
  business_owner: "Orders Service Owner"
  go_live_decision: "NO_GO"
  review_required: true
~~~

Các mốc thời gian, ID, giá trị true/false và tên nhóm là **giả định dành cho bài học**. Dù nền tảng sạch, quyền đã thay và smoke test đạt, việc chưa đối soát dữ liệu khiến tiêu chí nghiệm thu tổng thể **FAIL** và quyết định hiện tại là **NO_GO**. Nếu có yêu cầu mở dịch vụ đọc hạn chế, phải lập một quyết định khác với phạm vi/điều kiện đã được phê duyệt.

### Bằng chứng tối thiểu cần lưu

Một recovery record nên gắn với:

- **Incident ID, asset/service IDs, phạm vi và timeline:** nguồn thời gian UTC, người thu thập, liên kết tài nguyên.
- **Mục tiêu và quyết định:** RTO/RPO, ưu tiên nghiệp vụ, phương án được chọn, người phê duyệt và lý do.
- **Nguồn khôi phục:** image/build, IaC version, backup ID, restore point và kết quả kiểm tra nguồn.
- **Kết quả thực hiện:** change tickets, runbook step, phiên bản trước/sau, lỗi và rollback nếu xảy ra.
- **Kết quả kỹ thuật:** cấu hình bảo mật, IAM, network, vulnerability checks, logging/detection, health và dữ liệu.
- **Kết quả nghiệp vụ:** thử nghiệm luồng quan trọng, đối soát giao dịch, mất dữ liệu đã xác minh, các giới hạn còn lại.
- **Phát hiện và ngoại lệ:** trạng thái, rủi ro còn lại, người chịu trách nhiệm, thời hạn và kết quả retest.
- **Phê duyệt chuyển giao:** go/no-go, người ký quyết định, thời điểm, mức phục hồi được chấp nhận và kế hoạch giám sát.

Bằng chứng có thể chứa dữ liệu nhạy cảm và thông tin điều tra; phải lưu ở kho được phân quyền, có lịch sử truy cập và thời hạn giữ phù hợp. Không đưa credential, bản sao dữ liệu khách hàng hay toàn bộ artifact forensics vào báo cáo chia sẻ rộng.

## 12. Đo chất lượng recovery bằng chỉ số có kiểm chứng

| Chỉ số | Mục tiêu đo | Cách xác minh và giới hạn |
|---|---|---|
| **Actual recovery duration** | Thời gian thực tế đạt điều kiện nghiệp vụ đã định nghĩa. | Mốc khởi đầu, điều kiện kết thúc, timeline và chấp thuận của owner; không dùng thời gian VM boot. |
| **RTO achievement** | Dịch vụ đạt mục tiêu thời gian hay không. | So sánh duration với RTO đã phê duyệt của đúng dịch vụ và mức chức năng. |
| **Actual data recovery gap** | Khoảng dữ liệu bị lùi hoặc còn thiếu chưa đối soát. | Backup point, event ledger và kết quả reconciliation; không dựa riêng timestamp snapshot. |
| **RPO achievement** | Mất dữ liệu nằm trong mức cho phép hay không. | So sánh kết quả dữ liệu thực với RPO; đánh dấu chưa rõ nếu chưa đối soát. |
| **Recovery test pass rate** | Tỷ lệ tiêu chí kỹ thuật/nghiệp vụ đạt trong phạm vi kiểm tra. | Báo riêng FAIL/INCONCLUSIVE, test nào là bắt buộc và test nào chưa thực hiện. |
| **Clean-state coverage** | Tỷ lệ asset được xác minh từ nguồn tin cậy, quyền và baseline đạt. | Đối chiếu inventory; node mới/đã scale cũng nằm trong phạm vi. |
| **Reinfection/recurrence signal** | Có dấu hiệu tái xâm nhập hoặc lỗi tương tự sau mở lại không. | EDR/SIEM, audit log, threat hunting và thời gian quan sát; không có alert không bảo đảm sạch. |
| **Open residual risks** | Số rủi ro chưa khắc phục, mức ưu tiên và tuổi của ngoại lệ. | Risk register, owner, người phê duyệt, thời hạn và điều kiện review. |
| **Exercise readiness** | Runbook và khả năng phục hồi có được diễn tập định kỳ theo rủi ro không. | Kết quả tabletop/restore test, những gì không được thử và hành động cải tiến. |

Để báo cáo recovery trung thực, cần tách **khả năng khôi phục đã đo** khỏi **giới hạn chưa được kiểm chứng**. Một bài diễn tập trên staging có thể xác nhận quy trình restore nhưng không chứng minh chắc chắn RTO của production nếu dung lượng, cấu hình, dependency hoặc lưu lượng khác đáng kể.

## 13. Tình huống thực hành: Ransomware trên hệ thống xử lý hóa đơn

Một công ty có hệ thống hóa đơn chạy trên ba VM và một managed database. Một nhân viên vận hành phát hiện mã hóa trái phép trên một VM, trong khi audit cloud ghi nhận một tài khoản có quyền cao vừa tạo access key mới và sửa chính sách backup. Nhóm hạ tầng xác nhận bản backup gần nhất có thể giải mã được và đề xuất khôi phục nguyên trạng VM từ snapshot rồi mở lại kết nối với database để đáp ứng RTO.

Dữ kiện ban đầu:

- VM bị ảnh hưởng đã được cách ly; chưa xác định toàn bộ tài khoản/secret mà kẻ tấn công có thể đã truy cập.
- Snapshot VM gần nhất được tạo **sau thời điểm đầu tiên nghi ngờ xâm nhập**.
- Có một golden image đã phê duyệt trước sự cố và backup database được lưu ở tài khoản khác.
- Tài khoản cloud dùng cho backup vẫn chia sẻ một trust relationship với tài khoản bị ảnh hưởng.
- Bộ phận kinh doanh cần xem hóa đơn gấp, nhưng chức năng tạo hóa đơn mới có thể tạm ngừng.
- Hệ thống SIEM chưa ghi nhận được log từ môi trường recovery mới.

### Câu hỏi

1. Có nên khôi phục nguyên trạng VM từ snapshot gần nhất rồi mở production ngay không? Vì sao?
2. Những đường tái xâm nhập và nguồn bằng chứng nào phải được kiểm tra?
3. Có thể cung cấp dịch vụ tối thiểu theo cách nào để cân bằng nhu cầu kinh doanh và an toàn?
4. Điều kiện và bằng chứng nào đủ để đưa chức năng tạo hóa đơn trở lại?

### Hướng giải quyết

**1. Bảo toàn chứng cứ và điều tra phạm vi.** Lưu bằng chứng VM, audit thay đổi quyền và backup policy, lịch sử tạo access key, kết nối và các snapshot liên quan theo quy trình. Xác định principal có thể truy cập máy chủ, database, backup và pipeline triển khai. Không xóa dữ liệu điều tra trước khi có quyết định phù hợp.

**2. Không tin ngay snapshot mới nhất.** Snapshot VM được tạo sau dấu hiệu xâm nhập có nguy cơ chứa persistence hoặc cấu hình bị cài cắm. Ưu tiên dựng VM mới từ golden image đã kiểm tra, cập nhật bản vá và hardening; chỉ nhập lại dữ liệu/cấu hình đã được xác minh. Kiểm tra tính tin cậy của nguồn golden image và hệ thống build.

**3. Kiểm tra identity và chuỗi cung ứng.** Thu hồi access key lạ, session liên quan, rà soát trust relationship với backup account, key policy, account quản trị và credential của ứng dụng. Nếu backup account chưa được bảo vệ độc lập thực sự, phải xác minh lại quyền truy cập và lịch sử thao tác trước khi sử dụng backup.

**4. Khôi phục trong vùng cô lập.** Dựng môi trường hạn chế kết nối, kiểm tra backup database, chọn điểm phục hồi an toàn dựa trên timeline, khôi phục vào môi trường thử nghiệm và kiểm tra integrity. Đối chiếu danh sách hóa đơn và giao dịch phát sinh quanh mốc sự cố; ghi rõ dữ liệu còn thiếu hoặc cần xử lý thủ công.

**5. Phục hồi chức năng tối thiểu nếu được phê duyệt.** Có thể xem xét cung cấp **chế độ chỉ đọc** trên dữ liệu đã được xác minh và môi trường sạch, với quyền tối thiểu, giới hạn người dùng và quyết định chấp nhận rủi ro. Không bật chức năng tạo hóa đơn khi dữ liệu chưa nhất quán hoặc log/detection chưa sẵn sàng.

**6. Sửa và kiểm tra logging.** Cài/định tuyến lại audit từ hệ thống mới, tạo sự kiện kiểm thử có kiểm soát, kiểm tra SIEM nhận đúng, alert tới người trực và không có dấu hiệu xâm nhập mới trong cửa sổ đánh giá.

**7. Go/no-go cho chức năng ghi.** Chỉ mở khi IAM, network, image/baseline, integrity, nghiệp vụ, logging và giám sát đạt tiêu chí; chủ nghiệp vụ và incident lead phê duyệt. Thực hiện canary, quan sát error/alert, sẵn sàng cô lập nếu dấu hiệu bất thường quay lại.

### Quyết định minh họa

| Điều kiện | Trạng thái giả định ban đầu | Kết luận |
|---|---|---|
| VM mới từ nguồn sạch | Chưa triển khai | Không dùng snapshot VM nghi nhiễm làm nguồn tin cậy duy nhất. |
| Quyền cloud và backup trust | Chưa xác minh | Có nguy cơ tái xâm nhập, cần đóng trước khi mở kết nối rộng. |
| Backup database | Có thể giải mã; chưa đối soát | Chưa đủ bằng chứng về điểm khôi phục và dữ liệu. |
| Môi trường logging | SIEM chưa nhận event | Chưa đạt tiêu chí quan sát. |
| Nhu cầu đọc hóa đơn | Có nhu cầu khẩn | Có thể đánh giá phương án giới hạn, có người phê duyệt. |
| Chức năng tạo hóa đơn | Chưa đủ gate | NO_GO cho chức năng ghi tới khi retest và phê duyệt. |

Đây là bài tập về **quyết định theo bằng chứng**: mức độ cấp thiết của nghiệp vụ ảnh hưởng thứ tự phục hồi và phạm vi dịch vụ tối thiểu, nhưng không làm biến mất yêu cầu xác minh mối đe dọa, dữ liệu và kiểm soát.

## 14. Sai lầm thường gặp trong Recovery

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ cần ứng dụng chạy lại là đóng sự cố. | Có thể còn persistence, quyền chiếm đoạt hoặc dữ liệu sai. | Đặt gate về nền tảng, IAM, dữ liệu, logging và nghiệm thu nghiệp vụ. |
| Khôi phục nguyên host từ snapshot sau thời điểm xâm nhập. | Đưa mã độc/cấu hình độc hại trở lại. | Đánh giá timeline, ưu tiên clean rebuild và kiểm chứng dữ liệu nhập lại. |
| Mở traffic trước khi kiểm tra log và detection. | Tái xâm nhập không được nhận biết. | Test pipeline và alert trước khi mở rộng, giám sát tăng cường. |
| Coi backup job success là chứng minh restore được. | Backup có thể lỗi, thiếu dữ liệu hoặc không giải mã được. | Diễn tập restore, kiểm tra integrity và dependency. |
| Đổi mật khẩu nhưng bỏ qua token/role liên quan. | Kẻ tấn công vẫn dùng session hoặc quyền còn tồn tại. | Rà soát toàn bộ identity, trust, key và cơ chế thu hồi. |
| Failover sang vùng dự phòng dùng chung quyền bị lộ. | Phạm vi xâm nhập chuyển sang môi trường dự phòng. | Xác minh tách biệt credential và quyền hiệu lực trước chuyển. |
| Không đối soát giao dịch khi replay queue. | Thanh toán lặp, thiếu đơn hàng hoặc dữ liệu không nhất quán. | Kiểm tra idempotency, ledger, reconcile và phê duyệt data owner. |
| Chỉ đo thời gian VM boot cho RTO. | Báo cáo sai trạng thái nghiệp vụ thực tế. | Định nghĩa thời điểm bắt đầu/kết thúc và điều kiện mức dịch vụ. |
| Không giữ artifact điều tra trước reimage. | Mất bằng chứng root cause và không thể đối chiếu pháp lý. | Bảo toàn chứng cứ theo runbook và thẩm quyền trước hành động phá hủy. |
| Rollback tự động về hệ thống cũ nghi nhiễm. | Tái mở đường xâm nhập. | Đặt rollback về điểm tin cậy/cô lập và quy trình no-go. |
| Chấp nhận rủi ro không hạn và không owner. | Các điểm chưa khắc phục bị quên sau go-live. | Risk register có người duyệt, thời hạn, remediation và review. |
| Không diễn tập recovery. | Đến khi sự cố xảy ra mới phát hiện backup/secret/ứng dụng không tương thích. | Thử khôi phục theo kịch bản có rủi ro, cập nhật runbook và kiểm tra lại. |

## 15. Checklist nghiệm thu Recovery và bài tập tự đánh giá

Trước khi quyết định mở lại dịch vụ, người làm security assurance nên xác minh:

1. **Phạm vi:** Incident ID, danh sách tài sản và nguồn dữ liệu bị ảnh hưởng đã đầy đủ tới mức có thể đưa ra quyết định chưa? Các giới hạn còn chưa biết đã được ghi nhận?
2. **Nguyên nhân và containment:** Các đường tái xâm nhập đã biết đã được xử lý hoặc kiểm soát đủ cho phạm vi phục hồi được phê duyệt chưa?
3. **Nguồn tin cậy:** Image, IaC, artifact, backup, key, secret và môi trường quản trị được chọn có bằng chứng về nguồn gốc và tình trạng an toàn không?
4. **Bảo toàn chứng cứ:** Snapshot, log, timeline và dữ liệu liên quan điều tra đã được lưu theo thẩm quyền trước thao tác xóa/rebuild chưa?
5. **Dữ liệu:** Restore point, consistency, giao dịch còn thiếu, khả năng replay và đối soát với hệ thống ngoài đã được xác nhận chưa?
6. **Chức năng:** Những luồng nghiệp vụ tối thiểu và toàn bộ phụ thuộc cần thiết đã được kiểm thử trên môi trường mục tiêu chưa?
7. **Kiểm soát bảo mật:** IAM, MFA, session/token revoke, network segmentation, patch, hardening, audit log và detection có đạt tiêu chí không?
8. **Quan sát sau mở lại:** Có canary, ngưỡng dừng, nguồn telemetry, người trực và phương án cô lập/rollback về trạng thái đáng tin không?
9. **Mục tiêu:** RTO/RPO được báo bằng cách đo và đối soát phù hợp; trường hợp chưa đủ dữ liệu không bị ghi thành đạt?
10. **Quyết định:** Ai phê duyệt go/no-go, dịch vụ được mở ở mức nào, những ngoại lệ/rủi ro còn lại có owner và thời hạn?
11. **Bàn giao:** Nhóm vận hành và bộ phận nghiệp vụ đã nhận được timeline, giới hạn, bằng chứng, liên hệ khẩn và lịch review chưa?
12. **Cải tiến:** Kết quả diễn tập/sự cố đã được chuyển thành thay đổi runbook, backup, IAM, architecture, logging và kiểm thử tiếp theo?

### Câu hỏi tình huống ngắn

Một dịch vụ đạt mục tiêu RTO vì ứng dụng đã hoạt động trong 2 giờ, nhanh hơn mốc 4 giờ. Tuy nhiên, nguồn logging không ghi nhận truy cập quản trị và chưa ai xác minh dữ liệu được restore từ bản sao lưu có trước thời điểm xâm nhập. Có thể kết luận Recovery đạt đầy đủ không?

**Gợi ý:** Chưa thể kết luận. Mục tiêu thời gian đã đạt ở phạm vi nghiệp vụ được đo, nhưng **G3 — trusted data** và **G5 — security readiness** chưa có bằng chứng phù hợp. Cần giữ trạng thái chưa đạt hoặc chưa đủ bằng chứng tại các gate, giới hạn dịch vụ nếu cần và bổ sung kiểm tra trước khi duyệt khôi phục đầy đủ.

**Một quá trình Recovery có giá trị assurance khi hệ thống không chỉ hoạt động trở lại mà còn chứng minh được nguồn khôi phục đáng tin, dữ liệu và chức năng đúng, đường tái xâm nhập được kiểm soát, hoạt động giám sát sẵn sàng và mọi quyết định chấp nhận rủi ro đều có thể truy vết bằng bằng chứng.**
