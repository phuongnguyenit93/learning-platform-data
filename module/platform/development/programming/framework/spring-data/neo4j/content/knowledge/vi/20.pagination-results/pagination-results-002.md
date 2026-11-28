# Pageable, PageRequest và Sort trong truy vấn suy diễn

Khi một ứng dụng Spring Data Neo4j cần hiển thị danh sách sản phẩm, nhân viên hoặc đơn hàng theo từng trang, không nên tải toàn bộ kết quả rồi tự cắt danh sách trong bộ nhớ. Spring Data cung cấp `Pageable`, `PageRequest` và `Sort` để truyền yêu cầu phân trang, sắp xếp trực tiếp vào repository method. Với truy vấn suy diễn, SDN có thể áp dụng các thông tin này khi xây dựng truy vấn Cypher.

Ba khái niệm có vai trò khác nhau: `Pageable` mô tả trang và kích thước trang, `PageRequest` là một cách tạo đối tượng `Pageable`, còn `Sort` mô tả thứ tự kết quả. Chọn đúng kiểu trả về (`Page`, `Slice` hoặc `List`) giúp cân bằng metadata cần cho giao diện với chi phí truy vấn.

## 1. Vì sao cần phân trang ở repository?

Giả sử hệ thống có hàng trăm nghìn sản phẩm. Một màn hình chỉ cần hiển thị 20 sản phẩm mỗi lần. Nếu repository trả về toàn bộ danh sách, ứng dụng phải truyền và giữ nhiều dữ liệu hơn mức giao diện cần.

Phân trang giới hạn số kết quả lấy cho một lần truy vấn. Với Neo4j, SDN có thể đưa giới hạn và vị trí bắt đầu tương ứng vào truy vấn được sinh ra. Ứng dụng chỉ nhận phần dữ liệu cần cho trang hiện tại.

Các lợi ích chính:

- Giảm số node được trả về trong mỗi lần gọi repository.
- Giảm dữ liệu truyền từ Neo4j đến ứng dụng.
- Giúp API và giao diện điều hướng theo trang.
- Cho phép chọn thứ tự ổn định và lặp lại giữa các lần truy vấn.
- Tránh tải toàn bộ kết quả vào bộ nhớ khi chỉ cần một phần.

Phân trang không làm cho một truy vấn vốn kém chọn lọc trở nên hiệu quả trong mọi trường hợp. Cần kết hợp điều kiện lọc, index và thứ tự sắp xếp phù hợp.

## 2. Khai báo Pageable trong repository method

`Pageable` nằm trong package `org.springframework.data.domain`. Có thể thêm tham số `Pageable` vào method truy vấn suy diễn để nhận trang và kích thước trang từ phía gọi:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ProductRepository extends Neo4jRepository<Product, String> {

    Page<Product> findByStatus(String status, Pageable pageable);
}
```

Tên method `findByStatus` yêu cầu SDN tìm các node `Product` có property `status` bằng giá trị truyền vào. `Pageable` yêu cầu repository chỉ trả về phần kết quả thuộc trang đã chọn.

`Pageable` là interface mô tả yêu cầu phân trang. Trong ứng dụng thông thường, không cần tự cài đặt interface này; hãy tạo đối tượng bằng `PageRequest`.

## 3. Tạo yêu cầu trang bằng PageRequest

`PageRequest` là implementation phổ biến của `Pageable`. Phương thức `PageRequest.of(page, size)` nhận chỉ số trang và số phần tử tối đa trong một trang:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

Pageable pageable = PageRequest.of(0, 20);
Page<Product> result = productRepository.findByStatus("ACTIVE", pageable);
```

Các điểm cần nhớ:

- Chỉ số trang bắt đầu từ `0`; `PageRequest.of(0, 20)` là trang đầu tiên.
- `PageRequest.of(1, 20)` là trang thứ hai.
- `size` là số phần tử tối đa muốn nhận trong một trang.
- `page` không được âm và `size` phải lớn hơn `0`.

Ví dụ, với `size = 20`, trang thứ ba có offset tương đương 40 phần tử đầu tiên. Ứng dụng không cần tự tính offset khi dùng `PageRequest`; Spring Data xử lý thông tin đó.

Có thể tạo `PageRequest` với sắp xếp ngay trong cùng lời gọi:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.DESC, "name")
);
```

Không truyền `null` cho tham số `Pageable`. Nếu use case thực sự không cần phân trang, dùng `Pageable.unpaged()` thay cho null.

## 4. Sắp xếp với Sort

`Sort` mô tả thứ tự kết quả theo một hoặc nhiều thuộc tính. Có thể tạo sắp xếp tăng dần hoặc giảm dần:

```java
import org.springframework.data.domain.Sort;

Sort ascendingByName = Sort.by("name").ascending();
Sort descendingByPrice = Sort.by(Sort.Direction.DESC, "priceMinor");
```

Trong truy vấn suy diễn, có thể truyền `Sort` trực tiếp nếu chỉ cần sắp xếp và không cần phân trang:

```java
import java.util.List;
import org.springframework.data.domain.Sort;

List<Product> findByStatus(String status, Sort sort);
```

Gọi method:

```java
List<Product> products = productRepository.findByStatus(
        "ACTIVE",
        Sort.by("name").ascending()
);
```

Tên thuộc tính trong `Sort` phải tương ứng với property được ánh xạ trong entity, ví dụ `name` hoặc `priceMinor`. Không tùy tiện dùng tên cột trong một bảng quan hệ SQL hoặc tên hiển thị không tồn tại trong entity.

### Sắp xếp theo nhiều thuộc tính

Khi nhiều node có cùng giá trị ở thuộc tính đầu tiên, có thể thêm tiêu chí phụ để thứ tự rõ ràng hơn:

```java
Sort sort = Sort.by(Sort.Order.asc("status"))
        .and(Sort.by(Sort.Order.desc("createdAt")))
        .and(Sort.by(Sort.Order.asc("sku")));
```

Thứ tự trên sắp xếp theo `status` tăng dần, sau đó `createdAt` giảm dần, cuối cùng `sku` tăng dần. Thuộc tính cuối nên có giá trị phân biệt ổn định, thường là định danh nghiệp vụ hoặc ID phù hợp với mô hình.

Sắp xếp nhiều tiêu chí rất hữu ích cho phân trang: nếu nhiều node có cùng giá trị ở tiêu chí chính, tiêu chí phụ giúp tránh thứ tự không xác định giữa các lần truy vấn.

## 5. Kết hợp PageRequest và Sort

`PageRequest` có thể nhận `Sort` làm đối số thứ ba:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"))
                .and(Sort.by(Sort.Order.asc("orderId")))
);

Page<PurchaseOrder> page = orderRepository.findByStatus("OPEN", pageable);
```

Trong ví dụ, mỗi trang có tối đa 20 đơn hàng. Đơn mới hơn đứng trước; nếu thời điểm tạo giống nhau, `orderId` được dùng làm tiêu chí phụ.

`Pageable` đã bao gồm thông tin `Sort`, vì vậy không truyền thêm một tham số `Sort` riêng cùng method có `Pageable`. Tương tự, `Pageable` đã xác định giới hạn số phần tử nên không kết hợp thêm tham số `Limit` trong cùng method query.

## 6. Page, Slice và List khác nhau thế nào?

Spring Data hỗ trợ nhiều kiểu kết quả cho method có `Pageable`. Hãy chọn theo metadata mà ứng dụng thực sự cần.

| Kiểu trả về | Thông tin có sẵn | Chi phí và cách dùng |
|---|---|---|
| `Page<T>` | Nội dung trang, số phần tử toàn bộ, tổng số trang | Cần count query để xác định tổng số; phù hợp khi giao diện cần số trang |
| `Slice<T>` | Nội dung lát kết quả và thông tin còn trang tiếp theo hay không | Không cần tổng số toàn bộ; phù hợp với nút “Xem thêm” hoặc cuộn tiếp |
| `List<T>` | Chỉ có các phần tử của phạm vi trang được yêu cầu | Không tạo metadata Page và không cần count query chỉ để tính tổng |

### Dùng Page khi cần tổng số trang

```java
Page<Product> findByStatus(String status, Pageable pageable);
```

Một `Page` cung cấp các thông tin như:

```java
page.getContent();       // Danh sách phần tử của trang hiện tại
page.getNumber();        // Chỉ số trang, bắt đầu từ 0
page.getSize();          // Kích thước trang được yêu cầu
page.getTotalElements(); // Tổng số phần tử phù hợp điều kiện
page.getTotalPages();    // Tổng số trang
page.hasNext();          // Có trang tiếp theo không
page.isFirst();          // Có phải trang đầu tiên không
```

Để tính `totalElements` và `totalPages`, Spring Data cần chạy count query. Với truy vấn suy diễn, count query thường được suy ra từ điều kiện truy vấn chính. Trên graph lớn hoặc điều kiện lọc phức tạp, phép đếm này có thể tốn chi phí đáng kể.

### Dùng Slice khi chỉ cần biết còn dữ liệu hay không

```java
import org.springframework.data.domain.Slice;

Slice<Product> readByStatus(String status, Pageable pageable);
```

`Slice` cho biết có phần kết quả tiếp theo hay không mà không cung cấp tổng số phần tử và tổng số trang. Hạ tầng thường đọc thêm một phần tử ngoài kích thước trang để xác định `hasNext()`.

Đây là lựa chọn phù hợp cho giao diện “Tải thêm” hoặc luồng duyệt dữ liệu tuần tự khi không cần hiển thị “Trang 3 trên 18”.

### Dùng List khi chỉ cần phần dữ liệu

```java
import java.util.List;

List<Product> findAllByStatus(String status, Pageable pageable);
```

Với `List`, repository chỉ trả về các phần tử trong phạm vi trang. Ứng dụng không nhận metadata của `Page` và không cần count query chỉ để tính tổng số. Nếu giao diện cần tổng số trang, hãy chọn `Page`.

## 7. Ví dụ hoàn chỉnh với truy vấn suy diễn

Giả sử entity sản phẩm có các property `sku`, `name`, `status`, `priceMinor` và `createdAt`:

```java
import java.time.LocalDateTime;

import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Product")
public class Product {

    @Id
    private String sku;

    private String name;
    private String status;
    private long priceMinor;
    private LocalDateTime createdAt;

    protected Product() {
    }
}
```

Repository cung cấp các lựa chọn trả về:

```java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ProductRepository extends Neo4jRepository<Product, String> {

    Page<Product> findByStatus(String status, Pageable pageable);

    Slice<Product> readByStatus(String status, Pageable pageable);

    List<Product> findAllByStatus(String status, Pageable pageable);

    List<Product> findByStatus(String status, Sort sort);
}
```

Các method có cùng điều kiện lọc nhưng phục vụ những nhu cầu kết quả khác nhau. Ứng dụng chọn method phù hợp với màn hình hoặc quy trình xử lý.

Ví dụ gọi repository để lấy trang đầu tiên gồm 20 sản phẩm đang hoạt động, sắp xếp theo thời điểm tạo mới nhất:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"))
                .and(Sort.by(Sort.Order.asc("sku")))
);

Page<Product> products = productRepository.findByStatus("ACTIVE", pageable);
```

Nếu chỉ cần duyệt tiếp:

```java
Slice<Product> products = productRepository.readByStatus("ACTIVE", pageable);

if (products.hasNext()) {
    Pageable nextPage = products.nextPageable();
    // Gọi repository với nextPage khi người dùng yêu cầu tải tiếp.
}
```

## 8. Xử lý tham số phân trang từ API

Spring MVC có thể tự bind tham số request thành `Pageable` khi ứng dụng đã có cấu hình Spring Data Web phù hợp. Ví dụ request:

```text
GET /products?status=ACTIVE&page=0&size=20&sort=createdAt,desc&sort=sku,asc
```

Controller có thể nhận `Pageable`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    private final ProductRepository products;

    public ProductController(ProductRepository products) {
        this.products = products;
    }

    @GetMapping("/products")
    public Page<Product> findProducts(
            @RequestParam String status,
            Pageable pageable) {
        return products.findByStatus(status, pageable);
    }
}
```

Các tham số thường dùng:

- `page`: chỉ số trang, bắt đầu từ `0`.
- `size`: số phần tử tối đa trong một trang.
- `sort`: thuộc tính và hướng sắp xếp; có thể truyền nhiều lần để tạo nhiều tiêu chí.

Không nên chấp nhận `size` không giới hạn từ client. Hãy đặt kích thước mặc định và giới hạn tối đa ở tầng API hoặc cấu hình resolver. Với `sort`, nên cho phép danh sách property được hỗ trợ thay vì chấp nhận mọi chuỗi do client gửi.

## 9. Sắp xếp ổn định và tránh kết quả trùng hoặc bị bỏ qua

Phân trang theo offset có thể cho kết quả thiếu ổn định nếu thứ tự không xác định. Ví dụ, nhiều sản phẩm có cùng `createdAt`; nếu chỉ sort theo `createdAt`, database có thể trả các node cùng thời điểm theo thứ tự khác nhau giữa hai lần gọi.

Hãy thêm một tiêu chí phụ có giá trị phân biệt ổn định:

```java
Sort sort = Sort.by(Sort.Order.desc("createdAt"))
        .and(Sort.by(Sort.Order.asc("sku")));
```

Thứ tự ổn định giúp giảm nguy cơ một node xuất hiện ở hai trang hoặc bị bỏ qua khi dữ liệu không đổi. Tuy nhiên, khi có bản ghi mới được thêm hoặc xóa giữa hai lần gọi, offset vẫn có thể dịch chuyển. Đây là đặc điểm của offset pagination.

Với tập dữ liệu rất lớn hoặc dữ liệu thay đổi liên tục, cân nhắc thiết kế truy vấn theo cursor/keyset dựa trên khóa sắp xếp thay vì tăng offset không giới hạn. Cách triển khai cụ thể cần phù hợp với phiên bản Spring Data Neo4j và mô hình truy vấn của ứng dụng.

## 10. Hiệu năng và giới hạn của phân trang

Phân trang giúp giới hạn số dòng trả về, nhưng không đảm bảo mọi trang đều có chi phí giống nhau.

- `Page` có thể cần thêm count query để tính tổng số phần tử.
- Offset lớn có thể tốn thời gian vì database vẫn phải xử lý phần kết quả trước vị trí bắt đầu.
- Sắp xếp theo property không có index phù hợp có thể cần xử lý nhiều dữ liệu.
- Điều kiện lọc nên dùng label và property phù hợp, kết hợp index hoặc constraint khi cần.
- Kích thước trang quá lớn làm tăng dữ liệu truyền và bộ nhớ ứng dụng.

Hãy dùng `EXPLAIN` hoặc `PROFILE` để đánh giá truy vấn được sinh ra khi cần điều tra hiệu năng. Với `Page`, cũng cần xem chi phí của count query chứ không chỉ query lấy content.

## 11. Những kết hợp tham số cần tránh

`Pageable` đã chứa cả page, size và sort. Vì vậy, không khai báo thêm `Sort` hoặc `Limit` như một special parameter riêng trong cùng method:

```java
// Không hợp lệ: Pageable đã chứa Sort.
Page<Product> findByStatus(String status, Pageable pageable, Sort sort);

// Không hợp lệ: Pageable đã xác định giới hạn kết quả.
List<Product> findByStatus(String status, Pageable pageable, Limit limit);
```

Nếu chỉ cần sort, truyền `Sort`. Nếu cần cả trang và sort, truyền `Pageable`. Nếu chỉ cần giới hạn số kết quả cố định, có thể cân nhắc `Top` hoặc `First` trong tên method theo yêu cầu của use case.

Khi không muốn sắp xếp, truyền `Sort.unsorted()`. Khi không muốn phân trang, truyền `Pageable.unpaged()`. Các special parameter này không nên là `null`.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng page index bắt đầu từ `1` | Lấy sai trang vì Spring Data đánh số từ `0` | Chuyển số trang API về chỉ số zero-based |
| Đặt `size` bằng `0` hoặc âm | `PageRequest` không hợp lệ | Kiểm tra size lớn hơn `0` và giới hạn tối đa |
| Dùng `Page` dù không cần tổng số | Phát sinh count query không cần thiết | Dùng `Slice` hoặc `List` |
| Dùng `List` nhưng giao diện cần tổng số trang | Không có metadata tổng số | Dùng `Page` |
| Sort theo thuộc tính không có trong entity | Truy vấn có thể lỗi hoặc không thể sắp xếp như mong muốn | Dùng property được ánh xạ và kiểm tra tên chính xác |
| Sort theo một thuộc tính có nhiều giá trị trùng | Thứ tự giữa các trang có thể không ổn định | Thêm tiêu chí phụ duy nhất và ổn định |
| Kết hợp `Pageable` với `Sort` riêng | Trùng special parameter | Đưa Sort vào `PageRequest` |
| Cho client gửi kích thước trang tùy ý | Có thể tạo truy vấn quá lớn | Đặt mặc định và giới hạn size |
| Dùng offset rất lớn trên graph lớn | Thời gian truy vấn tăng | Cân nhắc cursor/keyset và đo bằng `PROFILE` |

## 13. Bài tập thực hành

Tạo repository tìm sản phẩm theo trạng thái:

```java
public interface ProductRepository extends Neo4jRepository<Product, String> {
    Page<Product> findByStatus(String status, Pageable pageable);
    Slice<Product> readByStatus(String status, Pageable pageable);
    List<Product> findAllByStatus(String status, Pageable pageable);
    List<Product> findByStatus(String status, Sort sort);
}
```

Thực hiện các yêu cầu:

1. Gọi `findByStatus` với `PageRequest.of(0, 10)` và kiểm tra content cùng metadata của `Page`.
2. Gọi trang thứ hai bằng `PageRequest.of(1, 10)` và xác nhận chỉ số trang.
3. Thêm `Sort` theo `createdAt` giảm dần và `sku` tăng dần.
4. Gọi `readByStatus` và kiểm tra `hasNext()` mà không cần tổng số trang.
5. Gọi `findAllByStatus` với `Pageable` và so sánh kết quả với kiểu `Page`.
6. Dùng method chỉ nhận `Sort` để lấy toàn bộ kết quả theo thứ tự yêu cầu.
7. Thử `PageRequest.of(0, 0)` và giải thích vì sao kích thước trang không hợp lệ.
8. Dùng `PROFILE` để so sánh truy vấn lấy trang với count query của `Page` trên tập dữ liệu thử nghiệm.

Sau bài tập, hãy giải thích được vai trò của `Pageable`, `PageRequest`, `Sort`, sự khác nhau giữa `Page`, `Slice`, `List` và vì sao một tiêu chí sắp xếp phụ giúp kết quả phân trang ổn định hơn.

## Kết luận

Với truy vấn suy diễn của Spring Data Neo4j, thêm `Pageable` để truyền trang và kích thước, tạo yêu cầu bằng `PageRequest`, và dùng `Sort` để xác định thứ tự kết quả. Chọn `Page` khi cần tổng số phần tử và số trang, `Slice` khi chỉ cần biết còn dữ liệu tiếp theo, hoặc `List` khi chỉ cần phần nội dung. Dùng thứ tự sắp xếp ổn định, giới hạn kích thước trang từ API và chú ý chi phí count query cùng offset lớn để phân trang hoạt động hiệu quả trên graph lớn.
