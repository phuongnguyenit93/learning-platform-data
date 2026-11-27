# DataAccessException trong Spring LDAP

Trong ứng dụng Spring, `DataAccessException` thường xuất hiện khi truy cập cơ sở dữ liệu bằng JDBC, JPA hoặc một repository. Vì LDAP cũng là nguồn dữ liệu, người mới học **Spring LDAP** dễ cho rằng mọi lỗi từ `LdapTemplate`, `LdapClient` hay ODM đều thuộc `org.springframework.dao.DataAccessException`. Giả định này dẫn đến `catch` sai kiểu, bỏ sót lỗi vận hành hoặc cấu hình cơ chế retry không đúng.

**Điểm cốt lõi:** Spring LDAP có hệ exception riêng, với lớp gốc `org.springframework.ldap.NamingException`. Lớp này và `org.springframework.dao.DataAccessException` **không kế thừa nhau**. Khi thiết kế tầng truy cập thư mục, ta có thể giữ nguyên exception LDAP hoặc **chủ động** chuyển nó thành lỗi miền ứng dụng / lỗi DAO; không nên cho rằng việc chuyển đổi đó tự xảy ra.

Bài học thuộc chương **Exception**, gắn với quá trình làm việc với DN, schema, filter, tìm kiếm và thao tác entry, cấu hình `ContextSource`, xác thực, TLS, pooling và chẩn đoán truy cập thư mục an toàn.

## 1. `DataAccessException` thực sự là gì?

`org.springframework.dao.DataAccessException` là lớp gốc **abstract** của hệ exception truy cập dữ liệu dùng chung trong Spring Framework. Nó kế thừa `org.springframework.core.NestedRuntimeException`, vì vậy là **unchecked exception** và có thể giữ nguyên nhân gốc qua `getCause()`, `getRootCause()` hoặc `getMostSpecificCause()`.

Một số subclass thường dùng ở tầng persistence:

| Nhóm / lớp | Ý nghĩa thường gặp |
| --- | --- |
| `TransientDataAccessException` | Nhóm lỗi dữ liệu tạm thời, có thể cân nhắc thử lại tùy trường hợp |
| `NonTransientDataAccessException` | Nhóm lỗi thường không khắc phục bằng cách lặp lại nguyên thao tác |
| `DataAccessResourceFailureException` | Tài nguyên dữ liệu không khả dụng, chẳng hạn không kết nối được |
| `DuplicateKeyException` | Vi phạm ràng buộc duy nhất / trùng định danh ở nguồn dữ liệu |
| `DataIntegrityViolationException` | Vi phạm tính toàn vẹn hoặc ràng buộc dữ liệu |
| `DataRetrievalFailureException` | Không thể truy xuất dữ liệu như mong đợi |

Đây là một **hệ phân loại theo ý nghĩa truy cập dữ liệu**, phổ biến trong Spring JDBC/JPA và một số tích hợp Spring Data. Nó không khẳng định nguyên nhân gốc phải là SQL, nhưng **Spring LDAP không tự động biến mọi JNDI exception thành hệ DAO này**.

### 1.1. Ba hệ exception dễ bị nhầm

```text
java.lang.Exception
└── javax.naming.NamingException                  (checked, JNDI)

java.lang.RuntimeException
└── org.springframework.core.NestedRuntimeException
    ├── org.springframework.dao.DataAccessException       (Spring DAO)
    │   ├── DataAccessResourceFailureException
    │   ├── DuplicateKeyException
    │   └── ...
    └── org.springframework.ldap.NamingException         (Spring LDAP)
        ├── CommunicationException
        ├── AuthenticationException
        ├── NameNotFoundException
        ├── SchemaViolationException
        └── ...
```

Hai lớp `DataAccessException` và `org.springframework.ldap.NamingException` có cùng tổ tiên là `NestedRuntimeException`, **không có quan hệ cha–con với nhau**. Điều này quyết định trực tiếp cách viết `try/catch`:

```java
try {
    ldapTemplate.lookup("uid=mai,ou=people");
} catch (org.springframework.dao.DataAccessException ex) {
    // Không bắt được các exception LDAP tiêu chuẩn
    // như org.springframework.ldap.NameNotFoundException.
}
```

Thay vì đoạn trên, nếu đang làm việc trực tiếp với Spring LDAP, hãy bắt **subclass cụ thể của `org.springframework.ldap.NamingException`** hoặc bắt lớp gốc này khi thật sự cần xử lý chung.

### 1.2. Vì sao đôi lúc tài liệu có chữ `DataAccessException`?

Một số ví dụ chữ ký phương thức trong trang hướng dẫn Spring LDAP về `DirContextProcessor` có `throws DataAccessException`. Đây **không phải bằng chứng** rằng `org.springframework.ldap.NamingException` kế thừa `org.springframework.dao.DataAccessException`. Javadoc API hiện hành của `LdapTemplate` và `NamingException` xác định hệ exception riêng; bản thân các phương thức Java cũng không cần khai báo `throws` cho unchecked exception.

Khi gặp khác biệt giữa ví dụ minh họa và API, hãy xem **package import, cây kế thừa và Javadoc đúng phiên bản thư viện thực tế** trước khi chọn loại exception để bắt.

## 2. Spring LDAP chuyển đổi lỗi như thế nào?

Một yêu cầu LDAP thường đi qua các tầng:

```text
Ứng dụng (service/controller)
         │
         ▼
LdapTemplate / LdapClient / ODM
         │
         ▼
ContextSource → JNDI DirContext
         │
         ▼
LDAP server (bind/search/add/modify/delete)
         │
         ▼
javax.naming.NamingException (nếu lỗi)
         │
         ▼
Spring LDAP chuyển đổi exception
         │
         ▼
org.springframework.ldap.NamingException (runtime, subclass phù hợp)
```

Khi làm việc với `LdapTemplate`, các lỗi JNDI như `javax.naming.CommunicationException` có thể được chuyển thành `org.springframework.ldap.CommunicationException`. Spring LDAP cung cấp `LdapUtils.convertLdapException(javax.naming.NamingException)` để thực hiện chuyển đổi theo loại lỗi. Khi không có ánh xạ chuyên biệt, có thể nhận `UncategorizedLdapException`.

Ví dụ điển hình:

| Khi thao tác LDAP | JNDI exception / nguyên nhân thường gặp | Spring LDAP exception thường gặp |
| --- | --- | --- |
| Mở kết nối, thực hiện tìm kiếm, TLS bị lỗi | `javax.naming.CommunicationException` | `org.springframework.ldap.CommunicationException` |
| Bind bằng thông tin không hợp lệ | `javax.naming.AuthenticationException` | `org.springframework.ldap.AuthenticationException` |
| `lookup` DN không tồn tại | `javax.naming.NameNotFoundException` | `org.springframework.ldap.NameNotFoundException` |
| Tạo entry có DN đã tồn tại | `javax.naming.NameAlreadyBoundException` | `org.springframework.ldap.NameAlreadyBoundException` |
| Tạo/sửa entry vi phạm schema | `javax.naming.directory.SchemaViolationException` | `org.springframework.ldap.SchemaViolationException` |
| Tài khoản bind thiếu quyền thao tác | `javax.naming.NoPermissionException` | `org.springframework.ldap.NoPermissionException` |
| LDAP server không sẵn sàng | `javax.naming.ServiceUnavailableException` | `org.springframework.ldap.ServiceUnavailableException` |

**Quan trọng:** không phải mọi lỗi từ LDAP đều là exception. `search` không có entry khớp filter thường trả **danh sách rỗng**. `lookup` DN không tồn tại thường ném `NameNotFoundException`. Ngoài ra, `LdapTemplate` có một số tùy chọn bỏ qua lỗi tìm kiếm đặc thù như `ignoreNameNotFoundException` và `ignorePartialResultException`. Hành vi chính xác phụ thuộc đường gọi và cấu hình; không nên coi danh sách rỗng là bằng chứng chắc chắn rằng entry không tồn tại hoặc truy vấn đã trả đủ kết quả.

Các callback ánh xạ thuộc tính có thể phát sinh `javax.naming.NamingException` khi đọc dữ liệu; `LdapTemplate` xử lý và chuyển đổi chúng ở các đường gọi phù hợp. Còn ngoại lệ nghiệp vụ do callback chủ động ném không nhất thiết được chuyển thành exception LDAP.

## 3. Xử lý trực tiếp ở tầng Spring LDAP: ưu tiên exception đúng loại

Giả sử `ContextSource` đã được cấu hình base DN `dc=example,dc=org` và danh sách người dùng nằm trong `ou=people`. Đoạn mã sau đọc `cn` theo `uid`, dùng `LdapNameBuilder` để escape giá trị RDN chính xác:

```java
import java.util.Optional;
import javax.naming.Name;
import javax.naming.directory.Attribute;

import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.NoPermissionException;
import org.springframework.ldap.ServiceUnavailableException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class DirectoryPersonService {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Optional<String> findCommonName(String uid) {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        try {
            String commonName = ldapTemplate.lookup(
                    dn,
                    (AttributesMapper<String>) attrs -> {
                        Attribute cn = attrs.get("cn");
                        return cn == null ? null : cn.get().toString();
                    }
            );
            return Optional.ofNullable(commonName);
        } catch (NameNotFoundException ex) {
            // Chỉ trường hợp lookup không có entry tại DN này.
            return Optional.empty();
        } catch (CommunicationException | ServiceUnavailableException ex) {
            // Phân biệt hệ thống thư mục không khả dụng với dữ liệu không tồn tại.
            throw new IllegalStateException("Dịch vụ LDAP không khả dụng", ex);
        } catch (NoPermissionException ex) {
            // Bind có thể thành công nhưng tài khoản không đủ quyền đọc entry.
            throw new IllegalStateException("Thiếu quyền đọc thông tin LDAP", ex);
        }
    }
}
```

Lưu ý:

1. `Optional.empty()` chỉ diễn đạt một quyết định nghiệp vụ: *DN được lookup không có entry*; nó không bao gồm lỗi kết nối, xác thực hay ACL.
2. `NoPermissionException` là vấn đề phân quyền, không nên retry mù quáng.
3. `IllegalStateException` chỉ là wrapper để ví dụ gọn. Ứng dụng thực tế thường dùng exception miền riêng hoặc để nguyên exception LDAP và xử lý tập trung.
4. `LdapTemplate` nhận DN **tương đối** so với base cấu hình trong `ContextSource`. Không tự ghép lại `dc=example,dc=org` nếu `ContextSource` đã định nghĩa base.
5. Nếu ứng dụng yêu cầu `cn` bắt buộc, thiếu `cn` nên trở thành lỗi dữ liệu rõ ràng thay vì `Optional.empty()`; ví dụ chỉ thể hiện trường hợp cho phép giá trị `cn` không có.

### 3.1. Bắt lớp cha ở đâu?

Bắt `org.springframework.ldap.NamingException` phù hợp tại **ranh giới hệ thống** để ghi log, đo lường và trả lỗi chung:

```java
try {
    return directoryPersonService.findCommonName(uid);
} catch (org.springframework.ldap.NamingException ex) {
    // Chuyển tại ranh giới API hoặc service.
    // Ghi loại thao tác, nhóm lỗi, correlation ID;
    // không ghi bind password, token hay attribute nhạy cảm.
    throw ex;
}
```

Tuy nhiên, nếu service đã chuyển lỗi thành `IllegalStateException` hoặc exception miền, khối `catch` này không bắt được chúng. Nên **đặt chính sách xử lý rõ ở một tầng**, tránh dịch đi dịch lại và mất thông tin về nguyên nhân.

## 4. Khi nào nên chuyển exception LDAP sang `DataAccessException`?

Một hệ thống có thể có cả nguồn dữ liệu quan hệ và LDAP; tầng nghiệp vụ muốn một hợp đồng **DAO thống nhất**. Khi đó có thể viết **adapter chuyển đổi có chủ đích** từ các loại lỗi LDAP sang loại lỗi DAO gần ý nghĩa nhất.

Quy tắc chuyển đổi minh họa:

| Spring LDAP exception | Nếu cần biểu diễn bằng Spring DAO | Lưu ý |
| --- | --- | --- |
| `CommunicationException`, `ServiceUnavailableException` | `DataAccessResourceFailureException` | Nguồn LDAP không sẵn sàng; retry có điều kiện |
| `NameAlreadyBoundException` khi tạo entry | `DuplicateKeyException` | DN của entry đã tồn tại; chỉ map khi đó thực sự là xung đột duy nhất |
| `SchemaViolationException` khi ghi | `DataIntegrityViolationException` | Cần sửa dữ liệu hoặc schema, không phải lỗi tạm thời |
| `NameNotFoundException` khi lookup | Thường chuyển thành `Optional.empty()` hoặc lỗi nghiệp vụ `NotFound` | Tình huống “không tìm thấy” cần quyết định theo API, không có ánh xạ máy móc |
| `NoPermissionException` | Có thể chuyển sang exception phân quyền của ứng dụng | Đừng đánh đồng với xác thực thất bại của người dùng cuối |
| `AuthenticationException` | Có thể là lỗi cấu hình tài khoản dịch vụ hoặc lỗi xác thực người dùng | Phân loại dựa trên **luồng bind** và ngữ cảnh |
| `InvalidNameException` / lỗi filter | Lỗi yêu cầu/cấu hình, xử lý riêng | Không nên coi là lỗi kết nối có thể thử lại |

Không có bảng ánh xạ **mặc định duy nhất** áp dụng được cho mọi nghiệp vụ LDAP. Ví dụ `NameNotFoundException` khi tìm một người theo DN là “không có dữ liệu”; cùng exception khi search base `ou=people` không tồn tại lại là lỗi cấu hình. Việc đổi cả hai thành một `DataRetrievalFailureException` có thể làm mất ý nghĩa quan trọng.

### 4.1. Adapter mẫu: chỉ dịch lỗi hệ thống ở một ranh giới rõ ràng

Giả sử repository công khai giao diện sử dụng `DataAccessException` của Spring DAO. Adapter chỉ đổi những lỗi cần thống nhất cho tầng gọi; giữ lại `cause` để chẩn đoán:

```java
import java.util.Optional;
import javax.naming.Name;
import javax.naming.directory.Attribute;

import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.DataRetrievalFailureException;
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.ServiceUnavailableException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public final class LdapPersonDaoAdapter {
    private final LdapTemplate ldapTemplate;

    public LdapPersonDaoAdapter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Optional<String> loadCommonName(Name dn) {
        try {
            String commonName = ldapTemplate.lookup(
                    dn,
                    (AttributesMapper<String>) attributes -> {
                        Attribute cn = attributes.get("cn");
                        return cn == null ? null : cn.get().toString();
                    }
            );
            return Optional.ofNullable(commonName);
        } catch (NameNotFoundException ex) {
            return Optional.empty();
        } catch (CommunicationException | ServiceUnavailableException ex) {
            throw new DataAccessResourceFailureException(
                    "Không thể kết nối tới nguồn dữ liệu LDAP", ex);
        } catch (org.springframework.ldap.NamingException ex) {
            // Ví dụ tổng quát: chỉ dùng khi giao diện DAO cần lỗi chung.
            // Ứng dụng thực tế có thể tách rõ lỗi ACL, schema, DN...
            throw new DataRetrievalFailureException(
                    "Không thể đọc dữ liệu từ LDAP", ex);
        }
    }
}
```

Lúc này, tầng sử dụng **adapter** có thể bắt `org.springframework.dao.DataAccessException`:

```java
try {
    Optional<String> cn = personDaoAdapter.loadCommonName(userDn);
    // Xử lý dữ liệu nếu có.
} catch (org.springframework.dao.DataAccessException ex) {
    // Được bắt vì adapter đã chuyển exception LDAP sang hệ DAO.
    // Quyết định trả lỗi, đo lường hoặc thử lại tùy loại cụ thể.
    throw ex;
}
```

Đây là một **quyết định thiết kế kiến trúc**, không phải chuyển đổi tự động của `LdapTemplate`. Chỉ tạo adapter như vậy khi các caller thật sự cần hợp đồng DAO; nhiều ứng dụng sẽ đơn giản và chính xác hơn nếu giữ exception Spring LDAP, rồi map sang lỗi miền tại service.

### 4.2. `@Repository` có tự chuyển lỗi LDAP không?

Đừng giả định thêm `@Repository` lên một class gọi `LdapTemplate` sẽ làm `org.springframework.ldap.NamingException` trở thành `org.springframework.dao.DataAccessException`. Annotation giúp đánh dấu vai trò repository, nhưng cơ chế chuyển đổi ngoại lệ persistence của Spring chỉ hoạt động khi có translator phù hợp và được cấu hình. Nếu dùng Spring Data LDAP repository hoặc một thư viện tích hợp khác, phải kiểm tra **API và exception contract của lớp cụ thể**. Các quy tắc xử lý `LdapTemplate` trong bài này vẫn dựa trên hệ exception `org.springframework.ldap.*`.

## 5. Retry và phân loại lỗi: `DataAccessException` không đủ để quyết định

Trong DAO của Spring Framework, `TransientDataAccessException` mang ý nghĩa lỗi dữ liệu có khả năng tạm thời. Với Spring LDAP, `CommunicationException` hoặc `ServiceUnavailableException` **không phải** là subclass của `TransientDataAccessException`. Vì vậy cơ chế retry cấu hình theo kiểu exception DAO có thể **không kích hoạt** khi lỗi LDAP đi qua trực tiếp.

Để xử lý đúng:

- Nếu **giữ exception LDAP**: chính sách retry phải nhắm vào các exception LDAP thích hợp và xem `cause`, timeout, thao tác hiện tại.
- Nếu **chuyển sang exception DAO**: adapter quyết định loại lỗi, giữ `cause` và lập chính sách retry dựa trên loại sau chuyển đổi.
- Chỉ thử lại sự cố có khả năng tạm thời với số lần hữu hạn, backoff, jitter và timeout tổng. TLS truststore sai, DN không hợp lệ, thiếu quyền và schema sai thường **không thể** sửa bằng retry.
- Với `bind`, `modifyAttributes`, `unbind`, mất phản hồi sau khi gửi request có thể xảy ra khi server **đã áp dụng thao tác**. Trước khi thử lại cần đọc lại trạng thái hoặc thiết kế thao tác idempotent, bảo vệ khỏi cập nhật trùng.
- Với `search`, cần kiểm tra kết quả có bị cắt bởi size limit, time limit hay referral. Bỏ qua exception và trả kết quả một phần có thể làm người dùng tưởng đã truy vấn đủ.

Ví dụ phân biệt kết quả và lỗi:

| Tình huống | Kết quả nên được hiểu như thế nào? |
| --- | --- |
| `search` base hợp lệ, không có entry khớp | Danh sách rỗng; không nhất thiết là exception |
| `lookup` DN không tồn tại | Tình huống not found tùy hợp đồng; thường `NameNotFoundException` |
| LDAP server mất kết nối | Lỗi hạ tầng; không trả `Optional.empty()` hoặc `404` một cách máy móc |
| Bind bằng tài khoản dịch vụ sai mật khẩu | Lỗi cấu hình/secret hạ tầng; không quy thành người dùng cuối nhập sai mật khẩu |
| Bind kiểm tra mật khẩu người dùng thất bại | Lỗi xác thực người dùng; phản hồi an toàn, không lộ tình trạng tồn tại tài khoản |
| Thêm entry có DN đã tồn tại | Xung đột; có thể trả `409` nếu đó là ý nghĩa nghiệp vụ |
| Sửa entry bị `SchemaViolationException` | Sửa payload/objectClass/schema; không retry cùng payload |

## 6. Đưa lỗi ra API, log và hệ thống giám sát

Một lớp API không nên đưa toàn bộ stack trace LDAP hoặc thông báo từ server cho người dùng. DN, filter, principal, thuộc tính và mã phụ của Active Directory có thể chứa thông tin định danh hoặc nội bộ.

Gợi ý diễn giải ở biên HTTP:

| Kết quả nguồn LDAP / ứng dụng | Ví dụ phản hồi nếu phù hợp nghiệp vụ |
| --- | --- |
| Entry không tồn tại khi truy cập tài nguyên bằng ID | `404 Not Found` |
| Thêm entry trùng DN | `409 Conflict` |
| Input DN hoặc filter không hợp lệ do client | `400 Bad Request` |
| Người dùng cuối xác thực thất bại | `401 Unauthorized` theo cơ chế xác thực đang dùng |
| Caller thiếu quyền | `403 Forbidden` nếu danh tính caller thực sự không có quyền |
| Tài khoản dịch vụ thiếu quyền đọc/sửa LDAP | `500` hoặc `502` tùy kiến trúc; đây là lỗi hạ tầng của ứng dụng |
| Thư mục LDAP không khả dụng | `503 Service Unavailable` nếu lỗi gây gián đoạn tạm thời |

Đây là **gợi ý ánh xạ có điều kiện**, không phải quy tắc áp đặt cho mọi endpoint. Ví dụ `NoPermissionException` của tài khoản bind kỹ thuật không chứng minh người gọi HTTP bị cấm, còn `AuthenticationException` của service account không nên được biến thành `401` cho người dùng cuối.

Khi ghi log, nên lưu **tên thao tác**, endpoint logic hoặc mã hệ thống, loại exception, thời lượng, số lần retry, correlation ID và loại nguyên nhân gốc. Che hoặc rút gọn DN và filter khi có dữ liệu nhạy cảm. Tuyệt đối không log bind password, token, credential hay giá trị thuộc tính nhạy cảm. Có thể đo các chỉ số như tỷ lệ `CommunicationException`, độ trễ bind/search, lỗi schema và tỷ lệ kết quả không đầy đủ.

## 7. Kiểm thử chiến lược exception

Ngay cả khi chỉ học `LdapTemplate`, nên định nghĩa các ca kiểm thử ở ranh giới DAO/service. Mock những lời gọi LDAP cần thiết để kiểm tra **hành vi**, sau đó dùng LDAP test server (hoặc môi trường tích hợp kiểm soát được) để xác nhận sự khác biệt giữa client, TLS, ACL và schema.

| Ca thử | Kỳ vọng |
| --- | --- |
| `lookup` thành công | Nhận dữ liệu đã ánh xạ |
| `lookup` không có DN | Trả `Optional.empty()` / not found theo hợp đồng |
| `CommunicationException` | Không bị coi là not found; nếu qua adapter thì giữ `cause` dưới `DataAccessResourceFailureException` |
| `NoPermissionException` | Không âm thầm trả danh sách rỗng; phân biệt ACL hệ thống và quyền caller |
| `SchemaViolationException` khi ghi | Không retry nguyên payload; cung cấp chẩn đoán nội bộ đúng |
| Lỗi mạng sau khi gửi cập nhật | Không thực hiện lệnh ghi lặp lại mù quáng |
| `search` có size limit/referral | Kiểm tra đầy đủ dữ liệu, không mặc nhiên chấp nhận kết quả thiếu |
| Lỗi TLS do truststore | Có tín hiệu cấu hình lỗi, không retry liên tục |

Phải kiểm tra **đúng loại exception** ở nơi thật sự chịu trách nhiệm: `org.springframework.ldap.*` quanh `LdapTemplate` hoặc `org.springframework.dao.*` **sau adapter chuyển đổi**. Đây cũng là cách tránh test giả định sai rằng hai hệ kế thừa nhau.

## 8. Những lỗi thiết kế thường gặp

1. **`catch (DataAccessException)` trực tiếp quanh `LdapTemplate`** rồi tưởng đã xử lý hết lỗi LDAP. Các Spring LDAP runtime exception thông thường thuộc nhánh `org.springframework.ldap.NamingException`.
2. **`catch (Exception)` và trả danh sách rỗng.** Lỗi kết nối hay phân quyền bị che thành “không có người dùng”, ảnh hưởng cả tính đúng đắn và an toàn.
3. **Bắt nhầm `javax.naming.NamingException`** ở lớp dùng `LdapTemplate` và tin rằng nó luôn được ném ra như checked exception. Spring LDAP thường đã chuyển sang runtime exception.
4. **Map mọi lỗi LDAP thành `DataAccessResourceFailureException`.** Xung đột DN, lỗi schema, lỗi xác thực và không tồn tại là những trường hợp khác nhau.
5. **Giả định Spring Retry bắt `TransientDataAccessException` sẽ bao phủ LDAP.** Retry phụ thuộc loại exception thực tế hoặc loại đã được adapter chuyển đổi.
6. **Retry thao tác ghi mà không kiểm tra trạng thái.** Điều này có thể dẫn đến tạo trùng hoặc sửa dữ liệu nhiều lần khi phản hồi bị mất.
7. **Dùng `@Repository` làm bằng chứng chuyển đổi.** Phải xem implementation và bộ translator được cấu hình.
8. **Trả diagnostic message của server ra HTTP.** Dễ rò rỉ thông tin về DN, người dùng, cơ chế bảo mật và cấu trúc thư mục.

## 9. Tự kiểm tra

**Câu 1.** Nếu `ldapTemplate.lookup(...)` ném `org.springframework.ldap.NameNotFoundException`, khối `catch (org.springframework.dao.DataAccessException ex)` có bắt được không?

**Đáp án:** Không. Hai lớp thuộc hai nhánh kế thừa khác nhau.

**Câu 2.** Khi nào `catch (DataAccessException)` có thể xử lý lỗi xuất phát từ LDAP?

**Đáp án:** Khi một adapter/lớp tích hợp **đã chủ động dịch** exception LDAP sang hệ DAO hoặc có API riêng cam kết ném loại này. Phải kiểm tra thực tế API và translator.

**Câu 3.** Có nên đổi mọi `NameNotFoundException` thành `DataRetrievalFailureException`?

**Đáp án:** Không. `lookup` một DN không tồn tại có thể là “không tìm thấy”; search base thiếu lại có thể báo lỗi cấu hình.

**Câu 4.** Có thể retry cùng payload ngay khi `CommunicationException` xảy ra sau lệnh `modifyAttributes`?

**Đáp án:** Không mặc định. Server có thể đã áp dụng thay đổi; cần xác minh trạng thái hoặc cơ chế đảm bảo idempotency.

**Câu 5.** `DataAccessResourceFailureException` hợp lý nhất trong ví dụ adapter cho tình huống nào?

**Đáp án:** Tình huống không thể truy cập nguồn LDAP do vấn đề kết nối hoặc server không khả dụng, có giữ cause gốc.

## 10. Tài liệu tham khảo

- [Spring Framework API — `DataAccessException`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataAccessException.html): vai trò, cây kế thừa và đặc tính runtime exception.
- [Spring LDAP API — `org.springframework.ldap.NamingException`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/NamingException.html): lớp gốc của hệ exception LDAP; quan hệ với `NestedRuntimeException`.
- [Spring LDAP API — `LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): hành vi lookup/search và chuyển `javax.naming.NamingException`.
- [Spring LDAP API — package `org.springframework.ldap`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/package-summary.html): danh sách exception cụ thể.
- [Spring LDAP Reference — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): ví dụ `DirContextProcessor`, lưu ý đối chiếu với API.
- [Spring LDAP API — `LdapUtils`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapUtils.html): tiện ích `convertLdapException`.

**Kết luận:** `DataAccessException` hữu ích khi ứng dụng muốn hợp đồng DAO chung, nhưng **Spring LDAP trực tiếp sử dụng hệ `org.springframework.ldap.NamingException`**. Chỉ chuyển đổi exception tại ranh giới đã thiết kế, giữ nguyên nhân gốc và bảo toàn ý nghĩa khác nhau của “không tìm thấy”, lỗi xác thực, thiếu quyền, lỗi dữ liệu và sự cố hạ tầng.
