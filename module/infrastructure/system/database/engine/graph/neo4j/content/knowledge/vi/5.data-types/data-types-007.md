# Giới hạn khi lưu danh sách, bản đồ và cấu trúc lồng nhau trong Neo4j

Trong Neo4j, một `node` hoặc `relationship` chứa các **property** dạng cặp khóa–giá trị. Cypher cho phép tạo và xử lý `LIST`, `MAP`, thậm chí danh sách bản đồ nhiều tầng, nhưng **không phải mọi giá trị Cypher đều lưu trực tiếp thành property**. Hiểu ranh giới này giúp tránh lỗi khi nhập JSON, truyền tham số từ Java và thiết kế dữ liệu đồ thị.

Bài thuộc chương **Kiểu dữ liệu**, tập trung vào việc dùng Neo4j để mô hình hóa dữ liệu liên kết theo *property graph*, truy vấn quan hệ và đường đi bằng Cypher. Các tình huống liên quan đến nhập dữ liệu, Java Driver và Spring Data Neo4j được đặt trong cùng nguyên tắc: dữ liệu đầu vào có thể lồng nhau, còn dữ liệu bền vững phải được chuyển thành **property hợp lệ** hoặc **node và relationship phù hợp**.

## 1. Hai tầng giá trị: xử lý trong Cypher và lưu xuống đồ thị

Hãy phân biệt:

1. **Giá trị trong biểu thức, tham số và kết quả truy vấn:** Cypher cho phép `MAP`, `LIST` chứa nhiều kiểu, `LIST<MAP>` và cấu trúc lồng nhau. Chúng hữu ích cho `WITH`, `RETURN`, `UNWIND`, truyền tham số và tạo kết quả cho API.
2. **Giá trị của một property trên node/relationship:** Neo4j chỉ chấp nhận các **property value** được hỗ trợ. Với danh sách, trường hợp lưu được thông thường là **danh sách đồng nhất của các giá trị đơn giản, không có `null`**. `MAP` và cấu trúc lồng nhiều cấp không phải là property value hợp lệ.

Ví dụ sau **hợp lệ** vì dữ liệu chỉ tồn tại trong quá trình truy vấn:

~~~cypher
WITH {
  theme: 'dark',
  contacts: [
    {kind: 'home', city: 'Hà Nội'},
    {kind: 'work', city: 'Đà Nẵng'}
  ]
} AS settings
RETURN settings.theme AS theme,
       settings.contacts[0].city AS firstCity;
~~~

Ngược lại, lệnh này **không hợp lệ khi gán property**:

~~~cypher
MERGE (u:User {id: 'u-007'})
SET u.settings = {
  theme: 'dark',
  contacts: [{kind: 'home', city: 'Hà Nội'}]
};
~~~

Nguyên nhân là giá trị của `u.settings` là `MAP`. Việc `MAP` hợp lệ ở câu lệnh `WITH` không có nghĩa là có thể đặt nó vào một property.

> **Quy tắc cốt lõi:** “Cypher đọc được/nhận tham số được” khác với “Neo4j lưu trực tiếp được vào một property”. Quy tắc áp dụng như nhau cho property trên node và trên relationship.

## 2. Những cấu trúc nào lưu trực tiếp được?

| Giá trị cần lưu | Ví dụ | Kết quả ở property | Lý do |
| --- | --- | --- | --- |
| Giá trị vô hướng | `'Lan'`, `42`, `true`, `date('2026-01-01')` | Được | Thuộc nhóm property value được hỗ trợ |
| Danh sách chuỗi | `['java', 'neo4j']` | Được | Các phần tử cùng kiểu `STRING` |
| Danh sách số nguyên | `[10, 20, 30]` | Được | Các phần tử cùng kiểu `INTEGER` |
| Danh sách ngày | `[date('2026-01-01'), date('2026-02-01')]` | Được | Danh sách đồng nhất kiểu ngày |
| Danh sách lẫn chuỗi và số | `[1, 'hai', 3]` | Không | Kiểu phần tử không đồng nhất |
| Danh sách chứa `null` | `['java', null]` | Không | Danh sách lưu dưới dạng property không được chứa `null` |
| Bản đồ | `{theme: 'dark', alerts: true}` | Không | `MAP` không phải property value |
| Danh sách bản đồ | `[{city: 'Huế'}, {city: 'Hà Nội'}]` | Không | Mỗi phần tử là `MAP` |
| Danh sách lồng danh sách | `[[1, 2], [3, 4]]` | Không | Phần tử của danh sách ngoài lại là `LIST` |
| Node, relationship, path | Kết quả của `MATCH` | Không | Chúng là giá trị cấu trúc của đồ thị, không phải property value |

Neo4j còn có các kiểu property chuyên biệt như thời gian, khoảng thời gian, điểm không gian và một số kiểu phụ thuộc phiên bản/phiên bản thương mại. Bảng chỉ mô tả các trường hợp điển hình; không nên suy rằng mọi kiểu mới đều được lưu trong danh sách. Chẳng hạn, tài liệu hiện hành quy định không lưu danh sách chứa giá trị `VECTOR` dưới dạng property.

### 2.1. Lưu danh sách một chiều hợp lệ

~~~cypher
MERGE (u:User {id: 'u-007'})
SET u.name = 'Lan',
    u.tags = ['java', 'neo4j', 'graph'],
    u.scores = [85, 91, 88],
    u.active = true
RETURN u.id AS id, u.tags AS tags, u.scores AS scores;
~~~

`tags` và `scores` được lưu như hai property riêng. Phần tử trong mỗi danh sách đồng nhất; thứ tự phần tử trong danh sách được giữ lại.

Có thể truy cập hoặc xử lý danh sách bằng Cypher:

~~~cypher
MATCH (u:User {id: 'u-007'})
RETURN u.tags[0] AS firstTag,
       size(u.tags) AS tagCount,
       'neo4j' IN u.tags AS knowsNeo4j,
       [tag IN u.tags WHERE tag <> 'graph'] AS filteredTags;
~~~

Truy vấn trả về một danh sách mới cho `filteredTags`; không làm thay đổi property nếu chưa dùng `SET`.

### 2.2. Danh sách hỗn hợp có thể trả về nhưng không thể lưu

~~~cypher
RETURN [1, 'hai', true, null] AS mixedValues;
~~~

Lệnh `RETURN` hợp lệ. Lệnh sau sẽ lỗi khi lưu:

~~~cypher
MATCH (u:User {id: 'u-007'})
SET u.mixedValues = [1, 'hai', true, null];
~~~

Không nên chỉ xóa `null` rồi cho rằng danh sách tự động trở thành hợp lệ: các phần tử còn lại vẫn phải có **kiểu lưu trữ tương thích và đồng nhất**. Dữ liệu nhập từ JSON/API cần được kiểm tra và chuẩn hóa tại ranh giới hệ thống.

### 2.3. `null` không đồng nghĩa với “phần tử trống”

Hai thao tác rất khác nhau:

~~~cypher
MATCH (u:User {id: 'u-007'})
SET u.nickname = null;  // Xóa property nickname nếu đang tồn tại
~~~

~~~cypher
// Ví dụ không hợp lệ đối với property lưu trữ:
MATCH (u:User {id: 'u-007'})
SET u.tags = ['java', null, 'neo4j'];
~~~

Nếu nghiệp vụ cần danh sách chuỗi và muốn **loại** phần tử `null`, có thể lọc trước khi lưu:

~~~cypher
WITH ['java', null, 'neo4j'] AS incoming
MATCH (u:User {id: 'u-007'})
SET u.tags = [tag IN incoming WHERE tag IS NOT NULL]
RETURN u.tags AS tags;
~~~

Chỉ làm vậy khi việc bỏ giá trị thiếu là đúng nghiệp vụ. Nếu `null` mang nghĩa riêng (ví dụ “chưa biết điểm tại vị trí thứ hai”), hãy mô hình hóa vị trí hoặc trạng thái thiếu bằng node/property riêng; không âm thầm làm lệch chỉ số.

## 3. `MAP`: được dùng để cập nhật nhiều property, không được lưu làm một property

Một node có tập property biểu diễn như bản đồ khóa–giá trị. Vì vậy `properties(u)` trả về `MAP`, nhưng từng **giá trị** trong bản đồ đó vẫn phải thuộc kiểu lưu trữ được.

Ví dụ sau **hợp lệ**:

~~~cypher
WITH {theme: 'dark', alertsEnabled: true} AS preferences
MERGE (u:User {id: 'u-007'})
SET u += preferences
RETURN properties(u) AS properties;
~~~

`SET u += preferences` trải các cặp khóa–giá trị hợp lệ thành hai property `u.theme` và `u.alertsEnabled`. Nó **không** tạo ra property `u.preferences` chứa bản đồ.

So sánh các cách viết:

| Câu lệnh | Ý nghĩa | Hệ quả |
| --- | --- | --- |
| `SET u.theme = 'dark'` | Gán một property hợp lệ | Thêm/cập nhật `theme` |
| `SET u += {theme: 'dark'}` | Thêm/cập nhật các property có trong map | Giữ nguyên các property khác |
| `SET u = {theme: 'dark'}` | Thay thế **toàn bộ tập property** bằng map | Các property không có trong map, kể cả `id`, bị xóa |
| `SET u.preferences = {theme: 'dark'}` | Cố lưu map làm **một** property | Lỗi kiểu giá trị |
| `SET u += {preferences: {theme: 'dark'}}` | Cố trải map chứa giá trị lồng map | Lỗi vì giá trị `preferences` không lưu được |

Đặc biệt cẩn thận với `SET u = $props` khi xử lý dữ liệu nhập: thao tác thay thế này có thể xóa khóa định danh và các property khác. Với cập nhật từng phần, `SET u += $props` thường dễ kiểm soát hơn, nhưng **mọi giá trị trong `$props` vẫn phải hợp lệ**; giá trị `null` trong map cập nhật còn có nghĩa xóa property tương ứng.

## 4. Cấu trúc lồng nhau: chọn cách biểu diễn theo nhu cầu truy vấn

Giả sử ứng dụng nhận tài liệu JSON:

~~~json
{
  "id": "u-007",
  "name": "Lan",
  "tags": ["java", "neo4j"],
  "settings": {
    "theme": "dark",
    "alerts": true
  },
  "addresses": [
    {"code": "home", "city": "Hà Nội", "position": 0},
    {"code": "work", "city": "Đà Nẵng", "position": 1}
  ]
}
~~~

Không thể gán toàn bộ JSON này làm `u.document` ở dạng `MAP`. Có ba cách biểu diễn phổ biến, tùy cách sử dụng dữ liệu.

### Cách A — Trải những trường đơn giản thành property

Nếu `settings` chỉ có vài trường ổn định và thường được lọc trực tiếp:

~~~cypher
MERGE (u:User {id: 'u-007'})
SET u.name = 'Lan',
    u.tags = ['java', 'neo4j'],
    u.theme = 'dark',
    u.alertsEnabled = true;
~~~

Ưu điểm: đơn giản, đọc bằng `u.theme`, có thể khai báo chỉ mục hoặc ràng buộc phù hợp trên các property vô hướng. Nhược điểm: mất cấu trúc phân cấp ban đầu; khó quản lý trường có tên thay đổi liên tục hoặc nhiều nhóm lồng nhau cùng loại.

### Cách B — Chuyển các đối tượng con thành node và relationship

Khi `addresses` chứa nhiều bản ghi có thuộc tính riêng, cần tra cứu, sắp xếp, cập nhật hoặc liên kết sang đối tượng khác, mô hình đồ thị rõ ràng hơn:

~~~text
(:User {id: 'u-007', name: 'Lan', tags: [...]})
    ├─[:HAS_ADDRESS]─> (:Address {
    │                      userId: 'u-007',
    │                      code: 'home',
    │                      city: 'Hà Nội',
    │                      position: 0
    │                   })
    └─[:HAS_ADDRESS]─> (:Address {
                           userId: 'u-007',
                           code: 'work',
                           city: 'Đà Nẵng',
                           position: 1
                        })
~~~

Ví dụ đầy đủ để tạo các địa chỉ từ **danh sách map trong biểu thức truy vấn**:

~~~cypher
WITH [
  {code: 'home', city: 'Hà Nội', position: 0},
  {code: 'work', city: 'Đà Nẵng', position: 1}
] AS incoming
MERGE (u:User {id: 'u-007'})
WITH u, incoming
UNWIND incoming AS item
MERGE (a:Address {userId: u.id, code: item.code})
SET a.city = item.city,
    a.position = item.position
MERGE (u)-[:HAS_ADDRESS]->(a)
RETURN u.id AS userId, count(a) AS addressCount;
~~~

Ở đây `incoming` là `LIST<MAP>` **tạm thời**; `UNWIND` chuyển từng map thành một dòng để lấy các giá trị đơn giản. Mỗi địa chỉ được lưu bằng node `Address` và relationship `HAS_ADDRESS`.

Đọc lại thành cấu trúc API dạng danh sách map là **hợp lệ**:

~~~cypher
MATCH (u:User {id: 'u-007'})-[:HAS_ADDRESS]->(a:Address)
WITH u, a
ORDER BY a.position
RETURN u.id AS userId,
       collect({
         code: a.code,
         city: a.city,
         position: a.position
       }) AS addresses;
~~~

`collect({...})` tạo danh sách map **trong kết quả truy vấn**, không cố lưu nó thành một property. Nếu cần trả cả người dùng không có địa chỉ, phải xử lý trường hợp `OPTIONAL MATCH` và giá trị rỗng phù hợp.

Lưu ý thiết kế:

- Relationship không tự bảo đảm thứ tự. Nếu danh sách có thứ tự nghiệp vụ, lưu `position` trên node hoặc relationship và dùng `ORDER BY` khi dựng lại.
- Khóa `{userId, code}` trong `MERGE` chỉ là mẫu minh họa nhận diện bản ghi. Khi nhập dữ liệu đồng thời hoặc ở quy mô lớn, cần thiết kế khóa định danh và uniqueness constraint phù hợp để tránh tạo trùng.
- Node con có thể có thêm relationship (ví dụ địa chỉ thuộc khu vực), giúp khai thác ưu thế truy vấn liên kết và đường đi của Neo4j.

### Cách C — Lưu JSON đã tuần tự hóa thành chuỗi

Nếu toàn bộ cấu trúc chỉ phục vụ lưu dấu vết hoặc trao đổi nguyên trạng, ứng dụng có thể **serialize** JSON trước rồi lưu vào `STRING` như `u.profileJson`:

~~~cypher
MERGE (u:User {id: $id})
SET u.profileJson = $jsonText;
~~~

`$jsonText` phải là **chuỗi JSON** đã được ứng dụng tạo ra (chẳng hạn Jackson trong Java), không phải một `MAP` truyền trực tiếp. Đừng dùng cách này khi nghiệp vụ cần thường xuyên tìm địa chỉ theo thành phố, đi qua các mối liên hệ hoặc cập nhật riêng một phần tử: Cypher sẽ không xem nội dung chuỗi là đồ thị hay các property lồng nhau. Việc tìm kiếm, validate từng trường và cập nhật cục bộ cũng khó hơn.

### Chọn biểu diễn theo truy vấn cần thực hiện

| Nhu cầu | Biểu diễn nên cân nhắc |
| --- | --- |
| Danh sách thẻ, vài chục mã hoặc số cùng kiểu | `LIST` property |
| Các tùy chọn cấu hình nhỏ, tên trường ổn định | Các property vô hướng trên một node |
| Danh sách object có thuộc tính, ID và vòng đời riêng | Node con + relationship |
| Nhiều cấp đối tượng, cần truy vấn đường đi/quan hệ | Mô hình property graph với nhiều node và relationship |
| Payload tùy ý chỉ lưu/đọc nguyên khối, ít truy vấn nội dung | Chuỗi JSON, kèm các property chọn lọc để tra cứu |
| Mảng hai chiều, các hàng có ý nghĩa riêng | Node `Row` giữ `position` và `values` một chiều; hoặc node `Cell` nếu cần truy vấn từng ô |

Không có quy tắc “mọi array phải chuyển thành node”. Một danh sách chuỗi ngắn và ổn định thường hợp lý ở property; một danh sách đối tượng địa chỉ có thuộc tính và quan hệ nên tách thành node.

## 5. Trường hợp mảng nhiều chiều và giữ thứ tự

Giá trị này dùng được trong tính toán nhưng **không lưu trực tiếp**:

~~~cypher
RETURN [[10, 20], [30, 40]] AS matrix;
~~~

Không thể viết `SET m.cells = [[10, 20], [30, 40]]` vì mỗi phần tử của danh sách ngoài là một `LIST`. Một lựa chọn thay thế:

~~~cypher
MERGE (m:Matrix {id: 'matrix-1'})
MERGE (r0:MatrixRow {matrixId: 'matrix-1', position: 0})
SET r0.values = [10, 20]
MERGE (r1:MatrixRow {matrixId: 'matrix-1', position: 1})
SET r1.values = [30, 40]
MERGE (m)-[:HAS_ROW]->(r0)
MERGE (m)-[:HAS_ROW]->(r1);
~~~

Đọc lại:

~~~cypher
MATCH (m:Matrix {id: 'matrix-1'})-[:HAS_ROW]->(row:MatrixRow)
WITH row ORDER BY row.position
RETURN collect(row.values) AS matrix;
~~~

Kết quả `matrix` là danh sách lồng nhau, hoàn toàn hợp lệ **ở kết quả truy vấn**. Bài toán chỉ yêu cầu lưu `row.values` ở từng node dưới dạng danh sách số một chiều.

Nếu cần truy vấn từng ô hoặc đặt quan hệ giữa các ô, mô hình `(:Cell {row: ..., column: ..., value: ...})` có thể phù hợp hơn. Nếu cần đại số ma trận mật độ cao, cũng nên cân nhắc nơi lưu trữ/tính toán chuyên dụng thay vì biến toàn bộ ma trận thành vô số node.

## 6. Nhập dữ liệu lồng nhau từ Java Driver và Spring Data Neo4j

### 6.1. Java Driver: map và list là tham số hợp lệ

Java Driver có thể truyền `Map<String, Object>` và `List<?>` thành tham số Cypher. Điều này **không nới lỏng** quy tắc lưu property của Neo4j.

Ví dụ dưới đây giả định biến `driver` là một `org.neo4j.driver.Driver` đã kết nối và ứng dụng dùng Java có hỗ trợ text block:

~~~java
Map<String, Object> params = Map.of(
    "id", "u-007",
    "addresses", List.of(
        Map.of("code", "home", "city", "Hà Nội", "position", 0),
        Map.of("code", "work", "city", "Đà Nẵng", "position", 1)
    )
);

driver.executableQuery("""
    MERGE (u:User {id: $id})
    WITH u
    UNWIND $addresses AS item
    MERGE (a:Address {userId: $id, code: item.code})
    SET a.city = item.city,
        a.position = item.position
    MERGE (u)-[:HAS_ADDRESS]->(a)
    """)
    .withParameters(params)
    .execute();
~~~

Driver chấp nhận `addresses` là danh sách các `Map` **để Cypher xử lý**. Sau `UNWIND`, mã chỉ lưu `code`, `city`, `position` thành các property đơn giản. Nếu thay phần xử lý bằng `SET u.addresses = $addresses`, lệnh sẽ lỗi vì đang cố lưu `LIST<MAP>`.

Khi cần lưu JSON dưới dạng chuỗi, ứng dụng có thể dùng Jackson hoặc thư viện tương đương để biến object thành `String` trước khi truyền `$jsonText`. Không nên coi `toString(map)` là giải pháp tuần tự hóa JSON chính xác.

### 6.2. Spring Data Neo4j: phân biệt property và relationship

Với entity ánh xạ bằng Spring Data Neo4j, các trường như `String name`, `boolean active`, `List<String> tags` phù hợp với property (tùy cấu hình ánh xạ và phiên bản). Ngược lại, một collection các đối tượng `Address` mang ý nghĩa thực thể liên kết nên được mô hình hóa bằng entity `@Node` và field `@Relationship`.

Một field Java kiểu `Map<String,Object>` hoặc `List<AddressDto>` **không tự động biến cấu trúc lồng nhau thành một property native được Neo4j chấp nhận**. Nếu có converter tùy biến thành chuỗi JSON, database thực chất chỉ lưu chuỗi. Cần xem rõ mô hình lưu cuối cùng trước khi thiết kế repository query, index hoặc ràng buộc.

## 7. Hệ quả với chỉ mục, cập nhật và vận hành

**Truy vấn theo phần tử trong danh sách:** Điều kiện `'neo4j' IN u.tags` diễn tả đúng ý nghĩa, nhưng không nên mặc nhiên giả định chỉ mục property vô hướng sẽ tăng tốc việc tìm từng phần tử. Nếu truy vấn kiểu “tìm mọi người gắn tag X” là chức năng chính, hãy cân nhắc node `Tag` và relationship `HAS_TAG`, đặt index/constraint trên khóa tag, rồi kiểm tra kế hoạch bằng `EXPLAIN` hoặc `PROFILE`.

~~~cypher
MERGE (t:Tag {name: 'neo4j'})
MERGE (u:User {id: 'u-007'})
MERGE (u)-[:HAS_TAG]->(t);
~~~

**Cập nhật danh sách:** Thêm/xóa phần tử bằng cách tính danh sách mới rồi gán lại property. Ví dụ:

~~~cypher
MATCH (u:User {id: 'u-007'})
SET u.tags = coalesce(u.tags, []) + ['cypher']
RETURN u.tags;
~~~

Lệnh trên thêm phần tử ở cuối và có thể tạo giá trị trùng nếu gọi lại. Để tránh trùng, cần kiểm tra membership hoặc dùng mô hình node/relationship có khóa định danh và `MERGE` thích hợp. Đừng xem danh sách property như một tập hợp tự chống trùng.

**Dữ liệu lớn và thay đổi thường xuyên:** Một property chứa danh sách dài khiến các thao tác đọc/ghi thường liên quan đến cả giá trị danh sách, đồng thời tăng dữ liệu truyền qua Driver. Khi các phần tử cần cập nhật độc lập, phân quyền, liên kết, tìm kiếm hoặc có lịch sử riêng, các node con thường linh hoạt hơn. Không nên viện dẫn một “giới hạn số phần tử cố định” cho mọi phiên bản: hiệu năng còn tùy mô hình, kích thước giá trị, phiên bản Neo4j và truy vấn.

**Dữ liệu thiếu:** `SET n.key = null` xóa property; `[1, null, 2]` có thể là kết quả Cypher nhưng không phải danh sách property hợp lệ. Việc phân biệt “không có property”, “danh sách rỗng”, “không biết phần tử nào” cần được quy định ở tầng nghiệp vụ.

**Tính nhất quán:** Với dữ liệu nhập có object lồng nhau, hãy kiểm tra schema trước khi ghi, chọn khóa định danh ổn định, tạo uniqueness constraint phù hợp khi cần, và dùng transaction để cập nhật node cùng relationship trong một thao tác nhất quán.

## 8. Ba lỗi thiết kế cần tự nhận diện

**Tình huống 1 — Lưu hồ sơ API nguyên trạng.** API gửi `{name, preferences: {theme}, addresses: [{...}]}`. Gán toàn bộ vào `user.payload` thất bại vì `payload` là map. Hướng xử lý: lưu `name` và các cấu hình đơn giản thành property; dựng `Address` node cho các địa chỉ cần truy vấn; hoặc serialize toàn bộ payload thành JSON string nếu chỉ cần lưu nguyên trạng.

**Tình huống 2 — Thêm danh sách kết quả từ `collect()` vào node.** `collect({city: a.city})` trả về `LIST<MAP>` hợp lệ trong `RETURN`. `SET u.addresses = collect(...)` (kể cả được đưa qua `WITH` trước đó) vẫn không được vì đích là property. Cần lưu liên kết `HAS_ADDRESS` rồi chỉ dựng danh sách map khi truy vấn trả dữ liệu.

**Tình huống 3 — Đưa mảng trộn kiểu từ JSON vào `SET`.** `['neo4j', 2026, null]` có thể đi qua tham số Driver. Nếu lưu nguyên vào property, Neo4j sẽ từ chối. Cần quyết định rõ kiểu đích, chuyển đổi hoặc loại bỏ dữ liệu theo quy tắc nghiệp vụ, hay tách các thành phần thành thuộc tính/nút khác nhau.

Ghi nhớ: **`MAP` và `LIST` lồng nhau là công cụ biểu đạt mạnh trong Cypher; muốn lưu bền vững, phải biểu diễn chúng bằng property value hợp lệ hoặc bằng cấu trúc node–relationship của property graph.**

## Tài liệu tham khảo

- [Neo4j Cypher Manual — Property, structural, and constructed values](https://neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/): phân biệt các nhóm giá trị và điều kiện lưu property.
- [Neo4j Cypher Manual — Lists](https://neo4j.com/docs/cypher-manual/current/values-and-types/lists/): danh sách trong biểu thức và giới hạn khi lưu danh sách.
- [Neo4j Cypher Manual — Maps](https://neo4j.com/docs/cypher-manual/current/values-and-types/maps/): map dùng trong truy vấn.
- [Neo4j Cypher Manual — SET](https://neo4j.com/docs/cypher-manual/current/clauses/set/): gán property, `+=`, `=` và cách xử lý `null`.
- [Neo4j Java Driver Manual — Data types and mapping to Cypher types](https://neo4j.com/docs/java-manual/current/data-types/): Java values, Cypher values và tham số Driver.

