# Wrapper miền nhận Streamable và quy tắc được framework nhận diện

## 1. Vì sao trả về một wrapper miền?

Một truy vấn nhiều phần tử thường trả về `List<Invoice>`. Nếu nhiều nơi cùng tính tổng tiền hoặc lọc hóa đơn theo cùng quy tắc, các thao tác đó dễ bị viết lặp trong service.

Một wrapper miền như `Invoices` đặt tên cho cả tập kết quả và cung cấp API gắn với nghiệp vụ:

```java
Invoices invoices = repository.findByStatusOrderByIdAsc("PENDING");

BigDecimal total = invoices.totalAmountVnd();
Invoices largeInvoices = invoices.atLeast(new BigDecimal("100000"));
```

Ở đây, `Invoice` biểu diễn một hóa đơn, còn `Invoices` biểu diễn một nhóm hóa đơn đã được truy vấn. Wrapper không phải một entity mới để lưu vào database.

Spring Data Commons có cơ chế cho phép dùng wrapper dạng này trực tiếp làm kiểu trả về của query method. Mục tiêu của bài là hiểu hợp đồng nhận diện và thiết kế wrapper hoạt động đúng trong phạm vi đó.

## 2. Hai điều kiện nhận diện cốt lõi

Theo [Spring Data Commons — Returning Custom Streamable Wrapper Types](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.collections-and-iterables.streamable-wrapper), wrapper cần:

1. Triển khai `org.springframework.data.util.Streamable<T>`.
2. Cung cấp constructor nhận `Streamable`, hoặc static factory tên `of` hay `valueOf` nhận `Streamable`.

Một trong các dạng điểm vào sau là đủ cho phần tạo wrapper:

```java
public Invoices(Streamable<Invoice> source)

// Hoặc:
public static Invoices of(Streamable<Invoice> source)

// Hoặc:
public static Invoices valueOf(Streamable<Invoice> source)
```

Đây là các chữ ký minh họa thay thế nhau, không phải khai báo đặt đồng thời vào một file Java chưa có thân phương thức.

Ngoài điểm vào, lớp phải triển khai hợp đồng duyệt phần tử. Cách thông dụng là giữ một `Streamable<Invoice>` và ủy quyền `iterator()` cho đối tượng đó.

Không cần một annotation chuyên biệt để đánh dấu wrapper cho cơ chế này. Việc đặt tên lớp số nhiều chỉ giúp người đọc; framework dựa vào kiểu và điểm tạo đối tượng phù hợp.

### 2.1. Vì sao chỉ có một field là chưa đủ?

Khai báo sau chỉ thể hiện quan hệ chứa dữ liệu:

```java
final class Invoices {
    private final Streamable<Invoice> source;

    public Invoices(Streamable<Invoice> source) {
        this.source = source;
    }
}
```

Lớp này chưa triển khai `Streamable<Invoice>`, nên chưa đáp ứng cả hai điều kiện. Tương tự, triển khai riêng `Iterable<Invoice>` không thay thế được điều kiện triển khai `Streamable` của cơ chế wrapper đang học.

### 2.2. Tên factory và tham số có ý nghĩa

| Thiết kế duy nhất được cung cấp | Đánh giá theo hợp đồng trong bài |
|---|---|
| Constructor `Invoices(Streamable<Invoice>)` | Đúng dạng đầu vào |
| Static `Invoices of(Streamable<Invoice>)` | Đúng tên và dạng đầu vào |
| Static `Invoices valueOf(Streamable<Invoice>)` | Đúng tên và dạng đầu vào |
| Static `Invoices from(Streamable<Invoice>)` | `from` không thuộc hai tên factory được công bố |
| Static `Invoices of(List<Invoice>)` | Không phải điểm vào nhận `Streamable` được yêu cầu |
| Static `Invoices of(Stream<Invoice>)` | Nhầm Java `Stream` với Spring Data `Streamable` |
| Instance method `Invoices of(Streamable<Invoice>)` | Không phải static factory |
| Constructor `Invoices(Streamable<Invoice>, String currency)` | Cần thêm đối số mà hợp đồng tạo wrapper không cung cấp |
| Chỉ có builder | Builder không tự trở thành constructor/factory theo hợp đồng này |

Bảng giả định lớp không còn một constructor hoặc factory hợp lệ khác. Khi thiết kế, nên cung cấp một điểm vào rõ ràng và trả về chính kiểu wrapper; tránh dựa vào cách framework lựa chọn giữa nhiều overload.

## 3. Streamable cung cấp những gì?

`Streamable<T>` mở rộng `Iterable<T>` và `Supplier<Stream<T>>`. Nó có các thao tác tiện ích như `stream()`, `map()`, `filter()`, `and()`, `toList()`; `stream()` mặc định tạo stream không song song từ dữ liệu bên dưới. Xem [Javadoc Streamable](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/util/Streamable.html).

Đối với wrapper, phần phải cung cấp thường chỉ là:

```java
@Override
public Iterator<Invoice> iterator() {
    return source.iterator();
}
```

Các phương thức mặc định sẽ sử dụng khả năng duyệt này. Tuy nhiên, chữ `Streamable` không bảo đảm truy vấn database được đọc lười, không tự mở cursor và không cam kết bộ nhớ hằng số.

Cần phân biệt các lớp hành vi:

| Thành phần | Trách nhiệm |
|---|---|
| Query method | Chọn dữ liệu theo điều kiện và thứ tự mà store hỗ trợ |
| Cơ chế chuyển đổi kết quả | Tạo wrapper phù hợp từ tập kết quả |
| `Streamable` | Cung cấp khả năng duyệt và biến đổi tập phần tử |
| Wrapper miền | Đặt tên nghiệp vụ và đóng gói các thao tác trên tập kết quả |
| Service | Phối hợp transaction, phân quyền và các bước nghiệp vụ có tác động |

Một phép `filter` gọi trên wrapper là thao tác Java trên nguồn dữ liệu của wrapper. Nó không tự bổ sung điều kiện `WHERE` vào truy vấn đã được repository thực thi.

## 4. Ví dụ đầy đủ về wrapper Invoices

### 4.1. Hợp đồng dữ liệu của ví dụ

Giả sử `Invoice` đã là entity được ánh xạ phù hợp với store và có các thuộc tính:

| Thuộc tính | Kiểu | Giả định |
|---|---|---|
| `id` | `Long` | Định danh hóa đơn |
| `status` | `String` | Ví dụ `PENDING`, `PAID` |
| `amountVnd` | `BigDecimal` | Khác null, không âm, cùng đơn vị VND |

Entity cung cấp `getId()`, `getStatus()`, `getAmountVnd()`. Phần mapping entity phụ thuộc store, còn wrapper dưới đây không dùng annotation của JPA hay MongoDB.

Việc cố định đơn vị VND giúp phép cộng trong ví dụ có nghĩa. Nếu dữ liệu có nhiều loại tiền, cần quy tắc gom nhóm hoặc chuyển đổi tiền tệ riêng; không cộng các số tiền khác đơn vị thành một tổng.

### 4.2. Triển khai bằng static factory

```java
import java.math.BigDecimal;
import java.util.Iterator;
import java.util.Objects;

import org.springframework.data.util.Streamable;

public final class Invoices implements Streamable<Invoice> {

    private final Streamable<Invoice> source;

    private Invoices(Streamable<Invoice> source) {
        this.source = Objects.requireNonNull(source, "source");
    }

    public static Invoices of(Streamable<Invoice> source) {
        return new Invoices(source);
    }

    @Override
    public Iterator<Invoice> iterator() {
        return source.iterator();
    }

    public BigDecimal totalAmountVnd() {
        return stream()
                .map(Invoice::getAmountVnd)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public Invoices atLeast(BigDecimal minimumAmountVnd) {
        Objects.requireNonNull(minimumAmountVnd, "minimumAmountVnd");

        if (minimumAmountVnd.signum() < 0) {
            throw new IllegalArgumentException(
                    "minimumAmountVnd must not be negative");
        }

        return Invoices.of(filter(invoice ->
                invoice.getAmountVnd()
                        .compareTo(minimumAmountVnd) >= 0));
    }
}
```

Điểm tạo đối tượng được công khai là `of(Streamable<Invoice>)`. Constructor riêng phục vụ việc triển khai factory. Không cần vừa công khai constructor vừa tạo hai factory khác nhau.

`iterator()` chuyển việc duyệt cho nguồn đang bọc. `totalAmountVnd()` cộng tiền của các phần tử hiện có. `atLeast()` bổ sung ý nghĩa nghiệp vụ và trả về một `Invoices` mới.

Giá trị tổng được tính lại mỗi lần gọi. Cách này tránh giữ một tổng đã cache nhưng không còn khớp khi các entity bên dưới thay đổi.

### 4.3. Khai báo repository

```java
import org.springframework.data.repository.Repository;

public interface InvoiceRepository extends Repository<Invoice, Long> {

    Invoices findByStatusOrderByIdAsc(String status);
}
```

Repository khai báo entity là `Invoice`, không phải `Invoices`. Phần tên `findByStatusOrderByIdAsc` mô tả truy vấn; kiểu trả về mô tả cách tập kết quả được đưa cho bên gọi.

Ví dụ giả định store và phiên bản đang dùng hỗ trợ kiểu trả về này. Danh sách kiểu trả về của Commons là hợp đồng tổng quát; cần đối chiếu hỗ trợ cụ thể ở module store. Xem [Repository query return types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html).

Luồng xử lý có thể hiểu ở mức khái niệm như sau:

```text
Bên gọi repository
        |
        v
Thực thi truy vấn lấy các Invoice
        |
        v
Chuẩn bị kết quả có thể duyệt bằng Streamable
        |
        v
Tạo Invoices qua điểm vào phù hợp
        |
        v
Trả Invoices cho bên gọi
```

Sơ đồ mô tả trách nhiệm, không yêu cầu mọi store có cùng cấu trúc lớp nội bộ.

### 4.4. Kết quả nghiệp vụ mong đợi

Với các hóa đơn `PENDING` sau:

| id | amountVnd |
|---|---:|
| 1 | 120000 |
| 2 | 80000 |
| 3 | 150000 |

Đoạn sử dụng:

```java
Invoices pending =
        repository.findByStatusOrderByIdAsc("PENDING");

BigDecimal total = pending.totalAmountVnd();

Invoices selected =
        pending.atLeast(new BigDecimal("100000"));

BigDecimal selectedTotal = selected.totalAmountVnd();
```

Kết quả mong đợi:

- `total` có giá trị số học là 350000 VND.
- `selected` gồm hóa đơn 1 và 3.
- `selectedTotal` có giá trị số học là 270000 VND.

Bộ lọc ngưỡng trong đoạn này chạy trên tập hóa đơn đã lấy về. Nếu cần giảm số hàng đọc từ database, phải đưa ngưỡng vào query method hoặc đường query phù hợp của store.

## 5. Khi nào dùng constructor, khi nào dùng factory?

### 5.1. Constructor công khai

Một thiết kế thay thế là bỏ factory và công khai constructor:

```java
public Invoices(Streamable<Invoice> source) {
    this.source = Objects.requireNonNull(source, "source");
}
```

Các phần khác của wrapper vẫn triển khai `Streamable<Invoice>` như cũ. Vì biến thể này bỏ factory `of`, lời gọi `Invoices.of(...)` trong `atLeast()` cũng cần đổi thành `new Invoices(...)`. Thiết kế này đơn giản khi việc tạo wrapper không cần một tên riêng.

### 5.2. Factory valueOf

Nếu nhóm phát triển chọn quy ước `valueOf`, có thể thay factory `of` bằng:

```java
public static Invoices valueOf(Streamable<Invoice> source) {
    return new Invoices(source);
}
```

Khi thay theo cách này, lời gọi nội bộ trong `atLeast()` cũng phải đổi sang `Invoices.valueOf(...)`.

Không cần thêm nhiều điểm tạo đối tượng để “giúp framework dễ tìm”. Một điểm vào đủ điều kiện, có kiểu tham số rõ ràng và hành vi nhất quán giúp giảm nhầm lẫn.

### 5.3. Wrapper không phải bean có dependency được tự inject

Constructor/factory dành cho chuyển đổi kết quả nên tập trung vào dữ liệu đang bọc. Không thêm repository, service, thông tin người dùng hoặc exchange-rate client vào chữ ký bắt buộc.

Nếu việc tính tổng cần tỷ giá, thời điểm định giá hoặc quyền của người gọi, service có thể nhận `Invoices` rồi phối hợp thêm ngữ cảnh. Cơ chế tạo wrapper từ `Streamable` không phải hợp đồng dependency injection.

Factory cũng nên tránh gọi truy vấn hoặc tạo tác động phụ. Việc tính toán đắt ngay trong factory sẽ khiến mọi lần gọi repository phải trả chi phí đó, kể cả khi bên gọi chỉ muốn duyệt phần tử.

## 6. Tập rỗng, null và tính bất biến

### 6.1. Chấp nhận một tập kết quả rỗng

Một truy vấn nhiều kết quả có thể không tìm thấy phần tử nào. Wrapper nên biểu diễn được trường hợp này:

```java
Invoices empty = Invoices.of(Streamable.<Invoice>empty());

boolean noInvoices = empty.isEmpty();
BigDecimal total = empty.totalAmountVnd();
```

`noInvoices` là `true`; tổng có giá trị bằng không nhờ giá trị khởi đầu của phép `reduce`.

Không nên ném ngoại lệ chỉ vì nguồn rỗng nếu hợp đồng của truy vấn cho phép không có kết quả. Spring Data phân biệt kết quả nhiều phần tử rỗng với việc không tìm thấy một phần tử đơn lẻ; xem [Null Handling of Repository Methods](https://docs.spring.io/spring-data/commons/reference/repositories/null-handling.html).

### 6.2. Nguồn null là lỗi đầu vào khác

`Objects.requireNonNull(source)` trong wrapper bảo vệ invariant: luôn có một đối tượng nguồn để duyệt. Nó không cấm nguồn rỗng.

Đối với `amountVnd`, ví dụ đã giả định từng entity có giá trị khác null. Nếu dữ liệu thực tế cho phép null, phải quyết định rõ đó là lỗi dữ liệu, trạng thái chưa xác định hay số không theo quy tắc nghiệp vụ. Tự đổi null thành zero có thể che mất hóa đơn chưa có số tiền.

### 6.3. Field final không làm toàn bộ kết quả bất biến

`private final Streamable<Invoice> source` chỉ ngăn thay tham chiếu nguồn sau khi tạo wrapper. Nó không ngăn:

- Collection được bọc bị sửa ở nơi khác.
- Iterator được ủy quyền có khả năng thay đổi collection.
- Thuộc tính của một entity `Invoice` bị cập nhật.

Nếu muốn cố định thành phần của tập kết quả khi tạo wrapper, có thể chụp một danh sách:

```java
private Invoices(Streamable<Invoice> source) {
    Objects.requireNonNull(source, "source");
    this.source = Streamable.of(source.toList());
}
```

`toList()` tạo danh sách không cho sửa cấu trúc theo Javadoc. Tuy vậy, đây vẫn là bản sao nông: các phần tử `Invoice` giữ nguyên tham chiếu. Nó không đóng băng trạng thái entity, không tải trước mọi quan hệ lazy và có chi phí duyệt cùng lưu toàn bộ nguồn.

Chỉ chọn cách chụp này khi cần semantics đó và tập dữ liệu có kích thước phù hợp.

## 7. Những điều wrapper không tự cung cấp

### 7.1. Không tự giữ kiểu miền sau mọi phép biến đổi

Các phương thức kế thừa có kiểu trả về theo hợp đồng `Streamable`:

```java
Streamable<Invoice> filtered =
        pending.filter(invoice ->
                invoice.getAmountVnd().signum() > 0);
```

`filtered` không tự trở thành `Invoices`. Cơ chế bọc kết quả repository không chạy lại sau mỗi lời gọi Java thông thường.

Nếu cần tiếp tục gọi API miền, bọc rõ ràng:

```java
Invoices positive = Invoices.of(filtered);
```

Phương thức `atLeast()` trong ví dụ đã thực hiện bước này cho bên gọi.

### 7.2. Không tự biến tổng trong Java thành truy vấn tổng hợp

`totalAmountVnd()` cộng tiền của các phần tử wrapper đang chứa. Nó không tự thực hiện `SUM(amount)` trên toàn bộ bảng.

Nếu query chỉ lấy 20 hóa đơn, tổng là của 20 hóa đơn. Nếu cần một tổng ở database mà không đọc từng entity, nên có truy vấn aggregate riêng được store hỗ trợ.

### 7.3. Không tự mang metadata phân trang

`Streamable` mô tả khả năng duyệt, không tự bổ sung tổng số bản ghi, số trang hoặc cursor tiếp theo. Nếu nghiệp vụ cần các metadata này, cần chọn `Page`, `Slice`, `Window` hoặc thiết kế kết quả chuyên biệt tương ứng.

Đừng thêm một field `totalElements` vào wrapper rồi kỳ vọng factory chỉ nhận `Streamable` tự biết tổng số hàng của toàn bộ query.

### 7.4. Không tự chuyển thành luồng đọc database

Java `Stream` có vòng đời riêng và chỉ nên được sử dụng một lần. Lưu một stream duy nhất rồi trả lại iterator của nó nhiều lần là thiết kế lỗi:

```java
// Không dùng cách giữ cùng một Stream để duyệt lại.
private final Stream<Invoice> oneStream;

@Override
public Iterator<Invoice> iterator() {
    return oneStream.iterator();
}
```

Một lần tính tổng có thể đã tiêu thụ stream đó; lần duyệt tiếp theo có thể thất bại. Hợp đồng sử dụng stream được mô tả trong [Java Stream API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).

Thiết kế wrapper nên có nguồn phù hợp với cách dùng mong đợi. Với nguồn collection đã có trong bộ nhớ, việc tạo iterator mới thường cho phép duyệt lại. Với nguồn tự viết, cần kiểm tra cụ thể khả năng này.

Wrapper cũng không thay thế quản lý transaction. Nếu phép tính truy cập quan hệ lazy của entity JPA, việc thành công vẫn phụ thuộc ranh giới persistence context và chiến lược tải dữ liệu.

## 8. Metadata kiểu và phạm vi hỗ trợ

Khai báo `implements Streamable<Invoice>` cho biết kiểu phần tử của wrapper. Nên giữ generic cụ thể thay vì dùng raw type:

```java
// Tránh làm mất thông tin kiểu.
class Invoices implements Streamable {
    // ...
}
```

Wrapper là lớp cụ thể như `Invoices` thường dễ đọc hơn một wrapper chung chứa kiểu chưa được xác định. Nếu dùng `ResultGroup<T>`, phải xác định được `T` tại chữ ký repository và kiểm tra hành vi trên bộ phiên bản thực tế.

Các điểm cần phân biệt khi áp dụng:

| Thông tin | Vai trò |
|---|---|
| `Repository<Invoice, Long>` | Khai báo domain type và ID của repository |
| `Invoices implements Streamable<Invoice>` | Khai báo wrapper cho tập phần tử `Invoice` |
| Constructor/factory nhận `Streamable<Invoice>` | Điểm tạo wrapper từ dữ liệu trả về |
| Mapping của `Invoice` | Chuyển dữ liệu store thành phần tử |
| Mapping DTO/projection nếu có | Một cơ chế khác, cần cấu hình và hỗ trợ tương ứng |

Một constructor nhận DTO đơn lẻ không thay thế constructor nhận cả `Streamable`. Wrapper của tập kết quả cũng không tự trở thành projection cho từng hàng.

Khi đổi store hoặc nâng phiên bản, cần kiểm tra query method thực tế trả về wrapper và dữ liệu bên trong đúng kiểu. Việc gọi `Invoices.of(...)` thủ công thành công mới xác minh mã wrapper; nó chưa xác minh đường chuyển đổi của repository.

## 9. Các tình huống thực hành cần quan sát

Không cần thay đổi cả ứng dụng để hiểu cơ chế. Có thể bắt đầu với tập dữ liệu nhỏ và kết quả có thể tính bằng tay:

| Tình huống | Kết quả mong đợi |
|---|---|
| Gọi repository với trạng thái có ba hóa đơn của ví dụ | Nhận `Invoices`, duyệt đủ ba phần tử |
| Trạng thái không có hóa đơn | Nhận kết quả wrapper rỗng theo đường query hỗ trợ, không yêu cầu có ít nhất một phần tử |
| Gọi tổng rồi duyệt lại nguồn collection | Hai thao tác cùng hoạt động |
| Lọc ngưỡng 100000 | Còn hóa đơn 1 và 3, tổng 270000 |
| Ngưỡng âm | `atLeast()` từ chối đầu vào theo quy tắc của ví dụ |
| Factory được đổi tên thành `from` và không còn điểm vào hợp lệ khác | Phát hiện wrapper không đáp ứng hợp đồng nhận diện |
| Field nguồn đổi từ `Streamable` sang `List`, constructor cũng đổi theo | Kiểm tra lại vì chữ ký được framework yêu cầu đã bị thay đổi |
| Query có giới hạn số phần tử | Tổng của wrapper chỉ phản ánh số phần tử đã lấy |
| Dùng wrapper với quan hệ lazy | Quan sát transaction và số truy vấn phát sinh |
| Nguồn hoặc entity bị sửa sau khi tạo wrapper | Kết quả phải phù hợp với lựa chọn ủy quyền hoặc chụp dữ liệu đã công bố |

Đây là các tình huống để kiểm chứng khi đưa mẫu vào dự án, không phải kết quả thực thi đã được xác nhận cho một store chưa được chỉ định.

## 10. Lựa chọn thiết kế trong thực tế

Nên dùng wrapper miền khi nó giúp bên gọi hiểu tập kết quả và có các thao tác lặp lại mang ý nghĩa nghiệp vụ. Ví dụ, `Invoices.totalAmountVnd()` hoặc `Invoices.atLeast(...)` diễn đạt rõ hơn các đoạn stream giống nhau xuất hiện ở nhiều service.

Nếu chỉ cần trả vài phần tử cho một nơi sử dụng và không có hành vi chung, `List<Invoice>` hoặc `Streamable<Invoice>` có thể đã đủ. Nếu cần kết quả phân trang, tổng hợp ở database hoặc đọc lượng dữ liệu rất lớn, hãy chọn hợp đồng phù hợp trước khi thêm wrapper.

Một thiết kế có thể bàn giao rõ ràng cần nêu được: kiểu phần tử, điểm tạo wrapper được nhận diện, hành vi khi rỗng, quy tắc tính toán và nguồn dữ liệu có thể duyệt lại hay không. Những lựa chọn đó giữ cho API miền gọn mà vẫn phản ánh đúng khả năng của repository và store.
