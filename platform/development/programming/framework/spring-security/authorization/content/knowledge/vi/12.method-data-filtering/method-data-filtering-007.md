# Giới hạn của lọc trong bộ nhớ với dữ liệu lớn

## 1. Bài toán và mục tiêu

Trong Spring Security, **lọc dữ liệu ở mức phương thức** có thể áp dụng biểu thức phân quyền cho từng phần tử của tham số đầu vào (`@PreFilter`) hoặc giá trị trả về (`@PostFilter`). Cách này thuận tiện khi cần trả về những tài liệu thuộc người dùng hiện tại, chẳng hạn: người dùng `alice` chỉ được thấy tài liệu có `ownerUsername = "alice"`.

Tuy nhiên, nếu phương thức đã tải hàng trăm nghìn hoặc hàng triệu bản ghi rồi mới chạy `@PostFilter`, ứng dụng vẫn phải trả giá cho **việc truy vấn, truyền dữ liệu, tạo đối tượng và giữ dữ liệu trong bộ nhớ** trước khi những phần tử không được phép bị loại bỏ. Khi dữ liệu lớn, đây là vấn đề về hiệu năng, bộ nhớ, tính đúng đắn của phân trang và vị trí thực thi chính sách bảo mật.

Sau bài học, cần phân biệt được lọc trong Java với lọc ngay tại nguồn dữ liệu; giải thích vì sao `@PostFilter` không làm câu SQL tự động thêm `WHERE`; biết cách đưa điều kiện quyền truy cập vào truy vấn và kiểm chứng phân trang, quyền truy cập, hiệu năng.

## 2. Cơ chế lọc dữ liệu phương thức

Bật bảo mật mức phương thức cho Spring bean bằng `@EnableMethodSecurity`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

Trong ứng dụng Spring Boot có Spring Security, cấu hình này kích hoạt các interceptor cho `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter`. Spring Security Starter không tự bật method security chỉ vì đã được khai báo phụ thuộc.

| Cơ chế | Thời điểm | Đối tượng kiểm tra | Tác động lên việc tải dữ liệu |
| --- | --- | --- | --- |
| `@PreAuthorize` | Trước khi gọi phương thức | Quyền gọi phương thức, tham số | Có thể từ chối sớm; không tự lọc các hàng SQL |
| `@PreFilter` | Trước thân phương thức | Từng phần tử của tham số tập hợp | Phần tử đầu vào đã được tạo/nhận; không tự sửa truy vấn dữ liệu |
| `@PostFilter` | Sau khi thân phương thức trả kết quả | Từng phần tử của tập hợp kết quả | Dữ liệu thường đã được đọc và ánh xạ thành đối tượng |
| Lọc bằng `WHERE`/ACL ở database | Trong truy vấn | Những hàng phù hợp với người dùng, tenant và quyền | Giảm số hàng đi vào ứng dụng **trước** khi tạo kết quả |

Ví dụ trong một Spring service (đoạn minh họa, giả định `Document` là JPA entity có getter `getOwnerUsername()` và `DocumentRepository` kế thừa `JpaRepository`):

```java
import java.util.List;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PostFilter("filterObject.ownerUsername == authentication.name")
    public List<Document> listMine() {
        return repository.findAll();
    }
}
```

Khi `alice` gọi `listMine()` qua Spring proxy, `repository.findAll()` vẫn truy xuất **tất cả** tài liệu trong phạm vi truy vấn. Sau đó Spring Security đánh giá `filterObject` cho từng phần tử và loại phần tử không thuộc `alice` khỏi kết quả trả về. `authentication.name` lấy từ ngữ cảnh xác thực; `filterObject` là phần tử đang được kiểm tra. Từng phần tử có thể được bảo vệ ở kết quả cuối, nhưng toàn bộ quá trình tải dữ liệu đã xảy ra.

Lưu ý: annotation mức phương thức được áp dụng qua cơ chế interceptor/proxy của Spring; gọi nội bộ bằng `this.listMine()` trong cùng đối tượng có thể bỏ qua interceptor. Đặt quy tắc ở biên service rõ ràng và kiểm thử đường gọi thực tế.

## 3. Tại sao tập dữ liệu lớn làm lọc trong bộ nhớ đắt đỏ?

Giả sử bảng có **2.000.000** tài liệu, trong đó người dùng chỉ được xem **10.000** tài liệu (0,5%). Để lấy 10.000 tài liệu bằng `findAll()` rồi `@PostFilter`, hệ thống có thể phải:

1. Quét/đọc và trả về 2.000.000 hàng (tùy kế hoạch truy vấn).
2. Truyền khối lượng dữ liệu lớn từ database sang JVM.
3. Tạo đối tượng Java, ánh xạ JPA và có thể giữ nhiều entity trong persistence context.
4. Kiểm tra biểu thức phân quyền cho từng phần tử rồi xây dựng kết quả được giữ lại.
5. Thu gom các đối tượng bị loại sau khi chúng đã làm tăng áp lực heap và GC.

Nếu trung bình mỗi hàng chiếm **1 KiB dữ liệu truyền**, riêng phần dữ liệu thô đã xấp xỉ **1,9 GiB**, chưa tính chi phí của đối tượng Java, ORM, bộ đệm hay quan hệ liên kết. Đây là ví dụ tính nhẩm theo giả định, không phải số đo cố định cho mọi hệ thống.

- **Thời gian:** kiểm tra trong bộ nhớ thường phải xét khoảng `N` phần tử, tức `O(N)` cho bước lọc, bên cạnh thời gian database, mạng và ánh xạ. Truy vấn có điều kiện và index phù hợp có thể chuyển ít hàng hơn; tốc độ quét thực tế vẫn tùy cơ sở dữ liệu/kế hoạch truy vấn.
- **Bộ nhớ:** materialize danh sách lớn thường tốn bộ nhớ tỷ lệ với `N`; `@PostFilter` không hoàn tác chi phí tải dữ liệu ban đầu. Với ORM, persistence context còn có thể giữ tham chiếu tới các entity đã nạp.
- **Độ trễ và ổn định:** các đợt tải lớn làm tăng GC, thời gian phản hồi và nguy cơ `OutOfMemoryError` khi có nhiều request đồng thời.
- **N+1 và dữ liệu liên quan:** nếu điều kiện SpEL truy cập quan hệ lazy, mỗi lần kiểm tra có thể kích hoạt thêm truy vấn, khiến chi phí tăng mạnh.
- **Tác dụng phụ:** `@PostFilter` chỉ xử lý kết quả sau khi phương thức chạy; nó không ngăn mã ở trong phương thức ghi log nội dung nhạy cảm, đưa dữ liệu vào cache hoặc thực hiện tác dụng phụ trước khi lọc.

Không đánh đồng `Stream` với tối ưu hóa truy vấn. Spring Security hỗ trợ lọc stream còn mở, nhưng dùng stream không bảo đảm nguồn dữ liệu được giới hạn bởi chính sách ở database; việc đọc từng hàng vẫn có thể xảy ra và còn phụ thuộc thời gian sống của connection/transaction.

## 4. Lỗi đúng đắn thường gặp: phân trang rồi mới lọc

Giả sử database chọn `LIMIT 20 OFFSET 0` trên **tất cả** tài liệu, trong đó chỉ 3 tài liệu thuộc người dùng. Nếu ứng dụng lọc sau khi phân trang:

- Kết quả trang đầu có 3 phần tử dù thực tế còn nhiều tài liệu được phép ở trang tiếp theo.
- `totalElements` / `totalPages` được tính trên tập chưa áp dụng quyền sẽ sai với góc nhìn người dùng và có thể để lộ thông tin về quy mô dữ liệu.
- Trang có thể rỗng dù vẫn còn bản ghi người dùng được phép xem ở vị trí sau; cách sắp xếp và phân trang trở nên khó đoán.

**Thứ tự đúng:** xác định người dùng và tenant đáng tin cậy → đưa điều kiện quyền vào `WHERE`/chính sách truy vấn → `ORDER BY` ổn định → áp dụng `LIMIT/OFFSET` hoặc keyset pagination → trả về trang kèm tổng số bản ghi **đã được cấp quyền**. Với `Page<T>` của Spring Data, ưu tiên truy vấn repository có điều kiện thay vì trông chờ `@PostFilter` xử lý trang; annotation này được thiết kế cho mảng, collection, map và stream, không thay thế logic phân trang của `Page`.

## 5. Thiết kế tốt hơn: lọc tại tầng dữ liệu

Ví dụ này thuộc một ứng dụng Spring Boot có Spring Data JPA, Spring Security và entity `Document` chứa các trường `tenantId`, `ownerUsername`, `id`. Các đoạn dưới đây là **các lớp thành phần**, không phải một tệp Java độc lập; chúng cần entity, cấu hình database và bean `TenantContext` của ứng dụng.

Repository đưa ràng buộc vào truy vấn:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository extends JpaRepository<Document, Long> {
    Page<Document> findByTenantIdAndOwnerUsername(
        String tenantId, String ownerUsername, Pageable pageable);
}
```

Service lấy danh tính đã xác thực ở phía máy chủ, lấy tenant đã được kiểm tra quyền tham gia, rồi gọi repository với điều kiện rõ ràng:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository repository;
    private final TenantContext tenantContext;

    public DocumentService(
        DocumentRepository repository, TenantContext tenantContext) {
        this.repository = repository;
        this.tenantContext = tenantContext;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Page<Document> myDocuments(Pageable pageable) {
        String username = SecurityContextHolder.getContext()
            .getAuthentication().getName();
        String tenantId = tenantContext.requireTrustedTenantId();

        return repository.findByTenantIdAndOwnerUsername(
            tenantId, username, pageable);
    }
}
```

Ở đây, `TenantContext.requireTrustedTenantId()` **phải** xác nhận tenant bằng thông tin đã xác thực và quan hệ membership trên server, không chấp nhận tenant chỉ do client tự khai. Quy tắc `hasAuthority('document:read')` là cửa kiểm tra quyền gọi phương thức; điều kiện repository là ràng buộc quyền theo từng hàng. Cần duy trì cả hai nếu hệ thống có cả quyền thao tác và quyền truy cập dữ liệu.

Truy vấn SQL tương đương về mặt ý tưởng:

```sql
SELECT id, tenant_id, owner_username, title
FROM documents
WHERE tenant_id = :tenantId
  AND owner_username = :username
ORDER BY id ASC
LIMIT :pageSize OFFSET :offset;
```

Cú pháp phân trang thực tế do JPA dialect và database quyết định. Truy vấn đếm cho `Page` cũng phải dùng **cùng điều kiện quyền**. Với mẫu truy vấn này, có thể xem xét index:

```sql
CREATE INDEX idx_documents_tenant_owner_id
ON documents (tenant_id, owner_username, id);
```

Không thêm index chỉ theo cảm tính: dùng `EXPLAIN`/execution plan, phân bố dữ liệu, tần suất ghi và số liệu thực tế để quyết định. Với offset rất sâu, cân nhắc keyset pagination theo khóa sắp xếp ổn định và có index.

### Khi quyền phức tạp hơn quyền sở hữu

Nếu một tài liệu được chia sẻ qua ACL/nhóm, điều kiện có thể cần `EXISTS` hoặc `JOIN` đến bảng quyền. Ví dụ ý tưởng:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :tenantId
  AND (
    d.owner_username = :username
    OR EXISTS (
      SELECT 1
      FROM document_acl a
      WHERE a.document_id = d.id
        AND a.principal_name = :username
        AND a.can_read = TRUE
    )
  )
ORDER BY d.id
LIMIT :pageSize OFFSET :offset;
```

Cần tham số hóa, kiểm tra tenant cho ACL, thiết kế index và bảo đảm truy vấn `COUNT` phản ánh đúng tập được phép. Cơ chế Row-Level Security (RLS) của database có thể bổ sung một lớp bảo vệ khi được cấu hình đúng session, transaction và connection pool. Với dữ liệu đa tenant, **không chỉ lọc theo username** nếu username không bảo đảm phân tách tenant.

Trường hợp dữ liệu đến từ search engine, cache hoặc dịch vụ ngoài, phải đưa bộ lọc quyền vào chính hệ thống truy vấn đó (hoặc một cơ chế truy xuất đã giới hạn quyền); không lấy toàn bộ kết quả rồi mới bỏ phần tử trái phép để phục vụ phân trang.

## 6. Minh họa Java 17 chạy độc lập

Đoạn sau **không sử dụng Spring Security**; nó cho thấy vì sao lọc sau khi đã tải dữ liệu không tiết kiệm được công đọc ban đầu. Lưu với tên `FilteringDemo.java`:

```java
import java.util.List;

public class FilteringDemo {
    record Doc(int id, String owner) {}

    public static void main(String[] args) {
        List<Doc> loaded = List.of(
            new Doc(1, "alice"),
            new Doc(2, "bob"),
            new Doc(3, "charlie"),
            new Doc(4, "alice"),
            new Doc(5, "bob")
        );

        List<Doc> visible = loaded.stream()
            .filter(doc -> doc.owner().equals("alice"))
            .toList();

        System.out.println("Rows read: " + loaded.size());
        System.out.println("Rows visible: " + visible.size());
        System.out.println("IDs: " + visible.stream().map(Doc::id).toList());
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac FilteringDemo.java
java FilteringDemo
```

Kết quả chuẩn:

```text
Rows read: 5
Rows visible: 2
IDs: [1, 4]
```

Dù chỉ trả về 2 tài liệu, biến `loaded` đã chứa 5 tài liệu. Trong ứng dụng thực, `@PostFilter` cũng không thể xóa chi phí truy vấn đã hoàn thành.

## 7. Khi nào còn nên dùng `@PreFilter`/`@PostFilter`?

| Trường hợp | Hướng tiếp cận |
| --- | --- |
| Danh sách nhỏ, **bị giới hạn cứng**, đã sẵn trong bộ nhớ | `@PostFilter` có thể diễn đạt chính sách rõ ràng; đo chi phí thực tế |
| Dữ liệu lớn, cần tìm kiếm/phân trang/đếm/sắp xếp | Lọc ở database/search index trước khi phân trang |
| Phương thức nhận một tập input nhỏ từ caller | `@PreFilter` có thể lọc input; vẫn phải kiểm tra quyền với tài nguyên phía server khi xử lý |
| Truy cập một tài nguyên theo ID | Kiểm tra quyền trước khi thay đổi trạng thái; query theo ID + tenant + quyền, hoặc `@PreAuthorize` với logic kiểm tra đáng tin cậy |
| Dữ liệu đa tenant hoặc ACL phức tạp | Chính sách thống nhất ở tầng truy cập dữ liệu, cân nhắc RLS và kiểm thử đường đi qua các service |

`@PreFilter` không phải là giải pháp thay cho việc truy vấn có giới hạn: input collection đã tồn tại trước khi annotation lọc. Với tham số collection, cần kiểm tra khả năng thay đổi của collection và hành vi theo phiên bản Spring Security; không giả định một danh sách bất biến có thể bị lọc tại chỗ. Đừng nhầm `@PreFilter` (lọc từng phần tử đầu vào) với `@PreAuthorize` (quyết định có cho gọi phương thức hay không).

`@PostFilter` vẫn có giá trị như một quy tắc bảo vệ thêm cho kết quả nhỏ, nhưng khi quyền quyết định những hàng được đọc, **ràng buộc từ sớm ở truy vấn mới là biện pháp chủ đạo**. Cần cẩn thận với self-invocation, lazy loading, transaction, kết quả null, loại tập hợp, và logic nhiều tenant.

## 8. Kiểm thử đúng đắn, phân quyền và hiệu năng

Nên kiểm thử ít nhất các tình huống sau:

1. **Phân quyền:** người dùng A chỉ thấy dữ liệu A; người dùng B không truy cập được dữ liệu A qua danh sách, ID trực tiếp, thao tác xuất file hay các endpoint khác.
2. **Cô lập tenant:** hai tenant có cùng username hoặc ID giống nhau vẫn không đọc chéo tài liệu; tenant client gửi lên không tự quyết định phạm vi truy cập.
3. **Phân trang:** trang đủ `pageSize` khi còn đủ dữ liệu hợp lệ; `totalElements` và `totalPages` phản ánh đúng tập đã cấp quyền; thứ tự ổn định giữa các trang.
4. **Trường hợp biên:** kết quả rỗng, quyền bị thu hồi, quyền nhóm/ACL, bản ghi không có owner, dữ liệu thay đổi trong lúc phân trang.
5. **Cấu trúc truy vấn:** dùng integration test/SQL log có kiểm soát để xác nhận `WHERE` và `COUNT` đều bao gồm owner, tenant và điều kiện ACL cần thiết. Không chỉ test rằng response đã được cắt bớt.
6. **Tải lớn:** đo số hàng thực tế trả từ database, số truy vấn (đặc biệt N+1), p95/p99 latency, sử dụng heap/GC và thông lượng khi nhiều request chạy đồng thời.

Ví dụ một bộ dữ liệu có 100 tài liệu, trong đó 10 thuộc `alice`, yêu cầu trang đầu `size=5` phải trả **5 tài liệu của alice** (nếu query được sắp xếp và dữ liệu không đổi), tổng hợp lệ là **10**, không phải 100. Đó là một phép thử cụ thể bắt lỗi "phân trang trước, lọc sau".

Có thể thêm quy tắc tránh truy vấn vô hạn: giới hạn `pageSize`, timeout truy vấn, giới hạn xuất dữ liệu theo lô có kiểm tra quyền, tránh chuyển `Page` thành `List` toàn bộ, và dùng DTO/projection nếu chỉ cần một số trường. Các biện pháp này giảm tải nhưng **không thay thế** điều kiện phân quyền ở nguồn.

## 9. Lỗi phổ biến và cách tự kiểm tra

- **"Có `@PostFilter` nên `findAll()` vẫn an toàn và hiệu quả."** Kết quả trả ra có thể được lọc, nhưng ứng dụng đã tải mọi hàng và chịu chi phí trước khi lọc.
- **"Đặt `LIMIT` trước rồi `@PostFilter` là đã phân trang."** Làm vậy dễ sinh trang thiếu/rỗng và metadata đếm sai; phải lọc theo quyền trước phân trang.
- **"Gửi `ownerUsername` từ request vào query là đủ."** Caller có thể giả mạo; identity và tenant phải lấy từ nguồn đã xác thực/được kiểm tra trên server.
- **"`@PreAuthorize` thay thế được điều kiện owner/tenant."** Một quyền chung như `document:read` chỉ nói được phép đọc loại tài nguyên; còn phải kiểm tra **hàng nào** được đọc.
- **"`Stream`, cache hoặc batch tự động xử lý được vấn đề."** Chúng có thể thay đổi cách tải, nhưng không tự đưa chính sách quyền vào truy vấn và không tự làm đúng total count.
- **"Test output không có dữ liệu của B là đủ."** Cần kiểm tra SQL, tổng phân trang, cache/log/side effect, tenant và đường gọi qua proxy.

**Quy tắc ra quyết định:** nếu số hàng phải đọc trước khi lọc có thể tăng theo kích thước toàn bảng, hoặc kết quả phải phân trang/đếm theo quyền, hãy ưu tiên truy vấn đã ràng buộc quyền tại tầng dữ liệu. Chỉ dùng lọc trong bộ nhớ khi tập đầu vào nhỏ, giới hạn rõ ràng, và việc đó đã được đo/kiểm thử.

## Tài liệu tham khảo

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): mô tả `@PreFilter`/`@PostFilter`, cấu hình `@EnableMethodSecurity` và cảnh báo chi phí lọc trong bộ nhớ.
- [Spring Data JPA — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): các cách tạo truy vấn repository có điều kiện.
