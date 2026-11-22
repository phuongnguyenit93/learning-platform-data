# Nguy cơ cập nhật một phần khi lọc dữ liệu của yêu cầu hàng loạt

## 1. Vấn đề cần hiểu

Trong Spring Security, phân quyền theo phương thức (method security) có thể kiểm tra quyền cho **từng phần tử** của một danh sách truyền vào service bằng `@PreFilter`. Cơ chế này hữu ích khi nghiệp vụ chủ động cho phép “chỉ xử lý những phần tử người dùng được phép”. Tuy nhiên, nếu API nhận **một yêu cầu cập nhật hàng loạt** và cam kết xử lý **toàn bộ hoặc không xử lý gì** (all-or-nothing), lọc âm thầm có thể tạo ra **cập nhật một phần**.

Ví dụ, người dùng gửi ba lệnh cập nhật tài liệu `[101, 102, 103]`, nhưng chỉ có quyền sửa `101` và `103`. Với lọc đầu vào:

- Dữ liệu gốc: `[101, 102, 103]`.
- Danh sách vào thân phương thức sau lọc: `[101, 103]`.
- Service cập nhật hai tài liệu này rồi trả về thành công.
- Tài liệu `102` không được cập nhật; người gọi có thể không biết yêu cầu đã bị rút bớt.

Đây là sự khác biệt giữa **“giao dịch thành công với danh sách đã lọc”** và **“toàn bộ yêu cầu ban đầu được thực hiện”**. Một giao dịch cơ sở dữ liệu có thể commit nguyên vẹn hai thay đổi `101`, `103` mà vẫn vi phạm cam kết nghiệp vụ của yêu cầu ba phần tử.

**Mục tiêu:** nhận diện chính xác rủi ro khi lọc dữ liệu ở tầng method security; chọn giữa chính sách từ chối toàn bộ hoặc thành công một phần có chủ đích; kiểm soát giao dịch, tính nhất quán và phản hồi API tương ứng.

## 2. `@PreFilter` hoạt động ra sao?

Để dùng các annotation như `@PreAuthorize`, `@PreFilter`, `@PostFilter`, ứng dụng cần bật method security, chẳng hạn:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

Hai annotation trong ví dụ trên thuộc Spring Framework (`org.springframework.context.annotation.Configuration`) và Spring Security (`org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity`).

Khi một lời gọi đi **qua Spring proxy** đến phương thức được quản lý bởi Spring:

1. Advice của `@PreFilter` xét từng phần tử của tham số được lọc; trong biểu thức SpEL, `filterObject` đại diện cho phần tử hiện tại.
2. Phần tử không thỏa điều kiện bị loại khỏi dữ liệu được chuyển vào phương thức. Với `Collection`, cần lưu ý khả năng hỗ trợ thao tác loại bỏ; truyền collection bất biến như `List.of(...)` có thể gây lỗi thao tác, tùy đường đi xử lý.
3. Thân phương thức nhận và xử lý các phần tử còn lại. `@PreFilter` tự nó **không yêu cầu từ chối cả lời gọi** chỉ vì một phần tử bị loại.

Ví dụ minh họa tích hợp trong một ứng dụng đã có `ChangeRequest`, repository và bean `documentPolicy`:

```java
@Service
class UnsafeBatchService {
    private final DocumentRepository repository;

    UnsafeBatchService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreFilter("@documentPolicy.canEdit(authentication, filterObject.id())")
    @Transactional
    public void updateAll(List<ChangeRequest> commands) {
        for (ChangeRequest command : commands) {
            repository.updateTitle(command.id(), command.title());
        }
    }
}
```

*Đây là đoạn tích hợp minh họa, chưa phải một file Java chạy độc lập:* `ChangeRequest`, `DocumentRepository` và `documentPolicy` là kiểu/bean do ứng dụng cung cấp. `documentPolicy.canEdit` phải kiểm tra quyền trên **dữ liệu đáng tin cậy từ server/database**, không tin trường “owner” do client tự khai. Nếu 1/3 phần tử bị lọc, vòng lặp chỉ cập nhật 2/3 phần tử; `@Transactional` không tự khôi phục phần tử đã bị loại.

Nếu có nhiều tham số kiểu collection, cần chỉ rõ tham số cần lọc bằng `filterTarget` và bảo đảm Spring nhận diện đúng tên tham số (ví dụ biên dịch với `-parameters` hoặc cơ chế khai báo tên phù hợp). Với một tham số collection duy nhất, thường có thể bỏ `filterTarget`.

**Phân biệt ba cơ chế:**

| Cơ chế | Thời điểm | Khi kiểm tra không thỏa | Ý nghĩa với bulk write |
| --- | --- | --- | --- |
| `@PreFilter` | Trước khi thân phương thức chạy | Loại phần tử không được phép khỏi tham số | Dễ phát sinh cập nhật một phần nếu service viết những phần tử còn lại |
| `@PreAuthorize` | Trước khi thân phương thức chạy | Từ chối **toàn bộ lời gọi**, thường ném `AccessDeniedException` | Phù hợp cho điều kiện “mọi mục đều được phép” nếu kiểm tra trên **yêu cầu gốc** |
| `@PostFilter` | Sau khi thân phương thức trả về | Lọc phần tử khỏi **kết quả trả về** | Chỉ thay đổi dữ liệu trả về; không hoàn tác các thao tác ghi đã xảy ra |

`@PostAuthorize` cũng kiểm tra sau khi phương thức chạy; không nên dùng kết quả kiểm tra sau ghi làm hàng rào phân quyền chính cho một bulk write. Đặc biệt, **lọc kết quả không tương đương rollback dữ liệu**.

Lưu ý nâng cao: khi phối hợp `@PreFilter` và `@PreAuthorize` trên cùng phương thức, đừng mặc định `@PreAuthorize` còn nhìn thấy danh sách ban đầu. Trong cấu hình advisor method security mặc định, pre-filter có thứ tự xử lý sớm hơn pre-authorize; việc kiểm tra số lượng hoặc quyền trên tham số có thể đang áp dụng cho **danh sách đã lọc**. Với nghiệp vụ all-or-nothing, tránh đặt `@PreFilter` trên cùng đường ghi đó.

## 3. Vì sao cập nhật một phần nguy hiểm?

### 3.1. Sai lệch hợp đồng API

Giả sử endpoint `PATCH /documents/bulk` nhận:

```json
{
  "changes": [
    {"id": 101, "title": "A1"},
    {"id": 102, "title": "B1"},
    {"id": 103, "title": "C1"}
  ]
}
```

Nếu API trả `200 OK` kèm thông điệp “Updated 3 documents” trong khi chỉ sửa `101` và `103` thì phản hồi sai thực tế. Ngay cả khi trả “Updated 2 documents”, API vẫn cần làm rõ mục bị từ chối và liệu thành công một phần có nằm trong hợp đồng hay không.

### 3.2. Phá vỡ ràng buộc nghiệp vụ

Một batch có thể biểu diễn một thao tác logic duy nhất: chuyển toàn bộ hóa đơn sang trạng thái mới, phân bổ hạn mức cho một nhóm, đóng một kỳ xử lý, hoặc cập nhật các mục có quan hệ phụ thuộc. Bỏ một mục có thể làm mất cân bằng hoặc để lại trạng thái trung gian không mong muốn.

### 3.3. Gây khó kiểm toán và thử lại

Danh sách trong log đầu vào có thể khác danh sách thực sự được ghi. Client thử lại toàn bộ request có thể ghi lặp những phần tử đã thành công; nếu thao tác không idempotent, hậu quả còn lớn hơn. Một bộ lọc chạy trước thân phương thức còn có thể làm mất dấu hiệu cho thấy mục nào bị từ chối nếu ứng dụng không lưu danh sách gốc.

### 3.4. Nhầm lẫn giữa quyền truy cập và tính nguyên tử

Phân quyền trả lời “ai được làm gì trên tài nguyên nào”; giao dịch trả lời “những thay đổi trong một phạm vi tài nguyên có cùng commit/rollback không”. Hai cơ chế giải quyết những câu hỏi khác nhau:

- `@PreFilter` chọn tập phần tử được xử lý.
- `@Transactional` bao bọc những thao tác ghi thực tế khi chạy qua transactional proxy và tài nguyên hỗ trợ giao dịch.
- Giao dịch **không biết** ba mục đã được client gửi nếu nó chỉ nhận hai mục sau lọc.

Vì vậy, gắn `@Transactional` lên phương thức có `@PreFilter` **không bảo đảm** “không cập nhật gì nếu một phần tử trong yêu cầu gốc bị cấm”.

## 4. Chọn rõ hai hợp đồng nghiệp vụ

### A. All-or-nothing: khuyến nghị cho một lệnh bulk mang tính nguyên tử

Quy tắc: **tất cả phần tử hợp lệ và được phép thì mới ghi; chỉ một phần tử không hợp lệ/không có quyền thì không ghi phần tử nào**.

Quy trình:

1. Nhận trọn yêu cầu gốc; kiểm tra null, danh sách rỗng, dữ liệu sai và ID trùng.
2. Kiểm tra quyền mức phương thức/vai trò, rồi **kiểm tra quyền đối tượng cho mọi ID** dựa trên bản ghi có thẩm quyền ở server.
3. Khi cần chống thay đổi đồng thời, đọc và khóa hoặc kiểm tra phiên bản trong cùng phạm vi giao dịch với thao tác ghi.
4. Nếu tồn tại mục thiếu, cấm hoặc sai trạng thái thì ném exception phù hợp **trước thao tác ghi đầu tiên**.
5. Chỉ sau khi tất cả mục vượt qua kiểm tra mới ghi; một lỗi giữa chừng phải khiến giao dịch rollback theo chính sách đã định.
6. Trả phản hồi thành công chỉ khi toàn bộ batch được áp dụng.

Có thể dùng `@PreAuthorize("@bulkPolicy.canEditAll(authentication, #p0)")` ở ranh giới service để **từ chối cả lời gọi** khi toàn bộ danh sách gốc không đạt chính sách. `#p0` là tham số đầu tiên, tránh phụ thuộc tên tham số. Nếu quyền phụ thuộc dữ liệu có thể thay đổi đồng thời, hãy kiểm tra lại dữ liệu/phiên bản trong giao dịch trước khi ghi: một precheck trước transaction không đủ loại bỏ cuộc đua thời gian (time-of-check/time-of-use).

### B. Partial success: chỉ khi sản phẩm chủ động cho phép

Quy tắc: từng phần tử là một thao tác độc lập; kết quả phải nêu rõ thành công, bị từ chối và lỗi nghiệp vụ **theo từng ID**. Thiết kế ranh giới transaction theo từng mục hoặc nhóm được phép; quy định cách retry/idempotency. Ví dụ phản hồi nghiệp vụ:

```json
{
  "requested": 3,
  "updated": [101, 103],
  "rejected": [
    {"id": 102, "reason": "NOT_AUTHORIZED"}
  ]
}
```

HTTP status và nội dung phản hồi phải theo hợp đồng đã công bố, không tự động suy ra mọi trường hợp partial success đều là `200` hay `207`. Tránh tiết lộ thông tin nhạy cảm về sự tồn tại/quyền sở hữu của tài nguyên trong thông báo lỗi. Nếu cần phân biệt “không tồn tại” và “không có quyền”, hãy cân nhắc yêu cầu bảo mật của API.

## 5. Thiết kế service an toàn cho all-or-nothing

Ví dụ sau dùng Java 17 và Spring Security method authorization. Đây là một **class có thể biên dịch khi đặt trong dự án Spring có các dependency tương ứng**; phần triển khai `DocumentStore` do dự án cung cấp. Điểm quyết định là `lockAndFindByIds` phải đọc/khóa các dòng có thẩm quyền trong chính transaction đang ghi.

Tệp `BatchDocumentService.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BatchDocumentService {

    public record ChangeRequest(long id, String title) {}

    public record DocumentSnapshot(long id, String ownerUsername) {}

    public interface DocumentStore {
        // Implementation: load authoritative rows with appropriate locking.
        List<DocumentSnapshot> lockAndFindByIds(List<Long> ids);

        // Implementation: perform a database update within the caller's transaction.
        void updateTitle(long id, String title);
    }

    private final DocumentStore store;

    public BatchDocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("hasAuthority('DOCUMENT_WRITE')")
    @Transactional
    public void updateAll(List<ChangeRequest> commands) {
        if (commands == null || commands.isEmpty()
                || commands.stream().anyMatch(c ->
                    c == null || c.id() <= 0
                    || c.title() == null || c.title().isBlank())) {
            throw new IllegalArgumentException("Invalid batch");
        }

        List<Long> ids = commands.stream()
                .map(ChangeRequest::id)
                .toList();

        if (new HashSet<>(ids).size() != ids.size()) {
            throw new IllegalArgumentException("Duplicate ID");
        }

        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        if (auth == null) {
            throw new AccessDeniedException("Authentication required");
        }

        Map<Long, DocumentSnapshot> byId = new HashMap<>();
        for (DocumentSnapshot document : store.lockAndFindByIds(ids)) {
            byId.put(document.id(), document);
        }

        boolean denied = ids.stream().anyMatch(id -> {
            DocumentSnapshot document = byId.get(id);
            return document == null
                    || !auth.getName().equals(document.ownerUsername());
        });
        if (denied) {
            throw new AccessDeniedException("Batch access denied");
        }

        // Only reached when ALL original items pass authorization.
        for (ChangeRequest command : commands) {
            store.updateTitle(command.id(), command.title());
        }
    }
}
```

Cách đọc ví dụ:

- `@PreAuthorize("hasAuthority('DOCUMENT_WRITE')")` chặn thiếu quyền tổng quát **trước khi** vào method. Quyền sở hữu từng đối tượng được xác nhận sau khi tải bản ghi đáng tin cậy trong transaction.
- Không dùng `@PreFilter`, nên `commands` giữ nguyên số phần tử client gửi; không có hành vi âm thầm loại mục.
- Xác thực danh sách và phát hiện ID trùng ngăn ghi hai lần cùng một tài nguyên do input bất thường.
- `lockAndFindByIds` là hợp đồng của tầng truy cập dữ liệu: adapter thật phải thực hiện khóa/đảm bảo phiên bản phù hợp với database và mức cách ly đã chọn; tên phương thức **không tự tạo khóa**.
- Điều kiện `document == null` từ chối cả batch nếu có ID không lấy được. `ownerUsername` lấy từ bản ghi server, tránh việc client giả mạo quyền sở hữu trong body.
- `AccessDeniedException` là exception không kiểm tra (runtime). Với transaction mặc định, exception này dẫn tới rollback. Trường hợp lỗi phát sinh sau một vài lần `updateTitle`, rollback sẽ hủy các thay đổi tham gia cùng transaction.
- Đoạn code cần một bean `DocumentStore` thật, hạ tầng transaction, cấu hình `@EnableMethodSecurity` và đường gọi thông qua proxy. Đây không phải ví dụ JDK thuần chạy bằng `javac` không classpath.

**Không hiểu nhầm ví dụ:** cơ chế khóa phải phù hợp database; một số nghiệp vụ cần optimistic locking (`@Version`/`If-Match`), xác minh trạng thái, tenant, hạn mức hoặc điều kiện chuyển trạng thái bên trong transaction trước khi ghi. Nếu một phép cập nhật có thể thất bại do ràng buộc DB, hãy để exception thoát ra hoặc cấu hình rollback rõ ràng, không bắt lỗi rồi trả thành công.

### Giới hạn của transaction cần tính đến

- `@Transactional` thường hoạt động qua Spring proxy; tự gọi phương thức được annotation từ một phương thức khác trong **cùng instance** có thể bỏ qua advice.
- Mặc định Spring rollback với `RuntimeException` và `Error`; exception checked không mặc định rollback (có thể cấu hình `rollbackFor`).
- Transaction DB không tự rollback email, HTTP request tới hệ thống ngoài, file đã ghi, message đã gửi hoặc side effect không cùng transactional resource. Dùng outbox/event sau commit, idempotency và cơ chế bù trừ khi thích hợp.
- Kiểm tra quyền ở điểm bắt đầu không thay thế kiểm tra trạng thái được đọc và sử dụng lúc ghi. Cần xử lý tình huống quyền, owner hoặc phiên bản tài nguyên đổi trong khi thực thi.
- Với batch lớn, cân nhắc chi phí khóa và timeout; nếu phải chia nhiều transaction, API không còn là một giao dịch DB nguyên tử duy nhất, cần nói rõ với client.

## 6. Chương trình Java 17 chạy độc lập: thấy sự khác biệt

Đoạn sau **mô phỏng kết quả lọc phần tử** mà không cần Spring; nó không tự kích hoạt `@PreFilter`. Nhờ đó ta quan sát rõ hai hợp đồng nghiệp vụ, còn code Spring ở trên là cách áp dụng vào service thật.

Lưu thành `BatchFilterRiskDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public class BatchFilterRiskDemo {
    record Change(long id, String newTitle) {}

    static final Set<Long> ALLOWED_IDS = Set.of(101L, 103L);
    static final List<Long> WRITTEN_IDS = new ArrayList<>();

    static void write(List<Change> commands) {
        for (Change command : commands) {
            WRITTEN_IDS.add(command.id());
        }
    }

    static void silentlyFilterThenWrite(List<Change> original) {
        List<Change> filtered = original.stream()
                .filter(c -> ALLOWED_IDS.contains(c.id()))
                .toList();
        write(filtered);
    }

    static void validateAllThenWrite(List<Change> original) {
        boolean denied = original.stream()
                .anyMatch(c -> !ALLOWED_IDS.contains(c.id()));
        if (denied) {
            throw new SecurityException("Denied: cancel entire batch");
        }
        write(original);
    }

    public static void main(String[] args) {
        List<Change> batch = List.of(
                new Change(101, "A1"),
                new Change(102, "B1"),
                new Change(103, "C1")
        );

        silentlyFilterThenWrite(batch);
        System.out.println("Filtered write: " + WRITTEN_IDS);

        WRITTEN_IDS.clear();
        try {
            validateAllThenWrite(batch);
        } catch (SecurityException ex) {
            System.out.println(ex.getMessage());
        }
        System.out.println("All-or-nothing write: " + WRITTEN_IDS);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac BatchFilterRiskDemo.java
java BatchFilterRiskDemo
```

Stdout chính xác:

```text
Filtered write: [101, 103]
Denied: cancel entire batch
All-or-nothing write: []
```

Trong mô phỏng, `WRITTEN_IDS` là bộ nhớ ghi nhận ID, **không phải database transaction**. Nó chứng minh khác biệt về tập đầu vào được xử lý; để chứng minh rollback thật cần integration test với transaction và database của ứng dụng.

## 7. Kiểm thử an toàn theo hợp đồng

Với lựa chọn **all-or-nothing**, nên có integration test gọi service qua Spring bean/proxy, xác minh dữ liệu DB trước và sau. Những trường hợp cốt lõi:

| Tình huống | Kết quả mong đợi | Dấu hiệu cần kiểm tra |
| --- | --- | --- |
| Tất cả ID tồn tại, đều được phép | Thành công toàn bộ | Số bản ghi ghi đúng bằng số mục gốc |
| Có một ID không được phép | Từ chối toàn bộ | **0** thay đổi DB, không chỉ “ít hơn” |
| Không ID nào được phép | Từ chối toàn bộ | **0** thay đổi |
| Một ID không tồn tại | Theo chính sách, thường từ chối toàn bộ | Không ghi các ID còn lại |
| ID trùng hoặc payload lỗi | Báo lỗi đầu vào | Không ghi hoặc ghi lặp |
| Vai trò chung hợp lệ nhưng quyền đối tượng thiếu | Từ chối toàn bộ | Kiểm tra quyền đối tượng thật sự chạy |
| Lỗi DB ở mục thứ hai sau khi mục đầu ghi | Rollback cả transaction | Mục đầu quay về trạng thái cũ |
| Chủ sở hữu/phiên bản thay đổi đồng thời | Phát hiện xung đột/khóa đúng chính sách | Không commit dựa trên trạng thái quyền đã lỗi thời |
| API được cấu hình partial success | Phản hồi tường minh từng ID | `requested = updated + rejected + failed` theo định nghĩa hợp đồng |

Cần test cả khi caller truyền `ArrayList` có thể thay đổi và collection bất biến, nhất là nếu lựa chọn `@PreFilter`. Test phải đi qua proxy; gọi trực tiếp `new Service(...)` sẽ không kiểm tra được method security advice. Với HTTP API, kiểm tra status, response và số bản ghi thực sự thay đổi; không chỉ assert exception.

## 8. Câu hỏi thường gặp và lỗi dễ mắc

**Hỏi: Có `@Transactional` là đủ chống cập nhật một phần chưa?** Không. Giao dịch chỉ bao trùm thao tác đã thực thi trong transaction. Nếu `@PreFilter` loại một phần trước khi service chạy, các phần tử ấy chưa từng được đưa vào phần ghi.

**Hỏi: Có thể ghép `@PreFilter` với `@PreAuthorize` để giữ all-or-nothing không?** Không nên dựa vào cách ghép đó mà không chứng minh thứ tự và danh sách được kiểm tra. Cách rõ nhất cho lệnh nguyên tử là giữ nguyên input và từ chối khi **bất kỳ** mục gốc nào không đủ quyền.

**Hỏi: `@PostFilter` có bảo vệ khỏi ghi dữ liệu trái phép không?** Không. Nó lọc kết quả trả về sau khi method chạy; với phương thức có side effect, việc che mục khỏi kết quả không xóa side effect.

**Hỏi: Kiểm tra trường `ownerId` từ request có đủ không?** Không. Quyền phải đối chiếu với tài nguyên/tenant/trạng thái đáng tin cậy phía server. Một client có thể sửa trường owner hoặc ID bất kỳ trong body.

**Hỏi: Khi nào `@PreFilter` là phù hợp?** Khi mục tiêu được công bố thật sự là **xử lý tập con được phép** (ví dụ tạo danh sách hiển thị hoặc tác vụ độc lập cho từng tài nguyên), và client/nghiệp vụ chấp nhận kết quả đó. Với bulk update, cần có hợp đồng partial success, báo cáo đầy đủ và chiến lược thử lại.

**Hỏi: Lỗi quyền trả mã HTTP nào?** Trong web flow Spring Security thường ánh xạ `AccessDeniedException` thành `403 Forbidden`; kết quả cụ thể còn phụ thuộc authentication, cấu hình exception handling và policy che giấu sự tồn tại tài nguyên. Lỗi validation hay xung đột trạng thái cần xử lý riêng theo API contract.

## 9. Checklist trước khi đưa bulk update vào production

- [ ] API đã định nghĩa rõ **all-or-nothing** hay **partial success**, bao gồm status và dữ liệu phản hồi.
- [ ] Quyền được tính cho **mọi phần tử trong yêu cầu gốc**, không chỉ phần tử còn lại sau filter.
- [ ] Không gắn `@PreFilter`/`@PostFilter` như cơ chế bảo vệ duy nhất cho các thao tác ghi nguyên tử.
- [ ] Có kiểm tra ID trùng, mục không tồn tại, dữ liệu không hợp lệ và các ràng buộc chéo giữa mục.
- [ ] Phân quyền từng đối tượng dựa trên dữ liệu đáng tin cậy; cân nhắc tenant và thay đổi đồng thời.
- [ ] Ranh giới transaction, rollback, locking/version và side effect bên ngoài đã được xác định.
- [ ] Tests xác minh **0 thay đổi** với batch bị từ chối, kể cả khi mục đầu tiên vốn được phép.
- [ ] Log/audit ghi lại yêu cầu, quyết định và kết quả theo cách tuân thủ giới hạn dữ liệu nhạy cảm.
- [ ] Retry/idempotency đã được quyết định khi có lỗi mạng hoặc trạng thái kết quả không rõ.

**Nguyên tắc ghi nhớ:** `@PreFilter` diễn đạt **“chỉ đưa các mục đạt điều kiện vào phương thức”**; `@PreAuthorize` diễn đạt **“lời gọi này có được phép tiếp tục không?”**. Đối với bulk update nguyên tử, phải kiểm tra **toàn bộ yêu cầu ban đầu** và kiểm soát **toàn bộ thao tác ghi** trong transaction phù hợp.

### Tài liệu tham khảo

- [Spring Security — Method Security, `@PreFilter`, `@PostFilter`, `@PreAuthorize`](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework — Declarative transaction rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — `@Transactional` annotation settings](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
