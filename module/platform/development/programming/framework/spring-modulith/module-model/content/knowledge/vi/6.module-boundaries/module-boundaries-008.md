# Ranh giới module không thay thế ranh giới database

Spring Modulith giúp chia một ứng dụng Spring Boot thành các mô-đun có ranh giới rõ ràng ở cấp package, API và phụ thuộc mã nguồn. Tuy nhiên, một ranh giới mô-đun không tự động tạo ra một ranh giới database. Các mô-đun trong modular monolith thường vẫn chạy trong cùng tiến trình, dùng chung một database, cùng một tài khoản kết nối và có thể cùng tham gia một giao dịch. Vì vậy, việc tổ chức package tốt chưa đủ để bảo đảm dữ liệu của mô-đun này được cô lập khỏi mô-đun khác.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, cần phân biệt hai câu hỏi: mô-đun nào được phép gọi API của mô-đun khác, và thành phần nào được phép đọc hoặc ghi dữ liệu trong database. `ApplicationModules.verify()` hỗ trợ kiểm tra phụ thuộc kiến trúc trong mã nguồn. Quyền truy cập database, quyền sở hữu bảng, schema, transaction và migration cần được thiết kế và kiểm soát bằng các cơ chế dữ liệu phù hợp.

## 1. Ranh giới module và ranh giới database giải quyết hai vấn đề khác nhau

Giả sử ứng dụng bán hàng có các mô-đun `orders`, `inventory` và `customers`:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   └── internal
│       └── OrderRepository.java
├── inventory
│   ├── InventoryOperations.java
│   └── internal
│       └── InventoryRepository.java
└── customers
    ├── CustomerManagement.java
    └── internal
        └── CustomerRepository.java
```

Spring Modulith có thể mô hình hóa các package nghiệp vụ này thành application module và kiểm tra phụ thuộc giữa chúng. Chẳng hạn, `orders` được phép gọi API công khai của `inventory` nhưng không được tham chiếu trực tiếp vào package nội bộ của `inventory`.

Ở tầng database, cả ba mô-đun vẫn có thể dùng chung một database:

```text
                         shop_db
                 ┌─────────────────────┐
                 │ orders               │
                 │ inventory            │
                 │ customers            │
                 └─────────────────────┘
                    ▲       ▲       ▲
                    │       │       │
                  orders inventory customers
                  module  module   module
```

Việc các bảng được đặt trong cùng database không làm mất ranh giới mô-đun ở cấp mã nguồn. Ngược lại, việc chia package thành nhiều mô-đun cũng không tự tạo ra schema riêng, database user riêng hay quyền truy cập riêng.

| Ranh giới | Điều nó kiểm soát | Cơ chế điển hình |
|---|---|---|
| Application module | Mô-đun nào được phụ thuộc vào package/API nào | Package structure, `NamedInterface`, `allowedDependencies`, `ApplicationModules.verify()` |
| Data ownership | Mô-đun nào chịu trách nhiệm về dữ liệu và quy tắc ghi dữ liệu nào | Quy ước sở hữu bảng, repository nội bộ, API nghiệp vụ, quy trình migration |
| Database access | Tài khoản hoặc ứng dụng nào được đọc/ghi schema, bảng hay cột nào | Database users, roles, grants, schema và quyền ở database |
| Transaction boundary | Những thay đổi dữ liệu nào phải cùng commit hoặc rollback | Transaction manager, `@Transactional`, thiết kế use case và cơ chế nhất quán |

Các ranh giới này liên quan với nhau nhưng không thay thế nhau. Một dependency có thể hợp lệ theo package architecture nhưng vẫn vi phạm data ownership nếu nó chạy SQL trực tiếp trên bảng do mô-đun khác sở hữu.

## 2. Vì sao package boundary không cô lập được dữ liệu?

Giả sử `inventory` sở hữu bảng `inventory_stock`. Repository được đặt trong package nội bộ:

```java
package com.acme.shop.inventory.internal;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class InventoryRepository {

    private final JdbcTemplate jdbc;

    InventoryRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    int availableQuantity(String sku) {
        return jdbc.queryForObject(
            "select available_quantity from inventory_stock where sku = ?",
            Integer.class,
            sku
        );
    }
}
```

Nếu `orders` tham chiếu trực tiếp đến class này, Spring Modulith có thể phát hiện dependency vào package nội bộ. Nhưng nếu `orders` có quyền dùng cùng `DataSource`, nó vẫn có thể tự viết SQL:

```java
package com.acme.shop.orders;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class OrderStockLookup {

    private final JdbcTemplate jdbc;

    OrderStockLookup(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    Integer availableQuantity(String sku) {
        return jdbc.queryForObject(
            "select available_quantity from inventory_stock where sku = ?",
            Integer.class,
            sku
        );
    }
}
```

Ở ví dụ thứ hai, `orders` không import class nào từ package `inventory.internal`. Kiểm tra phụ thuộc package có thể không nhìn thấy ý định truy cập bảng nằm trong chuỗi SQL. Nếu tài khoản database dùng chung có quyền đọc `inventory_stock`, câu truy vấn vẫn có thể chạy. Điều này cho thấy ranh giới mã nguồn và quyền dữ liệu là hai lớp kiểm soát độc lập.

Vấn đề không chỉ là truy vấn đọc. Một mô-đun khác có thể cập nhật hoặc xóa dữ liệu trực tiếp, bỏ qua quy tắc nghiệp vụ, validation, audit, sự kiện và những bất biến mà mô-đun sở hữu dữ liệu cần duy trì.

## 3. Xác định data ownership cho từng mô-đun

Mỗi mô-đun nên có trách nhiệm rõ ràng đối với một tập dữ liệu và các quy tắc thay đổi dữ liệu đó. Ví dụ:

| Mô-đun sở hữu | Dữ liệu sở hữu minh họa | Trách nhiệm |
|---|---|---|
| `orders` | `orders`, `order_items`, `order_status_history` | Tạo đơn, chuyển trạng thái, tính tổng tiền đơn hàng |
| `inventory` | `inventory_stock`, `stock_reservations` | Theo dõi số lượng, giữ hàng, giải phóng hàng |
| `customers` | `customers`, `customer_addresses` | Quản lý hồ sơ và địa chỉ khách hàng |

Data ownership có nghĩa mô-đun sở hữu là nơi định nghĩa quy tắc nghiệp vụ và chịu trách nhiệm cho các thao tác ghi dữ liệu đó. Mô-đun khác nên yêu cầu hành động thông qua API công khai hoặc thông báo sự kiện thay vì tự sửa bảng của chủ sở hữu.

Ví dụ, khi đặt hàng, `orders` có thể yêu cầu `inventory` giữ hàng:

```java
package com.acme.shop.inventory;

public interface InventoryOperations {

    ReservationResult reserve(String orderId, String sku, int quantity);
}
```

Phần triển khai bên trong `inventory` chịu trách nhiệm cập nhật `inventory_stock` và `stock_reservations`, kiểm tra số lượng còn lại và áp dụng quy tắc giữ hàng. `orders` nhận kết quả nghiệp vụ mà không cần biết tên bảng hay câu SQL.

Quy tắc hữu ích là: mô-đun có thể lưu một ID tham chiếu đến thực thể thuộc mô-đun khác, nhưng không nên coi việc biết ID đó là quyền sở hữu hoặc quyền sửa dữ liệu gốc. Ví dụ, `orders` có thể lưu `customerId` và `sku`; thông tin khách hàng và tồn kho vẫn do mô-đun tương ứng quản lý.

## 4. Dùng API và sự kiện để giao tiếp qua ranh giới dữ liệu

### API công khai cho yêu cầu cần kết quả

Khi mô-đun gọi cần kết quả để quyết định bước tiếp theo, dùng API công khai. Ví dụ, thao tác giữ hàng cần biết có thành công hay không:

```java
ReservationResult result = inventoryOperations.reserve(
    orderId,
    sku,
    quantity
);

if (!result.isAccepted()) {
    throw new OrderCannotBePlacedException(result.reason());
}
```

Mô-đun `inventory` thực hiện thay đổi dữ liệu của mình và trả kết quả qua hợp đồng. API nên mô tả hành động hoặc truy vấn nghiệp vụ, thay vì phơi bày repository, entity persistence hay cấu trúc bảng.

### Sự kiện cho bên nhận xử lý độc lập

Khi một sự kiện đã xảy ra và các mô-đun khác cần phản ứng, có thể phát sự kiện nghiệp vụ. Ví dụ, sau khi đơn được xác nhận, mô-đun `orders` phát `OrderConfirmed`; `inventory` hoặc mô-đun thông báo có thể xử lý theo trách nhiệm của mình.

```java
public record OrderConfirmed(String orderId) {}
```

Với xử lý sự kiện bất đồng bộ, cần thiết kế cách xử lý lỗi, thử lại, chống xử lý trùng và theo dõi sự kiện chưa hoàn tất. Nếu cần đảm bảo sự kiện được ghi cùng transaction với dữ liệu nguồn, hãy cân nhắc cơ chế phát sự kiện gắn với transaction hoặc transactional outbox phù hợp với yêu cầu triển khai.

Không nên chuyển một thao tác cần kết quả tức thời thành event chỉ để tránh truy cập bảng. Hãy chọn giao tiếp theo ngữ nghĩa nghiệp vụ và yêu cầu nhất quán.

## 5. Một database chung vẫn có thể có ownership rõ ràng

Modular monolith thường bắt đầu với một database dùng chung để đơn giản hóa triển khai và transaction. Dùng chung database không bắt buộc mọi mô-đun được tự do đọc/ghi mọi bảng.

Có thể phân vùng ownership theo schema:

```text
shop_db
├── orders_schema
│   ├── orders
│   └── order_items
├── inventory_schema
│   ├── inventory_stock
│   └── stock_reservations
└── customers_schema
    ├── customers
    └── customer_addresses
```

Hoặc dùng quy ước tên bảng theo mô-đun nếu database không dùng schema riêng. Điều quan trọng là ownership phải được ghi rõ và các đường ghi dữ liệu phải đi qua mô-đun sở hữu.

Schema riêng giúp tổ chức và quản lý quyền thuận tiện hơn, nhưng tự nó chưa phải là cách ly bảo mật. Nếu tất cả mô-đun dùng cùng một database user có quyền `SELECT`, `INSERT`, `UPDATE` và `DELETE` trên mọi schema, code vẫn có thể truy cập chéo. Muốn database thực sự từ chối truy cập, cần thiết lập roles/grants hoặc các quyền tương đương ở database.

Ví dụ khái niệm với PostgreSQL:

```sql
CREATE ROLE orders_app LOGIN;
CREATE ROLE inventory_owner LOGIN;

GRANT USAGE ON SCHEMA orders_schema TO orders_app;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA orders_schema TO orders_app;

REVOKE ALL ON SCHEMA inventory_schema FROM orders_app;
```

Đây chỉ là minh họa cho nguyên tắc quyền tối thiểu. Cấu hình thực tế còn phải xem xét quyền mặc định cho object được tạo sau này, quyền sequence, function, view, migration owner và cách ứng dụng cấp credentials. Nếu cả modular monolith chỉ sử dụng một datasource và một database role chung, database không thể phân biệt request đến từ mô-đun `orders` hay `inventory` chỉ dựa trên package Java.

## 6. Schema, database và mức độ cô lập

Có nhiều mức tổ chức dữ liệu. Mỗi mức mang lại lợi ích và chi phí khác nhau:

| Cách tổ chức | Lợi ích | Chi phí hoặc giới hạn |
|---|---|---|
| Chung database, chung schema | Đơn giản, dễ join và transaction, ít cấu hình | Ownership chủ yếu dựa vào quy ước và kiểm thử; quyền truy cập thường rộng nếu dùng chung credentials |
| Chung database, schema theo mô-đun | Phân vùng bảng rõ, thuận tiện cấp quyền và quản lý migration theo schema | Vẫn dùng chung hạ tầng; join, transaction và quyền có thể tạo coupling giữa schema |
| Database riêng theo mô-đun | Cô lập dữ liệu và quyền tốt hơn, có thể quản lý vòng đời độc lập | Vận hành, backup, monitoring, migration, giao tiếp và nhất quán phân tán phức tạp hơn |

Không cần tạo database riêng cho mỗi application module chỉ để gọi kiến trúc là modular. Ranh giới mô-đun có thể được thực thi ở cấp package và data ownership trong khi vẫn dùng chung một database. Chỉ nên tách database khi yêu cầu về bảo mật, mở rộng, quyền sở hữu, vòng đời dữ liệu hoặc triển khai độc lập đủ lớn để bù chi phí vận hành.

## 7. Transaction không đồng nghĩa với module boundary

Các mô-đun trong cùng ứng dụng có thể sử dụng cùng transaction manager và tham gia một transaction database. Điều đó có thể hữu ích khi một use case cần một thay đổi nguyên tử trên nhiều bảng. Tuy nhiên, khả năng kỹ thuật cùng transaction không có nghĩa mọi mô-đun nên sửa trực tiếp dữ liệu của nhau.

Ví dụ, quy trình đặt hàng có thể gọi API của `inventory` để giữ hàng và sau đó ghi đơn hàng trong cùng một transaction, nếu kiến trúc transaction của ứng dụng được thiết kế như vậy. `inventory` vẫn phải thực hiện thao tác trên bảng mà nó sở hữu; `orders` điều phối use case qua hợp đồng công khai.

Khi một use case cần thay đổi dữ liệu thuộc nhiều mô-đun, hãy làm rõ:

- Mô-đun nào điều phối use case và mô-đun nào sở hữu từng thay đổi?
- Các thao tác có cần cùng commit/rollback hay chấp nhận trạng thái trung gian?
- Có thể gọi API đồng bộ trong cùng transaction hay cần quy trình theo sự kiện?
- Nếu một bước thất bại, cần rollback, bù trừ hay retry như thế nào?
- Có nguy cơ khóa dữ liệu lâu hoặc tạo coupling giữa các mô-đun không?

Nếu tất cả thao tác cần nguyên tử trên cùng một database, một transaction có thể phù hợp. Khi dữ liệu được tách sang nhiều database hoặc bước xử lý bất đồng bộ, transaction ACID cục bộ không còn bao phủ toàn bộ quy trình; cần cân nhắc saga, outbox, idempotency và cơ chế bù trừ. Đây là quyết định về tính nhất quán và vận hành, không được giải quyết chỉ bằng `ApplicationModule`.

## 8. Migration và thay đổi schema cần có chủ sở hữu

Một nguồn coupling thường bị bỏ qua là migration. Nếu mọi nhóm đều có thể sửa mọi bảng trong cùng database, một migration của mô-đun này có thể phá vỡ truy vấn của mô-đun khác mà không tạo ra lỗi package dependency.

Hãy xác định mô-đun sở hữu schema hoặc bảng và quy định rõ:

1. Migration nào được phép tạo, đổi tên, thay đổi hoặc xóa bảng thuộc mô-đun đó.
2. Thay đổi nào ảnh hưởng đến hợp đồng dữ liệu mà mô-đun khác đang sử dụng.
3. Cách triển khai thay đổi tương thích ngược, ví dụ thêm cột trước, cập nhật consumer, rồi mới loại bỏ cột cũ.
4. Cách quản lý quyền của tài khoản migration so với tài khoản runtime.
5. Cách kiểm thử migration và truy vấn của các mô-đun phụ thuộc.

Không nên để mô-đun khác dựa vào cấu trúc bảng nội bộ như thể đó là API ổn định. Nếu có nhu cầu truy vấn dữ liệu xuyên mô-đun cho báo cáo, hãy tạo read model hoặc reporting projection có hợp đồng rõ ràng và được cập nhật theo một cơ chế có kiểm soát.

## 9. Kiểm chứng kiến trúc và kiểm chứng database bổ trợ nhau

Spring Modulith có thể kiểm tra ranh giới package và các phụ thuộc mà nó phát hiện trong mô hình ứng dụng:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Kiểm tra này giúp phát hiện phụ thuộc vào package nội bộ, chu trình phụ thuộc và các vi phạm kiến trúc mà Spring Modulith hỗ trợ. Nó không thay thế các kiểm tra sau:

- Database integration test để xác nhận truy vấn và cập nhật đúng dữ liệu.
- Kiểm thử quyền database để xác nhận role không thể truy cập schema hoặc bảng ngoài phạm vi.
- Migration test để phát hiện thay đổi schema phá vỡ consumer.
- Test transaction để xác nhận rollback, commit và xử lý lỗi đúng yêu cầu.
- Kiểm thử luồng sự kiện, retry và xử lý trùng nếu giao tiếp bất đồng bộ.

Một bộ kiểm tra đầy đủ cần bảo vệ cả dependency mã nguồn và hành vi truy cập dữ liệu. Ví dụ, `ApplicationModules.verify()` có thể PASS trong khi một đoạn SQL native vẫn đọc bảng của mô-đun khác. Vì thế, cần có kiểm soát ở tầng database và test phù hợp với cách ứng dụng kết nối dữ liệu.

## 10. Checklist thiết kế ranh giới module và database

Khi thiết kế một modular monolith, hãy kiểm tra:

1. Mỗi mô-đun có tập dữ liệu và quy tắc ghi mà nó sở hữu rõ ràng.
2. Mô-đun khác truy cập dữ liệu qua API công khai hoặc cơ chế sự kiện phù hợp.
3. Repository và entity persistence nội bộ không trở thành hợp đồng liên mô-đun ngoài ý muốn.
4. Schema hoặc bảng được phân vùng theo ownership và có người chịu trách nhiệm migration.
5. Database credentials chỉ có quyền cần thiết; nếu cần cách ly thực sự, quyền được áp dụng ở database.
6. Transaction boundary phản ánh yêu cầu nhất quán của use case, không chỉ phản ánh vị trí package.
7. Báo cáo xuyên mô-đun dùng read model hoặc hợp đồng truy vấn được quản lý.
8. `ApplicationModules.verify()` được chạy cùng với database integration, permission và migration tests phù hợp.

## Kết luận

Ranh giới application module bảo vệ cấu trúc và phụ thuộc trong mã nguồn; nó không tự cô lập bảng, schema, database credentials hay transaction. Một modular monolith có thể dùng chung database mà vẫn duy trì data ownership rõ ràng: mỗi mô-đun chịu trách nhiệm ghi dữ liệu của mình, công khai hợp đồng nghiệp vụ cho mô-đun khác và quản lý thay đổi schema có chủ đích. Khi cần mức cô lập mạnh hơn, hãy bổ sung schema, roles/grants hoặc database riêng theo yêu cầu thực tế. Kết hợp `ApplicationModules.verify()` với kiểm thử và quyền ở tầng database để bảo vệ cả ranh giới mã nguồn lẫn ranh giới dữ liệu.
