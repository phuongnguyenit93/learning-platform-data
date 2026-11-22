# Truy vết biến đổi

## 1. Truy vết biến đổi trong compiler và DSL

Trong quá trình biên dịch hoặc thông dịch một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL), chương trình thường đi qua nhiều bước biến đổi. Văn bản nguồn được phân tích thành cây cú pháp, kiểm tra ngữ nghĩa, chuyển thành mã trung gian, tối ưu hóa rồi được hạ xuống mã đích hoặc kế hoạch thực thi. Mỗi bước có thể tạo ra một biểu diễn mới hoặc thay đổi biểu diễn hiện tại.

**Truy vết biến đổi (transformation tracing)** là việc ghi nhận và liên kết các thay đổi mà chương trình trải qua trong pipeline. Mục tiêu là trả lời được:

- Một cấu trúc trong biểu diễn hiện tại bắt nguồn từ đoạn DSL nào?
- Bước biến đổi nào đã tạo, sửa, gộp, di chuyển hoặc loại bỏ cấu trúc đó?
- Dữ liệu và quy tắc nào được dùng để quyết định phép biến đổi?
- Trạng thái chương trình trước và sau bước đó khác nhau ở đâu?
- Nếu kết quả cuối sai, có thể tìm ngược về bước làm thay đổi ngữ nghĩa ở đâu?

Ví dụ DSL:

~~~text
pipeline "paid-orders" {
    source "orders.csv"
    filter status == "PAID"
    filter amount > 100
    output "paid-orders.csv"
}
~~~

Compiler có thể thực hiện các bước:

1. Parse văn bản thành AST.
2. Resolve tên trường status và amount theo schema.
3. Lower hai câu lệnh filter thành các operation trong HIR.
4. Gộp hai filter thành một điều kiện kết hợp.
5. Đẩy điều kiện xuống database nếu backend hỗ trợ.
6. Sinh SQL hoặc execution plan.

Truy vết biến đổi ghi nhận mối quan hệ giữa các trạng thái đó. Nếu kết quả truy vấn thiếu đơn hàng hợp lệ, kỹ sư có thể xem AST ban đầu, HIR trước và sau khi gộp filter, truy vấn SQL được sinh và metadata giải thích phép đẩy điều kiện.

Truy vết biến đổi có liên quan đến debugging, source mapping, provenance, logging và kiểm toán compiler. Nó có thể được thực hiện ở nhiều mức: ghi sự kiện gọn, lưu snapshot IR, tạo diff giữa các pass hoặc xây dựng đồ thị nguồn gốc của từng node.

## 2. Biến đổi là gì?

Một phép biến đổi (transformation) nhận một biểu diễn chương trình hoặc một phần của nó, áp dụng quy tắc và tạo ra kết quả mới. Có thể mô tả khái quát:

~~~text
T : Representation_before -> Representation_after
~~~

Trong compiler, đầu vào và đầu ra có thể là AST, HIR, MIR, LIR, CFG, SSA hoặc bytecode. Một transformation có thể:

- Thay một cấu trúc bằng cấu trúc tương đương đơn giản hơn.
- Chuyển cú pháp cấp cao thành các thao tác cơ bản.
- Chuẩn hóa kiểu hoặc biểu thức.
- Tạo thêm node hoặc instruction.
- Gộp nhiều node thành một node.
- Di chuyển thao tác đến vị trí khác.
- Loại bỏ phần không còn cần thiết.
- Thay đổi luồng điều khiển hoặc cách lưu trữ dữ liệu.

Ví dụ constant folding:

~~~text
Before:
    %a = add 10, 20
    %b = multiply %a, 2

After:
    %b = 60
~~~

Phép biến đổi đã thay hai phép toán bằng một hằng số. Truy vết nên ghi nhận pass thực hiện, các instruction đầu vào, instruction đầu ra và vị trí nguồn liên quan.

### 2.1. Transformation pass

Một pass là đơn vị xử lý có mục đích xác định trên một biểu diễn. Ví dụ:

- Name resolution pass.
- Type checking pass.
- AST lowering pass.
- Constant folding pass.
- Dead code elimination pass.
- Control-flow simplification pass.
- Backend lowering pass.

Một pass có thể duyệt toàn bộ chương trình hoặc chỉ một phần. Nó có thể thực hiện một phép biến đổi hoặc lặp nhiều phép biến đổi đến khi đạt điểm cố định.

### 2.2. Pipeline các pass

Các pass thường được tổ chức thành chuỗi:

~~~text
AST
 |
 v
Resolve names
 |
 v
Check types
 |
 v
Lower to HIR
 |
 v
Optimize HIR
 |
 v
Lower to LIR
 |
 v
Generate target code
~~~

Thứ tự có ý nghĩa. Một pass có thể cần kết quả của pass trước hoặc làm mất thông tin mà pass sau không còn truy cập được. Truy vết giúp xác định trạng thái tại từng ranh giới.

## 3. Phân biệt truy vết biến đổi với log thông thường

Log thông thường ghi các sự kiện xảy ra trong ứng dụng, chẳng hạn compiler bắt đầu, hoàn tất hoặc phát sinh lỗi. Truy vết biến đổi tập trung vào quan hệ giữa các biểu diễn chương trình.

| Khía cạnh | Log thông thường | Truy vết biến đổi |
|---|---|---|
| Mục tiêu | Ghi lại sự kiện và trạng thái vận hành | Giải thích chương trình thay đổi qua các bước |
| Đối tượng | Process, request, thời gian, lỗi | Node, instruction, block, symbol, IR |
| Nội dung | Message, severity, timestamp | Pass, input/output, nguồn gốc, lý do biến đổi |
| Liên kết | Thường theo request hoặc execution ID | Theo node ID, source span, pass ID và lineage |
| Câu hỏi chính | Điều gì đã xảy ra trong hệ thống? | Cấu trúc nào đã đổi, do bước nào và bắt nguồn từ đâu? |

Hai cơ chế có thể bổ trợ nhau. Log ghi rằng pass OptimizeHIR mất 120 ms; transformation trace cho biết pass đó đã gộp hai filter và loại một node trung gian.

Không nên ghi mọi chi tiết IR vào log vận hành chung. Dữ liệu biến đổi có thể lớn và cần công cụ xem riêng, trong khi log vẫn giữ thông tin tổng quan và liên kết đến trace.

## 4. Những thông tin cần ghi nhận

Một transformation event có thể chứa các trường:

| Trường | Ý nghĩa |
|---|---|
| Trace ID | Định danh toàn bộ lần biên dịch hoặc lần phân tích |
| Pass ID | Định danh pass hoặc bước biến đổi |
| Event ID | Định danh sự kiện biến đổi |
| Parent event | Sự kiện trước đó hoặc sự kiện cha trong chuỗi biến đổi |
| Input representation | Biểu diễn được xử lý |
| Output representation | Biểu diễn sau khi xử lý |
| Node IDs | Các node hoặc instruction liên quan |
| Source spans | Vị trí trong DSL nguồn |
| Rule name | Tên quy tắc biến đổi |
| Reason | Lý do hoặc điều kiện áp dụng |
| Timestamp/duration | Thời điểm và thời lượng |
| Compiler version | Phiên bản compiler và pass |
| Configuration | Cấu hình tối ưu hoặc tùy chọn ảnh hưởng kết quả |
| Diagnostics | Cảnh báo hoặc lỗi phát sinh |

Không phải mọi trace đều cần lưu toàn bộ trường. Trace nhẹ có thể chỉ ghi pass, thời gian, số node trước/sau và mã quy tắc. Trace phục vụ điều tra lỗi compiler có thể cần snapshot hoặc diff chi tiết.

### 4.1. Định danh ổn định

Để liên kết một node qua nhiều bước, cần một cách định danh. Có thể dùng:

- Node ID nội bộ trong một compilation.
- Symbol ID cho khai báo và tham chiếu.
- Instruction ID trong IR.
- Source span kết hợp loại node và ngữ cảnh.
- ID lineage đại diện cho nguồn gốc của node sau biến đổi.

Source span không phải định danh duy nhất. Hai node có thể cùng lấy dữ liệu từ một đoạn nguồn, và một node được tổng hợp có thể bắt nguồn từ nhiều đoạn. Vì vậy, thường cần ID riêng kết hợp metadata nguồn.

### 4.2. Định danh theo compilation

Node ID chỉ cần duy nhất trong một lần biên dịch có thể được cấp tuần tự hoặc sinh từ bộ cấp ID. Nếu cần so sánh nhiều lần compile, có thể dùng stable ID dựa trên cấu trúc hoặc provenance. Không nên giả định ID tạm của hai lần compile khác nhau đại diện cho cùng node chỉ vì chúng có cùng số.

## 5. Truy vết theo từng tầng biểu diễn

Một compiler DSL có thể có nhiều tầng. Mỗi tầng giữ loại thông tin khác nhau, nên trace cần theo dõi được quá trình chuyển tiếp giữa chúng.

### 5.1. Từ văn bản nguồn đến AST

Parser chuyển token thành node AST. Truy vết ở tầng này có thể ghi:

- Source file và source span của node.
- Loại node được tạo.
- Token hoặc rule parser tạo ra node.
- Các node con được gắn vào node cha.
- Diagnostics khi một phần nguồn không phân tích được.

Ví dụ:

~~~text
Source:
    amount > 100

AST:
    GreaterThan
    ├── NameReference("amount")
    └── NumberLiteral(100)
~~~

AST node GreaterThan có thể giữ source span bao phủ toàn biểu thức; NameReference và NumberLiteral có span riêng.

### 5.2. Từ AST đến biểu diễn ngữ nghĩa

Name resolution và type checking có thể bổ sung symbol, type hoặc thông tin miền vào AST hoặc một bảng liên kết riêng.

Ví dụ:

~~~text
NameReference("amount")
    symbolId = field:orders.amount
    type = Decimal
    source = orders.dsl:4:12-4:18
~~~

Trace có thể ghi tham chiếu amount được resolve thành trường nào và schema phiên bản nào đã được sử dụng. Đây là thông tin quan trọng khi DSL có nhiều nguồn dữ liệu hoặc schema thay đổi.

### 5.3. Từ AST sang HIR

Lowering có thể chuyển một câu lệnh DSL thành operation ở mức miền:

~~~text
AST:
    Filter(amount > 100)

HIR:
    FilterRows(
        input = %orders,
        predicate = GreaterThan(Field(%row, "amount"), Constant(100))
    )
~~~

Trace cần giữ liên kết giữa node AST và operation HIR. Nếu một node AST tạo ra nhiều operation HIR, quan hệ là một-nhiều. Nếu nhiều node AST được gộp, quan hệ có thể là nhiều-một.

### 5.4. Từ HIR sang LIR hoặc CFG

Một operation miền có thể được phân rã thành nhiều instruction:

~~~text
HIR:
    FilterRows(%orders, amount > 100)

LIR:
    %row = iterator_next %orders
    %amount = load_field %row, "amount"
    %keep = greater_than %amount, 100
    branch_if %keep, keep_row, next_row
~~~

Trace nên liên kết các instruction mới với operation HIR đã tạo ra chúng. Nếu một operation được hạ thành một CFG gồm nhiều block, có thể ghi nhóm node hoặc lineage group.

### 5.5. Từ IR sang mã đích

Backend có thể sinh SQL, Java, bytecode hoặc execution plan. Source map liên kết output với IR và DSL. Truy vết cần giữ được chuỗi nguồn gốc qua các lần hạ tầng để người dùng có thể đi từ mã đích về biểu thức nguồn.

## 6. Source mapping và provenance

Source mapping trả lời một node hoặc đoạn mã hiện tại liên quan đến vị trí nào trong nguồn. Provenance (nguồn gốc) rộng hơn: nó mô tả một phần biểu diễn được hình thành từ những phần nào và qua những phép biến đổi nào.

### 6.1. Source span

Source span thường gồm:

- File hoặc document ID.
- Offset bắt đầu và kết thúc.
- Dòng và cột nếu cần hiển thị.
- Có thể thêm source version hoặc content hash.

Ví dụ:

~~~text
source = orders.dsl
startOffset = 142
endOffset = 157
line = 4
column = 12
~~~

Offset là vị trí trong nguồn gốc. Cách tính offset theo byte, UTF-16 code unit hay Unicode code point cần nhất quán giữa parser, IDE và diagnostic reporter.

### 6.2. Một nguồn tạo nhiều node

Một câu lệnh DSL có thể tạo nhiều node IR:

~~~text
filter amount > 100
~~~

Có thể tạo instruction đọc field, nạp hằng số, so sánh và branch. Tất cả có thể cùng tham chiếu source span của câu lệnh filter, nhưng cần ID riêng để phân biệt.

### 6.3. Nhiều nguồn tạo một node

Khi compiler gộp:

~~~text
filter status == "PAID"
filter amount > 100
~~~

thành:

~~~text
filter status == "PAID" and amount > 100
~~~

Node kết quả có provenance từ cả hai biểu thức nguồn. Không nên chỉ gán span của dòng đầu hoặc dòng cuối nếu cần giải thích đầy đủ nguồn gốc.

### 6.4. Nguồn tổng hợp

Compiler đôi khi tạo node không có đoạn nguồn trực tiếp, ví dụ:

- Phi node trong SSA.
- Temporary variable được tạo khi lowering.
- Runtime guard.
- Lệnh cleanup được thêm tự động.
- Check null hoặc check overflow do compiler chèn.

Các node này có thể được đánh dấu synthetic và liên kết với node nguồn đã kích hoạt việc tạo ra chúng hoặc với pass đã sinh chúng.

### 6.5. Provenance graph

Có thể mô hình hóa nguồn gốc thành đồ thị:

~~~text
Source node A ----\
                   \
                    > Transformed node C
                   /
Source node B ----/
~~~

Các cạnh có thể mang nhãn như derived-from, lowered-from, merged-from, split-from hoặc replaced-by. Đồ thị cho phép truy ngược một node đến nhiều node nguồn và truy xuôi một node nguồn đến các kết quả được tạo ra.

## 7. Snapshot, diff và event trace

Có ba cách phổ biến để lưu trạng thái biến đổi. Chúng có thể kết hợp trong cùng hệ thống.

### 7.1. Snapshot

Snapshot lưu toàn bộ biểu diễn ở một thời điểm:

~~~text
Snapshot 0: AST after parsing
Snapshot 1: AST after name resolution
Snapshot 2: HIR before optimization
Snapshot 3: HIR after optimization
Snapshot 4: LIR after lowering
~~~

Ưu điểm:

- Có thể mở lại trạng thái độc lập.
- Dễ so sánh trực quan giữa các bước.
- Hữu ích khi tái hiện lỗi hoặc gửi artifact cho nhóm compiler.

Hạn chế:

- Tốn bộ nhớ và dung lượng lưu trữ.
- Chương trình lớn có thể tạo snapshot rất lớn.
- Cần định dạng serialization và quản lý phiên bản.

### 7.2. Diff

Diff chỉ lưu phần khác nhau giữa hai trạng thái:

~~~text
Before:
    Filter A
    Filter B

After:
    Filter Combined

Changes:
    removed: Filter A
    removed: Filter B
    added: Filter Combined
    rule: MergeAdjacentFilters
~~~

Diff tiết kiệm hơn snapshot đầy đủ trong nhiều trường hợp và làm nổi bật thay đổi. Tuy nhiên, để tái dựng trạng thái, cần snapshot nền và chuỗi diff có thứ tự, không bị thiếu.

### 7.3. Event trace

Event trace ghi lại từng hành động:

~~~text
pass.started: MergeFilters
node.visited: filter-12
node.visited: filter-13
transform.applied: MergeAdjacentFilters
node.created: filter-27
node.removed: filter-12
node.removed: filter-13
pass.completed: MergeFilters
~~~

Event trace mô tả lịch sử thao tác, có thể dùng để giải thích vì sao kết quả hiện tại xuất hiện. Tuy nhiên, event cần đủ thông tin để liên kết node và trạng thái. Nếu chỉ ghi message tự do, việc dựng lại quan hệ sẽ khó.

### 7.4. Chọn chiến lược lưu trữ

| Chiến lược | Phù hợp khi | Chi phí chính |
|---|---|---|
| Snapshot đầy đủ | Debug một chương trình cụ thể, cần tái hiện trạng thái | Dung lượng lớn |
| Diff giữa các pass | Muốn xem thay đổi và tiết kiệm lưu trữ | Cần trạng thái nền và chuỗi diff đầy đủ |
| Event trace | Cần lịch sử và lý do từng hành động | Thiết kế schema sự kiện và liên kết |
| Hybrid | Hệ thống lớn cần cân bằng chi tiết và dung lượng | Quản lý nhiều dạng artifact |

Một chiến lược hybrid có thể lưu snapshot ở ranh giới pass lớn, diff cho các pass tối ưu và event chi tiết khi bật chế độ debug.

## 8. Truy vết pass và pass manager

Pass manager điều phối các bước biến đổi, thứ tự chạy, điều kiện áp dụng và phân tích phụ trợ. Đây là vị trí tự nhiên để tích hợp tracing.

### 8.1. Pass identity

Mỗi pass nên có tên ổn định và phiên bản hoặc build identifier. Ví dụ:

~~~text
pass.name = "ConstantFolding"
pass.version = "3"
pass.instance = 18
~~~

Tên ổn định giúp nhóm phát triển so sánh trace giữa các lần chạy. Version hoặc build ID giúp phân biệt hành vi giữa các phiên bản compiler.

### 8.2. Pass input và output

Ở mức tổng quan, manager có thể ghi:

- Loại IR đầu vào.
- Số block, node hoặc instruction trước pass.
- Loại IR đầu ra.
- Số block, node hoặc instruction sau pass.
- Thời gian thực thi.
- Số thay đổi được áp dụng.
- Trạng thái thành công hoặc lỗi.

Các số liệu này giúp phát hiện pass nào làm IR tăng kích thước bất thường hoặc tiêu tốn nhiều thời gian.

### 8.3. Pass dependency

Một pass có thể yêu cầu phân tích đã được tính trước, chẳng hạn dominator tree hoặc alias analysis. Nếu pass thay đổi CFG, một số kết quả phân tích cũ có thể mất hiệu lực.

Trace có thể ghi:

- Phân tích nào được dùng.
- Phân tích nào được cập nhật.
- Phân tích nào bị invalidated.
- Pass nào cần chạy lại.

Điều này hữu ích khi kết quả tối ưu phụ thuộc vào dữ liệu phân tích được cache.

### 8.4. Pass lặp đến điểm cố định

Một số pass manager chạy một nhóm pass nhiều lần cho đến khi không còn thay đổi hoặc đạt giới hạn:

~~~text
repeat:
    changed = false
    changed |= constantFold()
    changed |= simplifyBranches()
    changed |= eliminateDeadCode()
until not changed or iterationLimit
~~~

Trace cần ghi số vòng lặp, pass nào tạo thay đổi và lý do dừng. Nếu dừng do iteration limit, trạng thái đó khác với đạt điểm cố định.

### 8.5. Pass thất bại

Nếu pass phát hiện IR không hợp lệ hoặc phát sinh exception, trace nên ghi:

- Pass đang chạy.
- IR đầu vào hoặc snapshot gần nhất.
- Diagnostics và vị trí liên quan.
- Pass trước đó đã hoàn tất.
- Compiler có hủy compilation hay tiếp tục theo chính sách.

Không nên ghi nhận pass thất bại như một lần biến đổi thành công chỉ vì nó đã tạo một phần output tạm.

## 9. Truy vết một phép biến đổi cụ thể

Một transformation event chi tiết có thể được biểu diễn:

~~~text
TransformationEvent {
    eventId
    traceId
    passId
    rule
    inputNodeIds[]
    outputNodeIds[]
    sourceOrigins[]
    reason
    beforeHash
    afterHash
}
~~~

Đây là cấu trúc khái niệm. Trường dữ liệu thực tế tùy hệ thống.

### 9.1. Một-một

Một node được thay bằng một node khác:

~~~text
Before: Add(x, 0)
After:  x
Rule:   AddZero
~~~

Output node có thể kế thừa provenance từ node Add và node con x, đồng thời event ghi rõ hằng số 0 đã bị loại.

### 9.2. Một-nhiều

Một node cấp cao được phân rã:

~~~text
Before: ForEach(items, body)

After:
    iterator = create_iterator(items)
    loop_header:
        item = iterator_next(iterator)
        ...
~~~

Một AST node có thể tạo nhiều block và instruction. Trace cần lưu danh sách output node IDs và quan hệ derived-from.

### 9.3. Nhiều-một

Nhiều node được gộp:

~~~text
Before:
    Filter(A)
    Filter(B)

After:
    Filter(And(A, B))
~~~

Node mới có nguồn gốc từ cả hai filter và các biểu thức con.

### 9.4. Nhiều-nhiều

Một phép tối ưu có thể tái cấu trúc toàn bộ vùng CFG, xóa vài block và tạo các block mới. Khi đó quan hệ không thể biểu diễn bằng một cặp node đơn giản. Có thể dùng group ID, region ID hoặc transformation graph để liên kết vùng đầu vào và đầu ra.

### 9.5. Loại bỏ node

Khi node bị xóa, trace vẫn cần ghi nhận nó đã tồn tại và lý do bị loại:

~~~text
removedNode = instruction-42
reason = "result is unused and instruction is pure"
pass = DeadCodeElimination
~~~

Nếu không ghi removal event, việc node biến mất có thể bị nhầm với lỗi tạo AST hoặc lỗi serialization.

## 10. Truy vết dữ liệu và luồng điều khiển

Biến đổi compiler thường tác động đến cả luồng dữ liệu lẫn luồng điều khiển.

### 10.1. Data-flow lineage

Data-flow lineage mô tả một giá trị được tạo từ những giá trị nào:

~~~text
price ----\
           > multiply ----\
quantity -/                \
                            > subtract -> total
discount -----------------/
~~~

Nếu một giá trị cuối sai, lineage giúp truy ngược đến operand hoặc phép tính gây ra sai lệch.

Trong IR, quan hệ này có thể lấy từ def-use chain, use-def chain hoặc metadata riêng. Khi optimizer thay thế một giá trị, lineage cần được cập nhật để không trỏ đến definition đã bị loại mà không có quan hệ thay thế.

### 10.2. Control-flow lineage

Control-flow lineage giải thích tại sao một block có thể chạy hoặc vì sao một nhánh bị loại:

- Điều kiện branch được tạo từ biểu thức DSL nào?
- Phép tối ưu nào chứng minh điều kiện luôn true hoặc false?
- Block nào trở nên unreachable?
- Cạnh nào bị loại và block nào được hợp nhất?

Thông tin này hữu ích khi một nhánh mà người dùng mong đợi không được thực thi.

### 10.3. Def-use chain sau biến đổi

Trong SSA, mỗi value có một definition duy nhất. Trace có thể liên kết:

- Definition instruction.
- Các use instruction.
- Phi node hợp nhất.
- Các phép biến đổi thay thế value.

Khi constant propagation thay value bằng hằng số, trace ghi nhận các use đã được thay và definition cũ có thể trở thành dead.

### 10.4. Bộ nhớ và side effect

Không phải mọi quan hệ dữ liệu đều là phép tính thuần. Load, store, I/O, gọi dịch vụ hoặc cập nhật trạng thái có thể tạo side effect.

Trace cần phân biệt:

- Giá trị được tính thuần.
- Đọc trạng thái có thể thay đổi.
- Ghi hoặc tác dụng phụ.
- Exception hoặc lỗi có thể quan sát.

Phân biệt này giúp giải thích vì sao optimizer được hoặc không được phép di chuyển, gộp hay loại một instruction.

## 11. Ví dụ: truy vết constant folding

Xét DSL:

~~~text
let limit = 10 * 2
filter amount > limit
~~~

### 11.1. AST sau parsing

~~~text
VariableDeclaration("limit")
└── Multiply
    ├── Number(10)
    └── Number(2)

Filter
└── GreaterThan
    ├── NameReference("amount")
    └── NameReference("limit")
~~~

### 11.2. Sau name resolution

Tham chiếu limit được liên kết đến khai báo limit. amount được liên kết đến field của schema nguồn. Type checker xác nhận phép nhân và so sánh có kiểu tương thích.

### 11.3. HIR trước tối ưu

~~~text
%a = constant 10
%b = constant 2
%limit = multiply %a, %b
%amount = load_field "amount"
%condition = greater_than %amount, %limit
filter_rows where %condition
~~~

### 11.4. Event constant folding

~~~text
pass = ConstantFolding
rule = FoldMultiplyConstants
inputs = [%a, %b, %limit]
output = [%limit]
reason = "both operands are compile-time constants"
replacement = constant 20
~~~

### 11.5. HIR sau tối ưu

~~~text
%limit = constant 20
%amount = load_field "amount"
%condition = greater_than %amount, %limit
filter_rows where %condition
~~~

Trace liên kết giá trị 20 với biểu thức nguồn 10 * 2. Nếu người dùng xem IR cuối, họ vẫn có thể điều hướng về biểu thức gốc và xem pass ConstantFolding đã thực hiện phép thay thế.

## 12. Ví dụ: truy vết gộp filter và predicate pushdown

Nguồn DSL:

~~~text
pipeline "paid-large-orders" {
    source "orders"
    filter status == "PAID"
    filter amount > 100
    output "result"
}
~~~

HIR trước tối ưu:

~~~text
%orders = read_table("orders")
%paid = filter_rows %orders where status == "PAID"
%large = filter_rows %paid where amount > 100
write_table %large to "result"
~~~

### 12.1. Gộp hai filter

Sau phép biến đổi:

~~~text
%orders = read_table("orders")
%selected = filter_rows %orders
    where status == "PAID" AND amount > 100
write_table %selected to "result"
~~~

Trace nên lưu hai node filter đầu vào, node filter đầu ra, source origins của cả hai điều kiện và rule MergeAdjacentFilters.

### 12.2. Đẩy điều kiện xuống nguồn

Nếu backend hỗ trợ SQL, HIR có thể được hạ thành:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID' AND amount > 100
~~~

Trace cần ghi backend và capability đã dùng, đồng thời liên kết đoạn SQL với hai điều kiện nguồn.

### 12.3. Điều kiện an toàn

Gộp hoặc đẩy filter không phải lúc nào cũng an toàn. Cần xem xét:

- Các biểu thức có thuần và xác định không?
- Có thứ tự đánh giá hoặc exception quan sát được không?
- Null và kiểu dữ liệu được xử lý giống nhau không?
- Database có cùng semantics so sánh với DSL không?
- Có hàm tùy chỉnh hoặc locale-specific collation không?

Trace có thể ghi rule được áp dụng và điều kiện đã xác nhận. Nếu không áp dụng, có thể ghi lý do bị từ chối trong chế độ explain để hỗ trợ người phát triển hiểu quyết định của optimizer.

## 13. Truy vết quyết định tối ưu hóa

Biết một phép biến đổi đã xảy ra đôi khi chưa đủ. Kỹ sư còn cần biết vì sao optimizer chọn hoặc không chọn phép biến đổi.

### 13.1. Applied transformation

Khi áp dụng, ghi:

- Tên rule.
- Node hoặc region liên quan.
- Điều kiện áp dụng đã thỏa mãn.
- Thay đổi cấu trúc.
- Chi phí ước lượng trước và sau nếu có.

### 13.2. Rejected transformation

Khi không áp dụng, có thể ghi lý do:

~~~text
optimization = PredicatePushdown
status = rejected
reason = "backend comparison semantics are not equivalent for this expression"
source = orders.dsl:4:12-4:30
~~~

Thông tin này giúp giải thích vì sao một tối ưu mong đợi không xuất hiện. Không nên ghi mọi lần thử thất bại trong chế độ mặc định nếu số lượng quá lớn; có thể bật chế độ explain chi tiết.

### 13.3. Cost model

Một số optimizer dùng cost model để so sánh kế hoạch:

- Số hàng ước lượng.
- Kích thước dữ liệu.
- Chi phí I/O.
- Chi phí CPU.
- Số lần trao đổi dữ liệu.
- Độ trễ dự kiến.

Trace có thể ghi input statistics và cost estimate của các phương án. Đây là ước lượng, không phải số đo thực tế. Nên đánh dấu rõ estimated và actual để tránh hiểu nhầm.

### 13.4. Explain plan

Explain plan là cách trình bày kế hoạch hoặc quyết định tối ưu ở dạng người dùng có thể đọc. Nó có thể hiển thị:

- Operation tree.
- Thứ tự các bước.
- Điều kiện lọc.
- Nguồn dữ liệu.
- Ước lượng chi phí.
- Pass hoặc rule đã biến đổi.

Explain plan có thể là sản phẩm trình bày từ transformation trace, nhưng hai khái niệm không đồng nhất. Trace giữ lịch sử và quan hệ nguồn gốc; explain plan thường tập trung vào kế hoạch hiện tại hoặc lý do lựa chọn.

## 14. Truy vết trong môi trường compiler nhiều backend

Một DSL có thể chạy trên nhiều backend, chẳng hạn SQL, Java hoặc VM bytecode. Mỗi backend có thể biến đổi HIR theo cách khác nhau.

~~~text
                  HIR
                /  |  \
               v   v   v
             SQL  Java  VM
               \   |   /
                execution
~~~

Truy vết cần phân biệt:

- Phần biến đổi chung trước khi chọn backend.
- Phần biến đổi riêng cho từng backend.
- Capability và cấu hình của backend.
- Source mapping từ từng output về DSL.

Nếu hai backend tạo kết quả khác nhau, trace cho phép so sánh các phép lowering riêng. Có thể cùng HIR nhưng SQL backend dùng phép so sánh database, còn Java backend dùng phép so sánh trong runtime; khác biệt semantics cần được xác định.

### 14.1. Backend-specific pass

Mỗi backend có thể có pass riêng:

- SQL: predicate pushdown, join reordering, projection pruning.
- Java: inline method, boxing elimination, chọn API runtime.
- VM: instruction selection, constant pool layout, jump optimization.

Pass ID nên có namespace hoặc metadata backend để tránh nhầm các pass trùng tên.

### 14.2. So sánh backend

Để so sánh, cần giữ cùng:

- Phiên bản DSL và schema.
- Input data hoặc snapshot.
- Cấu hình compiler chung.
- Semantics của các hàm miền.

Sau đó so sánh kết quả, diagnostics và side effect. Trace cấu trúc giúp giải thích khác biệt, nhưng không thay thế kiểm thử tương đương hành vi.

## 15. Truy vết biến đổi trong IDE và công cụ phát triển

Transformation trace có thể hỗ trợ các tính năng tương tác:

### 15.1. Điều hướng từ DSL đến IR

Người dùng chọn một biểu thức trong editor và xem các node IR được tạo từ nó. Điều này hữu ích khi một câu lệnh DSL cấp cao được hạ thành nhiều thao tác.

### 15.2. Điều hướng từ IR về nguồn

Người phát triển compiler chọn instruction trong IR viewer và quay về source span. Nếu instruction tổng hợp, IDE có thể hiển thị pass đã tạo nó và các node nguồn liên quan.

### 15.3. So sánh trước và sau

Một diff viewer có thể tô rõ:

- Node được thêm.
- Node bị xóa.
- Node được thay thế.
- Node được di chuyển.
- Thuộc tính hoặc kiểu bị thay đổi.

Với biểu diễn dạng đồ thị, diff có thể cần ghép node theo ID hoặc lineage thay vì chỉ so sánh văn bản tuần tự.

### 15.4. Explain tại vị trí

Khi người dùng chọn một operation trong plan, công cụ có thể trả lời:

- Operation bắt nguồn từ câu lệnh nào?
- Nó được tạo bởi pass nào?
- Vì sao nó được giữ lại?
- Có phép tối ưu nào đã bị từ chối?

### 15.5. Incremental compilation

Trong IDE, mỗi lần sửa một đoạn nguồn có thể chỉ làm mất hiệu lực một phần AST hoặc IR. Trace nên ghi compilation version và phần nào được tái sử dụng, phần nào được tạo lại. Điều này giúp hiểu vì sao một node được giữ từ cache hoặc được phân tích mới.

## 16. Determinism và khả năng tái lập

Một trace hữu ích cho điều tra cần gắn với đủ thông tin để tái lập phép biến đổi.

### 16.1. Compiler version

Pass có thể thay đổi thuật toán giữa các phiên bản. Cần ghi version hoặc build ID của compiler.

### 16.2. Configuration

Tùy chọn như optimization level, target architecture, feature flag và backend capability có thể làm thay đổi pipeline. Trace cần lưu các tùy chọn ảnh hưởng đến kết quả.

### 16.3. Input identity

Nếu nguồn DSL hoặc schema thay đổi, cùng một lệnh compile có thể cho kết quả khác. Có thể ghi content hash hoặc version ID của input, nhưng cần tránh ghi nội dung nhạy cảm.

### 16.4. External metadata

Schema database, plugin version, environment profile hoặc metadata dịch vụ có thể ảnh hưởng lowering. Nếu những dữ liệu này được tải động, trace nên ghi version hoặc snapshot reference.

### 16.5. Nondeterministic pass

Một số hệ thống dùng parallel compilation, randomization hoặc heuristic có thể tạo thứ tự hoặc kế hoạch khác nhau giữa các lần chạy. Nếu cần tái lập, cần ghi seed, thứ tự pass hoặc các yếu tố nondeterministic liên quan.

### 16.6. Hash trạng thái

Hash của biểu diễn trước và sau pass giúp nhận diện trạng thái và kiểm tra artifact có bị thay đổi:

~~~text
beforeHash = sha256(serializedInput)
afterHash = sha256(serializedOutput)
~~~

Hash chỉ hữu ích nếu serialization có tính ổn định hoặc được chuẩn hóa. Nếu thứ tự map hoặc metadata không ổn định, cùng một IR logic có thể tạo hash khác nhau.

## 17. Hiệu năng và dung lượng của transformation trace

Ghi chi tiết mọi node ở mọi pass có thể làm compiler chậm và tạo lượng dữ liệu lớn. Hệ thống cần các mức trace.

### 17.1. Mức tổng quan

Chỉ ghi:

- Pass bắt đầu/kết thúc.
- Thời gian.
- Số node hoặc instruction trước/sau.
- Trạng thái và diagnostics.

Mức này phù hợp để theo dõi hiệu năng compiler thường xuyên.

### 17.2. Mức diff

Ghi các node thêm, xóa và sửa, cùng source lineage. Phù hợp khi điều tra một chương trình cụ thể.

### 17.3. Mức snapshot

Lưu toàn bộ IR trước/sau một số pass được chọn. Phù hợp với miscompilation hoặc lỗi khó tái hiện.

### 17.4. Sampling và giới hạn

Có thể:

- Chỉ bật trace chi tiết cho một compilation ID.
- Lấy mẫu một tỷ lệ compilation.
- Chỉ ghi các pass có thời gian hoặc thay đổi vượt ngưỡng.
- Giới hạn kích thước artifact.
- Cắt bớt phần payload nhưng giữ metadata chỉ rõ trace bị giới hạn.

Không nên âm thầm bỏ sự kiện khiến trace có vẻ đầy đủ. Nếu bị giới hạn, cần đánh dấu dropped events hoặc truncated artifact.

### 17.5. Tránh làm thay đổi hành vi compiler

Instrumentation nên quan sát trạng thái mà không làm thay đổi thứ tự hoặc kết quả biến đổi. Việc serialize IR, gọi logger hoặc tạo snapshot không nên sửa node, chạy lại semantic action hay thay đổi cache của pass.

## 18. Bảo mật và quyền riêng tư

IR và trace có thể chứa thông tin nhạy cảm:

- Literal trong cấu hình.
- Đường dẫn nội bộ.
- Tên bảng hoặc schema.
- Endpoint và tên tài nguyên.
- Giá trị constant được nhúng trong chương trình.
- Thông tin người dùng hoặc dữ liệu mẫu.

Một số nguyên tắc:

1. Chỉ bật trace chi tiết cho đối tượng hoặc nhóm có quyền.
2. Che hoặc loại bỏ secret và credential.
3. Giới hạn thời gian lưu snapshot.
4. Kiểm soát quyền tải và chia sẻ artifact.
5. Không đưa toàn bộ input data vào trace nếu chỉ cần schema hoặc ID.
6. Ghi nhận khi nội dung bị redact để người đọc hiểu giới hạn của trace.
7. Bảo đảm trace ID không chứa thông tin nhận dạng nhạy cảm.

Trace phục vụ debugging không nên trở thành một bản sao không kiểm soát của mọi dữ liệu mà compiler đã xử lý.

## 19. Triển khai transformation tracing trong Java

Một thiết kế đơn giản có thể định nghĩa interface cho pass và một listener nhận sự kiện trước/sau biến đổi.

### 19.1. Mô hình sự kiện

~~~java
import java.time.Duration;
import java.util.List;

record TransformationEvent(
    String traceId,
    String passName,
    String ruleName,
    List<String> inputNodeIds,
    List<String> outputNodeIds,
    List<String> sourceOrigins,
    String reason,
    Duration duration
) {
}
~~~

Đây là mô hình minh họa. Hệ thống thực tế có thể dùng ID có kiểu riêng, source span có cấu trúc và timestamp.

### 19.2. Listener

~~~java
interface TransformationTraceListener {
    void onTransformation(TransformationEvent event);
}
~~~

Pass gọi listener sau khi đã xác định kết quả. Listener có thể ghi event vào buffer, file hoặc hệ thống quan sát. Cần quy định lỗi từ listener có làm compilation thất bại hay không; trong nhiều hệ thống, lỗi instrumentation không nên âm thầm thay đổi ngữ nghĩa compiler.

### 19.3. Pass với trace

~~~java
final class ConstantFoldingPass {
    private final TransformationTraceListener listener;

    ConstantFoldingPass(TransformationTraceListener listener) {
        this.listener = listener;
    }

    IrModule run(IrModule input) {
        long started = System.nanoTime();

        IrModule output = foldConstants(input);

        long elapsed = System.nanoTime() - started;
        listener.onTransformation(new TransformationEvent(
            "compile-123",
            "ConstantFolding",
            "FoldConstantExpression",
            List.of("node-10", "node-11"),
            List.of("node-20"),
            List.of("orders.dsl:4:12-4:20"),
            "Both operands are constants",
            Duration.ofNanos(elapsed)
        ));

        return output;
    }

    private IrModule foldConstants(IrModule input) {
        // Transformation implementation omitted.
        return input;
    }
}
~~~

Các kiểu IrModule và node ID là giả định. Ví dụ tập trung vào điểm tích hợp listener. Một pass thực tế nên tạo event dựa trên thay đổi thật, không dùng ID hoặc lý do cố định như ví dụ.

### 19.4. Buffer và ghi bất đồng bộ

Nếu mỗi event đều ghi đồng bộ ra đĩa hoặc mạng, trace có thể làm chậm compiler đáng kể. Có thể dùng buffer theo compilation và ghi theo lô. Tuy nhiên cần:

- Giới hạn dung lượng buffer.
- Chính sách khi buffer đầy.
- Đảm bảo event có thứ tự trong phạm vi cần thiết.
- Flush khi compilation kết thúc hoặc thất bại.
- Ghi nhận event bị mất nếu có.

### 19.5. Snapshot bất biến

Nếu lưu snapshot, nên dùng biểu diễn bất biến hoặc bản sao độc lập. Không giữ reference đến IR mutable rồi serialize sau khi pass tiếp theo đã sửa nó; khi đó snapshot có thể phản ánh trạng thái mới thay vì trạng thái tại thời điểm event.

## 20. Điều tra lỗi compiler bằng transformation trace

Một miscompilation xảy ra khi chương trình được biên dịch hoặc tối ưu nhưng hành vi không đúng với ngữ nghĩa nguồn. Trace giúp thu hẹp vị trí sai lệch.

Quy trình điều tra:

1. Thu thập DSL nguồn, phiên bản compiler, cấu hình và input cần thiết.
2. Tái hiện compilation với trace phù hợp.
3. Xác định đầu ra hoặc hành vi sai.
4. Tìm pass cuối cùng làm trạng thái thay đổi đáng kể trước khi kết quả sai xuất hiện.
5. So sánh IR trước và sau pass đó.
6. Kiểm tra điều kiện áp dụng rule và metadata được dùng.
7. Xác định source origins của node bị thay đổi.
8. Tạo trường hợp tối giản tái hiện lỗi.
9. Kiểm tra lại bằng interpreter hoặc backend khác nếu có.
10. Xác nhận bản sửa giữ nguyên hành vi mong đợi và không phá các trường hợp liên quan.

### 20.1. Binary search trên các ranh giới pass

Nếu có snapshot tại nhiều ranh giới, có thể tìm khoảng pass đầu tiên tạo ra trạng thái sai bằng cách so sánh từng nửa pipeline. Cách này giống binary search trên thứ tự pass, nhưng cần biết cách xác định một IR có sai hay không.

### 20.2. Pass isolation

Có thể chạy compiler với một pass bị tắt hoặc chạy riêng pass nghi vấn trên IR đã lưu. Nếu lỗi biến mất khi tắt pass, đó là bằng chứng hữu ích nhưng chưa đủ để kết luận: pass trước hoặc sau có thể phụ thuộc vào thứ tự hoặc invariant của pass đó.

### 20.3. Minimal reproducer

Rút gọn DSL đến chương trình nhỏ nhất vẫn tái hiện lỗi giúp phân tích rule và điều kiện biến đổi. Trace lineage hỗ trợ xác định phần nguồn có liên quan, nhưng việc rút gọn vẫn cần bảo toàn điều kiện kích hoạt lỗi.

### 20.4. So sánh kết quả trước/sau tối ưu

Chạy cùng chương trình ở chế độ không tối ưu và có tối ưu, rồi so sánh kết quả, lỗi và side effect. Nếu chỉ khác khi bật một nhóm pass, có thể tiếp tục cô lập pass cụ thể. Cần kiểm soát input và môi trường để tránh nhầm khác biệt dữ liệu với lỗi compiler.

## 21. Truy vết trong compiler gia tăng

Compiler gia tăng chỉ xử lý phần bị ảnh hưởng sau khi nguồn thay đổi. Transformation trace cần phân biệt kết quả được tính mới và kết quả được tái sử dụng.

Ví dụ người dùng sửa:

~~~text
filter amount > 100
~~~

thành:

~~~text
filter amount > 200
~~~

Compiler có thể:

- Parse lại dòng đã sửa.
- Resolve lại biểu thức liên quan.
- Vô hiệu hóa HIR node phụ thuộc.
- Giữ nguyên IR của các pipeline độc lập.
- Chạy lại optimizer cho vùng bị ảnh hưởng.

Trace có thể ghi cache hit, cache invalidation, node được tái sử dụng và node được tạo mới.

### 21.1. Dependency graph

Để xác định phần cần làm lại, compiler có thể lưu quan hệ phụ thuộc giữa:

- Source file.
- Declaration.
- Symbol.
- Type.
- IR node.
- Pass result.
- Schema hoặc metadata ngoài.

Khi một đầu vào thay đổi, các node phụ thuộc được đánh dấu stale và cần tính lại.

### 21.2. Cache key

Cache key nên bao gồm mọi yếu tố ảnh hưởng đến kết quả:

- Nội dung nguồn hoặc hash.
- Phiên bản compiler/pass.
- Cấu hình liên quan.
- Phiên bản schema.
- Backend và target.
- Dependency IDs.

Nếu thiếu một yếu tố, compiler có thể tái sử dụng kết quả cũ không còn hợp lệ.

### 21.3. Trace của kết quả tái sử dụng

Khi node được lấy từ cache, nên ghi nguồn gốc lần tạo trước hoặc cache artifact ID. Điều đó giúp người điều tra biết node không được tạo trong compilation hiện tại.

## 22. Tiêu chí đánh giá một hệ thống truy vết

Một hệ thống tracing hữu ích cần cân bằng giữa khả năng giải thích và chi phí.

| Tiêu chí | Câu hỏi cần trả lời |
|---|---|
| Coverage | Có ghi nhận các pass và thay đổi quan trọng không? |
| Provenance | Có thể truy ngược node về nguồn không? |
| Identity | Node và event có ID đủ rõ không? |
| Ordering | Có biết thứ tự các phép biến đổi không? |
| Reproducibility | Có lưu version và config ảnh hưởng kết quả không? |
| Fidelity | Snapshot hoặc diff có phản ánh đúng trạng thái tại thời điểm ghi không? |
| Performance | Chi phí tracing có kiểm soát được không? |
| Privacy | Trace có bảo vệ dữ liệu nhạy cảm không? |
| Usability | Kỹ sư có thể tìm và hiểu thay đổi không? |
| Failure handling | Có biết trace bị thiếu hoặc bị cắt không? |

Không phải mọi môi trường đều cần tracing ở mức node. Một DSL cấu hình có thể chỉ cần diagnostics và explain plan; compiler tối ưu phức tạp có thể cần event lineage và snapshot theo pass.

## 23. Những sai lầm thường gặp

### 23.1. Chỉ lưu IR cuối cùng

IR cuối giúp xem chương trình được đưa đến backend, nhưng không cho biết vì sao nó có hình dạng đó. Khi cần điều tra lỗi biến đổi, cần trace ở các ranh giới quan trọng hoặc khả năng tái chạy pass.

### 23.2. Chỉ lưu tên pass và thời gian

Thông tin đó hữu ích cho profiling nhưng không đủ để giải thích node nào đã thay đổi. Nên bổ sung node IDs, số lượng thay đổi, rule name và provenance khi cần điều tra.

### 23.3. Dùng source span làm ID duy nhất

Một đoạn nguồn có thể tạo nhiều node và một node có thể đến từ nhiều đoạn. Cần định danh node riêng và mô hình lineage.

### 23.4. Không ghi node bị loại

Node biến mất mà không có removal event khiến khó phân biệt tối ưu hợp lệ với lỗi trong lowering hoặc serialization. Hãy ghi lý do loại bỏ ở mức trace phù hợp.

### 23.5. Ghi snapshot mutable

Nếu snapshot giữ reference đến đối tượng IR sẽ tiếp tục bị sửa, dữ liệu lưu sau đó có thể không phải trạng thái tại thời điểm snapshot. Dùng bản sao bất biến hoặc serialize ngay.

### 23.6. Không ghi version và configuration

Trace không có compiler version, schema version hoặc optimization flags có thể không tái hiện được kết quả. Lưu metadata đủ để xác định môi trường biến đổi.

### 23.7. Trace làm thay đổi hành vi compiler

Instrumentation có thể gây side effect, thay đổi thứ tự hoặc tạo race condition nếu thiết kế không cẩn thận. Trace nên quan sát trạng thái và có chính sách concurrency rõ.

### 23.8. Ghi quá nhiều dữ liệu

Snapshot mọi node ở mọi pass có thể gây tốn bộ nhớ và làm chậm compile. Dùng mức tracing, sampling, giới hạn và lưu artifact theo nhu cầu.

### 23.9. Không đánh dấu trace thiếu dữ liệu

Nếu buffer đầy hoặc một pass không hỗ trợ tracing, người dùng cần biết trace không đầy đủ. Không nên trình bày một chuỗi bị thiếu event như lịch sử hoàn chỉnh.

### 23.10. Nhầm trace với chứng minh tính đúng

Trace giải thích compiler đã làm gì, nhưng bản thân nó không chứng minh phép biến đổi bảo toàn ngữ nghĩa. Tính đúng cần được hỗ trợ bằng đặc tả, verifier, kiểm thử và phương pháp chứng minh phù hợp.

## 24. Quy trình thiết kế transformation tracing

Khi bổ sung tracing cho compiler DSL, có thể đi theo các bước:

1. **Xác định câu hỏi cần trả lời.** Debug miscompilation, explain optimization, profiling hay kiểm toán nguồn gốc?
2. **Chọn ranh giới quan sát.** AST, HIR, LIR, pass hoặc backend.
3. **Định nghĩa ID.** Trace ID, pass ID, node ID, event ID và lineage ID.
4. **Định nghĩa source provenance.** Cách gắn source span và quan hệ một-nhiều/nhiều-một.
5. **Chọn dạng lưu.** Snapshot, diff, event hoặc hybrid.
6. **Tích hợp pass manager.** Ghi input/output, thời gian, trạng thái và invalidation của analysis.
7. **Ghi rule-level event.** Khi cần, lưu input nodes, output nodes và lý do áp dụng.
8. **Bảo toàn tính nhất quán.** Snapshot bất biến, thứ tự event và xử lý lỗi instrumentation.
9. **Thêm công cụ xem.** Diff, lineage graph, explain view và source navigation.
10. **Thiết lập giới hạn.** Sampling, buffer, dung lượng và retention.
11. **Bảo vệ dữ liệu.** Redaction, quyền truy cập và kiểm soát chia sẻ.
12. **Tích hợp tái lập.** Compiler version, configuration, schema và input identity.
13. **Kiểm chứng bằng tình huống thật.** Dùng một phép tối ưu có thể quan sát và xác nhận trace giải thích được thay đổi.

Mức triển khai nên tương xứng với nhu cầu. Bắt đầu từ pass-level metadata và source mapping thường dễ hơn việc xây ngay một đồ thị lineage hoàn chỉnh.

## 25. Câu hỏi tự kiểm tra

1. Truy vết biến đổi là gì và nó giúp ích gì trong compiler DSL?
2. Phân biệt transformation tracing với log vận hành thông thường.
3. Một transformation event nên lưu những trường thông tin nào?
4. Vì sao source span không đủ làm định danh duy nhất cho node?
5. Phân biệt snapshot, diff và event trace; nêu ưu nhược điểm của từng cách.
6. Mối quan hệ provenance một-một, một-nhiều và nhiều-một xuất hiện trong trường hợp nào?
7. Pass manager có thể cung cấp những thông tin nào cho transformation trace?
8. Data-flow lineage và control-flow lineage khác nhau ra sao?
9. Hãy mô tả trace cho phép constant folding biểu thức 10 * 2.
10. Vì sao optimizer cần ghi cả quyết định áp dụng và lý do từ chối phép biến đổi?
11. Source mapping cần được duy trì như thế nào khi một HIR node được hạ thành nhiều instruction?
12. Compiler nhiều backend cần dùng trace để so sánh những yếu tố nào?
13. Những metadata nào giúp tái lập một lần biên dịch?
14. Tracing chi tiết có thể ảnh hưởng hiệu năng và dung lượng như thế nào? Nêu cách giới hạn chi phí.
15. Vì sao snapshot của IR mutable cần được sao chép hoặc serialize ngay?
16. Hãy đề xuất cách dùng transformation trace để điều tra một miscompilation do dead code elimination.
