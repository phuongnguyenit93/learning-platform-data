# Duyệt kết quả bằng callback và kiểm soát bộ nhớ

## 1. Vì sao một truy vấn LDAP lớn có thể làm ứng dụng thiếu bộ nhớ?

Khi dùng **Spring Data LDAP**, ứng dụng có thể tìm entry bằng repository hoặc `LdapTemplate`. Các API trả về `List<T>` rất tiện khi kết quả nhỏ, nhưng chúng có một đặc điểm quan trọng: **mọi đối tượng được map sẽ được giữ trong danh sách cho tới khi phương thức trả về**.

Giả sử một truy vấn trả về 100.000 người dùng, mỗi đối tượng Java sau khi map chiếm vài KB tính cả object, chuỗi và collection. Chỉ riêng kết quả có thể tiêu thụ hàng trăm MB heap, chưa tính bộ nhớ của ứng dụng, JNDI provider, cache và dữ liệu tạm.

Một cách xử lý phù hợp cho tập kết quả lớn là **callback**. Thay vì trả toàn bộ danh sách, `LdapTemplate` gọi handler một lần cho từng kết quả trong lúc duyệt `NamingEnumeration`. Ứng dụng có thể ánh xạ một entry, ghi vào batch nhỏ hoặc đưa vào hàng đợi có giới hạn rồi giải phóng tham chiếu.

Bài học này tập trung vào:

- Khác biệt giữa `AttributesMapper`, `ContextMapper` và `NameClassPairCallbackHandler`.
- Dùng `LdapTemplate.search(...)` với callback để xử lý từng `SearchResult`.
- Giới hạn thuộc tính, scope, số lượng và thời gian tìm kiếm.
- Giữ bộ nhớ ở mức ổn định bằng batch nhỏ hoặc bounded queue.
- Kết hợp callback với LDAP paged results.
- Xử lý lỗi callback, downstream chậm và kết quả Search bị cắt.
- Đo bộ nhớ, throughput và kiểm thử trên directory có dữ liệu lớn.

Sau bài này, người học có thể chọn API tìm kiếm theo kích thước dữ liệu, triển khai callback an toàn và giải thích rõ giới hạn của mô hình streaming.

> **Nguyên tắc:** Callback tránh tích lũy toàn bộ kết quả thành `List`, nhưng không tự tạo ra bộ nhớ vô hạn hay paging. Muốn kiểm soát tài nguyên, cần kết hợp callback với projection thuộc tính, batch/queue có giới hạn, Search controls và paging khi phù hợp.

## 2. Ba cách nhận kết quả trong Spring LDAP

Spring LDAP cung cấp các kiểu mapper và callback khác nhau. Cần chọn theo cách ứng dụng muốn tiêu thụ kết quả.

| API | Đầu vào cho mỗi kết quả | Hình thức trả về | Đặc điểm bộ nhớ |
| --- | --- | --- | --- |
| `AttributesMapper<T>` | `Attributes` | `List<T>` | `LdapTemplate` tích lũy tất cả object được map |
| `ContextMapper<T>` | Context/đối tượng context của entry | `List<T>` | `LdapTemplate` tích lũy tất cả object được map |
| `NameClassPairCallbackHandler` | Một `NameClassPair` (với Search là `SearchResult`) | `void` | Handler tự xử lý từng entry; không có List kết quả tự động |

### 2.1. `AttributesMapper`: đơn giản khi chỉ cần attributes

Ví dụ:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;

List<String> names = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    (AttributesMapper<String>) attrs -> {
        var cn = attrs.get("cn");
        return cn == null ? null : String.valueOf(cn.get());
    }
);
~~~

Mapper nhận `Attributes` của từng entry và tạo ra một giá trị `String`. Dù mỗi kết quả chỉ là một chuỗi nhỏ, phương thức vẫn phải tích lũy danh sách tất cả chuỗi trước khi trả về.

Cách này phù hợp khi:

- Kết quả được giới hạn nhỏ và rõ ràng.
- Caller thực sự cần toàn bộ danh sách.
- Mỗi object sau mapping nhẹ.
- Có giới hạn số lượng kết quả hợp lý.

Không nên đổi entity lớn thành DTO nhỏ rồi cho rằng đã giải quyết mọi vấn đề bộ nhớ: nếu kết quả có hàng triệu phần tử, `List<DTO>` vẫn tăng theo tổng số phần tử.

### 2.2. `ContextMapper`: cần ngữ cảnh entry hoặc ODM

`ContextMapper<T>` nhận context của entry, hữu ích khi cần DN, thuộc tính qua `DirContextOperations` hoặc mapping ODM:

~~~java
import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

List<PersonSummary> people = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    (ContextMapper<PersonSummary>) context -> {
        DirContextOperations entry = (DirContextOperations) context;

        return new PersonSummary(
            entry.getDn().toString(),
            entry.getStringAttribute("uid"),
            entry.getStringAttribute("cn")
        );
    }
);
~~~

Đoạn này cũng trả về `List<PersonSummary>`. Nó thuận tiện khi muốn map entry theo kiểu Spring LDAP, nhưng không phải callback streaming.

Nếu muốn map entity ODM đầy đủ qua `ObjectDirectoryMapper`, có thể dùng các API Spring LDAP phù hợp. Hãy cân nhắc kích thước kết quả trước khi dùng overload trả về `List<T>`.

### 2.3. `NameClassPairCallbackHandler`: xử lý từng SearchResult

Callback API có dạng:

~~~java
void search(
    String base,
    String filter,
    SearchControls controls,
    NameClassPairCallbackHandler handler
);
~~~

Handler có một phương thức:

~~~java
void handleNameClassPair(NameClassPair nameClassPair)
    throws NamingException;
~~~

Với thao tác Search, đối tượng callback thường là `javax.naming.directory.SearchResult`, một lớp kế thừa `NameClassPair`. `SearchResult` cung cấp `Attributes` của entry.

Điểm khác biệt quan trọng:

- Callback được gọi cho từng kết quả.
- `LdapTemplate` không tạo `List<T>` kết quả thay cho ứng dụng.
- Handler có thể chuyển kết quả thành DTO, ghi batch hoặc chuyển vào queue.
- `LdapTemplate` quản lý vòng đời `NamingEnumeration` và LDAP context cho lời gọi Search.
- Nếu callback ném lỗi, Search có thể dừng; kết quả chưa được duyệt hết không được coi là hoàn tất.

`NameClassPairCallbackHandler` **không nhận trực tiếp `DirContextOperations`**. Nếu cần `Attributes`, hãy kiểm tra `SearchResult` và gọi `getAttributes()`. Nếu cần object được bind, phải hiểu `returningObjFlag` và API mapping tương ứng; không giả định callback có cùng chữ ký với `ContextMapper`.

## 3. Đường đi của một callback Search

~~~mermaid
sequenceDiagram
    participant S as Application service
    participant T as LdapTemplate
    participant C as ContextSource
    participant D as LDAP server
    participant H as NameClassPairCallbackHandler
    participant W as Batch / downstream sink
    S->>T: search(base, filter, controls, handler)
    T->>C: Lấy read-only DirContext
    C->>D: LDAP SearchRequest
    D-->>T: SearchResult entries
    loop Từng entry trong NamingEnumeration
        T->>H: handleNameClassPair(SearchResult)
        H->>H: Đọc Attributes, map DTO
        H->>W: Thêm vào batch / xử lý
    end
    T->>T: Đóng NamingEnumeration và context
    T-->>S: Search hoàn tất
~~~

Đây là luồng đồng bộ: callback chạy trong quá trình `LdapTemplate` duyệt kết quả trên thread gọi Search. Nó không tự tạo thread mới hoặc biến truy vấn thành reactive stream.

Trong quá trình duyệt:

1. `LdapTemplate` lấy context từ `ContextSource`.
2. Search được gửi tới LDAP server với base, filter và controls.
3. Mỗi `SearchResult` được chuyển cho handler.
4. Handler đọc những thuộc tính đã yêu cầu và xử lý entry.
5. Khi enumeration kết thúc, `LdapTemplate` đóng enumeration và giải phóng context theo cơ chế của nó.

Ứng dụng **không tự đóng** `SearchResult`, `Attributes` hoặc context của `LdapTemplate` trong callback. Không giữ `SearchResult` hoặc object gắn với context lâu dài; hãy chuyển dữ liệu cần thiết thành DTO độc lập.

## 4. Giới hạn dữ liệu ngay từ Search

Callback giảm việc tích lũy kết quả ở client. Nhưng nếu server phải tìm toàn bộ directory hoặc trả về tất cả thuộc tính của mỗi entry, chi phí mạng và server vẫn lớn.

### 4.1. Chọn base DN và scope hẹp nhất

Ba scope thông dụng:

| Scope | Hành vi | Ví dụ |
| --- | --- | --- |
| `OBJECT_SCOPE` | Chỉ entry tại base DN | Đọc đúng một OU/entry |
| `ONELEVEL_SCOPE` | Các child trực tiếp của base | Danh sách user nằm trực tiếp trong OU |
| `SUBTREE_SCOPE` | Base và toàn bộ descendants | Tìm user trong các OU con |

Nếu user nằm trực tiếp trong `ou=people`, `ONELEVEL_SCOPE` có thể đủ. Dùng `SUBTREE_SCOPE` khi nghiệp vụ thực sự cần tìm xuyên các OU con.

### 4.2. Chỉ yêu cầu thuộc tính cần dùng

Không yêu cầu toàn bộ attributes nếu handler chỉ cần `uid`, `cn` và `entryUUID`.

~~~java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(
    new String[] {"uid", "cn", "entryUUID"}
);
controls.setReturningObjFlag(false);
controls.setTimeLimit(5_000);
controls.setCountLimit(10_000);
~~~

Ý nghĩa:

- `setReturningAttributes(...)` giới hạn projection của Search.
- `setReturningObjFlag(false)` không yêu cầu JNDI provider trả bound object trong kết quả; callback ở ví dụ tiếp theo chỉ cần `SearchResult` và attributes.
- `setTimeLimit(5_000)` đặt giới hạn thời gian Search ở mức JNDI SearchControls, tính bằng mili giây.
- `setCountLimit(10_000)` giới hạn số kết quả được trả về cho Search này.

**Count limit không phải page size.** Nếu truy vấn có thể vượt 10.000 entry, kết quả có thể bị giới hạn và Search có thể phát sinh `SizeLimitExceededException`. Không đánh dấu scan hoàn tất nếu giới hạn khiến dữ liệu chưa được đọc hết. Với tập lớn, dùng paged results và vẫn tôn trọng giới hạn phía server.

Một số thuộc tính như `entryUUID` là operational attribute và có thể cần được yêu cầu rõ ràng. Directory khác nhau có thể cung cấp stable ID khác nhau; Active Directory thường dùng `objectGUID` dạng binary.

### 4.3. Dùng filter builder thay vì nối chuỗi input

~~~java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

AndFilter filter = new AndFilter();
filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
filter.and(new EqualsFilter("departmentNumber", departmentNumber));

String encodedFilter = filter.encode();
~~~

Dùng `EqualsFilter` để encode giá trị assertion theo cú pháp LDAP filter. Không làm như sau:

~~~java
// KHÔNG AN TOÀN: input có thể thay đổi cấu trúc filter.
String filter = "(departmentNumber=" + departmentNumber + ")";
~~~

Escape LDAP filter theo RFC 4515 khác với escape DN theo RFC 4514. Callback không làm filter trở nên an toàn; filter phải được xây dựng đúng trước khi gọi Search.

## 5. Ví dụ callback xử lý từng entry

Giả sử ứng dụng cần duyệt nhân viên trong `ou=people`, chỉ lấy DN, `uid` và `cn`, rồi ghi theo batch nhỏ.

### 5.1. DTO và sink

~~~java
import java.util.List;

public record PersonSummary(
    String dn,
    String uid,
    String commonName
) {}

public interface PersonSink {
    void upsertBatch(List<PersonSummary> people);
}

public interface QuarantineSink {
    void record(String dn, String safeReason);
}
~~~

`PersonSink` nên thực hiện upsert idempotent theo stable identifier nếu directory cung cấp. `QuarantineSink` cần ghi lỗi bền vững. Hai interface là abstraction của ứng dụng, không phải class Spring LDAP có sẵn.

### 5.2. Callback có batch giới hạn

~~~java
import java.util.ArrayList;
import java.util.List;

import javax.naming.NameClassPair;
import javax.naming.NamingException;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchResult;

import org.springframework.ldap.core.NameClassPairCallbackHandler;

public final class PersonBatchHandler
        implements NameClassPairCallbackHandler {

    private static final int BATCH_SIZE = 250;

    private final List<PersonSummary> buffer =
        new ArrayList<>(BATCH_SIZE);

    private final PersonSink sink;
    private final QuarantineSink quarantine;

    public PersonBatchHandler(
            PersonSink sink,
            QuarantineSink quarantine) {
        this.sink = sink;
        this.quarantine = quarantine;
    }

    @Override
    public void handleNameClassPair(NameClassPair pair)
            throws NamingException {

        if (!(pair instanceof SearchResult)) {
            throw new NamingException(
                "Search callback không trả về SearchResult"
            );
        }

        SearchResult result = (SearchResult) pair;
        Attributes attributes = result.getAttributes();
        String dn = result.getNameInNamespace();

        String uid = readString(attributes, "uid");
        String cn = readString(attributes, "cn");

        if (uid == null || uid.isBlank()) {
            quarantine.record(dn, "missing-required-uid");
            return;
        }

        buffer.add(new PersonSummary(dn, uid, cn));

        if (buffer.size() >= BATCH_SIZE) {
            flush();
        }
    }

    public void flush() {
        if (buffer.isEmpty()) {
            return;
        }

        // Sink nhận bản sao bất biến; buffer chỉ được xóa khi ghi thành công.
        sink.upsertBatch(List.copyOf(buffer));
        buffer.clear();
    }

    private static String readString(
            Attributes attributes,
            String attributeName) throws NamingException {

        var attribute = attributes.get(attributeName);
        return attribute == null
            ? null
            : String.valueOf(attribute.get());
    }
}
~~~

Một số điểm cần hiểu:

- `NameClassPairCallbackHandler` nhận `NameClassPair`; với Search, code kiểm tra và cast sang `SearchResult`.
- `SearchResult.getAttributes()` chỉ chứa các thuộc tính mà Search trả về.
- `getNameInNamespace()` lấy tên đầy đủ nếu JNDI provider hỗ trợ. Nếu provider không hỗ trợ tên đầy đủ, cần ghép tên tương đối với search base bằng API `LdapName`/`LdapNameBuilder`, không tự `split(",")` hoặc nối chuỗi DN.
- Handler chỉ giữ tối đa `BATCH_SIZE` DTO trước khi gọi sink.
- `List.copyOf(buffer)` chuyển batch sang một danh sách độc lập để sink sử dụng.
- Buffer chỉ được xóa sau khi sink ghi thành công; lỗi downstream sẽ làm callback dừng và lỗi được truyền lên caller.
- Entry thiếu `uid` được ghi vào quarantine. Nếu ghi quarantine thất bại, exception cần truyền lên để Search không bị coi là hoàn tất.

Ví dụ đọc `String.valueOf(attribute.get())` giả định thuộc tính là một giá trị chuỗi. Với attribute đa trị, cần duyệt `NamingEnumeration<?>`; với binary attribute như `objectGUID` hoặc ảnh, cần xử lý `byte[]` theo đúng schema, không chuyển thành chuỗi bằng `String.valueOf`.

### 5.3. Gọi Search với callback

~~~java
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

public void exportPeople(
        LdapTemplate ldapTemplate,
        PersonSink sink,
        QuarantineSink quarantine,
        String departmentNumber) {

    AndFilter filter = new AndFilter();
    filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
    filter.and(new EqualsFilter("departmentNumber", departmentNumber));

    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setReturningAttributes(
        new String[] {"uid", "cn", "entryUUID"}
    );
    controls.setReturningObjFlag(false);
    controls.setTimeLimit(5_000);
    controls.setCountLimit(10_000);

    PersonBatchHandler handler =
        new PersonBatchHandler(sink, quarantine);

    // Mỗi kết quả được chuyển vào handler, không tạo List kết quả.
    ldapTemplate.search(
        "ou=people",
        filter.encode(),
        controls,
        handler
    );

    // Chỉ flush batch cuối sau khi Search kết thúc thành công.
    handler.flush();
}
~~~

Đây là callback Search đồng bộ. Các batch đầy đủ có thể đã được ghi trong lúc enumeration đang chạy. Batch cuối nhỏ hơn 250 chỉ được ghi sau khi Search kết thúc bình thường.

Nếu Search ném lỗi trước khi kết thúc:

- Các batch đã được sink ghi thành công vẫn có thể tồn tại.
- Buffer cuối chưa được flush.
- Không được đánh dấu toàn bộ export là hoàn tất.
- Lần chạy lại có thể đọc lại các entry đã ghi; sink phải idempotent để không tạo bản ghi trùng.
- Nếu cần resume chính xác, lưu tiến độ theo stable ID/page hoặc run manifest thay vì chỉ dựa vào biến đếm trong RAM.

## 6. Callback không đồng nghĩa với O(1) memory

Callback giúp tránh một `List` chứa toàn bộ kết quả, nhưng bộ nhớ thực tế vẫn phụ thuộc nhiều yếu tố:

~~~text
Tổng bộ nhớ tiến trình
  = bộ nhớ ứng dụng nền
  + SearchResult/Attributes hiện tại
  + buffer của callback
  + queue downstream
  + buffer JNDI/provider và network
  + object tạm do mapping/logging
~~~

Nếu callback chỉ giữ một DTO rồi ghi ngay, bộ nhớ phía ứng dụng có thể gần như không tăng theo tổng số kết quả. Nếu giữ batch 250 phần tử, bộ nhớ phụ thuộc batch size và kích thước DTO. Nếu queue không giới hạn, callback có thể đẩy toàn bộ kết quả vào queue và vấn đề bộ nhớ quay trở lại.

### 6.1. So sánh cách giữ kết quả

Giả sử Search trả về 200.000 entry:

| Cách xử lý | Bộ nhớ ứng dụng | Khi phù hợp |
| --- | --- | --- |
| `search(..., AttributesMapper)` trả `List<T>` | Tăng theo toàn bộ kết quả | Tập nhỏ, caller cần toàn bộ List |
| `search(..., ContextMapper)` trả `List<T>` | Tăng theo toàn bộ object được map | Cần mapping context/ODM và tập có giới hạn |
| Callback ghi từng entry | Không giữ toàn bộ List; phụ thuộc object hiện tại và sink | Export/ETL hoặc xử lý lần lượt |
| Callback + batch 250 | Tăng theo tối đa batch đang giữ | Ghi database theo lô |
| Callback + bounded queue | Tăng theo capacity queue và batch worker | Tách producer/consumer với backpressure |
| Callback + queue không giới hạn | Có thể tăng theo tổng kết quả | Không nên dùng cho tập không biết trước kích thước |

Không dùng từ “constant memory” như một bảo đảm tuyệt đối. JNDI provider, LDAP server, TLS buffer, driver và downstream đều có thể giữ dữ liệu tạm. Mục tiêu là **giới hạn được phần bộ nhớ do ứng dụng chủ động tích lũy**.

### 6.2. Batch size là một trade-off

Batch quá nhỏ:

- Nhiều lần gọi database hoặc HTTP.
- Overhead transaction lớn.
- Throughput có thể thấp.

Batch quá lớn:

- Giữ nhiều DTO trong heap.
- Transaction lâu hơn.
- Retry một batch thất bại tốn nhiều công hơn.
- Tăng độ trễ trước khi dữ liệu được ghi.

Hãy đo theo kích thước DTO, latency sink, số worker và giới hạn database. Bắt đầu với batch vừa phải, sau đó đo throughput và heap thay vì chọn một con số cố định cho mọi hệ thống.

## 7. Dùng bounded queue để tách Search và downstream

Nếu xử lý database trong callback làm LDAP context bị giữ quá lâu, có thể tách callback thành producer đưa DTO vào queue và worker xử lý queue.

~~~mermaid
flowchart LR
    A["LDAP Search"] --> B["Callback producer"]
    B --> C["Bounded queue"]
    C --> D["Worker 1"]
    C --> E["Worker 2"]
    C --> F["Worker N"]
    D --> G["Idempotent sink"]
    E --> G
    F --> G
~~~

Ví dụ:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

BlockingQueue<PersonSummary> queue =
    new ArrayBlockingQueue<>(500);
~~~

Trong callback:

~~~java
queue.put(summary);
~~~

Khi queue đầy, producer phải chờ cho đến khi worker giải phóng chỗ. Đây là **backpressure**: tốc độ đọc từ LDAP tự giảm theo tốc độ downstream.

Cần lưu ý:

- `put` có thể block callback, nên LDAP Search và context vẫn đang mở trong thời gian chờ.
- Queue phải có capacity hữu hạn; `LinkedBlockingQueue` không giới hạn có thể gây OOM.
- Nếu worker lỗi, cần một chính sách retry/poison message và cách dừng producer.
- Không bỏ entry khi `offer` trả `false`; phải retry enqueue hoặc làm Search thất bại.
- Nếu worker cần gọi lại LDAP để lấy từng entry, có thể mượn thêm context trong lúc callback vẫn giữ một context. Pool nhỏ có thể cạn hoặc deadlock. Hãy đưa đủ dữ liệu cần thiết vào DTO hoặc điều phối Search theo batch.
- Nếu process crash, queue trong RAM mất dữ liệu; cần manifest/checkpoint hoặc durable queue khi yêu cầu resume.

Với export đơn giản, callback ghi batch đồng bộ có thể dễ vận hành hơn. Bounded queue chỉ nên thêm khi đo được lợi ích từ việc tách producer/consumer.

## 8. Paged results: giới hạn dữ liệu server trả về mỗi lượt

Callback giúp ứng dụng không tích lũy một `List` lớn. Tuy nhiên, Search có thể vẫn yêu cầu server trả về hàng trăm nghìn entry trong một operation. **Paged Results Control** (RFC 2696) yêu cầu server trả từng trang, ví dụ 500 entry mỗi trang.

Hai cơ chế giải quyết hai vấn đề khác nhau:

- **Callback:** kiểm soát cách ứng dụng tiêu thụ từng kết quả, không tạo List lớn.
- **Paging:** kiểm soát số kết quả server trả về trong mỗi lần Search.

Có thể kết hợp cả hai.

### 8.1. Ví dụ paging với callback trên Spring LDAP 4.1+

Spring LDAP 4.1+ cung cấp `PagedResultsControlExchangeDirContextProcessor`. Paged results cần **cùng underlying LDAP connection** giữa các trang. Dùng `SingleContextSource.doWithSingleContext(...)` để giữ cùng connection trong chuỗi paging.

~~~java
import javax.naming.directory.SearchControls;

import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapOperations;
import org.springframework.ldap.core.support.SingleContextSource;

public void exportPaged(
        ContextSource contextSource,
        String encodedFilter,
        PersonBatchHandler handler) {

    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setReturningAttributes(
        new String[] {"uid", "cn", "entryUUID"}
    );
    controls.setReturningObjFlag(false);
    controls.setTimeLimit(5_000);

    PagedResultsControlExchangeDirContextProcessor paging =
        new PagedResultsControlExchangeDirContextProcessor(500);

    SingleContextSource.doWithSingleContext(
        contextSource,
        (LdapOperations operations) -> {
            do {
                operations.search(
                    "ou=people",
                    encodedFilter,
                    controls,
                    handler,
                    paging
                );
            } while (paging.hasMore());

            return null;
        },
        true,  // Dùng read-only context cho Search.
        false, // Không bỏ qua PartialResultException.
        false  // Không bỏ qua NameNotFoundException.
    );

    // Flush batch cuối sau khi toàn bộ trang hoàn tất.
    handler.flush();
}
~~~

Ví dụ này giả định `LdapTemplate` và `ContextSource` được cấu hình cho cùng directory, và `encodedFilter` đã được xây an toàn. Có thể gọi `operations.search(...)` với callback và `DirContextProcessor` để gắn request/response control vào Search.

**Không bỏ `SingleContextSource`** trong chuỗi paging chỉ vì mỗi lần gọi `search` đã dùng cùng processor. Nếu connection thay đổi giữa các trang, cookie có thể không còn hợp lệ. Spring LDAP cũng hỗ trợ giữ context trong transaction phù hợp, nhưng không nên tự mở transaction dài chỉ để thay thế cơ chế connection scope nếu chưa hiểu tác động.

`PagedResultsControlExchangeDirContextProcessor` được giới thiệu trong Spring LDAP 4.1. Với phiên bản cũ hơn, API thường gặp là `PagedResultsDirContextProcessor`; hãy kiểm tra version và tài liệu tương ứng. Trong API hiện hành, class cũ đã được thay thế bằng processor mới.

### 8.2. Cookie paging không phải checkpoint bền vững

Cookie của RFC 2696 dùng để tiếp tục một chuỗi paged Search. Nó không chứng minh các entry đã được ghi vào database đích và không phải cursor đồng bộ lâu dài.

Nếu process chết giữa các trang:

- Những batch đã ghi có thể tồn tại.
- Trang đang xử lý có thể chưa hoàn tất.
- Cookie có thể không còn hợp lệ nếu connection/server thay đổi.
- Cần chạy lại Search theo cửa sổ an toàn hoặc cơ chế resume được directory hỗ trợ.
- Sink cần idempotent để xử lý candidate trùng.

Không lưu cookie rồi dùng lại vô thời hạn sau deploy, failover hoặc reconnect. Nếu yêu cầu theo dõi thay đổi lâu dài, phân biệt paging control với LDAP Content Synchronization (RFC 4533) hoặc changelog/DirSync của vendor.

### 8.3. Page size và callback batch size là hai thông số riêng

| Thông số | Điều khiển | Ví dụ |
| --- | --- | --- |
| LDAP page size | Số entry server trả cho một page | 500 |
| Callback batch size | Số DTO ứng dụng gom trước khi ghi sink | 250 |
| Queue capacity | Số DTO chờ worker xử lý | 500 |
| Worker concurrency | Số consumer chạy song song | 4 |

Page size 500 không có nghĩa callback sẽ tích lũy 500 object. Callback có thể flush mỗi 250 entry trong một trang. Ngược lại, nếu callback không flush và giữ toàn bộ page, memory sẽ tăng theo page size.

## 9. Scope, count limit, time limit và kết quả không đầy đủ

Callback có thể xử lý các entry đã nhận trước khi server báo lỗi. Điều đó không có nghĩa toàn bộ Search đã hoàn tất.

### 9.1. Những giới hạn thường gặp

| Tình huống | Ý nghĩa | Hành động |
| --- | --- | --- |
| `SizeLimitExceededException` | Server/client giới hạn số kết quả | Không đánh dấu scan hoàn tất; dùng paging hoặc điều chỉnh phạm vi/quyền |
| `TimeLimitExceededException` | Search vượt thời gian server cho phép | Thu hẹp filter/base, tối ưu index hoặc chia phạm vi |
| `CommunicationException` | Kết nối bị gián đoạn | Giữ checkpoint, resume/re-scan theo policy |
| `PartialResultException` | Có kết quả một phần, thường liên quan referral/provider | Xử lý referral hoặc đánh dấu scan chưa đầy đủ |
| `NameNotFoundException` ở base | Search base không tồn tại/không nhìn thấy | Kiểm tra base DN và ACL; không tự coi như empty hợp lệ trong mọi ngữ cảnh |
| Cookie paging lỗi | Chuỗi page không tiếp tục được | Hủy chuỗi và khởi động lại từ cửa sổ an toàn |
| Callback ném exception | Handler không xử lý được entry hoặc downstream lỗi | Search dừng; ghi trạng thái và không commit scan complete |

Một số cấu hình `LdapTemplate` có thể bỏ qua một số exception như `NameNotFoundException` hoặc `PartialResultException` theo policy. Hãy hiểu cấu hình thực tế trước khi kết luận rằng Search hoàn tất bình thường.

### 9.2. Đếm số kết quả không đồng nghĩa với biết tổng số

Có thể dùng callback để đếm:

~~~java
import java.util.concurrent.atomic.LongAdder;
import org.springframework.ldap.core.NameClassPairCallbackHandler;

LongAdder count = new LongAdder();

NameClassPairCallbackHandler counter = pair -> count.increment();

ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    controls,
    counter
);
~~~

Đây là đếm số kết quả callback đã nhận. Nó không nhất thiết là tổng số entry trong directory nếu Search bị giới hạn, lỗi, referral chưa xử lý hoặc server trả partial result.

Một số server có thể cung cấp estimated result size qua paged response control, nhưng giá trị này có thể không có hoặc không chính xác tuyệt đối. Đừng dùng count estimate làm bằng chứng scan đầy đủ.

### 9.3. Không đánh dấu hoàn tất trước khi callback Search trả về bình thường

Mẫu an toàn:

~~~java
boolean completed = false;

try {
    ldapTemplate.search(base, encodedFilter, controls, handler);
    handler.flush();
    completed = true;
} finally {
    if (!completed) {
        // Ghi trạng thái scan chưa hoàn tất.
        // Các batch đã commit vẫn được giữ và sẽ được dedupe khi chạy lại.
    }
}
~~~

Trong hệ thống thực, `completed` cần được lưu bền vững trong run manifest, không chỉ là biến local. Nếu `flush()` cuối cùng lỗi, Search có thể đã đọc hết nhưng downstream chưa hoàn tất; run vẫn chưa được coi là thành công.

## 10. Xử lý lỗi trong callback

### 10.1. Lỗi dữ liệu của một entry

Ví dụ một entry thiếu `uid` hoặc giá trị không phù hợp mapping. Nếu có thể xác định DN và lỗi là riêng entry, handler có thể ghi quarantine rồi tiếp tục:

~~~java
if (uid == null || uid.isBlank()) {
    quarantine.record(dn, "missing-required-uid");
    return;
}
~~~

Điều kiện quan trọng: ghi quarantine phải thành công và bền vững. Nếu quarantine store đang lỗi, không thể âm thầm bỏ entry rồi đánh dấu Search hoàn tất.

### 10.2. Lỗi hạ tầng/downstream

Nếu database đích timeout, queue bị lỗi hoặc sink không còn khả dụng, callback nên dừng Search bằng cách truyền exception lên caller. Tiếp tục đọc LDAP trong khi không thể ghi dữ liệu sẽ làm tăng buffer hoặc tạo một scan không có đầu ra bền vững.

Một callback không nên bắt mọi `RuntimeException` rồi tiếp tục. Cần phân biệt:

- **Lỗi entry có thể cách ly:** malformed attribute, thiếu trường nghiệp vụ, mapping không hợp lệ.
- **Lỗi hệ thống:** DB outage, queue full không thể phục hồi, credential/connection lỗi, sink không khả dụng.
- **Lỗi không rõ:** dừng scan, giữ trạng thái chưa hoàn tất và điều tra.

### 10.3. Callback có thể ném `NamingException`

`NameClassPairCallbackHandler.handleNameClassPair(...)` khai báo `throws NamingException`. Nếu thao tác đọc attribute hoặc xử lý JNDI gặp lỗi, có thể truyền lỗi lên. `LdapTemplate` quản lý việc kết thúc enumeration/context và chuyển đổi exception theo cơ chế của Spring LDAP.

Nếu callback ném unchecked exception do sink thất bại, exception cũng làm lời gọi Search kết thúc. Đừng nuốt exception rồi trả về như thể toàn bộ kết quả đã được xử lý.

### 10.4. Không gọi LDAP lồng nhau cho mỗi callback nếu không cần

Trong callback, `LdapTemplate` đang duyệt Search và giữ context của operation đó. Nếu mỗi callback lại gọi một Search khác qua cùng pool:

- Số context đang mượn tăng.
- Pool nhỏ có thể cạn.
- Latency tăng do N+1 Search.
- Callback giữ connection lâu hơn.
- Có nguy cơ deadlock nếu callback chờ worker mà worker cần mượn connection nhưng pool đã bị giữ.

Ưu tiên lấy đủ projection attributes trong Search đầu tiên. Nếu cần fetch thêm dữ liệu, hãy cân nhắc batch theo DN hoặc xử lý ở worker sau khi callback đã kết thúc, với concurrency được giới hạn.

## 11. Callback và Spring Data LDAP Repository

Repository phù hợp với truy vấn miền và thao tác CRUD có kết quả vừa phải:

~~~java
public interface PersonRepository
        extends LdapRepository<PersonEntry> {

    List<PersonEntry> findByDepartmentNumber(String departmentNumber);
}
~~~

Method trả `List<PersonEntry>` tích lũy kết quả trong bộ nhớ. Nếu nghiệp vụ cần duyệt một tập rất lớn, có thể dùng `LdapTemplate.search(...)` với callback thay vì kỳ vọng repository tự trả một Java Stream không giới hạn.

Một cách phân chia hợp lý:

| Nhu cầu | API |
| --- | --- |
| Lấy một entry theo DN | `findById(Name)` hoặc `LdapTemplate.lookup` |
| Tìm một số lượng nhỏ theo thuộc tính | Repository query hoặc `LdapTemplate.search` trả List |
| Tìm một kết quả duy nhất | `searchForObject`/repository method phù hợp |
| Export hàng chục nghìn entry | `LdapTemplate.search` callback |
| Đọc từng trang server-side | Callback + paged results control |
| Lấy thuộc tính đặc biệt hoặc controls | `LdapTemplate` và `DirContextProcessor` |

Callback API nằm ở Spring LDAP core. Nó không phải một method của `LdapRepository`; vì vậy service có thể inject `LdapTemplate` khi cần kiểm soát cách duyệt Search.

## 12. Kiểm thử callback và bộ nhớ

### 12.1. Kiểm tra mỗi entry được callback đúng một lần trong fixture nhỏ

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import javax.naming.directory.SearchControls;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.NameClassPairCallbackHandler;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class LdapCallbackIntegrationTest {

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void callbackReceivesEachMatchingEntry() {
        AtomicInteger count = new AtomicInteger();

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid"});
        controls.setReturningObjFlag(false);

        NameClassPairCallbackHandler handler =
            pair -> count.incrementAndGet();

        ldapTemplate.search(
            "ou=people",
            "(objectClass=inetOrgPerson)",
            controls,
            handler
        );

        assertThat(count.get()).isEqualTo(3);
    }
}
~~~

Fixture test cần có đúng ba entry phù hợp filter. Test này chứng minh callback được gọi theo số entry trả về trong directory test; nó không chứng minh bộ nhớ production sẽ không tăng.

### 12.2. Kiểm tra batch luôn nằm trong giới hạn

Với `PersonBatchHandler`, thêm metric hoặc test sink để ghi nhận kích thước batch:

~~~java
public void upsertBatch(List<PersonSummary> people) {
    if (people.size() > 250) {
        throw new IllegalStateException("batch vượt giới hạn");
    }

    // Upsert idempotent theo stable ID.
}
~~~

Test với nhiều fixture để xác minh:

- Mỗi batch không vượt `BATCH_SIZE`.
- Batch cuối có thể nhỏ hơn.
- Khi sink ném lỗi, buffer không bị xóa.
- Khi Search lỗi giữa chừng, scan không được đánh dấu hoàn tất.
- Khi chạy lại, sink không tạo duplicate.

### 12.3. Kiểm tra lỗi giữa enumeration

Mô phỏng sink thất bại sau batch thứ hai:

~~~text
Page/search bắt đầu
  Batch 1 -> SUCCESS
  Batch 2 -> SUCCESS
  Batch 3 -> downstream timeout
Search bị dừng
Scan status = INCOMPLETE
Batch 1 và 2 vẫn tồn tại
Lần chạy lại -> upsert idempotent, xử lý lại candidate
~~~

Không yêu cầu callback phải tiếp tục khi downstream không còn khả dụng. Mục tiêu là giữ dữ liệu đã commit, giữ trạng thái scan chưa hoàn tất và có thể chạy lại an toàn.

### 12.4. Đo heap và throughput

Đo trong môi trường test có kích thước directory tương tự production:

- Heap trước và sau Search.
- Peak heap trong khi callback chạy.
- Số DTO trong buffer/queue.
- Thời gian Search và thời gian sink.
- Số context LDAP đang active.
- Số entry mỗi giây.
- GC pause và allocation rate.

So sánh ba trường hợp:

1. `search(..., AttributesMapper)` trả List.
2. Callback xử lý từng entry.
3. Callback + batch có giới hạn.

Dùng cùng filter, scope, projection, server và sink để so sánh công bằng. Một callback có sink chậm vẫn có thể giữ connection lâu và giảm throughput; giảm heap không đồng nghĩa mọi chỉ số hiệu năng đều tốt hơn.

## 13. Những lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `AttributesMapper` rồi trả List cho hàng triệu entry | Heap tăng theo số kết quả | Callback hoặc paging |
| Nghĩ `ContextMapper` tự streaming | Vẫn tích lũy `List<T>` | Dùng `NameClassPairCallbackHandler` |
| Callback đưa mọi object vào List nội bộ | Vấn đề bộ nhớ vẫn còn | Batch/queue có giới hạn |
| Dùng queue không giới hạn | OOM khi downstream chậm | Bounded queue và backpressure |
| Yêu cầu mọi attributes | Tăng network, heap và thời gian mapping | Projection đúng nhu cầu |
| Search `SUBTREE_SCOPE` trên root không cần thiết | Server phải duyệt quá rộng | Thu hẹp base/scope/filter |
| Không đặt count/time limit | Search có thể chạy quá lâu hoặc trả quá nhiều | Chọn controls và xử lý limit |
| Coi page size là callback batch size | Tích lũy không đúng mức dự kiến | Điều chỉnh hai thông số riêng |
| Dùng callback như reactive stream | Hiểu sai threading/lifecycle | Callback chạy đồng bộ trong Search |
| Giữ `SearchResult` sau callback | Giữ dữ liệu JNDI không cần thiết | Map sang DTO độc lập |
| Gọi Search lồng nhau trong mỗi callback | N+1, pool exhaustion | Projection đủ hoặc batch fetch sau |
| Bắt mọi exception rồi tiếp tục | Mất dữ liệu và báo scan thành công giả | Phân loại entry/system failure |
| Flush batch cuối trong `finally` vô điều kiện | Có thể ghi dữ liệu sau Search lỗi mà không có policy | Flush cuối sau Search thành công; checkpoint riêng |
| Dùng paging cookie qua connection khác | Cookie có thể không hợp lệ | Giữ cùng connection bằng `SingleContextSource` |
| Đánh dấu export hoàn tất khi đã nhận một số callback | Bỏ kết quả sau lỗi/page limit | Chỉ hoàn tất sau Search/paging kết thúc hợp lệ |

## 14. Checklist trước khi đưa callback Search lên production

**Truy vấn và dữ liệu**

- [ ] Base DN và scope nhỏ nhất đáp ứng nghiệp vụ.
- [ ] Filter được tạo bằng builder/encoder.
- [ ] Chỉ yêu cầu các attributes cần thiết.
- [ ] Binary và multivalued attributes được xử lý đúng.
- [ ] Count/time limit phù hợp; biết cách nhận biết kết quả bị giới hạn.
- [ ] Referral và partial result có chính sách rõ.

**Bộ nhớ và throughput**

- [ ] Callback không giữ toàn bộ kết quả.
- [ ] Batch size hoặc queue capacity có giới hạn.
- [ ] Downstream có backpressure.
- [ ] Callback không thực hiện N+1 LDAP Search.
- [ ] Search context không bị giữ lâu hơn cần thiết.
- [ ] Có metric heap, batch size, queue depth và latency.

**Độ tin cậy**

- [ ] Sink idempotent.
- [ ] Batch đã commit có thể replay an toàn.
- [ ] Search lỗi giữa chừng không đánh dấu scan hoàn tất.
- [ ] Paging dùng cùng connection khi server yêu cầu.
- [ ] Resume/re-scan có chiến lược dedupe.
- [ ] Quarantine và retry không âm thầm bỏ entry.

**Bảo mật**

- [ ] Bind account chỉ có quyền đọc cần thiết.
- [ ] TLS xác minh certificate/hostname.
- [ ] Log không chứa mật khẩu hoặc toàn bộ entry nhạy cảm.
- [ ] Filter và DN được encode theo đúng cú pháp riêng.

## 15. Câu hỏi tự kiểm tra

1. Vì sao `AttributesMapper` trả `List<T>` vẫn có thể tiêu thụ nhiều heap dù DTO rất nhỏ?
2. `ContextMapper` khác `NameClassPairCallbackHandler` như thế nào về kiểu đầu vào và cách trả kết quả?
3. Callback Search nhận loại object nào trong `handleNameClassPair`?
4. Vì sao không nên giả định callback nhận trực tiếp `DirContextOperations`?
5. `LdapTemplate` quản lý `NamingEnumeration` và LDAP context như thế nào?
6. Vì sao callback là xử lý đồng bộ chứ không phải reactive stream?
7. `SearchControls.setReturningAttributes` giảm chi phí nào?
8. `setCountLimit` khác page size như thế nào?
9. Khi `SizeLimitExceededException` xảy ra sau một số callback, scan có được coi là hoàn tất không?
10. Vì sao callback + unbounded queue vẫn có thể gây OOM?
11. Bounded queue tạo backpressure ra sao và ảnh hưởng thế nào tới thời gian giữ LDAP context?
12. Vì sao gọi một Search khác trong mỗi callback có thể gây N+1 hoặc pool exhaustion?
13. Tại sao cần dùng `LdapQueryBuilder`, `AndFilter` hoặc `EqualsFilter` cho input động?
14. Vì sao DN escaping và filter escaping là hai việc khác nhau?
15. Page size và batch size ở callback điều khiển những phần nào?
16. Vì sao paged results cần giữ cùng underlying LDAP connection?
17. `SingleContextSource` giải quyết vấn đề gì?
18. Cookie RFC 2696 có phải checkpoint đồng bộ bền vững không?
19. Nếu sink lỗi sau khi một số batch đã ghi, lần chạy sau cần điều kiện gì để không tạo duplicate?
20. Khi nào nên quarantine entry và khi nào phải dừng toàn bộ Search?
21. Làm sao xác minh callback đã nhận đủ kết quả khi có referral hoặc partial result?
22. Vì sao không flush batch cuối một cách vô điều kiện trong `finally`?
23. Khi nào repository query phù hợp hơn callback?
24. Những metric nào giúp xác định bottleneck nằm ở LDAP Search, callback hay downstream?

## 16. Tổng kết

`AttributesMapper` và `ContextMapper` rất tiện cho các truy vấn có kết quả vừa phải, nhưng các overload Search trả `List<T>` tích lũy toàn bộ object được map. Khi cần duyệt tập kết quả lớn, `NameClassPairCallbackHandler` cho phép `LdapTemplate` chuyển từng `SearchResult` đến ứng dụng trong lúc duyệt enumeration, không tạo List kết quả tự động.

Để kiểm soát bộ nhớ thực sự, callback nên đọc projection attributes tối thiểu, map sang DTO độc lập và ghi theo batch hoặc bounded queue. Callback chạy đồng bộ trong Search; xử lý quá lâu sẽ giữ LDAP context lâu hơn, còn queue không giới hạn chỉ chuyển vấn đề bộ nhớ sang một nơi khác. Search controls giới hạn scope, thuộc tính, số lượng và thời gian; paged results giới hạn số entry server trả mỗi lượt. Hai cơ chế có thể kết hợp và paging phải giữ đúng connection/cookie theo yêu cầu server.

Cuối cùng, callback có thể đã xử lý một phần kết quả trước khi Search lỗi. Chỉ đánh dấu scan hoàn tất sau khi enumeration và mọi trang kết thúc hợp lệ, sink đã commit và trạng thái downstream được xác minh. Với idempotent sink, batch giới hạn, retry và resume, ứng dụng có thể duyệt directory lớn mà không phải giữ toàn bộ kết quả trong heap.

### Tài liệu tham khảo

- [Spring LDAP API — `NameClassPairCallbackHandler`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/NameClassPairCallbackHandler.html).
- [Spring LDAP API — `LdapTemplate`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html).
- [Spring LDAP API — `LdapOperations`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html).
- [Spring LDAP Reference — Processing the `DirContext` and Paged Search Results](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html).
- [Spring LDAP API — `PagedResultsControlExchangeDirContextProcessor`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html).
- [Spring LDAP API — `SingleContextSource`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/SingleContextSource.html).
- [RFC 4511 — LDAPv3 Protocol: Search Operation and Controls](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4515 — LDAP Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515).
- [RFC 2696 — LDAP Simple Paged Results Control](https://www.rfc-editor.org/rfc/rfc2696).
