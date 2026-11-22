# Đọc cảnh báo tự động và lập luận mức độ liên quan

Một pipeline CI báo 47 cảnh báo sau khi nhóm nâng phiên bản công cụ phân tích mã. Trong đó có cảnh báo về độ phức tạp của một phương thức, một dependency có CVE, một nhánh có thể dereference giá trị null, một quy tắc đặt tên và một cảnh báo SQL injection. Nhóm không thể sửa tất cả ngay trong một ngày. Nếu chỉ nhìn màu đỏ hoặc mức severity do công cụ gán, họ có thể dành thời gian cho những cảnh báo ít tác động trong khi bỏ sót một đường chạy có rủi ro bảo mật thật. Nếu bỏ qua hàng loạt vì “tool thường báo sai”, lỗi quan trọng cũng có thể đi vào production.

Cảnh báo tự động là **tín hiệu cần điều tra**, không phải phán quyết cuối cùng về chất lượng hay rủi ro. Công cụ phân tích dựa trên quy tắc, mô hình và dữ liệu mà nó có thể quan sát. Nó có thể phát hiện một mẫu code đáng ngờ nhưng không biết đầy đủ nghiệp vụ, cấu hình runtime, khả năng truy cập của người dùng hoặc biện pháp bảo vệ ở các lớp khác.

Bài học **“Đọc cảnh báo tự động và lập luận mức độ liên quan”** thuộc chương **Thực hành** của module `CODE_QUALITY_FUNDAMENTALS`. Mục tiêu của module là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Đọc cảnh báo tốt giúp nhóm chuyển tín hiệu kỹ thuật thành quyết định có căn cứ: sửa ngay, tạo công việc, chấp nhận rủi ro có thời hạn, loại trừ có bằng chứng hoặc yêu cầu thêm thông tin.

Sau bài học, bạn có thể:

- Phân biệt cảnh báo của công cụ với defect đã được xác nhận.
- Đọc rule, vị trí, dữ liệu đầu vào và giới hạn phát hiện của công cụ.
- Đánh giá một finding theo khả năng xảy ra, khả năng tiếp cận, tác động và bối cảnh vận hành.
- Phân biệt false positive, finding không áp dụng, duplicate, accepted risk và vấn đề đã được khắc phục.
- Đưa ra lập luận có bằng chứng thay vì chỉ nói “cảnh báo này không liên quan”.
- Chọn mức ưu tiên dựa trên rủi ro thực tế, không chỉ dựa vào severity mặc định.
- Dùng suppression hoặc exception có phạm vi hẹp, chủ sở hữu và thời hạn xem lại.
- Ghi nhận quyết định triage để reviewer và người bảo trì sau này hiểu được.

## 1. Cảnh báo tự động đang nói điều gì?

Một công cụ có thể phát hiện:

- Một biến có thể được dùng trước khi kiểm tra null.
- Một chuỗi được nối trực tiếp vào câu SQL.
- Một dependency có phiên bản nằm trong advisory bảo mật.
- Một phương thức có nhiều nhánh hoặc quá nhiều tham số.
- Một nhánh điều kiện không thể chạy theo phân tích tĩnh.
- Một API có thể làm lộ dữ liệu nhạy cảm trong log.
- Một đoạn code không tuân thủ formatter hoặc coding convention.
- Một test chưa bao phủ nhánh quan trọng.

Mỗi finding thường gồm một số thông tin:

| Thành phần | Ý nghĩa |
| --- | --- |
| Rule ID | Mã quy tắc để tra cứu cách phát hiện và giới hạn |
| Message | Mô tả điều công cụ nghi ngờ |
| Location | File, dòng, symbol hoặc dependency liên quan |
| Severity | Mức độ nghiêm trọng theo mô hình của công cụ |
| Confidence | Mức tin cậy của bộ phát hiện, nếu công cụ cung cấp |
| Evidence/trace | Đường dữ liệu, call path hoặc đoạn code làm cơ sở |
| Remediation | Gợi ý sửa hoặc liên kết tài liệu |
| Suppression state | Finding có bị loại trừ hoặc chấp nhận ngoại lệ không |

Không phải công cụ nào cũng cung cấp đủ các trường trên. Nếu thiếu evidence hoặc confidence, người triage phải tìm thêm bằng chứng từ source, test, cấu hình hoặc runtime.

### Finding chưa đồng nghĩa với lỗi đã xảy ra

Ví dụ cảnh báo “possible null dereference” có thể có nghĩa:

1. Công cụ thấy một đường điều khiển mà biến có thể null.
2. Đường đó có thực sự đi tới lệnh dereference hay không cần xem thêm.
3. Dữ liệu đầu vào có thể tạo trạng thái null hay không cần xem hợp đồng và validation.
4. Nếu xảy ra, hậu quả có thể là exception, lỗi request hoặc ảnh hưởng rộng hơn.

Chỉ sau khi xác minh các điểm này, nhóm mới biết finding là defect có thể tái hiện, rủi ro tiềm ẩn, cảnh báo không áp dụng hay false positive.

## 2. Phân biệt các kết luận khi triage

Không nên gom mọi quyết định thành hai trạng thái “sửa” và “bỏ qua”. Có nhiều kết luận khác nhau:

| Kết luận | Ý nghĩa | Hành động |
| --- | --- | --- |
| **Confirmed issue** | Có lỗi hoặc rủi ro thực trong bối cảnh hiện tại | Sửa, giảm thiểu hoặc lập kế hoạch xử lý |
| **True positive, low relevance** | Mẫu code được phát hiện là có thật nhưng ít tác động hoặc không nằm trong đường chạy đang xét | Ghi lý do và quyết định ưu tiên |
| **False positive** | Điều kiện mà rule giả định không đúng với code thực tế | Ghi bằng chứng, loại trừ theo quy trình |
| **Not applicable** | Rule đúng nói chung nhưng không áp dụng cho loại file, môi trường hoặc cách dùng cụ thể | Ghi phạm vi và lý do |
| **Duplicate** | Cùng một nguyên nhân đã được báo ở finding khác | Liên kết finding gốc, tránh xử lý trùng |
| **Already fixed** | Source hiện tại đã được sửa, kết quả scan hoặc branch đang xem đã cũ | Chạy lại scan đúng commit và xác nhận |
| **Accepted risk** | Rủi ro có thật nhưng chủ sở hữu quyết định tạm chấp nhận | Ghi người chấp nhận, biện pháp giảm thiểu và ngày xem lại |
| **Needs investigation** | Bằng chứng hiện tại chưa đủ kết luận | Giao người điều tra và câu hỏi cần trả lời |

Một finding true positive có thể có mức ưu tiên thấp. Ngược lại, một cảnh báo có confidence chưa cao vẫn có thể cần điều tra ngay nếu hậu quả tiềm tàng rất nghiêm trọng. **Độ đúng của phát hiện, mức liên quan và mức ưu tiên là ba câu hỏi khác nhau.**

## 3. Đọc rule trước khi kết luận

Khi nhận một finding, đừng chỉ đọc message. Hãy tìm tài liệu của rule và trả lời:

- Rule đang phát hiện mẫu code hoặc điều kiện nào?
- Nó dùng phân tích cú pháp, type, data flow, taint analysis hay dependency metadata?
- Nó có yêu cầu cấu hình đặc biệt để hiểu framework không?
- Nó có giới hạn liên quan tới reflection, generated code hoặc dynamic dispatch không?
- Có known false positive hoặc cách cấu hình loại trừ được khuyến nghị không?
- Severity do rule đặt cố định hay được tính từ context?
- Phiên bản rule/tool nào tạo ra finding?

Ví dụ, một rule phát hiện SQL injection có thể tìm việc nối chuỗi vào câu SQL. Nếu công cụ không theo được một wrapper nội bộ để nhận ra tham số đã được bind, nó có thể cảnh báo dù đường thực thi thực tế dùng parameterized query. Tuy nhiên, chỉ nói “ứng dụng có repository layer” không đủ chứng minh an toàn; cần lần theo giá trị tới câu SQL cuối cùng.

### Rule ID quan trọng hơn câu mô tả ngắn

Message thường được rút gọn để hiển thị trên dashboard. Rule ID giúp tra cứu định nghĩa chính xác, phiên bản và hướng xử lý. Khi ghi nhận triage, giữ rule ID cùng vị trí và phiên bản scanner để người khác có thể kiểm tra lại sau khi rule thay đổi.

## 4. Đánh giá mức liên quan theo bối cảnh

Một finding cần được xem trong bối cảnh của đường chạy, dữ liệu và hệ thống. Có thể dùng các câu hỏi sau:

### Khả năng tiếp cận

- Code có được gọi trong production không?
- Entry point nào dẫn tới nó?
- Có feature flag hoặc cấu hình khiến nhánh bị tắt không?
- Người dùng hoặc hệ thống ngoài có thể kiểm soát dữ liệu đầu vào không?
- Có quyền hoặc điều kiện trước đó giới hạn người gọi không?

### Khả năng xảy ra

- Điều kiện gây cảnh báo có thể xuất hiện với dữ liệu hợp lệ không?
- Validation có thực sự bảo đảm điều kiện đó không?
- Có race condition hoặc trạng thái bất đồng bộ không?
- Đường code có thể chạy trong cấu hình triển khai hiện tại không?

### Tác động

- Có thể gây crash, sai dữ liệu, mất dữ liệu hoặc giao dịch trùng không?
- Có thể lộ thông tin, vượt quyền hoặc làm gián đoạn dịch vụ không?
- Chỉ ảnh hưởng một request hay lan sang nhiều tenant/service?
- Có thể phát hiện và phục hồi nhanh không?

### Biện pháp bảo vệ hiện có

- Có validation ở ranh giới tin cậy không?
- Có parameterized query, encoding hoặc authorization enforcement ở lớp khác không?
- Có transaction, idempotency hoặc constraint bảo vệ không?
- Có rate limit, timeout, monitoring hoặc rollback không?
- Biện pháp đó được kiểm tra bằng test hay chỉ được giả định?

Không phải mọi câu hỏi đều cần câu trả lời dài. Với một cảnh báo format, chỉ cần xác định quy ước dự án. Với cảnh báo SQL injection hoặc authorization, cần truy dấu dữ liệu và quyền đầy đủ hơn.

## 5. Severity của công cụ không phải mức ưu tiên của nhóm

Công cụ thường gán severity như Blocker, Critical, High, Medium, Low hoặc một thang riêng. Severity giúp phân loại ban đầu nhưng không tự phản ánh toàn bộ rủi ro trong hệ thống cụ thể.

Ví dụ:

- Một cảnh báo High về secret hard-coded trong mã test chỉ dùng giá trị giả có thể không có cùng tác động như secret production thật.
- Một cảnh báo Medium về thiếu kiểm tra quyền ở endpoint quản trị có thể ảnh hưởng dữ liệu nhạy cảm và cần xử lý gấp.
- Một cảnh báo Low về complexity ở đoạn code ít thay đổi có thể được xếp sau lỗi dữ liệu ở đường thanh toán.
- Một CVE Critical trong dependency không được nạp hoặc không nằm trên đường sử dụng vẫn cần xác minh reachability và điều kiện triển khai; không nên tự động bỏ qua chỉ vì chưa thấy call site trực tiếp.

Ưu tiên nên cân nhắc ít nhất:

1. **Severity kỹ thuật:** mức hậu quả theo rule hoặc advisory.
2. **Exposure:** khả năng người dùng, dữ liệu hoặc đường chạy tiếp cận.
3. **Impact:** phạm vi và mức thiệt hại nếu xảy ra.
4. **Likelihood:** khả năng điều kiện kích hoạt xuất hiện.
5. **Compensating controls:** biện pháp giảm rủi ro đã được xác minh.
6. **Urgency:** thời điểm cần xử lý do exploit đang hoạt động, release, audit hoặc thay đổi sắp tới.

Có thể dùng ma trận định tính:

| Mức ưu tiên | Dấu hiệu | Hành động thường phù hợp |
| --- | --- | --- |
| **P0 — Khẩn cấp** | Đường khai thác hoặc lỗi nghiêm trọng đang hoạt động, tác động lớn và exposure cao | Kích hoạt quy trình incident/security, giảm thiểu ngay |
| **P1 — Cao** | Rủi ro nghiêm trọng, đường chạy có thể tiếp cận, chưa có kiểm soát đủ mạnh | Ưu tiên sửa trước thay đổi ít rủi ro |
| **P2 — Bình thường** | Có vấn đề thực nhưng exposure/tác động giới hạn hoặc có workaround đã xác minh | Lên kế hoạch trong chu kỳ phù hợp |
| **P3 — Thấp** | Chủ yếu ảnh hưởng maintainability hoặc phạm vi rất hẹp | Gom theo khu vực khi có thay đổi liên quan |
| **Triage thêm** | Bằng chứng chưa đủ, hậu quả có thể cao | Đặt thời hạn điều tra ngắn và người sở hữu |

Đây là ví dụ cách nhóm tổ chức ưu tiên, không phải chuẩn severity phổ quát. Nhóm cần định nghĩa P0–P3 theo quy trình của mình.

## 6. Ví dụ 1: cảnh báo possible null dereference

Giả sử công cụ báo tại dòng gọi `customer.email().toLowerCase()`:

```java
String normalizeEmail(Customer customer) {
    return customer.email().toLowerCase();
}
```

Finding có thể liên quan đến hai giá trị:

- `customer` có thể null.
- `customer.email()` có thể trả null.

Không nên trả lời “không thể null vì database có NOT NULL” nếu hàm cũng được gọi từ API, test, import file hoặc một object tạo thủ công. Constraint database chỉ bảo vệ dữ liệu được ghi qua đường đó; nó không tự bảo vệ mọi object trong JVM.

### Bằng chứng cần kiểm tra

- Tất cả call site của `normalizeEmail`.
- Constructor/factory tạo `Customer`.
- Validation ở API hoặc mapping layer.
- Database constraint và dữ liệu lịch sử.
- Test cho customer null và email null.
- Hợp đồng của domain model: email có bắt buộc trong mọi trạng thái không?

Nếu hàm chỉ nhận `Customer` được tạo bởi factory đã kiểm tra email và constructor không cho phép null, đó là bằng chứng có ích. Nhưng cần xác minh không có deserialization, reflection hoặc đường tạo object khác phá bất biến.

### Cách sửa nếu finding là thật

```java
String normalizeEmail(Customer customer) {
    Objects.requireNonNull(customer, "customer");
    String email = Objects.requireNonNull(
            customer.email(), "customer.email");
    return email.toLowerCase(Locale.ROOT);
}
```

Đoạn này chuyển lỗi tiềm ẩn thành lỗi hợp đồng rõ tại ranh giới hàm. Nếu email thiếu là tình huống nghiệp vụ hợp lệ, nên dùng kiểu/nhánh biểu diễn tình huống đó thay vì ném exception tùy tiện.

Nếu rule báo null nhưng một invariant được kiểm tra ở mọi đường tạo object, nhóm có thể kết luận false positive cho vị trí đó. Khi ấy cần trích bằng chứng về invariant và các call site, không chỉ ghi “đã validate ở nơi khác”.

## 7. Ví dụ 2: cảnh báo SQL injection

Một đoạn code đáng ngờ:

```java
String sql = "SELECT id, email FROM customer WHERE email = '"
        + email + "'";
Statement statement = connection.createStatement();
ResultSet result = statement.executeQuery(sql);
```

Nếu `email` có thể chứa dữ liệu do người dùng kiểm soát, việc nối trực tiếp vào SQL có thể thay đổi cấu trúc câu truy vấn. Đây là finding cần ưu tiên điều tra vì dữ liệu đầu vào có thể trở thành cú pháp.

Cách viết dùng tham số:

```java
String sql = "SELECT id, email FROM customer WHERE email = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    try (ResultSet result = statement.executeQuery()) {
        // Xử lý kết quả.
    }
}
```

Dùng `PreparedStatement` theo cách này tách giá trị khỏi cú pháp SQL. Tuy nhiên, parameter binding không thay thế authorization, validation nghiệp vụ hoặc kiểm soát các phần SQL động như tên cột và hướng sắp xếp.

### Lập luận mức liên quan

Một báo cáo triage tốt cần nêu:

- `email` đến từ đâu và có bị người dùng kiểm soát không?
- Giá trị có đi tới câu SQL cuối cùng không?
- Có nối chuỗi ở wrapper hoặc query builder phía dưới không?
- Query có chạy trong production path không?
- Tài khoản database có quyền đọc/ghi những bảng nào?
- Có parameter binding ở lớp cuối cùng không?

Nếu công cụ báo trên một đoạn wrapper nhưng trace cho thấy mọi giá trị được bind thành parameter, có thể là false positive. Cần đưa ra đường dữ liệu cụ thể và test/implementation của wrapper. Không nên kết luận chỉ từ tên phương thức `querySafe`.

## 8. Ví dụ 3: dependency có CVE

Một scanner báo dependency `example-json-lib` phiên bản 2.1 có CVE. Cần xem:

- Dependency trực tiếp hay bắc cầu?
- Phiên bản thực tế được đóng gói trong artifact production là gì?
- Advisory áp dụng cho phiên bản, module và cấu hình nào?
- Ứng dụng có gọi thành phần bị ảnh hưởng không?
- Dữ liệu đầu vào có thể kích hoạt code dễ tổn thương không?
- Có mitigation chính thức hoặc phiên bản vá không?
- Nâng phiên bản có ảnh hưởng tương thích hoặc serialization không?

Không nên tự kết luận “không dùng nên bỏ qua” chỉ vì không tìm thấy import trực tiếp. Framework có thể nạp dependency qua reflection, service loader hoặc code generated. Cần xem dependency tree, packaged artifact và cách framework sử dụng.

Ngược lại, scanner có thể phân tích manifest hoặc lockfile cũ không còn phản ánh artifact đang phát hành. Khi đó cần chạy lại scan trên commit/artifact chính xác và lưu phiên bản công cụ.

**Reachability là bằng chứng quan trọng nhưng không phải điều kiện duy nhất để xử lý CVE.** Chính sách bảo mật, khả năng khai thác, exposure và hậu quả vẫn cần được xem xét.

## 9. Ví dụ 4: cảnh báo complexity hoặc code smell

Một công cụ báo phương thức có cognitive complexity cao. Đây thường là tín hiệu maintainability, không nhất thiết là lỗi chức năng.

Hãy hỏi:

- Phương thức có nhiều trách nhiệm độc lập hay một thuật toán gắn kết?
- Đường chạy có được thay đổi thường xuyên không?
- Có lỗi hồi quy hoặc thời gian điều tra cao ở vùng này không?
- Test có bảo vệ các nhánh và trạng thái quan trọng không?
- Việc tách phương thức có làm rõ ý nghĩa hay chỉ tạo thêm helper?
- Có thay đổi sắp tới khiến refactor mang lại giá trị thực không?

Một phương thức parser dài có thể biểu diễn một state machine rõ ràng, trong khi một phương thức ngắn điều phối nhiều side effect có thể khó bảo trì hơn. Finding complexity nên được đọc cùng cohesion, churn, defect history và mục tiêu thay đổi.

Có thể kết luận finding là **true positive về số đo** nhưng chưa cần sửa ngay. Đây không phải false positive. Nhóm thừa nhận cấu trúc có độ phức tạp cao nhưng quyết định ưu tiên thấp dựa trên bối cảnh và ghi lại lý do.

## 10. Ví dụ 5: cảnh báo hard-coded secret

Scanner phát hiện một chuỗi giống API key:

```java
private static final String API_KEY = "sk_example_value";
```

Không thể kết luận đó là secret thật chỉ từ hình dạng chuỗi. Cần xác minh:

- Giá trị có phải credential có hiệu lực không?
- Nó có từng được commit hoặc xuất hiện trong artifact/log không?
- Có thể truy cập từ môi trường ngoài production không?
- Credential có quyền gì và còn hiệu lực không?
- Có lịch sử sử dụng hoặc audit trail cần kiểm tra không?

Nếu đó là secret thật, xóa chuỗi khỏi file hiện tại chưa đủ. Cần **thu hồi/rotate credential**, kiểm tra nơi đã lộ và chuyển sang secret management phù hợp. Lịch sử Git vẫn có thể chứa giá trị cũ.

Nếu đó là chuỗi giả trong test fixture, hãy chứng minh nó không có hiệu lực và được tạo cho mục đích kiểm thử. Có thể cấu hình scanner loại trừ file/đường dẫn hẹp nếu quy trình cho phép; không tắt toàn bộ rule chỉ để hết cảnh báo.

## 11. Ví dụ 6: cảnh báo coverage thấp

Một công cụ báo một package chỉ có 42% line coverage. Con số này chưa cho biết package có thiếu kiểm thử hành vi quan trọng hay không.

Cần xem:

- Package có chứa code generated hoặc adapter mỏng không?
- Các nhánh rủi ro đã được test chưa?
- Test có assert kết quả hay chỉ gọi method?
- Có exception path, boundary và concurrency chưa được kiểm tra không?
- Coverage có giảm vì code mới hay vì cấu hình đo thay đổi?
- Có report theo branch/method thay vì chỉ line không?

Coverage thấp có thể chỉ ra khoảng trống đáng điều tra. Coverage cao cũng không chứng minh test tốt. Một test gọi `calculate()` nhưng không assert kết quả có thể tăng line coverage mà không bảo vệ quy tắc.

Khi lập luận mức liên quan, chỉ ra **hành vi chưa được kiểm tra**, thay vì dùng phần trăm làm kết luận duy nhất.

## 12. Xây dựng lập luận: claim, evidence, reasoning, decision

Một phản hồi triage dễ review có thể dùng bốn phần:

1. **Claim — Kết luận tạm thời:** finding có liên quan, không liên quan, đã được sửa hay cần điều tra.
2. **Evidence — Bằng chứng:** file/call site, cấu hình, test, dependency tree, trace hoặc contract.
3. **Reasoning — Lập luận:** bằng chứng đó làm thay đổi khả năng xảy ra hoặc tác động như thế nào.
4. **Decision — Quyết định:** sửa ngay, tạo issue, chấp nhận rủi ro, loại trừ hoặc tiếp tục điều tra.

Ví dụ:

```text
Finding:
  Possible null dereference tại CustomerNormalizer.java:42.

Claim:
  Finding có liên quan và cần sửa.

Evidence:
  normalize() được gọi từ API import khách hàng.
  DTO cho phép email null; không có validation trước call site.
  Test import hiện chưa có trường hợp thiếu email.

Reasoning:
  Dữ liệu ngoài có thể tạo trạng thái null.
  Lời gọi toLowerCase() có thể ném NullPointerException,
  làm thất bại toàn bộ batch import.

Decision:
  Thêm validation tại boundary và test null.
  Giữ rule bật trong CI.
```

Một phản hồi không đủ căn cứ:

```text
Không liên quan. Chỗ này chắc chắn không null.
```

Nó không cho biết ai bảo đảm invariant, ở đâu, bằng cách nào và có bao nhiêu đường vào. Nếu người khác xem lại sau sáu tháng, họ không thể đánh giá quyết định.

## 13. Phân biệt false positive với accepted risk

Hai kết luận này thường bị dùng lẫn:

- **False positive:** công cụ báo điều kiện mà thực tế không tồn tại theo rule hoặc giả định của nó.
- **Accepted risk:** finding mô tả rủi ro có thật, nhưng người có thẩm quyền quyết định tạm thời chấp nhận.

Ví dụ false positive: scanner cho rằng một biến có thể null, nhưng type invariant và mọi constructor được xác minh bảo đảm không null trên tất cả đường sử dụng liên quan.

Ví dụ accepted risk: dependency có lỗ hổng thật, ứng dụng có exposure giới hạn và chưa thể nâng ngay do tương thích. Chủ sở hữu bảo mật chấp nhận trong thời gian ngắn với mitigation, deadline và kế hoạch nâng.

Không nên đánh dấu accepted risk thành false positive để làm dashboard xanh. Điều đó làm mất thông tin về rủi ro còn tồn tại.

### “Không liên quan” cần nói rõ không liên quan ở khía cạnh nào

Có thể finding không nằm trên đường chạy production hiện tại nhưng vẫn là code được build và có thể được kích hoạt trong profile khác. Có thể rule đúng nhưng tác động nhỏ. Có thể cảnh báo trùng với finding gốc.

Hãy dùng nhãn chính xác và nêu điều kiện: “Không được đóng gói trong artifact production của profile hiện tại theo dependency report của commit X” có giá trị hơn “không dùng”.

## 14. Dùng suppression có trách nhiệm

Suppression là chỉ dẫn cho công cụ bỏ qua một finding hoặc một phạm vi nhất định. Nó có thể cần thiết cho false positive đã xác minh hoặc rủi ro được chấp nhận, nhưng cũng có thể che lỗi tương lai.

Một suppression tốt nên:

- Chỉ áp dụng cho rule và vị trí cần thiết.
- Có lý do cụ thể, không chỉ “false positive”.
- Trỏ tới bằng chứng hoặc issue giải thích.
- Có người sở hữu nếu là accepted risk.
- Có thời hạn hoặc ngày xem lại với ngoại lệ tạm thời.
- Không vô tình bỏ qua các finding mới cùng rule ở file khác.
- Được review như một thay đổi cấu hình có tác động tới quality gate.

Ví dụ comment minh họa:

```java
@SuppressWarnings("ExampleRule")
void mapTrustedValue(TrustedValue value) {
    // Suppression chỉ hợp lệ nếu invariant được bảo đảm
    // ở constructor và mọi đường tạo object đã được xác minh.
}
```

Tên rule ở đây chỉ minh họa. Cú pháp suppression và khả năng hỗ trợ phụ thuộc công cụ. Comment không tự chứng minh an toàn; bằng chứng phải tồn tại ở code, test hoặc tài liệu liên quan.

### Khi không nên suppression

- Chưa hiểu rule phát hiện gì.
- Chỉ muốn pipeline xanh trước deadline.
- Finding có thể được sửa với chi phí nhỏ.
- Suppression phải bao phủ cả package/module để bỏ qua một vị trí.
- Không có người chịu trách nhiệm hoặc ngày xem lại cho risk acceptance.
- Một finding security có thể cần xử lý incident hoặc credential rotation.

Nếu chưa đủ bằng chứng, chọn trạng thái **Needs investigation** và đặt thời hạn xử lý thay vì suppress.

## 15. Triage finding theo một quy trình lặp lại

Một quy trình thực tế:

### Bước 1 — Xác định đúng phiên bản và phạm vi scan

Kiểm tra commit, branch, artifact, phiên bản scanner, rule set và cấu hình. Tránh xử lý report cũ hoặc report từ nhánh khác.

### Bước 2 — Đọc rule và vị trí

Tra Rule ID, xem code quanh vị trí, call site và evidence/trace mà công cụ cung cấp.

### Bước 3 — Tìm đường chạy và dữ liệu

Xác định entry point, input, điều kiện kích hoạt, cấu hình runtime và consumer. Với dependency, kiểm tra dependency tree và artifact được đóng gói.

### Bước 4 — Đánh giá exposure và impact

Ai có thể kích hoạt? Điều gì xảy ra nếu finding là thật? Phạm vi ảnh hưởng là một request, tenant, service hay toàn hệ thống?

### Bước 5 — Kiểm tra biện pháp bảo vệ

Tìm validation, parameter binding, authorization, transaction, constraint, timeout, monitoring hoặc mitigation. Xác minh bằng test và implementation, không chỉ giả định.

### Bước 6 — Chọn disposition

Confirmed issue, false positive, not applicable, duplicate, already fixed, accepted risk hoặc needs investigation.

### Bước 7 — Đặt priority và owner

Dùng severity, exposure, impact, likelihood và urgency. Gán người chịu trách nhiệm và mốc xem lại.

### Bước 8 — Ghi quyết định và bằng chứng

Ghi claim, evidence, reasoning và decision. Liên kết issue, test hoặc tài liệu rule khi có thể.

### Bước 9 — Xác minh sau sửa hoặc suppression

Chạy lại scanner trên commit mới. Xác nhận finding đã biến mất vì được sửa, không phải vì rule bị tắt hoặc phạm vi scan bị thu hẹp ngoài ý muốn.

## 16. Phân biệt finding mới, finding cũ và baseline

Một dự án có thể đã có hàng trăm finding trước khi nhóm đưa scanner vào CI. Nếu pipeline đột ngột chặn mọi PR vì toàn bộ nợ cũ, nhóm có thể tìm cách tắt scanner. Nếu bỏ qua toàn bộ baseline, code mới tiếp tục thêm nợ.

Một chiến lược có thể dùng:

- Ghi nhận baseline tại một commit hoặc phiên bản công cụ cụ thể.
- Chặn finding mới có mức rủi ro đã định nghĩa.
- Không làm tăng số finding hoặc severity trong phạm vi được kiểm soát.
- Tạo backlog xử lý finding cũ theo rủi ro.
- Định kỳ nâng baseline và giảm nợ.
- Khi nâng phiên bản scanner, review thay đổi rule set và số finding mới.

Baseline không có nghĩa finding cũ vô hại. Nó chỉ phân biệt **nợ đã tồn tại** với **hồi quy do thay đổi mới**. Finding cũ nghiêm trọng vẫn cần xử lý theo quy trình security/incident phù hợp.

### Không dùng “new code” để che rủi ro cũ đang được kích hoạt

Một thay đổi nhỏ có thể mở một đường chạy mới tới code cũ có finding nghiêm trọng. Dù finding nằm trong baseline, thay đổi mới làm exposure tăng thì cần đánh giá lại. Phạm vi mới không chỉ là dòng được sửa; còn là đường chạy vừa được mở.

## 17. Công cụ khác nhau có giới hạn khác nhau

Một số nhóm công cụ thường gặp:

| Loại công cụ | Có thể phát hiện | Giới hạn cần nhớ |
| --- | --- | --- |
| Compiler và type checker | Lỗi cú pháp, kiểu, một số bất nhất tĩnh | Không chứng minh nghiệp vụ đúng |
| Formatter/linter | Quy ước, style, một số mẫu lỗi | Không đánh giá toàn bộ thiết kế |
| Static analysis | Nullability, control flow, bug pattern, complexity | Có thể không hiểu hết runtime/reflection |
| SAST/taint analysis | Luồng dữ liệu từ source tới sink đáng ngờ | Phụ thuộc framework model và cấu hình |
| Dependency scanner | Phiên bản nằm trong advisory/CVE | Cần xem artifact, module và reachability |
| Secret scanner | Chuỗi giống credential | Cần xác minh giá trị có hiệu lực và phạm vi lộ |
| Test coverage | Dòng/nhánh đã được chạy | Không chứng minh assertion có ý nghĩa |
| Dynamic analysis | Hành vi trong lần chạy cụ thể | Không bao phủ mọi input và đường chạy |
| Performance profiler | Hot path, allocation, latency trong workload đo | Kết quả phụ thuộc môi trường và workload |

Không nên yêu cầu một công cụ trả lời câu hỏi nằm ngoài khả năng của nó. Ví dụ, coverage không chứng minh không có SQL injection; SAST không chứng minh quy tắc hoàn tiền đúng; formatter không chứng minh phương thức dễ bảo trì.

## 18. Mẫu ghi nhận triage

Một bản ghi finding có thể dùng mẫu sau:

```markdown
# Triage finding

## Định danh
- Tool:
- Tool version:
- Rule ID:
- Commit/artifact:
- File và vị trí:

## Mô tả
- Message của công cụ:
- Evidence/trace:
- Severity và confidence do công cụ cung cấp:

## Bối cảnh
- Entry point/đường chạy:
- Dữ liệu đầu vào:
- Runtime/configuration:
- Consumer hoặc dependency liên quan:

## Đánh giá
- Có thể tiếp cận không?
- Điều kiện kích hoạt:
- Impact nếu xảy ra:
- Biện pháp bảo vệ đã xác minh:
- Giới hạn của bằng chứng:

## Kết luận
- Disposition:
- Priority:
- Lý do:
- Bằng chứng liên kết:

## Hành động
- Owner:
- Cách xử lý:
- Ngày cần hoàn thành/xem lại:
- Suppression/exception nếu có:
```

Mẫu này không phải yêu cầu phải điền dài cho mọi cảnh báo. Một warning style có thể chỉ cần ghi nhận ngắn. Finding bảo mật hoặc dữ liệu cần bằng chứng và người chịu trách nhiệm rõ hơn.

### Ví dụ bản ghi ngắn cho cảnh báo complexity

```text
Rule:
  MethodCognitiveComplexity

Finding:
  OrderReconciliationService.reconcile()

Disposition:
  True positive, low immediate priority.

Evidence:
  Method có nhiều nhánh trạng thái, nhưng tất cả nhánh
  cùng thực hiện một quy trình đối soát.
  Test hiện có bao phủ các trạng thái hợp lệ.
  Module ít thay đổi trong các release gần đây.

Reasoning:
  Complexity cao là tín hiệu maintainability thật.
  Chưa có bằng chứng rằng việc tách ngay giảm rủi ro
  nhiều hơn chi phí tạo abstraction mới.

Decision:
  Tạo backlog refactor có điều kiện khi mở rộng trạng thái
  hoặc khi xuất hiện lỗi liên quan.
  Không suppress rule toàn module.
```

Đây là ví dụ quyết định ưu tiên thấp, không phải lời khẳng định rằng code sẽ không bao giờ cần refactor.

## 19. Những lỗi thường gặp khi đọc cảnh báo

**Tin tuyệt đối vào severity.** Severity là đầu vào; cần thêm exposure, impact, likelihood và bối cảnh.

**Bỏ qua vì công cụ từng báo sai.** False positive trước đây không chứng minh finding hiện tại sai.

**Chỉ nhìn một dòng được đánh dấu.** Data flow và call path có thể nằm ở nhiều file.

**Không kiểm tra artifact hoặc commit.** Report có thể cũ, sai branch hoặc không phản ánh dependency thực tế.

**Gọi mọi finding chưa khai thác là false positive.** Rủi ro có thể có thật dù chưa có exploit quan sát được.

**Dùng “không reachable” mà không kiểm tra wiring.** Reflection, framework, configuration hoặc job có thể kích hoạt code.

**Nhầm true positive với ưu tiên cao.** Một code smell có thể đúng nhưng ít urgency; một finding ít confidence có thể cần điều tra ngay vì impact lớn.

**Suppress quá rộng.** Tắt rule cho package có thể che các finding mới không liên quan.

**Không có owner hoặc thời hạn.** Accepted risk dễ trở thành rủi ro bị quên.

**Chỉ sửa dòng được cảnh báo.** Root cause có thể nằm ở input boundary, API contract, dependency hoặc configuration.

**Chạy lại scanner nhưng không kiểm tra phạm vi.** Finding biến mất vì scanner bỏ qua file hoặc rule không có nghĩa lỗi đã được sửa.

**Dùng số lượng finding làm KPI chất lượng đơn giản.** Scanner mới có thể tạo thêm finding dù code không thay đổi; nhóm cần theo dõi xu hướng, severity, tuổi finding và mức xử lý có bằng chứng.

## 20. Thực hành lập luận mức độ liên quan

Với mỗi finding, hãy thử viết bốn câu:

1. **Tôi kết luận gì?** Nêu disposition tạm thời.
2. **Bằng chứng nào ủng hộ?** Chỉ ra call site, input, test, config hoặc artifact.
3. **Bằng chứng đó nói lên điều gì?** Giải thích khả năng xảy ra và tác động.
4. **Tôi đề xuất quyết định gì?** Sửa, tạo issue, suppress hẹp, chấp nhận rủi ro hoặc điều tra tiếp.

Ví dụ:

```text
Kết luận:
  Finding SQL injection là confirmed issue.

Bằng chứng:
  Query được tạo bằng nối chuỗi.
  Tham số xuất phát từ HTTP request.
  Không có parameter binding ở tầng JDBC cuối.

Lập luận:
  Người gọi có thể đưa dữ liệu làm thay đổi cấu trúc SQL.
  Đường này chạy trong production và truy vấn bảng khách hàng.

Quyết định:
  Chuyển sang PreparedStatement, thêm test với input chứa
  ký tự SQL đặc biệt và giữ rule bật trong CI.
```

Nếu thiếu bằng chứng, hãy nói rõ “chưa xác minh được” và đặt câu hỏi cần trả lời. Sự trung thực về mức chắc chắn tốt hơn một kết luận dứt khoát nhưng không có cơ sở.

## 21. Bài tập tình huống

### Tình huống A — Null warning trong một domain object

Scanner báo có thể null tại `order.customer().email().toLowerCase()`. Entity được đọc từ database có constraint NOT NULL, nhưng cùng method cũng được gọi từ import CSV và test fixture.

Hãy xác định các đường tạo object, kiểm tra hợp đồng null ở từng đường và quyết định finding là confirmed issue, false positive hay cần điều tra thêm. Nêu test nào sẽ cung cấp bằng chứng.

### Tình huống B — SQL injection ở query wrapper

SAST đánh dấu một query builder nội bộ. Call site truyền tham số đã bind, nhưng wrapper có một overload nhận raw SQL string.

Hãy lần theo data flow đến JDBC sink, xác định overload nào được gọi trong production và đưa ra bằng chứng cho kết luận. Nếu chỉ một overload an toàn, suppression nên đặt ở đâu và vì sao?

### Tình huống C — CVE trong dependency bắc cầu

Scanner báo CVE Critical trong một thư viện bắc cầu. Dependency tree cho thấy module có trong artifact, nhưng chưa xác định tính năng dễ tổn thương có được sử dụng.

Hãy phân biệt presence, reachability, exploitability và impact. Quyết định ưu tiên cần thêm bằng chứng nào? Vì sao không nên tự động dismiss chỉ vì không có import trực tiếp?

### Tình huống D — Complexity cao nhưng ít thay đổi

Một phương thức có cognitive complexity cao, nhưng nó biểu diễn state machine ổn định và có test cho mọi chuyển trạng thái hợp lệ.

Hãy giải thích vì sao finding có thể là true positive nhưng priority thấp. Những thay đổi hoặc bằng chứng nào khiến bạn nâng mức ưu tiên?

### Tình huống E — Secret scanner trên test fixture

Scanner báo một chuỗi giống token trong fixture. Nhóm nói đó là giá trị giả.

Hãy xác định bằng chứng để chứng minh giá trị không có hiệu lực, kiểm tra lịch sử commit và quyết định có cần rotate secret hay không. Suppression nào đủ hẹp?

### Tình huống F — Coverage giảm sau khi nâng scanner

Coverage giảm từ 78% xuống 64% dù source không đổi. Phiên bản tool mới thay đổi cách tính generated code và branch coverage.

Hãy kiểm tra report, cấu hình include/exclude và baseline. Có nên tạo ngay nhiều task bổ sung test không? Cần phân biệt thay đổi số đo với thay đổi thực của chất lượng ra sao?

### Tình huống G — Finding bị suppress rộng

Một nhóm thêm suppression cho toàn package để bỏ qua một cảnh báo null ở file generated. Một tháng sau, scanner không còn báo một lỗi null mới trong service viết tay.

Hãy xác định vì sao suppression quá rộng nguy hiểm, cách thu hẹp phạm vi và cách xác minh finding mới sau khi bật lại rule.

### Tình huống H — Accepted risk bị quên

Một dependency có rủi ro đã được chấp nhận vì chưa thể nâng trước release. Không có owner hoặc ngày xem lại, và dependency tiếp tục được dùng trong một endpoint mới.

Hãy đánh giá lại exposure, xác định ai có thẩm quyền chấp nhận, biện pháp giảm thiểu và điều kiện hết hạn của ngoại lệ. Việc mở thêm đường sử dụng mới có làm quyết định cũ mất hiệu lực không?

Với mỗi tình huống, trả lời theo chuỗi: **rule và finding → đường chạy/bối cảnh → bằng chứng → khả năng và tác động → disposition → priority → owner/hành động → cách xác minh lại**.

## 22. Ghi nhớ

Đọc cảnh báo tự động là quá trình **đánh giá tín hiệu bằng bằng chứng và bối cảnh**, không phải đếm số dòng đỏ hoặc làm dashboard xanh.

- Tra Rule ID và hiểu giới hạn của công cụ trước khi kết luận.
- Phân biệt finding với defect đã xác nhận; true positive, false positive, not applicable và accepted risk có ý nghĩa khác nhau.
- Đánh giá exposure, likelihood, impact và biện pháp bảo vệ đã xác minh.
- Không đồng nhất severity của tool với priority của nhóm.
- Lần theo input, call path, runtime wiring, artifact và dữ liệu trước khi tuyên bố finding không liên quan.
- Viết lập luận theo claim, evidence, reasoning và decision.
- Suppression phải hẹp, có lý do, người sở hữu và thời hạn xem lại khi là ngoại lệ.
- Chạy lại scanner trên đúng commit/artifact và xác minh finding biến mất vì nguyên nhân đã được xử lý.
- Dùng baseline để quản lý nợ cũ, nhưng không bỏ qua rủi ro cũ khi thay đổi mới mở thêm đường tiếp cận.
- Ưu tiên theo rủi ro và tác động thực tế; ghi rõ điều chưa biết và bước tiếp theo.

Một quyết định triage tốt cho phép người khác đọc lại và hiểu **công cụ đã phát hiện gì, hệ thống thực sự làm gì, bằng chứng nào hỗ trợ kết luận và vì sao nhóm chọn hành động đó**. Đó là cách biến cảnh báo tự động thành cải thiện chất lượng có trách nhiệm.
