# Ranh giới giữa API công khai, SPI mở rộng và chi tiết nội bộ không nên phụ thuộc trong Hibernate

Khi sử dụng Hibernate, lập trình viên thường thấy rất nhiều lớp, interface và annotation dưới các package như `jakarta.persistence`, `org.hibernate`, `org.hibernate.spi`, `org.hibernate.engine` hay `org.hibernate.internal`. Chúng có thể đều xuất hiện trong JAR và đều có những kiểu khai báo `public` của Java, nhưng **không có cùng mục đích sử dụng hoặc mức cam kết tương thích**.

Hiểu đúng ranh giới này là một phần quan trọng của kiến trúc ứng dụng: sử dụng API thích hợp giúp mã dễ bảo trì, tận dụng được Hibernate và giới hạn ảnh hưởng khi nâng cấp; phụ thuộc trực tiếp vào cấu trúc triển khai có thể khiến ứng dụng hỏng chỉ vì framework thay đổi một lớp nội bộ.

Bài học tập trung vào ba câu hỏi:

1. **API công khai** nào ứng dụng nên dùng để truy cập dữ liệu?
2. **SPI mở rộng** nào dành cho người xây dựng tích hợp hoặc tùy biến Hibernate?
3. **Chi tiết nội bộ** nào chỉ nên để Hibernate tự sử dụng, dù có thể truy cập từ mã Java?

## 1. Phân biệt ba loại hợp đồng

### 1.1. API công khai: hợp đồng dành cho người sử dụng Hibernate

**API (*Application Programming Interface*)** là các kiểu, phương thức và hành vi mà framework công bố để ứng dụng gọi vào.

Hibernate có hai nhóm API thường gặp:

- **API chuẩn Jakarta Persistence**: `EntityManager`, `EntityManagerFactory`, `@Entity`, `@Id`, `@ManyToOne`, JPQL, Criteria API, `Metamodel`… Đây là hợp đồng được định nghĩa bởi đặc tả Jakarta Persistence, còn Hibernate là một provider triển khai.
- **API riêng, được Hibernate hỗ trợ công khai**: ví dụ `org.hibernate.Session`, `SessionFactory`, `org.hibernate.query.Query` và một số API truy vấn, thống kê hoặc đặc tính nâng cao của Hibernate. Các API này có thể rất phù hợp khi ứng dụng chủ ý chọn Hibernate, nhưng không chuyển nguyên trạng sang provider khác.

Từ “công khai” ở đây có nghĩa là **được công bố để bên ngoài sử dụng theo mục đích thiết kế**, không chỉ là có từ khóa `public` trong khai báo Java.

### 1.2. SPI mở rộng: hợp đồng dành cho người tích hợp vào Hibernate

**SPI (*Service Provider Interface*)** là điểm mở rộng để framework **gọi lại mã do ứng dụng hoặc thư viện tích hợp cung cấp**. Một SPI có thể là interface cần hiện thực, service cần đăng ký hoặc callback cần triển khai.

Ví dụ về những nhu cầu có thể dùng SPI/tích hợp do Hibernate công bố:

- Can thiệp hoặc quan sát chuỗi SQL do Hibernate chuẩn bị thông qua `StatementInspector`.
- Tích hợp dịch vụ ở quá trình bootstrap qua cơ chế `Integrator` hoặc contributor phù hợp phiên bản.
- Tùy biến việc cung cấp kết nối hoặc tenant bằng các contract dành cho multitenancy.
- Đóng góp kiểu dữ liệu hoặc cơ chế ánh xạ nâng cao khi converter theo Jakarta Persistence không đủ.

SPI **có thể được dùng bên ngoài** vì đó chính là mục đích của nó. Tuy nhiên, đây thường là hợp đồng chuyên sâu, gắn chặt hơn với kiến trúc Hibernate và có thể thay đổi nhiều hơn qua các lần nâng cấp, đặc biệt khi API còn được đánh dấu *incubating*.

### 1.3. Chi tiết nội bộ: cấu trúc hiện thực, không phải điểm tích hợp được cam kết

Hibernate cần nhiều lớp để thực thi ORM: bộ quản lý persistence context, entity persister, action queue, bộ sinh SQL, các implementation của `Session`, proxy, bộ phát hiện thay đổi, bộ khởi tạo mapping…

Những cấu trúc này phục vụ **cách Hibernate thực hiện công việc**, không phải lời hứa rằng mã ứng dụng có thể dựa vào chúng lâu dài.

Ví dụ: thay vì ép đối tượng sang `org.hibernate.internal.SessionImpl` để gọi một phương thức của implementation, hãy tìm hợp đồng `Session`, `EntityManager` hoặc một SPI được tài liệu hóa đáp ứng nhu cầu. Implementation của `Session` có thể đổi trong phiên bản tiếp theo; hợp đồng `Session` là điểm tham chiếu phù hợp hơn.

### Bảng so sánh nhanh

| Tiêu chí | API công khai | SPI mở rộng | Chi tiết nội bộ |
|---|---|---|---|
| Ai chủ động gọi ai? | Ứng dụng gọi framework | Framework gọi extension; thường có đăng ký hoặc bootstrap | Các thành phần Hibernate gọi nhau |
| Người dùng chính | Developer xây dựng nghiệp vụ/repository | Tác giả adapter, thư viện tích hợp, plugin | Người bảo trì Hibernate |
| Ví dụ | `EntityManager`, `Session`, `Query` | `StatementInspector`, `Integrator`, các provider/contributor được hỗ trợ | `SessionImpl`, các class triển khai persister/action queue |
| Mức phụ thuộc | Ưu tiên API chuẩn; native API khi cần | Chỉ dùng cho nhu cầu mở rộng rõ ràng | Tránh phụ thuộc trực tiếp |
| Rủi ro nâng cấp | Theo hợp đồng và chính sách phiên bản | Có thể cao hơn, tùy SPI và trạng thái API | Cao, có thể đổi mà không giữ tương thích |

**Nguyên tắc xuyên suốt:** chọn **hợp đồng có phạm vi hẹp nhất nhưng được hỗ trợ chính thức** cho nhu cầu của mình. Không cần dùng SPI để thực hiện CRUD thông thường; cũng không cần né mọi API riêng của Hibernate nếu hệ thống thực sự cần chúng.

## 2. Vị trí các ranh giới trong kiến trúc

Một cách hình dung các lớp phụ thuộc:

```text
                  ỨNG DỤNG JAVA
+------------------------------------------------+
| Domain / Application Service                   |
|    |                                           |
|    v                                           |
| Repository / Persistence Adapter               |
+----+----------------------+--------------------+
     |                      |
     | thao tác dữ liệu      | tích hợp đặc biệt
     v                      v
+------------------+   +------------------------+
| PUBLIC API       |   | SUPPORTED EXTENSION SPI|
| Jakarta          |   | StatementInspector,     |
| Persistence      |   | Integrator, providers…  |
| hoặc Session API |   +------------+-----------+
+--------+---------+                |
         |                          |
         v                          v
+------------------------------------------------+
|                  HIBERNATE ORM                 |
|     Implementation, SQL generation, dirty      |
|     checking, mapping engine, action queue…    |
|     (các chi tiết nội bộ)                      |
+------------------------+-----------------------+
                         |
                         v
                     JDBC driver
                         |
                         v
                 Relational Database
```

Phía **ứng dụng** chọn và sử dụng hợp đồng công khai. Phía **Hibernate** tự quyết định sử dụng thuật toán, class và cấu trúc nội bộ nào để thực thi hợp đồng đó. Khi cần tùy biến, ứng dụng cung cấp một implementation của SPI đã được hỗ trợ, rồi để Hibernate gọi vào implementation ấy.

Ranh giới này không đồng nghĩa với việc ứng dụng không bao giờ được import `org.hibernate.*`. Cần phân loại **từng contract theo tài liệu và mục đích sử dụng**, vì cùng namespace có cả API dành cho ứng dụng, SPI và implementation.

## 3. Tầng API thứ nhất: ưu tiên Jakarta Persistence cho thao tác thông thường

Với các thao tác lưu, tải, sửa, xóa và truy vấn entity, Jakarta Persistence thường là lựa chọn tự nhiên.

Ví dụ một persistence adapter tối giản:

```java
import jakarta.persistence.EntityManager;

public final class JpaPurchaseOrderRepository {
    private final EntityManager entityManager;

    public JpaPurchaseOrderRepository(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    public PurchaseOrder findById(Long id) {
        return entityManager.find(PurchaseOrder.class, id);
    }

    public void saveNew(PurchaseOrder order) {
        entityManager.persist(order);
    }
}
```

`PurchaseOrder` ở đây là entity đã được mapping. Đoạn mã không cần biết Hibernate sử dụng implementation `Session` nào, persister nào hoặc cache nội bộ nào. Các thao tác ghi được kỳ vọng thực hiện trong transaction thích hợp do môi trường ứng dụng quản lý.

Một ví dụ truy vấn bằng JPQL:

```java
List<PurchaseOrder> orders = entityManager.createQuery("""
        select o
        from PurchaseOrder o
        where o.status = :status
        order by o.createdAt desc
        """, PurchaseOrder.class)
    .setParameter("status", OrderStatus.CONFIRMED)
    .setMaxResults(20)
    .getResultList();
```

Đây là ngôn ngữ truy vấn **entity và thuộc tính của entity**, chứ không trực tiếp dựa vào cấu trúc `SessionImpl`, trình biên dịch truy vấn hoặc đối tượng SQL AST mà Hibernate dùng phía dưới.

### Ví dụ mở rộng bằng API chuẩn: AttributeConverter

Giả sử domain có kiểu `EmailAddress` riêng, còn database lưu bằng `VARCHAR`. Có thể dùng điểm mở rộng chuẩn Jakarta Persistence:

```java
public record EmailAddress(String value) {
}

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {

    @Override
    public String convertToDatabaseColumn(EmailAddress email) {
        return email == null ? null : email.value();
    }

    @Override
    public EmailAddress convertToEntityAttribute(String dbValue) {
        return dbValue == null ? null : new EmailAddress(dbValue);
    }
}
```

Các đoạn trên minh họa hai file Java khác nhau (kiểu `EmailAddress` và converter). Converter là một **điểm mở rộng chuẩn**; không cần truy cập hệ thống type descriptor nội bộ của Hibernate cho trường hợp đơn giản này.

Sử dụng API chuẩn giúp **giảm mức phụ thuộc vào provider**, nhưng không bảo đảm mọi behavior và hiệu năng giống nhau giữa các database/provider. Chiến lược fetch, SQL thực tế, dialect, transaction isolation và khả năng hỗ trợ đặc thù vẫn phải được kiểm chứng trên môi trường chạy thật.

## 4. Tầng API thứ hai: sử dụng Hibernate native API khi có lý do

Hibernate công khai nhiều tính năng ngoài Jakarta Persistence. Ví dụ ứng dụng cần điều chỉnh kích thước JDBC batch ở phạm vi một phiên làm việc và đang chủ ý sử dụng Hibernate.

Trong ứng dụng đã có `EntityManager`:

```java
import jakarta.persistence.EntityManager;
import org.hibernate.Session;

public final class HibernateBatchTuning {
    public static void configureBatch(EntityManager em, int batchSize) {
        Session session = em.unwrap(Session.class);
        session.setJdbcBatchSize(batchSize);
    }
}
```

`EntityManager.unwrap(Session.class)` là cách yêu cầu đối tượng native theo hợp đồng chuẩn của Jakarta Persistence. `Session` và `setJdbcBatchSize` là API riêng của Hibernate; adapter này cần Hibernate làm provider và API tương ứng trong phiên bản được chọn.

Sử dụng native API là quyết định hợp lệ khi:

- Yêu cầu chức năng không thể biểu diễn tốt bằng Jakarta Persistence.
- Hibernate là provider được lựa chọn chính thức cho ứng dụng.
- Chi phí phụ thuộc được khoanh vào một nơi dễ nâng cấp.
- Tính năng được tài liệu Hibernate trình bày như API được hỗ trợ.

**Không nên tìm đường đi vòng vào `SessionImpl` hoặc `SessionFactoryImpl`** chỉ vì đã sử dụng `Session` hoặc `SessionFactory`. Từ API native đến implementation nội bộ vẫn là một ranh giới độc lập.

### Hai cấp độ “public” khác nhau

Cần tách hai nhận định:

- `Session` là **Hibernate public API**: dùng được theo tài liệu Hibernate, nhưng không phải API của Jakarta Persistence.
- `EntityManager` là **Jakarta Persistence API**: được chuẩn hóa ở cấp đặc tả, các provider khác cũng phải hỗ trợ phần tương ứng mà họ công bố tuân thủ.

Nếu việc đổi provider là yêu cầu kiến trúc quan trọng, hãy hạn chế những lệnh `unwrap` trong adapter Hibernate. Nếu ứng dụng chắc chắn sử dụng Hibernate, public native API có thể đem lại lợi ích thiết thực mà không cần che giấu mọi khác biệt.

## 5. SPI hoạt động ra sao?

Luồng phổ biến của một SPI:

```text
Ứng dụng / thư viện tích hợp
    |
    | implements một interface SPI
    | đăng ký bằng cấu hình, ServiceLoader hoặc bootstrap
    v
Hibernate nhận implementation
    |
    | gọi callback tại thời điểm phù hợp
    v
Mã extension thực thi hành vi tùy biến
```

Điểm khác với API thông thường là **chiều điều khiển**. Khi sử dụng `EntityManager.find(...)`, ứng dụng gọi Hibernate. Khi cung cấp `StatementInspector`, Hibernate gọi phương thức do ứng dụng triển khai trong quá trình chuẩn bị SQL.

### Ví dụ SPI: StatementInspector

`StatementInspector` là contract do Hibernate công bố trong package `org.hibernate.resource.jdbc.spi`. Nó cho phép kiểm tra hoặc thay đổi chuỗi SQL trước khi JDBC statement được chuẩn bị.

Một extension đếm số lần Hibernate đưa chuỗi SQL qua inspector:

```java
import java.util.concurrent.atomic.LongAdder;

import org.hibernate.resource.jdbc.spi.StatementInspector;

public final class CountingStatementInspector
        implements StatementInspector {

    private final LongAdder inspected = new LongAdder();

    @Override
    public String inspect(String sql) {
        inspected.increment();
        return sql; // Giữ nguyên SQL.
    }

    public long inspectedSqlCount() {
        return inspected.sum();
    }
}
```

Tùy cơ chế cấu hình/bootstrap, Hibernate có thể nhận class hoặc instance của inspector. Ví dụ cấu hình property của Hibernate:

```properties
hibernate.session_factory.statement_inspector=com.example.persistence.CountingStatementInspector
```

Để sử dụng đúng, đặt class ở package tương ứng, có constructor thích hợp và đăng ký property trong cấu hình thực sự được Hibernate xử lý.

**Điểm cần hiểu về ví dụ:**

- `StatementInspector` là điểm mở rộng cho SQL được chuẩn bị; số lần gọi inspector **không phải phép đo chuẩn xác về số câu SQL đã thực thi thành công**.
- Nếu một inspector được dùng chung, mã callback phải an toàn khi có nhiều phiên/luồng cùng truy cập. Ví dụ dùng `LongAdder` thay vì biến `long` thường.
- Chỉ thay đổi chuỗi SQL khi thật sự hiểu ràng buộc SQL, tham số, dialect và quy trình Hibernate. Đối với thống kê sản xuất, logging/metrics chuẩn có thể thích hợp hơn.
- Việc có interface SPI không có nghĩa ứng dụng nên dựng một SPI cho mọi yêu cầu nhỏ.

### Các SPI khác và mức độ gắn kết

| Nhu cầu | Hướng tiếp cận | Điểm cần cân nhắc |
|---|---|---|
| Chuyển value object thành kiểu cột cơ bản | `AttributeConverter` của Jakarta Persistence | Thường ưu tiên vì là chuẩn và đơn giản |
| Quan sát/điều chỉnh SQL tại điểm Hibernate cho phép | `StatementInspector` | Phụ thuộc SPI Hibernate; cần kiểm tra tài liệu phiên bản |
| Tích hợp trong giai đoạn khởi động Hibernate | `Integrator` hoặc cơ chế contributor được tài liệu hóa | Đặc biệt nhạy cảm với thay đổi bootstrap qua các phiên bản |
| Cấp phát connection theo tenant | Contract multitenancy như `MultiTenantConnectionProvider` trong phiên bản đang dùng | Liên quan connection lifecycle, transaction và cách chọn tenant |
| Hỗ trợ kiểu JDBC/SQL đặc biệt | API type mapping hoặc contributor chính thức | Có thể chịu thay đổi đáng kể giữa các đời Hibernate |

Không nên mặc định một SPI có cùng chữ ký trên mọi bản Hibernate: hãy kiểm tra **Javadoc và migration guide của đúng version**. Với SPI chuyên sâu, bài test tích hợp cần xác nhận cả điểm đăng ký và thời điểm callback thực sự được framework gọi.

### SPI không phải “bất kỳ interface nào bên trong Hibernate”

Một implementation class hoặc internal interface có thể sở hữu phương thức `public` và vẫn không phải extension point. Ngược lại, một SPI trong package `.spi` được Hibernate công bố có thể được hỗ trợ dùng từ bên ngoài.

Vì vậy, khi tìm điểm mở rộng, câu hỏi không phải “có import được interface này không?” mà là:

> “Hibernate có công bố contract này để bên thứ ba triển khai/gọi, và hướng dẫn cách đăng ký/sử dụng nó ở phiên bản đang chạy hay không?”

## 6. Vì sao phụ thuộc vào implementation nội bộ nguy hiểm?

Đoạn mã sau thể hiện cách ràng buộc không cần thiết vào Hibernate implementation:

```java
import jakarta.persistence.EntityManager;
import org.hibernate.internal.SessionImpl;

// Ví dụ không nên dùng.
SessionImpl impl = (SessionImpl) entityManager.unwrap(
    org.hibernate.Session.class
);
```

Tại thời điểm cụ thể, `SessionImpl` có thể là implementation mà Hibernate trả về. Tuy nhiên, việc ép kiểu này khiến ứng dụng dựa vào **đúng class triển khai**, không còn chỉ dựa vào API `Session`.

Rủi ro gồm:

1. **Sai kiểu khi chạy:** một implementation hoặc wrapper khác có thể được trả về, khiến ép kiểu thất bại.
2. **Không tương thích khi biên dịch:** phương thức hay constructor nội bộ có thể đổi, chuyển package hoặc biến mất.
3. **Phụ thuộc vào thứ tự xử lý:** code có thể dựa trên action queue, flush event hoặc lifecycle nội bộ vốn không được hứa giữ nguyên.
4. **Khó nâng cấp framework:** thay đổi version phải sửa cả mã nghiệp vụ, không chỉ tầng persistence adapter.
5. **Khó kiểm thử độc lập:** test phải mô phỏng đúng các đối tượng nội bộ phức tạp.

Nếu chỉ muốn dùng thao tác được Hibernate hỗ trợ, làm việc qua `Session`:

```java
import jakarta.persistence.EntityManager;
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);
// Sử dụng các phương thức được tài liệu của Session hỗ trợ.
```

Nếu muốn xem metadata entity, hãy cân nhắc API metamodel chuẩn:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.metamodel.EntityType;

EntityType<PurchaseOrder> orderType =
    entityManager.getMetamodel().entity(PurchaseOrder.class);

orderType.getAttributes().forEach(attribute ->
    System.out.println(attribute.getName())
);
```

Ví dụ metamodel trả về **các thuộc tính mapping theo API**, không hứa phơi bày toàn bộ SQL, cấu trúc persister hay engine. Nếu yêu cầu vượt ngoài phạm vi chuẩn, tìm API native/SPI chính thức tương ứng, hoặc cân nhắc thiết kế lại yêu cầu.

### Những dạng phụ thuộc nội bộ thường cần tránh

- Ép kiểu `Session` sang `org.hibernate.internal.SessionImpl` hoặc `SessionFactory` sang implementation tương ứng.
- Import trực tiếp lớp từ `org.hibernate.internal.*` để truy cập trạng thái phiên, metadata hoặc SQL engine.
- Gọi các lớp parser, AST hoặc SQL translator chỉ vì đang thấy chúng trên classpath, khi không có hợp đồng tích hợp công khai.
- Viết code dựa vào đúng tên hoặc kiểu class proxy của lazy association.
- Truy cập trực tiếp action queue, persister, bytecode interceptor hoặc persistence context implementation để điều khiển flush.
- Dùng reflection truy cập field/private method nội bộ nhằm vượt qua giới hạn API.

Không phải mọi interface trong `org.hibernate.engine.spi` đều tuyệt đối “cấm”: một số là contract phục vụ các extension chuyên biệt. Nhưng **package có chữ SPI không tự động xác nhận độ ổn định, còn package không có chữ internal không tự động bảo đảm là API công khai**.

## 7. Cách nhận biết một contract có được hỗ trợ hay không

Không thể phân loại an toàn chỉ dựa vào từ khóa `public` hoặc tên package. Thay vào đó, kết hợp nhiều dấu hiệu:

| Dấu hiệu | Cách diễn giải |
|---|---|
| Được đề cập như API ứng dụng trong User Guide/Javadoc | Có căn cứ sử dụng theo cách đã tài liệu hóa |
| Thuộc `jakarta.persistence.*` | API chuẩn theo đặc tả, trong phạm vi tuân thủ và version tương ứng |
| Là `org.hibernate.Session`, `SessionFactory` hoặc API native được công bố | Có thể dùng khi chọn Hibernate, nhưng vẫn phụ thuộc provider |
| Được mô tả là SPI và có tài liệu về đăng ký/callback | Có thể triển khai cho use case tương ứng, cần xác nhận version |
| Đánh dấu `@Incubating` | API đang phát triển; nên dự phòng thay đổi trong các bản phát hành sau |
| Đánh dấu `@Internal` hoặc nằm trong package implementation nội bộ | Không nên dùng như hợp đồng tích hợp ứng dụng |
| Đánh dấu deprecated | Cần tra hướng thay thế và lịch loại bỏ; không phát triển phụ thuộc mới khi có lựa chọn tốt hơn |
| Chỉ tìm thấy qua IDE decompile/stack trace hoặc source nội bộ | Chưa đủ bằng chứng đây là contract được hỗ trợ |

Ở Hibernate, các annotation trạng thái như `org.hibernate.Incubating` và `org.hibernate.Internal` là những tín hiệu hữu ích khi đọc tài liệu/API. Tuy nhiên, **sự vắng mặt của annotation không phải bảo đảm vô điều kiện rằng một kiểu sẽ ổn định vĩnh viễn**. Quyết định vẫn dựa vào tài liệu công bố, version và phạm vi mà framework hỗ trợ.

### Các mức ổn định cũng phụ thuộc phiên bản

Ngay cả API công khai cũng có thể thay đổi ở **major version** hoặc trong quá trình chuyển đổi đặc tả. Chẳng hạn, hệ sinh thái Hibernate đã chuyển từ namespace `javax.persistence` sang `jakarta.persistence` khi chuyển sang các thế hệ mới dựa trên Jakarta Persistence. Nhiều SPI bootstrap, type system và truy vấn cũng có thay đổi quan trọng giữa các đời Hibernate.

Điều này không có nghĩa mọi import từ Hibernate đều rủi ro như nhau. Mức rủi ro thông thường tăng theo mức độ gắn với framework:

```text
Jakarta Persistence API
         |
         v
Hibernate documented public API
         |
         v
Hibernate supported SPI
         |
         v
Hibernate internal implementation
         
      Phụ thuộc càng sâu, càng cần kiểm soát version chặt chẽ
```

Mũi tên thể hiện **xu hướng phụ thuộc**, không phải quy luật cứng cho từng phương thức. Một SPI được hỗ trợ ổn định có thể ít rủi ro hơn một API native đang incubating; cần kiểm tra contract cụ thể.

## 8. Giữ ranh giới trong cấu trúc mã nguồn

Một lựa chọn dễ bảo trì là tổ chức code theo chức năng và giữ các tích hợp Hibernate tại một lớp biên của ứng dụng.

```text
com.example.orders
├── domain
│   ├── PurchaseOrder.java
│   └── OrderStatus.java
├── application
│   ├── OrderService.java
│   └── OrderRepository.java
└── persistence
    ├── JpaOrderRepository.java
    ├── HibernateBatchTuning.java
    └── CountingStatementInspector.java
```

Ở đây, service làm việc với contract nghiệp vụ `OrderRepository`:

```java
package com.example.orders.application;

import java.util.Optional;

public interface OrderRepository {
    Optional<PurchaseOrder> findById(Long id);
    void add(PurchaseOrder order);
}
```

Adapter triển khai bằng Jakarta Persistence:

```java
package com.example.orders.persistence;

import java.util.Optional;
import jakarta.persistence.EntityManager;

public final class JpaOrderRepository implements OrderRepository {
    private final EntityManager em;

    public JpaOrderRepository(EntityManager em) {
        this.em = em;
    }

    @Override
    public Optional<PurchaseOrder> findById(Long id) {
        return Optional.ofNullable(em.find(PurchaseOrder.class, id));
    }

    @Override
    public void add(PurchaseOrder order) {
        em.persist(order);
    }
}
```

Các ví dụ trên lược bỏ import của `OrderRepository` và `PurchaseOrder` để tập trung vào ranh giới. Chúng giả định entity mapping đã tồn tại và transaction được xử lý ở tầng thích hợp.

Với kiểu thiết kế này, khi quyết định bổ sung một tính năng riêng của Hibernate, phần thay đổi thường nằm trong `persistence`. `OrderService` không cần biết đến `Session`, `StatementInspector` hay implementation của Hibernate.

Đây là **lựa chọn kiến trúc theo mức độ phức tạp**: ứng dụng nhỏ có thể dùng trực tiếp repository với `EntityManager` mà không cần tạo thêm nhiều interface hình thức. Mục tiêu là giới hạn phụ thuộc có ý nghĩa, không tạo abstraction chỉ để tăng số lớp.

### Quy tắc import thực tế

Có thể áp dụng chính sách theo vùng mã:

- **Domain/application:** không import Hibernate-specific API nếu nghiệp vụ không đòi hỏi; tốt nhất không biết implementation persistence.
- **Repository/persistence adapter:** dùng `jakarta.persistence.*` trước; cho phép API native được tài liệu hóa khi cần.
- **Integration/extension package:** cho phép import SPI đã được chấp thuận, kèm thông tin version và mục đích tích hợp.
- **Mọi vùng mã ứng dụng:** tránh tham chiếu trực tiếp `org.hibernate.internal.*` và các implementation nội bộ khác.

Với codebase lớn, quy tắc import có thể được bảo vệ bằng kiểm tra dependency tĩnh như ArchUnit hoặc quy tắc build, với danh sách ngoại lệ được duyệt. Không nên chặn mù quáng toàn bộ `org.hibernate.*` nếu dự án có nhu cầu sử dụng native API hợp lệ.

## 9. Khi cần một tính năng mới, nên quyết định theo trình tự nào?

Giả sử nhóm phát triển muốn “kiểm soát cách Hibernate thực hiện X”. Hãy lần lượt xét:

**Bước 1 — Xác định nhu cầu ở mức hành vi.** Ví dụ “lấy 20 đơn hàng cùng tên khách hàng trong một lần xử lý” khác với “lấy được đối tượng persister đang quản lý thuộc tính customer”. Trường hợp thứ nhất là yêu cầu nghiệp vụ có API truy vấn hợp lý; trường hợp thứ hai thường đang hướng vào implementation.

**Bước 2 — Tìm giải pháp theo chuẩn Jakarta Persistence.** Có thể dùng JPQL `JOIN FETCH`, entity graph, query projection, `AttributeConverter`, `@Version` hoặc transaction API hay không?

**Bước 3 — Tìm Hibernate public API.** Nếu chuẩn không đáp ứng, xem User Guide/Javadoc của phiên bản hiện tại có API native giải quyết yêu cầu hay không.

**Bước 4 — Chỉ dùng SPI khi cần Hibernate gọi extension.** Chẳng hạn có nhu cầu tích hợp quan sát SQL hoặc mở rộng type system đúng nghĩa. Kiểm tra điểm đăng ký và vòng đời callback.

**Bước 5 — Nếu chỉ còn đường vào internal, xem lại thiết kế.** Có thể chuyển công việc sang SQL/query, tự xử lý ở adapter, dùng event/hook chính thức, hoặc chấp nhận đây là tính năng không được Hibernate hỗ trợ. Nếu buộc phải dùng workaround nội bộ, cô lập nó và coi là khoản nợ kỹ thuật có kế hoạch thay thế, không biến thành phụ thuộc của domain.

Một vài quyết định minh họa:

| Yêu cầu | Hướng ưu tiên | Vì sao |
|---|---|---|
| Tìm entity theo khóa | `EntityManager.find` | API chuẩn, trực tiếp |
| Lọc entity và phân trang | JPQL/Criteria, `setMaxResults` và `setFirstResult` | Truy vấn theo contract công khai |
| Thay đổi cách nạp một quan hệ | Entity graph hoặc fetch join phù hợp | Xác định hành vi truy vấn thay vì sửa proxy |
| Ánh xạ một value object đơn giản | `AttributeConverter` | Điểm mở rộng chuẩn |
| Điều chỉnh một khả năng riêng Hibernate | API `Session`/`SessionFactory` được hỗ trợ | Sử dụng tính năng native có chủ đích |
| Quan sát SQL trước khi chuẩn bị statement | `StatementInspector` | Đây là callback mở rộng chính thức |
| Kiểm tra tên field của entity | Jakarta Persistence metamodel | Không cần đọc persister internal |
| Truy cập trực tiếp action queue để ép thứ tự SQL | Tái thiết kế transaction, mapping, flush; xem API hỗ trợ | Action queue là cơ chế triển khai |

## 10. Kiểm soát rủi ro khi phụ thuộc SPI và API riêng Hibernate

Một số hệ thống thực sự cần viết tích hợp sâu. Để phụ thuộc đó có thể bảo trì:

### Ghi rõ version và hợp đồng được dùng

Nêu rõ trong tài liệu kỹ thuật: Hibernate version nào, dùng API/SPI nào, liên kết Javadoc/User Guide của version đó và hành vi nào extension cần bảo đảm. Đừng dựa vào ví dụ tìm thấy ngẫu nhiên từ version cũ.

### Cô lập phụ thuộc vào adapter hoặc module tích hợp

Các kiểu `SessionFactoryImplementor`, `Integrator` hoặc class hỗ trợ bootstrap chuyên sâu, nếu thực sự cần, không nên xuất hiện trong interface của service nghiệp vụ. Giữ chúng phía sau một contract thuộc ứng dụng.

### Coi việc nâng cấp version là thay đổi tích hợp

Khi nâng cấp Hibernate, đọc release notes/migration guide, chú ý:

- Namespace Jakarta Persistence và phiên bản Java được hỗ trợ.
- Thay đổi tên/chữ ký API, trạng thái deprecated/incubating.
- Cơ chế đăng ký extension hoặc bootstrap.
- Hành vi flush, query translation, fetch, type mapping và dialect khi liên quan.
- Khả năng chạy lại test tích hợp với database mà dự án thực sự sử dụng.

Đối với extension SPI, test quan trọng nhất là **hành vi đầu-cuối**: extension có được đăng ký, callback có được gọi vào đúng thời điểm, transaction và SQL có còn đúng hay không. Tránh test phụ thuộc vào tên class proxy hoặc implementation nội bộ nếu không thực sự thuộc yêu cầu sản phẩm.

### Ưu tiên quan sát qua kênh được hỗ trợ

Nếu mục tiêu là đo số lượng query, xác định N+1, chẩn đoán flush hoặc xem SQL, sử dụng logging, thống kê Hibernate được công bố và công cụ quan sát JDBC/database. Đọc trực tiếp field internal của persistence context thường tạo thêm rủi ro mà không đem lại giá trị nghiệp vụ tương xứng.

## 11. Các hiểu lầm thường gặp

**“Lớp nào khai báo `public` thì đều thuộc public API.”**  
Không chính xác. Modifier `public` quyết định khả năng truy cập trong Java; **API/SPI/internal** mô tả mục đích thiết kế và hợp đồng hỗ trợ.

**“Tên package có `spi` tức là tuyệt đối ổn định.”**  
Không đúng. SPI là điểm mở rộng dành cho tích hợp; mức ổn định phụ thuộc từng contract, trạng thái API và phiên bản Hibernate.

**“Hễ import `org.hibernate.*` là đang dùng internal.”**  
Không đúng. `Session` và nhiều kiểu khác là Hibernate native public API. Đánh giá bằng tài liệu và mục đích của từng kiểu.

**“Dùng Jakarta Persistence thì có thể thay provider mà không cần sửa gì.”**  
Không chắc. API chuẩn giảm phụ thuộc ở bề mặt mã, nhưng SQL dialect, behavior loading, schema generation, query extension và các cấu hình riêng có thể khác nhau.

**“Tùy biến sâu phải subclass một lớp implementation nội bộ.”**  
Thường không. Hãy tìm documented SPI, extension hook, converter, interceptor hoặc API công khai thích hợp trước. Subclass nội bộ có thể dựa vào những constructor và invariant mà framework không cam kết giữ.

**“Test chạy được với version hiện tại chứng tỏ cách dùng internal là an toàn.”**  
Test chỉ xác nhận một cấu hình ở thời điểm đó. Code phụ thuộc implementation vẫn có thể hỏng khi đổi provider wrapper, Hibernate version hoặc điều kiện vận hành.

## 12. Tổng kết theo tình huống

Bạn đang viết chức năng nghiệp vụ lưu và tìm đơn hàng? **Hãy bắt đầu từ Jakarta Persistence API**. Bạn cần một khả năng được Hibernate công bố nhưng không có trong chuẩn? **Dùng Hibernate native public API**, khoanh trong adapter phù hợp. Bạn đang viết một thư viện tích hợp để Hibernate gọi vào lifecycle/SQL/type system? **Dùng documented SPI**, ghi rõ version và kiểm thử hành vi extension. Bạn thấy một lớp `SessionImpl`, persister hoặc action queue trong debugger? **Xem nó là chi tiết triển khai**, không biến cấu trúc nội bộ ấy thành contract của ứng dụng.

Ranh giới API–SPI–internal giúp phân định trách nhiệm: **ứng dụng phụ thuộc vào hành vi được hứa hỗ trợ; phần triển khai phụ thuộc vào chính Hibernate**. Giữ được ranh giới này cho phép tận dụng các tính năng mạnh của ORM, trong khi vẫn kiểm soát được độ phức tạp và chi phí nâng cấp về sau.
