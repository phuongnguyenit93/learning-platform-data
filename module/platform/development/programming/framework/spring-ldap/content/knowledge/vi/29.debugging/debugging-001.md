# Đọc DN, base DN và search scope khi truy vấn LDAP sai

Khi một truy vấn Spring LDAP trả về danh sách rỗng, trả về sai nhánh thư mục hoặc báo `NameNotFoundException`, nguyên nhân có thể nằm ở **DN**, **base DN** hoặc **search scope** trước cả khi xét tới filter hay mã ánh xạ kết quả. Bài này hướng dẫn cách đọc đường dẫn LDAP, tính vị trí tìm kiếm thực tế và kiểm tra từng giả thuyết bằng công cụ dòng lệnh cùng `LdapTemplate`.

## 1. Phân biệt DN, RDN, base DN và bind DN

Trong LDAP, **Distinguished Name (DN)** xác định vị trí của một entry trong cây thư mục. DN gồm các **Relative Distinguished Name (RDN)**, phân cách bằng dấu phẩy; RDN ở **bên trái** là entry đang nói tới, các RDN kế tiếp đi dần lên phía gốc.

Giả sử máy chủ chứa cây:

```text
dc=example,dc=com
├── ou=people
│   ├── uid=lan
│   └── ou=contractors
│       └── uid=minh
└── ou=service
    └── uid=reader
```

DN đầy đủ của Lan là:

```text
uid=lan,ou=people,dc=example,dc=com
│       │         └──────────────┘
│       │              hậu tố của cây (naming context)
│       └── đơn vị chứa entry
└── RDN của entry được tìm
```

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| **RDN** | `uid=lan` | Tên tương đối của entry so với entry cha. |
| **DN đầy đủ** | `uid=lan,ou=people,dc=example,dc=com` | Địa chỉ của một entry cụ thể trong cây LDAP. |
| **Base DN của truy vấn** | `ou=people,dc=example,dc=com` | Entry xuất phát của phép tìm kiếm; có thể được tìm thấy hay không tùy `scope` và filter. |
| **Bind DN** | `uid=reader,ou=service,dc=example,dc=com` | Danh tính dùng để xác thực phiên kết nối; không quyết định vị trí tìm kiếm. |

`cn`, `ou`, `uid`, `dc` là các **tên thuộc tính** thường gặp trong RDN, không phải các cấp cố định mà mọi thư mục đều có. DN có quy tắc escape riêng: dấu phẩy thuộc giá trị phải được escape, chẳng hạn `cn=Nguyen\, Van A,ou=people,dc=example,dc=com`. Vì vậy không tách DN đơn thuần bằng `String.split(",")` khi debug hoặc xử lý dữ liệu thực; có thể dùng `javax.naming.ldap.LdapName` hoặc `org.springframework.ldap.support.LdapNameBuilder` để phân tích và xây dựng tên hợp lệ.

> **Quy tắc cần nhớ:** DN cho biết entry **ở đâu**; LDAP filter (ví dụ `(uid=lan)`) chọn entry **nào** trong vùng tìm kiếm; bind DN cho biết truy vấn được thực hiện **với quyền của ai**.

## 2. Tính base DN hiệu lực trong Spring LDAP

Trong Spring LDAP, `ContextSource` có thể được cấu hình với một base để mọi thao tác từ `LdapTemplate` dùng đường dẫn tương đối so với base đó:

```java
// Ví dụ cấu hình: LdapContextSource đã được tạo, chưa gọi afterPropertiesSet().
contextSource.setUrl("ldaps://ldap.example.com:636");
contextSource.setBase("dc=example,dc=com");
// User DN và mật khẩu nên được cấp qua cấu hình bảo mật, không ghi cứng.
```

Với cấu hình trên, lệnh tìm kiếm:

```java
ldapTemplate.search(
    "ou=people",                  // Base tương đối với ContextSource
    "(uid=lan)",                 // Filter
    SearchControls.ONELEVEL_SCOPE,
    (Attributes attrs) -> attrs.get("cn").get().toString()
);
```

sẽ tìm kiếm bắt đầu từ **`ou=people,dc=example,dc=com`**. Để chạy ví dụ, import `javax.naming.directory.Attributes`, `javax.naming.directory.SearchControls` và có một `LdapTemplate` đã cấu hình. Ví dụ giả định entry phù hợp có thuộc tính `cn`; trong ứng dụng thực, hãy kiểm tra `attrs.get("cn") != null` trước khi đọc.

| `ContextSource` base | Base truyền cho `search(...)` | Base DN hiệu lực |
|---|---|---|
| `dc=example,dc=com` | `ou=people` | `ou=people,dc=example,dc=com` |
| `dc=example,dc=com` | `ou=contractors,ou=people` | `ou=contractors,ou=people,dc=example,dc=com` |
| `dc=example,dc=com` | `""` (chuỗi rỗng) | `dc=example,dc=com` |
| Không đặt base | `ou=people,dc=example,dc=com` | `ou=people,dc=example,dc=com` |

**Lỗi thường gặp:** `ContextSource` đã có base `dc=example,dc=com` nhưng mã lại đưa **DN đầy đủ** `ou=people,dc=example,dc=com` vào tham số base tương đối. Đường dẫn được xử lý có thể sai hoặc lặp phần hậu tố. Hãy kiểm tra base đã cấu hình trước khi sửa filter; sử dụng nhất quán DN tương đối trong các thao tác dựa trên `ContextSource` có base.

Ở cấu hình thực tế, giá trị base đôi khi đến từ biến môi trường hoặc cấu hình ứng dụng. Vì vậy khi debug phải xác nhận **giá trị đã nạp khi chạy**, không chỉ đọc giá trị mặc định trong mã nguồn. `LdapTemplate` và các API như `LdapClient` đều cần một điểm xuất phát đúng để tìm kiếm trong cây; cách xây filter hay ánh xạ ODM không bù được một base sai.

## 3. Search scope thay đổi những entry có thể thấy

LDAP định nghĩa ba phạm vi tìm kiếm cơ bản, tương ứng với hằng số trong `javax.naming.directory.SearchControls`:

| Scope | Hằng số Java | Tìm ở đâu nếu base là `ou=people`? |
|---|---|---|
| **BASE / OBJECT** | `OBJECT_SCOPE` | Chỉ chính entry `ou=people` (nếu thỏa filter). |
| **ONELEVEL** | `ONELEVEL_SCOPE` | Các con trực tiếp: `uid=lan`, `ou=contractors`; **không** bao gồm base. |
| **SUBTREE** | `SUBTREE_SCOPE` | Base, các con trực tiếp và mọi hậu duệ, gồm cả `uid=minh` dưới `ou=contractors`. |

Xét lại cây ví dụ, với base `ou=people,dc=example,dc=com`:

```text
ou=people                     [BASE, SUBTREE]
├── uid=lan                   [ONELEVEL, SUBTREE]
└── ou=contractors            [ONELEVEL, SUBTREE]
    └── uid=minh              [SUBTREE]
```

Các scope chỉ giới hạn **ứng viên có thể xét**. Sau đó server mới áp dụng filter. Chẳng hạn:

- `BASE` với `(objectClass=*)` có thể trả về `ou=people`; với `(uid=lan)` thường trả về **0 entry** vì entry `ou=people` không có `uid=lan`.
- `ONELEVEL` với `(uid=lan)` tìm thấy Lan, nhưng `ONELEVEL` với `(uid=minh)` trả về **0 entry** do Minh nằm sâu hơn một cấp.
- `SUBTREE` với `(uid=minh)` có thể tìm thấy Minh; tuy nhiên nếu filter sai hoặc tài khoản không có quyền đọc entry, kết quả vẫn có thể rỗng.

Không nên chuyển mọi truy vấn sang `SUBTREE` một cách máy móc: vùng quét lớn hơn có thể làm tăng chi phí tìm kiếm và trả về entry ngoài nhánh nghiệp vụ mong muốn. Hãy chọn scope theo cấu trúc thư mục thực tế.

## 4. Quy trình debug khi truy vấn trả về kết quả sai

### Bước 1: Ghi lại đủ bốn thông tin

Trước khi sửa mã, xác định **base DN hiệu lực**, **filter**, **scope** và **bind identity/quyền truy cập**. Với ví dụ tìm Lan:

```text
ContextSource.base = dc=example,dc=com
search.base        = ou=people
effective base     = ou=people,dc=example,dc=com
filter             = (uid=lan)
scope              = ONELEVEL
bind DN            = uid=reader,ou=service,dc=example,dc=com
```

Thứ tự kiểm tra có ích vì cùng một biểu hiện “0 kết quả” có thể xuất phát từ nhiều nguyên nhân khác nhau.

### Bước 2: Xác nhận base có tồn tại

Dùng `ldapsearch` để loại trừ sai DN **trước khi** thay filter hoặc scope. Khác với tham số base tương đối của `LdapTemplate` ở trên, `ldapsearch -b` trong ví dụ nhận **DN đầy đủ**:

```bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.com:636 \
  -D "uid=reader,ou=service,dc=example,dc=com" -W \
  -b "ou=people,dc=example,dc=com" \
  -s base "(objectClass=*)" dn
```

`-W` nhắc nhập mật khẩu, tránh đưa mật khẩu vào lịch sử shell; kết nối LDAPS cần CA/chứng chỉ máy chủ hợp lệ. Nếu truy vấn trả DN của `ou=people`, base tồn tại và được tài khoản này nhìn thấy. Nếu server báo **`No such object` (LDAP result code 32)**, hãy kiểm tra tên RDN, thứ tự các cấp và hậu tố naming context. Một số server có thể che giấu entry không được phép xem; do đó lỗi 32 không luôn chứng minh entry hoàn toàn không tồn tại.

### Bước 3: Kiểm tra độ sâu và filter tách biệt

Đầu tiên tìm các con trực tiếp bằng filter rộng trong môi trường kiểm thử hoặc trên nhánh nhỏ:

```bash
ldapsearch -LLL -x -H ldaps://ldap.example.com:636 \
  -D "uid=reader,ou=service,dc=example,dc=com" -W \
  -b "ou=people,dc=example,dc=com" \
  -s one "(objectClass=*)" dn
```

Sau đó thử hai scope với **cùng base**, **cùng bind DN** và **cùng filter đích** để so sánh:

```bash
ldapsearch -LLL -x -H ldaps://ldap.example.com:636 \
  -D "uid=reader,ou=service,dc=example,dc=com" -W \
  -b "ou=people,dc=example,dc=com" \
  -s one "(uid=minh)" dn
```

```bash
ldapsearch -LLL -x -H ldaps://ldap.example.com:636 \
  -D "uid=reader,ou=service,dc=example,dc=com" -W \
  -b "ou=people,dc=example,dc=com" \
  -s sub "(uid=minh)" dn
```

Nếu `-s one` không thấy `uid=minh` nhưng `-s sub` thấy, vấn đề là **độ sâu search scope**. Nếu cả hai đều không thấy, thử tìm với filter đã biết đúng như `(objectClass=*)` trong phạm vi hẹp, rồi kiểm tra thuộc tính `uid`, quyền đọc hoặc nhánh DN thực tế. Không dùng truy vấn toàn bộ cây làm cách debug mặc định trên directory lớn.

### Bước 4: Chuyển kết quả đã xác nhận về Spring LDAP

Giữ nguyên **base tương đối**, **filter** và **scope** đã kiểm tra; thay đổi từng biến một để biết yếu tố nào giải quyết vấn đề:

```java
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;

// ContextSource.base đã được đặt thành dc=example,dc=com.
// ldapTemplate được inject từ cấu hình Spring LDAP.
List<String> names = ldapTemplate.search(
    "ou=people",
    "(uid=minh)",
    SearchControls.SUBTREE_SCOPE,
    (Attributes attrs) -> {
        var cn = attrs.get("cn");
        return cn == null ? "(không có cn)" : cn.get().toString();
    }
);
```

Ở đây `SUBTREE_SCOPE` cần thiết vì `uid=minh` nằm dưới `ou=contractors`. Trong code production, đừng ghép trực tiếp giá trị người dùng vào LDAP filter: dùng `LdapQueryBuilder`/cơ chế escape filter của Spring LDAP khi dựng điều kiện động. Escape **filter** và escape **DN** là hai bài toán khác nhau.

## 5. Đọc triệu chứng để khoanh vùng

| Triệu chứng | Giả thuyết nên kiểm tra | Phép kiểm tra nhanh |
|---|---|---|
| `NameNotFoundException` hoặc LDAP `No such object (32)` | Base không tồn tại, RDN sai, `ContextSource` base và search base bị cộng sai | `ldapsearch -s base` với DN đầy đủ; so sánh base hiệu lực. |
| Trả về 0 entry, không báo lỗi | Scope quá hẹp, filter không khớp, entry ngoài nhánh, quyền đọc hạn chế | Giữ nguyên bind DN, đổi `one` sang `sub` trong nhánh nhỏ; xác minh thuộc tính bằng công cụ LDAP. |
| Tìm được entry trực tiếp nhưng bỏ sót entry trong OU con | `ONELEVEL` không đi sâu | Dùng `SUBTREE` nếu yêu cầu nghiệp vụ bao gồm hậu duệ. |
| Trả về nhiều entry ở OU không mong muốn | Base quá cao trong cây hoặc `SUBTREE` quá rộng | Thu hẹp base tới đúng OU; cân nhắc `ONELEVEL`. |
| `InvalidNameException` / DN không hợp lệ | Dấu phẩy trong giá trị DN chưa escape hoặc thứ tự RDN sai | Phân tích DN bằng `LdapName`, đối chiếu DN chuẩn trên server. |
| LDAP `Invalid credentials (49)` | Bind DN/mật khẩu sai | Kiểm tra danh tính kết nối; lỗi xảy ra trước bước xét search scope. |
| LDAP `Insufficient access rights (50)` | Bind account thiếu quyền | Dùng quyền phù hợp và kiểm tra ACL; không “sửa” bằng cách mở rộng scope. |

Lưu ý: LDAP server có thể trả về kết quả khác nhau tùy ACL, alias, referral và giới hạn size/time. Nếu đã xác nhận DN, scope, filter đúng mà kết quả vẫn khác giữa `ldapsearch` và ứng dụng, hãy so sánh **server URL**, bind identity, cấu hình TLS, referral và giới hạn tìm kiếm của hai phía. Có thể bật mức `DEBUG` có kiểm soát cho `org.springframework.ldap` để xem ngữ cảnh lỗi trong ứng dụng, nhưng tránh ghi mật khẩu, dữ liệu nhạy cảm hay filter chứa thông tin cá nhân vào log production.

## 6. Bài thực hành tự kiểm tra

Với cây ví dụ và `ContextSource.base = dc=example,dc=com`, hãy dự đoán truy vấn nào tìm được kết quả, rồi kiểm tra trên một LDAP test server có dữ liệu tương ứng:

| Base truyền vào `LdapTemplate` | Filter | Scope | Kết quả dự kiến |
|---|---|---|---|
| `ou=people` | `(uid=lan)` | `ONELEVEL_SCOPE` | Tìm thấy `uid=lan`. |
| `ou=people` | `(uid=minh)` | `ONELEVEL_SCOPE` | Không thấy vì `uid=minh` sâu hơn một cấp. |
| `ou=people` | `(uid=minh)` | `SUBTREE_SCOPE` | Tìm thấy `uid=minh`. |
| `ou=contractors,ou=people` | `(uid=minh)` | `ONELEVEL_SCOPE` | Tìm thấy `uid=minh`. |
| `ou=people` | `(objectClass=*)` | `OBJECT_SCOPE` | Chỉ thấy chính entry `ou=people`. |

Kết quả trên giả định các entry tồn tại, có thuộc tính phù hợp và bind account được quyền tìm/đọc. Nếu không đúng dự kiến, hãy viết ra **base DN hiệu lực** của từng truy vấn rồi kiểm tra scope; chỉ sau đó mới phân tích filter và quyền truy cập.

### Ghi nhớ khi điều tra lỗi

Một truy vấn đúng cần hội đủ ba yếu tố: **đúng nhánh cây (base DN)**, **đúng độ sâu (scope)** và **đúng điều kiện (filter)**. Trong Spring LDAP, luôn tính base DN hiệu lực từ `ContextSource.base` cộng với base tương đối của lời gọi; trong `ldapsearch`, dùng DN đầy đủ để kiểm chứng. Tách từng thành phần và giữ cố định danh tính bind giúp tìm được nguyên nhân mà không phải sửa truy vấn theo cảm tính.
