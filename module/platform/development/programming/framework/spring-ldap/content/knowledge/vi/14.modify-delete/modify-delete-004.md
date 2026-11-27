# Xóa entry lá và xóa nhánh có entry con trong Spring LDAP

Trong dịch vụ thư mục LDAP, xóa một tài khoản nằm ở cuối cây là thao tác tương đối đơn giản. Nhưng nếu ứng dụng yêu cầu xóa cả một phòng ban, một nhánh lưu trữ hoặc một vùng dữ liệu có nhiều entry con, thao tác xóa thông thường sẽ bị máy chủ từ chối. Khi chuyển sang xóa đệ quy, nguy cơ mới xuất hiện: một DN được xác định sai có thể khiến ứng dụng xóa nhiều entry ngoài dự kiến, còn việc xóa giữa chừng có thể để lại một cây chưa được dọn sạch.

Bài học thuộc chương **Modify và delete** của **Spring LDAP**. Bạn sẽ phân biệt entry lá và entry cha, hiểu nguyên tắc LDAP Delete, thực hiện xóa bằng `LdapTemplate` và JNDI, tổ chức xóa nhánh theo thứ tự con trước cha, cũng như xử lý lỗi, quyền truy cập và kiểm thử an toàn. Các ví dụ giả định ứng dụng đã cấu hình `ContextSource` với base DN `dc=example,dc=org` và LDAP server cho phép thao tác tương ứng.

## 1. Entry lá và nhánh có entry con

LDAP tổ chức các entry thành **Directory Information Tree (DIT)**. Mỗi entry có một **Distinguished Name (DN)**; DN của entry con kéo dài bằng cách thêm Relative Distinguished Name (RDN) ở bên trái DN của cha.

Xét cây dữ liệu:

~~~text
dc=example,dc=org
└── ou=people
    ├── uid=linh                         [entry lá]
    ├── uid=an                           [entry lá]
    └── ou=archive                       [entry cha]
        ├── uid=old-a                    [entry lá]
        └── ou=contractors               [entry cha]
            └── uid=old-b                [entry lá]
~~~

Từ cấu trúc trên:

- `uid=linh,ou=people,dc=example,dc=org` là **entry lá** vì không có entry con trực tiếp.
- `ou=archive,ou=people,dc=example,dc=org` là **entry không phải lá** vì còn chứa `uid=old-a` và `ou=contractors`.
- `uid=old-b,ou=contractors,ou=archive,ou=people,dc=example,dc=org` là entry lá nằm sâu hơn.
- `ou=people,dc=example,dc=org` là nhánh lớn, chứa nhiều entry không liên quan đến nhu cầu dọn kho lưu trữ.

**Entry lá được xác định bởi quan hệ cha–con trong DIT, không phải số attribute hoặc số tham chiếu.** Ví dụ entry nhóm có attribute `member` chứa DN của nhiều người vẫn có thể là entry lá nếu bản thân nó không chứa entry con trong cây.

### Định danh tương đối và DN đầy đủ

Nếu `ContextSource` đã cấu hình base `dc=example,dc=org`, các API Spring LDAP thường nhận DN **tương đối** với base này:

| Đối tượng | DN đầy đủ | DN truyền cho `LdapTemplate` khi đã có base |
|---|---|---|
| Tài khoản Linh | `uid=linh,ou=people,dc=example,dc=org` | `uid=linh,ou=people` |
| Kho lưu trữ | `ou=archive,ou=people,dc=example,dc=org` | `ou=archive,ou=people` |
| Nhánh contractors | `ou=contractors,ou=archive,ou=people,dc=example,dc=org` | `ou=contractors,ou=archive,ou=people` |

Không tự thêm `dc=example,dc=org` lần nữa vào DN tương đối nếu `ContextSource` đã sử dụng nó làm base. Việc đặt sai base hoặc nhầm DN tương đối với DN đầy đủ có thể khiến thao tác trỏ vào đối tượng khác hoặc trả lỗi `noSuchObject`.

## 2. LDAP Delete chỉ xóa một entry lá trong thao tác chuẩn

Theo mô hình LDAPv3, thao tác **Delete** thông thường nhận DN của **một entry** cần xóa. Máy chủ chỉ chấp nhận khi entry đó **không có entry con**, caller đủ quyền và các ràng buộc khác được thỏa mãn.

~~~mermaid
flowchart TD
    A["Gửi Delete với DN của entry"] --> B{"Entry tồn tại và có thể truy cập?"}
    B -->|Không| C["Trả lỗi phù hợp: noSuchObject hoặc quyền truy cập"]
    B -->|Có| D{"Entry còn con?"}
    D -->|Có| E["Từ chối: notAllowedOnNonLeaf (66)"]
    D -->|Không| F{"Quyền và chính sách hợp lệ?"}
    F -->|Không| G["Từ chối thao tác"]
    F -->|Có| H["Xóa entry lá"]
~~~

Điểm cần nhớ:

1. **Xóa entry** là xóa chính đối tượng LDAP và toàn bộ attribute của nó; không phải chỉ xóa một attribute.
2. **Xóa entry cha không mặc định kéo theo xóa con.** Nếu còn con, kết quả LDAP phổ biến là `notAllowedOnNonLeaf` với result code **66**.
3. **Tham chiếu không đồng nghĩa quan hệ cây.** Một nhóm chứa `member: uid=linh,...` không làm entry người dùng trở thành “con” của nhóm.
4. **Xóa không phải soft delete mặc định.** Không thể giả định có thùng rác hay hoàn tác. Một số hệ thống có cơ chế riêng (chẳng hạn tombstone hoặc recycle bin), nhưng phải cấu hình và kiểm thử độc lập.

Đừng nhầm **LDAP protocol Unbind** (kết thúc phiên LDAP) với phương thức **`LdapTemplate.unbind(Name)`** của Spring LDAP (xóa entry được chỉ định). Tên gần giống nhau nhưng mục đích khác nhau.

## 3. Xóa entry lá với `LdapTemplate`

Với Spring LDAP, API thường dùng để xóa một entry là:

~~~java
ldapTemplate.unbind(relativeDn);
~~~

Ví dụ repository xóa một tài khoản có RDN `uid=linh` nằm dưới `ou=people`:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonDirectory {
    private final LdapTemplate ldapTemplate;

    public PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void deleteLeafPerson(String uid) {
        Name relativeDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", uid)
                .build();

        ldapTemplate.unbind(relativeDn);
    }
}
~~~

Mục đích của từng phần:

- `LdapNameBuilder` dựng DN từ các thành phần RDN và xử lý escape đúng với DN; tốt hơn việc nối chuỗi `uid=` với input người dùng.
- Khi `ContextSource` có base `dc=example,dc=org`, `relativeDn` đại diện cho `uid=<giá trị>,ou=people`.
- `ldapTemplate.unbind(relativeDn)` yêu cầu máy chủ xóa **chính entry tại DN đó**. Phương thức trả về thành công không đồng nghĩa hệ thống khác đã xóa dữ liệu hoặc tham chiếu liên quan.
- `LdapTemplate` quản lý context JNDI trong phạm vi thao tác, do đó repository không cần tự mở hoặc đóng `DirContext`.

Trong đoạn giải thích trên, `LdapTemplate` là bean được cấu hình với URL LDAP, base DN, tài khoản bind và phương thức kết nối an toàn. Mã giả định caller đã được kiểm tra quyền nghiệp vụ; ứng dụng không nên cung cấp một endpoint có thể xóa bất kỳ DN nào theo chuỗi do người dùng nhập.

> Trong ứng dụng thực, một thao tác xóa tài khoản cần quy trình nghiệp vụ như vô hiệu hóa phiên đăng nhập, xử lý tham chiếu nhóm, kiểm tra chính sách lưu giữ và ghi nhận audit. Những bước đó không được LDAP Delete tự động thực hiện.

### Nếu entry không tồn tại, còn con hoặc không đủ quyền?

`unbind` thường không trả về `false` khi xóa thất bại; thay vào đó Spring LDAP chuyển lỗi từ JNDI/server thành exception thuộc hệ thống truy cập dữ liệu LDAP. Những trường hợp thường gặp:

| Kết quả LDAP | Mã | Ý nghĩa trong thao tác xóa |
|---|---:|---|
| `success` | 0 | Máy chủ chấp nhận xóa entry được chỉ định |
| `noSuchObject` | 32 | DN không tồn tại hoặc phần đường dẫn liên quan không tìm thấy |
| `insufficientAccessRights` | 50 | Danh tính bind không đủ quyền xóa; đôi khi cần cả quyền liên quan entry cha |
| `unwillingToPerform` | 53 | Máy chủ từ chối vì chính sách/trạng thái riêng |
| `notAllowedOnNonLeaf` | 66 | Entry được xóa còn entry con |
| `invalidDNSyntax` | 34 | DN không hợp cú pháp |

Chính xác exception Java được ném phụ thuộc phiên bản Spring LDAP, JNDI provider và chính sách máy chủ. Không dùng một `catch (Exception)` để giả định mọi lỗi đều là “không tìm thấy”.

Nếu nghiệp vụ muốn thao tác **idempotent** (“entry đã không tồn tại thì coi là xong”), chỉ nên xử lý riêng trường hợp không tồn tại sau khi xác minh đúng DN. Không nên coi lỗi thiếu quyền hoặc không phải lá là thành công.

## 4. Xóa entry bằng JNDI thuần và trách nhiệm đóng context

Đôi khi ứng dụng cần thao tác ở mức JNDI để tích hợp tính năng riêng của máy chủ. Với JNDI, có thể xóa entry bằng phương thức như `DirContext.destroySubcontext(Name)` sau khi nhận context đủ quyền.

~~~java
import javax.naming.Name;
import javax.naming.directory.DirContext;

import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.ldap.support.LdapUtils;

public void deleteLeafWithJndi(
        ContextSource contextSource,
        String uid) {

    Name relativeDn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", uid)
            .build();

    DirContext ctx = null;
    try {
        ctx = contextSource.getReadWriteContext();
        ctx.destroySubcontext(relativeDn);
    } catch (javax.naming.NamingException e) {
        // Ở mã thực, phân loại lỗi và chuyển thành lỗi nghiệp vụ phù hợp.
        throw new IllegalStateException("LDAP delete failed", e);
    } finally {
        LdapUtils.closeContext(ctx);
    }
}
~~~

Trong mã JNDI trực tiếp, **đoạn mã lấy context sở hữu trách nhiệm đóng/trả context**. Ngay cả khi xóa thất bại, khối `finally` vẫn thực thi. Ngược lại, nếu gọi `ldapTemplate.unbind(...)`, hãy để Spring LDAP quản lý context.

Tránh truyền `DirContext` có thể sống lâu qua nhiều request hoặc chia sẻ giữa các thread. Nếu đang dùng pooling, đóng context thường là hành động **trả tài nguyên về pool**; không gọi `close()` có thể làm cạn pool dù LDAP Delete đã hoàn tất.

## 5. Tại sao không thể xóa trực tiếp nhánh còn con?

Giả sử cần xóa `ou=archive,ou=people` và toàn bộ dữ liệu bên dưới. Trực tiếp gọi:

~~~java
Name archiveDn = LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("ou", "archive")
        .build();

ldapTemplate.unbind(archiveDn);
~~~

Trong cây minh họa, thao tác này có thể thất bại với `notAllowedOnNonLeaf (66)` bởi `ou=archive` vẫn còn con.

Thao tác LDAP Delete chuẩn không mang ý nghĩa “xóa cả subtree”. Để xóa nhánh trên một máy chủ hỗ trợ LDAP Delete thông thường, client phải **xóa các entry con trước, rồi mới xóa entry cha**.

Với cây minh họa, thứ tự hợp lệ là:

~~~text
Bước 1: uid=old-b,ou=contractors,ou=archive,ou=people
Bước 2: ou=contractors,ou=archive,ou=people
Bước 3: uid=old-a,ou=archive,ou=people
Bước 4: ou=archive,ou=people
~~~

Tại bước 2, `ou=contractors` đã trở thành lá. Tại bước 4, `ou=archive` cũng đã trở thành lá. Hai bước đầu có thể hoán đổi với bước 3 nếu quan hệ con trước cha vẫn được bảo đảm.

Đây là chiến lược **duyệt hậu tự (post-order traversal)**: đi xuống các nhánh sâu nhất, xóa lá, quay lên xóa cha.

~~~mermaid
flowchart TD
    A["Chọn root DN cần xóa"] --> B["Liệt kê các entry con trực tiếp"]
    B --> C{"Còn entry con?"}
    C -->|Có| D["Xóa đệ quy từng nhánh con"]
    D --> B
    C -->|Không| E["Xóa chính entry hiện tại"]
    E --> F["Trả kết quả cho nhánh cha"]
~~~

Lưu ý: đây là **chuỗi nhiều thao tác**; việc xóa đệ quy từ client thông thường không có tính nguyên tử như một giao dịch duy nhất.

## 6. Xóa nhánh bằng Spring LDAP

Một số phiên bản Spring LDAP cung cấp overload:

~~~java
ldapTemplate.unbind(relativeDn, true);
~~~

Tham số `true` yêu cầu xóa đệ quy các entry con theo khả năng hỗ trợ của `LdapTemplate`. Điều này thuận tiện khi đã xác minh chính xác nhánh cần dọn:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class ArchiveDirectory {
    private final LdapTemplate ldapTemplate;

    public ArchiveDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void deleteArchiveSubtree() {
        Name archiveDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("ou", "archive")
                .build();

        // Nguy hiểm nếu xác định sai DN: nhiều entry sẽ bị xóa.
        ldapTemplate.unbind(archiveDn, true);
    }
}
~~~

**Đây là ví dụ đào tạo, không phải endpoint xóa hàng loạt dùng nguyên trạng trong production.** Khi áp dụng cần kiểm tra phiên bản Spring LDAP, giới hạn quyền và thuộc tính dữ liệu của directory server. Tham số đệ quy chỉ cho phép ứng dụng thực hiện các bước xóa cần thiết; không đảm bảo tính nguyên tử, tự khôi phục hoặc hỗ trợ vô điều kiện với mọi server.

### `unbind(dn)` và `unbind(dn, true)` khác nhau như thế nào?

| Cách gọi | Ý nghĩa | Kết quả khi DN còn con |
|---|---|---|
| `ldapTemplate.unbind(dn)` | Xóa chính entry tại DN | Thường thất bại với `notAllowedOnNonLeaf` |
| `ldapTemplate.unbind(dn, false)` | Xóa không đệ quy, nếu overload được cung cấp | Tương đương hành vi xóa entry lá |
| `ldapTemplate.unbind(dn, true)` | Yêu cầu xóa cả nhánh, con trước cha theo cách triển khai | Có thể thành công nếu client nhìn thấy và xóa được mọi entry liên quan |

**Không nên hiểu `true` là LDAP server cấp quyền đặc biệt để vượt ACL.** Từng thao tác xóa vẫn chịu quyền và chính sách của server. Những hệ thống có referral, phân vùng, entry bị ẩn do ACL, giới hạn truy vấn hoặc dữ liệu thay đổi đồng thời có thể khiến xóa nhánh thất bại giữa chừng.

Nếu dự án sử dụng `LdapClient` thay cho `LdapTemplate`, hãy kiểm tra API xóa trong phiên bản đang dùng; không suy luận rằng mọi biến thể fluent đều có tùy chọn đệ quy tương đương. Những hệ thống dùng ODM cũng phải tôn trọng cùng một quy tắc “con trước cha”.

## 7. Nếu cần tự triển khai xóa hậu tự

Khi framework không cung cấp lựa chọn phù hợp hoặc cần kiểm soát chi tiết, có thể xây dựng quy trình theo ý tưởng:

1. Xác định **root DN** với nguồn dữ liệu tin cậy và kiểm tra nó thuộc nhánh cho phép xóa.
2. Liệt kê **entry con trực tiếp** bằng search scope `ONELEVEL` tại root. Không nhầm với `SUBTREE` vốn bao gồm cả root và các mức con, tùy API.
3. Với mỗi entry con, lặp lại từ bước 2 cho đến khi xuống tới entry lá; có thể thực hiện tuần tự để dễ kiểm soát lỗi.
4. Xóa entry lá bằng thao tác Delete chuẩn.
5. Sau khi không còn con, xóa root của nhánh.
6. Đọc lại để xác nhận nhánh không còn tồn tại, hoặc ghi nhận các phần chưa xóa được.

**Giả mã:**

~~~text
deleteSubtree(rootDn):
    verifyWithinAllowedDeleteRoot(rootDn)
    children = searchOneLevel(rootDn)

    for each childDn in children:
        deleteSubtree(childDn)

    deleteSingleEntry(rootDn)
~~~

Đây là **mô hình thuật toán**, chưa phải triển khai production. Cần bổ sung xử lý paging, giới hạn dữ liệu, DN trả về từ search, retry có điều kiện, timeout, tình huống concurrent changes và audit.

### Tại sao scope tìm kiếm quan trọng?

Giả sử có hai nhánh:

~~~text
ou=people,dc=example,dc=org
├── uid=linh
└── ou=archive
    └── uid=old-a
~~~

Nếu mục tiêu chỉ là xóa archive mà ứng dụng tìm nhầm từ base `ou=people` với scope `SUBTREE`, tập kết quả có thể bao gồm cả `uid=linh`. Vì vậy **search base** là giới hạn an toàn rất quan trọng; filter `(objectClass=*)` đơn thuần không bảo vệ khỏi việc xóa nhầm.

Một quy tắc hữu ích là tách **phạm vi được phép xóa** khỏi **phạm vi xóa cụ thể**. Ví dụ toàn bộ thao tác dọn kho chỉ được hoạt động dưới `ou=archive,ou=people,dc=example,dc=org`, và không thể chấp nhận root `ou=people` hoặc root `dc=example,dc=org` dù người gọi đưa vào.

**DN phải được phân tích như DN**, bằng `javax.naming.ldap.LdapName` hoặc helper thích hợp, thay vì chỉ dùng `String.endsWith()` để kiểm tra phạm vi. So sánh chuỗi có thể bỏ qua quy tắc escape, nhiều biểu diễn hợp lệ của DN, hoặc nhầm một hậu tố ký tự với quan hệ tổ tiên thực sự.

## 8. Hành vi khi xóa nhánh thất bại giữa chừng

Giả sử nhánh archive có 500 entry. Ứng dụng đã xóa 320 entry thì gặp lỗi thiếu quyền ở một entry con.

Kết quả có thể là:

- Những entry đã xóa **vẫn bị xóa**; thao tác đệ quy không tự hoàn tác.
- Các entry chưa xóa vẫn còn trong DIT.
- Entry cha có thể vẫn còn, vì một hoặc nhiều entry con chưa được xóa.
- Chạy lại từ đầu có thể gặp thêm `noSuchObject` với các entry đã xóa nếu quy trình dùng danh sách DN cũ; cần quyết định cách xử lý nghiệp vụ tương ứng.

Các lỗi dễ gặp gồm:

| Tình huống | Hệ quả | Hướng xử lý |
|---|---|---|
| Một entry con thiếu quyền xóa | Không hoàn tất nhánh | Ngừng thao tác, báo cáo DN thất bại và kiểm tra ACL |
| Có entry mới xuất hiện trong lúc dọn | Cha vẫn còn con ở thời điểm xóa | Khóa luồng tạo mới ở cấp nghiệp vụ hoặc điều phối thời điểm dọn |
| Entry bị xóa bởi tiến trình khác | Truy vấn/xóa có thể nhận `noSuchObject` | Kiểm tra tính idempotent và phạm vi cho phép |
| Server timeout hoặc mất kết nối | Không chắc lệnh gần nhất đã được áp dụng hay chưa | Đọc trạng thái thực tế trước khi retry |
| Referral hoặc nhánh bị che bởi ACL | Client không duyệt/xóa đầy đủ | Xác minh phạm vi, danh tính và chính sách referral |
| Search bị giới hạn kích thước/thời gian | Danh sách con thiếu entry | Xử lý paging hoặc giới hạn đúng chuẩn, không xóa cha khi còn con |

**Không retry mù quáng một thao tác đệ quy**. Trước khi thử lại, cần truy vấn trạng thái thực tế, xác nhận root DN và giới hạn số thao tác. Nếu quy trình bắt buộc có tính nhất quán cao, thiết kế thêm pha “đánh dấu ngừng sử dụng/khóa ghi” ở tầng nghiệp vụ và quy trình dọn theo lô có thể quan sát/khôi phục.

## 9. Xóa nhánh và các cơ chế riêng của máy chủ

Một số dịch vụ thư mục cung cấp **tính năng xóa cây riêng**, không phải thao tác Delete LDAP thông thường. Chẳng hạn, Active Directory có **LDAP_SERVER_TREE_DELETE_OID** (control OID `1.2.840.113556.1.4.805`) cho thao tác xóa cây trong điều kiện server và quyền hỗ trợ.

Cần phân biệt:

- **Xóa phía client**: Spring LDAP hoặc mã JNDI duyệt/xóa các entry theo thứ tự thích hợp qua nhiều yêu cầu.
- **Xóa cây do server hỗ trợ**: client gửi yêu cầu đặc biệt với control/extension của nhà cung cấp. Đặc tính quyền, thất bại, logging và khôi phục phụ thuộc sản phẩm.
- **Xóa mềm/đánh dấu**: ứng dụng chuyển hoặc gắn trạng thái entry theo nghiệp vụ; không phải LDAP Delete chuẩn. Các tính năng recycle bin của server cũng có cơ chế và điều kiện riêng.

Không mặc định control dành cho Active Directory hoạt động trên OpenLDAP, ApacheDS hoặc mọi LDAP server. Chỉ dùng tính năng riêng sau khi đọc tài liệu sản phẩm và kiểm thử ở môi trường tương ứng; nhiều bản triển khai có ràng buộc quyền quản trị hoặc tác động ngoài dự kiến.

## 10. Quan hệ với nhóm, tham chiếu và các hệ thống khác

Xóa entry người dùng có thể ảnh hưởng đến dữ liệu liên quan ngay cả khi entry là lá. Ví dụ:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=example,dc=org
~~~

Nếu xóa entry `uid=linh,ou=people,dc=example,dc=org`, giá trị `member` trong nhóm có thể **vẫn còn**. LDAP thông thường không đảm bảo ràng buộc khóa ngoại tự động như cơ sở dữ liệu quan hệ. Một số server có plugin *referential integrity* hoặc cơ chế cập nhật tham chiếu, nhưng đó là tính năng cần bật và xác minh.

Trước khi xóa, xem xét:

- Nhóm dùng `member`, `uniqueMember` hoặc cơ chế thành viên riêng của server có tham chiếu DN mục tiêu không?
- Ứng dụng khác có lưu DN, uid hoặc khóa định danh của entry vào cơ sở dữ liệu, cache hay token không?
- Tài khoản có đang được dùng để bind hoặc cung cấp quyền truy cập dịch vụ không?
- Có yêu cầu lưu giữ dữ liệu, kiểm toán hoặc khôi phục sau sự cố không?

Nếu cần gỡ tư cách thành viên, thao tác đó là **modify attribute** trên entry nhóm, khác với **delete entry**. Trình tự thực hiện nên được thiết kế ở tầng nghiệp vụ và có kế hoạch xử lý lỗi khi các thao tác không nằm trong một giao dịch chung.

## 11. Kiểm soát an toàn trước khi xóa hàng loạt

Xóa nhánh là tác vụ có tác động lớn. Đối với ứng dụng sản xuất, nên có quy trình **preview → xác nhận → xóa → đối soát**:

| Giai đoạn | Việc cần làm | Lý do |
|---|---|---|
| **Xác định đích** | Xây dựng DN từ dữ liệu tin cậy; xác minh thuộc nhánh được phép xóa | Tránh xóa nhầm base hoặc nhánh ngoài phạm vi |
| **Preview** | Liệt kê DN sẽ bị xóa, đếm entry, kiểm tra dữ liệu và cấu trúc | Người vận hành nhìn thấy phạm vi tác động |
| **Ràng buộc** | Giới hạn DN gốc, số entry, loại object class, thời gian chạy và danh tính được phép | Giảm thiệt hại nếu cấu hình/input sai |
| **Chuẩn bị** | Backup phù hợp, xác nhận phương án restore, chặn cập nhật đồng thời khi cần | Có cơ chế khôi phục và tránh race condition |
| **Thực thi** | Dùng TLS, tài khoản có quyền tối thiểu, ghi audit; xóa con trước cha | Bảo vệ credentials và bảo đảm đúng thứ tự |
| **Đối soát** | Kiểm tra lại DIT, tham chiếu nhóm, lỗi và số entry còn lại | Xác định thực sự đã hoàn tất hay còn sót |

**Không cung cấp API nhận bất kỳ DN nào rồi gọi `unbind(dn, true)` mà không kiểm tra.** Dù tài khoản bind có quyền LDAP, người dùng ứng dụng không được mặc nhiên có quyền xóa mọi nhánh.

### Ví dụ thiết kế ranh giới xóa

Giả sử nghiệp vụ chỉ được phép xóa **một kho lưu trữ xác định trước**:

~~~java
public void purgeArchive() {
    Name archiveDn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("ou", "archive")
            .build();

    // Root được mã hóa bằng cấu hình tin cậy, không nhận DN tùy ý từ HTTP.
    // Preview và bước xác nhận vận hành diễn ra trước phương thức này.
    ldapTemplate.unbind(archiveDn, true);
}
~~~

Đây là biện pháp giảm sai sót ở thiết kế API; trong dự án thật còn phải có phân quyền, giới hạn môi trường, audit, kiểm tra thay đổi đồng thời và khả năng khôi phục.

Không nên dùng quyền admin toàn directory cho một tiến trình chỉ cần xóa dưới `ou=archive` nếu LDAP server hỗ trợ ACL giới hạn phù hợp. Mọi thông tin bind cần được truyền an toàn và không xuất hiện trong log. Dùng LDAPS hoặc StartTLS với xác thực chứng chỉ máy chủ đúng cấu hình.

## 12. Phân biệt delete, modify, rename và disable

Một số nhu cầu nghiệp vụ dùng từ “xóa” nhưng thao tác LDAP thích hợp có thể khác:

| Mục tiêu | Thao tác phù hợp | Tác động |
|---|---|---|
| Xóa hẳn entry người dùng không có con | `unbind(dn)` / LDAP Delete | Entry biến mất khỏi DIT |
| Xóa toàn bộ nhánh archive | Xóa hậu tự hoặc tính năng tree delete có kiểm soát | Nhiều entry bị xóa |
| Gỡ email khỏi tài khoản | Modify, ví dụ xóa attribute `mail` | Entry vẫn tồn tại |
| Loại một người khỏi nhóm | Modify attribute `member` trên entry nhóm | Người dùng và nhóm vẫn tồn tại |
| Chuyển người dùng sang nhánh khác | Rename/Modify DN | Thay đổi DN, không xóa và tạo entry theo nghĩa đơn giản |
| Ngừng cho đăng nhập nhưng vẫn giữ lịch sử | Trạng thái disable/lock phù hợp chính sách directory server | Entry còn tồn tại; cơ chế cụ thể phụ thuộc server |

Trong nhiều hệ thống, **disable trước, xóa sau thời hạn lưu giữ** là lựa chọn nghiệp vụ hợp lý hơn việc xóa ngay. Tuy nhiên, trạng thái disable và cách kiểm soát đăng nhập không có một attribute chung áp dụng cho mọi LDAP server.

## 13. Kiểm thử thao tác xóa trong Spring LDAP

Không chỉ kiểm thử rằng phương thức Java không ném lỗi; cần xác minh trạng thái cây sau thao tác.

**Các kịch bản tối thiểu:**

1. **Xóa lá thành công:** tạo entry thử `uid=temp` dưới nhánh thử nghiệm; gọi `unbind` rồi kiểm tra entry không còn.
2. **Xóa lá không tồn tại:** xác nhận ứng dụng xử lý `noSuchObject` theo đúng chính sách idempotency.
3. **Thử xóa cha còn con bằng xóa thường:** xác nhận máy chủ từ chối với hành vi tương ứng `notAllowedOnNonLeaf`, không xóa ngầm các con.
4. **Xóa nhánh nhiều cấp:** tạo cây ba cấp; dùng thao tác đệ quy hoặc hậu tự; xác nhận đúng các entry trong nhánh bị xóa.
5. **Bảo vệ ngoài phạm vi:** bảo đảm entry cùng cấp hoặc nhánh khác, như `uid=linh,ou=people`, vẫn còn.
6. **Lỗi giữa chừng:** giả lập thiếu quyền với một entry hoặc làm gián đoạn kết nối; kiểm tra báo cáo kết quả từng phần và cơ chế retry có kiểm soát.
7. **Concurrent changes:** tiến trình khác tạo entry con giữa bước preview và delete; xem ứng dụng phản ứng thay vì xóa ngoài dự kiến.
8. **Khôi phục:** thử restore từ dữ liệu sao lưu trên môi trường cô lập để đảm bảo phương án thực tế khả thi.

Một môi trường LDAP thử nghiệm cô lập có schema, ACL và cấu hình gần với production sẽ cho kết quả hữu ích hơn mock chỉ xác minh rằng hàm `unbind` được gọi. Khi kiểm thử, dùng nhánh riêng dành cho test, không trỏ tới dữ liệu thật.

### Bài tập thực hành có hướng dẫn

Giả sử bạn được giao dọn nhánh:

~~~text
ou=sandbox,dc=example,dc=org
├── uid=demo-1
├── uid=demo-2
└── ou=expired
    └── uid=demo-3
~~~

Yêu cầu:

1. Hãy cho biết DN nào có thể xóa trước bằng LDAP Delete chuẩn.
2. Nêu thứ tự xóa toàn bộ `ou=sandbox`.
3. Điều gì xảy ra nếu xóa `ou=sandbox` ngay từ đầu?
4. Nếu tiến trình dừng sau khi xóa hai người dùng, ứng dụng nên xử lý lần chạy lại ra sao?
5. Hãy đề xuất một cách chứng minh rằng thao tác không xóa entry bên ngoài `ou=sandbox`.

**Gợi ý giải:** Các lá ban đầu là `uid=demo-1`, `uid=demo-2` và `uid=demo-3`. Xóa `uid=demo-3` trước khi xóa `ou=expired`; xóa các lá còn lại rồi mới xóa `ou=sandbox`. Xóa root ngay khi còn con sẽ gặp lỗi kiểu `notAllowedOnNonLeaf (66)`. Sau khi dừng giữa chừng, truy vấn lại cây thay vì cố replay toàn bộ danh sách cũ; phân biệt DN đã không còn với lỗi quyền/hạ tầng. Dùng một DN root được cố định và đối soát cả các entry bên ngoài nhánh.

## 14. Những lỗi tư duy thường gặp

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “Gọi `unbind` ở cha sẽ tự xóa mọi người dùng bên dưới.” | Xóa thông thường chỉ xóa một entry lá; muốn xóa cây cần cơ chế đệ quy hoặc tính năng riêng. |
| “Một nhóm có nhiều thành viên là entry không phải lá.” | Attribute `member` là tham chiếu; quan hệ cha–con xác định bằng DN trong DIT. |
| “`unbind(dn, true)` chắc chắn hoạt động như một transaction.” | Đệ quy client có thể gồm nhiều lệnh; thất bại giữa chừng để lại trạng thái từng phần. |
| “Biết chuỗi DN có đuôi `dc=example,dc=org` là đủ an toàn.” | Cần kiểm tra quan hệ DN thực sự, base được phép, quyền và phạm vi nghiệp vụ. |
| “Server sẽ xóa các tham chiếu nhóm tự động.” | Tùy plugin/cấu hình; phải kiểm tra và cập nhật nếu cần. |
| “Xóa không tồn tại và xóa thiếu quyền là như nhau.” | `noSuchObject` khác `insufficientAccessRights`; không nên che khuất lỗi. |
| “Tăng quyền admin sẽ giải quyết lỗi xóa nhánh.” | Cần đúng thứ tự và chính sách; nâng quyền không sửa sai thuật toán hoặc sai phạm vi. |
| “Có backup là có thể xóa tùy ý.” | Restore cần được thử nghiệm; nhiều hệ thống khác có thể bị ảnh hưởng trước khi khôi phục. |

## Tài liệu tham khảo

- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): định nghĩa thao tác Delete, kết quả lỗi và hành vi giao thức.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): mô hình DN, cây entry và schema.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `ContextSource`, thao tác thay đổi entry.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): tra cứu overload `unbind` tương ứng phiên bản đang dùng.
- [Microsoft LDAP_SERVER_TREE_DELETE_OID](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/): tài liệu giao thức và các control dành cho Active Directory; cần kiểm tra tài liệu chi tiết của phiên bản server trước khi triển khai.

## Ghi nhớ

**LDAP Delete chuẩn xóa một entry lá; muốn xóa nhánh có con phải xóa các con trước rồi mới xóa cha**, hoặc dùng một tính năng xóa cây được máy chủ hỗ trợ. Trong **Spring LDAP**, `LdapTemplate.unbind(dn)` thể hiện xóa entry thường, còn overload đệ quy như `unbind(dn, true)` có thể giúp thực hiện xóa nhánh khi phiên bản thư viện hỗ trợ. Mọi thao tác cần giới hạn DN gốc, tuân thủ ACL, dùng kết nối TLS an toàn, xử lý lỗi từng phần và đối soát sau khi xóa. Xóa đúng đối tượng quan trọng hơn xóa nhanh, bởi LDAP Delete thông thường không cung cấp hoàn tác tự động.
