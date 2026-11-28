# Đọc danh bạ lớn bằng phân trang LDAP

Một ứng dụng Spring Boot cần xuất danh bạ gồm hàng chục nghìn entry LDAP để đối soát dữ liệu. Cách đơn giản là gọi `ldapTemplate.search(...)`, gom toàn bộ kết quả vào một `List` rồi xử lý. Nhưng directory server thường giới hạn số entry của một truy vấn, còn ứng dụng có thể hết bộ nhớ, timeout hoặc ngộ nhận rằng “1.000 kết quả nhận được” là toàn bộ 30.000 người dùng.

Trong bài **Thực hành** thuộc module **SPRING_DATA_LDAP**, chúng ta xây dựng một chương trình đọc directory **theo từng trang bằng Simple Paged Results (RFC 2696)**. Spring Data LDAP cung cấp repository/ODM ánh xạ entry Java, trong khi `LdapTemplate` của Spring LDAP có thể gửi các LDAP search control chuyên biệt. Bài tập sẽ sử dụng context kết nối, filter theo `objectClass`, DN/base/scope, mapper, cookie phân trang và cơ chế kiểm thử với directory thật. Mọi thao tác đều phải giữ filter an toàn, ACL đọc tối thiểu và kết nối TLS đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa server-side paging, `countLimit` và phân trang một danh sách Java đã tải.
2. Kiểm tra máy chủ có hỗ trợ RFC 2696, control OID `1.2.840.113556.1.4.319` hay không.
3. Tạo search có base DN, scope, filter, danh sách attribute và page size phù hợp.
4. Dùng `PagedResultsControlExchangeDirContextProcessor` và `SingleContextSource` trên Spring LDAP 4.1+ để đọc nhiều trang trên **cùng LDAP connection**.
5. Xử lý từng trang mà không giữ toàn bộ directory trong bộ nhớ.
6. Kiểm thử danh bạ **2.505 entry**, page size **250**, phát hiện lỗi cookie, thiếu/trùng entry và mất kết nối.
7. Phân biệt quét đầy đủ với scan bị cắt hoặc thất bại; hiểu vì sao paging **không bảo đảm snapshot nhất quán**.

**Kết quả thực hành:** Một service Java chỉ đọc OU test `ou=practice`, trả thống kê tổng số trang và entry sau khi server báo hết trang. Bài có bước tạo dữ liệu mẫu, chạy `ldapsearch` đối chiếu, kiểm thử lỗi và bài tập mở rộng. Không áp dụng các thao tác tạo/xóa lên directory production.

## 2. Cách Simple Paged Results hoạt động

RFC 2696 định nghĩa một request control chứa kích thước trang và **cookie**. Server gửi một nhóm kết quả cùng response control; nếu còn dữ liệu, cookie được dùng cho lần search kế tiếp. Khi đã hết, server gửi trạng thái cookie kết thúc.

~~~text
Spring Boot                     LDAP server
    |                               |
    |-- search(size=250, cookie=∅) ->|
    |<-- 250 entry + cookie A ------|
    |                               |
    |-- search(size=250, cookie=A) ->|
    |<-- 250 entry + cookie B ------|
    |              ...              |
    |-- search(size=250, cookie=J) ->|
    |<-- 5 entry + cookie kết thúc --|
    |                               |
  xử lý đủ 2.505 entry
~~~

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Page size** | Số entry client đề nghị server trả trong một response. |
| **Request control** | Control RFC 2696, có page size và cookie của trang trước. |
| **Response control** | Control trả về cookie tiếp tục; tổng số entry nếu có chỉ là ước lượng do server cung cấp. |
| **Cookie** | Giá trị nhị phân *opaque*, do server tạo, không phải số thứ tự trang. |
| **Base/filter/scope** | Phạm vi tìm kiếm; phải giữ nguyên trong một chuỗi paging. |
| **Connection** | Cần được giữ nhất quán giữa các trang theo hợp đồng Spring LDAP, vì cookie có thể phụ thuộc connection/server. |

**Không kết luận trang cuối chỉ vì `page.size() < PAGE_SIZE`.** Server có thể trả ít hơn page size vì chính sách của nó. Tín hiệu hoàn tất phải đến từ response control/cookie, qua `processor.hasMore()`.

### Ba cách đọc khác nhau

| Phương pháp | Có thể tiếp tục lấy trang kế tiếp? | Rủi ro |
| --- | --- | --- |
| Lấy toàn bộ rồi dùng `subList()`. | Chỉ khi đã tải được toàn bộ dữ liệu. | Chiếm RAM và có thể chạm server size limit. |
| `countLimit(250)` / `SearchControls.setCountLimit(250)`. | **Không**, giới hạn số kết quả không tự tạo cookie. | Gọi lặp một search có thể trả lại cùng 250 entry. |
| RFC 2696 **Simple Paged Results**. | **Có**, nếu server hỗ trợ và client gửi cookie đúng cách. | Cần quản lý kết nối, control, lỗi và trạng thái scan. |

### Vòng lặp xử lý

~~~mermaid
flowchart TD
    A["Tạo context đọc LDAP"] --> B["Tạo processor, pageSize=250"]
    B --> C["Search cố định base + filter + scope"]
    C --> D["Nhận một trang + response control"]
    D --> E["Ánh xạ và xử lý trang"]
    E --> F{"Có cookie tiếp tục?"}
    F -- "Có" --> C
    F -- "Không" --> G["Kết thúc scan thành công, đóng context"]
    C -- "Timeout / lỗi ACL / control" --> H["Scan FAILED, dữ liệu chỉ là partial"]
    E -- "Lỗi consumer/DB" --> H
~~~

## 3. Môi trường và phạm vi bài thực hành

Giả sử một LDAP server hỗ trợ `inetOrgPerson`, `uid` và RFC 2696 với cây:

~~~text
dc=example,dc=org
├── ou=practice
│   ├── uid=practice0001
│   ├── uid=practice0002
│   ├── ...
│   └── uid=practice2505
└── ou=services
    ├── cn=lab-reader
    └── cn=lab-writer
~~~

Một entry mẫu:

~~~ldif
dn: uid=practice0001,ou=practice,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: practice0001
cn: Practice 0001
sn: Example
mail: practice0001@example.org
~~~

### 3.1. Điều kiện cần

- JDK/Spring Boot và dependency `spring-boot-starter-data-ldap` phù hợp với phiên bản Spring LDAP.
- Một directory **test** hỗ trợ paged search; **không giả định** mọi LDAP server đều hỗ trợ RFC 2696.
- Công cụ `ldapsearch` có hỗ trợ tham số `-E pr=...` để đối chiếu.
- Tài khoản `lab-reader` có quyền bind/search/read trên `ou=practice` và các attribute cần dùng.
- Chỉ khi seed dữ liệu, tài khoản `lab-writer` được cấp quyền **thêm entry test**, không cần quyền quản trị toàn directory.

Với Active Directory, bộ lọc và attribute có thể là `objectClass=user`, `sAMAccountName`, `objectGUID` và base DN khác. Ví dụ hiện tại dùng schema `inetOrgPerson`/`uid` để lab dễ hiểu; không sao chép cấu hình này sang AD mà không kiểm tra schema.

### 3.2. Kiểm tra control paging

LDAP root DSE có thể công bố các control hỗ trợ qua `supportedControl`:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=lab-reader,ou=services,dc=example,dc=org" -W \
  -b "" -s base "(objectClass=*)" supportedControl
~~~

Tìm OID `1.2.840.113556.1.4.319`. Nếu không thấy, kiểm tra quyền đọc root DSE, tài liệu server và chạy thử truy vấn paging trên môi trường test. Không bỏ qua một lỗi **unsupported control** rồi coi trang đầu là toàn bộ dữ liệu.

Thử phân trang ngay trên CLI:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=lab-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=practice,dc=example,dc=org" -s sub \
  -E pr=250/noprompt \
  "(objectClass=inetOrgPerson)" dn uid cn
~~~

`-E pr=250/noprompt` là cú pháp OpenLDAP `ldapsearch` để yêu cầu paged results và tự tiếp tục. `-W` nhập password tương tác; không đưa mật khẩu vào command line. **CLI thành công không chứng minh Java tự giữ cùng connection**, vì hai client có cơ chế quản lý context khác nhau.

## 4. Tạo 2.505 entry thử nghiệm

Nếu OU test đã có dữ liệu đủ lớn và biết chắc số lượng, bạn có thể bỏ qua bước này. Nếu không, bảo đảm entry cha `ou=practice` tồn tại. LDIF tạo OU khi chưa có:

~~~ldif
dn: ou=practice,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: practice
~~~

Sau khi tạo OU **trong directory thử nghiệm được cấp quyền**, tại terminal có shell POSIX, sinh tệp LDIF:

~~~bash
for n in $(seq 1 2505); do
  id=$(printf "practice%04d" "$n")
  cat <<EOF
dn: uid=${id},ou=practice,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: ${id}
cn: Practice ${n}
sn: Example
mail: ${id}@example.org

EOF
done > /tmp/ldap-practice-paging.ldif
~~~

Kiểm tra nội dung file trước khi chạy `ldapadd`. Nạp dữ liệu vào **directory test**, không phải production:

~~~bash
ldapadd -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=lab-writer,ou=services,dc=example,dc=org" -W \
  -f /tmp/ldap-practice-paging.ldif
~~~

Nếu đã chạy seed trước đó, server có thể báo entry trùng. Đừng tự xóa OU hoặc ghi đè dữ liệu mà không xác minh; dùng một nhánh test riêng để tránh ảnh hưởng tài khoản khác. Những entry đều là dữ liệu giả, không chứa thông tin cá nhân thật.

## 5. Cấu hình Spring Boot và dependency

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

`application.yml`:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
    base-environment:
      com.sun.jndi.ldap.connect.timeout: "3000"
      com.sun.jndi.ldap.read.timeout: "7000"
~~~

Ví dụ biến môi trường:

~~~dotenv
LDAP_URL=ldaps://ldap.example.org:636
LDAP_BASE_DN=dc=example,dc=org
LDAP_BIND_DN=cn=lab-reader,ou=services,dc=example,dc=org
LDAP_BIND_PASSWORD=<secret-cua-moi-truong>
~~~

Các timeout `3000/7000 ms` chỉ minh họa cho JNDI LDAP provider của JVM, không phải SLA của toàn job. `ldaps://` yêu cầu chứng chỉ máy chủ hợp lệ và CA/hostname được JVM tin cậy. Nếu dùng `ldap://`, cần bật StartTLS tường minh; không coi LDAP cổng 389 là đã mã hóa.

Với `spring.ldap.base=dc=example,dc=org`, search base `ou=practice` là **tương đối với context base**. Truy vấn thực tế bắt đầu từ `ou=practice,dc=example,dc=org`. Không ghép lặp context base hoặc cho client HTTP tự gửi base DN rộng.

### 5.1. Lựa chọn API theo phiên bản

Tài liệu Spring LDAP mới dùng `PagedResultsControlExchangeDirContextProcessor` (có từ Spring LDAP **4.1**) cùng `SingleContextSource`. Các phiên bản trước dùng `PagedResultsDirContextProcessor`, nay được đánh dấu deprecated trong API mới.

| Phiên bản Spring LDAP | API dùng cho lab |
| --- | --- |
| **4.1+** | `PagedResultsControlExchangeDirContextProcessor`. |
| **Trước 4.1** | `PagedResultsDirContextProcessor`, với cơ chế `getCookie()/hasMore()` tương ứng. |

**Ví dụ Java chính dưới đây dành cho Spring LDAP 4.1+.** Trước khi copy vào dự án, kiểm tra version được Spring Boot BOM quản lý. Không cố import class 4.1 vào dự án chỉ có Spring LDAP 3.x. Dù dùng API cũ hay mới, yêu cầu **same underlying connection** giữa các lần gọi vẫn quan trọng.

## 6. Viết service đọc từng trang

Mục tiêu của service:

- Tìm tất cả entry phù hợp filter cố định dưới OU test.
- Mỗi lần chỉ giữ một trang `List<PersonRow>`.
- Mapper chỉ lấy `uid`, `cn`, `mail`.
- Một paging processor tồn tại xuyên suốt vòng lặp.
- Một `SingleContextSource` cung cấp **cùng context** cho mọi trang.
- Trả `ScanStats` **chỉ sau khi** server báo hết trang.

### 6.1. Mã Java minh họa đầy đủ — Spring LDAP 4.1+

~~~java
import java.util.List;
import java.util.function.Consumer;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.SingleContextSource;
import org.springframework.stereotype.Service;

@Service
public final class PagedDirectoryReader {

    private static final String BASE = "ou=practice";
    private static final String FILTER = "(objectClass=inetOrgPerson)";
    private static final int PAGE_SIZE = 250;
    private static final int MAX_PAGES = 100;

    private final ContextSource contextSource;

    public PagedDirectoryReader(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public record PersonRow(
            String uid, String fullName, String email) {}

    public record ScanStats(int pages, long entries) {}

    private static final AttributesMapper<PersonRow> MAPPER = attrs ->
            new PersonRow(
                    stringValue(attrs, "uid"),
                    stringValue(attrs, "cn"),
                    stringValue(attrs, "mail"));

    public ScanStats scan(Consumer<PersonRow> consumer) {
        if (consumer == null) {
            throw new IllegalArgumentException("consumer bat buoc");
        }

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(
                new String[] {"uid", "cn", "mail"});
        controls.setTimeLimit(5000); // cho tung LDAP search

        var pager =
                new PagedResultsControlExchangeDirContextProcessor(
                        PAGE_SIZE);

        // Cung context LDAP duoc giu trong toan bo callback.
        return SingleContextSource.doWithSingleContext(
                contextSource,
                operations -> {
                    int pages = 0;
                    long entries = 0;

                    do {
                        if (pages >= MAX_PAGES) {
                            throw new IllegalStateException(
                                    "Scan vuot so trang cho phep");
                        }

                        List<PersonRow> page = operations.search(
                                BASE, FILTER, controls, MAPPER, pager);

                        pages++;
                        for (PersonRow person : page) {
                            consumer.accept(person);
                            entries++;
                        }
                    } while (pager.hasMore());

                    return new ScanStats(pages, entries);
                },
                true,  // context chi doc
                false, // khong bo qua PartialResultException
                false  // khong bo qua NameNotFoundException
        );
    }

    private static String stringValue(
            Attributes attrs, String name) throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null) {
            return null;
        }
        Object value = attribute.get();
        return value == null ? null : value.toString();
    }
}
~~~

### 6.2. Giải thích từng thành phần

**`ContextSource`.** Spring Boot cung cấp context kết nối theo `spring.ldap.*` khi auto-configuration phù hợp. Trong ví dụ, service nhận `ContextSource` để dùng với `SingleContextSource`; tài khoản bind có quyền chỉ đọc OU test.

**`SearchControls`.** `SUBTREE_SCOPE` tìm cả OU và mọi entry dưới OU test; `setReturningAttributes` giảm payload còn ba trường. `setTimeLimit(5000)` áp dụng cho từng search, **không** cho toàn bộ nhiều trang. Một page có thể trả ít entry hơn `PAGE_SIZE` theo chính sách server.

**Paging processor.** `PagedResultsControlExchangeDirContextProcessor` gắn paged results control vào LDAP context, đọc response control và giữ cookie để dùng ở lần search kế tiếp. `pager.hasMore()` báo có cần thêm trang hay không.

**`SingleContextSource`.** Đây là phần cốt lõi. Spring LDAP có thể đóng context sau mỗi lời gọi `LdapTemplate.search` thông thường. Cookie phân trang có thể chỉ hợp lệ trên cùng connection/server; `SingleContextSource.doWithSingleContext` giữ cùng underlying context xuyên suốt callback rồi giải phóng khi kết thúc, kể cả khi xảy ra lỗi.

**`operations.search(...)`.** Callback nhận `LdapOperations` (API template) với overload hỗ trợ `SearchControls`, `AttributesMapper` và `DirContextProcessor`. Đây là cách làm theo Spring LDAP template, không tự quản lý `DirContext.search` ở mỗi trang.

**`consumer.accept(person)`.** Chỉ xử lý các entry của trang hiện tại. Không có danh sách toàn bộ danh bạ được gom vào RAM. Một consumer production phải được thiết kế idempotent và không nên giữ cả triệu entry trong một danh sách khác.

**`MAX_PAGES`.** Nếu vượt giới hạn trong khi còn cookie, service **báo lỗi**, không trả trạng thái thành công thiếu dữ liệu. Hạn mức 100 cho lab 2.505 entry; trong hệ thống thật phải gắn với SLA, quy mô và cảnh báo vận hành.

### 6.3. Vì sao không chỉ gọi `LdapRepository.findAll()`?

Repository/LDAP ODM thuận tiện cho entity `@Entry`, `@Id` và các truy vấn theo thuộc tính như `findByUid`. Tuy nhiên, **đừng mặc định `findAll()` hoặc `findBy...` tự triển khai RFC 2696**. Khi cần kiểm soát paged results control/cookie và connection, dùng API Spring LDAP chuyên biệt như trong lab.

`countLimit(250)` trong `LdapQueryBuilder` hay `SearchControls` không biến một truy vấn thành phân trang server-side. Tương tự, chia một `List` sau khi đã tải không khắc phục size limit do directory áp đặt.

## 7. Chạy lab và đo kết quả

Ví dụ gọi từ một job hoặc integration test đã inject `PagedDirectoryReader reader`:

~~~java
PagedDirectoryReader.ScanStats stats = reader.scan(person -> {
    if (person.uid() == null || person.uid().isBlank()) {
        throw new IllegalStateException("UID trong lab bi thieu");
    }
    // Co the xu ly theo batch; khong log PII.
});

System.out.printf("pages=%d, entries=%d%n",
        stats.pages(), stats.entries());
~~~

Với đúng 2.505 entry và server phục vụ tối đa 250 entry mỗi lần, dự kiến:

~~~text
pages=11, entries=2505
~~~

Phép tính:

~~~text
10 trang x 250 = 2.500 entry
 1 trang x 5   =     5 entry
                  -----------
                   2.505 entry
~~~

**Số trang thực tế có thể khác** do server quyết định kích thước response. Số entry xử lý được và tín hiệu `hasMore() == false` mới là căn cứ xác nhận vòng lặp đã kết thúc, sau khi không có lỗi.

### 7.1. So sánh với công cụ dòng lệnh

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=lab-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=practice,dc=example,dc=org" -s sub \
  -E pr=250/noprompt \
  "(objectClass=inetOrgPerson)" dn \
  | grep -c '^dn:'
~~~

Trong fixture không thay đổi, kết quả mong đợi là `2505`. Lệnh `grep` chỉ là kiểm tra nhanh; nếu `ldapsearch` lỗi giữa các trang, pipeline có thể vẫn in con số thiếu. Hãy kiểm tra **exit status và stderr của LDAP command** trước khi tin số đếm.

### 7.2. Thử phát hiện kết quả trùng

Vì dữ liệu lab được tạo với UID duy nhất, có thể dùng `Set` trong test:

~~~java
import java.util.HashSet;
import java.util.Set;

Set<String> seen = new HashSet<>();
PagedDirectoryReader.ScanStats result = reader.scan(person -> {
    if (!seen.add(person.uid())) {
        throw new IllegalStateException("Trung UID trong lab");
    }
});

if (result.entries() != 2505 || seen.size() != 2505) {
    throw new IllegalStateException("Scan lab chua day du");
}
~~~

**Không sử dụng tập `HashSet` chứa hàng triệu UID trong production**. Với đồng bộ thật, lưu trạng thái và upsert theo stable external ID trong database có unique constraint; `uid`, email và DN có thể thay đổi hoặc được cấp lại.

## 8. Cookie không phải số trang hay checkpoint dài hạn

Cookie RFC 2696 là dữ liệu opaque của server. Nó không phải `offset`, không phải một mã trang HTTP có thể lưu nhiều giờ, và không phải một checkpoint bền vững của job.

### 8.1. Vì sao không chuyển cookie giữa hai server?

~~~text
Trang 1: server A -> cookie A
Trang 2: server B <- cookie A  (có thể không hợp lệ)
~~~

Nếu dùng nhiều LDAP URL, load balancer hoặc connection pooling, phải kiểm tra việc giữ cùng connection trong chuỗi paging. **Failover giữa chừng** không đồng nghĩa có thể tiếp tục cookie cũ trên backend mới.

Nếu mất kết nối ở trang 4, hãy đánh dấu scan **FAILED**. Thực hiện lại một chuỗi scan mới hoặc dùng cơ chế đồng bộ incremental do provider hỗ trợ, thay vì mang cookie cũ sang context mới và đoán rằng nó còn hợp lệ.

### 8.2. Vì sao trang ngắn không có nghĩa là đã hết?

Không viết:

~~~java
// SAI: do dai trang khong thay the server response cookie.
if (page.size() < PAGE_SIZE) {
    break;
}
~~~

Đúng là kiểm tra `pager.hasMore()` **sau** search. Nếu server trả trang rỗng nhưng vẫn còn cookie, client phải xử lý trạng thái theo protocol, có giới hạn vòng lặp/deadline để không treo vô hạn.

### 8.3. Nếu server không hỗ trợ control?

Một server có thể trả lỗi `unavailableCriticalExtension` hoặc không phản hồi đúng control theo policy/cấu hình. **Không âm thầm fallback** sang một search thường rồi đánh dấu thành công. Khi dữ liệu cần đầy đủ, phải xác minh hỗ trợ RFC 2696 và kiểm tra response trên server thực tế.

### 8.4. Bảo mật cookie

Không log raw cookie, không cố parse nội dung server-private, không phát cookie nguyên bản cho client HTTP phổ thông. Nếu xây API cho người dùng duyệt trang, cần thiết kế **session/authorization riêng** và một cơ chế pagination phù hợp, không dùng thẳng LDAP cookie làm bookmark vượt phiên.

## 9. Thay đổi dữ liệu trong lúc quét: không có snapshot tự động

RFC 2696 giúp chia truy vấn thành các trang; nó **không bảo đảm** các trang cùng phản ánh một snapshot LDAP tại một thời điểm duy nhất.

~~~text
T0: Quét bắt đầu ở OU People.
T1: Nhận trang đầu.
T2: Admin tạo, xóa hoặc move một entry.
T3: Nhận các trang kế tiếp.
T4: Quét hoàn tất.
~~~

Tùy server, thứ tự trả entry, replication và kiểu thay đổi, job có thể thấy entry mới, không thấy entry đã xóa, hoặc có kết quả bị trùng/thiếu so với một thời điểm tham chiếu. Không khẳng định kết quả chính xác tại T0 hay T4 chỉ vì `hasMore()` đã chuyển false.

### 9.1. Đồng bộ sang database cần thêm những gì?

Một luồng reconciliation nên:

1. Dùng định danh entry ổn định của provider, ví dụ `entryUUID` với server hỗ trợ RFC 4530 hoặc `objectGUID` với AD; không dùng DN/username/email làm khóa bất biến.
2. Lưu liên kết bằng cặp `(provider_key, external_id)` và unique constraint.
3. Xử lý mỗi entry theo cách **idempotent** để có thể replay khi scan thất bại.
4. Đánh dấu `last_seen_run_id` sau khi xử lý thành công.
5. **Chỉ đánh dấu entry không còn** khi toàn bộ scan đúng phạm vi đã hoàn thành và qua đối soát phù hợp; tuyệt đối không hard-delete hàng loạt vì thiếu entry trong một lần quét lỗi.
6. Khi cần theo dõi biến động liên tục, xem xét changelog/change feed/DirSync/syncrepl tùy server; Simple Paged Results **không phải change tracking**.

Ví dụ schema tối giản cho liên kết:

~~~sql
CREATE TABLE directory_identity_link (
    provider_key      VARCHAR(100) NOT NULL,
    external_id       VARCHAR(200) NOT NULL,
    app_user_id       UUID NOT NULL,
    last_seen_run_id  UUID,
    last_seen_at      TIMESTAMPTZ,
    PRIMARY KEY (provider_key, external_id)
);
~~~

Bảng minh họa ràng buộc chống trùng, chưa phải migration đầy đủ: production cần foreign key tới user, retention, audit, transaction database và quy tắc linking/provisioning. LDAP và database không có transaction xuyên hệ thống mặc định.

## 10. Giới hạn tài nguyên và vận hành

| Giới hạn | Mục đích | Giá trị ví dụ |
| --- | --- | --- |
| Page size | Kiểm soát số entry trong một response. | 250. |
| Max pages | Ngăn loop vô hạn/quét ngoài ý muốn. | 100 (lab). |
| Search base | Chỉ đọc OU nghiệp vụ được phép. | `ou=practice`. |
| Search scope | Giới hạn độ sâu. | `SUBTREE_SCOPE` khi cần OU con. |
| Returning attributes | Không tải dữ liệu nhạy cảm/không cần thiết. | `uid`, `cn`, `mail`. |
| Time limit từng search | Kiểm soát độ trễ của một page. | 5.000 ms. |
| Connect/read timeout | Kiểm soát kết nối JNDI. | 3.000/7.000 ms. |
| Deadline toàn job | Không giữ context vô hạn. | Do scheduler/application áp đặt. |
| Concurrency | Tránh nhiều scan cạnh tranh tài nguyên. | Một job đồng thời cho lab. |
| Metrics | Phát hiện lỗi/quét thiếu. | Số trang, số entry, lỗi, duration, lần quét đầy đủ. |

Phân trang **không vượt qua mọi giới hạn** của server. LDAP server có thể giới hạn kích thước trang, thời gian truy vấn, số cookie/session hoặc quyền đọc; cần phối hợp với người quản trị directory và đo tải thực tế.

**Không mở endpoint HTTP trả toàn bộ directory cho mọi caller.** Nếu cần chức năng duyệt danh bạ, bổ sung Spring Security, filter theo nghiệp vụ, phân quyền từng OU, DTO giới hạn và thiết kế trang UI riêng; đừng trộn raw LDAP cookie vào API công khai.

## 11. Xử lý lỗi đúng tầng

| Triệu chứng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| Search thường chỉ trả khoảng 1.000 entry. | Server size limit, không gửi paging control. | Xác minh RFC 2696, thử `ldapsearch -E pr=...`. |
| Trang đầu được, trang sau lỗi cookie. | Context đổi, connection đóng, backend thay hoặc cookie hết hiệu lực. | Dùng `SingleContextSource`, giữ query/connection. |
| Control không được hỗ trợ. | Server/ACL/policy không có Simple Paged Results. | Báo lỗi capability, không dùng dữ liệu partial. |
| Job trả thiếu entry. | Base/scope/filter, ACL, lỗi giữa trang, dữ liệu thay đổi. | Đối chiếu CLI với cùng account, ghi metrics trang. |
| Memory tăng theo tổng số user. | Code đang gom mọi trang vào `List`/`Set`. | Xử lý theo batch, không giữ dữ liệu cả scan. |
| LDAP code 49/50. | Credential bind sai hoặc ACL thiếu. | Xác minh tài khoản dịch vụ, nhánh và attribute. |
| `SSLHandshakeException`. | CA/hostname/truststore chưa đúng. | Cấu hình TLS, không tắt xác minh chứng chỉ. |
| `PartialResultException`. | Referral/partial search do topology server. | Chính sách referrals rõ, không bỏ qua lỗi để coi scan thành công. |
| Paged search bị timeout ở trang n. | Server chậm/mạng không ổn định. | Đánh dấu FAILED, retry an toàn từ đầu/changelog. |
| Đọc lại tạo bản ghi trùng. | Consumer không idempotent, thiếu khóa stable ID. | Unique constraint + upsert theo nguồn và ID. |

## 12. Ma trận kiểm thử chấp nhận

| Tình huống | Bước thử | Kỳ vọng |
| --- | --- | --- |
| 2.505 entry, page=250. | Chạy scan trên fixture cố định. | Tổng 2.505, hoàn tất theo cookie; thường 11 trang. |
| Chỉ 50 entry, page=250. | Đổi OU test nhỏ. | Một trang, đủ 50 entry. |
| Đúng 500 entry, page=250. | Thử khi tổng là bội số page size. | Kết thúc theo control, không suy theo `page.size()`. |
| Dataset rỗng. | Filter không khớp entry nào. | 0 kết quả và hoàn tất hợp lệ khi control xử lý đúng. |
| Lỗi ở trang 4. | Ngắt mạng trên directory test. | Scan FAILED, không tuyên bố dữ liệu đầy đủ. |
| Không hỗ trợ RFC 2696. | Thử trên server test khác. | Báo lỗi rõ, không fallback lặng lẽ. |
| Server A → B giữa chuỗi. | Ép chuyển backend trên môi trường test. | Không giả định cookie tiếp tục được ở B. |
| Thêm/rename entry giữa scan. | Sửa entry test có kiểm soát. | Không kỳ vọng snapshot nhất quán, có kế hoạch reconcile. |
| ACL không đủ. | Dùng bind account chỉ đọc ngoài vùng. | Không trả dữ liệu vượt quyền; phân biệt lỗi với “không có entry”. |
| Consumer thất bại ở một trang. | Giả lập lỗi ghi DB. | Dừng scan, retry idempotent, không đánh dấu full scan thành công. |
| Nhiều scan song song. | Chạy nhiều job thử nghiệm. | Có giới hạn concurrency và cảnh báo tải. |

**Unit test mapper** có thể xác nhận xử lý attribute thiếu hoặc sai định dạng; nhưng **integration test** mới chứng minh được Java thực sự gửi paged control, nhận cookie, giữ cùng connection và xử lý lỗi server. Mock `LdapTemplate` trả lần lượt ba trang không thay thế được phép thử trên directory có RFC 2696.

## 13. Bài tập mở rộng

1. Thử các page size `100`, `250` và `500`, đo tổng số request và thời gian. Vì sao page lớn nhất chưa chắc nhanh nhất?
2. Đổi `SUBTREE_SCOPE` thành `ONELEVEL_SCOPE`. Nếu có `ou=archive` bên dưới `ou=practice`, entry trong nhánh con có được trả về không?
3. Xóa thuộc tính `mail` khỏi một entry test. Mapper và DTO nên xử lý như thế nào?
4. Ngắt kết nối sau ba trang. Viết trạng thái `FAILED` và giải thích vì sao không nên tiếp tục raw cookie khi tạo context mới.
5. Thêm entry trong lúc scan, giải thích tại sao kết quả không là một snapshot ở T0.
6. Thêm `entryUUID` (hoặc `objectGUID` với AD) vào mapper; thiết kế dedup dựa trên nguồn + stable ID thay vì `uid`.
7. Nếu ứng dụng đồng bộ database, hãy thiết kế unique constraint và `last_seen_run_id`; chỉ đánh dấu vắng mặt khi **full scan** đã hoàn tất.
8. Viết test xác nhận khi server trả ít hơn page size nhưng còn cookie, chương trình vẫn tiếp tục.
9. Nếu directory dùng hai LDAP URL, những điều kiện nào phải đúng để scan không bị lỗi khi backend A ngừng phục vụ?
10. Đề xuất số liệu vận hành: `pages_read`, `entries_processed`, `duration`, `failed_scans`, `last_successful_scan` mà không log PII/cookie.

**Gợi ý đáp án:** Page nhỏ tăng round-trip nhưng giảm response size; page lớn giảm round-trip nhưng tăng RAM/network. `ONELEVEL` chỉ lấy entry con trực tiếp, `SUBTREE` bao gồm OU con. Attribute `mail` có thể vắng, DTO phải cho phép theo hợp đồng. Cookie chỉ là token của một chuỗi query/connection, không phải checkpoint dài hạn. Với đồng bộ, xử lý idempotent theo stable ID và coi partial scan là thất bại, không xóa dữ liệu nội bộ dựa trên kết quả thiếu.

## 14. Ghi nhớ

**Phân trang LDAP đúng nghĩa cần RFC 2696, paging control và cookie, không phải chỉ `countLimit` hoặc `List.subList()`.** Khi dùng Spring LDAP 4.1+, `PagedResultsControlExchangeDirContextProcessor` xử lý request/response control; `SingleContextSource` giữ cùng connection xuyên suốt mọi trang. Mỗi lần chỉ giữ một trang dữ liệu, giữ base/filter/scope cố định và kết thúc theo `hasMore()`.

Phân trang hỗ trợ đọc directory lớn với mức tiêu thụ bộ nhớ kiểm soát được, nhưng **không bảo đảm snapshot nhất quán** hoặc khả năng resume sau crash. Muốn đồng bộ an toàn cần định danh ổn định, upsert idempotent, đối soát full scan, ACL tối thiểu, TLS, giới hạn tài nguyên và integration test với directory thật.

### Tài liệu tham khảo

- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696)
- [Spring LDAP Reference — Processing the DirContext / Paged Search Results](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html)
- [Spring LDAP API — PagedResultsControlExchangeDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html)
- [Spring LDAP API — SingleContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/SingleContextSource.html)
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP API — PagedResultsDirContextProcessor (API cũ)](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsDirContextProcessor.html)
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/)
- [RFC 4511 — LDAPv3 Search Operation](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515)
