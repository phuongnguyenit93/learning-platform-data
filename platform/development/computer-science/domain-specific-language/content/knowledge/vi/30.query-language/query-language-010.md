# An toàn trước injection

DSL truy vấn (Query Domain-Specific Language) giúp ứng dụng mô tả dữ liệu cần đọc hoặc thay đổi bằng một ngôn ngữ có cấu trúc. Một truy vấn có thể chứa tên bảng, trường, phép so sánh, điều kiện, phép nối, sắp xếp, phân trang và các giá trị do người dùng cung cấp. Nếu ứng dụng ghép dữ liệu đầu vào trực tiếp vào chuỗi truy vấn, dữ liệu có thể bị diễn giải thành cú pháp. Kẻ tấn công khi đó có thể thay đổi ý nghĩa truy vấn, đọc dữ liệu ngoài phạm vi hoặc thực hiện thao tác không được phép. Vấn đề này được gọi là **injection**.

An toàn trước injection bắt đầu từ một nguyên tắc: **cú pháp truy vấn và dữ liệu truy vấn phải được biểu diễn tách biệt**. Một Query DSL tốt giữ cấu trúc truy vấn trong AST hoặc query model có kiểu, còn giá trị động được truyền qua parameter binding. Backend sinh câu lệnh đích và gửi tham số riêng cho database hoặc query engine. Cách làm này ngăn dữ liệu được hiểu như một phần của grammar.

Ví dụ truy vấn tìm người dùng theo email:

~~~sql
SELECT id, display_name
FROM users
WHERE email = ?
~~~

Giá trị email được truyền bằng parameter riêng. Nếu người dùng nhập một chuỗi có chứa dấu nháy hoặc từ khóa SQL, database vẫn xử lý nó như giá trị của email, không biến nó thành một phần của câu lệnh.

Trong Query DSL, trách nhiệm an toàn trải dài từ thiết kế API, parser, semantic model, code generator, parameter binding, quyền truy cập dữ liệu cho tới kiểm thử và vận hành. Chỉ escape một vài ký tự hoặc dùng một thư viện ORM không tự động bảo đảm hệ thống an toàn.

## 1. Injection là gì?

**Injection** xảy ra khi dữ liệu đầu vào không đáng tin cậy được ghép vào một ngôn ngữ có cú pháp và sau đó bị bộ phân tích hoặc engine diễn giải như mã lệnh. Kẻ tấn công tận dụng ranh giới không rõ giữa dữ liệu và cú pháp để thay đổi chương trình mà nhà phát triển dự định thực hiện.

Ví dụ không an toàn:

~~~javascript
const sql =
  "SELECT * FROM users WHERE email = '" + email + "'";
~~~

Nếu email được cung cấp bởi người dùng và chứa nội dung có thể đóng chuỗi literal rồi thêm điều kiện khác, chuỗi SQL kết quả có thể khác với ý định ban đầu.

Vấn đề không nằm ở việc chuỗi có ký tự đặc biệt. Vấn đề là ứng dụng đã dùng dữ liệu để xây dựng grammar của truy vấn. Một chuỗi có thể hoàn toàn hợp lệ làm dữ liệu nhưng lại có ý nghĩa đặc biệt khi xuất hiện ở vị trí cú pháp.

### 1.1. Hậu quả của SQL injection

Nhà phát triển muốn tìm đúng một email. Nếu đầu vào được chèn trực tiếp, người dùng có thể cung cấp nội dung làm thay đổi biểu thức WHERE hoặc phần còn lại của câu lệnh. Tùy cách ghép chuỗi, database và quyền của tài khoản kết nối, hậu quả có thể gồm:

- Bỏ qua điều kiện xác thực.
- Đọc bản ghi của người dùng khác.
- Sửa hoặc xóa dữ liệu.
- Đọc dữ liệu từ bảng khác.
- Gọi chức năng database ngoài dự kiến.
- Làm lộ cấu trúc schema hoặc thông tin nội bộ qua lỗi.

### 1.2. Injection không chỉ xảy ra trong SQL

Mọi ngôn ngữ truy vấn hoặc biểu diễn có grammar đều có nguy cơ tương tự nếu dữ liệu được đưa vào sai vị trí:

| Loại | Ví dụ mục tiêu | Rủi ro |
|---|---|---|
| SQL injection | SQL database | Thay đổi điều kiện hoặc câu lệnh |
| NoSQL injection | Document query | Chèn operator hoặc biểu thức truy vấn |
| GraphQL injection | GraphQL document | Thay đổi cấu trúc query hoặc selection |
| LDAP injection | LDAP filter | Mở rộng phạm vi tìm kiếm |
| XPath injection | XPath expression | Thay đổi điều kiện truy vấn XML |
| Search query injection | Search engine syntax | Thay đổi field, operator hoặc phạm vi tìm kiếm |

Mỗi ngôn ngữ có quy tắc escaping và parameterization riêng. Biện pháp an toàn cần dựa trên grammar và API chính thức của engine đích.

## 2. Vì sao Query DSL cần quan tâm tới injection?

Query DSL thường được giới thiệu như một lớp trừu tượng an toàn hơn so với ghép chuỗi SQL. Điều đó chỉ đúng khi DSL giữ được cấu trúc truy vấn và truyền dữ liệu động theo cách an toàn.

Ví dụ một API có vẻ tiện:

~~~javascript
query("users")
  .where("email = '" + email + "'");
~~~

API này vẫn ghép chuỗi và vẫn có nguy cơ injection. Việc bọc câu lệnh trong một hàm có tên query không làm dữ liệu trở nên an toàn.

Ngược lại, API có cấu trúc:

~~~javascript
query(users)
  .where(eq(users.email, value(email)));
~~~

có thể tạo AST gồm:

~~~text
Select
  From: users
  Where:
    Equal
      Column: users.email
      Parameter: p1
~~~

Backend sinh SQL với placeholder và truyền email trong danh sách parameter. Cấu trúc của truy vấn không bị thay đổi bởi nội dung email.

Query DSL cần quan tâm injection vì:

- Query thường nhận dữ liệu từ form, API, file hoặc message bên ngoài.
- Truy vấn có thể được tạo động theo filter, sort và pagination.
- Một số API DSL cho phép raw query hoặc raw expression.
- DSL có thể hỗ trợ nhiều backend với cách bind parameter khác nhau.
- Truy vấn có thể thực hiện dưới quyền database rộng hơn quyền người dùng cuối.
- Lỗi truy vấn có thể làm lộ dữ liệu hoặc ảnh hưởng tính toàn vẹn của hệ thống.

## 3. Nguyên tắc cốt lõi: tách cú pháp khỏi dữ liệu

Một truy vấn có thể được xem như hai phần:

1. **Cấu trúc:** bảng, cột, phép nối, toán tử, điều kiện và thứ tự thực thi.
2. **Giá trị:** email, tên, ngày tháng, số lượng, trạng thái hoặc dữ liệu do người dùng cung cấp.

Giá trị động nên được truyền dưới dạng parameter. Cấu trúc truy vấn phải được tạo từ AST, query builder có kiểu, schema hoặc lựa chọn được kiểm soát.

~~~mermaid
flowchart TD
    A[Untrusted input] --> B[Validate and normalize value]
    B --> C[Typed parameter]
    D[Trusted query structure] --> E[Query AST]
    C --> E
    E --> F[Target query and placeholders]
    F --> G[Database driver]
    C --> H[Separate parameter values]
    H --> G
    G --> I[Query result]
~~~

### 3.1. Parameterization

Parameterization là cách truyền giá trị riêng khỏi câu lệnh truy vấn. Ví dụ:

~~~java
String sql = "SELECT id FROM users WHERE email = ?";
PreparedStatement statement = connection.prepareStatement(sql);
statement.setString(1, email);
ResultSet result = statement.executeQuery();
~~~

Placeholder đại diện cho giá trị. Driver truyền email như một parameter theo protocol database.

Các database hoặc driver khác nhau có thể dùng placeholder dạng dấu hỏi, ký hiệu vị trí hoặc tên parameter. Cần dùng đúng API của driver thay vì tự thay placeholder bằng chuỗi.

### 3.2. Prepared statement

Prepared statement cho phép database nhận câu lệnh và giá trị tham số tách biệt. Database hoặc driver có thể chuẩn bị và thực thi câu lệnh với các giá trị khác nhau.

Lợi ích bảo mật quan trọng là giá trị parameter không được parse lại như một phần grammar SQL. Prepared statement cũng có thể hỗ trợ tái sử dụng kế hoạch thực thi, nhưng hiệu năng phụ thuộc database và workload.

### 3.3. Parameter không phải identifier

Parameter thường dùng cho giá trị như string, number, date hoặc boolean. Nó không thay thế trực tiếp tên bảng, tên cột, keyword hoặc hướng sắp xếp.

Ví dụ, câu lệnh sau thường sắp xếp theo một biểu thức giá trị hằng:

~~~sql
SELECT * FROM users ORDER BY ?
~~~

Nó không có nghĩa parameter được thay bằng tên cột. Không thể dùng parameter binding để chọn tùy ý một identifier trong grammar SQL.

Tên bảng, tên cột và operator động cần được chọn từ tập cho phép, tạo bằng AST có kiểu hoặc được kiểm tra bằng allowlist.

## 4. Query DSL an toàn nên biểu diễn truy vấn bằng AST

AST (Abstract Syntax Tree) biểu diễn cấu trúc truy vấn thành các node có kiểu. Thay vì giữ một chuỗi SQL duy nhất, DSL lưu từng thành phần như Select, Table, Column, Equal, And, OrderBy và Parameter.

Ví dụ truy vấn:

~~~text
select users.id, users.email
from users
where users.status == parameter("status")
  and users.createdAt >= parameter("since")
~~~

AST khái niệm:

~~~text
Select
  Projection
    Column(users.id)
    Column(users.email)
  From
    Table(users)
  Where
    And
      Equal
        Column(users.status)
        Parameter(status, String)
      GreaterThanOrEqual
        Column(users.createdAt)
        Parameter(since, Timestamp)
~~~

Code generator chỉ nhận những node mà DSL cho phép. Người dùng không thể thêm một dấu chấm phẩy hay keyword bằng cách đưa chúng vào giá trị parameter.

### 4.1. Node riêng cho từng khái niệm

AST có thể định nghĩa các node:

- Query node: Select, Insert, Update, Delete.
- Relation node: Table, Join, Subquery.
- Expression node: Column, Literal, Parameter, FunctionCall.
- Predicate node: Equal, LessThan, And, Or, Not, IsNull.
- Ordering node: OrderBy, Ascending, Descending.
- Pagination node: Limit, Offset hoặc Cursor.

Không nên dùng một node RawString cho mọi cấu trúc. Nếu mọi phần đều có thể chứa chuỗi tùy ý, AST không còn bảo vệ được grammar.

### 4.2. Type của node

Node có thể giữ type metadata:

~~~text
Parameter(name = "age", type = Integer)
Column(name = "age", type = Integer)
GreaterThan(left = Column(age), right = Parameter(age))
~~~

Type checker xác nhận hai toán hạng tương thích trước khi sinh query. Kiểu giúp ngăn lỗi dữ liệu và có thể hỗ trợ parameter binding chính xác.

### 4.3. Không serialize rồi parse lại như một cách parameterize

Một cách thiết kế kém là tạo một chuỗi query bằng nối giá trị, sau đó cố escape hoặc parse chuỗi đó để tìm parameter. Cách này khó bảo đảm vì grammar có thể phức tạp và escaping phụ thuộc context.

Hãy giữ cấu trúc truy vấn trong AST từ lúc xây dựng cho tới lúc backend tạo query và parameter list.

## 5. Query builder có kiểu

Query builder có kiểu (typed query builder) là API tạo truy vấn mà mỗi thao tác trả về một kiểu mô tả phần cấu trúc hiện tại. Các thao tác chỉ cho phép những thành phần hợp lệ theo schema.

Ví dụ TypeScript minh họa:

~~~typescript
const result = db
  .select({
    id: users.id,
    email: users.email
  })
  .from(users)
  .where(eq(users.status, param(status)))
  .limit(50);
~~~

API có thể bảo đảm:

- users.status là một column đã biết.
- eq nhận hai biểu thức có kiểu tương thích.
- param(status) được bind riêng.
- limit nhận số nguyên trong range hợp lệ.
- Query builder không nhận một chuỗi SQL tùy ý ở vị trí điều kiện thông thường.

### 5.1. Type-safe không tự động có nghĩa injection-safe

Một thư viện có type declaration vẫn có thể cung cấp hàm raw. Hàm này chỉ an toàn nếu contract của nó thực sự biến giá trị thành parameter. Nếu nó chỉ nối chuỗi, type system không bảo vệ khỏi injection.

Type safety kiểm tra quan hệ kiểu. Injection safety yêu cầu dữ liệu động không trở thành cú pháp. Hai thuộc tính có liên quan nhưng không đồng nhất.

### 5.2. Schema-generated API

DSL có thể sinh query builder từ database schema:

~~~text
users.id: Integer
users.email: String
users.status: UserStatus
~~~

API được sinh chỉ expose column và operator phù hợp. Điều này giảm lỗi chính tả, sai kiểu và truy vấn tới field không tồn tại.

### 5.3. Runtime validation vẫn cần thiết

TypeScript hoặc Java type chỉ bảo vệ lúc compile trong phạm vi mà type system kiểm soát. Dữ liệu từ HTTP request, JSON hoặc message vẫn cần validate runtime. Một client có thể gửi kiểu dữ liệu không đúng dù code gọi API được type-check.

## 6. Ví dụ SQL injection và cách parameterize

Giả sử ứng dụng tìm user theo email.

### 6.1. Cách ghép chuỗi không an toàn

~~~javascript
const sql =
  "SELECT id, email FROM users WHERE email = '" + email + "'";

db.query(sql);
~~~

Đầu vào được nối vào chuỗi SQL. Nếu nó chứa cú pháp có ý nghĩa trong SQL, cấu trúc câu lệnh có thể thay đổi.

### 6.2. Dùng parameter binding

~~~javascript
const sql =
  "SELECT id, email FROM users WHERE email = ?";

db.query(sql, [email]);
~~~

Ở đây câu lệnh và giá trị được gửi riêng. Nội dung email được xử lý như dữ liệu.

### 6.3. Dùng Query DSL

~~~typescript
const query = select(users.id, users.email)
  .from(users)
  .where(eq(users.email, param(email)));

const result = await query.execute(db);
~~~

DSL giữ cấu trúc bằng node Select, From, Where, Equal và Parameter. Backend sinh placeholder phù hợp với database đích.

### 6.4. Nhiều điều kiện động

Một form tìm kiếm có thể gửi email, trạng thái và ngày tạo. Thay vì nối điều kiện, hãy xây predicate:

~~~typescript
const predicates = [];

if (filters.email !== undefined) {
  predicates.push(eq(users.email, param(filters.email)));
}

if (filters.status !== undefined) {
  predicates.push(eq(users.status, param(filters.status)));
}

if (filters.createdAfter !== undefined) {
  predicates.push(
    gte(users.createdAt, param(filters.createdAfter))
  );
}

const query = select(users.id, users.email)
  .from(users)
  .where(and(...predicates));
~~~

Mỗi giá trị được giữ ở node parameter. Các toán tử và column đến từ API/schema đã biết.

## 7. Identifier động: tên bảng và tên cột

Một ứng dụng đôi khi cho phép người dùng chọn field để sắp xếp hoặc lọc. Vì identifier không thể bind như giá trị thông thường, cần kiểm soát chặt.

Ví dụ yêu cầu sắp xếp:

~~~json
{
  "sortBy": "createdAt",
  "direction": "desc"
}
~~~

Không nên ghép trực tiếp sortBy vào SQL. Thay vào đó, ánh xạ giá trị đầu vào sang các column đã được định nghĩa:

~~~typescript
const sortableColumns = {
  createdAt: users.createdAt,
  email: users.email,
  displayName: users.displayName
};

const column = sortableColumns[input.sortBy];

if (!column) {
  throw new Error("Unsupported sort field");
}

const direction =
  input.direction === "desc" ? desc : asc;

const query = select(users.id, users.email)
  .from(users)
  .orderBy(direction(column));
~~~

Trong ví dụ, input chỉ chọn một phần tử từ allowlist. Nó không được biến thành identifier tùy ý.

### 7.1. Allowlist

Allowlist là tập các giá trị hợp lệ được định nghĩa trước. Với identifier động, allowlist nên chứa object hoặc symbol đã resolve trong schema, không chỉ chuỗi chưa kiểm tra.

| Đầu vào client | Ánh xạ được phép |
|---|---|
| createdAt | users.createdAt |
| email | users.email |
| displayName | users.displayName |
| passwordHash | Từ chối |
| bất kỳ chuỗi khác | Từ chối |

### 7.2. Không dùng blocklist

Blocklist cố gắng loại một số keyword hoặc ký tự bị cho là nguy hiểm. Cách này dễ bỏ sót cú pháp khác, comment, encoding hoặc cách viết hợp lệ khác của database. Allowlist định nghĩa chính xác những lựa chọn được phép và thường dễ kiểm soát hơn.

### 7.3. Quote identifier

Database có cơ chế quote identifier, nhưng quoting chỉ giúp tên được hiểu là identifier đúng cú pháp. Nó không tự xác định người dùng có quyền chọn identifier đó hay không. Vẫn cần allowlist và authorization.

### 7.4. Schema và table động

Nếu tenant hoặc module có database schema riêng, tên schema cần được lấy từ mapping tin cậy của session/tenant. Không dùng trực tiếp một chuỗi schema do client gửi.

## 8. Operator động và cấu trúc điều kiện

Không chỉ identifier, operator cũng là một phần grammar. Nếu API cho phép client gửi operator:

~~~json
{
  "field": "age",
  "operator": "gte",
  "value": 18
}
~~~

hãy ánh xạ operator từ danh sách cho phép:

~~~typescript
const operatorBuilders = {
  eq: (column, value) => eq(column, value),
  ne: (column, value) => ne(column, value),
  gt: (column, value) => gt(column, value),
  gte: (column, value) => gte(column, value),
  lt: (column, value) => lt(column, value),
  lte: (column, value) => lte(column, value)
};
~~~

Không nên lấy chuỗi operator rồi chèn trực tiếp vào query text. Đồng thời, cần kiểm tra operator phù hợp với kiểu column. Ví dụ, greater-than có thể hợp lệ với number hoặc date nhưng không nhất thiết hợp lệ với mọi kiểu domain.

### 8.1. Boolean expression

Các node And, Or và Not cần được xây từ biểu thức con đã kiểm tra. Không nhận một đoạn WHERE text do client gửi vào API thông thường.

### 8.2. Nhóm điều kiện

AST nên giữ cấu trúc nhóm rõ ràng:

~~~text
And(
    Equal(status, Parameter(p1)),
    Or(
        GreaterThan(age, Parameter(p2)),
        IsNull(lastLogin)
    )
)
~~~

Code generator chịu trách nhiệm thêm ngoặc và sinh placeholder đúng thứ tự. Không nên tự ghép chuỗi điều kiện bằng cách nối các đoạn SQL không có metadata.

## 9. IN, danh sách và collection parameter

Truy vấn có thể dùng danh sách giá trị:

~~~sql
SELECT id
FROM products
WHERE category_id IN (?, ?, ?)
~~~

Mỗi phần tử phải được bind như một parameter. Không nối các phần tử thành một chuỗi có dấu phẩy.

### 9.1. Collection binding

Một số driver hỗ trợ bind array hoặc collection trực tiếp. Một số driver cần tạo một placeholder cho mỗi phần tử. Query DSL backend phải biết capability của driver.

### 9.2. Danh sách rỗng

Nếu danh sách rỗng, DSL cần quy định semantics:

- Điều kiện luôn false.
- Bỏ qua điều kiện nếu đó là filter tùy chọn.
- Báo lỗi đầu vào.

Không nên sinh SQL không hợp lệ hoặc vô tình bỏ điều kiện lọc.

### 9.3. Giới hạn kích thước

Danh sách rất lớn có thể vượt giới hạn parameter của database hoặc tạo query tốn tài nguyên. Cần giới hạn số phần tử hoặc dùng cơ chế phù hợp như temporary table, table-valued parameter hoặc array parameter tùy backend.

## 10. LIKE và wildcard injection

Parameter binding ngăn dữ liệu trở thành cú pháp SQL, nhưng không nhất thiết ngăn người dùng điều khiển wildcard của toán tử LIKE.

Ví dụ:

~~~sql
SELECT id
FROM users
WHERE display_name LIKE ?
~~~

Nếu ứng dụng bind giá trị phần trăm, truy vấn có thể tìm mọi tên. Đây không phải SQL syntax injection; đó là việc người dùng điều khiển semantics của pattern.

Nếu nghiệp vụ yêu cầu tìm chuỗi literal, cần escape wildcard theo quy tắc của database và chỉ định escape character:

~~~sql
WHERE display_name LIKE ? ESCAPE '\\'
~~~

Giá trị pattern cần được xử lý để ký tự phần trăm, dấu gạch dưới và escape character được xem như literal. Cú pháp chính xác phụ thuộc dialect SQL.

Phân biệt hai mục tiêu:

- Injection safety: dữ liệu không thay đổi grammar truy vấn.
- Input semantics: dữ liệu chỉ được phép tạo loại pattern mà nghiệp vụ cho phép.

Parameterization giải quyết mục tiêu đầu; validation và pattern escaping theo semantics giải quyết mục tiêu thứ hai.

## 11. LIMIT, OFFSET và pagination

LIMIT và OFFSET thường nhận giá trị số. Nhiều database cho phép bind chúng như parameter, nhưng Query DSL cần kiểm tra kiểu và range.

Ví dụ:

~~~typescript
const pageSize = Math.min(
  Math.max(Number(input.pageSize) || 20, 1),
  100
);

const offset = Math.max(Number(input.offset) || 0, 0);

const query = select(users.id, users.email)
  .from(users)
  .limit(param(pageSize))
  .offset(param(offset));
~~~

Kiểm tra range ngăn page size âm, quá lớn hoặc offset không hợp lệ. Nó cũng giúp giảm nguy cơ query tiêu tốn tài nguyên bất thường.

### 11.1. Cursor pagination

Cursor pagination thường dùng giá trị khóa cuối cùng của trang trước:

~~~text
where users.id > parameter("cursor")
order by users.id ascending
limit parameter("pageSize")
~~~

Cursor cần được validate và có thể được ký hoặc mã hóa để ngăn client sửa cấu trúc hoặc mở rộng phạm vi. Dù cursor được mã hóa, backend vẫn cần bind giá trị như parameter.

### 11.2. Không để pagination bỏ qua authorization

Mỗi trang vẫn phải áp dụng tenant và authorization predicate. Không nên chỉ bảo vệ truy vấn trang đầu rồi dùng cursor không giới hạn cho các trang sau.

## 12. NoSQL operator injection

NoSQL không có nghĩa là không thể xảy ra injection. Một số document database nhận query dưới dạng object có operator. Nếu ứng dụng nhận object tùy ý từ client và chuyển thẳng cho database, client có thể gửi operator ngoài dự kiến.

Ví dụ API muốn nhận:

~~~json
{
  "email": "person@example.com"
}
~~~

Nhưng client gửi một object thay cho string:

~~~json
{
  "email": {
    "$ne": null
  }
}
~~~

Nếu backend đưa object này trực tiếp vào filter document, điều kiện có thể trở thành một phép so sánh operator thay vì equality với email string.

### 12.1. Xây query object từ schema

Không chuyển toàn bộ request body thành database filter. Hãy chọn field và toán tử được phép:

~~~typescript
const filter = {
  email: {
    $eq: validateEmail(input.email)
  }
};

collection.find(filter);
~~~

Ở đây backend tạo operator và chỉ truyền giá trị email đã validate.

### 12.2. Reject object ở nơi cần scalar

Nếu email phải là string, từ chối object, array hoặc giá trị không phải string. Validation cần kiểm tra cả cấu trúc và kiểu runtime.

### 12.3. Không nhận query operator tùy ý

Một API tìm kiếm nâng cao có thể cho phép operator như eq, contains hoặc in. Hãy ánh xạ từng operator qua enum và builder đã kiểm soát. Không chuyển tiếp nguyên object query của client.

### 12.4. Aggregation pipeline

Aggregation pipeline có thể chứa nhiều stage và operator. Nếu client được phép gửi stage tùy ý, họ có thể truy cập collection hoặc biểu thức ngoài dự kiến. Nên định nghĩa một DSL con có schema và whitelist stage, hoặc chỉ cho phép những thao tác nghiệp vụ cần thiết.

## 13. GraphQL và các ngôn ngữ truy vấn có cấu trúc

GraphQL query cũng là một document có grammar. Nếu server xây GraphQL document bằng cách nối chuỗi chứa input, dữ liệu có thể làm thay đổi cấu trúc query.

### 13.1. Dùng variables

GraphQL hỗ trợ variables để tách giá trị khỏi document:

~~~graphql
query UserByEmail($email: String!) {
  userByEmail(email: $email) {
    id
    displayName
  }
}
~~~

Giá trị email được truyền trong variables object. Không nối nó vào query document.

### 13.2. Kiểm tra quyền ở resolver

Parameterization không thay thế authorization. Resolver cần xác nhận caller có quyền đọc user hoặc field được yêu cầu.

### 13.3. Giới hạn độ phức tạp

Query GraphQL hợp lệ vẫn có thể quá tốn tài nguyên do nested selections, alias hoặc pagination lớn. Cần giới hạn depth, cost, số lượng node và thời gian thực thi.

## 14. Raw query và escape hatch

Một Query DSL có thể cung cấp raw SQL hoặc raw expression để hỗ trợ tính năng database đặc thù. Đây là vùng rủi ro cao vì người gọi có thể quay lại cách ghép chuỗi.

Ví dụ API nguy hiểm:

~~~typescript
db.raw("SELECT * FROM users WHERE email = '" + email + "'");
~~~

API raw an toàn hơn nên yêu cầu template hoặc cấu trúc parameter:

~~~typescript
db.raw(
  "SELECT * FROM users WHERE email = ?",
  [email]
);
~~~

Tên API không chứng minh nó an toàn. Cần đọc và hiểu contract của thư viện.

### 14.1. Giới hạn quyền của raw API

Có thể:

- Đặt raw query trong module riêng.
- Yêu cầu review hoặc annotation.
- Không expose raw API cho code nghiệp vụ thông thường.
- Ghi audit nơi raw query được dùng.
- Dùng static analysis để tìm call site.
- Cấm raw query trong policy của project.

### 14.2. Raw fragment phải có type

Nếu cần hỗ trợ raw expression, DSL có thể phân biệt:

- RawIdentifier đã được validate và quote.
- RawExpression được xây từ AST tin cậy.
- BoundParameter chứa dữ liệu.
- UnsafeRawText chỉ dùng trong API đặc quyền.

Không nên dùng cùng một kiểu String cho cả identifier, expression và value.

### 14.3. Không tin dữ liệu đã được escape ở nơi khác

Một chuỗi được escape cho HTML không tự động an toàn cho SQL. Một chuỗi đã URL encode cũng không phải SQL-safe. Escaping phụ thuộc context và không nên được coi là thuộc tính vĩnh viễn của chuỗi.

## 15. Escaping không thay thế parameterization

Escaping cố gắng biến ký tự đặc biệt thành dạng literal theo grammar đích. Tuy nhiên, escaping có nhiều giới hạn:

- Quy tắc khác nhau giữa database và SQL dialect.
- Context khác nhau: string, identifier, LIKE pattern, JSON path.
- Encoding và collation có thể ảnh hưởng cách diễn giải.
- Một lần encode không bảo đảm an toàn khi chuỗi đi qua context khác.
- Dễ quên escape một trường hợp hoặc escape hai lần.

Parameter binding là lựa chọn ưu tiên cho giá trị. Escaping chỉ nên dùng khi grammar hoặc API yêu cầu một trường hợp cụ thể mà parameter không thể biểu diễn, và phải dùng hàm chuyên dụng của backend.

### 15.1. Context-specific escaping

Không có một hàm escape tổng quát dùng an toàn cho mọi ngữ cảnh. Ví dụ:

- SQL string literal.
- SQL identifier.
- LIKE pattern.
- JSON string.
- XPath literal.
- Search query syntax.

Mỗi context có grammar riêng.

### 15.2. Double encoding và normalization

Nếu dữ liệu được encode nhiều lần hoặc normalize ở những bước khác nhau, hệ thống có thể kiểm tra một dạng nhưng engine lại nhận dạng dạng khác. Nên xác định một canonical representation cho validation và dùng driver binding để truyền dữ liệu.

### 15.3. Không tự viết SQL escaping

Không nên tự triển khai thuật toán escape quote hoặc comment marker. Hãy dùng parameter binding của driver và identifier quoting API của database khi thật sự cần identifier động.

## 16. Stored procedure và dynamic SQL

Stored procedure có thể giúp tập trung logic trong database, nhưng không tự động an toàn.

Ví dụ procedure an toàn về ý tưởng:

~~~sql
CREATE PROCEDURE find_user(IN requested_email VARCHAR(255))
BEGIN
    SELECT id, email
    FROM users
    WHERE email = requested_email;
END;
~~~

Procedure dùng tham số làm giá trị.

Nếu procedure tự ghép requested_email vào dynamic SQL string rồi execute, nó vẫn có nguy cơ injection. Việc đặt logic trong database không thay thế parameterization.

### 16.1. Dynamic table hoặc column

Nếu procedure cần chọn bảng theo input, cần validate identifier từ allowlist và dùng API quote identifier phù hợp. Không nối identifier tùy ý vào dynamic SQL.

### 16.2. Quyền của procedure

Một procedure chạy với quyền definer có thể có quyền cao hơn caller. Cần kiểm tra quyền thực thi, phạm vi dữ liệu và cách procedure áp dụng authorization.

## 17. Second-order injection

Second-order injection xảy ra khi dữ liệu đầu vào được lưu trữ trước, sau đó được sử dụng trong một truy vấn khác theo cách không an toàn.

Ví dụ:

1. Người dùng nhập một chuỗi vào trường cấu hình tìm kiếm.
2. Ứng dụng lưu chuỗi đó trong database.
3. Một tác vụ quản trị đọc lại và ghép chuỗi vào SQL.
4. Nội dung được lưu trước đó được diễn giải thành cú pháp ở truy vấn sau.

Việc dữ liệu đã được lưu trong database không làm nó trở nên đáng tin cậy. Khi sử dụng trong một query context mới, vẫn phải bind như parameter hoặc validate theo vai trò dữ liệu.

### 17.1. Taint tracking

Một compiler hoặc Query DSL có thể gắn metadata tainted cho dữ liệu đến từ nguồn không tin cậy. Khi dữ liệu đi vào vị trí cấu trúc, checker cảnh báo; khi đi vào Parameter node, dữ liệu được truyền qua binding.

Taint tracking có thể hỗ trợ phân tích tĩnh nhưng cần hiểu luồng dữ liệu và các hàm sanitize. Nó không thay thế thiết kế API an toàn.

## 18. Authorization và tenant isolation

Ngăn injection chỉ bảo vệ cấu trúc truy vấn. Một truy vấn được tạo an toàn vẫn có thể đọc dữ liệu mà caller không được phép xem.

Ví dụ:

~~~typescript
const query = select(orders.id, orders.total)
  .from(orders)
  .where(eq(orders.id, param(requestedOrderId)));
~~~

Query này không có dấu hiệu injection, nhưng nếu không kiểm tra quyền sở hữu đơn hàng, người dùng có thể đọc order của tenant khác.

### 18.1. Authorization predicate

Có thể áp dụng tenant filter từ context tin cậy:

~~~typescript
const query = select(orders.id, orders.total)
  .from(orders)
  .where(and(
    eq(orders.id, param(requestedOrderId)),
    eq(orders.tenantId, param(authenticatedTenant.id))
  ));
~~~

tenant ID phải lấy từ authentication/session context đã xác thực, không lấy trực tiếp từ field do client tự khai báo.

### 18.2. Centralized query policy

Nếu mỗi developer tự nhớ thêm tenant filter, một truy vấn mới có thể quên điều kiện. Query DSL có thể cung cấp scoped repository hoặc policy layer tự động thêm điều kiện bắt buộc.

### 18.3. Row-level security

Database row-level security có thể cung cấp lớp bảo vệ bổ sung. Cần cấu hình session context an toàn và kiểm thử quyền thực tế. Không nên giả định RLS đang bật chỉ vì schema hoặc migration có policy.

### 18.4. Không nhầm filtering với authorization

Filter do người dùng chọn nhằm giới hạn kết quả tìm kiếm. Authorization là quy tắc quyết định người dùng được truy cập dữ liệu nào. Không nên để client tự cung cấp filter rồi coi nó là điều kiện phân quyền.

## 19. Least privilege cho query execution

Nếu query vẫn bị khai thác hoặc có bug, quyền của database account quyết định mức độ ảnh hưởng.

Một số nguyên tắc:

- Dùng account riêng cho từng ứng dụng hoặc service.
- Chỉ cấp quyền trên schema và bảng cần thiết.
- Không dùng tài khoản admin hoặc superuser cho request thông thường.
- Tách quyền đọc và ghi nếu phù hợp.
- Giới hạn quyền DDL và quản trị.
- Xem xét quyền execute procedure.
- Xoay vòng credential và quản lý qua secret manager.

Query DSL có thể khai báo operation capability để compiler hoặc runtime xác định truy vấn có quyền thực hiện SELECT, INSERT, UPDATE hay DELETE. Database privilege vẫn là lớp enforce cuối cùng.

## 20. Kiểm soát độ phức tạp và tài nguyên truy vấn

Một query không cần injection vẫn có thể gây từ chối dịch vụ nếu quá tốn tài nguyên.

Các nguồn rủi ro:

- Không có pagination hoặc giới hạn quá lớn.
- Filter không có index trên bảng lớn.
- Join nhiều quan hệ không cần thiết.
- Regex hoặc full-text pattern tốn kém.
- Subquery lồng sâu.
- GraphQL selection quá phức tạp.
- IN list chứa quá nhiều phần tử.
- Client được phép yêu cầu sort theo expression đắt đỏ.

### 20.1. Query budget

DSL hoặc runtime có thể đặt giới hạn:

- Maximum rows.
- Maximum page size.
- Maximum join count.
- Maximum AST depth.
- Maximum number of predicates.
- Query timeout.
- Database statement timeout.
- Giới hạn số lần truy vấn mỗi request.

### 20.2. Cost analysis

Một Query DSL có thể ước lượng cost từ AST và schema metadata. Đây chỉ là ước lượng; query planner của database mới có thông tin thực tế về statistics và execution plan.

### 20.3. Timeout và cancellation

Runtime cần hỗ trợ timeout ở driver hoặc database khi có thể. Hủy request ở tầng HTTP không nhất thiết dừng query đang chạy. Cần propagate cancellation và giải phóng connection đúng cách.

## 21. Error handling và logging

Lỗi database có thể chứa SQL text, tên bảng, column, constraint hoặc thông tin nội bộ. Không nên trả nguyên lỗi database cho người dùng cuối.

### 21.1. Thông báo cho người dùng

Trả message tổng quát và mã lỗi phù hợp:

~~~json
{
  "error": {
    "code": "QUERY_INVALID_FILTER",
    "message": "The requested filter is not supported."
  }
}
~~~

### 21.2. Log nội bộ

Log có thể chứa query template, parameter type, correlation ID và database error code. Cần tránh ghi raw secret, password, token hoặc dữ liệu cá nhân không cần thiết.

### 21.3. Parameter redaction

Ngay cả khi query template an toàn, parameter values có thể nhạy cảm. Có thể log:

~~~text
Query: SELECT id FROM users WHERE email = ?
Parameters: [String(<redacted>)]
~~~

Hoặc chỉ log kiểu, độ dài và hash đã được thiết kế cho mục đích chẩn đoán. Không nên dùng hash không có salt cho dữ liệu có miền giá trị nhỏ nếu có nguy cơ dò ngược.

### 21.4. Error detail không phải bằng chứng injection

Một lỗi cú pháp database có thể xuất hiện do bug nội bộ hoặc input không hợp lệ. Không nên tiết lộ stack trace, raw query hoặc schema details qua response công khai.

## 22. Kiểm thử injection cho Query DSL

Kiểm thử cần chứng minh rằng dữ liệu đầu vào không thay đổi cấu trúc truy vấn và những lựa chọn cấu trúc động bị giới hạn.

### 22.1. Unit test parameterization

Với một query builder, kiểm tra:

- SQL template có placeholder.
- Parameter values được lưu riêng.
- Giá trị không xuất hiện trong query text.
- Thứ tự và kiểu parameter đúng.

Ví dụ kỳ vọng:

~~~text
Input value: a string containing quote characters
Query text: SELECT id FROM users WHERE email = ?
Parameters: [the original input value]
~~~

### 22.2. Test với input có ký tự đặc biệt

Thử các đầu vào chứa:

- Dấu nháy đơn và kép.
- Dấu gạch chéo ngược.
- Dấu chấm phẩy.
- Comment marker.
- Dấu ngoặc.
- Unicode và combining characters.
- Chuỗi rỗng và chuỗi rất dài.

Mục tiêu là xác nhận chúng vẫn là parameter values và không làm đổi AST hoặc query template.

### 22.3. Test identifier allowlist

- Tên hợp lệ được ánh xạ đúng column.
- Tên không tồn tại bị từ chối.
- Column nhạy cảm không được expose.
- Case sensitivity theo hợp đồng được áp dụng.
- Không có fallback sang raw identifier.

### 22.4. Test NoSQL structure

Gửi object thay cho scalar, array lồng nhau hoặc key bắt đầu bằng ký hiệu operator. Xác nhận API từ chối cấu trúc không phù hợp và backend chỉ tạo filter từ schema đã kiểm soát.

### 22.5. Integration test với database thật

Test trên database engine được hỗ trợ để xác nhận driver binding, placeholder syntax, identifier quoting và transaction behavior. Mock có thể không phản ánh chính xác cách driver hoặc database parse query.

### 22.6. Regression tests

Mỗi lỗi injection hoặc bypass đã phát hiện nên có test tái hiện. Test cần xác nhận cả kết quả bảo mật và hành vi nghiệp vụ mong muốn.

## 23. Property-based testing và fuzzing

Property-based testing sinh nhiều giá trị đầu vào để kiểm tra một tính chất tổng quát.

Ví dụ property:

> Với mọi chuỗi email đầu vào, cấu trúc AST và query template của truy vấn tìm user không đổi; chỉ danh sách parameter thay đổi.

Một test có thể:

1. Sinh chuỗi ngẫu nhiên gồm Unicode và ký tự đặc biệt.
2. Tạo query bằng DSL.
3. Serialize sang target query.
4. Kiểm tra query text có template ổn định.
5. Kiểm tra giá trị đầu vào nằm trong parameter list.
6. Thực thi trên database test và xác nhận chỉ trả kết quả theo equality.

Fuzzing parser và query builder có thể tìm lỗi crash, xử lý sai delimiter hoặc trạng thái AST không hợp lệ. Fuzzing không thay thế review thiết kế parameterization và authorization.

## 24. Static analysis và taint analysis

Static analysis có thể tìm các đường đi từ nguồn dữ liệu không tin cậy tới sink truy vấn.

### 24.1. Sources

Nguồn dữ liệu có thể gồm:

- HTTP request parameters.
- JSON body.
- Message queue payload.
- File upload hoặc file cấu hình.
- Cookie hoặc header.
- Dữ liệu database đã lưu trước đó.
- Input từ plugin hoặc extension.

### 24.2. Sinks

Sink là nơi truy vấn được thực thi hoặc được parse:

- Database query API.
- Raw SQL execution.
- NoSQL collection filter.
- GraphQL document parser.
- Search engine query endpoint.
- Stored procedure dynamic execution.

### 24.3. Safe flow

Static analyzer có thể nhận diện:

- Parameter binding API.
- Query AST builder.
- Allowlist identifier mapping.
- Unsafe raw query function.
- Sanitizer chuyên biệt theo context.

Không nên đánh dấu một hàm generic tên sanitize là an toàn cho mọi sink. Sanitizer phải gắn với grammar và context cụ thể.

### 24.4. False positive và false negative

Phân tích tĩnh có thể không hiểu query được xây qua nhiều module hoặc reflection. Nó cũng có thể cảnh báo một chuỗi đã được kiểm soát hợp lệ. Cần kết hợp rule rõ, type metadata, test và review.

## 25. Thiết kế API Query DSL an toàn

API tốt nên làm cho cách dùng an toàn trở thành con đường mặc định.

### 25.1. Ưu tiên API có cấu trúc

Ví dụ:

~~~typescript
where(eq(users.email, param(email)))
~~~

thay vì:

~~~typescript
where("email = '" + email + "'")
~~~

### 25.2. Phân biệt kiểu dữ liệu

Không dùng String cho mọi thành phần. Có thể có các kiểu:

- TableRef.
- ColumnRef<T>.
- Parameter<T>.
- Predicate.
- OrderExpression.
- QueryNode.
- TrustedSqlFragment.

Kiểu giúp API xác định vị trí nào được nhận identifier, expression hoặc parameter.

### 25.3. Không expose raw query ở API thông thường

Raw query nên là API riêng, có tên và quyền sử dụng rõ. Có thể yêu cầu parameter object và kiểm tra nội dung tại thời điểm build.

### 25.4. Tạo query từ enum hoặc schema

Nếu người dùng chọn sort field hoặc filter field, map lựa chọn từ enum/schema sang ColumnRef. Không nhận identifier text tùy ý.

### 25.5. Immutable query builder

Query builder bất biến giúp mỗi thao tác tạo node mới thay vì thay đổi query dùng chung. Điều này giảm lỗi khi nhiều request tái sử dụng builder hoặc query template.

### 25.6. Backend contract

Mỗi backend cần định nghĩa:

- Cách bind từng kiểu dữ liệu.
- Placeholder syntax.
- Collection parameter strategy.
- Identifier quoting.
- Hỗ trợ transaction và cancellation.
- Cách báo lỗi.
- Giới hạn query và parameter.

Không nên giả định cùng một AST được serialize giống hệt cho mọi database.

## 26. Thiết kế compiler và backend cho injection safety

Một Query DSL compiler nên giữ phân tách dữ liệu/cú pháp xuyên suốt pipeline.

~~~mermaid
flowchart TD
    A[DSL source or API call] --> B[Parser / typed builder]
    B --> C[Query AST]
    C --> D[Name and type resolution]
    D --> E[Policy validation]
    E --> F[Target backend]
    F --> G[Query template]
    F --> H[Parameter collection]
    G --> I[Driver prepared execution]
    H --> I
    I --> J[Database]
~~~

### 26.1. Parser

Parser phải tạo node riêng cho literal, identifier và reference. Không nên mất thông tin về nguồn dữ liệu khi chuyển token thành AST.

### 26.2. Name resolution

Tên bảng và cột cần được resolve tới schema symbol. Backend dùng symbol đã resolve thay vì chuỗi client gửi.

### 26.3. Type checking

Kiểm tra kiểu expression và parameter. Nếu column là Integer, không nhận một object tùy ý chỉ vì runtime có thể serialize object đó thành JSON.

### 26.4. Policy validation

Kiểm tra bảng/cột được phép, operator được phép, giới hạn query và quyền theo context.

### 26.5. Code generation

Sinh query template và parameter list riêng. Không thay placeholder bằng cách nối chuỗi. Nếu backend không hỗ trợ một cấu trúc, báo lỗi thay vì fallback sang raw string không an toàn.

### 26.6. Driver execution

Gọi API binding chính thức của driver. Không tự format parameter rồi gọi API execute chuỗi thuần.

## 27. Các tình huống đặc biệt cần xử lý

### 27.1. Dynamic table theo tenant

Nếu mỗi tenant có table hoặc schema riêng, resolve tenant từ authenticated context và ánh xạ sang TableRef đã kiểm soát. Không lấy tên bảng từ query parameter.

### 27.2. JSON path

Một số database cho phép truy vấn field trong JSON bằng path expression. Nếu path được build động, cần API chuyên dụng hoặc allowlist segment. Parameter value không nhất thiết bind được ở vị trí JSON path.

### 27.3. Full-text search

Search engine có grammar riêng như phrase, prefix, field selector hoặc boolean operator. Nếu sản phẩm chỉ cần tìm từ khóa, nên dùng API query object hoặc literal search mode thay vì cho người dùng đưa query syntax tùy ý.

### 27.4. Regex

Regex có thể chứa cú pháp phức tạp và gây ReDoS nếu pattern tốn thời gian. Parameter binding bảo vệ query grammar, nhưng không bảo đảm pattern an toàn hoặc rẻ. Cần giới hạn độ dài, timeout và engine phù hợp.

### 27.5. Database function

Nếu Query DSL cho phép function call, chỉ expose function được duyệt. Function có thể đọc dữ liệu nhạy cảm, truy cập filesystem hoặc tạo side effect tùy database và quyền.

### 27.6. Multi-statement execution

Không nên cho query builder thông thường thực thi nhiều statement trong một raw string. Tắt multi-statement nếu driver hoặc môi trường không cần nó, và dùng API riêng có kiểm soát cho migration hoặc batch.

## 28. Quy trình xử lý một truy vấn an toàn

Một request tìm kiếm có thể đi qua các bước:

1. Xác thực người gọi và xác định tenant từ context đáng tin cậy.
2. Validate cấu trúc request theo schema API.
3. Chuyển field và operator động qua allowlist.
4. Chuẩn hóa kiểu dữ liệu và kiểm tra range.
5. Tạo AST hoặc query builder node.
6. Thêm predicate authorization bắt buộc.
7. Áp dụng pagination, timeout và query budget.
8. Type-check và validate query model.
9. Backend sinh template và parameter list.
10. Driver thực thi prepared statement hoặc API binding.
11. Kiểm tra và giới hạn kết quả trả về.
12. Log metadata an toàn và correlation ID.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant U as Caller
    participant A as Application
    participant Q as Query DSL
    participant D as Database Driver
    participant DB as Database
    U->>A: Search request
    A->>A: Authenticate and validate input
    A->>Q: Typed filters and trusted context
    Q->>Q: Build AST and validate policy
    Q->>D: Query template + parameters
    D->>DB: Prepared execution
    DB-->>D: Rows
    D-->>A: Typed result
    A-->>U: Authorized response
~~~

## 29. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nối input vào SQL string | Input có thể thay đổi grammar | Parameter binding |
| Nghĩ ORM luôn an toàn | Raw query hoặc string condition vẫn có thể injection | Dùng API có cấu trúc và review raw escape hatch |
| Bind identifier như value | Query không chọn đúng column hoặc dùng workaround nguy hiểm | Allowlist và typed identifier |
| Dùng blocklist keyword | Bỏ sót cú pháp hoặc encoding khác | Allowlist cấu trúc được phép |
| Escape bằng hàm tự viết | Sai theo dialect hoặc context | Dùng driver binding và API quote chuyên dụng |
| Nhận NoSQL filter object tùy ý | Client có thể chèn operator | Xây filter từ schema và enum operator |
| Cho raw query trong mọi module | Mất kiểm soát AST và parameterization | Giới hạn API raw và audit |
| Tin dữ liệu đã lưu là an toàn | Second-order injection | Bind dữ liệu tại mọi query context |
| Quên tenant predicate | Đọc dữ liệu tenant khác dù query không injection | Authorization layer và RLS |
| Không giới hạn query cost | Query hợp lệ có thể làm cạn tài nguyên | Query budget, timeout và pagination |
| Log parameter đầy đủ | Lộ PII hoặc secret | Redaction và log metadata |
| Chỉ test bằng mock | Bỏ sót khác biệt driver/database | Integration test với engine thật |
| Dùng sanitizer tổng quát | Escape sai context | Sanitizer chuyên biệt hoặc parameter binding |
| Fallback sang raw string khi backend thiếu tính năng | Có thể tạo lỗ hổng ở backend phụ | Báo unsupported feature hoặc triển khai AST node an toàn |

## 30. Checklist thiết kế Query DSL an toàn

Khi thiết kế hoặc tích hợp Query DSL, hãy xác nhận:

- Giá trị động luôn đi qua parameter binding.
- AST phân biệt literal, parameter, identifier và expression.
- Identifier động được resolve từ schema hoặc allowlist.
- Operator động được ánh xạ từ enum hoặc builder cố định.
- API thông thường không nhận raw query text.
- Raw escape hatch có phạm vi và contract rõ.
- NoSQL filter được xây từ schema, không chuyển tiếp object tùy ý.
- Query áp dụng authorization và tenant context đáng tin cậy.
- Pagination, list size, query depth và timeout có giới hạn.
- Secret và dữ liệu cá nhân được redact khỏi log.
- Mọi backend đều dùng driver binding đúng cách.
- Lỗi backend không làm lộ query hoặc schema nhạy cảm.
- Có unit, integration, property-based và regression tests.
- Có policy kiểm tra raw query và luồng dữ liệu không tin cậy.

Checklist này hỗ trợ review thiết kế. Kết quả an toàn vẫn cần được xác nhận bằng implementation, driver behavior, quyền database và kiểm thử thực tế.

## 31. Quy trình triển khai an toàn trước injection

Một kế hoạch triển khai có thể chia thành các bước:

1. **Liệt kê nguồn dữ liệu không tin cậy:** request, message, file, stored value và plugin.
2. **Xác định query sinks:** SQL, NoSQL, GraphQL, search engine hoặc API truy vấn khác.
3. **Thiết kế query model:** AST có kiểu, tách parameter khỏi syntax.
4. **Chuẩn hóa API:** dùng builder và schema-generated symbols cho query thông thường.
5. **Thiết kế identifier policy:** allowlist table, column, sort key và operator.
6. **Triển khai backend binding:** dùng API chính thức của từng driver.
7. **Giới hạn raw query:** yêu cầu review, audit và parameter list.
8. **Bổ sung authorization:** tenant scope, row-level policy và least privilege.
9. **Giới hạn tài nguyên:** pagination, timeout, depth và query budget.
10. **Thiết kế diagnostics/logging:** không lộ parameter nhạy cảm hoặc chi tiết nội bộ.
11. **Viết kiểm thử:** input đặc biệt, identifier bypass, NoSQL operator, second-order và multi-backend.
12. **Tích hợp CI/static analysis:** tìm raw query và luồng tainted data.
13. **Theo dõi vận hành:** query latency, lỗi, timeout và hành vi truy cập bất thường.

Khi chuyển một hệ thống cũ sang Query DSL an toàn, nên ưu tiên các query nhận input trực tiếp từ người dùng, query có raw string và query chạy bằng quyền cao. Sau đó chuẩn hóa từng nhóm API và giữ regression test cho mỗi lỗ hổng đã xử lý.

## 32. Ví dụ tổng hợp: API tìm kiếm đơn hàng

Giả sử API cho phép lọc đơn hàng theo trạng thái, ngày tạo và sắp xếp theo một số trường.

Request:

~~~json
{
  "status": "PAID",
  "createdAfter": "2026-01-01T00:00:00Z",
  "sortBy": "createdAt",
  "direction": "desc",
  "pageSize": 25
}
~~~

### 32.1. Validate request

- status phải thuộc enum OrderStatus.
- createdAfter phải là timestamp hợp lệ.
- sortBy chỉ nhận id, createdAt hoặc total.
- direction chỉ nhận asc hoặc desc.
- pageSize nằm trong khoảng 1 đến 100.

### 32.2. Build query

~~~typescript
const sortColumns = {
  id: orders.id,
  createdAt: orders.createdAt,
  total: orders.total
};

const sortColumn = sortColumns[input.sortBy];
if (!sortColumn) {
  throw new InvalidSortFieldError();
}

const filters = [
  eq(orders.tenantId, param(auth.tenantId))
];

if (input.status !== undefined) {
  filters.push(
    eq(orders.status, param(parseOrderStatus(input.status)))
  );
}

if (input.createdAfter !== undefined) {
  filters.push(
    gte(orders.createdAt, param(parseTimestamp(input.createdAfter)))
  );
}

const sort =
  input.direction === "desc" ? desc(sortColumn) : asc(sortColumn);

const query = select({
    id: orders.id,
    status: orders.status,
    total: orders.total,
    createdAt: orders.createdAt
  })
  .from(orders)
  .where(and(...filters))
  .orderBy(sort)
  .limit(param(validatePageSize(input.pageSize)));
~~~

Ví dụ này dùng builder giả định để minh họa:

- tenantId đến từ context đã xác thực.
- status và createdAfter là parameter values.
- sortBy chỉ chọn column từ allowlist.
- direction chỉ chọn hai builder asc hoặc desc.
- pageSize được kiểm tra range và bind theo khả năng backend.

### 32.3. Backend execution

Backend có thể sinh template:

~~~sql
SELECT id, status, total, created_at
FROM orders
WHERE tenant_id = ?
  AND status = ?
  AND created_at >= ?
ORDER BY created_at DESC
LIMIT ?
~~~

Danh sách parameter được gửi riêng theo thứ tự tương ứng. SQL template không chứa dữ liệu request.

### 32.4. Authorization và kết quả

Tenant predicate là điều kiện bắt buộc do ứng dụng thêm từ authenticated context. Database account chỉ có quyền cần thiết. Kết quả trả về được giới hạn theo page size và chỉ chứa field caller được phép xem.

## 33. Tiêu chí của một Query DSL an toàn

Một Query DSL an toàn giữ được ranh giới rõ ràng giữa cấu trúc truy vấn và dữ liệu. API thông thường biểu diễn query bằng node có kiểu; backend sinh placeholder và bind parameter qua driver. Những phần cấu trúc động như table, column, operator và sort key được chọn từ schema hoặc allowlist. Raw query được giới hạn và kiểm soát.

An toàn trước injection cũng cần được đặt trong bức tranh bảo mật rộng hơn. Query phải áp dụng authorization, tenant isolation và least privilege; đồng thời giới hạn tài nguyên, bảo vệ log và xử lý lỗi phù hợp. Một query không có injection vẫn có thể truy cập sai dữ liệu hoặc gây quá tải nếu thiếu những lớp kiểm soát này.

Các câu hỏi quan trọng:

- Giá trị người dùng có bao giờ được nối trực tiếp vào query text không?
- Query DSL có AST hoặc builder giữ cấu trúc truy vấn không?
- Parameter được truyền riêng qua driver API nào?
- Identifier và operator động được chọn từ đâu?
- Raw query có được giới hạn, audit và kiểm thử không?
- NoSQL hoặc GraphQL input có được xây từ schema thay vì chuyển tiếp nguyên object không?
- Dữ liệu đã lưu có được xem là không tin cậy khi dùng trong query mới không?
- Tenant và authorization predicate đến từ context đã xác thực không?
- Query có giới hạn pagination, độ sâu, thời gian và số lượng phần tử không?
- Parameter nhạy cảm có được redact khỏi log và lỗi không?
- Mọi backend có giữ cùng hợp đồng an toàn không?
- Test có xác nhận query template không đổi khi giá trị input thay đổi không?

An toàn trước injection không phải một thao tác escape đơn lẻ. Đó là thuộc tính của toàn bộ thiết kế Query DSL: cấu trúc truy vấn được kiểm soát, dữ liệu được bind riêng, lựa chọn động được giới hạn, quyền truy cập được enforce và hành vi được kiểm thử trên backend thực tế. Khi những nguyên tắc này được tích hợp ngay từ API và compiler, Query DSL có thể cung cấp cách truy vấn linh hoạt mà vẫn giữ được ranh giới an toàn giữa mã và dữ liệu.
