# Tương thích cú pháp

## 1. Tương thích cú pháp trong phiên bản và di trú DSL

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) thường được sử dụng lâu dài trong cấu hình, workflow, policy, rule, pipeline hoặc source code của nhiều nhóm. Khi ngôn ngữ phát triển, grammar có thể cần thêm keyword, operator, cấu trúc block hoặc cách viết mới. Những thay đổi đó có thể làm source cũ không còn parse được, hoặc khiến source từng hợp lệ được hiểu theo nghĩa khác. Vì vậy, **tương thích cú pháp (syntax compatibility)** là một phần quan trọng của chiến lược versioning và migration.

Tương thích cú pháp mô tả khả năng một phiên bản parser hoặc compiler tiếp tục chấp nhận và diễn giải source được viết theo phiên bản khác, trong phạm vi được xác định. Nó liên quan đến grammar, tokenization, precedence, reserved word, syntax form, default và cách parser xử lý construct cũ.

Ví dụ phiên bản đầu của DSL cho phép:

~~~text
service payment {
    timeout = 3
}
~~~

Phiên bản sau yêu cầu đơn vị thời gian rõ ràng:

~~~text
service payment {
    timeout = 3s
}
~~~

Nếu parser mới từ chối source cũ, đây là một thay đổi không tương thích về cú pháp. Nếu parser mới vẫn chấp nhận số nguyên và diễn giải là giây theo quy tắc cũ, nó có thể duy trì tương thích. Tuy nhiên, việc tự thêm đơn vị mặc định cũng cần được định nghĩa rõ vì nó ảnh hưởng semantics.

Tương thích cú pháp không chỉ là việc parser có parse thành công hay không. Parser có thể chấp nhận source cũ nhưng tạo AST hoặc semantics khác. Do đó cần xem xét cả syntax acceptance, AST shape, type checking và runtime behavior.

## 2. Các lớp tương thích

Khi nói về compatibility, cần xác định đang bảo đảm lớp nào.

### 2.1. Lexical compatibility

Token cũ tiếp tục được nhận diện như trước. Ví dụ identifier từng hợp lệ không bất ngờ trở thành keyword mới.

### 2.2. Grammar compatibility

Cấu trúc cú pháp cũ vẫn được parser chấp nhận và tạo ra cấu trúc tương ứng.

### 2.3. AST compatibility

Parser mới có thể tạo AST nội bộ khác nhưng các công cụ downstream vẫn nhận được biểu diễn tương thích hoặc có adapter.

### 2.4. Semantic compatibility

Source cũ vẫn có cùng ý nghĩa nghiệp vụ, kiểu dữ liệu và hành vi runtime.

### 2.5. Diagnostic compatibility

Diagnostic code, severity, vị trí và nội dung thông báo có thể thay đổi. Nếu editor hoặc CI tiêu thụ diagnostic theo code ổn định, thay đổi format có thể phá integration dù grammar không đổi.

### 2.6. Tooling compatibility

Formatter, language server, linter, generator và migration tool vẫn xử lý source cũ.

### 2.7. Runtime compatibility

Artifact hoặc workflow đã biên dịch từ source cũ tiếp tục chạy đúng với runtime mới, nếu hệ thống cam kết hỗ trợ.

### 2.8. Phân biệt syntax với behavior

Một source có thể vẫn parse được nhưng hành vi thay đổi do default mới hoặc operator precedence mới. Đó là semantic compatibility issue, dù syntax acceptance vẫn đạt.

## 3. Backward và forward compatibility

Hai thuật ngữ này mô tả hướng tương thích giữa producer và consumer hoặc giữa source và parser.

### 3.1. Backward compatibility

Parser/compiler phiên bản mới chấp nhận source được viết cho phiên bản cũ và giữ semantics được cam kết.

Ví dụ source DSL v1 vẫn được parser v2 đọc:

~~~text
language_version = "1"
rule "eligible" when customer.age >= 18
then outcome = APPROVE
~~~

### 3.2. Forward compatibility

Một parser hoặc tool cũ có thể xử lý source được tạo bởi phiên bản mới trong phạm vi được định nghĩa. Điều này khó hơn nếu source mới dùng syntax mà parser cũ không hiểu.

Ví dụ một formatter cũ có thể giữ nguyên extension block chưa biết thay vì xóa nó, nhưng nó không nhất thiết có thể thực thi construct mới.

### 3.3. Full compatibility

Một số hệ thống schema dùng thuật ngữ full compatibility cho cả hai hướng. Với DSL source, cần định nghĩa cụ thể: parser nào đọc source nào, compiler nào tạo artifact nào và semantics nào được bảo đảm.

### 3.4. Compatibility matrix

| Source version | Parser v1 | Parser v2 | Parser v3 |
|---|---|---|---|
| v1 | Native | Backward-compatible | Backward-compatible nếu còn support |
| v2 | Không hỗ trợ syntax mới | Native | Backward-compatible |
| v3 | Không hỗ trợ | Có thể từ chối | Native |

Đây là ví dụ minh họa. Một dự án nên công bố ma trận thực tế cùng thời hạn hỗ trợ.

### 3.5. Compatibility không tự động theo số version

Tăng major version thường báo hiệu có thể có breaking change, nhưng không phải mọi major đều phải phá cú pháp. Tăng minor version cũng không bảo đảm parser cũ hiểu syntax mới.

## 4. Version declaration trong source DSL

Một cách rõ ràng để quản lý cú pháp là cho source khai báo language version.

### 4.1. File-level version

~~~text
language_version = "2"

workflow "order-approval" {
    ...
}
~~~

Parser hoặc compiler dùng version này để chọn grammar và semantic rules phù hợp.

### 4.2. Module-level version

Một project có thể có nhiều module dùng version khác nhau. Module manifest có thể xác định version mặc định, còn file riêng có thể override nếu policy cho phép.

### 4.3. Project-level version

Project manifest có thể pin DSL version để mọi file dùng cùng semantics, giúp build reproducible.

### 4.4. Version range

Dependency hoặc plugin có thể khai báo dải version tương thích:

~~~text
requires dsl >= "2.1" and < "3.0"
~~~

### 4.5. Default version

Nếu source không khai báo version, compiler cần một quy tắc: dùng version mặc định hiện hành, dùng version theo project metadata hoặc từ chối để tránh diễn giải mơ hồ.

### 4.6. Pinning và reproducibility

Build nên ghi lại DSL version, compiler version, plugin version và dependency version. Nếu chỉ dùng latest, source có thể được parse khác nhau theo thời điểm.

### 4.7. Version syntax riêng với application version

Version của DSL language khác version của ứng dụng, package hoặc workflow. Không nên dùng một số version chung cho mọi lớp nếu chúng có lifecycle khác nhau.

## 5. Grammar evolution

Grammar thay đổi theo nhu cầu ngôn ngữ, nhưng mỗi thay đổi cần được đánh giá tác động tới source hiện có.

### 5.1. Additive syntax

Thêm một construct mới thường ít rủi ro hơn nếu không chiếm token hoặc chuỗi ký tự từng được dùng hợp lệ theo cách khác.

### 5.2. New keyword

Thêm keyword có thể làm identifier cũ không còn hợp lệ:

~~~text
let policy = "standard"
~~~

Nếu phiên bản mới dùng policy làm reserved word, source cũ có thể bị lỗi. Có thể dùng contextual keyword, escape identifier hoặc deprecation period.

### 5.3. New operator

Thêm operator có thể thay đổi tokenization hoặc precedence. Ví dụ chuỗi hai ký tự trước đây được hiểu thành hai token riêng có thể trở thành operator mới.

### 5.4. Precedence change

Đổi precedence có thể khiến cùng một expression tạo AST khác. Đây là breaking change về semantics dù grammar vẫn chấp nhận source.

### 5.5. Associativity change

Đổi cách kết hợp operator có thể làm biểu thức số học hoặc logic thay đổi kết quả.

### 5.6. Optional thành required

Một field hoặc clause từng tùy chọn trở thành bắt buộc sẽ làm source cũ không còn hợp lệ.

### 5.7. Syntax removal

Xóa construct cũ là breaking change. Cần deprecation, migration guide và thời gian hỗ trợ.

### 5.8. Ambiguity

Thêm production có thể tạo ambiguity hoặc làm parser chọn nhánh khác. Cần kiểm tra grammar conflict và test các input gần ranh giới.

## 6. Lexical compatibility và identifier

Thay đổi lexer đôi khi có ảnh hưởng rộng hơn thay đổi grammar.

### 6.1. Reserved word

Reserved word không được dùng làm identifier. Khi thêm keyword mới, cần tìm các identifier cũ có cùng spelling.

### 6.2. Contextual keyword

Contextual keyword chỉ được xem là keyword trong một vị trí grammar nhất định. Cách này giảm nguy cơ phá identifier cũ nhưng làm lexer/parser cần phối hợp rõ.

### 6.3. Escaped identifier

DSL có thể cho phép escape keyword bằng một delimiter riêng:

~~~text
let |policy| = "legacy-value"
~~~

Syntax escape phải được định nghĩa ổn định và formatter cần giữ hoặc chuẩn hóa nhất quán.

### 6.4. Case sensitivity

Đổi từ case-insensitive sang case-sensitive có thể làm identifier trước đây trùng nhau hoặc khác nhau. Đây thường là thay đổi breaking.

### 6.5. Unicode normalization

Hai identifier có thể nhìn giống nhau nhưng có code point khác nhau. Thay đổi normalization policy có thể làm symbol resolution thay đổi.

### 6.6. Whitespace và comments

Thay quy tắc whitespace hoặc comment có thể khiến source cũ tokenize khác. Cần test newline, tab, Unicode whitespace và nested comment nếu hỗ trợ.

### 6.7. String và numeric literal

Thay escape sequence, separator, exponent hoặc đơn vị literal có thể làm dữ liệu cũ parse khác. Literal semantics cần được version hóa nếu thay đổi không tương thích.

## 7. AST evolution và parser adapter

Parser có thể giữ grammar cũ nhưng AST internal model thay đổi theo thời gian.

### 7.1. AST là contract nội bộ

IDE, formatter, linter, code generator và plugin có thể phụ thuộc AST. Thay node type hoặc field có thể phá API của tooling.

### 7.2. Canonical AST

Có thể parse nhiều syntax version vào một canonical AST chung. Cách này giúp các phase downstream không phải xử lý mọi biến thể syntax.

### 7.3. Version-specific AST

Trong một số hệ thống, AST khác nhau theo version rồi được normalize qua adapter. Điều này hữu ích khi semantics thực sự khác nhau.

### 7.4. Preserve source syntax

Formatter hoặc migration tool có thể cần biết construct gốc để giữ comment, whitespace và style. AST semantic thuần có thể không giữ đủ trivia.

### 7.5. Unknown node

Tool cũ có thể giữ unknown syntax node như opaque source slice để tránh xóa dữ liệu khi chỉnh sửa một phần file. Nó không có nghĩa tool có thể hiểu hoặc thực thi node đó.

### 7.6. Source map

Sau khi normalize AST, cần giữ mapping từ node canonical về source span để diagnostics và refactoring trỏ đúng vị trí.

## 8. Semantic compatibility

Một thay đổi cú pháp có thể giữ source hợp lệ nhưng làm thay đổi cách hiểu.

### 8.1. Default change

Ví dụ timeout không khai báo trước đây là vô hạn, phiên bản mới mặc định 30 giây. Source không đổi nhưng runtime behavior thay đổi.

### 8.2. Operator precedence

Nếu precedence của AND và OR thay đổi, expression không có ngoặc có thể đổi kết quả.

### 8.3. Numeric semantics

Đổi integer division, overflow behavior hoặc decimal rounding có thể làm rule tính toán khác.

### 8.4. Null semantics

Đổi cách xử lý null trong comparison hoặc coalescing operator có thể ảnh hưởng nhiều rule.

### 8.5. Evaluation order

Đổi từ left-to-right sang unspecified hoặc lazy evaluation có thể thay đổi side effect và exception behavior.

### 8.6. Enum expansion

Thêm enum variant có thể làm pattern match cũ không còn exhaustive. Parser vẫn chấp nhận source nhưng semantic analysis có thể cần cảnh báo hoặc lỗi.

### 8.7. Compatibility mode

Compiler có thể chọn semantic profile theo language version, thay vì áp dụng một semantics duy nhất cho mọi source.

## 9. Deprecation và removal policy

Deprecation cho người dùng thời gian chuyển đổi trước khi syntax bị loại bỏ.

### 9.1. Deprecation stages

Một vòng đời thường gồm:

1. Introduced: syntax mới được thêm.
2. Supported: syntax cũ và mới cùng được chấp nhận.
3. Deprecated: syntax cũ vẫn chạy nhưng có warning.
4. Restricted: syntax cũ cần compatibility flag.
5. Removed: parser mới từ chối syntax cũ.

### 9.2. Warning quality

Warning nên nêu construct cũ, lý do, construct thay thế và phiên bản dự kiến loại bỏ.

### 9.3. Deprecation identifier

Diagnostic code nên ổn định để CI hoặc editor có thể lọc và theo dõi.

### 9.4. Sunset date

Thông báo thời điểm ngừng hỗ trợ giúp nhóm sở hữu source lên kế hoạch migration. Thời gian cần phù hợp với mức độ phổ biến và rủi ro của syntax.

### 9.5. Compatibility flag

Flag tạm thời có thể cho phép chạy source cũ trong giai đoạn chuyển tiếp. Cần có owner, ngày hết hạn và metric theo dõi mức sử dụng.

### 9.6. Không deprecate quá lâu

Giữ quá nhiều syntax cũ làm parser, documentation và test matrix phình lớn. Cần có policy rõ để quyết định giữ, chuyển hoặc loại.

## 10. Versioned grammar và parser selection

Compiler có thể chọn grammar dựa trên language version.

### 10.1. Separate grammar

Mỗi version có grammar riêng. Cách này dễ giữ semantics cũ nhưng tăng chi phí bảo trì và test.

### 10.2. Shared grammar with feature gates

Một grammar chung có điều kiện cho phép construct theo version. Cách này giảm duplicate nhưng có thể làm parser logic phức tạp.

### 10.3. Parse then validate

Parser có thể chấp nhận một grammar superset, sau đó semantic validation kiểm tra construct có được phép ở version hiện tại hay không.

### 10.4. Version-specific parser facade

Facade chọn parser tương ứng và trả về canonical AST. Phần còn lại của compiler làm việc với một API thống nhất.

### 10.5. Version negotiation

>Nếu DSL được trao đổi qua API hoặc remote compiler, client và server cần thống nhất language version, feature set và compiler capability.

### 10.6. Unknown feature

Nếu source yêu cầu feature mới mà compiler không hỗ trợ, báo lỗi có version và feature name rõ ràng thay vì parse sai một cách im lặng.

## 11. Feature flags và capability declarations

Không phải mọi thay đổi đều cần tăng language version nếu hệ thống có cơ chế feature rõ ràng.

### 11.1. Feature flag trong source

~~~text
features {
    typed_duration
    strict_null_checks
}
~~~

### 11.2. Capability requirement

Source có thể khai báo yêu cầu compiler phải hỗ trợ một capability. Compiler kiểm tra capability trước khi phân tích hoặc thực thi.

### 11.3. Feature detection

Compiler có thể cung cấp capability query để tooling biết construct nào được hỗ trợ mà không cần đoán từ version string.

### 11.4. Flag scope

Flag có thể áp dụng toàn file, module hoặc block. Cần quy định precedence và cấm override ở nơi có thể làm semantics mơ hồ.

### 11.5. Feature flag không thay thế versioning

Feature flag phù hợp thử nghiệm hoặc rollout có kiểm soát. Version vẫn cần để tái lập build và xác định contract tổng thể.

### 11.6. Flag lifecycle

Mỗi flag cần trạng thái experimental, stable, deprecated hoặc removed. Tránh để flag thử nghiệm tồn tại vô thời hạn.

## 12. Migration strategy

Migration chuyển source hoặc project từ một version DSL sang version khác.

### 12.1. Manual migration

Developer đọc migration guide và sửa source. Cách này phù hợp khi thay đổi mang tính nghiệp vụ hoặc cần quyết định con người.

### 12.2. Automated migration

Tool phân tích source cũ và biến đổi syntax sang dạng mới. Tự động hóa tốt với rename, syntax rewrite hoặc thêm annotation có quy tắc rõ.

### 12.3. In-place migration

Tool ghi trực tiếp file đã sửa. Cần backup, diff review và khả năng rollback.

### 12.4. Non-destructive migration

Tool tạo file hoặc branch mới để review trước khi thay thế source hiện tại.

### 12.5. Staged migration

Project có thể nâng từng module, package hoặc workflow thay vì chuyển toàn bộ cùng lúc. Dependency giữa module cần có compatibility bridge.

### 12.6. Migration manifest

Ghi source version, target version, migration tool version, thời điểm, file đã chuyển và warning còn lại. Manifest giúp tái lập và audit.

## 13. AST-based codemod

Codemod là chương trình biến đổi source có quy tắc. Với DSL, codemod nên làm việc trên AST hoặc syntax tree có giữ trivia thay vì thay chuỗi thuần túy.

### 13.1. Vì sao không chỉ dùng regex

Regex có thể sửa text đơn giản nhưng khó phân biệt keyword trong comment, string, identifier hoặc nested expression. AST-aware transformation hiểu cấu trúc cú pháp.

### 13.2. Parse source cũ

Codemod dùng parser đúng version nguồn để tạo syntax tree. Nếu parser mới không còn hỗ trợ cú pháp cũ, cần giữ parser legacy hoặc parser migration.

### 13.3. Rewrite node

Transformation tìm node cũ và thay bằng node mới, ví dụ đổi field name, thêm unit hoặc thay block syntax.

### 13.4. Preserve comments

Comment, whitespace và formatting có thể có giá trị cho người dùng. Concrete syntax tree hoặc trivia attachment giúp giữ chúng.

### 13.5. Reparse output

Sau khi rewrite, parse lại source mới bằng target parser để xác nhận cấu trúc có thể được đọc.

### 13.6. Semantic validation

Codemod cần chạy semantic analysis hoặc migration check để xác nhận việc rewrite giữ ý nghĩa dự kiến.

### 13.7. Idempotent codemod

Chạy migration hai lần không nên tiếp tục làm thay đổi source đã chuyển. Tính idempotent giúp migration an toàn khi chạy lại.

## 14. Ví dụ migration cú pháp

Giả sử version cũ dùng:

~~~text
retry = 3
~~~

Version mới dùng block rõ ràng:

~~~text
retry {
    max_attempts = 3
    backoff = exponential(200ms)
}
~~~

Migration cần xác định retry = 3 trước đây có nghĩa tổng số attempt hay số lần thử lại thêm. Nếu semantics cũ không rõ, tool không nên tự động đoán; nó có thể phát warning và yêu cầu lựa chọn.

### 14.1. Rename field

Field endpoint đổi thành base_url có thể được rewrite tự động nếu mapping một-một và không có tên trùng khác.

### 14.2. Add unit

Giá trị timeout = 5 có thể được đổi thành timeout = 5s nếu contract cũ xác định số đó là giây. Nếu đơn vị cũ phụ thuộc môi trường, cần manual review.

### 14.3. Replace keyword

Keyword cũ có thể được thay bằng syntax mới nếu không xung đột với identifier hoặc string.

### 14.4. Restructure block

>Một cấu trúc phẳng có thể được chuyển thành block lồng. Codemod cần giữ thứ tự khai báo nếu thứ tự có semantics.

### 14.5. Preserve behavior

>Mỗi migration rule nên mô tả điều kiện áp dụng và lý do transformation giữ semantics. Với thay đổi không thể bảo toàn, report cần đánh dấu manual action.

## 15. Migration diagnostics

Compiler và migration tool cần thông báo rõ về syntax cũ.

### 15.1. Deprecation warning

Warning chỉ ra construct cũ, version giới thiệu deprecation và replacement.

### 15.2. Migration hint

Hint có thể hiển thị bản rewrite dự kiến hoặc link tới tài liệu migration.

### 15.3. Unsupported syntax error

Lỗi cần nêu language version hiện tại, version tối thiểu cần thiết và cách nâng version.

### 15.4. Ambiguous migration

Nếu một syntax cũ có nhiều cách hiểu ở version mới, tool cần báo ambiguity thay vì chọn tùy ý.

### 15.5. Diagnostic stability

Diagnostic code nên ổn định qua minor releases nếu tooling bên ngoài dựa vào nó. Message có thể được cải thiện mà không đổi code.

### 15.6. Machine-readable report

Migration report có thể cung cấp JSON hoặc structured format với file, range, rule ID, status và action required.

## 16. Tương thích formatter và language server

Tooling thường tồn tại lâu hơn một lần compile và có thể gặp source nhiều version.

### 16.1. Formatter

Formatter cần parse source version tương ứng và giữ semantics. Không nên tự chuyển syntax deprecated trừ khi người dùng bật rewrite mode.

### 16.2. Language server

Language server cần biết language version của workspace hoặc file để completion, diagnostics và code action đúng.

### 16.3. Completion

Completion chỉ nên gợi ý keyword và syntax được hỗ trợ trong version hiện tại hoặc capability đã bật.

### 16.4. Code action

Code action có thể cung cấp quick fix cho deprecated syntax. Quick fix nên giới hạn phạm vi thay đổi và hiển thị preview.

### 16.5. Refactoring

Rename symbol phải hiểu identifier escaping và keyword status theo version để không tạo source sai.

### 16.6. Mixed-version workspace

Workspace có thể chứa module khác version. Language server cần giữ context theo module thay vì áp dụng một parser version toàn cục.

## 17. Package, module và dependency compatibility

Source DSL có thể import package hoặc module do nhóm khác phát hành.

### 17.1. Module language version

Mỗi module có thể khai báo version DSL mà nó dùng. Compiler cần kiểm tra module dependency có tương thích với compiler và consumer không.

### 17.2. Import contract

Import nên tham chiếu API hoặc exported symbol ổn định, không phụ thuộc syntax nội bộ của module.

### 17.3. Version range

Dependency có thể khai báo range hỗ trợ. Resolver chọn version đáp ứng cả constraint và compatibility policy.

### 17.4. Lockfile

Lockfile pin dependency version và digest để build không đổi theo thời gian.

### 17.5. Compatibility bridge

Adapter hoặc facade có thể chuyển API cũ sang API mới trong thời gian migration.

### 17.6. Breaking dependency

Khi dependency bỏ syntax hoặc API cũ, consumer cần migration trước khi nâng version. Package manager có thể cảnh báo conflict.

## 18. Build, artifact và runtime compatibility

Source syntax chỉ là một phần của hệ thống versioning.

### 18.1. Compile-time pinning

Build record cần lưu language version và compiler version. Cùng source với compiler khác có thể tạo artifact khác nếu semantics hoặc optimization thay đổi.

### 18.2. Artifact format

Compiled artifact cần có format version riêng. Runtime kiểm tra version trước khi load.

### 18.3. Runtime compatibility

Runtime mới có thể hỗ trợ artifact cũ nếu có compatibility layer. Runtime cũ thường không thể chạy artifact mới nếu không hiểu instruction hoặc metadata mới.

### 18.4. Recompilation

Một chiến lược là giữ source và compile lại bằng compiler mới. Cần bảo đảm migration và test xác nhận behavior.

### 18.5. Long-running workflow

Workflow đã chạy có thể cần tiếp tục bằng definition version ban đầu. Không tự động diễn giải state cũ bằng semantics mới nếu chưa có migration plan.

### 18.6. Rollback

Rollback ứng dụng có thể cần compiler/runtime cũ và artifact tương ứng. Giữ artifact provenance giúp xác định tổ hợp cần khôi phục.

## 19. Compatibility testing

Compatibility cần được kiểm tra có hệ thống thay vì dựa vào một vài ví dụ.

### 19.1. Golden corpus

Giữ tập source DSL đại diện cho các version đã hỗ trợ. Mỗi parser mới chạy trên corpus và so sánh acceptance, AST hoặc diagnostics theo contract.

### 19.2. Version matrix

Chạy source version cũ trên parser mới và source version mới trên parser cũ trong các trường hợp được cam kết.

### 19.3. Semantic regression

Thực thi source cũ trên runtime mới và so sánh output, state transition hoặc decision result với baseline.

### 19.4. Round-trip formatting

Parse, format và parse lại; xác nhận semantics không đổi và syntax vẫn hợp lệ.

### 19.5. Migration tests

Chạy codemod trên fixture cũ, so sánh output mong đợi và chạy target parser/semantic checker.

### 19.6. Property-based compatibility

>Sinh source hợp lệ theo grammar cũ rồi xác nhận parser mới chấp nhận và canonical AST giữ semantics tương ứng.

### 19.7. Negative compatibility tests

Xác nhận parser từ chối syntax mới khi version cũ không hỗ trợ, với diagnostic đúng thay vì parse sai hoặc im lặng.

### 19.8. Fuzzing version boundaries

Fuzz input gần các điểm grammar thay đổi như keyword, operator prefix, nested block và delimiter để phát hiện ambiguity.

## 20. Quản trị chính sách tương thích

Một chính sách công khai giúp người dùng biết source được hỗ trợ trong bao lâu.

### 20.1. Support window

Quy định các major/minor language version được hỗ trợ và thời gian bảo trì parser.

### 20.2. Breaking change policy

Liệt kê loại thay đổi cần major version, deprecation và migration guide.

### 20.3. Compatibility review

Mỗi thay đổi grammar cần ghi tác động lên source hiện có, identifier, parser ambiguity, tooling và runtime semantics.

### 20.4. Feature owner

Chỉ định owner cho syntax mới và deprecation để có người xử lý feedback và migration.

### 20.5. Telemetry

>Nếu được phép và bảo vệ quyền riêng tư, có thể thu thập aggregate usage của deprecated construct để ước lượng mức độ cần migration. Không thu source hoặc dữ liệu nhạy cảm không cần thiết.

### 20.6. Documentation

Release note cần nêu syntax mới, syntax deprecated, syntax removed, compatibility mode và hướng dẫn nâng cấp.

## 21. Những sai lầm thường gặp

### 21.1. Chỉ kiểm tra parser có chấp nhận source

Source có thể parse được nhưng semantics thay đổi. Cần kiểm tra AST, type, runtime và diagnostics theo cam kết.

### 21.2. Thêm keyword mà không kiểm tra identifier cũ

Keyword mới có thể làm source hợp lệ trước đây bị lỗi. Dùng contextual keyword hoặc escape strategy.

### 21.3. Đổi precedence mà không version hóa

Expression cũ có thể cho kết quả khác. Giữ precedence theo version hoặc yêu cầu ngoặc tường minh qua migration.

### 21.4. Dùng regex cho mọi migration

Regex không hiểu nested syntax, comment và string. Dùng parser và AST-aware codemod cho transformation cấu trúc.

### 21.5. Tự động migration khi semantics mơ hồ

Tool có thể thay đổi ý nghĩa nghiệp vụ. Báo manual action thay vì đoán.

### 21.6. Giữ compatibility flag vô thời hạn

Quá nhiều flag làm tăng test matrix và độ phức tạp. Mỗi flag cần owner và sunset plan.

### 21.7. Không pin compiler version

Build có thể thay đổi theo compiler mới dù source không đổi. Ghi language/compiler version và lock dependency.

### 21.8. Không hỗ trợ tooling cùng lúc

Parser có thể đã hiểu syntax mới nhưng formatter hoặc language server vẫn làm hỏng source. Compatibility phải bao gồm toàn bộ toolchain.

### 21.9. Không kiểm tra mixed-version workspace

Module khác version có thể bị parse bằng một grammar toàn cục. Giữ version context theo file hoặc module.

### 21.10. Xóa syntax cũ quá sớm

Consumer chưa có thời gian migration. Công bố deprecation và support window.

## 22. Quy trình thiết kế thay đổi cú pháp

1. **Xác định lý do.** Nêu vấn đề mà syntax mới giải quyết và người dùng nào bị ảnh hưởng.
2. **Phân loại thay đổi.** Additive, deprecation, rename, semantic change, precedence change hay removal.
3. **Đánh giá lexical impact.** Kiểm tra keyword, identifier, operator, literal, whitespace và comment.
4. **Đánh giá grammar impact.** Kiểm tra ambiguity, precedence, associativity và error recovery.
5. **Đánh giá semantic impact.** Xác định default, type rule, evaluation order và runtime behavior.
6. **Chọn version policy.** Quyết định language version, feature flag hoặc compatibility mode.
7. **Thiết kế deprecation.** Thêm warning, replacement, sunset date và owner.
8. **Cập nhật parser/tooling.** Parser, AST adapter, formatter, language server và code action.
9. **Viết migration.** Dùng codemod khi có thể chứng minh transformation giữ semantics; đánh dấu manual case.
10. **Kiểm thử compatibility.** Dùng corpus, version matrix, semantic regression và migration fixture.
11. **Cập nhật tài liệu.** Release note, syntax reference, migration guide và support matrix.
12. **Rollout có kiểm soát.** Theo dõi deprecated usage và lỗi parse trước khi loại syntax cũ.
13. **Loại bỏ theo policy.** Chỉ remove khi support window kết thúc và migration đã có đường thực hiện.

## 23. Câu hỏi tự kiểm tra

1. Tương thích cú pháp là gì và khác tương thích ngữ nghĩa như thế nào?
2. Phân biệt lexical, grammar, AST, semantic, diagnostic, tooling và runtime compatibility.
3. Backward compatibility và forward compatibility được hiểu thế nào với source DSL?
4. Vì sao cần compatibility matrix giữa source version và parser version?
5. Version declaration nên đặt ở file, module hay project và có trade-off gì?
6. Thêm keyword, operator hoặc đổi precedence có thể phá source cũ ra sao?
7. Contextual keyword và escaped identifier giúp giảm breaking change như thế nào?
8. Canonical AST và version-specific AST có ưu nhược điểm gì?
9. Deprecation lifecycle nên có những giai đoạn nào?
10. Feature flag khác language version ở điểm nào?
11. Khi nào migration có thể tự động và khi nào cần manual review?
12. Vì sao AST-based codemod an toàn hơn regex với syntax lồng nhau?
13. Migration tool cần bảo toàn comment, source range và semantics ra sao?
14. Formatter và language server cần xử lý mixed-version workspace như thế nào?
15. Version của source DSL, compiler, artifact và runtime liên quan với nhau ra sao?
16. Golden corpus, version matrix và semantic regression giúp kiểm tra compatibility thế nào?
17. Vì sao cần kiểm tra cả trường hợp parser mới chấp nhận source cũ lẫn trường hợp từ chối syntax mới?
18. Những thông tin nào nên có trong migration report và release note?
19. Hãy thiết kế deprecation plan cho một keyword sẽ được thay thế trong major version kế tiếp.
20. Hãy đề xuất quy trình chuyển một project từ DSL v1 sang v2, bao gồm parser, codemod, test và rollback.
