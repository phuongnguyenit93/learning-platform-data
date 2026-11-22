# Projection, sắp xếp, phân trang và tổng hợp dữ liệu tài liệu

Trong cơ sở dữ liệu NoSQL theo **mô hình tài liệu** (*document model*), dữ liệu thường được lưu dưới dạng các đối tượng có cấu trúc lồng nhau: một sản phẩm chứa thông tin danh mục, nhãn hiệu, biến thể và hình ảnh; một đơn hàng chứa các dòng hàng cùng địa chỉ giao nhận. Khi đọc tài liệu, ứng dụng không chỉ quan tâm **tài liệu nào được chọn**, mà còn cần quyết định **trả về trường nào, thứ tự nào, lấy từng trang như thế nào và tổng hợp thông tin ra sao**.

Bốn kỹ thuật thường đi cùng nhau:

- **Projection** định hình dữ liệu trả về, giúp client chỉ nhận những field cần thiết.
- **Sorting** sắp xếp tài liệu theo khóa đã định và phải xử lý được các giá trị trùng nhau.
- **Pagination** chia tập kết quả thành những phần có thể tải và điều hướng ổn định.
- **Aggregation** biến tập tài liệu thành thống kê, nhóm, tính toán và cấu trúc kết quả mới.

Bài học dùng **MongoDB** để minh họa bằng truy vấn cụ thể; các nguyên tắc về thiết kế API, tải dữ liệu, phân trang và chi phí truy vấn cũng hữu ích khi làm việc với những document store khác. Cú pháp và khả năng hỗ trợ của từng hệ phải được đối chiếu với sản phẩm, phiên bản, chỉ mục và mô hình nhất quán đang sử dụng.

## 1. Từ tài liệu gốc đến dữ liệu phục vụ màn hình

Giả sử ứng dụng thương mại điện tử có collection **products**:

~~~javascript
{
  _id: ObjectId("67340d86e3bcdf25a8901001"),
  sku: "LAPTOP-014",
  name: "Laptop Atlas 14",
  categoryId: "laptop",
  status: "ACTIVE",
  price: NumberDecimal("18500000.00"),
  currency: "VND",
  createdAt: ISODate("2026-11-01T03:20:00Z"),
  updatedAt: ISODate("2026-11-12T10:20:00Z"),
  brand: {
    id: "atlas",
    name: "Atlas"
  },
  tags: ["office", "portable"],
  images: [
    { url: "/images/atlas-front.webp", alt: "Góc trước" },
    { url: "/images/atlas-side.webp", alt: "Góc nghiêng" }
  ],
  variants: [
    { code: "GRAY-16", color: "gray", memoryGb: 16, stock: 8 },
    { code: "SILVER-32", color: "silver", memoryGb: 32, stock: 0 }
  ],
  supplierCost: NumberDecimal("16000000.00"),
  internalNotes: "Giá nhập dành riêng cho quản trị"
}
~~~

Một thẻ sản phẩm trên danh sách chỉ cần **id, name, price, image đại diện, brand**. Trang chi tiết cần thêm variants, tags và images. Báo cáo doanh thu lại phải đọc từ orders/payments, không thể suy ra doanh thu thực từ giá niêm yết trong products.

Nếu API luôn trả toàn bộ document, trang danh sách nhận cả thông tin không dùng đến, có thể lộ dữ liệu nội bộ và gây tốn băng thông. Nếu API lọc/nhóm/sắp xếp ở client sau khi tải hàng nghìn document, hệ thống mất khả năng phân trang chính xác và tận dụng index tại database.

~~~mermaid
flowchart LR
    A[Collection documents] --> B[Filter]
    B --> C[Project fields]
    C --> D[Sort theo thứ tự xác định]
    D --> E[Paginate]
    E --> F[API response]
    B --> G[Aggregation pipeline]
    G --> H[Nhóm và tính toán]
    H --> I[Dashboard / report]
~~~

Đây là mô hình khái niệm, không phải khẳng định database luôn thực thi các bước theo đúng thứ tự vẽ. Query optimizer có thể tối ưu hoặc di chuyển một số phép biến đổi nếu vẫn bảo toàn ngữ nghĩa.

## 2. Projection là gì?

**Projection** lựa chọn và/hoặc biến đổi những field được đưa vào kết quả. Có hai hình thức cần phân biệt:

1. **Field selection:** chỉ lấy hoặc loại trừ một số field, thường dùng với truy vấn đọc tài liệu.
2. **Computed projection:** tạo field mới, đổi tên, tính toán, trích phần tử mảng hoặc biến đổi cấu trúc, thường dùng trong aggregation pipeline.

### 2.1. Chỉ lấy những trường cần hiển thị

Với MongoDB:

~~~javascript
db.products.find(
  { categoryId: "laptop", status: "ACTIVE" },
  {
    name: 1,
    price: 1,
    currency: 1,
    "brand.name": 1,
    createdAt: 1
  }
);
~~~

Giá trị **1** yêu cầu đưa field vào kết quả. MongoDB mặc định vẫn trả **_id** nếu không loại trừ tường minh:

~~~javascript
db.products.find(
  { categoryId: "laptop", status: "ACTIVE" },
  {
    _id: 0,
    name: 1,
    price: 1,
    currency: 1
  }
);
~~~

Có thể lựa chọn theo kiểu **loại bỏ** field:

~~~javascript
db.products.find(
  { _id: ObjectId("67340d86e3bcdf25a8901001") },
  {
    supplierCost: 0,
    internalNotes: 0
  }
);
~~~

Trong truy vấn projection dạng thông thường, không thể tùy ý trộn inclusion **1** và exclusion **0**; **_id** là ngoại lệ phổ biến. Khi cần định dạng phức tạp, nên dùng aggregation hoặc xây dựng DTO rõ ràng.

**Projection không tự thay thế kiểm soát truy cập.** Nếu một vai trò không được phép đọc dữ liệu nội bộ, cần áp dụng quyền ở tầng API/database thích hợp. Việc quên thêm một field vào danh sách loại trừ có thể vô tình để lộ nó. Với API công khai, **danh sách field được phép trả về** thường dễ kiểm soát hơn cách lấy tất cả rồi loại trừ vài field nhạy cảm.

### 2.2. Field lồng nhau

Document lưu **brand.name** bên trong object **brand**. MongoDB hỗ trợ truy vấn, projection và sort theo dotted path với những ngữ nghĩa cụ thể:

~~~javascript
db.products.find(
  { "brand.id": "atlas" },
  {
    _id: 0,
    name: 1,
    "brand.name": 1
  }
);
~~~

Đây là **cách lựa chọn đường dẫn field**, không phải phép join sang collection brands. Nếu cần tổng hợp dữ liệu từ collection khác, có thể cân nhắc **$lookup**, nhưng phải đo chi phí join trong thực tế.

### 2.3. Computed projection trong aggregation pipeline

Pipeline dùng **$project** để dựng đầu ra theo ý API:

~~~javascript
db.products.aggregate([
  {
    $match: {
      categoryId: "laptop",
      status: "ACTIVE"
    }
  },
  {
    $project: {
      _id: 0,
      productId: { $toString: "$_id" },
      name: 1,
      price: 1,
      currency: 1,
      brandName: "$brand.name",
      thumbnailUrl: {
        $arrayElemAt: ["$images.url", 0]
      }
    }
  },
  { $limit: 20 }
]);
~~~

Ở đây **productId** được chuyển sang string, **brandName** lấy từ field lồng nhau và **thumbnailUrl** lấy hình đầu tiên. Với dữ liệu thiếu field/mảng rỗng, API cần thống nhất quy tắc trả **null**, bỏ field hoặc giá trị mặc định; không nên dựa vào một hình đại diện luôn tồn tại.

### 2.4. Projection với mảng con

Một document có thể lưu nhiều variants, nhưng màn hình chỉ muốn các biến thể còn hàng:

~~~javascript
db.products.aggregate([
  { $match: { sku: "LAPTOP-014" } },
  {
    $project: {
      _id: 0,
      sku: 1,
      name: 1,
      availableVariants: {
        $filter: {
          input: "$variants",
          as: "variant",
          cond: { $gt: ["$$variant.stock", 0] }
        }
      }
    }
  }
]);
~~~

**$filter** giữ lại phần tử của mảng thỏa điều kiện. Khi field có thể thiếu hoặc không phải mảng, cần xác định policy dữ liệu và bổ sung kiểm tra/chuẩn hóa phù hợp trước khi áp dụng toán tử mảng.

**$map** có thể tạo dạng phần tử mới:

~~~javascript
{
  $project: {
    sku: 1,
    variantOptions: {
      $map: {
        input: "$variants",
        as: "v",
        in: {
          code: "$$v.code",
          label: {
            $concat: ["$$v.color", " / ", { $toString: "$$v.memoryGb" }, " GB"]
          }
        }
      }
    }
  }
}
~~~

Ví dụ trên là một **stage** để đặt bên trong pipeline, không phải truy vấn chạy độc lập.

## 3. Projection tối ưu được gì và không tối ưu được gì?

Tác dụng thường thấy:

- Giảm kích thước JSON/BSON trả về nếu chỉ cần một phần nhỏ document.
- Giảm số byte gửi qua mạng và tải serialize/deserialize ở driver, API, client.
- Giảm lượng dữ liệu ứng dụng vô tình giữ trong bộ nhớ hoặc log.
- Làm API response rõ ràng và dễ quản lý version hơn.
- Trong điều kiện thích hợp, cho phép **covered query** được phục vụ từ index mà không cần đọc toàn bộ document.

Tuy nhiên, **projection ít field không luôn tương đương đọc ít dữ liệu từ disk**. Nếu database vẫn phải đọc toàn bộ document để lấy field chưa có trong index, chi phí truy cập storage có thể vẫn đáng kể.

Ví dụ nếu index chứa mọi field cần **lọc, sắp xếp và trả về** thì truy vấn có thể được phục vụ chủ yếu từ index, tùy kế hoạch thực thi:

~~~javascript
db.products.createIndex({
  categoryId: 1,
  status: 1,
  createdAt: -1,
  _id: -1,
  name: 1,
  price: 1
});

db.products.find(
  { categoryId: "laptop", status: "ACTIVE" },
  { _id: 0, name: 1, price: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

Truy vấn **không nhất thiết** được covered chỉ vì index đã khai báo: kế hoạch thực thi còn phụ thuộc kiểu truy vấn, multikey, collations, trường đưa ra và phiên bản engine. Cần xem **explain** và số tài liệu phải đọc thực tế.

Không nên thêm mọi field vào compound index chỉ để tránh đọc document. Index càng lớn càng tốn RAM/disk, tăng chi phí ghi và xây dựng index. Hãy đo độ lợi của projection/covering với workload cụ thể.

## 4. Sorting: thứ tự phải xác định

Sắp xếp thường dùng một hoặc nhiều field:

~~~javascript
db.products.find(
  { categoryId: "laptop", status: "ACTIVE" },
  { name: 1, price: 1, createdAt: 1 }
).sort({ price: 1, _id: 1 });
~~~

Trong MongoDB, **1** là tăng dần và **-1** là giảm dần. Truy vấn trên sắp theo giá thấp đến cao, rồi theo **_id** khi giá bằng nhau.

### 4.1. Vì sao cần tie-breaker?

Giả sử ba sản phẩm có cùng **createdAt**:

~~~text
createdAt            _id
2026-11-10T10:00Z    A
2026-11-10T10:00Z    B
2026-11-10T10:00Z    C
~~~

Nếu chỉ gọi:

~~~javascript
.sort({ createdAt: -1 })
~~~

thứ tự tương đối của A/B/C **không có hợp đồng ổn định** để làm nền cho phân trang. Kết quả có thể thay đổi do kế hoạch truy vấn, shard, dữ liệu mới, thao tác cập nhật hoặc các điều kiện khác.

Thêm khóa định danh duy nhất:

~~~javascript
.sort({ createdAt: -1, _id: -1 })
~~~

Từ đó mọi tài liệu trong tập phù hợp có một thứ tự **toàn phần** theo cặp *(createdAt, _id)*. Một sort ổn định không làm bộ dữ liệu bất biến qua thời gian, nhưng loại bỏ nhập nhằng khi các giá trị sort chính trùng nhau.

### 4.2. Kiểu dữ liệu và giá trị thiếu

Một field có thể bị thiếu hoặc mang kiểu khác nhau giữa các document. MongoDB có quy tắc so sánh theo BSON type order, do đó việc trộn **string, number, date, null** trong cùng field có thể tạo thứ tự khác mong đợi của người dùng.

Ví dụ giá lưu thành hai loại:

~~~javascript
{ sku: "A", price: "90000" }     // string
{ sku: "B", price: 100000 }      // number
~~~

Không nên dựa vào sort số tiền khi schema cho phép kiểu giá lẫn lộn. Hãy thống nhất kiểu số, đơn vị tiền tệ, cách biểu diễn tiền và xử lý null/missing từ đầu.

Với tiền, nhiều hệ dùng **Decimal128** hoặc số nguyên theo đơn vị nhỏ nhất. Khi sort, phải xác định liệu các giá trị **VND** và **USD** có được so trực tiếp hay cần chuẩn hóa theo đồng tiền.

### 4.3. Sắp xếp chuỗi và collation

Chuỗi có dấu, chữ hoa/thường và quy tắc locale có thể được sắp khác nhau. MongoDB hỗ trợ **collation** cho những thao tác liên quan đến so sánh chuỗi.

~~~javascript
db.products.find(
  { status: "ACTIVE" },
  { name: 1 }
).collation({ locale: "vi", strength: 2 })
 .sort({ name: 1, _id: 1 });
~~~

Collation trong query cần tương thích với index nếu muốn tận dụng index cho sort theo chuỗi. **Thứ tự mã ký tự** và **thứ tự theo ngôn ngữ** là hai yêu cầu khác nhau; tên sản phẩm tiếng Việt cần kiểm tra cùng dataset thực tế và cấu hình MongoDB đang dùng.

### 4.4. Sort trên field mảng

Khi sort theo field có giá trị mảng hoặc đường dẫn trỏ vào nhiều phần tử, database phải áp dụng ngữ nghĩa sort riêng cho mảng; kết quả có thể không giống “lấy biến thể đầu tiên” hay “lấy phần tử mà filter vừa match”. Nếu nghiệp vụ yêu cầu sort theo giá biến thể thấp nhất, hãy **lưu/materialize giá nhỏ nhất**, hoặc dùng aggregation tạo field **minVariantPrice** với quy tắc chính xác trước khi sort.

Một field sort dùng thường xuyên nên được định nghĩa tường minh trong schema và hợp đồng API.

## 5. Index hỗ trợ lọc và sắp xếp

Trong mô hình document, index thường quyết định liệu truy vấn phân trang cần quét và sort số lượng lớn document hay có thể đọc một vùng index theo thứ tự đã có.

Ví dụ API:

~~~text
GET /products?categoryId=laptop&status=ACTIVE&sort=newest
~~~

Truy vấn:

~~~javascript
db.products.find({
  categoryId: "laptop",
  status: "ACTIVE"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Một compound index phù hợp:

~~~javascript
db.products.createIndex({
  categoryId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Trong trường hợp các field **categoryId** và **status** được lọc bằng equality, phần tiếp theo của index có thể hỗ trợ thứ tự sort **createdAt DESC, _id DESC**.

Quy tắc suy nghĩ phổ biến cho compound index là **Equality → Sort → Range (ESR)**, nhưng đây là *heuristic*; tính chọn lọc và các kiểu range cụ thể có thể làm kế hoạch tối ưu khác. Index thực tế cần dựa vào hình thái truy vấn chính, tần suất, lượng dữ liệu và số liệu explain.

### 5.1. Khi có nhiều kiểu sort

Một API cho phép:

- **newest:** createdAt DESC, _id DESC.
- **price_asc:** price ASC, _id ASC.
- **price_desc:** price DESC, _id DESC.
- **name:** tên theo collation mong muốn.

Những kiểu sort này có thể cần các index khác nhau. Không thể chỉ thêm mọi field vào một index rất dài rồi mặc định database đều sort hiệu quả.

Quy trình thiết kế:

1. Liệt kê các tổ hợp filter/sort thực sự được hỗ trợ và mức phổ biến của từng tổ hợp.
2. Tạo index cho các đường truy vấn quan trọng.
3. Giới hạn số trường sort/filter tùy ý nếu không có nhu cầu thực tế.
4. Đo **keysExamined, docsExamined, nReturned** và xem có stage sort tốn bộ nhớ hay không.
5. Tính chi phí index đối với tốc độ ghi, bộ nhớ và dung lượng lưu trữ.

### 5.2. Kiểm tra bằng explain

~~~javascript
db.products.find({
  categoryId: "laptop",
  status: "ACTIVE"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20)
  .explain("executionStats");
~~~

Một số thông tin hữu ích:

| Thông tin | Ý nghĩa sử dụng |
| --- | --- |
| **winningPlan** | Cách engine quyết định thực hiện truy vấn, có dùng index phù hợp hay không. |
| **totalKeysExamined** | Lượng entry index đã đọc trong truy vấn. |
| **totalDocsExamined** | Lượng document được xem xét/lấy ra để xử lý. |
| **nReturned** | Số document thực trả cho client. |
| **executionTimeMillis** | Thời gian thực thi được báo trong điều kiện đo; không thay toàn bộ latency end-to-end. |
| **SORT / IXSCAN / COLLSCAN** hoặc biểu diễn tương đương | Dấu hiệu cần điều tra sort, quét index hoặc quét collection, tùy engine/version. |

Một truy vấn trả 20 document nhưng phải duyệt hàng triệu document không thể coi là hiệu quả chỉ vì response có 20 item. Cũng không kết luận query “tốt” chỉ vì có IXSCAN; index có thể quét quá rộng, và còn chi phí lấy document, sắp xếp, network.

## 6. Pagination: chia tập kết quả mà không mất ý nghĩa thứ tự

Khi người dùng xem danh sách hàng nghìn sản phẩm, server không nên trả hết trong một response. Pagination cần giải quyết cả **tài nguyên**, **trải nghiệm** và **tính ổn định của kết quả**.

Hai nhóm kỹ thuật phổ biến:

1. **Offset pagination**: bỏ qua N document rồi lấy một trang.
2. **Keyset/cursor pagination**: dùng khóa sắp xếp cuối trang trước để tìm phần dữ liệu kế tiếp.

Mỗi chiến lược có đánh đổi khác nhau.

## 7. Offset pagination bằng skip/limit

Ví dụ mỗi trang có 20 sản phẩm:

~~~javascript
const page = 4;
const pageSize = 20;

db.products.find({
  categoryId: "laptop",
  status: "ACTIVE"
}).sort({
  createdAt: -1,
  _id: -1
}).skip((page - 1) * pageSize)
  .limit(pageSize);
~~~

Trang 4 bỏ qua 60 document đầu của tập đã sắp xếp rồi lấy 20 document.

### 7.1. Ưu điểm

- Dễ hiểu với UI dạng **trang 1, 2, 3…**.
- Truy cập trực tiếp trang N nếu có yêu cầu.
- Dễ áp dụng cho các danh sách nhỏ hoặc tập dữ liệu ít biến động.

### 7.2. Nhược điểm khi tập lớn

Với **page = 50.000, pageSize = 20**, offset gần một triệu document. Engine thường phải đi qua lượng lớn kết quả phù hợp trước khi có thể bỏ qua chúng; **skip không phải dịch con trỏ đến trang cuối với chi phí cố định**.

Ngoài chi phí, khi dữ liệu thay đổi giữa các request:

~~~text
Trang 1 (sort mới nhất):
[A, B, C]    -> client nhận

Có document X mới, đứng đầu:
[X, A, B, C, D, ...]

Trang 2 với skip(3), limit(3):
[C, D, E]    -> C bị lặp từ trang 1
~~~

Dù đã có tie-breaker, **offset vẫn bị dịch** khi có thêm hoặc xóa document phía trước trang hiện tại. Ở một số lịch cập nhật khác, document có thể bị bỏ sót.

### 7.3. Tổng số trang có thể tốn chi phí

API offset thường muốn trả **totalCount** và **totalPages**:

~~~javascript
const filter = { categoryId: "laptop", status: "ACTIVE" };

const totalCount = db.products.countDocuments(filter);
const pageItems = db.products.find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .skip(60)
  .limit(20);
~~~

Hai lệnh độc lập có thể quan sát dữ liệu ở các thời điểm khác nhau nếu có ghi đồng thời; **totalCount** chưa chắc khớp chính xác với tập kết quả của page. Đếm đúng toàn bộ tài liệu phù hợp filter cũng có chi phí; trong nhiều ứng dụng **hasMore** hoặc số lượng gần đúng hữu ích hơn việc tính số trang tuyệt đối.

## 8. Cursor/keyset pagination theo cặp (createdAt, _id)

Keyset pagination không nói “bỏ qua 60 phần tử”, mà nói “lấy phần tử **đứng sau khóa cuối trang trước** trong thứ tự đã chốt”.

Giả sử sort:

~~~javascript
.sort({ createdAt: -1, _id: -1 })
~~~

Ở trang trước, phần tử cuối có:

~~~text
createdAt = 2026-11-10T08:30:00Z
_id       = ObjectId("673354c8e3bcdf25a8901009")
~~~

Vì cả hai field sắp **giảm dần**, trang tiếp theo cần điều kiện:

~~~text
(createdAt < lastCreatedAt)
OR
(createdAt == lastCreatedAt AND _id < lastId)
~~~

Truy vấn MongoDB:

~~~javascript
const lastCreatedAt = ISODate("2026-11-10T08:30:00Z");
const lastId = ObjectId("673354c8e3bcdf25a8901009");

db.products.find({
  categoryId: "laptop",
  status: "ACTIVE",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(21); // yêu cầu 20 + 1 để xác định hasMore
~~~

**Giới hạn 21** cho một trang kích thước 20 để phát hiện còn trang tiếp theo:

- Lấy tối đa 21 document.
- Trả 20 document đầu.
- **hasMore = true** nếu có document thứ 21.
- **nextCursor** chứa cặp *(createdAt, _id)* của **document thứ 20**, không phải của document thứ 21.

Nếu lấy cursor từ phần tử thứ 21 rồi không trả phần tử ấy ở trang này, trang sau có thể bỏ sót nó.

### 8.1. Minh họa tuần tự

~~~text
Thứ tự giảm theo (createdAt, _id):

T9/C  T9/B  T9/A  T8/F  T8/E  T8/D  T7/Q ...

Trang 1, size 3:
T9/C  T9/B  T9/A
Cursor = (T9, A)

Trang 2, where key < (T9, A):
T8/F  T8/E  T8/D
Cursor = (T8, D)
~~~

Khi cặp khóa sort là duy nhất, điều kiện tiếp nối dựa vào đúng cặp khóa và thứ tự sort giúp tránh lỗi phân trang do **các giá trị createdAt trùng nhau**.

### 8.2. Khi có bản ghi mới

Nếu X được chèn với createdAt mới hơn đầu trang 1 sau lúc client đã lấy trang 1, keyset dựa vào khóa cuối vẫn đi tiếp phần dữ liệu **sau cursor**, nên không bị offset dịch bởi X đứng đầu. Tuy nhiên:

- Keyset **không tự tạo snapshot cố định** của toàn bộ collection.
- Document cũ bị xóa có thể không xuất hiện ở trang sau.
- Document bị đổi **createdAt** hay field sort có thể dịch sang vùng khác, dẫn đến lặp hoặc bỏ sót tùy lịch cập nhật.
- Nếu một document mới được backfill với timestamp **cũ hơn cursor**, nó có thể xuất hiện ở trang sau mặc dù không tồn tại lúc bắt đầu.

Với feed thông thường, điều đó thường chấp nhận được. Với **xuất báo cáo phải duyệt đúng một tập dữ liệu không đổi**, cần chiến lược snapshot, mốc thời gian đóng băng, cursor có version hoặc materialized result phù hợp.

### 8.3. Cursor phải mang theo điều gì?

Một payload cursor có thể gồm:

~~~json
{
  "v": 1,
  "sort": "newest",
  "filtersHash": "sha256-of-canonical-filters",
  "lastCreatedAt": "2026-11-10T08:30:00.000Z",
  "lastId": "673354c8e3bcdf25a8901009"
}
~~~

Có thể mã hóa payload dưới dạng token không trong suốt (opaque token) gửi cho client. Những thông tin thiết yếu:

- **Version** của định dạng token để có thể nâng cấp.
- **Sort** và **filter** hoặc fingerprint của chúng để không dùng cursor cũ cho truy vấn mới.
- **Last sort tuple** gồm tất cả tie-breaker với đúng kiểu BSON khi giải mã.
- **Tenant/authorization scope** nếu API có đa tenant, đảm bảo không dùng token để truy vấn vượt phạm vi.
- **Thời hạn** token nếu sản phẩm muốn giới hạn tuổi cursor.

Mã hóa Base64 chỉ là encoding, **không phải bảo vệ chống sửa đổi**. Nếu dữ liệu cursor ảnh hưởng đến quyền truy cập hoặc chi phí truy vấn, hãy dùng token ký/HMAC hoặc cơ chế xác thực thích hợp và luôn áp dụng lại quyền ở phía server. Không được coi các điều kiện trong cursor là nguồn sự thật cho phân quyền.

### 8.4. API response gợi ý

~~~json
{
  "items": [
    {
      "id": "67340d86e3bcdf25a8901001",
      "name": "Laptop Atlas 14",
      "price": "18500000.00",
      "currency": "VND"
    }
  ],
  "page": {
    "limit": 20,
    "hasMore": true,
    "nextCursor": "opaque-signed-token"
  }
}
~~~

Kiểu dữ liệu **price** trong API ví dụ này là chuỗi decimal để tránh mất độ chính xác ở client JavaScript. Không phải mọi API đều phải chọn kiểu chuỗi; điều cần giữ là hợp đồng serialization nhất quán.

## 9. Cursor pagination với sort tăng dần và sort nhiều khóa

Nếu sort tăng:

~~~javascript
.sort({ price: 1, _id: 1 })
~~~

điều kiện trang tiếp theo là:

~~~javascript
{
  $or: [
    { price: { $gt: lastPrice } },
    { price: lastPrice, _id: { $gt: lastId } }
  ]
}
~~~

Nếu sort theo **price ASC, createdAt DESC, _id DESC**, điều kiện tiếp nối phải xây theo thứ tự từ điển với chiều so sánh tương ứng:

~~~text
price > lastPrice
OR (price = lastPrice AND createdAt < lastCreatedAt)
OR (price = lastPrice AND createdAt = lastCreatedAt AND _id < lastId)
~~~

Không thể thay bằng một phép so sánh trên **_id** duy nhất khi API đang sort theo giá. Với sort theo thứ tự nhiều field, thiết kế cursor và index phải tương thích nhau.

Khi sort theo field có thể thay đổi liên tục (stock, lượt yêu thích, ranking, giá), keyset pagination khó giữ kết quả ổn định xuyên nhiều trang. Các lựa chọn tùy mục tiêu:

1. Chấp nhận feed động và ghi rõ trạng thái có thể đổi vị trí.
2. Dùng field sắp xếp ổn định hoặc snapshot/version của dataset.
3. Cố định danh sách ID/result trong một job truy vấn, rồi phân trang trên tập cố định.
4. Với search engine chuyên dụng, dùng cơ chế **search-after** và snapshot/point-in-time tương ứng nếu hệ hỗ trợ.

Không có lựa chọn nào miễn phí; cần chọn theo độ chính xác, dữ liệu thay đổi, dung lượng và thời gian giữ trạng thái.

## 10. Aggregation: từ tài liệu thành thông tin

**Aggregation** xử lý một tập tài liệu để tạo kết quả đã lọc, biến đổi, nhóm hoặc tính toán. Trong MongoDB, **aggregation pipeline** gồm chuỗi stage; mỗi stage nhận kết quả của stage trước.

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$customerId", orderCount: { $sum: 1 } } },
  { $sort: { orderCount: -1, _id: 1 } },
  { $limit: 10 }
]);
~~~

Luồng xử lý khái niệm:

~~~mermaid
flowchart LR
    A[orders] --> B["$match PAID"]
    B --> C["$group by customerId"]
    C --> D["$sort orderCount DESC"]
    D --> E["$limit 10"]
    E --> F[Top customers]
~~~

Các stage phổ biến:

| Stage | Công việc | Tình huống |
| --- | --- | --- |
| **$match** | Lọc document theo điều kiện. | Đơn đã thanh toán trong khoảng ngày. |
| **$project** | Chọn, đổi tên, tạo field. | DTO cho response, bóc nested field. |
| **$set / $addFields** | Bổ sung hoặc tính lại field mà vẫn giữ field khác. | Tạo amountNormalized, bucket. |
| **$group** | Gom document theo khóa, tính accumulator. | Tổng doanh thu theo customer hoặc ngày. |
| **$sort** | Sắp kết quả trung gian/đầu ra. | Top N hoặc biểu đồ theo thời gian. |
| **$limit / $skip** | Chỉ lấy một phần kết quả. | Top N hoặc phân trang. |
| **$unwind** | Biến các phần tử mảng thành nhiều document trong pipeline. | Tổng hợp theo order.items[].sku. |
| **$lookup** | Kết hợp dữ liệu từ collection khác theo điều kiện hỗ trợ. | Gắn tên customer vào report. |
| **$facet** | Chạy nhiều nhánh pipeline trên cùng tập đầu vào stage. | Data page và count/nhóm thống kê. |
| **$count** | Đếm số document đi tới stage. | Tổng số document sau filter. |
| **$bucket / $bucketAuto** | Nhóm theo khoảng giá trị. | Biểu đồ phân bố giá. |

Không nên coi aggregation chỉ là “SQL GROUP BY phiên bản MongoDB”. Các stage có thể biến đổi cấu trúc tài liệu, thao tác mảng, kết hợp collection và tính toán đa tầng.

## 11. Ví dụ tổng hợp doanh thu theo ngày

Giả sử collection **orders**:

~~~javascript
{
  _id: ObjectId("67348a5de3bcdf25a8902088"),
  orderId: "ORD-901",
  customerId: "CUS-14",
  status: "PAID",
  paidAt: ISODate("2026-11-10T04:20:00Z"),
  totalAmount: NumberDecimal("250000.00"),
  currency: "VND",
  items: [
    { sku: "A", quantity: 2, unitPrice: NumberDecimal("100000.00") },
    { sku: "B", quantity: 1, unitPrice: NumberDecimal("50000.00") }
  ]
}
~~~

Muốn báo cáo **doanh thu ghi nhận từ các đơn PAID theo ngày địa phương Việt Nam** trong khoảng thời gian cụ thể:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      currency: "VND",
      paidAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$paidAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 },
      grossRevenue: { $sum: "$totalAmount" },
      averageOrderValue: { $avg: "$totalAmount" }
    }
  },
  {
    $sort: { _id: 1 }
  },
  {
    $project: {
      _id: 0,
      day: "$_id",
      orderCount: 1,
      grossRevenue: 1,
      averageOrderValue: 1
    }
  }
]);
~~~

**Điểm cần thỏa thuận nghiệp vụ trước khi tin báo cáo:**

- **PAID** là trạng thái ghi nhận doanh thu hay phải dùng trạng thái **SETTLED**? Các đơn hủy, hoàn tiền xử lý thế nào?
- **paidAt** có phải mốc nghiệp vụ đúng? Báo cáo “ngày Việt Nam” nhưng filter dùng khoảng UTC phải tính đúng ranh giới tháng theo múi giờ.
- **totalAmount** đã bao gồm thuế, vận chuyển, giảm giá hay chưa? Có hoàn tiền từng phần không?
- Có nhiều **currency** không? Không cộng thẳng VND và USD thành một số tổng.
- Có thể thiếu **paidAt** hay **totalAmount** không? Dữ liệu cần được chuẩn hóa và kiểm tra kiểu trước khi tổng hợp.
- **Gross revenue**, **net revenue**, **booked revenue** và **cash received** có thể là bốn số khác nhau.

Ví dụ chọn khoảng UTC từ 1/11 đến 1/12 để dễ đọc cú pháp. Nếu mục tiêu là **cả tháng 11 theo múi giờ Việt Nam**, phải chuyển đúng hai mốc 00:00 ngày 1/11 và 1/12 của Việt Nam thành UTC rồi mới lọc, nếu không các giao dịch sát nửa đêm sẽ bị đưa nhầm tháng.

### 11.1. Vì sao đặt $match sớm?

Bộ lọc **status, currency, paidAt** giúp giảm số document đi vào **$group** và có thể tận dụng index:

~~~javascript
db.orders.createIndex({
  status: 1,
  currency: 1,
  paidAt: 1
});
~~~

Tuy nhiên, không phải mọi pipeline đều cần một **$project** sớm. Optimizer có thể tự quyết định cách đẩy projection xuống. Nếu $project làm mất field cần cho $match/$sort, hoặc tính toán biến đổi khiến index không được dùng như mong muốn, pipeline có thể chậm hơn.

Với báo cáo lớn, hãy xem **aggregate(...).explain("executionStats")** theo API/phiên bản hỗ trợ; chú ý lượng document vào group, stage sort, lượng đọc index, bộ nhớ và thời gian.

### 11.2. $group xử lý kiểu số thế nào?

Không nên cộng giá tiền lưu kiểu chuỗi:

~~~javascript
{ totalAmount: "250000" }
~~~

Lưu bằng kiểu số phù hợp (ví dụ **Decimal128** hoặc số nguyên đơn vị nhỏ nhất) giúp thao tác cộng và chính sách làm tròn nhất quán hơn. Nếu kết quả trả client JavaScript, cần serializer giữ đủ độ chính xác; một số ứng dụng trả Decimal128 thành chuỗi decimal.

Hàm **$sum** không biến một báo cáo thành ledger tài chính. Nếu dữ liệu nguồn có đơn trùng, refund chưa ghi nhận hoặc currency lẫn lộn, phép cộng vẫn chạy nhưng kết quả nghiệp vụ sai.

## 12. Aggregation với mảng bằng $unwind

Đơn hàng chứa **items** là mảng các dòng sản phẩm. Muốn biết số lượng đã bán theo SKU, cần biến từng item thành một dòng logic:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      paidAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      unitsSold: { $sum: "$items.quantity" },
      lineRevenue: {
        $sum: {
          $multiply: [
            "$items.quantity",
            "$items.unitPrice"
          ]
        }
      }
    }
  },
  {
    $sort: { unitsSold: -1, _id: 1 }
  },
  { $limit: 20 }
]);
~~~

Nếu một order có 5 items thì sau **$unwind** nó có thể thành 5 record trung gian. Vì vậy:

- **$sum: 1** sau unwind đếm số dòng item, **không còn đếm số order**.
- Nếu cần số order duy nhất trên mỗi SKU, phải dùng chiến lược phân biệt order ID phù hợp.
- Nếu mảng lớn, fan-out có thể làm tăng đáng kể số record phải group/sort.
- Mảng rỗng hoặc thiếu field **items** có thể bị bỏ khỏi kết quả theo mặc định; nếu cần giữ, phải cấu hình **preserveNullAndEmptyArrays** và tính tiếp phù hợp.
- Tính doanh thu từng dòng theo **quantity × unitPrice** có thể khác totalAmount của order vì thuế, khuyến mãi, phí ship, refund và làm tròn.

Đây là lý do cần hiểu **cấu trúc document lồng nhau** trước khi xây aggregation.

## 13. Top N, nhóm theo thuộc tính và phân bố giá

### 13.1. Top danh mục theo số sản phẩm ACTIVE

~~~javascript
db.products.aggregate([
  { $match: { status: "ACTIVE" } },
  {
    $group: {
      _id: "$categoryId",
      productCount: { $sum: 1 }
    }
  },
  { $sort: { productCount: -1, _id: 1 } },
  { $limit: 10 },
  {
    $project: {
      _id: 0,
      categoryId: "$_id",
      productCount: 1
    }
  }
]);
~~~

Ở đây **productCount** là số document sản phẩm ACTIVE, không phải số lượng tồn kho và không phải số SKU biến thể nếu mỗi product chứa nhiều variants.

### 13.2. Phân bố sản phẩm theo khoảng giá

Có thể nhóm theo các dải giá cố định:

~~~javascript
db.products.aggregate([
  {
    $match: {
      status: "ACTIVE",
      currency: "VND",
      price: { $gte: NumberDecimal("0") }
    }
  },
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("1000000"),
        NumberDecimal("5000000"),
        NumberDecimal("10000000"),
        NumberDecimal("50000000")
      ],
      default: "50000000+",
      output: {
        productCount: { $sum: 1 }
      }
    }
  }
]);
~~~

Các khoảng trong **$bucket** được xác định bởi các ranh giới liên tiếp; cần ghi nhãn khoảng đúng quy tắc bao gồm ranh giới dưới và loại trừ ranh giới trên. Giá bằng hoặc cao hơn mốc cuối vào nhóm **default** trong ví dụ. Các giá trị không thuộc khoảng còn lại (sau filter) cũng cần được hiểu theo quy tắc default.

Có thể dùng **$bucketAuto** để để engine đề xuất khoảng dựa trên phân bố, nhưng khi hiển thị báo cáo định kỳ cho nghiệp vụ, các khoảng cố định thường dễ so sánh hơn qua thời gian.

## 14. $lookup: kết hợp document từ collection khác

Document model thường ưu tiên **embedding** cho dữ liệu có quan hệ đọc cùng nhau, nhưng không phải mọi quan hệ đều nên nhúng. **$lookup** hỗ trợ phép kết hợp theo điều kiện từ collection khác.

Ví dụ order có **customerId** và danh sách khách hàng thuộc collection **customers**:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { paidAt: -1, _id: -1 } },
  { $limit: 20 },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "customerId",
      as: "customer"
    }
  },
  {
    $unwind: {
      path: "$customer",
      preserveNullAndEmptyArrays: true
    }
  },
  {
    $project: {
      _id: 0,
      orderId: 1,
      paidAt: 1,
      totalAmount: 1,
      customerName: "$customer.displayName"
    }
  }
]);
~~~

Ví dụ giới hạn 20 order **trước khi lookup** để tránh join trên toàn bộ collection khi chỉ cần trang mới nhất. Đây là lựa chọn phù hợp với mục đích “liệt kê 20 order mới nhất”; nếu mục tiêu là lọc/sort theo tên khách hàng trước khi phân trang thì việc đặt limit sớm sẽ **làm sai kết quả**.

Các điểm phải kiểm tra:

- **Cardinality:** một customerId có đúng một customer hay có thể tạo nhiều kết quả? Nếu join trả mảng nhiều phần tử, **$unwind** sẽ nhân số order ở đầu ra.
- **Index phía foreign collection:** ví dụ cần cân nhắc index trên **customers.customerId**.
- **Missing reference:** order có thể trỏ tới customer đã xóa; cần nêu trường hợp không có customer.
- **Khối lượng dữ liệu:** lookup rộng và pipeline phức tạp có thể ngốn tài nguyên hơn việc lưu một snapshot tên khách hàng trong order khi nghiệp vụ chỉ cần tên tại thời điểm đặt.
- **Ý nghĩa nhất quán:** nếu tên khách hàng được cập nhật giữa các request báo cáo, join có thể cho tên hiện tại thay vì tên tại thời điểm giao dịch.

Embedding, referencing và $lookup là lựa chọn mô hình dữ liệu; không có quy tắc “mọi quan hệ phải lookup” hoặc “không bao giờ dùng lookup”.

## 15. Kết hợp pagination và aggregation

Một danh sách API có thể cần vừa trả **data page**, vừa trả **totalCount**. MongoDB có thể dùng **$facet**:

~~~javascript
db.products.aggregate([
  {
    $match: {
      categoryId: "laptop",
      status: "ACTIVE"
    }
  },
  {
    $facet: {
      items: [
        { $sort: { createdAt: -1, _id: -1 } },
        { $skip: 40 },
        { $limit: 20 },
        {
          $project: {
            _id: 0,
            name: 1,
            price: 1,
            createdAt: 1
          }
        }
      ],
      metadata: [
        { $count: "totalCount" }
      ]
    }
  }
]);
~~~

**$facet** chuyển cùng một tập đầu vào sang nhiều pipeline con. Nhánh **items** có thể tạo trang 3; nhánh **metadata** đếm toàn bộ document phù hợp filter. Với tập rất lớn, việc đếm chính xác và sort/skip có thể tốn chi phí đáng kể; $facet có giới hạn tài nguyên/kích thước đầu ra riêng, không phải công cụ “đếm và phân trang miễn phí”.

Nếu UI chỉ cần biết có trang sau, thường có thể **limit(pageSize + 1)** ở truy vấn chính mà không cần count chính xác. Với danh sách lớn có nhiều lượt đọc, cân nhắc **pre-aggregated count**, cache có chính sách sai lệch được công bố hoặc endpoint count chạy theo yêu cầu riêng.

### 15.1. Phân trang kết quả đã $group

Giả sử báo cáo nhóm theo customerId rồi sort theo **totalRevenue**:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$customerId",
      totalRevenue: { $sum: "$totalAmount" }
    }
  },
  { $sort: { totalRevenue: -1, _id: 1 } },
  { $limit: 20 }
]);
~~~

Lúc này mỗi record đầu ra là **một customer aggregate**, không còn là một order gốc. Cursor phải dựa trên **(totalRevenue, customerId)** sau group; cursor theo **orders._id** sẽ sai nghĩa.

Nếu doanh thu tiếp tục biến động, vị trí customer trong bảng xếp hạng thay đổi giữa các trang. Báo cáo cần tính ổn định có thể materialize snapshot tổng hợp theo chu kỳ, gắn **reportVersion/asOf**, rồi phân trang trên tập đã cố định. Với dữ liệu nhóm có cardinality rất lớn, sort tất cả nhóm mỗi request có thể tốn kém; cần cân nhắc kết quả tổng hợp lưu sẵn.

## 16. Tổng hợp trực tiếp hay materialized/pre-aggregated views?

Không phải dashboard nào cũng nên quét hàng triệu đơn hàng ở mỗi lần refresh. Có thể lựa chọn ba cách:

| Phương án | Mô tả | Lợi ích | Đánh đổi |
| --- | --- | --- | --- |
| **Aggregation trực tiếp** | Chạy pipeline trên collection gốc khi client gọi. | Dữ liệu gần thời điểm đọc, đơn giản với báo cáo nhỏ. | Chi phí lặp lại, dễ quá tải khi nhiều người xem, có thể cần index/phân vùng phù hợp. |
| **Pre-aggregation** | Job định kỳ tổng hợp từ dữ liệu gốc vào collection chỉ số. | Đọc dashboard nhanh, kết quả có thể sắp xếp/phân trang dễ. | Dữ liệu chậm hội tụ, cần lịch chạy, xử lý job lỗi và đối soát. |
| **Incremental materialization** | Cập nhật bản tổng khi có sự kiện thay đổi. | Có thể cho độ trễ thấp và giảm scan toàn bộ. | Phức tạp hơn với duplicate, update, delete, refund, out-of-order events và replay. |

Ví dụ lưu kết quả doanh thu ngày:

~~~javascript
{
  _id: "revenue:VND:2026-11-10",
  day: "2026-11-10",
  currency: "VND",
  grossRevenue: NumberDecimal("186500000.00"),
  orderCount: 742,
  dataThrough: ISODate("2026-11-10T23:59:59Z"),
  computedAt: ISODate("2026-11-11T00:10:00Z"),
  reportVersion: 5
}
~~~

**dataThrough** phải được định nghĩa rõ theo timezone và cơ chế xử lý late events; một timestamp không tự chứng minh không còn event đến trễ. Có thể thêm trạng thái **PROVISIONAL/FINAL**, khoảng thời gian nước rút cho dữ liệu đến trễ và lệnh rebuild từ nguồn chuẩn.

Nếu một message đơn hàng đến hai lần, job incremental không được cộng doanh thu hai lần. Cần **idempotent event processing**, khóa xử lý hoặc reconciliation. Khi đơn bị hoàn tiền, việc giảm/điều chỉnh doanh thu phải phản ánh đúng định nghĩa nghiệp vụ, không chỉ xử lý lần INSERT đầu.

### 16.1. Tính nhất quán giữa dữ liệu gốc và bản tổng

Một order được ghi thành công lúc T0, bản tổng cập nhật lúc T1. Trong khoảng T0–T1, query dashboard có thể vẫn trả số cũ. Hợp đồng API nên mô tả:

- **Nguồn chuẩn** của dữ liệu doanh thu là gì.
- **Độ trễ tối đa chấp nhận được** để cập nhật bản tổng.
- **Thời điểm cuối** mà kết quả đã phản ánh (asOf/dataThrough).
- **Cơ chế khi job chậm/lỗi**: cảnh báo stale, giữ số cũ có chú thích hay chặn truy vấn.
- **Cách khôi phục**: rebuild aggregation từ dữ liệu nguồn hoặc replay event theo idempotency.

Trong hệ phân tán, “data has been acknowledged” và “all materialized views contain the new value” là hai cột mốc khác nhau.

## 17. Phân quyền và khả năng lộ dữ liệu qua truy vấn

Một API đa tenant có thể cho filter **tenantId** từ identity của request:

~~~javascript
const filter = {
  tenantId: authenticatedTenantId,
  status: "ACTIVE"
};
~~~

Không được tin tenantId nằm trong query string hay cursor của client mà bỏ qua kiểm tra quyền. Projection giúp giảm dữ liệu trả về, nhưng nếu quyền truy vấn không đúng, client vẫn có thể xem document của tenant khác hoặc suy ra số lượng/nhóm thông qua aggregation.

Các quy tắc thực hành:

1. Mọi truy vấn phân trang và count/aggregate phải áp dụng **cùng ranh giới quyền**.
2. Whitelist field sort, filter, projection được client phép yêu cầu; không chuyển nguyên object query tùy ý từ HTTP vào database.
3. API public nên có output DTO rõ ràng; field nội bộ không được lộ do projection thiếu.
4. Kiểm soát chi phí query: hạn chế pageSize, số pipeline stage do client điều khiển, thời gian query và phạm vi thời gian báo cáo.
5. Chỉ đưa thông tin cần thiết vào cursor; nếu có dữ liệu nhạy cảm thì cần bảo vệ nội dung token phù hợp.
6. Không trả totalCount/aggregation ở phạm vi rộng hơn quyền người gọi.

## 18. Hiệu năng: những điểm hay tạo nghẽn

### 18.1. Sort nhiều document mà không có index thích hợp

Một pipeline:

~~~javascript
db.products.aggregate([
  { $match: { status: "ACTIVE" } },
  { $sort: { price: 1 } },
  { $limit: 20 }
]);
~~~

có thể phải duyệt/sort nhiều document nếu index không hỗ trợ đầy đủ. Tùy cách optimizer xử lý, một **top-k sort** có thể giảm bộ nhớ so với sort toàn bộ, nhưng điều đó không thay chi phí lọc/đọc dữ liệu. Index phải được thiết kế cho filter + sort thực tế.

### 18.2. Deep skip

**skip(500000)** làm truy vấn lãng phí công đi qua nhiều phần tử trước khi lấy trang. Nếu UI chỉ cần **next/previous**, keyset thường phù hợp hơn cho danh sách lớn. Nếu cần nhảy tới trang bất kỳ, hãy cân nhắc giới hạn độ sâu offset hoặc dùng materialized snapshot.

### 18.3. $unwind khuếch đại số dòng

Một order có 200 items nhân thành 200 bản ghi trung gian. Với 1 triệu orders, số phần tử trung gian có thể lớn hơn rất nhiều số order. Lọc càng sớm càng tốt theo nghiệp vụ, dùng schema phù hợp và xét pre-aggregation nếu nhóm theo item quá thường xuyên.

### 18.4. $lookup có fan-out

Join một order với nhiều document customer không duy nhất có thể nhân số dòng kết quả, làm sai count và tăng bộ nhớ. Cần index phía được lookup, quan hệ cardinality rõ ràng và kiểm tra dữ liệu không khớp.

### 18.5. Aggregation không giới hạn phạm vi

Báo cáo “tổng doanh thu tất cả lịch sử” chạy mỗi giây cho nhiều dashboard dễ gây áp lực CPU/I/O. Thường nên có filter khoảng thời gian, cache hoặc pre-aggregate, đồng thời công bố thời điểm số liệu được cập nhật.

### 18.6. Quá nhiều index

Mỗi index có chi phí lưu trữ và cập nhật. Thêm index cho mọi kiểu sort tùy ý làm ghi chậm hơn và tăng nhu cầu tài nguyên. Ưu tiên những đường query có tần suất/sản lượng dữ liệu đáng kể.

### 18.7. Tập kết quả và giới hạn bộ nhớ

Các stage như **$group, $sort, $facet** có thể tiêu thụ tài nguyên đáng kể. MongoDB có cơ chế quản lý giới hạn bộ nhớ và tùy chọn **allowDiskUse** trong những ngữ cảnh được hỗ trợ, nhưng spill ra disk không biến pipeline nặng thành truy vấn rẻ. Một số stage có giới hạn riêng ngay cả khi cho phép disk; hãy đọc giới hạn theo phiên bản triển khai và đo áp lực tài nguyên.

## 19. Java/Spring Data MongoDB: viết API phân trang có chủ đích

Trong Spring Data MongoDB, có thể dùng **MongoTemplate**, **Query**, **Criteria**, **Sort** để xây truy vấn. Ví dụ đơn giản với trang đầu kiểu newest:

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class ProductQueryService {
    private final MongoTemplate mongo;

    public ProductQueryService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<ProductDocument> firstPage(
        String categoryId,
        int pageSize
    ) {
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Invalid pageSize");
        }

        Query query = new Query(
            Criteria.where("categoryId").is(categoryId)
                .and("status").is("ACTIVE")
        );

        query.fields().include("name", "price", "currency", "createdAt");
        query.with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("_id")
        ));
        query.limit(pageSize + 1);

        return mongo.find(query, ProductDocument.class, "products");
    }
}
~~~

Đây là minh họa cách dựng **projection + filter + sort + limit**. Dữ liệu thực tế thường cần response DTO riêng (đặc biệt khi projection khiến field trong entity không được nạp), handling **pageSize + 1** và next cursor từ document cuối thực trả. Không coi một document chỉ được nạp một phần là aggregate đầy đủ để **save** trở lại DB; ghi đè theo entity thiếu field có thể gây sai dữ liệu tùy cơ chế lưu.

### 19.1. Repository paging so với keyset

Spring Data cung cấp khái niệm **Pageable**, **Page**, **Slice** và các cơ chế truy vấn tương ứng tùy module/version. Khi dùng pagination kiểu page number, cần xem implementation có dùng **skip/limit** và có chạy **count** không.

- **Page** thường nhằm cung cấp tổng số item/trang và có thể cần count.
- **Slice** tập trung vào biết còn phần tiếp theo, có thể tránh một số chi phí count.
- **Cursor/keyset** đòi điều kiện tiếp nối dựa trên sort tuple, đôi khi cần truy vấn tự dựng hoặc API hỗ trợ theo phiên bản Spring Data dùng.

Nếu API cần scale tốt ở trang sâu, không nên chọn **Page** theo thói quen mà bỏ qua chi phí offset/count.

## 20. Các lỗi thường gặp và cách sửa

| Lỗi | Tác động | Hướng sửa |
| --- | --- | --- |
| Không chỉ định **sort** | Thứ tự kết quả không có hợp đồng. | Thêm sort theo nghiệp vụ. |
| Sort theo **createdAt** nhưng không có tie-breaker | Tài liệu trùng timestamp có thể đổi vị trí giữa trang. | Thêm **_id** hoặc khóa duy nhất phù hợp. |
| Dùng skip sâu | Độ trễ tăng theo độ sâu trang. | Keyset/cursor hoặc giới hạn offset. |
| Cursor chỉ chứa _id khi sort theo price | Trang tiếp theo sai thứ tự, có thể bỏ/lặp dữ liệu. | Cursor chứa đủ sort tuple, đúng chiều so sánh. |
| Dùng **$project** để che dữ liệu nhạy cảm nhưng không có authorization | Nguy cơ lộ thông tin do thay đổi query/field. | Phân quyền và allowlist ở API/database. |
| Trả mọi field của document | Payload lớn, lộ field nội bộ. | Projection/DTO theo use case. |
| Đặt **$limit** trước filter/group cần xét toàn bộ tập | Sai kết quả báo cáo. | Xác định ngữ nghĩa pipeline trước khi tối ưu. |
| **$unwind** rồi dùng **$sum:1** để đếm order | Đếm số dòng item thay vì số đơn. | Group theo order ID hoặc thay đổi chiến lược đếm. |
| Cộng tiền khác đơn vị/currency | Báo cáo vô nghĩa. | Nhóm theo currency hoặc đổi tiền theo quy tắc được duyệt. |
| Dùng giá hiện tại để tính doanh thu lịch sử | Không phản ánh giá lúc giao dịch. | Dùng snapshot line item trên order và logic hoàn tiền. |
| Đếm chính xác toàn bộ tập ở mỗi request | Tăng I/O/CPU và độ trễ. | Dùng hasMore, cache, precomputed count tùy nhu cầu. |
| Xem IXSCAN là đủ để kết luận nhanh | Có thể quét hàng triệu key hoặc FETCH nhiều document. | Đọc executionStats và đo end-to-end. |
| Dùng live pagination cho báo cáo cần snapshot | Lặp hoặc mất record khi dữ liệu thay đổi. | Dùng snapshot/mốc version/materialized result. |

## 21. Bài thực hành: danh sách sản phẩm và bảng thống kê

Giả sử một collection products có các trường **_id, categoryId, status, createdAt, price, name, currency** và collection orders có **status, paidAt, totalAmount, items**. Hãy xây ba endpoint có hợp đồng rõ ràng:

### Bài A: Danh sách sản phẩm mới nhất

~~~text
GET /products?categoryId=laptop&limit=20&cursor=...
~~~

Yêu cầu:

- Chỉ lấy **status = ACTIVE**.
- Sắp theo **createdAt DESC, _id DESC**.
- Chỉ trả **id, name, price, currency, createdAt**.
- Dùng **limit + 1**, **nextCursor**, **hasMore**, giới hạn limit tối đa 100.
- Không để client tự truyền raw MongoDB query.
- Lựa chọn index phù hợp với filter và sort.

### Bài B: Phân trang sản phẩm theo giá

~~~text
GET /products?categoryId=laptop&sort=price_asc&limit=20
~~~

Yêu cầu:

- **price ASC, _id ASC**.
- Cursor sau trang trước chứa **lastPrice** và **lastId**.
- Lọc trang sau bằng điều kiện từ điển tương ứng.
- Đảm bảo **price** có kiểu thống nhất và so sánh trong cùng currency.
- Ghi rõ rằng nếu giá thay đổi giữa các request, thứ tự có thể dịch chuyển.

### Bài C: Báo cáo sản phẩm bán chạy

~~~text
GET /reports/top-products?from=...&to=...&limit=20
~~~

Yêu cầu:

- Chọn các order đã ghi nhận đúng theo định nghĩa nghiệp vụ.
- **$unwind** từng item, nhóm theo SKU, tính tổng số lượng.
- Sắp **unitsSold DESC, sku ASC** để có tie-breaker.
- Không tự coi mỗi dòng item là một order.
- Thống nhất timezone, xử lý hoàn trả và dữ liệu đến trễ.
- Xem xét pre-aggregation nếu báo cáo được truy vấn liên tục trên dữ liệu lớn.

### Một bảng nghiệm thu minh họa

| ID | Tiêu chí | Cách xác minh |
| --- | --- | --- |
| **AC-01** | Mỗi trang danh sách có tối đa 20 item và chỉ gồm các field được phép. | Kiểm tra schema của response, including nested fields. |
| **AC-02** | Thứ tự newest luôn theo cặp *(createdAt, _id)*. | Sinh nhiều item trùng timestamp và đối chiếu kết quả. |
| **AC-03** | Không lặp/mất item chỉ vì các giá trị createdAt bằng nhau khi lật trang. | Đọc toàn bộ một dataset tĩnh với cursor, so sánh tập ID. |
| **AC-04** | Với dữ liệu mới chèn ở đầu, trang tiếp theo theo cursor vẫn đi tiếp từ khóa cuối. | Chèn X sau trang 1 rồi đọc trang 2. |
| **AC-05** | Pipeline bán chạy tính đúng số lượng trong các items của order PAID. | So với tập ví dụ nhỏ có thể tính tay. |
| **AC-06** | Truy vấn có index phù hợp và số document/key scan không tăng bất thường so với số kết quả. | Phân tích explain trên dataset đại diện. |
| **AC-07** | Không trả dữ liệu của tenant khác trong list/count/report. | Kiểm tra phân quyền với identity khác nhau. |

Các ngưỡng hiệu năng cụ thể như p95/p99 cần được bổ sung dựa trên tải, kích thước dữ liệu và môi trường đã thống nhất. Một bảng đúng chức năng chưa chứng minh hệ chịu được lượng truy vấn trong production.

## 22. Chọn chiến lược theo nhu cầu thực

~~~mermaid
flowchart TD
    A[Thiết kế API đọc document] --> B{Chỉ cần field gốc?}
    B -->|Có| C[Filter + projection]
    B -->|Không| D[Aggregation project/transform]
    C --> E{Cần danh sách nhiều trang?}
    D --> E
    E -->|Không| F[Sort và limit phù hợp]
    E -->|Có| G{Cần nhảy trực tiếp trang N?}
    G -->|Có| H[Offset, giới hạn độ sâu]
    G -->|Không| I[Keyset/cursor với sort tuple duy nhất]
    F --> J{Có nhóm/tính tổng?}
    H --> J
    I --> J
    J -->|Có| K[Group/unwind/lookup hoặc pre-aggregate]
    J -->|Không| L[Response DTO]
    K --> L
    L --> M[Explain, đo tải và kiểm tra correctness]
~~~

Một quy trình thiết kế đủ rõ có thể diễn đạt như sau:

1. **Viết câu hỏi của màn hình:** danh sách nào, theo filter nào, field nào, người dùng có quyền xem gì.
2. **Chọn một thứ tự xác định:** sort đúng nghiệp vụ, thêm tie-breaker duy nhất, xét null/kiểu dữ liệu và collation.
3. **Chọn pagination:** offset khi cần page number trên tập phù hợp; cursor khi cần duyệt tuần tự sâu và ổn định hơn trước insert phía đầu.
4. **Thiết kế index theo filter/sort:** không thêm index tùy ý; dùng explain và workload đại diện để xác minh.
5. **Định nghĩa aggregation đúng nghĩa:** nhóm theo khóa nào, sau unwind đang đếm gì, tổng tiền/quantity có cùng đơn vị và trạng thái không.
6. **Quy định tính nhất quán:** danh sách live có thể thay đổi hay phải snapshot, kết quả tổng hợp có độ trễ cập nhật bao lâu.
7. **Đo và quan sát:** response size, độ trễ p95/p99, lượng key/document scan, bộ nhớ sort/group, số lần spill, tỷ lệ lỗi và độ tươi dữ liệu.

## Kết luận

Trong document database, **projection** quyết định hình dạng dữ liệu trả về; **sorting** tạo thứ tự xác định; **pagination** đảm bảo ứng dụng không phải tải toàn bộ tập kết quả; **aggregation** chuyển các document, kể cả dữ liệu mảng lồng nhau, thành báo cáo và thống kê có ý nghĩa.

Điểm then chốt là các kỹ thuật này **liên quan chặt chẽ**: projection phải phù hợp API và quyền đọc; sort cần khóa phụ duy nhất để cursor không nhập nhằng; pagination phải hiểu dữ liệu có thể thay đổi; aggregation phải giữ đúng nghĩa nghiệp vụ trước và sau khi nhóm, unwind hay join. Kết hợp với index, explain, DTO và một hợp đồng nhất quán rõ ràng, ta có thể thiết kế truy vấn NoSQL vừa trả đúng dữ liệu, vừa mở rộng được khi tập document và lưu lượng tăng.
