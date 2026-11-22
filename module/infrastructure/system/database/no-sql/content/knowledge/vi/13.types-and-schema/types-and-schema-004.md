# NULL, thiếu trường, chuỗi rỗng và ngữ nghĩa cập nhật trong NoSQL

## 1. Cùng là “không có dữ liệu”, nhưng không phải cùng một trạng thái

Trong cơ sở dữ liệu NoSQL, một bản ghi có thể linh hoạt về số lượng và kiểu trường. Điều này rất hữu ích khi sản phẩm thay đổi, nhưng cũng tạo ra một câu hỏi quan trọng: **trường không xuất hiện, trường có giá trị `null` và trường có chuỗi rỗng `""` có phải cùng nghĩa không?**

Xét ba hồ sơ khách hàng:

```json
{ "_id": "U01", "name": "Lan" }
{ "_id": "U02", "name": "Minh", "nickname": null }
{ "_id": "U03", "name": "An", "nickname": "" }
```

Ba bản ghi đều không cung cấp một biệt danh có nội dung, nhưng trạng thái dữ liệu là **khác nhau**:

- `U01` **thiếu trường (missing/absent)** `nickname`: khóa không có trong document.
- `U02` có trường `nickname` nhưng giá trị **`null`**: khóa tồn tại, giá trị được biểu diễn là null.
- `U03` có trường `nickname` bằng **chuỗi rỗng `""`**: khóa tồn tại, giá trị thuộc kiểu chuỗi và có độ dài bằng 0.

Trong nghiệp vụ, chúng có thể mang những ý nghĩa riêng:

- *Missing*: người dùng chưa từng cung cấp biệt danh; record có thể thuộc phiên bản schema cũ.
- *Null*: người dùng hoặc hệ thống đã chủ động ghi nhận “chưa có giá trị” hoặc “đã xóa giá trị”, tùy hợp đồng dữ liệu.
- *Empty string*: người dùng gửi một chuỗi nhưng chuỗi không chứa ký tự nào; có thể là giá trị hợp lệ hoặc lỗi validation.

**Không có quy tắc toàn cục rằng `null` là “đã xóa”, hoặc `""` là “không nhập”.** Ý nghĩa phải do hợp đồng dữ liệu và API định nghĩa. Nếu hệ thống tùy tiện coi ba trạng thái giống nhau, những phép cập nhật, lọc, đặt mặc định, index và đồng bộ dữ liệu có thể hoạt động sai.

## 2. Bốn trạng thái cần phân biệt

Giả sử trường `nickname` được phép là chuỗi.

| Trạng thái | JSON minh họa | Trường có tồn tại? | Kiểu dữ liệu | Một cách diễn giải nghiệp vụ |
|---|---|---|---|---|
| **Missing** | `{}` | Không | Không có giá trị tại đường dẫn | Chưa có thông tin hoặc record cũ |
| **Explicit null** | `{"nickname":null}` | Có | Null | Đã ghi nhận giá trị rỗng/chưa xác định |
| **Empty string** | `{"nickname":""}` | Có | String | Chuỗi có độ dài 0 |
| **Non-empty string** | `{"nickname":"Lan"}` | Có | String | Biệt danh cụ thể |

Ngoài ba trạng thái đầu, còn những trạng thái cần tránh đánh đồng:

```json
{
  "score": 0,
  "enabled": false,
  "tags": [],
  "preferences": {},
  "nickname": " ",
  "lastLoginAt": null
}
```

- Số `0` là một số hợp lệ, **không phải null**.
- Boolean `false` là một giá trị hợp lệ, **không phải missing**.
- Mảng rỗng `[]` là **mảng có 0 phần tử**, không phải một trường vắng mặt.
- Object rỗng `{}` là **object không có trường con**, khác với `null`.
- `" "` là chuỗi chứa một dấu cách, **khác với `""`**. Có nên trim hay không phụ thuộc nghiệp vụ.
- `null` chỉ có nghĩa “giá trị null được lưu”; không tự chỉ ra lý do vì sao thiếu thông tin.

### JSON, BSON và giá trị không xác định của ngôn ngữ lập trình

JSON chuẩn có literal `null` và **không có literal `undefined`**. Trong JavaScript, `undefined` là một giá trị ngôn ngữ riêng; quá trình serialize JSON có thể bỏ qua các property nhận `undefined`:

```javascript
const a = { nickname: undefined };
const b = { nickname: null };
const c = { nickname: "" };

JSON.stringify(a); // "{}"
JSON.stringify(b); // '{"nickname":null}'
JSON.stringify(c); // '{"nickname":""}'
```

Vì vậy, khi đi qua JSON API, một giá trị `undefined` ở tầng lập trình có thể trở thành **missing**, còn `null` vẫn được truyền tường minh. Không được suy diễn rằng mọi driver NoSQL hoặc mọi bộ serialize đều lưu `undefined` theo cùng một cách; nên xác định hợp đồng JSON ở ranh giới API và tránh phụ thuộc vào hành vi ngầm.

## 3. Vì sao khác biệt này quan trọng với schema linh hoạt?

Document database cho phép hai document trong cùng collection có tập trường khác nhau:

```javascript
// Bản ghi tạo trước khi ứng dụng hỗ trợ nickname.
{ _id: "U01", name: "Lan", schemaVersion: 1 }

// Bản ghi tạo sau khi ứng dụng hỗ trợ nickname.
{ _id: "U02", name: "Minh", nickname: null, schemaVersion: 2 }

// Người dùng đã cung cấp nickname.
{ _id: "U03", name: "An", nickname: "Annie", schemaVersion: 2 }
```

Khi thêm trường `nickname` ở phiên bản 2, dữ liệu cũ **không tự xuất hiện trường mới**. Nếu code mới yêu cầu field này luôn có mặt và chỉ kiểm tra giá trị có null không, code có thể xử lý sai dữ liệu cũ.

Một chiến lược tương thích là:

1. Định nghĩa ý nghĩa của trường thiếu ở các phiên bản cũ.
2. Cho phép lớp đọc xử lý đúng cả missing và explicit null trong giai đoạn chuyển đổi.
3. Nếu cần, chạy backfill dữ liệu cũ với version guard.
4. Sau khi hoàn tất migration, chỉ siết ràng buộc mới khi chắc chắn mọi đường ghi và record đều theo hợp đồng mới.

Sự linh hoạt về schema **không loại bỏ yêu cầu quản lý phiên bản và ràng buộc dữ liệu**.

## 4. MongoDB: tìm NULL và trường thiếu bằng truy vấn chính xác

MongoDB dùng BSON cho document. Với bộ dữ liệu minh họa:

```javascript
db.profiles.insertMany([
  { _id: "U01", name: "Lan" },
  { _id: "U02", name: "Minh", nickname: null },
  { _id: "U03", name: "An", nickname: "" },
  { _id: "U04", name: "Bình", nickname: "Bee" }
]);
```

### 4.1. Truy vấn `{nickname: null}` không chỉ khớp explicit null

```javascript
db.profiles.find({ nickname: null });
```

Trong MongoDB, phép so khớp này tìm document có `nickname` **bằng null hoặc không tồn tại**. Với bộ dữ liệu trên, nó khớp **U01 và U02**.

Điểm này dễ gây nhầm lẫn: nếu mục tiêu là “chỉ những người đã chủ động lưu giá trị null” thì không nên dùng duy nhất `{nickname: null}`.

### 4.2. Chỉ tìm trường không tồn tại: `$exists: false`

```javascript
db.profiles.find({
  nickname: { $exists: false }
});
```

Kết quả dự kiến: **U01**.

`$exists: false` có nghĩa đường dẫn field không tồn tại, không có nghĩa field tồn tại với giá trị null. Với các trường lồng nhau hoặc mảng, cần cân nhắc cấu trúc đường dẫn và ngữ nghĩa truy vấn của MongoDB thay vì áp thẳng suy luận từ field đơn.

### 4.3. Chỉ tìm explicit null: `$type: "null"`

```javascript
db.profiles.find({
  nickname: { $type: "null" }
});
```

Kết quả dự kiến: **U02**. Toán tử `$type` kiểm tra kiểu dữ liệu BSON; trường thiếu không có kiểu `null`. Có thể dùng kiểu BSON số 10 để chỉ null, nhưng tên `"null"` thường dễ đọc hơn.

### 4.4. Tìm trường hiện hữu bất kể giá trị

```javascript
db.profiles.find({
  nickname: { $exists: true }
});
```

Kết quả: **U02, U03, U04**. Một trường tồn tại dù giá trị là null hoặc chuỗi rỗng. Vì vậy `$exists: true` **không đồng nghĩa** “có thông tin hữu ích”.

### 4.5. Tìm trường có giá trị khác null

```javascript
db.profiles.find({
  nickname: { $ne: null }
});
```

Với field đơn trong ví dụ, điều kiện tìm giá trị **tồn tại và khác null**, nên khớp **U03 và U04**. Chuỗi rỗng `""` vẫn khác null; nếu hệ thống coi chuỗi rỗng là không hợp lệ, phải kiểm tra thêm.

Muốn tìm nickname là chuỗi không rỗng, có thể kết hợp:

```javascript
db.profiles.find({
  nickname: {
    $type: "string",
    $ne: ""
  }
});
```

Với dữ liệu mẫu, kết quả là **U04**. Điều kiện này **không tự loại chuỗi chỉ gồm dấu cách**, chẳng hạn `"   "`. Quy tắc trim và whitespace nên được xác định tại validation/normalization của ứng dụng, hoặc dùng truy vấn khác khi thật sự cần.

### 4.6. Bảng tóm tắt kết quả trên dữ liệu mẫu

| Điều kiện MongoDB | U01 missing | U02 null | U03 `""` | U04 `"Bee"` |
|---|:---:|:---:|:---:|:---:|
| `{nickname: null}` | Có | Có | Không | Không |
| `{nickname: {$exists: false}}` | Có | Không | Không | Không |
| `{nickname: {$exists: true}}` | Không | Có | Có | Có |
| `{nickname: {$type: "null"}}` | Không | Có | Không | Không |
| `{nickname: {$ne: null}}` | Không | Không | Có | Có |
| `{nickname: ""}` | Không | Không | Có | Không |

**Giới hạn ví dụ:** bảng xét field `nickname` dạng scalar ở bốn document đơn giản. Những field có mảng, nhiều kiểu hoặc đường dẫn lồng nhau có thể có ngữ nghĩa matching khác, cần thiết kế truy vấn theo cấu trúc thật.

## 5. MongoDB: phép cập nhật `$set` và `$unset` mang nghĩa khác nhau

Hãy bắt đầu từ:

```javascript
{ _id: "U04", name: "Bình", nickname: "Bee" }
```

### 5.1. `$set` thành null: trường vẫn tồn tại

```javascript
db.profiles.updateOne(
  { _id: "U04" },
  { $set: { nickname: null } }
);
```

Sau khi ghi:

```javascript
{ _id: "U04", name: "Bình", nickname: null }
```

Trường `nickname` vẫn hiện hữu; phép kiểm tra `$exists: true` trả đúng. Nếu nghiệp vụ quy định null nghĩa là “đã chủ động xóa biệt danh nhưng còn lưu dấu”, đây có thể là hành vi mong muốn.

### 5.2. `$unset`: bỏ trường ra khỏi document

```javascript
db.profiles.updateOne(
  { _id: "U04" },
  { $unset: { nickname: "" } }
);
```

Sau khi ghi:

```javascript
{ _id: "U04", name: "Bình" }
```

`$unset` xóa field khỏi document; giá trị `""` trong biểu thức `$unset` chỉ là cú pháp thường dùng để chỉ thao tác, **không có nghĩa lưu chuỗi rỗng**. Với thao tác cập nhật kiểu operator, `$unset` khác hẳn `$set: {nickname: null}`.

### 5.3. `$set` thành chuỗi rỗng: lưu một chuỗi có độ dài 0

```javascript
db.profiles.updateOne(
  { _id: "U04" },
  { $set: { nickname: "" } }
);
```

Sau khi ghi:

```javascript
{ _id: "U04", name: "Bình", nickname: "" }
```

Trường vẫn tồn tại và có kiểu String; nó không khớp truy vấn `{nickname: null}`. Nếu ứng dụng yêu cầu nickname phải có ít nhất một ký tự có ý nghĩa, hãy từ chối `""` hoặc chuẩn hóa theo hợp đồng.

### 5.4. Bảng ý nghĩa cập nhật

| Thao tác | Giá trị sau ghi | `$exists: true` | Khi nào dùng |
|---|---|---|---|
| Không cập nhật `nickname` | Giữ nguyên | Theo trạng thái trước đó | Request không muốn sửa biệt danh |
| `$set: {nickname: null}` | Explicit null | Có | Nghiệp vụ dùng null làm trạng thái riêng |
| `$unset: {nickname: ""}` | Missing | Không | Muốn bỏ trường hẳn |
| `$set: {nickname: ""}` | Empty string | Có | Chuỗi rỗng được cho phép hoặc cần ghi nhận |
| `$set: {nickname: "Bee"}` | String không rỗng | Có | Gán giá trị cụ thể |

### 5.5. Cập nhật object lồng nhau có thể làm mất trường

Giả sử:

```javascript
{
  _id: "U05",
  profile: {
    city: "Hà Nội",
    phone: "0900000000",
    nickname: "Bé Mèo"
  }
}
```

Hai lệnh dưới đây **không tương đương**:

```javascript
// Chỉ đặt profile.nickname thành null.
db.profiles.updateOne(
  { _id: "U05" },
  { $set: { "profile.nickname": null } }
);

// Thay thế TOÀN BỘ profile bằng object mới.
db.profiles.updateOne(
  { _id: "U05" },
  { $set: { profile: { nickname: null } } }
);
```

Lệnh thứ hai làm mất `city` và `phone` vì thay object `profile`. Nếu ý định là giữ các trường còn lại, dùng **dot notation** để thay đúng field con. Tương tự, `$unset: {"profile.nickname": ""}` bỏ field con mà không xóa các sibling.

**Trong mảng, cần thận trọng hơn:** dùng `$unset` lên một phần tử ở vị trí mảng có thể để lại `null` tại vị trí đó thay vì rút ngắn mảng. Nếu cần xóa phần tử theo điều kiện và làm mảng ngắn đi, cân nhắc `$pull` với điều kiện chính xác. Không được đồng nhất “xóa trường của object” và “xóa phần tử khỏi array”.

## 6. Partial update và replace toàn document: hậu quả khác nhau

Một API muốn sửa hồ sơ có thể nhận:

```json
{
  "name": "Lan mới"
}
```

Có hai cách hiểu:

1. **Partial update:** chỉ sửa trường được gửi, các trường không xuất hiện giữ nguyên.
2. **Full replacement:** bản ghi mới chỉ gồm những trường được gửi; các trường cũ không có trong representation mới có thể bị bỏ.

Trong MongoDB, các update operator như `$set`, `$unset` là cập nhật có mục tiêu. Ngược lại, `replaceOne()` thay toàn bộ nội dung document (trừ quy định với `_id`):

```javascript
// Chỉ đổi name, giữ nickname và các trường khác.
db.profiles.updateOne(
  { _id: "U03" },
  { $set: { name: "An mới" } }
);

// Thay document bằng representation mới.
db.profiles.replaceOne(
  { _id: "U03" },
  { name: "An mới" }
);
```

Ở lệnh thay thế, field `nickname` cũ sẽ không còn nếu không có trong replacement. `_id` là định danh đặc biệt, được giữ theo quy tắc của MongoDB và không được thay thành giá trị khác như field thông thường. Vì vậy, một handler vô tình biến PATCH thành full replacement có thể làm mất dữ liệu mà client không gửi.

### PATCH khác với PUT ở mức hợp đồng API

Theo quy ước HTTP phổ biến, `PUT` mô tả cập nhật/thay thế representation đích, còn `PATCH` mô tả các thay đổi áp vào resource. Tuy nhiên, **ý nghĩa chính xác của missing/null trong body vẫn phụ thuộc media type và hợp đồng API**, không nên suy ra chỉ từ tên phương thức.

Ví dụ một API **tự định nghĩa**:

| Payload PATCH | Ý định nghiệp vụ |
|---|---|
| `{}` | Không sửa biệt danh |
| `{"nickname": null}` | Xóa biệt danh khỏi document |
| `{"nickname": ""}` | Gán chuỗi rỗng nếu schema cho phép |
| `{"nickname": "Bee"}` | Gán biệt danh `Bee` |

Đây là **hợp đồng cụ thể của ví dụ**, không phải nghĩa mặc định của tất cả API. Một API khác có thể chọn `null` nghĩa là “lưu explicit null” và yêu cầu một operation riêng để xóa field.

## 7. JSON Merge Patch và JSON Patch không giống nhau

Hai định dạng phổ biến làm rõ vì sao cần xác định ngữ nghĩa patch.

### 7.1. JSON Merge Patch (RFC 7396)

Ở **JSON Merge Patch**, thành viên có giá trị `null` trong patch biểu diễn hành động **remove** thành viên đó khỏi object đích.

Ví dụ resource ban đầu:

```json
{
  "name": "Lan",
  "nickname": "Lani",
  "city": "Hà Nội"
}
```

Merge patch:

```json
{ "nickname": null }
```

Kết quả:

```json
{
  "name": "Lan",
  "city": "Hà Nội"
}
```

Trong định dạng này, `null` đóng vai trò xóa field chứ **không diễn đạt dễ dàng việc đặt field thành explicit null**. Nếu nghiệp vụ cần lưu null như một giá trị độc lập, JSON Merge Patch có thể không phù hợp hoặc phải dùng một cơ chế khác.

### 7.2. JSON Patch (RFC 6902)

**JSON Patch** biểu diễn thao tác bằng danh sách operation:

```json
[
  { "op": "remove", "path": "/nickname" },
  { "op": "replace", "path": "/city", "value": null }
]
```

Ở đây:

- `remove` bỏ thành viên `nickname` khỏi object.
- `replace` đặt giá trị `city` thành explicit null (nếu đường dẫn tồn tại và thao tác hợp lệ).

Vì operation được nêu rõ, JSON Patch phân biệt “xóa field” với “lưu null”. Khi dùng API thật, cần kiểm tra path, quyền sửa từng trường, phiên bản và khả năng cạnh tranh giữa các update.

## 8. Xây PATCH handler không làm mất phân biệt missing và null

Một lỗi thường gặp ở tầng ứng dụng là đọc giá trị bằng cách chỉ trả về `null` khi không tồn tại, khiến **missing** và **explicit null** trở nên không thể phân biệt.

Ví dụ trong JavaScript:

```javascript
const patchA = {};
const patchB = { nickname: null };
const patchC = { nickname: "" };

patchA.nickname === undefined; // true
patchB.nickname === null;      // true
patchC.nickname === "";        // true

Object.prototype.hasOwnProperty.call(patchA, "nickname"); // false
Object.prototype.hasOwnProperty.call(patchB, "nickname"); // true
Object.prototype.hasOwnProperty.call(patchC, "nickname"); // true
```

Nếu API quy định `null` nghĩa là **xóa**, còn missing nghĩa là **giữ nguyên**, có thể xây update operator:

```javascript
// Pseudocode gần cú pháp Node.js; patch đã được parse từ JSON.
function buildNicknameUpdate(patch) {
  const update = {};

  if (!Object.prototype.hasOwnProperty.call(patch, "nickname")) {
    return null; // Không thay đổi nickname.
  }

  if (patch.nickname === null) {
    update.$unset = { nickname: "" };
  } else if (typeof patch.nickname === "string") {
    update.$set = { nickname: patch.nickname };
  } else {
    throw new Error("nickname must be a string or null");
  }

  return update;
}

// {}                  -> null (no-op)
// {nickname: null}    -> {$unset: {nickname: ""}}
// {nickname: ""}      -> {$set: {nickname: ""}}
// {nickname: "Bee"}   -> {$set: {nickname: "Bee"}}
```

Handler này là ví dụ về **ngữ nghĩa**, chưa bao gồm xác thực người dùng, chống ghi đè phiên bản, error handling hoặc thao tác database thực. Trong API có nhiều trường, nên dựng danh sách field được phép sửa, kiểm tra kiểu và giới hạn từng field, rồi mới tạo update document.

### Khi dùng Java/Jackson

Với JSON tree của Jackson, có thể kiểm tra:

```java
JsonNode patch = objectMapper.readTree(requestBody);

if (!patch.has("nickname")) {
    // Missing: không sửa nickname.
} else if (patch.get("nickname").isNull()) {
    // Explicit null: áp ngữ nghĩa null theo hợp đồng API.
} else if (patch.get("nickname").isTextual()) {
    String nickname = patch.get("nickname").asText();
    // "" vẫn là chuỗi; validate riêng nếu không cho phép.
} else {
    throw new IllegalArgumentException("Invalid nickname");
}
```

Một DTO Java chỉ có `String nickname` thường không đủ để phân biệt **field không được gửi** với **field được gửi và có giá trị null** sau khi deserialize. Có thể dùng JSON tree, wrapper có trạng thái present/absent, hoặc cơ chế patch chuyên dụng. Tương tự, chỉ dùng `Optional<String>` không tự động biểu diễn trọn vẹn cả ba trạng thái missing, null và string.

## 9. MongoDB: default, `$ifNull` và cách nó làm mờ khác biệt

### 9.1. Giá trị mặc định khi đọc

Ứng dụng đôi khi muốn hiển thị `"Chưa đặt biệt danh"` cho cả missing và null. Trong aggregation của MongoDB, `$ifNull` coi **giá trị null và field missing** là điều kiện để dùng fallback:

```javascript
db.profiles.aggregate([
  {
    $project: {
      _id: 1,
      displayNickname: {
        $ifNull: ["$nickname", "Chưa đặt biệt danh"]
      }
    }
  }
]);
```

Với dữ liệu ban đầu, U01 và U02 đều có displayNickname là chuỗi mặc định. Nhưng U03 có nickname `""` nên `$ifNull` **không tự dùng fallback cho empty string**.

Đây là behavior hữu ích cho UI, nhưng nó **gộp hai trạng thái missing và null ở tầng hiển thị**. Nếu ứng dụng cần lưu dấu hiệu “chưa từng nhập” khác với “đã chủ động xóa”, cần dựa vào trường gốc, không coi kết quả của `$ifNull` là dữ liệu nguyên bản.

### 9.2. Phân biệt missing với null trong aggregation

Biểu thức `$type` trong aggregation có thể cho biết kiểu của field; khi field không hiện diện, kiểu trả về là `"missing"`:

```javascript
db.profiles.aggregate([
  {
    $project: {
      _id: 1,
      nicknameType: { $type: "$nickname" }
    }
  }
]);
```

Trên dữ liệu ban đầu, kết quả về kiểu có thể là:

```text
U01 -> "missing"
U02 -> "null"
U03 -> "string"
U04 -> "string"
```

Đừng nhầm **`$type` trong aggregation** với các điều kiện `$type` trong phép lọc truy vấn: chúng xuất hiện ở các ngữ cảnh khác nhau và cần đọc đúng cú pháp/ý nghĩa.

### 9.3. Đặt mặc định lúc insert khác với cập nhật

Giả sử chỉ muốn gán một giá trị mặc định khi **upsert tạo document mới**, không thay đổi các document đã tồn tại:

```javascript
db.profiles.updateOne(
  { _id: "U06" },
  {
    $set: { name: "Hà" },
    $setOnInsert: { notificationLanguage: "vi" }
  },
  { upsert: true }
);
```

`$setOnInsert` áp dụng khi update với `upsert` dẫn đến **insert**; nó không có nghĩa “nếu một trường đang missing trên document cũ thì tự bổ sung default”. Nếu cần backfill legacy, hãy thiết kế một job riêng có điều kiện field missing và version phù hợp.

## 10. Schema validation: required, nullable và empty string là ba câu hỏi

Trong MongoDB, `$jsonSchema` có thể kết hợp:

- `required`: trường phải **hiện diện**.
- `bsonType`: trường có thể nhận những kiểu nào.
- `minLength`: ràng buộc độ dài chuỗi.
- `enum`: giới hạn tập giá trị.

Ví dụ quy định:

- `name` bắt buộc là chuỗi không rỗng.
- `nickname` là tùy chọn; nếu có, chỉ chấp nhận chuỗi không rỗng hoặc null.
- `email` là tùy chọn; nếu có, phải là chuỗi có độ dài tối thiểu theo quy tắc.

```javascript
db.createCollection("users_validated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name"],
      properties: {
        name: {
          bsonType: "string",
          minLength: 1
        },
        nickname: {
          anyOf: [
            { bsonType: "null" },
            { bsonType: "string", minLength: 1 }
          ]
        },
        email: {
          bsonType: "string",
          minLength: 3
        }
      }
    }
  },
  validationAction: "error"
});
```

Giải thích:

| Document | Theo quy tắc ví dụ | Vì sao |
|---|---|---|
| `{"name":"Lan"}` | Hợp lệ | `nickname` và `email` không bắt buộc |
| `{"name":"Lan","nickname":null}` | Hợp lệ | `nickname` cho phép null |
| `{"name":"Lan","nickname":""}` | Không hợp lệ | Nhánh string yêu cầu tối thiểu 1 ký tự |
| `{"name":"","nickname":"Bee"}` | Không hợp lệ | `name` không rỗng |
| `{"name":"Lan","email":null}` | Không hợp lệ | `email` chỉ cho phép string nếu tồn tại |

`required` và `nullable` không đồng nghĩa. Muốn một trường **bắt buộc xuất hiện nhưng có thể null**, cần cả `required` và kiểu cho phép null. Muốn **tùy chọn nhưng nếu có phải là string**, không đưa vào `required` và chỉ cho phép string.

`minLength: 1` không loại bỏ chuỗi chỉ chứa khoảng trắng. Nếu yêu cầu “sau khi trim vẫn còn ký tự”, cần normalization/validation bổ sung. Ngoài ra, không nên dựa vào việc validator chỉ kiểm tra một số trường để tự kết luận tất cả bất biến nghiệp vụ đã được bảo vệ.

## 11. Chỉ mục và uniqueness: null, missing, chuỗi rỗng có hậu quả thực

Giả sử mỗi tài khoản có thể có một email; email không bắt buộc, nhưng nếu được cung cấp thì phải duy nhất.

### 11.1. Unique index đơn trên trường tùy chọn

```javascript
db.users.createIndex(
  { emailNormalized: 1 },
  { unique: true }
);
```

Với **single-field unique index thông thường** trong MongoDB, giá trị chỉ mục của trường missing hoặc null có thể được biểu diễn như mục nhập null. Do đó, nếu nhiều document không có `emailNormalized` hoặc có `emailNormalized: null`, unique index có thể không cho phép chúng cùng tồn tại, hoặc việc tạo index trên dữ liệu sẵn có bị lỗi duplicate key.

Điều này thường **không phải** hợp đồng mong muốn nếu nhiều người được phép chưa cung cấp email.

### 11.2. Partial unique index cho email thật sự có giá trị

Một cách thiết kế là chỉ đánh chỉ mục các document có `emailNormalized` thuộc kiểu chuỗi:

```javascript
db.users.createIndex(
  { emailNormalized: 1 },
  {
    unique: true,
    partialFilterExpression: {
      emailNormalized: { $type: "string" }
    }
  }
);
```

Như vậy document missing hoặc explicit null không được đưa vào phạm vi unique của index trên. **Nhưng chuỗi rỗng vẫn là String**, nên nhiều document có `emailNormalized: ""` vẫn xung đột uniqueness. Nếu `""` mang nghĩa “chưa có email”, tốt hơn nên từ chối đầu vào hoặc chuẩn hóa thành missing/null theo một quy tắc thống nhất trước khi ghi.

`partialFilterExpression` chỉ quy định phạm vi được index; ứng dụng vẫn cần normalization (ví dụ cách xử lý chữ hoa/chữ thường), validation và quy tắc uniqueness phù hợp. Những khác biệt collation và mã hóa Unicode cũng có thể ảnh hưởng ý nghĩa “email trùng”.

### 11.3. Sparse index không giống partial index

Sparse index thường **bỏ qua document không có trường được index**, nhưng một document có trường với giá trị null vẫn có thể được đưa vào index. Vì thế `sparse: true` không mặc nhiên loại cả explicit null lẫn empty string. Với nghiệp vụ “chỉ giá trị String hợp lệ mới phải duy nhất”, partial index cùng validation thường thể hiện ý định rõ hơn.

Các hành vi index có thể khác ở index ghép, multikey, phân vùng dữ liệu hoặc hệ NoSQL khác. Khi áp dụng uniqueness trong cluster, cần xác minh quy tắc của loại index và shard key cụ thể.

## 12. Từng hệ NoSQL có cách biểu diễn “không có” khác nhau

Các khái niệm missing, null và empty string không có cùng API ở mọi loại NoSQL. Cần hiểu ngữ nghĩa của **storage model**, không chỉ xem chuỗi JSON gửi lên.

### 12.1. Redis: key/field không tồn tại khác chuỗi rỗng

Redis key–value không tự có kiểu JSON null cho giá trị string. Với một Redis string:

```redis
SET user:U01:nickname ""
GET user:U01:nickname
EXISTS user:U01:nickname

DEL user:U01:nickname
GET user:U01:nickname
EXISTS user:U01:nickname
```

- Sau `SET ... ""`, key **tồn tại** và giá trị là chuỗi rỗng.
- Sau `DEL`, key **không tồn tại**; `GET` trả một phản hồi kiểu nil/null tùy giao thức và client.
- `SET user:U01:nickname "null"` lưu **chuỗi bốn ký tự `null`**, không phải giá trị BSON null hay JSON null.
- `EXISTS` giúp kiểm tra sự tồn tại của key, nhưng vẫn cần xử lý race nếu client thực hiện nhiều lệnh độc lập.

Redis hash cũng phân biệt field hiện hữu với field vắng mặt:

```redis
HSET user:U01 nickname ""
HEXISTS user:U01 nickname
HGET user:U01 nickname
HDEL user:U01 nickname
HEXISTS user:U01 nickname
```

Với Redis, **TTL hết hạn** cũng làm key trở nên không tồn tại. Tình trạng missing có thể là “chưa từng ghi”, “đã chủ động xóa”, hoặc “đã hết TTL”, nếu không có một event/audit hoặc metadata riêng thì chỉ nhìn trạng thái hiện tại không thể biết nguyên nhân.

### 12.2. DynamoDB: thuộc tính `NULL` là một kiểu dữ liệu

DynamoDB lưu item có các attribute. Ở API dạng low-level, có thể biểu diễn explicit NULL bằng kiểu attribute `NULL`:

```json
{
  "userId": { "S": "U02" },
  "nickname": { "NULL": true }
}
```

Một item khác có thể **không có attribute `nickname`**. Đây là hai trạng thái khác nhau. DynamoDB hỗ trợ chuỗi rỗng cho một số trường không phải key, nhưng những giá trị key bắt buộc có ràng buộc riêng và không được sử dụng chuỗi rỗng như khóa partition/sort.

Trong `UpdateExpression`:

```text
SET nickname = :newValue
REMOVE nickname
```

`SET` gán một giá trị thuộc kiểu được hỗ trợ, còn `REMOVE` xóa attribute khỏi item. Nếu muốn lưu kiểu `NULL`, dùng giá trị attribute null phù hợp, không đánh đồng với `REMOVE`.

Những điều kiện như `attribute_exists(nickname)` kiểm tra attribute có tồn tại hay không; attribute có kiểu `NULL` **vẫn là attribute đang tồn tại**. Khi cần kiểm tra loại null, cần dùng điều kiện về kiểu attribute phù hợp, thay vì suy ra từ `attribute_exists`. Cần phân biệt rõ low-level API với SDK/document mapper, vì cú pháp giá trị được serialize khác nhau.

### 12.3. Họ wide-column như Cassandra

Trong các hệ wide-column, “không có cột”, “giá trị null” và “cập nhật không nhắc đến cột” có thể liên quan tới cơ chế **tombstone**, thứ tự ghi và chiến lược compaction. Chẳng hạn, trong CQL của Cassandra, thao tác gán null cho cột có thể mang nghĩa xóa và tạo tombstone; **UNSET** trong câu lệnh prepared khác với ghi null vì nó có thể mang nghĩa bỏ qua cập nhật cột đó.

Không thể bê nguyên quy tắc của MongoDB như “`$set` null luôn giữ field tồn tại” sang Cassandra. Khi dùng một datastore cụ thể, hãy kiểm tra ngữ nghĩa driver và storage engine, đặc biệt trong hệ phân tán có retry hoặc ghi trễ.

### So sánh ý nghĩa tổng quát

| Hệ / biểu diễn | “Không có” | “Explicit null” | Chuỗi rỗng | Hành động xóa |
|---|---|---|---|---|
| MongoDB document | Field missing | BSON null | String `""` | `$unset` |
| Redis string | Key không tồn tại | Không phải kiểu string null độc lập | Giá trị `""` | `DEL` |
| Redis hash | Hash field thiếu | Không phải kiểu hash field null độc lập | Hash field `""` | `HDEL` |
| DynamoDB item | Attribute thiếu | Attribute kiểu `NULL` | Được hỗ trợ với giới hạn key | `REMOVE` |
| Cassandra/CQL | Cột không có giá trị đang sống theo storage semantics | Có thể mang nghĩa xóa/tombstone | Có ngữ nghĩa type riêng | Ghi null/DELETE tùy thao tác |

Mục tiêu của bảng là giúp nhận ra **các hệ không có API tương đương từng-một**. Không nên thiết kế một lớp abstraction tuyên bố “null = delete” cho mọi datastore nếu chưa xác định tính đúng đắn của từng phép ghi.

## 13. Mô hình ba trạng thái trong đồng bộ sự kiện

Một hệ thống phát event `UserUpdated` tới các read model. Nếu event chỉ có:

```json
{
  "userId": "U01",
  "nickname": null
}
```

consumer phải biết `null` có nghĩa gì:

- Đặt nickname thành explicit null?
- Xóa attribute khỏi projection?
- Trường không được biết tại nơi phát?
- Một bản snapshot được trả về không đầy đủ?

Nếu cùng một event được tiêu thụ bởi MongoDB, Redis và DynamoDB, mỗi projector phải áp dụng **quy tắc ánh xạ tương đương về nghiệp vụ**, chứ không chỉ copy giá trị theo mặc định của client.

### 13.1. Patch event phải có operation rõ ràng

Một hợp đồng sự kiện có thể mô tả phép cập nhật:

```json
{
  "eventId": "user:U01:v8",
  "userId": "U01",
  "version": 8,
  "operations": [
    { "op": "remove", "path": "/nickname" }
  ]
}
```

Hoặc full-state event có thể quy định trường nào **bắt buộc hiện diện** và ý nghĩa của missing trong schema version tương ứng:

```json
{
  "eventId": "user:U01:v8",
  "userId": "U01",
  "version": 8,
  "eventType": "UserSnapshot",
  "state": {
    "name": "Lan",
    "nickname": null
  }
}
```

Một event mang patch khác một event mang full snapshot. **Không được hiểu field vắng mặt trong patch là “xóa”, rồi dùng quy tắc đó cho full snapshot (hoặc ngược lại) mà không có hợp đồng rõ ràng**.

### 13.2. Thứ tự và idempotency

Giả sử source đã đi từ v7 `nickname="Bee"` sang v8 `nickname=null`, sau đó v9 `nickname="B"`. Nếu event v8 đến sau v9 và projector áp vô điều kiện, dữ liệu cuối cùng sẽ bị lùi.

Cần version/sequence theo thực thể và cơ chế apply an toàn:

```text
if incomingVersion <= storedVersion:
    ignore old/duplicate event
else:
    atomically apply full-state or valid ordered patch
    store incomingVersion
```

Với patch chỉ nêu thao tác `remove`, bỏ sót một event trung gian có thể khiến trạng thái cuối khác mong muốn; cần xử lý gap hoặc nạp lại full snapshot. `null` không tự cung cấp cơ chế chống event trùng hoặc sai thứ tự.

## 14. Đặt mặc định và migration: đừng sửa thiếu thành null một cách mù quáng

Giả sử phiên bản 1 không có field `preferredLanguage`. Phiên bản 2 muốn hỗ trợ ngôn ngữ giao diện.

Một lựa chọn là:

```text
missing              -> chưa xác định; UI dùng ngôn ngữ trình duyệt
explicit null        -> người dùng chọn “dùng mặc định hệ thống”
string "vi" / "en"   -> lựa chọn cụ thể
```

Nếu migration tự động ghi `preferredLanguage: null` cho mọi record thiếu field, hệ thống đã **xóa khác biệt** giữa “chưa từng quyết định” và “đã chủ động chọn mặc định”. Điều đó có thể phá logic giới thiệu tính năng hoặc thống kê hành vi.

### Khi nên backfill?

Backfill có thể hợp lý nếu hợp đồng mới quy định dứt khoát:

> Mọi record được coi là có ngôn ngữ mặc định `"vi"`; không cần phân biệt đã chọn hay chưa.

Khi đó có thể backfill có điều kiện:

```javascript
db.profiles.updateMany(
  { preferredLanguage: { $exists: false } },
  { $set: { preferredLanguage: "vi" } }
);
```

Đây là thao tác ghi hàng loạt, chỉ nên áp dụng sau khi đã xác định đúng quy tắc nghiệp vụ, đo số bản ghi bị ảnh hưởng và xem rủi ro concurrent writes. Nếu nguồn có version và nhiều writer, nên thiết kế cập nhật theo phiên bản hoặc di trú từng batch có đối soát để tránh ghi đè lựa chọn mới của người dùng.

### Chiến lược tương thích khi schema đổi

Một quy trình thực dụng:

1. Đưa logic đọc hỗ trợ schema cũ và mới vào ứng dụng.
2. Đưa logic ghi mới cùng validation rõ ràng.
3. Chạy scan báo số record missing, null, empty string và kiểu sai.
4. Xác định trường hợp nào được chuẩn hóa tự động.
5. Backfill theo batch có checkpoint, giới hạn tải và kiểm tra phiên bản.
6. Đối soát kết quả, tìm dữ liệu không thể xác định và đưa xử lý riêng.
7. Sau khi ổn định mới siết validation/index và gỡ tương thích cũ.

Không nên chỉ chạy một lệnh thay tất cả `null` bằng `""` rồi tuyên bố migration xong.

## 15. Phân quyền và tính riêng tư: null có thể là một trạng thái quan trọng

Một trường thông tin cá nhân như `phoneNumber` có thể mang ngữ nghĩa:

| Trạng thái | Ý nghĩa có thể cần phân biệt |
|---|---|
| Missing | Tài khoản cũ chưa được yêu cầu cung cấp số điện thoại |
| Null | Người dùng đã chủ động xóa số điện thoại theo chính sách |
| Empty string | Dữ liệu nhập không hợp lệ hoặc UI gửi chuỗi rỗng |
| Số điện thoại | Có giá trị nhưng còn phải xác minh quyền truy cập |

Lưu `null` không tự chứng minh dữ liệu đã được xóa khỏi cache, search index, log, bản sao hoặc backup. Nếu người dùng yêu cầu xóa dữ liệu, hệ thống phải có quy trình xóa/ẩn thông tin phù hợp xuyên các bản biểu diễn. Ngược lại, nếu cần giữ bằng chứng “đã yêu cầu xóa” nhưng không giữ số điện thoại, nên lưu **metadata/audit sự kiện riêng** thay vì nhét ý nghĩa không rõ vào một giá trị null.

Khi API trả dữ liệu, một field missing đôi khi được client hiểu khác field hiện hữu với null. Nên có contract rõ về quyền xem trường và sự hiện diện của nó; không biến “không được xem” thành một dấu hiệu trả về quá giàu thông tin vô tình tiết lộ trạng thái của dữ liệu.

## 16. Concurrency: PATCH độc lập có thể vẫn ghi đè nhau

Phân biệt missing/null/empty string chỉ bảo vệ **ý định thay đổi field**, chưa tự giải quyết cạnh tranh ghi.

Ví dụ:

```text
T0: document v5, nickname="Bee", city="Hà Nội"
T1: Client A đọc v5 và muốn xóa nickname
T2: Client B đọc v5 và muốn đổi city="Huế"
T3: B cập nhật city, document lên v6
T4: A gửi full replacement dựa trên bản v5
=> có nguy cơ đưa city về "Hà Nội" hoặc làm mất trường
```

Giải pháp thường dùng:

- **Field-level update** bằng `$set`/`$unset` thay vì replace toàn document khi chỉ sửa vài trường.
- **Optimistic concurrency** bằng version hoặc điều kiện trạng thái.
- Transaction nếu các trường/tài nguyên phải được thay cùng nhau theo bất biến.
- Xử lý conflict rõ ràng thay vì tự retry bằng payload cũ.

Ví dụ MongoDB với version:

```javascript
db.profiles.updateOne(
  { _id: "U05", version: 5 },
  {
    $unset: { nickname: "" },
    $inc: { version: 1 }
  }
);
```

Nếu document đã lên v6, `matchedCount = 0` và API nên yêu cầu đọc lại/giải quyết xung đột theo chính sách. Không nên tự bỏ điều kiện `version` để ép ghi. Việc kết hợp `$set` và `$unset` cho nhiều trường cần bảo đảm không áp những thao tác xung đột tới cùng đường dẫn.

## 17. Lỗi do ánh xạ giữa API, object và database

Một lớp DTO/ORM/mapper có thể vô tình làm mất phân biệt ba trạng thái:

| Lỗi ánh xạ | Hậu quả | Cách hạn chế |
|---|---|---|
| Parse JSON vào object mà không giữ thông tin field có được gửi hay không | Missing bị biến thành null | Dùng presence-aware DTO, JSON tree hoặc patch operation |
| Dùng điều kiện `if (nickname)` | Bỏ qua `""` và các giá trị falsy | Kiểm tra presence và kiểu riêng |
| Thấy `null` rồi tự động `$unset` cho mọi API | Mất explicit null khi nghiệp vụ cần | Định nghĩa hợp đồng patch |
| Dùng replacement cho request chỉ sửa một trường | Các field không gửi bị xóa | Update operator hoặc JSON Patch đúng nghĩa |
| Trả null mặc định cho field missing ở mọi nơi | Không phân biệt legacy với chủ động xóa | Giữ trạng thái gốc khi cần nghiệp vụ |
| Chuẩn hóa mọi `""` thành null không có quy tắc | Mất thông tin có ý nghĩa | Kiểm tra theo từng field |
| Dùng `$ifNull` làm bằng chứng dữ liệu có null | Gộp missing và null | Dùng `$exists`, `$type` để kiểm tra |
| Index unique field tùy chọn mà không xem null/missing | Duplicate-key khi nhiều record chưa có giá trị | Partial index và validation phù hợp |
| Đổi phiên bản schema nhưng không xử lý record cũ | Lỗi runtime hoặc kết quả thống kê sai | Migration có phiên bản và backfill |
| Coi cache nil là explicit null từ nguồn | Không biết do thiếu key hay hết TTL | Dùng cache metadata hoặc đọc nguồn |

### Một phản ví dụ JavaScript ngắn

```javascript
function incorrectPatch(profile, patch) {
  if (patch.nickname) {          // Sai: chuỗi rỗng bị bỏ qua.
    profile.nickname = patch.nickname;
  }
}

function presenceAwarePatch(profile, patch) {
  if (!Object.prototype.hasOwnProperty.call(patch, "nickname")) {
    return;                     // Missing: không thay đổi.
  }

  if (patch.nickname === null) {
    delete profile.nickname;    // Chỉ đúng nếu API quy định null là remove.
  } else {
    profile.nickname = patch.nickname; // Có thể là "".
  }
}
```

Đây là ví dụ thao tác trên object trong bộ nhớ; trong hệ phân tán, vẫn phải xử lý validation và version khi ghi xuống datastore. Việc dùng toán tử JavaScript như `??` hoặc `||` cũng cần cẩn thận: `??` fallback cho null/undefined, còn `||` fallback thêm cho các giá trị falsy như `""`, `0` và `false`.

## 18. Đo lường và đối soát dữ liệu đã tồn tại

Trước khi thay đổi schema, nên đếm từng nhóm để biết mức ảnh hưởng:

```javascript
// 1. Field thiếu
db.profiles.countDocuments({
  nickname: { $exists: false }
});

// 2. Explicit null
db.profiles.countDocuments({
  nickname: { $type: "null" }
});

// 3. Empty string
db.profiles.countDocuments({
  nickname: ""
});

// 4. String không rỗng
db.profiles.countDocuments({
  nickname: { $type: "string", $ne: "" }
});
```

Nếu dữ liệu có mảng, kiểu khác hoặc trường lồng nhau, cần detector bổ sung. Bốn nhóm trên có thể **chưa bao phủ** kiểu sai như số hoặc boolean. Nên thống kê cả giá trị không đúng kiểu và các biến thể whitespace nếu nghiệp vụ quan tâm.

### Quét theo batch thay vì sửa toàn bộ một lần

Với collection lớn, có thể quét theo dải `_id` hoặc tenant và lưu checkpoint. Sau khi xác minh quy tắc:

```text
scan batch:
    classify missing/null/empty/nonempty/type-error
    determine repair policy for each class
    dry-run and record counts
    conditional update with version guard
    verify changed records
    record progress and failures
```

Không nên mặc định chạy `updateMany` không điều kiện trên production đang tải cao. Nếu một document được người dùng sửa giữa lúc scan và backfill, job phải tránh ghi đè thông tin mới. Sau migration cần **đối soát** số lượng và bản mẫu, không chỉ dựa vào kết quả “modifiedCount” rồi kết luận mọi dữ liệu đã đúng.

## 19. Một tình huống đầy đủ: trường số điện thoại của khách hàng

Giả sử hệ thống có quy tắc:

- `phoneNumber` có thể thiếu ở tài khoản cũ.
- Khi có số, phải là chuỗi đã chuẩn hóa theo quy tắc nghiệp vụ.
- Người dùng có thể **xóa số điện thoại**.
- Chuỗi rỗng không được lưu.
- Chỉ số điện thoại hiện hữu, hợp lệ mới tham gia unique index.
- Sau thay đổi, cache hồ sơ phải được làm mới hoặc vô hiệu hóa.

Hợp đồng PATCH đề xuất:

| Request | Cách xử lý |
|---|---|
| `{}` | Không thay đổi số điện thoại |
| `{"phoneNumber": null}` | Xóa field bằng `$unset` |
| `{"phoneNumber": ""}` | Trả lỗi validation |
| `{"phoneNumber": "0912345678"}` | Chuẩn hóa và `$set` |
| `{"phoneNumber": 123}` | Trả lỗi sai kiểu |

Luồng xử lý:

```text
Authenticated PATCH request
          |
          v
Check field presence and type
          |
          v
Validate and normalize number
          |
          v
Conditional update in source database
          |
          v
Commit + publish change safely
          |
          v
Invalidate/update profile cache
          |
          v
Return response with version
```

Nếu business muốn phân biệt “chưa từng cung cấp” với “người dùng chủ động xóa”, chỉ dùng missing sau `$unset` **không đủ**. Có thể bổ sung trạng thái hoặc sự kiện riêng:

```json
{
  "_id": "U01",
  "phoneNumber": null,
  "phoneStatus": "REMOVED_BY_USER",
  "phoneUpdatedAt": "2026-11-14T09:00:00Z",
  "version": 8
}
```

Hoặc giữ missing ở source và lưu sự kiện xóa trong audit có phân quyền. Cách chọn phụ thuộc yêu cầu bảo vệ dữ liệu, vòng đời và ngữ nghĩa của ứng dụng. **Đừng bắt một giá trị null phải gánh nhiều ý nghĩa mâu thuẫn.**

## 20. Các câu hỏi cần quyết định trước khi đưa field mới vào NoSQL

Một bảng quyết định thiết kế có thể dùng cho từng trường:

| Câu hỏi | Ví dụ quyết định |
|---|---|
| Trường có bắt buộc xuất hiện không? | `name` bắt buộc; `nickname` tùy chọn |
| Null có được phép không? | `nickname` có thể null; `emailNormalized` không cho null nếu tồn tại |
| Empty string có hợp lệ không? | Không cho `emailNormalized=""`; có thể cho `middleName=""` nếu có lý do |
| Missing có khác explicit null về nghiệp vụ không? | Có với dữ liệu đồng ý/xóa |
| Giá trị mặc định đặt ở đọc hay ghi? | UI fallback khi missing; chỉ backfill nếu nghiệp vụ chấp nhận |
| PATCH thiếu trường nghĩa là gì? | Giữ nguyên |
| PATCH gửi null nghĩa là gì? | Remove hoặc set null, quy định rõ |
| PUT/replacement có bỏ trường vắng mặt không? | Phải mô tả rõ trong API |
| Dữ liệu cũ không có trường được xử lý thế nào? | Tương thích schema và backfill có kiểm soát |
| Field có unique/index không? | Xem null/missing/empty và phạm vi |
| Cache hoặc search index đồng bộ xóa field thế nào? | Event operation hoặc snapshot/version |
| Dữ liệu được phân quyền và xóa thế nào? | Chủ sở hữu, audit, TTL, chính sách bảo vệ |

**Ghi hợp đồng này vào tài liệu schema/API** giúp frontend, backend, worker, pipeline tìm kiếm và job migration xử lý nhất quán; nếu không, mỗi thành phần có thể tự diễn giải khác nhau.

## 21. Bài tập thực hành

### Bài 1 — Phân loại trạng thái

Cho bốn document:

```javascript
{ _id: 1 }
{ _id: 2, phone: null }
{ _id: 3, phone: "" }
{ _id: 4, phone: "0900000000" }
```

Hãy nêu kết quả dự kiến cho các truy vấn `{phone: null}`, `{phone: {$exists: false}}`, `{phone: {$type: "null"}}`, và `{phone: {$ne: null}}`. Giải thích vì sao truy vấn `{phone: null}` không chỉ tìm explicit null.

### Bài 2 — Chọn `$set` hay `$unset`

Một API quy định `{"nickname": null}` có nghĩa xóa biệt danh, `{}` nghĩa giữ nguyên, `{"nickname": ""}` nghĩa lưu chuỗi rỗng. Hãy viết MongoDB update operator cho từng payload. Có nên gọi `updateOne` khi payload rỗng không?

### Bài 3 — Phân biệt replace và partial update

Document trước khi cập nhật:

```json
{ "_id": "U01", "name": "Lan", "nickname": "Lani", "city": "Huế" }
```

Client chỉ gửi `{"name":"Lan mới"}`. So sánh kết quả nếu dùng `$set` với `replaceOne`. Cách nào phù hợp cho API PATCH chỉ sửa tên?

### Bài 4 — Index duy nhất của trường tùy chọn

Nhiều người dùng chưa đăng ký email. Có nên dùng single-field unique index thông thường trên `emailNormalized` không? Hãy đề xuất partial unique index phù hợp và giải thích vì sao cần từ chối hoặc chuẩn hóa `""`.

### Bài 5 — Chuyển từ schema v1 sang v2

Phiên bản v1 không có `preferredLanguage`; v2 cho phép một trong các giá trị `"vi"`, `"en"` và null. Hãy viết ý nghĩa của missing và null, sau đó đề xuất chiến lược migration không vô tình xóa khác biệt này.

### Bài 6 — Redis và TTL

Key `user:U01:nickname` lần đầu được lưu bằng chuỗi rỗng, sau đó bị `DEL` hoặc hết TTL. `GET` trả gì về mặt trạng thái? Chỉ dùng `GET` có phân biệt được “chưa từng lưu”, “đã xóa” và “đã hết hạn” không?

### Bài 7 — Event đến sai thứ tự

Full-state event v8 đặt `nickname=null` và v9 đặt `nickname="Bee"`. Nếu projector nhận v9 trước rồi v8 sau, cần cơ chế nào để không ghi lùi? Nếu event v8 mang operation `remove` thay vì full snapshot, cần quan tâm điều gì khi mất event trung gian?

### Bài 8 — Kiểu giá trị trong DTO Java

Một controller nhận body JSON vào DTO chỉ có `String nickname`. Vì sao nó khó phân biệt field missing và explicit null? Hãy chọn cách dùng `JsonNode.has()` hoặc một wrapper có presence để triển khai PATCH đúng hợp đồng.

## 22. Kết luận

Trong NoSQL, **`null`, thiếu trường và chuỗi rỗng là ba trạng thái khác nhau**. Khác biệt này không chỉ nằm ở cách hiển thị JSON; nó ảnh hưởng trực tiếp đến:

- **Truy vấn:** MongoDB `{field: null}` khớp cả explicit null và missing, trong khi `$exists` và `$type` giúp phân biệt.
- **Cập nhật:** `$set: null` giữ field hiện hữu; `$unset` xóa field; `$set: ""` lưu chuỗi rỗng.
- **API:** thiếu trường trong PATCH có thể mang nghĩa giữ nguyên, trong khi null phải có hợp đồng rõ là remove hay set explicit null.
- **Schema và index:** required, nullable, empty string và unique index là những quyết định tách biệt.
- **Đồng bộ:** patch event, snapshot, cache invalidation và migration phải giữ ngữ nghĩa hiện diện của từng field.
- **Hệ quản trị:** Redis, MongoDB, DynamoDB và Cassandra không có cùng cách lưu/đọc/xóa null; không thể áp dụng máy móc một quy tắc cho mọi database.

Khi thiết kế một field mới, hãy trả lời trước: **trường có bắt buộc xuất hiện không, null có được phép không, chuỗi rỗng có ý nghĩa gì, hành vi PATCH/replace là gì và dữ liệu cũ được xử lý thế nào?** Chỉ khi các quyết định đó nhất quán giữa API, lớp ứng dụng, datastore và các bản phục vụ đọc, hệ thống mới tránh được những lỗi “xóa nhầm”, “không cập nhật”, “mất field” và “query sai” rất khó phát hiện.
