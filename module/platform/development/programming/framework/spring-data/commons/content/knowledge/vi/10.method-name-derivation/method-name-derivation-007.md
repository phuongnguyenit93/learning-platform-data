# So sánh, khoảng giá trị, chuỗi, tập hợp và null theo store

## Mục tiêu bài học

Derived query giúp biểu đạt điều kiện bằng tên phương thức, nhưng keyword được nhận diện ở tầng Spring Data Commons không có nghĩa mọi store đều hỗ trợ hoặc thực thi với ngữ nghĩa giống nhau. Sự khác biệt đặc biệt quan trọng với biên khoảng giá trị, so khớp chuỗi, thuộc tính dạng collection và dữ liệu thiếu.

Sau bài học, bạn có thể:

- Chọn keyword so sánh và cung cấp đúng số lượng tham số.
- Mô tả rõ khoảng đóng, khoảng mở và khoảng nửa mở thay vì dựa vào trực giác về tên `Between`.
- Phân biệt so khớp chuỗi, kiểm tra thuộc tập giá trị và kiểm tra phần tử của collection.
- Phân biệt `null`, chuỗi rỗng, collection rỗng và trường không tồn tại.
- Xác định những ngữ nghĩa phải kiểm tra lại khi chuyển query method giữa các store.

## 1. Bắt đầu từ domain và ý định nghiệp vụ

Dùng mô hình sản phẩm để minh họa:

```text
Product
├── id: Long
├── tenantId: String
├── name: String
├── price: BigDecimal
├── stock: Integer
├── status: String
├── description: String
├── tags: Set<String>
└── createdAt: Instant
```

`tenantId` giới hạn dữ liệu theo đơn vị sử dụng hệ thống. `description` có thể vắng dữ liệu; `tags` là tập nhãn. Đây là mô hình khái niệm: cách mapping entity quan hệ, document, giá trị tiền tệ và collection cần được cấu hình theo store.

Một repository có thể bắt đầu từ abstraction Commons:

```java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.repository.Repository;

interface ProductRepository extends Repository<Product, Long> {

    List<Product> findByTenantIdAndPriceLessThan(
            String tenantId, BigDecimal upperExclusive);
}
```

Interface trên chưa tự cung cấp kết nối hay một bộ máy truy vấn độc lập với store. Bạn cần module cụ thể như Spring Data JPA hoặc Spring Data MongoDB cùng mapping phù hợp.

Trước khi đặt tên phương thức, hãy viết ý định thành biểu thức:

```text
 tenantId = tenant đang được phép truy cập
 AND price < ngưỡng trên
```

Sau đó mới chọn keyword. Làm ngược lại dễ khiến một từ quen thuộc như `Between` hoặc `Containing` được dùng mà chưa xác định rõ ngữ nghĩa.

## 2. Keyword chung và phần việc của store

Commons cung cấp hạ tầng phân tích tên như `LessThan`, `Between`, `Containing`, `In` và `IsNull`. Module lưu trữ quyết định có hỗ trợ điều kiện đó không, chuyển nó thành biểu thức nào và xử lý kiểu dữ liệu ra sao.

| Tầng | Trách nhiệm |
| --- | --- |
| Tên phương thức | Biểu đạt thuộc tính, toán tử và cách kết hợp điều kiện |
| Metadata domain | Xác định kiểu thuộc tính và đường dẫn được mapping |
| Module Spring Data | Chuyển điều kiện thành truy vấn theo store |
| Provider, driver và backend | Thực hiện so sánh, xử lý dữ liệu và chọn kế hoạch thực thi |

Ví dụ, `price` trong tên phương thức hướng đến thuộc tính domain, không phải tên cột SQL được chép nguyên vào tên Java. Cùng kiểu Java `BigDecimal` còn cần mapping sang kiểu lưu trữ thích hợp để bảo toàn giá trị và phép so sánh.

Các bảng keyword trong bài mô tả những dạng thường dùng. Chỉ áp dụng sau khi xác nhận store hỗ trợ toán tử, kiểu thuộc tính và chữ ký tương ứng.

## 3. So sánh bằng, khác và thứ tự

### 3.1. So sánh bằng có thể không cần viết keyword

```java
List<Product> findByTenantIdAndStatus(
        String tenantId, String status);
```

Phần `Status` không kèm toán tử đặc biệt thường biểu đạt so sánh bằng. Các dạng `StatusIs` và `StatusEquals` cũng thuộc nhóm so sánh bằng trong cơ chế phân tích tên.

```java
List<Product> findByTenantIdAndStatusIs(
        String tenantId, String status);

List<Product> findByTenantIdAndStatusEquals(
        String tenantId, String status);
```

Với giá trị khác `null` và store hỗ trợ, ba tên này diễn đạt cùng ý định bằng trên thuộc tính `status`. Cách xử lý đối số `null` cần xem riêng, vì không thể suy rộng mọi quy tắc giữa các store hoặc giữa derived query và truy vấn khai báo.

### 3.2. Nhóm so sánh thứ tự

| Keyword | Ý định với giá trị được lưu và so sánh hợp lệ | Số giá trị điều kiện |
| --- | --- | --- |
| `LessThan` | Nhỏ hơn, `<` | 1 |
| `LessThanEqual` | Nhỏ hơn hoặc bằng, `<=` | 1 |
| `GreaterThan` | Lớn hơn, `>` | 1 |
| `GreaterThanEqual` | Lớn hơn hoặc bằng, `>=` | 1 |
| `Before` | Trước một mốc, thường dùng với thời gian | 1 |
| `After` | Sau một mốc, thường dùng với thời gian | 1 |
| `Not` hoặc `IsNot` | Khác một giá trị, theo ngữ nghĩa của store | 1 |

Ví dụ:

```java
List<Product> findByTenantIdAndPriceGreaterThanEqual(
        String tenantId, BigDecimal minimum);

List<Product> findByTenantIdAndStockLessThanEqual(
        String tenantId, Integer threshold);

List<Product> findByTenantIdAndCreatedAtAfter(
        String tenantId, Instant instant);
```

Ví dụ thời gian cần import `java.time.Instant`. Tên biến `minimum`, `threshold` hoặc `instant` giúp người đọc hiểu vai trò của đầu vào, nhưng không thay đổi toán tử đã được chọn trong tên phương thức.

### 3.3. Kiểu dữ liệu ảnh hưởng kết quả

So sánh giá tiền được lưu bằng kiểu số khác với so sánh các chuỗi như `"100"` và `"20"`. Không nên lưu dữ liệu số dưới dạng chuỗi rồi kỳ vọng keyword so sánh sẽ tự chuyển thành ngữ nghĩa tiền tệ.

Với thời gian, cần thống nhất:

- Kiểu thời gian của domain và kiểu lưu trữ thực tế.
- Múi giờ dùng để chuyển yêu cầu của người dùng thành các mốc thời gian.
- Độ chính xác mà backend giữ lại, chẳng hạn mili giây hoặc vi giây.

Nếu cắt hoặc làm tròn thời gian trong mapping, các bản ghi sát biên có thể không nằm trong khoảng bạn dự đoán chỉ từ giá trị Java ban đầu.

## 4. Khoảng giá trị: phải xác định cả hai biên

Bốn loại khoảng thường gặp:

| Ký hiệu | Điều kiện |
| --- | --- |
| `[a, b]` | `a <= x AND x <= b` |
| `(a, b)` | `a < x AND x < b` |
| `[a, b)` | `a <= x AND x < b` |
| `(a, b]` | `a < x AND x <= b` |

Hai truy vấn chỉ khác việc có lấy giá trị đúng tại biên vẫn có thể tạo ra khác biệt nghiệp vụ đáng kể.

### 4.1. Không coi `Between` là một hợp đồng giống nhau ở mọi store

Ví dụ chữ ký:

```java
List<Product> findByTenantIdAndPriceBetween(
        String tenantId, BigDecimal lower, BigDecimal upper);
```

Với dạng `Between` nhận hai giá trị, có một khác biệt tiêu biểu:

| Module | Cách diễn đạt thông thường | Ý nghĩa của hai biên |
| --- | --- | --- |
| Spring Data JPA | Điều kiện JPQL `between` | Bao gồm hai biên: `[lower, upper]` |
| Spring Data MongoDB | Điều kiện `$gt` và `$lt` cho dạng hai giá trị | Không bao gồm hai biên: `(lower, upper)` |

Đây là lý do không nên sao chép một phương thức `Between` sang store khác rồi chỉ kiểm tra rằng ứng dụng vẫn khởi tạo được. Cần có dữ liệu đúng tại `lower` và `upper` để phân biệt ngữ nghĩa.

Một số module còn hỗ trợ `org.springframework.data.domain.Range` với thông tin biên đóng hoặc mở, chẳng hạn MongoDB có cơ chế nhận khoảng cho derived query phù hợp. `Range` là abstraction của Commons, nhưng chữ ký nhận `Range` không mặc nhiên được mọi store hỗ trợ. Không thay hai đối số của JPA bằng một `Range` chỉ vì kiểu đó có sẵn trong dependency.

### 4.2. Dùng toán tử tường minh cho khoảng nửa mở

Để lấy sản phẩm trong khoảng `[minimum, maximum)`, có thể biểu đạt rõ:

```java
List<Product> findByTenantIdAndPriceGreaterThanEqualAndPriceLessThan(
        String tenantId,
        BigDecimal minimumInclusive,
        BigDecimal maximumExclusive);
```

Ý định là:

```text
 tenantId = ?
 AND price >= minimumInclusive
 AND price < maximumExclusive
```

Phương thức này vẫn cần store hỗ trợ các toán tử liên quan, nhưng tên đã thể hiện rõ yêu cầu về biên.

### 4.3. Khoảng thời gian nên có hợp đồng rõ ràng

Để lấy các sản phẩm được tạo trong một ngày nghiệp vụ, khoảng nửa mở thường dễ ghép nối:

```java
List<Product> findByTenantIdAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
        String tenantId,
        Instant startInclusive,
        Instant endExclusive);
```

Nếu ngày được xác định theo một múi giờ nghiệp vụ, hãy chuyển thời điểm bắt đầu ngày và bắt đầu ngày kế tiếp trong múi giờ đó thành hai `Instant`. Không cần đoán một giá trị “cuối ngày” có đủ chữ số phần giây cho mọi backend.

Hai ngày liền nhau dùng `[d1, d2)` và `[d2, d3)` không lấy trùng bản ghi đúng tại `d2`. Các biên phải được tính từ yêu cầu nghiệp vụ, không phải được auditing hoặc tên thuộc tính `createdAt` tự suy ra.

Cần xác thực `startInclusive < endExclusive` nếu đó là hợp đồng bạn muốn. Repository không tự đổi chỗ hai mốc truyền ngược để sửa lỗi đầu vào.

## 5. Chuỗi: bằng, pattern, tiền tố và đoạn chứa

### 5.1. Chọn đúng loại so khớp

| Keyword | Ý định |
| --- | --- |
| Không ghi toán tử, `Is`, `Equals` | Bằng giá trị |
| `StartingWith` | Bắt đầu bằng một chuỗi |
| `EndingWith` | Kết thúc bằng một chuỗi |
| `Containing` | Chứa chuỗi, khi thuộc tính là chuỗi |
| `Like` | So khớp pattern theo cơ chế của store |
| `NotLike`, `NotContaining` | Phủ định dạng so khớp tương ứng, nếu được hỗ trợ |
| `IgnoreCase` | Yêu cầu không phân biệt hoa thường cho thuộc tính thích hợp |

Ví dụ:

```java
List<Product> findByTenantIdAndNameStartingWith(
        String tenantId, String prefix);

List<Product> findByTenantIdAndNameContainingIgnoreCase(
        String tenantId, String fragment);

List<Product> findByTenantIdAndNameLike(
        String tenantId, String pattern);
```

`Containing` trên tên sản phẩm không đồng nghĩa với tìm kiếm toàn văn. Nó không tự có tách từ, xếp hạng độ liên quan, bỏ dấu tiếng Việt hoặc tìm gần đúng.

### 5.2. Pattern phụ thuộc ngôn ngữ truy vấn

Trong ngữ cảnh JPA/JPQL, `Like` dùng ngữ nghĩa pattern với `%` đại diện cho một chuỗi ký tự và `_` đại diện cho một ký tự. Khi cần tìm nguyên văn các ký tự này, phải có quy tắc escape phù hợp.

Các derived query chuỗi như `StartingWith`, `EndingWith` và `Containing` trong JPA có cơ chế chuẩn bị giá trị và escape wildcard cho dạng được hỗ trợ. Người gọi thường truyền đoạn văn bản cần tìm, không tự thêm `%` như khi chủ động cung cấp một pattern cho `Like`.

Ở MongoDB, các truy vấn chuỗi có thể được biểu diễn bằng regular expression; module cũng có những keyword đặc thù như `Regex`. Không mặc định rằng `%` và `_` có cùng ngữ nghĩa như trong JPQL khi chuyển phương thức hoặc dữ liệu đầu vào sang MongoDB.

Nếu cho phép người dùng cung cấp pattern regex, bạn đang cung cấp một hợp đồng khác với tìm nguyên văn một đoạn chuỗi. Cần xác định phạm vi pattern được chấp nhận và chi phí xử lý phù hợp.

### 5.3. Không phân biệt hoa thường không đồng nghĩa bỏ dấu

```java
List<Product> findByTenantIdAndNameIgnoreCase(
        String tenantId, String name);
```

`IgnoreCase` yêu cầu store thực hiện dạng so sánh thích hợp. Nó không tự xác lập rằng `"ca phe"` và `"cà phê"` bằng nhau, cũng không tự quyết định cách chuẩn hóa mọi biến thể Unicode.

Quy tắc collation, biểu thức chuyển hoa/thường, kiểu lưu trữ và index có thể ảnh hưởng kết quả lẫn hiệu năng. Với dữ liệu đa ngôn ngữ, nên dùng các cặp dữ liệu kiểm chứng đại diện thay vì chỉ thử chuỗi ASCII.

### 5.4. Đoạn rỗng có thể mở rộng phạm vi ngoài mong muốn

Một bộ lọc chứa chuỗi rỗng có thể khớp với một phạm vi rất rộng theo cách store chuyển truy vấn. Nếu màn hình tìm kiếm cần tối thiểu một số ký tự, hãy quy định ở tầng nhận yêu cầu trước khi gọi repository.

Chuỗi `""`, chuỗi chỉ có dấu cách và `null` là ba đầu vào khác nhau. Việc trim hay coi đầu vào trắng là thiếu bộ lọc phải là một quyết định rõ ràng.

## 6. Thuộc một tập giá trị với `In` và `NotIn`

### 6.1. `In` trên thuộc tính scalar

```java
import java.util.Collection;

List<Product> findByTenantIdAndStatusIn(
        String tenantId, Collection<String> statuses);
```

Nếu `statuses` là `{"ACTIVE", "DRAFT"}`, ý định là:

```text
 tenantId = ?
 AND status thuộc {ACTIVE, DRAFT}
```

Các phần tử của tập được dùng để kiểm tra một thuộc tính `status` của mỗi sản phẩm. Đây không phải yêu cầu rằng sản phẩm phải đồng thời mang cả hai trạng thái.

Truyền một collection, không nối các trạng thái thành một chuỗi như `"ACTIVE,DRAFT"` rồi kỳ vọng repository tự tách thành hai giá trị. Các store có thể còn hỗ trợ mảng hoặc những dạng đối số khác; hãy dùng dạng chữ ký được module hỗ trợ.

### 6.2. `NotIn` không phải phần bù đơn giản khi có dữ liệu thiếu

```java
List<Product> findByTenantIdAndStatusNotIn(
        String tenantId, Collection<String> excludedStatuses);
```

Với dữ liệu quan hệ, `NULL` chịu ngữ nghĩa logic ba giá trị. Một dòng có `status IS NULL` không tự được chọn chỉ vì trạng thái đó không bằng các chuỗi trong danh sách loại trừ.

Trong MongoDB, `$nin` có thể chọn cả document không có trường đang xét, chẳng hạn khi loại trừ một tập trạng thái chuỗi khác `null`. Do đó, kết quả của một derived query phủ định có thể khác với kỳ vọng hình thành từ SQL.

Nếu nghiệp vụ yêu cầu “có trạng thái xác định và không thuộc tập bị chặn”, cần biểu đạt cả yêu cầu tồn tại/khác null theo store. Không chỉ đổi `In` thành `NotIn` rồi coi các dữ liệu thiếu là đã được xử lý giống nhau.

### 6.3. Collection đầu vào rỗng và phần tử null

Cần quyết định rõ:

| Đầu vào | Một hợp đồng nghiệp vụ có thể chọn |
| --- | --- |
| Tập trạng thái được phép rỗng | Không có sản phẩm nào thỏa điều kiện |
| Tập trạng thái loại trừ rỗng | Không áp dụng bộ lọc loại trừ |
| Collection là `null` | Yêu cầu không hợp lệ hoặc biểu thị thiếu bộ lọc, tùy thiết kế |
| Collection có phần tử `null` | Xử lý riêng hoặc từ chối nếu trạng thái phải có giá trị |

Đây là những lựa chọn của ứng dụng, không phải cam kết chung của mọi derived query. Một backend có thể không chấp nhận dạng `IN` rỗng mà một provider sinh ra, hoặc có quy tắc riêng khi mở rộng collection.

Với SQL, thêm `NULL` vào danh sách của `NOT IN` có thể làm các ứng viên không còn thỏa điều kiện do kết quả so sánh trở thành không xác định. Đừng dùng `null` như một giá trị thay thế cho “không có trạng thái” trong tập đầu vào rồi kỳ vọng kết quả trực quan.

Tập đầu vào quá lớn còn có thể chạm giới hạn tham số hoặc tạo truy vấn tốn kém. Việc dùng một keyword ngắn không làm mất đi kích thước thực tế của yêu cầu.

## 7. Thuộc tính dạng collection là một bài toán khác

`Product.status` là một chuỗi, còn `Product.tags` là một collection. Điều kiện “status thuộc tập trạng thái đầu vào” khác với “collection tags chứa một phần tử”.

### 7.1. Ví dụ riêng cho collection được mapping trong JPA

Giả sử `tags` được mapping hợp lệ thành một collection giá trị, chẳng hạn qua cơ chế element collection của JPA. Các dạng truy vấn sau có ý nghĩa riêng khi được hỗ trợ:

```java
List<Product> findByTenantIdAndTagsContaining(
        String tenantId, String tag);

List<Product> findByTenantIdAndTagsIsEmpty(String tenantId);

List<Product> findByTenantIdAndTagsIsNotEmpty(String tenantId);
```

| Điều kiện | Ý nghĩa trong ngữ cảnh collection JPA này |
| --- | --- |
| `TagsContaining(tag)` | Collection có phần tử tương ứng với `tag` |
| `TagsIsEmpty` | Collection không có phần tử |
| `TagsIsNotEmpty` | Collection có ít nhất một phần tử |

`Containing` ở đây là kiểm tra thành viên collection. Nó không tìm xem một phần tử nhãn có chứa đoạn ký tự đó hay không.

Ví dụ, nếu nhãn là `"spring-data"`, việc tìm thành viên `"spring"` không tự có nghĩa là tìm một phần chuỗi bên trong nhãn.

### 7.2. Document và array cần xem ngữ nghĩa riêng

Trong MongoDB, một trường có thể là array. Các toán tử như `$in` có thể khớp khi array có phần tử thuộc tập đầu vào. Đây là ngữ nghĩa của truy vấn document, không phải bằng chứng rằng mọi tên derived query trên collection đều được JPA và MongoDB hiểu giống nhau.

Cần phân biệt ít nhất ba yêu cầu:

1. Có ít nhất một phần tử thuộc tập đầu vào.
2. Chứa tất cả phần tử đầu vào.
3. Toàn bộ collection bằng tập đầu vào theo một quy tắc cụ thể.

Không tự suy ra yêu cầu thứ hai hoặc thứ ba từ keyword `In`. Khi tên phương thức không thể hiện rõ yêu cầu hoặc store không hỗ trợ dạng cần dùng, hãy chuyển sang truy vấn khai báo hay API truy vấn/fragment tùy biến phù hợp.

`IsEmpty` cũng cần được xem theo kiểu thuộc tính và store. Một keyword dùng cho collection không tự trở thành cách kiểm tra chuỗi rỗng; document có trường thiếu, trường null và array rỗng còn là những trạng thái khác nhau.

## 8. `null`, không tồn tại, rỗng và trắng

### 8.1. Các trạng thái không được đánh đồng

| Trạng thái | Ví dụ |
| --- | --- |
| Giá trị null | `description = null` |
| Chuỗi rỗng | `description = ""` |
| Chuỗi trắng | `description = "   "` |
| Collection rỗng | `tags = []` |
| Trường không tồn tại | Document chưa có key `description` |

Một cột quan hệ không có khái niệm “key của dòng không tồn tại” giống một document linh hoạt. Ngược lại, trong document store, cả null và thiếu trường có thể cùng được ánh xạ về `null` trong một object Java thông thường. Mapping về cùng giá trị Java không làm cho trạng thái lưu trữ ban đầu trở thành giống nhau.

### 8.2. Điều kiện null tường minh

```java
List<Product> findByTenantIdAndDescriptionIsNull(String tenantId);

List<Product> findByTenantIdAndDescriptionIsNotNull(String tenantId);
```

Những điều kiện này không cần thêm một đối số `description`, vì `IsNull` và `IsNotNull` đã thể hiện giá trị cần kiểm tra.

Đối chiếu hai store tiêu biểu:

| Ngữ cảnh | Điều kiện null thường gặp | Ý nghĩa đáng chú ý |
| --- | --- | --- |
| JPA với cột được mapping | `IS NULL` | Cột có giá trị SQL null |
| MongoDB | Điều kiện bằng null trên trường | Có thể khớp cả giá trị null lẫn trường không tồn tại |
| MongoDB với điều kiện khác null | Dạng `$ne: null` | Nhắm đến trường tồn tại và có giá trị khác null |

Nếu cần phân biệt chính xác “có trường nhưng null” với “không có trường”, hãy dùng điều kiện đặc thù của store, chẳng hạn kiểm tra sự tồn tại và kiểu dữ liệu qua cơ chế truy vấn được hỗ trợ. Không coi `IsNull` là một abstraction bảo toàn sự phân biệt này trên mọi backend.

### 8.3. Đối số null trong so sánh bằng không phải bộ lọc tùy chọn chung

Xét:

```java
List<Product> findByTenantIdAndDescription(
        String tenantId, String description);
```

Trong derived query của JPA, đối số `null` cho dạng so sánh bằng này được xử lý thành điều kiện `IS NULL`. Nó không có nghĩa là bỏ điều kiện description và tìm mọi sản phẩm của tenant.

Hành vi đó cũng không được sao chép nguyên sang một câu JPQL viết tay có `p.description = :description`. Trong truy vấn khai báo, truyền `null` vào phép bằng không tự viết lại câu truy vấn thành `IS NULL` hay bỏ bộ lọc.

Nếu giao diện cho phép bỏ qua bộ lọc description, hãy thể hiện lựa chọn đó ở tầng xây dựng truy vấn hoặc ở cách chọn phương thức repository. Query by Example hay những API truy vấn động khác có quy tắc null riêng và chỉ là lựa chọn khi store cùng yêu cầu nghiệp vụ phù hợp.

### 8.4. Phủ định cần xem dữ liệu thiếu

Không nên mặc định:

```text
Tập kết quả của Not(X) = mọi dữ liệu trừ kết quả của X
```

Trong SQL, null ảnh hưởng logic điều kiện. Trong document store, dữ liệu thiếu và quy tắc của toán tử phủ định cũng có thể thay đổi phạm vi khớp.

Nếu nghiệp vụ nói “sản phẩm có mô tả và mô tả khác giá trị X”, hãy viết rõ phần “có mô tả” theo ngữ nghĩa cần dùng. Từ `Not` không thay thế quyết định nghiệp vụ về dữ liệu thiếu.

## 9. Kết hợp điều kiện mà vẫn giữ đúng phạm vi tenant

Một tên dài có thể hợp lệ về cú pháp nhưng không biểu đạt đúng ngoặc logic mong muốn:

```java
List<Product> findByTenantIdAndNameContainingOrDescriptionContaining(
        String tenantId, String namePart, String descriptionPart);
```

Cấu trúc các nhóm `Or` và `And` ở đây tương ứng với:

```text
(tenantId = ? AND name chứa ?) OR description chứa ?
```

Nhánh description không được giới hạn bởi tenant như yêu cầu thường gặp:

```text
 tenantId = ? AND (name chứa ? OR description chứa ?)
```

Khi cần ngoặc, nhiều điều kiện tùy chọn hoặc quy tắc kết hợp khó đọc, truy vấn khai báo hay implementation tùy biến có thể biểu đạt rõ hơn. Đừng kéo dài tên chỉ để giữ mọi logic trong derived query.

Cũng cần xác định tenant từ ngữ cảnh được phép truy cập. Một keyword so sánh đúng không tự xác thực người gọi có quyền chọn giá trị tenant đã truyền vào hay không.

## 10. Chọn derived query hay cơ chế khác

| Nhu cầu | Hướng xử lý phù hợp |
| --- | --- |
| Một vài điều kiện bằng, so sánh hoặc tập giá trị | Derived query, nếu store hỗ trợ |
| Khoảng có biên rõ và tên vẫn dễ đọc | Các toán tử so sánh tường minh hoặc abstraction khoảng được store hỗ trợ |
| Nhiều bộ lọc tùy chọn | API truy vấn động, Query by Example khi đủ khả năng, hoặc fragment tùy biến |
| Cần phân biệt null với thiếu trường trong document | Điều kiện đặc thù của store |
| Collection cần chứa tất cả phần tử, đếm phần tử hoặc logic phức tạp | Truy vấn khai báo hoặc API truy vấn phù hợp |
| Tìm kiếm toàn văn, xếp hạng hoặc xử lý ngôn ngữ | Tính năng tìm kiếm của store và index tương ứng |
| Cần ngữ nghĩa ổn định khi chuyển backend | Định nghĩa hợp đồng nghiệp vụ, triển khai riêng theo store và xác minh các ca biên |

Đổi sang truy vấn khai báo không tự làm truy vấn đúng hơn; lợi ích là bạn có thể biểu đạt cấu trúc và toán tử cụ thể rõ ràng hơn. Vẫn cần mapping, binding và hợp đồng kết quả chính xác.

Phân trang, sắp xếp và projection là các chiều khác của query method. Chúng không sửa được một điều kiện `Between` sai biên hoặc `IsNull` không đúng ý định. Tương tự, auditing điền thời điểm tạo không tự chọn giúp khoảng thời gian cần truy vấn.

## 11. Ví dụ phân tích yêu cầu hoàn chỉnh

Yêu cầu của một màn hình quản lý:

> Lấy sản phẩm của tenant hiện tại, có giá từ 100.000 đến dưới 500.000, thuộc một trong các trạng thái được chọn và được tạo trong khoảng thời gian báo cáo.

Trước tiên, diễn đạt bằng điều kiện độc lập với tên phương thức:

```text
 tenantId = tenant hiện tại
 AND price >= 100000
 AND price < 500000
 AND status thuộc tập trạng thái đã chọn
 AND createdAt >= startInclusive
 AND createdAt < endExclusive
```

Sau đó quyết định các trường hợp rìa:

- Không chọn trạng thái nghĩa là không có kết quả hay bỏ lọc trạng thái?
- Khoảng thời gian được tính theo múi giờ nào?
- Sản phẩm thiếu giá hoặc thời điểm tạo có được xem là dữ liệu hợp lệ không?
- Bộ lọc có thay đổi tùy chọn theo yêu cầu không?

Có thể ghép các keyword thành một derived query rất dài, nhưng nếu nhiều điều kiện là tùy chọn thì implementation truy vấn động thường dễ diễn đạt và bảo trì hơn. Cần chọn API có trong module thực tế; một abstraction đặc thù của JPA không tự hoạt động cho MongoDB.

Sau khi chọn implementation, sắp xếp và phân trang phải được bổ sung theo hợp đồng của màn hình. Chúng giúp giới hạn dữ liệu được trả về nhưng không thay đổi ngữ nghĩa của các bộ lọc đã xác định.

## 12. Các ca dữ liệu nên dùng để xác minh ngữ nghĩa

| Nhóm | Dữ liệu có khả năng phân biệt hành vi |
| --- | --- |
| So sánh số | Giá trị ngay dưới, đúng bằng và ngay trên ngưỡng |
| Khoảng | Đúng hai biên, ở trong và ngoài khoảng |
| Thời gian | Đúng mốc bắt đầu, đúng mốc kết thúc và gần mức chính xác của backend |
| Chuỗi | Khác hoa thường, có dấu, chuỗi rỗng, dấu cách và ký tự wildcard |
| `In` / `NotIn` | Giá trị có trong tập, ngoài tập, null, tập rỗng và tập chứa null |
| Collection thuộc tính | Không phần tử, một phần tử khớp, nhiều phần tử và chỉ khớp một phần chuỗi của nhãn |
| Document thiếu dữ liệu | Trường không tồn tại, trường có null và array rỗng |
| Phạm vi tenant | Hai tenant có sản phẩm với cùng tên, trạng thái hoặc giá |

Các ca này giúp phát hiện khác biệt mà một dữ liệu “đẹp” duy nhất không thể hiện. Khi chuyển store, nên giữ hợp đồng kỳ vọng ở mức nghiệp vụ và đối chiếu lại các ca biên, thay vì chỉ giữ nguyên tên phương thức.

Tên hợp lệ cũng không bảo đảm hiệu năng. Cần quan sát truy vấn thực tế, độ chọn lọc, index, kích thước tập `In`, phép so khớp chuỗi và chi phí phân trang trên backend đang dùng.

## 13. Bài tập tự kiểm tra

### Bài 1: Chọn biên khoảng giá

Yêu cầu là lấy sản phẩm giá từ 100 đến dưới 200. Một phương thức `findByPriceBetween(100, 200)` có đủ để bảo đảm hợp đồng đó trên JPA và MongoDB không?

**Gợi ý đáp án:** Không. Dạng `Between` hai giá trị có khác biệt về biên giữa hai module đã minh họa. Có thể biểu đạt rõ `PriceGreaterThanEqualAndPriceLessThan`, rồi xác minh store hỗ trợ và mapping đúng.

### Bài 2: So sánh chuỗi với thành viên collection

Domain có `name: String` và `tags: Set<String>`. Trong ngữ cảnh JPA được mapping phù hợp, `NameContaining("spring")` và `TagsContaining("spring")` có cùng loại kiểm tra không?

**Gợi ý đáp án:** Không. Dạng đầu tìm đoạn chuỗi trong tên. Dạng sau kiểm tra thành viên collection, không tự tìm một phần ký tự trong từng nhãn.

### Bài 3: Tập rỗng

Người dùng không chọn trạng thái nào, nhưng nghiệp vụ quy định điều đó nghĩa là không có sản phẩm phù hợp. Có nên bỏ điều kiện trạng thái rồi chạy truy vấn còn lại không?

**Gợi ý đáp án:** Không, vì làm vậy mở rộng kết quả trái với hợp đồng. Có thể xử lý trả tập kết quả rỗng ở tầng phù hợp thay vì gửi một `In` rỗng với hành vi backend chưa được xác định.

### Bài 4: Null và trường thiếu

Hai document MongoDB lần lượt có `description: null` và không có trường `description`. Có thể dùng điều kiện bằng null để chắc chắn chỉ chọn document thứ nhất không?

**Gợi ý đáp án:** Không. Điều kiện bằng null có thể khớp cả hai trạng thái. Cần điều kiện đặc thù để phân biệt trường có tồn tại và giá trị null theo yêu cầu.

### Bài 5: Bộ lọc tùy chọn

Một derived query JPA có điều kiện bằng trên `description`. Truyền `null` có tự bỏ điều kiện này không?

**Gợi ý đáp án:** Không. Với dạng derived equality nêu trong bài, nó được chuyển thành kiểm tra null. Nếu muốn bỏ lọc, hãy thể hiện bằng lựa chọn phương thức hoặc cơ chế xây dựng truy vấn phù hợp.

### Bài 6: Ngày báo cáo liền nhau

Vì sao khoảng `[đầu ngày, đầu ngày kế tiếp)` thuận tiện hơn việc tự tạo một thời điểm cuối ngày có nhiều chữ số phần giây?

**Gợi ý đáp án:** Nó biểu đạt biên rõ, ghép được các khoảng liên tiếp và không cần đoán mức chính xác cuối ngày của backend. Hai mốc phải được tính theo múi giờ nghiệp vụ rồi chuyển sang kiểu thời gian được lưu.

## Những điểm cần nhớ

- Chọn keyword sau khi đã viết rõ biểu thức và hợp đồng nghiệp vụ.
- `Between` không bảo đảm cùng quy tắc biên trên mọi store; các toán tử tường minh giúp thể hiện khoảng mong muốn.
- Phép chứa chuỗi, thành viên collection và thuộc một tập đầu vào là những yêu cầu riêng.
- `null`, thiếu trường, chuỗi rỗng và collection rỗng cần được phân biệt có chủ đích.
- Commons cung cấp abstraction; module, mapping và backend quyết định mức hỗ trợ cùng ngữ nghĩa thực thi cụ thể.
