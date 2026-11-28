# Cấu hình nhiều URL và kiểm tra hành vi chuyển máy chủ

Một ứng dụng Spring Boot dùng **Spring Data LDAP** để đọc hồ sơ người dùng, tìm nhóm và đôi khi cập nhật entry trong dịch vụ thư mục. Nếu ứng dụng chỉ cấu hình `ldaps://ldap-a.example.org:636` mà máy chủ đó ngừng hoạt động, các truy vấn qua `LdapRepository` và `LdapTemplate` có thể thất bại dù tổ chức vẫn còn một LDAP server khác đang chạy. Cấu hình **nhiều URL LDAP** giúp ứng dụng có thêm endpoint để thử khi thiết lập kết nối. Tuy nhiên, cần hiểu chính xác khi nào quá trình chuyển máy chủ có thể xảy ra, những trường hợp không được bảo đảm tự động khôi phục và cách kiểm thử bằng lỗi thực tế.

Bài **Kết nối** này tập trung vào `spring.ldap.urls`, cách `LdapContextSource`/JNDI xử lý danh sách endpoint, điều kiện để máy chủ dự phòng dùng được, giới hạn chuyển đổi khi mất kết nối đang hoạt động, cùng chiến lược timeout, TLS, retry, quan sát và kiểm thử. Các ví dụ nằm trong phạm vi **Spring Data LDAP**: repository và `LdapTemplate` dùng cùng kết nối để truy vấn entry phân cấp, ánh xạ thuộc tính theo `objectClass`/schema, thực hiện CRUD và filter an toàn.

## 1. Mục tiêu

Sau bài học, bạn có thể:

1. Cấu hình nhiều URL LDAP trong Spring Boot, giữ riêng URL, base DN và tài khoản bind.
2. Giải thích sự khác nhau giữa **chọn endpoint khi tạo context**, **khôi phục sau lỗi đang đọc/ghi**, **load balancing** và **failover do hạ tầng cung cấp**.
3. Xác minh hai LDAP server có cùng dữ liệu, schema, quyền đọc và trạng thái replication phù hợp.
4. Thiết lập timeout kết nối/đọc để việc thử endpoint dự phòng không bị treo quá lâu.
5. Kiểm thử các tình huống mất kết nối, server dự phòng không đồng bộ, chứng chỉ TLS lỗi, bind thất bại và ghi dữ liệu bị gián đoạn.
6. Xây chiến lược retry giới hạn, chú ý **idempotency** và tính nhất quán của các thao tác LDAP.

## 2. Sơ đồ một ứng dụng và hai LDAP endpoint

Ví dụ tổ chức triển khai hai máy chủ cùng phục vụ một không gian thư mục:

~~~text
                      Spring Boot
             +---------------------------+
             | PersonRepository          |
             | LdapTemplate              |
             |         |                 |
             |   LdapContextSource       |
             +---------+-----------------+
                       |
              LDAP URL list
                       |
          +------------+------------+
          |                         |
          v                         v
 ldaps://ldap-a.example.org:636   ldaps://ldap-b.example.org:636
          |                         |
          +------ directory --------+
                   replicas
           dc=example,dc=org
                ou=people
                ou=groups
~~~

Danh sách URL chỉ định **các đích có thể thử**. Nó không tự tạo replication giữa hai server, không làm các server chia sẻ transaction, không kiểm tra rằng dữ liệu là giống nhau và không bảo đảm yêu cầu LDAP đang chạy trên A sẽ được thực hiện lại trên B.

Để chuyển sang B mà vẫn đúng nghiệp vụ, B phải phục vụ **cùng base DN hoặc quy tắc định danh tương đương**, nhận cùng thông tin bind, có schema/ACL phù hợp và chứa dữ liệu đủ mới đối với chức năng ứng dụng.

### Bốn khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Có được bảo đảm chỉ nhờ nhiều URL? |
| --- | --- | --- |
| **Kết nối mới thử URL khác** | Khi tạo một LDAP context mới, provider có thể thử endpoint còn lại nếu endpoint trước không dùng được. | Có thể được hỗ trợ bởi JNDI/provider, cần kiểm thử trên stack thực tế. |
| **Failover khi request đang chạy** | Một truy vấn/ghi đã gửi sang A tự tiếp tục trên B khi A mất kết nối. | **Không** mặc định được bảo đảm. |
| **Load balancing** | Phân phối tải giữa nhiều server theo chính sách round robin, sức khỏe hoặc tải. | **Không** suy ra từ danh sách URL. |
| **Replication/nhất quán dữ liệu** | Server B có cùng entry, schema và trạng thái cập nhật như server A. | **Không**; do directory/hạ tầng quản lý. |

## 3. Cấu hình nhiều URL bằng `application.yml`

Với Spring Boot dùng Spring Data LDAP starter:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Khai báo danh sách URL:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap-a.example.org:636
      - ldaps://ldap-b.example.org:636
    base: dc=example,dc=org
    username: cn=app-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Hoặc cấu hình URL qua biến môi trường dành riêng cho từng endpoint:

~~~yaml
spring:
  ldap:
    urls:
      - ${LDAP_PRIMARY_URL:ldaps://ldap-a.example.org:636}
      - ${LDAP_SECONDARY_URL:ldaps://ldap-b.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Các giá trị trên đều là **ví dụ**. Chúng chỉ hoạt động khi có server, nhánh directory, tài khoản bind và secret tương ứng. Không ghi mật khẩu thật vào file nguồn.

| Thuộc tính | Vai trò | Lỗi thường gặp |
| --- | --- | --- |
| `spring.ldap.urls` | Danh sách endpoint LDAP có thứ tự. | Nhầm cổng hoặc trộn endpoint của hai directory không tương đương. |
| `spring.ldap.base` | Gốc các DN tương đối khi Spring LDAP tìm kiếm/thao tác. | A dùng gốc đúng, B không phục vụ gốc đó. |
| `spring.ldap.username` | Danh tính tài khoản dịch vụ để bind. | DN chỉ tồn tại trên A, hoặc B chưa đồng bộ account. |
| `spring.ldap.password` | Credential của tài khoản bind. | Secret chưa cập nhật đồng đều giữa các server. |

Trong `application.properties`, có thể thể hiện danh sách theo chỉ số để rõ thứ tự:

~~~properties
spring.ldap.urls[0]=ldaps://ldap-a.example.org:636
spring.ldap.urls[1]=ldaps://ldap-b.example.org:636
spring.ldap.base=dc=example,dc=org
spring.ldap.username=cn=app-reader,ou=services,dc=example,dc=org
spring.ldap.password=${LDAP_BIND_PASSWORD}
~~~

**Lưu ý cấu hình:** một danh sách URL trong Spring Boot thường được truyền vào `LdapContextSource`. Khi làm việc qua Java Naming and Directory Interface (**JNDI**) của JVM, các provider URL có thể được biểu diễn thành danh sách trong thuộc tính môi trường `java.naming.provider.url`. Chi tiết thứ tự thử, mở kết nối và tái sử dụng kết nối phụ thuộc provider, phiên bản và cách cấu hình context; kiểm thử hành vi thực tế là bước bắt buộc.

## 4. Chuyển máy chủ xảy ra tại thời điểm nào?

### 4.1. Thử endpoint khác khi tạo context

Luồng minh họa của một provider hỗ trợ danh sách URL:

~~~mermaid
flowchart TD
    A["Ứng dụng cần LDAP context mới"] --> B["Thử endpoint A"]
    B --> C{"Tạo kết nối / context thành công?"}
    C -- "Có" --> D["Thực hiện bind và thao tác với A"]
    C -- "Không, lỗi thuộc loại có thể thử URL kế tiếp" --> E["Thử endpoint B"]
    E --> F{"Tạo context thành công?"}
    F -- "Có" --> G["Thực hiện thao tác với B"]
    F -- "Không" --> H["Báo lỗi cho ứng dụng"]
    C -- "Lỗi không thuộc loại chuyển tiếp" --> H
~~~

Đây là **mô hình để suy nghĩ và kiểm thử**, không phải cam kết rằng mọi lỗi JNDI đều được chuyển tiếp sang URL kế tiếp. Một số lỗi, chẳng hạn credential không hợp lệ, chứng chỉ TLS không tin cậy hoặc lỗi dữ liệu, cần được coi là lỗi cấu hình/xác thực và **không được mặc nhiên giả định sẽ chuyển máy chủ**.

Đối với một số JNDI LDAP service provider, danh sách provider URL được xem xét trong quá trình tạo **initial context**. Nếu context đã kết nối với A, một exception khi thực hiện search hoặc modify **không có nghĩa** framework tự chuyển thao tác đang chạy sang B. Ứng dụng phải quyết định có lấy context mới, thử lại thao tác nào và giới hạn thử lại ra sao.

### 4.2. Một connection đang mở mất giữa chừng

Giả sử:

1. `PersonRepository.findByUid("lan")` đã dùng một LDAP context đang kết nối với A.
2. A ngừng phục vụ ngay trước hoặc trong khi truyền kết quả.
3. Caller nhận lỗi kết nối/đọc.

Trong trường hợp này, danh sách URL **không bảo đảm lệnh search tự được tiếp tục trên B**. Tùy tình trạng context, việc tạo context mới trong lần gọi tiếp theo có thể thử endpoint khác. Không nên quảng bá “zero downtime” chỉ bằng cấu hình `spring.ldap.urls`.

Đối với đọc, retry có kiểm soát thường dễ lập luận hơn nếu kết quả không gây side effect. Đối với ghi, có thể server A đã áp dụng thay đổi nhưng phản hồi thất lạc; tự động thử lại trên B có thể gây lỗi trùng entry hoặc thao tác ghi lặp.

### 4.3. Chuyển hướng không đồng nghĩa chia tải

Khi mọi URL đều khả dụng, provider có thể ưu tiên endpoint nhất định theo hành vi triển khai; đừng kết luận các yêu cầu sẽ chia đều 50/50. Muốn chia tải và quản lý sức khỏe endpoint một cách có chủ ý, cân nhắc dịch vụ LDAP VIP/load balancer hoặc lớp routing do hạ tầng quản lý và **kiểm thử chính sách thật**.

### 4.4. Đổi DNS hoặc cấu hình URL khi ứng dụng đang chạy

DNS failover, load balancer và danh sách URL cấp ứng dụng có những chu kỳ cache/tái kết nối khác nhau. Thay đổi địa chỉ DNS hoặc giá trị biến môi trường không tự bảo đảm một context đang sống chuyển đích ngay; cấu hình Spring Boot thông thường cũng không tự nạp lại mọi thuộc tính môi trường nếu không có cơ chế refresh được thiết kế riêng.

## 5. Những điều kiện để máy chủ B thực sự thay thế được A

Một endpoint “trả lời cổng 636” chưa chắc đủ điều kiện làm server dự phòng.

### 5.1. Cùng namespace và dữ liệu thiết yếu

Nếu A có entry:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
~~~

thì B phải phục vụ nhánh tương ứng và có dữ liệu phù hợp cho nhu cầu của ứng dụng. Nếu dữ liệu được replication bất đồng bộ, B có thể chưa nhận bản cập nhật mới nhất. Ứng dụng có thể tìm được `uid=lan` trên A nhưng nhận danh sách rỗng trên B ngay sau khi vừa tạo entry; điều này là vấn đề **độ trễ replica**, không nhất thiết do filter hay mapper.

### 5.2. Cùng schema và cách ánh xạ

Với entity Spring Data LDAP:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    public String getUid() { return uid; }
    public String getCommonName() { return commonName; }
}
~~~

Ứng dụng sẽ thất bại hoặc ánh xạ sai nếu B không có cùng `objectClass`/attribute cần thiết, hoặc ACL khiến các trường quan trọng không được trả về. Nếu A là OpenLDAP còn B là Active Directory không được thiết kế chung namespace/schema, việc liệt kê cả hai URL **không biến chúng thành replica tương đương**.

### 5.3. Cùng khả năng bind và ACL

Tài khoản `cn=app-reader,ou=services,dc=example,dc=org` phải có thể bind và đọc đúng nhánh trên cả A lẫn B. Trong một cụm có replication, các thay đổi mật khẩu, khóa tài khoản, ACL và nhóm có thể có độ trễ. Không sử dụng bind ẩn danh làm phương án thay thế khi bind bằng tài khoản dịch vụ lỗi.

### 5.4. Đọc và ghi có thể có chính sách khác nhau

Hệ thống directory có thể tổ chức replica chỉ đọc hoặc chính sách ghi chỉ qua một máy chủ/đầu mối nhất định. Trong trường hợp đó, liệt kê endpoint read-only làm URL dự phòng cho **CRUD** có thể khiến thao tác `save(...)` hoặc `delete(...)` thất bại dù `findByUid(...)` vẫn hoạt động.

Nếu ứng dụng có ghi LDAP, phải xác nhận topology cho phép cập nhật trên endpoint nào, cách replication hoạt động, các ràng buộc schema/ACL và chính sách giải quyết xung đột. Không suy ra có thể ghi vào B chỉ từ việc tìm kiếm thành công.

## 6. Timeout kết nối và timeout đọc

Khi A không phản hồi nhưng cổng không đóng ngay, quá trình thử kết nối có thể chờ lâu. Một chiến lược chuyển endpoint có ích khi ứng dụng đặt timeout hợp lý và hiểu tổng thời gian chờ.

Với JNDI LDAP provider của JVM hỗ trợ các thuộc tính sau, có thể truyền chúng qua `spring.ldap.base-environment`:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap-a.example.org:636
      - ldaps://ldap-b.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
    base-environment:
      com.sun.jndi.ldap.connect.timeout: "3000"
      com.sun.jndi.ldap.read.timeout: "5000"
~~~

Các giá trị **3000 ms** và **5000 ms** là ví dụ để thực hành, không phải thời hạn mặc định hay khuyến nghị phù hợp mọi môi trường. Đo độ trễ mạng, thời gian xử lý của directory và mức chịu lỗi của ứng dụng trước khi chọn giá trị.

| Thuộc tính JNDI | Mục đích | Điều cần chú ý |
| --- | --- | --- |
| `com.sun.jndi.ldap.connect.timeout` | Giới hạn thời gian chờ thiết lập kết nối theo hành vi provider hỗ trợ. | Không phải timeout cho toàn bộ HTTP request hay cả chuỗi URL. |
| `com.sun.jndi.ldap.read.timeout` | Giới hạn thời gian chờ phản hồi thao tác LDAP theo provider. | Không tự bảo đảm request được retry trên server khác. |
| `spring.ldap.base-environment` | Đưa map thuộc tính môi trường bổ sung vào context. | Tác dụng cụ thể phụ thuộc JNDI/provider được sử dụng. |

Với hai endpoint, thời gian chờ tích lũy có thể lớn hơn timeout của một endpoint. Một số thao tác như DNS resolution, TLS handshake, bind, retry hoặc các lớp proxy có thời gian chờ riêng; hãy kiểm thử **độ trễ quan sát được**, không tính đơn giản `3 s + 5 s` rồi coi đó là SLA.

Không đặt timeout quá ngắn khiến mạng có độ trễ tự nhiên bị xem là lỗi; cũng không để timeout vô hạn làm worker thread và pool kết nối bị giữ mãi. Ứng dụng HTTP nên có **ngân sách thời gian tổng** và chiến lược trả lỗi rõ ràng khi directory không đáp ứng.

## 7. TLS và an toàn khi chuyển endpoint

Các máy chủ dự phòng phải được cấu hình bảo mật tương đương:

- **LDAPS:** mỗi URL `ldaps://host:636` thiết lập TLS từ đầu; chứng chỉ của A và B phải hợp lệ đối với hostname tương ứng và chuỗi chứng chỉ phải được JVM tin cậy.
- **StartTLS:** dùng `ldap://` rồi nâng cấp TLS theo cấu hình cụ thể; việc liệt kê nhiều `ldap://` URL không tự bật StartTLS. Cần bảo đảm chiến lược StartTLS được áp dụng cho **mọi context mới**, gồm kết nối sang B.
- **Xác minh chứng chỉ:** không tắt hostname verification hoặc tin cậy mọi chứng chỉ để “sửa” lỗi chuyển máy chủ. Cấu hình CA/truststore hoặc SSL bundle đúng cho môi trường.
- **Tài khoản dịch vụ:** credential có thể được gửi đến bất kỳ endpoint nào được cấu hình; chỉ thêm những máy chủ thuộc miền quản trị tin cậy và cùng chính sách xác thực.
- **Filter và DN:** chuyển sang B không làm filter đã nối chuỗi trở nên an toàn. Dùng `LdapQueryBuilder` để escape giá trị filter và API như `LdapNameBuilder` để xây DN từ đầu vào động.

Ví dụ, A có chứng chỉ hợp lệ nhưng B dùng chứng chỉ tự ký chưa được tin cậy. Lúc A ngừng phục vụ, ứng dụng có thể nhận `SSLHandshakeException` khi thử B. Đây là lỗi **TLS của endpoint dự phòng**, không phải bằng chứng framework không hỗ trợ URL list.

## 8. Truy vấn repository và `LdapTemplate` sau khi cấu hình

Khai báo repository:

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    Optional<PersonEntry> findByUid(String uid);
}
~~~

Service truy vấn bằng `LdapTemplate`, dùng filter builder:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryLookupService {
    private final LdapTemplate ldapTemplate;

    public DirectoryLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNames(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("cn")
                .where("uid").is(uid);

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>) attributes ->
                    String.valueOf(attributes.get("cn").get())
        );
    }
}
~~~

Với `spring.ldap.base=dc=example,dc=org`, base tương đối `ou=people` tìm dưới `ou=people,dc=example,dc=org`. Khi B thay A, repository và template vẫn sử dụng base DN và filter này; B cần phục vụ cùng dữ liệu và schema tương ứng. Trong ví dụ, mapper giả định `cn` có mặt và được ACL cho đọc; code production phải xử lý thiếu thuộc tính phù hợp.

**Phân định trách nhiệm:** `DirectoryLookupService` gọi `LdapTemplate`; việc chọn endpoint là trách nhiệm cấu hình context và provider. Không cần viết hai `PersonRepository` rồi tự chọn repository theo URL trong mỗi phương thức chỉ để bật danh sách nhiều URL. Nếu ứng dụng có yêu cầu routing cụ thể theo read/write hoặc vùng địa lý, có thể thiết kế nhiều `ContextSource` riêng, nhưng đó là **kiến trúc tùy biến khác** và cần kiểm thử riêng.

## 9. Cách kiểm tra từng server trước khi thử failover

Trước khi cấu hình cả hai URL cùng lúc, hãy truy cập **từng endpoint độc lập** bằng một công cụ LDAP. Với OpenLDAP command-line client:

~~~bash
# Endpoint A: kiểm tra bind và entry gốc.
ldapsearch -LLL -x \
  -H "ldaps://ldap-a.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "dc=example,dc=org" -s base \
  "(objectClass=*)" dn

# Endpoint B: kiểm tra cùng base DN và tài khoản.
ldapsearch -LLL -x \
  -H "ldaps://ldap-b.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "dc=example,dc=org" -s base \
  "(objectClass=*)" dn
~~~

`-W` hỏi mật khẩu qua prompt, tránh đặt mật khẩu trực tiếp vào tham số lệnh. Sau đó kiểm tra **cùng filter** và **cùng attribute** ở hai nơi:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap-a.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(uid=lan)" dn uid cn mail

ldapsearch -LLL -x \
  -H "ldaps://ldap-b.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(uid=lan)" dn uid cn mail
~~~

Đối chiếu DN và các thuộc tính quan trọng. Nếu B chưa có entry mới được tạo trên A, ghi nhận **replication lag** trước khi thử tình huống sự cố. Hai lệnh đơn lẻ chứng minh endpoint có thể đọc dữ liệu, **không tự chứng minh cơ chế failover của ứng dụng Java**. `ldapsearch` có thể dùng thư viện TLS và chính sách tin cậy khác với JVM; việc công cụ này chạy thành công chưa bảo đảm Java tin cậy chứng chỉ của cả hai endpoint.

## 10. Kiểm thử hành vi chuyển máy chủ thực tế

Thực hiện trên **directory thử nghiệm hoặc môi trường được phép tạo sự cố**, với hai endpoint hoạt động và có entry canary `uid=lan` trên cả hai. Dùng tài khoản dịch vụ chỉ đọc cho các test search.

### 10.1. Chuẩn bị

1. Xác minh A và B bind được bằng cùng tài khoản; schema/ACL và dữ liệu canary tương đương.
2. Chạy ứng dụng Spring Boot với URL list A trước, B sau và timeout đã cấu hình.
3. Cung cấp một thao tác gọi `findByUid("lan")` hoặc `findNames("lan")`, ghi nhận kết quả, lỗi và thời gian phản hồi.
4. Theo dõi log phía LDAP server, proxy/load balancer hoặc mạng để biết ứng dụng **thực sự kết nối máy nào**. Spring Data LDAP không cung cấp một cam kết chung rằng mọi kết quả repository đều có nhãn hostname endpoint đã phục vụ.

### 10.2. Ma trận kiểm thử

| Kịch bản | Cách tiến hành an toàn | Điều cần xác minh |
| --- | --- | --- |
| **Cả A và B hoạt động** | Gọi truy vấn canary nhiều lần từ ứng dụng. | Kết quả đúng; ghi nhận endpoint thực sự, không giả định chia tải đều. |
| **A không khả dụng trước khi tạo context mới** | Chặn A ở mạng thử nghiệm hoặc dừng A trước khi khởi tạo kết nối mới. | Ứng dụng có thử B và đọc được canary không? Tổng thời gian chờ là bao nhiêu? |
| **A mất khi đã có context/đang search** | Thiết lập kết nối, sau đó ngắt A trong lúc gọi search. | Lời gọi hiện tại nhận lỗi hay phục hồi? Request kế tiếp có tạo context mới và chuyển sang B được không? |
| **B cũng không khả dụng** | Dừng hoặc chặn cả hai endpoint. | Lỗi trả về đúng, không treo vô hạn; ứng dụng không báo giả là entry không tồn tại. |
| **B thiếu entry/replication chậm** | Cho B chậm đồng bộ dữ liệu canary trong môi trường test. | Ứng dụng nhận biết dữ liệu cũ/không thấy entry, không tự tạo bản sao hay xóa dữ liệu nghiệp vụ vì kết quả rỗng. |
| **B có chứng chỉ không được tin cậy** | Dùng chứng chỉ test chưa có trong truststore JVM. | Báo lỗi TLS rõ ràng; không âm thầm tắt xác minh TLS. |
| **B từ chối bind/thiếu ACL** | Chỉnh ACL hoặc credential trên B trong môi trường test. | Lỗi xác thực/quyền được phân biệt với server down; không giả định fallback qua mọi lỗi. |
| **B chỉ đọc, A cho phép ghi** | Thực hiện thay đổi trên entry test có quyền và backup. | Read thành công nhưng write có thể bị từ chối; chính sách routing ghi được xác minh. |
| **Đổi thứ tự URL** | Cấu hình B trước A, khởi tạo kết nối mới. | Xác minh cách provider thật xử lý thứ tự; kết luận dựa trên quan sát. |

**Bài kiểm thử chỉ đạt yêu cầu khi có bằng chứng endpoint thực sự được sử dụng.** Chỉ thấy kết quả search thành công khi A bị dừng chưa đủ nếu ứng dụng đang dùng cache, load balancer hoặc kết nối còn mở tới A theo cách nào đó. Trong trường hợp không có quyền đọc log server, dùng packet capture/quan sát proxy được phép trên hệ thống test.

### 10.3. Chú ý “kết nối mới”

Nếu muốn thử **failover lúc tạo context**, hãy bảo đảm request thực sự cần tạo context mới: kiểm tra pool, đóng các context test thích hợp hoặc khởi động lại ứng dụng thử nghiệm sau khi dừng A. Nếu không, ứng dụng có thể tiếp tục dùng context cũ hoặc kết nối qua proxy, khiến kết luận về cơ chế fallback bị sai.

Với **JNDI connection pooling** hoặc pool khác, kết nối được tái sử dụng có thể vẫn trỏ tới endpoint cũ; kiểm tra tính phù hợp của pool, việc loại bỏ connection lỗi và cơ chế TLS/StartTLS. Pooling **không đồng nghĩa** với kiểm tra sức khỏe hoặc tự chuyển mọi kết nối lỗi sang endpoint khác.

## 11. Xử lý lỗi đúng ở tầng ứng dụng

Khi một request LDAP lỗi, trước hết cần phân loại:

| Loại lỗi | Ví dụ | Hành động ưu tiên |
| --- | --- | --- |
| **Kết nối/timeout** | A không nghe cổng, socket bị reset, vượt read timeout. | Đánh dấu lỗi hệ thống, cân nhắc thử lại bounded trên context mới cho thao tác phù hợp. |
| **TLS** | Chứng chỉ sai hostname, CA chưa được tin cậy. | Sửa truststore/chứng chỉ và cấu hình endpoint; không hạ mức bảo mật. |
| **Xác thực** | LDAP result code `49` – invalid credentials. | Kiểm tra bind DN, secret, trạng thái tài khoản, sự nhất quán giữa server. |
| **Quyền** | LDAP result code `50` – insufficient access rights. | Kiểm tra ACL của danh tính bind và loại thao tác. |
| **DN/schema/filter** | Code `32` noSuchObject, schema violation, filter sai. | Kiểm tra base DN, schema `objectClass`, tên attribute, filter và dữ liệu đầu vào. |
| **Dữ liệu chưa đồng bộ** | Entry có trên A nhưng chưa có trên B. | Kiểm tra replication và tính nhất quán; không quy lỗi thành “user bị xóa”. |

### Khi nào nên retry?

Với **tìm kiếm chỉ đọc**, có thể thiết kế retry giới hạn cho các lỗi kết nối tạm thời, chẳng hạn thử tối đa một hoặc hai lần với delay ngắn và jitter, trong một **time budget tổng**. Phải tạo cơ hội sử dụng context mới theo cách thư viện quản lý, đồng thời có giới hạn tránh làm sự cố nghiêm trọng hơn.

Với **CRUD/ghi**, không tự động retry tất cả các lệnh. Ví dụ, `ldapTemplate.bind(...)` tạo entry: A có thể đã tạo thành công nhưng phản hồi bị mất. Nếu retry trên B trước khi replication hoàn tất, hệ thống có thể tạo trùng hoặc gặp `entryAlreadyExists`. `modify` nhiều thuộc tính và `delete` cũng có những tình huống kết quả không chắc chắn.

Trước khi retry ghi, cần thiết kế **idempotency, kiểm tra trạng thái theo DN hoặc stable ID, quy trình đối soát và thứ tự replication**. Nếu không chứng minh được thao tác có thể lặp lại an toàn, trả lỗi có thể xử lý và đối soát thay vì thực hiện lại mù quáng.

### Khi không nên retry?

Đừng retry liên tục khi credential sai, thiếu ACL, schema không hợp lệ hoặc filter sai. Chuyển endpoint cũng không giải quyết nguyên nhân dữ liệu đầu vào không hợp lệ. Cần giữ riêng **lỗi hệ thống** và **“không tìm thấy entry”**: search trả danh sách rỗng là một kết quả, còn exception timeout là lỗi chưa có kết luận về entry.

## 12. Kết nối nhiều URL trong hệ thống lớn

### 12.1. Danh sách URL và load balancer

Có hai cách phổ biến:

~~~text
Phương án A: nhiều URL ứng dụng
Spring -> ldap-a, ldap-b (danh sách trong ContextSource)

Phương án B: một endpoint logic
Spring -> ldaps://directory.example.org:636 -> LB/VIP -> ldap-a, ldap-b
~~~

Với phương án B, hạ tầng cân bằng tải chịu trách nhiệm kiểm tra sức khỏe và chọn backend, nhưng phải bảo toàn TLS, chính sách bind, thời gian chờ và hỗ trợ LDAP/LDAPS đúng cách. Khả năng chuyển backend của một kết nối đang hoạt động vẫn cần xác minh; TCP connection bị ngắt không có nghĩa LDAP operation có thể tự tiếp tục trên backend khác.

Có thể kết hợp nhiều VIP ở các vùng dự phòng nếu cần, nhưng độ phức tạp và nguy cơ đọc replica chậm sẽ tăng. Thiết kế cụ thể phụ thuộc SLO, topology replication và quy tắc ghi.

### 12.2. Giao thức và vấn đề consistency

Hai server có thể đạt **availability** tốt hơn nhưng tạo ra **độ trễ dữ liệu**. Ví dụ vừa đổi nhóm của user trên A mà B chưa nhận cập nhật; truy vấn qua B có thể trả membership cũ. Nếu group LDAP được dùng để đưa ra quyết định phân quyền, đây là rủi ro cần thiết kế rõ: độ trễ chấp nhận được, thời điểm quyền bị thu hồi, cơ chế xác thực nguồn có thẩm quyền và thời gian cache.

Đối với một số nghiệp vụ như vô hiệu hóa tài khoản ngay lập tức hoặc kiểm tra quyền nhạy cảm, đọc replica không đồng bộ có thể không đáp ứng yêu cầu. Khi đó cần tuyến đọc có tính nhất quán mạnh hơn hoặc kiểm tra trực tiếp với nguồn có thẩm quyền tùy khả năng directory.

### 12.3. Đo đạc và quan sát

Nên ghi nhận:

- Số lượng truy vấn LDAP thành công/thất bại theo loại thao tác (search, bind, modify).
- Thời gian mở kết nối, thời gian phản hồi search, tỉ lệ timeout và số lần retry.
- Tỉ lệ lỗi TLS, lỗi bind, lỗi ACL và lỗi schema.
- Độ trễ replication/độ mới của entry canary được phép sử dụng.
- Khả năng phục hồi sau khi một endpoint không khả dụng, dựa trên log/proxy/server có thể kiểm chứng.

Không ghi mật khẩu, DN nhạy cảm hoặc toàn bộ attribute cá nhân vào log. Khi theo dõi kết nối ở nhiều server, bảo đảm metric chỉ hiển thị những endpoint mà ứng dụng thật sự sử dụng; không suy ra URL đã chọn từ thứ tự cấu hình.

## 13. Bài tập thực hành

Một ứng dụng quản lý nhân sự có:

~~~text
URL 1: ldaps://ldap-hcm.example.org:636
URL 2: ldaps://ldap-hn.example.org:636
Base:  dc=company,dc=internal
Bind:  cn=hr-reader,ou=services,dc=company,dc=internal
Data:  ou=employees,dc=company,dc=internal
~~~

Hai server đồng bộ bất đồng bộ và tài khoản `hr-reader` chỉ có quyền đọc.

**Yêu cầu:**

1. Viết `application.yml` khai báo hai URL theo thứ tự HCM trước Hà Nội, cấu hình base DN, tài khoản bind và mật khẩu lấy từ biến môi trường.
2. Cấu hình timeout kết nối 2.000 ms và timeout đọc 4.000 ms bằng JNDI base environment, giải thích vì sao chúng không phải tổng thời gian chờ của toàn request.
3. Trình bày cách kiểm tra `uid=mai` với cùng base/filter trên từng endpoint trước khi cho ứng dụng sử dụng chung danh sách URL.
4. Dừng server HCM **trước khi tạo context mới** trong môi trường thử nghiệm. Nêu kết quả kỳ vọng, bằng chứng cần thu thập và lý do không kết luận chỉ dựa vào phản hồi thành công.
5. Đang thực hiện `modify` trên HCM thì mạng bị ngắt. Vì sao không nên lập tức thực hiện lại lệnh trên Hà Nội?
6. Nếu server Hà Nội trả dữ liệu nhóm quyền cũ, bạn cần điều chỉnh điều gì trước khi dùng kết quả cho phân quyền nhạy cảm?
7. Phân biệt ba lỗi: bind credential sai, TLS certificate B không được JVM tin cậy, và A ngừng phục vụ. Lỗi nào không thể khắc phục bằng filter repository?

**Gợi ý đáp án:**

- Sử dụng `spring.ldap.urls` dạng danh sách, `spring.ldap.base`, `username` và `password: ${LDAP_BIND_PASSWORD}`. Trong `base-environment` đặt `com.sun.jndi.ldap.connect.timeout: "2000"` và `com.sun.jndi.ldap.read.timeout: "4000"`.
- Gọi `ldapsearch` riêng ở HCM và Hà Nội với tài khoản dịch vụ, search base `ou=employees,dc=company,dc=internal`, filter `(uid=mai)`, đối chiếu DN và thuộc tính cần thiết.
- Khi A không sẵn sàng lúc tạo context, một provider hỗ trợ URL list có thể thử B; phải chứng minh B được kết nối qua log server/proxy và đo thời gian chờ. Nếu context đã kết nối A trước đó, không suy ra hành vi tương tự.
- Mất phản hồi sau modify không chứng minh A chưa ghi; retry trên B có nguy cơ cập nhật lặp hoặc xung đột replication. Cần đối soát trạng thái và chính sách idempotency.
- Với quyền nhạy cảm, xác định giới hạn độ trễ replica và truy vấn nguồn có thẩm quyền hoặc cơ chế đảm bảo dữ liệu đủ mới.
- Credential, TLS và lỗi mạng nằm ở lớp kết nối/xác thực; sửa filter trong repository không xử lý được.

## 14. Ghi nhớ

**Nhiều LDAP URL giúp client có lựa chọn khi thiết lập kết nối**, nhưng không tự bảo đảm failover cho thao tác đang chạy, chia tải, replication hay tính nhất quán. Khi dùng Spring Data LDAP, hãy cấu hình `spring.ldap.urls` cùng base DN và tài khoản bind phù hợp; kiểm tra từng endpoint về TLS, schema, ACL và dữ liệu; đo timeout thực tế và thực hiện thử nghiệm có ngắt kết nối trước cũng như trong một request.

Với thao tác đọc, cân nhắc retry có giới hạn khi lỗi hạ tầng tạm thời. Với thao tác ghi, phải xác định có khả năng **đã ghi thành công nhưng mất phản hồi** trước khi quyết định thử lại. Thành công của một triển khai dự phòng được đo bằng hành vi quan sát được khi có sự cố, không chỉ bằng việc file cấu hình chứa hai URL.

### Tài liệu tham khảo

- [Spring Boot Reference — Working with LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Spring Data LDAP Reference Documentation](https://docs.spring.io/spring-data/ldap/reference/)
- [Oracle JNDI — LDAP Service Provider](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap.html)
- [JNDI API — Context.PROVIDER_URL](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/Context.html#PROVIDER_URL)
- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513)
