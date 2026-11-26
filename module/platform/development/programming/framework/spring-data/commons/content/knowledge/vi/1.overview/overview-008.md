# Lộ trình học và ví dụ khách hàng–sản phẩm–đơn hàng xuyên suốt tài liệu

## 1. Học Commons bằng một bài toán có thể theo dõi đến cùng

Module **SPRING_DATA_COMMONS** tập trung vào những abstraction dùng chung của Spring Data: repository, CRUD, derived queries, phân trang, sắp xếp, projection, Query by Example, mở rộng repository, metadata và auditing. Mục tiêu là hiểu hợp đồng chung rồi áp dụng đúng khả năng của store module đang sử dụng.

Bài toán xuyên suốt là một hệ thống bán hàng nhỏ:

- Quản lý khách hàng và trạng thái hoạt động của họ.
- Tra cứu sản phẩm theo nhóm, giá và trạng thái kinh doanh.
- Theo dõi đơn hàng của từng khách hàng.
- Hiển thị danh sách có phân trang và dữ liệu rút gọn.
- Ghi nhận thời điểm, người tạo và người sửa dữ liệu.

Bài toán đủ nhỏ để kiểm tra kết quả bằng mắt, nhưng vẫn có các tình huống giúp phân biệt hợp đồng repository với quy tắc nghiệp vụ và khả năng của kho dữ liệu.

Lộ trình dưới đây sắp xếp chủ đề theo quan hệ phụ thuộc về kiến thức. Mỗi chặng sử dụng lại cùng các khái niệm domain và bổ sung một năng lực truy cập dữ liệu.

## 2. Chuẩn bị trước khi bắt đầu

Bạn nên nắm được:

- Class, interface, generic, enum và kiểu định danh trong Java.
- Cách đọc `Optional<T>`, collection và chữ ký phương thức.
- Constructor injection và vai trò của Spring application context.
- Sự khác nhau giữa đối tượng Java và dữ liệu được lưu bền vững.
- Khái niệm cơ bản về transaction và tính nhất quán dữ liệu.

Để thực hành, chọn **một store module** làm môi trường chính, chẳng hạn Spring Data JPA hoặc Spring Data MongoDB. Chuẩn bị mapping domain, kết nối và cấu hình repository theo module đó. Không cần đồng thời cấu hình nhiều store để học các hợp đồng chung.

Các đoạn code trong bài là những phần ghép vào môi trường thực hành đã cấu hình. Các lớp domain cần constructor và accessor phù hợp với mapping của store; ví dụ không tự tạo kết nối chỉ nhờ khai báo repository interface.

Giữ hai câu hỏi bên cạnh mọi ví dụ:

1. Commons đang mô tả yêu cầu hoặc kết quả bằng kiểu nào?
2. Store module đang chọn thực hiện yêu cầu đó hỗ trợ những gì?

## 3. Lộ trình và đầu ra của từng chặng

| Chặng | Nội dung trọng tâm | Việc làm trên bài toán bán hàng | Dấu hiệu đã hiểu |
| --- | --- | --- | --- |
| 1 | Domain, aggregate và định danh | Xác định khách hàng, sản phẩm, đơn hàng, dòng hàng | Giải thích được dữ liệu nào là tham chiếu, dữ liệu nào là bản chụp |
| 2 | Repository và CRUD | Lưu, đọc theo ID, kiểm tra tồn tại và xóa dữ liệu thử | Phân biệt kiểu domain, kiểu ID và ý nghĩa giá trị trả về |
| 3 | Derived queries | Tìm khách hàng theo email, lọc sản phẩm, tìm đơn theo khách | Đọc tên phương thức thành điều kiện trên thuộc tính Java |
| 4 | Phân trang và sắp xếp | Xem đơn mới nhất, duyệt danh sách theo từng phần | Chọn được `Page` hoặc `Slice`, có thứ tự xác định |
| 5 | Projection | Chỉ trả các cột thông tin cho danh sách sản phẩm | Phân biệt hình dạng kết quả với bảo đảm tối ưu truy vấn |
| 6 | Query by Example | Xây bộ lọc sản phẩm từ các trường tùy chọn | Biết vai trò của probe, matcher và giới hạn của ví dụ mẫu |
| 7 | Mở rộng repository và metadata | Bổ sung truy vấn báo cáo không phù hợp tên phương thức | Đặt đúng phần hợp đồng, phần triển khai và thông tin mapping |
| 8 | Auditing và ranh giới theo store | Theo dõi ai tạo, ai sửa, thời điểm thay đổi | Phân biệt annotation, cấu hình kích hoạt và bảo đảm thực tế |

Không cần chờ hoàn thành mọi chặng mới đọc được dữ liệu. Ngay từ chặng CRUD đã có thể thao tác trên domain nhỏ. Các chặng sau làm rõ cách biểu đạt, tổ chức và kiểm soát hành vi của những thao tác đó.

## 4. Chốt mô hình domain trước khi viết repository

### 4.1. Ba aggregate chính và một giá trị nằm trong đơn hàng

```text
Customer
  id
  email
  fullName
  active

Product
  id
  sku
  name
  category
  price
  stock
  active

PurchaseOrder
  id
  customerId
  status
  items: List<OrderLine>
  totalAmount
  createdAt
  lastModifiedAt
  createdBy
  lastModifiedBy

OrderLine
  productId
  productName
  unitPrice
  quantity
```

Trong mô hình thực hành này:

- `Customer`, `Product` và `PurchaseOrder` là các aggregate root được truy cập qua repository riêng.
- `OrderLine` thuộc nội dung một đơn hàng, không có repository độc lập.
- `PurchaseOrder.customerId` tham chiếu tới khách hàng.
- `OrderLine.productId` tham chiếu tới sản phẩm.
- `productName` và `unitPrice` trên dòng hàng là bản chụp tại thời điểm lập đơn.

Đây là lựa chọn thiết kế cho ví dụ. Một hệ thống thực tế có thể có mô hình khác, nhưng phải xác định rõ ranh giới aggregate trước khi suy luận cách lưu và cập nhật.

Các tham chiếu ID thể hiện quan hệ nghiệp vụ. Commons không tự biến chúng thành join, cascade, khóa ngoại hoặc thao tác tải đối tượng liên quan. Mapping và khả năng hỗ trợ quan hệ do store module cùng thiết kế ứng dụng quyết định.

Tên lớp Java `PurchaseOrder` được dùng để phân biệt đối tượng đơn hàng với các khái niệm sắp xếp trong API. Tên bảng hoặc collection được cấu hình theo store.

### 4.2. Kiểu dữ liệu thống nhất

| Thuộc tính | Kiểu Java dùng trong ví dụ | Quy ước |
| --- | --- | --- |
| ID của aggregate | `UUID` | Kiểu ID của repository tương ứng cũng là `UUID` |
| `price`, `unitPrice`, `totalAmount` | `BigDecimal` | Tất cả tiền trong ví dụ dùng VND |
| `quantity` | `int` | Lớn hơn 0 |
| `stock` | `Integer` | Không âm; có thể để null trên đối tượng probe |
| `active` | `Boolean` | Dữ liệu lưu có giá trị; probe có thể để null |
| Thời điểm | `Instant` | Trao đổi và đối chiếu bằng mốc UTC |
| Trạng thái đơn | `OrderStatus` | Enum của nghiệp vụ |
| Người tạo, người sửa | `String` | Mã người dùng hoặc tác nhân hệ thống |

```java
public enum OrderStatus {
    DRAFT,
    PAID,
    CANCELLED
}
```

Sử dụng `BigDecimal` từ chuỗi, chẳng hạn `new BigDecimal("1200000")`, giúp tránh đưa sai số của số thực nhị phân vào tiền. Khi so sánh giá trị số, cần lưu ý `BigDecimal.equals` còn xét scale; `compareTo` phù hợp khi chỉ cần so sánh giá trị tiền theo quy ước đã chọn.

UUID cũng cần được store hỗ trợ hoặc chuyển đổi bằng cấu hình phù hợp. Tự cấp UUID cho đối tượng mới có thể ảnh hưởng cơ chế nhận biết đối tượng mới; cần xem chiến lược phát hiện trạng thái của module thay vì mặc định ID khác null nghĩa là bản ghi đã tồn tại.

### 4.3. Những bất biến repository không tự bảo đảm

Quy ước nghiệp vụ của ví dụ:

- Email khách hàng và SKU sản phẩm phải duy nhất theo quy tắc chuẩn hóa đã chọn.
- Giá không âm, số lượng đặt hàng dương.
- Tổng tiền đơn bằng tổng `unitPrice × quantity` của các dòng hàng.
- Chỉ đơn `DRAFT` mới được chuyển sang `PAID` hoặc `CANCELLED`.
- Sản phẩm ngừng kinh doanh vẫn có thể xuất hiện trong đơn hàng lịch sử.
- Việc trả lại hoặc hoàn tiền của đơn đã thanh toán nằm ngoài phạm vi mô hình này.

Một phương thức `findByEmail` không tạo ràng buộc duy nhất. Một lần gọi `save` không tự kiểm tra tồn kho, tính lại tổng tiền hoặc ngăn chuyển trạng thái trái phép.

Các yêu cầu này cần được đặt vào domain/service và được củng cố bằng ràng buộc, transaction hoặc cơ chế đồng thời phù hợp của store. Đặc biệt, thao tác “đọc tồn kho rồi ghi số mới” có thể sai khi nhiều yêu cầu chạy cùng lúc nếu không có biện pháp kiểm soát.

## 5. Bộ dữ liệu tham chiếu

Các mã `C-001`, `P-001`, `O-001` trong bảng là nhãn để dễ đọc. Trong code, dùng UUID thực tế và giữ ánh xạ cố định cho từng nhãn.

Ví dụ UUID ứng với `C-001`:

```java
import java.util.UUID;

UUID customerMaiId =
        UUID.fromString("00000000-0000-0000-0000-000000000101");
```

Có thể dành các đuôi `101–103` cho khách hàng, `201–203` cho sản phẩm và `301–304` cho đơn hàng. Nhãn ngắn trong bảng không thay đổi kiểu ID của repository thành `String`.

### 5.1. Khách hàng

| Nhãn | Họ tên | Email | Hoạt động |
| --- | --- | --- | --- |
| C-001 | Nguyễn Mai | mai@example.com | true |
| C-002 | Trần An | an@example.com | true |
| C-003 | Lê Linh | linh@example.com | false |

### 5.2. Sản phẩm ở thời điểm quan sát hiện tại

| Nhãn | SKU | Tên | Nhóm | Giá VND | Tồn kho | Đang kinh doanh |
| --- | --- | --- | --- | ---: | ---: | --- |
| P-001 | KEY-001 | Bàn phím cơ | PHU_KIEN | 1.200.000 | 12 | true |
| P-002 | MOU-001 | Chuột không dây | PHU_KIEN | 450.000 | 30 | true |
| P-003 | MON-001 | Màn hình 24 inch | MAN_HINH | 3.500.000 | 0 | false |

### 5.3. Đơn hàng

| Nhãn | Khách hàng | Trạng thái | Dòng hàng theo giá lúc lập đơn | Tổng VND | `createdAt` |
| --- | --- | --- | --- | ---: | --- |
| O-001 | C-001 | PAID | P-001 × 1; P-002 × 2 | 2.100.000 | 2026-01-10T08:00:00Z |
| O-002 | C-001 | DRAFT | P-002 × 1 | 450.000 | 2026-01-11T08:00:00Z |
| O-003 | C-002 | PAID | P-003 × 1 | 3.500.000 | 2026-01-12T08:00:00Z |
| O-004 | C-002 | CANCELLED | P-001 × 2 | 2.400.000 | 2026-01-12T08:00:00Z |

P-003 đã được bán trước khi ngừng kinh doanh. Vì thế O-003 vẫn hợp lệ dù trạng thái sản phẩm hiện tại là `active = false`.

Đơn hủy vẫn giữ tổng tiền và dòng hàng để theo dõi lịch sử. Khi tính doanh thu trong bài, chỉ lấy đơn `PAID`; không cộng tất cả đơn có `totalAmount` khác 0.

Tồn kho trong bảng là ảnh chụp hiện tại, không phải số lượng ban đầu trước tất cả đơn hàng. Không dùng bảng này để tự suy ngược một quy trình trừ tồn kho chưa được định nghĩa.

### 5.4. Cách giữ dữ liệu thực hành nhất quán

Nạp bộ dữ liệu trong môi trường thử nghiệm riêng và đưa về trạng thái ban đầu trước khi kiểm tra một chặng có thay đổi dữ liệu. Không dùng thao tác xóa toàn bộ repository trên môi trường dùng chung để tiện làm bài.

Đối với chặng auditing, có thể để cơ chế auditing điền thời gian khi lưu thay vì cố định các mốc trên. Khi đó, các kết quả phụ thuộc thời gian phải dùng mốc được tạo trong lần thực hành đó. Không đồng thời đòi thời gian tự động bằng “hiện tại” và đòi nó trùng một fixture lịch sử.

## 6. Chặng 1–2: đọc domain và làm chủ CRUD

### 6.1. Bắt đầu từ hợp đồng nhỏ

```java
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, UUID> {

    Optional<Customer> findByEmail(String email);
}
```

Trong `CrudRepository<Customer, UUID>`:

- `Customer` là kiểu aggregate được repository quản lý.
- `UUID` là kiểu định danh.
- `save`, `findById`, `existsById`, `findAll` và các thao tác xóa thuộc hợp đồng CRUD.
- `findByEmail` là phương thức truy vấn bổ sung, được học kỹ hơn ở chặng kế tiếp.

`CrudRepository.findAll()` trả về `Iterable<Customer>`. Không ép kiểu kết quả thành `List<Customer>` chỉ vì dữ liệu mẫu nhỏ. Nếu cần hợp đồng trả về danh sách, lựa chọn interface hỗ trợ danh sách hoặc chuyển đổi tường minh theo API đang dùng.

```java
Optional<Customer> result = customers.findById(customerMaiId);

Customer customer = result.orElseThrow(
        () -> new IllegalArgumentException("Không tìm thấy khách hàng")
);
```

Ví dụ giả định `customers` là repository bean đã được inject. Không gọi `get()` trên `Optional` khi chưa xử lý trường hợp không tìm thấy.

### 6.2. Thao tác ghi và giá trị trả về

Khi tạo hoặc sửa khách hàng, sử dụng đối tượng do `save` trả về:

```java
Customer saved = customers.save(customer);
```

Không giả định mọi store luôn trả về đúng instance đầu vào hoặc đều ghi xuống kho dữ liệu tại cùng thời điểm. Cách phát hiện đối tượng mới, chuyển đổi dữ liệu và theo dõi trạng thái thuộc phần tích hợp của store module.

Không dùng UUID bất kỳ để thay thế cho một ID chưa tồn tại rồi suy luận `save` chắc chắn thực hiện đúng một câu lệnh insert. Hãy chọn và cấu hình rõ chiến lược định danh, phát hiện đối tượng mới cho môi trường thực hành.

### 6.3. Bài thực hành và kết quả mong đợi

1. Đọc C-001 bằng UUID tương ứng: nhận khách hàng Nguyễn Mai.
2. Đọc một UUID không có trong fixture: nhận `Optional.empty()`.
3. Đổi tên hiển thị C-001, lưu và đọc lại: kiểm tra tên mới.
4. Tạo một khách hàng thử có email riêng, lấy ID từ kết quả lưu, xóa rồi đọc lại: không còn kết quả.
5. Khôi phục fixture trước chặng tiếp theo.

Dùng một bản ghi thử chưa được đơn hàng tham chiếu cho bài tập xóa. Quy tắc có được xóa khách hàng có đơn hàng hay không là quyết định nghiệp vụ và ràng buộc lưu trữ riêng.

Đạt chặng này khi bạn giải thích được cả trường hợp tìm thấy và không tìm thấy, đồng thời không gắn ý nghĩa nghiệp vụ như “khách đang hoạt động” vào phép kiểm tra `existsById`.

## 7. Chặng 3: chuyển câu hỏi thành derived query

### 7.1. Tìm theo thuộc tính Java

```java
import java.util.List;
import java.util.UUID;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, UUID> {

    List<Product> findByActiveTrueAndCategoryOrderByPriceAsc(
            String category
    );
}
```

Đọc tên phương thức theo từng phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `findBy` | Bắt đầu biểu đạt điều kiện truy vấn |
| `ActiveTrue` | Thuộc tính `active` có giá trị true |
| `AndCategory` | Kết hợp với điều kiện bằng trên `category` |
| `OrderByPriceAsc` | Sắp xếp theo `price` tăng dần |

Với đối số `"PHU_KIEN"`, bộ dữ liệu mẫu cho kết quả P-002 rồi P-001.

Tên phương thức tham chiếu thuộc tính domain như `category` và `price`, không phải tên cột hay tên trường lưu trữ sau khi mapping. Nếu Java có thuộc tính `unitPrice` được lưu thành `unit_price`, derived query vẫn được khai báo theo thuộc tính Java.

Việc hỗ trợ keyword và cách so khớp cần được kiểm tra theo store module. Không mặc định mọi phép toán trên chuỗi, quan hệ lồng nhau hoặc biểu thức đều được hỗ trợ như nhau.

### 7.2. Tìm đơn theo khách hàng và trạng thái

```java
import java.util.List;
import java.util.UUID;

import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, UUID> {

    List<PurchaseOrder> findByCustomerIdAndStatus(
            UUID customerId,
            OrderStatus status
    );
}
```

Kết quả mong đợi:

| Yêu cầu | Kết quả |
| --- | --- |
| Khách C-001, trạng thái PAID | O-001 |
| Khách C-001, trạng thái DRAFT | O-002 |
| Khách C-003, trạng thái PAID | Danh sách rỗng |

Ở đây `customerId` là một thuộc tính trực tiếp của `PurchaseOrder`. Không suy diễn rằng phương thức đang join sang `Customer` để lọc theo email.

Các ví dụ `List` phù hợp với fixture nhỏ. Với danh sách có thể tăng lớn, bổ sung giới hạn hoặc phân trang thay vì tải toàn bộ dữ liệu về bộ nhớ.

### 7.3. Điểm kiểm tra

Bạn cần trả lời được: “Tại sao `findByEmail` trả `Optional<Customer>` không đủ bảo đảm email duy nhất?”

Kiểu trả về biểu đạt kỳ vọng tối đa một kết quả. Ràng buộc duy nhất phải được thiết kế và thực thi tại lớp phù hợp; nhiều kết quả thực tế có thể làm truy vấn đơn thất bại.

## 8. Chặng 4: phân trang và sắp xếp có thể kiểm chứng

### 8.1. Bổ sung yêu cầu phân trang cho truy vấn

Mở rộng `PurchaseOrderRepository` bằng các phương thức:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

Page<PurchaseOrder> findByCustomerId(
        UUID customerId,
        Pageable pageable
);

Slice<PurchaseOrder> findByStatus(
        OrderStatus status,
        Pageable pageable
);
```

Các chữ ký này nằm trong interface repository, không phải các phương thức độc lập ở cấp tệp Java.

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable firstPage = PageRequest.of(
        0,
        1,
        Sort.by("createdAt").descending()
            .and(Sort.by("id").descending())
);
```

Chỉ số trang bắt đầu từ 0. Với kích thước 1, truy vấn `findByCustomerId(customerMaiId, firstPage)` trả O-002 ở trang đầu và cho biết tổng cộng có 2 đơn của C-001. Trang kế tiếp trả O-001.

Ví dụ giả định truy vấn phân trang này được store module hỗ trợ.

### 8.2. Vì sao có thêm ID trong thứ tự?

O-003 và O-004 có cùng `createdAt`. Chỉ sắp xếp theo thời gian chưa xác định thứ tự giữa chúng. Thêm `id` làm tiêu chí phân định để có thứ tự đầy đủ trên tập dữ liệu không thay đổi.

Cách so sánh UUID cụ thể phụ thuộc biểu diễn và kho dữ liệu. Điều cần đạt là store thực hiện được tiêu chí phân định đã chọn và ứng dụng sử dụng nhất quán thứ tự đó.

Thứ tự đầy đủ vẫn không tạo ảnh chụp nhất quán qua nhiều yêu cầu HTTP. Nếu có đơn mới chen vào trong lúc người dùng chuyển trang, phân trang theo offset vẫn có thể bị dịch chuyển. Tình huống đó cần chiến lược truy cập và bảo đảm nhất quán riêng.

### 8.3. Chọn Page hay Slice theo nhu cầu

| Nhu cầu giao diện | Hợp đồng phù hợp để cân nhắc | Điều cần hiểu |
| --- | --- | --- |
| Hiển thị tổng số đơn và tổng số trang | `Page<T>` | Có thể cần thao tác đếm bổ sung |
| Chỉ cần biết còn dữ liệu phía sau hay không | `Slice<T>` | Không cung cấp hợp đồng tổng số phần tử |
| Danh sách nhỏ đã có giới hạn rõ | `List<T>` | Không tự mang metadata phân trang |

Không khẳng định mọi lần trả `Page` luôn phát sinh đúng hai truy vấn. Hạ tầng có thể tối ưu hoặc suy ra một số thông tin trong từng trường hợp; điều cần đánh giá là tổng chi phí của truy vấn thực tế.

Commons cung cấp các kiểu phân trang và sắp xếp. Store module quyết định cách chuyển yêu cầu đó thành thao tác truy cập kho dữ liệu.

## 9. Chặng 5: dùng projection cho danh sách sản phẩm

Màn hình danh sách chỉ cần ID, tên và giá. Có thể biểu đạt hình dạng đó bằng một interface:

```java
import java.math.BigDecimal;
import java.util.UUID;

public interface ProductSummary {

    UUID getId();

    String getName();

    BigDecimal getPrice();
}
```

Bổ sung vào `ProductRepository`:

```java
List<ProductSummary> findByActiveTrueOrderByPriceAsc();
```

Với fixture, kết quả gồm:

| Thứ tự | Sản phẩm | Giá VND |
| --- | --- | ---: |
| 1 | P-002 — Chuột không dây | 450.000 |
| 2 | P-001 — Bàn phím cơ | 1.200.000 |

Các getter khớp với tên thuộc tính domain. Projection mô tả dữ liệu mà người gọi muốn nhận; nó không làm phát sinh một aggregate mới để lưu bằng repository riêng.

Điểm cần kiểm chứng khi thực hành:

- Kết quả có đúng các giá trị mong muốn hay không.
- Store hỗ trợ kiểu projection đang dùng thế nào.
- Truy vấn có thực sự giảm dữ liệu đọc từ kho hay chỉ thay hình dạng kết quả ở phía Java.

Không suy ra từ việc interface có ba getter rằng mọi store chắc chắn chỉ đọc ba trường. Những tối ưu liên quan đến projection, thuộc tính lồng nhau hoặc biểu thức phụ thuộc phần triển khai cụ thể.

## 10. Chặng 6: bộ lọc tùy chọn bằng Query by Example

### 10.1. Ghép thêm hợp đồng hỗ trợ

Ở chặng này, mở rộng khai báo `ProductRepository` đã có:

```java
import java.util.UUID;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface ProductRepository
        extends CrudRepository<Product, UUID>,
                QueryByExampleExecutor<Product> {

    // Giữ các phương thức truy vấn đã thêm ở chặng trước.
}
```

Việc ghép `QueryByExampleExecutor` chỉ có ý nghĩa khi store module thực hành hỗ trợ cơ chế này.

### 10.2. Tạo probe và matcher

Giả định `Product` có constructor không đối số cùng getter/setter cho các thuộc tính:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Product probe = new Product();
probe.setCategory("PHU_KIEN");
probe.setActive(Boolean.TRUE);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withIgnorePaths("id");

Example<Product> example = Example.of(probe, matcher);

Iterable<Product> matches = products.findAll(example);
```

Trong ví dụ, các thuộc tính không đặt trên probe như `name`, `sku`, `price` và `stock` phải để null. Không khởi tạo mặc định `stock = 0` hoặc `price = BigDecimal.ZERO` trong probe rồi mong matcher tự hiểu đó là “không lọc”.

Nếu dùng kiểu nguyên thủy `boolean`, giá trị mặc định false không biểu đạt được “chưa chọn điều kiện”. Kiểu `Boolean` cho phép phân biệt null, true và false trên probe. Vẫn có thể dùng primitive khi có cấu hình bỏ qua thuộc tính rõ ràng, nhưng phải kiểm soát điều kiện được đưa vào truy vấn.

Kết quả mong đợi là **tập** P-001 và P-002. Ví dụ không yêu cầu sắp xếp nên không khẳng định thứ tự hai sản phẩm. Muốn có thứ tự, truyền thêm yêu cầu sắp xếp bằng API được hỗ trợ.

### 10.3. Biết điểm dừng của Query by Example

Một probe có giá `500000` không tự mang nghĩa “giá lớn hơn 500000”. Query by Example phù hợp với những điều kiện so khớp mà matcher và store hỗ trợ; nó không thay thế mọi dạng biểu thức truy vấn.

Nếu bộ lọc cần khoảng giá, nhóm điều kiện phức tạp hoặc báo cáo tổng hợp, hãy chọn derived query thích hợp, cơ chế truy vấn riêng của store hoặc repository fragment.

Đạt chặng này khi bạn chỉ ra được chính xác thuộc tính nào đang tham gia điều kiện, thay vì coi probe là một đối tượng có thể điền tùy ý.

## 11. Chặng 7: mở rộng repository và đọc metadata đúng mục đích

### 11.1. Một yêu cầu báo cáo có hợp đồng rõ ràng

Yêu cầu mới: tính tổng giá trị các đơn đang ở trạng thái `PAID`, có `createdAt` trong khoảng từ `fromInclusive` đến trước `toExclusive`.

```java
import java.math.BigDecimal;
import java.time.Instant;

public interface PaidOrderReport {

    BigDecimal sumPaidTotal(
            Instant fromInclusive,
            Instant toExclusive
    );
}
```

Quy ước của phương thức:

- Khoảng thời gian là `[fromInclusive, toExclusive)`.
- Chỉ cộng đơn `PAID`.
- Không có đơn phù hợp thì trả `BigDecimal.ZERO`.
- Hai mốc không null và mốc đầu phải nhỏ hơn mốc cuối.
- Kết quả dùng cùng đơn vị VND với domain.

Cho `PurchaseOrderRepository` kế thừa thêm `PaidOrderReport`, rồi cung cấp implementation fragment phù hợp với store. Theo quy ước mặc định của hạ tầng fragment, implementation có thể mang tên `PaidOrderReportImpl` và nằm trong phạm vi được phát hiện.

Implementation JPA có thể sử dụng `EntityManager`; implementation MongoDB có thể dùng cơ chế aggregation qua hạ tầng MongoDB. Không có một đoạn mã tổng hợp duy nhất mà Commons tự biến thành mọi ngôn ngữ truy vấn.

Với khoảng:

```text
fromInclusive = 2026-01-10T00:00:00Z
toExclusive   = 2026-01-13T00:00:00Z
```

Kết quả mong đợi là:

```text
O-001 + O-003
= 2.100.000 + 3.500.000
= 5.600.000 VND
```

O-002 và O-004 không tham gia vì không ở trạng thái `PAID`.

Đây là báo cáo theo **thời điểm tạo đơn**, không phải thời điểm thanh toán. Nếu nghiệp vụ muốn doanh thu theo ngày nhận thanh toán, domain cần thêm thông tin như `paidAt` và có thể cần mô hình giao dịch thanh toán riêng.

Viết hợp đồng trước giúp phát hiện điểm thiếu của domain sớm hơn việc cố kéo dài tên phương thức truy vấn.

### 11.2. Phân biệt ba loại metadata

| Loại thông tin | Ví dụ trong bài | Dùng để làm gì |
| --- | --- | --- |
| Repository metadata | Domain type là `PurchaseOrder`, ID type là `UUID` | Hạ tầng hiểu cấu trúc hợp đồng repository |
| Mapping metadata | Định danh, tên bảng/collection, chuyển đổi UUID hoặc enum | Store ánh xạ đối tượng với dữ liệu lưu trữ |
| Auditing metadata | `createdAt`, `createdBy`, `lastModifiedAt` | Ứng dụng theo dõi dấu vết tạo và thay đổi |

Commons có các abstraction như `RepositoryMetadata` và hạ tầng mapping dùng chung. Store module bổ sung ý nghĩa và cách xử lý riêng. Những thành phần này phục vụ công việc khác với các trường auditing trong bản ghi nghiệp vụ.

Khi làm bài mở rộng, hãy chỉ ra metadata nào implementation thực sự cần. Ví dụ, tổng hợp giá trị đơn có thể cần mapping của `totalAmount` và `status`; không có lý do mặc định phải tự viết một framework đọc toàn bộ metadata repository.

### 11.3. Điều kiện kết thúc chặng

Bạn có thể:

1. Viết được hợp đồng báo cáo, gồm cả dữ liệu rỗng và ranh giới thời gian.
2. Ghép fragment vào repository cụ thể.
3. Chọn implementation theo store.
4. Đối chiếu kết quả 5.600.000 VND trên fixture.
5. Giải thích vì sao chỉ khai báo phương thức tùy chỉnh chưa tạo ra implementation.

## 12. Chặng 8: auditing và các bảo đảm cần kiểm chứng

### 12.1. Đánh dấu các trường theo dõi

Trong `PurchaseOrder`, có thể khai báo:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;

@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant lastModifiedAt;

@CreatedBy
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
```

Đây là các khai báo field bên trong lớp domain, không phải một tệp Java độc lập.

Annotation biểu đạt vai trò của trường. Để các trường được điền, phải kích hoạt auditing và tích hợp theo store. Chẳng hạn, JPA cần cấu hình auditing và entity listener thích hợp; MongoDB có cơ chế tích hợp auditing riêng.

### 12.2. Cung cấp người thực hiện cho môi trường thực hành

```java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;

@Configuration
public class PracticeAuditorConfiguration {

    @Bean
    public AuditorAware<String> auditorAware() {
        return () -> Optional.of("learner");
    }
}
```

Giá trị cố định `"learner"` giúp quan sát cơ chế trong môi trường thực hành. Ứng dụng thực tế cần lấy danh tính từ ngữ cảnh xác thực hoặc tác nhân hệ thống phù hợp. Bean này vẫn cần được cấu hình auditing của store sử dụng.

Kiểu `AuditorAware<String>` khớp với kiểu `String` của `createdBy` và `lastModifiedBy` trong mô hình.

### 12.3. Kịch bản kiểm tra

1. Tạo một đơn thử ở trạng thái `DRAFT`, lưu qua repository và đọc lại.
2. Quan sát `createdAt` và `createdBy`.
3. Sửa đơn thông qua một đường cập nhật có hỗ trợ auditing.
4. Lưu và đọc lại, kiểm tra `lastModifiedAt` và `lastModifiedBy`.
5. Xác nhận các trường tạo ban đầu được giữ đúng theo cơ chế đã cấu hình.

Việc có điền các trường sửa đổi ngay khi tạo mới hay không phụ thuộc cấu hình auditing. Không viết kiểm tra dựa vào giả định chưa xác nhận.

Auditing cũng không phải lịch sử đầy đủ của mọi phiên bản dữ liệu. Nó không tự ghi lại toàn bộ giá trị trước và sau thay đổi. Các thao tác bulk, native hoặc cập nhật đi vòng qua callback/listener có thể không kích hoạt auditing theo cùng cách.

Nếu hai lần lưu diễn ra trong cùng độ phân giải của nguồn thời gian, timestamp có thể bằng nhau. Không dùng yêu cầu “lần sau luôn lớn hơn lần trước” như bằng chứng duy nhất rằng auditing đã chạy.

### 12.4. Kiểm tra giới hạn của store

Trước khi đưa bài toán vào tình huống nhiều người dùng, cần làm rõ:

| Câu hỏi | Vì sao quan trọng |
| --- | --- |
| Thay đổi đơn và tồn kho có nằm trong cùng bảo đảm atomicity không? | Một lần lưu đơn không tự bao trùm mọi cập nhật sản phẩm |
| Store có hỗ trợ optimistic locking theo cách đang dùng không? | Tránh ghi đè thay đổi khi có cập nhật đồng thời |
| Truy vấn phân trang, QBE và projection được hỗ trợ đến đâu? | API chung không đồng nghĩa mọi cách kết hợp đều được thực hiện |
| Index và ràng buộc duy nhất được tạo thế nào? | Code repository không tự chứng minh tính duy nhất hoặc hiệu năng |
| Đường cập nhật nào kích hoạt auditing? | Cập nhật qua API khác có thể bỏ qua cơ chế theo dõi |
| Kiểu ID, tiền và thời gian được chuyển đổi thế nào? | Mapping ảnh hưởng dữ liệu thực tế và phép so sánh |

Các câu hỏi này gắn kiến thức Commons với store cụ thể mà không trộn lẫn hợp đồng chung và bảo đảm của hệ thống lưu trữ.

## 13. Cách chia các buổi thực hành

Có thể tổ chức thành năm buổi, điều chỉnh thời lượng theo nền tảng hiện có:

| Buổi | Trọng tâm | Sản phẩm đầu ra |
| --- | --- | --- |
| 1 | Domain, mapping và CRUD | Ba aggregate, fixture cố định, đọc/ghi khách hàng |
| 2 | Derived queries | Bộ phương thức tìm khách, sản phẩm và đơn với kết quả đối chiếu |
| 3 | Phân trang, sắp xếp, projection | Danh sách sản phẩm gọn và danh sách đơn theo từng trang |
| 4 | Query by Example, fragment và metadata | Bộ lọc sản phẩm tùy chọn, báo cáo tổng giá trị đơn PAID |
| 5 | Auditing và khả năng của store | Kịch bản tạo/sửa có dấu vết và ghi nhận các giới hạn đã quan sát |

Mỗi buổi kết thúc bằng một thao tác có đầu vào, đầu ra và lý do giải thích. Khi đổi store để học tiếp, dùng lại yêu cầu nghiệp vụ và fixture logic, rồi kiểm tra lại mapping, truy vấn, transaction và auditing trên môi trường mới.

Không cần viết lại domain theo mọi tính năng của một store ngay từ đầu. Chỉ mở rộng mô hình khi một yêu cầu cụ thể, chẳng hạn thời điểm thanh toán hoặc kiểm soát đồng thời, thực sự cần thêm thông tin.

## 14. Bài tổng hợp cuối lộ trình

Sau khi khôi phục đúng fixture, thực hiện lần lượt:

| Yêu cầu | Kết quả đối chiếu |
| --- | --- |
| Tìm khách hàng bằng `mai@example.com` | C-001 |
| Lọc sản phẩm đang kinh doanh thuộc PHU_KIEN, giá tăng dần | P-002, P-001 |
| Lấy đơn của C-001 theo thời gian tạo giảm dần, trang 0, kích thước 1 | O-002; tổng số đơn là 2 nếu dùng `Page` |
| Lấy danh sách tóm tắt sản phẩm đang kinh doanh | P-002 và P-001 với ID, tên, giá |
| QBE với `category = PHU_KIEN`, `active = true` | Tập P-001, P-002 |
| Tổng giá trị đơn PAID tạo từ ngày 10 đến trước ngày 13 tháng 1 năm 2026, theo UTC | 5.600.000 VND |
| Tạo rồi sửa một đơn thử có auditing | Đọc lại được metadata theo cấu hình auditing |

Nếu một kết quả khác bảng, trước hết đối chiếu trạng thái fixture, điều kiện lọc, kiểu dữ liệu và thứ tự. Sau đó xem mapping và truy vấn thực tế của store. Tránh thay đổi nhiều yếu tố cùng lúc vì sẽ khó nhận ra nguyên nhân.

Tự giải thích thêm năm tình huống:

1. Vì sao C-003 có thể tồn tại nhưng không có đơn hàng?
2. Vì sao đơn O-003 vẫn giữ P-003 dù sản phẩm đã ngừng kinh doanh?
3. Vì sao trả `Page` có thể tốn hơn trả `Slice`?
4. Vì sao trường `stock = 0` trên probe có thể làm bộ lọc trả kết quả khác mong đợi?
5. Vì sao có `@CreatedDate` chưa đủ để kết luận mọi đường ghi đều cập nhật thời gian?

Trả lời bằng hợp đồng API, dữ liệu mẫu và hành vi của store đang dùng. Đây là cách kiểm tra mức hiểu bền vững hơn việc chỉ ghi nhớ tên annotation.

## 15. Kết quả cần mang theo khi học tiếp

Kết thúc lộ trình, bạn có một mô hình khách hàng–sản phẩm–đơn hàng nhất quán, một bộ dữ liệu có thể đối chiếu và một tập tình huống thực hành tăng dần độ khó.

Từ nền đó, repository biểu đạt cách truy cập aggregate; CRUD xử lý các thao tác cơ bản; derived query, phân trang, projection và Query by Example giúp biểu đạt nhu cầu đọc dữ liệu; fragment bổ sung hành vi truy vấn riêng; metadata và auditing giúp hiểu hạ tầng cùng dấu vết thay đổi.

Mỗi khả năng đều cần được đặt vào đúng store module và ranh giới nghiệp vụ. Khi giữ được sự phân biệt này, bạn có thể tái sử dụng kiến thức Commons mà vẫn đánh giá đúng mapping, hiệu năng, tính nhất quán và giới hạn của kho dữ liệu đang chọn.

