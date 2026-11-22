# Điều kiện tập phần tử với $all, $in và $nin trong truy vấn mảng MongoDB

## 1. Bài toán: tìm document dựa trên các phần tử trong mảng

MongoDB lưu dữ liệu dưới dạng document BSON. Một field trong document có thể là mảng chứa nhiều phần tử cùng kiểu hoặc khác kiểu. Ví dụ, hệ thống nội dung lưu các nhãn (**tags**) gắn với bài viết:

~~~javascript
{
  _id: "A01",
  title: "MongoDB với Java",
  tags: ["mongodb", "java", "backend"]
}
~~~

Từ dữ liệu này, ứng dụng có thể đặt ra ba yêu cầu rất khác nhau:

1. **Bài viết phải có cả nhãn mongodb và java.**
2. **Bài viết có ít nhất một trong các nhãn mongodb hoặc java.**
3. **Bài viết không được có nhãn blocked hoặc spam.**

MongoDB cung cấp ba toán tử truy vấn thường dùng để diễn đạt các điều kiện trên:

- **$all:** field mảng chứa **tất cả** các giá trị được yêu cầu.
- **$in:** field có giá trị bằng **ít nhất một** giá trị trong danh sách; với field mảng, **ít nhất một phần tử** phải khớp.
- **$nin:** field **không khớp bất kỳ** giá trị nào trong danh sách; với field mảng, **không phần tử nào** được khớp. Toán tử này cũng khớp các document **không có field** được truy vấn.

Ba toán tử đều có cú pháp là một **mảng các giá trị điều kiện**, nhưng ngữ nghĩa khác nhau. Đặc biệt, **$in** và **$nin** không chỉ dùng cho field mảng: chúng còn dùng được với field đơn trị.

~~~text
                 Truy vấn field tags
                          |
             +------------+------------+
             |            |            |
            $all         $in          $nin
             |            |            |
        CẦN ĐỦ các    CẦN ÍT NHẤT    KHÔNG ĐƯỢC
        phần tử       MỘT phần tử    KHỚP phần tử
             |            |            |
          AND theo      OR theo       NOT IN theo
          thành viên    thành viên    thành viên
~~~

Mục tiêu của bài học là sử dụng chính xác ba toán tử trong truy vấn mảng, xử lý các trường hợp thiếu field, mảng rỗng, null và phần tử lồng nhau; sau đó áp dụng trong MongoDB Shell và ứng dụng Java/Spring Data.

## 2. Chuẩn bị bộ dữ liệu dùng xuyên suốt bài

Trong **mongosh**, chọn database riêng để thử nghiệm:

~~~javascript
use array_query_lab
~~~

Chạy một lần trên collection **articles** chưa có các **_id** bên dưới:

~~~javascript
db.articles.insertMany([
  {
    _id: "A01",
    tenantId: "T1",
    title: "MongoDB for Java",
    tags: ["mongodb", "java", "backend"]
  },
  {
    _id: "A02",
    tenantId: "T1",
    title: "MongoDB for Node.js",
    tags: ["mongodb", "node"]
  },
  {
    _id: "A03",
    tenantId: "T1",
    title: "Java Backend",
    tags: ["java", "backend"]
  },
  {
    _id: "A04",
    tenantId: "T1",
    title: "MongoDB tags repeated",
    tags: ["mongodb", "java", "mongodb"]
  },
  {
    _id: "A05",
    tenantId: "T1",
    title: "Empty tags",
    tags: []
  },
  {
    _id: "A06",
    tenantId: "T1",
    title: "Tags missing"
  },
  {
    _id: "A07",
    tenantId: "T1",
    title: "Null tags",
    tags: null
  },
  {
    _id: "A08",
    tenantId: "T1",
    title: "Legacy scalar tag",
    tags: "mongodb"
  },
  {
    _id: "A09",
    tenantId: "T1",
    title: "Blocked article",
    tags: ["mongodb", "blocked"]
  },
  {
    _id: "A10",
    tenantId: "T1",
    title: "MongoDB and Python",
    tags: ["mongodb", "python"]
  }
]);
~~~

**Lưu ý:** Chạy lại lệnh **insertMany** với các **_id** trùng sẽ gây lỗi **duplicate key**. Nếu cần thử lại từ đầu, sử dụng database/collection lab mới hoặc chủ động dọn dữ liệu thử nghiệm của mình. Không chạy lệnh xóa collection trên hệ thống thật.

### 2.1. Đọc nhanh dữ liệu

~~~javascript
db.articles.find(
  { tenantId: "T1" },
  { _id: 1, title: 1, tags: 1 }
).sort({ _id: 1 });
~~~

Những trường hợp cần ghi nhớ:

| Document | Giá trị **tags** | Ý nghĩa |
|---|---|---|
| A01 | **["mongodb", "java", "backend"]** | Có cả mongodb và java. |
| A02 | **["mongodb", "node"]** | Có mongodb, không có java. |
| A03 | **["java", "backend"]** | Có java, không có mongodb. |
| A04 | **["mongodb", "java", "mongodb"]** | Có phần tử trùng lặp. |
| A05 | **[]** | Có field tags nhưng mảng rỗng. |
| A06 | **không có field tags** | Field missing. |
| A07 | **null** | Field tồn tại với giá trị BSON null. |
| A08 | **"mongodb"** | Field đơn trị kiểu string, không phải mảng. |
| A09 | **["mongodb", "blocked"]** | Có nhãn bị chặn. |
| A10 | **["mongodb", "python"]** | Có nhãn python. |

Bộ dữ liệu cố ý có những giá trị không theo schema mong muốn để minh họa tác động của từng toán tử. Trong ứng dụng production, nên cân nhắc **schema validation** để field tags luôn là mảng string thay vì lẫn null, scalar và missing.

## 3. $all: yêu cầu có đầy đủ phần tử

### 3.1. Cú pháp

~~~javascript
db.collection.find({
  arrayField: {
    $all: [requiredValue1, requiredValue2]
  }
});
~~~

Với mảng giá trị thông thường, **$all** yêu cầu field chứa **tất cả** các giá trị được liệt kê, không phụ thuộc thứ tự xuất hiện trong mảng và không cấm các phần tử khác.

Ví dụ tìm bài viết có cả mongodb và java:

~~~javascript
db.articles.find(
  {
    tenantId: "T1",
    tags: { $all: ["mongodb", "java"] }
  },
  { _id: 1, tags: 1 }
);
~~~

**Kết quả theo bộ dữ liệu mẫu:** **A01** và **A04**.

| Document | Có mongodb? | Có java? | Khớp $all? |
|---|---|---|---|
| A01 | Có | Có | Có |
| A02 | Có | Không | Không |
| A03 | Không | Có | Không |
| A04 | Có | Có | Có |
| A09 | Có | Không | Không |
| A10 | Có | Không | Không |

Trong A01, nhãn **backend** xuất hiện thêm nhưng không làm document bị loại. **$all không diễn đạt “mảng chỉ được chứa đúng những phần tử này”**.

### 3.2. Thứ tự phần tử không ảnh hưởng

Hai điều kiện sau có cùng ý nghĩa đối với mảng string:

~~~javascript
db.articles.find({
  tags: { $all: ["mongodb", "java"] }
});

db.articles.find({
  tags: { $all: ["java", "mongodb"] }
});
~~~

Mảng trong document có thể lưu nhãn theo thứ tự bất kỳ; **$all** kiểm tra khả năng chứa giá trị, không kiểm tra vị trí.

Nếu nghiệp vụ cần so sánh **chính xác thứ tự và nội dung mảng**, sử dụng điều kiện so khớp toàn mảng phù hợp:

~~~javascript
db.articles.find({
  tags: ["mongodb", "java"]
});
~~~

Query này yêu cầu mảng tương ứng với thứ tự được nêu, nên không có nghĩa tương đương với **$all**. Ví dụ A01 có nhãn **backend** đi kèm nên không khớp toàn mảng hai phần tử đó.

### 3.3. Phần tử trùng không tạo yêu cầu về số lần xuất hiện

~~~javascript
db.articles.find({
  tags: { $all: ["mongodb", "mongodb"] }
});
~~~

**$all không đếm số lần lặp của một phần tử.** Điều kiện này yêu cầu phần tử mongodb xuất hiện, không phải xuất hiện ít nhất hai lần. Vì vậy A01 có một nhãn mongodb vẫn đáp ứng; A04 có hai nhãn mongodb cũng đáp ứng.

Nếu nghiệp vụ thực sự cần kiểm đếm hoặc đặt điều kiện về số lần lặp, phải dùng logic khác như aggregation với **$filter/$size** hoặc thiết kế lại mô hình dữ liệu để lưu số lượng rõ ràng.

### 3.4. Một giá trị trong $all

~~~javascript
db.articles.find({
  tags: { $all: ["java"] }
});
~~~

Với field mảng string, toán tử này yêu cầu mảng chứa java. Kết quả mẫu: A01, A03 và A04. Nếu truy vấn đơn giản chỉ cần kiểm tra phần tử java:

~~~javascript
db.articles.find({
  tags: "java"
});
~~~

Điều kiện equality trên field mảng cũng có thể tìm document chứa phần tử tương ứng. Tuy nhiên, equality còn có semantics đối với field đơn trị; nếu dữ liệu trộn scalar và array, cần chủ động quyết định loại tài liệu nào được chấp nhận.

### 3.5. $all với danh sách trống

~~~javascript
db.articles.find({
  tags: { $all: [] }
});
~~~

**$all: [] không khớp document nào** trong MongoDB. Đừng suy luận toán tử này theo quy tắc toán học “mọi tập đều chứa tập rỗng”.

Điều này quan trọng khi UI cho phép người dùng chọn nhãn “phải có tất cả”:

- Người dùng chọn 2 nhãn: tạo điều kiện **$all** với 2 giá trị.
- Người dùng chọn 0 nhãn: phải quyết định nghiệp vụ là **không lọc theo nhãn** hay **không trả kết quả**.
- Nếu ý định là “không lọc”, hãy **bỏ điều kiện $all khỏi query** khi đầu vào rỗng, thay vì truyền **$all: []**.

### 3.6. $all không thay thế mọi kiểu điều kiện AND

**$all** kiểm tra **sự hiện diện của những giá trị** trong một field mảng. Nó không tự diễn đạt các phép toán như:

- Mọi phần tử phải có giá trị lớn hơn 0;
- Mọi phần tử phải thuộc danh sách được phép;
- Hai điều kiện phải xảy ra **trên cùng một object con**;
- Mảng phải có kích thước chính xác.

Các yêu cầu đó có thể cần **$elemMatch**, **$not**, **$size**, **$expr**, hoặc aggregation và schema validation.

## 4. $in: ít nhất một giá trị phù hợp

### 4.1. Cú pháp

~~~javascript
db.collection.find({
  field: {
    $in: [value1, value2, value3]
  }
});
~~~

Với field mảng, **$in** khớp document nếu **ít nhất một phần tử của mảng** bằng một giá trị trong danh sách điều kiện. Với field scalar, nó khớp nếu **giá trị scalar** thuộc danh sách.

Ví dụ tìm bài viết có **mongodb hoặc java**:

~~~javascript
db.articles.find(
  {
    tenantId: "T1",
    tags: { $in: ["mongodb", "java"] }
  },
  { _id: 1, tags: 1 }
).sort({ _id: 1 });
~~~

**Kết quả theo bộ dữ liệu mẫu:** **A01, A02, A03, A04, A08, A09, A10**.

Tại sao có **A08**? Vì **tags** của A08 là string **"mongodb"**, không phải mảng, nhưng **$in** vẫn có thể so sánh một field scalar với các giá trị được liệt kê.

### 4.2. $in là OR giữa các lựa chọn

Đối với điều kiện đơn giản trên cùng field:

~~~javascript
db.articles.find({
  $or: [
    { tags: "mongodb" },
    { tags: "java" }
  ]
});
~~~

về ý nghĩa lựa chọn giá trị tương đương với:

~~~javascript
db.articles.find({
  tags: { $in: ["mongodb", "java"] }
});
~~~

**$in** thường ngắn gọn và dễ sinh query hơn khi cần chọn nhiều giá trị của **cùng một field**. Không nên dùng **$in** khi nghiệp vụ yêu cầu phải có **cả hai** giá trị, vì đó là điều kiện của **$all**.

### 4.3. $in trên một field đơn trị

Giả sử document có **status**:

~~~javascript
{
  _id: "P01",
  status: "ACTIVE",
  tags: ["mongodb", "java"]
}
~~~

Ứng dụng có thể lọc:

~~~javascript
db.products.find({
  status: { $in: ["ACTIVE", "DRAFT"] }
});
~~~

Lúc này **status** là string đơn trị. **$in** chỉ kiểm tra status có bằng ACTIVE hay DRAFT không. Vì vậy tên bài học tập trung vào truy vấn mảng nhưng cần nhớ toán tử **$in** có phạm vi dùng rộng hơn.

### 4.4. Mảng giá trị đầu vào rỗng

~~~javascript
db.articles.find({
  tags: { $in: [] }
});
~~~

**$in: [] không khớp document nào**, vì không có giá trị được phép để so khớp.

Với bộ lọc nhiều lựa chọn ở UI, một danh sách rỗng có thể mang hai ý nghĩa nghiệp vụ:

- **Không chọn nhãn nào, vì vậy không lọc theo nhãn:** bỏ điều kiện **$in**.
- **Không giá trị nào được chấp nhận:** giữ **$in: []** để nhận kết quả rỗng.

Phân biệt hai ý nghĩa này ngay ở lớp xử lý request, thay vì để MongoDB quyết định UX.

### 4.5. Sử dụng regular expression trong $in

MongoDB hỗ trợ biểu thức chính quy dạng regex literal trong danh sách **$in**:

~~~javascript
db.articles.find({
  tags: {
    $in: [/^mongo/i, "java"]
  }
});
~~~

Điều này cho phép khớp một phần tử bắt đầu bằng **mongo** (không phân biệt hoa/thường theo cờ **i**) hoặc phần tử bằng **java**. Khi dùng regex trong **$in**, phải dùng biểu thức regex theo cú pháp được hỗ trợ; không tự nhét một document **{$regex: "..."}** như một phần tử của danh sách và cho rằng có cùng ngữ nghĩa.

Regex có chi phí truy vấn phụ thuộc pattern/index. Không nên cho người dùng gửi trực tiếp pattern regex không giới hạn độ dài hay độ phức tạp vào query production.

### 4.6. Danh sách $in quá dài có thể gây tốn kém

Ví dụ:

~~~javascript
db.articles.find({
  tags: { $in: largeListOfThousandsOfTags }
});
~~~

Một danh sách hàng nghìn hoặc hàng chục nghìn lựa chọn có thể làm tăng chi phí parse, planning và tìm kiếm index. Không có một con số tối ưu cố định cho mọi cluster. Với truy vấn thường xuyên, nên giữ danh sách ở quy mô hợp lý, giới hạn input từ client và đo bằng **explain("executionStats")**.

## 5. $nin: loại trừ danh sách giá trị

### 5.1. Cú pháp

~~~javascript
db.collection.find({
  field: {
    $nin: [blockedValue1, blockedValue2]
  }
});
~~~

Với field mảng, **$nin** chọn document khi **không phần tử nào** của field khớp một giá trị bị loại. Với field đơn trị, nó chọn document khi giá trị không nằm trong danh sách.

Ví dụ loại mọi bài viết chứa nhãn **blocked** hoặc **python**:

~~~javascript
db.articles.find(
  {
    tenantId: "T1",
    tags: { $nin: ["blocked", "python"] }
  },
  { _id: 1, tags: 1 }
).sort({ _id: 1 });
~~~

**Kết quả theo bộ dữ liệu mẫu:** **A01, A02, A03, A04, A05, A06, A07, A08**.

**A09** bị loại vì có blocked, **A10** bị loại vì có python. Điều đáng chú ý là:

- **A05** có **tags: []** nên không chứa nhãn nào bị cấm.
- **A06** **không có field tags** nhưng vẫn khớp **$nin**.
- **A07** có **tags: null**, không bằng blocked hoặc python, nên vẫn khớp.
- **A08** là string mongodb, không thuộc danh sách bị cấm, nên vẫn khớp.

### 5.2. $nin khớp document thiếu field

Đây là khác biệt cần nhớ kỹ:

~~~javascript
db.articles.find({
  tags: { $nin: ["blocked"] }
});
~~~

Document **A06** thiếu field tags vẫn được trả về. MongoDB quy định **$nin** chọn cả document có field **không tồn tại**. Nếu nghiệp vụ “chỉ nhận những bài viết có danh sách tags hợp lệ và không chứa blocked”, điều kiện trên **chưa đủ**.

Yêu cầu field tồn tại:

~~~javascript
db.articles.find({
  tags: {
    $exists: true,
    $nin: ["blocked", "python"]
  }
});
~~~

Điều kiện này loại **A06** nhưng **vẫn có thể giữ A07** vì **null** là giá trị của một field đang tồn tại; đồng thời giữ A08 vì là scalar.

Nếu schema yêu cầu **tags luôn là array**:

~~~javascript
db.articles.find({
  tags: {
    $type: "array",
    $nin: ["blocked", "python"]
  }
});
~~~

Trong bộ dữ liệu mẫu, kết quả khi thêm **$type: "array"** là **A01, A02, A03, A04, A05**. A06 thiếu field, A07 là null, A08 là string nên không khớp. **A05** vẫn khớp vì mảng rỗng là mảng hợp lệ về kiểu, dù chưa chắc hợp lệ về nghiệp vụ.

### 5.3. $nin là NOT IN, không phải yêu cầu chứa phần tử khác

So sánh:

~~~javascript
// Không được có phần tử blocked.
db.articles.find({
  tags: { $nin: ["blocked"] }
});

// Phải có ít nhất một phần tử khác blocked.
db.articles.find({
  tags: { $elemMatch: { $ne: "blocked" } }
});
~~~

Hai truy vấn này **không tương đương**. Một mảng **["mongodb", "blocked"]** có phần tử khác blocked nên có thể khớp truy vấn thứ hai, nhưng vẫn bị loại bởi **$nin**. Muốn diễn đạt **“không có bất kỳ phần tử nào bị cấm”**, dùng **$nin** là tự nhiên hơn.

### 5.4. $nin với danh sách rỗng

~~~javascript
db.articles.find({
  tags: { $nin: [] }
});
~~~

**$nin: []** không loại giá trị nào, do đó khớp mọi document theo điều kiện field này, bao gồm document thiếu field. Nó khác hoàn toàn **$in: []** và **$all: []**.

### 5.5. Loại trừ nhiều trạng thái đơn trị

~~~javascript
db.orders.find({
  status: { $nin: ["CANCELLED", "DELETED"] }
});
~~~

Nếu một đơn hàng **thiếu status**, nó cũng có thể được chọn. Khi nghiệp vụ chỉ nhận các trạng thái đã biết, một **allowlist bằng $in** thường dễ kiểm soát hơn:

~~~javascript
db.orders.find({
  status: { $in: ["NEW", "PAID", "SHIPPED"] }
});
~~~

Chọn **allowlist** hay **denylist** tùy domain. Với dữ liệu không đồng nhất hoặc field có thể thiếu, denylist **$nin** dễ tạo ra kết quả rộng hơn dự kiến.

## 6. So sánh trực tiếp $all, $in và $nin

Xét danh sách **["mongodb", "java"]** và field tags:

| Toán tử | Câu hỏi | Mô hình điều kiện | Với mảng **["mongodb", "java", "backend"]** |
|---|---|---|---|
| **$all: ["mongodb", "java"]** | Có **đủ cả hai** không? | AND giữa các yêu cầu hiện diện. | Khớp. |
| **$in: ["mongodb", "java"]** | Có **ít nhất một** không? | OR giữa các giá trị được phép. | Khớp. |
| **$nin: ["mongodb", "java"]** | Có **hoàn toàn không chứa** hai giá trị này không? | Không phần tử nào thuộc danh sách. | Không khớp. |

### 6.1. Bảng kết quả đầy đủ trên dữ liệu lab

| _id | **$all: ["mongodb","java"]** | **$in: ["mongodb","java"]** | **$nin: ["blocked","python"]** |
|---|---|---|---|
| A01 | Có | Có | Có |
| A02 | Không | Có | Có |
| A03 | Không | Có | Có |
| A04 | Có | Có | Có |
| A05 | Không | Không | Có |
| A06 | Không | Không | Có |
| A07 | Không | Không | Có |
| A08 | Không | Có | Có |
| A09 | Không | Có | Không |
| A10 | Không | Có | Không |

Phân biệt **A05**, **A06** và **A07** đặc biệt hữu ích trong thực tế: array rỗng, field missing và giá trị null **không cùng một trạng thái**, dù cùng bị loại bởi những ví dụ **$all/$in** ở trên.

### 6.2. Trường hợp danh sách điều kiện rỗng

| Điều kiện | Kết quả |
|---|---|
| **{tags: {$all: []}}** | Không khớp document nào. |
| **{tags: {$in: []}}** | Không khớp document nào. |
| **{tags: {$nin: []}}** | Khớp tất cả document, kể cả khi tags thiếu. |

Không tự động đưa cả ba toán tử vào query với một array rỗng khi người dùng chưa chọn filter. Cần xác định rõ hành vi mong muốn tại API.

### 6.3. Nên chọn toán tử nào?

~~~text
Tìm ứng viên có tất cả kỹ năng yêu cầu
    -> skills: {$all: requiredSkills}

Tìm sản phẩm thuộc bất kỳ nhóm ưu tiên
    -> categories: {$in: selectedCategories}

Ẩn bài có bất kỳ nhãn cấm nào
    -> tags: {$nin: forbiddenTags}

Tìm bài có danh sách nhãn hợp lệ và không nhãn cấm
    -> tags: {$type: "array", $nin: forbiddenTags}
~~~

**$all = phải có đủ**, **$in = được có một trong**, **$nin = không được có bất cứ giá trị nào bị liệt kê**. Đây là cách ghi nhớ nhanh, nhưng vẫn phải xem kiểu field và trường hợp thiếu field.

## 7. Truy vấn kết hợp: phải có A/B và không có C

Nhiều bài toán cần đồng thời cả điều kiện bao gồm và điều kiện loại trừ.

### 7.1. Có cả mongodb và java, không có blocked

MongoDB không cho phép đặt cùng lúc hai khóa **$all** và **$nin** hai lần trong cùng một document JSON mà ghi đè nhau. Cách rõ ràng là dùng **$and**:

~~~javascript
db.articles.find({
  tenantId: "T1",
  $and: [
    { tags: { $all: ["mongodb", "java"] } },
    { tags: { $nin: ["blocked"] } }
  ]
});
~~~

Theo dữ liệu mẫu, A01 và A04 khớp. Nếu A01 có thêm blocked thì dù có đủ nhãn yêu cầu, nó vẫn bị loại.

Với các toán tử khác tên, có thể kết hợp trong cùng object điều kiện field:

~~~javascript
db.articles.find({
  tenantId: "T1",
  tags: {
    $all: ["mongodb", "java"],
    $nin: ["blocked"]
  }
});
~~~

Hai cách trên đều dễ hiểu. **$and** có ích khi điều kiện được xây dựng động từ các module lọc độc lập, hoặc phải áp đặt nhiều biểu thức trên cùng field.

### 7.2. Có mongodb hoặc java, nhưng không có python

~~~javascript
db.articles.find({
  tenantId: "T1",
  tags: {
    $in: ["mongodb", "java"],
    $nin: ["python"]
  }
});
~~~

Điều kiện bao gồm yêu cầu **ít nhất một** nhãn ưu tiên; điều kiện loại trừ yêu cầu **không chứa python**. A10 có mongodb nhưng cũng có python nên bị loại.

### 7.3. Kết hợp với điều kiện khác

~~~javascript
db.articles.find({
  tenantId: "T1",
  status: { $in: ["PUBLISHED", "SCHEDULED"] },
  tags: { $all: ["mongodb", "java"] }
});
~~~

Ví dụ này giả định collection có thêm **status**. Nếu sử dụng chính dữ liệu lab ở Mục 2, document thiếu status nên không khớp **$in** đó. Mục đích là minh họa việc kết hợp một điều kiện **mảng** với một điều kiện **scalar**.

### 7.4. Khi nào dùng $or thay vì $in?

Nếu các lựa chọn áp dụng cho **những field khác nhau**, **$or** mới là cách diễn đạt thích hợp:

~~~javascript
db.articles.find({
  $or: [
    { tags: { $in: ["mongodb", "java"] } },
    { category: "DATABASE" }
  ]
});
~~~

Không thể thay điều kiện này bằng **$in** trên tags, vì một nhánh dựa trên **category**.

## 8. Mảng object: điều kiện phải nằm trên cùng phần tử hay không?

Cho collection **orders** với các dòng hàng:

~~~javascript
db.orders.insertMany([
  {
    _id: "O01",
    tenantId: "T1",
    items: [
      { sku: "A", qty: NumberInt(1), color: "red" },
      { sku: "B", qty: NumberInt(10), color: "blue" }
    ]
  },
  {
    _id: "O02",
    tenantId: "T1",
    items: [
      { sku: "A", qty: NumberInt(5), color: "blue" }
    ]
  },
  {
    _id: "O03",
    tenantId: "T1",
    items: [
      { sku: "A", qty: NumberInt(5), color: "red" },
      { sku: "B", qty: NumberInt(2), color: "green" }
    ]
  }
]);
~~~

### 8.1. Dotted path có thể khớp nhiều phần tử khác nhau

~~~javascript
db.orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 5 }
});
~~~

Truy vấn này có thể khớp **O01**, dù hàng A của O01 chỉ có qty = 1, bởi điều kiện **sku = A** khớp phần tử thứ nhất và điều kiện **qty >= 5** khớp phần tử thứ hai (sku B, qty = 10).

Nếu yêu cầu là **một dòng hàng có sku = A và qty >= 5**, phải ràng buộc điều kiện vào **cùng một phần tử**.

### 8.2. Dùng $elemMatch cho cùng một embedded document

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 5 }
    }
  }
});
~~~

Trong dữ liệu mẫu, truy vấn này khớp **O02** và **O03**, không khớp O01.

**$elemMatch** diễn đạt “tồn tại ít nhất một phần tử của mảng thỏa tất cả điều kiện được đặt trong đó”.

### 8.3. $in trên field của object trong mảng

~~~javascript
db.orders.find({
  "items.sku": { $in: ["A", "C"] }
});
~~~

Ở đây **items.sku** là đường dẫn tới field **sku** của các object nằm trong mảng **items**. Query khớp nếu một trong các giá trị sku thuộc danh sách A/C. Cả O01, O02 và O03 đều có A.

Với loại dữ liệu này, **$in** vẫn là điều kiện **ít nhất một giá trị phù hợp**, không có ngữ nghĩa về cùng phần tử với điều kiện ở field khác.

### 8.4. $all với dotted path

~~~javascript
db.orders.find({
  "items.sku": { $all: ["A", "B"] }
});
~~~

Truy vấn tìm order có **cả SKU A và SKU B** ở những item của nó. Theo dữ liệu mẫu, **O01** và **O03** khớp, O02 không.

Điều kiện này khác với câu hỏi “một item vừa có sku A vừa có sku B”, vì một field sku đơn trị không thể bằng cả hai giá trị khác nhau trong cùng một phần tử.

### 8.5. Kết hợp $all với nhiều $elemMatch để yêu cầu nhiều loại phần tử

Ví dụ cần order có:

- **Một item sku = A và qty >= 2**;
- **Một item sku = B và qty >= 2**.

~~~javascript
db.orders.find({
  items: {
    $all: [
      {
        $elemMatch: {
          sku: "A",
          qty: { $gte: 2 }
        }
      },
      {
        $elemMatch: {
          sku: "B",
          qty: { $gte: 2 }
        }
      }
    ]
  }
});
~~~

Kết quả mẫu là **O03**. O01 có B với qty = 10 nhưng A chỉ có qty = 1, còn O02 thiếu B.

Cú pháp **$all** với nhiều biểu thức **$elemMatch** hữu ích khi phải thỏa nhiều nhóm điều kiện ở **các phần tử mảng**, mỗi nhóm có thể áp dụng cho một phần tử riêng. Nó khác **một $elemMatch với nhiều điều kiện**, vốn yêu cầu **cùng một phần tử** thỏa cả nhóm.

### 8.6. So sánh object nguyên vẹn khác với so khớp theo field

Với mảng embedded documents, một điều kiện equality trên **toàn object** có các quy tắc so khớp BSON riêng, bao gồm cấu trúc và thứ tự field. Không nên dùng danh sách object trong **$in/$all** như một cách thay thế chung cho các điều kiện theo thuộc tính.

Ví dụ muốn tìm item có **sku = A** và **qty >= 5**, dùng **$elemMatch** như trên, thay vì thử so sánh một object literal chứa thiếu field:

~~~javascript
// Không phải cách diễn đạt tổng quát cho "item A có qty >= 5".
db.orders.find({
  items: {
    $in: [{ sku: "A", qty: 5 }]
  }
});
~~~

Object trong **$in** ở ví dụ này đại diện một giá trị cụ thể để so khớp, không phải một biểu thức điều kiện khoảng cho qty. Với embedded documents, nên ưu tiên **dotted path + $elemMatch** theo semantics nghiệp vụ.

## 9. Mảng lồng nhau và giới hạn trực giác “tập hợp”

Một field mảng có thể chứa **mảng khác**:

~~~javascript
{
  _id: "N01",
  groups: [
    ["admin", "write"],
    ["reader", "view"]
  ]
}
~~~

Khi yêu cầu khớp một **mảng con như một phần tử**, cách truy vấn cần phân biệt rõ **mảng ngoài** và **giá trị mảng con**. Không nên giả định một mảng lồng nhau được tự động “trải phẳng” thành tập tất cả phần tử ở mọi độ sâu.

MongoDB hỗ trợ so khớp giá trị mảng lồng nhau qua một số biểu thức equality, **$all** và **$elemMatch**, nhưng có những quy tắc đặc biệt khi giá trị điều kiện cũng là array. Vì vậy, trước khi dựa vào một kiểu truy vấn array-of-arrays phức tạp, nên tạo dữ liệu đại diện và kiểm tra kết quả theo đúng phiên bản server.

Nếu nghiệp vụ cần thao tác trên **nhóm quyền**, đôi khi mô hình rõ hơn là:

~~~javascript
{
  _id: "N01",
  groups: [
    { name: "admin", permissions: ["write"] },
    { name: "reader", permissions: ["view"] }
  ]
}
~~~

Khi đó có thể truy vấn:

~~~javascript
db.accounts.find({
  groups: {
    $elemMatch: {
      name: "admin",
      permissions: { $in: ["write", "delete"] }
    }
  }
});
~~~

Điều kiện được nêu rõ: một nhóm tên admin có **ít nhất một permission** thuộc write/delete. Cấu trúc document hợp lý giúp query dễ hiểu hơn việc cố “ép” array-of-arrays vào cú pháp tập hợp.

## 10. Missing, null, array rỗng và dữ liệu sai kiểu

Các toán tử truy vấn mảng rất dễ gây nhầm lẫn khi dữ liệu có schema không đồng nhất.

### 10.1. Bốn trạng thái khác nhau

~~~javascript
{ _id: "X1", tags: ["a", "b"] }
{ _id: "X2", tags: [] }
{ _id: "X3", tags: null }
{ _id: "X4" }
~~~

Chúng lần lượt biểu diễn:

1. Field là mảng có phần tử;
2. Field là mảng rỗng;
3. Field tồn tại với giá trị null;
4. Field không tồn tại.

Nếu nghiệp vụ yêu cầu **tags** là mảng hợp lệ, chỉ dùng **$exists: true** chưa đủ vì null và scalar cũng là field đang tồn tại.

### 10.2. Kết hợp $type để chặn sai kiểu

~~~javascript
db.articles.find({
  tags: {
    $type: "array",
    $nin: ["blocked"]
  }
});
~~~

Điều kiện này kiểm tra đồng thời field là array và không có phần tử blocked. Nhờ vậy, document có tags missing/null/scalar sẽ bị loại.

Nếu nghiệp vụ còn yêu cầu array **không rỗng**, có thể thêm điều kiện kích thước khác với null/missing. Ví dụ kiểm tra tồn tại phần tử ở chỉ số 0:

~~~javascript
db.articles.find({
  "tags.0": { $exists: true },
  tags: { $nin: ["blocked"] }
});
~~~

Đường dẫn **tags.0** có thể biểu diễn sự tồn tại phần tử đầu tiên trong cấu trúc mảng. Cần kết hợp schema validation nếu dữ liệu có thể bị trộn kiểu hoặc các field có tên đặc biệt.

### 10.3. Lưu ý về null trong bộ lọc giá trị

MongoDB có **quy tắc so khớp null** liên quan đến document thiếu field ở một số dạng điều kiện. Khi xây dựng query có **null** trong danh sách **$in/$nin**, không nên dựa vào trực giác của SQL **IN/NOT IN** rồi suy đoán kết quả.

Nếu câu hỏi là **“field này bắt buộc tồn tại và phải là mảng string hợp lệ”**, hãy dùng schema validation và điều kiện kiểu rõ ràng; kiểm thử riêng trường hợp field missing/null. Đặc biệt **$nin** luôn cần được xem xét cẩn thận vì nó có thể bao gồm document thiếu field.

### 10.4. Không coi mảng là tập hợp toán học hoàn toàn

MongoDB **array là dãy phần tử có thứ tự**, có thể chứa phần tử trùng và nhiều kiểu BSON. **$all/$in/$nin** mang ngữ nghĩa kiểm tra các giá trị trong dãy, chứ không biến mảng thành kiểu dữ liệu **set** thực sự.

Ví dụ:

~~~javascript
{
  tags: ["mongodb", "mongodb", "java"]
}
~~~

Document này có ba phần tử, trong đó mongodb xuất hiện hai lần. Điều kiện **$all: ["mongodb", "java"]** khớp nhưng không cho biết số lần xuất hiện. Cần validation/logic update để ngăn trùng nếu nghiệp vụ coi tags là tập không trùng phần tử.

## 11. Phân biệt $all với $size và so khớp toàn mảng

Ba yêu cầu dưới đây khác nhau:

| Yêu cầu | Cách biểu diễn |
|---|---|
| Có **cả a và b**, cho phép giá trị khác. | **{tags: {$all: ["a","b"]}}** |
| Mảng có **đúng 2 phần tử**, không quan tâm phần tử nào. | **{tags: {$size: 2}}** |
| Mảng bằng **["a","b"] theo đúng thứ tự**. | **{tags: ["a","b"]}** |

Kết hợp **$all** và **$size** khi muốn có đủ các nhãn được yêu cầu và giới hạn tổng số phần tử:

~~~javascript
db.articles.find({
  tags: {
    $all: ["mongodb", "java"],
    $size: 2
  }
});
~~~

Với mảng string gồm hai giá trị khác nhau, điều kiện này chỉ nhận mảng chứa đúng mongodb và java theo bất kỳ thứ tự nào, không có phần tử thứ ba. Trong bộ dữ liệu mẫu **A01** có thêm backend, **A04** có phần tử mongodb lặp nên đều không khớp.

**$size** dùng để so sánh kích thước mảng với một giá trị cụ thể; nếu cần điều kiện kích thước theo khoảng hoặc xử lý trường hợp thiếu field, có thể cần aggregation **$expr/$size** cùng bước kiểm soát kiểu dữ liệu.

## 12. Dùng $all, $in và $nin với giá trị BSON đúng kiểu

MongoDB so khớp theo semantics BSON, bao gồm loại dữ liệu và quy tắc so sánh. Điều kiện trên mảng **ObjectId** phải dùng ObjectId thích hợp; đừng dùng string hex và mặc định database tự chuyển đổi.

### 12.1. Mảng ObjectId

~~~javascript
db.projects.insertOne({
  _id: "PR01",
  memberIds: [
    ObjectId("507f1f77bcf86cd799439011"),
    ObjectId("507f1f77bcf86cd799439012")
  ]
});
~~~

Truy vấn cần cả hai thành viên:

~~~javascript
db.projects.find({
  memberIds: {
    $all: [
      ObjectId("507f1f77bcf86cd799439011"),
      ObjectId("507f1f77bcf86cd799439012")
    ]
  }
});
~~~

Nếu ứng dụng gửi chuỗi **"507f1f77bcf86cd799439011"** thay vì ObjectId, điều kiện không có cùng ý nghĩa. Ứng dụng Java/Spring Data cần converter đúng loại field.

### 12.2. Mảng số

~~~javascript
db.measurements.insertOne({
  _id: "M01",
  levels: [NumberInt(10), NumberInt(20), NumberInt(30)]
});

db.measurements.find({
  levels: { $in: [10, 30] }
});
~~~

MongoDB có quy tắc so sánh giữa các giá trị số BSON. Dù vậy, trong hệ thống cần chính xác về decimal/int64, hãy dùng kiểu dữ liệu phù hợp và không chuyển số nguyên 64-bit lớn qua JavaScript Number rồi mới tạo điều kiện.

### 12.3. Collation và so sánh string

Mặc định, so sánh string có thể phân biệt chữ hoa/chữ thường theo collation được dùng. Ví dụ **"MongoDB"** và **"mongodb"** không mặc định là một nhãn giống nhau trong mọi truy vấn.

Nếu nghiệp vụ cần so sánh không phân biệt chữ hoa/chữ thường, có thể:

- Chuẩn hóa tags thành dạng canonical như lowercase khi ghi;
- Dùng **collation** thích hợp cho query và index;
- Với một số truy vấn, dùng regex được kiểm soát.

Quyết định này ảnh hưởng index và tính nhất quán. Không nên thêm **/i** vào hàng loạt truy vấn rồi bỏ qua hệ quả hiệu năng.

## 13. Index multikey giúp truy vấn mảng ra sao?

MongoDB dùng **multikey index** khi index một field có giá trị mảng. Mỗi phần tử trong array có thể đóng góp các index key phù hợp.

### 13.1. Tạo index cho tags

~~~javascript
db.articles.createIndex(
  { tags: 1 },
  { name: "ix_articles_tags" }
);
~~~

Nếu collection có các mảng **tags**, đây là **multikey index**. Ví dụ một document:

~~~javascript
{ _id: "A01", tags: ["mongodb", "java", "backend"] }
~~~

được lập chỉ mục theo các giá trị cần thiết để tìm những document có nhãn tương ứng mà không phải luôn đọc toàn bộ collection.

### 13.2. $in thường phù hợp để tận dụng index

~~~javascript
db.articles.find({
  tags: { $in: ["mongodb", "java"] }
}).explain("executionStats");
~~~

Query planner có thể chọn index scan nếu có lợi. Khi **$in** chứa nhiều giá trị, MongoDB có thể phải tìm nhiều khoảng/điểm trong index rồi tổng hợp document phù hợp.

### 13.3. $all cũng có thể hưởng lợi từ multikey index

~~~javascript
db.articles.find({
  tags: { $all: ["mongodb", "java"] }
}).explain("executionStats");
~~~

MongoDB có thể dùng multikey index để lọc ứng viên rồi kiểm tra thêm các giá trị còn lại. **Không mặc định** database nhất thiết giao (intersect) các tập index theo cách đơn giản “mỗi nhãn một scan rồi AND”: kế hoạch thực tế do query planner quyết định.

### 13.4. $nin thường có tính chọn lọc thấp

~~~javascript
db.articles.find({
  tags: { $nin: ["blocked"] }
}).explain("executionStats");
~~~

Nếu hầu hết document đều **không bị blocked**, query có thể phải trả về phần lớn collection. Một index trên tags không nhất thiết giúp nhiều vì **điều kiện phủ định không chọn được tập nhỏ**. MongoDB có thể phải quét nhiều index key hoặc document, thậm chí chọn collection scan.

Nếu ứng dụng thường xuyên lấy “mọi bài viết đủ điều kiện”, có thể cân nhắc một field trạng thái được quản lý rõ ràng như **visibilityStatus: "VISIBLE"** và index tương ứng, thay vì trông chờ **$nin** trên blacklist luôn chạy nhanh. Nhưng phải bảo đảm trạng thái dẫn xuất luôn được cập nhật nhất quán.

### 13.5. Compound index với điều kiện tenant

Trong ứng dụng đa tenant:

~~~javascript
db.articles.createIndex(
  { tenantId: 1, tags: 1 },
  { name: "ix_tenant_tags" }
);
~~~

Truy vấn:

~~~javascript
db.articles.find({
  tenantId: "T1",
  tags: { $in: ["mongodb", "java"] }
}).explain("executionStats");
~~~

Index ghép giúp kết hợp lọc tenant với tìm tag. Tuy nhiên, lựa chọn thứ tự field trong compound index phải dựa trên query shape thực tế, tần suất lọc và sort.

Một giới hạn quan trọng: MongoDB có quy tắc đối với **compound multikey indexes** và việc lập chỉ mục nhiều array fields trong cùng document. Đừng tùy tiện tạo compound index gồm hai mảng độc lập mà không kiểm tra các hạn chế của phiên bản MongoDB.

### 13.6. Các chỉ số cần đọc trong explain

Khi dùng **explain("executionStats")**, chú ý:

- **winningPlan:** query planner chọn index scan hay collection scan?
- **totalKeysExamined:** số index key đã đọc;
- **totalDocsExamined:** số document đã đọc;
- **nReturned:** số document thực tế trả về;
- Độ trễ và điều kiện chạy thực tế nếu đo ở tầng ứng dụng.

Với dataset nhỏ trong lab, MongoDB có thể chọn **COLLSCAN** vì rẻ hơn dùng index. Không kết luận index vô dụng chỉ từ 10 document; cần đo trên dữ liệu có kích thước và phân bố đại diện.

## 14. Giữ truy vấn đúng khi đầu vào đến từ API

Một API có thể nhận:

~~~json
{
  "requiredTags": ["mongodb", "java"],
  "anyTags": ["backend", "tutorial"],
  "excludedTags": ["blocked"]
}
~~~

Ý nghĩa nghiệp vụ:

- **requiredTags:** phải có tất cả.
- **anyTags:** có ít nhất một trong danh sách.
- **excludedTags:** không có bất kỳ giá trị bị loại nào.

Một filter builder có thể tạo:

~~~javascript
const requiredTags = ["mongodb", "java"];
const anyTags = ["backend", "tutorial"];
const excludedTags = ["blocked"];

const clauses = [
  { tenantId: "T1" }
];

if (requiredTags.length > 0) {
  clauses.push({ tags: { $all: requiredTags } });
}

if (anyTags.length > 0) {
  clauses.push({ tags: { $in: anyTags } });
}

if (excludedTags.length > 0) {
  clauses.push({ tags: { $nin: excludedTags } });
}

const filter = { $and: clauses };
printjson(filter);

db.articles.find(filter);
~~~

**Các array rỗng được bỏ qua có chủ đích** vì API này quy định “không chọn bộ lọc đó thì không ràng buộc theo nó”. Một ứng dụng khác có thể muốn semantics khác, nhưng phải khai báo rõ.

### 14.1. Không để client gửi tự do MongoDB query operators

Đừng lấy nguyên body JSON từ client làm filter nếu API chỉ cho phép chọn nhãn:

~~~javascript
// Không nên để rawFilter do user gửi quyết định toàn bộ MongoDB query:
db.articles.find(rawFilterFromRequest);
~~~

Thay vào đó:

1. Đọc các field được phép như **requiredTags, anyTags, excludedTags**.
2. Xác minh chúng là array string, có giới hạn số phần tử và độ dài.
3. Chuẩn hóa và loại duplicate theo hợp đồng.
4. Gắn **tenantId** từ ngữ cảnh xác thực ở server, không tin tenantId tự khai từ client.
5. Tự tạo object filter với những toán tử đã cho phép.

Cách xây dựng này bảo vệ tính đúng đắn của query và hạn chế nguy cơ người dùng điều khiển ngoài ý muốn qua những operator MongoDB khác.

### 14.2. Danh sách giá trị quá lớn

Giới hạn các filter list của API theo nhu cầu nghiệp vụ. Một danh sách nhiều nghìn điều kiện có thể làm tăng CPU, kích thước request và thời gian query. Nếu tập dữ liệu được phép lọc thực sự rất lớn, cân nhắc cách biểu diễn khác như một nhóm/tag set được lưu sẵn và truy vấn theo ID nhóm.

## 15. Sử dụng trong MongoDB Java Sync Driver

MongoDB Java Sync Driver có các builder trong **com.mongodb.client.model.Filters**, giúp tạo BSON filter không cần tự ghép chuỗi JSON.

### 15.1. $all với Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

// MongoDatabase database đã được khởi tạo từ MongoClient.
MongoCollection<Document> articles =
        database.getCollection("articles");

Bson filter = Filters.and(
        Filters.eq("tenantId", "T1"),
        Filters.all("tags", "mongodb", "java")
);

for (Document article : articles.find(filter)) {
    System.out.println(article.getString("_id"));
}
~~~

**Filters.all** tạo điều kiện **$all**. Nếu collection dùng String **_id** như lab, có thể đọc bằng **getString("_id")**; với ObjectId cần dùng loại tương ứng.

### 15.2. $in với Java

~~~java
Bson filter = Filters.and(
        Filters.eq("tenantId", "T1"),
        Filters.in("tags", "mongodb", "java")
);

articles.find(filter).forEach(
        article -> System.out.println(article.getString("title"))
);
~~~

Mỗi document có ít nhất một tag mongodb hoặc java sẽ khớp. Nhớ rằng dữ liệu lab có A08 dạng string vẫn khớp **$in**.

### 15.3. $nin với Java

~~~java
Bson filter = Filters.and(
        Filters.eq("tenantId", "T1"),
        Filters.nin("tags", "blocked", "python")
);

articles.find(filter).forEach(
        article -> System.out.println(article.getString("_id"))
);
~~~

Kết quả còn bao gồm document không có tags. Nếu domain yêu cầu tags là mảng, kết hợp thêm điều kiện kiểu BSON trong filter hoặc ngăn dữ liệu sai schema ngay ở database.

### 15.4. Một filter Java có cả ba nhóm

~~~java
import static com.mongodb.client.model.Filters.all;
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.in;
import static com.mongodb.client.model.Filters.nin;

Bson filter = and(
        eq("tenantId", "T1"),
        all("tags", "mongodb", "java"),
        in("tags", "backend", "tutorial"),
        nin("tags", "blocked")
);

articles.find(filter).forEach(System.out::println);
~~~

**Filters.and** giữ từng điều kiện dưới dạng một clause, tránh vấn đề ghi đè khóa khi tự lắp các object JSON bằng thao tác put trên cùng field.

Trong ứng dụng lớn, nên kiểm soát danh sách filter bằng DTO typed, kiểm tra giá trị đầu vào và thực thi giới hạn truy vấn (pagination, timeout, projection) theo API.

## 16. Sử dụng trong Spring Data MongoDB

Spring Data MongoDB có **Criteria**, **Query** và **MongoTemplate** để xây dựng điều kiện.

### 16.1. Tìm document có tất cả các nhãn

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// MongoTemplate mongoTemplate được inject qua Spring.
Query query = new Query(
        Criteria.where("tenantId").is("T1")
                .and("tags").all("mongodb", "java")
);

List<Document> result =
        mongoTemplate.find(query, Document.class, "articles");
~~~

**Criteria.all** là biểu diễn thuận tiện của **$all**. Nếu ứng dụng dùng entity class, thay **Document.class** bằng kiểu entity phù hợp và khai báo mapping cho field.

### 16.2. Tìm document có bất kỳ nhãn được chọn

~~~java
Query query = new Query(
        Criteria.where("tenantId").is("T1")
                .and("tags").in("mongodb", "java")
);

List<Document> result =
        mongoTemplate.find(query, Document.class, "articles");
~~~

### 16.3. Loại các nhãn bị cấm

~~~java
Query query = new Query(
        Criteria.where("tenantId").is("T1")
                .and("tags").nin("blocked", "python")
);

List<Document> result =
        mongoTemplate.find(query, Document.class, "articles");
~~~

**Criteria.nin** không tự loại document thiếu tags. Nếu ứng dụng đòi hỏi field tags phải có mặt và là array, hãy thêm kiểm soát kiểu/schema phù hợp.

### 16.4. Xây dựng bộ lọc động

Không nên cố gọi **Criteria.where("tags")** nhiều lần rồi đặt một loạt tiêu chí cùng field bằng những API không phù hợp. Một cách đơn giản là tạo **danh sách Criteria**, sau đó ghép bằng **andOperator**:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

List<String> requiredTags = List.of("mongodb", "java");
List<String> anyTags = List.of("backend", "tutorial");
List<String> forbiddenTags = List.of("blocked");

List<Criteria> clauses = new ArrayList<>();
clauses.add(Criteria.where("tenantId").is("T1"));

if (!requiredTags.isEmpty()) {
    clauses.add(Criteria.where("tags").all(requiredTags));
}

if (!anyTags.isEmpty()) {
    clauses.add(Criteria.where("tags").in(anyTags));
}

if (!forbiddenTags.isEmpty()) {
    clauses.add(Criteria.where("tags").nin(forbiddenTags));
}

Criteria combined = new Criteria().andOperator(
        clauses.toArray(new Criteria[0])
);

Query query = new Query(combined);
~~~

Đoạn code giả định DTO đã được xác minh và danh sách được giới hạn. **tenantId** phải lấy từ ngữ cảnh phân quyền của ứng dụng thực tế.

### 16.5. Lưu ý về mapping và BSON types

Nếu **tags** trong entity Java được khai báo **List<String>**, Spring Data có thể map các field theo quy ước và converter đã cấu hình. Tuy nhiên, document cũ lưu tags dạng string hoặc null vẫn có thể xuất hiện trong collection; code không nên mặc định mọi kết quả đều hợp lệ với model mới nếu chưa migration hoặc validation.

Với danh sách **ObjectId** hoặc enum được chuyển đổi, hãy kiểm tra representation lưu trên MongoDB và dùng kiểu Java tương ứng. Một danh sách string hex không nhất thiết khớp mảng BSON ObjectId.

## 17. Performance khi kết hợp tập điều kiện và index

### 17.1. So sánh độ chọn lọc

Giả sử collection có 1 triệu bài:

- 2% chứa cả mongodb và java;
- 40% chứa ít nhất một trong hai nhãn;
- 98% không chứa blocked.

Đây là **ví dụ giả định**, không phải số liệu đo.

**$all** có thể trả về tập nhỏ nếu kết hợp nhãn hiếm. **$in** có thể trả về nhiều document hơn. **$nin** với blocked chỉ loại 2% dữ liệu nên rất ít chọn lọc và có thể phải đọc gần như toàn collection.

Với cùng một multikey index trên tags, ba query vẫn có chi phí khác nhau.

### 17.2. Dùng điều kiện tích cực để giới hạn phạm vi

Thay vì:

~~~javascript
db.articles.find({
  tags: { $nin: ["blocked"] }
});
~~~

Nếu API đã biết tenant và trạng thái, hãy đưa chúng vào:

~~~javascript
db.articles.find({
  tenantId: "T1",
  status: "PUBLISHED",
  tags: { $nin: ["blocked"] }
});
~~~

Điều kiện **tenantId/status** có thể giúp giảm tập dữ liệu được xét, miễn các field/index và dữ liệu thực tế phù hợp. Không thể khẳng định câu query mới luôn nhanh hơn khi chưa đo.

### 17.3. Không xem $nin là cơ chế bảo mật duy nhất

Ví dụ ứng dụng ẩn nội dung bằng **tags: {$nin:["private"]}**. Nếu record thiếu field tags, nó vẫn được trả về. Đây là rủi ro logic nếu **private** là kiểm soát truy cập.

Quyền truy cập nên được biểu diễn bằng cơ chế **authorization/visibility** đáng tin cậy với trạng thái mặc định an toàn và kiểm tra server-side; **$nin** trên một field tùy chọn không thể thay thế logic phân quyền.

### 17.4. Kiểm tra kế hoạch query

~~~javascript
const candidates = [
  { tags: { $all: ["mongodb", "java"] } },
  { tags: { $in: ["mongodb", "java"] } },
  { tags: { $nin: ["blocked", "python"] } }
];

for (const filter of candidates) {
  const plan = db.articles.find(filter).explain("executionStats");
  printjson({
    filter: filter,
    returned: plan.executionStats.nReturned,
    keysExamined: plan.executionStats.totalKeysExamined,
    docsExamined: plan.executionStats.totalDocsExamined
  });
}
~~~

Trên dataset nhỏ, các chỉ số có thể quá nhỏ để rút ra kết luận hiệu năng. Khi benchmark thực, kiểm tra lượng dữ liệu, cardinality, index, projection, sort và kết quả cache.

## 18. Những lỗi thường gặp

### 18.1. Dùng $in khi cần đủ mọi giá trị

**Sai ý định:**

~~~javascript
// Muốn có cả mongodb lẫn java,
// nhưng $in chỉ cần một trong hai.
db.articles.find({
  tags: { $in: ["mongodb", "java"] }
});
~~~

**Đúng ý định:**

~~~javascript
db.articles.find({
  tags: { $all: ["mongodb", "java"] }
});
~~~

### 18.2. Dùng $nin để chứng minh field hợp lệ

~~~javascript
db.articles.find({
  tags: { $nin: ["blocked"] }
});
~~~

Query này **không chứng minh** field tags có mặt, không null và có kiểu array. Cần schema validation và điều kiện kiểu theo yêu cầu nghiệp vụ.

### 18.3. Tin rằng $all đếm số lần xuất hiện

~~~javascript
db.articles.find({
  tags: { $all: ["mongodb", "mongodb"] }
});
~~~

Không buộc phải có **hai** phần tử mongodb. Muốn đếm phải dùng một biểu thức khác.

### 18.4. Truyền danh sách điều kiện rỗng mà không định nghĩa ý nghĩa

~~~javascript
{ tags: { $all: [] } } // không có kết quả
{ tags: { $in: [] } }  // không có kết quả
{ tags: { $nin: [] } } // không loại trừ gì
~~~

Khi user bỏ chọn filter, đừng vô tình tạo kết quả rỗng hoặc trả về toàn bộ dữ liệu ngoài ý định.

### 18.5. Dùng nhiều điều kiện dotted path và tưởng cùng phần tử

~~~javascript
{
  "items.sku": "A",
  "items.qty": { $gte: 5 }
}
~~~

Hai điều kiện có thể khớp hai item khác nhau. Nếu cần cùng item, dùng **$elemMatch**.

### 18.6. Trộn scalar và array ngoài chủ đích

~~~javascript
{ tags: "mongodb" }
{ tags: ["mongodb"] }
~~~

**$in** có thể khớp cả hai. Nếu business schema chỉ cho phép array, phải validate/migrate; không giả định kết quả query chứng minh document có đúng hình dạng.

### 18.7. Nghĩ $nin sẽ dùng index hiệu quả như $in

**$nin** thường có tính chọn lọc thấp. Nếu kết quả chiếm phần lớn collection, index không bảo đảm cải thiện. Đo thực tế và cân nhắc field cho phép trạng thái tích cực nếu phù hợp domain.

### 18.8. Truy vấn sai kiểu ObjectId

~~~javascript
{ memberIds: { $in: ["507f1f77bcf86cd799439011"] } }
~~~

Khi memberIds chứa ObjectId, không nên dùng string hex thay thế; cần tạo ObjectId đúng.

### 18.9. Tự ghép query JSON bằng cách ghi đè field

~~~javascript
const filter = { tags: { $all: ["mongodb", "java"] } };

// Ghi đè trường tags, mất điều kiện $all!
filter.tags = { $nin: ["blocked"] };
~~~

Hãy gộp các operator khác tên trong cùng object hoặc sử dụng **$and**:

~~~javascript
const filter = {
  tags: {
    $all: ["mongodb", "java"],
    $nin: ["blocked"]
  }
};
~~~

### 18.10. Đưa raw MongoDB query từ client vào database

Không cho người dùng tùy ý gửi các object operator nếu API chỉ cần một danh sách nhãn. Dùng DTO typed, allowlist fields, kiểm tra số phần tử và dựng query phía server.

## 19. Thực hành tổng hợp

### Bài 1 — Có cả hai nhãn

Tìm bài có **mongodb** và **java**:

~~~javascript
db.articles.find(
  { tags: { $all: ["mongodb", "java"] } },
  { _id: 1, tags: 1 }
);
~~~

**Kết quả dự kiến:** A01, A04.

### Bài 2 — Có một trong hai nhãn

~~~javascript
db.articles.find(
  { tags: { $in: ["mongodb", "java"] } },
  { _id: 1, tags: 1 }
);
~~~

**Kết quả dự kiến:** A01, A02, A03, A04, A08, A09, A10.

### Bài 3 — Không chứa nhãn cấm

~~~javascript
db.articles.find(
  { tags: { $nin: ["blocked", "python"] } },
  { _id: 1, tags: 1 }
);
~~~

**Kết quả dự kiến:** A01, A02, A03, A04, A05, A06, A07, A08. Hãy giải thích vì sao A06 thiếu tags vẫn được chọn.

### Bài 4 — Không chứa nhãn cấm, đồng thời tags phải là array

~~~javascript
db.articles.find(
  {
    tags: {
      $type: "array",
      $nin: ["blocked", "python"]
    }
  },
  { _id: 1, tags: 1 }
);
~~~

**Kết quả dự kiến:** A01, A02, A03, A04, A05. Giải thích vì sao A05 vẫn còn.

### Bài 5 — Phải có một bộ nhãn, không có nhãn bị loại

~~~javascript
db.articles.find(
  {
    tags: {
      $all: ["mongodb", "java"],
      $nin: ["blocked"]
    }
  },
  { _id: 1, tags: 1 }
);
~~~

**Kết quả dự kiến:** A01, A04.

### Bài 6 — Tìm order có cả SKU A và B

~~~javascript
db.orders.find({
  "items.sku": { $all: ["A", "B"] }
});
~~~

**Kết quả dự kiến:** O01 và O03.

### Bài 7 — Tìm order mà cùng một item A có qty >= 5

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 5 }
    }
  }
});
~~~

**Kết quả dự kiến:** O02, O03; giải thích vì sao O01 bị loại dù có một item B qty = 10.

### Bài 8 — So sánh kế hoạch truy vấn

Tạo index tags, chạy **explain("executionStats")** cho **$all/$in/$nin**. Ghi lại **nReturned**, **totalDocsExamined** và **totalKeysExamined**. Sau đó dùng tập dữ liệu lớn hơn và có phân bố nhãn đại diện để xem sự khác biệt về độ chọn lọc.

## 20. Câu hỏi tự kiểm tra

1. **$all** khác **$in** ở điều kiện AND/OR như thế nào?
2. Với tags = **["mongodb", "java", "backend"]**, vì sao **$all: ["mongodb","java"]** khớp dù có nhãn thứ ba?
3. Với tags = **["mongodb","mongodb"]**, **$all: ["mongodb","mongodb"]** có chứng minh phần tử xuất hiện ít nhất hai lần không?
4. Vì sao **$in** có thể khớp document mà field tags là scalar string?
5. **$nin** có trả về document thiếu field tags không? Cần bổ sung gì nếu không muốn vậy?
6. Khác biệt giữa **$exists: true** và **$type: "array"** là gì?
7. Kết quả của **$all: []**, **$in: []** và **$nin: []** khác nhau như thế nào?
8. Khi nào nên dùng **$elemMatch** thay cho nhiều điều kiện dotted path?
9. Làm sao tìm order có **ít nhất một item SKU A** và **ít nhất một item SKU B**?
10. Làm sao đảm bảo hai điều kiện **sku = A** và **qty >= 5** xảy ra trên cùng một item?
11. **Multikey index** giúp gì cho truy vấn mảng, và vì sao **$nin** vẫn có thể chậm?
12. Nếu tags chứa **ObjectId**, điều gì có thể xảy ra khi ứng dụng truyền danh sách string hex vào **$in**?
13. Với một API filter động, tại sao cần định nghĩa rõ ý nghĩa danh sách rỗng?
14. Tại sao bộ lọc denylist không nên là cơ chế kiểm soát quyền truy cập duy nhất?

## 21. Ghi nhớ khi sử dụng trong ứng dụng

~~~text
Yêu cầu nghiệp vụ                             Toán tử
-----------------------------------------------------------
Có tất cả các kỹ năng bắt buộc                $all
Có ít nhất một danh mục được chọn             $in
Không chứa bất kỳ nhãn bị cấm nào             $nin
Có một item thỏa nhiều điều kiện cùng lúc     $elemMatch
Mảng có đúng N phần tử                        $size
Chỉ chấp nhận document có field là array      $type: "array"
~~~

Các quy tắc thực hành:

1. **Chọn $all** khi phải có đủ mọi giá trị trong danh sách, bất kể thứ tự và cho phép phần tử khác.
2. **Chọn $in** khi có ít nhất một giá trị thỏa; nhớ nó cũng có thể khớp field scalar.
3. **Chọn $nin** khi cần loại các giá trị bị cấm; luôn cân nhắc document thiếu field và độ chọn lọc thấp.
4. **Dùng $elemMatch** khi nhiều điều kiện phải nằm trên cùng một phần tử của mảng object.
5. **Phân biệt missing, null, mảng rỗng và scalar**. Schema validation giúp dữ liệu ổn định hơn.
6. **Xử lý danh sách điều kiện rỗng có chủ đích**, tránh UI trả dữ liệu sai mong đợi.
7. **Giữ đúng BSON type** khi truyền điều kiện, đặc biệt với ObjectId, Date và số lớn.
8. **Đo index/query bằng explain** trên dữ liệu đại diện; không mặc định ba toán tử có hiệu năng tương đương.
9. **Xây dựng filter phía server** từ DTO/allowlist, giữ ràng buộc tenant và quyền truy cập độc lập với bộ lọc tag do client chọn.

### Tài liệu MongoDB chính thức

- [$all Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/all/) — ngữ nghĩa yêu cầu đầy đủ, mảng rỗng và kết hợp **$elemMatch**.
- [$in Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/in/) — so khớp ít nhất một giá trị và sử dụng với array.
- [$nin Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/nin/) — loại trừ giá trị và xử lý missing field.
- [Query an Array](https://www.mongodb.com/docs/manual/tutorial/query-arrays/) — những mẫu truy vấn array cơ bản.
- [Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/) — phân biệt dotted path và **$elemMatch**.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — cách index hỗ trợ field mảng.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — truy vấn bằng **Filters** trong Java.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — dùng **Criteria**, **Query**, **MongoTemplate** với MongoDB.

Ba toán tử **$all**, **$in** và **$nin** thường chỉ khác nhau một ký tự trong query nhưng có thể làm thay đổi tập kết quả rất lớn. Khi thiết kế truy vấn mảng, hãy xác định trước ý nghĩa **“đầy đủ / ít nhất một / không phần tử nào”**, sau đó kiểm tra những tình huống ngoại lệ như field missing, null, nested objects và danh sách điều kiện rỗng.
