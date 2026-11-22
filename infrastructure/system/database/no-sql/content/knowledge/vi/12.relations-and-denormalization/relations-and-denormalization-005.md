# Ghi đến nhiều nơi (fan-out) so với tập hợp dữ liệu khi đọc

Trong cơ sở dữ liệu NoSQL, khi một đối tượng được nhiều người hoặc nhiều chức năng sử dụng, ta thường phải chọn **làm thêm công việc lúc ghi** hay **làm thêm công việc lúc đọc**. Hai chiến lược thường được gọi là **fan-out-on-write** (phát tán/cập nhật nhiều nơi khi ghi) và **fan-in-on-read** (tập hợp dữ liệu từ nhiều nguồn khi đọc).

Đây là một quyết định quan trọng của chương **Quan hệ và lặp dữ liệu**: ta có thể **nhân bản một phần dữ liệu để đọc nhanh**, hoặc **giữ ít bản sao hơn rồi truy vấn/ghép dữ liệu theo yêu cầu**. Cả hai cách đều có chi phí. Không có quy tắc “NoSQL thì luôn denormalize” hoặc “cứ ít bản sao là tốt”.

Bài học sử dụng một ứng dụng bảng tin (*social feed*) làm ví dụ xuyên suốt. Mỗi tác giả đăng bài; những người theo dõi muốn xem bài mới. Cùng dữ liệu và cùng yêu cầu giao diện có thể được phục vụ theo hai cách:

- **Fan-out-on-write:** khi có bài mới, tạo một mục trong bảng tin của từng người theo dõi.
- **Fan-in-on-read:** khi người dùng mở bảng tin, tìm những tác giả họ theo dõi rồi tập hợp bài viết của các tác giả đó.

Ta sẽ mô hình hóa dữ liệu, viết truy vấn MongoDB, đối chiếu chi phí đọc–ghi, xử lý nhất quán và tìm điểm cân bằng bằng chiến lược lai.

## 1. Định nghĩa trong ngữ cảnh NoSQL

### 1.1. Fan-out-on-write: ghi một sự kiện, cập nhật nhiều nơi phục vụ đọc

Một bài đăng `post-101` do tác giả An tạo ra. An có 10.000 người theo dõi. Nếu mỗi người theo dõi có một danh sách bảng tin riêng, hệ thống có thể phát tán bài vào 10.000 danh sách:

~~~text
                     GHI MỘT BÀI ĐĂNG
                     An tạo post-101
                             |
                             v
                    Collection posts
                             |
                             v
                    Fan-out dispatcher
                      /      |      \
                     v       v       v
              Inbox Mai   Inbox Bình   ... Inbox 10.000 người
               post-101    post-101        post-101
                     \       |       /
                      \      |      /
                       Đọc từng inbox:
                       có sẵn bài để xem
~~~

Fan-out có thể được thực hiện **đồng bộ** trong request đăng bài hoặc **bất đồng bộ** qua queue/stream và worker. Với số người theo dõi lớn, cách bất đồng bộ thường dễ giới hạn tải và khôi phục khi lỗi hơn; nhưng nó mang theo **độ trễ xuất hiện của bài trên bảng tin**.

Một mục inbox **không bắt buộc là bản sao đầy đủ của bài đăng**. Thông thường chỉ cần lưu `postId`, `authorId`, `publishedAt` và một vài metadata cần cho việc sắp xếp/hiển thị. Nội dung gốc có thể tiếp tục nằm ở collection `posts`.

### 1.2. Fan-in-on-read: giữ dữ liệu gốc, ghép khi có yêu cầu đọc

Thay vì tạo mục bảng tin cho từng người theo dõi, hệ thống lưu bài đăng theo tác giả. Khi Mai mở bảng tin, ứng dụng lấy danh sách tác giả Mai theo dõi, tìm bài mới của họ, gộp và sắp xếp:

~~~text
                   Mai mở bảng tin
                          |
                          v
                 Xem Mai theo dõi ai
                          |
            +-------------+-------------+
            |             |             |
            v             v             v
          Bài An       Bài Bình       Bài Chi
            |             |             |
            +-------------+-------------+
                          |
                          v
                    Gộp + lọc + sort
                          |
                          v
                    20 bài gần nhất
~~~

Khi An đăng bài, phần ghi chính có thể chỉ là thêm một document vào `posts`; chưa cần cập nhật bảng tin của từng người. Đổi lại, mỗi lần đọc bảng tin có thể phải xử lý **nhiều tác giả**, **nhiều tập kết quả** và bộ lọc quyền truy cập.

### 1.3. Fan-out và fan-in nói về vị trí của công việc

| Khía cạnh | Fan-out-on-write | Fan-in-on-read |
| --- | --- | --- |
| Công việc chính đặt ở đâu? | Khi bài được tạo/cập nhật: phát tán đến nơi đọc | Khi bảng tin được mở: tìm và tập hợp |
| Dữ liệu dẫn xuất | Mục inbox/feed theo người nhận | Có thể không có inbox riêng |
| Đường đọc phổ biến | Truy vấn `feed_inbox` theo `userId` và thời gian | Truy vấn `follows` rồi `posts` theo các tác giả |
| Chi phí ghi | Tăng theo số người nhận hoặc số view cần duy trì | Thường gần với số thực thể nguồn được ghi |
| Chi phí đọc | Có thể nhỏ nếu inbox đã xếp sẵn | Có thể tăng theo số tác giả theo dõi và lượng bài ứng viên |
| Tính cập nhật | Phụ thuộc tốc độ fan-out và đồng bộ | Có thể thấy bài nguồn mới ngay, tùy cơ chế đọc/index |
| Độ phức tạp chính | Queue, retry, xóa mục cũ, đồng bộ trạng thái | Truy vấn nhiều nguồn, merge, pagination, giới hạn fan-in |
| Nguy cơ nổi bật | Tác giả có quá nhiều người theo dõi gây bùng nổ ghi | Người dùng theo dõi quá nhiều nguồn gây bùng nổ đọc |

Bảng mô tả xu hướng, **không phải cam kết hiệu năng**. Một inbox lưu sẵn nhưng cần xác minh quyền truy cập từng bài vẫn có nhiều lần đọc; một fan-in có index tốt và cache đôi khi rất nhanh. Cần đo đúng workload.

## 2. Phân biệt fan-out với replication, sharding và denormalization

Các khái niệm này liên quan nhưng không đồng nghĩa:

- **Fan-out-on-write:** một sự kiện ghi nghiệp vụ tạo ra **nhiều mục dữ liệu phục vụ các người nhận hoặc đường truy vấn khác nhau**. Ví dụ một bài đăng tạo 10.000 mục inbox.
- **Denormalization:** lưu lặp thông tin hoặc cấu trúc dẫn xuất để giảm công việc khi đọc. Fan-out-on-write thường là **một cách hiện thực denormalization**, nhưng không phải mọi denormalization đều là fan-out bảng tin.
- **Replication:** giữ nhiều bản sao vật lý/logical của cùng dữ liệu để tăng khả năng chịu lỗi hoặc phục vụ đọc. Replica do database quản lý **khác** với mục inbox cho từng người dùng.
- **Sharding/partitioning:** chia dữ liệu thành các phần để phân bố trên nhiều node. Sharding có thể giúp phân tán inbox, nhưng không tự làm biến mất tổng số lượt ghi fan-out.
- **Pub/sub:** một thông điệp được phát tới nhiều subscriber. Đây có thể là **cơ chế truyền sự kiện** để triển khai fan-out; subscriber nhận message không tự đồng nghĩa với dữ liệu inbox đã được ghi bền và có thể truy vấn.

Nếu một bài được replicate ở ba node và còn được sao chép logic vào 10.000 inbox, có **hai lớp nhân bản khác nhau**. Khi tính dung lượng và throughput phải phân biệt chúng.

## 3. Cố định nghiệp vụ trước khi chọn mô hình

Một ứng dụng bảng tin có ba loại thực thể:

1. **User:** người dùng, được nhận diện bằng `userId` ổn định.
2. **Follow:** quan hệ `followerId → followeeId`, nghĩa là người thứ nhất theo dõi tác giả thứ hai.
3. **Post:** bài đăng do một `authorId` tạo ra, có thời gian xuất bản và trạng thái.

Một bài đăng:

~~~json
{
  "_id": "post-101",
  "authorId": "u-an",
  "body": "Bai viet thu nhat",
  "publishedAt": "2026-11-14T08:00:00Z",
  "visibility": "PUBLIC",
  "status": "PUBLISHED"
}
~~~

Một quan hệ theo dõi:

~~~json
{
  "_id": "u-mai|u-an",
  "followerId": "u-mai",
  "followeeId": "u-an",
  "createdAt": "2026-11-14T07:00:00Z"
}
~~~

Yêu cầu cơ bản của bảng tin:

- Trả tối đa **20 bài mới nhất** của các tác giả mà người đọc đang theo dõi.
- Sắp xếp theo `publishedAt DESC` và dùng `postId DESC` làm **khóa phụ**, để thứ tự ổn định khi hai bài có cùng timestamp.
- Chỉ lấy bài còn **PUBLISHED** và người đọc có quyền xem.
- Không lặp cùng một bài trong một trang.
- Phân trang được khi số bài rất lớn.
- Khi bỏ theo dõi hoặc khi một bài bị xóa/ẩn, dữ liệu không được hiển thị trái với chính sách truy cập.

Để minh họa truy vấn, các bài trong bộ dữ liệu nhỏ sẽ được gắn `visibility: "PUBLIC"`. Với bài riêng tư, nhóm kín hoặc đa tenant, cần bổ sung chính sách phân quyền; không được tin chỉ vì một bài đã nằm trong inbox.

### 3.1. Cùng yêu cầu nhưng hai đường truy cập

**Fan-out-on-write:**

~~~text
WRITE:
  create post
  -> tìm followers của author
  -> tạo feed item cho từng follower

READ:
  query feed_inbox WHERE userId = viewer
  ORDER BY publishedAt DESC, postId DESC
  LIMIT 20
~~~

**Fan-in-on-read:**

~~~text
WRITE:
  create post

READ:
  tìm followeeIds của viewer
  -> tìm posts WHERE authorId IN followeeIds
  -> lọc visibility/status, ORDER BY time + id, LIMIT 20
~~~

Đây là cùng một hợp đồng đầu ra, nhưng **đường ghi và đường đọc** khác nhau.

## 4. Mô hình dữ liệu cho fan-out-on-write

Ta lưu ba collection: `posts`, `follows`, `feed_inbox`.

### 4.1. Nguồn chân lý là bài đăng

~~~json
{
  "_id": "post-101",
  "authorId": "u-an",
  "body": "Bai viet thu nhat",
  "publishedAt": "2026-11-14T08:00:00Z",
  "visibility": "PUBLIC",
  "status": "PUBLISHED",
  "version": 1
}
~~~

`posts` là nguồn chân lý của nội dung và quyền truy cập. Một bài có thể nằm trong nhiều inbox, nhưng **nội dung gốc** không nhất thiết bị nhân bản nguyên vẹn.

### 4.2. Inbox item là dữ liệu dẫn xuất để phục vụ đọc

~~~json
{
  "_id": "u-mai|post-101",
  "userId": "u-mai",
  "postId": "post-101",
  "authorId": "u-an",
  "publishedAt": "2026-11-14T08:00:00Z"
}
~~~

Một số quyết định thiết kế có chủ đích:

- `_id = userId|postId` làm khóa **idempotency** trong ví dụ. Một người nhận và một bài chỉ có một mục inbox.
- `userId` dùng cho truy vấn theo người đọc.
- `publishedAt` được sao chép để sắp xếp nhanh. Nếu thời gian xuất bản được phép sửa, phải có quy tắc cập nhật giá trị đã nhân bản.
- `postId` trỏ tới document gốc. Khi trả nội dung, có thể lấy các bài tương ứng từ `posts`.
- Không đưa toàn bộ `body` vào mọi inbox, tránh nhân bản nội dung không cần thiết. Nhưng việc chỉ lưu tham chiếu có thể đòi thêm bước **hydrate** khi đọc.

Trong hệ có nhiều tenant, khóa duy nhất phải bao gồm **tenant scope** khi userId/postId không duy nhất toàn cục; dùng một quy tắc mã hóa khóa không gây va chạm giữa các thành phần. Chuỗi ghép dấu `|` chỉ phục vụ ví dụ vì các ID mẫu không chứa dấu này.

### 4.3. Đọc từ inbox

~~~javascript
db.feed_inbox.find(
  { userId: "u-mai" },
  { _id: 0, postId: 1, authorId: 1, publishedAt: 1 }
)
  .sort({ publishedAt: -1, postId: -1 })
  .limit(20);
~~~

Nếu có chỉ mục theo `userId + publishedAt + postId`, hệ có thể lấy mục gần nhất mà không cần quét tất cả bài của mọi tác giả.

Tuy nhiên, truy vấn này mới trả **ID và metadata** của bài. Nếu giao diện cần nội dung, trạng thái hoặc tác giả hiện tại, ứng dụng cần lấy dữ liệu gốc và xác minh quyền. Đó là khác biệt giữa **fan-out các con trỏ** và **fan-out bản sao nội dung đầy đủ**.

## 5. Mô hình dữ liệu cho fan-in-on-read

Với fan-in, có thể dùng hai collection `posts` và `follows` mà **không cần `feed_inbox`**.

Trước tiên tìm danh sách tác giả Mai đang theo dõi:

~~~javascript
const followeeIds = db.follows.find(
  { followerId: "u-mai" },
  { _id: 0, followeeId: 1 }
).toArray().map(edge => edge.followeeId);
~~~

Sau đó tìm bài từ các tác giả đó:

~~~javascript
const feed = followeeIds.length === 0
  ? []
  : db.posts.find({
      authorId: { $in: followeeIds },
      status: "PUBLISHED",
      visibility: "PUBLIC"
    })
    .sort({ publishedAt: -1, _id: -1 })
    .limit(20)
    .toArray();
~~~

Truy vấn này diễn đạt đúng **bảng tin bài công khai của tác giả được theo dõi**. Nhưng `$in` chứa hàng nghìn tác giả có thể tạo kế hoạch truy vấn phức tạp; một index riêng trên `authorId` chưa chắc khiến việc **sort toàn tập** trở nên rẻ. Cần dùng `explain` để quan sát.

Một cách hiện thực khác là lấy **một số bài mới nhất của từng tác giả** rồi hợp nhất bằng *k-way merge* ở phía ứng dụng hoặc query service. Cách này có thể khai thác index theo tác giả và thời gian, nhưng yêu cầu kiểm soát số tác giả, số ứng viên, pagination và round trip. **Không mặc định mọi cách fan-in chỉ là một truy vấn MongoDB đơn giản.**

## 6. Thực hành MongoDB: cùng một bảng tin, hai chiến lược

Phần thực hành sử dụng `mongosh` và database thử nghiệm `nosql_fanout_lab`. Tất cả ID và nội dung đều là dữ liệu giả định, không phải người dùng thật.

> Lưu ý: đoạn khởi tạo dưới đây **xóa các collection `posts`, `follows`, `feed_inbox` trong database thực hành**, để mỗi lần chạy bắt đầu từ cùng một trạng thái. Không chạy trên collection chứa dữ liệu quan trọng.

### 6.1. Tạo dữ liệu gốc

~~~javascript
const lab = db.getSiblingDB("nosql_fanout_lab");

["posts", "follows", "feed_inbox"].forEach(name =>
  lab.getCollection(name).drop()
);

lab.follows.insertMany([
  {
    _id: "u-mai|u-an",
    followerId: "u-mai",
    followeeId: "u-an"
  },
  {
    _id: "u-mai|u-binh",
    followerId: "u-mai",
    followeeId: "u-binh"
  },
  {
    _id: "u-lan|u-an",
    followerId: "u-lan",
    followeeId: "u-an"
  }
]);

lab.posts.insertMany([
  {
    _id: "post-101",
    authorId: "u-an",
    body: "Bai 1 cua An",
    publishedAt: new Date("2026-11-14T08:00:00Z"),
    visibility: "PUBLIC",
    status: "PUBLISHED"
  },
  {
    _id: "post-102",
    authorId: "u-binh",
    body: "Bai 1 cua Binh",
    publishedAt: new Date("2026-11-14T09:00:00Z"),
    visibility: "PUBLIC",
    status: "PUBLISHED"
  },
  {
    _id: "post-103",
    authorId: "u-an",
    body: "Bai 2 cua An",
    publishedAt: new Date("2026-11-14T10:00:00Z"),
    visibility: "PUBLIC",
    status: "PUBLISHED"
  }
]);
~~~

Quan hệ:

~~~text
Mai ──FOLLOWS──> An
Mai ──FOLLOWS──> Bình
Lan ──FOLLOWS──> An

Bài:
  08:00 An   -> post-101
  09:00 Bình -> post-102
  10:00 An   -> post-103

Bảng tin mong đợi:
  Mai: post-103, post-102, post-101
  Lan: post-103, post-101
~~~

Ta sẽ dùng các kết quả mong đợi này để xác nhận **tính đúng nghiệp vụ**, trước khi bàn về hiệu năng.

### 6.2. Tạo chỉ mục theo đường truy vấn

~~~javascript
// Tìm tác giả mà một người đang theo dõi.
lab.follows.createIndex(
  { followerId: 1, followeeId: 1 },
  { unique: true }
);

// Tìm người nhận của một tác giả: dùng khi fan-out.
lab.follows.createIndex({ followeeId: 1, followerId: 1 });

// Tìm bài của một tác giả theo thời gian khi fan-in.
lab.posts.createIndex({
  authorId: 1,
  publishedAt: -1,
  _id: -1
});

// Đọc inbox của một người theo thứ tự mới nhất.
lab.feed_inbox.createIndex({
  userId: 1,
  publishedAt: -1,
  postId: -1
});
~~~

Các collection MongoDB thông thường đã có index duy nhất theo `_id`. Index `followerId + followeeId` giúp tránh một quan hệ theo dõi bị tạo lặp theo cặp; index đảo chiều `followeeId + followerId` phục vụ việc tìm mọi người nhận khi tác giả đăng bài.

Một index trên `posts(authorId, publishedAt, _id)` giúp truy vấn **theo từng tác giả**. Với bộ lọc `authorId: {$in: [...] }` gồm rất nhiều tác giả và sắp xếp toàn cục, MongoDB có thể dùng chiến lược khác tùy thống kê và phiên bản. Không nên khẳng định index này giải quyết mọi vấn đề fan-in.

### 6.3. Tạo inbox bằng fan-out

Định nghĩa một hàm thực nghiệm để tạo mục inbox cho mọi follower của một bài công khai:

~~~javascript
function fanOutPost(post) {
  if (
    post.status !== "PUBLISHED" ||
    post.visibility !== "PUBLIC"
  ) {
    return;
  }

  const followers = lab.follows.find({
    followeeId: post.authorId
  }).toArray();

  for (const edge of followers) {
    const itemId = edge.followerId + "|" + post._id;

    lab.feed_inbox.updateOne(
      { _id: itemId },
      {
        $setOnInsert: {
          userId: edge.followerId,
          postId: post._id,
          authorId: post.authorId,
          publishedAt: post.publishedAt
        }
      },
      { upsert: true }
    );
  }
}

// Backfill toàn bộ bài hiện có để so sánh với fan-in.
lab.posts.find({
  status: "PUBLISHED",
  visibility: "PUBLIC"
}).forEach(post => fanOutPost(post));

print("Inbox items:", lab.feed_inbox.countDocuments({}));
~~~

Với dữ liệu mẫu, kết quả mong đợi là **5 mục inbox**:

- An có 2 người theo dõi và 2 bài → 4 mục.
- Bình có 1 người theo dõi và 1 bài → 1 mục.
- Tổng cộng 5 mục.

Đây là minh họa **fan-out đồng bộ trong mongosh**, không phải worker production. Với nhiều follower, không nên tải hàng triệu quan hệ bằng `toArray()` hoặc ghi tuần tự trong request. Cần batching, giới hạn tải, queue/stream và cơ chế resume sau lỗi.

`$setOnInsert` kết hợp khóa `_id` cố định giúp thao tác fan-out **idempotent ở mức tạo mục**: chạy lại cùng bài và người nhận không tạo thêm một mục mới. Điều đó chưa tự giải quyết nội dung bị sửa, quyền truy cập thay đổi hoặc xóa bài.

### 6.4. Đọc bảng tin theo fan-out-on-write

~~~javascript
function feedByFanOut(viewerId, limit = 20) {
  return lab.feed_inbox.find({ userId: viewerId })
    .sort({ publishedAt: -1, postId: -1 })
    .limit(limit)
    .toArray()
    .map(item => item.postId);
}

printjson(feedByFanOut("u-mai"));
// ["post-103", "post-102", "post-101"]

printjson(feedByFanOut("u-lan"));
// ["post-103", "post-101"]
~~~

Hàm này trả **danh sách ID để thực hành so sánh**, chưa có bước tải nội dung gốc hoặc xác minh quyền truy cập. Trong API thực tế, phải bổ sung các bước đó trước khi trả nội dung cho người dùng.

### 6.5. Đọc cùng bảng tin theo fan-in-on-read

~~~javascript
function feedByFanIn(viewerId, limit = 20) {
  const authorIds = lab.follows.find(
    { followerId: viewerId },
    { _id: 0, followeeId: 1 }
  ).toArray().map(edge => edge.followeeId);

  if (authorIds.length === 0) {
    return [];
  }

  return lab.posts.find({
    authorId: { $in: authorIds },
    status: "PUBLISHED",
    visibility: "PUBLIC"
  })
    .sort({ publishedAt: -1, _id: -1 })
    .limit(limit)
    .toArray()
    .map(post => post._id);
}

printjson(feedByFanIn("u-mai"));
// ["post-103", "post-102", "post-101"]

printjson(feedByFanIn("u-lan"));
// ["post-103", "post-101"]
~~~

Với bộ dữ liệu hiện tại, hai chiến lược nên trả cùng một tập và thứ tự ID:

~~~javascript
for (const viewerId of ["u-mai", "u-lan"]) {
  const byWrite = feedByFanOut(viewerId);
  const byRead = feedByFanIn(viewerId);

  print(
    viewerId,
    JSON.stringify(byWrite) === JSON.stringify(byRead)
  );
}
~~~

Kết quả mong đợi là `true` cho cả hai người dùng. Đây chỉ là kiểm tra **đầu ra của bộ dữ liệu mẫu sau khi backfill hoàn tất**. Nó chưa kiểm tra độ trễ của worker, cập nhật quan hệ theo dõi, bài riêng tư, bài bị xóa hoặc dữ liệu đang thay đổi.

## 7. Một bài đăng mới: khác biệt xuất hiện ngay ở đường ghi

Bây giờ An đăng thêm một bài:

~~~javascript
const newPost = {
  _id: "post-104",
  authorId: "u-an",
  body: "Bai 3 cua An",
  publishedAt: new Date("2026-11-14T11:00:00Z"),
  visibility: "PUBLIC",
  status: "PUBLISHED"
};

lab.posts.insertOne(newPost);
~~~

Tại thời điểm **mới chèn vào `posts`**:

- `feedByFanIn("u-mai")` có thể thấy `post-104` ngay khi lần đọc đó nhìn thấy bản ghi mới theo chính sách consistency.
- `feedByFanOut("u-mai")` **chưa có `post-104`** vì inbox chưa được cập nhật.

Sau đó chạy:

~~~javascript
fanOutPost(newPost);

printjson(feedByFanOut("u-mai"));
printjson(feedByFanIn("u-mai"));
~~~

Lúc này hai bảng tin lại tương đương trong ví dụ: bài mới nhất nằm trước các bài cũ. Chênh lệch thời gian từ lúc chèn bài đến lúc cập nhật inbox chính là **fan-out lag** nếu quá trình phát tán được thực hiện bất đồng bộ.

### 7.1. Tại sao fan-out thường cần hàng đợi?

Nếu người đăng có **2 triệu follower**, không thể kỳ vọng request HTTP tạo bài sẽ mở 2 triệu thao tác ghi đơn lẻ và vẫn có độ trễ nhỏ. Một kiến trúc thường gặp:

~~~text
POST /posts
     |
     v
Ghi bài canonical vào posts
     |
     v
Ghi sự kiện bền vững / outbox
     |
     v
Queue hoặc event stream
     |
     +── Worker 1: batch người nhận 1
     +── Worker 2: batch người nhận 2
     +── Worker 3: batch người nhận 3
     |
     v
feed_inbox (upsert idempotent)
     |
     v
Đánh dấu tiến độ / thống kê lag
~~~

Một hệ có thể dùng **transaction + outbox**, CDC hoặc cơ chế phát sự kiện đáng tin cậy tương đương, để tránh trường hợp bài đã ghi thành công nhưng sự kiện fan-out bị mất. Gửi message sau khi ghi database bằng hai thao tác độc lập mà không có cơ chế khôi phục có nguy cơ **dual-write failure**.

### 7.2. Fan-out có thể hoàn thành một phần

Ví dụ bài mới cần phát đến 10.000 người:

~~~text
Đã tạo 7.000 inbox items
Worker bị restart
Còn 3.000 người chưa nhận
~~~

Cách xử lý tốt là **chạy tiếp hoặc phát lại phần công việc** bằng event/cursor/batch bền vững. Vì mỗi mục inbox có khóa idempotent theo người nhận và bài, việc retry không tạo mục trùng. Nhưng tiến độ “7.000 người đã xong” phải được tính theo thao tác ghi thành công, không được suy ra chỉ từ số request worker đã gửi.

Cũng phải phân biệt **at-least-once delivery** của message với **exactly-once effect** ở dữ liệu đích. Hàng đợi có thể giao lại một message nhiều lần; thiết kế idempotent giúp kết quả cuối đúng dù worker chạy lại.

## 8. Ước lượng chi phí đọc và ghi

Hãy đặt:

- `P`: số bài mới được xuất bản trong một khoảng thời gian.
- `F(p)`: số người nhận cần fan-out của bài `p`.
- `R`: số lần mở bảng tin trong khoảng đó.
- `K`: số mục muốn trả trong một trang (ví dụ 20).
- `S(u)`: số tác giả người dùng `u` theo dõi.
- `C_merge(u, K)`: chi phí tập hợp và lọc đủ `K` bài từ các nguồn mà `u` theo dõi.

**Fan-out-on-write** có số mục inbox mới xấp xỉ:

\[
W_{\mathrm{fanout}} = \sum_{p=1}^{P} F(p)
\]

Chưa tính một lần ghi bài canonical, index, bản sao vật lý, retry và những lần cập nhật/xóa về sau. Chi phí đọc inbox thường gắn với việc lấy `K` mục gần nhất theo một khóa đã được đánh chỉ mục, cộng chi phí hydrate và kiểm tra quyền nếu có.

**Fan-in-on-read** không tạo `F(p)` mục inbox cho mỗi bài, nhưng tổng chi phí tập hợp ở phía đọc có thể gần với:

\[
C_{\mathrm{fanin}} = \sum_{r=1}^{R} C_{\mathrm{merge}}(u_r, K)
\]

`C_merge` phụ thuộc cách query engine thực thi, số nguồn thực sự có bài, index, cache, bộ lọc và số ứng viên cần xét. **Không có một công thức `O(S × K)` đúng cho mọi fan-in implementation.**

### 8.1. Ví dụ số học minh họa

Giả sử trong một ngày:

- 1.000 bài được đăng.
- Mỗi bài trung bình phải gửi đến 500 người.
- Có 20.000 lần mở bảng tin.

Khi đó số mục inbox cần tạo khoảng:

\[
1\,000 \times 500 = 500\,000\ \text{mục}
\]

Đây là **số lượng ghi logic phát sinh**, không phải số byte hay thời gian thực tế. Một item nhỏ có thể rẻ hơn một document lớn; cập nhật index và replication vẫn làm tăng chi phí.

Nếu một người nổi tiếng có 5.000.000 follower đăng một bài, riêng bài đó có thể yêu cầu **5 triệu mục inbox**. Số follower trung bình của hệ không phản ánh cú sốc này.

### 8.2. Chọn phương án dựa trên tỷ lệ đọc/ghi

| Workload | Xu hướng thường thấy |
| --- | --- |
| Người dùng mở bảng tin nhiều, tác giả đăng ít, số follower vừa phải | Fan-out-on-write có thể tiết kiệm công việc đọc |
| Rất nhiều bài mới, người đọc hiếm khi mở ứng dụng | Fan-in-on-read tránh tạo inbox cho người không đọc |
| Một vài tác giả có hàng triệu follower | Fan-out thuần túy dễ tạo write amplification cực lớn |
| Người dùng theo dõi rất nhiều tác giả | Fan-in có thể phải giải bài toán merge và filter lớn |
| Bảng tin cần xếp hạng cá nhân hóa theo hành vi mới nhất | Fan-in hoặc mô hình lai có thể linh hoạt hơn việc đóng băng thứ tự khi ghi |
| Hệ cần timeline theo thứ tự thời gian, tải đọc cao | Inbox đã sắp theo thời gian có thể phù hợp |
| Nhiều cập nhật/xóa/chỉnh quyền sau khi đăng | Fan-out cần chi phí đồng bộ các bản sao hoặc xác minh dữ liệu gốc |

Đây là các **giả thuyết kiến trúc**, cần kiểm chứng bằng dữ liệu đại diện và tải thực tế. Ngoài số follower trung bình, phải nhìn **phân bố đuôi**: tác giả rất nổi tiếng và người dùng theo dõi hàng chục nghìn nguồn có thể chi phối p99.

## 9. Fan-in khi đọc không nhất thiết là quét toàn bộ dữ liệu

Một cách fan-in đơn giản dùng `$in` để hỏi toàn bộ tập tác giả trong một truy vấn. Nhưng có những chiến lược nâng cao:

### 9.1. Lấy top N của từng tác giả rồi hợp nhất

Giả sử Mai theo dõi An, Bình và Chi, cần 20 bài gần nhất:

~~~text
An:    10:20 post-A3, 09:10 post-A2, 08:00 post-A1
Bình:  10:40 post-B2, 08:50 post-B1
Chi:   10:30 post-C2, 07:00 post-C1

Merge theo publishedAt DESC:
post-B2, post-C2, post-A3, post-A2, post-B1, ...
~~~

Có thể duy trì một cursor ở mỗi nguồn và dùng **priority queue/heap** để chọn item mới nhất. Khi một item được lấy từ nguồn An, đọc tiếp một item khác của An rồi đưa vào heap. Đây là ý tưởng *k-way merge*.

Nếu các luồng nguồn đã được sắp, chọn từ `S` nguồn bằng heap có chi phí xử lý phía ứng dụng thường là `O(K log S)` cho `K` lần lấy item **sau khi đã có candidate/cursor phù hợp**; chưa tính chi phí khởi tạo `S` nguồn, số request, network và lượng dữ liệu phải lọc. Trong thực tế, đọc từ 20.000 tác giả ngay khi mở bảng tin vẫn có thể rất đắt.

### 9.2. Index theo tác giả và thời gian

Một index gợi ý:

~~~javascript
lab.posts.createIndex({
  authorId: 1,
  publishedAt: -1,
  _id: -1
});
~~~

Index này phục vụ đường đọc “bài của **một tác giả** theo thời gian”. Nếu query theo nhiều tác giả với `$in` và còn cần sắp xếp toàn cục, hãy dùng `explain("executionStats")`: bộ tối ưu có thể chọn cách truy cập khác tùy cardinality, phân bố dữ liệu và điều kiện lọc.

### 9.3. Cache và partial materialization

Có thể cache kết quả `feedByFanIn` trong thời gian ngắn, hoặc giữ một **candidate pool** của các tác giả nổi bật. Cache làm giảm số lần query lặp nhưng phải xác định TTL, invalidation và chính sách nhất quán khi có bài mới hoặc quyền truy cập thay đổi.

Lưu cache không làm biến mất chi phí: nó **dịch chi phí sang việc làm mới và quản lý bản sao tạm thời**. Một cache sai quyền riêng tư vẫn có thể gây lộ nội dung.

## 10. Fan-out khi ghi không bắt buộc nhân bản toàn bộ bài đăng

Giả sử mỗi bài có body dài 10 KB, nhưng inbox item chỉ gồm ID, tác giả và thời gian, khoảng vài chục hoặc vài trăm byte trước overhead lưu trữ. Fan-out **con trỏ** có thể tiết kiệm hơn fan-out **nội dung đầy đủ** rất nhiều.

| Cách lưu | Mục inbox chứa | Ưu điểm | Chi phí / rủi ro |
| --- | --- | --- | --- |
| **Pointer fan-out** | `postId`, `authorId`, `publishedAt` | Bản sao nhỏ; nội dung sửa ở một nơi | Cần thêm bước hydrate, kiểm tra trạng thái/ACL |
| **Snapshot fan-out** | ID, thời gian và thêm tiêu đề/ảnh đại diện/preview | Đọc nhanh, ít truy vấn phụ | Metadata có thể cũ; cập nhật/xóa nhiều bản sao |
| **Full-content fan-out** | Toàn bộ nội dung và metadata | Đọc ít phải join nguồn | Dung lượng và write amplification lớn, đồng bộ/xóa khó |
| **Fan-out theo nhóm** | Một mục cho một nhóm người nhận thay vì mỗi cá nhân | Có thể giảm số bản sao trong một số bài toán | Khi đọc vẫn phải xác định thành viên/điều kiện truy cập |

**Lặp dữ liệu là một lựa chọn có granularity.** Có thể sao chép đúng những trường cần cho sort/preview, giữ nội dung canonical và áp dụng cơ chế hydrate theo batch.

Với pointer fan-out, nếu trả 20 mục và phải truy vấn từng bài riêng lẻ, API dễ gặp **N+1 queries**. Nên xem cách lấy nhiều bài một lượt:

~~~javascript
const entries = lab.feed_inbox.find({
  userId: "u-mai"
})
  .sort({ publishedAt: -1, postId: -1 })
  .limit(20)
  .toArray();

const ids = entries.map(e => e.postId);

const posts = lab.posts.find({
  _id: { $in: ids },
  status: "PUBLISHED",
  visibility: "PUBLIC"
}).toArray();

const byId = new Map(posts.map(post => [post._id, post]));

const hydrated = entries
  .map(entry => byId.get(entry.postId))
  .filter(Boolean);
~~~

Đoạn này chỉ dùng **bài PUBLIC trong phòng thực hành**. Với dữ liệu thật, cần **kiểm tra lại quyền** và quan hệ hiện tại, không xem một item inbox là bằng chứng người nhận còn quyền đọc. Nếu một số bài đã bị ẩn/xóa, trang có thể ít hơn 20 mục; ứng dụng có thể cần đọc thêm các ứng viên để lấp trang, theo giới hạn tài nguyên.

Một truy vấn với `$in` không tự bảo đảm thứ tự kết quả theo `ids`. Bước `map` qua `entries` giúp giữ thứ tự bảng tin đã xác định.

## 11. Bài bị xóa, bị sửa hoặc chuyển quyền riêng tư

Đây là nơi fan-out phơi bày **chi phí duy trì bản sao** rõ nhất.

### 11.1. Xóa bài đăng

Nếu `post-101` bị xóa hoặc đổi trạng thái `DELETED`:

- Với **fan-in**, truy vấn vào `posts` có thể loại bài theo trạng thái nguồn, tùy tính nhất quán của đường đọc.
- Với **fan-out**, các mục inbox `userId|post-101` có thể vẫn tồn tại. Nếu chỉ trả nội dung snapshot, người đọc còn có thể thấy bài đã xóa.

Có nhiều chính sách:

1. **Ẩn tức thì ở đường đọc bằng trạng thái nguồn:** hydrate và lọc trạng thái/ACL trước khi hiển thị.
2. **Phát sự kiện xóa để dọn inbox:** xóa hoặc tombstone những mục mang `postId` tương ứng.
3. **Kết hợp cả hai:** lọc an toàn khi đọc và dọn dữ liệu dẫn xuất bất đồng bộ để tiết kiệm dung lượng.

Cách thứ ba thường hữu ích khi **không được phép hiển thị bài đã thu hồi**, nhưng dọn hàng triệu inbox không thể luôn hoàn tất ngay lập tức.

Nếu hệ có yêu cầu xóa dữ liệu theo chính sách riêng tư, phải xét cả snapshot, cache, search index, backup/retention và dữ liệu sự kiện. **Chỉ xóa canonical document không nhất thiết xóa mọi bản sao dẫn xuất**.

### 11.2. Sửa nội dung hoặc tên tác giả

Nếu inbox lưu `bodyPreview` hoặc `authorDisplayName`, khi bài/tác giả đổi thông tin, view có thể cũ. Quyết định đúng phụ thuộc nghiệp vụ:

- Trường cần luôn mới: dùng canonical source hoặc phát sự kiện cập nhật bản sao.
- Trường là **snapshot lịch sử** có chủ đích: có thể không cần cập nhật.
- Trường nhạy cảm hoặc bị thu hồi: phải có đường chặn hiển thị phù hợp, không dựa hoàn toàn vào fan-out chậm.

Không được coi “dữ liệu có thể cũ vài giây” là chấp nhận được nếu đó là dữ liệu đã bị cấm truy cập.

### 11.3. Visibility và block/unfollow

Một bài chỉ cho follower xem không thể được bảo vệ chỉ bằng điều kiện “đã từng được gửi vào inbox”. Người dùng có thể bỏ theo dõi, bị tác giả chặn hoặc bị thu hồi quyền.

Do đó, **ACL là quy tắc ở thời điểm đọc**, trừ khi nghiệp vụ có một cơ chế cấp quyền bất biến được xác định rõ. Với feed có nội dung riêng tư, bước hydrate thường phải kết hợp kiểm tra **viewerId + postId + quan hệ được phép + trạng thái hiện tại**.

Đối với fan-in, cũng không được chỉ kiểm tra người đọc có ID tác giả trong danh sách follow cũ rồi bỏ qua block/privacy; danh sách quan hệ và chính sách truy cập phải được xử lý theo trạng thái nhất quán đã cam kết.

## 12. Theo dõi mới, bỏ theo dõi và phần lịch sử nào được hiển thị

Một người mới theo dõi An tại 11:00. Các bài An đăng lúc 08:00 và 10:00 có được hiện trên bảng tin của người đó không?

Không có câu trả lời duy nhất. Cần chọn **chính sách nghiệp vụ** trước khi tạo mô hình:

| Chính sách | Hệ quả với fan-out | Hệ quả với fan-in |
| --- | --- | --- |
| **Hiện toàn bộ bài lịch sử công khai của tác giả** | Cần backfill những bài cũ vào inbox hoặc đọc bổ sung | Truy vấn các bài cũ của tác giả mới theo dõi |
| **Chỉ hiện bài đăng từ thời điểm theo dõi** | Fan-out những bài mới sau follow | Cần lọc theo thời gian của follow edge, không chỉ `authorId IN (...)` |
| **Hiện tối đa N bài gần nhất khi mới theo dõi** | Backfill N mục, tránh quét lịch sử vô hạn | Truy vấn chọn lọc N bài mỗi tác giả hoặc nhóm |
| **Bỏ theo dõi thì ẩn ngay tất cả bài của tác giả** | Phải lọc theo quan hệ hiện tại hoặc xóa inbox items | Bỏ tác giả khỏi danh sách nguồn ngay khi quan hệ có hiệu lực |

Đây là ví dụ rõ về **tính đúng**: phép fan-in ở phần thực hành trả bài lịch sử công khai của tác giả đang được theo dõi. Nếu nghiệp vụ muốn “chỉ từ thời điểm follow”, cần lưu `createdAt` của cạnh follow và có điều kiện lọc theo thời gian tương ứng. Cùng số bài hiển thị nhưng sai chính sách thì không phải mô hình đúng.

### 12.1. Race condition khi follow thay đổi trong lúc fan-out

Giả sử worker đã chụp danh sách follower ở 10:00, trong khi Mai bỏ theo dõi An ở 10:01. Worker xử lý tới Mai ở 10:02 và thêm bài vào inbox.

Giải pháp phải xác định **mốc hiệu lực** và **quy tắc lọc khi đọc**. Nếu bỏ theo dõi có hiệu lực ngay, không được dựa duy nhất vào snapshot của worker. Có thể kết hợp xóa/lọc mục cũ, kiểm tra quan hệ hiện tại và event xử lý cập nhật sau khi danh sách fan-out được tạo.

Nếu nghiệp vụ yêu cầu “người đã theo dõi tại thời điểm đăng bài vẫn xem được bản sao kể cả sau khi unfollow”, đó là một hợp đồng khác; nó phải được mô tả và kiểm chứng riêng.

## 13. Fan-out dưới tải: batch, idempotency và thứ tự sự kiện

### 13.1. Batch và backpressure

Mỗi bài có thể có hàng triệu người nhận. Không nên giữ toàn bộ follower IDs trong RAM và ghi lần lượt trong một request HTTP. Một hệ thống phát tán có thể dùng:

~~~text
Event post-104 published
        |
        v
Chia danh sách follower thành nhiều batch có cursor
        |
        +-- batch 1: recipients 1..1000
        +-- batch 2: recipients 1001..2000
        +-- batch 3: recipients 2001..3000
        ...
        |
        v
Bulk upsert vào các partition inbox
        |
        v
Ghi tiến độ + retry những batch thất bại
~~~

Kích thước batch phải được chọn dựa trên throughput, giới hạn lệnh ghi và độ trễ của database. **Bulk write không đồng nghĩa một transaction cho toàn bộ batch**; kết quả có thể có thao tác thành công và thao tác thất bại, cần phân tích kết quả và retry idempotent.

Backpressure giúp tránh fan-out đẩy hàng đợi, disk hoặc index write đến mức làm chậm những thao tác quan trọng khác.

### 13.2. Idempotency key cần xác định đúng phạm vi

Một mục bảng tin theo `(viewerId, postId)` thường cần xuất hiện tối đa một lần. Dùng khóa duy nhất theo cặp này giúp chống nhân bản khi worker nhận lại event.

Tuy nhiên, có những nghiệp vụ mà cùng post được phát lại trong **hai chiến dịch khác nhau** và phải tạo hai thông báo riêng. Khi đó khóa idempotency phải chứa `campaignId` hoặc `deliveryId`. Không thể áp dụng một công thức khóa duy nhất cho mọi loại fan-out.

### 13.3. Sắp xếp theo thời gian xuất bản, không theo thời điểm worker hoàn thành

Post A được tạo lúc 08:00, post B được tạo lúc 08:05. Do retry, worker phát bài A đến một inbox lúc 08:10, còn bài B đã tới lúc 08:06.

Nếu sort theo **insertedAt của inbox item**, A có thể nhảy lên đầu dù cũ hơn. Để timeline theo thời gian đăng bài, phải sort theo **`publishedAt` của bài canonical**, kèm khóa phụ `postId` cho trường hợp trùng thời gian.

Nếu ứng dụng dùng **ranking score cá nhân hóa** thay vì timeline theo thời gian, phải định nghĩa riêng score, độ ổn định và cơ chế tái xếp hạng. Không thể dùng nguyên tắc thời gian đăng bài rồi giả rằng nó giải quyết feed được xếp hạng theo sở thích.

### 13.4. Thay đổi metadata phải có version

Giả sử bài `post-101` được sửa nội dung phiên bản 2, nhưng event phiên bản 1 đến sau và ghi đè preview của phiên bản 2 ở một inbox. Nếu dữ liệu dẫn xuất được cập nhật vô điều kiện, người đọc thấy nội dung cũ.

Có thể gắn `sourceVersion` hoặc số thứ tự sự kiện theo từng post và chỉ chấp nhận cập nhật mới hơn bằng thao tác có điều kiện. Không nên so sánh timestamp từ nhiều máy như một thứ tự tuyệt đối nếu hệ không bảo đảm điều đó.

## 14. Hot author và hot reader: hai loại nút nghẽn khác nhau

Không chỉ tổng số người dùng quyết định mô hình. **Độ lệch phân bố** thường là yếu tố quan trọng nhất.

### 14.1. Hot author: tác giả có rất nhiều follower

Một tác giả có 5 triệu follower đăng một bài:

~~~text
Một ghi vào posts
        |
        v
5.000.000 mục inbox cần tạo nếu fan-out toàn bộ
        |
        +-- tải ghi lớn
        +-- hàng đợi dài
        +-- index update nhiều
        +-- mất thời gian phát tán
        +-- nhiều mục có thể không bao giờ được đọc
~~~

Đó là **write amplification** theo số người nhận. Nếu phần lớn người theo dõi không mở ứng dụng trong ngày, nhiều ghi đã được thực hiện mà không được sử dụng ngay.

### 14.2. Hot reader: người theo dõi rất nhiều tác giả

Một người theo dõi 20.000 tài khoản và mở feed liên tục:

~~~text
Một request đọc
        |
        v
Tập 20.000 nguồn cần xem xét hoặc rút gọn
        |
        +-- fan-in nhiều nguồn
        +-- merge nhiều danh sách
        +-- lọc quyền và trạng thái
        +-- pagination phức tạp
~~~

Đó là **read amplification** theo số nguồn và số ứng viên. Nếu ứng dụng vẫn muốn feed chỉ 20 bài, việc tìm **đúng 20 bài gần nhất** mà không bỏ sót bài ở những nguồn ít hoạt động là một bài toán cần giải quyết, không chỉ là đặt `LIMIT 20` cho từng nguồn rồi ghép tùy ý.

### 14.3. Người dùng có cả hai đặc điểm

Một tài khoản có thể vừa có nhiều follower vừa theo dõi nhiều người. Hệ phải kiểm tra **phân bố follower count**, **following count**, **tần suất đăng**, **tần suất mở feed** và **mức tương tác**. Chỉ dùng trung bình sẽ che mất những tác giả/người đọc ở đuôi phân bố gây tốn phần lớn tài nguyên.

## 15. Chiến lược lai: fan-out tác giả thường, fan-in tác giả rất lớn

Một kiến trúc phổ biến về mặt ý tưởng là **hybrid fan-out**:

1. Với tác giả có quy mô vừa và tần suất đăng hợp lý, đưa bài vào inbox người theo dõi.
2. Với tác giả có lượng follower cực lớn, không tạo mục cho từng người; giữ bài trong kho tác giả để **fan-in tại thời điểm đọc**.
3. Khi người dùng mở feed, kết hợp **inbox đã fan-out** với **bài mới từ những tác giả lớn đang theo dõi**.
4. Gộp, khử trùng theo `postId`, kiểm tra quyền và sắp theo quy tắc feed.

~~~text
                        Post mới
                           |
                      Phân loại tác giả
                      /             \
                     v               v
            Tác giả bình thường   Tác giả nhiều follower
                     |               |
                     v               v
               Fan-out inbox    Chỉ giữ bài canonical
                     |               |
                     +-------+-------+
                             |
                   Người dùng mở bảng tin
                             |
                             v
                     Inbox + pull sources
                             |
                             v
                  Merge / dedup / ACL / sort
                             |
                             v
                         Trang feed
~~~

Ưu điểm là tránh **ghi theo hàng triệu follower** của tác giả cực lớn, trong khi vẫn giữ đường đọc nhanh cho phần đông bài đăng.

Chiến lược lai cũng có chi phí riêng:

- Một người dùng theo dõi nhiều tác giả “lớn” vẫn tạo tải fan-in đáng kể.
- Khi tác giả đổi phân nhóm, có thể tồn tại cả inbox item cũ và bài được kéo trực tiếp, phải **dedup**.
- Pagination qua hai nguồn phải giữ **cùng thứ tự và cursor**, tránh lặp hoặc bỏ sót giữa các trang.
- Chính sách xóa/visibility phải được thực thi thống nhất ở cả hai đường.
- Ngưỡng phân loại cần dựa trên tải thực tế, không phải một con số follower tùy ý.

### 15.1. Không có ngưỡng follower phù hợp với mọi hệ

Một tác giả có 100.000 follower nhưng chỉ đăng một bài/tháng có thể rẻ hơn tác giả có 20.000 follower đăng 100 bài/ngày.

Một tiêu chí tốt cần xét **fan-out work per time**:

\[
\text{fanoutWritesPerDay(author)} \approx
\text{postsPerDay(author)} \times \text{eligibleFollowers(author)}
\]

Cũng nên xét mức độ người theo dõi **thực sự đọc**: với một bài rất ít người xem, tạo inbox cho mọi follower có thể lãng phí. Với một người đọc hoạt động liên tục, view đã chuẩn bị sẵn có thể đáng giá.

## 16. Phân trang và thứ tự khi đọc bảng tin

Bảng tin thường phân trang. Dù dùng fan-out hay fan-in, **offset pagination** sâu có thể đắt và không ổn định khi dữ liệu mới liên tục được chèn.

### 16.1. Cursor theo (publishedAt, postId)

Nếu thứ tự là:

~~~text
ORDER BY publishedAt DESC, postId DESC
~~~

thì cursor của trang tiếp theo nên lưu **cả thời gian và ID của item cuối trang trước**.

Ví dụ fan-out:

~~~javascript
// Cursor thực tế phải được lấy từ phần tử cuối trang trước.
const lastTime = new Date("2026-11-14T09:00:00Z");
const lastPostId = "post-102";

lab.feed_inbox.find({
  userId: "u-mai",
  $or: [
    { publishedAt: { $lt: lastTime } },
    {
      publishedAt: lastTime,
      postId: { $lt: lastPostId }
    }
  ]
})
  .sort({ publishedAt: -1, postId: -1 })
  .limit(20)
  .toArray();
~~~

Giá trị cursor trên chỉ minh họa, không phải token được tạo tự động. Nếu thay thứ tự theo **ranking score**, cursor phải phù hợp với score, phiên bản thuật toán và tie-breaker; không thể áp dụng máy móc cursor thời gian.

### 16.2. Fan-in có thể cần nhiều cursor nguồn

Với *k-way merge*, mỗi tác giả có dòng bài được sắp theo thời gian. Khi sang trang, cần biết đã đọc tới đâu ở từng nguồn hoặc có một tiêu chí toàn cục đảm bảo lấy đủ các ứng viên cũ hơn cursor.

Đơn giản lấy “20 bài mới nhất của mỗi tác giả” cho mọi trang có thể thiếu bài ở những trang sâu. Thiết kế cursor, giới hạn bộ nhớ và tính ổn định giữa lúc quan hệ theo dõi thay đổi cần được định nghĩa rõ.

### 16.3. Dedup theo ID nghiệp vụ

Một bài có thể xuất hiện ở nhiều nguồn: có trong inbox và đồng thời được kéo từ tác giả, hoặc cùng bài được đề xuất từ nhiều quan hệ. Trước khi trả trang, có thể cần khử trùng theo `postId` hoặc `contentId`, tùy nghiệp vụ.

Nếu ứng dụng có khái niệm “repost” là một hoạt động riêng, việc dedup theo bài gốc có thể làm mất một hành vi có ý nghĩa. Khóa dedup phải phản ánh **đơn vị hiển thị** được sản phẩm định nghĩa, không phải mặc nhiên luôn dùng `postId`.

## 17. Kiểm chứng với bộ truy vấn và dữ liệu đại diện

Một mô hình chỉ được coi là phù hợp khi đạt **tính đúng** và **SLO** trên workload đại diện.

### 17.1. Bộ thao tác cần đo

| Mã | Thao tác | Kết quả cần đúng | Chỉ số đo |
| --- | --- | --- | --- |
| Q1 | Đọc 20 bài mới nhất của người dùng bình thường | Đúng bài được phép xem, đúng thứ tự | p50/p95/p99, docs/keys examined |
| Q2 | Đọc feed của người theo dõi 20.000 tác giả | Không bỏ sót/nhân đôi bài ngoài giới hạn | Latency, lượng nguồn/ứng viên, CPU |
| Q3 | Đăng bài từ tác giả 100 follower | Bài xuất hiện theo hợp đồng | Write latency, queue lag, số inbox writes |
| Q4 | Đăng bài từ tác giả 5 triệu follower | Không làm quá tải đường ghi | Throughput, backlog, thời gian fan-out |
| Q5 | Xóa hoặc ẩn bài đã phát | Không lộ nội dung đã bị thu hồi | Tỷ lệ stale, số mục còn tồn |
| Q6 | Follow/unfollow khi đang fan-out | Feed đúng theo chính sách follow | Số mục sai, độ trễ cập nhật |
| Q7 | Retry cùng event nhiều lần | Không tạo mục inbox trùng | Số duplicate, số lần retry |
| Q8 | Tải hỗn hợp: đăng và đọc đồng thời | Không bỏ event, vẫn đạt SLO | RPS, error rate, backlog |

Các ngưỡng cụ thể (ví dụ p95 bao nhiêu ms, lag chấp nhận bao nhiêu giây) phải được quyết định theo nghiệp vụ và môi trường. Không nên điền một con số “chuẩn NoSQL” không có cơ sở.

### 17.2. Dữ liệu đại diện cần có skew

Một bộ dữ liệu chỉ gồm tác giả có 10 follower và người đọc theo dõi 5 tác giả sẽ làm cả hai cách trông rất nhẹ. Nên có:

- Tác giả thường, tác giả hoạt động nhiều, tác giả có rất nhiều follower.
- Người đọc ít theo dõi và người đọc theo dõi hàng chục nghìn nguồn.
- Tỷ lệ bài bị xóa/chỉnh sửa, thay quyền và chuyển trạng thái.
- Phân bố tần suất người dùng mở feed: người mở mỗi phút, mỗi ngày và gần như không mở.
- Nhiều tác giả đăng đồng thời, nhiều bài có cùng timestamp.
- Feed chứa bài cũ, dữ liệu cache và trường hợp inbox bị thiếu do worker thất bại.

Bài thực hành chỉ có ba bài để hiểu đúng thuật toán. Để đo hiệu năng, cần sinh dữ liệu lớn hơn và mô phỏng đúng tần suất đọc/ghi, hot keys và topology.

### 17.3. Xem execution plan trong MongoDB

~~~javascript
printjson(
  lab.feed_inbox.find({ userId: "u-mai" })
    .sort({ publishedAt: -1, postId: -1 })
    .limit(20)
    .explain("executionStats")
);

printjson(
  lab.posts.find({
    authorId: { $in: ["u-an", "u-binh"] },
    status: "PUBLISHED",
    visibility: "PUBLIC"
  })
    .sort({ publishedAt: -1, _id: -1 })
    .limit(20)
    .explain("executionStats")
);
~~~

Đọc các trường như `totalKeysExamined`, `totalDocsExamined`, `nReturned`, `winningPlan` và `executionTimeMillis` theo khả năng phiên bản MongoDB. Chú ý: `executionTimeMillis` trong `explain` **không phải latency end-to-end** của API. Fan-in còn có bước lấy quan hệ theo dõi; fan-out có thể còn bước hydrate/ACL. Muốn so sánh công bằng, phải đo **toàn bộ công việc để trả cùng dữ liệu cho người dùng**.

### 17.4. Dung lượng và write amplification

Với fan-out, có thể đo:

~~~javascript
for (const collectionName of [
  "posts",
  "follows",
  "feed_inbox"
]) {
  const stats = lab.getCollection(collectionName).stats();

  printjson({
    collection: collectionName,
    count: stats.count,
    logicalSizeBytes: stats.size,
    storageSizeBytes: stats.storageSize,
    totalIndexSizeBytes: stats.totalIndexSize
  });
}
~~~

Phải tính cả index, replication và dữ liệu dẫn xuất. `stats.storageSize` chịu ảnh hưởng storage engine, nén và cấp phát; không nên lấy số document nhân một kích thước tưởng tượng rồi gọi đó là số dung lượng thật.

Đối với fan-in, chi phí lưu trữ inbox có thể bằng không, nhưng đọc nhiều nguồn và cache/aggregator có chi phí CPU, mạng, bộ nhớ. **So sánh chi phí tổng thể**, không chỉ số lượng document.

## 18. Thử tình huống lỗi để hiểu giới hạn của từng chiến lược

### Tình huống A: worker fan-out bị dừng giữa chừng

Một bài có 10.000 follower, worker ghi được 6.000 mục thì mất kết nối.

**Câu hỏi:** Làm sao hoàn tất 4.000 mục còn lại mà không tạo 6.000 mục trùng?

**Hướng xử lý:** dùng idempotent upsert theo người nhận và bài, lưu tiến độ/cursor hoặc phát lại batch có kiểm soát, đối chiếu số mục đích so với tập người nhận theo chính sách đã chọn. Queue có thể giao lại event; tác vụ phải chịu được retry.

### Tình huống B: người dùng bỏ theo dõi

Mai bỏ theo dõi An, nhưng inbox Mai vẫn có 100 bài của An.

**Câu hỏi:** Nếu chính sách “unfollow thì ẩn bài ngay”, đọc inbox có đủ không?

**Hướng xử lý:** chưa đủ. Phải lọc theo quan hệ hiện tại hoặc cơ chế quyền tương đương và có thể dọn mục cũ bất đồng bộ. Tách **khả năng hiển thị ngay** khỏi **dọn vật lý**.

### Tình huống C: bài bị xóa vì vi phạm

Một bài bị đổi sang trạng thái `DELETED` nhưng snapshot inbox chưa cập nhật.

**Câu hỏi:** Có thể tiếp tục phục vụ snapshot cho tới khi cleanup xong không?

**Hướng xử lý:** không nếu hợp đồng yêu cầu ngăn hiển thị ngay. Phải có đường kiểm tra trạng thái/ACL nguồn đáng tin cậy hoặc cơ chế thu hồi tức thì phù hợp, rồi cleanup bản sao dẫn xuất.

### Tình huống D: tác giả nổi tiếng đăng 20 bài một giờ

Fan-out tạo một backlog lớn, các bài đến inbox không theo thứ tự hoàn thành của worker.

**Câu hỏi:** Làm sao hiển thị thứ tự thời gian đúng?

**Hướng xử lý:** lưu `publishedAt` từ nguồn và sort theo `publishedAt DESC, postId DESC`; theo dõi fan-out lag, retry idempotent. Nếu yêu cầu bảng tin đầy đủ ngay, phải có fallback hoặc chiến lược lai trong khi worker còn lag.

### Tình huống E: người dùng theo dõi 30.000 nguồn

Fan-in query theo nhiều authorId trở nên chậm.

**Câu hỏi:** Chỉ tăng `LIMIT 20` có giải quyết được không?

**Hướng xử lý:** không. Giới hạn kết quả không giải quyết toàn bộ công việc chọn ứng viên; cần index, k-way merge, cache, giới hạn số nguồn, ranking candidate hoặc fan-out chọn lọc. Đo trên workload có phân bố giống thực tế.

## 19. Khi nào nên dùng fan-out-on-write, fan-in-on-read hay hybrid?

Một ma trận quyết định:

| Đặc điểm quan trọng | Fan-out-on-write | Fan-in-on-read | Hybrid |
| --- | --- | --- | --- |
| Feed được đọc thường xuyên | Có thể tốt | Có thể tốn tập hợp lặp | Thường cân bằng |
| Ít người nhận mỗi bài | Chi phí fan-out kiểm soát được | Vẫn phù hợp | Có thể không cần hybrid |
| Một số tác giả có follower cực lớn | Dễ gây bùng nổ ghi | Tránh nhân bản theo người nhận | Pull riêng nhóm tác giả lớn |
| Người đọc theo dõi rất nhiều nguồn | Đọc inbox thuận lợi | Dễ gây bùng nổ fan-in | Fan-out phần lớn nguồn |
| Truy vấn cần xếp hạng cá nhân hóa động | Cần cập nhật view/rank | Linh hoạt tập hợp lúc đọc | Có thể lưu candidate, rank lúc đọc |
| Nội dung thường xuyên bị sửa/xóa | Cần đồng bộ bản sao hoặc kiểm tra nguồn | Lọc theo nguồn tương đối trực tiếp | Vẫn cần quy tắc chung |
| Cần xuất hiện bài ngay sau publish | Fan-out async có thể trễ | Có thể thấy ở nguồn trước | Có thể kết hợp pull trong lúc lag |
| Ngân sách lưu trữ hạn chế | Inbox có thể rất lớn | Ít bản sao hơn | Giảm fan-out đắt nhất |
| Độ phức tạp triển khai | Worker/queue/backfill | Merge/index/pagination | Cả hai và dedup/cursor |

Không nên chọn chỉ bằng số follower trung bình. Tốt hơn là:

1. Đo số người theo dõi và bài đăng **theo từng tác giả**, cả p95/p99/max.
2. Đo số nguồn mỗi người theo dõi và số lần mở feed.
3. Xác định SLO đọc, độ trễ đăng bài được chấp nhận và mức nhất quán/ACL.
4. Đánh giá số ghi fan-out dự kiến, index/storage, backlog và chi phí cập nhật.
5. Đánh giá fan-in ở các người đọc nhiều nguồn, kể cả pagination và bộ lọc.
6. Thử hybrid nếu hai loại điểm nóng cùng tồn tại và mỗi phương án thuần túy đều có giới hạn.

## 20. Bài tập tự kiểm tra

### Bài 1: giải thích hai chiến lược

Một tác giả đăng bài mới, có 500 follower. Trình bày đường ghi và đường đọc theo fan-out-on-write và fan-in-on-read.

**Gợi ý:** Fan-out ghi bài và tạo tối đa 500 mục inbox phù hợp; đọc từng người qua inbox. Fan-in ghi bài nguồn; khi người dùng mở feed, tìm danh sách tác giả theo dõi và bài từ các tác giả đó.

### Bài 2: đếm ghi logic

Có 2.000 bài/ngày; mỗi bài cần phát tới trung bình 800 người nhận. Bỏ qua retry, xóa/cập nhật và index, số mục inbox fan-out dự kiến là bao nhiêu?

**Gợi ý:** `2.000 × 800 = 1.600.000` mục/ngày. Đây chỉ là số ghi logic ở bảng tin, không phải byte hay latency.

### Bài 3: dữ liệu đúng nhưng chưa nhất quán

Bài `post-104` đã có trong `posts` nhưng chưa có trong `feed_inbox`. Hai đường đọc trả kết quả khác nhau. Đây là lỗi hay trạng thái tạm thời hợp lệ?

**Gợi ý:** Phụ thuộc hợp đồng. Với fan-out async và eventual consistency có giới hạn lag, đây có thể là trạng thái tạm thời được thiết kế. Nếu SLO cam kết bài xuất hiện ngay, cần xử lý hoặc fallback; phải đo độ trễ.

### Bài 4: idempotency của fan-out

Worker nhận event tạo `post-104` hai lần. Làm sao tránh hai mục giống nhau trong inbox Mai?

**Gợi ý:** Khóa duy nhất theo `(viewerId, postId)` và upsert/insert có điều kiện. Retry phải cho cùng kết quả dữ liệu.

### Bài 5: chọn mô hình cho tác giả “nóng”

Một người có 3 triệu follower đăng 30 bài/ngày, trong khi nhiều follower hiếm khi mở ứng dụng. Chiến lược nào đáng xem xét để giảm lượng ghi?

**Gợi ý:** Fan-in cho nguồn này hoặc hybrid, tránh fan-out 90 triệu mục logic/ngày chỉ từ một tác giả nếu không cần thiết. Nhưng phải đo tải đọc để xác định chi phí chuyển sang thời điểm đọc.

### Bài 6: hai yêu cầu quyền riêng tư

A: bài công khai có thể xuất hiện trễ vài giây. B: bài bị xóa phải biến mất khỏi mọi bảng tin ngay lập tức. Mô hình fan-out con trỏ cần cơ chế nào?

**Gợi ý:** A có thể chấp nhận queue và eventual consistency; B cần kiểm tra trạng thái/ACL đáng tin cậy khi phục vụ bài hoặc một cơ chế thu hồi tương đương, không chỉ cleanup bất đồng bộ.

### Bài 7: follow lịch sử

Lan mới theo dõi An lúc 11:00, còn bài An đăng lúc 08:00. Fan-in trả bài cũ khi chỉ lọc `authorId IN followees`. Cách đó có đúng không?

**Gợi ý:** Đúng nếu sản phẩm cho xem lịch sử của người mới theo dõi. Sai nếu chỉ được xem từ thời điểm follow; cần lưu thời gian follow và lọc theo quy tắc đó. Fan-out muốn cho xem lịch sử cũng phải backfill.

### Bài 8: so sánh toàn nghiệp vụ

Mô hình A đọc inbox nhanh trong 1 query nhưng cần thêm 1 query lấy nội dung và xác minh quyền; mô hình B có một query lấy follows và một query posts. Có thể kết luận A nhanh hơn chỉ từ số query inbox không?

**Gợi ý:** Không. Phải tính **tất cả bước để trả cùng dữ liệu hợp lệ**, cả round trip, index, kích thước kết quả, ACL, cache, latency và tải.

### Bài 9: chọn cursor

Hai bài có cùng `publishedAt`. Vì sao chỉ giữ timestamp trong cursor là chưa đủ?

**Gợi ý:** Có thể lặp hoặc bỏ sót bài cùng timestamp. Cần khóa phụ ổn định như `postId` và điều kiện trang tiếp theo theo đúng thứ tự toàn phần.

### Bài 10: thiết kế hybrid

Hệ có một số tác giả hàng triệu follower, còn phần lớn tác giả có vài trăm follower. Hãy mô tả cách hợp nhất feed khi vừa có dữ liệu inbox vừa có bài kéo trực tiếp từ tác giả lớn.

**Gợi ý:** Chọn ứng viên từ cả hai nguồn, xác minh trạng thái/quyền, khử trùng theo đơn vị hiển thị đã xác định, sắp xếp/rank thống nhất và phân trang với cursor phù hợp. Đo tải fan-in của nguồn lớn và fan-out lag của phần còn lại.

## 21. Điều quan trọng nhất khi chọn vị trí của công việc

**Fan-out-on-write** chuyển một phần chi phí từ thời điểm đọc sang thời điểm ghi: tạo các mục đã chuẩn bị để bảng tin có thể truy vấn nhanh. **Fan-in-on-read** giữ ít bản sao dữ liệu dẫn xuất hơn nhưng chuyển công việc tập hợp, lọc và sắp xếp sang lúc người dùng yêu cầu. **Hybrid** phân chia công việc theo nhóm tác giả, người đọc hoặc loại dữ liệu để tránh các trường hợp cực đoan.

Câu hỏi cốt lõi không phải “có nên lặp dữ liệu trong NoSQL không?” mà là:

- **Ai tạo dữ liệu, ai sẽ đọc và tần suất ra sao?**
- **Một lần ghi phải cập nhật bao nhiêu bản sao, một lần đọc phải truy vấn bao nhiêu nguồn?**
- **Nếu dữ liệu thay đổi, bị xóa hoặc quyền truy cập bị thu hồi thì các bản sao được xử lý thế nào?**
- **Có thể chấp nhận độ trễ xuất hiện của dữ liệu không?**
- **Phương án nào đạt đúng hợp đồng nghiệp vụ với chi phí tổng thể thấp hơn ở tải đại diện?**

Giữ **một nguồn chân lý rõ ràng**, quản lý bản sao bằng **khóa idempotent và cơ chế đồng bộ có thể khôi phục**, kiểm tra **quyền truy cập khi đọc** và đo **read/write amplification** là những nguyên tắc giúp cả fan-out lẫn fan-in trở thành lựa chọn kỹ thuật có thể kiểm chứng.
