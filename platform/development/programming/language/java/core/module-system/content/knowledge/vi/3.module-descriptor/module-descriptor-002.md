# Tên module và quy tắc đặt tên

Tên module là định danh mà Java Platform Module System (JPMS) dùng để nhận diện một module trong module graph. Tên này xuất hiện trong khai báo `module` của `module-info.java`, trong mệnh đề `requires` của module phụ thuộc và trong các lệnh chạy ứng dụng trên module path. Vì vậy, tên module cần hợp lệ theo cú pháp Java, dễ hiểu và ổn định theo thời gian.

## 1. Tên module được khai báo ở đâu?

Một module tường minh khai báo tên trong file `module-info.java` đặt tại thư mục gốc của module source:

```java
module com.acme.orders {
    requires java.sql;
    exports com.acme.orders.api;
}
```

Trong ví dụ này:

- `com.acme.orders` là **tên module**.
- `java.sql` là tên một module mà module hiện tại phụ thuộc.
- `com.acme.orders.api` là tên package được công khai cho module khác sử dụng.

Tên module và tên package là hai loại định danh khác nhau. Mệnh đề `requires` nhận tên module; mệnh đề `exports` nhận tên package. Một module có thể chứa nhiều package và không bắt buộc tên module phải trùng với một package cụ thể.

## 2. Cú pháp hợp lệ

Tên module là một hoặc nhiều Java identifier, ngăn cách bằng dấu chấm (`.`). Mỗi thành phần nằm giữa hai dấu chấm phải tự nó là một identifier hợp lệ.

Ví dụ:

| Tên | Hợp lệ? | Giải thích |
|---|---|---|
| `com.acme.orders` | Có | Các thành phần đều là identifier hợp lệ |
| `org.example.billing.api` | Có | Có thể dùng nhiều thành phần để thể hiện phạm vi |
| `com.acme2.orders` | Có | Identifier có thể chứa chữ số sau ký tự đầu |
| `com.2orders` | Không | Thành phần `2orders` bắt đầu bằng chữ số |
| `com.acme-orders` | Không | Dấu gạch nối không thuộc cú pháp identifier |
| `com..orders` | Không | Có một thành phần rỗng giữa hai dấu chấm |
| `com acme.orders` | Không | Tên module không chứa khoảng trắng |

Một Java identifier thường bắt đầu bằng chữ cái, dấu gạch dưới hoặc ký hiệu `$`; các ký tự tiếp theo có thể bao gồm chữ số. Tuy nhiên, từ khóa Java không thể được dùng như identifier. Từ Java 9, `_` đứng riêng là từ khóa và không được dùng làm một thành phần tên.

Về mặt ngôn ngữ, Java cho phép identifier Unicode và một số ký tự ít gặp. Trong dự án thông thường, nên ưu tiên chữ cái Latin không dấu, chữ số và dấu chấm để tên dễ đọc, dễ gõ và ít gây khác biệt giữa môi trường.

Tên module phân biệt chữ hoa và chữ thường. Dù `com.acme.orders` và `com.acme.Orders` là hai tên khác nhau, quy ước phổ biến là viết toàn bộ bằng chữ thường để nhất quán với cách đặt tên package Java.

## 3. Quy ước đặt tên nên dùng

### Dùng thứ tự tên miền đảo ngược

Cách phổ biến là đảo ngược tên miền của tổ chức hoặc dự án, sau đó thêm tên sản phẩm hay chức năng:

- `com.acme.orders`
- `com.acme.orders.api`
- `com.acme.orders.persistence`
- `vn.example.inventory`
- `org.example.reporting`

Tên miền đảo ngược giúp giảm nguy cơ trùng tên giữa các thư viện do những nhóm khác nhau phát triển. Đây là quy ước đặt tên, không phải yêu cầu module phải có một tên miền Internet đang hoạt động.

Nếu dự án không sở hữu tên miền riêng, hãy chọn một namespace ổn định mà nhóm kiểm soát, chẳng hạn namespace của tổ chức hoặc dự án mã nguồn mở. Tránh chọn một tên quá phổ biến như `util`, `common` hay `core` làm tên module độc lập vì dễ va chạm với module khác.

### Thể hiện trách nhiệm của module

Tên nên cho người đọc biết module phục vụ miền nghiệp vụ hoặc trách nhiệm kỹ thuật nào. Ví dụ, trong hệ thống bán hàng:

- `com.acme.orders` quản lý đơn hàng.
- `com.acme.catalog` quản lý danh mục sản phẩm.
- `com.acme.billing` xử lý thanh toán và hóa đơn.

Chỉ tách thêm các module con như `com.acme.orders.api` hoặc `com.acme.orders.persistence` khi chúng đại diện cho ranh giới phụ thuộc có ý nghĩa. Không cần tạo một module cho mỗi package hoặc mỗi class.

### Giữ tên ổn định

Tên module được các module khác tham chiếu trong `requires`. Đổi tên module vì thế có thể làm hỏng cấu hình biên dịch, module path và các module phụ thuộc. Hãy chọn tên có thể tồn tại lâu dài.

Không nên đưa thông tin thay đổi theo lần phát hành hoặc môi trường vào tên module, ví dụ:

- Tránh `com.acme.orders.v2` chỉ để biểu thị phiên bản phát hành.
- Tránh `com.acme.orders.dev` hoặc `com.acme.orders.prod` chỉ để phân biệt môi trường.
- Tránh đưa tên file JAR hoặc ngày build vào tên module.

Phiên bản phát hành, cấu hình môi trường và tên artifact nên được quản lý ở các cơ chế tương ứng. Nếu cần thay đổi API hoặc ranh giới module, hãy thực hiện như một thay đổi tương thích có chủ đích.

### Tránh namespace của nền tảng

Không tự đặt tên module ứng dụng dưới các tiền tố `java.*` hoặc `jdk.*`; đây là các namespace gắn với Java Platform và JDK. Dùng namespace của tổ chức hoặc dự án để tránh gây nhầm lẫn và xung đột.

## 4. Tên module khác tên package và tên file JAR

Ba loại tên này có liên quan nhưng không đồng nhất:

| Thành phần | Ví dụ | Dùng ở đâu |
|---|---|---|
| Tên module | `com.acme.orders` | `module`, `requires`, module path |
| Tên package | `com.acme.orders.api` | `package`, `exports`, `opens` |
| Tên file JAR | `orders-service-2.1.0.jar` | Tên artifact trên filesystem hoặc trong kho lưu trữ |

Ví dụ, file JAR có thể tên `orders-service-2.1.0.jar` trong khi module bên trong có tên `com.acme.orders`. Với một JAR có `module-info.class`, tên module được xác định bởi module descriptor; không cần suy ra từ tên file.

Khi thiết kế nhiều module, nên đặt package theo namespace của dự án và tránh để các named module cùng chứa một package. Việc chia sẻ package giữa nhiều named module trong cùng cấu hình có thể gây lỗi split package khi module graph được phân giải.

## 5. Tên của automatic module

Một thư viện JAR chưa có `module-info.class` vẫn có thể được đặt trên module path. Khi đó, JPMS có thể xem nó là **automatic module**.

Tên automatic module được xác định theo thứ tự sau:

1. Nếu JAR có thuộc tính manifest `Automatic-Module-Name`, giá trị của thuộc tính đó được dùng làm tên module.
2. Nếu không có thuộc tính này, tên được suy ra từ tên file JAR: bỏ phần mở rộng `.jar`, loại bỏ hậu tố phiên bản được nhận diện, thay các chuỗi ký tự không phải chữ hoặc số bằng dấu chấm, gộp các dấu chấm liên tiếp và bỏ dấu chấm ở đầu/cuối.

Ví dụ, `commons-lang3-3.12.0.jar` có thể được suy ra thành tên `commons.lang3`. Cách suy ra này phụ thuộc tên file, vì vậy đổi tên artifact có thể làm thay đổi tên module mà module khác đang `requires`.

Đối với thư viện muốn hỗ trợ người dùng JPMS nhưng chưa phát hành module descriptor, nên khai báo tên ổn định trong manifest:

```text
Automatic-Module-Name: org.example.reporting
```

Khi thư viện được nâng cấp thành explicit module bằng `module-info.java`, tên trong module descriptor sẽ xác định danh tính module. Tên đã công bố nên được giữ tương thích để các ứng dụng phụ thuộc không phải đổi `requires` chỉ vì thư viện chuyển từ automatic module sang explicit module.

Có thể kiểm tra tên mà JDK nhận diện bằng lệnh:

```bash
jar --describe-module --file libs/commons-lang3-3.12.0.jar
```

Lệnh này hữu ích khi gặp lỗi không tìm thấy module hoặc khi cần xác nhận một thư viện cũ được nhận diện dưới tên nào.

## 6. Ví dụ cấu trúc source và module descriptor

Một dự án có hai module có thể tổ chức source như sau:

```text
src/
├── com.acme.orders/
│   ├── module-info.java
│   └── com/acme/orders/api/OrderService.java
└── com.acme.billing/
    ├── module-info.java
    └── com/acme/billing/api/InvoiceService.java
```

`src/com.acme.orders/module-info.java`:

```java
module com.acme.orders {
    requires java.sql;
    exports com.acme.orders.api;
}
```

`src/com.acme.billing/module-info.java`:

```java
module com.acme.billing {
    requires com.acme.orders;
    exports com.acme.billing.api;
}
```

Ở đây, `com.acme.billing` phụ thuộc vào module `com.acme.orders` bằng đúng tên module đã khai báo. Package được export vẫn được ghi đầy đủ trong mệnh đề `exports`. Tên thư mục source trong ví dụ phản ánh tên module để dễ tổ chức dự án, nhưng chính nội dung module descriptor mới là nơi khai báo tên của explicit module.

## 7. Lỗi thường gặp

- **Dùng dấu gạch nối trong tên module:** `com.acme.order-service` không phải tên module hợp lệ theo cú pháp identifier. Dùng `com.acme.order.service` hoặc một tên có thành phần hợp lệ khác.
- **Dùng tên package trong `requires`:** `requires` cần tên module, không phải tên package được export.
- **Viết sai chữ hoa/chữ thường:** tên module phân biệt hoa thường, nên `com.acme.orders` khác `com.acme.Orders`.
- **Đổi tên JAR của automatic module mà không kiểm tra:** tên suy ra từ filename có thể đổi và làm hỏng các khai báo `requires`. Dùng `Automatic-Module-Name` để cố định tên cho thư viện chưa có descriptor.
- **Dùng tên quá chung:** tên như `common` khó phân biệt và dễ trùng với thư viện khác. Thêm namespace của tổ chức và trách nhiệm cụ thể.
- **Nhầm tên module với tên package:** `exports com.acme.orders.api;` export package; nó không tạo hoặc đổi tên module.

Khi gặp lỗi `module not found`, hãy kiểm tra ba điểm: tên trong `requires` có khớp chính xác với tên module được khai báo hay không, module có thực sự nằm trên module path hay không, và tên automatic module có bị suy ra khác dự kiến từ tên JAR hay không.

## 8. Checklist đặt tên

Trước khi chốt tên module, hãy kiểm tra:

- [ ] Mỗi thành phần ngăn cách bằng dấu chấm là một Java identifier hợp lệ.
- [ ] Tên dùng chữ thường và dễ đọc.
- [ ] Namespace có khả năng duy nhất, ưu tiên tên miền đảo ngược hoặc namespace do tổ chức kiểm soát.
- [ ] Tên thể hiện trách nhiệm của module và không quá chung chung.
- [ ] Tên không chứa phiên bản phát hành, môi trường hoặc thông tin build.
- [ ] Tên không sử dụng namespace `java.*` hoặc `jdk.*` dành cho nền tảng.
- [ ] Tên trong `requires` khớp chính xác với tên module được cung cấp trên module path.
- [ ] Với thư viện automatic module, tên được công bố ổn định bằng `Automatic-Module-Name` nếu có thể.

Một tên module tốt thường ngắn gọn, có namespace rõ ràng, mô tả đúng ranh giới trách nhiệm và không cần thay đổi theo từng phiên bản phát hành.