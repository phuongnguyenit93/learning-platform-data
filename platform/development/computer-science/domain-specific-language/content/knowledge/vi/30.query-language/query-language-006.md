# Sắp xếp và phân trang

Trong một DSL truy vấn (query DSL), người dùng thường cần chọn một tập bản ghi, sắp xếp chúng theo tiêu chí nghiệp vụ rồi lấy một phần kết quả để hiển thị hoặc xử lý. **Sắp xếp (ordering)** xác định thứ tự các dòng trong kết quả; **phân trang (pagination)** chia kết quả thành những phần nhỏ có thể truy xuất lần lượt. Hai chức năng này thường được dùng cùng nhau trong bảng dữ liệu, danh sách tìm kiếm, API và báo cáo.

Ví dụ, một truy vấn đơn hàng có thể lấy các đơn đang chờ xử lý, sắp xếp theo thời điểm tạo mới nhất rồi trả về 20 đơn mỗi trang:

```text
query pendingOrders {
    from Order
    where status == PENDING
    orderBy createdAt descending, id ascending
    page size 20
}
```

Để kết quả đúng và ổn định, DSL cần quy định rõ thứ tự ưu tiên của nhiều khóa sắp xếp, cách xử lý giá trị null, collation của chuỗi, tie-breaker, giới hạn kích thước trang và cách xác định vị trí tiếp theo. Khi truy vấn được chuyển thành SQL hoặc thực thi trên nhiều nguồn dữ liệu, compiler/runtime cũng phải giữ nguyên semantics đó.

## 1. Sắp xếp và phân trang là gì?

Sắp xếp biến một tập kết quả thành một dãy có thứ tự theo một hoặc nhiều biểu thức. Phân trang chọn một đoạn của dãy đó hoặc tiếp tục từ một vị trí đã biết.

Có thể mô hình hóa:

```text
filtered = filter(source, predicate)
ordered = sort(filtered, ordering)
page = slice(ordered, offset, limit)
```

Thứ tự khái niệm thường là lọc, sắp xếp rồi phân trang. Nếu phân trang trước khi sắp xếp, mỗi trang có thể chứa các bản ghi không theo thứ tự toàn cục.

### 1.1. Sắp xếp (ordering)

Sắp xếp quy định bản ghi nào đứng trước bản ghi nào. Một tiêu chí sắp xếp thường gồm:

- Biểu thức lấy giá trị dùng để so sánh, ví dụ `createdAt` hoặc `total`.
- Hướng sắp xếp: tăng dần (ascending) hoặc giảm dần (descending).
- Quy tắc cho giá trị null.
- Quy tắc so sánh chuỗi, số, ngày giờ hoặc kiểu miền.

### 1.2. Phân trang (pagination)

Phân trang giới hạn số bản ghi được trả về trong một lần truy vấn. Nó giúp giảm payload, thời gian truyền dữ liệu và lượng dữ liệu cần hiển thị hoặc xử lý ở client.

### 1.3. Vì sao hai chức năng phải được thiết kế cùng nhau?

Pagination chỉ có ý nghĩa khi thứ tự kết quả được xác định. Nếu dữ liệu không có thứ tự ổn định, cùng một trang có thể trả về các bản ghi khác nhau giữa hai lần gọi, gây trùng hoặc bỏ sót khi người dùng chuyển trang.

## 2. Thứ tự mặc định và tính xác định

Nhiều nguồn dữ liệu không bảo đảm thứ tự tự nhiên. Một database có thể trả các dòng theo thứ tự khác nhau tùy query plan, index, phân vùng hoặc lần chạy. Vì vậy, nếu DSL không khai báo `orderBy`, không nên giả định kết quả có thứ tự ổn định.

Ví dụ:

```text
query customers {
    from Customer
    page size 20
}
```

Truy vấn này giới hạn số dòng nhưng chưa xác định khách hàng nào nằm ở trang đầu. Nếu thứ tự quan trọng, DSL nên yêu cầu hoặc khuyến nghị `orderBy`.

### 2.1. Total order

Một thứ tự tổng (total order) có thể so sánh mọi cặp bản ghi và quyết định bản ghi nào đứng trước. Nếu sắp xếp theo một trường không duy nhất như `createdAt`, nhiều bản ghi có thể bằng nhau. Khi đó, thứ tự giữa chúng chưa được xác định.

Để có total order, thường thêm một khóa duy nhất làm tie-breaker:

```text
orderBy createdAt descending, id ascending
```

`createdAt` quyết định thứ tự chính; nếu hai bản ghi cùng thời điểm, `id` quyết định thứ tự phụ. Điều này đặc biệt quan trọng với pagination.

### 2.2. Stable sort

Stable sort giữ nguyên thứ tự tương đối của các phần tử có khóa so sánh bằng nhau. Tính ổn định này hữu ích khi sắp xếp một tập đã có thứ tự trước đó, nhưng không thay thế tie-breaker nếu nguồn ban đầu không có thứ tự được bảo đảm.

### 2.3. Deterministic ordering

Ordering deterministic nghĩa là cùng tập dữ liệu và cùng tiêu chí sẽ tạo cùng thứ tự. Để đạt điều này, cần xác định:

- Các khóa sắp xếp và thứ tự ưu tiên.
- Cách xử lý giá trị bằng nhau.
- Quy tắc null.
- Collation và locale của chuỗi.
- Kiểu so sánh và precision của số.
- Time zone hoặc cách chuẩn hóa thời gian khi có liên quan.

## 3. Sắp xếp tăng dần và giảm dần

Tiêu chí cơ bản có hai hướng:

| Hướng | Ý nghĩa | Ví dụ với số |
|---|---|---|
| Ascending (ASC) | Giá trị nhỏ đến lớn | `2, 5, 9, 12` |
| Descending (DESC) | Giá trị lớn đến nhỏ | `12, 9, 5, 2` |

Ví dụ DSL:

```text
query productsByPrice {
    from Product
    orderBy price ascending
}
```

```text
query newestProducts {
    from Product
    orderBy createdAt descending
}
```

### 3.1. Hướng mặc định

DSL có thể yêu cầu viết rõ `ascending` hoặc `descending`, hoặc mặc định là ascending. Nếu có mặc định, cần tài liệu hóa và bảo đảm parser/editor hiển thị nhất quán.

### 3.2. Hướng sắp xếp không thay đổi giá trị

Descending chỉ đảo thứ tự so sánh; nó không biến đổi dữ liệu. Không nên hiểu `orderBy price descending` là phép tính `-price`, vì điều đó có thể sai với kiểu không phải số hoặc giá trị biên.

### 3.3. Kiểu không có thứ tự tự nhiên

Một số kiểu miền như `Money` có thể chỉ so sánh được khi cùng currency. Kiểu trạng thái có thể có thứ tự nghiệp vụ riêng hoặc không có thứ tự. DSL cần định nghĩa comparator hoặc từ chối sort nếu không có semantics phù hợp.

## 4. Sắp xếp theo nhiều khóa

Nhiều truy vấn cần tiêu chí chính và tiêu chí phụ. Các khóa được xét theo thứ tự khai báo: chỉ khi khóa trước bằng nhau mới xét khóa tiếp theo.

Ví dụ:

```text
query tickets {
    from Ticket
    orderBy priority descending, createdAt ascending, id ascending
}
```

Ý nghĩa:

1. Ticket có priority cao đứng trước.
2. Nếu priority bằng nhau, ticket cũ hơn đứng trước.
3. Nếu cả priority và createdAt bằng nhau, `id` quyết định thứ tự.

### 4.1. Lexicographic ordering

Đây là thứ tự từ điển theo bộ khóa. Có thể biểu diễn mỗi bản ghi bằng tuple:

```text
(priority DESC, createdAt ASC, id ASC)
```

So sánh tuple bắt đầu ở phần tử đầu tiên. Khi một cặp khóa khác nhau, kết quả của khóa đó quyết định thứ tự; các khóa sau không còn ảnh hưởng.

### 4.2. Mỗi khóa có hướng riêng

Các khóa trong cùng một `orderBy` có thể có hướng khác nhau:

```text
orderBy status ascending, total descending, id ascending
```

Không nên giả định một hướng chung cho toàn bộ danh sách trừ khi cú pháp DSL quy định rõ.

### 4.3. Tie-breaker

Tie-breaker là khóa phụ được thêm để phân biệt bản ghi có cùng giá trị ở các khóa chính. Khóa duy nhất như primary key thường là lựa chọn tốt.

### 4.4. Khóa phụ và pagination

Nếu page boundary nằm giữa nhiều bản ghi có cùng khóa chính, thiếu tie-breaker có thể khiến các bản ghi đổi vị trí giữa các request. Kết quả là một bản ghi có thể xuất hiện ở hai trang hoặc không xuất hiện ở trang nào.

## 5. Sắp xếp theo biểu thức

DSL có thể cho phép sort theo biểu thức tính toán thay vì chỉ tên field.

Ví dụ:

```text
orderBy lower(customer.name) ascending
orderBy quantity * unitPrice descending
orderBy date(createdAt) ascending
```

Biểu thức sắp xếp cần được kiểm tra kiểu và khả năng thực thi trên target. Nếu DSL cho phép gọi hàm trong `orderBy`, hàm đó cần có implementation tương ứng trong database hoặc runtime.

### 5.1. Computed key

Có thể tính khóa sắp xếp một lần cho mỗi bản ghi rồi dùng khóa đó để so sánh. Với truy vấn database, biểu thức thường được chuyển thành biểu thức `ORDER BY`; database quyết định cách thực thi.

### 5.2. Alias của projection

Nếu truy vấn đã tính `totalWithTax`, DSL có thể cho phép `orderBy totalWithTax`. Cần quy định có thể sắp xếp theo alias projection hay phải lặp lại biểu thức gốc.

### 5.3. Aggregation và grouping

Với truy vấn `groupBy`, ordering có thể áp dụng lên khóa nhóm hoặc kết quả aggregate như `count()` và `sum(amount)`. DSL cần xác định thứ tự sắp xếp xảy ra sau aggregation và những biểu thức nào được phép dùng.

### 5.4. Biểu thức có tác dụng phụ

Biểu thức dùng làm sort key nên thuần (pure) và xác định. Nếu biểu thức thay đổi trạng thái hoặc trả kết quả khác nhau mỗi lần gọi, thứ tự có thể không ổn định và database có thể đánh giá nó theo cách không dự đoán được.

## 6. Giá trị null trong sắp xếp

Khi khóa sắp xếp có thể null, cần quy định null đứng trước hay sau các giá trị bình thường.

Ví dụ dữ liệu:

| Customer | lastLogin |
|---|---|
| An | 2026-01-10 |
| Bình | null |
| Chi | 2026-02-02 |

Có thể có các chính sách:

- `NULLS FIRST`: null đứng trước.
- `NULLS LAST`: null đứng sau.
- Default theo target/database dialect.
- Cấm sort theo nullable field nếu không chỉ rõ.

Ví dụ DSL:

```text
orderBy lastLogin descending nulls last
```

### 6.1. Default null ordering

Các database có thể khác nhau về thứ tự mặc định của null khi sort ASC hoặc DESC. Nếu DSL muốn hành vi portable, nên định nghĩa null ordering độc lập với target hoặc luôn yêu cầu khai báo tường minh.

### 6.2. Null không phải giá trị nhỏ nhất

Không nên giả định null tương đương 0, chuỗi rỗng hoặc ngày sớm nhất. Null biểu thị thiếu hoặc không có giá trị; comparator cần xử lý nó như một trạng thái riêng.

### 6.3. Optional values

Với kiểu `Optional<T>` hoặc `T?`, quy tắc sort cần xác định cách lấy giá trị và vị trí của trường hợp absent. Nếu DSL phân biệt missing với null, có thể cần quy tắc riêng cho từng trạng thái.

## 7. Collation và sắp xếp chuỗi

Sắp xếp chuỗi phức tạp hơn so sánh số vì phụ thuộc bảng chữ cái, locale, chữ hoa/thường, dấu và quy tắc Unicode.

Ví dụ các chuỗi:

```text
"An", "Ánh", "Binh", "bình", "Đạt"
```

Thứ tự có thể khác tùy collation. Một database dùng binary ordering có thể cho kết quả khác so với collation tiếng Việt không phân biệt hoa thường hoặc dấu.

### 7.1. Locale

Locale xác định quy tắc ngôn ngữ và vùng. DSL có thể hỗ trợ:

```text
orderBy customer.name ascending collate "vi-VN"
```

Locale cần được chuẩn hóa và giới hạn theo các collation mà target hỗ trợ.

### 7.2. Case sensitivity

Có thể sắp xếp phân biệt chữ hoa/thường hoặc không phân biệt. Một cách là dùng collation phù hợp; cách khác là áp dụng biểu thức như `lower(name)`. Hai cách không luôn tương đương về Unicode.

### 7.3. Accent sensitivity

Một collation có thể coi `a` và `á` tương đương ở một cấp so sánh, hoặc phân biệt chúng. Cần xác định quy tắc nếu người dùng cần thứ tự ổn định qua các môi trường.

### 7.4. Natural sorting

Natural sort coi đoạn số trong chuỗi như số. Ví dụ `item2` có thể đứng trước `item10`, dù thứ tự từ điển thuần có thể đặt `item10` trước. Đây là tính năng riêng, không nên mặc định cho mọi chuỗi.

## 8. Kiểu dữ liệu và comparator

Ordering phải dùng comparator phù hợp với kiểu dữ liệu.

| Kiểu | Quy tắc cần xác định |
|---|---|
| Integer | So sánh số học và overflow không liên quan đến sort key đã lưu |
| Decimal | Precision và scale |
| Date | Thứ tự ngày lịch |
| Instant/DateTime | Time zone hoặc chuẩn hóa thời điểm |
| String | Collation, locale, case/accent sensitivity |
| Enum | Thứ tự khai báo hay thứ tự nghiệp vụ |
| Money | Currency có tương thích hay không |
| Duration | Đơn vị chuẩn hóa |
| Custom type | Comparator được đăng ký hoặc từ chối |

### 8.1. Số thập phân

Không nên chuyển Decimal sang floating-point chỉ để sắp xếp nếu việc chuyển đổi có thể làm mất độ chính xác. Comparator cần dùng semantics của kiểu nguồn.

### 8.2. Date và Instant

`Date` biểu diễn ngày lịch, còn `Instant` biểu diễn thời điểm tuyệt đối. Sắp xếp hai kiểu cần theo ý nghĩa tương ứng; không được so sánh chuỗi ngày định dạng tùy ý như thể mọi chuỗi đều có thứ tự thời gian.

### 8.3. Money

So sánh `Money` có thể yêu cầu cùng currency. Nếu có nhiều currency, DSL cần quy định quy đổi theo tỷ giá và thời điểm cụ thể hoặc không cho phép so sánh trực tiếp.

### 8.4. Custom comparator

DSL có thể cho phép đăng ký comparator cho kiểu miền. Comparator cần có tính nhất quán, xác định và tương thích giữa các target nếu cùng truy vấn có thể chạy ở nhiều nơi.

## 9. Phân trang bằng offset và limit

Offset pagination chọn một đoạn kết quả bằng vị trí bắt đầu và số dòng tối đa.

```text
query orders {
    from Order
    orderBy createdAt descending, id ascending
    offset 40
    limit 20
}
```

Truy vấn bỏ qua 40 dòng đầu và lấy tối đa 20 dòng tiếp theo.

### 9.1. Page number và page size

API có thể nhận page number và page size rồi chuyển thành offset:

```text
offset = (pageNumber - 1) * pageSize
```

Nếu page number bắt đầu từ 1, trang đầu có offset 0. Nếu API dùng zero-based index, trang đầu có page number 0. Quy ước cần được công bố rõ.

### 9.2. Limit

Limit là số dòng tối đa được trả về. Nên đặt giới hạn page size tối đa để tránh client yêu cầu hàng triệu dòng và gây quá tải.

### 9.3. Offset lớn

Offset lớn có thể tốn kém vì database vẫn phải xác định và bỏ qua nhiều dòng trước khi trả kết quả. Với bảng lớn, trang càng sâu có thể càng chậm.

### 9.4. Khi nào offset phù hợp?

Offset phù hợp khi:

- Dữ liệu vừa phải.
- Người dùng cần nhảy trực tiếp đến trang số N.
- Thứ tự ổn định và thay đổi dữ liệu trong lúc duyệt không gây vấn đề lớn.
- Database có thể xử lý offset hiệu quả.

## 10. Keyset pagination (seek pagination)

Keyset pagination tiếp tục từ giá trị khóa của bản ghi cuối trang trước thay vì đếm và bỏ qua một số lượng dòng.

Ví dụ sắp xếp theo `createdAt DESC, id ASC`. Trang tiếp theo lấy các dòng nằm sau cursor cuối cùng:

```text
where createdAt < lastCreatedAt
   or (createdAt == lastCreatedAt and id > lastId)
orderBy createdAt descending, id ascending
limit 20
```

Điều kiện so sánh cần khớp chính xác hướng của từng khóa. Với nhiều khóa, cursor chứa giá trị của tất cả khóa cần thiết để xác định vị trí tiếp theo.

### 10.1. Ưu điểm

- Không phải bỏ qua một offset lớn.
- Hiệu quả hơn khi có index phù hợp.
- Ít bị xáo trộn bởi việc thêm bản ghi ở đầu danh sách.
- Phù hợp với feed, API duyệt dữ liệu lớn và truy vấn tuần tự.

### 10.2. Hạn chế

- Khó nhảy trực tiếp đến trang bất kỳ.
- Cần một thứ tự tổng và cursor chứa đủ khóa.
- Cursor phải được mã hóa/serialize an toàn.
- Các khóa sort cần ổn định trong quá trình duyệt.
- Điều kiện seek cho nhiều khóa và null phức tạp hơn.

### 10.3. Cursor

Cursor là token đại diện cho vị trí tiếp tục. Nó có thể chứa:

- Các giá trị sort key của bản ghi cuối trang.
- Unique tie-breaker.
- Hướng và phiên bản sort definition.
- Query/filter fingerprint để tránh dùng cursor với truy vấn khác.
- Snapshot hoặc version nếu hệ thống hỗ trợ.

Ví dụ payload khái niệm:

```json
{
  "createdAt": "2026-02-12T10:00:00Z",
  "id": "order-1042",
  "sort": "createdAt:desc,id:asc",
  "queryHash": "..."
}
```

Cursor công khai thường nên opaque đối với client. Server có thể encode và ký token để người dùng không sửa các trường nội bộ.

### 10.4. Forward và backward pagination

Forward pagination lấy các bản ghi sau cursor; backward pagination lấy các bản ghi trước cursor. Khi truy vấn ngược, cần đảo hướng so sánh và có thể đảo kết quả trước khi trả về để giữ thứ tự hiển thị thống nhất.

## 11. Cursor và điều kiện nhiều khóa

Với ordering nhiều khóa, điều kiện keyset là biểu thức từ điển tương ứng với từng hướng.

Giả sử:

```text
orderBy priority descending, createdAt ascending, id ascending
```

Với cursor `(p, t, id)`, các bản ghi tiếp theo có thể được mô tả bằng:

```text
priority < p
or (priority == p and createdAt > t)
or (priority == p and createdAt == t and id > cursorId)
```

Đây là dạng khái niệm cho trường hợp các khóa không null. Nếu khóa có null, điều kiện phải phản ánh null ordering đã chọn. Không nên tự tạo cursor predicate bằng cách áp dụng cùng một toán tử cho mọi khóa.

### 11.1. Cursor phải chứa tie-breaker

Nếu cursor chỉ lưu `createdAt` mà nhiều bản ghi có cùng thời điểm, server không thể xác định duy nhất vị trí tiếp tục. Cần lưu thêm unique key như `id`.

### 11.2. Cursor gắn với truy vấn

Không nên dùng cursor của query A cho query B có filter hoặc sort khác. Server có thể lưu query fingerprint trong cursor và từ chối nếu không khớp.

### 11.3. Cursor có chữ ký

Ký cursor hoặc dùng token server-side giúp phát hiện việc client sửa giá trị. Cursor không nên chứa secret; nếu có dữ liệu nhạy cảm, cần mã hóa hoặc chỉ lưu opaque identifier phía server.

## 12. Page metadata và tổng số bản ghi

API phân trang thường trả dữ liệu cùng metadata:

```json
{
  "items": [
    {"id":"o-101"},
    {"id":"o-102"}
  ],
  "page": 3,
  "pageSize": 20,
  "hasNext": true,
  "totalCount": 248
}
```

Các trường phổ biến:

- `items`: bản ghi của trang hiện tại.
- `page` hoặc `cursor`: vị trí trang.
- `pageSize`: kích thước yêu cầu hoặc thực tế.
- `hasNext`/`hasPrevious`: còn dữ liệu ở hướng tương ứng không.
- `totalCount`: tổng số bản ghi phù hợp với filter.
- `totalPages`: tổng số trang nếu biết totalCount và pageSize.

### 12.1. Count query

`totalCount` thường cần một truy vấn count riêng với cùng điều kiện lọc nhưng không áp dụng pagination. Nếu có join hoặc group by, count cần đếm đúng đơn vị kết quả, không nhất thiết là số dòng của bảng gốc.

### 12.2. Count có thể tốn kém

Với dữ liệu lớn hoặc truy vấn phức tạp, count chính xác có thể tốn kém hơn lấy một trang. API có thể chỉ trả `hasNext`, hoặc cho phép total count tùy chọn.

### 12.3. Total pages

Nếu `totalCount = 0`, `totalPages` thường là 0. Nếu có dữ liệu:

```text
totalPages = ceil(totalCount / pageSize)
```

Page size phải lớn hơn 0. Cần quy định page number vượt quá total pages trả danh sách rỗng, lỗi hay được điều chỉnh về trang cuối.

### 12.4. Count và dữ liệu phải nhất quán

Nếu count và page query chạy ở hai snapshot khác nhau, `totalCount` có thể không khớp số trang thực tế trong lúc dữ liệu thay đổi. Với yêu cầu nhất quán cao, cần transaction/snapshot phù hợp hoặc chấp nhận metadata gần đúng.

## 13. Thứ tự thực thi và vị trí của pagination trong query

Query DSL cần quy định thứ tự các phép toán. Một pipeline quan hệ phổ biến:

```text
FROM / JOIN
     |
     v
WHERE
     |
     v
GROUP BY / AGGREGATE
     |
     v
HAVING
     |
     v
ORDER BY
     |
     v
OFFSET / LIMIT
     |
     v
SELECT / RESULT
```

Đây là mô hình logic; database optimizer có thể thay đổi thứ tự thực thi vật lý nếu vẫn giữ kết quả quan sát được.

### 13.1. Filter trước pagination

Thông thường cần lọc tập kết quả trước rồi mới sắp xếp và phân trang. Nếu limit trước filter, một trang có thể trả ít bản ghi dù còn nhiều bản ghi phù hợp phía sau.

### 13.2. Sort sau aggregation

Với group query, sort thường áp dụng lên các group hoặc aggregate result, không phải từng dòng nguồn. Ví dụ `orderBy sum(amount) descending` cần được thực hiện sau khi nhóm.

### 13.3. Projection và sort key

Có thể sort theo field không được trả trong projection nếu query semantics cho phép. DSL cần quy định điều này, đặc biệt khi có `distinct`, `groupBy` hoặc query chạy trên nhiều target.

### 13.4. Distinct

Khi có `distinct`, cần xác định ordering áp dụng trên tập giá trị distinct. Nếu sort key không nằm trong projection, một số target không cho phép hoặc cần quy tắc riêng.

## 14. Mapping sang SQL

Với relational backend, `orderBy`, offset và limit thường được chuyển thành SQL `ORDER BY`, `OFFSET` và `FETCH/LIMIT` tùy dialect.

Ví dụ DSL:

```text
query recentOrders {
    from Order
    where status == PAID
    orderBy createdAt descending, id ascending
    offset 20
    limit 10
}
```

SQL minh họa:

```sql
SELECT id, created_at, total
FROM orders
WHERE status = ?
ORDER BY created_at DESC, id ASC
OFFSET 20 ROWS
FETCH NEXT 10 ROWS ONLY;
```

SQL cụ thể phụ thuộc dialect. Một số database dùng `LIMIT 10 OFFSET 20`; một số dùng `FETCH FIRST` hoặc cú pháp khác.

### 14.1. Không tự nối giá trị người dùng vào SQL

Giá trị filter phải được bind parameter. Sort field và direction thường không thể bind như một value parameter, nên cần lấy từ AST đã resolve và allowlist theo schema/query model, không chèn raw text do client gửi.

### 14.2. Dialect portability

Null ordering, collation, offset syntax và cursor predicates có thể khác giữa database. Backend cần chuyển semantics DSL sang dialect cụ thể hoặc báo tính năng không hỗ trợ.

### 14.3. Keyset predicate

Backend có thể sinh điều kiện `WHERE` tương ứng với cursor. Với khóa nhiều chiều, cần tạo biểu thức OR lồng nhau theo đúng hướng và null policy.

### 14.4. Không có ORDER BY thì LIMIT không ổn định

SQL không bảo đảm thứ tự dòng nếu không có `ORDER BY`. `LIMIT` hoặc `OFFSET` một mình không tạo thứ tự ổn định.

## 15. Hiệu năng và index

Ordering và pagination có thể chiếm phần lớn chi phí của query. Thiết kế DSL nên cho phép backend tận dụng index và tránh yêu cầu sort lớn không cần thiết.

### 15.1. Index theo khóa sort

Index trên cột lọc và sort có thể giúp database tìm và trả kết quả nhanh hơn. Với multi-key ordering, composite index có thể hữu ích nếu thứ tự cột và hướng phù hợp query pattern.

### 15.2. Filter kết hợp ordering

Ví dụ query luôn lọc `status` rồi sort `createdAt DESC, id ASC`. Composite index như `(status, createdAt, id)` có thể phù hợp hơn các index rời, tùy database và selectivity.

### 15.3. Sort in memory

Nếu DSL chạy trên collection trong bộ nhớ, sort thường cần O(n log n) thời gian và có thể cần O(n) bộ nhớ tùy thuật toán. Với dữ liệu lớn, nên đẩy sorting xuống data source hoặc dùng streaming strategy khi có thể.

### 15.4. Offset sâu

Offset lớn thường buộc database đọc/bỏ qua nhiều dòng. Keyset pagination thường hiệu quả hơn khi duyệt tuần tự và có index phù hợp.

### 15.5. Query plan

Có thể kiểm tra execution plan để xem database dùng index, sort operation, temporary storage hoặc full scan. Đây là công cụ tối ưu hiệu năng, không thay thế kiểm tra tính đúng đắn.

## 16. Pagination khi dữ liệu thay đổi

Khi người dùng xem trang 1 rồi chuyển sang trang 2, dữ liệu có thể đã được thêm, xóa hoặc cập nhật. Cần xác định semantics mong muốn.

### 16.1. Offset pagination và dịch chuyển trang

Giả sử trang đầu có 20 bản ghi. Trước khi tải trang 2, một bản ghi mới được thêm vào đầu danh sách. Offset 20 có thể làm một bản ghi cũ bị lặp hoặc bỏ qua vì vị trí của các dòng đã dịch chuyển.

### 16.2. Keyset pagination và thay đổi dữ liệu

Keyset ít bị ảnh hưởng bởi bản ghi mới thêm trước cursor, vì trang tiếp theo dựa trên giá trị khóa cuối cùng. Tuy nhiên, nếu sort key của bản ghi thay đổi hoặc bản ghi bị xóa, tập kết quả vẫn có thể thay đổi.

### 16.3. Snapshot consistency

Nếu cần duyệt một tập dữ liệu nhất quán qua nhiều trang, hệ thống có thể dùng snapshot ID, transaction snapshot hoặc version watermark. Mỗi request tiếp theo phải đọc cùng snapshot hoặc cùng giới hạn version.

### 16.4. Eventual consistency

Với search index hoặc hệ thống phân tán, dữ liệu có thể cập nhật trễ. Pagination cần chấp nhận kết quả gần đúng hoặc sử dụng snapshot/version nếu yêu cầu không bỏ sót dữ liệu.

### 16.5. Cursor gắn với snapshot

Cursor có thể chứa snapshot token hoặc watermark để đảm bảo các trang thuộc cùng một phiên duyệt. Snapshot có thể hết hạn; server cần trả lỗi rõ và hướng dẫn bắt đầu lại.

## 17. Phân trang trong hệ thống phân tán

Khi dữ liệu nằm trên nhiều shard hoặc partition, việc sắp xếp toàn cục phức tạp hơn sort trên một bảng.

### 17.1. Local ordering và global ordering

Mỗi shard có thể trả các dòng đã sắp xếp cục bộ. Coordinator cần merge các luồng đã sắp xếp để tạo global order. Có thể dùng heap hoặc k-way merge thay vì gom toàn bộ dữ liệu rồi sort lại.

### 17.2. Tie-breaker toàn cục

Khóa tie-breaker phải duy nhất trên toàn bộ tập dữ liệu, không chỉ duy nhất trong từng shard. Có thể dùng global ID hoặc tuple `(shardId, localId)` nếu semantics đảm bảo duy nhất.

### 17.3. Offset qua nhiều shard

Offset lớn có thể khiến mỗi shard phải đọc nhiều dữ liệu rồi coordinator mới bỏ phần không cần. Keyset pagination và pushdown predicate thường giảm chi phí.

### 17.4. Cursor phân tán

Cursor có thể cần lưu vị trí tiếp theo của từng shard hoặc một global merge key. Token cần được bảo vệ và có thể chứa snapshot/version của các partition.

### 17.5. Thứ tự nhất quán giữa các shard

Các shard cần dùng comparator tương thích, đặc biệt với collation, null ordering và kiểu số/ngày. Nếu mỗi shard so sánh chuỗi theo locale khác nhau, kết quả merge toàn cục có thể sai.

## 18. Thiết kế cú pháp trong query DSL

Cú pháp nên thể hiện rõ thứ tự, hướng và chính sách cần thiết mà không làm truy vấn khó đọc.

Ví dụ một dạng DSL:

```text
query orders {
    from Order
    where status in [PAID, SHIPPED]
    orderBy {
        createdAt descending
        total descending nulls last
        id ascending
    }
    paginate {
        limit 25
        offset 50
    }
}
```

Hoặc cú pháp gọn:

```text
orderBy createdAt desc, id asc
limit 25 offset 50
```

### 18.1. Grammar và AST

AST có thể mô hình hóa:

```text
Query
├── source
├── predicate
├── orderings: List<Ordering>
│   ├── expression
│   ├── direction
│   ├── nullPolicy
│   └── collation?
└── pagination
    ├── offset?
    ├── limit?
    └── cursor?
```

Việc giữ mỗi ordering thành node riêng giúp validator, optimizer và backend xử lý nhất quán.

### 18.2. Chỉ một cơ chế pagination mỗi query?

DSL có thể cho phép offset/limit hoặc cursor, nhưng không nhất thiết cho phép dùng cả hai cùng lúc. Nếu hỗ trợ cả hai, cần định nghĩa precedence hoặc từ chối kết hợp để tránh ngữ nghĩa mơ hồ.

### 18.3. Giá trị động

Page size có thể đến từ parameter như `:pageSize`. Cần kiểm tra kiểu, giá trị dương và giới hạn tối đa tại thời điểm phù hợp.

### 18.4. Default page size

Có thể đặt page size mặc định, nhưng cần thống nhất giữa compiler, runtime và API. Default quá lớn gây tải không cần thiết; quá nhỏ khiến client phải gọi nhiều lần.

## 19. Validation và lỗi thường gặp

Query validator nên kiểm tra các điều kiện:

- Sort expression có thể được resolve và có kiểu hỗ trợ ordering.
- Direction chỉ nhận ASC hoặc DESC.
- Null policy chỉ áp dụng cho kiểu nullable hoặc được định nghĩa rõ.
- Collation hợp lệ và được target hỗ trợ.
- Offset không âm.
- Limit lớn hơn 0 và không vượt maximum.
- Cursor đúng định dạng, đúng query và đúng version.
- Không kết hợp các chế độ pagination bị cấm.
- Với cursor pagination, ordering tạo được total order.
- Sort key không dùng expression không xác định hoặc có tác dụng phụ nếu policy yêu cầu purity.

Ví dụ diagnostic:

```text
Invalid pagination limit: 0
Expected a positive integer between 1 and 500.
```

```text
Cursor pagination requires a deterministic ordering.
Add a unique tie-breaker such as "id" to the ORDER BY clause.
```

### 19.1. Offset âm

Offset âm thường không hợp lệ. DSL nên báo lỗi thay vì phụ thuộc vào database xử lý hoặc tự chuyển về 0.

### 19.2. Limit quá lớn

Limit vượt maximum có thể bị từ chối hoặc clamp theo policy. Từ chối thường dễ phát hiện lỗi client hơn; clamp cần được công bố để tránh client hiểu sai số dòng trả về.

### 19.3. Cursor sai hoặc hết hạn

Cursor không parse được, chữ ký không hợp lệ, query fingerprint không khớp hoặc snapshot hết hạn cần tạo diagnostic/API error riêng. Không nên bỏ qua cursor rồi trả trang đầu vì có thể khiến client lặp dữ liệu.

### 19.4. Unsupported sort expression

Backend có thể không hỗ trợ một function hoặc collation trong ORDER BY. Cần báo rõ target không thể biểu diễn expression đó thay vì sinh query khác semantics.

## 20. Bảo mật và giới hạn tài nguyên

Pagination cũng là một cơ chế bảo vệ tài nguyên. Nếu client có thể yêu cầu limit rất lớn hoặc cursor tùy ý, truy vấn có thể gây quá tải.

Các biện pháp:

- Giới hạn page size tối đa.
- Giới hạn offset sâu hoặc khuyến nghị cursor pagination.
- Bind filter values và kiểm soát sort fields qua allowlist.
- Ký hoặc mã hóa cursor nếu nó chứa metadata nội bộ.
- Gắn cursor với người dùng/tenant/query nếu cần.
- Giới hạn thời gian và chi phí truy vấn.
- Áp dụng authorization trước khi phân trang để không làm lộ số lượng hoặc vị trí bản ghi không được phép xem.

### 20.1. Sort field do client chọn

Không nên chèn tên cột raw do client gửi vào SQL. Client gửi sort key logic như `createdAt`; server resolve key này qua schema/AST và ánh xạ đến biểu thức đã được phê duyệt.

### 20.2. Cursor tampering

Client có thể sửa giá trị cursor để truy vấn vị trí khác hoặc cố vượt phạm vi tenant. Server cần kiểm tra chữ ký, query fingerprint, authorization và giới hạn cursor.

### 20.3. Authorization trước pagination

Phải lọc theo quyền truy cập trước khi xác định trang và total count. Nếu phân trang trước rồi mới loại bản ghi không được phép, kết quả có thể thiếu dòng, sai metadata hoặc làm lộ thông tin về dữ liệu bị ẩn.

## 21. API response và trải nghiệm người dùng

API nên cung cấp metadata đủ để client điều hướng mà không phải tự đoán.

Ví dụ offset response:

```json
{
  "items": [],
  "page": 2,
  "pageSize": 25,
  "totalCount": 132,
  "totalPages": 6,
  "hasNext": true,
  "hasPrevious": true
}
```

Ví dụ cursor response:

```json
{
  "items": [],
  "nextCursor": "opaque-token",
  "previousCursor": "opaque-token",
  "hasNext": true
}
```

### 21.1. Offset UI

Offset pagination phù hợp với giao diện có số trang, nút đầu/cuối và nhảy đến trang cụ thể. Nếu total count không có sẵn, UI có thể chỉ hiển thị Next/Previous.

### 21.2. Cursor UI

Cursor pagination phù hợp với nút “Load more”, infinite scroll hoặc feed. Client giữ token opaque và gửi lại token để lấy trang tiếp theo.

### 21.3. Empty page

Kết quả rỗng có thể nghĩa là không có dữ liệu phù hợp hoặc page number vượt quá phạm vi. API nên giữ semantics rõ ràng để client hiển thị đúng.

### 21.4. Kích thước trang thay đổi

Nếu client thay page size giữa một phiên cursor, cursor cũ có thể vẫn hợp lệ nhưng số lượng item tiếp theo thay đổi. Query contract cần quy định cursor có gắn với page size hay không.

## 22. Kiểm thử ordering và pagination

Kiểm thử cần bao phủ cả semantics của comparator và hành vi qua nhiều trang.

Các trường hợp nên có:

1. Sort ascending và descending với số, chuỗi và ngày.
2. Multi-key ordering với nhiều bản ghi bằng khóa chính.
3. Tie-breaker duy nhất tạo total order.
4. Nulls first và nulls last.
5. Collation, case và accent sensitivity.
6. Sort theo expression và aggregate.
7. Offset đầu, giữa, cuối và vượt phạm vi.
8. Limit nhỏ nhất, lớn nhất và không hợp lệ.
9. Page number zero-based/one-based theo hợp đồng.
10. Keyset pagination với khóa nhiều chiều.
11. Cursor sai, bị sửa, hết hạn hoặc dùng với query khác.
12. Thêm/xóa/cập nhật dữ liệu giữa các lần lấy trang.
13. Snapshot consistency và concurrent updates.
14. Count query khớp filter và semantics grouping.
15. SQL dialect khác nhau cho null ordering và pagination.
16. Authorization được áp dụng trước pagination.
17. Query plan và hiệu năng với index phù hợp.
18. Dữ liệu phân tán qua nhiều shard.

### 22.1. Property tests

Với cùng dataset và total order, có thể kiểm tra rằng:

- Kết quả sort đã có thứ tự không giảm hoặc không tăng theo comparator.
- Mỗi bản ghi xuất hiện đúng một lần khi ghép tất cả trang trên snapshot cố định.
- Các trang không chồng lặp và không bỏ sót bản ghi.
- Tổng số item qua các trang bằng số dòng trong tập kết quả nếu count chính xác.
- Cursor tiếp tục sau khóa cuối của trang trước.

### 22.2. Test dữ liệu có khóa trùng

Không chỉ test với sort key duy nhất. Cần tạo nhiều bản ghi cùng `createdAt`, cùng tên hoặc cùng priority để xác nhận tie-breaker thực sự được dùng.

### 22.3. Test khi dữ liệu thay đổi

Chạy test thêm/xóa record giữa page requests để xác nhận semantics đã chọn: best-effort traversal, keyset behavior hoặc snapshot consistency.

## 23. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Phân trang không có ordering | Trang không ổn định, trùng hoặc thiếu bản ghi | Yêu cầu ordering deterministic |
| Sort theo khóa không duy nhất | Thứ tự giữa các dòng bằng nhau không xác định | Thêm unique tie-breaker |
| Sort sau limit | Trang không phản ánh thứ tự toàn bộ tập | Filter, sort rồi mới paginate |
| Không quy định null ordering | Kết quả khác giữa database dialect | Khai báo null policy |
| Không xác định collation | Chuỗi có thứ tự khác giữa môi trường | Chọn collation/locale tường minh |
| Offset quá sâu | Query chậm do bỏ qua nhiều dòng | Dùng keyset/cursor khi phù hợp |
| Cursor chỉ chứa khóa chính | Không phân biệt được vị trí trong multi-key sort | Lưu mọi sort key và tie-breaker |
| Cursor không gắn với query | Có thể dùng token sai filter/sort | Dùng query fingerprint và signature |
| Count không cùng filter | Metadata sai với dữ liệu trả về | Dùng cùng predicate và snapshot phù hợp |
| Count bắt buộc cho mọi query | Tốn chi phí không cần thiết | Cho phép hasNext hoặc total tùy chọn |
| Client tự gửi raw sort column | Rủi ro injection hoặc truy cập field trái phép | Resolve qua allowlist/schema |
| Authorization sau pagination | Lộ dữ liệu hoặc làm trang thiếu dòng | Áp dụng quyền trước sort/page |
| Không kiểm tra concurrent changes | Kết quả duyệt có thể thiếu/lặp | Snapshot hoặc semantics nhất quán được công bố |

## 24. Nguyên tắc thiết kế sắp xếp và phân trang cho DSL

Khi xây dựng query DSL, có thể áp dụng các nguyên tắc sau:

1. **Định nghĩa ordering rõ ràng.** Mỗi khóa có expression, direction, null policy và collation khi cần.
2. **Hỗ trợ nhiều khóa.** Xác định thứ tự ưu tiên và hướng riêng cho từng khóa.
3. **Bảo đảm total order khi paginate.** Thêm tie-breaker duy nhất hoặc từ chối cursor query không xác định.
4. **Không giả định thứ tự tự nhiên.** Nếu không có `orderBy`, kết quả không được xem là ổn định.
5. **Đặt pagination sau filter và ordering.** Với grouping, áp dụng trên tập group theo semantics được công bố.
6. **Chọn pagination strategy phù hợp.** Offset cho nhảy trang; keyset/cursor cho duyệt tuần tự trên dữ liệu lớn.
7. **Quy định page size.** Có default, minimum và maximum rõ ràng.
8. **Thiết kế cursor an toàn.** Chứa đủ sort keys, tie-breaker và query identity; kiểm tra signature/version.
9. **Xác định count semantics.** Count phải cùng filter, group và snapshot nếu yêu cầu chính xác.
10. **Xử lý concurrent changes.** Chọn best-effort, keyset hoặc snapshot consistency theo yêu cầu.
11. **Giữ portability giữa target.** Chuẩn hóa null ordering, collation và dialect translation.
12. **Tận dụng index.** Xem xét filter/order composite indexes và execution plan.
13. **Áp dụng authorization trước pagination.** Không để phân trang làm lộ dữ liệu bị hạn chế.
14. **Kiểm thử khóa trùng và trường hợp biên.** Bao gồm cursor, null, dữ liệu thay đổi và nhiều shard.

## 25. Kết luận

Sắp xếp xác định thứ tự của tập kết quả; phân trang chọn một phần của thứ tự đó để truy xuất theo từng lần. Trong query DSL, hai chức năng phải được mô hình hóa cùng nhau vì pagination chỉ đáng tin khi ordering có semantics rõ và ổn định.

Với truy vấn đơn giản, offset/limit dễ dùng và hỗ trợ nhảy đến trang bất kỳ. Với dữ liệu lớn hoặc duyệt tuần tự, keyset/cursor pagination thường hiệu quả và ít bị dịch chuyển vị trí hơn. Dù chọn cách nào, cần tie-breaker duy nhất, quy tắc null/collation, cursor gắn với query, page size giới hạn và semantics nhất quán khi dữ liệu thay đổi.

Khi compiler hoặc runtime chuyển query DSL sang SQL hay backend phân tán, nó phải giữ đúng thứ tự logic, bind dữ liệu an toàn, áp dụng authorization trước pagination và tận dụng index phù hợp. Một thiết kế tốt giúp kết quả có thể dự đoán, API dễ sử dụng và truy vấn hoạt động ổn định khi quy mô dữ liệu tăng.
