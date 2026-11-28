# Luân chuyển mật khẩu tài khoản dịch vụ và kiểm tra pool

> **Chương:** Triển khai  
> **Module:** `SPRING_DATA_LDAP` — truy cập directory LDAP từ Spring Data LDAP qua repository, `LdapTemplate` và ánh xạ entry phân cấp sang entity Java.

Một ứng dụng Spring Data LDAP thường sử dụng **tài khoản dịch vụ** (*service account*, hay *bind account*) để kết nối directory, tìm entry, đọc thuộc tính và thực hiện các thao tác được cấp quyền. Mật khẩu tài khoản này cần được **luân chuyển định kỳ hoặc khi có sự cố bảo mật**. Tuy nhiên, cập nhật secret trên hệ thống quản lý bí mật chưa đủ để đảm bảo mọi instance của ứng dụng đang dùng credential mới.

Nguyên nhân là ứng dụng có thể đã khởi tạo `ContextSource` bằng mật khẩu cũ, trong khi **connection pool** còn giữ các `DirContext` đã bind thành công trước thời điểm đổi mật khẩu. Một phép tìm kiếm chạy được trên kết nối cũ có thể tạo cảm giác luân chuyển thành công, nhưng lần kết nối mới lại gặp lỗi `invalidCredentials`. Trường hợp ngược lại cũng xảy ra: credential mới hoạt động, nhưng các context cũ trong pool bị server từ chối hoặc mất kết nối, gây lỗi ngắt quãng.

Bài này hướng dẫn cách lập kế hoạch luân chuyển mật khẩu, kiểm tra tài khoản dịch vụ bằng **fresh bind**, xử lý pool khi chuyển cấu hình, triển khai/rollback an toàn và giám sát hoạt động LDAP. Ví dụ sử dụng Spring Boot, Spring Data LDAP và Spring LDAP; cơ chế cụ thể có thể khác giữa OpenLDAP, Active Directory hoặc directory server khác.

## 1. Phân biệt tài khoản dịch vụ với tài khoản người dùng

Giả sử ứng dụng quản lý nhân sự có cây thư mục:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=binh
├── ou=groups
│   └── cn=developers
└── ou=services
    ├── uid=app-reader-a
    └── uid=app-reader-b
~~~

Hai tài khoản `app-reader-a` và `app-reader-b` có thể được chuẩn bị để chuyển đổi luân phiên. Ví dụ này giả định tổ chức cho phép tạo hai danh tính dịch vụ với phạm vi quyền tương đương.

| Loại danh tính | Mục đích | Credential được sử dụng khi nào? |
|---|---|---|
| **Service/bind account** | Tìm kiếm hoặc CRUD entry theo quyền ứng dụng | Khi `ContextSource` lấy context phục vụ `LdapTemplate`/repository |
| **Người dùng cuối** | Đăng nhập vào ứng dụng qua Spring Security LDAP | Khi xác thực người dùng bằng bind hoặc cơ chế xác thực phù hợp |
| **Tài khoản quản trị directory** | Quản trị schema, ACL, tài khoản hoặc mật khẩu | Trong quy trình vận hành được kiểm soát; không dùng mặc định cho ứng dụng |

**Luân chuyển mật khẩu service account không đồng nghĩa đổi mật khẩu của người dùng cuối.** Nếu ứng dụng sử dụng Spring Security LDAP bind để xác thực người dùng, việc kiểm tra service account chủ yếu bảo đảm **khả năng tìm DN và nhóm**, không xác nhận mọi người dùng có thể đăng nhập. Luồng LDAP bind của user cần được kiểm tra riêng.

Đừng dùng tài khoản quản trị directory làm credential chung cho tất cả repository. Một dịch vụ chỉ tìm người dùng có thể sử dụng tài khoản chỉ đọc, giới hạn ở các OU và thuộc tính cần thiết.

## 2. Vì sao cập nhật secret không tự làm mới kết nối?

Trong một ứng dụng Spring Boot, cấu hình thường được cấp lúc khởi động:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL}
    base: ${LDAP_BASE_DN}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Các giá trị có thể đến từ biến môi trường, secret manager hoặc nền tảng triển khai. `spring.ldap.username` và `spring.ldap.password` là credential cho `ContextSource` do Spring LDAP sử dụng theo cấu hình tương ứng.

Đường đi thông thường:

~~~mermaid
flowchart TD
    A["Secret manager / cấu hình triển khai"] --> B["Environment hoặc nguồn cấu hình của process"]
    B --> C["LdapContextSource giữ bind DN và credential"]
    C --> D["Pool (nếu được cấu hình)"]
    D --> E["DirContext đã bind / kết nối mới"]
    E --> F["LdapTemplate và LdapRepository"]
    F --> G["Directory server kiểm tra quyền và xử lý truy vấn"]
~~~

Những trạng thái cần phân biệt:

- **Secret đã được thay đổi trong secret manager:** nguồn dữ liệu bên ngoài ứng dụng có giá trị mới.
- **Process đã nhận secret mới:** ứng dụng được khởi động lại, được cập nhật qua cơ chế refresh có hỗ trợ hoặc nhận cấu hình mới bằng phương pháp phù hợp.
- **ContextSource sử dụng secret mới:** bean được tạo/cập nhật theo cơ chế thư viện; một biến môi trường thay đổi sau khi JVM khởi động không tự cập nhật bean cũ.
- **Kết nối mới bind thành công:** server chấp nhận **DN + mật khẩu mới** ở phiên LDAP mới.
- **Pool đã sử dụng kết nối phù hợp:** các context cũ đã được xử lý, pool không còn phụ thuộc trạng thái credential trước khi chuyển đổi.
- **Nghiệp vụ hoạt động:** `LdapTemplate` và repository vẫn tìm đúng entry với ACL/schema và base DN của production.

**Không thể kết luận “mật khẩu mới hoạt động” chỉ vì một truy vấn từ pool trả dữ liệu.** Context đã bind từ trước có thể vẫn còn phiên xác thực hợp lệ cho đến khi server ngắt, hết hạn hoặc ứng dụng đóng kết nối. Cách server xử lý các phiên đã bind sau đổi mật khẩu là chi tiết triển khai, cần được kiểm thử thực tế.

## 3. Kiểm kê trước khi luân chuyển

Trước khi thay credential, cần xác định phạm vi ảnh hưởng:

| Câu hỏi | Vì sao cần biết? |
|---|---|
| Có bao nhiêu service hoặc instance dùng bind DN này? | Tránh đổi mật khẩu khi còn ứng dụng chưa được cập nhật |
| Tài khoản có quyền gì và truy vấn trên OU nào? | Credential mới phải giữ đúng phạm vi nghiệp vụ |
| Secret được lấy ở startup hay có cơ chế refresh? | Quyết định restart/rollout hoặc đổi context động |
| Sử dụng `LdapContextSource` trực tiếp hay pool? | Quyết định cách xử lý các kết nối đang tồn tại |
| Pool thuộc Spring LDAP hay JNDI native? | Cách kiểm tra, cấu hình và xả kết nối khác nhau |
| Có nhiều LDAP URL/replica không? | Kiểm tra tính nhất quán credential trên các directory replica |
| Có thể tạo **hai service account cùng quyền** không? | Có thể triển khai luân phiên mà không phải tranh chấp mật khẩu của cùng DN |
| Có quy trình rollback mật khẩu/danh tính không? | Cần đường quay lại thực tế nếu chuyển đổi thất bại |
| Ứng dụng có thao tác ghi, đổi DN hoặc xóa không? | Smoke test nên dùng phép đọc an toàn, còn kiểm tra ghi phải có fixture riêng |

Ghi nhận **đường dẫn/tên secret**, bind DN, endpoint và người/phần mềm sở hữu quy trình. Không đưa giá trị mật khẩu vào ticket, log, chat hoặc Git. Lập danh sách consumer của tài khoản dịch vụ để tránh bỏ sót batch job, scheduled job, API service hay công cụ quản trị cùng sử dụng credential.

Với directory có replication, cần xác định nơi đổi mật khẩu được thực hiện, thời gian dữ liệu mới lan truyền và khả năng mỗi node chấp nhận credential mới. Không giả định một lần bind thành công tới một endpoint chứng minh toàn bộ replica đã đồng bộ.

## 4. Hiểu connection pool trong Spring LDAP

Spring LDAP có thể hoạt động **không pool**, sử dụng **pooling của JNDI/JDK** hoặc sử dụng **`PoolingContextSource`** của Spring LDAP. Cần biết chính xác cơ chế mà ứng dụng đang dùng.

| Cơ chế | Đặc điểm | Điều cần xem khi rotate |
|---|---|---|
| **Không pooling** | Tạo/đóng context theo mỗi lần sử dụng | Mỗi kết nối mới phản ánh credential mà `ContextSource` thực sự đang giữ |
| **JNDI native pooling** | Kích hoạt thông qua cờ `pooled` và cấu hình JNDI/JVM; ít tùy chọn bảo trì | Kiểm tra cache kết nối theo danh tính, hành vi TLS và việc làm mới credential |
| **Spring LDAP `PoolingContextSource`** | Bọc `ContextSource`, tái sử dụng `DirContext`, hỗ trợ validation/eviction | Kiểm tra context cũ, borrowed/idle, validation và lifecycle pool |
| **Pool do thư viện/hạ tầng khác quản lý** | Có thể là một bean hoặc lớp proxy riêng | Dựa trên hướng dẫn và API thực tế để đóng/xả pool |

Theo tài liệu Spring LDAP, cờ native `setPooled(boolean)` của `AbstractContextSource` mặc định là `false` trong cấu hình thông thường. Pool JNDI native có nhiều hạn chế và **không phù hợp khi dùng TLS theo cách mà cờ native pooling này không hỗ trợ**. Nếu cần connection pooling với khả năng kiểm tra context, ưu tiên đánh giá cơ chế pooling của Spring LDAP và kiểm thử trên phiên bản đang dùng.

**Không tự thêm khóa `spring.ldap.pool.*` vào YAML rồi giả định Spring Boot sẽ cấu hình pool.** Các thuộc tính `spring.ldap.urls`, `base`, `username`, `password` được Spring Boot hỗ trợ; còn cấu hình pool phải dựa trên bean/API thực tế hoặc cơ chế tích hợp được dự án cung cấp.

Một lỗi cấu hình đặc biệt nguy hiểm là sử dụng một pool `PoolingContextSource` chung cho nhiều danh tính người dùng thay đổi theo từng request. Cơ chế này giả định các context lấy từ cùng nhánh read-only/read-write có môi trường xác thực nhất quán; nếu bọc `AuthenticationSource` động theo từng người dùng mà không thiết kế đúng, pool có thể tái sử dụng context của danh tính trước. Trong ứng dụng có Spring Security LDAP bind của người dùng cuối, không gộp tùy tiện pool dịch vụ với cơ chế bind riêng của từng user.

## 5. Validation của pool kiểm tra gì?

`PoolingContextSource` hỗ trợ các ý tưởng như:

| Thiết lập | Ý nghĩa | Chú ý khi luân chuyển |
|---|---|---|
| `testOnBorrow` | Kiểm tra context trước khi đưa cho caller | Giúp phát hiện context đã hỏng; có chi phí kiểm tra |
| `testOnReturn` | Kiểm tra context khi được trả về pool | Có thêm chi phí cho mỗi lần trả |
| `testWhileIdle` | Kiểm tra context nhàn rỗi trong vòng dọn pool | Cần có tác vụ eviction/validation hoạt động |
| **Validation query** | Phép tìm LDAP nhỏ dùng để xác minh context còn phục vụ được | Base/filter phải tồn tại, tài khoản có quyền đọc |
| **Idle eviction** | Loại bỏ context nhàn rỗi theo thời gian và chính sách | Không thay thế quy trình làm mới toàn bộ credential |
| **Pool size/wait** | Giới hạn số context đang được mượn và thời gian chờ | Thiết lập quá thấp có thể gây nghẽn request khi rollout |

`DefaultDirContextValidator` của Spring LDAP dùng một phép search nhỏ để kiểm tra kết nối còn hoạt động; nếu query không trả kết quả như yêu cầu hoặc ném exception, validation có thể thất bại. Cần cấu hình validation base phù hợp với context base và quyền ACL. Nếu service account không được phép đọc entry kiểm tra, validator có thể đánh dấu lỗi dù mật khẩu đúng.

**Đặc biệt:** `testOnBorrow=true` không xác nhận server sẽ chấp nhận **mật khẩu mới trên một phiên bind mới**. Nó có thể chỉ kiểm tra rằng context cũ vẫn thực hiện search thành công. Vì vậy quy trình rotation luôn cần một **fresh bind probe** độc lập với pool.

### Ba phép kiểm tra không nên gộp thành một

~~~text
A. Fresh bind  -> LDAP server chấp nhận credential mới khi mở kết nối mới
B. Pool borrow -> Context lấy từ pool có còn hoạt động không
C. Business    -> Repository/LdapTemplate truy cập đúng OU, ACL, schema
~~~

Cả A, B và C đều phải đạt yêu cầu trước khi kết luận đã chuyển đổi thành công. Một health endpoint chỉ kiểm tra bean `LdapTemplate` tồn tại không chứng minh bất kỳ phép kiểm tra kết nối nào.

## 6. Cách an toàn nhất khi cần chuyển không gián đoạn: hai danh tính dịch vụ

Nếu directory và chính sách tổ chức cho phép, hãy luân phiên giữa **hai service account độc lập** có quyền tương đương đã kiểm tra, ví dụ:

~~~text
uid=app-reader-a,ou=services,dc=example,dc=org
uid=app-reader-b,ou=services,dc=example,dc=org
~~~

Mục tiêu là giữ account A đang phục vụ traffic trong lúc chuẩn bị và kiểm thử account B. Mỗi account có DN và secret riêng; việc vô hiệu hóa A chỉ diễn ra khi chắc chắn không còn consumer hợp lệ cần A.

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Operator / CI-CD
    participant S as Secret manager
    participant D as LDAP directory
    participant P as Application pods

    O->>D: Tạo/chuẩn bị account B với ACL cần thiết
    O->>S: Lưu credential B dưới secret version mới
    O->>D: Fresh bind B + read-only probe
    D-->>O: Bind và đọc thành công
    O->>P: Rollout instance mới với DN/secret B
    P->>D: Kết nối mới bằng B
    D-->>P: Truy vấn thành công
    O->>P: Kiểm tra từng instance và toàn bộ consumer
    O->>D: Vô hiệu hóa A sau thời gian quan sát
    O->>S: Thu hồi secret A theo quy trình
~~~

Các bước vận hành:

1. **Chuẩn bị B:** tạo account với đúng ACL, object class và policy cần thiết; không sao chép vô điều kiện đặc quyền quản trị từ A.
2. **Lưu secret B:** cấp vào secret manager dưới danh tính/phiên bản mới; ghi audit event mà không lộ giá trị.
3. **Kiểm tra độc lập:** từ cùng network/JVM hoặc môi trường gần production, mở **kết nối LDAP mới** bằng DN và mật khẩu B, đọc một entry chỉ dành cho health/probe.
4. **Rollout từng đợt:** khởi tạo context và pool mới cho instance sử dụng B. Kiểm tra readiness và phép đọc thực tế sau mỗi đợt.
5. **Giám sát:** theo dõi lỗi bind, timeout, số connection, độ trễ truy vấn, lỗi từ `LdapTemplate` và repository; không dùng credential cũ để che lỗi.
6. **Đối soát consumer:** xác minh tất cả instance/job còn cần LDAP đã chuyển sang B, bao gồm tiến trình chạy nền.
7. **Thu hồi A:** chỉ sau khi hoàn tất cutover, vô hiệu hóa A/secret A theo chính sách và theo dõi xem còn sự phụ thuộc bất ngờ nào xuất hiện.

**Rollback:** trước khi thu hồi A, có thể triển khai trở lại cấu hình A nếu B gây lỗi và A vẫn còn hợp lệ. Sau khi A đã bị vô hiệu hóa, rollback không còn đơn giản là đổi biến môi trường về A; cần quy trình khôi phục danh tính/credential đã được phê duyệt.

Phương án hai account không tự đảm bảo zero downtime. Kết quả còn phụ thuộc cách ứng dụng rollout, session, request đang chạy, pool, replication và ACL. Tuy nhiên, nó cho phép một khoảng **chồng lấn danh tính** có kiểm soát để xác minh B trước khi ngắt A.

## 7. Khi bắt buộc phải đổi mật khẩu trên cùng một bind DN

Có hệ thống chỉ cấp một service account, ví dụ `uid=app-reader,ou=services,dc=example,dc=org`. Khi đó không thể mặc định cả mật khẩu cũ và mới đều được server chấp nhận đồng thời.

Một trình tự được điều phối:

1. **Chuẩn bị secret mới ở chế độ chưa được ứng dụng sử dụng**; không ghi mật khẩu vào file, ticket hay log.
2. **Lên cửa sổ triển khai** và thông báo rõ những consumer của account; chuẩn bị khả năng giảm traffic hoặc restart phù hợp yêu cầu dịch vụ.
3. **Đổi mật khẩu trên directory** qua cơ chế quản trị có kiểm soát.
4. **Cấp secret mới cho các instance** và khởi tạo lại `ContextSource`/pool theo thiết kế, thường bằng rolling restart hoặc rollout mới.
5. **Thử fresh bind và phép đọc** từ từng lớp môi trường hoặc replica cần thiết.
6. **Theo dõi tỷ lệ lỗi** trong thời gian chuyển tiếp; các context cũ có thể còn sống hoặc thất bại tùy server.
7. **Xác nhận mọi consumer đã nhận secret mới**; hoàn thành kiểm tra pool và hoạt động nghiệp vụ.

**Rủi ro:** trong khoảng sau khi directory đổi mật khẩu nhưng trước khi tất cả instance nhận secret mới, các kết nối mới do instance cũ tạo có thể bị từ chối. Restart pool bằng **mật khẩu cũ** cũng không sửa được vấn đề này.

Rollback với một bind DN **không có nghĩa chỉ khôi phục phiên bản secret cũ trong ứng dụng**. Nếu directory đã vô hiệu hóa mật khẩu cũ, cần đổi lại mật khẩu ở directory hoặc khôi phục một phương án credential hợp lệ khác rồi xác minh fresh bind. Do đó, phải định nghĩa phương án rollback trước khi đổi.

Nếu directory có cơ chế cho phép nhiều credential hoặc khoảng chuyển tiếp cho cùng một DN, cần xác minh bằng tài liệu/kiểm thử thực tế; không giả định tính năng đó tồn tại ở mọi LDAP server.

## 8. Secrets và profile cho ứng dụng Spring Boot

Một cấu hình production tối giản:

~~~yaml
# application-prod.yml
spring:
  ldap:
    urls: ${LDAP_URL}
    base: ${LDAP_BASE_DN}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}

app:
  directory:
    probe-dn: ${LDAP_PROBE_DN:ou=people}
~~~

`app.directory.probe-dn` là khóa **tùy chỉnh của ứng dụng** để chỉ định entry phục vụ phép đọc kiểm tra. Nó không phải thuộc tính Spring Boot tự động dùng. Đường dẫn probe được biểu diễn **tương đối với** `spring.ldap.base` trong ví dụ.

Khi đang dùng `spring.ldap.base=dc=example,dc=org` và `probe-dn=ou=people`, phép lookup phải đọc:

~~~text
ou=people,dc=example,dc=org
~~~

Yêu cầu đối với cấu hình production:

- URL phải trỏ đúng LDAP server của môi trường và sử dụng LDAPS hoặc StartTLS được cấu hình, kiểm chứng.
- Bind DN rõ ràng, không trộn account của `dev`/`test` với `prod`.
- Mật khẩu được inject từ secret manager; không có giá trị default dạng rõ trong Git.
- Endpoint, base DN, chứng chỉ CA/truststore và ACL được kiểm tra trước rollout.
- Nếu secret được đưa vào **environment variable của process**, sửa Secret bên ngoài thường **không cập nhật environment của process đang chạy**. Cần restart/rollout hoặc cơ chế nạp lại secret thật sự đã được triển khai.
- Nếu dùng secret dạng tệp được cập nhật động, ứng dụng vẫn phải có cơ chế đọc lại tệp và thay thế context/pool. Việc mount tự thay file không làm bean `ContextSource` đang giữ mật khẩu cũ tự đổi theo.

### Ví dụ phần cấu hình container trên Kubernetes

~~~yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: prod
  - name: LDAP_URL
    value: ldaps://directory.example.org:636
  - name: LDAP_BASE_DN
    value: dc=example,dc=org
  - name: LDAP_BIND_DN
    valueFrom:
      secretKeyRef:
        name: ldap-service-identity
        key: bind-dn
  - name: LDAP_BIND_PASSWORD
    valueFrom:
      secretKeyRef:
        name: ldap-service-identity
        key: password
~~~

Đây chỉ là phần `env` của container spec, không phải manifest Deployment hoàn chỉnh. Khi chuyển từ A sang B, một phương án là cập nhật nội dung hoặc tham chiếu secret, **rollout instance mới** và đảm bảo mỗi process/pool khởi tạo bằng DN và mật khẩu B. Quyền đọc Secret và rollout phải được kiểm soát; không in giá trị secret khi kiểm tra cấu hình.

## 9. Fresh bind probe: kiểm tra credential mới độc lập với pool

Phép kiểm tra tốt nhất cho credential mới là tạo **`ContextSource` riêng không bật pooling**, thực hiện một LDAP bind mới và đọc một entry an toàn mà tài khoản dịch vụ phải có quyền xem.

Ví dụ Java:

~~~java
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

public final class FreshServiceBindProbe {

    private FreshServiceBindProbe() {
    }

    public static void verify(
            String url,
            String baseDn,
            String serviceBindDn,
            String newPassword,
            String probeDnRelativeToBase) {

        LdapContextSource freshSource = new LdapContextSource();
        freshSource.setUrl(url);
        freshSource.setBase(baseDn);
        freshSource.setUserDn(serviceBindDn);
        freshSource.setPassword(newPassword);

        // Không lấy lại context từ JNDI native pool.
        freshSource.setPooled(false);
        freshSource.afterPropertiesSet();

        LdapTemplate freshTemplate = new LdapTemplate(freshSource);

        Boolean canReadEntry = freshTemplate.lookup(
                probeDnRelativeToBase,
                (AttributesMapper<Boolean>) attributes ->
                        attributes.get("objectClass") != null);

        if (!Boolean.TRUE.equals(canReadEntry)) {
            throw new IllegalStateException(
                    "Service account bind probe did not return the expected entry");
        }
    }
}
~~~

Với ví dụ directory có `dc=example,dc=org` và `ou=people`, truyền `probeDnRelativeToBase="ou=people"`. Nhánh probe phải thực sự tồn tại, tài khoản dịch vụ có quyền đọc `objectClass` và kết nối mới dùng TLS với xác minh chứng chỉ. Nếu service không có quyền đọc OU đó, hãy chọn **entry probe khác được cấp quyền rõ ràng**.

Ý nghĩa và giới hạn:

- Tạo `LdapContextSource` mới với `setPooled(false)` tránh tái sử dụng native JNDI pool trong phép thử này.
- `lookup(...)` thực hiện thao tác LDAP thực tế để xác minh không chỉ khởi tạo bean, mà còn có bind và quyền đọc cần thiết.
- Vì đây là context riêng, nó **không** chứng minh rằng pool chính của ứng dụng đã được thay thế hoặc làm mới.
- Không log `newPassword`, không trả secret trong exception/metrics và không xuất giá trị qua endpoint công khai.
- Phép probe đọc một entry đã biết, không thực hiện Add/Modify/Delete hoặc thử credential sai hàng loạt gây khóa account.

Đối với một số directory hoặc trình xử lý xác thực có nhiều địa chỉ LDAP, cần thực hiện phép thử trên từng endpoint/replica theo chính sách. Thành công ở một server không đảm bảo credential đã lan truyền đến mọi server.

### Lệnh kiểm tra thủ công ở lớp LDAP

Có thể dùng `ldapwhoami` khi server hỗ trợ thao tác tương ứng:

~~~bash
ldapwhoami -x \
  -H ldaps://directory.example.org:636 \
  -D "uid=app-reader-b,ou=services,dc=example,dc=org" \
  -W
~~~

`-W` yêu cầu nhập mật khẩu tương tác, tránh ghi mật khẩu trong command line. Lệnh này giúp kiểm tra danh tính bind; nó **không** chứng minh account có quyền đọc các nhánh nghiệp vụ.

Để kiểm tra quyền đọc bằng thao tác không thay đổi dữ liệu:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://directory.example.org:636 \
  -D "uid=app-reader-b,ou=services,dc=example,dc=org" \
  -W \
  -b "ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" dn objectClass
~~~

Dùng cùng CA/truststore và network policy với ứng dụng khi có thể. `ldapsearch` nhận DN tuyệt đối ở `-b`, khác với `LdapTemplate` có thể dùng DN tương đối theo `spring.ldap.base`.

## 10. Đưa cấu hình mới vào pool như thế nào?

Sau khi fresh bind bằng B hoặc mật khẩu mới thành công, phải đảm bảo kết nối thực tế của ứng dụng cũng chuyển sang credential đó.

### Phương án restart/rollout (thường dễ xác minh nhất)

1. Cập nhật secret version hoặc tham chiếu secret của workload.
2. Rollout instance mới và khởi tạo lại `ContextSource` bằng giá trị mới.
3. Tạo pool mới với cấu hình hiện hành; không tái sử dụng pool cũ của process trước.
4. Chạy readiness check bằng truy vấn đọc phù hợp (có thể mượn context từ **pool mới**).
5. Chỉ nhận traffic khi instance đã được kiểm tra; rút dần traffic khỏi instance dùng cấu hình cũ.
6. Chờ tác vụ đang chạy hoàn thành theo timeout và đóng resource/pool của instance cũ theo lifecycle của ứng dụng.
7. Xác minh không còn process/job phụ thuộc DN/credential cũ trước khi thu hồi.

Spring LDAP `PoolingContextSource` có lifecycle giải phóng tài nguyên khi bean bị hủy. Tuy nhiên, cách đóng chính xác còn phụ thuộc phiên bản, cấu hình và việc ứng dụng quản lý bean. **Không chỉ thay field mật khẩu của một contextsource đang có pool rồi mặc định mọi context trong pool sẽ tự bind lại.** Với ứng dụng có yêu cầu hot reload, phải thiết kế thay **toàn bộ cặp contextsource + pool** một cách nhất quán, ngăn request mới mượn pool cũ và xử lý request đang chạy.

### Khi không có pool

Ngay cả khi không dùng pooling, một bean `LdapContextSource` được tạo từ secret cũ vẫn có thể tiếp tục dùng mật khẩu cũ cho những kết nối sau đó. Vì vậy vẫn phải tái khởi tạo contextsource hoặc restart theo cơ chế cấu hình. Việc không có pool làm giảm số context đang sống, nhưng không giải quyết vấn đề stale configuration.

### Khi sử dụng Spring LDAP pool

Tùy phiên bản, có thể cấu hình `PoolingContextSource` để:

- Kiểm tra context khi borrow và khi idle.
- Cấu hình `DefaultDirContextValidator` với một validation query nhỏ, được ACL cho phép.
- Giới hạn số context hoạt động, số idle và thời gian chờ khi pool cạn.
- Bảo trì/loại bỏ context hỏng bằng eviction và lifecycle phù hợp.

Mã Java bên dưới chỉ minh họa **cấu hình pool**, giả định ứng dụng đã có bean `LdapContextSource` được cấu hình đúng từ secret và TLS; khi tích hợp thực tế cần chú ý bean nào được chọn làm `ContextSource` cho `LdapTemplate` và tránh tạo vòng phụ thuộc:

~~~java
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.pool.factory.PoolingContextSource;
import org.springframework.ldap.pool.validation.DefaultDirContextValidator;

// Đoạn minh họa trong phương thức cấu hình bean:
PoolingContextSource pool = new PoolingContextSource();
pool.setContextSource(rawLdapContextSource);
pool.setDirContextValidator(new DefaultDirContextValidator());
pool.setTestOnBorrow(true);
pool.setTestWhileIdle(true);
pool.setTimeBetweenEvictionRunsMillis(30_000L);
pool.setMaxActive(8);
pool.setMaxIdle(4);
~~~

`rawLdapContextSource` là biến đã được định nghĩa từ cấu hình ứng dụng (không phải một biến mặc định của Spring). Để sử dụng các lớp này cần module hỗ trợ Spring LDAP pooling và dependency phù hợp với phiên bản Spring LDAP. Những giá trị `8`, `4` và `30_000L` chỉ là **số minh họa**, cần điều chỉnh theo lưu lượng, giới hạn kết nối của directory và đặc điểm workload.

Pool validation thường kiểm tra **khả năng sử dụng của context**, không kiểm tra lại mật khẩu theo một bind mới cho từng lần borrow. Cần thực hiện fresh bind riêng trong quy trình luân chuyển.

## 11. Theo dõi pool sau khi đổi credential

Một lần bind thành công không đảm bảo ứng dụng chịu tải ổn định. Cần theo dõi sự thay đổi theo thời gian:

| Tín hiệu | Điều nó có thể cho thấy | Cách diễn giải |
|---|---|---|
| **Lỗi bind / invalid credentials** | Process còn secret cũ, replication chưa đồng bộ hoặc secret sai | Kiểm tra mới/từng instance; không in password |
| **Số context active/in use** | Mức độ mượn pool | Tăng cao kéo dài có thể là nghẽn hoặc không trả resource |
| **Số context idle** | Mức dự trữ kết nối | Giảm về 0 khi traffic tăng có thể bình thường; xem cùng active/wait |
| **Wait time / pool exhaustion** | Request đang chờ context | Pool quá nhỏ, server chậm hoặc kết nối bị kẹt |
| **Validation failures** | Context cũ/hỏng hoặc validation query thiếu quyền | Phân biệt lỗi network và lỗi ACL/probe |
| **LDAP operation latency** | Chất lượng dịch vụ sau rollover | So sánh với baseline trước rollout |
| **CommunicationException / timeout** | Kết nối bị ngắt, DNS, TLS, server quá tải | Kiểm tra endpoint, certificate, timeout |
| **Lỗi `noSuchObject` hoặc ACL** | Base DN, quyền hoặc schema khác trước | Credential mới có thể khác quyền dù bind thành công |
| **Độ lệch giữa các instance** | Chỉ một số pod/job còn dùng cấu hình cũ | Kiểm tra rollout revision và secret version |

Không phải mọi thư viện công bố sẵn tất cả metrics trên. Nếu `PoolingContextSource` có khả năng quan sát số active/idle, hãy tích hợp metric tại lớp pool theo API thực tế; không tự giả định có sẵn các tên metric Spring Boot Actuator cố định.

### Phân biệt ba trạng thái sau rollout

| Trạng thái | Kết luận |
|---|---|
| Fresh bind thành công, pool cũ còn sống | Credential mới hợp lệ, nhưng rollout pool **chưa được chứng minh** |
| Pool borrow thành công, fresh bind thất bại | Context cũ có thể vẫn hợp lệ; **không đạt yêu cầu rotation** |
| Fresh bind, pool và phép đọc nghiệp vụ đều thành công | Đạt kiểm tra kỹ thuật cơ bản; tiếp tục theo dõi consumer và replica |

Phép đọc ở bước cuối phải dùng đúng account và vùng dữ liệu mà ứng dụng thực sự cần. Nếu account mới chỉ bind được nhưng không tìm thấy `ou=people` do ACL, thay đổi vẫn chưa sẵn sàng.

## 12. Bảo mật khi xử lý mật khẩu và pool

Luân chuyển mật khẩu liên quan tới cả bảo vệ secret và bảo vệ quá trình vận hành:

- **Không log credential.** Không ghi `LDAP_BIND_PASSWORD`, giá trị secret, phần header nhạy cảm hoặc context environment có chứa mật khẩu.
- **Tránh truyền mật khẩu trên command line.** Dùng cơ chế prompt `-W` hoặc secret injection; tránh tham số mật khẩu xuất hiện trong shell history và process list.
- **Giới hạn quyền secret manager.** CI/CD, operator và ứng dụng chỉ đọc được secret của môi trường mà chúng phụ trách.
- **Dùng TLS được xác minh.** Bind qua LDAPS hoặc StartTLS có CA/truststore và kiểm tra hostname; không tắt TLS verification khi thay đổi account.
- **Giới hạn ACL của account mới.** Phân quyền theo OU/attribute và thao tác thực sự cần; không nhân cơ hội rotation mở quyền rộng.
- **Không dùng pool chung cho danh tính user tùy ý.** Phân biệt bind của service với bind của người dùng cuối qua Spring Security LDAP.
- **Không dùng phép kiểm tra ghi/xóa trên production** để xác minh rotation nếu không có fixture riêng được cấp phép; fresh bind và read-only lookup thường đủ cho smoke test.
- **Ghi audit hợp lý.** Theo dõi thời điểm chuyển secret, actor, identity alias/secret version, trạng thái rollout và mã lỗi, nhưng không ghi bí mật.
- **Thu hồi account cũ đúng thời điểm.** Không vô hiệu hóa trước khi xác nhận consumer; cũng không giữ vô thời hạn credential không còn dùng.

Credential hợp lệ không chứng minh quyền truy cập hợp lệ cho mọi nghiệp vụ. Ví dụ account có quyền đọc `uid` nhưng không đọc `member` của nhóm có thể khiến Spring Security LDAP tìm được người dùng nhưng không xác định được quyền ứng dụng.

## 13. Những lỗi vận hành thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `invalidCredentials (49)` sau rotation | Instance còn mật khẩu cũ; secret mới chưa tới nơi; replica chưa cập nhật | Fresh bind trên endpoint liên quan, kiểm tra rollout và secret version |
| Truy vấn đang chạy được nhưng mở kết nối mới thất bại | Pool còn context đã bind trước khi đổi mật khẩu | Kiểm tra credential mới riêng; tạo context/pool mới |
| Fresh bind thành công nhưng repository lỗi ACL | Account mới thiếu quyền đọc OU/attribute hoặc quyền ghi | So sánh ACL, thử read-only lookup đúng vùng nghiệp vụ |
| Một pod thất bại, pod khác thành công | Rollout chưa đồng bộ, pod giữ config/pool cũ | Kiểm tra từng instance và revision |
| Lỗi kết nối chỉ khi traffic tăng | Pool size, timeout hoặc server connection limit | Theo dõi active/idle/wait, cân đối pool và giới hạn server |
| `testOnBorrow` báo fail hàng loạt | Entry validation không đọc được, network/TLS lỗi hoặc context hỏng | Kiểm tra validation base/filter và quyền của account |
| Lỗi TLS handshake sau đổi credential | Thay URL/CA/truststore sai trong cùng rollout | Tách chẩn đoán TLS khỏi mật khẩu; kiểm tra certificate |
| LDAP đọc sai nhánh sau chuyển | `spring.ldap.base`/DN thay đổi ngoài ý muốn | So sánh cấu hình base DN và probe tương đối |
| Rollback secret cũ không đăng nhập được | Mật khẩu cũ đã bị directory vô hiệu hóa | Khôi phục credential tại directory hoặc dùng account dự phòng đã chuẩn bị |
| Nhóm/quyền người dùng không tải được | Account service mới không đọc được group OU | Kiểm tra `member`/ACL và search base của Spring Security |
| Restart liên tục không sửa lỗi | Cả secret mới và/hoặc directory đang sai | Dừng retry hàng loạt, đối chiếu LDAP server diagnostics |
| Lỗi JNDI pooling khi dùng TLS | Chọn native pooling không tương thích cấu hình | Đánh giá pooling Spring LDAP hoặc bỏ native pooling, kiểm thử TLS |

Các lỗi có thể là exception ở JNDI/Spring LDAP và mã trả về từ server; không giả định một exception Java luôn tương ứng duy nhất một nguyên nhân. Dùng log chẩn đoán server, metric và kiểm tra fresh bind để xác định vấn đề.

**Không liên tục thử mật khẩu cũ và mới bằng một account** khi directory có chính sách khóa do đăng nhập sai. Hãy xác minh phiên bản secret và thời điểm cập nhật trước khi thử lại; giới hạn số lần thử.

## 14. Kiểm thử rotation bằng directory thử nghiệm

Một test directory độc lập nên mô phỏng tối thiểu:

- Một entry `ou=people` và vài entry `inetOrgPerson` có đủ `cn`, `sn`.
- Service account A và B (nếu thực tế cho phép), có ACL gần giống production.
- Kết nối TLS và chứng chỉ CA dùng trong test.
- Spring Boot test profile, dùng secret/endpoint tách khỏi production.
- Nếu cần kiểm tra pooling, một `PoolingContextSource` được cấu hình và quan sát được số context active/idle theo khả năng phiên bản thư viện.

### Ma trận kiểm thử

| Kịch bản | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| **Fresh bind A** | Tạo context mới với DN/secret A | Bind và lookup thành công |
| **Chuẩn bị B** | Tạo account B có ACL cần thiết; fresh bind B | B có thể đọc entry probe và dữ liệu nghiệp vụ được phép |
| **Rollout A → B** | Khởi chạy instance mới dùng B; pool mới | Từng instance readiness, LDAP query ổn định |
| **Xóa A sau cutover** | Vô hiệu hóa A ở directory test | B tiếp tục hoạt động; các consumer còn A được phát hiện |
| **Đổi mật khẩu cùng DN** | Đổi mật khẩu account A, giữ một context cũ nếu server cho phép | Fresh bind cũ có thể thất bại; fresh bind mới thành công; hành vi context cũ được ghi nhận |
| **Pool stale** | Thay secret mà không tái tạo pool | Chứng minh một query trong pool không đảm bảo fresh bind mới |
| **Validation lỗi** | Chặn entry probe hoặc ngắt mạng test | Validator/borrow báo lỗi theo cấu hình |
| **ACL sai** | Bỏ quyền đọc một OU của B | Bind có thể thành công nhưng nghiệp vụ báo lỗi |
| **Nhiều replica** | Thử từng LDAP URL phù hợp | Xác nhận thời điểm credential đồng bộ |
| **Rollback** | Chuyển về A khi A còn hợp lệ hoặc khôi phục credential theo quy trình | Dịch vụ quay về trạng thái đã kiểm chứng |
| **Credential cũ không hợp lệ** | Thử fresh bind với phiên bản cũ trong giới hạn an toàn | Xác minh kết quả từ chối, không dùng pool để suy luận |
| **Không rò rỉ secret** | Xem log, exception, build artifact và health output | Không có mật khẩu dạng rõ |

Các bài test cố tình tạo lỗi bind hoặc thay đổi mật khẩu phải chạy với account/directory test riêng, có giới hạn số lần thử để không kích hoạt chính sách khóa ngoài ý muốn.

### Một bài test tích hợp cho credential mới

Ví dụ test sử dụng phương thức `FreshServiceBindProbe.verify(...)` ở mục 9, với giá trị đưa vào từ **test configuration/secret**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class ServiceAccountRotationIntegrationTest {

    @Value("${spring.ldap.urls}")
    private String url;

    @Value("${spring.ldap.base}")
    private String baseDn;

    @Value("${spring.ldap.username}")
    private String bindDn;

    @Value("${spring.ldap.password}")
    private String password;

    @Test
    void newCredentialCanBindAndReadDirectory() {
        FreshServiceBindProbe.verify(
                url, baseDn, bindDn, password, "ou=people");
    }
}
~~~

Bài kiểm tra này buộc tạo context riêng và thực hiện LDAP lookup thật. Nó không thay cho kiểm thử pool đang phục vụ `LdapTemplate`/repository, hoặc xác minh đường truyền TLS và ACL trong production. Nếu cấu hình `spring.ldap.urls` là nhiều LDAP URL, cần điều chỉnh hàm probe và kiểm thử endpoint theo yêu cầu thực tế.

## 15. Quy trình release và rollback để người vận hành sử dụng

Có thể dùng một runbook gọn với các mốc rõ ràng:

| Giai đoạn | Việc cần làm | Điều kiện chuyển bước |
|---|---|---|
| **Chuẩn bị** | Kiểm kê consumer, contextsource/pool, ACL, secret, backup và kế hoạch rollback | Có danh sách consumer và owner |
| **Tạo credential mới** | Chuẩn bị B hoặc mật khẩu mới trên cùng DN theo phương án đã chọn | Credential được lưu an toàn |
| **Kiểm tra trước rollout** | Fresh bind và read-only probe, TLS và quyền LDAP | Probe hợp lệ trên các endpoint yêu cầu |
| **Triển khai** | Cập nhật secret, restart/rollout instance, tạo contextsource/pool mới | Instance mới sẵn sàng |
| **Quan sát** | So sánh lỗi bind, LDAP latency, active/idle/wait, query nghiệp vụ | Không có lỗi nghiêm trọng vượt ngưỡng đã thống nhất |
| **Đối soát** | Kiểm tra mọi pod, batch job, scheduled job đã dùng credential mới | Không còn consumer hợp lệ trên A |
| **Thu hồi** | Vô hiệu hóa credential cũ và xóa quyền truy cập secret cũ | Credential mới vẫn phục vụ tốt |
| **Ghi nhận** | Lưu thời điểm, secret version, danh tính, kết quả và hành động rollback nếu có | Audit hoàn chỉnh, không lộ bí mật |

**Điểm quyết định rollback:** nếu fresh bind thất bại, không tiến hành rollout. Nếu rollout thất bại trước khi vô hiệu hóa A, chuyển traffic về phiên bản A đã kiểm chứng. Nếu đã đổi mật khẩu của **cùng DN**, rollback phải phối hợp thay đổi **tại directory** và ở ứng dụng; chỉ phục hồi Secret cũ không đủ.

Cần xác định trước ngưỡng ra quyết định theo SLO thực tế, ví dụ tỷ lệ lỗi LDAP, độ trễ xác thực và thời gian chờ pool; không dùng một giá trị số chung cho mọi hệ thống.

## 16. Bài tập thực hành

**Bối cảnh:** service Spring Boot `employee-directory` dùng `LdapRepository` để tìm nhân sự trong `ou=people`, sử dụng `LdapContextSource` với bind account riêng. Ứng dụng đang chạy hai instance và có pool tái sử dụng context. Nhóm muốn chuyển từ account A sang B mà không đánh mất khả năng đọc directory.

Hãy thực hiện trên **LDAP test độc lập**:

1. Dựng `dc=example,dc=org`, `ou=people` và hai service account A/B với ACL chỉ đọc tương đương.
2. Cấu hình profile `test` để ứng dụng dùng A; gọi repository và ghi nhận kết quả, độ trễ và số context pool.
3. Viết hàm kiểm tra fresh bind B bằng context không pooling; kiểm tra đọc đúng entry probe.
4. Tạo instance cấu hình B và pool mới; chạy truy vấn lặp lại, xác minh DN/base và kết quả vẫn đúng.
5. Đặt instance A ở chế độ ngừng nhận request, chờ các thao tác đang chạy kết thúc, sau đó dừng instance A.
6. Vô hiệu hóa A trong directory test; xác nhận B vẫn hoạt động và fresh bind A thất bại trong giới hạn thử hợp lý.
7. Thử lại theo phương án **một DN**: đổi password mà chưa cập nhật process, quan sát sự khác biệt giữa context cũ và fresh bind.
8. Kiểm tra tác dụng của `testOnBorrow`/`testWhileIdle` đối với context bị hỏng; giải thích vì sao chúng không chứng minh password mới.
9. Thiết kế rollback cho hai trường hợp A/B và cùng DN, chỉ rõ ở bước nào có thể dùng lại credential cũ.
10. Viết checklist release gồm secret version, TLS, ACL, readiness, pool metrics, LDAP search và thu hồi account cũ.

**Tiêu chí hoàn thành:** người học phân biệt được cập nhật secret, fresh bind, làm mới contextsource/pool và kiểm tra nghiệp vụ; xác định đúng lý do rollback với cùng DN phức tạp; không dùng credential production trong test.

## 17. Ghi nhớ và tài liệu tham khảo

**Luân chuyển mật khẩu LDAP chỉ hoàn tất khi credential mới được server chấp nhận trên kết nối mới, ứng dụng thực sự dùng cấu hình mới, pool không còn phụ thuộc vào context cũ và các thao tác nghiệp vụ vẫn thành công với ACL phù hợp.**

Cách triển khai dùng hai service account độc lập thường giúp giảm rủi ro gián đoạn khi có thể duy trì A và B trong thời gian chuyển tiếp. Nếu buộc phải đổi mật khẩu trên cùng DN, cần điều phối thời điểm thay đổi ở directory và rollout ứng dụng, đồng thời chuẩn bị rollback thực tế. `PoolingContextSource` có validation và eviction hữu ích, nhưng **không thay thế fresh bind probe**.

Tài liệu chính thức để tra cứu theo phiên bản đang sử dụng:

- [Spring Boot — LDAP connection configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html): `spring.ldap.urls`, `username`, `password` và cấu hình ứng dụng.
- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): `PoolingContextSource`, validation/eviction, các hạn chế với `AuthenticationSource` động.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): cấu hình `ContextSource` và native Java LDAP pooling.
- [Spring LDAP — PoolingContextSource API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/pool/factory/PoolingContextSource.html): các thuộc tính của pool và vòng đời context.
- [Spring LDAP — LdapTemplate](https://docs.spring.io/spring-ldap/reference/): thao tác đọc, tìm kiếm và quản lý context trong Spring LDAP.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): Bind, Search và mã kết quả LDAP.
- [RFC 4513 — Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): bảo mật xác thực, bind và các yêu cầu bảo vệ credential.
