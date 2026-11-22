# `@PreFilter`, `@PostFilter` và giới hạn của việc lọc sau truy vấn

> **Phạm vi:** Spring Security Method Security, Java 17+, Spring Security 6.x. Bài học thuộc chủ đề **Bảo vệ phương thức**. Trọng tâm là phân biệt lọc đối số **trước** khi chạy phương thức và lọc kết quả **sau** khi phương thức trả về; hiểu giới hạn về bảo mật, hiệu năng, phân trang, giao dịch và tính toàn vẹn dữ liệu khi chỉ lọc ở bộ nhớ sau truy vấn.

## 1. Vì sao cần lọc ở cấp phương thức?

Giả sử dịch vụ trả danh sách tài liệu. Cơ sở dữ liệu có 100.000 tài liệu của nhiều người, nhưng Alice chỉ được nhìn các tài liệu của mình. Có ba việc khác nhau dễ bị gộp làm một:

1. **Quyền gọi phương thức:** Alice có được gọi thao tác “đọc tài liệu” không? `@PreAuthorize("hasAuthority('document:read')")` phù hợp với điều kiện này.
2. **Quyền trên từng phần tử:** trong danh sách trả về, phần tử nào Alice được nhìn thấy? `@PostFilter` có thể lọc kết quả sau khi phương thức đã chạy.
3. **Giới hạn dữ liệu ngay từ nguồn:** database chỉ nên đọc hàng của Alice/tenant hợp lệ, trước khi phân trang, count, join và chuyển dữ liệu vào ứng dụng. Đây là nhiệm vụ của truy vấn có ràng buộc phạm vi, repository hoặc data-access policy.

Điều quan trọng nhất: **`@PostFilter` không ngăn một truy vấn đã thực thi truy cập những hàng không thuộc quyền người dùng.** Nó chỉ có thể giới hạn các phần tử được trả về qua proxy method security đối với kiểu dữ liệu và biểu thức được hỗ trợ. Để bảo vệ dữ liệu lớn, đa tenant, phân trang hay xử lý có tác dụng phụ, cần thiết kế quyền ngay từ trước và trong quá trình truy vấn.

```text
Caller → Spring AOP Method Security
  ├─ @PreFilter: loại phần tử đầu vào không đạt điều kiện
  ├─ @PreAuthorize: kiểm tra quyền gọi (nếu có)
  ↓
  phương thức dịch vụ thực thi
  ↓
  repository truy vấn / nghiệp vụ chạy
  ↓
  @PostAuthorize: kiểm tra quyền trên kết quả (nếu có)
  @PostFilter: lọc phần tử của kết quả (nếu có)
  ↓
  caller nhận kết quả đã được xử lý qua proxy

Nếu repository đã đọc quá nhiều hàng, @PostFilter không làm
truy vấn SQL vừa thực hiện trở nên hẹp hơn.
```

Sơ đồ giúp hiểu các giai đoạn, **không cam kết thứ tự chi tiết giữa mọi interceptor tùy biến**. Spring Security tổ chức annotation theo các interceptor/AOP advisor có thứ tự; điều kiện cụ thể còn phụ thuộc cấu hình AOP, phiên bản và loại phương thức.

## 2. So sánh các annotation method security

| Annotation | Thời điểm | Đối tượng kiểm tra | Hành vi chính | Chọn dùng khi |
|---|---|---|---|---|
| `@PreAuthorize` | Trước khi gọi phương thức | Quyền gọi, tham số, identity | Cho phép hoặc từ chối **cả lời gọi** | Cần quyền bắt buộc hoặc kiểm tra input trước hành động |
| `@PreFilter` | Trước khi phương thức đích chạy | Mỗi phần tử của một tham số tập hợp | Loại phần tử không khớp khỏi đầu vào nhìn thấy bởi phương thức | Nghiệp vụ **chấp nhận bỏ phần tử** không có quyền |
| `@PostAuthorize` | Sau khi phương thức đích chạy | Giá trị trả về (thường một object) | Cho phép hoặc từ chối **cả kết quả** | Kiểm tra quyền dựa trên dữ liệu đã đọc; không phù hợp để cứu tác dụng phụ đã xảy ra |
| `@PostFilter` | Sau khi phương thức đích chạy | Mỗi phần tử của kết quả dạng tập hợp được hỗ trợ | Loại các phần tử không phù hợp trước khi trả về qua proxy | Kết quả nhỏ, đã có, không cần pagination/count đúng theo tập nhìn thấy |
| `@EnableMethodSecurity` | Khởi tạo application | Các Spring bean chịu proxy | Kích hoạt cơ chế method authorization | Điều kiện cần cho các annotation trong ứng dụng Servlet thông thường |

**`@PreFilter` và `@PostFilter` không đồng nghĩa với từ chối truy cập toàn bộ.** Ví dụ, Alice gửi 5 tài liệu gồm 3 tài liệu của Bob thì `@PreFilter` có thể khiến service chỉ nhận 2 tài liệu của Alice. Điều này có thể hợp lý với thao tác “lọc danh sách”, nhưng cực kỳ nguy hiểm về giao ước nghiệp vụ nếu API yêu cầu “xử lý thành công toàn bộ hoặc báo lỗi”. Khi muốn **all-or-nothing**, hãy kiểm tra tất cả phần tử và từ chối toàn bộ nếu bất kỳ phần tử nào không đủ quyền.

Một `@PostFilter` chỉ dùng cho kết quả list có thể khiến caller thấy list rỗng; nó **không tự trả HTTP 403** khi tất cả phần tử bị loại. Nếu cần một lỗi từ chối thay vì danh sách rỗng, dùng `@PreAuthorize`, `@PostAuthorize` hoặc một kiểm tra policy rõ ràng theo contract của API.

## 3. Kích hoạt method security

Trong ứng dụng Spring Boot dùng Spring Security 6.x, cần kích hoạt method security rõ ràng. Ví dụ tệp `MethodSecurityConfig.java`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

`@EnableMethodSecurity` kích hoạt các annotation `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` theo cấu hình mặc định. Dependency `spring-boot-starter-security` **không tự bật method security** chỉ vì đã có HTTP `SecurityFilterChain`. Các chú thích phải nằm trên Spring-managed bean/method có lời gọi đi qua cơ chế proxy/AOP thích hợp.

Nếu thêm annotation vào một object tạo bằng `new`, hoặc phương thức nội bộ gọi `this.otherAnnotatedMethod()` mà lời gọi không qua proxy, kiểm tra có thể **không chạy**. Private/final method và kiểu proxy cụ thể cũng cần lưu ý. Hãy test trên **bean được Spring inject** thay vì chỉ tạo đối tượng bằng `new` rồi kết luận annotation đang hoạt động.

Trong ứng dụng reactive, việc bật `@EnableReactiveMethodSecurity` và hỗ trợ Reactor `Context` là cơ chế khác; không xem hai cấu hình Servlet và WebFlux là hoán đổi trực tiếp. Phần ví dụ annotation bên dưới nhắm tới Spring method security đồng bộ thông thường; cách xử lý danh sách reactive được trình bày riêng ở cuối bài.

## 4. `@PreFilter`: lọc phần tử đầu vào trước khi gọi phương thức

Đối với một tham số collection, SpEL dùng biến đặc biệt `filterObject` đại diện cho **phần tử đang xét**. `authentication.name` lấy tên danh tính từ `Authentication` của security context, do hệ thống xác thực thiết lập.

Ví dụ:

```java
@PreFilter("filterObject.owner == authentication.name")
public List<Document> acceptOwnedDocuments(List<Document> documents) {
    return documents;
}
```

Nếu caller đã xác thực là `alice` và truyền danh sách ba Document có `owner` là `alice`, `bob`, `alice`, phương thức đích nhìn thấy hai document của Alice. Ví dụ này là **trích đoạn trong một Spring bean đã bật method security**, Document phải có JavaBean property `owner` có thể được SpEL đọc (ví dụ getter `getOwner()`). Không phải chương trình chạy độc lập.

### 4.1. Phương thức có nhiều tham số tập hợp

Nếu có nhiều tham số có thể lọc, chỉ rõ đích bằng `filterTarget`:

```java
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.core.parameters.P;

@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "documents"
)
public List<Document> acceptOwnedDocuments(
        @P("documents") List<Document> documents,
        List<Document> attachments,
        boolean dryRun) {
    return documents;
}
```

Annotation `@P("documents")` gắn tên tham số cho cơ chế truy xuất tham số của Spring Security. Khi biểu thức tham chiếu tên tham số Java trực tiếp (ví dụ `#documentId`), cấu hình biên dịch giữ tên bằng `-parameters` hoặc kỹ thuật khai báo tên tương thích là quan trọng. Đừng suy đoán rằng tên xuất hiện trong source Java chắc chắn luôn có thể truy cập được ở runtime.

**Các container theo tài liệu Spring Security 6.5:** lọc có thể áp dụng cho array, collection, map và stream ở những ngữ cảnh được hỗ trợ; khi dùng `Map`, phần tử được xét là entry, nên truy xuất giá trị qua `filterObject.value`:

```java
@PreFilter("filterObject.value.owner == authentication.name")
public Map<String, Document> importOwned(
        Map<String, Document> documentsByCode) {
    return documentsByCode;
}
```

Những đoạn trên mô tả ý nghĩa, **không bảo đảm mọi collection tùy biến/immutable đều lọc được bằng cùng một cách**. Cần dùng container tương thích và test với phiên bản Spring Security thực tế. Đặc biệt, không dựa vào việc Spring tự biến `null` thành list rỗng. Với `Stream`, chỉ xử lý stream còn mở, tránh tái sử dụng stream đã tiêu thụ.

### 4.2. `@PreFilter` là bộ lọc, không phải giao dịch xác thực toàn bộ

Giả sử API `POST /documents/batch-delete` nhận 4 id, gồm 3 id thuộc Alice và 1 id thuộc Bob. Nếu áp dụng `@PreFilter` trên danh sách tài liệu, method có thể chỉ nhận 3 tài liệu của Alice và xử lý tiếp. Nếu API đã cam kết “xóa toàn bộ 4 hoặc không xóa gì”, **lọc âm thầm là sai contract**, dù không xóa nhầm dữ liệu của Bob.

Giải pháp cho all-or-nothing:

- Kiểm tra input đã được xác thực, ánh xạ ID sang entity tin cậy từ database; đừng tin `owner`/`tenant` do client gửi.
- Dùng policy ở service xác minh **mọi phần tử** thuộc tenant, owner hoặc quyền của actor.
- Nếu bất kỳ phần tử không hợp lệ, từ chối toàn bộ trước khi có tác dụng phụ.
- Với cập nhật đồng thời, giao dịch, khóa hoặc cập nhật có điều kiện vẫn cần thiết để policy không bị vô hiệu do dữ liệu thay đổi sau khi check.

## 5. `@PostFilter`: lọc phần tử kết quả sau khi phương thức hoàn tất

Ví dụ trích đoạn service trả danh sách tài liệu:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostFilter("filterObject.owner == authentication.name")
public List<Document> browseAllDocuments() {
    return documentRepository.findAll();
}
```

Diễn giải đúng thứ tự logic:

1. `@PreAuthorize` yêu cầu `document:read`. User thiếu quyền bị từ chối trước khi phương thức thực thi.
2. Phương thức truy vấn `findAll()`; **repository đã đọc tất cả document mà query trả về**, dù không thuộc Alice.
3. `@PostFilter` đánh giá từng document trong kết quả, loại phần tử có owner khác `authentication.name`.
4. Caller đi qua proxy nhận list đã được lọc. Điều này **không quay ngược thời gian** để tránh chi phí của `findAll()` hoặc những tác dụng phụ đã phát sinh trong method.

Với 5 tài liệu (3 của Alice, 2 của Bob), service có thể đọc 5 phần tử nhưng caller chỉ nhận 3. Nếu dữ liệu ít, công việc đọc danh sách đã cần thực hiện vì một lý do khác và ràng buộc an toàn đã được xử lý ở nơi khác, cách này có thể là một lớp lọc phụ trợ hợp lý. Nếu danh sách tăng tới hàng triệu bản ghi, thiết kế này có thể gây quá tải và vi phạm yêu cầu cách ly dữ liệu tại nguồn.

### 5.1. `@PostFilter` không phải `@PostAuthorize`

`@PostFilter` đánh giá từng phần tử của kết quả tập hợp; `@PostAuthorize` kiểm tra toàn bộ invocation dựa vào giá trị trả về. Ví dụ trả một Document duy nhất:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Document loadOneDocument(long id) {
    return documentRepository.findRequiredById(id);
}
```

Trích đoạn này giả định repository trả `Document` không null và `owner` là JavaBean property. `@PostAuthorize` có thể từ chối việc trả Document cho người không có quyền, nhưng repository đã thực hiện truy vấn và mọi side effect trước lúc method kết thúc vẫn có thể đã xảy ra. Với dữ liệu nhạy cảm, ưu tiên truy vấn đã giới hạn owner/tenant hoặc kiểm tra quyền trước hành động.

### 5.2. Map, array và Stream

Theo tài liệu Spring Security 6.5, `@PostFilter` hỗ trợ các dạng array, collection, map và stream (đối với stream còn mở). Với `Map<K, Document>`, `filterObject` là entry; để truy xuất Document dùng `filterObject.value`:

```java
@PostFilter("filterObject.value.owner == authentication.name")
public Map<String, Document> browseByCode() {
    return documentRepository.findByCode();
}
```

Với JPA Stream/lazy collection, cần cẩn trọng transaction, session, cursor và thời điểm tiêu thụ. Một stream chưa được đọc hết không nên bị coi là “một list đã lọc sẵn, hoàn toàn an toàn”. Đọc/đóng stream đúng vòng đời và ưu tiên điều kiện ở repository khi yêu cầu có khối lượng lớn hoặc cần phân trang.

Với `Mono<List<Document>>` hoặc `Flux<Document>` trong WebFlux, **không mặc định coi đó là List thông thường** để áp `@PostFilter` bằng cách copy code Servlet. Thiết kế reactive thường dùng truy vấn có ràng buộc và các toán tử `filter`/`filterWhen` trong cùng Publisher khi thật sự cần lọc bổ sung; việc kiểm soát quyền phải gắn đúng subscription và Reactor Context.

## 6. Giới hạn cốt lõi của lọc sau truy vấn

### 6.1. SQL đã chạy, dữ liệu đã rời database

Khi method chạy `findAll()` rồi `@PostFilter`, truy vấn có thể đã đọc và chuyển nhiều hàng hơn mức người gọi được phép xem. Việc lọc sau đó không tiết kiệm:

- I/O ổ đĩa, CPU query, bộ nhớ buffer, network DB-to-app và thời gian hydrate entity.
- Chi phí ánh xạ DTO, lazy loading hoặc N+1 queries trước lúc lọc (nếu xảy ra trong method).
- Chi phí khởi tạo các object nhạy cảm vào bộ nhớ tiến trình.
- Side effects bên trong method như ghi log dữ liệu đầy đủ, cache chung, gửi event, tính aggregate hay gọi service phụ trợ.

**Không suy ra `@PostFilter` tự làm lộ thông tin cho HTTP client**: kết quả trả qua proxy có thể đã được lọc trước khi serialization. Vấn đề là **hàng vượt phạm vi đã bị đọc/xử lý ở tầng bên dưới**, làm tăng bề mặt rủi ro và chi phí, trong khi những đường đi không qua proxy/cách sử dụng dữ liệu trung gian cần được bảo vệ riêng.

### 6.2. Lọc sau phân trang làm sai kích thước trang và tổng số

Giả sử database có 20 bản ghi, query lấy trang đầu với `LIMIT 10 OFFSET 0`. Trong 10 bản ghi trả về chỉ có 3 bản ghi Alice được xem. Nếu chạy `@PostFilter` trên 10 bản ghi đó:

- Caller chỉ thấy **3 phần tử**, dù còn nhiều bản ghi khác của Alice ở trang tiếp theo.
- `totalElements = 20` được tính ở database trước lọc có thể không phải tổng của bản ghi Alice nhìn thấy.
- `hasNext`, `totalPages`, offset/cursor có thể bị lệch so với tập dữ liệu của Alice.
- Nếu dùng kiểu `Page<Document>`, **không giả định** `@PostFilter` tự hiểu, lọc và cập nhật toàn bộ metadata của Page; tài liệu của annotation nêu các kiểu tập hợp như array/collection/map/stream, không đảm bảo logic phân trang của Spring Data.

Vì vậy, ràng buộc phải đưa vào query **trước `LIMIT/OFFSET` và phép đếm**. Câu lệnh đúng về ý nghĩa:

```sql
SELECT id, owner_id, tenant_id, title
FROM documents
WHERE tenant_id = :trustedTenantId
  AND owner_id = :trustedUserId
ORDER BY id
LIMIT :pageSize OFFSET :offset;
```

Truy vấn count tương ứng cũng phải cùng điều kiện:

```sql
SELECT COUNT(*)
FROM documents
WHERE tenant_id = :trustedTenantId
  AND owner_id = :trustedUserId;
```

`trustedUserId` và `trustedTenantId` phải lấy từ identity được xác thực và chính sách hợp lệ, không copy từ query parameter hay JSON do caller tự sửa. Sắp xếp ổn định (ví dụ `ORDER BY id`) và chiến lược snapshot/cursor khi dữ liệu thay đổi cũng quan trọng cho phân trang thực.

### 6.3. Lọc sau truy vấn có thể làm sai thống kê hoặc phép tổng hợp

Ví dụ service đã tính `sum(totalAmount)` hoặc `count(*)` trên toàn bảng trước khi gọi `@PostFilter`. Vì kết quả là con số, không phải các Document cần loại riêng lẻ, `@PostFilter` không sửa tổng để biến nó thành “tổng được phép xem”. Tương tự, nếu tính ranking, thống kê, top N hoặc aggregate bằng dữ liệu không thuộc quyền, các phép tính đã chịu ảnh hưởng của dữ liệu đó dù list đầu ra sau này bị lọc.

Mọi query aggregate phải dùng **cùng phạm vi quyền** với query đọc chi tiết.

### 6.4. Không bảo vệ việc ghi, xóa hay gọi dịch vụ phụ

Giả sử một method có side effect:

```java
@PostFilter("filterObject.owner == authentication.name")
public List<Document> deleteAndReturnDeleted(long[] ids) {
    return documentRepository.deleteAndReturnDeleted(ids);
}
```

**Sai về thiết kế bảo mật:** phương thức đã xóa bản ghi trước khi kết quả được lọc. Lọc dữ liệu trả về sau đó không phục hồi bản ghi của người khác. Với thao tác ghi/xóa, quyền phải được xác minh **trước và trong** lệnh thay đổi trạng thái, kèm ràng buộc tenant/owner ở SQL, transaction và xử lý cạnh tranh.

### 6.5. Phân quyền đa tenant và che giấu tồn tại dữ liệu

Nếu database có tenant A và B, lọc ở Java sau khi đọc dữ liệu toàn bảng có thể phá mục tiêu cách ly ngay từ data access. Có thể còn rò số lượng qua count, timing, log hoặc hệ thống cache. Dùng tenant predicate trong repository; nếu nghiệp vụ cho phép admin xem nhiều owner cùng tenant, vẫn giữ `WHERE tenant_id = :trustedTenantId` rồi mới áp rule về role/owner.

Chính sách quyết định `403` hay `404` cho bản ghi ngoài quyền cần nhất quán và không lộ ID/metadata qua thông báo lỗi. Lọc list về rỗng **không đồng nghĩa** với kiểm soát quyền đọc một document đơn lẻ.

## 7. Ví dụ Java 17 độc lập: thấy lỗi phân trang ngay trong bộ nhớ

Tệp `AfterQueryFilteringDemo.java` sau dùng Java thuần để mô phỏng một query đã phân trang rồi mới lọc Alice. Đây **không phải lớp Spring**; purpose là nhìn chính xác hệ quả về trang/đếm, không giả định annotation đã được chạy.

```java
import java.util.List;

public class AfterQueryFilteringDemo {

    record Document(long id, String owner) {}

    public static void main(String[] args) {
        List<Document> all = List.of(
            new Document(1, "alice"),
            new Document(2, "bob"),
            new Document(3, "alice"),
            new Document(4, "bob"),
            new Document(5, "alice")
        );

        // Giả lập một trang DB trả 3 record trước khi kiểm tra owner.
        List<Document> dbPage = all.stream().limit(3).toList();

        // Tương đương ý tưởng lọc theo owner SAU khi tải trang.
        List<Document> afterFilter = dbPage.stream()
            .filter(d -> d.owner().equals("alice"))
            .toList();

        long actualVisibleTotal = all.stream()
            .filter(d -> d.owner().equals("alice"))
            .count();

        System.out.println("fetchedPage=" + dbPage.size());
        System.out.println("visiblePage=" + afterFilter.size());
        System.out.println("visibleIds=" +
            afterFilter.stream().map(Document::id).toList());
        System.out.println("rawTotal=" + all.size());
        System.out.println("visibleTotal=" + actualVisibleTotal);
    }
}
```

Biên dịch và chạy với **JDK 17+**:

```bash
javac AfterQueryFilteringDemo.java
java AfterQueryFilteringDemo
```

Kết quả stdout dự kiến:

```text
fetchedPage=3
visiblePage=2
visibleIds=[1, 3]
rawTotal=5
visibleTotal=3
```

Trang đầu lấy 3 bản ghi nhưng sau lọc chỉ còn 2; tổng raw là 5, tổng bản ghi Alice được phép thấy là 3. Nếu query thực không lọc owner trước `LIMIT`/`OFFSET`, cơ chế phân trang không thể giả định dùng các số thống kê của raw dataset cho actor. Đây là lỗi thiết kế truy vấn, **không được giải quyết bằng cách tăng page size tùy ý**.

## 8. Cách đúng hơn: giới hạn quyền trong repository/query

Giả sử ứng dụng dùng Spring Data JPA và user ở trong một tenant. Có thể định nghĩa repository method để SQL tự bao gồm ranh giới owner và tenant trước khi phân trang:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository extends JpaRepository<DocumentEntity, Long> {

    Page<DocumentEntity> findByTenantIdAndOwnerId(
        String tenantId, String ownerId, Pageable pageable);

    Page<DocumentEntity> findByTenantId(
        String tenantId, Pageable pageable);
}
```

Đây là **mẫu interface** cần có `DocumentEntity` với các property `tenantId`, `ownerId` và cấu hình Spring Data JPA phù hợp, không phải chương trình độc lập. Query dẫn xuất tương ứng phải tạo đúng điều kiện tenant/owner; cần kiểm tra SQL sinh ra, index và test với dữ liệu nhiều tenant. Nếu quyền đọc không đơn giản là owner, thiết kế predicate/ACL rõ ràng theo policy.

Service tách hai nhánh dựa trên **identity tin cậy và quyền đã xác thực**, đồng thời giữ tenant trong cả hai nhánh:

```java
// Trích đoạn trong một @Service, AccountPrincipal do ứng dụng định nghĩa.
@PreAuthorize("hasAuthority('document:read')")
public Page<DocumentEntity> findVisibleDocuments(
        Authentication authentication,
        Pageable pageable) {

    AccountPrincipal actor =
        (AccountPrincipal) authentication.getPrincipal();

    if (authentication.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_REVIEWER"))) {
        return documentRepository.findByTenantId(
            actor.getTenantId(), pageable);
    }

    return documentRepository.findByTenantIdAndOwnerId(
        actor.getTenantId(), actor.getUserId(), pageable);
}
```

Trong ứng dụng thật, đối số `Authentication` nên lấy từ nguồn do Spring Security kiểm soát (ví dụ principal injected qua `@AuthenticationPrincipal`, hoặc context đáng tin trong service), **không nhận một Authentication do caller tạo từ request body**. Lựa chọn allow reviewer thấy mọi document cùng tenant là giả định nghiệp vụ cần test, không phải đặc quyền Spring tự cấp. Nếu principal không đúng kiểu, thiếu tenant, userId, hoặc quyền, **từ chối** thay vì bỏ điều kiện SQL.

Đối với người dùng có quyền quản trị nhưng không được vượt tenant, repository vẫn phải có điều kiện tenant. Với các quyền phức tạp (nhóm sở hữu, chia sẻ, ACL, tổ chức cha), predicate phải thể hiện đúng logic “được phép” bằng join/subquery hoặc policy data-access tương đương. Phải dùng cùng predicate cho query dữ liệu và `COUNT`, đồng thời bảo đảm order và giới hạn tài nguyên.

### 8.1. Đặt authorization ở đâu?

| Kiểm tra | Vị trí phù hợp |
|---|---|
| User có quyền gọi chức năng đọc? | `@PreAuthorize("hasAuthority('document:read')")` |
| Tenant/user nào đang gọi? | Authentication/principal đáng tin |
| Bản ghi nào được đọc? | Query/repository có tenant, owner hoặc ACL |
| Bản ghi có được sửa/xóa? | Service policy + điều kiện update/delete tại data layer |
| Kết quả nhỏ đã tải xong cần ẩn một số phần tử phụ trợ? | Có thể dùng `@PostFilter` như một lớp bổ sung |
| Batch input cho phép bỏ những phần tử không hợp lệ? | Có thể dùng `@PreFilter` với contract rõ |
| Thao tác batch phải nguyên tử và từ chối nếu thiếu quyền? | Kiểm tra toàn bộ input + transaction, không chỉ `@PreFilter` |

## 9. Ví dụ Spring service sử dụng cả `@PreFilter` và `@PostFilter`

Mẫu dưới đây dùng kiểu `Document` có getter `getOwner()`, để SpEL `filterObject.owner` được hiểu là JavaBean property. Code yêu cầu Spring Security + Spring Context và cần bean `DocumentStore` do ứng dụng triển khai. Mục tiêu là minh họa wiring và semantics; đây không phải ứng dụng Spring Boot độc lập.

Tệp `DocumentFilterService.java`:

```java
import java.util.List;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;

@Service
public class DocumentFilterService {

    private final DocumentStore store;

    public DocumentFilterService(DocumentStore store) {
        this.store = store;
    }

    // Lọc các phần tử của collection đầu vào trước khi chạy saveBatch.
    @PreAuthorize("hasAuthority('document:write')")
    @PreFilter("filterObject.owner == authentication.name")
    public List<Document> saveBatch(List<Document> documents) {
        return store.saveBatch(documents);
    }

    // Chỉ là ví dụ cho một kết quả nhỏ; findAll không thích hợp dữ liệu lớn.
    @PreAuthorize("hasAuthority('document:read')")
    @PostFilter("filterObject.owner == authentication.name")
    public List<Document> listVisibleSmallSet() {
        return store.findAll();
    }

    public interface DocumentStore {
        List<Document> saveBatch(List<Document> documents);
        List<Document> findAll();
    }

    public static final class Document {
        private final long id;
        private final String owner;

        public Document(long id, String owner) {
            this.id = id;
            this.owner = owner;
        }

        public long getId() {
            return id;
        }

        public String getOwner() {
            return owner;
        }
    }
}
```

**Cách đọc:**

- `saveBatch` có `@PreFilter`: service đích nhìn thấy phần tử có `owner` khớp `authentication.name`; **nhưng filter một property trên object đầu vào không chứng minh người gọi thực sự sở hữu bản ghi trong database**. Nếu caller gửi `Document{id=7, owner="alice"}` trong khi ID 7 thuộc Bob ở DB, việc so sánh giá trị do caller cung cấp sẽ sai quyền. Phải tải/đối chiếu dữ liệu chuẩn trước khi ghi.
- `@PreAuthorize("document:write")` là gate thêm cho cả phương thức, không thay thế owner check trên bản ghi chuẩn. Đừng coi có permission đồng nghĩa đủ điều kiện với mọi ID.
- `listVisibleSmallSet` minh họa `@PostFilter` rõ ràng; tránh áp dụng cách này cho `findAll()` dữ liệu lớn, page/cursor hoặc dữ liệu đa tenant có yêu cầu cách ly tại nguồn.
- Loại `List` và việc có thể loại bỏ phần tử phụ thuộc sự tương thích của collection; chuẩn bị một collection có thể thay đổi trong test, kiểm tra chính xác Spring Security version và cách lưu.
- Các ví dụ có thể dùng `@PreFilter`/`@PostFilter` với biểu thức gọi bean policy như `@documentAccess.canRead(filterObject, authentication)` khi kiểm tra phức tạp; bean này phải dựa trên identity và dữ liệu đáng tin. Lọc hàng loạt bằng callback từ Spring Expression có thể tạo nhiều truy vấn per-row; đánh giá N+1 và cache thật kỹ.

Nếu business yêu cầu lưu **toàn bộ batch hoặc không lưu gì**, không gọi `saveBatch` ở trên như một endpoint all-or-nothing; thay bằng method xác minh từng ID và transaction để từ chối toàn bộ nếu một phần tử vi phạm.

## 10. Kiểm thử đúng semantics, bao gồm ca âm tính

Để kiểm tra annotation có tác dụng, test phải gọi **Spring-managed bean qua proxy**, dùng `@EnableMethodSecurity`, thiết lập authentication/authorities và mock repository. Với `@WithMockUser` (từ `spring-security-test`), có thể mô hình hóa user cho test Servlet đồng bộ; annotation hỗ trợ các security expression dựa trên context của request hoặc test.

Ma trận test tối thiểu:

| Ca | Input/kết quả thô | Kỳ vọng | Lý do |
|---|---|---|---|
| Alice gọi method có `document:read` | 2 của Alice, 1 của Bob | `@PostFilter` trả đúng 2 của Alice | Kiểm tra per-element filter |
| Alice thiếu `document:read` | Danh sách bất kỳ | Method bị từ chối trước khi repo chạy | Kiểm tra `@PreAuthorize` |
| Alice gọi `saveBatch` | 2 Alice, 1 Bob trong danh sách đầu vào | Method nhìn thấy 2 Alice nếu container hợp lệ | Kiểm tra `@PreFilter` |
| Alice thiếu `document:write` | Batch bất kỳ | Không được phép ghi | Gate quyền toàn method |
| Danh sách không có phần tử Alice | 3 Bob | Kết quả lọc có thể rỗng, không tự phát 403 | Hiểu đúng semantics lọc |
| Alice query page 10, chỉ 3 hàng thuộc Alice | Database trả page 10 rồi lọc | Test chỉ ra page bị thiếu và count sai | Chứng minh cần lọc từ query |
| Tenant A vs tenant B | Cùng owner string nhưng tenant khác | Không lọt dữ liệu B trong truy vấn A | Tenant isolation |
| Bob cố cập nhật ID thuộc Alice nhưng giả owner=Bob | Object giả mạo từ request | Bị từ chối khi đối chiếu DB | Chống tin thuộc tính từ client |
| Gọi internal method bằng `this` | Inner method có annotation | Test phát hiện advice không chạy khi bypass proxy | Giới hạn proxy |
| Stream bị đóng hoặc collection bất biến | Dữ liệu đặc biệt | Test theo contract/container thực tế | Tránh giả định loại nào cũng lọc được |

Ví dụ trích đoạn test JUnit 5 với bean được Spring inject (cần import chính xác class test và fixture phù hợp):

```java
@WithMockUser(username = "alice", authorities = {"document:read"})
@Test
void postFilterRemovesOtherOwners() {
    List<Document> actual = filterService.listVisibleSmallSet();

    assertThat(actual).extracting(Document::getOwner)
        .containsOnly("alice");
}
```

Đây chỉ là trích đoạn test: `filterService` là Spring bean đã inject, `Document` là kiểu fixture, `assertThat` từ AssertJ, và `DocumentStore` được mock trả cả document Alice/Bob. Nếu fixture chỉ trả document Alice, test không thực sự kiểm chứng `@PostFilter`.

**Đối với `@PreFilter`:** nên dùng `ArrayList` hoặc một loại input collection đã xác minh phù hợp, có dữ liệu của Alice và Bob, rồi mock store để xác nhận tham số mà method nhận. Không dựa vào input `List.of(...)` immutable khi chưa xác nhận semantics lọc của framework. Cũng phải khẳng định test không xóa/sửa bản ghi Bob ở DB chỉ vì SpEL đã lọc một bản sao object trong request.

**Đối với truy vấn cấp repository:** dùng integration test với database test chứa nhiều owner/tenant, kiểm tra cả `content`, `totalElements`, `hasNext`/`totalPages`, thứ tự và hiệu năng. Trường hợp query dùng native SQL/JPA, xác minh predicate owner/tenant xuất hiện trước `LIMIT/OFFSET`; không chỉ assert “HTTP 200”.

## 11. Sai lầm thường gặp

1. **Dùng `@PostFilter` để che chi phí `findAll()`:** dữ liệu vẫn bị đọc hết trước khi bị loại ở bộ nhớ đối với kết quả list eager.
2. **Dùng `@PostFilter` trên `Page<T>` như một phép phân trang quyền tự động:** metadata/offset/count không được tái tính đáng tin.
3. **Nhầm lọc với từ chối:** list rỗng từ `@PostFilter` khác lỗi authorization; `@PreFilter` có thể chấp nhận một phần batch.
4. **Tin dữ liệu do client gửi:** `owner` trong DTO có thể bị giả mạo, cần đối chiếu entity gốc và principal.
5. **Bỏ qua tenant:** `owner="alice"` không chứng minh dữ liệu thuộc tenant được truy cập, nhất là khi tên user không duy nhất toàn hệ thống.
6. **Đặt `@PostFilter` sau method có side effect:** không rollback hành vi ghi/xóa, gửi email hoặc event đã xảy ra.
7. **Quên `@EnableMethodSecurity`:** annotation trông đúng nhưng không có interceptor áp dụng.
8. **Self-invocation:** gọi `this.someMethod()` trong cùng bean có thể bypass AOP proxy.
9. **SpEL nhầm property:** `filterObject.owner` cần property đọc được; map entry cần `filterObject.value.owner`.
10. **Container không tương thích:** null, immutable collection, consumed stream hoặc kiểu trả về không hỗ trợ có thể gây lỗi hoặc hành vi không như dự đoán.
11. **Dùng biểu thức từng item để query DB:** mỗi phần tử tạo một truy vấn phụ là N+1, rất tốn tài nguyên.
12. **Sai identity source:** lấy tenant từ header/client thay vì principal đã xác thực, dẫn tới BOLA/IDOR.
13. **Bỏ qua thời điểm giao dịch và stream:** đọc sau transaction/session đã đóng có thể thất bại; giữ session mở quá lâu có chi phí.
14. **Không test ranh giới quyền:** chỉ test admin hoặc một user mà không có object khác owner/tenant, thiếu âm tính.
15. **Dùng `@PreFilter` như security gate cho batch atomic:** lọc bớt rồi vẫn ghi phần còn lại, trái contract all-or-nothing.
16. **Chỉ bảo vệ controller:** đường vào khác (job, message consumer, service khác) có thể sử dụng method mà không đi qua rule HTTP; đặt policy ở đúng service và repository.

## 12. Reactive và chiến lược an toàn cho dữ liệu lớn

Trong ứng dụng WebFlux/Spring Security reactive, cần bật method security theo cơ chế tương ứng (`@EnableReactiveMethodSecurity`), lấy danh tính qua Reactor `Context` khi cần. Các hàm trả `Mono`/`Flux` không nên được xử lý như `List` đồng bộ; **không gọi `block()` hay `subscribe()` thủ công** trong policy hoặc filter để ép một quyết định.

Ví dụ **trích đoạn minh họa**, `ReactiveDocumentRepository` có phương thức trả `Flux<Document>` và được tự triển khai để truy vấn đã giới hạn tenant/user ở storage:

```java
return reactiveDocumentRepository
    .findByTenantIdAndOwnerId(actor.tenantId(), actor.userId())
    .filter(document -> document.isVisible())
    .map(this::toDto);
```

`actor` ở đây là principal đã xác thực trong reactive pipeline, không lấy từ input chưa tin cậy. `filter` chỉ là kiểm tra logic bổ sung **sau khi repository đã hạn chế phạm vi**; filter reactive không phải SQL predicate và không sửa page/count đã tính. Nếu chính sách cần kiểm tra async mỗi phần tử, có thể dùng `filterWhen`/`flatMap` với logic phù hợp, giới hạn concurrency và lỗi; vẫn không thay thế query ACL/tenant thực thi tại nguồn.

Với danh sách lớn, lựa chọn thường tốt hơn:

1. **Predicate ở data layer** cho tenant, owner, share grants, ACL.
2. **Phân trang/count trong cùng phạm vi quyền**.
3. **Projection/DTO tối thiểu** để tránh tải cột nhạy cảm không cần thiết.
4. **Method-level authorize** cho chức năng chung, còn resource policy xác nhận ID/owner/state khi ghi.
5. **Lọc bổ sung sau query** chỉ với dữ liệu đã được giới hạn, khối lượng phù hợp và contract rõ.

## 13. Checklist áp dụng

- [ ] `@EnableMethodSecurity` hoặc cơ chế method security đúng stack đã bật; các lời gọi thực tế đi qua Spring proxy.
- [ ] Xác định rõ muốn **từ chối cả method**, **lọc một phần input**, hay **lọc output**.
- [ ] Dùng `@PreAuthorize`/`@PostAuthorize` nếu cần ALLOW/DENY cho toàn lời gọi, không lạm dụng filter.
- [ ] Biểu thức `filterObject` và `authentication` đọc đúng property và đúng principal tin cậy.
- [ ] Với nhiều collection input, `filterTarget` chọn đúng tham số, biên dịch/tên tham số được bảo đảm.
- [ ] Lọc sau query không được dùng làm cơ chế duy nhất bảo vệ dữ liệu nhiều tenant hoặc hàng triệu bản ghi.
- [ ] Repository áp `WHERE`/ACL trước `LIMIT/OFFSET` và đồng bộ với `COUNT`.
- [ ] Không dùng `@PostFilter` như cơ chế sửa aggregate, paging metadata hay rollback side effect.
- [ ] Batch thay đổi dữ liệu có chính sách all-or-nothing/partial rõ ràng, có transaction/optimistic locking khi phù hợp.
- [ ] Test cả bản ghi được xem và bị chặn, nhiều tenant, page, self-invocation, stream/collection edge cases.
- [ ] Với WebFlux, không tách subscription; giữ security context trong Reactor pipeline.

## 14. Tài liệu tham khảo

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): hướng dẫn `@PreFilter`, `@PostFilter`, `filterObject`, loại collection hỗ trợ, `@EnableMethodSecurity`.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): cơ chế Reactor `Context` và phương thức reactive.
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): phân quyền tại request/HTTP so với method-level.
- [OWASP API1:2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): tại sao truy vấn theo ID và quyền trên từng resource phải được kiểm tra.

**Điểm cần nhớ:** `@PreFilter` lọc phần tử của tham số **trước** khi phương thức đích thực thi; `@PostFilter` lọc phần tử kết quả **sau** khi phương thức đích chạy. Chúng hữu ích ở method boundary, nhưng **không thay thế quyền ở data layer**: phân trang, thống kê, tenant, owner, tác dụng phụ và dữ liệu lớn cần được ràng buộc từ truy vấn/transaction và kiểm thử bằng dữ liệu thực.