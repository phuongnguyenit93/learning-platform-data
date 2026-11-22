# Chính sách loại bỏ phần tử so với từ chối toàn bộ thao tác

> **Phạm vi:** Spring Security – authorization, nhóm **Lọc dữ liệu phương thức** (method filtering). Bài này giải thích khi nào cho phép gọi phương thức nhưng chỉ giữ các phần tử được quyền xem/xử lý, và khi nào phải từ chối cả lời gọi. Ví dụ dùng Java 17+ và Spring Security method security trên ứng dụng Spring Boot Servlet.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt **lọc từng phần tử** (*element filtering / partial result*) với **từ chối toàn bộ thao tác** (*all-or-nothing authorization*).
- Chọn đúng thời điểm và công cụ: `@PreFilter`, `@PostFilter`, `@PreAuthorize`, `@PostAuthorize` hoặc kiểm tra quyền trong service/data layer.
- Dự đoán chính xác việc thực thi phương thức, dữ liệu đầu vào/đầu ra, kết quả rỗng, ngoại lệ và phản hồi HTTP.
- Tránh các lỗi bảo mật và nghiệp vụ thường gặp ở truy vấn lớn, cập nhật hàng loạt, phân trang và giao dịch.

## 2. Hai chính sách giải quyết hai bài toán khác nhau

Giả sử kho báo cáo có ba bản ghi: `R1(owner=alice)`, `R2(owner=bob)`, `R3(owner=alice)`. Người đăng nhập là `alice`.

**Lọc phần tử**: cho phép thao tác trên phần hợp lệ; loại bỏ phần tử không đủ điều kiện. Với yêu cầu “liệt kê báo cáo tôi được xem”, danh sách `[R1, R2, R3]` có thể trở thành `[R1, R3]`. Việc một phần tử bị loại bỏ **không tự động làm thất bại cả lời gọi**. Nếu không phần tử nào hợp lệ, kết quả danh sách thường là rỗng.

**Từ chối toàn bộ**: đánh giá điều kiện mà *cả lời gọi* phải đáp ứng. Với yêu cầu “xuất toàn bộ báo cáo”, người thiếu quyền xuất toàn bộ không được nhận một bản xuất chỉ có hai bản ghi rồi bị tưởng là dữ liệu đầy đủ. Hệ thống từ chối thao tác và phát sinh lỗi truy cập bị từ chối, thường được ánh xạ thành HTTP 403 khi đã xác thực trong luồng web thông thường.

Điểm quyết định là **hợp đồng nghiệp vụ và ý nghĩa của dữ liệu**: người dùng có chấp nhận một tập con hợp lệ hay không? Quyền có cần áp dụng cho *mọi* phần tử trong một thao tác nguyên tử hay không?

| Tiêu chí | Lọc phần tử | Từ chối cả thao tác |
| --- | --- | --- |
| Đơn vị quyết định | Mỗi phần tử trong tập dữ liệu | Cả lời gọi/phép xử lý |
| Kết quả khi chỉ một số phần tử được phép | Trả/xử lý tập con hợp lệ | Thất bại toàn bộ |
| Kết quả khi không phần tử nào hợp lệ | Có thể là tập rỗng | Ngoại lệ từ chối nếu điều kiện bắt buộc thất bại |
| Công cụ method security điển hình | `@PreFilter`, `@PostFilter` | `@PreAuthorize`, `@PostAuthorize` |
| Bài toán thích hợp | Danh sách “của tôi”, danh sách chia sẻ, lựa chọn các mục hợp lệ | Xuất dữ liệu đầy đủ, cập nhật nguyên tử, xóa hàng loạt, hành động phải có quyền toàn cục |
| Rủi ro nếu dùng sai | Rò rỉ qua metadata, thiếu dữ liệu âm thầm, tốn tài nguyên | Từ chối quá mức hoặc kiểm tra quá muộn sau side effect |

> **Không có chính sách mặc định đúng cho mọi API.** “Danh sách cá nhân” có thể cho phép lọc; “tổng số liệu toàn tổ chức” thường cần quyền ở cấp thao tác. Hai endpoint đọc cùng một bảng vẫn có thể có hợp đồng quyền khác nhau.

## 3. Thời điểm các annotation can thiệp

Kích hoạt method security bằng `@EnableMethodSecurity` trên một lớp cấu hình. Spring Boot Starter Security **không tự kích hoạt** method-level authorization chỉ vì dependency có mặt. Các annotation hoạt động trên các lời gọi được Spring AOP proxy chặn, thường là public method của Spring-managed bean được gọi từ bean khác.

~~~java
package example.authz;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Luồng khái niệm:

~~~text
Caller -> Spring AOP proxy
           |
           +-- @PreFilter: sàng lọc collection/array/map/stream đầu vào
           +-- @PreAuthorize: điều kiện không đạt -> từ chối, không gọi thân method
           |
           v
        Method thực thi
           |
           +-- @PostAuthorize: xét kết quả; không đạt -> từ chối trả kết quả
           +-- @PostFilter: sàng lọc các phần tử của kết quả
           |
           v
        Caller nhận dữ liệu được phép
~~~

Sơ đồ nêu mục đích và thời điểm, **không khẳng định thứ tự giữa mọi advisor hoặc mọi proxy khác**. Khi phối hợp nhiều annotation, các quy tắc được áp dụng tuần tự; cần thỏa các điều kiện chặn toàn bộ. `@PostAuthorize` và `@PostFilter` đều nằm **sau khi thân phương thức đã chạy**; chúng không ngăn truy vấn cơ sở dữ liệu đã xảy ra. Spring Security cung cấp thứ tự interceptor và có thể tùy chỉnh nên không dựa vào thứ tự minh họa để thiết kế side effect.

- `@PreFilter("...")`: với đầu vào dạng tập hợp, biến `filterObject` là từng phần tử; phần tử không đạt bị loại trước khi logic nghiệp vụ nhận tập dữ liệu.
- `@PostFilter("...")`: với đầu ra dạng tập hợp, `filterObject` là từng phần tử được trả về; phần tử không đạt bị loại khỏi kết quả.
- `@PreAuthorize("...")`: điều kiện áp dụng cho cả lời gọi **trước** khi thực thi. Thích hợp để chặn thao tác ghi khi người dùng không có quyền.
- `@PostAuthorize("...")`: điều kiện áp dụng cho kết quả của lời gọi **sau** khi thực thi; `returnObject` tham chiếu đến kết quả. Hữu ích khi quyết định quyền cần đọc thuộc tính đối tượng, nhưng không nên là lớp bảo vệ duy nhất cho thao tác ghi.

Ví dụ biểu thức dùng `authentication.name` (tên principal), `hasAuthority('report:read')` (authority chính xác), `filterObject.owner()` (gọi accessor của Java record) và `#p0` (tham số đầu tiên của phương thức). Với JavaBean có `getOwner()`, có thể dùng `filterObject.owner`. Để truy cập tham số theo tên như `#id`, cần cấu hình biên dịch/khám phá tên tham số phù hợp; `#p0` tránh phụ thuộc đó.

## 4. Ví dụ Spring Security: lọc danh sách nhưng chặn đọc/xuất không hợp lệ

Các file sau nằm trong cùng package của một ứng dụng Spring Boot đã có `spring-boot-starter-security`. Kho lưu trữ giả lập bằng bộ nhớ để tập trung vào chính sách. Lớp record dùng accessor `owner()`; nguồn trả về `ArrayList` có thể lọc được.

**`Report.java`**

~~~java
package example.authz;

public record Report(long id, String owner, String title) {
}
~~~

**`ReportStore.java`**

~~~java
package example.authz;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class ReportStore {
    private final List<Report> reports = List.of(
            new Report(1L, "alice", "Báo cáo A"),
            new Report(2L, "bob", "Báo cáo B"),
            new Report(3L, "alice", "Báo cáo C")
    );

    public List<Report> findAll() {
        return new ArrayList<>(reports);
    }

    public Optional<Report> findById(long id) {
        return reports.stream().filter(r -> r.id() == id).findFirst();
    }
}
~~~

**`ReportAccess.java`** – bean xác định quyền trên từng bản ghi (demo dùng owner đơn giản; ứng dụng thực tế còn phải xét tenant, ACL và trạng thái tài nguyên):

~~~java
package example.authz;

import org.springframework.stereotype.Component;

@Component("reportAccess")
public class ReportAccess {
    private final ReportStore store;

    public ReportAccess(ReportStore store) {
        this.store = store;
    }

    public boolean isOwner(long reportId, String username) {
        return store.findById(reportId)
                .map(report -> report.owner().equals(username))
                .orElse(false);
    }
}
~~~

**`ReportService.java`** – ba hợp đồng khác nhau:

~~~java
package example.authz;

import java.util.List;
import java.util.NoSuchElementException;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ReportStore store;

    public ReportService(ReportStore store) {
        this.store = store;
    }

    // Hợp đồng: danh sách chỉ gồm báo cáo được xem.
    @PreAuthorize("hasAuthority('report:read')")
    @PostFilter("filterObject.owner() == authentication.name")
    public List<Report> listVisibleReports() {
        return store.findAll();
    }

    // Hợp đồng: đọc đúng một bản ghi hoặc bị từ chối.
    @PreAuthorize("hasAuthority('report:read') and "
            + "@reportAccess.isOwner(#p0, authentication.name)")
    public Report readOne(long id) {
        return store.findById(id).orElseThrow(NoSuchElementException::new);
    }

    // Hợp đồng: kết quả đầy đủ, không chấp nhận thiếu âm thầm.
    @PreAuthorize("hasAuthority('report:export:all')")
    public List<Report> exportAll() {
        return store.findAll();
    }
}
~~~

Các annotation có hiệu lực khi gọi `ReportService` **qua Spring proxy**. Nếu Alice có authority `report:read` nhưng không có `report:export:all`:

| Lời gọi | Kết quả |
| --- | --- |
| `listVisibleReports()` | Hai báo cáo ID 1 và 3; báo cáo của Bob bị bỏ |
| `readOne(1L)` | Trả báo cáo ID 1 |
| `readOne(2L)` | Bị từ chối **trước** khi chạy thân `readOne` |
| `exportAll()` | Bị từ chối toàn bộ; không trả tập con |
| `listVisibleReports()` với người chỉ có quyền đọc nhưng không sở hữu bản ghi nào | Danh sách rỗng; đây không phải lỗi từ chối từng phần tử |
| `listVisibleReports()` với người không có authority `report:read` | Bị chặn toàn bộ ngay từ `@PreAuthorize` |

**Vì sao ghép `@PreAuthorize` và `@PostFilter`?** Người dùng phải có quyền sử dụng tính năng đọc danh sách, sau đó mỗi phần tử còn phải đạt điều kiện sở hữu. Chỉ đặt `@PostFilter` mà quên quyền cấp chức năng có thể vô tình cho mọi người truy vấn (dù kết quả được lọc).

**Vì sao `readOne` dùng `@PreAuthorize`?** API lấy một tài nguyên có ý nghĩa “được xem hoặc không”; không thể trả “một phần của một đối tượng”. Bean `reportAccess` kiểm tra quyền trước khi service trả tài nguyên. Ứng dụng thật phải xử lý trường hợp không tồn tại/không được phép theo cùng chính sách tránh lộ sự tồn tại (có thể chọn ánh xạ 404 đồng nhất ở tầng HTTP, không tự động suy ra từ annotation).

## 5. `@PreFilter` cho đầu vào: chỉ dùng khi thực sự chấp nhận xử lý một phần

~~~java
// Trích đoạn phương thức minh họa trong một @Service;
// Report có accessor owner(), and reports là tham số đầu vào.
@PreAuthorize("hasAuthority('report:process')")
@PreFilter(filterTarget = "reports",
           value = "filterObject.owner() == authentication.name")
public List<Report> processAllowedOnly(List<Report> reports) {
    // Chỉ nhận những report còn lại sau khi lọc.
    return reports;
}
~~~

Nếu Alice gửi `[R1, R2, R3]`, logic xử lý nhận `[R1, R3]`. Điều này **chỉ đúng nghiệp vụ** khi người gọi biết và chấp nhận các phần tử không đủ quyền bị bỏ qua. Với “duyệt tất cả hóa đơn trong yêu cầu”, “chuyển tiền hàng loạt” hoặc “xóa toàn bộ danh sách đã chọn”, bỏ qua âm thầm làm sai hợp đồng, tạo trạng thái xử lý dở.

Với một thao tác cần **all-or-nothing**, hãy kiểm tra trước toàn bộ ID/tài nguyên cùng điều kiện quyền, từ chối khi có bất kỳ mục không hợp lệ, rồi mới thực thi trong ranh giới giao dịch thích hợp. Ví dụ phác thảo trong service:

~~~java
// Sơ đồ logic, cần hiện thực canProcessAll theo tenant/ACL của ứng dụng.
@PreAuthorize("hasAuthority('report:process') "
        + "and @reportAccess.canProcessAll(#p0, authentication)")
public void processAtomically(List<Long> ids) {
    // Thực thi toàn bộ chỉ sau khi các kiểm tra bắt buộc đã qua.
}
~~~

Đây là **mã minh họa chưa độc lập**: `canProcessAll` và nghiệp vụ phải được hiện thực. Cần chặn race/TOCTOU giữa kiểm tra và ghi (bằng giao dịch, locking, điều kiện update ở DB, và kiểm tra số dòng cập nhật); `@PreAuthorize` tự nó không tạo giao dịch.

## 6. `@PostAuthorize` khác `@PostFilter` thế nào?

Với một tài nguyên đơn lẻ:

~~~java
// Minh họa trong @Service đã có ReportStore.
@PostAuthorize("returnObject.owner() == authentication.name")
public Report readOneAfterCheck(long id) {
    return store.findById(id).orElseThrow();
}
~~~

`@PostAuthorize` không tạo một phiên bản báo cáo đã lọc. Nó **chấp nhận hoặc từ chối toàn bộ kết quả** sau khi `readOneAfterCheck` chạy. Với lời gọi trả danh sách, biểu thức `returnObject` thường xét cả danh sách như một giá trị; nó **không tự lặp qua từng phần tử** như `@PostFilter`.

Đặt hậu kiểm sau một phương thức ghi là nguy hiểm:

~~~java
// Phản ví dụ: KHÔNG dùng làm rào chắn quyền duy nhất.
@PostAuthorize("returnObject.owner() == authentication.name")
public Report updateReport(long id, String title) {
    // Nếu đã ghi DB/gửi sự kiện rồi mới bị từ chối, side effect đã xảy ra.
    throw new UnsupportedOperationException("Ví dụ minh họa");
}
~~~

Một lỗi từ chối sau lời gọi không bảo đảm mọi side effect ngoài DB (email, message, API bên ngoài) được hoàn tác. Với thao tác ghi, ưu tiên **kiểm tra trước** khi thực thi, cân nhắc ủy quyền tại lớp dữ liệu và ranh giới transaction. Không coi `@PostAuthorize` là “rollback tự động”.

## 7. Ví dụ Java 17 chạy độc lập để thấy rõ ngữ nghĩa

Ví dụ này **minh họa chính sách**, không giả lập Spring AOP hay API HTTP. Lưu thành `PolicyDemo.java`:

~~~java
import java.util.List;

public class PolicyDemo {
    record Item(int id, String owner) {}

    static List<Integer> visibleIds(String username, List<Item> all) {
        return all.stream()
                .filter(item -> item.owner().equals(username))
                .map(Item::id)
                .toList();
    }

    static List<Item> exportComplete(boolean permitted, List<Item> all) {
        if (!permitted) {
            throw new SecurityException("DENIED");
        }
        return all;
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item(1, "alice"),
                new Item(2, "bob"),
                new Item(3, "alice")
        );
        System.out.println(visibleIds("alice", items));

        try {
            exportComplete(false, items);
        } catch (SecurityException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 PolicyDemo.java
java PolicyDemo
~~~

stdout chính xác:

~~~text
[1, 3]
DENIED
~~~

Hai cách đều có thể bảo vệ dữ liệu, nhưng API cho người dùng phải công bố rõ khi nào trả tập con và khi nào không cho phép tiếp tục.

## 8. Các giới hạn và hệ quả quan trọng khi chọn chính sách

### 8.1. Phân trang, tổng số và điều kiện tìm kiếm

`@PostFilter` xử lý dữ liệu **sau** khi phương thức đã lấy/trả tập đầu ra. Nếu repository đã lấy 20 hàng cho page và chỉ 3 hàng thuộc Alice, việc lọc sau không biến page thành “20 hàng của Alice”; `totalElements`, số trang, thứ tự và các aggregation tính trước có thể sai hoặc tiết lộ thông tin. Không hứa “phân trang an toàn” bằng cách lọc nội dung một `Page` tùy ý.

Với danh sách lớn, tìm kiếm, phân trang hay dữ liệu nhiều tenant, đưa predicate quyền vào query/repository/row-level security ngay từ lúc truy vấn (ví dụ điều kiện `owner_id = current_user_id` kết hợp điều kiện tenant). Đánh giá quyền trên dữ liệu thực tế, tránh ghép câu SQL trực tiếp từ dữ liệu người dùng. `@PostFilter` thích hợp cho tập nhỏ hoặc lớp phòng thủ bổ sung; nó không thay thế thiết kế truy vấn có kiểm soát.

### 8.2. Tính nhất quán giữa danh sách và chi tiết

Một item bị ẩn khỏi `listVisibleReports` cũng phải bị từ chối qua `readOne(id)`, export, download, search, URL đoán ID và các API liên quan. Không nhầm “ẩn ở UI” hoặc “lọc một endpoint” với quyền truy cập tài nguyên tổng thể. Tập trung logic ACL/ownership/tenant vào một nơi kiểm thử được; khi có chính sách “được chia sẻ”, cần sửa cả lọc danh sách lẫn kiểm tra chi tiết.

### 8.3. Lọc đầu vào và ghi hàng loạt

`@PreFilter` có thể sửa dạng collection đầu vào hoặc tạo dạng dữ liệu đã lọc; kiểu dữ liệu hỗ trợ và khả năng thay đổi phụ thuộc triển khai. Spring Security hỗ trợ collection, array, map và stream còn mở. Với map, `filterObject` biểu thị entry, ví dụ `filterObject.value.owner()`. Không giả định mọi kiểu bao `List.of(...)` hay mọi wrapper immutable đều cho phép lọc tại chỗ; hãy dùng cấu trúc được hỗ trợ và viết test cho loại đầu vào/đầu ra thực tế.

Lọc đầu vào không chứng minh các phần tử còn lại an toàn cho mọi hành động: cần xác thực đầu vào, ranh giới tenant và quyền thao tác. Nếu client phải được báo phần tử nào bị bỏ, hãy thiết kế kết quả riêng (ID đã chấp nhận, ID bị từ chối, lý do) hoặc chọn từ chối toàn bộ, tránh trả “thành công” khi thực tế đã bỏ mục.

### 8.4. Thời điểm kiểm tra, proxy và side effect

- `@PreAuthorize` kiểm tra trước thân method; phương thức bị từ chối chưa thực thi. `@PostFilter` và `@PostAuthorize` đánh giá sau khi method hoàn tất nên truy vấn/side effect có thể đã xảy ra.
- Lời gọi nội bộ `this.someSecuredMethod()` cùng bean thường bỏ qua Spring AOP proxy, khiến method-level annotations không được áp dụng. Gọi qua bean proxy hoặc tái cấu trúc ranh giới service; không coi annotation là lớp bảo vệ duy nhất.
- Đảm bảo security context đúng khi chạy async/background; không giả định `authentication` của HTTP request tự truyền qua mọi thread.
- Thao tác từ chối cần tuân thủ nguyên tắc **deny by default** khi không xác định được quyền. Tránh bắt `AccessDeniedException` rồi âm thầm trả dữ liệu đầy đủ hoặc biến lỗi bảo mật thành danh sách rỗng mà không có chủ đích.
- HTTP 401/403/404 phụ thuộc xác thực, entry point, exception handling và chính sách chống enumeration; method security tự nó không quyết định mọi response code.

### 8.5. Hiệu năng và lớp dữ liệu

Lọc hậu kỳ tất cả bản ghi tốn chi phí tải DB, bộ nhớ, xử lý biểu thức theo phần tử và có thể kích hoạt N+1 query khi kiểm tra ACL lười. Dùng `@PostFilter` không có nghĩa là truy vấn DB đã được thêm `WHERE owner = ...`. Đối với lượng dữ liệu lớn, áp chính sách ở tầng truy vấn và bảo vệ thêm tại service là lựa chọn thường hiệu quả hơn.

## 9. Kiểm thử theo ma trận chính sách

Trong ứng dụng có `spring-security-test`, dùng `@WithMockUser` hoặc thiết lập `SecurityContext` phù hợp để gọi **Spring bean được proxy**, không khởi tạo service trực tiếp bằng `new` rồi tưởng annotation sẽ chạy.

| Bối cảnh kiểm thử | Kỳ vọng |
| --- | --- |
| Alice có `report:read`, danh sách gồm 2 báo cáo Alice + 1 Bob | `listVisibleReports` chỉ trả ID 1, 3 |
| Alice có `report:read`, chỉ có báo cáo của Bob | Trả danh sách rỗng |
| Alice có `report:read`, đọc ID 2 của Bob | `AccessDeniedException` (hoặc subtype thích hợp) |
| Alice thiếu `report:read` | Lời gọi danh sách bị từ chối trước khi xử lý |
| Alice thiếu `report:export:all` | `exportAll` bị từ chối toàn bộ |
| Người có `report:export:all` | `exportAll` trả đủ ba bản ghi |
| Cập nhật hàng loạt yêu cầu nguyên tử chứa một ID trái quyền | Toàn bộ yêu cầu bị từ chối, không có bản ghi nào bị ghi dở |
| Truy vấn phân trang và filter theo owner/tenant | Nội dung, số lượng và tổng trang nhất quán với phạm vi được phép |
| Gọi method được bảo vệ qua bean proxy so với tự gọi nội bộ | Test bảo đảm chặn quyền ở đường gọi thực tế |

Ví dụ test đơn vị tích hợp với Spring context (đặt trong ứng dụng có `@SpringBootApplication` phát hiện package `example.authz`):

~~~java
package example.authz;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class ReportServiceSecurityTest {
    @Autowired
    ReportService service;

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void filtersListAndDeniesAnotherOwnersReport() {
        List<Long> ids = service.listVisibleReports().stream()
                .map(Report::id).toList();
        assertEquals(List.of(1L, 3L), ids);
        assertThrows(AccessDeniedException.class, () -> service.readOne(2L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void deniesWholeExportWhenPermissionMissing() {
        assertThrows(AccessDeniedException.class, service::exportAll);
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:export:all")
    void privilegedExportKeepsAllItems() {
        assertEquals(3, service.exportAll().size());
    }
}
~~~

Các test này cần dependency `spring-boot-starter-test` và `spring-security-test` cùng Spring Boot application context. Ví dụ chưa cung cấp một ứng dụng khởi chạy độc lập; nó là tập file tích hợp vào dự án Spring Boot hiện có. Không dùng kỳ vọng “HTTP 403” trong unit test service: ở đây cần bắt ngoại lệ; status HTTP chỉ xuất hiện khi qua web/security filter chain và exception handler.

## 10. Quy tắc chọn nhanh trong tình huống thực tế

1. **Cần cho người dùng nhìn thấy đúng phần được phép?** Trả danh sách theo owner/ACL/tenant, thường lọc tại DB; `@PostFilter` có thể bổ trợ cho collection nhỏ.
2. **Một tài nguyên cụ thể hoặc một tính năng cần quyền bắt buộc?** Chặn bằng `@PreAuthorize` trước service; `@PostAuthorize` chỉ phù hợp cho đọc cần kiểm tra kết quả sau khi lấy.
3. **Khách gửi nhiều item, API cho phép thành công một phần?** Có thể `@PreFilter`, nhưng phải nói rõ hợp đồng và trả thông tin các item bị bỏ khi cần.
4. **Phép ghi/xuất cần tính đầy đủ hoặc nguyên tử?** Kiểm tra tất cả điều kiện và từ chối cả lời gọi nếu một phần tử không hợp lệ; dùng transaction/DB constraints cho tính nguyên tử và tránh race.
5. **Kết quả có phân trang, thống kê, nhiều tenant, hoặc số lượng lớn?** Đưa predicate quyền vào tầng truy vấn trước khi phân trang/tính tổng; kiểm tra mọi đường truy cập chéo.

**Tự kiểm tra:** Nếu Alice yêu cầu xóa đồng thời R1 (của Alice) và R2 (của Bob), việc `@PreFilter` bỏ R2 rồi xóa R1 có đúng không? **Chỉ đúng nếu API được thiết kế cho thành công một phần và thông báo rõ.** Nếu yêu cầu là “xóa cả hai hoặc không xóa gì”, phải từ chối cả thao tác, không xóa R1.

## Tài liệu đối chiếu

- Spring Security Reference – Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html (mục `@PreFilter`, `@PostFilter`, `@PreAuthorize`, `@PostAuthorize` và phương thức AOP).
