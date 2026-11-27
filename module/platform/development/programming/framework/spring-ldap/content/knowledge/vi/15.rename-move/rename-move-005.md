# Thay đổi parent và quyền yêu cầu

## Mục tiêu học tập

Trong LDAP, một entry thuộc về một vị trí trong cây thư mục. Khi chuyển entry từ nhánh này sang nhánh khác, ta **thay đổi parent** (entry cha), dẫn tới thay đổi **Distinguished Name (DN)** của entry. Với **Spring LDAP**, thao tác thường được thực hiện bằng `LdapTemplate.rename(oldDn, newDn)`, dựa trên thao tác **Modify DN** của LDAP.

Sau bài này, bạn có thể:

- Phân biệt đổi **RDN** với chuyển **parent** và nhận ra trường hợp đổi cả hai.
- Xây dựng DN nguồn/đích đúng khi dùng `ContextSource` có cấu hình base DN.
- Gọi `LdapTemplate.rename(...)` để di chuyển một entry đến parent khác.
- Giải thích các quyền điển hình cần có đối với **entry được chuyển**, **parent cũ** và **parent mới**, đồng thời hiểu rằng cơ chế ACL phụ thuộc máy chủ LDAP.
- Kiểm tra các điều kiện trước/sau khi chuyển, phân loại lỗi và đánh giá ảnh hưởng tới tham chiếu DN, phạm vi tìm kiếm, quyền thừa kế và dữ liệu nghiệp vụ.

Bài học đặt trong chương **Rename và move** của Spring LDAP. Các nguyên tắc về DN, schema, quyền truy cập và kết nối an toàn cũng áp dụng khi làm việc qua JNDI, `LdapClient` hoặc tầng ODM.

## 1. Thay đổi parent là gì?

Giả sử thư mục có base DN `dc=example,dc=org`:

~~~text
dc=example,dc=org
├── ou=engineering
│   └── uid=lan
└── ou=support
~~~

Entry của Lan có DN đầy đủ:

~~~text
uid=lan,ou=engineering,dc=example,dc=org
~~~

Khi chuyển Lan sang nhánh `ou=support`, DN trở thành:

~~~text
uid=lan,ou=support,dc=example,dc=org
~~~

Phần `uid=lan` là **Relative Distinguished Name (RDN)**, còn `ou=engineering,dc=example,dc=org` là đường dẫn đến **parent**. Trong ví dụ này, RDN vẫn là `uid=lan`; chỉ parent thay đổi.

Trước và sau:

~~~text
TRƯỚC                                  SAU
dc=example,dc=org                     dc=example,dc=org
├── ou=engineering                    ├── ou=engineering
│   └── uid=lan                        └── ou=support
└── ou=support                             └── uid=lan
~~~

Phân biệt ba thao tác:

| Thao tác | DN cũ | DN mới | Điều thay đổi |
| --- | --- | --- | --- |
| Đổi RDN, giữ parent | `uid=lan,ou=engineering,...` | `uid=lan.nguyen,ou=engineering,...` | Tên tương đối của entry |
| Chuyển parent, giữ RDN | `uid=lan,ou=engineering,...` | `uid=lan,ou=support,...` | Vị trí của entry trong cây |
| Đổi RDN và parent | `uid=lan,ou=engineering,...` | `uid=lan.nguyen,ou=support,...` | Cả tên tương đối và vị trí |

Cả ba thuộc nhóm thao tác **Modify DN** của LDAP. Đây không phải cách để thay riêng thuộc tính `department`, `description` hoặc `mail`. Những thuộc tính đó có thể được sửa bằng `modifyAttributes(...)`, nhưng tự sửa thuộc tính không làm entry chuyển sang OU khác.

> **Điểm cần nhớ:** Parent trong DN là vị trí cấu trúc của entry. Thay đổi `ou=engineering` thành `ou=support` ở DN **không tự động** đặt thuộc tính nghiệp vụ `department=support`, cũng không tự cập nhật mọi nơi đang lưu chuỗi DN cũ.

## 2. Cơ chế LDAP Modify DN khi thay đổi parent

LDAP định nghĩa thao tác **Modify DN** (RFC 4511, mục 4.9). Về mặt giao thức, yêu cầu có các thông tin chính:

- **entry**: DN hiện tại của entry cần đổi tên/chuyển.
- **newRDN**: RDN mới (có thể giống RDN cũ nếu chỉ chuyển parent).
- **deleteOldRDN**: có loại bỏ giá trị RDN cũ khỏi các attribute liên quan hay không khi RDN thay đổi.
- **newSuperior**: DN của parent mới, dùng khi chuyển entry sang nhánh khác.

Với ví dụ chuyển Lan, hình dung yêu cầu:

~~~text
entry:        uid=lan,ou=engineering,dc=example,dc=org
newRDN:       uid=lan
newSuperior:  ou=support,dc=example,dc=org
~~~

Máy chủ sẽ kiểm tra DN đích, parent mới, schema và quyền của tài khoản LDAP trước khi thực hiện. Nếu thành công, truy vấn theo DN cũ thường không còn tìm thấy entry, còn DN mới truy cập được.

Spring LDAP cung cấp cách gọi thuận tiện bằng **DN nguồn** và **DN đích**:

~~~java
ldapTemplate.rename(oldDn, newDn);
~~~

Thư viện lo phần làm việc với JNDI/LDAP; lập trình viên cần dựng hai DN đúng và xử lý lỗi theo ngữ cảnh.

### Những điều Modify DN không bảo đảm

1. **Không tạo parent mới:** `ou=support` phải tồn tại trước khi di chuyển entry vào đó.
2. **Không tự đồng bộ dữ liệu bên ngoài:** cơ sở dữ liệu khác, cấu hình ứng dụng hoặc tham chiếu DN có thể vẫn giữ DN cũ.
3. **Không thay mọi thuộc tính nghiệp vụ:** di chuyển sang OU mới không đồng nghĩa chỉnh `department` hay thay đổi nhóm quyền.
4. **Không nhất thiết hỗ trợ mọi cây thư mục:** máy chủ có thể giới hạn việc di chuyển entry có con, chuyển giữa naming context hoặc chuyển qua máy chủ khác.
5. **Không phải giao dịch xuyên nhiều dịch vụ:** Modify DN có ngữ nghĩa riêng ở LDAP, nhưng cập nhật hệ thống khác sau đó phải được điều phối riêng.

## 3. Ví dụ Spring LDAP với `LdapTemplate.rename(...)`

Giả sử ứng dụng đã cấu hình `LdapTemplate` từ `ContextSource`, trong đó:

~~~text
base DN: dc=example,dc=org
~~~

Khi đó, DN truyền vào `LdapTemplate` thông thường là DN **tương đối với base**:

~~~text
oldDn = uid=lan,ou=engineering
newDn = uid=lan,ou=support
~~~

Ví dụ một service di chuyển entry:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class EmployeeMoveService {

    private final LdapTemplate ldapTemplate;

    public EmployeeMoveService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void moveLanToSupport() {
        Name oldDn = LdapNameBuilder.newInstance()
            .add("ou", "engineering")
            .add("uid", "lan")
            .build();

        Name newDn = LdapNameBuilder.newInstance()
            .add("ou", "support")
            .add("uid", "lan")
            .build();

        ldapTemplate.rename(oldDn, newDn);
    }
}
~~~

Dòng `ldapTemplate.rename(oldDn, newDn)` yêu cầu máy chủ LDAP chuyển entry `uid=lan` sang `ou=support`. Hai OU phải tồn tại, tài khoản kết nối phải có quyền phù hợp, và DN mới không được trùng với entry đã có.

**Tại sao dùng `LdapNameBuilder`?** DN là cấu trúc có quy tắc escape và thứ tự RDN. Ghép chuỗi như `"uid=" + uid + ",ou=" + ou` dễ sai nếu giá trị chứa dấu phẩy, dấu cộng hoặc ký tự đặc biệt. Bộ dựng DN tạo các thành phần tên có cấu trúc rõ ràng.

### 3.1. Không nhân đôi base DN

Nếu `ContextSource` đã có base `dc=example,dc=org`, ví dụ trên dùng:

~~~text
uid=lan,ou=engineering
uid=lan,ou=support
~~~

Không nên tự nối thêm `dc=example,dc=org` vào các DN tương đối này rồi truyền chúng như thể base chưa được thiết lập; thao tác có thể tìm sai nhánh. Nếu ứng dụng cấu hình `ContextSource` không có base, quy ước DN đầu vào sẽ khác và phải xác định theo context thực tế.

### 3.2. Chuyển parent với tham số động

Khi tạo chức năng “chuyển nhân viên sang phòng ban khác”, cần giới hạn OU nguồn và OU đích vào những nhánh nghiệp vụ cho phép. Ví dụ dùng enum:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

public enum PersonUnit {
    ENGINEERING("engineering"),
    SUPPORT("support");

    private final String ou;

    PersonUnit(String ou) {
        this.ou = ou;
    }

    public String ou() {
        return ou;
    }
}

// Bên trong EmployeeMoveService:
private Name personDn(String uid, PersonUnit unit) {
    return LdapNameBuilder.newInstance()
        .add("ou", unit.ou())
        .add("uid", uid)
        .build();
}

public void movePerson(String uid, PersonUnit from, PersonUnit to) {
    if (from == to) {
        throw new IllegalArgumentException("Parent nguồn và đích giống nhau");
    }

    // Cần kiểm tra uid theo quy tắc nghiệp vụ trước khi gọi.
    Name oldDn = personDn(uid, from);
    Name newDn = personDn(uid, to);
    ldapTemplate.rename(oldDn, newDn);
}
~~~

Đây là một mẫu minh họa; trong ứng dụng thật, đặt mã trong class và import phù hợp. Việc dùng enum không thay thế **ACL phía máy chủ LDAP**: dù ứng dụng chỉ cho chọn hai OU, máy chủ vẫn phải xác thực và kiểm tra quyền ghi.

## 4. Quyền nào cần khi thay đổi parent?

Đây là điểm dễ gặp lỗi nhất. Di chuyển entry tác động đồng thời đến **entry đang có**, **nhánh cha cũ** và **nhánh cha mới**. Vì vậy tài khoản bind chỉ có quyền ghi thuộc tính của entry chưa chắc đủ quyền di chuyển.

Mô hình quyền ở mức khái niệm:

~~~text
ou=engineering                  ou=support
   │                                │
   ├─ cho phép bỏ một child          ├─ cho phép nhận child mới
   │                                │
   └─ uid=lan                        └─ uid=lan (sau khi chuyển)
      └─ cho phép đổi DN của entry
~~~

| Đối tượng | Nhu cầu quyền | Vì sao |
| --- | --- | --- |
| Entry nguồn `uid=lan,ou=engineering,...` | Quyền đổi tên/chuyển entry (Modify DN hoặc quyền tương đương) | Máy chủ cần cho phép tác động đến danh tính vị trí của entry |
| Parent cũ `ou=engineering,...` | Quyền loại bỏ entry con khỏi container | Entry rời khỏi danh sách con của parent cũ |
| Parent mới `ou=support,...` | Quyền tạo/thêm entry con vào container | Entry trở thành con của parent mới |
| Thông tin tra cứu cần thiết | Quyền đọc hoặc tra cứu thích hợp theo chính sách server | Giúp định vị entry và xác minh trước/sau, nếu server yêu cầu |
| Nhánh và naming context liên quan | Được phép di chuyển trong phạm vi hỗ trợ | Một số máy chủ chặn chuyển qua ranh giới quản lý hoặc máy chủ |

### 4.1. Ví dụ quyền trên OpenLDAP

Với OpenLDAP, tài liệu ACL mô tả quyền cho thao tác Modify RDN/Move thông qua các **pseudo-attribute**:

- Quyền `write` đối với pseudo-attribute `entry` của entry đang đổi DN.
- Quyền `write` đối với pseudo-attribute `children` của **parent cũ**.
- Quyền `write` đối với pseudo-attribute `children` của **parent mới**.

Như vậy, cấp quyền `write` cho thuộc tính `mail` hay `telephoneNumber` trên nhân viên **không đồng nghĩa** có đủ quyền Modify DN. Ngay cả khi entry là của nhân viên, account bind vẫn có thể bị từ chối vì không được thêm child vào OU đích.

Các tên `entry` và `children` ở đây là **khái niệm ACL riêng của OpenLDAP**; không phải mọi LDAP server đều dùng đúng tên hoặc mô hình phân quyền này. Tài liệu này mô tả các điều kiện điển hình để giúp chẩn đoán, không đưa ra một ACL mẫu cấp quyền rộng áp dụng vô điều kiện.

### 4.2. Ví dụ tư duy với Active Directory

Trong Active Directory, quyền di chuyển trong cùng miền thường liên quan đến quyền **Delete Child** (hoặc quyền xóa phù hợp) trên vùng nguồn và **Create Child** đối với loại đối tượng tương ứng trên vùng đích. Quyền cụ thể còn chịu tác động của ACL/ACE, các quyền bị từ chối, loại đối tượng, cấu trúc OU và chính sách quản trị.

Điều cần rút ra là **kiểm tra cả hai parent**. Một account có quyền cập nhật user ở OU nguồn có thể không có quyền đưa user vào OU đích. Khi đổi parent, các chính sách áp dụng theo OU hoặc quyền kế thừa cũng có thể thay đổi; cần đánh giá trước khi chạy trên hệ thống thật.

### 4.3. Nguyên tắc cấp quyền tối thiểu

- Tạo tài khoản dịch vụ riêng cho tác vụ di chuyển, chỉ cho phép trên **các OU được chỉ định**.
- Cấp quyền cần thiết tại entry nguồn và hai parent liên quan, thay vì cho phép chỉnh sửa toàn bộ directory.
- Tách quyền **cập nhật thuộc tính**, **đổi DN** và **xóa cả subtree** theo nhu cầu thật.
- Sử dụng LDAPS hoặc StartTLS, xác minh chứng chỉ máy chủ và bảo vệ credentials trong cấu hình `ContextSource`.
- Ghi log thao tác ở mức vừa đủ (loại hành động, mã kết quả, mã yêu cầu), tránh ghi thông tin nhạy cảm từ DN/attribute.
- Kiểm thử ACL bằng đúng tài khoản dịch vụ dự kiến, không lấy kết quả chạy dưới tài khoản quản trị làm bằng chứng rằng quyền tối thiểu đã đủ.

## 5. Điều kiện phải kiểm tra trước khi move

Trước khi thay đổi parent, cần đánh giá những vấn đề sau.

### 5.1. Parent đích phải có sẵn và đúng schema

Khi `ou=support,dc=example,dc=org` không tồn tại, máy chủ không thể đặt `uid=lan` vào dưới nhánh đó và có thể báo mã LDAP `noSuchObject`. `rename(...)` không tự tạo OU.

Ngoài ra, cấu trúc thư mục có thể có quy tắc **DIT structure rule** hoặc ràng buộc schema chỉ cho phép một số loại entry dưới một số loại parent. Việc parent đích tồn tại chưa chắc bảo đảm được chấp nhận di chuyển.

### 5.2. DN đích phải chưa được sử dụng

Nếu đã có:

~~~text
uid=lan,ou=support,dc=example,dc=org
~~~

thì một thao tác chuyển `uid=lan` khác tới cùng DN sẽ gây xung đột tên. Không được tự ghi đè hoặc xóa entry đích khi phát hiện trùng. Nếu hai entry cùng thuộc một nhân viên về mặt nghiệp vụ, cần quy trình hợp nhất dữ liệu riêng.

### 5.3. Giới hạn naming context và máy chủ

Chuyển entry giữa hai OU thuộc cùng naming context thường đơn giản hơn chuyển giữa các naming context, domain, partition hoặc LDAP server khác nhau. Một số máy chủ từ chối Modify DN xuyên ranh giới quản lý; chẳng hạn lỗi `affectsMultipleDSAs` có thể được trả về khi yêu cầu ảnh hưởng nhiều DSA.

Nếu nghiệp vụ thực sự cần chuyển giữa máy chủ hoặc domain, đừng giả định `LdapTemplate.rename(...)` sẽ thực hiện được. Hãy kiểm tra khả năng server và thiết kế quy trình migration riêng nếu cần. Việc “tạo bản sao rồi xóa bản gốc” không có cùng ngữ nghĩa nguyên tử với Modify DN; còn phải xử lý schema, thuộc tính máy chủ quản lý, quyền và khôi phục khi lỗi.

### 5.4. Entry có con, alias hoặc referral

Ví dụ bài học sử dụng **entry lá** (không có child) để tránh khác biệt giữa máy chủ. Một số LDAP server có thể hỗ trợ di chuyển cả subtree; server khác có thể từ chối thao tác trên entry không phải lá hoặc có hạn chế riêng. Alias, referral và các ranh giới directory có thể khiến đường đi xử lý khác nhau.

Không thử di chuyển một OU lớn với giả định mọi server đều cho phép và mọi ứng dụng liên quan đều cập nhật theo DN mới. Hãy kiểm tra tài liệu server và thử trên môi trường tích hợp.

## 6. Xử lý ngoại lệ khi quyền hoặc DN không hợp lệ

Spring LDAP chuyển các lỗi JNDI/LDAP phổ biến thành exception runtime trong package `org.springframework.ldap`. Tránh bắt chung tất cả rồi diễn giải thành “không tìm thấy nhân viên”.

Ví dụ một phương thức ứng dụng phân loại một số lỗi quan trọng:

~~~java
import javax.naming.Name;

import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.NoPermissionException;
import org.springframework.ldap.core.LdapTemplate;

// Ví dụ minh họa kết quả của một thao tác move.
public enum MoveResult {
    MOVED,
    SOURCE_OR_PARENT_NOT_FOUND,
    DESTINATION_CONFLICT,
    ACCESS_DENIED
}

public MoveResult move(Name oldDn, Name newDn, LdapTemplate ldapTemplate) {
    try {
        ldapTemplate.rename(oldDn, newDn);
        return MoveResult.MOVED;
    } catch (NameNotFoundException ex) {
        // Có thể thiếu entry nguồn HOẶC parent đích.
        return MoveResult.SOURCE_OR_PARENT_NOT_FOUND;
    } catch (NameAlreadyBoundException ex) {
        return MoveResult.DESTINATION_CONFLICT;
    } catch (NoPermissionException ex) {
        return MoveResult.ACCESS_DENIED;
    }
}
~~~

Ví dụ trên thể hiện **chiến lược phân loại**; đưa mã vào class service phù hợp trong dự án. Các lỗi khác như vi phạm schema, lỗi kết nối, referral hoặc giới hạn từ server vẫn cần được xử lý ở lớp ứng dụng. Không bắt và trả `MOVED` khi lệnh thực tế thất bại.

| Dấu hiệu | Khả năng nguyên nhân | Bước xử lý |
| --- | --- | --- |
| `NameNotFoundException` | DN nguồn hoặc parent đích không tồn tại; base DN không đúng | Xác minh riêng DN nguồn, parent đích và base của `ContextSource` |
| `NameAlreadyBoundException` | DN đích đã có entry khác | Dừng thao tác; điều tra xung đột tên và quy tắc định danh |
| `NoPermissionException` | Thiếu quyền trên entry, parent cũ hoặc parent mới | Kiểm tra ACL theo đường đi chuyển, bằng tài khoản bind đang chạy |
| Vi phạm schema/ràng buộc | Entry không được đặt dưới loại parent này; RDN/schema không hợp lệ | Kiểm tra objectClass, naming rules và chính sách directory |
| Không hỗ trợ hoặc lỗi DSA | Move vượt naming context, máy chủ không hỗ trợ subtree move | Xem khả năng của server và dùng quy trình migration phù hợp |
| Lỗi TLS/kết nối/timeout | Không xác định thao tác thành công hay chưa | Kiểm tra hạ tầng và **xác minh trạng thái trước khi retry** |

**Vì sao không retry mù?** Nếu client mất kết nối sau khi server đã chuyển entry, gọi lại `rename(oldDn, newDn)` có thể báo DN nguồn không tồn tại. Kết quả đó không chứng minh lệnh đầu thất bại. Với tác vụ quan trọng, hãy tra cứu DN nguồn và đích, đối chiếu thuộc tính định danh ổn định (nếu server cung cấp) và xử lý trạng thái không chắc chắn.

## 7. Kiểm tra kết quả sau khi đổi parent

Có thể sử dụng `LdapTemplate.lookupContext(...)` để đọc lại entry ở DN đích và xác nhận rằng DN nguồn không còn tìm thấy.

~~~java
import javax.naming.Name;

import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

// oldDn và newDn là Name đã tạo trong ví dụ trước.
ldapTemplate.rename(oldDn, newDn);

// Tra cứu bằng DN mới.
DirContextOperations moved = ldapTemplate.lookupContext(newDn);
String uid = moved.getStringAttribute("uid");

// Kiểm tra DN nguồn không còn trỏ tới entry.
boolean oldDnAbsent;
try {
    ldapTemplate.lookupContext(oldDn);
    oldDnAbsent = false;
} catch (NameNotFoundException ex) {
    oldDnAbsent = true;
}

// Kỳ vọng: uid = "lan"; oldDnAbsent = true.
// Trong kiểm thử, so sánh cả các attribute cần được giữ nguyên.
~~~

Đoạn mã giả định thao tác đã thành công và không có tác vụ khác tác động ngay sau đó. Trong sản phẩm thực tế, hai lần đọc sau khi chuyển không cùng một giao dịch; nếu có cập nhật đồng thời, cần kiểm soát ở tầng nghiệp vụ.

Không chỉ kiểm tra `uid`: tùy server, một entry có thể được phân biệt đáng tin cậy hơn bằng định danh nội bộ ổn định (ví dụ `entryUUID` trên hệ thống hỗ trợ hoặc `objectGUID` trong Active Directory). Đừng mặc định mọi server cung cấp cùng một thuộc tính định danh.

### 7.1. Tác động tới tìm kiếm theo OU

Giả sử ứng dụng tìm người dùng dưới `ou=engineering` với phạm vi `SUBTREE_SCOPE`. Sau khi chuyển Lan sang `ou=support`:

- Tìm trong nhánh `ou=engineering` không còn trả về Lan.
- Tìm trong nhánh `ou=support` có thể trả về Lan.
- Tìm dưới `dc=example,dc=org` với phạm vi phù hợp có thể vẫn thấy entry.

Đây là hệ quả cấu trúc của thay đổi parent, kể cả khi các thuộc tính nhân viên giữ nguyên. Những quy tắc nghiệp vụ dựa vào OU cần được kiểm thử lại.

### 7.2. Tham chiếu DN có thể cần cập nhật

Ứng dụng khác có thể lưu DN dưới dạng khóa, đường dẫn hoặc attribute tham chiếu. Ví dụ:

~~~text
member: uid=lan,ou=engineering,dc=example,dc=org
~~~

Sau khi move, giá trị trên có thể trở thành tham chiếu cũ. Một số server có cơ chế tự duy trì tham chiếu, nhưng **không thể giả định điều đó cho mọi triển khai LDAP**. Cần xác định các entry/ứng dụng tham chiếu và cơ chế cập nhật khi thiết kế chuyển OU.

Nếu hạ tầng áp dụng chính sách theo OU hoặc kế thừa quyền, các đặc quyền hiệu lực của tài khoản có thể khác sau khi chuyển. Điều này cần được kiểm tra trước/sau, nhất là với môi trường xác thực và phân quyền.

## 8. Kịch bản triển khai và kiểm thử quyền

Một kế hoạch di chuyển an toàn cho ứng dụng Spring LDAP thường bao gồm:

1. **Xác định DN chuẩn:** tính `oldDn` và `newDn` từ những giá trị đã kiểm tra; xác nhận cả hai dùng đúng base DN.
2. **Kiểm tra điều kiện nghiệp vụ:** người dùng thuộc nhóm được phép chuyển, parent đích hợp lệ, thao tác không vi phạm quy tắc định danh.
3. **Xác nhận điều kiện LDAP:** entry nguồn và parent đích tồn tại, DN đích không trùng, máy chủ hỗ trợ kiểu move cần thiết.
4. **Xác minh quyền:** dùng tài khoản dịch vụ thực tế để thử quyền cần thiết ở entry, parent nguồn và parent đích; giới hạn ACL đúng vùng.
5. **Gọi `rename(...)`:** xem kết quả thực tế từ máy chủ là nguồn sự thật; các lần đọc trước đó không loại bỏ được race condition.
6. **Kiểm tra trạng thái:** đọc lại DN đích, xác nhận DN cũ vắng mặt, đối chiếu thuộc tính và các tham chiếu liên quan.
7. **Ghi nhận và xử lý sự cố:** lưu kết quả thao tác không chứa dữ liệu nhạy cảm; khi lỗi không chắc chắn, xác minh trước khi retry.

Bảng ca kiểm thử tích hợp:

| Ca | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Move hợp lệ | Hai OU có sẵn; `uid=lan` chỉ ở engineering; tài khoản có đủ quyền | Entry có tại DN đích và không còn ở DN nguồn |
| Thiếu parent đích | Không có `ou=support` | Move thất bại; không tự tạo OU |
| Trùng DN đích | Đã có `uid=lan,ou=support` | Move bị từ chối; không ghi đè entry cũ |
| Thiếu quyền ở parent cũ | Tài khoản không được loại bỏ child khỏi engineering | Move bị từ chối; entry nguồn giữ nguyên |
| Thiếu quyền ở parent mới | Tài khoản không được thêm child vào support | Move bị từ chối; entry nguồn giữ nguyên |
| Thiếu quyền trên entry | Tài khoản không được Modify DN với entry đích | Move bị từ chối dù có quyền trên OU |
| Có quyền sửa `mail` nhưng không có quyền move | Cấp quyền sửa thuộc tính riêng | Sửa `mail` có thể thành công, move vẫn bị từ chối |
| Kiểm thử search scope | Tìm SUBTREE_SCOPE tại OU cũ/mới | Entry biến mất khỏi kết quả ở OU cũ và xuất hiện tại OU mới |
| Entry có child | Thử trên nhánh thử nghiệm chứa entry con | Quan sát hành vi đúng theo tài liệu LDAP server; không giả định luôn được |
| Kết nối gián đoạn | Cắt kết nối trong môi trường thử nghiệm | Ứng dụng xác minh DN nguồn và đích trước khi quyết định retry |

Các ca kiểm thử quyền nên được chạy với account có quyền **cụ thể** theo từng trường hợp. Tài khoản quản trị thường đủ quyền để chuyển thành công nhưng không chứng minh cơ chế phân quyền tối thiểu của ứng dụng hoạt động đúng.

## 9. Những nhầm lẫn thường gặp

**“Tôi sửa thuộc tính `ou` hoặc `department` của nhân viên rồi, tại sao DN không đổi?”** Vì thuộc tính nghiệp vụ và đường dẫn DN là hai lớp dữ liệu khác nhau. Muốn đổi parent phải dùng thao tác Modify DN, ví dụ `LdapTemplate.rename(...)`.

**“Tôi có quyền ghi trên nhân viên, vì sao move vẫn báo thiếu quyền?”** Modify DN cần thêm quyền liên quan đến parent cũ và mới. Với OpenLDAP, hãy kiểm tra quyền `children` ở cả hai OU và `entry` của entry; với server khác, kiểm tra ACL tương ứng.

**“Parent mới chưa có; lệnh rename có tự tạo không?”** Không. Phải tạo parent trước theo schema và quyền phù hợp, hoặc chọn parent đã có.

**“Có thể move từ một domain/LDAP server sang server khác không?”** Không thể mặc định. Tính năng và giới hạn phụ thuộc LDAP server/naming context; chuyển qua ranh giới có thể cần quy trình migration.

**“Đổi DN có bảo đảm mọi group và ứng dụng tự cập nhật không?”** Không. Cần kiểm tra cơ chế tham chiếu, group membership và các hệ thống đang lưu DN cũ; một số directory hỗ trợ cập nhật tham chiếu tự động, một số thì không.

**“Kiểm tra tồn tại trước rồi chuyển là đủ an toàn chứ?”** Không hoàn toàn. Giữa thời điểm kiểm tra và lúc `rename(...)`, một tiến trình khác có thể xóa hoặc chuyển entry. Vẫn phải xử lý ngoại lệ từ chính thao tác đổi DN.

## 10. Bài tập tự đánh giá

Cho cây thư mục:

~~~text
dc=example,dc=org
├── ou=staff
│   └── uid=mai
└── ou=contractors
~~~

Hãy thực hiện hoặc giải thích:

1. Dựng `Name oldDn` và `Name newDn` (tương đối với base) để chuyển `uid=mai` từ `ou=staff` sang `ou=contractors` mà giữ nguyên RDN.
2. Xác định ba vị trí cần kiểm tra quyền khi máy chủ dùng mô hình ACL tương tự OpenLDAP.
3. Nếu service account có quyền sửa `mail` của Mai nhưng move bị từ chối, bạn sẽ chẩn đoán theo thứ tự nào?
4. Nếu `uid=mai` đã tồn tại trong `ou=contractors`, vì sao không được tự xóa entry tại DN đích rồi tiếp tục?
5. Nếu yêu cầu move trả timeout, nhưng tra cứu sau đó thấy entry ở DN mới, bạn sẽ xử lý việc retry như thế nào?
6. Những tìm kiếm giới hạn ở nhánh `ou=staff` và các tham chiếu DN cần được rà soát ra sao sau move?

**Ghi nhớ:** Thay đổi parent là thay đổi **vị trí DN của entry** bằng LDAP Modify DN. Spring LDAP cung cấp `LdapTemplate.rename(oldDn, newDn)`, nhưng lệnh chỉ thành công khi **entry nguồn, parent đích, DN mới, schema, phạm vi hỗ trợ của server và các quyền liên quan** đều phù hợp. Cần đặc biệt kiểm tra quyền trên **entry**, **parent cũ** và **parent mới** thay vì chỉ kiểm tra quyền sửa attribute.

## Tài liệu tham khảo

- [RFC 4511, §4.9 — Modify DN Operation](https://www.rfc-editor.org/rfc/rfc4511#section-4.9): `newRDN`, `deleteOldRDN`, `newSuperior` và ngữ nghĩa thay đổi DN.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): phương thức `rename(...)` và các thao tác LDAP.
- [OpenLDAP Administrator’s Guide — Access Control](https://www.openldap.org/doc/admin26/access-control.html): mô hình ACL với pseudo-attribute và quyền dành cho thao tác Modify RDN.
- [Java Naming and Directory Interface — DirContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.naming/javax/naming/directory/DirContext.html): giao diện JNDI có thao tác `rename` kế thừa từ `Context`.
