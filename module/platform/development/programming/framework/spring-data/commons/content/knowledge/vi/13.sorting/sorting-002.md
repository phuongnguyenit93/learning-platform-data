# Thứ tự nhiều thuộc tính và cách kết hợp Sort

## Mục tiêu bài học

Một kết quả truy vấn thường cần nhiều tiêu chí sắp xếp: nhóm theo loại sản phẩm, trong mỗi loại ưu tiên giá cao hơn, rồi dùng tên và định danh để phân biệt các phần tử còn bằng nhau. Spring Data Commons biểu diễn yêu cầu đó bằng một `Sort` chứa các `Sort.Order` theo thứ tự ưu tiên.

Sau bài học, bạn có thể:

- Đọc thứ tự nhiều thuộc tính theo nguyên tắc ưu tiên từ trái sang phải.
- Tạo `Sort` có nhiều hướng tăng/giảm khác nhau.
- Kết hợp các `Sort` mà vẫn giữ đúng chính sách ưu tiên.
- Phân biệt nối tiêu chí, chọn mặc định và ghi đè tiêu chí.
- Xử lý thuộc tính trùng, thêm khóa phụ và áp dụng vào truy vấn có phân trang.

Ví dụ sử dụng abstraction của Commons. Việc store hỗ trợ sắp xếp trên một thuộc tính, một biểu thức hoặc một kiểu truy vấn vẫn cần được xác nhận với module lưu trữ cụ thể.

## 1. Một Sort là một danh sách tiêu chí có thứ tự

Giả sử domain sản phẩm có các thuộc tính:

```text
Product
├── id: Long
├── tenantId: String
├── category: String
├── price: BigDecimal
├── name: String
├── updatedAt: Instant
└── active: boolean
```

Yêu cầu của màn hình:

```text
category tăng dần
    ↓ nếu category bằng nhau
price giảm dần
    ↓ nếu price cũng bằng nhau
name tăng dần
    ↓ nếu name cũng bằng nhau
id tăng dần
```

Mỗi tiêu chí chỉ được dùng khi các tiêu chí đứng trước chưa phân biệt được hai phần tử. Đây là cách so sánh theo thứ tự từ điển, không phải cộng điểm các thuộc tính hoặc sắp xếp lại độc lập nhiều lần.

Có thể viết ý định dưới dạng:

```text
(category ASC, price DESC, name ASC, id ASC)
```

Đối với một store quan hệ có mapping tương ứng, ý định có thể được chuyển thành một mệnh đề `ORDER BY` nhiều biểu thức. Với document store, module tạo cấu trúc sort phù hợp với backend. `Sort` mô tả yêu cầu, không tự thực thi sắp xếp bằng Java comparator.

## 2. Ví dụ dữ liệu: tiêu chí đầu tiên luôn được ưu tiên

Dữ liệu minh họa:

| id | category | price | name |
| --- | --- | --- | --- |
| 101 | BOOK | 100 | Java |
| 102 | BOOK | 120 | Spring |
| 103 | BOOK | 120 | Data |
| 104 | BOOK | 120 | Data |
| 201 | TOOL | 90 | IDE |
| 202 | TOOL | 150 | Profiler |
| 203 | TOOL | 150 | Debugger |

Giả sử các chuỗi được so sánh theo thứ tự minh họa `BOOK` trước `TOOL`, và `Data` trước `Spring`. Áp dụng:

```text
category ASC, price DESC, name ASC, id ASC
```

thu được:

| Vị trí | id | category | price | name | Lý do chính |
| --- | --- | --- | --- | --- | --- |
| 1 | 103 | BOOK | 120 | Data | Trong BOOK, giá 120 đứng trước 100; Data trước Spring |
| 2 | 104 | BOOK | 120 | Data | Bằng ba tiêu chí đầu với 103, nên so id |
| 3 | 102 | BOOK | 120 | Spring | Cùng nhóm và giá, tên đứng sau Data |
| 4 | 101 | BOOK | 100 | Java | Giá thấp hơn các sản phẩm BOOK còn lại |
| 5 | 203 | TOOL | 150 | Debugger | Sau toàn bộ BOOK; trong TOOL ưu tiên giá 150 |
| 6 | 202 | TOOL | 150 | Profiler | Cùng giá với 203, tên đứng sau Debugger |
| 7 | 201 | TOOL | 90 | IDE | Giá thấp hơn trong nhóm TOOL |

Sản phẩm TOOL giá 150 không vượt lên trên BOOK giá 100, vì category là tiêu chí chính. Nếu muốn giá quyết định trước, phải đưa `price` lên trước `category`.

Quy tắc collation, phân biệt hoa thường và giá trị null có thể làm thứ tự chuỗi thực tế khác ví dụ. Cần phân biệt nguyên tắc ưu tiên tiêu chí với quy tắc so sánh một giá trị của backend.

## 3. Tạo Sort với nhiều thuộc tính

### 3.1. Dùng cùng một hướng cho nhiều thuộc tính

```java
import org.springframework.data.domain.Sort;

Sort alphabetical = Sort.by("category", "name", "id");
```

Các thuộc tính trong dạng này có hướng mặc định tăng dần:

```text
category ASC, name ASC, id ASC
```

Khi muốn cùng một hướng giảm dần:

```java
Sort newest = Sort.by(
        Sort.Direction.DESC,
        "updatedAt",
        "id"
);
```

Ý định là:

```text
updatedAt DESC, id DESC
```

Thứ tự chuỗi thuộc tính trong lời gọi là thứ tự ưu tiên, không phải một tập không có thứ tự.

### 3.2. Dùng hướng riêng cho từng thuộc tính

```java
Sort catalog = Sort.by(
        Sort.Order.asc("category"),
        Sort.Order.desc("price"),
        Sort.Order.asc("name"),
        Sort.Order.asc("id")
);
```

Dạng này biểu đạt trực tiếp yêu cầu hỗn hợp tăng/giảm. Mỗi `Order` giữ thuộc tính, hướng và những metadata liên quan của tiêu chí đó.

Nếu các tiêu chí được xây dựng thành một `List<Sort.Order>`, có thể dùng overload `Sort.by(listOfOrders)` tương ứng. Danh sách đầu vào vẫn phải có thứ tự đúng với chính sách mong muốn.

### 3.3. Tên thuộc tính thuộc mô hình domain

Trong ví dụ, `updatedAt` là tên thuộc tính domain. Nếu JPA mapping nó sang cột `updated_at`, người gọi `Sort` thông thường vẫn dùng thuộc tính domain theo hợp đồng của module.

Không tự thay tên thuộc tính bằng tên cột, chuỗi SQL hoặc biểu thức backend rồi kỳ vọng mọi store hiểu. Đường dẫn lồng nhau, alias và biểu thức sắp xếp có quy tắc riêng theo module và loại query.

## 4. Kết hợp bằng `.and()` là nối tiêu chí

Có thể chia thứ tự thành các phần có tên:

```java
Sort grouping = Sort.by(Sort.Order.asc("category"));

Sort ranking = Sort.by(
        Sort.Order.desc("price"),
        Sort.Order.asc("name")
);

Sort tieBreaker = Sort.by(Sort.Order.asc("id"));

Sort finalSort = grouping.and(ranking).and(tieBreaker);
```

Kết quả có ý nghĩa:

```text
category ASC, price DESC, name ASC, id ASC
```

`.and()` bổ sung các tiêu chí của đối số sau những tiêu chí hiện có. Nó không làm cho hai nhóm tiêu chí có cùng độ ưu tiên, cũng không yêu cầu store tự chọn nhóm nào quan trọng hơn.

### 4.1. Phép kết hợp không giao hoán

```java
Sort first = grouping.and(ranking);
Sort second = ranking.and(grouping);
```

Hai yêu cầu khác nhau:

| Biểu thức | Thứ tự |
| --- | --- |
| `grouping.and(ranking)` | `category ASC, price DESC, name ASC` |
| `ranking.and(grouping)` | `price DESC, name ASC, category ASC` |

Ở biểu thức thứ hai, mọi khác biệt về giá đã quyết định trước khi category được xét. Không thể đổi chỗ hai `Sort` chỉ vì chúng cùng chứa các thuộc tính đó.

### 4.2. Có thể chia nhóm mà vẫn giữ thứ tự nối

Khi cùng giữ thứ tự tiêu chí, cách đặt ngoặc để chia các nhóm không thay đổi ý định:

```java
Sort a = grouping.and(ranking).and(tieBreaker);
Sort b = grouping.and(ranking.and(tieBreaker));
```

Điểm cần kiểm tra là thứ tự phần tử được nối, không phải hình thức có nhiều biến hay nhiều ngoặc hơn.

## 5. Sort có tính bất biến: cần giữ kết quả trả về

Các thao tác tạo hoặc điều chỉnh `Sort` trả về một giá trị biểu diễn thứ tự mới; không nên sử dụng chúng như lệnh thay đổi đối tượng tại chỗ.

Ví dụ dễ sai:

```java
Sort sort = Sort.by("category");
sort.and(Sort.by(Sort.Order.desc("price")));

// sort vẫn chỉ biểu đạt category ASC.
```

Cách dùng đúng:

```java
Sort sort = Sort.by("category");
sort = sort.and(Sort.by(Sort.Order.desc("price")));
```

Hoặc tạo kết quả cuối trong một biểu thức:

```java
Sort sort = Sort.by("category")
        .and(Sort.by(Sort.Order.desc("price")));
```

Tính bất biến giúp các phần như `grouping` và `tieBreaker` được tái sử dụng mà không bị một nơi gọi thay đổi nội dung ngầm. Tuy vậy, bạn vẫn phải giữ lại hoặc trả về `Sort` mới để yêu cầu mới có hiệu lực.

### 5.1. `.ascending()` và `.descending()` tác động lên cả Sort

```java
Sort mixed = Sort.by(
        Sort.Order.asc("category"),
        Sort.Order.desc("price")
);

Sort allDescending = mixed.descending();
```

`allDescending` có ý nghĩa:

```text
category DESC, price DESC
```

Nó không chỉ thay hướng của thuộc tính cuối và cũng không có nghĩa là đảo từng hướng của thứ tự hỗn hợp. Nếu muốn giữ các hướng khác nhau, hãy tạo hoặc điều chỉnh các `Order` tương ứng có chủ đích.

Hướng và các hint như null handling là những metadata khác nhau. Đừng mặc định đổi hướng sẽ tự thiết kế lại toàn bộ chính sách đặt null hoặc so sánh chuỗi.

## 6. `Sort.unsorted()` và lựa chọn mặc định

`Sort.unsorted()` biểu đạt không có tiêu chí sắp xếp được yêu cầu qua đối tượng đó.

```java
Sort noPreference = Sort.unsorted();

Sort byName = noPreference.and(Sort.by("name"));
```

Ý định của `byName` là `name ASC`. Nối với một `Sort` không có tiêu chí không thêm một mức ưu tiên mới.

`unsorted` không yêu cầu backend xáo trộn ngẫu nhiên và cũng không bảo đảm thứ tự tự nhiên ổn định. Nếu query còn có thứ tự tĩnh hoặc cơ chế khác, đối tượng unsorted không tự xóa những phần đó.

### 6.1. Mặc định khi người gọi chưa chọn thứ tự

```java
Sort defaults = Sort.by(
        Sort.Order.desc("updatedAt"),
        Sort.Order.asc("id")
);

Sort selected = requested.isSorted() ? requested : defaults;
```

Ở đây `requested` được giả định khác null. Khi người gọi đã chọn thứ tự, dùng lựa chọn đó; khi chưa chọn, dùng mặc định.

Điều này khác với:

```java
Sort selected = defaults.and(requested);
```

Biểu thức thứ hai luôn đặt `updatedAt` và `id` lên trước. Vì `id` đã phân biệt các sản phẩm trong phạm vi truy vấn, các tiêu chí người gọi thêm phía sau có thể không còn cơ hội ảnh hưởng kết quả.

### 6.2. Mặc định hay khóa phụ là hai chính sách khác nhau

| Chính sách | Cách biểu đạt khái niệm |
| --- | --- |
| Chỉ dùng mặc định khi không có lựa chọn | Chọn `requested` hoặc `defaults` |
| Luôn nhóm theo category rồi mới theo lựa chọn | `grouping.and(requested)` |
| Ưu tiên lựa chọn, sau đó phân biệt các phần tử còn bằng nhau | `requested.and(tieBreaker)` |

Trước khi gọi `.and()`, cần biết bạn đang nối tiêu chí bắt buộc, tiêu chí do người gọi chọn hay một fallback thay thế. Tên biến rõ giúp tránh lẫn ba mục đích này.

## 7. Thuộc tính trùng không được ghi đè tự động

Xét:

```java
Sort defaults = Sort.by(Sort.Order.asc("price"));
Sort requested = Sort.by(Sort.Order.desc("price"));

Sort combined = defaults.and(requested);
```

Không nên hiểu `combined` là “price giảm dần vì cấu hình sau ghi đè cấu hình trước”. `Sort.and()` nối các tiêu chí; nó không phải thao tác cập nhật một map theo tên thuộc tính.

Ý định được biểu diễn có thể chứa:

```text
price ASC, price DESC
```

Với cùng biểu thức so sánh thông thường, tiêu chí sau không đảo được quyết định của tiêu chí trước. Một store có thể có cách xử lý hoặc giới hạn riêng với tiêu chí trùng; không dựa vào đó để triển khai quy tắc ghi đè.

### 7.1. Chọn chính sách xung đột trước

Ứng dụng có thể chọn một trong những chính sách:

- Từ chối thuộc tính trùng để yêu cầu luôn rõ ràng.
- Giữ lần xuất hiện đầu tiên.
- Giữ cấu hình sau nhưng xác định rõ nó sẽ đứng ở vị trí ưu tiên nào.
- Hạn chế các thuộc tính do người gọi chọn để không xung đột với tiêu chí bắt buộc.

Đây là chính sách của ứng dụng. Commons không tự quyết định rằng lựa chọn giao diện luôn được ưu tiên hơn mặc định.

Khi chuẩn hóa, cần giữ cả metadata của `Order` nếu muốn bảo toàn hướng, ignore-case và null handling. Chuyển mọi tiêu chí về một danh sách tên thuộc tính rồi gọi `Sort.by(names)` sẽ làm mất các hướng hỗn hợp và những metadata đã chọn.

## 8. Ví dụ chuẩn hóa Sort tại biên ứng dụng

Chính sách minh họa:

1. Chấp nhận một tập thuộc tính đã biết.
2. Nếu chưa có lựa chọn, dùng `updatedAt DESC`.
3. Từ chối thuộc tính trùng.
4. Thêm `id ASC` khi chưa có `id`, để phân biệt các phần tử còn bằng nhau.
5. Giữ nguyên ưu tiên và metadata của các tiêu chí hợp lệ.

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import org.springframework.data.domain.Sort;

final class ProductSortPolicy {

    private static final Set<String> ALLOWED = Set.of(
            "category", "price", "name", "updatedAt", "id");

    private ProductSortPolicy() {
    }

    static Sort normalize(Sort requested) {
        Objects.requireNonNull(requested, "requested");

        Sort selected = requested.isSorted()
                ? requested
                : Sort.by(Sort.Order.desc("updatedAt"));

        Map<String, Sort.Order> orders = new LinkedHashMap<>();

        for (Sort.Order order : selected) {
            String property = order.getProperty();

            if (!ALLOWED.contains(property)) {
                throw new IllegalArgumentException(
                        "Thuộc tính sắp xếp không được hỗ trợ: " + property);
            }

            if (orders.putIfAbsent(property, order) != null) {
                throw new IllegalArgumentException(
                        "Thuộc tính sắp xếp bị lặp: " + property);
            }
        }

        orders.putIfAbsent("id", Sort.Order.asc("id"));

        return Sort.by(new ArrayList<>(orders.values()));
    }
}
```

`LinkedHashMap` giữ thứ tự chèn, nên các `Order` hợp lệ giữ nguyên ưu tiên. `putIfAbsent` cuối cùng chỉ bổ sung `id` khi chưa xuất hiện.

Nếu người gọi chủ động đưa `id` lên đầu, chính sách này giữ lựa chọn đó. Khi `id` đã là duy nhất trong phạm vi kết quả, các tiêu chí sau nó thường không còn phân biệt thêm được gì. Nếu sản phẩm muốn `id` luôn chỉ là khóa phụ cuối cùng, cần định nghĩa và triển khai một chính sách khác.

Danh sách cho phép là một ví dụ về hợp đồng API, không phải danh sách thuộc tính bắt buộc của Spring Data. Khi API bên ngoài dùng các tên như `moi-nhat` hoặc `gia`, có thể ánh xạ chúng sang thuộc tính domain trước khi tạo `Sort`.

Phương thức trên chuẩn hóa thứ tự. Nó không kiểm tra rằng backend hỗ trợ mọi hint có trong `Order`; phần đó còn phải phù hợp với module và kiểu query.

## 9. Khóa phụ giúp thứ tự xác định khi phân trang

Giả sử mười sản phẩm có cùng `updatedAt`. Chỉ dùng:

```text
updatedAt DESC
```

thì query chưa quy định thứ tự giữa mười sản phẩm đó. Backend không bắt buộc trả cùng một cách sắp xếp giữa chúng trong mọi lần thực thi.

Bổ sung một thuộc tính duy nhất trong phạm vi truy vấn:

```text
updatedAt DESC, id ASC
```

giúp xác định thứ tự giữa những phần tử trùng thời điểm.

### 9.1. Khóa phụ phải đủ phân biệt trong phạm vi kết quả

Nếu truy vấn đã giới hạn một tenant và `id` duy nhất trong tenant, `id` có thể đủ làm khóa phụ. Nếu truy vấn gồm nhiều tenant và `id` chỉ duy nhất nội bộ từng tenant, cần một tổ hợp khóa đủ phân biệt, chẳng hạn thêm tenant vào phần khóa phù hợp.

Không nhất thiết mọi domain đều dùng một field tên `id`. Cần chọn thuộc tính hoặc tổ hợp thuộc tính theo mô hình định danh thực tế.

### 9.2. Thứ tự xác định không tạo snapshot dữ liệu

Ngay cả khi có khóa phụ duy nhất, dữ liệu thêm mới, bị xóa hoặc thay đổi giá trị sắp xếp giữa hai lần đọc vẫn có thể ảnh hưởng việc phân trang theo offset.

`Sort` xác định cách so sánh dữ liệu được nhìn thấy tại một lần đọc. Nó không tự giữ một snapshot xuyên nhiều request, khóa dữ liệu hoặc chuyển offset pagination thành keyset scrolling.

Nếu cần tính nhất quán hoặc hiệu năng đặc biệt, hãy chọn chiến lược phân trang/scroll và khả năng transaction của store phù hợp. Khóa phụ vẫn là thành phần quan trọng của thứ tự, nhưng không giải quyết mọi vấn đề đồng thời.

## 10. Dùng với repository và Pageable

Ví dụ repository, khi store hỗ trợ:

```java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.repository.Repository;

interface ProductRepository extends Repository<Product, Long> {

    List<Product> findByTenantIdAndActiveTrue(
            String tenantId, Sort sort);

    Page<Product> findByTenantIdAndActiveTrue(
            String tenantId, Pageable pageable);
}
```

Lấy danh sách:

```java
Sort requested = Sort.by(
        Sort.Order.asc("category"),
        Sort.Order.desc("price")
);

Sort sort = ProductSortPolicy.normalize(requested);

List<Product> products = repository.findByTenantIdAndActiveTrue(
        tenantId, sort);
```

Với chính sách minh họa, thứ tự cuối là:

```text
category ASC, price DESC, id ASC
```

Lấy một trang:

```java
import org.springframework.data.domain.PageRequest;

PageRequest pageable = PageRequest.of(0, 20, sort);

Page<Product> page = repository.findByTenantIdAndActiveTrue(
        tenantId, pageable);
```

Chỉ số trang bắt đầu từ `0`; kích thước trang là `20`. `Pageable` đã mang thông tin sort nên không cần thêm một tham số `Sort` riêng vào cùng phương thức để mô tả lại thứ tự đó.

`tenantId` và `active` là điều kiện truy vấn. `Sort` không lọc tenant, không thay thế kiểm tra quyền và không làm thay đổi phạm vi dữ liệu được phép đọc.

### Thứ tự tĩnh và thứ tự động

Nếu tên derived query đã có `OrderBy...`, hoặc một truy vấn khai báo có thứ tự riêng, cần xem quy tắc kết hợp của module đang dùng. Không mặc định rằng một `Sort` truyền vào sẽ xóa hoặc ghi đè thứ tự đã có.

Với các yêu cầu động, tập trung chính sách ưu tiên ở một nơi thường giúp dễ đọc hơn việc rải tiêu chí trong tên phương thức, service và tham số đầu vào mà chưa xác định thứ tự cuối cùng.

## 11. Hướng, null handling và ignore-case thuộc từng Order

Một `Order` có thể mang thêm yêu cầu:

```java
Sort sort = Sort.by(
        Sort.Order.asc("name").ignoreCase().nullsLast(),
        Sort.Order.desc("updatedAt"),
        Sort.Order.asc("id")
);
```

Các metadata không tự áp dụng đồng loạt cho mọi thuộc tính:

- Ignore-case và nulls-last trong ví dụ gắn với `name`.
- `updatedAt` giữ hướng giảm dần và các thiết lập riêng của nó.
- `id` là tiêu chí tăng dần cuối cùng.

Null handling là hint đối với datastore; mức hỗ trợ có thể khác nhau hoặc bị giới hạn theo loại query. Ignore-case cũng cần kiểu thuộc tính và khả năng store phù hợp. `Sort` không tự chuẩn hóa toàn bộ dữ liệu hoặc bỏ dấu tiếng Việt.

Nếu chính sách phân trang dựa vào thuộc tính nullable hoặc collation đặc biệt, cần xác minh cả dữ liệu sát biên trang. Thêm `id` không tự làm quy tắc so sánh chuỗi của hai backend trở nên giống nhau.

## 12. Hiệu năng và những tình huống cần xác minh

Thứ tự nhiều thuộc tính có thể ảnh hưởng index, công đoạn sort và lượng dữ liệu backend cần xử lý. Một index hữu ích thường cần được cân nhắc cùng điều kiện lọc, thứ tự ưu tiên và hướng của các thuộc tính, theo khả năng của store.

Không thể kết luận truy vấn nhanh chỉ vì `Sort` có một dòng code. Cũng không nên tạo index cho mọi tổ hợp sắp xếp mà chưa biết các đường truy vấn quan trọng.

Các ca dữ liệu có ích:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Khác tiêu chí đầu, tiêu chí sau có vẻ thuận lợi hơn | Tiêu chí đầu vẫn quyết định |
| Bằng tiêu chí đầu | Tiêu chí thứ hai được dùng đúng hướng |
| Bằng mọi tiêu chí nghiệp vụ | Khóa phụ phân biệt các phần tử |
| Thuộc tính xuất hiện hai lần | Chính sách chuẩn hóa xử lý đúng |
| Người gọi không chọn thứ tự | Fallback được chọn, không bị nối sai ưu tiên |
| Người gọi đã chọn thứ tự | Tiêu chí mặc định không vô tình chiếm vị trí chính |
| Có null hoặc khác hoa thường | Hành vi backend đúng hợp đồng |
| Dữ liệu nằm sát ranh giới hai trang | Thứ tự giữa phần tử trùng giá trị được quy định |
| Có thay đổi dữ liệu giữa các lần đọc | Đánh giá riêng giới hạn nhất quán của cách phân trang |

Các kiểm tra này tập trung vào ý nghĩa thứ tự. Việc parser hoặc repository chấp nhận tên thuộc tính mới chỉ là một phần của hợp đồng.

## 13. Bài tập tự kiểm tra

### Bài 1: Ưu tiên từ trái sang phải

Với `category ASC, price DESC`, sản phẩm TOOL giá 150 có chắc đứng trước BOOK giá 100 không?

**Gợi ý đáp án:** Không. Khi category khác nhau, tiêu chí category quyết định trước. Giá chỉ được dùng khi category bằng nhau.

### Bài 2: Nối có phải ghi đè không?

```java
Sort sort = Sort.by(Sort.Order.asc("price"))
        .and(Sort.by(Sort.Order.desc("price")));
```

Có nên coi kết quả là `price DESC` vì tiêu chí sau mới hơn không?

**Gợi ý đáp án:** Không. `.and()` nối tiêu chí, không ghi đè theo thuộc tính. Ứng dụng cần một chính sách xung đột rõ ràng.

### Bài 3: Bỏ qua kết quả trả về

```java
Sort sort = Sort.by("name");
sort.and(Sort.by("id"));
```

Biến `sort` đã chứa thêm `id` chưa?

**Gợi ý đáp án:** Chưa. Cần giữ kết quả trả về, chẳng hạn `sort = sort.and(Sort.by("id"))`.

### Bài 4: Mặc định và lựa chọn người dùng

Mặc định là `updatedAt DESC, id ASC`; người dùng chọn `price ASC`. Nếu mục tiêu là người dùng được ưu tiên và chỉ dùng mặc định khi chưa có lựa chọn, có nên dùng `defaults.and(requested)` không?

**Gợi ý đáp án:** Không. Cần chọn requested khi có tiêu chí, nếu không mới chọn defaults. Sau đó bổ sung khóa phụ theo chính sách và tránh thuộc tính trùng.

### Bài 5: Thứ tự hỗn hợp

Một `Sort` là `category ASC, price DESC`. Gọi `.descending()` có tạo ra `category DESC, price ASC` không?

**Gợi ý đáp án:** Không. `.descending()` đặt hướng giảm dần cho các tiêu chí, nên kết quả là `category DESC, price DESC`.

### Bài 6: Khóa phụ và dữ liệu thay đổi

Đã thêm `id` duy nhất sau `updatedAt`. Có thể kết luận mọi request phân trang sẽ nhìn thấy cùng một snapshot dù có sản phẩm được cập nhật không?

**Gợi ý đáp án:** Không. Khóa phụ quy định thứ tự giữa phần tử trùng giá trị. Snapshot và thay đổi đồng thời thuộc hợp đồng transaction/cách phân trang của store.

## Những điểm cần nhớ

- `Sort` chứa một danh sách tiêu chí có ưu tiên: tiêu chí bên trái được xét trước.
- `.and()` nối thứ tự và trả một giá trị Sort; nó không ghi đè thuộc tính hoặc sửa đối tượng tại chỗ.
- Chọn fallback, nối tiêu chí bắt buộc và thêm khóa phụ là ba chính sách cần phân biệt.
- Giữ nguyên các `Order` khi cần bảo toàn hướng và metadata; xử lý thuộc tính trùng ở tầng chính sách ứng dụng.
- Khóa phụ duy nhất giúp thứ tự xác định, còn hiệu năng, null handling và tính nhất quán qua nhiều trang vẫn phụ thuộc store cùng cách truy vấn.
