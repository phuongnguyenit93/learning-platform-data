# Phân biệt LDAP port với Global Catalog trong Active Directory

## Mục tiêu bài học

**Spring Data LDAP** cho phép ứng dụng Java truy cập dịch vụ thư mục bằng repository và ánh xạ entry phân cấp thành đối tượng Java; **LdapTemplate** hỗ trợ tìm kiếm và CRUD ở mức thuộc tính. Khi directory đích là **Microsoft Active Directory Domain Services (AD DS)**, một quyết định quan trọng là **kết nối LDAP thông thường đến domain controller hay kết nối Global Catalog (GC)**. Hai kiểu endpoint đều có thể trả lời truy vấn LDAP, nhưng khác nhau về **phạm vi dữ liệu**, **thuộc tính được sao chép** và **vai trò trong thao tác ghi**.

Trong chương **Khác biệt máy chủ**, bài này giúp người học:

- Nhận biết các cổng **389, 636, 3268, 3269** và hiểu TLS được sử dụng như thế nào.
- Giải thích **domain controller**, **forest**, **domain naming context** và **Global Catalog**.
- Phân biệt việc tìm trong **một domain** với tra cứu trên **nhiều domain thuộc cùng một forest**.
- Hiểu **Partial Attribute Set (PAS)** và vì sao không thể mặc định mọi thuộc tính đều có trên GC.
- Thiết kế kết nối **Spring LDAP/Spring Data LDAP** riêng cho đọc qua GC và ghi qua domain controller khi cần.
- Kiểm tra vấn đề DN, filter, referrals, TLS, phân quyền, độ trễ replication và kết quả tìm kiếm giữa các máy chủ.

## 1. LDAP là giao thức; Global Catalog là vai trò dịch vụ của AD DS

**LDAP (Lightweight Directory Access Protocol)** là giao thức để tìm, đọc và thay đổi dữ liệu directory. Ứng dụng thực thi các yêu cầu như **bind**, **search**, **compare**, **add**, **modify**, **modify DN**, **delete** thông qua LDAP server.

Trong AD DS, **domain controller (DC)** chứa bản sao dữ liệu của domain mà nó phục vụ, cùng những naming context hệ thống cần thiết. Một AD forest có thể chứa nhiều domain. Ví dụ:

~~~text
Forest: corp.example.com
|
+-- Domain: corp.example.com
|   +-- DC=corp,DC=example,DC=com
|       +-- OU=People
|       +-- OU=Groups
|
+-- Child domain: branch.corp.example.com
    +-- DC=branch,DC=corp,DC=example,DC=com
        +-- OU=People
        +-- OU=Groups
~~~

Một DC ở **corp.example.com** thường có bản sao đầy đủ của domain **corp.example.com**, còn DC ở **branch.corp.example.com** có bản sao đầy đủ của domain **branch.corp.example.com**. Nếu tìm người dùng trên DC domain gốc bằng truy vấn LDAP thông thường, bạn không được mặc định truy vấn sẽ trực tiếp trả về mọi người dùng thuộc domain con.

**Global Catalog** là một vai trò/dịch vụ được bật trên một số domain controller trong forest AD DS. Một GC nắm:

1. **Bản sao đầy đủ** của các đối tượng thuộc domain của chính GC server.
2. **Bản sao một phần** của các đối tượng thuộc những domain còn lại trong **cùng forest**. Bản sao một phần này chỉ chứa tập thuộc tính được chọn, gọi là **Partial Attribute Set (PAS)**.

Nhờ đó, GC hữu ích cho các trường hợp như tra cứu người dùng theo **userPrincipalName**, email hoặc các thuộc tính có mặt trong PAS khi không biết người dùng thuộc domain nào.

> **Điểm cốt lõi:** Global Catalog sử dụng giao thức LDAP và các LDAP search filter quen thuộc; tên gọi GC không phải một phiên bản LDAP khác. Khác biệt nằm ở dịch vụ AD DS, dữ liệu mà endpoint cung cấp và cổng mà ứng dụng kết nối.

## 2. Bảng cổng LDAP và Global Catalog

| TCP port | Tên thường dùng | TLS | Phạm vi sử dụng điển hình |
| --- | --- | --- | --- |
| **389** | LDAP thông thường trên domain controller | Kết nối LDAP ban đầu; có thể nâng cấp bằng StartTLS nếu hỗ trợ và được cấu hình | Đọc/ghi và tra cứu trong phạm vi domain/naming context server phục vụ |
| **636** | **LDAPS** trên domain controller | TLS ngay từ đầu kết nối | Đọc/ghi directory qua kênh TLS, nhất là khi dùng bind có mật khẩu |
| **3268** | LDAP tới **Global Catalog** | Kết nối LDAP GC thông thường; không mặc nhiên được mã hóa | Tìm kiếm trong forest theo dữ liệu mà GC có thể cung cấp |
| **3269** | **GC over TLS / LDAPS GC** | TLS ngay từ đầu kết nối | Tìm kiếm forest qua GC với kết nối TLS |

Đây là **các cổng TCP thông dụng** của AD DS. Cổng **UDP 389** còn liên quan đến cơ chế **CLDAP** dùng trong định vị domain controller; đừng nhầm với việc ứng dụng Spring LDAP thực hiện các thao tác CRUD thông thường qua TCP.

Khi sử dụng tài khoản bind có mật khẩu, **ưu tiên 636 cho domain LDAP và 3269 cho GC**. Nếu muốn dùng StartTLS trên một endpoint LDAP không mã hóa, phải xác minh khả năng hỗ trợ và thực sự hoàn tất TLS **trước khi gửi mật khẩu**; chỉ dùng URL **ldap://** không tự động bật StartTLS.

Các cổng 3268/3269 chỉ có ý nghĩa với một DC thực sự là **Global Catalog server và đã sẵn sàng**. Không phải mọi DC trong forest đều được cấu hình GC. Một cổng đang mở cũng không bảo đảm dữ liệu GC đã replication xong hoặc đáp ứng truy vấn của ứng dụng.

### 2.1. Bốn URL nhìn giống nhau nhưng không tương đương

~~~text
ldap://dc01.corp.example.com:389
ldaps://dc01.corp.example.com:636
ldap://gc01.corp.example.com:3268
ldaps://gc01.corp.example.com:3269
~~~

Khác biệt ở cả **dịch vụ**, **cổng** và **đặc điểm bảo mật**. Hai URL đầu hướng đến LDAP trên DC; hai URL sau hướng tới GC trên DC được bật vai trò GC. Scheme **ldaps://** chỉ định kết nối TLS ngay từ đầu, không làm thay đổi tính chất **domain LDAP hay GC**.

Nếu cần một bản ghi ở **DC=branch,DC=corp,DC=example,DC=com** với toàn bộ thuộc tính được phép đọc, hãy chọn DC của **branch** trên cổng **636**. Nếu cần tra cứu tài khoản nằm ở domain chưa biết trong cùng forest bằng thuộc tính được GC sao chép, GC trên cổng **3269** thường thích hợp.

## 3. Phạm vi tìm kiếm: domain so với forest

### 3.1. LDAP domain endpoint thường trả lời trong naming context tương ứng

Truy vấn tới **ldaps://dc01.corp.example.com:636** với search base:

~~~text
OU=People,DC=corp,DC=example,DC=com
~~~

sẽ tìm trong nhánh **OU=People** của domain gốc. Với entry thuộc child domain:

~~~text
CN=An Nguyen,OU=People,DC=branch,DC=corp,DC=example,DC=com
~~~

muốn đọc/ghi toàn bộ dữ liệu, thông thường cần endpoint DC của **branch**, chẳng hạn:

~~~text
ldaps://branch-dc01.branch.corp.example.com:636
~~~

Một số thao tác LDAP giữa naming context có thể trả **referral**. Không nên mặc định rằng một LDAP search tại DC gốc luôn tự theo referral, kết hợp mọi kết quả từ tất cả domain, và giữ nguyên danh tính/kênh TLS khi chuyển server. Chính sách referral phải được thiết kế riêng.

### 3.2. GC hỗ trợ tra cứu nhiều domain

Giả sử ứng dụng cần tìm tài khoản có **userPrincipalName=an@branch.corp.example.com** nhưng không biết domain đích. Khi truy vấn **GC**:

~~~text
Endpoint: ldaps://gc01.corp.example.com:3269
Base DN:  DC=corp,DC=example,DC=com
Filter:   (&(objectCategory=person)(objectClass=user)(userPrincipalName=an@branch.corp.example.com))
~~~

GC có thể sử dụng bản sao thuộc tính của những domain khác để trả về DN tương ứng, nếu đối tượng nằm trong phạm vi search base và các thuộc tính trong filter đã có trên GC.

**Lưu ý về nhiều domain tree:** một forest có thể chứa **nhiều cây domain với DN không cùng hậu tố**. Ví dụ forest gốc có domain **corp.example.com**, nhưng có thêm tree **example.net**. Khi tìm với base **DC=corp,DC=example,DC=com**, đừng mặc định mọi naming context có DN ngoài nhánh đó cũng được bao phủ. Cần xác định các domain naming context cần tìm và chiến lược tra cứu qua GC phù hợp, chẳng hạn tìm riêng từng domain base hoặc sử dụng cơ chế định vị/tra cứu đã được kiểm thử.

GC **không tự tìm qua forest khác chỉ vì có trust**. AD forest trust và GC forest scope là hai khái niệm riêng.

### 3.3. DN có đầy đủ cấu trúc domain

Ví dụ kết quả GC cho An:

~~~ldif
dn: CN=An Nguyen,OU=People,DC=branch,DC=corp,DC=example,DC=com
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: user
userPrincipalName: an@branch.corp.example.com
displayName: An Nguyen
~~~

**DN trả về phản ánh vị trí thật của đối tượng trong directory**. Khi cập nhật người dùng đó, ứng dụng cần định tuyến theo **domain của DN** tới một DC có thể xử lý thao tác ghi, thay vì cho rằng DN đó thuộc domain của GC server.

Trong Spring LDAP, phân biệt **DN đầy đủ của entry** với **DN tương đối theo base DN** của từng **ContextSource**. Nếu ContextSource có base **DC=branch,DC=corp,DC=example,DC=com**, DN tương đối của An có thể là **CN=An Nguyen,OU=People**. Không nối thêm base DN hai lần.

## 4. Partial Attribute Set (PAS): giới hạn quan trọng của GC

GC giữ bản sao một phần của các đối tượng thuộc domain khác. **PAS** là tập thuộc tính được cấu hình để replication vào GC. Mục tiêu là cung cấp tra cứu nhanh trong forest mà không sao chép mọi thuộc tính của mọi domain vào mọi GC.

Ví dụ giả định một đối tượng ở **branch.corp.example.com** có:

~~~text
distinguishedName
userPrincipalName
displayName
mail
department
telephoneNumber
someCustomAttribute
~~~

Khi hỏi **domain DC của branch** qua cổng 636, client có thể lấy những thuộc tính mà tài khoản được phép đọc và server có lưu. Khi hỏi **GC đặt ở domain khác**, một số thuộc tính có thể không được trả nếu **không nằm trong PAS**; những thuộc tính được phép đọc và có trong bản sao GC mới sẵn sàng cho truy vấn.

| Tình huống | Với domain LDAP | Với GC |
| --- | --- | --- |
| Đọc người ở chính domain của server | Có thể đọc các thuộc tính server lưu, tùy ACL | GC có bản sao đầy đủ của domain mình, nhưng vẫn cần kiểm tra hành vi thực tế |
| Đọc người ở domain khác trong forest | Cần chọn đúng DC, xử lý referral hoặc gọi domain đích | GC có bản sao một phần, phục vụ tra cứu theo PAS |
| Tìm theo thuộc tính không nằm trong PAS | Tìm trên DC của domain chứa thuộc tính | Có thể không tìm ra entry thuộc domain khác |
| Đọc thuộc tính custom không có trên GC | Có thể đọc tại DC của domain đích | Có thể thiếu hoặc không có giá trị |
| Thay đổi thuộc tính hồ sơ/người dùng | Thực hiện trên DC phù hợp và có quyền | Thiết kế ứng dụng **không ghi qua endpoint GC**; dùng DC của domain đối tượng |

**Không có danh sách PAS cố định áp dụng cho mọi forest và mọi phiên bản AD**. Nhiều thuộc tính thường dùng để tra cứu, chẳng hạn **userPrincipalName**, **mail**, **displayName**, có thể có trên GC, nhưng quản trị viên và schema của forest có thể thay đổi danh sách. Cần **kiểm tra schema/PAS của forest thực tế** và các thuộc tính nghiệp vụ đang cần.

Một thuộc tính thiếu trên kết quả GC không luôn có nghĩa entry thiếu thuộc tính đó tại nguồn. Các nguyên nhân có thể là:

- Thuộc tính không được đưa vào PAS cho bản sao của domain khác.
- ACL không cho tài khoản bind đọc thuộc tính.
- Thuộc tính thực sự không có giá trị.
- Replication tới GC chưa hoàn tất hoặc một DC đang có dữ liệu khác.
- Truy vấn đang chọn nhầm base, scope hoặc filter.

Vì vậy, **không đồng nhất giá trị null của GC với null ở domain DC** khi logic nghiệp vụ cần độ chính xác cao.

### 4.1. Kiểm tra thuộc tính có trong PAS không

Trong AD schema, định nghĩa **attributeSchema** có cờ **isMemberOfPartialAttributeSet** cho biết một thuộc tính được chọn vào Global Catalog PAS. Việc đọc schema cần quyền và search base phù hợp.

Ví dụ về ý tưởng truy vấn:

~~~text
Search base: CN=Schema,CN=Configuration,DC=corp,DC=example,DC=com
Filter:      (&(objectClass=attributeSchema)(lDAPDisplayName=department))
Attributes:  lDAPDisplayName, isMemberOfPartialAttributeSet
~~~

Đường dẫn schema naming context thật phải được lấy từ **RootDSE.schemaNamingContext**; không hardcode **CN=Schema,CN=Configuration,...** trong chương trình khi chưa xác nhận tên miền/cấu trúc forest. Thay đổi PAS ảnh hưởng replication toàn forest, nên là công việc quản trị directory, không phải một bước cấu hình tự động của ứng dụng Spring LDAP.

## 5. Lựa chọn endpoint theo yêu cầu nghiệp vụ

| Nhu cầu | Endpoint khuyến nghị | Vì sao |
| --- | --- | --- |
| Tìm người dùng theo UPN/mail trên nhiều domain cùng forest | **GC 3269** | Giúp tìm đối tượng bằng những thuộc tính được sao chép vào PAS |
| Đọc nhiều trường hồ sơ custom của người dùng trong một domain | **DC của domain đó, LDAPS 636** | Truy cập bản sao đầy đủ của domain, phụ thuộc ACL |
| Tạo user, đổi mật khẩu, đổi DN hoặc cập nhật thuộc tính | **Domain DC 636** | Thao tác ghi thuộc domain đích và có kiểm tra schema/ACL |
| Tra cứu nhóm trực tiếp trong một domain | **DC 636** | Đọc đầy đủ thông tin membership trong phạm vi domain |
| Tìm người dùng toàn forest rồi đọc thêm thông tin | **GC 3269 → DC domain đích 636** | GC dùng để tìm, DC dùng để đọc chi tiết hoặc thay đổi |
| Tra cứu quyền hiệu lực phức tạp | Cơ chế kiểm tra quyền/nhóm phù hợp AD, không chỉ một search GC | Membership lồng nhau và domain-local group có quy tắc riêng |

**Mẫu hai giai đoạn** thường dễ kiểm soát:

~~~mermaid
flowchart TD
    A["Ứng dụng cần tìm một người dùng trong forest"] --> B["Tìm qua GC:3269 theo UPN / thuộc tính trong PAS"]
    B --> C{"Tìm được DN?"}
    C -->|Không| D["Thông báo không tìm thấy; kiểm tra base, PAS, replication"]
    C -->|Có| E["Xác định domain từ DN"]
    E --> F["Chọn domain DC được phép từ cấu hình"]
    F --> G["Đọc thuộc tính chi tiết hoặc ghi qua LDAPS:636"]
    G --> H["Kiểm tra ACL, schema và kết quả cuối"]
~~~

Không lấy hostname của DC từ dữ liệu LDAP không tin cậy rồi kết nối tùy ý. Ứng dụng nên có danh sách domain/endpoint được quản trị, cơ chế DNS/AD discovery đáng tin và quy tắc phân quyền trước khi ghi.

## 6. Khám phá AD DC và GC server

### 6.1. Dùng DNS SRV record

Trong môi trường AD DS, các bản ghi DNS SRV hỗ trợ client xác định domain controller và Global Catalog. Ví dụ ở forest có DNS root **corp.example.com**:

~~~bash
# Tìm DC cho domain (ví dụ phổ biến; bản ghi thực tế tùy DNS/AD site).
nslookup -type=SRV _ldap._tcp.dc._msdcs.corp.example.com

# Tìm Global Catalog trong forest.
nslookup -type=SRV _gc._tcp.corp.example.com
~~~

DNS SRV giúp định vị server, nhưng ứng dụng còn phải xem xét **site**, tính sẵn sàng, độ trễ mạng và lựa chọn endpoint an toàn. Certificate trên LDAPS endpoint phải có **DNS SAN khớp hostname thực tế client sử dụng**. Một tên alias hoặc load-balancer DNS cần được bao phủ bởi SAN nếu đó là tên trong URL.

### 6.2. Đọc RootDSE để xác nhận naming context

**RootDSE** là entry đặc biệt ở base DN rỗng, cung cấp thông tin server. Có thể đọc nó trên LDAP/GC endpoint được bảo vệ:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://gc01.corp.example.com:3269 \
  -D "CN=svc-reader,OU=Service Accounts,DC=corp,DC=example,DC=com" -W \
  -b "" -s base \
  defaultNamingContext rootDomainNamingContext \
  configurationNamingContext schemaNamingContext \
  namingContexts isGlobalCatalogReady
~~~

Những thuộc tính RootDSE có thể giúp xác định **domain mặc định của server**, **forest root domain**, **configuration/schema naming context** và **GC readiness**, tùy loại server/phiên bản và quyền đọc. Không suy luận chỉ từ **defaultNamingContext** rằng server đang phục vụ GC toàn forest: thuộc tính này thường phản ánh domain của máy chủ, trong khi GC có thể chứa bản sao một phần của nhiều domain khác.

Một cách kiểm tra tốt là **truy vấn một DN đã biết thuộc domain khác** qua cổng 3269, rồi đối chiếu với truy vấn cùng DN trên DC của domain đó.

## 7. Kiểm tra thực tế bằng ldapsearch

Để so sánh, giả sử có:

- Root-domain DC: **dc01.corp.example.com**.
- Child-domain DC: **branch-dc01.branch.corp.example.com**.
- Global Catalog: **gc01.corp.example.com**.
- Người dùng **an@branch.corp.example.com** thuộc child domain.

### 7.1. Tra cứu bằng GC qua TLS

~~~bash
ldapsearch -LLL -x \
  -H ldaps://gc01.corp.example.com:3269 \
  -D "CN=svc-reader,OU=Service Accounts,DC=corp,DC=example,DC=com" -W \
  -b "DC=corp,DC=example,DC=com" -s sub \
  "(&(objectCategory=person)(objectClass=user)(userPrincipalName=an@branch.corp.example.com))" \
  distinguishedName userPrincipalName displayName mail
~~~

Truy vấn này minh họa một forest có **child domain nằm dưới cùng cây DN của root domain**. Nếu forest có domain tree khác hậu tố, cần truy vấn với naming context thích hợp. Kết quả phụ thuộc PAS, replication, filter và ACL.

### 7.2. Tra cứu trực tiếp domain DC của người dùng

~~~bash
ldapsearch -LLL -x \
  -H ldaps://branch-dc01.branch.corp.example.com:636 \
  -D "CN=svc-reader,OU=Service Accounts,DC=corp,DC=example,DC=com" -W \
  -b "DC=branch,DC=corp,DC=example,DC=com" -s sub \
  "(&(objectCategory=person)(objectClass=user)(userPrincipalName=an@branch.corp.example.com))" \
  distinguishedName userPrincipalName displayName mail department
~~~

Ở đây, **department** là một thuộc tính thêm để minh họa kiểm tra dữ liệu trên DC nguồn. Nếu GC trả không có một thuộc tính mà domain DC trả có, cần kiểm tra PAS/ACL/replication thay vì coi kết quả GC là nguồn đầy đủ tuyệt đối.

Các ví dụ sử dụng **-W** để nhập bind password tương tác. Công cụ ldapsearch/OpenLDAP và JVM dùng hệ thống cấu hình CA khác nhau; phải cấu hình trust đúng, xác minh server certificate và **không vô hiệu hóa hostname verification** để chạy được lệnh.

## 8. Cấu hình Spring Boot dùng GC cho truy vấn

Nếu ứng dụng chỉ cần tìm kiếm directory, có thể cấu hình một **LdapTemplate** qua GC:

~~~yaml
spring:
  ldap:
    urls: ldaps://gc01.corp.example.com:3269
    base: DC=corp,DC=example,DC=com
    username: ${GC_BIND_DN}
    password: ${GC_BIND_PASSWORD}
~~~

Ứng dụng phải có CA phù hợp trong truststore JVM, đúng hostname SAN và một tài khoản được phép đọc các thuộc tính cần truy vấn. **base** cần tương ứng phạm vi tìm kiếm; nếu forest có nhiều domain tree, thiết kế truy vấn theo từng naming context thay vì tin rằng một base duy nhất bao trùm mọi domain.

Ví dụ service sử dụng **LdapTemplate**:

~~~java
package org.example.directory;

import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

record DirectoryUser(String upn, String displayName) {}

@Service
public class ForestDirectoryLookup {
    private final LdapTemplate ldapTemplate;

    public ForestDirectoryLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryUser> findByUpn(String upn) {
        if (upn == null || upn.isBlank() || upn.length() > 256) {
            throw new IllegalArgumentException("UPN không hợp lệ");
        }

        return ldapTemplate.search(
                query().base("")
                        .attributes("userPrincipalName", "displayName")
                        .where("objectCategory").is("person")
                        .and("objectClass").is("user")
                        .and("userPrincipalName").is(upn),
                (AttributesMapper<DirectoryUser>) attrs ->
                        new DirectoryUser(
                                value(attrs, "userPrincipalName"),
                                value(attrs, "displayName"))
        );
    }

    private static String value(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null ? null : (String) attribute.get();
    }
}
~~~

Vì cấu hình **spring.ldap.base** đã là **DC=corp,DC=example,DC=com**, **query().base("")** có ý nghĩa tìm từ base của ContextSource. Bộ lọc dùng **LdapQueryBuilder** để escape giá trị UPN; không ghép filter thủ công với chuỗi từ request. Kết quả trả DTO với **hai thuộc tính được yêu cầu**, phù hợp ý tưởng GC lookup.

**Giới hạn của mẫu code:** đây là ví dụ tìm kiếm ngắn, chưa bổ sung size limit, timeout, phân trang, kiểm tra tính duy nhất của UPN hay xử lý nhiều naming context. **Không tự động suy ra một người dùng duy nhất** từ một danh sách kết quả. Với các thuộc tính nhạy cảm hoặc không có trong PAS, hãy đọc tiếp từ DC của domain đích sau khi đã định vị DN.

Spring Data LDAP repository cũng có thể đọc qua một ContextSource trỏ đến GC, nhưng các **@Entry**, **@Attribute** và phương thức repository không khiến thuộc tính ngoài PAS xuất hiện trên GC. Annotation ánh xạ Java không thay đổi phạm vi dữ liệu của directory server.

## 9. Tách GC đọc và domain LDAP ghi trong ứng dụng Spring

Ứng dụng vừa tìm kiếm toàn forest vừa cập nhật thông tin người dùng nên khai báo **hai đường kết nối rõ ràng**: GC để đọc tra cứu, domain DC để đọc chi tiết/ghi.

Ví dụ cấu hình cho một domain đích đã được biết trước:

~~~yaml
app:
  ldap:
    gc:
      url: ldaps://gc01.corp.example.com:3269
      base: DC=corp,DC=example,DC=com
      bind-dn: ${GC_BIND_DN}
      password: ${GC_BIND_PASSWORD}
    domain:
      url: ldaps://dc01.corp.example.com:636
      base: DC=corp,DC=example,DC=com
      bind-dn: ${DOMAIN_BIND_DN}
      password: ${DOMAIN_BIND_PASSWORD}
~~~

Java configuration minh họa Spring LDAP:

~~~java
package org.example.directory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration(proxyBeanMethods = false)
public class DirectoryConnections {

    @Bean("gcContextSource")
    LdapContextSource gcContextSource(
            @Value("${app.ldap.gc.url}") String url,
            @Value("${app.ldap.gc.base}") String base,
            @Value("${app.ldap.gc.bind-dn}") String bindDn,
            @Value("${app.ldap.gc.password}") String password) {
        return contextSource(url, base, bindDn, password);
    }

    @Bean("domainContextSource")
    LdapContextSource domainContextSource(
            @Value("${app.ldap.domain.url}") String url,
            @Value("${app.ldap.domain.base}") String base,
            @Value("${app.ldap.domain.bind-dn}") String bindDn,
            @Value("${app.ldap.domain.password}") String password) {
        return contextSource(url, base, bindDn, password);
    }

    private static LdapContextSource contextSource(
            String url, String base, String bindDn, String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source; // Spring sẽ khởi tạo bean và gọi lifecycle.
    }

    @Bean("gcTemplate")
    LdapTemplate gcTemplate(
            @Qualifier("gcContextSource") ContextSource source) {
        return new LdapTemplate(source);
    }

    @Bean("domainTemplate")
    LdapTemplate domainTemplate(
            @Qualifier("domainContextSource") ContextSource source) {
        return new LdapTemplate(source);
    }
}
~~~

Trong service:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class DirectoryService {
    private final LdapTemplate gcTemplate;
    private final LdapTemplate domainTemplate;

    public DirectoryService(
            @Qualifier("gcTemplate") LdapTemplate gcTemplate,
            @Qualifier("domainTemplate") LdapTemplate domainTemplate) {
        this.gcTemplate = gcTemplate;
        this.domainTemplate = domainTemplate;
    }

    // Truy vấn forest dùng gcTemplate;
    // đọc chi tiết hoặc ghi trong domain đã cấu hình dùng domainTemplate.
}
~~~

Khi có nhiều **LdapTemplate/ContextSource**, luôn dùng **@Qualifier** hoặc định danh tương đương để tránh tiêm nhầm bean. Repository được cấu hình qua Spring Data LDAP cũng phải được gán **đúng ContextSource**; không giả định mọi repository tự chọn GC hay domain dựa trên DN được truyền.

**Cấu hình minh họa chỉ phục vụ domain gốc.** Nếu cần ghi người dùng ở **branch.corp.example.com**, ứng dụng phải có domain ContextSource trỏ tới DC của **branch**, với base tương ứng, hoặc cơ chế định tuyến có allowlist đã được kiểm soát. Không lấy DN thuộc branch rồi gửi thẳng vào **domainTemplate** đang cấu hình cho root domain và kỳ vọng chắc chắn thành công.

## 10. Những giới hạn không thể giải quyết chỉ bằng đổi cổng

### 10.1. Replication và tính mới của dữ liệu

GC nhận bản sao một phần từ các domain qua replication. Nếu vừa tạo hoặc cập nhật người dùng ở một DC, GC khác có thể **chưa phản ánh ngay** thay đổi. Kết quả tìm kiếm phụ thuộc vị trí DC/GC, trạng thái replication và thời điểm truy vấn.

Nếu nghiệp vụ cần **đọc ngay sau khi ghi (read-your-writes)**, ưu tiên xác minh trên DC có liên quan đến thao tác vừa thực hiện. Không coi kết quả GC cũ là bằng chứng rằng giao dịch ghi thất bại.

### 10.2. Thành viên nhóm và quyền truy cập

Group membership của AD có những quy tắc theo **domain local**, **global**, **universal**, mức lồng nhau và phạm vi áp dụng. GC được dùng cho một số nhu cầu tra cứu thành viên trên nhiều domain, đặc biệt liên quan đến **universal groups**, nhưng **không thể lấy một search member/memberOf duy nhất trên GC làm lời giải đầy đủ cho mọi quyền hiệu lực**.

Khi cần quyết định cấp quyền, sử dụng nguồn/thuật toán phù hợp với chính sách AD, token và nhóm được áp dụng tại tài nguyên đích. Đối chiếu với DC/domain liên quan nếu dữ liệu membership không thuộc phạm vi GC hoặc có độ trễ sao chép.

### 10.3. Một cổng GC không tương đương quyền ghi toàn forest

Việc GC có thể **đọc một phần dữ liệu của nhiều domain** không có nghĩa tài khoản ứng dụng được tạo/sửa/xóa entry của mọi domain hoặc có thể ghi qua GC port. **Định tuyến ghi tới DC của domain sở hữu entry** và để server áp dụng ACL, schema, quyền thao tác, mật khẩu và quy tắc DN.

Đừng sử dụng cùng một tài khoản quản trị rộng quyền cho cả tra cứu GC và thao tác cập nhật nếu nghiệp vụ có thể tách thành tài khoản **GC read-only** và tài khoản **domain writer** với quyền tối thiểu.

### 10.4. Không phải mọi directory có Global Catalog

**Global Catalog là đặc điểm của AD DS forest**; nó không phải một dịch vụ mặc định của OpenLDAP hoặc mọi LDAP directory khác. AD LDS, Microsoft Entra ID và những LDAP server khác không nên mặc định có cùng hành vi cổng 3268/3269. Nếu ứng dụng Spring LDAP cần hỗ trợ nhiều loại directory, hãy để chiến lược chọn endpoint/phạm vi tìm kiếm tùy nhà cung cấp và có integration test.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| **Connection refused** trên 3269 | Endpoint không phải GC, GC chưa sẵn sàng, cổng không mở hoặc firewall chặn | Kiểm tra DNS SRV, GC readiness, listener, firewall |
| **PKIX path building failed** trên 3269/636 | JVM chưa trust CA/certificate chain của endpoint | Kiểm tra truststore JVM, intermediate CA và chứng chỉ server |
| **Hostname mismatch** | Tên trong LDAPS URL không khớp SAN certificate | Cấp lại certificate/đổi URL đúng tên đã được phê duyệt |
| Tìm thấy người trên 3269 nhưng không có **department** | Thuộc tính không có trong PAS ở bản sao domain khác, hoặc bị ACL/replication hạn chế | Kiểm tra PAS và truy vấn cùng DN ở domain DC |
| Tìm thấy ở domain DC nhưng không thấy ở GC | Sai base/scope/filter, thiếu PAS hoặc replication chưa xong | So sánh search base, RootDSE, PAS và trạng thái replication |
| Tìm tại root domain không thấy user ở tree domain khác | DN không nằm dưới base dùng cho truy vấn | Xác định naming context của domain tree thứ hai |
| **Invalid credentials / LDAP result 49** | Bind DN, password hoặc chính sách tài khoản sai | Kiểm tra xác thực sau khi TLS đã thành công |
| **No such object / LDAP result 32** | DN hoặc base sai, hoặc chọn nhầm domain DC | Kiểm tra naming context và DN tương đối/đầy đủ |
| **Insufficient access rights / result 50** | Tài khoản không có quyền đọc/ghi thuộc tính | Kiểm tra ACL và quyền cụ thể |
| Cập nhật LDAP xong nhưng GC vẫn thấy dữ liệu cũ | Replication lag | Đọc lại tại domain DC và theo dõi replication |
| Query trả quá nhiều kết quả hoặc bị giới hạn | Search scope rộng, size/time limits hoặc cơ chế phân trang | Thêm filter, giới hạn kết quả, dùng paging theo hỗ trợ server |

**Lưu ý về giới hạn kích thước kết quả:** AD có các giới hạn tìm kiếm và cơ chế range retrieval cho một số thuộc tính đa giá trị lớn như **member**. Chuyển sang GC không tự loại bỏ giới hạn về kích thước/paging và cũng không biến một danh sách thành viên lớn thành dữ liệu đầy đủ tức thì.

## 12. Kiểm thử tích hợp với AD DS

Để kiểm thử đúng khác biệt, nên dùng **forest thử nghiệm** có ít nhất domain gốc và child domain, một DC không bật GC (nếu có thể) và một DC bật GC. Chuẩn bị tài khoản đọc có quyền tối thiểu, dữ liệu mẫu ở cả hai domain và chứng chỉ TLS tin cậy.

| Ca kiểm thử | Thực hiện | Kết quả cần chứng minh |
| --- | --- | --- |
| Domain LDAP 636 | Tìm người dùng trong domain của DC | Trả về dữ liệu được phép đọc của domain đó |
| GC 3269 | Tìm người dùng thuộc domain con qua GC | Trả về đối tượng nếu base/filter và PAS phù hợp |
| PAS | So sánh một thuộc tính có trong PAS và một thuộc tính không có trong PAS tại domain khác | GC có thể thiếu trường không được sao chép; domain DC trả dữ liệu nếu được phép |
| Base DN giới hạn | Dùng base chỉ nằm trong domain gốc | Kết quả tuân theo phạm vi DN, không mặc định toàn forest |
| Multi-tree forest | Query domain tree có suffix khác | Phải chọn đúng naming context để bao phủ tree đó |
| Ghi thuộc domain con | Dùng domain DC của child trên 636 | Thao tác chịu schema/ACL của child domain |
| Replication lag | Ghi rồi kiểm tra ngay trên DC và GC | Có thể quan sát chênh tạm thời; không kết luận lỗi ghi chỉ từ GC |
| Đọc membership | So sánh truy vấn GC và domain DC | Hiểu giới hạn group scope/lồng nhau và quyền hiệu lực |
| TLS | Dùng certificate CA không trust hoặc SAN sai | Kết nối 636/3269 thất bại an toàn |
| Wrong GC endpoint | Gọi 3269 trên server không có GC | Lỗi kết nối/cấu hình được ghi nhận và xử lý |
| Referral | Query ngoài naming context trên domain LDAP | Ứng dụng xử lý referral theo chính sách, không kết nối endpoint không được phép |
| Password/ACL | Sử dụng tài khoản sai mật khẩu hoặc quyền | Phân biệt lỗi bind và lỗi authorization |

Trong Java test, dùng **Spring LDAP ContextSource thật** và **LdapTemplate** để phát sinh request. Mock repository đơn thuần không thể kiểm chứng PAS, replication, GC port, hostname verification hay LDAP referral. Kết quả test cần kèm **endpoint đã dùng, DN base, filter, thuộc tính yêu cầu, thời điểm và domain**; không ghi password hoặc dữ liệu nhạy cảm.

### 12.1. Quy trình kiểm thử nhỏ có thể lặp lại

1. Xác nhận DNS/SRV và RootDSE của GC, domain DC.
2. Tạo hoặc seed một người dùng ở root domain và một người ở child domain; ghi lại DN đầy đủ.
3. Truy vấn hai người qua **GC 3269** với thuộc tính nằm trong PAS.
4. Truy vấn người ở child domain qua **child DC 636** để lấy thuộc tính bổ sung.
5. So sánh kết quả, đặc biệt với thuộc tính custom và thời điểm vừa cập nhật.
6. Thử sai SAN/CA ở môi trường test để chắc chắn client không bỏ qua TLS validation.
7. Kiểm tra mã ứng dụng không ghi qua GC, không tùy ý follow referral, và có timeout/giới hạn kết quả.

Chỉ dùng directory thử nghiệm được cấp phép; những thay đổi trên schema/PAS và quyền AD có thể tác động rộng tới forest, nên không thực hiện trong bài tập trên production.

## 13. Các hiểu nhầm phổ biến

**“Port 3269 là LDAP version mới hơn 636.”** Sai. Cả hai dùng LDAP qua TLS; **3269** hướng đến **Global Catalog**, còn **636** hướng đến LDAP thông thường trên domain controller.

**“GC chứa đầy đủ mọi thuộc tính của mọi domain.”** Sai. GC chứa bản sao đầy đủ của domain mình và bản sao một phần của các domain khác theo **PAS**.

**“Chọn GC luôn tìm được mọi người dùng toàn forest chỉ với một base.”** Sai. Base DN, domain tree, filter, PAS và replication vẫn quyết định kết quả.

**“Đọc được người dùng ở domain khác qua GC thì cũng có thể ghi bằng GC.”** Sai về cách thiết kế ứng dụng. Thao tác ghi phải nhắm tới domain DC có quyền và dữ liệu đầy đủ.

**“Port 3268 luôn bảo mật vì thuộc Active Directory.”** Sai. Cổng 3268 là GC LDAP thông thường; nếu kết nối cần TLS, hãy dùng cơ chế TLS phù hợp, thường là **3269**, và xác minh chứng chỉ/hostname.

**“@Entry hay repository của Spring Data LDAP tự phát hiện cần đổi sang GC.”** Sai. Repository sử dụng **ContextSource** mà ứng dụng cấu hình; kiểu truy vấn và dữ liệu trả về phụ thuộc endpoint đó.

**“Không có thuộc tính trong kết quả GC nghĩa là thuộc tính đã bị xóa.”** Không thể kết luận như vậy nếu chưa kiểm tra PAS, ACL, replication và DC gốc.

## 14. Tổng kết và bài tập tự luyện

Chọn **LDAP 389/636** hay **Global Catalog 3268/3269** dựa trên **mục tiêu truy cập và phạm vi dữ liệu**, không chỉ dựa trên số cổng. Trong môi trường thực tế, **636** phù hợp để đọc/ghi vào domain DC qua TLS, còn **3269** phù hợp cho nhiều nhu cầu tra cứu forest-wide qua TLS. GC lưu bản sao một phần từ những domain khác nên không bảo đảm mọi thuộc tính hoặc mọi quan hệ quyền đều sẵn có. Spring Data LDAP và LdapTemplate sử dụng dữ liệu mà endpoint cung cấp, vì vậy ứng dụng cần cấu hình **ContextSource, base DN, filter, PAS, TLS, ACL** chính xác.

**Bài tập:**

1. Vẽ sơ đồ một forest có root domain và hai child domain. Đánh dấu DC có GC và DC không có GC; điền các cổng **389, 636, 3268, 3269**.
2. Một người dùng thuộc child domain không xuất hiện khi truy vấn DC của root domain. Hãy nêu các bước xác minh và cách GC có thể giúp tìm người đó.
3. Dùng RootDSE lấy **schemaNamingContext**, kiểm tra cờ **isMemberOfPartialAttributeSet** của một thuộc tính custom. Giải thích tác động khi thuộc tính không có trong PAS.
4. Xây dựng một service Spring LDAP dùng **gcTemplate** để tìm UPN rồi **domainTemplate** để đọc đầy đủ hồ sơ. Bảo đảm định tuyến theo domain và không lấy server URL từ input người dùng.
5. Sau khi đổi **displayName** trên domain DC, GC trả giá trị cũ. Trình bày cách kiểm chứng replication và cách đáp ứng yêu cầu read-your-writes.
6. Vì sao chỉ đọc **memberOf** trên GC có thể chưa đủ cho quyết định ủy quyền? Cần xác minh thêm những nguồn/nhóm nào?
7. Giải thích sự khác nhau giữa **GC 3268**, **GC 3269** và **LDAP 636**, đặc biệt trong tình huống bind có mật khẩu.

### Tài liệu tham khảo

- [Microsoft Learn — Global Catalog](https://learn.microsoft.com/en-us/windows/win32/ad/global-catalog) — mục đích và dữ liệu của Global Catalog trong AD DS.
- [Microsoft Learn — Searching in the Global Catalog](https://learn.microsoft.com/en-us/windows/win32/ad/searching-in-the-global-catalog) — tìm kiếm trên GC.
- [Microsoft Learn — Active Directory Domain Services](https://learn.microsoft.com/en-us/windows/win32/ad/active-directory-domain-services) — tài liệu nền tảng về tổ chức và dịch vụ AD DS.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — ContextSource, LdapTemplate, truy vấn LDAP và kết nối TLS.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — repository và ánh xạ LDAP entry sang Java.
