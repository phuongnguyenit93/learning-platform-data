# Tách context chỉ đọc và context đọc–ghi

Khi ứng dụng dùng **Spring Data LDAP** để tra cứu danh tính và quản lý entry, phần lớn yêu cầu có thể chỉ là **đọc** người dùng hoặc nhóm, trong khi một tỷ lệ nhỏ cần **ghi**: thêm entry, sửa thuộc tính, đổi DN hoặc xóa entry. Nếu mọi yêu cầu đều dùng cùng một tài khoản LDAP có quyền sửa dữ liệu, một lỗi lập trình ở đường đọc có thể biến thành thao tác ghi ngoài ý muốn. Nếu mọi kết nối cùng dùng một pool, truy vấn tìm kiếm tải lớn còn có thể chiếm hết kết nối cần cho thao tác cập nhật quan trọng.

Trong chương **Pool kết nối**, bài học này hướng dẫn **tách context chỉ đọc và context đọc–ghi** bằng cách thiết kế hai đường truy cập Spring LDAP với danh tính bind, quyền ACL, `ContextSource`, `LdapTemplate` và tài nguyên pool độc lập. Người học sẽ áp dụng điều đó khi ánh xạ LDAP entry phân cấp thành đối tượng Java, truy vấn repository/`LdapTemplate`, xử lý CRUD, giới hạn base DN và LDAP filter, bảo vệ kết nối cũng như kiểm thử với directory.

> **Nguyên tắc cốt lõi:** tên API `getReadOnlyContext()` và `getReadWriteContext()` mô tả **cách yêu cầu context** trong Spring LDAP; nó **không tự tạo hai tài khoản LDAP với ACL khác nhau**. Ranh giới bảo mật có thể kiểm chứng phải đến từ **tài khoản bind và ACL thực sự được LDAP server thực thi**.

## 1. Hai loại thao tác cần được phân luồng

Giả sử ứng dụng quản lý tài khoản nhân viên có hai nghiệp vụ:

- `GET /directory/users/u1001`: đọc thông tin người dùng, nhóm và trạng thái.
- `PATCH /directory/users/u1001/email`: cập nhật `mail` sau khi đã xác thực và phân quyền người thực hiện.

Directory thử nghiệm có cấu trúc:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=u1001    ← inetOrgPerson: uid, cn, sn, mail, ...
│   └── uid=u1002
├── ou=groups
│   └── cn=developers
└── ou=service-accounts
    ├── cn=svc-reader  ← chỉ đọc entry/thuộc tính đã duyệt
    └── cn=svc-writer  ← được sửa một tập entry/thuộc tính được duyệt
```

Ví dụ một entry người dùng:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
mail: an.nguyen@example.org
```

Trong ví dụ, `dn` là địa chỉ entry trong cây, còn `objectClass` và schema quy định các thuộc tính hợp lệ. Đổi `mail` khác với đổi RDN `uid=u1001` hoặc chuyển entry sang OU khác. **Đường đọc không cần quyền ghi chỉ để dùng chung DTO với đường cập nhật.**

| Nhu cầu | Đường truy cập nên dùng | Quyền LDAP tối thiểu gợi ý |
|---|---|---|
| Search người dùng theo UID | **Read** | Search/read các thuộc tính cần thiết trong `ou=people` |
| Lookup user theo DN | **Read** | Read đúng entry và thuộc tính |
| Đọc nhóm/quyền | **Read** | Read nhóm và membership theo ACL đã duyệt |
| Đổi `mail` của nhân viên | **Write** | Modify thuộc tính `mail` trên tập entry được phép |
| Tạo tài khoản | **Write, theo luồng provisioning** | Add entry dưới OU được phép, đúng schema |
| Đổi RDN/OU, xóa tài khoản | **Write đặc quyền cao hơn** | Rename/delete chỉ khi quy trình phê duyệt riêng cho phép |

Tài khoản `svc-writer` **không nên mặc nhiên có toàn quyền quản trị directory**. Nếu nghiệp vụ chỉ sửa email, hãy giới hạn quyền `modify` ở `mail` và những entry phù hợp. Cách biểu đạt ACL chi tiết khác nhau giữa OpenLDAP, Active Directory và các sản phẩm LDAP khác.

## 2. Ba lớp “chỉ đọc” cần phân biệt

Trong Spring LDAP, interface `ContextSource` cung cấp các cách lấy context, ví dụ:

```java
DirContext readerContext = contextSource.getReadOnlyContext();
DirContext writerContext = contextSource.getReadWriteContext();
```

Hai phương thức trên hữu ích cho cách Spring LDAP **phân biệt mục đích** khi thực thi thao tác. Tuy nhiên:

1. **Loại context trong API** (`readOnly`/`readWrite`) không phải bằng chứng LDAP server áp dụng quyền khác nhau. Một `LdapContextSource` thông thường có thể sử dụng **cùng user DN và password** khi tạo cả hai context.
2. **ACL của directory** mới quyết định tài khoản bind được đọc, thêm, sửa hoặc xóa entry/thuộc tính nào. Muốn chặn ghi từ luồng đọc, hãy kiểm thử `modify` bằng chính tài khoản đọc và xác nhận **server từ chối**.
3. **Phân luồng ở ứng dụng** giúp lập trình viên chỉ được tiêm bean đọc vào code chỉ đọc. Đây là lớp phòng vệ bổ sung, nhưng không thể thay thế ACL server nếu bean writer bị sử dụng sai.

Không nhầm `DirContext.READ_ONLY` hoặc tên method Java với chính sách **read-only replica**. Một replica LDAP có thể nhận search nhưng từ chối write do vai trò máy chủ; đó là quy tắc triển khai/phân quyền của directory, không phải kết quả tự động khi gọi `getReadOnlyContext()`.

### Tách theo mục đích không nhất thiết đồng nghĩa tách theo máy chủ

Hai đường kết nối có thể cùng dùng `ldap.example.org` nhưng **khác tài khoản bind và pool**. Nếu hạ tầng có read replica và node nhận ghi riêng, ứng dụng còn có thể cấu hình **endpoint khác nhau**. Quyết định chọn endpoint thuộc kiến trúc directory; không mặc định mọi LDAP server đều có mô hình primary/replica như một cơ sở dữ liệu quan hệ.

## 3. Kiến trúc đề xuất: hai ContextSource và hai pool

```text
                     Spring Boot application
                              │
              ┌───────────────┴─────────────────┐
              │                                 │
        ReadDirectoryService              WriteDirectoryService
              │                                 │
        readLdapTemplate                    writeLdapTemplate
              │                                 │
        [read pool, nếu dùng]               [write pool, nếu dùng]
              │                                 │
        readContextSource                   writeContextSource
              │                                 │
        bind: svc-reader                    bind: svc-writer
              │                                 │
       LDAP endpoint đọc                  LDAP endpoint ghi
              └───────────────┬─────────────────┘
                              │
                 Directory schema + ACL
```

Trong sơ đồ này, **pool đọc không tái sử dụng context đã bind bằng `svc-writer`**, và **pool ghi không mượn context đã bind bằng `svc-reader`**. Tách pool vừa giúp bảo vệ danh tính bind, vừa tạo khả năng đặt giới hạn tài nguyên khác nhau cho hai workload.

**Tại sao nên tách pool?** Giả sử 100 truy vấn đọc đồng thời giữ nhiều connection. Nếu cùng pool với thao tác cập nhật mật khẩu hoặc trạng thái tài khoản, cập nhật có thể phải đợi hết lượt. Hai pool cho phép đặt ngưỡng, hàng đợi và timeout độc lập; tuy nhiên **không giảm tổng số connection được LDAP server cho phép**. Cần tính tổng tài nguyên trên mọi instance ứng dụng và mọi tài khoản bind.

## 4. Ma trận quyền là bước đầu tiên, không phải chỉnh pool

Trước khi viết cấu hình Java, hãy thống nhất danh sách nghiệp vụ/thuộc tính và quyền:

| Nhánh/thuộc tính | `svc-reader` | `svc-writer` | Ghi chú |
|---|---|---|---|
| `ou=people`: `uid,cn,sn,mail` | Đọc/tìm kiếm | Đọc cần thiết + sửa `mail` | Chỉ sửa trên tập entry thuộc phạm vi được duyệt |
| `ou=groups`: `cn,member` | Đọc nếu nghiệp vụ cần | Không ghi nếu không có provisioning nhóm | Membership ảnh hưởng phân quyền |
| `ou=service-accounts` | Không đọc secret | Không thay mật khẩu tài khoản khác | Tách vùng nhạy cảm khỏi các query phổ thông |
| `userPassword`, `unicodePwd` | Không đọc | Không sửa trong workflow email | Thuộc tính mật khẩu có quy tắc riêng theo server |
| Xóa/đổi DN/tạo account | Không | Theo quy trình và account chuyên biệt nếu cần | Không suy từ quyền sửa email sang quyền quản trị |

Một số directory có quyền **search**, **compare** và **read** được kiểm soát riêng; truy vấn có thể trả rỗng khi thuộc tính không được phép xét hoặc entry bị che. **Tài khoản chỉ đọc không đồng nghĩa mọi thuộc tính đều được đọc.**

Hai lớp kiểm soát phải đồng thời tồn tại:

- **Authorization trong ứng dụng:** ai được gọi API thay email, ai được cập nhật tài khoản nào; lựa chọn context không được phụ thuộc hoàn toàn vào trường `mode=write` từ client.
- **Authorization tại LDAP server:** khi bean writer bị gọi nhầm hoặc logic ứng dụng lỗi, ACL vẫn ngăn ghi ngoài tập quyền.

## 5. Cấu hình hai `LdapContextSource` độc lập

Ví dụ Spring Boot dưới đây dùng **thuộc tính riêng** của ứng dụng để cấu hình hai source. Cả hai cùng có suffix `dc=example,dc=org` nhưng sử dụng hai principal khác nhau.

```yaml
app:
  ldap:
    base: dc=example,dc=org
    read:
      url: ldaps://ldap-read.example.org:636
      bind-dn: cn=svc-reader,ou=service-accounts,dc=example,dc=org
      password: ${LDAP_READ_PASSWORD}
    write:
      url: ldaps://ldap-write.example.org:636
      bind-dn: cn=svc-writer,ou=service-accounts,dc=example,dc=org
      password: ${LDAP_WRITE_PASSWORD}
```

Đây là **cấu hình minh họa**. Hai URL chỉ có thể trỏ tới hai endpoint khác nhau khi hạ tầng xác nhận endpoint đọc và ghi được phân vai phù hợp. Dùng **LDAPS với xác minh chứng chỉ**; nếu dùng StartTLS thì URL phải là `ldap://` và cấu hình **TLS authentication strategy** phù hợp, không chỉ đổi scheme.

Tạo các bean tách biệt (ví dụ dùng các API Spring LDAP phổ biến):

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryContextConfiguration {

    @Bean("readContextSource")
    public LdapContextSource readContextSource(
            @Value("${app.ldap.read.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.read.bind-dn}") String userDn,
            @Value("${app.ldap.read.password}") String password) {
        return createSource(url, base, userDn, password);
    }

    @Bean("writeContextSource")
    public LdapContextSource writeContextSource(
            @Value("${app.ldap.write.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.write.bind-dn}") String userDn,
            @Value("${app.ldap.write.password}") String password) {
        return createSource(url, base, userDn, password);
    }

    private static LdapContextSource createSource(
            String url, String base, String userDn, String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(userDn);
        source.setPassword(password);
        source.setPooled(false); // Không bật native JNDI LDAP pooling.
        return source;
    }

    @Bean("readLdapTemplate")
    public LdapTemplate readLdapTemplate(
            @Qualifier("readContextSource") ContextSource source) {
        return new LdapTemplate(source);
    }

    @Bean("writeLdapTemplate")
    public LdapTemplate writeLdapTemplate(
            @Qualifier("writeContextSource") ContextSource source) {
        return new LdapTemplate(source);
    }
}
```

**Vì sao chưa tạo pool ngay?** Ví dụ khởi đầu với **hai context source và hai template không pool** để bạn có thể kiểm tra riêng credential/ACL/endpoint. Sau khi chứng minh luồng đọc và ghi đúng, mới thêm pooling bao quanh từng source để tránh vừa sửa lỗi kết nối vừa sửa lỗi pool cùng lúc.

Spring container gọi bước khởi tạo của `LdapContextSource` trong lifecycle bean phù hợp. Nếu bạn tự tạo source **ngoài Spring container**, phải hoàn tất thuộc tính và gọi `afterPropertiesSet()` trước khi sử dụng theo contract API. Khi tạo hai `ContextSource` và hai `LdapTemplate`, có thể có nhiều ứng viên để autowire theo kiểu; vì vậy hãy dùng `@Qualifier` ở mọi điểm tiêu thụ, đồng thời kiểm tra cơ chế tự cấu hình bean LDAP của Spring Boot phiên bản đang dùng.

**Không cho Spring Boot tự chọn nhầm một `LdapTemplate` mặc định** qua `@Primary` chỉ để tránh lỗi injection rồi vô tình gửi tác vụ `save` vào source đọc. Tốt nhất là điểm truy cập LDAP phải nói rõ mục đích và bean được chọn.

## 6. Gọi luồng đọc: luôn dùng bean chỉ đọc

Khi chỉ cần đọc dữ liệu, service phải phụ thuộc **`readLdapTemplate`**:

```java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

record PersonView(String uid, String cn, String mail) {}

@Service
public class ReadDirectoryService {
    private final LdapTemplate ldap;

    public ReadDirectoryService(
            @Qualifier("readLdapTemplate") LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public List<PersonView> findByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid is required");
        }

        LdapQuery q = query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        AttributesMapper<PersonView> mapper = attrs ->
                new PersonView(readText(attrs, "uid"),
                               readText(attrs, "cn"),
                               readText(attrs, "mail"));

        return ldap.search(q, mapper);
    }

    private static String readText(Attributes attrs, String name)
            throws NamingException {
        Attribute value = attrs.get(name);
        return value == null ? null : (String) value.get();
    }
}
```

Giả sử context base là `dc=example,dc=org`; `.base("ou=people")` sẽ chọn nhánh tương đối với base đó. Filter builder xử lý escaping giá trị LDAP filter; **không nối `"(uid=" + uid + ")"`** từ input không tin cậy.

Đây là một phép **search theo thuộc tính**, không phải lookup theo DN. Nếu đã biết DN chính xác, có thể dùng `ldap.lookup(relativeDn, mapper)` với DN được xây bằng `LdapNameBuilder`. Trong cả hai trường hợp, query vẫn phải tuân theo ACL và giới hạn dữ liệu ứng dụng được phép trả về.

`PersonView` là DTO minh họa. Với thuộc tính `objectClass`, `member` đa trị, dữ liệu binary hoặc giá trị không phải `String`, phải dùng mapper phù hợp schema. Một thành công ở lớp TLS không bảo đảm `mail` sẽ luôn tồn tại hoặc đọc được.

## 7. Gọi luồng ghi: bean riêng và quyền nghiệp vụ riêng

Ví dụ luồng cập nhật `mail` cho một entry đã biết RDN dạng `uid` dưới `ou=people`. Service **chỉ được gọi sau khi kiểm tra quyền của người yêu cầu và danh tính tài khoản đích**; ví dụ chỉ minh họa phần LDAP:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class WriteDirectoryService {
    private final LdapTemplate ldap;

    public WriteDirectoryService(
            @Qualifier("writeLdapTemplate") LdapTemplate ldap) {
        this.ldap = ldap;
    }

    // Chỉ tầng nghiệp vụ đã xác thực + phân quyền mới được gọi method này.
    public void replaceMail(String approvedUid, String approvedMail) {
        if (approvedUid == null || approvedUid.isBlank() ||
                approvedMail == null || approvedMail.isBlank()) {
            throw new IllegalArgumentException("uid/mail required");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", approvedUid)
                .build();

        ModificationItem replace = new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("mail", approvedMail));

        ldap.modifyAttributes(dn, new ModificationItem[] {replace});
    }
}
```

Các điểm then chốt:

- `writeLdapTemplate` được tạo từ `writeContextSource`, nên thao tác LDAP dùng principal writer đã cấu hình.
- `LdapNameBuilder` xây **DN tương đối với context base** và escape giá trị RDN. Không tự ghép `"uid=" + value` hoặc cho người dùng gửi DN ngoài OU được phép.
- Ví dụ có giả định **RDN thật sự là `uid`**. Trên Active Directory, user có thể có RDN `CN=...`; không áp dụng máy móc công thức này khi DN thật khác.
- `REPLACE_ATTRIBUTE` thay giá trị `mail`; hãy kiểm tra thuộc tính, schema, chính sách ghi và ACL của directory. Không dùng logic cập nhật email để tự động sửa mật khẩu, trạng thái tài khoản hoặc group membership.
- `writeContextSource` không cần quyền xóa entry hoặc thay mọi thuộc tính. Server phải từ chối thao tác vượt quyền ngay cả khi code gửi được yêu cầu.

**Quan trọng:** không chỉ dựa vào hai bean `ReadDirectoryService` và `WriteDirectoryService` để bảo mật. Nếu write service bị gọi từ controller không phân quyền, nó vẫn có thể thực hiện thao tác trong phạm vi tài khoản writer. Cần kết hợp kiểm soát ở API/service, ACL và audit.

## 8. Tích hợp `LdapRepository` mà không làm lẫn đường đọc–ghi

Repository của **Spring Data LDAP** rất tiện để ánh xạ entry qua ODM:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String mail;

    public DirectoryPerson() {}
    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) { this.commonName = commonName; }
    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }
    public String getMail() { return mail; }
    public void setMail(String mail) { this.mail = mail; }
}
```

Với `LdapRepository<DirectoryPerson>`, các phương thức `findBy...`, `findById`, `save`, `delete` có thể cùng thuộc một interface. Do đó **không được nghĩ rằng cứ đặt tên repository là `ReadOnlyRepository` thì `save()` sẽ bị khóa**. Một repository vẫn phụ thuộc vào `LdapTemplate`/context source được repository factory chọn.

Các cách kiểm soát:

1. **Đường đọc:** có thể khai báo interface repository chỉ công bố các method đọc cần dùng (ví dụ dựa trên `Repository<DirectoryPerson, Name>`, không bắt buộc kế thừa tất cả CRUD). Kiểm chứng khả năng tạo query method ở Spring Data LDAP phiên bản thực tế.
2. **Đường ghi:** đặt facade/service riêng với method nghiệp vụ cụ thể (như `replaceMail`), không để controller dùng raw `LdapRepository.save` theo dữ liệu request chưa kiểm soát.
3. **Wiring:** nếu dùng repository factory, cấu hình rõ bean `LdapTemplate` mà tập repository sử dụng (các phiên bản Spring Data LDAP có cơ chế cấu hình repository cụ thể). Tránh giả định `@Qualifier` trên một `LdapTemplate` service sẽ tự điều hướng mọi repository bean.
4. **An toàn:** ngay cả khi repository đọc vô tình có method ghi, LDAP ACL của `svc-reader` vẫn phải từ chối ghi.

Nếu ứng dụng cần hai nhóm repository thực sự tách biệt, nên kiểm chứng khả năng đăng ký hai cấu hình repository và template ref theo **phiên bản Spring Data LDAP** đang dùng. Ví dụ ở phần 5–7 dùng `LdapTemplate` được qualify tường minh để ranh giới đọc–ghi dễ quan sát và kiểm thử.

## 9. Từ hai ContextSource đến hai pool kết nối

Sau khi cấu hình và ACL hoạt động đúng khi **chưa có pool**, có thể thêm pooling để giảm chi phí tạo context/kết nối/bind/TLS nhiều lần.

**Mô hình đúng:**

```text
readLdapTemplate  → read PoolingContextSource  → readContextSource
writeLdapTemplate → write PoolingContextSource → writeContextSource
```

Một pool không nên chứa context từ **các danh tính bind khác nhau** theo kiểu không được kiểm soát. Tối thiểu, hãy phân nhóm kết nối theo **endpoint, cấu hình TLS, danh tính bind, cơ chế xác thực và quyền**. Vì vậy, không lấy một pool dùng tài khoản writer rồi cho cả reader/writer dùng chung chỉ để giảm số socket.

### Chọn loại pooling

| Cơ chế | Đặc điểm | Lưu ý |
|---|---|---|
| Không pool | Mỗi context theo vòng đời thông thường | Dễ xác minh ACL, chi phí kết nối có thể cao |
| **Native JNDI LDAP pooling** | Cơ chế pool của LDAP provider JNDI | Không luôn phù hợp StartTLS/vòng đời bind; ít tùy chọn giám sát theo nghiệp vụ |
| **Spring LDAP PoolingContextSource** | Wrapper pool cho context theo API Spring LDAP, thường dựa Commons Pool/Pool2 ở phiên bản thích hợp | Cần đúng module, cấu hình, validator, policy và hai instance pool tách biệt |
| Pool tại proxy/server | Có thể tái sử dụng backend connection theo proxy | Không thay thế việc bảo đảm isolation danh tính/ACL và routing chính xác |

Đặc biệt, **khi sử dụng StartTLS qua `DirContextAuthenticationStrategy`**, không nên bật **native JNDI LDAP pooling**. Cần dùng giải pháp pooling có vòng đời TLS/context phù hợp và kiểm thử trực tiếp với server. Với LDAPS cũng phải xác minh chứng chỉ, hostname và cách refresh credential.

### Gắn pool vào từng source

API cấu hình chi tiết của `PoolingContextSource`, các setter giới hạn pool và namespace `org.springframework.ldap.pool...` hoặc `org.springframework.ldap.pool2...` **phụ thuộc phiên bản Spring LDAP và module pooling được sử dụng**. Vì vậy, ví dụ dưới đây mô tả **quan hệ bean cần đạt**, không phải class Java hoàn chỉnh để copy vào mọi phiên bản:

```text
readSource  --wrap with--> readPool  --inject into--> readLdapTemplate
writeSource --wrap with--> writePool --inject into--> writeLdapTemplate

readPool:
  bind principal = svc-reader
  maxTotal       = 8      # giá trị ví dụ, chọn theo tải thực tế
  borrow timeout = giới hạn hữu hạn
  validate       = khi mượn/định kỳ theo khả năng provider

writePool:
  bind principal = svc-writer
  maxTotal       = 3      # ví dụ: nhỏ hơn nhưng có phần tài nguyên riêng
  borrow timeout = giới hạn hữu hạn
  validate       = khi mượn/định kỳ theo khả năng provider
```

Hãy cấu hình **`LdapTemplate` nhận wrapper pool** (thay vì raw source) khi đã xác nhận phiên bản và làm lại kiểm thử ACL. Nếu một pool tự phân biệt read-only/read-write context bên trong thì vẫn cần xác nhận danh tính bind và ranh giới quyền; điều đó **không thay thế** việc tách hai source với hai credential.

Không có con số `maxTotal=8` hoặc `3` đúng cho mọi ứng dụng. Hãy đo thời gian giữ context, số request đồng thời, giới hạn connection của LDAP server, tỷ lệ đọc/ghi và tài nguyên của từng instance. Nếu có nhiều instance ứng dụng, **tổng số kết nối tiềm năng** là tổng cấu hình pool của tất cả instance, không chỉ một node.

## 10. Các bất biến cần giữ khi pool vận hành

Một thiết kế pooling an toàn phải duy trì những bất biến sau:

1. **Danh tính:** context mượn từ read pool luôn thực hiện LDAP operations dưới danh tính được phép đọc; write pool dùng principal được phép ghi.
2. **Endpoint:** read pool chỉ kết nối tới endpoint đọc đã duyệt; write pool chỉ tới endpoint được phép ghi, kể cả sau failover.
3. **TLS:** từng kết nối thực sự được bảo vệ và xác minh đúng chứng chỉ; pool không làm bỏ qua TLS handshake bắt buộc của kết nối mới.
4. **Vòng đời:** context hỏng hoặc hết hạn không được trả lại như còn hợp lệ; sau TLS/bind failure không phát cho request khác.
5. **Quyền:** không vì pool đã bind thành công mà bỏ qua phân quyền nghiệp vụ cho từng thao tác.
6. **Giới hạn tài nguyên:** có ngưỡng mượn và thời gian chờ hữu hạn; nếu hết pool, phải trả lỗi hạ tầng có kiểm soát thay vì đợi vô hạn.
7. **Credential rotation:** khi secret bị đổi, context cũ trong pool có thể còn phiên đã xác thực; cần chính sách làm mới/drain pool và thử bind bằng secret mới.

### Không pool context xác thực từng người dùng một cách tùy tiện

Nếu ứng dụng kiểm tra mật khẩu LDAP cho từng end user bằng cách tạo context với danh tính người đó, **không đẩy các context này vào pool service account chung**. Một kết nối còn bind bằng user A được trao cho request user B là lỗi cô lập danh tính nghiêm trọng. Luồng kiểm tra credential từng người dùng cần thiết kế vòng đời riêng, không nhầm với hai pool cố định `svc-reader`/`svc-writer`.

Trong một số hệ thống, LDAP bind có thể được dùng để xác minh mật khẩu người dùng nhưng **không nên giữ và tái sử dụng quyền của người dùng cuối** cho những thao tác không liên quan nếu chưa có mô hình phân quyền và pooling được thiết kế tường minh.

## 11. Read replica, write endpoint và tính nhất quán

Tách context cho phép đọc từ một endpoint và ghi tới endpoint khác, nhưng không có nghĩa dữ liệu vừa ghi sẽ hiển thị ngay ở điểm đọc.

```text
writeTemplate → writable directory node → replication → read replica
       │                                     (có thể trễ)
       └──────── trả kết quả MODIFY thành công

readTemplate  → read replica → có thể vẫn trả mail cũ trong một khoảng ngắn
```

Đây là vấn đề **read-after-write consistency**. Ví dụ luồng cập nhật email thành công trên endpoint ghi rồi ngay lập tức đọc từ replica có thể thấy email cũ, tùy topology và cơ chế replication.

Các chính sách có thể áp dụng:

- **Read-your-writes theo yêu cầu:** sau khi sửa, đọc/xác minh trên endpoint ghi (hoặc node được bảo đảm đã có thay đổi), sau đó cho phép các truy vấn thông thường đi qua read endpoint.
- **Chấp nhận eventual consistency:** giao diện có thể hiển thị trạng thái “đang đồng bộ” và chỉ thông báo dữ liệu đã sẵn sàng khi thỏa quy tắc nghiệp vụ.
- **Không chấp nhận độ trễ cho quyền bảo mật:** nếu vừa vô hiệu hóa tài khoản hoặc thu hồi nhóm, cần cơ chế đồng bộ/xác thực bảo đảm yêu cầu an toàn; không dựa đơn thuần vào replica có thể trễ.

Thao tác **modify trên một LDAP entry** không nên bị diễn giải thành một transaction ACID xuyên nhiều entry. Nếu một workflow cập nhật người dùng rồi cập nhật nhiều nhóm, phải thiết kế kiểm tra kết quả và cách khôi phục khi chỉ thành công một phần.

**Đối với Active Directory**, khả năng ghi ở domain controller, Global Catalog, quyền ghi và phạm vi attribute có những quy tắc riêng. Global Catalog thường cung cấp tập thuộc tính một phần cho tìm kiếm cross-domain; không được mặc định dùng một GC endpoint để ghi mọi entry.

## 12. Tối ưu đọc–ghi bằng số liệu, không bằng cảm tính

Để biết nên tăng read pool hay write pool, cần đo được **thời gian, thông lượng và số LDAP operation thực tế**:

| Chỉ số | Đọc | Ghi | Vì sao quan trọng |
|---|---|---|---|
| Thời gian chờ mượn context | p50/p95/p99 | p50/p95/p99 | Biết tắc ở pool hay LDAP server |
| Thời gian LDAP operation | Search/lookup | Modify/add/delete/rename | Phân biệt độ chậm của từng workload |
| Active/idle/waiting | Theo read pool | Theo write pool | Chẩn đoán cạn tài nguyên và overprovision |
| Connection/bind/TLS handshake | Theo principal reader | Theo principal writer | Nhìn chi phí mở lại kết nối |
| Error rate | Timeout, ACL, base/filter | ACL, schema, write conflict | Phát hiện cấu hình quyền và lỗi vận hành |
| Operations/s | Search + compare (nếu có) | Modify/add/delete | Giải thích tổng tải directory |
| Replica lag | Nếu đọc replica | Nếu ghi node khác | Giải thích dữ liệu cũ sau ghi |

Ví dụ giả định: trong cửa sổ tải ổn định, read pool thường có 7/8 connection active và p95 chờ borrow tăng, trong khi write pool chỉ dùng 1/3 connection và LDAP server chưa quá tải. Có thể xem xét tăng giới hạn read pool **nếu** hạ tầng cho phép và sau khi loại trừ search quá rộng, N+1 lookup hoặc không trả context đúng vòng đời.

Ngược lại, nếu cả read/write pool ít connection nhưng LDAP server có CPU cao hoặc search filter thiếu index, tăng pool có thể làm tăng áp lực lên server. Nếu writer bị **ACL denied**, mở rộng pool hoàn toàn không giải quyết được lỗi.

**Cách tính dung lượng cần theo tải thực tế:** tổng số connection có thể mở là tổng trên tất cả instance. Một instance có read max 8 và write max 3, triển khai nhiều instance, có thể nhanh chóng chạm giới hạn phía LDAP server. Cần cân nhắc connection limit theo **principal/IP/node**, chính sách hạ tầng và tác động khi failover dồn lưu lượng sang một node.

## 13. Các lỗi cấu hình hay gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Read API thực hiện được MODIFY | `svc-reader` có quyền ghi; hoặc tiêm nhầm writer template | Thử thao tác ghi với account reader; rà soát wiring và ACL |
| Write API báo `Insufficient access rights` | `svc-writer` thiếu quyền attribute/entry cụ thể | Kiểm tra ACL, DN, objectClass và quyền cập nhật đó |
| Repository `save` dùng account reader | Repository factory trỏ tới read template mặc định | Xác định `LdapTemplate`/context source được repository dùng |
| GET tài khoản đôi khi rất chậm | Read pool bị cạn, search rộng hoặc server chậm | Đo thời gian borrow, operation và metric directory |
| Write thành công, GET vẫn thấy dữ liệu cũ | Đọc từ replica có replication lag | Đối chiếu endpoint, kiểm tra read-your-writes policy |
| Sau đổi password, request đột nhiên lỗi | Pool còn context cũ, credential mới chưa được áp dụng | Drain/rebuild pool và kiểm thử bind bằng secret mới |
| StartTLS lỗi khi pooling | Native JNDI pool không tương thích vòng đời TLS | Tắt native pool, dùng wrapper tương thích và kiểm thử |
| Lỗi không tìm thấy dù LDAP chứa user | Sai base DN/scope/filter hoặc đọc endpoint khác | Xác minh RootDSE, DN thực, search base và ACL |
| Kết nối tăng tới mức server từ chối | Tổng giới hạn pool nhiều instance quá cao | Tính tổng connection và quota directory |
| User A đọc được dữ liệu của user B | Context bind theo người dùng bị tái sử dụng sai | Cô lập credential, bỏ pooling kiểu không an toàn, điều tra quyền |

Khi debug, log **tên luồng read/write, tên bean, endpoint đã định danh, loại operation, mã lỗi và correlation ID**; tránh ghi password, secret, toàn bộ LDAP filter chứa dữ liệu riêng tư hoặc DN nhạy cảm không cần thiết.

## 14. Kiểm thử tích hợp: xác nhận ranh giới bằng directory thật

Mock `LdapTemplate` có thể chứng minh service được tiêm đúng bean, nhưng **không chứng minh LDAP server đã áp ACL chính xác**. Do đó cần kiểm thử tích hợp với directory test có hai service account và dữ liệu/schema gần môi trường vận hành.

| Ca thử | Thiết lập | Kỳ vọng |
|---|---|---|
| Reader search hợp lệ | `svc-reader` đọc `uid=u1001` trong OU được duyệt | Trả đúng entry và các thuộc tính được phép |
| Reader thử modify | Dùng read context gửi thay `mail` trên entry test | LDAP server **từ chối**, dữ liệu không đổi |
| Writer modify hợp lệ | `svc-writer` sửa `mail` của entry được duyệt | Thành công, hậu kiểm đọc thấy giá trị mới theo consistency policy |
| Writer sửa trường cấm | Thử sửa attribute/entry ngoài allowlist | Server từ chối, không chỉ UI chặn |
| Writer delete khi chưa được phép | Thử với entry test và ACL hạn chế | Delete bị từ chối |
| Hai tài khoản có password khác nhau | Cấu hình riêng `readSource`/`writeSource` | Bind đúng danh tính và quyền, không phụ thuộc bean mặc định |
| Cùng UID, sai OU | Entry nằm ngoài `ou=people` | Code không mở rộng tìm kiếm ngoài phạm vi cho phép |
| Input ký tự đặc biệt | UID có RDN/filter cần escape | `LdapNameBuilder`/`LdapQueryBuilder` không làm lệch cấu trúc |
| Read pool bão hòa | Nhiều query đồng thời trong test | Giới hạn borrow timeout, không chiếm hết write pool |
| Server đóng idle connection | Context idle bị ngắt | Pool phát hiện/loại bỏ kết nối hỏng theo policy |
| Password rotation | Thay secret riêng của reader | Chỉ đường reader được làm mới; write path không bị thay credential |
| StartTLS/LDAPS lỗi | Chứng chỉ sai hoặc server từ chối TLS | Không fallback plain LDAP; fail closed |
| Replica lag | Đọc endpoint khác writer | Hậu kiểm tuân theo chính sách nhất quán đã chọn |

Một phép thử quan trọng là **cố ý thử thao tác ghi qua read template ở directory test**. Nếu thao tác thành công, thiết kế **chưa thực sự tách quyền**, dù trong Java đã đặt tên bean `readLdapTemplate` rất rõ. Không chạy phép thử ghi trái phép trên entry production.

### Các bước xác minh có thể làm thủ công ở môi trường test

1. Dùng `ldapwhoami` hoặc công cụ directory tương ứng để xác nhận principal reader và writer qua LDAPS/StartTLS hợp lệ.
2. Với cùng DN và cùng base, dùng reader để search; xác nhận phạm vi và danh sách thuộc tính.
3. Dùng writer thực hiện một thay đổi đã được phê duyệt trên entry giả lập; hậu kiểm từ endpoint ghi và đọc.
4. Dùng reader thử thao tác tương tự trên entry giả lập, kỳ vọng **không được cấp quyền**.
5. Chạy tải có kiểm soát và xem log LDAP server: principal của các search đọc là reader; principal của modify là writer. Một số luồng có thể đọc qua writer để kiểm tra sau ghi nếu chính sách ghi nhận điều đó, nhưng phải có lý do rõ.

Nếu LDAP server che dữ liệu theo ACL và trả kết quả tìm kiếm rỗng, đừng tự kết luận DN không tồn tại. Phân loại lỗi bind, quyền, base, schema và TLS theo từng tầng.

## 15. Bài tập tình huống

Một ứng dụng quản trị danh tính có 20 request tra cứu cho mỗi request cập nhật. Tài khoản LDAP `svc-admin` hiện được cả `GET` lẫn `PATCH` sử dụng. LDAP server có thể phục vụ hai endpoint: `ldap-read.example.org` và `ldap-write.example.org`, cùng suffix `dc=example,dc=org`.

Yêu cầu:

- Đường `GET` chỉ được đọc `uid,cn,sn,mail` ở `ou=people`.
- Đường `PATCH` chỉ được cập nhật `mail` của tài khoản đã được phép.
- Không endpoint nào được tự ý xóa user, đổi DN hoặc sửa nhóm.
- Thao tác cập nhật email thành công phải có cách kiểm tra kết quả không bị nhầm bởi replication lag.

Hãy trả lời:

1. Nên có bao nhiêu `LdapContextSource`, `LdapTemplate` và pool? Phân biệt credential từng đường.
2. Chỉ gọi `getReadOnlyContext()` trên source dùng `svc-admin` có đáp ứng yêu cầu bảo mật không? Vì sao?
3. Những quyền LDAP nào cần đặt cho `svc-reader` và `svc-writer`? Làm sao kiểm chứng ACL thực sự được áp dụng?
4. Khi các query đọc làm pool cạn, vì sao hai pool độc lập giúp giảm ảnh hưởng tới nghiệp vụ ghi nhưng không làm biến mất giới hạn tổng connection trên server?
5. Vì sao `repository.save()` không nên xuất hiện trực tiếp trong REST controller xử lý email?
6. Sau khi sửa email ở endpoint ghi, khi nào đọc ở replica có thể chưa thấy giá trị mới? Hãy đề xuất cách hậu kiểm phù hợp.

**Gợi ý đối chiếu:** tạo hai context source với hai bind account và hai template tách biệt; sau khi xác minh quyền, thêm hai pool nếu cần. Reader không có quyền modify, writer chỉ sửa những attribute/entry được duyệt. `getReadOnlyContext()` không tự cấp lại ACL khi principal vẫn là admin. Tầng nghiệp vụ kiểm tra quyền trước khi gọi write service. Để kiểm tra ngay sau ghi, có thể đọc lại từ endpoint ghi hoặc sử dụng cơ chế bảo đảm consistency được directory hỗ trợ.

## 16. Checklist triển khai và tổng kết

Trước khi đưa thiết kế vào vận hành, kiểm tra:

1. **Mục đích và danh tính:** hai luồng read/write có tài khoản bind độc lập, quyền tối thiểu, secret tách biệt và cơ chế rotation.
2. **Wiring:** các service và repository được gắn đúng `LdapTemplate`/`ContextSource`; không phụ thuộc một bean mặc định dễ nhầm.
3. **Directory model:** base DN, DN/RDN, OU, `objectClass`, schema và LDAP filter builder đúng cho từng thao tác.
4. **Pool:** chỉ thêm sau khi đường truy cập không pool hoạt động; hai pool tách biệt, timeout/validation hợp lý, tổng connection không vượt khả năng directory.
5. **TLS:** LDAPS hoặc StartTLS với xác thực chứng chỉ; không dùng native JNDI pooling tùy tiện với StartTLS.
6. **An toàn ghi:** write service kiểm tra quyền nghiệp vụ, ACL ở LDAP server giới hạn thuộc tính, audit mọi sửa đổi, không mở sẵn delete/rename.
7. **Nhất quán:** biết endpoint nào nhận ghi, độ trễ nhân bản và phương án read-after-write cho trường hợp cần thiết.
8. **Đo lường và kiểm thử:** đo borrow wait/p95, LDAP operations, lỗi bind/ACL; thử đọc, ghi được phép, ghi bị từ chối, lỗi TLS, hết pool và đổi credential.

**Kết luận:** tách context chỉ đọc và đọc–ghi trong Spring Data LDAP không chỉ là đặt hai tên bean. Cần tạo **hai ranh giới truy cập có thể kiểm chứng** từ service → `LdapTemplate`/repository → `ContextSource` → pool → principal LDAP → ACL ở directory. Khi các lớp này thống nhất, ứng dụng vừa giảm nguy cơ ghi ngoài quyền, vừa kiểm soát được tài nguyên kết nối và xử lý chính xác khác biệt giữa đường đọc và đường ghi.
