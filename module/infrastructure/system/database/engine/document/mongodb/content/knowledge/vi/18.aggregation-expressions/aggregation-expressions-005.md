# Xử lý chuỗi, biểu thức chính quy và giới hạn theo collation trong MongoDB Aggregation

## 1. Mục tiêu bài học

Một document MongoDB thường chứa nhiều loại chuỗi: tên khách hàng, mã đơn, địa chỉ email, ghi chú, nhãn phân loại và nội dung người dùng nhập tự do. Khi tạo báo cáo hoặc xây API, ứng dụng cần tách, ghép, cắt, tìm mẫu, chuẩn hóa hoặc kiểm tra những chuỗi này ngay trong **aggregation pipeline**.

Ví dụ:

- Biến chuỗi `"  Minh  "` thành `"Minh"`.
- Tách `"vip, new, priority"` thành mảng nhãn sạch.
- Tạo `displayName` từ nhiều field nhưng không để một giá trị `null` phá hỏng phép ghép.
- Trích mã `ORD-123` từ `"Mã ORD-123, INV-456"`.
- Kiểm tra xem tên có khớp mẫu `^lan$` không phân biệt chữ hoa/thường.
- Đếm và cắt chuỗi Unicode có dấu hoặc emoji mà không nhầm **byte** với **code point**.
- Biết vì sao collation `strength: 1` có thể coi `cafe` và `café` tương đương trong equality, trong khi `$regexMatch` không làm như vậy.
- Dùng collation-aware index cho phép so sánh bằng mà không kỳ vọng regex bỏ qua dấu tự động sử dụng được index ấy.

Bài thuộc chương **Biểu thức aggregation** của module **Database Engine Document MongoDB**, tập trung vào **xử lý chuỗi, biểu thức chính quy và giới hạn theo collation**.

Sau khi học, bạn sẽ phân biệt được:

1. Những biểu thức thao tác chuỗi như `$concat`, `$split`, `$trim`, `$substrCP`, `$replaceAll`.
2. Những biểu thức regular expression như `$regexMatch`, `$regexFind`, `$regexFindAll`.
3. So sánh chuỗi theo `collation`, ví dụ `$eq`, `$match`, `$sort`, `$group`, với các thao tác **không collation-aware**.
4. Kiểu dữ liệu đầu vào, giá trị missing/null, Unicode, lỗi cú pháp và chi phí thực thi.
5. Thiết kế pipeline tự chứa trong mongosh, sử dụng trên Compass và Java Driver.

**Nguyên tắc trung tâm:** collation không phải là một bộ chuyển đổi Unicode hoặc công tắc khiến mọi toán tử chuỗi trở thành không phân biệt hoa/thường và dấu. Mỗi nhóm expression có quy tắc riêng.

## 2. Aggregation expression nằm ở đâu?

Aggregation pipeline nhận các document từ collection rồi đưa chúng qua nhiều stage:

~~~text
customers collection
       |
       v
     $match             Chọn document cần xử lý
       |
       v
     $set               Thêm field đã tính toán
       |
       v
     $project           Chọn field đầu ra
       |
       v
     $sort              Sắp xếp theo quy tắc operation
       |
       v
    Kết quả
~~~

Một expression được dùng ở những vị trí như:

~~~javascript
db.customers.aggregate([
  {
    $set: {
      cleanName: {
        $trim: { input: "$name" }
      }
    }
  },
  {
    $project: {
      _id: 1,
      cleanName: 1
    }
  }
]);
~~~

Phân biệt ba ký hiệu:

| Cú pháp | Ý nghĩa |
|---|---|
| `"$name"` | Tham chiếu field `name` của document đang xử lý |
| `"$$part"` | Tham chiếu biến `part` được tạo trong expression như `$map` |
| `{ $literal: "$name" }` | Chuỗi dữ liệu nguyên văn `"$name"`, không đọc field |

Một lệnh `aggregate()` thông thường chỉ tạo **kết quả đọc**; `$set` trong pipeline không tự ghi dữ liệu mới vào collection. Khi dùng các stage tương tự trong update pipeline hoặc thêm stage ghi như `$merge`, ý nghĩa ghi dữ liệu sẽ khác.

## 3. Chuẩn bị database thực hành

Dùng một MongoDB Server/cluster bạn có quyền truy cập và mở `mongosh`. Chỉ thực hiện lệnh ghi trên database thực hành:

~~~javascript
use aggregation_string_lab
~~~

Nạp 11 document để kiểm tra chữ hoa/thường, dấu, emoji, field thiếu, null và ghi chú có mã:

~~~javascript
const sampleCustomers = [
  {
    _id: 1, tenantId: "tenant-A",
    name: "Lan", code: "AB-001",
    email: "lan@example.test",
    note: "Mã ORD-123, INV-456",
    rawTags: "vip, new"
  },
  {
    _id: 2, tenantId: "tenant-A",
    name: "lan", code: "ab-002",
    email: "LAN@example.test",
    note: "ORD-789",
    rawTags: " new ,vip "
  },
  {
    _id: 3, tenantId: "tenant-A",
    name: "LAN", code: "AB-003",
    email: "lan.alt@example.test",
    note: "Không có mã",
    rawTags: ""
  },
  {
    _id: 4, tenantId: "tenant-A",
    name: "cafe", code: "CA-010",
    email: "cafe@example.test",
    note: "Mã ORD-123, INV-456",
    rawTags: "food, sale"
  },
  {
    _id: 5, tenantId: "tenant-A",
    name: "café", code: "CA-011",
    email: "cafe.plus@example.test",
    note: "Mã ORD-456",
    rawTags: "food"
  },
  {
    _id: 6, tenantId: "tenant-A",
    name: "Ánh", code: "VN-100",
    email: "anh.accent@example.test",
    note: "Chào khách",
    rawTags: "vip"
  },
  {
    _id: 7, tenantId: "tenant-A",
    name: "Anh", code: "VN-101",
    email: "Anh@Example.Test",
    note: "Đã giao",
    rawTags: ""
  },
  {
    _id: 8, tenantId: "tenant-A",
    name: "  Minh  ", code: "VN-102",
    email: "minh@example.test",
    note: "REF: ABC-123-XYZ",
    rawTags: " new , vip ,, "
  },
  {
    _id: 9, tenantId: "tenant-B",
    name: "🎉Lan", code: "EM-103",
    email: "emoji@example.test",
    note: "Chào 🎉 bạn",
    rawTags: "event"
  },
  {
    _id: 10, tenantId: "tenant-A",
    name: "Mai", code: "VN-104",
    email: null,
    rawTags: null
    // Cố ý không có field note
  },
  {
    _id: 11, tenantId: "tenant-B",
    name: "lan-anh", code: "AB-004",
    email: "lan-anh@example.test",
    note: "ORD-001, ORD-002",
    rawTags: "special"
  }
];

sampleCustomers.forEach(customer => {
  db.customers.replaceOne(
    { _id: customer._id },
    customer,
    { upsert: true }
  );
});

db.customers.countDocuments({});
~~~

Với collection ban đầu rỗng, lệnh cuối trả **11**. `replaceOne(..., {upsert:true})` cho phép nạp lại theo `_id`, nhưng cũng **đặt lại** 11 document mẫu nếu chúng đã bị sửa. Nó không xóa document khác đã được chèn vào collection.

Xem nhanh:

~~~javascript
db.customers.find(
  {},
  { _id: 1, name: 1, code: 1, rawTags: 1 }
).sort({ _id: 1 });
~~~

Các nhóm có dụng ý:

- ID 1, 2, 3: `Lan`, `lan`, `LAN`.
- ID 4, 5: `cafe` và `café`.
- ID 6, 7: tên có dấu và không dấu trong tiếng Việt.
- ID 8: khoảng trắng đầu/cuối, nhãn có khoảng trắng thừa.
- ID 9: emoji `🎉` chiếm nhiều byte UTF-8.
- ID 10: `email: null`, `rawTags: null` và **thiếu** `note`.
- ID 11: tên bắt đầu bằng `lan` nhưng không bằng chính xác `lan`.

Khi so sánh kết quả ID bên dưới, giả định collection chỉ chứa dữ liệu mẫu và không có thay đổi đồng thời.

## 4. $concat: ghép chuỗi

### 4.1. Cú pháp

`$concat` ghép các biểu thức chuỗi theo thứ tự:

~~~javascript
{
  $concat: [
    <string-expression-1>,
    <string-expression-2>,
    ...
  ]
}
~~~

Ví dụ ghép ID với tên:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      label: {
        $concat: [
          "Khách: ",
          "$name"
        ]
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  label: "Khách: Lan"
}
~~~

Các giá trị phải phù hợp kiểu chuỗi. Khi cần ghép số hoặc ObjectId, hãy chuyển kiểu trước theo hợp đồng dữ liệu.

### 4.2. Một toán hạng null/missing ảnh hưởng cả phép ghép

Thử:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 10 } },
  {
    $project: {
      label: {
        $concat: [
          "$name",
          " <",
          "$email",
          ">"
        ]
      }
    }
  }
]);
~~~

Vì ID 10 có `email: null`, `$concat` trả `null` cho `label`. Nó không tự bỏ qua phần tử null.

Giải pháp dùng `$ifNull`:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 10 } },
  {
    $project: {
      label: {
        $concat: [
          "$name",
          " <",
          { $ifNull: ["$email", "chua-co-email"] },
          ">"
        ]
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  _id: 10,
  label: "Mai <chua-co-email>"
}
~~~

`$ifNull` xử lý null và missing; nó không tự biến giá trị thuộc kiểu BSON không phải string thành string.

### 4.3. Chuyển kiểu với $toString

Với field dạng số, có thể dùng:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      label: {
        $concat: [
          "ID=",
          { $toString: "$_id" },
          " - ",
          "$name"
        ]
      }
    }
  }
]);
~~~

Kết quả `"ID=1 - Lan"`.

`$toString` có quy tắc chuyển đổi BSON và có thể báo lỗi với loại dữ liệu không hỗ trợ. Trong pipeline cần chịu dữ liệu không đồng nhất, có thể dùng `$convert` với `onError`/`onNull` phù hợp.

## 5. $trim, $ltrim và $rtrim

Ba expression phục vụ việc loại ký tự không mong muốn ở **đầu/cuối chuỗi**:

| Expression | Tác dụng |
|---|---|
| `$trim` | Bỏ ở cả hai đầu |
| `$ltrim` | Bỏ phía trái/đầu |
| `$rtrim` | Bỏ phía phải/cuối |

### 5.1. Loại khoảng trắng hai đầu

~~~javascript
db.customers.aggregate([
  { $match: { _id: 8 } },
  {
    $project: {
      _id: 0,
      before: "$name",
      after: {
        $trim: { input: "$name" }
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  before: "  Minh  ",
  after: "Minh"
}
~~~

`$trim` không loại mọi khoảng trắng ở **giữa** chuỗi. Ví dụ `"Nguyễn   An"` vẫn có thể chứa nhiều dấu cách giữa hai từ sau khi trim.

### 5.2. Chọn chính xác các ký tự muốn bỏ

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      cleanedCode: {
        $trim: {
          input: "$code",
          chars: " -"
        }
      }
    }
  }
]);
~~~

`chars` là tập **ký tự** được phép cắt ở các đầu, không phải một chuỗi con phải khớp nguyên thứ tự. Với `chars: " -"`, các dấu cách và dấu gạch ngang liên tiếp ở đầu/cuối có thể bị loại.

Nếu ứng dụng cần xóa dấu gạch ngang **ở giữa** mã, `$trim` không phải lựa chọn đúng; hãy xem `$replaceAll` hoặc quy tắc khác.

### 5.3. Thiếu dữ liệu và kiểu dữ liệu

Nếu input null/missing, kết quả của nhóm trim có thể là null. Nếu input không phải chuỗi, expression có thể báo lỗi kiểu. Với dữ liệu API không tin cậy, dùng schema validation hoặc xử lý kiểu trước khi trim.

Một mẫu có fallback:

~~~javascript
{
  $trim: {
    input: {
      $ifNull: ["$name", ""]
    }
  }
}
~~~

Fallback về `""` là một quyết định nghiệp vụ; nó không đồng nghĩa rằng field thiếu và chuỗi rỗng luôn có ý nghĩa giống nhau.

## 6. $split: tách chuỗi thành mảng

`$split` cắt chuỗi theo một delimiter:

~~~javascript
{
  $split: [
    <input-string>,
    <delimiter-string>
  ]
}
~~~

Ví dụ trên ID 1:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      rawTags: 1,
      parts: {
        $split: ["$rawTags", ","]
      }
    }
  }
]);
~~~

Kết quả `parts` gần như:

~~~javascript
[
  "vip",
  " new"
]
~~~

Phần tử thứ hai vẫn có dấu cách đầu. `$split` chỉ **tách**, không tự trim từng phần.

### 6.1. Tách rồi làm sạch từng phần tử

Dùng `$map` và `$trim`:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 2 } },
  {
    $project: {
      _id: 0,
      tags: {
        $map: {
          input: {
            $split: [
              { $ifNull: ["$rawTags", ""] },
              ","
            ]
          },
          as: "tag",
          in: {
            $trim: { input: "$$tag" }
          }
        }
      }
    }
  }
]);
~~~

Kết quả ID 2:

~~~javascript
{
  tags: ["new", "vip"]
}
~~~

### 6.2. Loại phần tử rỗng với $filter

ID 8 có `rawTags: " new , vip ,, "`, nên sau `$split` và `$trim` sẽ có các phần tử rỗng. Có thể thêm `$filter`:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 8 } },
  {
    $project: {
      _id: 0,
      tags: {
        $filter: {
          input: {
            $map: {
              input: {
                $split: [
                  { $ifNull: ["$rawTags", ""] },
                  ","
                ]
              },
              as: "tag",
              in: {
                $trim: { input: "$$tag" }
              }
            }
          },
          as: "tag",
          cond: { $ne: ["$$tag", ""] }
        }
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  tags: ["new", "vip"]
}
~~~

Cũng có thể áp dụng cho ID 10 có `rawTags: null`: fallback thành `""`, `$split` cho phần tử rỗng, sau `$filter` mảng cuối cùng là `[]`.

### 6.3. Delimiter là chuỗi cụ thể

`$split` không nhận regex như delimiter. Ví dụ `","` chỉ tách ở dấu phẩy. Nếu input dùng nhiều delimiter khác nhau, bạn có thể chuẩn hóa trước bằng `$replaceAll`, kết hợp nhiều bước, hoặc dùng chiến lược xử lý ngoài database.

Đầu vào và delimiter phải đúng kiểu chuỗi. Nếu delimiter không xuất hiện trong input, kết quả thường là mảng một phần tử chứa nguyên input.

## 7. $strLenBytes và $strLenCP: chuỗi Unicode dài bao nhiêu?

Với chuỗi ASCII, độ dài UTF-8 theo byte và số code point thường bằng nhau. Với tiếng Việt, emoji và ký tự đa byte, chúng có thể khác đáng kể.

Hai expression:

- `$strLenBytes`: đếm **byte UTF-8**.
- `$strLenCP`: đếm **Unicode code point**.

### 7.1. Ví dụ cafe và café

~~~javascript
db.customers.aggregate([
  { $match: { _id: 5 } },
  {
    $project: {
      _id: 0,
      name: 1,
      bytes: { $strLenBytes: "$name" },
      codePoints: { $strLenCP: "$name" }
    }
  }
]);
~~~

Với chuỗi `"café"` chứa ký tự `é` dạng một code point precomposed:

~~~javascript
{
  name: "café",
  bytes: 5,
  codePoints: 4
}
~~~

Ba chữ `c`, `a`, `f` mỗi chữ chiếm một byte; `é` thường chiếm hai byte trong UTF-8. Số code point là bốn.

### 7.2. Emoji

~~~javascript
db.customers.aggregate([
  { $match: { _id: 9 } },
  {
    $project: {
      _id: 0,
      name: 1,
      bytes: { $strLenBytes: "$name" },
      codePoints: { $strLenCP: "$name" }
    }
  }
]);
~~~

Với `"🎉Lan"`:

~~~javascript
{
  name: "🎉Lan",
  bytes: 7,
  codePoints: 4
}
~~~

Emoji `🎉` chiếm 4 byte UTF-8 nhưng một code point. Các chuỗi emoji phức tạp có thể gồm **nhiều code point nhưng chỉ một grapheme cluster** hiển thị. Vì vậy:

> `$strLenCP` đo code point, không nhất thiết đo số ký tự người dùng nhìn thấy (*grapheme clusters*).

Điều này rất quan trọng khi bạn cần giới hạn chiều dài tên theo giao diện người dùng. Với Unicode phức tạp, đếm code point vẫn có thể khác số ký tự trực quan.

### 7.3. Chuỗi giống nhau khi hiển thị chưa chắc có cùng code points

Unicode có thể biểu diễn một chữ có dấu theo dạng precomposed hoặc base character + combining mark. Hai chuỗi trông giống nhau có thể có số code point và byte khác nhau.

`$strLenCP` không tự chuẩn hóa tất cả chuỗi theo cùng một dạng Unicode. Nếu ứng dụng cần quy tắc độ dài nghiêm ngặt, nên thiết kế chính sách normalization và validation nhất quán ở ranh giới nhập liệu.

## 8. $substrBytes và $substrCP: cắt chuỗi đúng đơn vị

### 8.1. Cú pháp

~~~javascript
{
  $substrBytes: [
    <string>,
    <start-byte>,
    <byte-count>
  ]
}
~~~

~~~javascript
{
  $substrCP: [
    <string>,
    <start-codepoint>,
    <codepoint-count>
  ]
}
~~~

Hai expression giống hình thức nhưng khác đơn vị vị trí và độ dài.

### 8.2. Cắt chuỗi ASCII

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      prefix: {
        $substrCP: ["$code", 0, 2]
      }
    }
  }
]);
~~~

Với `code: "AB-001"`, kết quả `prefix: "AB"`. Khi chuỗi thuần ASCII, `$substrBytes` với cùng chỉ số thường cho kết quả tương đương.

### 8.3. Cắt tên có emoji

~~~javascript
db.customers.aggregate([
  { $match: { _id: 9 } },
  {
    $project: {
      _id: 0,
      firstCodePoint: {
        $substrCP: ["$name", 0, 1]
      },
      firstFourBytes: {
        $substrBytes: ["$name", 0, 4]
      }
    }
  }
]);
~~~

Cả hai đều có thể cho `"🎉"` trên chuỗi `"🎉Lan"`, nhưng chỉ số biểu diễn khác nhau:

- `$substrCP` đếm 1 code point.
- `$substrBytes` cần 4 byte để chứa emoji đó.

Không dùng `$substrBytes: ["$name",0,1]` rồi mong lấy nguyên emoji: việc cắt vào giữa một ký tự UTF-8 đa byte không hợp lệ và có thể khiến MongoDB trả lỗi.

### 8.4. Chọn Bytes hay CP?

| Nhu cầu | Nên cân nhắc |
|---|---|
| Xử lý định dạng giao thức có offset theo byte UTF-8 | `$substrBytes` |
| Lấy một số code point Unicode | `$substrCP` |
| Hiển thị “n ký tự đầu” theo cảm nhận người dùng | Cần hiểu grapheme clusters; `$substrCP` không giải quyết mọi emoji/combining mark |
| Mã SKU hoàn toàn ASCII | Cả hai có thể tương đương về kết quả, nhưng cần quy định kiểu dữ liệu |
| Không biết input có Unicode hay không | Tránh suy đoán offset byte từ số code point |

## 9. $indexOfBytes và $indexOfCP: tìm vị trí chuỗi con

Hai expression tìm vị trí xuất hiện đầu tiên của chuỗi con:

~~~javascript
{
  $indexOfBytes: [
    <string>,
    <substring>
  ]
}
~~~

~~~javascript
{
  $indexOfCP: [
    <string>,
    <substring>
  ]
}
~~~

Ngoài hai đối số đầu, các expression còn hỗ trợ chỉ định vị trí bắt đầu/kết thúc khi cần. Giá trị trả về dùng đơn vị byte hoặc code point tương ứng; trả **-1** khi không tìm thấy chuỗi con trong phạm vi tìm kiếm.

### 9.1. So sánh offset trên emoji

~~~javascript
db.customers.aggregate([
  { $match: { _id: 9 } },
  {
    $project: {
      _id: 0,
      name: 1,
      byteIndex: {
        $indexOfBytes: ["$name", "Lan"]
      },
      codePointIndex: {
        $indexOfCP: ["$name", "Lan"]
      }
    }
  }
]);
~~~

Với `"🎉Lan"`:

~~~javascript
{
  name: "🎉Lan",
  byteIndex: 4,
  codePointIndex: 1
}
~~~

`"Lan"` bắt đầu sau 4 byte của emoji nhưng sau 1 code point. Đừng trộn offset từ `$indexOfCP` vào `$substrBytes` hoặc ngược lại.

### 9.2. Kiểm tra có substring

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      code: 1,
      hasDash: {
        $gte: [
          { $indexOfCP: ["$code", "-"] },
          0
        ]
      }
    }
  }
]);
~~~

Kết quả `hasDash` là true cho các mã mẫu có dấu `-`. Nếu không tìm thấy, `$indexOfCP` trả -1.

### 9.3. Không nhầm substring search với regex

`$indexOfCP` tìm chuỗi con theo phép so khớp literal; nó không hiểu `[0-9]` hay `^ABC` như regular expression. Nếu cần pattern, dùng nhóm `$regexMatch`/`$regexFind`.

Các thao tác tìm literal này cũng không mặc định áp dụng toàn bộ quy tắc tương đương hoa/thường và dấu của collation.

## 10. $toLower, $toUpper và $strcasecmp

### 10.1. Chuyển chữ hoa và chữ thường

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      code: 1,
      codeUpper: { $toUpper: "$code" },
      codeLower: { $toLower: "$code" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Trên chuỗi mã ASCII:

~~~text
AB-001 → ab-001 (toLower)
ab-002 → AB-002 (toUpper)
~~~

**Giới hạn quan trọng:** MongoDB mô tả hành vi của `$toLower`, `$toUpper` và `$strcasecmp` là **chỉ được định nghĩa rõ cho chuỗi ký tự ASCII**. Không xây một chính sách chuẩn hóa tên tiếng Việt đầy đủ chỉ dựa vào những expression đó.

Ví dụ, việc mong `$toLower` chuẩn hóa chính xác mọi chữ có dấu, quy tắc viết hoa theo locale, hoặc các chuỗi Unicode phức tạp là không an toàn về mặt hợp đồng kỹ thuật.

### 10.2. So sánh hai chuỗi bằng $strcasecmp

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      compareWithLan: {
        $strcasecmp: ["$name", "lan"]
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

`$strcasecmp` trả số âm, 0 hoặc dương tương ứng với thứ tự so sánh không phân biệt hoa/thường theo semantics của nó. Với các chuỗi ASCII `Lan`, `lan` và `LAN`, kết quả so sánh với `lan` là 0.

Không dùng kết quả từ chuỗi có dấu/Unicode phức tạp để suy ra toàn bộ quy tắc collation tiếng Việt.

### 10.3. Khi cần so sánh chuỗi theo ngôn ngữ

Nếu yêu cầu là “tên so sánh theo locale, có thể phân biệt dấu nhưng bỏ qua hoa/thường”, dùng **collation** với những toán tử so sánh tương ứng như `$eq` hoặc `$sort`, thay vì nghĩ rằng `$toLower` trên mọi Unicode sẽ tạo khóa canonical hoàn chỉnh.

Nếu muốn lưu một field đã chuẩn hóa lâu dài, ứng dụng cần chính sách Unicode normalization, kiểm soát locale, test dữ liệu thực và duy trì field đó khi ghi.

## 11. $replaceOne và $replaceAll: thay chuỗi con

Trong **aggregation expression**, MongoDB có:

- `$replaceOne`: thay **lần xuất hiện đầu tiên** của chuỗi cần tìm.
- `$replaceAll`: thay **mọi lần xuất hiện** của chuỗi cần tìm.

Cả hai dùng các field:

~~~javascript
{
  $replaceOne: {
    input: <string-expression>,
    find: <string-expression>,
    replacement: <string-expression>
  }
}
~~~

Hoặc thay `$replaceOne` bằng `$replaceAll`.

### 11.1. So sánh một lần và mọi lần

~~~javascript
db.customers.aggregate([
  { $match: { _id: 11 } },
  {
    $project: {
      _id: 0,
      original: "$note",
      firstOnly: {
        $replaceOne: {
          input: "$note",
          find: "ORD",
          replacement: "ORDER"
        }
      },
      allMatches: {
        $replaceAll: {
          input: "$note",
          find: "ORD",
          replacement: "ORDER"
        }
      }
    }
  }
]);
~~~

ID 11 có note `"ORD-001, ORD-002"`. Kết quả:

~~~javascript
{
  original: "ORD-001, ORD-002",
  firstOnly: "ORDER-001, ORD-002",
  allMatches: "ORDER-001, ORDER-002"
}
~~~

### 11.2. Không tự coi tìm và thay là regex

`find` trong `$replaceAll` là chuỗi literal, không phải regex pattern:

~~~javascript
{
  $replaceAll: {
    input: "ORD-123",
    find: "[0-9]+",
    replacement: "XXX"
  }
}
~~~

Biểu thức này không tự thay dãy số thành `XXX` theo regex; nó tìm chuỗi literal `"[0-9]+"`. Với bài toán thay theo mẫu phức tạp, cần thiết kế nhiều bước trích/tái tạo string hoặc xử lý tại ứng dụng phù hợp.

### 11.3. Collation không điều khiển $replaceOne và $replaceAll

Giả sử query được chạy với:

~~~javascript
{
  collation: {
    locale: "en",
    strength: 1
  }
}
~~~

Strength 1 có thể coi `cafe` và `café` tương đương trong phép so sánh equality theo collation. Nhưng `$replaceAll` không áp dụng sự tương đương đó:

~~~javascript
db.customers.aggregate(
  [
    { $match: { _id: { $in: [4, 5] } } },
    {
      $project: {
        _id: 1,
        name: 1,
        renamed: {
          $replaceAll: {
            input: "$name",
            find: "cafe",
            replacement: "shop"
          }
        }
      }
    },
    { $sort: { _id: 1 } }
  ],
  {
    collation: { locale: "en", strength: 1 }
  }
);
~~~

Kỳ vọng:

~~~text
ID 4: "cafe" → "shop"
ID 5: "café" → "café" (không thay)
~~~

Ngữ nghĩa tìm chuỗi trong các expression replacement là phân biệt hoa/thường và dấu; **bỏ qua collation của operation**. Đây là một trong các giới hạn cốt lõi của bài.

### 11.4. Null/missing và chuẩn hóa đầu vào

Nếu `input`, `find` hoặc `replacement` null/missing, expression replacement có thể trả null theo semantics tương ứng. Khi cần chuỗi đầu ra ổn định:

~~~javascript
{
  $replaceAll: {
    input: { $ifNull: ["$note", ""] },
    find: "ORD",
    replacement: "ORDER"
  }
}
~~~

Nếu field có sai kiểu BSON, nên dùng schema validation hoặc biểu thức chuyển đổi có kiểm soát thay vì kỳ vọng phép thay chuỗi tự nhận mọi loại dữ liệu.

## 12. Regular expression: ba expression quan trọng

MongoDB hỗ trợ ba aggregation expression để xử lý regular expression:

| Expression | Dạng kết quả | Khi dùng |
|---|---|---|
| `$regexMatch` | Boolean | Kiểm tra có khớp pattern không |
| `$regexFind` | Một object khớp đầu tiên hoặc null | Trích chuỗi con đầu tiên, vị trí, capture groups |
| `$regexFindAll` | Mảng các object khớp | Trích mọi lần xuất hiện của pattern |

Ba expression dùng cấu hình cơ bản:

~~~javascript
{
  $regexMatch: {
    input: <string-expression>,
    regex: <pattern>,
    options: <regex-flags>
  }
}
~~~

`regex` có thể được biểu diễn dưới dạng chuỗi pattern hoặc regex literal trong ngữ cảnh hỗ trợ. `options` là tùy chọn; chỉ truyền khi cần cờ như `i`.

### 12.1. Regex literal trong mongosh

~~~javascript
{
  $regexMatch: {
    input: "$name",
    regex: /^lan$/i
  }
}
~~~

### 12.2. Pattern string và options

~~~javascript
{
  $regexMatch: {
    input: "$name",
    regex: "^lan$",
    options: "i"
  }
}
~~~

Hai ví dụ cùng định nghĩa pattern bắt đầu từ đầu chuỗi, chứa `lan` và kết thúc chuỗi, không phân biệt hoa/thường theo regex flag `i`.

Không khai báo một cờ theo hai cách gây xung đột (ví dụ literal đã có `i` nhưng `options` lặp lại không nhất quán). Đối với JSON của Compass hoặc pipeline được xây từ cấu hình, dạng string + options thường dễ biểu diễn.

### 12.3. Những ký hiệu regex thường gặp

| Ký hiệu | Ý nghĩa |
|---|---|
| `^` | Đầu chuỗi (hoặc đầu dòng khi có cờ phù hợp) |
| `$` | Cuối chuỗi (hoặc cuối dòng khi có cờ phù hợp) |
| `[0-9]` | Một chữ số ASCII |
| `[A-Z]` | Một chữ cái Latin viết hoa trong khoảng |
| `+` | Một hoặc nhiều |
| `*` | Không hoặc nhiều |
| `?` | Không hoặc một, hoặc modifier theo ngữ cảnh |
| `{3}` | Đúng 3 lần |
| `(...)` | Nhóm và có thể tạo capture |
| `a|b` | Một trong hai nhánh |
| `\d` | Ký hiệu nhóm chữ số theo semantics regex engine |
| `i` | Cờ không phân biệt hoa/thường |
| `m` | Cờ multiline, ảnh hưởng anchors |
| `s` | Cờ dotall để dấu chấm có thể khớp newline |
| `x` | Chế độ mở rộng cho pattern khi được hỗ trợ |

Không coi regex là công cụ validate đầy đủ mọi tiêu chuẩn phức tạp chỉ từ một biểu thức ngắn. Ví dụ xác thực email hoặc số điện thoại quốc tế còn có quy tắc nghiệp vụ riêng.

## 13. $regexMatch: kiểm tra một chuỗi có khớp pattern không

### 13.1. Tìm tên bằng mẫu case-insensitive

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      isLan: {
        $regexMatch: {
          input: "$name",
          regex: "^lan$",
          options: "i"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Với bộ mẫu:

- `isLan: true` ở ID **1, 2, 3**.
- `isLan: false` ở ID **11** vì `"lan-anh"` còn ký tự sau `lan`.
- ID 9 `"🎉Lan"` không khớp pattern có anchor `^` ở đầu.
- Những tên khác không khớp.

Nếu bỏ `$` ở cuối:

~~~javascript
{
  $regexMatch: {
    input: "$name",
    regex: "^lan",
    options: "i"
  }
}
~~~

thì ID 11 `"lan-anh"` cũng khớp. Vì thế, **anchor là thành phần của yêu cầu nghiệp vụ**, không chỉ là chi tiết cú pháp.

### 13.2. Dùng boolean trong $match

Có thể đưa expression vào `$expr` để lọc document:

~~~javascript
db.customers.aggregate([
  {
    $match: {
      $expr: {
        $regexMatch: {
          input: { $ifNull: ["$name", ""] },
          regex: "^lan$",
          options: "i"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả IDs **1, 2, 3**.

Tuy nhiên, đặt regex expression trong `$expr` không tự đảm bảo tận dụng index cho tìm kiếm theo tên. Khi bài toán chỉ là equality không phân biệt case và có index collation phù hợp, một `$match` equality với collation thường là thiết kế đáng cân nhắc hơn.

### 13.3. Kiểm tra dạng mã, không phải giá trị toàn chuỗi tùy ý

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      code: 1,
      codeLooksValid: {
        $regexMatch: {
          input: "$code",
          regex: "^[A-Z]{2}-[0-9]{3}$"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Tất cả mã mẫu trừ ID **2** có dạng hai chữ hoa ASCII + dấu gạch ngang + ba chữ số. ID 2 có `ab-002` nên không khớp pattern phân biệt hoa/thường.

Thêm `options: "i"` sẽ chấp nhận dạng `ab-002`. Nhưng điều đó chỉ kiểm tra *hình dạng*, không bảo đảm SKU hợp lệ trong nghiệp vụ hoặc tồn tại trong danh mục sản phẩm.

### 13.4. Null và input sai kiểu

ID 10 có `email: null`. Không nên giả định regex nhận null như chuỗi rỗng. Cần xử lý rõ:

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      hasExampleDomain: {
        $regexMatch: {
          input: {
            $ifNull: ["$email", ""]
          },
          regex: "@example[.]test$",
          options: "i"
        }
      }
    }
  }
]);
~~~

Với null/missing, fallback `""` cho boolean false, thay vì để expression hoạt động trên null không phù hợp kiểu.

Nếu email được lưu thành number hoặc array, `$ifNull` không sửa được kiểu đó. Khi dữ liệu không được schema đảm bảo, dùng `$type`/`$cond` hoặc chính sách `$convert` phù hợp.

## 14. $regexFind: lấy lần khớp đầu tiên, vị trí và captures

`$regexFind` trả:

~~~javascript
{
  match: <matched-string>,
  idx: <index>,
  captures: [<capture1>, <capture2>, ...]
}
~~~

hoặc `null` khi không có match. `idx` biểu thị vị trí của match tính bằng **Unicode code point**, không phải byte offset.

### 14.1. Trích mã từ ghi chú

ID 1 có note:

~~~text
Mã ORD-123, INV-456
~~~

Dùng:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      firstCode: {
        $regexFind: {
          input: "$note",
          regex: "(ORD|INV)-([0-9]{3})"
        }
      }
    }
  }
]);
~~~

Kết quả có dạng:

~~~javascript
{
  firstCode: {
    match: "ORD-123",
    idx: 3,
    captures: ["ORD", "123"]
  }
}
~~~

Với chuỗi đã cho, ba code point đầu là `M`, `ã` và dấu cách; `ORD` bắt đầu ở chỉ số 3 (bắt đầu đếm từ 0).

- `match` là toàn bộ đoạn khớp.
- `idx` là vị trí bắt đầu.
- `captures[0]` là nhóm thứ nhất `ORD|INV`.
- `captures[1]` là ba chữ số.

Nếu regex không dùng nhóm `(...)`, `captures` có thể là mảng rỗng; nhóm tùy chọn không tham gia match có thể xuất hiện dạng null tương ứng.

### 14.2. Chỉ trả chuỗi match

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $set: {
      extracted: {
        $regexFind: {
          input: "$note",
          regex: "(ORD|INV)-([0-9]{3})"
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      code: "$extracted.match"
    }
  }
]);
~~~

Kết quả `code: "ORD-123"`.

Nếu không tìm thấy match, `$regexFind` trả null, nên phải có quyết định rõ về field output mong muốn. Có thể sử dụng `$ifNull` hoặc biểu thức điều kiện:

~~~javascript
{
  $ifNull: [
    "$extracted.match",
    "KHONG_CO_MA"
  ]
}
~~~

### 14.3. Chỉ số Unicode của regexFind

Xét một biểu thức trên chuỗi chứa emoji:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 9 } },
  {
    $project: {
      _id: 0,
      found: {
        $regexFind: {
          input: "$name",
          regex: "Lan"
        }
      }
    }
  }
]);
~~~

Với `"🎉Lan"`, kết quả `found.idx` là **1** code point. Nếu bạn dùng `$indexOfBytes:["$name","Lan"]`, byte offset là **4**. Hai offset không thể hoán đổi cho nhau khi cắt chuỗi.

## 15. $regexFindAll: lấy mọi lần khớp

Cú pháp gần giống `$regexFind`:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      matches: {
        $regexFindAll: {
          input: "$note",
          regex: "(ORD|INV)-([0-9]{3})"
        }
      }
    }
  }
]);
~~~

Trên note `"Mã ORD-123, INV-456"`, kết quả có hai phần tử:

~~~javascript
{
  matches: [
    {
      match: "ORD-123",
      idx: 3,
      captures: ["ORD", "123"]
    },
    {
      match: "INV-456",
      idx: 12,
      captures: ["INV", "456"]
    }
  ]
}
~~~

Nếu không tìm thấy match, `$regexFindAll` trả **mảng rỗng**, khác với `$regexFind` trả null.

### 15.1. Lấy riêng các đoạn match thành mảng string

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      codes: {
        $map: {
          input: {
            $regexFindAll: {
              input: { $ifNull: ["$note", ""] },
              regex: "(ORD|INV)-([0-9]{3})"
            }
          },
          as: "hit",
          in: "$$hit.match"
        }
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  codes: ["ORD-123", "INV-456"]
}
~~~

### 15.2. Tạo document có mã loại và số

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      tokens: {
        $map: {
          input: {
            $regexFindAll: {
              input: "$note",
              regex: "(ORD|INV)-([0-9]{3})"
            }
          },
          as: "hit",
          in: {
            full: "$$hit.match",
            kind: {
              $arrayElemAt: ["$$hit.captures", 0]
            },
            number: {
              $arrayElemAt: ["$$hit.captures", 1]
            }
          }
        }
      }
    }
  }
]);
~~~

Kết quả minh họa:

~~~javascript
{
  tokens: [
    {
      full: "ORD-123",
      kind: "ORD",
      number: "123"
    },
    {
      full: "INV-456",
      kind: "INV",
      number: "456"
    }
  ]
}
~~~

`number` đang là chuỗi `"123"`, không tự trở thành số nguyên. Nếu cần số để tính toán, có thể dùng `$toInt` hoặc `$convert` với xử lý lỗi.

### 15.3. Đếm số lần xuất hiện

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      matchCount: {
        $size: {
          $regexFindAll: {
            input: { $ifNull: ["$note", ""] },
            regex: "(ORD|INV)-([0-9]{3})"
          }
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Với bộ dữ liệu mẫu:

- ID 1 và 4 có 2 mã.
- ID 2 và 5 có 1 mã.
- ID 11 có 2 mã.
- Những ID còn lại không có mã thỏa pattern ở ví dụ.

Đây là số **match của regex** trong chuỗi, không phải số document ở collection.

## 16. So sánh regex expression với query predicate $regex

Hai cú pháp thường bị nhầm:

### 16.1. Query predicate trong $match

~~~javascript
db.customers.aggregate([
  {
    $match: {
      name: {
        $regex: "^lan$",
        $options: "i"
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1
    }
  }
]);
~~~

`$regex` ở đây là **query operator**. Nó chọn document có tên khớp pattern và có thể được planner xem xét trong ngữ cảnh truy vấn.

### 16.2. Aggregation expression dùng $regexMatch

~~~javascript
db.customers.aggregate([
  {
    $match: {
      $expr: {
        $regexMatch: {
          input: "$name",
          regex: "^lan$",
          options: "i"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1
    }
  }
]);
~~~

`$regexMatch` là **aggregation expression trả boolean**. Nó còn có thể được dùng trong `$project`, `$set`, `$cond`, `$filter` và các stage/expression hỗ trợ.

Cả hai trường hợp có thể chọn ID **1, 2, 3** với dữ liệu mẫu. Tuy nhiên, cách lập kế hoạch và khả năng tận dụng index có thể khác; không kết luận hai cú pháp luôn có hiệu năng tương đương.

### 16.3. Chọn công cụ theo mục tiêu

| Mục tiêu | Lựa chọn |
|---|---|
| Chọn document có field khớp regex trực tiếp | Query `$regex` trong `$match` |
| Tạo field boolean `isValid` từ pattern | `$regexMatch` |
| Trích match đầu tiên với vị trí/captures | `$regexFind` |
| Trích nhiều match | `$regexFindAll` |
| So sánh tên bằng theo locale, không cần regex | Equality + collation tương thích |

Nếu bạn không cần trích mã hay tìm mẫu phức tạp, không nhất thiết dùng regex chỉ để mô phỏng equality.

## 17. Collation hoạt động như thế nào trong aggregation?

**Collation** định nghĩa cách so sánh và sắp xếp chuỗi theo các quy tắc ngôn ngữ. Ví dụ:

~~~javascript
{
  locale: "en",
  strength: 2
}
~~~

Có thể làm phép so sánh theo tiếng Anh phân biệt dấu nhưng bỏ qua khác biệt chữ hoa/thường đối với các ví dụ Latin thông dụng.

### 17.1. Các mức strength cơ bản

| Cấu hình | Ý nghĩa khái quát cho các ví dụ Latin |
|---|---|
| `strength: 1` | Thường bỏ qua khác biệt case và dấu |
| `strength: 2` | Phân biệt dấu, thường bỏ qua case |
| `strength: 3` | Phân biệt thêm case |

Đây là cách diễn giải khái quát, không phải một danh sách đầy đủ quy tắc Unicode/ICU. Các tùy chọn như `caseLevel` và locale cụ thể có thể làm hành vi chi tiết khác đi.

### 17.2. Collation trong lệnh aggregate

~~~javascript
db.customers.aggregate(
  [
    { $match: { name: "lan" } },
    {
      $project: {
        _id: 1,
        name: 1
      }
    },
    { $sort: { _id: 1 } }
  ],
  {
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Với dữ liệu mẫu, kết quả ID **1, 2, 3** vì `Lan`, `lan` và `LAN` tương đương theo cấu hình này.

Nếu collection có simple collation mặc định và operation không chỉ định collation:

~~~javascript
db.customers.aggregate([
  { $match: { name: "lan" } }
]);
~~~

thì equality thường chỉ chọn ID **2**. Đó là khác biệt do quy tắc so sánh, không phải do MongoDB tự viết lại tên.

### 17.3. Strength 1 và 2 với dấu

~~~javascript
db.customers.aggregate(
  [
    { $match: { name: "cafe" } },
    { $project: { _id: 1, name: 1 } },
    { $sort: { _id: 1 } }
  ],
  { collation: { locale: "en", strength: 1 } }
);
~~~

Với ví dụ `cafe`/`café`, strength 1 có thể trả ID **4, 5**.

~~~javascript
db.customers.aggregate(
  [
    { $match: { name: "cafe" } },
    { $project: { _id: 1, name: 1 } },
    { $sort: { _id: 1 } }
  ],
  { collation: { locale: "en", strength: 2 } }
);
~~~

Strength 2 phân biệt dấu nên chỉ ID **4** theo bộ mẫu.

Không suy rộng từ cặp này rằng mọi biến thể chữ và dấu của tất cả ngôn ngữ đều có quy tắc tương đương tuyệt đối giống nhau.

### 17.4. Collation ảnh hưởng tới $eq

Có thể dùng aggregation comparison expression:

~~~javascript
db.customers.aggregate(
  [
    {
      $project: {
        _id: 1,
        name: 1,
        equalsLan: {
          $eq: ["$name", "lan"]
        }
      }
    },
    { $sort: { _id: 1 } }
  ],
  { collation: { locale: "en", strength: 2 } }
);
~~~

Trong cấu hình này, `equalsLan` là true cho các tên `Lan`, `lan`, `LAN` theo ngữ nghĩa collation. Đây là ví dụ expression so sánh chuỗi, khác với nhóm regex có quy tắc riêng.

### 17.5. Collation ảnh hưởng tới $sort và $group

~~~javascript
db.customers.aggregate(
  [
    {
      $group: {
        _id: "$name",
        count: { $sum: 1 },
        ids: { $push: "$_id" }
      }
    },
    { $sort: { _id: 1 } }
  ],
  { collation: { locale: "en", strength: 2 } }
);
~~~

Các biến thể `Lan/lan/LAN` có thể được nhóm cùng nhau vì `$group` sử dụng quy tắc so sánh string theo collation của operation.

Tên `_id` đại diện cho nhóm không nên được coi là bản chuẩn hóa chữ hoa/thường có hợp đồng hiển thị cố định. Nếu ứng dụng cần một giá trị canonical, hãy định nghĩa quy tắc riêng.

Tương tự, `$sort` theo tên với collation có thể cho thứ tự khác simple binary. Khi phân trang theo chuỗi locale-aware, thêm khóa duy nhất làm tie-breaker để thứ tự ổn định.

### 17.6. Collation được khai báo ở phạm vi nào?

Một operation aggregate thường có **một collation áp dụng cho toàn bộ command**, không phải tùy ý một collation cho mỗi field/stage.

Nếu collection có default collation, thao tác không override có thể thừa kế default đó. Index cũng có thể kế thừa hoặc khai báo riêng.

Muốn kiểm tra:

~~~javascript
db.getCollectionInfos({ name: "customers" });
db.customers.getIndexes();
~~~

Trong bài thực hành, collection được tạo ngầm qua các lệnh ghi mà không khai báo default collation riêng, nên các ví dụ không chỉ định collation dựa trên mặc định simple của môi trường mới.

## 18. Giới hạn cốt lõi: regex bỏ qua collation

Các aggregation regex expression:

- `$regexMatch`.
- `$regexFind`.
- `$regexFindAll`.

**Không collation-aware:** chúng bỏ qua quy tắc so sánh chuỗi của collation. Chúng sử dụng ngữ nghĩa regular expression và những cờ regex được khai báo.

### 18.1. So sánh equality với regex trên cafe/café

Equality theo strength 1:

~~~javascript
db.customers.aggregate(
  [
    { $match: { name: "cafe" } },
    { $project: { _id: 1, name: 1 } }
  ],
  {
    collation: {
      locale: "en",
      strength: 1
    }
  }
);
~~~

Có thể trả cả ID **4** (`cafe`) và **5** (`café`).

Nhưng:

~~~javascript
db.customers.aggregate(
  [
    {
      $project: {
        _id: 1,
        name: 1,
        matchesPattern: {
          $regexMatch: {
            input: "$name",
            regex: "^cafe$",
            options: "i"
          }
        }
      }
    }
  ],
  {
    collation: {
      locale: "en",
      strength: 1
    }
  }
);
~~~

`matchesPattern` là true với `"cafe"` (ID 4) và false với `"café"` (ID 5). Cờ regex `i` xử lý khác biệt hoa/thường theo regex engine; nó **không có nghĩa bỏ qua dấu** như collation strength 1 ở ví dụ này.

### 18.2. RegexFind cũng không tự bỏ dấu

~~~javascript
db.customers.aggregate(
  [
    { $match: { _id: 5 } },
    {
      $project: {
        _id: 0,
        found: {
          $regexFind: {
            input: "$name",
            regex: "cafe"
          }
        }
      }
    }
  ],
  { collation: { locale: "en", strength: 1 } }
);
~~~

`found` không tìm thấy `"cafe"` nguyên văn trong `"café"`. Đặt strength 1 không làm `$regexFind` biến regex thành phép so sánh equality locale-aware.

### 18.3. RegexFindAll cũng vậy

Tương tự:

~~~javascript
{
  $regexFindAll: {
    input: "$name",
    regex: "cafe",
    options: "i"
  }
}
~~~

không tự coi `café` là `cafe` chỉ vì operation có collation bỏ dấu.

### 18.4. Query $regex có cùng cảnh báo về collation

`$regex` trong query predicate không collation-aware theo cách equality hoặc sort sử dụng ICU collation. Thêm collation strength 1 vào truy vấn `{name:{$regex:"^cafe$"}}` không đồng nghĩa nó sẽ nhận diện mọi biến thể có dấu.

Nếu yêu cầu là so sánh **bằng nhau theo collation**, hãy dùng equality với collation tương thích; không thay bằng regex chỉ vì muốn “linh hoạt”.

## 19. Những string expression nào phụ thuộc collation?

Đây là câu hỏi quan trọng để tránh áp dụng một quy tắc chung cho mọi biểu thức:

| Nhóm | Ví dụ | Cần hiểu về collation |
|---|---|---|
| So sánh và sắp xếp chuỗi | `$eq`, equality trong `$match`, `$sort`, `$group` | Sử dụng collation của operation trong ngữ cảnh hỗ trợ |
| Regex expression | `$regexMatch`, `$regexFind`, `$regexFindAll` | Bỏ qua collation; dùng regex và regex options |
| Thay chuỗi con | `$replaceOne`, `$replaceAll` | Bỏ qua collation; tìm literal, phân biệt ký tự |
| Tìm vị trí chuỗi con | `$indexOfBytes`, `$indexOfCP` | Không xem đây là equality locale-aware |
| Tách chuỗi | `$split` | Tách theo delimiter chuỗi, không phải regex locale-aware |
| Độ dài/cắt chuỗi | `$strLenBytes`, `$strLenCP`, `$substrBytes`, `$substrCP` | Tính đơn vị byte hoặc code point, không chuẩn hóa theo collation |
| Biến đổi chữ | `$toLower`, `$toUpper` | Không thay thế phép so sánh theo locale; chú ý giới hạn ASCII |
| So sánh bỏ qua hoa/thường kiểu expression riêng | `$strcasecmp` | Chú ý hành vi chỉ được định nghĩa rõ cho ASCII |

Không suy luận rằng “toàn bộ aggregation tôn trọng collation” theo cùng một cách. Hãy xác định chính xác expression có semantics so sánh locale-aware hay semantics regex/literal/byte riêng.

## 20. Index có collation và giới hạn tối ưu regex

### 20.1. Tạo index cho equality không phân biệt case

~~~javascript
db.customers.createIndex(
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

Truy vấn:

~~~javascript
db.customers.find({
  name: "lan"
})
.collation({
  locale: "en",
  strength: 2
})
.explain("executionStats");
~~~

Index trên có ngữ nghĩa tương thích với phép so sánh string của query. MongoDB **có thể** dùng nó khi planner thấy có lợi.

Nếu query không chỉ định collation trên collection simple:

~~~javascript
db.customers.find({
  name: "lan"
}).explain("executionStats");
~~~

thì query và index strength 2 không có cùng semantics cho equality string. Cần phân biệt **đúng kết quả** với **dùng index hiệu quả**.

### 20.2. Vì sao case-insensitive regex không tự được index này tăng tốc?

~~~javascript
db.customers.find({
  name: {
    $regex: "^lan$",
    $options: "i"
  }
}).collation({
  locale: "en",
  strength: 2
}).explain("executionStats");
~~~

Index case-insensitive với collation strength 2 **không tự tối ưu hiệu quả** cho `$regex` có cờ `i`. Regex không collation-aware theo cách index chuỗi locale-aware được tổ chức.

Một regex có prefix phân biệt case đôi khi có thể khai thác index theo simple collation trong những tình huống phù hợp. Điều đó khác với việc index locale-aware case-insensitive có thể xử lý mọi regex `/i`.

### 20.3. Expression regex trong $expr cũng cần đo riêng

~~~javascript
db.customers.aggregate([
  {
    $match: {
      $expr: {
        $regexMatch: {
          input: "$name",
          regex: "^lan$",
          options: "i"
        }
      }
    }
  }
]);
~~~

Lọc bằng expression có thể làm server phải đánh giá regex trên nhiều document. Đừng mặc định query planner biến phép thử này thành equality lookup tận dụng index collation.

### 20.4. Xem explain

~~~javascript
db.customers.find({
  name: "lan"
})
.collation({
  locale: "en",
  strength: 2
})
.explain("executionStats");
~~~

Theo dõi:

- `winningPlan`.
- `IXSCAN` hoặc `COLLSCAN`.
- `indexName`.
- `indexBounds`.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `nReturned`.

Trên 11 document, planner có thể chọn collection scan vì tập rất nhỏ. Không kết luận index sai chỉ vì không được chọn trong một bài thử nhỏ.

### 20.5. Khi nào nên cân nhắc công cụ tìm kiếm khác?

Các nhu cầu như tìm kiếm ngôn ngữ tự nhiên, autocomplete, fuzzy matching, nhiều loại dấu, tách từ hoặc tìm mẫu lớn có thể vượt phạm vi của equality index và regex đơn giản.

Có thể cân nhắc thiết kế field search canonical theo hợp đồng, text search hoặc giải pháp search chuyên dụng phù hợp hạ tầng và yêu cầu. Không mặc định thêm cờ `i` cho regex là đủ để xây hệ thống tìm kiếm đa ngôn ngữ hiệu quả.

## 21. Dữ liệu Unicode và giới hạn chuẩn hóa

### 21.1. Chữ có dấu và dạng chuẩn hóa

Chuỗi trực quan giống `é` có thể được biểu diễn:

~~~text
Dạng precomposed:       U+00E9
Dạng decomposed:        U+0065 + U+0301
~~~

Một số phép so sánh theo collation có thể xử lý các quan hệ tương đương này theo quy tắc Unicode/locale. Nhưng những expression xử lý **literal substring**, regex hoặc code point không nên được giả định sẽ tự chuẩn hóa tất cả dạng giống nhau về thị giác.

Ví dụ:

~~~javascript
{
  $replaceAll: {
    input: "$name",
    find: "é",
    replacement: "e"
  }
}
~~~

không nên được xem là một giải pháp chuẩn hóa toàn bộ chuỗi tiếng Việt hay mọi dạng Unicode dấu ghép.

### 21.2. Không coi lowercase là chuẩn hóa dấu

Ngay cả khi một expression biến chữ hoa thành thường, nó không tự bỏ dấu, không tách từ, không thực hiện transliteration và không áp dụng mọi quy tắc locale.

Một hệ thống cần tìm `"Ánh"` khi người dùng gõ `"anh"` phải xác định:

- Có thực sự muốn bỏ dấu trong nghiệp vụ hay không?
- Tên được chuẩn hóa theo quy tắc nào?
- Có cần giữ dữ liệu gốc để hiển thị?
- Quy tắc có thay đổi khi locale khác không?
- Có index nào phục vụ biểu thức tìm kiếm được chọn?
- Có rủi ro hai tên khác nhau bị xem là trùng không?

### 21.3. Chọn đúng đơn vị độ dài

| Thông tin | Công cụ phù hợp |
|---|---|
| Byte UTF-8 | `$strLenBytes` |
| Unicode code point | `$strLenCP` |
| Vị trí byte | `$indexOfBytes` |
| Vị trí code point | `$indexOfCP` |
| Cắt theo byte | `$substrBytes` |
| Cắt theo code point | `$substrCP` |
| Vị trí match regex | `$regexFind.idx` là code point |
| Số ký tự người dùng nhìn thấy | Cần xác định grapheme-cluster semantics; không mặc định bằng code point |

Tránh trộn các đơn vị này trong một pipeline cắt chuỗi có Unicode.

## 22. Xây pipeline thực tế: làm sạch, trích mã và tạo output

Ví dụ tạo báo cáo cho tenant-A:

- Làm sạch khoảng trắng ở tên.
- Tách nhãn thành array đã trim và loại rỗng.
- Kiểm tra mã có hình dạng hai chữ cái Latin viết hoa + `-` + ba chữ số không.
- Trích mọi mã đơn/chứng từ từ ghi chú.
- Chỉ trả một tập field được phép hiển thị.

~~~javascript
db.customers.aggregate([
  {
    $match: {
      tenantId: "tenant-A"
    }
  },
  {
    $set: {
      cleanName: {
        $trim: {
          input: { $ifNull: ["$name", ""] }
        }
      },
      cleanedTags: {
        $filter: {
          input: {
            $map: {
              input: {
                $split: [
                  { $ifNull: ["$rawTags", ""] },
                  ","
                ]
              },
              as: "tag",
              in: {
                $trim: {
                  input: "$$tag"
                }
              }
            }
          },
          as: "tag",
          cond: {
            $ne: ["$$tag", ""]
          }
        }
      },
      codeIsValid: {
        $regexMatch: {
          input: { $ifNull: ["$code", ""] },
          regex: "^[A-Z]{2}-[0-9]{3}$"
        }
      },
      extractedCodes: {
        $map: {
          input: {
            $regexFindAll: {
              input: { $ifNull: ["$note", ""] },
              regex: "(ORD|INV)-([0-9]{3})"
            }
          },
          as: "hit",
          in: "$$hit.match"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      cleanName: 1,
      code: 1,
      codeIsValid: 1,
      cleanedTags: 1,
      extractedCodes: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Một vài kết quả có thể đối chiếu:

| ID | cleanName | codeIsValid | cleanedTags | extractedCodes |
|---|---|---|---|---|
| 1 | Lan | true | `["vip","new"]` | `["ORD-123","INV-456"]` |
| 2 | lan | false | `["new","vip"]` | `["ORD-789"]` |
| 3 | LAN | true | `[]` | `[]` |
| 4 | cafe | true | `["food","sale"]` | `["ORD-123","INV-456"]` |
| 5 | café | true | `["food"]` | `["ORD-456"]` |
| 8 | Minh | true | `["new","vip"]` | `[]` |
| 10 | Mai | true | `[]` | `[]` |

Pipeline không biến dữ liệu gốc thành lowercase hoặc thay đổi field trên server. Nó chỉ trả document đầu ra đã định hình.

### 22.1. Nếu chỉ muốn giữ document có mã hợp lệ

Vì `codeIsValid` được tạo trong `$set`, có thể thêm:

~~~javascript
{
  $match: { codeIsValid: true }
}
~~~

**Sau** `$set` rồi mới `$project`. Nếu cần lọc trực tiếp bằng regex trên `code` ở đầu pipeline, có thể dùng query predicate `$regex` trong `$match`. Cách nào tốt hơn phụ thuộc việc có cần giá trị boolean trong output và kế hoạch truy vấn.

### 22.2. Nếu muốn sắp xếp tên theo locale

~~~javascript
db.customers.aggregate(
  [
    { $match: { tenantId: "tenant-A" } },
    { $project: { _id: 1, name: 1 } },
    { $sort: { name: 1, _id: 1 } }
  ],
  {
    collation: {
      locale: "vi",
      strength: 2
    }
  }
);
~~~

Đây là thao tác sort có collation, không phải regex. Trên dữ liệu tên người thực tế, cần xác định locale và thứ tự mong muốn, đồng thời dùng khóa `_id` làm tie-breaker cho phân trang.

Không dùng kết quả thứ tự ở locale `vi` để suy ra mọi phép biến đổi `$toLower`, regex hoặc replacement cũng sẽ theo thứ tự/ngữ nghĩa tiếng Việt.

## 23. Tối ưu hiệu năng và hạn chế regex đầu vào

### 23.1. Regex có thể rất đắt

Một biểu thức regex được thực thi cho số lượng lớn document có thể tiêu tốn CPU. Các pattern phức tạp, sự lặp lại mơ hồ và input dài có thể dẫn tới **catastrophic backtracking** hoặc các tình huống thời gian xử lý lớn.

Đặc biệt thận trọng khi cho người dùng cung cấp pattern tùy ý.

Nên:

1. Hạn chế độ dài của pattern và input.
2. Chỉ cho phép pattern thuộc tập đã kiểm soát nếu có thể.
3. Không ghép thẳng dữ liệu người dùng thành regex phức tạp mà không escape ký tự điều khiển.
4. Xác định nhu cầu thực: equality, prefix, full-text hay extraction.
5. Lọc tập document bằng điều kiện chọn lọc và index phù hợp trước khi chạy regex trên từng giá trị.
6. Đo độ trễ và giám sát truy vấn chậm.
7. Cân nhắc giới hạn thời gian thực thi và fallback đúng ngữ nghĩa.

Regex không phải phương thức duy nhất để giải quyết mọi yêu cầu tìm kiếm chuỗi.

### 23.2. Đừng để một field thiếu làm hỏng pipeline

Các expression string thường yêu cầu đầu vào là chuỗi hoặc array đúng kiểu. Dữ liệu null/missing/sai kiểu có thể khiến expression trả null hoặc lỗi tùy toán tử.

Ví dụ an toàn cho regex:

~~~javascript
{
  $regexMatch: {
    input: {
      $cond: [
        { $eq: [{ $type: "$note" }, "string"] },
        "$note",
        ""
      ]
    },
    regex: "ORD-[0-9]{3}"
  }
}
~~~

Ở đây, nếu `note` không phải string, expression dùng `""`, tránh đưa số, mảng hoặc null vào regex. Nếu bài toán cần phân biệt lỗi dữ liệu với “không khớp”, ứng dụng có thể giữ thêm trường `noteType` để chẩn đoán.

### 23.3. Giữ bộ lọc tenant trong cả truy vấn và kết quả

Một pipeline phân tích customer có thể chỉ cần tên/mã, nhưng vẫn phải filter đúng phạm vi quyền:

~~~javascript
{
  $match: {
    tenantId: "tenant-A"
  }
}
~~~

Việc `$project` bỏ `tenantId` khỏi output không bảo đảm chỉ đọc dữ liệu tenant-A; cần filter ở đầu pipeline và phân quyền tại tầng ứng dụng/database.

### 23.4. Explain khi nào?

~~~javascript
db.customers.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 1,
      matches: {
        $regexMatch: {
          input: "$name",
          regex: "^lan$",
          options: "i"
        }
      }
    }
  }
]);
~~~

Quan sát `winningPlan`, số document quét và các stage liên quan nếu server cung cấp. Có thể cần index theo tenant cho workload thực tế, nhưng không tạo index chỉ từ 11 document mẫu rồi kết luận đã tối ưu production.

## 24. MongoDB Compass: sử dụng biểu thức và collation

MongoDB Compass thường cung cấp giao diện **Aggregations** để thêm các stage. Tên các nút và vùng Options có thể thay đổi theo phiên bản.

Quy trình đề xuất:

1. Kết nối Compass tới đúng server đang chứa `aggregation_string_lab.customers`.
2. Mở collection `customers` và tab **Aggregations**.
3. Tạo stage `$match` lọc tenant-A:

   ~~~json
   {"tenantId":"tenant-A"}
   ~~~

4. Thêm stage `$project` với biểu thức trim:

   ~~~json
   {
     "_id":1,
     "name":1,
     "cleanName":{"$trim":{"input":"$name"}}
   }
   ~~~

5. Chạy và quan sát ID 8 chuyển từ `"  Minh  "` thành `"Minh"` trong output.
6. Thử `$regexMatch`:

   ~~~json
   {
     "_id":1,
     "name":1,
     "isLan":{
       "$regexMatch":{
         "input":"$name",
         "regex":"^lan$",
         "options":"i"
       }
     }
   }
   ~~~

7. Thử `$regexFindAll` trên field `note` để lấy các mã.
8. Nếu giao diện hỗ trợ cấu hình **Collation** cho aggregation, đặt `{"locale":"en","strength":1}` rồi so sánh equality `cafe`/`café` với `$regexMatch`.
9. Nếu không thấy tùy chọn collation, dùng `mongosh` để truyền object options thứ hai vào `aggregate(...)`, tránh suy luận từ UI.
10. Sau khi chạy, quay lại tab Documents để xác nhận aggregation chỉ đọc không tự thay đổi dữ liệu gốc.

Một số phiên bản Compass yêu cầu chọn tên stage (`$project`) riêng và chỉ nhập nội dung stage vào editor. Khi đó không nhập lồng cả object `{"$project":...}` vào ô đã chọn stage.

## 25. Java Driver: xây pipeline xử lý chuỗi

Trong MongoDB Java Driver, có thể tạo aggregation pipeline bằng các BSON `Document`. Ví dụ sau chỉ minh họa phần truy vấn; biến `database` phải là `MongoDatabase` đã kết nối.

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

MongoCollection<Document> customers =
    database.getCollection("customers");

Document normalizedName = new Document(
    "$trim",
    new Document(
        "input",
        new Document("$ifNull", Arrays.asList("$name", ""))
    )
);

Document regexMatch = new Document(
    "$regexMatch",
    new Document("input", "$code")
        .append("regex", "^[A-Z]{2}-[0-9]{3}$")
);

List<Document> pipeline = Arrays.asList(
    new Document("$match",
        new Document("tenantId", "tenant-A")),

    new Document("$project",
        new Document("_id", 1)
            .append("name", 1)
            .append("cleanName", normalizedName)
            .append("code", 1)
            .append("codeIsValid", regexMatch))
);

List<Document> result = customers.aggregate(pipeline)
    .into(new ArrayList<>());

for (Document item : result) {
    System.out.println(item.toJson());
}
~~~

### 25.1. Chỉ định collation cho aggregation

~~~java
import com.mongodb.client.model.Collation;
import com.mongodb.client.model.CollationStrength;

Collation caseInsensitive = Collation.builder()
    .locale("en")
    .collationStrength(CollationStrength.SECONDARY)
    .build();

List<Document> result = customers.aggregate(
    Arrays.asList(
        new Document("$match", new Document("name", "lan")),
        new Document("$project",
            new Document("_id", 1).append("name", 1))
    )
).collation(caseInsensitive)
 .into(new ArrayList<>());
~~~

Với collection chỉ có bộ mẫu, equality trên `name` ở strength 2 có thể chọn ID **1, 2, 3**.

**Không nhầm:** `.collation(caseInsensitive)` không khiến `$regexMatch` hoặc `$regexFind` bên trong pipeline tự bỏ qua dấu hoặc áp dụng so khớp theo locale. Regex có semantics riêng.

### 25.2. Tránh truyền pattern không tin cậy thẳng vào pipeline

Nếu API nhận từ khóa người dùng và mục tiêu là **tìm một chuỗi literal**, hãy bảo đảm các ký tự như `.`, `*`, `?`, `[`, `(` được escape khi dùng chúng trong regex. Việc tạo BSON `Document` tránh ghép JSON bằng chuỗi một cách tùy tiện, nhưng **không tự kiểm soát chi phí regex** hoặc tính hợp lệ của pattern.

Khi nghiệp vụ thật ra cần equality không phân biệt case, một phép equality với collation phù hợp và index tương thích có thể đơn giản, dễ kiểm soát hơn.

## 26. Những lỗi và hiểu nhầm thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `$concat` trả null | Một thành phần null/missing | Dùng `$ifNull` cho từng trường cần fallback |
| `$concat` không nhận number | Toán hạng không phải chuỗi | `$toString` hoặc `$convert` với xử lý lỗi |
| `$trim` không bỏ khoảng trắng giữa từ | Trim chỉ xử lý các đầu | Dùng quy tắc chuẩn hóa khác cho whitespace nội bộ |
| `$split` còn dấu cách đầu phần tử | Split không tự trim | `$map` + `$trim` |
| Tags có phần tử rỗng | Delimiter liền nhau hoặc input rỗng | `$filter` loại chuỗi rỗng |
| `$size`/`$map` lỗi kiểu | Input không phải array | `$isArray` hoặc schema validation |
| `$strLenBytes` khác `$strLenCP` | UTF-8 đa byte | Chọn đúng đơn vị |
| `$substrBytes` lỗi trên emoji | Cắt giữa chuỗi byte UTF-8 của ký tự | `$substrCP` hoặc dùng byte offset đúng |
| Match index từ regexFind không dùng được cho substrBytes | `idx` tính code point | Dùng `$substrCP` nếu cần cùng đơn vị |
| `$indexOfCP` trả -1 | Không tìm thấy chuỗi con | Kiểm tra trước khi sử dụng offset |
| `$regexFind` trả null | Không có match | `$ifNull` hoặc xử lý null |
| `$regexFindAll` trả `[]` | Không có match | Đây là trạng thái hợp lệ |
| `$regexMatch` không nhận null | Input không phù hợp kiểu | `$ifNull` hoặc kiểm tra `$type` |
| Pattern `^lan$` không khớp `lan-anh` | Có anchor kết thúc | Bỏ `$` nếu muốn prefix, sau khi xác định đúng yêu cầu |
| Regex với `i` vẫn không khớp `café` khi tìm `cafe` | Case-insensitive không đồng nghĩa accent-insensitive | Dùng equality + collation khi yêu cầu là bằng nhau theo locale |
| Collation strength 1 không ảnh hưởng regex | Regex expressions bỏ qua collation | Dùng regex options hoặc thiết kế search phù hợp |
| `$replaceAll` không thay `café` bằng find `cafe` | Replacement literal bỏ qua collation | Chuẩn hóa có chủ đích hoặc chọn phép so sánh đúng |
| Index CI không tăng tốc regex `/i` như mong đợi | Regex không collation-aware | So sánh equality + collation/index hoặc phương án search khác |
| `$toLower` không chuẩn hóa tên Unicode như mong muốn | Hành vi chỉ được định nghĩa rõ cho ASCII | Định nghĩa chính sách Unicode ở ứng dụng |
| `$group` gộp tên khác cách viết hoa | Collation có thể coi chuỗi tương đương | Chọn strength phù hợp; không coi khóa nhóm là canonical tự sinh |
| Count và trang có tập kết quả khác | Filter/collation/điều kiện không đồng nhất | Dùng cùng phạm vi và cùng collation |
| Pipeline rất chậm khi dùng regex phức tạp | Backtracking, scan nhiều document | Giới hạn pattern/input, lọc sớm, đo workload |
| Kết quả trong aggregate đúng nhưng database không đổi | Pipeline đọc không ghi | Dùng write API riêng nếu yêu cầu cập nhật thật |

## 27. Bài thực hành

Các bài sử dụng bộ dữ liệu 11 document ở mục 3.

### Bài 1. Làm sạch tên

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      before: "$name",
      after: {
        $trim: { input: "$name" }
      }
    }
  },
  { $match: { _id: 8 } }
]);
~~~

**Kỳ vọng:** `before: "  Minh  "` và `after: "Minh"`. Giải thích vì sao `$trim` không phải regex và không tự chuẩn hóa dấu.

### Bài 2. Ghép nhãn và xử lý null

~~~javascript
db.customers.aggregate([
  { $match: { _id: 10 } },
  {
    $project: {
      label: {
        $concat: [
          "$name",
          " <",
          { $ifNull: ["$email", "unknown"] },
          ">"
        ]
      }
    }
  }
]);
~~~

**Kỳ vọng:** `"Mai <unknown>"`. Nếu bỏ `$ifNull`, điều gì xảy ra?

### Bài 3. Chuẩn hóa tags

Dùng `$split`, `$map`, `$trim` và `$filter` trên ID 8.

**Kỳ vọng:** `["new","vip"]`. Vì sao chỉ dùng `$split` là chưa đủ?

### Bài 4. Unicode bytes và code points

~~~javascript
db.customers.aggregate([
  { $match: { _id: 9 } },
  {
    $project: {
      name: 1,
      byteLength: { $strLenBytes: "$name" },
      cpLength: { $strLenCP: "$name" },
      startBytes: {
        $indexOfBytes: ["$name", "Lan"]
      },
      startCP: {
        $indexOfCP: ["$name", "Lan"]
      }
    }
  }
]);
~~~

**Kỳ vọng:** `byteLength:7`, `cpLength:4`, `startBytes:4`, `startCP:1`.

### Bài 5. Regex boolean

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      matched: {
        $regexMatch: {
          input: "$name",
          regex: "^lan$",
          options: "i"
        }
      }
    }
  },
  { $match: { matched: true } },
  { $sort: { _id: 1 } }
]);
~~~

**Kỳ vọng IDs:** 1, 2, 3. Nếu đổi pattern thành `^lan`, ID nào được thêm?

### Bài 6. Regex trích mã

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      first: {
        $regexFind: {
          input: "$note",
          regex: "(ORD|INV)-([0-9]{3})"
        }
      },
      all: {
        $regexFindAll: {
          input: "$note",
          regex: "(ORD|INV)-([0-9]{3})"
        }
      }
    }
  }
]);
~~~

**Kỳ vọng:** `first.match = "ORD-123"`, `first.idx = 3` và `all` có 2 phần tử, lần lượt ORD-123 và INV-456.

### Bài 7. Tính số match theo từng khách

Dùng `$size` kết hợp `$regexFindAll` để tạo `matchCount` từ `note`. Với ID 10 thiếu note, tránh lỗi bằng `$ifNull`.

**Kỳ vọng:** ID 1, 4, 11 có 2 match; ID 2, 5 có 1; các ID còn lại có 0.

### Bài 8. Thay một lần và thay mọi lần

~~~javascript
db.customers.aggregate([
  { $match: { _id: 11 } },
  {
    $project: {
      first: {
        $replaceOne: {
          input: "$note",
          find: "ORD",
          replacement: "ORDER"
        }
      },
      all: {
        $replaceAll: {
          input: "$note",
          find: "ORD",
          replacement: "ORDER"
        }
      }
    }
  }
]);
~~~

**Kỳ vọng:** `first` chỉ đổi ORD đầu; `all` đổi cả hai.

### Bài 9. Equality collation khác regex

Chạy:

~~~javascript
db.customers.aggregate(
  [
    { $match: { name: "cafe" } },
    { $project: { _id: 1, name: 1 } }
  ],
  { collation: { locale: "en", strength: 1 } }
);
~~~

Rồi thử:

~~~javascript
db.customers.aggregate(
  [
    {
      $project: {
        _id: 1,
        name: 1,
        matched: {
          $regexMatch: {
            input: "$name",
            regex: "^cafe$",
            options: "i"
          }
        }
      }
    },
    { $match: { matched: true } }
  ],
  { collation: { locale: "en", strength: 1 } }
);
~~~

**Kỳ vọng:** Equality có thể chọn ID 4 và 5, còn regex chỉ chọn ID 4. Giải thích chính xác vì sao.

### Bài 10. Collation không làm replaceAll bỏ dấu

Trên ID 4 và 5, dùng `$replaceAll` tìm chuỗi `"cafe"` rồi thay bằng `"shop"`. Đặt collation `locale:"en", strength:1` cho operation.

**Kỳ vọng:** ID 4 đổi tên trong output thành `"shop"`; ID 5 giữ `"café"`.

### Bài 11. So sánh $eq với $strcasecmp

Dùng `$eq:["$name","lan"]` kèm collation strength 2 để so sánh ba biến thể Lan. Sau đó dùng `$strcasecmp` trên chuỗi ASCII tương ứng.

**Giải thích:** Hai phương thức có thể cùng kết luận ba chuỗi ASCII đó tương đương về case, nhưng `$strcasecmp` không phải cách thay thế mọi quy tắc collation cho tên Unicode có dấu.

### Bài 12. Regex kiểm tra code

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      code: 1,
      validCode: {
        $regexMatch: {
          input: "$code",
          regex: "^[A-Z]{2}-[0-9]{3}$"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

**Kỳ vọng:** ID 2 không khớp vì `ab-002` có chữ thường; các mã còn lại phù hợp hình dạng. Nếu cho thêm cờ `i`, ID 2 được chấp nhận về mặt pattern.

### Bài 13. Làm pipeline chịu được missing/null

Tạo output `noteCodes` là mảng mọi mã từ `note`, ngay cả khi note null hoặc field không tồn tại:

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      noteCodes: {
        $map: {
          input: {
            $regexFindAll: {
              input: { $ifNull: ["$note", ""] },
              regex: "(ORD|INV)-([0-9]{3})"
            }
          },
          as: "hit",
          in: "$$hit.match"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

**Kỳ vọng:** ID 10 có `noteCodes: []`, không làm pipeline lỗi.

### Bài 14. So sánh hiệu năng

Tạo index collation trong mục 20 rồi xem explain cho:

1. Equality `name:"lan"` với `en/strength:2`.
2. Regex `^lan$` có `options:"i"`.

Nhận xét `IXSCAN`/`COLLSCAN`, keys/docs examined và giới hạn của bài thử 11 document. Không coi sự tồn tại của một index case-insensitive là bằng chứng mọi regex được tăng tốc.

### Bài 15. Thiết kế API tìm kiếm theo yêu cầu

| Nhu cầu | Lựa chọn đầu tiên cần cân nhắc |
|---|---|
| Tên phải bằng nhau theo quy tắc tiếng Anh, bỏ qua hoa/thường | Equality + collation strength 2 + index tương thích |
| Tên cần so sánh bỏ qua dấu | Collation với strength phù hợp, test dữ liệu thật |
| Tìm mã `ORD-123` trong note | `$regexFind` |
| Lấy tất cả mã trong note | `$regexFindAll` + `$map` |
| Chỉ biết note có mã hay không | `$regexMatch` |
| Tách chuỗi tags CSV đơn giản | `$split`, `$map`, `$trim`, `$filter` |
| Đếm byte UTF-8 | `$strLenBytes` |
| Đếm code point | `$strLenCP` |
| Sắp xếp tên theo ngôn ngữ | `$sort` với collation phù hợp |
| Tìm kiếm nhập tự do, fuzzy/đa ngôn ngữ lớn | Cần thiết kế search riêng và benchmark |

## 28. Tổng kết

MongoDB Aggregation cung cấp nhiều biểu thức xử lý chuỗi, nhưng nên chọn công cụ dựa trên **ý nghĩa phép toán**:

- **Ghép/tách/làm sạch:** `$concat`, `$split`, `$trim`, `$ltrim`, `$rtrim`.
- **Độ dài/vị trí/cắt:** `$strLenBytes`/`$strLenCP`, `$indexOfBytes`/`$indexOfCP`, `$substrBytes`/`$substrCP`. Luôn thống nhất đơn vị byte hay code point.
- **Thay chuỗi literal:** `$replaceOne` và `$replaceAll`; không phải regex replacement và không áp dụng collation để bỏ dấu/case.
- **Regex:** `$regexMatch` trả boolean; `$regexFind` trả match đầu; `$regexFindAll` trả mọi match. Chúng không collation-aware.
- **So sánh/sort theo ngôn ngữ:** `$eq`, equality `$match`, `$sort` và `$group` sử dụng collation khi phù hợp. Cần chọn locale, strength và index tương thích.
- **Unicode:** `$toLower`/`$toUpper`/`$strcasecmp` không thay thế chính sách chuẩn hóa Unicode đa ngôn ngữ; `$strLenCP` cũng không đếm đầy đủ grapheme clusters.
- **Dữ liệu đầu vào:** xử lý null/missing và sai kiểu một cách tường minh; không biến lỗi input thành kết quả nghiệp vụ sai.
- **Hiệu năng:** Regex và các pipeline xử lý chuỗi có chi phí thực thi; index case-insensitive không tự làm mọi regex `/i` nhanh hơn.
- **Bảo mật và API:** giữ filter theo tenant/phạm vi quyền, hạn chế pattern không tin cậy, và xác định rõ output mong muốn.

Một pipeline xử lý chuỗi tốt phải **đúng quy tắc so sánh**, **đúng đơn vị Unicode**, **an toàn với dữ liệu biên** và **phù hợp với khối lượng truy vấn thực tế**. Hiểu giới hạn của collation là chìa khóa để không đánh đồng “bằng nhau theo ngôn ngữ” với “khớp biểu thức chính quy” hay “thay thế chuỗi con”.
