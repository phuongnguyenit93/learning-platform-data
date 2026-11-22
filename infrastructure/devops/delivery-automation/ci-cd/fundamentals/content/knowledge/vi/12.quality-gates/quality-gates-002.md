# Kiểm tra định dạng, quy tắc mã và lỗi phân tích tĩnh

Trong CI/CD, mã nguồn cần được kiểm tra trước khi được tích hợp vào nhánh chính hoặc dùng để tạo artifact phát hành. Ngoài việc chạy test, pipeline nên có các cổng chất lượng kiểm tra cách trình bày mã, quy tắc lập trình của nhóm và những lỗi có thể phát hiện mà không cần chạy ứng dụng.

Ba nhóm kiểm tra thường được dùng là **formatting (định dạng)**, **lint/code rules (quy tắc mã)** và **static analysis (phân tích tĩnh)**. Chúng có liên quan nhưng trả lời những câu hỏi khác nhau:

- Formatter giúp mã có cách trình bày nhất quán.
- Linter và bộ quy tắc mã phát hiện cách viết không tuân theo quy ước hoặc mẫu lập trình không mong muốn.
- Static analysis phân tích cấu trúc, kiểu dữ liệu, luồng điều khiển hoặc luồng dữ liệu để tìm lỗi tiềm ẩn mà không cần thực thi chương trình.

Một quality gate tốt xác định công cụ nào phải chạy, mức độ lỗi nào chặn pipeline, cách xử lý cảnh báo cũ và bằng chứng nào được lưu. Nhờ vậy, nhóm có thể phát hiện vấn đề sớm, review dễ hơn và duy trì tiêu chuẩn chất lượng ổn định qua nhiều lần build.

## 1. Phân biệt ba nhóm kiểm tra

| Nhóm | Câu hỏi chính | Ví dụ | Kết quả mong đợi |
|---|---|---|---|
| Formatting | Mã có được trình bày thống nhất không? | Indentation, line wrapping, import order, khoảng trắng | File tuân theo format chuẩn |
| Lint và code rules | Mã có vi phạm quy ước hoặc mẫu lập trình đã thống nhất không? | Tên biến, độ phức tạp, import thừa, API bị cấm | Danh sách rule violation có vị trí và rule ID |
| Static analysis | Có lỗi logic hoặc rủi ro có thể suy ra từ mã mà không chạy chương trình không? | Null dereference, resource leak, dead code, đường đi dữ liệu nguy hiểm | Finding có severity, vị trí và giải thích |

Ranh giới giữa lint và static analysis không hoàn toàn giống nhau ở mọi công cụ. Một linter có thể thực hiện phân tích luồng dữ liệu; một static analyzer cũng có thể kiểm tra style. Vì vậy, khi thiết kế pipeline, hãy phân loại theo mục tiêu và chính sách của nhóm thay vì chỉ dựa vào tên sản phẩm.

## 2. Formatting: chuẩn hóa cách trình bày mã

Formatter tự động áp dụng một bộ quy tắc trình bày. Với cùng nội dung và cùng phiên bản formatter/cấu hình, công cụ tạo ra cách xuống dòng, thụt lề, khoảng trắng hoặc sắp xếp import nhất quán.

Formatting thường xử lý:

- Indentation, dấu ngoặc và khoảng trắng.
- Độ dài dòng và cách xuống dòng biểu thức.
- Thứ tự import hoặc cách nhóm import nếu formatter hỗ trợ.
- Cách trình bày annotation, generic, lambda và cấu trúc ngôn ngữ.
- Quy tắc định dạng cho JSON, YAML, XML, Markdown hoặc file cấu hình.

Formatter giúp review tập trung vào thay đổi logic vì diff ít bị nhiễu bởi phong cách cá nhân. Nó cũng giảm tranh luận lặp lại về style và giúp các file mới có hình thức đồng nhất.

### Format và check là hai thao tác khác nhau

Trong máy phát triển, lập trình viên có thể chạy lệnh tự động sửa file, ví dụ:

```bash
./gradlew spotlessApply
```

Trong CI, thông thường nên chạy lệnh chỉ kiểm tra:

```bash
./gradlew spotlessCheck
```

`spotlessApply` có thể thay đổi file trong workspace. `spotlessCheck` xác minh file đã đúng định dạng và trả lỗi nếu phát hiện sai lệch. CI nên báo lỗi để tác giả sửa và commit thay đổi, nhờ đó nội dung được review và lưu trong Git.

Không nên để pipeline âm thầm format file rồi tiếp tục build mà không thể hiện diff. Khi đó artifact có thể được tạo từ nội dung khác với commit đã review. Nếu tổ chức muốn bot tự tạo commit hoặc pull request format, đó phải là một quy trình riêng có quyền và lịch sử rõ ràng.

### Cấu hình formatter nhất quán

Đặt cấu hình ở repository hoặc trong công cụ dùng chung đã ghim phiên bản. Ví dụ, dự án Java có thể dùng Spotless với formatter được cấu hình rõ:

```kotlin
plugins {
    id("com.diffplug.spotless") version "<PINNED_PLUGIN_VERSION>"
}

spotless {
    java {
        googleJavaFormat("<PINNED_FORMATTER_VERSION>")
        target("src/**/*.java")
    }
}
```

Các giá trị trong dấu ngoặc nhọn là placeholder, cần thay bằng phiên bản đã được tổ chức lựa chọn và kiểm tra. Không để formatter tự lấy bản mới nhất vì thay đổi formatter có thể tạo ra diff lớn dù mã nghiệp vụ không đổi.

Khi cập nhật formatter, nên thực hiện trong pull request riêng hoặc tách rõ phần thay đổi format khỏi thay đổi logic. Điều này giúp reviewer kiểm tra dễ hơn và tránh che khuất lỗi trong diff lớn.

## 3. Lint và quy tắc mã: thống nhất cách viết và giới hạn thiết kế

Lint kiểm tra những mẫu mã đáng ngờ hoặc không phù hợp với quy ước. Code rules có thể do ngôn ngữ, framework, tổ chức hoặc chính dự án định nghĩa.

Ví dụ quy tắc:

- Không dùng import hoặc biến không được sử dụng.
- Đặt tên class, method, field theo quy ước.
- Không gọi API đã deprecated hoặc API bị cấm trong module.
- Giới hạn độ phức tạp của method hoặc số nhánh điều kiện.
- Không nuốt exception hoặc để catch block rỗng.
- Yêu cầu xử lý tài nguyên theo try-with-resources.
- Không gọi `System.out` trong mã production nếu dự án yêu cầu logger.
- Không dùng wildcard import nếu quy ước không cho phép.

Với Java, các công cụ thường gặp gồm Checkstyle, PMD và các rule của compiler. Checkstyle tập trung mạnh vào style và cấu trúc mã; PMD có thể phát hiện nhiều mẫu mã đáng ngờ, độ phức tạp hoặc cách dùng API không phù hợp. Khả năng cụ thể phụ thuộc bộ rule và phiên bản được cấu hình.

Ví dụ Checkstyle có thể kiểm tra:

```xml
<module name="Checker">
    <module name="TreeWalker">
        <module name="UnusedImports"/>
        <module name="NeedBraces"/>
        <module name="AvoidInlineConditionals"/>
    </module>
</module>
```

Đây là đoạn cấu hình minh họa; cần xác minh tên module và cấu trúc cấu hình theo phiên bản Checkstyle được dùng. Không nên sao chép bộ rule mà không xem xét quy ước của dự án.

### Chọn rule có ích thay vì bật mọi cảnh báo

Một bộ rule quá rộng hoặc không phù hợp có thể tạo nhiều cảnh báo ít giá trị. Khi đó lập trình viên dễ bỏ qua kết quả, tắt rule hoặc thêm suppression tùy tiện.

Hãy bắt đầu từ những quy tắc:

1. Ngăn lỗi thường gặp và có tác động rõ ràng.
2. Có hướng sửa cụ thể, nhất quán giữa các thành viên.
3. Phù hợp ngôn ngữ, framework và kiến trúc của repository.
4. Có thể áp dụng tự động hoặc giải thích rõ trong review.
5. Có owner chịu trách nhiệm khi cần thay đổi rule.

Quy tắc mang tính sở thích cá nhân nên được cân nhắc kỹ trước khi biến thành cổng chặn. Các quy tắc an toàn, tài nguyên, API và lỗi có khả năng gây sự cố thường có giá trị cao hơn một quy tắc style ít ảnh hưởng.

## 4. Static analysis: tìm lỗi tiềm ẩn mà không chạy chương trình

Static analysis phân tích mã nguồn hoặc bytecode để tìm những đường thực thi có thể dẫn đến lỗi. Công cụ có thể sử dụng AST, type information, control-flow graph, data-flow analysis hoặc mô hình liên thủ tục để suy luận hành vi.

Một số nhóm finding thường gặp:

| Nhóm | Ví dụ | Rủi ro |
|---|---|---|
| Nullability | Có thể dereference một tham chiếu null | Runtime exception |
| Resource management | Mở stream/socket nhưng không đóng | Rò rỉ tài nguyên |
| Error handling | Bỏ qua exception hoặc xử lý sai nhánh lỗi | Lỗi bị che giấu, trạng thái không nhất quán |
| Concurrency | Truy cập trạng thái dùng chung không an toàn | Race condition hoặc dữ liệu sai |
| Dead code | Nhánh không thể tới hoặc giá trị không được sử dụng | Mã thừa, logic bị bỏ quên |
| API misuse | Dùng API sai hợp đồng hoặc theo cách không an toàn | Lỗi runtime hoặc hành vi ngoài dự kiến |
| Security-related flow | Dữ liệu không tin cậy đi vào điểm nhạy cảm | Injection hoặc lộ dữ liệu tùy ngữ cảnh |

Với Java, SpotBugs phân tích bytecode để tìm các bug pattern; Error Prone bổ sung kiểm tra khi biên dịch; một số công cụ khác thực hiện data-flow hoặc security analysis sâu hơn. Kết quả phụ thuộc cấu hình, phiên bản, thư viện annotation và phạm vi mã được phân tích.

Static analysis không chứng minh chương trình hoàn toàn đúng. Công cụ có thể bỏ sót lỗi (false negative) hoặc báo finding không phải lỗi trong ngữ cảnh cụ thể (false positive). Unit test, integration test, review và kiểm thử runtime vẫn cần thiết vì chúng cung cấp loại bằng chứng khác.

## 5. Thiết kế quality gate theo severity

Không phải mọi finding đều nên có cùng cách xử lý. Một cổng chất lượng cần xác định severity và ngưỡng chặn:

| Mức | Cách xử lý tham khảo | Ví dụ |
|---|---|---|
| Error/Critical | Chặn pipeline hoặc merge | Lỗi có khả năng gây crash, resource leak nghiêm trọng hoặc lỗ hổng rõ ràng |
| High | Chặn theo chính sách rủi ro | Bug pattern có khả năng gây sai dữ liệu hoặc lỗi bảo mật |
| Medium | Cảnh báo hoặc chặn theo module | Độ phức tạp cao, xử lý lỗi thiếu, API nguy hiểm trong ngữ cảnh nhất định |
| Low/Info | Hiển thị để cải thiện dần | Gợi ý maintainability hoặc style không ảnh hưởng trực tiếp |

Tên severity không thống nhất giữa các công cụ. Cần ánh xạ severity của từng scanner sang chính sách chung của dự án và giải thích rõ finding nào chặn merge.

Một gate thực tế có thể yêu cầu:

- Formatter và lint bắt buộc không có violation mới.
- Static analysis không có finding mới ở mức Error/Critical.
- Finding High phải được xử lý hoặc có exception đã phê duyệt.
- Finding Medium/Low được theo dõi theo backlog hoặc ngưỡng chất lượng.
- Các check bắt buộc phải có kết quả cho đúng commit đang được đánh giá.

Không nên đặt ngưỡng bằng cách đếm tổng số finding mà không xét loại và mức độ. Một finding critical có thể nghiêm trọng hơn hàng trăm cảnh báo style. Ngược lại, cho phép số lượng finding tăng vô hạn sẽ làm chất lượng giảm dần mà dashboard vẫn xanh.

## 6. Baseline: kiểm soát lỗi cũ và ngăn lỗi mới

Repository lâu năm có thể đã tồn tại hàng trăm finding trước khi static analysis được đưa vào CI. Nếu chặn toàn bộ ngay lập tức, nhóm khó tích hợp công cụ mà không tạo ra một đợt sửa đổi lớn.

Baseline là danh sách finding hiện có được ghi nhận tại một thời điểm để phân biệt nợ kỹ thuật cũ với vấn đề mới. Một cách triển khai:

1. Chạy analyzer trên revision nền đã chọn.
2. Lưu baseline cùng repository hoặc trong hệ thống quản lý finding có phiên bản.
3. Trong pull request, so sánh kết quả mới với baseline.
4. Chặn finding mới thuộc severity được quy định.
5. Định kỳ giảm baseline bằng cách sửa finding cũ và cập nhật danh sách.

Baseline phải có owner, ngày tạo, quy tắc cập nhật và khả năng review. Nếu tự động chấp nhận mọi finding sau mỗi lần chạy, baseline sẽ hấp thụ cả lỗi mới và làm mất tác dụng của gate.

Với dự án mới, có thể bắt đầu không cần baseline nếu bộ rule đã phù hợp. Với dự án cũ, có thể đặt mục tiêu giảm dần finding theo module hoặc severity thay vì bỏ qua toàn bộ kết quả.

## 7. Suppression và exception phải có lý do

Đôi khi analyzer báo một finding không áp dụng trong ngữ cảnh cụ thể. Suppression cho phép loại trừ finding đó, nhưng cần giới hạn phạm vi:

- Chỉ suppress rule hoặc finding cụ thể, tránh tắt toàn bộ analyzer.
- Ghi lý do và điều kiện khiến finding không áp dụng.
- Gắn owner hoặc ticket xử lý nếu suppression chỉ là tạm thời.
- Đặt thời hạn xem xét lại khi có thể.
- Review suppression như một thay đổi mã nguồn bình thường.

Ví dụ Java:

```java
@SuppressWarnings("SpecificRule")
void processLegacyPayload() {
    // Lý do và liên kết ticket nên được ghi trong comment theo quy ước dự án.
}
```

`SpecificRule` là placeholder; tên suppression phải đúng với analyzer đang dùng. Không nên thêm suppression chung như `all` chỉ để làm pipeline xanh. Nếu một finding được chấp nhận, hồ sơ exception cần cho biết ai chấp thuận, phạm vi nào được miễn và khi nào cần đánh giá lại.

## 8. Xử lý generated code và phạm vi phân tích

Generated code thường có hình thức khác mã viết tay và có thể tạo nhiều finding lặp lại. Có thể cấu hình analyzer loại trừ thư mục generated khỏi một số rule, nhưng phải bảo đảm mã sinh ra vẫn được kiểm tra ở những lớp cần thiết như compile, dependency scan hoặc kiểm tra bảo mật.

Không nên loại trừ cả thư mục chỉ vì có generated file nếu trong đó còn mã do lập trình viên viết. Tách output generator vào thư mục riêng, đánh dấu nguồn sinh và kiểm soát generator version sẽ giúp cấu hình rõ ràng hơn.

Với monorepo, cần xác định phạm vi scan theo module và dependency. Nếu chỉ scan file thay đổi, có thể bỏ sót lỗi do thay đổi ở thư viện dùng chung ảnh hưởng đến consumer. Các thay đổi build script, rule config, dependency hoặc generated source thường cần mở rộng phạm vi kiểm tra.

## 9. Ví dụ quality gate trong Gradle và CI

Một dự án Gradle có thể nối formatter, lint và static analysis thành các task riêng. Ví dụ khái niệm:

```kotlin
plugins {
    java
    id("com.diffplug.spotless") version "<PINNED_VERSION>"
    checkstyle
    pmd
    id("com.github.spotbugs") version "<PINNED_VERSION>"
}

tasks.named("check") {
    dependsOn(
        "spotlessCheck",
        "checkstyleMain",
        "pmdMain",
        "spotbugsMain"
    )
}
```

Đây là ví dụ minh họa; cần chọn plugin version tương thích với Gradle/JDK, cấu hình rule set và kiểm tra task thực tế được tạo. Với dự án nhiều module, cấu hình cần bảo đảm các task áp dụng đúng module và source set. Có thể thêm các task test hoặc kiểm tra khác vào `check` theo chính sách.

Pipeline CI sau đó chỉ cần gọi một task tổng hợp:

```yaml
jobs:
  code_quality:
    steps:
      - name: Checkout
        uses: actions/checkout@<FULL_COMMIT_SHA>
      - name: Run code quality gate
        run: ./gradlew --no-daemon check
      - name: Publish reports
        if: always()
        run: ./gradlew --no-daemon aggregateQualityReports
```

`<FULL_COMMIT_SHA>` là placeholder cần thay bằng SHA đã xác minh. `aggregateQualityReports` chỉ là tên task minh họa, cần tạo task hoặc thay bằng cơ chế upload report thật của dự án. Bước publish report nên chạy sau failure để lưu bằng chứng, nhưng kết quả publish thành công không được biến quality gate thất bại thành thành công.

Trong GitHub Actions, GitLab CI hoặc Jenkins, có thể tách từng nhóm kiểm tra thành job riêng để chạy song song. Nếu tách job, cần có job tổng hợp kiểm tra tất cả check bắt buộc và phân biệt success, failure, skipped, cancelled. Cổng merge chỉ đạt khi các check bắt buộc có kết quả hợp lệ cho đúng revision.

## 10. Giữ kết quả ổn định và dễ xử lý

Chất lượng của quality gate phụ thuộc vào tính ổn định của chính công cụ:

- Ghim phiên bản formatter, linter, analyzer, plugin và rule bundle.
- Giữ cấu hình rule trong Git để thay đổi có thể review.
- Chạy cùng phiên bản công cụ ở local và CI khi có thể.
- Ghi lại version, command, commit SHA, report và thời gian chạy.
- Tránh để analyzer tải rule hoặc policy mới nhất không kiểm soát trong lúc chạy.
- Tách report theo module và source set để finding có vị trí rõ ràng.
- Theo dõi thời gian chạy và tránh phân tích lặp cùng một source nhiều lần mà không có lợi ích.

Nếu tool version thay đổi, kết quả finding có thể thay đổi dù source không đổi. Hãy xem nâng cấp analyzer là thay đổi có ảnh hưởng đến quality gate: đọc release notes, chạy thử trên baseline, đánh giá finding mới và cập nhật ngưỡng có review.

## 11. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ chạy formatter mà không kiểm tra rule | Mã đồng nhất về hình thức nhưng vẫn có lỗi tiềm ẩn | Bổ sung lint và static analysis phù hợp |
| Dùng formatter tự sửa file trong CI | Artifact có thể khác commit đã review | Dùng chế độ check; yêu cầu sửa và commit |
| Bật quá nhiều rule ngay lập tức | Nhiều cảnh báo ít giá trị, nhóm mất niềm tin | Chọn rule theo rủi ro và áp dụng theo giai đoạn |
| Chặn pipeline với mọi warning | Tăng false positive và thời gian xử lý | Định nghĩa severity và ngưỡng rõ ràng |
| Tắt analyzer khi có finding khó sửa | Mất khả năng phát hiện lỗi mới | Dùng baseline và suppression có lý do |
| Baseline tự động hấp thụ mọi finding | Lỗi mới biến thành nợ cũ | Review thay đổi baseline và theo dõi xu hướng |
| Loại trừ toàn bộ generated folder không chọn lọc | Có thể bỏ sót mã cần kiểm tra | Tách generated output và giới hạn exclusion |
| Không lưu report khi job thất bại | Khó điều tra finding và cải thiện rule | Upload report bằng bước diagnostics luôn chạy |

## 12. Checklist thiết kế cổng chất lượng mã

- [ ] Có formatter và chế độ check không tự sửa source trong CI.
- [ ] Phiên bản formatter và cấu hình được ghim, lưu trong repository.
- [ ] Bộ lint/code rules phản ánh quy ước và rủi ro thực tế của dự án.
- [ ] Static analysis được cấu hình cho ngôn ngữ, framework và source set phù hợp.
- [ ] Severity được ánh xạ thành chính sách chặn/cảnh báo rõ ràng.
- [ ] Finding mới được phân biệt với nợ kỹ thuật cũ bằng baseline có kiểm soát khi cần.
- [ ] Suppression có phạm vi hẹp, lý do và người chịu trách nhiệm.
- [ ] Generated code được xử lý theo quy tắc riêng, không loại trừ quá rộng.
- [ ] Report, log, rule ID và commit SHA được lưu để truy vết.
- [ ] Quality gate tổng hợp trạng thái của mọi check bắt buộc và chặn khi có check thiếu kết quả.

Formatting, lint và static analysis bổ sung cho nhau. Formatter tạo sự nhất quán, code rules giữ quy ước và giới hạn thiết kế, còn static analysis tìm lỗi tiềm ẩn từ cấu trúc chương trình. Khi công cụ được ghim phiên bản, rule có chủ đích và gate có ngưỡng minh bạch, pipeline có thể phản hồi sớm mà vẫn duy trì tiêu chuẩn chất lượng có thể kiểm chứng.
