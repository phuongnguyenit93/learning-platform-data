# Cập nhật trường lồng nhau mà không thay thế nhầm document con trong MongoDB

Trong MongoDB, một document có thể chứa nhiều **embedded document** (document lồng nhau) và array. Khi chỉ cần đổi một field nhỏ, chẳng hạn thành phố trong địa chỉ giao hàng, câu lệnh update phải chỉ đúng **đường dẫn field**. Nếu cập nhật nguyên object cha, MongoDB có thể thay thế toàn bộ object con và làm mất các field không xuất hiện trong dữ liệu mới.

Ví dụ, từ địa chỉ:

~~~javascript
{
  address: {
    city: "Hà Nội",
    district: "Ba Đình",
    postalCode: "100000"
  }
}
~~~

Muốn đổi **city** sang **Đà Nẵng** và giữ nguyên **district**, **postalCode**, hãy dùng **$set** kết hợp **dot notation**:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "address.city": "Đà Nẵng" } }
);
~~~

Nếu viết:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { address: { city: "Đà Nẵng" } } }
);
~~~

thì **address** được thay bằng object mới chỉ có **city**. Hai lệnh đều hợp lệ; khác biệt nằm ở **ranh giới field được gán**.

Bài học này tập trung vào cách cập nhật field lồng nhau an toàn trong MongoDB, từ dot notation cơ bản đến array filters, điều kiện ghi đồng thời và cách tạo patch trong Java.

## 1. Vì sao cập nhật document con dễ gây mất dữ liệu?

Document BSON có cấu trúc cây. Mỗi field có thể chứa giá trị đơn, document con hoặc array.

~~~text
Collection: users
└── Document: _id = "U-1001"
    ├── fullName
    ├── profile
    │   ├── displayName
    │   ├── address
    │   │   ├── city
    │   │   ├── district
    │   │   ├── postalCode
    │   │   └── geo
    │   │       ├── lat
    │   │       └── lon
    │   └── preferences
    │       ├── language
    │       └── emailNotifications
    ├── contacts[]
    └── audit
        ├── version
        └── updatedAt
~~~

Có ba mức cập nhật khác nhau:

| Đường dẫn dùng với $set | Phạm vi giá trị bị gán | Điều có thể mất |
| --- | --- | --- |
| **profile.address.city** | Chỉ field city bên trong address | Các field anh em của city được giữ |
| **profile.address** | Toàn bộ document address | district, postalCode, geo nếu không có trong object mới |
| **profile** | Toàn bộ document profile | address, preferences và các field profile khác không có trong object mới |

MongoDB không tự hiểu rằng object JavaScript trong **$set** là một bản vá từng field theo kiểu deep merge. **Gán một object là thay giá trị tại đúng đường dẫn được chỉ định**, dù giá trị đó là object lớn hay nhỏ.

## 2. Tạo bộ dữ liệu minh họa

Các lệnh dưới đây dùng **mongosh** và một database thử nghiệm riêng:

~~~javascript
use nested_update_lab

db.users.insertOne({
  _id: "U-1001",
  fullName: "Nguyễn Minh An",
  profile: {
    displayName: "Minh An",
    address: {
      city: "Hà Nội",
      district: "Ba Đình",
      postalCode: "100000",
      geo: {
        lat: 21.034,
        lon: 105.815
      }
    },
    preferences: {
      language: "vi",
      emailNotifications: true
    }
  },
  contacts: [
    {
      type: "home",
      phone: "0900000001",
      verified: true
    },
    {
      type: "work",
      phone: "0900000002",
      verified: false
    }
  ],
  audit: {
    version: 1,
    updatedAt: ISODate("2026-01-01T00:00:00Z")
  }
});
~~~

Ví dụ giả định collection chưa có document có **_id = "U-1001"**. Nếu chạy lại lệnh insert, MongoDB báo lỗi duplicate key. Trong môi trường thử nghiệm, có thể xóa riêng document mẫu bằng **deleteOne({ _id: "U-1001" })** rồi thêm lại; không cần xóa cả collection.

Xem document:

~~~javascript
db.users.findOne({ _id: "U-1001" });
~~~

Với cấu trúc này:

- **profile** là document lồng nhau.
- **profile.address** là một document con sâu hơn.
- **profile.address.geo** chứa hai field tọa độ.
- **contacts** là array gồm nhiều embedded document.
- **audit.version** dùng minh họa kiểm soát cập nhật đồng thời.

## 3. Cập nhật một field con bằng dot notation

**Dot notation** sử dụng dấu chấm để diễn tả đường đi qua các field của document lồng nhau:

~~~text
profile.address.city
│       │       └── field cần gán
│       └── embedded document address
└── embedded document profile
~~~

Thay thành phố:

~~~javascript
const result = db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address.city": "Đà Nẵng"
    }
  }
);

printjson(result);
~~~

Đọc phần address sau update:

~~~javascript
db.users.findOne(
  { _id: "U-1001" },
  { _id: 0, "profile.address": 1 }
);
~~~

Kết quả về mặt cấu trúc:

~~~javascript
{
  profile: {
    address: {
      city: "Đà Nẵng",
      district: "Ba Đình",
      postalCode: "100000",
      geo: {
        lat: 21.034,
        lon: 105.815
      }
    }
  }
}
~~~

Chỉ **city** thay đổi; các field còn lại của **address** và **profile** không bị xóa bởi phép **$set** tại đường dẫn lá đó.

### 3.1. Vì sao tên đường dẫn phải là string?

Trong object JavaScript, tên field có dấu chấm cần được đặt trong dấu nháy:

~~~javascript
{
  $set: {
    "profile.address.city": "Đà Nẵng"
  }
}
~~~

Nếu viết cú pháp dạng:

~~~javascript
// Sai cú pháp JavaScript object literal:
{
  $set: {
    profile.address.city: "Đà Nẵng"
  }
}
~~~

JavaScript không coi **profile.address.city** là một key hợp lệ khi không có nháy. MongoDB driver nhận tên field cần cập nhật dưới dạng **string path**, ví dụ "profile.address.city".

### 3.2. Cập nhật nhiều field lá trong cùng một thao tác

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address.city": "Hồ Chí Minh",
      "profile.address.postalCode": "700000",
      "profile.preferences.language": "en"
    },
    $currentDate: {
      "audit.updatedAt": true
    },
    $inc: {
      "audit.version": 1
    }
  }
);
~~~

Một lệnh **updateOne** sửa nhiều field trên **cùng document**, và MongoDB áp dụng thao tác ghi đó nguyên tử ở phạm vi document. Những field không bị nhắm tới vẫn được giữ lại.

Lưu ý: cập nhật đồng thời **city** và **postalCode** không tự bảo đảm chúng là cặp giá trị địa lý đúng. **Atomicity** bảo đảm tính trọn vẹn của write, còn kiểm tra dữ liệu nghiệp vụ cần do ứng dụng hoặc schema validation thực hiện.

## 4. Khi nào $set thay thế nguyên document con?

MongoDB không tự deep merge hai object. Hãy so sánh hai câu lệnh.

### 4.1. Gán đúng field lá: giữ các field anh em

Document ban đầu:

~~~javascript
{
  profile: {
    address: {
      city: "Hà Nội",
      district: "Ba Đình",
      postalCode: "100000"
    },
    preferences: {
      language: "vi"
    }
  }
}
~~~

Cập nhật:

~~~javascript
{
  $set: {
    "profile.address.city": "Đà Nẵng"
  }
}
~~~

Kết quả:

~~~javascript
{
  profile: {
    address: {
      city: "Đà Nẵng",
      district: "Ba Đình",
      postalCode: "100000"
    },
    preferences: {
      language: "vi"
    }
  }
}
~~~

### 4.2. Gán nguyên field address: thay toàn bộ giá trị address

Cập nhật:

~~~javascript
{
  $set: {
    "profile.address": {
      city: "Đà Nẵng"
    }
  }
}
~~~

Kết quả:

~~~javascript
{
  profile: {
    address: {
      city: "Đà Nẵng"
    },
    preferences: {
      language: "vi"
    }
  }
}
~~~

Các field **district** và **postalCode** bị loại bỏ vì object mới không chứa chúng. **preferences** vẫn còn do thao tác chỉ gán **profile.address**, không gán cả **profile**.

### 4.3. Gán nguyên profile: tác động còn rộng hơn

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      profile: {
        address: {
          city: "Đà Nẵng"
        }
      }
    }
  }
);
~~~

Nếu thao tác này chạy trên document mẫu, **profile.displayName** và **profile.preferences** cũng mất. Sau đó muốn khôi phục cần có dữ liệu gốc hoặc backup phù hợp.

Quy tắc thực hành: **mức sâu nhất của đường dẫn được gán chính là phạm vi thay thế giá trị**. Hãy tạo path tới field cần đổi, không đưa cả object cha vào **$set** khi dữ liệu đầu vào chỉ là bản vá một phần.

## 5. $set khác replaceOne và lưu toàn bộ object như thế nào?

Hai cơ chế cập nhật thường gặp:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.city": "Đà Nẵng" } }
);
~~~

và:

~~~javascript
db.users.replaceOne(
  { _id: "U-1001" },
  {
    fullName: "Nguyễn Minh An",
    profile: {
      address: { city: "Đà Nẵng" }
    }
  }
);
~~~

Lệnh **replaceOne** thay thế **toàn bộ nội dung document** bằng replacement document (giữ _id theo quy tắc của replacement nếu _id không được cung cấp). Những field không có trong replacement, như **contacts**, **audit**, **profile.preferences**, sẽ không còn trong document sau thay thế.

| API / thao tác | Phạm vi thay thế | Thích hợp khi |
| --- | --- | --- |
| **updateOne** + $set trên path lá | Field tại path được chỉ định | Cập nhật một vài field |
| **updateOne** + $set trên object cha | Toàn bộ giá trị object cha | Chủ ý thay toàn bộ subtree |
| **replaceOne** | Toàn bộ document | Có bản thay thế đầy đủ và kiểm soát rõ |
| **findOneAndUpdate** + $set | Những field được chỉ định | Cần update rồi lấy document trước/sau |
| **findOneAndReplace** | Toàn bộ document | Cần thay cả document và lấy bản trước/sau |

Nguy cơ tương tự có thể xảy ra khi một ORM/ODM hoặc lớp repository gọi phương thức **save** để ghi lại đối tượng chỉ được nạp một phần. Tùy thư viện và API, save có thể đưa đến thao tác thay thế cả document hoặc ghi lại những giá trị mặc định/null ngoài dự kiến. Cần hiểu chính xác API đang gọi, không mặc định “save DTO chứa ba field” tương đương “patch ba field”.

## 6. Sự khác nhau giữa $set, $unset và gán null

Giả sử field **profile.address.postalCode** tồn tại.

### 6.1. Gán giá trị null

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address.postalCode": null
    }
  }
);
~~~

Field **postalCode** vẫn tồn tại, nhưng có giá trị BSON **null**.

### 6.2. Xóa field con

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $unset: {
      "profile.address.postalCode": ""
    }
  }
);
~~~

Lúc này **postalCode** không còn trong document. Hai lệnh có kết quả khác nhau:

~~~javascript
db.users.find({
  "profile.address.postalCode": { $exists: true }
});

db.users.find({
  "profile.address.postalCode": { $exists: false }
});
~~~

Điều kiện **$exists** giúp phân biệt field có tồn tại hay không; bản thân filter so sánh **null** trong MongoDB có thể khớp cả field null và field thiếu.

### 6.3. Không nên dùng $set toàn address để xóa một field

Nếu chỉ muốn bỏ postalCode, dùng **$unset** trên path đó. Việc đưa lại một object address chỉ có city và district sẽ thay cả subtree, dễ làm mất field mới được hệ thống khác bổ sung, chẳng hạn **geo**.

Ví dụ ứng dụng muốn xóa riêng **profile.address.geo.lon**:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $unset: {
      "profile.address.geo.lon": ""
    }
  }
);
~~~

Những field cùng cấp như **lat** vẫn được giữ.

## 7. Đường dẫn thiếu, giá trị null và kiểu dữ liệu không phù hợp

Dot notation có thể tạo đường dẫn lồng nhau khi các thành phần trung gian **chưa tồn tại** và MongoDB có thể xây dựng object cần thiết.

Ví dụ document:

~~~javascript
{ _id: "U-2001", fullName: "Bình" }
~~~

Cập nhật:

~~~javascript
db.users.updateOne(
  { _id: "U-2001" },
  {
    $set: {
      "profile.address.city": "Huế"
    }
  }
);
~~~

Khi document đó tồn tại và không có field **profile**, MongoDB có thể tạo cấu trúc:

~~~javascript
{
  _id: "U-2001",
  fullName: "Bình",
  profile: {
    address: {
      city: "Huế"
    }
  }
}
~~~

Nhưng nếu một thành phần trung gian **đã tồn tại dưới kiểu không phải document**, thao tác có thể thất bại. Ví dụ:

~~~javascript
{
  _id: "U-2002",
  profile: {
    address: null
  }
}
~~~

Yêu cầu:

~~~javascript
db.users.updateOne(
  { _id: "U-2002" },
  {
    $set: {
      "profile.address.city": "Huế"
    }
  }
);
~~~

Ở đây **address** là null nên MongoDB không thể đi xuyên qua nó như một embedded document thông thường. Với field đang là string, number hoặc array không phù hợp, vấn đề tương tự cũng có thể xảy ra. **Không nên coi dot notation là cơ chế tự sửa mọi kiểu dữ liệu sai**.

### 7.1. Chỉ update khi cấu trúc trung gian đúng kiểu

Với dữ liệu đã chuẩn hóa, có thể kiểm tra kiểu trước khi cập nhật:

~~~javascript
const result = db.users.updateOne(
  {
    _id: "U-2002",
    "profile.address": { $type: "object" }
  },
  {
    $set: {
      "profile.address.city": "Huế"
    }
  }
);

printjson(result);
~~~

Nếu **matchedCount = 0**, không có document đáp ứng filter, hoặc cấu trúc hiện tại không đúng điều kiện. Ứng dụng cần quyết định có migration, báo lỗi dữ liệu hay tạo cấu trúc mới theo nghiệp vụ.

### 7.2. Tạo object cha có chủ đích

Nếu trường hợp hợp lệ là **address: null** và nghiệp vụ muốn khởi tạo địa chỉ mới, có thể chủ động thay address bằng object đầy đủ:

~~~javascript
db.users.updateOne(
  {
    _id: "U-2002",
    "profile.address": null
  },
  {
    $set: {
      "profile.address": {
        city: "Huế",
        district: "",
        postalCode: null
      }
    }
  }
);
~~~

Lưu ý điều kiện **{ "profile.address": null }** thông thường có thể khớp cả field null và field thiếu. Nếu cần nhắm riêng BSON null, kết hợp điều kiện **$type: "null"**. Việc thay toàn bộ address trong trường hợp này là **chủ đích tạo mới một object**; khác với tình huống chỉ đổi city của địa chỉ đã có.

## 8. Cập nhật array chứa embedded document

Dot notation đối với object đơn giản chưa đủ khi đường dẫn đi qua array. Nếu document chứa:

~~~javascript
{
  _id: "U-1001",
  contacts: [
    { type: "home", phone: "0900000001", verified: true },
    { type: "work", phone: "0900000002", verified: false }
  ]
}
~~~

thì mục tiêu thường là đổi **phone của contact có type = "work"**, đồng thời giữ **type** và **verified**.

### 8.1. Positional operator $: phần tử array đầu tiên phù hợp

~~~javascript
db.users.updateOne(
  {
    _id: "U-1001",
    "contacts.type": "work"
  },
  {
    $set: {
      "contacts.$.phone": "0911111111"
    }
  }
);
~~~

Toán tử positional **$** đại diện cho **phần tử array đầu tiên khớp điều kiện** trong ngữ cảnh được hỗ trợ. Field **verified** của contact đó vẫn nguyên vẹn.

Khi filter liên quan nhiều array, điều kiện phức tạp hoặc mục tiêu là nhiều phần tử, vị trí phần tử qua **$** dễ trở nên khó hiểu. Lúc đó ưu tiên **arrayFilters**.

### 8.2. Filtered positional operator $[identifier]

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "contacts.$[contact].phone": "0911111111"
    }
  },
  {
    arrayFilters: [
      { "contact.type": "work" }
    ]
  }
);
~~~

**$[contact]** chọn phần tử trong array **contacts** thỏa filter **contact.type = "work"**. Nếu có nhiều contact thỏa, các phần tử phù hợp có thể cùng được cập nhật trong document.

Nếu mục tiêu nghiệp vụ là chỉ có **một** contact cho mỗi type, hãy bảo đảm quy ước đó trong cách ghi và mô hình dữ liệu. Toán tử update không tự tạo ràng buộc duy nhất cho giá trị type bên trong array.

### 8.3. All positional operator $[]: mọi phần tử

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "contacts.$[].verified": false
    }
  }
);
~~~

**$[]** tác động đến tất cả phần tử của array contacts. Nó khác **$[identifier]** vì không có điều kiện chọn từng phần tử.

### 8.4. Vị trí chỉ số cố định

Cũng có thể chỉ thẳng một chỉ số:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "contacts.0.phone": "0922222222"
    }
  }
);
~~~

Điều này sửa phần tử ở vị trí index 0 của array. Cách này chỉ phù hợp khi ứng dụng biết chắc vị trí đó mang ý nghĩa cần sửa. Nếu array có thể sắp xếp lại, thêm hoặc xóa phần tử, index cố định có thể đổi nhầm contact.

### 8.5. Gán cả phần tử array có thể làm mất field con

So sánh:

~~~javascript
// Giữ verified và type của contact tại vị trí 0.
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "contacts.0.phone": "0922222222" } }
);
~~~

và:

~~~javascript
// Thay nguyên object contact ở vị trí 0.
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "contacts.0": {
        phone: "0922222222"
      }
    }
  }
);
~~~

Lệnh thứ hai thay toàn bộ phần tử array bằng một object chỉ có **phone**. Nguy cơ mất field **type** và **verified** vẫn giống cập nhật nguyên embedded document.

### 8.6. Array lồng nhiều cấp

Giả sử đơn hàng có các nhóm giao hàng, mỗi nhóm có nhiều dòng sản phẩm:

~~~javascript
{
  _id: "ORD-5001",
  shipments: [
    {
      shipmentId: "S-01",
      items: [
        { sku: "BOOK-01", quantity: 1, note: "Bìa cứng" },
        { sku: "PEN-02", quantity: 2, note: "Màu xanh" }
      ]
    }
  ]
}
~~~

Chỉ sửa **note** cho item BOOK-01 trong shipment S-01:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-5001" },
  {
    $set: {
      "shipments.$[shipment].items.$[item].note": "Gói riêng"
    }
  },
  {
    arrayFilters: [
      { "shipment.shipmentId": "S-01" },
      { "item.sku": "BOOK-01" }
    ]
  }
);
~~~

Hai array filter xác định đúng cấp phần tử. Cách này giữ các field **quantity**, **sku** và những shipment/item không phù hợp.

## 9. Phân biệt update thường và update bằng aggregation pipeline

MongoDB hỗ trợ hai hình thức update:

~~~javascript
// Update document với toán tử $set.
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.city": "Đà Nẵng" } }
);
~~~

và:

~~~javascript
// Aggregation pipeline update.
db.users.updateOne(
  { _id: "U-1001" },
  [
    {
      $set: {
        "profile.address.city": "Đà Nẵng"
      }
    }
  ]
);
~~~

Ở hình thức thứ hai, **$set** là một **aggregation stage**. Trong ví dụ gán string thông thường, kết quả cập nhật field giống nhau. Nhưng pipeline hỗ trợ biểu thức aggregation và có cách đánh giá value khác update operators.

Ví dụ, nếu string dữ liệu thực sự bắt đầu bằng dấu **$**, pipeline có thể hiểu nó là biểu thức đường dẫn field. Dùng **$literal** khi muốn gán nguyên string:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  [
    {
      $set: {
        "profile.displayName": {
          $literal: "$admin"
        }
      }
    }
  ]
);
~~~

Với update thông thường **{ $set: { "profile.displayName": "$admin" } }**, chuỗi **"$admin"** là giá trị literal của toán tử cập nhật, không phải expression tham chiếu field.

### 9.1. Chủ động merge object bằng $mergeObjects

Đôi khi ứng dụng cần gộp một object mới với object cũ trên server. Aggregation có thể dùng **$mergeObjects**:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  [
    {
      $set: {
        "profile.address": {
          $mergeObjects: [
            "$profile.address",
            {
              city: "Đà Nẵng",
              postalCode: "550000"
            }
          ]
        }
      }
    }
  ]
);
~~~

Cách này giữ các field top-level khác bên trong **profile.address**, như **district** và **geo**, nếu các giá trị cũ có cấu trúc phù hợp.

Tuy nhiên, **$mergeObjects chỉ merge một cấp field**. Nếu object mới chứa **geo: { lat: ... }**, toàn bộ field **geo** cũ có thể bị thay bằng object mới và **lon** sẽ mất. Nó **không phải cơ chế deep merge vô hạn cấp**.

Với bản vá chỉ gồm vài field đã biết, dot notation vẫn là cách trực tiếp và dễ kiểm soát nhất.

### 9.2. Tránh cập nhật cả cha và con trong cùng một câu lệnh

Không viết:

~~~javascript
// Xung đột đường dẫn cập nhật.
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address": { city: "Huế" },
      "profile.address.postalCode": "530000"
    }
  }
);
~~~

Hai đường dẫn trên chồng lấn: một đường dẫn gán **profile.address**, đường dẫn kia gán field **postalCode** bên trong chính object đó. MongoDB sẽ báo lỗi xung đột path trong update thông thường.

Hãy chọn một mức rõ ràng:

~~~javascript
// Cập nhật từng field lá.
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address.city": "Huế",
      "profile.address.postalCode": "530000"
    }
  }
);
~~~

Hoặc cố ý thay toàn bộ **profile.address** bằng một object đầy đủ khi đó thực sự là yêu cầu nghiệp vụ.

## 10. Đường dẫn có dấu chấm khác field name chứa dấu chấm

Trong schema thông thường:

~~~javascript
{
  profile: {
    address: {
      city: "Hà Nội"
    }
  }
}
~~~

Đường dẫn **"profile.address.city"** có nghĩa đi qua ba cấp embedded document.

Nhưng MongoDB ở các phiên bản hỗ trợ còn có thể lưu **field name chứa dấu chấm**, ví dụ field top-level có tên nguyên văn **"profile.address.city"**:

~~~javascript
{
  "profile.address.city": "Hà Nội"
}
~~~

Hai cấu trúc này **khác nhau**. Trong update thông thường, dot notation mặc định được diễn giải thành **đường dẫn lồng nhau**, không phải tên field nguyên văn có dấu chấm.

Với field name đặc biệt, MongoDB cung cấp các biểu thức như **$getField** và **$setField** trong các phiên bản hỗ trợ. Ví dụ minh họa cập nhật field top-level tên literal **"profile.address.city"**:

~~~javascript
db.specialRecords.updateOne(
  { _id: "R-01" },
  [
    {
      $replaceWith: {
        $setField: {
          field: "profile.address.city",
          input: "$$ROOT",
          value: "Đà Nẵng"
        }
      }
    }
  ]
);
~~~

Đây là thao tác **đặt field name có dấu chấm nguyên văn ở cấp document**, không phải cập nhật object profile.address.

Với thiết kế ứng dụng thông thường, nên **tránh field name chứa dấu chấm hoặc bắt đầu bằng $** trừ khi có lý do rõ ràng. Dùng tên field bình thường và dot notation cho embedded document sẽ giảm nhầm lẫn giữa các driver và công cụ import/export.

## 11. Tạo patch đúng cách ở tầng ứng dụng

Một lỗi hay xảy ra khi API nhận JSON một phần rồi chuyển trực tiếp thành **$set**.

Ví dụ client gửi HTTP PATCH:

~~~json
{
  "profile": {
    "address": {
      "city": "Đà Nẵng"
    }
  }
}
~~~

Nếu backend làm:

~~~javascript
const patch = {
  profile: {
    address: {
      city: "Đà Nẵng"
    }
  }
};

db.users.updateOne(
  { _id: "U-1001" },
  { $set: patch }
);
~~~

thì **toàn bộ profile** có thể bị thay thành object chỉ chứa **address.city**. Các field **displayName**, **preferences**, **address.district**, **address.geo** có nguy cơ biến mất.

### 11.1. Chuyển đổi sang patch dạng đường dẫn lá

Khi API có hợp đồng rõ ràng, xây dựng update document bằng những path đã biết:

~~~javascript
const requestBody = {
  address: {
    city: "Đà Nẵng"
  },
  preferredLanguage: "en"
};

const setFields = {};

if (requestBody.address?.city !== undefined) {
  setFields["profile.address.city"] =
    requestBody.address.city;
}

if (requestBody.preferredLanguage !== undefined) {
  setFields["profile.preferences.language"] =
    requestBody.preferredLanguage;
}

db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: setFields
  }
);
~~~

Với cách này, input **city** được ánh xạ sang một field lá xác định. Không tự động đẩy nguyên requestBody hay object cha vào MongoDB.

Dùng **!== undefined** thay vì kiểm tra truthy để không bỏ qua các giá trị hợp lệ như **false**, **0** hoặc chuỗi rỗng. Với **null**, cần quyết định theo hợp đồng API: **gán BSON null** hay **xóa field bằng $unset**; hai hành vi không giống nhau.

Trong ví dụ thực tế, nếu không có field nào cần cập nhật, có thể trả về trạng thái no-op ở tầng ứng dụng thay vì phát lệnh update rỗng.

### 11.2. Không tạo path tùy ý từ key của client

Không nên cho client tùy ý gửi:

~~~json
{
  "fieldPath": "audit.version",
  "value": 999
}
~~~

rồi dùng thẳng **fieldPath** đó trong **$set**. Nếu ứng dụng không xác thực, client có thể sửa field nội bộ, thay field bảo mật hoặc gây xung đột cấu trúc.

Nên dùng **allowlist** những field được phép sửa:

~~~javascript
const allowedPaths = {
  city: "profile.address.city",
  postalCode: "profile.address.postalCode",
  language: "profile.preferences.language"
};

function buildUpdate(key, value) {
  const path = allowedPaths[key];

  if (!path) {
    throw new Error("Field không được phép cập nhật");
  }

  return {
    $set: {
      [path]: value
    }
  };
}
~~~

Cách làm này vừa giữ đúng ranh giới của document con, vừa giúp kiểm soát quyền cập nhật theo hợp đồng API.

### 11.3. JSON Merge Patch và JSON Patch có quy tắc riêng

Tên HTTP **PATCH** không tự đảm bảo backend sẽ deep merge JSON theo đúng ý muốn. Hai chuẩn patch phổ biến có semantics khác nhau:

- **JSON Merge Patch** mô tả việc hòa trộn object, trong đó giá trị null thường mang ý nghĩa loại bỏ member theo chuẩn tương ứng.
- **JSON Patch** là danh sách thao tác như add, replace, remove trên path JSON.

MongoDB **$set** không tự triển khai đầy đủ hai chuẩn này. Nếu API nhận một định dạng patch cụ thể, backend cần diễn giải đúng chuẩn đó rồi chuyển sang update phù hợp; không nên đồng nhất một cách máy móc request JSON với MongoDB update document.

## 12. Cập nhật trường lồng nhau bằng MongoDB Java Sync Driver

Trong Java Sync Driver, có thể dùng **Updates.set(...)** để chỉ rõ đường dẫn field, tương tự **$set** trong mongosh.

Ví dụ đầy đủ:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

public class UpdateNestedFieldExample {

    public static void main(String[] args) {
        try (MongoClient client =
                     MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase database =
                    client.getDatabase("nested_update_lab");

            MongoCollection<Document> users =
                    database.getCollection("users");

            Bson filter = Filters.eq("_id", "U-1001");

            Bson update = Updates.combine(
                    Updates.set(
                            "profile.address.city",
                            "Đà Nẵng"
                    ),
                    Updates.set(
                            "profile.preferences.language",
                            "vi"
                    ),
                    Updates.currentDate("audit.updatedAt"),
                    Updates.inc("audit.version", 1)
            );

            UpdateResult result = users.updateOne(filter, update);

            System.out.println(
                    "Matched: " + result.getMatchedCount()
            );
            System.out.println(
                    "Modified: " + result.getModifiedCount()
            );

            Document updated = users.find(filter).first();
            System.out.println(updated);
        }
    }
}
~~~

**Updates.set("profile.address.city", "Đà Nẵng")** chỉ gán field **city**. Nếu thay bằng:

~~~java
Updates.set(
    "profile.address",
    new Document("city", "Đà Nẵng")
)
~~~

thì MongoDB nhận yêu cầu **thay toàn bộ object address** bằng object mới chỉ có **city**. Driver Java không biến thao tác này thành deep merge.

### 12.1. Cập nhật có điều kiện bằng version

Nếu nhiều service sửa cùng user, nên cân nhắc kiểm soát version:

~~~java
Bson filter = Filters.and(
        Filters.eq("_id", "U-1001"),
        Filters.eq("audit.version", 3)
);

Bson update = Updates.combine(
        Updates.set("profile.address.city", "Huế"),
        Updates.inc("audit.version", 1)
);

UpdateResult result = users.updateOne(filter, update);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
            "Document không tồn tại hoặc version đã thay đổi"
    );
}
~~~

Nếu một writer khác đã tăng **audit.version** lên 4, update có điều kiện version 3 không khớp và không ghi đè thay đổi mới. Mô hình này chỉ tin cậy khi mọi thao tác cập nhật liên quan đều duy trì quy tắc tăng version.

### 12.2. Dùng Updates.unset cho field con

~~~java
users.updateOne(
    Filters.eq("_id", "U-1001"),
    Updates.unset("profile.address.postalCode")
);
~~~

Lệnh này xóa field **postalCode**, không xóa object **address** và không tự chuyển **postalCode** thành null.

### 12.3. Cập nhật phần tử array với ArrayFilters

Java Driver hỗ trợ **UpdateOptions.arrayFilters** để điều kiện hóa phần tử:

~~~java
import com.mongodb.client.model.UpdateOptions;
import java.util.List;

// users là MongoCollection<Document> đã được tạo.

UpdateOptions options = new UpdateOptions()
        .arrayFilters(
                List.of(new Document("contact.type", "work"))
        );

users.updateOne(
        Filters.eq("_id", "U-1001"),
        Updates.set(
                "contacts.$[contact].phone",
                "0911111111"
        ),
        options
);
~~~

Cách này cập nhật **phone** của phần tử contact phù hợp và giữ nguyên những field khác của phần tử đó.

## 13. Spring Data MongoDB: chú ý phân biệt update và save

Với Spring Data MongoDB, có thể dùng **MongoTemplate** và **Update.set** để cập nhật một path lồng nhau:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

// mongoTemplate được inject/cấu hình sẵn.

Query query = new Query(
        Criteria.where("_id").is("U-1001")
);

Update update = new Update()
        .set("profile.address.city", "Đà Nẵng")
        .currentDate("audit.updatedAt");

mongoTemplate.updateFirst(query, update, "users");
~~~

**Update.set("profile.address.city", ...)** biểu diễn ý định patch field lá. Nếu DTO chỉ chứa city, đây thường là hướng an toàn hơn việc tạo một entity thiếu những field khác rồi gọi **save** mà không biết thư viện sẽ phát thao tác gì.

Một số mẫu code Spring Data dùng:

~~~java
repository.save(userEntity);
~~~

Phương thức này lưu **entity** theo semantics của repository và mapping hiện tại. Khi đối tượng chỉ chứa một phần dữ liệu, việc save có thể làm mất các giá trị chưa được nạp hoặc bị đặt null. Ngoài ra, entity có trường **@Version** có thể có quy tắc optimistic locking riêng. Trước khi dùng **save** cho cập nhật một field lồng nhau, cần hiểu cách entity được tải và ánh xạ, cũng như lệnh ghi thực tế của framework.

### 13.1. Các lớp DTO nên diễn đạt đúng ý định

Ví dụ DTO dành riêng cho thay đổi thành phố:

~~~java
public record UpdateCityRequest(String city) {
}
~~~

Backend nên kiểm tra dữ liệu đầu vào và tạo lệnh:

~~~java
Update update = new Update()
        .set("profile.address.city", request.city());
~~~

Thao tác này rõ ràng hơn DTO chứa toàn bộ **Profile** nhưng chỉ truyền field **address.city**. API nên cho biết liệu một field vắng mặt có nghĩa “giữ nguyên” hay “xóa field”, và không nên để mapper ngầm thay toàn bộ object cha.

## 14. Cập nhật đồng thời: không làm mất field nhưng vẫn có thể mất thay đổi

Dùng dot notation giúp tránh xóa các field anh em một cách vô ý. Tuy nhiên, nó **không tự bảo vệ tất cả tình huống cập nhật đồng thời**.

Giả sử hai request cùng đọc:

~~~javascript
{
  profile: {
    address: {
      city: "Hà Nội",
      district: "Ba Đình"
    }
  }
}
~~~

Request A đổi **city** sang **Đà Nẵng** bằng:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.city": "Đà Nẵng" } }
);
~~~

Request B đổi **district** bằng:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.district": "Sơn Trà" } }
);
~~~

Vì hai lệnh nhắm vào **hai field lá khác nhau**, chúng không phải thay lại cả object address. Đây là ưu điểm thực tế khi nhiều phần hệ thống cập nhật những trường độc lập.

Nhưng nếu cả hai cùng sửa **city**:

~~~javascript
// Request A
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.city": "Đà Nẵng" } }
);

// Request B
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.city": "Huế" } }
);
~~~

mỗi write vẫn nguyên tử; giá trị cuối phụ thuộc thứ tự các write được áp dụng. Nếu hệ thống cần phát hiện cập nhật dựa trên dữ liệu cũ, dùng điều kiện giá trị hiện tại hoặc **version**.

### 14.1. Compare-and-set theo giá trị cũ

~~~javascript
const result = db.users.updateOne(
  {
    _id: "U-1001",
    "profile.address.city": "Hà Nội"
  },
  {
    $set: {
      "profile.address.city": "Đà Nẵng"
    }
  }
);

if (result.matchedCount === 0) {
  print("Giá trị đã đổi, hoặc user không tồn tại");
}
~~~

Điều kiện **city = "Hà Nội"** là một phần của thao tác update. Nếu document đã chuyển sang giá trị khác trước khi lệnh được áp dụng, lệnh sẽ không khớp và không tự ghi đè.

### 14.2. Optimistic locking bằng version

~~~javascript
const result = db.users.updateOne(
  {
    _id: "U-1001",
    "audit.version": 1
  },
  {
    $set: {
      "profile.address.city": "Đà Nẵng"
    },
    $inc: {
      "audit.version": 1
    }
  }
);
~~~

Nếu đúng document tồn tại với **version = 1**, update đổi city và tăng version trong cùng một write. Nếu version đã khác, **matchedCount = 0**. Ứng dụng có thể đọc lại dữ liệu, xử lý xung đột hoặc yêu cầu người dùng xác nhận.

Lưu ý: số version trong ví dụ giả định dữ liệu bắt đầu ở version 1; những bài tập đã chạy trước đó có thể đã tăng version. Khi chạy thực tế, cần dùng version vừa đọc được.

### 14.3. Một write sửa nhiều field là nguyên tử

Nếu ứng dụng phải cập nhật city và postalCode như một cặp:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address.city": "Đà Nẵng",
      "profile.address.postalCode": "550000"
    }
  }
);
~~~

Hai thay đổi cùng thuộc **một document**, nên một single-document update được áp dụng nguyên tử. Nếu tách thành hai lệnh, client khác có thể đọc trạng thái giữa hai lần update.

## 15. MatchedCount, ModifiedCount và lỗi ghi

Sau **updateOne**, ứng dụng nên phân biệt:

| Giá trị | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| **matchedCount = 0** | Không document nào khớp filter | Không có ID phù hợp, hoặc điều kiện version/path không còn đúng |
| **matchedCount = 1; modifiedCount = 1** | Có một document khớp và thực sự thay đổi | Update áp dụng thay đổi trên document |
| **matchedCount = 1; modifiedCount = 0** | Có document khớp nhưng không thay đổi nội dung | Ví dụ gán lại đúng giá trị cũ, hoặc thao tác không tạo thay đổi |
| **Exception / write error** | Yêu cầu lỗi | Có thể do cấu trúc path sai, validation, conflict, quyền hoặc lỗi server |

Ví dụ:

~~~javascript
const result = db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.city": "Đà Nẵng" } }
);

print("matched =", result.matchedCount);
print("modified =", result.modifiedCount);
~~~

Đừng kết luận **modifiedCount = 0** luôn có nghĩa update thất bại. Có thể field đã có đúng giá trị được gán; document khớp nhưng không cần thay đổi.

Mặt khác, không nên bỏ qua exception. Ví dụ field **profile.address** đang là null mà code cố truy cập sâu, hoặc cùng một update vừa gán cha vừa gán con, thao tác có thể báo lỗi. Lỗi ghi cần được phân loại và xử lý đúng nghiệp vụ; không tự sửa bằng cách thay cả object cha rồi bỏ mất dữ liệu.

## 16. Hướng dẫn chọn đường dẫn cập nhật

Trước khi viết update, hãy đi từ mục tiêu nghiệp vụ đến scope của đường dẫn.

| Nhu cầu | Ví dụ đường dẫn hoặc toán tử | Tác động |
| --- | --- | --- |
| Sửa thành phố | $set: { "profile.address.city": ... } | Chỉ city |
| Sửa postalCode | $set: { "profile.address.postalCode": ... } | Chỉ postalCode |
| Xóa postalCode | $unset: { "profile.address.postalCode": "" } | Bỏ một field |
| Đổi cờ thông báo | $set: { "profile.preferences.emailNotifications": false } | Chỉ một cờ |
| Tăng version | $inc: { "audit.version": 1 } | Tăng số trong document |
| Đổi phone contact loại work | contacts.$[c].phone + arrayFilters | Field phone của phần tử phù hợp |
| Đổi tất cả verified thành false | contacts.$[].verified | Field verified của mọi phần tử |
| Thay toàn bộ địa chỉ | $set: { "profile.address": fullAddress } | Mọi field trong address được thay |
| Thay toàn bộ user | replaceOne với document đầy đủ | Toàn bộ nội dung document được thay |

Trước khi truyền vào MongoDB, hãy xác định **đó là patch một phần hay replacement đầy đủ**. Một yêu cầu “đổi city” không cần gán lại **address**. Một yêu cầu “thay toàn bộ địa chỉ” có thể gán lại address, nhưng phải có đủ các field cần lưu theo hợp đồng dữ liệu.

### Những sai lầm phổ biến

**Sai lầm 1: Dùng $set với object cha cho bản vá một phần.**  
Field con không có trong object mới có thể mất. Chọn đường dẫn lá cụ thể.

**Sai lầm 2: Tưởng $set tự deep merge mọi cấp.**  
$set gán giá trị tại path; $mergeObjects cũng chỉ merge nông theo một cấp field.

**Sai lầm 3: Dùng replaceOne khi chỉ thay một giá trị.**  
Replacement document không đầy đủ làm mất những field khác.

**Sai lầm 4: Coi null là tương đương với field vắng mặt.**  
$set null vẫn giữ field; $unset mới xóa field.

**Sai lầm 5: Dùng chỉ số array cố định trong khi thứ tự có thể thay đổi.**  
Dùng positional operator hoặc arrayFilters với điều kiện định danh ổn định.

**Sai lầm 6: Không xử lý trường hợp parent đang là null hoặc sai kiểu.**  
Dot notation không thể đi xuyên qua mọi giá trị scalar/null; kiểm tra schema và dữ liệu.

**Sai lầm 7: Xây dựng update path trực tiếp từ input client.**  
Có nguy cơ sửa các field ứng dụng không cho phép; dùng allowlist và validate.

**Sai lầm 8: Coi mọi lệnh PATCH là deep merge.**  
HTTP PATCH phải có semantics rõ; mapper và driver không tự suy ra ý định nghiệp vụ.

**Sai lầm 9: Không kiểm tra matchedCount và xung đột đồng thời.**  
Lệnh có thể không khớp vì version khác hoặc document không tồn tại.

**Sai lầm 10: Đổi cả cha và con trong cùng update.**  
Các path chồng lấn có thể gây lỗi; chọn một scope cập nhật nhất quán.

## 17. Bài thực hành từng bước

Các bài tập giả định bạn đã có document **U-1001** theo dữ liệu mẫu ở mục 2. Nếu đã thực hiện các ví dụ làm thay đổi cấu trúc, hãy tạo lại document mẫu trong môi trường thử nghiệm trước khi so sánh kết quả.

### Bài 1: Chỉ đổi city

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address.city": "Hải Phòng"
    }
  }
);

db.users.findOne(
  { _id: "U-1001" },
  { _id: 0, "profile.address": 1 }
);
~~~

Hãy xác nhận về mặt dữ liệu:

1. **city** có giá trị mới.
2. **district** và **postalCode** vẫn tồn tại.
3. **geo.lat** và **geo.lon** không bị thay đổi.
4. Các field **profile.displayName**, **profile.preferences** cũng được giữ lại.

### Bài 2: Quan sát trường hợp thay nhầm object

Sử dụng một document thử nghiệm độc lập để tránh ảnh hưởng user mẫu:

~~~javascript
db.users.insertOne({
  _id: "U-TEMP",
  profile: {
    address: {
      city: "Hà Nội",
      district: "Ba Đình",
      postalCode: "100000"
    },
    preferences: {
      language: "vi"
    }
  }
});

db.users.updateOne(
  { _id: "U-TEMP" },
  {
    $set: {
      "profile.address": {
        city: "Đà Nẵng"
      }
    }
  }
);

db.users.findOne({ _id: "U-TEMP" });
~~~

Sau update, **district** và **postalCode** không còn trong address; **profile.preferences** vẫn còn. Hãy giải thích vì sao mức path được gán quyết định field nào mất.

Chạy lại với **$set: { profile: { address: { city: "Huế" } } }** trên một bản mẫu được khởi tạo đầy đủ để quan sát phạm vi thay thế rộng hơn.

### Bài 3: Xóa một field con, không xóa object cha

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $unset: {
      "profile.address.postalCode": ""
    }
  }
);

db.users.findOne(
  { _id: "U-1001" },
  { _id: 0, "profile.address": 1 }
);
~~~

Hãy so sánh kết quả với việc **$set postalCode: null**. Khi nào ứng dụng cần biểu diễn “người dùng chưa cung cấp” bằng field thiếu, và khi nào cần lưu null có chủ đích?

### Bài 4: Cập nhật một phần tử array

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "contacts.$[c].verified": true
    }
  },
  {
    arrayFilters: [
      { "c.type": "work" }
    ]
  }
);

db.users.findOne(
  { _id: "U-1001" },
  { _id: 0, contacts: 1 }
);
~~~

Kiểm tra chỉ những contact có **type = "work"** nhận giá trị **verified = true**, còn số điện thoại và các field khác giữ nguyên.

### Bài 5: Update có điều kiện version

~~~javascript
const before = db.users.findOne({ _id: "U-1001" });
const currentVersion = before.audit.version;

const result = db.users.updateOne(
  {
    _id: "U-1001",
    "audit.version": currentVersion
  },
  {
    $set: {
      "profile.address.city": "Huế"
    },
    $inc: {
      "audit.version": 1
    }
  }
);

printjson(result);
~~~

Chạy lại **cùng update filter với currentVersion cũ** và quan sát **matchedCount = 0**. Giải thích cách version ngăn một request dựa trên dữ liệu cũ ghi đè thay đổi mới.

### Bài 6: Tự chọn patch hay replace

Một API nhận yêu cầu:

~~~json
{
  "shippingAddress": {
    "city": "Đà Nẵng"
  }
}
~~~

Document order hiện tại:

~~~javascript
{
  _id: "ORD-1001",
  shippingAddress: {
    recipient: "Nguyễn An",
    city: "Hà Nội",
    street: "12 Phố Huế",
    instructions: "Gọi trước khi giao"
  },
  status: "CONFIRMED"
}
~~~

Hãy viết:

1. Lệnh chỉ cập nhật **shippingAddress.city**, giữ các field **recipient**, **street** và **instructions**.
2. Lệnh xóa riêng **shippingAddress.instructions**.
3. Lệnh thay **toàn bộ shippingAddress** khi nghiệp vụ yêu cầu một replacement đầy đủ.
4. Điều kiện bổ sung để không cho thay địa chỉ khi **status = "DELIVERED"**.
5. Cách phát hiện xung đột khi hai nhân viên cùng cập nhật địa chỉ.

Một hướng cho câu 1 và 4:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: { $ne: "DELIVERED" }
  },
  {
    $set: {
      "shippingAddress.city": "Đà Nẵng"
    }
  }
);
~~~

Trong ví dụ này, **$ne** chỉ biểu diễn điều kiện lọc theo status, chưa thay thế kiểm tra phân quyền và quy tắc nghiệp vụ đầy đủ.

## 18. Nguyên tắc ghi nhớ

Khi cần đổi một field lồng sâu trong MongoDB, hãy xác định **đường dẫn nhỏ nhất cần thay đổi**. Một lệnh:

~~~javascript
{ $set: { "parent.child.leaf": newValue } }
~~~

chỉ gán field **leaf**, trong khi:

~~~javascript
{ $set: { "parent.child": { leaf: newValue } } }
~~~

thay **toàn bộ giá trị của child**. Các field trước đó nằm dưới child nhưng không có trong object mới có thể mất.

Khi đường dẫn đi qua array, chọn phần tử bằng **$**, **$[]** hoặc **$[identifier]** phù hợp. Khi nhiều writer cùng sửa, kết hợp điều kiện trên giá trị hiện tại hoặc **version** để tránh ghi đè ngoài ý muốn. Ở tầng Java và API, tạo update từ **allowlist các field lá** thay vì gửi trực tiếp một object cha chưa đầy đủ.

Việc sử dụng đúng dot notation giúp giữ nguyên dữ liệu không liên quan và làm rõ phạm vi thay đổi, trong khi việc kiểm tra schema, quyền cập nhật và điều kiện đồng thời đảm bảo thao tác đáp ứng đúng nghiệp vụ.

## Tài liệu tham khảo

- [MongoDB Manual — $set](https://www.mongodb.com/docs/manual/reference/operator/update/set/)
- [MongoDB Manual — $unset](https://www.mongodb.com/docs/manual/reference/operator/update/unset/)
- [MongoDB Manual — Dot Notation](https://www.mongodb.com/docs/manual/core/document/)
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/)
- [MongoDB Manual — Array Update Operators](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/)
- [MongoDB Manual — Updates with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
