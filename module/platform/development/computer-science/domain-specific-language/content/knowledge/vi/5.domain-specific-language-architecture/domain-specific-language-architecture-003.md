# Luồng qua mô hình trung gian

Một DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền) thường được viết bằng cú pháp gần với công việc mà người dùng muốn mô tả. Tuy nhiên, máy tính không trực tiếp hiểu ý nghĩa nghiệp vụ của một tệp DSL. Công cụ xử lý cần đọc văn bản, xác định cấu trúc, kiểm tra quy tắc và chuyển nội dung đó thành dạng mà engine hoặc nền tảng đích có thể thực thi.

Trong nhiều kiến trúc, nội dung DSL được chuyển qua một hoặc nhiều **mô hình trung gian** (*Intermediate Representation – IR*) trước khi chạy hoặc sinh mã. IR là biểu diễn có cấu trúc của chương trình, nằm giữa ngôn ngữ đầu vào và cách thực thi cuối cùng. Nhờ IR, parser, phân tích ngữ nghĩa, các bước biến đổi và backend có thể được tổ chức thành những thành phần tương đối độc lập.

Luồng tổng quát có thể hình dung như sau:

```text
Tệp DSL
   |
   v
Phân tích từ vựng và cú pháp
   |
   v
AST (cây cú pháp trừu tượng)
   |
   v
Phân tích ngữ nghĩa và kiểm tra
   |
   v
IR (mô hình trung gian)
   |
   v
Các bước biến đổi / tối ưu hóa
   |
   v
Backend: interpreter, code generator hoặc engine
   |
   v
Thực thi trên môi trường đích
```

Đây là mô hình khái quát. Một DSL nhỏ có thể bỏ qua một số lớp, dùng AST làm IR, hoặc thực thi trực tiếp sau khi phân tích. Một hệ thống lớn có thể có nhiều IR và nhiều backend.

## 1. Vì sao cần mô hình trung gian?

Nếu một DSL chỉ có một cú pháp đơn giản và một cách thực thi duy nhất, công cụ có thể chuyển trực tiếp từ cấu trúc cú pháp sang lệnh thực thi. Khi ngôn ngữ phát triển, cách làm này dễ khiến parser, quy tắc miền và phần chạy phụ thuộc chặt vào nhau.

IR tạo ra một biểu diễn chung để các thành phần khác nhau cùng làm việc. Nó có một số vai trò quan trọng:

- **Tách cú pháp khỏi ngữ nghĩa:** cách người dùng viết chương trình không buộc phải giống cách engine lưu trữ hoặc thực thi chương trình.
- **Chuẩn hóa biểu diễn:** nhiều cách viết khác nhau có thể được chuyển về một dạng thống nhất.
- **Tái sử dụng phân tích:** nhiều backend có thể nhận cùng một IR.
- **Tổ chức biến đổi:** các bước kiểm tra, mở rộng macro, đơn giản hóa hoặc tối ưu có thể hoạt động trên cấu trúc rõ ràng.
- **Hỗ trợ kiểm tra và chẩn đoán:** công cụ có thể kiểm tra cấu trúc và kiểu dữ liệu trước khi thực thi.
- **Tạo khả năng mở rộng:** có thể thêm backend hoặc bước biến đổi mà không phải viết lại toàn bộ parser.

Ví dụ, một DSL pipeline có thể cho phép người dùng viết `filter`, `select` và `sort` theo thứ tự dễ đọc. IR có thể biểu diễn chúng thành các nút thao tác với kiểu đầu vào, đầu ra và tham số đã được xác định. Backend chạy cục bộ và backend chạy phân tán có thể cùng sử dụng biểu diễn đó.

## 2. Các lớp biểu diễn trong luồng xử lý

### 2.1. Văn bản nguồn và token

Đầu vào ban đầu thường là văn bản DSL. Bước phân tích từ vựng (*lexical analysis* hoặc *tokenization*) đọc chuỗi ký tự và tạo ra các token như từ khóa, tên định danh, số, chuỗi, toán tử và dấu phân cách.

Ví dụ, câu DSL giả định:

```text
select name, salary from employees where salary > 50000
```

Có thể được tách thành các token:

```text
SELECT
IDENTIFIER("name")
COMMA
IDENTIFIER("salary")
FROM
IDENTIFIER("employees")
WHERE
IDENTIFIER("salary")
GREATER_THAN
NUMBER(50000)
```

Token thường mang theo vị trí nguồn như số dòng, cột hoặc khoảng ký tự. Thông tin này giúp công cụ chỉ ra lỗi ở đúng vị trí trong tệp DSL.

### 2.2. Cây cú pháp cụ thể và AST

Parser (*syntax parser*) nhận token và kiểm tra chúng có tuân theo grammar của DSL hay không. Parser có thể tạo **cây cú pháp cụ thể** (*Concrete Syntax Tree – CST*) giữ lại nhiều chi tiết cú pháp, chẳng hạn dấu ngoặc, dấu phẩy và dấu kết thúc câu lệnh.

Từ CST, hoặc trực tiếp từ token, công cụ thường tạo **cây cú pháp trừu tượng** (*Abstract Syntax Tree – AST*). AST giữ cấu trúc có ý nghĩa đối với chương trình và lược bỏ nhiều chi tiết trình bày.

Ví dụ biểu thức:

```text
price * quantity + shipping
```

Có thể được biểu diễn bằng AST:

```text
        Add
       /   \
    Multiply  Name("shipping")
     /   \
 Name("price") Name("quantity")
```

Cây cho thấy phép nhân được nhóm trước phép cộng theo quy tắc ưu tiên toán tử. AST hữu ích cho việc kiểm tra và biến đổi vì mỗi loại nút có ý nghĩa rõ ràng.

### 2.3. Mô hình trung gian (IR)

IR là biểu diễn nội bộ được thiết kế để phục vụ một hoặc nhiều mục tiêu xử lý. Nó có thể giống AST, nhưng thường được chuẩn hóa hơn và có thêm thông tin ngữ nghĩa.

Một IR có thể lưu:

- Loại thao tác và quan hệ giữa các thao tác.
- Kiểu dữ liệu của biểu thức và kết quả.
- Tham chiếu đã được phân giải đến biến, hàm, bảng hoặc tài nguyên.
- Kiểu đầu vào và đầu ra của từng bước.
- Các giá trị hằng đã được tính trước.
- Thông tin về phụ thuộc, phạm vi hoặc hiệu ứng của thao tác.
- Vị trí nguồn để truy ngược lỗi về đoạn DSL ban đầu.

Không có một định dạng IR chung cho mọi DSL. IR cần phản ánh những khái niệm mà các bước sau thực sự cần, đồng thời đủ ổn định để nhiều thành phần có thể sử dụng.

## 3. Phân tích ngữ nghĩa trước khi tạo hoặc hoàn thiện IR

Một chương trình có thể đúng cú pháp nhưng vẫn sai ý nghĩa. Ví dụ, DSL chấp nhận cấu trúc `salary + name`, nhưng nếu `salary` là số còn `name` là chuỗi và phép cộng hai kiểu đó không được hỗ trợ, chương trình không hợp lệ về ngữ nghĩa.

Phân tích ngữ nghĩa (*semantic analysis*) thường thực hiện một số công việc sau:

### 3.1. Phân giải tên

Tên biến, bảng, hàm, trường hoặc tài nguyên phải được liên kết với khai báo tương ứng. Công cụ có thể xây dựng bảng ký hiệu (*symbol table*) để lưu tên, phạm vi, kiểu và thông tin khai báo.

Ví dụ, trong biểu thức `salary > 50000`, công cụ cần biết `salary` là trường nào, thuộc nguồn dữ liệu nào và có kiểu gì. Nếu tên không tồn tại hoặc mơ hồ, cần phát sinh lỗi ngữ nghĩa.

### 3.2. Kiểm tra kiểu

Hệ thống kiểm tra các phép toán và kết nối có phù hợp với kiểu dữ liệu hay không. Với DSL pipeline, đầu ra của bước trước phải tương thích với đầu vào của bước sau. Với DSL truy vấn, phép so sánh phải hợp lệ đối với kiểu của hai vế.

Một số DSL có kiểu tĩnh, kiểm tra trước khi chạy. DSL khác có thể kiểm tra một phần lúc biên dịch và một phần lúc thực thi. Mức độ kiểm tra phụ thuộc vào mục tiêu và khả năng của ngôn ngữ.

### 3.3. Kiểm tra quy tắc miền

Ngoài quy tắc ngôn ngữ, công cụ còn phải kiểm tra điều kiện riêng của miền. Ví dụ:

- Một pipeline không được có hai nguồn dữ liệu chính nếu DSL chỉ hỗ trợ một nguồn.
- Một trạng thái trong quy trình không được chuyển sang trạng thái không hợp lệ.
- Một tài nguyên triển khai phải có trường bắt buộc như tên hoặc vùng.
- Một phép toán dữ liệu phải nhận đúng số lượng tham số.

Các quy tắc này có thể được kiểm tra khi phân tích, khi xác thực cấu hình hoặc trước khi thực thi tùy khả năng của hệ thống.

### 3.4. Gắn thông tin ngữ nghĩa vào biểu diễn

Sau khi phân giải tên và kiểm tra kiểu, IR có thể lưu các tham chiếu đã được giải quyết thay vì giữ lại chuỗi tên thô. Chẳng hạn, nút `Field("salary")` có thể được chuyển thành tham chiếu đến cột số 3 trong schema đầu vào, với kiểu `Decimal`.

Điều này giúp backend không phải lặp lại toàn bộ công việc tìm tên và xác định kiểu. Tuy nhiên, IR cần giữ đủ thông tin nguồn để khi backend phát hiện lỗi vẫn có thể báo vị trí tương ứng trong DSL.

## 4. Luồng chuyển đổi từ AST sang IR

Quá trình chuyển AST sang IR thường được gọi là lowering hoặc IR construction. Mục tiêu là chuyển cấu trúc gần với cú pháp nguồn thành biểu diễn phù hợp hơn cho xử lý tiếp theo.

Các thao tác thường gặp gồm:

1. **Loại bỏ chi tiết cú pháp:** bỏ dấu ngoặc hoặc dấu phân cách không còn cần thiết sau khi cấu trúc đã được xác định.
2. **Phân giải tên:** thay tên chưa phân giải bằng tham chiếu đến khai báo hoặc tài nguyên.
3. **Chuẩn hóa cấu trúc:** đưa nhiều dạng cú pháp tương đương về cùng một dạng nội bộ.
4. **Bổ sung kiểu và metadata:** gắn kiểu dữ liệu, vị trí nguồn và thông tin cần thiết cho backend.
5. **Hạ mức trừu tượng:** chuyển một lệnh cấp cao thành các thao tác nhỏ hơn mà engine hiểu được.

Ví dụ, DSL có thể cho phép:

```text
repeat 3 times {
    send("hello")
}
```

Nếu runtime không có lệnh `repeat`, bước lowering có thể chuyển cấu trúc này thành vòng lặp trong IR. Nếu runtime có thao tác lặp chuyên biệt, IR có thể giữ nguyên một nút `Repeat`. Quyết định phụ thuộc vào kiến trúc engine và những phép biến đổi cần thực hiện.

## 5. Ví dụ xuyên suốt: DSL truy vấn dữ liệu

Xét DSL truy vấn giả định sau:

```text
from employees
where department == "Engineering" and salary > 50000
select name, salary
sort salary descending
```

Mục tiêu là lấy tên và lương của nhân viên thuộc phòng ban Engineering, có lương trên 50.000, sau đó sắp xếp theo lương giảm dần.

### 5.1. AST sau khi phân tích cú pháp

Parser có thể tạo cấu trúc khái quát:

```text
Query
├── Source("employees")
├── Filter
│   └── And
│       ├── Equal(Field("department"), String("Engineering"))
│       └── GreaterThan(Field("salary"), Number(50000))
├── Project
│   ├── Field("name")
│   └── Field("salary")
└── Sort
    └── Order(Field("salary"), DESC)
```

Ở giai đoạn này, các trường vẫn có thể chỉ là tên văn bản. Parser biết cấu trúc câu truy vấn nhưng chưa chắc biết schema của `employees`.

### 5.2. Phân tích ngữ nghĩa

Giả sử schema nguồn là:

| Trường | Kiểu |
|---|---|
| `id` | Integer |
| `name` | String |
| `department` | String |
| `salary` | Decimal |

Công cụ xác nhận `department` và `name` là chuỗi, `salary` là số thập phân, phép so sánh với `50000` hợp lệ, và trường sắp xếp có tồn tại.

Sau bước này, tham chiếu trường trong IR có thể gắn với định danh nội bộ và kiểu dữ liệu:

```text
FieldRef(id=2, name="department", type=String)
FieldRef(id=3, name="salary", type=Decimal)
FieldRef(id=1, name="name", type=String)
```

Các ID ở đây chỉ minh họa vị trí trường trong schema. Một hệ thống thật có thể dùng symbol ID, column handle hoặc object reference khác.

### 5.3. IR dạng pipeline

Một IR dạng pipeline có thể biểu diễn cùng truy vấn bằng chuỗi thao tác:

```text
Scan(table="employees")
  -> Filter(
       And(
         Equal(Column(2), Literal("Engineering")),
         GreaterThan(Column(3), Literal(50000))
       )
     )
  -> Project(columns=[Column(1), Column(3)])
  -> Sort(keys=[Column(3, DESC)])
```

IR mô tả rõ các bước xử lý theo thứ tự. Tên bảng và cột đã được xác định, biểu thức đã có cấu trúc, và backend có thể chuyển các nút này sang cách thực thi phù hợp.

### 5.4. Biến đổi IR

Một bước tối ưu có thể đẩy phép lọc gần nguồn dữ liệu hơn (*predicate pushdown*) nếu backend hỗ trợ. Một phép biến đổi khác có thể chỉ đọc các cột cần thiết thay vì tải toàn bộ bản ghi (*projection pushdown*).

Ví dụ, nếu nguồn là cơ sở dữ liệu quan hệ, backend có thể sinh SQL tương đương. Nếu nguồn là tệp CSV, engine có thể thực hiện lọc và sắp xếp trong bộ xử lý dữ liệu. Cùng một IR logic có thể được triển khai theo nhiều cách, miễn là giữ nguyên ngữ nghĩa truy vấn.

## 6. Các dạng IR thường gặp

IR không chỉ có một hình thức. Việc chọn cấu trúc phụ thuộc vào loại DSL và các thao tác cần thực hiện.

### 6.1. IR dạng cây

IR dạng cây giữ quan hệ cha-con giữa biểu thức và thao tác. Nó phù hợp với biểu thức lồng nhau, cấu hình phân cấp và các phép biến đổi đệ quy.

Ví dụ: AST, cây biểu thức, cây truy vấn hoặc cây quy tắc. Cấu trúc này dễ phản ánh thứ tự ưu tiên và phạm vi lồng nhau.

### 6.2. IR dạng đồ thị

IR dạng đồ thị biểu diễn các nút và cạnh phụ thuộc. Nó phù hợp với pipeline, luồng dữ liệu hoặc chương trình mà một kết quả có thể được nhiều thao tác sử dụng.

Ví dụ, một DAG (*Directed Acyclic Graph* – đồ thị có hướng không chu trình) có thể biểu diễn các bước xử lý dữ liệu. Engine có thể xác định những nút độc lập để chạy song song, nếu ngữ nghĩa và tài nguyên cho phép.

### 6.3. IR dạng lệnh tuần tự

Một số hệ thống chuyển chương trình thành danh sách lệnh hoặc mã bytecode. Mỗi lệnh thực hiện thao tác nhỏ như nạp hằng, đọc biến, cộng, gọi hàm hoặc nhảy đến vị trí khác.

Ví dụ đơn giản:

```text
LOAD_CONST 2
LOAD_CONST 3
ADD
STORE result
```

Dạng này thuận tiện cho máy ảo hoặc interpreter vì runtime có thể đọc và thực hiện từng lệnh.

### 6.4. IR nhiều cấp

Một hệ thống có thể dùng nhiều IR với mức trừu tượng khác nhau:

- IR cấp cao giữ các thao tác miền như `Join`, `Filter`, `DeployResource` hoặc `ApproveOrder`.
- IR cấp thấp hơn chuyển chúng thành thao tác dữ liệu, lệnh điều khiển hoặc lời gọi runtime.
- IR gần máy hoặc bytecode biểu diễn các lệnh mà môi trường đích có thể thực thi.

IR cấp cao giữ được ý nghĩa miền, thuận tiện cho tối ưu theo quy tắc nghiệp vụ. IR cấp thấp gần với môi trường thực thi hơn, nhưng có thể khó đọc và khó biến đổi ở mức miền.

## 7. Các bước biến đổi và tối ưu hóa IR

Sau khi IR được tạo, hệ thống có thể chạy một chuỗi các pass (*transformation passes*). Mỗi pass nhận một biểu diễn, kiểm tra điều kiện và tạo ra biểu diễn đã được biến đổi.

Một số loại pass phổ biến:

### 7.1. Chuẩn hóa

Đưa các cấu trúc tương đương về một dạng thống nhất. Ví dụ, biểu thức `a >= b` có thể được giữ nguyên hoặc chuyển về dạng phủ định của `a < b`, tùy phép toán mà IR hỗ trợ.

### 7.2. Mở rộng macro hoặc cấu trúc cấp cao

Một lệnh tiện ích có thể được mở rộng thành các thao tác cơ bản hơn. Ví dụ, `retry 3 times` có thể được chuyển thành cấu trúc điều khiển và kiểm tra lỗi mà runtime hỗ trợ.

### 7.3. Tính hằng

Nếu một biểu thức chỉ chứa hằng số, công cụ có thể tính trước kết quả:

```text
Before: Add(Literal(10), Multiply(Literal(2), Literal(3)))
After:  Literal(16)
```

Điều này giảm công việc cần làm lúc chạy, nhưng chỉ hợp lệ nếu phép tính không có hiệu ứng phụ và tuân theo đúng quy tắc số học của DSL.

### 7.4. Loại bỏ thao tác không cần thiết

Nếu một bước không ảnh hưởng đến kết quả quan sát được, hệ thống có thể loại bỏ nó. Ví dụ, một phép chuyển đổi dữ liệu đồng nhất có thể được bỏ qua nếu chắc chắn không có tác dụng phụ.

### 7.5. Tối ưu theo miền

IR có thể cho phép áp dụng các quy tắc riêng của DSL. Với truy vấn dữ liệu, có thể đẩy bộ lọc xuống nguồn hoặc gộp các phép chiếu. Với DSL workflow, có thể phát hiện các bước độc lập để lên lịch song song. Với DSL tính toán, có thể gộp các phép toán tương thích.

### 7.6. Lowering sang mức thấp hơn

Pass lowering chuyển các thao tác cấp cao thành những thao tác mà backend tiếp theo hỗ trợ. Một DSL có thể có nhiều lần lowering, từ mô hình miền sang mô hình thực thi, rồi sang bytecode hoặc lệnh nền tảng.

## 8. Backend: thực thi hoặc sinh mã từ IR

Sau khi IR đã sẵn sàng, backend quyết định cách chuyển nó thành kết quả thực thi. Một kiến trúc DSL có thể hỗ trợ nhiều backend:

**Interpreter:** duyệt IR và thực hiện trực tiếp từng nút hoặc lệnh. Cách này dễ triển khai cho DSL nhỏ, hỗ trợ thử nghiệm nhanh và có thể cung cấp thông báo lỗi theo từng thao tác.

**Code generator:** chuyển IR thành mã nguồn của ngôn ngữ khác như Java, JavaScript, SQL hoặc một ngôn ngữ đích riêng. Mã được sinh có thể tiếp tục được biên dịch hoặc chạy trong môi trường tương ứng.

**Bytecode generator:** chuyển IR thành bytecode cho máy ảo. Runtime đọc bytecode và thực thi lệnh theo quy tắc đã định.

**Engine chuyên biệt:** diễn giải IR bằng một engine dữ liệu, workflow, quy tắc hoặc triển khai hạ tầng. Backend có thể lập kế hoạch và điều phối tài nguyên theo cách phù hợp với miền.

| Backend | Đầu ra | Trường hợp phù hợp |
|---|---|---|
| Interpreter | Kết quả thực thi trực tiếp | DSL nhỏ, tương tác, cấu hình hoặc kịch bản |
| Code generator | Mã nguồn của ngôn ngữ đích | Tận dụng compiler và hệ sinh thái sẵn có |
| Bytecode generator | Bytecode | Máy ảo hoặc runtime riêng |
| Engine chuyên biệt | Kế hoạch hoặc tác vụ thực thi | Truy vấn, workflow, pipeline, luật nghiệp vụ |

Một IR chung không tự động bảo đảm mọi backend có thể hỗ trợ mọi chương trình. Backend cần khai báo tập tính năng, kiểu dữ liệu và thao tác mà nó thực hiện được. Nếu IR chứa thao tác không được backend hỗ trợ, hệ thống phải báo lỗi rõ ràng hoặc chọn backend khác.

## 9. Bảo toàn ngữ nghĩa qua các bước biến đổi

Điều quan trọng nhất của một pipeline IR là giữ nguyên ý nghĩa chương trình. Một phép biến đổi chỉ hợp lệ khi kết quả có hành vi quan sát được tương đương với đầu vào theo ngữ nghĩa của DSL.

Ví dụ, hai phép lọc có thể được gộp thành một điều kiện `A AND B` nếu chúng không có hiệu ứng phụ và thứ tự đánh giá không làm thay đổi kết quả. Nếu một điều kiện gọi hàm có thể ghi dữ liệu hoặc phát sinh ngoại lệ, việc đổi thứ tự có thể làm chương trình khác đi.

Khi thiết kế IR và pass, cần xác định:

- Thứ tự đánh giá biểu thức.
- Quy tắc xử lý giá trị rỗng, lỗi và ngoại lệ.
- Kiểu số, độ chính xác và quy tắc chuyển kiểu.
- Hành vi có hiệu ứng phụ như ghi dữ liệu, gọi dịch vụ hoặc thay đổi trạng thái.
- Quy tắc đồng thời và thứ tự thực thi nếu engine chạy song song.
- Hành vi mặc định và khả năng tương thích giữa các phiên bản DSL.

Không nên áp dụng tối ưu hóa chỉ vì hai biểu thức trông giống nhau. Cần có quy tắc ngữ nghĩa chứng minh phép biến đổi là an toàn trong phạm vi DSL.

## 10. Chẩn đoán lỗi và truy vết về mã nguồn

Khi chương trình đi qua nhiều biểu diễn, lỗi có thể được phát hiện ở nhiều giai đoạn:

| Giai đoạn | Ví dụ lỗi | Cách báo lỗi hữu ích |
|---|---|---|
| Tokenization | Ký tự không hợp lệ | Chỉ vị trí ký tự trong tệp |
| Parsing | Thiếu dấu đóng hoặc sai cấu trúc | Chỉ dòng, cột và cấu trúc mong đợi |
| Semantic analysis | Tên trường không tồn tại | Nêu tên và phạm vi tra cứu |
| Type checking | So sánh hai kiểu không tương thích | Nêu kiểu thực tế và kiểu mong đợi |
| IR validation | Nút IR thiếu đầu vào bắt buộc | Nêu thao tác và điều kiện vi phạm |
| Backend | Môi trường đích không hỗ trợ thao tác | Nêu tính năng không được hỗ trợ và backend liên quan |
| Runtime | Dữ liệu thực tế không thỏa điều kiện | Nêu thao tác đang chạy và ngữ cảnh lỗi |

Để hỗ trợ chẩn đoán, AST và IR nên giữ source location hoặc metadata liên kết với đoạn mã nguồn ban đầu. Khi một thao tác được sinh từ nhiều đoạn DSL, hệ thống có thể lưu một hoặc nhiều nguồn gốc (*source provenance*) để báo lỗi chính xác hơn.

Khi biến đổi IR, không nên vô tình làm mất thông tin nguồn cần thiết. Nếu backend báo lỗi ở nút đã được tối ưu, công cụ có thể dùng metadata để chỉ lại câu lệnh DSL mà người dùng cần sửa.

## 11. Thiết kế IR cho một DSL

IR quá gần cú pháp nguồn có thể khiến backend phải hiểu nhiều chi tiết ngôn ngữ. IR quá thấp lại làm mất ý nghĩa miền và khiến các phép tối ưu chuyên biệt khó thực hiện. Thiết kế cần cân bằng hai mục tiêu.

### 11.1. Xác định người sử dụng IR

Liệt kê các thành phần sẽ đọc hoặc biến đổi IR: validator, optimizer, interpreter, code generator, debugger hay công cụ trực quan hóa. Mỗi thành phần cần những trường thông tin nào?

### 11.2. Chọn mức trừu tượng

Giữ các thao tác miền nếu chúng có ý nghĩa quan trọng với tối ưu hoặc chẩn đoán. Hạ thấp những cấu trúc mà backend không cần hoặc không thể thực thi trực tiếp.

### 11.3. Định nghĩa kiểu và bất biến

Mỗi nút IR nên có quy tắc rõ ràng về kiểu đầu vào, đầu ra, tham số bắt buộc và điều kiện hợp lệ. Một IR đã được xác thực nên bảo đảm các bất biến cơ bản để các pass sau không phải kiểm tra lại mọi thứ.

### 11.4. Giữ thông tin nguồn

Lưu vị trí nguồn, tên định danh ban đầu hoặc provenance cần thiết để debugger và thông báo lỗi có thể liên kết IR với tệp DSL.

### 11.5. Xác định ranh giới pass

Mỗi pass nên có đầu vào, đầu ra và điều kiện rõ ràng. Ví dụ, pass type resolution nhận AST có tên chưa phân giải và trả về IR có tham chiếu đã phân giải. Pass constant folding nhận IR hợp lệ và trả về IR tương đương đã tính các biểu thức hằng.

### 11.6. Có chiến lược phiên bản

Nếu IR được lưu xuống đĩa, trao đổi giữa tiến trình hoặc dùng làm giao diện plugin, cần nghĩ đến phiên bản schema và khả năng tương thích. Nếu IR chỉ là cấu trúc nội bộ trong một lần chạy, việc thay đổi có thể đơn giản hơn nhưng vẫn cần kiểm soát phụ thuộc giữa các pass.

## 12. Ví dụ mã giả: pipeline qua IR

Đoạn mã giả dưới đây minh họa cách một công cụ có thể tổ chức các bước. Đây là thiết kế khái quát, không phải API của một framework cụ thể.

```java
ProgramAst ast = parser.parse(sourceText);

SemanticContext context = semanticAnalyzer.analyze(ast, domainSchema);

IrModule ir = irBuilder.lower(ast, context);

irValidator.validate(ir);

IrModule optimized = optimizer.run(ir, List.of(
    new ConstantFoldingPass(),
    new NormalizeExpressionsPass(),
    new DomainOptimizationPass()
));

ExecutionPlan plan = backend.compile(optimized);

ExecutionResult result = runtime.execute(plan);
```

Các lớp được tách theo trách nhiệm:

- `parser` kiểm tra cấu trúc cú pháp và tạo AST.
- `semanticAnalyzer` giải quyết tên, kiểu và quy tắc miền.
- `irBuilder` chuyển AST cùng thông tin ngữ nghĩa thành IR.
- `irValidator` xác nhận các bất biến của IR.
- `optimizer` chạy các pass có thể biến đổi IR.
- `backend` tạo kế hoạch thực thi hoặc mã đích.
- `runtime` thực hiện kế hoạch trong môi trường phù hợp.

Trong triển khai thực tế, một số lớp có thể được gộp, hoặc backend có thể vừa lập kế hoạch vừa thực thi. Điều quan trọng là xác định rõ dữ liệu đầu vào, đầu ra và trách nhiệm của từng giai đoạn.

## 13. Khi nào nên dùng một IR, nhiều IR hoặc không dùng IR riêng?

**Một IR** phù hợp khi DSL có một mức trừu tượng tương đối ổn định, số backend ít và các phép biến đổi không quá phức tạp. Một IR duy nhất giúp giảm chi phí duy trì.

**Nhiều IR** phù hợp khi hệ thống có nhiều giai đoạn hạ mức trừu tượng, nhiều backend khác biệt hoặc cần tối ưu ở các mức khác nhau. IR cấp cao có thể giữ ý nghĩa miền; IR cấp thấp mô tả thao tác runtime.

**Không cần IR riêng** khi DSL rất nhỏ, chỉ có một cách thực thi và AST đã đủ để interpreter chạy trực tiếp. Trong trường hợp này, AST có thể đóng vai trò biểu diễn nội bộ. Không nên thêm một lớp IR chỉ vì kiến trúc compiler thường có lớp đó.

Khi quyết định, hãy cân nhắc chi phí chuyển đổi, số lần phải duy trì đồng bộ schema, độ phức tạp của debug và lợi ích thực tế mà IR mang lại.

## 14. Những lỗi thiết kế thường gặp

**Để backend phụ thuộc trực tiếp vào cú pháp nguồn:** khi cú pháp thay đổi, mọi backend có thể phải sửa. Một IR ổn định giúp giảm phụ thuộc này.

**Đưa mọi chi tiết vào IR:** IR quá lớn, chứa nhiều trường không dùng đến và khó duy trì. Chỉ nên giữ thông tin phục vụ các giai đoạn sau hoặc chẩn đoán.

**Mất thông tin nguồn quá sớm:** khi IR không còn liên kết với vị trí trong tệp DSL, lỗi ở bước tối ưu hoặc thực thi khó giải thích cho người dùng.

**Không xác định bất biến của IR:** các pass có thể giả định khác nhau về kiểu, thứ tự hoặc trạng thái nút, gây lỗi khó tìm. Cần quy định điều kiện hợp lệ cho mỗi cấp IR.

**Tối ưu hóa làm thay đổi ngữ nghĩa:** đổi thứ tự thao tác có hiệu ứng phụ, thay đổi quy tắc làm tròn hoặc xử lý giá trị rỗng có thể tạo kết quả khác. Mọi pass cần tuân theo ngữ nghĩa DSL.

**Dùng một IR cho mọi backend dù khả năng khác nhau:** IR có thể biểu diễn tính năng mà một backend không hỗ trợ. Cần kiểm tra capability hoặc có bước lowering riêng cho từng backend.

**Tạo quá nhiều tầng trung gian:** mỗi lần chuyển đổi tăng chi phí và làm debug phức tạp. Chỉ thêm tầng khi nó tạo ra ranh giới có ích hoặc hỗ trợ một nhu cầu cụ thể.

## 15. Ghi nhớ

- IR là biểu diễn có cấu trúc nằm giữa DSL nguồn và cách thực thi hoặc mã đích.
- Luồng thường gồm tokenization, parsing, AST, phân tích ngữ nghĩa, tạo IR, các pass biến đổi và backend.
- AST nhấn mạnh cấu trúc cú pháp; IR được thiết kế cho xử lý, tối ưu hoặc thực thi và có thể mang thêm thông tin ngữ nghĩa.
- IR có thể là cây, đồ thị, danh sách lệnh hoặc nhiều cấp biểu diễn.
- Backend có thể là interpreter, code generator, bytecode generator hoặc engine chuyên biệt.
- Các phép biến đổi IR phải bảo toàn ngữ nghĩa của DSL và giữ đủ thông tin nguồn để chẩn đoán lỗi.
- Không phải DSL nào cũng cần IR riêng; cấu trúc nên phản ánh quy mô và yêu cầu thực tế.

## 16. Câu hỏi tự kiểm tra

1. Vì sao một công cụ DSL thường chuyển chương trình qua IR trước khi thực thi?
2. AST khác IR ở mục tiêu sử dụng và mức độ thông tin ngữ nghĩa như thế nào?
3. Phân tích ngữ nghĩa giải quyết những vấn đề nào mà parser không thể xác định chỉ từ cú pháp?
4. Hãy mô tả cách câu truy vấn DSL được chuyển thành pipeline IR.
5. Nêu hai ví dụ về phép biến đổi IR và điều kiện để chúng bảo toàn ngữ nghĩa.
6. Một IR dạng đồ thị có lợi thế gì khi biểu diễn pipeline dữ liệu?
7. Vì sao cần giữ vị trí nguồn trong IR sau khi đã hạ mức trừu tượng?
8. Khi nào AST có thể được dùng trực tiếp làm biểu diễn cho interpreter mà không cần IR riêng?
