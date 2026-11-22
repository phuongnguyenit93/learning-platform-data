# DSL nội bộ và DSL bên ngoài

## 1. Hai cách xây dựng một ngôn ngữ chuyên biệt

Ngôn ngữ chuyên biệt miền (*Domain-Specific Language — DSL*) là ngôn ngữ được thiết kế để diễn đạt vấn đề trong một lĩnh vực cụ thể. SQL tập trung vào truy vấn dữ liệu, biểu thức chính quy mô tả mẫu văn bản, còn CSS mô tả cách trình bày giao diện. DSL thường cung cấp một bộ khái niệm và quy tắc nhỏ hơn ngôn ngữ lập trình đa dụng, nhờ đó người dùng có thể diễn đạt công việc của lĩnh vực đó ngắn gọn và rõ ràng.

Có hai cách phổ biến để tạo ra DSL:

- **DSL nội bộ (*internal DSL*)** được xây dựng bên trong cú pháp của một ngôn ngữ lập trình đa dụng, gọi là ngôn ngữ chủ (*host language*). DSL tận dụng cú pháp, kiểu dữ liệu, hàm và công cụ của ngôn ngữ chủ.
- **DSL bên ngoài (*external DSL*)** có cú pháp và ngữ pháp riêng. Nó được phân tích và xử lý bởi một parser, interpreter, compiler hoặc một thành phần chuyên dụng của ứng dụng.

Cả hai đều hướng tới một miền nghiệp vụ. Điểm phân biệt chính là cách người viết biểu đạt DSL và cách hệ thống hiểu phần biểu đạt đó: DSL nội bộ dựa vào bộ phân tích cú pháp của ngôn ngữ chủ; DSL bên ngoài có bộ quy tắc cú pháp riêng.

## 2. DSL nội bộ

### 2.1. Khái niệm và cách hoạt động

DSL nội bộ là một thư viện hoặc API được thiết kế sao cho mã sử dụng thư viện trông giống một ngôn ngữ nhỏ dành riêng cho một miền. Mã đó vẫn là chương trình hợp lệ theo cú pháp của ngôn ngữ chủ. Trình biên dịch hoặc trình thông dịch của ngôn ngữ chủ phân tích cú pháp trước; các hàm, lớp, kiểu dữ liệu và toán tử do thư viện cung cấp quyết định ý nghĩa chuyên biệt.

Ví dụ, một nhóm có thể xây dựng DSL bằng Kotlin để mô tả truy vấn:

```kotlin
val adults = query<Person> {
    where { age >= 18 }
    orderBy { lastName ascending }
    limit(20)
}
```

Đoạn mã trên là ví dụ minh họa cho một API DSL giả định. `query`, `where`, `orderBy`, `ascending` và `limit` là các thành phần do thư viện định nghĩa. Cú pháp khối lambda và lời gọi hàm vẫn tuân theo Kotlin. Thư viện có thể chuyển các lời gọi đó thành một cấu trúc truy vấn rồi thực thi trên bộ sưu tập trong bộ nhớ hoặc chuyển thành câu lệnh cho cơ sở dữ liệu.

Một cách khác là dùng chuỗi lời gọi hàm (*fluent interface*):

```python
pipeline = (
    workflow("nightly")
    .when_(cron("0 2 * * *"))
    .run("backup")
    .notify("ops")
)
```

Ví dụ Python này cũng là DSL nội bộ: các lời gọi hàm và dấu chấm nối tiếp được Python phân tích theo cú pháp thông thường, còn thư viện định nghĩa ý nghĩa của `workflow`, `when_`, `run` và `notify`.

### 2.2. Những kỹ thuật thường dùng

Các kỹ thuật sau thường được kết hợp để tạo cảm giác như đang viết một ngôn ngữ riêng:

1. **Fluent interface:** trả về đối tượng hiện tại hoặc một đối tượng liên quan để nối nhiều lời gọi hàm thành một biểu thức có thứ tự.
2. **Builder pattern:** dùng một đối tượng builder để thu thập cấu hình theo từng bước, sau đó tạo ra cấu hình hoặc mô hình hoàn chỉnh.
3. **Lambda và closure:** cho phép người dùng truyền một khối mã ngắn vào hàm của DSL. Ngôn ngữ chủ vẫn chịu trách nhiệm phân tích khối mã đó.
4. **Kiểu dữ liệu và API có kiểu:** biểu diễn khái niệm miền bằng class, enum, generic và kiểu chuyên biệt để giới hạn những thao tác hợp lệ.
5. **Nạp chồng toán tử hoặc cú pháp tiện ích:** ở ngôn ngữ hỗ trợ, toán tử có thể được định nghĩa lại để biểu thức gần với ký hiệu của miền. Cần dùng có chừng mực để tránh làm mã khó hiểu.

Một DSL nội bộ tốt thường thiết kế API quanh các khái niệm của miền, thay vì chỉ đổi tên các hàm kỹ thuật. Chẳng hạn, một DSL định nghĩa quy tắc giá nên có các khái niệm như `customer`, `order`, `condition` và `discount`, thay vì buộc người dùng thao tác trực tiếp với những chi tiết triển khai như map lồng nhau hoặc chuỗi cấu hình.

### 2.3. Ưu điểm

- **Tận dụng hệ sinh thái sẵn có:** có thể dùng IDE, tự động hoàn thành, điều hướng mã, debugger, formatter, trình biên dịch và công cụ kiểm tra của ngôn ngữ chủ.
- **Tích hợp thuận tiện:** DSL có thể gọi trực tiếp các hàm và thư viện hiện có, chia sẻ kiểu dữ liệu với phần còn lại của ứng dụng và tham gia vào cùng quy trình build.
- **Có thể kiểm tra kiểu sớm:** nếu API được thiết kế tốt, nhiều lỗi như truyền sai kiểu hoặc gọi thao tác không hợp lệ có thể được phát hiện khi biên dịch.
- **Chi phí triển khai ban đầu thường thấp hơn:** nhóm phát triển chủ yếu thiết kế API và mô hình thực thi, không nhất thiết phải tự viết lexer và parser.
- **Dễ tiếp cận với lập trình viên quen ngôn ngữ chủ:** người dùng không cần học thêm một cú pháp hoàn toàn mới.

### 2.4. Hạn chế

- **Bị giới hạn bởi cú pháp ngôn ngữ chủ:** DSL khó có thể tạo ra ký hiệu hoàn toàn tự do. Một biểu thức tự nhiên trong miền có thể phải viết thành lời gọi hàm hoặc cấu trúc lồng nhau.
- **Phụ thuộc vào ngôn ngữ chủ:** người dùng phải biết ít nhất những quy tắc cơ bản của ngôn ngữ đó. Việc đổi ngôn ngữ chủ có thể khiến DSL phải thiết kế lại.
- **Thông báo lỗi có thể chưa đúng ngữ cảnh:** lỗi cú pháp hoặc kiểu đôi khi xuất hiện dưới dạng lỗi của ngôn ngữ chủ, khó giải thích bằng thuật ngữ nghiệp vụ.
- **Ranh giới giữa DSL và mã thông thường có thể mờ:** nếu API cho phép gọi tùy ý mã của ngôn ngữ chủ, việc đọc, kiểm tra hoặc giới hạn hành vi của DSL sẽ khó hơn.
- **Không tự động an toàn:** thực thi lambda hoặc mã do người dùng cung cấp có thể cho phép truy cập tài nguyên ngoài dự kiến. Cần xác định rõ ai được viết mã và mã chạy với quyền nào.

DSL nội bộ phù hợp khi người viết chủ yếu là lập trình viên, ứng dụng đã dùng một ngôn ngữ chủ ổn định và khả năng tích hợp với mã hiện có quan trọng hơn việc có cú pháp hoàn toàn độc lập.

## 3. DSL bên ngoài

### 3.1. Khái niệm và cách hoạt động

DSL bên ngoài có cú pháp được định nghĩa riêng, độc lập với cú pháp của một ngôn ngữ lập trình đa dụng. Người dùng viết nội dung theo ngôn ngữ đó; một thành phần chuyên dụng đọc nội dung, kiểm tra cấu trúc và xác định ý nghĩa.

Ví dụ, một hệ thống khuyến mãi có thể định nghĩa ngôn ngữ quy tắc như sau:

```text
rule "vip-discount" {
    when customer.tier == "GOLD" and order.total >= 10000000
    then discount.percent = 15
}
```

Đây là cú pháp giả định của một DSL bên ngoài. Nó không phải cú pháp Kotlin, Python hay SQL. Ứng dụng sở hữu DSL phải định nghĩa những từ khóa như `rule`, `when`, `and`, `then`, cấu trúc khối, kiểu giá trị và ý nghĩa của từng biểu thức. Sau khi đọc quy tắc, ứng dụng có thể kiểm tra điều kiện rồi áp dụng mức giảm giá tương ứng.

Các ngôn ngữ quen thuộc có tính chất DSL bên ngoài gồm:

- **SQL:** mô tả truy vấn và thao tác dữ liệu quan hệ.
- **Regular expressions:** mô tả mẫu cần tìm trong văn bản.
- **CSS:** mô tả quy tắc trình bày tài liệu HTML hoặc XML.
- **GraphQL:** mô tả cấu trúc dữ liệu mà client yêu cầu từ một API GraphQL.
- **HCL trong Terraform:** mô tả cấu hình hạ tầng theo các khái niệm của Terraform.

Các ví dụ này có phạm vi và mức độ phức tạp khác nhau, nhưng đều có cú pháp được xử lý theo quy tắc riêng của ngôn ngữ đó.

### 3.2. Các bước xử lý một DSL bên ngoài

Một hệ thống DSL bên ngoài thường có các giai đoạn sau. Những DSL đơn giản có thể gộp một số giai đoạn, còn ngôn ngữ lớn có thể bổ sung nhiều bước khác.

```text
Văn bản nguồn
    |
    v
Lexer / bộ phân tích từ vựng
    |
    v
Parser / bộ phân tích cú pháp
    |
    v
AST / cây cú pháp trừu tượng
    |
    v
Kiểm tra ngữ nghĩa và kiểu
    |
    v
Interpreter, compiler hoặc bộ sinh mã
    |
    v
Kết quả thực thi
```

1. **Phân tích từ vựng (*lexing*):** tách văn bản thành các token như từ khóa, tên biến, số, chuỗi và dấu phân cách.
2. **Phân tích cú pháp (*parsing*):** kiểm tra thứ tự token có tuân theo ngữ pháp hay không, rồi xây dựng cấu trúc cú pháp.
3. **Tạo AST:** biểu diễn chương trình dưới dạng cây gồm các nút có ý nghĩa, chẳng hạn `Rule`, `Condition`, `And`, `Comparison` và `Discount`.
4. **Kiểm tra ngữ nghĩa:** xác minh những điều cú pháp đơn thuần không thể bảo đảm, ví dụ trường `customer.tier` có tồn tại không, phép so sánh có dùng kiểu tương thích không và mức giảm giá có nằm trong giới hạn cho phép không.
5. **Thực thi hoặc chuyển đổi:** interpreter duyệt AST để thực thi; compiler chuyển AST thành mã hoặc dạng trung gian khác; bộ sinh mã có thể chuyển DSL thành SQL, JSON hay cấu hình cho một hệ thống khác.

Tách các giai đoạn giúp hệ thống đưa ra lỗi cụ thể. Ví dụ, `when customer.tier =` có thể là lỗi cú pháp vì biểu thức chưa hoàn chỉnh; `customer.unknownField` có thể là lỗi ngữ nghĩa vì trường không tồn tại; còn mức giảm giá `150` có thể vi phạm quy tắc nghiệp vụ dù cú pháp và kiểu dữ liệu đều hợp lệ.

### 3.3. Ưu điểm

- **Tự do thiết kế cú pháp:** ngôn ngữ có thể dùng từ khóa, biểu thức và cấu trúc gần với cách chuyên gia miền diễn đạt công việc.
- **Tách biệt với ngôn ngữ triển khai:** người viết DSL không nhất thiết phải biết ngôn ngữ mà ứng dụng được xây dựng bằng đó.
- **Có thể giới hạn khả năng biểu đạt:** DSL chỉ cung cấp các thao tác được cho phép, giúp kiểm soát tốt hơn cấu hình hoặc quy tắc mà người dùng được quyền khai báo.
- **Dễ hỗ trợ nhiều nền tảng:** nếu ngữ nghĩa được định nghĩa rõ, nhiều ứng dụng hoặc ngôn ngữ lập trình có thể dùng chung định dạng DSL.
- **Có thể xây dựng trải nghiệm chuyên biệt:** hệ thống có thể cung cấp thông báo lỗi theo thuật ngữ miền, kiểm tra trước khi chạy, tài liệu cú pháp và công cụ biên tập riêng.

### 3.4. Hạn chế

- **Chi phí xây dựng và bảo trì cao hơn:** cần định nghĩa ngữ pháp, parser, mô hình dữ liệu, kiểm tra ngữ nghĩa và cơ chế thực thi hoặc chuyển đổi.
- **Phải đầu tư công cụ:** tự động hoàn thành, định dạng, điều hướng, gỡ lỗi và tô màu cú pháp có thể cần plugin IDE hoặc language server riêng.
- **Cần quản lý phiên bản ngôn ngữ:** thay đổi cú pháp hoặc ngữ nghĩa có thể làm hỏng các tệp DSL cũ. Hệ thống cần quy tắc tương thích và cách nâng cấp.
- **Tăng thêm một ngôn ngữ cần học:** người dùng phải hiểu cú pháp, kiểu dữ liệu, giới hạn và quy tắc lỗi của DSL.
- **Vẫn cần bảo đảm an toàn:** parser đúng cú pháp không đồng nghĩa nội dung an toàn. Bộ thực thi phải giới hạn quyền, tài nguyên và các thao tác được phép.

DSL bên ngoài phù hợp khi cần một định dạng độc lập, người viết không nhất thiết là lập trình viên của ứng dụng, cú pháp của ngôn ngữ chủ không diễn đạt tốt miền nghiệp vụ hoặc nhiều hệ thống cần dùng chung một ngôn ngữ.

## 4. So sánh DSL nội bộ và DSL bên ngoài

| Tiêu chí | DSL nội bộ | DSL bên ngoài |
|---|---|---|
| Cú pháp | Tuân theo ngôn ngữ chủ, được định hình qua API và thư viện | Có ngữ pháp riêng |
| Phân tích cú pháp | Dùng compiler/parser của ngôn ngữ chủ | Dùng parser hoặc công cụ chuyên biệt |
| Cách triển khai | Thường là hàm, lớp, builder, lambda và kiểu dữ liệu | Thường gồm lexer/parser, AST, kiểm tra ngữ nghĩa và bộ thực thi hoặc sinh mã |
| Công cụ phát triển | Tận dụng IDE và công cụ của ngôn ngữ chủ | Có thể cần công cụ riêng hoặc tích hợp thêm vào IDE |
| Người dùng thường gặp | Lập trình viên dùng ngôn ngữ chủ | Chuyên gia miền, người viết cấu hình hoặc lập trình viên ở nhiều nền tảng |
| Tự do về cú pháp | Bị giới hạn bởi ngôn ngữ chủ | Cao hơn vì có thể định nghĩa cú pháp riêng |
| Tích hợp với ứng dụng | Thường trực tiếp và thuận tiện | Cần lớp chuyển đổi hoặc thực thi DSL |
| Chi phí ban đầu | Thường thấp hơn nếu ngôn ngữ chủ có thư viện phù hợp | Thường cao hơn do phải xây dựng hạ tầng ngôn ngữ |
| Rủi ro thiết kế | API khó đọc, phụ thuộc ngôn ngữ chủ, quyền thực thi quá rộng | Ngữ pháp phức tạp, lỗi khó chẩn đoán, vấn đề tương thích phiên bản |

Không có loại nào luôn tốt hơn loại còn lại. Lựa chọn phụ thuộc vào người viết, môi trường triển khai, mức độ tự do cú pháp cần thiết và chi phí duy trì ngôn ngữ trong thời gian dài.

## 5. Cùng một miền, hai cách biểu đạt

Giả sử cần lấy tên những người từ 18 tuổi trở lên. Với một DSL truy vấn nội bộ được xây dựng bằng Kotlin, mã có thể trông như sau:

```kotlin
val names = query<Person> {
    where { age >= 18 }
    select { name }
}
```

Với DSL SQL bên ngoài, cùng ý định có thể được biểu đạt như sau:

```sql
SELECT name
FROM Person
WHERE age >= 18;
```

Hai đoạn mã diễn đạt một thao tác tương tự nhưng đi qua hai cơ chế khác nhau. Đoạn Kotlin được compiler Kotlin phân tích; các hàm trong thư viện truy vấn xây dựng ý nghĩa của DSL nội bộ. Đoạn SQL được parser SQL của hệ quản trị cơ sở dữ liệu hoặc công cụ SQL phân tích theo ngữ pháp SQL.

Ví dụ cũng cho thấy việc một đoạn DSL xuất hiện bên trong mã nguồn của ứng dụng không làm nó trở thành DSL nội bộ. Nếu chương trình Java chứa một chuỗi SQL rồi gửi chuỗi đó đến cơ sở dữ liệu, SQL vẫn là DSL bên ngoài: cú pháp SQL có parser và ngữ nghĩa riêng, dù chuỗi được đặt trong tệp Java.

## 6. Trường hợp kết hợp và ranh giới phân loại

Trong thực tế, một sản phẩm có thể dùng cả hai loại DSL. Chẳng hạn, ứng dụng có một DSL bên ngoài để người vận hành khai báo quy tắc trong tệp cấu hình. Ứng dụng đọc tệp, phân tích thành AST, kiểm tra quy tắc rồi chuyển AST thành các đối tượng miền. Phần mã ứng dụng có thể cung cấp thêm một DSL nội bộ để lập trình viên tạo cùng loại quy tắc trực tiếp bằng ngôn ngữ chủ.

Một số điểm cần phân biệt:

- **Định dạng dữ liệu không tự động là DSL.** JSON và YAML chủ yếu định nghĩa cách biểu diễn dữ liệu. Một tệp YAML chỉ trở thành cách sử dụng DSL khi ứng dụng gán cho cấu trúc và các trường của nó một ngữ nghĩa chuyên biệt, ví dụ mô tả pipeline build hoặc hạ tầng.
- **Vị trí đặt văn bản không quyết định loại DSL.** SQL nằm trong chuỗi của Java vẫn là SQL bên ngoài; ngược lại, một API Kotlin có thể tạo DSL nội bộ dù mã được viết trong một tệp cấu hình của dự án.
- **Ranh giới có thể mang tính phổ.** Một ngôn ngữ có cú pháp riêng rất nhỏ, được nhúng trong cú pháp ngôn ngữ chủ, đôi khi được mô tả là DSL nhúng. Khi phân loại, hãy xem parser nào chịu trách nhiệm hiểu cú pháp và ngữ nghĩa của biểu thức.
- **Tên gọi không quyết định bản chất.** Một thư viện có chữ “DSL” trong tên chưa chắc tạo ra DSL dễ đọc. Chất lượng còn phụ thuộc vào việc API có phản ánh đúng khái niệm miền và giới hạn thao tác hợp lý hay không.

## 7. Cách lựa chọn loại DSL cho một bài toán

Trước khi triển khai, hãy xác định ai sẽ viết DSL và họ cần biểu đạt điều gì.

**Nên cân nhắc DSL nội bộ khi:**

- Người viết chủ yếu là lập trình viên và đã quen với ngôn ngữ chủ.
- DSL cần gọi thường xuyên các kiểu dữ liệu, hàm và thư viện của ứng dụng.
- Muốn tận dụng compiler, IDE, debugger và quy trình build hiện có.
- Miền nghiệp vụ có thể biểu đạt rõ ràng bằng builder, lambda hoặc fluent API.
- Nhóm muốn thử nghiệm một API chuyên biệt trước khi đầu tư xây dựng ngôn ngữ độc lập.

**Nên cân nhắc DSL bên ngoài khi:**

- Người viết là chuyên gia miền hoặc người vận hành không cần viết chương trình bằng ngôn ngữ chủ.
- Cú pháp của ngôn ngữ chủ quá nặng hoặc không tự nhiên đối với miền nghiệp vụ.
- Cần dùng chung định dạng giữa các ứng dụng, ngôn ngữ lập trình hoặc nền tảng.
- Cần kiểm soát rõ những thao tác mà tài liệu DSL có thể yêu cầu hệ thống thực hiện.
- Có đủ nguồn lực để duy trì parser, kiểm tra ngữ nghĩa, tài liệu, công cụ và tương thích phiên bản.

Có thể bắt đầu bằng DSL nội bộ để kiểm chứng mô hình miền và các thao tác cần thiết. Nếu sau đó xuất hiện nhu cầu cho phép nhiều nhóm hoặc người dùng không lập trình khai báo cùng nội dung, nhóm có thể thiết kế DSL bên ngoài và chuyển cả hai cách biểu đạt về một mô hình miền chung. Đây là một lộ trình khả thi, nhưng không phải quy tắc bắt buộc: chi phí chuyển đổi cần được cân nhắc ngay từ đầu.

## 8. Những nguyên tắc thiết kế cần chú ý

Dù chọn loại nào, một DSL hữu ích cần có ngữ nghĩa rõ ràng và nhất quán.

1. **Bắt đầu từ mô hình miền:** xác định danh từ, hành động, điều kiện và giới hạn quan trọng của lĩnh vực trước khi chọn cú pháp.
2. **Giữ phạm vi vừa đủ:** chỉ đưa vào những khả năng phục vụ bài toán. Quá nhiều tính năng làm DSL khó học và khó kiểm soát.
3. **Làm rõ kiểu và giá trị hợp lệ:** quy định kiểu dữ liệu, giá trị mặc định, giới hạn số, đơn vị đo và cách xử lý giá trị thiếu.
4. **Thiết kế thông báo lỗi có ích:** chỉ ra vị trí, nguyên nhân và cách sửa. Với DSL nghiệp vụ, thông báo nên dùng thuật ngữ mà người viết hiểu.
5. **Tách phân tích khỏi thực thi khi cần:** mô hình trung gian như AST giúp kiểm tra, tối ưu, ghi log, xem trước và chuyển đổi mà không phải chạy ngay nội dung đầu vào.
6. **Quản lý quyền và tài nguyên:** xác định DSL có thể đọc dữ liệu nào, gọi dịch vụ nào, ghi tệp hay thay đổi trạng thái nào; đặt giới hạn thời gian và bộ nhớ khi thực thi nội dung không đáng tin cậy.
7. **Có chiến lược tương thích:** nếu DSL được lưu trong tệp và tồn tại lâu dài, cần cân nhắc phiên bản cú pháp, cách di trú và cách xử lý tài liệu cũ.
8. **Tài liệu hóa bằng ví dụ thực tế:** người dùng cần biết cú pháp, ngữ nghĩa, trường hợp hợp lệ, trường hợp lỗi và kết quả mong đợi.

## 9. Kết luận

DSL nội bộ tạo ra một ngôn ngữ nhỏ bằng API nằm trong ngôn ngữ lập trình chủ. Nó thường dễ tích hợp và tận dụng được công cụ sẵn có, nhưng phải chấp nhận giới hạn cú pháp và sự phụ thuộc vào ngôn ngữ chủ. DSL bên ngoài có ngữ pháp riêng, cho phép thiết kế cách diễn đạt sát với miền và tách người viết khỏi ngôn ngữ triển khai, nhưng đòi hỏi đầu tư vào parser, kiểm tra, công cụ và quản lý phiên bản.

Khi lựa chọn, hãy bắt đầu từ người sẽ viết DSL, mức độ tự do cú pháp cần có, yêu cầu tích hợp và khả năng bảo trì lâu dài. Mục tiêu cuối cùng là giúp người dùng diễn đạt đúng khái niệm của miền một cách dễ hiểu, có thể kiểm tra và an toàn khi thực thi.
