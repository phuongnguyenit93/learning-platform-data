# Sắp xếp tĩnh trong tên phương thức và sắp xếp động

Trong Spring Data, điều kiện lọc và thứ tự kết quả là hai phần riêng của hợp đồng truy vấn. Phương thức tìm đúng các đơn hàng có trạng thái `PAID` chưa trả lời đơn hàng nào đứng trước, nhất là khi kết quả được giới hạn hoặc phân trang.

Có hai cách thường gặp trong repository:

- **Sắp xếp tĩnh:** ghi đường dẫn thuộc tính và hướng sắp xếp vào tên phương thức suy diễn bằng `OrderBy`.
- **Sắp xếp động:** truyền một mô tả `Sort`, hoặc truyền `Pageable` có chứa `Sort`, khi gọi phương thức.

Spring Data Commons cung cấp abstraction như `Sort`, `Sort.Order` và `Pageable`. Module của từng store chịu trách nhiệm chuyển mô tả đó thành truy vấn thực tế. Không phải mọi loại truy vấn hoặc store đều hỗ trợ mọi dạng sắp xếp.

Sau bài học, bạn cần có khả năng:

- Đọc đúng phần `OrderBy` trong tên phương thức.
- Tạo thứ tự nhiều tiêu chí bằng `Sort`.
- Chọn nơi đặt thứ tự mặc định và khóa phân xử.
- Hiểu cách kết hợp thứ tự tĩnh và động trong bối cảnh có hỗ trợ.
- Tránh sắp xếp sai phạm vi dữ liệu khi phân trang.
- Giới hạn các trường sắp xếp động từ API theo một hợp đồng rõ ràng.

## 1. Mô hình và dữ liệu dùng trong bài

Giả sử domain `PurchaseOrder` có các thuộc tính:

| Thuộc tính Java | Kiểu minh họa | Vai trò |
|---|---|---|
| `id` | `Long` | Định danh duy nhất, không null |
| `status` | `String` | Trạng thái đơn hàng |
| `createdAt` | `Instant` | Thời điểm tạo |
| `total` | `BigDecimal` | Tổng tiền |
| `customer` | `Customer` | Đối tượng/association có mapping riêng |

Các ví dụ repository chính đặt trong bối cảnh Spring Data JPA có mapping, kết nối và repository scanning phù hợp. Những khái niệm dùng chung được tách khỏi giới hạn của từng store ở phần sau.

Dữ liệu minh họa, tất cả cùng trạng thái `PAID`:

| id | createdAt | total |
|---:|---|---:|
| 105 | 10:15 | 50 |
| 104 | 10:15 | 200 |
| 103 | 10:12 | 100 |
| 102 | 10:10 | 300 |

Ba yêu cầu khác nhau cho ba thứ tự:

| Yêu cầu | Tiêu chí | Thứ tự id |
|---|---|---|
| Mới nhất trước, phân xử bằng id giảm dần | `createdAt DESC, id DESC` | 105, 104, 103, 102 |
| Tổng tiền cao nhất trước | `total DESC, id DESC` | 102, 104, 103, 105 |
| Mới nhất trước, cùng thời điểm thì ưu tiên tổng tiền | `createdAt DESC, total DESC, id DESC` | 104, 105, 103, 102 |

Các tiêu chí được xét từ trái sang phải. Tiêu chí sau chỉ phân xử những bản ghi bằng nhau theo các tiêu chí trước.

### 1.1. Không có thứ tự được khai báo thì không có hợp đồng thứ tự

Một truy vấn không có sắp xếp có thể tình cờ trả kết quả theo id hoặc theo cách dữ liệu được đọc ở một lần chạy. Không nên dựa vào quan sát đó làm hợp đồng.

Không mặc định “thứ tự tự nhiên” là thứ tự chèn, thứ tự khóa chính hoặc thứ tự mới nhất. Kế hoạch truy cập và dữ liệu thay đổi có thể làm thứ tự quan sát được thay đổi.

## 2. Sắp xếp tĩnh bằng OrderBy trong tên phương thức

Một phương thức suy diễn:

```java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder>
    findByStatusOrderByCreatedAtDescIdDesc(String status);
}
```

Có thể đọc thành:

```text
find
  By Status
  OrderBy CreatedAt Desc
          Id        Desc
```

Ý nghĩa:

1. Lọc theo `status` bằng giá trị đối số.
2. Sắp xếp giảm dần theo `createdAt`.
3. Nếu cùng thời điểm, sắp xếp giảm dần theo `id`.

Phương thức chỉ nhận một đối số `status`. `CreatedAt` và `Id` ở sau `OrderBy` là thuộc tính dùng để sắp xếp, không tạo thêm tham số lọc.

### 2.1. Một thuộc tính có thể xuất hiện ở hai vai trò

Ví dụ:

```java
List<PurchaseOrder>
findByStatusAndTotalGreaterThanOrderByTotalAscIdAsc(
    String status,
    BigDecimal minimumTotal
);
```

Ở đây:

- `TotalGreaterThan` là điều kiện lọc, cần giá trị `minimumTotal`.
- `TotalAsc` là thứ tự, không cần thêm một đối số tổng tiền.
- `IdAsc` phân xử khi nhiều đơn hàng có cùng tổng tiền.

Hai vai trò độc lập dù cùng nhắc tới thuộc tính `total`.

### 2.2. Giới hạn kết quả vẫn cần thứ tự

```java
List<PurchaseOrder>
findTop10ByStatusOrderByCreatedAtDescIdDesc(String status);
```

Trong module hỗ trợ cách suy diễn này, phương thức thể hiện “lấy tối đa 10 đơn hàng theo thứ tự mới nhất đã xác định”.

Chỉ viết `findTop10ByStatus` không đủ để diễn đạt “10 đơn hàng mới nhất”. `Top10` giới hạn số lượng; `OrderBy` mới mô tả thứ tự.

### 2.3. Khi nào thứ tự tĩnh phù hợp?

Sắp xếp tĩnh phù hợp khi thứ tự là một phần ổn định của use case:

- Lấy các đơn mới nhất cho một chức năng cụ thể.
- Duyệt hàng chờ theo độ ưu tiên cố định.
- Trả lịch sử theo thời gian với một quy tắc phân xử rõ.
- Tạo phương thức mà mọi caller đều cần cùng một thứ tự.

Đổi thứ tự tĩnh cần thay đổi khai báo repository. Nó dễ đọc khi số tiêu chí ít, nhưng tên phương thức có thể dài nếu đồng thời chứa nhiều điều kiện và nhiều tiêu chí sort.

## 3. Sắp xếp động bằng Sort

Khi cùng một tập điều kiện cần nhiều cách xem, có thể nhận `Sort`:

```java
import java.util.List;

import org.springframework.data.domain.Sort;

List<PurchaseOrder> findByStatus(String status, Sort sort);
```

Lời gọi:

```java
Sort newestFirst = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

List<PurchaseOrder> orders =
    repository.findByStatus("PAID", newestFirst);
```

`Sort` là tham số điều khiển truy vấn. Nó không trở thành một giá trị cần so sánh với field tên `sort`.

Một caller khác có thể dùng:

```java
Sort highestTotalFirst = Sort.by(
    Sort.Order.desc("total"),
    Sort.Order.desc("id")
);

List<PurchaseOrder> orders =
    repository.findByStatus("PAID", highestTotalFirst);
```

Điều kiện lọc không đổi, nhưng ưu tiên kết quả đổi từ thời điểm tạo sang tổng tiền.

### 3.1. Cùng hướng cho nhiều thuộc tính

```java
Sort sort = Sort.by("createdAt", "id").descending();
```

Dạng này đặt hướng giảm dần cho cả hai thuộc tính. Nó không có nghĩa chỉ đảo hướng thuộc tính cuối.

### 3.2. Khác hướng cho từng thuộc tính

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("id")
);
```

Khi cùng thời điểm, id nhỏ hơn đứng trước. Đây là một hợp đồng khác với `id DESC`; hãy chọn có chủ đích.

### 3.3. Ghép Sort không phải sửa tại chỗ

```java
Sort primary = Sort.by("createdAt").descending();
Sort combined = primary.and(Sort.by("id").descending());
```

`combined` có hai tiêu chí. `primary` vẫn là mô tả ban đầu.

Nếu chỉ gọi `primary.and(...)` rồi bỏ giá trị trả về, không nên kỳ vọng biến `primary` đã được thay đổi.

### 3.4. Không yêu cầu sort động

```java
List<PurchaseOrder> orders =
    repository.findByStatus("PAID", Sort.unsorted());
```

Dùng đối tượng `Sort.unsorted()` thay vì truyền null cho tham số đặc biệt theo hợp đồng API.

Với phương thức chỉ có sort động, điều này nghĩa là không đưa ra yêu cầu thứ tự động. Nó không tự chọn id hoặc thời điểm tạo làm thứ tự mặc định.

Nếu phương thức còn có `OrderBy` tĩnh, `Sort.unsorted()` không phải yêu cầu xóa bỏ thứ tự tĩnh.

## 4. Khi phương thức có cả OrderBy tĩnh và Sort động

Ví dụ trong derived query của Spring Data JPA sử dụng cơ chế tạo truy vấn từ `PartTree`:

```java
List<PurchaseOrder> findByStatusOrderByCreatedAtDesc(
    String status,
    Sort sort
);
```

Lời gọi:

```java
Sort extraOrder = Sort.by(
    Sort.Order.desc("total"),
    Sort.Order.desc("id")
);

repository.findByStatusOrderByCreatedAtDesc("PAID", extraOrder);
```

Trong cơ chế này, thứ tự tĩnh được đặt trước, rồi ghép thứ tự động phía sau:

```text
createdAt DESC
total     DESC
id        DESC
```

Kết quả theo bảng dữ liệu đầu bài là `104, 105, 103, 102`.

`total DESC` chỉ phân xử các đơn có cùng `createdAt`. Nó không đưa đơn id 102 lên đầu dù đơn đó có tổng tiền lớn nhất.

Đối với module hoặc loại query khác, cần xác nhận cách áp dụng sort thực tế. Không mở rộng quy tắc của derived query JPA thành lời cam kết cho mọi truy vấn khai báo hoặc native query.

### 4.1. Sort động không có nghĩa ghi đè thứ tự tĩnh

Nếu caller muốn tổng tiền là tiêu chí chính, phương thức có `OrderByCreatedAtDesc` không diễn đạt đúng yêu cầu đó theo quy tắc ghép trên.

Một thiết kế rõ hơn là dùng phương thức chỉ nhận `Sort`, rồi truyền toàn bộ thứ tự mong muốn:

```java
repository.findByStatus(
    "PAID",
    Sort.by(
        Sort.Order.desc("total"),
        Sort.Order.desc("id")
    )
);
```

Thứ tự mặc định lúc này có thể được đặt ở service hoặc lớp chuyển đổi tham số API. Caller có thể chọn một thứ tự khác mà không bị một tiêu chí tĩnh đứng trước.

### 4.2. Đặt khóa duy nhất quá sớm làm tiêu chí phía sau mất tác dụng

Xét phương thức:

```java
List<PurchaseOrder> findByStatusOrderByCreatedAtDescIdDesc(
    String status,
    Sort sort
);
```

Nếu truyền thêm `total ASC`, thứ tự logic là:

```text
createdAt DESC, id DESC, total ASC
```

Do `id` duy nhất, không còn hai đơn hàng bằng nhau sau tiêu chí id để `total` phân xử. Thứ tự động vẫn được mô tả nhưng không thay đổi thứ tự các đơn.

Nếu yêu cầu là “mới nhất trước, cùng thời điểm thì tổng tiền thấp trước, cuối cùng mới tới id”, khóa id phải nằm sau tổng tiền.

Đừng đặt một khóa phân xử duy nhất tĩnh trước các tiêu chí mà caller kỳ vọng còn có ảnh hưởng.

### 4.3. Không dùng Sort.and như một map ghi đè

```java
Sort conflicting = Sort.by("createdAt").descending()
    .and(Sort.by("createdAt").ascending());
```

`and` ghép các mô tả thứ tự, không có nghĩa “thay hướng cũ của createdAt bằng hướng mới”.

Một yêu cầu cùng thuộc tính với hai hướng đối lập không phải cách ghi đè rõ ràng. Module có thể chuyển nó thành thứ tự dư thừa hoặc xử lý theo giới hạn riêng; không nên dựa vào việc đó để điều khiển ưu tiên.

Hãy xây một danh sách tiêu chí đã thống nhất, không trùng thuộc tính ngoài chủ đích.

### 4.4. Unsorted chỉ bỏ phần yêu cầu động

Với phương thức có `OrderByCreatedAtDesc`:

```java
repository.findByStatusOrderByCreatedAtDesc(
    "PAID",
    Sort.unsorted()
);
```

Thứ tự tĩnh vẫn còn. Nếu API cần một lựa chọn thật sự không áp dụng thứ tự mặc định, hợp đồng service/repository phải được thiết kế để biểu diễn lựa chọn đó, không chỉ truyền `Sort.unsorted()` vào một phương thức vốn đã có thứ tự tĩnh.

## 5. Tên thuộc tính domain và đường dẫn lồng nhau

### 5.1. Dùng thuộc tính Java trong query derivation

Nếu thuộc tính Java là `createdAt`, còn cột quan hệ là `created_at`:

```java
Sort.by("createdAt").descending();
```

là cách diễn đạt theo domain trong ví dụ derived query JPA.

Không tự đổi thành `Sort.by("created_at")` vì nhìn thấy tên cột trong database. Việc chuyển tên thuộc tính sang định danh lưu trữ thuộc mapping của module.

Với truy vấn khai báo có alias hoặc cơ chế sort đặc thù, phải xem hợp đồng của loại query đó; không lấy quy tắc alias để suy ngược rằng mọi `Sort` đều nhận tùy ý tên cột.

### 5.2. Đường dẫn lồng nhau

Giả sử `Customer` có thuộc tính `name`, và mapping cho phép truy vấn qua `PurchaseOrder.customer`.

Một tên phương thức có thể viết:

```java
List<PurchaseOrder>
findByStatusOrderByCustomer_NameAscIdAsc(String status);
```

Dấu `_` chỉ rõ ranh giới giữa `customer` và `name`. Nó không yêu cầu một field Java tên `customer_name`.

Với API sort động hỗ trợ đường dẫn dấu chấm:

```java
Sort byCustomer = Sort.by(
    Sort.Order.asc("customer.name"),
    Sort.Order.asc("id")
);
```

Hai cách đều có ý định sắp xếp theo tên khách hàng, rồi theo id đơn hàng, trong bối cảnh module hỗ trợ.

### 5.3. Đường dẫn đúng chưa bảo đảm mọi hành vi

Cần kiểm tra thêm:

- Đường dẫn thuộc tính có mơ hồ hoặc viết sai không.
- Store hỗ trợ đi qua embedded object, association hay reference đó không.
- Nếu đối tượng trung gian thiếu/null, bản ghi được xử lý thế nào.
- Sắp xếp có tạo thêm join hoặc làm tăng chi phí truy vấn không.
- Nếu đi qua collection, một đơn hàng có nhiều giá trị con sẽ được sắp xếp theo quy tắc nào.

Sắp xếp qua association không đồng nghĩa đã fetch toàn bộ association cho caller. Trong JPA, fetch plan vẫn là một vấn đề riêng.

## 6. Sắp xếp với Pageable

Một hợp đồng phân trang:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<PurchaseOrder> findByStatus(
    String status,
    Pageable pageable
);
```

Lời gọi:

```java
import org.springframework.data.domain.PageRequest;

Sort newestFirst = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Pageable request = PageRequest.of(0, 20, newestFirst);

Page<PurchaseOrder> page =
    repository.findByStatus("PAID", request);
```

Chỉ số trang trong `PageRequest` bắt đầu từ 0. Sort trong `Pageable` là yêu cầu thứ tự đi cùng giới hạn/phân trang.

### 6.1. Đặt sort ở một nơi trong chữ ký phân trang

Không thêm một tham số `Sort` riêng bên cạnh `Pageable` chỉ để mong có hai nguồn điều khiển thứ tự:

```java
// Không dùng mẫu này làm hợp đồng phân trang:
Page<PurchaseOrder> findByStatus(
    String status,
    Pageable pageable,
    Sort sort
);
```

`Pageable` đã chứa sort. Các tổ hợp tham số đặc biệt còn phải tuân theo quy tắc của Spring Data; không giả định framework sẽ tự chọn ưu tiên giữa chúng.

Hãy tạo `Pageable` với thứ tự cuối cùng mà API cần.

### 6.2. Thứ tự ổn định cần khóa phân xử

Chỉ sắp xếp theo `createdAt DESC` chưa xác định thứ tự giữa id 105 và 104 trong dữ liệu ví dụ, vì chúng có cùng thời điểm.

Thêm `id DESC` cho phép xác định thứ tự giữa các bản ghi đó. Trong mô hình giả định id duy nhất và không null, đây là tiêu chí phân xử phù hợp.

Điều này giúp trang và tập kết quả giới hạn có ý nghĩa rõ hơn. Tuy nhiên, thứ tự xác định không tự tạo snapshot bất biến. Khi dữ liệu được thêm/xóa/thay đổi giữa hai lần đọc, offset pagination vẫn có thể có phần tử bị lặp hoặc bị bỏ qua.

Nếu use case cần cuộn theo cursor/keyset hoặc một snapshot nhất quán, phải chọn cơ chế phù hợp với module và yêu cầu dữ liệu.

### 6.3. Sắp xếp sau khi đã lấy một trang chỉ đổi thứ tự trong trang

Giả sử repository đã chọn 20 bản ghi của trang đầu mà chưa áp dụng thứ tự tổng tiền mong muốn. Sau đó service sort 20 phần tử đó trong Java.

Kết quả chỉ là “20 bản ghi đã lấy được, sắp lại theo tổng tiền”. Nó không phải “20 đơn có tổng tiền cao nhất trong toàn bộ tập thỏa điều kiện”.

Thứ tự cần ảnh hưởng tới việc chọn trang phải được áp dụng ở truy vấn trước giới hạn dữ liệu. Tải toàn bộ rồi sort trong bộ nhớ có chi phí và phạm vi khác, cần được chủ động thiết kế.

## 7. Hướng sắp xếp, chữ hoa/thường và null

`Sort.Order` không chỉ chứa tên thuộc tính. Nó còn có thể mang các yêu cầu về hướng, xử lý chữ hoa/thường và vị trí null.

Ví dụ tạo một mô tả:

```java
Sort.Order nameOrder = Sort.Order.asc("customer.name")
    .ignoreCase()
    .nullsLast();
```

Đây là mô tả mong muốn. Nó chưa chứng minh module và store sẽ thực thi đầy đủ các tùy chọn.

### 7.1. IgnoreCase không phải quy tắc collation chung

Cách sắp xếp chữ hoa/thường, dấu tiếng Việt và ký tự Unicode phụ thuộc store, collation và cách module tạo biểu thức.

`ignoreCase()` có thể cần biến đổi biểu thức hoặc một cơ chế đặc thù. Nó không tự cung cấp một thứ tự ngôn ngữ học đúng cho mọi ngôn ngữ, và có thể làm thay đổi khả năng dùng index.

Nếu nghiệp vụ yêu cầu sắp tên tiếng Việt, hãy xem collation và những trường hợp dữ liệu cụ thể thay vì chỉ kiểm tra một cặp chữ hoa/chữ thường.

### 7.2. NullsFirst/NullsLast là yêu cầu cần được đối chiếu

Các tùy chọn `nullsFirst()`, `nullsLast()`, `nullsNative()` thể hiện chính sách null handling trong mô tả sort.

Module có thể hỗ trợ, có thể không áp dụng được, hoặc từ chối một tùy chọn trong loại truy vấn đang dùng. Chẳng hạn, không mặc định mọi đường tạo truy vấn Criteria trong JPA có thể chuyển các null handling hint này thành biểu thức tương ứng.

`nullsNative()` để store quyết định theo hành vi native; nó không có nghĩa null luôn đứng cuối.

### 7.3. Kiểu dữ liệu ảnh hưởng thứ tự

Một tổng tiền được lưu đúng kiểu số không có cùng thứ tự như chuỗi biểu diễn số. Tương tự, thời gian lưu dưới dạng chuỗi có định dạng không thống nhất có thể không cho thứ tự thời gian mong muốn.

Đổi từ sort tĩnh sang sort động không sửa được mapping dữ liệu sai kiểu.

## 8. Thiết kế sort động cho API có giới hạn

Không nên nhận một chuỗi thuộc tính bất kỳ từ client rồi dùng nó làm hợp đồng truy vấn công khai mà không kiểm soát. Client cần một tập lựa chọn ổn định; domain có thể thay đổi.

Một cách làm là ánh xạ khóa công khai sang thuộc tính nội bộ:

| Khóa công khai | Thuộc tính domain | Mục đích |
|---|---|---|
| `created` | `createdAt` | Thời điểm tạo |
| `amount` | `total` | Tổng tiền |

Khóa id được thêm ở server làm tiêu chí phân xử, thay vì để xuất hiện lặp lại tùy ý trong đầu vào.

### 8.1. Factory tạo thứ tự hoàn chỉnh

Ví dụ sau dùng switch expression, giả định dự án Java 17 trở lên:

```java
import org.springframework.data.domain.Sort;

public final class OrderSorts {

    private OrderSorts() {
    }

    public static Sort from(
        String requestedKey,
        String requestedDirection
    ) {
        String key = requestedKey == null
            ? "created"
            : requestedKey;

        String property = switch (key) {
            case "created" -> "createdAt";
            case "amount" -> "total";
            default -> throw new IllegalArgumentException(
                "Unsupported sort key: " + key
            );
        };

        Sort.Direction direction = requestedDirection == null
            ? Sort.Direction.DESC
            : Sort.Direction.fromString(requestedDirection);

        return Sort.by(new Sort.Order(direction, property))
            .and(Sort.by(Sort.Order.desc("id")));
    }
}
```

Lời gọi:

```java
Sort defaultSort = OrderSorts.from(null, null);
// createdAt DESC, id DESC

Sort amountAscending = OrderSorts.from("amount", "asc");
// total ASC, id DESC
```

Trong ví dụ, id luôn giảm dần theo chính sách của API. Nó không bắt buộc phải cùng hướng với tiêu chí chính; điều quan trọng là quy tắc rõ ràng và xác định.

Các khóa không có trong danh sách được từ chối. Hướng không hợp lệ cũng bị từ chối theo API `Sort.Direction`. Lớp HTTP cần ánh xạ lỗi đầu vào thành phản hồi phù hợp với hợp đồng ứng dụng.

### 8.2. Đặt mặc định tại một ranh giới đã chọn

Service sử dụng phương thức chỉ có sort động:

```java
Sort sort = OrderSorts.from(sortKey, sortDirection);

List<PurchaseOrder> result =
    repository.findByStatus(status, sort);
```

Hoặc dùng cùng sort cho phân trang:

```java
Pageable request = PageRequest.of(
    pageNumber,
    pageSize,
    OrderSorts.from(sortKey, sortDirection)
);

Page<PurchaseOrder> result =
    repository.findByStatus(status, request);
```

Trong thiết kế này:

- Repository nhận toàn bộ thứ tự đã giải quyết.
- Mặc định nằm ở factory/service.
- Thứ tự do client chọn có thể là tiêu chí chính.
- Khóa phân xử được bổ sung một lần.

Đừng vừa đặt một thứ tự mặc định tĩnh không thể thay thế trong tên phương thức, vừa diễn giải sort động là quyền ghi đè hoàn toàn mặc định đó.

### 8.3. Đầu vào sort là cấu hình truy vấn

Cần giới hạn theo use case:

- Trường nào được phép sort.
- Có cho phép đường dẫn lồng nhau không.
- Có bao nhiêu tiêu chí tối đa.
- Có loại bỏ hoặc từ chối thuộc tính lặp không.
- Khi thiếu sort thì dùng mặc định nào.
- Khi giá trị đầu vào sai thì phản hồi thế nào.

Không ghép trực tiếp chuỗi đầu vào vào SQL/JPQL hoặc tên biểu thức. Nếu cần sort theo một biểu thức tính toán, đó là khả năng riêng của loại query/module và cần được thiết kế tường minh.

Sort chỉ điều khiển thứ tự. Nó không tự áp dụng điều kiện phân quyền hoặc giới hạn tập dữ liệu; các điều kiện lọc cần được giữ đúng trong query.

## 9. Phạm vi hỗ trợ theo store và loại truy vấn

| Bối cảnh | Điều cần xác nhận |
|---|---|
| Derived query JPA | Thuộc tính persistent, đường dẫn, cách ghép static/dynamic và query thực tế |
| Query khai báo JPA | JPQL/native query, alias, khả năng áp dụng hoặc viết lại sort |
| MongoDB | Trường theo mapping, dữ liệu nhúng/reference, collation, mảng và index |
| JDBC/R2DBC | Derived query hay SQL tự khai báo; dialect và hỗ trợ tham số sort |
| Cassandra | Giới hạn ORDER BY theo clustering và phạm vi partition của CQL |
| Neo4j | Mapping thuộc tính/node/relationship và query Cypher tương ứng |
| Elasticsearch | Trường có mapping phù hợp để sort, chẳng hạn keyword cho chuỗi; nested/multi-value nếu có |

### 9.1. Query khai báo không lấy toàn bộ ngữ nghĩa từ tên phương thức

Khi một truy vấn khai báo được chọn, chuỗi query hoặc cơ chế khai báo đó là nguồn quan trọng của truy vấn. Không mặc định phần `OrderBy` nằm trong tên phương thức vẫn được dùng như trong derived query.

Tương tự, một tham số `Sort` không phải cam kết rằng module có thể tự viết lại mọi câu SQL phức tạp. Native query, hàm, alias, phép nhóm và union có thể có giới hạn khác.

Phải phân biệt “sort tĩnh trong tên suy diễn” với “ORDER BY cố định trong query khai báo”. Hai trường hợp không có cùng quy tắc xử lý chỉ vì đều cố định ở source code.

### 9.2. Sort không tạo ra phép truy cập mà store không cung cấp

CQL không trở thành một engine sắp xếp toàn cục theo cột bất kỳ khi phương thức nhận `Sort`. Một document reference cũng không tự trở thành join để sort theo trường ở document khác.

Nếu yêu cầu vượt khỏi khả năng của query derivation, cần API hoặc fragment phù hợp, hoặc xem lại mô hình dữ liệu.

### 9.3. Projection không tự định nghĩa đường dẫn lưu trữ

Một DTO có thuộc tính hiển thị `displayAmount` không có nghĩa domain có thuộc tính truy vấn được với tên đó.

Khi sort kết quả projection, cần xem module nhận tên thuộc tính domain, alias hay biểu thức nào. Hãy ánh xạ lựa chọn API tới định danh được loại query hỗ trợ, thay vì dùng mọi tên getter của DTO làm sort key.

## 10. Hiệu năng: sort động cũng cần một ngân sách truy vấn

Thứ tự tĩnh giúp dự đoán một số đường truy cập thường dùng. Sort động mở nhiều khả năng hơn, đồng thời có thể tạo những truy vấn khó dùng index.

Với store quan hệ, một truy vấn lọc trạng thái rồi sort theo thời điểm/id có thể cần index phù hợp với cả bộ lọc và thứ tự. Thiết kế cụ thể còn phụ thuộc hệ quản trị, hướng sort, độ chọn lọc và kế hoạch thực thi.

Không cần tạo index cho mọi hoán vị do client nghĩ ra. Tập khóa sort được phép nên phản ánh nhu cầu và khả năng vận hành của ứng dụng.

Cần quan sát:

- Số bản ghi phải đọc trước khi lấy đủ kết quả.
- Sort có được hỗ trợ bởi index hay phải xử lý một tập trung gian lớn.
- Chi phí join cho đường dẫn lồng nhau.
- Độ trễ ở các trang sâu.
- Tùy chọn ignore-case/collation có ảnh hưởng kế hoạch truy cập không.

Việc một đối tượng `Sort` được tạo thành công chỉ chứng minh mô tả đã được dựng. Nó chưa đánh giá chi phí thực thi.

## 11. Chọn cách đặt thứ tự theo use case

| Use case | Cách tổ chức phù hợp |
|---|---|
| Mọi caller luôn cần cùng thứ tự | Phương thức suy diễn có `OrderBy` tĩnh rõ ràng |
| Caller có quyền chọn tiêu chí chính | Phương thức nhận `Sort`, mặc định được giải quyết ở service/API |
| Một ưu tiên cố định, caller chỉ chọn cách phân xử phía sau | Có thể ghép static/dynamic nếu module hỗ trợ và thứ tự ưu tiên được mô tả rõ |
| Kết quả có phân trang | Đưa thứ tự cuối cùng vào `Pageable`, có khóa phân xử phù hợp |
| Sort theo biểu thức hoặc cấu trúc phức tạp | Query khai báo hoặc API/fragment đặc thù được module hỗ trợ |

Một ứng dụng có thể dùng nhiều cách cho các use case khác nhau. Không cần buộc mọi phương thức trong repository phải theo cùng một kiểu nếu hợp đồng nghiệp vụ khác nhau.

Điều quan trọng là caller biết mình đang chọn toàn bộ thứ tự hay chỉ thêm tiêu chí phụ. Tên phương thức, factory tạo sort và tài liệu API cần nhất quán về điểm này.

## 12. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Điều cần kiểm tra |
|---|---|---|
| Chọn sort động nhưng kết quả vẫn ưu tiên ngày tạo | Thứ tự tĩnh được ghép trước | Phần `OrderBy` và quy tắc ghép của query |
| Thêm sort động nhưng không thấy tác dụng | Khóa duy nhất đã đứng trước | Vị trí id trong danh sách tiêu chí |
| Gọi `and` nhưng thiếu tiêu chí mới | Bỏ giá trị trả về | Biến Sort cuối cùng được truyền vào query |
| Tên cột đúng trong DB nhưng sort lỗi | Dùng tên cột thay cho thuộc tính domain | Mapping và hợp đồng tên của loại query |
| Hai bản ghi cùng thời điểm đổi vị trí | Chưa có thứ tự phân xử đầy đủ | Thêm một khóa phù hợp, thường là định danh |
| Top/Page chứa sai nhóm bản ghi theo yêu cầu | Sort chỉ được thực hiện sau khi đã lấy dữ liệu | Vị trí sort so với giới hạn/phân trang |
| Null không đứng như mong muốn hoặc query bị từ chối | Hint không được hỗ trợ hoặc hành vi native khác | Module, loại query và chính sách null |
| Tên tiếng Việt sắp khác mong muốn | Collation hoặc quy tắc chuỗi khác | Cấu hình store và dữ liệu đại diện |
| Sort lồng nhau làm query chậm | Join/truy cập dữ liệu phát sinh | Query thực tế và index |
| `Sort.unsorted()` vẫn còn thứ tự | Thứ tự có sẵn trong tên/query | Các nguồn thứ tự ngoài tham số động |

### 12.1. Phân biệt lỗi dựng mô tả và lỗi thực thi

`Sort.by("unknownProperty")` có thể tạo được một mô tả chuỗi. Điều này không chứng minh domain có thuộc tính đó.

Lỗi có thể xuất hiện khi module phân giải đường dẫn hoặc tạo/thực thi query. Một kiểm tra chỉ tạo đối tượng `Sort` không xác nhận toàn bộ hợp đồng repository.

Ngược lại, lỗi dữ liệu không đúng thứ tự có thể xảy ra dù query hợp lệ: tiêu chí đã được ghép theo ưu tiên khác với kỳ vọng của caller.

### 12.2. Đọc thứ tự cuối cùng từ trái sang phải

Khi cần chẩn đoán, hãy viết ra toàn bộ thứ tự logic:

```text
1. createdAt DESC
2. total ASC
3. id DESC
```

Sau đó hỏi:

- Tiêu chí đầu có đúng thứ cần ưu tiên toàn cục không?
- Hai bản ghi nào còn bằng nhau sau mỗi bước?
- Một tiêu chí trước đã duy nhất chưa?
- Có thuộc tính bị lặp với hướng đối lập không?
- Phần nào đến từ tên phương thức, phần nào từ caller?

Cách đọc này thường cho thấy nguyên nhân trước khi cần thay đổi query.

## 13. Kiểm chứng hành vi trong dự án thực tế

Với bốn đơn hàng đầu bài, có thể dùng các kỳ vọng:

| Trường hợp | Thứ tự mong đợi |
|---|---|
| Static `CreatedAtDescIdDesc` | 105, 104, 103, 102 |
| Dynamic `total DESC, id DESC` | 102, 104, 103, 105 |
| Dynamic `total ASC, id DESC` | 105, 103, 104, 102 |
| Static `createdAt DESC` rồi dynamic `total DESC, id DESC` trong bối cảnh JPA đã nêu | 104, 105, 103, 102 |
| Lấy tối đa 2 theo `createdAt DESC, id DESC` | 105, 104 |

Dữ liệu có hai đơn cùng thời điểm giúp phát hiện lỗi thứ tự phân xử. Nếu mọi giá trị đều khác nhau, tiêu chí phụ sai hoặc bị thiếu có thể không lộ ra.

Ngoài ra cần xem các trường hợp:

- Không có kết quả.
- Một phần tử.
- Nhiều phần tử cùng tiêu chí chính.
- Khóa sort không hợp lệ và hướng không hợp lệ.
- Không truyền lựa chọn sort, dùng chính sách mặc định.
- Collection rỗng hoặc giá trị null ở thuộc tính có liên quan nếu domain cho phép.
- Truy vấn phân trang, đặc biệt ranh giới giữa hai trang.
- Loại query/store thực tế có giới hạn sort riêng.

Một mock repository không tự chứng minh cách module ghép static/dynamic. Kiểm chứng quy tắc ghép và query cần đi qua repository thật phù hợp với dự án.

Không cần kỳ vọng truy vấn thiếu khóa phân xử phải luôn đổi thứ tự giữa hai lần chạy mới được coi là chưa xác định. Việc hai lần tình cờ giống nhau không tạo ra bảo đảm mới.

## 14. Bài tập vận dụng

### Bài tập 1: Đọc đúng tham số và thứ tự

Phương thức:

```java
findByStatusOrderByCreatedAtDescIdDesc(String status)
```

có cần nhận thêm `createdAt` và `id` làm đối số không?

**Gợi ý lời giải:** Không. Hai thuộc tính sau `OrderBy` mô tả thứ tự. Đối số `status` phục vụ điều kiện lọc trước `OrderBy`.

### Bài tập 2: Sort động có thay được ưu tiên tĩnh không?

Trong derived query JPA theo cơ chế đã nêu, phương thức có `OrderByCreatedAtDesc`. Caller truyền `Sort.by("total").descending()` và mong đơn tổng tiền lớn nhất đứng đầu toàn bộ kết quả.

**Gợi ý lời giải:** Kỳ vọng đó không khớp cách ghép. `createdAt DESC` vẫn là tiêu chí chính, `total DESC` chỉ phân xử sau. Muốn caller chọn tiêu chí chính, dùng phương thức chỉ nhận Sort và giải quyết mặc định ở service/API.

### Bài tập 3: Tiêu chí không còn cơ hội phân xử

Thứ tự cuối cùng là:

```text
createdAt DESC, id DESC, total ASC
```

Với id duy nhất, `total ASC` có thể đổi thứ tự giữa hai đơn không?

**Gợi ý lời giải:** Không. Sau tiêu chí id không còn hai đơn khác nhau bằng nhau để total phân xử. Đặt id sau những tiêu chí nghiệp vụ cần có ảnh hưởng.

### Bài tập 4: Sort trong Java sau khi lấy trang

Service lấy trang đầu 20 đơn theo một thứ tự khác, rồi sort 20 đơn đó theo tổng tiền giảm dần. Có thể gọi đây là 20 đơn tổng tiền cao nhất của toàn bộ tập không?

**Gợi ý lời giải:** Không. Service chỉ sắp lại phần dữ liệu đã được chọn. Thứ tự cần quyết định nhóm bản ghi trong trang phải được áp dụng trước giới hạn kết quả ở query phù hợp.

### Bài tập 5: Phân biệt tên cột và thuộc tính

Cột là `created_at`, thuộc tính Java là `createdAt`. Trong derived query JPA thông thường, nên truyền tên nào vào Sort?

**Gợi ý lời giải:** Dùng `createdAt`. Mapping chuyển nó sang tên cột. Không áp dụng tùy ý quy tắc tên cột hoặc alias của một query đặc thù cho mọi repository.

### Bài tập 6: NullsLast đã được mô tả

Code tạo được `Sort.Order.asc("customer.name").nullsLast()`. Có thể kết luận mọi store/query sẽ đưa null xuống cuối không?

**Gợi ý lời giải:** Không. Đây là yêu cầu trong mô tả sort. Cần xác nhận khả năng của module, loại query và store; có trường hợp tùy chọn không được áp dụng hoặc bị từ chối.

### Bài tập 7: Thứ tự xác định và dữ liệu thay đổi

Đã có `createdAt DESC, id DESC`. Có thể cam kết offset pagination không bao giờ lặp hoặc bỏ qua phần tử khi dữ liệu liên tục được thêm/xóa không?

**Gợi ý lời giải:** Không. Khóa phân xử làm rõ thứ tự trên tập dữ liệu đang xét, nhưng không tạo snapshot. Yêu cầu cuộn nhất quán cần được thiết kế theo cơ chế phân trang và tính nhất quán của store.

## 15. Những điều cần ghi nhớ

- `OrderBy` trong tên phương thức đặt thứ tự tĩnh cho query được suy diễn.
- `Sort` hoặc sort trong `Pageable` cho phép caller đưa ra yêu cầu thứ tự động trong phạm vi module hỗ trợ.
- Tiêu chí được xét từ trái sang phải; khóa duy nhất nên đặt sau những tiêu chí còn cần phân xử.
- Trong derived query JPA đã minh họa, phần động nối sau phần tĩnh, không tự ghi đè nó.
- `Sort.and` ghép mô tả và trả giá trị mới; hãy dùng đối tượng kết quả.
- Thứ tự phải được áp dụng trước giới hạn/phân trang nếu nó quyết định nhóm bản ghi cần lấy.
- Dùng tên thuộc tính/domain path theo hợp đồng query, giới hạn lựa chọn công khai và thêm khóa phân xử có chủ đích.
- Mapping, null handling, collation, index và khả năng từng store vẫn quyết định hành vi thực tế.
