# Root DSE, naming context và base DN trong LDAP

## 1. Vì sao cần phân biệt ba khái niệm này?

Khi bắt đầu kết nối một dịch vụ thư mục LDAP bằng **Spring LDAP**, ba câu hỏi thường xuất hiện:

1. Máy chủ đang cung cấp những thông tin và khả năng nào?
2. Máy chủ quản lý những vùng tên nào của cây thư mục?
3. Ứng dụng phải bắt đầu tìm kiếm ở nhánh nào?

Ba câu hỏi tương ứng với **Root DSE**, **naming context** và **base DN**. Chúng liên quan nhưng không đồng nghĩa. Chọn sai base DN có thể khiến truy vấn không trả về người dùng, chỉ thấy một phần dữ liệu hoặc vô tình tìm kiếm quá rộng. Nhầm Root DSE với một entry người dùng thông thường lại dẫn đến thao tác đọc sai DN và hiểu nhầm kết quả.

Trong Spring LDAP, các khái niệm này là nền tảng để cấu hình `ContextSource`, dùng `LdapTemplate` hoặc `LdapClient`, xây bộ lọc tìm kiếm, ánh xạ entry bằng ODM, xác thực và kiểm thử truy cập thư mục an toàn.

## 2. Bản đồ khái niệm: Root DSE, naming context và base DN

### 2.1. Root DSE: entry mô tả chính máy chủ LDAP

**Root DSE** (*Root Directory Server-specific Entry*) là entry đặc biệt mà máy chủ LDAP công bố để mô tả dịch vụ và những khả năng hỗ trợ. DN của Root DSE là **chuỗi rỗng** (`""`). Đây không phải entry `dc=example,dc=org`, không phải `ou=people` và cũng không phải một nhóm hay người dùng trong cây thư mục.

Ứng dụng thường đọc Root DSE để khám phá các hậu tố thư mục (*naming contexts*) và thông tin về giao thức, extension, control hay vị trí schema. Các thuộc tính của Root DSE phần lớn là thuộc tính vận hành (*operational attributes*), vì vậy khi truy vấn nên yêu cầu rõ tên thuộc tính thay vì giả định chúng xuất hiện trong kết quả mặc định.

Ví dụ minh họa dữ liệu **có thể** được máy chủ trả về:

```ldif
dn:
namingContexts: dc=example,dc=org
supportedLDAPVersion: 3
subschemaSubentry: cn=Subschema
supportedControl: 1.2.840.113556.1.4.319
```

Trong ví dụ này, dòng `dn:` rỗng chính là DN của Root DSE. OID ở `supportedControl` minh họa một control phân trang; nó cho biết khả năng được máy chủ công bố, không bảo đảm tài khoản hiện tại được phép sử dụng tính năng trong mọi trường hợp.

### 2.2. Naming context: vùng tên do máy chủ quản lý

**Naming context** là một vùng của cây tên thư mục mà máy chủ cung cấp nội dung; DN ở đỉnh vùng đó được gọi là *naming-context root* hoặc *suffix*. Root DSE có thể công bố các DN này qua thuộc tính `namingContexts`, mỗi giá trị là một DN.

Giả sử Root DSE trả về:

```ldif
namingContexts: dc=example,dc=org
```

Máy chủ đang công bố vùng tên bắt đầu ở `dc=example,dc=org`. Bên trong đó có thể chứa các đơn vị tổ chức, người dùng và nhóm. Một máy chủ cũng có thể công bố **nhiều** naming context, chẳng hạn vùng dữ liệu ứng dụng, vùng cấu hình và vùng schema, tùy sản phẩm và cách triển khai. Không nên mặc định giá trị đầu tiên của `namingContexts` là nhánh người dùng cần tìm.

### 2.3. Base DN: điểm bắt đầu của một thao tác LDAP

**Base DN** (*base distinguished name*) là DN mà **ứng dụng hoặc từng yêu cầu tìm kiếm** chọn làm gốc để truy vấn. Base DN phải phù hợp với dữ liệu muốn thao tác và phạm vi mà máy chủ cho phép. Nó có thể trùng naming-context root, nhưng thường là một nhánh **bên dưới** naming context.

Ví dụ:

```text
Root DSE: DN = ""                 (entry mô tả máy chủ)
     |
     +-- naming context: dc=example,dc=org
             |
             +-- ou=people,dc=example,dc=org      <-- base DN tìm người dùng
             |      |
             |      +-- uid=alice,ou=people,dc=example,dc=org
             |      +-- uid=bob,ou=people,dc=example,dc=org
             |
             +-- ou=groups,dc=example,dc=org      <-- base DN tìm nhóm
                    |
                    +-- cn=developers,ou=groups,dc=example,dc=org
```

Sơ đồ giúp hình dung quan hệ phân cấp; **Root DSE không phải entry cha LDAP thông thường của `dc=example,dc=org`**. DN rỗng dùng để truy cập entry đặc biệt, còn naming context đánh dấu gốc của vùng dữ liệu được phục vụ.

| Khái niệm | Đại diện trong ví dụ | Ý nghĩa thực tế |
| --- | --- | --- |
| Root DSE | `""` (DN rỗng) | Đọc thông tin và khả năng máy chủ |
| Naming-context root | `dc=example,dc=org` | Gốc một vùng dữ liệu máy chủ cung cấp |
| Base DN ứng dụng | `ou=people,dc=example,dc=org` | Gốc được chọn để tìm người dùng |
| DN của entry | `uid=alice,ou=people,dc=example,dc=org` | Định danh duy nhất của một entry trong cây |
| RDN của entry | `uid=alice` | Thành phần tên phân biệt entry với các entry cùng cha |

> **Quy tắc nhớ:** Root DSE trả lời “máy chủ có gì?”, naming context trả lời “máy chủ phục vụ vùng tên nào?”, base DN trả lời “truy vấn này bắt đầu ở đâu?”.

## 3. Đọc Root DSE để khám phá máy chủ

### 3.1. Những thuộc tính thường gặp

| Thuộc tính Root DSE | Công dụng | Lưu ý |
| --- | --- | --- |
| `namingContexts` | Danh sách hậu tố/vùng tên được máy chủ công bố | Có thể có nhiều giá trị; phạm vi hiển thị tùy máy chủ và quyền |
| `supportedLDAPVersion` | Phiên bản LDAP được hỗ trợ, thường là `3` | Không thay thế kiểm tra khả năng của từng extension |
| `supportedControl` | OID của các LDAP control được công bố | Ví dụ control phân trang; không suy ra mọi thao tác đều được phép |
| `supportedExtension` | OID của thao tác mở rộng được công bố | Có thể dùng để kiểm tra một số năng lực máy chủ |
| `supportedFeatures` | OID của tính năng LDAP được công bố | Danh sách thay đổi theo máy chủ |
| `subschemaSubentry` | DN của entry chứa mô tả schema áp dụng | Là con trỏ đến schema; không phải nội dung schema |
| `vendorName`, `vendorVersion` | Thông tin sản phẩm nếu máy chủ cung cấp | Không phải thuộc tính bắt buộc phải thấy ở mọi nơi |
| `defaultNamingContext` | Naming context mặc định trong một số triển khai như Active Directory | Thuộc tính đặc thù sản phẩm; không phải thay thế phổ quát cho `namingContexts` |

`namingContexts` và `defaultNamingContext` đặc biệt dễ gây nhầm lẫn. Ví dụ, Active Directory có thể công bố nhiều naming context cho domain, Configuration, Schema hoặc các partition khác, đồng thời trả về `defaultNamingContext` cho domain mặc định. Ứng dụng cần chọn vùng chứa dữ liệu nghiệp vụ thực tế, sau đó xác định quyền truy cập và vị trí các entry bên trong vùng đó.

### 3.2. Thử bằng `ldapsearch`

Với công cụ dòng lệnh của OpenLDAP, có thể đọc Root DSE qua một kết nối LDAP mã hóa:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -b "" -s base \
  "(objectClass=*)" \
  namingContexts supportedLDAPVersion subschemaSubentry supportedControl
```

Giải thích những tham số quyết định:

- `-b ""`: truy vấn **DN rỗng** của Root DSE.
- `-s base`: chỉ đọc entry tại DN được chọn, không duyệt xuống subtree.
- `"(objectClass=*)"`: filter thông dụng khi đọc entry; máy chủ quyết định kết quả phù hợp.
- Danh sách thuộc tính cuối lệnh: yêu cầu rõ những thông tin cần đọc. Root DSE không nhất thiết trả về mọi thuộc tính nếu không có yêu cầu cụ thể.
- `-x`: sử dụng simple authentication; không có `-D` thì ví dụ thực hiện anonymous bind. Chính sách máy chủ có thể từ chối anonymous read, khi đó dùng tài khoản có quyền đọc.

Khi cần bind bằng tài khoản được cấp phép, bổ sung `-D` và `-W` để nhập mật khẩu qua lời nhắc, thay vì đặt mật khẩu ngay trên dòng lệnh:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "" -s base \
  "(objectClass=*)" namingContexts defaultNamingContext
```

Hai ví dụ dùng địa chỉ và DN giả định. Trước khi thực hành, cần có truststore/cấu hình chứng chỉ đúng với môi trường LDAP thử nghiệm. Nếu máy chủ không công bố thuộc tính hoặc giới hạn quyền đọc, **không nên suy ra rằng thuộc tính đó chắc chắn không tồn tại**.

### 3.3. Root DSE khác gì với schema?

Root DSE cho biết **nơi tìm schema** qua `subschemaSubentry`, còn schema mô tả `objectClass`, `attributeType`, ràng buộc dữ liệu và quy tắc mà entry phải tuân theo. Ví dụ, biết naming context là `dc=example,dc=org` vẫn chưa đủ để khẳng định mọi entry người dùng dùng `uid`, `cn` hay `mail`; cần kiểm tra schema và quy ước của thư mục.

## 4. Base DN phải đi cùng search scope và filter

Một LDAP search không được xác định chỉ bởi base DN. Kết quả còn phụ thuộc vào **phạm vi tìm kiếm** (*search scope*), bộ lọc (*filter*), thuộc tính được yêu cầu và quyền của tài khoản bind.

| Search scope | Ví dụ với base `ou=people,dc=example,dc=org` | Phạm vi |
| --- | --- | --- |
| `base` | Chỉ `ou=people,dc=example,dc=org` | Đúng entry tại base |
| `one` / one-level | Các entry con trực tiếp, như `uid=alice,...` | Không gồm base và không đi sâu qua nhiều cấp |
| `sub` / subtree | Base và các entry hậu duệ ở mọi cấp | Dùng khi người dùng nằm trong nhiều OU con |

Ví dụ tìm người dùng có `uid=alice` dưới nhánh `ou=people`:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(uid=alice)" cn mail
```

Truy vấn này có thể trả về:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
cn: Alice Nguyen
mail: alice@example.org
```

Nếu chuyển base thành `ou=groups,dc=example,dc=org`, cùng filter sẽ không tìm thấy `alice` ở nhánh people. Nếu đặt base ngay tại `uid=alice,...` và dùng scope `base`, truy vấn chỉ kiểm tra entry đó. Việc chọn base hẹp giúp giới hạn vùng truy vấn và tránh đọc dữ liệu không liên quan, nhưng base hẹp quá mức có thể bỏ sót người dùng nằm ở OU khác.

### Base DN có nhất thiết bắt đầu bằng `dc=` không?

Không. `dc=example,dc=org` là cách đặt tên phổ biến dựa trên thành phần miền, nhưng DN có thể bắt đầu bằng `o=example`, `ou=people` hoặc một RDN khác theo cấu trúc thư mục được quản trị. Không thể lấy tên miền ứng dụng rồi tự kết luận chính xác base DN. Hãy dựa vào cấu hình thư mục, Root DSE, vị trí entry thực tế và quyền của tài khoản kết nối.

## 5. Áp dụng trong Spring LDAP: cấu hình base và đọc Root DSE

### 5.1. `ContextSource` gắn một base DN cho các thao tác thường ngày

Trong ứng dụng Spring, `LdapContextSource` định nghĩa địa chỉ máy chủ, danh tính bind và base DN mặc định. `LdapTemplate` sử dụng cấu hình đó để tìm, đọc, tạo, cập nhật và xóa entry. Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class DirectoryConfiguration {

    @Bean
    LdapContextSource directoryContextSource(
            @Value("${ldap.url}") String url,
            @Value("${ldap.base}") String base,
            @Value("${ldap.bind-dn}") String bindDn,
            @Value("${ldap.bind-password}") String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(
            @Qualifier("directoryContextSource") LdapContextSource directoryContextSource) {
        return new LdapTemplate(directoryContextSource);
    }
}
```

```yaml
# application.yml
ldap:
  url: ${LDAP_URL:ldaps://ldap.example.org:636}
  base: dc=example,dc=org
  bind-dn: ${LDAP_BIND_DN}
  bind-password: ${LDAP_BIND_PASSWORD}
```

`ldap.url` ở đây chỉ chứa **scheme, hostname và port**; hậu tố thư mục được cấu hình riêng trong `ldap.base`. Không ghép cùng hậu tố vào URL rồi cấu hình base lần nữa, vì cách kết hợp hai nơi có thể dẫn đến DN truy vấn không như mong muốn. Bind DN là danh tính kết nối, **không đồng nghĩa** base DN; tài khoản bind có thể nằm ở nhánh khác hoặc trong cấu trúc tên đặc thù của máy chủ.

Với `ldap.base = dc=example,dc=org`, các DN truyền vào thao tác của template thường là **DN tương đối** so với base đã cấu hình:

```java
import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Component;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Component
class PersonLookup {
    private final LdapTemplate template;

    PersonLookup(@Qualifier("ldapTemplate") LdapTemplate template) {
        this.template = template;
    }

    List<String> findNamesByUid(String uid) {
        return template.search(
            query().base("ou=people").where("uid").is(uid),
            attrs -> (String) attrs.get("cn").get()
        );
    }
}
```

Ở đây, `ou=people` được diễn giải tương đối với base `dc=example,dc=org`, nên vùng tìm kiếm tương ứng là `ou=people,dc=example,dc=org`. Cách dựng filter qua `where("uid").is(uid)` giúp xử lý escaping giá trị theo cú pháp filter LDAP. Ví dụ giả định entry tìm được có `cn`; khi triển khai thực tế cần kiểm tra các thuộc tính tùy chọn và xử lý giá trị đa trị.

Nếu đặt base ngay tại `ou=people,dc=example,dc=org`, biểu thức `query().base("")` sẽ truy vấn từ nhánh people. Khi chuyển sang thao tác nhóm ở `ou=groups`, cần một base phù hợp hoặc một cấu hình `ContextSource` khác thay vì cố truy cập ra ngoài phạm vi được chọn.

### 5.2. Đọc Root DSE bằng Spring LDAP cần chú ý `base` đã cấu hình

Điểm dễ mắc lỗi: nếu `LdapContextSource` đã đặt `base = dc=example,dc=org`, gọi `template.lookup("")` **không có nghĩa** đang đọc Root DSE của máy chủ. DN rỗng trong thao tác này là DN tương đối với base mà `ContextSource` sử dụng, nên yêu cầu hướng tới entry ở base đã cấu hình.

Muốn đọc Root DSE (DN rỗng tuyệt đối), hãy dùng một `ContextSource` riêng **không đặt base**. Ví dụ cấu hình bean bổ sung:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class RootDseConfiguration {

    @Bean("rootContextSource")
    LdapContextSource rootContextSource(
            @Value("${ldap.url}") String url,
            @Value("${ldap.bind-dn}") String bindDn,
            @Value("${ldap.bind-password}") String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        // Không gọi setBase(): context nằm tại gốc dịch vụ LDAP.
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean("rootDseTemplate")
    LdapTemplate rootDseTemplate(
            @Qualifier("rootContextSource") LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
```

Lớp đọc một thuộc tính đa trị `namingContexts` có thể viết như sau:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Component;

@Component
class RootDseReader {
    private final LdapTemplate rootTemplate;

    RootDseReader(@Qualifier("rootDseTemplate") LdapTemplate rootTemplate) {
        this.rootTemplate = rootTemplate;
    }

    List<String> readNamingContexts() {
        return rootTemplate.lookup(
            LdapNameBuilder.newInstance().build(), // DN rỗng tại gốc
            new String[] {"namingContexts"},      // operational attribute
            (AttributesMapper<List<String>>) attrs -> {
                Attribute attr = attrs.get("namingContexts");
                if (attr == null) {
                    return List.of();
                }
                List<String> contexts = new ArrayList<>();
                NamingEnumeration<?> values = attr.getAll();
                try {
                    while (values.hasMore()) {
                        contexts.add(String.valueOf(values.next()));
                    }
                } finally {
                    values.close();
                }
                return contexts;
            }
        );
    }
}
```

Trong ví dụ, bean `rootContextSource` và `directoryContextSource` được Spring quản lý vòng đời. Hai `LdapTemplate` có thể dùng cùng địa chỉ máy chủ và cùng tài khoản bind, nhưng có **base khác nhau**. Mỗi template có mục đích cụ thể: đọc metadata Root DSE hoặc truy cập dữ liệu nghiệp vụ. `List.of()` trong ví dụ yêu cầu Java 9 trở lên.

Đọc `namingContexts` trả về danh sách rỗng chưa đủ kết luận máy chủ không có naming context: có thể thuộc tính không được công bố, bị giới hạn quyền hoặc máy chủ có hành vi đặc thù. Nếu kết nối thất bại hoặc không có quyền, thao tác có thể ném ngoại lệ Spring LDAP và cần được xử lý riêng. Không biến mọi lỗi thành danh sách rỗng.

### 5.3. Tương quan với `LdapClient` và ODM

`LdapClient` ở những phiên bản Spring LDAP hỗ trợ API fluent và ODM giúp làm việc với entry theo mô hình đối tượng Java. Chúng không thay đổi ý nghĩa của **Root DSE**, **naming context** hoặc **base DN**. Dù chọn `LdapTemplate`, `LdapClient` hay ODM, ứng dụng vẫn cần thiết lập `ContextSource` phù hợp, xác định DN tương đối/tuyệt đối, dùng filter an toàn và hiểu schema của entry.

## 6. Các trường hợp dễ nhầm và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể gặp | Cách kiểm tra |
| --- | --- | --- |
| `lookup("")` trả về entry `dc=example,dc=org`, không phải Root DSE | Template có `ContextSource` với base được cấu hình | Dùng context không có base để truy cập DN rỗng tuyệt đối |
| Root DSE có `namingContexts` nhưng tìm người dùng không ra | Chọn sai base, scope, filter hoặc không đủ quyền | Xác nhận DN người dùng thật và chạy thử `ldapsearch` tại nhánh mong muốn |
| Truy vấn dưới `ou=people` không thấy user ở OU con | Scope là `one`, trong khi entry nằm sâu nhiều cấp | Xác nhận mức phân cấp rồi chọn `sub` nếu đúng nhu cầu |
| Kết quả từ Root DSE thiếu thuộc tính | Thuộc tính vận hành chưa được yêu cầu rõ, chính sách truy cập hoặc khác biệt máy chủ | Yêu cầu đích danh thuộc tính; xem tài liệu sản phẩm LDAP và quyền bind |
| Tên trong `namingContexts` chứa Configuration/Schema | Máy chủ công bố nhiều naming context | Chọn partition/nhánh nghiệp vụ đúng, tránh dùng phần tử đầu tiên một cách máy móc |
| Có kết nối TCP nhưng LDAP không hoạt động | TLS/truststore, hostname, bind hoặc giao thức không hợp lệ | Kiểm tra chứng chỉ, phương thức bind và lỗi chi tiết (không ghi mật khẩu vào log) |

### Bảo mật và vận hành

- **Kết nối an toàn:** dùng LDAPS hoặc StartTLS theo thiết kế hạ tầng; kiểm tra chuỗi chứng chỉ và hostname. Không mặc định rằng mọi máy chủ hỗ trợ StartTLS, và không bỏ xác minh TLS để “chữa” lỗi chứng chỉ.
- **Quyền tối thiểu:** tài khoản dùng để khám phá Root DSE hoặc tìm người dùng chỉ nên có quyền đọc cần thiết. Một số thuộc tính có thể được phép đọc ẩn danh, nhưng không nên dựa vào đặc tính đó cho mọi môi trường.
- **Hiệu năng:** chọn base và scope phù hợp, hạn chế thuộc tính yêu cầu, đặt timeout và giới hạn kết quả hoặc paging khi cần. Việc Root DSE công bố control phân trang không thay thế thiết kế paging chính xác trong truy vấn.
- **Pooling:** có thể dùng cơ chế tái sử dụng context nếu phù hợp với cấu hình LDAP, nhưng cần xem xét đặc biệt khi dùng StartTLS hoặc xác thực bằng nhiều danh tính. Không chia sẻ tùy tiện context đã bind dưới quyền một người dùng cho người khác.
- **Xử lý lỗi:** phân biệt tìm kiếm không có kết quả, base DN không tồn tại, không đủ quyền, sai bind credentials và sự cố mạng/TLS; các tình huống này cần hành vi xử lý khác nhau.

## 7. Bài thực hành: xác định base DN đúng cho ứng dụng

Giả sử ứng dụng cần tìm người dùng trong miền `example.org` và quản trị viên cung cấp endpoint LDAP. Hãy thực hiện trên thư mục **thử nghiệm**, dùng dữ liệu không nhạy cảm:

1. Kết nối qua LDAPS với chứng chỉ hợp lệ, đọc Root DSE bằng DN `""`, scope `base` và yêu cầu `namingContexts`, `supportedLDAPVersion`, `subschemaSubentry`.
2. Liệt kê mọi naming context nhận được. Phân biệt vùng dữ liệu người dùng với các vùng schema, cấu hình hoặc partition phụ trợ (nếu có). Không chọn bừa giá trị đầu tiên.
3. Xác nhận với quản trị viên hoặc dữ liệu thử nghiệm nhánh chứa user, ví dụ `ou=people,dc=example,dc=org`. Chạy truy vấn một lần với scope `one`, một lần với `sub` để thấy khác biệt nếu có OU con.
4. Cấu hình `LdapContextSource` với base `dc=example,dc=org`, rồi viết truy vấn Spring LDAP có base tương đối `ou=people`. Kiểm tra DN hiệu lực so với lệnh `ldapsearch` ở bước 3.
5. Thêm một template với base rỗng để đọc Root DSE, so sánh kết quả với `ldapTemplate.lookup("")` trên template có base. Xác nhận hai lời gọi hướng tới những DN khác nhau.
6. Thử tìm một UID không tồn tại, dùng sai base DN hoặc tài khoản thiếu quyền, sau đó ghi nhận sự khác nhau giữa **không có kết quả** và **lỗi truy cập**. Ghi log đủ để chẩn đoán nhưng không tiết lộ mật khẩu.

**Câu hỏi tự kiểm tra:**

- Vì sao `namingContexts: dc=example,dc=org` không bắt buộc ứng dụng phải tìm kiếm từ chính `dc=example,dc=org`?
- Điều gì xảy ra với truy vấn `query().base("ou=people")` khi `ContextSource` đã đặt base `dc=example,dc=org`?
- Vì sao Root DSE có DN rỗng nhưng không thể coi là entry cha bình thường của tất cả naming context?
- Cần thay đổi điều gì để đọc Root DSE khi `LdapTemplate` đang dùng base DN nghiệp vụ?
- Nếu LDAP server trả về nhiều naming context, bạn dựa vào yếu tố nào để chọn đúng nhánh dữ liệu và scope tìm kiếm?

## 8. Tổng kết kiến thức

**Root DSE** là entry metadata tại DN rỗng của dịch vụ LDAP; **naming context** xác định các vùng tên mà máy chủ công bố; **base DN** là điểm bắt đầu do ứng dụng hoặc yêu cầu truy vấn lựa chọn. Root DSE giúp khám phá môi trường, nhưng không tự xác định base nghiệp vụ phù hợp. Trong Spring LDAP, `ContextSource` quyết định base mặc định cho `LdapTemplate`, `LdapClient` hoặc cách truy cập entry của ứng dụng, nên phải phân biệt DN tương đối với DN đầy đủ. Việc cấu hình đúng kết hợp với filter, search scope, schema, TLS và quyền tối thiểu là nền tảng để tìm kiếm, cập nhật, xác thực và kiểm thử LDAP an toàn.
