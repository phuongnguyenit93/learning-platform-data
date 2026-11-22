# Duyệt quan hệ bằng $graphLookup và kiểm soát độ sâu

Các ứng dụng thực tế không chỉ lưu document độc lập. Một nhân viên có thể báo cáo cho một người quản lý, phòng ban có thể có phòng ban con, một danh mục có nhiều cấp, hoặc một sân bay kết nối tới các sân bay khác. Những dữ liệu đó hình thành **đồ thị (graph)** gồm **đỉnh (vertex)** và **cạnh (edge)**. Nếu muốn tìm “toàn bộ cấp dưới của giám đốc”, “chuỗi quản lý từ nhân viên tới lãnh đạo”, hoặc “các điểm có thể đến trong tối đa hai lần chuyển tiếp”, thao tác join một cấp thông thường là chưa đủ.

Trong **MongoDB Aggregation Framework**, stage **`$graphLookup`** thực hiện **truy vấn đệ quy** qua các quan hệ được lưu bằng field, trả về những document có thể tiếp cận từ một hay nhiều giá trị khởi đầu. Stage này có tham số giới hạn độ sâu **`maxDepth`**, trả độ sâu bằng **`depthField`**, và cho phép hạn chế các nút được duyệt bằng **`restrictSearchWithMatch`**.

Bài thuộc chương **Aggregation nâng cao** của module *Database Engine Document MongoDB*, tập trung vào cách xác định **hướng duyệt**, **độ sâu**, **điều kiện dừng**, **index**, **chu trình**, cũng như các giới hạn bộ nhớ và sharding khi áp dụng `$graphLookup` trên hệ thống thật.

Sau bài học, bạn có thể:

- Phân biệt `$lookup` một cấp với `$graphLookup` nhiều cấp.
- Dựng đúng `startWith`, `connectFromField`, `connectToField`, `from` và `as`.
- Truy vấn **hậu duệ (descendants)** và **tổ tiên (ancestors)** của cùng một cấu trúc tổ chức.
- Diễn giải chính xác **`maxDepth: 0`, `maxDepth: 1`** và giá trị `depthField` bắt đầu từ **0**.
- Hiểu `restrictSearchWithMatch` có thể **cắt cả nhánh duyệt**, khác với `$filter` sau khi đã duyệt xong.
- Sắp xếp kết quả khi `$graphLookup` không cam kết thứ tự array, và tính số nút theo từng mức.
- Kiểm soát quan hệ vòng, mảng nhiều cạnh, dữ liệu thiếu/trùng khóa, và ranh giới giữa tenant.
- Thiết kế index trên field được nối, giới hạn đầu vào, đọc `explain` và cân nhắc các giới hạn bộ nhớ/phiên bản.
- Viết pipeline tương ứng qua `mongosh` và MongoDB Java Sync Driver.

> **Lưu ý phiên bản:** Các ví dụ về cú pháp và độ sâu dùng cơ chế `$graphLookup` có trong MongoDB 7.0, 8.0 và các phiên bản tương thích. Một số hành vi **bộ nhớ/spill-to-disk** khác nhau theo dòng server: tài liệu MongoDB 7.0/8.0 nêu giới hạn 100 MB riêng cho `$graphLookup` và không hỗ trợ `allowDiskUse` để vượt giới hạn này, trong khi tài liệu Database Manual hiện hành mô tả cơ chế spill khi vượt 100 MB nếu được phép. Phải kiểm tra tài liệu **đúng phiên bản server** trước khi thiết kế tải lớn; không suy ra khả năng spill từ một đoạn ví dụ chung.

## 1. Vì sao cần truy vấn đệ quy?

Xét hệ thống nhân sự:

~~~text
CEO
├── A (Trưởng kỹ thuật)
│   ├── C (Nhóm nền tảng)
│   │   └── E (Kỹ sư)
│   └── D (Nhóm kiểm thử)
│       └── I (Kiểm thử viên)
└── B (Trưởng vận hành)
    ├── F (Nhóm hạ tầng)
    │   └── G (Kỹ sư hạ tầng)
    └── H (Nhân viên vận hành)
~~~

Mỗi nhân viên chỉ lưu **mã người quản lý trực tiếp**:

~~~javascript
{
  employeeId: "E",
  managerId: "C"
}
~~~

Muốn biết người quản lý trực tiếp của E, chỉ cần một phép tra cứu theo `managerId`. Nhưng muốn đi từ E lên C → A → CEO, hoặc từ CEO xuống toàn bộ A/B/C/D/E/F/G/H/I, ứng dụng phải lặp lại việc tìm các nút liên quan qua **nhiều bước không cố định trước**.

Ba hướng triển khai thường gặp:

1. **Nhiều lần gọi truy vấn từ ứng dụng:** tìm manager cấp 1, rồi cấp 2, cứ tiếp tục; dễ phát sinh nhiều round trips và phải tự xử lý vòng lặp/giới hạn.
2. **Lưu sẵn toàn bộ tổ tiên/hậu duệ:** đọc nhanh nhưng cập nhật phức tạp khi đổi cấu trúc; cần duy trì dữ liệu dẫn xuất.
3. **Dùng `$graphLookup`:** để MongoDB thực hiện traversal đệ quy trong aggregation, có tham số giới hạn số bước và điều kiện trên document đang duyệt.

`$graphLookup` không yêu cầu một “graph database” riêng. Các đỉnh vẫn là document trong collection và cạnh có thể là field scalar hoặc array các giá trị tham chiếu.

### 1.1. `$lookup` và `$graphLookup` khác nhau thế nào?

| Khía cạnh | `$lookup` | `$graphLookup` |
|---|---|---|
| Mục tiêu thông thường | Join document sang một collection khác. | Đi theo quan hệ **đệ quy nhiều cấp**. |
| Số cấp quan hệ | Một phép join trong mỗi stage; có thể lồng các stage theo thiết kế. | Tự mở rộng qua `connectFromField`/`connectToField` cho tới khi dừng. |
| Giới hạn độ sâu | Không có `maxDepth` của traversal đệ quy. | Có `maxDepth`. |
| Thông tin độ sâu | Không tự thêm depth của nút. | Có `depthField` (bắt đầu từ 0). |
| Điều kiện lọc | Filter ở query/pipeline lookup. | `restrictSearchWithMatch` áp trong quá trình duyệt. |
| Kết quả | Array các document join. | Array các document có thể đi tới theo quan hệ. |

Không dùng `$graphLookup` chỉ để thay `$lookup` đơn giản nếu không cần đi nhiều cấp: stage đệ quy có chi phí và ngữ nghĩa riêng.

## 2. Mô hình thuật toán của `$graphLookup`

Hình thức cơ bản:

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    as: "descendants",
    maxDepth: 2,
    depthField: "depth",
    restrictSearchWithMatch: { active: true }
  }
}
~~~

Trong đó:

| Tham số | Bắt buộc? | Ý nghĩa |
|---|---|---|
| **`from`** | Có | Tên collection đích **trong cùng database** chứa các document để duyệt. |
| **`startWith`** | Có | Aggregation **expression** lấy giá trị bắt đầu từ document đầu vào; có thể là literal, field path, hoặc expression/array. |
| **`connectFromField`** | Có | Tên field của nút vừa tìm được, lấy giá trị để tiếp tục mở rộng các cạnh. |
| **`connectToField`** | Có | Tên field trong collection `from` dùng để đối chiếu giá trị khởi đầu và các giá trị mở rộng. |
| **`as`** | Có | Tên array gắn vào document đầu vào để chứa những nút đã tìm thấy. |
| **`maxDepth`** | Không | Số nguyên không âm giới hạn mức recursion tối đa; **0** vẫn thực hiện một lượt tra cứu đầu. |
| **`depthField`** | Không | Tên field gắn vào mỗi document được tìm thấy, biểu diễn độ sâu bằng `NumberLong`; **bắt đầu từ 0**. |
| **`restrictSearchWithMatch`** | Không | Query filter giới hạn những document `from` được chấp nhận và mở rộng tiếp trong traversal. |

### 2.1. Đọc traversal thành từng bước

Giả sử document đầu vào có `employeeId = "CEO"` và `startWith: "$employeeId"`:

~~~text
Input document (CEO)
     |
     | startWith = "CEO"
     v
Tìm from.employees có managerId = "CEO"  --> A, B (depth 0)
     |
     | Lấy employeeId từ A và B
     v
Tìm managerId = "A" hoặc "B"              --> C, D, F, H (depth 1)
     |
     | Lấy employeeId từ C, D, F, H
     v
Tìm managerId = "C", "D", "F", "H"        --> E, I, G (depth 2)
     |
     v
Đạt maxDepth = 2 -> dừng mở rộng sâu hơn
     |
     v
Gắn các nút đã tìm vào array CEO.descendants
~~~

Điều kiện quan trọng là **đối chiếu `connectToField`**, sau đó **lấy `connectFromField` của nút mới** để mở rộng vòng tiếp theo. Đổi hai field này cho nhau thường khiến query duyệt **ngược hướng** hoặc bắt đầu từ nút khác.

### 2.2. Không nhầm `startWith` với document đầu tiên được trả về

`startWith` tạo **giá trị tìm kiếm đầu tiên**, không mặc nhiên thêm document input vào output. Với truy vấn hậu duệ, startWith là mã CEO, nhưng vòng đầu tìm những người có `managerId = "CEO"`, tức **A và B** — không phải bản thân CEO.

Ngược lại, nếu `startWith: "$employeeId"` và `connectToField: "employeeId"` thì nút đầu tiên có thể chính là nhân viên input. Hãy tự viết phép so sánh đầu tiên dưới dạng:

~~~text
from.<connectToField> == evaluated(startWith)
~~~

Trước khi chạy pipeline, câu này giúp phát hiện hầu hết lỗi đảo chiều.

### 2.3. `startWith` và `connectFromField` là array

`startWith` có thể trả một **array giá trị**; MongoDB sẽ bắt đầu traversal đồng thời từ các phần tử đó. Nếu field `connectFromField` của nút được duyệt là array, MongoDB sẽ theo **từng giá trị cạnh** từ mảng.

Điều này phù hợp với quan hệ nhiều–nhiều như sân bay nối nhiều sân bay hoặc người dùng có nhiều bạn bè. Không cần một lời gọi `$graphLookup` riêng cho từng edge của array.

### 2.4. Output của `$graphLookup` không bảo đảm thứ tự

Các document trong array `as` **không có thứ tự được cam kết**. Không được mặc định phần tử 0 là cấp trên gần nhất, hoặc mọi nút depth 0 luôn đứng trước depth 1 trong array. Nếu cần hiển thị có thứ tự, thêm bước sort sau khi duyệt; bài sẽ trình bày `$sortArray` và `$unwind` ở phần sau.

## 3. Dữ liệu thực hành có thể tái tạo

Mọi ví dụ dùng database `graph_lookup_lab`. Dữ liệu nhân viên có field:

- `employeeId`: khóa nghiệp vụ ổn định trong mô hình demo.
- `managerId`: mã quản lý trực tiếp; CEO có `managerId: null`.
- `name` và `department`: thông tin hiển thị.
- `active`: trạng thái để minh họa việc cắt nhánh truy vấn.

Chỉ chạy lệnh `insertMany` trên **collection lab đang trống**. Chạy lại với cùng `_id` sẽ báo duplicate key; không xóa production hoặc database dùng chung để tái tạo ví dụ.

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

lab.employees.insertMany([
  {
    _id: "E-CEO",
    employeeId: "CEO",
    managerId: null,
    name: "Tổng giám đốc",
    department: "EXEC",
    active: true
  },
  {
    _id: "E-A",
    employeeId: "A",
    managerId: "CEO",
    name: "Trưởng kỹ thuật",
    department: "ENG",
    active: true
  },
  {
    _id: "E-B",
    employeeId: "B",
    managerId: "CEO",
    name: "Trưởng vận hành",
    department: "OPS",
    active: true
  },
  {
    _id: "E-C",
    employeeId: "C",
    managerId: "A",
    name: "Nhóm nền tảng",
    department: "ENG",
    active: true
  },
  {
    _id: "E-D",
    employeeId: "D",
    managerId: "A",
    name: "Nhóm kiểm thử",
    department: "ENG",
    active: false
  },
  {
    _id: "E-E",
    employeeId: "E",
    managerId: "C",
    name: "Kỹ sư",
    department: "ENG",
    active: true
  },
  {
    _id: "E-F",
    employeeId: "F",
    managerId: "B",
    name: "Nhóm hạ tầng",
    department: "OPS",
    active: true
  },
  {
    _id: "E-G",
    employeeId: "G",
    managerId: "F",
    name: "Kỹ sư hạ tầng",
    department: "OPS",
    active: true
  },
  {
    _id: "E-H",
    employeeId: "H",
    managerId: "B",
    name: "Nhân viên vận hành",
    department: "OPS",
    active: true
  },
  {
    _id: "E-I",
    employeeId: "I",
    managerId: "D",
    name: "Kiểm thử viên",
    department: "ENG",
    active: true
  }
])

lab.employees.find(
  {},
  { _id: 0, employeeId: 1, managerId: 1, active: 1 }
).sort({ employeeId: 1 })
~~~

### 3.1. Sơ đồ chính xác của fixture

~~~text
CEO [EXEC, active]
|
|-- A [ENG, active]                         Cấp dưới trực tiếp
|   |-- C [ENG, active]                     Cấp cháu
|   |   +-- E [ENG, active]                 Cấp sâu hơn
|   +-- D [ENG, INACTIVE]
|       +-- I [ENG, active]
|
+-- B [OPS, active]
    |-- F [OPS, active]
    |   +-- G [OPS, active]
    +-- H [OPS, active]
~~~

Tập hậu duệ của CEO nếu **không filter active** gồm A, B, C, D, E, F, G, H, I — tổng **9** nhân viên. Nếu chỉ đi qua các **nút active**, D bị loại và nhánh dưới D (I) cũng không được duyệt qua D; tập kết quả là A, B, C, E, F, G, H — tổng **7** nhân viên.

### 3.2. Tạo index thử nghiệm

~~~javascript
// Khóa business ID; cần duy nhất trong mô hình demo.
lab.employees.createIndex(
  { employeeId: 1 },
  { unique: true, name: "ux_employeeId" }
)

// Cho phép tra các nhân viên theo quản lý trực tiếp.
lab.employees.createIndex(
  { managerId: 1 },
  { name: "ix_managerId" }
)

// Có thể dùng index này khi traversal còn lọc active,
// nhưng cần xem explain và workload thực tế.
lab.employees.createIndex(
  { managerId: 1, active: 1 },
  { name: "ix_managerId_active" }
)
~~~

Với truy vấn hậu duệ, engine thường cần tìm `managerId` trong collection `from`. Với truy vấn tổ tiên, engine tìm `employeeId`. Vì thế index trên **`connectToField` của hướng duyệt** là ứng viên quan trọng; không suy rằng chỉ index `managerId` thì cả hai hướng đều tối ưu như nhau.

## 4. Tìm toàn bộ cấp dưới: traversal từ cha xuống con

Để tìm hậu duệ của CEO, ta bắt đầu bằng **mã CEO** và tìm các document có **`managerId` bằng mã đó**. Với mỗi nhân viên vừa tìm được, tiếp tục lấy `employeeId` của người ấy để tìm những cấp dưới kế tiếp:

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      depthField: "level"
    }
  },
  {
    $project: {
      _id: 0,
      employeeId: 1,
      descendantIds: "$descendants.employeeId",
      descendantCount: { $size: "$descendants" }
    }
  }
])
~~~

Trên fixture, `descendantCount` là **9**. Array `descendantIds` có A, B, C, D, E, F, G, H, I nhưng **thứ tự không được cam kết**. Cần phân biệt:

~~~text
Input: employeeId = "CEO"
        |
        v
Lookup from.employee.managerId = "CEO" -> A, B
        |
        +-> lấy A.employeeId = "A" để tìm managerId = "A" -> C, D
        +-> lấy B.employeeId = "B" để tìm managerId = "B" -> F, H
        ...
~~~

**Vì sao không bắt đầu từ `managerId`?** Document CEO có `managerId: null`; nếu dùng `startWith: "$managerId"` kết hợp với `connectToField:"managerId"`, ta đang hỏi “ai có managerId null?” chứ không tìm đúng tuyến con của CEO. Điểm khởi đầu và hướng cạnh phải được xác định cùng nhau.

### 4.1. Trả danh sách tên và độ sâu

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      depthField: "level",
      maxDepth: 2
    }
  },
  {
    $set: {
      descendants: {
        $sortArray: {
          input: "$descendants",
          sortBy: { level: 1, employeeId: 1 }
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      employeeId: 1,
      "descendants.employeeId": 1,
      "descendants.name": 1,
      "descendants.level": 1
    }
  }
])
~~~

`$sortArray` được MongoDB hỗ trợ từ phiên bản **5.2**. Dạng ví dụ có field `level` và `employeeId` đủ để sắp theo cấp rồi theo mã nhân viên. Không dùng thứ tự phần tử gốc của `$graphLookup` để hiển thị cây hoặc để suy ra vị trí đầu tiên.

### 4.2. Trả kết quả “phẳng” thay vì một array lớn

Nếu API cần mỗi hậu duệ một dòng, dùng `$unwind`:

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      depthField: "level",
      maxDepth: 2
    }
  },
  { $unwind: "$descendants" },
  {
    $project: {
      _id: 0,
      employeeId: "$descendants.employeeId",
      name: "$descendants.name",
      managerId: "$descendants.managerId",
      level: "$descendants.level"
    }
  },
  { $sort: { level: 1, employeeId: 1 } }
])
~~~

Trong fixture, pipeline trả **9 pipeline documents**, mỗi document là một hậu duệ với `level`. Cách này thuận tiện để đếm/phân nhóm theo cấp, nhưng `$graphLookup` **vẫn phải duyệt và xây array** trước khi `$unwind`; đừng suy rằng unwind sẽ xóa được mọi giới hạn tài nguyên của traversal.

### 4.3. Đếm số người dưới mỗi cấp

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      maxDepth: 2,
      depthField: "level"
    }
  },
  { $unwind: "$descendants" },
  {
    $group: {
      _id: "$descendants.level",
      employees: { $sum: 1 },
      employeeIds: { $addToSet: "$descendants.employeeId" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Kết quả dự kiến:

| `_id` = level | Số nhân viên | Tập mã nhân viên |
|---:|---:|---|
| 0 | 2 | A, B |
| 1 | 4 | C, D, F, H |
| 2 | 3 | E, G, I |

`$addToSet` tạo **tập** các ID nhưng thứ tự bên trong array không được bảo đảm. Với báo cáo số lượng theo cấp, `$sum:1` là đủ; chỉ trả ID khi thực sự cần và cân nhắc output lớn.

## 5. Tìm chuỗi cấp trên: traversal từ con lên cha

Cũng trên collection `employees`, ta có thể tìm **tổ tiên** bằng cách đảo hướng nối.

Một nhân viên G có `managerId:"F"`. Để tìm cấp trên:

1. Lấy giá trị `managerId` của G (`"F"`).
2. Tìm người có `employeeId:"F"`.
3. Lấy `managerId` của F (`"B"`), tìm người `employeeId:"B"`.
4. Tiếp tục đến CEO.

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "G" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$managerId",
      connectFromField: "managerId",
      connectToField: "employeeId",
      as: "ancestors",
      depthField: "level"
    }
  },
  {
    $project: {
      _id: 0,
      employeeId: 1,
      name: 1,
      "ancestors.employeeId": 1,
      "ancestors.name": 1,
      "ancestors.level": 1
    }
  }
])
~~~

Với G, các tổ tiên là **F (level 0), B (level 1), CEO (level 2)**. Array `ancestors` có thể ở thứ tự bất kỳ.

### 5.1. So sánh hướng truy vấn

| Mục tiêu | `startWith` | `connectFromField` | `connectToField` | Đọc mối quan hệ |
|---|---|---|---|---|
| Tìm **hậu duệ** | `"$employeeId"` | `"employeeId"` | `"managerId"` | Tìm ai có `managerId` bằng ID nút hiện tại. |
| Tìm **tổ tiên** | `"$managerId"` | `"managerId"` | `"employeeId"` | Tìm ai có `employeeId` bằng manager ID hiện tại. |

Hãy dùng câu hỏi xác minh:

~~~text
Lần tra cứu đầu tiên phải tìm:
  from.connectToField = evaluated(startWith)

Mỗi lần mở rộng phải tìm:
  from.connectToField = giá trị connectFromField của nút vừa tìm
~~~

Không có khái niệm tự động “đi ngược” trong `$graphLookup`; đổi field của hai phía chính là cách thay hướng.

### 5.2. Sắp chuỗi quản lý gần nhất đến xa nhất

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "G" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$managerId",
      connectFromField: "managerId",
      connectToField: "employeeId",
      as: "ancestors",
      depthField: "level"
    }
  },
  {
    $set: {
      ancestors: {
        $sortArray: {
          input: "$ancestors",
          sortBy: { level: 1, employeeId: 1 }
        }
      }
    }
  },
  { $project: { _id: 0, employeeId: 1, ancestors: 1 } }
])
~~~

Sau khi sort, chuỗi đi **F → B → CEO**. Nếu muốn trình bày từ cao xuống thấp, thay `level: 1` bằng `level: -1`. **Depth 0 là người quản lý trực tiếp**, không phải bản thân nhân viên G.

### 5.3. Tổ tiên với độ sâu giới hạn

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "G" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$managerId",
      connectFromField: "managerId",
      connectToField: "employeeId",
      as: "managers",
      maxDepth: 1,
      depthField: "level"
    }
  }
])
~~~

Với `maxDepth:1`, chỉ trả **F (level 0)** và **B (level 1)**; CEO ở level 2 không được lấy. Đây là cách diễn đạt “tối đa **hai cấp quản lý** tính từ manager trực tiếp” trong fixture.

## 6. Hiểu đúng `maxDepth` và `depthField`

Đây là hai tham số quan trọng nhất để **kiểm soát độ sâu traversal**. Chúng liên quan nhưng không có cùng chức năng:

- **`maxDepth`** quyết định traversal **được mở rộng sâu tối đa tới mức nào**.
- **`depthField`** ghi mức đã đạt được vào từng document trong output để bạn quan sát/hiển thị/lọc/nhóm.

### 6.1. Độ sâu bắt đầu từ 0, không phải 1

Khi tìm hậu duệ CEO:

~~~text
CEO          -> document đầu vào, không tính vào descendants
├─ A, B      -> depth 0  (lượt tìm đầu tiên)
├─ C,D,F,H   -> depth 1  (lượt mở rộng thứ hai)
└─ E,I,G     -> depth 2  (lượt mở rộng thứ ba)
~~~

Vì vậy câu “cấp dưới trực tiếp” tương ứng **`maxDepth:0`**, không phải `maxDepth:1`. Nếu nói “lấy tối đa ba tầng con” thì tương ứng `maxDepth:2`.

### 6.2. Bảng `maxDepth` theo fixture

| `maxDepth` | Các nút trả về | Số nút | Ý nghĩa |
|---:|---|---:|---|
| 0 | A, B | 2 | Chỉ cấp dưới trực tiếp. |
| 1 | A, B, C, D, F, H | 6 | Cấp dưới trực tiếp và một tầng dưới họ. |
| 2 | A, B, C, D, E, F, G, H, I | 9 | Ba tầng hậu duệ. |
| 3 | Như level 2 trên fixture | 9 | Không có nút mới ở tầng sâu hơn. |
| Không chỉ định | Toàn bộ các nút có thể đến | 9 | Duyệt tới khi không có match mới trong fixture. |

`maxDepth` phải là **số nguyên không âm**. Giá trị âm hoặc kiểu không phù hợp không phải cách diễn đạt “không giới hạn”; muốn dùng độ sâu không giới hạn thì **bỏ tham số**, nhưng làm vậy có thể rất tốn tài nguyên trên graph thực tế.

### 6.3. Ví dụ tối đa hai tầng hậu duệ

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      maxDepth: 1,
      depthField: "level"
    }
  },
  {
    $project: {
      _id: 0,
      employeeId: 1,
      count: { $size: "$descendants" },
      descendantIds: "$descendants.employeeId"
    }
  }
])
// CEO có 6 descendants ở levels 0 và 1.
~~~

### 6.4. `maxDepth:0` tương đương tra cứu một cấp

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "directReports",
      maxDepth: 0
    }
  }
])
~~~

Kết quả là A và B; MongoDB Manual mô tả `maxDepth:0` tương đương một **non-recursive `$graphLookup` search**. Khi chỉ cần join một cấp, `$lookup` vẫn có thể là lựa chọn đơn giản hơn. Không dùng `maxDepth:0` để “tắt stage”: nó **vẫn truy vấn lượt đầu**.

### 6.5. Depth dùng cho nghiệp vụ, nhưng không phải đường đi được xuất đầy đủ

`depthField` chỉ cho biết **mức traversal của document được tìm thấy**, không lưu toàn bộ chuỗi ID từ nút gốc tới nút đó. Với cấu trúc **cây có một cha**, người ta có thể dựng đường đi bằng cách lần theo `managerId`. Với graph có **nhiều đường đi tới cùng một nút**, chỉ có depth không đủ để biết chính xác đường nào đã dẫn tới nút đó.

Không suy rằng `$graphLookup` tự trả **shortest path**, **mọi đường đi**, **số đường đi** hoặc **trọng số cạnh**. Nó trả tập document có thể đến trong phạm vi traversal; với bài toán đường đi ngắn nhất có trọng số hoặc tối ưu nhiều tiêu chí, cần thuật toán/mô hình khác hoặc hậu xử lý phù hợp.

### 6.6. Giới hạn độ sâu là giới hạn mở rộng, không giới hạn tổng số nút

Một graph có **hệ số phân nhánh lớn** vẫn có thể trả rất nhiều document ở depth 1 hoặc 2. Ví dụ nếu mỗi nút có 1.000 con:

~~~text
depth 0:             1.000 nodes
depth 1:         1.000.000 nodes (trong trường hợp không trùng/cắt nhánh)
depth 2:     1.000.000.000 nodes (mức lý thuyết)
~~~

Do đó `maxDepth:2` **không phải hạn mức 2 document, 2 truy vấn hay 2 MB**. Phải kiểm soát cả **fan-out**, số document đầu vào, kích thước nút và memory/output limits.

## 7. `restrictSearchWithMatch`: lọc **trong lúc duyệt** và cắt nhánh

Giả sử hệ thống nhân sự chỉ muốn đi qua **nhân viên đang active**, không tiếp tục duyệt các tuyến nằm bên dưới một nút không active. Trong fixture, D inactive nhưng I (cấp dưới của D) active.

Lúc này dùng `restrictSearchWithMatch`:

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "activeDescendants",
      depthField: "level",
      maxDepth: 3,
      restrictSearchWithMatch: {
        active: true
      }
    }
  },
  {
    $project: {
      _id: 0,
      activeIds: "$activeDescendants.employeeId",
      count: { $size: "$activeDescendants" }
    }
  }
])
~~~

Kết quả dự kiến có **7 người**: A, B, C, E, F, G, H; **không có D**, và **không có I** dù I đang active. Lý do: traversal gặp D không thỏa `active: true` nên **không chấp nhận D làm nút để mở rộng tiếp**. Cạnh D → I không được tiếp tục đi theo.

~~~text
CEO
├── A (active)
│   ├── C (active) --> E (active)
│   └── D (INACTIVE) -X-> I (active nhưng không được tới qua D)
└── B (active)
    ├── F (active) --> G (active)
    └── H (active)
~~~

Đây là khác biệt bản chất giữa **lọc trong quá trình duyệt** và **lọc kết quả cuối**.

### 7.1. Lọc sau `$graphLookup` không cắt nhánh

So sánh:

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "everyone",
      depthField: "level",
      maxDepth: 3
    }
  },
  {
    $set: {
      activeOnly: {
        $filter: {
          input: "$everyone",
          as: "person",
          cond: { $eq: ["$$person.active", true] }
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      count: { $size: "$activeOnly" },
      activeIds: "$activeOnly.employeeId"
    }
  }
])
~~~

Trong pipeline này `$graphLookup` đã duyệt cả D và I; chỉ sau đó `$filter` mới bỏ D. Kết quả **8 người**: A, B, C, E, F, G, H, **I**.

| Mục đích | Nên dùng | Vì sao |
|---|---|---|
| “Chỉ được đi qua những người active; dừng ở người inactive.” | `restrictSearchWithMatch:{active:true}` | **Cắt nhánh** khi gặp nút không thỏa. |
| “Đi qua mọi người nhưng chỉ hiển thị những người active.” | `$filter` trên array sau traversal | Có thể vẫn hiển thị **I** dù con đường đi qua D inactive. |
| “Chỉ chọn root CEO nếu CEO active.” | `$match` trước `$graphLookup` | Chỉ lọc document đầu vào, chưa hạn chế mỗi nút ở `from`. |

**Không thay `restrictSearchWithMatch` bằng `$match` sau graph khi nghiệp vụ phụ thuộc việc cắt nhánh.**

### 7.2. Syntax của `restrictSearchWithMatch` là **query filter**, không phải aggregation expression

Hợp lệ:

~~~javascript
restrictSearchWithMatch: {
  active: true,
  department: { $in: ["ENG", "OPS"] }
}
~~~

Không diễn đạt điều kiện field–field như sau rồi kỳ vọng `"$department"` được hiểu là field path:

~~~javascript
// Không thực hiện so sánh với department của input.
restrictSearchWithMatch: {
  department: { $ne: "$department" }
}
~~~

Theo MongoDB Manual, **không dùng aggregation expressions** trong `restrictSearchWithMatch` như cách dùng trong `$expr` của một `$match` thông thường. Chuỗi `"$department"` trong ngữ cảnh này được hiểu là **literal string**, không phải một tham chiếu field động tới document gốc.

### 7.3. Điều kiện có động theo input được không?

`startWith` là aggregation expression nên có thể lấy giá trị **động** từ từng document đầu vào. Trái lại, `restrictSearchWithMatch` không cung cấp cú pháp `let` để đem mọi field của từng input vào một `$expr` tùy ý.

Ví dụ ứng dụng multi-tenant cần chỉ duyệt nhân viên trong tenant hiện tại. Nếu request được xác thực cho tenant T1, có thể truyền một **giá trị literal đã được xác minh** trong filter:

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    as: "descendants",
    maxDepth: 3,
    restrictSearchWithMatch: {
      tenantId: "T1"
    }
  }
}
~~~

Đây là **minh họa cấu trúc** cho dữ liệu có field tenantId; fixture nhân viên ở mục 3 chưa chứa field này, nên muốn chạy demo phải thêm tenantId vào document hoặc tạo collection đa tenant riêng. Giá trị tenant phải lấy từ **ngữ cảnh authorization phía server**, không đơn giản tin input từ client.

Nếu một query phải duyệt **nhiều tenants khác nhau** với điều kiện tenant của từng root, không được giả sử `restrictSearchWithMatch:{tenantId:"$tenantId"}` tự tham chiếu root. Một mô hình an toàn hơn là dùng **composite node key đã bao gồm tenant** (ví dụ `nodeKey` và `parentKey` được chuẩn hóa, có kiểm tra uniqueness), hoặc chạy truy vấn có phạm vi tenant riêng ở backend. Cần kiểm thử tránh ghép cạnh xuyên tenant trước khi triển khai.

### 7.4. Không dùng `restrictSearchWithMatch` như một giới hạn số lượng kết quả

`restrictSearchWithMatch` chọn **loại nút** được mở rộng, không có option “chỉ trả 20 node đầu”. `maxDepth` giới hạn **mức**, không giới hạn **số node**. Nếu graph có fan-out rất lớn, kể cả depth 1 và filter active cũng có thể trả quá nhiều document.

Nếu chỉ muốn hiển thị 20 kết quả đầu:

~~~javascript
{
  $set: {
    top20: {
      $slice: [
        { $sortArray: {
            input: "$descendants",
            sortBy: { level: 1, employeeId: 1 }
        } },
        20
      ]
    }
  }
}
~~~

Đoạn trên **chỉ cắt output sau khi traversal kết thúc**. Nó **không** hạn chế `$graphLookup` phải duyệt 20 nút. Để có một thuật toán “tìm tối đa N nút rồi dừng ngay”, `$graphLookup` không cung cấp một tham số `maxNodes` tổng quát; cần thiết kế giới hạn từ mô hình dữ liệu/ứng dụng, hoặc chọn chiến lược truy vấn khác.

## 8. Mở rộng từ nhiều điểm khởi đầu và nhiều cạnh

`$graphLookup` không giới hạn ở cây “một người có một quản lý”. Nếu mỗi nút có **array các liên kết**, có thể mô hình hóa graph nhiều–nhiều.

### 8.1. Sơ đồ tuyến sân bay

~~~text
HAN --> DAD --> CXR
 |       |
 |       +--> HAN (chu trình)
 v
SGN --> CXR
 | 
 +----> PQC
~~~

Tạo collection thứ hai, độc lập với `employees`:

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

lab.airports.insertMany([
  {
    _id: "AP-HAN",
    airport: "HAN",
    connects: ["DAD", "SGN"]
  },
  {
    _id: "AP-DAD",
    airport: "DAD",
    connects: ["CXR", "HAN"]
  },
  {
    _id: "AP-SGN",
    airport: "SGN",
    connects: ["CXR", "PQC"]
  },
  {
    _id: "AP-CXR",
    airport: "CXR",
    connects: ["HAN"]
  },
  {
    _id: "AP-PQC",
    airport: "PQC",
    connects: []
  }
])

lab.airports.createIndex(
  { airport: 1 },
  { unique: true, name: "ux_airport" }
)

lab.travelers.insertOne({
  _id: "TR-1",
  displayName: "Khách A",
  nearestAirport: "HAN"
})
~~~

### 8.2. Một traveler duyệt các tuyến từ sân bay gần nhất

~~~javascript
lab.travelers.aggregate([
  { $match: { _id: "TR-1" } },
  {
    $graphLookup: {
      from: "airports",
      startWith: "$nearestAirport",
      connectFromField: "connects",
      connectToField: "airport",
      as: "reachable",
      maxDepth: 2,
      depthField: "hops"
    }
  },
  {
    $set: {
      reachable: {
        $sortArray: {
          input: "$reachable",
          sortBy: { hops: 1, airport: 1 }
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      nearestAirport: 1,
      "reachable.airport": 1,
      "reachable.hops": 1
    }
  }
])
~~~

Các nút duyệt được trong fixture:

| `hops` | Sân bay |
|---:|---|
| 0 | HAN (lượt tra cứu đầu khớp `nearestAirport`) |
| 1 | DAD, SGN |
| 2 | CXR, PQC |

**Đặc biệt:** Ở mô hình này, `startWith` có giá trị `"HAN"` và `connectToField:"airport"` nên **HAN có trong array `reachable` với hops 0**. Nếu màn hình chỉ muốn *sân bay khác* mà khách có thể đến, hãy loại HAN khỏi phần hiển thị sau traversal, hoặc thiết kế startWith/đường cạnh theo ngữ nghĩa phù hợp.

### 8.3. Điều kiện mảng trong `connectFromField`

Với nút HAN, `connects:["DAD","SGN"]` có hai phần tử. MongoDB dùng **cả DAD và SGN** để tìm document có `airport` trùng ở lượt kế tiếp. Sau đó nó lấy `connects` của DAD và SGN để tiếp tục. Không cần tự `$unwind` connects trước mỗi bước.

### 8.4. Bắt đầu từ nhiều sân bay

Thêm document input:

~~~javascript
lab.travelers.insertOne({
  _id: "TR-2",
  displayName: "Khách B",
  nearestAirports: ["HAN", "SGN"]
})
~~~

Truy vấn:

~~~javascript
lab.travelers.aggregate([
  { $match: { _id: "TR-2" } },
  {
    $graphLookup: {
      from: "airports",
      startWith: "$nearestAirports",
      connectFromField: "connects",
      connectToField: "airport",
      as: "reachable",
      depthField: "hops",
      maxDepth: 1
    }
  }
])
~~~

`startWith` là array nên lượt tra cứu đầu tiên xét **HAN và SGN**. Không suy rằng “traversal từ một phần tử xong mới chuyển phần tử khác” hay output sẽ sắp theo thứ tự mảng input. Với graph nhiều điểm xuất phát/nhiều đường tới cùng nút, `depthField` là thông tin độ sâu traversal, **không phải một bản ghi từng tuyến đường đi qua**.

## 9. Chu trình, nút lặp và đồ thị không phải cây

Một graph có thể có **chu trình**: A → B → C → A. Nếu ứng dụng tự duyệt bằng while-loop không lưu tập nút đã thăm, nó có thể chạy vô hạn. `$graphLookup` theo cơ chế traversal đồ thị, tránh việc lặp mãi trên cùng nút được duyệt. Tuy nhiên, vẫn nên **giới hạn độ sâu và số nút hợp lý** để tránh tài nguyên bị tiêu thụ quá lớn ở graph có nhiều nhánh.

### 9.1. Một cycle fixture riêng

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

lab.cycleNodes.insertMany([
  { _id: "A", nodeId: "A", links: ["B"] },
  { _id: "B", nodeId: "B", links: ["C"] },
  { _id: "C", nodeId: "C", links: ["A", "D"] },
  { _id: "D", nodeId: "D", links: [] }
])

lab.cycleRoots.insertOne({
  _id: "ROOT-A",
  initialNode: "A"
})

lab.cycleNodes.createIndex(
  { nodeId: 1 },
  { unique: true }
)

lab.cycleRoots.aggregate([
  { $match: { _id: "ROOT-A" } },
  {
    $graphLookup: {
      from: "cycleNodes",
      startWith: "$initialNode",
      connectFromField: "links",
      connectToField: "nodeId",
      as: "reachable",
      depthField: "hops",
      maxDepth: 4
    }
  },
  {
    $project: {
      _id: 1,
      "reachable.nodeId": 1,
      "reachable.hops": 1
    }
  }
])
~~~

Reachable nodes là **A, B, C, D**; cạnh C → A không làm array chứa A vô hạn lần. Trên dữ liệu chuẩn có một document cho mỗi `nodeId`, các nút được duyệt không bị nhân thành một bản sao cho mỗi lần chu trình quay lại.

### 9.2. Cycle prevention ở tầng dữ liệu vẫn cần thiết

Việc `$graphLookup` không lặp vô hạn **không có nghĩa dữ liệu quan hệ vòng là hợp lệ**. Với sơ đồ nhân sự, A quản lý B và B lại quản lý A là lỗi nghiệp vụ, dù query có thể kết thúc.

Khi cập nhật `managerId`, ứng dụng có thể cần:

1. Bảo đảm người quản lý tồn tại và thuộc cùng tenant/organization.
2. Không cho một nhân viên quản lý chính mình.
3. Không cho đổi manager thành một **hậu duệ** của nhân viên, vì sẽ tạo cycle.
4. Chống race khi hai client cập nhật các cạnh cùng lúc; transaction hoặc versioning có thể cần nếu bất biến spanning documents quan trọng.
5. Có bước kiểm tra/khắc phục graph sai do import hoặc migration.

`$graphLookup` có thể hỗ trợ **phát hiện khả năng gây cycle** khi kiểm tra hậu duệ, nhưng một truy vấn kiểm tra rồi một update riêng rẽ không mặc nhiên nguyên tử với các writers khác. MongoDB không tự thực thi ràng buộc “một cây không có cycle” chỉ bằng `$graphLookup`.

### 9.3. Khi hai đường dẫn hội tụ

Trong graph nhiều–nhiều, một nút D có thể được đi tới qua A → B → D và A → C → D. `$graphLookup` trả **các document có thể tới**, không trả riêng một bản sao D cho mỗi tuyến đường. Vì thế:

- Không dùng `$size:"$reachable"` để đếm số **đường đi**.
- Không coi `depthField` là **một danh sách các edge**.
- Không giả định có đủ dữ liệu trong output để dựng **mọi** đường đi, nhất là khi có nhiều đường dẫn tới cùng đỉnh.
- Nếu cần tối ưu theo trọng số, đường đi rẻ nhất hoặc số tuyến đường, cân nhắc thuật toán graph chuyên dụng hoặc mô hình dữ liệu dẫn xuất ngoài `$graphLookup`.

### 9.4. Tham chiếu thiếu, trùng mã và null

`connectToField` nên có **giá trị khóa ổn định** phù hợp với mô hình quan hệ. Trong fixture nhân viên, `employeeId` duy nhất và `managerId` của CEO null; một nút tham chiếu `managerId:"UNKNOWN"` sẽ không đi tiếp nếu không có nhân viên tương ứng.

Nếu nhiều document cùng có một giá trị `connectToField`, một edge có thể khớp **nhiều nút**, tăng fan-out và khiến kết quả khác ý định. Dùng unique index trên khóa ID khi domain yêu cầu. Với field missing/null, quan hệ bình thường có thể bị tạo ra do BSON equality semantics không mong muốn; nên thiết kế **khóa bắt buộc đúng kiểu** và tránh để `startWith`/`connectFromField` phát sinh null vô ý.

## 10. Index cho `$graphLookup`: tối ưu từng bước tìm cạnh

`$graphLookup` thực hiện nhiều lượt match trong collection `from`. Để traversal không phải quét collection cho mỗi vòng mở rộng, **index trên `connectToField` của quan hệ đang đi** là một trong những công cụ quan trọng nhất.

### 10.1. Hướng hậu duệ cần index nào?

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    as: "descendants",
    maxDepth: 3
  }
}
~~~

Mỗi bước phải tìm các document có:

~~~javascript
{ managerId: "ID-của-nút-hiện-tại" }
~~~

Vì vậy index ứng viên là:

~~~javascript
lab.employees.createIndex(
  { managerId: 1 },
  { name: "ix_managerId" }
)
~~~

Index này hỗ trợ tra con trực tiếp ở **mỗi cấp**. Điều đó có ý nghĩa lớn nếu graph có hàng triệu nodes nhưng mỗi node chỉ có vài con. Không phải MongoDB sẽ tự chạy một query find riêng qua mạng cho mỗi nút; traversal được tổ chức bên trong stage server, nhưng việc tra chỉ mục trên collection `from` vẫn là vấn đề cốt lõi.

### 10.2. Hướng tổ tiên lại cần index khác

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$managerId",
    connectFromField: "managerId",
    connectToField: "employeeId",
    as: "ancestors"
  }
}
~~~

Mỗi lượt tìm người quản lý theo:

~~~javascript
{ employeeId: "ID-người-quản-lý-đang-cần-tìm" }
~~~

Nên index trên `employeeId`, tốt nhất là **unique** nếu mô hình yêu cầu mỗi employeeId chỉ ứng với một document:

~~~javascript
lab.employees.createIndex(
  { employeeId: 1 },
  { unique: true, name: "ux_employeeId" }
)
~~~

Đảo chiều traversal mà giữ nguyên index trên `managerId` có thể khiến mỗi lượt tìm manager không sử dụng được index ứng viên tốt nhất. Hãy đọc chính xác **`connectToField`** trong pipeline trước khi chọn index.

### 10.3. Kết hợp index với `restrictSearchWithMatch`

Nếu chỉ duyệt nút active:

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    restrictSearchWithMatch: { active: true },
    as: "activeDescendants",
    maxDepth: 3
  }
}
~~~

Một compound index có thể là ứng viên:

~~~javascript
lab.employees.createIndex(
  { managerId: 1, active: 1 },
  { name: "ix_managerId_active" }
)
~~~

Với mỗi lượt tìm `managerId` cụ thể và `active:true`, index có thể giúp giới hạn cả quan hệ lẫn trạng thái. Nhưng:

- Nếu hầu hết nhân viên đều active, thành phần `active` có thể ít giúp thêm.
- Nếu application nhiều nơi chỉ lọc theo `managerId`, index đơn `{managerId:1}` có thể đã đủ.
- Index compound tăng chi phí ghi và dung lượng.
- Planner/engine có thể chọn index khác tùy thống kê và phiên bản.

Không tạo hai index chỉ vì một ví dụ; đo workload traversal thật và cân đối chi phí.

### 10.4. Lọc root trước khi duyệt

Truy vấn sau có thể thực hiện traversal cho **mọi document trong employees**:

~~~javascript
lab.employees.aggregate([
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      maxDepth: 2
    }
  }
])
~~~

Nếu collection có hàng triệu nhân viên, stage sẽ tạo **một kết quả traversal cho mỗi nhân viên**. Điều đó rất khác với chỉ tính cây dưới CEO. Khi API chỉ cần một root, đặt `$match` **trước `$graphLookup`**:

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      maxDepth: 2
    }
  }
])
~~~

`$match` trên root có thể dùng index `ux_employeeId`, và chỉ **một input document** đi vào `$graphLookup`. Index trên **root filter** và index trên **connectToField của collection `from`** phục vụ **hai pha khác nhau**.

### 10.5. `$limit` trước và sau traversal

~~~javascript
// Chọn tối đa 10 roots trước khi traversal:
[
  { $match: { department: "ENG" } },
  { $sort: { employeeId: 1 } },
  { $limit: 10 },
  { $graphLookup: { /* ... */ } }
]
~~~

Stage này giới hạn **số root cần duyệt**. Ngược lại:

~~~javascript
[
  { $match: { department: "ENG" } },
  { $graphLookup: { /* ... */ } },
  { $limit: 10 }
]
~~~

không thể suy ra chỉ 10 root được tính traversal; `$limit` phía sau **không phải giới hạn sâu/nút** của `$graphLookup`. Khi hiển thị pagination, phải xác định **đang phân trang root hay phân trang các nút con**, vì đó là hai bài toán khác nhau.

### 10.6. Lựa chọn index cho graph nhiều tenant

Với mô hình đa tenant, query thường cần `tenantId` cùng khóa quan hệ. Nếu một tenant có nhiều nodes:

~~~javascript
// Minh họa index cho collection có field tenantId:
lab.employees.createIndex(
  { tenantId: 1, managerId: 1 },
  { name: "ix_tenant_manager" }
)
~~~

Index này không mặc nhiên thay thế được `{managerId:1}` trong mọi `$graphLookup` vì predicate traversal có thể chỉ dùng `managerId`. Nếu `restrictSearchWithMatch` có `tenantId` literal xác thực, index compound có cơ hội được dùng phù hợp. Cần xem **exact query shape** và explain thay vì suy từ việc “index gồm cả hai field”.

Nếu mô hình bảo mật không cho phép truy cập chéo tenant, **index không phải ràng buộc phân quyền**. Cần encode tenant identity vào cạnh hoặc áp dụng filter được xác thực và kiểm tra dữ liệu; xem phần thiết kế multi-tenant.

## 11. Đọc `explain` và theo dõi traversal

Với aggregation, có thể gọi:

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

const pipeline = [
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      maxDepth: 2,
      depthField: "level"
    }
  },
  {
    $project: {
      _id: 0,
      employeeId: 1,
      count: { $size: "$descendants" }
    }
  }
]

printjson(
  lab.employees.explain("executionStats").aggregate(pipeline)
)
~~~

Hãy quan sát execution plan của **phép chọn root** và thống kê liên quan `$graphLookup`. Tùy phiên bản, thông tin stage có thể xuất hiện ở các vị trí khác nhau trong cấu trúc explain.

### 11.1. Các thông tin đáng quan sát

| Thông tin | Câu hỏi cần trả lời |
|---|---|
| `IXSCAN` hoặc `COLLSCAN` ở đầu | Root `employeeId:"CEO"` được chọn bằng index hay scan? |
| `indexesUsed` (nếu stage có báo cáo) | Traversal dùng index nào trên collection `from`? |
| `totalDocsExamined`, `totalKeysExamined` | Mức quét trong phần xử lý được báo cáo có phù hợp số nút trả về không? |
| `collectionScans` trong stage (nếu có) | Có đang quét collection lặp lại trong traversal không? |
| `executionTimeMillisEstimate`/thời gian (nếu có) | Stage đệ quy tốn bao lâu theo thống kê engine? |
| `usedDisk`/`spills` (khi hỗ trợ) | Có spill hoặc áp lực bộ nhớ không? |
| Số root/size output | Có đang chạy traversal cho nhiều root quá mức cần thiết không? |

Cấu trúc explain khác giữa classic engine, SBE, bản MongoDB và pipeline shape. Không dựa vào một đường JSON cố định để đọc thống kê mọi phiên bản.

### 11.2. Một `IXSCAN` chưa chứng minh traversal tối ưu

Nếu explain có `IXSCAN` của root `employeeId:"CEO"` nhưng traversal trên `managerId` lại không có index phù hợp, tổng truy vấn vẫn có thể chậm. Ngược lại, nếu collection chỉ có mười nhân viên như fixture, việc planner chọn scan có thể rẻ hơn. Đánh giá trên graph đủ lớn, với **fan-out và độ sâu đại diện**, chứ không lấy thời gian của demo mười document làm benchmark.

### 11.3. Đo biến động theo độ sâu

Có thể dùng cùng một pipeline với `maxDepth:0`, `1`, `2`, `3` để quan sát:

~~~javascript
for (const depth of [0, 1, 2, 3]) {
  const result = lab.employees.aggregate([
    { $match: { employeeId: "CEO" } },
    {
      $graphLookup: {
        from: "employees",
        startWith: "$employeeId",
        connectFromField: "employeeId",
        connectToField: "managerId",
        as: "descendants",
        maxDepth: depth
      }
    },
    {
      $project: {
        _id: 0,
        depthLimit: { $literal: depth },
        count: { $size: "$descendants" }
      }
    }
  ]).toArray()

  printjson(result)
}
~~~

Trên fixture, các counts là **2, 6, 9, 9**. Trong production, số nút có thể tăng theo cấp số nhân ở những cây phân nhánh lớn. Vòng lặp này là **thí nghiệm kiểm soát**, không phải lý do để chạy nhiều truy vấn sâu cùng lúc trên hệ thống đang quá tải.

### 11.4. Kiểm soát thời gian truy vấn

`aggregate()` hỗ trợ tùy chọn `maxTimeMS`:

~~~javascript
lab.employees.aggregate(
  [
    { $match: { employeeId: "CEO" } },
    {
      $graphLookup: {
        from: "employees",
        startWith: "$employeeId",
        connectFromField: "employeeId",
        connectToField: "managerId",
        as: "descendants",
        maxDepth: 3
      }
    }
  ],
  { maxTimeMS: 5000 }
)
~~~

`maxTimeMS` đặt một giới hạn thời gian xử lý mà server có thể ngắt khi vượt; đây là **biện pháp bảo vệ** chứ không phải bảo đảm truy vấn luôn trả đầy đủ trong 5 giây. Nếu quá thời gian, ứng dụng cần xử lý lỗi timeout và quyết định có giảm độ sâu/phạm vi hay không, không retry vô hạn cùng pipeline đắt tiền.

## 12. Giới hạn bộ nhớ, kích thước kết quả và phiên bản

`$graphLookup` có thể mở rộng một tập document rất lớn và gắn chúng vào **một array trên mỗi root**. Vì vậy cần cân nhắc hai loại giới hạn riêng:

1. **Tài nguyên thực thi traversal** — bộ nhớ, disk spill theo phiên bản, I/O, CPU, số lượt truy vấn và thời gian.
2. **Kích thước document trả về** — mỗi document kết quả của aggregation phải đáp ứng giới hạn **16 MiB BSON**.

### 12.1. Điều phải kiểm tra theo dòng MongoDB

Tài liệu chính thức thay đổi giữa các dòng:

| Dòng tài liệu | `$graphLookup` và bộ nhớ |
|---|---|
| **MongoDB 7.0/8.0** | Trang `$graphLookup` mô tả giới hạn **100 MB**; `allowDiskUse:true` **không làm stage này vượt giới hạn** (option vẫn có thể áp dụng cho stage khác trong pipeline). |
| **Database Manual hiện hành** | Trang `$graphLookup` mô tả stage vượt **100 MB** có thể ghi temporary files ra đĩa khi được phép; với `allowDiskUse:false` thì trả lỗi nếu vượt. |

Không sử dụng một kết luận duy nhất “`$graphLookup` luôn spill” hoặc “`$graphLookup` không bao giờ spill” mà bỏ qua **server version**. Cần tra trang documentation **của phiên bản đang dùng**, kiểm tra `explain("executionStats")` và quan sát usedDisk/spill khi load test phù hợp.

Ngoài ra, từ MongoDB 9.0 có **giới hạn bộ nhớ theo toàn operation** bên cạnh giới hạn từng stage; đó là một tầng kiểm soát khác. Không nên dựa vào việc có disk spill để triển khai traversal không giới hạn.

### 12.2. `allowDiskUse` không thay thế thiết kế graph

Ví dụ đặt tùy chọn:

~~~javascript
lab.employees.aggregate(
  [
    { $match: { employeeId: "CEO" } },
    {
      $graphLookup: {
        from: "employees",
        startWith: "$employeeId",
        connectFromField: "employeeId",
        connectToField: "managerId",
        as: "descendants",
        maxDepth: 3
      }
    }
  ],
  { allowDiskUse: true }
)
~~~

Trên MongoDB 7.0/8.0, theo trang `$graphLookup` tương ứng, **không được trông đợi option này vượt giới hạn 100 MB của chính stage `$graphLookup`**. Trên dòng hiện hành có hỗ trợ spill của graphLookup, ghi ra đĩa vẫn gây chi phí I/O và không cứu được việc kết quả quá lớn để trả về.

### 12.3. Array kết quả quá lớn và giới hạn 16 MiB

Nếu một root có 200.000 descendants, mỗi descendant chứa rất nhiều field, array `as` có thể trở thành document output quá lớn. Một `$project` sau traversal có thể giảm các field được trả ra, nhưng **không làm traversal ban đầu tự duyệt ít nút hơn**; những giới hạn memory trong quá trình xử lý vẫn tồn tại.

Những giải pháp thiết kế:

- Giới hạn `maxDepth` theo yêu cầu thực tế.
- Dùng `restrictSearchWithMatch` để **cắt các nhánh không cần thiết** khi đúng nghiệp vụ.
- Chọn **ít root** bằng `$match`/`$limit` trước traversal.
- Lưu collection graph với **node documents gọn**, tách dữ liệu chi tiết lớn sang collection khác.
- Nếu API chỉ cần **trang con trực tiếp**, dùng query `find({managerId:...})` có index thay vì duyệt toàn cây.
- Cân nhắc **materialized path**, bảng tổ tiên/hậu duệ, cache hoặc tính toán ngoài MongoDB cho traversal cực lớn/lặp lại thường xuyên.

### 12.4. `$project`/`$slice` không phải giới hạn traversal

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  { $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants"
  } },
  { $project: {
      descendants: { $slice: ["$descendants", 10] }
  } }
])
~~~

Stage cuối chỉ cắt **array output**. Nó không bảo MongoDB “đừng duyệt quá 10 nút”. Nếu graph rất lớn, phần nặng nhất có thể đã xảy ra trước đó. Hơn nữa, khi không sort, “10 nút đầu” trong array không có thứ tự được bảo đảm.

### 12.5. Thiết kế giới hạn theo nghiệp vụ

Không phải graph nào cũng cần đi sâu:

| Nhu cầu | Giới hạn hợp lý để bắt đầu |
|---|---|
| Hiển thị quản lý trực tiếp | Query một cấp / `maxDepth:0`. |
| Sơ đồ hai tầng dưới một quản lý | `maxDepth:1`. |
| Phân quyền theo tối đa ba tầng tổ chức | `maxDepth:2` cùng kiểm soát tenant/active. |
| Báo cáo tất cả descendants | Cân nhắc unbounded graph, fan-out, memory và phương án precompute. |
| Tìm bạn bè cách tối đa hai cạnh | `maxDepth` theo cách chọn seed; chú ý depth 0. |
| Đếm mọi đường đi khác nhau giữa hai nút | `$graphLookup` một mình không giải quyết trực tiếp. |

Điều quan trọng là **định nghĩa số bước theo kết quả mong muốn**, không chọn độ sâu chỉ để tránh timeout rồi trả kết quả thiếu mà không thông báo.

## 13. `$graphLookup` trên sharded collection, view và transaction

### 13.1. `from` là collection trong **cùng database**

`$graphLookup` dùng:

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    as: "descendants"
  }
}
~~~

`from:"employees"` là **tên collection trong cùng database** với aggregation; không phải một URL hoặc namespace tùy ý trỏ sang database khác. Nếu input là `lab.roots` và `from:"employees"`, cả `roots` và `employees` cần thuộc database `graph_lookup_lab`.

Ví dụ hai collection:

~~~javascript
const lab = db.getSiblingDB("graph_lookup_lab")

lab.roots.insertOne({
  _id: "R-ENG",
  rootEmployeeId: "A",
  title: "Sơ đồ khối kỹ thuật"
})

lab.roots.aggregate([
  { $match: { _id: "R-ENG" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$rootEmployeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "members",
      maxDepth: 2,
      depthField: "level"
    }
  },
  {
    $project: {
      title: 1,
      memberIds: "$members.employeeId",
      memberCount: { $size: "$members" }
    }
  }
])
~~~

Root A có bốn hậu duệ trong fixture: C, D, E, I (C/D ở depth 0, E/I ở depth 1). Nếu dùng `restrictSearchWithMatch:{active:true}`, chỉ còn C và E vì D inactive và I nằm dưới D.

### 13.2. Hỗ trợ sharded collection từ MongoDB 5.1

Từ MongoDB **5.1**, `$graphLookup` cho phép collection `from` là **sharded collection**. Trước đó, giới hạn hỗ trợ khác nên không áp dụng câu khẳng định 5.1+ cho server cũ.

Hệ quả khi triển khai:

- Traversal có thể liên quan đến **nhiều shard**, tăng độ trễ và công việc mạng/merge.
- Index trên `connectToField` và **shard-key-aware data model** vẫn quan trọng, nhưng một index không tự bảo đảm mọi lượt tìm được gửi tới đúng một shard.
- Nếu các cạnh không mang key phù hợp với routing, server có thể cần tìm trên nhiều shard.
- Phải đo `explain`/profiler của deployment sharded thực tế; fixture một collection nhỏ không phản ánh chi phí fan-out.

### 13.3. Giới hạn transaction với sharded `from`

Theo MongoDB Database Manual: **không thể dùng `$graphLookup` trong một transaction khi stage nhắm vào một sharded collection ở `from`**. Đây là giới hạn rõ ràng, kể cả trên các dòng MongoDB mới hỗ trợ sharded `from`.

Không suy rằng vì `$lookup` hoặc aggregation nói chung có thể chạy trong một số transaction thì mọi `$graphLookup` cũng được hỗ trợ trong transaction sharded. Nếu nghiệp vụ bắt buộc snapshot/atomic consistency, cần thiết kế luồng dữ liệu hoặc giải pháp khác phù hợp với giới hạn deployment.

### 13.4. View và collation

Khi aggregation liên quan nhiều **views** thông qua `$graphLookup` (hoặc `$lookup`), các views cần có **collation tương thích/giống nhau** theo tài liệu MongoDB. Collation cũng ảnh hưởng việc đối chiếu các giá trị chuỗi trong quan hệ.

Nếu ID node là chuỗi và ứng dụng phân biệt `"A"` với `"a"`, hãy xác định rõ collation/canonical ID. Một graph dùng node keys không thống nhất chữ hoa/thường có thể tạo kết quả khác dự kiến hoặc match nhầm giữa các ID tưởng là khác nhau.

### 13.5. Dữ liệu có thể thay đổi trong khi duyệt

Một `$graphLookup` có thể chạy trên collection mà ứng dụng đang cập nhật manager links hoặc trạng thái active. Nếu nghiệp vụ đòi một **ảnh chụp nhất quán mạnh** của toàn cây trong khi nhiều writer thay đổi, cần xem read concern/transaction semantics và hạn chế sharding; đừng mặc định một aggregation đệ quy tự khóa toàn bộ graph để các cạnh không đổi.

Một số hệ thống duy trì **graphVersion** hoặc xuất bản snapshot cây tổ chức sau khi thay đổi đã được duyệt; kết quả UI đọc theo một phiên bản xác định. Đó là phương án kiến trúc khi tính nhất quán toàn quan hệ quan trọng hơn việc tính graph trực tiếp ở mọi request.

## 14. Mô hình dữ liệu phù hợp với truy vấn graph

### 14.1. Adjacency list: đơn giản và linh hoạt

Mô hình fixture dùng:

~~~javascript
{ employeeId: "G", managerId: "F" }
~~~

Đây là **adjacency list**: mỗi nút lưu liên kết trực tiếp tới nút lân cận/cha. Ưu điểm:

- Ghi/sửa manager trực tiếp khá đơn giản.
- Không phải cập nhật danh sách toàn bộ tổ tiên khi di chuyển một nhánh.
- Truy vấn một cấp bằng index `{managerId:1}` hiệu quả.
- `$graphLookup` có thể truy vấn nhiều cấp khi cần.

Nhược điểm:

- Truy vấn toàn bộ subtree sâu và rộng có thể tốn tài nguyên.
- Kiểm tra cycle/phân quyền theo cả cây phải được thiết kế riêng.
- Các báo cáo lặp lại thường xuyên có thể lặp cùng traversal nhiều lần.

### 14.2. Materialized path

Một hướng khác lưu đường dẫn từ root tới node:

~~~javascript
{
  employeeId: "G",
  managerId: "F",
  ancestorPath: ["CEO", "B", "F"]
}
~~~

Để tìm những nodes dưới B, có thể truy vấn theo `ancestorPath` nếu array/path được thiết kế và index phù hợp. Phương án này giúp một số truy vấn đọc descendants/tổ tiên đơn giản, nhưng khi chuyển một nhánh sang manager khác, phải **cập nhật đường dẫn dẫn xuất của toàn bộ các descendants**, làm tăng chi phí ghi và nguy cơ nhất quán.

### 14.3. Ancestor/closure collection

Một mô hình khác lưu các cặp quan hệ:

~~~javascript
{
  ancestorId: "CEO",
  descendantId: "G",
  distance: 3
}
~~~

Với **closure table** kiểu MongoDB, truy vấn descendants có thể thực hiện bằng `find({ancestorId:"CEO"})`, và khoảng cách đã được lưu. Nhưng ứng dụng phải duy trì tất cả các cặp phù hợp khi thêm/xóa/di chuyển cạnh. Mô hình này tốt nếu **đọc cây cực thường xuyên, thay đổi cấu trúc hiếm** và có quy trình cập nhật nhất quán.

### 14.4. Embedded subtree

Có thể nhúng một phần cây nhỏ bên trong document root khi cardinality có giới hạn và thường được đọc cùng lúc. Nhưng nếu cây mở rộng không giới hạn hoặc nhiều writers cập nhật những nhánh độc lập, document root có thể trở thành **hot document** và gặp giới hạn 16 MiB. Không chọn embedding toàn bộ graph chỉ để tránh `$graphLookup` mà bỏ qua fan-out và tốc độ tăng trưởng.

### 14.5. Bảng chọn theo access pattern

| Nhu cầu chính | Mô hình/cách truy vấn thường phù hợp | Đánh đổi |
|---|---|---|
| Chỉ xem quản lý trực tiếp | Adjacency list + `find`/`$lookup` một cấp. | Đơn giản, không cần đệ quy. |
| Tìm descendants trong vài tầng | Adjacency list + `$graphLookup` có `maxDepth`. | Phụ thuộc fan-out và index. |
| Tìm ancestors theo chuỗi ngắn | Adjacency list + `$graphLookup` hướng lên. | Cần đúng khóa và dừng ở root. |
| Hiển thị toàn bộ tổ chức rất lớn thường xuyên | Cache/materialized graph/closure collection. | Phức tạp hóa cập nhật và invalidation. |
| Quan hệ nhiều–nhiều có vòng | Array edges + `$graphLookup` cho reachability. | Không tự trả shortest weighted path/mọi đường. |
| Đếm đường đi, tối ưu trọng số | Thuật toán graph riêng hoặc cấu trúc chuyên biệt. | Cần thêm computation ngoài `$graphLookup`. |
| Phân quyền theo cây đa tenant | Kiểm tra tenant, cycle, constraints, snapshot. | Không chỉ là một traversal; phải phòng cross-tenant edges. |

## 15. Ví dụ triển khai bằng MongoDB Java Sync Driver

MongoDB Java Sync Driver hỗ trợ aggregation pipelines bằng `List<Bson>`. Để minh họa chính xác cấu trúc `$graphLookup`, có thể tạo stage bằng `org.bson.Document`; server vẫn nhận BSON tương đương với lệnh `mongosh`.

### 15.1. Duyệt hậu duệ trong Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static com.mongodb.client.model.Aggregates.match;
import static com.mongodb.client.model.Filters.eq;

// database là MongoDatabase đã trỏ tới "graph_lookup_lab".
MongoCollection<Document> employees = database.getCollection("employees");

Document graphLookupConfig = new Document("from", "employees")
    .append("startWith", "$employeeId")
    .append("connectFromField", "employeeId")
    .append("connectToField", "managerId")
    .append("as", "descendants")
    .append("maxDepth", 2)
    .append("depthField", "level")
    .append(
        "restrictSearchWithMatch",
        new Document("active", true)
    );

Bson graphLookupStage = new Document("$graphLookup", graphLookupConfig);

List<Bson> pipeline = Arrays.asList(
    match(eq("employeeId", "CEO")),
    graphLookupStage
);

employees.aggregate(pipeline)
    .maxTime(5, TimeUnit.SECONDS)
    .forEach(doc -> System.out.println(doc.toJson()));
~~~

Với fixture, pipeline chỉ đi qua các nút active, nên trả **7 descendants** (D inactive bị loại, I bên dưới D cũng không được duyệt). `maxTime(5, TimeUnit.SECONDS)` là tùy chọn về thời gian chờ xử lý server theo driver API; nó không thay thế việc giới hạn depth và index.

### 15.2. Duyệt tổ tiên trong Java

Chỉ đổi ba field biểu diễn chiều duyệt:

~~~java
Document ancestorsConfig = new Document("from", "employees")
    .append("startWith", "$managerId")
    .append("connectFromField", "managerId")
    .append("connectToField", "employeeId")
    .append("as", "ancestors")
    .append("maxDepth", 2)
    .append("depthField", "level");

List<Bson> ancestorsPipeline = Arrays.asList(
    match(eq("employeeId", "G")),
    new Document("$graphLookup", ancestorsConfig)
);

employees.aggregate(ancestorsPipeline)
    .forEach(doc -> System.out.println(doc.toJson()));
~~~

Kết quả có F, B, CEO ở các mức 0, 1, 2. Dùng `Document` để biểu diễn stage giúp dễ đối chiếu với MongoDB Manual; tùy driver version cũng có aggregation builders chuyên biệt mà bạn có thể dùng sau khi kiểm tra API và generic types tương ứng.

### 15.3. Chặn depth không hợp lệ từ request

Không nhận vô điều kiện một `maxDepth` cực lớn từ URL/query parameter. Trong service Java:

~~~java
int requestedDepth = 2; // Ví dụ do service nhận từ request.
int allowedMaximum = 4; // Quy tắc của endpoint.

if (requestedDepth < 0 || requestedDepth > allowedMaximum) {
    throw new IllegalArgumentException(
        "depth must be between 0 and " + allowedMaximum
    );
}

Document config = new Document("from", "employees")
    .append("startWith", "$employeeId")
    .append("connectFromField", "employeeId")
    .append("connectToField", "managerId")
    .append("as", "descendants")
    .append("maxDepth", requestedDepth);
~~~

Đây là **giới hạn phía ứng dụng**, không phải quy tắc MongoDB “maxDepth tối đa 4”. Có thể chọn mức khác dựa trên fan-out và SLO, nhưng phải tính từ nghiệp vụ và đo tải thật.

### 15.4. Kết hợp root filter, restrict và tenant

Nếu ứng dụng dùng nhiều tenant, không lấy `tenantId` từ request một cách không xác thực rồi đưa vào filter graph. Có thể kết hợp:

~~~java
String authorizedTenantId = "T1"; // Lấy từ authorization đã xác minh.
String requestedEmployeeId = "CEO";

List<Bson> scopedPipeline = Arrays.asList(
    match(new Document("employeeId", requestedEmployeeId)
        .append("tenantId", authorizedTenantId)),
    new Document("$graphLookup",
        new Document("from", "employees")
            .append("startWith", "$employeeId")
            .append("connectFromField", "employeeId")
            .append("connectToField", "managerId")
            .append("as", "descendants")
            .append("maxDepth", 3)
            .append("restrictSearchWithMatch",
                new Document("tenantId", authorizedTenantId)
                    .append("active", true)))
);
~~~

Đây là pattern cho **collection có tenantId**, không chạy ra dữ liệu trên fixture mục 3 nếu chưa bổ sung field tenantId. Việc truyền cùng tenant scope cho **root** và **from nodes** giúp biểu diễn ý định. Tuy nhiên, để không ghép nhầm hai nhân viên cùng `employeeId` giữa các tenants, **khóa liên kết cần unique theo tenant** hoặc dùng composite node ID; chỉ dùng index toàn cục không phù hợp có thể chặn hoặc mở nhầm quan hệ.

### 15.5. Spring Data MongoDB

Spring Data có các abstraction cho aggregation; cách xây stage `$graphLookup` và kiểu builder có thể khác giữa phiên bản framework. Nếu dự án không có builder đủ option, có thể định nghĩa một `AggregationOperation` trả một BSON `Document` với `$graphLookup`. Dù qua API nào, các trường server nhận vẫn phải có:

~~~javascript
{
  from: "employees",
  startWith: "$employeeId",
  connectFromField: "employeeId",
  connectToField: "managerId",
  as: "descendants",
  maxDepth: 2,
  depthField: "level"
}
~~~

Khi dự án dùng entity field mapping, hãy kiểm tra field name được serialize có thực sự là `employeeId`/`managerId` trong BSON hay đã bị đổi bởi annotations/converters. Đừng chỉ nhìn tên thuộc tính Java rồi suy ra `connectToField` đúng.

## 16. Những lỗi thường gặp khi dùng `$graphLookup`

| Cách hiểu/cách làm dễ sai | Vấn đề | Hướng đúng |
|---|---|---|
| “`$graphLookup` chỉ giống `$lookup`, không khác gì join.” | `$graphLookup` **đi đệ quy**, có cost và giới hạn riêng. | Dùng `$lookup` cho một cấp nếu không cần recursion. |
| “`startWith` phải là tên một field.” | `startWith` là **aggregation expression**, có thể là field path, literal hoặc array expression. | Xác định giá trị đầu tiên thật sự được evaluate. |
| “`connectFromField` là field đem so sánh, `connectToField` là field lấy cho bước kế.” | Hai field bị đảo ngược. | **Match trên connectTo**, rồi **lấy connectFrom** để mở rộng. |
| “Đi xuống và đi lên chỉ cần thay `startWith`.” | Hướng còn phụ thuộc cặp connect fields. | Đảo cả `startWith`, `connectFromField` và `connectToField` theo quan hệ. |
| “`depthField:0` là root input.” | Depth 0 thuộc **document tìm thấy ở lượt đầu**. | Trực tiếp là 0; sau đó 1, 2, ... |
| “`maxDepth:0` không chạy truy vấn.” | Nó vẫn có **một lượt tra cứu**, chỉ không mở rộng thêm. | Dùng `maxDepth:0` để lấy một cấp. |
| “`maxDepth:2` trả tối đa hai node.” | Đây là **hai mức mở rộng sau depth 0**, không phải số lượng node. | Bổ sung kiểm soát fan-out, số roots, output. |
| “Không có `maxDepth` sẽ an toàn nếu dữ liệu ít hiện tại.” | Fan-out/cycles/cập nhật có thể tăng chi phí nhanh. | Định mức độ sâu và giới hạn phục vụ endpoint. |
| “Array `as` đã sắp từ gần tới xa.” | `$graphLookup` **không cam kết thứ tự**. | Dùng `$sortArray` hoặc `$unwind → $sort`. |
| “`depthField` là toàn bộ path.” | Nó là **mức**, không chứa từng cạnh hoặc mọi đường đi. | Muốn path/shortest path phải có mô hình/thuật toán phù hợp. |
| “Lọc active sau `$graphLookup` tương đương restrict active.” | Post-filter vẫn có thể giữ nút nằm dưới **inactive ancestor**. | Dùng `restrictSearchWithMatch` nếu cần **cắt nhánh**. |
| “`restrictSearchWithMatch` hỗ trợ `"$tenantId"` tham chiếu input.” | Chuỗi `"$tenantId"` trong filter là literal, không phải dynamic expression. | Scope bằng literal đã xác thực hoặc composite keys/mô hình khác. |
| “Một `$match` root đủ để bảo đảm mọi descendant trong tenant.” | Cạnh có thể trỏ sang tenant khác. | Enforce tenant scope ở quan hệ/from và identity. |
| “Muốn chỉ lấy 10 nút thì `$slice` array output.” | `$slice` sau traversal **không ngăn server duyệt toàn graph**. | Chọn data model/pagination hoặc thuật toán có bound thực. |
| “`$limit:10` sau `$graphLookup` giới hạn 10 phép traversal.” | Stage chạy sau không đồng nghĩa đã hạn chế input cho graph. | `$match`/`$limit` root **trước** graph khi hợp nghĩa. |
| “Có index trên `managerId` thì truy vấn tổ tiên luôn được index.” | Hướng tổ tiên match `employeeId`. | Index trên **connectToField** của từng hướng. |
| “Có index là `$graphLookup` chắc chắn nhanh.” | Graph rộng, nhiều roots, lookup/fan-out, memory vẫn tốn. | Đọc explain, đo số nút/mức, maxTimeMS, load test. |
| “Graph có chu trình thì `$graphLookup` cứ lặp mãi.” | Stage quản lý các nút đã truy cập, không trả một node vô hạn lần chỉ do cycle. | Nhưng phải **ngăn cycle ở domain** nếu dữ liệu phải là cây. |
| “Unique index trên managerId sẽ làm cây hợp lệ.” | Nó còn cấm nhiều người có cùng quản lý; trái với nhu cầu. | Unique trên **employeeId**; nonunique trên **managerId**. |
| “`allowDiskUse:true` luôn giải quyết memory của graphLookup.” | MongoDB 7.0/8.0 có giới hạn 100 MB riêng; hành vi khác ở tài liệu hiện hành. | Kiểm tra đúng phiên bản; giảm graph fan-out và output. |
| “Trả array rất lớn cũng được vì MongoDB có cursor.” | Mỗi **document kết quả** vẫn chịu 16 MiB; cursor không xóa giới hạn này. | Giới hạn depth, node size, thiết kế output thích hợp. |
| “Sharded `from` hỗ trợ ở mọi phiên bản.” | Hỗ trợ từ **MongoDB 5.1**; còn hạn chế transaction. | Đối chiếu server version và routing. |
| “`$graphLookup` trong transaction nhắm sharded collection vẫn dùng như `$lookup`.” | MongoDB có hạn chế riêng: **không hỗ trợ** `$graphLookup` trong transaction khi nhắm sharded `from`. | Chọn kế hoạch nhất quán khác. |
| “`$graphLookup` kiểm tra luôn tính đúng của foreign key.” | Stage chỉ duyệt các reference theo dữ liệu hiện có. | Validate node keys, refs, tenant và cycle ở tầng thiết kế/ghi dữ liệu. |

### 16.1. Ba câu hỏi trước khi code review

1. **Đi từ đâu, theo hướng nào?** Viết phép tra cứu đầu tiên: `from.connectToField = startWith`.
2. **Dừng khi nào?** Xác định `maxDepth`, rule `restrictSearchWithMatch` và fan-out lớn nhất có thể.
3. **Kết quả là gì?** Tập nút có thể đến, cây đã sắp thứ tự, danh sách manager, hay mọi đường đi? `$graphLookup` không tự cung cấp tất cả những cấu trúc đó.

### 16.2. Hai câu hỏi về giới hạn hệ thống

4. **Tìm các cạnh bằng index nào?** Index trên `connectToField`, thêm điều kiện restrict khi thật sự hữu ích.
5. **Có an toàn với tenant, memory và kích thước output không?** Xác thực root scope, kiểm tra edges, bảo vệ maxDepth, đo tải thực.

## 17. Bài tập thực hành có đáp án

Dùng fixture `graph_lookup_lab.employees`, `airports`, `travelers` và `cycleNodes` ở các mục trước. Các bài chỉ đọc dữ liệu, trừ khi được nói rõ; không cần chạy trên production.

### Bài 1 — Tìm toàn bộ cấp dưới CEO

**Yêu cầu:** Trả hậu duệ của CEO trong tối đa ba tầng con, có `level`.

**Đáp án:**

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "reports",
      maxDepth: 2,
      depthField: "level"
    }
  }
])
~~~

Kết quả **9 người**, không gồm chính CEO. A/B level 0; C/D/F/H level 1; E/I/G level 2.

### Bài 2 — Chỉ lấy quản lý trực tiếp

**Yêu cầu:** Từ CEO chỉ lấy A và B, không lấy C/D.

**Đáp án:** Dùng cùng pipeline hậu duệ với `maxDepth:0`:

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    as: "directReports",
    maxDepth: 0
  }
}
~~~

`maxDepth:0` là **một lượt tra cứu**. Nếu chỉ cần một cấp và data model đơn giản, `find({managerId:"CEO"})` có index cũng có thể đủ.

### Bài 3 — Tìm chuỗi quản lý của G

**Yêu cầu:** Trả tất cả cấp trên của G tới CEO.

**Đáp án:**

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "G" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$managerId",
      connectFromField: "managerId",
      connectToField: "employeeId",
      as: "ancestors",
      depthField: "level"
    }
  }
])
~~~

Tập kết quả: **F, B, CEO**. Level tương ứng 0, 1, 2; thứ tự array không được cam kết.

### Bài 4 — Chuỗi quản lý ngắn

**Yêu cầu:** Với G chỉ lấy tối đa hai người quản lý tính từ G.

**Đáp án:** Dùng truy vấn tổ tiên với `maxDepth:1`, trả **F và B**, không có CEO.

### Bài 5 — Đếm theo tầng

**Yêu cầu:** Đếm số descendants CEO ở từng level 0, 1, 2.

**Đáp án:**

~~~javascript
lab.employees.aggregate([
  { $match: { employeeId: "CEO" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "reports",
      maxDepth: 2,
      depthField: "level"
    }
  },
  { $unwind: "$reports" },
  {
    $group: {
      _id: "$reports.level",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Counts là **2, 4, 3** theo các mức 0, 1, 2.

### Bài 6 — Hai cách lọc active cho kết quả khác nhau thế nào?

**Yêu cầu:** So sánh `restrictSearchWithMatch:{active:true}` với `$filter` ở cuối traversal không restrict.

**Đáp án:**

- **Restrict khi duyệt**: A, B, C, E, F, G, H = **7**; D inactive bị cắt và I dưới D không tới được.
- **Lọc array sau khi duyệt**: A, B, C, E, F, G, H, I = **8**; I vẫn xuất hiện vì traversal đã đi qua D trước khi lọc.

Đây là khác biệt **ngữ nghĩa và chi phí**, không chỉ hai cú pháp khác nhau.

### Bài 7 — Vì sao `startWith:"$managerId"` sai khi tìm cấp dưới CEO?

**Đáp án:** CEO có `managerId:null`. Nếu dùng `startWith:"$managerId"` thay vì `"$employeeId"` để đi xuống, lượt tìm đầu tiên không phải “ai có managerId = CEO”. Cần lấy `employeeId` của CEO làm seed để so với `managerId` của các nhân viên con.

### Bài 8 — Index nào cho hai hướng?

**Yêu cầu:** Đề xuất index tương ứng khi tìm descendants và ancestors.

**Đáp án:**

~~~javascript
// Tìm con theo managerId:
lab.employees.createIndex({ managerId: 1 })

// Tìm cha theo employeeId:
lab.employees.createIndex(
  { employeeId: 1 },
  { unique: true }
)
~~~

Chú ý: không tạo unique index trên `managerId`, vì nhiều nhân viên có thể cùng một người quản lý. Với fixture đã tạo các index ở mục 3, câu lệnh này là **minh họa key pattern**, không cần tạo lại một index trùng.

### Bài 9 — Duyệt sân bay từ HAN

**Yêu cầu:** Với traveler TR-1, `maxDepth:1` trả những sân bay nào?

**Đáp án:** **HAN** có hops 0, **DAD và SGN** có hops 1. CXR/PQC chỉ đến ở hops 2, không nằm trong kết quả. Ở đây HAN là node đầu tiên trong `from` được match vì `startWith:"HAN"` và `connectToField:"airport"`.

### Bài 10 — Sắp theo level

**Yêu cầu:** Sắp các hậu duệ CEO theo `level` tăng rồi `employeeId` tăng.

**Đáp án gợi ý:**

~~~javascript
{
  $set: {
    descendants: {
      $sortArray: {
        input: "$descendants",
        sortBy: { level: 1, employeeId: 1 }
      }
    }
  }
}
~~~

Đặt stage sau `$graphLookup`. `$sortArray` hỗ trợ từ MongoDB 5.2; không dựa vào thứ tự tự nhiên của array `as`.

### Bài 11 — Root có cấp dưới inactive

**Yêu cầu:** Bắt đầu từ A, `restrictSearchWithMatch:{active:true}` với `maxDepth:2`. Ai được trả?

**Đáp án:** C (level 0) và E (level 1). D bị loại vì inactive, I không được duyệt do nằm dưới D. Nếu bỏ restrict, trả C, D, E, I.

### Bài 12 — Chạy từ một collection khác

**Yêu cầu:** Từ `lab.roots` có `rootEmployeeId:"A"`, lấy descendants trong `lab.employees`.

**Đáp án:**

~~~javascript
lab.roots.aggregate([
  { $match: { _id: "R-ENG" } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$rootEmployeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "members",
      maxDepth: 2
    }
  }
])
~~~

`from` có thể là collection khác **trong cùng database**. Không cần source và target cùng tên.

### Bài 13 — Truy vấn bị chậm dù đã `$match` root

**Đề:** `$match:{employeeId:"CEO"}` dùng `IXSCAN`, nhưng `$graphLookup` vẫn chậm. Chỉ số nào cần xem tiếp?

**Đáp án:** Index trên `connectToField` là `managerId`, cùng traversal fan-out, độ sâu, số nodes, stats stage, memory/disk usage theo version và kích thước result. `IXSCAN` root chỉ giải quyết tìm input đầu; nó không chứng minh các lượt duyệt recursive đã dùng index tốt.

### Bài 14 — `$slice` có giảm số nút duyệt không?

**Đề:** Sau `$graphLookup`, áp `$project:{reports:{$slice:["$reports",5]}}`. MongoDB có dừng sau năm nút không?

**Đáp án:** Không. `$slice` áp dụng **sau khi array đã hình thành**, chỉ giới hạn output. Muốn hạn chế chi phí traversal phải giảm root/depth/nhánh, thiết kế model khác hoặc thuật toán có bound.

### Bài 15 — Xử lý cycle

**Đề:** Graph A → B → C → A, có thêm C → D. `$graphLookup` từ A có trả A nhiều lần vô hạn không?

**Đáp án:** Không; traversal kiểm soát nút đã đi qua, nên reachable set chỉ có A, B, C, D. Nhưng nếu domain yêu cầu graph là **cây nhân sự**, chu trình vẫn là **dữ liệu sai** và cần bị ngăn ở đường ghi.

### Bài 16 — Dynamic tenant filter

**Đề:** Có thể đặt `restrictSearchWithMatch:{tenantId:"$tenantId"}` và kỳ vọng giá trị là tenantId của từng input không?

**Đáp án:** Không. Đây không phải aggregation expression, `"$tenantId"` là literal string trong filter. Với một tenant đã được xác thực, dùng literal tenantId ở backend; với query nhiều tenant cần thiết kế **composite keys**/scope data để không có cross-tenant traversal.

### Bài 17 — Vì sao `maxDepth:2` chưa đủ bảo vệ tài nguyên?

**Đáp án:** Tại mỗi mức có thể có rất nhiều nút. Với 1.000 con mỗi node, depth 0 có 1.000, depth 1 có thể tới 1.000.000 nút. Phải xét **fan-out**, number of roots, doc size, memory và limit 16 MiB; không thể coi maxDepth là số lượng result.

### Bài 18 — Giới hạn memory khác theo phiên bản

**Đề:** Một tutorial cho rằng chỉ cần `allowDiskUse:true` là `$graphLookup` trên MongoDB 8.0 không còn giới hạn 100 MB. Có đúng không?

**Đáp án:** Không theo **tài liệu `$graphLookup` của MongoDB 8.0**, nơi option này không làm stage vượt giới hạn 100 MB riêng. Manual hiện hành mô tả behavior spill khác; phải xem đúng **server version** và test, không sao chép một quy tắc sang mọi phiên bản.

### Bài 19 — Nhu cầu shortest path có trọng số

**Đề:** Trong mạng sân bay, tìm đường có **tổng chi phí vé thấp nhất**, mỗi cạnh có giá khác nhau. `$graphLookup` có trực tiếp trả đường bay rẻ nhất không?

**Đáp án:** Không. `$graphLookup` thực hiện reachability traversal, không phải giải thuật Dijkstra/shortest weighted path và không tự tính toàn bộ đường đi tối ưu. Cần mô hình edge weights và thuật toán phù hợp hoặc một thành phần graph processing chuyên dụng.

## 18. Quy trình thiết kế một endpoint duyệt quan hệ an toàn

Một service có endpoint tương tự:

~~~text
GET /organizations/{tenantId}/employees/{employeeId}/descendants?depth=2
~~~

không nên chỉ ghép một `$graphLookup` vào controller rồi trả toàn bộ array. Quy trình hợp lý:

### Bước 1 — Chốt ngữ nghĩa

Xác định:

- `depth=0` là “cấp trực tiếp” hay “chỉ root”? Trong MongoDB `maxDepth:0` có **một lượt tìm**; nếu API muốn depth=0 nghĩa là **chỉ root**, phải chuyển đổi quy ước ở backend.
- Có lấy root trong output không?
- Mỗi node có một cha hay nhiều cha?
- Nút inactive có **chặn traversal** hay chỉ bị ẩn khỏi danh sách hiển thị?
- Trả mọi descendants hay chỉ một subset; có yêu cầu thứ tự xác định không?
- Dữ liệu tenant có được nối xuyên tenant không?

Viết các quy tắc này vào API contract, không để người dùng suy từ trường `maxDepth`.

### Bước 2 — Ràng buộc identity của các nút

Với mô hình một tenant:

~~~javascript
{
  employeeId: "E",
  managerId: "C",
  active: true
}
~~~

Kiểm tra `employeeId` ổn định/duy nhất, `managerId` cùng kiểu và tham chiếu tới nhân viên hợp lệ; nếu không, traversal dễ bị thiếu nhánh hoặc nhân nhiều nhánh. Với multi-tenant, cân nhắc khóa `(tenantId, employeeId)` và composite edge key để không ghép nhầm mã nhân viên giống nhau ở hai tenant.

### Bước 3 — Giới hạn root và depth từ ngữ cảnh xác thực

~~~javascript
const requestedEmployeeId = "CEO"
const requestedDepth = 2
const maximumDepth = 4

if (!Number.isInteger(requestedDepth) ||
    requestedDepth < 0 ||
    requestedDepth > maximumDepth) {
  throw new Error("depth ngoài giới hạn API")
}

lab.employees.aggregate([
  { $match: { employeeId: requestedEmployeeId } },
  {
    $graphLookup: {
      from: "employees",
      startWith: "$employeeId",
      connectFromField: "employeeId",
      connectToField: "managerId",
      as: "descendants",
      maxDepth: requestedDepth,
      depthField: "level",
      restrictSearchWithMatch: { active: true }
    }
  }
], { maxTimeMS: 5000 })
~~~

Đoạn minh họa dùng biến `requestedEmployeeId` đã được hệ thống xác thực/phân quyền theo quyền truy cập nếu triển khai thực. Trong API multi-tenant, còn phải bổ sung tenant scope vào **root và graph edges** như đã thảo luận. Đừng lấy một key bất kỳ từ path rồi cho truy vấn đọc toàn bộ quan hệ nhạy cảm.

### Bước 4 — Tạo index theo chiều duyệt

Cho descendants:

~~~javascript
lab.employees.createIndex({ managerId: 1 })
~~~

Cho ancestors:

~~~javascript
lab.employees.createIndex(
  { employeeId: 1 },
  { unique: true }
)
~~~

Đây là các index ứng viên. Nếu collection đang có indexes tương đương, không cần thêm bản sao. Thử explain và cân nhắc compound index với các điều kiện restrict phổ biến.

### Bước 5 — Kiểm thử đồ thị nhỏ nhưng có các edge cases

Một bộ test nên có:

| Nhóm dữ liệu | Điều cần xác nhận |
|---|---|
| Root không có con | `as` là array rỗng. |
| Root có đúng một con | `maxDepth:0` trả một con level 0. |
| Cây ba tầng | `maxDepth:1` không lấy tầng depth 2. |
| Nhánh inactive có cháu active | Restrict có cắt cả nhánh đúng policy không? |
| Nút orphan (managerId không tồn tại) | Không tạo nút ảo; phạm vi traversal đúng. |
| Cycle A → B → A | Query kết thúc; domain có bác bỏ cycle không? |
| Nhiều đường tới một node | Không suy “một output = một đường đi”. |
| Hai tenants dùng cùng employeeId | Không tạo cạnh xuyên tenant. |
| Một node có mảng links | Mỗi phần tử link được mở rộng khi hợp lệ. |
| Graph rất rộng | Hạn mức tài nguyên/output có được xử lý? |

### Bước 6 — Load test với graph đại diện

Kiểm tra ít nhất:

- Số root mỗi query và phân bố số children/node.
- Tỷ lệ nút bị restrict filter loại và **số nhánh cắt được**.
- `maxDepth` thường dùng so với độ sâu tối đa trong dữ liệu.
- `totalKeysExamined`/`totalDocsExamined` và indexes used theo explain.
- P50/P95/P99 latency, CPU, memory, I/O/disk spill tùy version.
- Kích thước BSON output theo node count và field count.
- Shard targeting/fan-out nếu collection `from` bị shard.
- Khả năng timeout/hủy thao tác khi client ngắt kết nối.

Một tree mười nút có thể chạy rất nhanh nhưng không nói gì về graph hàng triệu nodes, nhiều cross-shard edges hoặc input roots không có index.

### Bước 7 — Đặt ranh giới sản phẩm khi graph quá lớn

Thay vì trả toàn bộ cây:

- UI có thể **lấy con trực tiếp theo từng lần mở rộng** bằng `find({managerId:...})`.
- Báo cáo có thể chạy **offline/precompute** rồi lưu summary.
- Chức năng tìm người quản lý có thể giới hạn tới một số cấp hợp lý.
- Nếu business cần lấy tất cả descendants, API nên có cơ chế paging/streaming ở **mô hình phù hợp** thay vì kỳ vọng `$slice` sau graphLookup giới hạn chi phí duyệt.
- Các node có nhiều field nhạy cảm/lớn nên được **tách thông tin graph** và thông tin hồ sơ chi tiết.

### Bước 8 — Theo dõi thay đổi graph

Khi có thao tác chuyển bộ phận hoặc đổi manager, cần:

1. Ngăn cycle và cross-tenant references nếu domain không cho phép.
2. Cập nhật cache/materialized paths đúng phiên bản, nếu có.
3. Kiểm soát concurrent modifications và audit.
4. Đo các truy vấn sau thay đổi, vì fan-out của một node có thể tăng mạnh.
5. Không diễn giải thiếu nút sau restrict như lỗi index nếu thực tế filter đang cắt nhánh theo thiết kế.

## 19. Tóm tắt cú pháp để tra cứu nhanh

### 19.1. Duyệt hậu duệ

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$employeeId",
    connectFromField: "employeeId",
    connectToField: "managerId",
    as: "descendants",
    maxDepth: 2,
    depthField: "level"
  }
}
~~~

**Tìm những document có `managerId` bằng mã node hiện tại**, lặp lại từ employeeId mới tìm được.

### 19.2. Duyệt tổ tiên

~~~javascript
{
  $graphLookup: {
    from: "employees",
    startWith: "$managerId",
    connectFromField: "managerId",
    connectToField: "employeeId",
    as: "ancestors",
    maxDepth: 2,
    depthField: "level"
  }
}
~~~

**Tìm document có `employeeId` bằng managerId hiện tại**, lặp lại lên cấp quản lý phía trên.

### 19.3. Cắt nhánh theo điều kiện

~~~javascript
restrictSearchWithMatch: {
  active: true
}
~~~

Nút không hợp điều kiện không được chấp nhận để tiếp tục duyệt. **Không** dùng `"$field"` trong restrict filter để kỳ vọng so sánh động với root.

### 19.4. Bảng quy đổi “số tầng”

| Số tầng kết quả từ nút bắt đầu (không tính root) | `maxDepth` |
|---:|---:|
| 1 | 0 |
| 2 | 1 |
| 3 | 2 |
| N | N − 1 |

Quy đổi này đúng khi lượt tra cứu đầu tiên trả **tầng con/manager đầu tiên**, như ví dụ nhân viên. Nếu seed là một node nằm trong `from` và chính node đó được trả ở depth 0 (ví dụ sân bay HAN), cần xem lại nghĩa “tầng” theo API.

### 19.5. Kiểm tra thứ tự và kết quả

~~~javascript
{
  $set: {
    descendants: {
      $sortArray: {
        input: "$descendants",
        sortBy: { level: 1, employeeId: 1 }
      }
    }
  }
}
~~~

Làm sau graphLookup, không dựa vào array order tự nhiên. Muốn nhóm theo depth có thể `$unwind` rồi `$group`/`$sort`.

## 20. Tài liệu MongoDB chính thức

Các nguồn dưới đây giúp kiểm tra cú pháp và giới hạn **theo server version**, đặc biệt về bộ nhớ của `$graphLookup`:

- [`$graphLookup` — MongoDB Database Manual](https://www.mongodb.com/docs/manual/reference/operator/aggregation/graphLookup/) — tham số `from`/`startWith`/`connectFromField`/`connectToField`, `maxDepth`/`depthField`, restrict filter, sharding và kết quả không được sort.
- [`$graphLookup` — MongoDB 8.0 Manual](https://www.mongodb.com/docs/v8.0/reference/operator/aggregation/graphLookup/) — đối chiếu chính xác giới hạn memory và hành vi `allowDiskUse` ở nhánh 8.0.
- [`$graphLookup` — MongoDB 7.0 Manual](https://www.mongodb.com/docs/v7.0/reference/operator/aggregation/graphLookup/) — tham chiếu theo nhánh 7.0.
- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — stage semantics, luồng dữ liệu và aggregation basics.
- [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/) — các phép chuyển vị trí/tối ưu stage khi tương đương về ngữ nghĩa.
- [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/) — giới hạn bộ nhớ, disk use, kích thước kết quả.
- [`$lookup` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — đối chiếu join một cấp và lookup có pipeline.
- [`$unwind` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/) — chuyển mỗi phần tử của array kết quả thành pipeline document.
- [`$sortArray` Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sortArray/) — sắp xếp array output theo field.
- [`$filter` Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/) — lọc phần tử của array **sau khi đã tạo**, khác cắt nhánh trong traversal.
- [`$match` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/) — chỉ chọn các root cần duyệt.
- [Indexes](https://www.mongodb.com/docs/manual/indexes/) — thiết kế index phù hợp field được tìm trong `connectToField`.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — cách đọc execution plan và các số liệu giải thích.
- [`db.collection.explain()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/) — gọi `explain("executionStats")` cho aggregation.
- [Sharded Collections and Aggregation](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-sharded-collections/) — cơ chế aggregation trên sharded collections.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — giới hạn với `$graphLookup` nhắm `from` sharded.
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/) — tạo pipeline qua `MongoCollection.aggregate` và Java BSON builders.
- [MongoDB 9.0 Release Notes](https://www.mongodb.com/docs/manual/release-notes/9.0/) — giới hạn memory theo toàn operation từ 9.0, phân biệt với limit từng stage.

**Kết luận:** `$graphLookup` phù hợp để **duyệt đệ quy những quan hệ biểu diễn bằng field tham chiếu** trong MongoDB. Ba quyết định ảnh hưởng tính đúng đắn nhất là **đi đúng chiều bằng cặp `connectFromField`/`connectToField`**, **đặt `maxDepth` theo quy tắc depth bắt đầu từ 0**, và **chọn `restrictSearchWithMatch` khi muốn cắt nhánh thay vì chỉ lọc kết quả hiển thị**. Khi vận hành thực tế, hãy giảm số roots, lập index trên `connectToField`, đo fan-out, tránh giả định output có thứ tự hoặc chứa mọi đường đi, và đối chiếu giới hạn bộ nhớ/sharding đúng phiên bản server trước khi mở rộng graph.
