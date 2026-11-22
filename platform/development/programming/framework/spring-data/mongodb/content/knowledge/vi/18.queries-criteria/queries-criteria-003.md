# Nhóm AND, OR, NOR và phủ định đúng phạm vi

> **Chương:** Query và Criteria  
> **Module:** `SPRING_DATA_MONGODB`

Trong MongoDB, lỗi truy vấn logic thường không nằm ở một phép so sánh đơn lẻ mà ở **phạm vi của phép nhóm và phủ định**. Một bộ lọc đúng phải đảm bảo mọi nhánh `OR` đều bị giới hạn bởi tenant, một phép `NOR` không vô tình loại cả điều kiện phân quyền, và câu “không phải X” có ý nghĩa chính xác khi field bị thiếu hoặc chứa `null`.

Spring Data MongoDB cung cấp `Query` và `Criteria` để diễn đạt các biểu thức này bằng Java. Chúng cho phép kết hợp `andOperator(...)`, `orOperator(...)`, `norOperator(...)` và `not()`, nhưng các phương thức **không có cùng phạm vi**. Bài này xây từng biểu thức MongoDB trước, rồi chuyển thành `Criteria`, thử trên một bộ BSON có cả dữ liệu đầy đủ và dữ liệu cũ thiếu field.

Nội dung thuộc module `SPRING_DATA_MONGODB`: kết nối, ánh xạ document và thao tác bằng `MongoTemplate` hoặc repository; các truy vấn là nền tảng cho aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **AND ngầm định** giữa các field, `$and` tường minh, `$or`, `$nor` và `$not`.
2. Đặt ngoặc logic đúng cho biểu thức `Tenant AND (A OR B) AND NOT(C OR D)`.
3. Sử dụng `Criteria.andOperator(...)`, `orOperator(...)`, `norOperator(...)` và `Criteria.not()` đúng phạm vi.
4. Phân biệt `$nor` với phủ định của cả một nhóm `$and`, áp dụng định luật De Morgan đúng cách.
5. Nhận biết cách `$ne`, `$nin`, `$not` và `$nor` tương tác với BSON `null`, field thiếu hoặc array.
6. Viết bộ lọc động an toàn, truy vấn có phạm vi tenant, kiểm thử tích hợp và kiểm tra index/hiệu năng.

## 2. Bản đồ các toán tử logic MongoDB

| Biểu thức | Cú pháp BSON | Diễn giải |
| --- | --- | --- |
| `A AND B` | `{ a: 1, b: 2 }` | Hai field cùng phải thỏa; đây là AND ngầm định |
| `A AND B` tường minh | `{ $and: [ {a: 1}, {b: 2} ] }` | Thuận tiện khi phải nhóm nhiều biểu thức |
| `A OR B` | `{ $or: [ {a: 1}, {b: 2} ] }` | Ít nhất một nhánh khớp |
| `NOT(A OR B)` | `{ $nor: [ {a: 1}, {b: 2} ] }` | Không nhánh nào khớp |
| `NOT(field thỏa điều kiện)` | `{ score: { $not: { $gte: 100 } } }` | Phủ định điều kiện **trên một field** |
| `field != x` | `{ status: { $ne: "PAID" } }` | Phủ định giá trị theo ngữ nghĩa `$ne` |
| `field không thuộc tập` | `{ status: { $nin: ["PAID","NEW"] } }` | Loại các giá trị trong tập |

**Cần nhớ:** `$not` là **field-level operator**, không phải một toán tử phủ định bất kỳ document expression ở vị trí gốc. Muốn phủ định **một hoặc nhiều điều kiện hoàn chỉnh**, thường dùng `$nor` với các nhánh được nhóm đúng.

### 2.1. Nhóm theo phép toán, không theo độ dài tên phương thức

Xét hai biểu thức:

```text
E1 = TENANT_A AND (STATUS_NEW OR STATUS_PAID)

E2 = (TENANT_A AND STATUS_NEW) OR STATUS_PAID
```

E1 chỉ cho phép document của tenant A. E2 có thể nhận document `STATUS_PAID` của **mọi tenant**, vì nhánh thứ hai không chứa điều kiện tenant.

Đây là lỗi **mở rộng phạm vi truy cập dữ liệu**, không đơn thuần là lỗi lọc kết quả. Khi xây query động, nên đặt `tenantId` như một điều kiện AND bao ngoài toàn bộ nhóm OR nghiệp vụ.

## 3. Bộ dữ liệu xuyên suốt

Giả sử collection `orders` ghi đơn hàng theo `tenantId`, `status`, `active`, `fraud` và `totalMinor`. Một số bản ghi lịch sử thiếu `status`/`fraud` để kiểm thử hành vi null/missing.

### 3.1. Seed dữ liệu thử nghiệm

```javascript
use shop

db.orders.insertMany([
  { _id: "A-01", tenantId: "T-A", status: "NEW",
    active: true, fraud: false, totalMinor: NumberLong(150),
    orderCode: "ORD-01" },

  { _id: "A-02", tenantId: "T-A", status: "PAID",
    active: true, fraud: false, totalMinor: NumberLong(750),
    orderCode: "ORD-02" },

  { _id: "A-03", tenantId: "T-A", status: "CANCELLED",
    active: true, fraud: false, totalMinor: NumberLong(900),
    orderCode: "ORD-03" },

  { _id: "A-04", tenantId: "T-A", status: "NEW",
    active: true, fraud: true, totalMinor: NumberLong(50),
    orderCode: "ORD-04" },

  { _id: "A-05", tenantId: "T-A", status: "PAID",
    active: false, fraud: true, totalMinor: NumberLong(1200),
    orderCode: "ORD-05" },

  { _id: "A-06", tenantId: "T-A", status: null,
    active: true, fraud: false, totalMinor: NumberLong(1000),
    orderCode: "ORD-06" },

  { _id: "A-07", tenantId: "T-A", /* thiếu status */
    active: true, /* thiếu fraud */ totalMinor: NumberLong(300),
    orderCode: "ORD-07" },

  { _id: "A-08", tenantId: "T-A", status: "NEW",
    active: true, fraud: false, totalMinor: NumberLong(350),
    orderCode: "ORD-08" },

  { _id: "A-09", tenantId: "T-A", status: "PAID",
    active: true, fraud: false, totalMinor: NumberLong(300),
    orderCode: "ORD-09" },

  { _id: "B-01", tenantId: "T-B", status: "PAID",
    active: true, fraud: false, totalMinor: NumberLong(900),
    orderCode: "ORD-B01" }
])
```

Chạy đoạn seed **chỉ trong MongoDB kiểm thử cô lập**. Các mã `A-01`, `B-01` là BSON String, còn `totalMinor` là BSON Int64.

| ID | Tenant | Status | Active | Fraud | Total |
| --- | --- | --- | --- | --- | ---: |
| A-01 | T-A | NEW | true | false | 150 |
| A-02 | T-A | PAID | true | false | 750 |
| A-03 | T-A | CANCELLED | true | false | 900 |
| A-04 | T-A | NEW | true | true | 50 |
| A-05 | T-A | PAID | false | true | 1200 |
| A-06 | T-A | null | true | false | 1000 |
| A-07 | T-A | *thiếu* | true | *thiếu* | 300 |
| A-08 | T-A | NEW | true | false | 350 |
| A-09 | T-A | PAID | true | false | 300 |
| B-01 | T-B | PAID | true | false | 900 |

**Không nhầm “thiếu field” với field chứa `null`:** hai BSON document khác nhau. Một số phép phủ định vẫn khớp cả hai vì điều kiện dương tính không khớp; nhưng `$exists` có thể phân biệt chúng.

## 4. AND ngầm định và $and tường minh

MongoDB mặc định kết hợp nhiều field ở **cùng một cấp document filter** bằng phép AND:

```javascript
db.orders.find({
  tenantId: "T-A",
  active: true
})
```

Tương đương về mặt logic:

```javascript
db.orders.find({
  $and: [
    { tenantId: "T-A" },
    { active: true }
  ]
})
```

Hai câu này trả mọi đơn thuộc T-A có `active: true`, bao gồm A-01, A-02, A-03, A-04, A-06, A-07, A-08 và A-09.

### 4.1. Criteria cho AND đơn giản

```java
Query query = Query.query(
    Criteria.where("tenantId").is("T-A")
        .and("active").is(true));

List<OrderDocument> orders =
    mongoTemplate.find(query, OrderDocument.class);
```

`mongoTemplate` là `MongoTemplate` đã được inject. Với filter một nhóm field đơn giản, `Criteria.where(...).and(...)` có ít mã hơn `andOperator(...)`.

### 4.2. AND nhiều nhóm

Khi cần nhóm phức tạp, dùng:

```java
Criteria tenant = Criteria.where("tenantId").is("T-A");
Criteria active = Criteria.where("active").is(true);
Criteria amount = Criteria.where("totalMinor").gte(300L);

Criteria all = new Criteria().andOperator(
    tenant, active, amount);

Query query = Query.query(all);
```

Tương đương:

```javascript
{
  $and: [
    { tenantId: "T-A" },
    { active: true },
    { totalMinor: { $gte: NumberLong(300) } }
  ]
}
```

**Không tạo hai entry cùng tên field trong một JSON object** để diễn đạt hai điều kiện. Trong Java, các dạng như `new Document("totalMinor", ...).append("totalMinor", ...)` có thể ghi đè key trước; khi kết hợp `Query.addCriteria` với hai `Criteria` mang cùng key, Spring Data cũng có thể từ chối vì trùng key.

Đối với **cùng một field**, viết chuỗi toán tử trong một Criteria:

```java
Criteria range = Criteria.where("totalMinor")
    .gte(300L)
    .lt(1000L);
```

Hoặc dùng `new Criteria().andOperator(...)` khi hai nhóm logic cần tồn tại đồng thời nhưng không thể nhập vào cùng một object field.

## 5. OR: đặt các lựa chọn trong đúng phạm vi

Yêu cầu: đơn thuộc tenant T-A và có **trạng thái NEW hoặc PAID**.

### 5.1. BSON chính xác

```javascript
db.orders.find({
  tenantId: "T-A",
  $or: [
    { status: "NEW" },
    { status: "PAID" }
  ]
})
```

Kết quả không xét thứ tự: **A-01, A-02, A-04, A-05, A-08, A-09**. B-01 là `PAID` nhưng thuộc T-B nên bị loại.

Tất cả phần tử trong `$or` là những **điều kiện độc lập**. Với bộ lọc khác nhau trên từng field, `$or` có thể phù hợp hơn một `$in` trên một field.

### 5.2. Spring Data Criteria.orOperator

```java
Criteria statusChoices = new Criteria().orOperator(
    Criteria.where("status").is(OrderStatus.NEW),
    Criteria.where("status").is(OrderStatus.PAID));

Criteria scoped = new Criteria().andOperator(
    Criteria.where("tenantId").is("T-A"),
    statusChoices);

List<OrderDocument> result = mongoTemplate.find(
    Query.query(scoped), OrderDocument.class);
```

Spring Data mapping thông thường chuyển enum `OrderStatus.NEW`/`PAID` sang chuỗi lưu trong BSON. Tên field ở `Criteria` là property Java khi dùng entity mapping của `MongoTemplate`; nếu đã dùng `@Field` để đổi tên field, mapper xử lý việc ánh xạ phù hợp.

Đối với nhiều giá trị **cùng một field**, có thể viết ngắn hơn:

```java
Query query = Query.query(
    Criteria.where("tenantId").is("T-A")
        .and("status")
        .in(OrderStatus.NEW, OrderStatus.PAID));
```

`$in` và `$or` của những phép bằng trên **một scalar field** thường có cùng ý nghĩa chọn tập giá trị; nhưng chúng không phải cùng một cấu trúc ở mọi trường hợp (đặc biệt khi mỗi nhánh OR có nhiều field/biểu thức).

### 5.3. Ví dụ OR trên hai thuộc tính khác nhau

Yêu cầu: T-A và (**status NEW hoặc totalMinor từ 900 trở lên**).

```javascript
db.orders.find({
  tenantId: "T-A",
  $or: [
    { status: "NEW" },
    { totalMinor: { $gte: NumberLong(900) } }
  ]
})
```

Kết quả: **A-01, A-03, A-04, A-05, A-06, A-08**. A-06 có `status: null` nhưng số tiền 1000 nên khớp nhánh số tiền.

Đây là ví dụ minh họa OR là phép **hợp**. Một document chỉ cần thỏa **một** trong các nhánh, nhưng vẫn phải thỏa điều kiện tenant **ở bên ngoài**.

## 6. NOR: phủ định *toàn bộ nhóm OR*

`$nor` chọn các document mà **không điều kiện nào trong danh sách khớp**:

```text
NOR(A, B)  =  NOT(A OR B)
           =  (NOT A) AND (NOT B)
```

Giả sử cần các đơn T-A mà **không bị hủy** và **không gắn cờ gian lận**:

```javascript
db.orders.find({
  tenantId: "T-A",
  $nor: [
    { status: "CANCELLED" },
    { fraud: true }
  ]
})
```

Kết quả: **A-01, A-02, A-06, A-07, A-08, A-09**.

Vì sao A-06 và A-07 vẫn xuất hiện? `status: null` hoặc field `status` bị thiếu không khớp điều kiện `status: "CANCELLED"`; field `fraud` bị thiếu cũng không khớp `fraud: true`. Do đó **không nhánh nào của NOR khớp**, nên document được nhận.

### 6.1. Criteria.norOperator

```java
Criteria excluded = new Criteria().norOperator(
    Criteria.where("status").is(OrderStatus.CANCELLED),
    Criteria.where("fraud").is(true));

Criteria scoped = new Criteria().andOperator(
    Criteria.where("tenantId").is("T-A"),
    excluded);

Query query = Query.query(scoped);
List<OrderDocument> result = mongoTemplate.find(
    query, OrderDocument.class);
```

### 6.2. Giới hạn phạm vi của phủ định

**Đúng:**

```text
(tenantId = T-A) AND NOT(status = CANCELLED OR fraud = true)
```

**Sai trong hệ thống nhiều tenant:**

```text
NOT(tenantId = T-A OR status = CANCELLED OR fraud = true)
```

Biểu thức thứ hai không chỉ “loại đơn xấu trong tenant A”; nó phủ định luôn điều kiện tenant và có thể **chọn các tenant khác**. Đừng đưa ràng buộc bảo mật vào bên trong một nhóm bị phủ định rồi mong ràng buộc đó vẫn có hiệu lực.

### 6.3. NOR khác với NOT của một nhóm AND

Hai công thức:

```text
X = NOT(A OR B)  = (NOT A) AND (NOT B)
Y = NOT(A AND B) = (NOT A) OR  (NOT B)
```

**Không tương đương.** Nếu A đúng, B sai thì X sai nhưng Y đúng.

Ví dụ cần loại document **đồng thời** có `status PAID` **và** `fraud true`, nghĩa là:

```text
NOT(status = PAID AND fraud = true)
```

Biểu diễn bằng cách phủ định một **nhóm AND đã được đóng**:

```javascript
db.orders.find({
  tenantId: "T-A",
  $nor: [
    {
      $and: [
        { status: "PAID" },
        { fraud: true }
      ]
    }
  ]
})
```

Không được viết `$nor: [{status:"PAID"}, {fraud:true}]` cho yêu cầu này. Cách viết đó loại mọi document PAID **hoặc** fraud true, rộng hơn nhiều.

Spring Data:

```java
Criteria both = new Criteria().andOperator(
    Criteria.where("status").is(OrderStatus.PAID),
    Criteria.where("fraud").is(true));

Criteria notBoth = new Criteria().norOperator(both);

Criteria scoped = new Criteria().andOperator(
    Criteria.where("tenantId").is("T-A"),
    notBoth);
```

Lưu ý: `norOperator` cần ít nhất một biểu thức hợp lệ; không xây nhóm rỗng từ dữ liệu input và hy vọng framework tự chọn ý nghĩa nghiệp vụ.

## 7. $not chỉ phủ định *một điều kiện trên field*

`$not` được đặt **bên trong field**:

```javascript
db.orders.find({
  totalMinor: { $not: { $gte: NumberLong(300) } }
})
```

Nó chọn các document có `totalMinor` **không thỏa** điều kiện `$gte: 300`. Với bộ seed hiện tại (mọi document có số tiền), đó là A-01 và A-04. Nếu có document **thiếu totalMinor**, document đó có thể cũng khớp `$not` vì không thỏa phép so sánh dương tính.

### 7.1. Criteria.not()

```java
Criteria amountNotLarge = Criteria
    .where("totalMinor")
    .not()
    .gte(300L);

Query query = Query.query(
    new Criteria().andOperator(
        Criteria.where("tenantId").is("T-A"),
        amountNotLarge));
```

Spring Data dùng `not()` để phủ định **toán tử kế tiếp trên cùng field**. Nó không áp dụng cho một `Query` hoàn chỉnh và không nên dùng để “đặt NOT trước một orOperator”. Chẳng hạn việc gọi `not().orOperator(...)` không phải cú pháp hợp lệ để diễn tả phủ định nhóm OR trong Criteria API; dùng `norOperator(...)`.

### 7.2. Với regex

```javascript
db.orders.find({
  orderCode: { $not: /^TEST-/i }
})
```

Tương ứng về ý nghĩa với:

```java
import java.util.regex.Pattern;

Criteria notTestOrder = Criteria
    .where("orderCode")
    .not()
    .regex(Pattern.compile("^TEST-", Pattern.CASE_INSENSITIVE));
```

Đây là **điều kiện trên field `orderCode`**, không phủ định cả BSON document. `$not` trên regex có thể nhận cả document **thiếu field `orderCode`**. Nếu nghiệp vụ chỉ muốn mã đơn tồn tại và không bắt đầu bằng TEST, hãy thêm điều kiện tồn tại/kiểu dữ liệu phù hợp.

### 7.3. $not, $ne, $nin và $nor: khi nào dùng?

| Ý định | Biểu thức ưu tiên | Cẩn trọng |
| --- | --- | --- |
| Field khác giá trị X | `$ne` | Thường khớp cả field thiếu; đặc biệt xem `null` |
| Field không thuộc tập [X,Y] | `$nin` | Có thể nhận field thiếu; tập rỗng thường rất rộng |
| Phủ định một phép so sánh/regex trên field | `$not` | Không phải phủ định cả query |
| Phủ định ít nhất một nhóm điều kiện toàn document | `$nor` | Tập nhánh phải được nhóm đúng theo De Morgan |
| Phải nằm trong tập trạng thái **được phép** | `$in` | Fail-closed với allowlist rỗng |

Ví dụ `{ status: { $ne: "PAID" } }` trên dữ liệu T-A có thể nhận cả `status: null` và document thiếu `status`. Nếu muốn **chỉ nhận các giá trị hợp lệ cụ thể**, dùng `$in: ["NEW", "CANCELLED"]` thay vì phủ định PAID và giả định mọi giá trị còn lại đều hợp lệ.

## 8. Sơ đồ ngoặc logic: ghép AND, OR và NOR

Một bộ lọc nghiệp vụ phổ biến:

> Chỉ lấy đơn của tenant T-A, còn active, có trạng thái NEW hoặc PAID, tổng tiền từ 300 trở lên, đồng thời không bị hủy và không đánh dấu gian lận.

Ta viết biểu thức trước khi chuyển sang Java:

```text
T = tenantId = "T-A"
A = active = true
S = (status = NEW OR status = PAID)
M = totalMinor >= 300
E = NOT(status = CANCELLED OR fraud = true)

Kết quả mong muốn = T AND A AND S AND M AND E
```

Biểu thức BSON đầy đủ:

```javascript
db.orders.find({
  $and: [
    { tenantId: "T-A" },
    { active: true },
    {
      $or: [
        { status: "NEW" },
        { status: "PAID" }
      ]
    },
    { totalMinor: { $gte: NumberLong(300) } },
    {
      $nor: [
        { status: "CANCELLED" },
        { fraud: true }
      ]
    }
  ]
})
```

Trên bộ dữ liệu mẫu, kết quả là **A-02, A-08, A-09**. Các record khác không đạt ít nhất một điều kiện: A-01 dưới mức tiền, A-04 dưới mức tiền và bị đánh dấu fraud, A-05 không active, A-03 bị hủy, A-06/A-07 không có trạng thái được cho phép, B-01 ở tenant khác.

### 8.1. Viết bằng Criteria

```java
Criteria allowed = new Criteria().orOperator(
    Criteria.where("status").is(OrderStatus.NEW),
    Criteria.where("status").is(OrderStatus.PAID));

Criteria excluded = new Criteria().norOperator(
    Criteria.where("status").is(OrderStatus.CANCELLED),
    Criteria.where("fraud").is(true));

Criteria filter = new Criteria().andOperator(
    Criteria.where("tenantId").is("T-A"),
    Criteria.where("active").is(true),
    allowed,
    Criteria.where("totalMinor").gte(300L),
    excluded);

Query query = Query.query(filter);
List<OrderDocument> matched = mongoTemplate.find(
    query, OrderDocument.class);
```

Ở đây `OrderStatus` và `OrderDocument` là các kiểu Java minh họa ở phần sau; `mongoTemplate` phải được inject đúng bean của ứng dụng. `Criteria` giúp biểu diễn nhóm giống như ngoặc trong công thức, nhờ đó việc kiểm tra code dễ hơn so với một câu query string được ghép nhiều nhánh.

### 8.2. Thứ tự nhóm và phân quyền

Một hệ thống có thể cho người dùng tạo bộ lọc tự do qua UI. Luôn phân biệt:

- **Ràng buộc bắt buộc:** tenantId, phạm vi quyền, soft-delete policy và các điều kiện bảo vệ dữ liệu.
- **Điều kiện lựa chọn:** trạng thái, số tiền, loại đơn, tag, khoảng thời gian.
- **Điều kiện loại trừ:** cờ gian lận, trạng thái cấm, hoặc các trường hợp chất lượng dữ liệu.

Nên đặt **ràng buộc bắt buộc ở cùng nhóm AND bao ngoài**. Mọi nhánh OR, NOR xuất phát từ input phải nằm bên trong phạm vi đó. Tuy nhiên, chỉ đưa `tenantId` vào query **chưa xác thực quyền**: service phải xác định tenantId được phép từ danh tính/ủy quyền trước khi gọi repository.

## 9. Phủ định trên dữ liệu null và field thiếu

MongoDB không áp dụng logic hai giá trị đơn giản cho mọi phép so sánh khi dữ liệu có thể thiếu hoặc `null`. Bản thân phép phủ định dương tính còn liên quan đến kiểu BSON và toán tử được dùng.

### 9.1. Bảng kết quả cụ thể

Để so sánh, luôn thêm `tenantId: "T-A"` ngoài điều kiện đang xét:

| Điều kiện | ID thuộc T-A được nhận | Lý do đặc biệt |
| --- | --- | --- |
| `status: "PAID"` | A-02, A-05, A-09 | Chỉ trạng thái PAID |
| `status: { $ne: "PAID" }` | A-01, A-03, A-04, A-06, A-07, A-08 | Chấp nhận cả null và field missing |
| `$nor: [{status:"PAID"}]` | A-01, A-03, A-04, A-06, A-07, A-08 | Không khớp nhánh PAID |
| `status: { $in: ["NEW","PAID"] }` | A-01, A-02, A-04, A-05, A-08, A-09 | Danh sách allowlist |
| `status: { $exists:true, $ne:null }` | A-01, A-02, A-03, A-04, A-05, A-08, A-09 | Loại A-06 null và A-07 missing |
| `$nor: [{status:"CANCELLED"}, {fraud:true}]` | A-01, A-02, A-06, A-07, A-08, A-09 | Không hủy và không fraud true |
| `$nor: [{status:{$exists:true}}]` | A-07 | Chỉ field status không tồn tại |

**Quan trọng:** `status: null` và `status: { $exists: false }` không cùng một ý nghĩa. Truy vấn `{ status: null }` theo quy tắc MongoDB thường khớp **cả null lẫn field missing**. Nếu cần **chỉ BSON null nhưng field hiện diện**, phải kết hợp với `$exists: true` hoặc kiểm tra `$type: "null"` theo yêu cầu.

### 9.2. Không vô tình biến phủ định thành allowlist

Giả sử enum trong ứng dụng hiện tại chỉ có `NEW`, `PAID`, `CANCELLED`. Câu:

```javascript
{ status: { $ne: "CANCELLED" } }
```

**Không đồng nghĩa** với:

```javascript
{ status: { $in: ["NEW", "PAID"] } }
```

Câu đầu còn nhận `null`, missing và trạng thái khác như `REFUNDED` được phiên bản mới bổ sung. Trong bộ lọc bảo mật hoặc quyết định nghiệp vụ có tập trạng thái cho phép rõ ràng, **lọc dương tính bằng `$in`** thường an toàn hơn phủ định một vài trạng thái cấm.

### 9.3. Kiểm tra field tồn tại trước khi phủ định

Nếu yêu cầu là “có trạng thái được ghi và không phải CANCELLED”, có thể diễn đạt:

```javascript
{
  status: {
    $exists: true,
    $ne: null,
    $nin: ["CANCELLED"]
  }
}
```

Ở Java:

```java
Criteria status = Criteria.where("status")
    .exists(true)
    .ne(null)
    .nin(OrderStatus.CANCELLED);
```

Với bộ dữ liệu mẫu, query cho tenant A trả `A-01, A-02, A-05, A-08, A-09`. Nhưng trong database có nhiều enum lịch sử không được ứng dụng mới biết, điều kiện trên vẫn có thể nhận các trạng thái **không phải CANCELLED** nhưng chưa được công nhận. Khi yêu cầu là “chỉ NEW hoặc PAID”, dùng `in(NEW, PAID)` trực tiếp sẽ rõ và chặt hơn.

### 9.4. Không áp phủ định lên field nhầm loại dữ liệu

Nếu BSON có `fraud: "false"` là String từ phiên bản cũ, đó **không phải** BSON Boolean `false`. Câu `{ fraud: { $ne: true } }` có thể nhận cả string này, nhưng điều đó không chứng minh đơn đã được kiểm tra gian lận và đánh dấu false hợp lệ.

Giải pháp đúng là xác định hợp đồng kiểu dữ liệu, kiểm kê record cũ và migration; không dùng `$nor`/`$ne` để che sự không nhất quán của schema.

## 10. Nhóm với cùng một field, nhiều OR và giới hạn của Query.addCriteria

### 10.1. Không ghi đè khóa trong JSON

Ví dụ này **không hợp lệ về ý định**:

```javascript
// PHẢN VÍ DỤ: cùng key $or ở một object.
{
  $or: [{ status: "NEW" }, { status: "PAID" }],
  $or: [{ fraud: false }, { active: true }]
}
```

Trong JavaScript/BSON document, một key bị lặp có thể làm biểu thức đầu mất tác dụng hoặc dẫn đến hành vi không mong muốn. MongoDB cũng không khuyến khích xây document có field name lặp. Tương tự, gọi `query.addCriteria(or1)` rồi `query.addCriteria(or2)` khi cả hai cùng có key `$or` có thể bị Spring Data từ chối do duplicate criteria.

Nếu ý định là **(NEW OR PAID) AND (fraud=false OR active=true)**, dùng nhóm `$and` chứa **hai `$or` riêng**:

```javascript
db.orders.find({
  tenantId: "T-A",
  $and: [
    {
      $or: [
        { status: "NEW" },
        { status: "PAID" }
      ]
    },
    {
      $or: [
        { fraud: false },
        { active: true }
      ]
    }
  ]
})
```

Spring Data:

```java
Criteria statusOr = new Criteria().orOperator(
    Criteria.where("status").is(OrderStatus.NEW),
    Criteria.where("status").is(OrderStatus.PAID));

Criteria flagOr = new Criteria().orOperator(
    Criteria.where("fraud").is(false),
    Criteria.where("active").is(true));

Criteria filter = new Criteria().andOperator(
    Criteria.where("tenantId").is("T-A"),
    statusOr,
    flagOr);
```

### 10.2. Vì sao AND/OR trong array khác AND trên field lồng nhau?

Giả sử document chứa mảng:

```javascript
{
  _id: "O-ARRAY",
  items: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 9 }
  ]
}
```

Query:

```javascript
db.orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 5 }
})
```

**Có thể khớp** document này vì điều kiện `sku=A` do phần tử đầu thỏa, còn `qty>=5` do phần tử sau thỏa. Hai điều kiện AND của đường dẫn mảng **không tự yêu cầu cùng một phần tử**.

Nếu cần cùng phần tử `sku=A AND qty>=5`:

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 5 }
    }
  }
})
```

Query này **không khớp** `O-ARRAY`. Trong `Criteria`, dùng `elemMatch(...)` để tạo phạm vi điều kiện trên **một phần tử array**. Đây cũng là một dạng “đặt ngoặc đúng phạm vi”, ngoài AND/OR/NOR ở cấp document.

## 11. Model Java và service có ranh giới tenant

### 11.1. Entity và enum

File `OrderStatus.java`:

```java
package com.example.shop.orders;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    OrderStatus status,
    Boolean active,
    Boolean fraud,
    Long totalMinor,
    String orderCode
) {}
```

`Boolean` và `Long` được dùng thay vì primitive nhằm không đánh đồng dữ liệu thiếu/`null` với một giá trị mặc định. Trong nghiệp vụ mới, có thể yêu cầu các field luôn không null và kiểm tra tại ranh giới ghi; model ở đây cho phép đọc dữ liệu cũ để minh họa.

### 11.2. Bộ lọc động fail-closed

Giả sử màn hình nhận:

- `allowedStatuses`: các trạng thái được phép chọn, **rỗng = không có kết quả**.
- `includeHighValueNew`: có cho phép thêm đơn NEW có tiền từ ngưỡng không.
- `excludeFraudAndCancelled`: có loại những đơn bị đánh dấu fraud hoặc CANCELLED không.
- `tenantId`: tenant đã được service xác định từ người dùng có quyền.

File `OrderSearchService.java`:

```java
package com.example.shop.orders;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderSearchService {

    private final MongoTemplate template;

    public OrderSearchService(MongoTemplate template) {
        this.template = template;
    }

    public List<OrderDocument> search(
            String permittedTenantId,
            Collection<OrderStatus> allowedStatuses,
            boolean includeHighValueNew,
            long minimumAmount,
            boolean excludeFraudAndCancelled) {

        Objects.requireNonNull(
            permittedTenantId, "permittedTenantId");
        Objects.requireNonNull(
            allowedStatuses, "allowedStatuses");

        if (permittedTenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant rỗng");
        }
        if (allowedStatuses.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException(
                "Trạng thái được phép không được chứa null");
        }
        if (minimumAmount < 0) {
            throw new IllegalArgumentException(
                "minimumAmount phải không âm");
        }

        List<Criteria> alternatives = new ArrayList<>();

        if (!allowedStatuses.isEmpty()) {
            alternatives.add(
                Criteria.where("status").in(allowedStatuses));
        }
        if (includeHighValueNew) {
            alternatives.add(new Criteria().andOperator(
                Criteria.where("status").is(OrderStatus.NEW),
                Criteria.where("totalMinor").gte(minimumAmount)
            ));
        }

        // Không có lựa chọn nào được cấp phép: không gọi database.
        if (alternatives.isEmpty()) {
            return List.of();
        }

        List<Criteria> required = new ArrayList<>();
        required.add(
            Criteria.where("tenantId").is(permittedTenantId));

        required.add(new Criteria().orOperator(
            alternatives.toArray(new Criteria[0])));

        if (excludeFraudAndCancelled) {
            required.add(new Criteria().norOperator(
                Criteria.where("status")
                    .is(OrderStatus.CANCELLED),
                Criteria.where("fraud").is(true)
            ));
        }

        Criteria filter = new Criteria().andOperator(
            required.toArray(new Criteria[0]));

        Query query = Query.query(filter)
            .with(Sort.by(
                Sort.Order.desc("totalMinor"),
                Sort.Order.desc("id")))
            .limit(50);

        return template.find(query, OrderDocument.class);
    }
}
```

**Phạm vi tenant luôn nằm trong nhóm AND ngoài cùng.** Hai nhánh OR được thêm tùy đầu vào, nhưng không nhánh nào có thể “thoát” khỏi `tenantId`. Nhánh không có lựa chọn nào trả `List.of()` mà không thực hiện truy vấn rộng bất ngờ.

Hạn mức `50` chỉ minh họa bảo vệ endpoint; thực tế cần giới hạn từ cấu hình sản phẩm và cách phân trang phù hợp. Không dùng một kết quả 50 phần tử để đại diện cho toàn bộ lịch sử khi xử lý xuất dữ liệu.

**Về bảo mật:** `permittedTenantId` phải lấy từ hoặc được kiểm tra đối chiếu với identity/authorization của người dùng. Chữ “permitted” trong tên tham số tự nó **không** chứng minh quyền.

### 11.3. Chú ý sự khác biệt giữa OR và phép hợp nghiệp vụ

Trong service vừa viết, một document thỏa **bất kỳ** nhánh nào trong `alternatives` sẽ được chọn, sau đó vẫn phải thỏa toàn bộ ràng buộc AND khác. Nếu sản phẩm muốn “chọn trạng thái trong allowlist **và đồng thời** đạt ngưỡng tiền”, không được dùng OR; lúc đó phải đặt điều kiện ngưỡng vào nhóm AND.

Việc tách câu tiếng Việt thành các phép logic tường minh **trước khi code** giúp tránh lỗi mà compiler không thể phát hiện.

## 12. Kiểm thử tích hợp các nhóm logic với BSON thật

Test mock `MongoTemplate` chỉ chứng minh service gọi hàm; nó không xác minh filter cuối cùng của Spring Data hay cách MongoDB xử lý `$nor` khi field không tồn tại. Vì thế, nên sử dụng MongoDB instance dành riêng cho test, với BSON được chèn qua Java driver để tạo được **null và missing thực sự**.

### 12.1. Fixture cho JUnit 5

File `LogicalCriteriaIntegrationTest.java`:

```java
package com.example.shop.orders;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class LogicalCriteriaIntegrationTest {

    @Autowired
    MongoTemplate template;

    private static Document order(
            String id, String tenant,
            String status, Boolean fraud,
            boolean active, long total) {

        Document d = new Document("_id", id)
            .append("tenantId", tenant)
            .append("active", active)
            .append("totalMinor", total)
            .append("orderCode", "ORD-" + id);

        if (status != null) {
            d.append("status", status);
        }
        if (fraud != null) {
            d.append("fraud", fraud);
        }
        return d;
    }

    private static List<String> ids(List<OrderDocument> items) {
        return items.stream().map(OrderDocument::id).toList();
    }

    private List<String> findIds(Criteria criteria) {
        return ids(template.find(
            Query.query(criteria), OrderDocument.class));
    }

    @BeforeEach
    void seed() {
        // Xóa dữ liệu CHỈ trên database test cô lập.
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        Document nullStatus = order(
            "A-06", "T-A", null, false, true, 1000)
            .append("status", null);

        Document missingStatusAndFraud = order(
            "A-07", "T-A", null, null, true, 300);

        collection.insertMany(List.of(
            order("A-01", "T-A", "NEW", false, true, 150),
            order("A-02", "T-A", "PAID", false, true, 750),
            order("A-03", "T-A", "CANCELLED", false, true, 900),
            order("A-04", "T-A", "NEW", true, true, 50),
            order("A-05", "T-A", "PAID", true, false, 1200),
            nullStatus,
            missingStatusAndFraud,
            order("A-08", "T-A", "NEW", false, true, 350),
            order("A-09", "T-A", "PAID", false, true, 300),
            order("B-01", "T-B", "PAID", false, true, 900)
        ));
    }

    @Test
    void orGroupStaysInsideTenantScope() {
        Criteria allowed = new Criteria().orOperator(
            Criteria.where("status").is(OrderStatus.NEW),
            Criteria.where("status").is(OrderStatus.PAID));

        Criteria filter = new Criteria().andOperator(
            Criteria.where("tenantId").is("T-A"),
            allowed);

        assertThat(findIds(filter))
            .containsExactlyInAnyOrder(
                "A-01", "A-02", "A-04", "A-05",
                "A-08", "A-09")
            .doesNotContain("B-01");
    }

    @Test
    void norExcludesEitherConditionButKeepsMissingFields() {
        Criteria filter = new Criteria().andOperator(
            Criteria.where("tenantId").is("T-A"),
            new Criteria().norOperator(
                Criteria.where("status")
                    .is(OrderStatus.CANCELLED),
                Criteria.where("fraud").is(true)));

        assertThat(findIds(filter))
            .containsExactlyInAnyOrder(
                "A-01", "A-02", "A-06",
                "A-07", "A-08", "A-09");
    }

    @Test
    void norOfAndIsDifferentFromNorOfIndividualTerms() {
        Criteria paidAndFraud = new Criteria().andOperator(
            Criteria.where("status").is(OrderStatus.PAID),
            Criteria.where("fraud").is(true));

        Criteria filter = new Criteria().andOperator(
            Criteria.where("tenantId").is("T-A"),
            new Criteria().norOperator(paidAndFraud));

        // Chỉ A-05 đồng thời PAID và fraud=true.
        assertThat(findIds(filter))
            .containsExactlyInAnyOrder(
                "A-01", "A-02", "A-03", "A-04",
                "A-06", "A-07", "A-08", "A-09");
    }

    @Test
    void notPaidIncludesNullAndMissingStatus() {
        Criteria filter = new Criteria().andOperator(
            Criteria.where("tenantId").is("T-A"),
            Criteria.where("status").ne(OrderStatus.PAID));

        assertThat(findIds(filter))
            .containsExactlyInAnyOrder(
                "A-01", "A-03", "A-04",
                "A-06", "A-07", "A-08");
    }

    @Test
    void nestedAndOrNorSelectsOnlyIntendedOrders() {
        Criteria filter = new Criteria().andOperator(
            Criteria.where("tenantId").is("T-A"),
            Criteria.where("active").is(true),
            new Criteria().orOperator(
                Criteria.where("status").is(OrderStatus.NEW),
                Criteria.where("status").is(OrderStatus.PAID)),
            Criteria.where("totalMinor").gte(300L),
            new Criteria().norOperator(
                Criteria.where("status")
                    .is(OrderStatus.CANCELLED),
                Criteria.where("fraud").is(true)));

        assertThat(findIds(filter))
            .containsExactlyInAnyOrder(
                "A-02", "A-08", "A-09");
    }
}
```

Ở đây `OrderStatus`/`OrderDocument` là hai kiểu ở mục 11. Test dùng `MongoTemplate.getCollection("orders")` để chèn BSON thô, nên A-06 có `status: null` còn A-07 thực sự **không có field `status` và `fraud`**.

**Cảnh báo thực thi:** `collection.deleteMany(new Document())` xóa toàn bộ collection `orders` của database mà test đang kết nối. Test phải được cấu hình trỏ tới MongoDB thử nghiệm **cô lập**, chẳng hạn Testcontainers, không được dùng database sản xuất hoặc dùng chung. `@DataMongoTest` cần package import tương ứng với phiên bản Spring Boot thực tế; ví dụ dùng namespace phổ biến trong các phiên bản Spring Boot hỗ trợ.

### 12.2. Test chủ động phát hiện một nhóm OR sai phạm vi

Ví dụ **phản diện**:

```java
Criteria unsafe = new Criteria().orOperator(
    new Criteria().andOperator(
        Criteria.where("tenantId").is("T-A"),
        Criteria.where("status").is(OrderStatus.NEW)),
    Criteria.where("status").is(OrderStatus.PAID));
```

Lỗi nằm ở chỗ nhánh `status = PAID` không có `tenantId = T-A`. Nếu chạy cùng fixture, truy vấn này sẽ nhận **B-01**. Có thể viết kiểm thử negative để cố tình chứng minh sai lệch trước khi sửa:

```java
// PHẢN VÍ DỤ: đây là query sai, chỉ dùng để minh họa lỗi.
assertThat(findIds(unsafe)).contains("B-01");
```

Sau đó sửa bằng cách đặt `tenantId` ở nhóm AND ngoài cùng như test `orGroupStaysInsideTenantScope`. Trong kiểm thử bảo mật, không chỉ assert ID mong muốn xuất hiện; còn phải assert **không có document tenant khác** trong kết quả.

### 12.3. Ma trận bổ sung cho dữ liệu thực

| Tình huống | Kỳ vọng cần xác minh |
| --- | --- |
| `fraud` là BSON Boolean false | Không bị loại bởi `$nor: [{fraud:true}]` |
| `fraud` bị thiếu hoặc null | Phân biệt với false theo chính sách nghiệp vụ |
| `status` bị thiếu | Có thể khớp `$ne`/`$nor`; không khớp allowlist string |
| `status` là String không có trong enum mới | Query MongoDB chạy trên BSON; xử lý reading converter khi đọc kết quả |
| Hai nhóm `$or` cần đồng thời thỏa | Phải được đặt trong `$and`, không ghi trùng key `$or` |
| Nhiều điều kiện trên một phần tử array | `$elemMatch` thay vì chỉ AND trên các dotted paths |
| Input allowlist rỗng | Fail-closed: trả kết quả rỗng hoặc lỗi input, không bỏ lọc |
| OR do người dùng chọn + tenant bắt buộc | Mọi nhánh vẫn thuộc tenant đã được cấp quyền |
| Nhóm `$nor` không có nhánh nào | Service xử lý riêng, không tạo query mơ hồ |
| MongoDB có nhiều dữ liệu | Đo `explain` và số document phải duyệt, không chỉ test tập rất nhỏ |

## 13. Index và chi phí của nhóm OR/NOR

`$and`, `$or` và `$nor` là phép logic. Chúng **không bảo đảm** MongoDB sẽ dùng index theo cùng một cách.

### 13.1. AND và index ghép

Nếu các truy vấn thông thường luôn giới hạn theo `tenantId`, rồi lọc `status` và `totalMinor`, có thể cân nhắc index:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  totalMinor: -1,
  _id: -1
})
```

Đây chỉ là **index ứng viên**. Khi query dùng OR có nhiều giá trị status, hoặc sort khác thứ tự của index, MongoDB có thể phải chạy nhiều nhánh index scan hoặc cần sắp xếp thêm. Hãy kiểm tra kế hoạch trên dataset đại diện, không suy đoán từ tên method Java.

### 13.2. OR và index của từng nhánh

MongoDB có thể tối ưu `$or` bằng index khi các nhánh và điều kiện cho phép. Nếu một nhánh ít chọn lọc hoặc không có index hữu ích, kế hoạch tổng thể có thể phải đọc nhiều document.

Ví dụ:

```javascript
db.orders.find({
  tenantId: "T-A",
  $or: [
    { status: "NEW" },
    { totalMinor: { $gte: NumberLong(900) } }
  ]
})
```

Không nên tin rằng một index trên `status` đơn lẻ làm toàn bộ query này hiệu quả. Cần xem `totalMinor`, tính chọn lọc, thứ tự index và phân bố tenant.

### 13.3. NOR và điều kiện phủ định thường ít chọn lọc

`$nor`, `$ne` và `$nin` có thể khớp phần lớn document, kể cả field thiếu. Một index trên field bị phủ định **không** đảm bảo tập kết quả nhỏ hoặc chi phí thấp.

Nếu yêu cầu nghiệp vụ có tập trạng thái được phép xác định, `$in` với allowlist có thể vừa chặt chẽ hơn vừa dễ tối ưu hơn phủ định một vài giá trị cấm. Tuy nhiên hiệu năng cuối cùng vẫn phải **đo**.

### 13.4. Xem explain

```javascript
db.orders.find({
  tenantId: "T-A",
  active: true,
  $or: [
    { status: "NEW" },
    { status: "PAID" }
  ],
  $nor: [
    { fraud: true },
    { status: "CANCELLED" }
  ]
})
.sort({ totalMinor: -1, _id: -1 })
.limit(20)
.explain("executionStats")
```

Quan sát `totalDocsExamined`, `totalKeysExamined`, `nReturned`, stage index/sort và thời gian thực thi. Một query `find` có thể nhanh trên fixture 10 document nhưng chậm ở hàng triệu document, đặc biệt khi điều kiện phủ định không chọn lọc.

Với `MongoTemplate`/repository, hãy quan sát **câu BSON thực sự gửi xuống driver** bằng command monitoring/log thích hợp khi cần chẩn đoán; `Query.getQueryObject()` trước bước mapping có thể chưa phản ánh đầy đủ tên field BSON và custom conversion.

## 14. Các lựa chọn với repository, @Query và reactive access

`MongoTemplate` phù hợp khi cần dựng nhóm AND/OR/NOR tùy chọn. Tuy nhiên truy vấn tĩnh cũng có thể viết bằng `@Query` của repository:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Query("""
        {
          'tenantId': ?0,
          '$or': [
            { 'status': 'NEW' },
            { 'status': 'PAID' }
          ],
          '$nor': [
            { 'status': 'CANCELLED' },
            { 'fraud': true }
          ]
        }
        """)
    List<OrderDocument> findAllowedNotFlagged(String tenantId);
}
```

Đoạn này giả định có thêm import `MongoRepository` và dùng Java text block (Java 15+). Khi điều kiện thay đổi nhiều theo input, nên viết `Criteria` thay vì tạo hàng loạt biến thể `@Query`. Tên field trong chuỗi và enum BSON cần được kiểm tra theo mapping/configuration của ứng dụng.

Với **reactive access**, `ReactiveMongoTemplate` cũng có thể nhận `Query`/`Criteria`:

```java
import reactor.core.publisher.Flux;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

public Flux<OrderDocument> findByLogicalFilter(
        ReactiveMongoTemplate reactiveTemplate,
        String tenantId) {

    Criteria filter = new Criteria().andOperator(
        Criteria.where("tenantId").is(tenantId),
        new Criteria().orOperator(
            Criteria.where("status").is(OrderStatus.NEW),
            Criteria.where("status").is(OrderStatus.PAID)),
        new Criteria().norOperator(
            Criteria.where("fraud").is(true),
            Criteria.where("status")
                .is(OrderStatus.CANCELLED)));

    return reactiveTemplate.find(
        Query.query(filter), OrderDocument.class);
}
```

Đoạn trên là phương thức đặt trong một service/class Java phù hợp, đã có imports `Criteria`, `Query` và `OrderStatus`. Sử dụng reactive template **không làm đổi ngữ nghĩa MongoDB** và không tự biến query lớn thành rẻ. Kiểm thử reactive bằng `StepVerifier` hoặc công cụ tương đương, xác nhận publisher được subscribe và không có tenant khác xuất hiện.

Việc ghi dữ liệu nhiều document trong transaction hoặc aggregation nhóm báo cáo theo trạng thái là các bài toán khác; sự đúng đắn của phép AND/OR/NOR vẫn cần thiết trong những thao tác đó, nhưng lựa chọn transaction/aggregation không thay thế việc đặt ngoặc logic.

## 15. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query OR trả document tenant khác | `tenantId` chỉ nằm trong một nhánh OR | Đặt tenant trong nhóm AND ngoài cùng và test anti-leak |
| `$nor` trả cả document thiếu `fraud` | Field missing không khớp `fraud:true` | Xác định chính sách cho missing/null; thêm điều kiện tồn tại/allowlist |
| Dùng NOR để phủ định một nhóm AND nhưng loại quá nhiều | Viết `$nor:[A,B]` thay cho `$nor:[{$and:[A,B]}]` | Diễn đạt De Morgan, kiểm thử A đúng/B sai |
| `Criteria.not().orOperator(...)` không hoạt động | `not()` là field-level, không phủ định nhóm OR | Dùng `norOperator(...)` |
| Query chứa hai khóa `$or` | JSON/BSON lặp key hoặc `addCriteria` trùng key | Nhóm hai OR riêng trong `$and` |
| `$ne: "PAID"` trả cả status null/missing | Negation trên giá trị không phải allowlist | Dùng `$in` với trạng thái được phép |
| Lọc array khác với yêu cầu “cùng một phần tử” | Dotted paths có thể khớp các phần tử khác nhau | Dùng `$elemMatch` |
| Query chạy chậm dù đã có index | Nhóm OR/NOR ít chọn lọc, index không phù hợp | Đo `explain` và giới hạn tenant/sort/limit |
| Query mới bỏ sót dữ liệu cũ | Kiểu BSON của field không nhất quán | Kiểm kê schema và migration, kiểm thử BSON raw |
| Điều kiện tùy chọn rỗng mở rộng query | Service tự bỏ allowlist hoặc tạo nhóm rỗng | Fail-closed, validation rõ và không gọi database khi không có quyền |

## 16. Bài tập vận dụng

Một hệ thống đặt vé lưu collection `tickets` với:

- `tenantId`: tenant bắt buộc.
- `status`: `OPEN`, `CONFIRMED`, `CANCELLED`, có thể thiếu trong dữ liệu cũ.
- `priority`: số nguyên.
- `fraudFlag`: boolean.
- `lines`: array các mục vé có `eventCode` và `quantity`.

Hãy triển khai các yêu cầu:

1. Lấy vé tenant T-A thỏa **(status OPEN hoặc CONFIRMED) và priority từ 5 trở lên**.
2. Lấy vé **không** đồng thời có status CONFIRMED và fraudFlag true, nhưng vẫn giới hạn trong tenant T-A.
3. Viết lại câu 2 bằng `$nor` có **một nhóm `$and`**; chứng minh vì sao `$nor` của hai nhánh độc lập là sai.
4. Nếu `fraudFlag` bị thiếu ở một vé cũ, có cho phép vé đó đi qua bộ lọc `$nor:[{fraudFlag:true}]` không? Nêu quyết định nghiệp vụ và query phù hợp.
5. Viết query để tìm vé có **một phần tử lines** với `eventCode="E1"` và `quantity>=2`. So sánh kết quả với AND trên hai dotted paths.
6. Viết integration test với ít nhất một vé tenant khác, một vé thiếu `status` và một vé có `fraudFlag:null`.
7. Đề xuất index cho truy vấn chủ đạo và xem `explain("executionStats")` trên tập dữ liệu đại diện.

**Gợi ý:** ở câu 1, đặt `tenantId` ngoài cùng, thêm `new Criteria().orOperator(...)` cho status và `priority>=5` trong `andOperator(...)`. Ở câu 2, dùng `norOperator(new Criteria().andOperator(...))`. Với array, `elemMatch` diễn đạt “cùng một phần tử”. Không coi `fraudFlag` missing tương đương xác minh false nếu nghiệp vụ không nói như vậy.

## 17. Tài liệu tham khảo

- Spring Data MongoDB — [Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Query`, `Criteria`, toán tử và `MongoTemplate`.
- Spring Data MongoDB — [Criteria API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html): `andOperator`, `orOperator`, `norOperator` và `not`.
- MongoDB Manual — [`$and`](https://www.mongodb.com/docs/manual/reference/operator/query/and/), [`$or`](https://www.mongodb.com/docs/manual/reference/operator/query/or/), [`$nor`](https://www.mongodb.com/docs/manual/reference/operator/query/nor/) và [`$not`](https://www.mongodb.com/docs/manual/reference/operator/query/not/).
- MongoDB Manual — [`$elemMatch`](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/): nhiều điều kiện phải thỏa trong cùng phần tử mảng.
- MongoDB Manual — [`$exists`](https://www.mongodb.com/docs/manual/reference/operator/query/exists/): phân biệt field tồn tại với field thiếu.

## Ghi nhớ

**AND** có thể ngầm định giữa các field hoặc diễn đạt bằng `$and`; **OR** chọn document thỏa ít nhất một nhánh; **NOR** phủ định **toàn bộ OR**; còn **`$not` chỉ phủ định điều kiện của một field**. Đừng nhầm `NOT(A AND B)` với `NOT(A OR B)`. Luôn đặt **tenant và các điều kiện bắt buộc trong nhóm AND bên ngoài**, xử lý null/missing bằng quy ước nghiệp vụ rõ ràng, dùng `$elemMatch` cho các điều kiện cùng phần tử mảng, kiểm thử với BSON thực và đo index trước khi đưa query vào sản xuất.
