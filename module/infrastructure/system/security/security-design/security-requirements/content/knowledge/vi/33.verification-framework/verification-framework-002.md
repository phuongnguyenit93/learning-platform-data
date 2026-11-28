# Mục tiêu của ASVS

## 1. ASVS giúp giải quyết vấn đề gì?

**ASVS — Application Security Verification Standard** là chuẩn yêu cầu bảo mật ứng dụng của OWASP, dùng cho thiết kế, phát triển và kiểm chứng ứng dụng web cùng dịch vụ web. Nó cung cấp một cơ sở chung để xác định các kiểm soát bảo mật cần đạt và đánh giá chúng có căn cứ. [Nguồn: OWASP ASVS Overview](https://asvs.owasp.org/).

Một yêu cầu như “hệ thống phải an toàn” không cho biết đội phát triển phải tạo hành vi nào, người kiểm thử phải quan sát điều gì hoặc bên nghiệm thu nên chấp nhận dựa trên bằng chứng nào. ASVS giúp tạo một ngôn ngữ yêu cầu chung, để các bên chuyển từ mong muốn chung sang đối tượng có thể kiểm chứng.

Trong chương **Verification framework** của module yêu cầu bảo mật, mục tiêu học ASVS là biết dùng chuẩn làm nền cho đặc tả và xác minh. Nhóm vẫn phải bổ sung ngữ cảnh dữ liệu, quyền, kiến trúc, luồng nghiệp vụ và điều kiện vận hành của sản phẩm. Một mã ASVS gắn vào ticket chưa tự biến ticket đó thành yêu cầu đầy đủ.

Ví dụ: một dịch vụ xuất báo cáo cần ngăn caller điều khiển lệnh hệ điều hành, bảo đảm quyền đọc đúng report và không lộ dữ liệu tenant khác. ASVS hỗ trợ xác định các mục tiêu kiểm soát chung; đội sản phẩm phải chốt report nào được xuất, ai được phép, đường thực thi nào tạo tệp và bằng chứng nào cho thấy điều kiện được giữ.

### Phạm vi phiên bản trong bài

Các ví dụ tham chiếu **ASVS 5.0.0**. Đây là bản có tài liệu phát hành chính thức được dùng làm mốc của bài; khi áp dụng, phải ghi phiên bản đã chọn và quản lý thay đổi, không tự đổi sang nội dung nhánh phát triển. [Nguồn: OWASP ASVS repository](https://github.com/OWASP/ASVS).

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích các mục tiêu của ASVS đối với phát triển, đánh giá và nghiệm thu.
2. Phân biệt yêu cầu của chuẩn, đặc tả sản phẩm, phương pháp kiểm chứng và bằng chứng.
3. Chọn phạm vi, phiên bản và mức kiểm chứng theo rủi ro.
4. Truy vết từ yêu cầu tham chiếu tới kiến trúc, test và kết luận cho một release.
5. Đọc báo cáo ASVS mà không nhầm phần chưa kiểm chứng hoặc ngoại lệ thành đạt.

## 2. Ba mục tiêu sử dụng cốt lõi

OWASP mô tả ASVS như một thước đo để đánh giá mức tin cậy vào ứng dụng, hướng dẫn xây dựng các kiểm soát đáp ứng yêu cầu và cơ sở nêu yêu cầu kiểm chứng khi mua sắm phần mềm. [Nguồn: OWASP ASVS Overview](https://asvs.owasp.org/).

### 2.1. Tạo cơ sở đánh giá có thể giải thích

Thay vì chỉ nhận kết luận “ứng dụng khá an toàn”, bên đánh giá và owner có thể hỏi: yêu cầu nào đã được xem xét, áp dụng cho phần nào, bằng chứng ra sao và khoảng trống còn lại là gì. Tính hữu ích nằm ở khả năng kiểm tra kết luận, không chỉ ở số lượng ô được đánh dấu.

Hai báo cáo đều ghi “không tìm thấy lỗ hổng” có thể rất khác nhau: một bên chỉ quét một endpoint không có tài khoản; bên còn lại kiểm tra API, worker, cấu hình quyền và các luồng dữ liệu. Một hồ sơ yêu cầu rõ phạm vi giúp người đọc thấy khác biệt đó.

### 2.2. Hướng dẫn xây kiểm soát từ giai đoạn đặc tả

Đội phát triển có thể dùng yêu cầu tham chiếu để đặt câu hỏi trước khi code: quyền được kiểm tra ở đâu, dữ liệu ra có thể tới ai, credential có bị caller chọn và lỗi có dẫn tới fallback ngoài chính sách không. Những quyết định này cần xuất hiện trong thiết kế và acceptance criteria của tính năng.

Điều này giảm tình huống đến cuối dự án mới phát hiện một yêu cầu đòi hỏi đổi kiến trúc. Tuy nhiên, việc dùng ASVS không tự chọn thư viện, cơ chế IAM hoặc mọi giá trị timeout cho sản phẩm; các lựa chọn đó cần quyết định và kiểm chứng trong ngữ cảnh thực tế.

### 2.3. Tạo ngôn ngữ nghiệm thu với nhà cung cấp

Thay câu “nhà cung cấp phải tuân thủ OWASP”, hồ sơ có thể nêu phiên bản, mức mục tiêu, hệ thống trong phạm vi, cách xử lý mục không áp dụng, loại bằng chứng, bên kiểm chứng và điều kiện chấp nhận. Đây là cách tổ chức yêu cầu của ví dụ, không phải mẫu hợp đồng pháp lý.

Một sản phẩm có nhiều module hoặc tích hợp cần ghi rõ phần nào được kiểm chứng. Bằng chứng của một portal không tự áp dụng cho worker, API mới hoặc một môi trường có cấu hình quyền khác. Kết quả cần hỗ trợ quyết định thực tế của người mua, không chỉ một tuyên bố tiếp thị.

## 3. ASVS định nghĩa mục tiêu kiểm soát; sản phẩm phải làm rõ cách áp dụng

### 3.1. Bốn đối tượng không nên trộn lẫn

| Đối tượng | Trả lời câu hỏi | Ví dụ trong dịch vụ báo cáo |
|---|---|---|
| Yêu cầu tham chiếu | Kết quả bảo mật nào cần được đáp ứng? | Ngăn đầu vào dẫn đến thực thi lệnh ngoài quyền |
| Đặc tả sản phẩm | Ai, dữ liệu nào, hành động nào và ràng buộc nào? | Caller chỉ gửi report ID và định dạng được cho phép, không gửi command/path |
| Thiết kế/triển khai | Kiểm soát được thực hiện ở đâu và bằng cơ chế nào? | Phân quyền ở service; exporter dùng thư viện trong tiến trình và đường lưu do máy chủ cấp |
| Phương pháp/bằng chứng | Làm sao quan sát được kết quả? | Review sink, test input âm và quan sát không có thao tác hệ điều hành ngoài hợp đồng |

Các hàng cần liên kết nhưng không thay thế nhau. Có test tên “ASVS check” không chứng minh yêu cầu đã được hiểu đúng. Có một thư viện được phê duyệt cũng không chứng minh mọi đường gọi đều dùng thư viện ấy.

### 3.2. Phạm vi của chuẩn và phạm vi rủi ro sản phẩm

ASVS tập trung các kết quả bảo mật của ứng dụng; bản 5.0 không phải đặc tả quy trình CI/CD hay toàn bộ quản trị hạ tầng. Một proxy mà ứng dụng dựa vào để cưỡng chế kiểm soát vẫn có thể cần được xét cho chức năng đó. [Nguồn: ASVS 5.0.0 — What is the ASVS?](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/en/0x03-What-is-the-ASVS.md).

Trong hồ sơ sản phẩm, nhóm cần phân biệt “ngoài phạm vi ASVS” với “không có rủi ro”. Backup, quyền quản trị host, chuỗi phát hành hoặc phục hồi có thể vẫn là yêu cầu an toàn bắt buộc của hệ thống dù cần nguồn tham chiếu và phương pháp riêng.

Ví dụ: test phân quyền API đạt chưa chứng minh backup không bị đọc trái phép. Nếu ứng dụng dựa vào gateway chặn đích mạng, chỉ test code ứng dụng mà không xác minh cấu hình gateway liên quan cũng chưa đủ cho kết luận về kiểm soát đó.

### 3.3. Không dùng chuẩn để thay mô hình đe dọa

Threat model nêu tài sản, đối phương, entry point, ranh giới và các kịch bản cụ thể. Một catalog chung không tự biết quy tắc chia sẻ báo cáo, giá trị dữ liệu hoặc quyền của bộ phận vận hành trong tổ chức.

Do đó, một hồ sơ tốt đi theo cả hai hướng: kiểm tra catalog để không quên lớp kiểm soát quan trọng, đồng thời đưa rủi ro nghiệp vụ trở lại thành yêu cầu bổ sung. Một yêu cầu bổ sung không có mã ASVS vẫn có thể là điều kiện phát hành bắt buộc nếu sản phẩm cần nó.

## 4. Mức kiểm chứng phục vụ việc lựa chọn theo rủi ro

ASVS 5.0 có L1, L2 và L3, mở rộng tập yêu cầu và độ sâu bảo vệ. L1 là điểm khởi đầu tối thiểu; L2 là mục tiêu cho phần lớn ứng dụng; L3 hướng tới mức bảo vệ cao nhất. L2 bao gồm các yêu cầu áp dụng của L1; L3 bao gồm cả ba mức. Chọn mức cần dựa vào rủi ro; L1 không mặc nhiên chỉ cần kiểm thử black-box. [Nguồn: ASVS 5.0.0 — Verification Levels](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/en/0x03-What-is-the-ASVS.md).

### 4.1. Chọn mức và tạo hồ sơ áp dụng

Với dịch vụ chứa báo cáo nhạy cảm, nhóm nên xem xét độ nhạy dữ liệu, đối tượng truy cập, tác động vượt quyền, tích hợp ngoài và kỳ vọng của người dùng trước khi chốt mục tiêu. Không chọn mức thấp chỉ để vừa ngân sách rồi mô tả đó là mức đủ cho mọi rủi ro.

Hồ sơ nội bộ nên ghi phiên bản, mức mục tiêu, các phần áp dụng, yêu cầu bổ sung và lý do phân loại. Đây là quyết định quản lý rủi ro của tổ chức; mức trên giấy không nâng được chất lượng triển khai nếu thiếu bằng chứng.

### 4.2. Không đánh đồng một vài kiểm soát nâng cao với toàn bộ mức cao hơn

Một sản phẩm có MFA, khóa bảo vệ tốt hoặc một bài test nâng cao chưa tự đáp ứng mọi yêu cầu áp dụng của một mức. Ngược lại, rủi ro cụ thể có thể đòi hỏi một kiểm soát vượt baseline đang chọn; nhóm không nên bỏ nó chỉ vì nằm ngoài kế hoạch tối thiểu.

Nếu điều chỉnh catalog thành hồ sơ riêng, phải giữ liên kết với yêu cầu gốc và diễn đạt trung thực phạm vi. Cắt một yêu cầu còn áp dụng rồi ghi “đạt đầy đủ mức X” làm người đọc hiểu sai kết luận. Hồ sơ dựa trên ASVS và tuyên bố đáp ứng một mức ASVS là hai loại thông tin cần phân biệt rõ.

## 5. Phiên bản và mã yêu cầu là điều kiện của truy vết

### 5.1. Mã cần kèm phiên bản

OWASP khuyến nghị định danh theo dạng `v<version>-<chapter>.<section>.<requirement>` vì nội dung và số thứ tự có thể thay đổi giữa các phiên bản. Ví dụ chính thức `v5.0.0-1.2.5` liên quan bảo vệ trước OS command injection. [Nguồn: OWASP ASVS — How to Reference Requirements](https://github.com/OWASP/ASVS#how-to-reference-asvs-requirements).

Không lấy ý nghĩa một mã ở bản cũ rồi gắn vào bản mới mà chưa đối chiếu. Report hoặc test chỉ ghi “ASVS 1.2.5” thiếu phiên bản sẽ khó được diễn giải nhất quán khi chuẩn thay đổi.

### 5.2. Phân biệt mã chuẩn với mã sản phẩm

Một yêu cầu chuẩn có thể cần nhiều điều kiện cụ thể để áp dụng cho sản phẩm. Ngược lại, một cơ chế dùng chung có thể góp phần đáp ứng nhiều yêu cầu. Quan hệ mapping không bắt buộc là một–một.

```text
ASVS reference có phiên bản
    ↓ làm rõ trong ngữ cảnh tài sản và rủi ro
Yêu cầu sản phẩm với ID riêng
    ↓ xác định nơi cưỡng chế
Thiết kế, code và cấu hình
    ↓ quan sát bằng phương pháp phù hợp
Test/review và bằng chứng theo release
    ↓ quyết định có phạm vi
Kết quả, finding và việc xử lý còn lại
```

Trong bài, các mã `EXP-*`, `ADOPT-*` và `AC-*` là mã minh họa do bài đặt, không phải số yêu cầu OWASP. Chúng thể hiện cách tổ chức hồ sơ và tiêu chí nghiệm thu. Khi mapping thêm một mục của chuẩn, người thực hiện phải đọc đúng nội dung/version rồi mới kết luận quan hệ.

## 6. Ví dụ: từ mục tiêu ASVS tới yêu cầu xuất báo cáo

### 6.1. Ngữ cảnh và rủi ro

Xét endpoint `POST /v1/reports/{report_id}/export` trả một bản xuất JSON. Caller là người dùng đã xác thực trong một tenant. Rủi ro gồm thực thi lệnh ngoài quyền nếu đầu vào điều khiển công cụ xuất, đọc report ngoài phạm vi và lộ dữ liệu qua lỗi/log.

Trong ví dụ này, `v5.0.0-1.2.5` được dùng cho mục tiêu chống OS command injection. Các yêu cầu về quyền, dữ liệu và audit bên dưới là đặc tả bổ sung của ví dụ; bài không gán mã ASVS chưa đối chiếu cho chúng.

| ID sản phẩm | Yêu cầu minh họa | Điểm cưỡng chế | Bằng chứng cần có |
|---|---|---|---|
| EXP-01 | Chỉ principal được phép đọc đúng report của tenant có thẩm quyền mới được xuất. | Service cấp quyền và truy vấn dữ liệu | Ca hợp lệ, cùng tenant sai quyền và chéo tenant; không đọc/cấp dữ liệu báo cáo ngoài quyền |
| EXP-02 | Dữ liệu từ caller không được trở thành lệnh hoặc làm mở rộng thao tác hệ điều hành; luồng mẫu dùng exporter trong tiến trình. | Exporter và các sink liên quan | Review mọi đường gọi exporter/job trong phạm vi và test input đặc biệt với quan sát tác động |
| EXP-03 | Chỉ nhận report ID và định dạng JSON theo hợp đồng; đường lưu và credential do máy chủ quản lý. | Schema, service và storage adapter | Caller không chọn path/command/credential; các trường ngoài hợp đồng không làm đổi đích hoặc quyền |
| EXP-04 | Bản xuất tối đa 1 MiB UTF-8 trong hồ sơ ví dụ; vượt giới hạn phải dừng có kiểm soát và không công bố tệp dở. | Bộ xuất/lưu có bộ đếm và trạng thái | Test dưới/ngay/trên ngưỡng, cleanup và trạng thái công bố |
| EXP-05 | Audit được hành động bằng định danh phù hợp, không ghi payload báo cáo, secret hoặc URL mang quyền. | API/worker/audit sink | Đối chiếu kết quả và kiểm tra marker nhạy cảm fixture trên các đầu ra liên quan |

Giá trị 1 MiB và hợp đồng JSON là quyết định minh họa của sản phẩm, không phải con số hoặc yêu cầu định dạng do ASVS quy định chung. `1 MiB = 1.048.576 byte`.

### 6.2. Luồng triển khai tham chiếu

```text
export_report(request):
    context = verified_identity_and_authorized_tenant(request)
    validate_report_id_and_fixed_export_schema(request)
    report = authorize_and_load_exact_report(context, request.report_id)
    content = in_process_json_exporter.stream(report, max_utf8_bytes=1MiB)
    result = store_with_server_owned_target_and_partial_state_policy(content)
    audit_by_report_id_without_sensitive_payload(context, result)
    return authorized_export_result(result)
```

Các hàm mô tả trách nhiệm, không phải API bảo mật sẵn có. Exporter trong tiến trình chỉ là phương án của ví dụ; phải xác minh thư viện, wrapper hoặc job không âm thầm gọi công cụ ngoài theo dữ liệu caller. Đồng thời cần kiểm tra quyền truy cập bản xuất sau khi tạo; cấp quyền xuất không đồng nghĩa mọi người đều được đọc tệp.

### 6.3. Mapping một endpoint chưa đủ cho kết luận toàn ứng dụng

EXP-02 hỗ trợ đánh giá yêu cầu tham chiếu ở luồng xuất báo cáo, nhưng một chức năng chuyển đổi tệp khác vẫn có thể gọi lệnh hệ điều hành. Bằng chứng phải nêu chính xác vùng code/config và các đường đã kiểm tra.

Không dùng một test input đặc biệt bị từ chối ở API làm bằng chứng duy nhất rằng không có thao tác ngoài quyền: có thể hành động đã xảy ra rồi mới trả lỗi. Cần quan sát sink, process hoặc fixture liên quan, trong môi trường cô lập không chứa dữ liệu/credential production.

## 7. Kiểm chứng bằng nhiều loại bằng chứng

### 7.1. Chọn phương pháp theo yêu cầu

ASVS không quy định chi tiết từng thủ tục test. Việc xác minh có thể cần tài liệu, code, cấu hình, tài khoản và trao đổi với đội phát triển; chạy một công cụ tự động không đủ cho toàn bộ yêu cầu. Báo cáo cần nêu phạm vi, những mục đã kiểm tra và khoảng trống. [Nguồn: ASVS 5.0.0 — Assessment and Certification](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/en/0x04-Assessment_and_Certification.md).

Với hồ sơ minh họa, có thể tổ chức bằng chứng như sau:

| Câu hỏi cần xác minh | Phương pháp phù hợp | Giới hạn cần ghi |
|---|---|---|
| Quy tắc quyền của report đã được xác định chưa? | Review đặc tả, mô hình quyền và quyết định nghiệp vụ | Tài liệu tồn tại chưa chứng minh code cưỡng chế đúng |
| API và worker có cùng giữ quyền không? | Review code/cấu hình và test tích hợp với principal khác nhau | Một đường HTTP đạt không đại diện mọi job |
| Caller có điều khiển lệnh/đích xuất không? | Phân tích luồng dữ liệu tới sink và test âm với fixture quan sát | Scanner không tìm thấy không chứng minh mọi sink đã được xem |
| Tệp dở có bị công bố khi vượt giới hạn không? | Test biên, fault injection và quan sát trạng thái storage | Chỉ đo response code không cho biết nội dung đã được lưu ra sao |
| Kết quả áp dụng cho release nào? | Đối chiếu commit, artifact digest, cấu hình và môi trường | Test trên artifact/config khác cần đánh giá lại phạm vi |

Các phương pháp bổ sung cho nhau. Một kết luận có thể cần nhiều bằng chứng, và một test tự động có thể hỗ trợ nhiều yêu cầu nếu nêu rõ thuộc tính đã quan sát. Không đếm số công cụ như số kiểm soát đã được xác minh.

### 7.2. Quyết định bảo mật và triển khai cần được kiểm tra riêng

ASVS 5.0 có các yêu cầu ghi nhận quyết định bảo mật và các yêu cầu triển khai tương ứng; xác minh quyết định đã được nêu và xác minh kiểm soát thực tế là hai việc riêng. [Nguồn: ASVS 5.0.0 — Documented Security Decisions](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/en/0x03-What-is-the-ASVS.md).

Trong ví dụ, tài liệu ghi tenant lấy từ danh tính có thẩm quyền, nhưng worker lại tin `tenant_id` trong payload queue. Tài liệu có thể đủ để biết thiết kế mong muốn, còn triển khai vẫn vi phạm đặc tả. Không chuyển kết quả review tài liệu thành PASS cho mọi đường thực thi.

Ngược lại, nếu code hiện có một timeout nhưng nhóm chưa xác định thời điểm bắt đầu, dữ liệu áp dụng hoặc hành vi khi hết hạn, người kiểm chứng khó biết giá trị đó có đáp ứng mục tiêu không. Cần làm rõ quyết định, thay vì chọn một thông số ngẫu nhiên làm chuẩn nghiệm thu.

### 7.3. Record bằng chứng phải có ngữ cảnh

Một record hữu ích gồm: yêu cầu có phiên bản, yêu cầu sản phẩm, phạm vi, phương pháp, dữ liệu/principal fixture, expected/actual, nguồn bằng chứng, commit/artifact/configuration, thời điểm, người thực hiện và finding liên quan. Với kiểm soát do gateway/provider thực hiện, cần record đúng cấu hình và trách nhiệm ở thành phần đó.

Không đưa secret, dữ liệu khách hàng hoặc URL mang quyền vào báo cáo chỉ để chứng minh đã test. Dùng dữ liệu tổng hợp và đầu ra đã che theo chính sách; bằng chứng vẫn phải đủ để người có quyền tái hiện hoặc đánh giá lại kết luận.

## 8. Trạng thái, mục không áp dụng và cách đo tiến độ

### 8.1. Trạng thái hồ sơ không phải tất cả đều là kết luận đạt

Bảng dưới là mô hình quản lý do bài đề xuất, không phải danh sách trạng thái bắt buộc của ASVS:

| Trạng thái nội bộ | Cách hiểu | Cách dùng khi báo cáo mức đáp ứng |
|---|---|---|
| PASS | Có bằng chứng đủ cho yêu cầu trong phạm vi đã nêu | Được tính đạt cho phạm vi/version đó |
| FAIL | Có điều kiện vi phạm yêu cầu | Giữ finding và việc xử lý; không tính đạt |
| NOT_VERIFIED | Chưa thực hiện hoặc chưa có đủ bằng chứng | Chưa có kết luận; không coi là sạch |
| BLOCKED | Không thể kiểm chứng do thiếu quyền, môi trường hoặc phụ thuộc | Ghi nguyên nhân và owner giải quyết; không tính đạt |
| NOT_APPLICABLE | Điều kiện áp dụng thật sự không tồn tại, có lý do được xác nhận | Ghi rõ lý do và phạm vi; không dùng để che thiếu triển khai |
| RISK_ACCEPTED | Chủ thể có thẩm quyền chấp nhận rủi ro còn lại theo hồ sơ | Quyết định vận hành riêng, không tự đổi FAIL thành PASS |

Một yêu cầu chỉ được gắn PASS cho phần có bằng chứng. Nếu một trong các đường nằm trong phạm vi còn vi phạm, không lấy kết quả endpoint khác để ghi toàn yêu cầu đạt. Tách sub-scope có thể giúp theo dõi, nhưng báo cáo tổng phải phản ánh phần còn thiếu.

### 8.2. Không áp dụng cần khác với chưa làm được

Ví dụ: một giao thức thực sự không được sản phẩm dùng có thể dẫn tới một nhóm yêu cầu có điều kiện không áp dụng, sau khi xác nhận phạm vi và đường tích hợp. Chưa triển khai một kiểm soát cần thiết, thiếu tài khoản test hoặc không xem được source không phải lý do tương đương.

Dùng nhà cung cấp ngoài cũng không tự làm rủi ro biến mất. Cần xác định kiểm soát nào provider chịu trách nhiệm, ứng dụng dựa vào điều gì và bằng chứng nào hỗ trợ điều kiện đó. Không mặc định có thể loại mọi mục xác thực vì “đã dùng identity provider”.

Lý do không áp dụng phải được xem lại khi thêm chức năng, đổi protocol, mở kênh client hoặc thay kiến trúc. Một record N/A của release cũ không phải miễn trừ vĩnh viễn.

### 8.3. Tách tỷ lệ đánh giá khỏi tỷ lệ đáp ứng

Giả sử một hồ sơ thử có 100 dòng tham chiếu: 10 dòng không áp dụng đã được xác nhận, 70 PASS, 5 FAIL và 15 chưa kiểm chứng/bị chặn. Đây là số liệu tự đặt để minh họa phép đo, không phải số lượng yêu cầu của một mức ASVS thật.

```text
Số áp dụng = 100 - 10 = 90
Đã có kết luận PASS/FAIL = 70 + 5 = 75

Coverage đánh giá = 75 / 90 ≈ 83,3%
Tỷ lệ đáp ứng trong phạm vi áp dụng = 70 / 90 ≈ 77,8%
```

Nếu 2 trong 5 FAIL được chấp nhận rủi ro, số PASS vẫn là 70. Nếu 15 dòng chưa có bằng chứng bị bỏ khỏi mẫu số, tỷ lệ sẽ gây hiểu nhầm rằng hồ sơ hoàn tất hơn thực tế.

Ngay cả tỷ lệ cao cũng không cho biết rủi ro còn lại có chấp nhận được không. Một FAIL về quyền đọc dữ liệu tenant có thể quan trọng hơn nhiều PASS khác. Quyết định release cần xét yêu cầu bắt buộc, tác động và thẩm quyền chấp nhận; không lấy phần trăm làm phép bù cho vi phạm nghiêm trọng.

## 9. Dùng ASVS trong vòng đời phát triển và nghiệm thu

### 9.1. Một luồng áp dụng có thể review được

```text
Tài sản + mô hình đe dọa + nghĩa vụ sản phẩm
                    ↓
Phiên bản ASVS + mức mục tiêu + phạm vi có lý do
                    ↓
Mapping yêu cầu gốc → yêu cầu sản phẩm → owner
                    ↓
Thiết kế kiểm soát + quyết định được ghi nhận
                    ↓
Code/config + test/review theo acceptance criteria
                    ↓
Bằng chứng đúng artifact và môi trường
                    ↓
Báo cáo PASS/FAIL/phần chưa biết/N/A + việc xử lý
                    ↓
Quyết định release và đánh giá lại khi điều kiện đổi
```

Đây là cách tổ chức công việc được bài đề xuất để dùng chuẩn trong module yêu cầu bảo mật; không phải quy trình CI/CD do ASVS bắt buộc. Nhóm có thể dùng workflow khác nếu vẫn giữ được phạm vi, ngữ nghĩa yêu cầu và độ tin cậy của kết luận.

### 9.2. Điều khoản nghiệm thu cần đủ cụ thể

Một đề nghị yếu là “đạt OWASP” hoặc “không có lỗi high từ scanner”. Một hồ sơ cụ thể hơn có thể ghi: ứng dụng và các thành phần dựa vào để cưỡng chế kiểm soát nào nằm trong phạm vi; dùng phiên bản/mức nào; bên đánh giá được tiếp cận những gì; báo cáo bao gồm mọi dòng áp dụng và bằng chứng nào; xử lý vi phạm/N/A/ngoại lệ ra sao.

Với dịch vụ báo cáo, cần nêu API, worker xuất, storage adapter, gateway nếu có kiểm soát liên quan và cấu hình môi trường nghiệm thu. Không dùng báo cáo ở chế độ single-tenant làm bằng chứng đủ cho một bản multi-tenant mới nếu các giả định đã thay đổi.

Phải phân biệt “có một báo cáo đánh giá theo ASVS” với “được OWASP cấp chứng nhận”. OWASP không chứng nhận vendor, verifier hoặc phần mềm; các tuyên bố assurance của bên thứ ba không phải chứng nhận chính thức do OWASP bảo chứng. [Nguồn: ASVS 5.0.0 — OWASP's Stance on Certifications](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/en/0x04-Assessment_and_Certification.md).

### 9.3. Đánh giá lại theo thay đổi

Khi đổi phiên bản chuẩn, không chỉ thay nhãn trong report: cần xem mapping và nội dung nào thay đổi. Khi đổi code, feature, provider, cấu hình quyền hoặc topology, cần xác định bằng chứng nào mất hiệu lực và kiểm chứng lại phần bị ảnh hưởng.

Rollback cũng là quyết định với artifact và policy hiện hành. Một release từng được đánh giá có thể không còn chấp nhận được khi phát hiện rủi ro mới hoặc cấu hình đã thay. Hồ sơ cần thể hiện điều kiện còn hiệu lực, thay vì dùng một dấu PASS cũ làm miễn trừ lâu dài.

## 10. Yêu cầu cho một hồ sơ áp dụng ASVS có chất lượng

Các mã `ADOPT-*` sau là yêu cầu quản lý hồ sơ minh họa của bài. Chúng không phải yêu cầu hoặc mức mới của OWASP và không thay catalog đã chọn.

| ID | Yêu cầu của hồ sơ minh họa | Bằng chứng kiểm chứng |
|---|---|---|
| ADOPT-01 | Phải ghi phiên bản, mức mục tiêu, hệ thống/môi trường và các thành phần phụ thuộc để cưỡng chế kiểm soát. | AC-01: người đọc biết chính xác phạm vi kết luận và nguồn chuẩn. |
| ADOPT-02 | Mã ASVS phải có phiên bản và mapping giữ đúng ngữ nghĩa; yêu cầu sản phẩm có ID riêng, không giả làm mã chuẩn. | AC-02: đối chiếu được reference đã xác minh và nội dung sản phẩm tương ứng. |
| ADOPT-03 | Quyết định bảo mật và việc triển khai phải có bằng chứng riêng, gắn owner và nơi cưỡng chế. | AC-03: tài liệu đúng nhưng worker sai quyền vẫn tạo FAIL triển khai. |
| ADOPT-04 | Phương pháp phải phù hợp yêu cầu; scanner hoặc một test endpoint không tự đại diện mọi kiểm soát/đường trong phạm vi. | AC-04: quan sát được cả ca hợp lệ, ca âm và sink/tác động cần kiểm tra. |
| ADOPT-05 | N/A phải có lý do đã xác nhận; chưa kiểm chứng, bị chặn và chấp nhận rủi ro không được tính PASS. | AC-05: các trạng thái khó không biến thành kết quả sạch. |
| ADOPT-06 | Bằng chứng phải gắn revision/artifact/configuration/môi trường và phương pháp; thay đổi liên quan phải kích hoạt đánh giá lại. | AC-06: báo cáo cũ hoặc cấu hình khác không tự được tái sử dụng. |
| ADOPT-07 | Báo cáo phải thể hiện mẫu số, phần chưa biết, finding và giới hạn tuyên bố; không mô tả assessment của bên thứ ba là OWASP cấp chứng nhận. | AC-07: phép đo minh họa đúng và tuyên bố phù hợp nguồn bằng chứng. |
| ADOPT-08 | Nghiệm thu phải có chủ thể chịu trách nhiệm, phạm vi được thống nhất, việc xử lý còn lại và điều kiện chấp nhận có thể kiểm tra. | AC-08: nhà cung cấp và bên nhận hiểu cùng một đầu ra và giới hạn. |

## 11. Ví dụ test và acceptance criteria

### 11.1. Phạm vi của các ca minh họa

Các ca sau kiểm tra cách tổ chức hồ sơ và một số yêu cầu của luồng xuất báo cáo. Chúng không phải bộ test đầy đủ ASVS và không đủ để tự tuyên bố ứng dụng đạt một mức. Dùng tài liệu/bản build fixture, dữ liệu tổng hợp và công cụ quan sát được cấp quyền.

**AC-01 — Chốt phiên bản và phạm vi, truy vết ADOPT-01.**

Given hồ sơ chỉ ghi “ASVS level 2”; when review kế hoạch; then phải bổ sung phiên bản, hệ thống, môi trường và các thành phần liên quan trước khi dùng làm cơ sở nghiệm thu. Thử thêm worker/gateway có vai trò kiểm soát vào kiến trúc; hồ sơ phải nêu chúng được kiểm chứng ở đâu thay vì mặc định báo cáo API đã bao phủ.

**AC-02 — Mã tham chiếu và ngữ nghĩa, truy vết ADOPT-02.**

Đối chiếu `v5.0.0-1.2.5` với nguồn chuẩn, rồi kiểm tra EXP-02 mô tả đóng góp nào cho mục tiêu đó. Thử một record dùng mã không có phiên bản hoặc chép ý nghĩa từ bản khác; record chưa được xác minh không được coi mapping hoàn tất. EXP-01–05 phải được nhận diện là mã sản phẩm, không phải các mục OWASP được bài sáng tạo thêm.

**AC-03 — Tài liệu và thực thi, truy vết ADOPT-03.**

Cho đặc tả ghi đúng tenant từ context nhưng worker fixture tin tenant trong payload. Review tài liệu có thể xác nhận quyết định đã được nêu, còn ca chéo tenant phải cho thấy triển khai chưa đạt. Sau sửa, test cả API và worker cùng các chủ thể hợp lệ/sai quyền; không lấy việc cập nhật tài liệu làm bằng chứng đã sửa code.

**AC-04 — Kiểm chứng tại điểm có tác động, truy vết ADOPT-04.**

Với EXP-02/03, gửi input fixture có ký tự đặc biệt, giá trị format/path/command ngoài hợp đồng và quan sát exporter/sink trong sandbox. Không có thao tác ngoài quyền được phép xảy ra trước hoặc sau phản hồi lỗi. Đồng thời test ca JSON hợp lệ và bản xuất dưới/ngay/trên 1 MiB cho EXP-04; chỉ trả lỗi sau khi đã công bố tệp dở là chưa đạt. Kết quả của ca này phải ghi rõ luồng được thử, không tự đại diện các chức năng gọi OS khác trong ứng dụng.

**AC-05 — Trạng thái và N/A, truy vết ADOPT-05.**

Tạo record thiếu quyền truy cập môi trường, thiếu test và một FAIL có quyết định chấp nhận rủi ro. Không record nào được chuyển PASS hoặc N/A chỉ để hoàn tất bảng. Một N/A hợp lệ phải có điều kiện không áp dụng, người xác nhận và phạm vi; khi thêm tính năng làm điều kiện đổi, record phải được đánh giá lại.

**AC-06 — Bằng chứng và thay đổi, truy vết ADOPT-06.**

Đánh giá artifact A rồi thử dùng cùng report cho artifact B hoặc môi trường có cấu hình gateway/quyền khác. Hệ thống quản lý hồ sơ phải phát hiện khác biệt và xác định phần cần kiểm chứng lại. Khi chuyển phiên bản ASVS, mapping phải được đối chiếu thay vì chỉ thay chuỗi version; bằng chứng còn giữ giá trị cần được giải thích theo phạm vi.

**AC-07 — Phép đo và giới hạn tuyên bố, truy vết ADOPT-07.**

Dùng dữ liệu 100 dòng ở mục 8: phải tính 90 áp dụng, 75 đã có kết luận, coverage khoảng 83,3% và tỷ lệ đáp ứng khoảng 77,8%. Chấp nhận rủi ro 2 FAIL không làm số PASS tăng. Báo cáo phải thể hiện 15 dòng chưa kết luận và các FAIL, không tuyên bố đạt toàn bộ mức mục tiêu hoặc “OWASP chứng nhận” từ số liệu này.

**AC-08 — Đầu ra nghiệm thu, truy vết ADOPT-08.**

Hai bên dùng cùng hồ sơ phiên bản/phạm vi, điều kiện bằng chứng, owner và quy tắc xử lý finding. Thử một report chỉ liệt kê lỗi nhưng không nêu các yêu cầu đã kiểm tra, hoặc một report không chỉ được artifact/môi trường; đầu ra đó chưa đủ theo hợp đồng minh họa. Bản hoàn chỉnh phải cho người nhận xác định được điều gì đạt, chưa đạt, chưa biết và ai chịu trách nhiệm xử lý.

### 11.2. Điều kiện chấp nhận của ví dụ

Các record ADOPT-01–08 cần có bằng chứng tương ứng; EXP-01–05 cần được kiểm chứng trong phạm vi tính năng đã nêu. Một kết luận cho toàn ứng dụng hoặc cho mức ASVS mục tiêu còn cần đánh giá tất cả yêu cầu áp dụng của hồ sơ chuẩn đó, không suy từ tám ca minh họa này.

Các ca trên là đặc tả nghiệm thu để người triển khai thực hiện. Bài không tuyên bố đã chạy chúng trên một sản phẩm cụ thể, đã hoàn thành assessment hoặc đã đáp ứng một mức ASVS.

## 12. Giới hạn cần giữ rõ và nguồn tham chiếu

ASVS giúp tạo cơ sở yêu cầu và kiểm chứng, nhưng không tự chọn hết chính sách nghiệp vụ, làm toàn bộ threat model, chạy test hoặc quyết định thay chủ sở hữu rủi ro. Cần các hoạt động và nguồn hướng dẫn bổ sung để triển khai, vận hành, bảo vệ hạ tầng và xử lý sự cố theo phạm vi hệ thống.

Một bằng chứng hữu ích phải nối được mục tiêu kiểm soát với đặc tả sản phẩm, nơi cưỡng chế, phương pháp và artifact đã kiểm tra. Một danh sách PASS thiếu phạm vi hoặc một chứng thư không chỉ ra được cơ sở đánh giá không thay thế chuỗi đó.

Nguồn chính thức được dùng cho các phát biểu về chuẩn trong bài:

- [OWASP ASVS Overview](https://asvs.owasp.org/): mục tiêu và bối cảnh sử dụng chuẩn.
- [OWASP ASVS repository](https://github.com/OWASP/ASVS): bản phát hành và cách tham chiếu mã có phiên bản.
- [ASVS 5.0.0 — What is the ASVS?](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/en/0x03-What-is-the-ASVS.md): phạm vi, mức kiểm chứng và quyết định bảo mật được ghi nhận.
- [ASVS 5.0.0 — Assessment and Certification](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/en/0x04-Assessment_and_Certification.md): cơ chế kiểm chứng, báo cáo và giới hạn tuyên bố chứng nhận.

Các mô hình trạng thái, số liệu, yêu cầu EXP/ADOPT và test AC là thiết kế minh họa của bài. Chúng giúp chuyển mục tiêu ASVS thành công việc cụ thể và có thể review, đồng thời giữ rõ đâu là nội dung chuẩn và đâu là quyết định cần được tổ chức chịu trách nhiệm.
