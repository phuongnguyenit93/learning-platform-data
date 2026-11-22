# SpEL và EvaluationContextExtension trong phạm vi được hỗ trợ

## 1. SpEL giúp gì cho truy vấn SQL tùy chỉnh?

Spring Data JDBC cho phép khai báo SQL trực tiếp bằng `@Query`. Trong nhiều trường hợp, câu truy vấn cần một giá trị được lấy từ tham số method hoặc từ ngữ cảnh ứng dụng, chẳng hạn tenant hiện tại hay thông tin người dùng đã xác thực.

Ta có thể truyền các giá trị đó như named parameter thông thường:

```java
@Query("SELECT * FROM customers WHERE status = :status")
List<Customer> findByStatus(@Param("status") String status);
```

Khi cần tính giá trị tham số bằng biểu thức, Spring Data hỗ trợ **Spring Expression Language (SpEL)** trong các vị trí biểu thức được query method hỗ trợ. Ví dụ:

```java
@Query("SELECT * FROM customers WHERE status = :#{#status}")
List<Customer> findByStatusWithExpression(
        @Param("status") String status
);
```

Biểu thức `:#{#status}` được đánh giá thành một giá trị, sau đó giá trị đó được bind vào tham số SQL. Nó không có nghĩa là SpEL được phép thay thế tùy ý tên bảng, tên cột hoặc một đoạn SQL bất kỳ.

`EvaluationContextExtension` mở rộng evaluation context dùng khi đánh giá SpEL. Nhờ đó, biểu thức có thể truy cập những giá trị do ứng dụng cung cấp, ví dụ tenant hiện tại hoặc một phần thông tin principal. Cơ chế này hữu ích khi cùng một ngữ cảnh cần được dùng trong nhiều query method.

Bài này tập trung vào phạm vi dùng SpEL trong query method của Spring Data JDBC:

- Truyền và biến đổi giá trị tham số bằng SpEL.
- Cung cấp root object thông qua `EvaluationContextExtension`.
- Dùng ngữ cảnh tenant hoặc security một cách có kiểm soát.
- Phân biệt bind parameter với việc ghép SQL động.
- Nhận diện giới hạn và trường hợp nên dùng tham số tường minh, application service hoặc SQL tùy chỉnh.

## 2. SpEL trong @Query: biểu thức tạo ra giá trị tham số

SpEL là ngôn ngữ biểu thức của Spring. Trong Spring Data repository query, biểu thức được đặt trong placeholder theo cú pháp `:#{...}` khi dùng named parameter, hoặc dạng biểu thức tương ứng mà query parser hỗ trợ.

Ví dụ:

```java
@Query("""
    SELECT *
    FROM customers
    WHERE email = :#{#email.trim().toLowerCase()}
    """)
Optional<Customer> findByNormalizedEmail(
        @Param("email") String email
);
```

Nếu `email` là chuỗi có khoảng trắng và chữ hoa, biểu thức tính giá trị đã trim và chuyển chữ thường trước khi bind. Ý định SQL tương đương:

```sql
SELECT *
FROM customers
WHERE email = ?;
```

Giá trị đã được tính bằng SpEL được truyền riêng cho JDBC driver. Nó không bị nối trực tiếp vào chuỗi SQL.

### 2.1. Truy cập tham số method

Trong biểu thức, `#` dùng để tham chiếu biến. Tên tham số có thể được tham chiếu qua tên đã nhận diện hoặc chỉ số tham số theo cơ chế evaluation context của Spring Data:

```java
@Query("""
    SELECT *
    FROM orders
    WHERE customer_id = :#{#customerId}
      AND status = :#{#status}
    """)
List<PurchaseOrder> findForCustomer(
        @Param("customerId") Long customerId,
        @Param("status") String status
);
```

Trong các truy vấn đơn giản, cách viết sau thường dễ đọc hơn:

```java
@Query("""
    SELECT *
    FROM orders
    WHERE customer_id = :customerId
      AND status = :status
    """)
List<PurchaseOrder> findForCustomer(
        @Param("customerId") Long customerId,
        @Param("status") String status
);
```

Hãy ưu tiên named parameter thông thường khi chỉ cần truyền một giá trị. SpEL có ích khi cần tính toán hoặc lấy dữ liệu từ evaluation context; không cần bọc mọi tham số trong biểu thức chỉ vì có thể làm vậy.

### 2.2. Truy cập thuộc tính của tham số

SpEL có thể đọc thuộc tính của object được truyền vào method:

```java
public record CustomerFilter(
        String status,
        String city
) {}

@Query("""
    SELECT *
    FROM customers
    WHERE status = :#{#filter.status}
      AND city = :#{#filter.city}
    """)
List<Customer> search(@Param("filter") CustomerFilter filter);
```

Điều này có thể hữu ích khi một use case có một filter object gồm nhiều giá trị. Tuy nhiên, nếu query chỉ có hai điều kiện đơn giản, các tham số tường minh có thể dễ hiểu và dễ kiểm tra hơn.

## 3. EvaluationContext và EvaluationContextExtension

Để đánh giá SpEL, Spring cần một `EvaluationContext`. Context này chứa root object, biến, property accessor và những thành phần cần thiết để diễn giải biểu thức.

Spring Data Commons định nghĩa interface `EvaluationContextExtension` để bổ sung thành phần vào evaluation context được dùng cho repository query. Một extension có thể cung cấp:

- **Extension ID:** tên định danh của extension.
- **Root object:** đối tượng làm nguồn thuộc tính/phương thức cho biểu thức.
- **Properties hoặc functions:** các biến/khả năng bổ sung nếu implementation cần cung cấp.

Interface nằm trong package:

```java
import org.springframework.data.spel.spi.EvaluationContextExtension;
```

Một extension thường được đăng ký như Spring bean. Spring Data có thể thu thập các extension bean để mở rộng context khi đánh giá biểu thức query, trong phạm vi module và phiên bản hỗ trợ tính năng đó.

### 3.1. Tại sao cần extension?

Giả sử nhiều query đều cần lọc dữ liệu theo tenant hiện tại. Nếu mỗi repository method nhận `tenantId` từ caller, chữ ký sẽ lặp lại tham số:

```java
List<PurchaseOrder> findByTenantIdAndStatus(
        UUID tenantId,
        String status
);
```

Nếu tenant là một phần của security/request context đã được thiết lập ở tầng ứng dụng, extension có thể cung cấp tenant ID đó cho SpEL:

```text
HTTP request / authenticated principal
              |
              v
      TenantContext
              |
              v
EvaluationContextExtension
              |
              v
      SpEL expression
              |
              v
     bound SQL parameter
```

Như vậy query method không cần nhận lại tenant ID trong từng chữ ký. Tuy nhiên, đây là một lựa chọn kiến trúc: truyền tenant ID tường minh vẫn phù hợp, nhất là với job nền, batch, message consumer hoặc use case cần truy vấn nhiều tenant.

## 4. Ví dụ: cung cấp tenant hiện tại bằng EvaluationContextExtension

Giả sử bảng đơn hàng có cột `tenant_id`. Mỗi request đã được xác thực và tầng security/application thiết lập tenant hiện tại trong một context theo request. Repository cần lọc theo tenant đó.

### 4.1. Context giữ tenant ID

Một ví dụ tối giản dùng `ThreadLocal`:

```java
package com.example.tenancy;

import java.util.UUID;

public final class TenantContext {

    private static final ThreadLocal<UUID> CURRENT = new ThreadLocal<>();

    private TenantContext() {
    }

    public static void setTenantId(UUID tenantId) {
        CURRENT.set(tenantId);
    }

    public static UUID requireTenantId() {
        UUID tenantId = CURRENT.get();
        if (tenantId == null) {
            throw new IllegalStateException(
                    "No tenant is available in the current context");
        }
        return tenantId;
    }

    public static void clear() {
        CURRENT.remove();
    }
}
```

Đây chỉ là context minh họa cho ứng dụng đồng bộ chạy trên thread gắn với request. Trong hệ thống thực tế, tenant context cần được thiết lập và xóa ở filter/interceptor hoặc security integration; với xử lý reactive, không nên dựa vào `ThreadLocal` vì execution có thể đổi thread. Hãy dùng cơ chế context phù hợp với mô hình thực thi.

### 4.2. Root object cho SpEL

Tạo một object nhỏ chỉ phơi bày giá trị cần truy cập:

```java
package com.example.tenancy;

import java.util.UUID;

public record TenantExpressionRoot(UUID tenantId) {
}
```

Root object không nên phơi bày toàn bộ security context, request object hoặc các service có nhiều quyền. Chỉ đưa vào evaluation context những thuộc tính/phương thức cần thiết cho query.

### 4.3. Implement EvaluationContextExtension

```java
package com.example.tenancy;

import org.springframework.data.spel.spi.EvaluationContextExtension;

public class TenantEvaluationContextExtension
        implements EvaluationContextExtension {

    @Override
    public String getExtensionId() {
        return "tenant";
    }

    @Override
    public TenantExpressionRoot getRootObject() {
        return new TenantExpressionRoot(
                TenantContext.requireTenantId()
        );
    }
}
```

`getRootObject()` cung cấp đối tượng gốc cho phần mở rộng evaluation context. Property `tenantId` của root có thể được tham chiếu trong SpEL theo cơ chế root-property của context. `getExtensionId()` định danh extension trong hệ thống mở rộng; không nên tự suy diễn rằng mọi module/phiên bản đều dùng ID này như một prefix trong cú pháp biểu thức. Hãy dùng đúng cú pháp được tài liệu của phiên bản Spring Data JDBC dự án hỗ trợ.

### 4.4. Đăng ký extension thành bean

```java
package com.example.tenancy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.spel.spi.EvaluationContextExtension;

@Configuration
public class QueryExpressionConfiguration {

    @Bean
    EvaluationContextExtension tenantEvaluationContextExtension() {
        return new TenantEvaluationContextExtension();
    }
}
```

Spring Data có thể phát hiện extension bean để mở rộng evaluation context của query method. Việc tự động phát hiện và thời điểm đánh giá phụ thuộc tích hợp của phiên bản module; hãy kiểm tra tài liệu Spring Data Relational đang dùng nếu extension không xuất hiện trong query.

### 4.5. Dùng giá trị root trong @Query

Ví dụ repository:

```java
package com.example.orders;

import java.util.List;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT *
        FROM purchase_orders
        WHERE tenant_id = :#{tenantId}
          AND status = :status
        """)
    List<PurchaseOrder> findForCurrentTenant(
            @Param("status") String status);
}
```

Trong ví dụ, `tenantId` được lấy từ root object do extension cung cấp; `status` là tham số method. Giá trị tenant được đánh giá rồi bind vào vị trí tham số SQL. Tên bảng/cột là ví dụ; cần khớp schema thực tế và cú pháp SpEL được hỗ trợ bởi phiên bản Spring Data JDBC đang dùng.

## 5. Extension có thể cung cấp những gì?

Extension không giới hạn ở tenant. Một số trường hợp có thể hữu ích:

| Nguồn ngữ cảnh | Giá trị có thể cung cấp | Ví dụ mục đích |
| --- | --- | --- |
| Security principal | User ID, username hoặc tenant được xác thực | Lọc bản ghi thuộc người dùng hiện tại |
| Tenant context | Tenant ID hiện tại | Cô lập dữ liệu theo tenant |
| Ngữ cảnh ứng dụng | Một giá trị phân vùng hoặc đơn vị kinh doanh | Áp dụng bộ lọc mặc định cho query |
| Chính sách đơn giản | Một hàm/giá trị được giới hạn rõ | Chuẩn hóa hoặc tính giá trị bind |

Với Spring Security, một extension có thể cung cấp root object dựa trên authentication hiện tại. Khi đó biểu thức có thể đọc các thuộc tính mà root object công khai, chẳng hạn principal hoặc thông tin quyền, nếu các thuộc tính đó thực sự có trong object và được hỗ trợ trong context.

Không nên đưa cả `SecurityContext`, `HttpServletRequest`, `ApplicationContext` hay bean tùy ý vào SpEL root. Mục tiêu là cung cấp một bề mặt nhỏ, ổn định và dễ kiểm tra.

### Extension ID và root object

Hai khái niệm này có vai trò khác nhau:

- `getExtensionId()` đặt tên cho extension trong cơ chế tích hợp của Spring Data.
- `getRootObject()` cung cấp object để biểu thức truy cập thuộc tính/phương thức.

Không nhầm `extensionId` với tên property của root. Khi xây dựng biểu thức, dựa vào ví dụ và tài liệu chính thức của đúng phiên bản Spring Data, thay vì đoán cú pháp chỉ từ tên ID.

## 6. SpEL trong query chỉ nên tạo giá trị bind

Một điểm quan trọng của việc dùng SpEL trong SQL là phân biệt **giá trị dữ liệu** với **cấu trúc SQL**.

### 6.1. Giá trị bind an toàn

Ví dụ:

```java
@Query("""
    SELECT *
    FROM customers
    WHERE email = :#{#email}
    """)
List<Customer> findByEmailExpression(@Param("email") String email);
```

Email được đánh giá thành một giá trị rồi bind như parameter. Dù email có chứa dấu nháy đơn hoặc chuỗi giống cú pháp SQL, nó vẫn là dữ liệu parameter chứ không trở thành câu lệnh SQL.

### 6.2. Không dùng SpEL để thay tên bảng hoặc cột tùy ý

Không thiết kế query theo kiểu cố gắng thay thế identifier:

```text
SELECT * FROM :#{#tableName}
```

Bind parameter JDBC đại diện cho **giá trị**, không đại diện cho tên bảng, tên cột, từ khóa SQL hay đoạn `ORDER BY`. Tương tự, không lấy một đoạn SQL do client gửi rồi nhúng vào query bằng SpEL.

Nếu cần chọn một trong vài bảng/cột hoặc hướng sắp xếp, hãy ánh xạ input sang danh sách lựa chọn cố định trong code và xây dựng câu SQL theo cơ chế được kiểm soát. Với truy vấn động phức tạp, dùng `JdbcTemplate`/`NamedParameterJdbcTemplate` hoặc một query builder phù hợp.

### 6.3. Không coi SpEL là bộ lọc quyền truy cập hoàn chỉnh

Ví dụ tenant filter trong repository có thể giúp tránh quên điều kiện tenant ở một query, nhưng nó không tự tạo ranh giới bảo mật cho toàn hệ thống. Cần xem xét:

- Mọi đường truy cập dữ liệu có đi qua repository method được bảo vệ không?
- Có câu SQL tùy chỉnh khác bỏ qua tenant filter không?
- Job nền có thiết lập tenant context trước khi chạy không?
- Có cần database row-level security hoặc constraint riêng không?
- Người dùng có thể điều khiển tenant ID qua request hay chỉ tenant đã được xác thực mới được dùng?

Tenant ID nên được lấy từ ngữ cảnh đã xác thực hoặc truyền qua một use case đã kiểm tra quyền. Không tin giá trị tenant do client tự gửi chỉ vì nó được đưa vào SpEL.

## 7. Khi nào nên dùng tham số method thay cho extension?

Extension tiện lợi khi giá trị ngữ cảnh thực sự là ngữ cảnh dùng chung, chẳng hạn tenant đã xác định cho request. Tuy nhiên, tham số tường minh thường có ưu điểm:

- Method signature cho thấy query phụ thuộc dữ liệu nào.
- Dễ gọi trong batch, scheduled job và message consumer.
- Unit test không phải thiết lập global/thread context.
- Không phụ thuộc vào trạng thái security/request ẩn.
- Có thể dùng cùng một method cho nhiều tenant nếu use case cho phép.

Ví dụ tham số tường minh:

```java
@Query("""
    SELECT *
    FROM purchase_orders
    WHERE tenant_id = :tenantId
      AND status = :status
    """)
List<PurchaseOrder> findByTenantAndStatus(
        @Param("tenantId") UUID tenantId,
        @Param("status") String status
);
```

Chọn extension khi ngữ cảnh là một phần mặc định của cách ứng dụng thực thi query và được thiết lập đáng tin cậy. Chọn tham số tường minh khi tenant/user là dữ liệu đầu vào thực sự của use case hoặc khi caller cần kiểm soát rõ ràng.

## 8. Những giới hạn cần nhớ

### 8.1. SpEL không thay thế SQL

SpEL tính giá trị biểu thức. Nó không thay thế khả năng của SQL trong JOIN, grouping, window function, CTE hoặc tối ưu execution plan. Nếu một truy vấn cần các khả năng đó, hãy viết SQL phù hợp.

### 8.2. Chỉ dùng trong vị trí biểu thức được query parser hỗ trợ

Không giả định có thể đặt SpEL ở bất kỳ vị trí nào trong câu SQL. Tập vị trí hỗ trợ phụ thuộc module và phiên bản. Trường hợp phổ biến là biểu thức tạo giá trị bind parameter. Nếu muốn dùng expression để thay identifier hoặc tạo cả đoạn query, hãy kiểm tra tài liệu và cân nhắc công cụ khác.

### 8.3. Kiểu kết quả phải bind được qua JDBC

Giá trị SpEL trả về cần có kiểu mà mapping/JDBC có thể chuyển thành kiểu SQL của parameter. UUID, String, số, enum hoặc kiểu ngày giờ được hỗ trợ thường dễ xử lý hơn object tùy chỉnh. Nếu expression trả về một object phức tạp, hãy lấy thuộc tính scalar cụ thể hoặc chuyển đổi ở application service.

### 8.4. Context có thể không tồn tại ngoài request

Một extension gọi `TenantContext.requireTenantId()` có thể hoạt động trong HTTP request nhưng thất bại ở scheduler hoặc consumer nếu các luồng đó không thiết lập context. Hãy định nghĩa rõ hành vi khi không có principal/tenant: từ chối query, yêu cầu truyền tham số tường minh hoặc dùng một context hệ thống có giới hạn.

### 8.5. Extension phải an toàn khi được gọi nhiều lần

Không lưu request-specific state vào field mutable của một extension bean singleton. Bean có thể được dùng đồng thời bởi nhiều request. Hãy đọc context hiện tại tại thời điểm đánh giá hoặc truyền giá trị qua tham số; không cache tenant/user của request trước vào instance dùng chung.

## 9. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| SpEL báo không tìm thấy property | Tên property không có trong tham số hoặc root object | Kiểm tra tên tham số, getter/record accessor và root object trả về từ extension. |
| Biểu thức không nhận được extension | Bean chưa được đăng ký, package/configuration không được scan hoặc module/version không tích hợp extension như kỳ vọng | Xác nhận bean được tạo và kiểm tra tài liệu Spring Data Relational của phiên bản dự án. |
| Query báo thiếu parameter | Tên placeholder và tên `@Param` không khớp, hoặc biểu thức không được parser nhận diện | Đối chiếu tên placeholder, annotation và cú pháp biểu thức. |
| Lỗi khi chạy job nền | Tenant/security context không được thiết lập ngoài HTTP request | Truyền tenant rõ ràng hoặc thiết lập context có kiểm soát trước khi gọi repository. |
| Query trả dữ liệu sai tenant | Context lấy sai nguồn, bị giữ lại giữa request hoặc query khác bỏ qua filter | Xem lifecycle set/clear, kiểm tra mọi đường truy cập và cân nhắc bảo vệ ở database. |
| SQL sai khi dùng expression cho identifier | Parameter binding không thể thay tên bảng/cột | Chọn identifier từ whitelist trong code hoặc xây dựng SQL có kiểm soát. |
| Kiểu parameter không tương thích | SpEL trả về object không map được sang JDBC type | Trả về scalar/kiểu được hỗ trợ hoặc chuyển đổi trước khi gọi repository. |

### Quan sát SQL

Bật log Spring JDBC trong môi trường phát triển:

```properties
logging.level.org.springframework.jdbc=DEBUG
logging.level.org.springframework.jdbc.core.StatementCreatorUtils=TRACE
```

Log giúp kiểm tra câu SQL và thông tin bind parameter. Hãy cẩn thận khi bật TRACE trong môi trường có dữ liệu nhạy cảm: giá trị được bind có thể chứa email, user ID hoặc thông tin cá nhân.

Khi debug SpEL, tách vấn đề thành ba câu hỏi:

1. Bean `EvaluationContextExtension` đã được tạo chưa?
2. Root object có cung cấp property mà expression yêu cầu không?
3. Giá trị expression có được chuyển thành parameter đúng kiểu và được bind vào SQL không?

## 10. Ví dụ kiểm thử extension độc lập

Có thể kiểm tra phần root object mà không cần database:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

class TenantEvaluationContextExtensionTest {

    @AfterEach
    void clearContext() {
        TenantContext.clear();
    }

    @Test
    void exposesCurrentTenantAsRootProperty() {
        UUID expected = UUID.randomUUID();
        TenantContext.setTenantId(expected);

        TenantEvaluationContextExtension extension =
                new TenantEvaluationContextExtension();

        assertEquals("tenant", extension.getExtensionId());
        assertEquals(
                expected,
                extension.getRootObject().tenantId()
        );
    }
}
```

Đây chỉ kiểm tra extension cung cấp đúng root object. Một integration test repository vẫn cần thiết để chứng minh query parser đánh giá expression và bind giá trị vào SQL trong đúng phiên bản Spring Data JDBC của ứng dụng.

Với integration test, nên:

- Thiết lập tenant A, lưu dữ liệu cho A và B.
- Gọi query trong context A và xác nhận chỉ thấy dữ liệu A.
- Đổi sang context B và xác nhận chỉ thấy dữ liệu B.
- Xóa context sau mỗi test để tránh rò rỉ trạng thái giữa test.
- Thử gọi query khi không có tenant context và xác nhận hành vi fail-closed theo thiết kế.

## 11. Quy trình thiết kế query có SpEL

Khi cần một giá trị động trong `@Query`, thực hiện theo thứ tự:

1. **Xác định giá trị cần bind.** Đó là status, tenant ID, user ID hay một giá trị đã chuẩn hóa?
2. **Xem có thể dùng named parameter thường không.** Nếu caller đã có giá trị, ưu tiên truyền trực tiếp.
3. **Nếu cần context dùng chung, định nghĩa root object nhỏ.** Chỉ phơi bày thuộc tính cần thiết.
4. **Đăng ký extension như bean.** Bảo đảm cấu hình nằm trong phạm vi Spring Data repository.
5. **Viết biểu thức tại placeholder được hỗ trợ.** Expression nên trả về scalar/kiểu JDBC có thể bind.
6. **Kiểm tra SQL và giá trị bind.** Dùng log hoặc instrumentation trong môi trường an toàn.
7. **Kiểm thử nhiều context.** Bao gồm request, background job và trường hợp context vắng mặt.
8. **Đánh giá ranh giới bảo mật.** Không coi expression filter là cơ chế bảo vệ duy nhất.

## 12. Bài tập tự thực hành

**Bài tập 1 — SpEL với tham số.** Viết query method lọc customer theo email và dùng `:#{#email}`. So sánh với named parameter `:email`; giải thích trường hợp nào expression đem lại lợi ích.

**Bài tập 2 — Chuẩn hóa đầu vào.** Dùng SpEL gọi `trim()` và `toLowerCase()` trên tham số chuỗi. Kiểm tra giá trị SQL nhận được và xem việc chuẩn hóa có nên nằm ở application service hay không.

**Bài tập 3 — Tenant extension.** Tạo `TenantEvaluationContextExtension`, đăng ký bean và dùng root property trong query. Lưu dữ liệu cho hai tenant rồi kiểm tra kết quả độc lập.

**Bài tập 4 — Context không tồn tại.** Gọi repository từ một job không thiết lập tenant. Xác định hành vi mong muốn và sửa thiết kế bằng tham số tenant tường minh hoặc context hệ thống có kiểm soát.

**Bài tập 5 — Không ghép identifier.** Thử thiết kế một query có tên bảng lấy từ SpEL. Giải thích vì sao bind parameter không thay thế identifier; thay bằng whitelist hoặc SQL builder.

**Bài tập 6 — Kiểm thử tích hợp.** Viết test xác nhận extension thực sự được dùng trong query method trên database mà dự án triển khai. Kiểm tra cả trường hợp không có tenant và trường hợp hai tenant cùng tồn tại dữ liệu.

## 13. Ghi nhớ

Trong Spring Data JDBC, SpEL hữu ích khi một query cần tính giá trị parameter từ method arguments hoặc evaluation context. `EvaluationContextExtension` cho phép ứng dụng cung cấp root object và ngữ cảnh bổ sung cho việc đánh giá biểu thức. Một ví dụ thường gặp là tenant ID hoặc thuộc tính của principal hiện tại.

Hãy giữ biểu thức ngắn, trả về giá trị có thể bind qua JDBC và chỉ sử dụng ở vị trí mà query method của phiên bản Spring Data JDBC hỗ trợ. SpEL không phải công cụ thay thế SQL, không thay tên bảng/cột bằng bind parameter và không phải ranh giới bảo mật đầy đủ. Với giá trị đã có ở caller, named parameter tường minh thường dễ hiểu hơn; extension phù hợp khi đó là ngữ cảnh dùng chung được thiết lập và quản lý đáng tin cậy.

### Tài liệu tham khảo

- [Spring Data Relational – Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Data Commons – EvaluationContextExtension API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/spel/spi/EvaluationContextExtension.html)
- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)

