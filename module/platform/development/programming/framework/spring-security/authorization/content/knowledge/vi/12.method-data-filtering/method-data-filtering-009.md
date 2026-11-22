# Lọc tại truy vấn so với @PostFilter: chọn lớp thực thi phù hợp

## 1. Mục tiêu: đặt kiểm soát truy cập vào đúng lớp

Khi một phương thức trả về danh sách bản ghi, có hai câu hỏi liên quan nhưng khác nhau:

1. **Người gọi có được thực hiện thao tác không?** Ví dụ: có quyền mở trang liệt kê tài liệu hay không.
2. **Trong các bản ghi có thể tìm thấy, bản ghi nào người gọi được phép xem?** Ví dụ: chỉ dữ liệu thuộc tenant hiện tại, tài liệu do mình sở hữu hoặc được chia sẻ hợp lệ.

Trong Spring Security, `@PreAuthorize` thường giải quyết câu hỏi thứ nhất. Câu hỏi thứ hai có thể giải quyết ở **truy vấn dữ liệu** (SQL/JPQL/Criteria/Specification, ACL join, database Row-Level Security) hoặc tại **ranh giới trả về của method** bằng `@PostFilter`. Hai cách không có cùng chi phí, thời điểm thực thi hay ý nghĩa phân trang.

**Quy tắc lựa chọn:** Với dữ liệu lưu trữ lớn, truy vấn tìm kiếm, phân trang, đếm, đa tenant hoặc danh sách có thể tăng không giới hạn, lọc quyền ngay tại truy vấn. `@PostFilter` phù hợp khi tập đối tượng đầu vào đã **nhỏ, hữu hạn, nằm trong bộ nhớ**, cần lọc theo từng phần tử ở ranh giới method và không cần metadata phân trang chính xác từ nguồn.

Dù chọn cách nào, **chính sách quyền phải được thực thi trước khi dữ liệu được đưa ra cho người dùng**. Việc chọn tầng kiểm tra chỉ quyết định nơi thực hiện và cách chứng minh tính đúng.

## 2. Các tầng thực thi và thời điểm dữ liệu bị loại

~~~text
HTTP request
  │
  ▼
SecurityFilterChain: xác thực, quy tắc URL
  │
  ▼
Service qua Spring proxy: @PreAuthorize (quyền gọi thao tác)
  │
  ▼
Repository/Query: WHERE tenant + trạng thái + chủ sở hữu/ACL
  │                    │
  │                    └─ ORDER BY → LIMIT/OFFSET/cursor → COUNT theo cùng scope
  ▼
Kết quả service
  │
  ├─ Khi có @PostFilter: xét từng phần tử của kiểu trả về được hỗ trợ
  │
  ▼
Controller / serializer / client
~~~

`@PostFilter` được đánh giá **sau khi phương thức hoàn tất**. Nó không đẩy biểu thức Spring EL xuống database, không biến `repository.findAll()` thành truy vấn có `WHERE`, cũng không tự khôi phục dữ liệu hợp lệ đã bị `LIMIT` cắt ở trước đó.

Cần phân biệt các công cụ:

| Công cụ | Thời điểm | Nhiệm vụ đúng | Không tự làm được |
|---|---|---|---|
| `@PreAuthorize` | Trước khi gọi method | Cho phép/từ chối thao tác, có thể tham chiếu tham số và principal | Không tự thêm bộ lọc từng hàng vào repository |
| Predicate của query / ACL / RLS | Trong quá trình đọc dữ liệu | Giới hạn bản ghi từ nguồn, đồng nhất content và count | Không tự thay thế toàn bộ kiểm tra quyền thực thi thao tác |
| `@PostFilter` | Sau method, trước caller | Xóa phần tử không đạt biểu thức khỏi một kết quả có cấu trúc được hỗ trợ | Không giảm lượng bản ghi đã truy vấn; không tính lại phân trang của nguồn |
| `@PostAuthorize` | Sau method | Chấp nhận/từ chối **cả kết quả** dựa trên `returnObject` | Không lọc một danh sách thành các phần tử hợp lệ |
| DTO/projection | Trước khi trả response | Giới hạn trường thông tin được công bố | Không thay thế việc kiểm tra bản ghi nào được xem |

Cũng đừng nhầm `@PreFilter` với lọc trong query: `@PreFilter` lọc **tham số collection/array/map/stream trước khi method chạy**, không tự chuyển thành điều kiện SQL.

## 3. Cơ chế @PostFilter và giới hạn cần nhớ

Bật method security trong cấu hình Spring:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Sau đó một service bean có thể khai báo:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.stereotype.Service;

@Service
public class PreviewService {
    private final PreviewSource previewSource;

    public PreviewService(PreviewSource previewSource) {
        this.previewSource = previewSource;
    }

    @PostFilter("filterObject.ownerUsername == authentication.name")
    public List<DocumentPreview> preview() {
        return new ArrayList<>(previewSource.loadAtMost(40));
    }
}
~~~

Đây là **mã tích hợp Spring**; `PreviewSource` và `DocumentPreview` là các thành phần ứng dụng cần có, không phải chương trình độc lập để biên dịch bằng một lệnh `javac`. Ví dụ giả định chính sách chỉ cho xem đối tượng do username hiện tại sở hữu. Nếu chính sách còn yêu cầu tenant, nhóm hoặc ACL, biểu thức hoặc lớp bảo vệ tương ứng phải kiểm tra đầy đủ các điều kiện đó.

Điểm chính:

- `filterObject` là phần tử đang được xét; với `Map`, nó đại diện cho `Map.Entry`, do đó muốn đọc thuộc tính của value thường viết `filterObject.value.ownerUsername`.
- Theo tài liệu Spring Security, hậu lọc được thiết kế cho **collection, array, map và stream còn mở**. Đừng coi mọi loại wrapper, đặc biệt `Page<T>` và `Optional<T>`, là collection được hỗ trợ. Cần kiểm tra chính xác kiểu trả về và phiên bản trước khi dùng.
- Với kết quả collection, quá trình lọc có thể thay đổi collection được trả về; ví dụ dùng `new ArrayList<>(...)` để tách khỏi nguồn shared/cache. Tránh trả thẳng collection bất biến hoặc đối tượng mutable được dùng chung khi chưa kiểm tra hành vi filter.
- Biểu thức được đánh giá cho từng phần tử. Một phép kiểm tra quyền gọi database/API cho mỗi phần tử tạo nguy cơ **N+1** và thời gian tăng theo kích thước kết quả.
- Method security thường chạy qua Spring AOP proxy. Tự gọi `this.preview()` trong cùng bean không đi qua proxy, nên annotation có thể bị bỏ qua. Phải kiểm thử qua bean Spring thực tế.
- `@EnableMethodSecurity` cần được bật trong ứng dụng; thêm Spring Security dependency không có nghĩa method security được tự kích hoạt.

Có thể dùng `@PostFilter("hasPermission(filterObject, 'read')")` khi đã cấu hình mô hình quyền phù hợp, chẳng hạn `PermissionEvaluator`. Tuy nhiên, biểu thức không tự tạo truy vấn ACL hiệu quả; nếu mỗi lần `hasPermission` lại truy cập DB, cần giới hạn tập và xét batch/pushdown.

## 4. Bảng quyết định: chọn lớp nào?

| Tình huống | Lớp nên chịu trách nhiệm lọc chính | Giải thích |
|---|---|---|
| API list/search từ bảng hàng nghìn đến hàng triệu dòng | Query/repository | Không tải bản ghi bị từ chối, có thể index và phân trang đúng |
| Có `Pageable`, `Page<T>`, `Slice<T>`, cursor hoặc COUNT | Query/repository | Dữ liệu và metadata phải xuất phát từ cùng tập đã phân quyền |
| Dữ liệu nhiều tenant, cần cách ly cứng | Query có tenant predicate; cân nhắc RLS ở DB | Ngăn đọc chéo tenant từ nguồn, áp dụng cho nhiều đường truy cập |
| Quyền theo chủ sở hữu, nhóm, bảng share, ACL có thể biểu diễn bằng JOIN/EXISTS | Query/ACL-aware repository | Đếm đúng, tránh một lần kiểm tra riêng cho từng object |
| Danh sách vài chục object đã được tải hợp lệ, không phân trang | `@PostFilter` có thể phù hợp | Biểu thức dễ hiểu, dữ liệu đã giới hạn trước khi kiểm tra |
| Danh sách tổng hợp từ nhiều nguồn ngoài DB, dữ liệu nhỏ đã được chuẩn hóa | Filter trong service; `@PostFilter` nếu rõ kiểu trả về và lifecycle | Không phải nguồn nào cũng hỗ trợ predicate; vẫn phải giới hạn số object và tránh lộ dữ liệu trung gian |
| Đọc **một** tài liệu theo ID | Query theo ID + scope; `@PreAuthorize`/`@PostAuthorize` khi thích hợp | Một object không phải tập phần tử để dùng `@PostFilter` |
| Chỉ muốn ẩn một số field nhạy cảm trong object | DTO/projection hoặc field-level policy | `@PostFilter` lọc **phần tử**, không xóa thuộc tính bên trong |
| Policy phụ thuộc kết quả tính toán không thể đẩy xuống query | Service/domain authorization; có thể hậu kiểm tập nhỏ | Cần mô hình rõ về phân trang, chi phí và xử lý trường hợp từ chối |
| Policy chung cho nhiều client/worker/truy vấn trực tiếp DB | Kiểm soát tại data layer, có thể kết hợp RLS | Bảo vệ được cả các đường đọc không đi qua một service cụ thể |

**Một câu hỏi kiểm tra hữu ích:** Nếu bỏ bước `@PostFilter`, query hiện tại có đang đọc hàng nghìn bản ghi mà người dùng không có quyền xem không? Nếu có, thông thường nên sửa thiết kế ở tầng dữ liệu thay vì chỉ tăng khả năng hậu lọc.

## 5. Ví dụ 1 — Query-first cho API phân trang

Giả sử có entity JPA `Document` với các thuộc tính `id`, `tenantId`, `ownerUsername`, `deleted`. Chính sách ví dụ: người dùng chỉ thấy tài liệu của chính mình trong tenant hiện tại và chưa bị xóa.

Repository thực hiện phân quyền **trong cả truy vấn nội dung lẫn COUNT**:

~~~java
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentRepository extends JpaRepository<Document, Long> {

    @Query(
        value = """
            select d from Document d
            where d.tenantId = :tenantId
              and d.ownerUsername = :username
              and d.deleted = false
            """,
        countQuery = """
            select count(d) from Document d
            where d.tenantId = :tenantId
              and d.ownerUsername = :username
              and d.deleted = false
            """
    )
    Page<Document> findVisible(
        @Param("tenantId") UUID tenantId,
        @Param("username") String username,
        Pageable pageable
    );
}
~~~

Service chỉ chuyển **scope đã xác thực** xuống repository:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentQueryService {
    private final DocumentRepository repository;
    private final CurrentAccessScope accessScope;

    public DocumentQueryService(
        DocumentRepository repository,
        CurrentAccessScope accessScope
    ) {
        this.repository = repository;
        this.accessScope = accessScope;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Page<Document> findMine(Pageable pageable) {
        return repository.findVisible(
            accessScope.requiredTenantId(),
            accessScope.requiredUsername(),
            pageable
        );
    }
}
~~~

Các đoạn trên là mã minh họa cho dự án Spring Data JPA đã có entity `Document` và bean ứng dụng `CurrentAccessScope`. Bean scope này phải lấy thông tin từ principal/token đã **xác minh**, từ chối nếu thiếu principal hoặc tenant, không chấp nhận tenant/user tùy ý từ HTTP query parameter. `@PreAuthorize` kiểm tra quyền thực thi thao tác; query kiểm tra quyền **từng hàng**.

Khi policy còn bao gồm shared document, cần mở rộng predicate theo đúng quyền: ví dụ `owner = currentUser OR EXISTS(permission cho currentUser)` trong **cả SELECT và COUNT**. Với join một-nhiều, kiểm tra duplicate và cách dùng `DISTINCT/COUNT(DISTINCT ...)`. Không đưa logic khó hiểu vào SpEL nếu việc JOIN/EXISTS trong database giải quyết hiệu quả hơn.

Nếu điều kiện nghiệp vụ thay đổi theo filter của client, xây một hàm tạo predicate dùng chung cho điều kiện nghiệp vụ + quyền, rồi áp dụng nhất quán cho câu truy vấn nội dung và đếm. Với Spring Data JPA, có thể dùng `Specification`/Criteria/Querydsl khi chính sách động; kiểm tra phiên bản thực tế khi dùng API countSpec riêng.

**Điều kiện để kết quả đáng tin:** `WHERE` theo quyền, `ORDER BY` ổn định (nên thêm khóa duy nhất), phân trang và COUNT phải cùng hiểu một tập dữ liệu. Chỉ dùng `Page` khi thực sự cần tổng; `Slice` hoặc keyset/cursor phù hợp khi giao diện chỉ cần tải tiếp.

## 6. Ví dụ 2 — @PostFilter cho tập nhỏ được giới hạn

Giả sử một phương thức cần trả tối đa 40 bản xem trước đã lấy vào bộ nhớ và không công bố total/page. Khi nguồn không có cách lọc theo chủ sở hữu hiệu quả hoặc danh sách được tổng hợp từ nhiều nguồn, hậu lọc tại ranh giới service có thể đủ rõ ràng.

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.stereotype.Service;

@Service
public class SmallPreviewService {
    private final PreviewSource source;

    public SmallPreviewService(PreviewSource source) {
        this.source = source;
    }

    @PreAuthorize("hasAuthority('document:read')")
    @PostFilter("filterObject.ownerUsername == authentication.name")
    public List<DocumentPreview> previewForCurrentUser() {
        return new ArrayList<>(source.loadAtMost(40));
    }
}
~~~

Ở ví dụ này, `loadAtMost(40)` là **hợp đồng thực sự của nguồn**: nó phải bảo đảm lượng dữ liệu tối đa; không được chỉ đặt tên phương thức như vậy nhưng vẫn tải toàn bảng. Nếu các phần tử trong cache hoặc nguồn chia sẻ có dữ liệu nhạy cảm, cần bảo vệ đường đọc/trung gian (logs, trace, cache keys, lifecycle), chứ không chỉ dựa vào việc xóa trước controller.

Giả sử nguồn có dữ liệu `[(A, "an"), (B, "binh"), (C, "an")]`, người dùng `an` nhận `[A, C]`. Kết quả là một **danh sách đã lọc**, không phải một `Page` có thông số chính xác. Nếu UI yêu cầu “trả đủ 20 phần tử được phép xem” nhưng nguồn chỉ tải 20 phần tử thô, `@PostFilter` không tự tìm thêm phần tử hợp lệ ở các batch sau.

Có thể dùng `@PostFilter` như lớp kiểm tra bổ sung sau query-first khi tập đã nhỏ, nhưng phải cân nhắc chi phí và việc có thể lặp chính sách. Nếu policy ở query và policy ở annotation khác nhau, một trong hai có thể thiếu quyền hoặc loại bỏ nhầm dữ liệu. Nên có đặc tả chính sách chung và test đối chiếu.

## 7. Chọn vị trí xử lý trong từng ranh giới hệ thống

### Controller và Spring Security filter chain

Controller nhận input, validate bộ lọc nghiệp vụ và gọi service. Spring Security ở HTTP layer kiểm tra xác thực/quyền URL. Không nên viết `stream().filter(...permission...)` trong controller làm lớp phân quyền dữ liệu chính, vì service có thể được gọi từ job, message consumer hoặc endpoint khác.

### Service và method security

Service thể hiện **use case** và ranh giới được bảo vệ: ai được gọi thao tác, policy nào cần áp dụng, thứ tự các bước. `@PreAuthorize` thường thuận tiện để chặn thao tác trước khi đọc DB. Đối với tải theo ID, có thể dùng query giới hạn `WHERE id=:id AND tenant=:tenant AND ...`; `@PostAuthorize` phù hợp khi yêu cầu kiểm tra toàn bộ một kết quả sau method, nhưng nhớ rằng dữ liệu đã được truy xuất trước thời điểm đó.

### Repository, search engine, remote data source

Repository nên nhận một scope quyền đã chuẩn hóa và chuyển thành điều kiện lọc thực thi ngay tại dữ liệu. Tương đương với Elasticsearch hoặc remote service có filtering API: gửi filter quyền như một phần query nếu nguồn tin cậy thực thi đúng. Tuy nhiên, một tham số do client tùy ý gửi **không** đại diện cho quyền. Nếu nguồn không thể bảo đảm phân quyền, service phải hậu kiểm đầy đủ và lựa chọn cách phân trang/đếm phù hợp, hoặc từ chối kiểu API đòi hỏi kết quả chính xác mà nguồn không đáp ứng được.

### Database Row-Level Security

RLS có thể là lớp bảo vệ bổ sung khi nhiều đường code cùng đọc một bảng. Tuy nhiên, session/connection phải nhận được danh tính và tenant đúng, nhất là khi dùng pool; test cả dữ liệu, COUNT và quá trình reset khi tái sử dụng connection. RLS không tự thay thế kiểm tra quyền gọi use case, truy cập trường nhạy cảm hay authorization ở các hệ thống ngoài DB.

## 8. Quyền phức tạp: không đưa N+1 xuống từng phần tử

Chính sách thường vượt xa điều kiện `owner == username`:

- Người dùng được xem tài liệu thuộc nhóm mà họ đang là thành viên.
- Người dùng có quyền thông qua bảng chia sẻ.
- Quản trị viên có quyền xem trong tenant nhưng không có quyền xuyên tenant.
- Tài liệu ở trạng thái nhạy cảm cần thêm permission riêng.

Với danh sách lớn, một biểu thức `@PostFilter("hasPermission(filterObject, 'read')")` có thể phát sinh nhiều phép kiểm tra ACL độc lập, thậm chí một truy vấn cho mỗi đối tượng. Khi quyền có thể được biểu diễn ở DB, dùng predicate `EXISTS`/JOIN kết hợp scope để database xét tập một lần, có index và COUNT nhất quán. Nếu policy phụ thuộc dịch vụ phân quyền từ xa, cân nhắc lấy quyết định hàng loạt (batch authorization) rồi giới hạn candidate set; đưa ra giới hạn tải và cách báo lỗi rõ ràng.

**Tránh bất đồng chính sách:** cùng một quyền “read document” không nên có ý nghĩa khác nhau giữa API list và API detail. Viết test dùng chung các tình huống cho predicate của query, decision của service và khả năng truy cập chi tiết từng ID. Nếu không thể bảo đảm hai tầng có chính sách giống nhau, phải làm rõ tầng nào là nơi thực thi chính và tầng nào chỉ phòng thủ bổ sung.

## 9. Những điều @PostFilter không giải quyết

### Không sửa được metadata phân trang

Giả sử database lấy một trang 5 bản ghi thô, chỉ 2 bản ghi được phép xem. Hậu lọc sẽ để lại 2 bản ghi, không thể kéo bản ghi hợp lệ tiếp theo từ database để làm đầy trang; `COUNT` gốc cũng có thể bao gồm dữ liệu không được phép xem. Nếu cần `Page<T>`, phải áp dụng quyền trong query content và COUNT. Không lấy `filteredPage.size()` làm `totalElements` của toàn bộ dataset.

### Không bảo đảm field-level authorization

Một `Document` có thể được xem nhưng chứa trường `secretToken` hoặc thông tin nội bộ không được công bố. `@PostFilter` chỉ quyết định giữ hay loại **cả phần tử**. Hãy dùng DTO/projection và kiểm soát serialize phù hợp với từng use case.

### Không kiểm soát các side effect trước khi trả kết quả

Trước khi `@PostFilter` chạy, method đã có thể truy vấn database, ghi log, đưa dữ liệu vào cache hoặc gọi hệ thống khác. Vì thế phải hạn chế truy cập sớm nhất khả thi, bảo vệ log/caching và không coi hậu lọc là biện pháp duy nhất trong mọi trường hợp.

### Không tự giải quyết consistency hoặc race condition

Nếu quyền của một object thay đổi giữa truy vấn và serialization, cần quy định consistency/transaction boundary phù hợp với nghiệp vụ và mức độ nhạy cảm. Mọi lần gọi endpoint/detail sau đó vẫn phải kiểm tra quyền theo trạng thái hiện hành. Cache theo tenant/user/scope và invalidation theo thay đổi quyền nếu dữ liệu cá nhân hóa.

### Không phù hợp mặc định với mọi kiểu kết quả

`Page<T>`, `Optional<T>` hoặc wrapper tự tạo không phải các kiểu supported mặc định mà tài liệu mô tả cho `@PostFilter`. Không gắn annotation theo suy đoán rồi cho rằng metadata sẽ được sửa; dùng query filtering, `@PostAuthorize` hoặc service guard phù hợp với kiểu kết quả.

## 10. Demo Java 17 độc lập: cùng một policy, hai thời điểm

Ví dụ mô phỏng việc lấy trang đầu trước và sau khi áp dụng quyền. Nó dùng Java Stream trong bộ nhớ để minh họa **thứ tự thao tác**, không mô phỏng SQL optimizer hoặc chi phí thực tế của database.

Tệp `FilteringLayerDemo.java`:

~~~java
import java.util.List;

public class FilteringLayerDemo {
    record Doc(int id, String tenant, String owner) { }

    private static boolean canRead(Doc doc) {
        return doc.tenant().equals("north")
                && doc.owner().equals("an");
    }

    public static void main(String[] args) {
        List<Doc> database = List.of(
                new Doc(1, "north", "binh"),
                new Doc(2, "north", "an"),
                new Doc(3, "south", "an"),
                new Doc(4, "north", "binh"),
                new Doc(5, "north", "an"),
                new Doc(6, "north", "an")
        );
        int size = 2;

        List<Integer> queryFirst = database.stream()
                .filter(FilteringLayerDemo::canRead)
                .limit(size)
                .map(Doc::id)
                .toList();

        List<Integer> postFilter = database.stream()
                .limit(size)
                .filter(FilteringLayerDemo::canRead)
                .map(Doc::id)
                .toList();

        long visibleTotal = database.stream()
                .filter(FilteringLayerDemo::canRead)
                .count();

        System.out.println("Query-first page: " + queryFirst);
        System.out.println("Post-filtered page: " + postFilter);
        System.out.println("Authorized total: " + visibleTotal);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac FilteringLayerDemo.java
java FilteringLayerDemo
~~~

Stdout chính xác:

~~~text
Query-first page: [2, 5]
Post-filtered page: [2]
Authorized total: 3
~~~

Ở đây dữ liệu người `an` thuộc tenant `north` có ba tài liệu: ID 2, 5, 6. Nếu áp dụng policy trước khi lấy tối đa hai phần tử, trang đầu đúng là `[2,5]`. Nếu chỉ lấy hai phần tử thô rồi lọc, còn `[2]`. Với preview không phân trang và chỉ vài object, cách lọc sau có thể hợp lý; với danh sách phân trang, ví dụ cho thấy vì sao phải chọn query-first.

## 11. Kiểm thử lựa chọn tầng thực thi

Một bộ test có ý nghĩa cần kiểm tra **hành vi quyền trên dữ liệu thật**, không chỉ kiểm tra annotation có mặt:

1. **Query-first:** với hai tenant, hai người dùng và các record chia sẻ, kiểm tra danh sách + COUNT + `Page`/`Slice` chỉ phản ánh bản ghi được phép xem; thử trang rỗng, trang cuối, sắp xếp bằng khóa phụ duy nhất.
2. **Method security:** test qua Spring bean/proxy với principal có và không có authority; gọi trực tiếp nội bộ bean để phát hiện tình huống bypass proxy; thử `@PostFilter` với danh sách vừa có phần tử hợp lệ vừa không hợp lệ.
3. **Kiểu và nguồn trả về:** test collection mutable, map (`filterObject.value`), stream còn mở nếu thực sự dùng; xác nhận không sửa shared cache/list và không giả định `Page` được hỗ trợ.
4. **ACL phức tạp:** owner, shared, member, admin theo tenant, revoked permission; cả query danh sách và truy xuất theo ID phải nhất quán. Dùng dữ liệu có nhiều permission record trỏ về một document để phát hiện duplicate/COUNT sai.
5. **Hiệu năng:** theo dõi số row đọc, query count, N+1 của permission evaluator và thời gian truy vấn theo tập dữ liệu tăng; test trường hợp 100% record bị từ chối mà client vẫn yêu cầu trang đầu.
6. **An toàn:** không rò rỉ nội dung lẫn tổng số ngoài quyền, không dùng tenant client đưa vào làm scope, không lộ field nhạy cảm, cache không chia sẻ dữ liệu cá nhân hóa giữa người dùng.

Nếu quyền được thi hành cả trong query lẫn `@PostFilter`, nên có test đối chiếu cùng bộ ca chính sách để tránh tình huống “query cho qua nhưng annotation loại” hoặc “annotation cho qua khi một đường truy cập bỏ quên query filter”.

## 12. Những lựa chọn sai và cách sửa

**Gắn `@PostFilter` lên service trả `Page<Document>` vì nghĩ annotation sẽ lọc cả total.** Cách này dựa trên một kiểu trả về không thuộc các kiểu collection hậu lọc được tài liệu mô tả và không giải quyết count/pagination. **Sửa:** đưa predicate quyền vào query trả `Page` và query COUNT.

**Dùng `repository.findAll()` rồi `@PostFilter` cho bảng lớn.** Tải quá nhiều dữ liệu không cần thiết, tăng bộ nhớ, CPU và nguy cơ lộ dữ liệu trung gian. **Sửa:** repository lọc theo scope; chỉ hậu lọc tập thật nhỏ khi cần.

**Dùng `@PreAuthorize("hasRole('USER')")` và cho rằng mọi row đã an toàn.** Annotation cho phép gọi method, không tự giới hạn từng row. **Sửa:** thêm điều kiện quyền theo object tại nguồn.

**Để controller tự ghép điều kiện tenant do client cung cấp.** Người dùng có thể đổi tenant trong request. **Sửa:** dựng scope từ authentication/identity đã kiểm chứng và kiểm tra scope mọi đường đọc.

**Dùng cùng một mutable list được cache làm giá trị trả về của `@PostFilter`.** Lọc collection có thể thay đổi list dùng chung, khiến kết quả của request sau sai. **Sửa:** tách collection riêng, ưu tiên immutable DTO sau lọc và thiết kế cache theo scope.

**Lọc từng phần tử bằng `hasPermission` nhưng không đo số truy vấn.** Với danh sách lớn, N+1 gây chậm và làm load tăng theo lượng data. **Sửa:** đẩy ACL xuống predicate query hoặc batch quyết định quyền.

**Chỉ lọc list mà quên API detail hoặc nested field.** Có thể bị truy cập trực tiếp bằng ID hoặc lộ dữ liệu qua serialization. **Sửa:** bảo vệ cả query theo ID và projection/field policy.

## 13. Checklist chọn lớp thực thi

Trước khi chốt thiết kế, trả lời đủ các câu sau:

- Kích thước tập kết quả có thể tăng không giới hạn, có phân trang, tổng bản ghi hoặc cursor không? **Có → ưu tiên query-first.**
- Điều kiện quyền có thể biểu diễn bằng owner/tenant/group/ACL trong query không? **Có → đẩy xuống data layer và kiểm tra COUNT cùng predicate.**
- Tập đã nhỏ, hữu hạn, không có metadata phân trang và cần hậu kiểm từng object ở ranh giới method không? **Có → cân nhắc `@PostFilter`.**
- Đang kiểm soát quyền gọi use case hay quyền trên từng bản ghi? **Quyền gọi → `@PreAuthorize`; quyền từng bản ghi → predicate hoặc hậu lọc phù hợp.**
- Có một object đơn lẻ hoặc các field cần che không? **Dùng object-level authorization và DTO/projection**, không dùng `@PostFilter` để thay thế.
- Principal/tenant có được lấy từ nguồn tin cậy, có test nhiều người dùng/tenant, proxy method security và hiệu năng không? **Phải có.**

**Kết luận thực hành:** Chọn query filtering làm lớp thực thi quyền chính khi phải tìm kiếm, đếm hoặc phân trang dữ liệu lưu trữ. Dùng `@PostFilter` có chủ đích cho một tập kết quả nhỏ, đã giới hạn, tại ranh giới method. Kết hợp `@PreAuthorize` để chặn thao tác không được phép và kiểm tra các đường truy cập khác bằng cùng chính sách.

## Tham khảo

- [Spring Security Reference – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostFilter`, `filterObject`, kiểu kết quả và chi phí in-memory.
- [Spring Data JPA Reference – Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html): xây dựng predicate truy vấn có thể kết hợp.
- [Spring Data JPA Reference – Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): `Page`, `Slice`, COUNT và ý nghĩa pagination.
