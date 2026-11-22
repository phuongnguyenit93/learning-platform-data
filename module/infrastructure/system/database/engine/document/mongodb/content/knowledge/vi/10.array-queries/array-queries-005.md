# Kiểm tra kích thước mảng với $size và biểu thức phù hợp trong MongoDB

MongoDB cho phép một trường document chứa **array (mảng)**. Từ đó xuất hiện nhiều nhu cầu truy vấn theo số phần tử: tìm giỏ hàng có đúng ba dòng sản phẩm, tìm tài khoản chưa có vai trò nào, tìm học viên có ít nhất hai kỹ năng, hoặc tìm đơn hàng chứa quá nhiều mục hàng. MongoDB cung cấp toán tử truy vấn **$size** cho điều kiện **mảng có đúng N phần tử**. Khi phải so sánh số phần tử theo khoảng, so sánh hai mảng hoặc đếm những phần tử thỏa điều kiện, cần dùng biểu thức tính toán như **$size, $expr, $filter, $gt, $gte, $lt, $lte**.

Điểm cần phân biệt ngay là MongoDB có **hai cách dùng cùng tên $size**:

- **$size query operator**: viết trong filter của một trường, nhận **số nguyên không âm N** và khớp những document mà trường ấy là array có đúng N phần tử.
- **$size aggregation expression**: nhận **biểu thức trả về array**, đếm và trả về **số phần tử**. Có thể dùng trong aggregation pipeline hoặc đặt bên trong **$expr** của find().

Hai cách có cú pháp và quy tắc xử lý dữ liệu sai kiểu khác nhau. Bài học sẽ đi từ ví dụ truy vấn cơ bản đến so sánh động, xử lý null/trường thiếu, mảng lồng nhau, đếm theo điều kiện, Java và tối ưu index.

## 1. Kích thước mảng thực sự là gì?

Kích thước của array là số **phần tử trực tiếp** ở cấp đang được xét. Nó không phải số byte BSON, không phải số ký tự chuỗi, không phải số giá trị phân biệt và cũng không tự tính tổng số phần tử trong các mảng con.

| Giá trị trường tags | Kích thước | Giải thích |
|---|---:|---|
| [] | 0 | Array rỗng |
| ["mongo"] | 1 | Một phần tử |
| ["mongo", "java"] | 2 | Hai phần tử |
| ["mongo", "mongo"] | 2 | Hai phần tử dù trùng giá trị |
| [["mongo", "java"], "docker"] | 2 | Array con là một phần tử của array ngoài |
| [{name: "A"}, {name: "B"}] | 2 | Hai embedded document |
| null | Không phải array | BSON Null |
| "mongo" | Không phải array | BSON String |
| Trường không có trong document | Không phải array | Không có giá trị để đếm |

Ví dụ một đơn hàng có hai dòng items, mỗi dòng có quantity lần lượt là 2 và 4: **$size của items bằng 2**, còn **tổng số đơn vị hàng bằng 6**. Nếu nghiệp vụ cần tổng quantity, phải dùng phép cộng giá trị trong các phần tử thay vì $size.

## 2. Dữ liệu mẫu để thực hành

Trong mongosh, chọn database riêng:

~~~javascript
use array_size_lab
~~~

Giả sử collection **students** còn trống. Chạy đoạn dữ liệu mẫu một lần:

~~~javascript
db.students.insertMany([
  {
    _id: "S01",
    name: "An",
    groups: ["java", "mongo"],
    scores: [80, 90, 75]
  },
  {
    _id: "S02",
    name: "Bình",
    groups: [],
    scores: [60]
  },
  {
    _id: "S03",
    name: "Chi",
    groups: ["mongo"],
    scores: [100, 65]
  },
  {
    _id: "S04",
    name: "Dũng",
    groups: ["java", "mongo", "docker"],
    scores: []
  },
  {
    _id: "S05",
    name: "Hà",
    groups: null,
    scores: null
  },
  {
    _id: "S06",
    name: "Huy"
  },
  {
    _id: "S07",
    name: "Lan",
    groups: "mongo",
    scores: "90"
  },
  {
    _id: "S08",
    name: "Minh",
    groups: ["java", "java"],
    scores: [80, 80]
  },
  {
    _id: "S09",
    name: "Nam",
    groups: [["java", "mongo"], "docker"],
    scores: [95, 70, 85, 55]
  },
  {
    _id: "S10",
    name: "Vy",
    groups: ["kafka", "mongo", "redis", "java"],
    scores: [88, 92, 77, 91, 66]
  }
])
~~~

Các document **S05, S06, S07** được cố tình thiết kế không có array hợp lệ ở groups/scores, lần lượt là **null**, **field thiếu** và **String**, để quan sát khác biệt giữa $size query operator và aggregation expression.

| ID | groups | Số phần tử groups | Số phần tử scores |
|---|---|---:|---:|
| S01 | ["java", "mongo"] | 2 | 3 |
| S02 | [] | 0 | 1 |
| S03 | ["mongo"] | 1 | 2 |
| S04 | ["java", "mongo", "docker"] | 3 | 0 |
| S05 | null | Không phải array | Không phải array |
| S06 | Thiếu field | Không phải array | Không phải array |
| S07 | "mongo" | Không phải array | Không phải array |
| S08 | ["java", "java"] | 2 | 2 |
| S09 | [["java", "mongo"], "docker"] | 2 | 4 |
| S10 | ["kafka", "mongo", "redis", "java"] | 4 | 5 |

Để xem document theo thứ tự ID:

~~~javascript
db.students.find().sort({ _id: 1 })
~~~

Không nên dựa vào thứ tự mặc định của find(); đặt **sort()** khi muốn kiểm tra các kết quả dự kiến trong bài. Các ví dụ kết quả dưới đây áp dụng cho dữ liệu ban đầu, trước khi chạy phần update về sau.

## 3. $size query operator: đúng N phần tử

Cú pháp:

~~~javascript
db.collection.find({
  arrayField: { $size: N }
})
~~~

**N phải là số nguyên không âm**. Ví dụ:

~~~javascript
db.students.find(
  { groups: { $size: 2 } },
  { _id: 1, name: 1, groups: 1 }
).sort({ _id: 1 })
~~~

Kết quả: **S01, S08, S09**. S08 vẫn khớp vì hai phần tử "java" trùng nhau nhưng vẫn nằm ở hai vị trí; S09 khớp vì array con ["java", "mongo"] được tính là **một phần tử của mảng ngoài**.

Một số truy vấn khác:

~~~javascript
// Mảng rỗng: S02
db.students.find({ groups: { $size: 0 } })

// Đúng một nhóm: S03
db.students.find({ groups: { $size: 1 } })

// Đúng ba nhóm: S04
db.students.find({ groups: { $size: 3 } })

// Đúng bốn nhóm: S10
db.students.find({ groups: { $size: 4 } })
~~~

**$size: 0 chỉ tìm array rỗng**. Nó không coi groups: null (S05), groups không tồn tại (S06) hoặc groups: "mongo" (S07) là array không có phần tử. Những giá trị này không khớp query operator $size.

### 3.1. Áp dụng với field lồng nhau

Ví dụ document đơn hàng:

~~~javascript
{
  orderCode: "ORD-001",
  customer: {
    contacts: ["email", "phone"]
  }
}
~~~

Query dùng đường dẫn dấu chấm:

~~~javascript
db.orders.find({
  "customer.contacts": { $size: 2 }
})
~~~

Toán tử chỉ đếm số phần tử trực tiếp của **customer.contacts**, không đếm tất cả trường khác trong document.

### 3.2. Các cú pháp dễ nhầm

~~~javascript
// SAI: query $size không nhận một toán tử điều kiện.
{ groups: { $size: { $gt: 2 } } }

// SAI: kích thước không thể là số âm.
{ groups: { $size: -1 } }

// SAI: không truyền chuỗi thay cho kích thước nguyên.
{ groups: { $size: "2" } }

// ĐÚNG: kiểm tra đúng hai phần tử.
{ groups: { $size: 2 } }
~~~

Viết **{ groups: { $size: 2, $gt: 2 } }** cũng **không** có nghĩa "groups có nhiều hơn hai phần tử". $gt đặt cạnh $size được hiểu như một điều kiện so sánh giá trị trường theo quy tắc truy vấn MongoDB, không so sánh kết quả đếm. Muốn so sánh kích thước với một ngưỡng, cần dùng biểu thức $size như mục sau.

## 4. $size aggregation expression: tính số phần tử

Trong aggregation, $size nhận **một biểu thức trả về array** và cho ra con số kích thước:

~~~javascript
{
  $size: "$groups"
}
~~~

Chuỗi **"$groups"** là tham chiếu tới giá trị field groups của document hiện tại. Ví dụ trên không đồng nghĩa với query **{ groups: { $size: 2 } }**.

So sánh:

| Đặc điểm | $size query operator | $size aggregation expression |
|---|---|---|
| Cú pháp | { groups: { $size: 2 } } | { $size: "$groups" } |
| Nhận vào | Số nguyên không âm | Biểu thức trả về array |
| Công dụng | Kiểm tra độ dài chính xác | Trả về số phần tử để dùng trong tính toán |
| Có thể dùng với $gt/$lte | Không trực tiếp | Có, trong $expr hoặc pipeline |
| Khi field không phải array | Không khớp | Biểu thức $size phát sinh lỗi nếu đối số không phải array |

### 4.1. Tính trường groupCount trong $project

Nếu dữ liệu luôn có groups là array:

~~~javascript
db.students.aggregate([
  {
    $match: { groups: { $type: "array" } }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      groupCount: { $size: "$groups" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Stage $match chọn các document có groups là array; stage $project tính độ dài của field. Kết quả là S01, S02, S03, S04, S08, S09, S10 với groupCount lần lượt **2, 0, 1, 3, 2, 2, 4**.

Nếu bỏ bước $match ở tập dữ liệu mẫu, biểu thức **$size: "$groups"** có thể phát sinh lỗi ở S05/S06/S07 vì null, field thiếu và String **không phải array**.

### 4.2. $isArray + $cond để tránh lỗi với dữ liệu hỗn hợp

Khi không chắc field luôn là array, dùng cách có kiểm tra kiểu:

~~~javascript
db.students.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      groupCount: {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Trong biểu thức:

1. **$isArray** hỏi groups có đúng là array không.
2. **$cond** chọn groups nếu đúng, hoặc [] nếu không đúng.
3. **$size** đếm array được chọn, tránh lỗi.

Với chính sách này, S05, S06, S07 được **quy ước** groupCount bằng 0. Đây là quyết định xử lý đầu vào không hợp lệ; không có nghĩa null, missing hoặc String vốn là array rỗng.

### 4.3. $ifNull chỉ giải quyết null hoặc missing

Nếu schema đảm bảo groups chỉ có thể là array, null hoặc missing, cách ngắn hơn:

~~~javascript
{
  $size: {
    $ifNull: ["$groups", []]
  }
}
~~~

**$ifNull** thay giá trị null/missing bằng []; nó **không thay thế String "mongo"** của S07. Vì vậy, trên tập dữ liệu mẫu chưa chuẩn hóa, $size vẫn có thể lỗi. Khi cần xử lý cả trường sai kiểu không-null, sử dụng **$isArray + $cond**.

## 5. Tìm mảng có nhiều hơn N phần tử bằng $expr

Toán tử **$expr** cho phép dùng các biểu thức aggregation ngay trong filter của **find()**. Vì $size expression trả về một số, có thể dùng **$gt** để tìm những array dài hơn một ngưỡng:

~~~javascript
db.students.find({
  $expr: {
    $gt: [
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      },
      2
    ]
  }
}).sort({ _id: 1 })
~~~

Cách đọc:

~~~text
document.groups
    |
    v
Kiểm tra có phải array?
    |                |
   Có              Không
    |                |
  groups              []
    |                |
    +------ $size ----+
              |
              v
       Kích thước > 2 ?
         /         \
       true        false
~~~

Kết quả từ dữ liệu mẫu: **S04** (3 nhóm) và **S10** (4 nhóm).

Lưu ý: **$gt** đang so sánh **kết quả số** của biểu thức $size; không phải so sánh phần tử groups trực tiếp.

### 5.1. Ít nhất N phần tử với $gte

~~~javascript
db.students.find({
  $expr: {
    $gte: [
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      },
      2
    ]
  }
}).sort({ _id: 1 })
~~~

Kết quả: **S01, S04, S08, S09, S10**. S03 chỉ có một nhóm; S02 rỗng; S05/S06/S07 được quy đổi thành [] nên không qua ngưỡng.

### 5.2. Ít hơn N phần tử với $lt

~~~javascript
db.students.find({
  $expr: {
    $lt: [
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      },
      2
    ]
  }
}).sort({ _id: 1 })
~~~

Kết quả theo cách **coi non-array là []**: **S02, S03, S05, S06, S07**. Nếu nghiệp vụ chỉ chấp nhận **array thực sự**, đây không phải tập kết quả bạn muốn: cần loại S05/S06/S07 hoặc áp dụng schema validation để ngăn dữ liệu sai kiểu.

### 5.3. Tối đa N phần tử với $lte, nhưng bắt buộc là array

Muốn chỉ nhận những document có groups là array và kích thước tối đa hai, có thể kết hợp:

~~~javascript
db.students.find({
  $expr: {
    $and: [
      { $isArray: "$groups" },
      {
        $lte: [
          {
            $size: {
              $cond: [
                { $isArray: "$groups" },
                "$groups",
                []
              ]
            }
          },
          2
        ]
      }
    ]
  }
}).sort({ _id: 1 })
~~~

Kết quả: **S01, S02, S03, S08, S09**.

Ta vẫn dùng **$cond** bảo vệ $size dù đã có $isArray trong $and: không nên dựa vào giả định rằng MongoDB luôn đánh giá các nhánh $and theo thứ tự được viết trước khi gặp biểu thức có khả năng phát sinh lỗi.

### 5.4. Bảng quy đổi sáu phép so sánh kích thước

Giả sử **arr** là biểu thức chắc chắn trả về array:

| Nhu cầu | Biểu thức dùng bên trong $expr |
|---|---|
| Đúng N phần tử | { $eq: [{ $size: arr }, N] } |
| Khác N phần tử | { $ne: [{ $size: arr }, N] } |
| Nhiều hơn N phần tử | { $gt: [{ $size: arr }, N] } |
| Ít nhất N phần tử | { $gte: [{ $size: arr }, N] } |
| Ít hơn N phần tử | { $lt: [{ $size: arr }, N] } |
| Nhiều nhất N phần tử | { $lte: [{ $size: arr }, N] } |

Với yêu cầu **đúng N** của một trường array, query operator **{ groups: { $size: N } }** thường gọn hơn biểu thức $eq + aggregation $size. Những trường hợp còn lại mới cần phép tính hoặc một trường đếm riêng.

## 6. Phân biệt array rỗng, null, missing và sai kiểu

Một số tình huống có vẻ giống nhau trên giao diện nhưng khác nhau trong database:

~~~javascript
{ groups: [] }       // Array rỗng
{ groups: null }     // Field tồn tại, giá trị BSON Null
{ name: "Huy" }      // Không có field groups
{ groups: "mongo" }  // Field là String, không phải Array
~~~

Theo dữ liệu mẫu:

| Mục đích | Filter | Kết quả |
|---|---|---|
| Groups là array rỗng | { groups: { $size: 0 } } | S02 |
| Groups là null hoặc field thiếu | { groups: null } | S05, S06 |
| Groups không tồn tại | { groups: { $exists: false } } | S06 |
| Groups có tồn tại | { groups: { $exists: true } } | S01–S05, S07–S10 |
| Groups là array | { groups: { $type: "array" } } | S01–S04, S08–S10 |
| Groups là String | { groups: { $type: "string" } } | S07 |

Đây là lý do **$size: 0 không thay thế được $eq: null**.

### 6.1. "Chưa có nhóm" là quy tắc nghiệp vụ

Nếu ứng dụng định nghĩa "chưa có nhóm" gồm cả array rỗng, null và field thiếu:

~~~javascript
db.students.find({
  $or: [
    { groups: { $size: 0 } },
    { groups: null }
  ]
})
~~~

Kết quả: **S02, S05, S06**. String "mongo" của S07 không được tính là "chưa có nhóm".

Trong một hệ thống khác, null có thể mang nghĩa "chưa đồng bộ", missing mang nghĩa "dữ liệu cũ", còn [] mang nghĩa "không đăng ký". Hãy chọn bộ lọc dựa trên **định nghĩa nghiệp vụ**, thay vì gộp các trạng thái khác nhau chỉ để rút ngắn câu truy vấn.

### 6.2. Mảng có ít nhất một phần tử

Cách rõ ràng là kiểm tra độ dài > 0 bằng $expr như phần trước. Nếu schema đảm bảo groups luôn là array, có thể tận dụng sự tồn tại của vị trí 0:

~~~javascript
db.students.find({
  "groups.0": { $exists: true }
})
~~~

Mảng không rỗng có phần tử đầu tiên tại chỉ số 0. Cách này thường được dùng như một mẹo đơn giản để nhận diện array có ít nhất một phần tử. Tuy nhiên, nếu schema cho phép object có key "0" hoặc cấu trúc không đồng nhất, nên dùng biểu thức kiểm tra kiểu phù hợp. Không dùng mẹo **groups.0** cho điều kiện độ dài tùy ý như "ít nhất 10 phần tử" mà chưa xác định được ngữ nghĩa và khả năng index.

## 7. Mảng lồng nhau và phần tử trùng lặp

### 7.1. Mảng con chỉ là một phần tử ở cấp ngoài

S09 có:

~~~javascript
{
  _id: "S09",
  groups: [
    ["java", "mongo"],
    "docker"
  ]
}
~~~

**$size của groups bằng 2**. MongoDB không tự làm phẳng mảng con. Nếu cần đếm tất cả giá trị nằm trong nhiều cấp, phải định nghĩa số cấp cần duyệt rồi dùng các biểu thức như **$map**, **$reduce**, **$sum** hoặc thiết kế pipeline phù hợp.

Ví dụ, nếu muốn đếm các phần tử bên trong phần tử đầu tiên của groups ở document S09:

~~~javascript
db.students.aggregate([
  { $match: { _id: "S09" } },
  {
    $project: {
      outerCount: { $size: "$groups" },
      innerCount: { $size: { $arrayElemAt: ["$groups", 0] } }
    }
  }
])
~~~

Với đúng S09, hai giá trị lần lượt là **2** và **2**. Nhưng **innerCount** không phải biểu thức tổng quát cho mọi document: phần tử đầu tiên của S01 là String, nên áp dụng y nguyên trên toàn collection có thể báo lỗi.

### 7.2. Số phần tử không phải số phần tử phân biệt

S08 có groups: ["java", "java"]. **$size trả về 2**. Nếu cần số **giá trị phân biệt**, có thể dùng **$setUnion**:

~~~javascript
db.students.aggregate([
  { $match: { _id: "S08" } },
  {
    $project: {
      _id: 1,
      totalCount: { $size: "$groups" },
      distinctCount: {
        $size: { $setUnion: ["$groups", []] }
      }
    }
  }
])
~~~

Kết quả:

~~~javascript
{
  _id: "S08",
  totalCount: 2,
  distinctCount: 1
}
~~~

**$setUnion** dùng ngữ nghĩa tập hợp để loại phần tử trùng; nó không đảm bảo thứ tự phần tử đầu ra và không đệ quy làm phẳng mọi mảng lồng nhau.

## 8. Kết hợp số phần tử với điều kiện giá trị

Kiểm tra mảng có **đúng hai phần tử và chứa chuỗi "mongo"**:

~~~javascript
db.students.find({
  groups: { $size: 2 },
  $and: [
    { groups: "mongo" }
  ]
})
~~~

Kết quả: **S01**. S08 có hai phần tử nhưng không có "mongo". S09 có một mảng con ["java", "mongo"] và "docker"; mảng con không phải một chuỗi "mongo" ở cấp ngoài.

Có thể viết gọn bằng cách gộp điều kiện trong cùng field:

~~~javascript
db.students.find({
  groups: {
    $size: 2,
    $in: ["mongo"]
  }
})
~~~

Nếu yêu cầu **đúng hai nhóm và chứa cả "java" và "mongo"**:

~~~javascript
db.students.find({
  groups: {
    $size: 2,
    $all: ["java", "mongo"]
  }
})
~~~

Kết quả: **S01**. **$all** yêu cầu các giá trị được liệt kê cùng xuất hiện; **$size** yêu cầu đúng hai phần tử. Hai ràng buộc bổ sung ý nghĩa cho nhau.

Nếu cần **ít nhất ba nhóm và có "java"**:

~~~javascript
db.students.find({
  groups: "java",
  $expr: {
    $gte: [
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      },
      3
    ]
  }
})
~~~

Kết quả: **S04 và S10**. Điều kiện groups: "java" kiểm tra giá trị phần tử, còn $expr kiểm tra số phần tử.

Với array các embedded document, nếu nhiều điều kiện phải cùng áp dụng trên **một item**, thường dùng **$elemMatch**. Tuy nhiên, $elemMatch chỉ kiểm tra điều kiện tồn tại phần tử phù hợp; nó không tự đếm có bao nhiêu phần tử đạt yêu cầu.

## 9. Đếm phần tử thỏa điều kiện bằng $filter + $size

Một yêu cầu nâng cao hơn là **“học viên có ít nhất hai điểm từ 80 trở lên”**. Câu này khác “scores có ít nhất hai phần tử”, vì chỉ những điểm đạt ngưỡng mới được tính.

Kết hợp ba thành phần:

1. **$filter** tạo mảng mới chỉ chứa phần tử thỏa điều kiện.
2. **$size expression** tính số phần tử trong mảng đã lọc.
3. **$expr** và toán tử so sánh như $gte xác định document phù hợp.

### 9.1. Tính số điểm từ 80 trở lên trong aggregation

~~~javascript
db.students.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      highScoreCount: {
        $size: {
          $filter: {
            input: {
              $cond: [
                { $isArray: "$scores" },
                "$scores",
                []
              ]
            },
            as: "score",
            cond: {
              $gte: ["$$score", 80]
            }
          }
        }
      }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Ý nghĩa:

- **input** là danh sách scores đã bảo đảm kiểu array.
- **as: "score"** đặt tên biến cho từng phần tử đang xét.
- **"$$score"** tham chiếu biến phần tử, khác **"$scores"** là tham chiếu field của toàn document.
- **cond** chọn giá trị score từ 80 trở lên.
- **$size** đếm danh sách sau lọc.

Ví dụ:

| ID | scores | Điểm đạt ít nhất 80 | highScoreCount |
|---|---|---|---:|
| S01 | [80,90,75] | [80,90] | 2 |
| S02 | [60] | [] | 0 |
| S03 | [100,65] | [100] | 1 |
| S04 | [] | [] | 0 |
| S08 | [80,80] | [80,80] | 2 |
| S09 | [95,70,85,55] | [95,85] | 2 |
| S10 | [88,92,77,91,66] | [88,92,91] | 3 |

S05/S06/S07 nhận highScoreCount bằng 0 theo quy ước dùng [] khi field không phải array. Nếu thực tế những document này cần được sửa dữ liệu, hãy xử lý như lỗi dữ liệu thay vì mặc nhiên cho là không có điểm.

### 9.2. Chỉ tìm học viên có ít nhất hai điểm từ 80

~~~javascript
db.students.find({
  $expr: {
    $gte: [
      {
        $size: {
          $filter: {
            input: {
              $cond: [
                { $isArray: "$scores" },
                "$scores",
                []
              ]
            },
            as: "score",
            cond: { $gte: ["$$score", 80] }
          }
        }
      },
      2
    ]
  }
}).sort({ _id: 1 })
~~~

Kết quả: **S01, S08, S09, S10**.

Ở đây **$gte bên trong $filter** so sánh từng điểm với 80; **$gte bên ngoài** so sánh số điểm đạt với 2. Tuy cùng tên, hai toán tử đang kiểm tra hai đại lượng khác nhau.

### 9.3. Vì sao $elemMatch không thay thế được phép đếm?

~~~javascript
db.students.find({
  scores: {
    $elemMatch: { $gte: 80 }
  }
})
~~~

Filter này chỉ yêu cầu **tồn tại ít nhất một phần tử** có điểm từ 80 trở lên. Ví dụ S03 có một điểm 100 nên khớp $elemMatch, nhưng **không** thỏa điều kiện “ít nhất hai điểm từ 80”.

Với câu hỏi “bao nhiêu phần tử thỏa điều kiện”, cần **đếm**, không chỉ kiểm tra tồn tại.

### 9.4. Đếm embedded document thỏa nhiều điều kiện

Giả sử document đơn hàng:

~~~javascript
{
  _id: "ORD-001",
  items: [
    { sku: "PEN", quantity: 2, status: "ACTIVE" },
    { sku: "BOOK", quantity: 1, status: "CANCELLED" },
    { sku: "USB", quantity: 5, status: "ACTIVE" }
  ]
}
~~~

Đếm item có đồng thời **status = ACTIVE** và **quantity >= 2**:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      eligibleItemCount: {
        $size: {
          $filter: {
            input: {
              $cond: [
                { $isArray: "$items" },
                "$items",
                []
              ]
            },
            as: "item",
            cond: {
              $and: [
                { $eq: ["$$item.status", "ACTIVE"] },
                { $gte: ["$$item.quantity", 2] }
              ]
            }
          }
        }
      }
    }
  }
])
~~~

Kết quả của document mẫu là **eligibleItemCount = 2** vì PEN và USB thỏa cả hai điều kiện. BOOK không được tính. Nếu mảng items có phần tử sai schema hoặc quantity là String, ứng dụng nên chuẩn hóa hoặc kiểm tra kiểu trước khi sử dụng biểu thức nghiệp vụ.

## 10. So sánh độ dài hai mảng trong một document

Giả sử mỗi học viên có **groups** và **scores**. Muốn tìm document có **số nhóm lớn hơn số điểm**, kích thước cần so sánh sẽ thay đổi theo từng document; không thể biểu diễn chỉ bằng query $size với N cố định.

~~~javascript
db.students.find({
  $expr: {
    $gt: [
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      },
      {
        $size: {
          $cond: [
            { $isArray: "$scores" },
            "$scores",
            []
          ]
        }
      }
    ]
  }
}).sort({ _id: 1 })
~~~

Kết quả: **S04** vì groups có 3 phần tử và scores có 0. Các document còn lại có groupCount không lớn hơn scoreCount. Biểu thức coi những field không phải array là [] theo chính sách đã chọn.

Nếu yêu cầu chỉ chọn document **có đủ cả hai trường dạng array**, thêm điều kiện:

~~~javascript
db.students.find({
  $expr: {
    $and: [
      { $isArray: "$groups" },
      { $isArray: "$scores" },
      {
        $gt: [
          {
            $size: {
              $cond: [{ $isArray: "$groups" }, "$groups", []]
            }
          },
          {
            $size: {
              $cond: [{ $isArray: "$scores" }, "$scores", []]
            }
          }
        ]
      }
    ]
  }
})
~~~

Ta vẫn bảo vệ từng $size để biểu thức không phụ thuộc vào giả định các nhánh điều kiện luôn được tính tuần tự từ trái sang phải.

## 11. Aggregation pipeline: tính trước rồi lọc

Thay vì viết tất cả bên trong find/$expr, có thể dùng **$set** tính một trường trung gian rồi **$match** trên trường đã tính:

~~~javascript
db.students.aggregate([
  {
    $set: {
      computedGroupCount: {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      }
    }
  },
  {
    $match: {
      computedGroupCount: { $gte: 2 }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      computedGroupCount: 1
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Kết quả là **S01, S04, S08, S09, S10**, đồng thời có **computedGroupCount** để ứng dụng hiển thị.

Lưu ý: **$set ở đây là stage của aggregation pipeline đọc**. Nó tạo field trong tài liệu đang đi qua pipeline, không tự cập nhật document trong collection. Muốn ghi kết quả vào database phải có thao tác update hoặc cơ chế ghi kết quả riêng.

Ưu điểm của pipeline là chia thành các bước rõ:

~~~text
Document đầu vào
    |
    v
$set computedGroupCount = độ dài groups
    |
    v
$match computedGroupCount >= 2
    |
    v
$project fields cần xuất
~~~

Đây cũng là cách thuận tiện khi cần tính nhiều thống kê khác từ array, chẳng hạn totalCount, highScoreCount, distinctCount rồi so sánh hoặc sắp xếp.

## 12. Hiểu giới hạn index của $size

**Query operator $size không được index trực tiếp hỗ trợ để xác định những document có array đúng N phần tử.** Index multikey trên một array chủ yếu lưu các giá trị phần tử, không lưu trực tiếp số lượng phần tử thành khóa truy vấn tương ứng.

Ví dụ:

~~~javascript
db.students.createIndex({ groups: 1 })

db.students.find({
  groups: { $size: 2 }
}).explain("executionStats")
~~~

Index trên groups không bảo đảm MongoDB có thể tìm tất cả document có độ dài bằng 2 mà không cần kiểm tra document ứng viên. Tương tự, biểu thức **$expr + $size** tính độ dài từ giá trị document, không tự trở thành truy vấn range có index trên số lượng.

### 12.1. Kết hợp với điều kiện chọn lọc khác

Nếu collection có field **department**, có thể tạo index:

~~~javascript
db.students.createIndex({ department: 1 })

db.students.find({
  department: "engineering",
  groups: { $size: 2 }
})
~~~

Điều kiện department có khả năng thu hẹp tập document cần kiểm tra. Phần $size vẫn cần được đánh giá. Hiệu quả thực tế tùy phân bố dữ liệu, độ chọn lọc và query planner.

### 12.2. Sử dụng explain() để quan sát

~~~javascript
db.students.find({
  groups: { $size: 2 }
}).explain("executionStats")
~~~

Những mục nên quan sát:

| Trường | Ý nghĩa |
|---|---|
| winningPlan | Kế hoạch thực thi được chọn |
| totalKeysExamined | Số entry index đã duyệt |
| totalDocsExamined | Số document cần đọc/kiểm tra |
| nReturned | Số document trả về |

Trên collection chỉ có 10 document, collection scan có thể hoàn toàn hợp lý. Nên đo trên dữ liệu gần với workload thực tế trước khi quyết định một cách tối ưu.

## 13. Lưu trường đếm dẫn xuất khi truy vấn kích thước thường xuyên

Nếu ứng dụng có hàng triệu document và thường xuyên lọc “ít nhất năm nhóm”, một cách tối ưu là **lưu groupCount** cùng với groups:

~~~javascript
{
  _id: "S11",
  name: "Quân",
  groups: ["java", "mongo", "docker"],
  groupCount: 3
}
~~~

Khi đó có thể dùng truy vấn số thông thường:

~~~javascript
db.students.createIndex({ groupCount: 1 })

db.students.find({
  groupCount: { $gte: 3 }
})
~~~

Nếu thường lọc theo khoa và số nhóm, có thể cân nhắc compound index:

~~~javascript
db.students.createIndex({
  department: 1,
  groupCount: 1
})

db.students.find({
  department: "engineering",
  groupCount: { $gte: 3 }
})
~~~

Index và thứ tự trường cần dựa trên truy vấn thực tế, dữ liệu phân bố thế nào và yêu cầu sắp xếp; không phải mọi hệ thống đều cần một index mới cho groupCount.

### 13.1. Rủi ro dữ liệu dẫn xuất bị lệch

**groupCount phải bằng độ dài thực của groups**. Nếu ứng dụng nối thêm hoặc xóa phần tử nhưng quên cập nhật bộ đếm, truy vấn theo groupCount sẽ cho kết quả sai.

Ví dụ rủi ro:

~~~javascript
// Nếu chỉ thay mảng mà không cập nhật groupCount,
// document có thể trở nên không nhất quán.
db.students.updateOne(
  { _id: "S11" },
  { $push: { groups: "redis" } }
)
~~~

Sau thao tác trên, groups đã dài 4, nhưng groupCount có thể vẫn là 3. MongoDB không tự biết groupCount là trường dẫn xuất và không tự đồng bộ hai trường nếu ứng dụng không thiết kế cơ chế cập nhật.

### 13.2. Cập nhật mảng và tính lại độ dài trong một update pipeline

Một ví dụ nối thêm "redis" vào groups rồi tính lại groupCount:

~~~javascript
db.students.updateOne(
  {
    _id: "S01",
    groups: { $type: "array" }
  },
  [
    {
      $set: {
        groups: {
          $concatArrays: ["$groups", ["redis"]]
        }
      }
    },
    {
      $set: {
        groupCount: { $size: "$groups" }
      }
    }
  ]
)
~~~

Trong **aggregation pipeline update**, các stage thực thi theo thứ tự. Stage thứ nhất thay đổi groups; stage thứ hai đếm giá trị groups đã được cập nhật. Với dữ liệu ban đầu của S01, groups có 3 phần tử sau thao tác và groupCount cũng bằng 3.

Một document được cập nhật nguyên tử theo một lệnh update, nhưng ứng dụng vẫn cần xử lý quy tắc thêm không trùng, xóa, thay thế và các thao tác đồng thời. Lệnh ví dụ chỉ nối thêm phần tử, nên chạy lại có thể thêm "redis" lần nữa. Nếu cần semantics **set** không chứa phần tử trùng, hãy dùng cơ chế phù hợp và tính lại count theo trạng thái array thực, không tăng bộ đếm một cách mù quáng.

### 13.3. Phát hiện groupCount không khớp

Khi đã có một trường đếm, có thể so sánh nó với $size thực:

~~~javascript
db.students.find({
  $expr: {
    $ne: [
      "$groupCount",
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      }
    ]
  }
})
~~~

Nếu collection chứa document cũ chưa có groupCount, biểu thức cũng có thể chọn các document chưa backfill. Cần xác định chính sách migration trước khi coi tất cả kết quả là lỗi logic. Với dữ liệu sai kiểu, có thể cần sửa schema thay vì tự coi field String là array rỗng.

**Tóm lại**, trường đếm dẫn xuất giúp đánh đổi thêm chi phí duy trì dữ liệu để lấy khả năng lọc theo index. Đây là một lựa chọn thiết kế, không phải thay thế bắt buộc cho $size.

## 14. Bảo vệ mảng bằng schema validation

Khi nhóm kỹ năng được thiết kế luôn là array, nên kiểm soát từ lớp ghi để tránh các trường hợp groups: null hoặc groups: "mongo". MongoDB hỗ trợ validator sử dụng **$jsonSchema** và **bsonType**.

Ví dụ tạo collection mới:

~~~javascript
db.createCollection("validatedStudents", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "groups"],
      properties: {
        name: {
          bsonType: "string",
          minLength: 1
        },
        groups: {
          bsonType: "array",
          items: {
            bsonType: "string"
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Collection này yêu cầu groups là **BSON Array** và các phần tử là String. Nó cho phép [] nhưng không cho phép null, String hoặc array chứa array con. Muốn yêu cầu có ít nhất một phần tử, thêm **minItems: 1**; muốn giới hạn năm phần tử, thêm **maxItems: 5**:

~~~javascript
groups: {
  bsonType: "array",
  minItems: 1,
  maxItems: 5,
  items: { bsonType: "string" }
}
~~~

Hãy phân biệt:

| Cơ chế | Câu hỏi mà nó trả lời |
|---|---|
| $size query operator | Khi đọc: field đang có đúng N phần tử không? |
| $size aggregation expression | Khi tính toán: field có bao nhiêu phần tử? |
| $jsonSchema minItems/maxItems | Khi ghi: số phần tử có nằm trong giới hạn được phép không? |
| bsonType: "array" | Khi ghi: field có đúng kiểu Array không? |
| Trường đếm groupCount + index | Khi đọc nhiều lần: có thể tìm theo số phần tử qua index không? |

Thêm validator vào collection đã có dữ liệu không tự chuyển document String/null sang array. Cần kế hoạch làm sạch dữ liệu, cập nhật nguồn ghi và thay đổi validator phù hợp.

## 15. Java MongoDB Sync Driver: truy vấn $size

Trong ứng dụng Java có dependency **mongodb-driver-sync** tương thích, MongoDB Driver cung cấp **Filters.size()** để tạo filter kiểm tra độ dài chính xác.

### 15.1. Tìm học viên có đúng hai nhóm

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

public class FindStudentsWithTwoGroups {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Bson filter = Filters.size("groups", 2);

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> students = client
                    .getDatabase("array_size_lab")
                    .getCollection("students");

            for (Document student : students.find(filter)
                    .sort(new Document("_id", 1))) {
                System.out.println(student.toJson());
            }
        }
    }
}
~~~

**Filters.size("groups", 2)** tương đương:

~~~javascript
{ groups: { $size: 2 } }
~~~

Với dữ liệu chưa cập nhật của phần 2, kết quả là **S01, S08, S09**.

### 15.2. Truy vấn nhiều hơn hai nhóm bằng $expr trong Java

Có thể xây dựng bộ lọc MongoDB dưới dạng các **Document** lồng nhau. Ví dụ:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.Collections;

public class FindStudentsWithManyGroups {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Bson arrayOrEmpty = new Document(
                "$cond",
                Arrays.asList(
                        new Document("$isArray", "$groups"),
                        "$groups",
                        Collections.emptyList()
                )
        );

        Bson lengthExpr = new Document("$size", arrayOrEmpty);

        Bson filter = new Document(
                "$expr",
                new Document("$gt", Arrays.asList(lengthExpr, 2))
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> students = client
                    .getDatabase("array_size_lab")
                    .getCollection("students");

            for (Document student : students.find(filter)
                    .sort(new Document("_id", 1))) {
                System.out.println(student.getString("_id"));
            }
        }
    }
}
~~~

Cấu trúc Java tương ứng với:

~~~javascript
{
  $expr: {
    $gt: [
      {
        $size: {
          $cond: [
            { $isArray: "$groups" },
            "$groups",
            []
          ]
        }
      },
      2
    ]
  }
}
~~~

Đoạn Java minh họa cách dựng BSON filter. Trong code production, nên đặt tên biểu thức và tái sử dụng một cách có chủ đích, thay vì lặp lại nhiều cây Document quá dài ở các repository method.

### 15.3. Vì sao cần validate tham số kích thước?

Giả sử một API nhận **groupCount** từ query parameter:

~~~text
GET /students?groupCount=2
~~~

HTTP truyền giá trị dưới dạng chuỗi; trước khi dùng Filters.size(), ứng dụng phải parse thành số nguyên và đảm bảo **groupCount >= 0**:

~~~java
if (groupCount < 0) {
    throw new IllegalArgumentException(
            "groupCount must be non-negative"
    );
}

Bson filter = Filters.size("groups", groupCount);
~~~

Giá trị N quá lớn hoặc không hợp lệ cũng cần được xử lý theo quy tắc API. Không đưa thẳng một chuỗi **"2"** vào toán tử $size rồi mong database tự hiểu thành số lượng.

## 16. Spring Data MongoDB: Criteria.size()

Trong Spring Data MongoDB, **Criteria.where("groups").size(2)** tạo điều kiện $size query operator.

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class StudentQueryService {
    private final MongoTemplate mongoTemplate;

    public StudentQueryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> findExactlyTwoGroups() {
        Query query = new Query(
                Criteria.where("groups").size(2)
        );

        return mongoTemplate.find(
                query,
                Document.class,
                "students"
        );
    }
}
~~~

Ví dụ giả định MongoTemplate đã trỏ đến database **array_size_lab** và document được ánh xạ theo cấu hình ứng dụng. Kết quả filter vẫn là những document groups có đúng hai phần tử.

**Đừng dùng**:

~~~java
// Không có nghĩa groups có độ dài lớn hơn 2.
Criteria.where("groups").size(2).gt(2);
~~~

size(2) tạo query operator $size cho độ dài **đúng 2**; gt(2) không tự nhận kết quả của size() làm toán hạng. Với “nhiều hơn 2”, hãy dùng biểu thức $expr như ví dụ MongoDB Sync Driver hoặc các API aggregation tương ứng với phiên bản Spring Data MongoDB đang dùng.

## 17. Đếm số lượng sản phẩm khác tổng số đơn vị

Với document:

~~~javascript
{
  _id: "ORDER-100",
  items: [
    { sku: "PEN", quantity: 2 },
    { sku: "BOOK", quantity: 4 }
  ]
}
~~~

**$size của items = 2** vì có hai line item. Nhưng tổng quantity = **6**. Nếu muốn tính tổng số đơn vị, có thể kết hợp **$map** và **$sum**:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ORDER-100" } },
  {
    $project: {
      _id: 1,
      lineCount: { $size: "$items" },
      unitCount: {
        $sum: {
          $map: {
            input: "$items",
            as: "item",
            in: "$$item.quantity"
          }
        }
      }
    }
  }
])
~~~

Đối với document hợp lệ ví dụ, kết quả:

~~~javascript
{
  _id: "ORDER-100",
  lineCount: 2,
  unitCount: 6
}
~~~

Biểu thức trên yêu cầu items là array các object, quantity có kiểu số phù hợp. Với dữ liệu không đồng nhất, cần thêm bước kiểm tra hoặc chuẩn hóa kiểu để tránh sai lệch khi tổng hợp.

## 18. Các lỗi thường gặp và cách giải quyết

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| $size: 0 không trả document có groups: null | Null không phải array rỗng | Dùng điều kiện null/missing nếu nghiệp vụ cho phép |
| $size: 2 trả array ["java", "java"] | $size đếm phần tử, không đếm giá trị phân biệt | Dùng $setUnion + $size khi cần distinctCount |
| $size: 2 trả một array chứa array con | Array con tính là một phần tử cấp ngoài | Xác định cấp cần đếm hoặc dùng biểu thức duyệt sâu hơn |
| $size: { $gt: 2 } báo lỗi | Query $size chỉ nhận kích thước chính xác | Dùng $expr và aggregation $size |
| $size expression lỗi khi field null | Aggregation $size cần đối số là array | Bọc bằng $ifNull hoặc $cond + $isArray |
| $ifNull vẫn lỗi khi field là String | $ifNull chỉ thay null/missing | Kiểm tra kiểu bằng $isArray |
| $elemMatch chọn cả document chỉ có một điểm đạt | $elemMatch kiểm tra sự tồn tại, không đếm số phần tử phù hợp | Dùng $filter + $size |
| Dùng $gt cạnh query $size không ra kết quả mong muốn | $gt không tự so sánh kết quả đếm | Đặt phép so sánh trong $expr |
| Thêm index trên groups nhưng vẫn quét nhiều document | Index multikey không trực tiếp index độ dài array | Kết hợp điều kiện chọn lọc, hoặc thêm trường đếm có index |
| groupCount lệch groups | Có cập nhật mảng nhưng không đồng bộ bộ đếm | Dùng cập nhật nguyên tử và quy trình kiểm tra/migration |
| Array hai item nhưng cần tính sáu đơn vị hàng | $size đếm dòng items, không cộng quantity | Dùng phép tổng hợp số lượng |
| Truy vấn trả cùng tập kết quả nhưng khác thứ tự | Không có sort() | Sắp xếp theo khóa nghiệp vụ |

### 18.1. Phân biệt cú pháp filter và aggregation expression

Cùng một chữ **$size**, nhưng không thể dùng thay nhau:

~~~javascript
// Filter: groups có đúng 2 phần tử.
db.students.find({
  groups: { $size: 2 }
})

// Aggregation: xuất ra số phần tử.
db.students.aggregate([
  { $match: { groups: { $type: "array" } } },
  {
    $project: {
      groupCount: { $size: "$groups" }
    }
  }
])

// Filter kết hợp biểu thức: groups có hơn 2 phần tử.
db.students.find({
  $expr: {
    $gt: [
      {
        $size: {
          $cond: [{ $isArray: "$groups" }, "$groups", []]
        }
      },
      2
    ]
  }
})
~~~

Đừng kết luận rằng mọi vị trí có thể viết **$size** đều cho cùng một kết quả hoặc cùng một cách xử lý giá trị không phải array.

### 18.2. Đừng dùng phép so sánh array để suy ra độ dài

Ví dụ:

~~~javascript
db.students.find({
  groups: { $gt: 2 }
})
~~~

Đây **không phải** filter “groups có nhiều hơn hai phần tử”. $gt là toán tử so sánh giá trị theo ngữ nghĩa của truy vấn MongoDB; khi field là array có thể phát sinh ngữ nghĩa khớp phần tử. Muốn so sánh độ dài, cần tính **$size của array** trước.

### 18.3. Kiểm tra trường dữ liệu sai kiểu

Một collection có thể xuất hiện đồng thời:

~~~javascript
{ groups: [] }
{ groups: "java" }
{ groups: null }
~~~

Hãy tìm những record sai schema:

~~~javascript
db.students.find({
  $expr: {
    $not: [
      { $isArray: "$groups" }
    ]
  }
})
~~~

Với dữ liệu mẫu, các record không có groups là array gồm **S05, S06, S07**. Việc nên chuyển chúng thành [] hay sửa theo nguồn dữ liệu gốc tùy nghiệp vụ.

Một cách khác là dùng aggregation để hiển thị kiểu BSON:

~~~javascript
db.students.aggregate([
  {
    $project: {
      _id: 1,
      groupsType: { $type: "$groups" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Kết quả có thể hiển thị **array**, **null**, **missing**, **string**. Đây là dữ liệu hữu ích để quyết định cách xử lý trước khi thiết lập validator.

## 19. Bài tập thực hành

Các bài tập sau sử dụng collection **students** ban đầu, chưa chạy ví dụ update làm thay đổi groups của S01.

### Bài 1. Kiểm tra kích thước đúng bằng

Hãy viết truy vấn cho:

1. Học viên có **0 nhóm**.
2. Học viên có **2 nhóm**.
3. Học viên có **4 nhóm**.

Đáp án:

~~~javascript
// 0 nhóm
db.students.find({ groups: { $size: 0 } })

// 2 nhóm
db.students.find({ groups: { $size: 2 } })

// 4 nhóm
db.students.find({ groups: { $size: 4 } })
~~~

Các kết quả theo thứ tự là **S02**, **S01/S08/S09** và **S10**. Giải thích vì sao S08 có giá trị trùng, S09 có array con mà vẫn thỏa $size: 2.

### Bài 2. Chọn query operator hay expression

Yêu cầu:

- Đúng 3 nhóm.
- Nhiều hơn 3 nhóm.
- Ít nhất 3 nhóm.
- Tối đa 3 nhóm.

Hãy chọn cú pháp thích hợp cho từng yêu cầu. Gợi ý:

~~~javascript
// Đúng 3: query operator.
{ groups: { $size: 3 } }

// Nhiều hơn 3: biểu thức đặt bên trong $expr.
{
  $gt: [
    { $size: "$groups" },
    3
  ]
}
~~~

Biểu thức thứ hai chỉ an toàn khi groups chắc chắn là array. Với dữ liệu hỗn hợp, cần dùng **$cond + $isArray**. Những yêu cầu còn lại dùng **$gte** hoặc **$lte** trên kết quả $size expression theo đúng ngữ nghĩa biên.

### Bài 3. Phân biệt array rỗng và giá trị chưa xác định

Hãy xác định ID cho:

1. groups là array rỗng.
2. groups là null hoặc không tồn tại.
3. groups là String.
4. groups là array không rỗng.

Gợi ý:

~~~javascript
{ groups: { $size: 0 } }
{ groups: null }
{ groups: { $type: "string" } }
{
  $expr: {
    $gt: [
      {
        $size: {
          $cond: [{ $isArray: "$groups" }, "$groups", []]
        }
      },
      0
    ]
  }
}
~~~

Kết quả lần lượt: **S02**; **S05, S06**; **S07**; **S01, S03, S04, S08, S09, S10**.

### Bài 4. Đếm điểm cao

Hãy tìm học viên có **ít nhất hai giá trị scores >= 80**.

Đáp án:

~~~javascript
db.students.find({
  $expr: {
    $gte: [
      {
        $size: {
          $filter: {
            input: {
              $cond: [{ $isArray: "$scores" }, "$scores", []]
            },
            as: "score",
            cond: { $gte: ["$$score", 80] }
          }
        }
      },
      2
    ]
  }
})
~~~

Kết quả: **S01, S08, S09, S10**. Vì sao chỉ dùng $elemMatch với $gte: 80 lại không đủ? Vì nó chỉ cần **một** phần tử đạt ngưỡng.

### Bài 5. So sánh hai mảng trong một document

Viết filter để tìm học viên có **nhiều nhóm hơn điểm số đã ghi nhận**.

Gợi ý: dùng **$expr: { $gt: [...] }** với hai vế đều là biểu thức $size được bảo vệ bằng $isArray. Kết quả của dữ liệu ban đầu là **S04**.

### Bài 6. Độ dài mảng và số phần tử phân biệt

Đối với S08:

~~~javascript
{ groups: ["java", "java"] }
~~~

Hãy xác định:

- Số phần tử từ $size.
- Số phần tử từ $size sau khi sử dụng $setUnion.
- Tại sao hai con số khác nhau và trường hợp nghiệp vụ nào cần distinctCount.

Đáp án: **2** và **1**. Nếu danh sách nhóm phải không có trùng lặp, cần kiểm tra quy tắc thêm phần tử khi ghi thay vì chỉ sửa dữ liệu lúc truy vấn.

### Bài 7. Xem xét hiệu năng

Một collection chứa nhiều triệu học viên. API thường lọc theo khoa và yêu cầu ít nhất năm nhóm.

Hãy đề xuất:

1. Query dùng **department** và **$expr + $size** khi chưa đổi schema.
2. Query dùng **department** và trường đếm **groupCount >= 5**.
3. Index có thể phù hợp với truy vấn thứ hai.
4. Cách đảm bảo groupCount được cập nhật đồng thời khi groups thay đổi.

Định hướng: có thể cân nhắc index **{ department: 1, groupCount: 1 }**, nhưng cần đo với explain() và duy trì groupCount nhất quán để tránh đổi hiệu năng lấy kết quả sai.

### Bài 8. Số mục hàng so với tổng quantity

Xét:

~~~javascript
{
  orderCode: "O-200",
  items: [
    { sku: "A", quantity: 2 },
    { sku: "B", quantity: 4 },
    { sku: "C", quantity: 1 }
  ]
}
~~~

Trả lời: **$size của items bằng bao nhiêu? Tổng quantity bằng bao nhiêu?** Muốn tìm đơn hàng có hơn năm đơn vị sản phẩm, chỉ dùng $size có đúng không?

Đáp án: **3 mục hàng**, **7 đơn vị**; muốn so sánh tổng đơn vị cần tính theo quantity, không chỉ đếm số document con trong array.

## 20. Cách chọn công cụ theo yêu cầu

| Câu hỏi | Công cụ chính |
|---|---|
| Mảng có đúng N phần tử? | Query operator $size |
| Mảng có nhiều hơn/ít hơn N phần tử? | $expr + aggregation $size + toán tử so sánh |
| Mảng A dài hơn mảng B? | $expr với hai biểu thức $size |
| Có ít nhất K phần tử đạt điều kiện? | $filter + $size + $gte |
| Có bao nhiêu phần tử phân biệt? | $setUnion + $size |
| Chỉ muốn array thực sự, không nhận null/String? | $isArray, $type hoặc schema validation |
| Muốn ngăn ghi array quá dài? | $jsonSchema với maxItems |
| Cần lọc kích thước thường xuyên với index? | Trường đếm dẫn xuất được cập nhật nhất quán |

**Quy tắc dễ nhớ:** **$size trong filter** khớp **đúng số phần tử**; **$size trong aggregation expression** tạo ra **con số để tính toán hoặc so sánh**. Kết hợp chúng với kiểm tra kiểu và chính sách xử lý dữ liệu phù hợp sẽ giúp truy vấn array chính xác, tránh nhầm giữa array rỗng, null, missing và các giá trị sai kiểu, đồng thời hỗ trợ tối ưu hiệu năng khi hệ thống mở rộng.
