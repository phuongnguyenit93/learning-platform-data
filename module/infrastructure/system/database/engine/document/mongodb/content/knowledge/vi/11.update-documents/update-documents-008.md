# Loại phần tử bằng $pull, $pullAll và $pop trong MongoDB

## 1. Bài toán: xóa phần tử bên trong một document

Một document MongoDB có thể chứa những mảng như `tags`, `roles`, `cartItems`, `comments` hoặc `recentEvents`. Khi một nhãn không còn áp dụng, một quyền bị thu hồi hoặc một công việc đã hoàn tất, ứng dụng thường muốn **loại phần tử khỏi mảng** mà vẫn giữ nguyên document chứa mảng đó.

MongoDB có ba toán tử cập nhật phục vụ các trường hợp phổ biến:

| Toán tử | Cách chọn phần tử cần loại | Ví dụ nghiệp vụ |
| --- | --- | --- |
| **`$pull`** | Xóa **tất cả phần tử** bằng giá trị cho trước hoặc thỏa một điều kiện truy vấn. | Xóa mọi nhãn `"archived"`, mọi công việc `status = "DONE"`, mọi điểm dưới ngưỡng. |
| **`$pullAll`** | Xóa **tất cả lần xuất hiện** của từng giá trị trong danh sách đã chỉ định. | Thu hồi đồng thời các vai trò `"EDITOR"` và `"REVIEWER"`. |
| **`$pop`** | Xóa **một phần tử ở đầu hoặc cuối mảng**. | Bỏ phần tử đầu của một danh sách có thứ tự hoặc phần tử cuối của stack đơn giản. |

Các thao tác này khác nhau về **điều kiện lựa chọn**, chứ không chỉ về cú pháp. Nếu cần xóa một dòng hàng theo `itemId`, hãy dùng điều kiện nhận diện dòng hàng, thường là `$pull`. Nếu muốn xóa phần tử **cuối cùng hiện tại** dù nó là gì, `$pop: 1` phù hợp hơn. Nếu muốn loại nhiều giá trị cụ thể trong mảng chuỗi, `$pullAll` giúp thể hiện ý định rõ ràng.

Trong cả ba trường hợp, MongoDB cập nhật **mảng đang lưu trong document**. Nó không xóa document cha khỏi collection và không tự làm sạch dữ liệu liên quan ở collection khác.

### 1.1. Khung lệnh chung

~~~javascript
db.collection.updateOne(
  { /* điều kiện tìm document */ },
  {
    $pull: {
      arrayField: /* giá trị hoặc điều kiện chọn phần tử */
    }
  }
);
~~~

Một lệnh cập nhật có hai phạm vi lọc:

1. **Filter bên ngoài** chọn document nào được cập nhật, ví dụ `_id: "ORDER-1"`.
2. **Điều kiện bên trong `$pull`** chọn phần tử nào phải bị loại trong mảng của document đã tìm.

Hai phạm vi này không thay thế cho nhau. Document có thể khớp filter ngoài nhưng mảng không có phần tử cần xóa; khi đó có thể có `matchedCount = 1` và `modifiedCount = 0`.

---

## 2. Chuẩn bị dữ liệu mẫu

Các ví dụ dùng `mongosh` và collection minh họa `arrayRemovalLab`. Giả sử collection này chưa chứa những ID trong ví dụ. Có thể tạo dữ liệu:

~~~javascript
db.arrayRemovalLab.insertMany([
  {
    _id: "TAGS-PULL",
    tags: ["vip", "archived", "vip", "featured"],
    scores: [55, 78, 82, 99]
  },
  {
    _id: "TAGS-ALL",
    tags: ["red", "blue", "red", "green", "blue"]
  },
  {
    _id: "QUEUE-POP",
    queue: ["created", "validated", "processed", "sent"]
  },
  {
    _id: "TASKS-PULL",
    tasks: [
      { taskId: "T1", status: "DONE", points: 4 },
      { taskId: "T2", status: "OPEN", points: 8 },
      { taskId: "T3", status: "DONE", points: 9 },
      { taskId: "T4", status: "OPEN", points: 2 }
    ]
  },
  {
    _id: "NESTED",
    groups: [
      { code: "ENG", members: ["U1", "U2"] },
      { code: "OPS", members: ["U2", "U3"] }
    ]
  },
  {
    _id: "EMPTY",
    tags: []
  },
  {
    _id: "MISSING",
    label: "document không có tags"
  },
  {
    _id: "SCALAR",
    tags: "vip"
  }
]);
~~~

Các ví dụ thao tác trên **ID riêng** để dễ quan sát. Một vài đoạn đưa ra phương án thay thế hoặc tình huống khác biệt: hãy coi những đoạn đó là ví dụ độc lập trên trạng thái dữ liệu được mô tả, không mặc định chạy mọi biến thể liên tiếp rồi vẫn mong thấy cùng kết quả.

Để kiểm tra mảng sau khi cập nhật:

~~~javascript
db.arrayRemovalLab.findOne(
  { _id: "TAGS-PULL" },
  { tags: 1, scores: 1 }
);
~~~

Không dùng các lệnh thực hành trên collection chứa dữ liệu sản xuất nếu chưa có kế hoạch và giới hạn cập nhật phù hợp.

---

## 3. `$pull`: xóa mọi phần tử khớp giá trị

Cú pháp:

~~~javascript
{
  $pull: {
    <arrayField>: <value>
  }
}
~~~

Khi giá trị cung cấp là một giá trị đơn giản, MongoDB loại **tất cả lần xuất hiện** của giá trị đó trong mảng.

### 3.1. Xóa một chuỗi trong mảng

Mảng ban đầu:

~~~javascript
{
  _id: "TAGS-PULL",
  tags: ["vip", "archived", "vip", "featured"]
}
~~~

Lệnh:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "TAGS-PULL" },
  { $pull: { tags: "vip" } }
);
~~~

Sau khi cập nhật:

~~~javascript
{
  _id: "TAGS-PULL",
  tags: ["archived", "featured"]
}
~~~

Cả **hai** phần tử `"vip"` đều bị loại. `$pull` không có nghĩa “xóa một phần tử đầu tiên tìm thấy”. Nếu có 100 lần xuất hiện của `"vip"`, tất cả các phần tử đó đều là ứng viên bị xóa.

Các phần tử còn lại giữ thứ tự tương đối của chúng. `$pull` không tự sắp xếp mảng.

### 3.2. Xóa giá trị số

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "TAGS-PULL" },
  { $pull: { scores: 82 } }
);
~~~

Từ `scores: [55, 78, 82, 99]`, kết quả là `[55, 78, 99]`.

MongoDB so sánh theo ngữ nghĩa kiểu dữ liệu BSON. Không nên giả định chuỗi `"82"` luôn tương đương với số `82`. Nếu một field được thiết kế là mảng số, hãy xác thực kiểu dữ liệu để tránh lưu hỗn hợp string/number rồi nhận kết quả xóa khó dự đoán.

### 3.3. Xóa mọi lần xuất hiện khác với xóa đúng một phần tử

Nếu nghiệp vụ nói “thu hồi quyền `EDITOR` khỏi danh sách quyền”, xóa mọi lần xuất hiện `EDITOR` thường hợp lý vì danh sách quyền không nên chứa cùng quyền nhiều lần.

Nhưng nếu nghiệp vụ nói “hủy **một** lượt đặt vé trong hai lượt có cùng tên”, dùng `$pull: { bookings: "VIP" }` sẽ xóa **cả hai** lượt. Thiết kế đúng hơn là mỗi lượt có `bookingId` riêng và xóa bằng định danh đó.

Một toán tử không thể tự biết “lần xuất hiện thứ hai mang ý nghĩa khác lần thứ nhất” nếu dữ liệu không có thông tin nhận diện.

## 4. `$pull` với điều kiện so sánh

`$pull` nhận **biểu thức điều kiện truy vấn**, không chỉ nhận một giá trị chính xác. Với mảng số, có thể xóa mọi điểm dưới ngưỡng, trong khoảng hoặc thuộc một tập giá trị.

### 4.1. Xóa mọi điểm dưới ngưỡng

Trên dữ liệu ban đầu `scores: [55, 78, 82, 99]`:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "TAGS-PULL" },
  {
    $pull: {
      scores: { $lt: 80 }
    }
  }
);
~~~

Kết quả là `scores: [82, 99]`. Phần tử 55 và 78 đều nhỏ hơn 80 nên bị loại.

Các toán tử so sánh quen thuộc gồm:

| Toán tử | Ý nghĩa với mỗi phần tử |
| --- | --- |
| `$eq` | Bằng giá trị đã chỉ định. |
| `$ne` | Khác giá trị đã chỉ định. |
| `$gt` / `$gte` | Lớn hơn / lớn hơn hoặc bằng. |
| `$lt` / `$lte` | Nhỏ hơn / nhỏ hơn hoặc bằng. |
| `$in` | Thuộc một tập giá trị. |
| `$nin` | Không thuộc một tập giá trị. |
| `$regex` | Chuỗi khớp biểu thức chính quy theo điều kiện áp dụng. |

Đối với yêu cầu “xóa các điểm nằm trong khoảng **[80, 90)**”:

~~~javascript
db.examRecords.updateOne(
  { _id: "EXAM-1" },
  {
    $pull: {
      scores: {
        $gte: 80,
        $lt: 90
      }
    }
  }
);
~~~

Một phần tử bị loại khi giá trị của chính phần tử đó đồng thời **lớn hơn hoặc bằng 80** và **nhỏ hơn 90**. Ví dụ, từ `[75, 80, 85, 90, 92]` sẽ còn `[75, 90, 92]`. Với dữ liệu do người dùng gửi, việc **từ chối điểm ngoài miền hợp lệ ngay khi ghi** thường an toàn hơn so với lưu rồi mới xóa. Các ví dụ minh họa khả năng của `$pull`; không khuyến khích dùng nó thay cho schema validation.

### 4.2. Xóa nhiều giá trị bằng `$in`

~~~javascript
db.users.updateOne(
  { _id: "U100" },
  {
    $pull: {
      roles: { $in: ["GUEST", "OBSOLETE"] }
    }
  }
);
~~~

Mọi phần tử `"GUEST"` hoặc `"OBSOLETE"` đều bị loại. Đây là trường hợp `$pull` có thể diễn đạt mục tiêu rất giống `$pullAll`. Chọn cách đọc rõ hơn cho người bảo trì và giữ quy tắc loại bỏ nhất quán.

### 4.3. Xóa chuỗi theo mẫu

~~~javascript
db.documents.updateOne(
  { _id: "DOC-1" },
  {
    $pull: {
      tags: { $regex: "^tmp-" }
    }
  }
);
~~~

Với `tags: ["published", "tmp-draft", "tmp-legacy"]`, lệnh loại các nhãn bắt đầu bằng `"tmp-"`. Biểu thức chính quy cần được xây dựng cẩn thận, đặc biệt khi có đầu vào người dùng. Dùng regex không được kiểm soát có thể làm xóa nhầm nhiều phần tử hoặc gây chi phí xử lý không cần thiết.

### 4.4. `$pull` là cập nhật, không phải truy vấn đọc

~~~javascript
// Truy vấn: tìm document có phần tử thuộc tập cấm
db.documents.find({
  tags: { $in: ["tmp-draft", "tmp-legacy"] }
});

// Cập nhật: xóa phần tử thuộc tập cấm trong document được chọn
db.documents.updateOne(
  { _id: "DOC-1" },
  {
    $pull: {
      tags: { $in: ["tmp-draft", "tmp-legacy"] }
    }
  }
);
~~~

Ở lệnh đọc, `$in` dùng để xác định **document nào** được trả về. Ở lệnh cập nhật, điều kiện bên trong `$pull` xác định **những phần tử nào của mảng** cần loại bỏ. Cùng toán tử điều kiện nhưng khác vị trí trong câu lệnh dẫn đến phạm vi hành động khác nhau.

---

## 5. `$pull` với mảng chứa embedded document

Trường hợp thực tế thường gặp là mảng chứa object, không phải mảng chuỗi. Ví dụ:

~~~javascript
{
  _id: "TASKS-PULL",
  tasks: [
    { taskId: "T1", status: "DONE", points: 4 },
    { taskId: "T2", status: "OPEN", points: 8 },
    { taskId: "T3", status: "DONE", points: 9 },
    { taskId: "T4", status: "OPEN", points: 2 }
  ]
}
~~~

### 5.1. Loại mọi công việc có trạng thái DONE

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "TASKS-PULL" },
  {
    $pull: {
      tasks: { status: "DONE" }
    }
  }
);
~~~

Kết quả:

~~~javascript
{
  _id: "TASKS-PULL",
  tasks: [
    { taskId: "T2", status: "OPEN", points: 8 },
    { taskId: "T4", status: "OPEN", points: 2 }
  ]
}
~~~

Điều kiện `{ status: "DONE" }` được áp dụng cho **từng document phần tử** của mảng `tasks`. Nó tìm các phần tử có trường `status` bằng `"DONE"`, kể cả phần tử có thêm những field khác như `taskId` và `points`.

### 5.2. Nhiều điều kiện trên cùng một embedded document

Giả sử mục tiêu là **chỉ xóa công việc đã hoàn tất có điểm từ 8 trở lên**:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "TASKS-PULL" },
  {
    $pull: {
      tasks: {
        status: "DONE",
        points: { $gte: 8 }
      }
    }
  }
);
~~~

Nếu áp dụng lên dữ liệu **ban đầu** ở mục 2, chỉ `T3` (DONE, 9 điểm) bị loại. `T1` có DONE nhưng chỉ 4 điểm; `T2` có 8 điểm nhưng OPEN. Cả hai phải được giữ.

Điểm quan trọng: **điều kiện của `$pull` trên mảng embedded document được đánh giá như một truy vấn đối với từng phần tử**. Không cần tự bao một `$elemMatch` bên ngoài chỉ để ràng buộc `status` và `points` thuộc cùng object đang bị xét.

So sánh ý định:

~~~javascript
// Đọc: một task thỏa đồng thời cả hai điều kiện.
db.arrayRemovalLab.find({
  tasks: {
    $elemMatch: {
      status: "DONE",
      points: { $gte: 8 }
    }
  }
});

// Ghi: xóa mọi task thỏa đồng thời cả hai điều kiện.
db.arrayRemovalLab.updateOne(
  { _id: "TASKS-PULL" },
  {
    $pull: {
      tasks: {
        status: "DONE",
        points: { $gte: 8 }
      }
    }
  }
);
~~~

`$elemMatch` trong phần **truy vấn đọc** giúp ràng buộc nhiều điều kiện trên cùng một phần tử. Khi dùng `$pull`, đối tượng đang xét đã là **từng phần tử mảng**, nên đặt trực tiếp điều kiện trường của phần tử như ví dụ.

### 5.3. Xóa theo ID ổn định

Trong hệ thống đơn hàng, điều kiện đáng tin cậy hơn thường là định danh dòng hàng:

~~~javascript
db.orders.updateOne(
  { _id: "ORDER-1007" },
  {
    $pull: {
      items: { lineId: "LINE-02" }
    }
  }
);
~~~

Lệnh này loại mọi dòng có `lineId: "LINE-02"` khỏi document đơn hàng. Nếu schema bảo đảm `lineId` duy nhất trong từng đơn, kết quả nghiệp vụ là xóa đúng một dòng.

Nếu `lineId` xuất hiện hai lần do dữ liệu đầu vào sai, **cả hai** phần tử cùng khớp đều bị xóa. `$pull` không có tham số “chỉ xóa lần khớp đầu tiên”. Vì vậy, khi nghiệp vụ yêu cầu duy nhất một phần tử, cần bảo đảm tính duy nhất đó ở mô hình/logic cập nhật.

### 5.4. Điều kiện trên field lồng trong embedded document

~~~javascript
db.shipments.updateOne(
  { _id: "SHIP-1" },
  {
    $pull: {
      packages: {
        "warehouse.city": "HCM",
        state: "CANCELLED"
      }
    }
  }
);
~~~

Mỗi phần tử `packages` phải đồng thời có `warehouse.city = "HCM"` và `state = "CANCELLED"` để bị loại. Đường dẫn `warehouse.city` được hiểu tương đối với **document phần tử**.

### 5.5. Khi bên trong phần tử lại có mảng

Một document trong `reports` có thể chứa mảng `checks`:

~~~javascript
{
  _id: "RUN-1",
  reports: [
    {
      reportId: "R1",
      checks: [
        { code: "ACCESS", passed: true },
        { code: "SECURITY", passed: false }
      ]
    },
    {
      reportId: "R2",
      checks: [
        { code: "ACCESS", passed: true }
      ]
    }
  ]
}
~~~

Nếu cần xóa report có **một check SECURITY không đạt**, có thể dùng `$elemMatch` cho **mảng con `checks`**:

~~~javascript
db.testRuns.updateOne(
  { _id: "RUN-1" },
  {
    $pull: {
      reports: {
        checks: {
          $elemMatch: {
            code: "SECURITY",
            passed: false
          }
        }
      }
    }
  }
);
~~~

Trong trường hợp này, `$pull` vẫn xét **từng report**, còn `$elemMatch` là cần thiết để diễn đạt hai điều kiện trên **cùng một phần tử của mảng con checks**. Không nên nhầm hai tầng mảng khi thiết kế predicate.

---

## 6. `$pullAll`: loại mọi giá trị thuộc một danh sách

Cú pháp:

~~~javascript
{
  $pullAll: {
    <arrayField>: [<value1>, <value2>, ...]
  }
}
~~~

`$pullAll` nhận một **mảng các giá trị cần loại**, xóa mọi lần xuất hiện của mỗi giá trị đó trong mảng đích.

### 6.1. Xóa nhiều nhãn và cả bản trùng

Dữ liệu ban đầu:

~~~javascript
{
  _id: "TAGS-ALL",
  tags: ["red", "blue", "red", "green", "blue"]
}
~~~

Lệnh:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "TAGS-ALL" },
  {
    $pullAll: {
      tags: ["red", "blue"]
    }
  }
);
~~~

Kết quả:

~~~javascript
{
  _id: "TAGS-ALL",
  tags: ["green"]
}
~~~

Từ `"red"` xuất hiện hai lần và `"blue"` cũng xuất hiện hai lần; **cả bốn phần tử** đều bị xóa. Danh sách `["red", "blue"]` nêu **những giá trị cần loại**, không nêu “xóa hai phần tử”.

### 6.2. So sánh `$pullAll` và `$pull` + `$in`

Hai lệnh sau có **cùng mục tiêu** đối với mảng chuỗi thông thường:

~~~javascript
// Cách 1: danh sách giá trị phải loại
db.users.updateOne(
  { _id: "U1" },
  { $pullAll: { roles: ["OBSOLETE", "GUEST"] } }
);

// Cách 2: điều kiện membership
db.users.updateOne(
  { _id: "U1" },
  { $pull: { roles: { $in: ["OBSOLETE", "GUEST"] } } }
);
~~~

Nhưng hai ví dụ trên **không cần chạy liên tiếp** để đạt cùng kết quả; chúng minh họa hai cách biểu đạt thay thế nhau.

Sự khác biệt về khả năng:

| Yêu cầu | `$pullAll` | `$pull` |
| --- | --- | --- |
| Loại chính xác giá trị `"old"` | Có. | Có. |
| Loại cả `"old"` và `"deprecated"` | Có, bằng danh sách. | Có, bằng `$in`. |
| Loại mọi số nhỏ hơn 0 | Không nhận điều kiện so sánh. | Có, bằng `$lt`. |
| Loại mọi object có `status = "DONE"` | Không phải công cụ thích hợp để lọc theo field. | Có, bằng điều kiện trên embedded document. |
| Loại chuỗi khớp regex | Không hỗ trợ biểu thức điều kiện như query predicate. | Có, bằng `$regex` phù hợp. |
| Loại tất cả bản trùng của giá trị được chọn | Có. | Có. |

`$pullAll` thích hợp nhất với **tập giá trị cụ thể, thường là scalar**. Nếu mảng chứa object có nhiều field thay đổi theo thời gian, thường nên dùng `$pull` với khóa nhận diện như `itemId` hoặc điều kiện nghiệp vụ. Đừng yêu cầu client phải tái tạo nguyên object với mọi field chỉ để xóa một phần tử.

### 6.3. Giá trị cần loại phải ở đúng kiểu

~~~javascript
db.metrics.updateOne(
  { _id: "M1" },
  { $pullAll: { codes: [2, 3] } }
);
~~~

Nếu `codes` là `[1, 2, 3, "2"]`, thao tác theo điều kiện số không nên được hiểu là phép chuyển đổi mọi phần tử sang số. Việc lưu kiểu dữ liệu thống nhất và dùng đúng kiểu giá trị quan trọng hơn việc thử lặp đi lặp lại các toán tử.

### 6.4. Cẩn thận với mảng document

Ví dụ:

~~~javascript
{
  _id: "A1",
  participants: [
    { userId: "U1", role: "EDITOR" },
    { userId: "U2", role: "REVIEWER" }
  ]
}
~~~

Nếu mục đích là thu hồi tất cả participant có `userId = "U1"`, dùng:

~~~javascript
db.sessions.updateOne(
  { _id: "A1" },
  {
    $pull: {
      participants: { userId: "U1" }
    }
  }
);
~~~

Hành động không phụ thuộc vào field `role` có thể đổi sau này. Cố dùng `$pullAll` với cả object sẽ dễ làm bộ lọc quá chặt hoặc không thể diễn đạt một quy tắc linh hoạt.

---

## 7. `$pop`: xóa phần tử đầu hoặc cuối mảng

Cú pháp:

~~~javascript
{
  $pop: {
    <arrayField>: -1 // phần tử đầu
  }
}
~~~

hoặc:

~~~javascript
{
  $pop: {
    <arrayField>: 1 // phần tử cuối
  }
}
~~~

Giá trị điều khiển **vị trí**, không phải số lượng cần xóa:

- **`-1`:** xóa phần tử **đầu tiên**.
- **`1`:** xóa phần tử **cuối cùng**.

### 7.1. Xóa phần tử cuối

Ban đầu:

~~~javascript
{
  _id: "QUEUE-POP",
  queue: ["created", "validated", "processed", "sent"]
}
~~~

Lệnh:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "QUEUE-POP" },
  {
    $pop: { queue: 1 }
  }
);
~~~

Sau lệnh:

~~~javascript
{
  _id: "QUEUE-POP",
  queue: ["created", "validated", "processed"]
}
~~~

### 7.2. Xóa phần tử đầu

Thực hiện tiếp **trên trạng thái vừa cập nhật**:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "QUEUE-POP" },
  {
    $pop: { queue: -1 }
  }
);
~~~

Kết quả:

~~~javascript
{
  _id: "QUEUE-POP",
  queue: ["validated", "processed"]
}
~~~

`$pop` không lọc theo giá trị. Nếu danh sách có `["A", "B", "A"]`, `$pop: 1` xóa `"A"` cuối; `$pop: -1` xóa `"A"` đầu. Muốn xóa **tất cả** `"A"` bất kể vị trí, dùng `$pull`.

### 7.3. `$pop: 1` không có nghĩa xóa một phần tử bất kỳ

Nếu đối tượng cần xóa được chỉ định bằng `notificationId`, dùng `$pull`:

~~~javascript
db.notifications.updateOne(
  { _id: "USER-1" },
  {
    $pull: {
      messages: { notificationId: "N-42" }
    }
  }
);
~~~

Dùng `$pop: 1` ở đây chỉ xóa phần tử cuối tại thời điểm cập nhật, có thể là một thông báo khác hoàn toàn.

### 7.4. Khi nào `$pop` hợp lý?

- Mảng có **thứ tự có ý nghĩa** và yêu cầu chỉ là bỏ đầu hoặc cuối.
- Danh sách ngắn, có giới hạn rõ và được sở hữu bởi một document.
- Ứng dụng chấp nhận rằng phần tử bị loại chính là phần tử đang ở vị trí đó tại lúc thao tác chạy.

`$pop` **không trả lại phần tử vừa bị xóa** như một API lấy job ra khỏi queue rồi bảo đảm worker nào đã sở hữu job. Nếu cần hàng đợi nhiều consumer, ack/retry và tránh nhận trùng, nên cân nhắc thiết kế collection job riêng hoặc hệ queue chuyên dụng.

---

## 8. So sánh trực quan ba toán tử

Xét cùng mảng ban đầu:

~~~javascript
{
  labels: ["A", "B", "A", "C", "B"]
}
~~~

Mỗi lệnh sau giả định chạy **độc lập trên mảng ban đầu**:

| Lệnh | Kết quả |
| --- | --- |
| `{ $pull: { labels: "A" } }` | `["B", "C", "B"]` |
| `{ $pull: { labels: { $in: ["A", "B"] } } }` | `["C"]` |
| `{ $pullAll: { labels: ["A", "B"] } }` | `["C"]` |
| `{ $pop: { labels: -1 } }` | `["B", "A", "C", "B"]` |
| `{ $pop: { labels: 1 } }` | `["A", "B", "A", "C"]` |

Điểm dễ nhớ:

- `$pull` trả lời **“phần tử nào khớp điều kiện?”**.
- `$pullAll` trả lời **“phần tử nào nằm trong danh sách giá trị?”**.
- `$pop` trả lời **“phần tử nào đang ở đầu/cuối?”**.

Mảng có nhiều giá trị trùng nhau là ca thử đặc biệt quan trọng để phân biệt hai nhóm đầu với `$pop`.

---

## 9. Trường thiếu, mảng rỗng và kiểu dữ liệu không đúng

Xét ba document:

~~~javascript
{ _id: "EMPTY", tags: [] }
{ _id: "MISSING", label: "document không có tags" }
{ _id: "SCALAR", tags: "vip" }
~~~

### 9.1. Mảng rỗng

Nếu `tags: []`, không có phần tử để loại. Ví dụ:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "EMPTY" },
  { $pull: { tags: "vip" } }
);
~~~

Document vẫn có `tags: []`. Với các thao tác tương ứng, `$pullAll` hoặc `$pop` cũng không thể xóa phần tử nào từ mảng rỗng.

### 9.2. Field không tồn tại

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "MISSING" },
  { $pull: { tags: "vip" } }
);
~~~

Vì document không có field `tags`, thao tác không làm xuất hiện mảng mới chỉ để xóa. Thao tác cập nhật không tự biến field thiếu thành `[]`. Nếu nghiệp vụ cần luôn có mảng, hãy khởi tạo schema hoặc sửa dữ liệu qua một thao tác riêng.

### 9.3. Field tồn tại nhưng không phải array

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "SCALAR" },
  { $pull: { tags: "vip" } }
);
~~~

Ở đây `tags` là string `"vip"`, không phải array. MongoDB không coi string là mảng một phần tử chỉ để thực hiện toán tử xóa. Thao tác có thể bị từ chối vì không thể áp dụng cập nhật mảng cho giá trị không phải array. `$pullAll` và `$pop` cũng đòi một trường mảng thích hợp.

Với ứng dụng có schema không nhất quán, đừng sửa lỗi bằng cách coi mọi trường scalar giống array. Cần quyết định migration: chuyển scalar thành array, thay đổi API hoặc loại giá trị cũ theo quy tắc nghiệp vụ.

### 9.4. Kết quả cập nhật khi không có phần tử khớp

~~~javascript
const result = db.arrayRemovalLab.updateOne(
  { _id: "EMPTY" },
  { $pull: { tags: "not-found" } }
);

printjson(result);
~~~

Trong thao tác được xác nhận thông thường, kết quả có thể tương tự:

~~~javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 0,
  upsertedId: null
}
~~~

- **`matchedCount = 1`**: đã tìm được document theo filter ngoài.
- **`modifiedCount = 0`**: document không bị thay đổi.
- **`upsertedId = null`**: không có document mới được tạo.

Đừng coi `modifiedCount = 0` chắc chắn là lỗi. Đối với hành động **“bảo đảm vai trò cũ không còn tồn tại”**, thao tác không thay đổi gì vì vai trò đã bị xóa trước đó có thể là kết quả hợp lệ và idempotent. Nếu nghiệp vụ yêu cầu **“phải xóa chính xác một phần tử đang tồn tại”**, cần thêm điều kiện và báo trạng thái rõ ràng.

---

## 10. Xóa phần tử ở mảng con bằng filtered positional operator

Đôi khi document chứa **mảng các nhóm**, mỗi nhóm lại có mảng thành viên:

~~~javascript
{
  _id: "NESTED",
  groups: [
    { code: "ENG", members: ["U1", "U2"] },
    { code: "OPS", members: ["U2", "U3"] }
  ]
}
~~~

Yêu cầu: chỉ thu hồi `U2` khỏi **nhóm ENG**, giữ nguyên membership của OPS. Nếu cập nhật toàn bộ mảng `groups` hoặc pull sai path, có thể vô tình xóa dữ liệu của nhóm khác.

Có thể dùng **filtered positional operator `$[g]`** cùng `arrayFilters`:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "NESTED" },
  {
    $pull: {
      "groups.$[g].members": "U2"
    }
  },
  {
    arrayFilters: [
      { "g.code": "ENG" }
    ]
  }
);
~~~

Kết quả:

~~~javascript
{
  _id: "NESTED",
  groups: [
    { code: "ENG", members: ["U1"] },
    { code: "OPS", members: ["U2", "U3"] }
  ]
}
~~~

Trong ví dụ:

1. `groups` là mảng ngoài.
2. `$[g]` chỉ các phần tử `groups` thỏa `g.code = "ENG"`.
3. `members` là mảng bên trong từng group được chọn.
4. `$pull` xóa tất cả giá trị `"U2"` khỏi đúng những mảng `members` đó.

`arrayFilters` lọc **phần tử của mảng ngoài**; điều kiện của `$pull` lọc **phần tử của mảng trong**. Hai lớp điều kiện có mục tiêu khác nhau.

Nếu `code` được phép trùng giữa nhiều group, mọi group khớp `arrayFilters` có thể bị tác động. Nếu nghiệp vụ chỉ muốn một group, cần bảo đảm định danh group ổn định và duy nhất trong document.

### 10.1. Không nhầm với `$unset` trên vị trí mảng

Trong một số tình huống, `$unset` áp vào vị trí mảng (chẳng hạn `"tags.1"`) **đặt phần tử thành `null`**, chứ không tự thu ngắn mảng và dịch các phần tử sau lên. Nếu mục đích là **loại phần tử và co lại mảng**, hãy dùng `$pull` theo giá trị/định danh hoặc `$pop` cho hai đầu.

Ví dụ cần xóa một item có ID cụ thể: `$pull: { items: { itemId: "I2" } }` thường rõ nghĩa hơn việc tìm vị trí rồi `$unset`.

---

## 11. Tính nguyên tử và cập nhật đồng thời

Một lệnh cập nhật trên **một document** trong MongoDB có tính nguyên tử. Điều này áp dụng khi dùng `$pull`, `$pullAll` hoặc `$pop` trong `updateOne`: người đọc không nhìn thấy document ở trạng thái đang xóa được một nửa số phần tử.

Tuy vậy, **tính nguyên tử của document không giải quyết mọi quy tắc cạnh tranh nghiệp vụ**.

### 11.1. Hai client cùng xóa một giá trị

Giả sử mảng chứa `"EDITOR"`. Hai request cùng chạy:

~~~javascript
db.users.updateOne(
  { _id: "U100" },
  { $pull: { roles: "EDITOR" } }
);
~~~

Khi hoàn tất, vai trò `EDITOR` không còn. Một request có thể làm thay đổi document, request còn lại không phải sửa gì. Đó thường là hành vi phù hợp cho thao tác **thu hồi quyền theo trạng thái đích** (*ensure absent*).

Nếu API định nghĩa “thu hồi một quyền đã có và gửi thông báo chính xác một lần”, cần thêm quy tắc để xác định request nào thật sự thực hiện thay đổi và tránh xử lý phụ hai lần.

### 11.2. `$pop` trên mảng bị thêm đồng thời

Giả sử client A đọc mảng thấy phần tử cuối là `"JOB-1"`, rồi client B thêm `"JOB-2"` trước khi A gửi `$pop: 1`. Khi lệnh của A chạy, phần tử cuối **hiện tại** có thể đã là `"JOB-2"`.

Do vậy, nếu mục tiêu là xóa `"JOB-1"`, đừng chỉ dựa vào lần đọc trước rồi gọi `$pop`. Dùng định danh:

~~~javascript
db.jobs.updateOne(
  { _id: "QUEUE-1" },
  { $pull: { pending: { jobId: "JOB-1" } } }
);
~~~

Nếu đó thực sự là queue nhiều worker, còn phải giải quyết việc **nhận job, xác nhận xử lý, retry sau crash và chống xử lý trùng**. Một thao tác xóa phần tử không tự cung cấp tất cả các bảo đảm của hệ thống queue.

### 11.3. Cập nhật nhiều document

~~~javascript
db.users.updateMany(
  { tenantId: "T1" },
  { $pull: { roles: "LEGACY_USER" } }
);
~~~

Lệnh áp dụng thao tác xóa cho **mỗi document khớp**. Cập nhật từng document là nguyên tử; **toàn bộ nhiều document không tự trở thành một transaction nguyên tử**. Trong trường hợp xảy ra lỗi hoặc gián đoạn giữa chừng, ứng dụng phải phân biệt trạng thái và có thể cần chạy lại có kiểm soát.

Nếu nghiệp vụ yêu cầu một tập thay đổi nhiều document phải cùng commit hoặc cùng rollback, cân nhắc transaction nhiều document trong deployment được hỗ trợ. Với chiến dịch thu hồi một role cũ trên hàng triệu người dùng, một quá trình batch idempotent có checkpoint có thể thực dụng hơn transaction rất lớn.

### 11.4. Nhận diện cập nhật trùng và idempotency

`$pull` một giá trị đã không còn thường không tạo thêm thay đổi, nên dễ phù hợp với thao tác lặp lại. `$pullAll` tương tự nếu tập giá trị cần loại không còn trong mảng.

Ngược lại, **`$pop` không idempotent theo nghĩa “xóa đúng một phần tử mong muốn”**: gọi lần thứ nhất xóa phần tử cuối; gọi lần thứ hai xóa **phần tử cuối mới**, dẫn đến mất thêm dữ liệu. Nếu API có retry sau timeout, đặc biệt nguy hiểm khi gửi lại `$pop` mà không kiểm soát.

Trong hệ thống có retryable writes, driver có thể sử dụng cơ chế retry theo điều kiện hỗ trợ, nhưng điều đó không thay thế thiết kế idempotency của nghiệp vụ hoặc việc đối soát trạng thái khi client không biết chính xác kết quả.

---

## 12. Xóa một phần tử cần giữ bất biến nghiệp vụ

Giả sử giỏ hàng có:

~~~javascript
{
  _id: "CART-1",
  status: "OPEN",
  items: [
    { lineId: "L1", sku: "P1", quantity: 2, unitPriceMinor: 100000 },
    { lineId: "L2", sku: "P2", quantity: 1, unitPriceMinor: 300000 }
  ],
  totalMinor: 500000
}
~~~

Nếu chỉ thực hiện:

~~~javascript
db.carts.updateOne(
  { _id: "CART-1" },
  { $pull: { items: { lineId: "L2" } } }
);
~~~

Sau cập nhật, mảng đúng là không còn `L2`, nhưng **`totalMinor` có thể vẫn là 500000**. Bất biến “tổng tiền bằng tổng các dòng hàng” đã bị phá vỡ nếu ứng dụng coi field tổng là dữ liệu chuẩn.

Các phương án:

1. Chỉ lưu `items` và tính tổng ở đường đọc khi dữ liệu nhỏ, tần suất phù hợp.
2. Cập nhật cùng document bằng **pipeline update** tính lại tổng dựa trên mảng sau khi lọc, khi logic có thể biểu đạt đầy đủ bằng aggregation expressions.
3. Dùng cơ chế cập nhật theo phiên bản hoặc transaction phù hợp nếu có nhiều dữ liệu liên quan.

Ví dụ pipeline update loại `L2` rồi tính tổng từ mảng còn lại:

~~~javascript
db.carts.updateOne(
  { _id: "CART-1", status: "OPEN" },
  [
    {
      $set: {
        items: {
          $filter: {
            input: "$items",
            as: "item",
            cond: { $ne: ["$$item.lineId", "L2"] }
          }
        }
      }
    },
    {
      $set: {
        totalMinor: {
          $sum: {
            $map: {
              input: "$items",
              as: "item",
              in: {
                $multiply: [
                  "$$item.quantity",
                  "$$item.unitPriceMinor"
                ]
              }
            }
          }
        }
      }
    }
  ]
);
~~~

Đây là một **lựa chọn thay thế** khi cần cập nhật mảng và giá trị dẫn xuất trong cùng thao tác trên document. Nó không sử dụng `$pull` nhưng cho thấy giới hạn quan trọng của việc chỉ xóa phần tử: một cập nhật nghiệp vụ có thể còn phải duy trì các trường tổng hợp khác.

Nếu dữ liệu tiền tệ cần độ chính xác cao, dùng số nguyên đại diện đơn vị tiền nhỏ nhất hoặc kiểu thập phân thích hợp, kiểm soát tràn số và quy tắc làm tròn.

### 12.1. Tại sao không đơn giản dùng `$inc` cùng `$pull`?

Có thể nghĩ tới việc đọc giá dòng hàng, rồi làm:

~~~javascript
db.carts.updateOne(
  { _id: "CART-1" },
  {
    $pull: { items: { lineId: "L2" } },
    $inc: { totalMinor: -300000 }
  }
);
~~~

Các phép cập nhật trên **cùng document** là nguyên tử, nhưng lệnh trên có thể vẫn **giảm tổng dù dòng L2 đã bị xóa trước đó**, vì filter ngoài chỉ chọn `_id`. Retry có thể trừ tiền hai lần. Nếu ứng dụng chọn cách này, phải kèm điều kiện bảo đảm dòng hàng cần xóa còn tồn tại và quy tắc concurrency/idempotency phù hợp, hoặc chọn pipeline tính lại tổng từ dữ liệu hiện tại.

Điểm cốt lõi là **xóa được phần tử chưa chắc hoàn thành nghiệp vụ**; cần xét các invariant phụ thuộc mảng.

---

## 13. Giới hạn kích thước, index và hiệu năng

### 13.1. MongoDB vẫn giới hạn một document 16 MiB

Một mảng lớn có thể làm document chạm giới hạn BSON **16 MiB**. Các toán tử xóa giúp giảm số phần tử, nhưng không biến mảng tăng vô hạn thành mô hình tốt. Nếu danh sách lịch sử có thể chứa hàng triệu bản ghi, tách thành collection riêng với khóa tham chiếu thường bền vững hơn.

Ví dụ không nên để toàn bộ lịch sử đơn hàng trong:

~~~javascript
{
  _id: "CUSTOMER-1",
  orders: [ /* nhiều năm lịch sử đơn hàng */ ]
}
~~~

Nếu các đơn hàng có vòng đời độc lập, dùng collection `orders` với `customerId` và index phù hợp. Lúc đó thao tác xóa một đơn hàng khỏi lịch sử cần được thiết kế theo chính sách nghiệp vụ và lưu trữ, thay vì đơn giản xóa một phần tử trong document khách hàng.

### 13.2. Xóa phần tử có thể tác động tới multikey index

Nếu một field mảng tham gia **multikey index**, việc thêm/xóa phần tử có thể yêu cầu cập nhật index entries. Ví dụ:

~~~javascript
db.products.createIndex({ tags: 1 });
~~~

Sau đó:

~~~javascript
db.products.updateOne(
  { _id: "P1" },
  { $pull: { tags: "obsolete" } }
);
~~~

Việc cập nhật mảng phải duy trì dữ liệu index phù hợp. Với array rất lớn, cập nhật thường xuyên và nhiều index, chi phí ghi có thể đáng kể. Không nên giả định rằng xóa một chuỗi nhỏ trong mảng luôn có chi phí cố định rất thấp.

### 13.3. Chọn được document cần sửa bằng index

Toán tử `$pull` vận hành trên mảng **của document đã được chọn**. Đường tìm document trước khi sửa vẫn rất quan trọng:

~~~javascript
db.carts.updateOne(
  { _id: "CART-1" },
  { $pull: { items: { lineId: "L2" } } }
);
~~~

Filter theo `_id` có thể dùng index mặc định để tìm nhanh cart. Ngược lại, một `updateMany` với filter không có index trên collection rất lớn có thể phải quét nhiều document rồi mới thực hiện cập nhật.

Một phép `explain` trên truy vấn đọc có cùng filter là cách hữu ích để hiểu chiến lược tìm document; việc tối ưu index cho truy vấn và chi phí cập nhật mảng cần được đánh giá cùng nhau.

### 13.4. Xóa hàng loạt phần tử trên nhiều document

Giả sử 500.000 user có mảng `roles`, cần bỏ quyền cũ. Có thể dùng:

~~~javascript
db.users.updateMany(
  { roles: "LEGACY" },
  { $pull: { roles: "LEGACY" } }
);
~~~

Filter ngoài tránh cập nhật những user không có role này (và có thể tận dụng index multikey nếu phù hợp). Tuy nhiên, dữ liệu lớn vẫn cần kế hoạch về tải ghi, replication, giám sát và kết quả từng lượt. Một `updateMany` có lỗi giữa chừng không tự rollback toàn bộ document đã sửa.

### 13.5. Đối với danh sách “giữ N phần tử mới nhất”

Nếu mục tiêu là giữ đúng **N giá trị gần đây**, không nhất thiết phải gọi `$pop: -1` trong vòng lặp sau mỗi lần thêm. MongoDB hỗ trợ `$push` với modifier `$each` và `$slice` để giới hạn kích thước mảng:

~~~javascript
db.userActivity.updateOne(
  { _id: "U1" },
  {
    $push: {
      recentActions: {
        $each: [
          { actionId: "A100", happenedAt: new Date() }
        ],
        $slice: -20
      }
    }
  }
);
~~~

Đây là cách thêm một phần tử và giữ **20 phần tử cuối theo thứ tự mảng** trong một update. Nếu thứ tự thời gian và thứ tự thêm không giống nhau, phải định nghĩa thêm quy tắc sắp xếp và xử lý sự kiện đến muộn. Không coi modifier `$slice` là chính sách lưu giữ lịch sử đầy đủ; các phần tử bị cắt mất khỏi mảng hiện tại.

---

## 14. Sử dụng trong Java MongoDB Sync Driver

MongoDB Java Sync Driver cho phép truyền update dưới dạng `Bson`, ví dụ `org.bson.Document`. Cách này minh họa trực tiếp mối liên hệ giữa lệnh `mongosh` và mã Java.

### 14.1. `$pull` với giá trị scalar

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public class ArrayRemovalExamples {
    public static void removeVip(MongoCollection<Document> collection) {
        UpdateResult result = collection.updateOne(
            Filters.eq("_id", "TAGS-PULL"),
            new Document(
                "$pull",
                new Document("tags", "vip")
            )
        );

        System.out.printf(
            "matched=%d modified=%d%n",
            result.getMatchedCount(),
            result.getModifiedCount()
        );
    }
}
~~~

Từ Java, cách biểu đạt cũng giống `mongosh`:

~~~javascript
{
  $pull: {
    tags: "vip"
  }
}
~~~

Khi dùng write concern không xác nhận (unacknowledged), một số phương thức đọc kết quả không áp dụng như trường hợp acknowledged; ứng dụng cần sử dụng cấu hình xác nhận phù hợp.

### 14.2. `$pull` với điều kiện trên embedded document

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public class RemoveCompletedTasks {
    public static void run(MongoCollection<Document> collection) {
        Document condition = new Document("status", "DONE")
            .append("points", new Document("$gte", 8));

        Document update = new Document(
            "$pull",
            new Document("tasks", condition)
        );

        collection.updateOne(
            Filters.eq("_id", "TASKS-PULL"),
            update
        );
    }
}
~~~

Đoạn code dùng điều kiện cho **mỗi document bên trong `tasks`**. Nó không xóa cả document `TASKS-PULL`.

### 14.3. `$pullAll`

~~~java
import java.util.List;
import org.bson.Document;
import com.mongodb.client.model.Filters;

collection.updateOne(
    Filters.eq("_id", "TAGS-ALL"),
    new Document(
        "$pullAll",
        new Document("tags", List.of("red", "blue"))
    )
);
~~~

Nếu mục đích là loại các phần tử bằng đúng các chuỗi xác định, danh sách Java ở đây ánh xạ trực tiếp sang BSON array.

### 14.4. `$pop`

~~~java
// Xóa phần tử cuối:
collection.updateOne(
    Filters.eq("_id", "QUEUE-POP"),
    new Document("$pop", new Document("queue", 1))
);

// Xóa phần tử đầu:
collection.updateOne(
    Filters.eq("_id", "QUEUE-POP"),
    new Document("$pop", new Document("queue", -1))
);
~~~

Hai lệnh trên chạy liên tiếp sẽ xóa **hai phần tử**, mỗi lệnh một phần tử ở đầu/cuối tại thời điểm lệnh đó chạy. Đừng gọi cả hai trong cùng nghiệp vụ nếu chỉ định xóa một phần tử.

### 14.5. Dùng builder của Java Driver

Với thao tác phổ biến, Java Driver có các builder trong `Updates`:

~~~java
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.pull;

collection.updateOne(
    eq("_id", "TAGS-PULL"),
    pull("tags", "vip")
);
~~~

Cách dùng builder giúp tránh viết tên toán tử bằng string trong nhiều chỗ. Với update phức tạp hoặc pipeline, vẫn có thể tạo BSON bằng builder hoặc `Document` theo API và phiên bản driver được triển khai.

### 14.6. Spring Data MongoDB

Với Spring Data MongoDB, có thể diễn đạt cùng thao tác bằng `Query` và `Update`:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class RemoveUserRole {
    private final MongoTemplate mongoTemplate;

    public RemoveUserRole(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void revoke(String userId, String role) {
        Query query = new Query(
            Criteria.where("_id").is(userId)
        );

        Update update = new Update().pull("roles", role);

        mongoTemplate.updateFirst(
            query,
            update,
            "users"
        );
    }
}
~~~

Đây là cùng ý tưởng `$pull` trong MongoDB. Nếu hệ thống lưu role và quyền ở nhiều document/collection, cần xử lý thêm các bất biến và hiệu lực quyền ở tầng nghiệp vụ.

---

## 15. Phân biệt `$pull` với các cách cập nhật/xóa khác

MongoDB có nhiều toán tử liên quan tới array và document. Chúng không thể thay thế nhau tùy ý:

| Mục tiêu | Công cụ thường phù hợp | Điều cần nhớ |
| --- | --- | --- |
| Xóa hẳn document khỏi collection | `deleteOne` / `deleteMany` | Tác động lên document, không chỉ một phần tử mảng. |
| Bỏ field `tags` khỏi document | `$unset: { tags: "" }` | Xóa **toàn bộ field**, không chỉ một giá trị trong mảng. |
| Xóa mọi phần tử khớp điều kiện | `$pull` | Có thể xóa nhiều phần tử. |
| Xóa mọi lần xuất hiện của những giá trị cụ thể | `$pullAll` | Dùng danh sách giá trị. |
| Xóa phần tử đầu/cuối mảng | `$pop` | Theo vị trí, không theo nội dung. |
| Đổi giá trị phần tử đang tồn tại | `$set` với vị trí hoặc `arrayFilters` | Cập nhật, không xóa. |
| Thêm giá trị vào mảng | `$push` | Có thể thêm trùng. |
| Thêm nếu chưa có giá trị tương ứng | `$addToSet` | Hạn chế thêm trùng theo ngữ nghĩa so sánh, không làm sạch mọi bản trùng đã có từ trước. |
| Giữ những phần tử đạt điều kiện bằng cách dựng lại mảng | Update pipeline + `$filter` | Hữu ích khi cần tính lại các field dẫn xuất trong cùng document. |
| Xóa một giá trị theo index bằng `$unset` | Thường không phù hợp | Có thể để lại `null` tại vị trí đó. |

Ví dụ, nếu muốn **xóa tất cả vai trò của người dùng**, không cần `$pull` cho từng role riêng lẻ:

~~~javascript
db.users.updateOne(
  { _id: "U1" },
  { $set: { roles: [] } }
);
~~~

Nhưng thao tác này xóa cả những role còn hợp lệ. Khi chỉ muốn thu hồi `"LEGACY"`, dùng `$pull` diễn đạt yêu cầu hẹp và an toàn hơn.

Nếu muốn **xóa field `roles` hoàn toàn** (phân biệt field thiếu với mảng rỗng):

~~~javascript
db.users.updateOne(
  { _id: "U1" },
  { $unset: { roles: "" } }
);
~~~

Cách chọn `[]` hay field thiếu phụ thuộc hợp đồng schema và ý nghĩa của dữ liệu.

---

## 16. Mã lỗi, kết quả và xử lý API

### 16.1. Phân biệt tìm thấy document với thực sự thay đổi

~~~javascript
const result = db.users.updateOne(
  { _id: "U1" },
  { $pull: { roles: "LEGACY" } }
);

printjson({
  matchedCount: result.matchedCount,
  modifiedCount: result.modifiedCount,
  acknowledged: result.acknowledged
});
~~~

Có ba tình huống thông thường:

| Trạng thái | `matchedCount` | `modifiedCount` | Diễn giải |
| --- | --- | --- | --- |
| Không tìm được user | 0 | 0 | Filter ngoài không khớp document nào. |
| Tìm user, role đã không còn | 1 | 0 | Không có phần tử phù hợp để xóa. |
| Tìm user và loại được role | 1 | 1 | **Document đã thay đổi**; `modifiedCount` đếm document, không đếm phần tử bị xóa. |

Nếu `$pull` loại 10 phần tử trong **một** document, `modifiedCount` vẫn thường là **1**, không phải 10. Muốn biết số phần tử đã bị loại, cần logic riêng (ví dụ so sánh độ dài trước/sau có kiểm soát, hoặc tính toán trên dữ liệu trong pipeline), chú ý cập nhật đồng thời.

### 16.2. Lỗi khi field không phải array

Một thao tác `$pull` trên field chứa string/object scalar có thể gây write error. Không nên retry vô hạn với cùng payload; cần sửa dữ liệu hoặc schema. Ở ứng dụng Java, bắt loại exception từ driver/Spring Data thích hợp và trả phản hồi nghiệp vụ mà không lộ document nhạy cảm.

### 16.3. Quyền truy cập và validation

Update array vẫn chịu **quyền ghi**, **schema validator** và các ràng buộc khác của collection. Ví dụ, nếu validator yêu cầu `roles` luôn có ít nhất một phần tử, lệnh `$pull` làm array trống có thể bị từ chối.

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    properties: {
      roles: {
        bsonType: "array",
        minItems: 1
      }
    }
  }
}
~~~

Đây là ví dụ một phần validator, không phải cấu hình toàn collection có thể chạy độc lập. Nó cho thấy kết quả của cập nhật phải xét ràng buộc **sau khi cập nhật**, không chỉ xét tính hợp lệ của điều kiện `$pull`.

### 16.4. Bảo mật thao tác xóa theo ID

Một API chẳng hạn:

~~~text
DELETE /carts/CART-1/items/L2
~~~

Không nên chỉ dùng `_id: "CART-1"` lấy từ URL. Cần xác thực và kiểm tra người dùng có quyền sửa cart đó hay không. Có thể đưa điều kiện chủ sở hữu vào filter cập nhật:

~~~javascript
db.carts.updateOne(
  {
    _id: "CART-1",
    ownerId: "AUTHENTICATED-USER-ID",
    status: "OPEN"
  },
  {
    $pull: {
      items: { lineId: "L2" }
    }
  }
);
~~~

Giá trị `ownerId` cần lấy từ ngữ cảnh xác thực đáng tin cậy, không tin vào chuỗi người dùng tự gửi. Nếu `matchedCount = 0`, có thể cart không tồn tại, không thuộc quyền truy cập hoặc trạng thái không cho sửa; cách trả thông báo cần tuân theo chính sách bảo mật của API.

---

## 17. Tình huống thực tế

### 17.1. Thu hồi nhiều quyền cũ

**Yêu cầu:** User có mảng `roles: ["USER", "EDITOR", "GUEST", "EDITOR"]`. Cần bỏ `EDITOR` và `GUEST`, giữ `USER`.

~~~javascript
db.users.updateOne(
  { _id: "U1" },
  {
    $pullAll: {
      roles: ["EDITOR", "GUEST"]
    }
  }
);
~~~

**Kết quả:** `roles: ["USER"]`. Mọi bản trùng EDITOR đều bị loại.

**Vì sao không dùng `$pop`?** Role cần bỏ không gắn với vị trí đầu/cuối.

### 17.2. Dọn comment đã được kiểm duyệt

**Yêu cầu:** Xóa tất cả comment trong document bài viết có `status = "REJECTED"`.

~~~javascript
db.posts.updateOne(
  { _id: "POST-1" },
  {
    $pull: {
      comments: { status: "REJECTED" }
    }
  }
);
~~~

**Lưu ý:** Nếu cần giữ comment đã bị từ chối cho kiểm toán hoặc khiếu nại, xóa hẳn có thể trái yêu cầu nghiệp vụ. Trong trường hợp đó, nên giữ bản ghi và thay trạng thái hiển thị, hoặc chuyển sang kho lưu trữ phù hợp.

### 17.3. Loại sự kiện hết hạn dựa trên thời gian

**Yêu cầu:** Mảng sự kiện chỉ cần giữ những sự kiện trong thời hạn; sự kiện cũ cần loại.

~~~javascript
const cutoff = ISODate("2026-11-01T00:00:00Z");

db.sessions.updateOne(
  { _id: "SESSION-1" },
  {
    $pull: {
      events: {
        occurredAt: { $lt: cutoff }
      }
    }
  }
);
~~~

Mọi document sự kiện có `occurredAt < cutoff` sẽ bị loại. Cần thống nhất múi giờ và cách xác định hạn lưu. Khi dữ liệu quá lớn hoặc cần xóa theo thời hạn quy mô lớn, tách sự kiện thành collection riêng với chính sách retention/TTL phù hợp có thể dễ vận hành hơn.

### 17.4. Bỏ phần tử cuối của một danh sách thao tác ngắn

**Yêu cầu:** Một document lưu `recentSteps` theo thứ tự và UI có hành động bỏ **bước cuối cùng hiện tại**.

~~~javascript
db.editorSessions.updateOne(
  { _id: "EDIT-1" },
  { $pop: { recentSteps: 1 } }
);
~~~

Nếu UI định nghĩa “undo bước X vừa hiển thị”, cần đảm bảo không có client khác thêm bước Y trước khi thao tác; nếu có cập nhật đồng thời, cần dùng version/checkpoint hoặc model undo riêng. `$pop` chỉ có ngữ nghĩa loại phần tử cuối **ở thời điểm cập nhật**.

### 17.5. Xóa item theo mã hàng có thể trùng

**Yêu cầu:** Giỏ có hai dòng cùng `sku` nhưng khác tùy chọn giao hàng. Người dùng yêu cầu xóa **một dòng**.

~~~javascript
{
  items: [
    { lineId: "L1", sku: "P42", shipping: "STANDARD" },
    { lineId: "L2", sku: "P42", shipping: "EXPRESS" }
  ]
}
~~~

Không dùng:

~~~javascript
{ $pull: { items: { sku: "P42" } } }
~~~

vì lệnh xóa **cả hai** dòng. Dùng khóa `lineId`:

~~~javascript
{ $pull: { items: { lineId: "L2" } } }
~~~

Sự khác nhau này xuất phát từ mô hình nghiệp vụ, không phải từ việc toán tử nào “mạnh hơn”.

---

## 18. Bài tập thực hành có đáp án

Các bài tập dưới đây dùng dữ liệu minh họa riêng. Hãy dự đoán trạng thái mảng, rồi mới thực hiện trong collection thử nghiệm.

### Bài 1 — Xóa mọi lần xuất hiện

Ban đầu:

~~~javascript
{ _id: 1, tags: ["A", "B", "A", "C"] }
~~~

Lệnh:

~~~javascript
db.samples.updateOne(
  { _id: 1 },
  { $pull: { tags: "A" } }
);
~~~

**Đáp án:** `tags: ["B", "C"]`. Không còn giá trị `"A"` ở bất kỳ vị trí nào.

### Bài 2 — Xóa nhiều giá trị

Ban đầu:

~~~javascript
{ _id: 2, roles: ["ADMIN", "EDITOR", "READER", "EDITOR"] }
~~~

Lệnh:

~~~javascript
db.samples.updateOne(
  { _id: 2 },
  { $pullAll: { roles: ["EDITOR", "READER"] } }
);
~~~

**Đáp án:** `roles: ["ADMIN"]`. Mọi lần xuất hiện của các giá trị đã liệt kê đều bị loại.

### Bài 3 — Phân biệt đầu và cuối

Ban đầu:

~~~javascript
{ _id: 3, values: [10, 20, 30] }
~~~

- `$pop: { values: -1 }` -> `[20, 30]`.
- `$pop: { values: 1 }` -> `[10, 20]`.

Hai kết quả được tính **độc lập từ mảng ban đầu**. Nếu chạy hai lệnh nối tiếp trên cùng document, kết quả sẽ khác.

### Bài 4 — Xóa document con theo điều kiện

Ban đầu:

~~~javascript
{
  _id: 4,
  attempts: [
    { id: "A1", passed: false, score: 40 },
    { id: "A2", passed: true, score: 90 },
    { id: "A3", passed: false, score: 85 }
  ]
}
~~~

Yêu cầu: xóa mọi attempt **không đạt** và có điểm **dưới 50**.

~~~javascript
db.samples.updateOne(
  { _id: 4 },
  {
    $pull: {
      attempts: {
        passed: false,
        score: { $lt: 50 }
      }
    }
  }
);
~~~

**Đáp án:** chỉ `A1` bị xóa; `A2` và `A3` vẫn ở lại.

### Bài 5 — Mảng con chỉ trong nhóm ENG

Ban đầu:

~~~javascript
{
  _id: 5,
  groups: [
    { code: "ENG", users: ["A", "B"] },
    { code: "OPS", users: ["B", "C"] }
  ]
}
~~~

Yêu cầu: xóa user B **chỉ trong nhóm ENG**.

~~~javascript
db.samples.updateOne(
  { _id: 5 },
  {
    $pull: {
      "groups.$[g].users": "B"
    }
  },
  {
    arrayFilters: [{ "g.code": "ENG" }]
  }
);
~~~

**Đáp án:** ENG còn `["A"]`, OPS vẫn là `["B", "C"]`.

### Bài 6 — Bẫy của `$pop` và retry

Ban đầu `queue: ["J1", "J2", "J3"]`. Client gửi `$pop: { queue: 1 }`, không nhận phản hồi vì mất kết nối, rồi **gửi lại cùng thao tác như một lệnh mới**.

**Đáp án:** Nếu thao tác thứ nhất thực sự đã ghi và thao tác thứ hai cũng được thực thi độc lập, kết quả có thể là `["J1"]`, vì `"J3"` rồi `"J2"` lần lượt bị xóa. Không nên retry mù thao tác theo vị trí. Cần idempotency, xác nhận trạng thái hoặc thao tác theo định danh cụ thể.

### Bài 7 — `modifiedCount` và số phần tử bị xóa

Ban đầu `tags: ["x", "x", "x", "y"]`. Gọi `$pull: { tags: "x" }`.

**Đáp án:** ba phần tử bị xóa, document trở thành `tags: ["y"]`; tuy nhiên `modifiedCount` đối với một `updateOne` được xác nhận là **1**, vì nó đếm số **document được thay đổi**, không đếm số phần tử mảng bị loại.

### Bài 8 — Thiết kế giỏ hàng

Một cart chứa `items` và `totalMinor`. API yêu cầu loại dòng `L5` mà không làm tổng tiền bị sai. Hãy nêu:

1. Cách xác định đúng dòng cần xóa.
2. Cách ngăn thao tác khi cart đã `CHECKED_OUT`.
3. Vì sao chỉ dùng `$pull` có thể chưa đủ.
4. Cách tránh giảm tổng tiền hai lần khi API retry.
5. Trường hợp nào nên dùng pipeline update tính lại tổng từ mảng còn lại.

**Gợi ý:** dùng filter ngoài theo `_id`, chủ sở hữu và `status: "OPEN"`; dùng `lineId` cho điều kiện loại; duy trì trường tổng trong cùng thao tác nguyên tử hoặc tính lại từ nguồn mảng; tránh ghép `$inc` vô điều kiện với thao tác xóa có thể lặp lại.

---

## 19. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “`$pull` chỉ xóa một phần tử đầu tiên tìm thấy.” | Nó xóa **tất cả phần tử** khớp giá trị/điều kiện. |
| “`$pullAll` chỉ xóa tối đa một lần cho mỗi giá trị liệt kê.” | Nó xóa **mọi lần xuất hiện** của từng giá trị. |
| “`$pullAll` dùng được với mọi điều kiện `$gte`, `$regex`.” | Nó là danh sách **giá trị**, không phải toán tử điều kiện tổng quát; dùng `$pull` cho predicate. |
| “`$pop: 3` nghĩa là xóa ba phần tử cuối.” | `$pop` dùng `1` hoặc `-1` để chọn đầu/cuối, mỗi thao tác xóa một phần tử. |
| “`$pop` xóa đúng item mà client vừa thấy ở cuối.” | Nó xóa item đang ở cuối **lúc update chạy**; có thể đã bị thay đổi bởi client khác. |
| “`$pull` một item là xóa cả document.” | Chỉ sửa field mảng của document, không xóa document cha. |
| “Xóa theo `sku` sẽ luôn xóa đúng một dòng hàng.” | Nếu nhiều dòng trùng `sku`, tất cả dòng khớp sẽ bị xóa; nên dùng định danh dòng. |
| “Phải bao `$elemMatch` cho hai field của object trong `$pull`.” | Với mảng object, điều kiện `$pull` trực tiếp được áp dụng cho **từng object**; `$elemMatch` có thể cần cho một **mảng con** trong object. |
| “Field không tồn tại sẽ được MongoDB tạo thành `[]` trước khi xóa.” | Thường không thay đổi gì nếu field không tồn tại. |
| “Field scalar `"a"` sẽ được coi như `["a"]`.” | Toán tử xóa mảng đòi giá trị array phù hợp. |
| “`modifiedCount = 1` nghĩa là một phần tử đã bị loại.” | Nó đếm **document**, một document có thể mất nhiều phần tử. |
| “`updateMany` là transaction nguyên tử trên mọi document.” | Nguyên tử từng document; nhiều document không tự cùng commit/rollback. |
| “`$pull` luôn bảo đảm `totalMinor` được cập nhật.” | Các trường dẫn xuất phải có quy tắc cập nhật riêng. |
| “Lặp lại `$pop` sau timeout luôn an toàn.” | Lần lặp có thể xóa thêm phần tử mới ở đầu/cuối. |
| “`$unset` vào vị trí mảng là cách xóa phần tử tương đương `$pull`.” | `$unset` có thể để lại `null` ở vị trí đó. |

## 20. Tài liệu MongoDB chính thức

- [`$pull` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/update/pull/): xóa mọi phần tử mảng khớp điều kiện hoặc giá trị.
- [`$pullAll` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/update/pullAll/): xóa các giá trị trong danh sách chỉ định.
- [`$pop` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/update/pop/): xóa phần tử đầu hoặc cuối.
- [Filtered Positional Operator `$[identifier]`](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/): chọn phần tử của mảng ngoài bằng `arrayFilters`.
- [`$push` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/update/push/): thêm phần tử và các modifier như `$slice`.
- [`$filter` — Aggregation](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/): tạo mảng chỉ chứa phần tử thỏa điều kiện trong pipeline update.
- [`updateOne()` và `updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/): kết quả cập nhật và phạm vi thao tác.
- [Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/): cập nhật field và dùng các toán tử update trong Java.

Khi chọn giữa ba toán tử, cần hỏi chính xác **“mình đang chỉ định phần tử bằng giá trị, bằng điều kiện hay bằng vị trí?”**. `$pull` phù hợp với giá trị/điều kiện, `$pullAll` phù hợp với danh sách giá trị cụ thể, còn `$pop` phù hợp khi chỉ cần bỏ đầu hoặc cuối. Trong ứng dụng thật, lựa chọn đó phải đi cùng **định danh phần tử ổn định, kiểu dữ liệu nhất quán, kiểm soát đồng thời và duy trì bất biến của document** để việc loại một phần tử không vô tình làm sai nghiệp vụ.
