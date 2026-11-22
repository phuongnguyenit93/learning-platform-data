# Phân trang, tổng số bản ghi và sai lệch khi lọc sau truy vấn

## 1. Vì sao phân trang và lọc quyền phải đi cùng nhau?

Trong Spring Security, method security có thể kiểm tra quyền gọi phương thức bằng `@PreAuthorize`, hoặc hậu lọc từng phần tử trong kết quả bằng `@PostFilter`. Tuy nhiên, nếu repository đã áp dụng `LIMIT/OFFSET` rồi code mới loại bỏ các bản ghi không được phép xem, trang trả về không còn biểu diễn đúng tập dữ liệu mà người dùng được quyền truy cập.

Phân biệt hai trình tự:

- **Đúng:** lọc theo điều kiện nghiệp vụ **và quyền truy cập** trong truy vấn, sắp xếp ổn định, rồi phân trang; tính COUNT trên cùng tập đã được phân quyền.
- **Có vấn đề:** lấy một trang từ dữ liệu chưa lọc quyền, sau đó xóa những phần tử không được phép xem; giữ nguyên total/count/hasNext của truy vấn ban đầu.

Với API phân trang, nguồn chân lý của `content`, `totalElements`, `totalPages` và `hasNext` phải là **cùng tập dữ liệu được phép xem**.

## 2. Ví dụ trực quan

Giả sử dữ liệu có 12 bản ghi ID từ 1 đến 12. Người dùng A chỉ có quyền xem ID chẵn: `[2,4,6,8,10,12]`. Client yêu cầu trang 0, kích thước 5.

| Chỉ số | Phân trang trước rồi lọc quyền | Lọc quyền trước rồi phân trang |
|---|---|---|
| Trang 0 | `[2,4]` | `[2,4,6,8,10]` |
| Trang 1 | `[6,8,10]` | `[12]` |
| Trang 2 | `[12]` | Không có |
| Tổng bản ghi nếu giữ metadata query gốc | 12 (**sai với người dùng A**) | 6 |
| Tổng số trang | 3 (**sai**) | 2 |

Truy vấn thô của trang đầu có thể trả `[1,2,3,4,5]`. Sau `@PostFilter`, chỉ còn `[2,4]`; mặc dù chưa hết bản ghi hợp lệ, trang bị thiếu ba phần tử. Từ `content.size() < size` không thể kết luận đây là trang cuối khi quyền được lọc **sau** truy vấn.

Tương tự, `totalElements=12` có thể tiết lộ số lượng bản ghi ngoài phạm vi truy cập. Không thể sửa bằng `totalElements=content.size()`, bởi đó chỉ là số phần tử hợp lệ trong một trang thô, không phải số phần tử hợp lệ trong toàn bộ dataset.

## 3. Cơ chế và giới hạn của `@PostFilter`

`@PostFilter` đánh giá biểu thức trên các phần tử của kết quả phương thức sau khi phương thức đã thực thi. Nó không tự thêm `WHERE` vào SQL, cũng không khiến database tính lại `COUNT` theo quyền. Vì thế, nó phù hợp hơn với các tập hữu hạn nhỏ đã có trong bộ nhớ, thay vì dùng làm cơ chế chính cho endpoint phân trang.

Ví dụ minh họa hậu lọc một danh sách:

~~~java
@Service
class DocumentService {
    private final DocumentRepository repository;

    DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PostFilter("filterObject.ownerUsername == authentication.name")
    public List<Document> listCandidates() {
        return repository.findAll();
    }
}
~~~

Đoạn trên chỉ là thành phần Spring, phụ thuộc vào các lớp `Document` và `DocumentRepository` của ứng dụng; không phải chương trình Java độc lập. Annotation cần method security được bật, chẳng hạn `@EnableMethodSecurity`. Với Spring AOP dùng proxy, việc gọi nội bộ như `this.listCandidates()` thường không đi qua interceptor, nên không được dựa vào annotation trong đường gọi đó.

Đừng giả định `@PostFilter` tự hỗ trợ mọi wrapper như `Page<Document>` hoặc tự điều chỉnh `Page.getTotalElements()`. Phải kiểm tra đúng kiểu trả về được hỗ trợ trong phiên bản Spring Security đang dùng. Ngay cả khi có thể lọc phần tử, metadata phân trang đã được tạo trước vẫn không tự trở thành COUNT sau phân quyền.

## 4. Các sai lệch thường gặp

### Trang thiếu bản ghi

Các bản ghi không có quyền chiếm vị trí trong `LIMIT/OFFSET`. Các bản ghi hợp lệ ở phía sau không được tự động kéo lên lấp chỗ trống. Người dùng có thể thấy trang rỗng nằm giữa các trang vẫn còn bản ghi hợp lệ.

### Tổng và số trang bị thổi phồng

`COUNT(*)` theo điều kiện nghiệp vụ chung sẽ đếm cả tài liệu của người khác hoặc tenant khác. Metadata có thể sai, đồng thời để lộ quy mô dữ liệu ngoài phạm vi cho phép. COUNT trên cùng chính sách quyền, trạng thái và bộ lọc là yêu cầu bắt buộc nếu API công bố tổng chính xác.

### `hasNext` không còn đáng tin

`hasNext` của tập chưa phân quyền không nói chính xác liệu còn phần tử **được phép xem** nào ở trang sau. Tương tự, `content.size() < size` sau hậu lọc không chứng minh đã hết dữ liệu hợp lệ.

### Sai lệch khi dữ liệu biến động

OFFSET pagination có thể lặp hoặc bỏ sót dữ liệu khi người khác chèn/xóa bản ghi giữa hai lần gọi. Hậu lọc càng khó diễn giải khi các trang bị thiếu không đều. Sắp xếp cần có khóa phụ duy nhất, chẳng hạn `createdAt DESC, id DESC`, và cursor/keyset pagination có thể hữu ích khi danh sách lớn hoặc thường biến động.

### Chi phí và nguy cơ rò rỉ

Đọc các record không có quyền rồi kiểm tra từng record trong Java làm tăng số row truy vấn, N+1 kiểm tra ACL, CPU và bộ nhớ. Nó cũng khiến dữ liệu chưa phân quyền có cơ hội đi qua mapper, logging hoặc caching trước khi bị loại. Đưa predicate quyền xuống lớp truy vấn giảm bề mặt này.

## 5. Cách thiết kế truy vấn an toàn

Điều kiện quyền phải xuất phát từ danh tính/tenant đã được xác thực, kết hợp với bộ lọc nghiệp vụ trước phân trang. Ví dụ một hệ thống cho phép xem tài liệu đang hoạt động thuộc chính người dùng trong tenant hiện tại:

~~~java
public interface DocumentRepository extends JpaRepository<Document, Long> {
    @Query(
        value = """
            select d from Document d
            where d.tenantId = :tenantId
              and d.ownerUsername = :username
              and d.active = true
            """,
        countQuery = """
            select count(d) from Document d
            where d.tenantId = :tenantId
              and d.ownerUsername = :username
              and d.active = true
            """
    )
    Page<Document> findVisible(
        @Param("tenantId") UUID tenantId,
        @Param("username") String username,
        Pageable pageable
    );
}
~~~

Ở service, xác định quyền từ principal tin cậy:

~~~java
@Service
public class DocumentQueryService {
    private final DocumentRepository repository;
    private final CurrentScope currentScope;

    public DocumentQueryService(
        DocumentRepository repository,
        CurrentScope currentScope
    ) {
        this.repository = repository;
        this.currentScope = currentScope;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Page<Document> listVisible(Pageable pageable) {
        return repository.findVisible(
            currentScope.requiredTenantId(),
            currentScope.requiredUsername(),
            pageable
        );
    }
}
~~~

Hai đoạn là mã minh họa tích hợp, giả định có entity `Document` và abstraction ứng dụng `CurrentScope`. `CurrentScope` phải lấy tenant/user đáng tin từ authentication, không đọc trực tiếp tham số `tenantId` hay `username` do client tự gửi rồi coi đó là phạm vi quyền.

`@PreAuthorize` quyết định người dùng có quyền gọi method; nó **không tự động** giới hạn từng row. Predicate trong repository mới quyết định dữ liệu nào vào Page. Nếu chính sách cho phép xem tài liệu chia sẻ, thuộc nhóm hoặc ACL, predicate phải biểu diễn đầy đủ các trường hợp đó; điều kiện owner-only trên chỉ đúng với chính sách owner-only.

Nếu dùng `Specification`, Criteria API hay Querydsl, hãy giữ cùng điều kiện quyền cho truy vấn content và COUNT. Khi JOIN nhiều permission row có thể tạo bản ghi trùng, xử lý `DISTINCT` và `COUNT(DISTINCT ...)` phù hợp để tránh tăng sai tổng.

## 6. Thứ tự xử lý

1. Xác thực request và lấy principal, tenant, authority từ ngữ cảnh đáng tin.
2. Kiểm tra quyền thực thi hành động danh sách, chẳng hạn `document:read`.
3. Tạo predicate quyền theo bản ghi và kết hợp với bộ lọc nghiệp vụ.
4. Sắp xếp ổn định bằng trường chính và khóa phụ duy nhất.
5. Chạy SELECT với predicate đã phân quyền, sau đó mới OFFSET/LIMIT hoặc cursor.
6. Khi cần `Page`, chạy COUNT trên **chính cùng tập điều kiện**; khi không cần tổng, cân nhắc `Slice`.
7. Trả về content, thông tin trang và metadata đúng với tập dữ liệu được phép xem.

~~~text
Authentication -> trusted access scope
                          |
Business filters ---------+--> WHERE (authorized AND business)
                                      |
                              stable ORDER BY
                                      |
                              LIMIT / cursor
                                      |
                              authorized content
                                      |
                    COUNT (same WHERE), if requested
~~~

Nếu database dùng Row-Level Security (RLS), cần bảo đảm security context đúng trên connection/session cho SELECT và COUNT, và được reset theo lifecycle pool; kiểm chứng điều này bằng integration test.

## 7. `Page`, `Slice` và cursor

| Lựa chọn | Có gì? | Khi dùng |
|---|---|---|
| `Page<T>` | Nội dung, số phần tử tổng, số trang tổng | UI cần tổng chính xác; COUNT cùng quyền có thể tốn tài nguyên |
| `Slice<T>` | Nội dung và có lát tiếp theo hay không | UI chỉ cần “Xem thêm”, tránh COUNT |
| Keyset/cursor | Tiếp tục từ khóa sắp xếp ổn định | Dữ liệu lớn, OFFSET sâu hoặc nhiều thay đổi |

Cả ba đều cần predicate quyền nằm ở nguồn. Với cursor, dùng khóa sắp xếp xác định và bảo vệ cursor khỏi sửa đổi khi nó mang thông tin nhạy cảm hoặc quyết định phạm vi truy cập. Cursor không cấp thêm quyền; mỗi request luôn phải xác thực lại scope.

Nếu bất khả kháng phải hậu kiểm một policy không thể đẩy xuống database, có thể quét nhiều lô để tìm đủ `size+1` phần tử hợp lệ và xác định `hasNext`. Khi đó cần lưu vị trí quét **của nguồn**, đặt giới hạn tài nguyên và tính đến dữ liệu thay đổi. Không tuyên bố `totalElements` chính xác nếu chưa đếm toàn bộ tập được phép xem. Thường `Slice` hoặc cursor có ngữ nghĩa minh bạch hơn.

## 8. Java 17 demo: chứng minh thứ tự filter/pagination

Ví dụ Java 17 độc lập dưới đây tái hiện chính xác tình trạng trang thiếu khi lọc quyền sau `limit`:

~~~java
import java.util.List;

public class PaginationDemo {
    public static void main(String[] args) {
        List<Integer> ids = List.of(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12);
        int pageSize = 5;

        List<Integer> rawPage = ids.stream().limit(pageSize).toList();
        List<Integer> postFiltered = rawPage.stream()
                .filter(id -> id % 2 == 0).toList();

        List<Integer> visible = ids.stream()
                .filter(id -> id % 2 == 0).toList();
        List<Integer> authorizedPage = visible.stream()
                .limit(pageSize).toList();

        System.out.println("After pagination: " + postFiltered);
        System.out.println("Before pagination: " + authorizedPage);
        System.out.println("Authorized total: " + visible.size());
    }
}
~~~

Lưu thành `PaginationDemo.java`; chạy:

~~~bash
javac PaginationDemo.java
java PaginationDemo
~~~

Stdout:

~~~text
After pagination: [2, 4]
Before pagination: [2, 4, 6, 8, 10]
Authorized total: 6
~~~

Demo chỉ mô phỏng thứ tự thao tác trên Java Stream, không tự chạy Spring Data JPA hay method security proxy.

## 9. Test cần có

- Với 12 record và người A chỉ được xem 6 ID chẵn, `size=5`: trang 0 `[2,4,6,8,10]`, trang 1 `[12]`, `totalElements=6`, `totalPages=2`, `hasNext=true/false` tương ứng.
- Người B có tập quyền khác; xác nhận cả content và COUNT chỉ đếm đúng tập B được xem.
- Thử đoán ID, đổi tenant, thay query parameter, truy vấn trang sâu và sort khác nhau; user không thể đọc row ngoài quyền hoặc suy ra metadata ngoài quyền.
- Thử trang cuối không đầy, trang ngoài phạm vi, tập rỗng, permission thay đổi, record thêm/xóa giữa các lần truy vấn.
- Khi ACL JOIN nhiều dòng, test record trùng và COUNT distinct.
- Nếu dùng annotation method security, test qua Spring bean/proxy thực tế, không chỉ gọi nội bộ Java.
- Kiểm tra query plan và index trên các cột tenant, owner/ACL, filter và sort khi dữ liệu tăng.

## 10. Lỗi phổ biến

**Lỗi: `@PostFilter` trên trang đã truy vấn.** Phần tử hợp lệ ở ngoài trang không được bù vào trang hiện tại. **Sửa:** đưa policy xuống truy vấn trước phân trang.

**Lỗi: COUNT toàn bảng nhưng content đã lọc quyền.** Tổng/số trang sai, có thể lộ metadata. **Sửa:** cùng predicate quyền ở SELECT và COUNT.

**Lỗi: `totalElements = content.size()`.** Đây chỉ là số record của một trang. **Sửa:** COUNT chính xác hoặc chuyển sang `Slice` nếu không cần tổng.

**Lỗi: dùng `content.size() < pageSize` để kết luận hết dữ liệu sau hậu lọc.** Trang thiếu phần tử không đồng nghĩa hết dữ liệu hợp lệ. **Sửa:** tính `hasNext` trên tập đã phân quyền.

**Lỗi: client tự chọn tenant/owner để được quyền xem.** Cho phép vượt ranh giới dữ liệu. **Sửa:** scope quyền do server lấy từ authentication, còn filter client chỉ được thu hẹp quyền.

**Lỗi: sort không ổn định hoặc COUNT khác SELECT.** Gây lặp/bỏ sót hoặc tổng sai. **Sửa:** ORDER BY có khóa duy nhất và đồng nhất predicate.

## 11. Checklist

Một API phân trang an toàn cần chứng minh được: (1) SELECT chỉ thấy row được phép truy cập; (2) COUNT có cùng predicate; (3) phân trang diễn ra sau điều kiện quyền; (4) sort ổn định; (5) scope đến từ authentication; (6) `totalElements`, `totalPages`, `hasNext` phản ánh dữ liệu được phép xem; (7) test bao phủ nhiều principal, tenant và nhiều trang; (8) dữ liệu chưa phân quyền không bị phơi ra qua log, cache hoặc mapper.

Khi đảm bảo cùng một phạm vi quyền từ truy vấn đến metadata, frontend có thể phân trang nhất quán mà không lộ số lượng bản ghi bị từ chối.
