# Collation của index và yêu cầu tương thích với truy vấn trong MongoDB

## 1. Mục tiêu và vấn đề thực tế

Khi xây dựng ứng dụng với MongoDB, không phải mọi phép so sánh chuỗi đều có ý nghĩa giống nhau. Một hệ thống quản lý khách hàng có thể muốn:

- Tìm `"Lan"` khi người dùng gõ `"lan"` hoặc `"LAN"`.
- Phân biệt `"cafe"` với `"café"`, hoặc cố ý coi chúng tương đương.
- Sắp xếp tên theo quy tắc của một ngôn ngữ thay vì theo giá trị byte.
- Xem `"item2"` đứng trước `"item10"` khi sắp xếp số nằm trong chuỗi.
- Ngăn hai email chỉ khác chữ hoa/thường cùng được tạo trong một collection.
- Đảm bảo một index dùng để tăng tốc filter và sort có **quy tắc so sánh tương thích với truy vấn**.

MongoDB sử dụng **collation** để mô tả cách so sánh, sắp xếp chuỗi theo ngôn ngữ. Collation có thể được cấu hình cho collection, index hoặc riêng một thao tác truy vấn. Điều quan trọng không chỉ là “tạo index cho trường `name`”, mà là **index và truy vấn có cùng ngữ nghĩa so sánh chuỗi hay không**.

Trong chương **Index chuyên biệt** của **Database Engine Document MongoDB**, bài học này tập trung vào collation của index và yêu cầu tương thích với truy vấn. Sau bài, bạn có thể:

1. Giải thích `locale`, `strength`, `caseLevel`, `numericOrdering` và các tùy chọn thường gặp.
2. Tạo index có collation cụ thể, kể cả khi collection có default collation khác.
3. Viết `find`, `sort`, `countDocuments` và `aggregate` sử dụng collation tương thích.
4. Phân biệt **đúng kết quả** với **có dùng được index hiệu quả hay không**.
5. Hiểu ràng buộc unique index dựa trên collation và tác động tới dữ liệu hiện có.
6. Phân tích trường hợp compound index có thành phần không phải chuỗi, regex, dữ liệu đa ngôn ngữ và phân trang.
7. Dùng `explain("executionStats")` để quan sát hành vi của query planner.

> **Nguyên tắc trung tâm:** MongoDB có thể thực hiện truy vấn với collation được chỉ định dù index không có collation đó, nhưng index không tương thích có thể **không hỗ trợ được phần so sánh hoặc sắp xếp chuỗi**. Đúng về kết quả và nhanh về hiệu năng là hai câu hỏi khác nhau.

## 2. Collation là gì?

**Collation** là tập quy tắc để so sánh các giá trị chuỗi. Thay vì chỉ so sánh chuỗi theo thứ tự byte, MongoDB có thể áp dụng các quy tắc dựa trên Unicode và locale.

Ví dụ, hai chuỗi sau:

~~~text
"Lan"
"lan"
~~~

có thể:

- Được xem là **khác nhau** với so sánh nhị phân mặc định (*simple collation*).
- Được xem là **tương đương** với collation không phân biệt chữ hoa/thường ở strength phù hợp.

Tương tự:

~~~text
"cafe"
"café"
~~~

có thể giống nhau nếu collation bỏ qua dấu, nhưng khác nhau nếu yêu cầu phân biệt dấu.

Cấu hình ví dụ:

~~~javascript
{
  locale: "en",
  strength: 2
}
~~~

Nghĩa thường dùng: so sánh theo quy tắc tiếng Anh, phân biệt dấu nhưng không phân biệt khác biệt chữ hoa/thường ở cấp độ strength này (khi không bật tùy chọn khác làm thay đổi hành vi).

### 2.1. Simple collation

~~~javascript
{ locale: "simple" }
~~~

`simple` là so sánh chuỗi dạng binary, không áp dụng quy tắc ngôn ngữ của ICU giống những locale thông thường. Trong một collection có simple collation, điều kiện bằng:

~~~javascript
{ name: "Lan" }
~~~

không mặc định khớp document chỉ có `name: "lan"`.

Simple là collation mặc định khi bạn không cấu hình collation ở cấp collection hay thao tác, và không có quy tắc mặc định nào khác được thừa kế.

### 2.2. Các mức cấu hình

Collation xuất hiện ở ba phạm vi thường gặp:

~~~text
Collection default collation
          |
          +--> Index có thể thừa kế default hoặc khai báo riêng
          |
          +--> Operation có thể thừa kế default hoặc khai báo riêng
                     |
                     +--> find / sort / count / aggregate ...
~~~

Chỉ “cùng trường index” chưa đủ. Với string comparison, cần xem **collation của thao tác** có tương thích với **collation của index** hay không.

## 3. Các tùy chọn collation quan trọng

### 3.1. locale

`locale` xác định quy tắc ngôn ngữ cần dùng:

~~~javascript
{ locale: "en" } // tiếng Anh
{ locale: "vi" } // tiếng Việt
{ locale: "fr" } // tiếng Pháp
{ locale: "simple" } // so sánh binary
~~~

Cách sắp xếp chữ cái và quy tắc nhấn dấu có thể khác theo locale. Khi dữ liệu thực tế chứa tên tiếng Việt, nên xác định xem người dùng muốn so sánh theo `vi`, theo quy tắc khác, hay theo mã chuẩn hóa do ứng dụng kiểm soát.

Không nên chỉ vì ứng dụng hiển thị tiếng Việt mà mặc định mọi trường có cùng ngữ nghĩa: mã SKU, UUID, email, tên người và mô tả sản phẩm có thể cần các chính sách so sánh khác nhau.

### 3.2. strength: mức phân biệt ký tự

Ba mức thường dùng nhất:

| `strength` | Ý nghĩa khái quát | So sánh `Lan` với `lan` | So sánh `cafe` với `café` |
|---|---|---|---|
| `1` | Mức cơ bản, thường bỏ qua khác biệt hoa/thường và dấu | Tương đương | Tương đương |
| `2` | Phân biệt dấu, thường bỏ qua hoa/thường | Tương đương | Khác |
| `3` | Phân biệt thêm hoa/thường | Khác | Khác |

Đây là bảng minh họa theo các ví dụ chữ Latin phổ biến và khi không bật tùy chọn đặc biệt như `caseLevel`. Quy tắc Unicode/locale thực tế có thể phức tạp hơn những cặp minh họa trên.

Ví dụ case-insensitive nhưng accent-sensitive:

~~~javascript
{ locale: "en", strength: 2 }
~~~

Ví dụ case-insensitive và accent-insensitive ở mức cơ bản:

~~~javascript
{ locale: "en", strength: 1 }
~~~

Nếu sản phẩm yêu cầu chính xác về dấu trong tiếng Việt, cần thử các trường hợp thực tế thay vì khẳng định chung rằng mọi tổ hợp dấu đều đơn giản như cặp `cafe/café`.

### 3.3. caseLevel và caseFirst

`caseLevel` có thể kích hoạt mức phân biệt hoa/thường bổ sung trong những tình huống dùng strength thấp:

~~~javascript
{
  locale: "en",
  strength: 1,
  caseLevel: true
}
~~~

`caseFirst` ảnh hưởng thứ tự ưu tiên chữ hoa hoặc chữ thường trong những trường hợp thích hợp:

~~~javascript
{
  locale: "en",
  strength: 3,
  caseFirst: "upper"
}
~~~

Các tùy chọn này phục vụ nhu cầu sort rất cụ thể. Nếu chỉ muốn tìm tên không phân biệt hoa/thường, `strength: 2` hoặc `strength: 1` theo yêu cầu dấu thường dễ giải thích hơn.

### 3.4. numericOrdering

Với các chuỗi:

~~~text
"item1"
"item2"
"item10"
~~~

So sánh chuỗi thông thường có thể đặt `item10` trước `item2` do thứ tự ký tự. Muốn các dãy chữ số liên tiếp trong chuỗi được xét theo thứ tự số, có thể khai báo:

~~~javascript
{
  locale: "en",
  numericOrdering: true
}
~~~

Đây là **so sánh chuỗi có thành phần số**, không chuyển toàn bộ field thành kiểu Number. Một số dạng như số âm, dấu thập phân hoặc scientific notation không được xử lý như phép so sánh số học thông thường. Nếu thứ tự số học là quy tắc dữ liệu chính, lưu số bằng BSON numeric type là lựa chọn rõ ràng hơn.

### 3.5. Các tùy chọn khác

| Thuộc tính | Vai trò |
|---|---|
| `alternate` | Quy định cách xử lý một số dấu câu/khoảng trắng khi so sánh |
| `maxVariable` | Kết hợp `alternate: "shifted"` để chọn nhóm ký tự có thể bị bỏ qua ở mức phù hợp |
| `backwards` | Có thể ảnh hưởng cách so sánh dấu từ cuối chuỗi theo quy tắc locale thích hợp |
| `normalization` | Liên quan đến xử lý dạng chuẩn hóa Unicode |
| `caseFirst` | Điều chỉnh ưu tiên chữ hoa/chữ thường trong sort |
| `numericOrdering` | So sánh các chuỗi chữ số liên tiếp theo giá trị số |

Một số tùy chọn chỉ có ý nghĩa khi đi kèm thiết lập liên quan. Không cần thêm tất cả vào mọi index; hãy xuất phát từ quy tắc so sánh mà sản phẩm thật sự cần.

## 4. Chuẩn bị bộ dữ liệu thực hành

Sử dụng database riêng để tránh ảnh hưởng dữ liệu thật:

~~~javascript
use collation_index_lab
~~~

Tạo collection thông thường, không cấu hình default collation đặc biệt:

~~~javascript
if (db.getCollectionInfos({ name: "people" }).length === 0) {
  db.createCollection("people");
}
~~~

Chèn dữ liệu mẫu bằng `replaceOne` theo ID để có thể chạy lại:

~~~javascript
const samplePeople = [
  {
    _id: 1,
    name: "Lan",
    city: "Hà Nội",
    age: NumberInt(21),
    code: "item2",
    groupId: NumberInt(10)
  },
  {
    _id: 2,
    name: "lan",
    city: "Hà Nội",
    age: NumberInt(22),
    code: "item10",
    groupId: NumberInt(10)
  },
  {
    _id: 3,
    name: "LAN",
    city: "Huế",
    age: NumberInt(23),
    code: "item1",
    groupId: NumberInt(10)
  },
  {
    _id: 4,
    name: "cafe",
    city: "Đà Nẵng",
    age: NumberInt(24),
    code: "item9",
    groupId: NumberInt(20)
  },
  {
    _id: 5,
    name: "café",
    city: "Đà Nẵng",
    age: NumberInt(25),
    code: "item12",
    groupId: NumberInt(20)
  },
  {
    _id: 6,
    name: "Anh",
    city: "Huế",
    age: NumberInt(20),
    code: "item11",
    groupId: NumberInt(30)
  },
  {
    _id: 7,
    name: "anh",
    city: "Hà Nội",
    age: NumberInt(30),
    code: "item3",
    groupId: NumberInt(30)
  }
];

samplePeople.forEach(person => {
  db.people.replaceOne(
    { _id: person._id },
    person,
    { upsert: true }
  );
});

db.people.countDocuments({});
~~~

Với collection mới, kết quả là **7 document**. Khi chạy lại đoạn nạp mẫu, nội dung 7 document sẽ được đặt lại, nhưng MongoDB không tự xóa record khác từng được thêm trong collection.

### 4.1. Xem dữ liệu trước khi dùng collation

~~~javascript
db.people.find(
  {},
  { _id: 1, name: 1, code: 1 }
).sort({ _id: 1 });
~~~

Bộ dữ liệu cố ý có ba biến thể `Lan`/`lan`/`LAN`, hai biến thể `cafe`/`café` và các mã `item1`/`item2`/`item10`.

Các trường hợp này giúp kiểm tra sự khác nhau giữa:

- So sánh binary và so sánh theo locale.
- Phân biệt dấu và không phân biệt dấu.
- So sánh bằng và sắp xếp.
- Sort chuỗi thông thường và `numericOrdering`.

## 5. Tạo index có collation riêng

### 5.1. Index mặc định và index không phân biệt hoa/thường

Tạo một index cho `name` với collation `en` và `strength: 2`:

~~~javascript
db.people.createIndex(
  { name: 1 },
  {
    name: "idx_name_en_strength2",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Index này tổ chức khóa chuỗi theo quy tắc collation đã cấu hình. Nó có thể hỗ trợ các phép so sánh hoặc sort chuỗi **cùng collation** khi query planner thấy phù hợp.

Xem metadata index:

~~~javascript
db.people.getIndexes();
~~~

Trong định nghĩa của `idx_name_en_strength2`, cần nhìn trường `collation`. Các trường hiển thị thực tế phụ thuộc phiên bản MongoDB, nhưng collation đã cấu hình là phần quan trọng cần xác nhận.

### 5.2. Thêm index simple trên cùng trường

Có thể tạo nhiều index có cùng key pattern nhưng **collation khác nhau**, với tên index riêng:

~~~javascript
db.people.createIndex(
  { name: 1 },
  {
    name: "idx_name_simple",
    collation: { locale: "simple" }
  }
);
~~~

Ở đây hai index cùng khóa `{name:1}` nhưng có ngữ nghĩa thứ tự chuỗi khác nhau:

| Index | Key pattern | Collation |
|---|---|---|
| `idx_name_en_strength2` | `{name:1}` | `{locale:"en", strength:2}` |
| `idx_name_simple` | `{name:1}` | `{locale:"simple"}` |

Cách này phù hợp khi ứng dụng thật sự cần cả tìm kiếm không phân biệt hoa/thường lẫn so sánh binary. Tuy nhiên, **mỗi index thêm đều tốn dung lượng và chi phí duy trì khi ghi**. Không tạo hai index chỉ vì ví dụ; trong production phải đo workload.

### 5.3. Vì sao phải chỉ định tên index?

Khi nhiều index có cùng key pattern nhưng collation khác nhau, cần tên index phân biệt để quản trị dễ dàng và tránh xung đột tên. Quy ước tên nên thể hiện mục đích:

~~~text
idx_name_simple
idx_name_en_strength2
idx_code_numeric_en
uniq_email_en_ci
~~~

Không nên chỉ nhìn tên để đoán cấu hình thật; luôn dùng `getIndexes()` để kiểm tra định nghĩa lưu trên server.

## 6. Truy vấn phải có collation tương thích với index

### 6.1. Query không chỉ định collation

Collection `people` được tạo mặc định, không khai báo collation nên sử dụng simple collation. Truy vấn:

~~~javascript
db.people.find({
  name: "lan"
});
~~~

với so sánh simple thường chỉ chọn document có `name: "lan"`, tức ID **2**, không tự khớp `Lan` và `LAN`.

Vì truy vấn này dùng simple collation, index simple có thể phục vụ phép so sánh chuỗi tương ứng. Index `idx_name_en_strength2` có ngữ nghĩa khác nên không thể được coi như một index simple tương đương cho điều kiện chuỗi.

### 6.2. Query chỉ định cùng collation với index

~~~javascript
db.people.find(
  { name: "lan" },
  { _id: 1, name: 1 }
).collation({
  locale: "en",
  strength: 2
}).sort({ _id: 1 });
~~~

Với dữ liệu mẫu, kết quả là ID **1, 2, 3**.

Trong query trên, collation của thao tác phù hợp với collation của `idx_name_en_strength2`. Index có thể giúp tối ưu lookup bằng chuỗi theo ngữ nghĩa đó. Query planner vẫn được quyền chọn kế hoạch khác khi collection quá nhỏ hoặc các chi phí dự đoán khiến plan khác phù hợp hơn.

### 6.3. Query dùng strength khác

~~~javascript
db.people.find({
  name: "lan"
}).collation({
  locale: "en",
  strength: 3
});
~~~

`strength: 3` có yêu cầu phân biệt hoa/thường mà index `strength: 2` không đáp ứng tương đương. Vì vậy không nên mong index strength 2 sẽ cung cấp cùng phạm vi tìm kiếm chuỗi như truy vấn strength 3.

Nếu ứng dụng thường tìm kiếm ở strength 3, cần cân nhắc index có collation tương ứng hoặc dùng simple collation nếu đúng yêu cầu ngữ nghĩa.

### 6.4. Bảng tương thích thực hành

| Truy vấn | Index name strength 2 | Index name simple | Nhận xét |
|---|---|---|---|
| `find({name:"lan"})` mặc định simple | Không phù hợp cho string equality simple | Phù hợp | Kết quả chỉ có `lan` |
| `find({name:"lan"}).collation({locale:"en",strength:2})` | Phù hợp | Không phù hợp cho equality không phân biệt hoa/thường | Có thể trả ba biến thể Lan |
| `find({name:"lan"}).collation({locale:"en",strength:1})` | Không tương đương đầy đủ | Không tương đương | Strength 1 bỏ qua thêm khác biệt dấu |
| `find({name:"lan"}).collation({locale:"en",strength:3})` | Không tương đương đầy đủ | Không tương đương | Strength 3 phân biệt hoa/thường |
| `find({age:22})` | Collation thường không quyết định phép bằng số | Có thể dùng index nếu có key age phù hợp | Không nhầm tương thích collation với việc có index cho field |

“Phù hợp” ở bảng nghĩa là index có **ngữ nghĩa tương thích**, không phải MongoDB chắc chắn chọn index đó trên mọi tập dữ liệu.

### 6.5. Vì sao index không tương thích không thể thay thế nhau?

Một index trên string không đơn thuần lưu các byte theo thứ tự ngẫu nhiên. Nó được xây dựng theo quy tắc so sánh của collation.

Nếu index được tổ chức theo cách coi `"Lan"`, `"lan"`, `"LAN"` tương đương, nó không thể dùng cùng cách tra cứu khóa để thực hiện mọi phép so sánh binary yêu cầu phân biệt chính xác các chuỗi ấy.

Ngược lại, index simple không thể tự cung cấp mọi quan hệ tương đương theo locale mà không có thêm bước xử lý. MongoDB có thể quét dữ liệu rồi so sánh theo collation của truy vấn, nhưng khi đó chi phí khác với index lookup phù hợp.

## 7. Kiểm chứng bằng explain()

### 7.1. Query có collation tương thích

~~~javascript
db.people.find({
  name: "lan"
})
.collation({ locale: "en", strength: 2 })
.explain("executionStats");
~~~

Các thông tin nên quan sát:

- `winningPlan`: kế hoạch được chọn.
- `IXSCAN`: có dùng quét index hay không.
- `COLLSCAN`: quét collection.
- `indexName`: tên index nếu plan có index scan.
- `indexBounds`: phạm vi khóa index được sử dụng.
- `totalKeysExamined`: số khóa index phải đọc.
- `totalDocsExamined`: số document được xem.
- `nReturned`: số document trả về.

Nếu dùng `IXSCAN` trên `idx_name_en_strength2`, đó là dấu hiệu index phù hợp đã được chọn.

### 7.2. Query simple

~~~javascript
db.people.find({
  name: "lan"
})
.collation({ locale: "simple" })
.explain("executionStats");
~~~

So sánh plan với mục 7.1. Nếu planner chọn `idx_name_simple`, điều đó phản ánh sự phù hợp giữa quy tắc so sánh truy vấn và index.

### 7.3. Query dùng collation không tương thích

~~~javascript
db.people.find({
  name: "lan"
})
.collation({ locale: "en", strength: 1 })
.explain("executionStats");
~~~

Truy vấn này bỏ qua nhiều khác biệt hơn so với index strength 2. Không giả định nó được xử lý như một equality lookup trên index strength 2.

**Lưu ý về kích thước dữ liệu:** Với 7 document, MongoDB có thể chọn `COLLSCAN` cho mọi trường hợp vì tổng chi phí rất nhỏ. Không nên kết luận collation index “không hoạt động” chỉ dựa trên việc query planner thích collection scan trong bộ mẫu.

### 7.4. Không ép hint để “chứng minh tương thích”

Có thể dùng `hint()` trong công tác kiểm tra kế hoạch, nhưng ép sử dụng một index không có collation tương thích **không biến nó thành index phục vụ được phép so sánh chuỗi đúng cách**. Server có thể phải quét nhiều khóa hoặc áp dụng bước lọc bổ sung.

Với đánh giá hiệu năng, nên quan sát plan mặc định, sau đó so sánh các lựa chọn có ý nghĩa trên dữ liệu đại diện, thay vì ép một index rồi nhìn thấy `IXSCAN` và coi đó là đã tối ưu.

## 8. Collection default collation và cơ chế kế thừa

### 8.1. Tạo collection có default collation

Ngoài cách khai báo riêng cho từng index, bạn có thể tạo một collection dùng collation mặc định:

~~~javascript
use collation_index_lab

if (db.getCollectionInfos({ name: "catalogDefaultCI" }).length === 0) {
  db.createCollection("catalogDefaultCI", {
    collation: {
      locale: "en",
      strength: 2
    }
  });
}
~~~

Với collection có default collation như trên:

- Thao tác truy vấn không khai báo collation thường sử dụng default collation của collection.
- Index được tạo không khai báo collation riêng thường thừa kế default collation của collection.
- Có thể khai báo collation khác cho từng index khi có nhu cầu.

Ví dụ:

~~~javascript
db.catalogDefaultCI.createIndex(
  { title: 1 },
  { name: "idx_title_default" }
);
~~~

Index `idx_title_default` thừa kế collation của collection nếu được tạo như trên.

Kiểm tra metadata:

~~~javascript
db.getCollectionInfos({ name: "catalogDefaultCI" });
db.catalogDefaultCI.getIndexes();
~~~

### 8.2. Query không cần khai báo lại khi dùng default

~~~javascript
db.catalogDefaultCI.insertMany([
  { _id: 1, title: "MongoDB Guide" },
  { _id: 2, title: "mongodb guide" }
]);

db.catalogDefaultCI.find({
  title: "MONGODB GUIDE"
});
~~~

Trong một collection mới có default `locale:"en", strength:2`, truy vấn không chỉ định collation có thể khớp cả hai biến thể do kế thừa collation mặc định.

Nếu chạy lại `insertMany` sẽ gặp duplicate `_id`; đó là lỗi dữ liệu mẫu, không phải lỗi collation. Có thể dùng `replaceOne(..., {upsert:true})` nếu muốn nạp lại có kiểm soát.

### 8.3. Khi nào cần chỉ định simple để override?

Muốn một thao tác trên collection có default case-insensitive sử dụng so sánh binary:

~~~javascript
db.catalogDefaultCI.find({
  title: "MongoDB Guide"
}).collation({
  locale: "simple"
});
~~~

Lệnh này yêu cầu simple collation, khác default của collection. Nếu muốn tăng tốc **chuỗi theo simple collation**, cần cân nhắc index có simple collation:

~~~javascript
db.catalogDefaultCI.createIndex(
  { title: 1 },
  {
    name: "idx_title_simple",
    collation: { locale: "simple" }
  }
);
~~~

Không phải vì collection đã có index trên `title` mà mọi truy vấn với bất kỳ collation nào đều được index đó hỗ trợ hiệu quả.

### 8.4. Collation mặc định không nên đổi tùy tiện sau khi tạo

Hãy quyết định default collation khi thiết kế collection. Với collection đã tồn tại, không nên giả định có thể chỉ chạy một `collMod` thông thường để thay đổi toàn bộ default collation và tự động chuyển đổi mọi index. Thay đổi chính sách so sánh ở cấp collection có thể đòi hỏi quy trình migration/tạo mới/rebuild index phù hợp với khả năng server và dữ liệu.

Khi cần áp dụng collation mới cho một query cụ thể, hãy dùng collation ở cấp operation và index được thiết kế tương ứng, thay vì vội thay đổi cấu hình toàn collection.

## 9. Sort theo collation và tương thích index

Collation không chỉ điều khiển equality filter. Nó còn ảnh hưởng **thứ tự sắp xếp chuỗi**.

### 9.1. Sort với simple collation

~~~javascript
db.people.find(
  {},
  { _id: 1, name: 1 }
)
.sort({ name: 1, _id: 1 })
.collation({ locale: "simple" });
~~~

MongoDB so sánh tên theo simple ordering. Chữ hoa, chữ thường và dấu có thể cho thứ tự khác với thứ tự người dùng mong đợi trong một danh bạ.

### 9.2. Sort theo locale và strength

~~~javascript
db.people.find(
  {},
  { _id: 1, name: 1 }
)
.sort({ name: 1, _id: 1 })
.collation({
  locale: "en",
  strength: 2
});
~~~

Các biến thể `Lan`/`lan`/`LAN` có thể được xem tương đương tại mức collation này. Khi muốn **thứ tự hiển thị ổn định giữa các lần phân trang**, hãy có khóa phụ duy nhất như `_id`.

Không nên khẳng định chính xác thứ tự mọi ký tự có dấu trong mọi locale chỉ từ một ví dụ nhỏ; ICU và phiên bản môi trường có thể ảnh hưởng chi tiết sắp xếp.

### 9.3. Index cho sort có collation

Nếu ứng dụng thường sort theo tên với `en, strength:2`, index đơn `{name:1}` có cùng collation là một lựa chọn cần xem xét. Với sort có tie-breaker `_id`:

~~~javascript
db.people.createIndex(
  { name: 1, _id: 1 },
  {
    name: "idx_name_id_en_strength2",
    collation: { locale: "en", strength: 2 }
  }
);
~~~

Truy vấn:

~~~javascript
db.people.find(
  {},
  { _id: 1, name: 1 }
)
.sort({ name: 1, _id: 1 })
.collation({ locale: "en", strength: 2 })
.explain("executionStats");
~~~

Khi index phù hợp được chọn, MongoDB có thể tránh một số bước sort tốn tài nguyên. Nếu collation không tương thích, index không nhất thiết hỗ trợ sort theo yêu cầu và server có thể cần thực hiện sort riêng.

### 9.4. Sort theo số nằm trong chuỗi

Ví dụ:

~~~javascript
db.people.find(
  {},
  { _id: 1, code: 1 }
)
.sort({ code: 1, _id: 1 })
.collation({
  locale: "en",
  numericOrdering: true
});
~~~

Với các mã như `item1`, `item2`, `item10`, numeric ordering có thể tạo thứ tự người đọc mong đợi hơn so với simple string order.

Nếu truy vấn này thường xuyên, index `{code:1}` dùng cùng collation có thể hỗ trợ sort:

~~~javascript
db.people.createIndex(
  { code: 1 },
  {
    name: "idx_code_numeric_en",
    collation: {
      locale: "en",
      numericOrdering: true
    }
  }
);
~~~

Truy vấn dùng `numericOrdering:true` và truy vấn không dùng không có cùng quy tắc sort. Vì thế không được xem hai cấu hình index là tương đương chỉ vì cùng `locale:"en"`.

## 10. Unique index và collation: kiểm soát trùng theo ngữ nghĩa

Một ứng dụng đăng ký tài khoản có thể coi email viết hoa và viết thường là cùng một khóa nghiệp vụ. Unique index có collation phù hợp là một công cụ để ràng buộc dữ liệu ở server.

### 10.1. Tạo unique index không phân biệt hoa/thường

Tạo collection thực hành riêng:

~~~javascript
use collation_index_lab

if (db.getCollectionInfos({ name: "accountsUnique" }).length === 0) {
  db.createCollection("accountsUnique");
}
~~~

Tạo index:

~~~javascript
db.accountsUnique.createIndex(
  { email: 1 },
  {
    name: "uniq_email_en_strength2",
    unique: true,
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Chèn dữ liệu đầu tiên:

~~~javascript
db.accountsUnique.insertOne({
  _id: "acc-001",
  email: "Hello@example.test",
  displayName: "First account"
});
~~~

Thử chèn email chỉ khác cách viết hoa:

~~~javascript
// Dự kiến lỗi duplicate key theo unique index có collation.
db.accountsUnique.insertOne({
  _id: "acc-002",
  email: "hello@example.test",
  displayName: "Second account"
});
~~~

Vì collation của unique index coi hai chuỗi tương đương theo tiêu chí của nó, việc chèn record thứ hai có thể bị từ chối với lỗi **E11000 duplicate key**.

### 10.2. Unique index không tự sửa dữ liệu

Index không chuyển chuỗi lưu trữ thành chữ thường. Document đầu vẫn có thể giữ `"Hello@example.test"`; ràng buộc uniqueness được áp dụng khi ghi dựa trên phép so sánh của index.

Nếu ứng dụng cần đồng nhất cách hiển thị và tra cứu, có thể chuẩn hóa email tại tầng ứng dụng thành dạng canonical. Lưu ý các quy tắc email quốc tế và nghiệp vụ có thể phức tạp; collation theo locale không thay thế một chính sách identity/email hoàn chỉnh.

### 10.3. Không tạo unique index trước khi xử lý dữ liệu trùng

Nếu collection đã có:

~~~javascript
{ _id: 1, email: "Hello@example.test" }
{ _id: 2, email: "hello@example.test" }
~~~

thì việc tạo **unique index** không phân biệt hoa/thường có thể thất bại vì dữ liệu hiện có vi phạm ràng buộc. Cần:

1. Xác định tập các chuỗi sẽ bị coi là trùng theo collation dự định.
2. Quyết định bản ghi nào được giữ, hợp nhất hoặc cập nhật.
3. Sửa dữ liệu cũ theo quy trình.
4. Tạo unique index.
5. Theo dõi lỗi ghi từ ứng dụng và giải thích rõ cho người dùng.

Không dùng lệnh drop/xóa dữ liệu hàng loạt chỉ để index tạo thành công mà không có kế hoạch bảo toàn dữ liệu.

### 10.4. Strength 1 khác strength 2 trong tính duy nhất

Với các giá trị `cafe` và `café`:

- Ở strength 1, chúng có thể bị coi tương đương → unique index sẽ không cho đồng thời cả hai nếu chúng là khóa duy nhất theo collation ấy.
- Ở strength 2, chúng có thể là hai giá trị khác nhau vì dấu được phân biệt.
- Ở strength 3, chữ hoa/thường cũng tham gia phân biệt theo mức đó.

Do đó, trước khi chọn unique collation, phải quyết định **định nghĩa nghiệp vụ của “trùng”**, nhất là với dữ liệu tiếng Việt, tên người hoặc mã nhận diện.

### 10.5. Unique index không loại trừ các quy tắc khác

Unique collation index không thay thế `_id` unique, schema validation, kiểm tra trường bắt buộc hoặc phân quyền. Nếu nghiệp vụ yêu cầu mọi tài khoản luôn có email, cần thêm validator/logic kiểm tra sự hiện diện và kiểu dữ liệu, thay vì chỉ tin vào unique index.

## 11. Compound index: phần khóa không phải chuỗi

Một điểm đặc biệt: khi collation truy vấn không khớp collation của index, MongoDB có thể vẫn sử dụng **phần tiền tố của compound index gồm các trường không phải string**, nếu điều kiện truy vấn cho phép. Điều này không đồng nghĩa index được dùng cho phần so sánh string không tương thích.

### 11.1. Tạo compound index

~~~javascript
db.people.createIndex(
  { groupId: 1, name: 1 },
  {
    name: "idx_group_name_en_strength2",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

`groupId` được lưu Int32, còn `name` là string.

### 11.2. Query chỉ lọc groupId

~~~javascript
db.people.find({
  groupId: NumberInt(10)
}).collation({
  locale: "simple"
}).explain("executionStats");
~~~

Dù index được tạo với `en/strength:2` và query dùng simple, MongoDB vẫn **có thể** tận dụng phần tiền tố `groupId` không phải string, vì phép bằng số nguyên không phụ thuộc quy tắc so sánh chuỗi.

Tuy nhiên, query planner không buộc phải chọn index đó khi collection nhỏ hoặc có index khác tối ưu hơn.

### 11.3. Query lọc groupId và name

~~~javascript
db.people.find({
  groupId: NumberInt(10),
  name: "lan"
}).collation({
  locale: "simple"
}).explain("executionStats");
~~~

Index có thể hỗ trợ phần `groupId`, nhưng phần so sánh `name` với simple collation **không tương đương** phần khóa string của index `en/strength:2`. Server có thể phải đọc và lọc thêm document hoặc chọn kế hoạch khác.

Khi dùng cùng collation với index:

~~~javascript
db.people.find({
  groupId: NumberInt(10),
  name: "lan"
}).collation({
  locale: "en",
  strength: 2
}).explain("executionStats");
~~~

index có khả năng phục vụ đồng thời các điều kiện phù hợp theo cấu trúc key pattern, tùy optimizer và thống kê.

### 11.4. Đừng suy luận “colllation mismatch ⇒ không bao giờ dùng index”

Quy tắc đúng cần nhớ:

- **So sánh string:** để tận dụng index đúng cách, collation phải tương thích.
- **Phần khóa không phải string:** một compound index vẫn có thể được dùng cho điều kiện trên prefix đó ngay cả khi collation truy vấn khác.
- **Sort string:** index phải có ngữ nghĩa thứ tự phù hợp; nếu không, có thể phải sort lại.
- **Plan thực tế:** luôn xác nhận bằng explain, không kết luận chỉ từ tên index.

Ví dụ này là lý do cần đọc `indexBounds`, `FETCH` và số khóa/document được quét, thay vì chỉ nhìn thấy `IXSCAN` rồi coi toàn bộ query đã được index tối ưu.

## 12. Collation trong aggregation và các API truy vấn khác

### 12.1. Aggregation chỉ định collation ở cấp operation

Ví dụ gom nhóm người theo tên bằng collation không phân biệt hoa/thường:

~~~javascript
db.people.aggregate(
  [
    {
      $group: {
        _id: "$name",
        count: { $sum: 1 },
        ids: { $push: "$_id" }
      }
    },
    {
      $sort: { _id: 1 }
    }
  ],
  {
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Collation của aggregation có thể ảnh hưởng cách so sánh chuỗi trong `$group` và `$sort`. Với bộ dữ liệu, các biến thể `Lan/lan/LAN` có thể thuộc cùng nhóm theo collation strength 2.

Đừng xem tên `_id` đại diện của nhóm là một dạng chữ viết canonical do MongoDB chủ động chuẩn hóa. Nếu ứng dụng cần một khóa hiển thị duy nhất ổn định, hãy định nghĩa canonical value riêng.

### 12.2. Aggregation match và sort

~~~javascript
db.people.aggregate(
  [
    { $match: { name: "lan" } },
    { $sort: { name: 1, _id: 1 } },
    { $project: { _id: 1, name: 1 } }
  ],
  {
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Tương tự `find()`, truy vấn aggregation muốn dùng index string hiệu quả cần collation tương thích và pipeline đủ điều kiện để optimizer khai thác index.

Collation của aggregation là tùy chọn **cấp operation**, không phải một cấu hình tùy ý khác nhau cho từng `$match` và `$sort` stage trong cùng command.

### 12.3. countDocuments có collation

~~~javascript
db.people.countDocuments(
  { name: "lan" },
  {
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Với dữ liệu mẫu và collection không có record khác, kết quả là **3**. Nếu đếm không chỉ định collation, collection `people` dùng simple, nên `name: "lan"` chỉ khớp một document trong bộ mẫu.

Đây là tình huống dễ gây nhầm trong API phân trang: dữ liệu trang được truy vấn case-insensitive, nhưng count lại dùng simple. Khi đó `items` và `total` không còn diễn tả cùng tập dữ liệu.

### 12.4. distinct và collation

Một số API đọc giá trị khác nhau cũng hỗ trợ collation. Để thể hiện đầy đủ tùy chọn mà không phụ thuộc biến thể helper trong shell, có thể dùng database command:

~~~javascript
db.runCommand({
  distinct: "people",
  key: "name",
  query: {},
  collation: {
    locale: "en",
    strength: 2
  }
});
~~~

Cách hiểu tính khác nhau của chuỗi phụ thuộc collation chỉ định. Khi muốn làm báo cáo số lượng tên hoặc giá trị unique, phải thống nhất quy tắc đó với nghiệp vụ và index.

### 12.5. Một operation không tùy ý trộn nhiều collation

Nếu một câu truy vấn vừa lọc vừa sort chuỗi, collation của operation thường áp dụng nhất quán cho các phép so sánh chịu ảnh hưởng. Khi một yêu cầu muốn `name` không phân biệt hoa/thường nhưng `code` phải so sánh binary chính xác, bạn cần thiết kế mô hình dữ liệu và filter phù hợp, thay vì kỳ vọng có thể gắn hai collation độc lập vào hai field trong cùng một truy vấn thông thường.

Một chiến lược là lưu field canonical riêng, chẳng hạn `nameNormalized`, `codeExact`, với quy tắc sinh giá trị rõ ràng. Nhưng mọi field bổ sung có chi phí đồng bộ và phải được cập nhật nhất quán.

## 13. $regex và index case-insensitive: ngoại lệ thường bị bỏ qua

Một hiểu nhầm phổ biến là: “Đã có index case-insensitive thì mọi truy vấn regex không phân biệt hoa/thường sẽ tự chạy nhanh.”

Ví dụ:

~~~javascript
db.people.find({
  name: /^lan/i
});
~~~

`$regex` không collation-aware theo cách phép so sánh bằng/sort dựa trên ICU collation. Vì vậy **case-insensitive collation index thường không làm tăng tốc hiệu quả cho truy vấn `$regex` không phân biệt hoa/thường**.

Thêm collation vào truy vấn:

~~~javascript
db.people.find({
  name: /^lan/i
}).collation({
  locale: "en",
  strength: 2
});
~~~

không tự biến phép regex thành equality lookup theo index collation.

### 13.1. Phân biệt ba bài toán

| Nhu cầu | Cách tiếp cận |
|---|---|
| Tìm chính xác tên nhưng không phân biệt hoa/thường | Equality query + collation tương thích + index |
| Tìm chuỗi bắt đầu bằng một prefix | Regex có prefix, hoặc cấu trúc dữ liệu tìm kiếm phù hợp; cần đo plan |
| Tìm gần đúng, full-text, autocomplete có phân tích ngôn ngữ | Công cụ search/index phù hợp nhu cầu, không mặc định dùng collation index |

Một regex có prefix phân biệt hoa/thường có thể tận dụng index trong những trường hợp phù hợp, nhưng điều đó khác với việc một index strength 2 tự tối ưu mọi pattern `/i`.

### 13.2. Khi nào lưu trường đã chuẩn hóa?

Nếu ứng dụng cần tìm prefix không phân biệt hoa/thường theo logic cố định, có thể cân nhắc lưu `nameSearch` đã được chuẩn hóa, có index phù hợp, rồi dùng một phương pháp truy vấn được thiết kế cho prefix. Tuy nhiên:

- Quy tắc chuẩn hóa Unicode và ngôn ngữ phải rõ ràng.
- Chuẩn hóa theo lower-case có thể không tương đương mọi quy tắc locale.
- Dữ liệu gốc vẫn cần lưu để hiển thị.
- Khi sửa tên, cả field gốc và field chuẩn hóa phải được cập nhật đồng bộ.
- Với tìm kiếm nâng cao, giải pháp search chuyên dụng có thể phù hợp hơn.

Không sử dụng normalization như một cách tự động thay thế mọi collation mang tính ngôn ngữ.

## 14. Collation và phân trang: filter, sort, count phải thống nhất

Giả sử API danh sách người dùng cần:

~~~text
GET /people?name=lan&pageSize=2
~~~

Quy tắc nghiệp vụ: không phân biệt hoa/thường, phân biệt dấu.

Filter:

~~~javascript
const filter = { name: "lan" };
const ciCollation = { locale: "en", strength: 2 };
~~~

Truy vấn trang:

~~~javascript
const items = db.people.find(filter)
  .sort({ name: 1, _id: 1 })
  .collation(ciCollation)
  .limit(2)
  .toArray();
~~~

Count phải dùng cùng collation:

~~~javascript
const total = db.people.countDocuments(
  filter,
  { collation: ciCollation }
);
~~~

Với ba document `Lan/lan/LAN`, tổng chính xác theo bộ dữ liệu mẫu là **3**; trang đầu tối đa **2** document.

### 14.1. Vì sao count có thể sai?

Lỗi:

~~~javascript
const items = db.people.find({ name: "lan" })
  .collation({ locale: "en", strength: 2 })
  .limit(2)
  .toArray();

const total = db.people.countDocuments({ name: "lan" });
~~~

Ở collection `people` có default simple, count thứ hai chỉ khớp `"lan"`, trong khi query lấy trang nhìn thấy cả các biến thể khác. API có thể hiển thị 2 items nhưng `total = 1`: mâu thuẫn đến từ **collation khác nhau**, không phải lỗi của toán tử count.

### 14.2. Seek pagination theo chuỗi có collation

Nếu phân trang theo `name` rồi `_id`, điều kiện chuyển sang trang sau phải theo cùng quy tắc sắp xếp. Không nên lấy token theo simple collation rồi dùng lại cho truy vấn strength 2.

Thông tin trong token nên gắn với:

- Locale và các tùy chọn collation.
- Thứ tự sort và khóa tie-breaker.
- Bộ lọc/tenant và phạm vi quyền.
- Giá trị BSON của khóa cuối trang trước.

Khi thay đổi phiên bản chính sách sort hoặc collation, có thể cần vô hiệu hóa token cũ để tránh nhảy/lặp document.

### 14.3. Collation-aware equality có thể tạo các khóa sort ngang nhau

Với `strength: 2`, `Lan`, `lan`, `LAN` có thể tương đương trong so sánh chuỗi. Nếu chỉ sắp xếp `{name:1}`, thứ tự giữa chúng có thể không đủ quyết định cho phân trang.

Thêm `_id` vào sort và có index phù hợp giúp xác định thứ tự. Tuy nhiên, nếu `_id` cũng là string, phép so sánh khóa phụ có thể chịu ảnh hưởng của collation; cần xác định thứ tự và tính duy nhất theo cấu trúc dữ liệu thật. Bộ ví dụ dùng `_id` dạng số nên khóa phụ không chịu khác biệt chữ hoa/thường.

## 15. Kiểm tra collation của index bằng metadata

Công cụ quan trọng nhất là:

~~~javascript
db.people.getIndexes();
~~~

Đầu ra có thể chứa các object với `key`, `name`, `collation`, `unique` và trường liên quan.

Ví dụ mô tả:

~~~javascript
[
  {
    name: "idx_name_en_strength2",
    key: { name: 1 },
    collation: {
      locale: "en",
      strength: 2
      // Một số thuộc tính mặc định khác có thể hiện ra.
    }
  },
  {
    name: "idx_name_simple",
    key: { name: 1 }
  }
]
~~~

Các index có simple collation có thể không hiển thị object collation tường minh giống index locale-aware; điều quan trọng là xác nhận ý nghĩa cấu hình từ kết quả thật.

Xem collection default:

~~~javascript
db.getCollectionInfos({ name: "people" });
db.getCollectionInfos({ name: "catalogDefaultCI" });
~~~

Cần phân biệt:

- `options.collation` của collection: default cho thao tác/index khi không override.
- `collation` của từng index: cách index xử lý string.
- `collation(...)` hoặc option của mỗi operation: cách truy vấn so sánh/sort string.

### 15.1. Checklist chẩn đoán vì sao index không được chọn

Khi query có kết quả đúng nhưng chậm, lần lượt xem:

1. **Trường và key pattern:** index có chứa đúng field lọc/sort không?
2. **Operation collation:** query dùng simple, `en`, `vi` hay một cấu hình khác?
3. **Index collation:** có `locale`, `strength` và tùy chọn tương ứng không?
4. **Collection default:** truy vấn không khai báo có đang thừa kế default khác mong đợi không?
5. **Type:** field là string, number, Date hay hỗn hợp BSON?
6. **Filter và sort:** có tiền tố key phù hợp không, có sort blocking không?
7. **Predicate đặc biệt:** có regex hay biểu thức không được tối ưu như equality không?
8. **Dữ liệu/độ chọn lọc:** index có giúp giảm đáng kể số document/keys được đọc không?
9. **Plan:** `explain` báo `IXSCAN`, `COLLSCAN`, `FETCH`, `SORT` như thế nào?
10. **Quy mô thử nghiệm:** collection có quá nhỏ khiến full scan rẻ hơn không?

Các bước này chỉ là thao tác phân tích query plan; không đồng nghĩa phải tạo hoặc xóa index ngay.

## 16. Dữ liệu đa ngôn ngữ và yêu cầu nghiệp vụ

### 16.1. Một collection chứa tên từ nhiều quốc gia

Nếu dữ liệu có tên tiếng Việt, tiếng Anh, tiếng Pháp và các chuỗi kỹ thuật, một collation mặc định duy nhất có thể không phù hợp với mọi trường.

Ví dụ:

- `displayName` có thể cần sort theo locale của từng giao diện.
- `username` có thể được quy định dạng chuẩn hóa cố định, không phụ thuộc locale của người xem.
- `productCode` thường cần so sánh định danh chính xác.
- `description` cần tìm kiếm theo từ, không chỉ so sánh equality.

Tránh dùng một index case-insensitive theo `en` rồi mặc định mọi giao diện ngôn ngữ đều có cùng thứ tự mong đợi.

### 16.2. Khi nào tạo nhiều index collation?

Có thể hợp lý nếu ứng dụng thật sự có hai workload quan trọng:

~~~text
Workload A: tra cứu name không phân biệt hoa/thường theo en
Workload B: sort name binary để đồng bộ dữ liệu kỹ thuật
~~~

Khi đó hai index cùng key pattern nhưng collation khác nhau có thể phục vụ hai nhu cầu. Tuy nhiên, nếu ứng dụng chỉ dùng một kiểu so sánh, một index phù hợp thường đơn giản hơn.

Với nhiều locale được lựa chọn động từ người dùng, việc tạo một index cho mọi locale có thể tăng chi phí lớn. Cần xác định các locale thực sự được dùng, phân tích truy vấn, và cân nhắc mô hình search khác nếu bài toán đòi hỏi sắp xếp đa ngôn ngữ quá linh hoạt.

### 16.3. Không coi collation là phương pháp làm sạch dữ liệu

Collation có thể làm `"Lan"` và `"lan"` khớp nhau trong truy vấn, nhưng nó không tự sửa các giá trị lưu trên server.

Nếu nghiệp vụ cần:

- Username chỉ chứa một tập ký tự cho phép.
- Email được chuẩn hóa và duy nhất.
- Tên người được lưu nguyên bản nhưng có field tìm kiếm riêng.
- SKU theo định dạng và kiểu dữ liệu ổn định.

thì cần phối hợp schema validation, logic ứng dụng và unique index theo hợp đồng dữ liệu. Collation chỉ là **quy tắc so sánh**, không phải quy trình chuẩn hóa tổng quát.

## 17. MongoDB Compass: xem index và thử query

MongoDB Compass giúp kiểm tra document, định nghĩa index và thực thi filter bằng giao diện. Tên tab/nút có thể thay đổi theo phiên bản, nhưng quy trình thực hành cơ bản:

1. Kết nối Compass tới cùng MongoDB Server/cluster đang dùng trong `mongosh`.
2. Mở database `collation_index_lab` và collection `people`.
3. Vào phần **Indexes**, xem hai index `idx_name_en_strength2` và `idx_name_simple` cùng cấu hình nếu UI hiển thị.
4. Mở tab **Documents** và thử filter:

   ~~~json
   {"name":"lan"}
   ~~~

5. Kiểm tra phần **Collation/Options** trong giao diện truy vấn nếu phiên bản Compass hỗ trợ. Đặt `locale: "en"`, `strength: 2` rồi so sánh kết quả với thao tác simple.
6. Nếu Compass có **Explain Plan**, đối chiếu tên index được chọn và số document/keys examined.
7. Dùng `mongosh` để chạy cùng truy vấn với `.collation(...)` và xác nhận kết quả trên server.
8. Thử query `name: "cafe"` ở strength 1 và strength 2, quan sát sự khác nhau về dấu.
9. Nếu muốn kiểm tra unique case-insensitive, dùng collection `accountsUnique` ở mục 10 và đối chiếu lỗi duplicate key.

Không mặc định mọi bản Compass đều có cùng giao diện đặt collation cho Documents query. Khi giao diện không cho phép chỉ định đầy đủ tùy chọn, dùng mongosh để kiểm tra chính xác.

## 18. Collation trong MongoDB Java Driver

Ví dụ Java Driver với `Filters`, `Collation` và `CollationStrength`. Giả sử `database` đã là một `MongoDatabase` được kết nối đúng:

~~~java
import static com.mongodb.client.model.Filters.eq;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Collation;
import com.mongodb.client.model.CollationStrength;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

MongoCollection<Document> people =
    database.getCollection("people");

Collation caseInsensitive = Collation.builder()
    .locale("en")
    .collationStrength(CollationStrength.SECONDARY)
    .build();

List<Document> items = people.find(eq("name", "lan"))
    .collation(caseInsensitive)
    .into(new ArrayList<>());

System.out.println("Matching people: " + items.size());
~~~

`CollationStrength.SECONDARY` tương ứng với strength 2 trong ngữ cảnh API này.

### 18.1. Tạo index từ Java

~~~java
import static com.mongodb.client.model.Indexes.ascending;

import com.mongodb.client.model.IndexOptions;

String indexName = people.createIndex(
    ascending("name"),
    new IndexOptions()
        .name("idx_name_ci_java")
        .collation(caseInsensitive)
);
~~~

Ví dụ chỉ minh họa API. Nếu index tương tự đã tồn tại hoặc cấu hình đụng tên index cũ, cần quản lý tên/chính sách tạo index rõ ràng. Không chạy lệnh tạo index mới mỗi request của ứng dụng.

### 18.2. Count phải cùng collation

~~~java
import com.mongodb.client.model.CountOptions;

long total = people.countDocuments(
    eq("name", "lan"),
    new CountOptions().collation(caseInsensitive)
);
~~~

Nếu query lấy trang dùng collation strength 2 mà count không dùng, số total có thể khác số document hiển thị. Bộ lọc, tenant, quyền, collation và các tùy chọn ảnh hưởng ngữ nghĩa đều phải được chia sẻ giữa hai câu truy vấn.

### 18.3. Collation trong aggregation

~~~java
import static com.mongodb.client.model.Aggregates.match;
import static com.mongodb.client.model.Aggregates.sort;
import static com.mongodb.client.model.Sorts.ascending;

import org.bson.conversions.Bson;

import java.util.List;

List<Bson> pipeline = List.of(
    match(eq("name", "lan")),
    sort(ascending("name", "_id"))
);

List<Document> result = people.aggregate(pipeline)
    .collation(caseInsensitive)
    .into(new ArrayList<>());
~~~

Đoạn code là phần thao tác truy vấn, không phải chương trình độc lập. Trong dự án sử dụng Spring Data MongoDB, cần kiểm tra cách framework truyền collation vào query/aggregation thay vì mặc định mọi repository method sẽ dùng đúng cấu hình.

## 19. Các lỗi và hiểu nhầm thường gặp

| Hiện tượng hoặc hiểu nhầm | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| Index có `name` nhưng query case-insensitive vẫn chậm | Index simple, query dùng `en/strength:2` | Tạo/khai thác index có collation tương thích và đo explain |
| Query có kết quả đúng nhưng `COLLSCAN` | Không có index phù hợp, dữ liệu nhỏ hoặc planner chọn scan | Kiểm tra index, collation, selectivity, không suy ra lỗi chỉ từ scan |
| Tìm `lan` không thấy `Lan` | Dùng simple collation | Khai báo collation phù hợp hoặc dùng collection default tương ứng |
| Tìm `cafe` lại thấy `café` | Strength bỏ qua dấu | Chọn strength phân biệt dấu nếu nghiệp vụ cần |
| Unique index case-insensitive không tạo được | Dữ liệu cũ trùng theo collation mới | Khảo sát/chuẩn hóa dữ liệu trước khi tạo |
| Hai index cùng field tạo lỗi tên | Không đặt tên phân biệt hoặc cấu hình xung đột | Dùng tên riêng, xem `getIndexes()` |
| Tạo index có collation nhưng query không dùng index | Operation mặc định simple hoặc collation khác | Chỉ định collation tương ứng trên query |
| Collection có default CI nhưng muốn so sánh exact | Query thừa kế CI mặc định | Override `locale:"simple"` và có index simple nếu cần hiệu năng |
| `countDocuments` cho total khác list | Count thiếu collation hoặc filter khác | Dùng cùng filter/collation/phạm vi quyền |
| Index CI không tăng tốc regex `/i` | Regex không collation-aware giống equality | Dùng thiết kế prefix/search phù hợp, đo plan |
| Sort chậm dù có index field | Index collation/sort order không phù hợp | Dùng index phục vụ đúng sort và collation |
| `numericOrdering` cho số âm/thập phân không như mong đợi | Đây là quy tắc chuỗi chữ số, không phải numeric field | Lưu kiểu BSON số nếu cần toán học |
| Compound index vẫn hiện `IXSCAN` khi collation lệch | Index có thể dùng prefix không-string | Xem `indexBounds`, `FETCH`, totalKeysExamined |
| Cùng locale nhưng khác strength lại xem như tương đương | Strength ảnh hưởng phân biệt case/dấu | Kiểm tra toàn bộ tùy chọn collation |
| Truy vấn đa ngôn ngữ cho thứ tự không mong muốn | Locale không phù hợp với người dùng/dữ liệu | Xác định locale thực tế và test với dữ liệu đại diện |
| Tên được tìm case-insensitive nhưng dữ liệu lưu vẫn mixed case | Collation chỉ quy định so sánh | Chuẩn hóa khi ghi hoặc dùng field canonical nếu cần |
| Phân trang lặp/bỏ document | Sort không có tie-break hoặc cursor thiếu collation | Thêm khóa unique, giữ filter/sort/collation ổn định |

## 20. Bài tập thực hành

Các bài dưới đây dùng collection `collation_index_lab.people` có 7 record mẫu, cùng hai index đã tạo ở mục 5. Nếu có dữ liệu khác, kết quả ID có thể thay đổi.

### Bài 1. So sánh simple và case-insensitive

Chạy:

~~~javascript
db.people.find(
  { name: "lan" },
  { _id: 1, name: 1 }
).sort({ _id: 1 });

db.people.find(
  { name: "lan" },
  { _id: 1, name: 1 }
).collation({
  locale: "en",
  strength: 2
}).sort({ _id: 1 });
~~~

Kết quả mong đợi:

- Simple: ID **2**.
- Strength 2: ID **1, 2, 3**.

Giải thích vì sao trường và giá trị filter không đổi nhưng kết quả khác nhau.

### Bài 2. Phân biệt dấu

So sánh:

~~~javascript
db.people.find(
  { name: "cafe" },
  { _id: 1, name: 1 }
).collation({
  locale: "en",
  strength: 1
}).sort({ _id: 1 });

db.people.find(
  { name: "cafe" },
  { _id: 1, name: 1 }
).collation({
  locale: "en",
  strength: 2
}).sort({ _id: 1 });
~~~

Ở strength 1, `cafe` và `café` có thể cùng khớp (ID **4, 5**). Ở strength 2, kỳ vọng chỉ ID **4** theo quy tắc dấu trong ví dụ. Rút ra yêu cầu chọn strength dựa trên nghiệp vụ.

### Bài 3. Đọc định nghĩa index

~~~javascript
db.people.getIndexes();
~~~

Tìm tên, key pattern và collation của:

- `idx_name_en_strength2`.
- `idx_name_simple`.

Nếu UI hoặc output không hiện tất cả thuộc tính mặc định, vẫn phải phân biệt index có collation được khai báo với index simple.

### Bài 4. Explain với hai collation

~~~javascript
db.people.find({ name: "lan" })
  .collation({ locale: "en", strength: 2 })
  .explain("executionStats");

db.people.find({ name: "lan" })
  .collation({ locale: "simple" })
  .explain("executionStats");
~~~

Ghi nhận `winningPlan`, `indexName` (nếu có), `totalKeysExamined` và `totalDocsExamined`. Giải thích vì sao trên 7 document, `COLLSCAN` không tự có nghĩa index sai.

### Bài 5. Unique email không phân biệt hoa/thường

Tạo `accountsUnique` và index mục 10. Chèn:

~~~javascript
db.accountsUnique.insertOne({
  _id: "acc-101",
  email: "Student@example.test"
});
~~~

Sau đó thử:

~~~javascript
db.accountsUnique.insertOne({
  _id: "acc-102",
  email: "student@example.test"
});
~~~

**Kỳ vọng:** Lệnh sau có thể bị từ chối vì unique index coi hai chuỗi tương đương. Nêu vì sao việc bỏ unique index hoặc thay strength có thể làm thay đổi định nghĩa “trùng”.

### Bài 6. Collection default collation

Xem:

~~~javascript
db.getCollectionInfos({ name: "catalogDefaultCI" });
db.catalogDefaultCI.getIndexes();
~~~

Giải thích vì sao query không ghi `.collation()` trên collection này vẫn có thể là case-insensitive. Sau đó thử override `{locale:"simple"}` và đối chiếu kết quả.

### Bài 7. Count và list có cùng collation

~~~javascript
const query = { name: "lan" };
const ci = { locale: "en", strength: 2 };

const total = db.people.countDocuments(
  query,
  { collation: ci }
);

const items = db.people.find(query)
  .collation(ci)
  .limit(2)
  .toArray();

printjson({
  total: total,
  pageItems: items.length
});
~~~

**Kết quả:** `total = 3`, `pageItems = 2`.

Thử bỏ collation của count. Vì sao total có thể thành 1 và không phù hợp với kết quả trang?

### Bài 8. numericOrdering

~~~javascript
db.people.find(
  {},
  { _id: 1, code: 1 }
).sort({ code: 1 })
.collation({
  locale: "en",
  numericOrdering: true
});
~~~

So sánh thứ tự `item1`, `item2`, `item10` với query dùng simple collation. Khi nào nên lưu số riêng thay vì tận dụng numeric ordering?

### Bài 9. Compound index có prefix số

Tạo index:

~~~javascript
db.people.createIndex(
  { groupId: 1, name: 1 },
  {
    name: "idx_group_name_en_strength2",
    collation: { locale: "en", strength: 2 }
  }
);
~~~

Chạy:

~~~javascript
db.people.find({
  groupId: NumberInt(10),
  name: "lan"
}).collation({
  locale: "simple"
}).explain("executionStats");
~~~

Giải thích vì sao index có thể hỗ trợ phần `groupId` nhưng không dùng được phần so sánh tên như query theo simple collation.

### Bài 10. Regex và collation

~~~javascript
db.people.find({
  name: /^lan/i
}).collation({
  locale: "en",
  strength: 2
}).explain("executionStats");
~~~

Giải thích vì sao sự tồn tại của index case-insensitive không bảo đảm regex `/i` được tối ưu giống equality query `{name:"lan"}` với collation strength 2.

### Bài 11. Lựa chọn collation cho nghiệp vụ

| Nhu cầu | Một cách tiếp cận phù hợp |
|---|---|
| Tìm tên không phân biệt hoa/thường nhưng phân biệt dấu | Equality với locale phù hợp, strength 2 và index tương thích |
| Tìm tên không phân biệt cả hoa/thường và dấu | Xem strength 1, kiểm tra dữ liệu thực tế |
| So sánh mã sản phẩm chính xác theo byte | Simple collation hoặc khóa canonical được quản lý riêng |
| Unique username không phân biệt case | Unique index có collation phù hợp và chính sách canonical |
| Sort chuỗi có số như item2/item10 | `numericOrdering:true` hoặc lưu số riêng |
| Tìm prefix bất kỳ không phân biệt case | Không mặc định index collation hỗ trợ regex `/i`; thiết kế search phù hợp |
| Phân trang theo tên locale-aware | Cùng collation cho filter, sort, count, seek và tie-breaker unique |
| Có nhiều locale người dùng | Khảo sát workload/index, không tạo vô hạn index theo mọi locale |

## 21. Nguyên tắc triển khai index collation trong dự án

1. **Xác định ngữ nghĩa trước khi tạo index.** Phân biệt yêu cầu chính xác byte, không phân biệt case, không phân biệt dấu hoặc sort theo ngôn ngữ.
2. **Chọn locale và strength phù hợp.** Đừng coi mọi phép so sánh chuỗi có cùng một định nghĩa “bằng nhau”.
3. **Đồng bộ operation với index.** Filter, sort, count và aggregation phải dùng collation tương thích để vừa cho kết quả đúng vừa có cơ hội tận dụng index.
4. **Hiểu collection default.** Query không ghi collation có thể thừa kế default, không nhất thiết là simple.
5. **Không quên unique semantics.** Unique index dựa trên collation có thể cấm các chuỗi khác hình thức nhưng tương đương về so sánh.
6. **Đánh giá prefix compound index.** Collation khác không loại trừ mọi khả năng dùng index với các trường không phải string.
7. **Không nhầm equality với regex.** Case-insensitive collation index không tự tối ưu mọi truy vấn regex có cờ `i`.
8. **Sử dụng explain thực tế.** Xem indexName, indexBounds, keys/docs examined và SORT; tránh kết luận chỉ từ key pattern.
9. **Giữ nhất quán pagination.** Cùng filter, sort, collation và khóa duy nhất ở trang và count; token seek phải gắn với chính sách sort.
10. **Tính chi phí duy trì index.** Nhiều index khác collation nghĩa là nhiều vùng lưu trữ và công việc cập nhật khi ghi.
11. **Làm sạch dữ liệu trước unique index mới.** Dữ liệu đã tồn tại có thể trùng dưới quy tắc collation được chọn.
12. **Tài liệu hóa chính sách.** Khi API thay collation hoặc chuẩn hóa mới, kiểm tra khả năng tương thích dữ liệu và các consumer hiện có.

Collation giúp MongoDB so sánh và sắp xếp chuỗi theo cách phù hợp với ngôn ngữ và nghiệp vụ. Tuy nhiên, **một index chỉ thật sự hỗ trợ hiệu quả những thao tác có ngữ nghĩa so sánh tương thích với nó**. Nắm rõ sự liên hệ giữa collection default, index collation và operation collation là nền tảng để thiết kế truy vấn đúng kết quả, tránh lỗi trùng dữ liệu và tối ưu hiệu năng bền vững.

## Tài liệu tham khảo

- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/)
- [MongoDB Manual — Indexes and Collation](https://www.mongodb.com/docs/manual/core/index-case-insensitive/)
- [MongoDB Manual — createIndex](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
