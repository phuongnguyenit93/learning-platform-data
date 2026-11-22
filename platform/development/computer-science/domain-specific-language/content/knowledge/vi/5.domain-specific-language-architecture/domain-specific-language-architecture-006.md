# Công cụ phát triển DSL

## 1. Vai trò của công cụ trong kiến trúc DSL

Ngôn ngữ chuyên biệt miền (*Domain-Specific Language — DSL*) chỉ thực sự hữu ích khi người dùng có thể viết, kiểm tra, hiểu và vận hành nó một cách thuận tiện. Ngoài cú pháp và bộ thực thi, một DSL thường cần một hệ sinh thái công cụ hỗ trợ toàn bộ vòng đời: soạn thảo mã nguồn, phân tích cú pháp, kiểm tra ngữ nghĩa, gỡ lỗi, kiểm thử, đóng gói, triển khai và theo dõi khi chạy.

**Công cụ phát triển DSL** là tập hợp thư viện, chương trình và tiện ích giúp nhóm xây dựng ngôn ngữ, đồng thời giúp người dùng DSL làm việc với ngôn ngữ đó. Công cụ có thể được chia thành hai nhóm có liên quan:

- **Công cụ xây dựng ngôn ngữ:** grammar, lexer/parser generator, AST, bộ kiểm tra ngữ nghĩa, interpreter/compiler, formatter, test framework và công cụ phát hành.
- **Công cụ dành cho người viết DSL:** editor, tô màu cú pháp, tự động hoàn thành, điều hướng, thông báo lỗi, định dạng mã, kiểm tra trước khi chạy và debugger.

Hai nhóm cần dùng chung một định nghĩa ngôn ngữ. Nếu parser chấp nhận một cấu trúc nhưng formatter, IDE hoặc validator hiểu theo quy tắc khác, trải nghiệm sẽ không nhất quán và lỗi khó tìm. Vì vậy, kiến trúc công cụ nên dựa trên một grammar, mô hình ngữ nghĩa và bộ chẩn đoán được quản lý thống nhất.

Một luồng phát triển điển hình:

```text
Đặc tả DSL và grammar
          |
          v
Lexer / Parser hoặc Parser Generator
          |
          v
AST / Mô hình cú pháp
          |
          v
Kiểm tra ngữ nghĩa và kiểu
          |
          +---------------------+
          |                     |
          v                     v
Interpreter / Compiler     Editor Services
          |                 - Completion
          v                 - Diagnostics
Thực thi / Sinh mã         - Hover / Go to Definition
          |                 - Formatting
          v                     |
Runtime, log, metrics <---------+
```

Đây là sơ đồ khái quát. Một DSL nhỏ có thể chỉ cần parser, validator và CLI; một DSL được nhiều nhóm sử dụng có thể cần IDE plugin, language server, debugger, hệ thống quản lý phiên bản và tài liệu chuyên biệt.

## 2. Công cụ mô tả cú pháp và phân tích ngôn ngữ

### 2.1. Đặc tả grammar

Grammar mô tả những chuỗi nào là chương trình hợp lệ theo cú pháp DSL. Nó định nghĩa token, từ khóa, biểu thức, thứ tự thành phần và cấu trúc lồng nhau. Grammar là cơ sở cho parser, tài liệu cú pháp, syntax highlighting và nhiều tính năng editor.

Ví dụ, một DSL nhỏ mô tả quy tắc giảm giá có thể cho phép viết:

```text
rule "gold-customer" {
    when customer.tier == "GOLD" and order.total >= 1000000
    then discount.percent = 10
}
```

Trước khi chọn công cụ, nhóm cần làm rõ các quyết định cú pháp: từ khóa có phân biệt chữ hoa chữ thường không, chuỗi được escape thế nào, biểu thức có thứ tự ưu tiên ra sao, comment có dạng nào, tên định danh có hỗ trợ Unicode không và cách báo lỗi ở vị trí không hợp lệ. Những quyết định này nên được ghi trong đặc tả để parser và editor áp dụng giống nhau.

### 2.2. Parser viết tay

Với DSL nhỏ và grammar đơn giản, nhóm có thể tự viết lexer và parser. Một parser đệ quy xuống (*recursive descent parser*) thường có một hàm cho mỗi nhóm quy tắc grammar; parser kiểu Pratt thường hữu ích khi xử lý biểu thức với nhiều mức ưu tiên toán tử.

Ưu điểm của parser viết tay là kiểm soát được cách phân tích, cách phục hồi sau lỗi và thông báo chẩn đoán. Nhóm có thể điều chỉnh parser theo cú pháp đặc thù hoặc yêu cầu editor. Đổi lại, phải tự duy trì tính đúng đắn, xử lý precedence, vị trí nguồn, lỗi cú pháp và các trường hợp đầu vào bất thường.

Parser viết tay phù hợp khi grammar nhỏ, ít thay đổi và nhóm có đủ kinh nghiệm. Khi cú pháp phát triển nhanh, có nhiều cấu trúc lồng nhau hoặc cần sinh parser cho nhiều nền tảng, parser generator có thể giảm công việc thủ công.

### 2.3. Parser generator

Parser generator nhận grammar và sinh mã parser theo ngôn ngữ đích. Thay vì tự cài đặt mọi quy tắc, nhóm mô tả cú pháp bằng một định dạng grammar rồi tích hợp mã được sinh vào ứng dụng.

Một số công cụ thường gặp:

| Công cụ | Vai trò chính | Khi nào hữu ích |
|---|---|---|
| ANTLR | Sinh lexer, parser và parse tree từ grammar | DSL có grammar rõ ràng, cần parser trong Java hoặc nhiều ngôn ngữ được hỗ trợ |
| JavaCC | Sinh parser cho Java từ đặc tả grammar | Dự án Java muốn tích hợp parser được sinh mã |
| Bison / Flex | Công cụ parser generator và lexer generator trong hệ sinh thái C/C++ | Ngôn ngữ cần pipeline phân tích truyền thống, kiểm soát sâu hơn |
| PEG parser libraries | Phân tích theo Parsing Expression Grammar | Grammar phù hợp với PEG và muốn dùng thư viện parser trong ngôn ngữ triển khai |

Các công cụ có mô hình grammar, cách xử lý lỗi và ngôn ngữ đích khác nhau. Cần kiểm tra phiên bản, khả năng tích hợp, giấy phép, tài liệu và yêu cầu triển khai trước khi chọn.

Ví dụ grammar ANTLR giản lược cho quy tắc giảm giá:

```antlr
grammar DiscountRules;

ruleFile
    : ruleDefinition* EOF
    ;

ruleDefinition
    : RULE STRING LBRACE WHEN condition THEN assignment RBRACE
    ;

condition
    : IDENTIFIER DOT IDENTIFIER EQ STRING
      AND IDENTIFIER DOT IDENTIFIER GE NUMBER
    ;

assignment
    : IDENTIFIER DOT IDENTIFIER EQ NUMBER
    ;

RULE   : 'rule';
WHEN   : 'when';
THEN   : 'then';
AND    : 'and';
EQ     : '==';
GE     : '>=';
DOT    : '.';
LBRACE : '{';
RBRACE : '}';
STRING : '"' (~["\\] | '\\' .)* '"';
NUMBER : [0-9]+ ('.' [0-9]+)?;
IDENTIFIER : [a-zA-Z_] [a-zA-Z_0-9]*;
WS : [ \t\r\n]+ -> skip;
```

Đây là grammar minh họa để giới thiệu cách mô tả token và cấu trúc. Một grammar sản phẩm cần bổ sung quy tắc comment, xử lý escape string đầy đủ, precedence tổng quát, vị trí lỗi và các trường hợp cú pháp mà miền thực tế yêu cầu. Không nên xem ví dụ ngắn này là đặc tả hoàn chỉnh.

### 2.4. AST và mô hình trung gian

Parser thường tạo ra parse tree hoặc AST (*Abstract Syntax Tree*). Parse tree phản ánh các quy tắc grammar đã dùng; AST lược bỏ chi tiết cú pháp không cần cho xử lý ngữ nghĩa và giữ lại cấu trúc có ý nghĩa.

Ví dụ, điều kiện:

```text
customer.tier == "GOLD" and order.total >= 1000000
```

có thể được biểu diễn khái quát như sau:

```text
And
├── Equal
│   ├── Property(customer, tier)
│   └── String("GOLD")
└── GreaterThanOrEqual
    ├── Property(order, total)
    └── Number(1000000)
```

AST giúp tách cú pháp khỏi phần kiểm tra và thực thi. Parser có thể thay đổi cách viết mà interpreter vẫn xử lý cùng loại node. AST cũng có thể được dùng bởi formatter, validator, bộ sinh mã, công cụ trực quan hóa và debugger.

Khi xây dựng AST, nên lưu thông tin vị trí nguồn (*source span*) của node: tệp, dòng, cột và khoảng ký tự. Thông tin này cho phép IDE gạch chân đúng đoạn mã, hiển thị lỗi tại chỗ và hỗ trợ điều hướng từ node về văn bản gốc.

## 3. Công cụ kiểm tra ngữ nghĩa và kiểu

Parser chỉ xác nhận cấu trúc có hợp lệ theo grammar. Một chương trình vẫn có thể sai về ý nghĩa, ví dụ tham chiếu đến trường không tồn tại, so sánh hai kiểu không tương thích hoặc khai báo hành động không được phép.

Semantic analyzer thường thực hiện các việc sau:

- Xây dựng và tra cứu symbol table cho biến, hàm, thực thể và tên miền.
- Kiểm tra tên trường, tên hàm và phạm vi truy cập.
- Kiểm tra kiểu của biểu thức, phép toán và giá trị gán.
- Kiểm tra ràng buộc nghiệp vụ như giới hạn phần trăm, đơn vị tiền tệ hoặc trạng thái hợp lệ.
- Phát hiện tham chiếu chưa khai báo, tên trùng hoặc cấu hình không nhất quán.
- Tạo diagnostics có mã lỗi, mức độ nghiêm trọng, vị trí và gợi ý sửa.

Ví dụ, nếu DSL chỉ cho phép `discount.percent` trong khoảng từ 0 đến 100, parser có thể chấp nhận cú pháp `discount.percent = 150`, nhưng semantic analyzer phải báo lỗi nghiệp vụ.

Nên phân biệt ít nhất ba loại lỗi:

| Loại lỗi | Ví dụ | Thành phần thường phát hiện |
|---|---|---|
| Lỗi từ vựng | Chuỗi không đóng dấu ngoặc kép | Lexer |
| Lỗi cú pháp | Thiếu biểu thức sau `>=` | Parser |
| Lỗi ngữ nghĩa | Trường `customer.unknown` không tồn tại | Semantic analyzer |
| Lỗi thực thi | Dịch vụ được gọi không phản hồi | Runtime |

Một mô hình diagnostics dùng chung giúp CLI, IDE và CI hiển thị lỗi nhất quán. Diagnostic nên có mã ổn định để tài liệu, test và editor có thể tham chiếu, thay vì phụ thuộc vào câu thông báo tự do dễ thay đổi.

## 4. Công cụ soạn thảo và tích hợp IDE

### 4.1. Những tính năng editor cơ bản

Người viết DSL cần một nơi tạo và sửa tài liệu ngôn ngữ. Có thể bắt đầu bằng text editor thông thường, nhưng khi DSL được sử dụng thường xuyên, những tính năng chuyên biệt giúp giảm lỗi và tăng tốc độ làm việc:

- **Syntax highlighting:** tô màu từ khóa, chuỗi, số, comment và tên miền.
- **Code completion:** gợi ý từ khóa, tên trường, hàm và giá trị hợp lệ tại vị trí con trỏ.
- **Diagnostics:** gạch chân lỗi cú pháp, kiểu và quy tắc nghiệp vụ ngay khi soạn thảo.
- **Hover information:** hiển thị kiểu, mô tả hoặc tài liệu của ký hiệu.
- **Go to definition / Find references:** đi đến nơi khai báo và tìm nơi sử dụng một tên.
- **Rename symbol:** đổi tên ký hiệu đồng bộ trong phạm vi được phân tích.
- **Formatting:** tự động căn lề, khoảng trắng và xuống dòng theo quy ước.
- **Code actions:** gợi ý sửa lỗi, thêm import hoặc chuyển cú pháp cũ sang cú pháp mới.

Không phải DSL nào cũng cần tất cả tính năng. Với ngôn ngữ cấu hình nhỏ, tô màu, kiểm tra và định dạng có thể đã đủ. Với DSL dùng để lập trình workflow hoặc quy tắc phức tạp, completion, điều hướng và debugger có giá trị lớn hơn.

### 4.2. TextMate grammar và Tree-sitter

Một cách đơn giản để thêm tô màu cú pháp vào editor là cung cấp grammar kiểu TextMate. Grammar này thường mô tả pattern token bằng biểu thức chính quy và được nhiều editor sử dụng cho syntax highlighting. Nó không thay thế parser đầy đủ và thường không đủ để kiểm tra ngữ nghĩa hoặc hiểu cấu trúc lồng nhau phức tạp.

Tree-sitter là một công cụ tạo parser có khả năng phân tích tăng dần (*incremental parsing*). Nó thường được dùng để hỗ trợ tô màu cú pháp có nhận biết cấu trúc, phân tích khi người dùng đang gõ và xây dựng tính năng editor dựa trên cây cú pháp. Tree-sitter không tự cung cấp toàn bộ semantic analyzer hay runtime cho DSL; nhóm vẫn cần triển khai logic miền và các dịch vụ bổ sung.

### 4.3. Language Server Protocol (LSP)

Language Server Protocol là giao thức cho phép editor giao tiếp với một language server. Thay vì viết plugin riêng cho từng editor, nhóm có thể triển khai một server cung cấp các khả năng ngôn ngữ theo giao thức chung; những editor hỗ trợ LSP có thể kết nối đến server đó.

Một language server có thể cung cấp:

- `textDocument/publishDiagnostics` để gửi lỗi và cảnh báo.
- `textDocument/completion` để gợi ý mã.
- `textDocument/hover` để hiển thị thông tin ký hiệu.
- `textDocument/definition` để điều hướng đến khai báo.
- `textDocument/references` để tìm nơi sử dụng.
- `textDocument/formatting` để định dạng tài liệu.
- Các khả năng khác như rename, signature help, document symbols và code actions nếu server hỗ trợ.

Kiến trúc khái quát:

```text
VS Code / IntelliJ / Editor hỗ trợ LSP
                  |
                  | LSP messages
                  v
           DSL Language Server
                  |
        +---------+----------+
        |         |          |
        v         v          v
      Parser   Semantic   Formatter
               Analyzer
        |         |          |
        +---------+----------+
                  |
                  v
           DSL Core Model
```

Language server thường giữ trạng thái tài liệu đang mở, phân tích lại khi nội dung thay đổi và trả kết quả cho editor. Cần xử lý cập nhật bất đồng bộ cẩn thận: kết quả phân tích cũ không nên ghi đè diagnostics mới hơn. Với workspace lớn, nên dùng phân tích tăng dần hoặc debounce hợp lý để editor phản hồi nhanh.

### 4.4. Framework hỗ trợ xây dựng IDE

Một số nền tảng cung cấp nhiều thành phần hơn LSP:

- **Eclipse Xtext:** hỗ trợ định nghĩa grammar và sinh nhiều thành phần cho ngôn ngữ, gồm parser, mô hình và tích hợp editor trong hệ sinh thái Eclipse; tùy cấu hình có thể tạo hỗ trợ language server.
- **JetBrains MPS:** môi trường xây dựng ngôn ngữ theo hướng projectional editing, trong đó người dùng thao tác với cấu trúc ngôn ngữ thay vì chỉ sửa văn bản thuần túy.
- **VS Code extension API:** cho phép đóng gói syntax highlighting, cấu hình editor, snippets, lệnh và kết nối language server.
- **IntelliJ Platform:** cho phép phát triển plugin với hỗ trợ parser, PSI, inspection, completion và navigation theo mô hình của nền tảng.

Các framework này có mức độ trừu tượng và chi phí học khác nhau. Nhóm nên chọn dựa trên editor người dùng thực sự sử dụng, khả năng bảo trì plugin và mức độ tùy biến cần thiết.

## 5. Formatter, validator và CLI

### 5.1. Formatter

Formatter chuẩn hóa cách trình bày tài liệu DSL, ví dụ thụt lề, khoảng trắng quanh toán tử, cách xuống dòng và dấu phân cách. Formatter hữu ích khi nhiều người cùng sửa một tập hợp tệp cấu hình hoặc quy tắc.

Một formatter tốt nên có tính ổn định và có thể chạy lặp lại: định dạng một tài liệu đã được định dạng không nên tiếp tục tạo ra thay đổi. Nếu có thể, formatter nên hoạt động dựa trên AST hoặc parse tree để hiểu cấu trúc thay vì chỉ thay thế chuỗi bằng biểu thức chính quy.

Ví dụ trước và sau khi định dạng:

```text
rule "vip"{when customer.tier=="GOLD" then discount.percent=10}
```

```text
rule "vip" {
    when customer.tier == "GOLD"
    then discount.percent = 10
}
```

Formatter cần giữ nguyên ý nghĩa chương trình. Một số DSL có comment gắn với vị trí hoặc thứ tự trường có ý nghĩa; khi đó việc định dạng phải bảo toàn các chi tiết đó.

### 5.2. Validator và lệnh kiểm tra

Validator là công cụ kiểm tra tài liệu DSL mà không cần thực thi hành động nghiệp vụ. Nó thường được dùng trước khi lưu cấu hình, trước khi deploy hoặc trong CI.

Một CLI có thể cung cấp các lệnh như:

```bash
dsl parse rules.dsl
dsl validate rules.dsl
dsl format --check rules.dsl
dsl compile rules.dsl --output build/rules.bin
dsl run rules.dsl --input sample.json
```

Các lệnh trên là ví dụ thiết kế CLI, không đại diện cho cú pháp của một sản phẩm cụ thể. Một CLI tốt nên có mã thoát rõ ràng, thông báo lỗi có vị trí, output máy đọc được như JSON khi cần tích hợp CI, và tùy chọn verbose để hỗ trợ điều tra.

### 5.3. Schema và công cụ kiểm tra cấu hình

Nếu DSL được biểu diễn bằng JSON, YAML hoặc TOML, schema có thể hỗ trợ kiểm tra cấu trúc, kiểu dữ liệu, trường bắt buộc và gợi ý trong editor. Tuy nhiên, schema thường chỉ xử lý tốt một phần quy tắc. Những ràng buộc phụ thuộc vào trạng thái hệ thống, symbol table hoặc nghiệp vụ vẫn cần semantic validator chuyên biệt.

Ví dụ, JSON Schema có thể xác nhận `discount.percent` là số từ 0 đến 100, nhưng việc một `customer.tier` có tồn tại trong dữ liệu hiện hành hay không có thể cần truy vấn miền hoặc một registry riêng.

## 6. Công cụ gỡ lỗi và quan sát khi thực thi

Khi DSL được diễn giải hoặc biên dịch thành hành động, người dùng cần biết chương trình đã làm gì và vì sao kết quả xảy ra.

### 6.1. Debugger cho DSL

Debugger chuyên biệt có thể cung cấp:

- Breakpoint tại rule, bước hoặc biểu thức.
- Thực thi từng bước (*step over*, *step into*, *step out*) nếu mô hình thực thi hỗ trợ.
- Hiển thị giá trị biến, context và kết quả biểu thức.
- Theo dõi nhánh điều kiện nào được chọn.
- Xem call stack hoặc execution trace của workflow.
- Dừng, tiếp tục hoặc hủy một lần chạy dài.

Muốn hỗ trợ breakpoint và thông báo lỗi chính xác, runtime cần giữ liên hệ giữa instruction hoặc node thực thi với vị trí trong tài liệu nguồn. Nếu compiler tối ưu hoặc chuyển DSL thành bytecode, cần source map hoặc metadata tương đương để truy ngược kết quả về dòng mã ban đầu.

### 6.2. Logging, tracing và metrics

Trong môi trường vận hành, nên ghi nhận mã tài liệu DSL, phiên bản, rule hoặc workflow đã chạy, thời gian thực thi, kết quả và lỗi. Với quy trình nhiều bước, distributed tracing có thể giúp theo dõi một lần thực thi qua nhiều dịch vụ.

Metrics có thể gồm số lần chạy, tỷ lệ thành công, thời gian xử lý, số rule được đánh giá và số lỗi theo mã. Tránh ghi trực tiếp dữ liệu nhạy cảm trong context hoặc input. Cần xác định chính sách che dữ liệu, thời gian lưu và quyền truy cập log.

### 6.3. Giới hạn runtime

Một DSL có thể được viết bởi người dùng không đáng tin cậy. Khi đó, runtime nên có giới hạn thời gian, bộ nhớ, số bước, độ sâu đệ quy, số lần gọi dịch vụ và quyền truy cập tài nguyên. Nếu DSL cho phép gọi hàm mở rộng, chỉ đăng ký các capability được cho phép và kiểm soát rõ quyền của từng hàm.

Việc parser từ chối cú pháp sai không đủ để bảo vệ runtime. Kiểm soát an toàn phải được thực hiện ở cả semantic validation, API extension và môi trường thực thi.

## 7. Công cụ kiểm thử DSL

Một DSL cần kiểm thử cả cú pháp, ngữ nghĩa, công cụ editor và hành vi runtime. Chỉ kiểm tra một vài chương trình chạy thành công sẽ bỏ sót nhiều lỗi ở các lớp khác nhau.

### 7.1. Parser tests

Parser tests xác nhận chương trình hợp lệ được phân tích thành cấu trúc mong đợi và chương trình sai tạo ra diagnostics phù hợp. Nên có các trường hợp:

- Cú pháp tối thiểu và cú pháp đầy đủ.
- Biểu thức lồng nhau, precedence và associativity.
- Chuỗi escape, comment, Unicode và khoảng trắng.
- Tệp rỗng, tệp lớn và token không hợp lệ.
- Thiếu dấu đóng, token thừa và lỗi ở cuối tệp.
- Phục hồi sau lỗi để tiếp tục báo nhiều diagnostics trong một lần phân tích.

### 7.2. Semantic tests

Semantic tests kiểm tra symbol resolution, kiểu, phạm vi, ràng buộc nghiệp vụ và các trường hợp không hợp lệ. Mỗi quy tắc nên có ít nhất một ví dụ đúng và một ví dụ sai để tránh validator chỉ kiểm tra trường hợp phổ biến.

### 7.3. Runtime tests

Runtime tests kiểm tra kết quả của DSL với input xác định. Với DSL quy tắc, có thể dùng bảng dữ liệu đầu vào và kết quả kỳ vọng. Với DSL workflow, cần kiểm tra thứ tự bước, timeout, retry, hủy, lỗi dịch vụ và khả năng chạy lại an toàn.

### 7.4. Golden tests và snapshot tests

Golden test lưu đầu vào và kết quả kỳ vọng, chẳng hạn AST được serialize, diagnostics, output formatter hoặc mã được sinh. Khi grammar hay formatter thay đổi, test sẽ cho thấy khác biệt. Cần review cập nhật golden files để tránh chấp nhận vô tình thay đổi ngữ nghĩa.

### 7.5. Property-based và fuzz testing

Property-based testing tạo nhiều đầu vào theo các thuộc tính đã định nghĩa, ví dụ formatter phải bảo toàn AST hoặc parse rồi serialize không làm mất thông tin cần thiết. Fuzz testing đưa đầu vào ngẫu nhiên hoặc biến đổi mạnh vào lexer/parser để tìm crash, vòng lặp vô hạn, tràn bộ nhớ và trường hợp lỗi không được xử lý.

### 7.6. Kiểm thử tích hợp editor

Nếu có language server hoặc IDE plugin, cần kiểm tra các tương tác thực tế: mở tệp, thay đổi văn bản, nhận diagnostics, completion, go to definition, rename và formatting. Đặc biệt cần kiểm tra trường hợp người dùng đang gõ dở một biểu thức; editor không nên treo hoặc hiển thị lỗi cũ sau khi tài liệu đã thay đổi.

Một pipeline CI mẫu:

```text
Commit grammar và mã nguồn
          |
          v
Sinh parser / Build language server
          |
          v
Parser tests + Semantic tests
          |
          v
Runtime + Formatter tests
          |
          v
Compatibility / Golden tests
          |
          v
Đóng gói CLI, runtime và editor extension
          |
          v
Phát hành phiên bản
```

## 8. Tài liệu, ví dụ và quản lý phiên bản

Công cụ phát triển không chỉ là compiler và IDE. Tài liệu tốt là một phần quan trọng của hệ sinh thái DSL.

Một bộ tài liệu nên có:

- **Language reference:** grammar, từ khóa, kiểu dữ liệu, biểu thức, precedence và ngữ nghĩa.
- **Getting started:** cài đặt công cụ, tạo tệp đầu tiên, validate và chạy thử.
- **Tutorial theo miền:** các tình huống thực tế, từ đơn giản đến phức tạp.
- **API reference:** hàm, thư viện mở rộng, biến context và capability mà DSL được phép sử dụng.
- **Error catalog:** mã lỗi, nguyên nhân và cách khắc phục.
- **Migration guide:** thay đổi cú pháp và cách nâng cấp tài liệu cũ.

Nếu DSL được lưu trữ lâu dài, cần quản lý phiên bản ngôn ngữ độc lập với phiên bản ứng dụng khi thích hợp. Tệp DSL có thể khai báo version hoặc được gắn version trong metadata. Runtime cần biết cách diễn giải phiên bản đó, từ chối phiên bản không hỗ trợ hoặc chuyển đổi qua migration có kiểm soát.

Ví dụ:

```text
language-version: 2

rule "vip" {
    when customer.tier == "GOLD"
    then discount.percent = 10
}
```

Khi thay đổi grammar hoặc semantics, nhóm cần đánh giá ảnh hưởng đến tài liệu hiện có, hỗ trợ nhiều phiên bản trong giai đoạn chuyển tiếp nếu cần, cung cấp công cụ migration và thông báo rõ thời điểm ngừng hỗ trợ. Thay đổi cách tính toán nhưng giữ nguyên cú pháp vẫn có thể là thay đổi ngữ nghĩa và cần được quản lý cẩn thận.

## 9. Công cụ đóng gói, triển khai và vận hành

Tùy kiến trúc, một DSL có thể được triển khai theo một trong các cách:

- **Interpreter:** runtime đọc AST và thực thi trực tiếp.
- **Compiler:** chuyển DSL thành bytecode, mã máy hoặc mã của ngôn ngữ khác.
- **Code generator:** chuyển DSL thành SQL, JSON, cấu hình hoặc mã nguồn để hệ thống khác xử lý.
- **Configuration engine:** tải và kiểm tra DSL như cấu hình, sau đó áp dụng vào ứng dụng.

Toolchain cần đóng gói các thành phần tương thích với nhau: parser/runtime, thư viện miền, CLI, language server và extension. Nên công bố phiên bản, checksum hoặc chữ ký gói khi phù hợp, cùng tài liệu cài đặt và yêu cầu môi trường.

Trong quy trình triển khai, nên kiểm tra DSL trước khi đưa vào production. Một cấu hình mới có thể được parse, validate, chạy thử trên dữ liệu mẫu hoặc môi trường staging, rồi mới được kích hoạt. Với hệ thống hỗ trợ rollback, cần giữ phiên bản DSL và cấu hình trước đó để khôi phục khi phát hành mới gây lỗi.

## 10. Ví dụ một bộ công cụ DSL hoàn chỉnh

Giả sử nhóm phát triển một DSL quy tắc giá bằng Java. Một cấu trúc dự án có thể là:

```text
pricing-dsl/
├── grammar/
│   └── PricingRules.g4
├── language-core/
│   ├── ast/
│   ├── parser/
│   ├── semantic/
│   └── diagnostics/
├── runtime/
│   ├── evaluator/
│   └── context/
├── cli/
│   └── commands/
├── language-server/
│   └── handlers/
├── editor-vscode/
│   ├── syntaxes/
│   └── snippets/
├── docs/
└── tests/
    ├── parser/
    ├── semantic/
    ├── runtime/
    └── fixtures/
```

Đây là một cách chia module minh họa. Dự án nhỏ có thể gộp nhiều thư mục; dự án lớn có thể tách thành các package hoặc repository riêng. Điều quan trọng là xác định một lõi ngôn ngữ dùng chung để CLI, runtime và language server không tự triển khai các quy tắc khác nhau.

Luồng người dùng có thể như sau:

1. Người dùng mở `discount.rules` trong editor có extension DSL.
2. Extension kết nối đến language server.
3. Khi tài liệu thay đổi, server gọi parser và semantic analyzer của language core.
4. Diagnostics xuất hiện tại vị trí lỗi; completion lấy gợi ý từ grammar và symbol table.
5. Người dùng chạy `dsl validate discount.rules` để kiểm tra lại trong CLI hoặc CI.
6. Khi hợp lệ, pipeline đóng gói rule và phát hành cùng runtime tương thích.
7. Runtime thực thi rule trong context được cấp quyền và ghi trace phục vụ vận hành.

Với cách tổ chức này, grammar, AST và semantic model là nền tảng dùng chung; các công cụ phía trên cung cấp những trải nghiệm khác nhau cho lập trình viên, chuyên gia miền và hệ thống tự động.

## 11. Cách lựa chọn công cụ theo quy mô DSL

Không cần xây dựng một IDE đầy đủ ngay từ đầu. Hãy chọn công cụ dựa trên số lượng người dùng, độ phức tạp grammar, mức độ quan trọng của trải nghiệm soạn thảo và nguồn lực bảo trì.

| Nhu cầu | Bộ công cụ khởi đầu phù hợp |
|---|---|
| DSL nhỏ, chỉ nhóm phát triển sử dụng | Parser viết tay hoặc parser generator, validator, unit tests và CLI |
| Grammar trung bình, nhiều cấu trúc | Grammar đặc tả rõ, parser generator, AST, semantic analyzer và diagnostics chuẩn hóa |
| Nhiều người dùng viết DSL hằng ngày | Thêm formatter, syntax highlighting, completion và language server |
| DSL có quy tắc nghiệp vụ phức tạp | Thêm type checking, symbol resolution, debugger, runtime trace và test fixtures |
| DSL lưu trữ lâu dài, triển khai ở nhiều môi trường | Thêm versioning, migration, compatibility tests, packaging và release process |
| DSL chạy mã hoặc hành động không đáng tin cậy | Thêm sandbox/capability controls, quota, audit log và kiểm thử bảo mật |

Khi đánh giá một công cụ cụ thể, hãy xem xét:

1. Ngôn ngữ lập trình và nền tảng mà nhóm đang dùng.
2. Grammar có hỗ trợ cấu trúc và cách xử lý lỗi cần thiết không.
3. Khả năng giữ vị trí nguồn để diagnostics và debugger hoạt động tốt.
4. Tốc độ phân tích với tệp lớn và khi người dùng đang gõ.
5. Mức độ tích hợp với editor, CI và hệ thống build hiện tại.
6. Giấy phép, hoạt động bảo trì, tài liệu và khả năng tuyển người có kinh nghiệm.
7. Chi phí nâng cấp khi DSL thay đổi trong nhiều năm.

Một lựa chọn phổ biến chưa chắc phù hợp với mọi dự án. Nên tạo một prototype nhỏ bằng grammar và vài tình huống thực tế, đo tốc độ, kiểm tra lỗi và thử tích hợp editor trước khi cam kết kiến trúc lâu dài.

## 12. Những sai lầm thường gặp khi xây dựng toolchain

- **Chỉ xây parser mà bỏ qua diagnostics:** người dùng biết tài liệu sai nhưng không biết vị trí, nguyên nhân và cách sửa.
- **Định nghĩa grammar ở nhiều nơi:** parser, syntax highlighting và tài liệu có thể lệch nhau sau vài lần cập nhật.
- **Dùng regex để xử lý mọi cấu trúc:** biểu thức chính quy đơn giản phù hợp với token hoặc pattern nhỏ, nhưng thường không đủ cho ngôn ngữ có nesting, precedence và phạm vi.
- **Để editor chạy logic nặng đồng bộ:** phân tích tệp lớn có thể làm giao diện bị treo; nên cân nhắc xử lý bất đồng bộ và phân tích tăng dần.
- **Không lưu source location trong AST:** lỗi runtime hoặc semantic khó trỏ về dòng DSL gốc.
- **Formatter làm thay đổi ý nghĩa:** định dạng phải bảo toàn cấu trúc và semantics, được kiểm tra bằng test.
- **Không có compatibility tests:** một thay đổi grammar hoặc runtime có thể làm hỏng hàng loạt tài liệu đã phát hành.
- **Đồng nhất parse thành công với chạy an toàn:** cú pháp hợp lệ vẫn có thể gọi thao tác nguy hiểm hoặc tiêu thụ tài nguyên quá mức.
- **Tách editor plugin khỏi lõi ngôn ngữ:** nhiều editor có thể đưa ra gợi ý hoặc thông báo lỗi khác nhau nếu mỗi plugin tự triển khai logic.

## 13. Kết luận

Công cụ phát triển DSL bao gồm parser và semantic analyzer, mô hình AST, formatter, validator, CLI, editor integration, language server, debugger, hệ thống kiểm thử, tài liệu và quy trình phát hành. Không phải DSL nào cũng cần toàn bộ thành phần, nhưng các thành phần được chọn phải dựa trên cùng một đặc tả và mô hình ngôn ngữ.

Hãy bắt đầu bằng grammar rõ ràng, parser đáng tin cậy, diagnostics có vị trí và bộ kiểm thử đại diện. Khi nhu cầu tăng, bổ sung formatter, language server, debugger, quản lý phiên bản và công cụ vận hành. Một toolchain nhất quán giúp người dùng viết DSL dễ hơn, giúp nhóm phát hiện lỗi sớm và giúp ngôn ngữ được bảo trì an toàn trong suốt vòng đời sản phẩm.
