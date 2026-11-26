# Pageable và PageRequest với chỉ số trang bắt đầu từ 0

## Mục tiêu bài học

Phân trang chia tập kết quả truy vấn thành những phần có kích thước được yêu cầu. Trong Spring Data Commons, `Pageable` mô tả yêu cầu phân trang, còn `PageRequest` là một implementation thường dùng để tạo yêu cầu đó. Quy tắc nền tảng là **chỉ số trang bắt đầu từ 0**.

Sau bài học, bạn có thể:

- Phân biệt yêu cầu phân trang với dữ liệu kết quả của một trang.
- Tạo `PageRequest` với chỉ số trang, kích thước và thứ tự rõ ràng.
- Tính đúng offset và tránh lỗi lệch một trang.
- Chuyển đổi giữa số trang hiển thị từ 1 và chỉ số nội bộ từ 0.
- Xử lý trang rỗng, trang vượt cuối, yêu cầu không phân trang và giới hạn đầu vào.

Các ví dụ dùng repository đồng bộ. Spring Data Commons cung cấp abstraction; module lưu trữ quyết định cách áp dụng giới hạn, offset, thứ tự và kiểu kết quả trên backend thực tế.

## 1. Yêu cầu trang và kết quả trang là hai đối tượng khác nhau

| Thành phần | Vai trò |
| --- | --- |
| `Pageable` | Hợp đồng mô tả vị trí trang, kích thước và thứ tự được yêu cầu |
| `PageRequest` | Một giá trị cụ thể implement `Pageable` |
| `Sort` | Mô tả thứ tự các phần tử trước khi lấy một phần kết quả |
| `Page<T>` | Nội dung trang cùng metadata như tổng số phần tử và tổng số trang |
| `Slice<T>` | Một lát dữ liệu với thông tin còn lát tiếp theo, không yêu cầu tổng số như Page |

Luồng sử dụng:

```text
Tạo yêu cầu Pageable
        ↓
Truyền vào repository method được store hỗ trợ
        ↓
Backend lọc, sắp xếp và lấy phần dữ liệu tương ứng
        ↓
Nhận kết quả theo kiểu trả về đã khai báo
```

Tạo một `PageRequest` không thực hiện truy vấn và không biết database có bao nhiêu phần tử. Nó chỉ mang yêu cầu. Thông tin “có trang tiếp theo không” cần được xác định từ kết quả hoặc cơ chế truy vấn phù hợp.

`PageRequest` cũng không phải một danh sách để tự cắt mọi collection Java. Việc áp dụng nó vào truy vấn là trách nhiệm của module repository.

## 2. Tạo PageRequest: trang đầu là 0

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

Pageable firstPage = PageRequest.of(0, 20);
```

Hai đối số là:

```text
0  → chỉ số trang đầu tiên
20 → số phần tử tối đa được yêu cầu cho một trang
```

Ví dụ tiếp theo:

```java
Pageable secondPage = PageRequest.of(1, 20);
Pageable thirdPage = PageRequest.of(2, 20);
```

| Trang hiển thị cho người dùng | Chỉ số truyền vào PageRequest |
| --- | --- |
| Trang 1 | `0` |
| Trang 2 | `1` |
| Trang 3 | `2` |

`PageRequest.of(1, 20)` yêu cầu trang thứ hai. Nó không phải trang đầu có hai mươi phần tử.

### Điều kiện hợp lệ của factory

- Chỉ số trang phải lớn hơn hoặc bằng `0`.
- Kích thước trang phải lớn hơn `0`.
- Khi dùng overload có `Sort`, cần truyền một đối tượng Sort hợp lệ, có thể là `Sort.unsorted()` nếu không yêu cầu thứ tự.

Các giá trị như `PageRequest.of(-1, 20)` hoặc `PageRequest.of(0, 0)` không hợp lệ và bị từ chối, thường bằng `IllegalArgumentException`. Không cần đợi tới lúc query chạy mới phát hiện những giá trị này.

`size = 0` không phải cách biểu đạt “lấy tất cả”. Trường hợp không phân trang có abstraction riêng.

## 3. Offset được tính từ chỉ số trang và kích thước

Với phân trang theo offset:

```text
 offset = pageIndex × pageSize
```

Nếu kích thước là 20:

| pageIndex | pageSize | offset | Vị trí khái niệm, đếm từ 0 |
| --- | --- | --- | --- |
| 0 | 20 | 0 | Bắt đầu từ phần tử 0 |
| 1 | 20 | 20 | Bắt đầu từ phần tử 20 |
| 2 | 20 | 40 | Bắt đầu từ phần tử 40 |
| 3 | 20 | 60 | Bắt đầu từ phần tử 60 |

Có thể đọc yêu cầu bằng API:

```java
Pageable pageable = PageRequest.of(2, 20);

int pageIndex = pageable.getPageNumber(); // 2
int pageSize = pageable.getPageSize();    // 20
long offset = pageable.getOffset();      // 40
```

`getOffset()` trả `long`. Khi cần tự tính cho một adapter riêng, phải dùng phép tính long đúng lúc, chẳng hạn `(long) pageIndex * pageSize`, thay vì nhân hai số int rồi mới chuyển kết quả đã có thể tràn sang long.

Đối với repository Spring Data thông thường, nên dùng thông tin của `Pageable` thay vì tính thêm một offset khác rồi truyền đồng thời hai nguồn vị trí có thể mâu thuẫn.

### Offset không phải định danh bản ghi

Offset 40 nghĩa là bỏ qua bốn mươi phần tử đầu của **tập đã được lọc và sắp xếp**. Nó không có nghĩa là tìm bản ghi có `id = 40` hoặc bắt đầu từ id 40.

Nếu định danh có khoảng trống, điều kiện lọc thay đổi hoặc thứ tự khác, offset vẫn được áp dụng trên tập kết quả của truy vấn đó.

## 4. Kết hợp Sort trước khi phân trang

Giả sử domain sản phẩm có các thuộc tính:

```text
Product
├── id: Long
├── tenantId: String
├── name: String
├── active: boolean
└── createdAt: Instant
```

Yêu cầu hiển thị sản phẩm mới nhất trước:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);

PageRequest pageable = PageRequest.of(0, 20, sort);
```

`Sort` nằm trong yêu cầu `PageRequest`; không cần giữ một thứ tự khác không liên quan ở bên ngoài rồi hy vọng backend tự kết hợp đúng.

Thứ tự khái niệm là:

```text
Lọc đúng phạm vi dữ liệu
        ↓
Sắp xếp theo createdAt DESC, id DESC
        ↓
Bỏ qua offset phần tử
        ↓
Lấy tối đa pageSize phần tử
```

Đây là mô hình ngữ nghĩa của yêu cầu, không phải mô tả mọi bước vật lý trong execution plan của database.

### Khóa phụ giúp xác định thứ tự

Nhiều sản phẩm có thể có cùng `createdAt`. Thêm `id` giúp phân biệt chúng nếu id duy nhất trong phạm vi truy vấn.

Chỉ dùng `PageRequest.of(0, 20)` là một yêu cầu không có tiêu chí sort từ đối tượng này. Backend không bị yêu cầu trả một thứ tự ổn định chỉ vì bạn đang phân trang.

Tên trong Sort thông thường là thuộc tính domain mà module nhận diện, chẳng hạn `createdAt`, không phải mặc nhiên tên cột SQL như `created_at`. Collation, đường dẫn lồng nhau và null ordering cần phù hợp với store.

## 5. Truyền Pageable vào query method

Repository minh họa:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

interface ProductRepository extends Repository<Product, Long> {

    Page<Product> findByTenantIdAndActiveTrue(
            String tenantId, Pageable pageable);
}
```

Ví dụ cần domain được mapping, kết nối và module repository hỗ trợ derived query cùng kiểu trả về này.

Lời gọi:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
        )
);

Page<Product> page = repository.findByTenantIdAndActiveTrue(
        tenantId, pageable);
```

Trong chữ ký trên:

- `tenantId` là giá trị dùng cho điều kiện dữ liệu.
- `ActiveTrue` là điều kiện trạng thái trong tên phương thức.
- `Pageable` là tham số đặc biệt điều khiển việc lấy trang và thứ tự.
- `Page<Product>` là hợp đồng kết quả được người gọi yêu cầu.

Không thêm phần `AndPageable` vào tên phương thức và không coi đối tượng Pageable là một giá trị để so sánh với field của Product.

### Phân trang không thay thế lọc hoặc kiểm tra quyền

Mỗi trang cần được lấy trong cùng phạm vi dữ liệu đã xác định. Nếu một endpoint cho người gọi chọn tenant tùy ý mà không có kiểm tra quyền, việc chỉ trả hai mươi phần tử không giải quyết được vấn đề truy cập dữ liệu.

Khi chuyển trang, điều kiện lọc và sort cần được giữ nhất quán theo hợp đồng truy vấn. Thay điều kiện mà vẫn dùng chỉ số trang cũ có thể đưa người dùng tới một trang rỗng trong một tập hoàn toàn khác.

## 6. Đọc Page: phân biệt kích thước yêu cầu và số phần tử thực tế

Với `Page<Product> page`, những thông tin thường dùng là:

| API | Ý nghĩa |
| --- | --- |
| `getContent()` | Danh sách phần tử trong trang |
| `getNumber()` | Chỉ số trang hiện tại, bắt đầu từ 0 |
| `getSize()` | Kích thước trang theo yêu cầu |
| `getNumberOfElements()` | Số phần tử thực tế trong nội dung trang |
| `getTotalElements()` | Tổng số phần tử khớp điều kiện theo kết quả đếm của Page |
| `getTotalPages()` | Tổng số trang theo kích thước trang |
| `hasContent()` | Nội dung trang có phần tử không |
| `hasNext()` | Có trang tiếp theo theo metadata kết quả không |
| `hasPrevious()` | Có trang trước theo vị trí trang không |

Giả sử có 53 sản phẩm khớp điều kiện và kích thước trang là 20:

| pageIndex | Số phần tử thực tế | Tổng phần tử | Tổng trang |
| --- | --- | --- | --- |
| 0 | 20 | 53 | 3 |
| 1 | 20 | 53 | 3 |
| 2 | 13 | 53 | 3 |

Trang cuối có `getSize() = 20` nhưng `getNumberOfElements() = 13`. Kích thước yêu cầu là giới hạn, không phải lời hứa luôn có đủ số phần tử đó.

Tổng số trang trong ví dụ là 3, nên các chỉ số trang có dữ liệu là 0, 1 và 2. Không lấy `getTotalPages()` làm chỉ số trang cuối.

Nếu không có dữ liệu, một Page rỗng có thể có tổng số trang bằng 0. Cần xử lý riêng trạng thái này thay vì tính một chỉ số trang cuối âm rồi tạo PageRequest từ nó.

### Nội dung và metadata tổng có thể có chi phí khác nhau

Để tạo Page, module thường cần xác định tổng số phần tử, có thể bằng một truy vấn đếm bổ sung. Không nên khẳng định mọi Page luôn thực hiện đúng hai câu query: hạ tầng có thể tối ưu hoặc bỏ phép đếm trong những tình huống đã có đủ thông tin.

Với dữ liệu thay đổi đồng thời, mức nhất quán giữa nội dung trang và tổng số còn phụ thuộc cách thực thi, transaction và backend. Page là hợp đồng cung cấp metadata, không tự tạo snapshot xuyên mọi lần đọc.

## 7. Chuyển đổi số trang từ giao diện bắt đầu từ 1

Giao diện thường hiển thị “Trang 1”, nhưng nội bộ vẫn dùng chỉ số 0. API bên ngoài có thể chọn quy ước bắt đầu từ 0 hoặc từ 1; cần công bố rõ một lựa chọn.

| Hợp đồng endpoint | Yêu cầu trang đầu | Chỉ số nội bộ |
| --- | --- | --- |
| API bắt đầu từ 0 | `page=0` | 0 |
| API bắt đầu từ 1 | `page=1` | 0 sau chuyển đổi |

Đây là hai lựa chọn hợp đồng khác nhau. Không diễn giải cùng một tham số `page=1` theo hai cách trong cùng endpoint.

### 7.1. Ví dụ endpoint nhận số trang bắt đầu từ 1

Chính sách của ứng dụng minh họa:

- `page` phải từ 1 trở lên.
- `size` phải trong khoảng 1 đến 100.
- Repository luôn nhận chỉ số bắt đầu từ 0.

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

final class ProductPageRequests {

    private ProductPageRequests() {
    }

    static Pageable fromOneBasedInput(int page, int size) {
        if (page < 1) {
            throw new IllegalArgumentException("page phải bắt đầu từ 1");
        }

        if (size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "size phải nằm trong khoảng 1 đến 100");
        }

        int pageIndex = page - 1;

        Sort sort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
        );

        return PageRequest.of(pageIndex, size, sort);
    }
}
```

Giới hạn 100 là chính sách của ví dụ, không phải giới hạn chung của PageRequest.

Gọi `fromOneBasedInput(1, 20)` tạo yêu cầu nội bộ trang 0. Gọi với trang 0 bị từ chối theo hợp đồng bên ngoài này.

### 7.2. Chỉ chuyển đổi ở một nơi

Nếu tầng web hoặc argument resolver đã được cấu hình chuyển số trang bắt đầu từ 1 sang Pageable bắt đầu từ 0, service không được trừ thêm lần nữa.

Lỗi chuyển đổi hai lần có thể biến trang đầu thành chỉ số âm hoặc khiến mọi trang bị lệch. Chọn một nơi chịu trách nhiệm chuyển đổi, rồi giữ Pageable theo quy ước nội bộ thống nhất.

Khi trả metadata ra ngoài, nếu API dùng số trang bắt đầu từ 1, có thể chuyển `page.getNumber() + 1` tại ranh giới phản hồi. Không đổi quy tắc của chính PageRequest để phù hợp với nhãn hiển thị.

## 8. Điều hướng: Pageable mới không đồng nghĩa query mới

Ví dụ:

```java
PageRequest current = PageRequest.of(0, 20, sort);

Pageable next = current.next();
Pageable previous = current.previousOrFirst();
Pageable first = current.first();
```

Các phương thức tạo yêu cầu vị trí tương ứng. Chúng chưa gọi database.

- `next()` tăng chỉ số trang theo yêu cầu hiện tại.
- `previousOrFirst()` lùi một trang, hoặc giữ ở trang đầu nếu đã ở đầu.
- `first()` tạo yêu cầu trang đầu với thông tin kích thước/thứ tự tương ứng.

`current.next()` không biết trang kế tiếp có dữ liệu hay không. Bản thân Pageable không chứa tổng số phần tử.

### Dựa vào Page khi cần quyết định có đi tiếp

```java
if (page.hasNext()) {
    Pageable nextRequest = page.nextPageable();

    Page<Product> nextPage =
            repository.findByTenantIdAndActiveTrue(
                    tenantId, nextRequest);

    // Sử dụng nextPage theo luồng của ứng dụng.
}
```

Kiểm tra `hasNext()` giúp thể hiện ý định rõ ràng. Không coi `nextPageable()` là một tín hiệu luôn có trang tiếp theo; ở biên không có trang sau, API có thể trả biểu diễn unpaged.

Tương tự, `hasPrevious()` phản ánh vị trí trang. Nó không thực hiện một query mới để kiểm tra rằng trang trước vẫn còn dữ liệu sau các thay đổi đồng thời.

### PageRequest có tính bất biến

```java
PageRequest current = PageRequest.of(0, 20, sort);
current.next();

// current vẫn là yêu cầu trang 0.
```

Cần giữ đối tượng được trả về nếu muốn dùng yêu cầu mới. Với các API như `withPage(...)` hoặc `withSort(...)` của dòng PageRequest đang sử dụng, nguyên tắc tạo giá trị mới cũng cần được giữ.

## 9. Trang rỗng và trang vượt cuối

Có ít nhất hai lý do nội dung trang rỗng:

1. Không có phần tử nào khớp điều kiện.
2. Có phần tử khớp, nhưng chỉ số yêu cầu đã vượt phần dữ liệu hiện có.

Với 53 phần tử và size 20, yêu cầu pageIndex 3 bắt đầu từ offset 60. Trong một thực thi thông thường với dữ liệu ổn định, nội dung trang đó rỗng dù tổng số phần tử vẫn là 53.

PageRequest không tự biết yêu cầu này vượt cuối để từ chối ngay tại factory. Query cần được thực thi hoặc cần có thông tin tổng phù hợp trước đó.

Ứng dụng cần định nghĩa chính sách:

| Chính sách | Hành vi |
| --- | --- |
| Cho phép trang vượt cuối | Trả nội dung rỗng cùng metadata theo hợp đồng |
| Từ chối yêu cầu vượt phạm vi | Kiểm tra ở tầng phù hợp và trả lỗi đã quy định |
| Điều hướng giao diện về một trang hợp lệ | Thực hiện có chủ đích, tránh đổi yêu cầu ngầm gây khó hiểu |

Không có yêu cầu chung rằng mọi repository phải ném lỗi khi chỉ số vượt tổng số trang.

Khi người dùng đổi bộ lọc, thường nên đưa chỉ số về trang đầu theo thiết kế giao diện. Ví dụ, trang thứ mười của toàn bộ sản phẩm có thể không tồn tại trong tập chỉ còn vài sản phẩm sau khi tìm theo tên.

## 10. `Pageable.unpaged()` và giới hạn của trạng thái không phân trang

Khi một API hỗ trợ bỏ phân trang, có thể biểu đạt rõ:

```java
Pageable pageable = Pageable.unpaged();
```

Không dùng null hoặc size 0 để thay thế cho ý định này.

`unpaged` không có đầy đủ các thông số vị trí như một PageRequest thông thường. Những lời gọi lấy số trang, kích thước hay offset trên biểu diễn unpaged có thể ném `UnsupportedOperationException`.

Với code xử lý cả hai trường hợp:

```java
if (pageable.isPaged()) {
    long offset = pageable.getOffset();
    int limit = pageable.getPageSize();

    // Dùng offset và limit cho adapter hỗ trợ phân trang.
} else {
    // Xử lý nhánh không phân trang theo hợp đồng của adapter.
}
```

Đoạn code minh họa một adapter tự xử lý yêu cầu; repository chuẩn thường đã có logic tương ứng của module.

Không phân trang có thể trả một tập lớn. Chỉ mở lựa chọn này khi phù hợp với yêu cầu và cách tiêu thụ dữ liệu; một endpoint công cộng cần giới hạn kích thước không nên vô tình chuyển đầu vào lỗi thành unpaged.

## 11. Cùng Pageable nhưng kiểu kết quả có thể khác

Không phải mọi phương thức nhận Pageable đều cần trả Page. Những hợp đồng thường gặp, khi store hỗ trợ:

| Kiểu trả về | Người gọi nhận được |
| --- | --- |
| `Page<Product>` | Nội dung và metadata tổng số phần tử/trang |
| `Slice<Product>` | Nội dung và thông tin có lát tiếp theo |
| `List<Product>` với Pageable | Phần dữ liệu bị giới hạn theo yêu cầu, không có metadata trang đầy đủ |

Ví dụ các lựa chọn độc lập:

```java
Page<Product> findByTenantId(
        String tenantId, Pageable pageable);

Slice<Product> findByTenantIdAndActiveTrue(
        String tenantId, Pageable pageable);

List<Product> findByTenantIdAndNameStartingWith(
        String tenantId, String prefix, Pageable pageable);
```

Các chữ ký cần import những kiểu tương ứng. Không thể khai báo hai phương thức giống hệt tên và danh sách tham số rồi chỉ đổi kiểu trả về để overload trong Java.

Nếu màn hình cần tổng số trang, Page phù hợp với nhu cầu đó. Nếu chỉ có nút “Tiếp”, Slice có thể đủ và tránh yêu cầu tổng số không cần thiết. Slice thường xác định còn dữ liệu tiếp theo bằng cách lấy thêm phần tử theo cơ chế của module, không cung cấp tổng số toàn bộ như Page.

Nếu lấy một List, không nên chỉ dựa vào `list.size() == pageSize` để kết luận chắc chắn còn trang sau: tập dữ liệu có thể kết thúc đúng tại một trang đầy.

## 12. Giới hạn đầu vào và chi phí offset

PageRequest kiểm tra tính hợp lệ cơ bản, nhưng không đặt ra mọi chính sách của ứng dụng.

| Điều cần quyết định | Ví dụ |
| --- | --- |
| Kích thước mặc định | 20 theo thiết kế của một màn hình |
| Kích thước tối đa | 100 theo khả năng và mục tiêu của ứng dụng |
| Chỉ số tối đa chấp nhận | Giới hạn nếu sản phẩm không cần đi tới các offset rất sâu |
| Thuộc tính sort cho phép | Một tập tên hoặc lựa chọn nghiệp vụ đã biết |
| Hành vi khi đầu vào lỗi | Từ chối rõ ràng hoặc chuẩn hóa theo hợp đồng đã công bố |

Offset lớn có thể tốn công vì backend vẫn cần xử lý hoặc đi qua một phạm vi dữ liệu đáng kể trước khi trả phần cần lấy. Chi phí cụ thể phụ thuộc index, bộ lọc, thứ tự và công nghệ lưu trữ.

`getOffset()` trả long không có nghĩa mọi backend đều hỗ trợ mọi giá trị long hoặc mọi độ sâu trang đều có hiệu năng tương đương. Với xử lý tuần tự khối lượng lớn, cần cân nhắc cơ chế scroll/keyset hoặc cursor mà store hỗ trợ.

Thứ tự có khóa phụ giúp xác định vị trí giữa các phần tử bằng nhau, nhưng dữ liệu thay đổi vẫn có thể làm offset pagination lặp hoặc bỏ qua phần tử giữa các request. Cần đánh giá riêng yêu cầu nhất quán thay vì coi phân trang như một snapshot tự động.

Các ca có ích để xác minh:

- Trang đầu 0, trang kế 1 và công thức offset.
- Đầu vào giao diện bắt đầu từ 1 chỉ được chuyển đổi một lần.
- Size âm, size 0 và size vượt giới hạn ứng dụng.
- Tập rỗng, trang cuối thiếu phần tử và trang vượt cuối.
- Nhiều phần tử trùng giá trị sắp xếp chính.
- Thay đổi bộ lọc trong khi đang ở một chỉ số trang lớn.
- Nhánh unpaged nếu API thật sự cho phép.

## 13. Bài tập tự kiểm tra

### Bài 1: Chỉ số và vị trí

`PageRequest.of(2, 15)` yêu cầu trang thứ mấy theo cách người dùng đếm từ 1, và offset là bao nhiêu?

**Gợi ý đáp án:** Trang thứ ba, offset bằng 30. Backend bắt đầu lấy sau ba mươi phần tử đầu của tập đã lọc và sắp xếp.

### Bài 2: Trang cuối

Có 45 phần tử, size 20. Các chỉ số trang có dữ liệu là gì và trang cuối có bao nhiêu phần tử?

**Gợi ý đáp án:** Các chỉ số là 0, 1, 2. Trang cuối có 5 phần tử; kích thước yêu cầu của trang vẫn là 20.

### Bài 3: Chuyển đổi hai lần

Tầng web đã nhận `page=1` theo quy ước bên ngoài và tạo Pageable có pageIndex 0. Service có nên tiếp tục trừ 1 không?

**Gợi ý đáp án:** Không. Chuyển đổi tại một ranh giới duy nhất. Nội bộ đã là chỉ số bắt đầu từ 0.

### Bài 4: Size bằng 0

Có thể dùng `PageRequest.of(0, 0)` để lấy toàn bộ dữ liệu không?

**Gợi ý đáp án:** Không. Size phải lớn hơn 0. Nếu hợp đồng cho phép không phân trang, dùng `Pageable.unpaged()` và xử lý trạng thái đó đúng cách.

### Bài 5: Có trang tiếp theo không?

Một đối tượng Pageable đang ở trang 5. Gọi `next()` có xác nhận backend đang có dữ liệu ở trang 6 không?

**Gợi ý đáp án:** Không. Nó chỉ tạo yêu cầu vị trí mới. Cần thông tin từ Page/Slice hoặc cơ chế truy vấn phù hợp để quyết định có dữ liệu tiếp theo.

### Bài 6: List vừa đủ kích thước

Query trả List có đúng 20 phần tử với size 20. Có chắc chắn còn trang sau không?

**Gợi ý đáp án:** Không. Có thể tổng dữ liệu kết thúc đúng ở phần tử cuối trang này. Chọn Slice hoặc Page nếu người gọi cần metadata điều hướng tương ứng.

## Những điểm cần nhớ

- PageRequest dùng chỉ số bắt đầu từ 0 và yêu cầu size lớn hơn 0.
- Offset bằng chỉ số trang nhân kích thước; nó không phải định danh bản ghi.
- Pageable là yêu cầu, còn Page/Slice hoặc collection là kết quả có hợp đồng riêng.
- Chuyển đổi số trang hiển thị từ 1 ở đúng một ranh giới, rồi giữ quy ước nội bộ thống nhất.
- Sort có khóa phụ, giới hạn đầu vào và khả năng của store quyết định chất lượng phân trang thực tế.
