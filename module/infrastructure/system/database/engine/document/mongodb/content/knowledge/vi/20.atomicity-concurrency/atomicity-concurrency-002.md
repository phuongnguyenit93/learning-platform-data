# Tránh mất cập nhật bằng toán tử nguyên tử thay cho đọc rồi ghi trong MongoDB

Trong hệ thống nhiều người dùng, hai request có thể đọc **cùng một trạng thái document**, tự tính giá trị mới và ghi lại gần như đồng thời. Nếu cả hai đều ghi đè bằng giá trị đã tính từ dữ liệu cũ, một thay đổi có thể biến mất. Đây là tình huống **lost update – mất cập nhật**.

MongoDB cung cấp các **toán tử cập nhật nguyên tử** như **$inc**, **$set**, **$min**, **$max**, **$addToSet**, **$pull** và khả năng gắn **điều kiện vào update filter**. Nhờ vậy, nhiều quy tắc nghiệp vụ có thể được diễn đạt thành **một thao tác ghi trực tiếp trên server**, thay vì chuỗi đọc → sửa trong bộ nhớ ứng dụng → ghi lại.

Nguyên tắc chủ đạo:

> **Nếu một giá trị có thể được biến đổi bằng một toán tử update trên document hiện tại, hãy thực hiện phép biến đổi ở server trong cùng một lệnh ghi. Đừng đọc giá trị cũ về ứng dụng chỉ để tính rồi $set lại kết quả.**

Tuy nhiên, **atomicity không có nghĩa mọi xung đột nghiệp vụ đều được tự giải quyết**. Hai lệnh $set vào cùng một field vẫn có thể ghi đè nhau theo thứ tự thực thi. Những phép cập nhật cần so sánh trạng thái cũ, bảo toàn bất biến nghiệp vụ hoặc sửa nhiều document phải dùng thêm **conditional update, optimistic concurrency control** hoặc transaction thích hợp.

Bài học giải thích cơ chế, ví dụ mongosh, Java Sync Driver, các tình huống tranh chấp và cách thiết kế thao tác ghi an toàn trong MongoDB.

## 1. Lost update xuất hiện như thế nào?

Giả sử document lưu tổng lượt xem:

~~~javascript
{
  _id: "ARTICLE-01",
  views: 100
}
~~~

Hai request A và B cùng muốn tăng views thêm một đơn vị.

~~~text
A đọc views = 100
B đọc views = 100

A tính 100 + 1 = 101
B tính 100 + 1 = 101

A ghi views = 101
B ghi views = 101

Kết quả cuối: 101
Kết quả mong muốn: 102
~~~

Mỗi lần ghi riêng lẻ có thể thành công. Vấn đề là **giá trị được gán xuất phát từ bản đọc cũ**, không phản ánh mọi thay đổi vừa xảy ra.

### 1.1. Mẫu code dễ gây mất cập nhật

~~~javascript
const article = db.articles.findOne({
  _id: "ARTICLE-01"
});

const newViews = article.views + 1;

db.articles.updateOne(
  { _id: "ARTICLE-01" },
  {
    $set: {
      views: newViews
    }
  }
);
~~~

Đoạn này có thể chạy đúng khi chỉ một request ghi. Trong môi trường cạnh tranh, **findOne** và **updateOne** là hai hoạt động tách biệt. Giữa chúng, writer khác có thể đã tăng views.

**$set tự nó vẫn được thực hiện nguyên tử trên document**. Lost update là hậu quả của việc ứng dụng gửi lên một giá trị tính từ dữ liệu lỗi thời.

### 1.2. Cách đúng với $inc

~~~javascript
db.articles.updateOne(
  { _id: "ARTICLE-01" },
  {
    $inc: {
      views: 1
    }
  }
);
~~~

Mỗi writer yêu cầu server **tăng giá trị hiện hành thêm một**.

~~~text
Ban đầu: views = 100

A: $inc views +1  -> views = 101
B: $inc views +1  -> views = 102

Cuối cùng: views = 102
~~~

Không request nào phải đọc số cũ, tự tính 101 rồi cố gán trở lại.

## 2. Atomicity trong MongoDB bảo đảm điều gì?

Một write trên **một document** được áp dụng nguyên tử. Nếu thao tác update thay nhiều field của cùng document, các thay đổi đó được thực thi như một đơn vị.

~~~javascript
db.accounts.updateOne(
  { _id: "ACC-01" },
  {
    $inc: {
      balanceCents: -1500,
      purchaseCount: 1
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

Đây là **một thao tác ghi** trên account document, không phải ba write độc lập.

| Tình huống | Phạm vi nguyên tử |
| --- | --- |
| **updateOne** sửa một document | Một document |
| **findOneAndUpdate** | Tìm và sửa một document trong thao tác tương ứng |
| **updateMany** | Mỗi document nguyên tử; cả tập không tự all-or-nothing |
| **bulkWrite** có nhiều operation | Không mặc nhiên là transaction cho cả nhóm |
| Hai **updateOne** trên hai document | Không tự nguyên tử chung |
| Multi-document transaction | Có thể nhóm nhiều write vào một giao dịch khi dùng đúng |

**Một API call không mặc nhiên là transaction đa document.** Nếu updateMany sửa được một số document rồi gặp lỗi, ứng dụng có thể phải xử lý trạng thái hoàn thành một phần.

### 2.1. Atomicity không tự ngăn last-write-wins

~~~javascript
// Request A:
db.users.updateOne(
  { _id: "U-01" },
  { $set: { nickname: "An" } }
);

// Request B:
db.users.updateOne(
  { _id: "U-01" },
  { $set: { nickname: "Bình" } }
);
~~~

Mỗi update đều nguyên tử. Nhưng nickname cuối cùng phụ thuộc thứ tự write được áp dụng. Nếu nghiệp vụ cần phát hiện writer khác đã sửa dữ liệu, dùng **CAS hoặc version**.

### 2.2. Cập nhật field lá thay vì thay cả object

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  { $set: { "profile.city": "Huế" } }
);

db.users.updateOne(
  { _id: "U-01" },
  { $set: { "profile.language": "en" } }
);
~~~

Hai lệnh gán hai field lá độc lập. Ngược lại:

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $set: {
      profile: {
        language: "en"
      }
    }
  }
);
~~~

gán lại toàn bộ profile, có thể làm mất city đã được writer khác cập nhật. **Đường dẫn update phải đúng mức field cần sửa.**

## 3. Tạo bộ dữ liệu thực hành

Sử dụng database thử nghiệm **atomic_concurrency_lab**. Chỉ chạy các lệnh drop trong môi trường học tập vì chúng xóa collection.

~~~javascript
use atomic_concurrency_lab

db.counters.drop();
db.products.drop();
db.orders.drop();
db.accounts.drop();
db.users.drop();

db.counters.insertOne({
  _id: "PAGE-01",
  views: NumberLong(100),
  likes: NumberLong(20),
  version: NumberLong(1)
});

db.products.insertMany([
  {
    _id: "SKU-BOOK-01",
    name: "Sách MongoDB",
    available: 10,
    reserved: 0,
    version: 1
  },
  {
    _id: "SKU-PEN-02",
    name: "Bút viết",
    available: 3,
    reserved: 0,
    version: 1
  }
]);

db.orders.insertOne({
  _id: "ORD-1001",
  status: "PENDING",
  totalCents: NumberLong(150000),
  paymentAttempts: 0,
  tags: ["new"],
  events: [],
  version: 1
});

db.accounts.insertMany([
  {
    _id: "ACC-A",
    balanceCents: NumberLong(100000),
    version: 1
  },
  {
    _id: "ACC-B",
    balanceCents: NumberLong(50000),
    version: 1
  }
]);

db.users.insertOne({
  _id: "U-01",
  profile: {
    city: "Hà Nội",
    language: "vi"
  },
  favoriteCategories: ["books"],
  version: 1
});
~~~

Các ví dụ tài khoản lưu giá trị **balanceCents** dưới dạng số nguyên theo đơn vị nhỏ nhất giả định. Với hệ thống tiền tệ thật, phải chọn đơn vị và kiểu dữ liệu chính xác; MongoDB cũng hỗ trợ Decimal128 nếu nghiệp vụ cần số thập phân.

## 4. $inc: tăng hoặc giảm trên server

**$inc** là toán tử quan trọng nhất khi muốn tránh lost update cho bộ đếm.

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  {
    $inc: {
      views: NumberLong(1)
    }
  }
);
~~~

Giảm likes:

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  {
    $inc: {
      likes: NumberLong(-1)
    }
  }
);
~~~

Đồng thời tăng views và likes:

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  {
    $inc: {
      views: NumberLong(1),
      likes: NumberLong(1)
    }
  }
);
~~~

### 4.1. Vì sao $inc tránh lost update?

| Cách viết | Giá trị request gửi | Khả năng mất cập nhật |
| --- | --- | --- |
| Đọc count = 10 rồi $set count = 11 | Giá trị tuyệt đối 11 | Hai request cùng đọc 10 có thể đều ghi 11 |
| **$inc count +1** | Delta +1 | Hai write hợp lệ đều đóng góp một lần tăng |
| **$inc count -2** | Delta -2 | Phép trừ nguyên tử, nhưng phải kiểm tra không vượt ngưỡng |

### 4.2. Khi field chưa có hoặc có null

Nếu field chưa tồn tại, $inc có thể tạo field với giá trị delta:

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  { $inc: { downloads: 1 } }
);
~~~

Nếu field có **null** hoặc kiểu không tương thích với phép cộng, $inc có thể báo lỗi. Đừng tự mặc định null tương đương 0; dùng schema validation, migration hoặc chuyển đổi có chủ đích.

### 4.3. Atomic increment không tự giới hạn giá trị

~~~javascript
db.products.updateOne(
  { _id: "SKU-PEN-02" },
  { $inc: { available: -5 } }
);
~~~

Nếu available ban đầu là 3, việc giảm 5 có thể tạo ra available = -2. Atomicity không tự bảo đảm **tồn kho không âm**.

Muốn giữ một bất biến nghiệp vụ, đưa điều kiện cần kiểm tra vào filter của **cùng update**.

## 5. Conditional update: điều kiện và thay đổi trong một lệnh

Yêu cầu giữ chỗ 2 sản phẩm khi available ≥ 2:

~~~javascript
const quantity = 2;

const result = db.products.updateOne(
  {
    _id: "SKU-PEN-02",
    available: { $gte: quantity }
  },
  {
    $inc: {
      available: -quantity,
      reserved: quantity
    }
  }
);

printjson(result);
~~~

Điều kiện **available ≥ quantity** được kiểm tra khi MongoDB áp dụng thao tác ghi. Nếu writer khác đã trừ tồn kho, filter có thể không còn match.

### 5.1. Hai request tranh sản phẩm cuối

~~~text
Ban đầu: available = 3
A muốn 2 sản phẩm
B muốn 2 sản phẩm

A:
  điều kiện available >= 2 đúng
  trừ 2 -> available = 1
  matchedCount = 1

B:
  điều kiện available >= 2 sai
  không ghi
  matchedCount = 0

Không bán vượt quá 3 sản phẩm.
~~~

Với mô hình đọc ở client rồi ghi đè:

~~~text
A đọc 3 -> thấy đủ
B đọc 3 -> thấy đủ
A ghi available = 1
B ghi available = 1

Hai request có thể đều tin rằng đã giữ chỗ 2,
trong khi field available chỉ còn 1.
~~~

### 5.2. matchedCount cần được diễn giải đúng

~~~javascript
if (result.matchedCount === 1) {
  print("Giữ chỗ thành công");
} else {
  print("Sản phẩm không tồn tại hoặc tồn kho không đủ");
}
~~~

**matchedCount = 0** có thể do không có ID phù hợp **hoặc** available không đủ. Ứng dụng có thể đọc lại để hiển thị thông báo cụ thể, nhưng không được dùng lần đọc đó làm cơ sở cho một phép trừ không điều kiện.

### 5.3. Kết hợp status với tồn kho

~~~javascript
db.products.updateOne(
  {
    _id: "SKU-BOOK-01",
    status: "ACTIVE",
    available: { $gte: 2 }
  },
  {
    $inc: { available: -2 }
  }
);
~~~

Dữ liệu mẫu chưa có status; cần bổ sung status = ACTIVE trước nếu muốn lệnh match. Ví dụ minh họa rằng **mọi điều kiện nghiệp vụ quan trọng** có thể được đưa vào filter cùng thao tác.

### 5.4. Cập nhật nhiều field phụ thuộc trong một write

~~~javascript
db.products.updateOne(
  {
    _id: "SKU-BOOK-01",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2,
      reserved: 2,
      version: 1
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

Việc giảm available, tăng reserved, tăng version và cập nhật thời gian thuộc một thao tác nguyên tử trên document sản phẩm.

Nếu tách:

~~~javascript
db.products.updateOne(
  { _id: "SKU-BOOK-01" },
  { $inc: { available: -2 } }
);

db.products.updateOne(
  { _id: "SKU-BOOK-01" },
  { $inc: { reserved: 2 } }
);
~~~

process có thể dừng giữa hai write hoặc writer khác đọc được trạng thái trung gian. Nếu các field cùng thuộc một invariant của một document, nên kết hợp trong một update.

## 6. $min và $max: không đọc rồi so sánh thủ công

Một số phép cập nhật chỉ cần giữ giá trị thấp nhất hoặc cao nhất từng quan sát.

Giả sử có:

~~~javascript
{
  _id: "SKU-01",
  bestPriceCents: 100000,
  maxObservedScore: 82
}
~~~

Mẫu có rủi ro:

~~~javascript
const product = db.products.findOne({
  _id: "SKU-01"
});

if (90000 < product.bestPriceCents) {
  db.products.updateOne(
    { _id: "SKU-01" },
    {
      $set: {
        bestPriceCents: 90000
      }
    }
  );
}
~~~

Trong lúc request đọc 100000 rồi chuẩn bị ghi 90000, writer khác có thể đã đặt bestPriceCents = 85000. Request chậm sau đó ghi lại 90000 và **làm mất giá tốt hơn**.

Dùng **$min**:

~~~javascript
db.products.updateOne(
  { _id: "SKU-01" },
  {
    $min: {
      bestPriceCents: 90000
    }
  }
);
~~~

Dùng **$max** cho điểm cao nhất:

~~~javascript
db.products.updateOne(
  { _id: "SKU-01" },
  {
    $max: {
      maxObservedScore: 95
    }
  }
);
~~~

### 6.1. Các toán tử biến đổi

| Toán tử | Quy tắc | Ví dụ |
| --- | --- | --- |
| **$inc** | Cộng delta | Lượt xem, số lượng |
| **$min** | Giữ giá trị thấp hơn | Giá thấp nhất từng thấy |
| **$max** | Giữ giá trị cao hơn | Điểm cao nhất, watermark |
| **$mul** | Nhân giá trị hiện tại | Hệ số tăng trưởng trong một số nghiệp vụ |
| **$currentDate** | Gán ngày giờ/timestamp hiện tại theo cấu hình | updatedAt |

$min/$max dựa trên quy tắc so sánh BSON, vì vậy nên thống nhất kiểu của field. Tránh dùng chúng để vô tình xử lý một field lúc là string, lúc là number.

### 6.2. Atomic không đồng nghĩa idempotent

~~~javascript
db.products.updateOne(
  { _id: "SKU-01" },
  {
    $mul: {
      multiplier: 2
    }
  }
);
~~~

Nếu cùng yêu cầu được áp dụng hai lần, multiplier bị nhân hai lần. $mul là phép biến đổi nguyên tử nhưng không tự bảo vệ khỏi retry lặp của nghiệp vụ.

## 7. $set với filter trạng thái: chuyển trạng thái an toàn

**$set** phù hợp để gán một trạng thái đích. Khi trạng thái chỉ được phép đổi từ một trạng thái cũ nhất định, đưa trạng thái cũ vào filter.

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "PENDING"
  },
  {
    $set: {
      status: "PAID"
    },
    $currentDate: {
      paidAt: true
    },
    $inc: {
      version: 1
    }
  }
);

printjson(result);
~~~

Nếu writer khác đã đổi status thành CANCELLED, filter status PENDING không khớp, nên request này không ghi đè CANCELLED thành PAID.

### 7.1. Hai transition cạnh tranh

~~~text
PENDING
  |       |
  v       v
PAID   CANCELLED
~~~

Hai request gửi:

~~~javascript
// Thanh toán:
db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "PENDING"
  },
  {
    $set: {
      status: "PAID"
    }
  }
);
~~~

~~~javascript
// Hủy:
db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "PENDING"
  },
  {
    $set: {
      status: "CANCELLED"
    }
  }
);
~~~

Khi một thao tác đã chuyển status ra khỏi PENDING, thao tác còn lại không match nữa. Cách này bảo vệ quy tắc **chỉ được chuyển từ PENDING một lần**.

### 7.2. Atomic transition không bao phủ email và API bên ngoài

Thành công của status = PAID không đồng nghĩa các bước sau cũng đã được thực hiện nguyên tử:

- Gửi email xác nhận.
- Tạo hóa đơn ở collection khác.
- Gọi hệ thống thanh toán.
- Gửi message tới broker.
- Trừ tồn kho ở một document khác.

Nếu cần những bước đó nhất quán, phải thiết kế transaction, outbox, idempotency hoặc quy trình phục hồi phù hợp.

## 8. Compare-and-set (CAS) theo giá trị cũ

Khi user sửa form từ bản dữ liệu đã đọc, có thể dùng **CAS** để chỉ ghi nếu field vẫn giữ giá trị cũ.

Giả sử user đọc city = Hà Nội, sau đó muốn đổi thành Huế:

~~~javascript
const result = db.users.updateOne(
  {
    _id: "U-01",
    "profile.city": "Hà Nội"
  },
  {
    $set: {
      "profile.city": "Huế"
    }
  }
);

if (result.matchedCount === 0) {
  print("Document không tồn tại hoặc city đã đổi");
}
~~~

Nếu writer khác đã đổi city thành Đà Nẵng, thao tác với điều kiện city = Hà Nội không match và không ghi đè.

### 8.1. CAS theo field phù hợp khi nào?

- Chỉ một field cần kiểm soát xung đột.
- Đầu vào là giá trị mới dựa trên giá trị cũ mà client đã thấy.
- Các field khác có thể được writer khác cập nhật độc lập.

### 8.2. Giới hạn ABA

~~~text
A đọc city = Hà Nội

B đổi city: Hà Nội -> Đà Nẵng
C đổi city: Đà Nẵng -> Hà Nội

A ghi với CAS city = Hà Nội
-> lại match
~~~

CAS chỉ nhìn thấy giá trị hiện tại, không phát hiện lịch sử đã đổi rồi trở lại giống cũ. Khi cần phát hiện **bất kỳ thay đổi nào** từ lần đọc, nên dùng field **version**.

## 9. Optimistic concurrency control bằng version

Document có thêm version:

~~~javascript
{
  _id: "U-01",
  profile: {
    city: "Hà Nội",
    language: "vi"
  },
  version: 1
}
~~~

Client đọc version = 1. Khi ghi:

~~~javascript
const expectedVersion = 1;

const result = db.users.updateOne(
  {
    _id: "U-01",
    version: expectedVersion
  },
  {
    $set: {
      "profile.city": "Huế"
    },
    $inc: {
      version: 1
    }
  }
);

if (result.matchedCount === 0) {
  print("Không tồn tại hoặc version đã đổi");
}
~~~

### 9.1. Hai request cùng đọc version

~~~text
Ban đầu: version = 1

A đọc version 1, muốn city = Huế
B đọc version 1, muốn language = en

A:
  filter version 1 -> khớp
  set city, inc version -> version 2

B:
  filter version 1 -> không khớp
  matchedCount = 0
~~~

B phải xử lý xung đột. Nếu hai field hoàn toàn độc lập, việc version chung gây thêm conflict là một **đánh đổi có chủ ý** để bảo đảm document được quản lý như một đơn vị.

### 9.2. Quy tắc để version đáng tin cậy

1. Khi đọc, trả về version hiện tại.
2. Khi ghi, dùng version đã đọc làm điều kiện.
3. Tăng version trong **cùng** update.
4. Kiểm tra matchedCount sau update.
5. Khi conflict, đọc lại và xử lý theo nghiệp vụ.

Nếu một writer sửa document **nhưng không tăng version**, cơ chế version không còn phát hiện đủ thay đổi. Các service, script bảo trì và repository update phải thống nhất quy tắc.

### 9.3. Không xử lý conflict bằng cách bỏ điều kiện

Sai:

~~~text
Update với version thất bại
-> bỏ filter version
-> dùng $set với dữ liệu cũ để ghi cho thành công
~~~

Động tác đó biến cơ chế phát hiện conflict thành vô nghĩa.

Tùy hệ thống, có thể trả **HTTP 409 Conflict**, hiển thị thay đổi mới để người dùng merge, hoặc tự retry có giới hạn sau khi tính lại trên trạng thái hiện hành nếu phép tính thật sự cho phép.

## 10. Không replace cả document chỉ để sửa một field

Một kiểu lost update nghiêm trọng xuất hiện khi ứng dụng nạp cả document vào DTO, sửa một field rồi gọi replaceOne:

~~~javascript
const order = db.orders.findOne({
  _id: "ORD-1001"
});

// Giả sử writer khác vừa thêm events.
order.status = "PAID";

db.orders.replaceOne(
  { _id: "ORD-1001" },
  order
);
~~~

Nếu dữ liệu order đã đọc là snapshot cũ, replacement có thể ghi đè **events**, **paymentAttempts** hoặc các field khác vừa thay đổi.

So sánh:

| Cách | Phạm vi | Bảo đảm thêm |
| --- | --- | --- |
| **replaceOne** bằng document đã đọc | Thay cả document | Dễ ghi đè dữ liệu ngoài ý muốn |
| **$set { status: "PAID" }** | Chỉ field status | Không xóa các field khác, nhưng status có thể last-write-wins |
| **$set status với filter status: PENDING** | Một field, có điều kiện | Bảo vệ transition |
| **$set status với filter version và $inc version** | Có điều kiện version | Phát hiện document đã được sửa |

### 10.1. Dot notation tránh thay cả document con

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $set: {
      "profile.city": "Huế"
    }
  }
);
~~~

Không gán cả **profile** nếu chỉ đổi city:

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $set: {
      profile: {
        city: "Huế"
      }
    }
  }
);
~~~

Lệnh thứ hai có thể làm mất profile.language vì nó **thay nguyên object profile**.

## 11. $addToSet và $pull: sửa array ở server

Giả sử user có:

~~~javascript
{
  _id: "U-01",
  favoriteCategories: ["books"]
}
~~~

Mẫu đọc rồi gán lại array:

~~~javascript
const user = db.users.findOne({
  _id: "U-01"
});

const updated = [
  ...user.favoriteCategories,
  "music"
];

db.users.updateOne(
  { _id: "U-01" },
  {
    $set: {
      favoriteCategories: updated
    }
  }
);
~~~

Nếu writer khác vừa thêm **sports** vào array, bản updated từ snapshot cũ có thể ghi đè và làm mất sports.

### 11.1. Dùng $addToSet

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $addToSet: {
      favoriteCategories: "music"
    }
  }
);
~~~

Request khác:

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $addToSet: {
      favoriteCategories: "sports"
    }
  }
);
~~~

Mỗi lệnh biến đổi array trên server, không cần gửi lại cả array cũ.

### 11.2. Thêm nhiều phần tử với $each

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $addToSet: {
      favoriteCategories: {
        $each: ["music", "sports"]
      }
    }
  }
);
~~~

### 11.3. Xóa phần tử với $pull

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $pull: {
      favoriteCategories: "books"
    }
  }
);
~~~

Nếu một writer khác đang thêm phần tử, $pull không cần gán lại nguyên array, nên ít rủi ro mất phần tử mới như cách đọc–ghi cả array.

### 11.4. $push vẫn có thể tạo trùng khi retry

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $push: {
      events: {
        type: "PAYMENT_ATTEMPTED",
        at: new Date()
      }
    }
  }
);
~~~

Nếu lệnh được **áp dụng hai lần**, array có thể có hai event. Điều đó đúng nếu là hai lần thử thanh toán khác nhau, nhưng sai nếu lần thứ hai chỉ là retry của cùng business request.

| Toán tử | Semantics |
| --- | --- |
| **$addToSet** | Thêm giá trị nếu chưa có theo quy tắc so sánh của MongoDB |
| **$push** | Thêm phần tử, có thể trùng |
| **$pull** | Loại phần tử phù hợp điều kiện |
| **$pop** | Loại phần tử ở đầu hoặc cuối array theo quy tắc operator |

**$addToSet không thay thế unique index cho mọi quan hệ nghiệp vụ** và không tự xóa những phần tử trùng đã tồn tại. Với embedded document, so sánh bằng nhau còn phụ thuộc cấu trúc và thứ tự field trong document theo quy tắc của MongoDB.

## 12. Cập nhật nguyên tử phần tử của array

Giả sử order có:

~~~javascript
{
  _id: "ORD-2001",
  items: [
    {
      sku: "BOOK-01",
      quantity: 1,
      fulfilled: false
    },
    {
      sku: "PEN-02",
      quantity: 2,
      fulfilled: false
    }
  ]
}
~~~

Tăng quantity của BOOK-01:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-2001",
    "items.sku": "BOOK-01"
  },
  {
    $inc: {
      "items.$.quantity": 1
    }
  }
);
~~~

Positional **$** đại diện cho phần tử array đầu tiên phù hợp điều kiện trong ngữ cảnh được hỗ trợ.

### 12.1. Dùng arrayFilters

~~~javascript
db.orders.updateOne(
  { _id: "ORD-2001" },
  {
    $inc: {
      "items.$[line].quantity": 1
    }
  },
  {
    arrayFilters: [
      { "line.sku": "BOOK-01" }
    ]
  }
);
~~~

Nếu nhiều phần tử thỏa điều kiện, filtered positional operator có thể sửa nhiều phần tử phù hợp. Nếu chỉ được tồn tại một dòng theo sku, cần bảo vệ quy tắc đó trong mô hình dữ liệu hoặc nghiệp vụ.

### 12.2. Không thay nguyên phần tử để sửa một field

Nguy hiểm:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-2001" },
  {
    $set: {
      "items.0": {
        quantity: 3
      }
    }
  }
);
~~~

Lệnh này thay toàn object item tại index 0, có thể xóa sku và fulfilled.

Thay vào đó:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-2001" },
  {
    $set: {
      "items.0.quantity": 3
    }
  }
);
~~~

Tuy nhiên, index cố định có thể đổi khi array được sắp xếp lại. Dùng định danh lineId hoặc sku và arrayFilters nếu đó là cách chọn phần tử đúng theo nghiệp vụ.

### 12.3. $elemMatch khi điều kiện phải cùng một phần tử

Không nên cho rằng:

~~~javascript
{
  "items.sku": "BOOK-01",
  "items.quantity": { $gte: 1 }
}
~~~

bắt buộc cả hai điều kiện thuộc cùng một item. Chúng có thể khớp những phần tử khác nhau trong array.

Dùng **$elemMatch** khi cần cùng phần tử:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-2001",
    items: {
      $elemMatch: {
        sku: "BOOK-01",
        quantity: { $gte: 1 }
      }
    }
  },
  {
    $inc: {
      "items.$.quantity": -1
    }
  }
);
~~~

Điều kiện và phép trừ được áp dụng trong một write, với filter bảo vệ quy tắc cho phần tử phù hợp.

## 13. Update bằng aggregation pipeline

Khi phép biến đổi phải tính từ **nhiều field hiện hành**, có thể dùng update pipeline để thực hiện phép tính ở server.

Giả sử invoice:

~~~javascript
{
  _id: "INV-01",
  quantity: 3,
  unitPriceCents: 12000,
  amountCents: 36000
}
~~~

Tính lại amount:

~~~javascript
db.invoices.updateOne(
  { _id: "INV-01" },
  [
    {
      $set: {
        amountCents: {
          $multiply: [
            "$quantity",
            "$unitPriceCents"
          ]
        }
      }
    }
  ]
);
~~~

Phép tính được đánh giá theo giá trị field hiện hành trong thao tác update trên document.

### 13.1. Khi chỉ tăng số, $inc đơn giản hơn

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  [
    {
      $set: {
        views: {
          $add: [
            { $ifNull: ["$views", 0] },
            1
          ]
        }
      }
    }
  ]
);
~~~

Pipeline này diễn đạt tăng views ở server, nhưng nếu field luôn là số hợp lệ, **$inc** rõ ràng và ngắn hơn.

### 13.2. Phân biệt $set stage và $set update operator

~~~javascript
// Update operator:
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $set: {
      status: "PAID"
    }
  }
);
~~~

~~~javascript
// Aggregation pipeline update:
db.orders.updateOne(
  { _id: "ORD-1001" },
  [
    {
      $set: {
        status: {
          $cond: [
            { $eq: ["$status", "PENDING"] },
            "PAID",
            "$status"
          ]
        }
      }
    }
  ]
);
~~~

Trong pipeline, $set là **aggregation stage** và các value có thể là expression. Với transition đơn giản, filter status PENDING + update operator thường dễ xác nhận matchedCount hơn.

### 13.3. Filter vẫn cần bảo vệ invariant

~~~javascript
db.products.updateOne(
  {
    _id: "SKU-BOOK-01",
    available: { $gte: 2 }
  },
  [
    {
      $set: {
        available: {
          $subtract: ["$available", 2]
        },
        reserved: {
          $add: ["$reserved", 2]
        }
      }
    }
  ]
);
~~~

Đây là một cách diễn đạt giữ chỗ nguyên tử với expression. Khi công thức chỉ là cộng/trừ hằng, dùng $inc cho cả available và reserved thường dễ hiểu hơn.

## 14. findOneAndUpdate: sửa và lấy kết quả trong cùng thao tác

Đôi khi ứng dụng cần số counter hoặc tồn kho **ngay sau chính thao tác của mình**.

Hai lệnh tách rời:

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  { $inc: { views: 1 } }
);

const current = db.counters.findOne({
  _id: "PAGE-01"
});
~~~

Trong khoảng giữa chúng, writer khác có thể tăng views tiếp, vì thế current.views không nhất thiết là giá trị sau **chỉ riêng** lần tăng của request đầu.

Dùng:

~~~javascript
const updated = db.counters.findOneAndUpdate(
  { _id: "PAGE-01" },
  {
    $inc: {
      views: 1
    }
  },
  {
    returnDocument: "after"
  }
);

printjson(updated);
~~~

Trong mongosh, returnDocument = "after" yêu cầu trả document sau update. Phương thức giúp thao tác sửa và lấy giá trị thuộc cùng find-and-modify operation.

**Giới hạn:** Một writer khác có thể cập nhật document ngay sau operation này, nên giá trị trả về không phải cam kết trạng thái sẽ giữ nguyên mãi tới khi client sử dụng.

### 14.1. Khi nào dùng updateOne hoặc findOneAndUpdate?

- Chỉ cần biết có match và update không: **updateOne** thường đủ.
- Cần giá trị trước/sau trong cùng operation: **findOneAndUpdate**.
- Cần sửa nhiều document all-or-nothing: đánh giá **transaction**, không dùng findOneAndUpdate để giả định nó tác động toàn collection.

## 15. Không có atomicity chung trên nhiều document

Chuyển 10.000 đơn vị nhỏ nhất từ account A sang B:

~~~javascript
db.accounts.updateOne(
  { _id: "ACC-A" },
  {
    $inc: {
      balanceCents: NumberLong(-10000)
    }
  }
);

db.accounts.updateOne(
  { _id: "ACC-B" },
  {
    $inc: {
      balanceCents: NumberLong(10000)
    }
  }
);
~~~

Mỗi update là nguyên tử trên một account. Nhưng **hai update không nguyên tử chung**. Process có thể dừng sau khi trừ A mà chưa cộng B.

Nếu hai bước phải commit cùng nhau, có thể dùng **multi-document transaction** trong topology và điều kiện hỗ trợ, hoặc thiết kế ledger, idempotency và đối soát theo yêu cầu nghiệp vụ.

### 15.1. Transaction minh họa

~~~javascript
const session = db.getMongo().startSession();

try {
  const database = session.getDatabase("atomic_concurrency_lab");
  const accounts = database.getCollection("accounts");

  session.startTransaction();

  const debit = accounts.updateOne(
    {
      _id: "ACC-A",
      balanceCents: { $gte: NumberLong(10000) }
    },
    {
      $inc: {
        balanceCents: NumberLong(-10000)
      }
    }
  );

  if (debit.matchedCount !== 1) {
    throw new Error("Không đủ tiền hoặc không có tài khoản A");
  }

  const credit = accounts.updateOne(
    { _id: "ACC-B" },
    {
      $inc: {
        balanceCents: NumberLong(10000)
      }
    }
  );

  if (credit.matchedCount !== 1) {
    throw new Error("Không có tài khoản B");
  }

  session.commitTransaction();
} catch (error) {
  session.abortTransaction();
  throw error;
} finally {
  session.endSession();
}
~~~

Ví dụ này thể hiện phạm vi transaction, **chưa** triển khai đầy đủ retry cho transient transaction errors, unknown commit result, idempotency và các quy tắc tài chính. Khi triển khai thật cần dùng API driver tương ứng và xử lý các trạng thái commit chưa rõ kết quả.

### 15.2. Khi nào không cần transaction?

Nếu invariant nằm trong một document, **một updateOne có điều kiện** thường đơn giản và ít overhead hơn. Transaction chỉ cần khi yêu cầu nhất quán thực sự vượt qua ranh giới document.

## 16. Retryable writes và idempotency

Xét tình huống:

~~~text
Client gửi $inc views +1
Server có thể đã cập nhật views
Kết nối đứt trước khi client nhận response
Client không biết chắc kết quả
~~~

Nếu ứng dụng tự phát một command mới và lại $inc +1, **cùng một lượt xem có thể được tính hai lần**.

### 16.1. Ba khái niệm khác nhau

- **Atomicity:** một update trên document được áp dụng như một đơn vị.
- **Idempotency:** cùng một business request được lặp lại mà không nhân đôi hiệu ứng.
- **Retryable write:** cơ chế driver/server hỗ trợ thử lại cùng logical write trong các điều kiện cụ thể.

$inc và $push **không idempotent nếu được áp dụng như những operation độc lập nhiều lần**.

### 16.2. Driver retry khác retry nghiệp vụ

MongoDB drivers có thể sử dụng session/transaction number để nhận diện retry của **cùng logical write** khi thao tác/topology được hỗ trợ.

Nhưng:

~~~text
Driver retry lại cùng logical write
~~~

khác:

~~~text
Ứng dụng nhận timeout rồi tạo một request nghiệp vụ mới
~~~

Không nên suy ra retryable writes của driver giải quyết mọi trường hợp trùng business command giữa nhiều lần khởi động process hoặc nhiều request HTTP.

### 16.3. Idempotency marker trong cùng document

Giả sử một job cộng rewardPoints = 10 chỉ một lần theo jobId:

~~~javascript
const jobId = "REWARD-2026-11";

db.accounts.updateOne(
  {
    _id: "ACC-A",
    appliedRewards: { $ne: jobId }
  },
  {
    $inc: {
      rewardPoints: 10
    },
    $addToSet: {
      appliedRewards: jobId
    }
  }
);
~~~

Filter và thay đổi nằm trong cùng atomic update. Nếu jobId đã có, operation mới không match và không cộng lại.

**Giới hạn:** Array appliedRewards có thể tăng vô hạn. Với số request lớn, cần thiết kế marker có thời hạn, ledger hoặc collection riêng; khi marker và điểm thưởng nằm trên hai document, phải giải quyết lại ranh giới atomicity.

### 16.4. Tránh nhân đôi side effect ngoài database

Ngay cả lệnh:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $set: {
      status: "PAID"
    }
  }
);
~~~

có thể idempotent về trạng thái cuối, nhưng nếu mỗi lần request gọi xong lại **gửi email** hoặc **tạo hóa đơn**, các side effect đó vẫn có thể lặp lại.

Thiết kế đúng có thể cần **outbox** hoặc idempotency key ở các hệ thống liên quan.

## 17. Upsert và nguy cơ insert trùng do cạnh tranh

Upsert kết hợp tìm rồi insert/update trên server:

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-NEW" },
  {
    $inc: {
      views: 1
    }
  },
  {
    upsert: true
  }
);
~~~

Khi filter dựa vào _id, unique index _id mặc định bảo vệ không có hai document cùng _id.

Nhưng nếu filter dùng những field **không có unique index**, hai upsert đồng thời có thể cùng xác định chưa có document và insert thành **hai document trùng khóa nghiệp vụ**.

Ví dụ counter theo ngày:

~~~javascript
db.dailyCounters.updateOne(
  {
    day: "2026-11-14",
    pageId: "PAGE-01"
  },
  {
    $inc: {
      views: 1
    }
  },
  {
    upsert: true
  }
);
~~~

Nếu cặp (day, pageId) phải duy nhất:

~~~javascript
db.dailyCounters.createIndex(
  { day: 1, pageId: 1 },
  {
    unique: true,
    name: "uq_daily_page"
  }
);
~~~

Unique index giúp bảo vệ bất biến uniqueness tại database. Khi nhiều upsert tranh cùng key, vẫn có những trường hợp client nhận duplicate key; cần phân loại lỗi và retry theo quy tắc phù hợp.

### 17.1. $setOnInsert

~~~javascript
db.dailyCounters.updateOne(
  {
    day: "2026-11-14",
    pageId: "PAGE-01"
  },
  {
    $inc: {
      views: 1
    },
    $setOnInsert: {
      createdAt: new Date()
    }
  },
  {
    upsert: true
  }
);
~~~

**$setOnInsert** chỉ đặt field khi upsert tạo mới document, không ghi đè createdAt ở những lần tăng counter tiếp theo.

## 18. Kiểu dữ liệu và schema validation

Các toán tử update có yêu cầu kiểu dữ liệu:

| Toán tử | Điều cần lưu ý |
| --- | --- |
| **$inc** | Field phải có kiểu số phù hợp hoặc chưa tồn tại; null có thể gây lỗi |
| **$mul** | Phép nhân theo kiểu số; không tự phù hợp mọi kiểu dữ liệu |
| **$min/$max** | Dùng so sánh BSON, nên thống nhất kiểu field |
| **$addToSet/$push/$pull** | Làm việc với array theo quy tắc của toán tử |
| **$set** | Thay giá trị đúng path, kể cả khi path là nguyên object cha |
| **$currentDate** | Đặt ngày giờ hiện tại, không tự bảo đảm idempotency khi retry |

Có thể dùng JSON Schema validation để giảm lỗi kiểu dữ liệu:

~~~javascript
db.createCollection("validatedCounters", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["views"],
      properties: {
        views: {
          bsonType: ["int", "long"],
          description: "views phải là số nguyên"
        }
      }
    }
  }
});
~~~

Validator giúp phát hiện dữ liệu không đúng schema. Tuy nhiên, điều kiện động như **available ≥ quantity** vẫn cần bảo vệ bằng filter/update thích hợp.

## 19. Write concern và read concern không thay thế atomic update

| Cơ chế | Câu hỏi nó giải quyết |
| --- | --- |
| **Atomic update** | Một write trên document có được áp dụng nguyên tử không? |
| **Conditional filter** | Điều kiện nghiệp vụ còn đúng lúc ghi không? |
| **Version/CAS** | Có writer khác thay dữ liệu sau lúc request đọc không? |
| **Write concern** | Mức xác nhận của thao tác ghi là gì? |
| **Read concern** | Mức nhất quán của dữ liệu đọc là gì? |
| **Transaction** | Có cần nguyên tử qua nhiều document không? |

Đặt **write concern majority** không tự sửa mẫu lost update đọc count = 10 rồi $set count = 11. Nó liên quan đến mức xác nhận/durability, không biến client read + write thành một lệnh nguyên tử.

Tương tự, đọc với mức nhất quán cao hơn không tự làm một quyết định **được tính từ bản đọc trước đó** trở nên đúng khi writer khác đã thay đổi document.

### 19.1. Kết quả ghi chưa rõ do network

Nếu client timeout sau write, kết quả có thể **không xác định từ góc nhìn client**. Không được tự khẳng định write chưa xảy ra. Với những operation không idempotent, cần cơ chế nhận diện business request hoặc đối soát phù hợp.

## 20. Java Sync Driver: Updates.inc

Ví dụ Java Sync Driver:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public class AtomicCounterExample {

    public static void main(String[] args) {
        try (MongoClient client =
                MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase db =
                    client.getDatabase("atomic_concurrency_lab");

            MongoCollection<Document> counters =
                    db.getCollection("counters");

            UpdateResult result = counters.updateOne(
                    Filters.eq("_id", "PAGE-01"),
                    Updates.inc("views", 1L)
            );

            System.out.println(
                    "Matched: " + result.getMatchedCount()
            );
            System.out.println(
                    "Modified: " + result.getModifiedCount()
            );
        }
    }
}
~~~

**Updates.inc("views", 1L)** đưa phép tăng vào MongoDB server, không cần client đọc views trước rồi ghi lại số đã tự tính.

### 20.1. Mẫu read–modify–write sai trong Java

~~~java
Document doc = counters.find(
        Filters.eq("_id", "PAGE-01")
).first();

long nextViews = doc.getLong("views") + 1L;

counters.updateOne(
        Filters.eq("_id", "PAGE-01"),
        Updates.set("views", nextViews)
);
~~~

Trong khoảng giữa find và update, writer khác có thể tăng views. **nextViews** dựa vào snapshot cũ, nên có thể mất cập nhật. Java Driver không tự biết ý định thật sự là increment.

## 21. Java Sync Driver: trừ tồn kho có điều kiện

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

public class ReserveStockExample {

    public static void main(String[] args) {
        String productId = "SKU-BOOK-01";
        int quantity = 2;

        try (MongoClient client =
                MongoClients.create("mongodb://localhost:27017")) {

            MongoCollection<Document> products =
                    client.getDatabase("atomic_concurrency_lab")
                            .getCollection("products");

            Bson filter = Filters.and(
                    Filters.eq("_id", productId),
                    Filters.gte("available", quantity)
            );

            Bson update = Updates.combine(
                    Updates.inc("available", -quantity),
                    Updates.inc("reserved", quantity),
                    Updates.inc("version", 1),
                    Updates.currentDate("updatedAt")
            );

            UpdateResult result =
                    products.updateOne(filter, update);

            if (result.getMatchedCount() == 1) {
                System.out.println("Giữ chỗ thành công");
            } else {
                System.out.println(
                        "Sản phẩm không tồn tại hoặc không đủ tồn kho"
                );
            }
        }
    }
}
~~~

Điều kiện được MongoDB server kiểm tra cùng update. Một **synchronized** block ở JVM không thay thế được filter này khi database còn được ghi bởi process khác.

## 22. Java Sync Driver: optimistic locking

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.conversions.Bson;

// users là MongoCollection<Document> đã được khởi tạo.

int expectedVersion = 1;

Bson filter = Filters.and(
        Filters.eq("_id", "U-01"),
        Filters.eq("version", expectedVersion)
);

Bson update = Updates.combine(
        Updates.set("profile.city", "Huế"),
        Updates.inc("version", 1)
);

UpdateResult result = users.updateOne(filter, update);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
            "Document không tồn tại hoặc đã có thay đổi đồng thời"
    );
}
~~~

### 22.1. Client cần mang version của bản đã đọc

~~~text
GET /users/U-01
  -> trả profile và version = 7

Client chỉnh sửa form

PATCH /users/U-01
  -> gửi city mới, expectedVersion = 7

Server:
  updateOne({_id, version:7},
            {$set city, $inc version:1})
~~~

Nếu writer khác đã tăng version thành 8, request này không match. Không nên đọc version **mới nhất** ngay trước lúc ghi rồi luôn dùng nó để vượt qua kiểm tra xung đột của bản form cũ.

### 22.2. Không phải conflict nào cũng tự retry được

Nếu hai người cùng sửa địa chỉ, retry bằng cách gán lại dữ liệu cũ sau khi đọc version mới có thể làm mất ý định người khác. Có thể cần hiển thị conflict, cho người dùng merge hoặc xác định quy tắc nghiệp vụ về quyền ưu tiên.

## 23. Java Sync Driver: findOneAndUpdate

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;
import com.mongodb.client.model.Updates;
import org.bson.Document;

// products là MongoCollection<Document> đã được tạo.

int quantity = 2;

Document after = products.findOneAndUpdate(
        Filters.and(
                Filters.eq("_id", "SKU-BOOK-01"),
                Filters.gte("available", quantity)
        ),
        Updates.combine(
                Updates.inc("available", -quantity),
                Updates.inc("reserved", quantity)
        ),
        new FindOneAndUpdateOptions()
                .returnDocument(ReturnDocument.AFTER)
);

if (after == null) {
    System.out.println("Không đủ hàng hoặc không có sản phẩm");
} else {
    System.out.println(
            "Số còn lại: " + after.getInteger("available")
    );
}
~~~

**findOneAndUpdate** trả document trước/sau theo cấu hình trong cùng operation. Writer khác vẫn có thể cập nhật sau khi operation hoàn tất.

## 24. Mô phỏng nhiều writer trong Node.js

Để thấy khác biệt giữa $inc và read–modify–write, dùng **MongoDB Node.js Driver** trên collection thử nghiệm.

### 24.1. Tăng 100 lần bằng $inc

~~~javascript
import { MongoClient } from "mongodb";

const uri = process.env.MONGODB_URI
  ?? "mongodb://localhost:27017";

const client = new MongoClient(uri);

try {
  await client.connect();

  const counters = client
    .db("atomic_concurrency_lab")
    .collection("counters");

  await counters.updateOne(
    { _id: "CONCURRENT-COUNTER" },
    { $set: { views: 0 } },
    { upsert: true }
  );

  const count = 100;

  await Promise.all(
    Array.from({ length: count }, () =>
      counters.updateOne(
        { _id: "CONCURRENT-COUNTER" },
        { $inc: { views: 1 } }
      )
    )
  );

  const result = await counters.findOne({
    _id: "CONCURRENT-COUNTER"
  });

  console.log("views =", result.views);
} finally {
  await client.close();
}
~~~

Nếu cả 100 write đều được áp dụng thành công, kết quả kỳ vọng **views = 100**.

### 24.2. Tái hiện lỗi bằng hai pha đọc và ghi

Trong một script khác với client đã kết nối:

~~~javascript
const counters = client
  .db("atomic_concurrency_lab")
  .collection("counters");

await counters.updateOne(
  { _id: "CONCURRENT-COUNTER" },
  { $set: { views: 0 } }
);

// Cho 100 tác vụ đọc xong trước khi tác vụ nào ghi.
const snapshots = await Promise.all(
  Array.from({ length: 100 }, () =>
    counters.findOne({ _id: "CONCURRENT-COUNTER" })
  )
);

// Mỗi tác vụ ghi giá trị đã tính từ snapshot riêng.
await Promise.all(
  snapshots.map(snapshot =>
    counters.updateOne(
      { _id: "CONCURRENT-COUNTER" },
      {
        $set: {
          views: snapshot.views + 1
        }
      }
    )
  )
);

console.log(
  await counters.findOne({ _id: "CONCURRENT-COUNTER" })
);
~~~

Nếu mọi snapshot đều có views = 0, mọi write đều $set views = 1, nên kết quả là **1 chứ không phải 100**. Thử nghiệm cố tình buộc các lần đọc hoàn tất trước các lần ghi để thấy lost update rõ ràng.

Trong thực tế các request có thể xen kẽ ngẫu nhiên hơn, vì vậy biểu hiện lỗi không phải lúc nào cũng giống nhau.

## 25. Hot document và giới hạn throughput

Một bộ đếm chung:

~~~javascript
db.metrics.updateOne(
  { _id: "GLOBAL-VIEWS" },
  { $inc: { count: 1 } }
);
~~~

có thể đúng về atomicity nhưng trở thành **hot document** nếu lượng writer cực lớn. Tính nguyên tử không có nghĩa throughput tăng vô hạn khi bổ sung thread.

### 25.1. Sharded counter ở tầng mô hình dữ liệu

Có thể phân tán lượt tăng lên nhiều document:

~~~text
counter-0
counter-1
counter-2
...
counter-N

Tổng logic = sum(count ở các counter document)
~~~

Mỗi request cập nhật một partition, giảm tranh chấp tại một document. Nhưng đọc tổng phải hợp nhất nhiều counter, cần xác định độ trễ và mức nhất quán có thể chấp nhận.

### 25.2. Đánh đổi

- Ghi được phân tán hơn.
- Đọc tổng tốn thêm công việc.
- Khó đạt tổng chính xác tức thời nếu hệ thống phân tán.
- Vẫn cần idempotency cho event có thể bị gửi lại.
- Có chi phí quản lý số partition và phân bố tải.

Không nên phức tạp hóa một counter chỉ vì lo ngại lý thuyết. Hãy đo throughput, latency và mức tranh chấp thực tế trước khi thay đổi mô hình.

## 26. Bảng quyết định nhanh

| Nhu cầu | Cơ chế gợi ý | Lý do |
| --- | --- | --- |
| Tăng lượt xem | **$inc** | Tránh đọc rồi gán số cũ + 1 |
| Giảm tồn kho có giới hạn | **Filter available ≥ q + $inc -q** | Kiểm tra và thay đổi cùng write |
| Đổi PENDING thành PAID | **Filter status PENDING + $set PAID** | Bảo vệ quy tắc transition |
| Thêm category vào array | **$addToSet** | Không gán đè toàn bộ array |
| Xóa category khỏi array | **$pull** | Sửa trực tiếp array hiện tại |
| Ghi giá thấp nhất | **$min** | So sánh và lưu ở server |
| Ghi điểm cao nhất | **$max** | Không ghi lùi điểm tối đa |
| Sửa form trên bản đã đọc | **CAS/version** | Phát hiện conflict |
| Thay nhiều field phụ thuộc cùng document | **Một updateOne kết hợp** | Nguyên tử ở mức document |
| Tính phức tạp từ các field hiện tại | **Update pipeline** | Không cần read–modify–write ở client |
| Sửa và lấy giá trị mới | **findOneAndUpdate** | Một operation find-and-modify |
| Chuyển tiền giữa hai account | **Transaction/ledger** | Invariant vượt qua một document |
| Gửi email đúng một lần sau ghi | **Outbox/idempotency** | Side effect ngoài database |

## 27. Những sai lầm thường gặp

**Sai lầm 1: Cho rằng $set không nguyên tử.**  
$set nguyên tử trên document; lost update do việc gán giá trị tính từ một lần đọc cũ.

**Sai lầm 2: Dùng $inc mà không kiểm tra ngưỡng.**  
$inc có thể làm tồn kho âm. Đưa điều kiện available ≥ quantity vào cùng filter.

**Sai lầm 3: Chuyển trạng thái không có điều kiện.**  
Hai request “thanh toán” và “hủy” có thể ghi đè nhau. Filter theo trạng thái cũ.

**Sai lầm 4: Dùng replaceOne hoặc $set object cha cho bản vá nhỏ.**  
Có thể xóa field người khác vừa cập nhật. Dùng đường dẫn field lá.

**Sai lầm 5: Coi matchedCount = 0 chỉ là không có ID.**  
Có thể do hết hàng, version đã đổi hoặc trạng thái không còn hợp lệ.

**Sai lầm 6: Có version nhưng một số writer không tăng version.**  
Cơ chế optimistic concurrency mất độ tin cậy.

**Sai lầm 7: Retry một $inc/$push mới khi không biết write cũ đã xảy ra chưa.**  
Có thể nhân đôi side effect. Dùng idempotency key hoặc quy tắc retry được thiết kế.

**Sai lầm 8: Coi $addToSet là unique index cho mọi tình huống.**  
Nó có semantics riêng với giá trị array, không phải mọi invariant xuyên document.

**Sai lầm 9: Dùng synchronized trong một process để khóa database.**  
Writer từ process khác vẫn có thể ghi. Bất biến chia sẻ cần bảo vệ ở server.

**Sai lầm 10: Coi bulkWrite/updateMany là transaction đa document.**  
Mỗi document nguyên tử, toàn nhóm không tự all-or-nothing.

**Sai lầm 11: Dùng majority write concern thay CAS.**  
Write concern liên quan mức xác nhận, không loại race giữa client read và write.

**Sai lầm 12: Coi update thành công là mọi side effect thành công.**  
Email, thanh toán, message broker và ghi ở collection khác cần quy tắc riêng.

## 28. Bài thực hành

Các bài tập giả định đã tạo dữ liệu ở mục 3. Khi cần so sánh từ trạng thái ban đầu, hãy khởi tạo lại document tương ứng trong môi trường thử nghiệm.

### Bài 1 – Timeline của lost update

Cho counter count = 10, hai request đều đọc 10, tính 11 và ghi 11. Hãy vẽ timeline, nêu kết quả thực tế, kết quả mong muốn và giải thích vì sao hai $inc +1 khắc phục tình huống này.

### Bài 2 – Tăng hai counter nguyên tử

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  {
    $inc: {
      views: 1,
      likes: 1
    }
  }
);
~~~

Trả lời:

1. Có bao nhiêu document được sửa?
2. Có bao nhiêu operation ghi?
3. Vì sao không cần đọc views và likes trước?
4. Nếu views là null thay vì number thì sao?

### Bài 3 – Trừ tồn kho không âm

Product SKU-PEN-02 có available = 3. Hai request đều muốn 2.

~~~javascript
db.products.updateOne(
  {
    _id: "SKU-PEN-02",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2
    }
  }
);
~~~

Chạy hai lần và quan sát matchedCount, available. Vì sao request thứ hai không thể trừ tiếp khi chỉ còn 1?

### Bài 4 – Chuyển trạng thái có điều kiện

Order PENDING được thanh toán hoặc hủy:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "PENDING"
  },
  {
    $set: { status: "PAID" }
  }
);
~~~

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "PENDING"
  },
  {
    $set: { status: "CANCELLED" }
  }
);
~~~

Kết quả cuối phụ thuộc thứ tự nào? Vì sao cả hai không thể đều chuyển thành công từ cùng trạng thái PENDING trong hai thao tác áp dụng lần lượt lên một document?

### Bài 5 – Sửa profile đúng path

So sánh:

~~~javascript
{
  $set: {
    "profile.city": "Huế"
  }
}
~~~

và:

~~~javascript
{
  $set: {
    profile: {
      city: "Huế"
    }
  }
}
~~~

Cách nào làm mất profile.language nếu field đó không có trong object mới?

### Bài 6 – Version conflict

Hai request cùng đọc version = 1. Một request cập nhật city và tăng version; request còn lại cố đổi language với version = 1. Viết lệnh của cả hai và diễn giải matchedCount. Nếu cả hai field độc lập, có cách thiết kế nào giảm conflict quá mức không?

### Bài 7 – Array không mất phần tử

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $addToSet: {
      favoriteCategories: "music"
    }
  }
);

db.users.updateOne(
  { _id: "U-01" },
  {
    $pull: {
      favoriteCategories: "books"
    }
  }
);
~~~

Giải thích vì sao không cần đọc toàn bộ array ở client rồi gán lại.

### Bài 8 – Expression trên server

Invoice có quantity = 2, unitPriceCents = 50000. Viết update pipeline tính amountCents = quantity × unitPriceCents. Nếu quantity bị thay đổi đồng thời, vì sao tính ở server hợp lý hơn việc đọc quantity tại client rồi $set amountCents sau đó?

### Bài 9 – Idempotency key

Một job phải cộng rewardPoints +10 đúng một lần theo jobId. Network timeout khiến client không biết write đã thành công chưa. Thiết kế filter và update dùng appliedRewards để không cộng hai lần, rồi nêu giới hạn khi array marker quá lớn.

### Bài 10 – Invariant trên hai document

Account A có balanceCents = 100000, B có 50000. Cần chuyển 20000. Vì sao hai $inc riêng không đủ nguyên tử chung? Khi nào cần transaction? Nếu còn phải gọi payment API, transaction database có tự bao phủ được API bên ngoài không?

## 29. Checklist thiết kế trước khi viết update

Trước khi xây một API ghi có cạnh tranh, lần lượt hỏi:

1. Giá trị mới là **delta** hay **giá trị đích**? Nếu delta, ưu tiên $inc; nếu cực trị, $min/$max.
2. Có invariant phải đúng **khi ghi** không? Đưa điều kiện vào filter.
3. Có tính toán từ dữ liệu cũ ở client không? Xem xét pipeline update, CAS hoặc version.
4. Có nhiều field phụ thuộc cùng document không? Gộp vào một updateOne.
5. Có ghi qua nhiều document không? Đánh giá transaction/ledger.
6. Lệnh có thể bị retry sau timeout không? Cần idempotency.
7. Có thay nguyên object hoặc array không? Chỉ cập nhật đúng path nếu là bản vá.
8. Có cần phân biệt thành công với conflict không? Kiểm tra matchedCount/modifiedCount.
9. Có cần trả document sau thay đổi không? Cân nhắc findOneAndUpdate.
10. Có hot document khi nhiều writer không? Đo tải và cân nhắc phân tán counter.

## 30. Kết luận

Lost update xảy ra khi nhiều request **đọc một giá trị cũ rồi ghi đè bằng kết quả tự tính**, khiến một thay đổi của writer khác biến mất. Trong MongoDB, hãy biểu diễn phép biến đổi trực tiếp bằng **toán tử cập nhật nguyên tử trên server** bất cứ khi nào phù hợp:

- **$inc** để tăng/giảm không cần đọc trước.
- **$min/$max** để giữ ngưỡng thấp nhất/cao nhất mà không tự so sánh tại client.
- **$addToSet/$pull** để thay đổi array mà không gán lại bản array cũ.
- **$set kèm filter** để chuyển trạng thái có điều kiện.
- **CAS/version** để phát hiện document đã được sửa sau lúc đọc.
- **Update pipeline** để tính công thức từ field hiện hành.
- **findOneAndUpdate** khi cần sửa và lấy giá trị trước/sau trong cùng operation.
- **Transaction hoặc kiến trúc idempotent/ledger phù hợp** khi invariant vượt qua nhiều document.

Hai ý phải đi cùng nhau: **atomicity bảo vệ phạm vi thao tác**, còn **đúng nghiệp vụ** phụ thuộc điều kiện lọc, quản lý version, idempotency và ranh giới document. Một write nguyên tử không tự chặn tồn kho âm, không tự bảo vệ toàn bộ chuyển tiền giữa hai account, và không tự ngăn side effect bị nhân đôi do retry nghiệp vụ.

## Tài liệu tham khảo

- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — $inc](https://www.mongodb.com/docs/manual/reference/operator/update/inc/)
- [MongoDB Manual — $min](https://www.mongodb.com/docs/manual/reference/operator/update/min/)
- [MongoDB Manual — $max](https://www.mongodb.com/docs/manual/reference/operator/update/max/)
- [MongoDB Manual — $addToSet](https://www.mongodb.com/docs/manual/reference/operator/update/addToSet/)
- [MongoDB Manual — $pull](https://www.mongodb.com/docs/manual/reference/operator/update/pull/)
- [MongoDB Manual — findOneAndUpdate](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndUpdate/)
- [MongoDB Manual — Updates with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update/)
