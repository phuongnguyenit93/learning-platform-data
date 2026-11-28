# Phân trang để kiểm soát bộ nhớ và tải máy chủ

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập dịch vụ thư mục LDAP thông qua Spring Data LDAP repository hoặc `LdapTemplate`, ánh xạ entry phân cấp theo DN (*Distinguished Name*) và các thuộc tính tuân theo `objectClass`/schema thành đối tượng Java. Khi tìm một tài khoản theo `uid`, số kết quả thường nhỏ. Nhưng đồng bộ toàn bộ danh bạ, xuất dữ liệu, kiểm tra hàng chục nghìn người dùng hoặc duyệt các nhóm lớn có thể tạo truy vấn trả về rất nhiều entry.

Nếu ứng dụng gọi một phép tìm kiếm rộng rồi giữ toàn bộ `List<Person>` trong bộ nhớ, heap, thời gian xử lý, network và LDAP server đều có thể bị ảnh hưởng. **Server-side paging** cho phép lấy một lượng kết quả có kiểm soát qua từng lần LDAP search, xử lý xong một đợt rồi tiếp tục bằng *cookie*. Đây là cơ chế khác với `Pageable`/`PageRequest` của Spring Data cho SQL.

Mục tiêu của bài:

- Phân biệt `size limit`, `time limit`, phân trang ở client và **LDAP Simple Paged Results** theo RFC 2696.
- Biết vai trò của `PagedResultsControl`, `cookie`, cùng một `LdapContext` và giới hạn của server.
- Dùng Spring LDAP `DirContextProcessor` với `SingleContextSource` để duyệt dữ liệu từng trang.
- Giữ bộ nhớ gần theo kích thước **một trang**, thay vì tích lũy toàn bộ dữ liệu.
- Tối ưu filter, search base, projection thuộc tính, concurrency và kích thước trang.
- Hiểu tính nhất quán khi directory thay đổi, xử lý lỗi/khôi phục, quan sát và kiểm thử tải.

## 1. Khi không phân trang, vấn đề nằm ở đâu?

Giả sử directory có 100.000 entry `inetOrgPerson` dưới `ou=people,dc=example,dc=org`. Một lời gọi tìm kiếm:

```java
List<PersonSummary> people =
        ldapTemplate.search(
                "ou=people",
                "(objectClass=inetOrgPerson)",
                attrs -> new PersonSummary(
                        (String) attrs.get("uid").get(),
                        (String) attrs.get("cn").get(),
                        attrs.get("mail") == null
                                ? null
                                : (String) attrs.get("mail").get()));
```

có thể khiến ứng dụng cố gắng vật hóa một danh sách lớn, hoặc thất bại sớm do giới hạn kích thước/thời gian của directory. Ví dụ code này **chỉ minh họa rủi ro**, chưa đủ xử lý trường bắt buộc, đa trị và ngoại lệ.

```text
Không phân trang
Ứng dụng                                   LDAP server
    | -- search toàn bộ ou=people ------------> |
    | <----------- hàng loạt entry ------------ |
    |
    +-- List có thể rất lớn
    +-- Mapping/GC tăng
    +-- Kết nối và thời gian truy vấn kéo dài
    +-- Dễ vượt sizeLimit/read timeout
```

Chỉ thêm `countLimit(100)` hoặc `SearchControls.setCountLimit(100)` **không tạo ra cơ chế lấy 100 entry tiếp theo**. Nó giới hạn số entry mà lời tìm kiếm có thể trả về, nhưng không cung cấp một con trỏ để đọc phần còn lại.

So sánh:

| Chiến lược | Cách hoạt động | Có lấy tiếp sau trang đầu? | Điểm cần lưu ý |
|---|---|---|---|
| Search toàn bộ | Một phép tìm kiếm yêu cầu tất cả entry khớp | Không cần nếu có đủ kết quả | Có nguy cơ tốn bộ nhớ và bị server giới hạn |
| Client-side paging | Tải danh sách lớn, sau đó cắt thành các đoạn | Có, **nhưng đã tải toàn bộ** | Không giảm peak memory của phép tìm kiếm |
| `countLimit(100)` | Yêu cầu giới hạn số kết quả | **Không** có cơ chế tiếp tục | Khác với phân trang |
| **LDAP Simple Paged Results** | Mỗi search nhận một đợt + cookie | **Có**, nếu server hỗ trợ và cookie còn hợp lệ | Cần cùng phiên/kết nối và tuân thủ quy tắc RFC 2696 |
| `PageRequest.of(0, 100)` | Abstraction phân trang thường thấy ở JPA | **Không mặc định** với Spring Data LDAP repository | Đừng suy luận từ interface generic |

**Chú ý:** phân trang không tự làm tổng số entry cần xử lý giảm. Nếu cuối cùng vẫn thu toàn bộ các trang vào một `ArrayList`, peak heap sau cùng vẫn có thể tương đương một phép tải toàn bộ.

## 2. LDAP Simple Paged Results theo RFC 2696

LDAPv3 hỗ trợ **request/response controls** để mở rộng hành vi của thao tác. RFC 2696 mô tả control để nhận kết quả search thành nhiều đợt.

- **Control OID:** `1.2.840.113556.1.4.319`.
- **Request** chứa `size` (số entry mong muốn trong một trang) và `cookie` (chuỗi byte từ server).
- **Response** chứa `size` (ước lượng tổng số kết quả nếu server cung cấp) và `cookie` để lấy tiếp.
- **Cookie rỗng** ở response nghĩa là server không còn trang tiếp theo.

Minh họa với page size 3:

```text
Client                                             LDAP server
  | -- Search(filter, pageSize=3, cookie=empty) ----> |
  | <--- [Lan, Binh, Hoa], cookie=C1 ---------------- |
  | -- Search(same query, pageSize=3, cookie=C1) ---> |
  | <--- [Minh, An, Ha], cookie=C2 ------------------ |
  | -- Search(same query, pageSize=3, cookie=C2) ---> |
  | <--- [Mai], cookie=empty ----------------------- |
  |            Kết thúc duyệt                        |
```

Cookie là **dữ liệu opaque do server tạo**. Không đoán cấu trúc, không giải mã để lấy offset, không tự tăng số trang và không tạo cookie giả. Theo RFC 2696, lần tiếp tục phải giữ các tham số tìm kiếm như yêu cầu đầu (ngoại trừ message ID, cookie và có thể page size); dùng **cookie mới nhất**, không dùng lại cookie cũ hoặc cookie đã hoàn tất.

Một số hệ quả quan trọng:

1. **Không phải SQL `OFFSET/LIMIT`.** Không thể nhảy ngay tới “trang số 50” nếu không có chuỗi cookie hoặc cơ chế khác.
2. **Không có snapshot nhất quán mặc định.** Nếu entry được thêm/xóa/sửa trong lúc duyệt, RFC 2696 cho phép kết quả có thể bị lặp hoặc bỏ sót tùy thay đổi của tập kết quả.
3. **Ước lượng tổng số** không phải luôn có, không nhất thiết chính xác. Server có thể trả `0` khi không biết tổng.
4. **Cookie có vòng đời giới hạn.** Server có thể hết thời gian lưu trạng thái, giới hạn phiên, chuyển node hoặc kết thúc cursor.
5. **Server phải hỗ trợ control**. Nếu client gửi control bắt buộc (*critical*) mà server không hiểu, phép tìm kiếm phải thất bại thay vì âm thầm bỏ qua.

Thông thường không nên cung cấp trực tiếp cookie RFC 2696 cho HTTP client như một **cursor bền vững** qua nhiều request cách xa nhau. Cookie có thể phụ thuộc đúng kết nối/phiên và trạng thái của server; không mặc định tái dùng được sau khi ứng dụng đóng connection, đổi LDAP server, restart hay failover.

## 3. Điều kiện để phân trang hoạt động

Trước khi viết code:

| Điều kiện | Cách kiểm tra |
|---|---|
| Server hỗ trợ RFC 2696 | Tra `supportedControl` của root DSE hoặc kiểm thử request control trên server đích |
| Kết nối LDAPv3 có hỗ trợ controls | Sử dụng `LdapContextSource`/`LdapContext` thay vì một `DirContext` không hỗ trợ controls |
| Các trang thuộc cùng một search sequence | Giữ base DN, scope, filter, danh sách thuộc tính và các thông số liên quan nhất quán |
| Giữ đúng kết nối | Sử dụng `SingleContextSource` hoặc cơ chế Spring LDAP duy trì context cho toàn chuỗi |
| Page size hợp lệ | Chọn số dương và cân nhắc server size limit cùng giới hạn tài nguyên |
| Người dùng bind có quyền đọc | Kiểm tra ACL; thiếu quyền có thể làm kết quả khác dự kiến |
| Search có giới hạn và mục đích rõ | Chọn base/filter hẹp, thuộc tính trả về cần thiết và budget cho batch |

Nếu server **bỏ qua** một paging control không critical, client có thể nhận một lượng kết quả lớn ở lần gọi đầu. Vì vậy, với yêu cầu bắt buộc giới hạn tải, phải xác nhận server thực sự trả **paged-results response control** và xử lý rõ ràng trường hợp không hỗ trợ; không chỉ dựa vào việc truyền tham số page size.

**Tính toán bộ nhớ:** nếu mỗi trang có `P` entry và mỗi DTO đã ánh xạ dùng khoảng `S` byte, dữ liệu trang cần chỗ chứa khoảng `O(P × S)`, cộng overhead của JNDI, mapper và callback. Đây là ước lượng định tính, không phải giới hạn cứng; server có thể trả các giá trị thuộc tính lớn và mapper có thể tạo thêm đối tượng.

## 4. Chọn API Spring LDAP theo phiên bản

Spring LDAP cung cấp `DirContextProcessor` để gắn request controls trước search và đọc response controls sau search.

| Spring LDAP | API liên quan | Lưu ý |
|---|---|---|
| **4.1+** | `PagedResultsControlExchangeDirContextProcessor` | API mới, constructor nhận page size; có `hasMore()` |
| Các bản **3.x/4.0** | `PagedResultsDirContextProcessor` | Hỗ trợ `hasMore()`, `getCookie()`; bị đánh dấu deprecated ở bản 4.1+ |
| JNDI thuần | `javax.naming.ldap.PagedResultsControl` và `PagedResultsResponseControl` | Tự quản lý `LdapContext`, response controls và cookie |

Trong tài liệu hiện hành, ví dụ ở bài này dùng API **Spring LDAP 4.1+**. Nếu module của bạn đang dùng 3.x hoặc 4.0, cần đổi sang `PagedResultsDirContextProcessor` **và kiểm tra API cụ thể**; không thể chỉ copy import của bản 4.1+ vào bản cũ.

Quan trọng hơn tên class là **quy tắc cùng một kết nối**. `LdapTemplate` thường nhận context, thực hiện search rồi trả/đóng context sau mỗi thao tác. Một chuỗi paged search phải dùng lại đúng kết nối, nên cần `SingleContextSource.doWithSingleContext(...)` như tài liệu Spring LDAP đề xuất.

## 5. Ví dụ Java: duyệt từng trang nhưng không tích lũy cả directory

Giả sử cấu hình `LdapContextSource.base` là `dc=example,dc=org`; cần duyệt các entry người dùng dưới `ou=people` và gửi từng DTO sang một bộ xử lý dữ liệu.

### 5.1. DTO gọn

**`PersonSummary.java`**

```java
package com.example.directory;

public record PersonSummary(
        String uid,
        String fullName,
        String email
) {}
```

DTO không chứa toàn bộ `Attributes` để tránh mang theo các giá trị không dùng đến. Nếu nghiệp vụ cần DN, chọn mapper có thông tin context/DN thay cho mapper chỉ có `Attributes`, đồng thời quy định DN tương đối hay đầy đủ.

### 5.2. Scanner xử lý từng đợt

**`PagedPersonScanner.java` — ví dụ với Spring LDAP 4.1+ và Java 17+**

```java
package com.example.directory;

import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;

import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.InvalidAttributeValueException;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.LdapOperationsCallback;
import org.springframework.ldap.core.support.SingleContextSource;
import org.springframework.stereotype.Service;

@Service
public class PagedPersonScanner {

    private static final int PAGE_SIZE = 100;
    private static final int MAX_PAGES = 200;
    private final ContextSource contextSource;

    public PagedPersonScanner(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public int scan(Consumer<PersonSummary> sink) {
        Objects.requireNonNull(sink, "sink");

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(
                new String[] {"uid", "cn", "mail"});
        // Không đặt countLimit nhỏ hơn page size rồi mong đọc đủ.
        controls.setCountLimit(0);
        controls.setTimeLimit(3_000);

        AttributesMapper<PersonSummary> mapper = attrs ->
                new PersonSummary(
                        required(attrs, "uid"),
                        required(attrs, "cn"),
                        optional(attrs, "mail"));

        var processor =
                new PagedResultsControlExchangeDirContextProcessor(PAGE_SIZE);

        return SingleContextSource.doWithSingleContext(
                contextSource,
                (LdapOperationsCallback<Integer>) operations -> {
                    int seen = 0;
                    int pages = 0;

                    do {
                        if (pages >= MAX_PAGES) {
                            throw new IllegalStateException(
                                    "Vượt giới hạn trang, batch chưa hoàn tất");
                        }

                        List<PersonSummary> batch = operations.search(
                                "ou=people",
                                "(&(objectClass=inetOrgPerson)(uid=*))",
                                controls,
                                mapper,
                                processor);
                        pages++;

                        // Xử lý NGAY từng entry. Không giữ danh sách mọi trang.
                        for (PersonSummary person : batch) {
                            sink.accept(person);
                            seen++;
                        }
                        // Sang vòng sau, batch cũ không được lưu trong scanner.
                    } while (processor.hasMore());

                    return seen;
                },
                true,   // Dùng read-only context.
                false,  // Không im lặng bỏ qua PartialResultException.
                false); // Không im lặng bỏ qua NameNotFoundException.
    }

    private static String required(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        if (attr == null || attr.size() == 0) {
            throw new InvalidAttributeValueException(
                    "Thiếu thuộc tính bắt buộc: " + name);
        }
        return (String) attr.get();
    }

    private static String optional(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        return attr == null || attr.size() == 0
                ? null : (String) attr.get();
    }
}
```

Các phần đáng chú ý:

1. `PAGE_SIZE=100` là **số entry mong muốn mỗi lần gọi**, không phải tổng giới hạn của toàn bộ scan. Đây là số minh họa cần đo và hiệu chỉnh.
2. `MAX_PAGES` ngăn job kéo dài ngoài dự định; khi chạm giới hạn, code **báo batch chưa hoàn tất**, không im lặng tuyên bố dữ liệu đã được đồng bộ hết.
3. `SearchControls` đặt `SUBTREE` và chỉ yêu cầu `uid`, `cn`, `mail`. Tránh trả ảnh, chứng chỉ hoặc thuộc tính đa trị khổng lồ nếu không cần.
4. `controls.setCountLimit(0)` tránh xung đột với giới hạn phía client; vẫn có thể gặp **administrative size limit** hoặc time limit phía server.
5. Bộ lọc trong ví dụ là **chuỗi cố định**, không nối input người dùng. Với filter động, phải dùng `LdapQueryBuilder` hoặc `Filter` builder của Spring LDAP để escape đúng RFC 4515.
6. `processor.hasMore()` dùng trạng thái cookie mà processor nhận từ response; không tự tính số trang bằng phép chia hay đoán từ kích thước batch.
7. `SingleContextSource` bảo đảm chuỗi lời gọi dùng **cùng kết nối**. Trong overload được dùng, `true` chọn read-only context; overload ngắn hơn mặc định có thể mượn read-write context.
8. `sink.accept(person)` cần xử lý đồng bộ và không giữ các DTO mãi. Nếu sink gom tất cả vào một `List`, lợi ích tiết kiệm heap sẽ mất đi.

Trong code thật, xử lý thêm giới hạn tổng thời gian/entry và kế hoạch khôi phục batch. Ví dụ này tập trung vào nguyên lý **paging + bounded memory**, không triển khai hàng đợi phân tán, retry hay transaction liên LDAP và hệ thống đích.

### 5.3. Cách sử dụng scanner

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger processed = new AtomicInteger();

int fetched = scanner.scan(person -> {
    // Thực tế: ghi từng item hoặc từng batch nhỏ vào đích,
    // có chiến lược idempotency và backpressure.
    processed.incrementAndGet();
});

System.out.println("Entries fetched: " + fetched);
```

`processed` không phải số entry được commit thành công ở hệ thống đích nếu `sink` có lỗi hoặc lưu không đồng bộ. Phải phân biệt **đã nhận từ LDAP**, **đã xử lý**, **đã xác nhận lưu**, và **batch hoàn tất**.

**Một cảnh báo vận hành:** `SingleContextSource` giữ kết nối cho toàn bộ callback. Nếu sink tốn nhiều thời gian (gọi API chậm, gửi mạng hay chờ người dùng), một kết nối có thể bị chiếm quá lâu, gây áp lực cho LDAP pool và server. Trong job thực, nên dùng pipeline có backpressure và giới hạn xử lý; không coi duyệt phân trang là lý do hợp lệ để giữ kết nối vô hạn.

## 6. Phiên bản Spring LDAP cũ hơn: khác class, cùng nguyên tắc

Với Spring LDAP 3.x/4.0, mã cốt lõi thường dùng:

```java
import org.springframework.ldap.control.PagedResultsDirContextProcessor;

PagedResultsDirContextProcessor processor =
        new PagedResultsDirContextProcessor(100);

// Giữ nguyên một SingleContextSource hoặc transaction-aware context:
// operations.search(..., mapper, processor);
// while (processor.hasMore()) { ... }
```

Ở API cũ:

- `PagedResultsDirContextProcessor.getCookie()` cung cấp wrapper `PagedResultsCookie`.
- `getResultSize()` là **ước lượng** nếu server cung cấp, không nên dùng làm tổng bắt buộc.
- Ở Spring LDAP 4.1+, class này bị đánh dấu **deprecated** để ưu tiên `PagedResultsControlExchangeDirContextProcessor`. Không thay thế bằng constructor hoặc method tự nghĩ ra; xem tài liệu đúng phiên bản trước khi nâng cấp.

Với 4.1+, processor mới tự quản lý control exchange trong một chuỗi gọi; bạn không cần parse hoặc ghi cookie ra database trong ví dụ duyệt đồng bộ.

## 7. Tại sao một kết nối là yêu cầu quan trọng?

Một câu hỏi thường gặp: “Tại sao không gọi `ldapTemplate.search` lần thứ nhất, đóng context rồi lấy trang 2 bằng một context mới từ pool?”

```text
Lần 1: connection A -> page 1 + cookie C1
Lần 2: connection B -> page 2 với cookie C1
                         |
                         +-- Có thể fail: cookie không hợp lệ/không còn state
```

RFC 2696 để cookie do server quản lý. Spring LDAP yêu cầu giữ **cùng underlying connection** giữa các trang. Pool chỉ đảm bảo bạn có thể mượn một context khác, không đảm bảo đó là connection A. Đóng trả context sau từng trang rồi mượn lại từ pool **không phải** phương pháp duy trì phiên paging an toàn.

Hai hướng được tài liệu Spring LDAP đề cập:

- `SingleContextSource.doWithSingleContext(...)`: giữ cùng context cho toàn bộ callback, hợp cho một batch duyệt liên tiếp.
- `ContextSourceTransactionManager` kết hợp `TransactionAwareContextSourceProxy`: cho các thao tác dùng cùng connection trong phạm vi transaction/scope được cấu hình thích hợp. **Không** suy ra từ đó LDAP đã có ACID transaction cho nhiều entry.

Nếu dùng `PooledContextSource`/Commons Pool, phải kiểm tra khả năng sử dụng LDAP request controls trên context proxy. Một số thao tác có trạng thái cần `MutablePooledContextSource` hoặc cấu hình riêng. Tuy nhiên, ngay cả khi pooling hỗ trợ controls, **giữ nguyên context qua từng trang** vẫn là yêu cầu của paging.

Không đồng thời dùng chung một `LdapContext` hoặc processor cho hai người dùng hoặc hai job ở nhiều thread: JNDI context/control có trạng thái; một chuỗi paging cần sở hữu riêng logic, filter và cookie.

## 8. Phân trang không đồng nghĩa với kết quả nhất quán

Trong lúc một job duyệt directory, admin có thể sửa DN, thay thuộc tính, thêm hoặc xóa entry:

```text
T0: Page 1 -> uid=lan, uid=binh
T1: Admin đổi DN, thêm uid=an, xóa uid=hoa
T2: Page 2 -> tập kết quả đã thay đổi
```

RFC 2696 **không hứa** snapshot isolation. Khi tập kết quả thay đổi sau request đầu, entry có thể bị trả lặp hoặc bị bỏ sót. Cũng không có thứ tự ổn định được bảo đảm nếu server không hỗ trợ/cấu hình server-side sorting theo quy tắc riêng.

Với bài toán đồng bộ:

| Yêu cầu | Chiến lược bổ sung |
|---|---|
| Hiển thị một đoạn danh bạ gần đúng | Duyệt trang liên tiếp, báo rõ dữ liệu có thể thay đổi |
| Batch định kỳ có thể chạy lại | Dùng **upsert idempotent** theo identity ổn định và đối soát |
| Không được bỏ sót thay đổi | Dùng cơ chế thay đổi/incremental sync đặc thù server (`DirSync`, changelog, persistent search...) và checkpoint |
| Xuất snapshot nhất quán tuyệt đối | Cần hỗ trợ snapshot/consistency của backend hoặc cửa sổ dữ liệu có kiểm soát; paging thông thường không đủ |
| Cần thứ tự duy nhất giữa các trang | Kiểm tra server-side sort control + khóa ổn định, và thử nghiệm tương thích với paging |

Các định danh như `entryUUID` hoặc `objectGUID` tùy LDAP server có thể giúp idempotent upsert; chúng không tự cung cấp snapshot. Không dùng `uid` làm khóa toàn cục nếu có nhiều tenant/domain hoặc khả năng đổi login.

Cookie không phải “vị trí vĩnh viễn”. Sau lỗi kết nối hoặc server restart, nhiều hệ thống phải **bắt đầu lại một scan mới** rồi dựa trên idempotency/reconciliation để bảo đảm kết quả cuối.

## 9. Ưu tiên thu hẹp truy vấn và dữ liệu trả về

**Phân trang không sửa được một truy vấn LDAP kém chọn lọc.** Trước khi chọn page size:

1. **Chọn search base hẹp.** `ou=people` thường tốt hơn tìm toàn `dc=example,dc=org` nếu nghiệp vụ chỉ liên quan người dùng.
2. **Chọn scope đúng.** `ONELEVEL` nếu chỉ cần entry con trực tiếp; `SUBTREE` khi thực sự cần toàn nhánh.
3. **Xây filter chọn lọc, đúng schema.** Tránh `(objectClass=*)` hoặc substring `(cn=*a*)` trên toàn cây chỉ để phục vụ màn hình nhỏ.
4. **Chỉ trả thuộc tính cần thiết** bằng `SearchControls.setReturningAttributes(...)` hoặc `LdapQueryBuilder.attributes(...)`.
5. **Kiểm tra index và matching rule** trên directory. Filter đúng cú pháp nhưng không có index vẫn có thể đắt.
6. **Dùng server/page/total timeouts** hợp lý; timeouts cần phân biệt với `pageSize`.
7. **Giới hạn số job đồng thời** trên mỗi LDAP server/replica để tránh nhân đôi tải.

Ví dụ, khi chỉ cần tên và email:

```java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
controls.setReturningAttributes(new String[] {"uid", "cn", "mail"});

// Chỉ yêu cầu ba thuộc tính, nhưng vẫn phải có filter đúng nhu cầu.
```

Thuộc tính `objectClass` có thể nằm trong filter nhưng không cần nằm trong returning attributes nếu DTO không sử dụng nó. Một entry có thể không có `mail` hoặc bị ACL che; mapper phải xử lý trường tùy chọn thay vì giả định mọi entry có đủ dữ liệu.

**Lưu ý về giá trị lớn:** LDAP attribute có thể đa trị hoặc chứa binary, ví dụ `jpegPhoto` hoặc chứng chỉ. Page size 100 **không bảo đảm** bộ nhớ nhỏ nếu mỗi entry có payload rất lớn. Projection và giới hạn dữ liệu vẫn là bước quan trọng.

## 10. Chọn page size theo dữ liệu đo được

Không có một page size tối ưu cho mọi LDAP server. Page quá nhỏ tăng số lượt network round-trip và overhead server; page quá lớn tăng peak heap, kích thước response và thời gian giữ tài nguyên.

Giả sử có `N` entry:

```text
Số request lý thuyết xấp xỉ ceil(N / pageSize)

N = 10.000
pageSize = 100  -> khoảng 100 trang
pageSize = 500  -> khoảng 20 trang
pageSize = 1000 -> khoảng 10 trang
```

Đây là phép đếm xấp xỉ; không nói lên thời gian thực tế vì mỗi page có chi phí khác nhau, server có size limit và có thể thay đổi tập kết quả giữa các trang.

| Page size | Điểm mạnh | Rủi ro |
|---|---|---|
| 20–50 | Từng đợt nhỏ, thuận lợi khi mỗi entry lớn | Nhiều round-trip và cookie state lâu hơn |
| 100–200 | Điểm bắt đầu thử nghiệm cho nhiều workload vừa | Chưa chắc phù hợp với index/latency/server quota |
| 500–1000 | Ít round-trip hơn nếu entry nhỏ và server khỏe | Peak memory/latency mỗi trang lớn hơn |
| Rất lớn | Giảm số đợt lý thuyết | Có thể gần như tải toàn bộ; mất lợi ích pacing |

Các khoảng số trên chỉ là **kịch bản để benchmark**, không phải giá trị cấu hình mặc định của Spring LDAP hay khuyến nghị phổ quát. Hãy thử với dữ liệu và giới hạn directory thực tế; một số backend có ngưỡng paging riêng.

Các chỉ số nên đo:

- p50/p95/p99 **latency từng trang** và latency toàn batch.
- `page_size_requested` so với `entries_returned_per_page`.
- Heap allocation, GC pause, peak RSS và số DTO giữ lại.
- Tổng entry đã nhận, đã xử lý, đã commit; số page và tỷ lệ hoàn tất.
- LDAP server CPU, search index efficiency, active connections và số paged-search cursor.
- Timeout, cookie invalid/expired, referrals và rate limit/administrative limit.
- Số worker scan đồng thời và thời gian mỗi worker giữ context.

Nếu page size tăng làm throughput cao hơn nhưng p99 latency, heap hoặc LDAP server CPU vượt mức cho phép, chọn giá trị thấp hơn. Mục tiêu không phải “lấy trang lớn nhất”, mà là **thông lượng ổn định với tải và bộ nhớ dự đoán được**.

## 11. Budget tổng: giới hạn trang, thời gian và độ song song

Một `read.timeout` trên từng lời gọi LDAP không giới hạn thời gian của **toàn bộ** scan nếu có hàng trăm trang. Cần budget độc lập ở tầng job:

```text
Job budget:
  pageSize            = 100
  maxPages            = 200
  maxTotalDuration    = 60 seconds
  maxConcurrentScans  = 2 per directory instance
  perPageReadTimeout  = 3 seconds
```

Đây là ví dụ giới hạn nghiệp vụ, không phải các thuộc tính Spring LDAP tự động có sẵn. Khi hết budget:

1. Ghi trạng thái **INCOMPLETE**, không ghi `SUCCESS`.
2. Không trả cho client một số tổng như thể đã đọc hết directory.
3. Dừng nhận thêm trang ở điểm an toàn; nếu còn cookie, cân nhắc hủy chuỗi paging theo RFC 2696.
4. Giải phóng connection/context, xử lý timeout và dọn phần dữ liệu đích chưa commit.
5. Khi retry, quyết định chạy lại từ đầu hay dùng cơ chế checkpoint đáng tin **khác** cookie tùy thời gian sống/khả năng backend.

RFC 2696 có cách **abandon paging sequence** bằng request control với page size bằng 0 và cookie mới nhất; `LDAP Abandon` thuần không được khuyến nghị để kết thúc nguyên một chuỗi paging. Ví dụ scanner ở mục 5 dùng giới hạn và giải phóng context khi kết thúc/ngoại lệ; trong production, nếu chủ động cắt ngang một paging sequence còn cookie, hãy bổ sung cơ chế hủy control phù hợp với API Spring LDAP/JNDI và server đang dùng, thay vì mặc định server lập tức dọn state.

Nếu một LDAP server giữ cursor state quá lâu do nhiều job bị ngắt, tài nguyên server có thể cạn dù ứng dụng không dùng hết heap. Cần theo dõi **cursor/session quota** phía directory.

## 12. Không coi LDAP cookie là cursor HTTP bền vững

Một UI HTTP thường muốn:

```text
GET /people?page=1
GET /people?page=2
GET /people?page=20
```

LDAP RFC 2696 không phải offset paging của cơ sở dữ liệu quan hệ. Request tiếp theo có thể đến server ứng dụng khác, lấy LDAP connection khác hoặc sau khi cookie đã hết hạn. Vì vậy:

- Không mặc định ánh xạ `PageRequest.of(19, 20)` thành “LDAP page 20”.
- Không lưu một cookie RFC 2696 lâu dài rồi dùng sau restart/failover mà không có hợp đồng xác nhận từ directory.
- Không phát tán cookie thô cho người dùng không tin cậy; nó có thể gắn với trạng thái tìm kiếm và điều kiện truy cập.
- Không sử dụng cookie của filter/base/credential này cho một filter/base/credential khác.
- Không dùng việc client yêu cầu trang tiếp theo làm cơ chế khống chế quyền truy cập; LDAP ACL và authorization của API vẫn cần độc lập.

Thiết kế phù hợp hơn tùy mục tiêu:

| Use case | Thiết kế cân nhắc |
|---|---|
| **Batch export/sync** | Một scanner duyệt liên tục trên cùng context, xử lý từng trang và kiểm soát thời gian |
| **UI danh sách nhỏ** | Filter chọn lọc, truy vấn có size limit phù hợp; không tải cả directory |
| **UI có next/previous giữa nhiều HTTP request** | Xây service cursor session có lifetime/ngữ cảnh được quản lý hoặc giải pháp phân trang khác được server hỗ trợ |
| **Duyệt dữ liệu rất lớn, cần resume bền vững** | Checkpoint theo stable key/change feed của directory đã kiểm chứng, không mặc định dựa cookie |
| **Sắp xếp xác định** | Dùng server-side sort/VLV khi server hỗ trợ, kiểm tra tương tác với paging và yêu cầu consistency |

Một số LDAP backend cung cấp Virtual List View (VLV), server-side sort (RFC 2891), DirSync hoặc cơ chế đồng bộ riêng. Những tính năng này không tự động có từ `LdapRepository` và **không nên** được coi là tương đương RFC 2696.

## 13. Kiểm thử tích hợp và kiểm thử tải

### 13.1. Dữ liệu và môi trường thử nghiệm

Chuẩn bị LDAP test directory chứa `dc=example,dc=org`, container `ou=people` và ít nhất 5 user với `inetOrgPerson`, `uid`, `cn`, `sn`, `mail`. Cấu hình:

```yaml
spring:
  ldap:
    urls: ldaps://ldap-test.example.org:636
    base: dc=example,dc=org
    username: cn=reader,ou=service,dc=example,dc=org
    password: ${LDAP_TEST_BIND_PASSWORD}
```

Đây là địa chỉ giả để minh họa; test cần server thực sự chạy và cung cấp chứng chỉ TLS hợp lệ. Không dùng mật khẩu thật trong mã nguồn hoặc dùng directory production làm nơi thử scan tải lớn.

Trước test, xác nhận server hỗ trợ OID `1.2.840.113556.1.4.319`; một test chỉ thấy đủ entry chưa chứng minh control được áp dụng nếu server bỏ qua và trả toàn bộ kết quả.

### 13.2. Bài test cơ bản với kích thước trang nhỏ

Ví dụ skeleton:

```java
// PSEUDOCODE integration test:
// 1. Khởi tạo PagedPersonScanner cho test với pageSize=2.
// 2. Chuẩn bị directory có đúng 5 entry.
// 3. Mỗi lần search phải dùng paged-results control cùng connection.
// 4. Sink nhận đủ 5 uid, không mất/lặp khi directory KHÔNG đổi.
// 5. Quan sát ít nhất ba response page:
//       page1=2, page2=2, page3=1, final cookie empty.
// 6. Kiểm tra paging controls thực sự xuất hiện trong response.
// 7. Không tích lũy toàn bộ result ở production scanner.
```

Do ví dụ `PagedPersonScanner` đặt page size là hằng 100, cần parameterize constructor hoặc thêm cấu hình test để đặt page size bằng 2. Mục tiêu test không phải “thấy danh sách dài 5”, mà là xác nhận **thật sự có nhiều lượt search**, cookie được tiếp tục hợp lệ và kết thúc ở response cuối.

Các kịch bản cần kiểm tra:

| Kịch bản | Kỳ vọng |
|---|---|
| Có 5 entry, page size 2 | Duyệt đủ các entry trên nhiều trang, cookie kết thúc |
| Không có entry phù hợp | Không lỗi; tổng đã đọc bằng 0, không loop vô hạn |
| Page size lớn hơn số entry | Có thể chỉ một trang; response được xử lý đúng |
| Server không hỗ trợ paging control | Báo lỗi/cảnh báo rõ; không coi dữ liệu là đã được phân trang |
| Giữa hai trang connection bị thay | Có thể lỗi cookie; không im lặng bắt đầu lại bằng trang đầu |
| Đổi filter/base giữa các trang | Từ chối thiết kế này; không dùng lại cookie cho query khác |
| Server trả ước lượng total bằng 0 | Không suy luận không có entry nếu thực tế có kết quả |
| Thêm/xóa entry khi đang scan | Cho phép phát hiện thiếu/lặp; dùng idempotency và reconciliation |
| Sink báo lỗi sau trang đầu | Job INCOMPLETE, giải phóng context, thiết kế retry rõ ràng |
| Chạm `MAX_PAGES` | Batch thất bại có chủ đích, không báo kết quả đầy đủ |
| Server có size/time limit nghiêm ngặt | Không tự coi dữ liệu trả ít là hết; xử lý response/error |
| Nhiều scan đồng thời | Pool/server không bị giữ context vượt budget |

### 13.3. Kiểm thử tải trước khi triển khai

So sánh ba cấu hình page size, ví dụ 50/100/500, với **cùng dataset, filter, base DN, server, quyền và mức tải**. Đo:

```text
test_run_id
page_size
total_entries_fetched
pages_requested
entries_processed
scan_duration_ms
page_latency_p95_ms
heap_peak_mb
ldap_active_connections
ldap_error_count
final_status = COMPLETE | INCOMPLETE | FAILED
```

Các chỉ số mang tên ổn định; **không đưa DN/email/password hoặc filter chứa dữ liệu cá nhân** vào tag metrics có cardinality cao. Khi bật debug JNDI/LDAP, kiểm soát log và xóa dữ liệu nhạy cảm theo chính sách.

Không kết luận “paging tốt hơn” chỉ từ thời gian một batch: hãy xem cả server CPU, p99 latency của các request khác và thời gian giữ context. Một batch có throughput cao nhưng làm dịch vụ xác thực LDAP chậm đi là một thiết kế chưa đạt.

## 14. Lỗi thường gặp và hướng chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Page đầu trả toàn bộ entry | Server bỏ qua control không critical, hoặc code không dùng DirContextProcessor | Kiểm tra `supportedControl`/response control, cấu hình phù hợp |
| Trang sau lỗi cookie | Connection thay đổi, cookie hết hạn, server failover, query bị đổi | Giữ cùng context; không reuse cookie cũ/khác query |
| Lặp trang đầu vô hạn | Không đọc/cập nhật cookie hoặc không kiểm tra `hasMore()` | Dùng cùng processor qua vòng lặp; đặt `maxPages` |
| Đủ entry nhưng heap vẫn tăng mạnh | Sink hoặc ứng dụng gom toàn bộ các trang trong một list/cache | Xử lý/flush từng batch, giới hạn pipeline buffer |
| Giảm page size nhưng query vẫn chậm | Filter không index, base/scope quá rộng, server quá tải | Tối ưu query và directory index, đo page latency |
| Bị `SizeLimitExceededException` | Server limit, SearchControls countLimit hoặc quyền/behavior backend | Xem lại giới hạn, không dùng countLimit để giả lập paging |
| Có entry bị lặp/bỏ sót khi đồng bộ | Directory thay đổi giữa các trang | Idempotency, incremental sync hoặc reconciliation |
| UI muốn nhảy đến trang 100 | Cookie RFC 2696 không phải offset | Chọn thiết kế cursor/session hoặc công nghệ hỗ trợ phù hợp |
| Pool cạn trong khi scan | Nhiều job giữ context suốt nhiều trang | Giới hạn concurrency và thời gian scan |
| Test chạy với bản Spring LDAP cũ không có class mới | `PagedResultsControlExchangeDirContextProcessor` chỉ có từ 4.1 | Dùng API cũ phù hợp phiên bản và kiểm chứng |
| Không thấy operational attributes | Mặc định trả user attributes, hoặc projection thiếu trường | Chọn thuộc tính cần thiết và kiểm tra ACL/server |

Đừng chữa lỗi bằng cách `catch (Exception) { return List.of(); }`. Điều đó biến lỗi mạng, ACL, size limit hoặc cookie thành **“không còn dữ liệu”**, tạo nguy cơ đồng bộ thiếu người dùng hoặc nhóm.

## 15. Câu hỏi tự đánh giá

1. Phân biệt `countLimit(100)`, chia một `List` thành trang ở Java và LDAP Simple Paged Results theo RFC 2696.
2. Cookie ở response LDAP có ý nghĩa gì? Khi nào cookie rỗng?
3. Vì sao cookie không phải số offset và không được dùng lại với filter khác?
4. Tại sao `SingleContextSource` cần thiết trong một chuỗi paged search dùng `LdapTemplate`?
5. Đâu là khác biệt API chính giữa `PagedResultsDirContextProcessor` và `PagedResultsControlExchangeDirContextProcessor`?
6. Nếu code dùng `result.addAll(onePage)` qua mọi trang, nó có thực sự giới hạn peak heap không?
7. Vì sao directory thay đổi giữa các trang có thể tạo entry lặp hoặc bỏ sót dù client dùng cookie đúng?
8. Có thể lấy tổng số trang chính xác chỉ bằng `response size` của control không?
9. Khi nào page size 100 vẫn tiêu tốn nhiều bộ nhớ? Vai trò của returning attributes là gì?
10. Cần quan sát những metric nào để chọn page size và biết một batch đã hoàn tất an toàn?
11. Vì sao `PageRequest.of(0, 20)` của repository LDAP không đồng nghĩa một paged-results LDAP control?
12. Nếu batch dừng sau trang 3 do timeout, hệ thống phải báo trạng thái gì và xử lý cookie/checkpoint ra sao?

**Ghi nhớ:** muốn kiểm soát bộ nhớ khi tìm kiếm nhiều entry LDAP, hãy dùng **server-side paging** theo RFC 2696, **xử lý ngay từng trang** và giữ **cùng connection** trong chuỗi cookie. Kết hợp base/scope/filter chọn lọc, chỉ yêu cầu các thuộc tính cần dùng, đặt budget tổng, giới hạn concurrency, kiểm tra server thực sự hỗ trợ control và đo hiệu năng. Phân trang **không bảo đảm snapshot**, không tạo cursor HTTP bền vững và không thay thế ACL, giới hạn server hay chiến lược đồng bộ nhất quán.

### Tài liệu tham khảo

- IETF [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696): cấu trúc request/response control, opaque cookie, completion và abandon.
- IETF [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest, controls, size/time limits và SearchResultDone.
- Spring LDAP Reference — [Processing the DirContext / Paged Search Results](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): `DirContextProcessor`, paging và `SingleContextSource`.
- Spring LDAP API — [`PagedResultsControlExchangeDirContextProcessor`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html): API paging mới từ 4.1.
- Spring LDAP API — [`SingleContextSource`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/SingleContextSource.html): duy trì đúng context giữa các thao tác LDAP.
- Spring LDAP API — [`PagedResultsDirContextProcessor`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsDirContextProcessor.html): API cũ/deprecated từ 4.1.
- Spring Data LDAP — [Repository Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): giới hạn paging/sorting của repository LDAP.
- Oracle Java SE — [`SearchControls`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/SearchControls.html) và [`PagedResultsControl`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/PagedResultsControl.html).
