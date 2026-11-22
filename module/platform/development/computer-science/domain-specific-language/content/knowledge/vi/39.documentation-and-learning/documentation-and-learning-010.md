# Lộ trình onboarding

## 1. Onboarding trong một dự án DSL là gì?

**Onboarding** là quá trình giúp một người mới hiểu mục tiêu, kiến trúc, công cụ, quy trình làm việc và cách đóng góp vào một dự án. Với một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), onboarding cần kết hợp kiến thức ngôn ngữ, kỹ thuật compiler, runtime, tích hợp ứng dụng, kiểm thử và quy tắc nghiệp vụ của miền.

Một người mới có thể đã biết lập trình nhưng vẫn chưa hiểu:

- DSL được tạo ra để giải quyết vấn đề nào.
- Ai viết DSL và ai chịu trách nhiệm vận hành chương trình DSL.
- Source đi qua lexer, parser, semantic analysis, compiler và runtime ra sao.
- Cách thêm cú pháp, kiểu, function hoặc host integration.
- Cách chạy test và xác định regression.
- Cách review, phát hành và hỗ trợ người dùng.
- Những dữ liệu và capability nào cần được bảo vệ.

Một lộ trình onboarding tốt giúp người mới đi từ hiểu bối cảnh đến thực hiện một thay đổi nhỏ, sau đó tự xử lý một nhiệm vụ có phạm vi rõ. Lộ trình cần có mục tiêu, tài liệu, bài tập thực hành, người hỗ trợ và tiêu chí hoàn thành.

Onboarding không chỉ là đọc tài liệu hoặc cài công cụ. Người học cần tạo được một kết quả có thể kiểm chứng trong môi trường dự án.

## 2. Kết quả cần đạt

Kết thúc onboarding cơ bản, thành viên nên có khả năng:

1. Giải thích DSL phục vụ người dùng và nghiệp vụ nào.
2. Chạy được project và các lệnh phát triển cơ bản.
3. Tìm đúng nơi định nghĩa grammar, AST, semantic model và runtime.
4. Theo dõi một source DSL qua pipeline xử lý.
5. Viết hoặc cập nhật test cho một behavior nhỏ.
6. Đọc diagnostic, log và failure output.
7. Thực hiện một thay đổi nhỏ theo quy trình review của nhóm.
8. Nhận biết ranh giới bảo mật và quyền của host API.
9. Biết tìm tài liệu, hỏi đúng người và báo blocker có đủ thông tin.
10. Hiểu cách một thay đổi đi từ local development đến release.

Các mục tiêu này là năng lực quan sát được. Chẳng hạn, thay vì chỉ nói người học đã hiểu parser, yêu cầu họ tìm parser entry point, chạy một test parser và giải thích AST được tạo từ một fixture.

## 3. Xác định đối tượng và lộ trình phù hợp

Không phải ai tham gia dự án cũng cần học mọi phần ở cùng độ sâu.

| Vai trò | Trọng tâm onboarding |
|---|---|
| DSL author / domain expert | Cú pháp, semantics, ví dụ, validation và cách đọc diagnostic |
| Application developer | Host API, data contract, integration và error handling |
| Compiler engineer | Lexer, parser, AST, type checking, IR và code generation |
| Runtime engineer | Evaluation, execution context, state, scheduling và isolation |
| Plugin developer | Extension API, lifecycle, capability và compatibility |
| QA / test engineer | Test strategy, fixtures, golden tests, regression và reproducibility |
| DevOps / platform engineer | Build, CI/CD, artifact, observability và incident response |
| Technical writer / trainer | Learning objectives, examples, glossary và documentation workflow |

### 3.1 Common core

Mọi vai trò nên hiểu mục tiêu DSL, cách lấy source và tài liệu, cách chạy môi trường cần thiết, cách báo lỗi, cách tìm owner và các quy tắc bảo mật cơ bản.

### 3.2 Role-specific depth

Sau common core, người học đi sâu vào các module liên quan đến công việc. Một domain expert không cần tự sửa parser để sử dụng DSL tốt; compiler engineer cần hiểu sâu grammar và AST hơn người viết policy.

### 3.3 Không giả định mọi người có cùng nền tảng

Trước khi bắt đầu, xác định kiến thức đã có về ngôn ngữ lập trình, Git, build tool, testing, domain nghiệp vụ và hệ thống phân tán. Dùng thông tin đó để chọn bài học bổ trợ, không dùng để loại bỏ những bước kiểm tra thực hành quan trọng.

## 4. Lộ trình onboarding theo giai đoạn

Một lộ trình tham khảo có thể chia thành sáu giai đoạn:

~~~text
1. Orientation
      |
      v
2. Environment setup
      |
      v
3. Understand the DSL
      |
      v
4. Explore the implementation
      |
      v
5. Make a first contribution
      |
      v
6. Independent ownership
~~~

| Giai đoạn | Mục tiêu | Bằng chứng hoàn thành |
|---|---|---|
| Orientation | Hiểu mục tiêu, người dùng và quy trình | Giải thích được use case và tìm đúng owner |
| Environment | Cài đặt và chạy project | Chạy được một command hoặc test cơ bản |
| DSL fundamentals | Viết và đọc chương trình DSL | Hoàn thành bài tập nhỏ |
| Architecture | Hiểu pipeline và module | Theo dấu một feature qua các lớp |
| First contribution | Sửa một vấn đề có phạm vi nhỏ | Pull request được review |
| Ownership | Tự xử lý nhiệm vụ thông thường | Hoàn thành task với mức hỗ trợ phù hợp |

Thời gian thực tế phụ thuộc độ phức tạp của DSL, quy mô repository, nền tảng của người học và mức độ sẵn có của mentor.

## 5. Giai đoạn 1: Orientation và bối cảnh nghiệp vụ

Trước khi đọc source code, người mới cần hiểu vì sao DSL tồn tại.

### 5.1 Tìm hiểu bài toán

Trả lời các câu hỏi:

- DSL mô hình hóa domain nào?
- Vấn đề nào khiến một DSL phù hợp hơn cấu hình thông thường hoặc code tổng quát?
- Người dùng chính là ai?
- Ai tạo, review, triển khai và vận hành chương trình DSL?
- Chương trình DSL chạy ở đâu và có tác động gì?
- Những use case nào được hỗ trợ và những use case nào nằm ngoài phạm vi?

### 5.2 Tìm hiểu thuật ngữ miền

Thu thập glossary gồm tên entity, relationship, trạng thái, command, event, rule và thuật ngữ nghiệp vụ. Ví dụ trong DSL đơn hàng có thể gồm Order, LineItem, Payment, Shipment, Refund và OrderStatus.

Thuật ngữ nghiệp vụ cần được dùng nhất quán trong tài liệu, grammar, API và diagnostic.

### 5.3 Đọc ví dụ thực tế

Bắt đầu bằng một chương trình DSL hợp lệ và một chương trình không hợp lệ. Người học nên xác định:

- Cấu trúc chính.
- Input và output.
- Các rule hoặc step.
- Những validation được áp dụng.
- Kết quả mong đợi.
- Cách người dùng phát hiện lỗi.

### 5.4 Hiểu giới hạn và rủi ro

Xác định dữ liệu nào nhạy cảm, thao tác nào tạo side effect, ai có quyền chạy chương trình và điều gì xảy ra khi chương trình lỗi.

**Mốc hoàn thành:** người học giải thích được một use case từ nhu cầu nghiệp vụ đến kết quả khi chạy DSL.

## 6. Giai đoạn 2: Thiết lập môi trường phát triển

Mục tiêu là có thể lấy source, build, chạy test và quan sát kết quả.

### 6.1 Kiểm tra prerequisites

Tùy project, prerequisites có thể gồm:

- Git và quyền truy cập repository.
- JDK hoặc runtime tương ứng.
- Build tool và wrapper.
- IDE/editor và extension cần thiết.
- Database hoặc service local nếu integration test yêu cầu.
- Container runtime hoặc công cụ phát triển phụ trợ.
- Quyền truy cập package registry và artifact repository.

Dùng đúng version được project hỗ trợ. Không tự nâng cấp toolchain khi chưa hiểu tác động đến build và generated output.

### 6.2 Lấy source code

Người mới cần biết repository chính, branch strategy, cách cập nhật branch và cách kiểm tra working tree.

~~~bash
git clone <repository>
cd <project>
git status
git branch --show-current
~~~

Các lệnh trên minh họa quy trình; URL và branch cần lấy từ hướng dẫn chính thức của dự án.

### 6.3 Build lần đầu

Chạy build wrapper hoặc command được project tài liệu hóa. Ghi nhận:

- Command đã chạy.
- Tool version.
- Kết quả và thời gian.
- Những dependency cần tải.
- Cách xử lý lỗi môi trường phổ biến.

Không cần chạy toàn bộ pipeline phát hành để chứng minh môi trường local hoạt động.

### 6.4 Chạy test cơ bản

Bắt đầu với một test nhỏ hoặc một module độc lập. Người học cần biết cách chạy test đơn lẻ, xem failure output và tìm test report.

### 6.5 Cấu hình local

Phân biệt configuration mẫu với secret thật. Không commit token, password hoặc file cấu hình chứa credential. Nếu cần service local, dùng dữ liệu giả và tài khoản phát triển được cấp.

### 6.6 Troubleshooting môi trường

Các lỗi phổ biến:

- JDK không đúng version.
- Build wrapper không có quyền thực thi.
- Dependency registry không truy cập được.
- Port local đã được sử dụng.
- Environment variable bị thiếu.
- Database hoặc service local chưa chạy.
- IDE dùng JDK khác với terminal.

Ghi rõ command, error message và môi trường trước khi nhờ hỗ trợ.

**Mốc hoàn thành:** người học build được module liên quan và chạy được ít nhất một test thành công.

## 7. Giai đoạn 3: Học cách sử dụng DSL

Trước khi đọc compiler implementation, người mới nên sử dụng DSL như một người dùng.

### 7.1 Cú pháp căn bản

Học:

- Identifier, literal và type.
- Expression và operator.
- Declaration và block.
- Function hoặc rule.
- Scope và reference.
- Import/module nếu có.
- Comment và formatting.

### 7.2 Semantics

Hiểu cú pháp viết ra có ý nghĩa gì. Ví dụ, hai biểu thức có thể parse thành AST hợp lệ nhưng có ý nghĩa khác do precedence, type conversion hoặc scope.

### 7.3 Diagnostics

Tạo một số lỗi có chủ ý:

- Thiếu dấu phân cách.
- Dùng identifier chưa khai báo.
- Truyền sai kiểu.
- Thiếu field bắt buộc.
- Gọi function không được phép.

Quan sát diagnostic code, message, severity và source location.

### 7.4 Bài tập tăng dần

1. Đọc một ví dụ có sẵn và mô tả từng phần.
2. Thay đổi literal hoặc identifier.
3. Thêm một rule đơn giản.
4. Tạo input sai và đọc diagnostic.
5. Chạy chương trình và so sánh kết quả với mong đợi.

### 7.5 Đọc tài liệu tham chiếu

Biết tìm grammar reference, built-in functions, type reference, examples, migration guide và troubleshooting. Tài liệu tutorial giúp bắt đầu; reference là nguồn tra cứu khi viết chương trình thật.

**Mốc hoàn thành:** người học có thể viết một chương trình nhỏ, chạy được và giải thích kết quả.

## 8. Giai đoạn 4: Hiểu kiến trúc DSL

Sau khi sử dụng DSL, người mới bắt đầu tìm hiểu cách triển khai.

### 8.1 Bản đồ kiến trúc

Một pipeline phổ biến:

~~~text
Source text
    |
    v
Lexer
    |
    v
Token stream
    |
    v
Parser
    |
    v
AST
    |
    v
Semantic analysis
    |
    v
Typed AST / IR
    |
    +----> Code generation
    |
    +----> Runtime execution
    |
    v
Diagnostics and result
~~~

Không phải DSL nào cũng có đủ các thành phần hoặc đúng thứ tự trên. Dùng sơ đồ thực tế của repository làm bản đồ chính.

### 8.2 Lexer

Tìm nơi định nghĩa token, keyword, literal, comment và source position. Thử truy vết một token từ source đến token stream.

### 8.3 Parser

Tìm grammar, parser entry point và AST node. Học cách một production rule tạo ra node hoặc diagnostic.

### 8.4 Semantic analysis

Tìm symbol table, scope resolution, type checking, validation và diagnostic model. Hiểu parser thành công không có nghĩa chương trình hợp lệ về nghiệp vụ.

### 8.5 Intermediate representation

Nếu có IR, tìm cách compiler chuyển AST sang IR, cách biểu diễn dependency và những pass biến đổi.

### 8.6 Generator hoặc runtime

Nếu DSL generate code, tìm template, backend và artifact writer. Nếu DSL được interpret, tìm evaluator, execution context, host function registry và error boundary.

### 8.7 Editor integration

Nếu có Language Server, tìm document lifecycle, diagnostics, completion, hover, navigation và cách source range được chuyển sang protocol của editor.

### 8.8 Theo dấu một feature

Chọn một cú pháp nhỏ, ví dụ declaration hoặc function call, rồi lần theo:

1. Token được lexer tạo ra.
2. Parser nhận diện production.
3. AST node được tạo.
4. Semantic analyzer resolve symbol và type.
5. Generator/runtime xử lý node.
6. Diagnostics hoặc result được trả về.

**Mốc hoàn thành:** người học có thể tìm các module chính và giải thích đường đi của một feature.

## 9. Giai đoạn 5: Đọc repository và quy tắc dự án

Không nên bắt đầu bằng việc đọc mọi file. Hãy hiểu cấu trúc và tìm đúng điểm vào.

### 9.1 Bản đồ thư mục

Tạo ghi chú ngắn cho:

- Module compiler.
- Module runtime.
- Module API/model.
- Plugin hoặc extension.
- Editor/Language Server.
- Test và fixture.
- Documentation.
- Build và deployment configuration.

Tên module thực tế tùy repository.

### 9.2 Điểm vào quan trọng

Tìm:

- Application entry point.
- Compiler facade.
- Parser entry point.
- Runtime bootstrap.
- Host API registry.
- Test suite entry point.
- Configuration loader.

### 9.3 Hướng dẫn repository

Đọc hướng dẫn đóng góp, coding conventions, branch policy, pull request template và quy tắc xử lý issue. Nếu có file hướng dẫn theo thư mục, tuân theo hướng dẫn áp dụng cho phần code đang sửa.

### 9.4 Lịch sử thay đổi

Dùng Git history để hiểu vì sao một abstraction được tạo ra hoặc vì sao một behavior đã thay đổi. Lịch sử giúp bổ sung ngữ cảnh nhưng code và tài liệu hiện tại vẫn là nguồn mô tả implementation đang chạy.

### 9.5 Hỏi người phụ trách

Hỏi owner của module về điểm mở rộng được hỗ trợ, API ổn định, test phù hợp và các phần đang được thay đổi. Tránh suy đoán rằng một class public trong repository là extension contract được bảo đảm.

**Mốc hoàn thành:** người học có thể tìm nơi cần sửa cho một loại task và biết ai review phần đó.

## 10. Giai đoạn 6: Thực hành kiểm thử

Test là cách an toàn để học behavior hiện tại và chứng minh thay đổi.

### 10.1 Các lớp test

| Loại test | Ví dụ trong DSL |
|---|---|
| Unit test | Lexer tokenization, type rule |
| Parser test | AST cho một grammar case |
| Semantic test | Scope resolution, type mismatch |
| Golden test | AST dump, diagnostics, generated code |
| Integration test | Compiler kết hợp host API |
| Runtime test | Execution result và side effect |
| Property test | Formatter idempotence, parser invariant |
| Fuzz test | Input bất thường cho parser/runtime |

### 10.2 Chạy test hiện có trước khi sửa

Một test baseline giúp xác định lỗi có sẵn hay do thay đổi mới. Ghi lại command và kết quả. Nếu test không chạy vì môi trường, nêu rõ blocker thay vì kết luận code sai.

### 10.3 Golden test

Golden test so sánh output thực tế với baseline đã duyệt. Khi diff xuất hiện, xác định đó là regression hay thay đổi có chủ ý trước khi cập nhật expected file.

### 10.4 Regression fixture

Khi sửa bug, tạo test tái hiện tình huống và giữ test đó trong suite để ngăn lỗi quay lại.

### 10.5 Chất lượng test

Một test tốt có input rõ, mục tiêu cụ thể, expected result có lý do và failure message giúp khoanh vùng vấn đề.

**Mốc hoàn thành:** người học có thể thêm một test cho behavior nhỏ và giải thích test đang bảo vệ điều gì.

## 11. Thực hiện đóng góp đầu tiên

Nhiệm vụ đầu tiên nên có phạm vi nhỏ, kết quả quan sát được và ít phụ thuộc vào nhiều module.

### 11.1 Chọn loại task phù hợp

Ví dụ:

- Sửa lỗi diagnostic message.
- Bổ sung một parser fixture.
- Cập nhật tài liệu một function.
- Thêm một validation case.
- Sửa một edge case trong formatter.
- Bổ sung một test cho bug đã biết.

Tránh giao ngay một thay đổi grammar lớn, migration API hoặc refactor xuyên nhiều module cho người mới.

### 11.2 Hiểu acceptance criteria

Trước khi sửa, làm rõ:

- Hành vi hiện tại là gì?
- Hành vi mong muốn là gì?
- Input nào tái hiện vấn đề?
- Module nào sở hữu behavior?
- Test nào chứng minh hoàn thành?
- Có ảnh hưởng tương thích hoặc security không?

### 11.3 Tạo branch và thay đổi nhỏ

~~~bash
git switch -c fix/clear-diagnostic
~~~

Tách thay đổi thành một mục tiêu. Không trộn format toàn repository hoặc refactor không liên quan vào task onboarding.

### 11.4 Viết test trước hoặc cùng thay đổi

Tạo fixture tái hiện behavior. Khi sửa implementation, chạy test liên quan và xác nhận diff.

### 11.5 Review diff

Kiểm tra:

- Chỉ file cần thiết bị thay đổi.
- Không có secret hoặc file build sinh ra ngoài ý muốn.
- Test thể hiện acceptance criteria.
- Diagnostic và documentation phù hợp.
- Không thay đổi public contract ngoài dự kiến.

### 11.6 Pull request

Mô tả vấn đề, behavior trước/sau, cách kiểm tra và giới hạn còn lại. Yêu cầu reviewer phù hợp với module.

### 11.7 Tiếp nhận review

Phản hồi review bằng cách làm rõ ý định, sửa theo góp ý phù hợp và chạy lại kiểm tra sau khi thay đổi. Không coi review là đánh giá cá nhân.

**Mốc hoàn thành:** một thay đổi nhỏ được review và tích hợp theo quy trình của nhóm.

## 12. Học cách debug

Người mới cần biết cách đi từ triệu chứng đến lớp gây lỗi.

### 12.1 Bắt đầu từ reproduction

Tạo input nhỏ nhất có thể tái hiện vấn đề. Ghi command, version, configuration và actual result.

### 12.2 Xác định phase

Phân biệt lỗi lexer, parser, semantic analysis, code generation, runtime hoặc host integration. Diagnostic và stack trace thường giúp khoanh vùng.

### 12.3 Dùng debugger

Đặt breakpoint ở entry point phù hợp, xem input/output và theo dõi call stack. Không đặt breakpoint ngẫu nhiên ở quá nhiều nơi trước khi hiểu luồng xử lý.

### 12.4 Đọc structured log

Tìm execution ID, source URI, function ID, correlation ID và error code. Không đưa secret vào log khi thêm instrumentation.

### 12.5 Giảm thiểu input

Loại bỏ phần source không liên quan cho đến khi còn một case nhỏ. Input tối thiểu giúp hiểu grammar và viết regression test tốt hơn.

### 12.6 Phân biệt lỗi code và lỗi môi trường

Kiểm tra version, path, environment variable, dependency và service local. Báo cáo phải nêu bằng chứng để người hỗ trợ không phải tái tạo từ đầu.

## 13. Làm việc với tài liệu kỹ thuật

Tài liệu là một phần của sản phẩm DSL.

### 13.1 Các loại tài liệu cần biết

- Getting started.
- Language tutorial.
- Syntax/grammar reference.
- Type và function reference.
- Architecture overview.
- API/extension reference.
- Configuration guide.
- Testing guide.
- Troubleshooting.
- Security guidance.
- Release notes và migration guide.

### 13.2 Đọc theo mục tiêu

Khi cần viết một rule, đọc tutorial và syntax reference. Khi cần thêm host function, đọc API contract và extension guide. Khi cần điều tra production issue, đọc operations và incident playbook.

### 13.3 Ghi chú có thể tái sử dụng

Ghi đường dẫn file, command, module owner, test liên quan và những khái niệm mới. Không chép credential, dữ liệu khách hàng hoặc nội dung nội bộ nhạy cảm vào ghi chú cá nhân không được bảo vệ.

### 13.4 Cập nhật tài liệu cùng code

Nếu thay đổi syntax, API hoặc behavior người dùng nhìn thấy, xem xét cập nhật tutorial/reference và ví dụ. Tài liệu cũ có thể gây lỗi sử dụng dù code đúng.

## 14. Tìm kiếm trợ giúp và giao tiếp trong nhóm

Onboarding hiệu quả cần một kênh hỗ trợ rõ ràng.

### 14.1 Người hướng dẫn

Mentor giúp người mới:

- Hiểu bối cảnh và architecture.
- Chọn task đầu tiên.
- Tìm test và module owner.
- Đọc diff và diagnostic.
- Hiểu tiêu chuẩn review.
- Nhận biết khi nào cần escalation.

### 14.2 Cách đặt câu hỏi hữu ích

Một câu hỏi kỹ thuật nên có:

1. Mục tiêu đang cố đạt.
2. Bước đã thực hiện.
3. Command hoặc input đã dùng.
4. Kết quả thực tế.
5. Kết quả mong đợi.
6. Error message hoặc log đã loại bỏ dữ liệu nhạy cảm.
7. Những giả thuyết đã kiểm tra.

### 14.3 Khi nào cần báo blocker?

Báo sớm khi thiếu quyền, thiếu dependency, không thể tái tạo, acceptance criteria mơ hồ hoặc thay đổi có thể ảnh hưởng dữ liệu/production.

### 14.4 Không che giấu sự không chắc chắn

Phân biệt điều đã xác minh, điều đang suy đoán và điều cần người khác xác nhận. Cách này giúp nhóm ra quyết định chính xác hơn.

## 15. Bảo mật trong onboarding

Người mới cần hiểu các quy tắc an toàn trước khi được giao quyền chạy hoặc phát hành DSL.

### 15.1 Source không tin cậy

DSL source có thể đến từ user hoặc tenant. Không giả định source hợp lệ hoặc vô hại chỉ vì parser chấp nhận.

### 15.2 Host API capability

Chỉ cấp function và resource cần thiết. Runtime cần kiểm tra authorization khi thực thi, kể cả khi compiler đã kiểm tra trước đó.

### 15.3 Secret

Không commit secret, in token ra log hoặc đặt credential trong DSL source. Dùng secret manager hoặc cơ chế cấp credential được tổ chức hỗ trợ.

### 15.4 Tenant isolation

Hiểu cách tenant context được truyền qua compiler, runtime, worker và host service. Không dùng global mutable state cho dữ liệu tenant.

### 15.5 Dependency và plugin

Dùng dependency có nguồn gốc rõ, kiểm tra version và signature theo policy. Không cài plugin tùy ý vào môi trường có dữ liệu thật.

### 15.6 Production access

Quyền production cần được cấp theo vai trò và thời hạn. Người mới nên bắt đầu bằng local/test environment và chỉ nhận quyền cần thiết cho nhiệm vụ.

### 15.7 Incident reporting

Biết kênh báo cáo nếu phát hiện secret bị lộ, truy cập trái phép, plugin đáng ngờ hoặc dữ liệu sai lệch. Không tự xóa bằng chứng.

## 16. Release và vận hành

Ngay cả người chỉ phát triển compiler cũng cần hiểu thay đổi được phát hành và vận hành như thế nào.

### 16.1 Build artifact

Biết artifact nào được phát hành: compiler library, CLI, runtime, plugin, language server, container hoặc package.

### 16.2 Versioning

Hiểu cách version hóa public API, schema, plugin contract và DSL language version. Breaking change cần migration guide và support policy.

### 16.3 CI/CD

Nắm pipeline build, test, package, signing và deploy. Biết nơi xem kết quả và ai có quyền phê duyệt release.

### 16.4 Observability

Hiểu log, metrics, traces, diagnostics và audit. Biết cách liên kết một DSL execution với host API calls bằng execution/correlation ID.

### 16.5 Rollback

Rollback binary không nhất thiết khôi phục dữ liệu đã migrate hoặc side effect đã phát sinh. Thay đổi schema và workflow cần kế hoạch phục hồi riêng.

### 16.6 Incident response

Biết cách dừng execution, disable capability/plugin, revoke credential và báo incident theo playbook. Không tự xử lý sự cố production ngoài quyền được giao.

## 17. Lộ trình theo tuần: ví dụ 30 ngày

Một kế hoạch 30 ngày minh họa giúp chia onboarding thành các mốc nhỏ. Đây không phải thời hạn bắt buộc; mentor và người học có thể điều chỉnh theo vai trò.

| Thời gian | Trọng tâm | Hoạt động | Kết quả |
|---|---|---|---|
| Ngày 1–3 | Orientation | Tìm hiểu domain, người dùng, glossary, quy trình | Mô tả được use case |
| Ngày 4–5 | Environment | Clone, build, chạy test, cấu hình local | Môi trường hoạt động |
| Ngày 6–10 | DSL basics | Đọc và viết chương trình, tạo diagnostics | Hoàn thành bài tập DSL |
| Ngày 11–15 | Architecture | Theo dấu lexer, parser, AST và runtime | Sơ đồ một feature |
| Ngày 16–20 | Testing/debugging | Chạy fixture, golden test, tái hiện bug | Thêm một regression test |
| Ngày 21–25 | First contribution | Chọn task nhỏ, sửa, viết test, mở PR | PR được review |
| Ngày 26–30 | Ownership | Xử lý task có phạm vi rõ, trình bày kết quả | Hoàn thành với hỗ trợ giảm dần |

### 17.1 Checkpoint cuối tuần

Cuối mỗi tuần, mentor và người học trao đổi:

- Điều gì đã hoàn thành?
- Khái niệm nào còn chưa rõ?
- Blocker nào lặp lại?
- Có thể giao nhiệm vụ nào độc lập hơn?
- Tài liệu hoặc môi trường nào cần cải thiện?

### 17.2 Điều chỉnh thời gian

Người đã có kinh nghiệm compiler có thể đi nhanh qua phần lexer/parser cơ bản và dành nhiều thời gian cho domain semantics hoặc host integration. Người mới với Git/build tool có thể cần thêm thời gian ở environment setup.

## 18. Checklist hoàn thành onboarding

Checklist giúp cả người học và mentor nhìn thấy bằng chứng cụ thể.

### Bối cảnh

- [ ] Giải thích được DSL giải quyết bài toán nào.
- [ ] Biết nhóm người dùng và owner của các module.
- [ ] Hiểu các thuật ngữ domain cơ bản.

### Môi trường

- [ ] Lấy được source từ repository chính.
- [ ] Build được module liên quan.
- [ ] Chạy được test cơ bản.
- [ ] Biết nơi xem log và test report.

### Ngôn ngữ

- [ ] Viết được chương trình DSL nhỏ.
- [ ] Đọc được diagnostic và source location.
- [ ] Hiểu syntax và semantics cơ bản.

### Kiến trúc

- [ ] Tìm được lexer/parser entry point.
- [ ] Tìm được AST và semantic model.
- [ ] Biết runtime hoặc generator entry point.
- [ ] Theo dấu được một feature qua pipeline.

### Đóng góp

- [ ] Tạo được branch theo quy trình.
- [ ] Thêm hoặc sửa test phù hợp.
- [ ] Đọc và giải thích được diff.
- [ ] Mở pull request có mô tả và validation.
- [ ] Tiếp nhận và xử lý review.

### Bảo mật và vận hành

- [ ] Biết quy tắc xử lý secret.
- [ ] Hiểu capability và tenant boundary.
- [ ] Biết kênh báo incident.
- [ ] Biết quy trình release/rollback liên quan vai trò.

Không nên đánh dấu hoàn thành chỉ dựa trên việc đã đọc tài liệu. Mỗi mục cần có bằng chứng phù hợp.

## 19. Đánh giá năng lực mà không biến onboarding thành kỳ thi

Đánh giá nên phục vụ việc xác định hỗ trợ tiếp theo.

### 19.1 Quan sát qua nhiệm vụ

Quan sát người học thực hiện một task thật có phạm vi nhỏ. Ghi nhận khả năng tìm module, chọn test, giải thích diff và giao tiếp blocker.

### 19.2 Mức độ hỗ trợ

Có thể dùng các mức:

- **Guided:** cần mentor hướng dẫn từng bước.
- **Supported:** tự làm phần lớn, cần trao đổi ở quyết định quan trọng.
- **Independent:** tự xử lý nhiệm vụ thông thường và báo cáo rõ.
- **Owner:** có thể hướng dẫn người khác hoặc chịu trách nhiệm một khu vực.

Đây là mô tả mức hỗ trợ, không phải đánh giá giá trị cá nhân.

### 19.3 Không đánh giá chỉ bằng tốc độ

Một người hoàn thành nhanh nhưng bỏ qua test, security hoặc review chưa chắc đã sẵn sàng làm độc lập. Chất lượng giải thích, khả năng tái lập và judgment quan trọng không kém thời gian.

### 19.4 Phản hồi hai chiều

Người học cũng nên đánh giá tài liệu, setup và mức độ rõ của task. Onboarding là quy trình của tổ chức cần được cải tiến liên tục.

## 20. Vai trò của mentor và team

Mentor không chỉ trả lời câu hỏi; họ giúp người mới tiếp cận đúng kiến thức theo đúng thời điểm.

### 20.1 Trước ngày bắt đầu

- Chuẩn bị quyền repository và công cụ.
- Chọn tài liệu bắt đầu.
- Chọn một task nhỏ.
- Xác định mentor và kênh hỗ trợ.
- Kiểm tra môi trường phát triển.

### 20.2 Trong tuần đầu

- Giới thiệu domain và architecture.
- Hỗ trợ build/test lần đầu.
- Cùng chạy một ví dụ DSL.
- Giải thích quy trình Git/review.
- Giúp xử lý blocker môi trường.

### 20.3 Trong các tuần tiếp theo

- Chuyển dần từ demo sang nhiệm vụ thật.
- Review thay đổi sớm.
- Giải thích lý do của góp ý.
- Giảm hỗ trợ khi người học đã tự tin.
- Ghi nhận tài liệu còn thiếu.

### 20.4 Hạn chế phụ thuộc vào một người

Tài liệu và ownership cần đủ rõ để người học có thể nhận hỗ trợ từ nhiều thành viên. Không để kiến thức thiết yếu chỉ nằm trong trí nhớ của một mentor.

## 21. Tùy biến lộ trình theo vai trò

### 21.1 Domain expert hoặc DSL author

Ưu tiên:

1. Domain glossary và business rules.
2. Syntax tutorial và language reference.
3. Cách viết, chạy và debug DSL.
4. Validation và diagnostic.
5. Review thay đổi rule và migration.
6. Security boundary của các function được phép.

Bài thực hành phù hợp là viết một rule nghiệp vụ, tạo một trường hợp sai và giải thích kết quả.

### 21.2 Compiler engineer

Ưu tiên:

1. Grammar và token model.
2. Parser và AST.
3. Scope, symbol và type system.
4. IR và compiler passes.
5. Diagnostics và source mapping.
6. Golden/regression test.
7. Generator hoặc backend.

Bài thực hành phù hợp là thêm một parser/semantic test cho cú pháp hoặc type rule đã có.

### 21.3 Runtime/application developer

Ưu tiên:

1. Execution model.
2. Host API và function registry.
3. Context, permission và tenant isolation.
4. Transaction, retry và idempotency.
5. Async, cancellation và timeout.
6. Observability và incident response.

Bài thực hành phù hợp là tích hợp một host function read-only với contract và test rõ.

### 21.4 Plugin developer

Ưu tiên:

1. Extension descriptor.
2. Plugin API và version.
3. Registration và lifecycle.
4. Capability và permission.
5. Class loading/dependency.
6. Compatibility test.

Bài thực hành phù hợp là viết một plugin nhỏ đăng ký capability an toàn và dispose đúng cách.

### 21.5 QA/test engineer

Ưu tiên:

1. Language behavior và acceptance criteria.
2. Fixture organization.
3. Golden test và approval flow.
4. Property/fuzz test.
5. Integration và runtime test.
6. CI failure triage.

Bài thực hành phù hợp là thêm fixture cho một edge case và giải thích vì sao baseline mong đợi đúng.

## 22. Các blocker thường gặp trong onboarding

### Không biết bắt đầu từ đâu

**Cách xử lý:** đưa một bản đồ repository, một ví dụ DSL chạy được và một task đầu tiên có acceptance criteria rõ.

### Build không chạy

**Cách xử lý:** xác nhận JDK, build wrapper, dependency access và environment variable; thu thập output đầy đủ của command.

### Không hiểu diagnostic

**Cách xử lý:** liên kết diagnostic code với grammar/type rule và cho người học xem input tối thiểu tái hiện.

### Test fail nhưng không biết thuộc phase nào

**Cách xử lý:** chạy test theo module, xác định actual output và lần theo pipeline.

### Không rõ API nào được hỗ trợ

**Cách xử lý:** hỏi module owner, xem public contract và extension documentation; không dựa vào implementation detail chưa được bảo đảm.

### Không có quyền cần thiết

**Cách xử lý:** yêu cầu quyền theo quy trình, ghi rõ resource và mục đích. Không chia sẻ credential của người khác.

### Task quá lớn

**Cách xử lý:** chia thành bước tìm hiểu, reproduction, test, implementation và review. Mentor điều chỉnh scope.

### Tài liệu không khớp code

**Cách xử lý:** ghi version và ví dụ không còn đúng, hỏi owner xác nhận rồi cập nhật tài liệu theo quy trình.

## 23. Duy trì và cải tiến chương trình onboarding

Onboarding cần được xem như một phần của sản phẩm kỹ thuật.

### 23.1 Đo lường

Có thể theo dõi:

- Thời gian đến lần build/test thành công đầu tiên.
- Thời gian đến đóng góp đầu tiên được review.
- Số blocker môi trường lặp lại.
- Tỷ lệ hoàn thành các learning milestone.
- Số lần phải sửa lại vì thiếu hướng dẫn.
- Mức độ hữu ích của tài liệu theo phản hồi.

Không dùng metrics để tạo áp lực hoặc so sánh cá nhân thiếu ngữ cảnh.

### 23.2 Cập nhật khi kiến trúc thay đổi

Khi compiler, runtime, API hoặc build process thay đổi, cập nhật sơ đồ, command và ví dụ onboarding.

### 23.3 Dùng lỗi thật làm bài học

Các bug đã được giải quyết có thể trở thành bài tập regression hoặc troubleshooting, sau khi loại bỏ dữ liệu nhạy cảm.

### 23.4 Giữ ví dụ chạy được

Ví dụ DSL và code snippet cần được kiểm tra theo version phù hợp. Tài liệu có code lỗi thời sẽ làm mất thời gian của người mới.

### 23.5 Thu thập phản hồi

Sau mỗi đợt onboarding, hỏi phần nào khó hiểu, bước nào bị chặn, tài liệu nào thiếu và task đầu tiên có phù hợp không. Chuyển phản hồi thành action có owner.

## 24. Mẫu kế hoạch onboarding cá nhân

Một kế hoạch ngắn có thể ghi:

~~~text
Learner:
Role:
Start date:
Mentor:
Primary module:

Learning goals:
1.
2.
3.

Environment:
- Repository access:
- Toolchain:
- Build command:
- Test command:

Practice tasks:
1. Run an existing DSL example.
2. Trace one feature through the compiler/runtime.
3. Add one focused test.
4. Complete one small contribution.

Support:
- Team channel:
- Module owner:
- Escalation contact:

Milestones:
- Environment ready:
- DSL exercise complete:
- Architecture walkthrough:
- First review:
- Independent task:

Open questions / blockers:
Next check-in:
~~~

Đây là mẫu để mentor và người học cùng điền. Không cần tạo thêm tài liệu hành chính nếu nhóm đã có công cụ onboarding phù hợp.

## 25. Ví dụ tổng hợp: onboarding một developer vào dự án DSL

Giả sử một developer mới tham gia nhóm xây dựng DSL cho quy trình phê duyệt đơn hàng.

### Ngày đầu: hiểu bài toán

Mentor giải thích người dùng viết policy, runtime đánh giá policy khi đơn hàng được gửi và host API cung cấp dữ liệu đơn hàng cùng lệnh phê duyệt. Developer đọc một ví dụ hợp lệ và một ví dụ có type error.

### Ngày 2–3: thiết lập môi trường

Developer lấy repository, cài toolchain theo hướng dẫn, build module compiler và chạy một parser test. Nếu build fail, ghi lại command và lỗi để mentor hỗ trợ.

### Ngày 4–7: sử dụng DSL

Developer viết policy kiểm tra giá trị đơn hàng, thêm một điều kiện và tạo trường hợp tham chiếu field không tồn tại. Họ đọc diagnostic và xác định source range.

### Tuần 2: theo dấu kiến trúc

Developer tìm token cho keyword, parser rule, AST node, semantic validation và runtime evaluator. Họ vẽ sơ đồ ngắn cho một function call.

### Tuần 3: đóng góp đầu tiên

Một diagnostic có message chưa rõ. Developer tạo fixture, xác nhận output hiện tại, sửa message hoặc mapping, cập nhật golden file nếu behavior text là contract và mở pull request.

### Tuần 4: làm nhiệm vụ độc lập

Developer nhận một task nhỏ về validation, xác định acceptance criteria, thêm test, sửa implementation, mô tả kết quả và xử lý review.

### Kết quả

Developer có thể tự tìm module, chạy test, tạo reproduction, thực hiện thay đổi nhỏ và biết khi nào cần hỏi owner. Mentor tiếp tục hỗ trợ các phần chuyên sâu như host API hoặc release khi công việc yêu cầu.

## 26. Câu hỏi tự kiểm tra

1. Onboarding trong một dự án DSL cần đạt những kết quả quan sát được nào?
2. Vì sao cần hiểu domain trước khi đọc compiler source?
3. Common core và role-specific learning khác nhau như thế nào?
4. Một môi trường phát triển DSL cần những thành phần nào?
5. Người mới nên học syntax và semantics theo thứ tự nào?
6. Làm sao theo dấu một feature từ source đến runtime?
7. Những module nào cần có trong bản đồ repository?
8. Vì sao nên chạy test hiện có trước khi sửa code?
9. Golden test giúp người mới hiểu regression như thế nào?
10. Một task đầu tiên tốt cần những đặc điểm nào?
11. Acceptance criteria giúp giới hạn scope ra sao?
12. Một báo cáo blocker hữu ích cần thông tin gì?
13. Vì sao source DSL cần được xem là input không tin cậy?
14. Host API capability và tenant isolation liên quan onboarding thế nào?
15. Mentor nên hỗ trợ trong tuần đầu và giảm hỗ trợ ra sao?
16. Lộ trình của compiler engineer khác domain expert ở điểm nào?
17. Cần quan sát những gì trước khi giao một task độc lập?
18. Vì sao onboarding cần cập nhật khi architecture thay đổi?
19. Những metrics nào có thể giúp cải tiến onboarding mà không tạo áp lực sai lệch?
20. Một kế hoạch onboarding cá nhân nên ghi những milestone nào?

Lộ trình onboarding giúp người mới chuyển từ hiểu bối cảnh sang sử dụng DSL, khám phá kiến trúc, kiểm thử và đóng góp vào dự án. Khi mục tiêu rõ, môi trường tái lập được, nhiệm vụ tăng dần theo vai trò và có mentor cùng tài liệu hỗ trợ, thành viên mới có thể làm việc độc lập với hiểu biết đúng về chất lượng, bảo mật và quy trình phát hành.
