# Directory Information Tree (DIT) và cấu trúc dạng cây

Trong LDAP, dữ liệu được tổ chức thành **Directory Information Tree (DIT)**: một cấu trúc phân cấp gồm các **entry** (bản ghi thư mục). Hiểu DIT là điều kiện cần để xác định đúng Distinguished Name (DN), chọn nơi bắt đầu tìm kiếm, giới hạn phạm vi truy vấn và thao tác entry bằng **Spring LDAP**.

Bài học thuộc chương **LDAP nền tảng**, đặt nền móng cho việc sử dụng `LdapTemplate`, `LdapClient` hoặc Object-Directory Mapping (ODM) khi làm việc với dịch vụ thư mục LDAP.

**Sau bài này, bạn có thể:**

- Đọc một sơ đồ DIT và xác định entry cha, entry con, nhánh và cây con.
- Phân biệt entry, attribute, RDN, DN, naming context và Root DSE.
- Tính DN đầy đủ từ vị trí một entry; chọn đúng search base và search scope.
- Áp dụng mô hình cây khi truy vấn LDAP bằng Spring LDAP và tránh lỗi cộng lặp base DN.

## 1. DIT là gì?

LDAP (Lightweight Directory Access Protocol) cung cấp cách truy cập dữ liệu thư mục. Đơn vị dữ liệu cơ bản là **entry**; mỗi entry có một tên phân biệt duy nhất trong cây thư mục liên quan và chứa tập hợp các thuộc tính (**attribute**).

Các entry được đặt theo quan hệ **cha – con**. Một entry có thể có nhiều entry con trực tiếp, nhưng một entry cụ thể chỉ có một vị trí cha trực tiếp trong DIT. Các entry bên dưới một nút hợp thành **subtree** (cây con).

Ví dụ, một tổ chức quản lý người dùng, nhóm và ứng dụng trên một LDAP server:

```text
dc=example,dc=com
├── ou=People
│   ├── uid=an
│   └── uid=binh
├── ou=Groups
│   ├── cn=Developers
│   └── cn=Support
└── ou=Applications
    └── cn=Payroll
```

Trong sơ đồ, mỗi dòng đại diện cho **một entry** và chỉ ghi **Relative Distinguished Name (RDN)** ở mỗi cấp để dễ nhìn. DN đầy đủ của `uid=an` là:

```text
uid=an,ou=People,dc=example,dc=com
```

Nhánh `ou=People` chứa hai entry người dùng. Nhánh `ou=Groups` chứa các entry nhóm. Chúng là các nhánh ngang hàng vì có cùng entry cha là `dc=example,dc=com`.

DIT là một **không gian tên phân cấp**, không phải bảng quan hệ. Những liên kết nghiệp vụ như “người dùng An thuộc nhóm Developers” thường được biểu diễn bằng **giá trị thuộc tính tham chiếu DN**, chứ không bắt buộc bằng quan hệ cha – con. Chẳng hạn, entry nhóm `cn=Developers,ou=Groups,dc=example,dc=com` có thể chứa thuộc tính:

```ldif
member: uid=an,ou=People,dc=example,dc=com
```

Người dùng An vẫn nằm dưới `ou=People`, dù là thành viên của nhóm dưới `ou=Groups`.

### Các thành phần trong cây

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Entry | Nút dữ liệu có DN và các attribute | Người dùng `uid=an,...` |
| Attribute | Một loại thông tin của entry; có thể có một hoặc nhiều giá trị theo schema | `cn`, `mail`, `member` |
| Parent | Entry ở cấp ngay bên trên | Cha của `uid=an,...` là `ou=People,...` |
| Child | Entry ở cấp ngay bên dưới | `uid=an` là con của `ou=People` |
| Sibling | Các entry có cùng cha | `uid=an` và `uid=binh` |
| Branch/subtree | Một entry và toàn bộ hậu duệ của nó | Nhánh `ou=Groups` |
| Leaf | Entry hiện không có con | `cn=Payroll,...` trong ví dụ |

Không phải mọi entry đều là “thư mục” chứa con: một entry người dùng vẫn có thể là nút cha nếu thiết kế và schema của hệ thống cho phép. `ou` chỉ là cách đặt tên thường gặp cho nhánh tổ chức, không phải quy tắc bắt buộc mọi node trung gian đều phải dùng `ou`.

## 2. DN và RDN: đọc đường đi trong DIT

**RDN (Relative Distinguished Name)** định danh một entry **so với entry cha**. Ví dụ: `uid=an`, `ou=People`, `dc=example`.

**DN (Distinguished Name)** là chuỗi các RDN xác định đường đi đến entry. Dạng chuỗi LDAP phổ biến ghi **RDN của entry cụ thể nhất bên trái**, rồi đến các cấp cha bên phải:

```text
uid=an,ou=People,dc=example,dc=com
│      │         │          └── dc=com
│      │         └───────────── dc=example
│      └─────────────────────── ou=People
└────────────────────────────── uid=an
```

Để tìm **cha trực tiếp** của một entry, bỏ RDN ở bên trái DN:

- DN hiện tại: `uid=an,ou=People,dc=example,dc=com`.
- DN cha: `ou=People,dc=example,dc=com`.
- DN ông/bà: `dc=example,dc=com`.

Đi từ cha xuống con nghĩa là **thêm RDN mới vào phía trái** DN. Ví dụ, thêm `uid=chi` dưới `ou=People,dc=example,dc=com` sẽ tạo DN `uid=chi,ou=People,dc=example,dc=com`.

### Các thành phần tên thường gặp

| Tiền tố RDN | Thuộc tính | Mục đích điển hình |
| --- | --- | --- |
| `dc` | `domainComponent` | Chia tên theo thành phần miền, ví dụ `dc=example,dc=com` |
| `ou` | `organizationalUnitName` | Đơn vị tổ chức hoặc nhánh logic, ví dụ `ou=People` |
| `o` | `organizationName` | Tên tổ chức, ví dụ `o=Example Corp` |
| `cn` | `commonName` | Tên thông dụng của đối tượng, nhóm, dịch vụ |
| `uid` | `userId` | Mã định danh người dùng theo quy ước thư mục |

Đây là những **attribute dùng để đặt tên**, không phải các loại thư mục cứng. Ví dụ, một người có thể được đặt tên bằng `uid=an` hoặc `cn=An Nguyen` tùy schema và quy tắc đặt tên.

**Hai quy tắc quan trọng:**

1. **RDN phải phân biệt các entry con của cùng cha.** Không thể có hai entry có cùng RDN theo quy tắc so khớp tên của server nằm dưới cùng một entry cha. Nhưng `uid=an,ou=People,...` và `uid=an,ou=Contractors,...` có thể cùng tồn tại vì khác DN đầy đủ.
2. **DN diễn tả vị trí trong cây.** Khi đổi RDN hoặc chuyển entry sang cha khác, DN của entry thay đổi; các DN của hậu duệ cũng bị ảnh hưởng theo cấu trúc mới. Ứng dụng không nên mặc định DN là mã định danh bất biến vĩnh viễn.

Theo RFC 4514, một RDN đôi khi chứa **nhiều cặp attribute–value**, nối bằng dấu `+` (ví dụ `cn=An Nguyen+uid=an`). Khi giá trị DN chứa ký tự đặc biệt như dấu phẩy, cần escape đúng cú pháp: `cn=Doe\, Jane,ou=People,dc=example,dc=com`. Không ghép DN từ chuỗi đầu vào tùy ý.

## 3. Naming context, base DN và Root DSE

### Naming context là gì?

Một LDAP server có thể phục vụ một hoặc nhiều **naming context** (các cây con mà server cung cấp). `dc=example,dc=com` trong ví dụ là **điểm bắt đầu của một naming context**. Đây thường cũng là *suffix* mà người quản trị cấu hình cho cơ sở dữ liệu thư mục.

Naming context **không nhất thiết** luôn bắt đầu bằng `dc`: các hệ thống có thể dùng `o=Example` hoặc cấu trúc tên khác. Và `dc=example,dc=com` chỉ là tên LDAP theo quy ước; nó không làm các bản ghi trong LDAP tự động đồng bộ với DNS.

### Root DSE nằm ở đâu?

**Root DSE** (Root Directory Specific Entry) là entry đặc biệt của **từng LDAP server**, truy cập qua DN rỗng `""`. Nó cho biết khả năng và thông tin server, chẳng hạn thuộc tính `namingContexts` nếu server công bố.

Root DSE **không phải entry `dc=example,dc=com`**, và **không nằm trong một naming context thông thường**. Vì vậy không được suy ra rằng LDAP luôn có một entry `dc=com` hoặc một entry “root” chứa mọi suffix. Các server khác nhau có thể công bố các naming context khác nhau.

Ví dụ truy vấn Root DSE bằng công cụ dòng lệnh (tùy server và quyền truy cập):

```bash
ldapsearch -x -H ldaps://ldap.example.com:636 \
  -b "" -s base "(objectClass=*)" namingContexts
```

Truy vấn này đặt **search base là DN rỗng** và **scope là `base`**. Nếu server cho phép trả về `namingContexts`, một giá trị có thể là `dc=example,dc=com`.

### Phân biệt ba loại base

| Tên gọi | Vai trò | Ví dụ |
| --- | --- | --- |
| Naming context/suffix | Điểm gốc của cây con do server phục vụ | `dc=example,dc=com` |
| `ContextSource.base` trong Spring LDAP | DN nền mà ứng dụng cấu hình để các thao tác thông thường dùng DN tương đối | `dc=example,dc=com` |
| Search base của một truy vấn | Entry mà phép tìm kiếm bắt đầu xét | `ou=People,dc=example,dc=com` |

Ba giá trị này thường liên hệ chặt chẽ nhưng **không đồng nghĩa**. Search base có thể là một nhánh rất nhỏ trong naming context.

## 4. Entry chứa gì? Schema ràng buộc hình dạng dữ liệu

Cây DIT mô tả **vị trí** của entry; còn **schema** mô tả những `objectClass` và `attribute` mà entry được phép hoặc bắt buộc có.

Dưới đây là một tập entry mẫu theo định dạng **LDIF** (LDAP Data Interchange Format). Ví dụ minh họa một phần cây ở trên; các entry `uid=binh`, `cn=Support` và nhánh `ou=Applications` có thể được bổ sung tương tự.

```ldif
dn: dc=example,dc=com
objectClass: top
objectClass: domain
dc: example

dn: ou=People,dc=example,dc=com
objectClass: top
objectClass: organizationalUnit
ou: People

dn: uid=an,ou=People,dc=example,dc=com
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Nguyen
sn: Nguyen
mail: an@example.com

dn: ou=Groups,dc=example,dc=com
objectClass: top
objectClass: organizationalUnit
ou: Groups

dn: cn=Developers,ou=Groups,dc=example,dc=com
objectClass: top
objectClass: groupOfNames
cn: Developers
member: uid=an,ou=People,dc=example,dc=com
```

Giải thích:

- `dn` cho biết **vị trí trong cây**. Thứ tự các phần trong DN không phải thứ tự các attribute bên trong entry.
- `objectClass` quyết định tập attribute phù hợp với schema. `inetOrgPerson` là loại entry người dùng phổ biến; các lớp `person`/`organizationalPerson`/`inetOrgPerson` kế thừa những yêu cầu tương ứng.
- `cn` là tên hiển thị, `sn` là họ, `mail` là địa chỉ email. `uid=an` trong RDN có giá trị thuộc tính `uid: an` ở entry.
- `groupOfNames` biểu diễn nhóm bằng attribute `member` có giá trị là **DN của thành viên**. Quan hệ thành viên không làm thay đổi vị trí người dùng trong DIT.

Khi thực hành trên một server cụ thể, phải kiểm tra schema đang được cài đặt: mỗi `objectClass` có quy định thuộc tính bắt buộc, thuộc tính được phép và quy tắc so khớp. Quyền sửa entry, chính sách đặt tên và khả năng tạo các loại entry còn phụ thuộc cấu hình server.

## 5. Tìm kiếm trong cây: base, scope và filter

Một phép tìm kiếm LDAP thường có ba phần chính:

1. **Base DN**: bắt đầu tại entry nào?
2. **Scope**: xét sâu bao nhiêu cấp?
3. **Filter**: trong các entry được xét, entry nào thỏa điều kiện?

Giả sử đặt base là `ou=People,dc=example,dc=com` và dữ liệu giống sơ đồ mục 1.

| Scope | Phạm vi xét | Entry được xét trong ví dụ |
| --- | --- | --- |
| `BASE` / `OBJECT` | Chỉ chính entry base | `ou=People` |
| `ONELEVEL` | Chỉ các con trực tiếp, không gồm base | `uid=an`, `uid=binh` |
| `SUBTREE` | Base và mọi cấp hậu duệ | `ou=People`, `uid=an`, `uid=binh` |

**Filter được áp dụng bên trong phạm vi đã chọn.** Ví dụ, với `SUBTREE` nhưng filter `(objectClass=inetOrgPerson)`, entry `ou=People` không được trả về vì không thỏa filter; các entry người dùng phù hợp mới được trả về. Không nên nhầm **các entry được xét theo scope** với **các entry thực sự được trả về**.

Ví dụ tìm người dùng `uid=an` dưới nhánh People:

```bash
ldapsearch -x -H ldaps://ldap.example.com:636 \
  -b "ou=People,dc=example,dc=com" \
  -s one "(uid=an)" dn cn mail
```

Trong lệnh trên, `-b` xác định base, `-s one` xác định scope một cấp và `(uid=an)` là filter. `-x` yêu cầu xác thực đơn giản; lệnh không có tham số bind sẽ thường thử truy cập ẩn danh. Việc có kết quả hay không phụ thuộc dữ liệu, chính sách xác thực và quyền đọc trên server.

### Chọn scope theo mục tiêu

- **Đọc đúng một entry đã biết DN**: dùng lookup hoặc scope `BASE`.
- **Liệt kê các user đặt trực tiếp dưới `ou=People`**: dùng `ONELEVEL`.
- **Tìm user nằm trong nhiều OU con lồng nhau** (ví dụ `ou=Engineering,ou=People,...`): dùng `SUBTREE` từ `ou=People`.

Chọn base càng sát vùng dữ liệu cần tìm càng tốt. Scope quá rộng có thể làm tăng chi phí truy vấn, chạm giới hạn số kết quả hoặc khiến dữ liệu ngoài phạm vi nghiệp vụ lọt vào kết quả.

## 6. Liên hệ với Spring LDAP

Spring LDAP cung cấp các API như `LdapTemplate`, `LdapClient` và ODM để làm việc với entry bằng Java. DIT quyết định **DN nào phải truyền cho API** và **query cần bắt đầu từ nhánh nào**.

### 6.1. Cấu hình `ContextSource` với base DN

Ví dụ cấu hình bean Spring (URL, bind DN và cây minh họa cần được thay bằng giá trị của hệ thống thực):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfig {

    @Bean
    LdapContextSource contextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://ldap.example.com:636");
        source.setBase("dc=example,dc=com");
        source.setUserDn(
            "cn=reader,ou=ServiceAccounts,dc=example,dc=com"
        );
        source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
```

Khi `ContextSource` có `base = dc=example,dc=com`, những DN dùng trong các thao tác Spring LDAP thông thường được hiểu là **tương đối với base này**:

| DN tương đối truyền cho Spring LDAP | DN đầy đủ trên server |
| --- | --- |
| `""` | `dc=example,dc=com` |
| `ou=People` | `ou=People,dc=example,dc=com` |
| `uid=an,ou=People` | `uid=an,ou=People,dc=example,dc=com` |

**Lỗi thường gặp:** đã đặt `source.setBase("dc=example,dc=com")` nhưng tiếp tục truyền `ou=People,dc=example,dc=com` làm search base. Điều đó có thể khiến đường dẫn bị cộng lặp suffix và dẫn đến lỗi không tìm thấy entry. Trong ví dụ này, chỉ truyền `ou=People` cho query.

Nếu cần tạo **DN đầy đủ làm giá trị của attribute** như `member`, phải dùng DN tuyệt đối thích hợp; DN tương đối chỉ áp dụng cho các thao tác dựa trên `ContextSource.base`, không tự động đúng cho mọi thuộc tính chứa DN.

### 6.2. Tìm entry theo nhánh bằng `LdapTemplate`

Ví dụ sau lấy `cn` của các entry có `objectClass=inetOrgPerson` **nằm trực tiếp dưới** `ou=People`:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PeopleDirectory {
    private final LdapTemplate ldapTemplate;

    public PeopleDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> listDirectPeople() {
        return ldapTemplate.search(
            query()
                .base("ou=People")
                .searchScope(SearchScope.ONELEVEL)
                .where("objectClass").is("inetOrgPerson"),
            (AttributesMapper<String>) attrs ->
                attrs.get("cn").get().toString()
        );
    }
}
```

Trong đoạn code:

- `base("ou=People")` chọn nhánh People **tương đối** với base đã cấu hình.
- `SearchScope.ONELEVEL` chỉ xét con trực tiếp. Đổi thành `SearchScope.SUBTREE` để xét cả các OU con.
- `where("objectClass").is("inetOrgPerson")` tạo filter LDAP. Khi cần lọc theo dữ liệu người dùng, dùng API xây filter này thay vì tự nối chuỗi filter không được escape.
- `AttributesMapper` chuyển attribute của mỗi entry tìm được thành giá trị Java.

`LdapClient` cũng cung cấp cách tìm kiếm fluent, và ODM cho phép gắn DN với đối tượng Java bằng các annotation như `@Entry`, `@Id` và `@DnAttribute`. Dù dùng API nào, ý nghĩa của base, DN và nhánh vẫn không đổi.

### 6.3. Tạo DN bằng `LdapNameBuilder`

Khi người dùng cung cấp giá trị RDN (ví dụ `uid`), không nên tự viết `"uid=" + uid + ",ou=People"`. Dấu phẩy, dấu cộng, dấu gạch chéo ngược và các ký tự đặc biệt trong giá trị có thể làm DN sai cấu trúc.

Spring LDAP có `LdapNameBuilder` giúp tạo DN và escape phần giá trị:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

public Name userDnRelativeToContextBase(String uid) {
    return LdapNameBuilder.newInstance()
        .add("ou", "People")
        .add("uid", uid)
        .build();
}
```

Với `uid = "an"`, kết quả là `uid=an,ou=People`. Khi truyền DN này cho `LdapTemplate` trong cấu hình mục 6.1, server sẽ truy cập entry `uid=an,ou=People,dc=example,dc=com`.

**DN escaping và LDAP filter escaping là hai việc khác nhau.** Dùng `LdapNameBuilder` cho DN; dùng bộ dựng filter của Spring LDAP hoặc cơ chế escape filter tương ứng cho điều kiện truy vấn.

## 7. Thiết kế DIT thực tế: tổ chức nhánh cho dễ vận hành

Không có một DIT duy nhất đúng cho mọi hệ thống. Các nhánh có thể tổ chức theo loại đối tượng (People/Groups/Services), đơn vị kinh doanh (Engineering/Sales), địa lý hoặc nhiều cấp kết hợp.

Ví dụ, nếu thường truy vấn toàn bộ nhân viên, cấu trúc `ou=People` là điểm bắt đầu dễ hiểu. Nếu cần phân quyền, ủy quyền quản trị hoặc đồng bộ các OU độc lập, chia thành `ou=Engineering,ou=People` và `ou=Sales,ou=People` có thể phù hợp. Tuy nhiên, mỗi cấp phân chia mới ảnh hưởng đến DN, phạm vi tìm kiếm và việc di chuyển entry.

Một số nguyên tắc khi thiết kế:

1. **Chọn cách đặt RDN nhất quán**, ví dụ `uid` cho người dùng, `cn` cho nhóm. Kiểm tra tính duy nhất trong cùng cha và yêu cầu của schema.
2. **Hạn chế đổi vị trí entry thường xuyên.** Di chuyển entry hoặc đổi RDN khiến DN thay đổi; ứng dụng lưu DN và các quan hệ tham chiếu có thể cần cập nhật tương ứng. Việc server hỗ trợ di chuyển và xử lý tham chiếu phụ thuộc triển khai/cấu hình.
3. **Tách cấu trúc cây khỏi quan hệ nghiệp vụ.** Thành viên nhóm nên được mô hình hóa bằng attribute nhóm phù hợp, thay vì đặt entry người dùng bên trong entry nhóm chỉ để biểu diễn membership.
4. **Đặt search base đủ hẹp** và áp dụng filter, giới hạn kết quả/phân trang, timeout phù hợp khi dữ liệu lớn. Chính sách truy cập có thể che một phần DIT đối với tài khoản bind.
5. **Đảm bảo kết nối an toàn.** Truy vấn hoặc bind tới thư mục thật cần TLS (LDAPS hoặc StartTLS) và kiểm tra chứng chỉ; không đặt mật khẩu bind cố định trong mã nguồn.

### Những nhầm lẫn cần tránh

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `No Such Object` khi đã nhìn thấy entry trên sơ đồ | Search base sai, cộng lặp suffix, entry chưa tồn tại hoặc server trả kết quả hạn chế theo quyền | Đọc lại DN, `ContextSource.base`, nhánh thực tế và quyền bind |
| `ONELEVEL` không tìm được user nằm sâu trong OU con | Scope chỉ xét con trực tiếp | Dùng `SUBTREE` khi cần toàn bộ hậu duệ |
| Tìm thấy nhóm nhưng không thấy user trong nhánh Groups | Membership là giá trị `member` trỏ tới DN bên People | Đọc attribute `member` rồi tra cứu entry theo DN |
| Hai người cùng `cn` làm truy vấn nhầm | `cn` không nhất thiết là khóa duy nhất của mọi người dùng | Dùng RDN/định danh phù hợp và filter đủ chặt |
| Rename làm tham chiếu `member` cũ không còn đúng | DN của user thay đổi, tham chiếu chưa được điều chỉnh | Xem chính sách referential integrity và quy trình cập nhật tham chiếu |
| Filter đúng nhưng không trả đủ kết quả | Base, scope, ACL, size limit hoặc filter loại các entry | Kiểm tra từng thành phần và giới hạn phía server |

## 8. Tự luyện tập với cây ví dụ

Xét sơ đồ DIT ở mục 1 và `ContextSource.base = dc=example,dc=com`.

**Bài 1.** DN đầy đủ của entry `cn=Support` là gì? Cha trực tiếp của nó có DN nào?

**Bài 2.** Muốn liệt kê các nhóm nằm trực tiếp dưới `ou=Groups`, nên chọn search base tương đối nào và scope nào?

**Bài 3.** Nếu có thêm `uid=lan,ou=Engineering,ou=People,dc=example,dc=com`, truy vấn bắt đầu tại `ou=People` với `ONELEVEL` có xét entry Lan không? Cần đổi gì?

**Bài 4.** Giả sử `cn=Developers` chứa `member: uid=an,ou=People,dc=example,dc=com`. Entry An có trở thành con của `cn=Developers` không?

<details>
<summary>Đáp án gợi ý</summary>

1. `cn=Support,ou=Groups,dc=example,dc=com`; cha là `ou=Groups,dc=example,dc=com`.
2. Search base tương đối `ou=Groups`, scope `ONELEVEL` (kết hợp filter phù hợp để chọn entry nhóm).
3. Không. Lan là hậu duệ ở hai cấp bên dưới `ou=People`; dùng `SUBTREE` nếu cần bao quát các OU con.
4. Không. `member` là tham chiếu DN giữa hai nhánh; vị trí của An vẫn là `uid=an,ou=People,...`.

</details>

## 9. Ghi nhớ

**DIT định nghĩa vị trí; DN định danh đường đi; schema quy định dữ liệu; search base và scope xác định phần cây cần truy vấn.** Khi làm việc với Spring LDAP, hãy luôn biết `ContextSource.base` đã được đặt chưa trước khi truyền DN cho `LdapTemplate` hoặc `LdapClient`.

Từ nền tảng này, bạn có thể tiếp tục học LDAP filter, xây dựng truy vấn an toàn, tạo/sửa/xóa entry và kiểm thử các thao tác thư mục.

### Tài liệu tham khảo

- [RFC 4512 – LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): mô hình DIT, naming context, entry và Root DSE.
- [RFC 4514 – LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514.html): định dạng DN, RDN nhiều thuộc tính và escaping.
- [Spring LDAP – Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): cách `ContextSource` áp dụng base DN.
- [Spring LDAP – Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): search base, scope và filter.
- [Spring LDAP – `LdapNameBuilder` API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapNameBuilder.html): cách dựng DN bằng Java.
