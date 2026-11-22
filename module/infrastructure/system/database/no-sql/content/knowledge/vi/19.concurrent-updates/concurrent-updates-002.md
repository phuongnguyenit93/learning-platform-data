# Lost update, ghi đè giá trị và cách tái hiện

Trong một ứng dụng dùng cơ sở dữ liệu NoSQL, hai request có thể đọc **cùng một giá trị cũ**, tự tính kết quả mới rồi lần lượt ghi đè lên một trường. Cả hai lệnh ghi đều có thể được DBMS xác nhận thành công, nhưng kết quả của một request **biến mất khỏi trạng thái cuối cùng**. Đây là hiện tượng **lost update** (*cập nhật bị mất*).

Ví dụ một cửa hàng có 10 sản phẩm trong kho. Hai khách đồng thời mua mỗi người 1 sản phẩm:

~~~text
Ban đầu: available = 10

Request A đọc available = 10
Request B đọc available = 10

A tính 10 - 1 = 9
B tính 10 - 1 = 9

A ghi available = 9
B ghi available = 9

Kết quả lưu: available = 9
Kết quả đúng nếu hai đơn đều được chấp nhận: available = 8
~~~

**Một lần giảm tồn đã bị mất**, mặc dù cả hai request đều có thể nhận phản hồi ghi thành công. Lỗi không nằm ở phép trừ. Nó nằm ở việc hai request **đưa quyết định ghi dựa trên cùng một trạng thái đã lỗi thời** mà không có cơ chế phát hiện hoặc phối hợp tranh chấp.

Bài học thuộc chương **Cập nhật đồng thời** của module **Database No SQL**. Nội dung tập trung vào:

1. Hiểu chính xác lost update và sự khác nhau giữa **ghi đè toàn document**, **ghi đè một field** và **cập nhật nguyên tử**.
2. Tái hiện lỗi theo một lịch chạy có kiểm soát thay vì phụ thuộc vào may rủi của chương trình đa luồng.
3. Hiểu vì sao **atomicity của từng lệnh ghi** chưa đủ để bảo vệ chuỗi **đọc – tính toán – ghi**.
4. Khắc phục bằng **server-side atomic update**, **conditional write / compare-and-set (CAS)**, **version/revision**, transaction và retry đúng cách.
5. Đối chiếu MongoDB, Redis, DynamoDB và Cassandra, đồng thời nhận diện những lỗi còn lại liên quan đến **idempotency**, **write skew**, replication và thao tác nhiều bản ghi.

## 1. Một thao tác có ba bước và một cửa sổ rủi ro

Một thao tác tăng/giảm trường trong code ứng dụng thường được viết theo kiểu:

~~~text
1. READ:    lấy trạng thái hiện tại từ DB
2. MODIFY:  tính trạng thái mới trong ứng dụng
3. WRITE:   ghi trạng thái mới xuống DB
~~~

Mẫu này được gọi là **read-modify-write**. Nó không tự sai; vấn đề là **khoảng thời gian giữa lần đọc và lần ghi**:

~~~text
       READ                       WRITE
        │                           │
        ▼                           ▼
Ứng dụng giữ một bản sao --------> Ghi dựa trên bản sao
          \_____________________/
           Cửa sổ tranh chấp

Trong khoảng này, client khác có thể cập nhật cùng dữ liệu.
~~~

Một câu lệnh DBMS như `updateOne` có thể được thực thi nguyên tử ở phạm vi một document, nhưng **toàn bộ chuỗi ba bước trong ứng dụng** không vì thế mà nguyên tử.

### Ví dụ đếm lượt thích

~~~javascript
// Minh họa cách làm dễ gây lost update.
const post = await posts.findOne({ _id: "POST-7" });
const nextCount = post.likeCount + 1;

await posts.updateOne(
  { _id: "POST-7" },
  { $set: { likeCount: nextCount } }
);
~~~

Nếu hai người cùng đọc `likeCount = 100`, cả hai có thể ghi `101`. Kết quả đúng về tổng lượt tăng là `102`.

**Điểm cốt lõi:** một phép toán có dạng “lấy giá trị hiện tại rồi cộng/trừ” không nên mặc định được triển khai bằng cách **đọc ra ứng dụng, tính và ghi đè** khi nhiều writer có thể cạnh tranh.

## 2. Ghi đè giá trị có nghĩa là gì?

**Ghi đè** (*overwrite*) là việc một writer thay giá trị hiện có bằng giá trị mới. Ghi đè có thể là hành vi hoàn toàn hợp lệ hoặc là nguyên nhân mất cập nhật, tùy ngữ nghĩa.

### Ghi đè có chủ đích

Một admin cập nhật nội dung mô tả sản phẩm:

~~~text
description: "Sổ tay 100 trang"
       ↓
description: "Sổ tay 120 trang"
~~~

Nếu đây là thay đổi mới nhất được chủ động chấp nhận, thay thế giá trị cũ có thể đúng.

### Ghi đè dựa trên bản sao cũ

Người A và người B cùng mở form chỉnh sửa:

~~~text
Ban đầu:
  title       = "Sổ tay"
  description = "100 trang"
  revision    = 4

A mở form ở revision 4, sửa title thành "Sổ tay A5".
B mở form ở revision 4, sửa description thành "120 trang".

A ghi cả object:
  title       = "Sổ tay A5"
  description = "100 trang"

B ghi cả object:
  title       = "Sổ tay"
  description = "120 trang"
~~~

Nếu B ghi cuối, **sửa title của A có thể biến mất**, dù hai người sửa hai trường khác nhau. Nguyên nhân là B gửi lại **bản object cũ cùng những trường mình không định sửa**.

### Phân biệt ba cách cập nhật

| Cách làm | Ví dụ | Nguy cơ |
| --- | --- | --- |
| Thay toàn document | `replaceOne` bằng bản sao đọc trước | Dễ ghi đè cả các field mà writer không chủ ý sửa |
| Ghi một trường với giá trị tính từ bản đọc cũ | `$set: {count: oldCount + 1}` | Có thể mất một lần tăng/giảm |
| Biểu diễn phép thay đổi ngay tại DBMS | `$inc: {count: 1}` | Tránh lost update cho phép tăng một trường ở phạm vi nguyên tử thích hợp |

**Không phải mọi `$set` đều xấu.** Nếu request có ý định “đặt tên là X bất kể tên trước đó”, `$set` có thể là phép cập nhật đúng. Nhưng nếu ý định là “cộng thêm 1 vào giá trị hiện tại”, ghi `$set` bằng giá trị tính từ snapshot cũ **không biểu diễn đúng ý định đồng thời**.

## 3. Lịch thực thi (*interleaving*) giải thích lost update

Cho `count = 10` và hai transaction logic:

~~~text
T1: count = count + 1
T2: count = count + 1
~~~

### Lịch tuần tự an toàn

~~~text
Thời điểm | T1                    | T2
--------- | --------------------- | ---------------------
1         | Đọc count = 10        |
2         | Ghi count = 11        |
3         |                       | Đọc count = 11
4         |                       | Ghi count = 12

Kết quả: count = 12
~~~

### Lịch chồng xen gây mất cập nhật

~~~text
Thời điểm | T1                    | T2
--------- | --------------------- | ---------------------
1         | Đọc count = 10        |
2         |                       | Đọc count = 10
3         | Tính next = 11        |
4         |                       | Tính next = 11
5         | Ghi count = 11        |
6         |                       | Ghi count = 11

Kết quả: count = 11
~~~

Cả T1 và T2 đều có thể nói “lệnh ghi của tôi đã thực thi”, nhưng hiệu ứng logic **hai lần tăng** chỉ được lưu dưới dạng một lần tăng.

### “Ai ghi sau thì thắng” không giải quyết ý định nghiệp vụ

Nếu lệnh ghi là “đặt ảnh đại diện thành ảnh mới”, chính sách **last writer wins** đôi khi được chấp nhận. Nhưng đối với “cộng điểm”, “trừ hàng”, “ghi hai phần của một đơn”, “trừ số dư”, mất một hiệu ứng là lỗi nghiệp vụ.

Phải phân biệt:

- **Giá trị cuối**: DB còn thấy 11.
- **Tập hiệu ứng đã được ứng dụng xác nhận**: hai người tăng một lần.
- **Bất biến mong muốn**: kết quả phải phản ánh hai lần tăng, tức 12.

Lost update được nhận diện khi một hiệu ứng hợp lệ, đã được ứng dụng chấp nhận theo ngữ nghĩa, **không còn hiện diện trong trạng thái cuối**.

## 4. Lost update có phải lỗi riêng của NoSQL?

Không. Lost update có thể xuất hiện khi lập trình viên dùng read-modify-write không được bảo vệ trong **SQL, NoSQL, file storage hay bộ nhớ chia sẻ**.

Trong NoSQL, hiện tượng này đáng chú ý vì:

- Nhiều API cung cấp lệnh **get–put** rất đơn giản nên dễ khiến ứng dụng thực hiện logic ở client.
- Dữ liệu có thể nằm ở nhiều **document/partition** với các ranh giới atomicity khác nhau.
- Một số hệ ưu tiên khả năng mở rộng và hỗ trợ **eventual consistency** ở các đường đọc phụ.
- Giao thức update, CAS, transaction hoặc LWT khác nhau theo DBMS.
- Client có thể retry sau timeout và tạo thêm tác động nếu không dùng idempotency.

**Không thể kết luận “NoSQL cho phép lost update” như một đặc tính bắt buộc.** Nhiều hệ có những phép cập nhật nguyên tử và điều kiện đủ để ngăn lỗi này trong phạm vi thiết kế. Trách nhiệm của người thiết kế là chọn đúng thao tác và mô hình dữ liệu.

## 5. Nguyên tử của một lần ghi khác nguyên tử của read-modify-write

MongoDB chẳng hạn bảo đảm một lần cập nhật một document được thực thi **nguyên tử ở phạm vi document**. Nhưng xem đoạn:

~~~javascript
const doc = await collection.findOne({ _id: "counter" });
const next = doc.value + 1;

await collection.updateOne(
  { _id: "counter" },
  { $set: { value: next } }
);
~~~

Có hai thao tác DB riêng:

~~~text
findOne()          → trả snapshot ở thời điểm đọc
updateOne($set)    → ghi đúng giá trị next đã tính
~~~

`updateOne` không thể tự biết rằng `next` được tính từ một giá trị **đã lỗi thời**. Nó thực hiện yêu cầu “đặt value bằng next” và có thể thành công ngay cả khi một writer khác đã cập nhật document ở giữa.

Nếu ý định là tăng, hãy biểu diễn ý định trực tiếp:

~~~javascript
await collection.updateOne(
  { _id: "counter" },
  { $inc: { value: 1 } }
);
~~~

Hai lệnh `$inc` đối với cùng một document được áp dụng theo ngữ nghĩa cập nhật nguyên tử của MongoDB; mỗi lần tăng **tác động lên giá trị hiện tại tại lúc cập nhật**, không phải số cũ đã tính ở ứng dụng.

> **Phạm vi bảo đảm:** giải pháp `$inc` đúng cho phép tăng/giảm đơn giản trong một document, nếu kiểu dữ liệu hợp lệ và các writer khác không ghi đè trường theo lối cũ. Nó không tự bảo vệ một nghiệp vụ liên quan nhiều document hoặc một lần gọi bị gửi lặp lại sau timeout.

## 6. Tái hiện lỗi bằng một lịch chạy có kiểm soát

Để học lost update, không nhất thiết tạo hàng nghìn request rồi hy vọng có race. Ta có thể **ép hai worker đọc cùng giá trị trước khi worker nào ghi**.

Các bước:

~~~text
Khởi tạo value = 10
       │
       ├─────────────┐
       ▼             ▼
   Worker A       Worker B
   READ 10        READ 10
       │             │
       └──────┬──────┘
              ▼
      Barrier: cả hai
      đã đọc xong
              │
       ┌──────┴──────┐
       ▼             ▼
   WRITE 9         WRITE 9
       │             │
       └──────┬──────┘
              ▼
         value = 9
~~~

**Barrier** là điểm đồng bộ trong bài thử: không worker nào ghi trước khi cả hai đã hoàn thành bước đọc. Cách này tái hiện điều kiện gây lỗi **một cách ổn định**; thứ tự hai lệnh ghi không quan trọng vì cả hai đều ghi giá trị 9.

### Vì sao không dùng `sleep(100)` làm bằng chứng duy nhất?

Một chương trình:

~~~javascript
const current = await read();
await sleep(100);
await write(current - 1);
~~~

có thể làm race dễ xảy ra hơn, nhưng **không bảo đảm** hai worker đọc cùng giá trị: scheduler, tải CPU, mạng và thứ tự request có thể thay đổi. Một barrier rõ ràng giúp bài thử có kết quả được giải thích từ lịch thao tác, không dựa vào thời gian chờ may rủi.

## 7. Bài thực hành MongoDB: script tái hiện hoàn chỉnh

Ví dụ dưới đây dùng **Node.js và MongoDB driver** để tái hiện lost update với một document. Nó không cần transaction nhiều document.

### 7.1. Môi trường và phạm vi an toàn

Chuẩn bị:

- Một MongoDB **phục vụ thử nghiệm**, có thể truy cập tại `mongodb://127.0.0.1:27017`.
- Node.js và package `mongodb` phù hợp với môi trường.
- Chỉ thực hiện trên database thử nghiệm `nosql_lost_update_lab`.

Có thể cài package trong thư mục lab riêng:

~~~bash
npm init -y
npm install mongodb
~~~

Tạo file `lost-update-demo.js`. **Không chạy trên dữ liệu production**: script chủ động thay thế document demo mỗi lần chạy.

### 7.2. Script

~~~javascript
const { MongoClient } = require("mongodb");

const uri = process.env.MONGO_URL || "mongodb://127.0.0.1:27017";
const client = new MongoClient(uri);

async function resetCounter(collection) {
  await collection.replaceOne(
    { _id: "counter-demo" },
    {
      _id: "counter-demo",
      value: 10,
      revision: 0
    },
    { upsert: true }
  );
}

async function main() {
  await client.connect();

  try {
    const collection = client
      .db("nosql_lost_update_lab")
      .collection("counters");

    await resetCounter(collection);

    // Hai worker không được ghi cho đến khi CẢ HAI đã đọc.
    let readersReady = 0;
    let releaseBarrier;
    const barrier = new Promise((resolve) => {
      releaseBarrier = resolve;
    });

    async function naiveDecrement(workerName) {
      // READ: lấy một bản sao giá trị hiện tại.
      const snapshot = await collection.findOne({
        _id: "counter-demo"
      });

      console.log(workerName, "read", snapshot.value);

      readersReady++;
      if (readersReady === 2) {
        releaseBarrier();
      }

      // Chặn đến khi cả hai worker đã đọc xong.
      await barrier;

      // MODIFY: giá trị được tính từ snapshot cũ.
      const next = snapshot.value - 1;

      // WRITE: không kiểm tra value hoặc revision hiện tại.
      const result = await collection.updateOne(
        { _id: "counter-demo" },
        { $set: { value: next } }
      );

      console.log(
        workerName,
        "set value to",
        next,
        "matched",
        result.matchedCount,
        "modified",
        result.modifiedCount
      );
    }

    await Promise.all([
      naiveDecrement("A"),
      naiveDecrement("B")
    ]);

    const finalDoc = await collection.findOne({
      _id: "counter-demo"
    });

    console.log("Expected value:", 8);
    console.log("Actual value:  ", finalDoc.value);
  } finally {
    await client.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
~~~

Chạy:

~~~bash
node lost-update-demo.js
~~~

### 7.3. Kết quả cần quan sát

~~~text
A read 10
B read 10
A set value to 9 matched 1 modified 1
B set value to 9 matched 1 modified 0
Expected value: 8
Actual value:   9
~~~

Đây là **một dạng output minh họa**. Thứ tự log có thể khác. Ở lần ghi thứ hai, `matchedCount` vẫn có thể là `1`, nhưng `modifiedCount` có thể là `0` vì field đã có giá trị 9 từ lần ghi trước. Điểm quan trọng là **hai worker đều định thực hiện một lần giảm mà trạng thái cuối chỉ giảm một lần**.

### Vì sao script này tái hiện ổn định?

1. `resetCounter` đưa document về `value = 10`.
2. `barrier` bảo đảm cả A và B đã nhận `snapshot.value = 10`.
3. Cả hai tính `next = 9`.
4. Hai `updateOne` dùng filter chỉ có `_id` nên cả hai có thể khớp và thực thi.
5. Không có CAS hay server-side decrement; giá trị cuối là 9.

Đây là **lịch chồng xen cố ý tạo ra**; trên hệ thống thật, race xảy ra không phải vì có barrier, mà vì request nhiều người dùng tự nhiên chồng lên nhau đúng khoảng đọc–ghi đó.

## 8. Biện pháp 1: cập nhật nguyên tử trên server

Đối với các phép **tăng, giảm, thêm phần tử, cập nhật có điều kiện đơn giản**, cách tốt thường là chuyển phép toán vào DBMS.

### 8.1. Thay `$set` từ snapshot bằng `$inc`

~~~javascript
await collection.updateOne(
  { _id: "counter-demo" },
  { $inc: { value: -1 } }
);
~~~

Hai worker cùng thực hiện câu lệnh này sẽ làm `value: 10 → 9 → 8` theo thứ tự mà DBMS xử lý các atomic updates trên document.

Không cần:

~~~javascript
const snapshot = await collection.findOne(...);
const next = snapshot.value - 1;
~~~

vì ứng dụng **không phải tự tính giá trị mới**.

### 8.2. Tái hiện cùng hai worker với `$inc`

Sau khi chạy ví dụ lỗi, reset document:

~~~javascript
await resetCounter(collection);

await Promise.all([
  collection.updateOne(
    { _id: "counter-demo" },
    { $inc: { value: -1 } }
  ),
  collection.updateOne(
    { _id: "counter-demo" },
    { $inc: { value: -1 } }
  )
]);

const result = await collection.findOne({
  _id: "counter-demo"
});

console.log(result.value); // 8
~~~

Ví dụ là đoạn bổ sung chạy trong cùng môi trường driver, có sẵn `collection`. Không được dùng hai đoạn demo cùng lúc trên cùng document khi muốn đo từng kết quả riêng.

### 8.3. Khi cần điều kiện nghiệp vụ

Nếu `value` biểu diễn **số hàng có thể bán**, chỉ giảm khi còn đủ:

~~~javascript
const quantity = 3;

if (!Number.isSafeInteger(quantity) || quantity <= 0) {
  throw new Error("Invalid quantity");
}

const result = await inventory.updateOne(
  {
    _id: "SKU-100",
    available: { $gte: quantity }
  },
  {
    $inc: { available: -quantity }
  }
);

if (result.matchedCount !== 1) {
  // SKU không tồn tại hoặc không đủ số lượng.
}
~~~

Điều kiện `available >= quantity` và việc giảm tồn xảy ra trong **cùng lệnh atomic update của một document**. Hai khách cùng muốn mua 3 chiếc khi chỉ còn 5 chiếc không thể đều dùng chung trạng thái “còn 5” để trừ thành 2 hai lần.

**Khác biệt với code sai:** điều kiện không nằm trong một `if` của ứng dụng dựa trên snapshot cũ; nó nằm trong **filter của chính thao tác cập nhật**.

### Không dùng `$inc` cho mọi ý định

`$inc` thích hợp cho phép cộng/trừ, nhưng không tự giải quyết:

- Thay toàn bộ document cần phát hiện phiên bản xung đột.
- Bảo vệ nhiều document phải cùng cập nhật.
- Đảm bảo một request bị retry không trừ tồn hai lần.
- Cập nhật một state machine có điều kiện phức tạp.
- Số học tiền tệ có precision/overflow ngoài miền kiểu số được chọn.

Đối với những nhu cầu đó cần CAS, transaction, idempotency hoặc mô hình dữ liệu phù hợp.

## 9. Biện pháp 2: optimistic concurrency với revision

**Optimistic concurrency control (OCC)** cho phép nhiều người đọc cùng dữ liệu nhưng yêu cầu lúc ghi phải chứng minh **bản dữ liệu mình dựa vào vẫn là bản hiện tại**.

Thêm trường `revision`:

~~~json
{
  "_id": "counter-demo",
  "value": 10,
  "revision": 7
}
~~~

Client đọc `value = 10, revision = 7` rồi muốn ghi 9. Thay vì:

~~~javascript
collection.updateOne(
  { _id: "counter-demo" },
  { $set: { value: 9 } }
);
~~~

dùng:

~~~javascript
const result = await collection.updateOne(
  {
    _id: "counter-demo",
    revision: 7
  },
  {
    $set: { value: 9 },
    $inc: { revision: 1 }
  }
);

if (result.matchedCount === 0) {
  // Có thể revision đã đổi hoặc document không còn tồn tại.
}
~~~

Nếu worker A cập nhật revision từ 7 lên 8, worker B vẫn mang revision 7 sẽ **không còn khớp filter**.

### Lịch chạy CAS

~~~text
Ban đầu: value=10, revision=7

A đọc: 10, revision=7
B đọc: 10, revision=7

A:
  UPDATE IF revision=7
  SET value=9, revision=8
  → matchedCount=1

B:
  UPDATE IF revision=7
  SET value=9, revision=8
  → matchedCount=0

Kết quả:
  value=9, revision=8
  B phát hiện xung đột, không được báo thành công.
~~~

CAS **không tự hoàn tất yêu cầu B**; nó làm lỗi trở nên **có thể phát hiện** thay vì bị ghi đè âm thầm.

### Retry sau conflict

Nếu B vẫn muốn giảm một đơn vị, B phải:

1. Đọc lại trạng thái mới `value=9, revision=8`.
2. Kiểm tra điều kiện nghiệp vụ vẫn còn hợp lệ.
3. Tính lại `next=8`.
4. Gửi update với điều kiện `revision=8`.
5. Nếu khớp, kết quả `value=8, revision=9`.

**Không được retry bằng cách gửi lại `value=9` với revision mới**, vì như vậy vẫn chỉ lưu một lần giảm. Retry phải **tính lại từ trạng thái mới nhất**.

## 10. Mẫu retry CAS bằng Node.js

Ví dụ hàm giảm một đơn vị với giới hạn số lần thử:

~~~javascript
async function decrementWithRevision(
  collection,
  documentId,
  maxAttempts = 5
) {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const snapshot = await collection.findOne({
      _id: documentId
    });

    if (snapshot === null) {
      throw new Error("NOT_FOUND");
    }

    if (
      !Number.isSafeInteger(snapshot.value) ||
      !Number.isSafeInteger(snapshot.revision)
    ) {
      throw new Error("INVALID_COUNTER_STATE");
    }

    if (snapshot.value < 1) {
      return { applied: false, reason: "INSUFFICIENT_VALUE" };
    }

    const result = await collection.updateOne(
      {
        _id: documentId,
        revision: snapshot.revision
      },
      {
        $set: { value: snapshot.value - 1 },
        $inc: { revision: 1 }
      }
    );

    if (result.matchedCount === 1) {
      return { applied: true, attempts: attempt };
    }

    // Revision bị đổi trong khoảng đọc–ghi.
    // Đọc lại và tính lại, không dùng next từ snapshot cũ.
  }

  throw new Error("TOO_MANY_CONCURRENT_CONFLICTS");
}
~~~

Sử dụng:

~~~javascript
await resetCounter(collection);

await Promise.all([
  decrementWithRevision(collection, "counter-demo"),
  decrementWithRevision(collection, "counter-demo")
]);

const finalDoc = await collection.findOne({
  _id: "counter-demo"
});

console.log(finalDoc.value);    // 8
console.log(finalDoc.revision); // 2
~~~

Đây là ví dụ **giảm counter theo snapshot mới**. Trong sản phẩm thật:

- Nếu tranh chấp nhiều, cần **backoff/jitter** và giới hạn retry hợp lý.
- Nếu có nhiều trường phụ thuộc nhau, cần tính và cập nhật chúng cùng điều kiện phù hợp.
- Nếu một request có thể bị gửi lại sau **timeout không rõ đã commit hay chưa**, cần **idempotency key**, vì retry CAS là cơ chế xử lý *conflict*, không phải cơ chế chống xử lý lại một ý định đã thành công.
- Nếu có writer khác sửa `value` mà **không tăng revision**, cơ chế phát hiện mất hiệu lực.

### Revision là một hợp đồng của mọi writer

Nếu một script admin làm:

~~~javascript
db.counters.updateOne(
  { _id: "counter-demo" },
  { $set: { value: 999 } }
);
~~~

nhưng không tăng `revision`, một client cũ có thể vẫn thấy revision khớp và ghi đè `value=999`. Vì vậy OCC chỉ an toàn khi **mọi đường ghi liên quan đều cập nhật revision theo cùng quy tắc**.

Các batch migration, job nền và thao tác quản trị không được âm thầm bỏ qua hợp đồng đó.

## 11. Compare-and-set theo giá trị, version và điều kiện nghiệp vụ

CAS không bắt buộc dùng revision. Có thể so khớp **giá trị đã đọc**:

~~~javascript
const snapshot = await collection.findOne({
  _id: "counter-demo"
});

const result = await collection.updateOne(
  {
    _id: "counter-demo",
    value: snapshot.value
  },
  {
    $set: { value: snapshot.value - 1 }
  }
);
~~~

Nếu giá trị đã đổi, filter không khớp. Tuy nhiên, **chỉ so theo giá trị có thể gặp vấn đề ABA**.

### Vấn đề ABA

~~~text
T0: value = A
Client X đọc A

T1: writer khác đổi A → B
T2: writer khác đổi B → A

T3: Client X thấy value vẫn bằng A
    → tưởng không có thay đổi giữa T0 và T3
~~~

Nếu ý nghĩa của thao tác phụ thuộc việc **trạng thái đã từng bị thay đổi**, chỉ kiểm tra giá trị A là chưa đủ. Revision tăng một cách đáng tin cậy:

~~~text
T0: value=A, revision=1
T1: value=B, revision=2
T2: value=A, revision=3
~~~

giúp phát hiện sự thay đổi ngay cả khi giá trị trở lại A.

### CAS và điều kiện nghiệp vụ thường cần kết hợp

Ví dụ giữ hàng:

~~~javascript
await inventory.updateOne(
  {
    _id: "SKU-100",
    revision: observedRevision,
    available: { $gte: quantity }
  },
  {
    $inc: {
      available: -quantity,
      reservedTotal: quantity,
      revision: 1
    }
  }
);
~~~

Ở đây:

- `revision` phát hiện thay đổi kể từ snapshot của client.
- `available >= quantity` bảo vệ điều kiện đủ hàng.
- Các `$inc` cập nhật đồng thời các bộ đếm trên **một document**.

Không phải mọi nghiệp vụ đều cần cả ba. Chọn cơ chế **đơn giản nhất vẫn bảo vệ đủ invariant**.

## 12. Java: ví dụ read-modify-write sai và atomic update đúng

Vì ứng dụng Java thường sử dụng MongoDB Java Sync Driver hoặc abstraction tương tự, xem hai mẫu mã.

### 12.1. Mẫu dễ mất cập nhật

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.set;

// collection đã được cấu hình và kết nối.
void decrementNaively(MongoCollection<Document> collection) {
    Document snapshot = collection
            .find(eq("_id", "counter-demo"))
            .first();

    if (snapshot == null) {
        throw new IllegalStateException("Missing counter");
    }

    int oldValue = snapshot.getInteger("value");
    int nextValue = oldValue - 1;

    // Có thể ghi đè kết quả của writer khác.
    collection.updateOne(
            eq("_id", "counter-demo"),
            set("value", nextValue)
    );
}
~~~

Nếu hai thread đọc được cùng `oldValue` rồi ghi, mỗi thread gửi **một hằng số nextValue**. DBMS thực thi các lệnh update, nhưng không biết cả hai hằng số đều được suy ra từ bản cũ.

### 12.2. Dùng phép tăng/giảm nguyên tử

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.inc;

void decrementAtomically(MongoCollection<Document> collection) {
    collection.updateOne(
            eq("_id", "counter-demo"),
            inc("value", -1)
    );
}
~~~

Thao tác này không cần đọc `value` về Java trước khi giảm. **Tính nguyên tử ở DBMS** xử lý hai lần decrement trên cùng document mà không xảy ra lỗi do stale client-side computation.

### 12.3. Java với revision/CAS

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;
import static com.mongodb.client.model.Updates.set;

boolean decrementWithCasOnce(
        MongoCollection<Document> collection
) {
    Document snapshot = collection
            .find(eq("_id", "counter-demo"))
            .first();

    if (snapshot == null) {
        throw new IllegalStateException("Missing counter");
    }

    int observedValue = snapshot.getInteger("value");
    int observedRevision = snapshot.getInteger("revision");

    if (observedValue < 1) {
        return false; // Hết số lượng.
    }

    UpdateResult result = collection.updateOne(
            and(
                    eq("_id", "counter-demo"),
                    eq("revision", observedRevision)
            ),
            combine(
                    set("value", observedValue - 1),
                    inc("revision", 1)
            )
    );

    // false có thể là xung đột; caller cần đọc lại hoặc
    // phân biệt trạng thái theo hợp đồng nghiệp vụ.
    return result.getMatchedCount() == 1;
}
~~~

Đây là **một lần thử CAS**, chưa gồm retry/backoff/idempotency. Đừng viết vòng `while(true)` retry không giới hạn trong hệ có contention lớn; việc cạnh tranh có thể tạo retry storm và kéo p99 lên cao.

## 13. Ghi đè toàn document và cập nhật từng field

Quay lại hai người cùng chỉnh sửa profile:

~~~json
{
  "_id": "U42",
  "displayName": "An",
  "city": "Da Nang",
  "revision": 7
}
~~~

Hai người đều đọc revision 7:

- A đổi `displayName` thành `"An Nguyen"`.
- B đổi `city` thành `"Ha Noi"`.

### Thay document bằng snapshot cũ

~~~javascript
// B gửi nguyên object được đọc trước khi A thay đổi.
await users.replaceOne(
  { _id: "U42" },
  {
    _id: "U42",
    displayName: "An",
    city: "Ha Noi",
    revision: 7
  }
);
~~~

Nếu A đã đổi `displayName`, lần thay toàn document của B có thể khôi phục `displayName="An"`. Đây là mất cập nhật dù B chỉ định sửa thành phố.

### Patch từng field giảm phạm vi ghi đè

~~~javascript
await users.updateOne(
  { _id: "U42" },
  { $set: { city: "Ha Noi" } }
);
~~~

Nếu A chỉ đổi `displayName` bằng `$set` riêng, hai phép cập nhật các field khác nhau thường có thể cùng được giữ lại trong document.

Tuy nhiên, **field-level patch không thay thế OCC trong mọi trường hợp**:

- Hai người cùng đổi `city` vẫn có xung đột về ý định.
- Một thay đổi ở `city` có thể phải phù hợp với `country` và `postalCode`.
- Quy tắc “được phép sửa khi revision vẫn đúng” không được kiểm tra nếu chỉ có `_id`.

### Chọn chính sách xung đột theo nghiệp vụ

| Dữ liệu | Có thể chấp nhận last-write-wins? | Cơ chế nên xét |
| --- | --- | --- |
| Màu theme UI | Có thể | `$set`/LWW nếu sản phẩm chấp nhận |
| Nội dung tài liệu có đồng biên tập | Thường cần bảo vệ thay đổi song song | Revision, merge, OT/CRDT tùy bài toán |
| Lượt thích | Không nên mất lần tăng hợp lệ | Atomic increment/idempotency |
| Số dư | Không được làm mất bút toán | Atomic conditional update/ledger/transaction |
| Tồn kho | Không được bán vượt tồn | Atomic decrement có điều kiện |
| Trạng thái đơn | Không chấp nhận chuyển trạng thái bất kỳ | Conditional state transition/revision |

**Đúng hay sai phụ thuộc ngữ nghĩa.** LWW có thể là chính sách xung đột chủ động cho dữ liệu có thể ghi đè, nhưng không phù hợp nếu mọi hiệu ứng tăng/giảm đều phải được bảo toàn.

## 14. Transactions có tự loại bỏ lost update không?

**Transaction** cung cấp các bảo đảm trong một phạm vi nhất định, nhưng phải xem **isolation level**, cách truy vấn và thao tác cập nhật.

Giả sử hai transaction cùng đọc một document rồi đều định viết lại theo snapshot:

~~~text
T1: read value=10
T2: read value=10
T1: write value=9
T2: write value=9
~~~

Một DBMS có thể phát hiện write conflict và abort một transaction trong cấu hình isolation thích hợp. Một hệ khác hoặc một cách sử dụng transaction khác có thể cho kết quả khác, nhất là nếu chỉ có các lệnh ngoài transaction hoặc mức cô lập yếu hơn.

**Không kết luận “chỉ cần bật transaction” mà bỏ qua câu hỏi transaction đã ngăn lịch sai hay chưa.**

### MongoDB multi-document transactions

Với MongoDB, transaction nhiều document có thể hỗ trợ thao tác inventory và reservation cùng commit. Các ghi cạnh tranh có thể gây write conflict/abort và phải retry theo hướng dẫn driver.

Nhưng:

- Nếu invariant chỉ là giảm một bộ đếm trong một document, `$inc`/conditional update thường đơn giản hơn transaction nhiều document.
- Nếu transaction sửa **những document khác nhau** dựa trên cùng một predicate về tổng số lượng, phải phân tích nguy cơ **write skew**.
- Các lời gọi đọc ngoài transaction không tự trở thành một phần của snapshot transaction.
- Callback transaction bị retry không được gửi email, gọi thanh toán hoặc tạo side effect ngoài DB không idempotent.

### Một transaction nhỏ đúng hơn một transaction lớn mơ hồ

Ví dụ:

~~~text
BEGIN
  Conditional decrement inventory
  Insert reservation keyed by requestId
COMMIT
~~~

có thể phù hợp hơn:

~~~text
BEGIN
  Read inventory
  Call payment HTTP (chờ 8 giây)
  Send email
  Update inventory
COMMIT
~~~

Lời gọi HTTP và email không tự nằm trong transaction DB. Giữ transaction mở qua những bước dài làm tăng contention, timeout và độ phức tạp phục hồi.

## 15. Lost update khác write skew

Hai hiện tượng đều có thể làm sai một invariant nhưng **không đồng nhất**.

### Lost update — cùng giá trị bị ghi đè

~~~text
count = 10
A đọc 10, ghi 11
B đọc 10, ghi 11
→ một lần tăng bị mất
~~~

### Write skew — hai bản ghi khác nhau cùng phá một điều kiện

Ví dụ cần luôn có **ít nhất một người trực**:

~~~text
Ban đầu:
  doctorA.onCall = true
  doctorB.onCall = true

T1 đọc cả hai rồi tắt doctorA.onCall
T2 đọc cả hai rồi tắt doctorB.onCall

Hai transaction ghi vào hai record khác nhau.
Kết quả có thể:
  doctorA.onCall = false
  doctorB.onCall = false
  → invariant bị phá
~~~

Trong một số hệ với **snapshot isolation**, hai transaction sửa hai record khác nhau có thể không đụng write-write conflict trực tiếp; vì vậy vẫn có nguy cơ write skew.

| Tiêu chí | Lost update | Write skew |
| --- | --- | --- |
| Phạm vi thường gặp | Một giá trị/record bị nhiều writer ghi đè | Nhiều record liên quan qua một invariant |
| Lỗi biểu hiện | Một cập nhật bị mất | Tập cập nhật kết hợp tạo trạng thái sai |
| Atomic increment một trường | Thường giải quyết trường hợp tăng đơn giản | Không đủ nếu invariant trải nhiều record |
| CAS theo một revision chung | Có thể phát hiện tranh chấp | Cần điểm xung đột chung hoặc serializable/protocol phù hợp |

Vì vậy, khi hệ sai dữ liệu, phải xác định **lịch cập nhật cụ thể** thay vì gọi mọi lỗi đồng thời là lost update.

## 16. Redis: GET/SET có thể mất cập nhật

Redis có những lệnh đơn được thực thi nguyên tử theo ngữ nghĩa của lệnh trên một instance, nhưng **hai lệnh `GET` rồi `SET` từ ứng dụng không tự tạo một giao dịch read-modify-write**.

Ví dụ:

~~~text
GET counter  → A nhận 10
GET counter  → B nhận 10
SET counter 9  (A)
SET counter 9  (B)
~~~

Kết quả là 9 thay vì 8.

### Dùng lệnh nguyên tử

~~~redis
SET counter 10
DECR counter
DECR counter
GET counter
~~~

Kỳ vọng `GET counter` trả `8` nếu các lệnh thành công và không có writer khác.

Với điều kiện phức tạp như “chỉ trừ nếu đủ tồn”, `DECRBY` đơn lẻ có thể tạo số âm khi nhiều request muốn trừ, nên cần kiểm tra và cập nhật trong **một thao tác phối hợp**.

### WATCH + MULTI/EXEC

Pseudocode:

~~~text
WATCH inventory:SKU-100
current = GET inventory:SKU-100

if current < quantity:
    UNWATCH
    return INSUFFICIENT_STOCK

MULTI
DECRBY inventory:SKU-100 quantity
EXEC

if EXEC indicates watched key changed:
    retry by reading a new value
else:
    success
~~~

`WATCH` triển khai một dạng **optimistic concurrency**: nếu key đã bị thay đổi trước `EXEC` theo ngữ nghĩa Redis, nhóm lệnh không được thực thi như dự kiến và ứng dụng có thể đọc lại rồi thử tiếp.

**Lưu ý:** `MULTI/EXEC` không có khả năng rollback chung mọi lỗi runtime giống transaction SQL. Khi script/lệnh phức tạp, phải xét lỗi kiểu dữ liệu và tác động một phần. Durability của Redis còn phụ thuộc persistence, replication và cấu hình, không thể suy ra từ `WATCH`.

### Lua script kiểm tra rồi trừ

Với một instance Redis hỗ trợ thực thi script nguyên tử và những key hợp lệ trong phạm vi triển khai:

~~~lua
-- KEYS[1] = inventory key
-- ARGV[1] = quantity dạng số nguyên dương đã validate ở caller

local current = tonumber(redis.call("GET", KEYS[1]))
local quantity = tonumber(ARGV[1])

if not current or not quantity or quantity <= 0 then
    return redis.error_reply("INVALID_STATE_OR_QUANTITY")
end

if current < quantity then
    return 0
end

redis.call("DECRBY", KEYS[1], quantity)
return 1
~~~

Đoạn minh họa áp dụng cho một counter số nguyên và không có writer khác bỏ qua quy tắc. Trong hệ thật cần kiểm soát miền số/overflow, nguồn có thẩm quyền, idempotency và Redis Cluster key-slot rules nếu script truy cập nhiều key.

**Không dùng script Redis như một cách mặc định để bảo vệ tiền/hàng nếu Redis chỉ là cache có thể evict dữ liệu** mà nghiệp vụ lại yêu cầu nguồn bền vững.

## 17. DynamoDB: UpdateExpression và ConditionExpression

DynamoDB hỗ trợ cập nhật một item bằng phép tính ngay trong DB và **conditional write**.

### Mẫu dễ mất cập nhật

~~~text
A GetItem inventory → available=10
B GetItem inventory → available=10

A PutItem với available=9
B PutItem với available=9
~~~

Nếu không có điều kiện kiểm soát phiên bản/trạng thái, một lần giảm có thể bị mất. `PutItem` toàn item còn có thể ghi đè các thuộc tính khác nếu gửi bản snapshot cũ.

### Đưa phép giảm vào UpdateItem

Ví dụ dạng yêu cầu API mức thấp:

~~~javascript
const input = {
  TableName: "Inventory",
  Key: {
    pk: { S: "SKU#100" }
  },
  UpdateExpression: "SET available = available - :q",
  ConditionExpression:
    "attribute_exists(pk) AND available >= :q",
  ExpressionAttributeValues: {
    ":q": { N: "3" }
  }
};
~~~

Yêu cầu này biểu diễn:

- Chỉ cập nhật item đã tồn tại.
- Chỉ giảm khi `available >= 3`.
- Tính giá trị mới tại lúc thực thi update thay vì truyền một hằng số stale.

Đây là **payload minh họa** cho `UpdateItem`, không phải đoạn gọi SDK hoàn chỉnh. Phải dùng đúng client, marshalling, quyền, loại khóa, kiểu thuộc tính và cách xử lý lỗi.

### CAS bằng revision

Nếu ứng dụng cần kiểm soát sửa một form:

~~~text
Key = USER#42
revision = 7
~~~

Một conditional update có thể yêu cầu:

~~~text
ConditionExpression: revision = :expectedRevision
UpdateExpression:
  SET displayName = :newName,
      revision = revision + :one
~~~

Nếu revision đã thay đổi, DynamoDB trả lỗi điều kiện thay vì chấp nhận ghi đè im lặng.

### GSI không phải nguồn để kiểm tra điều kiện ghi mạnh

DynamoDB GSI được cập nhật theo cơ chế **eventual consistency**. Đừng dựa vào việc query GSI chưa thấy một item để kết luận chắc chắn item không tồn tại rồi tự thực hiện “check-then-put” nhằm bảo vệ uniqueness hoặc tồn kho.

**Conditional write nên đặt trên item/khóa có thẩm quyền**, hoặc dùng transaction nhiều item trong phạm vi dịch vụ hỗ trợ nếu invariant cần bao trùm nhiều item.

## 18. Cassandra: LWT/IF để phát hiện giá trị cũ

Trong Cassandra, một thao tác CQL bình thường cập nhật cột theo ngữ nghĩa và conflict resolution của Cassandra. Nếu ứng dụng đọc giá trị, tự tính giá trị mới rồi gửi một `UPDATE` không điều kiện, nó có thể gặp trường hợp ghi đè dựa trên dữ liệu đã cũ.

Để triển khai **compare-and-set**, Cassandra có **Lightweight Transaction (LWT)** với điều kiện `IF` trong phạm vi được hỗ trợ.

Giả sử bảng:

~~~sql
CREATE TABLE stock_by_sku (
    sku text PRIMARY KEY,
    available int,
    revision int
);
~~~

Ứng dụng đọc:

~~~text
sku       = SKU-100
available = 10
revision  = 7
~~~

Sau đó muốn giảm 1:

~~~sql
UPDATE stock_by_sku
SET available = 9,
    revision = 8
WHERE sku = 'SKU-100'
IF revision = 7;
~~~

Nếu revision không còn 7, LWT không áp dụng cập nhật và ứng dụng phải đọc lại, kiểm tra tồn rồi tính lại.

### Đừng nhầm LWT với UPDATE không điều kiện

~~~sql
UPDATE stock_by_sku
SET available = 9
WHERE sku = 'SKU-100';
~~~

Lệnh này gửi **một giá trị cụ thể**; nó không biểu diễn “trừ 1 từ số lượng hiện tại”. Nếu hai writer cùng chọn giá trị 9 theo bản đọc cũ, một hiệu ứng giảm có thể bị mất.

### Không dùng counter Cassandra một cách tùy tiện

Cassandra có kiểu counter và ngữ nghĩa update counter riêng, nhưng counter không phải lựa chọn thay thế chung cho **conditional stock decrement**, idempotency hay transaction. Các hạn chế về counter, retry và LWT cần xem theo phiên bản/kiến trúc thực tế.

**LWT có chi phí phối hợp/latency cao hơn ghi thông thường**, nên chỉ nên chọn khi điều kiện nguyên tử thực sự cần. Với cập nhật dữ liệu số lượng lớn và access pattern khác, có thể cần thiết kế partition/aggregate hoặc nguồn tuần tự hóa cập nhật riêng.

## 19. Last-write-wins ở hệ phân tán không giống CAS

Trong một số hệ phân tán, nhiều bản cập nhật có thể tới các replica vào những thời điểm khác nhau. Một chính sách giải quyết xung đột là **last-write-wins (LWW)**: chọn phiên bản được coi là “mới nhất” theo metadata/timestamp của hệ.

Ví dụ hai writer ghi trên cùng key:

~~~text
Writer A: profile.city = "Ha Noi"
Writer B: profile.city = "Da Nang"
~~~

Nếu sản phẩm chọn “giá trị cuối thắng”, một trong hai giá trị có thể là kết quả hợp lệ theo chính sách. Nhưng với:

~~~text
Writer A: increment counter by 1
Writer B: increment counter by 1
~~~

LWW của **hai giá trị đã được tính sẵn** không có nghĩa hai ý định tăng đã được gộp thành +2.

### Những khái niệm khác nhau

| Cơ chế | Được thiết kế để làm gì? | Không tự bảo đảm |
| --- | --- | --- |
| LWW | Chọn một giá trị khi có nhiều bản ghi cạnh tranh | Gộp mọi thay đổi |
| Atomic increment | Áp dụng một phép cộng/trừ tại nơi lưu | Chống request lặp sau timeout |
| CAS/revision | Chỉ ghi nếu trạng thái/phiên bản chưa đổi | Tự retry đúng và idempotency |
| Transaction | Bảo vệ tập thao tác trong một ranh giới | Side effect ngoài DB cùng rollback |
| CRDT counter phù hợp | Gộp các phép tăng/giảm từ nhiều replica theo ngữ nghĩa được thiết kế | Đáp ứng mọi invariant như “không được âm” mà không cần phối hợp |

### Đồng hồ vật lý và thứ tự cập nhật

Một chính sách LWW dựa vào timestamp có thể chịu ảnh hưởng của cách chọn timestamp và đồng hồ. Không được suy luận “giá trị được ghi cuối theo thời gian thực chắc chắn thắng” khi hệ có write timestamp do client cung cấp, skew đồng hồ hoặc cơ chế conflict resolution riêng.

Đối với dữ liệu tiền, quota hoặc đơn hàng, cần một **mô hình thứ tự và ràng buộc rõ ràng** thay vì trông chờ timestamp tự giải quyết tranh chấp nghiệp vụ.

## 20. Lost update và idempotency là hai lỗi khác nhau

Giả sử tồn kho còn 10 và client đặt mua 1 chiếc:

~~~text
Client gửi request R-100
Server thực hiện atomic decrement → available=9
Server commit, nhưng HTTP response bị mất

Client retry request R-100
Server lại atomic decrement → available=8
~~~

Ở đây **không có lost update**. Cả hai decrement được lưu đầy đủ, nhưng **cùng một ý định bị áp dụng hai lần**.

Ngược lại, ở lost update:

~~~text
Client A request R-100 → muốn -1
Client B request R-101 → muốn -1

Cả hai đọc 10 rồi ghi 9.
Kết quả chỉ -1 dù có hai ý định độc lập.
~~~

### Bảng phân biệt

| Hiện tượng | Điều gì xảy ra? | Cơ chế điển hình |
| --- | --- | --- |
| Lost update | Một hiệu ứng hợp lệ biến mất do ghi đè | Atomic operation, CAS, transaction phù hợp |
| Duplicate effect | Một ý định được áp dụng nhiều lần | Idempotency key, unique claim, transaction |
| Write skew | Hai record khác nhau bị sửa, invariant chung sai | Serializable/protocol/aggregate chung |
| Stale read | Client đọc dữ liệu cũ từ replica/index/cache | Chọn consistency/freshness path phù hợp |
| Out-of-order event | Bản cập nhật cũ đến sau và ghi đè mới | Revision/sequence, conditional apply |

**Không được dùng `$inc` một mình rồi tuyên bố “đã xử lý an toàn retry”.** Nếu request bị gửi lại, `$inc` sẽ thực hiện thêm một lần nữa trừ khi có idempotency ở nơi phù hợp.

## 21. Thiết kế idempotency cho phép giảm tồn

Một mẫu nghiệp vụ có thể dùng:

~~~text
requestId = "R-100"
sku       = "SKU-100"
quantity  = 1
~~~

Các ràng buộc:

1. Một `requestId` chỉ đại diện cho **một ý định giữ hàng**.
2. Nếu cùng ID và cùng payload được gửi lại, trả kết quả đã lưu.
3. Nếu cùng ID nhưng payload khác, báo xung đột.
4. Giảm inventory và tạo reservation/claim ID phải cùng commit nếu invariant yêu cầu.

Một transaction logic:

~~~text
BEGIN
  Create reservation(requestId) only if absent
  Decrement inventory if available >= quantity
COMMIT
~~~

Hoặc thay đổi thứ tự phù hợp với DBMS, miễn bảo đảm atomicity và điều kiện đều đúng.

Nếu transaction abort vì request ID đã có, tầng ứng dụng cần **đọc reservation đã commit**, so payload và trả kết quả tương ứng.

**Idempotency không bắt buộc chỉ được triển khai bằng multi-document transaction.** Nếu toàn bộ trạng thái có thể được mô hình hóa trong một aggregate atomic, hoặc DBMS hỗ trợ transactional condition trên nhiều item, có thể chọn đường khác. Quan trọng là **cùng một ý định không tạo thêm tác động trong phạm vi cam kết**.

## 22. Các chiến lược giải quyết xung đột ở cấp ứng dụng

Không phải mọi lần CAS thất bại đều nên **tự động retry và ghi tiếp**.

### 22.1. Counter tăng/giảm

Nếu ý định vẫn hợp lệ, client có thể đọc lại và tính lại hoặc dùng atomic increment ngay từ đầu.

### 22.2. Chỉnh sửa văn bản

Nếu hai người sửa cùng một đoạn mô tả, retry tự động bằng cách lấy bản mới rồi ghi nội dung cũ có thể xóa thay đổi của người kia. Nên:

- Báo có xung đột và yêu cầu xem lại.
- Hiển thị diff hoặc phiên bản mới.
- Merge có kiểm soát.
- Dùng cơ chế đồng biên tập chuyên dụng nếu sản phẩm cần.

### 22.3. Tồn kho, số dư và hạn mức

Nếu CAS thất bại:

- Đọc lại giá trị hiện tại.
- Kiểm tra điều kiện đủ số dư/tồn **một lần nữa**.
- Nếu không đủ, trả từ chối đúng nghiệp vụ.
- Nếu đủ, thử lại trong giới hạn.
- Không tự thay đổi giá/quantity mà không có quyền từ nghiệp vụ.

### 22.4. State machine

Ví dụ chuyển:

~~~text
PENDING → PAID
PENDING → CANCELLED
~~~

Hai request cùng tác động lên `PENDING`. Sau khi một request chuyển trạng thái, request còn lại không thể mặc định ghi đè. Phải xem **chuyển trạng thái từ trạng thái mới có hợp lệ không**.

### Chính sách xung đột cần được công bố

| Loại thay đổi | Hành vi sau conflict có thể phù hợp |
| --- | --- |
| Phép tăng counter có thể áp dụng lặp theo ý định | Retry tính lại, giới hạn retry |
| Form có dữ liệu do người dùng chỉnh | Trả `409 Conflict` hoặc yêu cầu merge |
| Trừ tồn kho | Đọc lại và kiểm tra điều kiện; có thể từ chối |
| Cập nhật trạng thái đơn | Kiểm tra state transition mới |
| Ghi nhận thanh toán | Tra theo idempotency ID; không thu tiền lại |

**Trả HTTP 409 không phải tính năng tự động của DBMS**; đó là một lựa chọn ánh xạ conflict sang hợp đồng API.

## 23. Lost update với nhiều field có ràng buộc

Giả sử inventory document:

~~~json
{
  "_id": "SKU-100",
  "capacity": 10,
  "available": 10,
  "reservedTotal": 0
}
~~~

Bất biến đơn giản:

\[
available \ge 0,\qquad
reservedTotal \ge 0,\qquad
available+reservedTotal=capacity
\]

Hai request giữ mỗi request 3 chiếc. Một cách sai:

~~~javascript
const stock = await inventory.findOne({ _id: "SKU-100" });

if (stock.available >= 3) {
  await inventory.updateOne(
    { _id: "SKU-100" },
    {
      $set: {
        available: stock.available - 3,
        reservedTotal: stock.reservedTotal + 3
      }
    }
  );
}
~~~

Nếu cả hai đọc trạng thái ban đầu, cả hai ghi:

~~~text
available=7
reservedTotal=3
~~~

Từng snapshot cuối có thể vẫn thỏa `available + reservedTotal = 10`, nhưng nếu cả hai request đã được chấp nhận thì **tổng reservation nghiệp vụ là 6** mà bộ đếm chỉ ghi nhận 3. Một invariant ở document **chưa đủ phát hiện mất một yêu cầu** nếu còn một danh sách reservation/đơn bên ngoài.

### Cách biểu diễn phép chuyển nguyên tử

~~~javascript
const q = 3;

const result = await inventory.updateOne(
  {
    _id: "SKU-100",
    available: { $gte: q }
  },
  {
    $inc: {
      available: -q,
      reservedTotal: q
    }
  }
);
~~~

Sau hai lần ghi thành công, trạng thái hợp lý:

~~~text
available=4
reservedTotal=6
~~~

Trong trường hợp cả hai có request ID riêng, nếu còn cần lưu hai reservation trong collection khác, phải bảo vệ tính nhất quán của việc cập nhật bộ đếm **và** ghi nhận từng reservation; một-document atomicity không bao trùm các document khác.

## 24. Chứng minh cập nhật nguyên tử bảo toàn bất biến

Giả sử trạng thái hợp lệ:

\[
available+reservedTotal=capacity
\]

Với một yêu cầu giữ `q > 0` và điều kiện:

\[
available\ge q
\]

Phép cập nhật nguyên tử:

\[
\begin{aligned}
available' &= available-q\\
reservedTotal' &= reservedTotal+q
\end{aligned}
\]

Khi đó:

\[
\begin{aligned}
available'+reservedTotal'
&=(available-q)+(reservedTotal+q)\\
&=available+reservedTotal\\
&=capacity
\end{aligned}
\]

Và:

\[
available'\ge 0
\]

Như vậy, nếu dữ liệu ban đầu đúng và **mọi writer dùng cùng quy tắc cập nhật hợp lệ**, mỗi lần giữ hàng thành công bảo toàn invariant.

### Khi có nhiều writer đồng thời

Điều kiện `available >= q` được kiểm tra **ở thời điểm áp dụng update nguyên tử**. Nếu request thứ nhất đã giảm tồn, request thứ hai phải được đánh giá theo trạng thái còn lại, không dựa vào snapshot cũ từ ứng dụng.

Đó là lý do conditional atomic update phù hợp hơn **check-then-set** cho tồn kho.

### Điều kiện chứng minh không được bỏ qua

- `q` là số nguyên dương trong miền kiểu lưu trữ.
- Không có overflow khi cộng/trừ.
- Không có đường ghi khác tùy ý sửa `available` hoặc `reservedTotal`.
- Mỗi ý định chỉ được chấp nhận một lần nếu nghiệp vụ yêu cầu.
- Nếu dữ liệu có replica/read model, những đường ra quyết định dùng **nguồn/độ nhất quán phù hợp**.

**Một phép toán đúng không cứu được hệ nếu có một writer khác phá ràng buộc.**

## 25. Test nhiều request: điều cần đo ngoài kết quả cuối

Khi kiểm thử concurrent updates, nên ghi nhận:

1. **Số request được gửi**.
2. **Số yêu cầu được chấp nhận về nghiệp vụ**.
3. **Số update thực sự khớp điều kiện**.
4. **Số conflict/retry/failure**.
5. **Trạng thái cuối cùng**.
6. **Bất biến sau mỗi đợt thao tác**.

Ví dụ 100 request độc lập, mỗi request tăng một counter từ 0:

~~~text
Expected:
  sentRequests    = 100
  acceptedEffects = 100
  finalCounter    = 100
~~~

Một bài thử stress chỉ kiểm tra rằng “không có exception” là chưa đủ. Với lost update, **các lệnh ghi có thể không phát sinh exception** nhưng số cuối vẫn sai.

### Kiểm thử an toàn theo hai chế độ

**Bài thử cố ý sai:**

~~~text
Reset counter=0
N worker cùng read–modify–write bằng $set
Expected: Có thể thấy actual < N
~~~

**Bài thử đúng:**

~~~text
Reset counter=0
N worker dùng atomic $inc
Expected: actual = N nếu mọi lệnh thành công đúng một lần
~~~

Với script barrier ở phần trên, dùng hai worker là đủ để chứng minh lỗi; bài test N worker giúp quan sát **tần suất xung đột và khả năng chịu tải**.

Không sử dụng đồng thời cả hai bài trên cùng một key nếu không reset riêng, vì kết quả sẽ khó suy luận.

## 26. Deterministic test và stress test có vai trò khác nhau

| Hình thức | Mục tiêu | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| **Barrier test** | Ép lịch dẫn đến stale read | Dễ tái hiện và giải thích | Không đại diện tải hệ thống thực |
| **Stress test** | Thử nhiều request song song | Đo conflict, throughput, tail latency | Một lần chạy không gặp lỗi chưa chứng minh an toàn |
| **Property-based test** | Sinh nhiều chuỗi thao tác và kiểm invariant | Khám phá nhiều biên input/interleaving | Cần mô hình và cơ chế sinh dữ liệu |
| **Fault injection** | Chèn timeout, crash, restart, mất kết nối | Kiểm retry/unknown outcome | Cần môi trường cô lập và tiêu chí phục hồi |
| **History/linearizability analysis** | Kiểm lịch kết quả so với mô hình tuần tự | Đánh giá bảo đảm quan sát khi có concurrency | Cần ghi history chính xác, phức tạp hơn test đơn giản |

Đối với mục tiêu bài học này, **barrier test** giúp thấy nguyên nhân lost update trực tiếp; **stress test và fault injection** giúp kiểm tra thiết kế đã sửa dưới điều kiện thực tế.

### Lưu lại một history hữu ích

~~~text
timestamp | requestId | operation | observedRevision | result | finalRevision
--------- | --------- | --------- | ---------------- | ------ | -------------
...       | R-A       | dec(1)    | 7                | commit | 8
...       | R-B       | dec(1)    | 7                | conflict | 8
...       | R-B       | retry     | 8                | commit | 9
~~~

Đây là mẫu log minh họa. Trong sản phẩm thật, tránh ghi thông tin nhạy cảm và đừng cho rằng timestamp của log từ nhiều máy tự cung cấp thứ tự tổng tuyệt đối.

## 27. Quan sát trong production: dấu hiệu của lost update

Lost update thường **không tự phát tín hiệu lỗi** nếu ứng dụng ghi đè vô điều kiện. Cần giám sát ở tầng nghiệp vụ.

### Các tín hiệu đáng chú ý

- Tổng counter tăng ít hơn số sự kiện hợp lệ đã được chấp nhận.
- Tổng lượng hàng giữ không khớp reservation ledger.
- Số dư tính từ các bút toán khác số dư trong document.
- Người dùng báo nội dung vừa lưu bị trở lại phiên bản cũ.
- API ghi trả success nhưng truy vấn sau đó thấy một field không phản ánh thay đổi.
- Nhiều writer cùng sửa một hot key; tỷ lệ CAS conflict cao.
- Tác vụ migration hoặc admin cập nhật document bằng `replaceOne` từ snapshot cũ.

### Metric nên ghi

| Metric | Ý nghĩa |
| --- | --- |
| `concurrent_update_conflicts_total` | Số lần CAS/transaction phát hiện conflict |
| `concurrent_update_retries_total` | Số lần thử lại do conflict |
| `update_retry_exhausted_total` | Số request vượt giới hạn retry |
| `business_events_accepted_total` | Số hiệu ứng được chấp nhận |
| `inventory_reconciliation_mismatches_total` | Số bất nhất giữa bộ đếm và reservation/ledger |
| `update_latency_p95/p99` | Tác động của contention và retry |
| `hot_keys_write_rate` | Tần suất cập nhật các key nóng |

Tên metric chỉ là gợi ý; hệ thống cần xác định các event nào **thực sự được commit** để đối soát, tránh đếm cả request đã từ chối hoặc đã retry.

### Không che lỗi bằng cách cập nhật giá trị bù tùy tiện

Nếu phát hiện bộ đếm thấp hơn ledger, có thể cần quy trình đối soát hoặc rebuild dữ liệu dẫn xuất. Nhưng không nên tự “cộng thêm phần thiếu” mà không biết:

- Event nào đã được ghi nhận nhiều lần.
- Có request timeout nhưng commit thành công chưa.
- Ledger có phải nguồn có thẩm quyền không.
- Các thay đổi cùng thời điểm có đang tiếp diễn không.

**Reconciliation cũng phải có transaction/phiên bản để không ghi đè các thay đổi mới trong khi sửa dữ liệu.**

## 28. Hiệu năng của các cách bảo vệ

Các biện pháp có chi phí khác nhau:

| Cơ chế | Lợi ích | Đánh đổi/giới hạn |
| --- | --- | --- |
| Server-side `$inc` | Ít round trip, không dùng snapshot cũ | Chỉ phù hợp phép toán được hỗ trợ; không chống duplicate |
| Conditional atomic update | Bảo vệ điều kiện trong cùng lệnh | Điều kiện phải cùng phạm vi atomicity |
| CAS/revision | Phát hiện sửa dựa trên bản cũ | Cần retry/merge và mọi writer tuân thủ revision |
| Transaction nhiều document | Nhiều thay đổi có thể cùng commit | Conflict, metadata, retry, giới hạn và latency |
| Serialization per key/queue | Giảm xung đột cho một aggregate | Tạo điểm nóng, throughput giới hạn, cần xử lý failover |
| Conflict-free replicated type phù hợp | Có thể gộp một số hiệu ứng đồng thời | Không áp dụng chung cho mọi invariant; cần hiểu semantics |
| Read model/ledger có thẩm quyền | Dễ đối soát hiệu ứng | Thêm chi phí đồng bộ và thiết kế sự kiện |

**Không nên bật transaction nhiều document chỉ để tăng một counter** nếu DBMS đã có atomic increment phù hợp. Ngược lại, nếu invariant đòi hỏi ghi đồng thời hai document, một lệnh increment đơn lẻ trên một document không đủ.

### Hot key và retry storm

Một counter chung cho hàng triệu lượt truy cập có thể trở thành điểm tranh chấp. CAS mỗi lần phải đọc, thử ghi, rồi retry có thể làm throughput giảm mạnh khi nhiều worker.

Các hướng cân nhắc khi business cho phép:

- Atomic increment thay vì read–CAS cho phép cộng đơn giản.
- Sharded counters và tổng hợp khi tính chính xác tức thời không bắt buộc.
- Queue/worker tuần tự hóa theo aggregate.
- Batch/aggregation cho số liệu phân tích.
- Giới hạn concurrency và backoff.

Nhưng sharded counter không phù hợp nếu cần **quota chặt toàn cục** mà mỗi shard độc lập được phép cấp phát: tổng số cấp có thể vượt quota nếu thiếu phối hợp.

## 29. Mẫu lựa chọn cách sửa lost update

~~~text
Ứng dụng có cập nhật dựa trên giá trị hiện tại?
                    │
              ┌─────┴─────┐
              │           │
             Có          Không
              │           │
              ▼           ▼
 Có phép toán nguyên tử    Có cần phát hiện
 server-side phù hợp?      ghi đè có chủ đích?
              │                   │
        ┌─────┴─────┐          ┌───┴────┐
       Có          Không       Có       Không
        │            │          │         │
        ▼            ▼          ▼         ▼
   $inc / atomic   CAS/version  CAS/merge  $set/overwrite
   condition       hoặc txn    tùy domain  nếu LWW hợp lệ
        │            │          │         │
        └────────────┴──────────┴─────────┘
                          │
                          ▼
          Có nhiều document cùng invariant?
                          │
                 ┌────────┴────────┐
                Có                Không
                 │                  │
                 ▼                  ▼
       Transaction/protocol    Single-record
       phối hợp phù hợp        atomicity có thể đủ
                 │                  │
                 └────────┬─────────┘
                          ▼
             Retry/timeout có thể xảy ra?
                          │
                          ▼
              Thiết kế idempotency key
              và xử lý unknown outcome
~~~

Sơ đồ là **hướng suy nghĩ**, không phải thuật toán tự động. Trong triển khai thực tế còn phải xét isolation, write concern/durability, replication consistency và nguồn dữ liệu có thẩm quyền.

## 30. Các lỗi thiết kế thường gặp

| Cách nghĩ hoặc triển khai sai | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| `GET count` rồi `SET count+1` | Hai client có thể đọc cùng giá trị | Atomic increment |
| `findOne` rồi `$set` bằng giá trị đã tính | Snapshot có thể cũ | `$inc` hoặc CAS |
| `replaceOne` với toàn bộ object cũ | Ghi đè cả field không định sửa | Patch field; revision nếu cần |
| “Mỗi updateOne atomic nên read–write an toàn” | Atomicity chỉ cho từng lệnh | Gộp điều kiện/phép toán ở DB |
| “Hai lần modifiedCount=0/1 nghĩa không có lỗi” | Kết quả lệnh không phản ánh đủ hiệu ứng nghiệp vụ | So tổng event với invariant |
| Retry CAS bằng nextValue cũ | Vẫn bỏ hiệu ứng mới | Đọc lại và tính lại |
| Revision chỉ được cập nhật bởi một API | Writer khác có thể bypass OCC | Hợp đồng revision trên mọi đường ghi |
| Chỉ kiểm tra theo giá trị hiện tại | Có thể gặp ABA | Version/sequence phù hợp |
| Tăng counter bằng `$inc` nhưng không chống HTTP retry | Một ý định có thể áp dụng hai lần | Idempotency key/transaction |
| Query GSI eventual để quyết định “chưa có” | Dữ liệu index có thể trễ | Conditional write ở nguồn |
| Cassandra UPDATE giá trị stale không LWT | Có thể ghi đè giá trị mới | LWT/CAS cho invariant phù hợp |
| Redis `MULTI` nhưng không kiểm tra đủ tồn | Vẫn có thể trừ âm | WATCH hoặc script điều kiện |
| Dùng LWW cho tổng tiền/hàng | Chỉ giữ một trạng thái, mất hiệu ứng | Atomic ledger/transaction |
| Transaction dài chờ HTTP bên ngoài | Contention/timeout và side effect không rollback | Ranh giới DB ngắn, workflow/outbox |
| Đo chỉ số request success, không đối soát | Lost update có thể im lặng | Reconciliation và invariant metrics |
| Test concurrency bằng sleep rồi chạy một lần | Dễ bỏ sót lịch lỗi | Barrier/histories và stress test |
| Auto-retry không giới hạn | Retry storm và latency không giới hạn | Bounded retry, backoff, fail rõ |
| Gộp nhiều field cần invariant nhưng chỉ patch một field | Có thể tạo trạng thái không hợp lệ | Atomic multi-field update/transaction |

## 31. Bài tập thực hành

### Bài 1 — Đọc lịch đồng thời

Cho:

~~~text
count = 100
A đọc 100
B đọc 100
A ghi 101
B ghi 101
~~~

Hãy xác định expected/actual và giải thích cập nhật nào bị mất theo ngữ nghĩa hai lần tăng độc lập.

**Gợi ý:** expected=102, actual=101; cả hai đã tính cùng kết quả từ snapshot cũ.

### Bài 2 — Phân biệt `$set` và `$inc`

Trong MongoDB, giải thích sự khác nhau giữa:

~~~javascript
{ $set: { viewCount: oldViewCount + 1 } }
~~~

và:

~~~javascript
{ $inc: { viewCount: 1 } }
~~~

khi hai request chạy đồng thời.

**Gợi ý:** phép đầu mang hằng số được tính ở client; phép sau yêu cầu server tăng giá trị hiện tại.

### Bài 3 — Thay toàn document

Hai người sửa profile có `name`, `city`, `revision`. A sửa name, B sửa city từ cùng revision. Hãy mô tả trường hợp `replaceOne` làm mất thay đổi và đề xuất hai cách sửa.

**Gợi ý:** patch từng field hoặc dùng optimistic concurrency với revision; nếu xung đột có thể merge.

### Bài 4 — Tự xây barrier test

Viết một bài thử có hai worker:

1. Reset `value=10`.
2. Mỗi worker đọc `value`.
3. Chờ cả hai worker đọc xong.
4. Mỗi worker ghi `value-1` bằng `$set`.
5. Đối chiếu kết quả với 8.

Sau đó đổi code sang `$inc` và so lại.

**Gợi ý:** không dùng một khoảng sleep cố định để thay thế barrier.

### Bài 5 — CAS với revision

Ban đầu `value=10, revision=3`. A và B cùng đọc bản này. A update thành `9, revision=4` với điều kiện revision=3. B dùng revision=3.

1. B có được ghi không?
2. B cần làm gì để hoàn tất một lần giảm riêng?
3. Trạng thái cuối khi cả hai lần giảm hợp lệ và hoàn tất là gì?

**Gợi ý:** B bị conflict, đọc lại rồi tính `8, revision=5`.

### Bài 6 — ABA

Một client đọc `state=OPEN`, sau đó các writer khác chuyển `OPEN→CLOSED→OPEN`. Vì sao CAS chỉ so `state=OPEN` không phát hiện lịch thay đổi? Revision giải quyết thế nào?

**Gợi ý:** giá trị quay về bằng giá trị cũ, nhưng revision tăng qua mỗi lần chuyển.

### Bài 7 — Lost update hay duplicate effect?

Phân loại:

1. Hai request khác ID cùng đọc 10 rồi cùng ghi 9.
2. Một request cùng ID bị gửi lại hai lần và mỗi lần thực hiện `$inc:-1`.
3. Hai transaction sửa hai record bác sĩ khác nhau làm không còn ai trực.

**Gợi ý:** lần lượt lost update, duplicate effect, write skew.

### Bài 8 — Giữ hàng có điều kiện

Kho còn 5 sản phẩm. A muốn 4, B muốn 3.

- Vì sao kiểm tra tồn ở ứng dụng rồi `$set` có nguy cơ cả hai báo thành công?
- Viết filter và update MongoDB đúng cho một-document conditional decrement.
- Kết quả có thể có những trường hợp nào khi hai request cạnh tranh?

**Gợi ý:** trong thiết kế đúng, không thể cả hai cùng được chấp nhận; thứ tự thành công không cố định.

### Bài 9 — Java và JavaScript

Hãy viết lại một hàm Java đọc `likes`, tính `likes+1` rồi gọi `updateOne($set)` thành một lệnh dùng `Updates.inc`. Làm tương tự với Node.js MongoDB driver.

**Gợi ý:** giữ filter `_id` ổn định, chuyển phép tăng xuống DBMS.

### Bài 10 — Redis

Vì sao hai lệnh `GET` và `SET` riêng lẻ không an toàn cho counter nhiều writer dù Redis xử lý từng lệnh nguyên tử? Hãy đề xuất lệnh hoặc cơ chế phù hợp khi:

- Chỉ tăng counter.
- Chỉ trừ tồn nếu đủ.

**Gợi ý:** `INCR` cho tăng; conditional script hoặc `WATCH`/`MULTI` cho trừ với điều kiện.

### Bài 11 — DynamoDB và Cassandra

Một ứng dụng NoSQL có `available` và `revision`. Hãy giải thích ngắn:

- DynamoDB `ConditionExpression` giúp gì?
- Cassandra `UPDATE ... IF revision = ?` giúp gì?
- Vì sao query ở secondary index trễ không phù hợp để chứng minh giá trị nguồn “chưa tồn tại”?

**Gợi ý:** đặt điều kiện tại thao tác ghi có thẩm quyền, không tách kiểm tra ở client.

### Bài 12 — Retry và idempotency

Client trừ tồn một lần, DB commit nhưng response mất. Retry cùng request ID và retry với ID mới khác nhau thế nào? Tại sao atomic decrement vẫn chưa đủ?

**Gợi ý:** cần trạng thái request/unique key cùng hiệu ứng nghiệp vụ.

### Bài 13 — Đối soát

Một hệ nhận 1.000 event tăng view count; consumer được ghi nhận đã chấp nhận đủ 1.000 event duy nhất nhưng counter chỉ tăng 973. Hãy nêu:

1. Vì sao có thể nghi lost update?
2. Những nguyên nhân khác cần loại trừ?
3. Cách đo và thiết kế lại để tránh lỗi?

**Gợi ý:** lọc event trùng, event bị từ chối, job chưa xử lý, sai key, cache stale; dùng atomic update và log/idempotency theo yêu cầu.

### Bài 14 — Chọn chiến lược

Chọn một cách tiếp cận phù hợp và giải thích:

1. Hai người chỉnh sửa cùng văn bản dài.
2. Nhiều người bấm like cùng lúc.
3. Trừ số dư nhưng không cho âm.
4. Một thao tác phải trừ inventory và tạo reservation ở hai document.
5. Một dashboard chấp nhận số lượt xem trễ vài phút.

**Gợi ý:** conflict/merge hoặc cơ chế đồng biên tập, atomic increment, conditional decrement, transaction/read-model phù hợp, eventual aggregate tùy domain.

## 32. Mẫu đặc tả cho một thao tác cập nhật có đồng thời

Trước khi triển khai, nhóm phát triển có thể ghi một “hợp đồng concurrency”:

~~~yaml
operation: ReserveProduct
entity: "Inventory aggregate for one SKU"
businessIntent: "Reserve q units exactly once per requestId"
inputs:
  - requestId
  - tenantId
  - sku
  - quantity
validations:
  - "quantity is a positive supported integer"
  - "authorized tenant and sku"
invariants:
  - "available >= 0"
  - "reservedTotal >= 0"
  - "available + reservedTotal = capacity"
conflictRisk:
  - "Two writers reading the same old available"
  - "Duplicate request after timeout"
  - "Admin or batch writer bypassing revision"
writeDesign:
  singleDocument:
    - "Atomic condition available >= quantity"
    - "Atomic inc available=-q, reservedTotal=+q"
  reservationRecord:
    - "Unique requestId"
    - "Same transaction or approved coordination protocol"
readConsistency:
  decisionSource: "Authoritative inventory state"
  secondaryReadModels: "Not used as sole strong-condition check"
retryPolicy:
  conflicts: "Read fresh state and recalculate, bounded backoff"
  unknownOutcome: "Resolve using the same requestId"
  idempotency: "Return committed result for same ID and payload"
observability:
  - "CAS conflicts"
  - "Successful reservations"
  - "Retries and exhausted retries"
  - "Inventory/reservation reconciliation"
verification:
  - "Deterministic barrier test"
  - "Concurrent insufficient-stock scenario"
  - "Duplicate request after simulated lost response"
  - "Mixed writer and admin job"
  - "Crash/failover at the commit boundary"
~~~

Đây là **mẫu tài liệu thiết kế**, không phải cấu hình chạy trực tiếp của MongoDB, Redis, DynamoDB hoặc Cassandra. Mỗi hệ cần ánh xạ các điều kiện/transaction vào API và bảo đảm thực tế.

## 33. Ghi nhớ

**Lost update** xảy ra khi nhiều writer đọc một trạng thái cũ, tính giá trị mới độc lập rồi ghi đè mà không phát hiện thay đổi giữa lúc đọc và lúc ghi. Nó dễ xuất hiện nhất với mẫu **read–modify–write không điều kiện**, nhưng cũng có thể phát sinh khi thay toàn bộ document từ một form cũ hoặc giải quyết xung đột bằng last-write-wins không phù hợp với nghiệp vụ.

Những nguyên tắc quan trọng:

1. **Một lệnh ghi nguyên tử không làm toàn bộ chuỗi đọc–tính–ghi trở thành nguyên tử.** Nếu client tính một hằng số từ snapshot cũ rồi `$set`, lệnh ghi có thể thành công mà vẫn mất hiệu ứng của writer khác.
2. **Dùng phép toán nguyên tử ở nơi lưu dữ liệu** cho cập nhật có dạng tăng/giảm đơn giản, ví dụ MongoDB `$inc` hoặc Redis `INCR/DECR`.
3. **Đưa điều kiện nghiệp vụ vào lệnh ghi** khi cần tránh số dư/tồn âm. Đọc trước rồi kiểm tra bằng `if` ở client không đủ dưới concurrency.
4. **CAS/revision biến ghi đè âm thầm thành conflict có thể xử lý.** Sau conflict phải đọc lại, kiểm tra và tính lại, không gửi giá trị cũ một lần nữa.
5. **Patch theo field hạn chế ghi đè nhầm**, nhưng không thay thế versioning nếu các field phụ thuộc nhau hoặc nhiều người sửa cùng trường.
6. **Transaction được chọn theo ranh giới invariant.** Một-document atomic update có thể đủ cho một counter; nhiều document hoặc write skew đòi hỏi phân tích isolation và giao thức phù hợp.
7. **Idempotency khác lost update.** Atomic increment bảo toàn nhiều lần tăng độc lập, nhưng request bị retry vẫn có thể tăng hai lần nếu không có request ID và cơ chế chống trùng.
8. **Tái hiện bằng lịch có barrier**, sau đó đo stress, conflict, retry, tail latency và đối soát trạng thái cuối với những hiệu ứng đã được chấp nhận.

**Nguyên tắc thực hành:** hãy biểu diễn đúng **ý định cập nhật** — “cộng một đơn vị”, “giảm nếu còn đủ”, “chỉ ghi nếu revision chưa đổi” — ngay tại nơi có thể bảo đảm tính nguyên tử. Đừng biến ý định đó thành **“ghi đè bằng một con số tôi vừa tính từ dữ liệu cũ”** nếu hệ thống có nhiều writer đồng thời.
