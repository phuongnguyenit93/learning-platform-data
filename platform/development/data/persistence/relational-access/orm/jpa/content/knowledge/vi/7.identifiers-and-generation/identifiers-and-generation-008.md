# Sinh khóa UUID theo phiên bản đặc tả được sử dụng trong JPA

**UUID (Universally Unique Identifier)** là lựa chọn phổ biến cho khóa chính khi hệ thống cần tạo định danh ở phía ứng dụng, tránh phụ thuộc vào một bộ đếm số nguyên duy nhất của cơ sở dữ liệu, hoặc phải trao đổi ID giữa nhiều dịch vụ. Tuy nhiên, việc viết `@GeneratedValue(strategy = GenerationType.UUID)` **có biên giới phiên bản**: cú pháp này được chuẩn hóa từ **Jakarta Persistence 3.1**, không tồn tại trong các phiên bản JPA/Jakarta Persistence cũ hơn.

Bài học hướng dẫn cách chọn chiến lược sinh khóa UUID dựa vào **phiên bản API persistence đang biên dịch**, **JPA provider đang chạy**, **kiểu khóa Java** và **kiểu cột database**. Cùng một ý tưởng “khóa UUID” có thể được hiện thực bằng API chuẩn mới, annotation riêng của Hibernate, hoặc ứng dụng tự cấp giá trị trước khi lưu.

## 1. UUID là gì, khác gì khóa số tự tăng?

UUID thường được biểu diễn bằng 128 bit; dạng chuỗi dễ đọc có 36 ký tự gồm dấu gạch nối, ví dụ:

~~~text
550e8400-e29b-41d4-a716-446655440000
~~~

Trong Java, có kiểu `java.util.UUID` để biểu diễn giá trị này:

~~~java
import java.util.UUID;

UUID id = UUID.randomUUID();
System.out.println(id); // Ví dụ: 550e8400-e29b-41d4-a716-446655440000
~~~

`UUID.randomUUID()` của Java tạo UUID ngẫu nhiên phiên bản 4 (v4). Giá trị được in ra ở mỗi lần chạy sẽ khác nhau. Dùng UUID giúp giảm nhu cầu hỏi database “ID tiếp theo là bao nhiêu” ở thời điểm tạo object, nhưng không có nghĩa các UUID tuyệt đối không bao giờ trùng; hệ thống vẫn phải duy trì **ràng buộc khóa chính/unique** trong database.

So sánh theo góc nhìn persistence:

| Đặc điểm | Khóa số tự tăng, ví dụ `BIGINT IDENTITY` | Khóa UUID |
| --- | --- | --- |
| Kiểu giá trị | Thường là `Long` hoặc `Integer` | Thường là `UUID`, đôi khi `String` |
| Nơi sinh | Thường ở database qua identity hoặc sequence | Có thể ở provider, ứng dụng hoặc database tùy thiết kế |
| Dễ đoán ID kế tiếp | Số tăng tuần tự thường dễ đoán | UUID ngẫu nhiên khó suy ra từ một ID khác |
| Kích thước lưu trữ | `BIGINT` thường 8 byte | UUID nhị phân thường 16 byte; text 36 ký tự chưa kể overhead |
| Tính tuần tự của chỉ mục | Thường thuận lợi cho B-tree | UUID ngẫu nhiên có thể gây chèn phân tán, phụ thuộc loại UUID/index |
| Ghép dữ liệu nhiều nguồn | Cần quy tắc cấp dải/định danh khi nhập dữ liệu | Có thể cấp ID độc lập với xác suất va chạm rất thấp |
| Tính bảo mật | Không phải cơ chế phân quyền | UUID khó đoán vẫn không thay thế authorization |

UUID là **giá trị định danh**, không phải hệ thống phân quyền hay mã bí mật. Khi API nhận ID của entity, ứng dụng vẫn phải kiểm tra quyền truy cập bản ghi.

## 2. Vấn đề cốt lõi: phiên bản đặc tả quyết định API nào có sẵn

JPA có một lần chuyển đổi namespace đáng chú ý:

- **JPA 2.x**, kể cả JPA 2.2, dùng package `javax.persistence`.
- **Jakarta Persistence 3.0** chuyển sang package `jakarta.persistence`, nhưng **chưa** có enum `GenerationType.UUID` trong API chuẩn.
- **Jakarta Persistence 3.1** bổ sung chiến lược UUID vào `GenerationType`.
- **Jakarta Persistence 3.2** tiếp tục có chiến lược UUID, vì vậy code chuẩn 3.1 về sinh khóa UUID vẫn là cơ sở phù hợp khi sử dụng 3.2.

Bảng lựa chọn:

| API đặc tả | Namespace | Có `GenerationType.UUID` chuẩn? | Hướng triển khai khóa UUID |
| --- | --- | --- | --- |
| JPA 2.0 / 2.1 / 2.2 | `javax.persistence.*` | **Không** | Ứng dụng tự tạo ID; hoặc dùng generator của provider |
| Jakarta Persistence 3.0 | `jakarta.persistence.*` | **Không** | Tự tạo ID; hoặc dùng generator của provider tương thích |
| Jakarta Persistence 3.1 | `jakarta.persistence.*` | **Có** | Ưu tiên `@GeneratedValue(strategy = GenerationType.UUID)` |
| Jakarta Persistence 3.2 | `jakarta.persistence.*` | **Có** | Có thể dùng chiến lược UUID chuẩn như 3.1 |

**Đổi `javax.persistence` thành `jakarta.persistence` không tự bổ sung chức năng sinh UUID.** Nếu ứng dụng đang dùng Jakarta Persistence **3.0**, viết `GenerationType.UUID` vẫn là lỗi biên dịch, dù package import đã bắt đầu bằng `jakarta`.

Cũng cần phân biệt **phiên bản Java** với **phiên bản Jakarta Persistence**. Sử dụng Java 17 hoặc 21 không chứng tỏ dependency persistence của dự án đã là 3.1+. Class `java.util.UUID` có từ lâu; thứ thay đổi ở đây là **enum và hợp đồng sinh khóa trong API JPA**.

### 2.1. API và provider phải tương thích

Kiến trúc vận hành gồm hai phần:

~~~text
Mã nguồn entity
    |
    | import javax.persistence.* hoặc jakarta.persistence.*
    v
Persistence API (đặc tả, enum, annotation)
    |
    | được hiện thực bởi
    v
Provider (Hibernate, EclipseLink, ...)
    |
    | ánh xạ và phát sinh SQL
    v
JDBC / database
~~~

API quyết định **code có biên dịch** với `GenerationType.UUID` hay không. Provider quyết định **hệ thống có thể thực thi chiến lược đó** hay không. Một dependency API 3.1 được thêm thủ công không bảo đảm provider cũ hỗ trợ đầy đủ tính năng 3.1.

Vì vậy, khi chọn UUID strategy, xác định cả **phiên bản đặc tả thực sự dùng khi compile** và **phiên bản provider tương thích ở runtime**. Framework như Spring Boot hoặc Jakarta EE có thể quản lý các dependency này; nên xem bộ phiên bản được framework hỗ trợ, thay vì tự nâng riêng một jar mà không xét tương thích.

## 3. Cách chuẩn từ Jakarta Persistence 3.1: GenerationType.UUID

Khi dự án biên dịch theo **Jakarta Persistence 3.1 hoặc 3.2** và dùng provider tương thích, khai báo như sau:

~~~java
package com.example.shop.domain;

import java.util.UUID;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "description", nullable = false, length = 200)
    private String description;

    protected PurchaseOrder() {
        // Constructor không tham số cho JPA.
    }

    public PurchaseOrder(String description) {
        this.description = description;
    }

    public UUID getId() {
        return id;
    }

    public String getDescription() {
        return description;
    }
}
~~~

Ý nghĩa từng phần:

1. `@Entity` biến `PurchaseOrder` thành entity trong persistence unit thích hợp.
2. `@Id` đánh dấu `id` là định danh JPA.
3. `@GeneratedValue(strategy = GenerationType.UUID)` yêu cầu **persistence provider cấp UUID** cho khóa chính.
4. `UUID` là kiểu Java giữ giá trị ID, giúp API sử dụng định danh có kiểu rõ ràng.
5. `@Column(nullable = false, updatable = false)` thể hiện dự định về cột bắt buộc và không cập nhật ID; ràng buộc primary key ở database vẫn cần tồn tại.

Ứng dụng tạo entity mà không phải tự điền ID:

~~~java
PurchaseOrder order = new PurchaseOrder("Đơn giao hàng ngày mai");

em.getTransaction().begin();
em.persist(order);
em.getTransaction().commit();

UUID generatedId = order.getId();
System.out.println("New order ID = " + generatedId);
~~~

Ví dụ giao dịch thủ công trên giả định `EntityManager em` do ứng dụng quản lý với transaction kiểu `RESOURCE_LOCAL`. Trong môi trường JTA, giao dịch thường được container hoặc transaction manager điều phối.

**Thời điểm ID có giá trị** phụ thuộc vòng đời sinh khóa và provider. Không được kỳ vọng `new PurchaseOrder(...)` đã có ID, vì bản thân constructor không sinh UUID trong ví dụ. Sau thao tác persist/flush thành công theo cơ chế provider, entity sẽ có khóa để sử dụng; nếu cần ID tại một thời điểm cụ thể trước khi giao dịch, hãy thiết kế và xác nhận thời điểm cấp khóa theo provider đang dùng.

### 3.1. Dùng kiểu String có được không?

Jakarta Persistence 3.1 hỗ trợ UUID generation cho ID dạng `java.util.UUID` **hoặc** `java.lang.String`. Ví dụ:

~~~java
@Entity
public class ApiClient {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(length = 36, nullable = false, updatable = false)
    private String id;

    protected ApiClient() {
    }

    public String getId() {
        return id;
    }
}
~~~

Với kiểu `String`, cần quan tâm rõ cách provider ánh xạ sang cột và kích thước cột lưu biểu diễn text. Trong dự án dùng database có kiểu UUID native, `java.util.UUID` thường làm cho mô hình Java rõ nghĩa hơn và tránh việc truyền nhầm chuỗi tùy ý.

Hai kiểu ID đều có thể hợp lệ, nhưng **không nên tự đổi kiểu của một khóa đang dùng trong production** mà không lập kế hoạch migration cột, dữ liệu quan hệ và hợp đồng API.

### 3.2. Đặc tả có bắt buộc UUID phiên bản 4 hay không?

**Không nên suy luận rằng `GenerationType.UUID` luôn sinh UUID v4.** Đặc tả yêu cầu chiến lược UUID; lựa chọn thuật toán/phiên bản UUID cụ thể có thể phụ thuộc provider và phiên bản provider, trong phạm vi hợp đồng chuẩn được hỗ trợ.

Nếu một hệ thống có yêu cầu rõ “bắt buộc v4”, “UUID có tính thứ tự theo thời gian” hoặc “dùng một chuẩn UUID cụ thể”, hãy xem khả năng cấu hình của provider, hoặc chủ động cấp ID bằng cơ chế ứng dụng được kiểm soát. Không viết kiểm thử hoặc logic nghiệp vụ dựa vào UUID version mặc định mà không kiểm chứng và định nghĩa rõ yêu cầu.

Trong Java, `UUID.randomUUID()` sinh UUID v4, nhưng đó là **API Java tạo UUID**, khác với cam kết của `GenerationType.UUID` đối với mọi provider.

## 4. JPA 2.2: vì sao GenerationType.UUID không chạy?

JPA 2.2 có enum `GenerationType` với các lựa chọn chuẩn:

~~~java
// Các giá trị tiêu biểu của javax.persistence.GenerationType trong JPA 2.2:
AUTO
IDENTITY
SEQUENCE
TABLE
~~~

Nó **không định nghĩa** `UUID`, do đó đoạn mã sau không thể biên dịch dưới dependency JPA 2.2:

~~~java
import javax.persistence.GeneratedValue;
import javax.persistence.GenerationType;

@Id
@GeneratedValue(strategy = GenerationType.UUID) // Lỗi: UUID không tồn tại.
private java.util.UUID id;
~~~

Tương tự, Jakarta Persistence 3.0 cũng chưa có giá trị `GenerationType.UUID`, dù package là `jakarta.persistence`.

Khi gặp lỗi kiểu:

~~~text
cannot find symbol
  symbol:   variable UUID
  location: class GenerationType
~~~

hãy kiểm tra **version của persistence API đang nằm trên compile classpath**. Chỉ thêm import `java.util.UUID` không thể giải quyết lỗi này vì `GenerationType.UUID` là một hằng enum của thư viện persistence.

### 4.1. Giải pháp portable: ứng dụng tự cấp định danh

Nếu muốn giữ khả năng chạy mà không phụ thuộc generator UUID riêng của provider, có thể tự tạo ID **trước khi gọi `persist()`**.

Với JPA 2.2, cách dùng `String` có biểu diễn UUID là lựa chọn rõ ràng vì String là basic type được hỗ trợ rộng rãi:

~~~java
package com.example.shop.domain;

import java.util.UUID;
import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @Column(name = "id", length = 36, nullable = false, updatable = false)
    private String id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    protected Customer() {
    }

    public Customer(String fullName) {
        this.id = UUID.randomUUID().toString();
        this.fullName = fullName;
    }

    public String getId() {
        return id;
    }
}
~~~

Sử dụng:

~~~java
Customer customer = new Customer("An");
// ID đã được ứng dụng cấp ở constructor.
String idBeforePersist = customer.getId();

em.getTransaction().begin();
em.persist(customer);
em.getTransaction().commit();
~~~

Trong thiết kế này, khóa `id` là **assigned identifier**: ứng dụng cấp trước khi persist. **Không khai báo `@GeneratedValue`**, vì ID không do generator JPA cấp.

Ưu điểm: quy tắc sinh ID rõ ràng, không dựa vào annotation riêng của Hibernate. Giới hạn: code ứng dụng chịu trách nhiệm đảm bảo entity mới luôn có ID, tránh ghi đè ID khi cập nhật, xử lý va chạm hiếm gặp và đảm bảo các đường khởi tạo đều tuân thủ quy tắc.

**Tại sao không đặt việc cấp ID vào `@PrePersist` như cách mặc định duy nhất?** Các callback lifecycle và thời điểm provider kiểm tra assigned identifier có chi tiết triển khai; nếu cần chắc chắn entity có ID trước lệnh `persist()`, cấp ID ngay tại constructor/factory là rõ ràng hơn. Với JPA 2.2, kiểu `java.util.UUID` có thể được các provider hỗ trợ như basic ID theo cách riêng, nhưng dùng `String` ở ví dụ này giảm phụ thuộc vào mapping UUID đặc thù.

### 4.2. Nếu muốn trường Java là UUID khi đang dùng JPA cũ

Có thể thiết kế một lớp domain trả về `UUID` từ chuỗi lưu trữ:

~~~java
public java.util.UUID getUuid() {
    return java.util.UUID.fromString(id);
}
~~~

Hoặc dùng `UUID` ngay ở entity nếu provider và cách ánh xạ sang DB của dự án hỗ trợ. Khi làm vậy, cần xác định **provider hỗ trợ UUID mapping ở phiên bản đang dùng**; không lấy hành vi của Hibernate làm bảo đảm cho mọi implementation JPA 2.2.

## 5. Hibernate với phiên bản đặc tả cũ: UUID generator riêng của provider

Nhiều dự án đã tạo UUID trước khi Jakarta Persistence chuẩn hóa `GenerationType.UUID`. Ví dụ Hibernate cung cấp UUID generators của riêng nó.

### 5.1. Hibernate 5.x và javax.persistence

Một dạng cấu hình legacy phổ biến trong dự án Hibernate 5.x:

~~~java
package com.example.shop.domain;

import java.util.UUID;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import org.hibernate.annotations.GenericGenerator;

@Entity
public class Invoice {

    @Id
    @GeneratedValue(generator = "invoice-uuid")
    @GenericGenerator(
        name = "invoice-uuid",
        strategy = "org.hibernate.id.UUIDGenerator"
    )
    private UUID id;

    protected Invoice() {
    }

    public UUID getId() {
        return id;
    }
}
~~~

Điều quan trọng:

- `@Id` và `@GeneratedValue` ở ví dụ dùng namespace `javax.persistence` tương ứng với JPA 2.x.
- `@GenericGenerator` **không phải annotation chuẩn JPA**; nó thuộc package `org.hibernate.annotations`.
- Giá trị `generator = "invoice-uuid"` tham chiếu tên generator đã khai báo.
- Đây là hướng đi phụ thuộc Hibernate và nên được xem là **mã theo phiên bản provider**, không phải lời giải portable cho mọi provider.

Một số dự án dùng tên chiến lược legacy ngắn như `uuid2`. Khi bảo trì dự án cũ, cần kiểm tra Hibernate version vì tên API, generator, và cơ chế mapping đã thay đổi qua các thế hệ Hibernate.

### 5.2. Hibernate 6.x và @UuidGenerator

Hibernate 6 cung cấp annotation `org.hibernate.annotations.UuidGenerator` để định nghĩa UUID generator theo API của Hibernate:

~~~java
package com.example.shop.domain;

import java.util.UUID;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import org.hibernate.annotations.UuidGenerator;

@Entity
public class Shipment {

    @Id
    @GeneratedValue
    @UuidGenerator
    private UUID id;

    protected Shipment() {
    }

    public UUID getId() {
        return id;
    }
}
~~~

Cách này vẫn là **tính năng Hibernate**, dù annotation `@GeneratedValue` nằm trong Jakarta Persistence. Một số cấu hình Hibernate cho phép lựa chọn phong cách tạo UUID qua thuộc tính của `@UuidGenerator`; các tùy chọn và giá trị enum cần tra cứu đúng phiên bản Hibernate của dự án.

Nếu đang có **Jakarta Persistence 3.1+ và provider đã hỗ trợ `GenerationType.UUID`**, nên cân nhắc dùng annotation chuẩn:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
private UUID id;
~~~

Chỉ dùng generator riêng khi có yêu cầu rõ về thuật toán, biến thể UUID hoặc khả năng đặc biệt của provider.

**Không ghép vô điều kiện ví dụ Hibernate 5 dùng `javax.persistence` với ví dụ Hibernate 6 dùng `jakarta.persistence`**. Dependency của dự án cần nhất quán namespace và provider; một ứng dụng không thể sửa vấn đề bằng cách trộn hai bộ annotation trên cùng entity.

## 6. Jakarta Persistence 3.0: đã là jakarta nhưng UUID vẫn chưa chuẩn

Đây là trường hợp dễ nhầm khi nâng cấp Java EE/JPA lên Jakarta:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Payment {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;
}
~~~

Nếu compile với **Jakarta Persistence 3.0**, enum `GenerationType.UUID` không có, vì vậy code này sai dù import namespace chính xác.

Có ba hướng:

1. **Nâng lên Jakarta Persistence 3.1+** cùng provider/framework tương thích, rồi dùng `GenerationType.UUID`.
2. **Giữ 3.0** và dùng cơ chế UUID generator do provider đang chạy hỗ trợ.
3. **Giữ 3.0** và để ứng dụng tự cấp UUID trước khi gọi `persist()`, không dùng `@GeneratedValue`.

Không phải dự án nào cũng có thể nâng cấp ngay. Một dự án cần duy trì runtime và provider cũ hoàn toàn có thể dùng khóa UUID ổn định qua phương án gán ID chủ động, miễn thiết kế schema và lifecycle nhất quán.

## 7. AUTO, IDENTITY, SEQUENCE và UUID có thay thế được nhau không?

JPA cung cấp một số chiến lược cấp khóa chính:

| Chiến lược | Ý tưởng | Liên quan đến UUID |
| --- | --- | --- |
| `AUTO` | Provider chọn cách sinh khóa phù hợp theo kiểu ID và môi trường | Hành vi phụ thuộc đặc tả và provider; không nên dùng nếu yêu cầu tường minh UUID theo cơ chế cụ thể |
| `IDENTITY` | Dựa vào cột identity của database | Thường dành cho khóa số tự tăng, không phải “bật UUID” |
| `SEQUENCE` | Dùng database sequence | Thường dùng giá trị số; không tương đương UUID |
| `TABLE` | Dùng bảng phục vụ sinh khóa | Thường dùng cơ chế số; không tương đương UUID |
| `UUID` (từ Jakarta 3.1) | Yêu cầu provider cấp UUID | Cách chuẩn trực tiếp cho ID UUID/String |

Một số provider có thể suy ra UUID generation từ `@GeneratedValue` mặc định hoặc `AUTO` khi thuộc tính ID có kiểu `UUID`. Điều này **không đủ để kết luận cùng một đoạn code hoạt động giống nhau ở mọi phiên bản**. Nếu đã dùng Jakarta 3.1+, cách diễn đạt ý định rõ nhất là `@GeneratedValue(strategy = GenerationType.UUID)`.

Ví dụ:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private UUID id;
~~~

Đoạn này có thể được một provider chấp nhận hoặc suy diễn theo các quy tắc của phiên bản tương ứng. Khi cần tính dễ hiểu và hạn chế phụ thuộc ngầm, hãy viết `GenerationType.UUID` trên phiên bản có hỗ trợ; với phiên bản cũ, chọn một giải pháp đã được nhà cung cấp hỗ trợ và ghi rõ trong dự án.

## 8. Nơi lưu UUID trong cơ sở dữ liệu

Chiến lược sinh khóa là một chiều; **kiểu cột database** là chiều khác. Việc ứng dụng đã tạo được UUID không tự bảo đảm cơ sở dữ liệu có cột phù hợp.

### 8.1. PostgreSQL: kiểu uuid bản địa

Ví dụ schema:

~~~sql
CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY,
    description VARCHAR(200) NOT NULL
);
~~~

Với entity dùng `UUID id` và provider tương thích PostgreSQL, đây là lựa chọn thông dụng. Chú ý sự khác nhau giữa:

~~~sql
-- Trường hợp ứng dụng/provider cấp khóa và gửi ID khi INSERT:
INSERT INTO purchase_orders (id, description)
VALUES ('550e8400-e29b-41d4-a716-446655440000', 'Demo');
~~~

và:

~~~sql
-- Trường hợp database tự sinh qua DEFAULT:
CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description VARCHAR(200) NOT NULL
);
~~~

`DEFAULT gen_random_uuid()` chỉ hoạt động khi SQL INSERT **không cung cấp giá trị ID** hoặc dùng cú pháp DEFAULT phù hợp. Nếu JPA provider đang tự tạo khóa từ `GenerationType.UUID` và gửi nó tới database, database default sẽ không phải nguồn tạo ID của thao tác đó.

**GenerationType.UUID không đồng nghĩa với gọi hàm `gen_random_uuid()` của PostgreSQL.** Nếu muốn database thực sự là nơi sinh khóa, cần cơ chế lấy lại ID vừa sinh phù hợp với JPA provider và mapping đang dùng; không chỉ thêm DEFAULT rồi mặc định `@GeneratedValue(strategy=UUID)` sẽ giao mọi việc cho database.

### 8.2. Các database không có cột UUID native

Tùy database và provider, UUID có thể được lưu dưới dạng:

- **16 byte nhị phân** (ví dụ `BINARY(16)`).
- **36 ký tự text** (ví dụ `CHAR(36)`/`VARCHAR(36)`).
- Một kiểu UUID bản địa của DB, nếu DB cung cấp.

Ví dụ schema lưu text:

~~~sql
CREATE TABLE customers (
    id CHAR(36) PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);
~~~

Ví dụ schema nhị phân:

~~~sql
CREATE TABLE customers (
    id BINARY(16) PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);
~~~

Hai ví dụ là **hai lựa chọn schema khác nhau**, không phải SQL portable cho mọi database. Lưu dạng nhị phân tiết kiệm dung lượng hơn text, nhưng đòi hỏi driver/provider chuyển đổi 128 bit theo quy tắc thống nhất. Lưu dạng text dễ đọc bằng mắt, nhưng tốn nhiều không gian hơn. Với `UUID` Java, cách provider chọn kiểu JDBC/SQL mặc định có thể thay đổi theo dialect và phiên bản provider.

Đừng ghép một migration lưu `CHAR(36)` với entity đang cấu hình ghi `BINARY(16)` mà không có mapping chuyển đổi tương ứng.

### 8.3. Kiểu dữ liệu của khóa ngoại phải đồng bộ

Nếu `purchase_orders.id` là UUID thì những bảng tham chiếu đến ID đơn hàng cũng cần cột phù hợp:

~~~sql
CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    purchase_order_id UUID NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_orders(id)
);
~~~

Trong entity:

~~~java
@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "purchase_order_id", nullable = false)
    private PurchaseOrder order;

    protected OrderLine() {
    }
}
~~~

Ví dụ này minh họa rằng **một hệ thống có thể dùng khóa số cho `OrderLine` và khóa UUID cho `PurchaseOrder`**. Trong quan hệ, JPA dùng mapping của `PurchaseOrder.id` để liên kết khóa ngoại. Một chiến lược ID mới không yêu cầu tất cả entity dùng cùng loại khóa.

## 9. UUID làm khóa chính khác với UUID làm dữ liệu nghiệp vụ

Không phải mọi trường UUID đều là khóa chính. Ví dụ entity có khóa số nhưng thêm `publicToken` là UUID dùng cho một giao thức tích hợp:

~~~java
@Entity
public class DeliveryRequest {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, updatable = false)
    private UUID publicToken;

    protected DeliveryRequest() {
    }

    public static DeliveryRequest createNew() {
        DeliveryRequest request = new DeliveryRequest();
        request.publicToken = UUID.randomUUID();
        return request;
    }
}
~~~

Ở đây `publicToken` **không mang `@Id`**, nên `@GeneratedValue(strategy = GenerationType.UUID)` không phải cơ chế thích hợp cho nó. `@GeneratedValue` trong JPA chủ yếu phục vụ sinh **primary key**. Nếu cần tự tạo giá trị cho một cột nghiệp vụ, ứng dụng có thể cấp trong constructor/factory, hoặc sử dụng cơ chế riêng của provider/database khi được thiết kế tường minh.

Việc dùng một UUID làm API token cũng không tự biến nó thành giá trị bí mật đủ an toàn cho xác thực. Nếu dùng làm credential, các yêu cầu về tính ngẫu nhiên, lưu trữ và quyền truy cập phải được thiết kế riêng.

## 10. UUID phiên bản nào? v4, v1, v7 và phạm vi bảo đảm

UUID có nhiều phiên bản/thuật toán khác nhau. Một số hệ thống chọn UUID ngẫu nhiên, một số muốn giá trị có tính thứ tự theo thời gian để cải thiện đặc tính ghi chỉ mục.

| Biến thể | Đặc điểm khái quát | Điểm cần nhớ với JPA |
| --- | --- | --- |
| UUID v4 | Dựa trên ngẫu nhiên | `UUID.randomUUID()` tạo v4 trong Java; provider mặc định không nhất thiết cam kết đúng v4 chỉ từ `GenerationType.UUID` |
| UUID v1 | Dựa trên thông tin thời gian và quy tắc định danh theo đặc tả tương ứng | Tính chất thông tin bên trong phụ thuộc thuật toán; không mặc định phù hợp mục tiêu riêng tư |
| UUID v7 | Được thiết kế để có tính thứ tự theo thời gian theo chuẩn UUID hiện đại | `GenerationType.UUID` không tự cam kết v7; cần generator cụ thể nếu bài toán yêu cầu |
| Thuật toán đặc thù provider | Provider có thể đưa ra cấu hình/kiểu generator riêng | Phải kiểm tra compatibility và hành vi của phiên bản đang chạy |

**Từ “UUID” ở tên annotation không đồng nghĩa một cấu hình tối ưu chỉ mục cho mọi database.** Nếu muốn khóa có locality tốt hơn, cần chọn thuật toán và kiểu cột có chủ đích, đồng thời đánh giá cách DB sắp xếp bytes. Không nên giả định mọi UUID “theo thời gian” sẽ có thứ tự giống nhau trong mọi cách mã hóa cột.

Khi doanh nghiệp chỉ cần khóa duy nhất, UUID ngẫu nhiên thông thường có thể đủ. Khi yêu cầu index/insert throughput nghiêm ngặt, cân nhắc kiểu UUID, quy mô dữ liệu, index thực tế và provider. Đánh giá này tách biệt với việc kiểm tra API `GenerationType.UUID` có tồn tại hay không.

## 11. So sánh ba kiểu sinh UUID bằng cùng một entity

Giả sử muốn lưu `Order` với ID là UUID. Cùng mục tiêu nhưng có ba cách, tùy phiên bản:

### 11.1. Cách chuẩn Jakarta Persistence 3.1+

~~~java
import java.util.UUID;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class OrderA {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    protected OrderA() {
    }
}
~~~

**Ai sinh:** JPA provider theo chiến lược chuẩn.  
**Ưu điểm:** ý định rõ, không cần annotation riêng của Hibernate.  
**Yêu cầu:** API 3.1+ và provider tương thích.

### 11.2. Cách dùng Hibernate generator khi API chưa có UUID

~~~java
import java.util.UUID;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import org.hibernate.annotations.GenericGenerator;

@Entity
public class OrderB {
    @Id
    @GeneratedValue(generator = "order-uuid")
    @GenericGenerator(
        name = "order-uuid",
        strategy = "org.hibernate.id.UUIDGenerator"
    )
    private UUID id;

    protected OrderB() {
    }
}
~~~

**Ai sinh:** Hibernate theo generator được cấu hình.  
**Ưu điểm:** cho phép dự án Hibernate 5/JPA 2.x dùng UUID trước chuẩn 3.1.  
**Giới hạn:** phụ thuộc API riêng và phiên bản Hibernate; đây là ví dụ theo namespace `javax.persistence`.

### 11.3. Cách ứng dụng tự cấp, không dùng JPA generator

~~~java
import java.util.UUID;
import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
public class OrderC {
    @Id
    private String id;

    protected OrderC() {
    }

    public OrderC(String description) {
        this.id = UUID.randomUUID().toString();
    }
}
~~~

**Ai sinh:** ứng dụng qua `UUID.randomUUID()`.  
**Ưu điểm:** tránh yêu cầu enum `GenerationType.UUID` và có thể cấp ID ngay trước khi persist.  
**Giới hạn:** mọi đường tạo entity mới phải bảo đảm ID hợp lệ; cần thiết kế conversion/schema tương ứng.

Ba đoạn này **độc lập**, minh họa hướng lựa chọn. Không gộp cả ba cách trên một thuộc tính `@Id`. Chọn **một chủ thể chịu trách nhiệm sinh ID** cho mỗi entity và áp dụng nhất quán.

## 12. Các sai lầm thường gặp khi nâng cấp phiên bản

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `GenerationType.UUID` không biên dịch | API đang là JPA 2.2 hoặc Jakarta Persistence 3.0 | Nâng API **và provider** lên nhánh hỗ trợ, hoặc dùng cách khác |
| Import sai package | Code còn `javax.persistence` nhưng đã chuyển sang Jakarta, hoặc ngược lại | Đồng bộ imports với bộ API/provider của dự án |
| Có enum UUID nhưng runtime gặp lỗi generator | Provider/framework chưa hỗ trợ tương ứng | Kiểm tra version và tổ hợp dependency thực tế |
| `@GeneratedValue` với `UUID` hoạt động ở môi trường A nhưng lỗi ở B | Đang dựa vào hành vi `AUTO`/generator riêng của provider | Khai báo chiến lược rõ và kiểm tra phiên bản chạy |
| Hibernate 5 code `@GenericGenerator` khó chuyển lên Hibernate mới | API và cơ chế generator thay đổi qua phiên bản | Dùng API chuẩn 3.1+ nếu có hoặc thay bằng generator riêng tương ứng |
| Cột DB là `VARCHAR(36)` nhưng ORM ghi binary | Kiểu JDBC mapping không khớp schema | Thống nhất kiểu cột và conversion của provider |
| Đặt `DEFAULT gen_random_uuid()` nhưng nghĩ DB sẽ sinh mọi ID | Provider đã gửi ID từ phía Java | Xác định một nguồn sinh khóa; không mặc định database default được gọi |
| Muốn có ID trước persist nhưng `getId()` đang null | Provider chưa chạy generator ở thời điểm đó | Tạo assigned ID trước persist nếu đó là yêu cầu nghiệp vụ |
| Kiểm tra UUID có tăng theo thời gian nhưng ID ngẫu nhiên | Nhầm UUID generation chung với UUID tuần tự/v7 | Chọn thuật toán cụ thể nếu yêu cầu thứ tự |
| Đổi `Long id` sang `UUID id` làm các quan hệ thất bại | Khóa ngoại, DTO, API, migration chưa chuyển đồng bộ | Lập kế hoạch migration toàn bộ chuỗi phụ thuộc |

## 13. Khi nào nên tự sinh UUID thay vì giao cho provider?

Tự cấp UUID có thể hợp lý khi:

1. Ứng dụng cần định danh **trước khi kết nối database**, chẳng hạn tạo event hoặc gắn ID cho request xử lý bất đồng bộ.
2. Dự án chạy trên JPA 2.2/Jakarta 3.0, nhưng không muốn phụ thuộc generator riêng của một provider.
3. Có yêu cầu **UUID phiên bản hoặc thuật toán xác định**, được hiện thực tại một ID factory tập trung.
4. Một dữ liệu được tạo ở nhiều dịch vụ phải có ID ngay khi hình thành để dùng làm idempotency key hoặc correlate event.

Ví dụ Java cấp UUID bằng factory:

~~~java
public final class OrderIds {
    private OrderIds() {
    }

    public static java.util.UUID newId() {
        return java.util.UUID.randomUUID();
    }
}
~~~

Entity dùng assigned ID:

~~~java
@Entity
public class PurchaseOrderDraft {
    @Id
    private String id;

    private String description;

    protected PurchaseOrderDraft() {
    }

    public PurchaseOrderDraft(String description) {
        this.id = OrderIds.newId().toString();
        this.description = description;
    }

    public String getId() {
        return id;
    }
}
~~~

Như vậy, `id` có ngay sau khi tạo object, trước cả khi gọi `EntityManager.persist()`. Đổi lại, nếu có nhiều constructor, import dữ liệu hoặc bản sao entity, cần bảo đảm **không tái sử dụng nhầm ID**. Việc gửi event “đơn hàng đã lưu” cũng cần đồng bộ với transaction để tránh phát event cho dữ liệu cuối cùng bị rollback; UUID cấp sớm không giải quyết vấn đề này.

## 14. Đổi khóa số sang UUID: cần thay nhiều hơn annotation

Giả sử schema cũ:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);
~~~

và entity cũ:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Không thể chỉ đổi thành:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
private UUID id;
~~~

rồi kỳ vọng database đang chạy tự đổi cột và các foreign key. Thay đổi kiểu primary key ảnh hưởng ít nhất các nơi:

- Cột khóa chính và mọi cột khóa ngoại tham chiếu.
- Bảng liên kết nhiều-nhiều, bảng audit/log, bảng queue/outbox lưu ID.
- Repository generic type, service API, DTO, JSON schema, URL routing.
- Các job import/export, search index, event schema và client đã lưu ID số.
- Dữ liệu cũ: cần ánh xạ số → UUID và đảm bảo quan hệ vẫn đúng.
- Migration có thể cần giai đoạn song song hai khóa để tránh phá vỡ tích hợp.

Ví dụ chiến lược chuyển đổi từng bước ở mức thiết kế:

~~~text
Giai đoạn 1: thêm cột UUID mới, unique, nullable trong DB
           -> cấp UUID cho dữ liệu cũ
           -> thêm UUID FK tương ứng cho bảng tham chiếu

Giai đoạn 2: cập nhật service/API để biết cả ID cũ và ID mới
           -> đồng bộ hai cách định danh trong thời gian chuyển tiếp

Giai đoạn 3: chuyển toàn bộ truy cập và quan hệ sang UUID
           -> đổi PK/FK nếu cần, khóa ràng buộc, dọn đường cũ
~~~

Đây là **phác thảo migration**, không phải một kịch bản SQL dùng trực tiếp cho mọi database. Các thao tác khóa bảng, chuyển kiểu cột và tạo index cần lập kế hoạch tùy dung lượng dữ liệu và yêu cầu downtime.

Nếu chỉ muốn public ID khó đoán, đôi khi đơn giản hơn là **giữ primary key số nội bộ** và thêm một cột UUID unique để API công khai. Điều này tách yêu cầu công khai ID khỏi chi phí đổi toàn bộ khóa ngoại của hệ thống.

## 15. Tình huống thực hành theo từng phiên bản

### Bài 1: Dự án JPA 2.2 có dùng được GenerationType.UUID không?

~~~java
import javax.persistence.GenerationType;

@GeneratedValue(strategy = GenerationType.UUID)
~~~

**Giải thích:** Không. JPA 2.2 không định nghĩa hằng `UUID` trong `GenerationType`. Có thể dùng Hibernate generator nếu dự án phụ thuộc Hibernate, hoặc cấp ID trong ứng dụng; muốn dùng annotation chuẩn UUID phải nâng lên Jakarta Persistence 3.1+ cùng provider phù hợp.

### Bài 2: Dùng Java 21 và Jakarta Persistence 3.0, câu lệnh có hợp lệ?

~~~java
import jakarta.persistence.GenerationType;

@GeneratedValue(strategy = GenerationType.UUID)
~~~

**Giải thích:** Không. Java 21 không thay đổi enum trong Jakarta Persistence 3.0. Cần nâng API/persistence provider lên phiên bản hỗ trợ hoặc chọn giải pháp khác.

### Bài 3: Đã dùng Jakarta Persistence 3.1, chọn cách nào?

~~~java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
private UUID id;
~~~

**Giải thích:** Đây là cách diễn đạt tiêu chuẩn và phù hợp nếu provider runtime hỗ trợ. Không cần khai báo Hibernate generator riêng khi không có yêu cầu thuật toán đặc thù.

### Bài 4: Muốn UUID v4 chắc chắn ngay trong constructor?

~~~java
public PurchaseOrder(String description) {
    this.id = UUID.randomUUID();
    this.description = description;
}
~~~

**Giải thích:** Java cấp UUID v4 ở đây. Entity cần sử dụng **assigned identifier** thay vì đồng thời khai báo `@GeneratedValue` để tránh hai nguồn sinh khóa. Cũng cần mapping database tương thích với `UUID` hoặc chuyển thành String theo thiết kế.

### Bài 5: PostgreSQL có DEFAULT gen_random_uuid(), vậy GenerationType.UUID có chạy trong database?

**Giải thích:** Không thể suy ra như vậy. Provider có thể sinh UUID phía Java và gửi ID trong SQL INSERT, khiến DEFAULT không tham gia. Muốn DB cấp ID phải cấu hình cơ chế database-generated key phù hợp và khả năng đọc lại ID của provider.

### Bài 6: Cùng kiểu UUID nhưng query theo ID có khác Long không?

~~~java
UUID orderId = UUID.fromString(
    "550e8400-e29b-41d4-a716-446655440000"
);

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);
~~~

**Giải thích:** `EntityManager.find()` vẫn dùng entity type và giá trị khóa chính; chỉ khác kiểu tham số khóa là `UUID` thay vì `Long`. Phải dùng đúng kiểu khai báo của `@Id`, không giả định một chuỗi bất kỳ sẽ tự được chuyển sang UUID trong mọi API.

## 16. Quy trình chọn giải pháp theo phiên bản

~~~text
                  Cần dùng UUID làm @Id?
                             |
                             v
           API Jakarta Persistence >= 3.1 ?
                   /                 \
                 Có                  Không
                  |                     |
                  v                     v
         Provider tương thích?     Muốn phụ thuộc
           /          \              provider?
         Có           Không          /       \
          |             |           Có       Không
          v             v            |         |
     GenerationType.UUID      Cập nhật       Dùng generator
          |                   dependency      riêng đã hỗ trợ
          |                                 hoặc tự cấp ID
          +---------------------------------------+
                              |
                              v
                Xác định UUID/String ở Java
                              |
                              v
                 Khớp kiểu cột + khóa ngoại
                              |
                              v
                Quy định một nguồn sinh ID
                              |
                              v
              Persist, find, join, migration
~~~

Lộ trình chọn nhanh:

1. **Xác định đúng phiên bản API**: `javax.persistence` 2.x, `jakarta.persistence` 3.0, hay `jakarta.persistence` 3.1+.
2. **Xác định provider thực thi** và mức hỗ trợ API.
3. **Chọn một nguồn sinh ID**: provider theo chuẩn, generator riêng, ứng dụng, hoặc database.
4. **Chọn kiểu Java và SQL tương ứng**: `UUID`/`String` và `uuid`/binary/text theo database.
5. **Giữ kiểu FK, API và migration nhất quán** với kiểu PK.
6. **Không suy đoán UUID version hoặc thời điểm có ID** ngoài những bảo đảm thực tế của API và generator đã chọn.

## 17. Kết luận

**Khả năng sinh UUID chuẩn phụ thuộc phiên bản đặc tả JPA đang sử dụng:**

- Với **JPA 2.2 và các bản cũ**, `GenerationType.UUID` chưa tồn tại; dùng ID do ứng dụng cấp hoặc generator của provider.
- Với **Jakarta Persistence 3.0**, namespace đã đổi sang `jakarta.persistence` nhưng **vẫn chưa** có `GenerationType.UUID`.
- Từ **Jakarta Persistence 3.1**, `@GeneratedValue(strategy = GenerationType.UUID)` là cơ chế chuẩn để yêu cầu provider sinh khóa UUID; **Jakarta Persistence 3.2** tiếp tục hỗ trợ.
- Với **Hibernate**, có thêm generator riêng theo từng thế hệ, ví dụ `@GenericGenerator` trong code legacy và `@UuidGenerator` trong Hibernate 6; những API này không nên được coi là phần chung của mọi JPA provider.
- Dù chọn cách nào, cần thiết kế nhất quán **kiểu Java, cột SQL, khóa ngoại, transaction và quy tắc tạo khóa**.

Một nguyên tắc thực tiễn: **chọn chiến lược sinh khóa theo phiên bản API/provider thực tế, rồi thống nhất ai cấp UUID và database lưu UUID bằng cách nào**. Điều đó giúp tránh cả lỗi biên dịch, lỗi runtime lẫn những sai lệch khó phát hiện khi chuyển môi trường hoặc nâng cấp ORM.
