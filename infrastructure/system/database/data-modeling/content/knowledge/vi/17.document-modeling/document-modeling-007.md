# Chọn khóa tài liệu, chỉ mục và các trường cần truy vấn

## 1. Từ yêu cầu nghiệp vụ đến khóa và đường truy cập

Trong mô hình tài liệu (*document model*), một cấu trúc JSON dễ đọc chưa đủ để kết luận thiết kế dữ liệu tốt. Một tài liệu có thể mô tả đầy đủ khóa học, đơn hàng hoặc sản phẩm, nhưng nếu ứng dụng không thể tìm đúng tài liệu, lọc theo điều kiện thường dùng hoặc sắp xếp danh sách với chi phí hợp lý, mô hình đó sẽ khó vận hành khi dữ liệu lớn.

Ba quyết định phải được thiết kế **cùng nhau**:

1. **Khóa tài liệu:** mỗi tài liệu được nhận diện bằng gì, khóa có ổn định và duy nhất trong phạm vi cần thiết không?
2. **Các trường cần truy vấn:** nghiệp vụ tìm, lọc, sắp xếp, phân trang, tổng hợp và cập nhật dựa trên những trường nào?
3. **Chỉ mục:** hệ lưu trữ cần cấu trúc truy cập bổ sung nào để đáp ứng các thao tác đó với độ trễ và chi phí chấp nhận được?

Bài học nằm trong chương **Mô hình tài liệu**, thuộc phạm vi **DATABASE_DATA_MODELING**. Mục tiêu của mô-đun là rèn khả năng chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ và ràng buộc tới chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; đồng thời cân nhắc mô hình quan hệ, tài liệu, đồ thị hoặc phân tích theo yêu cầu thực tế.

Sau bài này, bạn có thể:

- Phân biệt khóa lưu trữ, khóa nghiệp vụ, khóa tham chiếu và khóa phân vùng.
- Thiết kế định danh ổn định, phạm vi duy nhất và quy tắc cập nhật/xóa phù hợp.
- Lập bảng **hình dạng truy vấn** (*query shape*) từ chức năng nghiệp vụ.
- Chọn chỉ mục đơn, chỉ mục ghép, chỉ mục trên trường lồng nhau hoặc mảng theo truy vấn chủ đạo.
- Sử dụng **projection**, thứ tự sắp xếp ổn định và phân trang theo cursor khi phù hợp.
- Đánh giá chi phí chỉ mục bằng kế hoạch thực thi, độ trễ, số tài liệu duyệt và tải ghi.
- Nhận ra khi cần đổi ranh giới tài liệu hoặc chọn mô hình lưu trữ khác thay vì thêm chỉ mục.

## 2. Hiểu đúng các loại khóa trong mô hình tài liệu

### 2.1. Khóa định danh của tài liệu

Mỗi tài liệu cần một cách nhận diện ổn định. Một số hệ quản trị tự tạo trường hoặc định danh nội bộ; MongoDB, chẳng hạn, sử dụng trường `_id` làm định danh duy nhất trong mỗi collection.

Ví dụ tài liệu khóa học:

```json
{
  "_id": "CRS-0042",
  "tenantId": "ORG-07",
  "courseCode": "DATA-101",
  "title": "Thiết kế dữ liệu",
  "status": "PUBLISHED"
}
```

Trong ví dụ, `_id` là định danh lưu trữ; `courseCode` là mã mà nghiệp vụ hoặc người dùng có thể nhận biết. Hai trường này có thể trùng về giá trị nhưng **không bắt buộc phải là một**.

Một khóa tốt nên:

- **Ổn định:** không đổi chỉ vì tiêu đề, email, tên hiển thị hoặc vị trí trong danh sách thay đổi.
- **Đủ duy nhất:** tránh trùng trong phạm vi nghiệp vụ đã xác định.
- **Dùng được cho tham chiếu:** tài liệu con, API và sự kiện có thể sử dụng định danh bền vững.
- **Có quy tắc tạo và lưu rõ ràng:** dịch vụ nào cấp mã; làm gì khi nhận yêu cầu trùng; định dạng có giới hạn nào?
- **Không chứa dữ liệu nhạy cảm không cần thiết:** hạn chế dùng email, số điện thoại, số giấy tờ làm khóa công khai.
- **Phù hợp với phân bố tải:** không tự tạo một điểm ghi nóng nếu hệ lưu trữ phân vùng theo vùng giá trị khóa.

### 2.2. Khóa tự nhiên và khóa thay thế

**Khóa tự nhiên (natural key)** là dữ kiện nghiệp vụ vốn có tính duy nhất theo quy tắc, ví dụ một mã khóa học do tổ chức cấp. **Khóa thay thế (surrogate key)** là định danh được tạo riêng để nhận diện bản ghi, ví dụ chuỗi ngẫu nhiên hoặc định danh do hệ quản trị sinh.

| Tiêu chí | Khóa tự nhiên | Khóa thay thế |
| --- | --- | --- |
| Ý nghĩa | Có nghĩa với nghiệp vụ | Chủ yếu dùng cho định danh |
| Khả năng thay đổi | Có thể đổi khi quy tắc nghiệp vụ đổi | Thường thiết kế bất biến |
| Chống trùng | Phải xác định phạm vi, chuẩn hóa dữ liệu và quy tắc duy nhất | Cần cơ chế sinh có rủi ro trùng đủ thấp hoặc kiểm tra duy nhất |
| API/tham chiếu | Thuận tiện nếu mã thật sự ổn định | Ít phụ thuộc thay đổi nghiệp vụ |
| Ví dụ | `(tenantId, courseCode)` | `courseId = "CRS-0042"` |

**Ví dụ:** `courseCode` có thể đổi từ `DATA-101` thành `DB-101` khi sửa chương trình. Nếu mã này được dùng như định danh duy nhất ở hàng nghìn tài liệu `enrollments`, việc đổi sẽ kéo theo nhiều tham chiếu. Thông thường hợp lý hơn khi có `courseId` ổn định và đặt ràng buộc duy nhất riêng lên mã nghiệp vụ.

Không có nguyên tắc “mọi document đều phải dùng UUID” hoặc “mọi document phải dùng khóa tự nhiên”. Cần đánh giá đặc điểm nghiệp vụ, cách tạo ID, tính duy nhất, khả năng tạo khóa tại client, chi phí lưu trữ và phân phối ghi.

### 2.3. Khóa tham chiếu

Khi hai thực thể có vòng đời độc lập, tài liệu có thể lưu một hoặc vài trường tham chiếu:

```json
{
  "_id": "ENR-0102",
  "tenantId": "ORG-07",
  "learnerId": "USR-0045",
  "courseId": "CRS-0042",
  "status": "ACTIVE",
  "createdAt": "2026-11-18T09:00:00Z"
}
```

`learnerId` và `courseId` tham chiếu tới học viên và khóa học. Trong nhiều hệ quản trị tài liệu, một trường chứa ID **không tự áp đặt khóa ngoại** như trong cơ sở dữ liệu quan hệ. Cần xác định ai xác thực tham chiếu, xử lý xóa thực thể đích, cách phát hiện tham chiếu mồ côi và chính sách lưu lịch sử.

Với tài liệu con, việc nhúng hoặc tham chiếu vẫn dựa trên **đơn vị đọc/ghi, kích thước, bội số và tính nhất quán**. Chọn khóa là bước kế tiếp của quyết định ranh giới tài liệu.

### 2.4. Khóa phân vùng hoặc shard key

Một số hệ quản trị dùng khóa để phân chia dữ liệu và định tuyến truy vấn. Khóa phân vùng có thể khác khóa định danh tài liệu.

Ví dụ mô hình nhiều tổ chức dùng `tenantId` để phân tách truy cập. Điều đó **không tự bảo đảm** `tenantId` là khóa phân vùng vật lý tốt: một tổ chức rất lớn có thể chiếm phần lớn lưu lượng, và một thao tác liên tổ chức có thể vượt phạm vi giao dịch thuận tiện.

Khi thiết kế cần đặt câu hỏi:

- Đa số truy vấn có chứa `tenantId` hay khóa phân vùng được chọn không?
- Một giá trị khóa có gom quá nhiều đọc/ghi lên cùng partition không?
- Có nghiệp vụ giao dịch xuyên partition không?
- Quy tắc duy nhất được hệ quản trị hỗ trợ như thế nào với khóa phân vùng đó?
- Khi tăng số tổ chức và lưu lượng, việc phân phối khóa có còn hợp lý không?

**Không thể suy ra cách phân vùng từ tên trường.** Khả năng định tuyến và quy tắc unique index phụ thuộc sản phẩm, phiên bản, cấu hình.

## 3. Tính duy nhất phải có phạm vi nghiệp vụ

Một sai lầm phổ biến là tuyên bố “`courseCode` phải duy nhất” nhưng không nói **duy nhất ở đâu**.

Giả sử hai tổ chức khác nhau cùng dùng mã `DB-101`:

```json
{
  "tenantId": "ORG-07",
  "courseId": "CRS-0042",
  "courseCode": "DB-101"
}
```

```json
{
  "tenantId": "ORG-12",
  "courseId": "CRS-0911",
  "courseCode": "DB-101"
}
```

Nếu nghiệp vụ cho phép cùng mã ở hai tổ chức, ràng buộc phải là **duy nhất theo cặp `(tenantId, courseCode)`**, không phải riêng `courseCode`.

Ví dụ với MongoDB:

```javascript
db.courses.createIndex(
  { tenantId: 1, courseCode: 1 },
  { unique: true }
);
```

Chỉ mục này kiểm soát tính duy nhất **trong collection và theo khả năng thực tế của cấu hình triển khai**. Nếu dùng sharding, cần kiểm tra riêng các giới hạn liên quan tới unique index và shard key.

Những điều phải xác định thêm:

- Mã có phân biệt chữ hoa/thường không? `db-101` và `DB-101` là một hay hai?
- Mã có cho phép khoảng trắng đầu/cuối không?
- Có được tái sử dụng mã sau khi khóa học bị ẩn hoặc xóa mềm không?
- Trường thiếu hoặc `null` phải xử lý thế nào trong unique index?
- Khi đổi mã, các API và tài liệu tham chiếu có cần đổi theo không?

Nếu có chuẩn hóa chữ hoa/thường, nên xác định chính sách tại nguồn ghi và cách đối chiếu (*collation*) phù hợp. Không nên để các client tự áp dụng quy tắc không thống nhất.

### 3.1. Khóa ghép cho quan hệ nghiệp vụ

Một học viên chỉ được có **một bản ghi ghi danh hiện hành** cho cùng một khóa trong cùng tổ chức:

```javascript
db.enrollments.createIndex(
  { tenantId: 1, learnerId: 1, courseId: 1 },
  { unique: true }
);
```

Ràng buộc này giữ tốt khi mỗi cặp học viên–khóa chỉ có một tài liệu và `status` phản ánh trạng thái qua thời gian. Nếu nghiệp vụ cần nhiều lần nhập học/hủy/nhập học lại như các **bản ghi lịch sử riêng**, khóa duy nhất theo cặp sẽ không còn phù hợp. Khi đó có thể dùng một tài liệu trạng thái hiện hành và các sự kiện lịch sử, hoặc ràng buộc duy nhất có điều kiện nếu hệ quản trị hỗ trợ đúng ngữ nghĩa.

Không đặt `status` vào khóa duy nhất chỉ để “cho phép ghi danh lại” nếu như vậy có thể sinh hai bản ghi `ACTIVE` dưới cùng một cặp do cơ chế cập nhật không bảo vệ đầy đủ.

## 4. Tài liệu truy vấn trước khi tạo chỉ mục

**Chỉ mục phục vụ truy vấn, không phục vụ sơ đồ trường.** Bước đầu tiên là liệt kê các đường truy cập thực tế từ API, màn hình và tác vụ nền.

Bảng mẫu cho nền tảng học tập:

| Mã | Nhu cầu nghiệp vụ | Bộ lọc chính | Sắp xếp/phân trang | Kết quả cần |
| --- | --- | --- | --- | --- |
| Q1 | Mở chi tiết một khóa | `tenantId`, `courseId` | Không | Tiêu đề, mô tả, trạng thái |
| Q2 | Danh sách khóa đã xuất bản | `tenantId`, `status=PUBLISHED` | `publishedAt` mới nhất, phân trang | `courseId`, `title`, `summary` |
| Q3 | Liệt kê bài của khóa | `tenantId`, `courseId` | `position` tăng dần | `lessonId`, `title` |
| Q4 | Danh sách ghi danh của học viên | `tenantId`, `learnerId` | `createdAt` mới nhất, phân trang | `courseId`, `status` |
| Q5 | Kiểm tra đã ghi danh | `tenantId`, `learnerId`, `courseId` | Không | Trạng thái ghi danh |
| Q6 | Thống kê học viên đang học một khóa | `tenantId`, `courseId`, `status=ACTIVE` | Có thể theo thời gian | Số lượng hoặc danh sách học viên |
| Q7 | Tìm khóa theo từ khóa | `tenantId`, trạng thái và từ khóa | Theo độ liên quan hoặc ngày | Kết quả tìm kiếm |
| Q8 | Báo cáo hoàn thành theo tháng | Khoảng thời gian, nhóm theo khóa | Tổng hợp nhiều bản ghi | Số liệu tổng |

Với mỗi truy vấn, ghi **tần suất**, kích thước kết quả, tốc độ tăng dữ liệu, độ trễ mục tiêu, mức ưu tiên và người dùng được phép truy cập. Q2 có thể chạy hàng nghìn lần/phút, trong khi Q8 chạy một lần mỗi đêm; không nên đánh đổi như nhau.

### 4.1. Hình dạng truy vấn (query shape) gồm những gì?

Một query shape nên mô tả:

- **Equality filters:** `tenantId = X`, `status = PUBLISHED`.
- **Range filters:** `createdAt >= T`, `priceMinor` trong khoảng.
- **Sort:** `publishedAt DESC` rồi `_id DESC`.
- **Projection:** các trường cần trả về, không mặc định toàn bộ tài liệu.
- **Limit/page:** số bản ghi/trang và chiến lược phân trang.
- **Aggregation:** nhóm, đếm, tổng hoặc đối chiếu dữ liệu.
- **Scope/security:** các điều kiện bắt buộc như `tenantId` và phân quyền hiển thị.

Hai API khác nhau về tên nhưng dùng cùng điều kiện lọc, sắp xếp và trả trường có thể chia sẻ một chỉ mục. Ngược lại, cùng một API nhưng có các nhánh truy vấn thay đổi thứ tự sắp xếp có thể cần đánh giá chỉ mục khác nhau.

### 4.2. Trường cần truy vấn khác trường cần lưu

Một tài liệu bài học có thể chứa `content` dài hàng chục KiB, nhưng Q3 chỉ cần tiêu đề. Vẫn cần lưu `content` cho màn hình học bài; điều đó **không có nghĩa** phải đặt trường nội dung dài vào mọi chỉ mục hoặc trả trong mọi danh sách.

Hãy phân loại trường theo vai trò:

| Vai trò | Ví dụ | Tác động thiết kế |
| --- | --- | --- |
| Định danh | `courseId`, `lessonId` | Khóa, duy nhất, tham chiếu |
| Phân vùng/phân quyền | `tenantId`, `visibility` | Bắt buộc trong điều kiện truy vấn đúng phạm vi |
| Lọc chính xác | `status`, `learnerId` | Thường là ứng viên cho tiền tố chỉ mục |
| Lọc khoảng | `createdAt`, `priceMinor` | Xem thứ tự với bộ lọc và sort |
| Sắp xếp | `publishedAt`, `position` | Xem chỉ mục có hỗ trợ hướng sắp xếp không |
| Hiển thị | `title`, `summary` | Dùng projection, cân nhắc covered query khi có lợi |
| Tìm kiếm văn bản | `title`, `description` | Xem chỉ mục text/search phù hợp |
| Tổng hợp | `priceMinor`, `rating` | Xem index, aggregation hoặc hệ phân tích |
| Cập nhật | `version`, `status` | Bảo vệ cập nhật đồng thời và trạng thái |

Đừng thêm chỉ mục chỉ vì một trường xuất hiện trong JSON. Chỉ mục có lợi khi phục vụ một đường truy cập có tần suất, tải và yêu cầu hiệu năng cụ thể.

## 5. Chỉ mục thực hiện công việc gì, và trả giá bằng gì?

Một chỉ mục bổ sung tạo đường truy cập dựa trên giá trị của một hoặc nhiều trường. Với chỉ mục phù hợp, hệ quản trị có thể tránh quét nhiều tài liệu hoặc thực hiện sắp xếp tốn kém. Tuy nhiên, chỉ mục không miễn phí:

- Chiếm dung lượng lưu trữ và bộ nhớ đệm.
- Cần được cập nhật khi tài liệu hoặc trường được lập chỉ mục thay đổi.
- Làm thao tác chèn/sửa/xóa tốn thêm công việc.
- Cần bảo trì, xây dựng và giám sát theo vòng đời dữ liệu.
- Có thể khiến query planner chọn một kế hoạch không tối ưu ở một số phân phối dữ liệu.

Một hệ thống có **nhiều chỉ mục** chưa chắc nhanh hơn hệ thống có **ít chỉ mục đúng đường truy cập**.

### 5.1. Chỉ mục đơn trường

Ví dụ tìm một khóa học theo `courseId`:

```javascript
db.courses.createIndex(
  { tenantId: 1, courseId: 1 },
  { unique: true }
);

db.courses.findOne({
  tenantId: "ORG-07",
  courseId: "CRS-0042"
});
```

Trong một môi trường dùng `_id` làm `courseId` và biết chắc khóa duy nhất toàn collection, có thể đọc trực tiếp bằng `_id`. Nhưng nếu nghiệp vụ yêu cầu mọi thao tác giới hạn `tenantId`, vẫn phải bảo vệ quyền truy cập ở lớp ứng dụng hoặc điều kiện truy vấn thích hợp; chỉ biết `_id` không mặc nhiên được phép xem tài liệu của tổ chức khác.

### 5.2. Chỉ mục ghép cho lọc và sắp xếp

Q2: liệt kê khóa học đã xuất bản của một tổ chức, mới nhất trước.

```javascript
db.courses.createIndex({
  tenantId: 1,
  status: 1,
  publishedAt: -1,
  _id: -1
});

db.courses.find(
  { tenantId: "ORG-07", status: "PUBLISHED" },
  { _id: 1, courseId: 1, title: 1, summary: 1, publishedAt: 1 }
).sort({ publishedAt: -1, _id: -1 }).limit(20);
```

Bộ lọc bằng hai điều kiện bằng nhau đi trước các trường sắp xếp. Cặp `(publishedAt, _id)` tạo thứ tự ổn định ngay cả khi nhiều khóa có cùng thời điểm xuất bản.

**Quy tắc gợi ý:** thường cân nhắc equality → sort → range khi thiết kế chỉ mục ghép, nhưng đây không phải công thức bất biến. Hiệu quả thật phụ thuộc mức chọn lọc, phân phối dữ liệu, kiểu truy vấn và khả năng tối ưu của hệ quản trị.

Nếu Q2 có nhánh “mọi trạng thái” không có bộ lọc `status`, chỉ mục trên có thể không còn hỗ trợ sắp xếp tối ưu như dự kiến. Cần đánh giá query shape đó riêng; không tự kết luận “có tiền tố `tenantId` là đủ”.

### 5.3. Thứ tự các trường trong chỉ mục ghép

Hai chỉ mục sau khác nhau:

```javascript
{ tenantId: 1, learnerId: 1, createdAt: -1 }
{ createdAt: -1, learnerId: 1, tenantId: 1 }
```

Chúng không phải hai cách viết tương đương. Với truy vấn “mọi ghi danh của học viên X trong tổ chức Y, mới nhất trước”, chỉ mục thứ nhất thường là ứng viên dễ giải thích hơn vì khớp bộ lọc chính trước rồi thứ tự thời gian.

Một chỉ mục ghép thường có thể phục vụ một số truy vấn sử dụng **tiền tố phù hợp**, nhưng không thể mặc nhiên dùng hiệu quả cho mọi tập con trường bất kỳ. Cần xác minh bằng kế hoạch thực thi.

### 5.4. Chỉ mục ghép và ràng buộc duy nhất là hai mục đích khác nhau

```javascript
// Bảo vệ một học viên có một bản ghi ghi danh cho mỗi khóa.
db.enrollments.createIndex(
  { tenantId: 1, learnerId: 1, courseId: 1 },
  { unique: true }
);

// Phục vụ lịch sử ghi danh, mới nhất trước.
db.enrollments.createIndex({
  tenantId: 1,
  learnerId: 1,
  createdAt: -1,
  _id: -1
});
```

Chỉ mục đầu nhắm tới **tính đúng đắn**; chỉ mục thứ hai nhắm tới **lọc/sắp xếp**. Không nên bỏ một ràng buộc duy nhất chỉ vì một chỉ mục phục vụ danh sách đã tồn tại. Ngược lại, không nên chờ chỉ mục unique theo khóa nghiệp vụ tự giải quyết truy vấn thời gian.

## 6. Trường lồng nhau và mảng: ý nghĩa truy vấn quan trọng hơn cú pháp

Tài liệu cho phép đối tượng lồng và mảng; nhiều hệ quản trị cho phép lập chỉ mục theo đường dẫn. Nhưng truy vấn một mảng đối tượng có bẫy về **phần tử nào thỏa điều kiện**.

Giả sử câu trả lời bài kiểm tra:

```json
{
  "attemptId": "ATT-017",
  "answers": [
    { "questionId": "Q-01", "isCorrect": false },
    { "questionId": "Q-02", "isCorrect": true }
  ]
}
```

Truy vấn MongoDB sau có thể khớp tài liệu dù câu Q-01 trả lời sai:

```javascript
db.attempts.find({
  "answers.questionId": "Q-01",
  "answers.isCorrect": true
});
```

Lý do: hai điều kiện trên mảng có thể được thỏa bởi **hai phần tử khác nhau**. Nếu cần “Q-01 đúng”, dùng cùng một phần tử:

```javascript
db.attempts.find({
  answers: {
    $elemMatch: {
      questionId: "Q-01",
      isCorrect: true
    }
  }
});
```

Tài liệu ví dụ sẽ không khớp. Đây là yêu cầu **ngữ nghĩa truy vấn**, không chỉ là tối ưu chỉ mục.

### 6.1. Chỉ mục multikey và mảng tăng trưởng

MongoDB có thể lập chỉ mục cho giá trị trong mảng thông qua cơ chế **multikey**. Ví dụ:

```javascript
db.attempts.createIndex({
  "answers.questionId": 1
});
```

Cần lưu ý:

- Một tài liệu có nhiều phần tử mảng có thể tạo nhiều mục chỉ mục.
- Mảng càng lớn và thay đổi thường xuyên, chi phí cập nhật chỉ mục càng cao.
- Chỉ mục ghép có nhiều đường dẫn mảng có các giới hạn sản phẩm cụ thể.
- Truy vấn cần `$elemMatch` hoặc cơ chế tương đương khi các điều kiện phải nằm trên cùng phần tử.
- Một mảng lớn, tăng liên tục và cần phân trang độc lập có thể nên tách thành tài liệu con, thay vì cố giải quyết chỉ bằng chỉ mục.

Trước khi lập chỉ mục, hãy hỏi **đường truy vấn thực sự cần ở cấp tài liệu cha hay từng phần tử con**. Nếu cần tìm các bài làm theo từng câu hỏi, lọc nhiều điều kiện và phân trang từng câu trả lời, một collection `attemptAnswers` riêng có thể đem lại mô hình truy cập rõ hơn.

### 6.2. Chỉ mục đường dẫn không thay thế validation

Nếu `answers.questionId` có lúc là chuỗi, có lúc là số, hoặc thiếu ở nhiều tài liệu, truy vấn có thể cho kết quả khó dự đoán. Cần hợp đồng dữ liệu cho kiểu trường, bắt buộc/không bắt buộc, giới hạn kích thước mảng và ngữ nghĩa trùng lặp.

## 7. Chỉ mục đặc biệt: sử dụng khi đúng nhu cầu

Các loại chỉ mục và thuộc tính dưới đây có thể hữu ích, nhưng **khả năng cụ thể phụ thuộc hệ quản trị**. Ví dụ cú pháp sử dụng MongoDB.

### 7.1. Chỉ mục có điều kiện (partial index)

Giả sử Q6 thường lấy học viên có ghi danh `ACTIVE` trong một khóa:

```javascript
db.enrollments.createIndex(
  { tenantId: 1, courseId: 1, createdAt: -1 },
  {
    partialFilterExpression: {
      status: "ACTIVE"
    }
  }
);

db.enrollments.find({
  tenantId: "ORG-07",
  courseId: "CRS-0042",
  status: "ACTIVE"
}).sort({ createdAt: -1 }).limit(30);
```

Chỉ mục chỉ bao gồm tài liệu đáp ứng điều kiện đặt trong `partialFilterExpression`, có thể giảm dung lượng và chi phí cập nhật so với lập chỉ mục mọi trạng thái. Tuy nhiên, các truy vấn không có điều kiện đủ để suy ra `status = ACTIVE` có thể không sử dụng chỉ mục đó để trả kết quả đầy đủ.

Không dùng partial index như một cách “ẩn” dữ liệu ngoài trạng thái ACTIVE: **phân quyền và kiểm soát truy cập vẫn phải được thực thi riêng**.

### 7.2. Chỉ mục TTL và dữ liệu hết hạn

Nếu hệ quản trị hỗ trợ TTL, có thể dùng cho dữ liệu tạm hoặc phiên đăng nhập với `expiresAt` hợp lệ.

```javascript
// MongoDB: trường expiresAt cần được lưu theo kiểu Date phù hợp.
db.ephemeralSessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
```

TTL thường xóa bằng tác vụ nền, **không đảm bảo xóa chính xác tới mili giây hết hạn**. Nếu cần chặn sử dụng session ngay sau `expiresAt`, logic xác thực phải kiểm tra thời điểm hết hạn tại đường đọc/ghi; không phụ thuộc duy nhất vào việc tài liệu đã bị dọn.

Không áp dụng TTL cho đơn hàng, chứng từ hoặc lịch sử phải lưu theo chính sách chỉ vì dung lượng tăng.

### 7.3. Tìm kiếm văn bản

Tìm khóa học theo cụm từ, gần đúng, lỗi gõ hoặc xếp hạng độ liên quan là một bài toán khác với bộ lọc `status = PUBLISHED`. Có thể cân nhắc chỉ mục text/search của hệ lưu trữ hoặc công cụ tìm kiếm chuyên dụng.

Cần xác định ngôn ngữ, tách từ tiếng Việt, dấu, xếp hạng, độ trễ cập nhật chỉ mục và quyền truy cập kết quả. Một chỉ mục B-tree trên `title` không tự giải quyết mọi kiểu tìm kiếm toàn văn.

### 7.4. Wildcard, hashed và các loại chỉ mục khác

Một số hệ quản trị hỗ trợ chỉ mục cho trường động (*wildcard*), khóa băm (*hashed*), không gian (*geospatial*) hoặc các loại chuyên biệt. Các cấu trúc này hữu ích khi phù hợp đường truy cập nhưng có giới hạn riêng về sắp xếp, tính duy nhất, khả năng bao phủ truy vấn và chi phí lưu trữ.

Đừng chọn chúng vì “hỗ trợ nhiều thứ”; hãy ghi rõ truy vấn bắt buộc, điều kiện áp dụng và số đo xác minh.

## 8. Projection: chỉ lấy những trường cần thiết

Một tài liệu `lessons` có thể chứa nội dung hàng chục KiB:

```json
{
  "lessonId": "LES-101",
  "tenantId": "ORG-07",
  "courseId": "CRS-0042",
  "position": 3,
  "title": "Khóa và chỉ mục",
  "content": "Nội dung bài học rất dài...",
  "attachments": ["ASSET-1", "ASSET-2"]
}
```

Trang mục lục thường chỉ cần `lessonId`, `position`, `title`. Ví dụ:

```javascript
db.lessons.createIndex({
  tenantId: 1,
  courseId: 1,
  position: 1,
  _id: 1
});

db.lessons.find(
  { tenantId: "ORG-07", courseId: "CRS-0042" },
  { _id: 1, lessonId: 1, position: 1, title: 1 }
).sort({ position: 1, _id: 1 });
```

**Projection** giúp giảm dữ liệu trả về và làm hợp đồng API rõ hơn. Nhưng projection không tự bảo đảm truy vấn chỉ đọc chỉ mục. Nếu `title` và `lessonId` không nằm trong chỉ mục phù hợp, hệ quản trị có thể vẫn phải lấy tài liệu để trả các trường đó.

### 8.1. Truy vấn bao phủ bởi chỉ mục (covered query)

Một truy vấn được gọi là *covered* khi hệ quản trị có thể thỏa mãn điều kiện và các trường trả về từ chỉ mục mà không cần đọc tài liệu gốc, tùy semantics và khả năng sản phẩm.

Ví dụ nếu danh sách chỉ cần `courseId` và `publishedAt`, một chỉ mục chứa đủ các trường lọc/sắp xếp/chiếu có thể là ứng viên:

```javascript
db.courses.createIndex({
  tenantId: 1,
  status: 1,
  publishedAt: -1,
  courseId: 1
});

db.courses.find(
  { tenantId: "ORG-07", status: "PUBLISHED" },
  { _id: 0, courseId: 1, publishedAt: 1 }
).sort({ publishedAt: -1 }).limit(20);
```

Đây là **ứng viên**, cần dùng `explain` để xác nhận. Việc thêm nhiều trường chỉ để “cover” mọi truy vấn có thể khiến chỉ mục lớn, giảm cache hit và làm ghi chậm. Hãy đo lợi ích từ số tài liệu phải fetch trước khi mở rộng chỉ mục.

### 8.2. Dữ liệu nhạy cảm và projection

Projection không thay thế ủy quyền. Nếu ứng dụng có quyền đọc một tài liệu chứa trường nhạy cảm, chỉ yêu cầu client “đừng hiển thị” vẫn không bảo đảm an toàn. Phải giới hạn trường trả về ở backend, thực thi quyền truy cập theo tenant/role và cân nhắc tách dữ liệu nhạy cảm sang ranh giới lưu trữ có chính sách phù hợp.

## 9. Phân trang: vì sao cần thứ tự ổn định?

### 9.1. Vấn đề với skip/offset sâu

Trang danh sách mới nhất thường được triển khai:

```javascript
db.enrollments.find({
  tenantId: "ORG-07",
  learnerId: "USR-0045"
}).sort({ createdAt: -1 }).skip(10000).limit(20);
```

Khi bỏ qua một số lượng lớn kết quả, hệ quản trị có thể phải duyệt nhiều bản ghi để tới trang sâu. Nếu đồng thời có bản ghi được thêm/xóa, người dùng có thể thấy phần tử bị lặp hoặc bị bỏ qua giữa các trang.

Offset vẫn phù hợp với danh sách nhỏ, các trang nông hoặc bài toán cần truy cập trang số cụ thể. Với lịch sử lớn cần “tải thêm”, **cursor/keyset pagination** thường đáng cân nhắc.

### 9.2. Phân trang theo cặp khóa

Dữ liệu `createdAt` có thể trùng; cần một khóa phụ ổn định như `_id` để bảo đảm thứ tự tổng quát.

Chỉ mục:

```javascript
db.enrollments.createIndex({
  tenantId: 1,
  learnerId: 1,
  createdAt: -1,
  _id: -1
});
```

Trang đầu:

```javascript
db.enrollments.find(
  { tenantId: "ORG-07", learnerId: "USR-0045" },
  { _id: 1, courseId: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(20);
```

Trang tiếp theo với khóa cuối trang trước, giả sử `cursorTime` là giá trị Date thực và `cursorId` cùng kiểu `_id` trong collection:

```javascript
db.enrollments.find(
  {
    tenantId: "ORG-07",
    learnerId: "USR-0045",
    $or: [
      { createdAt: { $lt: cursorTime } },
      { createdAt: cursorTime, _id: { $lt: cursorId } }
    ]
  },
  { _id: 1, courseId: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(20);
```

Cách này duyệt tiếp theo **giá trị khóa**, tránh phải bỏ qua toàn bộ các trang trước. Cần chú ý:

- `createdAt` nên được cố định sau khi tạo nếu dùng làm cursor; nếu trường sắp xếp đổi, bản ghi có thể di chuyển giữa các trang.
- Cursor phải lưu đủ khóa sắp xếp và gắn với bộ lọc/phiên truy vấn.
- Các bản ghi mới thêm trong khi phân trang có thể nằm phía trước cursor; đây là semantics “duyệt tiếp”, **không phải snapshot tĩnh**.
- Nếu yêu cầu một tập kết quả bất biến trong cả phiên phân trang, cần thiết kế snapshot hoặc mốc chốt theo khả năng hệ lưu trữ.
- Cần đo kế hoạch truy vấn có `$or`; có thể chọn cách biểu diễn hoặc chỉ mục khác nếu dữ liệu lớn và planner không tối ưu như dự kiến.

### 9.3. Thứ tự sắp xếp là một phần của hợp đồng API

Nếu danh sách đơn theo `createdAt` và hai đơn có cùng thời điểm, kết quả không có tie-breaker có thể thay đổi thứ tự giữa các lần đọc. Trường định danh ổn định giúp tránh thứ tự nhập nhằng, đồng thời cho phép cursor chính xác.

## 10. Đo kế hoạch thực thi trước khi khẳng định chỉ mục tốt

Một chỉ mục trông hợp lý trên giấy vẫn có thể không phù hợp do phân phối dữ liệu hoặc bộ lọc thực tế. Trong MongoDB, có thể xem kế hoạch như sau:

```javascript
db.enrollments.find({
  tenantId: "ORG-07",
  learnerId: "USR-0045"
}).sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
```

Những tín hiệu cần xem:

| Tín hiệu | Câu hỏi cần đặt |
| --- | --- |
| `nReturned` | Truy vấn thực trả bao nhiêu tài liệu? |
| `totalKeysExamined` | Có duyệt nhiều mục chỉ mục hơn số kết quả không? |
| `totalDocsExamined` | Có phải đọc nhiều tài liệu không? |
| Index scan hoặc collection scan | Truy vấn có dùng đúng đường truy cập dự kiến không? |
| Sort stage | Có sắp xếp ngoài chỉ mục hay không? |
| Thời gian thực thi | Độ trễ có đạt mục tiêu trên dữ liệu đại diện không? |
| Cách chọn kế hoạch | Truy vấn với tenant nhỏ và tenant rất lớn có khác nhau không? |

Một `COLLSCAN` không luôn là lỗi: tập dữ liệu rất nhỏ hoặc truy vấn lấy hầu hết tài liệu đôi khi quét tập hợp là lựa chọn hợp lý. Một `IXSCAN` cũng không mặc nhiên tốt nếu duyệt hàng triệu khóa để lấy vài dòng.

Các giá trị quan sát từ `explain` không thay thế benchmark ngoài ứng dụng. Cần đo cả độ trễ mạng, chuyển đổi dữ liệu, tải đồng thời và chỉ số p95/p99 theo đường API.

### 10.1. Phải thử các phân phối lệch

Giả sử phần lớn học viên có 3 khóa, nhưng một quản trị viên có quyền xem hàng trăm nghìn ghi danh. Nếu thử nghiệm chỉ dùng học viên bình thường, chỉ mục có thể trông rất tốt trong khi đường quản trị có độ trễ cao.

Bộ dữ liệu thử cần bao gồm:

- Tenant nhỏ, tenant trung bình và tenant nhiều dữ liệu.
- Khóa học ít và rất nhiều học viên.
- Trạng thái phổ biến/thưa hiếm và khoảng thời gian rộng/hẹp.
- Trang đầu và trang sâu.
- Cập nhật đồng thời khi hệ thống đang đọc.
- Phần tử mảng dài bất thường và trường thiếu/null theo schema.

## 11. Chi phí ghi, dung lượng và bảo trì chỉ mục

### 11.1. Mỗi chỉ mục là một cấu trúc phải duy trì

Giả sử collection `enrollments` có chỉ mục duy nhất cho cặp học viên–khóa, chỉ mục lịch sử theo thời gian, chỉ mục cho quản trị viên lọc theo khóa và chỉ mục cho thống kê trạng thái. Một lần ghi danh có thể làm thay đổi nhiều chỉ mục.

Hãy tránh “để an toàn, lập chỉ mục mọi trường”. Cách đó có thể gây:

- **Write amplification:** một thao tác ghi logic cập nhật nhiều cấu trúc vật lý.
- Tăng dung lượng chỉ mục và áp lực bộ nhớ đệm.
- Chậm xây dựng/rebuild chỉ mục, đặc biệt với tập dữ liệu lớn.
- Nhiều kế hoạch truy vấn cạnh tranh, khó giám sát và dọn dẹp.

Ngược lại, bỏ chỉ mục bảo vệ **unique constraint** chỉ để giảm chi phí ghi có thể vi phạm bất biến và gây sai dữ liệu. Chỉ mục phục vụ tính đúng đắn và chỉ mục phục vụ hiệu năng cần được đánh giá theo ưu tiên khác nhau.

### 11.2. Tần suất thay đổi trường ảnh hưởng chi phí

Một chỉ mục theo `createdAt` tương đối ổn định nếu trường đó chỉ được ghi lúc tạo. Một chỉ mục theo `updatedAt` có thể cần cập nhật ở mọi lần sửa.

Nếu `status` chuyển rất thường xuyên hoặc trường trong mảng thay đổi liên tục, chi phí duy trì chỉ mục tương ứng tăng. Chọn chỉ mục cần nhìn vào **cả đường đọc và đường ghi**, không chỉ một trong hai.

### 11.3. Thừa chỉ mục và trùng tiền tố

Ví dụ collection có:

```javascript
{ tenantId: 1, learnerId: 1 }
{ tenantId: 1, learnerId: 1, createdAt: -1 }
```

Chỉ mục thứ hai có thể phục vụ một số truy vấn dùng tiền tố `(tenantId, learnerId)`. Nhưng trước khi xóa chỉ mục đầu, phải kiểm tra:

- Chỉ mục đầu có ràng buộc `unique`, `partial` hoặc thuộc tính đặc biệt không?
- Hệ quản trị có dùng chỉ mục sau hiệu quả cho tất cả query shape liên quan không?
- Chỉ mục rộng hơn có tác động ghi/bộ nhớ đáng kể không?
- Có sự khác biệt về sort, collation hoặc tính duy nhất không?

Không gỡ chỉ mục chỉ dựa vào việc tên trường trông giống nhau.

## 12. Thiết kế khóa và chỉ mục phải tính tới cập nhật và di trú

### 12.1. Tránh khóa phải đổi theo nghiệp vụ

Một học viên đổi email, một khóa học đổi mã hoặc một nhà bán đổi tên. Nếu định danh tài liệu gắn chặt với các giá trị đó, các tham chiếu và cache có thể phải đồng bộ diện rộng.

Phương án thường bền vững hơn:

```text
users
  { userId: "USR-0045", email: "an@example.com" }

enrollments
  { enrollmentId: "ENR-0102", learnerId: "USR-0045", courseId: "CRS-0042" }
```

Khi email thay đổi, `learnerId` vẫn giữ nguyên. Nếu email phải duy nhất theo tenant, có thể thêm ràng buộc riêng với quy tắc chuẩn hóa và xử lý xóa/tái sử dụng.

### 12.2. Thêm chỉ mục vào collection đang có dữ liệu

Quy trình thông thường:

1. Liệt kê query shape đang cần, mục tiêu độ trễ và chỉ mục dự kiến.
2. Kiểm tra dữ liệu cũ có trùng hoặc thiếu giá trị nếu chuẩn bị tạo unique index.
3. Kiểm tra dung lượng, thời gian và tác động vận hành của việc xây chỉ mục trên sản phẩm đang dùng.
4. Tạo/chuyển chỉ mục theo cơ chế an toàn mà hệ quản trị hỗ trợ; quan sát lỗi và tải.
5. Kiểm tra `explain` và số đo ứng dụng trước/sau.
6. Chỉ gỡ đường truy cập cũ hoặc chỉ mục thừa sau khi xác nhận các truy vấn phụ thuộc đã được phục vụ.

Nếu muốn thêm ràng buộc unique lên dữ liệu hiện có mà đang có bản ghi trùng, cần xử lý nghiệp vụ **những bản ghi trùng đó** trước. Không nên để bước xây chỉ mục tự “quyết định” bản ghi nào đúng.

### 12.3. Trường lồng nhau chuyển sang tài liệu riêng

Một phiên bản đầu nhúng các lượt đánh giá trong `courses.reviews`, phiên bản sau tách thành `reviews` để phân trang. Khi đó phải thiết kế `reviewId` ổn định, `courseId` tham chiếu, chỉ mục theo khóa học/thời gian và quy trình di trú không tạo bản sao trùng.

Điều này cho thấy chọn **khóa con từ sớm** giúp việc tiến hóa mô hình dễ hơn. Tuy nhiên, không cần tạo hàng chục ID vô nghĩa cho mọi thuộc tính lồng nhau; ID chỉ cần thiết khi phần con có danh tính, được tham chiếu hoặc cần cập nhật độc lập.

## 13. Ví dụ tích hợp: thiết kế truy cập cho nền tảng học tập

### 13.1. Yêu cầu nghiệp vụ và dữ liệu

Một nền tảng có nhiều tổ chức đào tạo, mỗi tổ chức quản lý khóa học, bài học và người học. Người học có thể ghi danh nhiều khóa, theo dõi lịch sử và mở bài học. Màn hình danh sách khóa chỉ cần metadata ngắn; nội dung bài học có thể dài.

Lược đồ logic gợi ý:

```text
courses
  {
    _id, tenantId, courseId, courseCode,
    title, summary, status, publishedAt, schemaVersion
  }

lessons
  {
    _id, tenantId, lessonId, courseId,
    position, title, content, publishedVersion
  }

enrollments
  {
    _id, tenantId, learnerId, courseId,
    status, createdAt, updatedAt, version
  }
```

Trong đó `courseId` và `lessonId` là ID ổn định; `courseCode` là khóa nghiệp vụ có thể đổi; `tenantId` giới hạn dữ liệu tổ chức. Các trường thời gian được lưu theo kiểu ngày giờ phù hợp của hệ quản trị, với quy ước thời gian nhất quán.

### 13.2. Bảng khóa và bất biến

| Collection | Định danh tài liệu | Khóa nghiệp vụ / ràng buộc |
| --- | --- | --- |
| `courses` | `_id` hoặc `courseId` ổn định | `(tenantId, courseCode)` duy nhất theo tổ chức |
| `lessons` | `_id` hoặc `lessonId` ổn định | Tham chiếu `(tenantId, courseId)`; vị trí theo khóa có quy tắc |
| `enrollments` | `_id` hoặc `enrollmentId` | `(tenantId, learnerId, courseId)` duy nhất cho trạng thái hiện hành |

Nếu mỗi khóa cần vị trí bài `position` duy nhất, có thể thêm ràng buộc thích hợp trên `(tenantId, courseId, position)`. Tuy nhiên cần thiết kế cách **đổi vị trí hai bài** để không vướng ràng buộc duy nhất giữa chừng; có thể dùng thao tác giao dịch/phương án đánh số vị trí phù hợp.

### 13.3. Gợi ý chỉ mục gắn với đường truy cập

```javascript
// Tra khóa học theo mã nghiệp vụ trong một tổ chức.
db.courses.createIndex(
  { tenantId: 1, courseCode: 1 },
  { unique: true }
);

// Danh sách khóa đã xuất bản, mới nhất trước.
db.courses.createIndex({
  tenantId: 1, status: 1, publishedAt: -1, _id: -1
});

// Mục lục các bài học theo thứ tự.
db.lessons.createIndex({
  tenantId: 1, courseId: 1, position: 1, _id: 1
});

// Một ghi danh hiện hành cho mỗi cặp học viên - khóa.
db.enrollments.createIndex(
  { tenantId: 1, learnerId: 1, courseId: 1 },
  { unique: true }
);

// Lịch sử ghi danh theo học viên.
db.enrollments.createIndex({
  tenantId: 1, learnerId: 1, createdAt: -1, _id: -1
});

// Quản trị viên xem ghi danh theo khóa và trạng thái.
db.enrollments.createIndex({
  tenantId: 1, courseId: 1, status: 1, createdAt: -1
});
```

Đây là **bộ ứng viên cho workload giả định**, không phải chỉ dẫn tạo tất cả chỉ mục trong mọi dự án. Nếu Q6 chỉ dùng bộ đếm tổng hợp, chỉ mục chi tiết phục vụ Q6 có thể không cần; nếu danh sách theo `updatedAt` thay vì `createdAt`, cần đánh giá lại.

### 13.4. Tối ưu từng đường đọc

- **Trang danh sách khóa:** lọc `tenantId` + `status`, sắp xếp `publishedAt` và `_id`, chỉ lấy `title`, `summary`, mã khóa. Không trả nội dung bài.
- **Mục lục:** tìm `lessons` theo `tenantId, courseId`, sắp xếp `position`, chỉ lấy tiêu đề và ID.
- **Mở bài:** lấy một bài theo ID và phạm vi tenant, trả `content` cho người có quyền xem. Không cần tải tất cả bài của khóa.
- **Lịch sử học viên:** tìm `enrollments` theo `tenantId, learnerId`, sắp xếp thời gian và phân trang cursor.
- **Tra ghi danh trước khi cho học:** tra theo cặp khóa nghiệp vụ; kiểm tra trạng thái, thời hạn và quyền truy cập.
- **Báo cáo lớn:** cân nhắc truy vấn tổng hợp hoặc mô hình phân tích nếu quét hàng triệu bản ghi làm ảnh hưởng đường giao dịch.

### 13.5. Kiểm chứng bằng phép đo

Với từng query shape, chạy trên dữ liệu đủ lớn và lệch về tenant/khóa có tải cao. Thu thập:

- Số kết quả so với keys/docs examined.
- Có sort ngoài chỉ mục hay không.
- Độ trễ p95/p99.
- Chi phí chèn ghi danh và đổi trạng thái khi số chỉ mục tăng.
- Dung lượng chỉ mục và tác động tới bộ nhớ đệm.
- Xung đột concurrent write và lỗi unique constraint.
- Độ chính xác của phân trang khi có bản ghi mới.

Tài liệu thiết kế nên đính kèm **những quan sát này**, không chỉ liệt kê tên chỉ mục.

## 14. Những trường hợp chỉ mục không giải quyết được vấn đề mô hình

### 14.1. Mảng con tăng không giới hạn

Một tài liệu khóa học chứa hàng trăm nghìn `reviews` hoặc `learnerProgress`. Dù hệ quản trị lập chỉ mục đường dẫn mảng, tài liệu vẫn có nguy cơ quá lớn, khó phân trang và thành điểm nóng ghi. Cần tách phần con có vòng đời riêng hoặc dùng mô hình tổng hợp có giới hạn.

### 14.2. Tổng hợp trên nhiều tài liệu với tải rất lớn

Truy vấn doanh thu, mức độ học tập hoặc điểm số theo tháng có thể phải quét hàng triệu tài liệu. Chỉ mục giúp một phần, nhưng chưa chắc đáp ứng SLA báo cáo nặng. Có thể cần dữ liệu dẫn xuất, materialized view hoặc hệ phân tích; luôn xác định nguồn chuẩn, độ trễ và đối soát.

### 14.3. Duyệt quan hệ nhiều bước

Nếu nghiệp vụ thường hỏi “những người có liên hệ gián tiếp tới người này trong 5 bước”, mô hình đồ thị có thể phù hợp hơn. Thêm chỉ mục khóa tham chiếu không tự biến việc duyệt đồ thị sâu thành truy vấn đơn giản.

### 14.4. Bất biến trải nhiều thực thể

Chỉ mục unique có thể bảo vệ tính duy nhất của một khóa trong phạm vi được hỗ trợ, nhưng **không bảo đảm** mọi quy tắc liên tài liệu như “tồn kho không âm trong khi tạo đơn và thanh toán”. Cần transaction, điều kiện ghi hoặc quy trình phối hợp phù hợp.

## 15. Bài tập: hệ thống đặt lịch khám

**Yêu cầu:** Một ứng dụng quản lý nhiều phòng khám. Mỗi phòng khám có bác sĩ và lịch hẹn. Người dùng cần:

1. Mở chi tiết lịch hẹn bằng mã.
2. Xem các cuộc hẹn của **một bác sĩ trong một ngày**, sắp xếp theo giờ bắt đầu.
3. Xem các lịch hẹn gần đây của một bệnh nhân, phân trang.
4. Tìm các lịch hẹn `CONFIRMED` trong một khoảng thời gian của phòng khám.
5. Ngăn hai lịch hẹn có cùng **mã đặt lịch** trong một phòng khám.
6. Không cho hai lịch hẹn của cùng bác sĩ chồng thời gian nếu đó là quy tắc nghiệp vụ.

Hãy thiết kế khóa, các trường cần truy vấn, chỉ mục ứng viên và giải thích ràng buộc nào không thể giải quyết chỉ bằng chỉ mục.

### 15.1. Lược đồ gợi ý

```json
{
  "_id": "APT-0911",
  "clinicId": "CLN-03",
  "appointmentCode": "A-20261122-001",
  "doctorId": "DOC-07",
  "patientId": "PAT-042",
  "startsAt": "2026-11-22T02:30:00Z",
  "endsAt": "2026-11-22T03:00:00Z",
  "status": "CONFIRMED",
  "createdAt": "2026-11-20T08:00:00Z",
  "version": 1
}
```

Hai trường thời gian cần lưu ở kiểu Date thích hợp khi triển khai; chuỗi ISO ở JSON chỉ minh họa giá trị. Khi hiển thị cho người dùng, chuyển đổi theo múi giờ của phòng khám và xử lý thời gian làm việc theo chính sách địa phương.

### 15.2. Chỉ mục ứng viên

```javascript
// Mã đặt lịch duy nhất trong phạm vi phòng khám.
db.appointments.createIndex(
  { clinicId: 1, appointmentCode: 1 },
  { unique: true }
);

// Xem các cuộc hẹn của bác sĩ trong ngày/khoảng giờ.
db.appointments.createIndex({
  clinicId: 1, doctorId: 1, startsAt: 1
});

// Lịch sử của bệnh nhân, mới nhất trước.
db.appointments.createIndex({
  clinicId: 1, patientId: 1, createdAt: -1, _id: -1
});

// Lịch hẹn theo trạng thái trong khoảng thời gian.
db.appointments.createIndex({
  clinicId: 1, status: 1, startsAt: 1
});
```

Lưu ý `clinicId` vừa là phạm vi truy cập vừa xuất hiện trong các chỉ mục phục vụ truy vấn. Nếu bệnh nhân có thể đặt ở nhiều phòng khám và ứng dụng cần một danh sách **xuyên phòng khám**, đó là query shape khác, cần chính sách quyền truy cập và chỉ mục riêng.

### 15.3. Vì sao chỉ mục không tự ngăn lịch chồng nhau?

Hai cuộc hẹn có thể khác `startsAt` nhưng vẫn giao nhau về khoảng:

```text
A: 09:00–09:30
B: 09:15–09:45
```

Một unique index trên `(doctorId, startsAt)` chỉ ngăn **trùng chính xác giờ bắt đầu**, không ngăn mọi khoảng giao nhau.

Một kiểm tra chồng giờ có thể dùng điều kiện:

```text
existing.startsAt < requested.endsAt
AND existing.endsAt > requested.startsAt
```

Nhưng “kiểm tra không có lịch chồng rồi insert” ở hai lệnh rời rạc vẫn có thể bị race condition khi hai người đặt đồng thời. Cần cơ chế giao dịch/cô lập phù hợp, ràng buộc theo khoảng thời gian được hệ quản trị hỗ trợ, hoặc mô hình các slot có khóa duy nhất nếu thời lượng được lượng tử hóa hợp lệ. Thiết kế chính xác phụ thuộc cách đặt lịch và giới hạn sản phẩm.

### 15.4. Câu hỏi tự kiểm tra

- Nếu bác sĩ làm việc ở nhiều phòng khám, `doctorId` có duy nhất toàn hệ thống hay theo `clinicId`?
- Nếu bệnh nhân đổi email, khóa tài liệu và lịch sử hẹn có cần đổi không?
- Nếu một cuộc hẹn chuyển từ `CONFIRMED` sang `CANCELLED`, có cần xóa tài liệu hay chỉ chuyển trạng thái?
- Nếu quản trị viên tìm lịch hẹn theo 6 kiểu sắp xếp khác nhau, bạn sẽ ưu tiên chỉ mục nào dựa trên số liệu?
- Nếu danh sách cuộc hẹn cần trả cả ghi chú nhạy cảm của bác sĩ, cơ chế phân quyền và projection phải đặt ở đâu?
- Nếu phải xuất báo cáo toàn hệ thống theo tháng, chỉ thêm chỉ mục `startsAt` có đủ không?

## 16. Sai lầm thường gặp và cách khắc phục

**Sai lầm 1: Dùng email hoặc tên hiển thị làm khóa tài liệu.**  
Giá trị nghiệp vụ có thể thay đổi hoặc chứa thông tin nhạy cảm. Ưu tiên ID ổn định và giữ email/tên như thuộc tính có ràng buộc riêng khi cần.

**Sai lầm 2: Không xác định phạm vi duy nhất.**  
Mã khóa học có thể trùng giữa các tổ chức. Viết ràng buộc rõ ràng như `(tenantId, courseCode)`.

**Sai lầm 3: Tạo chỉ mục theo tất cả trường có mặt.**  
Dẫn tới tốn lưu trữ và tải ghi. Hãy xuất phát từ bảng query shape và đo hiệu quả.

**Sai lầm 4: Tin chỉ mục ghép nào cũng giúp mọi truy vấn con.**  
Thứ tự trường, bộ lọc và sắp xếp có ảnh hưởng. Dùng kế hoạch thực thi để kiểm chứng.

**Sai lầm 5: Không thêm khóa phụ khi sắp xếp.**  
Nhiều bản ghi có cùng `createdAt` có thể làm phân trang không ổn định. Sử dụng tie-breaker duy nhất và cursor đủ khóa.

**Sai lầm 6: Tin projection luôn tạo covered query.**  
Projection chỉ xác định trường trả về; covered query đòi hỏi chỉ mục và semantics phù hợp, phải kiểm tra bằng `explain`.

**Sai lầm 7: Lọc mảng đối tượng bằng các điều kiện không cùng phần tử.**  
Kết quả có thể khớp sai. Dùng `$elemMatch` hoặc cơ chế tương đương khi cần.

**Sai lầm 8: Dùng TTL như cơ chế thực thi hết hạn chính xác tức thì.**  
TTL có thể dọn trễ. Điều kiện hết hạn phải được kiểm tra ở đường nghiệp vụ quan trọng.

**Sai lầm 9: Quên `tenantId` trong một API hoặc chỉ mục duy nhất.**  
Có thể khiến dữ liệu bị tìm ngoài phạm vi tổ chức hoặc áp đặt ràng buộc sai. Thiết kế và kiểm thử toàn bộ đường truy cập theo tenant.

**Sai lầm 10: Chỉ kiểm tra dữ liệu mẫu nhỏ.**  
Chỉ mục hoạt động tốt với 100 tài liệu chưa chứng minh đáp ứng với hàng triệu tài liệu, tenant lệch lớn và ghi đồng thời.

**Sai lầm 11: Dùng chỉ mục để xử lý mọi bất biến.**  
Chỉ mục unique không tự giải quyết giao dịch liên tài liệu, đặt lịch khoảng chồng, kho hàng hoặc thanh toán.

**Sai lầm 12: Chọn shard key chỉ vì nó là primary key.**  
Định tuyến truy vấn, phân bố ghi và phạm vi transaction cần được phân tích riêng.

## 17. Quy trình thiết kế và checklist

Có thể áp dụng trình tự sau khi thiết kế một collection mới:

1. **Xác định thực thể và ranh giới tài liệu:** phần nào được nhúng, phần nào tham chiếu; phần con có giới hạn không?
2. **Chọn ID bất biến:** định dạng, nơi cấp mã, phạm vi duy nhất và đường tham chiếu.
3. **Chọn khóa nghiệp vụ/ràng buộc:** composite key, cách chuẩn hóa, quy tắc null/xóa/tái sử dụng.
4. **Xác định partition/tenant scope:** đường truy cập có luôn truyền khóa phân vùng và giới hạn bảo mật không?
5. **Liệt kê query shapes:** bộ lọc bằng nhau/khoảng, sắp xếp, projection, phân trang, tổng hợp và tần suất.
6. **Đề xuất chỉ mục tối thiểu:** bảo vệ ràng buộc duy nhất trước, sau đó tối ưu các truy vấn quan trọng.
7. **Thiết kế projection và cursor:** chỉ trả trường cần, thêm tie-breaker sắp xếp ổn định.
8. **Kiểm tra mảng và trường lồng nhau:** semantics cùng phần tử, giới hạn multikey và tăng trưởng.
9. **Tạo dữ liệu gần thực tế:** p50/p95/p99 cho số bản ghi, kích thước và tải theo khóa.
10. **Đo và điều chỉnh:** `explain`, keys/docs examined, latency, dung lượng index, retry và ảnh hưởng ghi.
11. **Xác định kế hoạch tiến hóa:** thêm chỉ mục, đổi khóa nghiệp vụ, di trú schema và gỡ chỉ mục thừa.
12. **Lưu bằng chứng:** bảng truy vấn–chỉ mục–lý do–số đo–giới hạn để người khác kiểm tra.

### Checklist ngắn trước khi duyệt

- [ ] ID tài liệu ổn định, duy nhất trong phạm vi xác định và không phụ thuộc dữ liệu dễ đổi.
- [ ] Các khóa tham chiếu có quy tắc xác thực, xóa và xử lý mồ côi.
- [ ] Phạm vi `tenantId`/partition được phản ánh ở truy vấn, ràng buộc và phân quyền.
- [ ] Có danh mục query shapes từ nghiệp vụ, không chỉ liệt kê các trường JSON.
- [ ] Chỉ mục phục vụ đúng equality, range, sort và pagination quan trọng.
- [ ] Mọi unique index đã được kiểm tra dữ liệu cũ, collation và ngữ nghĩa null/thiếu.
- [ ] Truy vấn mảng bảo đảm điều kiện cùng phần tử khi nghiệp vụ yêu cầu.
- [ ] Projection tránh trả nội dung lớn và trường nhạy cảm không cần thiết.
- [ ] Cursor có thứ tự ổn định và ngữ nghĩa khi dữ liệu thay đổi được xác định.
- [ ] Có số đo `explain`, p95/p99, kích thước chỉ mục và chi phí ghi trên dữ liệu đại diện.
- [ ] Chỉ mục đặc biệt như partial, TTL hay text được dùng theo khả năng/giới hạn sản phẩm.
- [ ] Không dựa vào chỉ mục để thay thế những ràng buộc cần giao dịch hoặc quy trình nghiệp vụ.
- [ ] Có chiến lược thêm/gỡ chỉ mục và di trú khóa mà không làm sai dữ liệu.

**Điểm cần nhớ:** Khóa tài liệu trả lời **“đâu là bản ghi này?”**; các trường truy vấn trả lời **“nghiệp vụ cần tìm và dùng dữ liệu thế nào?”**; chỉ mục trả lời **“hệ lưu trữ sẽ tìm dữ liệu với chi phí nào?”**. Thiết kế tốt bắt đầu từ ràng buộc và đường truy cập thật, chọn khóa ổn định, chỉ mục có mục đích và kiểm chứng bằng kế hoạch thực thi cùng tải thực tế.
