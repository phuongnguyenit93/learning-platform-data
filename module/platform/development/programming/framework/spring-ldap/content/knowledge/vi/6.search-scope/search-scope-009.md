# Đánh giá phạm vi tìm kiếm trước khi chạy trên DIT lớn

Trong LDAP, một truy vấn có thể đúng về mặt cú pháp nhưng vẫn không phù hợp để chạy trên thư mục lớn: chọn search base ở gần gốc, để scope là toàn bộ subtree hoặc dùng filter quá rộng có thể khiến máy chủ phải xem xét nhiều entry, trả dữ liệu lớn và ảnh hưởng các ứng dụng cùng dùng directory. Ngược lại, scope quá hẹp có thể bỏ sót entry hợp lệ. Bởi vậy, trước khi gọi `LdapTemplate.search(...)`, cần đánh giá **vị trí bắt đầu**, **độ sâu tìm kiếm**, **điều kiện lọc**, **số lượng dữ liệu dự kiến** và **giới hạn vận hành**.

Bài học thuộc chương **Search scope** của Spring LDAP, tập trung vào phương pháp ra quyết định khi **Directory Information Tree (DIT)** có nhiều cấp OU và lượng entry lớn. Sau bài này, bạn có thể:

- Chọn đúng `OBJECT_SCOPE`, `ONELEVEL_SCOPE` hoặc `SUBTREE_SCOPE` cho yêu cầu nghiệp vụ cụ thể.
- Phân biệt phạm vi entry được xét với độ chọn lọc của filter và tập thuộc tính trả về.
- Ước lượng rủi ro trước khi chạy truy vấn rộng, lập kế hoạch kiểm tra trên môi trường thử nghiệm.
- Cấu hình search scope, size limit, time limit và returning attributes trong Spring LDAP.
- Đọc kết quả có giới hạn đúng cách, phát hiện truy vấn trả thiếu và đề xuất cách thu hẹp an toàn.

## 1. Bối cảnh: DIT lớn không phải một danh sách phẳng

Một directory của doanh nghiệp có thể chứa hàng trăm OU và hàng trăm nghìn entry ở nhiều tầng khác nhau:

```text
dc=example,dc=org
├── ou=people
│   ├── ou=employees
│   │   ├── ou=hanoi
│   │   │   ├── uid=lan
│   │   │   └── uid=minh
│   │   └── ou=hochiminh
│   │       └── uid=hoa
│   ├── ou=contractors
│   │   └── uid=an
│   └── ou=alumni
│       └── uid=old
├── ou=groups
│   ├── cn=developers
│   └── cn=operators
└── ou=services
    └── uid=application-bot
```

Từ cây trên, xét cùng filter `(objectClass=inetOrgPerson)`:

| Search base đầy đủ | Scope | Phạm vi máy chủ được yêu cầu xem xét |
| --- | --- | --- |
| `dc=example,dc=org` | `SUBTREE_SCOPE` | Root và tất cả nhánh people, groups, services cùng cấp con |
| `ou=people,dc=example,dc=org` | `SUBTREE_SCOPE` | People cùng tất cả OU và entry bên dưới |
| `ou=people,dc=example,dc=org` | `ONELEVEL_SCOPE` | Chỉ ba OU employees, contractors, alumni; không đến entry người dùng ở cấp sâu hơn |
| `ou=hanoi,ou=employees,ou=people,dc=example,dc=org` | `ONELEVEL_SCOPE` | Chỉ Lan và Minh là con trực tiếp |
| `uid=lan,ou=hanoi,ou=employees,ou=people,dc=example,dc=org` | `OBJECT_SCOPE` | Chỉ xét đúng entry Lan |

**Scope** quyết định phạm vi ứng viên theo cấu trúc cây, còn **filter** quyết định entry nào khớp điều kiện. Máy chủ có thể dùng index để tối ưu cách tìm ứng viên, nên bảng trên **không khẳng định** server phải đọc tuần tự từng entry. Tuy nhiên, yêu cầu search trên một subtree rộng vẫn cho phép máy chủ tìm trong toàn vùng đó và có thể phát sinh chi phí lớn.

Các con số về quy mô trong bài chỉ là tình huống minh họa, không phải số đo của một LDAP server thật.

## 2. Ba scope: xác định chính xác độ sâu trước khi đo hiệu năng

LDAP định nghĩa ba phạm vi chuẩn, được JNDI và Spring LDAP biểu diễn qua `SearchControls`:

| Scope LDAP | Hằng Java | Bao gồm base? | Bao gồm con trực tiếp? | Bao gồm cháu/chắt? |
| --- | --- | --- | --- | --- |
| `baseObject` | `SearchControls.OBJECT_SCOPE` | Có | Không | Không |
| `singleLevel` | `SearchControls.ONELEVEL_SCOPE` | Không | Có | Không |
| `wholeSubtree` | `SearchControls.SUBTREE_SCOPE` | Có | Có | Có |

Ví dụ với base là `ou=people,dc=example,dc=org`:

- `OBJECT_SCOPE` chỉ kiểm tra entry `ou=people`.
- `ONELEVEL_SCOPE` chỉ kiểm tra các entry `ou=employees`, `ou=contractors` và `ou=alumni`, dù filter có thể không khớp chúng.
- `SUBTREE_SCOPE` xem xét cả `ou=people` và mọi entry ở các cấp sâu hơn, bao gồm Lan, Minh, Hoa, An và Old.

Không có chuyện filter `(uid=lan)` tự khiến one-level đi sâu xuống `ou=hanoi`. Nếu cần tìm Lan từ `ou=people` mà không biết người dùng ở OU con nào, chọn subtree phù hợp về mặt **tính đầy đủ**; sau đó mới phải đánh giá chi phí và phương án thay thế.

**Search base phải là một DN tồn tại** mà tài khoản tìm kiếm có thể truy cập theo chính sách server. Nếu base không tồn tại, server có thể trả lỗi `noSuchObject`; nếu không có entry khớp trong phạm vi, tìm kiếm có thể trả danh sách rỗng. Hai tình huống cần được chẩn đoán riêng.

## 3. Quy trình năm câu hỏi trước khi gửi truy vấn

Trước khi quyết định `SUBTREE_SCOPE` cho một directory lớn, hãy trả lời:

| Câu hỏi | Điều cần xác minh | Ảnh hưởng đến cách tìm |
| --- | --- | --- |
| **1. Cần dữ liệu nào?** | Một DN đã biết, các con của một OU, hay tất cả người thuộc nhiều OU? | Chọn OBJECT, ONELEVEL hoặc SUBTREE |
| **2. Chúng nằm ở đâu?** | DN đầy đủ, RDN của các nhánh, độ sâu và nhánh nào có dữ liệu mục tiêu | Đặt search base gần dữ liệu cần thiết |
| **3. Filter có chọn lọc không?** | Truy vấn một `uid` cụ thể, nhóm bộ phận, hay mọi `objectClass`? | Thu hẹp tập kết quả logic |
| **4. Quy mô và giới hạn?** | Số entry ước tính, index, quota thời gian/kích thước, giới hạn kết nối | Đặt giới hạn, chia truy vấn hoặc phân trang |
| **5. Nếu thiếu/trùng/không đủ kết quả thì sao?** | Cách kiểm chứng, báo lỗi, xử lý kết quả một phần, phân quyền | Tránh quyết định nghiệp vụ trên kết quả sai |

**Đặt vấn đề theo nhu cầu nghiệp vụ trước:** “Lấy các tài khoản có `uid` bằng giá trị X” khác với “Xuất toàn bộ danh bạ”, và “Liệt kê OU trực thuộc people” khác với “Liệt kê tất cả người dùng dưới people”. Cùng một search base nhưng scope phù hợp có thể khác hoàn toàn.

Quy trình quyết định gợi ý:

```text
Đã biết chính xác DN?
├── Có → Cân nhắc lookup / base-object; không cần duyệt subtree.
└── Không
    ├── Chỉ cần entry con trực tiếp của một OU?
    │   └── Có → ONELEVEL_SCOPE tại đúng OU.
    └── Cần entry ở nhiều cấp?
        ├── Biết rõ từng OU đích?
        │   └── Có → Nhiều truy vấn phạm vi hẹp theo từng OU.
        └── Không → Cân nhắc SUBTREE_SCOPE với filter chọn lọc,
                     giới hạn truy vấn và kiểm thử trước.
```

Đây là cách **chọn phạm vi theo chức năng**, không phải công thức bảo đảm tốc độ. Một one-level search trên OU có rất nhiều con trực tiếp vẫn có thể tốn tài nguyên; ngược lại, subtree search theo attribute được index tốt có thể thực hiện hiệu quả.

## 4. Ước lượng chi phí theo cấu trúc và dữ liệu

Hãy giả sử (chỉ là số liệu minh họa) dưới `ou=people` có:

- 4 OU chứa người dùng trực tiếp;
- mỗi OU có khoảng 20.000 tài khoản;
- tổng cộng khoảng 80.000 tài khoản, chưa kể OU trung gian.

Nếu yêu cầu chỉ là “Tìm tài khoản `uid=lan` thuộc nhánh Hanoi”, các lựa chọn có mức rộng khác nhau:

| Phương án | Base + scope | Nhận xét |
| --- | --- | --- |
| A | `dc=example,dc=org` + subtree | Bao phủ cả những nhánh không liên quan |
| B | `ou=people,dc=example,dc=org` + subtree | Bỏ nhánh groups/services, vẫn bao phủ toàn bộ people |
| C | `ou=hanoi,ou=employees,ou=people,dc=example,dc=org` + one-level | Phù hợp nếu tài khoản nằm trực tiếp dưới OU Hanoi |
| D | Lookup DN đầy đủ đã biết | Không cần chạy search nếu đã có DN chắc chắn |

Trong cùng điều kiện, **A thường có phạm vi logic rộng hơn B, B rộng hơn C**. Nhưng không thể suy ra thời gian chạy hay số entry được đọc từ các nhánh chỉ bằng số OU; máy chủ có thể sử dụng index, cache và tối ưu truy vấn.

Để ước lượng đúng hơn, cần biết:

1. **Phân bố entry:** số người ở từng OU, độ sâu phổ biến và OU mới được tạo theo thời gian.
2. **Tính chọn lọc:** `(uid=lan)` có thể khớp rất ít entry; `(objectClass=person)` có thể khớp phần lớn người dùng.
3. **Index của server:** `uid`, `mail`, `member`, `objectClass` hay thuộc tính tùy biến có được index theo matching rule cần dùng hay không.
4. **Hình thức tìm:** equality thường khác substring rộng `(cn=*an*)`; NOT và OR trên nhiều điều kiện có thể làm tối ưu khó hơn.
5. **Kích thước kết quả:** truy vấn trả vài chục entry với 2 attribute khác nhiều so với xuất hàng vạn entry cùng attribute nhiều giá trị hoặc dữ liệu nhị phân.

Index là đặc tính triển khai và cấu hình của LDAP server. **Không được giả định** mọi server hoặc mọi attribute đều đã có index phù hợp. Khi cần dữ liệu này, trao đổi với người quản trị thư mục hoặc dùng công cụ giám sát của server trên môi trường được phép.

### Kết quả ít không luôn đồng nghĩa truy vấn rẻ

Filter `(&(objectClass=inetOrgPerson)(uid=lan))` có thể chỉ trả một entry, nhưng chi phí thực thi phụ thuộc server. Ngược lại, filter rộng bị giới hạn 10 kết quả không chứng minh truy vấn chỉ tốn công xử lý 10 entry. **Size limit giới hạn đầu ra**, không thay cho lựa chọn base/scope/filter hợp lý.

## 5. Chọn search base: thu hẹp ở cấp DN trước

Giả sử ứng dụng Spring LDAP có `ContextSource.base = "dc=example,dc=org"`. Khi đó search base truyền cho `LdapTemplate.search(...)` thường là **DN tương đối**:

| Vị trí muốn tìm trên server | Search base tương đối trong Spring LDAP |
| --- | --- |
| `ou=people,dc=example,dc=org` | `ou=people` |
| `ou=hanoi,ou=employees,ou=people,dc=example,dc=org` | `ou=hanoi,ou=employees,ou=people` |
| `dc=example,dc=org` | DN rỗng `""` |

Nếu đem nguyên DN đầy đủ `ou=people,dc=example,dc=org` vào `LdapTemplate` đã có base, hậu tố `dc=example,dc=org` có thể bị áp dụng hai lần. Khi đó truy vấn sai dù scope và filter đều đúng.

**Không chọn base chỉ vì đó là root đang có sẵn trong cấu hình.** Nếu mục đích là đọc nhóm ở `ou=groups` thì search base nên bắt đầu ở groups; nếu mục đích là đọc nhân viên Hanoi thì bắt đầu ở OU Hanoi. Với hệ thống có nhiều tenant/đơn vị, giới hạn search base theo tenant có thể giúp ngăn truy vấn lãng phí, nhưng **không thay thế phân quyền ACL** của LDAP server.

Khi base hoặc RDN được chọn theo dữ liệu đầu vào, cần xây DN bằng API kiểu `LdapName`/`LdapNameBuilder` và giới hạn nhánh hợp lệ. Không nối chuỗi không kiểm soát để tạo DN rồi dùng làm search base.

## 6. Filter chọn lọc và thuộc tính trả về

Sau khi chọn base/scope, viết **filter nhỏ nhất đáp ứng yêu cầu** và chỉ yêu cầu các attribute thực sự cần.

Ví dụ:

```ldap
(&(objectClass=inetOrgPerson)(uid=lan))
```

Đây thường là lựa chọn rõ hơn `(objectClass=*)` nếu mục tiêu là lấy tài khoản theo `uid`. Tuy nhiên, filter equality chỉ thực sự hiệu quả khi server xử lý phù hợp với schema/matching rule và index.

Khi có đầu vào người dùng, **không ghép thô**:

```java
// Tránh: userUid có thể chứa '*', '(', ')' hoặc ký tự đặc biệt.
String filter = "(&(objectClass=inetOrgPerson)(uid=" + userUid + "))";
```

Sử dụng builder để escape **giá trị filter**:

```java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

AndFilter filter = new AndFilter();
filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
filter.and(new EqualsFilter("uid", userUid));

String encodedFilter = filter.encode();
```

Với một truy vấn “liệt kê danh sách”, bộ lọc `(objectClass=inetOrgPerson)` có thể là yêu cầu đúng, nhưng cần cân nhắc lượng dữ liệu thực tế. Nếu đây là một thao tác xuất dữ liệu quy mô lớn, hãy thiết kế riêng khả năng phân trang, checkpoint và báo cáo kết quả; đừng dùng một lệnh tìm kiếm vô hạn rồi giữ toàn bộ kết quả trong bộ nhớ.

**Projection** cũng quan trọng: ví dụ ứng dụng chỉ cần `uid` và `cn`, nên yêu cầu đúng hai thuộc tính. Tránh tải `jpegPhoto`, `userCertificate` hoặc những attribute lớn không phục vụ màn hình hiện tại. Điều này giảm dữ liệu truyền đi, nhưng không tự làm thay đổi search scope.

## 7. Spring LDAP: cấu hình scope và giới hạn cho truy vấn có kiểm soát

Ví dụ dưới đây sử dụng Java 17+, `LdapTemplate` và `SearchControls`. Giả định `ContextSource` đã cấu hình base `dc=example,dc=org` và kết nối LDAP an toàn.

```java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

record DirectoryPerson(String uid, String cn) {}

public final class PeopleDirectory {
    private final LdapTemplate ldapTemplate;

    public PeopleDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryPerson> findHanoiDirectUsers(String requestedUid) {
        // Search base được cố định ở OU phù hợp với yêu cầu nghiệp vụ.
        String relativeBase = "ou=hanoi,ou=employees,ou=people";

        // Giá trị requestedUid được escape bằng EqualsFilter.
        AndFilter filter = new AndFilter();
        filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        filter.and(new EqualsFilter("uid", requestedUid));

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
        controls.setReturningAttributes(new String[] {"uid", "cn"});
        controls.setCountLimit(50); // Giới hạn số entry client yêu cầu.
        controls.setTimeLimit(5_000); // Giới hạn thời gian tìm kiếm, đơn vị ms.

        return ldapTemplate.search(
            relativeBase,
            filter.encode(),
            controls,
            (AttributesMapper<DirectoryPerson>) attributes -> {
                Attribute uidAttr = attributes.get("uid");
                Attribute cnAttr = attributes.get("cn");

                String uid = uidAttr == null
                    ? null : (String) uidAttr.get();
                String cn = cnAttr == null
                    ? null : (String) cnAttr.get();

                return new DirectoryPerson(uid, cn);
            }
        );
    }
}
```

Để code trên phù hợp với dữ liệu thật, cần kiểm tra đối tượng `inetOrgPerson` nằm **trực tiếp** dưới OU Hanoi và tài khoản có quyền đọc hai thuộc tính. `AttributesMapper` xử lý trường bị ẩn hoặc vắng mặt bằng giá trị `null` trong ví dụ; tầng nghiệp vụ cần kiểm tra các trường bắt buộc trước khi sử dụng.

Ý nghĩa của từng giới hạn:

| Thiết lập | Mục đích | Điều không được suy ra |
| --- | --- | --- |
| `ONELEVEL_SCOPE` | Chỉ tìm con trực tiếp của OU Hanoi | Không đảm bảo tất cả người trong nhiều OU đều được tìm thấy |
| `setReturningAttributes({"uid","cn"})` | Chỉ yêu cầu hai thuộc tính | Không thu hẹp tập entry mà filter có thể khớp |
| `setCountLimit(50)` | Đặt giới hạn số entry kết quả theo yêu cầu tìm kiếm | Không chứng minh thực tế chỉ có tối đa 50 entry |
| `setTimeLimit(5_000)` | Đặt thời hạn tìm kiếm tính bằng mili giây thông qua JNDI | Không phải cơ chế kiểm soát tuyệt đối CPU/I/O của server |
| `filter.encode()` | Mã hóa điều kiện đã tạo bằng filter builder | Không thay thế kiểm tra quyền và giới hạn search base |

Giới hạn JNDI và giới hạn LDAP server có thể tương tác khác nhau tùy implementation. Khi bị áp giới hạn, client **có thể nhận lỗi** (chẳng hạn size/time limit exceeded) hoặc chỉ có dữ liệu một phần; ứng dụng phải coi kết quả bị cắt là **chưa đầy đủ**. Không được mặc nhiên báo “không có entry khác” khi vừa chạm giới hạn.

### Khi cần tìm toàn bộ subtree

Nếu nghiệp vụ thực sự cần tìm mọi người nằm trong nhiều OU con dưới `ou=people`, thay đổi có chủ đích:

```java
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
```

và chọn search base `ou=people`. Trước khi mở rộng này trên DIT lớn, hãy xác nhận filter đủ chọn lọc, người dùng cần dữ liệu ở mọi tầng, yêu cầu phân trang và giới hạn server, rồi kiểm thử tải ở môi trường phù hợp. **Thay scope có thể làm thay đổi tập kết quả**, không chỉ thời gian chạy.

### Với Spring LDAP query builder

`LdapQueryBuilder` hỗ trợ xây search base và filter an toàn. Tuy nhiên, khi yêu cầu kiểm soát rõ `SearchControls.ONELEVEL_SCOPE`, ví dụ dùng overload của `LdapTemplate.search` cùng `SearchControls` giúp mục đích thể hiện trực tiếp. Đừng suy luận scope chỉ từ `query().base("ou=people")`: base quyết định vị trí, scope quyết định độ sâu.

## 8. Thử nghiệm theo từng bước trước khi chạy trên production

Với DIT nhiều entry, cần xác minh cả **tính đúng đắn** lẫn **đặc tính vận hành** trước khi mở phạm vi. Một quy trình thực tế:

1. **Lấy sơ đồ DIT từ nguồn đáng tin:** ghi các DN gốc, OU trung gian và vị trí entry mẫu. Không cần xuất toàn bộ directory chỉ để hiểu cấu trúc.
2. **Chọn các trường hợp kiểm chứng:** một entry ngay dưới base, một entry ở OU con sâu hơn, một entry ngoài nhánh và một entry không khớp filter.
3. **Chạy trên môi trường thử nghiệm/nhánh hạn chế:** bắt đầu từ base hẹp, scope nhỏ và filter chọn lọc. Cấp quyền bind đọc tối thiểu.
4. **Giới hạn kết quả và thời gian:** dùng size/time limit; chỉ yêu cầu DN hoặc vài attribute cần kiểm tra. Nếu bị chặn bởi giới hạn, ghi nhận là một phép thử chưa đầy đủ.
5. **So sánh tính đúng:** xác minh danh sách DN thực tế với tập mong đợi theo base/scope/filter, kể cả trường hợp phải có và phải vắng mặt.
6. **Đo chi phí:** theo dõi latency, kích thước kết quả, số entry được server thực sự kiểm tra khi server cung cấp metric, tải CPU/I/O và ảnh hưởng các client khác.
7. **Mở dần phạm vi nếu cần:** từ OU nhỏ sang OU lớn hơn, tăng số lượng truy vấn có kiểm soát; quyết định dựa trên đo đạc và giới hạn vận hành của đơn vị.

**Không đánh đồng một lần chạy “nhanh” với khả năng an toàn khi dùng hàng loạt.** Nhiều truy vấn subtree chạy đồng thời, đặc biệt trên attribute không được index, có thể tạo tải đáng kể dù một truy vấn riêng lẻ hoàn thành sớm.

### Kiểm tra bằng ldapsearch

Lệnh minh họa dùng OpenLDAP command-line client, với địa chỉ và DN giả định:

```bash
ldapsearch -x -LLL -H ldaps://ldap.example.org:636 \
  -D "cn=readonly,ou=system,dc=example,dc=org" -W \
  -b "ou=hanoi,ou=employees,ou=people,dc=example,dc=org" \
  -s one -z 20 -l 5 \
  "(&(objectClass=inetOrgPerson)(uid=lan))" dn uid cn
```

Ở đây `-s one` chỉ scope một cấp, `-z 20` yêu cầu size limit và `-l 5` yêu cầu time limit tính bằng giây theo cú pháp công cụ. `-b` là **DN đầy đủ** trên server, khác với DN tương đối truyền vào `LdapTemplate` khi `ContextSource` đã có base. `-W` yêu cầu nhập mật khẩu khi chạy, tránh đặt mật khẩu trực tiếp vào tham số command.

Khi kiểm tra bằng công cụ ngoài, dùng đúng **tài khoản có quyền tương đương** với ứng dụng nếu mục tiêu là so sánh kết quả. Nếu LDAP browser dùng tài khoản quản trị còn ứng dụng dùng tài khoản chỉ đọc, khác biệt kết quả có thể đến từ ACL, không phải search scope.

**Kết quả thử nghiệm giới hạn không phải phép đếm đầy đủ.** Nếu yêu cầu tối đa 20 entry và nhận 20 entry, không thể kết luận tổng cộng chỉ có 20 entry. Phải nhận biết trạng thái kết thúc truy vấn và có chiến lược phân trang nếu cần đầy đủ.

## 9. Khi kết quả lớn: phân trang, chia nhánh và kiểm soát lỗi

Nếu nghiệp vụ yêu cầu đọc nhiều entry, có thể kết hợp:

- **Phân trang kết quả (paged results):** dùng extension/control mà LDAP server hỗ trợ, với kích thước trang được kiểm soát. Spring LDAP hỗ trợ xử lý paged results qua các API điều khiển tìm kiếm tương ứng; cần cấu hình, kiểm thử và theo dõi cookie/trạng thái kết thúc theo server cụ thể.
- **Chia truy vấn theo OU:** nếu cấu trúc directory ổn định và nghiệp vụ cho phép, tìm theo các nhánh đã biết để giảm phạm vi mỗi lượt và dễ phục hồi khi lỗi.
- **Giới hạn song song:** số truy vấn nhỏ lẻ chạy đồng thời quá lớn cũng tạo tải; dùng giới hạn concurrency, timeout và chính sách retry có kiểm soát.
- **Chỉ lấy dữ liệu cần thiết:** khi màn hình chỉ cần `uid`, `cn` thì không yêu cầu mọi attribute hoặc dữ liệu nhị phân lớn.
- **Lưu trạng thái tiến độ phù hợp:** với tác vụ xuất dữ liệu dài, cần cách tiếp tục mà không coi một kết quả bị cắt là đã hoàn thành.

Phân trang giúp chia **lượng kết quả nhận về mỗi lượt**, nhưng không tự làm filter hiệu quả hoặc scope an toàn hơn. Nó cũng không mặc nhiên tạo snapshot nhất quán nếu directory thay đổi giữa các trang; không được coi quá trình xuất dữ liệu đang thay đổi là một ảnh chụp giao dịch trừ khi giải pháp server có bảo đảm đó.

Nếu truy vấn gặp `SizeLimitExceededException`, `TimeLimitExceededException`, lỗi kết nối hoặc LDAP server báo giới hạn quản trị, phải báo rõ truy vấn **không hoàn tất**. Tránh tự động bỏ giới hạn hoặc mở scope rộng hơn để “sửa” lỗi. Nên kiểm tra ràng buộc nghiệp vụ, filter, index, quyền và quota vận hành trước.

## 10. Các lỗi thường gặp khi đánh giá scope

| Dấu hiệu | Phân tích | Cách xử lý |
| --- | --- | --- |
| One-level tại `ou=people` không thấy tài khoản | Người dùng nằm dưới `ou=employees/ou=hanoi`, sâu nhiều cấp | Chọn base sâu hơn hoặc subtree nếu cần |
| Subtree tại root trả nhiều entry không liên quan | Search base quá rộng | Chuyển base đến OU chứa dữ liệu mục tiêu |
| Filter có `uid=lan` nhưng tìm không thấy | Sai base/scope, schema, ACL hoặc giá trị | Kiểm tra DN thực, scope, matching rule, ACL |
| Tìm thấy vài chục entry rồi ngừng | Client/server chạm giới hạn size/time hoặc paging chưa hoàn tất | Đọc trạng thái kết thúc, thiết kế phân trang |
| Truy vấn ít kết quả nhưng vẫn chậm | Có thể thiếu index, filter kém chọn lọc, server đang tải | Đo trên server, xem index và đặc tính filter |
| Mọi thứ chạy nhanh trên thử nghiệm nhưng production quá tải | DIT lớn hơn, truy vấn đồng thời, phân bố OU khác | Đo có kiểm soát với quy mô đại diện và concurrency |
| Lấy đủ DN nhưng thiếu `cn` | Projection, ACL hoặc attribute vắng mặt | Kiểm tra returning attributes và quyền đọc |
| Truy vấn bằng lệnh ngoài đúng nhưng Spring trả sai | `ContextSource.base` và search base tương đối bị hiểu nhầm | Kiểm tra hai base và DN đầy đủ |
| Dùng size limit làm điều kiện “chỉ có N người” | Kết quả có thể bị cắt hoặc server trả lỗi limit | Phân biệt kết quả hoàn tất với kết quả giới hạn |
| Coi search scope là phân quyền dữ liệu | Scope chỉ mô tả tập tìm kiếm | Thiết lập ACL trên LDAP server, TLS, quyền bind tối thiểu |

Lưu ý sự khác nhau giữa các nguyên nhân:

- **Sai scope:** entry có tồn tại và khớp filter, nhưng nằm ngoài phạm vi.
- **Sai filter:** entry nằm trong phạm vi nhưng không thỏa điều kiện.
- **Không đủ quyền:** entry hoặc attribute bị che bởi ACL, dù DN/scope/filter có thể đúng.
- **Giới hạn hệ thống:** kết quả không đầy đủ, có thể kèm mã lỗi hoặc exception.

Một cách chẩn đoán hiệu quả là giữ nguyên **hai yếu tố** và thay **một yếu tố** mỗi lần (base, scope hoặc filter) trên nhánh thử nghiệm. Điều này giúp xác định nguồn lỗi mà không đồng thời nới rộng mọi tham số.

## 11. Tình huống thiết kế: tra cứu người dùng theo mã nhân viên

Một API cần tìm `uid=lan` trong tổ chức có 80.000 người dùng phân bố dưới các OU địa điểm. Có hai khả năng nghiệp vụ:

**Trường hợp A – API luôn biết địa điểm:** yêu cầu có `location=hanoi` đã được xác thực với danh sách địa điểm hợp lệ. Ứng dụng có thể chọn `ou=hanoi,ou=employees,ou=people` với one-level và filter `(uid=lan)` nếu dữ liệu người dùng nằm trực tiếp dưới OU địa điểm. Cách này mô tả đúng phạm vi cần xem.

**Trường hợp B – API không biết địa điểm:** cùng một `uid` có thể nằm ở bất kỳ OU nào dưới `ou=employees`. One-level tại `ou=employees` sẽ bỏ sót người dùng ở các OU con. Các lựa chọn gồm subtree với filter chọn lọc và giới hạn phù hợp, hoặc một chiến lược định vị DN đã được hệ thống thiết kế trước. **Không nên tùy tiện chọn one-level chỉ vì có vẻ nhẹ hơn** nếu yêu cầu phải tìm trên mọi địa điểm.

Trước khi đưa một trong hai phương án lên production, cần trả lời:

1. `uid` có thực sự được bảo đảm duy nhất trong vùng dữ liệu nghiệp vụ không, hay có thể trùng ở các nhánh?
2. Directory có các OU ngoại lệ, cấp con mới hoặc entry di chuyển theo thời gian không?
3. Attribute `uid` có được index cho equality search trên server đang dùng không?
4. Tải truy vấn đồng thời dự kiến và giới hạn size/time do server áp dụng là bao nhiêu?
5. Kết quả có cần đầy đủ tuyệt đối hay chỉ trả về entry đầu tiên đã xác định DN?

Nếu cùng `uid` có thể xuất hiện dưới nhiều OU, API phải quy định rõ xử lý **0, 1 hoặc nhiều kết quả**, không âm thầm lấy phần tử đầu tiên rồi coi đó là người duy nhất.

## 12. Bài thực hành tự kiểm tra

Cho cây thử nghiệm:

```text
dc=example,dc=org
└── ou=people
    ├── ou=employees
    │   ├── ou=hanoi
    │   │   ├── uid=lan     (inetOrgPerson)
    │   │   └── uid=minh    (inetOrgPerson)
    │   └── ou=hochiminh
    │       └── uid=hoa     (inetOrgPerson)
    └── ou=contractors
        └── uid=an          (inetOrgPerson)
```

Giả định tất cả entry cần thiết tồn tại, quyền đọc đầy đủ, mọi người dùng có `uid` và `ContextSource.base = "dc=example,dc=org"`.

**Câu hỏi:**

1. Với search base `ou=people` và `ONELEVEL_SCOPE`, filter `(objectClass=inetOrgPerson)` có trả về Lan không? Vì sao?
2. Muốn tìm đúng các con trực tiếp của OU Hanoi, dùng search base tương đối và scope nào?
3. Muốn tìm tất cả bốn người dùng từ `ou=people`, nên dùng scope nào? Filter có thể là gì?
4. Nếu `setCountLimit(2)` và nhận hai entry, có thể khẳng định chỉ có hai người dùng không?
5. Nếu chỉ cần `uid` và `cn`, nên yêu cầu những attribute nào? Điều này có thay đổi scope không?
6. Truy vấn subtree trả đúng một entry nhưng chậm bất thường. Có thể kết luận luôn rằng subtree đang quét mọi entry không?
7. API nhận giá trị `uid` từ người dùng: vì sao nên dùng `EqualsFilter` thay vì nối chuỗi thô?

**Đáp án:**

1. Không. One-level tại `ou=people` chỉ xét `ou=employees` và `ou=contractors`, không đến các entry ở cấp sâu hơn.
2. Base `ou=hanoi,ou=employees,ou=people`, scope `ONELEVEL_SCOPE`. Từ base này, Lan và Minh là con trực tiếp.
3. `SUBTREE_SCOPE` dưới `ou=people`; filter `(objectClass=inetOrgPerson)` có thể chọn bốn người dùng trong ví dụ.
4. Không. Giới hạn 2 có thể cắt kết quả hoặc gây lỗi limit; cần xác nhận truy vấn hoàn tất và xử lý phân trang/giới hạn khi cần.
5. Yêu cầu `uid` và `cn`. Projection chỉ thay đổi các thuộc tính trả về, không đổi phạm vi entry.
6. Không. Máy chủ có thể dùng index hoặc cơ chế tối ưu khác; phải kiểm tra số liệu và cấu hình thực tế thay vì kết luận từ một kết quả.
7. `EqualsFilter` escape đúng ký tự đặc biệt trong giá trị, giảm nguy cơ LDAP filter injection và truy vấn sai cấu trúc.

## 13. Checklist trước khi chạy trên DIT lớn

| Nội dung cần xác nhận | Dấu hiệu đủ điều kiện |
| --- | --- |
| **Mục đích nghiệp vụ** | Đã mô tả entry nào phải được tìm và entry nào phải bị loại |
| **DIT và search base** | Biết DN đích, các cấp OU và search base tương đối với `ContextSource` |
| **Search scope** | Đã kiểm tra OBJECT/ONELEVEL/SUBTREE khớp độ sâu thực tế |
| **Filter** | Có điều kiện cần thiết, escape giá trị động, tên attribute được kiểm soát |
| **Schema và index** | Hiểu matching rule và xác nhận đặc tính index khi cần |
| **Projection** | Chỉ yêu cầu thuộc tính ứng dụng sử dụng |
| **Giới hạn** | Có size/time limit, chính sách phân trang và phát hiện kết quả không đầy đủ |
| **Phân quyền và kết nối** | Bind account tối thiểu, ACL server, TLS và chứng chỉ hợp lệ |
| **Kiểm thử và giám sát** | Có trường hợp đúng/sai mẫu, số đo trên môi trường đại diện và ngưỡng vận hành |
| **Xử lý lỗi** | Phân biệt không tìm thấy, nhiều kết quả, thiếu quyền, timeout và limit exceeded |

## 14. Tổng kết và tài liệu tham khảo

Trước khi tìm kiếm trên DIT lớn, hãy hiểu **đúng hình dạng cây dữ liệu**, chọn **search base gần dữ liệu cần thiết**, quyết định **scope theo độ sâu nghiệp vụ**, rồi dùng **filter chọn lọc** và **projection vừa đủ**. `OBJECT_SCOPE` chỉ xét chính base, `ONELEVEL_SCOPE` chỉ xét con trực tiếp, còn `SUBTREE_SCOPE` xét cả base và mọi cấp con. Không dùng scope hẹp đến mức mất dữ liệu, cũng không mặc định tìm từ root khi có thể chọn OU cụ thể.

Trong Spring LDAP, `ContextSource` cung cấp base context; `LdapTemplate.search` dùng search base tương đối, filter và `SearchControls`. Giới hạn số lượng/thời gian, phân trang, ACL và TLS giúp kiểm soát hoạt động, nhưng **không thay cho việc đo kiểm trên directory server thực tế**. Truy vấn bị giới hạn không được xem là đã tìm đủ dữ liệu.

Tài liệu tham khảo:

- [RFC 4511 – Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest, scope, filter, size/time limits và mã kết quả.
- [RFC 4515 – LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp và escaping trong filter.
- [JNDI SearchControls (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/SearchControls.html): scope, returning attributes, count limit và time limit.
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, `LdapTemplate`, filter builders và phân trang kết quả.
