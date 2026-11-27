# Tách LDAP gateway khỏi domain service

## 1. Vì sao cần tách?

Trong một ứng dụng Spring, LDAP thường lưu tài khoản, tên hiển thị, email, nhóm hoặc các thuộc tính nhận diện. Ứng dụng lại có những quy tắc riêng: ai được xem hồ sơ, trường nào được công khai, khi nào cho phép đổi thông tin, và cách kết hợp tài khoản với dữ liệu nghiệp vụ trong cơ sở dữ liệu. Hai nhóm trách nhiệm này thay đổi theo những lý do khác nhau.

Nếu **domain service** gọi thẳng **LdapTemplate**, **LdapClient**, thao tác **DirContext**, tự tạo DN hay ghép LDAP filter, mỗi thay đổi của cấu trúc thư mục có thể lan vào nghiệp vụ. Ví dụ: chuyển người dùng từ nhánh **ou=people** sang **ou=members**, đổi thuộc tính đăng nhập từ **uid** sang **sAMAccountName**, hoặc đổi cách tìm entry sẽ buộc sửa và kiểm thử lại những lớp vốn chỉ chịu trách nhiệm về quy tắc hồ sơ.

Giải pháp là đặt một **LDAP gateway** ở tầng hạ tầng và cho nghiệp vụ làm việc qua một **port (interface)** mô tả nhu cầu của ứng dụng. Gateway chịu trách nhiệm kết nối, truy vấn, ánh xạ dữ liệu và xử lý lỗi giao tiếp LDAP. Tên lớp có thể là **DirectoryUserGateway**, **DirectoryAccountPort** hoặc **LdapUserAdapter**; điều quan trọng là hướng phụ thuộc.

Ví dụ xuyên suốt: ứng dụng quản lý thành viên cần tìm tài khoản theo tên đăng nhập, hiển thị hồ sơ công khai và có thể cập nhật email trên thư mục LDAP. Dữ liệu LDAP giả định đặt dưới **ou=people,dc=example,dc=org**, định danh đăng nhập là **uid**, tên hiển thị là **cn**, email là **mail**. Đây là *ví dụ schema*, không phải quy ước bắt buộc của mọi máy chủ LDAP.

~~~mermaid
flowchart LR
    UI["REST controller / API"] --> UC["Application service / use case"]
    UC --> DOMAIN["Domain service / quy tắc nghiệp vụ"]
    UC --> PORT["DirectoryUserGateway (port)"]
    ADAPTER["SpringLdapUserGateway (adapter)"] -. "implements" .-> PORT
    ADAPTER --> TEMPLATE["LdapTemplate / LdapClient"]
    TEMPLATE --> SOURCE["ContextSource"]
    SOURCE --> LDAP[("LDAP directory")]
~~~

**Nguyên tắc phụ thuộc:** application và domain không import API của Spring LDAP hay **javax.naming**. Adapter hạ tầng phụ thuộc vào port ứng dụng và chuyển dữ liệu thư mục thành kiểu dữ liệu mà nghiệp vụ hiểu được.

## 2. Phân trách nhiệm cho đúng

| Thành phần | Nên làm | Không nên làm |
| --- | --- | --- |
| Domain model / domain service | Biểu diễn thành viên, áp dụng quy tắc quyền xem, kiểm tra ý nghĩa dữ liệu nghiệp vụ | Đọc DN, tự tạo LDAP filter, điều khiển connection |
| Application service (use case) | Điều phối thao tác, gọi gateway, ánh xạ kết quả sang phản hồi ứng dụng, quyết định khi nào cần ghi | Chứa chi tiết schema LDAP, gọi trực tiếp LdapTemplate |
| Port **DirectoryUserGateway** | Khai báo các thao tác có ý nghĩa với ứng dụng, ví dụ tìm tài khoản và đổi email | Trả ra **Attributes**, **SearchResult**, **DirContextOperations** hoặc bắt người gọi tự cung cấp filter |
| Adapter **SpringLdapUserGateway** | Tạo truy vấn, ánh xạ **uid/cn/mail**, xử lý DN, gọi LdapTemplate, chuẩn hóa lỗi LDAP | Quyết định người dùng có được phép đổi email hay không |
| **ContextSource** / cấu hình | URL LDAP, base DN, bind account, TLS, timeout, lựa chọn pooling | Chứa mật khẩu trong mã nguồn hoặc thay thế quy tắc nghiệp vụ |

Một cổng tốt đặt tên theo **ý định**: **findByAccountName**, **changeEmail**, **findMemberships**. Tránh thiết kế các hàm như **search(String rawFilter)** hoặc **modify(Name dn, ModificationItem[] changes)** trong port; đó là chi tiết của giao thức, khiến ranh giới vừa tạo mất tác dụng.

Nếu ứng dụng có cơ sở dữ liệu quan hệ, repository của dữ liệu nghiệp vụ và gateway LDAP là **hai nguồn dữ liệu độc lập**. Không giả định thao tác LDAP sẽ tự tham gia transaction của JPA. Quyết định đồng bộ, bù trừ hoặc phát sự kiện khi cập nhật nhiều hệ thống phải nằm ở tầng điều phối ứng dụng.

## 3. Định nghĩa hợp đồng độc lập với LDAP

Ví dụ dùng Java 17 và các tên package minh họa. Mỗi định nghĩa **public** dưới đây nằm trong một tệp Java riêng của dự án.

**Domain model** biểu diễn thông tin thành viên mà ứng dụng sử dụng:

~~~java
// domain/MemberIdentity.java
package com.example.members.domain;

public record MemberIdentity(
        String accountName,
        String displayName,
        String email
) {}
~~~

**Port** đặt ở tầng application, chỉ dùng kiểu dữ liệu Java và domain:

~~~java
// application/port/DirectoryUserGateway.java
package com.example.members.application.port;

import com.example.members.domain.MemberIdentity;
import java.util.Optional;

public interface DirectoryUserGateway {
    Optional<MemberIdentity> findByAccountName(String accountName);
    void changeEmail(String accountName, String newEmail);
}
~~~

**Không tìm thấy** là kết quả hợp lệ của tìm kiếm nên dùng **Optional.empty()**. **Không kết nối được**, **không đủ quyền bind**, **entry không nhất quán** và **tìm ra nhiều entry cho một tài khoản** là những tình huống khác, không nên biến thành kết quả “không tìm thấy”.

Để ứng dụng phân biệt các lỗi hạ tầng mà không import exception của Spring LDAP, có thể khai báo lỗi trung lập:

~~~java
// application/port/DirectoryAccessException.java
package com.example.members.application.port;

public final class DirectoryAccessException extends RuntimeException {
    public enum Kind { UNAVAILABLE, DUPLICATE_ENTRY, INVALID_ENTRY }

    private final Kind kind;

    public DirectoryAccessException(Kind kind) {
        super("Directory operation failed: " + kind);
        this.kind = kind;
    }

    public DirectoryAccessException(Kind kind, Throwable cause) {
        super("Directory operation failed: " + kind, cause);
        this.kind = kind;
    }

    public Kind kind() {
        return kind;
    }
}
~~~

**Lưu ý thiết kế:** các kiểu **MemberIdentity** và **DirectoryAccessException** không chứa DN, **Attributes**, **LdapQuery** hoặc Spring-specific type. Nếu dùng Active Directory thay OpenLDAP, port và các quy tắc nghiệp vụ vẫn có thể giữ nguyên; chủ yếu phần ánh xạ trong adapter thay đổi.

## 4. Domain service giữ quy tắc nghiệp vụ

Trong ví dụ, hồ sơ công khai chỉ được hiển thị tên đăng nhập và tên hiển thị; email là thuộc tính không công khai. Nếu thư mục thiếu tên hiển thị, ứng dụng dùng tên đăng nhập làm phương án dự phòng. Đây là **quy tắc ứng dụng**, không phải trách nhiệm của LDAP.

~~~java
// domain/PublicMemberProfile.java
package com.example.members.domain;

public record PublicMemberProfile(
        String accountName,
        String displayName
) {}
~~~

~~~java
// domain/MemberProfilePolicy.java
package com.example.members.domain;

public final class MemberProfilePolicy {
    public PublicMemberProfile toPublicProfile(MemberIdentity member) {
        String name = member.displayName();
        if (name == null || name.isBlank()) {
            name = member.accountName();
        }
        return new PublicMemberProfile(member.accountName(), name);
    }
}
~~~

Application service điều phối việc lấy dữ liệu và áp dụng policy. Trong dự án thực tế có thể thay **NoSuchElementException** bằng exception nghiệp vụ dùng cho HTTP 404.

~~~java
// application/GetPublicMemberProfile.java
package com.example.members.application;

import com.example.members.application.port.DirectoryUserGateway;
import com.example.members.domain.MemberIdentity;
import com.example.members.domain.MemberProfilePolicy;
import com.example.members.domain.PublicMemberProfile;
import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;

@Service
public class GetPublicMemberProfile {
    private final DirectoryUserGateway directory;
    private final MemberProfilePolicy policy = new MemberProfilePolicy();

    public GetPublicMemberProfile(DirectoryUserGateway directory) {
        this.directory = directory;
    }

    public PublicMemberProfile execute(String accountName) {
        MemberIdentity member = directory.findByAccountName(accountName)
                .orElseThrow(() -> new NoSuchElementException(
                        "Không tìm thấy tài khoản: " + accountName));
        return policy.toPublicProfile(member);
    }
}
~~~

Không lớp nào trong ba lớp trên cần biết địa chỉ server LDAP, **ou=people**, schema **uid/cn/mail**, hoặc cách tạo kết nối. Có thể kiểm thử chính sách công khai chỉ bằng một object **MemberIdentity**, không cần LDAP server.

## 5. Hiện thực gateway bằng Spring LDAP

Adapter là nơi tập trung logic đặc thù của Spring LDAP: **LdapTemplate**, **LdapQueryBuilder**, **ContextMapper**, **DirContextOperations** và **ModificationItem**. Ví dụ sau dùng **LdapTemplate**; nếu dự án chọn **LdapClient** hoặc Spring LDAP ODM, chỉ adapter cần thay đổi. **ContextSource** có thể được Spring Boot cung cấp từ cấu hình.

~~~java
// infrastructure/ldap/SpringLdapUserGateway.java
package com.example.members.infrastructure.ldap;

import com.example.members.application.port.DirectoryAccessException;
import com.example.members.application.port.DirectoryUserGateway;
import com.example.members.domain.MemberIdentity;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Repository;

@Repository
public class SpringLdapUserGateway implements DirectoryUserGateway {
    private final LdapTemplate ldapTemplate;

    public SpringLdapUserGateway(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Override
    public Optional<MemberIdentity> findByAccountName(String accountName) {
        return locate(accountName).map(LocatedMember::member);
    }

    @Override
    public void changeEmail(String accountName, String newEmail) {
        if (newEmail == null || newEmail.isBlank()) {
            throw new IllegalArgumentException("Email không được rỗng");
        }
        LocatedMember found = locate(accountName)
                .orElseThrow(() -> new NoSuchElementException(
                        "Không tìm thấy tài khoản cần cập nhật"));

        ModificationItem[] changes = {
                new ModificationItem(
                        DirContext.REPLACE_ATTRIBUTE,
                        new BasicAttribute("mail", newEmail))
        };

        try {
            ldapTemplate.modifyAttributes(found.dn(), changes);
        } catch (org.springframework.ldap.CommunicationException ex) {
            throw new DirectoryAccessException(
                    DirectoryAccessException.Kind.UNAVAILABLE, ex);
        }
    }

    private Optional<LocatedMember> locate(String accountName) {
        if (accountName == null || accountName.isBlank()) {
            throw new IllegalArgumentException("Tên đăng nhập không được rỗng");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("uid", "cn", "mail")
                .where("uid").is(accountName);

        List<LocatedMember> matches;
        try {
            matches = ldapTemplate.search(
                    query,
                    (ContextMapper<LocatedMember>) context -> {
                        DirContextOperations entry = (DirContextOperations) context;
                        String uid = entry.getStringAttribute("uid");
                        if (uid == null || uid.isBlank()) {
                            throw new DirectoryAccessException(
                                    DirectoryAccessException.Kind.INVALID_ENTRY);
                        }
                        MemberIdentity member = new MemberIdentity(
                                uid,
                                entry.getStringAttribute("cn"),
                                entry.getStringAttribute("mail"));
                        return new LocatedMember(entry.getDn(), member);
                    });
        } catch (org.springframework.ldap.CommunicationException ex) {
            throw new DirectoryAccessException(
                    DirectoryAccessException.Kind.UNAVAILABLE, ex);
        }

        if (matches.size() > 1) {
            throw new DirectoryAccessException(
                    DirectoryAccessException.Kind.DUPLICATE_ENTRY);
        }
        return matches.stream().findFirst();
    }

    private record LocatedMember(Name dn, MemberIdentity member) {}
}
~~~

Các chi tiết cần hiểu khi triển khai:

1. **Query builder** tạo filter từ đầu vào **accountName**; tránh ghép chuỗi kiểu **"(uid=" + accountName + ")"** vì đầu vào có ký tự đặc biệt có thể làm sai filter hoặc tạo LDAP injection. Khi cần dựng DN từ thành phần động, dùng **LdapNameBuilder** thay vì nối chuỗi DN thủ công.
2. **base("ou=people")** là nhánh tương đối so với **base DN** đã cấu hình trong **ContextSource**. Nếu base DN là **dc=example,dc=org**, tìm kiếm được giới hạn trong **ou=people,dc=example,dc=org**. Không lặp lại base DN ở cả cấu hình và query.
3. **ContextMapper** cho phép giữ **DN thực** của entry bên trong adapter để cập nhật. Không giả định mọi entry đều có DN theo mẫu **uid=...,ou=people,...**: nhiều schema dùng **cn**, **entryUUID** hoặc vị trí OU khác nhau.
4. **attributes("uid", "cn", "mail")** giới hạn dữ liệu được đọc. Kiểm tra sự tồn tại của trường bắt buộc; thuộc tính tùy chọn như **cn** hoặc **mail** có thể vắng mặt. Không truy xuất hay log thuộc tính **userPassword**.
5. **modifyAttributes** thay một thuộc tính hiện có trong entry. Trước khi gọi gateway, application/domain cần kiểm tra quyền cập nhật và quy tắc email; gateway vẫn kiểm tra dữ liệu đầu vào cơ bản để không gửi request rỗng.
6. **CommunicationException** được chuyển thành exception trung lập. Trong sản phẩm thực tế, bổ sung mapping cho **AuthenticationException**, **NameNotFoundException**, **NoPermissionException**, vi phạm schema và timeout theo chính sách từng hệ thống; đừng gộp mọi lỗi thành **Optional.empty()**.

Đoạn mã mang tính mẫu cho schema minh họa; tên attribute, search base, cách xác định duy nhất một entry và quyền ghi phải được điều chỉnh theo LDAP server thật. Để tránh sai lệch khi entry bị đổi hoặc di chuyển giữa lúc tìm và cập nhật, có thể bắt lỗi “không còn entry” ở bước ghi và áp dụng chính sách thử lại hoặc báo xung đột phù hợp.

## 6. Cấu hình kết nối, TLS và pooling ở tầng hạ tầng

Trong dự án Spring Boot có Spring LDAP trên classpath, cấu hình kết nối có thể đặt trong **application.yml**:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

**LDAP_BIND_DN** là tài khoản dịch vụ chỉ có những quyền tối thiểu cần thiết; secret lấy từ biến môi trường hoặc secret manager. Ví dụ dùng **LDAPS** để bảo vệ kết nối. Phải xác thực chứng chỉ và tên máy chủ theo truststore được quản lý; đừng tắt kiểm tra TLS để “cho kết nối chạy được”. Nếu hạ tầng sử dụng **StartTLS**, cần cấu hình handshake và vòng đời connection đúng cách, không coi **ldap://** thuần là kết nối đã mã hóa.

Các lựa chọn như **timeout kết nối/đọc**, **pooling**, giới hạn số kết nối, kiểm tra connection cũ và cơ chế **retry** thuộc adapter/configuration. Cần cân nhắc pooling với **TLS/StartTLS** và các thao tác bind bằng danh tính người dùng: connection có thể mang trạng thái xác thực, vì vậy không tái sử dụng tùy tiện giữa các principal. Chỉ retry các thao tác an toàn theo tình huống; thao tác ghi LDAP có thể đã thành công dù client nhận timeout.

Không đưa credential LDAP, DN nội bộ hoặc filter chứa dữ liệu nhạy cảm vào log thông thường. Ở tầng API, lỗi thư mục gián đoạn thường được chuyển thành phản hồi tạm thời phù hợp, thay vì công bố chi tiết máy chủ hay bind account.

## 7. Xử lý xác thực và phân quyền đúng ranh giới

Tìm kiếm tài khoản, **xác thực mật khẩu** và **phân quyền ứng dụng** là ba nhu cầu khác nhau:

- **Tra cứu hồ sơ**: gateway đọc thuộc tính cần thiết qua service account có quyền hạn nhỏ nhất.
- **Xác thực**: nếu cần kiểm tra mật khẩu người dùng, thiết kế một cổng riêng như **DirectoryAuthenticationGateway**, thực hiện bind/xác thực theo cơ chế phù hợp (hoặc dùng tích hợp Spring Security LDAP). Không đọc trực tiếp giá trị mật khẩu trong entry để so sánh.
- **Phân quyền**: domain/application quyết định quyền thao tác theo vai trò hoặc chính sách của ứng dụng; gateway có thể cung cấp thông tin nhóm LDAP đã được ánh xạ sang mô hình trung lập nhưng không tự quyết định ai được sửa hồ sơ.

Đây cũng là lý do không nên truyền một đối tượng **DirContext** hoặc **LdapUserDetails** xuyên suốt các lớp. Chúng vừa làm lộ cách xác thực, vừa khóa nghiệp vụ vào một thư viện cụ thể.

## 8. Kiểm thử từng ranh giới

Không cần LDAP server để kiểm thử **domain service** và **application service**. Với domain, xác nhận tên rỗng được thay bằng tên đăng nhập và email không xuất hiện trong hồ sơ công khai. Với application, dùng fake gateway để mô phỏng tìm thấy, không tìm thấy và gateway lỗi:

~~~java
// Ý tưởng unit test: giả lập port, không cần kết nối mạng.
DirectoryUserGateway fake = new DirectoryUserGateway() {
    @Override
    public Optional<MemberIdentity> findByAccountName(String name) {
        return Optional.of(new MemberIdentity(
                "an", "Nguyễn An", "an@example.org"));
    }

    @Override
    public void changeEmail(String name, String email) {
        throw new UnsupportedOperationException();
    }
};

PublicMemberProfile actual = new GetPublicMemberProfile(fake).execute("an");
// Kỳ vọng: accountName = "an", displayName = "Nguyễn An";
// kiểu PublicMemberProfile không có thuộc tính email.
~~~

**Integration test cho adapter** cần một LDAP test server được khởi tạo bằng dữ liệu xác định (ví dụ OpenLDAP container hoặc LDAP server nhúng tương thích). Nên bao phủ các trường hợp sau:

| Tình huống | Kỳ vọng |
| --- | --- |
| Có đúng một entry khớp **uid** | Ánh xạ đúng **uid/cn/mail**, trả về domain model |
| Không có entry | **Optional.empty()**, không bị coi là hạ tầng lỗi |
| Nhiều entry cùng match | Lỗi **DUPLICATE_ENTRY**, không lấy phần tử đầu một cách tùy tiện |
| Thiếu attribute bắt buộc | Lỗi **INVALID_ENTRY** hoặc lỗi dữ liệu tương đương |
| Đầu vào chứa **\***, **(**, **)**, **\\** | Filter được escape đúng, không truy xuất ngoài ý định |
| Thay đổi email trên entry hợp lệ | Chỉ thuộc tính **mail** được thay; DN không bị dựng sai |
| LDAP tắt, timeout hoặc bind thiếu quyền | Exception được phân loại; không bị giả thành “không có người dùng” |
| TLS/certificate không hợp lệ | Kết nối bị từ chối, không âm thầm chuyển sang LDAP không mã hóa |

Có thể thêm phép kiểm kiến trúc để bảo đảm package **domain** và **application** không phụ thuộc vào **org.springframework.ldap** hoặc **javax.naming**. Một số dự án dùng ArchUnit; dự án nhỏ có thể duy trì quy ước import và kiểm tra trong code review.

## 9. Những lỗi thiết kế thường gặp

| Dấu hiệu | Hệ quả | Cách sửa |
| --- | --- | --- |
| Domain service inject **LdapTemplate** | Domain bị ràng buộc vào Spring LDAP, unit test phức tạp | Inject port vào use case; chuyển LDAP API vào adapter |
| Port nhận LDAP filter hoặc DN từ controller | Giao thức và schema lộ lên tầng API | Chỉ nhận tham số có nghĩa nghiệp vụ, như **accountName** |
| Gateway trả **Attributes** hoặc LDAP DTO | Caller phải biết tên **uid**, **cn**, **mail** | Map sang **MemberIdentity** trước khi trả |
| Coi mọi exception là “user not found” | Che giấu outage và lỗi cấu hình, dễ ra quyết định sai | Phân biệt absent, unavailable, dữ liệu sai, thiếu quyền |
| Ghép chuỗi DN/filter từ input | Sai escaping và tăng rủi ro injection | Dùng **LdapQueryBuilder**, **LdapNameBuilder** và mapper |
| Domain service tự cập nhật LDAP lẫn JPA | Quy tắc nghiệp vụ bị trộn với hai nguồn dữ liệu không cùng transaction | Điều phối qua port và thiết kế failure/retry nhất quán |
| Mọi chức năng đều dùng một gateway “đa năng” | Interface phình to, khó thay thế và khó kiểm thử | Tách cổng theo mục đích, chẳng hạn tra cứu và xác thực |

## 10. Checklist khi áp dụng trong dự án

1. Xác định tác vụ của ứng dụng: tra cứu danh tính, cập nhật thuộc tính, đọc nhóm hay xác thực. Viết **port** theo ngôn ngữ nghiệp vụ trước khi viết LDAP query.
2. Đặt model và domain rule ở nơi không phụ thuộc Spring LDAP; đưa **uid/cn/mail**, base DN, DN entry và filter vào adapter.
3. Dùng **ContextSource** với TLS và service account tối thiểu quyền; xác thực chứng chỉ, đặt timeout và kiểm soát pooling.
4. Chuẩn hóa kết quả **không tìm thấy** và các lỗi directory khác nhau; quy định chính sách retry, log và phản hồi API.
5. Kiểm thử domain/application bằng fake gateway; kiểm thử adapter với LDAP thực hoặc server thử nghiệm và schema tương ứng.
6. Khi đổi OpenLDAP, Active Directory, Spring LDAP **LdapTemplate**, **LdapClient** hoặc ODM, rà soát chủ yếu adapter và cấu hình; hợp đồng nghiệp vụ chỉ cần đổi nếu **yêu cầu ứng dụng** thật sự thay đổi.

**Kết luận:** tách gateway giúp domain service tập trung vào quy tắc ứng dụng, application service điều phối use case, còn Spring LDAP chịu trách nhiệm giao tiếp thư mục. Ranh giới rõ ràng giúp thay schema, cơ chế kết nối và cách ánh xạ mà không kéo theo thay đổi ở những lớp vốn không cần hiểu LDAP.
