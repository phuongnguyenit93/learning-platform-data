# Phân biệt lỗi mapping với lỗi search

## 1. Bài toán: cùng một lệnh search, nhiều nguyên nhân thất bại

Trong **Spring LDAP**, một ứng dụng có thể dùng `LdapTemplate`, `LdapClient` hoặc ODM (Object-Directory Mapping) để truy cập entry thư mục. Một lệnh tìm nhân viên theo `uid` thường đi qua hai công đoạn khác nhau:

1. **Search:** tạo kết nối qua `ContextSource`, xác thực, gửi base DN/scope/filter tới máy chủ LDAP và nhận các entry hoặc lỗi từ thư mục.
2. **Mapping:** biến entry/attributes trả về thành kiểu dữ liệu của Java, ví dụ `Employee`, DTO, hoặc đối tượng ODM.

Khi ứng dụng chỉ hiển thị thông báo “LDAP search failed”, rất dễ nhầm **lỗi ở phía LDAP search** với **lỗi chuyển đổi entry sang Java**. Thí dụ, filter đúng và server đã trả entry, nhưng code mapping gọi `attrs.get("displayName").get()` trong lúc entry không có `displayName`; kết quả vẫn là một ngoại lệ xuất hiện ngay trong lời gọi `ldapTemplate.search(...)`.

Mục tiêu của bài học trong chương **Debugging** là phân tách hai công đoạn đó bằng bằng chứng, hiểu các triệu chứng điển hình và thiết kế log, code, phép thử để sửa đúng nguyên nhân thay vì thay đổi filter, schema hoặc cấu hình TLS một cách phỏng đoán.

Sau bài học, người học có thể:

- Giải thích đường đi của một truy vấn qua `LdapContextSource`, LDAP server và `AttributesMapper`/`ContextMapper`/ODM.
- Phân biệt **search trả danh sách rỗng**, **search ném exception** và **mapping ném exception**.
- Dùng một mapper chẩn đoán tối thiểu để kiểm tra server có trả entry trước khi xử lý DTO không.
- Xử lý thuộc tính thiếu, nhiều giá trị, sai kiểu, binary và lỗi DN khi mapping.
- Ghi log theo giai đoạn mà không tiết lộ DN, filter value, mật khẩu bind hay dữ liệu cá nhân.
- Lập ma trận kiểm thử tách biệt lỗi kết nối/truy vấn và lỗi ánh xạ.

## 2. Hai giai đoạn trong một lời gọi LdapTemplate.search

~~~mermaid
sequenceDiagram
    participant S as Service
    participant T as LdapTemplate
    participant C as ContextSource
    participant D as LDAP server
    participant M as AttributesMapper
    S->>T: search(base, filter, mapper)
    T->>C: Lấy LDAP context
    C->>D: Kết nối / TLS / bind
    T->>D: SearchRequest
    alt Search thành công, có entry
        D-->>T: SearchResultEntry
        T->>M: mapFromAttributes(entry.attributes)
        alt Mapping hợp lệ
            M-->>T: Java object
            T-->>S: List kết quả
        else Mapping ném exception
            M--xT: Lỗi chuyển đổi
            T--xS: Exception ở lời gọi search
        end
    else Search không có entry
        D-->>T: SearchResultDone (0 entry)
        T-->>S: List rỗng
    else LDAP search lỗi
        D--xT: LDAP error / NamingException
        T--xS: Exception đã được xử lý/chuyển đổi
    end
~~~

Sơ đồ rút gọn đường đi thường gặp; với một số nhà cung cấp JNDI, kết quả được duyệt theo `NamingEnumeration`, nên lỗi mạng, referral, size limit hoặc paging cũng có thể xuất hiện **trong lúc duyệt kết quả**, trước hoặc xen giữa các lần mapper chạy. Vì vậy, thời điểm ném exception trong một stack trace chỉ là một phần bằng chứng: cần xem **giai đoạn thật sự thất bại** và chuỗi nguyên nhân.

### 2.1. Phân biệt ba kết quả quan trọng

| Hiện tượng | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- |
| `search(...)` trả `List` rỗng | Không có object nào được trả về theo truy vấn và cơ chế ánh xạ đang dùng | Chưa chứng minh entry không tồn tại; có thể sai base/scope/filter hoặc ACL che dữ liệu |
| `search(...)` ném lỗi kết nối, filter hoặc LDAP result code | Có vấn đề ở kết nối/LDAP request hoặc lúc đọc kết quả | Chưa được phép kết luận mapper sai |
| Mapper ném `NullPointerException`, `ClassCastException` hoặc lỗi conversion | Có vấn đề khi xử lý một entry hoặc dữ liệu Java tương ứng | Không đồng nghĩa LDAP server không tìm thấy entry |

Một mapper chỉ được gọi khi công đoạn search cung cấp entry cho mapper. Nếu không có entry được xử lý, lỗi kiểu `attrs.get("cn").get()` trong mapper sẽ không tự xuất hiện. Cần phân biệt **không có entry** với **entry có mặt nhưng thiếu thuộc tính mà mapper kỳ vọng**.

## 3. Những lỗi thuộc giai đoạn search

Search không chỉ là chuỗi filter. Nó phụ thuộc kết nối, danh tính bind, base DN, scope, alias/referral, schema và ACL của máy chủ.

| Nhóm lỗi | Biểu hiện có thể gặp | Cách kiểm tra |
| --- | --- | --- |
| DNS/kết nối, server không khả dụng | `CommunicationException`, `ServiceUnavailableException`, timeout | Endpoint thực, network, thời gian kết nối, trạng thái server |
| TLS hoặc xác thực server | Lỗi `SSLHandshakeException`, `PKIX path building failed` trong cause chain | Truststore, SAN/hostname, LDAPS/StartTLS |
| LDAP bind | `AuthenticationException`, mã invalid credentials | Bind DN, credential/secret, chính sách xác thực |
| Base DN không tồn tại | `NameNotFoundException` hoặc LDAP result code tương ứng | Base DN tuyệt đối/tương đối và `ContextSource#setBase` |
| Filter không hợp lệ | `InvalidSearchFilterException` hoặc LDAP filter parsing error | Cách dựng filter, escape input, cấu trúc ngoặc |
| Không đủ quyền xem | Access-control error hoặc truy vấn không thấy entry/attribute | ACL của bind identity, thuộc tính và nhánh được phép |
| Limit, referral, paging | `SizeLimitExceededException`, `PartialResultException` hoặc kết quả không đầy đủ | Search scope, size/time limit, referral policy, controls |

Tên ngoại lệ có thể là loại từ `javax.naming` hoặc ngoại lệ tương ứng trong Spring LDAP vì Spring LDAP thường chuyển đổi lỗi JNDI thành hệ phân cấp runtime exception của mình. Khi chẩn đoán, xem **cause chain**, mã LDAP result và những trường ngữ cảnh thật sự có sẵn; không gán mỗi tên lỗi cho một nguyên nhân duy nhất.

### 3.1. Ví dụ sai base DN

Giả sử `LdapContextSource` cấu hình:

~~~yaml
spring:
  ldap:
    urls: ldaps://directory.example.org:636
    base: dc=example,dc=org
    username: cn=app-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Để tìm nhân viên trong nhánh `ou=people,dc=example,dc=org`, với `LdapQueryBuilder` có thể sử dụng:

~~~java
query().base("ou=people").where("uid").is(uid)
~~~

Giá trị base của query là **tương đối** so với `dc=example,dc=org` đã đặt cho context source. Nếu vô tình truyền cả `ou=people,dc=example,dc=org` vào chỗ API kỳ vọng base tương đối, đường search thực tế có thể không đúng ý định, tùy cách API kết hợp DN. Hãy log **base DN dự kiến đã được cho phép**, kiểm tra cấu hình và sử dụng công cụ LDAP độc lập để đối chiếu.

### 3.2. Ví dụ filter không khớp schema

~~~text
(uid=dev.user)
~~~

Nếu LDAP server dùng `sAMAccountName` hoặc thuộc tính định danh khác thay vì `uid` cho loại entry này, truy vấn có thể trả rỗng dù vẫn có người dùng. Đây là vấn đề **search condition/schema**, không phải lỗi mapping. Một truy vấn rỗng cũng có thể vì entry nằm ở nhánh khác, search scope không phù hợp hoặc bind identity không được phép nhìn thấy entry.

Không tự kết luận “server trả rỗng tức là user không tồn tại” khi chưa biết **base, filter, scope và quyền truy cập**.

## 4. Những lỗi thuộc giai đoạn mapping

Khi LDAP trả về một entry, Spring LDAP có thể nhờ một mapper biến dữ liệu thư mục thành đối tượng Java. Mapper không nên giả định mọi entry luôn đủ thuộc tính hoặc có cùng kiểu dữ liệu.

### 4.1. AttributesMapper và thuộc tính thiếu

Ví dụ dễ lỗi:

~~~java
import org.springframework.ldap.core.AttributesMapper;

AttributesMapper<String> mapper =
    attrs -> (String) attrs.get("displayName").get();
~~~

Nếu `displayName` không có, `attrs.get("displayName")` có thể là `null`, khiến `.get()` ném `NullPointerException`. Search đã có thể tìm thấy entry; lỗi nằm tại **đoạn mapper giả định thuộc tính luôn tồn tại**.

Cách đọc an toàn hơn khi `displayName` là trường tùy chọn:

~~~java
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

static String optionalString(Attributes attrs, String name)
        throws NamingException {
    Attribute attribute = attrs.get(name);
    if (attribute == null || attribute.size() == 0) {
        return null;
    }
    Object raw = attribute.get();
    if (!(raw instanceof String)) {
        throw new IllegalStateException(
            "LDAP attribute has unexpected type: " + name
        );
    }
    return (String) raw;
}
~~~

Chọn giá trị mặc định, cho phép `null` hoặc báo lỗi hợp lệ tùy **hợp đồng DTO**. Không tự thay mọi thuộc tính thiếu thành chuỗi rỗng: điều đó có thể che lỗi dữ liệu nghiêm trọng. Những trường bắt buộc như khóa định danh nên được kiểm tra và thất bại có thông báo kỹ thuật an toàn.

### 4.2. Thuộc tính nhiều giá trị

Một thuộc tính như `memberOf` có thể là **multi-valued** nếu được server cung cấp. Gọi `attribute.get()` chỉ lấy một giá trị (theo API), không đại diện cho toàn bộ tập.

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

static List<String> optionalStrings(Attributes attrs, String name)
        throws NamingException {
    Attribute attribute = attrs.get(name);
    if (attribute == null) {
        return List.of();
    }
    List<String> values = new ArrayList<>();
    NamingEnumeration<?> all = attribute.getAll();
    try {
        while (all.hasMore()) {
            Object raw = all.next();
            if (!(raw instanceof String)) {
                throw new IllegalStateException(
                    "Unexpected LDAP attribute type: " + name
                );
            }
            values.add((String) raw);
        }
    } finally {
        all.close();
    }
    return values;
}
~~~

`memberOf` không phải thuộc tính được mọi LDAP server hỗ trợ với cùng ngữ nghĩa. Một số hệ thống tính thành viên nhóm từ `member` hoặc một cơ chế riêng. Nếu thuộc tính không được trả về, cần kiểm tra **schema và yêu cầu thuộc tính trong search** trước khi kết luận là bug của mapper.

### 4.3. Kiểu dữ liệu không phù hợp

LDAP attributes trả về qua JNDI có thể chứa `String`, `byte[]` hoặc các dạng giá trị khác tùy thuộc tính, schema và cách provider cấu hình. Ví dụ:

- `cn` và `mail` thường được xử lý như chuỗi.
- `jpegPhoto` có thể là `byte[]`; ép trực tiếp sang `String` sẽ gây `ClassCastException`.
- Các thuộc tính thời gian, DN hoặc số đếm có thể cần parse/chuẩn hóa cẩn thận.
- Thuộc tính multi-valued cần được ánh xạ sang collection, không lấy tùy tiện phần tử đầu.

Đừng lấy dữ liệu LDAP chưa kiểm tra để ép kiểu trực tiếp. Nếu sai kiểu, log **tên thuộc tính và loại lỗi** theo chính sách thay vì in toàn bộ giá trị nhạy cảm.

### 4.4. ContextMapper và ODM

`AttributesMapper` chủ yếu đọc tập `Attributes` của entry. `ContextMapper` có thể truy cập một context đại diện cho entry, thường qua `DirContextAdapter`. Mapper này hữu ích khi cần thao tác với DN hoặc biểu diễn directory context, nhưng vẫn phải xử lý thuộc tính tùy chọn và dữ liệu thiếu.

Với **ODM**, mapping được khai báo qua annotation và metadata của class. Các lỗi điển hình gồm:

- Thuộc tính LDAP trong entry không tương thích kiểu field Java.
- Class khai báo field bắt buộc nhưng dữ liệu thực tế thiếu hoặc sai định dạng.
- DN/`@Id`, objectClass hoặc cấu hình annotation không khớp dữ liệu.
- Một mapping kỳ vọng multi-valued nhưng model biểu diễn scalar, hoặc ngược lại.

Không nên coi mọi lỗi ODM là “LDAP server search thất bại”. Search có thể hoàn tất nhưng việc tạo đối tượng, chuyển đổi thuộc tính hoặc gắn DN vào model mới thất bại.

## 5. Cách cô lập lỗi nhanh bằng mapper chẩn đoán tối thiểu

Khi nghi ngờ mapping, một phép thử hữu ích là **giữ nguyên base DN và filter**, nhưng tạm dùng mapper không đọc thuộc tính nhạy cảm.

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

public class DirectoryDiagnostic {
    private final LdapTemplate ldapTemplate;

    public DirectoryDiagnostic(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public int countMappedEntries(String uid) {
        LdapQuery ldapQuery =
            query().base("ou=people").where("uid").is(uid);

        // Mapper không truy cập uid, cn, mail hoặc thuộc tính bắt buộc.
        List<Boolean> entries = ldapTemplate.search(
            ldapQuery,
            (AttributesMapper<Boolean>) attributes -> Boolean.TRUE
        );
        return entries.size();
    }
}
~~~

**Cách diễn giải kết quả:**

- Nếu phép thử này vẫn ném exception, cần điều tra **kết nối, bind, search, referral, limit hoặc đọc kết quả**; nó không còn phụ thuộc vào logic mapping DTO thông thường.
- Nếu phép thử trả số lượng dương nhưng mapper DTO cũ ném exception với **cùng base/filter và cùng điều kiện truy cập**, nguyên nhân nhiều khả năng nằm ở **mapping hoặc dữ liệu một entry**.
- Nếu phép thử trả `0`, không có entry nào được mapper này xử lý; cần xem search base/filter/scope/ACL. Không sửa mapper theo phỏng đoán để “tạo” dữ liệu.

Đây là **công cụ chẩn đoán**, không phải giải pháp production để đếm dữ liệu lớn. `search(...)` có thể materialize toàn bộ kết quả phù hợp, bị giới hạn size/time limit và tốn tài nguyên. Chỉ dùng trên tập dữ liệu lab hoặc truy vấn có phạm vi nhỏ; không lấy danh sách cả thư mục chỉ để đếm.

Nếu phải chẩn đoán trong production, hãy giữ filter và phạm vi an toàn, tránh tăng quyền bind hoặc vô hiệu hóa TLS để thực hiện thử nghiệm.

### 5.1. Giữ cùng ngữ cảnh để so sánh công bằng

Để khẳng định mapper là nguyên nhân, phép thử A/B nên giữ:

1. Cùng LDAP server/endpoint logic, `ContextSource` và danh tính bind.
2. Cùng base DN, filter, search scope, referral policy và các controls liên quan.
3. Cùng danh sách thuộc tính được server trả về khi có thể; nếu query A yêu cầu `displayName` còn query B không yêu cầu, sự khác biệt có thể gây nhầm lẫn.
4. Cùng thời điểm và tập dữ liệu tương đối ổn định; thư mục thay đổi liên tục có thể cho kết quả khác.
5. Cùng phiên bản Spring LDAP/JDK khi đang so sánh với môi trường lỗi.

Chỉ thay **bước mapping** để nhận biết nguyên nhân, tránh đồng thời sửa filter, cấu hình TLS và model rồi không biết yếu tố nào thật sự làm lỗi biến mất.

## 6. Viết mapper có kiểm tra hợp đồng dữ liệu

Thay vì dựa vào ép kiểu và chuỗi gọi `.get()` liên tiếp, mapper nên thể hiện rõ:

- Trường nào **bắt buộc** (ví dụ `uid`).
- Trường nào **tùy chọn** (ví dụ `displayName` trong một số loại entry).
- Trường nào là **multi-valued**.
- Trường nào cần chuyển đổi **binary, số, thời gian hoặc DN**.
- Khi dữ liệu không hợp lệ, báo lỗi với **tên trường và loại sai lệch**, không tự log giá trị thật.

Ví dụ Java dưới đây tạo DTO đơn giản từ các thuộc tính phổ biến:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class EmployeeReader {
    private final LdapTemplate template;

    public EmployeeReader(LdapTemplate template) {
        this.template = template;
    }

    public List<EmployeeView> findByUid(String uid) {
        return template.search(
            query().base("ou=people").where("uid").is(uid),
            (AttributesMapper<EmployeeView>) attrs ->
                new EmployeeView(
                    requiredString(attrs, "uid"),
                    optionalString(attrs, "displayName")
                )
        );
    }

    static String requiredString(Attributes attrs, String name)
            throws NamingException {
        String result = optionalString(attrs, name);
        if (result == null || result.isBlank()) {
            // Giữ tên attribute để debug, không ghi giá trị cá nhân.
            throw new IllegalStateException(
                "Missing required LDAP attribute: " + name
            );
        }
        return result;
    }

    static String optionalString(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            return null;
        }
        Object raw = attribute.get();
        if (!(raw instanceof String)) {
            throw new IllegalStateException(
                "Unexpected LDAP attribute type: " + name
            );
        }
        return (String) raw;
    }

    // Ví dụ dùng Java 17+.
    public record EmployeeView(String uid, String displayName) {}
}
~~~

Mapper ở đây phản ánh **hợp đồng giả định**: `uid` phải là chuỗi và không rỗng, `displayName` có thể thiếu. Nếu hệ thống dùng schema khác, cần thay hợp đồng tương ứng. Java `record` yêu cầu phiên bản Java phù hợp; với dự án cũ có thể dùng DTO class thông thường.

Trường hợp mapper ném `IllegalStateException` có thể biểu thị dữ liệu thư mục không đáp ứng contract. Tùy tầng Spring LDAP và cách lỗi xuất hiện, exception có thể bị chuyển đổi hoặc bao bọc; xem cause chain khi chẩn đoán. Không nên tự bắt mọi lỗi rồi trả object rỗng, vì điều đó có thể làm sai quyết định xác thực hoặc phân quyền.

### 6.1. Cẩn trọng với thuộc tính không yêu cầu trong search

Một số search có thể yêu cầu chỉ một tập attribute nhất định, ví dụ `cn` và `mail`. Nếu mapper bắt buộc `uid` nhưng thao tác tìm kiếm không yêu cầu trả `uid`, kết quả có thể thiếu field dù entry thực tế có lưu `uid`. Trước khi đổ lỗi cho dữ liệu, kiểm tra **search returning attributes** và quyền đọc.

Nếu thuộc tính được phép đọc nhưng không tồn tại trong entry, chọn xử lý theo contract. Nếu server không trả về do ACL, cần phân biệt không có quyền đọc với dữ liệu thiếu bằng kiểm thử cùng định danh bind/entry trong môi trường được phép.

## 7. Debug theo giai đoạn thay vì chỉ bắt một exception chung

Thiết kế chẩn đoán nên đặt **ngữ cảnh search** gần nơi khởi tạo query, và **ngữ cảnh mapping** gần nơi biến attributes thành DTO.

~~~mermaid
flowchart TD
    A["Lỗi phát sinh trong search(...)"] --> B{"Có bằng chứng kết nối/bind/TLS hoặc LDAP result code?"}
    B -- "Có" --> S["Điều tra SEARCH / NETWORK / AUTH"]
    B -- "Chưa rõ" --> C["Thử cùng query với mapper tối thiểu"]
    C --> D{"Mapper tối thiểu cũng lỗi?"}
    D -- "Có" --> S
    D -- "Không" --> E{"Có entry được xử lý?"}
    E -- "Không" --> F["Kiểm tra base DN, filter, scope, ACL"]
    E -- "Có" --> M["Kiểm tra MAPPING: thiếu attribute, kiểu, ODM"]
    S --> R["Thử lại theo chính sách an toàn"]
    F --> R
    M --> R
~~~

### 7.1. Ghi log operation, stage và nguyên nhân

Một sự kiện log hữu ích có thể mang các trường:

~~~text
event=ldap.operation.failed
operation=SEARCH
stage=MAPPING
target=primary_directory
base_dn=ou=people,dc=example,dc=org
filter_template=(uid={value})
filter_params=[REDACTED]
mapper=EmployeeViewMapper
attribute=displayName
error_type=IllegalStateException
trace_id=9b20f1d8
~~~

Log này mô tả **một ví dụ giả định**; chỉ ghi `stage=MAPPING` nếu có bằng chứng từ vị trí ném lỗi, instrumentation hoặc wrapper của mapper. Nếu chỉ thấy `ldapTemplate.search(...)` ném exception mà không rõ nguyên nhân, ghi `stage=UNKNOWN` thay vì đoán.

Giữ **base DN và filter shape** giúp nối lỗi với thao tác gốc; không ghi mặc định UID, email, giá trị filter, mật khẩu bind, entry đầy đủ hay các giá trị thuộc tính nhạy cảm. Nếu DN có RDN là tên cá nhân, cần che theo chính sách. Trace ID có thể giúp tra cứu sự cố giữa tầng web, service và LDAP client mà không phải đưa thông tin người dùng vào log.

### 7.2. Tại sao stack trace và cause chain vẫn quan trọng?

Stack trace giúp định vị nơi lỗi phát sinh:

- `javax.naming...`, JNDI search, bind, TLS hoặc response parsing: hướng điều tra kết nối/search.
- Một dòng trong lambda `AttributesMapper`, DTO converter, ODM metadata hoặc `DirContextAdapter`: hướng điều tra mapping.
- Hỗn hợp các frame: đọc **nguyên nhân gốc và context**; không chỉ dựa vào tên method `search` xuất hiện trên stack.

Spring LDAP có thể chuyển đổi `javax.naming.NamingException` thành ngoại lệ runtime trong hệ phân cấp Spring LDAP. Trong trường hợp mapper ném Java runtime exception khác, cách propagation tùy mã và thư viện. Đừng dựa vào giả định rằng mọi ngoại lệ thoát ra từ `search(...)` đều là “LDAP query invalid”.

Không in toàn bộ exception message/stack trace chứa DN hoặc giá trị LDAP vào log rộng quyền nếu chưa kiểm tra rủi ro rò rỉ. Có thể lưu thông tin đầy đủ trong kênh chẩn đoán có phân quyền khi chính sách cho phép.

## 8. Tránh sửa sai chỗ và tránh retry không phù hợp

| Dấu hiệu | Cách sửa sai thường gặp | Điều cần làm |
| --- | --- | --- |
| Mapper lỗi vì thiếu `displayName` | Đổi URL LDAP hoặc tắt TLS | Kiểm tra field optional/required, returning attributes và schema |
| Filter theo `uid` trả `0` | Thêm giá trị mặc định trong mapper | Kiểm tra base, scope, thuộc tính định danh, ACL |
| `PKIX path building failed` | Đổi mapper DTO | Sửa truststore, server chain hoặc CA đúng quy trình |
| `ClassCastException` với `jpegPhoto` | Retry search liên tục | Sửa kiểu dữ liệu mapping, dùng `byte[]` khi phù hợp |
| `NameNotFoundException` | Cho mapper bắt `NullPointerException` | Kiểm tra DN và đường search thực tế |
| Search trả entry nhưng mapper yêu cầu `memberOf` | Coi việc thiếu `memberOf` là server mất kết nối | Kiểm tra schema, ACL, cách quản lý membership, xử lý optional/multi-value |
| Server reset socket | Tắt kiểm tra mapping | Điều tra mạng/pooling, invalidate context hỏng, retry đọc có giới hạn |

**Mapping exception thường không được khắc phục bằng retry**, vì cùng dữ liệu và cùng code thường sẽ lỗi lặp lại. Lỗi kết nối tạm thời ở thao tác chỉ đọc có thể retry có giới hạn trên kết nối TLS hợp lệ. Với `ADD`, `MODIFY` hoặc `DELETE`, cẩn trọng vì server có thể đã áp dụng thay đổi trước khi client nhận lỗi; không retry mù quáng.

Không tăng quyền LDAP hoặc tắt certificate verification để “thấy đầy đủ attribute” khi debug. Phải điều tra trong môi trường có thẩm quyền, với tài khoản và truy cập phù hợp.

## 9. Quy trình debug từng bước trong một sự cố thật

Giả sử API trả HTTP 500 khi tìm nhân viên theo `uid`. Đội vận hành thấy `ldapTemplate.search(...)` xuất hiện trong stack trace. Cách xử lý có thể đi theo thứ tự:

1. **Ghi nhận trace ID, operation, target alias và thời điểm**. Không copy thông tin xác thực vào ticket.
2. **Xác nhận kết nối/bind/TLS:** ứng dụng có kết nối được tới LDAP server và xác minh chứng chỉ không? Lỗi có xảy ra trước search không?
3. **Xác nhận base, filter, scope và ACL:** dùng query shape đã sanitize; nếu cần tái hiện, dùng dữ liệu giả hoặc một account thử nghiệm được phép.
4. **Quan sát số entry mapper nhận:** dùng mapper chẩn đoán tối thiểu trên phạm vi nhỏ, cùng query và ngữ cảnh.
5. **Nếu entry có mặt, kiểm tra contract mapping:** thuộc tính bắt buộc, optional, multi-value, binary, kiểu Java, object class và metadata ODM.
6. **So sánh theo dữ liệu:** một entry hợp lệ và một entry gây lỗi trong lab; không đổ mọi lỗi cho toàn bộ thư mục.
7. **Thêm kiểm thử hồi quy:** giữ test search riêng, test mapper riêng và test tích hợp qua `LdapTemplate`, bảo đảm không tái phát.
8. **Giữ bảo mật:** tiếp tục LDAPS/StartTLS, không thêm raw filter/PII/password vào log và không cấp quyền quá mức để “thử nhanh”.

Nếu lỗi chỉ xuất hiện sau khi deployment mới, hãy so sánh thay đổi DTO, mapper, annotation ODM và returning attributes. Nếu lỗi xuất hiện sau khi LDAP schema/dữ liệu thay đổi, hãy kiểm tra tương thích ngược và quy tắc populate field.

## 10. Kiểm thử tách search với mapping

Một chiến lược kiểm thử tốt gồm **unit test mapper**, **integration test search** và **test xử lý lỗi/log**. Mỗi loại kiểm tra một ranh giới khác nhau:

| Tình huống | Dữ liệu/thiết lập thử nghiệm | Kết quả dự kiến |
| --- | --- | --- |
| Search đúng và có entry | LDAP server lab có người dùng và filter khớp | Mapper nhận entry, trả DTO hợp lệ |
| Search không có entry | Base/filter hợp lệ nhưng không khớp | List rỗng; mapper không được gọi |
| Sai base DN | Base không tồn tại | Lỗi search hoặc kết quả theo hành vi server được xác nhận; không đổ cho mapper |
| Sai filter syntax | Filter không hợp lệ trong lab | Lỗi search/filter được nhận diện |
| Bind sai mật khẩu | Credential thử nghiệm không hợp lệ | Lỗi AUTH/BIND trước mapping |
| Chứng chỉ server sai | LDAPS/StartTLS với CA/SAN không hợp lệ | TLS bị từ chối, không bind rõ |
| Thiếu thuộc tính bắt buộc | Entry test không có `uid` | Mapper trả lỗi contract cụ thể |
| Thiếu thuộc tính tùy chọn | Entry không có `displayName` | DTO có giá trị optional đã được quyết định theo contract |
| Thuộc tính nhị phân | `jpegPhoto` dưới dạng `byte[]` | Mapper phù hợp hoặc lỗi type rõ ràng |
| Multi-valued attribute | Có hai giá trị nhóm | Mapper giữ đủ giá trị, không chỉ phần tử đầu |
| ODM metadata sai | Class mapping không phù hợp với entry test | Lỗi mapping/metadata được nhận diện |
| Kết quả giới hạn/referral | Search với limit và referral policy cụ thể | Phân biệt lỗi partial result/limit với mapper |

### 10.1. Unit test mapper với Attributes giả

Có thể kiểm tra mapper mà không cần mở kết nối LDAP bằng `BasicAttributes` và `BasicAttribute` của JNDI:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.junit.jupiter.api.Test;

class EmployeeMappingTest {
    @Test
    void missingOptionalDisplayNameIsAccepted() throws Exception {
        BasicAttributes attrs = new BasicAttributes(true);
        attrs.put(new BasicAttribute("uid", "test.user"));

        String uid = EmployeeReader.requiredString(attrs, "uid");
        String displayName =
            EmployeeReader.optionalString(attrs, "displayName");

        assertEquals("test.user", uid);
        assertEquals(null, displayName);
    }

    @Test
    void missingRequiredUidIsRejected() {
        BasicAttributes attrs = new BasicAttributes(true);
        assertThrows(
            IllegalStateException.class,
            () -> EmployeeReader.requiredString(attrs, "uid")
        );
    }
}
~~~

Ví dụ dùng JUnit Jupiter và các helper từ `EmployeeReader` đã trình bày ở mục 6. Mục đích là kiểm tra **hợp đồng chuyển đổi**; không thử server search, permission, network hay TLS. Tại dự án thật, nên đặt mapper ở một class riêng và test trực tiếp để cô lập trách nhiệm, thay vì gắn cứng logic vào một lambda khó dùng lại.

### 10.2. Test tích hợp với LDAP lab

Trong môi trường thử nghiệm được phép, chuẩn bị ít nhất hai entry:

~~~text
uid=test.valid,ou=people,dc=example,dc=org
  objectClass: inetOrgPerson
  uid: test.valid
  cn: Test Valid
  sn: Valid
  displayName: Test Valid

uid=test.no-display,ou=people,dc=example,dc=org
  objectClass: inetOrgPerson
  uid: test.no-display
  cn: Test Without Display
  sn: Display
  (không có displayName)
~~~

Dùng query `(uid=test.valid)` để kiểm tra đường search và mapper đều thành công. Dùng `(uid=test.no-display)` để kiểm tra optional field; dùng một mapper cố tình yêu cầu `displayName` để mô phỏng lỗi mapping, trong khi mapper tối thiểu vẫn chứng minh server tìm thấy entry. Trường hợp entry thiếu `uid` có thể cần một object class/schema phù hợp trong lab; không cố chèn dữ liệu vi phạm schema của server chỉ để tạo test, vì lỗi khi thêm entry là lỗi **schema/write**, không phải lỗi mapping lúc search.

## 11. Bài thực hành: có entry nhưng API vẫn báo “search failed”

**Bối cảnh:** Một dịch vụ nhân sự cấu hình `LdapContextSource` với base `dc=example,dc=org` và kết nối LDAPS. Code:

~~~java
List<String> names = ldapTemplate.search(
    query().base("ou=people").where("uid").is(userUid),
    (org.springframework.ldap.core.AttributesMapper<String>)
        attrs -> (String) attrs.get("displayName").get()
);
~~~

Một người dùng có `uid=test.no-display`, `cn=Test Without Display` nhưng không có `displayName`. Yêu cầu API gặp `NullPointerException` ở lambda mapper. Trong khi đó, công cụ `ldapsearch` trong lab cho thấy filter `(uid=test.no-display)` có entry.

**Câu hỏi:**

1. Vì sao tên method `search` trong stack trace chưa đủ để nói server search lỗi?
2. Phép thử tối thiểu nào xác nhận entry đã được search trả về?
3. Sửa mapper thế nào nếu `displayName` là optional, và nếu nó là required?
4. Nếu sau khi sửa mapper mà kết quả là list rỗng, nên kiểm tra những gì?
5. Những thông tin nào nên xuất hiện trong log chẩn đoán nhưng không làm lộ PII?

**Hướng giải:**

1. `search(...)` bao gồm cả bước chuyển entry thành Java object; `NullPointerException` xuất hiện trong lambda vì `attrs.get("displayName")` là `null`. Chưa có bằng chứng lỗi từ LDAP server.
2. Dùng cùng query với mapper `attrs -> Boolean.TRUE` trên tập nhỏ; kết quả dương cho thấy entry đi tới mapper. Kiểm tra thêm số entry, returning attributes và bind identity khi cần.
3. Nếu optional, xử lý `null` theo contract (ví dụ fallback sang `cn` nếu nghiệp vụ cho phép). Nếu required, báo lỗi dữ liệu rõ tên field và sửa dữ liệu/schema hoặc validation thích hợp, không che lỗi bằng chuỗi rỗng tùy tiện.
4. Kiểm tra base DN, filter, search scope, quyền bind, thuộc tính định danh, referral và sự khác nhau giữa môi trường/cấu hình.
5. Ghi `operation=SEARCH`, `stage=MAPPING` nếu đã xác nhận, `target`, base DN đã cho phép, filter template, tên thuộc tính `displayName`, exception type và trace ID; che giá trị UID, mật khẩu và nội dung entry.

## 12. Checklist ghi nhớ

- [ ] Phân biệt **search trả rỗng**, **LDAP search ném exception** và **mapper/ODM ném exception**.
- [ ] Giữ cùng endpoint, bind identity, base DN, filter, scope và returning attributes khi thử mapper tối thiểu.
- [ ] Kiểm tra attribute **required/optional**, multi-valued, binary, kiểu Java và mapping DN/ODM metadata.
- [ ] Không suy đoán lỗi mapper từ việc method `search(...)` xuất hiện trong stack trace; xem cause chain và vị trí ném lỗi.
- [ ] Ghi log theo **operation, stage và trace ID**, bảo vệ DN/filter value, PII và thông tin xác thực.
- [ ] Không sửa sai chỗ bằng cách tắt TLS, tăng quyền LDAP hoặc retry một lỗi mapping có tính quyết định.
- [ ] Viết unit test mapper và integration test LDAP trên dữ liệu lab đại diện, gồm ca entry thiếu thuộc tính và search không có kết quả.

**Kết luận:** Trong Spring LDAP, **search tìm entry** và **mapping biến entry thành đối tượng Java** là hai trách nhiệm khác nhau nằm trong cùng một luồng API. Tách giai đoạn, giữ ngữ cảnh kiểm chứng và thử mapper tối thiểu sẽ giúp tìm đúng nguyên nhân, sửa đúng lớp và tránh những thay đổi rủi ro đối với kết nối hay dữ liệu thư mục.
