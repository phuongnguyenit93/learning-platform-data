# Interactive application testing

## 1. Đặt IAST vào đặc tả yêu cầu bảo mật

Trong chương **Secure development**, interactive application testing được xét theo ngữ cảnh **Interactive Application Security Testing — IAST**: quan sát bên trong ứng dụng đang chạy trong lúc test hoặc người kiểm thử tương tác với nó, nhằm thu thập bằng chứng về hành vi có thể gây rủi ro bảo mật.

IAST thường sử dụng instrumentation, chẳng hạn agent hoặc hook được runtime hỗ trợ, để quan sát các điểm thực thi và luồng dữ liệu. Test chức năng, test tích hợp hoặc thao tác có kiểm soát tạo hoạt động; cơ chế quan sát phân tích phần hoạt động mà nó hỗ trợ. [OWASP DevSecOps Guideline: IAST](https://github.com/OWASP/DevSecOpsGuideline/blob/master/current-version/2-Process/2-4-Test/2-4-1-Interactive-Application-Security-Testing.md)

Trong module yêu cầu bảo mật, mục tiêu không dừng ở “cài agent và lấy báo cáo”. Cần đặc tả:

**Rủi ro ứng dụng → tình huống cần chạy → điểm quan sát phù hợp → bằng chứng → kết luận có giới hạn → điều kiện cho phát hành.**

Ví dụ, một báo cáo không có SQL injection chỉ có giá trị trong phạm vi các đường đã được chạy, các source/sink đã được hỗ trợ và dữ liệu thu thập đủ hoàn chỉnh. Nếu test không đi qua truy vấn, agent không hoạt động hoặc báo cáo thuộc build khác, không thể dùng nó để kết luận yêu cầu đã đạt.

Sau bài học, người học có thể:

- Phân biệt IAST với SAST, DAST, SCA, kiểm thử nghiệp vụ và bảo vệ runtime.
- Chuyển yêu cầu xác thực, phân quyền, dữ liệu và logging thành kế hoạch test có quan sát.
- Đặc tả mức bao phủ, chất lượng bằng chứng và trạng thái không đủ dữ liệu.
- Kiểm soát agent, dữ liệu chẩn đoán và ảnh hưởng tới ứng dụng thử nghiệm.
- Thiết kế gate, phân loại finding, xác minh bản sửa và phục hồi môi trường test.

Các rule, trạng thái, mã yêu cầu và ngưỡng bên dưới là ví dụ thiết kế. Khả năng cụ thể phải được xác nhận đối với runtime, framework, thư viện và công cụ được dự án lựa chọn.

## 2. IAST quan sát gì và không thay thế điều gì?

### 2.1. Phân biệt các phương pháp

| Phương pháp | Nguồn quan sát chính | Giá trị trong kế hoạch bảo mật |
|---|---|---|
| SAST | Source, bytecode hoặc biểu diễn chương trình khi không chạy ứng dụng mục tiêu | Tìm mẫu lỗi và luồng đáng nghi, kể cả phần chưa được test runtime |
| DAST | Tương tác với ứng dụng đang chạy từ phía giao diện bên ngoài | Kiểm tra hành vi phản hồi và bề mặt truy cập theo phạm vi test |
| IAST | Các điểm thực thi và ngữ cảnh trong ứng dụng được instrument | Liên kết hoạt động test với vị trí code, dữ liệu hoặc thao tác nhạy cảm được hỗ trợ |
| SCA | Thành phần, phiên bản và dữ liệu liên quan dependency | Nhận diện rủi ro component trong phạm vi phân tích |
| Test bảo mật theo nghiệp vụ | Kỳ vọng về quyền, trạng thái và tác dụng phụ của hệ thống | Kiểm chứng một chủ thể được hoặc không được làm điều gì |
| RASP | Cơ chế bảo vệ trong runtime theo policy của giải pháp | Phát hiện hoặc can thiệp khi ứng dụng hoạt động, với hợp đồng vận hành riêng |

Một sản phẩm có thể kết hợp nhiều khả năng. Không suy ra mọi tính năng của một agent đều là IAST hoặc tự được phép hoạt động trong mọi môi trường.

DAST có thể chạy với tài khoản và trạng thái đăng nhập; không nên định nghĩa nó như phương pháp chỉ kiểm tra người dùng ẩn danh. SAST cũng có giới hạn riêng, không phải công cụ nào đều phân tích đầy đủ toàn bộ code hoặc framework.

Trong bài, baseline dùng IAST ở môi trường test được quản lý. Mọi khả năng tự tạo request, kiểm chứng chủ động hoặc chặn runtime của công cụ phải được khai báo riêng, không tự bật vì cùng một gói agent.

### 2.2. Bằng chứng runtime không tự đồng nghĩa đã chứng minh khai thác

Quan sát một request dẫn tới một sink có thể cung cấp ngữ cảnh hữu ích cho finding. Tuy nhiên, mức kết luận phụ thuộc rule, cách theo dõi dữ liệu, kiểm soát đã nhận diện và việc có kiểm chứng bổ sung hay không.

Không gộp các kết luận sau:

- Đường code đã chạy.
- Dữ liệu bên ngoài đã tới thao tác nhạy cảm.
- Một kiểm soát cần thiết chưa được công cụ nhận diện.
- Có bằng chứng vi phạm yêu cầu.
- Đã tái hiện được tác động bằng ca kiểm thử có kiểm soát.

Một finding cần nêu nó đang hỗ trợ kết luận nào. Không tuyên bố mọi finding IAST đều không có false positive hoặc mọi lỗi bảo mật đều được phát hiện.

### 2.3. Các giới hạn phải đi vào kế hoạch

IAST có thể thiếu quan sát khi một framework, thư viện, native call, cơ chế async hoặc kiểu dữ liệu không được hỗ trợ. Một đường không chạy cũng không tạo bằng chứng về hành vi thực thi của đường đó.

Các yêu cầu như phân quyền đối tượng, trình tự phê duyệt, hạn mức nghiệp vụ hoặc logic phục hồi thường cần assertion theo hợp đồng của ứng dụng. Agent tổng quát không tự biết tenant A không được đọc tài liệu tenant B.

Do đó, IAST bổ sung ngữ cảnh cho test và điều tra. Việc thay thế một kiểm tra khác phải có lý do và bằng chứng phù hợp, không dựa vào tên phương pháp.

## 3. Mô hình source, propagation, control và sink

### 3.1. Một luồng dữ liệu minh họa

Với rule theo dõi dữ liệu không tin cậy, có thể dùng mô hình:

```text
Source
  -> Truyền qua hàm, object, framework hoặc tác vụ
  -> Kiểm soát thích hợp với ngữ cảnh, nếu có
  -> Sink nhạy cảm
  -> Bằng chứng về luồng và kết quả quan sát
```

| Khái niệm | Ví dụ trong dịch vụ tài liệu |
|---|---|
| Source | Query parameter, JSON field, header, message hoặc dữ liệu được đọc lại từ nơi lưu |
| Propagation | Mapping DTO, nối chuỗi, gọi service, chuyển tham số hoặc queue |
| Control | Parameter binding cho giá trị SQL; kiểm tra đường dẫn theo hợp đồng; encoding đúng ngữ cảnh |
| Sink | Thực thi truy vấn, truy cập file, gọi network hoặc đưa dữ liệu vào nơi diễn giải đặc biệt |
| Observation | Điểm thực thi, vị trí code, loại dữ liệu và liên kết tới tình huống test |

Không phải mọi rule IAST đều dùng mô hình taint tracking này. Một số kiểm tra có thể quan sát cấu hình hoặc cách gọi API. Đặc tả cần nói rõ nhóm kiểm tra nào được yêu cầu.

### 3.2. Kiểm soát phải đúng ngữ cảnh

Một bước trim hoặc kiểm tra độ dài không tự làm chuỗi an toàn cho SQL. Một encoding phù hợp HTML không giải quyết lệnh shell hoặc path traversal.

Nếu công cụ cho phép khai báo sanitizer/custom rule, cần quản lý chúng như cấu hình có ảnh hưởng tới kết quả bảo mật. Đánh dấu một hàm chung là “an toàn cho mọi sink” có thể làm mất finding thật.

Quy tắc custom cần có owner, version, phạm vi, ca dương/âm và audit thay đổi. Khi thư viện hoặc framework thay đổi, phải kiểm tra lại cách công cụ nhận diện kiểm soát đó.

### 3.3. Bằng chứng cần đủ nhưng không thu dữ liệu thừa

Một finding có thể cần:

- Source category và field liên quan.
- Đường đi hoặc các điểm thực thi có ý nghĩa.
- Sink và vị trí code đã được đối chiếu với build.
- Rule ID, rule pack và phiên bản agent.
- Test/run ID cùng kết quả hành vi ứng dụng.
- Phần dữ liệu đã được lọc hoặc dấu nhận dạng thử nghiệm, khi cần.

Không cần ghi nguyên token, cookie, secret hoặc toàn bộ tài liệu để chứng minh một luồng dữ liệu. Chính hệ thống IAST có thể trở thành nơi tập trung thông tin nhạy cảm nếu thiết kế thu thập không có giới hạn.

## 4. Bắt đầu từ yêu cầu ứng dụng và phạm vi test

Xét API tài liệu đa tenant có tìm kiếm, tải nội dung, tải file lên, tạo bản xuất và worker xử lý bất đồng bộ.

Các yêu cầu bảo mật nghiệp vụ minh họa:

| ID yêu cầu | Hành vi cần kiểm chứng | Vai trò phù hợp của IAST |
|---|---|---|
| SEC-AUTH-01 | Request thiếu danh tính hợp lệ không đọc hoặc sửa tài liệu | Quan sát đường xử lý nếu hỗ trợ; assertion chính xác nhận bị từ chối và không có tác dụng phụ |
| SEC-AUTHZ-02 | Chủ thể tenant A không được truy cập tài liệu tenant B | Cần assertion theo quyền/đối tượng; IAST có thể hỗ trợ định vị code liên quan |
| SEC-DATA-03 | Dữ liệu tìm kiếm không thay đổi cấu trúc truy vấn SQL | Quan sát source, cách xây dựng truy vấn, binding và sink được hỗ trợ |
| SEC-FILE-04 | Tên file không làm truy cập ngoài vùng lưu trữ được cấp | Quan sát luồng tới file API cùng kiểm thử trạng thái filesystem |
| SEC-EGRESS-05 | Yêu cầu xuất không tạo kết nối tới đích ngoài policy | Quan sát lời gọi network được hỗ trợ và kiểm tra tại điểm kiểm soát egress |
| SEC-LOG-06 | Credential không xuất hiện trong log hoặc evidence | Cần kiểm tra đầu ra, bao gồm chính đầu ra của IAST |
| SEC-RECOVERY-07 | Retry hoặc lỗi worker không tạo quyền chia sẻ/tài liệu trái hợp đồng | Assertion nghiệp vụ và dữ liệu bền vững; không chỉ dựa finding agent |

Các ID này thuộc ví dụ, không phải ID chuẩn bên ngoài.

### 4.1. Ma trận tình huống phải có nhiều chiều

Một tình huống không chỉ là URL. Cần xác định:

- Operation: method, route hoặc loại message.
- Vai trò và trạng thái xác thực.
- Tenant, quyền sở hữu và tài nguyên.
- Dữ liệu đầu vào, kiểu nội dung và biến thể cần thiết.
- Feature flag và cấu hình có ảnh hưởng.
- Luồng thành công, bị từ chối, lỗi phụ thuộc hoặc retry.
- Thành phần đồng bộ/bất đồng bộ đi qua.
- Assertion nghiệp vụ và điểm quan sát mong đợi.

Ví dụ, “GET tài liệu đã chạy” không chứng minh đã thử thiếu session, sai role và sai tenant.

WSTG mô tả kiểm tra object reference với những người dùng/tài nguyên có quyền khác nhau để đánh giá kiểm soát truy cập. Điều đó cần dữ liệu đối chứng và kỳ vọng nghiệp vụ, không chỉ phản hồi HTTP thành công. [OWASP WSTG: Testing for IDOR](https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/05-Authorization_Testing/04-Testing_for_Insecure_Direct_Object_References/)

### 4.2. Đường bị từ chối có điểm quan sát khác đường thành công

Nếu request thiếu quyền phải bị chặn trước database, không nên yêu cầu nó chạm SQL sink để được tính là test đạt. Tiêu chí của tình huống đó là quyết định từ chối và không có truy cập/tác dụng phụ trái phép.

Ma trận phải ghi điểm quan sát nào áp dụng và điểm nào chủ đích không được tới. Nếu không có hook phù hợp cho quyết định quyền, vẫn có thể chạy assertion nghiệp vụ nhưng phải khai báo giới hạn quan sát IAST.

Không tự đánh dấu tình huống là đã được IAST xác minh chỉ vì một test HTTP bất kỳ trả đúng status.

### 4.3. Rủi ro của chính quy trình kiểm thử

| Mã rủi ro | Tình huống | Hệ quả |
|---|---|---|
| R-IAST-01 | Agent không hoạt động, thiếu hook hoặc collector mất dữ liệu | Kết quả rỗng bị hiểu nhầm là đạt |
| R-IAST-02 | Test chỉ đi luồng thuận hoặc dùng toàn quyền admin | Bỏ sót yêu cầu từ chối và ranh giới tenant |
| R-IAST-03 | Báo cáo không khớp build, config hoặc run | Bằng chứng không áp dụng cho ứng viên phát hành |
| R-IAST-04 | Rule/sanitizer bị cấu hình sai hoặc suppression quá rộng | Finding thật bị che |
| R-IAST-05 | Agent hoặc evidence làm lộ dữ liệu | Token, secret hoặc nội dung tài liệu đi vào hệ thống phụ trợ |
| R-IAST-06 | Instrumentation ảnh hưởng hành vi/tài nguyên | Test sai lệch hoặc hệ thống thử không ổn định |
| R-IAST-07 | Finding biến mất vì không chạy lại đường cũ | Đóng lỗi sai sau bản sửa |
| R-IAST-08 | Chỉ instrument API, bỏ worker hoặc service liên quan | Mất một phần chuỗi thực thi cần kiểm chứng |

## 5. Bộ yêu cầu cho việc sử dụng IAST

### 5.1. Một yêu cầu đầy đủ

**IAT-01 — Chỉ dùng một lần chạy đủ bằng chứng để xét gate**

- **Rủi ro:** R-IAST-01, R-IAST-03 và R-IAST-08.
- **Phạm vi:** các release ứng dụng mà dự án quy định IAST là bằng chứng bắt buộc.
- **Điều kiện:** trước khi hệ thống dùng kết quả IAST để cho ứng viên đi tiếp.
- **Yêu cầu:** xác minh đúng subject, test run, cấu hình, agent/rule pack, thành phần được instrument và trạng thái hoàn tất dữ liệu.
- **Phần bắt buộc:** mọi tình huống critical đã được chọn và điểm quan sát tương ứng phải có bằng chứng theo ma trận phiên bản hóa.
- **Khi thiếu:** đánh dấu không đủ dữ liệu và chưa cấp quyền phát hành qua gate này; không diễn giải là không có finding.
- **Bằng chứng:** run manifest, danh tính workload, mapping test/observation, finding và kết quả đối soát cuối run.
- **Tiêu chí chấp nhận:** tắt agent, bỏ worker thuộc phạm vi hoặc nộp báo cáo của build khác đều không được đánh giá như một lần chạy hợp lệ.

IAT-01 quy định độ tin cậy của kết quả. Nó không tự nói ứng dụng không có lỗ hổng.

### 5.2. Các yêu cầu bổ sung

| ID | Hành vi bắt buộc trong ví dụ | Bằng chứng chấp nhận chính |
|---|---|---|
| IAT-02 | Kế hoạch test liên kết từng yêu cầu bảo mật với tình huống, assertion và điểm quan sát phù hợp. | Có cả tình huống được phép/bị từ chối; không chỉ danh sách route |
| IAT-03 | Runtime, framework, library và nhóm rule cần thiết có ma trận hỗ trợ cùng kiểm tra hiệu lực. | Hook không hỗ trợ được khai báo; không báo bao phủ toàn bộ |
| IAT-04 | Agent, rule pack và cấu hình instrumentation được lấy từ nguồn được cấp, có định danh phiên bản và tính toàn vẹn. | Agent bị thay hoặc cấu hình khác baseline không được dùng như bằng chứng đã duyệt |
| IAT-05 | Mỗi observation/finding được liên kết tới đúng run, workload và subject; run song song không trộn dữ liệu. | Hai branch cùng tên ứng dụng vẫn tạo báo cáo tách biệt |
| IAT-06 | Mất event, sampling ngoài hợp đồng hoặc kết thúc chưa đối soát được thể hiện trong độ đầy đủ dữ liệu. | Collector lỗi không tạo kết quả “0 finding, PASS” |
| IAT-07 | Dữ liệu thu thập theo danh sách field và giới hạn; credential và payload bị cấm được lọc trước khi xuất. | Dấu thử trong cookie/body không xuất hiện ở log, collector hoặc export bị cấm |
| IAT-08 | Finding có bằng chứng, trạng thái triage, owner và liên kết đến yêu cầu/rủi ro. | Phân biệt nghi ngờ, tái hiện, false positive và rủi ro được chấp nhận |
| IAT-09 | Suppression và custom sanitizer có phạm vi, thẩm quyền, thời hạn/điều kiện cùng lịch sử. | Không dùng một suppression cho mọi build, sink hoặc sản phẩm ngoài phạm vi |
| IAT-10 | Bản sửa chỉ được xác nhận khi chạy lại đường liên quan, điểm quan sát hoạt động và assertion bảo mật đạt. | Finding biến mất vì test không tới sink không được coi là đã sửa |
| IAT-11 | Instrumentation có ngân sách tài nguyên và kiểm tra tương thích; ứng viên phát hành có xác minh thích hợp khi không có agent test. | Không suy từ một lần chạy instrument sang mọi hành vi của bản phân phối |
| IAT-12 | Agent, collector và kho evidence áp dụng xác thực, phân quyền và bảo vệ đường truyền. | Workload ngoài phạm vi không tự gửi evidence có quyền cho run khác |
| IAT-13 | Khi hạ tầng IAST lỗi, gate xử lý thiếu bằng chứng rõ ràng và môi trường test có quy trình dọn/khôi phục. | Không fallback bỏ kiểm tra bắt buộc; rerun không dùng nhầm dữ liệu cũ |
| IAT-14 | Ngoại lệ phải được policy cho phép, có chủ sở hữu rủi ro và scope/hiệu lực rõ. | Ngoại lệ cho một khoảng trống không biến báo cáo thành đủ dữ liệu hoặc lỗi thành đã sửa |

Các mã IAT là định danh nội bộ của bài học. Một dự án có thể dùng tên khác nhưng cần giữ được rủi ro, hành vi và bằng chứng đi cùng nhau.

## 6. Thiết kế một lần chạy có thể đối chiếu

### 6.1. Luồng thực hiện

```text
Chốt artifact, cấu hình và test plan
    -> Cấp môi trường/dữ liệu test được quản lý
    -> Khởi động các workload cần instrument
    -> Xác minh agent, rule và đường xuất evidence
    -> Chạy test theo ma trận, giữ assertion nghiệp vụ
    -> Chờ tác vụ async và đối soát dữ liệu cuối run
    -> Đánh giá coverage, findings và tính toàn vẹn của evidence
    -> Gate cho đúng ứng viên
    -> Dọn hoặc khôi phục môi trường, giữ evidence theo policy
```

Mỗi bước cần một kết quả riêng. “Agent đã kết nối” chỉ chứng minh một điều kiện khởi đầu; chưa chứng minh đúng hook, mọi workload hoặc toàn bộ event đã được thu.

### 6.2. Định danh subject và cấu hình thử nghiệm

Run manifest nên có:

- Artifact digest và build/source revision dùng để đối chiếu vị trí code.
- Runtime, dependency hoặc image liên quan trong phạm vi.
- Agent/rule pack và cấu hình instrumentation.
- Feature flag, cấu hình bảo mật và policy áp dụng.
- Test suite revision, dữ liệu fixture và role/tenant được sử dụng.
- Workload/instance bắt buộc, run ID và cửa sổ thời gian.
- Các khác biệt được chấp nhận so với môi trường đích.

Dùng agent ngoài file ứng dụng có thể giữ nguyên byte của JAR, nhưng vẫn làm thay đổi môi trường thực thi. Nếu công cụ sửa bytecode hoặc tạo artifact instrumented riêng, phải giữ mapping biến đổi và xác định chính xác bản nào đã được thử.

Không dùng kết quả của một build “gần giống” để xác nhận ứng viên mới mà thiếu đánh giá phần thay đổi. Cũng không khẳng định mọi phép đo hiệu năng với agent áp dụng nguyên vẹn cho bản không instrument.

### 6.3. Tương quan qua nhiều service và worker

Nếu test tạo job xuất tài liệu, request HTTP thành công có thể chỉ có nghĩa job được đưa vào queue. Cần kiểm tra worker xử lý, kết quả cuối và tác dụng phụ theo hợp đồng.

Run ID hoặc trace context giúp tương quan, nhưng không tự là quyền ghi evidence. Collector cần xác thực workload và giới hạn quyền gắn dữ liệu với run tương ứng.

Không tin một header do caller tự đặt để quyết định dữ liệu thuộc một release được chấp nhận. Với môi trường dùng chung, cần cơ chế tách dữ liệu các run song song và xử lý event đến muộn.

Sampling, mất context qua queue hoặc thư viện không được hỗ trợ phải được phản ánh trong khoảng trống. Không nối các đoạn không có bằng chứng rồi coi như đã theo dõi end-to-end.

## 7. Ví dụ Java: quan sát SQL không thay cho assertion phân quyền

### 7.1. Đường dữ liệu có vấn đề

Đoạn trích sau minh họa lỗi trong lớp truy cập dữ liệu. `authorizedTenantId` được giả định đã lấy từ ngữ cảnh quyền được xác nhận; `title` là đầu vào của ca test.

```java
String sql =
    "SELECT id FROM documents WHERE tenant_id = ? AND title = '"
    + title + "'";

try (PreparedStatement query = connection.prepareStatement(sql)) {
    query.setString(1, authorizedTenantId);
    try (ResultSet rows = query.executeQuery()) {
        // Đọc kết quả theo hợp đồng của hàm.
    }
}
```

Dù có PreparedStatement, phần title vẫn được nối vào cấu trúc SQL trước khi chuẩn bị truy vấn. Việc bind một tham số khác không bảo vệ phần đã được nối.

Một rule và hook hỗ trợ luồng này có thể liên kết source title với thao tác SQL. Finding phải nêu rõ quan sát, vị trí và giới hạn; có thể cần kiểm chứng thêm để xác nhận tác động cụ thể.

### 7.2. Bản sửa tách cấu trúc và dữ liệu

```java
String sql =
    "SELECT id FROM documents WHERE tenant_id = ? AND title = ?";

try (PreparedStatement query = connection.prepareStatement(sql)) {
    query.setString(1, authorizedTenantId);
    query.setString(2, title);
    try (ResultSet rows = query.executeQuery()) {
        // Đọc kết quả theo hợp đồng của hàm.
    }
}
```

Parameterized query tách giá trị dữ liệu khỏi cú pháp truy vấn. Các thành phần cấu trúc như tên cột hoặc hướng sắp xếp cần thiết kế riêng, không coi placeholder dữ liệu là cơ chế thay mọi thành phần SQL. [OWASP: SQL Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)

Các đoạn trên chỉ minh họa việc xây dựng truy vấn, không phải implementation đầy đủ cho xác thực, phân quyền và API.

### 7.3. Tiêu chí xác minh bản sửa

Cần có đồng thời:

1. Bản sửa được nhận diện bằng subject/build rõ.
2. Ca test thực sự đưa title tới đường truy vấn liên quan.
3. Agent và hook SQL áp dụng có bằng chứng hoạt động.
4. Không còn vi phạm theo rule được lựa chọn trong luồng đã chạy.
5. Assertion dữ liệu xác nhận đầu vào được xử lý như giá trị, kết quả đúng hợp đồng.
6. Ca sai tenant vẫn bị từ chối và không trả tài liệu ngoài quyền.

Dữ liệu thử có thể gồm một tiêu đề hợp lệ chứa dấu nháy đơn để phát hiện việc xử lý sai giá trị. Không cần dùng dữ liệu thật hoặc thao tác phá hủy để kiểm tra nguyên tắc tách cú pháp/dữ liệu.

Nếu finding cũ biến mất vì route đổi, test không đăng nhập được hoặc truy vấn được cache nên không chạy, chưa đủ cơ sở đóng lỗi.

## 8. Đo mức bao phủ và hiệu lực quan sát

### 8.1. Ít nhất ba loại bao phủ

| Loại | Câu hỏi | Giới hạn |
|---|---|---|
| Bao phủ tình huống | Những tổ hợp operation/role/tenant/state đã được chạy và assertion có kết quả? | Không chứng minh các điểm nội bộ đều được instrument |
| Bao phủ instrumentation | Những runtime, framework, source/sink hoặc nhóm hook bắt buộc được hỗ trợ và xác nhận hoạt động? | Có hook không đồng nghĩa test đã đi qua nó |
| Bao phủ observation theo kế hoạch | Những điểm quan sát áp dụng đã có evidence cho đúng tình huống? | Không chứng minh mọi đường chưa biết đều được kiểm tra |

Code coverage có thể giúp tìm khoảng trống nhưng không thay ba câu hỏi trên. Một dòng đã chạy một lần với admin không chứng minh hành vi đúng với tài khoản thiếu quyền.

Nếu tổng bề mặt chưa được kiểm kê đủ, tỷ lệ chỉ áp dụng cho phạm vi đã công bố. Không mô tả nó như tỷ lệ an toàn của toàn hệ thống.

### 8.2. Ví dụ số đo có mẫu số

Một test plan có 20 tình huống bắt buộc, trong đó 6 được phân loại critical. Có 18/20 tình huống thực hiện đủ assertion, 5/6 critical có bằng chứng quan sát cần thiết.

Ma trận hook có 8 nhóm bắt buộc; 7/8 nhóm được xác nhận hỗ trợ, nhóm cho thư viện worker còn thiếu.

Kết quả phải giữ riêng:

- Bao phủ thực hiện tình huống: 18/20.
- Bao phủ observation critical theo kế hoạch: 5/6.
- Nhóm hook được xác nhận: 7/8.
- Hai tình huống chưa hoàn tất và một nhóm hook thiếu có owner/lý do.

Không cộng các tỷ lệ thành một điểm duy nhất để che việc critical chưa được kiểm chứng. Trong baseline minh họa, thiếu một tình huống critical bắt buộc khiến bằng chứng cho gate chưa đủ.

### 8.3. Dùng kiểm tra đối chứng cho đường quan sát

Có thể dùng fixture kiểm chuẩn tách biệt để xác nhận một rule quan trọng phát hiện được mẫu lỗi đã biết, cùng mẫu an toàn tương ứng.

Fixture có chủ đích chứa lỗi phải:

- Tách khỏi artifact và đường phục vụ của sản phẩm phát hành.
- Chỉ hoạt động trong môi trường test được quản lý.
- Có dữ liệu và dependency giới hạn.
- Có run/subject riêng, không trộn finding vào ứng viên.
- Được kiểm tra đầu ra từ agent tới collector và báo cáo.

Một fixture chỉ chứng minh những khả năng mà nó kiểm tra. Nó không chứng minh mọi rule, framework hoặc toàn ứng dụng đều được bao phủ.

Nếu công cụ không cung cấp đủ tín hiệu để xác định mất event hoặc hook cần thiết, phải ghi giới hạn và chọn bằng chứng bổ sung phù hợp. Không tự tạo trạng thái complete từ việc giao diện không báo lỗi.

## 9. Hợp đồng evidence và gate phát hành

### 9.1. Ví dụ một lần chạy chưa đủ

Schema sau được tự định nghĩa để minh họa. Digest lặp là placeholder, không phải nội dung đã được đo.

```yaml
runId: "iast-documents-208"
subject:
  buildId: "build-208"
  artifactSha256: "1111111111111111111111111111111111111111111111111111111111111111"
testPlanRevision: "security-tests-042"

instrumentation:
  profileRevision: "iast-profile-17"
  agentArtifactRef: "approved-agent-digest-reference"
  rulePackRevision: "rules-09"
  requiredWorkloads: [documents-api, export-worker]
  observedWorkloads: [documents-api]

execution:
  functionalAssertions: PASSED
  criticalScenariosPlanned: 6
  criticalScenariosExecuted: 6
  criticalScenariosWithRequiredObservation: 5

collection:
  finalizationStatus: INCOMPLETE
  reasonCodes:
    - WORKER_INSTRUMENTATION_NOT_OBSERVED
  eventLossStatus: UNKNOWN

findings:
  reportedCount: 0
  triageSnapshotRef: "triage-208-r1"

gate:
  evidenceDecision: INSUFFICIENT
  releaseDecision: HOLD
```

Trong ví dụ, test nghiệp vụ có thể đã xác nhận worker hoàn thành tác vụ qua trạng thái bền vững, nhưng observation IAST bắt buộc của worker chưa có. Vì vậy 0 finding không tạo kết quả đạt.

Các trường phiên bản và reference phải phân giải tới dữ liệu được kiểm soát. Một string như approved-agent không tự chứng minh tính toàn vẹn của agent.

### 9.2. Tách độ đầy đủ bằng chứng khỏi kết quả bảo mật

| Evidence | Assertion/finding theo policy | Kết quả gate minh họa |
|---|---|---|
| Đủ cho phạm vi bắt buộc | Assertion đạt; không có finding thuộc lớp chặn chưa được xử lý hợp lệ | Có thể đi tiếp qua gate này |
| Đủ | Assertion vi phạm hoặc finding thuộc lớp chặn còn hiệu lực | Chặn ứng viên theo policy |
| Chưa đủ | Không thấy finding | Giữ lại vì thiếu bằng chứng |
| Chưa đủ | Đã có finding quan trọng | Giữ finding để xử lý; đồng thời không được bỏ trạng thái thiếu dữ liệu |

Không cần đợi run hoàn tất mới giữ bằng chứng lỗi đã thấy. Nhưng không dùng một finding đã ghi để làm như phần còn lại của run đã đủ.

Gate cần xét cả finding đang tồn tại theo policy, không chỉ finding mới. Việc đưa lỗi cũ vào baseline không tự tạo chấp nhận rủi ro.

### 9.3. Chỉ cho phép dùng kết quả đúng phạm vi

Một mã giả:

```text
evaluateIastEvidence(candidate, run):
    requireAuthorizedEvidenceProducer(run)
    requireSubjectAndConfigurationMatch(candidate, run)
    requireExpectedPlanAndInstrumentationProfile(run)
    requireMandatoryWorkloadsAndObservations(run)
    requireCollectionFinalizedWithoutUnacceptedGaps(run)
    requireRequiredBehaviorAssertionsPassed(run)
    requireNoUnresolvedBlockingFindings(run, currentPolicy)
    requireApplicableExceptionsValid(run, currentPolicy)
    persistDecision(candidate.subject, run.id, currentPolicy.revision)
    return permitBoundTo(candidate.subject, run.id)
```

Không tin một field PASS do test client tự gửi nếu chưa kiểm tra nguồn và dữ liệu hỗ trợ. Kết quả gate phải liên kết tới đúng subject và revision policy.

Một ngoại lệ hợp lệ có thể cho phép phát hành theo quyết định riêng, nhưng không được sửa báo cáo gốc thành “đã kiểm tra đủ” hoặc “lỗi đã được sửa”.

## 10. Triage, bảo vệ dữ liệu và ảnh hưởng vận hành

### 10.1. Vòng đời finding

Một finding có thể đi qua các trạng thái nội bộ như mới nhận, đang xác nhận, đã tái hiện, false positive có bằng chứng, rủi ro được chấp nhận, chờ bản sửa và đã xác minh bản sửa.

Hồ sơ cần giữ:

- Rule, vị trí, source/sink hoặc observation liên quan.
- Subject/run/config và bằng chứng đã lọc.
- Yêu cầu bảo mật bị nghi vi phạm, tác động và điều kiện xảy ra.
- Kết luận, người có thẩm quyền và lý do.
- Bản sửa, ca regression và kết quả retest.
- Suppression/ngoại lệ cùng phạm vi và điều kiện hết hiệu lực.

“Không tái hiện được” chưa tự đồng nghĩa false positive. Có thể là thiếu dữ liệu, cấu hình khác hoặc đường không được chạy.

Dedup giúp quản lý nhiều bằng chứng của cùng vấn đề, nhưng không được làm mất ảnh hưởng theo branch, service hoặc tenant. Đóng một finding ở build mới không tự sửa trạng thái của artifact cũ vẫn đang được sử dụng.

### 10.2. Chính agent là một thành phần có quyền trong runtime

Agent có thể quan sát code, request, cấu hình hoặc thao tác nhạy cảm. Cần quản lý nguồn artifact, quyền nạp, cập nhật, credential, egress và endpoint quản lý của nó.

Baseline của bài:

- Môi trường test dùng dữ liệu tổng hợp hoặc dữ liệu đã được xử lý theo policy.
- Không cấp secret production chỉ để test dễ chạy.
- Không mở console/debug endpoint ngoài hợp đồng.
- Credential agent có phạm vi ứng dụng/run cần thiết, không có quyền sửa quyết định gate.
- Evidence được lọc trước khi truyền hoặc lưu, có phân quyền đọc và export.
- Tệp tạm, hàng đợi cục bộ và bản sao báo cáo cũng chịu chính sách lưu/xóa.

Giao diện che token không chứng minh token chưa vào kho. Cần kiểm thử tại đầu ra thực tế và các đường fallback.

### 10.3. Ngân sách và tính đại diện

Dự án có thể quy định ngân sách overhead theo một workload đối chứng: độ trễ, CPU, memory, dung lượng evidence và thời gian test. Không lấy một tỷ lệ quảng bá làm yêu cầu đã được chứng minh.

Nếu agent phải sampling hoặc tắt rule để đáp ứng ngân sách, khoảng thay đổi đó phải đi vào phạm vi bằng chứng. Không âm thầm giảm quan sát trong khi gate vẫn đòi bao phủ cũ.

Hàng đợi evidence cần có cận và trạng thái khi đầy. Mất dữ liệu hoặc ngừng quan sát phải làm run bị đánh dấu phù hợp; không ghi đè bằng “0 issue”.

Nên có phép kiểm tra phù hợp trên artifact đích khi không gắn agent test để phát hiện khác biệt liên quan đến khởi động, chức năng hoặc tích hợp. Nó bổ sung bằng chứng, không biến một smoke test ngắn thành bảo đảm tương đương hoàn toàn.

### 10.4. Mục tiêu đo được và phục hồi

Ví dụ policy có thể yêu cầu:

- Mọi tình huống critical trong test plan phải có assertion và observation áp dụng trước gate.
- Trong tối đa 120 giây sau khi mọi tác vụ thuộc run kết thúc, hệ thống phải xác nhận finalization hoặc đánh dấu chưa hoàn tất.
- Run có mất event vượt mức policy chấp nhận phải giữ trạng thái thiếu bằng chứng.
- Evidence thô không chứa credential; evidence được phép lưu có thời hạn, owner và quyền truy cập.
- Finding thuộc lớp khẩn cấp được phân loại ban đầu trong thời hạn do dự án định nghĩa.

Mốc 120 giây là ví dụ về thời gian chờ, không bảo đảm mọi backend thực hiện được. Hết thời gian mà chưa đủ dữ liệu phải phản ánh đúng trạng thái, không tự hoàn tất.

Khi collector hoặc agent lỗi, khôi phục môi trường theo cấu hình đã chốt, dùng run ID mới nếu thực hiện lại và giữ liên kết tới run thất bại. Không ghép các phần của nhiều run khác subject rồi báo một lần chạy hoàn chỉnh.

Dọn fixture, queue, file xuất và tài khoản test theo phạm vi đã tạo. Bằng chứng cần lưu phải tách khỏi tài nguyên tạm cần xóa.

## 11. Kế hoạch kiểm chứng việc triển khai IAST

Các ca sau kiểm tra cả ứng dụng lẫn độ tin cậy của hệ thống thu thập. Chúng không phải yêu cầu chạy công cụ trên một hệ thống thật trong bài học.

| Ca | Thiết lập hoặc tác động | Kết quả chấp nhận |
|---|---|---|
| T01 | Run hợp lệ, đúng subject, đủ workload và tình huống bắt buộc | Evidence đủ và gate đánh giá theo finding/assertion thật |
| T02 | Tắt agent nhưng test chức năng vẫn thành công | Không báo IAST đạt; trạng thái thiếu observation |
| T03 | Agent kết nối nhưng hook SQL bắt buộc không hoạt động | Phát hiện giới hạn qua đối chứng; không tính nhóm đó đã bao phủ |
| T04 | Bỏ instrument worker trong luồng xuất tài liệu | Không báo end-to-end đầy đủ |
| T05 | Dùng báo cáo build trước hoặc khác config bắt buộc | Không áp dụng cho ứng viên mới |
| T06 | Hai run song song có cùng tên ứng dụng | Không trộn observation, finding hoặc quyết định |
| T07 | Collector mất kết nối hoặc hàng đợi evidence đầy | Ghi trạng thái mất/chưa đủ dữ liệu; không biến thành 0 finding đạt |
| T08 | Test chỉ dùng admin nhưng kế hoạch yêu cầu user và sai tenant | Không đạt bao phủ tình huống |
| T09 | Request sai quyền bị chặn trước SQL | Assertion từ chối đạt; không đòi đi tới sink không được phép |
| T10 | Đường nối dữ liệu vào SQL được chạy với hook hỗ trợ | Có bằng chứng theo rule và triage phù hợp; không chỉ nhìn status HTTP |
| T11 | Sửa sang binding nhưng retest không tới truy vấn | Chưa đóng lỗi vì thiếu evidence đường sửa |
| T12 | Bản sửa đi đúng đường, hook hoạt động và dữ liệu được xử lý đúng | Có thể xác nhận bản sửa trong phạm vi đã kiểm chứng |
| T13 | Suppression/custom sanitizer bị mở rộng trái quyền | Không thay quy tắc có hiệu lực; giữ audit |
| T14 | Credential thử có dấu nhận dạng đi qua cookie, header, body và lỗi | Không xuất hiện ở đầu ra bị cấm, kể cả evidence IAST |
| T15 | Nguồn không được cấp gửi field PASS cho run khác | Không tạo quyết định có thẩm quyền |
| T16 | Instrumentation làm vượt ngân sách hoặc tắt rule ngoài hợp đồng | Run phản ánh lỗi/giới hạn, không giữ tuyên bố bao phủ cũ |
| T17 | Ngoại lệ hết hạn hoặc khác subject/scope | Không được gate áp dụng |
| T18 | Run kết thúc nhưng event tới muộn hoặc thiếu finalization | Chưa coi dữ liệu hoàn tất; xử lý theo mốc chờ và hợp đồng đối soát |
| T19 | Agent có khả năng chặn nhưng baseline chỉ cho quan sát | Không tự bật mode can thiệp làm thay đổi ý nghĩa phép thử |
| T20 | Rerun sau khôi phục và dọn môi trường | Không dùng nhầm event cũ; giữ lịch sử và xóa tài nguyên tạm đúng scope |

### 11.1. Ví dụ Given–When–Then

```gherkin
Given bản sửa SQL được nhận diện bằng build mới
And finding cũ gắn với luồng tìm kiếm tài liệu
And retest chỉ gọi trang đăng nhập nhưng không chạy tìm kiếm
When hệ thống nhận báo cáo không có finding SQL
Then không đổi trạng thái lỗi thành đã xác minh sửa
And evidence chỉ ra tình huống tìm kiếm chưa có observation bắt buộc
And gate giữ ứng viên nếu luồng đó là điều kiện bắt buộc
And lịch sử finding và lần retest vẫn được giữ
```

Ca dương cần chạy lại đúng luồng với hook hoạt động, assertion dữ liệu đạt và finding được xử lý theo policy. Hệ thống phải hỗ trợ cả xác nhận sửa thành công lẫn phát hiện retest không đủ.

## 12. Bài tập: sửa yêu cầu “chạy IAST và không có lỗi nghiêm trọng”

Một nhóm mô tả điều kiện phát hành:

> Chạy test API có gắn agent. Nếu dashboard không có lỗi nghiêm trọng thì cho release. Khi agent lỗi, dùng báo cáo gần nhất.

Ứng dụng có API đa tenant và worker xuất file. Test hiện chỉ dùng tài khoản quản trị; collector dùng chung tên ứng dụng giữa nhiều branch.

Hãy viết lại đặc tả gồm:

1. Subject, môi trường, test plan, agent/rule pack và các workload cần instrument.
2. Ma trận quyền/tenant cho tìm kiếm, đọc tài liệu và xuất file.
3. Observation nào áp dụng cho mỗi đường, kể cả đường phải bị từ chối trước sink.
4. Cách xác nhận agent/hook và độ hoàn tất dữ liệu.
5. Kết quả gate khi 0 finding nhưng thiếu worker hoặc báo cáo không khớp build.
6. Redaction, quyền evidence, ngân sách và phục hồi run lỗi.
7. Triage, suppression, ngoại lệ và điều kiện đóng finding sau bản sửa.

Một chuỗi truy vết mẫu:

| Mắt xích | Nội dung |
|---|---|
| Rủi ro ứng dụng | Đầu vào tìm kiếm làm thay đổi cấu trúc SQL |
| Yêu cầu ứng dụng | SEC-DATA-03: dữ liệu được bind theo hợp đồng |
| Yêu cầu bằng chứng | IAT-01, IAT-03, IAT-05 và IAT-10 |
| Kiến trúc | Test harness, agent/hook SQL, collector và gate |
| Kiểm thử | T03, T10, T11 và T12 |
| Bằng chứng | Subject, run/config, source/sink đã lọc và assertion dữ liệu |

Khi có finding, cần xử lý nguyên nhân và bổ sung regression theo luồng thực tế. Cách tích hợp bằng chứng với quá trình phát triển và ngăn tái diễn phù hợp mục tiêu chung của SSDF về giảm lỗ hổng, hạn chế tác động và xử lý nguyên nhân gốc. [NIST SP 800-218: SSDF 1.1](https://csrc.nist.gov/pubs/sp/800/218/final)

Sản phẩm cần đạt là một hợp đồng về bằng chứng: đã chạy tình huống nào, quan sát được điều gì, phần nào chưa đủ và vì sao kết quả đó cho phép hoặc chưa cho phép ứng viên đi tiếp trong vòng đời phát triển.
