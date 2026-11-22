# Quy tắc suy ra đường dẫn mặc định từ tên kiểu miền

## Mục tiêu

Spring Data REST tự tạo đường dẫn cho collection resource của repository dựa trên **kiểu miền (domain type)** mà repository quản lý. Khi không cấu hình đường dẫn riêng, tên collection được tạo từ tên lớp miền: viết thường chữ cái đầu và chuyển tên sang dạng số nhiều theo quy tắc tiếng Anh.

Ví dụ, repository quản lý `Order` thường được công bố tại `/orders`; repository quản lý `Person` được công bố tại `/people`.

## Spring Data REST lấy tên từ đâu?

Đường dẫn mặc định được suy ra từ tên đơn giản của kiểu miền, tức tên lớp không kèm package. Spring Data REST không lấy tên từ interface repository, tên bảng trong database hay tên cột.

Ví dụ:

    @Entity
    public class PurchaseOrder {
        @Id
        private Long id;
        // ...
    }

    public interface PurchaseOrderRepository
            extends JpaRepository<PurchaseOrder, Long> {
    }

Kiểu miền của repository là `PurchaseOrder`, vì vậy tên collection mặc định là `purchaseOrders`. Tên interface `PurchaseOrderRepository` không trở thành đường dẫn `purchaseOrderRepositories`.

Quy tắc có thể hiểu theo các bước:

1. Xác định kiểu miền ở tham số generic của repository, chẳng hạn `JpaRepository<PurchaseOrder, Long>` có kiểu miền là `PurchaseOrder`.
2. Lấy tên đơn giản của lớp, bỏ package.
3. Viết thường chữ cái đầu của tên lớp.
4. Chuyển tên đó sang dạng số nhiều theo quy tắc số nhiều tiếng Anh.

Phần chữ hoa bên trong tên camel case thường được giữ lại. Do đó `PurchaseOrder` trở thành `purchaseOrders`.

## Ví dụ về tên collection mặc định

| Kiểu miền | Đường dẫn collection mặc định |
| --- | --- |
| `Order` | `/orders` |
| `Person` | `/people` |
| `Category` | `/categories` |
| `Address` | `/addresses` |
| `PurchaseOrder` | `/purchaseOrders` |

Không nên tự nối thêm ký tự `s` cho mọi tên lớp. Các danh từ tiếng Anh có dạng số nhiều bất quy tắc, như `Person` thành `people`, được xử lý theo quy tắc pluralization. Với tên miền phức tạp hoặc từ viết tắt, hãy kiểm tra đường dẫn thực tế do ứng dụng công bố.

## Đường dẫn collection và item

Đường dẫn được suy ra ở trên là đường dẫn collection. Spring Data REST dùng đường dẫn này làm tiền tố cho các tài nguyên của repository:

    GET /orders
    GET /orders/42

`GET /orders` truy cập collection; `GET /orders/42` truy cập item có ID `42` nếu repository hỗ trợ item resource và bản ghi tồn tại. Các query method được công bố thường nằm dưới nhánh `/search` của collection, ví dụ `/orders/search`.

Đường dẫn trong ví dụ chưa bao gồm base path tùy chỉnh. Nếu ứng dụng cấu hình `spring.data.rest.base-path=/api`, các URL tương ứng sẽ là `/api/orders` và `/api/orders/42`.

## Ghi đè đường dẫn mặc định

Nếu muốn URL ổn định, dễ đọc hoặc tuân theo quy ước API riêng, đặt thuộc tính `path` trên `@RepositoryRestResource` tại repository:

    import org.springframework.data.jpa.repository.JpaRepository;
    import org.springframework.data.rest.core.annotation.RepositoryRestResource;

    @RepositoryRestResource(path = "sales-orders")
    public interface PurchaseOrderRepository
            extends JpaRepository<PurchaseOrder, Long> {
    }

Repository trên được công bố tại `/sales-orders` thay cho `/purchaseOrders` (hoặc `/api/sales-orders` nếu base path là `/api`). `path` là tên đoạn URL của collection resource; nên dùng một giá trị rõ ràng, duy nhất và không cần thêm dấu `/` ở đầu.

Thuộc tính `collectionResourceRel` điều khiển tên quan hệ (rel) trong liên kết HAL ở API root. Nó có mục đích khác với `path`: `path` quyết định URL, còn `collectionResourceRel` quyết định tên link relation. Có thể cấu hình cả hai:

    @RepositoryRestResource(
        path = "sales-orders",
        collectionResourceRel = "salesOrders"
    )
    public interface PurchaseOrderRepository
            extends JpaRepository<PurchaseOrder, Long> {
    }

Trong ví dụ này, collection được truy cập qua `/sales-orders`; link relation ở API root có tên `salesOrders`.

Đối với một query method cụ thể, `@RestResource(path = "...")` có thể đổi đoạn đường dẫn của search resource đó. Annotation ở method không thay thế đường dẫn collection được đặt ở cấp repository.

## Những yếu tố không quyết định đường dẫn mặc định

- Tên interface repository: `PurchaseOrderRepository` không phải nguồn tạo tên collection.
- Tên bảng JPA trong `@Table(name = "...")`: đổi tên bảng không tự đổi URL REST.
- Tên package của lớp miền: package không được nối vào đường dẫn mặc định.
- Tên thuộc tính JSON hoặc tên cột database: các tên này không quyết định collection path.

Nếu hai kiểu miền khác package có cùng tên lớp đơn giản, tên collection mặc định có thể bị trùng. Hãy đặt `@RepositoryRestResource(path = "...")` rõ ràng cho các repository cần phân biệt.

## Kiểm tra đường dẫn trong ứng dụng

Không nên chỉ dựa vào tên lớp để đoán URL khi ứng dụng đã có cấu hình tùy chỉnh. Sau khi khởi động ứng dụng:

1. Gọi API root, thường là `GET /` hoặc `GET /api/` nếu có base path.
2. Xem các liên kết collection mà Spring Data REST trả về. Link relation cho biết tên quan hệ; `href` cho biết URL thực tế.
3. Gọi URL collection từ `href`, sau đó thử URL item bằng một ID hợp lệ.
4. Nếu URL khác tên mặc định, kiểm tra `@RepositoryRestResource(path = "...")` và cấu hình `spring.data.rest.base-path`.

Ví dụ với base path `/api` và repository `PurchaseOrderRepository` không ghi đè `path`, URL collection mặc định là `/api/purchaseOrders`. Nếu repository khai báo `path = "sales-orders"`, URL trở thành `/api/sales-orders`.

## Lưu ý

Đường dẫn chỉ được công bố khi repository được Spring Data REST export. Nếu repository bị đánh dấu `@RepositoryRestResource(exported = false)`, Spring Data REST không tạo collection endpoint tương ứng, dù vẫn có thể suy ra tên mặc định từ kiểu miền.

Đường dẫn mặc định là tiện ích quy ước, không phải hợp đồng URL bắt buộc cho mọi ứng dụng. Với API công khai hoặc client phụ thuộc lâu dài vào URL, nên cân nhắc khai báo `path` tường minh và kiểm tra các liên kết được trả về sau mỗi thay đổi cấu hình.