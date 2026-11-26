# Giới hạn và sự kết hợp hợp lệ của Pageable, Sort và Limit

## Mục tiêu bài học

Một query method có thể cần thứ tự, số lượng tối đa hoặc một trang cụ thể. `Sort`, `Limit` và `Pageable` mô tả những nhu cầu liên quan nhưng không được ghép tùy ý trong chữ ký repository. Đặc biệt, Pageable đã chứa thông tin kích thước trang và thứ tự, nên thêm tham số Sort hoặc Limit riêng sẽ tạo ra các nguồn điều khiển chồng lặp.

Sau bài học, bạn có thể:

- Phân biệt sắp xếp, giới hạn số lượng và phân trang có vị trí.
- Chọn tổ hợp tham số đặc biệt hợp lệ cho query method.
- Dùng `Limit.of(...)` và `Limit.unlimited()` trong dòng phiên bản hỗ trợ.
- Phân biệt giới hạn động với keyword `Top`/`First` trong tên phương thức.
- Thiết kế giới hạn đầu vào mà không tạo chữ ký repository không hợp lệ.

Các quy tắc kết hợp trong bài áp dụng cho query method được hạ tầng Spring Data xử lý. Chúng không phải lệnh cấm một phương thức Java tùy ý có các tham số đó. Fragment do ứng dụng tự triển khai có thể có hợp đồng riêng, nhưng việc chuyển yêu cầu xuống store vẫn cần được giải quyết rõ ràng.

## 1. Ba abstraction mô tả ba việc

| Abstraction | Thông tin chính | Có vị trí trang/offset? | Có thứ tự? |
| --- | --- | --- | --- |
| `Sort` | Các tiêu chí sắp xếp và hướng | Không | Có |
| `Limit` | Số kết quả tối đa hoặc trạng thái không giới hạn | Không | Không |
| `Pageable` | Vị trí trang, kích thước trang và Sort | Có khi đã phân trang | Có thể chứa Sort |

Ví dụ ý định:

```text
Sort:
    createdAt DESC, id DESC

Sort + Limit:
    lấy tối đa 10 kết quả đầu theo thứ tự trên

Pageable:
    trang chỉ số 2, kích thước 10, theo thứ tự trên
```

Với phân trang offset thông thường, trang chỉ số 2 có size 10 bắt đầu từ offset 20. Một `Limit` bằng 10 không chứa thông tin bỏ qua hai mươi kết quả đầu.

Cùng một số 10 nhưng vai trò khác nhau:

- Limit 10 giới hạn số kết quả của một lần lấy theo hợp đồng truy vấn.
- Page size 10 xác định kích thước từng trang và tham gia tính offset.
- `Top10` là giới hạn được khai báo trong tên phương thức.

Không nên chuyển đổi qua lại chỉ vì cả ba đều có thể dẫn tới việc trả mười phần tử.

## 2. Ma trận kết hợp cho query method

Khi phiên bản và module lưu trữ hỗ trợ các abstraction tương ứng:

| Khai báo | Hợp lệ? | Lý do |
| --- | --- | --- |
| Một `Sort` | Có | Chỉ định thứ tự động |
| Một `Limit` | Có | Chỉ định giới hạn động |
| Một `Pageable` | Có | Đã mô tả vị trí, kích thước và thứ tự |
| `Sort` cùng `Limit` | Có | Một tham số chọn thứ tự, một tham số chọn số lượng |
| `Pageable` cùng `Sort` | Không | Pageable đã mang Sort |
| `Pageable` cùng `Limit` | Không | Pageable đã mang giới hạn qua kích thước trang |
| Hai `Pageable` | Không | Không có một vị trí/kích thước duy nhất để thực thi |
| Hai `Sort` | Không | Cần kết hợp thành một Sort trước khi gọi |
| Hai `Limit` | Không | Cần giải quyết thành một giới hạn trước khi gọi |
| `Top`/`First` cùng tham số `Limit` | Không | Hai cơ chế khai báo giới hạn không được dùng đồng thời |
| `Top`/`First` cùng `Sort` | Có trong query được store hỗ trợ | Giới hạn tĩnh và thứ tự động có vai trò riêng |
| `Top`/`First` cùng `Pageable` | Có trong query được store hỗ trợ | Trường hợp giới hạn truy vấn kết hợp yêu cầu trang, cần hiểu ngữ nghĩa của module |

“Hợp lệ” ở đây là hình dạng hợp đồng có thể dùng. Nó chưa bảo đảm một keyword, một thuộc tính hoặc một kiểu trả về bất kỳ được mọi store thực thi.

### Chữ ký được kiểm tra trước giá trị cụ thể

Một query method có `Pageable` và `Sort` riêng không trở nên hợp lệ chỉ vì người gọi truyền `Pageable.unpaged()` hoặc `Sort.unsorted()`.

Tương tự, `Pageable` cùng `Limit.unlimited()` vẫn là một chữ ký chứa hai loại tham số không được kết hợp theo quy tắc query method. Hạ tầng nhận diện các tham số từ chữ ký; không nên kỳ vọng nó bỏ qua một tham số chỉ vì giá trị lần gọi này có vẻ không làm gì.

## 3. Chuẩn bị đúng phiên bản cho Limit

`org.springframework.data.domain.Limit` có từ dòng Spring Data Commons 3.2. Module lưu trữ và bộ dependency của dự án cần có khả năng hỗ trợ tương ứng; không chỉ thêm riêng một JAR Commons mới vào một bộ Spring Data cũ chưa tương thích.

Các ví dụ cơ bản:

```java
import org.springframework.data.domain.Limit;

Limit ten = Limit.of(10);
Limit unlimited = Limit.unlimited();
```

`Limit` không chứa số trang hoặc một cursor tiếp tục. Nó cũng không chứa `Sort`.

Có thể phân biệt trạng thái trước khi đọc mức tối đa:

```java
if (limit.isLimited()) {
    int maximum = limit.max();
    // Dùng maximum theo hợp đồng adapter.
} else {
    // Nhánh không giới hạn theo abstraction Limit.
}
```

Không gọi `max()` trên một Limit không giới hạn rồi coi đó là một số đặc biệt đáng tin cậy. Trạng thái unlimited không cung cấp một mức tối đa hữu hạn để đọc theo cách đó.

### Giá trị 0 hoặc âm không thay cho unlimited

Không nên sao chép máy móc quy tắc validation của PageRequest sang mọi cách dùng Limit. PageRequest yêu cầu kích thước trang dương; abstraction Limit có hợp đồng riêng và cách diễn giải giá trị còn phải phù hợp với ngữ cảnh cùng store.

Đối với API ứng dụng cần trả từ 1 đến 100 kết quả, hãy kiểm tra rõ khoảng đó trước khi gọi `Limit.of(...)`. Không dùng `0`, `-1` hoặc một số rất lớn để ngầm biểu đạt không giới hạn; hãy dùng `Limit.unlimited()` khi thật sự muốn trạng thái ấy và khi API cho phép.

Việc tạo được một đối tượng Limit không đồng nghĩa backend chấp nhận mọi giá trị bên trong nó.

## 4. Dùng Sort và Limit cho một tập kết quả đầu

Giả sử domain sản phẩm có:

```text
Product
├── id: Long
├── tenantId: String
├── name: String
├── active: boolean
└── createdAt: Instant
```

Repository minh họa:

```java
import java.util.List;

import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Sort;
import org.springframework.data.repository.Repository;

interface RecentProductRepository extends Repository<Product, Long> {

    List<Product> findByTenantIdAndActiveTrue(
            String tenantId, Sort sort, Limit limit);
}
```

Ví dụ cần domain được mapping và module hỗ trợ derived query, Sort cùng Limit.

Lời gọi:

```java
Sort newest = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);

List<Product> products = repository.findByTenantIdAndActiveTrue(
        tenantId,
        newest,
        Limit.of(10)
);
```

Ý định là lấy tối đa mười sản phẩm hoạt động của tenant, mới nhất trước. Nếu có ít hơn mười sản phẩm phù hợp, danh sách ngắn hơn là kết quả bình thường.

Khóa phụ `id` giúp xác định thứ tự giữa các sản phẩm có cùng thời điểm tạo, nếu id duy nhất trong phạm vi kết quả.

### 4.1. Có giới hạn nhưng không có thứ tự

Một phương thức chỉ nhận Limit có thể biểu đạt giới hạn số lượng, nhưng chưa yêu cầu “mới nhất”, “rẻ nhất” hay “ưu tiên cao nhất”. Nếu backend không có thứ tự được query xác lập, tập đầu được chọn không có hợp đồng nghiệp vụ tương ứng.

Nếu yêu cầu là top theo một tiêu chí, hãy thể hiện cả thứ tự. Đổi giới hạn không tự tạo thứ tự.

### 4.2. Lặp lại Limit không tạo trang tiếp theo

Gọi cùng query với cùng Sort và `Limit.of(10)` lần nữa không có nghĩa là lấy mười sản phẩm tiếp theo. Trong dữ liệu ổn định, bạn vẫn đang yêu cầu cùng phần đầu của tập kết quả.

Để đi tiếp, cần một cơ chế vị trí như Pageable hoặc scroll/cursor được store hỗ trợ. Limit chỉ mang số lượng, không giữ trạng thái đã đọc.

### 4.3. Không suy ra hasNext từ danh sách vừa đầy

Một List có đúng mười phần tử khi giới hạn là mười chưa chứng minh còn phần tử thứ mười một. Nếu cần metadata còn dữ liệu tiếp theo, chọn hợp đồng như Slice hoặc cơ chế scroll phù hợp, thay vì tự gán `hasNext = list.size() == limit` như một kết luận chắc chắn.

## 5. Dùng Pageable cho yêu cầu có vị trí

Repository:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

interface ProductPageRepository extends Repository<Product, Long> {

    Page<Product> findByTenantIdAndActiveTrue(
            String tenantId, Pageable pageable);
}
```

Yêu cầu trang thứ ba theo cách người dùng đếm từ 1:

```java
import org.springframework.data.domain.PageRequest;

PageRequest pageable = PageRequest.of(2, 10, newest);

Page<Product> page = repository.findByTenantIdAndActiveTrue(
        tenantId, pageable);
```

PageRequest đã chứa:

```text
pageIndex = 2
pageSize  = 10
offset    = 20
sort      = createdAt DESC, id DESC
```

Vì vậy, không cần thêm một tham số Limit bằng 10 hoặc một Sort giống `newest` vào chữ ký phương thức này.

### 5.1. Chữ ký sai: Pageable cùng Sort

```java
// Không dùng làm query method do Spring Data suy diễn.
Page<Product> findByTenantIdAndActiveTrue(
        String tenantId, Pageable pageable, Sort sort);
```

Cách giải quyết là đưa Sort vào Pageable trước lời gọi:

```java
Pageable request = PageRequest.of(pageIndex, pageSize, requestedSort);
```

Nếu cần ghép nhiều Sort, dùng `.and(...)` theo đúng ưu tiên để tạo một Sort cuối cùng, rồi đặt nó vào PageRequest.

### 5.2. Chữ ký sai: Pageable cùng Limit

```java
// Không dùng làm query method do Spring Data suy diễn.
Page<Product> findByTenantIdAndActiveTrue(
        String tenantId, Pageable pageable, Limit limit);
```

Nếu mục tiêu là page size không vượt 100, kiểm tra hoặc chuẩn hóa size trước khi tạo Pageable. Không thêm Limit riêng như một “hàng rào” chồng lên PageRequest.

### 5.3. Sort khi không phân trang

Ở dòng API hỗ trợ `Pageable.unpaged(Sort)`, có thể biểu đạt không phân trang nhưng có thứ tự trong chính Pageable:

```java
Pageable request = Pageable.unpaged(newest);
```

Đây là một Pageable duy nhất. Nó không làm cho chữ ký Pageable cộng Sort riêng trở nên hợp lệ.

Trạng thái không phân trang có thể lấy một tập lớn. Chỉ cho phép nó khi phù hợp với hợp đồng ứng dụng và khả năng xử lý kết quả, không dùng làm mặc định thay cho đầu vào trang không hợp lệ.

## 6. Top và First: giới hạn nằm trong tên phương thức

Với store hỗ trợ, các keyword `Top` và `First` biểu đạt giới hạn kết quả trong tên:

```java
List<Product> findTop10ByTenantIdAndActiveTrue(
        String tenantId, Sort sort);
```

Đây là giới hạn tĩnh mười kết quả, còn Sort được chọn tại lúc gọi.

Nếu không ghi số sau Top/First, giới hạn thường là một kết quả:

```java
Optional<Product> findFirstByTenantIdAndActiveTrueOrderByCreatedAtDescIdDesc(
        String tenantId);
```

Ví dụ cần import `java.util.Optional`. Giới hạn một kết quả ở đây đến từ `First`; Optional biểu đạt trường hợp không có sản phẩm, không tự tạo giới hạn.

### 6.1. Không dùng Top/First cùng Limit

```java
// Không dùng đồng thời keyword giới hạn và tham số Limit.
List<Product> findTop10ByTenantIdAndActiveTrue(
        String tenantId, Sort sort, Limit limit);
```

Không có hợp đồng rằng framework sẽ tự lấy giá trị nhỏ hơn giữa 10 và `limit.max()` cho chữ ký này. Chọn một cách:

- Giới hạn cố định: dùng Top/First và bỏ tham số Limit.
- Giới hạn động: bỏ Top/First, nhận Limit khi module hỗ trợ.

Việc truyền `Limit.unlimited()` vẫn không làm cho tổ hợp Top/First cùng Limit trở thành lựa chọn hợp lệ.

### 6.2. Top/First kết hợp Pageable là trường hợp khác

Một query method dạng sau có thể được hỗ trợ:

```java
Page<Product> queryTop50ByTenantIdAndActiveTrue(
        String tenantId, Pageable pageable);
```

Giới hạn khai báo trong tên và yêu cầu phân trang không bị coi là cùng tổ hợp với tham số Limit. Ý định là một truy vấn có trần kết quả tĩnh, trong đó yêu cầu trang tiếp tục xác định phần cần lấy theo hợp đồng của module.

Đây không phải lý do để mặc định thêm Top vào mọi truy vấn phân trang. Cần xác minh cách module áp dụng giới hạn, offset và metadata tổng trong đúng phiên bản, đặc biệt khi kiểu trả về là Page.

Không tự giả định `totalElements` luôn là tổng toàn bộ trước giới hạn Top, cũng không tự suy ra một công thức điều chỉnh tổng chung cho mọi store. Nếu API cần một tổng bị chặn rõ ràng ở mức nghiệp vụ, hãy kiểm tra và công bố đúng ngữ nghĩa đó.

## 7. Kiểu trả về không thay thế quy tắc tham số

| Nhu cầu | Chữ ký khái niệm có thể chọn |
| --- | --- |
| Danh sách có thứ tự, không yêu cầu giới hạn | `List<T>` với Sort |
| Tối đa K kết quả đầu theo thứ tự | `List<T>` với Sort và Limit |
| Một kết quả đầu với quy tắc chọn rõ ràng | Top/First, thứ tự phù hợp và kiểu kết quả đơn |
| Một trang cùng tổng số | `Page<T>` với Pageable |
| Một lát dữ liệu và thông tin còn lát sau | `Slice<T>` với Pageable |
| Chỉ cần nội dung của phần dữ liệu được giới hạn theo trang | `List<T>` với Pageable, nếu store hỗ trợ |

Đổi Page thành List không làm chữ ký Pageable cộng Sort trở nên hợp lệ. Đổi List thành Page cũng không tạo ra thông tin vị trí trang từ một Limit đơn lẻ.

Page cần một yêu cầu phân trang phù hợp trong hợp đồng query method tương ứng. Nó không chỉ là một lớp tùy ý để bọc danh sách đã lấy bằng Limit rồi tự có tổng số trang.

Các kiểu trả về và tham số phải cùng được store hỗ trợ. Một tổ hợp hợp lý về mặt ý định vẫn cần đúng cơ chế truy vấn của module.

## 8. Tham số đặc biệt và binding dữ liệu

Xét:

```java
List<Product> findByTenantIdAndActiveTrue(
        String tenantId, Sort sort, Limit limit);
```

Chỉ `tenantId` là đối số điều kiện nghiệp vụ trong ví dụ này. Sort và Limit được nhận diện theo vai trò tham số đặc biệt.

Không cần tạo các field giả `sort`, `limit` trong domain hoặc thêm phần `AndLimit` vào tên phương thức. Với query khai báo, cũng không gắn `@Param("limit")` để biến abstraction Limit thành một placeholder SQL theo trực giác.

Nếu bạn tự viết một query backend có tham số giới hạn bằng scalar, đó là một hợp đồng khác cần tuân theo cú pháp và binding của backend. Không đồng nhất nó với cách hạ tầng hiểu `org.springframework.data.domain.Limit`.

Với query có positional parameter, phải phân biệt tham số bindable với tham số đặc biệt. Không đếm mù toàn bộ tham số Java để suy ra vị trí binding.

## 9. Thiết kế policy giới hạn ở service hoặc biên API

Hai endpoint có thể có nhu cầu khác nhau:

```text
Danh sách quản trị:
    cần trang, kích thước và tổng số
    → Pageable

Khối sản phẩm mới nhất:
    cần tối đa K mục, không có số trang
    → Sort + Limit hoặc một Top cố định
```

Một policy minh họa cho giới hạn động:

```java
import org.springframework.data.domain.Limit;

final class ProductLimits {

    private ProductLimits() {
    }

    static Limit fromRequestedMaximum(int maximum) {
        if (maximum < 1 || maximum > 100) {
            throw new IllegalArgumentException(
                    "Số kết quả phải nằm trong khoảng 1 đến 100");
        }

        return Limit.of(maximum);
    }
}
```

Một policy minh họa cho phân trang:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

static Pageable toPageable(int pageIndex, int pageSize, Sort sort) {
    if (pageIndex < 0) {
        throw new IllegalArgumentException("pageIndex phải từ 0 trở lên");
    }

    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException(
                "pageSize phải nằm trong khoảng 1 đến 100");
    }

    return PageRequest.of(pageIndex, pageSize, sort);
}
```

Phương thức thứ hai được đặt trong một lớp policy của ứng dụng. `sort` cần là một giá trị hợp lệ theo hợp đồng đầu vào. Giới hạn 100 là lựa chọn sản phẩm của ví dụ, không phải quy tắc mặc định của Commons.

Các policy giải quyết đầu vào trước khi gọi repository, giúp chữ ký query chỉ có một nguồn phân trang hoặc một nguồn giới hạn động.

### Nếu ứng dụng chọn clamp kích thước

Có API chọn giảm kích thước vượt mức xuống mức tối đa thay vì từ chối. Nếu dùng chính sách đó, phải công bố rõ và dùng kích thước hiệu lực để tạo PageRequest.

Thay page size cũng thay offset của cùng pageIndex. Không giữ offset tính theo size cũ rồi coi đó vẫn là cùng một yêu cầu PageRequest mới.

## 10. Chuyển Pageable sang Limit là phép mất thông tin

Trong dòng API có hỗ trợ, Pageable có thể cung cấp một Limit tương ứng với kích thước, chẳng hạn qua `toLimit()`:

```java
Limit limit = pageable.toLimit();
```

Về mặt ý nghĩa, yêu cầu đã phân trang cho ra giới hạn theo page size; yêu cầu unpaged tương ứng trạng thái không giới hạn.

Tuy nhiên, phép chuyển này không giữ:

- Offset hoặc chỉ số trang.
- Sort.
- Metadata tổng số của một Page.

Ví dụ PageRequest trang 2, size 10 có offset 20. Limit nhận được chỉ biết mức tối đa 10. Nếu dùng nó thay Pageable trong một query lấy tập đầu, bạn đã đổi vị trí dữ liệu cần lấy.

Phép chuyển có ích ở một adapter biết rõ cần xử lý riêng các phần còn lại. Nó không phải cách lách quy tắc để tiếp tục truyền cả Pageable và Limit vào một query method không cho phép tổ hợp đó.

## 11. Lỗi thường gặp và hướng xác minh

| Biểu hiện | Điểm cần kiểm tra |
| --- | --- |
| Repository không khởi tạo với Pageable và Sort | Đưa Sort vào Pageable và bỏ tham số riêng |
| Chữ ký có Pageable và Limit bị từ chối | Chọn một nguồn điều khiển kích thước; giải quyết policy trước lời gọi |
| Chữ ký có Top/First và Limit bị từ chối | Chọn giới hạn tĩnh hoặc động |
| Có hai tham số Sort | Kết hợp thành một Sort theo thứ tự ưu tiên |
| Limit được nhận diện nhưng query không chạy | Kiểm tra phiên bản, store, kiểu query và giá trị giới hạn |
| Mỗi lần gọi đều nhận cùng nhóm đầu | Limit không chứa vị trí tiếp tục |
| Danh sách đầy nhưng nút Tiếp sai | Không suy hasNext chắc chắn từ kích thước bằng giới hạn |
| Chỉ cần vài kết quả nhưng dữ liệu bị tải nhiều | Xác minh giới hạn được áp dụng ở backend, không chỉ cắt sau khi lấy |
| Đổi Pageable sang Limit làm trang sai | Đã làm mất offset và Sort |
| Metadata tổng không như kỳ vọng khi có Top và Page | Kiểm tra ngữ nghĩa giới hạn/count của module và phiên bản |

Một chữ ký hợp lệ mới chỉ là bước đầu. Cần có dữ liệu trùng tiêu chí sort chính, ít hơn K phần tử, đúng K phần tử và nhiều hơn K phần tử để kiểm tra hợp đồng thực tế.

Giới hạn số lượng không thay thế điều kiện tenant hoặc kiểm tra quyền. Nó cũng không tự làm query nhanh nếu backend vẫn phải lọc hoặc sắp xếp một tập lớn trước khi trả các phần tử đầu.

## 12. Bài tập tự kiểm tra

### Bài 1: Sort đã nằm ở đâu?

Một query method nhận `(String tenantId, Pageable pageable, Sort sort)`. Người gọi hứa luôn truyền Pageable không có sort. Chữ ký có vì thế hợp lệ không?

**Gợi ý đáp án:** Không. Quy tắc kiểm tra dựa trên chữ ký tham số đặc biệt, không dựa trên lời hứa về từng giá trị. Hãy tạo Pageable chứa Sort cần dùng.

### Bài 2: Giới hạn bảo vệ trang

Muốn page size không vượt 100, có nên thêm `Limit.of(100)` cạnh Pageable không?

**Gợi ý đáp án:** Không. Kiểm tra hoặc chuẩn hóa page size trước khi tạo Pageable. Pageable cùng Limit là tổ hợp không hợp lệ cho query method chuẩn.

### Bài 3: Top và Limit

Một phương thức có `Top10` và tham số Limit. Có thể kỳ vọng framework chọn giá trị nhỏ hơn giữa hai mức không?

**Gợi ý đáp án:** Không. Không dùng đồng thời Top/First với Limit. Chọn giới hạn tĩnh hoặc giới hạn động.

### Bài 4: Top và Pageable

Có phải vì Top cùng Limit không hợp lệ nên Top cùng Pageable cũng luôn bị cấm không?

**Gợi ý đáp án:** Không. Đây là hai trường hợp khác nhau. Top/First có thể kết hợp Pageable trong query được module hỗ trợ, nhưng cần hiểu và xác minh ngữ nghĩa giới hạn, offset và metadata tổng.

### Bài 5: Trang kế bằng Limit

Query dùng Sort cố định và Limit 20. Gọi nó lần thứ hai có tự lấy phần tử 21 đến 40 không?

**Gợi ý đáp án:** Không. Limit không mang offset hoặc cursor. Cần Pageable hay cơ chế tiếp tục phù hợp với store.

### Bài 6: Unlimited để vô hiệu hóa xung đột

Một chữ ký có Pageable và Limit. Truyền `Limit.unlimited()` có tránh được xung đột không?

**Gợi ý đáp án:** Không. Chữ ký vẫn chứa hai loại tham số không được kết hợp. Phải sửa hợp đồng repository, không chỉ thay giá trị đối số.

## Những điểm cần nhớ

- Pageable đã chứa vị trí, kích thước và Sort; không thêm Sort hoặc Limit riêng vào cùng query method.
- Sort và Limit có thể đi cùng nhau khi store hỗ trợ vì chúng mô tả hai khía cạnh khác nhau.
- Mỗi loại tham số đặc biệt chỉ nên xuất hiện một lần; giải quyết xung đột và giới hạn ứng dụng trước khi gọi repository.
- Top/First không đi cùng tham số Limit; việc kết hợp với Pageable là một trường hợp riêng cần đối chiếu module.
- Giới hạn số lượng không tạo vị trí trang, hasNext, snapshot hoặc một cơ chế phân quyền.
