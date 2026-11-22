# Mã trung gian

## 1. Mã trung gian trong quá trình biên dịch và thông dịch

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) thường được viết để mô tả quy tắc, cấu hình, truy vấn hoặc quy trình trong một lĩnh vực cụ thể. Để thực hiện nội dung đó, công cụ DSL cần chuyển văn bản nguồn thành một dạng biểu diễn mà máy có thể phân tích, kiểm tra, tối ưu hóa và thực thi.

**Mã trung gian (Intermediate Representation — IR)** là một biểu diễn chương trình nằm giữa ngôn ngữ nguồn và dạng thực thi hoặc mã đích. IR giữ lại cấu trúc và ý nghĩa cần thiết cho các bước xử lý tiếp theo, đồng thời có thể loại bỏ một số chi tiết chỉ phục vụ cú pháp bề mặt.

Ví dụ, người dùng viết:

~~~text
pipeline "paid-orders" {
    source "orders.csv"
    filter status == "PAID" and amount > 100
    output "paid-orders.csv"
}
~~~

Parser có thể tạo AST gồm khai báo pipeline, nguồn dữ liệu, biểu thức lọc và đầu ra. Một bước lowering có thể chuyển AST sang IR mô tả rõ các thao tác đọc, lọc và ghi:

~~~text
%source = read_csv("orders.csv")
%condition1 = field(%source, "status") == "PAID"
%condition2 = field(%source, "amount") > 100
%selected = filter %source where (%condition1 AND %condition2)
write_csv(%selected, "paid-orders.csv")
~~~

Đây là IR minh họa, không phải cú pháp chuẩn của một công cụ cụ thể. Nó làm rõ các thao tác và giá trị trung gian để compiler có thể kiểm tra kiểu, tối ưu hóa hoặc chuyển sang một backend khác.

IR không nhất thiết là mã máy hay bytecode. Nó có thể là cây, đồ thị, danh sách lệnh, dạng ba địa chỉ, SSA, bytecode của một máy ảo hoặc một cấu trúc dữ liệu có kiểu riêng. Mức trừu tượng được chọn tùy mục tiêu của DSL và các backend cần hỗ trợ.

## 2. Vì sao compiler cần mã trung gian?

Nếu compiler chuyển trực tiếp mọi cấu trúc của DSL sang mã đích, parser, kiểm tra ngữ nghĩa, tối ưu hóa và backend có thể bị phụ thuộc chặt vào nhau. Khi thêm một cú pháp mới hoặc một backend mới, nhiều phần của hệ thống có thể phải thay đổi.

IR tạo ra một ranh giới giữa cách người dùng viết chương trình và cách hệ thống thực hiện chương trình.

Các mục đích chính:

1. **Tách ngôn ngữ nguồn khỏi backend.** Nhiều cú pháp DSL có thể được chuyển về cùng một IR, sau đó dùng chung các bước phân tích và tối ưu.
2. **Tách cú pháp khỏi ngữ nghĩa thực thi.** AST giữ cấu trúc gần nguồn; IR có thể biểu diễn rõ thao tác và luồng điều khiển.
3. **Chuẩn hóa chương trình.** Các dạng cú pháp khác nhau nhưng cùng ý nghĩa có thể được chuyển về một cấu trúc thống nhất.
4. **Tối ưu hóa.** Compiler có thể phân tích và biến đổi IR mà không phải xử lý trực tiếp mọi chi tiết của DSL.
5. **Hỗ trợ nhiều nền tảng.** Một IR có thể được dịch sang Java, SQL, bytecode, mã máy hoặc một workflow engine.
6. **Kiểm tra và gỡ lỗi.** IR có thể được in ra, lưu lại hoặc kiểm tra độc lập với parser.
7. **Tái sử dụng hạ tầng compiler.** Nhiều tính năng như phân tích luồng dữ liệu, kiểm tra kiểu hoặc sinh mã có thể dùng chung trên IR.

Một IR tốt giảm sự phụ thuộc giữa các thành phần. Tuy nhiên, thêm IR cũng tạo chi phí thiết kế, chuyển đổi và duy trì. DSL rất nhỏ, chỉ có một backend đơn giản, đôi khi có thể hoạt động tốt với AST trực tiếp. IR có giá trị rõ hơn khi ngôn ngữ có nhiều loại thao tác, cần tối ưu hoặc cần hỗ trợ nhiều đích thực thi.

## 3. Vị trí của IR trong compiler pipeline

Một pipeline biên dịch thường có cấu trúc:

~~~text
DSL source
    |
    v
Lexer / Parser
    |
    v
AST
    |
    v
Name resolution and type checking
    |
    v
Lowering to IR
    |
    v
IR validation and optimization
    |
    v
Backend lowering
    |
    v
Target code / bytecode / execution plan
    |
    v
Runtime or target platform
~~~

Đây là mô hình khái quát. Một compiler có thể có nhiều IR ở các mức khác nhau và nhiều bước chuyển đổi. Một số hệ thống thực hiện một phần kiểm tra ngữ nghĩa trong lúc tạo IR; một số khác dùng IR ngay từ đầu và không tạo AST riêng.

### 3.1. AST và IR

AST (Abstract Syntax Tree) thường phản ánh cấu trúc có ý nghĩa của ngôn ngữ nguồn. IR thường được tổ chức để phục vụ phân tích, tối ưu hoặc thực thi.

Ví dụ DSL:

~~~text
let total = price * quantity
output total
~~~

AST giản lược:

~~~text
Program
├── VariableDeclaration("total")
│   └── Multiply
│       ├── Name("price")
│       └── Name("quantity")
└── OutputStatement
    └── Name("total")
~~~

Một IR dạng lệnh:

~~~text
%0 = load price
%1 = load quantity
%2 = multiply %0, %1
store total, %2
%3 = load total
output %3
~~~

AST giữ khai báo và cấu trúc biểu thức theo ngôn ngữ. IR thể hiện các phép đọc, nhân, ghi và output thành những thao tác riêng.

| Tiêu chí | AST | IR |
|---|---|---|
| Trọng tâm | Cấu trúc cú pháp có ý nghĩa | Thao tác và quan hệ cần cho compiler/runtime |
| Quan hệ với DSL | Thường gần với cấu trúc nguồn | Có thể độc lập hơn với cú pháp nguồn |
| Chi tiết ngôn ngữ | Có thể giữ loại khai báo và biểu thức riêng | Có thể chuẩn hóa nhiều cấu trúc về một tập lệnh nhỏ |
| Tối ưu hóa | Có thể thực hiện | Thường thuận tiện hơn cho nhiều phép tối ưu |
| Backend | Có thể sinh mã trực tiếp | Có thể dùng chung nhiều backend |
| Thông tin nguồn | Thường gắn với vị trí nguồn | Cần giữ hoặc truyền source mapping để chẩn đoán |

Ranh giới không tuyệt đối. Một AST được chuẩn hóa có thể đóng vai trò IR; một IR dạng cây có thể trông giống AST. Điều quan trọng là mục đích và các bất biến của biểu diễn, không phải tên gọi.

### 3.2. Semantic analysis trước khi tạo IR

Trước khi lowering, compiler thường cần giải quyết tên, kiểm tra kiểu và xác nhận các quy tắc miền.

Ví dụ:

~~~text
filter amount > "large"
~~~

Parser có thể tạo AST hợp lệ vì cấu trúc biểu thức đúng. Nhưng nếu amount là số và "large" là chuỗi, phép so sánh có thể không hợp lệ theo kiểu. Compiler nên phát hiện lỗi trước khi tạo IR thực thi, hoặc đánh dấu lỗi rõ nếu IR được tạo để phục vụ phân tích tiếp.

### 3.3. Nhiều tầng IR

Một compiler có thể có:

- High-level IR (HIR): giữ các thao tác gần với khái niệm của DSL.
- Mid-level IR (MIR): chuẩn hóa cấu trúc, thể hiện luồng điều khiển và giá trị rõ hơn.
- Low-level IR (LIR): gần với lệnh máy ảo hoặc kiến trúc đích.

Tên gọi và số tầng không phải chuẩn bắt buộc. Mục tiêu là mỗi tầng có mức trừu tượng và hợp đồng rõ ràng.

## 4. Những dạng biểu diễn IR phổ biến

IR có nhiều hình thức. Không có một dạng phù hợp cho mọi compiler.

### 4.1. IR dạng cây

IR dạng cây giữ quan hệ bao chứa giữa các biểu thức và thao tác:

~~~text
Filter
├── Input
│   └── ReadCSV("orders.csv")
└── Condition
    └── GreaterThan
        ├── Field("amount")
        └── Constant(100)
~~~

Dạng cây gần với AST, dễ biểu diễn biểu thức lồng nhau và thuận tiện cho visitor đệ quy. Tuy nhiên, các giá trị được dùng nhiều lần hoặc các nhánh luồng điều khiển phức tạp có thể khó biểu diễn nếu chỉ dựa vào quan hệ cha-con.

### 4.2. IR dạng danh sách lệnh

Một danh sách lệnh tuyến tính biểu diễn mỗi thao tác thành một instruction:

~~~text
%1 = load_field "amount"
%2 = const 100
%3 = greater_than %1, %2
%4 = filter %input, %3
~~~

Mỗi lệnh có opcode, toán hạng và có thể có kết quả. Dạng này thuận tiện cho interpreter, kiểm tra instruction và các phép tối ưu cục bộ.

### 4.3. Three-address code

Three-address code (TAC) là dạng IR trong đó mỗi lệnh thường có tối đa một toán tử chính và một số lượng toán hạng nhỏ, thường là ba địa chỉ gồm đích và hai nguồn.

Ví dụ:

~~~text
t1 = price * quantity
t2 = discount * quantity
t3 = t1 - t2
~~~

TAC làm biểu thức phức tạp thành chuỗi bước đơn giản. Tên t1, t2, t3 là giá trị tạm. Dạng này giúp phân tích luồng dữ liệu và tối ưu hóa dễ hơn so với một biểu thức lồng sâu.

Tên three-address không có nghĩa mọi instruction trong mọi IR đều phải có đúng ba trường. Các lệnh nhảy, gọi hàm hoặc truy cập bộ nhớ có thể có cấu trúc riêng.

### 4.4. Control-flow graph

Control-flow graph (CFG) biểu diễn luồng điều khiển bằng các basic block và cạnh chuyển tiếp. Mỗi basic block là một chuỗi lệnh có một điểm vào và một điểm ra theo quy tắc của IR; luồng điều khiển chỉ chuyển vào block tại điểm đầu và rời block qua terminator ở cuối.

Ví dụ DSL:

~~~text
if amount > 100 {
    apply_discount()
} else {
    use_standard_price()
}
~~~

CFG giản lược:

~~~text
          [entry]
              |
       [check amount > 100]
          /         \
       true         false
        /             \
[apply_discount] [standard_price]
        \             /
          [merge]
              |
           [exit]
~~~

CFG hữu ích cho tối ưu hóa nhánh, phân tích khả năng đi tới, liveness, dominance và các phép biến đổi luồng điều khiển.

### 4.5. SSA form

Static Single Assignment (SSA) là một dạng IR trong đó mỗi biến hoặc giá trị ảo được gán đúng một lần. Khi giá trị có thể đến từ nhiều nhánh, SSA dùng phi node để hợp nhất các giá trị tại điểm gặp.

Ví dụ:

~~~text
if condition:
    x = 10
else:
    x = 20
use(x)
~~~

Biểu diễn SSA giản lược:

~~~text
entry:
    branch condition, then, else

then:
    x1 = 10
    jump merge

else:
    x2 = 20
    jump merge

merge:
    x3 = phi(x1, x2)
    use(x3)
~~~

Phi node chọn giá trị tương ứng với cạnh đi vào block merge. SSA làm quan hệ định nghĩa-sử dụng rõ ràng, hỗ trợ constant propagation, dead code elimination và nhiều phép phân tích khác.

### 4.6. Bytecode

Bytecode là mã lệnh ở dạng nhị phân hoặc dạng mã hóa gọn cho một máy ảo. Nó thường gần với instruction set của runtime hơn HIR hoặc TAC.

Ví dụ minh họa dạng stack bytecode:

~~~text
LOAD price
LOAD quantity
MUL
STORE total
~~~

Bytecode có thể được thông dịch trực tiếp hoặc được JIT compiler chuyển tiếp sang mã máy. Không phải mọi IR đều là bytecode; bytecode là một lựa chọn biểu diễn thường dùng khi DSL có runtime hoặc VM riêng.

## 5. High-level IR và low-level IR

IR có thể giữ khái niệm miền ở mức cao hoặc chuyển thành các thao tác gần máy hơn.

### 5.1. High-level IR

HIR có thể chứa lệnh như:

~~~text
%orders = read_table("orders")
%paid = filter_rows %orders where status == "PAID"
%totals = group_and_sum %paid by customer_id, amount
write_table %totals to "summary"
~~~

Các instruction như filter_rows hoặc group_and_sum gần với khái niệm DSL. HIR dễ ánh xạ về quy tắc miền, thuận tiện cho kiểm tra chính sách và tối ưu theo cấu trúc dữ liệu.

### 5.2. Low-level IR

LIR có thể phân rã các thao tác thành bước cơ bản:

~~~text
%row = iterator_next %source
%status = load_field %row, 0
%c1 = compare_equal %status, "PAID"
branch_if %c1, block_keep, block_next
~~~

LIR ít phụ thuộc vào cú pháp hoặc khái niệm cấp cao, nhưng thường cần nhiều instruction hơn và khó đọc hơn đối với người dùng miền.

### 5.3. Lý do giữ nhiều tầng

HIR thuận tiện cho tối ưu theo miền, chẳng hạn đẩy filter xuống database hoặc hợp nhất hai phép chiếu. LIR thuận tiện cho phân bổ thanh ghi, sinh bytecode hoặc mã máy. Giữ cả hai giúp mỗi bước làm việc ở mức phù hợp.

Không nên tạo quá nhiều tầng chỉ để chia nhỏ tên gọi. Mỗi IR nên có nhiệm vụ rõ, các phép chuyển đổi có thể kiểm tra và lợi ích đủ lớn để bù chi phí duy trì.

## 6. Cấu trúc dữ liệu của một IR

Một IR dạng instruction thường cần các thành phần:

| Thành phần | Mục đích |
|---|---|
| Module hoặc Program | Đơn vị chứa các hàm, block hoặc khai báo |
| Function | Nhóm instruction có đầu vào và kết quả |
| Basic block | Chuỗi instruction có luồng điều khiển tuần tự |
| Instruction | Một thao tác cụ thể |
| Operand | Giá trị, hằng số, symbol hoặc tham chiếu |
| Result | Giá trị do instruction tạo ra |
| Type | Kiểu của giá trị hoặc instruction |
| Terminator | Lệnh kết thúc block như return, branch hoặc jump |
| Source location | Liên kết về vị trí DSL gốc |
| Metadata | Thông tin phục vụ debug, tối ưu hoặc backend |

Ví dụ cấu trúc:

~~~text
Module
└── Function "calculate"
    ├── Parameters: price, quantity
    └── BasicBlock entry
        ├── %1 = multiply price, quantity
        ├── %2 = constant 0.08
        ├── %3 = multiply %1, %2
        └── return %3
~~~

### 6.1. Opcode

Opcode xác định loại thao tác, chẳng hạn add, multiply, load, store, call, branch hoặc return. Một tập opcode nhỏ giúp interpreter và optimizer đơn giản hơn.

Opcode nên có ngữ nghĩa rõ: kiểu toán hạng, số lượng toán hạng, kiểu kết quả, tác dụng phụ và điều kiện lỗi. Nếu cùng một opcode có hành vi không nhất quán tùy ngữ cảnh, các phép tối ưu có thể không an toàn.

### 6.2. Operand

Operand có thể là:

- Giá trị tạm do instruction khác tạo ra.
- Hằng số như số, chuỗi hoặc Boolean.
- Tham số của hàm.
- Symbol hoặc địa chỉ tài nguyên.
- Block đích của branch.
- Kiểu hoặc metadata tùy instruction.

Phân biệt operand với result giúp xác định quan hệ định nghĩa-sử dụng trong IR.

### 6.3. Terminator

Trong CFG, basic block thường kết thúc bằng một terminator như:

- return: kết thúc hàm.
- jump: chuyển đến block khác.
- branch: chọn một trong các block theo điều kiện.
- switch: chọn block theo giá trị.
- throw: chuyển sang xử lý ngoại lệ hoặc kết thúc theo mô hình lỗi.

Một block không nên có instruction thông thường sau terminator. Đây là một bất biến có thể được verifier kiểm tra.

## 7. Lowering: chuyển AST thành IR

Lowering là quá trình chuyển một biểu diễn ở mức trừu tượng cao sang biểu diễn cụ thể hơn hoặc gần với backend hơn. Quá trình này có thể diễn ra qua nhiều tầng.

Ví dụ AST:

~~~text
Multiply
├── Add
│   ├── Name("price")
│   └── Name("shipping")
└── Name("quantity")
~~~

Một lowering sang TAC:

~~~text
t1 = load price
t2 = load shipping
t3 = add t1, t2
t4 = load quantity
t5 = multiply t3, t4
~~~

### 7.1. Ánh xạ biểu thức

Với biểu thức, AST builder hoặc IR generator có thể đệ quy:

1. Hạ biểu thức con bên trái.
2. Hạ biểu thức con bên phải.
3. Tạo instruction cho toán tử hiện tại.
4. Trả về giá trị tạm do instruction tạo ra.

Đối với phép cộng, hàm lowering có thể trả về một IR value đại diện kết quả phép cộng. Nút cha dùng value đó làm operand.

### 7.2. Ánh xạ câu lệnh

Một câu lệnh gán:

~~~text
total = price * quantity
~~~

có thể thành:

~~~text
%price = load_variable "price"
%quantity = load_variable "quantity"
%product = multiply %price, %quantity
store_variable "total", %product
~~~

Nếu IR dùng SSA, phép gán có thể tạo một version mới của giá trị thay vì cập nhật một biến có tên.

### 7.3. Ánh xạ điều kiện

Một cấu trúc if/else trong AST thường được chuyển thành các block và branch:

~~~text
%condition = greater_than %amount, 100
branch_if %condition, then_block, else_block
~~~

Sau đó mỗi nhánh được hạ vào block riêng và kết thúc bằng jump đến block hợp nhất nếu cần.

### 7.4. Ánh xạ vòng lặp

Vòng lặp có thể được hạ thành các block kiểm tra điều kiện, thân vòng lặp và điểm thoát:

~~~text
entry:
    jump loop_header

loop_header:
    %continue = compare_less %index, %length
    branch_if %continue, loop_body, loop_exit

loop_body:
    process %index
    %next = add %index, 1
    jump loop_header

loop_exit:
    return
~~~

Đây là dạng minh họa. Cách xử lý biến vòng lặp và giá trị cập nhật phụ thuộc IR có dùng SSA hay không.

## 8. Basic block và control-flow graph

Basic block là một chuỗi instruction mà luồng điều khiển đi vào từ đầu block và đi ra ở cuối block. Không có nhánh vào giữa block; lệnh kết thúc quyết định nơi thực thi tiếp theo.

### 8.1. Xác định basic block

Các vị trí thường bắt đầu basic block:

- Entry của hàm.
- Đích của một branch hoặc jump.
- Instruction đứng ngay sau một terminator có thể chuyển luồng.

Một thuật toán chia block thường:

1. Xác định leader là instruction đầu tiên, mọi đích nhảy và instruction ngay sau lệnh chuyển luồng.
2. Mỗi leader mở đầu một block.
3. Gom các instruction tiếp theo cho đến trước leader kế tiếp hoặc terminator.
4. Tạo cạnh CFG từ terminator của mỗi block đến block đích.

### 8.2. Cạnh điều khiển

Một block có thể có:

- Không có successor nếu kết thúc hàm hoặc ném lỗi.
- Một successor nếu jump vô điều kiện.
- Hai successor nếu branch Boolean.
- Nhiều successor nếu switch hoặc dispatch.

Predecessor là các block có cạnh đi vào block hiện tại. Thông tin predecessor và successor hỗ trợ phân tích luồng điều khiển.

### 8.3. Reachability

Một block reachable nếu có đường đi từ entry đến block đó. Block không thể đi tới có thể chứa mã không bao giờ chạy và là ứng viên cho dead code elimination.

Không nên xóa block chỉ vì không thấy cạnh trực tiếp từ entry; cần duyệt toàn bộ đồ thị và xét các quy tắc đặc biệt của exception handler hoặc entry phụ.

### 8.4. Dominance

Block A dominate block B nếu mọi đường đi từ entry đến B đều phải đi qua A. Dominance giúp xác định vị trí có thể đặt một phép tính để nó luôn xảy ra trước một block khác, và là nền tảng cho một số thuật toán xây dựng SSA.

## 9. Static Single Assignment (SSA)

SSA làm cho mỗi giá trị được định nghĩa một lần. Thay vì gán lại cùng một biến, compiler tạo version mới cho mỗi lần định nghĩa.

Ví dụ nguồn:

~~~text
x = 1
x = x + 2
output x
~~~

SSA:

~~~text
x1 = 1
x2 = add x1, 2
output x2
~~~

### 9.1. Vì sao SSA hữu ích?

- Mỗi use có thể liên kết đến một definition cụ thể.
- Quan hệ def-use rõ ràng.
- Constant propagation dễ xác định giá trị.
- Dead code elimination có thể phát hiện definition không được dùng.
- Phân tích dữ liệu luồng và tối ưu hóa có thể đơn giản hơn.

### 9.2. Phi node

Khi một giá trị đến từ nhiều nhánh, compiler dùng phi node tại block hợp nhất:

~~~text
if condition:
    rate = 0.1
else:
    rate = 0.2
apply(rate)
~~~

SSA:

~~~text
entry:
    branch_if condition, then, else

then:
    rate1 = 0.1
    jump merge

else:
    rate2 = 0.2
    jump merge

merge:
    rate3 = phi [rate1, then], [rate2, else]
    call apply(rate3)
~~~

Phi node chọn giá trị theo predecessor đã đi vào block merge. Nó không phải lời gọi hàm thông thường; đây là một cấu trúc đặc biệt của SSA.

### 9.3. Phi node và block

Trong SSA cổ điển, phi node được đặt ở đầu basic block và có một đầu vào tương ứng với mỗi cạnh predecessor. Nếu CFG thay đổi, các phi node liên quan cần được cập nhật để giữ tính nhất quán.

Một số IR dùng block argument thay cho phi node tường minh. Khi đó, giá trị được truyền như tham số của block đích. Hai cách có thể biểu diễn cùng ý tưởng hợp nhất giá trị.

### 9.4. SSA không tự bảo đảm mọi tối ưu đều đúng

SSA làm quan hệ giá trị rõ ràng, nhưng compiler vẫn phải bảo toàn tác dụng phụ, ngoại lệ, thứ tự bộ nhớ và ngữ nghĩa số học. Không thể chỉ dựa vào việc mỗi biến được gán một lần để kết luận hai instruction có thể đổi chỗ hoặc xóa bỏ.

## 10. Kiểu dữ liệu trong IR

IR thường gắn kiểu cho giá trị hoặc instruction để verifier và optimizer biết thao tác nào hợp lệ.

Ví dụ:

~~~text
%1 : i32 = const 10
%2 : i32 = const 20
%3 : i32 = add %1, %2
%4 : bool = greater_than %3, %1
~~~

### 10.1. Kiểu tĩnh

Với typed IR, mỗi value có kiểu xác định. Verifier có thể kiểm tra:

- Operand của add có kiểu số tương thích.
- Điều kiện branch có kiểu Boolean.
- Hàm được gọi với số lượng và kiểu tham số phù hợp.
- Giá trị return khớp kiểu kết quả.
- Load/store dùng kiểu và vùng nhớ hợp lệ.

### 10.2. Kiểu động

Một DSL có thể dùng kiểu động hoặc cho phép một số giá trị chỉ biết kiểu tại runtime. IR có thể giữ kiểu dynamic, tagged value hoặc instruction kiểm tra kiểu lúc chạy.

Ví dụ:

~~~text
%value = load_dynamic "amount"
%number = check_or_convert_number %value
~~~

Nếu chuyển đổi thất bại, runtime cần phát lỗi có thể ánh xạ về biểu thức DSL nguồn.

### 10.3. Kiểu miền

HIR có thể giữ kiểu giàu ý nghĩa như Money, Timestamp, CustomerId hoặc Table<Order>. Khi lowering, các kiểu này có thể được biểu diễn bằng kiểu cơ bản hoặc cấu trúc backend. Không nên xóa thông tin miền quá sớm nếu các bước tối ưu cần biết quy tắc đặc biệt như đơn vị tiền tệ hoặc múi giờ.

### 10.4. Kiểu và phép chuyển đổi

Nếu hai kiểu không tương thích, compiler có thể:

- Báo lỗi.
- Chèn phép chuyển đổi tường minh nếu ngữ nghĩa cho phép.
- Giữ một instruction cast hoặc convert trong IR.
- Trì hoãn kiểm tra đến runtime nếu kiểu động là một phần của DSL.

Mọi phép chuyển đổi phải có quy tắc về độ chính xác, tràn số, null và lỗi.

## 11. Tối ưu hóa trên IR

IR giúp compiler áp dụng các phép biến đổi có quy tắc. Mỗi tối ưu hóa cần bảo toàn ngữ nghĩa chương trình, bao gồm giá trị trả về, tác dụng phụ, lỗi và thứ tự quan sát được.

### 11.1. Constant folding

Tính trước biểu thức chỉ chứa hằng số:

~~~text
t1 = multiply 3, 4
t2 = add t1, 2
~~~

Có thể rút gọn thành:

~~~text
t2 = 14
~~~

Chỉ hợp lệ nếu quy tắc số học của DSL cho phép tính trước và không làm thay đổi hành vi về overflow, precision, exception hoặc kiểu dữ liệu.

### 11.2. Constant propagation

Nếu compiler biết một giá trị không đổi:

~~~text
t1 = 100
t2 = greater_than amount, t1
~~~

Nó có thể thay các use của t1 bằng hằng số 100. Trong SSA, mỗi definition có một giá trị duy nhất nên việc theo dõi giá trị thường thuận tiện hơn.

### 11.3. Dead code elimination

Instruction tạo giá trị không được dùng và không có tác dụng phụ có thể bị loại:

~~~text
t1 = add 2, 3
t2 = multiply amount, 10
output t2
~~~

Nếu t1 không được sử dụng và add không gây lỗi hay tác dụng phụ theo ngữ nghĩa DSL, instruction đó có thể bị xóa.

### 11.4. Common subexpression elimination

Nếu cùng một biểu thức thuần được tính nhiều lần với cùng toán hạng và không có thay đổi trạng thái liên quan, compiler có thể dùng lại kết quả:

~~~text
t1 = multiply price, quantity
t2 = multiply price, quantity
~~~

Có thể giữ một phép nhân và thay use của t2 bằng t1. Không áp dụng máy móc với lời gọi hàm có tác dụng phụ, đọc trạng thái biến đổi hoặc có kết quả phụ thuộc thời gian.

### 11.5. Copy propagation

Nếu instruction chỉ sao chép một giá trị:

~~~text
t1 = load amount
t2 = copy t1
t3 = add t2, 10
~~~

Compiler có thể thay t2 bằng t1 và loại copy nếu không có yêu cầu debug hoặc ràng buộc khác cần giữ instruction.

### 11.6. Strength reduction

Thay một thao tác đắt hơn bằng thao tác rẻ hơn khi tương đương:

~~~text
t1 = multiply index, 2
~~~

Trong một số backend, có thể dùng phép dịch bit hoặc phép cộng phù hợp. Tính tương đương phụ thuộc kiểu số, overflow và kiến trúc đích; compiler phải tuân theo ngữ nghĩa đã công bố.

### 11.7. Dead branch elimination

Nếu điều kiện nhánh là hằng số:

~~~text
branch_if true, block_a, block_b
~~~

Compiler có thể giữ block_a và loại đường đi đến block_b nếu không có cơ chế khác khiến block_b được truy cập. Sau khi xóa nhánh, CFG và phi node cần được cập nhật.

## 12. Tối ưu hóa theo miền trong HIR

Một lợi ích quan trọng của HIR là giữ lại các thao tác đặc trưng của DSL để tối ưu hóa theo miền.

Ví dụ:

~~~text
%a = filter_rows %table where status == "PAID"
%b = project_columns %a [customer_id, amount]
%c = aggregate %b by customer_id sum(amount)
~~~

HIR cho phép nhận ra đây là chuỗi thao tác trên bảng. Compiler có thể:

- Đẩy filter gần nguồn dữ liệu hơn (predicate pushdown).
- Chỉ đọc các cột cần thiết (projection pruning).
- Gộp các bước tương thích.
- Chọn thứ tự join hoặc aggregate phù hợp.
- Chuyển một phần công việc sang database hoặc query engine.

### 12.1. Predicate pushdown

Nếu nguồn dữ liệu là database, điều kiện lọc có thể được chuyển xuống truy vấn nguồn để giảm số bản ghi truyền về:

~~~text
read_table("orders")
filter status == "PAID"
~~~

có thể thành một truy vấn có WHERE tương đương.

Phép biến đổi chỉ an toàn khi ngữ nghĩa null, kiểu dữ liệu, collation, timezone và hàm so sánh giữa DSL với backend tương thích. Nếu backend hiểu phép so sánh khác DSL, đẩy điều kiện xuống có thể làm thay đổi kết quả.

### 12.2. Projection pruning

Nếu các bước sau chỉ dùng customer_id và amount, compiler có thể tránh đọc các cột khác. Điều này giảm I/O và bộ nhớ.

### 12.3. Hợp nhất thao tác

Hai bước map hoặc filter có thể được hợp nhất nếu phép biến đổi bảo toàn thứ tự, lỗi và tác dụng phụ. Nếu một bước có thể phát sinh lỗi quan sát được hoặc ghi log, việc hợp nhất cần giữ nguyên hành vi tương ứng.

### 12.4. Tối ưu theo khả năng backend

HIR có thể được hạ khác nhau tùy backend:

- SQL backend có thể đẩy filter và aggregate xuống database.
- In-memory backend có thể dùng iterator và vectorized operations.
- Distributed backend có thể tạo các stage và shuffle.
- Workflow backend có thể biến mỗi operation thành task node.

Giữ một HIR chung giúp dùng lại logic ngôn ngữ; backend chịu trách nhiệm ánh xạ các operation sang khả năng cụ thể của nền tảng.

## 13. Verifier và bất biến của IR

Trước và sau tối ưu hóa, compiler nên kiểm tra IR có hợp lệ không. IR verifier là thành phần xác nhận các cấu trúc tuân theo hợp đồng của biểu diễn.

Các bất biến thường gặp:

1. Mỗi block có terminator hợp lệ.
2. Mọi branch đều trỏ đến block tồn tại trong cùng function hoặc module theo quy tắc.
3. Mọi operand tham chiếu đến value đã định nghĩa hoặc tham số hợp lệ.
4. Giá trị được dùng ở nơi có định nghĩa khả dụng theo quy tắc dominance hoặc SSA.
5. Kiểu của operand và result phù hợp với opcode.
6. Phi node có đầu vào tương ứng với predecessor.
7. Không có instruction thông thường sau terminator.
8. Các symbol và function reference đã được resolve hoặc được đánh dấu dynamic theo thiết kế.
9. Source metadata không làm sai lệch quan hệ giữa IR và nguồn.
10. Các quy tắc memory effect và side effect được khai báo nhất quán.

Verifier giúp phát hiện bug trong lowering hoặc optimizer gần nơi lỗi xuất hiện. Nếu IR không hợp lệ được đưa đến backend, lỗi có thể biểu hiện thành mã sai hoặc crash khó truy vết.

### 13.1. Kiểm tra sau từng phép biến đổi

Trong giai đoạn phát triển compiler, có thể chạy verifier sau mỗi pass:

~~~text
AST lowering
    |
    v
Verify IR
    |
    v
Constant folding
    |
    v
Verify IR
    |
    v
Control-flow simplification
    |
    v
Verify IR
    |
    v
Backend lowering
~~~

Việc kiểm tra nhiều lần giúp xác định pass nào tạo ra cấu trúc không hợp lệ. Khi compiler ổn định, chính sách chạy verifier có thể khác giữa chế độ phát triển và production.

## 14. Sinh mã từ IR

Backend nhận IR và chuyển thành dạng mà nền tảng đích có thể chạy.

### 14.1. Backend Java

Một DSL có thể hạ IR thành Java source hoặc bytecode. Ví dụ IR:

~~~text
%1 = load price
%2 = load quantity
%3 = multiply %1, %2
return %3
~~~

có thể sinh Java tương đương:

~~~java
BigDecimal value = price.multiply(quantity);
return value;
~~~

Compiler cần bảo đảm kiểu số và phép toán Java phù hợp với ngữ nghĩa DSL. Nếu DSL dùng decimal chính xác, không nên thay bằng double chỉ vì code generation đơn giản hơn.

### 14.2. Backend SQL

HIR biểu diễn filter và aggregate có thể được sinh thành SQL:

~~~sql
SELECT customer_id, SUM(amount) AS total
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
~~~

Backend cần ánh xạ tên bảng, cột, kiểu và hàm. Nó cũng cần xử lý khác biệt giữa null, chuỗi, ngày giờ, collation và transaction semantics của database.

### 14.3. Backend bytecode hoặc VM

Nếu DSL có máy ảo riêng, backend có thể chuyển IR sang instruction set:

~~~text
LOAD_FIELD 0
PUSH_CONST 100
GT
JUMP_IF_FALSE L1
CALL apply_discount, 0
L1:
RETURN
~~~

Bytecode cần định nghĩa rõ stack effect, kiểu operand, nhãn nhảy, calling convention và quy tắc lỗi.

### 14.4. Nhiều backend

Một HIR có thể được chuyển sang nhiều đích:

~~~text
                 HIR
               /  |  \
              v   v   v
            SQL  Java  VM bytecode
~~~

Điều này hữu ích khi DSL cần chạy trên nhiều môi trường. Tuy nhiên, mỗi backend phải thực hiện cùng ngữ nghĩa. Những tính năng không được backend hỗ trợ cần được phát hiện và báo lỗi rõ, thay vì âm thầm tạo kết quả khác.

## 15. IR cho interpreter và máy ảo

Không phải compiler nào cũng sinh mã nguồn hoặc mã máy. Một interpreter có thể thực thi trực tiếp IR.

### 15.1. Instruction dispatch

Interpreter đọc instruction và gọi thao tác tương ứng:

~~~text
LOAD_CONST 10
LOAD_CONST 20
ADD
STORE_LOCAL 0
~~~

Một VM có thể dùng stack machine hoặc register machine:

- Stack machine lấy operand từ stack và đẩy kết quả trở lại.
- Register machine đọc và ghi các virtual register hoặc slot được đánh số.

### 15.2. Stack-based IR

Ví dụ:

~~~text
PUSH 10
PUSH 20
ADD
STORE_LOCAL 0
~~~

Hai hằng số được đẩy lên stack; ADD lấy chúng ra và đẩy kết quả; STORE_LOCAL lưu kết quả vào local slot 0.

### 15.3. Register-based IR

Ví dụ:

~~~text
LOAD_CONST r0, 10
LOAD_CONST r1, 20
ADD r2, r0, r1
STORE_LOCAL 0, r2
~~~

Mỗi instruction chỉ rõ nơi đọc và ghi. Dạng này làm quan hệ dữ liệu rõ và có thể thuận tiện cho một số tối ưu hóa.

### 15.4. Interpreter và JIT

Interpreter có thể thực thi bytecode trực tiếp. JIT compiler (Just-In-Time compiler) có thể nhận các đoạn IR hoặc bytecode thường được chạy và biên dịch chúng thành mã máy tại runtime.

JIT cần bảo toàn ngữ nghĩa và quản lý các giả định tối ưu. Nếu tối ưu dựa trên kiểu hoặc trạng thái có thể thay đổi, runtime có thể cần guard và deoptimization khi giả định không còn đúng.

## 16. Debugging và source mapping

Khi compiler chuyển từ DSL sang IR rồi sang mã đích, người dùng vẫn cần xem lỗi tại vị trí nguồn ban đầu.

### 16.1. Source location trên IR

Instruction có thể giữ source span:

~~~text
%3 = multiply %1, %2
source = daily.dsl:4:20-4:35
~~~

Nếu instruction thất bại hoặc runtime phát sinh lỗi, engine có thể trỏ đến biểu thức DSL tạo ra nó.

### 16.2. Source map qua nhiều tầng

Nếu một HIR instruction được hạ thành nhiều LIR instruction, mỗi instruction có thể giữ cùng source location hoặc mapping đến node HIR gốc. Khi sinh SQL hoặc Java, backend có thể giữ mapping từ đoạn output về instruction IR và nguồn DSL.

### 16.3. Debug view

Một công cụ DSL có thể cung cấp các góc nhìn:

- AST để xem parser hiểu cấu trúc nguồn thế nào.
- HIR để xem thao tác miền sau chuẩn hóa.
- CFG/SSA để xem luồng điều khiển và dữ liệu.
- Bytecode để xem instruction runtime.
- Source map để đi từ instruction về dòng DSL.

Những góc nhìn này giúp xác định lỗi nằm ở parser, semantic analysis, lowering, optimizer hay backend.

### 16.4. Tối ưu hóa và debug

Optimizer có thể xóa, gộp hoặc di chuyển instruction. Để debug có ý nghĩa, compiler cần giữ metadata đủ để giải thích instruction đã biến đổi bắt nguồn từ đâu. Một instruction tổng hợp có thể liên kết đến nhiều source span; không phải lúc nào cũng có một vị trí duy nhất.

## 17. Quản lý nhiều phiên bản IR

Khi DSL phát triển, IR cũng có thể thay đổi. Backend, plugin hoặc tệp bytecode đã lưu có thể phụ thuộc vào phiên bản IR.

Một số quyết định cần xác định:

- IR chỉ là cấu trúc nội bộ trong một lần compile hay được lưu lâu dài?
- Có cho phép plugin bên ngoài tạo instruction mới không?
- Opcode có version hoặc schema không?
- Bytecode cũ có được runtime mới hỗ trợ không?
- Khi thay đổi kiểu hoặc calling convention, có cần migration không?
- Backend cần khai báo tập capability nào?

Nếu IR được lưu vào cache hoặc phân phối qua mạng, cần có format version và quy tắc tương thích. Không nên giả định cấu trúc nội bộ có thể thay đổi tùy ý mà mọi artifact cũ vẫn dùng được.

### 17.1. Stable IR và internal IR

Một compiler có thể có IR nội bộ thay đổi thường xuyên và một format bytecode ổn định hơn dành cho runtime. Tách hai mục tiêu giúp nhóm phát triển tối ưu compiler mà không làm runtime hoặc plugin phải cập nhật theo từng thay đổi nhỏ.

### 17.2. Capability của backend

Một backend có thể hỗ trợ một tập operation nhất định. Trước khi sinh mã, compiler nên xác định IR có instruction mà backend không hỗ trợ hay không.

Ví dụ backend SQL không hỗ trợ một hàm tùy chỉnh trong HIR. Compiler có thể:

- Hạ hàm đó bằng biểu thức SQL tương đương.
- Gọi UDF nếu môi trường cho phép.
- Chuyển phần thao tác sang runtime khác.
- Báo lỗi capability rõ ràng.

Không nên bỏ qua instruction không hỗ trợ và tiếp tục sinh mã có kết quả sai.

## 18. Kiểm thử IR và các phép biến đổi

IR cần được kiểm thử ở cấp cấu trúc, ngữ nghĩa và kết quả thực thi.

### 18.1. Kiểm thử lowering

Với mỗi cấu trúc DSL quan trọng:

1. Viết đầu vào nguồn.
2. Xác định AST mong đợi.
3. Xác định IR mong đợi hoặc các bất biến IR.
4. Chạy lowering.
5. So sánh cấu trúc hoặc kết quả chuẩn hóa.

### 18.2. Kiểm thử verifier

Tạo IR hợp lệ và IR cố ý sai:

- Block không có terminator.
- Branch trỏ đến block không tồn tại.
- Operand dùng trước khi được định nghĩa trong trường hợp không hợp lệ.
- Phi node thiếu đầu vào cho predecessor.
- Opcode nhận kiểu không tương thích.

Verifier phải chấp nhận cấu trúc hợp lệ và từ chối cấu trúc sai với chẩn đoán đủ rõ cho developer.

### 18.3. Kiểm thử tối ưu hóa

Với một chương trình đầu vào, so sánh kết quả trước và sau tối ưu hóa trong cùng môi trường và cùng điều kiện. Cần bao phủ tác dụng phụ, ngoại lệ, null, overflow, thứ tự thực thi và các tình huống biên.

Không chỉ so sánh giá trị trả về. Một phép tối ưu có thể giữ kết quả cuối nhưng thay đổi số lần gọi dịch vụ, số lần ghi file hoặc thứ tự thông báo.

### 18.4. Differential testing

Nếu có interpreter và backend độc lập, có thể chạy cùng một DSL trên cả hai rồi so sánh kết quả, diagnostics và tác dụng phụ được quan sát. Cách này giúp phát hiện khác biệt ngữ nghĩa giữa các backend.

### 18.5. Kiểm thử regression

Lưu các trường hợp DSL và IR đã biết. Khi sửa lowering hoặc optimizer, chạy lại để bảo đảm các chương trình cũ không thay đổi hành vi ngoài dự kiến.

## 19. Ví dụ xuyên suốt: từ DSL đến IR và thực thi

Xét DSL:

~~~text
pipeline "high-value-orders" {
    source "orders.csv"
    filter amount >= 100
    let fee = amount * 0.05
    output fee to "fees.csv"
}
~~~

Ví dụ này giản lược và giả định amount được tham chiếu trong ngữ cảnh của từng bản ghi.

### 19.1. AST

~~~text
Pipeline
├── Name("high-value-orders")
├── Source("orders.csv")
├── Filter
│   └── GreaterOrEqual
│       ├── Field("amount")
│       └── Number(100)
├── Let("fee")
│   └── Multiply
│       ├── Field("amount")
│       └── Number(0.05)
└── Output
    ├── Name("fee")
    └── Path("fees.csv")
~~~

AST giữ các cấu trúc theo ngôn ngữ nguồn.

### 19.2. HIR

~~~text
%orders = read_csv("orders.csv")
%filtered = filter_rows %orders where amount >= 100
%with_fee = map_rows %filtered:
    fee = amount * 0.05
write_csv %with_fee select fee to "fees.csv"
~~~

HIR giữ thao tác đọc, lọc, biến đổi từng bản ghi và ghi kết quả. Compiler có thể tối ưu pipeline theo miền.

### 19.3. LIR dạng CFG

~~~text
entry:
    %source = open_csv "orders.csv"
    %iterator = make_iterator %source
    jump loop_header

loop_header:
    %row = next %iterator
    %has_row = is_present %row
    branch_if %has_row, loop_body, loop_exit

loop_body:
    %amount = load_field %row, "amount"
    %keep = greater_or_equal %amount, 100
    branch_if %keep, write_row, loop_header

write_row:
    %fee = multiply %amount, 0.05
    write_field %row, "fee", %fee
    write_output_row "fees.csv", %row
    jump loop_header

loop_exit:
    close %source
    return
~~~

LIR mô tả rõ vòng lặp, điều kiện, nhánh và thao tác I/O. Một implementation thực tế cần thêm xử lý lỗi đọc/ghi, đóng tài nguyên khi thất bại và quy tắc schema.

### 19.4. Thực thi

Interpreter hoặc backend có thể thực hiện các instruction. Nếu mở orders.csv thất bại, runtime tạo lỗi có source mapping về câu lệnh source. Nếu ghi fees.csv thất bại, lỗi được liên kết với output. Nếu có optimizer, nó phải giữ đúng chính sách xử lý lỗi và tác dụng phụ của pipeline.

Ví dụ cho thấy mỗi tầng có vai trò:

- AST giúp hiểu cấu trúc nguồn.
- HIR giữ các phép toán miền.
- LIR thể hiện điều khiển và thao tác cụ thể.
- Runtime thực hiện các thao tác trên dữ liệu và tài nguyên.

## 20. Những sai lầm thường gặp khi thiết kế IR

### 20.1. Tạo IR chỉ là bản sao của AST

Nếu IR giữ nguyên mọi nút AST mà không bổ sung giá trị cho lowering, tối ưu hoặc backend, nó có thể chỉ tạo thêm một tầng chuyển đổi. Hãy xác định mục tiêu cụ thể của IR.

### 20.2. Hạ quá thấp quá sớm

Nếu HIR lập tức biến mọi thao tác miền thành lệnh load/store cơ bản, compiler có thể mất thông tin cần cho tối ưu theo miền như predicate pushdown hoặc chọn kế hoạch truy vấn.

### 20.3. Giữ quá nhiều cú pháp nguồn trong IR

IR dành cho thực thi không nhất thiết cần mọi dấu ngoặc, cách viết literal hoặc comment. Nếu cần formatter hoặc refactoring, hãy giữ CST/source metadata phù hợp thay vì buộc mọi backend mang theo toàn bộ chi tiết cú pháp.

### 20.4. Không định nghĩa kiểu và tác dụng phụ của instruction

Optimizer cần biết instruction thuần hay có side effect, có thể ném lỗi hay không, đọc/ghi vùng nhớ nào và kiểu operand ra sao. Thiếu hợp đồng này có thể dẫn đến tối ưu sai.

### 20.5. Không có verifier

IR sai có thể đi sâu đến backend và tạo lỗi khó truy vết. Verifier nên kiểm tra cấu trúc và kiểu ở các ranh giới quan trọng.

### 20.6. Mất source mapping

Khi runtime chỉ thấy instruction hoặc bytecode, người dùng khó tìm vị trí DSL gây lỗi. Hãy truyền source location qua các bước lowering và code generation.

### 20.7. Dùng một IR cho mọi mục tiêu

Một biểu diễn duy nhất có thể quá cao cho backend hoặc quá thấp cho tối ưu miền. Nhiều tầng IR có thể hữu ích nếu mỗi tầng có nhiệm vụ rõ ràng.

### 20.8. Tối ưu mà không xét ngữ nghĩa lỗi

Hai biểu thức có cùng giá trị trong trường hợp bình thường nhưng có thể khác cách phát sinh lỗi hoặc tác dụng phụ. Tối ưu hóa phải bảo toàn toàn bộ hành vi quan sát được theo hợp đồng DSL.

## 21. Quy trình thiết kế IR cho DSL

Khi thiết kế mã trung gian, có thể thực hiện theo các bước:

1. **Xác định backend và runtime.** Liệt kê nền tảng đích, yêu cầu thực thi và các capability cần hỗ trợ.
2. **Xác định mục tiêu của IR.** Chọn biểu diễn phục vụ chuẩn hóa, tối ưu, thực thi hoặc nhiều mục tiêu.
3. **Chọn mức trừu tượng.** Quyết định IR giữ operation miền hay đã phân rã thành instruction cơ bản.
4. **Định nghĩa value và type.** Xác định operand, result, constant, symbol và quy tắc kiểu.
5. **Định nghĩa control flow.** Chọn basic block, terminator, branch và cách biểu diễn vòng lặp.
6. **Định nghĩa memory và side effect.** Nêu rõ load, store, gọi hàm, I/O, exception và thứ tự quan sát.
7. **Định nghĩa source metadata.** Giữ liên kết đến AST hoặc source span.
8. **Viết lowering.** Ánh xạ từng loại AST hoặc thao tác miền sang IR.
9. **Xây verifier.** Kiểm tra cấu trúc, kiểu, luồng điều khiển và quan hệ dữ liệu.
10. **Thiết kế optimization pass.** Mỗi pass có điều kiện áp dụng và bảo đảm ngữ nghĩa.
11. **Xây backend hoặc interpreter.** Chuyển IR thành mã đích hoặc thực thi trực tiếp.
12. **Kiểm thử xuyên tầng.** So sánh kết quả, lỗi và tác dụng phụ trước/sau tối ưu và giữa backend.
13. **Quản lý version nếu cần.** Đặc tả format ổn định khi IR hoặc bytecode được lưu hoặc trao đổi.

Không phải DSL nào cũng cần SSA, CFG riêng hay nhiều tầng IR. Hãy chọn cấu trúc theo độ phức tạp thực tế và nhu cầu của compiler.

## 22. Câu hỏi tự kiểm tra

1. Mã trung gian (IR) là gì và nó nằm ở đâu trong compiler pipeline?
2. Phân biệt AST và IR bằng ví dụ một biểu thức hoặc pipeline.
3. Nêu các dạng IR phổ biến: dạng cây, danh sách lệnh, TAC, CFG, SSA và bytecode.
4. High-level IR và low-level IR khác nhau về mức trừu tượng như thế nào?
5. Basic block là gì? Terminator có vai trò gì?
6. Control-flow graph biểu diễn luồng điều khiển ra sao?
7. SSA yêu cầu điều gì đối với phép gán? Phi node dùng trong trường hợp nào?
8. Lowering chuyển một biểu thức lồng nhau thành TAC theo những bước nào?
9. Nêu ít nhất bốn phép tối ưu hóa có thể thực hiện trên IR và điều kiện để chúng an toàn.
10. Vì sao HIR có thể hỗ trợ predicate pushdown và projection pruning?
11. IR verifier nên kiểm tra những bất biến nào?
12. Vì sao source mapping cần được giữ qua nhiều tầng IR?
13. So sánh interpreter thực thi bytecode với backend sinh Java hoặc SQL.
14. Vì sao retry, exception và side effect phải được xem xét khi tối ưu hóa?
15. Hãy thiết kế một IR đơn giản cho DSL gồm source, filter, transform và output; mô tả operand, type và control flow.
