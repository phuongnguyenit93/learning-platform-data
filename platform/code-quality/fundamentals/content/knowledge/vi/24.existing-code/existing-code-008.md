# Dùng baseline mà vẫn giữ khả năng phát hiện vấn đề mới

Một codebase lâu năm có thể đang chứa hàng trăm cảnh báo từ static analysis, test cũ thiếu độ bao phủ, quy tắc định dạng chưa thống nhất và một số lỗi kỹ thuật đã được ghi nhận. Nếu bật một quality gate mới với yêu cầu “không có cảnh báo nào”, gần như mọi thay đổi đều bị chặn ngay từ đầu. Nhưng nếu tắt toàn bộ kiểm tra để nhóm tiếp tục phát triển, các lỗi mới sẽ dễ lọt vào cùng với nợ kỹ thuật cũ.

**Baseline** giúp xử lý khoảng cách đó. Baseline ghi nhận trạng thái vấn đề đã tồn tại tại một mốc đáng tin cậy, để quy trình có thể tập trung chặn **vấn đề mới được đưa vào** và theo dõi phần nợ cũ giảm dần. Baseline không làm cho các vấn đề đã biết trở nên vô hại, cũng không phải lý do để bỏ qua những lỗi nghiêm trọng.

Bài học thuộc chương **Mã hiện hữu** của **CODE_QUALITY_FUNDAMENTALS**. Theo mục tiêu module — hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không** — bài này trình bày cách thiết lập baseline, so sánh kết quả kiểm tra giữa các thay đổi, giữ khả năng phát hiện vấn đề mới, quản lý việc cập nhật baseline và tránh biến ngoại lệ tạm thời thành chính sách vĩnh viễn.

## 1. Vì sao mã hiện hữu cần baseline?

Một dự án mới có thể bắt đầu với bộ quy tắc chất lượng nghiêm ngặt và yêu cầu mọi kiểm tra đều đạt. Với một repository đã phát triển lâu năm, tình hình thường khác:

- Nhiều cảnh báo đã tồn tại trước khi nhóm áp dụng công cụ mới.
- Test có thể chậm, thiếu ổn định hoặc chưa bao phủ những vùng cũ.
- Một số module chưa theo convention hiện tại.
- Việc sửa tất cả vấn đề cùng lúc có thể làm tăng rủi ro hồi quy.
- Nhóm vẫn cần giao tính năng và sửa lỗi trong khi cải thiện chất lượng.

Nếu gate chỉ kiểm tra **tổng số vấn đề hiện tại**, một PR nhỏ có thể bị chặn bởi hàng trăm finding không liên quan. Nếu gate không kiểm tra gì, PR có thể thêm nhiều vấn đề mới mà không ai nhận ra.

Baseline tạo ra một mốc so sánh:

> **Những vấn đề đã được ghi nhận ở mốc nền được theo dõi như nợ hiện hữu; những vấn đề mới phát sinh sau mốc đó phải được phát hiện, phân loại và xử lý theo chính sách gate.**

Điều này cho phép nhóm cải thiện dần mà vẫn giữ tiêu chuẩn cho thay đổi mới.

### 1.1. Baseline không phải là “đạt chất lượng”

Giả sử công cụ phân tích phát hiện 300 finding ở nhánh chính. Nhóm tạo baseline cho các finding đó. Một PR không tạo thêm finding mới có thể đạt gate “không làm tăng nợ theo rule này”.

Nhưng kết luận đó **không có nghĩa**:

- Repository không còn lỗi.
- Tất cả 300 finding đã được chấp nhận về mặt rủi ro.
- Không có lỗ hổng nghiêm trọng.
- Các test cũ đã đáng tin cậy.
- Chất lượng tổng thể đã đạt một mức tuyệt đối.

Baseline chỉ mô tả **những gì đã được ghi nhận trong phạm vi và cấu hình cụ thể**. Mọi tuyên bố rộng hơn đều cần bằng chứng khác.

### 1.2. Khi nào baseline hữu ích?

Baseline thường hữu ích khi:

- Bổ sung static analysis hoặc lint vào một codebase cũ.
- Áp dụng quy tắc mới cho repository có nhiều vi phạm lịch sử.
- Đưa coverage hoặc metric “new code” vào quality gate.
- Di chuyển dần từ convention cũ sang convention mới.
- Tách việc sửa nợ kỹ thuật khỏi các PR tính năng.
- Theo dõi một danh sách finding đã xác minh qua nhiều phiên bản công cụ.

Không phải mọi kiểm tra đều nên dùng baseline. Một test bảo vệ giao dịch hoặc một kiểm tra phân quyền bắt buộc không nên bị miễn trừ chỉ vì lỗi đã tồn tại từ trước.

## 2. Baseline ghi nhận điều gì?

Baseline có thể là snapshot các finding tại một commit, một manifest có fingerprint, hoặc trạng thái được công cụ chất lượng lưu trữ. Dù cách lưu khác nhau, cần biết rõ **đối tượng nào được ghi nhận**.

Một bản ghi finding có thể chứa:

| Trường | Mục đích |
| --- | --- |
| **Fingerprint / identity** | Nhận diện cùng một finding qua các lần phân tích |
| **Rule ID** | Biết quy tắc nào phát hiện vấn đề |
| **Đường dẫn** | Xác định file hoặc module |
| **Vị trí tham khảo** | Giúp tìm đoạn mã hiện tại; có thể thay đổi sau refactor |
| **Severity / category** | Thể hiện mức độ và loại vấn đề theo công cụ |
| **First seen / baseline commit** | Biết finding đã xuất hiện từ khi nào |
| **Analyzer và version** | Biết công cụ nào tạo ra kết quả |
| **Configuration identity** | Biết tập rule và cấu hình áp dụng |
| **Disposition / owner** | Ghi trạng thái xử lý và người phụ trách nếu quy trình cần |

Không phải công cụ nào cũng cung cấp tất cả trường. Điều quan trọng là baseline phải đủ thông tin để **so sánh và điều tra**, không chỉ lưu một con số tổng.

### 2.1. Ví dụ manifest mang tính khái niệm

~~~yaml
baseline:
  createdAt: "2026-11-16"
  sourceCommit: "abc1234"
  analyzer:
    name: "example-static-analyzer"
    version: "4.2"
    configurationId: "java-quality-v3"
  findings:
    - fingerprint: "rule-null-8a71..."
      ruleId: "JAVA_NULL_DEREFERENCE"
      path: "src/main/java/example/LegacyMapper.java"
      severity: "major"
      firstSeen: "2026-11-16"
    - fingerprint: "rule-complexity-1f90..."
      ruleId: "METHOD_COMPLEXITY"
      path: "src/main/java/example/LegacyPricing.java"
      severity: "minor"
      firstSeen: "2026-11-16"
~~~

Đây là **ví dụ minh họa cấu trúc dữ liệu**, không phải file cấu hình hợp lệ cho một analyzer cụ thể. Tên trường, cách tính fingerprint và định dạng baseline phải theo công cụ hoặc cơ chế của repository thực tế.

### 2.2. Baseline cần gắn với mốc và cấu hình

Một snapshot chỉ có ý nghĩa nếu người đọc biết nó được tạo từ:

- Commit hoặc phiên bản mã nào.
- Nhánh nào là nguồn chuẩn.
- Phiên bản analyzer nào.
- Rule nào đang bật, tắt hoặc thay đổi severity.
- Phạm vi module/file nào được quét.
- Build profile, JDK và dependency model nào.
- Cách xử lý file sinh tự động, file test và file legacy.

Nếu hôm nay công cụ chạy 50 rule, tháng sau chạy 70 rule, số finding tăng có thể do **phạm vi phát hiện rộng hơn** chứ không phải code vừa xấu đi. Khi nâng công cụ hoặc đổi cấu hình, cần ghi lại mốc và đánh giá phần chênh lệch.

## 3. Phân biệt vấn đề cũ, vấn đề mới và vấn đề được tái phát hiện

Đây là quyết định cốt lõi của baseline.

| Trạng thái | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| **Existing finding** | Finding đã có trong baseline và vẫn còn | Theo dõi theo kế hoạch nợ kỹ thuật; không tự động coi là vấn đề mới |
| **New finding** | Finding không có trong baseline đáng tin cậy | Xử lý theo severity và chính sách gate |
| **Resolved finding** | Finding có trong baseline nhưng không còn được phát hiện | Ghi nhận đã được xử lý sau khi xác minh |
| **Changed / moved finding** | Finding có vẻ tương ứng nhưng vị trí hoặc fingerprint thay đổi | Đối chiếu thủ công hoặc dùng cơ chế tracking của công cụ |
| **Reintroduced finding** | Vấn đề đã được sửa rồi xuất hiện lại | Xem như vấn đề mới hoặc tái phát theo chính sách |
| **Unknown / unclassified** | Không đủ dữ liệu để kết luận là cũ hay mới | Không tự động bỏ qua; cần triage |

**Finding mới** không nhất thiết là finding nằm trong file mới. Một PR có thể sửa một file cũ và tạo ra lỗi mới ngay trong file đó. Ngược lại, một finding có vị trí dòng khác có thể là finding cũ bị dịch chuyển bởi refactor.

### 3.1. Ví dụ đơn giản

Baseline có:

- Một cảnh báo độ phức tạp trong `LegacyPricing.java`.
- Một cảnh báo nullability trong `LegacyMapper.java`.

PR sửa `LegacyPricing.java`, thêm một cảnh báo SQL injection ở chính file đó và không còn cảnh báo độ phức tạp cũ.

Kết quả cần phân loại:

- Finding độ phức tạp cũ đã được giải quyết.
- Finding SQL injection là **mới**, dù nằm trong file vốn đã có nợ.
- Finding nullability ở file không thay đổi vẫn là finding hiện hữu.

Không được áp dụng quy tắc “file đã có trong baseline thì mọi finding mới trong file đó đều được bỏ qua”. So sánh phải ở **cấp finding hoặc đơn vị đủ chính xác**, không chỉ cấp file.

### 3.2. Finding biến mất chưa chắc đã được sửa

Một cảnh báo có thể biến mất vì:

- Đoạn mã được sửa đúng.
- File được đổi tên hoặc di chuyển.
- Rule bị tắt.
- File bị loại khỏi phạm vi scan.
- Analyzer không còn hiểu được code hoặc build.
- Fingerprint thay đổi.
- Source code sinh tự động bị bỏ khỏi báo cáo.

Vì thế, **“không còn thấy” không đồng nghĩa “đã xử lý”**. Cần xác nhận cùng phạm vi và cùng rule vẫn được chạy, hoặc có lý do kỹ thuật rõ ràng cho việc tracking không còn áp dụng.

## 4. So sánh baseline với PR như thế nào?

Có nhiều cách triển khai, nhưng logic cần bảo đảm rằng kết quả của PR được so với **một baseline đáng tin cậy từ nhánh đích**, không phải snapshot tùy ý do PR tự sửa.

~~~mermaid
flowchart TD
    A[Nhánh đích có baseline đã review] --> B[Chạy analyzer trên commit nền]
    C[Commit PR] --> D[Chạy cùng analyzer và cấu hình]
    B --> E[So sánh findings]
    D --> E
    E --> F{Finding có trong baseline?}
    F -- Có --> G[Existing: theo dõi nợ cũ]
    F -- Không --> H[New: phân loại theo gate]
    H --> I{Mức độ và chính sách}
    I -- Blocking --> J[Chặn và yêu cầu xử lý]
    I -- Non-blocking --> K[Cảnh báo / ghi nhận]
    G --> L[Theo dõi giảm nợ]
    J --> M[Review và cập nhật PR]
    K --> M
~~~

Sơ đồ mô tả một mô hình so sánh khái niệm. Trong thực tế, analyzer có thể dùng server-side issue tracking, file baseline, diff analysis hoặc một cơ chế khác.

### 4.1. Nguồn baseline phải đáng tin

Nếu pipeline đọc baseline trực tiếp từ nhánh PR, tác giả có thể vô tình hoặc cố ý xóa finding khỏi baseline cùng lúc sửa code. Khi đó gate sẽ so sánh kết quả với một mốc đã bị thay đổi bởi chính thay đổi cần đánh giá.

Một số cách giảm rủi ro:

- Lấy baseline từ **merge base hoặc nhánh đích được bảo vệ** theo quy tắc repository.
- Nếu baseline là file trong Git, yêu cầu review riêng khi file đó thay đổi.
- Bảo vệ cấu hình analyzer và danh sách rule bằng code owner hoặc quyền phù hợp.
- Chỉ chấp nhận baseline update qua một quy trình được ghi nhận.
- Ghi commit và cấu hình nguồn trong báo cáo CI.

Không nhất thiết phải dùng một công cụ hoặc cách tổ chức duy nhất; cần đảm bảo **PR không thể tự làm mất các finding mới bằng cách thay đổi mốc so sánh mà không bị phát hiện**.

### 4.2. Phân tích full scan và phân tích diff

| Cách phân tích | Ưu điểm | Giới hạn |
| --- | --- | --- |
| **Full scan + compare baseline** | Có thể phát hiện thay đổi liên file và finding mới ở mọi vùng | Tốn thời gian, cần tracking identity ổn định |
| **Changed-line analysis** | Nhanh, tập trung vào dòng mới/sửa | Có thể bỏ sót lỗi do thay đổi luồng gọi hoặc hợp đồng ở file khác |
| **New-code period** | Đánh giá phần code mới trong một khoảng thời gian | Phụ thuộc cách công cụ xác định “new code” |
| **PR diff checks** | Phù hợp phản hồi nhanh cho tác giả | Không thay thế kiểm tra tích hợp/toàn hệ thống |

Nếu thay đổi một interface làm lộ ra lỗi ở implementation khác, chỉ quét dòng diff có thể bỏ sót. Với các rule cần call graph, data flow hoặc kiến trúc toàn cục, nên giữ **phân tích đủ phạm vi** và dùng baseline để phân loại kết quả.

### 4.3. Không chỉ so sánh số lượng

Giả sử baseline có 100 finding và PR có 100 finding. Hai tập kết quả có thể rất khác:

- 100 finding cũ còn nguyên.
- 10 finding cũ đã sửa và 10 finding mới được tạo ra.
- Một finding critical mới xuất hiện nhưng nhiều finding minor đã biến mất.
- Analyzer bỏ qua một module nên tổng số giảm.

Cần so sánh **identity, rule, severity, trạng thái và phạm vi**, không chỉ tổng số.

## 5. Fingerprint: nhận diện finding qua thay đổi

Một fingerprint nhằm nhận diện cùng một vấn đề qua nhiều lần phân tích. Nó có thể được tạo từ rule ID, đoạn mã, symbol, đường dẫn hoặc ngữ cảnh.

### 5.1. Vì sao line number không đủ?

Giả sử một cảnh báo nằm ở dòng 120. Khi thêm comment ở đầu file, nó chuyển sang dòng 121. Nếu baseline chỉ dùng `path + line`, hệ thống có thể coi đó là finding mới.

Tình huống ngược lại cũng có thể xảy ra: hai vấn đề khác nhau lần lượt chiếm cùng dòng 120 sau refactor. Nếu nhận diện chỉ dựa trên vị trí, hệ thống có thể nhầm chúng là một.

Vì vậy:

- Ưu tiên fingerprint hoặc issue identity do công cụ cung cấp và hỗ trợ tracking.
- Giữ đường dẫn và vị trí như thông tin điều hướng, không mặc định là identity duy nhất.
- Khi đổi tên hoặc di chuyển file, kiểm tra khả năng tracking/rename của công cụ.
- Khi rule hoặc analyzer đổi, xem fingerprint có thay đổi hàng loạt không.
- Không tự suy luận một finding đã được sửa chỉ vì fingerprint cũ biến mất.

### 5.2. Fingerprint cũng có giới hạn

Fingerprint có thể thay đổi khi:
- Rule ID đổi.
- Analyzer nâng version và đổi cách định danh.
- Method hoặc symbol được tách/gộp.
- File được di chuyển.
- Cấu trúc code thay đổi mạnh.
- Một rule tạo nhiều finding giống nhau trong cùng ngữ cảnh.

Do đó, kết quả không khớp fingerprint nên có trạng thái **cần đối chiếu**, không tự động được phân loại là “mới” hay “đã sửa” trong mọi trường hợp.

### 5.3. Tránh fingerprint tự chế quá đơn giản

Một key như `ruleId + filePath + lineNumber` dễ triển khai nhưng không ổn định qua refactor. Nếu phải tự xây, cần kiểm tra các trường hợp rename, thêm dòng, nhiều finding cùng rule trong một method và thay đổi nội dung xung quanh. Tốt hơn là dùng cơ chế tracking đã được công cụ hỗ trợ, nếu có.

## 6. Chính sách gate: chặn vấn đề mới mà vẫn nhìn thấy nợ cũ

Baseline có ích khi đi cùng **chính sách rõ về finding mới**.

Một ví dụ chính sách:

| Loại finding mới | Chính sách minh họa |
| --- | --- |
| Critical security hoặc data-loss risk | Chặn; cần xử lý hoặc quyết định rủi ro theo quy trình có thẩm quyền |
| High severity có tác động runtime rõ | Chặn theo rule và phạm vi đã thống nhất |
| Lỗi correctness trong code mới | Chặn khi đã xác nhận hoặc có bằng chứng mạnh |
| Medium maintainability issue | Có thể chặn theo rule hoặc yêu cầu ticket, tùy mức ảnh hưởng |
| Minor style issue đã được formatter xử lý | Để công cụ tự sửa hoặc cảnh báo |
| Finding chưa phân loại được | Chuyển triage; không tự động coi là existing |

Các mức severity phải theo **định nghĩa của dự án và công cụ**, không dùng từ “critical” mà không có tiêu chí. Một cảnh báo analyzer cũng cần xác minh: false positive không nên tự động trở thành blocker vĩnh viễn.

### 6.1. Nợ cũ không phải vùng miễn trừ tuyệt đối

Giả sử một finding null dereference đã nằm trong baseline. Một PR sửa đúng vùng đó và thêm đường gọi mới khiến khả năng dereference tăng. Không nên nói “đây là cảnh báo cũ nên bỏ qua”.

Cần hỏi:
- PR có làm đường dữ liệu mới đi đến vị trí nguy hiểm không?
- Finding cũ có trở nên dễ kích hoạt hơn?
- Có thay đổi severity hoặc điều kiện runtime không?
- Có thể sửa cùng PR với chi phí hợp lý không?

Một finding cũ có thể **trở thành vấn đề mới về tác động** khi bối cảnh thay đổi. Baseline giúp nhận diện lịch sử, nhưng không thay đánh giá rủi ro hiện tại.

### 6.2. Không miễn trừ theo file hoặc thư mục quá rộng

Nếu toàn bộ `legacy/` được bỏ khỏi analyzer, những lỗi mới trong thư mục đó cũng không còn được phát hiện. Nếu cần loại một vùng đặc biệt, ghi rõ:
- Phạm vi chính xác.
- Lý do và bằng chứng.
- Loại rule được loại.
- Người sở hữu.
- Điều kiện và thời điểm xem lại.

Ưu tiên baseline ở **cấp finding** hơn miễn trừ toàn bộ file/module, trừ khi công cụ có giới hạn kỹ thuật được ghi nhận.

## 7. Ratchet: chỉ giữ hoặc cải thiện mức nợ, không tăng âm thầm

Một **ratchet** là cơ chế giữ ngưỡng chất lượng không lùi lại: thay đổi mới không được làm nợ tăng, và theo thời gian baseline được thu hẹp khi finding được xử lý.

Ví dụ:
- Ban đầu có 300 finding đã ghi nhận.
- Sau một số PR, còn 285 finding cũ.
- PR mới tạo 2 finding mới, dù đã sửa 10 finding cũ.
- Chính sách “không thêm finding mới” vẫn chặn PR đó, hoặc yêu cầu giải quyết 2 finding mới trước khi merge.

Điều này tránh tình trạng nhóm dùng việc sửa một số nợ cũ để bù cho lỗi nghiêm trọng mới.

### 7.1. Ratchet theo tổng số có thể che thay đổi

Nếu gate chỉ yêu cầu `currentCount <= baselineCount`, một PR có thể xóa 20 cảnh báo minor nhưng thêm 1 cảnh báo critical mà vẫn đạt. Vì vậy cần kết hợp:

- **Delta theo finding identity:** finding mới nào xuất hiện?
- **Severity/category:** vấn đề mới thuộc loại gì?
- **Resolved findings:** vấn đề cũ nào thực sự được xử lý?
- **Scope completeness:** scan có chạy đầy đủ không?
- **Metric tổng:** chỉ dùng như tín hiệu bổ sung, không thay danh sách finding.

### 7.2. Quy tắc “không làm xấu hơn” phải định nghĩa rõ

Một chính sách có thể là:
- Không có finding mới thuộc nhóm blocker.
- Không tăng finding mới ở nhóm maintainability đã chọn.
- Coverage trên code mới không thấp hơn ngưỡng của module.
- Không thêm test flaky mới hoặc bỏ qua required check.
- Baseline chỉ được giảm hoặc thay đổi có review.

Không nên dùng câu “quality score không được giảm” nếu không nói rõ score tính thế nào, dữ liệu nào bị loại và cách xử lý severity.

## 8. Xử lý finding cũ khi PR chạm vào vùng mã đó

Đây là tình huống dễ bị xử lý sai.

Một finding cũ nằm trong một method. PR sửa method đó vì một yêu cầu mới. Có ba khả năng:

1. **Vấn đề cũ vẫn tồn tại và không bị ảnh hưởng:** ghi nhận tiếp, nhưng xem PR có làm rủi ro tăng không.
2. **Vấn đề cũ được giải quyết:** xác minh rule không còn phát hiện và cập nhật trạng thái baseline theo quy trình.
3. **Vấn đề cũ thay đổi hoặc chuyển vị trí:** đối chiếu identity, không tự coi là đã sửa hoặc tạo mới chỉ dựa vào line number.

### 8.1. Khi nào nên yêu cầu xử lý cùng PR?

Có thể yêu cầu nếu:
- Finding cũ nằm đúng đoạn code đang sửa và việc sửa cùng ít rủi ro.
- Nó làm thay đổi hành vi của phần mới.
- Nó là blocker theo chính sách hiện hành.
- PR làm finding dễ khai thác hoặc ảnh hưởng rộng hơn.
- Test mới sẽ không đáng tin nếu vấn đề cũ vẫn tồn tại.

Không nhất thiết buộc tác giả giải quyết toàn bộ nợ của module khi chỉ sửa một nhánh không liên quan. Nếu mở rộng phạm vi sẽ làm PR khó review hoặc khó rollback, tạo issue riêng và liên kết với finding.

### 8.2. Không tạo “vùng cấm sửa” vì có finding cũ

Nếu mỗi file có finding đều bị yêu cầu xử lý toàn bộ trước khi chạm vào, nhóm sẽ ngại cải thiện code hiện hữu. Cách hợp lý là:
- Giữ finding cũ có thể truy vết.
- Kiểm tra tác động của diff hiện tại.
- Sửa phần liên quan trực tiếp khi có căn cứ.
- Tách nợ độc lập thành công việc theo dõi.

Baseline nên **giúp mở đường cho thay đổi an toàn**, không đóng băng mã cũ.

## 9. Cập nhật baseline như thế nào?

Baseline cần được cập nhật khi:
- Một hoặc nhiều finding đã được sửa và xác minh.
- Rule hoặc analyzer được nâng cấp có chủ đích.
- Phạm vi module thay đổi.
- File được di chuyển hoặc tái cấu trúc khiến identity cần đối chiếu.
- Chính sách severity hoặc nhóm rule thay đổi.
- Một ngoại lệ được phê duyệt, có phạm vi và thời hạn.

Nhưng việc cập nhật baseline phải là **một thay đổi có review**, không phải bước tự động chạy sau mọi PR.

### 9.1. Quy trình cập nhật có kiểm soát

1. Chạy analyzer trên mốc chuẩn với version và config đã ghi.
2. Tạo diff giữa baseline hiện tại và snapshot mới.
3. Phân loại finding được thêm, giữ, sửa, biến mất hoặc chưa đối chiếu.
4. Xác nhận finding biến mất là đã sửa, không phải do rule/file bị loại.
5. Review những finding mới hoặc thay đổi severity.
6. Ghi lý do cho ngoại lệ và người sở hữu.
7. Commit baseline cùng bằng chứng và thay đổi cấu hình nếu có.
8. Theo dõi kết quả trên pipeline sau khi merge.

### 9.2. Không tự động chấp nhận mọi finding mới vào baseline

Một anti-pattern phổ biến:

~~~text
Mỗi PR:
  chạy analyzer
  ghi đè baseline bằng toàn bộ kết quả hiện tại
  chạy gate so với baseline vừa ghi
~~~

Nếu làm vậy, finding mới được đưa vào baseline ngay trong PR và không còn bị phát hiện. Gate trở thành **máy ghi nhận vấn đề sau khi chúng đã được cho qua**.

Baseline chỉ nên được cập nhật qua workflow được bảo vệ, thường sau khi PR đã được đánh giá và có quyết định rõ.

### 9.3. Nâng cấp analyzer cần tạo mốc so sánh mới

Khi nâng version, kết quả có thể:
- Thêm rule mới.
- Sửa false positive.
- Thay severity.
- Đổi fingerprint.
- Phân tích sâu hơn và phát hiện vấn đề cũ chưa từng được báo.
- Bỏ rule hoặc thay cách tính.

Không nên gộp hàng trăm finding do nâng version vào baseline mà không triage. Có thể tạo một PR riêng cho nâng cấp, phân tích chênh lệch và quyết định những rule mới nào bắt đầu chặn từ thời điểm đó.

## 10. Phân biệt baseline, suppression và risk acceptance

Ba cơ chế này thường bị nhầm lẫn:

| Cơ chế | Mục đích | Hệ quả |
| --- | --- | --- |
| **Baseline** | Ghi nhận finding tồn tại tại mốc nền để so sánh với kết quả sau | Finding cũ vẫn nhìn thấy và có thể được theo dõi |
| **Suppression / ignore** | Không hiển thị hoặc không áp dụng một rule/finding trong phạm vi nhất định | Có thể mất tín hiệu nếu phạm vi quá rộng |
| **Risk acceptance** | Người có thẩm quyền chấp nhận một rủi ro đã được xác định trong điều kiện cụ thể | Rủi ro vẫn tồn tại và cần kiểm soát/theo dõi |

Ví dụ, một cảnh báo bảo mật được xác nhận là có vấn đề nhưng chưa thể sửa ngay. Nhóm có thể ghi nhận vào baseline để quản lý lịch sử, nhưng **không nên dùng baseline để giả vờ rằng rủi ro đã được chấp nhận**. Nếu cần chấp nhận tạm, phải có quyết định, lý do, biện pháp bù trừ, chủ sở hữu và thời hạn.

### 10.1. Suppression phải hẹp và có lý do

Nếu một finding được xác minh là false positive, có thể cần suppression theo vị trí hoặc rule tùy công cụ. Ghi lý do và bằng chứng. Không tắt cả rule cho toàn repository nếu chỉ có một trường hợp đặc biệt.

### 10.2. Không dùng baseline thay quy trình xử lý lỗ hổng

Finding liên quan đến lộ bí mật, phân quyền, injection hoặc mất dữ liệu cần được đánh giá theo chính sách bảo mật. Việc nó đã tồn tại từ trước không tự làm giảm mức nghiêm trọng.

## 11. Ví dụ Java: phân loại finding mới theo baseline

Một analyzer thực tế thường có cơ chế fingerprint riêng. Ví dụ dưới đây chỉ minh họa **chính sách so sánh** bằng một danh sách identity đã được công cụ cung cấp; không tự tạo fingerprint từ dòng mã.

~~~java
import java.util.Objects;
import java.util.Set;

record Finding(String fingerprint, String ruleId, String path) {
    Finding {
        Objects.requireNonNull(fingerprint, "fingerprint");
        Objects.requireNonNull(ruleId, "ruleId");
        Objects.requireNonNull(path, "path");
    }
}

enum FindingState {
    EXISTING,
    NEW
}

final class BaselineComparator {
    static FindingState classify(
            Finding finding,
            Set<String> baselineFingerprints) {

        Objects.requireNonNull(finding, "finding");
        Objects.requireNonNull(
                baselineFingerprints, "baselineFingerprints");

        return baselineFingerprints.contains(finding.fingerprint())
                ? FindingState.EXISTING
                : FindingState.NEW;
    }
}
~~~

Mã này thể hiện nguyên tắc: **finding có identity nằm trong baseline thì được phân loại là hiện hữu; nếu không thì là mới**. Trong hệ thống thật, cần thêm trạng thái unknown/moved, rule version, scope completeness và severity. Không nên để comparator đơn giản này tự quyết định toàn bộ việc merge.

### 11.1. Kiểm thử quy tắc phân loại

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Set;
import org.junit.jupiter.api.Test;

class BaselineComparatorTest {
    @Test
    void classifiesKnownFingerprintAsExisting() {
        Finding finding = new Finding(
                "fp-legacy-001",
                "METHOD_COMPLEXITY",
                "src/main/java/example/Legacy.java");

        assertEquals(
                FindingState.EXISTING,
                BaselineComparator.classify(
                        finding, Set.of("fp-legacy-001")));
    }

    @Test
    void classifiesUnknownFingerprintAsNew() {
        Finding finding = new Finding(
                "fp-new-002",
                "SQL_INJECTION",
                "src/main/java/example/Legacy.java");

        assertEquals(
                FindingState.NEW,
                BaselineComparator.classify(
                        finding, Set.of("fp-legacy-001")));
    }
}
~~~

Test xác nhận comparator theo chính sách minh họa. Nó **không kiểm tra** analyzer có tạo fingerprint ổn định hay pipeline có lấy baseline từ đúng nhánh. Các điều kiện đó phải được xác minh ở cấp tích hợp.

### 11.2. Finding mới trong file cũ vẫn phải được nhận ra

Trong test thứ hai, finding SQL injection ở `Legacy.java` được phân loại là mới vì fingerprint không có trong baseline. Đường dẫn file không quyết định finding là cũ hay mới.

Đây là lý do không nên dùng logic kiểu:

~~~java
// Không đủ chính xác: miễn mọi finding trong file từng có vấn đề.
if (baselinePaths.contains(finding.path())) {
    return FindingState.EXISTING;
}
~~~

Một file có thể chứa nhiều vấn đề khác nhau được thêm ở những thời điểm khác nhau.

## 12. Dùng baseline cho coverage và metric “new code”

Không chỉ static analysis mới cần baseline. Một số chỉ số chất lượng được so sánh theo **phần code mới hoặc phần thay đổi**.

### 12.1. Coverage

Giả sử module cũ có line coverage 42%. Đặt gate yêu cầu toàn module đạt 80% có thể khiến nhóm không thể áp dụng ngay. Một chính sách chuyển tiếp có thể:
- Không cho coverage của code mới giảm dưới ngưỡng đã chọn.
- Yêu cầu test cho nhánh nghiệp vụ quan trọng mới.
- Theo dõi coverage tổng thể như mục tiêu cải thiện dài hạn.
- Bổ sung test cho vùng rủi ro cao theo kế hoạch.

Nhưng coverage không phải oracle. Một test chạy qua dòng mà không kiểm tra kết quả vẫn có thể không phát hiện lỗi. Gate cần xét **test có kiểm tra hành vi quan trọng hay không**, không chỉ phần trăm.

### 12.2. Complexity và duplication

Một module có nhiều method phức tạp lịch sử có thể dùng baseline để không tăng thêm method vượt ngưỡng, đồng thời giảm dần các hotspot cũ. Cần tránh cách làm:
- Tách method chỉ để điểm complexity giảm dù luồng khó hiểu hơn.
- Sao chép code sang file khác để duplication không còn nằm trong phạm vi.
- Thêm exclusion cho cả thư mục mà không có lý do.
- Hạ ngưỡng hoặc đổi rule trong PR tính năng để làm gate xanh.

### 12.3. Test ổn định và flaky checks

Không nên ghi một test flaky vào baseline rồi coi như đã giải quyết. Có thể cần một trạng thái quarantine riêng, nhưng test vẫn phải được chạy và theo dõi. Baseline finding và trạng thái ổn định của test là hai loại dữ liệu khác nhau.

### 12.4. Chất lượng mới và nợ cũ nên có hai góc nhìn

Một dashboard có thể hiển thị:
- **New code gate:** vấn đề mới trong PR hoặc kỳ phát triển.
- **Legacy debt:** số finding hiện hữu theo severity, tuổi và owner.
- **Debt trend:** finding được sửa, thêm mới hoặc tái phát.
- **Coverage/metric trend:** thay đổi theo module và thời gian.

Không gộp tất cả thành một điểm số duy nhất nếu người dùng không thể biết **điều gì đã cải thiện và điều gì vẫn còn rủi ro**.

## 13. Những tình huống baseline dễ bị sai

### 13.1. PR tự cập nhật baseline để làm xanh gate

**Dấu hiệu:** file baseline thay đổi cùng PR nhưng không có phần giải thích finding nào được thêm/xóa.

**Nguy cơ:** finding mới được chấp nhận âm thầm.

**Kiểm soát:** baseline update cần review riêng, pipeline lấy mốc tin cậy từ nhánh đích và báo cáo diff finding.

### 13.2. Rule bị tắt nhưng finding biến mất

**Dấu hiệu:** số finding giảm mạnh ngay sau khi sửa cấu hình.

**Nguy cơ:** dashboard báo nợ giảm dù analyzer không còn tìm vấn đề.

**Kiểm soát:** review thay đổi rule/config, ghi configuration identity và so sánh phạm vi scan.

### 13.3. Rename file tạo hàng loạt finding “mới”

**Dấu hiệu:** PR di chuyển package và báo nhiều finding mới trùng với các finding cũ.

**Nguy cơ:** fingerprint phụ thuộc path hoặc công cụ không theo dõi rename.

**Kiểm soát:** dùng khả năng tracking phù hợp, đối chiếu diff và giữ trạng thái moved/unknown khi chưa chắc chắn.

### 13.4. Full scan không hoàn tất nhưng gate vẫn xanh

**Dấu hiệu:** build thiếu dependency, module bị skip hoặc analyzer báo incomplete nhưng pipeline chỉ kiểm tra số finding.

**Nguy cơ:** không có finding vì không phân tích được.

**Kiểm soát:** gate phải xác minh scan status, module coverage và lỗi phân tích; incomplete không được coi như pass.

### 13.5. Severity đổi sau nâng cấp

**Dấu hiệu:** cùng một finding được chuyển từ minor sang critical hoặc ngược lại.

**Nguy cơ:** so sánh chỉ dựa vào fingerprint làm bỏ qua thay đổi rủi ro.

**Kiểm soát:** phân tích severity delta và áp dụng chính sách mới có kiểm soát. Finding cũ có thể cần triage lại nếu mức tác động được đánh giá khác.

### 13.6. Baseline quá cũ và không có owner

**Dấu hiệu:** nhiều finding đã tồn tại nhiều năm, không ai biết lý do hoặc kế hoạch xử lý.

**Nguy cơ:** baseline trở thành danh sách miễn trừ vô thời hạn.

**Kiểm soát:** phân loại theo module/owner, tuổi, severity và rủi ro; lập kế hoạch giảm nợ và review định kỳ.

## 14. Quy trình triển khai baseline lần đầu

### Bước 1 — Chọn mục tiêu gate

Quyết định baseline dùng cho static analysis, test, coverage, complexity hay nhóm rule nào. Không cố giải quyết mọi vấn đề bằng một baseline duy nhất.

### Bước 2 — Chọn nguồn chuẩn

Chọn nhánh được bảo vệ và commit đã xác định. Ghi phiên bản công cụ, cấu hình, JDK và phạm vi.

### Bước 3 — Chạy phân tích đầy đủ

Đảm bảo build và scan hoàn tất. Ghi cả lỗi phân tích, module bị bỏ qua và các giới hạn. Không tạo baseline từ một lần chạy thiếu phạm vi.

### Bước 4 — Triage finding có rủi ro cao

Trước khi ghi nhận toàn bộ nợ, kiểm tra critical/high security, data loss, quyền truy cập và correctness. Những finding nghiêm trọng không được tự động “chấp nhận” chỉ vì chúng cũ.

### Bước 5 — Tạo baseline và review

Lưu snapshot hoặc cấu hình tracking. Review diff, identity, severity, scope và nguồn dữ liệu. Ghi rõ các ngoại lệ đã được phê duyệt riêng.

### Bước 6 — Bật gate cho finding mới

Chọn rule nào chặn, rule nào cảnh báo, điều kiện nào cần điều tra. Chạy thử trên một số PR để xác nhận baseline tracking hoạt động như mong đợi.

### Bước 7 — Bảo vệ việc cập nhật baseline

Quy định ai được sửa, cần bằng chứng nào, cách review và nơi ghi quyết định. Không để mọi PR tự động ghi đè baseline.

### Bước 8 — Theo dõi và giảm nợ

Đặt owner cho vùng quan trọng, xem trend, xử lý finding cũ theo mức rủi ro. Khi finding được sửa, cập nhật baseline sau khi xác minh.

## 15. Mẫu chính sách baseline cho repository

Mẫu sau là tài liệu chính sách khái niệm, không phải cấu hình CI cụ thể:

~~~markdown
# Quality baseline policy

Nguồn baseline:
- Nhánh chuẩn:
- Commit:
- Analyzer/version:
- Configuration identity:
- Phạm vi module và loại file:

Quy tắc so sánh:
- Finding identity được lấy từ:
- Finding mới được phân loại như thế nào:
- Finding moved/unknown được triage ra sao:
- Finding đã sửa được xác minh bằng gì:

Quality gate:
- Nhóm finding bắt buộc chặn:
- Nhóm finding cảnh báo:
- Điều kiện scan incomplete:
- Chính sách retry và quarantine nếu có:

Baseline maintenance:
- Ai được đề xuất cập nhật:
- Ai review và phê duyệt:
- Bằng chứng cần đính kèm:
- Cách xử lý analyzer/config upgrade:
- Lịch rà soát nợ cũ:

Risk management:
- Finding bảo mật nghiêm trọng:
- Quy trình risk acceptance:
- Owner, hạn và biện pháp bù trừ:

Báo cáo:
- New findings:
- Resolved findings:
- Existing debt by severity/owner:
- Scope and scan status:
~~~

Một chính sách tốt phải trả lời được câu hỏi: **nếu PR thêm một lỗi mới vào một file đã có mười lỗi cũ, gate sẽ nhận ra bằng cách nào?** Nếu câu trả lời chỉ là “đếm số finding tổng thể”, chính sách chưa đủ chính xác.

## 16. Những sai lầm thường gặp

**“Đã có baseline nghĩa là finding cũ được chấp nhận.”** Không. Baseline chỉ ghi nhận lịch sử; risk acceptance là quyết định riêng có chủ sở hữu và điều kiện.

**“File đã có finding thì không cần chặn finding mới.”** Sai. Một file cũ có thể nhận thêm lỗ hổng hoặc bug mới; so sánh phải ở cấp finding.

**“Tổng số finding không tăng là gate đạt.”** Không đủ. Một finding critical mới có thể bị che bởi nhiều finding minor đã biến mất.

**“Rerun analyzer rồi ghi đè baseline là cách cập nhật nhanh.”** Cách này có thể hấp thụ cả vấn đề mới mà không triage. Baseline update phải có review và bằng chứng.

**“Finding biến mất là đã sửa.”** Có thể do file bị loại, rule bị tắt, scan không hoàn tất hoặc fingerprint đổi. Phải xác minh phạm vi và nguyên nhân.

**“Line number là identity ổn định.”** Không. Thêm dòng hoặc move code có thể làm vị trí thay đổi; dùng tracking phù hợp và xử lý finding chưa đối chiếu.

**“Baseline phải luôn nằm trong nhánh PR để pipeline dễ chạy.”** Nếu PR tự sửa mốc so sánh mà không kiểm soát, gate có thể bị vô hiệu hóa. Nguồn baseline phải đáng tin và được bảo vệ.

**“Mã legacy thì không cần kiểm tra bảo mật.”** Sai. Rủi ro nghiêm trọng hiện hữu vẫn cần xử lý theo chính sách bảo mật, dù nó đã có từ trước.

**“Coverage của code mới cao nghĩa là test tốt.”** Không. Coverage không chứng minh assertion và oracle đúng.

**“Baseline càng ít finding càng chứng minh chất lượng càng cao.”** Chỉ khi phạm vi scan và cấu hình tương đương, finding được xác minh và không bị loại bỏ tùy tiện.

**“Nợ cũ không liên quan tới PR thì không cần theo dõi.”** Không. Nó vẫn cần owner, xu hướng và kế hoạch xử lý phù hợp mức rủi ro.

## 17. Bài tập vận dụng

### Tình huống A — Finding mới trong file đã có nợ cũ

Baseline ghi nhận hai cảnh báo complexity trong `LegacyOrderService.java`. PR sửa class đó và tạo thêm một cảnh báo SQL injection ở một phương thức mới.

**Câu hỏi:** gate nên phân loại thế nào?

**Gợi ý:** hai finding complexity đã biết vẫn là existing nếu identity khớp; SQL injection là finding mới dù file đã có trong baseline. Phải xử lý theo chính sách security, không miễn trừ theo path.

### Tình huống B — Số finding giảm sau khi tắt rule

Sau khi thay cấu hình, báo cáo từ 120 finding giảm còn 70. Không có PR sửa code tương ứng.

**Câu hỏi:** có thể kết luận nợ kỹ thuật đã giảm không?

**Gợi ý:** chưa. Kiểm tra rule nào bị tắt/đổi severity, module nào còn được scan và analyzer version. Đây có thể là thay đổi phạm vi chứ không phải finding đã được xử lý.

### Tình huống C — File rename làm finding thành mới

Một PR di chuyển package từ `legacy.billing` sang `billing.core`. 30 finding cũ xuất hiện lại với path mới.

**Câu hỏi:** xử lý sao để không chặn nhầm và không bỏ sót?

**Gợi ý:** kiểm tra fingerprint/tracking của analyzer và rename mapping. Phân loại moved/unknown, đối chiếu rule, symbol và code context; không tự động xóa hoặc chấp nhận toàn bộ.

### Tình huống D — Một lỗi critical cũ đã nằm trong baseline

Scanner ghi nhận một vấn đề phân quyền critical từ trước. Nhóm muốn bật gate mới và cho qua vì “không phải PR này tạo ra”.

**Câu hỏi:** có thể dùng baseline để bỏ qua không?

**Gợi ý:** baseline có thể phân biệt lịch sử nhưng không biến rủi ro thành chấp nhận. Cần triage, xử lý hoặc risk acceptance theo quy trình bảo mật có thẩm quyền, với owner và thời hạn. Chính sách có thể chặn release cho tới khi có quyết định.

### Tình huống E — PR tự thêm finding vào baseline

Pipeline chạy scan trên PR, ghi kết quả mới vào baseline rồi so sánh với chính baseline đó. Gate luôn báo không có finding mới.

**Câu hỏi:** sai ở đâu?

**Gợi ý:** baseline không còn là mốc tin cậy độc lập. Pipeline phải so kết quả PR với baseline từ nhánh đích/commit chuẩn; cập nhật baseline cần workflow riêng và review.

### Tình huống F — Refactor làm finding cũ chuyển dòng

Một finding nullability nằm ở dòng 80 trước refactor, nay ở dòng 95. Fingerprint thay đổi nên công cụ báo một finding mới.

**Câu hỏi:** có nên tự động đánh dấu existing không?

**Gợi ý:** không tự động nếu chưa có bằng chứng. Đối chiếu symbol, rule, đường dữ liệu và nội dung; dùng trạng thái moved/unknown khi cần. Nếu refactor thực sự tạo một đường null mới, đó có thể là finding mới về tác động.

### Tình huống G — Baseline không ghi analyzer version

Sau một lần nâng công cụ, nhóm không thể giải thích vì sao 50 finding xuất hiện mới.

**Câu hỏi:** thông tin nào đã thiếu và cần bổ sung?

**Gợi ý:** analyzer/version, configuration identity, rule set, phạm vi scan, commit và môi trường build. Tạo một mốc nâng cấp có kiểm soát, triage chênh lệch rồi mới quyết định gate.

### Tình huống H — Coverage code mới đạt nhưng thiếu kiểm tra biên

Một PR có coverage 90% nhưng không test ngưỡng tính phí. Bug `>` thay vì `>=` vẫn lọt.

**Câu hỏi:** baseline coverage có đủ bảo vệ không?

**Gợi ý:** không. Coverage là chỉ số thực thi, không phải oracle. Cần test expected theo đặc tả cho giá trị ngay dưới, đúng và trên ngưỡng.

## 18. Checklist trước khi áp dụng baseline

- **Mục tiêu:** baseline dùng cho rule và quyết định chất lượng nào?
- **Nguồn:** snapshot lấy từ nhánh/commit chuẩn nào?
- **Phạm vi:** analyzer có quét đầy đủ module và artifact không?
- **Cấu hình:** version, rule set, JDK và config identity đã được ghi?
- **Identity:** finding được nhận diện bằng fingerprint nào, có xử lý rename/move?
- **So sánh:** finding mới trong file cũ có bị phát hiện?
- **Severity:** vấn đề nghiêm trọng có được xử lý theo policy riêng?
- **Trust:** PR có thể tự sửa baseline hoặc tắt rule mà không review không?
- **Update:** finding được xóa khỏi baseline sau khi xác minh hay chỉ vì biến mất?
- **Unknown:** kết quả chưa phân loại có bị tự động bỏ qua không?
- **Ratchet:** gate có chặn finding mới theo severity thay vì chỉ so tổng số?
- **Debt:** finding cũ có owner, trend và kế hoạch giảm nợ?
- **Tích hợp:** scan incomplete, skipped và failed có được phân biệt với pass?
- **Minh bạch:** báo cáo cho reviewer thấy new, existing, resolved và moved riêng biệt?

## 19. Kết luận

**Baseline cho phép nâng chuẩn chất lượng trên một codebase cũ mà không buộc nhóm phải sửa toàn bộ nợ kỹ thuật trong một lần.** Nó tạo mốc so sánh để những thay đổi mới không âm thầm làm chất lượng đi xuống, trong khi các vấn đề cũ vẫn có thể được theo dõi và xử lý theo mức rủi ro.

Muốn giữ được khả năng phát hiện, baseline phải có nguồn đáng tin, identity đủ ổn định, phạm vi scan được xác minh và quy trình cập nhật có review. Finding mới trong file cũ vẫn phải được nhận ra; finding nghiêm trọng đã tồn tại vẫn cần quyết định rủi ro; finding biến mất phải được xác minh trước khi coi là đã sửa.

Trong **CODE_QUALITY_FUNDAMENTALS**, dùng baseline đúng cách giúp mã **đáng tin cậy hơn nhờ không để vấn đề mới lọt qua, dễ hiểu hơn nhờ phân biệt nợ cũ với thay đổi hiện tại và dễ thay đổi hơn nhờ cải thiện chất lượng theo từng bước có thể kiểm chứng**.
