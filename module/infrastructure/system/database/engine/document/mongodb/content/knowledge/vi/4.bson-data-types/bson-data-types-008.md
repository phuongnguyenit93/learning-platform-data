# Phân biệt trường không tồn tại, null, chuỗi rỗng và mảng rỗng trong MongoDB

## 1. Vì sao bốn trạng thái nhìn giống “không có dữ liệu” nhưng lại khác nhau?

Trong MongoDB, một tài liệu (document) được biểu diễn bằng **BSON**, gồm các cặp tên trường và giá trị có kiểu. Một trường *không được ghi vào tài liệu* khác hoàn toàn với một trường *có mặt nhưng mang giá trị rỗng*. Bốn tình huống rất thường gặp là:

1. **Trường không tồn tại (missing field):** tài liệu không có khóa đó.
2. **`null`:** khóa có tồn tại và mang giá trị BSON Null.
3. **Chuỗi rỗng (`""`):** khóa tồn tại và chứa một chuỗi có độ dài bằng 0.
4. **Mảng rỗng (`[]`):** khóa tồn tại và chứa một mảng có 0 phần tử.

Ví dụ, bốn tài liệu sau mang ý nghĩa khác nhau:

```javascript
{ _id: 1 }                         // Không hề có trường value
{ _id: 2, value: null }             // Có value, giá trị BSON Null
{ _id: 3, value: "" }               // Có value, giá trị String rỗng
{ _id: 4, value: [] }               // Có value, giá trị Array rỗng
```

Nếu mô hình dữ liệu cho phép cả bốn, ứng dụng cần phân biệt chúng để biết người dùng **chưa gửi giá trị**, **chủ động để trống một giá trị**, **gửi một chuỗi rỗng**, hay **có một danh sách nhưng hiện không có phần tử**.

| Trạng thái | Trường tồn tại? | Kiểu BSON | Ý nghĩa nghiệp vụ có thể chọn |
|---|---|---|---|
| Không có `value` | Không | Không có kiểu vì không có trường | Chưa khai báo, chưa cung cấp hoặc không áp dụng |
| `value: null` | Có | Null | Đã khai báo nhưng chưa có giá trị, hoặc chủ động xóa giá trị |
| `value: ""` | Có | String | Có chuỗi nhưng người dùng để trống |
| `value: []` | Có | Array | Có danh sách và danh sách hiện rỗng |

Đây là **các cách diễn giải nghiệp vụ**, không phải quy tắc MongoDB tự áp đặt. Ứng dụng phải quyết định trạng thái nào là hợp lệ. Chẳng hạn trường `nickname` thường nên là chuỗi hoặc null, còn trường `tags` thường nên là mảng; việc lưu cả hai loại trong một trường là ví dụ kiểm chứng sự khác nhau về kiểu, không phải thiết kế schema được khuyến khích.

## 2. Tạo bộ dữ liệu minh họa

Các lệnh sử dụng cú pháp **mongosh**. Hãy chạy trên database thử nghiệm và dùng collection `fieldStatesDemo` riêng để tránh ảnh hưởng dữ liệu ứng dụng. Chạy `insertMany` một lần trên collection còn trống:

```javascript
db.fieldStatesDemo.insertMany([
  { _id: "missing",     note: "Không có value" },
  { _id: "null",        note: "BSON Null",       value: null },
  { _id: "emptyString", note: "Chuỗi rỗng",     value: "" },
  { _id: "emptyArray",  note: "Mảng rỗng",      value: [] },
  { _id: "text",        note: "Chuỗi có dữ liệu", value: "MongoDB" }
]);
```

Trong dữ liệu này:

- `missing` không có khóa `value`.
- `null` có khóa `value` với giá trị `null`.
- `emptyString` có `value` bằng chuỗi rỗng.
- `emptyArray` có `value` bằng mảng rỗng.
- `text` là trường hợp đối chiếu: chuỗi không rỗng.

Khi chạy các truy vấn bên dưới, dùng projection chỉ lấy `_id` để dễ nhận ra tài liệu nào khớp:

```javascript
db.fieldStatesDemo.find(
  { value: null },
  { _id: 1 }
);
```

Kết quả phù hợp của bộ mẫu gồm các `_id` `"missing"` và `"null"`. Điểm bất ngờ này là lý do cần học kỹ sự khác nhau giữa **so sánh bằng null** và **kiểm tra trường thực sự tồn tại**.

## 3. Điều kiện `{ field: null }`: trường thiếu hoặc có giá trị null

### 3.1. Hai trạng thái cùng khớp một biểu thức

Trong ngôn ngữ truy vấn MongoDB, biểu thức:

```javascript
db.fieldStatesDemo.find({ value: null });
```

khớp tài liệu có trường `value` **bằng null** *hoặc* **không tồn tại**. Với bộ dữ liệu vừa tạo, kết quả là:

```text
missing
null
```

Vì vậy, câu truy vấn này **không phải phép tìm chính xác các tài liệu chứa BSON Null**. Nó phù hợp khi nghiệp vụ chấp nhận cả “chưa có trường” lẫn “đã ghi null” như cùng một nhóm “không có giá trị”.

Cú pháp tương đương về mục đích ở trường hợp đơn giản:

```javascript
db.fieldStatesDemo.find({ value: { $eq: null } });
```

**Lưu ý về mảng:** MongoDB có ngữ nghĩa khớp phần tử mảng với nhiều biểu thức so sánh bằng. Nếu dữ liệu thực tế có mảng chứa `null`, một số truy vấn bằng null còn có thể khớp vì phần tử trong mảng. Vì thế, các ví dụ đòi hỏi kiểu chính xác nên kết hợp kiến thức về `$type` và cấu trúc schema, không suy diễn từ việc một biểu thức đã khớp.

### 3.2. Vì sao `$ne: null` cũng đáng chú ý?

```javascript
db.fieldStatesDemo.find({ value: { $ne: null } });
```

Với bộ mẫu, phép lọc này khớp `emptyString`, `emptyArray` và `text`. Trong MongoDB, so sánh **khác null** được sử dụng để tìm các trường **có tồn tại và có giá trị khác null**.

Đừng suy từ đó rằng mọi điều kiện `$ne` đều tự động loại trường thiếu:

```javascript
db.fieldStatesDemo.find({ value: { $ne: "" } });
```

Ở ví dụ trên, tài liệu `missing` vẫn có thể khớp, vì toán tử `$ne` với một giá trị thông thường cũng khớp tài liệu **không chứa trường**. Đây là khác biệt quan trọng giữa “khác chuỗi rỗng” và “có giá trị khác null”.

Khi cần kiểm tra một loại dữ liệu cụ thể, hãy biểu đạt điều kiện dương bằng `$type` và toán tử phù hợp, thay vì chỉ dựa vào phủ định `$ne`.

## 4. `$exists`: kiểm tra sự có mặt của khóa

`$exists` trả lời câu hỏi: **tài liệu có chứa trường này không?** Nó không đánh giá giá trị có “hữu ích”, có khác null, hay có độ dài lớn hơn 0.

### 4.1. Tìm trường không tồn tại

```javascript
db.fieldStatesDemo.find({
  value: { $exists: false }
});
```

Chỉ khớp tài liệu `missing`, vì tài liệu đó không chứa khóa `value`.

### 4.2. Tìm trường tồn tại

```javascript
db.fieldStatesDemo.find({
  value: { $exists: true }
});
```

Khớp bốn tài liệu `null`, `emptyString`, `emptyArray` và `text`. Dù `null`, `""` và `[]` đều có thể khiến giao diện trông “trống”, chúng vẫn là **giá trị của trường có tồn tại**.

| Tài liệu mẫu | `$exists: false` | `$exists: true` |
|---|:---:|:---:|
| `{ _id: "missing" }` | Có | Không |
| `{ _id: "null", value: null }` | Không | Có |
| `{ _id: "emptyString", value: "" }` | Không | Có |
| `{ _id: "emptyArray", value: [] }` | Không | Có |
| `{ _id: "text", value: "MongoDB" }` | Không | Có |

### 4.3. Phân biệt thiếu và null bằng hai điều kiện riêng

**Chỉ tìm trường thiếu:**

```javascript
db.fieldStatesDemo.find({
  value: { $exists: false }
});
```

**Chỉ tìm trường có BSON Null trong bộ mẫu:**

```javascript
db.fieldStatesDemo.find({
  value: { $type: "null" }
});
```

Trong một số tình huống có thể dùng `{ value: { $exists: true, $eq: null } }` để loại tài liệu thiếu, nhưng phép so sánh bằng có ngữ nghĩa riêng khi trường là mảng. Nếu muốn xác định **kiểu chính xác ở cấp trường**, phép tính `$type` trong aggregation (xem phần 7) là cách rõ ràng.

## 5. `$type`: xem giá trị thuộc kiểu BSON nào

MongoDB không tự suy luận rằng một chuỗi rỗng “tương đương” với null. `""` vẫn là kiểu `string`; `[]` vẫn là kiểu `array`.

```javascript
db.fieldStatesDemo.find({ value: { $type: "null" } });
// Bộ mẫu: null

db.fieldStatesDemo.find({ value: { $type: "string" } });
// Bộ mẫu: emptyString, text

db.fieldStatesDemo.find({ value: { $type: "array" } });
// Bộ mẫu: emptyArray
```

Điều cần nhớ:

- `$type: "string"` kiểm tra **kiểu chuỗi**, không kiểm tra chuỗi có rỗng hay không.
- `$type: "array"` kiểm tra **kiểu mảng**, không kiểm tra mảng có bao nhiêu phần tử.
- `$type: "null"` tìm giá trị BSON Null, không tự biến trường thiếu thành null.
- Với trường có kiểu mảng, toán tử `$type` trong bộ lọc truy vấn có thể có ngữ nghĩa khớp **kiểu của phần tử trong mảng**. Khi cần phân loại kiểu của *chính trường đó*, dùng biểu thức aggregation `{ $type: "$value" }`.

Điểm cuối cùng rất dễ nhầm:

```javascript
// $type trong filter: biểu thức truy vấn lên trường.
db.fieldStatesDemo.find({ value: { $type: "string" } });

// $type trong aggregation: trả về tên kiểu của biểu thức "$value".
db.fieldStatesDemo.aggregate([
  { $project: { valueType: { $type: "$value" } } }
]);
```

Với bộ mẫu không có mảng chứa chuỗi, hai cách trên không tạo ra mâu thuẫn. Nhưng nếu thêm tài liệu như `{ value: ["A"] }`, bộ lọc `$type: "string"` có thể khớp do phần tử `"A"`, trong khi biểu thức aggregation sẽ phân loại chính trường `value` là `"array"`.

## 6. Chuỗi rỗng và mảng rỗng: cùng rỗng, khác kiểu và điều kiện

### 6.1. Chuỗi rỗng: `""`

```javascript
db.fieldStatesDemo.find({ value: "" });
// Bộ mẫu: emptyString
```

Đây là phép so sánh với một chuỗi có độ dài bằng 0. Nó không tự tìm `null`, trường thiếu hoặc mảng rỗng. Tuy nhiên, do ngữ nghĩa so khớp phần tử mảng, **một mảng chứa chuỗi rỗng** cũng có thể khớp biểu thức bằng chuỗi rỗng:

```javascript
// Ví dụ minh họa riêng, không thêm vào bộ dữ liệu chính.
{ value: ["", "MongoDB"] }
```

Nếu cần đòi hỏi rằng **toàn bộ trường phải là một chuỗi rỗng**, có thể kiểm tra kiểu ở cấp trường bằng aggregation:

```javascript
db.fieldStatesDemo.aggregate([
  {
    $match: {
      $expr: {
        $and: [
          { $eq: [{ $type: "$value" }, "string"] },
          { $eq: ["$value", ""] }
        ]
      }
    }
  }
]);
```

Biểu thức trên tách hai yêu cầu: kiểu gốc phải là `string` và giá trị phải bằng `""`. Đừng mặc định hai cách lọc này có kế hoạch index tương đương; dùng `explain` khi hiệu năng quan trọng.

### 6.2. Mảng rỗng: `[]`

Để tìm trường chứa một **mảng có 0 phần tử**, toán tử rất trực quan là `$size`:

```javascript
db.fieldStatesDemo.find({
  value: { $size: 0 }
});
// Bộ mẫu: emptyArray
```

`$size: 0` kiểm tra độ dài mảng bằng 0; nó không khớp chuỗi rỗng vì chuỗi không phải mảng.

Cũng có thể viết so sánh bằng với mảng:

```javascript
db.fieldStatesDemo.find({ value: [] });
// Bộ mẫu: emptyArray
```

Trong bộ mẫu đơn giản này, hai câu cho kết quả như nhau. Tuy nhiên, so sánh bằng một giá trị mảng có các quy tắc khớp riêng, gồm cả tình huống phần tử lồng nhau; muốn biểu đạt “trường là mảng và độ dài bằng 0”, `$size: 0` thể hiện chủ đích rõ hơn.

Một vài giá trị trông “rỗng” nhưng hoàn toàn khác nhau:

| Giá trị | Kiểu | `$size: 0` khớp? |
|---|---|:---:|
| Không có trường | Missing | Không |
| `null` | Null | Không |
| `""` | String | Không |
| `[]` | Array | Có |
| `[""]` | Array có 1 chuỗi rỗng | Không |
| `[null]` | Array có 1 phần tử null | Không |
| `{}` | Object rỗng | Không |

**Lưu ý hiệu năng:** `$size` không phải một điều kiện thường được phục vụ trực tiếp bằng index để tính độ dài mảng. Trên tập lớn, nếu nghiệp vụ lọc theo số phần tử rất thường xuyên, có thể cân nhắc lưu **trường đếm** riêng và cập nhật nhất quán với mảng. Chỉ bổ sung dữ liệu dẫn xuất khi có nhu cầu được đo lường thực tế.

### 6.3. Bảng kết quả của những điều kiện quan trọng

Bảng dưới dùng đúng năm tài liệu đã thêm ở phần 2:

| Bộ lọc `value` | `missing` | `null` | `emptyString` | `emptyArray` | `text` |
|---|:---:|:---:|:---:|:---:|:---:|
| `{ value: null }` | ✓ | ✓ | — | — | — |
| `{ value: { $exists: false } }` | ✓ | — | — | — | — |
| `{ value: { $exists: true } }` | — | ✓ | ✓ | ✓ | ✓ |
| `{ value: { $type: "null" } }` | — | ✓ | — | — | — |
| `{ value: "" }` | — | — | ✓ | — | — |
| `{ value: { $type: "string" } }` | — | — | ✓ | — | ✓ |
| `{ value: { $size: 0 } }` | — | — | — | ✓ | — |
| `{ value: { $ne: null } }` | — | — | ✓ | ✓ | ✓ |
| `{ value: { $ne: "" } }` | ✓ | ✓ | — | ✓ | ✓ |

Bảng mô tả **chính xác bộ mẫu đã định nghĩa**, nơi các giá trị chỉ có một tầng; nếu ứng dụng lưu mảng chứa chuỗi hoặc null, một số biểu thức so sánh bằng cần phân tích thêm ngữ nghĩa khớp phần tử mảng.

## 7. Aggregation: phân loại đủ bốn trạng thái trong cùng một pipeline

Khi cần làm thống kê dữ liệu chất lượng kém, việc phân biệt cả bốn trạng thái trong một lần quét thường hữu ích hơn chạy nhiều câu `find()`.

### 7.1. `$type` trong aggregation nhận diện cả “missing”

```javascript
db.fieldStatesDemo.aggregate([
  {
    $project: {
      _id: 1,
      state: { $type: "$value" }
    }
  }
]);
```

Kết quả minh họa (không giả định thứ tự tài liệu trả về):

```javascript
{ _id: "missing",     state: "missing" }
{ _id: "null",        state: "null" }
{ _id: "emptyString", state: "string" }
{ _id: "emptyArray",  state: "array" }
{ _id: "text",        state: "string" }
```

Đây là một điểm rất quan trọng: **`"missing"` là kết quả của biểu thức `$type` trong aggregation**, không phải một kiểu BSON để gán trực tiếp cho trường. Vì vậy, câu kiểu `{ value: { $type: "missing" } }` không phải cách thay thế chuẩn cho `$exists: false` trong bộ lọc truy vấn.

### 7.2. `$ifNull` gộp missing và null nhưng giữ nguyên hai giá trị rỗng khác

```javascript
db.fieldStatesDemo.aggregate([
  {
    $project: {
      valueType: { $type: "$value" },
      normalized: {
        $ifNull: ["$value", "(chưa có giá trị)"]
      }
    }
  }
]);
```

`$ifNull` xem giá trị **missing**, **undefined** hoặc **null** như trường hợp cần thay bằng giá trị dự phòng. Trong ví dụ:

- `missing` → `"(chưa có giá trị)"`.
- `null` → `"(chưa có giá trị)"`.
- `emptyString` → giữ nguyên `""`.
- `emptyArray` → giữ nguyên `[]`.
- `text` → giữ nguyên `"MongoDB"`.

Điều này có nghĩa `$ifNull` không phải hàm “thay mọi giá trị rỗng”. Muốn thay cả chuỗi rỗng hoặc mảng rỗng, cần thêm điều kiện nghiệp vụ cụ thể; còn nếu muốn giữ **phân biệt null với missing**, đừng chuẩn hóa bằng `$ifNull` trước khi lưu trạng thái gốc.

### 7.3. Phân loại rõ cả chuỗi rỗng và mảng rỗng

Có thể dùng `$switch` để gắn nhãn trạng thái mà không đánh đồng chúng:

```javascript
db.fieldStatesDemo.aggregate([
  {
    $set: {
      state: {
        $switch: {
          branches: [
            {
              case: { $eq: [{ $type: "$value" }, "missing"] },
              then: "MISSING"
            },
            {
              case: { $eq: [{ $type: "$value" }, "null"] },
              then: "NULL"
            },
            {
              case: {
                $and: [
                  { $eq: [{ $type: "$value" }, "string"] },
                  { $eq: ["$value", ""] }
                ]
              },
              then: "EMPTY_STRING"
            },
            {
              case: {
                $and: [
                  { $isArray: "$value" },
                  {
                    $eq: [
                      {
                        $cond: [
                          { $isArray: "$value" },
                          { $size: "$value" },
                          null
                        ]
                      },
                      0
                    ]
                  }
                ]
              },
              then: "EMPTY_ARRAY"
            }
          ],
          default: "OTHER_VALUE"
        }
      }
    }
  },
  { $project: { _id: 1, state: 1 } }
]);
```

Trong nhánh `EMPTY_ARRAY`, `$cond` bảo đảm `$size` chỉ tính với giá trị thực sự là mảng. Biểu thức `$size` trong aggregation đòi toán hạng là mảng; nếu đưa trực tiếp chuỗi, null hoặc trường thiếu vào mà không bảo vệ kiểu, pipeline có thể trả lỗi. Với dữ liệu mà schema bảo đảm `value` luôn là mảng, có thể viết ngắn hơn.

Nếu chỉ muốn **đếm** số tài liệu theo trạng thái, nối thêm:

```javascript
// Đặt sau stage $set tạo state ở pipeline phía trên.
{ $group: { _id: "$state", count: { $sum: 1 } } }
```

Cách phân loại này hữu ích khi kiểm kê dữ liệu để chuẩn hóa schema, làm báo cáo hay chuẩn bị migration; nó không bắt buộc phải chạy trong mỗi yêu cầu sản xuất.

## 8. Các thao tác cập nhật làm trạng thái thay đổi ra sao?

MongoDB không tự chuyển chuỗi rỗng thành null hoặc tự xóa trường có mảng rỗng. Trạng thái mới phụ thuộc chính xác vào toán tử cập nhật.

### 8.1. `$set` ghi giá trị, kể cả giá trị rỗng

```javascript
// Cập nhật một tài liệu sang BSON Null.
db.fieldStatesDemo.updateOne(
  { _id: "text" },
  { $set: { value: null } }
);

// Đổi sang chuỗi rỗng.
db.fieldStatesDemo.updateOne(
  { _id: "text" },
  { $set: { value: "" } }
);

// Đổi sang mảng rỗng.
db.fieldStatesDemo.updateOne(
  { _id: "text" },
  { $set: { value: [] } }
);
```

Ba lệnh trên minh họa các trạng thái kế tiếp của **cùng một tài liệu** nếu chạy tuần tự. Mỗi lệnh vẫn giữ nguyên khóa `value`; chỉ thay đổi giá trị và kiểu của nó.

### 8.2. `$unset` xóa hẳn trường

```javascript
db.fieldStatesDemo.updateOne(
  { _id: "text" },
  { $unset: { value: "" } }
);
```

Sau lệnh này, tài liệu `text` không còn khóa `value`. Khi truy vấn `{ value: { $exists: false } }`, nó sẽ khớp cùng nhóm với `missing`. Giá trị được đặt cạnh `$unset` chỉ đóng vai trò chỉ định trường cần xóa, không phải một chuỗi để ghi vào trường.

### 8.3. Thêm trường vào tài liệu chưa có

```javascript
db.fieldStatesDemo.updateOne(
  { _id: "missing" },
  { $set: { value: null } }
);
```

Lệnh trên **tạo khóa `value` có giá trị null** trong tài liệu `missing`. Nó không để trường ở trạng thái thiếu. Muốn trường không xuất hiện, không đưa nó vào tài liệu mới hoặc dùng `$unset` để xóa.

**Ghi nhớ khi luyện tập:** sau khi chạy các ví dụ cập nhật ở phần 8, bộ dữ liệu không còn đúng các trạng thái ban đầu. Những bảng kết quả ở phần 6.3 chỉ áp dụng trước các lệnh cập nhật; nếu cần thử lại, dùng một collection thử nghiệm mới.

## 9. Trường hợp ứng dụng: “không gửi”, “xóa”, “để trống”, “không có phần tử”

### 9.1. API cập nhật hồ sơ người dùng

Giả sử API cập nhật hồ sơ nhận `nickname` và `tags`. Hãy thiết kế ngữ nghĩa rõ ràng cho từng trường:

| Payload ứng dụng | Cách diễn giải *nếu API quy định như vậy* | Thao tác MongoDB có thể dùng |
|---|---|---|
| Không gửi `nickname` | Giữ nguyên biệt danh hiện tại | Không đưa `nickname` vào update |
| `nickname: null` | Chủ động bỏ biệt danh | `$unset: { nickname: "" }` |
| `nickname: ""` | Lưu chuỗi rỗng, hoặc báo lỗi dữ liệu | `$set` chuỗi rỗng, hoặc từ chối |
| `nickname: "An"` | Đặt biệt danh mới | `$set: { nickname: "An" }` |
| Không gửi `tags` | Giữ nguyên danh sách tag | Không cập nhật `tags` |
| `tags: []` | Xóa tất cả tag nhưng giữ cấu trúc mảng | `$set: { tags: [] }` |
| `tags: null` | Có thể không hợp lệ nếu schema yêu cầu mảng | Kiểm tra hợp lệ, có thể từ chối |

**Đây là chính sách do API tự định nghĩa.** MongoDB không tự hiểu JSON `null` là lệnh xóa. Nếu mã ứng dụng gửi `$set: { nickname: null }`, MongoDB sẽ lưu null; nếu mã gửi `$unset`, MongoDB sẽ xóa hẳn trường.

Điều này đặc biệt quan trọng với những API cập nhật từng phần. Một chương trình dùng `if (value == null)` để bỏ qua mọi trường sẽ **đánh đồng** “không gửi trường” với “người dùng gửi null”. Muốn phân biệt, cần biết khóa có hiện diện trong request hay không trước khi quyết định thao tác database.

### 9.2. Java driver: phân biệt `containsKey` và `get`

Trong Java, một `Document` đóng vai trò bản đồ khóa/giá trị; có thể tạo bốn trạng thái rõ ràng:

```java
import java.util.List;
import org.bson.Document;

Document missing = new Document("_id", "missing");
Document withNull = new Document("_id", "null")
    .append("value", null);
Document emptyString = new Document("_id", "emptyString")
    .append("value", "");
Document emptyArray = new Document("_id", "emptyArray")
    .append("value", List.of());
```

Nếu chỉ gọi `document.get("value")`, Java trả về `null` cho cả trường **không có khóa** và trường **có khóa với giá trị Java null**. Cần kiểm tra sự tồn tại trước:

```java
Object value = document.get("value");

if (!document.containsKey("value")) {
    System.out.println("Trường không tồn tại");
} else if (value == null) {
    System.out.println("Trường tồn tại với BSON Null");
} else if (value instanceof String text && text.isEmpty()) {
    System.out.println("Chuỗi rỗng");
} else if (value instanceof List<?> items && items.isEmpty()) {
    System.out.println("Mảng rỗng");
} else {
    System.out.println("Có giá trị khác");
}
```

Ví dụ này áp dụng cho dữ liệu được đọc/biểu diễn dưới dạng `org.bson.Document` với chuỗi và danh sách Java thông thường. Nếu ứng dụng dùng POJO codec, Spring Data hoặc JSON mapper, cần xem quy tắc serialize field null/absent của công cụ tương ứng. Tùy cấu hình, một giá trị null trong đối tượng ứng dụng có thể bị bỏ qua khi ghi; **kiểm tra kết quả BSON thật**, không chỉ giá trị trong object Java.

### 9.3. Có nên “lấp đầy” mọi trường để schema đồng nhất?

Không có đáp án duy nhất. Một số nguyên tắc thiết kế:

- Với trường **bắt buộc**, nên yêu cầu nó luôn tồn tại và có kiểu phù hợp.
- Với trường **không bắt buộc**, chọn nhất quán giữa “không có trường” và “có trường nhưng null” theo nhu cầu nghiệp vụ.
- Với trường **danh sách**, mảng rỗng thường diễn đạt danh sách hiện không có phần tử rõ ràng hơn null, nếu schema coi đây là một danh sách.
- Với trường **chuỗi**, quyết định trước chuỗi rỗng có được chấp nhận không; đừng dùng cả null, missing và chuỗi rỗng làm ba cách ngẫu nhiên để chỉ cùng một ý.

Ví dụ, trường `phoneNumber` có thể cho phép thiếu khi người dùng chưa cung cấp; trường `tags` có thể mặc định là `[]`. Hai lựa chọn này là quyết định **mô hình dữ liệu** và **hợp đồng API**, không phải tối ưu truy vấn trước tiên.

## 10. Schema validation: kiểm soát trạng thái nào được lưu

MongoDB hỗ trợ xác thực schema bằng `$jsonSchema` ở cấp collection. Có thể dùng để áp đặt cả **sự tồn tại** và **kiểu giá trị**.

Ví dụ một collection hồ sơ dùng `displayName` bắt buộc là chuỗi không rỗng, còn `tags` nếu có thì phải là mảng:

```javascript
db.createCollection("validatedProfilesDemo", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["displayName"],
      properties: {
        displayName: {
          bsonType: "string",
          minLength: 1,
          description: "Tên hiển thị bắt buộc, không được rỗng"
        },
        tags: {
          bsonType: "array",
          description: "Danh sách tag khi được cung cấp"
        }
      }
    }
  }
});
```

Tác động của những quy tắc này:

| Dữ liệu | `displayName` | `tags` |
|---|---|---|
| Trường không tồn tại | Không hợp lệ vì nằm trong `required` | Hợp lệ vì không nằm trong `required` |
| `null` | Không hợp lệ do `bsonType: "string"` | Không hợp lệ nếu được gửi vì phải là array |
| `""` | Không hợp lệ do `minLength: 1` | Không hợp lệ vì String không phải Array |
| `[]` | Không hợp lệ vì Array không phải String | Hợp lệ vì mảng rỗng vẫn là mảng |
| `"An"` | Hợp lệ | Không hợp lệ nếu là giá trị `tags` |

Nếu `tags` cũng phải tồn tại, thêm `"tags"` vào mảng `required`. Nếu mảng `tags` phải có ít nhất một phần tử, thêm `minItems: 1` vào quy tắc của `tags`. Với yêu cầu một trường có thể là null **hoặc** chuỗi không rỗng, cần mô tả rõ hai trường hợp hợp lệ, chẳng hạn kết hợp `anyOf` với hai nhánh BSON Null và String có `minLength`.

Schema validation giúp tránh việc các trạng thái “rỗng” bị trộn tùy tiện ngay khi ghi. Song phải triển khai cùng quy tắc phía ứng dụng và kế hoạch xử lý dữ liệu cũ nếu collection trước đó đã chứa dữ liệu không đồng nhất.

## 11. Index và hiệu năng khi lọc những trạng thái đặc biệt

Điều kiện lọc theo kiểu dữ liệu và sự hiện diện của trường có thể ảnh hưởng đến cách MongoDB sử dụng index.

### 11.1. Index thường và những giá trị vắng mặt

```javascript
db.fieldStatesDemo.createIndex({ value: 1 });
```

Index một trường thông thường có thể tạo khóa cho tài liệu không có trường index và tài liệu có giá trị null theo những quy tắc index của MongoDB. Vì vậy, chỉ nhìn vào khóa index không nhất thiết đủ để tách “missing” khỏi “explicit null” theo cách trực giác. Một truy vấn kiểm tra `$exists` có thể cần đọc tài liệu hoặc chịu giới hạn tối ưu khác.

### 11.2. Sparse index và partial index

Một **sparse index** một trường bỏ qua các tài liệu không chứa trường được index, nhưng tài liệu có trường `value: null` vẫn chứa trường nên có thể được đưa vào index:

```javascript
// Ví dụ cho collection khác, không tạo cùng key pattern
// để thay thế mặc định cho index của bài thử nghiệm.
db.sparseIndexDemo.createIndex(
  { optionalValue: 1 },
  { sparse: true }
);
```

**Partial index** cho phép chỉ index những tài liệu thỏa một bộ lọc đã định, hữu ích khi truy vấn chủ yếu nhắm một nhóm nhỏ trạng thái:

```javascript
db.optionalUsersDemo.createIndex(
  { nickname: 1 },
  {
    unique: true,
    partialFilterExpression: {
      nickname: { $type: "string" }
    }
  }
);
```

Ở ví dụ này, chỉ những tài liệu có `nickname` thuộc nhóm thỏa điều kiện kiểu chuỗi mới tham gia ràng buộc duy nhất của index. **Chuỗi rỗng vẫn là chuỗi**, nên nhiều tài liệu chứa cùng `nickname: ""` có thể vi phạm tính duy nhất; trạng thái “không có trường” lại khác.

Với index unique một trường thông thường, các tài liệu có giá trị null hoặc thiếu trường có thể tranh chấp cùng một khóa null; một partial unique index có thể phù hợp hơn khi muốn cho phép nhiều tài liệu chưa có biệt danh, nhưng vẫn giữ biệt danh **thực sự có giá trị** là duy nhất.

Lưu ý: bộ lập kế hoạch chỉ dùng partial index cho truy vấn phù hợp với điều kiện lọc của index. Đừng tạo partial index chỉ để tiết kiệm dung lượng rồi cho rằng mọi biểu thức tìm kiếm đều sử dụng nó.

### 11.3. Đo kế hoạch thực tế

```javascript
db.fieldStatesDemo.find({
  value: { $exists: false }
}).explain("executionStats");

db.fieldStatesDemo.find({
  value: { $type: "null" }
}).explain("executionStats");

db.fieldStatesDemo.find({
  value: { $size: 0 }
}).explain("executionStats");
```

Quan sát `COLLSCAN`, `IXSCAN`, `FETCH`, `totalDocsExamined` và `totalKeysExamined` nếu được trả về. Với chỉ năm tài liệu mẫu, MongoDB có thể chọn collection scan dù đã có index vì quét dữ liệu nhỏ rất rẻ. Để kết luận về hiệu năng, cần so sánh trên dữ liệu có quy mô và phân bố giống hệ thống thực tế.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `null` giống trường thiếu | `null` là giá trị BSON của một khóa có tồn tại; trường thiếu không có khóa |
| `{ value: null }` chỉ tìm explicit null | Nó cũng khớp tài liệu không có `value` và cần lưu ý ngữ nghĩa mảng |
| `$exists: true` nghĩa là có giá trị khác null | Nó vẫn khớp null, chuỗi rỗng và mảng rỗng |
| `$type: "string"` nghĩa là chuỗi có nội dung | Chuỗi rỗng vẫn có kiểu String |
| `[]` và `""` đều rỗng nên truy vấn bằng nhau | Chúng có kiểu BSON khác nhau và cần toán tử khác nhau |
| `$size: 0` dùng để tìm mọi giá trị rỗng | Nó dành cho mảng có độ dài 0 |
| `$ifNull` thay được mọi dạng dữ liệu rỗng | Nó xử lý null/missing, giữ nguyên `""` và `[]` |
| `$set: { value: null }` xóa trường | `$set` lưu giá trị null; `$unset` mới xóa khóa |
| `document.get("value") == null` đủ để biết trường thiếu | Trong Java `Document` cần thêm `containsKey` |
| Index tự giải quyết sự không nhất quán null/missing/empty | Index không thay schema; chính sách nhập và lưu dữ liệu phải nhất quán |

## 13. Bài tập thực hành

### Bài tập 1 — Dự đoán bộ lọc

Với năm tài liệu tạo ở phần 2 **trước khi chạy update**, hãy xác định `_id` nào khớp:

```javascript
db.fieldStatesDemo.find({ value: null });
db.fieldStatesDemo.find({ value: { $exists: false } });
db.fieldStatesDemo.find({ value: { $type: "null" } });
db.fieldStatesDemo.find({ value: "" });
db.fieldStatesDemo.find({ value: { $size: 0 } });
db.fieldStatesDemo.find({ value: { $ne: null } });
```

Đối chiếu sau khi tự dự đoán với bảng ở phần 6.3 và giải thích kết quả bằng **sự tồn tại của trường**, **kiểu BSON** và **ngữ nghĩa toán tử**.

### Bài tập 2 — Nhận diện trạng thái trong aggregation

Viết một pipeline trả về hai trường `_id` và `state` với các nhãn:

```text
missing       -> MISSING
null          -> NULL
emptyString   -> EMPTY_STRING
emptyArray    -> EMPTY_ARRAY
text          -> OTHER_VALUE
```

Hãy sử dụng `$type`, `$switch`, `$isArray` và `$size` khi phù hợp. Sau đó thêm `$group` để đếm số tài liệu mỗi loại. Bạn có thể bắt đầu từ pipeline ở phần 7 và rút gọn những nhánh không cần thiết cho dữ liệu đã chuẩn hóa.

### Bài tập 3 — Xác định kết quả của cập nhật

Xét tài liệu:

```javascript
{ _id: "profile-1", nickname: "An", tags: ["mongodb"] }
```

Sau mỗi thao tác sau, hãy xác định **khóa có còn tồn tại không, kiểu BSON và giá trị là gì**:

```javascript
db.profilesDemo.updateOne(
  { _id: "profile-1" },
  { $set: { nickname: null } }
);

db.profilesDemo.updateOne(
  { _id: "profile-1" },
  { $set: { tags: [] } }
);

db.profilesDemo.updateOne(
  { _id: "profile-1" },
  { $unset: { nickname: "" } }
);
```

Chỉ chạy sau khi đã tạo tài liệu ví dụ trong collection thử nghiệm `profilesDemo`. Không lẫn lộn các thao tác trên với việc thiếu trường trong JSON request; đó là trách nhiệm của lớp API chuyển đổi yêu cầu thành toán tử cập nhật.

### Bài tập 4 — Thiết kế quy ước dữ liệu

Một ứng dụng lưu `email` và `favoriteCategories`. Hãy trả lời:

1. Khi người dùng chưa khai báo email, ứng dụng sẽ lưu **missing** hay **null**? Vì sao?
2. Khi người dùng bỏ hết mục yêu thích, nên lưu `[]` hay xóa trường? Trường hợp nào phù hợp với giao diện và hợp đồng API?
3. Có chấp nhận `email: ""` không? Nếu không, sẽ kiểm tra từ API hay `$jsonSchema`?
4. API cập nhật từng phần sẽ phân biệt “không gửi email” với “gửi email=null” bằng cách nào?
5. Nếu cần tìm hồ sơ chưa khai báo email, tại sao `{ email: null }` chưa chắc phản ánh đúng định nghĩa nghiệp vụ?

**Ghi nhớ:** Muốn truy vấn chính xác, hãy tách ba câu hỏi: **trường có tồn tại không?** (dùng `$exists`), **giá trị thuộc kiểu gì?** (dùng `$type`), và **giá trị có rỗng theo tiêu chí của kiểu đó không?** (ví dụ `""` cho chuỗi, `$size: 0` cho mảng). Trong MongoDB, *không có trường*, *BSON Null*, *chuỗi rỗng* và *mảng rỗng* là bốn trạng thái dữ liệu khác nhau, có thể dẫn tới bốn hành vi truy vấn và cập nhật khác nhau.
