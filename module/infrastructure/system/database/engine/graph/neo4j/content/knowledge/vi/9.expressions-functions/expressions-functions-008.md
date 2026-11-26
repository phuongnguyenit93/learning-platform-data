# Xử lý dữ liệu sai kiểu hoặc thiếu thuộc tính mà vẫn giữ đúng ngữ nghĩa

Trong Neo4j, dữ liệu được biểu diễn bằng **node**, **relationship** và các thuộc tính của property graph. Cùng một nhãn `:Person` có thể có node chứa `age` dạng số nguyên, node chứa `age` dạng chuỗi, và node hoàn toàn chưa có `age`. Khi truy vấn bằng Cypher, việc ép kiểu hoặc gán giá trị mặc định một cách tùy tiện có thể biến “chưa biết”, “không hợp lệ” thành một giá trị tưởng như có thật.

Mục tiêu của bài thuộc chương **Biểu thức và hàm** là đọc, phân loại, chuyển đổi và cập nhật dữ liệu không đồng nhất một cách có kiểm soát, đồng thời giữ nguyên ý nghĩa nghiệp vụ của giá trị thiếu, giá trị sai kiểu và giá trị hợp lệ.

## 1. Phân biệt các trạng thái trước khi xử lý

Giả sử hệ thống quản lý người dùng có các thuộc tính `externalId`, `ageRaw` và `active`. Ba tình huống sau mang ý nghĩa khác nhau:

| Dữ liệu ban đầu | Ý nghĩa có thể có | Cách xử lý phù hợp |
| --- | --- | --- |
| Không có thuộc tính `ageRaw` | Chưa được cung cấp tuổi | Giữ trạng thái thiếu; không suy ra tuổi bằng 0 |
| `ageRaw = 'abc'` | Đã cung cấp nhưng không chuyển được thành tuổi | Đánh dấu dữ liệu không hợp lệ để kiểm tra |
| `ageRaw = '0'` | Tuổi bằng 0 (hợp lệ nếu miền cho phép) | Chuyển thành số 0, không coi là thiếu |
| `ageRaw = 27.5` | Số thực, không phù hợp nếu tuổi phải là số nguyên | Từ chối hoặc xử lý theo quy tắc nghiệp vụ được xác nhận |
| `active = false` | Người dùng không hoạt động | Giữ `false`; không thay bằng giá trị mặc định |
| `nickname = ''` | Chuỗi rỗng đã được lưu | Quyết định theo nghiệp vụ chuỗi rỗng có hợp lệ hay không |

Quy tắc nền tảng: **kiểm tra tính hiện diện, tính hợp lệ của kiểu/định dạng và miền giá trị trước khi chọn giá trị thay thế**. Chuyển đổi thành công về mặt kỹ thuật chưa chắc đã đúng về mặt nghiệp vụ.

### `null` trong Cypher

Khi truy cập thuộc tính không tồn tại, chẳng hạn `p.ageRaw`, Cypher trả về `null`. Thuộc tính của node/relationship không lưu giá trị `null`: lệnh `SET p.ageRaw = null` sẽ loại bỏ thuộc tính đó. Vì thế, với một node đã lưu, truy vấn `p.ageRaw IS NULL` bao gồm trường hợp không có thuộc tính.

~~~cypher
MATCH (p:Person)
RETURN p.externalId AS id,
       p.ageRaw IS NULL AS thieuTuoi,
       p.ageRaw IS NOT NULL AS coTuoi;
~~~

So sánh thông thường với `null` không hoạt động như so sánh với một giá trị cụ thể:

~~~cypher
RETURN null = null AS soSanhKhongXacDinh,
       null IS NULL AS kiemTraDung,
       coalesce(null, 0) AS macDinhBangKhong;
~~~

Kết quả của `null = null` vẫn là `null`, còn `null IS NULL` là `true`. Trong mệnh đề `WHERE`, chỉ các biểu thức cho ra `true` được giữ lại; `false` và `null` đều không giữ dòng. Vì vậy hãy dùng `IS NULL` hoặc `IS NOT NULL` để kiểm tra thiếu dữ liệu, tránh `= null` và `<> null`.

## 2. Chọn đúng công cụ Cypher

| Công cụ | Công dụng | Điểm cần lưu ý |
| --- | --- | --- |
| `IS NULL` / `IS NOT NULL` | Xác định giá trị thiếu ở vị trí đang truy cập | Không chứng minh được giá trị hiện diện là đúng kiểu |
| `coalesce(a, b, ...)` | Trả về giá trị đầu tiên khác `null` | Chỉ có ý nghĩa khi một giá trị mặc định thật sự phù hợp |
| `CASE WHEN ... THEN ... ELSE ... END` | Phân nhánh theo điều kiện nghiệp vụ | Có thể tạo nhãn trạng thái `THIEU`, `SAI`, `HOP_LE` |
| `toIntegerOrNull(x)` | Thử chuyển giá trị thành số nguyên, trả `null` nếu không chuyển được | Không tự xác minh miền giá trị; số thực có thể bị cắt phần thập phân |
| `toFloatOrNull(x)` | Thử chuyển thành số thực | Không thay cho kiểm tra đơn vị hay độ chính xác |
| `toBooleanOrNull(x)` | Thử chuyển thành boolean | Chuỗi ngoài những biểu diễn được hỗ trợ có thể cho `null` |
| `toStringOrNull(x)` | Thử chuyển thành chuỗi | Việc chuỗi hóa không bảo đảm đúng ngữ nghĩa, nhất là mã định danh |
| `trim(x)`, `toLower(x)` | Chuẩn hóa văn bản | Nên áp dụng sau khi đã bảo đảm đầu vào phù hợp |
| `=~` | Đối chiếu chuỗi với biểu thức chính quy | Thích hợp kiểm tra định dạng trước khi ép số |

Các hàm đuôi `OrNull` giúp xử lý nhiều nguồn dữ liệu không đồng nhất, nhưng **kết quả `null` sau chuyển đổi có thể có hai nguyên nhân**: đầu vào vốn thiếu hoặc đầu vào có dữ liệu nhưng không hợp lệ. Phải giữ thông tin về đầu vào trước khi chuyển đổi nếu ứng dụng cần phân biệt hai trường hợp này.

### Vì sao không luôn dùng `coalesce`?

~~~cypher
MATCH (p:Person)
RETURN p.externalId AS id,
       coalesce(p.ageRaw, 0) AS tuoiHienThi;
~~~

Truy vấn trên đưa tuổi bằng 0 cho cả người chưa từng khai báo tuổi. Nếu `0` mang nghĩa “trẻ sơ sinh”, dữ liệu hiển thị đã sai.

`coalesce` vẫn phù hợp trong ngữ cảnh **hiển thị**, chẳng hạn tên thay thế khi không có biệt danh:

~~~cypher
MATCH (p:Person)
RETURN p.externalId AS id,
       coalesce(p.nickname, p.fullName, '[Chưa có tên]') AS tenHienThi;
~~~

Cần phân biệt giá trị dành cho giao diện với dữ liệu chuẩn để lưu hoặc dùng cho tính toán, báo cáo và quyết định nghiệp vụ.

## 3. Chuẩn hóa tuổi có kiểm tra định dạng và miền giá trị

Giả định nghiệp vụ:

- Tuổi là **số nguyên từ 0 đến 120**.
- Cho phép đầu vào là số nguyên hoặc chuỗi chữ số có thể có khoảng trắng hai đầu.
- Không tự làm tròn hoặc cắt một số thập phân.
- Thiếu thuộc tính phải có trạng thái khác với dữ liệu đã nhập sai.

Truy vấn sau giữ nguyên tất cả node, đồng thời tạo hai cột: trạng thái chất lượng dữ liệu và tuổi chuẩn hóa khi hợp lệ.

~~~cypher
MATCH (p:Person)
WITH p, trim(toStringOrNull(p.ageRaw)) AS ageText
WITH p, ageText,
     CASE
       WHEN ageText =~ '^[0-9]{1,3}$'
       THEN toIntegerOrNull(ageText)
       ELSE null
     END AS ageCandidate
RETURN p.externalId AS id,
       p.ageRaw AS tuoiGoc,
       CASE
         WHEN p.ageRaw IS NULL THEN 'THIEU'
         WHEN ageCandidate IS NULL OR ageCandidate > 120 THEN 'KHONG_HOP_LE'
         ELSE 'HOP_LE'
       END AS trangThai,
       CASE
         WHEN ageCandidate IS NOT NULL AND ageCandidate <= 120
         THEN ageCandidate
         ELSE null
       END AS tuoiChuan;
~~~

Giải thích theo thứ tự xử lý:

1. `toStringOrNull` tạo biểu diễn chuỗi khi có thể; `trim` bỏ khoảng trắng hai đầu. Nếu không thể chuyển đổi, `ageText` là `null`.
2. `=~ '^[0-9]{1,3}$'` chỉ chấp nhận một đến ba chữ số. Chuỗi `'27.5'` và số thực `27.5` không được lặng lẽ biến thành `27`.
3. `toIntegerOrNull` chỉ chạy trong nhánh đầu vào đúng định dạng; kết quả vẫn cần kiểm tra ngưỡng `120`.
4. Phân loại `THIEU` dựa vào giá trị gốc trước, rồi mới xét `KHONG_HOP_LE`. Vì vậy không gộp nhầm người chưa khai báo với người khai báo sai.

Định dạng trên là **quy ước của ví dụ**. Hệ thống thực tế có thể yêu cầu không chấp nhận số có số 0 ở đầu, chỉ nhận kiểu số nguyên gốc, hoặc cho phép tuổi lớn hơn; hãy thay biểu thức chính quy và miền giá trị theo đặc tả đó.

### Thử nhanh mà không cần tạo node

~~~cypher
WITH [
  {id: 'A', age: '27'},
  {id: 'B', age: '0'},
  {id: 'C', age: '27.5'},
  {id: 'D'},
  {id: 'E', age: 25.7},
  {id: 'F', age: 'abc'},
  {id: 'G', age: null}
] AS rows
UNWIND rows AS row
WITH row,
     'age' IN keys(row) AS daGuiTruong,
     trim(toStringOrNull(row.age)) AS ageText
WITH row, daGuiTruong,
     CASE WHEN ageText =~ '^[0-9]{1,3}$'
          THEN toIntegerOrNull(ageText)
          ELSE null
     END AS ageCandidate
RETURN row.id AS id,
       CASE
         WHEN NOT daGuiTruong THEN 'KHONG_GUI_TRUONG'
         WHEN row.age IS NULL THEN 'GUI_NULL'
         WHEN ageCandidate IS NULL OR ageCandidate > 120 THEN 'KHONG_HOP_LE'
         ELSE 'HOP_LE'
       END AS trangThai,
       CASE WHEN ageCandidate <= 120 THEN ageCandidate END AS tuoiChuan
ORDER BY id;
~~~

Kỳ vọng: `A → 27`, `B → 0`; `C`, `E` và `F` không có tuổi chuẩn vì sai định dạng; `D` là **không gửi trường**, còn `G` là **có gửi trường với giá trị null**. Sự khác biệt giữa `D` và `G` thể hiện rõ trên **map đầu vào** nhờ `'age' IN keys(row)`.

Chú ý: với **thuộc tính node**, Neo4j không lưu `null` như một giá trị thuộc tính riêng biệt; nhưng với **map nhận từ tham số** (chẳng hạn từ Java Driver), việc có khóa mang giá trị `null` có thể mang nghĩa khác với không gửi khóa. Đây là điểm quan trọng khi thiết kế API cập nhật từng phần.

## 4. Bảo toàn ngữ nghĩa khi cập nhật dữ liệu

Xét API nhận các map cập nhật từ ứng dụng Java:

- Không gửi `age`: giữ nguyên tuổi đang có.
- Gửi `age: null`: chỉ xóa tuổi nếu API **quy định rõ** `null` là yêu cầu xóa.
- Gửi `age` có dữ liệu sai: thông báo lỗi hoặc ghi vào hàng chờ làm sạch, không ghi đè.
- Gửi `age` hợp lệ: lưu tuổi đã chuẩn hóa.

Không được dùng biểu thức như `coalesce(toIntegerOrNull(row.age), 0)` để ghi trực tiếp. Cách này biến dữ liệu chưa cung cấp hoặc sai kiểu thành tuổi 0. Tương tự, `SET p.age = toIntegerOrNull(row.age)` sẽ **xóa thuộc tính hiện có** nếu kết quả là `null`.

Nếu tác vụ chỉ có yêu cầu “cập nhật những hàng có tuổi hợp lệ”, có thể lọc **trước khi SET**:

~~~cypher
UNWIND $rows AS row
WITH row, trim(toStringOrNull(row.age)) AS ageText
WITH row,
     CASE WHEN ageText =~ '^[0-9]{1,3}$'
          THEN toIntegerOrNull(ageText)
          ELSE null
     END AS ageCandidate
WHERE ageCandidate IS NOT NULL AND ageCandidate <= 120
MATCH (p:Person {externalId: row.externalId})
SET p.age = ageCandidate
RETURN count(DISTINCT p) AS soNguoiDuocCapNhat;
~~~

Ở đây `$rows` là tham số danh sách map do ứng dụng truyền vào. Các hàng không hợp lệ hoặc không có tuổi sẽ không đi tới `SET`; tuổi đã lưu của những node ấy được giữ nguyên. Trong ứng dụng thực tế, hãy thu thập và báo cáo riêng các hàng bị từ chối, vì chúng không xuất hiện trong kết quả cập nhật trên.

Nếu API hỗ trợ xóa có chủ đích, nên phân loại `KHONG_GUI_TRUONG` / `GUI_NULL` / `HOP_LE` / `KHONG_HOP_LE` trước, rồi xử lý các nhóm theo quy tắc được xác nhận. Không mặc định mọi `null` đều đồng nghĩa với lệnh xóa.

## 5. Dữ liệu thiếu trong quan hệ và phép tổng hợp

Giá trị thiếu không chỉ xuất hiện trong thuộc tính. `OPTIONAL MATCH` còn tạo dòng có biến bằng `null` khi không tìm được quan hệ phù hợp.

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.customerId AS khachHang,
       count(o) AS soDonHang,
       count(*) AS soDongSauOptional
ORDER BY khachHang;
~~~

Với khách hàng chưa có đơn hàng, `count(o)` bằng **0** vì phép đếm biểu thức bỏ qua `null`, còn `count(*)` bằng **1** vì `OPTIONAL MATCH` vẫn giữ một dòng cho khách hàng đó. Vì vậy, để đếm thực thể liên kết, hãy dùng `count(o)` (hoặc `count(DISTINCT o)` nếu đường truy vấn có thể tạo bản sao).

Các phép tổng hợp như `sum(o.total)` bỏ qua giá trị `null`. Tuy nhiên **không có đơn hàng** và **có đơn hàng nhưng thiếu tổng tiền** là hai trạng thái nghiệp vụ khác nhau. Khi làm báo cáo, có thể theo dõi cả số đơn và số đơn có giá:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.customerId AS khachHang,
       count(DISTINCT o) AS tongDon,
       count(o.total) AS soDongCoTongTien,
       sum(o.total) AS tongTien;
~~~

Giả định trong ví dụ: mỗi quan hệ `PLACED` tương ứng một đơn hàng và `o.total` có kiểu số đúng chuẩn. Nếu một đơn xuất hiện nhiều lần qua các mẫu quan hệ khác nhau, cần xem lại cách tổng hợp để không cộng trùng. Đừng thay tổng tiền thiếu bằng 0 nếu nguồn dữ liệu chưa khẳng định đó thực sự là đơn hàng trị giá 0.

### Điều kiện lọc và ba giá trị logic

~~~cypher
MATCH (p:Person)
WHERE p.active = false
RETURN p.externalId;
~~~

Truy vấn chỉ lấy người có `active` bằng `false`. Node thiếu `active` không tự động được xem là người không hoạt động: phép so sánh của nó cho `null` nên không qua `WHERE`. Nếu muốn báo cáo cả nhóm chưa xác định, hãy dùng `CASE` để tạo trạng thái `ACTIVE`, `INACTIVE` và `UNKNOWN`.

## 6. Từ Cypher đến Java Driver và Spring Data Neo4j

Cùng một nguyên tắc phải được duy trì ở tầng ứng dụng:

- **Java Driver:** truy vấn nên trả về cả giá trị chuẩn hóa và trạng thái chất lượng; kiểm tra `Value.isNull()` trước khi đọc một trường có thể thiếu, tránh ép `null` thành kiểu nguyên thủy hoặc mặc định bằng 0.
- **Spring Data Neo4j:** với thuộc tính có thể thiếu, biểu diễn bằng kiểu tham chiếu như `Integer` hoặc `Boolean` (thay vì `int` / `boolean`) khi miền dữ liệu cần phân biệt `null` với `0` / `false`.
- **Nhập dữ liệu:** ghi nhận giá trị gốc, trạng thái kiểm tra và lý do từ chối tại bước xử lý thích hợp. Chỉ ghi kiểu dữ liệu chuẩn vào các thuộc tính dùng để lọc, nối quan hệ hoặc tính toán.
- **Truy vấn hiệu năng:** chuẩn hóa kiểu ở bước nhập giúp viết điều kiện như `WHERE p.age = 27` trên thuộc tính đã chuẩn hóa. Nếu thường xuyên bọc thuộc tính bằng hàm chuyển đổi trong `WHERE`, truy vấn có thể khó tận dụng index theo cách tối ưu.

Ví dụ đọc một giá trị tuổi có thể thiếu từ Java Driver:

~~~java
org.neo4j.driver.Value ageValue = record.get("tuoiChuan");
Integer age = ageValue.isNull() ? null : ageValue.asInt();
~~~

Đoạn mã trên áp dụng khi truy vấn đã trả `tuoiChuan` kiểu số nguyên hoặc `null`. Nếu chỉ nhận `age` mà không nhận `trangThai`, tầng Java vẫn chưa thể biết vì sao tuổi thiếu: không có dữ liệu gốc hay dữ liệu gốc bị loại do sai định dạng.

## 7. Những lỗi thường gặp

| Cách viết / cách làm | Rủi ro | Cách thay |
| --- | --- | --- |
| `p.age = null` | So sánh cho `null`, không xác định thiếu hay không | `p.age IS NULL` |
| `coalesce(p.age, 0)` dùng cho dữ liệu nghiệp vụ | Nhập nhằng “chưa biết” và “bằng 0” | Giữ `null` và trạng thái riêng |
| `toIntegerOrNull(27.9)` rồi xem kết quả là tuổi hợp lệ | Có thể làm mất phần thập phân | Kiểm tra định dạng/kiểu và miền trước khi chấp nhận |
| `SET p.age = toIntegerOrNull(row.age)` | Giá trị không chuyển được dẫn tới xóa thuộc tính | Chỉ `SET` những hàng hợp lệ |
| Coi `false` hoặc `''` là dữ liệu thiếu | Làm mất giá trị đã được người dùng cung cấp | Xác định quy tắc cho từng thuộc tính |
| Chuyển mã như `'00123'` sang số 123 | Mất số 0 đầu, đổi mã định danh | Giữ mã ở kiểu chuỗi; xác thực bằng quy tắc của mã |
| Dùng `count(*)` để đếm node tùy chọn sau `OPTIONAL MATCH` | Có thể đếm cả dòng có biến liên kết bằng `null` | `count(o)` hoặc `count(DISTINCT o)` |
| Gộp “không gửi trường” với “gửi trường null” trong payload | API cập nhật từng phần có thể xóa hoặc thay dữ liệu ngoài ý muốn | Kiểm tra khóa bằng `keys(map)` trước khi quyết định |

## 8. Quy trình áp dụng cho dữ liệu đồ thị thực tế

1. **Định nghĩa ngữ nghĩa từng thuộc tính:** thiếu nghĩa là gì, có được rỗng hay không, kiểu chuẩn là gì, miền hợp lệ là gì.
2. **Đọc và phân loại đầu vào:** lưu được thông tin “không gửi”, “gửi null”, “sai định dạng”, “ngoài miền” và “hợp lệ” nếu quy trình cần phân biệt.
3. **Chuẩn hóa có điều kiện:** dùng `CASE`, `to*OrNull` và điều kiện định dạng, tránh chuyển đổi làm mất thông tin nghiệp vụ.
4. **Quyết định cập nhật:** chỉ ghi giá trị đã hợp lệ; chỉ xóa khi có yêu cầu xóa được định nghĩa rõ; chuyển dữ liệu lỗi sang luồng kiểm tra.
5. **Kiểm chứng kết quả:** truy vấn lại trạng thái và số lượng bản ghi, kiểm tra ca biên như 0, `false`, chuỗi rỗng, số âm, số thực và quan hệ không tồn tại.
6. **Ổn định lược đồ:** sau khi dữ liệu sạch, dùng ràng buộc và index thích hợp với phiên bản Neo4j đang vận hành để giảm khả năng tái xuất hiện dữ liệu thiếu hoặc sai chuẩn.

### Câu hỏi tự kiểm tra

1. Vì sao `coalesce(p.age, 0)` có thể đúng cho một giao diện nhưng sai cho báo cáo tuổi?
2. Khi xử lý `$rows` của Java Driver, làm sao phân biệt map không có khóa `age` với map có `age: null`?
3. Vì sao cần kiểm tra định dạng và miền tuổi ngay cả khi `toIntegerOrNull` trả về số?
4. Với `OPTIONAL MATCH`, khi nào nên dùng `count(o)` thay cho `count(*)`?
5. Nếu một lệnh `SET` nhận `null`, điều gì xảy ra với thuộc tính đang tồn tại trên node?

**Ghi nhớ:** trong Cypher, một biểu thức chuyển đổi hoặc giá trị mặc định chỉ là thao tác kỹ thuật. Độ chính xác của mô hình property graph phụ thuộc vào việc giữ rõ ý nghĩa của **thiếu**, **sai**, **có chủ đích xóa** và **giá trị hợp lệ**, từ khâu nhập dữ liệu đến truy vấn quan hệ và ứng dụng Java.
