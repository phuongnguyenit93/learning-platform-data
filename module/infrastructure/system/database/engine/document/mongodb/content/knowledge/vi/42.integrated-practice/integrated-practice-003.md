# Hoàn thiện CRUD, cập nhật mảng và phân trang ổn định trong MongoDB

## 1. Bài thực hành tổng hợp: quản lý tin đăng cho thuê nhà

Trong một dịch vụ cho thuê nhà, collection **listings** lưu các tin đăng thuộc nhiều tenant. Mỗi tin có trạng thái xuất bản, ngày tạo, giá thuê, nhãn và danh sách phòng. API phải thực hiện ba nhóm chức năng:

1. **CRUD:** tạo tin, đọc đúng tenant, cập nhật một phần dữ liệu, lưu trữ/xóa có kiểm soát.
2. **Cập nhật mảng:** thêm/bỏ nhãn, cập nhật chính xác một phòng hoặc nhiều phòng phù hợp điều kiện, tránh thay cả mảng.
3. **Phân trang ổn định:** trả page theo thứ tự có tie-breaker rõ ràng, không bị trùng/bỏ sót chỉ vì nhiều bản ghi cùng thời gian; hiểu giới hạn khi dữ liệu thay đổi giữa các request.

Nếu triển khai thiếu cẩn trọng, những lỗi thường gặp là:

- Update/xóa dựa vào **_id** mà quên tenantId, dẫn đến sửa dữ liệu của tenant khác.
- **replaceOne** làm mất field chưa được load hoặc mảng vừa được người khác chỉnh.
- Hai request cùng đọc một document rồi ghi đè nhau.
- Dùng điều kiện dotted trên **array of embedded documents** nhưng tưởng hai điều kiện luôn thuộc cùng phần tử.
- Cập nhật **rooms.$** sai phần tử hoặc dùng **$[]** khi chỉ định sửa một phòng.
- Dùng **skip/limit** với sort không unique, khiến bản ghi trùng trang hoặc mất bản ghi khi có inserts.
- Trả nextCursor theo document thứ **pageSize+1** thay vì phần tử cuối đã trả, làm bỏ sót.
- Tin có timestamp giống nhau nhưng chỉ sort **createdAt**, không có thứ tự tổng.

Bài học sẽ triển khai một mô hình và một bộ dữ liệu thống nhất, có thể chạy từng bước trong **mongosh**, sau đó kết nối với thiết kế API/Java, index, concurrency và kiểm thử.

### Mục tiêu

Sau khi hoàn thành bài, bạn có thể:

1. Thiết kế document chứa embedded rooms, tags, revision và timestamps.
2. Seed dữ liệu lab **idempotent** không đụng dữ liệu ngoài bài.
3. Phân biệt **insertOne, find/findOne, updateOne, updateMany, replaceOne, deleteOne**, kết quả và side effects.
4. Dùng **$set, $unset, $inc, $currentDate, $setOnInsert, $push, $addToSet, $pull** đúng mục đích.
5. Dùng **$elemMatch, positional $ , $[] và $[identifier] + arrayFilters** để truy vấn/cập nhật phần tử mảng.
6. Bảo vệ cập nhật bằng tenant predicate, trạng thái và **revision optimistic locking**.
7. Thiết kế **keyset/cursor pagination** với sort **createdAt DESC, _id DESC**, filter và compound index phù hợp.
8. Phân biệt **thứ tự phân trang xác định** với **snapshot consistency** khi dữ liệu được chèn/xóa/chỉnh đồng thời.
9. Thiết kế opaque cursor được xác thực trên API, giới hạn pageSize và không tin tham số do client tự sửa.
10. Kiểm tra hành vi, index/explain và các edge cases bằng test matrix.

> **Môi trường:** Ví dụ sử dụng MongoDB hiện đại và mongosh, database riêng **mongo_crud_pagination_lab_458**, collection **listings_458**. Mỗi document lab có labTag **crud458-v1** và _id bắt đầu bằng **l458-**. Không chạy lệnh deleteMany({}) hoặc drop collection trên môi trường dùng chung. Java/Spring Data chỉ là phần ứng dụng minh họa; hành vi driver/API có thể khác theo phiên bản.

## 2. Hợp đồng dữ liệu và bất biến nghiệp vụ

### 2.1. Một document mẫu

~~~javascript
{
  _id: "l458-001-01",
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  title: "Căn hộ 001-01",
  cityCode: "HCM",
  status: "PUBLISHED",
  monthlyRentVnd: NumberDecimal("9250000.00"),
  tags: ["FURNISHED", "HCM"],
  rooms: [
    {
      roomId: "bed-1",
      type: "BEDROOM",
      areaSqm: 17,
      available: false,
      amenities: ["WIFI", "AC"]
    },
    {
      roomId: "kitchen-1",
      type: "KITCHEN",
      areaSqm: 8,
      available: true,
      amenities: ["STOVE"]
    }
  ],
  createdAt: ISODate("2026-01-15T09:00:00Z"),
  updatedAt: ISODate("2026-01-15T09:00:00Z"),
  revision: NumberLong("1")
}
~~~

### 2.2. Quy tắc của bài

| Trường | Ý nghĩa | Quy tắc |
| --- | --- | --- |
| **_id** | Khóa định danh collection | String cố định trong lab, unique |
| **labTag** | Phân biệt dữ liệu bài thực hành | Luôn giới hạn các lệnh lab |
| **tenantId** | Phân vùng quyền truy cập nghiệp vụ | Query đọc/ghi phải lấy từ auth context đáng tin |
| **title** | Tiêu đề | Không rỗng; validate trước ghi |
| **cityCode** | Mã thành phố | Tập mã được phép theo ứng dụng |
| **status** | DRAFT/PUBLISHED/ARCHIVED | Chỉ chuyển theo workflow hợp lệ |
| **monthlyRentVnd** | Giá thuê VND | Decimal128, không âm |
| **tags** | Mảng nhãn String | Không thêm duplicate nếu dùng set semantics |
| **rooms** | Mảng embedded rooms | roomId unique trong một listing theo business rule |
| **createdAt** | Thời điểm tạo | **Bất biến** sau insert, dùng làm sort key |
| **updatedAt** | Thời điểm sửa | Cập nhật khi ghi |
| **revision** | Optimistic concurrency token | Mọi writer hợp tác phải tăng đúng |
| **deletedAt** | Soft-delete timestamp (nếu có) | Thiếu field nghĩa là chưa xóa trong lab |

**Lưu ý:** MongoDB không tự cưỡng chế sự duy nhất của roomId **bên trong cùng một array** chỉ nhờ unique index multikey. Nếu muốn mỗi listing chỉ có một roomId cụ thể, cần validation/domain logic hoặc data model tương ứng.

### 2.3. Tại sao chọn _id String?

Các ID **l458-001-01**, **l458-001-02** ... là strings có zero-padding, giúp phần thực hành dễ thấy thứ tự từ điển và không nhầm với BSON ObjectId.

Trong production, có thể dùng ObjectId/UUID/domain IDs. Điều quan trọng là:

- Dùng cùng BSON type khi so/query cursor.
- Sort _id có thứ tự ổn định.
- Không chuyển một ID string trông giống ObjectId thành ObjectId tùy tiện.
- Không dùng ID đoán được làm cơ chế authorization.

### 2.4. Document root và phần tử mảng

~~~text
Listing document
   |
   +-- _id
   +-- tenantId
   +-- createdAt
   +-- rooms[] ---------------------+
        |                           |
        +-- roomId: "bed-1"         +-- roomId: "kitchen-1"
        +-- type: "BEDROOM"          +-- type: "KITCHEN"
        +-- areaSqm: 17              +-- areaSqm: 8
        +-- available: false         +-- available: true
        +-- amenities[]              +-- amenities[]
~~~

Một **updateOne** trên listing có atomicity theo **một document**, bao gồm các thay đổi của rooms trong cùng lệnh. Nhưng hai update riêng biệt vẫn có thể xung đột/đè nhau nếu không có guard phù hợp.

## 3. Thiết lập lab tách biệt và seed 24 tin

### 3.1. Database và collection riêng

Mở mongosh vào MongoDB lab local hoặc cluster test được phép truy cập:

~~~javascript
const lab = db.getSiblingDB(
  "mongo_crud_pagination_lab_458"
);
const listings = lab.getCollection("listings_458");
~~~

Không sử dụng collection của khách hàng thật.

### 3.2. Seed ba tenant, mỗi tenant tám tin

~~~javascript
(() => {
  const lab = db.getSiblingDB(
    "mongo_crud_pagination_lab_458"
  );
  const listings = lab.getCollection("listings_458");
  const tag = "crud458-v1";
  const ops = [];

  for (let tenantNo = 1; tenantNo <= 3; tenantNo++) {
    const code = String(tenantNo).padStart(3, "0");
    const tenantId = "tenant-" + code;

    for (let i = 1; i <= 8; i++) {
      const number = String(i).padStart(2, "0");
      const id = "l458-" + code + "-" + number;
      const cityCode = ["HCM", "HN", "DN"][
        (tenantNo + i) % 3
      ];

      // Hai document cùng createdAt để luyện tie-breaker.
      const hour = 8 + Math.floor((i - 1) / 2);
      const createdAt = new Date(
        Date.UTC(2026, 0, 15, hour, 0, 0)
      );

      const doc = {
        _id: id,
        labTag: tag,
        tenantId,
        title: "Căn hộ " + code + "-" + number,
        cityCode,
        status: i % 3 === 0 ? "DRAFT" : "PUBLISHED",
        monthlyRentVnd: NumberDecimal(
          String(8000000 + tenantNo * 1000000
            + i * 250000) + ".00"
        ),
        tags: ["FURNISHED", cityCode],
        rooms: [
          {
            roomId: "bed-1",
            type: "BEDROOM",
            areaSqm: 16 + i,
            available: i % 2 === 0,
            amenities: ["WIFI", "AC"]
          },
          {
            roomId: "kitchen-1",
            type: "KITCHEN",
            areaSqm: 8,
            available: true,
            amenities: ["STOVE"]
          }
        ],
        createdAt,
        updatedAt: createdAt,
        revision: NumberLong("1")
      };

      ops.push({
        replaceOne: {
          filter: { _id: id, labTag: tag },
          replacement: doc,
          upsert: true
        }
      });
    }
  }

  const result = listings.bulkWrite(
    ops, { ordered: false }
  );

  printjson({
    matched: result.matchedCount,
    insertedByUpsert: result.upsertedCount,
    labDocuments: listings.countDocuments({
      labTag: tag
    })
  });
})();
~~~

Kết quả mong đợi với collection lab rỗng: **24 documents**, ba tenants, mỗi tenant tám documents. Có **hai documents cùng createdAt** ở mỗi mốc giờ trong một tenant. Mỗi tenant có **sáu PUBLISHED và hai DRAFT** vì i=3,6 là DRAFT.

Script có thể chạy lại: nó thay chính những documents cùng _id **và** labTag bằng fixture ban đầu. Điều này sẽ **đặt lại mọi thay đổi bạn đã làm trên các fixture đó**, nên chỉ chạy lại khi muốn reset lab. Nếu có document khác trùng _id nhưng không có labTag, upsert có thể gặp duplicate-key thay vì ghi đè. Không drop collection để khắc phục xung đột như vậy.

### 3.3. Kiểm tra phân bố

~~~javascript
const lab = db.getSiblingDB(
  "mongo_crud_pagination_lab_458"
);
const listings = lab.getCollection("listings_458");

printjson(listings.aggregate([
  { $match: { labTag: "crud458-v1" } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      n: { $sum: 1 }
    }
  },
  { $sort: { "_id.tenantId": 1, "_id.status": 1 } }
]).toArray());
~~~

Kỳ vọng:

~~~text
tenant-001: DRAFT 2, PUBLISHED 6
tenant-002: DRAFT 2, PUBLISHED 6
tenant-003: DRAFT 2, PUBLISHED 6
~~~

### 3.4. Kiểm tra timestamp trùng

~~~javascript
printjson(listings.aggregate([
  {
    $match: {
      labTag: "crud458-v1",
      tenantId: "tenant-001"
    }
  },
  {
    $group: {
      _id: "$createdAt",
      n: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray());
~~~

Mỗi createdAt có hai _id. Bộ dữ liệu được cố tình thiết kế như vậy để chứng minh chỉ sort thời gian không đủ cho phân trang ổn định.

## 4. Quyền truy cập và quy tắc an toàn trước mọi CRUD

### 4.1. Luôn scope theo tenant

**Không đủ:**

~~~javascript
listings.updateOne(
  { _id: "l458-002-01" },
  { $set: { title: "Đã sửa" } }
);
~~~

Nếu request thuộc tenant-001 nhưng đoán được _id tenant-002, câu lệnh có thể sửa dữ liệu của tenant khác.

**Đúng trong lab:**

~~~javascript
listings.updateOne(
  {
    _id: "l458-001-01",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  { $set: { title: "Tên đã được cập nhật" } }
);
~~~

Trong sản phẩm thật, tenantId phải lấy từ **security principal/session/token đã được server kiểm chứng**. Client-supplied tenantId hoặc header tự đặt không tự là authorization.

### 4.2. Điều kiện deletedAt

Trong lab, các documents chưa xóa **không có field deletedAt**. Vì vậy các query “đang hoạt động” có thể dùng:

~~~javascript
{ deletedAt: { $exists: false } }
~~~

Điều này **khác** với:

~~~javascript
{ deletedAt: null }
~~~

vì equality null có thể match cả explicit null và missing. Cần định nghĩa một trạng thái thống nhất ngay từ schema design để tránh sai lệch.

### 4.3. Kiểu ID và input validation

Chặn input:

- ID rỗng hoặc sai cú pháp.
- tenantId trống/không thuộc principal.
- title quá dài hoặc rỗng.
- price âm/sai currency hoặc BSON type.
- roomId duplicate.
- pageSize quá lớn.
- sort fields tùy ý gây scan nặng.
- raw MongoDB operators do client cung cấp.

Không trộn raw request JSON vào filter/update object mà không whitelist field names. Ngăn **NoSQL injection/operator injection** bằng typed DTO, validation và query builder an toàn.

### 4.4. Không xem matchedCount bằng 0 là luôn không tồn tại

Một update có filter:

~~~javascript
{
  _id: id,
  tenantId,
  revision: NumberLong("3")
}
~~~

trả matchedCount=0 khi:

- Document không tồn tại.
- Document thuộc tenant khác.
- Document đã soft-delete.
- Revision đã thay đổi.
- Status không thỏa điều kiện.

API có thể phản hồi 404/409 theo policy, nhưng cần phân biệt hành vi và không làm rò dữ liệu xuyên tenant.

## 5. CREATE: insertOne và kiểm soát khóa trùng

### 5.1. Tạo document rõ kiểu

Trên lab, tạo một tin mới không thuộc seed:

~~~javascript
const created = {
  _id: "l458-created-001",
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  title: "Studio mới",
  cityCode: "HCM",
  status: "DRAFT",
  monthlyRentVnd: NumberDecimal("11000000.00"),
  tags: ["FURNISHED"],
  rooms: [
    {
      roomId: "bed-1",
      type: "BEDROOM",
      areaSqm: 20,
      available: true,
      amenities: ["WIFI"]
    }
  ],
  createdAt: ISODate("2026-01-16T08:00:00Z"),
  updatedAt: ISODate("2026-01-16T08:00:00Z"),
  revision: NumberLong("1")
};

printjson(listings.insertOne(created));
~~~

Thao tác này có **side effect** trong database lab. Chạy hai lần với cùng _id sẽ gặp **duplicate key**, không tự tạo thêm một document. Dùng _id ổn định ở đây để dễ quan sát.

### 5.2. Không dùng ObjectId để thay thế validation nghiệp vụ

MongoDB thường tạo _id nếu bạn không cung cấp; ObjectId có tính duy nhất rất cao và tiện, nhưng:

- Không tự xác thực ownership.
- Không bảo vệ khỏi duplicate business request.
- Không tự đảm bảo idempotency của POST.

Nếu client retry tạo booking/listing sau timeout, server có thể tạo hai documents khác _id trừ khi có **idempotency key** hoặc business uniqueness được thiết kế.

### 5.3. Insert, save và upsert khác nhau

| Thao tác | Document có _id trước đó | Ý nghĩa |
| --- | --- | --- |
| **insertOne** | Nếu trùng _id | Lỗi duplicate key |
| **replaceOne** không upsert | Match theo filter | Thay nội dung document đã match |
| **updateOne** không upsert | Match theo filter | Thay đúng fields/operators |
| **updateOne** với upsert:true | Không match | Tạo document từ filter và update theo quy tắc upsert |

Một application sử dụng **save** của ORM/repository có thể thực hiện insert hoặc replace/upsert theo ID. Không dùng save toàn entity như thay thế an toàn cho partial update nếu còn concurrent writers.

### 5.4. Idempotent create bằng request key

Trong production, nếu nghiệp vụ đòi một request chỉ tạo một listing, có thể:

- Tạo idempotencyKey từ client request đã được validate.
- Lưu **tenantId + idempotencyKey** với unique index phù hợp.
- Khi retry, trả kết quả đã tồn tại nếu request body khớp contract.
- Không biến mọi duplicate-key thành success: kiểm tra payload và quyền.

Ví dụ thiết kế chỉ số:

~~~javascript
// Chỉ minh họa khi toàn bộ collection đã có schema/policy request key.
// Không chạy ngay trên collection lab nếu documents chưa có key:
// { tenantId: 1, idempotencyKey: 1 }, unique: true
~~~

Unique index với fields bị thiếu/null có semantics cần xử lý bằng schema validation hoặc **partial unique index** đúng tiêu chí. Không thêm unique index trên hai fields missing vào collection hiện có rồi kỳ vọng mọi documents legacy tự hợp lệ.

## 6. READ: filter, projection, count và sort

### 6.1. Đọc một tin theo tenant

~~~javascript
printjson(listings.findOne({
  _id: "l458-001-01",
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  deletedAt: { $exists: false }
}));
~~~

Lọc tenant từ phía server ngay trong MongoDB; không lấy theo _id rồi kiểm tenant trong Java nếu không cần thiết.

### 6.2. Chỉ lấy field cần thiết

~~~javascript
printjson(listings.find({
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  status: "PUBLISHED",
  deletedAt: { $exists: false }
}, {
  _id: 1,
  title: 1,
  cityCode: 1,
  monthlyRentVnd: 1,
  createdAt: 1
}).sort({
  createdAt: -1,
  _id: -1
}).toArray());
~~~

Projection giúp giảm dữ liệu truyền cho client. MongoDB thường giữ **_id** trong projection trừ khi bạn ghi **_id:0**.

### 6.3. Count chính xác theo filter

~~~javascript
printjson({
  publishedTenant1: listings.countDocuments({
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    status: "PUBLISHED",
    deletedAt: { $exists: false }
  })
});
~~~

Trong lab mới seed, kết quả là **6**. Nếu bạn đã sửa status hoặc soft-delete ở các bước sau, kết quả có thể thay đổi.

**estimatedDocumentCount()** là ước lượng ở mức collection, không thay cho filtered countDocuments khi API cần số bản ghi khớp tenant/status.

### 6.4. Nested query phải phân biệt cùng phần tử

~~~javascript
// Có thể match type của room A và area của room B:
{
  "rooms.type": "BEDROOM",
  "rooms.areaSqm": { $gte: 20 }
}
~~~

Nếu yêu cầu **cùng một room vừa là BEDROOM vừa có diện tích >=20**, dùng:

~~~javascript
printjson(listings.find({
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  rooms: {
    $elemMatch: {
      type: "BEDROOM",
      areaSqm: { $gte: 20 }
    }
  }
}, {
  _id: 1, title: 1, rooms: 1
}).toArray());
~~~

Đây là khác biệt semantics, không chỉ khác performance.

## 7. UPDATE: chỉ thay field cần thiết

### 7.1. $set và $currentDate

Ví dụ sửa tên tin **l458-created-001**:

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    deletedAt: { $exists: false }
  },
  {
    $set: {
      title: "Studio mới gần công viên"
    },
    $currentDate: { updatedAt: true },
    $inc: { revision: NumberLong("1") }
  }
));
~~~

Nếu bạn chưa chạy bước CREATE, matchedCount=0; điều đó không phải lỗi cú pháp.

### 7.2. $unset có tác dụng xóa field

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $unset: { optionalNote: "" },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

$unset field không tồn tại là trường hợp cập nhật không đổi dữ liệu field đó; khi còn $inc/$currentDate thì document vẫn được sửa. Không nhầm missing với explicit null.

### 7.3. Không tự tạo field với $set sai path

Nếu code vô tình ghi:

~~~javascript
{ $set: { monhtlyRentVnd: NumberDecimal("10000000") } }
~~~

thì MongoDB có thể tạo **field sai chính tả** thay vì sửa monthlyRentVnd. Dùng typed DTO, constants, schema validation và integration tests để giảm lỗi field name.

### 7.4. updateOne vs updateMany

**updateOne** sửa tối đa một document match. **updateMany** sửa tất cả match, phù hợp một batch được quản lý có điều kiện rõ:

~~~javascript
// Chỉ chạy có chủ đích trong lab:
printjson(listings.updateMany(
  {
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    status: "DRAFT",
    deletedAt: { $exists: false }
  },
  {
    $set: { reviewState: "PENDING" },
    $currentDate: { updatedAt: true },
    $inc: { revision: NumberLong("1") }
  }
));
~~~

Lệnh không ảnh hưởng tenants khác nhưng có thể sửa hai DRAFT của tenant-001. Đối với production, phải xác định batch-size, write pressure và concurrent updates.

### 7.5. matchedCount và modifiedCount

UpdateResult thường có:

- **matchedCount:** số documents phù hợp filter.
- **modifiedCount:** số documents thật sự bị thay đổi.
- **upsertedId:** ID document mới nếu upsert tạo ra bản ghi.

Một lệnh $set đặt đúng giá trị cũ có thể matchedCount=1 nhưng modifiedCount=0 nếu không có thay đổi khác. Trong các ví dụ kèm $inc, revision tăng nên thường modifiedCount=1.

## 8. replaceOne: hợp lệ nhưng phải hiểu rủi ro

### 8.1. Replacement khác update

~~~javascript
// KHÔNG chạy trên listing fixture nếu chưa chủ động muốn
// thay toàn bộ document:
listings.replaceOne(
  { _id: "l458-001-01", tenantId: "tenant-001" },
  {
    _id: "l458-001-01",
    tenantId: "tenant-001",
    title: "Chỉ còn một ít field"
  }
);
~~~

Nếu match, nhiều fields như rooms, createdAt, revision, labTag có thể **bị mất**. Replacement semantics khác hoàn toàn với $set title.

### 8.2. Khi nào replace phù hợp?

- Thay toàn bộ document theo hợp đồng rõ ràng.
- Dữ liệu được lock/version-guard để tránh lost updates.
- Có validation để mọi required fields được giữ.
- Đã quyết định xử lý unknown fields/schema evolution.

Thay nested object cũng tương tự:

~~~javascript
{ $set: { rooms: [] } }
~~~

là **thay cả array**, không phải sửa một room.

## 9. Atomicity và optimistic concurrency với revision

### 9.1. Một lệnh update trên một document là atomic

~~~javascript
listings.updateOne(
  { _id: id, tenantId: tenant },
  {
    $set: {
      title: newTitle,
      status: "PUBLISHED"
    },
    $inc: { revision: NumberLong("1") }
  }
);
~~~

Các thay đổi trên cùng document trong một update hợp lệ được áp dụng atomic. Nhưng **hai requests riêng biệt** vẫn có thể cạnh tranh.

### 9.2. Lost update

~~~text
T0: Request A đọc revision=3
T1: Request B đọc revision=3
T2: Request A ghi title "A", revision=4
T3: Request B replace toàn document từ snapshot cũ
    -> title "A" có thể bị mất
~~~

### 9.3. Compare-and-set (CAS)

Ví dụ với một fixture còn revision=1 sau seed:

~~~javascript
const result = listings.updateOne(
  {
    _id: "l458-001-01",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    revision: NumberLong("1"),
    deletedAt: { $exists: false }
  },
  {
    $set: {
      title: "Cập nhật có điều kiện revision"
    },
    $inc: {
      revision: NumberLong("1")
    },
    $currentDate: { updatedAt: true }
  }
);

printjson(result);
~~~

Lần đầu có thể matchedCount=1 nếu chưa sửa fixture. Lần hai, revision đã là 2 nên matchedCount=0. Đó là một **conflict/no-match**, không nên retry mù quáng với revision=1.

### 9.4. Khi matchedCount=0

Một service thường:

1. Kiểm tra document có tồn tại trong tenant không, theo policy không tiết lộ dữ liệu ngoài tenant.
2. Nếu bản ghi còn nhưng revision khác, trả **409 Conflict** hoặc đọc lại và áp lại business command theo điều kiện phù hợp.
3. Không tự bỏ revision predicate để “bắt update thành công”.

### 9.5. Revision chỉ có giá trị khi mọi writers tuân thủ

Nếu một admin script sửa rooms mà **không tăng revision**, CAS ở service có thể không phát hiện được. Tất cả write paths cần quy ước: API, worker, batch importer, migration, support tooling.

### 9.6. State transition có điều kiện

Chỉ cho publish từ DRAFT:

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    status: "DRAFT",
    deletedAt: { $exists: false }
  },
  {
    $set: { status: "PUBLISHED" },
    $currentDate: { updatedAt: true },
    $inc: { revision: NumberLong("1") }
  }
));
~~~

Filter bảo vệ business transition ngay ở atomic update: hai requests cố publish cùng một tin có thể chỉ một request match trạng thái DRAFT.

## 10. Mảng tags: $push, $addToSet và $pull

### 10.1. $push cho phép duplicate

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $push: { tags: "NEAR_PARK" },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

Chạy lại có thể thêm **NEAR_PARK** nhiều lần.

### 10.2. $addToSet khi cần uniqueness theo giá trị

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $addToSet: {
      tags: { $each: ["NEAR_PARK", "BALCONY"] }
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

$addToSet tránh thêm **giá trị bằng nhau** vào array, nhưng không tự loại duplicate vốn có từ trước. Đối với embedded documents, equality còn phụ thuộc cấu trúc/giá trị của document, không đồng nghĩa uniqueness theo một field như roomId.

### 10.3. $pull xóa theo giá trị

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $pull: { tags: "NEAR_PARK" },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

$pull loại các phần tử match; nếu duplicate đã tồn tại, nó có thể loại **tất cả phần tử phù hợp**.

### 10.4. $push modifiers

MongoDB hỗ trợ các modifiers cho $push như:

- **$each:** thêm nhiều phần tử.
- **$slice:** giới hạn array sau push.
- **$sort:** sắp xếp array trong thao tác.
- **$position:** vị trí chèn.

Ví dụ lưu **năm thay đổi gần nhất** trong một array nhỏ khi thiết kế đã chấp thuận:

~~~javascript
{
  $push: {
    recentNotes: {
      $each: ["Updated title"],
      $slice: -5
    }
  }
}
~~~

Đừng nhúng lịch sử sự kiện vô hạn vào listing. Nếu mỗi tin có hàng triệu events, sử dụng collection riêng thay vì một mảng có thể vượt 16 MiB.

## 11. Mảng rooms: match đúng một phần tử với $elemMatch

### 11.1. Truy vấn có ít nhất một room lớn

~~~javascript
printjson(listings.find({
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  rooms: {
    $elemMatch: {
      type: "BEDROOM",
      areaSqm: { $gte: 20 },
      available: true
    }
  }
}, {
  _id: 1,
  title: 1,
  rooms: 1
}).toArray());
~~~

$elemMatch đòi các điều kiện thuộc **cùng một phần tử array**, khác với nhiều dotted predicates độc lập.

### 11.2. Không dùng equality toàn document khi chỉ biết roomId

Sai cách cho mục tiêu tìm roomId:

~~~javascript
{ rooms: { roomId: "bed-1" } }
~~~

Điều này so với **giá trị array/embedded document**, không tự có nghĩa “một phần tử rooms có roomId bed-1” như người mới thường mong đợi.

Dùng:

~~~javascript
{ "rooms.roomId": "bed-1" }
~~~

hoặc $elemMatch khi cần điều kiện cùng phần tử.

## 12. Positional $: cập nhật một phần tử array được match

### 12.1. $ đầu tiên

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-01",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    "rooms.roomId": "bed-1"
  },
  {
    $set: {
      "rooms.$.available": true
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

Positional **$** tương ứng với **phần tử đầu tiên của array được query match** trong các trường hợp được hỗ trợ. Query phải có điều kiện match array phù hợp. Không dùng $ khi không xác định array element trong filter.

### 12.2. Hạn chế của positional $

- Nếu nhiều elements có roomId giống nhau, chỉ cập nhật một matching element.
- Nếu query có nhiều array conditions, matching semantics có thể phức tạp/mơ hồ.
- Không phù hợp cho mọi nested arrays hoặc thao tác muốn cập nhật nhiều matching elements.
- Không thay cho validation **roomId unique** theo nghiệp vụ.

Khi cần chọn phần tử bằng tiêu chí rõ và cập nhật một hoặc nhiều, dùng **$[identifier] + arrayFilters**.

## 13. Filtered positional: $[room] và arrayFilters

### 13.1. Cập nhật phòng theo roomId

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-01",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    deletedAt: { $exists: false }
  },
  {
    $set: {
      "rooms.$[room].areaSqm": 24
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  },
  {
    arrayFilters: [
      { "room.roomId": "bed-1" }
    ]
  }
));
~~~

**rooms.$[room].areaSqm** nghĩa là cập nhật areaSqm trên các phần tử rooms được alias **room** match theo arrayFilters.

Nếu có hai phần tử trùng roomId, cả hai có thể bị cập nhật. Vì vậy:

- Validate uniqueness của roomId trong một listing.
- Đừng trông chờ positional syntax tự cưỡng chế uniqueness.
- Nếu cần cập nhật đúng một phần tử về mặt nghiệp vụ, ID của phần tử phải unique.

### 13.2. Nhiều điều kiện trên cùng room

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-02",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $set: {
      "rooms.$[r].available": false
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  },
  {
    arrayFilters: [
      {
        "r.type": "BEDROOM",
        "r.areaSqm": { $gte: 18 }
      }
    ]
  }
));
~~~

Các điều kiện cùng identifier r áp lên **một room element**. Một updateOne chỉ giới hạn số **root documents** được sửa, không mặc định chỉ giới hạn **một matching array element** nếu arrayFilters match nhiều.

### 13.3. arrayFilters và toán tử hạn chế

Không phải mọi MongoDB expression đều hợp lệ trong arrayFilters; tài liệu hạn chế một số operator như **$expr, $text, $where**. Kiểm tra server version và sử dụng các predicates hỗ trợ thay vì copy raw user expressions vào arrayFilters.

### 13.4. Nested array amenities của room

Thêm amenities vào phòng bed-1 mà không nhân đôi giá trị String:

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-01",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $addToSet: {
      "rooms.$[r].amenities": {
        $each: ["WIFI", "ELEVATOR"]
      }
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  },
  {
    arrayFilters: [
      { "r.roomId": "bed-1" }
    ]
  }
));
~~~

Lệnh sửa một embedded array field của matching room, không thay toàn bộ rooms.

### 13.5. $pull một amenity khỏi một room

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-01",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $pull: {
      "rooms.$[r].amenities": "AC"
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  },
  {
    arrayFilters: [
      { "r.roomId": "bed-1" }
    ]
  }
));
~~~

Không remove room chỉ vì cần xóa một phần tử amenities.

## 14. All positional: $[] và cập nhật nhiều phần tử

### 14.1. Thay mọi room trong một listing

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-02",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $set: {
      "rooms.$[].available": false
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

**$[]** tác động lên **mọi phần tử rooms** trong document match, không chỉ BEDROOM. Dùng khi business intent thực sự là “đóng toàn bộ các phòng”.

### 14.2. $[] khác $[r]

| Cú pháp | Phạm vi |
| --- | --- |
| **rooms.$.available** | Phần tử array đầu tiên được query match theo positional semantics |
| **rooms.$[].available** | Mọi phần tử rooms |
| **rooms.$[r].available** | Mọi phần tử thỏa arrayFilters cho r |

Không dùng $[] cho một thao tác nhắm roomId cụ thể.

### 14.3. UpdateMany và arrayFilters

Nếu muốn sửa các BEDROOM của **mọi listings trong tenant-001**, cần chủ động chọn root scope:

~~~javascript
// Chỉ trên lab, có side effect trên nhiều listings:
printjson(listings.updateMany(
  {
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    deletedAt: { $exists: false }
  },
  {
    $set: {
      "rooms.$[r].available": true
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  },
  {
    arrayFilters: [
      { "r.type": "BEDROOM" }
    ]
  }
));
~~~

Tác động gồm **nhiều root documents và các matching room elements**. Dùng updateMany cần review phạm vi, vì một predicate tenant thiếu có thể sửa dữ liệu rất rộng.

### 14.4. Xóa phần tử room theo điều kiện

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-02",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $pull: {
      rooms: { roomId: "kitchen-1" }
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

Lệnh loại **mọi room element** có roomId kitchen-1, không phải xóa collection document. Trong nghiệp vụ thật cần kiểm invariant “listing phải có ít nhất một phòng” hoặc các foreign references trước khi xóa.

## 15. Đọc và cập nhật nguyên tử với findOneAndUpdate

### 15.1. Khi muốn nhận document sau khi sửa

~~~javascript
const updated = listings.findOneAndUpdate(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    deletedAt: { $exists: false }
  },
  {
    $set: { title: "Studio đã chỉnh sửa" },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  },
  {
    returnDocument: "after",
    projection: {
      _id: 1,
      tenantId: 1,
      title: 1,
      revision: 1,
      updatedAt: 1
    }
  }
);

printjson(updated);
~~~

Hành vi return value cụ thể theo mongosh/driver versions; trong mongosh API thông dụng **returnDocument:"after"** trả document sau update. Nếu không match, kết quả có thể null. Không tự coi null là thành công.

### 15.2. Lợi ích

- Filter và update là một thao tác nguyên tử trên một root document.
- Không cần read rồi update rồi read lại bằng ba requests chỉ để lấy trạng thái sau ghi.
- Có thể kết hợp revision/status predicates.

### 15.3. Giới hạn

FindOneAndUpdate không tự đảm bảo multi-document transaction. Nếu thao tác còn phải ghi audit event ở collection khác, cần design consistency/transaction/outbox tương ứng.

## 16. DELETE: soft delete và hard delete

### 16.1. Soft delete được ưu tiên khi cần phục hồi/audit

Ví dụ xóa mềm tin vừa tạo:

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    deletedAt: { $exists: false }
  },
  {
    $set: { status: "ARCHIVED" },
    $currentDate: {
      deletedAt: true,
      updatedAt: true
    },
    $inc: { revision: NumberLong("1") }
  }
));
~~~

Document vẫn tồn tại trong MongoDB; các query active dùng deletedAt **$exists:false** sẽ không trả nó.

### 16.2. Soft delete không đồng nghĩa tự động bảo vệ mọi query

Nếu read API chỉ query:

~~~javascript
{ _id: "l458-created-001" }
~~~

thì vẫn lấy được document ARCHIVED/deletedAt. Cần xây filter active cho mọi paths và quản lý quyền đọc dữ liệu lưu trữ.

### 16.3. Hard delete có điều kiện

Chỉ trên lab, ví dụ xóa chính document bạn đã tạo:

~~~javascript
printjson(listings.deleteOne({
  _id: "l458-created-001",
  labTag: "crud458-v1",
  tenantId: "tenant-001"
}));
~~~

Kết quả có **deletedCount** là 1 nếu match; chạy lại thường là 0. Không dùng deleteMany({}) để reset production.

### 16.4. Xóa hàng loạt

deleteMany có thể xóa nhiều documents; chỉ dùng trong job đã được phê duyệt với filter và backup/audit. Các rủi ro:

- Filter thiếu tenantId.
- Các relationships/references còn tồn tại.
- Change Streams/replication/write load.
- Race với đang tạo dữ liệu mới.
- Không có rollback nếu thiếu backup/retention.

Với cleanup lab, ưu tiên **reset riêng các seed IDs** thay vì xóa mọi collection lạ.

## 17. Bulk write và xử lý lỗi từng phần

### 17.1. Vì sao dùng bulk?

Nhiều thao tác cần update nhiều tin có thể dùng **bulkWrite** để giảm round-trips, nhưng đó không tự là một transaction nhiều document.

~~~javascript
const bulkResult = listings.bulkWrite([
  {
    updateOne: {
      filter: {
        _id: "l458-001-04",
        labTag: "crud458-v1",
        tenantId: "tenant-001"
      },
      update: {
        $set: { reviewState: "CHECKED" },
        $inc: { revision: NumberLong("1") }
      }
    }
  },
  {
    updateOne: {
      filter: {
        _id: "l458-001-05",
        labTag: "crud458-v1",
        tenantId: "tenant-001"
      },
      update: {
        $set: { reviewState: "CHECKED" },
        $inc: { revision: NumberLong("1") }
      }
    }
  }
], {
  ordered: false
});

printjson(bulkResult);
~~~

### 17.2. Ordered vs unordered

- **ordered:true:** các thao tác được xử lý theo thứ tự và dừng khi gặp lỗi theo semantics bulk.
- **ordered:false:** MongoDB có thể tiếp tục những thao tác khác; không giả định thứ tự thực thi.

Nếu một operation fail, cần đọc chi tiết **writeErrors/partial results** thay vì coi toàn bulk là success hoặc rollback toàn bộ.

### 17.3. Khi cần transaction

Một tin và một audit document thuộc hai collections có thể cần invariant **cùng commit/cùng rollback**. Với MongoDB deployment hỗ trợ multi-document transactions, có thể dùng transaction nhưng cần hiểu performance, retry semantics, session/transaction options và giới hạn topology.

Nhiều update trong **cùng một document** đã atomic; không dùng multi-document transaction chỉ vì có hai fields trong rooms.

## 18. Phân trang bằng skip/limit: đơn giản nhưng có nhược điểm

### 18.1. Công thức offset

~~~javascript
const pageNumber = 3;
const pageSize = 2;

const rows = listings.find({
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  status: "PUBLISHED",
  deletedAt: { $exists: false }
}, {
  _id: 1, title: 1, createdAt: 1
})
.sort({ createdAt: -1, _id: -1 })
.skip((pageNumber - 1) * pageSize)
.limit(pageSize)
.toArray();

printjson(rows);
~~~

Offset phân trang phù hợp với dataset nhỏ hoặc admin UI có số lượng trang hạn chế. Nhược điểm:

- Skip cao có thể phải đi qua nhiều keys/records.
- Khi documents được insert/delete trước offset, các trang sau có thể trùng/bỏ sót.
- Nếu sort không có tie-breaker unique, thứ tự giữa records cùng createdAt không xác định.

### 18.2. Ví dụ trùng trang khi insert mới

Trang 1 lúc T0:

~~~text
Sort descending:
  A, B, C, D, E, F

Page size=2
Page 1: A, B
~~~

Trước lúc lấy page 2, có một tin mới X đứng đầu:

~~~text
X, A, B, C, D, E, F
~~~

Query **skip(2).limit(2)** lúc T1 trả:

~~~text
B, C
~~~

B xuất hiện hai lần. Đây là bất ổn do **offset dịch chuyển**, dù sort đã có tie-breaker.

### 18.3. Đặt sort toàn phần trước

Ngay cả khi tiếp tục dùng offset, phải có sort deterministic:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

Không chỉ dùng:

~~~javascript
{ createdAt: -1 }
~~~

vì nhiều bản ghi có thể có cùng timestamp.

## 19. Keyset/cursor pagination: đặt điều kiện theo khóa cuối trang

### 19.1. Tư duy cơ bản

Với sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

ta lấy **createdAt và _id của bản ghi cuối trang hiện tại**, rồi tìm những bản ghi đứng **sau** nó trong thứ tự descending.

Ví dụ:

~~~text
createdAt DESC, _id DESC

10:00, ID=F
10:00, ID=E
09:00, ID=D
09:00, ID=C
08:00, ID=B
08:00, ID=A

Page size 2:
  Page 1 = F, E
  after = (10:00, E)

Page 2:
  09:00 D, 09:00 C
~~~

Nếu createdAt bằng nhau, so _id DESC để giữ thứ tự.

### 19.2. Điều kiện “nhỏ hơn tuple cuối” cho DESC/DESC

Với cursor **lastAt, lastId**, phần đứng sau là:

~~~javascript
{
  $or: [
    {
      createdAt: { $lt: lastAt }
    },
    {
      createdAt: lastAt,
      _id: { $lt: lastId }
    }
  ]
}
~~~

Đây là điều kiện so sánh tuple theo thứ tự lexicographic:

~~~text
(createdAt, _id) < (lastAt, lastId)
~~~

với **sort giảm dần cả hai trường**.

Nếu thay một trong hai chiều sort thành ASC, phải đổi phép so sánh tương ứng; không copy predicate DESC/DESC cho mọi sort direction.

### 19.3. Vì sao phải có _id?

Hai documents cùng createdAt:

~~~text
2026-01-15 11:00Z, l458-001-07
2026-01-15 11:00Z, l458-001-08
~~~

Nếu cursor chỉ lưu lastAt rồi query **createdAt < lastAt**, tài liệu còn cùng timestamp sau page boundary có thể bị bỏ sót. _id làm tie-breaker duy nhất.

### 19.4. Điều kiện để kết quả có thứ tự xác định

- **createdAt** phải có và đúng BSON Date.
- **_id** unique, kiểu BSON nhất quán.
- Sort keys được lưu và không đổi trong vòng đời document.
- Filter (tenant/status...) thống nhất giữa các pages.
- Cursor giữ đúng last returned tuple.
- Không đổi sort direction giữa requests.

Điều này cho **deterministic ordering** khi đọc một tập documents ở một thời điểm. Nó **không tự cho snapshot toàn bộ danh sách trong nhiều HTTP requests**.

## 20. Lab keyset pagination: hàm có thể chạy trong mongosh

### 20.1. Hàm getPage458

Hàm dưới đây dùng **stored BSON names** và trả next cursor dạng JavaScript object để dễ học. Backend production nên ký/opaque token.

~~~javascript
function getPage458(
    listings,
    tenantId,
    pageSize,
    after = null) {
  if (!/^tenant-[0-9]{3}$/.test(tenantId)) {
    throw new Error("Invalid tenantId");
  }
  if (!Number.isInteger(pageSize)
      || pageSize < 1 || pageSize > 10) {
    throw new Error("pageSize must be 1..10");
  }

  const base = {
    labTag: "crud458-v1",
    tenantId,
    status: "PUBLISHED",
    deletedAt: { $exists: false }
  };

  let filter = base;
  if (after !== null) {
    if (!(after.createdAt instanceof Date)
        || Number.isNaN(after.createdAt.getTime())
        || typeof after.id !== "string"
        || !after.id) {
      throw new Error("Invalid cursor");
    }

    filter = {
      $and: [
        base,
        {
          $or: [
            {
              createdAt: { $lt: after.createdAt }
            },
            {
              createdAt: after.createdAt,
              _id: { $lt: after.id }
            }
          ]
        }
      ]
    };
  }

  const rows = listings.find(filter, {
    _id: 1,
    tenantId: 1,
    title: 1,
    status: 1,
    createdAt: 1
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(pageSize + 1)
  .toArray();

  const hasNext = rows.length > pageSize;
  const items = rows.slice(0, pageSize);
  const last = items[items.length - 1];

  return {
    items,
    hasNext,
    nextAfter: hasNext && last ? {
      createdAt: last.createdAt,
      id: last._id
    } : null
  };
}
~~~

### 20.2. Lấy trang 1, 2, 3

~~~javascript
const lab = db.getSiblingDB(
  "mongo_crud_pagination_lab_458"
);
const listings = lab.getCollection("listings_458");

const p1 = getPage458(
  listings, "tenant-001", 2
);
printjson(p1);

if (p1.nextAfter) {
  const p2 = getPage458(
    listings,
    "tenant-001",
    2,
    p1.nextAfter
  );
  printjson(p2);

  if (p2.nextAfter) {
    const p3 = getPage458(
      listings,
      "tenant-001",
      2,
      p2.nextAfter
    );
    printjson(p3);
  }
}
~~~

Với **seed nguyên bản**, mỗi tenant có sáu PUBLISHED documents, pageSize=2 tạo **ba pages hai items**. Page thứ ba không có nextAfter.

Khi bạn đã sửa status, xóa document hoặc chạy các bài tập update trước đó, số kết quả có thể thay đổi. Hãy chạy seed lại nếu muốn đối chiếu con số chuẩn (seed reset những documents fixture).

### 20.3. Quy tắc pageSize+1

Để biết còn trang sau:

1. Query **pageSize + 1** records.
2. Trả về tối đa **pageSize** records đầu.
3. **hasNext = true** nếu lấy được thêm một record.
4. **nextAfter** phải là khóa của **record cuối cùng đã trả**.

Không lấy tuple của **record thừa** (phần tử thứ pageSize+1) làm nextAfter, vì nó chưa được trả cho client và sẽ bị bỏ qua ở request sau.

### 20.4. Cursor cuối cùng

Nếu không có record thừa, **hasNext=false, nextAfter=null**. Bạn không cần phát token tiếp theo. Không kết luận “còn page” chỉ vì response có đúng pageSize items — đó có thể là trang cuối.

### 20.5. Cursor là dữ liệu truy vấn, không phải quyền

Trong lab, client có thể tự sửa after object. Trong production, đừng để client thay token để đọc vượt quyền; lúc nào cũng áp **tenantId từ auth principal**, validate cursor integrity và filter compatibility.

## 21. Compound index cho keyset pagination

### 21.1. Index dành cho query chuẩn

~~~javascript
listings.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "ix458_lab_tenant_status_created_id"
  }
);
~~~

Vì lab query filter equality trên **labTag, tenantId, status** và sort **createdAt DESC, _id DESC**, index này là ứng viên phù hợp. Tìm bằng explain để biết plan thật.

DeletedAt $exists:false vẫn được kiểm tra; index trên chưa chứa deletedAt nên có thể cần FETCH để xác minh filter, tùy plan. Không tự giả định query là fully covered.

### 21.2. Kiểm tra getIndexes

~~~javascript
printjson(listings.getIndexes());
~~~

### 21.3. Explain page đầu

~~~javascript
printjson(
  listings.find({
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    status: "PUBLISHED",
    deletedAt: { $exists: false }
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(3)
  .explain("executionStats")
);
~~~

Theo dõi:

- winningPlan.
- totalKeysExamined.
- totalDocsExamined.
- nReturned.
- executionTimeMillis.
- Có blocking SORT hay index order phù hợp.

Với 24 documents, explain chỉ giúp quan sát semantics, **không chứng minh** index optimal trên hàng triệu records.

### 21.4. Explain page sau

~~~javascript
const lastAt = ISODate(
  "2026-01-15T11:00:00Z"
);
const lastId = "l458-001-08";

printjson(
  listings.find({
    $and: [
      {
        labTag: "crud458-v1",
        tenantId: "tenant-001",
        status: "PUBLISHED",
        deletedAt: { $exists: false }
      },
      {
        $or: [
          { createdAt: { $lt: lastAt } },
          {
            createdAt: lastAt,
            _id: { $lt: lastId }
          }
        ]
      }
    ]
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(3)
  .explain("executionStats")
);
~~~

Tuple trong ví dụ chỉ để minh họa cursor query; trong ứng dụng phải dùng tuple **thật của last returned record**, không hardcode một ID có thể không tương ứng timestamp.

### 21.5. Index có thể cần thay khi filter thay đổi

Nếu API còn filter cityCode và price range, cần thiết kế lại index theo query patterns:

~~~javascript
{
  tenantId: 1,
  status: 1,
  cityCode: 1,
  createdAt: -1,
  _id: -1
}
~~~

Ví dụ này thích hợp với cityCode equality; price range có thể ảnh hưởng index ordering/sort support. Không tạo một index cho mọi tổ hợp filter không được sử dụng; cần đo selectivity, workload và write overhead.

## 22. Stable order không đồng nghĩa snapshot

### 22.1. Keyset giúp tránh lệch offset do chèn ở đầu

Với page 1 đã trả hai documents mới nhất, một document mới có timestamp mới hơn phần cuối page 1 sẽ **không match after predicate** ở page 2. Điều này tránh kiểu duplicate do dịch offset như skip.

### 22.2. Nhưng keyset không đóng băng dữ liệu

Giữa hai pages có thể:

- Một document phía sau cursor bị xóa: nó biến mất.
- Một DRAFT được publish và nằm sau cursor: nó có thể xuất hiện.
- Một PUBLISHED bị archive: nó có thể không xuất hiện.
- Một document được insert **backdated** sau cursor: nó có thể xuất hiện.
- Một document thay đổi **createdAt** (nếu cho phép): nó có thể bị lặp hoặc bỏ sót.

Vì vậy, gọi keyset là **phân trang theo thứ tự ổn định**, không tuyên bố nó là một **snapshot bất biến** qua nhiều requests.

### 22.3. Bất biến của sort key

Giải pháp đơn giản: tạo createdAt một lần và **không cập nhật createdAt**. Các trường hợp khác dùng updatedAt cho hiển thị chứ không dùng làm key pagination nếu muốn giảm dịch vị trí.

Nếu sort theo **updatedAt DESC**, chỉ một edit có thể kéo listing sang đầu danh sách, khiến nó không còn ở chỗ cũ. Muốn “recently updated” thì điều này là semantics cố ý, nhưng pagination cần chấp nhận hoặc xử lý chặt hơn.

### 22.4. High-water anchor

Một số API lưu **anchor tuple** của item đầu tiên khi bắt đầu duyệt, và trên các trang sau chỉ cho items ở hoặc sau anchor theo thứ tự. Điều này có thể ngăn nhiều inserts **mới hơn anchor** đi vào kết quả.

Nhưng:

- Một insert backdated vẫn có thể xuất hiện.
- Xóa/status changes vẫn ảnh hưởng membership.
- Anchor **không thay thế snapshot read**.

Khi cần export chính xác một tập dữ liệu cố định, cân nhắc snapshot-consistent operation hoặc materialized job result theo MongoDB deployment/version, readConcern và retention requirements.

### 22.5. Snapshot consistency có trade-offs

MongoDB hỗ trợ read concerns/transactions/snapshot reads trong những điều kiện/version phù hợp. Nhưng giữ một snapshot qua nhiều HTTP requests có thể đòi session/timestamp management, giới hạn thời gian lưu history, resource costs và retry policy. Không mặc nhiên cho rằng chỉ truyền một cursor token là đã được snapshot.

Với API listing thông thường, keyset + immutable sort keys thường là lựa chọn cân bằng; với tài chính/kiểm toán/export nhất quán, yêu cầu mạnh hơn.

## 23. Opaque cursor ở API production

### 23.1. Không lộ cursor object thô như contract cố định

Mẫu API:

~~~json
{
  "items": [
    {
      "id": "l458-001-08",
      "title": "Căn hộ 001-08",
      "createdAt": "2026-01-15T11:00:00Z"
    }
  ],
  "hasNext": true,
  "nextCursor": "opaque-token"
}
~~~

**opaque-token** ở đây là placeholder giải thích hình dạng response; không phải token thực tế.

### 23.2. Nội dung logical token

Một token có thể biểu diễn:

~~~json
{
  "v": 1,
  "sort": "createdAt_desc_id_desc",
  "lastCreatedAt": "2026-01-15T11:00:00Z",
  "lastId": "l458-001-08",
  "tenantId": "tenant-001",
  "status": "PUBLISHED",
  "filterHash": "hash-of-canonical-filters",
  "pageSize": 20,
  "expiresAt": "2026-01-16T00:00:00Z"
}
~~~

Timestamps/IDs trong ví dụ mang tính minh họa; không dùng token hết hạn.

### 23.3. Ký token

Backend có thể:

1. Serialize một payload versioned theo canonical JSON format.
2. Tính **HMAC-SHA-256** bằng secret key của server.
3. Encode payload + MAC với Base64url hoặc token format đã chọn.
4. Khi nhận lại, verify MAC bằng constant-time compare.
5. Kiểm tra expiry, token schema version, sort, page size, tenant và filter fingerprint.
6. Chuyển tuple sang đúng BSON Date/ID type và tạo query có tenant predicate tin cậy.

**Base64 không phải mã hóa bảo mật và không chứng minh integrity**. Nếu payload chứa dữ liệu nhạy cảm, cần tránh lưu hoặc dùng encryption/authenticated encryption phù hợp. HMAC chống sửa token nhưng không tự làm nội dung bí mật.

### 23.4. Bind cursor với filter

Client trang đầu filter:

~~~text
tenant=001, status=PUBLISHED, city=HCM
~~~

rồi gửi cursor kèm filter:

~~~text
tenant=002, status=DRAFT
~~~

Nếu server không check filter binding, cursor có thể làm thứ tự/tính đúng của phân trang sai hoặc tạo nguy cơ cross-tenant. Cần validate **tenant từ security context** và hash canonical filters/sort specification.

### 23.5. Page-size limit

Không cho người dùng yêu cầu pageSize=1.000.000 để tải toàn bộ collection. Ví dụ policy:

~~~text
defaultPageSize = 20
maxPageSize = 100
~~~

Giới hạn là quyết định hiệu năng/API của ứng dụng, không phải một giới hạn cố định do MongoDB bắt buộc.

## 24. Java: phác thảo data access an toàn

### 24.1. Không trộn HTTP input với raw query

Ví dụ service ở Java với MongoDB Sync Driver: nhận tenantId đáng tin từ principal và một cursor đã được verify; các fields BSON do code chỉ định:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.ArrayList;
import java.util.List;
import java.util.Date;

record PageKey(Date createdAt, String id) {}

record ListingPage(
    List<Document> items,
    boolean hasNext,
    PageKey nextKey
) {}

ListingPage listPublished(
        MongoCollection<Document> coll,
        String trustedTenant,
        int pageSize,
        PageKey after) {
    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("Invalid pageSize");
    }

    Bson base = Filters.and(
        Filters.eq("labTag", "crud458-v1"),
        Filters.eq("tenantId", trustedTenant),
        Filters.eq("status", "PUBLISHED"),
        Filters.exists("deletedAt", false)
    );

    Bson filter = base;
    if (after != null) {
        filter = Filters.and(
            base,
            Filters.or(
                Filters.lt("createdAt", after.createdAt()),
                Filters.and(
                    Filters.eq(
                        "createdAt", after.createdAt()
                    ),
                    Filters.lt("_id", after.id())
                )
            )
        );
    }

    List<Document> fetched = coll.find(filter)
        .sort(Sorts.orderBy(
            Sorts.descending("createdAt"),
            Sorts.descending("_id")
        ))
        .limit(pageSize + 1)
        .into(new ArrayList<>());

    boolean hasNext = fetched.size() > pageSize;
    List<Document> items = new ArrayList<>(
        fetched.subList(
            0, Math.min(pageSize, fetched.size())
        )
    );

    Document last = items.isEmpty()
        ? null : items.get(items.size() - 1);

    PageKey nextKey = hasNext && last != null
        ? new PageKey(
            last.getDate("createdAt"),
            last.getString("_id")
        )
        : null;

    return new ListingPage(items, hasNext, nextKey);
}
~~~

Đây là **đoạn minh họa phương thức Java**, cần đặt trong class/service và cấu hình driver phù hợp để chạy. Việc dùng into(ArrayList) ở đây **có bound pageSize+1 tối đa 101**, không phải load toàn collection.

### 24.2. Đưa tenant vào base filter

Trường **trustedTenant** phải từ backend security context. ID có thể đoán được, cursor có thể replay; chỉ query filter với tenant và quyền thật mới đảm bảo isolation.

### 24.3. Xử lý kiểu Date và ID

Đoạn Java giả định _id BSON String và createdAt BSON Date, đúng với lab. Nếu đổi sang ObjectId, PageKey cần mang ObjectId hoặc convert đúng kiểu trước khi query. Không so String ObjectId với BSON ObjectId rồi kỳ vọng MongoDB match.

### 24.4. Không trả raw Document trực tiếp qua API

API nên map sang DTO whitelist fields, không lộ labTag, internal revision, audit metadata hoặc fields chứa thông tin riêng tư. Opaque cursor chứa tuple đúng kiểu và filter contract.

## 25. Spring Data MongoDB: mapping và query paths

Một entity đơn giản:

~~~java
@Document(collection = "listings_458")
public class ListingDocument {
    @Id
    private String id;
    private String tenantId;
    private String title;
    private String status;
    private Instant createdAt;
    private List<Room> rooms;

    @Version
    private Long revision;
}
~~~

**Chỉ là trích đoạn minh họa**, không phải class đầy đủ với constructors/getters/imports. Spring Data có hỗ trợ **@Version** optimistic locking khi thao tác thông qua APIs được hỗ trợ. Nhưng:

- Không tự bảo đảm raw MongoDB driver updates cũng tăng version.
- Không tự chống race nếu một writer bỏ qua version.
- Không thay thế business status predicates.
- Không thay API authorization.

Typed MongoTemplate có thể map Java property path thành BSON stored field path khi entity dùng @Field aliases. Mongosh/raw driver phải dùng **tên field BSON thực**.

### 25.1. Cập nhật room qua MongoTemplate

Ý tưởng:

~~~java
Query query = new Query(
    Criteria.where("id").is(listingId)
        .and("tenantId").is(trustedTenant)
);

Update update = new Update()
    .set("rooms.$[r].available", true)
    .filterArray(
        Criteria.where("r.roomId").is("bed-1")
    );

mongoTemplate.updateFirst(
    query, update, ListingDocument.class
);
~~~

Đây là hướng dẫn về API, phải kiểm tra mapping của arrayFilters, @Version behavior và Spring Data version thực tế. Với cập nhật concurrency-critical, nên thêm revision/status guard và kiểm matchedCount.

## 26. Kiểm thử CRUD và array updates

### 26.1. Ma trận kiểm thử chức năng

| Tình huống | Kỳ vọng |
| --- | --- |
| Insert tin mới hợp lệ | Một document với ID và revision ban đầu |
| Insert trùng _id | Duplicate key, không tạo document thứ hai |
| Read đúng tenant | Trả document |
| Read tenant khác | Không trả dữ liệu |
| Update title đúng tenant | Chỉ title/updatedAt/revision đổi |
| Update theo revision cũ | matchedCount=0 hoặc 409 |
| Publish DRAFT | Chỉ một transition hợp lệ |
| Publish PUBLISHED lần nữa | Theo contract no-op/conflict |
| AddToSet tag đã tồn tại | Không nhân đôi tag |
| Push tag cùng giá trị hai lần | Có thể duplicate |
| Pull tag | Loại các phần tử match |
| Update rooms.$ theo roomId | Phần tử được match thay đổi |
| Update rooms.$[r] | Các phần tử thỏa arrayFilters thay đổi |
| Update rooms.$[] | Mọi rooms thay đổi |
| Pull kitchen room | Chỉ phần tử kitchen bị loại |
| Soft delete | Document còn, không còn trong active query |
| Hard delete đúng ID/tenant | deletedCount=1 nếu tồn tại |
| Hard delete tenant khác | deletedCount=0 |

### 26.2. Integration test cần MongoDB thật

Mocked repository không xác minh:

- BSON Decimal128 vs Double/String.
- $elemMatch semantics.
- Array filters hoạt động đúng.
- Unique _id/index.
- Index plan/explain.
- CAS atomicity.

Dùng MongoDB Testcontainers hoặc database test được quản lý cô lập để kiểm chứng những điểm này.

### 26.3. Unit test vẫn có giá trị

Unit tests cho:

- Validate title, rent, roomId.
- State-transition DRAFT → PUBLISHED.
- Cursor payload parsing và HMAC verification.
- Page size bounds/filterHash.
- Error mapping 404/409.
- DTO whitelist fields.

### 26.4. Test kết quả, không chỉ matchedCount

Sau update array, đọc document thực:

~~~javascript
printjson(listings.findOne({
  _id: "l458-001-01",
  labTag: "crud458-v1",
  tenantId: "tenant-001"
}, {
  _id: 1,
  revision: 1,
  rooms: 1
}));
~~~

Kiểm các rooms khác **không bị thay đổi vô ý**.

## 27. Kiểm thử phân trang ổn định và dữ liệu thay đổi

### 27.1. Fixture có cùng createdAt

Seed đã có hai documents cùng timestamp. Test phải kiểm:

- Sort **createdAt DESC, _id DESC** xác định thứ tự.
- Page boundary có thể nằm giữa hai documents cùng createdAt.
- Cursor with tie-breaker không bỏ phần còn lại.

### 27.2. Thu mọi pages và so ID

Một test integration có thể:

1. Đọc trang đầu.
2. Theo nextAfter tới khi null.
3. Gom _id đã trả.
4. Assert không có _id trùng.
5. Assert số IDs bằng countDocuments của **dataset cố định** tại thời điểm test.
6. Assert thứ tự tuple giảm dần.

Chỉ so count như vậy khi dataset **không đổi trong lúc chạy test**. Nếu concurrent writes đang diễn ra, count và pages có thể nhìn những trạng thái khác nhau.

### 27.3. Insert mới giữa trang 1 và 2

Tạo document với createdAt mới hơn last cursor. Keyset page 2 không nên lặp lại một item đã thuộc page 1 chỉ vì insert mới đứng phía trước.

### 27.4. Backdated insert

Tạo document mới có createdAt cũ hơn last cursor. Nó có thể xuất hiện ở page tiếp theo; đây không phải vi phạm keyset semantics. Nếu API hứa snapshot cố định thì cần giải pháp khác.

### 27.5. Soft delete giữa pages

Xóa mềm item chưa được duyệt; nó không xuất hiện ở page sau. Không coi đây là bug của pagination nếu API cung cấp **live view**.

### 27.6. Thay đổi filter

Tạo token trang 1 với status=PUBLISHED, rồi yêu cầu trang 2 với status=DRAFT. Backend phải **từ chối cursor không khớp filter** thay vì tiếp tục trong tập dữ liệu khác.

### 27.7. Cursor bảo mật

Test:

- Token bị sửa một ký tự → invalid signature.
- Token expired → reject.
- Token thuộc tenant khác → reject.
- FilterHash khác → reject.
- Sort ID type sai → reject.
- PageSize vượt max → reject.
- Phiên bản token tương lai → graceful unsupported.

## 28. Query performance và access patterns

### 28.1. Count có thể tốn chi phí

Một API keyset không nhất thiết phải chạy filtered **countDocuments** trên hàng triệu records cho mỗi page. Có thể trả:

~~~json
{
  "items": [],
  "hasNext": false,
  "nextCursor": null
}
~~~

và cung cấp totalCount ở endpoint báo cáo hoặc tùy chọn có chi phí riêng.

### 28.2. Index phải khớp filter và order

Query:

~~~javascript
{
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  status: "PUBLISHED"
}
~~~

sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

index ứng viên:

~~~javascript
{
  labTag: 1,
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

Trong production không có labTag, bỏ prefix đó và thiết kế index thật cho tenant/status/time. Nếu truy vấn kết hợp nhiều optional filters, benchmark các index candidates thay vì tạo mọi hoán vị.

### 28.3. Keyset không phải miễn phí

Với range predicate trên tuple và nhiều optional filters, MongoDB có thể dùng OR branches hoặc xử lý thêm scans. Explain sau cursor phải được kiểm, không chỉ page đầu.

### 28.4. Projection chỉ fields cần

List endpoint không cần toàn bộ rooms array ở mỗi item. Chỉ lấy id/title/rent/city/status/createdAt; detail endpoint mới trả rooms. Điều này giảm network, client memory và khả năng lộ dữ liệu không cần thiết.

### 28.5. API quota

Giới hạn:

- Page size.
- Query time range nếu có.
- Sort fields được cho phép.
- Max concurrent exports.
- Rate/tenant quota.
- Cursor TTL.
- Request timeout/maxTimeMS.

Không để client tự chọn mọi sort field và bắt backend tạo index cho mỗi yêu cầu.

## 29. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Update thành công nhưng sai tenant | Filter chỉ có _id | Thêm tenantId từ principal |
| matchedCount=0 | ID sai, tenant sai, status/revision conflict | Phân loại, trả 404/409 đúng policy |
| replaceOne làm mất rooms | Replacement không đủ fields | Dùng targeted $set |
| $set tên field sai | Typo tạo field mới | Schema validation/typed mapping |
| $push tạo tag duplicate | $push không kiểm uniqueness | $addToSet nếu set semantics |
| $addToSet embedded doc vẫn duplicate roomId | So full document, không unique theo roomId | Domain invariant riêng |
| $pull xóa nhiều hơn mong muốn | Nhiều array elements cùng match | Validate identifiers và filter |
| rooms.$ cập nhật sai | Query array match mơ hồ | $elemMatch hoặc $[r] + arrayFilters |
| rooms.$[] sửa mọi room | Dùng all-positional thay vì filtered | $[r] |
| Array filter không match | Sai field path/type | Kiểm BSON/raw document |
| Hai updates đè nhau | Read-modify-save không revision guard | CAS, targeted updates |
| revision vẫn không bảo vệ | Writer khác không tăng version | Quy ước cho mọi write paths |
| DRAFT publish hai lần | Không có status predicate | Atomic state transition filter |
| Soft-delete vẫn được read | Thiếu deletedAt filter | Centralize active query |
| Pagination trùng trang | Skip offset trôi khi insert | Keyset |
| Pagination bỏ item cùng timestamp | Chỉ lưu createdAt | Tie-breaker _id |
| Pagination bỏ item ở ranh giới | Cursor lấy row thứ pageSize+1 | Dùng last returned row |
| Trang cuối báo hasNext sai | Chỉ dựa items.length==pageSize | Fetch pageSize+1 |
| Token tenant khác vẫn hợp lệ | Không bind cursor/auth filter | Verify signed token/context |
| Dữ liệu live thay đổi giữa pages | Keyset không phải snapshot | Ghi contract, dùng snapshot khi cần |
| Cursor so ID string với ObjectId | BSON types khác | Chuẩn hóa type |
| Sort theo updatedAt gây lặp | Mutable sort key | Dùng immutable key hoặc accept live semantics |
| Query chậm ở trang sâu | Skip lớn/index không phù hợp | Keyset + compound index |
| count quá tốn | Đếm mỗi page | Cân nhắc bỏ totalCount |
| Client OOM | Load toàn cursor | Bound result, page size |
| Không phát hiện unique index sai | Chỉ mock repository | Integration test MongoDB thật |

## 30. Runbook triển khai và kiểm tra API thực tế

### Phase A — Chuẩn bị hợp đồng

1. Định nghĩa collection schema và required fields.
2. Xác định tenant authorization boundary.
3. Chọn _id BSON type, createdAt bất biến, revision contract.
4. Quy định roomId uniqueness và array length limits.
5. Chọn status workflow và soft-delete rules.
6. Định nghĩa sort tuple và cursor token.

### Phase B — Data access

1. Viết CRUD với tenant filters.
2. Dùng targeted updates thay vì replace trừ khi business cần.
3. Viết array operations đúng scope.
4. Xử lý matchedCount/modifiedCount/conflicts.
5. Thiết lập migration/validation/index deployment có kiểm soát.

### Phase C — Index và hiệu năng

1. Phân tích query patterns.
2. Tạo index phù hợp.
3. Explain page đầu và page sau.
4. Đo p50/p95/p99 latency.
5. Giới hạn page size và query windows.
6. Tối ưu projection và count.

### Phase D — Kiểm thử

1. Unit test validation/state transition/cursor integrity.
2. Integration test BSON CRUD/arrayFilters/revision/index.
3. E2E test tenant isolation/API responses.
4. Pagination test duplicate timestamps.
5. Test insert/delete/status changes giữa pages.
6. Test concurrency, idempotency và timeout.

### Phase E — Release

1. Canary deployment.
2. Quan sát duplicate-key/409/404 rates.
3. Theo dõi pagination latency và keysExamined.
4. Theo dõi array update errors và unexpected bulk effects.
5. Có rollback plan cho code/index/schema changes.

## 31. Bài tập thực hành

### Bài 1 — Schema

Thiết kế một Listing có _id, tenantId, status, createdAt, updatedAt, revision, tags và rooms. Giải thích vì sao roomId không phải root _id.

### Bài 2 — Seed

Chạy seed 24 documents. Xác nhận có ba tenants, mỗi tenant tám listings, sáu PUBLISHED và hai DRAFT.

### Bài 3 — Timestamp trùng

Dùng aggregation group theo createdAt để chứng minh hai documents có chung thời gian tạo. Vì sao sort theo createdAt đơn lẻ không đủ?

### Bài 4 — Create

Tạo l458-created-001 và chạy insertOne lần hai. MongDB phản hồi thế nào? Vì sao không nên coi duplicate-key là thành công vô điều kiện?

### Bài 5 — Read

Viết findOne theo _id, tenantId và active condition. Truy vấn cùng _id nhưng tenantId khác phải trả gì?

### Bài 6 — Projection

Lấy 10 published listings nhưng chỉ trả _id/title/createdAt. Vì sao list API không nhất thiết tải rooms?

### Bài 7 — Count

So countDocuments có filter với estimatedDocumentCount; khi nào cần totalCount?

### Bài 8 — Set

Cập nhật title có revision tăng, updatedAt đổi. Kiểm matchedCount/modifiedCount.

### Bài 9 — Unset

Xóa optionalNote. Phân biệt missing field và field:null.

### Bài 10 — Replace

Giải thích vì sao replaceOne chỉ có title và _id có thể xóa rooms/tags của document đang tồn tại.

### Bài 11 — Multi-update

Viết updateMany cho DRAFT tenant-001; phân tích rủi ro nếu quên tenantId.

### Bài 12 — CAS

Với revision=1, update thành revision=2. Gọi lại với filter revision=1 sẽ có matchedCount bằng bao nhiêu? Cần trả lỗi API thế nào?

### Bài 13 — Concurrent writes

Hai request cùng đọc revision=2 và cùng sửa title. Thiết kế luồng để không âm thầm ghi đè thay đổi mới.

### Bài 14 — State transition

Viết updateOne chỉ chuyển DRAFT → PUBLISHED. Vì sao filter status phải đi cùng update?

### Bài 15 — $push

Thêm tag "BALCONY" hai lần bằng $push. Kết quả array thế nào?

### Bài 16 — $addToSet

Thêm "BALCONY" hai lần bằng $addToSet. Nó có tự xóa duplicate cũ không?

### Bài 17 — $pull

Xóa tag "BALCONY" khỏi tin. Nếu có ba phần tử trùng giá trị, chuyện gì xảy ra?

### Bài 18 — $elemMatch

Một listing có bedroom 18 m² và kitchen 25 m². Giải thích sự khác nhau giữa dotted predicates và $elemMatch khi tìm bedroom >=20 m².

### Bài 19 — Positional $

Viết update cập nhật available của roomId bed-1 bằng rooms.$. Vì sao filter phải match phần tử array?

### Bài 20 — Filtered positional

Dùng rooms.$[r].areaSqm cùng arrayFilters để đặt diện tích room bed-1 bằng 24.

### Bài 21 — Nhiều điều kiện cùng room

Dùng arrayFilters tìm BEDROOM có areaSqm >=18 và cập nhật available.

### Bài 22 — $[]

Viết update đặt available=false cho mọi rooms của một listing. Vì sao không dùng $[] khi chỉ muốn sửa bed-1?

### Bài 23 — Nested amenities

Thêm ELEVATOR vào amenities của room bed-1 bằng $addToSet và arrayFilters; tránh thêm lại WIFI.

### Bài 24 — $pull room

Xóa kitchen-1 khỏi rooms. Những invariants nghiệp vụ nào cần kiểm trước?

### Bài 25 — Array uniqueness

Vì sao $addToSet embedded document và unique multikey index không tự bảo đảm roomId unique trong cùng listing?

### Bài 26 — FindOneAndUpdate

Dùng returnDocument:"after" để nhận title/revision sau update. Khi filter không match thì sao?

### Bài 27 — Soft delete

Lưu deletedAt và status ARCHIVED. Vì sao filter active cần có ở cả detail API và list API?

### Bài 28 — Hard delete

deleteOne theo _id + tenantId + labTag. Phân biệt deletedCount=0 với document không thuộc quyền.

### Bài 29 — Bulk

Viết bulkWrite hai updateOne khác nhau. Giải thích ordered:false không tạo transaction.

### Bài 30 — Offset pagination

Vẽ một trang offset trước/sau insert mới ở đầu danh sách và giải thích nguyên nhân bản ghi bị lặp.

### Bài 31 — Keyset tuple

Sort createdAt DESC, _id DESC. Viết predicate cho phần tử đứng sau (lastAt,lastId).

### Bài 32 — Tie-breaker

Với hai documents cùng createdAt, chứng minh chỉ query createdAt<lastAt có thể bỏ sót document.

### Bài 33 — pageSize+1

Giả sử pageSize=3, query lấy bốn documents. Items trả ra bao nhiêu? nextAfter phải dùng document thứ mấy?

### Bài 34 — Trang cuối

Khi query lấy đúng pageSize documents nhưng không có phần tử thứ pageSize+1, hasNext là gì?

### Bài 35 — Lab phân trang

Chạy getPage458 pageSize=2 cho tenant-001. Thu tất cả sáu published IDs, chứng minh không trùng IDs và thứ tự giảm dần.

### Bài 36 — Index

Thiết kế index cho tenantId + status equality và sort createdAt DESC, _id DESC. Kiểm explain trên trang đầu và trang sau.

### Bài 37 — Cursor filter

Một cursor được tạo với tenant-001/status=PUBLISHED nhưng client dùng với tenant-002/status=DRAFT. Backend phải làm gì?

### Bài 38 — Cursor HMAC

Phác thảo payload versioned, MAC verification, expiry, tenant-binding, filterHash và giới hạn page size. Vì sao Base64 đơn lẻ không bảo vệ integrity?

### Bài 39 — Live data

Giữa trang 1 và 2, một tin mới xuất hiện với createdAt mới hơn cursor. Keyset xử lý thế nào? Nếu một DRAFT cũ được publish sau cursor thì sao?

### Bài 40 — Snapshot

Vì sao keyset không cam kết snapshot? Khi nào cần snapshot-consistent export hoặc job tạo tập kết quả cố định?

### Bài 41 — Mutable sort key

Nếu API sort updatedAt DESC và user cập nhật một document đang nằm ở trang sau, nguy cơ duplicate/missing là gì?

### Bài 42 — ID BSON type

Nếu chuyển _id từ String sang ObjectId, cần sửa cursor serialization/comparison và query filters như thế nào?

### Bài 43 — Tích hợp Spring Data

Viết entity có @Document, @Id, @Version và rooms. Thiết kế MongoTemplate arrayFilters update an toàn với tenant predicate.

### Bài 44 — Tenant security

Một user biết _id của tenant khác. Vì sao _id unique và cursor HMAC vẫn không thay được authorization trong MongoDB query?

### Bài 45 — Tổng hợp

Thiết kế API CRUD cho hàng triệu listings, nhiều tenant, có rooms và tags; bắt buộc audit, optimistic locking, soft delete, stable keyset pagination, HMAC cursor, index, integration tests và release runbook. Giải thích từng invariant và giới hạn snapshot.

## 32. Tài liệu tham khảo

- MongoDB Manual — [CRUD Operations](https://www.mongodb.com/docs/manual/crud/).
- MongoDB Manual — [Insert Documents](https://www.mongodb.com/docs/manual/tutorial/insert-documents/).
- MongoDB Manual — [Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/).
- MongoDB Manual — [Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/).
- MongoDB Manual — [Delete Documents](https://www.mongodb.com/docs/manual/tutorial/remove-documents/).
- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
- MongoDB Manual — [$set](https://www.mongodb.com/docs/manual/reference/operator/update/set/).
- MongoDB Manual — [$inc](https://www.mongodb.com/docs/manual/reference/operator/update/inc/).
- MongoDB Manual — [$push](https://www.mongodb.com/docs/manual/reference/operator/update/push/).
- MongoDB Manual — [$addToSet](https://www.mongodb.com/docs/manual/reference/operator/update/addToSet/).
- MongoDB Manual — [$pull](https://www.mongodb.com/docs/manual/reference/operator/update/pull/).
- MongoDB Manual — [Positional $ Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional/).
- MongoDB Manual — [All Positional $[] Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional-all/).
- MongoDB Manual — [Filtered Positional $[identifier] Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/).
- MongoDB Manual — [$elemMatch](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/).
- MongoDB Manual — [Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/).
- MongoDB Manual — [Sort and Index Use](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/).
- MongoDB Java Sync Driver — [CRUD](https://www.mongodb.com/docs/drivers/java/sync/current/crud/).
- Spring Data MongoDB — [Template CRUD](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html).
- Spring Data MongoDB — [Querying](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html).

**Kết luận:** Một bài CRUD MongoDB được xem là hoàn thiện không chỉ vì insert/find/update/delete chạy đúng với một document mẫu. Cần bảo vệ **tenant authorization, schema/BSON types, atomic update, optimistic concurrency, trạng thái xóa và các phần tử trong mảng**. Với **rooms**, $elemMatch đảm bảo các điều kiện trên cùng phần tử; positional **$**, **$[]** và **$[identifier] + arrayFilters** có phạm vi cập nhật khác nhau, nên phải chọn theo business intent và kiểm tra kết quả thực. Với danh sách lớn, phân trang theo **createdAt DESC + _id DESC**, điều kiện tuple keyset và **pageSize+1** giúp giữ thứ tự xác định và tránh vấn đề offset dịch khi chèn ở đầu; nhưng **keyset không tự đóng băng snapshot khi dữ liệu thay đổi**. Thiết kế production cần **compound index đúng query, cursor có kiểm chứng integrity/tenant/filter, page limits, telemetry, integration tests và rollback plan** để CRUD, cập nhật mảng và phân trang cùng đúng trong điều kiện có tải và cạnh tranh.
