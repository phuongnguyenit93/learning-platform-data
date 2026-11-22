# Phòng chống injection runtime trong DSL

Ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) thường cho phép người dùng mô tả truy vấn, quy tắc, biểu thức, workflow hoặc mẫu đầu ra. Khi chương trình DSL được thực thi, runtime có thể đọc dữ liệu từ request, database, message queue, file, plugin hoặc dịch vụ bên ngoài rồi chuyển dữ liệu đó đến interpreter và các API của hệ thống. Nếu runtime nhầm lẫn dữ liệu với cú pháp hoặc lệnh có thể thực thi, kẻ tấn công có thể đưa nội dung vào để thay đổi ý nghĩa của chương trình. Đây là nhóm lỗ hổng **injection**.

**Phòng chống injection runtime** là thiết kế và triển khai các ranh giới an toàn để dữ liệu không đáng tin cậy không thể trở thành cú pháp, truy vấn, lệnh hệ điều hành, template directive hoặc lời gọi chức năng ngoài ý muốn. Với DSL, biện pháp quan trọng nhất là giữ riêng phần cấu trúc đã được parse và kiểm tra kiểu với dữ liệu runtime, sau đó thực thi qua API có tham số và quyền hạn rõ ràng.

Injection không chỉ xảy ra khi một ứng dụng nối chuỗi SQL. Một DSL có thể tạo query, gọi expression engine, dựng template, gọi plugin, khởi chạy process hoặc truy cập nguồn dữ liệu. Mỗi đích thực thi có cú pháp và quy tắc escape riêng. Vì vậy, một hàm escape dùng chung không thể bảo vệ mọi sink. Cần xác định dữ liệu đến từ đâu, đi qua những bước nào và cuối cùng được sử dụng trong ngữ cảnh nào.

## 1. Injection runtime là gì?

### 1.1. Khái niệm

Injection xảy ra khi dữ liệu do người dùng hoặc nguồn không tin cậy kiểm soát được diễn giải như một phần của ngôn ngữ điều khiển tại nơi thực thi. Kết quả có thể là thay đổi câu truy vấn, thêm điều kiện, gọi hàm ngoài ý muốn, đọc dữ liệu khác, thực thi lệnh hoặc truy cập tài nguyên không được phép.

Ví dụ nguy hiểm:

~~~java
String query = "SELECT * FROM Customer WHERE name = '" + inputName + "'";
database.execute(query);
~~~

Nếu inputName chứa ký tự đóng chuỗi và phần cú pháp tiếp theo, nội dung dữ liệu có thể thay đổi cấu trúc câu SQL. Vấn đề cốt lõi là ứng dụng đã ghép dữ liệu vào một chuỗi mà database sẽ phân tích lại như chương trình.

Cách an toàn hơn là giữ query structure cố định và truyền giá trị qua parameter:

~~~java
database.query(
    "SELECT * FROM Customer WHERE name = ?",
    inputName
);
~~~

Database nhận câu lệnh và giá trị theo hai kênh riêng. Giá trị không được xem là SQL syntax.

### 1.2. Runtime injection trong DSL

Trong DSL, ranh giới dữ liệu và cú pháp có thể nằm ở nhiều nơi:

- DSL source được nạp từ file hoặc editor.
- Biểu thức được tạo động từ request.
- Giá trị được chèn vào query hoặc filter.
- Rule gọi function provider hoặc plugin.
- Template tạo SQL, HTML, shell command hoặc file.
- Runtime đánh giá expression được lưu trong database.
- Plugin chuyển dữ liệu thành lời gọi hệ thống.
- API nhận payload rồi đưa trường dữ liệu vào interpreter.

Một DSL có thể an toàn ở compile time nhưng vẫn bị injection lúc chạy nếu runtime xây lại câu lệnh từ dữ liệu chưa được xử lý đúng.

### 1.3. Code và data

Nguyên tắc nền tảng là phân biệt:

- **Code:** cấu trúc đã được định nghĩa, parse, kiểm tra và cho phép thực thi.
- **Data:** giá trị được đưa vào chương trình, không có quyền thay đổi cấu trúc chương trình.

Ví dụ, biểu thức DSL sau là code:

~~~text
customer.age >= 18 and customer.status == ACTIVE
~~~

Giá trị 21 là data. Nếu runtime nhận chuỗi người dùng nhập là biểu thức rồi parse và thực thi trực tiếp, data đã bị nâng thành code. Việc này chỉ an toàn khi sản phẩm chủ đích cung cấp tính năng authoring code, có xác thực, kiểm tra và sandbox thích hợp.

### 1.4. Compile-time và runtime

Compile-time injection có thể xảy ra khi build pipeline xử lý source DSL không đáng tin hoặc plugin compile-time. Runtime injection xảy ra khi ứng dụng thực thi rule, query hoặc template với dữ liệu động.

Hai giai đoạn liên quan nhưng có ranh giới kiểm soát khác nhau. Kiểm tra source lúc build không thay thế parameter binding và authorization ở runtime, vì dữ liệu đầu vào có thể thay đổi sau khi compile.

### 1.5. Tác động

Injection có thể dẫn đến:

- Đọc hoặc sửa dữ liệu ngoài phạm vi.
- Bỏ qua điều kiện nghiệp vụ.
- Thực hiện hành động trái phép.
- Truy cập file hoặc network nội bộ.
- Thực thi mã hoặc lệnh hệ điều hành.
- Lộ dữ liệu nhạy cảm.
- Tạo workload tiêu tốn tài nguyên.
- Làm sai quyết định và audit trail.

Mức độ ảnh hưởng phụ thuộc quyền của runtime, phạm vi dữ liệu và những chức năng mà DSL được phép gọi.

## 2. Mô hình đe dọa và ranh giới tin cậy

### 2.1. Xác định nguồn dữ liệu

Mọi giá trị đi vào runtime cần có nguồn gốc rõ. Nguồn thường gặp:

- HTTP request hoặc API payload.
- Query parameter và header.
- Message queue hoặc event.
- File import.
- Database record do người dùng có thể sửa.
- Nội dung DSL do tenant hoặc khách hàng tạo.
- Plugin và extension bên thứ ba.
- Kết quả từ dịch vụ ngoài.
- Environment variable hoặc cấu hình triển khai.

Dữ liệu nội bộ không mặc nhiên đáng tin. Một database field có thể chứa nội dung do người dùng gửi từ nhiều ngày trước; khi được đọc lại và dùng để tạo query, nó vẫn là dữ liệu không tin cậy.

### 2.2. Trust boundary

Trust boundary là điểm dữ liệu đi từ vùng có mức tin cậy này sang vùng có mức tin cậy khác. Ví dụ:

~~~text
HTTP Client
    |
    v
API Gateway
    |
    v
Payload Parser
    |
    v
DSL Runtime
    |
    +----> Query Engine
    |
    +----> Function Provider
    |
    +----> Template Renderer
    |
    +----> External Service
~~~

Mỗi mũi tên cần xác định dữ liệu nào được truyền, kiểu nào được chấp nhận và quyền nào được sử dụng.

### 2.3. Xác định sink

Sink là điểm cuối nơi dữ liệu có thể ảnh hưởng đến hành vi thực thi. Ví dụ:

- SQL executor.
- NoSQL query builder.
- Shell hoặc process API.
- Expression evaluator.
- Template renderer.
- XPath hoặc LDAP query engine.
- File system API.
- URL fetcher hoặc HTTP client.
- Plugin method.
- Deserializer có thể tạo object hoặc kích hoạt callback.

Kiểm soát đầu vào mà không xác định sink có thể bỏ sót đường đi nguy hiểm.

### 2.4. Data flow

Một đường đi điển hình:

~~~text
Untrusted Input
    |
    v
Parse / Decode
    |
    v
Validate Type and Domain
    |
    v
Transform / Map
    |
    v
Execution Sink
~~~

Tại từng bước, cần giữ thông tin về nguồn và mức tin cậy. Một chuỗi đã được trim hoặc kiểm tra độ dài vẫn không tự động an toàn để chèn vào SQL hoặc shell.

### 2.5. Threat modeling

Với mỗi chức năng DSL, hãy hỏi:

1. Ai có thể cung cấp source hoặc input?
2. Họ kiểm soát trường nào?
3. Dữ liệu đi đến sink nào?
4. Runtime thực thi với quyền gì?
5. Có thể truy cập tenant hoặc tài nguyên nào?
6. Có cách nào biến giá trị thành syntax?
7. Nếu plugin hoặc service bị xâm phạm thì ảnh hưởng ra sao?
8. Hành vi bất thường được phát hiện và audit như thế nào?

## 3. Các dạng injection thường gặp

### 3.1. SQL injection

Xảy ra khi dữ liệu được ghép trực tiếp vào SQL text. Kẻ tấn công có thể thay đổi điều kiện lọc, thêm biểu thức hoặc tác động đến câu lệnh.

### 3.2. NoSQL injection

Xảy ra khi dữ liệu đầu vào được ánh xạ trực tiếp thành operator hoặc cấu trúc query của document database. Ví dụ, một trường mong đợi string lại nhận object chứa operator đặc biệt.

### 3.3. Expression language injection

Runtime nhận chuỗi từ người dùng rồi đưa vào expression evaluator. Nếu evaluator hỗ trợ truy cập object, gọi method hoặc reflection, người dùng có thể tạo biểu thức vượt khỏi phạm vi dự kiến.

### 3.4. Template injection

Dữ liệu không tin cậy được diễn giải như directive của template engine. Server-side template injection có thể cho phép truy cập object, gọi method hoặc thực thi mã tùy engine và cấu hình.

### 3.5. OS command injection

Dữ liệu được ghép vào command line hoặc shell script. Ký tự đặc biệt có thể làm thay đổi lệnh, thêm pipeline hoặc thực thi chương trình khác.

### 3.6. XPath và LDAP injection

Dữ liệu được nối vào XPath hoặc LDAP filter có thể thay đổi điều kiện tìm kiếm hoặc phạm vi kết quả.

### 3.7. HTML và JavaScript injection

Nếu dữ liệu được đưa vào HTML, attribute, URL hoặc JavaScript context mà không encode đúng ngữ cảnh, trình duyệt có thể diễn giải dữ liệu thành markup hoặc script.

### 3.8. Path và file name injection

Dữ liệu dùng làm đường dẫn có thể chứa thành phần điều hướng thư mục, separator hoặc tên thiết bị đặc biệt. Kết quả có thể là đọc, ghi hoặc ghi đè file ngoài vùng cho phép.

### 3.9. URL và header injection

Dữ liệu được ghép vào URL hoặc HTTP header có thể làm thay đổi host, path, header boundary hoặc đích kết nối. Điều này cần được xử lý bằng URL builder và API header an toàn.

### 3.10. Deserialization và object injection

Payload được deserialize thành kiểu tùy ý hoặc object có hành vi khởi tạo đặc biệt có thể kích hoạt logic không mong muốn. Chỉ deserialize kiểu đã cho phép và ưu tiên format dữ liệu đơn giản.

## 4. Thiết kế DSL để giữ code tách khỏi data

### 4.1. Parse thành AST

DSL source nên được parse thành Abstract Syntax Tree (AST), thay vì được giữ như chuỗi rồi nối thêm dữ liệu vào cuối. AST biểu diễn cấu trúc chương trình bằng node có kiểu.

Ví dụ:

~~~text
Filter(
    field = "age",
    operator = GREATER_OR_EQUAL,
    value = Parameter("minimumAge")
)
~~~

Giá trị minimumAge được lưu như parameter node. Nó không được parse lại thành toán tử hoặc biểu thức.

### 4.2. Typed AST

Typed AST gắn kiểu cho node và kiểm tra các phép toán hợp lệ trước khi thực thi. Ví dụ so sánh Integer với Date có thể bị từ chối, còn một parameter có kiểu Integer được bind vào vị trí mong đợi.

Typed AST giúp giảm khả năng một chuỗi đầu vào thay đổi cấu trúc query, nhưng không tự bảo vệ mọi sink. Backend vẫn phải sinh câu lệnh an toàn.

### 4.3. Không parse dữ liệu thành DSL source

Không làm theo kiểu:

~~~java
String expression = "customer.name == '" + input + "'";
DslProgram program = parser.parse(expression);
runtime.evaluate(program);
~~~

Đây là cách biến dữ liệu thành source. Thay vào đó, parse chương trình cố định một lần và truyền input qua context:

~~~java
DslProgram program = parser.parse(
    "customer.name == input.targetName"
);

EvaluationContext context = EvaluationContext.builder()
    .put("targetName", input)
    .build();

runtime.evaluate(program, context);
~~~

### 4.4. Parameter node

Parameter nên là node riêng với:
- Tên hoặc ID ổn định.
- Kiểu tĩnh hoặc schema.
- Giá trị runtime.
- Nullability.
- Quyền truy cập.
- Quy tắc chuyển đổi.

Không thay parameter bằng chuỗi đã format.

### 4.5. Allowlist cho cấu trúc

Nếu người dùng được chọn field, operator hoặc function, chỉ cho phép các lựa chọn đã đăng ký. Ví dụ sort field có thể là name, createdAt hoặc total; không nhận tên cột SQL tùy ý từ client.

### 4.6. AST immutable

Sau khi validate và compile, AST hoặc executable plan nên immutable nếu thiết kế cho phép. Điều này tránh một plugin hoặc request khác sửa cấu trúc đang được dùng chung.

### 4.7. Không dùng eval tùy tiện

Không cung cấp hàm eval(string) có quyền truy cập toàn bộ host runtime cho mọi DSL user. Nếu cần biểu thức do người dùng tạo, hãy dùng grammar giới hạn, typed AST, function registry allowlist và sandbox riêng.

## 5. SQL injection và query DSL

### 5.1. Parameterized query

Biện pháp chính chống SQL injection là prepared statement hoặc parameter binding. SQL structure được cố định; giá trị truyền qua parameter:

~~~java
String sql =
    "SELECT id, name FROM customer WHERE status = ? AND age >= ?";

PreparedStatement statement = connection.prepareStatement(sql);
statement.setString(1, status);
statement.setInt(2, minimumAge);
~~~

Database hiểu status và minimumAge là dữ liệu, không phải SQL syntax.

### 5.2. Query builder an toàn

Query DSL nên tạo query object hoặc AST, sau đó backend sinh SQL cùng danh sách parameter. Ví dụ:

~~~text
query Customer {
    where status == input.status
      and age >= input.minimumAge
    select id, name
}
~~~

Compiler có thể sinh SQL:

~~~sql
SELECT id, name
FROM customer
WHERE status = ?
  AND age >= ?
~~~

Giá trị input được bind riêng khi thực thi.

### 5.3. Identifier không thể bind như value

Parameter binding thường áp dụng cho giá trị, không áp dụng trực tiếp cho tên bảng, tên cột hoặc keyword. Nếu cần sort động, hãy ánh xạ lựa chọn từ allowlist:

~~~java
Map<String, String> allowedSortColumns = Map.of(
    "name", "customer_name",
    "createdAt", "created_at",
    "total", "order_total"
);

String column = allowedSortColumns.get(request.sortField());
if (column == null) {
    throw new ValidationException("Unsupported sort field");
}
~~~

Sau đó dùng query builder có hỗ trợ identifier quoting. Không nối trực tiếp request.sortField() vào SQL.

### 5.4. Operator động

Operator như =, <, >, IN hoặc LIKE cần được chọn từ enum nội bộ. Không nhận chuỗi operator bất kỳ rồi chèn vào query text.

### 5.5. LIKE pattern

Parameter binding ngăn SQL syntax injection nhưng không loại bỏ semantics wildcard của LIKE. Nếu người dùng muốn tìm chuỗi literal, cần escape ký tự wildcard theo quy tắc database và chỉ rõ ESCAPE character.

### 5.6. IN list

Với danh sách giá trị, dùng API tạo đúng số placeholder hoặc cơ chế array parameter của database. Không ghép chuỗi các phần tử vào SQL. Giới hạn số lượng item để tránh query quá lớn.

### 5.7. Stored procedure

Stored procedure cũng cần parameter binding. Việc gọi procedure bằng chuỗi động hoặc để procedure tự ghép SQL vẫn có thể bị injection.

### 5.8. Multi-tenant query

Tenant ID phải được lấy từ identity context đã xác thực hoặc policy phía server. Không chỉ tin tenantId do client gửi trong payload. Query nên luôn áp dụng tenant scope ở lớp truy cập dữ liệu.

## 6. NoSQL và document query injection

### 6.1. Rủi ro cấu trúc query

Một document query có thể chứa operator như $eq, $ne, $gt hoặc $where. Nếu ứng dụng nhận nguyên object từ client và đưa trực tiếp vào query engine, client có thể tự cung cấp operator.

### 6.2. Bind giá trị và dựng cấu trúc có kiểm soát

Không dùng payload làm query document hoàn chỉnh nếu client chỉ được phép cung cấp giá trị tìm kiếm. Hãy dựng query object ở server:

~~~javascript
const filter = {
  status: { $eq: validatedStatus },
  age: { $gte: validatedMinimumAge }
};
collection.find(filter);
~~~

Ở đây cấu trúc operator do ứng dụng tạo, còn giá trị được validate và bind vào vị trí tương ứng.

### 6.3. Strict schema

Nếu trường status yêu cầu string, từ chối object hoặc array. Không tự động chuyển mọi kiểu payload thành object query.

### 6.4. Cấm operator không cần thiết

Tắt các operator cho phép thực thi expression hoặc JavaScript nếu ứng dụng không cần chúng. Dùng allowlist cho operator được hỗ trợ.

### 6.5. Projection và update

Update payload cần chỉ rõ field được phép sửa. Không áp dụng trực tiếp object client gửi vào update document vì có thể cho phép thay đổi field nhạy cảm hoặc dùng operator không mong muốn.

## 7. Expression injection trong interpreter DSL

### 7.1. Rủi ro từ expression động

Một hệ thống rule có thể lưu biểu thức trong database rồi đánh giá lúc runtime. Nếu người dùng có thể sửa chuỗi biểu thức và runtime cấp quyền gọi mọi method, expression có thể vượt khỏi mục tiêu nghiệp vụ.

### 7.2. Grammar giới hạn

Chỉ hỗ trợ các node cần thiết:
- Literal.
- Field reference.
- Arithmetic.
- Comparison.
- Boolean operators.
- Conditional expression.
- Function call từ registry.
- Collection operation đã định nghĩa.

Không thêm reflection, arbitrary class loading hoặc truy cập filesystem nếu use case không yêu cầu.

### 7.3. Function registry

Function DSL cần được đăng ký tường minh:
- Tên function.
- Chữ ký và kiểu.
- Capability cần thiết.
- Có side effect hay không.
- Timeout và cancellation.
- Quy tắc lỗi.
- Tenant scope nếu liên quan.

Runtime chỉ resolve function trong registry đã cho phép.

### 7.4. Cấm method invocation tùy ý

Không cho phép expression gọi mọi method trên object host. Một đối tượng được đưa vào context không nên tự động phơi toàn bộ public method của nó cho DSL.

Thay vào đó, expose immutable data view hoặc facade có method giới hạn.

### 7.5. Reflection và class loading

Reflection, dynamic class loading và native interop có thể mở rộng quyền của expression rất lớn. Nếu cần, chỉ cung cấp trong môi trường authoring hoặc plugin tin cậy, có policy và isolation rõ ràng.

### 7.6. Compile expression một lần

Nếu expression là cấu hình được kiểm duyệt, parse và compile trước rồi cache executable plan theo version. Runtime chỉ bind data. Khi source thay đổi, tạo revision mới và validate trước khi activate.

### 7.7. Không cache theo chuỗi chưa chuẩn hóa

Cache key cần bao gồm expression revision, schema version, compiler version và capability context phù hợp. Không để một executable plan có quyền cao được dùng nhầm trong tenant khác.

## 8. Template injection và output encoding

### 8.1. Phân biệt template code và dữ liệu

Template có thể chứa directive, expression và include. Dữ liệu người dùng phải được truyền dưới dạng biến, không nối trực tiếp vào template source.

~~~text
Hello, {{ customerName }}
~~~

Renderer cần coi customerName là giá trị, không phải template syntax.

### 8.2. Server-side template injection

Nếu một trường do người dùng kiểm soát được dùng làm template source, người dùng có thể chèn directive hoặc expression. Chỉ cho phép template authoring ở nhóm có quyền và compile template theo sandbox policy.

### 8.3. Contextual output encoding

Cách encode phụ thuộc vị trí đầu ra:

- HTML text context: HTML encode.
- HTML attribute: attribute encode.
- JavaScript string: JavaScript string encode hoặc tránh chèn vào script.
- URL component: URL encode theo component.
- CSS: dùng API/allowlist chuyên dụng.
- SQL: parameter binding, không dùng HTML escaping.
- Shell: tránh shell; nếu buộc phải dùng, xử lý theo API và platform cụ thể.

Một hàm escape chung không thể bảo vệ mọi context.

### 8.4. Auto-escaping

Template engine có auto-escaping giúp giảm lỗi, nhưng phải hiểu chế độ và cách tắt. Không đánh dấu dữ liệu là safe HTML trừ khi đã được tạo bởi sanitizer đáng tin cậy cho đúng context.

### 8.5. Include và template path

Không cho user cung cấp đường dẫn template tùy ý. Dùng template ID allowlist hoặc resolver giới hạn trong thư mục được phép.

### 8.6. Không dùng dữ liệu làm template name tùy tiện

Nếu cần chọn template theo loại nghiệp vụ, ánh xạ mã loại sang template đã đăng ký. Không ghép request value thành file path hoặc URL template.

## 9. OS command injection

### 9.1. Nguyên nhân

Command injection thường xuất hiện khi ứng dụng ghép input vào một chuỗi lệnh rồi đưa chuỗi đó cho shell. Ký tự như dấu nháy, dấu chấm phẩy, pipe hoặc substitution có thể thay đổi cách shell phân tích.

### 9.2. Tránh shell khi có API tương đương

Dùng process API nhận executable và danh sách argument riêng, không dùng shell command string:

~~~java
ProcessBuilder builder = new ProcessBuilder(
    "/usr/bin/converter",
    "--format",
    validatedFormat,
    inputFile.toString()
);
builder.start();
~~~

Đường dẫn executable nên cố định hoặc lấy từ cấu hình tin cậy. Argument cần được validate theo contract của chương trình đích.

### 9.3. Allowlist argument

Nếu người dùng chọn format, chỉ chấp nhận giá trị như PDF hoặc PNG đã định nghĩa. Không cho phép truyền option tùy ý nếu option có thể mở rộng quyền của process.

### 9.4. File path

Resolve path dưới một base directory cố định, chuẩn hóa canonical path và xác minh kết quả vẫn nằm trong vùng cho phép. Kiểm tra symlink nếu threat model yêu cầu.

### 9.5. Quyền process

Chạy process với user ít quyền nhất, environment tối thiểu, working directory giới hạn và resource quota. Không chạy runtime DSL bằng quyền quản trị nếu không cần.

### 9.6. Timeout và output limit

Process ngoài cần timeout, giới hạn stdout/stderr và khả năng terminate process tree. Nếu không, input có thể kích hoạt lệnh chạy lâu hoặc tạo output vô hạn.

### 9.7. Không cho DSL tự tạo shell script tùy ý

Nếu DSL có tính năng automation, hãy cung cấp các action được định nghĩa như convertFile, sendNotification hoặc invokeApprovedTool. Tránh expose shell tổng quát cho mọi người dùng.

## 10. Path, URL và các interpreter khác

### 10.1. Path traversal

Đầu vào như tên file hoặc đường dẫn có thể cố thoát khỏi thư mục gốc bằng thành phần ../ hoặc biến thể encoding. Dùng API path, normalize và kiểm tra containment sau khi resolve.

### 10.2. Symbolic link

Chỉ kiểm tra chuỗi path chưa đủ nếu filesystem có symlink. Với thao tác nhạy cảm, cần kiểm soát symlink và quyền thư mục cha.

### 10.3. URL construction

Dùng URL builder để đặt scheme, host, path và query parameter riêng. Không ghép nguyên chuỗi người dùng vào URL có quyền truy cập nội bộ.

### 10.4. SSRF liên quan đến URL sink

Nếu DSL có function fetchUrl, người dùng có thể khiến server gọi địa chỉ nội bộ hoặc metadata service. Đây không phải injection syntax thuần túy nhưng là rủi ro tại sink URL/network. Cần allowlist host, chặn địa chỉ private/link-local theo policy, kiểm tra redirect và giới hạn port/protocol.

### 10.5. LDAP và XPath

Dùng API filter builder hoặc parameterization nếu thư viện hỗ trợ. Nếu phải encode literal, dùng encoder chuyên biệt cho đúng grammar LDAP/XPath, không dùng escape SQL hoặc HTML.

### 10.6. HTTP header

Không đưa CR/LF từ input vào header. Dùng API header của HTTP client/server và từ chối ký tự điều khiển không hợp lệ.

## 11. Validation, canonicalization và escaping

### 11.1. Validation không phải là escaping

Validation xác định giá trị có thuộc miền hợp lệ hay không. Escaping biến đổi biểu diễn để an toàn trong một context cụ thể. Hai biện pháp có mục tiêu khác nhau.

Ví dụ, tên người dùng có thể chứa dấu nháy hợp lệ. Từ chối mọi dấu nháy không phải cách sửa SQL injection; query phải bind parameter.

### 11.2. Allowlist validation

Ưu tiên xác định tập giá trị hoặc cấu trúc được phép:
- Enum code.
- Sort field.
- Function name.
- Operator.
- Template ID.
- Output format.
- Resource ID thuộc tenant.

Allowlist rõ ràng hơn blacklist ký tự nguy hiểm.

### 11.3. Type validation

Chuyển input thành kiểu có cấu trúc trước khi dùng. Nếu cần Integer, parse thành Integer và từ chối phần còn lại. Không giữ chuỗi rồi tự ghép vào lệnh.

### 11.4. Range và length

Giới hạn giá trị số, độ dài chuỗi, số phần tử và độ sâu cấu trúc. Những giới hạn này giảm cả lỗi logic và khả năng gây cạn tài nguyên.

### 11.5. Canonicalization

Một giá trị có thể có nhiều cách biểu diễn tương đương do percent encoding, Unicode normalization hoặc separator khác nhau. Chuẩn hóa trước khi kiểm tra policy, nhưng phải dùng đúng thứ tự theo giao thức và tránh decode lặp.

### 11.6. Kiểm tra sau canonicalization

Nếu policy kiểm tra path hoặc URL, hãy kiểm tra giá trị đã được parse và normalize bởi thư viện chuẩn. Không tự xử lý bằng thay thế chuỗi đơn giản.

### 11.7. Không double encode hoặc double decode

Encode hai lần có thể tạo dữ liệu sai; decode nhiều lần có thể biến chuỗi tưởng an toàn thành cú pháp đặc biệt. Mỗi boundary cần quy định rõ ai chịu trách nhiệm decode/encode.

### 11.8. Escaping theo sink

Nếu một sink không hỗ trợ parameterization, dùng encoder chuyên biệt do thư viện tin cậy cung cấp. Tài liệu phải nêu chính xác context mà encoder hỗ trợ.

## 12. Taint tracking và provenance

### 12.1. Taint là gì?

Taint tracking gắn nhãn dữ liệu có nguồn không tin cậy và theo dõi nhãn đó qua các phép biến đổi. Khi dữ liệu tainted đến một sink nhạy cảm, hệ thống có thể cảnh báo hoặc từ chối nếu chưa qua biện pháp phù hợp.

### 12.2. Source và sink

Ví dụ source:
- Request field.
- File upload.
- Message body.
- Database field có nguồn gốc người dùng.

Ví dụ sink:
- SQL executor.
- Shell process.
- Template source.
- Dynamic evaluator.
- File path.
- HTTP destination.

### 12.3. Sanitizer và validator

Một bước validate có thể xác nhận giá trị là enum hợp lệ. Một bước encode HTML có thể làm dữ liệu an toàn trong HTML text context. Taint label chỉ nên được hạ hoặc thay đổi khi hệ thống biết rõ phép xử lý bảo vệ context nào.

### 12.4. Typed provenance

DSL có thể giữ metadata provenance trong evaluation context:
- Source identifier.
- Tenant.
- Trust level.
- Schema version.
- Validation state.
- Allowed use.

Không cần phơi metadata này cho người dùng cuối, nhưng runtime có thể dùng nó để quyết định quyền truy cập.

### 12.5. Giới hạn của taint tracking

Taint tracking có thể bỏ sót flow qua native code, serialization hoặc plugin không instrument. Nó là lớp hỗ trợ phân tích, không thay thế API an toàn và least privilege.

## 13. Capability security và sandbox runtime

### 13.1. Least privilege

Runtime chỉ nên có quyền tối thiểu cần thiết cho tác vụ. Một rule tính giá không cần quyền đọc filesystem hoặc gửi network request.

### 13.2. Capability

Capability là quyền cụ thể được cấp dưới dạng handle hoặc interface:
- Data.Read trên một tập dữ liệu.
- Data.Write trên một resource.
- Notification.Send tới một channel.
- File.Read trong một directory.
- Network.Connect tới một service allowlist.

DSL chỉ gọi được chức năng mà evaluation context cung cấp.

### 13.3. Không truyền host object toàn quyền

Tránh đưa database connection, application context hoặc service locator tổng quát vào expression. Cung cấp facade nhỏ, immutable và giới hạn method.

### 13.4. Sandbox

Sandbox có thể giới hạn:
- File system.
- Network.
- Environment variables.
- Native calls.
- Reflection.
- Memory.
- CPU time.
- Thread hoặc task.
- Số lượng function invocation.

### 13.5. Process isolation

Chạy plugin hoặc expression không tin cậy trong process riêng giúp cách ly crash và quyền. IPC vẫn cần xác thực, schema validation, giới hạn message và timeout.

### 13.6. WebAssembly hoặc restricted VM

Runtime sandbox như WebAssembly có thể giới hạn host imports và memory. Chỉ expose host function cần thiết; module không nên tự động có quyền truy cập mọi tài nguyên của host.

### 13.7. Sandbox không phải bảo đảm tuyệt đối

Cần cập nhật runtime, kiểm tra cấu hình, giới hạn resource và đánh giá escape risk. Không chỉ dựa vào nhãn sandbox để coi plugin an toàn.

## 14. Authorization và tenant isolation

### 14.1. Authentication khác authorization

Authentication xác định caller là ai. Authorization xác định caller được làm gì trên resource nào. Một payload hợp lệ vẫn có thể yêu cầu thao tác không được phép.

### 14.2. Kiểm tra quyền ở server

Không tin các field như role, isAdmin, tenantId hoặc ownerId do client gửi. Lấy principal từ authentication context và kiểm tra quyền trên từng resource.

### 14.3. Tenant scope

Query DSL nên tự động áp dụng tenant scope từ trusted context. Không dựa vào việc người dùng nhớ thêm điều kiện tenantId trong từng query.

### 14.4. Object-level authorization

Nếu request chứa orderId, server cần xác nhận caller có quyền truy cập đúng order đó. Biết một ID không có nghĩa là có quyền đọc hoặc sửa resource.

### 14.5. Function capability

Function provider có side effect cần kiểm tra capability trước khi thực hiện. Quyền không nên chỉ được kiểm tra ở UI hoặc editor.

### 14.6. Time-of-check to time-of-use

Quyền hoặc trạng thái có thể thay đổi sau lúc kiểm tra. Với thao tác nhạy cảm, kiểm tra quyền và thực hiện thay đổi trong cùng transaction hoặc dùng cơ chế đảm bảo nhất quán phù hợp.

## 15. An toàn cho plugin và extension

### 15.1. Plugin là code có thể thực thi

Plugin có thể thực hiện logic tùy ý trong phạm vi runtime của nó. Chỉ cài plugin từ nguồn tin cậy và xác minh package, chữ ký, dependency.

### 15.2. Plugin API có phạm vi hẹp

Chỉ công bố extension point cần thiết. Plugin validator không cần quyền khởi chạy process; plugin formatter không cần quyền ghi dữ liệu nghiệp vụ.

### 15.3. Kiểm tra input/output plugin

Validate request và response theo schema. Không tin output plugin để bỏ qua kiểm tra invariant hoặc authorization.

### 15.4. Timeout và cancellation

Mọi extension point có thể chạy lâu cần timeout và cancellation. Plugin không được phép giữ request hoặc connection vô hạn.

### 15.5. Version và trust policy

Manifest cần khai báo plugin ID, version, API compatibility và capability yêu cầu. Host kiểm tra trước khi activate.

### 15.6. Isolate plugin không tin cậy

Plugin bên thứ ba có thể chạy ở process riêng hoặc sandbox. Không dùng chung secret hoặc quyền rộng hơn mức cần thiết.

## 16. Error handling và logging an toàn

### 16.1. Lỗi rõ nhưng không tiết lộ nội bộ

Khi input bị từ chối, trả error code và field path đủ để client sửa. Không trả stack trace, câu SQL, đường dẫn tuyệt đối hoặc tên class nội bộ.

### 16.2. Không che giấu lỗi bảo mật

Không biến injection attempt thành kết quả rỗng hoặc default success. Từ chối thao tác và ghi nhận sự kiện phù hợp.

### 16.3. Logging có chọn lọc

Log có thể ghi:
- Request ID.
- Rule hoặc query ID.
- Schema version.
- Sink hoặc capability.
- Error code.
- Actor và tenant theo policy.
- Kết quả validation.

Tránh log secret, token, raw payload nhạy cảm hoặc dữ liệu cá nhân không cần thiết.

### 16.4. Correlation ID

Correlation ID liên kết API request, runtime evaluation, query và plugin call. Nó giúp điều tra mà không cần ghi toàn bộ payload vào mọi log.

### 16.5. Audit trail

Với hành động nhạy cảm, audit nên ghi actor, action, resource, decision, rule revision và thời điểm. Audit record cần bảo vệ khỏi sửa đổi trái phép.

### 16.6. Phân loại security event

Có thể phân biệt:
- Input validation failure.
- Forbidden function call.
- Unauthorized resource access.
- Suspicious query structure.
- Sandbox violation.
- Resource limit exceeded.
- Plugin integrity failure.

Không phải mọi lỗi validation đều là tấn công; cần tránh cảnh báo quá mức.

## 17. Giới hạn tài nguyên và chống abuse

### 17.1. Expression complexity

Giới hạn độ sâu AST, số node, số function call và kích thước expression. Một expression hợp lệ về cú pháp vẫn có thể gây tiêu tốn CPU quá lớn.

### 17.2. Query limits

Giới hạn thời gian query, số row, độ sâu join, số subquery và kích thước kết quả. Không để DSL user tự bỏ mọi limit.

### 17.3. Regex complexity

Regex do người dùng cung cấp có thể gây catastrophic backtracking. Dùng engine có giới hạn thời gian hoặc grammar regex an toàn, giới hạn độ dài và tránh pattern nguy hiểm.

### 17.4. Recursion và loops

Giới hạn recursion depth, vòng lặp, số lần kích hoạt rule và thời gian evaluate. Runtime cần hỗ trợ cancellation.

### 17.5. Memory và payload size

Đặt giới hạn payload, collection, binary data và intermediate result. Streaming giúp giảm bộ nhớ nhưng vẫn cần quota.

### 17.6. Rate limit

Giới hạn số request hoặc evaluation theo user, tenant và endpoint. Rate limit bổ sung cho resource quota, không thay thế kiểm soát chi phí từng query.

## 18. Kiểm thử phòng chống injection

### 18.1. Unit test parameter binding

Kiểm tra input chứa dấu nháy, comment marker hoặc ký tự đặc biệt vẫn được bind như dữ liệu và không làm thay đổi query structure.

### 18.2. Test dynamic identifier

Gửi tên field không nằm trong allowlist và xác nhận request bị từ chối. Kiểm tra cả tên gần giống, ký tự Unicode và biến thể chữ hoa/thường nếu policy phân biệt.

### 18.3. Test expression injection

Thử truyền chuỗi có toán tử, function call hoặc syntax bổ sung vào parameter. Xác nhận nó vẫn là literal data và không được parse lại.

### 18.4. Test template context

Kiểm tra dữ liệu hiển thị trong HTML text, attribute và URL context được encode đúng. Không dùng một assertion cho mọi context.

### 18.5. Test command invocation

Dùng fake executable hoặc process harness để xác nhận input chỉ trở thành một argument, không thể thêm argument hoặc lệnh ngoài dự kiến. Không chạy payload thử nghiệm trên host production.

### 18.6. Test path containment

Thử path traversal, separator khác nhau, percent encoding, Unicode normalization và symlink. Xác nhận file cuối cùng vẫn nằm trong vùng cho phép.

### 18.7. Test authorization

Dùng user và tenant khác nhau để kiểm tra truy cập chéo resource. Test cả trường hợp client tự sửa tenantId trong payload.

### 18.8. Fuzzing

Fuzz parser, serializer, query builder và deserializer với chuỗi bất thường, payload lồng sâu, ký tự điều khiển và encoding sai. Theo dõi crash, timeout và resource exhaustion.

### 18.9. Property-based tests

Một property hữu ích là thay đổi giá trị parameter không được làm thay đổi số node hoặc cấu trúc query plan:

~~~text
structure(compile(query, parameter = valueA))
    == structure(compile(query, parameter = valueB))
~~~

Giá trị có thể khác, nhưng query structure phải giữ nguyên khi chỉ parameter thay đổi.

### 18.10. Regression tests

Mỗi lỗi injection đã phát hiện cần có test tái hiện ở đúng sink. Khi nâng compiler, runtime, driver hoặc plugin, chạy lại bộ security regression.

### 18.11. Negative tests

Xác nhận function không được cấp quyền bị từ chối, network host ngoài allowlist không được gọi, query quá lớn bị giới hạn và sandbox violation được xử lý đúng.

## 19. Static analysis và secure code review

### 19.1. Tìm source-to-sink flow

Static analysis có thể tìm luồng từ request, file hoặc database đến SQL, shell, template và evaluator. Đánh dấu các API nguy hiểm làm sink.

### 19.2. Phát hiện string concatenation

Tìm nơi query hoặc command được tạo bằng nối chuỗi. Không phải mọi nối chuỗi đều nguy hiểm, nhưng những chuỗi đi đến interpreter hoặc process cần được xem xét.

### 19.3. API wrapper an toàn

Tạo wrapper cho query execution, process launch, template render và file access. Review có thể tập trung vào một số API wrapper thay vì từng chỗ sử dụng primitive nguy hiểm.

### 19.4. Code review checklist theo sink

Với mỗi sink, reviewer cần xác nhận:
- Cấu trúc có cố định không?
- Giá trị có parameterized không?
- Identifier có allowlist không?
- Context encoder có đúng không?
- Quyền có được kiểm tra không?
- Resource có giới hạn không?
- Lỗi và log có an toàn không?

### 19.5. Dependency scanning

Driver database, template engine, expression engine và plugin runtime cũng có thể có lỗ hổng. Theo dõi version, advisory và cập nhật bảo mật.

## 20. Kiến trúc runtime an toàn

Một kiến trúc tham khảo:

~~~mermaid
flowchart TD
    A["Untrusted Request / Event"] --> B["Parse and Size Limits"]
    B --> C["Schema and Type Validation"]
    C --> D["Authentication and Authorization Context"]
    D --> E["Typed DSL AST / Compiled Plan"]
    E --> F["Capability-Aware Evaluator"]
    F --> G["Safe Query Builder"]
    F --> H["Allowlisted Function Registry"]
    F --> I["Context-Safe Template Renderer"]
    G --> J["Parameterized Data Access"]
    H --> K["Scoped Service Facades"]
    I --> L["Contextual Output Encoding"]
    J --> M["Structured Result / Audit"]
    K --> M
    L --> M
~~~

### 20.1. Ingress layer

Ingress layer kiểm tra kích thước, content type, encoding và cấu trúc payload trước khi tạo object miền.

### 20.2. Typed model

Payload được chuyển thành kiểu dữ liệu rõ ràng. Không giữ chuỗi thô làm đại diện cho mọi kiểu.

### 20.3. Authorization context

Runtime nhận principal và capability đã xác thực từ server. Không lấy quyền trực tiếp từ field do client kiểm soát.

### 20.4. Evaluator

Evaluator chỉ thực thi AST hoặc plan hợp lệ, dùng function registry và resource quota.

### 20.5. Safe sink adapters

Query builder, template renderer, process adapter và file service cung cấp API riêng cho từng context. Không dùng một hàm execute(string) tổng quát.

### 20.6. Result và audit

Kết quả được serialize theo schema, còn audit ghi nhận quyết định và nguồn gốc thực thi mà không làm lộ dữ liệu nhạy cảm.

## 21. Ví dụ: query DSL an toàn

Giả sử API cho phép người dùng tìm khách hàng theo trạng thái, tuổi tối thiểu và trường sắp xếp.

### 21.1. Request schema

~~~text
type CustomerSearchRequest {
    status: CustomerStatus
    minimumAge: Integer min(0) max(120)
    sortField: CustomerSortField
    descending: Boolean
}
~~~

### 21.2. DSL query cố định

~~~text
query searchCustomers(input: CustomerSearchRequest) {
    from Customer
    where status == input.status
      and age >= input.minimumAge
    orderBy input.sortField direction input.descending
    select {
        id: id,
        name: name,
        age: age
    }
}
~~~

Trong DSL thực tế, sortField phải là một enum hoặc symbol được compiler ánh xạ sang identifier đã đăng ký. Không được xem nó là chuỗi SQL tùy ý.

### 21.3. SQL backend

~~~sql
SELECT id, name, age
FROM customer
WHERE status = ?
  AND age >= ?
ORDER BY customer_name ASC
~~~

Giá trị status và minimumAge được bind. Tên cột được chọn từ mapping server-side của enum CustomerSortField.

### 21.4. Kết quả kiểm tra

- status sai enum bị từ chối ở validation.
- minimumAge ngoài range bị từ chối.
- sortField không được nhận diện không thể tạo identifier tùy ý.
- Dữ liệu chứa ký tự quote vẫn là parameter value.
- Tenant scope được lấy từ authenticated context.
- Query timeout và row limit được áp dụng.

## 22. Ví dụ: expression runtime có giới hạn

Một hệ thống cho phép người dùng cấu hình điều kiện giảm giá. Thay vì cho phép mã tùy ý, grammar chỉ hỗ trợ field reference, literal, comparison và Boolean operator.

~~~text
rule DiscountEligible {
    when customer.tier == PREMIUM
      and order.total >= input.minimumTotal
    then result = true
}
~~~

### 22.1. Compile và validate

Khi lưu rule:
1. Parse source thành AST.
2. Kiểm tra field tồn tại trong schema.
3. Kiểm tra kiểu hai vế so sánh.
4. Kiểm tra function nếu có nằm trong registry.
5. Kiểm tra capability yêu cầu.
6. Lưu immutable rule revision.

### 22.2. Evaluate

Khi chạy:
1. Nạp đúng revision đã duyệt.
2. Validate input payload.
3. Tạo evaluation context với typed values.
4. Áp dụng tenant và capability.
5. Evaluate AST.
6. Thu trace và trả result.

### 22.3. Giới hạn

Rule không được gọi reflection, đọc file hoặc truy cập network. Nếu cần dữ liệu ngoài, nó gọi một function provider đã được cấp quyền, có timeout và schema.

## 23. Ví dụ: gọi công cụ ngoài an toàn

Nếu DSL cần chuyển đổi file, hãy expose một action có tham số rõ:

~~~text
action convertDocument {
    input: FileReference
    format: OutputFormat
    result: FileReference
}
~~~

Runtime resolve FileReference trong vùng lưu trữ được phép, ánh xạ OutputFormat sang option cố định và gọi process bằng argument list. Người dùng không được cung cấp executable path hoặc raw shell command.

### 23.1. Kiểm soát file

- Xác minh file thuộc tenant hiện tại.
- Kiểm tra MIME và kích thước.
- Resolve file trong storage root.
- Tạo output path do server quản lý.
- Không tin tên file gốc.
- Giới hạn thời gian và dung lượng output.

### 23.2. Kiểm soát process

- Executable path cố định.
- Argument được xây dựng từ enum và typed value.
- Không dùng shell.
- Process chạy với user ít quyền.
- Có timeout và giới hạn output.
- Ghi audit action và kết quả.

## 24. Những sai lầm thường gặp

### 24.1. Chỉ lọc ký tự nguy hiểm

Blacklist ký tự dễ bỏ sót encoding và cú pháp của từng ngôn ngữ. Hãy giữ cấu trúc riêng, bind value và dùng allowlist.

### 24.2. Nghĩ rằng validation đã ngăn injection

Một chuỗi hợp lệ về độ dài hoặc format vẫn có thể làm thay đổi cú pháp ở sink. Validation không thay parameterization.

### 24.3. Dùng một hàm escape cho mọi nơi

SQL, HTML, JavaScript, URL, shell và LDAP có grammar khác nhau. Encoder cần đúng context.

### 24.4. Parse lại parameter như code

Parameter string không được đưa trở lại parser hoặc evaluator. Nếu sản phẩm cho phép authoring expression, cần luồng riêng có quyền và sandbox.

### 24.5. Dùng query builder nhưng nối identifier tùy ý

Parameter binding chỉ bảo vệ value. Tên cột, bảng, sort direction và operator cần allowlist hoặc API identifier an toàn.

### 24.6. Expose toàn bộ object cho DSL

Object host có thể chứa method nhạy cảm. Dùng immutable data view và service facade có capability.

### 24.7. Tin dữ liệu trong database

Dữ liệu từng được lưu không tự nhiên trở nên tin cậy. Khi được dùng lại ở sink, vẫn cần validate và encode theo context.

### 24.8. Cấp quyền quá rộng cho runtime

Một lỗi injection chỉ gây tác động trong phạm vi quyền mà runtime có. Least privilege giúp giới hạn thiệt hại.

### 24.9. Bỏ qua resource exhaustion

Một expression không có injection syntax vẫn có thể tạo query cực lớn, regex tốn CPU hoặc recursion sâu. Cần quota, timeout và cancellation.

### 24.10. Log toàn bộ payload để điều tra

Log raw input có thể làm lộ secret và dữ liệu cá nhân. Dùng structured event, masking và correlation ID.

### 24.11. Không kiểm thử backend thật

Một AST an toàn có thể bị backend adapter chuyển thành SQL không an toàn. Cần integration test trên đúng driver và engine được hỗ trợ.

### 24.12. Xem sandbox là đủ

Sandbox cần cấu hình capability, resource limit, isolation và cập nhật. Nó không thay thế parameter binding hoặc authorization.

## 25. Quy trình triển khai phòng chống injection

Một quy trình thực tế có thể gồm:

1. **Lập inventory nguồn dữ liệu:** request, event, file, database, DSL source và plugin.
2. **Lập inventory sink:** SQL, NoSQL, expression, template, process, file, URL, LDAP và serializer.
3. **Vẽ data flow:** xác định mọi đường đi từ source đến sink.
4. **Tách code và data:** parse DSL thành AST/typed plan; không nối input vào source.
5. **Dùng API an toàn:** parameterized query, process argument list, template variable và path API.
6. **Áp dụng allowlist:** field, operator, function, template và resource.
7. **Validate kiểu và miền:** schema, range, length, enum, nullability và canonical form.
8. **Áp dụng authorization:** principal, tenant scope, object-level access và capability.
9. **Giới hạn runtime:** timeout, memory, query cost, recursion, output và rate.
10. **Cách ly plugin:** process hoặc sandbox khi trust level yêu cầu.
11. **Xử lý lỗi và log:** error code ổn định, correlation ID, masking và audit.
12. **Viết security tests:** injection payload, boundary, fuzz, authorization và regression.
13. **Phân tích static:** tìm source-to-sink flow và API nguy hiểm.
14. **Theo dõi dependency:** cập nhật database driver, interpreter, template engine và plugin runtime.
15. **Đánh giá lại:** khi thêm sink, function provider hoặc capability mới, cập nhật threat model và test.

## 26. Câu hỏi tự đánh giá

1. Runtime injection là gì và vì sao nó khác lỗi cú pháp thông thường?
2. Phân biệt source, transformation và sink trong data flow.
3. Vì sao parameterized query an toàn hơn nối chuỗi SQL?
4. Tại sao không thể bind tên cột như một giá trị thông thường?
5. Typed AST giúp ngăn expression injection như thế nào?
6. Vì sao không nên đưa host object toàn quyền vào DSL context?
7. Escaping khác validation và canonicalization ra sao?
8. Vì sao một encoder không thể dùng cho SQL, HTML và shell cùng lúc?
9. Path traversal và URL injection cần những kiểm soát nào?
10. Capability security giới hạn tác động của injection ra sao?
11. Taint tracking giúp tìm source-to-sink flow như thế nào?
12. Những resource limit nào cần áp dụng cho expression runtime?
13. Làm thế nào kiểm thử dynamic identifier và parameter binding?
14. Vì sao cần integration test trên backend thực tế?
15. Log và audit cần ghi gì để điều tra mà không làm lộ payload nhạy cảm?

## Kết luận

Phòng chống injection runtime trong DSL bắt đầu bằng việc giữ code tách khỏi data. Source DSL cần được parse thành AST có kiểu; giá trị runtime được truyền qua parameter và evaluation context. Query engine cần parameterized statement, identifier phải được allowlist, template phải encode theo đúng output context, còn process và file access cần API an toàn với quyền và đường dẫn giới hạn.

Bên cạnh việc xử lý đúng sink, runtime cần xác thực kiểu và miền giá trị, kiểm tra authorization ở server, cấp capability tối thiểu, cách ly plugin không tin cậy và giới hạn CPU, memory, thời gian cùng kích thước dữ liệu. Threat modeling, taint analysis, static analysis, fuzzing, security regression và integration test giúp xác minh các ranh giới này trong toàn bộ đường đi của dữ liệu. Khi những kiểm soát được xây dựng thành nguyên tắc của DSL và runtime, người dùng vẫn có thể mô tả nghiệp vụ linh hoạt mà dữ liệu đầu vào không thể tự biến thành lệnh thực thi ngoài ý muốn.
