# Quy trình đóng góp

Một DSL (Domain-Specific Language) thường được phát triển qua nhiều thành phần: grammar, parser, compiler, metamodel, runtime, editor, generator, tài liệu và ví dụ. Khi người dùng phát hiện lỗi, cần cú pháp mới hoặc muốn cải thiện tooling, họ có thể đóng góp thay đổi cho dự án. **Quy trình đóng góp (contribution process)** là tập bước và quy tắc giúp cộng đồng gửi, thảo luận, review, kiểm thử và tích hợp những thay đổi đó một cách minh bạch.

Quy trình tốt giúp người đóng góp biết bắt đầu từ đâu, cần chuẩn bị gì, thay đổi nào cần đề xuất thiết kế trước, cách chạy test và cách gửi pull request. Maintainer có cơ sở đánh giá tính đúng đắn, khả năng tương thích, chất lượng tài liệu, bảo mật và chi phí bảo trì. Với DSL, đóng góp còn cần xem xét ảnh hưởng đến source compatibility, semantics, generated output và dữ liệu người dùng đang lưu.

## 1. Quy trình đóng góp là gì?

Quy trình đóng góp mô tả cách một thay đổi đi từ ý tưởng đến bản phát hành. Nó thường bao gồm:

- Tìm hiểu dự án, kiến trúc và quy tắc cộng đồng.
- Tìm issue hoặc mở đề xuất mới.
- Thảo luận phạm vi và thiết kế.
- Chuẩn bị môi trường phát triển.
- Tạo branch và thực hiện thay đổi.
- Viết hoặc cập nhật tests.
- Cập nhật documentation và examples.
- Gửi pull request.
- Review, sửa đổi và kiểm tra CI.
- Merge, phát hành và ghi nhận đóng góp.

~~~text
Idea / Bug report
       |
       v
Issue discussion
       |
       v
Design agreement
       |
       v
Implementation + tests + docs
       |
       v
Pull request
       |
       v
Review and CI
       |
       v
Merge
       |
       v
Release / Changelog
~~~

### 1.1. Đóng góp không chỉ là code

Một đóng góp có thể là báo lỗi, cải thiện tài liệu, bổ sung ví dụ, viết test, đề xuất grammar, trả lời câu hỏi, cải thiện accessibility hoặc giúp review pull request. Những đóng góp này đều có giá trị nếu tuân theo quy tắc dự án.

### 1.2. Maintainer và contributor

Contributor đề xuất và thực hiện thay đổi. Maintainer chịu trách nhiệm định hướng dự án, review, bảo vệ chất lượng và quyết định tích hợp. Một contributor có thể trở thành maintainer sau khi xây dựng được lịch sử đóng góp và được cộng đồng tin tưởng theo governance của dự án.

### 1.3. Quy trình cần tương xứng với rủi ro

Sửa lỗi chính tả trong tài liệu không cần quy trình thiết kế như thay đổi type system hoặc grammar public. Quy trình nên phân loại thay đổi để không tạo thủ tục nặng cho việc nhỏ, đồng thời bảo đảm thay đổi có ảnh hưởng rộng được xem xét đầy đủ.

## 2. Đối tượng có thể đóng góp

Một dự án DSL có nhiều vùng mà cộng đồng có thể cải thiện.

| Khu vực | Ví dụ đóng góp |
|---|---|
| Grammar | Thêm syntax, sửa precedence, cải thiện error recovery |
| Parser/AST | Sửa node construction, source ranges hoặc visitor |
| Semantic analysis | Scope, type checking, validation |
| Runtime | Built-in functions, execution behavior |
| Code generator | Target backend, template, optimization |
| Editor/tooling | Completion, hover, diagnostics, rename |
| Language server | LSP features, cancellation, incremental updates |
| API/schema | Contract, serialization, compatibility |
| Documentation | Tutorial, reference, migration guide |
| Examples | Sample project, fixture, use case |
| Build/CI | Test pipeline, reproducible build, packaging |
| Security | Audit, permission checks, dependency updates |

### 2.1. Bug reports

Bug report mô tả hành vi sai, điều kiện tái hiện và kết quả mong đợi. Một báo cáo tốt giúp maintainer xác nhận lỗi mà không phải đoán môi trường hoặc viết lại toàn bộ chương trình.

### 2.2. Feature requests

Feature request mô tả vấn đề cần giải quyết, người dùng bị ảnh hưởng và kết quả mong muốn. Không nên chỉ nêu một implementation cụ thể nếu còn nhiều cách thiết kế có thể đáp ứng nhu cầu.

### 2.3. Documentation contributions

Tài liệu có thể cần cập nhật khi grammar, runtime hoặc semantics thay đổi. Người dùng thường phát hiện những chỗ khó hiểu khi họ cố làm theo hướng dẫn; phản hồi đó giúp tài liệu tốt hơn.

### 2.4. Community support

Trả lời câu hỏi, phân loại issue, tạo minimal reproduction và review ví dụ cũng là đóng góp. Cần khuyến khích trao đổi tôn trọng và tránh yêu cầu người dùng công khai dữ liệu nhạy cảm.

## 3. Đọc hướng dẫn và hiểu dự án trước khi sửa

Trước khi tạo thay đổi, contributor nên tìm hiểu cấu trúc repository và các tài liệu đóng góp mà dự án công bố.

Thông tin cần đọc:

- README và giới thiệu mục tiêu dự án.
- CONTRIBUTING guide hoặc developer guide.
- Code of Conduct.
- License và chính sách bản quyền.
- Architecture overview.
- Test instructions.
- Coding style và commit convention.
- Release policy và compatibility policy.
- Security reporting policy.
- Issue templates và pull request template.

### 3.1. Xác định đúng repository và module

Một DSL có thể chia thành grammar, runtime, IDE, language server và generator modules. Cần xác định module sở hữu hành vi cần sửa để tránh thay đổi nhầm lớp.

### 3.2. Kiểm tra issue hiện có

Trước khi mở issue mới, tìm kiếm theo keyword, error code và module. Issue trùng có thể đã có discussion hoặc workaround. Contributor có thể bổ sung reproduction vào issue hiện có.

### 3.3. Tìm người phụ trách

Một số dự án có CODEOWNERS hoặc module maintainers. Biết đúng người review giúp tránh thay đổi lớn bị gửi vào sai khu vực.

### 3.4. Không đoán quy tắc chưa được công bố

Nếu license, commit signing, CLA/DCO hoặc test command chưa rõ, hỏi maintainer qua kênh chính thức. Không nên tự áp dụng quy tắc từ một dự án khác.

## 4. Báo lỗi có thể tái hiện

Bug report nên cung cấp thông tin đủ để người khác tái hiện.

Một báo cáo hữu ích gồm:

1. Phiên bản compiler/runtime/tooling.
2. Hệ điều hành và JDK/runtime version nếu liên quan.
3. DSL source tối thiểu gây lỗi.
4. Lệnh hoặc thao tác để tái hiện.
5. Kết quả thực tế.
6. Kết quả mong đợi.
7. Diagnostic hoặc stack trace đã loại bỏ secret.
8. Có thể xảy ra thường xuyên hay không.
9. Có workaround nào không.
10. Mức độ ảnh hưởng và môi trường bị ảnh hưởng.

Ví dụ minimal reproduction:

~~~text
type Money {
    amount: Decimal
}

let total: Money = 10
~~~

Nếu lỗi xảy ra khi gán literal số cho Money, hãy cung cấp đúng file nhỏ này cùng compiler version và diagnostic. Không cần đính kèm toàn bộ repository nếu một fixture ngắn đã thể hiện lỗi.

### 4.1. Tách lỗi khỏi môi trường

Thử trên project mới hoặc cấu hình tối thiểu để xác định lỗi có đến từ plugin, cache, dependency hoặc code riêng của ứng dụng không.

### 4.2. Giữ dữ liệu an toàn

Không đưa token, password, customer data hoặc source độc quyền vào issue công khai. Thay bằng dữ liệu giả có cấu trúc tương tự.

### 4.3. Phân biệt bug và feature request

Nếu hành vi hiện tại phù hợp tài liệu nhưng người dùng muốn hành vi khác, đó có thể là feature request hoặc design proposal chứ không phải bug.

## 5. Đề xuất tính năng và thay đổi thiết kế

Thay đổi grammar hoặc semantics có thể ảnh hưởng nhiều dự án. Với thay đổi lớn, nên có proposal hoặc RFC trước khi viết code.

Một proposal có thể gồm:

- Vấn đề hiện tại và use cases.
- Đối tượng người dùng bị ảnh hưởng.
- Thiết kế đề xuất.
- Các phương án đã cân nhắc.
- Ví dụ syntax trước/sau.
- AST/metamodel impact.
- Semantic rules và error behavior.
- Compatibility và migration.
- Ảnh hưởng runtime/generator/tooling.
- Test plan và documentation plan.
- Các rủi ro hoặc câu hỏi còn mở.

### 5.1. Bắt đầu từ use case

Một proposal tốt cho thấy người dùng cần biểu đạt điều gì và vì sao cú pháp hiện tại không đáp ứng được. Tránh bắt đầu bằng một keyword mới mà chưa giải thích vấn đề.

### 5.2. Ví dụ syntax

Nếu đề xuất grammar, cần có ví dụ hợp lệ, không hợp lệ, lồng nhau và trường hợp biên. Ví dụ giúp cộng đồng thảo luận semantics thay vì tranh luận chỉ dựa vào tên keyword.

### 5.3. Các lựa chọn thiết kế

Mô tả ít nhất phương án được đề xuất và những trade-off quan trọng. Ví dụ cú pháp ngắn có thể dễ viết nhưng gây ambiguity; cú pháp tường minh có thể dài hơn nhưng dễ parse và đọc.

### 5.4. Consensus và quyết định

Maintainer hoặc nhóm governance cần ghi lại quyết định, lý do và các điểm chưa giải quyết. Discussion nên có kết luận rõ để contributor biết phạm vi implementation được chấp nhận.

### 5.5. Thay đổi lớn không nên bắt đầu bằng pull request bất ngờ

Một pull request lớn có thể tốn nhiều công review nếu thiết kế chưa được đồng thuận. Với thay đổi public API hoặc grammar, thảo luận trước giúp giảm công việc bị bỏ đi.

## 6. Chuẩn bị môi trường phát triển

Sau khi issue hoặc proposal được xác định, contributor cần tạo môi trường build có thể lặp lại.

Các bước thường gặp:

1. Clone repository.
2. Checkout branch hoặc commit phù hợp.
3. Cài JDK/runtime/toolchain theo hướng dẫn.
4. Resolve dependencies.
5. Chạy build baseline.
6. Chạy test hiện có.
7. Import project vào IDE nếu cần.
8. Tạo branch riêng cho thay đổi.

### 6.1. Dùng đúng toolchain

DSL framework có thể phụ thuộc phiên bản Java, Gradle/Maven, EMF, parser generator hoặc target SDK. Dùng version khác có thể tạo lỗi không liên quan đến thay đổi.

### 6.2. Chạy baseline trước khi sửa

Nếu test đã fail trước khi thay đổi, cần ghi nhận điều đó. Baseline giúp phân biệt lỗi có sẵn với regression do patch.

### 6.3. Dependency và cache

Không nên thay đổi dependency chỉ để xử lý lỗi cache cục bộ. Nếu cần cập nhật dependency, phải nêu lý do và kiểm tra ảnh hưởng tương thích.

### 6.4. Local configuration

IDE settings, credentials và file local không nên được commit nếu không thuộc project contract. Kiểm tra status trước khi tạo commit.

## 7. Tạo branch và tổ chức thay đổi

Một branch riêng giúp cô lập contribution và review dễ hơn.

Tên branch có thể thể hiện issue hoặc mục tiêu:

~~~text
fix/parser-expression-precedence
feature/workflow-timeout-syntax
docs/api-pagination-guide
~~~

### 7.1. Một mục tiêu chính cho mỗi pull request

Pull request nên giải quyết một mục tiêu có thể review. Trộn refactor lớn, formatting toàn repository và feature mới khiến reviewer khó xác định thay đổi thực sự.

### 7.2. Commit nhỏ và có ý nghĩa

Commit nên chia theo bước logic: parser change, semantic validation, tests, documentation. Lịch sử rõ giúp bisect và revert khi cần.

### 7.3. Tránh commit generated noise

Nếu generated code được tạo từ grammar hoặc model, chỉ commit theo policy của repository. Không nên đưa toàn bộ output thay đổi không liên quan vào patch.

### 7.4. Giữ patch gọn

Không reformat hoặc rename file ngoài phạm vi nếu không cần thiết. Patch nhỏ giúp review và cherry-pick dễ hơn.

### 7.5. Đồng bộ branch

Nếu branch chính thay đổi, rebase hoặc merge theo hướng dẫn dự án. Giải quyết conflict có chủ đích và chạy lại test bị ảnh hưởng.

## 8. Thực hiện thay đổi grammar và parser

Đóng góp vào grammar cần xem xét nhiều hơn việc parser chấp nhận một chuỗi mới.

### 8.1. Grammar rules

Thêm parser rule, terminal hoặc keyword cần kiểm tra ambiguity, precedence, associativity, hidden tokens và error recovery.

### 8.2. Backward compatibility

Một keyword mới có thể trùng với identifier mà người dùng cũ đang dùng. Cần kiểm tra source compatibility và đề xuất deprecation hoặc escaping nếu có xung đột.

### 8.3. AST/metamodel changes

Grammar có thể tạo hoặc thay đổi node types, attributes và references. Các visitor, validator, serializer và generator có thể cần cập nhật.

### 8.4. Error diagnostics

Parser nên báo lỗi ở vị trí hữu ích và tránh tạo diagnostic khó hiểu cho cú pháp phổ biến. Thêm syntax mới cũng cần test các input gần đúng nhưng không hợp lệ.

### 8.5. Generated parser

Nếu parser hoặc model code được sinh, cần chạy workflow generation theo hướng dẫn. Không sửa trực tiếp output generated để che lỗi trong grammar.

## 9. Thay đổi semantic analysis và runtime

Thay đổi semantics có thể ảnh hưởng behavior dù AST không đổi.

Các khu vực thường gặp:

- Name resolution và scope.
- Type inference và type checking.
- Overload resolution.
- Constant evaluation.
- Validation rules.
- Runtime execution.
- Error handling.
- Transaction và side effects.
- Event/workflow behavior.

### 9.1. Viết rõ semantic contract

Ví dụ, nếu thêm toán tử null-coalescing, cần định nghĩa short-circuit behavior, precedence, type rules và cách xử lý optional values.

### 9.2. Không thay đổi behavior ngầm

Một optimization không được làm thay đổi kết quả nếu DSL contract yêu cầu semantics cũ. Cần test side effects, evaluation order và error behavior.

### 9.3. Runtime compatibility

Nếu generated code gọi runtime API mới, cần xác định runtime version tối thiểu và cách consumer nâng cấp.

### 9.4. Diagnostics và error codes

Diagnostic code ổn định có thể được IDE, CI hoặc tooling khác sử dụng. Thay đổi message không nhất thiết phải đổi code; thay đổi semantics cần review compatibility.

## 10. Kiểm thử cho contribution

Mỗi thay đổi cần có test tương xứng với tác động.

| Loại thay đổi | Test thường cần |
|---|---|
| Grammar/parser | Valid/invalid fixtures, AST structure |
| AST model | Node types, containment, source ranges |
| Resolver/scope | Imports, shadowing, ambiguity |
| Type checker | Valid/invalid type cases |
| Runtime | Unit và behavior tests |
| Generator | Golden output, target compilation |
| Language server | LSP request/response và cancellation |
| API/schema | Contract tests và compatibility checks |
| Documentation | Link, code sample và schema validation |
| Build/packaging | Clean build và artifact checks |

### 10.1. Regression test

Nếu contribution sửa bug, nên thêm test tái hiện lỗi trước khi fix. Test cần fail trên behavior cũ và pass sau patch.

### 10.2. Boundary cases

Với parser, test nesting sâu, Unicode, empty input và incomplete input. Với type system, test nullability, generic bounds và overload ambiguity. Với runtime, test retry, cancellation và error paths.

### 10.3. Test generated artifacts

Nếu generator thay đổi, test output và compile/run artifact khi phù hợp. Một snapshot đơn thuần không chứng minh target code hoạt động.

### 10.4. Không làm test phụ thuộc môi trường cá nhân

Dùng fixture, fake clock, temporary directory và test service. Tránh hard-code absolute path, credential hoặc thứ tự collection không ổn định.

### 10.5. Chạy đúng test suite

Contributor nên chạy các test liên quan và lệnh kiểm tra bắt buộc được project công bố. Nếu không thể chạy một suite, cần nêu rõ lý do trong pull request thay vì khẳng định đã kiểm tra.

## 11. Cập nhật tài liệu và ví dụ

Thay đổi public behavior thường cần cập nhật docs.

Tài liệu có thể cần sửa:

- Grammar reference.
- Language concepts.
- API reference.
- Error catalog.
- Tutorial hoặc how-to guide.
- Migration guide.
- Release notes.
- Example projects.
- IDE/language server documentation.

### 11.1. Ví dụ phải phản ánh syntax mới

Nếu thêm cú pháp, cập nhật sample để người dùng không học cách viết đã deprecated.

### 11.2. Breaking changes cần migration notes

Nếu source cũ không còn tương thích, nêu version, before/after và công cụ chuyển đổi nếu có.

### 11.3. Không chỉ sửa code sample

Một thay đổi semantics có thể yêu cầu cập nhật mô tả, diagram, default values và error behavior. Tài liệu phải giải thích hành vi thực tế chứ không chỉ cú pháp.

### 11.4. Documentation examples as tests

Nếu có thể, dùng ví dụ trong docs làm parser/compile fixture. Cách này giúp phát hiện tài liệu lỗi khi grammar thay đổi.

## 12. Coding style và chất lượng patch

Coding style giúp repository nhất quán và giảm chi phí review.

Contributor nên tuân theo:

- Naming conventions.
- Formatting và lint rules.
- Error handling conventions.
- Logging policy.
- Nullability/immutability conventions.
- Package/module boundaries.
- Comment và documentation style.
- Test naming và fixture organization.

### 12.1. Giữ code dễ đọc

Ưu tiên tên thể hiện ý nghĩa domain, hàm có trách nhiệm rõ và abstraction phù hợp. Không tạo framework tổng quát cho một trường hợp nhỏ nếu chưa có nhu cầu.

### 12.2. Không thêm dependency tùy tiện

Dependency mới làm tăng bề mặt bảo trì, security scanning và compatibility. Pull request nên giải thích lý do, kích thước và lựa chọn thay thế.

### 12.3. Không che lỗi bằng catch-all

Bắt mọi exception rồi bỏ qua có thể làm compiler hoặc runtime tiếp tục với trạng thái sai. Lỗi cần được xử lý hoặc truyền tiếp theo policy.

### 12.4. Performance

Parser/compiler thường chạy trên nhiều file. Tránh thuật toán có chi phí tăng quá nhanh, repeated full scans hoặc giữ AST/resource lâu hơn cần thiết. Nếu thay đổi ảnh hưởng performance, cung cấp benchmark hoặc phân tích phù hợp.

## 13. Commit message và pull request

Pull request là đơn vị review và tích hợp. Mô tả cần giúp reviewer hiểu vấn đề, hành vi sau thay đổi và bằng chứng kiểm tra.

Một pull request thường gồm:

- Tiêu đề ngắn và cụ thể.
- Issue hoặc proposal liên quan.
- Vấn đề hiện tại.
- Hành vi mới hoặc bug được sửa.
- Phạm vi thay đổi.
- Các quyết định kỹ thuật quan trọng.
- Tests đã chạy.
- Documentation đã cập nhật.
- Breaking changes hoặc migration notes.
- Screenshot/log khi UI hoặc diagnostics thay đổi.

### 13.1. Commit message

Commit subject nên mô tả hành động và phạm vi. Nếu dự án dùng Conventional Commits hoặc convention khác, cần tuân theo. Không tự đưa convention mới nếu repository đã có quy định.

### 13.2. Pull request description

Nên có ví dụ before/after khi thay đổi syntax hoặc behavior. Reviewer cần thấy trigger cụ thể và kết quả mới.

### 13.3. Liên kết issue

Link issue giúp hiểu bối cảnh và tránh phải chép lại toàn bộ thảo luận. Nếu không có issue, mô tả lý do thay đổi và use case.

### 13.4. Draft pull request

Draft PR phù hợp khi muốn nhận phản hồi sớm về hướng thiết kế hoặc đang triển khai chưa hoàn tất. Trạng thái draft phải nói rõ phần nào còn thiếu.

### 13.5. Không gửi secret hoặc generated binary ngoài policy

Trước khi push, kiểm tra diff, ignored files, credential, log và artifact. Nếu lỡ đưa secret vào history, xóa file trong commit mới không đủ; cần thu hồi/rotate secret và xử lý lịch sử theo quy trình bảo mật.

## 14. Review và phản hồi

Code review kiểm tra correctness, maintainability, compatibility, security và sự phù hợp với mục tiêu dự án.

Reviewer có thể xem xét:

- Thay đổi có giải quyết đúng issue không?
- Grammar có ambiguity hoặc conflict không?
- AST/model có invariant rõ không?
- Semantics có nhất quán không?
- Test có bao phủ regression và edge cases không?
- Generated code có được cập nhật đúng cách không?
- Documentation có phản ánh behavior không?
- API có breaking change không?
- Dependency/security impact ra sao?
- Performance và memory có bị ảnh hưởng không?

### 14.1. Review comments

Comment nên cụ thể, chỉ ra dòng hoặc hành vi và giải thích rủi ro. Phân biệt blocker, suggestion và câu hỏi để contributor biết việc nào cần sửa trước merge.

### 14.2. Trả lời review

Contributor nên trả lời từng điểm, cập nhật patch hoặc giải thích quyết định bằng bằng chứng. Nếu không đồng ý, thảo luận trên semantics và project policy thay vì cá nhân hóa bất đồng.

### 14.3. Resolve conversations

Chỉ resolve thread khi vấn đề đã được xử lý hoặc reviewer đồng ý. Không nên đóng discussion chỉ để làm PR trông sạch.

### 14.4. Review nhiều vòng

Một pull request có thể cần nhiều vòng review. Lịch sử thay đổi nên giữ rõ lý do điều chỉnh; nếu patch đã đổi hướng đáng kể, cập nhật PR description.

### 14.5. Maintainer capacity

Review có thể mất thời gian do ưu tiên và năng lực maintainer. Contributor nên giữ PR nhỏ, trả lời rõ và tránh gửi nhiều lần ping không cần thiết.

## 15. CI và điều kiện merge

Continuous Integration chạy các kiểm tra tự động trên pull request.

Các gate có thể gồm:

- Build thành công.
- Unit/integration tests đạt.
- Formatter/linter sạch.
- Parser và grammar generation thành công.
- API/schema compatibility checks.
- Generated artifacts không lệch source.
- Security/dependency scans.
- Documentation build và link checks.
- Required approvals.
- Branch protection requirements.

### 15.1. CI fail

Nếu CI fail, đọc log để xác định lỗi do patch, hạ tầng hay test flaky. Không nên rerun liên tục mà không hiểu nguyên nhân.

### 15.2. Required checks

Một số check bắt buộc mới cho phép merge. Contributor cần biết rõ check nào required và không tìm cách bỏ qua chúng.

### 15.3. Flaky tests

Nếu phát hiện flaky test, mở issue hoặc cung cấp reproduction. Không xóa test hoặc làm test yếu đi chỉ để CI xanh.

### 15.4. Generated files

Nếu repository yêu cầu commit generated output, CI có thể chạy generator rồi kiểm tra diff. Nếu generated output không được commit, CI vẫn có thể build để bảo đảm source generation thành công.

## 16. License, DCO/CLA và nguồn gốc đóng góp

Đóng góp phần mềm cần tuân thủ license của dự án và quy tắc xác nhận quyền đóng góp.

### 16.1. License

Contributor cần biết dự án phát hành theo license nào và nội dung được đóng góp có thể phân phối theo license đó hay không. Không sao chép code hoặc tài liệu từ nguồn không rõ quyền sử dụng.

### 16.2. DCO

Một số dự án dùng Developer Certificate of Origin để contributor xác nhận có quyền gửi đóng góp, thường thông qua sign-off commit. Chỉ thực hiện nếu repository yêu cầu.

### 16.3. CLA

Một số tổ chức yêu cầu Contributor License Agreement. Nếu có, cần hoàn tất theo hướng dẫn chính thức trước khi merge.

### 16.4. Third-party code

Nếu thêm thư viện hoặc đoạn code từ bên ngoài, ghi rõ nguồn, license và điều kiện sử dụng. Không đưa dependency có license không tương thích mà không được review.

### 16.5. Generated content

Code sinh tự động từ schema hoặc tool có thể có license/notice riêng. Cần tuân thủ policy của generator và giữ attribution khi cần.

## 17. Code of Conduct và cộng đồng an toàn

Quy trình đóng góp cần bảo đảm mọi người có thể tham gia trong môi trường tôn trọng.

Các nguyên tắc phổ biến:

- Trao đổi lịch sự và tập trung vào vấn đề.
- Không công kích cá nhân hoặc quấy rối.
- Chấp nhận ý kiến khác biệt.
- Không tiết lộ thông tin cá nhân hoặc bí mật.
- Phản hồi hành vi vi phạm qua kênh được công bố.
- Maintainer xử lý khiếu nại theo quy trình công bằng.

Code of Conduct nên có phạm vi áp dụng, kênh báo cáo, người xử lý và cách bảo mật thông tin. Người báo cáo không nên bị trả đũa vì nêu vấn đề một cách thiện chí.

## 18. Báo cáo lỗ hổng bảo mật

Lỗ hổng bảo mật không nên được công bố công khai trước khi có cơ hội xử lý.

### 18.1. Security reporting channel

Dự án nên công bố kênh riêng như security advisory hoặc email bảo mật. Không gửi exploit hoặc dữ liệu nhạy cảm trong issue công khai.

### 18.2. Phạm vi thông tin

Báo cáo cần mô tả thành phần, phiên bản bị ảnh hưởng, điều kiện tái hiện và tác động. Chỉ chia sẻ chi tiết khai thác cần thiết với người xử lý.

### 18.3. Coordinated disclosure

Maintainer và reporter có thể thống nhất thời gian khắc phục, phát hành bản vá và công bố advisory. Mục tiêu là bảo vệ người dùng trong khi vẫn ghi nhận đóng góp của reporter.

### 18.4. Dependency vulnerabilities

Nếu contribution cập nhật dependency để xử lý CVE, cần nêu version bị ảnh hưởng, version đã sửa và kiểm tra compatibility.

## 19. Release và ghi nhận đóng góp

Merge chưa chắc đồng nghĩa thay đổi đã đến tay người dùng. Dự án cần release process và changelog.

### 19.1. Changelog entry

Feature, bug fix, breaking change và deprecation nên được ghi trong changelog hoặc release notes. Entry cần liên kết issue/PR khi phù hợp.

### 19.2. Release version

Maintainer quyết định version theo compatibility policy. Contributor không nên tự tăng version artifact nếu quy trình release do CI hoặc maintainer quản lý.

### 19.3. Release notes

Release notes nên giải thích tác động đến người dùng, migration steps và các giới hạn. Với DSL, cần ví dụ syntax mới và thông tin compiler/runtime compatibility.

### 19.4. Backport

Bug fix có thể cần backport về branch đang được hỗ trợ. Backport cần kiểm tra khác biệt API và test trên từng branch.

### 19.5. Credit

Dự án có thể ghi nhận contributor trong changelog, release notes hoặc contributor list. Cần dùng thông tin công khai mà contributor muốn hiển thị.

## 20. Governance và quyền quyết định

Quy trình đóng góp cần nêu rõ ai có quyền quyết định và cách giải quyết bất đồng.

### 20.1. Maintainer responsibilities

Maintainer review, giữ định hướng kỹ thuật, quản lý release và bảo vệ cộng đồng. Quyền merge nên gắn với phạm vi trách nhiệm và policy của dự án.

### 20.2. Module ownership

Các module như grammar, runtime, IDE và security có thể có owner riêng. Thay đổi cross-module có thể cần nhiều reviewer.

### 20.3. Design authority

Với thay đổi lớn, có thể có architecture group hoặc technical steering committee quyết định sau khi xem xét proposal và phản hồi cộng đồng.

### 20.4. Decision records

Quyết định thiết kế nên được lưu lại dưới dạng ADR/RFC hoặc issue summary. Điều này giúp người đến sau hiểu vì sao một lựa chọn được đưa ra.

### 20.5. Conflict resolution

Nếu contributor và maintainer bất đồng, nên dựa vào mục tiêu dự án, compatibility policy, test evidence và quyết định governance. Cần có đường escalation rõ ràng.

## 21. Đóng góp theo từng mức độ

Người mới có thể bắt đầu từ thay đổi nhỏ rồi mở rộng dần.

| Mức độ | Ví dụ | Kỹ năng cần |
|---|---|---|
| Beginner | Sửa typo, link hỏng, ví dụ nhỏ | Markdown và hiểu tài liệu |
| Intermediate | Regression test, bug parser nhỏ | Build/test và codebase |
| Advanced | Grammar feature, resolver, generator | Compiler/DSL architecture |
| Maintainer-level | Public API, type system, release design | Compatibility và governance |

### 21.1. Good first issue

Issue dành cho người mới nên có phạm vi nhỏ, expected behavior rõ và chỉ dẫn test. Maintainer có thể gắn nhãn hoặc cung cấp reproduction.

### 21.2. Mentoring

Contributor mới có thể hỏi trước khi nhận issue hoặc xin review thiết kế. Một quy trình thân thiện nên cung cấp hướng dẫn mà không yêu cầu người mới biết toàn bộ kiến trúc ngay lập tức.

### 21.3. Không chia issue quá nhỏ một cách máy móc

Task nhỏ chỉ hữu ích khi vẫn có kết quả độc lập. Chia một thay đổi logic thành quá nhiều PR có thể làm tăng chi phí review và integration.

## 22. Ví dụ: đóng góp một keyword mới cho DSL

Giả sử người dùng muốn thêm keyword retry vào workflow:

~~~text
task chargePayment {
    retry 3 times
    execute payment.charge()
}
~~~

Một contribution có thể đi qua các bước:

1. Mở issue mô tả nhu cầu retry trong workflow.
2. Cung cấp ví dụ và semantics mong muốn.
3. Thảo luận default delay, backoff, lỗi được retry và timeout.
4. Đề xuất grammar và AST representation.
5. Xác định compatibility với identifier cũ tên retry.
6. Maintainer chấp thuận proposal.
7. Thêm parser rule và AST node.
8. Thêm semantic validation cho số lần retry.
9. Cập nhật runtime để thực thi policy.
10. Viết parser, AST, runtime và integration tests.
11. Cập nhật language server completion/hover.
12. Thêm documentation và migration note nếu cần.
13. Gửi PR với before/after example.
14. Sửa theo review và chờ CI.
15. Maintainer merge và đưa vào release phù hợp.

### 22.1. Các câu hỏi thiết kế

- Retry có áp dụng cho mọi exception hay chỉ transient errors?
- Số lần retry có tính lần đầu không?
- Backoff mặc định là gì?
- Có jitter không?
- Có giới hạn tổng thời gian không?
- Cancellation có dừng retry không?
- Retry có yêu cầu idempotency không?
- Workflow state có được lưu bền vững không?

Những câu hỏi này cho thấy thay đổi syntax cần semantics và runtime contract, không chỉ một parser rule.

## 23. Mẫu pull request description

Một pull request description rõ ràng có thể dùng cấu trúc:

~~~markdown
## Problem
Mô tả hành vi hiện tại và tác động đến người dùng.

## Change
Mô tả hành vi sau thay đổi và phạm vi implementation.

## Example
Before:
...

After:
...

## Compatibility
Nêu breaking changes, deprecation hoặc migration.

## Validation
- [ ] Parser tests
- [ ] Semantic/runtime tests
- [ ] Documentation examples
- [ ] Relevant integration tests

## Related
Closes #123
~~~

Mẫu này chỉ là gợi ý. Nếu repository có PR template, contributor nên dùng template chính thức.

## 24. Những lỗi thường gặp trong quy trình đóng góp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Bắt đầu feature lớn mà chưa thảo luận | Patch có thể đi sai hướng | Viết proposal trước |
| Bug report không có reproduction | Maintainer khó xác nhận | Tạo minimal example |
| Trộn nhiều mục tiêu trong một PR | Review và rollback khó | Chia theo thay đổi độc lập |
| Không chạy baseline tests | Không biết lỗi có sẵn hay mới | Chạy test trước khi sửa |
| Chỉ sửa parser | AST/runtime/editor không đồng bộ | Xem toàn bộ compiler pipeline |
| Không cập nhật docs | Người dùng không biết syntax/behavior mới | Cập nhật docs cùng code |
| Bỏ qua compatibility | Dự án cũ bị phá | Kiểm tra source/API/data compatibility |
| Sửa generated output trực tiếp | Thay đổi bị ghi đè | Sửa source generator/grammar |
| Commit secret | Credential bị lộ | Secret scan và rotate nếu lỡ commit |
| Không trả lời review | PR bị đình trệ | Phản hồi từng thread |
| Cập nhật snapshot mù quáng | Regression được chấp nhận | Review nguyên nhân diff |
| Dùng dependency không rõ license | Rủi ro pháp lý và bảo mật | Kiểm tra license/provenance |
| Công bố lỗ hổng công khai quá sớm | Người dùng bị khai thác | Dùng security channel |
| Không có changelog | Người dùng không biết tác động | Ghi release note |

## 25. Nguyên tắc thiết kế quy trình đóng góp

Một quy trình đóng góp hiệu quả nên:

1. **Công khai điểm bắt đầu.** README và CONTRIBUTING guide chỉ rõ cách tham gia.
2. **Phân loại contribution.** Bug, feature, docs, security và design proposal có luồng phù hợp.
3. **Yêu cầu reproduction rõ.** Bug report có version, source tối thiểu và expected/actual behavior.
4. **Thảo luận thay đổi lớn trước implementation.** Grammar, semantics và public API cần design agreement.
5. **Giữ patch có phạm vi.** Một PR nên có mục tiêu chính và lịch sử dễ review.
6. **Kiểm tra toàn bộ DSL pipeline.** Parser, AST, semantic, runtime, generator và tooling có thể cùng bị ảnh hưởng.
7. **Viết regression tests.** Mọi bug fix nên có test tái hiện.
8. **Cập nhật tài liệu.** Public syntax và behavior phải có docs/examples.
9. **Bảo vệ compatibility.** Đánh giá source, API, schema và runtime impact.
10. **Thực thi CI gates.** Build, tests, lint, security và compatibility checks cần rõ.
11. **Tôn trọng license và quyền đóng góp.** Dùng đúng DCO/CLA nếu dự án yêu cầu.
12. **Bảo vệ cộng đồng.** Có Code of Conduct và security reporting channel.
13. **Ghi lại quyết định.** RFC/ADR và changelog giúp duy trì lịch sử.
14. **Minh bạch quyền quyết định.** Nêu maintainer, module owner và escalation path.
15. **Ghi nhận đóng góp.** Credit đúng người và đúng phạm vi.

## 26. Kết luận

Quy trình đóng góp giúp cộng đồng cải thiện DSL một cách có tổ chức. Một contribution có thể bắt đầu từ bug report, documentation fix hoặc feature proposal, nhưng cần đi qua các bước phù hợp: hiểu dự án, thống nhất phạm vi, thực hiện thay đổi, viết tests, cập nhật docs, gửi pull request và review.

Với DSL, thay đổi grammar thường kéo theo AST, semantics, runtime, generated code và editor tooling. Vì vậy, contributor cần xem xét toàn bộ đường đi từ source đến behavior, đặc biệt là compatibility và migration. Maintainer cần cung cấp quy tắc rõ ràng, CI đáng tin cậy, review công bằng và governance minh bạch.

Khi quy trình được tài liệu hóa và áp dụng nhất quán, người mới dễ tham gia, maintainer giảm chi phí điều phối và chất lượng DSL được duy trì qua nhiều release. Đóng góp khi đó trở thành một phần có thể kiểm tra, ghi nhận và phát triển bền vững của vòng đời ngôn ngữ.
