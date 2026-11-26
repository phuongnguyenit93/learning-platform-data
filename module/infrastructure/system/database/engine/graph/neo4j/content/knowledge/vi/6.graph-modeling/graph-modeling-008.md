# Biểu diễn thời gian hiệu lực, lịch sử và phiên bản thực thể trong Neo4j

Một thực thể trong đồ thị có thể giữ nguyên danh tính nhưng thay đổi thuộc tính hoặc quan hệ theo thời gian. Chẳng hạn, khách hàng `C001` được xếp hạng `BRONZE` từ ngày 01/01/2024, chuyển sang `GOLD` từ ngày 01/04/2024; nhân viên `E01` chuyển từ phòng ban `D01` sang `D02` từ ngày 01/07/2024. Nếu chỉ cập nhật trực tiếp thuộc tính hiện tại của node hoặc xóa relationship cũ, ta sẽ không trả lời được câu hỏi: **“Đồ thị đã có trạng thái nào tại một thời điểm trong quá khứ?”**

Trong Neo4j, ta có thể mô hình hóa thời gian hiệu lực bằng thuộc tính kiểu thời gian trên node/relationship, lưu các phiên bản của thực thể thành node riêng, hoặc kết hợp thêm thời gian ghi nhận để biết hệ thống **đã tin điều gì vào một thời điểm trước đây**. Bài này tập trung vào thiết kế property graph và câu truy vấn Cypher phục vụ lịch sử, truy vết và khôi phục trạng thái.

## 1. Phân biệt các khái niệm thời gian

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Thời gian hiệu lực (valid time)** | Khoảng thời gian một thông tin đúng trong nghiệp vụ | Hạng `GOLD` có hiệu lực từ 01/04/2024 |
| **Thời gian ghi nhận (recorded/system time)** | Khoảng thời gian hệ thống lưu và coi một thông tin là đúng | Ngày 10/04/2024 hệ thống mới nhận được thay đổi có hiệu lực từ 01/04/2024 |
| **Phiên bản (version)** | Một trạng thái cụ thể của thực thể, thường có số phiên bản và khoảng hiệu lực | `CustomerVersion` số 2 lưu hạng `GOLD` |
| **Sự kiện (event)** | Điều đã xảy ra, có thời điểm và ngữ nghĩa nghiệp vụ | `CustomerPromoted` xảy ra ngày 01/04/2024 |
| **Ảnh chụp theo thời điểm (snapshot)** | Trạng thái được dựng lại theo một thời điểm truy vấn | Hạng của `C001` vào ngày 15/03/2024 |

**Valid time** trả lời “Điều gì đúng trong nghiệp vụ vào ngày X?”. **Recorded time** trả lời “Vào ngày Y, hệ thống biết/ghi nhận điều gì?”. Hai câu hỏi khác nhau khi dữ liệu đến trễ hoặc bị đính chính.

Quy ước nên dùng cho khoảng thời gian là **đóng ở đầu, mở ở cuối**:

\[
[\text{validFrom},\ \text{validTo})
\]

Tại thời điểm `t`, bản ghi có hiệu lực nếu:

~~~text
validFrom <= t AND (validTo IS NULL OR t < validTo)
~~~

Theo đó, phiên bản cũ kết thúc vào `2024-04-01` và phiên bản mới bắt đầu đúng `2024-04-01` không chồng lấn. Trong Neo4j, thuộc tính không tồn tại được đọc thành `null`; việc gán thuộc tính bằng `null` cũng loại bỏ thuộc tính ấy. Vì vậy có thể **bỏ hẳn `validTo`** để biểu diễn khoảng chưa xác định điểm kết thúc.

Chọn đúng độ chính xác ngay từ đầu:

- `date` cho thay đổi theo ngày nghiệp vụ, ví dụ hạng khách hàng áp dụng từ đầu ngày.
- `datetime` cho thay đổi theo thời điểm, ví dụ quyền truy cập có hiệu lực từ `2024-04-01T09:30:00Z`. Cần thống nhất múi giờ và quy tắc quy đổi thời gian giữa các hệ thống.
- Không dùng chuỗi tùy ý như `"01/04/24"` để so sánh khoảng thời gian; chuyển thành kiểu thời gian của Neo4j.

## 2. Ba cách biểu diễn lịch sử trong property graph

| Mô hình | Cấu trúc | Phù hợp khi | Điểm cần chú ý |
| --- | --- | --- | --- |
| **Thuộc tính thời gian trên node/relationship** | Thêm `validFrom`, `validTo` vào bản ghi hoặc cạnh | Lịch sử quan hệ đơn giản, chẳng hạn nhân viên thuộc phòng ban nào | Không được xóa bản ghi lịch sử khi kết thúc hiệu lực |
| **Node phiên bản** | `(:Customer)-[:HAS_VERSION]->(:CustomerVersion)` | Cần truy vấn trạng thái cũ của một thực thể và giữ ID nghiệp vụ ổn định | Tăng số node/relationship; cần quản lý khoảng hiệu lực |
| **Node sự kiện** | `(:Customer)-[:HAS_EVENT]->(:CustomerEvent)` | Cần giải thích vì sao trạng thái thay đổi hoặc tái dựng từ luồng sự kiện | Dựng snapshot có thể tốn chi phí; thường cần phiên bản/snapshot bổ trợ |

Các mô hình này có thể phối hợp. Một hệ thống thường dùng node phiên bản cho truy vấn lịch sử, relationship có thời gian hiệu lực cho quan hệ đơn giản, và event cho nhật ký nghiệp vụ.

**Không nhầm “phiên bản thứ 3” với “trạng thái tại ngày thứ 3”.** Số phiên bản phản ánh thứ tự tạo/sửa; các phiên bản được nhập bổ sung hồi tố có thể có `validFrom` sớm hơn phiên bản được ghi trước đó.

## 3. Mô hình thực thể gốc và node phiên bản

Giữ một node gốc làm **danh tính ổn định** của thực thể, sau đó nối tới các node chứa trạng thái theo thời gian:

~~~mermaid
flowchart LR
    C["Customer<br/>customerId: C001"]
    V1["CustomerVersion v1<br/>BRONZE<br/>[2024-01-01, 2024-04-01)"]
    V2["CustomerVersion v2<br/>GOLD<br/>[2024-04-01, ∞)"]
    C -->|HAS_VERSION| V1
    C -->|HAS_VERSION| V2
~~~

Ở đây:

- `Customer.customerId` là khóa nghiệp vụ ổn định, dùng làm điểm bắt đầu truy vấn.
- `CustomerVersion` lưu thuộc tính có thể đổi: `loyaltyTier`, `fullName`, `validFrom`, `validTo` và `versionNo`.
- Relationship `HAS_VERSION` cho biết các trạng thái thuộc cùng một khách hàng.
- Thuộc tính bất biến hoặc được định nghĩa là danh tính có thể ở node gốc; thuộc tính cần truy vấn lịch sử phải nằm ở phiên bản tương ứng.

### 3.1. Ràng buộc và chỉ mục

Các câu lệnh Cypher sau dùng cú pháp Neo4j 5.x trở lên:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT customer_version_unique IF NOT EXISTS
FOR (v:CustomerVersion)
REQUIRE (v.customerId, v.versionNo) IS UNIQUE;

CREATE RANGE INDEX customer_version_time IF NOT EXISTS
FOR (v:CustomerVersion)
ON (v.customerId, v.validFrom);
~~~

Ràng buộc đầu tiên ngăn trùng danh tính gốc; ràng buộc thứ hai ngăn trùng **cặp** `(customerId, versionNo)`. Việc lặp `customerId` trong node phiên bản hỗ trợ định danh và lập chỉ mục, nhưng ứng dụng vẫn phải bảo đảm `CustomerVersion.customerId` khớp với node `Customer` mà nó nối tới.

Chỉ mục trên `(customerId, validFrom)` hữu ích cho truy vấn bắt đầu trực tiếp từ node phiên bản theo ID và thời gian. Nếu truy vấn luôn tìm `Customer` bằng ràng buộc duy nhất rồi đi qua `HAS_VERSION`, Neo4j có thể ưu tiên duyệt relationship; hãy dùng `EXPLAIN` hoặc `PROFILE` để xem kế hoạch thực tế.

### 3.2. Tạo ví dụ có hai phiên bản

~~~cypher
CREATE (c:Customer {customerId: 'C001'})
CREATE (v1:CustomerVersion {
    customerId: 'C001',
    versionNo: 1,
    validFrom: date('2024-01-01'),
    validTo: date('2024-04-01'),
    fullName: 'Nguyen An',
    loyaltyTier: 'BRONZE'
})
CREATE (v2:CustomerVersion {
    customerId: 'C001',
    versionNo: 2,
    validFrom: date('2024-04-01'),
    fullName: 'Nguyen An',
    loyaltyTier: 'GOLD'
})
CREATE (c)-[:HAS_VERSION]->(v1)
CREATE (c)-[:HAS_VERSION]->(v2);
~~~

Chạy đoạn tạo dữ liệu trên cơ sở dữ liệu thử nghiệm trống hoặc đổi ID nếu `C001` đã tồn tại. Phiên bản `v2` không có thuộc tính `validTo`, nghĩa là chưa có ngày hết hiệu lực được biết. Dữ liệu được khởi tạo để minh họa trạng thái nghiệp vụ, không hàm ý hai phiên bản đã được hệ thống ghi nhận vào đúng các ngày hiệu lực.

### 3.3. Truy vấn trạng thái “as of”

Giả sử ứng dụng truyền `$customerId = 'C001'` và `$asOf = '2024-03-15'` (chuỗi ngày ISO 8601):

~~~cypher
MATCH (c:Customer {customerId: $customerId})
      -[:HAS_VERSION]->(v:CustomerVersion)
WITH v, date($asOf) AS asOf
WHERE v.validFrom <= asOf
  AND (v.validTo IS NULL OR asOf < v.validTo)
RETURN v.versionNo AS version,
       v.fullName AS fullName,
       v.loyaltyTier AS loyaltyTier,
       v.validFrom AS validFrom,
       v.validTo AS validTo;
~~~

Kết quả của `2024-03-15` là phiên bản **1 / BRONZE**; của `2024-04-01` là phiên bản **2 / GOLD**. Với quy tắc không chồng lấn, truy vấn theo một thời điểm trả về tối đa một trạng thái của một thực thể. Nếu trả về nhiều dòng, đây là dấu hiệu phải kiểm tra tính toàn vẹn dữ liệu.

Để xem toàn bộ lịch sử thay vì một snapshot:

~~~cypher
MATCH (:Customer {customerId: $customerId})
      -[:HAS_VERSION]->(v:CustomerVersion)
RETURN v.versionNo AS version,
       v.loyaltyTier AS tier,
       v.validFrom AS fromDate,
       v.validTo AS toDate
ORDER BY v.validFrom, v.versionNo;
~~~

Muốn lấy trạng thái có hiệu lực **hôm nay**, dùng `date()` thay cho `date($asOf)`, với lưu ý “hôm nay” được xác định theo cách Neo4j xử lý thời gian và múi giờ của phiên truy vấn. Với nghiệp vụ theo múi giờ cụ thể, ứng dụng nên tính ngày nghiệp vụ rồi truyền vào tham số.

### 3.4. Ghi phiên bản mới trong một transaction

Khi thay đổi chỉ diễn ra **sau khoảng hiệu lực hiện có**, có thể đóng khoảng cũ và mở phiên bản mới:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
      -[:HAS_VERSION]->(old:CustomerVersion)
WHERE old.validTo IS NULL
  AND old.validFrom < date($effectiveFrom)
SET old.validTo = date($effectiveFrom)
CREATE (c)-[:HAS_VERSION]->(next:CustomerVersion {
    customerId: $customerId,
    versionNo: old.versionNo + 1,
    validFrom: date($effectiveFrom),
    fullName: $fullName,
    loyaltyTier: $loyaltyTier
})
RETURN next.versionNo AS version, next.validFrom AS validFrom;
~~~

Ví dụ này dành cho luồng cập nhật tuần tự, mỗi thực thể có **một phiên bản cuối chưa đóng**. Hãy chạy toàn bộ câu lệnh trong transaction ghi; việc đóng khoảng và tạo node mới phải thành công hoặc rollback cùng nhau. Trong môi trường có nhiều tác vụ cập nhật đồng thời, cần khóa/kiểm soát xung đột ở tầng ghi, sử dụng ràng buộc duy nhất để phát hiện trùng phiên bản và xử lý retry theo nghiệp vụ. Không giả định rằng `versionNo + 1` tự nó bảo đảm an toàn đồng thời.

Nếu muốn thay đổi có hiệu lực **hồi tố** (ví dụ ngày 15/03 khi đã có phiên bản bắt đầu 01/04), không dùng nguyên câu lệnh trên. Phải xác định khoảng bị tác động, chia hoặc điều chỉnh các khoảng liên quan, và kiểm tra lịch sử sau khi ghi. Cập nhật hồi tố còn khác với đính chính một thông tin đã được hệ thống ghi nhận sai, như phần mô hình hai trục thời gian bên dưới.

Một relationship phụ `CURRENT_VERSION` có thể tối ưu đọc trạng thái hiện tại, nhưng chỉ là dữ liệu suy ra. Nếu cho phép phiên bản có hiệu lực trong tương lai hoặc chỉnh hồi tố, phải định nghĩa rõ “current” và cập nhật con trỏ đúng lúc; truy vấn theo `validFrom/validTo` vẫn là cơ sở đáng tin cậy để truy xuất theo thời điểm.

## 4. Lịch sử relationship: ai liên kết với ai tại thời điểm nào?

Không phải thay đổi nào cũng cần node phiên bản. Relationship có thể mang trực tiếp khoảng hiệu lực. Ví dụ nhân viên `E01` thuộc phòng `D01` đến trước 01/07/2024, rồi chuyển sang `D02`:

~~~cypher
CREATE (e:Employee {employeeId: 'E01'})
CREATE (d1:Department {deptId: 'D01', name: 'Sales'})
CREATE (d2:Department {deptId: 'D02', name: 'Operations'})
CREATE (e)-[:WORKS_IN {
    validFrom: date('2024-01-01'),
    validTo: date('2024-07-01')
}]->(d1)
CREATE (e)-[:WORKS_IN {
    validFrom: date('2024-07-01')
}]->(d2);
~~~

Truy vấn phòng ban tại một ngày bất kỳ:

~~~cypher
MATCH (:Employee {employeeId: $employeeId})
      -[r:WORKS_IN]->(d:Department)
WITH r, d, date($asOf) AS asOf
WHERE r.validFrom <= asOf
  AND (r.validTo IS NULL OR asOf < r.validTo)
RETURN d.deptId AS departmentId, d.name AS departmentName;
~~~

Ngày `2024-06-30` trả về `D01`; ngày `2024-07-01` trả về `D02`. **Không xóa cạnh `WORKS_IN` cũ** khi nhân viên chuyển phòng, vì làm vậy sẽ mất lịch sử quan hệ.

Có một giới hạn quan trọng: nếu `Department.name` bị sửa trực tiếp từ `Sales` thành tên mới, câu truy vấn lịch sử vẫn trả về **tên hiện tại** của phòng ban. Nếu cần snapshot chính xác cả tên phòng ban tại thời điểm trước đây, hãy phiên bản hóa cả thực thể `Department` hoặc liên kết tới một phiên bản bất biến.

Khi bản thân mối quan hệ có nhiều thuộc tính, vòng đời hoặc các lần đính chính (ví dụ hợp đồng bổ nhiệm, vai trò, tỷ lệ phân bổ), có thể **nâng quan hệ thành node nghiệp vụ**:

~~~text
(:Employee)-[:HAS_ASSIGNMENT]->(:Assignment {
    assignmentId, validFrom, validTo, role
})-[:TO_DEPARTMENT]->(:Department)
~~~

Node `Assignment` dễ có ID riêng, lịch sử phiên bản, tài liệu đính kèm và các quan hệ bổ sung. Đây là lựa chọn phù hợp khi cạnh đơn giản không đủ biểu diễn ngữ nghĩa.

## 5. Mô hình hai trục thời gian (bitemporal)

Một phiên bản chỉ có `validFrom/validTo` cho biết **điều gì được coi là đúng trong nghiệp vụ hiện nay**. Nó không đủ để trả lời: **“Vào ngày 10/04, hệ thống đã tin rằng khách hàng có hạng gì vào ngày 15/03?”**

Để trả lời, mỗi sự thật/phiên bản cần hai khoảng độc lập:

- `validFrom` / `validTo`: thời gian đúng trong nghiệp vụ.
- `recordedFrom` / `recordedTo`: thời gian hệ thống coi sự thật đó là bản ghi được chấp nhận.

Ví dụ: hệ thống từng ghi nhận hạng `GOLD` có hiệu lực từ 01/03/2024, nhưng đến 01/05/2024 mới được đính chính rằng nó phải có hiệu lực từ 01/02/2024.

| Bản ghi | Hạng | Khoảng hiệu lực (valid) | Khoảng ghi nhận (recorded) |
| --- | --- | --- | --- |
| A | `BRONZE` | [01/01, 01/03) | [05/01, 01/05) |
| B | `GOLD` | [01/03, ∞) | [02/03, 01/05) |
| C | `BRONZE` | [01/01, 01/02) | [01/05, ∞) |
| D | `GOLD` | [01/02, ∞) | [01/05, ∞) |

*Tất cả ngày trong bảng thuộc năm 2024; “∞” chỉ khoảng chưa đóng.* Bản ghi A/B diễn tả góc nhìn trước đính chính; C/D diễn tả góc nhìn sau đính chính. Tại một thời điểm `recordedAt` xác định, chỉ xét các bản ghi có khoảng ghi nhận bao phủ thời điểm đó; do đó các khoảng valid của A/B không mâu thuẫn với C/D.

Có thể lưu các bản ghi này dưới label `CustomerAssertion`, nối từ `Customer` bằng `HAS_ASSERTION`. Đặt một node với thuộc tính ví dụ:

~~~cypher
CREATE (:CustomerAssertion {
    customerId: 'C001',
    loyaltyTier: 'GOLD',
    validFrom: date('2024-02-01'),
    recordedFrom: datetime('2024-05-01T00:00:00Z')
});
~~~

Đoạn trên chỉ minh họa thuộc tính của assertion D. Trong mô hình đầy đủ, cần tạo liên kết với node `Customer` và ghi cả các assertion còn lại.

Truy vấn bitemporal, với `$validAt` là chuỗi ngày ISO và `$knownAt` là chuỗi thời điểm ISO có múi giờ:

~~~cypher
MATCH (:Customer {customerId: $customerId})
      -[:HAS_ASSERTION]->(a:CustomerAssertion)
WITH a, date($validAt) AS validAt,
        datetime($knownAt) AS knownAt
WHERE a.validFrom <= validAt
  AND (a.validTo IS NULL OR validAt < a.validTo)
  AND a.recordedFrom <= knownAt
  AND (a.recordedTo IS NULL OR knownAt < a.recordedTo)
RETURN a.loyaltyTier AS tier,
       a.validFrom AS effectiveFrom,
       a.recordedFrom AS knownFrom;
~~~

Với ví dụ trong bảng:

- `validAt = 2024-02-15`, `knownAt = 2024-04-10T12:00:00Z`: trả về `BRONZE` theo bản ghi A.
- `validAt = 2024-02-15`, `knownAt = 2024-05-10T12:00:00Z`: trả về `GOLD` theo bản ghi D.

Khi đính chính, ghi một transaction để **đóng `recordedTo` của các assertion bị thay thế và tạo assertion mới** theo các khoảng valid đã được sửa. Không ghi đè hạng/valid time lên assertion cũ nếu cần bảo toàn câu trả lời “hệ thống biết gì tại thời điểm trước”. Việc chỉnh `recordedTo` là cập nhật siêu dữ liệu kết thúc hiệu lực ghi nhận; nội dung khẳng định cũ vẫn được giữ.

**Lưu ý:** Neo4j hỗ trợ các kiểu dữ liệu thời gian và transaction, nhưng không tự cung cấp tính năng system-versioned/bitemporal tự động cho mô hình này. `recordedFrom/recordedTo` phải được ứng dụng hoặc pipeline ghi nhận nhất quán. Nếu yêu cầu chính xác theo thứ tự commit, hãy thiết kế thêm cơ chế nhận diện giao dịch và xử lý đồng thời; timestamp lấy ở phía ứng dụng không mặc nhiên bằng thời điểm commit thật.

## 6. Phát hiện khoảng chồng lấn và dữ liệu sai

Chọn trước các bất biến nghiệp vụ. Ví dụ, “mỗi khách hàng có **tối đa một** hạng hợp lệ tại mỗi thời điểm”. Cypher không tự cấm hai phiên bản trùng khoảng chỉ bằng ràng buộc duy nhất trên `(customerId, versionNo)`.

### 6.1. Kiểm tra khoảng không hợp lệ

~~~cypher
MATCH (v:CustomerVersion)
WHERE v.validFrom IS NULL
   OR (v.validTo IS NOT NULL AND v.validTo <= v.validFrom)
RETURN v.customerId, v.versionNo, v.validFrom, v.validTo;
~~~

Kết quả lý tưởng là **0 dòng**: mọi khoảng phải có đầu và, nếu có cuối, cuối phải lớn hơn đầu.

### 6.2. Phát hiện hai phiên bản chồng lấn

Hai khoảng nửa mở `[aFrom, aTo)` và `[bFrom, bTo)` chồng lấn khi `aFrom < bTo` và `bFrom < aTo`:

~~~cypher
MATCH (c:Customer)-[:HAS_VERSION]->(a:CustomerVersion),
      (c)-[:HAS_VERSION]->(b:CustomerVersion)
WHERE a.versionNo < b.versionNo
  AND a.validFrom < coalesce(b.validTo, date('9999-12-31'))
  AND b.validFrom < coalesce(a.validTo, date('9999-12-31'))
RETURN c.customerId AS customerId,
       a.versionNo AS versionA,
       b.versionNo AS versionB,
       a.validFrom AS fromA, a.validTo AS toA,
       b.validFrom AS fromB, b.validTo AS toB;
~~~

Truy vấn này dùng ngày `9999-12-31` làm mốc thay thế cho cuối mở; chỉ dùng nếu dữ liệu nghiệp vụ không vượt qua mốc ấy. Nó phục vụ kiểm tra dữ liệu và có thể tốn chi phí khi mỗi thực thể có rất nhiều phiên bản.

### 6.3. Đếm các khoảng chưa đóng

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:HAS_VERSION]->(v:CustomerVersion)
WHERE v.validTo IS NULL
WITH c, count(v) AS openVersions
WHERE openVersions <> 1
RETURN c.customerId AS customerId, openVersions;
~~~

Nếu quy tắc mỗi khách hàng có đúng một phiên bản cuối chưa đóng, kết quả cũng phải **0 dòng**. Nếu nghiệp vụ cho phép một thực thể chưa có phiên bản, hoặc mọi khoảng đều có hạn chót, hãy điều chỉnh bất biến tương ứng.

Bên cạnh chồng lấn, phải kiểm tra **khoảng trống** nếu nghiệp vụ đòi lịch sử liên tục: sắp xếp theo `validFrom`, rồi đối chiếu `validTo` của phiên bản trước với `validFrom` của phiên bản tiếp theo. Một khoảng trống không nhất thiết là lỗi, ví dụ nhân viên nghỉ việc rồi quay lại; quy tắc phải bám vào nghiệp vụ thực tế.

## 7. Truy vấn khoảng thời gian và tối ưu hiệu năng

Ngoài câu hỏi “tại ngày X”, hệ thống còn cần biết **những phiên bản nào giao với một khoảng [start, end)**. Điều kiện giao hai khoảng là:

~~~cypher
MATCH (:Customer {customerId: $customerId})
      -[:HAS_VERSION]->(v:CustomerVersion)
WITH v, date($rangeStart) AS rangeStart,
        date($rangeEnd) AS rangeEnd
WHERE rangeStart < rangeEnd
  AND v.validFrom < rangeEnd
  AND (v.validTo IS NULL OR rangeStart < v.validTo)
RETURN v.versionNo, v.loyaltyTier, v.validFrom, v.validTo
ORDER BY v.validFrom;
~~~

Điều kiện dùng `<` thay cho `<=` để hai khoảng chỉ **chạm biên** không bị coi là giao nhau.

Một số lưu ý khi triển khai lớn:

1. **Bắt đầu từ khóa có chỉ mục** (ví dụ `Customer.customerId`) trước khi duyệt `HAS_VERSION`; tránh quét toàn bộ đồ thị cho từng request.
2. Với lịch sử rất dài, cân nhắc truy vấn trực tiếp `CustomerVersion` theo `customerId` và `validFrom` để tận dụng chỉ mục kết hợp; dùng `PROFILE` để xác nhận thay vì đoán.
3. Chỉ trả về trường cần thiết; phân trang lịch sử có `ORDER BY` ổn định khi dữ liệu lớn.
4. Phân biệt dữ liệu phục vụ **truy vấn trạng thái hiện tại** và **lịch sử kiểm toán**. Có thể duy trì snapshot hiện tại để đọc nhanh, nhưng phải cập nhật đồng bộ và luôn có cơ chế truy hồi từ lịch sử.
5. Với dữ liệu bitemporal, độ lớn có thể tăng nhanh khi đính chính làm tách nhiều khoảng. Xây dựng chính sách lưu giữ, kiểm thử tải truy vấn và giới hạn phạm vi truy xuất hợp lý.

## 8. Những quyết định cần chốt trước khi triển khai

| Câu hỏi thiết kế | Khuyến nghị |
| --- | --- |
| Thực thể cần ID ổn định xuyên các phiên bản? | Giữ node gốc có khóa nghiệp vụ, các trạng thái ở node phiên bản. |
| Quan hệ thay đổi nhưng hai đầu không cần phiên bản hóa? | Đặt `validFrom/validTo` trên relationship và giữ cạnh lịch sử. |
| Cần tái hiện cả thuộc tính của hai đầu quan hệ trong quá khứ? | Phiên bản hóa các node đầu mút hoặc mô hình hóa liên kết tới các version tương ứng. |
| Có dữ liệu đến trễ hoặc sửa sai hồi tố? | Tách valid time và recorded time; không ghi đè assertion cũ. |
| Cần biết “vì sao” có một thay đổi? | Lưu event nghiệp vụ hoặc metadata nguồn thay đổi, người thực hiện, lý do, mã giao dịch. |
| Có thể có nhiều trạng thái hợp lệ đồng thời? | Định nghĩa lại khóa và bất biến; chẳng hạn hạng theo từng chương trình khách hàng. |
| Hệ thống ghi đồng thời? | Dùng transaction ghi, ràng buộc duy nhất, kiểm soát xung đột và kiểm tra chồng lấn ở tầng ứng dụng. |

Khi dùng **Java Driver** hoặc **Spring Data Neo4j**, hãy truyền kiểu ngày/giờ có cấu trúc (ví dụ `LocalDate` cho `date`, kiểu có offset/múi giờ tương ứng cho `datetime`), giữ câu lệnh tạo phiên bản và đóng phiên bản cũ trong **cùng một transaction**, và đặt logic kiểm tra bất biến ở một nơi rõ ràng. Không nên để nhiều nhánh dịch vụ tự cập nhật các khoảng hiệu lực theo những quy tắc khác nhau.

## 9. Bài tập tự kiểm tra

**Tình huống 1.** Khách hàng `C001` có hai phiên bản như mục 3. Hãy dự đoán kết quả truy vấn `asOf` tại `2024-03-31`, `2024-04-01` và `2024-06-01`.

**Đáp án:** lần lượt là `BRONZE`, `GOLD`, `GOLD`. Ngày 01/04 thuộc phiên bản mới vì dùng khoảng `[from, to)`.

**Tình huống 2.** Nhân viên `E01` chuyển từ `D01` sang `D02` vào 01/07/2024. Có nên xóa cạnh `WORKS_IN` tới `D01`?

**Đáp án:** Không. Đóng hiệu lực cạnh cũ tại `2024-07-01` và tạo cạnh mới bắt đầu tại ngày đó. Xóa cạnh cũ sẽ khiến truy vấn lịch sử trước tháng 7 trả về thiếu dữ liệu.

**Tình huống 3.** Ngày 01/05 hệ thống phát hiện dữ liệu ghi từ tháng 3 có ngày hiệu lực sai. Chỉ sửa trực tiếp `validFrom` của node cũ có bảo toàn lịch sử kiểm toán không?

**Đáp án:** Không, nếu cần biết trước 01/05 hệ thống đã ghi nhận ngày nào. Khi đó cần mô hình hai trục thời gian hoặc lưu sự kiện đính chính có thể truy vết. Bitemporal bảo toàn cả trạng thái nghiệp vụ theo ngày hiệu lực và trạng thái tri thức của hệ thống theo ngày ghi nhận.

**Ghi nhớ:** Mô hình thời gian đúng phải định nghĩa rõ **điều gì có hiệu lực**, **khi nào có hiệu lực**, **khi nào hệ thống ghi nhận**, và **những trạng thái cũ nào bắt buộc được bảo toàn**. Các quy tắc về khoảng thời gian, phiên bản và transaction quyết định độ tin cậy của truy vấn lịch sử trong Neo4j.
