# @Id, @Version, @Transient, @Persistent và annotation chung

## 1. Annotation cung cấp metadata cho lớp ánh xạ

Trong chương **Metadata ánh xạ** của module **SPRING_DATA_COMMONS**, annotation là một nguồn thông tin để hạ tầng nhận biết vai trò của kiểu dữ liệu và thuộc tính. Cần phân biệt ba câu hỏi: thuộc tính nào định danh đối tượng, thuộc tính nào tham gia lưu trữ và thao tác ghi được thực hiện theo cơ chế nào.

Spring Data Commons cung cấp abstraction dùng chung; module cụ thể và kho dữ liệu quyết định cách thực thi. Vì thế, cùng một interface repository không có nghĩa các annotation đều hoạt động giống nhau trên mọi store. Nội dung nền tảng về object mapping của Commons áp dụng cho các module tự triển khai ánh xạ; Spring Data JPA giao việc ánh xạ cho JPA provider. [Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html)

Sau bài này, người học có thể:

- Chọn đúng import cho annotation định danh, kiểm soát phiên bản và loại trừ thuộc tính.
- Giải thích vai trò marker của `@Persistent` và giới hạn của metadata chung.
- Đọc một domain model để dự đoán dữ liệu được ghi, dữ liệu được khôi phục và dữ liệu chỉ phục vụ xử lý trong bộ nhớ.
- Kết nối metadata với CRUD, repository tùy biến, projection, truy vấn theo ví dụ và auditing mà vẫn kiểm tra khả năng của store.

## 2. Bốn annotation trọng tâm

Các annotation trong bảng thuộc package `org.springframework.data.annotation`.

| Annotation | Câu hỏi được trả lời | Điều cần phân biệt |
| --- | --- | --- |
| `@Id` | Thuộc tính nào là định danh? | Đánh dấu định danh không đồng thời định nghĩa chiến lược sinh ID. |
| `@Version` | Thuộc tính nào giữ phiên bản để hỗ trợ optimistic locking? | Có metadata phiên bản vẫn cần một đường ghi hỗ trợ kiểm tra phiên bản. |
| `@Transient` | Thuộc tính nào bị loại khỏi cơ chế persistence? | Không đồng nghĩa với việc ẩn thuộc tính khỏi JSON hoặc giao diện. |
| `@Persistent` | Kiểu, field hoặc parameter nào được đánh dấu có liên quan đến persistence? | Marker chung không thay thế cấu hình ánh xạ đặc thù của store. |

Tên ngắn dễ gây nhầm khi IDE tự thêm import. Đọc cả package là bước đầu tiên khi xem một entity. Danh mục annotation chung được mô tả trong [API của package annotation](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/package-summary.html).

## 3. @Id: xác định danh tính của entity

### 3.1. Khai báo định danh tường minh

```java
import org.springframework.data.annotation.Id;

public class Customer {

    @Id
    private Long customerId;

    private String email;
}
```

`customerId` mang vai trò định danh dù tên thuộc tính không phải `id`. `@Id` cho phép khai báo trên field hoặc method theo API annotation. Việc mapper xử lý accessor cụ thể vẫn phải tuân theo mô hình ánh xạ đang dùng. [API @Id](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/Id.html)

Khi khai báo `CrudRepository<Customer, Long>`, tham số `Long` diễn đạt kiểu ID mà API repository nhận. Cần giữ nó phù hợp với kiểu định danh được mapping nhận biết. Nếu domain dùng mã nghiệp vụ dạng chuỗi, thiết kế repository cũng phải phản ánh lựa chọn đó.

Phân biệt ba khái niệm trong một bài toán khách hàng:

- `customerId`: danh tính dùng để tìm đúng entity.
- `email`: dữ liệu nghiệp vụ có thể cần ràng buộc duy nhất riêng.
- `version`: trạng thái phục vụ phát hiện cập nhật cạnh tranh.

Không dùng việc gắn `@Id` để suy ra ràng buộc unique cho mọi thuộc tính khác, cũng không suy ra `equals()` và `hashCode()` đã được cài đặt đúng. Đây là các quyết định thiết kế cần xử lý riêng.

### 3.2. Sinh ID thuộc về module và database

Với Spring Data JDBC, một cột ID tự tăng có thể cung cấp giá trị sau insert; `@Id` chỉ xác định thuộc tính nhận vai trò định danh. Database và schema phải được chuẩn bị phù hợp. Với MongoDB, định danh liên quan đến trường `_id` và quy tắc chuyển đổi kiểu riêng. Không chuyển nguyên giả định về `Long` tự tăng từ JDBC sang document store. [JDBC: ID Generation](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html#id-generation), [MongoDB: ID handling](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#id-handling)

### 3.3. ID có liên quan đến nhận biết entity mới

Một số chiến lược mặc định xét ID `null`, hoặc `0` với primitive, để nhận biết entity mới. Khi có thuộc tính `@Version`, hạ tầng có thể xét phiên bản trước; nếu triển khai `Persistable`, `isNew()` có thể quyết định trạng thái. Cần đọc quy tắc của module thực tế. [Entity State Detection Strategies](https://docs.spring.io/spring-data/commons/reference/is-new-state-detection.html)

Ví dụ, tự gán UUID trước khi lưu không tự chứng minh entity đã tồn tại trong database. Nếu thiết kế dùng ID gán trước, cần chọn cơ chế nhận biết trạng thái mới phù hợp thay vì đặt lại ID tùy tiện.

## 4. @Version: phát hiện cập nhật dựa trên dữ liệu cũ

```java
import org.springframework.data.annotation.Version;

public class StockItem {

    @Version
    private Long version;
}
```

`@Version` đánh dấu thuộc tính phiên bản phục vụ optimistic locking. Nó khác số phiên bản phát hành của ứng dụng và cũng khác thời điểm cập nhật cuối. [API @Version](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/Version.html)

### 4.1. Một tình huống mất cập nhật

Giả sử hai tiến trình cùng đọc tồn kho ở phiên bản `7`:

| Thời điểm | Tiến trình A | Tiến trình B | Dữ liệu đã lưu |
| --- | --- | --- | --- |
| T1 | Đọc số lượng 20, version 7 | Đọc số lượng 20, version 7 | quantity 20, version 7 |
| T2 | Ghi số lượng 18 với version 7 | Chưa ghi | quantity 18, version 8 |
| T3 | Đã hoàn tất | Ghi số lượng 19 với version 7 | Thao tác B phải bị từ chối nếu đường ghi thực thi kiểm tra version. |

Ý tưởng cập nhật có điều kiện có thể diễn đạt bằng SQL minh họa:

```sql
UPDATE stock_item
SET quantity = :new_quantity,
    version = version + 1
WHERE item_id = :item_id
  AND version = :expected_version;
```

Đây là minh họa nguyên lý, không phải SQL dùng chung cho mọi module. Khi kết quả không cập nhật được bản ghi mong đợi, ứng dụng cần phân biệt dữ liệu đã bị sửa, đã bị xóa hoặc không còn thỏa điều kiện nghiệp vụ.

Spring Data MongoDB mô tả việc thêm version vào điều kiện ghi và ném `OptimisticLockingFailureException` khi dữ liệu đã thay đổi. Cơ chế này cần write acknowledgement; chỉ một số thao tác CRUD của template xử lý version theo hợp đồng tương ứng. [MongoDB: Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#optimistic-locking)

### 4.2. Thói quen sử dụng

- Để cơ chế persistence quản lý giá trị version trong luồng lưu thông thường.
- Dùng kiểu như `Long` khi cần biểu diễn trạng thái chưa có version bằng `null`, sau khi kiểm tra quy tắc của module.
- Đọc lại dữ liệu trước khi tính lại thao tác nghiệp vụ sau xung đột.
- Nếu API nhận yêu cầu sửa từ một màn hình cũ, thiết kế cách mang hoặc kiểm tra phiên bản mà người dùng đã đọc.

Không tự tăng version trước mỗi lần gọi `save()`. Không retry vô hạn một object cũ. Với nghiệp vụ trừ tồn kho, retry cần tính lại trên trạng thái mới và xác nhận điều kiện vẫn hợp lệ; việc phát hiện xung đột không tự quyết định cách hòa giải.

Bulk update, SQL viết tay và thao tác trực tiếp bằng driver phải được xem là những đường ghi riêng. Khi tự triển khai, kiểm tra rõ nơi thêm điều kiện phiên bản và nơi kiểm tra kết quả ghi.

## 5. @Transient: dữ liệu chỉ có ý nghĩa trong bộ nhớ

```java
import org.springframework.data.annotation.Transient;

public class SearchResult {

    private String title;

    @Transient
    private String highlightedTitle;
}
```

Trong ví dụ, `highlightedTitle` có thể được tính sau truy vấn để phục vụ màn hình kết quả. Annotation loại thuộc tính khỏi persistence của mapping framework; không biến nó thành một trường được đọc lại từ database. Cơ chế này độc lập với từ khóa Java `transient`, vốn phục vụ Java Serialization. [API @Transient](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/Transient.html)

### 5.1. Phân biệt theo lớp xử lý

| Công cụ | Lớp xử lý cần quan tâm |
| --- | --- |
| `org.springframework.data.annotation.Transient` | Metadata persistence của Spring Data tương ứng. |
| `jakarta.persistence.Transient` | Ánh xạ do JPA provider quản lý. |
| Từ khóa Java `transient` | Java Serialization; phải kiểm tra riêng nếu một thư viện persistence cũng diễn giải modifier này. |
| Annotation điều khiển JSON | Serializer JSON; không thể suy ra từ metadata persistence. |

Một giá trị không được lưu vẫn có thể xuất hiện trong JSON, log hoặc debugger. Nếu `temporaryToken` là dữ liệu nhạy cảm, lựa chọn `@Transient` chỉ giải quyết câu hỏi lưu trữ qua mapper; việc kiểm soát đầu ra phải được thiết kế tại lớp tương ứng.

### 5.2. Dữ liệu tính toán và constructor

Với giá trị suy ra từ dữ liệu đã lưu, thường dễ hiểu hơn khi tính từ các thuộc tính gốc:

```java
import java.math.BigDecimal;
import org.springframework.data.annotation.Transient;

public class Quote {

    private BigDecimal subtotal;
    private BigDecimal discount;

    @Transient
    public BigDecimal getPayableAmount() {
        return subtotal.subtract(discount);
    }
}
```

Ví dụ giả định hai giá trị gốc đã được khởi tạo hợp lệ. Annotation trên getter chỉ có ý nghĩa khi mapper nhận diện accessor tương ứng.

Không yêu cầu một thuộc tính transient phải được khôi phục từ cột hoặc field không tồn tại. Hãy chọn constructor phục vụ persistence dựa trên dữ liệu có thể ánh xạ và bổ sung giá trị dẫn xuất trong logic ứng dụng. Quy tắc xử lý tham số transient cần đối chiếu với phiên bản mapper; không thiết kế dựa trên giả định mapper có thể tự khôi phục dữ liệu đã bị loại khỏi lưu trữ.

`@Transient` cũng không phải migration: thêm annotation không tự xóa cột SQL hoặc dữ liệu cũ đã tồn tại trong document.

## 6. @Persistent: marker chung cho hạ tầng metadata

`org.springframework.data.annotation.Persistent` được định nghĩa để nhận diện kiểu, field và parameter có tính persistent. Vai trò này khác với việc chỉ định bảng, collection, column hay index. [API @Persistent](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/Persistent.html)

Có thể dùng marker trong một annotation tổng hợp:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.data.annotation.Persistent;

@Persistent
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface DomainRecord {
}
```

Ví dụ này chỉ minh họa cách biểu đạt metadata. Annotation `DomainRecord` tự định nghĩa chưa cung cấp quy tắc ánh xạ cho một database cụ thể và cũng chưa cung cấp cơ chế đăng ký repository.

Khi xem một class được đánh dấu persistent, tiếp tục xác định:

1. Module nào sẽ quản lý class này?
2. Mapping context nào nhận biết nó?
3. Quy tắc đặt tên bảng hoặc collection đến từ đâu?
4. Constructor và thuộc tính được mapper sử dụng là gì?

Không dùng `@Persistent` như lệnh tạo bảng, mở transaction hoặc bật optimistic locking. Nếu cần đặc điểm lưu trữ cụ thể, dùng metadata và cấu hình mà module đó hỗ trợ.

## 7. Các annotation chung thường xuất hiện cùng nhau

### 7.1. @AccessType: đọc và ghi qua field hay property

`@AccessType` cho phép lựa chọn `FIELD` hoặc `PROPERTY`; mặc định của annotation là field access. [API @AccessType](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/AccessType.html)

```java
import org.springframework.data.annotation.AccessType;

public class Contact {

    @AccessType(AccessType.Type.PROPERTY)
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Nếu setter có tác dụng phụ như phát sự kiện, gọi mạng hoặc ghi thêm dữ liệu, việc materialize object có thể trở nên khó kiểm soát. Hãy giữ thao tác truy cập thuộc tính đơn giản và đặt nghiệp vụ trong phương thức rõ ý định.

### 7.2. @PersistenceCreator: chọn cách khôi phục object

Annotation này đánh dấu constructor hoặc factory method được ưu tiên khi tạo object từ dữ liệu lưu trữ. [API @PersistenceCreator](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/PersistenceCreator.html)

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;

public class Warehouse {

    @Id
    private final Long id;
    private final String name;

    @PersistenceCreator
    public Warehouse(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Warehouse(String name) {
        this(null, name);
    }
}
```

Constructor một tham số thuận tiện cho code nghiệp vụ; constructor hai tham số phục vụ khôi phục đầy đủ. Việc gắn tên tham số với property cần được bảo toàn trong quá trình biên dịch, chẳng hạn thông qua `-parameters` theo yêu cầu mapper. Khi chỉ có một constructor, nhiều trường hợp hạ tầng đã tự chọn được và không cần annotation để phân biệt. [Object Mapping: object creation](https://docs.spring.io/spring-data/commons/reference/object-mapping.html#mapping.object-creation)

### 7.3. @ReadOnlyProperty: cho phép đọc, bỏ qua khi ghi

Đây là metadata cho thuộc tính chỉ đọc đối với mapping framework. Khác với transient, dữ liệu có thể được khôi phục khi đọc nhưng không được mapper ghi ra qua luồng persistence tương ứng. [API @ReadOnlyProperty](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/ReadOnlyProperty.html)

```java
import java.math.BigDecimal;
import org.springframework.data.annotation.ReadOnlyProperty;

public class BillingSummary {

    @ReadOnlyProperty
    private BigDecimal calculatedByDatabase;
}
```

Tình huống phù hợp là giá trị do database tính và đã có ánh xạ đọc hợp lệ. Annotation không tạo generated column và không hứa tự nạp lại giá trị mới sau `save()`. Nếu cần giá trị mới nhất, dùng cơ chế refresh hoặc đọc lại mà module hỗ trợ.

### 7.4. @TypeAlias và @Immutable

`@TypeAlias("invoice")` cung cấp tên bí danh dùng khi ghi thông tin kiểu qua hạ tầng hỗ trợ type metadata. Nó khác tên table hoặc collection; việc đổi alias phải xét khả năng đọc dữ liệu cũ. [API @TypeAlias](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/TypeAlias.html)

`@Immutable` biểu đạt chủ đích thiết kế immutable của persistent entity. Nó không thay thế việc thiết kế field, constructor và API cập nhật phù hợp. Khi dùng object immutable, luôn sử dụng kết quả trả về từ thao tác repository vì hạ tầng có thể trả về instance khác.

### 7.5. Các annotation auditing

| Annotation | Metadata nghiệp vụ |
| --- | --- |
| `@CreatedDate` | Thời điểm tạo. |
| `@LastModifiedDate` | Thời điểm sửa gần nhất. |
| `@CreatedBy` | Chủ thể tạo. |
| `@LastModifiedBy` | Chủ thể sửa gần nhất. |

Auditing cần được bật bằng cấu hình của module. Việc xác định chủ thể có thể dùng `AuditorAware<T>`; nếu chỉ theo dõi ngày giờ thì không bắt buộc cung cấp auditor. Auditing không thay thế kiểm soát xung đột của `@Version` và không tạo lịch sử đầy đủ của mọi thay đổi. [Spring Data Commons: Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)

## 8. Ví dụ hoàn chỉnh về model cho Spring Data JDBC

Phần này chọn **Spring Data JDBC** để có một bối cảnh lưu trữ cụ thể. Ứng dụng cần được cấu hình JDBC, datasource và repository scanning; bảng được tạo sẵn bằng công cụ quản lý schema của dự án. Đây là ví dụ học tập, không phải cấu hình chạy độc lập.

### 8.1. Aggregate Invoice

File Java minh họa `Invoice.java`:

```java
package example.billing;

import java.math.BigDecimal;
import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("invoice")
public class Invoice {

    @Id
    private Long id;

    @Version
    private Long version;

    private String code;
    private BigDecimal subtotal;
    private BigDecimal discount;

    @Transient
    private String uiLabel;

    public Invoice() {
    }

    public static Invoice draft(String code, BigDecimal subtotal) {
        Invoice invoice = new Invoice();
        invoice.code = Objects.requireNonNull(code);
        invoice.subtotal = Objects.requireNonNull(subtotal);
        invoice.discount = BigDecimal.ZERO;
        return invoice;
    }

    public void applyDiscount(BigDecimal amount) {
        Objects.requireNonNull(amount);
        if (amount.signum() < 0 || amount.compareTo(subtotal) > 0) {
            throw new IllegalArgumentException("Invalid discount");
        }
        this.discount = amount;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getCode() {
        return code;
    }

    public BigDecimal getSubtotal() {
        return subtotal;
    }

    public BigDecimal getDiscount() {
        return discount;
    }

    public String getUiLabel() {
        return uiLabel;
    }

    public void setUiLabel(String uiLabel) {
        this.uiLabel = uiLabel;
    }
}
```

`@Table` trong ví dụ thuộc module Relational; `@Id`, `@Version` và `@Transient` thuộc Commons. Bảng `invoice` cần có cột phù hợp cho `id`, `version`, `code`, `subtotal`, `discount`; `id` được cấu hình tự sinh theo database đã chọn. Không cần cột `ui_label` cho thuộc tính transient. Mapping JDBC phối hợp convention với metadata annotation. [Spring Data JDBC: Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)

Factory `draft()` tạo đối tượng nghiệp vụ mới. Constructor không tham số dành cho quá trình materialize theo mô hình mutable trong ví dụ. Ràng buộc database vẫn cần được thiết kế riêng: chẳng hạn độ chính xác số tiền, giá trị bắt buộc và unique cho mã hóa đơn nếu nghiệp vụ yêu cầu.

File Java minh họa `InvoiceRepository.java`:

```java
package example.billing;

import org.springframework.data.repository.CrudRepository;

public interface InvoiceRepository extends CrudRepository<Invoice, Long> {
}
```

### 8.2. Luồng tạo và sửa

Đoạn mã sau chạy bên trong một phương thức ứng dụng đã được inject `InvoiceRepository repository`:

```java
Invoice saved = repository.save(
    Invoice.draft("INV-2026-008", new BigDecimal("120000"))
);

Long invoiceId = saved.getId();

Invoice loaded = repository.findById(invoiceId).orElseThrow();
loaded.setUiLabel("Hóa đơn: " + loaded.getCode());
loaded.applyDiscount(new BigDecimal("10000"));

Invoice updated = repository.save(loaded);
```

Đọc đoạn mã theo vai trò metadata:

- ID nhận diện hóa đơn được tìm lại và cập nhật.
- Version mang dữ liệu đối chiếu khi luồng ghi thực thi optimistic locking.
- `subtotal` và `discount` là dữ liệu cần giữ để tính toán nghiệp vụ.
- `uiLabel` phục vụ hiển thị ở instance hiện tại, không phải trạng thái cần khôi phục sau mỗi lần đọc.

Không suy ra giá trị version đầu tiên từ tên kiểu `Long`; dùng quy tắc thực tế của module và phiên bản đang chạy. Khi hai request cùng sửa một hóa đơn, lớp dịch vụ phải có chính sách xử lý xung đột thay vì âm thầm ghi lại object cũ.

## 9. Đọc metadata khi mở rộng repository

Khi viết repository fragment, converter hoặc công cụ chẩn đoán, dùng abstraction metadata thay cho quy ước tự đoán rằng ID luôn mang tên `id`.

Ví dụ tiện ích nhận một `PersistentEntity` do mapping context đang dùng cung cấp:

```java
import org.springframework.data.mapping.PersistentEntity;
import org.springframework.data.mapping.PersistentProperty;

public final class MetadataPrinter {

    private MetadataPrinter() {
    }

    public static void print(PersistentEntity<?, ?> entity) {
        for (PersistentProperty<?> property : entity) {
            System.out.printf(
                "%s: id=%s, version=%s, writable=%s%n",
                property.getName(),
                property.isIdProperty(),
                property.isVersionProperty(),
                property.isWritable()
            );
        }
    }
}
```

`PersistentProperty` cung cấp các phép kiểm tra như `isIdProperty()`, `isVersionProperty()` và `isWritable()`. Khi cần viết công cụ tái sử dụng, đây là cách thể hiện rõ ý định hơn so với việc chỉ đọc tên field bằng reflection. [API PersistentProperty](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/mapping/PersistentProperty.html)

Hãy lấy entity từ mapping context của module thực tế. Một công cụ tự tạo context rời có thể bỏ lỡ converter hoặc quy tắc ánh xạ đang được cấu hình trong ứng dụng. Đừng giả định thuộc tính transient nhất thiết xuất hiện trong danh sách persistent properties để rồi đợi `isTransient()` báo `true`; hạ tầng có thể đã loại nó trước bước duyệt.

## 10. Kết nối với các abstraction dùng chung khác

| Abstraction | Điều cần kiểm tra ở metadata |
| --- | --- |
| CRUD repository | Kiểu ID, nhận biết entity mới và version của instance đang lưu. |
| Derived query | Tên property thuộc mô hình mà module nhận diện; quy tắc truy vấn riêng của store. |
| Phân trang và sắp xếp | Thuộc tính cần sort có thể ánh xạ sang dữ liệu của store và được truy vấn hỗ trợ. |
| Projection | Trường trả về có thể được chọn hoặc tính theo cơ chế projection được module hỗ trợ. |
| Query by Example | Thuộc tính trong probe có tham gia mapping và so khớp theo quy tắc nào của module. |
| Repository fragment | Đường ghi tùy biến có giữ quy tắc ID, version và auditing cần thiết hay không. |

Không dùng một thuộc tính `uiLabel` transient như thể nó là cột SQL có thể `ORDER BY`. Nếu sản phẩm cần sắp xếp theo một nhãn tổng hợp, lựa chọn rõ ràng có thể là biểu thức truy vấn, dữ liệu được lưu có chủ đích hoặc xử lý trong bộ nhớ sau khi đã chấp nhận hệ quả đối với phân trang. Cần đánh giá từng cách theo dữ liệu và khả năng của store.

Projection định nghĩa hình dạng kết quả; annotation persistence định nghĩa metadata của model. Hai khái niệm liên quan nhưng không thay thế nhau. Một projection có getter tính toán không chứng minh domain tương ứng cần thêm một field persistent.

## 11. Các nhầm lẫn thường gặp

| Hiện tượng | Điểm cần xem lại |
| --- | --- |
| Entity JPA không nhận diện ID đúng | Kiểm tra import `jakarta.persistence.Id` và quy tắc của JPA provider, thay vì dùng annotation Commons theo thói quen. |
| Tưởng `@Id` sẽ tự tạo UUID hoặc cột tự tăng | Kiểm tra chiến lược sinh ID và schema của module thực tế. |
| `@Version` có mặt nhưng SQL tự viết vẫn ghi đè | Kiểm tra điều kiện version và kết quả affected rows trong đường ghi tự triển khai. |
| Giá trị transient biến mất sau lần đọc mới | Kiểm tra nơi tính lại hoặc gán lại dữ liệu phục vụ hiển thị. |
| Field không lưu nhưng vẫn xuất hiện trong response | Kiểm tra DTO, projection và cấu hình serializer. |
| Gắn `@Persistent` nhưng class không được xử lý như mong đợi | Kiểm tra module quản lý, scanning và mapping context. |
| Giá trị read-only không đổi ngay sau `save()` | Kiểm tra cơ chế lấy lại dữ liệu do database tính. |
| Auditing annotation không được điền | Kiểm tra cấu hình auditing và nguồn auditor của module. |

Với Spring Data JPA, `save()` phối hợp với `EntityManager.persist()` hoặc `merge()`, và nhận biết entity mới có quy tắc riêng, bao gồm khác biệt với version primitive. Không áp dụng nguyên xi giả định của JDBC hoặc MongoDB vào luồng JPA. [Spring Data JPA: Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html)

## 12. Nguyên tắc áp dụng

Trước khi thêm annotation, xác định nó trả lời câu hỏi nào trong model. Dùng `@Id` cho danh tính, `@Version` cho metadata phiên bản, `@Transient` cho dữ liệu không tham gia persistence và `@Persistent` khi cần biểu đạt marker chung mà hạ tầng liên quan hiểu được.

Sau đó xác định module thực thi, đường đọc/ghi và cấu hình cần thiết. Một model dễ bảo trì thể hiện rõ dữ liệu nghiệp vụ, dữ liệu do persistence quản lý và dữ liệu phục vụ từng lần xử lý; repository và các phần mở rộng dựa trên chính metadata đó để làm việc nhất quán.