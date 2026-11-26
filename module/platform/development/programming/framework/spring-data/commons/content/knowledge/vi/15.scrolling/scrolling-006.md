# Thuộc tính sắp xếp, giá trị null và dữ liệu cần trong projection

## Mục tiêu bài học

Một truy vấn cuộn có thể trả nội dung cửa sổ đầu đúng nhưng vẫn thất bại khi tạo vị trí tiếp theo. Với keyset scrolling, hệ thống cần đọc được giá trị các khóa sắp xếp từ kết quả để xây dựng điều kiện tiếp tục. Vì vậy, lựa chọn Sort, cách xử lý null và hình dạng projection phải được thiết kế cùng nhau.

Sau bài học, bạn có thể:

- Giải thích vì sao keyset scrolling cần một thứ tự đủ phân biệt các phần tử.
- Xác định những thuộc tính phải có trong kết quả projection.
- Nhận biết rủi ro của khóa sắp xếp null hoặc trường không tồn tại.
- Phân biệt hint đặt null đầu/cuối với khả năng tạo điều kiện keyset hợp lệ.
- Tách projection phục vụ truy vấn cuộn khỏi DTO công khai của API.

Spring Data Commons cung cấp `ScrollPosition`, `Window` và metadata chung. Các ví dụ chỉ áp dụng trong dòng phiên bản và module lưu trữ hỗ trợ keyset scrolling với dạng query cùng projection tương ứng.

## 1. Offset và keyset sử dụng dữ liệu khác nhau để tiếp tục

Offset scrolling dùng một vị trí trong tập kết quả. Keyset scrolling dùng những giá trị khóa tại điểm đã đọc để xác định phần kết quả đứng sau điểm đó.

| Cơ chế | Thông tin cốt lõi để tiếp tục |
| --- | --- |
| Offset scrolling | Vị trí offset theo hợp đồng cuộn |
| Keyset scrolling | Giá trị của các thuộc tính trong thứ tự hiệu lực |

Ví dụ thứ tự:

```text
publishedAt DESC, id DESC
```

Sau một cửa sổ, mốc keyset cần chứa đủ thông tin tương ứng với:

```text
publishedAt của phần tử mốc
id của phần tử mốc
```

Chỉ biết id hoặc chỉ biết publishedAt có thể không đủ để tiếp tục đúng theo thứ tự đã chọn.

Đây là lý do projection phục vụ keyset không thể được thiết kế chỉ dựa trên những cột người dùng muốn nhìn thấy. Một số dữ liệu còn cần cho cơ chế điều hướng.

## 2. Bắt đầu từ thứ tự đủ phân biệt

Dùng domain bài viết:

```text
Article
├── id: Long
├── tenantId: String
├── title: String
└── publishedAt: Instant, có thể null khi còn là bản nháp
```

Màn hình chỉ đọc bài đã có thời điểm xuất bản, mới nhất trước:

```text
Bộ lọc:
    tenantId = tenant đang truy cập
    publishedAt khác null

Thứ tự:
    publishedAt DESC
    id DESC
```

Trong ví dụ, id khác null và duy nhất trong phạm vi tenant. Các thuộc tính phải được mapping đúng theo store.

### 2.1. Không chỉ dùng thời điểm nếu thời điểm có thể trùng

Giả sử dữ liệu đã được lọc như sau:

| id | publishedAt |
| --- | --- |
| 210 | 2026-11-25T08:00:00Z |
| 209 | 2026-11-25T08:00:00Z |
| 208 | 2026-11-25T08:00:00Z |
| 207 | 2026-11-25T08:00:00Z |
| 206 | 2026-11-25T07:59:00Z |
| 205 | 2026-11-25T07:58:00Z |

Cửa sổ đầu có ba phần tử 210, 209, 208. Nếu mốc chỉ giữ thời điểm 08:00 và lần sau tìm thời điểm nhỏ hơn 08:00, bài 207 sẽ bị bỏ qua.

Thêm id vào thứ tự giúp phân biệt các bài cùng thời điểm. Mốc sau bài 208 là cặp:

```text
(2026-11-25T08:00:00Z, 208)
```

Lần đọc tiếp vẫn lấy được bài 207 cùng thời điểm nhưng có id nhỏ hơn.

### 2.2. Thứ tự hiệu lực có thể được bổ sung khóa định danh

Trong cơ chế keyset được module hỗ trợ, Spring Data có thể bổ sung khóa định danh hoặc phần khóa định danh còn thiếu để bảo đảm thứ tự đủ duy nhất.

Khi thiết kế projection, cần tính tới các khóa của thứ tự hiệu lực, không chỉ những thuộc tính bạn đã viết đầu tiên trong Sort. Với định danh ghép, yêu cầu dữ liệu có thể gồm nhiều thành phần.

Khai báo rõ `publishedAt DESC, id DESC` trong ví dụ giúp người đọc nhìn thấy cả hướng lẫn khóa phụ, thay vì chỉ dựa vào việc hạ tầng có thể bổ sung khóa ngầm.

## 3. Giá trị khóa được dùng để xây dựng điều kiện tiếp tục

Với hai thuộc tính khác null, thứ tự giảm dần theo publishedAt rồi id, điều kiện khái niệm sau mốc `(t, k)` là:

```text
 publishedAt < t
 OR (publishedAt = t AND id < k)
```

Khi ghép với bộ lọc tenant, cấu trúc phải giữ toàn bộ nhánh tiếp tục bên trong cùng phạm vi:

```text
 tenantId = tenant hiện tại
 AND publishedAt khác null
 AND (
      publishedAt < t
      OR (publishedAt = t AND id < k)
 )
```

Đây là biểu thức giải thích ngữ nghĩa, không phải một câu SQL dùng nguyên văn cho mọi store. Query creator của module thực hiện việc chuyển đổi phù hợp.

### Hướng tăng/giảm quyết định phép so sánh

Với hai khóa không null `a`, `b` và mốc `(x, y)`:

| Thứ tự | Điều kiện khái niệm để đi tiếp theo chiều thuận |
| --- | --- |
| `a ASC, b ASC` | `a > x OR (a = x AND b > y)` |
| `a ASC, b DESC` | `a > x OR (a = x AND b < y)` |
| `a DESC, b ASC` | `a < x OR (a = x AND b > y)` |
| `a DESC, b DESC` | `a < x OR (a = x AND b < y)` |

Phép so sánh thực tế phải thống nhất với kiểu dữ liệu, collation và mapping của store. Không tự tái tạo cursor bằng một comparator Java rồi coi nó luôn tương đương với cách backend sắp xếp chuỗi.

Bảng cho thấy vì sao cần giá trị của mọi khóa: thiếu một giá trị làm một phần của điều kiện tiếp tục không còn được xác định đúng.

## 4. Khóa null làm hỏng giả định so sánh

Keyset scrolling thông thường yêu cầu các thuộc tính sắp xếp có giá trị khác null. Null gây vấn đề ở cả việc trích xuất khóa lẫn ngữ nghĩa của điều kiện tiếp tục.

Trong hệ quan hệ, các biểu thức như:

```text
publishedAt < NULL
publishedAt = NULL
```

không hoạt động như so sánh với một thời điểm thông thường. SQL dùng logic ba giá trị; phải có điều kiện chuyên biệt khi kiểm tra null.

Trong document store, giá trị null và trường không tồn tại còn có thể là những trạng thái khác nhau, với quy tắc so sánh và matching riêng.

Vì vậy, một khóa null có thể dẫn đến lỗi tạo vị trí hoặc kết quả tiếp tục không như mong muốn. Không chờ tới khi có exception mới coi thiết kế không phù hợp.

### 4.1. nullsFirst hoặc nullsLast không tự sửa keyset

Một Order có hint đặt null cuối không tự cung cấp giá trị hữu hạn cho khóa null. Cơ chế keyset vẫn cần tạo được predicate tương đương với đúng thứ tự đó.

Ngoài ra, mức hỗ trợ hint null ordering phụ thuộc store và dạng query. Không thể kết luận rằng:

```text
Đã yêu cầu NULLS LAST
        ⇒ mọi khóa nullable đều dùng được cho keyset
```

Đặt null ở đâu và xây dựng điều kiện tiếp tục qua vùng null là hai vấn đề cần được hỗ trợ đồng bộ.

### 4.2. Annotation non-null không thay dữ liệu hiện có

Một getter được chú thích khác null không tự điền các bản ghi cũ đang null hoặc các document đang thiếu trường. Cần bảo vệ dữ liệu bằng luồng ghi, mapping và ràng buộc phù hợp.

Auditing cũng chỉ điền những field được cấu hình và những tình huống nó thực sự tham gia. Không dùng việc có auditing như bằng chứng rằng mọi thuộc tính thời gian được dùng để sort đều đã có giá trị, nhất là dữ liệu nhập cũ hoặc được ghi qua luồng khác.

## 5. Chọn chính sách cho dữ liệu chưa có khóa

Với Article có publishedAt null ở bản nháp, có nhiều lựa chọn tùy nghiệp vụ:

| Chính sách | Khi có thể phù hợp | Điều cần giữ rõ |
| --- | --- | --- |
| Chỉ cuộn bài đã có thời điểm xuất bản | Danh sách bài đã xuất bản | Loại bản nháp khỏi phạm vi là chủ đích |
| Chọn một khóa khác luôn có giá trị | Danh sách cần cả bản nháp lẫn bài xuất bản | Ý nghĩa thứ tự mới phải đúng yêu cầu |
| Lưu một thuộc tính chuẩn hóa phục vụ sort | Có quy tắc ưu tiên riêng được xác định | Mọi luồng ghi phải giữ thuộc tính này nhất quán |
| Dùng một cách truy vấn khác có xử lý null phù hợp | Không đáp ứng được giả định keyset thông thường | Kiểm tra khả năng và chi phí theo store |

Không nên âm thầm bỏ bản nháp chỉ để truy vấn hết lỗi nếu màn hình cần cả bản nháp. Trước tiên phải xác định tập dữ liệu hợp lệ của tính năng.

Nếu dùng giá trị fallback, cần bảo đảm cùng một giá trị được dùng cho sắp xếp, trích xuất khóa và predicate tiếp tục. Chỉ thêm một biểu thức như `COALESCE` vào phần ORDER BY nhưng vẫn trích xuất hoặc so sánh field gốc nullable có thể tạo hai ngữ nghĩa khác nhau.

Một thuộc tính sort được lưu riêng hoặc một implementation truy vấn đặc thù có thể phù hợp hơn, nhưng phải được module hỗ trợ. Không giả định mọi truy vấn khai báo hay mọi expression đều tham gia được cơ chế keyset tự động.

## 6. Projection phải giữ đủ dữ liệu cho khóa

Projection phục vụ ví dụ Article:

```java
import java.time.Instant;

interface ArticleScrollRow {

    Long getId();

    String getTitle();

    Instant getPublishedAt();
}
```

Vai trò từng thuộc tính:

| Thuộc tính | Vai trò trong ví dụ | Cần cho keyset? |
| --- | --- | --- |
| `publishedAt` | Khóa sắp xếp chính | Có |
| `id` | Khóa phụ phân biệt các bài cùng thời điểm | Có |
| `title` | Nội dung màn hình | Không phải khóa, nhưng ứng dụng cần hiển thị |
| `tenantId` | Điều kiện lọc cố định của truy vấn | Không tự bắt buộc chỉ vì là bộ lọc; cần giữ ngữ cảnh truy vấn phù hợp |

Nếu tenantId là một phần của khóa định danh hoặc thứ tự hiệu lực trong một mô hình khác, yêu cầu dữ liệu phải được xét lại theo mô hình đó.

### 6.1. Projection chỉ có dữ liệu hiển thị có thể thiếu khóa

Ví dụ chưa đủ cho thứ tự publishedAt rồi id:

```java
interface ArticleTitleOnly {
    String getTitle();
}
```

Người dùng có thể chỉ muốn nhìn title, nhưng cơ chế keyset còn cần publishedAt và id để tạo vị trí tiếp tục.

Một cửa sổ đầu trả title thành công không chứng minh rằng mốc tiếp theo tạo được. Thiếu khóa có thể chỉ lộ khi hạ tầng trích xuất keyset hoặc khi người gọi yêu cầu vị trí của phần tử.

Không dựa vào giả định backend đã dùng cột sort trong ORDER BY nên chắc chắn projection cũng cung cấp cột đó cho cơ chế trích xuất. Phần được backend dùng để sắp xếp và phần được materialize qua projection là hai hợp đồng cần khớp nhau.

### 6.2. Tên và kiểu phải giữ đúng ngữ nghĩa

Nếu khóa gốc là Instant, projection nên cung cấp thuộc tính tương ứng với kiểu mà mapping/keyset extraction hiểu được. Một getter chỉ trả chuỗi ngày đã định dạng không tự thay thế được giá trị thời gian gốc.

Tương tự, làm tròn timestamp, cắt phần giây hoặc chuyển số thập phân sang một kiểu mất độ chính xác có thể khiến mốc không còn khớp đúng ranh giới đã sắp xếp.

Alias, đường dẫn lồng nhau và DTO constructor phải được thiết kế theo quy tắc mapping của store. Đổi tên getter sang một tên gần nghĩa không bảo đảm framework tự liên kết nó với khóa cần trích xuất.

### 6.3. Getter tính toán không tự trở thành khóa persistence

Một default method projection tính chuỗi hiển thị từ title và thời gian không tự cung cấp một field queryable có thể dùng cho keyset.

Điều kiện tiếp tục cần dựa trên cùng các giá trị mà store thực sự dùng trong thứ tự. Nếu muốn sắp xếp theo giá trị tính toán, cần một cơ chế truy vấn và trích xuất khóa hỗ trợ giá trị đó, thay vì chỉ thêm một getter Java.

## 7. Repository minh họa với projection đầy đủ

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.repository.Repository;

interface ArticleScrollRepository extends Repository<Article, Long> {

    Window<ArticleScrollRow>
    findFirst3ByTenantIdAndPublishedAtIsNotNullOrderByPublishedAtDescIdDesc(
            String tenantId, ScrollPosition position);
}
```

Ví dụ này giả định store hỗ trợ derived query, keyset scrolling và interface projection tương ứng. Chữ ký ScrollPosition là abstraction chung; các lời gọi dưới đây chủ động dùng keyset position.

Lần đọc đầu:

```java
Window<ArticleScrollRow> window = repository
        .findFirst3ByTenantIdAndPublishedAtIsNotNullOrderByPublishedAtDescIdDesc(
                tenantId,
                ScrollPosition.keyset()
        );
```

Các ràng buộc được thể hiện cùng nhau:

- Chỉ đọc đúng tenant.
- Chỉ đọc các bài có publishedAt khác null.
- Sắp xếp giảm dần theo publishedAt rồi id.
- Projection cung cấp cả hai khóa và title cần hiển thị.
- Kích thước cửa sổ tối đa là ba theo hợp đồng scrolling được hỗ trợ.

Tạo vị trí và đọc tiếp:

```java
if (!window.isEmpty() && window.hasNext()) {
    ScrollPosition nextPosition =
            window.positionAt(window.size() - 1);

    Window<ArticleScrollRow> nextWindow = repository
            .findFirst3ByTenantIdAndPublishedAtIsNotNullOrderByPublishedAtDescIdDesc(
                    tenantId,
                    nextPosition
            );

    // Xử lý nextWindow theo luồng của ứng dụng.
}
```

Không tự lấy id cuối rồi dựng một vị trí chỉ chứa id khi thứ tự còn có publishedAt. Dùng vị trí do Window cung cấp để giữ đầy đủ metadata mà cơ chế cuộn cần.

Với dữ liệu đã nêu, cửa sổ đầu gồm 210, 209, 208; cửa sổ sau vẫn lấy được 207 trước 206 và 205.

## 8. Dữ liệu nội bộ cho cursor khác dữ liệu công khai

Có thể cần publishedAt để tạo cursor nhưng không muốn hiển thị field đó trong phản hồi. Điều này không buộc phải loại nó khỏi projection repository.

Hãy tách ba lớp:

```text
Projection repository:
    id, title, publishedAt
        ↓
Tạo vị trí tiếp tục từ Window gốc
        ↓
DTO công khai:
    chỉ những field mà API muốn trả
```

Ví dụ DTO dùng Java record trong dự án có mức ngôn ngữ phù hợp:

```java
record ArticleView(Long id, String title) {

    static ArticleView from(ArticleScrollRow row) {
        return new ArticleView(row.getId(), row.getTitle());
    }
}
```

Xử lý kết quả:

```java
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

Optional<ScrollPosition> nextPosition =
        !window.isEmpty() && window.hasNext()
                ? Optional.of(window.positionAt(window.size() - 1))
                : Optional.empty();

List<ArticleView> items = window.getContent().stream()
        .map(ArticleView::from)
        .collect(Collectors.toList());
```

`nextPosition` là dữ liệu nội bộ để tầng API mã hóa theo hợp đồng cursor của ứng dụng. Không coi việc serialize nguyên một ScrollPosition bằng công cụ JSON bất kỳ là định dạng giao tiếp ổn định mặc định.

Điểm quan trọng là vị trí được lấy từ Window giữ đủ khóa, trước khi bạn chỉ còn danh sách DTO thiếu publishedAt. Không tự dựng một Window mới từ các DTO tối giản rồi kỳ vọng các khóa đã bỏ vẫn được suy ra.

API bên ngoài có thể giữ cursor là một token và danh sách là DTO riêng. Các field cần cho cơ chế truy vấn không phải tự động trở thành field công khai.

## 9. Phân biệt ba nguyên nhân của một khóa thiếu

| Nguyên nhân | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Dữ liệu lưu trữ thật sự null hoặc thiếu | Bản ghi cũ chưa có publishedAt | Chọn chính sách dữ liệu, backfill hoặc bộ lọc đúng nghiệp vụ |
| Projection không materialize khóa | Chỉ khai báo getter title | Bổ sung các thuộc tính khóa vào projection/mapping |
| Biến đổi làm mất ngữ nghĩa khóa | Chuyển Instant sang ngày rút gọn | Giữ giá trị và kiểu phù hợp cho việc tạo cursor |

Ba tình huống có thể cùng biểu hiện như không có giá trị lúc trích xuất, nhưng cách sửa khác nhau.

Thêm `@Nullable` vào getter không làm dữ liệu đủ cho keyset. Thêm annotation non-null cũng không tự tạo giá trị thiếu. Cần xác định thiếu từ nguồn lưu trữ, từ query hay từ quá trình ánh xạ.

Khi kiểm tra lỗi, nên xem cả nội dung được query chọn, effective sort và đối tượng projection mà cơ chế tạo vị trí thực sự nhìn thấy. Chỉ kiểm tra rằng một cột có tồn tại trong database chưa đủ.

## 10. Tính ổn định, ngữ cảnh và hiệu năng

### 10.1. Khóa phải giữ cùng quy tắc so sánh

Nếu sort dùng collation hoặc một giá trị chuẩn hóa, điều kiện tiếp tục và key extraction phải phù hợp với cùng quy tắc. Không dùng giá trị hiển thị đã biến đổi để tự dựng lại khóa theo một quy tắc khác.

Cursor cũng gắn với tập điều kiện và thứ tự. Đổi tenant, bộ lọc, hướng sort hoặc cấu trúc khóa rồi dùng lại mốc cũ không còn là tiếp tục cùng một truy vấn.

### 10.2. Khóa thay đổi vẫn có thể làm phần tử dịch chuyển

Keyset giúp tránh nhiều vấn đề offset sâu và dịch chỉ số, nhưng không tự tạo snapshot. Nếu publishedAt của một bài được sửa giữa hai lần đọc, bài có thể chuyển qua ranh giới mốc.

Cần chọn field đủ ổn định cho yêu cầu tác vụ và đánh giá riêng tình huống thêm, sửa hoặc xóa dữ liệu. Khóa non-null và đầy đủ trong projection là điều kiện cần cho thiết kế này, không phải bảo đảm rằng mọi thay đổi đồng thời đều vô hại.

### 10.3. Index phải được xem cùng bộ lọc và thứ tự

Đường truy vấn minh họa lọc tenant rồi sắp xếp publishedAt và id. Một index phù hợp cần được cân nhắc theo chính bộ lọc, thứ tự, hướng và khả năng của backend.

Projection có đủ khóa không đồng nghĩa query đã được index hỗ trợ hoặc trở thành covering query. Ngược lại, thêm field hiển thị vào projection có thể ảnh hưởng lượng dữ liệu đọc, dù keyset vẫn đúng.

Cần quan sát truy vấn và kế hoạch thực thi thực tế. Một abstraction Commons không tự tạo cùng một chiến lược index cho store quan hệ và document store.

## 11. Các ca dữ liệu nên dùng để xác minh

| Ca | Mục đích |
| --- | --- |
| Nhiều bài cùng publishedAt, ranh giới nằm giữa nhóm đó | Phát hiện thiếu khóa phụ hoặc điều kiện equality |
| Bài có publishedAt null | Kiểm tra đúng chính sách loại trừ hoặc xử lý |
| Document thiếu hẳn trường thời gian | Phân biệt dữ liệu thiếu với giả định non-null |
| Projection thiếu publishedAt hoặc id | Kiểm tra khả năng tạo vị trí, không chỉ đọc nội dung |
| Timestamp có phần giây sát nhau | Phát hiện mất độ chính xác khi ánh xạ hoặc tạo token |
| Cửa sổ cuối thiếu phần tử và cửa sổ rỗng | Kiểm tra điều hướng và việc gọi positionAt |
| Cùng giá trị ở tenant khác | Kiểm tra phạm vi dữ liệu của mọi nhánh keyset |
| Chuyển projection sang DTO tối giản | Bảo đảm vị trí đã được giữ đúng trước khi bỏ field nội bộ |
| Cập nhật khóa sắp xếp giữa hai lần đọc | Đánh giá yêu cầu nhất quán và tính ổn định |

Với một tập dữ liệu ổn định, việc duyệt toàn bộ nên giữ đúng thứ tự, không mất phần tử ở ranh giới trùng khóa và không đọc lặp do thiếu tiêu chí phân biệt.

Việc query đầu thành công chưa đủ. Cần xác minh mốc tiếp theo tạo được và được dùng để đọc đúng cửa sổ sau.

## 12. Bài tập tự kiểm tra

### Bài 1: Chỉ lấy title

Danh sách chỉ hiển thị title, nhưng sort là `publishedAt DESC, id DESC`. Projection repository chỉ có getter title có đủ cho keyset không?

**Gợi ý đáp án:** Không. Cần cung cấp publishedAt cùng id và những khóa hiệu lực khác nếu có. Có thể bỏ publishedAt ở DTO bên ngoài sau khi tạo vị trí từ Window đầy đủ.

### Bài 2: Nhóm trùng thời gian

Cửa sổ kết thúc ở bài id 208 lúc 08:00. Bài id 207 cũng xuất bản lúc 08:00. Nếu chỉ dùng điều kiện thời điểm nhỏ hơn 08:00 thì điều gì xảy ra?

**Gợi ý đáp án:** Bài 207 bị bỏ qua. Cần cả nhánh bằng thời điểm và so sánh khóa phụ theo đúng hướng.

### Bài 3: Nulls last

Đã yêu cầu đặt publishedAt null ở cuối. Có thể kết luận keyset qua các bài null sẽ tự đúng không?

**Gợi ý đáp án:** Không. Null ordering và điều kiện tiếp tục cần được hỗ trợ đồng bộ. Hint không tự tạo một giá trị khóa non-null hoặc giải quyết logic so sánh với null.

### Bài 4: Getter non-null

Projection khai báo getter thời gian theo hợp đồng non-null nhưng dữ liệu nhập cũ có giá trị null. Annotation có tự sửa dữ liệu đó không?

**Gợi ý đáp án:** Không. Cần xử lý dữ liệu và luồng ghi hoặc chọn bộ lọc/chính sách thích hợp. Hợp đồng kiểu không tự backfill kho dữ liệu.

### Bài 5: Chuỗi ngày hiển thị

Projection chỉ trả publishedAt dưới dạng chuỗi ngày không có giờ. Có thể dùng nó thay cho Instant để tiếp tục keyset theo thời điểm đầy đủ không?

**Gợi ý đáp án:** Không có cơ sở để coi là tương đương. Bạn đã mất độ chính xác và có thể đổi quy tắc so sánh. Giữ giá trị được mapping phù hợp cho khóa; định dạng cho giao diện ở bước sau.

### Bài 6: Bộ lọc và projection

TenantId chỉ dùng làm điều kiện cố định, không nằm trong sort hoặc khóa định danh của ví dụ. Có bắt buộc đưa nó vào projection chỉ vì query có lọc tenant không?

**Gợi ý đáp án:** Không tự động. Projection cần đủ các khóa để trích xuất và dữ liệu ứng dụng sử dụng. Ngữ cảnh tenant vẫn phải được giữ cho query tiếp theo; nếu mô hình khóa khác, yêu cầu projection cần được xét lại.

## Những điểm cần nhớ

- Keyset tiếp tục dựa trên giá trị khóa, nên thứ tự, dữ liệu nguồn và projection phải thống nhất.
- Dùng khóa phụ đủ duy nhất để không mất phần tử trong nhóm có cùng khóa chính.
- Khóa null hoặc thiếu trường không được sửa chỉ bằng nullsFirst/nullsLast hay annotation nullability.
- Projection nội bộ cần giữ mọi khóa sắp xếp hiệu lực với tên, kiểu và độ chính xác phù hợp.
- Tạo vị trí từ Window đầy đủ rồi mới ánh xạ sang DTO công khai; giữ cùng bộ lọc, thứ tự và ngữ cảnh khi tiếp tục.
