# PageImpl, SliceImpl và trường hợp tự tạo kết quả

Repository có thể trả về `Page<T>` hoặc `Slice<T>` khi module store hỗ trợ. Trong nhiều trường hợp khác, ứng dụng tự thực hiện truy vấn, gọi dịch vụ tìm kiếm hoặc xử lý một tập dữ liệu đã có. Khi đó, `PageImpl` và `SliceImpl` là những lớp triển khai của Spring Data Commons có thể dùng để đóng gói kết quả.

Điểm quan trọng nhất: **hai lớp này nhận nội dung đã được chuẩn bị; chúng không tự truy vấn, lọc, sắp xếp hay cắt trang cho danh sách được truyền vào**.

Muốn tự tạo kết quả đúng, cần tách hai việc:

1. Lấy đúng phần dữ liệu theo hợp đồng phân trang.
2. Tạo metadata đúng với nguồn dữ liệu đó.

Sau bài học, bạn cần có khả năng:

- Chọn `PageImpl` khi có tổng số phần tử đáng tin cậy và `SliceImpl` khi chỉ cần khả năng đi tiếp.
- Dùng đúng constructor và phân biệt kích thước yêu cầu với số phần tử thực tế.
- Tạo page từ một snapshot trong bộ nhớ mà không cắt sai offset.
- Tạo slice bằng kỹ thuật lấy dư một phần tử.
- Giữ bộ lọc, thứ tự, tổng số và phạm vi truy cập nhất quán.
- Nhận ra giới hạn của việc tự tạo metadata và cách xử lý những trường hợp biên.

## 1. Page và Slice khác nhau về thông tin phải biết

| Kiểu | Thông tin chính | Ứng dụng cần cung cấp khi tự tạo |
|---|---|---|
| `Slice<T>` | Nội dung hiện tại, mô tả yêu cầu, có phần tiếp theo hay không | `content`, `Pageable`, `hasNext` |
| `Page<T>` | Những thông tin của slice cùng tổng số phần tử/số trang | `content`, `Pageable`, `total` |

`Page` mở rộng hợp đồng `Slice`. Vì vậy page cũng có các phương thức như `hasNext()`, nhưng nó có thêm metadata tổng.

`PageImpl` triển khai `Page`. `SliceImpl` triển khai `Slice` và không tự có `getTotalElements()` hoặc `getTotalPages()`.

### 1.1. Không cần tổng thì đừng tự bịa tổng

Nếu nguồn chỉ cho biết “còn dữ liệu phía sau”, điều đó đủ để tạo một slice phù hợp. Nó không đủ để tạo một page có tổng chính xác.

Các cách như lấy `content.size()` làm tổng, hoặc gán một số rất lớn để `hasNext()` luôn đúng, làm hợp đồng page sai nghĩa.

Ngược lại, nếu giao diện cần tổng số trang để nhảy trực tiếp tới trang cuối, slice không cung cấp thông tin đó. Cần một nguồn tổng số thích hợp hoặc thay đổi yêu cầu giao diện.

### 1.2. Pageable là mô tả yêu cầu

Với:

```java
Pageable request = PageRequest.of(2, 10);
```

ý nghĩa là:

- Chỉ số trang bằng 2, tính từ 0.
- Kích thước yêu cầu bằng 10.
- Offset bằng 20.

Khi tự truy vấn, ứng dụng phải áp dụng offset và giới hạn đó lên đúng tập dữ liệu. Truyền `request` vào constructor không thay thế bước lấy dữ liệu.

## 2. Các constructor và trách nhiệm của chúng

Những import dùng chung:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.SliceImpl;
import org.springframework.data.domain.Sort;
```

### 2.1. PageImpl với metadata đầy đủ

```java
Page<OrderRow> page =
    new PageImpl<>(content, request, totalElements);
```

Trong đó:

- `content` là nội dung của trang hiện tại.
- `request` mô tả trang và thứ tự đã dùng để lấy nội dung.
- `totalElements` là tổng số phần tử của toàn bộ tập thỏa điều kiện, không phải số phần tử của trang.

### 2.2. SliceImpl với cờ đi tiếp

```java
Slice<OrderRow> slice =
    new SliceImpl<>(content, request, hasNext);
```

Constructor nhận cờ `hasNext` từ caller. Nó không tự hỏi store xem còn phần tử hay không.

### 2.3. Constructor chỉ có content

```java
Page<OrderRow> wholePage = new PageImpl<>(allRows);

Slice<OrderRow> wholeSlice = new SliceImpl<>(allRows);
```

Các dạng này dùng mô tả unpaged. Với page, danh sách được xem là toàn bộ kết quả, tổng dựa trên số phần tử của danh sách. Với slice chỉ có content, không khai báo phần tiếp theo.

Không dùng constructor một tham số để biểu diễn một phần kết quả từ xa rồi mong nó nhớ offset hoặc tổng số mà chưa được cung cấp.

### 2.4. Constructor không tự cắt danh sách

Ví dụ sai về ý định:

```java
// allRows chứa 500 phần tử.
// Constructor không tự chọn 20 phần tử đầu.
Page<OrderRow> wrong =
    new PageImpl<>(allRows, PageRequest.of(0, 20), 500);
```

Đối tượng có thể mang metadata kích thước yêu cầu là 20 nhưng nội dung thực tế vẫn có 500 phần tử.

Cần cắt đúng nội dung trước, hoặc tốt hơn là lấy đúng trang từ nguồn khi dữ liệu lớn.

Hai lớp cần content và `Pageable` hợp lệ, không phải null. Tuy nhiên, việc constructor nhận các giá trị không chứng minh chúng đã thống nhất về ngữ nghĩa.

## 3. Đọc metadata của một kết quả tự tạo

Giả sử:

```text
request: page = 2, size = 10
content: 5 phần tử
total:   25
```

Khi tạo page phù hợp:

| Phương thức | Giá trị/ý nghĩa |
|---|---|
| `getNumber()` | 2 |
| `getSize()` | 10, kích thước yêu cầu |
| `getNumberOfElements()` | 5, số phần tử thực tế |
| `getTotalElements()` | 25 trong ví dụ nhất quán này |
| `getTotalPages()` | 3 |
| `hasPrevious()` | Có trang trước theo chỉ số hiện tại |
| `hasNext()` | Không còn trang theo metadata tổng |

Không đồng nhất `getSize()` với `getNumberOfElements()`. Một trang cuối có ít phần tử hơn kích thước yêu cầu là bình thường.

Với slice, `hasNext()` phản ánh cờ được truyền khi tạo. Với page, khả năng đi tiếp được suy ra từ số trang và vị trí theo metadata tổng.

### 3.1. Metadata không tự tạo truy vấn tiếp theo

`nextPageable()` trả về mô tả yêu cầu tiếp theo theo hợp đồng kết quả. Nó không tự tải dữ liệu.

Luồng sử dụng thường là:

```text
nhận slice/page
    → kiểm tra hasNext()
    → lấy mô tả trang tiếp
    → gọi nguồn dữ liệu lần nữa
```

Không dùng `nextPageable()` mà bỏ qua trạng thái có phần tiếp theo; ở cuối kết quả, nó không còn biểu diễn một trang tiếp theo bình thường để tiếp tục vô hạn.

## 4. Trước khi cắt trang phải xác định tập dữ liệu logic

Một quy trình đúng về ý nghĩa:

```text
Phạm vi truy cập và bộ lọc
       ↓
Khử trùng lặp/nhóm nếu use case cần
       ↓
Thứ tự xác định
       ↓
Offset và giới hạn
       ↓
Đóng gói PageImpl hoặc SliceImpl
```

Tổng số cần nói về tập phần tử cùng cấp với `content`.

Ví dụ:

- Content là đơn hàng duy nhất thì count cần đếm đơn hàng, không phải số dòng join bị nhân lên.
- Content là nhóm theo trạng thái thì total phải nói về số nhóm nếu API phân trang các nhóm.
- Content chỉ thuộc một tenant thì count không được tính cả tenant khác.
- Bộ lọc tìm kiếm được áp dụng ở query dữ liệu cũng phải có trong nguồn tổng.

### 4.1. Thứ tự phải ổn định

Ví dụ thứ tự cho đơn hàng:

```java
Sort order = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Pageable request = PageRequest.of(0, 20, order);
```

Giả sử id duy nhất và không null, id là tiêu chí phân xử khi thời điểm tạo bằng nhau.

`Sort` trong metadata phải mô tả thứ tự đã thực hiện. Việc chỉ gắn nó vào `PageImpl` không sắp lại nội dung.

Thứ tự xác định vẫn không tạo snapshot bất biến. Nếu dữ liệu đổi giữa hai lần gọi, offset pagination có thể bị ảnh hưởng dù từng lần đều có sort rõ ràng.

## 5. Tạo PageImpl từ một snapshot trong bộ nhớ

Trường hợp phù hợp là danh sách nhỏ đã có sẵn, kết quả tổng hợp hữu hạn hoặc dữ liệu được cache theo một snapshot rõ ràng.

Hàm dưới nhận danh sách **đã lọc và đã có thứ tự mong muốn**. Nó không tự diễn giải `Sort` thành một comparator.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;

public final class InMemoryPages {

    private InMemoryPages() {
    }

    public static <T> Page<T> fromOrderedSnapshot(
        List<T> orderedItems,
        Pageable pageable
    ) {
        Objects.requireNonNull(orderedItems, "orderedItems");
        Objects.requireNonNull(pageable, "pageable");

        List<T> snapshot = new ArrayList<>(orderedItems);
        long total = snapshot.size();

        if (pageable.isUnpaged()) {
            return new PageImpl<>(snapshot, pageable, total);
        }

        long offset = pageable.getOffset();

        if (offset >= total) {
            return new PageImpl<>(List.of(), pageable, total);
        }

        int fromIndex = (int) offset;
        int toIndex = (int) Math.min(
            total,
            offset + (long) pageable.getPageSize()
        );

        List<T> content = new ArrayList<>(
            snapshot.subList(fromIndex, toIndex)
        );

        return new PageImpl<>(content, pageable, total);
    }
}
```

### 5.1. Vì sao giữ offset ở kiểu long?

`Pageable.getOffset()` trả về `long`, trong khi index của list dùng `int`.

Không ép kiểu offset ngay từ đầu. Hàm kiểm tra `offset >= total` trước; khi còn nằm trong list Java hữu hạn, offset mới được chuyển thành index.

Phép cộng giới hạn cũng dùng `long` để tránh thực hiện phép cộng `int` rồi mới chuyển kiểu.

Ví dụ dùng `PageRequest` hợp lệ bảo đảm page number không âm và page size dương. Nếu tự triển khai `Pageable`, caller cũng phải giữ những bất biến tương ứng.

### 5.2. Ví dụ một trang cuối chưa đầy

```java
List<Integer> orderedSnapshot = List.of(
    10, 20, 30, 40, 50, 60, 70, 80
);

Page<Integer> page = InMemoryPages.fromOrderedSnapshot(
    orderedSnapshot,
    PageRequest.of(2, 3)
);
```

Kết quả:

```text
content              = [70, 80]
number               = 2
size                 = 3
numberOfElements     = 2
totalElements        = 8
totalPages           = 3
hasNext              = false
```

Danh sách đã có thứ tự trước khi gọi hàm. Hàm không tự sắp các số dựa trên metadata.

### 5.3. Trang vượt phạm vi vẫn giữ tổng thực

Với cùng snapshot:

```java
Page<Integer> page = InMemoryPages.fromOrderedSnapshot(
    orderedSnapshot,
    PageRequest.of(4, 3)
);
```

Nội dung rỗng nhưng tổng vẫn là 8. Page number vẫn phản ánh yêu cầu trang 4, không tự đổi thành trang cuối.

Ứng dụng cần quyết định chính sách API: trả trang rỗng hay báo yêu cầu ngoài phạm vi. Đừng âm thầm thay page number trong metadata mà không thay hợp đồng.

### 5.4. Copy container không phải snapshot transaction của nguồn

`new ArrayList<>(orderedItems)` tạo bản sao container để xử lý ổn định hơn trong hàm. Nó không tạo transaction cho nguồn dữ liệu, không khóa nguồn và không deep-copy từng phần tử.

Caller cần cung cấp danh sách có thể được sao chép an toàn. Nếu phần tử mutable bị thay đổi đồng thời, một bản sao list không làm toàn bộ object graph bất biến.

Các implementation kết quả không nên được dùng như danh sách mutable để thêm/xóa/sắp lại qua `getContent()`. Hãy chuẩn bị nội dung trước khi đóng gói.

### 5.5. Không dùng như cách phân trang database mặc định

Tải hàng triệu bản ghi rồi mới cắt bằng `subList` có thể cho một lát dữ liệu đúng về vị trí, nhưng chi phí đọc, bộ nhớ và độ trễ rất lớn.

Khi nguồn có khả năng phân trang, hãy đẩy giới hạn dữ liệu xuống nguồn. Helper trong bộ nhớ phù hợp khi toàn bộ tập hữu hạn đã có sẵn theo thiết kế.

## 6. PageImpl có thể thích nghi total

`PageImpl` không luôn coi `total` đầu vào là giá trị bất biến tuyệt đối. Constructor có cơ chế thích nghi tổng trong một số tình huống nội dung cho thấy đang ở vùng trang cuối, nhằm giảm bất nhất giữa nội dung và tổng.

Ví dụ điển hình:

```text
request: page = 2, size = 10, offset = 20
content: 5 phần tử
total được truyền: 23
```

Trong cơ chế constructor này, tổng có thể được điều chỉnh thành:

```text
offset + số phần tử thực tế = 20 + 5 = 25
```

Vì vậy, đừng thiết kế mã dựa trên giả định `getTotalElements()` luôn bằng nguyên đối số thứ ba trong mọi trường hợp.

### 6.1. Thích nghi không phải đếm lại nguồn

Constructor không mở query đếm và không biết trạng thái thật của database. Nó chỉ dùng thông tin được truyền vào theo quy tắc của implementation.

Nó không thể sửa mọi lỗi, chẳng hạn:

- Total được đếm từ tenant khác.
- Content bị lọc bớt sau khi đã lấy một cửa sổ dữ liệu.
- Query join trả nhiều dòng cho một đơn hàng.
- Total là số ước lượng nhưng API lại cam kết chính xác.
- Thứ tự hoặc offset của nội dung không khớp `Pageable`.

Nếu caller phụ thuộc chi tiết thích nghi, cần đối chiếu implementation/version của dự án. Về thiết kế, nên cung cấp metadata nhất quán ngay từ nguồn.

### 6.2. Nội dung rỗng không chứng minh tổng bằng 0

Một trang nằm sau trang cuối có thể rỗng trong khi toàn bộ tập có nhiều phần tử. Cơ chế thích nghi không phải quy tắc luôn thay total bằng offset khi content rỗng.

Ví dụ, với tổng 25 và yêu cầu trang quá xa, có thể tạo page rỗng giữ tổng 25.

`Page.empty(pageable)` phù hợp khi cần một page rỗng với tổng 0. Không dùng nó thay cho mọi trang rỗng ngoài phạm vi nếu API cần bảo toàn tổng đã biết khác 0.

### 6.3. Tổng không nhất quán làm điều hướng sai nghĩa

Nếu truyền total lớn nhưng content ít vì truy vấn sai, page có thể tiếp tục báo còn trang theo tổng. Nếu truyền total quá nhỏ để che việc chưa đếm, metadata cũng không còn đại diện cho toàn bộ tập.

`PageImpl` là một implementation kết quả, không phải lớp xác minh nghiệp vụ của tất cả đầu vào.

## 7. Chuẩn bị hợp đồng nguồn cho truy vấn tùy chỉnh

Để tập trung vào Commons thay vì cú pháp SQL/JSON riêng của store, giả sử ứng dụng có một port tự triển khai:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.domain.Sort;

public record OrderRow(
    long id,
    Instant createdAt,
    BigDecimal total
) {
}

interface OrderReadPort {

    List<OrderRow> fetch(
        String tenantId,
        String status,
        long offset,
        int limit,
        Sort sort
    );

    long count(String tenantId, String status);
}
```

Các ví dụ record giả định Java 17 trở lên. Package, implementation và cấu hình kết nối được lược bỏ.

Port này không kế thừa `Repository` và không được kỳ vọng tự sinh query từ tên. Implementation có thể dùng template/client phù hợp hoặc gọi một nguồn bên ngoài.

Hợp đồng cần bảo đảm:

- `fetch` trả tối đa `limit` phần tử, không trả null container.
- Offset áp dụng sau các điều kiện tenant/status và logic tập dữ liệu cần thiết.
- Nội dung có đúng thứ tự mà `sort` mô tả.
- `count` đếm cùng tập logic, không tính riêng cửa sổ hiện tại.
- Kiểu dữ liệu, mapping và cơ chế giới hạn phù hợp store.
- Không lọc bớt tùy tiện ở service sau khi nguồn đã chọn cửa sổ.

Trong ứng dụng thật, điều kiện có thể còn gồm quyền truy cập, thời gian, từ khóa hoặc trạng thái xóa mềm. Chúng phải được áp dụng nhất quán cho dữ liệu và tổng.

## 8. Tự tạo Page và Slice từ một nguồn có giới hạn dữ liệu

Service minh họa sử dụng `OrderReadPort` ở trên. Ví dụ chỉ nhận yêu cầu paged; nó từ chối unpaged để không vô tình tải toàn bộ dữ liệu từ một nguồn lớn.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.SliceImpl;

public class CustomOrderPaging {

    private final OrderReadPort port;

    public CustomOrderPaging(OrderReadPort port) {
        this.port = Objects.requireNonNull(port, "port");
    }

    public Page<OrderRow> readPage(
        String tenantId,
        String status,
        Pageable pageable
    ) {
        requirePaged(pageable);

        int size = pageable.getPageSize();

        List<OrderRow> content = Objects.requireNonNull(
            port.fetch(
                tenantId,
                status,
                pageable.getOffset(),
                size,
                pageable.getSort()
            ),
            "fetch result"
        );

        if (content.size() > size) {
            throw new IllegalStateException(
                "Source returned more than the requested limit"
            );
        }

        long total = port.count(tenantId, status);

        if (total < 0) {
            throw new IllegalStateException(
                "Source returned a negative total"
            );
        }

        return new PageImpl<>(content, pageable, total);
    }

    public Slice<OrderRow> readSlice(
        String tenantId,
        String status,
        Pageable pageable
    ) {
        requirePaged(pageable);

        int size = pageable.getPageSize();
        int fetchLimit = Math.addExact(size, 1);

        List<OrderRow> fetched = Objects.requireNonNull(
            port.fetch(
                tenantId,
                status,
                pageable.getOffset(),
                fetchLimit,
                pageable.getSort()
            ),
            "fetch result"
        );

        if (fetched.size() > fetchLimit) {
            throw new IllegalStateException(
                "Source returned more than the requested limit"
            );
        }

        boolean hasNext = fetched.size() > size;

        List<OrderRow> content = new ArrayList<>(
            fetched.subList(0, Math.min(fetched.size(), size))
        );

        return new SliceImpl<>(content, pageable, hasNext);
    }

    private static void requirePaged(Pageable pageable) {
        Objects.requireNonNull(pageable, "pageable");

        if (pageable.isUnpaged()) {
            throw new IllegalArgumentException(
                "A paged request is required"
            );
        }
    }
}
```

Kích thước trang cần được giới hạn theo chính sách API trước khi gọi service. `Math.addExact` phát hiện tràn số nếu phép lấy dư không còn biểu diễn được bằng `int`.

Ví dụ không ngầm mở transaction. Nếu cần ranh giới đọc nhất quán, implementation ứng dụng phải thiết kế nó theo store đang dùng.

### 8.1. Nhánh Page cần tổng của cùng tập dữ liệu

`readPage` lấy một cửa sổ rồi lấy tổng. Metadata chỉ đúng khi hai phép đọc nói về cùng tập logic và kết quả phù hợp yêu cầu nhất quán.

Nếu count bỏ điều kiện tenant, trạng thái hoặc quyền truy cập, total sai ngay cả khi content đúng.

Nếu content là kết quả khử trùng lặp hay nhóm, count phải có cùng đơn vị phần tử. Không lấy số dòng vật lý làm tổng cho một page chứa đối tượng gốc duy nhất.

### 8.2. Nhánh Slice dùng phần tử nhìn trước

Giả sử size bằng 3 và nguồn trả:

```text
[7, 6, 5, 4]
```

Thuật toán tạo:

```text
content = [7, 6, 5]
hasNext = true
```

Phần tử 4 là bằng chứng còn ít nhất một phần tử phía sau, không thuộc nội dung slice hiện tại.

Yêu cầu tiếp theo vẫn tăng offset theo size là 3, không tăng theo số lấy dư là 4. Nếu tăng theo `size + 1`, phần tử nhìn trước có thể bị bỏ qua.

Nếu nguồn trả đúng 3 phần tử khi đã được yêu cầu tối đa 4 và nguồn hoàn tất cửa sổ đúng hợp đồng, không có phần tử nhìn trước; `hasNext` là false.

### 8.3. Vì sao không chỉ kiểm tra content.size() == size?

Một trang có đúng 20 phần tử có thể là:

- 20 phần tử cuối của toàn bộ tập.
- 20 phần tử đầu và vẫn còn dữ liệu.

Chỉ số lượng 20 không phân biệt được hai tình huống. Lấy dư một phần tử hoặc sử dụng metadata tiếp tục đáng tin cậy từ nguồn mới giải quyết được điều đó.

### 8.4. Nguồn phải hoàn tất cửa sổ được yêu cầu

Thuật toán lấy dư giả định nguồn trả đủ số phần tử có sẵn trong giới hạn và không tự dừng sớm mà giấu việc còn dữ liệu.

Nếu nguồn trả ít hơn limit do timeout, transport bị cắt hoặc một giới hạn nội bộ khác, không được coi đó là một kết quả hoàn tất bình thường để kết luận đã hết.

Với API từ xa có continuation token hoặc cờ riêng, phải hiểu hợp đồng nguồn. “Ít phần tử hơn size” không phải quy tắc hết dữ liệu áp dụng cho mọi giao thức.

## 9. Tổng và nội dung có thể lệch do hai lần đọc

Ngay cả khi query dữ liệu và count dùng cùng bộ lọc, dữ liệu có thể thay đổi giữa hai lần đọc:

```text
1. Lấy content.
2. Một tiến trình khác thêm/xóa dữ liệu.
3. Đếm total.
4. Tạo PageImpl.
```

Khi đó, hai giá trị không nhất thiết phản ánh cùng thời điểm.

Một transaction read-only không tự bảo đảm mọi lần đọc có cùng snapshot trên mọi store và mọi isolation level. Nếu API cần tính nhất quán mạnh hơn, phải chọn cơ chế phù hợp của nguồn dữ liệu.

Cơ chế thích nghi total của `PageImpl` không thay thế transaction/snapshot và không chứng minh kết quả đã nhất quán tuyệt đối.

### 9.1. Khi total chỉ là ước lượng

Một search engine hoặc dịch vụ bên ngoài có thể trả tổng ước lượng, tổng có ngưỡng hoặc tổng từ cache. Không nên đưa con số đó vào API như một tổng chính xác nếu chưa làm rõ nghĩa.

`Page` không có sẵn một cờ chung diễn đạt mọi dạng độ chính xác của nguồn. Có thể cần response DTO riêng với thông tin “ước lượng”, “tối thiểu” hoặc chính sách tổng theo hệ thống.

Nếu chỉ cần tải tiếp, slice có thể phù hợp hơn việc cố tạo một page với tổng chưa biết.

## 10. Có thể dùng PageableExecutionUtils khi điều kiện phù hợp

Spring Data Commons cung cấp utility hỗ trợ dựng page với một supplier lấy tổng:

```java
import org.springframework.data.support.PageableExecutionUtils;

Page<OrderRow> page = PageableExecutionUtils.getPage(
    content,
    request,
    () -> port.count(tenantId, status)
);
```

Ví dụ giả định content đã được lấy đúng cửa sổ, không vượt kích thước yêu cầu và cùng bộ lọc với count.

Utility có thể tránh gọi supplier khi số phần tử và vị trí cho phép suy ra tổng theo các điều kiện của implementation. Nó không nhất thiết gọi count trong mọi trường hợp.

### 10.1. Điều kiện trước khi suy ra tổng

Không áp dụng cách suy này cho dữ liệu đã bị cắt bớt tùy tiện sau truy vấn.

Ví dụ, nguồn trả đủ 20 đơn nhưng service loại 8 đơn bằng một điều kiện chưa được đưa xuống query. Content còn 12 không có nghĩa đây là trang cuối của tập logic mong muốn.

Tương tự, nếu một cơ chế join/deduplicate khiến số đối tượng trả về không phản ánh cửa sổ logic như giả định, phải kiểm tra kỹ trước khi dựa vào suy luận từ độ dài content.

Trang rỗng ở một offset lớn cũng không chứng minh tổng bằng offset. Muốn giữ tổng chính xác trong trường hợp đó có thể vẫn cần count.

### 10.2. Utility không thay thế việc lấy dữ liệu

`PageableExecutionUtils` không tự thực thi truy vấn nội dung, không áp dụng filter và không tạo snapshot. Supplier cũng cần trả tổng hợp lệ theo đúng hợp đồng.

Đừng truyền danh sách có cả phần tử nhìn trước của slice vào utility rồi coi đó là content page bình thường. Content page phải được chuẩn bị đúng kích thước và ý nghĩa trước.

## 11. Chuyển sang DTO: dùng map khi số phần tử không đổi

Giả sử có DTO:

```java
public record OrderView(long id, BigDecimal total) {
}
```

Có thể chuyển đổi:

```java
Page<OrderView> viewPage = page.map(
    row -> new OrderView(row.id(), row.total())
);

Slice<OrderView> viewSlice = slice.map(
    row -> new OrderView(row.id(), row.total())
);
```

`map` giữ ý nghĩa phân trang và metadata của kết quả trong phép chuyển đổi một-một. Không cần tự dựng lại mọi field chỉ để đổi kiểu phần tử.

### 11.1. Filter không phải map

Nếu xóa một số phần tử trong content rồi dùng lại total/hasNext cũ, cần xem lại hợp đồng:

- Content còn đại diện cho đúng cửa sổ của tập đã lọc không?
- Total có còn nói về những phần tử caller được nhận không?
- Có làm trang ngắn dù dữ liệu hợp lệ còn ở phía sau không?
- Cờ hasNext có được tính theo cùng logic không?

Nếu bộ lọc là một phần của tập kết quả, nên áp dụng nó trước offset/limit và trước count.

`map` cũng không tự sửa metadata đã sai từ nguồn. Nó bảo toàn hợp đồng hiện có của kết quả, không xác minh lại nguồn dữ liệu.

## 12. Khi nào tự tạo kết quả là phù hợp?

### 12.1. Repository fragment hoặc template/client riêng

Một truy vấn phức tạp có thể được viết trong phần triển khai riêng. Ứng dụng lấy content và count, hoặc content có nhìn trước, rồi trả hợp đồng `Page`/`Slice` cho tầng trên.

Việc tự đóng gói không làm module có thêm khả năng truy vấn. SQL, CQL, Cypher, JSON hoặc cơ chế tìm kiếm thực tế vẫn phải được nguồn hỗ trợ.

### 12.2. Bọc phản hồi từ dịch vụ từ xa

Một dịch vụ trả items cùng tổng chính xác có thể được chuyển thành page nếu các khái niệm tương thích:

- Chỉ số trang bắt đầu từ 0 hay 1.
- Offset và kích thước trang được hiểu thế nào.
- Items có thực sự là cửa sổ mà metadata mô tả không.
- Thứ tự nào đã được áp dụng.
- Tổng là chính xác, ước lượng hay có ngưỡng.
- Dịch vụ có tự đổi trang/size hoặc giới hạn kết quả không.

Ví dụ, nguồn dùng trang bắt đầu từ 1 trả trang 3, size 10. Khi tương thích đầy đủ, mô tả Commons tương ứng có page number bằng 2.

Không chỉ thay đổi con số trong response mà bỏ qua việc nguồn đã lấy dữ liệu theo một hợp đồng khác.

### 12.3. Nguồn dùng continuation token

Một continuation token không mặc nhiên là offset hoặc page number. Nếu client cần token để đi tiếp, `Pageable.next()` theo số trang không tự tạo được token đó.

Có thể cần response DTO giữ token hoặc một hợp đồng scroll mà module hỗ trợ. Chỉ dùng `SliceImpl` khi cách lấy tiếp của ứng dụng đã được mô tả đầy đủ; cờ `hasNext` không mang toàn bộ trạng thái continuation của một giao thức bất kỳ.

### 12.4. Tổng hợp nhiều nguồn

Nếu hai nguồn đều phân trang riêng, lấy “trang 2” của mỗi nguồn rồi ghép và sort không tự cho “trang 2” của tập hợp chung.

Cần xác định thứ tự toàn cục, cách merge, khử trùng lặp và vị trí cửa sổ trên tập chung. Tổng cũng chỉ cộng được theo nghĩa đơn giản khi các tập thực sự đáp ứng điều kiện phù hợp, chẳng hạn không trùng và cùng đơn vị phần tử.

`PageImpl` không giải bài toán phân trang phân tán này. Nó chỉ đóng gói một kết quả sau khi ứng dụng đã giải quyết đúng.

## 13. Tách mô hình phân trang nội bộ khỏi hợp đồng JSON

`PageImpl` và `SliceImpl` hữu ích trong Java, nhưng không nên coi toàn bộ cấu trúc serialization nội bộ của chúng là schema API công khai mà ứng dụng kiểm soát.

Có thể tạo DTO response với những field đã lựa chọn. Ví dụ:

```java
import java.util.List;

import org.springframework.data.domain.Page;

public record PageResponse<T>(
    List<T> items,
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean hasNext
) {
    public static <T> PageResponse<T> from(Page<T> source) {
        return new PageResponse<>(
            source.getContent(),
            source.getNumber(),
            source.getSize(),
            source.getTotalElements(),
            source.getTotalPages(),
            source.hasNext()
        );
    }
}
```

API cần nói rõ field `page` bắt đầu từ 0 trong ví dụ. Nếu giao diện công khai dùng cách đánh số khác, chuyển đổi ở ranh giới một cách nhất quán.

Với slice response, chỉ nên công bố metadata thực sự biết được, chẳng hạn items, size và hasNext. Không thêm `totalElements` giả để làm schema giống page.

DTO không sửa nội dung hoặc metadata sai ở phía dưới. Nó chỉ giúp hợp đồng truyền dữ liệu rõ ràng và do ứng dụng lựa chọn.

## 14. Chẩn đoán kết quả tự tạo

| Hiện tượng | Nguyên nhân có thể có | Điều cần kiểm tra |
|---|---|---|
| Page size là 20 nhưng có 500 phần tử | Truyền toàn bộ danh sách vào constructor | Content đã được cắt trước chưa |
| Trang cuối luôn báo còn dữ liệu | Dùng `content.size() == size` làm bằng chứng duy nhất | Có phần tử nhìn trước hoặc metadata nguồn không |
| Slice có size + 1 phần tử | Quên bỏ phần tử nhìn trước | Trim trước khi tạo `SliceImpl` |
| Mỗi lần đi tiếp bị mất một phần tử | Tăng offset theo size + 1 | Bước di chuyển phải theo size logic |
| Total bằng số phần tử trang | Nhầm tổng với độ dài content | Tổng của toàn bộ tập đã lọc |
| Total khác đối số truyền vào | Constructor thích nghi tổng ở tình huống tương ứng | Offset, số phần tử và quy tắc `PageImpl` |
| Trang rỗng làm total thành 0 dù tập có dữ liệu | Dùng `Page.empty` sai nghĩa | Đây là tập rỗng hay trang ngoài phạm vi |
| Metadata ghi sort nhưng content không đúng thứ tự | Chỉ gắn Sort vào wrapper | Nguồn hoặc xử lý trước đó đã sort thật chưa |
| Nội dung đúng nhưng tổng lộ dữ liệu khác tenant | Count thiếu điều kiện phạm vi | Bộ lọc và quyền cho cả hai truy vấn |
| Trang ngắn bất thường dù còn nhiều dữ liệu | Lọc/deduplicate sau khi lấy cửa sổ | Thứ tự các bước xử lý |
| Các lần đọc lệch nhau khi dữ liệu thay đổi | Content và count không cùng snapshot | Mức nhất quán và transaction của nguồn |

### 14.1. Bất biến cần giữ trong trường hợp paged thông thường

- Content không null.
- Page number không âm, page size dương theo yêu cầu hợp lệ.
- Content không vượt quá kích thước logic của page/slice.
- Total không âm và đếm đúng loại phần tử.
- `Pageable` mô tả cửa sổ và thứ tự thực sự được dùng.
- Cờ đi tiếp có bằng chứng từ nguồn hoặc từ thuật toán hợp lệ.
- Bộ lọc và phạm vi truy cập thống nhất trước giới hạn dữ liệu.

Không coi việc khởi tạo object thành công là xác nhận tất cả bất biến đã đúng.

### 14.2. Dữ liệu kỳ vọng để kiểm chứng

Với snapshot `[10, 20, 30, 40, 50, 60, 70, 80]`:

| Yêu cầu | Content mong đợi | Total | Has next |
|---|---|---:|---|
| Page 0, size 3 | `[10, 20, 30]` | 8 | true |
| Page 2, size 3 | `[70, 80]` | 8 | false |
| Page 4, size 3 | `[]` | 8 | false |
| Unpaged | Toàn bộ snapshot | 8 | false |

Với slice có size 3, nguồn hoàn tất cửa sổ lấy tối đa 4:

| Số phần tử nguồn trả | Số phần tử content | Has next |
|---:|---:|---|
| 0 | 0 | false |
| 2 | 2 | false |
| 3 | 3 | false |
| 4 | 3 | true |

Đây là các kỳ vọng để kiểm chứng trong dự án thực tế. Cần bổ sung trường hợp bộ lọc, sort, tenant, thay đổi dữ liệu và cơ chế nguồn đang sử dụng.

## 15. Bài tập vận dụng

### Bài tập 1: Constructor có phân trang không?

Một danh sách có 100 phần tử được truyền vào:

```java
new PageImpl<>(allRows, PageRequest.of(1, 10), 100);
```

Có tự nhận được phần tử thứ 11 đến 20 không?

**Gợi ý lời giải:** Không. Content vẫn là danh sách được truyền vào. Cần lấy cửa sổ đúng từ nguồn hoặc tự cắt snapshot trước khi đóng gói.

### Bài tập 2: Có đúng size thì còn trang sau?

Nguồn trả đúng 20 phần tử khi chỉ được yêu cầu 20. Có thể khẳng định `hasNext = true` không?

**Gợi ý lời giải:** Không. Có thể đây chính là 20 phần tử cuối. Cần lấy dư một phần tử hoặc dùng thông tin đi tiếp đáng tin cậy của nguồn.

### Bài tập 3: Sửa lỗi bỏ qua phần tử nhìn trước

Ứng dụng lấy 21 phần tử cho slice size 20, trả 20 phần tử đầu rồi tăng offset thêm 21.

**Gợi ý lời giải:** Offset tiếp theo cần tăng theo 20 phần tử logic đã trả. Phần tử thứ 21 là phần tử nhìn trước và phải còn cơ hội xuất hiện ở lần lấy tiếp theo.

### Bài tập 4: Total bị điều chỉnh

Request có offset 20, size 10; content có 5 phần tử; total đầu vào là 23. Vì sao `getTotalElements()` có thể là 25?

**Gợi ý lời giải:** `PageImpl` có cơ chế thích nghi tổng theo nội dung trong tình huống cuối trang tương ứng. Nó không đếm lại database, nên vẫn cần kiểm tra vì sao content và tổng ban đầu lệch nhau.

### Bài tập 5: Trang rỗng và tổng khác 0

Toàn bộ tập có 8 phần tử, caller yêu cầu page 4 với size 3. Nên luôn dùng `Page.empty(request)` không?

**Gợi ý lời giải:** Không nếu API cần giữ tổng 8. Có thể tạo `PageImpl` với content rỗng, request hiện tại và tổng đã biết. Trang ngoài phạm vi khác với toàn bộ tập rỗng.

### Bài tập 6: Filter sau khi lấy trang

Nguồn trả 20 đơn rồi service loại 7 đơn chưa đủ quyền. Count vẫn đếm tất cả đơn. Có thể giữ metadata cũ không?

**Gợi ý lời giải:** Không đáp ứng hợp đồng tập kết quả theo quyền. Điều kiện quyền cần được áp dụng trước cửa sổ và trong nguồn tổng, hoặc cần thiết kế một cách lấy dữ liệu khác bảo đảm cùng ý nghĩa.

### Bài tập 7: Đổi sang DTO

Muốn đổi mỗi `OrderRow` thành một `OrderView`, giữ nguyên số phần tử, request và metadata. Có cần tự dựng lại `PageImpl` không?

**Gợi ý lời giải:** Thường có thể dùng `page.map(...)` hoặc `slice.map(...)`. Việc lọc bớt phần tử lại là tình huống khác, cần xem lại tập dữ liệu và metadata.

## 16. Những điều cần ghi nhớ

- `PageImpl` và `SliceImpl` đóng gói nội dung đã chuẩn bị, không tự truy vấn hay cắt trang.
- Page cần tổng cùng tập logic; slice cần bằng chứng có phần tiếp theo.
- `getSize()` là kích thước yêu cầu, `getNumberOfElements()` là số phần tử thực tế.
- Với snapshot trong bộ nhớ, kiểm tra offset ở kiểu long trước khi chuyển sang index list.
- Với slice lấy dư, trả tối đa size phần tử và giữ bước di chuyển theo size.
- `PageImpl` có thể thích nghi total, nhưng không sửa mọi bất nhất hoặc tạo snapshot cho nguồn.
- Giữ filter, sort, đơn vị đếm và phạm vi truy cập nhất quán trước offset/limit.
- Dùng `map` cho chuyển đổi một-một; chọn DTO API riêng khi cần công bố hợp đồng metadata rõ ràng.
