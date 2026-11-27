# CommunicationException, timeout và lỗi mạng

Một ứng dụng **Spring LDAP** có thể truy vấn đúng DN, đúng filter và dùng tài khoản bind hợp lệ nhưng vẫn thất bại vì DNS, kết nối TCP, TLS, quá thời gian chờ hoặc LDAP server không sẵn sàng. Những lỗi này cần được phân biệt với “không tìm thấy entry” và “sai mật khẩu”: nếu trả danh sách rỗng khi thực tế thư mục đang mất kết nối, ứng dụng có thể đưa ra quyết định nghiệp vụ hoặc phân quyền sai.

Bài thuộc chương **Exception** của module **SPRING_LDAP**, tập trung vào `CommunicationException`, các loại timeout và sự cố mạng khi làm việc với `ContextSource`, `LdapTemplate`, `LdapClient` hoặc Object–Directory Mapping (ODM). Người học sẽ biết cách nhận diện nguồn lỗi, cấu hình giới hạn chờ, thiết kế retry và failover, xử lý trạng thái không xác định sau thao tác ghi, bảo vệ kết nối TLS và kiểm thử các tình huống mất khả dụng.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt `javax.naming.CommunicationException` của JNDI và `org.springframework.ldap.CommunicationException` của Spring LDAP.
2. Phân biệt **connect timeout**, **read/response timeout**, **search time limit** và giới hạn thời gian tổng của một request.
3. Nhận diện những nhóm lỗi thường gặp: DNS, TCP, TLS/StartTLS, server busy/unavailable, kết nối cũ trong pool, referral và thao tác tìm kiếm nặng.
4. Cấu hình timeout cho JNDI LDAP provider thông qua `LdapContextSource`/`ContextSource`, hiểu giới hạn của cấu hình này.
5. Quyết định khi nào retry có giới hạn, khi nào phải sửa cấu hình, và vì sao mất kết nối sau `bind`/`modifyAttributes`/`unbind` không chứng minh lệnh ghi chưa thành công.
6. Xây quy trình chẩn đoán, ghi log an toàn và kiểm thử lỗi mạng mà không làm lộ credential hoặc che giấu lỗi thư mục.

## 2. Vòng đời một yêu cầu LDAP: lỗi xảy ra ở đâu?

Một thao tác điển hình khi dùng `LdapTemplate`:

```text
Service / Repository
        │
        ▼
LdapTemplate / LdapClient / ODM
        │
        ▼
ContextSource: lấy hoặc tạo DirContext
        │
        ├── Phân giải DNS / chọn endpoint
        ├── Mở TCP connection
        ├── Đàm phán TLS/LDAPS hoặc StartTLS (nếu dùng)
        └── LDAP bind xác thực tài khoản kết nối
        │
        ▼
LDAP request: Search / Add / Modify / Delete / Compare ...
        │
        ▼
Chờ LDAP response
        │
        ▼
Ánh xạ dữ liệu, trả kết quả, đóng/trả context về pool phù hợp
```

Không thể suy ra chính xác nguyên nhân chỉ từ câu “LDAP timeout”. Cần xác định lỗi phát sinh **trước khi gửi request**, **trong khi server xử lý**, **khi đọc phản hồi** hay **sau khi server có thể đã thay đổi dữ liệu**.

| Giai đoạn | Ví dụ dấu hiệu | Câu hỏi điều tra |
| --- | --- | --- |
| DNS | Không phân giải được hostname | FQDN, DNS resolver, mạng và cấu hình endpoint có đúng không? |
| TCP connect | Connection refused, unreachable hoặc connect timeout | Host/port, firewall, route, load balancer, server đang lắng nghe? |
| TLS/StartTLS | `SSLHandshakeException`, certificate/truststore failure | Certificate chain, hostname verification, truststore và phiên bản TLS có phù hợp? |
| Bind xác thực | LDAP `49` hoặc lỗi cơ chế xác thực | Principal, secret, account policy hay yêu cầu bảo mật kênh? |
| Gửi/đợi phản hồi | Read timeout, connection reset, server unavailable | Server đã nhận/xử lý request chưa? Query nặng hay mạng gián đoạn? |
| Xử lý tìm kiếm | LDAP time limit `3`, size limit `4` | Base DN, scope, index, filter, giới hạn server và tính đầy đủ của kết quả? |
| Dùng lại context | Kết nối idle bị server/network đóng | Pool có kiểm tra kết nối cũ, có kết nối theo từng danh tính không? |

Trong môi trường có load balancer hoặc nhiều LDAP replica, việc một endpoint lỗi không đồng nghĩa mọi server đều lỗi. Ngược lại, tìm thấy một endpoint phản hồi cũng không chứng minh dữ liệu đã được đồng bộ hoặc cùng quyền truy cập với endpoint khác.

## 3. `CommunicationException` của JNDI và Spring LDAP

### 3.1. Hai lớp cùng tên, hai package khác nhau

| Lớp | Đặc điểm | Thường gặp khi |
| --- | --- | --- |
| `javax.naming.CommunicationException` | **Checked exception**, kế thừa `javax.naming.NamingException` | Gọi JNDI `DirContext` trực tiếp |
| `org.springframework.ldap.CommunicationException` | **Runtime exception**, kế thừa `org.springframework.ldap.NamingException` | Dùng `LdapTemplate` và các API Spring LDAP chuyển lỗi JNDI |
| `org.springframework.ldap.ServiceUnavailableException` | Runtime exception LDAP | Server báo bận/không khả dụng hoặc provider chuyển từ JNDI |
| `org.springframework.ldap.TimeLimitExceededException` | Runtime exception LDAP | Search vượt thời hạn theo phản hồi hoặc cơ chế JNDI tương ứng |

Spring LDAP cung cấp `LdapUtils.convertLdapException(javax.naming.NamingException)` và chuyển checked exception của JNDI sang hệ runtime của mình trong các đường gọi phù hợp. Vì vậy, đoạn sau bắt **đúng package** quanh `LdapTemplate`:

```java
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.core.LdapTemplate;

public final class DirectoryProbe {
    private final LdapTemplate ldapTemplate;

    public DirectoryProbe(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void checkEntry(String relativeDn) {
        try {
            ldapTemplate.lookup(relativeDn);
        } catch (CommunicationException ex) {
            // Lỗi giao tiếp với LDAP, không phải bằng chứng DN không tồn tại.
            throw new IllegalStateException("Không liên lạc được với LDAP", ex);
        }
    }
}
```

Nếu code dùng JNDI trực tiếp thì exception phù hợp là `javax.naming.CommunicationException`. Bắt `org.springframework.dao.DataAccessException` quanh `LdapTemplate` **không mặc định bắt được** các exception thuộc `org.springframework.ldap.NamingException`; muốn có hợp đồng DAO chung phải chuyển đổi rõ ràng tại adapter.

### 3.2. `CommunicationException` không luôn có LDAP result code

LDAP result code là phản hồi ở tầng **giao thức LDAP**. Khi TCP connection không thể mở, DNS sai hoặc TLS handshake thất bại, có thể **chưa có LDAP response** nào để chứa result code.

Ví dụ:

```text
TCP connection refused
  └── JNDI NamingException / CommunicationException
      └── java.net.ConnectException

Mở TCP thành công, TLS certificate không tin cậy
  └── JNDI NamingException / CommunicationException
      └── javax.net.ssl.SSLHandshakeException

Đã gửi request, hết thời gian chờ phản hồi
  └── JNDI NamingException / CommunicationException
      └── java.net.SocketTimeoutException (có thể là cause)
```

Cấu trúc chính xác của chuỗi `cause` phụ thuộc JDK, LDAP provider và giai đoạn lỗi. Ví dụ ở trên mô tả **những nguyên nhân thường gặp**, không phải quy tắc ánh xạ tuyệt đối. Khi bắt lỗi cần đọc cả exception ở tầng Spring và `getCause()`/nguyên nhân gốc, thay vì dựa vào việc thông điệp chứa một chuỗi cố định.

### 3.3. Phân biệt các exception dễ bị gộp

| Exception Spring LDAP | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `CommunicationException` | Socket, DNS, TLS, connection reset, timeout chờ phản hồi | Kiểm tra root cause, endpoint và tình trạng request; retry có điều kiện |
| `ServiceUnavailableException` | Server trả `busy (51)` hoặc `unavailable (52)` trong trường hợp provider ánh xạ tương ứng | Kiểm tra khả dụng/tải server, chính sách failover và hạn mức |
| `TimeLimitExceededException` | Search quá thời gian cho phép; LDAP `timeLimitExceeded (3)` là trường hợp điển hình | Thu hẹp filter/scope, dùng index, xem time limit phía server/client |
| `SizeLimitExceededException` | Số entry vượt giới hạn, LDAP `sizeLimitExceeded (4)` | Phân trang hoặc thay đổi phạm vi truy vấn; không mặc định chấp nhận dữ liệu thiếu |
| `AuthenticationException` | LDAP bind không được chấp nhận, thường `49` | Kiểm tra identity/credential và chính sách tài khoản |
| `NoPermissionException` | LDAP `insufficientAccessRights (50)` | Kiểm tra ACL của bind identity |
| `NameNotFoundException` | DN đích hoặc search base không tồn tại, thường `32` | Kiểm tra DN/base; không quy thành lỗi mạng |

Trạng thái “server không khả dụng” và “mạng không kết nối được” có thể dẫn tới hành động vận hành tương tự, nhưng **không phải cùng exception**. Tránh chỉ bắt `CommunicationException` rồi mặc định đã bao phủ mọi lỗi liên quan đến availability.

## 4. Bốn loại giới hạn thời gian cần phân biệt

Trong thực tế, từ *timeout* thường chỉ một trong các giới hạn:

| Loại | Bắt đầu tính khi nào? | Dùng để bảo vệ | Dấu hiệu khi vượt |
| --- | --- | --- | --- |
| **Connect timeout** | Khi cố thiết lập kết nối TCP đến LDAP endpoint | Không chờ vô hạn khi host không phản hồi | Lỗi kết nối; có thể được bọc thành `CommunicationException` |
| **Read / response timeout** | Khi client chờ dữ liệu từ kết nối LDAP | Không đợi phản hồi mãi khi server hoặc mạng treo | Có thể là `SocketTimeoutException` được bọc trong lỗi JNDI/Spring LDAP |
| **LDAP search time limit** | Trong một thao tác Search theo giới hạn được client/server áp dụng | Tránh search chạy quá thời gian cho phép | Có thể nhận `TimeLimitExceededException` hoặc LDAP `3` |
| **Request deadline tổng** | Từ khi service bắt đầu xử lý tới khi phải trả kết quả | Giữ SLA của API và ngân sách retry | Do lớp ứng dụng/gateway/framework quản lý; không tự suy từ một property LDAP |

Các giới hạn này **không thay thế nhau**. Ví dụ connect timeout 3 giây không giới hạn một search đã mở kết nối; server-side search time limit cũng không đảm bảo TLS handshake hoặc bind hoàn thành trước một deadline của HTTP request.

### 4.1. Connect timeout

Với JNDI LDAP provider phổ biến của Oracle/OpenJDK, property:

```properties
com.sun.jndi.ldap.connect.timeout=3000
```

thường được hiểu là **3.000 mili giây** để chờ mở kết nối. Đây là **property đặc thù của provider JNDI**, không phải tên property chuẩn của giao thức LDAP. Nó không thay thế kiểm tra DNS, firewall, truststore hay timeout ở lớp gateway. Các giai đoạn DNS/TLS, lựa chọn endpoint và connection pooling có thể làm thời gian thực tế khác ngân sách lý thuyết.

### 4.2. Read timeout

Với cùng provider:

```properties
com.sun.jndi.ldap.read.timeout=5000
```

giới hạn khoảng chờ phản hồi của JNDI LDAP client theo cơ chế provider. Đây **không phải tổng deadline của toàn bộ nghiệp vụ**: một API có thể thực hiện nhiều LDAP request, lấy context từ pool hoặc chạy logic Java trước/sau search. Thêm retry có thể làm tổng thời gian vượt ngân sách HTTP dù mỗi lần chờ đều nằm trong giới hạn.

Timeout khi chờ phản hồi **không khẳng định server chưa xử lý request**. Điều này đặc biệt quan trọng khi Add, Modify hoặc Delete entry.

### 4.3. Search time limit

LDAP Search có giới hạn thời gian riêng. Server có thể trả `timeLimitExceeded (3)` khi truy vấn vượt mức được phép. Ngoài ra, JNDI `SearchControls` cung cấp `setTimeLimit(int)` với đơn vị **mili giây** cho thao tác search. Cách provider chuyển/áp giới hạn này phụ thuộc triển khai; nó **không thay thế** read timeout ở tầng socket.

```java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setTimeLimit(2000); // mili giây, dành cho search
controls.setCountLimit(100); // giới hạn số kết quả theo SearchControls
```

Nếu query quá rộng, chỉ tăng timeout sẽ che vấn đề hiệu năng. Nên kiểm tra search base, scope, filter, index của server, kích thước kết quả, số attribute trả về và paging (khi server hỗ trợ).

### 4.4. Deadline tổng và retry

Giả sử service có ngân sách 6 giây để đáp ứng HTTP nhưng cấu hình mỗi lần read timeout là 5 giây và retry tối đa 3 lần. Ngay cả khi từng lần kết nối hoạt động đúng theo timeout, tổng thời gian có thể vượt xa 6 giây nếu không giới hạn từ trên xuống.

Một chính sách thực tế cần có:

- Deadline tổng cho request và ngân sách dành cho LDAP.
- Connect/read timeout **nhỏ hơn hoặc tương thích với ngân sách còn lại**.
- Số lần retry hữu hạn, backoff/jitter và điều kiện rõ ràng.
- Giới hạn đồng thời khi LDAP server chậm để tránh dồn hàng chờ và khuếch đại sự cố.

## 5. Cấu hình timeout trong `LdapContextSource`

Ví dụ Java dùng `LdapContextSource`. Tham số `ldapUrl` có thể là một endpoint `ldaps://` đã được cấu hình TLS tin cậy. Credential được cung cấp từ hệ cấu hình/secret management, không nhúng trong mã:

```java
import java.util.HashMap;
import java.util.Map;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

public final class DirectoryConfiguration {
    private DirectoryConfiguration() {}

    public static LdapTemplate createTemplate(
            String ldapUrl,
            String baseDn,
            String serviceDn,
            String servicePassword) throws Exception {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(ldapUrl);
        source.setBase(baseDn);
        source.setUserDn(serviceDn);
        source.setPassword(servicePassword);

        Map<String, Object> env = new HashMap<>();
        env.put("com.sun.jndi.ldap.connect.timeout", "3000");
        env.put("com.sun.jndi.ldap.read.timeout", "5000");
        source.setBaseEnvironmentProperties(env);

        // Nếu do Spring IoC quản lý, framework sẽ gọi lifecycle hook.
        // Khi tự khởi tạo thủ công, cần khởi tạo ContextSource:
        source.afterPropertiesSet();

        return new LdapTemplate(source);
    }
}
```

**Giải thích:**

1. `LdapTemplate` sử dụng `ContextSource` nên các cấu hình provider ở trên áp dụng cho các context được tạo qua nguồn này khi provider hỗ trợ.
2. Giá trị `"3000"` và `"5000"` là **chuỗi mili giây** theo yêu cầu của JNDI LDAP provider phổ biến; hãy kiểm tra phiên bản JDK/provider thực tế.
3. `setBase("dc=example,dc=org")` đặt search base; các DN truyền vào `LdapTemplate` thường tương đối với base đã cấu hình. Mã ví dụ nhận `baseDn` từ ngoài để tránh ghi cứng môi trường.
4. `setUserDn` và `setPassword` là credential của **tài khoản dịch vụ** dùng mở context. Nếu sai, có thể nhận lỗi xác thực (`49`); tăng timeout sẽ không sửa được.
5. Cách tạo thủ công nhằm minh họa API. Trong Spring Boot/IoC, thường để framework quản lý lifecycle và lấy thông tin nhạy cảm từ nguồn secret phù hợp. Không ghi log cấu hình chứa password.

### 5.1. Có cần đặt timeout trong `LdapTemplate`?

`LdapTemplate` xử lý các thao tác LDAP và chuyển đổi exception, còn **kết nối và read timeout** thường thuộc cấu hình `ContextSource`/JNDI provider. Search có thể có giới hạn riêng qua `SearchControls` hoặc API query. Không nên tìm một “timeout tổng” duy nhất trên `LdapTemplate` rồi giả định nó bao trùm DNS, TLS, bind, search, retry và logic ứng dụng.

### 5.2. Lập giới hạn cho từng search

Đoạn mã sau đặt `SearchControls` cho một truy vấn cụ thể và sử dụng filter cố định để tập trung vào giới hạn thời gian. Khi nhận filter từ input người dùng, phải dùng builder để escape đúng cú pháp, không ghép chuỗi trực tiếp.

```java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public final class BoundedDirectorySearch {
    private final LdapTemplate ldapTemplate;

    public BoundedDirectorySearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findAn() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setTimeLimit(2000);
        controls.setCountLimit(100);

        return ldapTemplate.search(
                "ou=people",
                "(uid=an)",
                controls,
                (AttributesMapper<String>) attrs -> {
                    Attribute cn = attrs.get("cn");
                    return cn == null ? null : cn.get().toString();
                });
    }
}
```

Đây là ví dụ tìm kiếm; **không bảo đảm trả toàn bộ dữ liệu** khi giới hạn số lượng hoặc thời gian bị chạm. API cần diễn đạt rõ tính đầy đủ, thay đổi phạm vi hoặc sử dụng paging khi server hỗ trợ. Nếu `cn` là thuộc tính bắt buộc của hợp đồng nghiệp vụ, việc trả `null` khi không có `cn` cần được thay bằng một lỗi dữ liệu rõ ràng.

## 6. Xử lý lỗi ở tầng service: kết quả rỗng khác lỗi mạng

Giả sử ứng dụng tìm một nhân viên theo `uid`. DN được tạo bằng `LdapNameBuilder` để escape RDN; khi DN không tồn tại có thể trả `Optional.empty()`. Còn lỗi kết nối, server unavailable và timeout phải được giữ thành những kết quả lỗi riêng:

```java
import java.util.Optional;
import javax.naming.Name;
import javax.naming.directory.Attribute;

import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.ServiceUnavailableException;
import org.springframework.ldap.TimeLimitExceededException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class DirectoryPersonReader {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Optional<String> findCommonName(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        try {
            String cn = ldapTemplate.lookup(
                    dn,
                    (AttributesMapper<String>) attrs -> {
                        Attribute attribute = attrs.get("cn");
                        if (attribute == null) {
                            throw new IllegalStateException(
                                    "Entry tồn tại nhưng thiếu cn");
                        }
                        return attribute.get().toString();
                    });
            return Optional.ofNullable(cn);
        } catch (NameNotFoundException ex) {
            return Optional.empty(); // Chỉ DN không tồn tại.
        } catch (CommunicationException | ServiceUnavailableException ex) {
            throw new DirectoryUnavailableException(
                    "Thư mục LDAP không khả dụng", ex);
        } catch (TimeLimitExceededException ex) {
            throw new DirectoryQueryTimeoutException(
                    "Truy vấn LDAP vượt giới hạn thời gian", ex);
        }
    }

    public static class DirectoryUnavailableException extends RuntimeException {
        public DirectoryUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static class DirectoryQueryTimeoutException extends RuntimeException {
        public DirectoryQueryTimeoutException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

Lưu ý:

- `NameNotFoundException` của **lookup theo DN cụ thể** có thể được diễn giải là không có entry, nhưng `search` với base bị thiếu lại là lỗi cấu hình — cùng exception, khác ý nghĩa.
- Timeout mạng có thể đi qua `CommunicationException` hoặc một wrapper khác tùy provider; `TimeLimitExceededException` thường liên quan giới hạn Search chứ không bao phủ mọi read timeout.
- Không bắt toàn bộ `NamingException` và trả `Optional.empty()`: như vậy sẽ che lỗi xác thực, ACL, TLS và schema.
- `DirectoryUnavailableException` / `DirectoryQueryTimeoutException` là exception **miền ứng dụng ví dụ**, không phải lớp có sẵn của Spring LDAP. Chúng giữ `cause` để hệ thống log/giám sát phân loại chính xác.
- `LdapClient` và ODM cũng có thể sử dụng cơ chế exception Spring LDAP; kiểm tra hợp đồng API đúng phiên bản đang chạy khi đặt bộ xử lý tại ranh giới repository/service.

### 6.1. Mapping ra HTTP theo ngữ cảnh

| Lỗi nội bộ | Gợi ý trả HTTP nếu endpoint phụ thuộc LDAP | Vì sao |
| --- | --- | --- |
| Lookup DN không có, resource thực sự không tồn tại | `404 Not Found` | Tùy hợp đồng truy vấn một tài nguyên |
| Search filter không khớp, search base hợp lệ | `200 OK` + `[]` | Kết quả hợp lệ, không phải outage |
| LDAP tạm thời không khả dụng | `503 Service Unavailable` | Có thể thể hiện lỗi phụ thuộc hạ tầng |
| LDAP query vượt timeout/deadline | `504 Gateway Timeout` hoặc mã lỗi nội bộ phù hợp | Tùy vai trò backend/gateway và hợp đồng API |
| Tài khoản kỹ thuật bind sai credential | `500`/`503` tùy kiến trúc | Lỗi cấu hình dịch vụ, không phải client nhập sai mật khẩu |
| LDAP báo thiếu quyền tài khoản kỹ thuật | Lỗi hạ tầng/cấu hình | Không suy ra HTTP caller cần `403` |

Đây là **gợi ý có điều kiện**, không phải bảng ánh xạ chuẩn bắt buộc cho tất cả hệ thống. Không gửi nguyên `cause`, endpoint nội bộ, DN đầy đủ hay thông điệp SSL/JNDI đến client. Nếu backend trực tiếp gọi LDAP và không đóng vai trò gateway, mã `504` có thể không phù hợp; chọn mã nhất quán với API thực tế.

## 7. Retry an toàn: khi nào có thể và khi nào phải dừng?

Retry chỉ hữu ích khi có cơ sở rằng sự cố **tạm thời**. Cùng loại `CommunicationException` có thể xuất phát từ kết nối bị ngắt thoáng qua hoặc truststore sai cố định; không thể phân biệt bằng tên exception đơn lẻ.

| Tình huống | Có nên retry tự động? | Lý do |
| --- | --- | --- |
| DNS sai hostname cấu hình | Không | Retry cùng hostname không giải quyết cấu hình sai |
| Certificate hết hạn/truststore thiếu CA | Không | Cần sửa TLS/configuration |
| Mạng gián đoạn ngắn khi đọc | Có điều kiện | Retry ít lần, có deadline tổng, backoff và jitter |
| LDAP server bận/không sẵn sàng | Có điều kiện | Có thể thử failover hoặc chờ phục hồi, tránh gây quá tải |
| Read timeout của một search rất nặng | Thường không lặp nguyên query | Thu hẹp filter, index, scope hoặc tối ưu search |
| LDAP `timeLimitExceeded (3)` | Không retry cùng truy vấn vô hạn | Tối ưu query/giới hạn phía server |
| LDAP `invalidCredentials (49)` | Không với cùng credential | Cần sửa principal/secret hoặc xử lý chính sách tài khoản |
| LDAP `insufficientAccessRights (50)` | Không | Cần thay đổi quyền/cấu hình, không phải lỗi thời gian |
| Mất phản hồi sau Add/Modify/Delete | Không tự động nếu chưa biết kết quả | Server có thể đã áp dụng thay đổi |

Một chính sách retry có kiểm soát thường gồm **tối đa vài lần thử**, backoff tăng dần, jitter, deadline tổng và một cơ chế ngắt/circuit breaker khi tỷ lệ lỗi cao. Các giá trị cụ thể phải dựa trên yêu cầu độ trễ, tải LDAP và trạng thái server; không dùng một bộ thời gian cho mọi hệ thống.

### 7.1. Vì sao thao tác ghi đặc biệt nguy hiểm khi timeout?

Giả sử ứng dụng thực hiện Add người dùng qua `LdapTemplate.bind(dn, null, attrs)`:

```text
Ứng dụng                                LDAP server
    │                                         │
    ├────── Add(uid=an,ou=people) ───────────>│
    │                                         ├── Đã tạo entry
    │<────── Phản hồi bị mất ──────────────────X
    │
    ├── CommunicationException / timeout
    │
    └────── Nếu gửi lại Add ─────────────────>│
                                              └── Có thể nhận LDAP 68
                                                  (entryAlreadyExists)
```

Nhận `CommunicationException` **không chứng minh Add thất bại**. Retry có thể tạo xung đột; nếu lệnh là Modify, thay đổi có thể bị áp dụng hai lần hoặc ghi đè giá trị của một writer khác.

Với thao tác ghi:

1. Xác định có bằng chứng request chưa được gửi hay không; khi không chắc phải coi trạng thái là **chưa xác định**.
2. Đọc lại DN/trạng thái trên nguồn có tính nhất quán phù hợp, nếu có quyền.
3. Đối chiếu các trường định danh, version, trạng thái nghiệp vụ hoặc idempotency key nếu kiến trúc có hỗ trợ.
4. Chỉ retry khi thao tác được thiết kế idempotent hoặc trạng thái đã được xác minh an toàn.
5. Nếu không thể xác định kết quả, báo một trạng thái cần đối soát thay vì khẳng định “thất bại hoàn toàn” hoặc tự động ghi đè.

Đọc trên **replica khác** có thể chưa thấy cập nhật do replication lag. Một lookup ngay sau timeout thấy “chưa có” chưa đủ để kết luận Add lần đầu không được thực hiện.

### 7.2. Retry cho tìm kiếm không có nghĩa bỏ qua lỗi

Đọc dữ liệu thường dễ thử lại hơn ghi, nhưng vẫn có giới hạn:

- Một request HTTP phải tuân thủ deadline của chính nó; retry nhiều lần có thể khiến client timeout trước.
- Truy vấn tìm kiếm có referral hoặc nhiều trang có thể đã trả một phần dữ liệu. Khi retry phải quy định rõ liệu cần làm lại từ đầu, theo tiếp trang, hay báo kết quả chưa đầy đủ.
- Một số thông tin danh mục hoặc quyền truy cập có thể thay đổi giữa hai lần tìm kiếm; kết quả retry không nhất thiết là snapshot nhất quán.
- Khi LDAP gặp sự cố diện rộng, retry đồng loạt từ nhiều instance có thể tạo *retry storm*. Giới hạn đồng thời và dùng circuit breaker/bulkhead khi phù hợp.

## 8. TLS, StartTLS và pooling: nguồn lỗi hay bị chẩn đoán nhầm

### 8.1. LDAPS và StartTLS

**LDAPS** tạo kết nối được bảo vệ TLS ngay khi thiết lập giao tiếp; **StartTLS** nâng một kết nối LDAP thông thường lên kênh TLS theo quy trình protocol. Cả hai cách đều yêu cầu xác minh server certificate và chính sách TLS phù hợp.

Những nguyên nhân thường gặp:

- Chứng chỉ của server không được truststore tin cậy hoặc thiếu chứng chỉ trung gian.
- Tên host dùng kết nối không khớp định danh mà chứng chỉ thể hiện.
- Certificate hết hạn hoặc bị thay đổi mà client chưa cập nhật truststore.
- Server/client không thống nhất phiên bản TLS hoặc cipher suites được cho phép.
- Endpoint/port sai, proxy hoặc load balancer can thiệp vào quá trình handshake.

Lỗi như `SSLHandshakeException` có thể nằm trong chuỗi `cause` của lỗi JNDI/Spring LDAP. Cấu hình retry nhiều lần **không sửa** certificate/truststore. Không tắt xác minh certificate, không dùng trust manager “tin mọi chứng chỉ” để làm hệ thống trông có vẻ khỏe; kết nối LDAP có thể chứa credential và dữ liệu quyền truy cập nhạy cảm.

### 8.2. Pool kết nối và stale connection

Pooling có thể giảm chi phí mở TCP/TLS và bind nhiều lần, nhưng đồng thời tạo ra một nhóm lỗi khó thấy:

```text
Ứng dụng lấy DirContext từ pool
               │
               ├── Kết nối còn sống → thao tác hoạt động
               └── Kết nối đã bị server/LB đóng khi idle
                          │
                          ▼
                    I/O failure, reset hoặc read timeout
```

Kiểm tra:

- Pool có giới hạn kích thước, thời gian giữ idle và cách loại bỏ connection lỗi phù hợp không?
- Server hoặc load balancer có idle timeout ngắn hơn thời gian pool giữ connection không?
- Có nhiều endpoint/replica, nên một số connection đang trỏ tới server đã rời cluster không?
- Có vô tình **chia sẻ context đã xác thực bằng danh tính người dùng** giữa các request không? Việc này có thể ảnh hưởng nghiêm trọng đến phân quyền.

Cơ chế pooling của JNDI và Spring LDAP/LDAP integration có thể có lựa chọn cấu hình và giới hạn khác nhau theo phiên bản. Không nên tự động bật pooling cho mọi kiểu context, đặc biệt các trường hợp StartTLS hoặc bind theo từng người dùng, trước khi kiểm tra hướng dẫn bảo mật của provider. Khi thử giải quyết lỗi stale connection, cần xác định thời điểm lấy/trả context và xử lý kết nối hỏng, thay vì chỉ tăng read timeout.

### 8.3. Failover và nhiều LDAP endpoint

Failover chỉ an toàn nếu các endpoint có:

- Quy tắc bind, ACL và schema tương thích cho thao tác cần thực hiện.
- Trạng thái dữ liệu/replication đủ đáp ứng yêu cầu nhất quán của ứng dụng.
- TLS certificate và trust configuration hợp lệ cho từng hostname.
- Chính sách ghi rõ ràng: nơi nào được phép write, trường hợp nào read-only hoặc có referral.

Không giả định cấu hình nhiều URL tự cung cấp chuyển đổi tức thời và chính xác trong mọi tình huống. Phải kiểm tra semantics của `ContextSource`/provider, DNS/load balancer và cách xử lý request đang dang dở. Đặc biệt, failover sau timeout của thao tác ghi có thể khiến cùng yêu cầu được gửi tới một server khác khi chưa biết server cũ đã thực hiện hay chưa.

## 9. Quy trình chẩn đoán khi LDAP chậm hoặc mất kết nối

Khi vận hành thực tế, hãy điều tra theo thứ tự:

1. **Xác định thao tác và thời điểm:** bind, lookup, search, Add, Modify hay Delete? Lỗi trước kết nối hay trong lúc đợi phản hồi?
2. **Đọc exception và root cause:** phân biệt `org.springframework.ldap.CommunicationException`, `ServiceUnavailableException`, `TimeLimitExceededException`; tìm `ConnectException`, `SocketTimeoutException`, `UnknownHostException`, `SSLHandshakeException` nếu có.
3. **Kiểm tra endpoint:** hostname/DNS, port, route, firewall, health của LDAP server, tình trạng load balancer và môi trường triển khai. Dùng công cụ chẩn đoán kết nối trong môi trường được phép mà không đưa credential vào command/log công khai.
4. **Kiểm tra TLS:** certificate chain, truststore, hostname, phiên bản TLS, LDAPS/StartTLS và cấu hình credential. Không giảm bảo mật để bỏ qua lỗi handshake.
5. **Kiểm tra timeout theo từng lớp:** connect timeout, read timeout, search time limit, deadline request, queue/pool wait và số lần retry.
6. **Kiểm tra truy vấn:** search base, scope, filter, chỉ mục, số lượng entry, attribute cần tải, paging và referral; search chậm có thể do query chứ không do mạng.
7. **Kiểm tra pooling/failover:** stale connection, idle timeout, kích thước pool, server đích sau chuyển tuyến và replication lag.
8. **Xác định tác dụng phụ:** với thao tác ghi, cần đối soát trạng thái trước khi retry.
9. **Theo dõi xu hướng:** ghi metric độ trễ p50/p95/p99, tỷ lệ connect/read/search timeout, số connection đang dùng, các retry và tỷ lệ lỗi theo endpoint, không chỉ tổng lượng lỗi.

### 9.1. Dữ liệu log nào hữu ích?

Ví dụ **log có cấu trúc** (không chứa credential hoặc DN nguyên vẹn):

```json
{
  "event": "ldap_request_failed",
  "operation": "search",
  "directory": "corp-directory",
  "endpointAlias": "ldap-primary",
  "exception": "org.springframework.ldap.CommunicationException",
  "rootCauseType": "java.net.SocketTimeoutException",
  "durationMs": 5024,
  "attempt": 1,
  "correlationId": "req-8c21"
}
```

Giá trị trong ví dụ chỉ để minh họa cấu trúc log, không phải phép đo thực tế. Tránh ghi password, bind secret, token, full DN, giá trị attribute hoặc filter chứa dữ liệu cá nhân. Nếu cần liên hệ một entry trong quá trình chẩn đoán, dùng ID nội bộ hoặc thông tin đã được che/băm phù hợp chính sách dữ liệu. Không trả diagnostic message hoặc stack trace nguyên vẹn cho người dùng HTTP.

### 9.2. Một số tình huống vận hành

**A. Chuyển từ LDAP thường sang LDAPS rồi tất cả kết nối thất bại**

Nếu root cause là `SSLHandshakeException`, kiểm tra chain/truststore/hostname và endpoint trước; đổi mật khẩu hoặc tăng retry sẽ không sửa lỗi certificate.

**B. Chỉ một phần request bị lỗi sau khi để hệ thống idle lâu**

Có thể pool trả connection đã bị firewall/load balancer hoặc server đóng. Kiểm tra idle timeout, chính sách validation/loại bỏ connection lỗi, việc tạo lại context và đối chiếu thời điểm sự cố.

**C. Search người dùng chạy lâu rồi trả `TimeLimitExceededException`**

Kiểm tra filter có dùng thuộc tính được index, scope có quá rộng, base có đúng, server đang tải nặng và time limit phía server/client. Không chỉ tăng giới hạn rồi chấp nhận kết quả thiếu hoặc bỏ qua exception.

**D. Một số LDAP node trả `ServiceUnavailableException`, node khác vẫn hoạt động**

Kiểm tra tải node, referral, failover và replication. Với thao tác đọc có thể chuyển sang endpoint khỏe theo chính sách; với thao tác ghi phải xem node nào có quyền và có thể đã xử lý request trước khi mất kết nối.

**E. Sau khi tạo entry, API trả timeout; retry trả “entry already exists”**

Đây có thể là Add lần đầu đã thành công nhưng phản hồi thất lạc. Đọc lại entry và đối chiếu nguồn tạo/idempotency theo khả năng hệ thống, không mặc định coi là tạo thất bại hoặc do request mới tạo.

## 10. Kiểm thử timeout và lỗi mạng

Unit test kiểm tra service phân loại đúng exception; integration test trên LDAP server cô lập hoặc môi trường kiểm thử kiểm soát được có thể xác minh kết nối, certificate, search limit và tình huống server thật. Không sử dụng credential thật hoặc chủ động làm gián đoạn LDAP production để thử lỗi.

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Lookup DN tồn tại, kết nối khỏe | Trả dữ liệu đúng |
| Lookup DN không tồn tại | Trả not found theo hợp đồng; không báo outage |
| Search filter không khớp, base tồn tại | Danh sách rỗng, không tự ném lỗi mạng |
| JNDI/Spring LDAP `CommunicationException` | Service báo lỗi phụ thuộc hạ tầng; không chuyển thành `Optional.empty()` |
| `ServiceUnavailableException` | Phân loại availability; retry nếu và chỉ nếu phù hợp |
| `TimeLimitExceededException` | Báo timeout/search limit; xem tối ưu query và tính đầy đủ |
| DNS sai hoặc TCP port không nghe | Nhận diện root cause; không retry vô hạn |
| TLS certificate không tin cậy | Từ chối kết nối và báo lỗi cấu hình, không tắt certificate validation |
| Read timeout khi đang chờ Search | Không bỏ qua và giả định kết quả đã đầy đủ |
| Pool trả connection cũ đã đóng | Phát hiện, loại bỏ và tái tạo context theo cơ chế pool |
| Hai request đọc cùng timeout | Retry hữu hạn không làm quá tải LDAP server |
| Timeout sau LDAP Add/Modify thành công | Không tự phát lại thao tác ghi khi chưa đối soát trạng thái |
| Failover giữa hai replica chưa đồng bộ | Không coi ngay “entry chưa có” là bằng chứng lần ghi trước thất bại |

### 10.1. Unit test minh họa phân loại lỗi

Ví dụ JUnit và Mockito: khi `LdapTemplate.lookup` ném `CommunicationException`, service phải đưa ra lỗi availability. Constructor exception Spring LDAP nhận nguyên nhân JNDI:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.core.LdapTemplate;

class DirectoryPersonReaderTest {
    @Test
    void communicationFailureIsNotTreatedAsNotFound() {
        LdapTemplate ldapTemplate = mock(LdapTemplate.class);
        when(ldapTemplate.lookup(any(Name.class), any(
                org.springframework.ldap.core.AttributesMapper.class)))
                .thenThrow(new CommunicationException(
                        new javax.naming.CommunicationException(
                                "LDAP connection failed")));

        DirectoryPersonReader reader =
                new DirectoryPersonReader(ldapTemplate);

        assertThrows(
                DirectoryPersonReader.DirectoryUnavailableException.class,
                () -> reader.findCommonName("an"));
    }
}
```

Đây là unit test về **quyết định xử lý**, không chứng minh socket/LDAP server sẽ ném đúng loại exception trong mọi tình huống. Thử nghiệm thật cần kiểm soát nguồn lỗi, timeout và provider. Nếu bản Spring LDAP được dùng có overload khác, cần khớp đúng chữ ký `lookup` và cách stub generic của Mockito tại phiên bản đang dùng.

## 11. Những sai lầm thường gặp

1. **`catch (Exception)` rồi trả danh sách rỗng:** biến outage thành “không có dữ liệu”, có thể làm sai quyết định quyền truy cập.
2. **Bắt `javax.naming.CommunicationException` trực tiếp quanh `LdapTemplate`:** Spring LDAP thường đã chuyển thành runtime exception thuộc `org.springframework.ldap`.
3. **Coi mọi timeout là `TimeLimitExceededException`:** connect/read timeout và giới hạn Search có thể xuất hiện dưới các loại/cause khác nhau.
4. **Coi mọi `CommunicationException` đều có thể retry:** TLS truststore sai hoặc hostname sai cần sửa cấu hình.
5. **Đặt connect timeout rồi tưởng đã giới hạn toàn bộ request:** chờ đọc phản hồi, search limit và retry còn tách biệt.
6. **Tăng timeout cho query thiếu index:** làm tăng độ trễ nhưng không giải quyết nguyên nhân.
7. **Nuốt `SizeLimitExceededException` hoặc partial result để trả một danh sách:** có thể gây sai lệch vì dữ liệu không đầy đủ.
8. **Retry thao tác ghi sau mất phản hồi mà không đối soát:** server có thể đã áp dụng Add/Modify/Delete.
9. **Bật pooling mà không kiểm tra connection idle và danh tính bind:** dễ gặp stale connection hoặc nguy cơ dùng sai context.
10. **Tắt xác minh certificate để sửa lỗi LDAPS:** làm suy giảm an toàn của credential và dữ liệu thư mục.
11. **Dựa vào HTTP `503` để kết luận nguyên nhân:** HTTP là ánh xạ ứng dụng, cần kiểm tra root cause phía LDAP.
12. **Dùng một timeout cố định cho mọi endpoint mà bỏ qua deadline tổng:** retry có thể làm tăng hàng chờ và khuếch đại outage.

## 12. Câu hỏi tự đánh giá

**Câu 1.** `CommunicationException` của Spring LDAP có phải checked exception không?

**Đáp án:** Không; `org.springframework.ldap.CommunicationException` là runtime exception. `javax.naming.CommunicationException` của JNDI là checked exception.

**Câu 2.** Kết nối TCP thành công nhưng TLS certificate không được tin cậy, retry liên tục có giúp không?

**Đáp án:** Không. Cần kiểm tra certificate chain, truststore, hostname và chính sách TLS; timeout/retry không thay thế việc xác minh certificate.

**Câu 3.** Connect timeout, read timeout và search time limit có giống nhau không?

**Đáp án:** Không. Connect timeout bảo vệ giai đoạn mở kết nối, read timeout bảo vệ giai đoạn chờ phản hồi theo provider, search time limit áp dụng cho xử lý truy vấn Search.

**Câu 4.** Mã LDAP `timeLimitExceeded (3)` có nhất thiết được nhận mỗi khi client gặp `SocketTimeoutException` không?

**Đáp án:** Không. Client có thể timeout ở socket trước khi nhận bất kỳ LDAP response nào; không có result code từ server để đọc.

**Câu 5.** Vì sao một API read-only có thể retry có giới hạn, còn Add/Modify/Delete cần cẩn thận hơn?

**Đáp án:** Thao tác ghi có thể đã tạo tác dụng phụ dù phản hồi thất lạc. Cần đối soát trạng thái hoặc dùng thiết kế idempotent trước khi gửi lại.

**Câu 6.** `ServiceUnavailableException` và `CommunicationException` có đồng nghĩa không?

**Đáp án:** Không. Chúng đại diện cho những nhóm lỗi LDAP khác nhau, dù có thể đều khiến phụ thuộc LDAP không khả dụng với ứng dụng.

**Câu 7.** Khi search không trả entry và khi LDAP server không kết nối được, có nên cùng trả `Optional.empty()` không?

**Đáp án:** Không. “Không có entry” là trạng thái nghiệp vụ hợp lệ trong phạm vi truy vấn, còn lỗi kết nối phải được báo và giám sát riêng.

## 13. Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): cấu hình `ContextSource`, `LdapTemplate`, tìm kiếm và exception.
- [Spring LDAP API — `CommunicationException`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/CommunicationException.html): exception Spring LDAP liên quan giao tiếp.
- [Spring LDAP API — `LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): thao tác lookup/search/modify và chuyển đổi exception.
- [Spring LDAP API — `LdapContextSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/LdapContextSource.html): cấu hình và vòng đời nguồn LDAP context.
- [Java SE JNDI — `javax.naming.CommunicationException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/CommunicationException.html): checked exception ở tầng JNDI.
- [Java SE JNDI — `SearchControls`](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/SearchControls.html): cấu hình scope, count limit và time limit.
- [Oracle JNDI LDAP Provider Guide](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap.html): các property đặc thù của JNDI LDAP provider, gồm kết nối và read timeout.
- [RFC 4511 — Lightweight Directory Access Protocol](https://www.rfc-editor.org/rfc/rfc4511): thông điệp Search và resultCode như `timeLimitExceeded`, `busy`, `unavailable`.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): bảo mật xác thực LDAP và bảo vệ kết nối.

**Ghi nhớ:** `CommunicationException` là tín hiệu cần điều tra đường giao tiếp với LDAP; **timeout** là một nhóm hiện tượng với nhiều giai đoạn và nguyên nhân. Phân biệt connect/read/search timeout, truy ngược root cause, đặt deadline và retry có giới hạn, bảo vệ TLS/pooling, và luôn đối soát kết quả trước khi thử lại thao tác ghi đã có thể được server thực hiện.
