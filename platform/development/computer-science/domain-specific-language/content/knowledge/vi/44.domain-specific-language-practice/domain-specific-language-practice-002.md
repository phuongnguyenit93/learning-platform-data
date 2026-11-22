# Viết bảng thuật ngữ

Một dự án DSL (Domain-Specific Language) thường sử dụng nhiều khái niệm thuộc cả ngôn ngữ lập trình và domain nghiệp vụ. Một từ như module, target, resource, provider, binding hoặc environment có thể mang nghĩa khác nhau tùy sản phẩm. Nếu mỗi tài liệu, API, diagnostic và thành viên trong nhóm dùng một cách gọi khác nhau, người học sẽ khó hiểu, developer dễ thiết kế interface không nhất quán và người vận hành có thể hiểu sai cấu hình.
 
**Bảng thuật ngữ (glossary)** là tập hợp các thuật ngữ quan trọng cùng định nghĩa, cách dùng và thông tin liên quan. Trong một dự án DSL, glossary giúp thống nhất ngôn ngữ giữa đặc tả, source code, tài liệu API, ví dụ, thông báo lỗi và trao đổi trong nhóm. Nó cũng giúp người mới hiểu domain mà không phải suy đoán ý nghĩa của những từ xuất hiện trong code hoặc tài liệu.
 
Ví dụ, một DSL có thể dùng các khái niệm Project, Workspace, Module, Target, Artifact và Provider. Nếu không định nghĩa rõ, người viết tài liệu có thể dùng Project và Workspace như hai từ đồng nghĩa, trong khi toolchain xem chúng là hai phạm vi khác nhau. Glossary xác định nghĩa chuẩn và giúp các thành phần dùng từ nhất quán.
 
Trong chương **Dự án thực hành**, viết bảng thuật ngữ là một hoạt động tạo tài sản dùng chung cho toàn bộ dự án. Công việc không chỉ là liệt kê từ và dịch nghĩa. Cần chọn thuật ngữ có giá trị, xác định định nghĩa chuẩn, phân biệt khái niệm gần nhau, ghi ví dụ đúng ngữ cảnh, quản lý thay đổi và tích hợp glossary vào quy trình phát triển.
 
## 1. Bảng thuật ngữ là gì?
 
Glossary là danh sách có cấu trúc các thuật ngữ của một domain hoặc sản phẩm. Mỗi mục thường có tên chuẩn, định nghĩa, ngữ cảnh, ví dụ và liên kết tới thuật ngữ liên quan.
 
Một entry cơ bản:
 
~~~yaml
term: Module
definition: >
  A named unit of DSL source that groups declarations and exposes
  a defined interface to other modules.
context: Language model
preferredTerm: module
related:
  - Project
  - Import
  - Namespace
example: 'import "network.dsl"'
status: approved
~~~
 
Cấu trúc thực tế có thể là Markdown table, YAML, JSON, spreadsheet hoặc hệ thống terminology management. Điều quan trọng là một mục có thể được tìm, review và cập nhật.
 
### 1.1. Glossary khác dictionary
 
Dictionary giải thích nghĩa phổ thông của từ trong một ngôn ngữ. Glossary tập trung vào nghĩa chuyên biệt trong một domain hoặc sản phẩm. Ví dụ, từ target trong tiếng Anh có nhiều nghĩa; trong DSL compiler, Target có thể là nền tảng đầu ra mà backend sinh artifact cho nó.
 
### 1.2. Glossary khác acronym list
 
Acronym list chỉ giải thích chữ viết tắt như AST, IR, CLI hoặc API. Glossary bao gồm cả thuật ngữ đầy đủ, khái niệm domain, tên thành phần và acronym. Có thể có một nhóm riêng cho acronym trong cùng glossary.
 
### 1.3. Glossary khác API reference
 
API reference mô tả cách gọi interface. Glossary giải thích các khái niệm được dùng trong interface. Một trang API có thể liên kết tới glossary để giải thích Project, Artifact hoặc Execution Context.
 
### 1.4. Glossary khác style guide
 
Style guide quy định cách viết, capitalization, dấu câu và terminology preference. Glossary ghi nghĩa và quan hệ giữa các thuật ngữ. Hai tài liệu nên liên kết với nhau.
 
## 2. Vì sao dự án DSL cần glossary?
 
DSL có nhiều thuật ngữ ở nhiều lớp:
 
- Language syntax: declaration, expression, literal, block.
- Compiler: lexer, parser, AST, IR, semantic analysis.
- Domain model: service, resource, environment, policy.
- Tooling: workspace, project, target, artifact.
- Runtime: evaluation, execution context, capability.
- API: provider, consumer, contract, schema.
 
Một từ có thể xuất hiện trong code, UI, log, tài liệu và trao đổi của nhiều team. Glossary giảm khác biệt trong cách hiểu.
 
### 2.1. Tăng tính nhất quán
 
Nếu cùng một khái niệm được gọi là deployment target ở một nơi và execution environment ở nơi khác, người đọc có thể nghĩ đó là hai khái niệm khác nhau. Glossary xác định preferred term.
 
### 2.2. Giúp người mới học
 
Người mới có thể tra một từ ngay khi gặp trong tutorial hoặc diagnostic. Glossary cũng giúp người có nền tảng khác nhau cùng hiểu domain.
 
### 2.3. Hỗ trợ thiết kế API
 
Tên class, method, field và command nên phản ánh cùng mô hình khái niệm. Glossary giúp tránh đặt tên mâu thuẫn hoặc dùng từ có nghĩa quá rộng.
 
### 2.4. Giảm lỗi giao tiếp
 
Trong review hoặc incident, nhóm cần phân biệt rõ parser error, semantic error, validation error và runtime error. Định nghĩa chuẩn giảm thời gian giải thích.
 
### 2.5. Hỗ trợ dịch thuật
 
Nếu dự án có tài liệu đa ngôn ngữ, glossary lưu thuật ngữ chuẩn ở từng ngôn ngữ và ghi rõ từ nào nên giữ nguyên.
 
### 2.6. Hỗ trợ search và onboarding
 
Glossary có thể trở thành index cho docs, API reference và training material. Search synonym giúp tìm được mục ngay cả khi người dùng nhập từ cũ.
 
## 3. Xác định phạm vi glossary
 
Trước khi thu thập thuật ngữ, cần xác định glossary dành cho phần nào của sản phẩm.
 
Một DSL platform có thể có các phạm vi:
 
| Phạm vi | Nội dung |
|---|---|
| Language glossary | Syntax, expression, type và declaration |
| Compiler glossary | Lexer, parser, AST, IR và optimization |
| Domain glossary | Khái niệm nghiệp vụ được mô tả bằng DSL |
| Toolchain glossary | CLI, project, workspace, target và artifact |
| Runtime glossary | Evaluation, execution, capability và host function |
| API glossary | Provider, consumer, contract và schema |
| Operations glossary | Environment, deployment, release và rollback |
 
### 3.1. Audience
 
Xác định người đọc là developer, DSL author, plugin author, operator, technical writer hay người dùng nghiệp vụ. Định nghĩa cần đủ chính xác cho audience nhưng không giả định mọi người đều biết thuật ngữ compiler.
 
### 3.2. Boundary
 
Không cần đưa mọi từ tiếng Anh xuất hiện trong repository vào glossary. Tập trung vào từ có nghĩa chuyên biệt, dễ nhầm, xuất hiện nhiều hoặc ảnh hưởng tới quyết định thiết kế.
 
### 3.3. Product terminology
 
Tên command, module, API, feature và resource có thể là tên sản phẩm. Phân biệt proper name với generic concept để tránh định nghĩa nhầm tên riêng thành khái niệm phổ quát.
 
### 3.4. Out of scope
 
Ghi rõ glossary không nhằm thay thế dictionary, language specification, API reference hoặc domain policy. Nó giúp kết nối những tài liệu đó.
 
## 4. Thu thập thuật ngữ
     
Không nên bắt đầu bằng việc tự nghĩ ra một danh sách từ dài. Hãy thu thập từ source và hoạt động thực tế của dự án.
 
Nguồn có thể gồm:
 
- Language specification và grammar.
- README, tutorials và API reference.
- Source code public API.
- Class, type, field và command names.
- Diagnostics và error codes.
- Project manifest và configuration schema.
- Architecture Decision Records.
- Issue, pull request và review discussion.
- Support ticket và câu hỏi onboarding.
- Từ vựng nghiệp vụ của domain.
 
### 4.1. Extract từ source
 
Có thể tìm các identifier public, enum, command và schema property. Tên nội bộ ít dùng không nhất thiết phải đưa vào glossary.
 
### 4.2. Extract từ tài liệu
 
Đọc heading, code sample và định nghĩa trong docs. Những từ được dùng lặp lại nhưng chưa có định nghĩa là ứng viên tốt.
 
### 4.3. Thu thập từ người dùng
 
Ghi lại những từ người dùng thường hỏi, nhầm lẫn hoặc dùng khác với nhóm phát triển. Đây là dấu hiệu glossary cần giải thích.
 
### 4.4. Thu thập từ domain expert
 
Domain expert có thể xác định nghĩa nghiệp vụ mà developer không thể suy ra từ tên field. Ví dụ Resource có thể là một đối tượng hạ tầng được quản lý, không phải tài nguyên máy tính nói chung.
 
### 4.5. Ghi nhận synonym và biến thể
 
Thu thập cách gọi khác, viết tắt, tên cũ và cách dịch. Không xóa synonym chỉ vì nó không phải tên chuẩn; ghi chúng để search và cross-reference.
 
## 5. Tiêu chí chọn thuật ngữ
     
Một glossary tốt tập trung vào thuật ngữ có giá trị cho người đọc.
 
Ưu tiên các từ:
 
- Có nghĩa riêng trong DSL hoặc domain.
- Có thể bị hiểu nhầm với khái niệm khác.
- Xuất hiện trong API, source hoặc diagnostics.
- Được dùng xuyên nhiều team.
- Có ảnh hưởng tới security, lifecycle hoặc runtime behavior.
- Có nhiều synonym hoặc cách dịch.
- Đã thay đổi nghĩa theo phiên bản.
 
### 5.1. Không đưa mọi identifier vào glossary
 
Tên biến cục bộ, tên test fixture hoặc tên class nội bộ thường không cần định nghĩa. Public API và domain concept đáng được ưu tiên.
 
### 5.2. Chọn thuật ngữ theo rủi ro hiểu sai
 
Ví dụ, Module và Package có thể bị dùng lẫn nhau. Nếu toolchain phân biệt chúng, cần entry riêng và mô tả ranh giới.
 
### 5.3. Chọn theo tần suất và tác động
 
Một thuật ngữ hiếm nhưng liên quan tới destructive deployment có thể quan trọng hơn một từ xuất hiện nhiều nhưng dễ hiểu.
 
### 5.4. Nhóm thuật ngữ liên quan
 
Có thể nhóm theo Language, Compiler, Project, Runtime, API và Operations. Nhóm giúp tổ chức nhưng mỗi entry vẫn cần có ID hoặc anchor riêng.
 
## 6. Cấu trúc của một glossary entry
     
Một entry có thể chứa các trường sau:
 
| Field | Mục đích |
|---|---|
| Term | Tên thuật ngữ chuẩn |
| Definition | Định nghĩa ngắn, chính xác |
| Context | Lĩnh vực hoặc thành phần sử dụng |
| Preferred form | Cách viết được khuyến nghị |
| Synonyms | Từ đồng nghĩa hoặc cách gọi khác |
| Acronym | Chữ viết tắt nếu có |
| Part of speech | Danh từ, động từ hoặc tính từ khi hữu ích |
| Example | Ví dụ dùng đúng |
| Related terms | Khái niệm liên quan |
| See also | Link tới tài liệu chi tiết |
| Status | Draft, review, approved, deprecated |
| Owner | Người hoặc team chịu trách nhiệm |
| Version | Phiên bản bắt đầu có nghĩa này |
 
Không phải entry nào cũng cần tất cả trường. Chọn schema phù hợp với quy mô và nhu cầu dự án.
 
### 6.1. Term
 
Dùng dạng số ít cho danh từ nếu phù hợp. Giữ nguyên tên API hoặc proper noun theo convention của sản phẩm.
 
### 6.2. Definition
 
Định nghĩa nên bắt đầu bằng loại khái niệm rồi nêu điểm phân biệt. Tránh định nghĩa vòng tròn bằng cách dùng lại chính từ đó.
 
Ví dụ chưa tốt:
 
~~~text
Parser: Thành phần thực hiện parsing.
~~~
 
Ví dụ rõ hơn:
 
~~~text
Parser: Thành phần nhận token từ lexer và xây dựng parse tree hoặc AST theo grammar của DSL.
~~~
 
### 6.3. Context
 
Context giúp phân biệt nghĩa của cùng một từ. Target trong compiler có thể khác target trong test framework.
 
### 6.4. Synonyms
 
Synonym có thể là từ cũ, cách gọi trong nhóm hoặc tên thường dùng ở domain khác. Cần chỉ rõ synonym nào được chấp nhận và synonym nào không nên dùng trong tài liệu mới.
 
### 6.5. Example
 
Ví dụ nên thể hiện đúng nghĩa trong source, API hoặc workflow. Không dùng ví dụ mơ hồ khiến người đọc suy ra semantics chưa được bảo đảm.
 
### 6.6. Related terms
 
Liên kết tới các khái niệm dễ nhầm hoặc có quan hệ. Ví dụ AST liên quan tới Parse Tree, Parser và Semantic Analysis.
 
### 6.7. Status và owner
 
Entry draft cần được review trước khi trở thành chuẩn. Owner giúp biết ai có thể quyết định khi có tranh luận.
 
## 7. Viết định nghĩa rõ và chính xác
     
Định nghĩa là phần quan trọng nhất của glossary.
 
Một định nghĩa tốt thường:
 
- Ngắn nhưng đủ phân biệt.
- Dùng từ đã có định nghĩa hoặc từ phổ thông.
- Nêu loại khái niệm.
- Tránh vòng tròn.
- Không lặp lại nguyên văn tên thuật ngữ.
- Không trộn recommendation với behavior được bảo đảm.
- Không mô tả implementation detail nếu đó không phải bản chất khái niệm.
 
### 7.1. Dùng genus và differentia
 
Một kỹ thuật hữu ích là bắt đầu bằng lớp khái niệm chung, sau đó nêu điểm khác biệt.
 
Ví dụ:
 
~~~text
Artifact: Một đầu ra có thể lưu trữ hoặc phân phối được tạo từ quá trình build, compile hoặc package của dự án.
~~~
 
"Đầu ra" là lớp khái niệm; "có thể lưu trữ hoặc phân phối" và nguồn tạo ra giúp phân biệt artifact với log hoặc temporary file.
 
### 7.2. Tránh định nghĩa bằng mục đích duy nhất
 
Ví dụ "Workspace là nơi làm việc" không đủ rõ. Cần mô tả nó là phạm vi tập hợp project, folder hoặc module mà tool/editor quản lý.
 
### 7.3. Phân biệt khái niệm gần nhau
 
Nếu hai từ khác nhau, entry nên nói rõ ranh giới. Không nên viết "Project tương tự Workspace" rồi bỏ qua điểm khác biệt.
 
### 7.4. Tránh tuyệt đối hóa
 
Không viết "mọi parser luôn..." nếu DSL hỗ trợ nhiều parser implementation. Định nghĩa phải phản ánh contract thực tế của dự án.
 
### 7.5. Phân biệt definition và usage note
 
Definition trả lời thuật ngữ là gì. Usage note giải thích cách viết hoặc cách dùng trong tài liệu/source.
 
### 7.6. Nêu scope
 
Một từ có thể có nghĩa khác nhau trong các module. Hãy ghi rõ context thay vì cố ép mọi nghĩa thành một định nghĩa chung.
 
## 8. Chuẩn hóa tên, capitalization và cách viết
     
Glossary cần quy định dạng chuẩn để tài liệu và API dùng nhất quán.
 
Ví dụ:
 
| Preferred term | Tránh dùng thay thế | Ghi chú |
|---|---|---|
| Workspace | Work space | Tên khái niệm trong tool |
| Code generator | Codegen ở văn bản hướng dẫn | Có thể dùng codegen trong identifier |
| Type checker | Type validation nếu nói về phase này | Hai khái niệm có thể khác |
| Deployment environment | Runtime target nếu không cùng nghĩa | Ghi rõ scope |
| Plugin | Plug-in hoặc extension nếu chỉ một khái niệm | Chọn một dạng chuẩn |
 
### 8.1. Capitalization
 
Quy định khi nào dùng Title Case, lowercase hoặc PascalCase. Ví dụ, tên khái niệm chung trong văn xuôi có thể viết lowercase; tên type public như ParseResult giữ đúng casing API.
 
### 8.2. Hyphenation
 
Chọn một dạng nhất quán cho từ ghép như code generation, build-time, runtime và end-to-end. Không để cùng một thuật ngữ có nhiều kiểu viết trong cùng bộ docs.
 
### 8.3. Singular và plural
 
Entry thường dùng dạng số ít. Trong văn bản, dùng plural theo ngữ pháp nhưng không tạo entry trùng.
 
### 8.4. Acronym
 
Giải thích acronym ở lần xuất hiện đầu tiên trong tài liệu dài. Glossary lưu cả dạng đầy đủ và dạng viết tắt.
 
### 8.5. API identifier
 
Không dịch tên class, method, field hoặc command. Có thể thêm cách giải thích tiếng Việt bên cạnh tên chuẩn.
 
## 9. Glossary song ngữ
     
Một dự án có thể dùng tiếng Anh trong source/API và tiếng Việt trong tài liệu học tập. Glossary song ngữ giúp giữ đúng nghĩa mà vẫn dễ tiếp cận.
 
Một entry song ngữ có thể có:
 
~~~yaml
term:
  en: "Semantic analysis"
  vi: "Phân tích ngữ nghĩa"
definition:
  vi: >
    Giai đoạn kiểm tra ý nghĩa của cấu trúc cú pháp, bao gồm
    name resolution, type checking và các quy tắc domain.
preferred: true
context: Compiler
~~~
 
### 9.1. Chọn cách dịch
 
Chọn một cách dịch được dùng xuyên suốt. Nếu một thuật ngữ không có bản dịch tự nhiên, có thể giữ tiếng Anh và giải thích nghĩa.
 
### 9.2. Không dịch literal tên API
 
Tên type, command và field cần giữ nguyên để người đọc tìm được trong code. Phần định nghĩa có thể viết bằng tiếng Việt.
 
### 9.3. Synonym theo ngôn ngữ
 
Một thuật ngữ có thể có nhiều cách dịch phổ biến. Ghi preferred translation và alias để tìm kiếm.
 
### 9.4. Translation status
 
Nếu bản dịch chưa được domain expert review, đánh dấu draft hoặc unreviewed. Không trình bày một bản dịch tạm như thuật ngữ chính thức.
 
### 9.5. Locale-specific behavior
 
Nếu thuật ngữ xuất hiện trong UI, cần thống nhất với localization glossary và style guide của sản phẩm.
 
## 10. Phân biệt thuật ngữ dễ nhầm
     
Glossary có giá trị cao khi làm rõ các cặp khái niệm gần nhau.
 
### 10.1. Project và Workspace
 
Project là đơn vị sản phẩm hoặc build có manifest, source và dependency. Workspace là phạm vi làm việc mà editor hoặc tool quản lý, có thể chứa một hoặc nhiều project.
 
### 10.2. Module và Package
 
Module là đơn vị cấu trúc hoặc namespace trong ngôn ngữ/toolchain. Package là đơn vị phân phối có version và dependency metadata. Một module có thể được đóng gói trong package, nhưng hai khái niệm không mặc nhiên giống nhau.
 
### 10.3. Parser và Compiler
 
Parser chuyển token thành parse tree hoặc AST. Compiler là pipeline rộng hơn, thường gồm parsing, semantic analysis, optimization và code generation.
 
### 10.4. AST và IR
 
AST phản ánh cấu trúc source. IR là representation trung gian được thiết kế cho các compiler pass hoặc backend. Một compiler có thể có nhiều IR.
 
### 10.5. Build và Deploy
 
Build tạo artifact từ source và dependency. Deploy đưa artifact hoặc cấu hình tới môi trường chạy. Build thành công không có nghĩa deploy đã xảy ra.
 
### 10.6. Target và Environment
 
Target thường xác định nền tảng hoặc dạng output mà compiler/backend hướng tới. Environment là ngữ cảnh tài nguyên và cấu hình nơi artifact được chạy hoặc triển khai. Một environment có thể dùng một target cụ thể.
 
### 10.7. Validation và Verification
 
Validation kiểm tra input hoặc model có đáp ứng rule đã định nghĩa không. Verification xác nhận implementation hoặc artifact đáp ứng specification/contract. Dự án cần định nghĩa cách dùng từ nhất quán.
 
### 10.8. Error và Diagnostic
 
Error là một loại vấn đề hoặc trạng thái thất bại. Diagnostic là thông tin có cấu trúc được tool phát ra, có thể là error, warning hoặc info.
 
## 11. Nhóm thuật ngữ cho DSL language
     
Các thuật ngữ ngôn ngữ nên có định nghĩa phù hợp với grammar cụ thể.
 
| Term | Định nghĩa ngắn |
|---|---|
| Grammar | Tập quy tắc xác định cấu trúc source hợp lệ |
| Token | Đơn vị lexical được lexer tạo ra |
| Identifier | Tên dùng để định danh declaration hoặc reference |
| Keyword | Token có ý nghĩa cú pháp được dành riêng |
| Literal | Cú pháp biểu diễn giá trị trực tiếp |
| Expression | Cấu trúc được đánh giá để tạo giá trị |
| Statement | Cấu trúc biểu đạt một hành động hoặc khai báo theo grammar |
| Declaration | Cấu trúc giới thiệu tên hoặc thành phần |
| Scope | Phạm vi mà tên có thể được resolve |
| Binding | Quan hệ gắn một tên với declaration hoặc value |
| Type | Phân loại giá trị và operation hợp lệ |
| Annotation | Metadata gắn với declaration hoặc node |
| Block | Nhóm construct được bao bởi delimiter theo grammar |
| Reference | Cách source trỏ tới một declaration hoặc resource |
 
### 11.1. Dùng định nghĩa theo language specification
 
Nếu grammar phân biệt Statement và Declaration, glossary phải giữ đúng phân biệt đó. Không lấy định nghĩa từ một ngôn ngữ khác rồi áp vào DSL.
 
### 11.2. Có ví dụ ngắn
 
Ví dụ:
 
~~~text
let replicas = 3
~~~
 
Trong dòng này, let là keyword, replicas là identifier, 3 là integer literal và toàn bộ dòng là variable declaration theo grammar giả định.
 
## 12. Nhóm thuật ngữ cho compiler và toolchain
     
Một DSL project thường cần giải thích:
 
| Term | Định nghĩa |
|---|---|
| Lexer | Thành phần chuyển source character thành token |
| Parser | Thành phần xây parse tree hoặc AST từ token |
| Parse Tree | Cây thể hiện các production rule đã được áp dụng |
| AST | Cấu trúc cú pháp trừu tượng dùng cho xử lý tiếp theo |
| Semantic Analysis | Giai đoạn kiểm tra ý nghĩa, tên và kiểu |
| Name Resolution | Quá trình ánh xạ reference tới declaration |
| Type Checking | Kiểm tra expression và operation tương thích kiểu |
| IR | Biểu diễn trung gian giữa source và backend |
| Optimization | Biến đổi representation để cải thiện chi phí hoặc output mà vẫn giữ semantics |
| Code Generation | Sinh source hoặc artifact đích |
| Backend | Thành phần chuyển IR/model thành output cho target |
| Diagnostic | Thông báo có cấu trúc về lỗi, warning hoặc thông tin |
| Language Server | Dịch vụ cung cấp tính năng ngôn ngữ cho editor |
| Runtime | Thành phần thực thi chương trình DSL hoặc cung cấp host service |
 
### 12.1. Acronym list
 
Một số acronym phổ biến:
 
| Acronym | Full form | Nghĩa |
|---|---|---|
| AST | Abstract Syntax Tree | Cây cú pháp trừu tượng |
| IR | Intermediate Representation | Biểu diễn trung gian |
| CLI | Command-Line Interface | Giao diện dòng lệnh |
| API | Application Programming Interface | Giao diện lập trình ứng dụng |
| LSP | Language Server Protocol | Giao thức giao tiếp editor và language server |
| CI | Continuous Integration | Tích hợp liên tục |
| CD | Continuous Delivery/Deployment | Phân phối hoặc triển khai liên tục |
| SDK | Software Development Kit | Bộ công cụ phát triển phần mềm |
| ABI | Application Binary Interface | Giao diện nhị phân giữa thành phần |
 
### 12.2. Phân biệt acronym có nhiều nghĩa
 
IR có thể có nghĩa khác trong các domain. Glossary cần ghi context để người đọc không áp dụng sai nghĩa.
 
## 13. Nhóm thuật ngữ cho project và lifecycle
     
Những khái niệm quản trị dự án cũng cần định nghĩa.
 
| Term | Định nghĩa |
|---|---|
| Repository | Kho lưu trữ source và lịch sử thay đổi có version control |
| Project | Đơn vị sản phẩm hoặc build có cấu hình và source |
| Workspace | Không gian làm việc chứa project hoặc module |
| Module | Đơn vị cấu trúc có interface và dependency |
| Package | Đơn vị phân phối được version hóa |
| Manifest | File mô tả metadata và cấu hình project/package |
| Lockfile | File ghi lại dependency resolution chính xác |
| Dependency | Thành phần mà project cần để build hoặc chạy |
| Artifact | Đầu ra được tạo và có thể lưu trữ/phân phối |
| Release | Phiên bản sản phẩm được công bố |
| Deployment | Quá trình đưa artifact/cấu hình tới target environment |
| Environment | Ngữ cảnh tài nguyên, cấu hình và policy khi chạy |
| Migration | Quá trình chuyển source, schema hoặc state sang phiên bản mới |
| Deprecation | Trạng thái thông báo API/tính năng sẽ ngừng hỗ trợ |
 
### 13.1. Gắn glossary với lifecycle
 
Một từ như Release có thể được dùng trong CLI, changelog và deployment record. Định nghĩa cần thống nhất với release process thực tế.
 
## 14. Nhóm thuật ngữ cho API và data
     
Glossary của API/data nên làm rõ các vai trò và schema.
 
| Term | Định nghĩa |
|---|---|
| Provider | Thành phần cung cấp API, event hoặc capability |
| Consumer | Thành phần sử dụng interface do provider cung cấp |
| Contract | Thỏa thuận về cấu trúc và behavior tại ranh giới |
| Schema | Mô tả cấu trúc, kiểu và constraint của dữ liệu |
| Serialization | Chuyển object/model thành representation truyền hoặc lưu |
| Deserialization | Khôi phục object/model từ representation |
| Versioning | Gắn version và quản lý tiến hóa interface hoặc data |
| Compatibility | Khả năng các phiên bản tiếp tục tương tác theo contract |
| Idempotency | Tính chất thực hiện lặp operation không tạo thêm side effect ngoài semantics đã định |
| Pagination | Chia tập kết quả lớn thành các phần có giới hạn |
| Cursor | Token hoặc giá trị dùng để tiếp tục đọc từ vị trí trong tập kết quả |
 
### 14.1. Không định nghĩa quá chung
 
Ví dụ, "Schema là cấu trúc dữ liệu" chưa đủ để phân biệt schema với model hoặc class. Nêu rõ schema mô tả shape, type, required fields và constraints.
 
## 15. Nhóm thuật ngữ cho security và governance
     
Các thuật ngữ bảo mật cần chính xác vì nhầm lẫn có thể dẫn đến cấu hình sai.
 
| Term | Định nghĩa |
|---|---|
| Authentication | Xác minh danh tính của caller |
| Authorization | Quyết định caller được phép thực hiện hành động nào |
| Capability | Quyền hoặc năng lực cụ thể được cấp cho thành phần |
| Least Privilege | Nguyên tắc chỉ cấp quyền tối thiểu cần thiết |
| Sandbox | Môi trường cô lập giới hạn tài nguyên và quyền |
| Secret | Dữ liệu xác thực hoặc thông tin nhạy cảm cần bảo vệ |
| Policy | Tập quy tắc quyết định hành vi được phép |
| Audit Trail | Lịch sử ghi nhận hành động và actor |
| Resource Limit | Giới hạn tài nguyên mà tác vụ được phép sử dụng |
| Threat Model | Mô tả asset, attacker, capability và rủi ro cần xử lý |
| Supply Chain | Chuỗi nguồn, dependency, build và phân phối artifact |
| Provenance | Metadata cho biết artifact được tạo từ source và quy trình nào |
 
### 15.1. Authentication và authorization
 
Đây là cặp thuật ngữ đặc biệt dễ nhầm. Xác minh danh tính thành công không có nghĩa caller được phép truy cập mọi resource.
 
### 15.2. Policy và configuration
 
Configuration cung cấp giá trị để hệ thống hoạt động. Policy quy định hành vi hoặc trạng thái được phép. Một config value có thể bị policy giới hạn.
 
## 16. Thêm ví dụ và quan hệ giữa các thuật ngữ
     
Một glossary dễ học nên liên kết khái niệm thành nhóm.
 
Ví dụ quan hệ compiler:
 
~~~mermaid
flowchart TD
    S[Source] --> L[Lexer]
    L --> T[Tokens]
    T --> P[Parser]
    P --> A[AST]
    A --> M[Semantic Analysis]
    M --> I[IR]
    I --> B[Backend]
    B --> R[Artifact]
~~~
 
Một số quan hệ:
 
- Lexer tạo Token.
- Parser tiêu thụ Token và tạo Parse Tree/AST.
- Semantic Analysis kiểm tra AST.
- IR biểu diễn kết quả trung gian.
- Backend sinh Artifact.
 
### 16.1. Related terms
 
Liên kết nên có hướng hoặc lý do:
 
- See also: khái niệm liên quan.
- Broader term: khái niệm tổng quát hơn.
- Narrower term: khái niệm cụ thể hơn.
- Synonym: cách gọi tương đương.
- Antonym/contrast: khái niệm đối lập hoặc cần phân biệt.
 
### 16.2. Cross-reference
 
Từ một entry Parser, người đọc nên có thể đi tới Lexer, AST, Grammar và Diagnostic. Điều này tạo mạng tri thức thay vì danh sách từ rời rạc.
 
## 17. Chọn định dạng và tổ chức file glossary
     
Glossary có thể lưu dưới nhiều định dạng.
 
### 17.1. Markdown
 
Markdown dễ review trong Git, dễ đọc và phù hợp dự án nhỏ hoặc vừa.
 
~~~text
docs/
    glossary/
        README.md
        language.md
        compiler.md
        project-lifecycle.md
        api-data.md
        security.md
~~~
 
### 17.2. Một file YAML/JSON có schema
 
Định dạng có cấu trúc phù hợp khi cần sinh website, search index hoặc kiểm tra duplicate tự động.
 
### 17.3. Database terminology
 
Tổ chức lớn có thể dùng terminology management system để quản lý owner, approval, localization và version.
 
### 17.4. Một file hay nhiều file?
 
Một file duy nhất dễ tìm khi glossary nhỏ. Khi số entry lớn, chia theo domain nhưng cần index tổng hợp và search.
 
### 17.5. Stable ID
 
Nếu entry được tham chiếu từ API docs hoặc UI, có thể cấp ID ổn định để rename term không làm hỏng link.
 
### 17.6. Source of truth
 
Chỉ định một nơi authoritative. Không duy trì cùng định nghĩa ở nhiều file không có quy trình đồng bộ.
 
## 18. Quy trình xây dựng glossary cho dự án
     
Một quy trình thực tế:
 
1. Xác định audience và phạm vi.
2. Thu thập candidate terms từ grammar, source, docs và domain experts.
3. Chuẩn hóa tên và nhóm theo domain.
4. Phát hiện synonym, duplicate và thuật ngữ dễ nhầm.
5. Viết definition ngắn, rõ và có context.
6. Thêm example và related terms.
7. Gắn owner, status và version khi cần.
8. Review với domain expert và API owner.
9. Publish vào docs hoặc terminology registry.
10. Tích hợp kiểm tra consistency vào CI.
11. Cập nhật glossary khi API, grammar hoặc domain thay đổi.
 
### 18.1. Tạo candidate list
 
Bắt đầu bằng danh sách rộng, nhưng chưa coi mọi mục là approved. Có thể gắn status candidate.
 
### 18.2. Nhóm và deduplicate
 
Tìm các entry có nghĩa giống nhau hoặc khác nhau chỉ ở spelling. Quyết định canonical term.
 
### 18.3. Viết definition
 
Dùng cùng một template và giữ mỗi định nghĩa tập trung vào một khái niệm.
 
### 18.4. Review domain
 
Domain expert xác nhận nghĩa nghiệp vụ; compiler/API owner xác nhận semantics kỹ thuật.
 
### 18.5. Approve và publish
 
Sau review, đánh dấu approved và đưa vào index/search. Entry chưa rõ nên giữ draft thay vì công bố như chuẩn.
 
## 19. Quản lý synonym, deprecated term và naming conflict
     
Ngôn ngữ dự án thay đổi. Một khái niệm có thể đổi tên, hoặc hai team dùng cùng từ với nghĩa khác nhau.
 
### 19.1. Canonical term
 
Chọn một tên chuẩn dùng trong tài liệu, API và giao tiếp chính thức.
 
### 19.2. Synonym
 
Ghi các từ đồng nghĩa để tìm kiếm. Nếu synonym không được khuyến nghị trong nội dung mới, đánh dấu discouraged.
 
### 19.3. Deprecated term
 
Nếu từ cũ đã bị thay thế, giữ entry với thông tin:
 
- Tên cũ.
- Trạng thái deprecated.
- Tên thay thế.
- Phiên bản hoặc thời điểm thay đổi.
- Link migration.
 
### 19.4. Ambiguous term
 
Nếu một từ có hai nghĩa, có thể tạo hai entry có context riêng hoặc chọn tên cụ thể hơn.
 
### 19.5. Naming conflict
 
Nếu hai module dùng cùng tên cho hai khái niệm khác nhau, cần namespace hoặc qualifier để tránh nhập nhằng.
 
### 19.6. Do not silently redefine
 
Không đổi nghĩa entry cũ mà không ghi version/history. Một từ có thể đã được dùng trong source, docs và API.
 
## 20. Versioning và lịch sử glossary
     
Glossary nên theo dõi sự thay đổi của thuật ngữ.
 
### 20.1. Version metadata
 
Có thể ghi introducedIn, deprecatedIn và removedIn. Điều này hữu ích khi nghĩa gắn với language version hoặc API version.
 
### 20.2. Change history
 
Git history có thể lưu ai thay đổi định nghĩa và lý do. Với glossary lớn, có thể ghi changelog terminology.
 
### 20.3. Compatibility
 
Nếu thuật ngữ đổi tên nhưng API vẫn giữ tên cũ, glossary cần phân biệt preferred term với public identifier hiện hành.
 
### 20.4. Translation history
 
Khi thay bản dịch, cần giữ alias để search và giúp người đọc tài liệu cũ.
 
### 20.5. Review cadence
 
Glossary có thể được review định kỳ hoặc theo trigger như language release, API change, onboarding feedback và domain model revision.
 
## 21. Tích hợp glossary vào tài liệu và công cụ
     
Glossary có ích nhất khi người dùng có thể truy cập ngay nơi họ gặp thuật ngữ.
 
### 21.1. API reference
 
Các trang API có thể liên kết tới glossary cho type hoặc concept phức tạp.
 
### 21.2. Diagnostics
 
Diagnostic có thể liên kết tới thuật ngữ hoặc concept guide liên quan, nhưng error message vẫn cần tự hiểu được.
 
### 21.3. IDE hover
 
Language server có thể cung cấp hover documentation cho keyword, built-in function hoặc type. Nội dung glossary có thể là nguồn giải thích.
 
### 21.4. Search
 
Search nên index preferred term, synonym, acronym và context. Người dùng tìm từ cũ vẫn được đưa tới entry chuẩn.
 
### 21.5. Onboarding
 
Dùng glossary trong training và tutorial để người học có một vocabulary chung.
 
### 21.6. Localization
 
UI và docs đa ngôn ngữ nên dùng cùng terminology database hoặc glossary đã được phê duyệt.
 
## 22. Kiểm tra chất lượng glossary
     
Có thể kiểm tra tự động và thủ công.
 
Các kiểm tra tự động:
 
- Term trùng nhau.
- Entry thiếu definition.
- Link hỏng.
- Related term không tồn tại.
- Synonym trỏ tới canonical term hợp lệ.
- Status hoặc version sai schema.
- Cách viết không theo convention.
- Example code block không hợp lệ nếu có thể chạy.
 
### 22.1. Duplicate detection
 
So sánh normalized term để tìm khác biệt casing hoặc dấu nối. Không tự động gộp nếu hai entry có context khác.
 
### 22.2. Cross-reference validation
 
Nếu entry A liên kết tới B, B phải tồn tại hoặc link external được đánh dấu rõ.
 
### 22.3. Definition review
 
Con người cần kiểm tra định nghĩa có chính xác, phân biệt được khái niệm và không vòng tròn hay không.
 
### 22.4. Example validation
 
Ví dụ source/API nên được kiểm tra theo phiên bản tool tương ứng nếu có thể.
 
### 22.5. Terminology lint
 
Docs lint có thể cảnh báo khi tài liệu dùng discouraged term hoặc spelling không chuẩn. Cần tránh cảnh báo sai trong code identifier hoặc trích dẫn.
 
### 22.6. Review status
 
Draft, in-review, approved và deprecated cần semantics rõ. Không coi mọi entry đã commit là approved.
 
## 23. Governance và ownership
     
Glossary cần người chịu trách nhiệm.
 
### 23.1. Glossary owner
 
Owner duy trì cấu trúc, quy tắc và quy trình review.
 
### 23.2. Domain owner
 
Domain expert xác nhận ý nghĩa nghiệp vụ.
 
### 23.3. API owner
 
API owner xác nhận tên public type, method, field và behavior.
 
### 23.4. Technical writer
 
Technical writer giúp định nghĩa dễ hiểu, nhất quán và phù hợp audience.
 
### 23.5. Contribution process
 
Contributor có thể đề xuất entry hoặc thay đổi qua pull request. Review cần kiểm tra trùng lặp, context và related terms.
 
### 23.6. Dispute resolution
 
Khi hai team bất đồng, owner cần xác định domain authority và ghi decision. Không để hai định nghĩa mâu thuẫn cùng ở trạng thái approved.
 
## 24. Ví dụ glossary cho một DSL platform
     
Bảng sau minh họa một phần glossary thực hành:
 
| Thuật ngữ | Định nghĩa | Liên quan |
|---|---|---|
| DSL | Ngôn ngữ được thiết kế cho một domain hoặc nhóm tác vụ cụ thể | Grammar, Language |
| Grammar | Tập quy tắc mô tả cấu trúc source hợp lệ | Parser, Syntax |
| Lexer | Thành phần chuyển ký tự thành token | Token, Parser |
| Parser | Thành phần xây parse tree hoặc AST từ token | Grammar, AST |
| AST | Cấu trúc cây trừu tượng biểu diễn source sau parsing | Parser, IR |
| Semantic Analysis | Giai đoạn kiểm tra ý nghĩa, tên và kiểu | Type Checking, Resolver |
| IR | Biểu diễn trung gian cho compiler pass hoặc backend | AST, Backend |
| Backend | Thành phần sinh output cho một target | IR, Artifact |
| Project | Đơn vị phát triển/build có manifest và source | Workspace, Module |
| Workspace | Phạm vi làm việc chứa một hoặc nhiều project/module | Project, Repository |
| Module | Đơn vị cấu trúc có declaration và interface | Import, Package |
| Package | Đơn vị phân phối có version và dependency metadata | Module, Registry |
| Manifest | File mô tả metadata và cấu hình project/package | Lockfile, Project |
| Lockfile | File ghi dependency graph đã resolve chính xác | Dependency, Manifest |
| Target | Nền tảng hoặc dạng output mà compiler hướng tới | Backend, Artifact |
| Artifact | Đầu ra có thể lưu trữ hoặc phân phối được tạo từ build/compile | Release, Target |
| Runtime | Thành phần thực thi chương trình DSL hoặc cung cấp host services | Evaluation, Host Function |
| Extension | Thành phần bổ sung năng lực qua extension point đã công bố | Plugin, Capability |
| Plugin | Gói extension được nạp vào host theo một API contract | Extension API, Registry |
| Capability | Quyền hoặc năng lực cụ thể được cấp cho thành phần | Authorization, Sandbox |
| Provider | Thành phần cung cấp API hoặc event | Consumer, Contract |
| Consumer | Thành phần sử dụng interface do provider cung cấp | Provider, Contract |
| Contract | Thỏa thuận về cấu trúc và behavior tại ranh giới | Schema, Compatibility |
| Environment | Ngữ cảnh tài nguyên, cấu hình và policy khi chạy | Deployment, Target |
| Deployment | Quá trình đưa artifact hoặc cấu hình tới environment | Release, Rollback |
| Diagnostic | Thông báo có cấu trúc về lỗi, warning hoặc thông tin | Error, Source Range |
| Resource Limit | Ràng buộc mức tài nguyên một tác vụ được phép tiêu thụ | Quota, Timeout |
| Sandbox | Môi trường cô lập giới hạn quyền và tài nguyên | Capability, Isolation |
 
Đây là glossary khởi đầu, không phải từ điển đầy đủ cho mọi DSL. Mỗi dự án cần điều chỉnh định nghĩa theo grammar, API và domain thực tế.
 
## 25. Ví dụ entry chi tiết
     
Một entry đầy đủ có thể trình bày như sau:
 
### Parser
 
**Preferred term:** Parser
 
**Tiếng Việt:** Bộ phân tích cú pháp
 
**Context:** Compiler / Language implementation
 
**Definition:** Thành phần nhận token từ lexer và áp dụng grammar để xây dựng parse tree hoặc AST. Parser chịu trách nhiệm xác định cấu trúc cú pháp của source; việc tên có tồn tại hay kiểu dữ liệu có phù hợp thường thuộc semantic analysis.
 
**Synonyms:** Syntax parser (mô tả), parser component.
 
**Related terms:** Lexer, Token, Grammar, Parse Tree, AST, Semantic Analysis.
 
**Example:**
 
~~~text
let replicas = 3
~~~
 
Parser nhận diện đây là một variable declaration với identifier replicas và integer literal 3.
 
**Do not confuse with:** Compiler. Parser là một phase hoặc thành phần của compiler, không phải toàn bộ compiler pipeline.
 
### Artifact
 
**Preferred term:** Artifact
 
**Tiếng Việt:** Tạo phẩm build / artifact
 
**Context:** Build and release
 
**Definition:** Đầu ra được tạo từ source, configuration và dependency bởi một quá trình build, compile hoặc package, có thể được lưu trữ, phân phối hoặc triển khai.
 
**Related terms:** Build, Package, Release, Deployment, Provenance.
 
**Example:** JAR, WebAssembly module, container image hoặc generated manifest bundle.
 
**Do not confuse with:** Log hoặc temporary file. Những file này có thể xuất hiện trong build nhưng không nhất thiết là artifact phát hành.
 
## 26. Template để thêm entry mới
     
Có thể dùng template Markdown:
 
~~~markdown
### Term name
 
- **Preferred term:**
- **Definition:**
- **Context:**
- **Synonyms:**
- **Acronym:**
- **Example:**
- **Related terms:**
- **Do not confuse with:**
- **Status:**
- **Owner:**
- **Introduced in:**
- **References:**
~~~
 
Hoặc template YAML có schema để tooling đọc. Dù chọn format nào, cần tránh trường không có semantics rõ hoặc bị dùng khác nhau giữa entry.
 
## 27. Những lỗi thường gặp khi viết glossary
     
| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Định nghĩa vòng tròn | Người đọc không hiểu thêm điều gì | Bắt đầu bằng lớp khái niệm và điểm phân biệt |
| Dùng một từ cho nhiều nghĩa | Tài liệu và API nhập nhằng | Ghi context hoặc chọn tên cụ thể |
| Không có preferred term | Team tiếp tục dùng nhiều biến thể | Chọn tên chuẩn và lưu synonym |
| Dịch thuật ngữ thiếu nhất quán | Docs song ngữ khó đối chiếu | Dùng terminology mapping đã review |
| Đưa mọi identifier vào glossary | Danh sách quá dài, khó tìm | Chọn public/domain terms có giá trị |
| Không có ví dụ | Định nghĩa khó áp dụng | Thêm source/API/workflow example |
| Nhầm glossary với tutorial | Entry quá dài và khó tra cứu | Giữ definition ngắn, liên kết guide |
| Không ghi context | Từ đa nghĩa bị hiểu sai | Ghi domain hoặc component |
| Không phân biệt deprecated term | Người dùng tiếp tục dùng tên cũ | Gắn trạng thái và replacement |
| Không có owner | Entry mâu thuẫn không được giải quyết | Gán domain/API owner |
| Cập nhật một tài liệu nhưng quên tài liệu khác | Terminology drift | Tích hợp glossary lint và docs review |
| Không version hóa | Nghĩa cũ bị thay đổi âm thầm | Ghi introduced/deprecated version |
| Related link không được kiểm tra | Điều hướng bị hỏng | Validate cross-reference trong CI |
| Ví dụ không chạy | Người đọc học cách dùng sai | Test example với tool version phù hợp |
| Dùng acronym không giải thích | Người mới khó hiểu | Có full form và definition |
 
## 28. Quy trình thực hành: tạo glossary cho một DSL project
     
Một bài thực hành có thể triển khai theo từng bước:
 
1. **Chọn phạm vi:** xác định glossary bao phủ language, compiler, project lifecycle, API hay toàn platform.
2. **Xác định audience:** developer, người viết DSL, plugin author, operator và người học.
3. **Thu thập candidate:** lấy thuật ngữ từ grammar, source, API docs, manifest và domain expert.
4. **Phân nhóm:** language, compiler, project, runtime, API/data và security.
5. **Chuẩn hóa:** chọn preferred term, spelling, capitalization và bản dịch.
6. **Viết definition:** mô tả ngắn, đúng semantics và nêu điểm phân biệt.
7. **Thêm example:** dùng source, API hoặc workflow thực tế.
8. **Liên kết:** thêm synonym, related terms và tài liệu chi tiết.
9. **Review:** domain expert và API owner xác nhận.
10. **Publish:** đặt glossary trong docs với navigation và search.
11. **Validate:** chạy duplicate check, link check và terminology lint.
12. **Maintain:** cập nhật khi grammar, API hoặc domain model thay đổi.
 
### 28.1. Deliverables
 
Kết quả thực hành có thể gồm:
 
- Một trang glossary index.
- Các entry theo nhóm domain.
- Quy tắc naming và preferred terminology.
- Danh sách acronym.
- Template thêm entry.
- Owner và review status.
- CI check cho duplicate/link/format.
 
### 28.2. Review session
 
Trong buổi review, chọn những cặp dễ nhầm như Project/Workspace, Module/Package và Target/Environment. Yêu cầu người tham gia giải thích bằng một ví dụ source hoặc workflow. Nếu các câu trả lời khác nhau, definition cần được làm rõ.
 
### 28.3. Adoption
 
Đưa link glossary vào README, contribution guide và API reference. Nhắc contributor cập nhật glossary khi thêm public concept hoặc đổi tên API.
 
## 29. Đưa glossary vào quy trình phát triển
     
Glossary cần được cập nhật cùng thay đổi sản phẩm.
 
### 29.1. Pull request template
 
Có thể thêm câu hỏi: thay đổi này có thêm hoặc đổi thuật ngữ public không? Nếu có, yêu cầu cập nhật glossary.
 
### 29.2. Documentation review
 
Reviewer kiểm tra từ ngữ mới có khớp preferred term hay không.
 
### 29.3. API design review
 
Khi thêm type, field hoặc command, tra glossary để tránh tạo synonym hoặc naming conflict.
 
### 29.4. Release process
 
Release có breaking change về terminology cần migration note hoặc deprecation entry.
 
### 29.5. Onboarding
 
Dùng glossary làm tài liệu tham khảo trong onboarding, nhưng không yêu cầu người mới học thuộc toàn bộ trước khi thực hành.
 
### 29.6. Search analytics
 
Theo dõi thuật ngữ người dùng tìm nhưng không có kết quả để bổ sung alias hoặc entry.
 
## 30. Tiêu chí của một glossary tốt
     
Một glossary tốt giúp người đọc hiểu đúng một khái niệm trong đúng ngữ cảnh và tìm được tài liệu liên quan. Nó có preferred term, definition rõ, ví dụ, synonym, owner và quy trình cập nhật. Nó được duy trì như một phần của sản phẩm thay vì tạo một lần rồi bỏ quên.
 
Các câu hỏi quan trọng:
 
- Phạm vi và audience của glossary đã rõ chưa?
- Thuật ngữ được chọn từ source, docs và domain usage chưa?
- Mỗi entry có định nghĩa không vòng tròn và có context không?
- Preferred term và synonym có được phân biệt không?
- Các cặp khái niệm dễ nhầm có được giải thích riêng không?
- Cách viết, capitalization và bản dịch có nhất quán không?
- Example có phản ánh semantics thật của DSL không?
- Related terms và cross-reference có hợp lệ không?
- Entry có status, owner và version khi cần không?
- Glossary có được tích hợp vào API docs, IDE và onboarding không?
- CI có kiểm tra duplicate, broken links và terminology drift không?
- Quy trình deprecation và rename có giữ lịch sử không?
 
Viết bảng thuật ngữ là một phần của thiết kế và quản trị tri thức trong dự án DSL. Khi các khái niệm được định nghĩa chính xác, tên gọi được chuẩn hóa và quan hệ giữa chúng được liên kết, nhóm có một vocabulary chung để thiết kế API, viết tài liệu, review code và trao đổi về domain. Glossary được duy trì cùng source và release sẽ tiếp tục hữu ích khi ngôn ngữ, toolchain và cộng đồng người dùng phát triển.
