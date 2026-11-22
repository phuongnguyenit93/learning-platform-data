# Phân chia kiểm tra dữ liệu giữa MongoDB và ứng dụng

## 1. Vì sao cần kiểm tra dữ liệu ở nhiều lớp?

Một ứng dụng dùng MongoDB thường nhận dữ liệu từ trình duyệt, ứng dụng di động, API, tác vụ nền, chương trình nhập dữ liệu và các dịch vụ khác. Nếu mỗi nguồn gửi dữ liệu với giả định khác nhau, collection có thể xuất hiện các document không nhất quán:

```javascript
// Cùng biểu diễn một lần đăng ký khóa học nhưng không thống nhất kiểu.
{ studentId: ObjectId("66a000000000000000000001"), status: "ACTIVE" }
{ studentId: "66a000000000000000000001", status: "active" }
{ studentId: null, status: "ACTVE" }
{ studentId: ObjectId("66a000000000000000000001"), status: 1 }
```

Mỗi document BSON có cấu trúc cụ thể, nhưng MongoDB mặc định cho phép document trong một collection có các trường và kiểu khác nhau. Sự linh hoạt này hữu ích khi mô hình tiến hóa; tuy nhiên, một ứng dụng có quy tắc nghiệp vụ ổn định vẫn cần bảo đảm các trường quan trọng đúng kiểu, có mặt khi bắt buộc và giữ các ràng buộc dữ liệu.

Ví dụ, tính năng **đăng ký khóa học** có các yêu cầu khác nhau:

- `studentId` và `courseId` phải là `ObjectId` hợp lệ.
- `status` chỉ nhận một số giá trị như `PENDING`, `ACTIVE`, `CANCELLED`.
- Một học viên không được có hai bản ghi đăng ký cho cùng một khóa học theo quy tắc của hệ thống.
- Chỉ học viên đã đăng nhập mới được đăng ký cho chính mình.
- Chỉ được đăng ký khi khóa học còn mở và còn chỗ.
- Sau khi hủy, không được tùy ý chuyển trạng thái về `ACTIVE` nếu quy trình yêu cầu đăng ký lại.

Các yêu cầu trên thuộc **những loại kiểm tra khác nhau**, vì thế không nên dồn hết vào một hàm ở API hoặc kỳ vọng `$jsonSchema` trong MongoDB tự giải quyết toàn bộ.

Bài học phân chia trách nhiệm giữa **MongoDB schema validation**, **index**, **lệnh ghi có điều kiện**, **transaction**, và **kiểm tra tại tầng ứng dụng**. Mục tiêu là vừa chặn dữ liệu hỏng ở lớp lưu trữ, vừa xử lý đúng nghiệp vụ, trả lỗi rõ cho người dùng và giữ tính nhất quán khi có nhiều yêu cầu đồng thời.

## 2. Các lớp kiểm tra trong hệ thống

Một luồng ghi dữ liệu phổ biến:

```text
Trình duyệt / ứng dụng di động / API client
             |
             v
  [1] Kiểm tra trải nghiệm đầu vào (UI)
             |
             v
  [2] API / tầng ứng dụng
      - parse và chuẩn hóa
      - xác thực, phân quyền
      - quy tắc nghiệp vụ
      - kiểm tra trạng thái & tham chiếu
             |
             v
  [3] Lệnh ghi MongoDB
      - filter có điều kiện / atomic update
      - transaction nếu thay đổi nhiều document
             |
             v
  [4] MongoDB
      - document validation / $jsonSchema
      - unique index và các chỉ mục
      - atomicity, ghi dữ liệu
             |
             v
  Document được chấp nhận hoặc MongoDB trả lỗi
```

Mỗi lớp có mục tiêu riêng:

| Lớp | Nên chịu trách nhiệm chính | Không đủ để bảo đảm |
| --- | --- | --- |
| **Client/UI** | Gợi ý nhập liệu, báo lỗi nhanh, kiểm tra định dạng trước khi gửi | Tính toàn vẹn dữ liệu: client có thể bị sửa, bỏ qua hoặc giả mạo |
| **API/tầng ứng dụng** | Parse input, chuẩn hóa, xác thực/phân quyền, quy tắc nghiệp vụ theo ngữ cảnh, thông báo lỗi | Một mình chống được mọi dữ liệu sai khi có script, worker hay dịch vụ khác ghi trực tiếp |
| **MongoDB schema validation** | Hình dạng document, kiểu BSON, trường bắt buộc, giá trị thuộc tập cho phép, giới hạn một field | Quyền truy cập, sự tồn tại của document ở collection khác và mọi quy trình nghiệp vụ |
| **Unique index** | Tính duy nhất của một khóa hoặc tổ hợp khóa khi nhiều request ghi đồng thời | Sự tồn tại của khóa tham chiếu hoặc tính hợp lệ của chuyển trạng thái |
| **Lệnh cập nhật có điều kiện** | Chỉ thay đổi khi document vẫn đang ở trạng thái mong đợi; một thao tác ghi trên một document là nguyên tử | Tự động bảo đảm nhiều document cùng thay đổi |
| **Transaction đa document** | Giữ một nhóm thay đổi trên nhiều document/collection cùng thành công hoặc cùng hủy | Tự hiểu quy tắc nghiệp vụ; ứng dụng vẫn phải xây dựng điều kiện đúng |

**Nguyên tắc thiết kế:** dùng nhiều lớp cho những ràng buộc quan trọng, nhưng có **một định nghĩa nhất quán** về ý nghĩa dữ liệu. Ví dụ API và MongoDB cùng hiểu `status` là `PENDING`, `ACTIVE` hoặc `CANCELLED`; không để mỗi nơi đặt bộ giá trị riêng.

## 3. Phân loại quy tắc theo bản chất

Trước khi chọn công cụ, hãy hỏi “quy tắc này kiểm tra được bằng một document hay phải biết ngữ cảnh bên ngoài?”.

| Quy tắc | Vị trí phù hợp | Lý do |
| --- | --- | --- |
| `studentId` bắt buộc, có kiểu BSON ObjectId | MongoDB `$jsonSchema`; ứng dụng cũng parse input | Cấu trúc dữ liệu bất biến với mọi nguồn ghi |
| `score` phải là số nguyên từ 0 đến 100 | MongoDB `$jsonSchema`; ứng dụng báo lỗi dễ hiểu | Giới hạn ngay trên một field |
| `status` thuộc một tập giá trị cố định | MongoDB `enum`; ứng dụng dùng cùng quy ước | Chặn giá trị không hợp lệ ở mọi đường ghi |
| Email cần trim, chuẩn hóa theo chính sách ứng dụng | Ứng dụng; MongoDB bảo vệ kiểu/độ dài | Chuẩn hóa phụ thuộc chính sách và cách xử lý input |
| Một học viên chỉ đăng ký một lần cho cùng một khóa học | Unique index ghép | Chặn trùng ngay cả khi hai yêu cầu đến đồng thời |
| Người đăng nhập chỉ được ghi đăng ký của chính mình | Ứng dụng/server authentication & authorization | Phụ thuộc danh tính của request |
| Khóa học phải tồn tại và còn nhận đăng ký | Ứng dụng kiểm tra; dùng ghi có điều kiện/transaction khi có cạnh tranh | Cần đọc dữ liệu ở collection khác và bảo vệ tính nhất quán |
| Trạng thái chỉ được chuyển `PENDING → ACTIVE` sau thanh toán | Ứng dụng + cập nhật có điều kiện | Phụ thuộc trạng thái cũ và kết quả một quy trình |
| Đăng ký phải kèm giảm số ghế còn lại | Transaction đa document hoặc thiết kế lại ranh giới document | Có nhiều thay đổi cần nguyên tử với nhau |
| Hiển thị “Bạn đã đăng ký khóa học này” bằng tiếng Việt | Ứng dụng/API | MongoDB trả lỗi kỹ thuật; thông điệp dành cho người dùng thuộc ứng dụng |

Có một số quy tắc có thể biểu diễn ở hơn một nơi. Chẳng hạn giới hạn tuổi có thể được kiểm tra ở API để trả thông báo và trong schema để chặn lỗi của một script nhập dữ liệu. Việc kiểm tra lặp lại ở hai lớp như vậy là **bảo vệ theo nhiều tầng**, miễn là quy tắc và giới hạn được thống nhất.

## 4. Tình huống thực hành: collection đăng ký khóa học

Ta thiết kế collection `enrollments_demo` với document mẫu:

```javascript
{
  _id: ObjectId("66a000000000000000000010"),
  studentId: ObjectId("66a000000000000000000001"),
  courseId: ObjectId("66a000000000000000000002"),
  status: "PENDING",
  enrolledAt: ISODate("2026-11-14T01:30:00Z"),
  schemaVersion: NumberInt(1),
  score: NumberInt(80),
  runId: "row87-demo-001"
}
```

Ý nghĩa các trường:

- `studentId`: khóa tham chiếu đến document học viên.
- `courseId`: khóa tham chiếu đến document khóa học.
- `status`: trạng thái thuộc tập giá trị do nghiệp vụ quy định.
- `enrolledAt`: thời điểm đăng ký, lưu bằng BSON Date.
- `schemaVersion`: phiên bản cấu trúc được ứng dụng hiểu.
- `score`: trường tùy chọn, số nguyên 0–100.
- `runId`: dấu nhận diện lượt thực hành, chỉ phục vụ việc kiểm thử và dọn dữ liệu có kiểm soát.

Trong demo, mỗi cặp `studentId` + `courseId` chỉ có tối đa một bản ghi. Đây là giả định nghiệp vụ để minh họa unique index. Nếu một học viên được học lại cùng khóa nhiều đợt, mô hình thực tế phải bổ sung `offeringId`/`termId` hoặc thiết kế quy tắc duy nhất khác.

Các ví dụ `mongosh` dưới đây chỉ thao tác với database **`mongo_validation_lab`** và collection thử nghiệm do người học sở hữu. Trên môi trường chung, không tự tạo/chỉnh sửa collection thật khi chưa có quyền quản lý schema.

## 5. MongoDB bảo vệ cấu trúc bằng `$jsonSchema`

### 5.1. Tạo collection có validator

Chạy trong `mongosh` với một database thử nghiệm chưa có collection cùng tên:

```javascript
const lab = db.getSiblingDB("mongo_validation_lab");

lab.createCollection("enrollments_demo", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "studentId",
        "courseId",
        "status",
        "enrolledAt",
        "schemaVersion"
      ],
      additionalProperties: false,
      properties: {
        _id: {
          bsonType: "objectId",
          description: "Định danh document"
        },
        studentId: {
          bsonType: "objectId",
          description: "Học viên phải có ObjectId"
        },
        courseId: {
          bsonType: "objectId",
          description: "Khóa học phải có ObjectId"
        },
        status: {
          enum: ["PENDING", "ACTIVE", "CANCELLED"],
          description: "Trạng thái đăng ký hợp lệ"
        },
        enrolledAt: {
          bsonType: "date",
          description: "Thời điểm đăng ký phải là BSON Date"
        },
        updatedAt: {
          bsonType: "date"
        },
        schemaVersion: {
          bsonType: "int",
          minimum: 1
        },
        score: {
          bsonType: "int",
          minimum: 0,
          maximum: 100
        },
        runId: {
          bsonType: "string",
          minLength: 1
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Điểm quan trọng trong validator này:

1. `bsonType: "object"` yêu cầu document là BSON object.
2. `required` xác định **các field bắt buộc phải có**. Một field được liệt kê trong `properties` chưa tự trở thành bắt buộc.
3. `bsonType: "objectId"`, `"date"`, `"int"` phân biệt kiểu BSON, không chỉ hình dạng JSON khi hiển thị.
4. `enum` giới hạn các giá trị cho phép của `status`.
5. `minimum`, `maximum` giới hạn số điểm; `minLength` bảo đảm chuỗi `runId` nếu có không rỗng.
6. `additionalProperties: false` không cho phép thêm field ngoài danh sách `properties`. Vì MongoDB tự thêm `_id` khi cần, phải liệt kê `_id` trong `properties`. Khi bổ sung trường mới, cần mở rộng validator có kế hoạch.
7. `validationLevel: "strict"` kiểm tra mọi lần chèn và cập nhật document theo validator; `validationAction: "error"` từ chối thao tác không hợp lệ, trừ các trường hợp được phép chủ động bỏ qua document validation.

Validator trên là **hợp đồng cấu trúc**. Nó chưa biết `studentId` có thật trong collection `students`, chưa kiểm tra còn chỗ học, và chưa biết ai đang gửi request.

### 5.2. Vì sao kiểu BSON cần được thống nhất?

Trong `mongosh`:

```javascript
NumberInt(80);                     // BSON Int32
NumberLong("80");                 // BSON Int64
ISODate("2026-11-14T01:30:00Z");  // BSON Date
ObjectId();                       // BSON ObjectId
```

Một giá trị nhìn giống “80” có thể được tạo theo kiểu BSON khác nhau tùy driver và cách serialize. Với schema `score: { bsonType: "int" }`, cần bảo đảm ứng dụng thực sự ghi một BSON Int32. Ví dụ `NumberInt(80)` trong `mongosh` phù hợp; trong Node.js có thể dùng `Int32` từ thư viện `mongodb` khi muốn chỉ rõ kiểu.

Nếu dữ liệu cũ dùng `long` hoặc một kiểu số BSON khác, cần cân nhắc quy tắc schema chấp nhận nhiều loại số hoặc chuyển đổi dữ liệu trước khi áp validator. Không nên tùy tiện nới rộng kiểu chỉ để tránh lỗi mà chưa hiểu miền giá trị.

### 5.3. Ghi một document hợp lệ

```javascript
const enrollments = lab.getCollection("enrollments_demo");
const studentId = new ObjectId();
const courseId = new ObjectId();
const runId = "row87-" + new ObjectId().toHexString();

const inserted = enrollments.insertOne({
  studentId: studentId,
  courseId: courseId,
  status: "PENDING",
  enrolledAt: new Date(),
  schemaVersion: NumberInt(1),
  score: NumberInt(80),
  runId: runId
});

printjson(inserted);
printjson(
  enrollments.findOne({ _id: inserted.insertedId, runId: runId })
);
```

Nếu lệnh thành công, `insertOne` trả về thông tin như `acknowledged` và `insertedId`. Trong ví dụ này `studentId`, `courseId` là ID giả lập; bài học chỉ đang chứng minh **tính hợp lệ của hình dạng document**. Việc hai ID đó phải tương ứng với học viên và khóa học có thật vẫn là trách nhiệm của nghiệp vụ.

### 5.4. Những dữ liệu bị từ chối

Giả sử các thao tác sau được chạy riêng sau khi tạo collection có validator:

```javascript
// Sai: status không nằm trong enum.
enrollments.insertOne({
  studentId: new ObjectId(),
  courseId: new ObjectId(),
  status: "WAITING_FOR_MAGIC",
  enrolledAt: new Date(),
  schemaVersion: NumberInt(1)
});

// Sai: enrolledAt là string thay vì BSON Date.
enrollments.insertOne({
  studentId: new ObjectId(),
  courseId: new ObjectId(),
  status: "PENDING",
  enrolledAt: "2026-11-14T01:30:00Z",
  schemaVersion: NumberInt(1)
});

// Sai: thiếu courseId (required).
enrollments.insertOne({
  studentId: new ObjectId(),
  status: "PENDING",
  enrolledAt: new Date(),
  schemaVersion: NumberInt(1)
});
```

Mỗi lệnh dự kiến bị từ chối do không đạt validator; trong MongoDB lỗi document validation thường có **mã `121`** và tên lỗi như `DocumentValidationFailure`. Chi tiết cấu trúc lỗi phụ thuộc phiên bản server và driver. Ví dụ chỉ để quan sát hành vi trong môi trường thử nghiệm; không cần thực hiện liên tiếp khi đã thấy nguyên tắc.

**Chú ý:** `required` và `bsonType` là hai kiểm tra độc lập. Một field có mặt với `null` chưa chắc hợp lệ nếu schema yêu cầu kiểu khác, ví dụ `bsonType: "objectId"`. Nếu cho phép `null`, phải biểu đạt điều đó có chủ đích trong schema.

### 5.5. Validator cũng áp dụng cho cập nhật

```javascript
// Hợp lệ: đổi điểm sang một số nguyên trong khoảng.
enrollments.updateOne(
  { _id: inserted.insertedId, runId: runId },
  { $set: { score: NumberInt(95), updatedAt: new Date() } }
);

// Không hợp lệ: điểm vượt quá maximum.
enrollments.updateOne(
  { _id: inserted.insertedId, runId: runId },
  { $set: { score: NumberInt(150) } }
);

// Không hợp lệ: xóa trường bắt buộc.
enrollments.updateOne(
  { _id: inserted.insertedId, runId: runId },
  { $unset: { courseId: "" } }
);
```

Với chế độ `strict` và `error`, MongoDB đánh giá **trạng thái document sau cập nhật**. Nếu document kết quả vi phạm validator, thao tác sẽ bị từ chối. Đây là lợi thế của validation ở database: không phụ thuộc vào việc code API đã gọi đúng hàm validate hay chưa.

## 6. Ứng dụng phải làm gì trước khi gửi lệnh ghi?

### 6.1. Parse và chuẩn hóa input không đáng tin

Client có thể gửi:

```json
{
  "courseId": "66a000000000000000000002",
  "status": "ACTIVE",
  "score": 100,
  "studentId": "66a000000000000000000099"
}
```

Ngay cả khi `courseId` có dạng hợp lệ, client **không nên tự quyết định** `studentId` của tài khoản đăng nhập, `status`, `score` hoặc `enrolledAt`. Các trường này cần được thiết lập bởi server theo quyền và luồng nghiệp vụ.

Một API đăng ký khóa học có thể chỉ chấp nhận:

```json
{
  "courseId": "66a000000000000000000002"
}
```

Tầng ứng dụng thực hiện:

1. Xác thực user từ session/token đã được xác minh.
2. Lấy `studentId` của người dùng từ ngữ cảnh server đáng tin.
3. Kiểm tra `courseId` là chuỗi ObjectId đúng dạng; đổi thành BSON ObjectId.
4. Kiểm tra quyền tham gia khóa học, trạng thái mở đăng ký và các điều kiện nghiệp vụ.
5. Đặt `status` ban đầu, thời điểm đăng ký và version ở server.
6. Gửi document đã chuẩn hóa vào MongoDB.

### 6.2. Ví dụ Node.js: kiểm tra input và dựng document

Ví dụ sau sử dụng MongoDB Node.js driver. Nó là hàm dịch vụ mẫu được gọi bởi route/controller đã xác thực; `authContext` phải đến từ middleware xác thực, **không lấy trực tiếp từ body client**.

```javascript
import { ObjectId, Int32 } from "mongodb";

function parseObjectIdFromRequest(value, fieldName) {
  if (
    typeof value !== "string" ||
    !/^[0-9a-fA-F]{24}$/.test(value)
  ) {
    throw new Error(fieldName + " phải là ObjectId dạng 24 ký tự hex");
  }
  return new ObjectId(value);
}

function buildEnrollmentDocument(body, authContext) {
  if (
    body === null ||
    typeof body !== "object" ||
    Array.isArray(body)
  ) {
    throw new Error("Body phải là một object");
  }

  // Chỉ cho phép trường đầu vào mà API đã công bố.
  const allowedKeys = new Set(["courseId"]);
  for (const key of Object.keys(body)) {
    if (!allowedKeys.has(key)) {
      throw new Error("Trường không được phép: " + key);
    }
  }

  const courseId = parseObjectIdFromRequest(body.courseId, "courseId");

  // studentId đã được middleware xác thực gắn vào context.
  const studentId = authContext?.studentId;
  if (!(studentId instanceof ObjectId)) {
    throw new Error("Thiếu danh tính học viên đã xác thực");
  }

  return {
    studentId,
    courseId,
    status: "PENDING",
    enrolledAt: new Date(),
    schemaVersion: new Int32(1)
  };
}

// Gọi trong service/controller đã có db và authContext.
async function createEnrollment(db, body, authContext) {
  const candidate = buildEnrollmentDocument(body, authContext);

  // Các điều kiện như khóa học có tồn tại, được phép đăng ký,
  // còn chỗ... cần được xử lý ở luồng nghiệp vụ phù hợp.
  const result = await db
    .collection("enrollments_demo")
    .insertOne(candidate);

  return result.insertedId;
}
```

Ở ví dụ trên, `Int32(1)` thể hiện chủ đích khớp với schema `bsonType: "int"`. Dữ liệu đầu vào được chuyển thành kiểu cần lưu, thay vì ghi nguyên bản JSON client vào MongoDB. Hàm `createEnrollment` chỉ minh họa phần dựng document và lệnh chèn; nếu nghiệp vụ cần bảo đảm sức chứa khóa học và tránh tranh chấp, phải bổ sung cơ chế ở mục 8.

Một ứng dụng thật thường dùng thư viện kiểm tra input như JSON Schema validator, Zod, Joi hoặc hệ thống validation tích hợp framework. Dù dùng thư viện nào, điều quan trọng là **không mặc nhiên tin body từ client**, định nghĩa rõ contract và phân biệt lỗi do người dùng nhập với lỗi hệ thống.

### 6.3. Kiểm tra độ hợp lệ có ý nghĩa nghiệp vụ

MongoDB có thể biết `status` nằm trong tập giá trị hợp lệ, nhưng không tự biết:

- Học viên có bị khóa tài khoản không?
- Khóa học có ở trạng thái nhận đăng ký không?
- Học viên có hoàn thành môn tiên quyết không?
- Học viên đã thanh toán hoặc được cấp quyền chưa?
- Hạn đăng ký của khóa học tính theo múi giờ nào?
- Một tác vụ tự động có quyền đổi `status` từ `PENDING` sang `ACTIVE` không?

Các quyết định này dựa trên **ngữ cảnh và chính sách**, vì thế thuộc tầng nghiệp vụ. Ngay cả khi có thể viết một phần logic vào biểu thức validator, không nên làm cơ sở dữ liệu phụ thuộc vào danh tính người dùng hoặc cuộc gọi dịch vụ ngoài.

### 6.4. Đưa dữ liệu về dạng chuẩn trước khi ghi

Ví dụ hệ thống tài khoản nhận email:

```javascript
function normalizeEmailForThisApp(input) {
  if (typeof input !== "string") {
    throw new Error("Email phải là chuỗi");
  }

  const result = input.trim().toLowerCase();
  if (!result || result.length > 254) {
    throw new Error("Email không hợp lệ theo chính sách ứng dụng");
  }
  return result;
}
```

Đây chỉ là minh họa một **chính sách chuẩn hóa đơn giản**, chưa phải bộ kiểm tra email đầy đủ theo mọi chuẩn và trường hợp quốc tế. Quy tắc lower-case toàn bộ địa chỉ cần được quyết định nhất quán theo sản phẩm. Sau khi chuẩn hóa, database có thể kiểm tra field là chuỗi, độ dài trong giới hạn và unique index trên giá trị chuẩn hóa nếu nghiệp vụ yêu cầu.

**Tách hai khái niệm:** chuẩn hóa biến input thành dạng biểu diễn nhất quán; validation quyết định dữ liệu có được chấp nhận hay không.

## 7. Những bảo đảm cần index hoặc điều kiện ghi, không chỉ `$jsonSchema`

### 7.1. Tính duy nhất dùng unique index

Validator ở mục 5 kiểm tra từng document. Nó không tự ngăn hai document có cùng `studentId` và `courseId`. Để bảo vệ ràng buộc cặp duy nhất:

```javascript
lab.enrollments_demo.createIndex(
  { studentId: 1, courseId: 1 },
  { unique: true, name: "uniq_student_course" }
);
```

Nếu hai request chèn cùng một cặp gần như đồng thời, unique index ở database sẽ chặn một thao tác bị trùng. Lỗi thường có mã **`11000`** (`DuplicateKey`). API nên chuyển lỗi thành thông điệp nghiệp vụ như “Học viên đã đăng ký khóa học này”, thay vì trả nguyên văn lỗi index và dữ liệu nội bộ.

Nếu index được tạo sau khi collection đã có dữ liệu trùng, thao tác tạo index có thể thất bại; cần xác định và xử lý trùng lặp trước khi áp dụng.

**Ví dụ giả định thay đổi quy tắc:** nếu một học viên có thể tham gia lại cùng khóa trong các đợt khác nhau, unique index trên cặp `studentId` + `courseId` sẽ quá chặt. Khi đó cần đặt đúng khóa nghiệp vụ (chẳng hạn thêm `offeringId`) trước khi đổi index.

### 7.2. Chuyển trạng thái cần điều kiện trên document hiện hành

Giả sử nghiệp vụ chỉ cho phép chuyển `PENDING` → `ACTIVE`. Cách dễ gây tranh chấp:

```javascript
// Ý tưởng thiếu an toàn khi chạy đồng thời:
// 1. Đọc document thấy status = PENDING.
// 2. Một request khác hủy đăng ký.
// 3. Request đầu vẫn update thành ACTIVE mà không kiểm tra lại.
```

Có thể bảo vệ bằng điều kiện ở chính lệnh ghi:

```javascript
const result = lab.enrollments_demo.updateOne(
  {
    _id: inserted.insertedId,
    status: "PENDING"
  },
  {
    $set: {
      status: "ACTIVE",
      updatedAt: new Date()
    }
  }
);

printjson(result);
```

Nếu `matchedCount` là `0`, không có document nào vừa khớp `_id` và trạng thái `PENDING`. Ứng dụng cần kiểm tra lý do (không tồn tại, đã hủy, đã active...) và trả phản hồi phù hợp. Một lệnh `updateOne` như vậy là **nguyên tử trong phạm vi một document**, giúp giảm nguy cơ cập nhật dựa trên trạng thái cũ.

MongoDB `enum` biết `ACTIVE` là một giá trị hợp lệ, nhưng không tự hiểu mọi bước chuyển giữa các trạng thái. Vì vậy **schema validation bảo vệ trạng thái đích**, còn **điều kiện ghi và tầng nghiệp vụ bảo vệ chuyển trạng thái**.

### 7.3. Tham chiếu sang collection khác

`studentId` và `courseId` là ObjectId hợp lệ chưa có nghĩa document tương ứng tồn tại. MongoDB không tự tạo foreign key giữa `enrollments_demo.courseId` và `courses._id`.

Tầng ứng dụng nên:

- Kiểm tra khóa học có tồn tại khi nhận đăng ký.
- Xác định quy tắc khi khóa học bị xóa/ẩn/khóa sau đó.
- Tránh tự động xóa lịch sử có giá trị nghiệp vụ.
- Khi cần tính nhất quán mạnh giữa nhiều document, thiết kế giao dịch hoặc cơ chế đồng bộ phù hợp.

Việc “đọc thấy course còn tồn tại” rồi mới insert cũng **chưa bảo đảm** course vẫn tồn tại trong lúc insert nếu có thao tác khác thay đổi đồng thời. Mức bảo đảm mong muốn sẽ quyết định có cần phối hợp transaction và chính sách xóa hay không.

## 8. Bảo vệ quy tắc liên quan nhiều document bằng transaction

Xét nghiệp vụ: đăng ký học viên vào một khóa học còn `seatsAvailable` ghế. Mỗi lần đăng ký mới phải:

1. Giảm `seatsAvailable` đúng một đơn vị với điều kiện còn ghế và đang mở đăng ký.
2. Tạo một enrollment mới, không được trùng học viên–khóa học.

Nếu giảm ghế xong rồi insert lỗi, hoặc insert xong mà giảm ghế thất bại, dữ liệu có thể mâu thuẫn. Khi đây là một điều kiện bất biến quan trọng, ứng dụng có thể dùng **transaction đa document** trên triển khai MongoDB hỗ trợ.

Ví dụ Node.js ở tầng dịch vụ, giả sử collection `courses` đã có `_id`, `registrationOpen`, `seatsAvailable` và unique index trên enrollment đã được tạo:

```javascript
import { Int32 } from "mongodb";

async function reserveSeatAndEnroll(client, db, studentId, courseId) {
  const session = client.startSession();

  try {
    return await session.withTransaction(async () => {
      const courses = db.collection("courses");
      const enrollments = db.collection("enrollments_demo");

      // Điều kiện và phép giảm được thực hiện nguyên tử trên course.
      const seatUpdate = await courses.updateOne(
        {
          _id: courseId,
          registrationOpen: true,
          seatsAvailable: { $gt: 0 }
        },
        { $inc: { seatsAvailable: -1 } },
        { session }
      );

      if (seatUpdate.matchedCount !== 1) {
        throw new Error("COURSE_NOT_AVAILABLE");
      }

      // Unique index chặn hai enrollment cùng student + course.
      const inserted = await enrollments.insertOne(
        {
          studentId,
          courseId,
          status: "PENDING",
          enrolledAt: new Date(),
          schemaVersion: new Int32(1)
        },
        { session }
      );

      return inserted.insertedId;
    });
  } finally {
    await session.endSession();
  }
}
```

Điểm cần hiểu:

- `$inc` với bộ lọc `seatsAvailable: { $gt: 0 }` bảo vệ việc giảm một document course khi có nhiều request cùng lúc.
- Unique index bảo vệ một cặp học viên–khóa học khỏi trùng.
- Transaction giúp hai thay đổi ở course và enrollment được commit cùng nhau hoặc rollback theo khả năng và ngữ nghĩa của transaction.
- Các điều kiện phân quyền, môn tiên quyết, giới hạn học viên, hạn đăng ký... vẫn phải được kiểm tra thêm theo nghiệp vụ.
- Callback transaction có thể được thực thi lại khi driver xử lý một số lỗi tạm thời; **không đặt thao tác gửi email/thanh toán bên ngoài** không thể hoàn tác trực tiếp trong callback mà không có thiết kế idempotency/outbox thích hợp.
- Transaction đòi hỏi cấu hình MongoDB phù hợp, chẳng hạn replica set hoặc sharded cluster; không nên mặc định một `mongod` standalone thử nghiệm hỗ trợ giống hệt.

Đây là ví dụ về việc **phân chia**: ứng dụng quyết định khi nào được đăng ký; update có điều kiện bảo vệ số ghế; unique index bảo vệ trùng; validator bảo vệ kiểu document; transaction bảo vệ nhóm thay đổi.

## 9. Kiểm tra khi cập nhật một phần (PATCH)

Các API chỉnh sửa thường không gửi lại toàn bộ document. Ví dụ request:

```json
{
  "status": "ACTIVE"
}
```

Ứng dụng cần kiểm tra **trường nào được phép thay đổi**, ai được sửa, trạng thái hiện tại và quy tắc chuyển trạng thái. Không nên làm:

```javascript
// Minh họa cách làm không an toàn:
// await collection.updateOne({ _id }, { $set: req.body });
```

Vì request có thể chứa `studentId`, `courseId`, `score` hoặc `schemaVersion`; cho phép ghi nguyên body khiến client sửa các field mà server phải quản lý. Ngoài ra cần phòng tránh các tên field và cấu trúc update không hợp lệ hoặc gây thay đổi ngoài dự kiến.

Thay vào đó, xác định rõ thao tác nghiệp vụ, ví dụ “kích hoạt đăng ký”:

```javascript
async function activateEnrollment(enrollments, enrollmentId) {
  const result = await enrollments.updateOne(
    { _id: enrollmentId, status: "PENDING" },
    {
      $set: {
        status: "ACTIVE",
        updatedAt: new Date()
      }
    }
  );

  if (result.matchedCount === 0) {
    throw new Error("ENROLLMENT_NOT_PENDING");
  }

  return result.modifiedCount;
}
```

Hàm trên giả định **phần xác thực, phân quyền và điều kiện kích hoạt** đã được thực hiện ở nơi gọi. Trong API thật, không nên cho người dùng bất kỳ gọi hàm kích hoạt một enrollment bất kỳ. MongoDB sẽ kiểm tra schema của document kết quả; nhưng validator không thể thay việc kiểm tra actor có quyền thực hiện thao tác này.

**Dùng field ownership:** quy định một nhóm field do client cung cấp, nhóm field do hệ thống sinh, nhóm field chỉ workflow quản trị sửa. Đây là cách đơn giản để tránh lỗi gán hàng loạt (*mass assignment*).

## 10. Chế độ validation của MongoDB

MongoDB cho phép điều chỉnh **mức áp dụng** và **hành động khi vi phạm**, hữu ích khi triển khai validator cho collection đã tồn tại.

### 10.1. `validationLevel`

| Giá trị | Ý nghĩa chính |
| --- | --- |
| `strict` | Kiểm tra mọi insert và update theo validator, trừ thao tác được phép bỏ qua validation |
| `moderate` | Kiểm tra insert và update trên các document hiện đã hợp lệ; không áp validator cho update trên document cũ đang không hợp lệ |
| `off` | Tắt áp dụng document validation của collection |

Lưu ý với `moderate`: nó không có nghĩa “chỉ kiểm tra vài field” hoặc “cho phép insert dữ liệu sai”. Giá trị này có ích ở một số giai đoạn chuyển đổi dữ liệu cũ khi chưa thể sửa toàn bộ ngay, nhưng không thay thế kế hoạch dọn dữ liệu.

### 10.2. `validationAction`

| Giá trị | Ứng xử phổ biến |
| --- | --- |
| `error` | Từ chối thao tác vi phạm validator |
| `warn` | Cho phép thao tác và ghi cảnh báo liên quan đến vi phạm validation vào log server |

Một số phiên bản MongoDB có thêm lựa chọn hoặc tính năng ghi log mở rộng. Khi làm việc với một phiên bản cụ thể, cần dùng đúng tùy chọn mà phiên bản đó hỗ trợ. Hai giá trị `error` và `warn` đủ để hiểu khác biệt căn bản giữa **chặn** và **quan sát**.

Ví dụ thay đổi action cho **collection demo**, khi đã hiểu tác động:

```javascript
lab.runCommand({
  collMod: "enrollments_demo",
  validationAction: "warn"
});

// Sau khi chuẩn hóa dữ liệu và muốn thực sự chặn:
lab.runCommand({
  collMod: "enrollments_demo",
  validationLevel: "strict",
  validationAction: "error"
});
```

Lệnh `collMod` thay đổi cấu hình collection hiện có; với collection dùng chung, phải thực hiện theo quy trình thay đổi schema của dự án. Khi `validationAction: "warn"`, dữ liệu sai vẫn có thể được ghi; cảnh báo **không đồng nghĩa đã được sửa**. Ngoài ra, unique index vẫn có thể từ chối bản ghi trùng dù schema đang ở chế độ warn.

### 10.3. Kiểm tra cấu hình validator của collection

Trong `mongosh`:

```javascript
printjson(lab.getCollectionInfos({ name: "enrollments_demo" }));
```

Thông tin collection có thể cho thấy `options.validator`, `validationLevel` và `validationAction`. Lệnh xem metadata có thể yêu cầu quyền phù hợp với tài khoản đang dùng.

**Trường hợp đặc biệt:** các thao tác có tùy chọn `bypassDocumentValidation`, khi tài khoản được phép, có thể bỏ qua schema validation. Đây là lý do database validator là một lớp bảo vệ quan trọng nhưng không phải biện pháp bảo mật duy nhất. Chỉ cấp quyền hoặc dùng cơ chế bypass khi có tình huống vận hành được kiểm soát.

## 11. Phối hợp schema validation khi dữ liệu đang thay đổi

### 11.1. Vấn đề thực tế khi cập nhật schema

Giả sử phiên bản đầu tiên lưu:

```javascript
{
  studentId: ObjectId("66a000000000000000000001"),
  courseId: ObjectId("66a000000000000000000002"),
  status: "PENDING"
}
```

Phiên bản mới thêm `enrolledAt` và `schemaVersion` bắt buộc. Nếu bật ngay validator `strict`/`error` mà dữ liệu cũ thiếu các trường này, các update sau đó lên document cũ có thể bị từ chối. Ứng dụng cũ vẫn chạy trên một số instance cũng có thể tiếp tục gửi định dạng cũ và gặp lỗi.

Vì vậy nên coi việc thay schema như một **thay đổi hợp đồng giữa dữ liệu lưu trữ và các phiên bản ứng dụng**.

### 11.2. Quy trình chuyển đổi theo từng giai đoạn

Một trình tự có thể áp dụng:

1. **Xác định mục tiêu:** trường nào thêm, bỏ, đổi kiểu; quy tắc nào là bất biến bắt buộc và ảnh hưởng đến phiên bản API nào.
2. **Khảo sát dữ liệu hiện tại:** đếm document thiếu field hoặc sai kiểu; xác định những writer đang ghi collection như API, job, ETL.
3. **Triển khai phần mềm tương thích:** code mới xử lý được cả định dạng cũ và mới khi giai đoạn chuyển đổi yêu cầu; writer mới bắt đầu ghi đủ dữ liệu.
4. **Quan sát vi phạm:** cân nhắc validator chế độ `warn` và đo số lần ghi sai trong môi trường phù hợp, kèm báo cáo lỗi từ ứng dụng.
5. **Backfill dữ liệu cũ:** chuyển đổi document theo batch có điều kiện; lưu checkpoint và có cách khôi phục nếu quá trình bị gián đoạn.
6. **Bật bảo vệ mạnh:** khi các writer đã tương thích và dữ liệu được xử lý, áp `strict` + `error` theo quy trình phát hành.
7. **Theo dõi sau phát hành:** quan sát mã lỗi validation, duplicate key và chỉ số liên quan; tránh để user gặp lỗi khó hiểu.

MongoDB không tự biến dữ liệu cũ thành hợp lệ chỉ vì validator được thêm vào. Áp validator trên collection hiện có chủ yếu tác động đến các thao tác ghi tiếp theo theo `validationLevel`, `validationAction` đã chọn.

### 11.3. Chọn chặt hay linh hoạt với các field mới?

`additionalProperties: false` làm schema khép kín: chỉ những field được định nghĩa mới được ghi. Nó phù hợp khi cần hợp đồng dữ liệu kiểm soát chặt và có quy trình phát hành đồng bộ.

Tuy nhiên, khi nhiều phiên bản ứng dụng cùng ghi một collection, schema quá khép kín có thể khiến rollout thêm field thất bại nếu validator chưa cập nhật. Lựa chọn cho phép field bổ sung hay không là quyết định có chủ đích. Bất kể lựa chọn nào, API vẫn phải kiểm soát những field mà client được phép cung cấp.

**Phân biệt trách nhiệm:** MongoDB quyết định document có tuân thủ hợp đồng lưu trữ; ứng dụng quyết định request có hợp lệ trong **ngữ cảnh phiên bản, người dùng và nghiệp vụ**.

## 12. Trả lỗi có ích từ MongoDB về API

Một API tốt không chuyển nguyên văn mọi lỗi driver ra client. Nó ánh xạ lỗi thành phản hồi có ý nghĩa, đồng thời giữ thông tin kỹ thuật cần thiết trong log nội bộ.

| Nguồn lỗi | Ví dụ | Phản hồi API thường phù hợp |
| --- | --- | --- |
| Kiểm tra input ở API | `courseId` không phải chuỗi ObjectId hợp lệ | HTTP `400 Bad Request` với chi tiết field |
| Xác thực | Chưa đăng nhập hoặc token không hợp lệ | `401 Unauthorized` |
| Phân quyền | Không được đăng ký thay người khác | `403 Forbidden` |
| Trạng thái nghiệp vụ | Khóa học ngừng nhận đăng ký | `409 Conflict` hoặc mã nghiệp vụ phù hợp |
| Unique index (`11000`) | Cặp student–course đã tồn tại | `409 Conflict`, thông điệp không tiết lộ chi tiết index nội bộ |
| Document validation (`121`) | Server nhận document sai BSON type/required/enum | Xử lý lỗi contract hoặc dữ liệu đầu vào phù hợp; ghi log để điều tra |
| Mạng, timeout, lỗi server | Không truy cập được MongoDB | Phản hồi lỗi hệ thống thích hợp, giữ chi tiết trong log và cơ chế retry hợp lý |

Mã HTTP ở bảng chỉ là cách ánh xạ phổ biến, có thể điều chỉnh theo API contract của dự án. Đặc biệt, nếu ứng dụng đã validate input nhưng vẫn gặp lỗi `121`, đây có thể là **lỗi lệch schema giữa application và database** hoặc writer không tuân thủ contract; không nên mặc định trả lại rằng người dùng đã nhập sai.

Ví dụ bắt một số lỗi ở tầng service Node.js:

```javascript
try {
  const result = await enrollments.insertOne(candidate);
  return { id: result.insertedId.toHexString() };
} catch (err) {
  if (err?.code === 11000) {
    throw new Error("ENROLLMENT_ALREADY_EXISTS");
  }
  if (err?.code === 121) {
    // Ghi log kỹ thuật nội bộ; kiểm tra lệch schema hoặc dữ liệu.
    throw new Error("INVALID_STORED_DOCUMENT_SHAPE");
  }
  throw err;
}
```

Ví dụ trên minh họa **phân loại lỗi trong service**; controller sẽ ánh xạ mã nội bộ sang HTTP response đã thống nhất. Không nên tự ý trả trực tiếp stack trace, raw document, thông tin kết nối hoặc chi tiết schema nhạy cảm đến client.

### 12.1. Quan sát lỗi cần có ngữ cảnh

Log ứng dụng của thao tác ghi nên có những thông tin an toàn và hữu ích, chẳng hạn:

- mã request hoặc correlation ID để tìm cùng một luồng xử lý;
- tên thao tác nghiệp vụ, tên collection và phiên bản ứng dụng;
- mã lỗi MongoDB và loại ràng buộc bị vi phạm;
- thời điểm xảy ra, kết quả retry nếu có;
- mức độ ảnh hưởng (một request hay nhiều request sau khi deploy).

Không đưa secret, mật khẩu, token, thông tin cá nhân không cần thiết hoặc toàn bộ document nhạy cảm vào log chỉ để chẩn đoán lỗi validation.

## 13. Vì sao không chỉ validate ở ứng dụng hoặc chỉ ở database?

### 13.1. Nếu chỉ kiểm tra ở ứng dụng

Giả sử API chính có hàm `validateEnrollment()` nhưng một script import dữ liệu chạy trực tiếp vào MongoDB:

```text
API request --> validateEnrollment() --> MongoDB

Import job -----------------------> MongoDB
```

Nếu import job không sử dụng cùng thư viện hoặc bị viết sai, dữ liệu sai vẫn có thể chui vào collection. Khi dùng document validator, một phần hợp đồng về kiểu và các field bắt buộc được thực thi **ở mọi writer thông thường**, dù writer đến từ API hay batch job.

### 13.2. Nếu chỉ kiểm tra ở database

MongoDB có thể từ chối `score = 150`, nhưng không biết client có được phép đặt điểm, sinh viên có đủ điều kiện học hay trạng thái được đổi theo quy trình chưa. Lỗi database cũng khó chuyển trực tiếp thành thông điệp phù hợp cho từng form hoặc ngôn ngữ người dùng.

Đặt toàn bộ logic nghiệp vụ vào một lớp validator sẽ khiến sự phụ thuộc giữa policy ứng dụng và storage trở nên khó triển khai. MongoDB document validation phù hợp với **tính đúng đắn của cấu trúc lưu trữ**, còn business services phù hợp với **quyết định có ngữ cảnh**.

### 13.3. Khi nhiều dịch vụ cùng ghi một collection

Mỗi writer phải tuân thủ contract chung, chẳng hạn kiểu ID, tên field, enum và quy tắc ngày giờ. Validator ở MongoDB là lớp bảo vệ chung; các service vẫn cần kiểm tra phù hợp với nhiệm vụ của mình.

Nếu nhiều service cùng thay đổi `status`, nên xác định **dịch vụ sở hữu state machine** hoặc API/command dùng chung, thay vì để mỗi service hiểu quá trình chuyển trạng thái theo cách riêng. Các cập nhật có điều kiện theo trạng thái hiện hành giúp giữ quy tắc dưới cạnh tranh, nhưng vẫn cần policy thống nhất ở tầng nghiệp vụ.

## 14. Sai lầm phổ biến và cách tránh

| Sai lầm | Hệ quả | Cách tiếp cận phù hợp |
| --- | --- | --- |
| Tin rằng client validation đủ an toàn | Có thể gửi request giả mạo hoặc bỏ qua UI | API phải validate và kiểm tra quyền độc lập |
| Chỉ dùng `$jsonSchema` cho quy tắc unique | Hai document có thể hợp lệ từng cái nhưng trùng khóa nghiệp vụ | Tạo unique index đúng khóa |
| Chỉ kiểm tra `courseId` có 24 ký tự hex | ID đúng định dạng nhưng course có thể không tồn tại | Kiểm tra tham chiếu và vòng đời nghiệp vụ |
| Đọc trạng thái rồi update không kèm điều kiện | Request đồng thời có thể ghi đè logic chuyển trạng thái | Dùng filter theo trạng thái/version hiện hành |
| Thực hiện hai thay đổi quan trọng ở collection khác nhau mà không phối hợp | Có thể tạo enrollment nhưng không cập nhật số ghế hoặc ngược lại | Transaction hoặc thiết kế lại ranh giới dữ liệu |
| Ghi nguyên `req.body` với `$set` | Client có thể sửa field nội bộ hoặc ngoài phạm vi | Allowlist và command nghiệp vụ rõ ràng |
| Dùng kiểu Number bất kỳ dù validator yêu cầu `int` | Dễ phát sinh lỗi BSON type | Quy định kiểu và serialize nhất quán ở driver |
| Bật `strict`/`error` ngay khi dữ liệu cũ chưa tương thích | Các writer cũ và update trên document cũ có thể bị từ chối | Khảo sát, mở rộng schema, backfill và triển khai có giai đoạn |
| Để `warn` vô thời hạn rồi coi là bảo vệ | Dữ liệu sai vẫn được ghi | Theo dõi cảnh báo và chuyển sang cơ chế chặn khi phù hợp |
| Cho tài khoản ứng dụng quyền bypass validation tùy ý | Mất lớp bảo vệ tại database | Giới hạn quyền và quy trình sử dụng bypass |
| Trả nguyên lỗi MongoDB ra API | Lộ chi tiết kỹ thuật; người dùng khó xử lý | Ánh xạ lỗi và log nội bộ có kiểm soát |
| Sao chép nhiều định nghĩa enum nhưng không đồng bộ | API chấp nhận một giá trị mà DB từ chối, hoặc ngược lại | Có nguồn contract được quản lý, phát hành schema theo phiên bản |

## 15. Thực hành quan sát phân chia trách nhiệm

Các thao tác dưới đây tiếp tục dùng biến `lab`, `enrollments`, `inserted` và `runId` đã tạo trong `mongosh` ở mục 5.

### 15.1. Thử nghiệm cấu trúc

1. Dùng `findOne` đọc document hợp lệ vừa tạo.
2. Thử cập nhật `score` sang `NumberInt(150)`, quan sát lỗi validation.
3. Đọc lại để thấy document gốc chưa bị thay đổi bởi thao tác không hợp lệ.
4. Thử cập nhật `score` sang `NumberInt(95)`, quan sát thao tác hợp lệ.

Ví dụ đọc trước và sau:

```javascript
const exactFilter = {
  _id: inserted.insertedId,
  runId: runId
};

printjson(
  enrollments.findOne(
    exactFilter,
    { score: 1, status: 1, schemaVersion: 1 }
  )
);
```

### 15.2. Thử nghiệm tính duy nhất

Nếu đã tạo unique index ở mục 7, một bản ghi thứ hai có cùng `studentId` và `courseId` sẽ vi phạm chỉ mục dù các field còn lại hợp lệ:

```javascript
// Dự kiến lỗi duplicate key nếu cặp này đã tồn tại.
enrollments.insertOne({
  studentId: studentId,
  courseId: courseId,
  status: "PENDING",
  enrolledAt: new Date(),
  schemaVersion: NumberInt(1),
  runId: runId
});
```

Phân biệt kết quả:

- `score` vượt giới hạn: vi phạm **document validator**.
- Cặp `studentId` + `courseId` trùng: vi phạm **unique index**.
- Khóa học đã đóng đăng ký: thuộc **nghiệp vụ**, phải kiểm tra và bảo vệ phù hợp.
- Người dùng đăng ký thay người khác: thuộc **phân quyền**, phải chặn tại API/service.

### 15.3. Dọn document của lượt thực hành

Vì demo có `runId` riêng, hãy xác nhận đúng database, collection và document trước khi xóa:

```javascript
print("database=" + lab.getName());
print("collection=" + enrollments.getName());
print("runId=" + runId);
printjson(enrollments.findOne(exactFilter));
```

Chỉ khi kết quả đúng document bạn đã tạo:

```javascript
const deletion = enrollments.deleteOne(exactFilter);
printjson(deletion);
print("remaining=" + enrollments.countDocuments(exactFilter));
```

Thông thường `deletedCount` là `1` và `remaining` là `0`. Không xóa cả database hoặc collection để dọn một lần thực hành; validator, index và collection có thể được người khác sử dụng trong môi trường chia sẻ.

## 16. Bảng quyết định cho dự án thật

Khi tiếp nhận một yêu cầu mới, có thể bắt đầu bằng bảng sau:

| Câu hỏi | Nếu câu trả lời là “có” | Công cụ cần cân nhắc |
| --- | --- | --- |
| Quy tắc chỉ phụ thuộc vào field/kiểu của một document? | Có thể áp dụng cho mọi writer | MongoDB `$jsonSchema` |
| Quy tắc cần báo lỗi ngay khi người dùng nhập? | Có thể kiểm tra sớm | UI validation và API input validation |
| Quy tắc liên quan đến người đang thực hiện? | Cần xác thực/quyền | API, service, auth middleware |
| Cần chuẩn hóa chuỗi, chuyển kiểu từ JSON hoặc gán trường hệ thống? | Cần dựng document đúng contract | Tầng ứng dụng |
| Cần ngăn trùng trong nhiều request đồng thời? | Có ràng buộc khóa duy nhất | Unique index |
| Chỉ được update khi giá trị cũ vẫn như mong đợi? | Có nguy cơ cạnh tranh ghi | Filter có điều kiện, atomic update, version |
| Có nhiều document phải thay đổi cùng nhau? | Có invariant xuyên document | Transaction hoặc thay đổi thiết kế dữ liệu |
| Schema phải thay đổi khi còn dữ liệu cũ? | Có nhiều writer/phiên bản | Migration, `collMod`, quan sát và rollout |
| Lỗi database cần được chuyển thành trải nghiệm API? | Client không nên thấy raw error | Error mapping, structured logging |

**Cách nghĩ cần ghi nhớ:** ứng dụng chịu trách nhiệm hiểu **ai đang làm gì, có được phép hay không và quy tắc nghiệp vụ có được thỏa mãn không**. MongoDB chịu trách nhiệm bảo vệ **hình dạng và tính nhất quán cơ bản của dữ liệu lưu trữ**; unique index, update có điều kiện và transaction bổ sung các bảo đảm mà chỉ `$jsonSchema` không cung cấp. Hai phía phối hợp để dữ liệu vẫn hợp lệ dù hệ thống có nhiều client, nhiều writer và nhiều request đến đồng thời.
