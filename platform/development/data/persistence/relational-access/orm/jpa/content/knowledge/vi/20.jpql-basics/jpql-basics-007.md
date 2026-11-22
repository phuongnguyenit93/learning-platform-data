# Sắp xếp kết quả và xử lý giá trị bằng nhau

Trong JPQL (*Jakarta Persistence Query Language*), truy vấn không có `ORDER BY` **không cam kết thứ tự trả về**. Một danh sách sản phẩm có thể trông như được sắp theo ID ở lần chạy đầu, nhưng thứ tự ấy có thể đổi khi dữ liệu tăng, thêm index, DB chọn query plan khác hoặc ứng dụng phân trang.

Ngay cả khi đã viết `ORDER BY p.price ASC`, vấn đề vẫn chưa hoàn toàn được giải quyết: **nhiều sản phẩm có cùng giá**. Database chỉ phải bảo đảm sản phẩm giá thấp đứng trước sản phẩm giá cao; nó không bắt buộc phải duy trì thứ tự ổn định giữa các hàng có **giá bằng nhau**. Khi danh sách được phân trang, các giá trị bằng nhau (*ties*) có thể khiến kết quả giữa các trang khó dự đoán nếu không có quy tắc sắp xếp phụ.

Bài học trong chương **JPQL cơ bản** trình bày cách dùng `ORDER BY`, `ASC`, `DESC`, nhiều tiêu chí sắp xếp, xử lý giá trị bằng nhau và `NULL`, bảo đảm thứ tự ổn định bằng khóa định danh, đồng thời áp dụng vào phân trang, truy vấn tổng hợp và truy vấn động.

## 1. Vì sao một danh sách cần thứ tự rõ ràng?

Giả sử bảng `product` có các sản phẩm:

| ID | Tên | Giá (VND) | Điểm ưu tiên |
|---:|---|---:|---:|
| 11 | Bút bi | 12.000 | `NULL` |
| 12 | Vở kẻ ngang | 20.000 | 5 |
| 13 | Thước kẻ | 12.000 | 4 |
| 14 | Sổ tay | 35.000 | 5 |
| 15 | Bút bi | 12.000 | `NULL` |
| 16 | Bút máy | 12.000 | `NULL` |

Nếu truy vấn:

```jpql
SELECT p FROM Product p
```

thì tập kết quả chứa các entity phù hợp, nhưng **không có bảo đảm** rằng `ID 11` sẽ xuất hiện trước `ID 12` hay rằng dữ liệu sẽ được sắp theo thứ tự chèn.

Nếu viết:

```jpql
SELECT p
FROM Product p
ORDER BY p.price ASC
```

ta xác định rằng sản phẩm giá 12.000 phải đứng trước 20.000, rồi trước 35.000. Tuy nhiên, trong nhóm giá 12.000 có bốn ID `11, 13, 15, 16`; **thứ tự bên trong nhóm này vẫn chưa được quyết định**.

Để thứ tự ổn định theo một quy tắc có thể tái tạo, ta thêm tiêu chí phụ:

```jpql
SELECT p
FROM Product p
ORDER BY p.price ASC, p.id ASC
```

Khi đó thứ tự trên bộ dữ liệu ví dụ trở thành:

```text
11  Bút bi       12000
13  Thước kẻ     12000
15  Bút bi       12000
16  Bút máy      12000
12  Vở kẻ ngang  20000
14  Sổ tay       35000
```

Ở đây ID là **khóa phân xử cuối cùng** (*tie-breaker*), vì khóa chính là duy nhất đối với các hàng của entity. Kết quả sẽ có thứ tự xác định **trên một tập dữ liệu không đổi**. Nếu các transaction khác thêm, xóa hoặc sửa sản phẩm giữa hai lần đọc, nội dung và vị trí tương đối của một số hàng vẫn có thể thay đổi.

## 2. ORDER BY trong JPQL: cú pháp cơ bản

Cấu trúc thông dụng:

```jpql
SELECT p
FROM Product p
WHERE p.category = :category
ORDER BY p.price ASC
```

Giải thích:

- `SELECT p`: trả các entity `Product`.
- `FROM Product p`: dùng **tên entity Java** `Product` và alias `p`, không dùng trực tiếp tên bảng vật lý `product`.
- `WHERE p.category = :category`: lọc theo category với tham số.
- `ORDER BY p.price ASC`: sắp tăng dần theo thuộc tính `price` của entity.

Trong Java:

```java
List<Product> products = em.createQuery(
        """
        SELECT p
        FROM Product p
        WHERE p.category = :category
        ORDER BY p.price ASC
        """,
        Product.class
    )
    .setParameter("category", "stationery")
    .getResultList();
```

Tên `p.price` tham chiếu **thuộc tính trong mô hình entity**, không phải tên cột SQL nếu `@Column(name=...)` đã đổi tên cột. Provider chịu trách nhiệm chuyển truy vấn JPQL thành SQL cho database.

### ASC và DESC

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| `ORDER BY p.price ASC` | Giá tăng dần | 12.000 → 20.000 → 35.000 |
| `ORDER BY p.price DESC` | Giá giảm dần | 35.000 → 20.000 → 12.000 |
| `ORDER BY p.name ASC` | Tên tăng dần theo quy tắc so sánh chuỗi của DB | Thứ tự phụ thuộc collation |
| `ORDER BY p.createdAt DESC` | Mới nhất trước theo timestamp | Những timestamp trùng nhau cần tie-breaker |
| `ORDER BY p.id` | Sắp tăng dần, do `ASC` là mặc định khi bỏ qua hướng | Theo giá trị khóa định danh |

Có thể viết ngắn:

```jpql
ORDER BY p.price
```

với cùng ý nghĩa hướng tăng dần như `ORDER BY p.price ASC`.

**Không có `ORDER BY` không có nghĩa mặc định `ORDER BY id ASC`.** Điều này vẫn đúng cả khi bảng có primary key, ORM đã lưu entity theo thứ tự chèn hoặc DB thường dùng index khóa chính.

## 3. Nhiều tiêu chí: tiêu chí bên trái có ưu tiên cao hơn

JPQL cho phép đưa nhiều biểu thức sắp xếp, ngăn cách bằng dấu phẩy:

```jpql
SELECT p
FROM Product p
ORDER BY p.category ASC,
         p.price DESC,
         p.id ASC
```

Cách đọc theo thứ tự:

1. Nhóm theo `category` tăng dần.
2. Trong cùng một `category`, giá cao đứng trước giá thấp.
3. Trong cùng category **và cùng giá**, ID nhỏ hơn đứng trước.

```text
category = stationery
    price = 35000  -> ID 14
    price = 20000  -> ID 12
    price = 12000  -> ID 11, 13, 15, 16 (ID tăng dần)
```

Mỗi tiêu chí có thể chọn hướng riêng:

```jpql
ORDER BY p.category ASC, p.price DESC, p.id ASC
```

Không có quy tắc rằng mọi tiêu chí phải cùng `ASC` hoặc cùng `DESC`.

### Hai cách viết khác ý nghĩa

```jpql
ORDER BY p.price DESC, p.name ASC
```

Ưu tiên giá, rồi tên khi giá trùng.

```jpql
ORDER BY p.name ASC, p.price DESC
```

Ưu tiên tên; giá chỉ được xét nếu tên trùng. Trong dữ liệu có hai sản phẩm tên "Bút bi", quy tắc thứ hai dùng giá phân xử giữa các hàng tên giống nhau.

**Thứ tự tiêu chí là một phần của yêu cầu nghiệp vụ**, không đơn thuần là vấn đề trình bày.

## 4. Giá trị bằng nhau: tie trong ORDER BY

Hai hàng `a` và `b` là **tie** theo một quy tắc sắp xếp nếu tất cả biểu thức hiện có trong `ORDER BY` cho các giá trị không phân biệt được theo bộ so sánh áp dụng.

Ví dụ:

```jpql
ORDER BY p.price ASC
```

Các sản phẩm cùng giá 12.000 là tie. Nếu bổ sung:

```jpql
ORDER BY p.price ASC, p.name ASC
```

hai sản phẩm cùng giá và cùng tên "Bút bi" vẫn tie.

Nếu bổ sung khóa cuối:

```jpql
ORDER BY p.price ASC, p.name ASC, p.id ASC
```

thì các entity khác nhau với ID duy nhất có thứ tự phân biệt. Với một entity table và bộ dữ liệu không đổi, điều này tạo **total ordering** trên các hàng được trả về.

### Vì sao DB không giữ mặc định thứ tự các hàng tie?

Trong SQL và JPQL, `ORDER BY` chỉ đặt ra yêu cầu với các biểu thức được liệt kê. Khi nhiều hàng có cùng giá trị sắp xếp, DB có thể trả chúng theo nhiều thứ tự mà vẫn đáp ứng query:

- Thứ tự đến từ index scan.
- Thứ tự sau bước sort của execution plan.
- Thứ tự do parallel execution hoặc pagination.
- Thứ tự thay đổi sau vacuum/rebuild/index maintenance hay cập nhật thống kê.
- Thứ tự khác nhau khi optimizer chọn plan mới.

Không nên dựa vào việc “tôi chạy 100 lần thấy giống nhau” để kết luận thứ tự tie được đảm bảo.

### Tie-breaker nên là gì?

Tiêu chí cuối cùng thường là một hoặc nhiều thuộc tính **ổn định và duy nhất**:

- `p.id ASC` nếu entity có khóa chính đơn.
- `p.id.tenantId ASC, p.id.orderNo ASC` nếu dùng `@EmbeddedId` gồm hai thành phần và cần phân giải theo khóa ghép.
- Một natural key thực sự unique và ổn định nếu phù hợp.

Không nên chọn một field có thể trùng tiếp như `updatedAt` rồi cho rằng thứ tự đã hoàn toàn xác định. Nếu có cả nhiều tiêu chí nghiệp vụ và khóa, giữ khóa ở **cuối** để không thay đổi quy tắc ưu tiên chính.

## 5. Thứ tự ổn định và phân trang OFFSET

Một ứng dụng hiển thị 3 sản phẩm mỗi trang:

```java
List<Product> page = em.createQuery(
        """
        SELECT p FROM Product p
        ORDER BY p.price ASC, p.id ASC
        """,
        Product.class
    )
    .setFirstResult(pageIndex * pageSize)
    .setMaxResults(pageSize)
    .getResultList();
```

Trong ví dụ, `pageIndex` là chỉ số bắt đầu từ 0 và `pageSize` là số hàng trên trang. Với dữ liệu đã liệt kê, nếu `pageSize = 3`:

| Trang | Hàng |
|---|---|
| 0 | ID 11, 13, 15 |
| 1 | ID 16, 12, 14 |

Nhờ `id` cuối `ORDER BY`, ta biết mỗi sản phẩm cùng giá thuộc vị trí nào **trong một snapshot dữ liệu không đổi**.

### Chỉ ORDER BY price có thể khiến trang thiếu ổn định

```jpql
SELECT p FROM Product p ORDER BY p.price ASC
```

Nếu giới hạn là 3, DB có thể đặt ID 11, 13, 15 trong page đầu ở một lần, nhưng lần khác đặt ID 16, 11, 13. Một ID có thể xuất hiện ở nhiều trang khi client lấy từng trang bằng các query riêng, hoặc một ID bị bỏ qua, **ngay cả khi dữ liệu không đổi** mà thứ tự tie được DB chọn khác nhau.

Sửa bằng một thứ tự cuối cùng mang tính duy nhất:

```jpql
ORDER BY p.price ASC, p.id ASC
```

### Nhưng tie-breaker không chống được mọi thay đổi giữa các trang

Giả sử sau khi client tải trang 0, một sản phẩm mới có giá thấp được chèn vào đầu danh sách. Khi client tải trang 1 bằng offset, các hàng phía sau đã dịch vị trí. Dù `ORDER BY` hoàn toàn xác định, client vẫn có thể thấy một hàng lặp hoặc bỏ qua một hàng.

Vì vậy cần phân biệt:

- **Deterministic ordering:** các hàng tie được phân xử nhất quán trên cùng tập dữ liệu.
- **Consistent pagination across changes:** các trang được đọc theo một snapshot đủ ổn định, hoặc dùng chiến lược cursor/keyset phù hợp.

Đây là hai vấn đề khác nhau; một tie-breaker là cần thiết cho phân trang ổn định nhưng **không tự tạo snapshot giao dịch xuyên các HTTP request**.

## 6. Phân trang theo keyset khi nhiều giá bằng nhau

Với trang rất sâu, offset pagination có thể phải đi qua nhiều hàng trước khi lấy được page. **Keyset pagination** (cursor pagination) dùng giá trị của hàng cuối trang trước để định nghĩa điểm bắt đầu của trang tiếp theo.

Giả sử thứ tự là:

```jpql
ORDER BY p.price ASC, p.id ASC
```

Hàng cuối trang trước có:

```text
lastPrice = 12000.00
lastId = 15
```

Trang tiếp theo cần các hàng có:

- `price > lastPrice`; hoặc
- `price == lastPrice` và `id > lastId`.

JPQL:

```java
List<Product> nextPage = em.createQuery(
        """
        SELECT p
        FROM Product p
        WHERE p.price > :lastPrice
           OR (p.price = :lastPrice AND p.id > :lastId)
        ORDER BY p.price ASC, p.id ASC
        """,
        Product.class
    )
    .setParameter("lastPrice", lastPrice)
    .setParameter("lastId", lastId)
    .setMaxResults(pageSize)
    .getResultList();
```

Nếu thay đổi sang **giá giảm dần, ID tăng dần**:

```jpql
ORDER BY p.price DESC, p.id ASC
```

thì điều kiện cursor tương ứng:

```jpql
WHERE p.price < :lastPrice
   OR (p.price = :lastPrice AND p.id > :lastId)
```

Không nên dùng mỗi `WHERE p.price > :lastPrice` khi có các sản phẩm cùng giá: như vậy các phần tử còn lại thuộc cùng mức giá sẽ bị bỏ qua.

### Những giới hạn của ví dụ keyset

- Điều kiện trên giả định `price` **không NULL** và `id` mang thứ tự so sánh phù hợp.
- Cursor phải chứa **toàn bộ thành phần ORDER BY** cần thiết để xác định vị trí.
- Nếu thứ tự gồm `category, price, id`, biểu thức sau cursor phải xử lý so sánh từ trái sang phải cho cả ba thành phần.
- Muốn qua các giá trị NULL cần thiết kế khóa phân loại NULL và điều kiện cursor tương ứng.
- Nếu giá của một sản phẩm thay đổi giữa hai page, sản phẩm có thể dịch vị trí; keyset không tự bảo đảm một snapshot bất biến.
- Khi API cần bảo đảm danh sách nhất quán tuyệt đối, có thể cần snapshot/export job, transaction isolation phù hợp hoặc cố định một mốc dữ liệu.

Keyset đặc biệt hữu ích khi truy vấn duyệt tuần tự lượng dữ liệu lớn và có index phù hợp với thứ tự.

## 7. NULL: thứ tự mặc định không giống nhau trên mọi DB

Một số tiêu chí có thể thiếu giá trị, ví dụ `Product.rating`:

| ID | Tên | Rating |
|---:|---|---:|
| 11 | Bút bi | `NULL` |
| 12 | Vở kẻ ngang | 5 |
| 13 | Thước kẻ | 4 |
| 14 | Sổ tay | 5 |
| 15 | Bút bi | `NULL` |
| 16 | Bút máy | `NULL` |

Xét:

```jpql
SELECT p FROM Product p
ORDER BY p.rating DESC, p.id ASC
```

Giá trị rating 5, 4 đã có hướng giảm dần; nhưng **NULL đứng trước hay sau** có thể phụ thuộc hệ quản trị DB, dialect, provider và tính năng JPQL/SQL được hỗ trợ. **Không dựa vào một vị trí NULL mặc định** nếu yêu cầu UI phải nhất quán xuyên nhiều DB.

### Đưa NULL xuống cuối bằng CASE

Một cách rõ ràng cho các provider hỗ trợ biểu thức `CASE` trong `ORDER BY` là tạo một khóa phân loại:

```jpql
SELECT p
FROM Product p
ORDER BY
    CASE WHEN p.rating IS NULL THEN 1 ELSE 0 END ASC,
    p.rating DESC,
    p.id ASC
```

Giải thích:

1. Khi `rating` khác NULL, biểu thức `CASE` trả 0.
2. Khi `rating` là NULL, biểu thức `CASE` trả 1.
3. `ASC` trên khóa phân loại đặt 0 trước 1 → những hàng có rating nằm trước NULL.
4. Trong nhóm có rating, sắp rating giảm dần.
5. Trong nhóm rating bằng nhau, hoặc cùng NULL, dùng ID tăng dần để phân xử.

Kết quả trên bộ dữ liệu minh họa:

```text
ID 12  rating 5
ID 14  rating 5
ID 13  rating 4
ID 11  rating NULL
ID 15  rating NULL
ID 16  rating NULL
```

Để đặt NULL lên **đầu**:

```jpql
ORDER BY
    CASE WHEN p.rating IS NULL THEN 0 ELSE 1 END ASC,
    p.rating DESC,
    p.id ASC
```

Mục đích là thể hiện **quy tắc phân loại explicit**, không phụ thuộc default ordering của DB.

### Có dùng NULLS FIRST / NULLS LAST được không?

Một số database và phiên bản ngôn ngữ/provider hỗ trợ cú pháp:

```sql
ORDER BY rating DESC NULLS LAST
```

Tuy nhiên, khả năng dùng `NULLS FIRST`/`NULLS LAST` trực tiếp trong **JPQL** phụ thuộc phiên bản Jakarta Persistence và provider. Không lấy cú pháp SQL native làm cam kết rằng mọi môi trường JPQL đang chạy đều chấp nhận. Nếu dự án cần tính portable trên cấu hình JPA đang sử dụng, có thể chọn `CASE`, hoặc xác nhận rõ hỗ trợ của provider/dialect rồi dùng tính năng tương ứng.

## 8. COALESCE và CASE khi giá trị bị thiếu

Có thể dùng `COALESCE` để thay NULL bằng giá trị dự phòng:

```jpql
ORDER BY COALESCE(p.rating, -1) DESC, p.id ASC
```

Với rating hợp lệ trong khoảng 0–5, `-1` có thể khiến NULL đứng sau khi DESC. Nhưng cách này có một **điều kiện ẩn**: dữ liệu thật không bao giờ có rating `-1`. Nếu quy tắc dữ liệu đổi hoặc fallback trùng một giá trị có thật, các hàng NULL và hàng có rating thật bị xếp cùng nhóm.

Bởi vậy:

- Dùng `COALESCE` khi giá trị thay thế có **ngữ nghĩa nghiệp vụ rõ** và miền giá trị được kiểm soát.
- Dùng `CASE WHEN ... IS NULL` khi chỉ muốn **kiểm soát vị trí NULL**, không đồng nhất NULL với một giá trị thật.
- Luôn thêm tie-breaker cuối nếu các biểu thức phía trước có thể trùng.

Ví dụ hiển thị sản phẩm chưa được chấm điểm trước:

```jpql
ORDER BY
    CASE WHEN p.rating IS NULL THEN 0 ELSE 1 END ASC,
    p.createdAt DESC,
    p.id DESC
```

Ở đây yêu cầu là: chưa có điểm trước, trong từng nhóm thì mới tạo trước, cuối cùng ID giảm dần.

## 9. String, chữ hoa/thường và collation

Khi sắp tên:

```jpql
ORDER BY p.name ASC, p.id ASC
```

thứ tự giữa `"Bút bi"`, `"bút bi"`, `"BÚT BI"` hoặc tên có dấu tiếng Việt phụ thuộc **collation của database** và kiểu cột. JPQL không tự cung cấp một quy tắc so sánh ngôn ngữ tiếng Việt bất biến trên mọi DB.

### Muốn giảm ảnh hưởng hoa/thường

Có thể chuẩn hóa biểu thức:

```jpql
ORDER BY LOWER(p.name) ASC, p.id ASC
```

Nhưng các chuỗi khác nhau có thể cùng `LOWER(...)`, ví dụ `"Notebook"` và `"notebook"`. Khi tie, ID sẽ phân xử.

Nếu muốn phân biệt thêm tên gốc trước ID:

```jpql
ORDER BY LOWER(p.name) ASC, p.name ASC, p.id ASC
```

Dù có `LOWER`, kết quả thứ tự vẫn có thể chịu ảnh hưởng collation/Unicode của DB, nhất là ký tự có dấu hoặc các ngôn ngữ có quy tắc case-folding đặc thù.

### Đừng tự khẳng định thứ tự bảng chữ cái tiếng Việt

Sort mặc định của một DB có thể dùng binary/code-point, collation tiếng Anh hoặc collation đặc thù locale. Để có thứ tự tiếng Việt đúng nhu cầu, cần thiết kế/cấu hình **collation phù hợp của DB** và kiểm tra với dữ liệu thật như `A, Ă, Â, D, Đ, E, Ê` cùng tên viết hoa/thường.

Có thể dùng native SQL với biểu thức `COLLATE` theo DB khi cần, nhưng cú pháp collation không portable; cân nhắc tạo **sort key chuẩn hóa** hoặc cột lưu khóa sắp xếp nếu yêu cầu rất nghiêm ngặt.

### Index và LOWER

`ORDER BY LOWER(p.name)` có thể không tận dụng index B-tree thông thường trên `name` theo cách tối ưu. Một số DB hỗ trợ function-based/expression index. Việc chọn index cần dựa trên plan và workload; không đánh đổi tính đúng hiển thị chỉ để giữ index mặc định.

## 10. Sắp theo ngày giờ: các giá trị timestamp cũng có thể trùng

Một use case phổ biến:

```jpql
SELECT p
FROM Product p
ORDER BY p.createdAt DESC
```

Nhìn có vẻ đủ để hiển thị mới nhất trước. Nhưng nếu nhiều hàng tạo trong cùng mili-giây hoặc cùng độ chính xác timestamp của cột SQL, chúng sẽ tie.

Nên dùng:

```jpql
SELECT p
FROM Product p
ORDER BY p.createdAt DESC, p.id DESC
```

Việc dùng `id DESC` cho tiêu chí phụ có thể phù hợp khi muốn các entity mới có ID lớn hơn đứng trước trong nhóm timestamp bằng nhau, nhưng **ID lớn hơn không luôn nghĩa là tạo sau** (UUID, ID cấp phân tán, sequence/transaction đồng thời). Mục đích chính của ID ở đây là **phân xử duy nhất**, không phải đại diện thời gian tuyệt đối.

Nếu `createdAt` nullable, bổ sung `CASE` để xác định vị trí NULL. Nếu dữ liệu có nhiều múi giờ, dùng kiểu và quy tắc lưu phù hợp, ví dụ `Instant`/UTC và ánh xạ DB chính xác; tránh dùng chuỗi thời gian hiển thị làm sort key.

## 11. ORDER BY với truy vấn có điều kiện WHERE

Thứ tự xử lý logic thường được hiểu là:

1. Xác định entity từ `FROM` và các `JOIN`.
2. Lọc theo `WHERE`.
3. Tính nhóm/tổng hợp nếu có.
4. Chọn các kết quả.
5. Áp dụng `ORDER BY` trên kết quả.
6. Áp dụng giới hạn/offset ở tầng API để phân trang.

Ví dụ:

```java
List<Product> products = em.createQuery(
        """
        SELECT p
        FROM Product p
        WHERE p.category = :category
          AND p.price BETWEEN :minPrice AND :maxPrice
        ORDER BY p.price DESC, p.id ASC
        """,
        Product.class
    )
    .setParameter("category", "stationery")
    .setParameter("minPrice", new BigDecimal("10000.00"))
    .setParameter("maxPrice", new BigDecimal("30000.00"))
    .getResultList();
```

Tiêu chí sort ở đây được áp dụng **sau khi lọc** những sản phẩm trong khoảng giá. Nếu có nhiều sản phẩm giá cao nhất bằng nhau, ID phân xử.

### Không “sort trước rồi WHERE sau” bằng cách thay vị trí clause

`ORDER BY` được đặt cuối truy vấn JPQL thông thường, sau `WHERE`/`GROUP BY`/`HAVING` nếu có. Không đặt `ORDER BY` giữa `FROM` và `WHERE` rồi kỳ vọng cú pháp đúng.

### ORDER BY có thể dùng biểu thức tính toán

Ví dụ ưu tiên sản phẩm có tên ngắn trước:

```jpql
SELECT p
FROM Product p
ORDER BY LENGTH(p.name) ASC, p.name ASC, p.id ASC
```

Tuy vậy, khi dùng biểu thức trong `ORDER BY`, khả năng portable và quy tắc sử dụng biểu thức cần phù hợp phiên bản JPQL/provider. Với yêu cầu tối ưu index, việc sắp theo hàm có thể tốn thêm CPU và memory ở DB.

## 12. ORDER BY trên giá trị tổng hợp và GROUP BY

Không phải truy vấn nào cũng trả về entity. Ví dụ muốn hiển thị các category có nhiều sản phẩm nhất:

```jpql
SELECT p.category, COUNT(p)
FROM Product p
GROUP BY p.category
ORDER BY COUNT(p) DESC, p.category ASC
```

Giải thích:

- `GROUP BY p.category` tạo nhóm theo category.
- `COUNT(p)` tính số sản phẩm trong mỗi nhóm.
- `ORDER BY COUNT(p) DESC` đặt nhóm đông sản phẩm trước.
- Nếu nhiều category có cùng count, `p.category ASC` phân xử.

Trong Java:

```java
List<Object[]> rows = em.createQuery(
        """
        SELECT p.category, COUNT(p)
        FROM Product p
        GROUP BY p.category
        ORDER BY COUNT(p) DESC, p.category ASC
        """,
        Object[].class
    )
    .getResultList();

for (Object[] row : rows) {
    String category = (String) row[0];
    Long count = (Long) row[1];
    System.out.println(category + " = " + count);
}
```

Chú ý: ở truy vấn tổng hợp, `p.id` không thể tùy ý đưa vào `ORDER BY` trong mọi DB nếu nó không thuộc nhóm và không được tính tổng hợp. **Tie-breaker cuối phải phù hợp mức dữ liệu của kết quả**: ở đây một hàng đại diện cho **một category**, nên tên category là khóa phân xử hợp lý khi các category được nhóm theo cách phân biệt rõ ràng.

### Alias trong SELECT và ORDER BY

JPQL có thể dùng **result variable** cho phần tử select:

```jpql
SELECT p.category AS categoryName, COUNT(p) AS productCount
FROM Product p
GROUP BY p.category
ORDER BY productCount DESC, categoryName ASC
```

Việc đặt alias giúp đọc truy vấn dễ hơn khi biểu thức phức tạp. Với yêu cầu portable, có thể lặp lại biểu thức như ví dụ đầu nếu provider/version xử lý alias khác mong đợi.

### HAVING khác ORDER BY

`HAVING` lọc các nhóm sau `GROUP BY`, còn `ORDER BY` xác định thứ tự:

```jpql
SELECT p.category, COUNT(p)
FROM Product p
GROUP BY p.category
HAVING COUNT(p) >= :minimum
ORDER BY COUNT(p) DESC, p.category ASC
```

Kết quả chỉ chứa category có đủ số lượng rồi mới được sắp. `ORDER BY` không dùng để loại bỏ các nhóm không đạt điều kiện.

## 13. JOIN và nguy cơ trùng kết quả khi sắp xếp

Nếu có quan hệ:

```java
@Entity
public class Order {
    @Id
    private Long id;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
```

thì query:

```jpql
SELECT o
FROM Order o
JOIN o.lines l
ORDER BY o.id ASC
```

về mặt join tạo ra các hàng ứng với cặp Order–OrderLine. Một Order có nhiều dòng có thể xuất hiện nhiều lần ở tầng kết quả SQL; cách provider xử lý entity result và `DISTINCT` cần được hiểu theo semantics JPQL.

Nếu cần **mỗi Order một lần**, có thể xét:

```jpql
SELECT DISTINCT o
FROM Order o
JOIN o.lines l
ORDER BY o.id ASC
```

Nhưng `DISTINCT` với ORDER BY biểu thức của entity liên quan có thể gặp giới hạn SQL, và sắp theo giá trị `l.price` không còn ý nghĩa duy nhất khi một Order có nhiều dòng giá khác nhau.

Hãy xác định muốn sắp **đơn hàng theo tiêu chí gì**:

- Theo `o.createdAt` → dùng field của Order.
- Theo tổng tiền → có thể dùng aggregate `SUM(l.quantity * l.price)` với `GROUP BY` tương ứng, hoặc cột tổng tiền đã được lưu đáng tin.
- Theo giá dòng cao nhất → dùng `MAX(l.price)`.
- Theo giá một dòng bất kỳ → yêu cầu mơ hồ; phải định nghĩa quy tắc cụ thể.

### Không phân trang bừa trên collection fetch join

Ví dụ:

```jpql
SELECT o
FROM Order o
LEFT JOIN FETCH o.lines
ORDER BY o.createdAt DESC, o.id DESC
```

Kết hợp `setMaxResults(20)` với fetch join collection có thể gây số hàng join lớn và làm provider phải phân trang trong bộ nhớ hoặc báo lỗi/cảnh báo. Một Order có nhiều OrderLine sinh nhiều hàng SQL; 20 hàng SQL không đồng nghĩa 20 Order với collection đầy đủ.

Một hướng thiết kế:

1. Query trang **ID Order** theo sort ổn định.
2. Query chi tiết những Order thuộc trang, dùng fetch phù hợp.
3. Giữ lại thứ tự trang theo danh sách ID nếu kết quả của query chi tiết không tự có cùng thứ tự.

Đây là vấn đề phân trang quan hệ, không chỉ của `ORDER BY`; điều cần nhớ là **tie-breaker không giải quyết hiệu ứng nhân hàng từ collection join**.

## 14. @OrderBy trên collection khác ORDER BY của JPQL

Một entity có thể khai báo:

```java
@OneToMany(mappedBy = "order")
@OrderBy("createdAt DESC, id DESC")
private List<OrderLine> lines = new ArrayList<>();
```

`@OrderBy` định nghĩa thứ tự **các phần tử của association** khi provider tải collection đó. Trong ví dụ, mỗi OrderLine được sắp theo `createdAt` giảm dần, rồi ID giảm dần.

Khác biệt:

| Cơ chế | Phạm vi áp dụng | Ghi chú |
|---|---|---|
| `ORDER BY` trong JPQL | Thứ tự kết quả của **truy vấn cụ thể** | Thích hợp cho danh sách/filter/page |
| `@OrderBy` trên association | Thứ tự các **phần tử trong collection** khi được tải | Không tự đổi thứ tự mọi query Product/Order khác |
| `@OrderColumn` | Lưu **vị trí của phần tử** trong quan hệ bằng cột thứ tự | Hữu ích khi người dùng kéo-thả thay đổi vị trí; có chi phí ghi |
| `List` Java không kèm ordering mapping/query | Chứa phần tử theo thứ tự runtime hiện tại | Không bảo đảm thứ tự từ DB sau reload |

`@OrderBy("createdAt DESC, id DESC")` giả định `OrderLine` có thuộc tính `createdAt` và `id`; snippet này chỉ minh họa mapping, cần định nghĩa đầy đủ entity để chạy.

**`@OrderBy` không giống `@OrderColumn`.** Một cái sắp theo dữ liệu hiện có, cái còn lại biểu diễn vị trí phần tử như một phần trạng thái persistent.

## 15. Truy vấn động: không truyền tên field bằng parameter

Giả sử API cho chọn sort field và direction:

```text
GET /products?sort=price&direction=desc
```

Không thể mong cách dưới đây hoạt động như truyền tên cột:

```jpql
SELECT p
FROM Product p
ORDER BY :sortField
```

Parameter `:sortField` đại diện **giá trị dữ liệu**, không phải một tên thuộc tính JPQL. DB không dùng một string bind `"price"` để tự thay thế thành `p.price`.

### Cách an toàn: whitelist tên field

Một implementation đơn giản:

```java
public List<Product> listSorted(
        EntityManager em, String requestedField, boolean descending) {

    String property = switch (requestedField) {
        case "price" -> "p.price";
        case "name" -> "p.name";
        case "createdAt" -> "p.createdAt";
        default -> throw new IllegalArgumentException(
            "Unsupported sort field");
    };

    String direction = descending ? "DESC" : "ASC";

    String jpql =
        "SELECT p FROM Product p ORDER BY "
        + property + " " + direction
        + ", p.id ASC";

    return em.createQuery(jpql, Product.class)
             .setMaxResults(100)
             .getResultList();
}
```

Đoạn code **không ghép trực tiếp text bất kỳ của người dùng** vào JPQL. Nó ánh xạ đầu vào sang danh sách field cố định đã được kiểm soát. Hướng sắp cũng được chọn bằng boolean thay vì nhận nguyên chuỗi tùy ý.

Cần thêm kiểm tra page size tối đa, sort field không gây query quá đắt, quyền truy cập và tên thuộc tính hợp lệ. Nếu ứng dụng cho phép sort nhiều field, whitelist và giới hạn số tiêu chí.

### Vì sao không string-concatenate đầu vào tự do?

`"ORDER BY p." + userInput` có thể dẫn đến JPQL injection hoặc truy vấn bị biến dạng/lỗi. Named parameter chỉ bảo vệ **giá trị**, không tự bảo vệ các cấu phần cấu trúc của query như field, hướng sort hoặc function name.

## 16. Criteria API: tạo ORDER BY có kiểu cấu trúc

Với nhiều sort option hoặc bộ lọc động, Criteria API tránh phải ghép thủ công các đoạn query:

```java
public List<Product> listByPrice(
        EntityManager em,
        String category,
        int limit) {

    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Product> cq = cb.createQuery(Product.class);
    Root<Product> root = cq.from(Product.class);

    cq.select(root)
      .where(cb.equal(root.get("category"), category))
      .orderBy(
          cb.desc(root.get("price")),
          cb.asc(root.get("id"))
      );

    return em.createQuery(cq)
             .setMaxResults(limit)
             .getResultList();
}
```

Các import:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Root;
import java.util.List;
```

Trong Criteria API:

- `cb.asc(expression)` biểu diễn tăng dần.
- `cb.desc(expression)` biểu diễn giảm dần.
- `cq.orderBy(...)` nhận các tiêu chí theo đúng thứ tự ưu tiên.
- `root.get("price")` là đường dẫn thuộc tính entity.

Để giảm lỗi do tên field string, dự án có thể dùng **static metamodel** (`Product_.price`) nếu đã cấu hình annotation processing tạo metamodel.

### NULLS LAST bằng CASE trong Criteria

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Product> cq = cb.createQuery(Product.class);
Root<Product> p = cq.from(Product.class);

Expression<Integer> nullRank = cb.<Integer>selectCase()
    .when(cb.isNull(p.get("rating")), 1)
    .otherwise(0);

cq.select(p).orderBy(
    cb.asc(nullRank),
    cb.desc(p.get("rating")),
    cb.asc(p.get("id"))
);

List<Product> products =
    em.createQuery(cq).getResultList();
```

Với Criteria API, cũng cần kiểm tra provider/SQL để đảm bảo cách biểu diễn `CASE` được hỗ trợ và quy tắc NULL như dự kiến. Ưu điểm là thứ tự tiêu chí hiện rõ trong object query.

## 17. Spring Data JPA: Sort và PageRequest

Trong Spring Data JPA, truy vấn theo repository thường nhận một `Sort` hoặc `Pageable`.

Ví dụ:

```java
Sort sort = Sort.by(
    Sort.Order.desc("price"),
    Sort.Order.asc("id")
);

List<Product> products = repository.findAll(sort);
```

Phân trang:

```java
Pageable pageable = PageRequest.of(
    pageIndex,
    pageSize,
    Sort.by(
        Sort.Order.asc("price"),
        Sort.Order.asc("id")
    )
);

Page<Product> page = repository.findAll(pageable);
```

Đoạn này giả định có repository:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Cần import các class Spring Data: `org.springframework.data.domain.Sort`, `Pageable`, `PageRequest`, `Page` và `JpaRepository`.

### Vì sao luôn thêm ID ở cuối Sort?

Vì Spring Data `PageRequest` không tự giải quyết mọi tie nghiệp vụ. Nếu sort field không unique, phần tử ở ranh giới page có thể không ổn định. Bổ sung `id` giúp phân xử.

### Chú ý khi sử dụng Sort.Order.nullsLast()

Spring Data có hỗ trợ API mô tả ý định xử lý NULL, ví dụ:

```java
Sort.Order.desc("rating").nullsLast();
```

Nhưng null handling là hint phụ thuộc store/provider/dialect. Với JPA backend, không mặc định mọi DB và phiên bản provider đều thể hiện y hệt yêu cầu. Khi thứ tự NULL là quy tắc bắt buộc, hãy kiểm tra SQL hoặc dùng query/Criteria diễn đạt `CASE` rõ ràng.

### Pageable có đồng nghĩa kết quả ổn định xuyên nhiều request?

Không. `Pageable` xác định offset/limit/sort của mỗi query. Nếu dữ liệu thay đổi trong lúc client lần lượt tải các page, vẫn có thể có dịch chuyển. Với feed hoặc xử lý hàng loạt lớn, cân nhắc cursor/keyset pagination.

## 18. Ví dụ Java SE hoàn chỉnh với H2 và Hibernate

Ví dụ dưới đây tạo dữ liệu chứa **nhiều sản phẩm có cùng giá**, **tên trùng** và **rating NULL** để nhìn thấy tác dụng của tie-breaker.

### 18.1. Cấu trúc dự án

```text
jpql-ordering-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/
        │   ├── Product.java
        │   └── Main.java
        └── resources/META-INF/
            └── persistence.xml
```

### 18.2. pom.xml

Sử dụng Java 17, Jakarta Persistence 3.1, Hibernate ORM 6.x và H2. Các version dưới đây là bộ ví dụ, không khẳng định là phiên bản phát hành mới nhất:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jpql-ordering-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>jakarta.persistence</groupId>
            <artifactId>jakarta.persistence-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.hibernate.orm</groupId>
            <artifactId>hibernate-core</artifactId>
            <version>6.6.4.Final</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 18.3. Product entity

Tệp `src/main/java/demo/Product.java`:

```java
package demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Objects;

@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false, length = 150)
    private String name;

    @Column(name = "category", nullable = false, length = 60)
    private String category;

    @Column(name = "price", nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Column(name = "rating")
    private Integer rating;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected Product() {
        // Constructor cho JPA.
    }

    public Product(
            String name,
            String category,
            BigDecimal price,
            Integer rating,
            LocalDateTime createdAt) {
        this.name = Objects.requireNonNull(name, "name");
        this.category = Objects.requireNonNull(category, "category");
        this.price = Objects.requireNonNull(price, "price");
        this.rating = rating;
        this.createdAt = Objects.requireNonNull(createdAt, "createdAt");
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public String getCategory() {
        return category;
    }

    public Integer getRating() {
        return rating;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
```

Trong ví dụ:

- `price` là `BigDecimal`, phù hợp việc lưu tiền chính xác đến hai chữ số thập phân.
- `rating` là `Integer` nullable để thể hiện sản phẩm chưa được đánh giá.
- `createdAt` là `LocalDateTime` có ý nghĩa thời điểm trong dữ liệu ví dụ; hệ thống thật cần thống nhất múi giờ và kiểu SQL.
- `id` được database sinh bằng IDENTITY, cung cấp tiêu chí phân xử cuối cùng.

### 18.4. persistence.xml

Tệp `src/main/resources/META-INF/persistence.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="
                 https://jakarta.ee/xml/ns/persistence
                 https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
             version="3.1">

    <persistence-unit name="productPU" transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>demo.Product</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:orderingdb;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password"
                      value=""/>
            <property name="jakarta.persistence.schema-generation.database.action"
                      value="drop-and-create"/>
        </properties>
    </persistence-unit>
</persistence>
```

`drop-and-create` chỉ dùng cho demo/test vì **có thể xóa dữ liệu**. Ứng dụng thực tế nên dùng migration và ràng buộc schema do nhóm phát triển quản lý.

### 18.5. Main: seed dữ liệu, ORDER BY, CASE và phân trang

Tệp `src/main/java/demo/Main.java`:

```java
package demo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

public class Main {

    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("productPU");

        try {
            seed(emf);
            showPriceAscending(emf);
            showNullsLast(emf);
            showFirstTwoPages(emf);
        } finally {
            emf.close();
        }
    }

    private static void seed(EntityManagerFactory emf) {
        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                LocalDateTime time =
                    LocalDateTime.of(2026, 11, 1, 10, 0);

                em.persist(new Product(
                    "Bút bi", "stationery",
                    new BigDecimal("12000.00"), null, time));

                em.persist(new Product(
                    "Vở kẻ ngang", "stationery",
                    new BigDecimal("20000.00"), 5, time));

                em.persist(new Product(
                    "Thước kẻ", "stationery",
                    new BigDecimal("12000.00"), 4, time));

                em.persist(new Product(
                    "Sổ tay", "stationery",
                    new BigDecimal("35000.00"), 5, time));

                em.persist(new Product(
                    "Bút bi", "stationery",
                    new BigDecimal("12000.00"), null, time));

                em.persist(new Product(
                    "Bút máy", "stationery",
                    new BigDecimal("12000.00"), null, time));

                tx.commit();
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw ex;
            }
        } finally {
            em.close();
        }
    }

    private static void showPriceAscending(
            EntityManagerFactory emf) {
        EntityManager em = emf.createEntityManager();

        try {
            System.out.println("Price ASC, ID ASC:");

            List<Product> products = em.createQuery(
                    """
                    SELECT p FROM Product p
                    ORDER BY p.price ASC, p.id ASC
                    """,
                    Product.class
                )
                .getResultList();

            for (Product p : products) {
                print(p);
            }
        } finally {
            em.close();
        }
    }

    private static void showNullsLast(
            EntityManagerFactory emf) {
        EntityManager em = emf.createEntityManager();

        try {
            System.out.println("Rating DESC, NULLS LAST, ID ASC:");

            List<Product> products = em.createQuery(
                    """
                    SELECT p FROM Product p
                    ORDER BY
                        CASE WHEN p.rating IS NULL THEN 1 ELSE 0 END ASC,
                        p.rating DESC,
                        p.id ASC
                    """,
                    Product.class
                )
                .getResultList();

            for (Product p : products) {
                print(p);
            }
        } finally {
            em.close();
        }
    }

    private static void showFirstTwoPages(
            EntityManagerFactory emf) {
        EntityManager em = emf.createEntityManager();

        try {
            for (int index = 0; index < 2; index++) {
                List<Product> products = em.createQuery(
                        """
                        SELECT p FROM Product p
                        ORDER BY p.price ASC, p.id ASC
                        """,
                        Product.class
                    )
                    .setFirstResult(index * 3)
                    .setMaxResults(3)
                    .getResultList();

                System.out.println("Page " + index + ":");
                for (Product p : products) {
                    print(p);
                }
            }
        } finally {
            em.close();
        }
    }

    private static void print(Product product) {
        System.out.println(
            product.getId() + " | "
            + product.getName() + " | "
            + product.getPrice() + " | rating="
            + product.getRating()
        );
    }
}
```

Chạy:

```bash
mvn compile exec:java
```

Trong một lượt tạo dữ liệu mới, sáu `Product` có bốn mức giá 12.000 trùng nhau và ba rating NULL. Khi chạy:

- Query thứ nhất hiển thị **giá tăng dần**, ID phân xử các sản phẩm cùng giá.
- Query thứ hai hiển thị **rating cao trước**, rating NULL xuống cuối, ID phân xử trong nhóm rating bằng nhau.
- Hai trang lấy 3 sản phẩm mỗi trang theo cùng thứ tự price + ID.

Chương trình in các ID thực tế do database cấp; không nên dựa vào một giá trị ID cố định khi thay database hoặc chiến lược sinh ID. Trật tự theo `id` vẫn rõ ràng đối với những giá trị đã được cấp.

## 19. Đọc kết quả khi có ties

Với truy vấn:

```jpql
ORDER BY p.price ASC, p.id ASC
```

giả sử ID theo thứ tự insert ví dụ là 1 đến 6, kết quả logic sẽ là:

```text
1 | Bút bi       | 12000.00
3 | Thước kẻ     | 12000.00
5 | Bút bi       | 12000.00
6 | Bút máy      | 12000.00
2 | Vở kẻ ngang  | 20000.00
4 | Sổ tay       | 35000.00
```

Trong nhóm giá 12.000, sản phẩm có cùng tên "Bút bi" vẫn được phân biệt bằng ID.

Với:

```jpql
ORDER BY
  CASE WHEN p.rating IS NULL THEN 1 ELSE 0 END ASC,
  p.rating DESC,
  p.id ASC
```

kết quả logic sẽ có dạng:

```text
2 | Vở kẻ ngang | rating=5
4 | Sổ tay      | rating=5
3 | Thước kẻ    | rating=4
1 | Bút bi      | rating=NULL
5 | Bút bi      | rating=NULL
6 | Bút máy     | rating=NULL
```

Một chi tiết dễ quên: nếu query chỉ viết `ORDER BY p.rating DESC`, việc ba rating NULL xuất hiện trước hay sau **không phải quy tắc portable** để suy luận ở mọi DB.

## 20. Vấn đề hiệu năng của ORDER BY

Một thứ tự đúng vẫn cần được thiết kế hiệu quả, nhất là khi dữ liệu rất lớn.

### 20.1. Sắp trong DB thay vì lấy hết rồi sort Java

Cách kém hiệu quả khi chỉ cần 20 sản phẩm:

```java
List<Product> all = em.createQuery(
    "SELECT p FROM Product p", Product.class
).getResultList();

// Không nên tải hàng trăm nghìn entity
// chỉ để sort và lấy 20 phần tử ở Java.
all.sort(Comparator.comparing(Product::getPrice)
                   .thenComparing(Product::getId));

List<Product> first20 = all.subList(
    0, Math.min(20, all.size()));
```

Hướng phù hợp:

```java
List<Product> first20 = em.createQuery(
        """
        SELECT p FROM Product p
        ORDER BY p.price ASC, p.id ASC
        """,
        Product.class
    )
    .setMaxResults(20)
    .getResultList();
```

Truy vấn ở DB cho phép DB áp dụng limit, index và chiến lược sort thích hợp, giảm lượng dữ liệu chuyển sang JVM.

### 20.2. Composite index tương ứng với bộ lọc và sort

Nếu truy vấn thường xuyên:

```sql
SELECT *
FROM product
WHERE category = ?
ORDER BY price ASC, id ASC
LIMIT 20;
```

có thể cân nhắc index khái niệm:

```sql
CREATE INDEX idx_product_category_price_id
ON product(category, price, id);
```

Index này có thể phục vụ lọc theo `category` và thứ tự `price, id` trong một số DB/query plan. Nhưng index **không tự bảo đảm** optimizer luôn sử dụng nó, và một số DB có cách xử lý ASC/DESC, covering index và NULL khác nhau.

Khi có nhiều sort mode:

- `price ASC, id ASC`
- `created_at DESC, id DESC`
- `LOWER(name) ASC, id ASC`

không nên tạo index cho mọi tổ hợp chỉ từ lý thuyết. Đo tần suất truy vấn, số hàng, query plan và chi phí INSERT/UPDATE/DELETE của từng index.

### 20.3. ORDER BY biểu thức có thể đắt

`LOWER(name)`, `CASE WHEN rating IS NULL` hoặc biểu thức tổng hợp có thể cần tính toán/sort thay vì tận dụng trực tiếp index đơn giản. Một số DB hỗ trợ expression/functional index hoặc generated sort key; tính năng này thường đặc thù DB.

Ưu tiên biểu đạt **đúng ý nghĩa sắp xếp**, rồi tối ưu dựa trên `EXPLAIN`, SQL log và số liệu tải thực tế.

## 21. Những lỗi thường gặp

### Lỗi 1: Không có ORDER BY nhưng mong kết quả theo ID

```jpql
SELECT p FROM Product p
```

Không có thứ tự cam kết. Viết `ORDER BY p.id ASC` nếu cần theo ID.

### Lỗi 2: ORDER BY chỉ một field có nhiều giá trị trùng

```jpql
ORDER BY p.price ASC
```

Giá trùng khiến thứ tự giữa các hàng tie chưa xác định. Thêm `p.id ASC` hoặc khóa phân xử duy nhất phù hợp.

### Lỗi 3: Cho rằng ASC hay DESC quyết định vị trí NULL trên mọi DB

```jpql
ORDER BY p.rating DESC
```

NULL ordering khác nhau tùy DB/provider. Dùng biểu thức `CASE` hoặc tính năng hỗ trợ đã được xác nhận khi cần quy tắc explicit.

### Lỗi 4: Ghép raw sort field của người dùng vào JPQL

```java
String jpql =
    "SELECT p FROM Product p ORDER BY p." + userProvidedField;
```

Không an toàn và khó kiểm soát. Whitelist tên field/hướng sort hoặc dùng Criteria API.

### Lỗi 5: Truyền tên field làm bind parameter

`ORDER BY :sortField` không có nghĩa `ORDER BY p.price` nếu bind `"price"`. Parameter đại diện một giá trị, không phải cú pháp JPQL.

### Lỗi 6: Sắp theo chuỗi rồi giả định collation tiếng Việt

`ORDER BY p.name` dùng quy tắc so sánh của DB. Cần xác định collation đúng để áp dụng thứ tự chữ cái tiếng Việt hoặc các locale khác.

### Lỗi 7: Tie-breaker lại là field không duy nhất

`ORDER BY p.createdAt DESC, p.rating DESC` vẫn có thể để nhiều hàng bằng nhau. Thêm một khóa unique cuối cùng nếu yêu cầu deterministic ordering.

### Lỗi 8: Phân trang join fetch collection trực tiếp

Một entity cha có nhiều con sinh nhiều hàng join. `setMaxResults` với collection fetch join không phải giải pháp phân trang cha đơn giản và portable.

### Lỗi 9: Dùng OFFSET lớn trên danh sách thay đổi nhanh

Dù có tie-breaker, chèn/xóa trước ranh giới offset có thể làm trùng/bỏ hàng giữa các request. Dùng cursor/keyset hoặc snapshot khi phù hợp.

### Lỗi 10: Nhầm @OrderBy và @OrderColumn

`@OrderBy` sắp phần tử theo thuộc tính; `@OrderColumn` lưu vị trí. Hai annotation có mục đích khác nhau.

### Lỗi 11: Sắp theo alias/biểu thức không phù hợp GROUP BY

Trong query tổng hợp, không phải field entity nào cũng có thể xuất hiện tùy ý ở `ORDER BY`. Chọn biểu thức hợp lệ với mức nhóm và kết quả.

### Lỗi 12: Không xét thứ tự và NULL trong keyset cursor

Cursor chỉ gồm `lastPrice` sẽ bỏ sót những sản phẩm cùng giá chưa xuất hiện; cursor có NULL cần chính sách so sánh riêng. Dùng đủ tiêu chí sắp và điều kiện sau cursor tương ứng.

## 22. Bài tập thực hành

### Bài 1 — Sắp tăng dần và giảm dần

Từ dữ liệu Product mẫu, viết hai JPQL:

1. `ORDER BY p.price ASC, p.id ASC`.
2. `ORDER BY p.price DESC, p.id ASC`.

Ghi lại khác biệt giữa nhóm giá cao/thấp và cách ID phân xử.

### Bài 2 — Hai cấp sort chưa đủ

Viết:

```jpql
ORDER BY p.price ASC, p.name ASC
```

Nhận xét hai hàng cùng tên "Bút bi", cùng giá 12.000 vẫn tie. Bổ sung `p.id ASC` và giải thích kết quả.

### Bài 3 — NULL ở cuối

Viết JPQL sort rating giảm dần, `NULL` xuống cuối bằng `CASE WHEN ... IS NULL`, ID tăng dần. Giải thích giá trị phân loại 0/1 và tại sao phải thêm ID.

### Bài 4 — NULL ở đầu

Viết truy vấn đặt các sản phẩm chưa có rating lên đầu, sau đó sắp rating giảm dần cho phần còn lại. Thêm `createdAt DESC, id DESC` để phân xử nếu muốn mới nhất trước.

### Bài 5 — Pagination qua các giá bằng nhau

Dùng `pageSize = 3`, thử query chỉ sort theo price rồi so với price + id. Ghi lại vì sao query đầu không có cam kết về vị trí nhóm giá 12.000. Không giả định phải quan sát được sự đảo thứ tự ở mọi lần chạy.

### Bài 6 — Keyset page

Viết query lấy trang tiếp theo sau `lastPrice = 12000`, `lastId = 15` theo `price ASC, id ASC`. Dự đoán hàng nào còn trong nhóm 12.000 và hàng nào thuộc nhóm giá lớn hơn.

### Bài 7 — Sắp theo tên không phân biệt hoa/thường

Thêm các tên `"Notebook"`, `"notebook"` và `"NOTEBOOK"`. So sánh `ORDER BY p.name` với `ORDER BY LOWER(p.name), p.id`. Quan sát ảnh hưởng collation.

### Bài 8 — Truy vấn aggregate

Thêm nhiều category có số lượng sản phẩm bằng nhau. Viết `GROUP BY category` rồi sort `COUNT(p) DESC, p.category ASC`. Giải thích vì sao category là tie-breaker thay vì Product ID.

### Bài 9 — Dynamic sorting có whitelist

Xây API nhận sort field thuộc `price`, `name` hoặc `createdAt`. Từ chối field lạ. Luôn thêm `id ASC` cuối truy vấn và giới hạn page size.

### Bài 10 — Criteria API

Viết CriteriaQuery sort `rating NULLS LAST`, `rating DESC`, `id ASC` bằng `CASE`. So sánh tính rõ ràng của query với JPQL string.

### Bài 11 — Spring Data PageRequest

Tạo repository `JpaRepository<Product, Long>` và truy vấn trang 0, 1 theo `Sort.by(asc("price"), asc("id"))`. Phân tích khi có một Product được chèn ở đầu danh sách giữa hai lần đọc.

### Bài 12 — Index và execution plan

Trên DB test có nhiều Product, thử truy vấn theo category, sắp price/id, giới hạn 20 hàng. Dùng `EXPLAIN` và đánh giá index `(category, price, id)`. Quan sát chi phí đọc/ghi trước khi quyết định dùng index.

### Bài 13 — @OrderBy trên collection

Tạo `Order`–`OrderLine`. Khai báo `@OrderBy("createdAt DESC, id DESC")` và tải collection sau khi đóng/mở EntityManager. Giải thích vì sao thứ tự list sau reload đã được quy định dù không có `@OrderColumn`.

## 23. Câu hỏi tự kiểm tra

1. **Nếu JPQL không có ORDER BY, kết quả có theo khóa chính không?** Không có bảo đảm, dù thực nghiệm có thể trông như vậy.
2. **ASC và DESC khác nhau thế nào?** ASC tăng dần, DESC giảm dần.
3. **Vì sao ORDER BY price ASC chưa đủ để phân trang ổn định?** Nhiều hàng có thể cùng price và DB không bắt buộc thứ tự giữa chúng.
4. **Tie-breaker cuối nên là gì?** Một khóa ổn định và duy nhất, thường là ID hoặc đủ các thành phần khóa ghép.
5. **ORDER BY price ASC, id ASC ưu tiên cột nào trước?** Price trước; ID chỉ phân xử khi price bằng nhau.
6. **NULL mặc định đứng đầu hay cuối ở mọi DB?** Không có một quy tắc portable đơn giản cho mọi DB/dialect.
7. **Làm sao yêu cầu NULL cuối rõ ràng?** Dùng CASE phân loại NULL trước các biểu thức sort thông thường hoặc cú pháp đã được provider hỗ trợ.
8. **COALESCE luôn tương đương CASE phân loại NULL không?** Không; fallback có thể trùng giá trị thực và đổi ý nghĩa nhóm.
9. **LOWER(name) có bảo đảm thứ tự chữ cái tiếng Việt không?** Không; collation của DB vẫn quan trọng.
10. **Dùng parameter :field để truyền tên cột ORDER BY được không?** Không. Bind parameter không thay thế cú pháp tên thuộc tính.
11. **Vì sao id ASC giúp tie-break nhưng không hoàn toàn ngăn page lặp khi dữ liệu đổi?** Vì offset chịu ảnh hưởng chèn/xóa giữa các lần đọc.
12. **Keyset cursor với price ASC, id ASC cần điều kiện gì?** Price lớn hơn lastPrice hoặc price bằng và ID lớn hơn lastId.
13. **Query tổng hợp COUNT có thể sort theo COUNT không?** Có, với biểu thức/alias tổng hợp và tiêu chí tie-breaker phù hợp.
14. **@OrderBy và ORDER BY JPQL giống nhau về phạm vi không?** Không; một cái áp vào collection mapping, một cái áp vào query cụ thể.
15. **@OrderColumn dùng để làm gì?** Lưu vị trí phần tử như trạng thái của quan hệ.
16. **ORDER BY LOWER(name) có thể làm query đắt hơn không?** Có, tùy DB/index/plan.
17. **Có nên gọi findAll rồi sort Java nếu chỉ cần 20 kết quả?** Thường không; nên để DB sort và limit.
18. **Nếu query JOIN collection tạo nhiều hàng, thêm tie-breaker ID có xóa trùng entity không?** Không. Cần thiết kế DISTINCT/grouping/fetch/pagination đúng.
19. **Tiêu chí sort cuối có cần giữ nguyên khi đổi ASC/DESC của tiêu chí chính không?** Không bắt buộc cùng hướng; chỉ cần quy tắc tổng thể rõ ràng và ổn định.
20. **Một thứ tự quyết định có tự bảo đảm snapshot xuyên nhiều request không?** Không; snapshot/concurrency là bài toán riêng.

**Ghi nhớ:** `ORDER BY` xác định thứ tự kết quả của JPQL. Khi nhiều hàng **có cùng giá trị sắp xếp**, hãy bổ sung tiêu chí phụ và thường là **khóa chính duy nhất ở cuối** để phân xử. Nếu có `NULL`, chữ hoa/thường, dữ liệu ngày giờ hoặc truy vấn tổng hợp, cần định nghĩa quy tắc tương ứng thay vì dựa vào hành vi ngầm của database. Với phân trang, **sort xác định** là điều kiện cần, còn thay đổi dữ liệu giữa các trang cần giải pháp bổ sung như **keyset cursor** hoặc snapshot phù hợp.
