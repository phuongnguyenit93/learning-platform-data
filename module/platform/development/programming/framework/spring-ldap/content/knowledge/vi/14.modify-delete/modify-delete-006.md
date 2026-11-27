# Xử lý entry không tồn tại

## Mục tiêu học tập

Trong phần **Modify và delete** của Spring LDAP, ứng dụng không chỉ cần biết cách cập nhật hoặc xóa một LDAP entry thành công, mà còn phải phản ứng đúng khi entry đích **không tồn tại**. Sau bài này, bạn có thể:

- Nhận diện tình huống **no such object** khi `lookup`, `modifyAttributes`, `unbind` hoặc `rename` một entry.
- Phân biệt **không tìm thấy entry** với **không tìm thấy attribute**, **không có kết quả tìm kiếm**, lỗi DN, lỗi quyền và lỗi kết nối.
- Bắt đúng `org.springframework.ldap.NameNotFoundException` từ `LdapTemplate`, rồi quyết định cách xử lý theo nghiệp vụ.
- Xây dựng thao tác cập nhật và xóa có kết quả rõ ràng, tránh che giấu lỗi khác, xử lý trường hợp thao tác lặp lại và hiểu rủi ro khi kiểm tra tồn tại trước khi ghi.
- Thiết kế các ca kiểm thử cho DN không tồn tại trong môi trường LDAP an toàn, sử dụng `ContextSource` và base DN đúng.

Các ví dụ dùng **Spring LDAP** với `LdapTemplate`; khi ứng dụng dùng `LdapClient`, ODM hoặc JNDI trực tiếp, nguyên lý nhận diện entry không tồn tại và lựa chọn chính sách nghiệp vụ vẫn tương tự.

## 1. “Entry không tồn tại” nghĩa là gì?

LDAP lưu dữ liệu trong một cây thư mục. Mỗi entry có một **Distinguished Name (DN)** duy nhất trong phạm vi cây và chứa các thuộc tính theo schema. Giả sử hệ thống có:

~~~text
dc=example,dc=org
└── ou=people
    ├── uid=lan
    └── uid=minh
~~~

DN đầy đủ của nhân viên Lan là:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Nếu ứng dụng gửi yêu cầu sửa hoặc xóa `uid=hoa,ou=people,dc=example,dc=org` nhưng máy chủ không có entry này, LDAP thường trả mã kết quả **noSuchObject (32)**. Khi thao tác đi qua `LdapTemplate`, lỗi JNDI `javax.naming.NameNotFoundException` được Spring LDAP chuyển thành ngoại lệ runtime `org.springframework.ldap.NameNotFoundException`.

Điểm quan trọng: **entry không tồn tại** không đồng nghĩa với **entry có thuộc tính trống**. Ví dụ, một nhân viên vẫn tồn tại dù `description` chưa được thiết lập; khi đó thao tác đọc entry có thể thành công và trả về `null` cho thuộc tính này.

### Phân biệt những trường hợp dễ nhầm

| Tình huống | Ý nghĩa | Phản ứng thường gặp |
| --- | --- | --- |
| `lookup` một DN không tồn tại | Không giải được tên entry đích | Ngoại lệ `NameNotFoundException` |
| `modifyAttributes` một DN không tồn tại | Không có entry để sửa | Ngoại lệ `NameNotFoundException` |
| `unbind` một DN không tồn tại | Không có entry để xóa | Ngoại lệ `NameNotFoundException` |
| `search` có base DN hợp lệ nhưng không entry nào khớp filter | Truy vấn thành công với **0 kết quả** | Danh sách rỗng |
| `search` với base DN không tồn tại | Thư mục gốc để tìm kiếm không hợp lệ | Theo mặc định, thường phát sinh `NameNotFoundException` trong `LdapTemplate` |
| Entry tồn tại nhưng thiếu `mail` | Thiếu attribute, **không** thiếu entry | Đọc `mail` có thể trả `null`; một số thay đổi có thể gặp lỗi về attribute |
| DN có tồn tại nhưng tài khoản thiếu quyền | Vấn đề cấp quyền hoặc cách máy chủ ẩn dữ liệu | Có thể bị từ chối; không tự kết luận entry đã bị xóa |
| Mất kết nối hoặc timeout | Chưa xác định trạng thái entry | Báo lỗi hạ tầng, không chuyển thành “không tồn tại” |

Không nên biến **mọi exception** hoặc **mọi kết quả tìm kiếm rỗng** thành thông báo “entry không tồn tại”; làm vậy sẽ che khuất lỗi vận hành và cấu hình.

## 2. Nhận diện ngoại lệ đúng tầng API

### 2.1. Spring LDAP và JNDI sử dụng hai loại exception khác nhau

Ở JNDI thuần, mã nguồn có thể làm việc với:

~~~java
import javax.naming.NameNotFoundException;
~~~

Với `LdapTemplate`, lớp cần bắt là:

~~~java
import org.springframework.ldap.NameNotFoundException;
~~~

Hai lớp có tên giống nhau nhưng **khác package và cơ chế xử lý**. `LdapTemplate` chịu trách nhiệm làm việc với `ContextSource`, quản lý context và chuyển ngoại lệ JNDI thành hệ ngoại lệ Spring LDAP. Vì vậy, khi gọi `LdapTemplate.lookupContext(...)`, `LdapTemplate.modifyAttributes(...)` hoặc `LdapTemplate.unbind(...)`, hãy bắt lớp của Spring LDAP.

Không bắt `Exception` hoặc `RuntimeException` chỉ để coi mọi lỗi là “không tìm thấy”. Lỗi thiếu quyền, lỗi schema, chứng chỉ TLS, lỗi kết nối hoặc timeout cần được phân loại và xử lý riêng.

### 2.2. Đảm bảo DN và base DN nhất quán

Nếu `ContextSource` được cấu hình với:

~~~text
base = dc=example,dc=org
~~~

thì trong các thao tác thông thường bạn truyền DN **tương đối**:

~~~text
uid=hoa,ou=people
~~~

Phần base đã được áp dụng bởi `ContextSource`; truyền lại DN đầy đủ mà không tính đến cấu hình có thể khiến truy vấn đến sai vị trí. Dựng DN bằng `LdapNameBuilder` giúp tránh lỗi nối chuỗi và escape các ký tự đặc biệt trong giá trị RDN:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("uid", "hoa")
    .build();
~~~

Khi gặp `NameNotFoundException`, cần kiểm tra cả **DN đích**, **base DN**, **entry cha** và vùng dữ liệu mà tài khoản bind có quyền nhìn thấy. Lỗi này không luôn khẳng định một nhân viên cụ thể đã bị xóa; đôi khi `ou=people` hoặc base đã bị cấu hình sai.

## 3. Đọc entry và trả kết quả có thể kiểm soát

Nếu chức năng chỉ cần xác định người dùng có trong thư mục hay không, có thể dùng `lookupContext`. Khi không tìm thấy, trả `Optional.empty()` là một lựa chọn hợp lý ở tầng truy cập dữ liệu:

~~~java
import java.util.Optional;

import javax.naming.Name;

import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Repository;

@Repository
public class PersonDirectoryRepository {

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    private Name personDn(String uid) {
        return LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", uid)
            .build();
    }

    public Optional<DirContextOperations> findByUid(String uid) {
        try {
            return Optional.of(ldapTemplate.lookupContext(personDn(uid)));
        } catch (NameNotFoundException ex) {
            return Optional.empty();
        }
    }
}
~~~

Ví dụ trên giả định `ContextSource` đã có base `dc=example,dc=org` và `ou=people` là một nhánh hợp lệ. Trước khi đưa ra thông báo nghiệp vụ “người dùng không tồn tại”, hãy bảo đảm những điều kiện cấu hình này đã được xác minh. Đầu vào `uid` cũng cần được kiểm tra theo quy tắc nghiệp vụ; `LdapNameBuilder` chỉ giải quyết vấn đề tạo DN an toàn.

Ưu điểm của `Optional<DirContextOperations>` là **không nhầm entry vắng mặt với attribute vắng mặt**. Ví dụ:

~~~java
Optional<DirContextOperations> found = repository.findByUid("lan");

if (found.isEmpty()) {
    // Không tìm thấy entry mang DN tương ứng.
} else {
    String mail = found.get().getStringAttribute("mail");
    // mail == null vẫn có thể xảy ra khi entry có tồn tại.
}
~~~

Nếu ứng dụng trả một DTO cho API, hãy ánh xạ `DirContextOperations` thành dữ liệu cần thiết tại repository/service; không cần đưa đối tượng LDAP nguyên bản ra ngoài tầng ứng dụng.

## 4. Cập nhật thuộc tính khi entry không tồn tại

`modifyAttributes` chỉ sửa **entry đã tồn tại**. Nó không tự tạo entry mới khi DN đích vắng mặt. Ví dụ cập nhật email:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonContactService {

    private final LdapTemplate ldapTemplate;

    public PersonContactService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean updateEmailIfPresent(String uid, String email) {
        Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", uid)
            .build();

        ModificationItem[] changes = {
            new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("mail", email)
            )
        };

        try {
            ldapTemplate.modifyAttributes(dn, changes);
            return true;
        } catch (NameNotFoundException ex) {
            return false;
        }
    }
}
~~~

Kết quả `true` nghĩa là yêu cầu sửa hoàn tất; `false` nghĩa là LDAP báo không tìm thấy DN trong thao tác này. Lỗi quyền, schema hoặc kết nối vẫn đi lên tầng gọi để được xử lý thích hợp.

Trong một API HTTP, có thể chuyển kết quả thành:

- `200 OK` hoặc `204 No Content` nếu đã cập nhật thành công.
- `404 Not Found` nếu hợp đồng API yêu cầu entry phải tồn tại và phép sửa trả về “không tìm thấy”.
- Mã lỗi khác tùy nguyên nhân nếu LDAP thất bại vì xác thực, thiếu quyền, dữ liệu sai schema hoặc hạ tầng.

Không mặc định dùng `404` cho bất kỳ `NameNotFoundException` nào ở mọi nơi: nếu nguyên nhân thực là **nhánh cha cấu hình sai**, hệ thống đang có lỗi triển khai, cần báo vận hành thay vì mô tả như thể người dùng đã bị xóa.

### Có nên tự tạo entry khi cập nhật không tìm thấy?

**Chỉ tạo khi nghiệp vụ cho phép upsert.** Nếu một lệnh cập nhật hồ sơ bất ngờ tạo tài khoản mới, có thể dẫn đến dữ liệu thiếu `objectClass`, `sn`, `cn`, quyền truy cập sai hoặc bản ghi ngoài dự tính.

Với nhu cầu *upsert* (có thì cập nhật, chưa có thì tạo), thiết kế một nhánh tạo riêng sử dụng `ldapTemplate.bind(...)` với **đầy đủ thuộc tính bắt buộc** theo schema. Việc thử `modifyAttributes` rồi `bind` sau `NameNotFoundException` không phải một giao dịch nguyên tử: nếu một tiến trình khác tạo entry ở giữa, `bind` có thể gặp `NameAlreadyBoundException`. Cần xử lý xung đột theo hợp đồng nghiệp vụ, không coi mọi lỗi bind là thành công.

## 5. Xóa entry vắng mặt: quyết định tính idempotent

Một lần gọi `ldapTemplate.unbind(dn)` sẽ xóa entry đích nếu nó tồn tại và **không có entry con**. Nếu DN không tồn tại, thao tác có thể ném `NameNotFoundException`.

Với một chức năng **“đảm bảo entry không còn tồn tại”**, có thể coi entry vốn đã vắng mặt là kết quả thành công; như vậy yêu cầu xóa lặp lại không gây lỗi nghiệp vụ:

~~~java
import javax.naming.Name;

import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonRemovalService {

    private final LdapTemplate ldapTemplate;

    public PersonRemovalService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    /**
     * true: đã xóa trong lần gọi này.
     * false: entry đã không tồn tại khi LDAP xử lý yêu cầu.
     */
    public boolean deleteIfPresent(String uid) {
        Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", uid)
            .build();

        try {
            ldapTemplate.unbind(dn);
            return true;
        } catch (NameNotFoundException ex) {
            return false;
        }
    }
}
~~~

Hàm này phân biệt **đã xóa trong lần gọi hiện tại** và **đã vắng mặt**, nhưng cả hai đều có thể đáp ứng mục tiêu “entry không còn tồn tại”. Nếu API HTTP quy định `DELETE` luôn trả `204 No Content` khi trạng thái cuối cùng là không còn bản ghi, có thể ánh xạ cả hai kết quả về `204`. Một API cần thông báo có/không có bản ghi bị xóa cũng có thể trả `404` cho lần xóa vắng mặt.

**Chính sách API là lựa chọn nghiệp vụ.** Không nên ràng buộc mã HTTP trực tiếp vào chi tiết ngoại lệ LDAP trong repository.

> **Lưu ý xóa cây:** `unbind(dn)` là xóa entry lá. Nếu entry có con, thao tác không tương đương với “không tìm thấy” và có thể thất bại vì subtree chưa rỗng. Spring LDAP có overload `unbind(dn, boolean recursive)`, nhưng `recursive=true` có thể xóa **nhiều entry**: chỉ dùng khi được yêu cầu rõ và có kiểm soát quyền, phạm vi DN.

### So sánh các cách xử lý

| Yêu cầu nghiệp vụ | Khi LDAP báo không tìm thấy | Kết quả nên biểu diễn |
| --- | --- | --- |
| Đọc một hồ sơ theo ID | Không có hồ sơ phù hợp | `Optional.empty()` hoặc Not Found ở tầng API |
| Cập nhật hồ sơ đã có | Không có đích để sửa | Báo Not Found; không tự tạo ngoài hợp đồng |
| Xóa tài khoản với yêu cầu “phải tồn tại” | Chưa có gì để xóa | Có thể báo Not Found |
| Dọn dẹp, đồng bộ dữ liệu, xóa lặp lại | Trạng thái mong muốn đã đạt | Chấp nhận “already absent” |
| Tạo tài khoản mới | Entry đích chưa có | Tạo qua `bind` nếu cha, schema và quyền hợp lệ |

## 6. Vì sao không nên luôn gọi “exists” rồi mới modify/delete?

Một triển khai dễ nghĩ tới là:

~~~java
if (repository.findByUid(uid).isPresent()) {
    ldapTemplate.unbind(dn);
}
~~~

Đoạn mã này không xử lý hoàn toàn trường hợp vắng mặt. Sau khi `lookup` thành công, một tiến trình khác có thể xóa entry trước khi lệnh `unbind` chạy. Khi đó `unbind` vẫn phát sinh `NameNotFoundException`. Hiện tượng này là **race condition**, thường được gọi là *time-of-check to time-of-use* (TOCTOU).

Sơ đồ thời gian:

~~~text
Ứng dụng A                   Ứng dụng B
    |                            |
    | lookup(uid=lan)            |
    | → tồn tại                  |
    |                            | unbind(uid=lan)
    |                            | → thành công
    | unbind(uid=lan)            |
    | → NameNotFoundException    |
    |                            |
~~~

Với một thao tác sửa/xóa đơn giản, cách dễ dự đoán hơn là **gửi yêu cầu trực tiếp rồi xử lý kết quả thực tế** (như hai phương thức ở trên). Nếu cần đọc trước để kiểm tra một quy tắc nghiệp vụ, vẫn phải tính tới trường hợp entry đổi hoặc biến mất giữa hai lệnh. Cần cơ chế kiểm soát đồng thời phù hợp nếu ứng dụng yêu cầu cập nhật có điều kiện hoặc nhất quán mạnh.

Tính nguyên tử của **một** yêu cầu LDAP Modify trên **một** entry không biến chuỗi `lookup → modify → delete` thành một giao dịch nguyên tử.

## 7. Không nhầm “search rỗng” với “base DN không tồn tại”

Khi tìm một hồ sơ bằng filter, kết quả rỗng có thể hoàn toàn bình thường:

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;

// "ou=people" là search base, phải tồn tại.
// search filter được escape bởi EqualsFilter.
List<String> uids = ldapTemplate.search(
    "ou=people",
    new EqualsFilter("uid", "hoa").encode(),
    SearchControls.SUBTREE_SCOPE,
    (attrs) -> (String) attrs.get("uid").get()
);

if (uids.isEmpty()) {
    // Search base hợp lệ, nhưng không có entry nào khớp filter.
}
~~~

Ngược lại, nếu `ou=people` không tồn tại, đây là lỗi **search base không hợp lệ**, khác về bản chất với “không có người dùng Hoa”. Theo mặc định, `LdapTemplate` báo `NameNotFoundException` cho trường hợp base không tồn tại.

Spring LDAP có cấu hình `setIgnoreNameNotFoundException(true)` (hoặc tùy chọn cấu hình tương đương) dành cho **các thao tác search**. Bật cấu hình này có thể làm lỗi search base không tồn tại bị bỏ qua, dẫn đến kết quả dễ bị hiểu nhầm là rỗng. Không nên bật chỉ để “né ngoại lệ” trong chức năng cần phân biệt cấu hình hỏng với truy vấn không khớp. Thiết lập này cũng **không phải** cách để bỏ qua lỗi của `modifyAttributes` hoặc `unbind`.

Đối với tên có thể chứa ký tự đặc biệt, hãy dùng bộ dựng filter của Spring LDAP như `EqualsFilter`; không tự ghép giá trị đầu vào trực tiếp vào biểu thức LDAP filter.

## 8. Chẩn đoán đúng nguyên nhân

Khi nhận được `NameNotFoundException`, hãy lần lượt xác minh:

1. **DN đích:** kiểm tra cấu trúc và cách escape giá trị RDN; ví dụ `uid=hoa,ou=people`.
2. **Base DN của `ContextSource`:** xác định ứng dụng có đang nối base đúng một lần hay không.
3. **Entry cha:** kiểm tra `ou=people,dc=example,dc=org` có thực sự tồn tại trên máy chủ đang kết nối.
4. **Máy chủ và môi trường:** bảo đảm application đang kết nối đúng LDAP server, cổng, base và dữ liệu thử nghiệm.
5. **Tài khoản bind và ACL:** xác nhận quyền tra cứu và sửa/xóa; một số máy chủ có thể ẩn sự tồn tại của entry theo quyền.
6. **Cấu hình kết nối:** TLS/LDAPS, chứng chỉ, referral và timeout được xử lý đúng; lỗi của các phần này không được mặc nhiên quy thành `NameNotFoundException`.

Các lỗi khác phải được giữ phân biệt:

| Dấu hiệu | Nhóm nguyên nhân | Xử lý phù hợp |
| --- | --- | --- |
| `NameNotFoundException` | DN/entry hoặc nhánh cha không tìm thấy | Kiểm tra DN/base; áp dụng chính sách Not Found nếu cấu hình hợp lệ |
| `NoPermissionException` hoặc lỗi quyền liên quan | Tài khoản thiếu quyền | Kiểm tra ACL và tài khoản bind; không coi như “đã xóa” |
| `SchemaViolationException` | Thuộc tính bắt buộc hoặc schema không hợp lệ | Sửa dữ liệu và logic thao tác |
| `NameAlreadyBoundException` | Cố tạo entry có DN đã tồn tại | Xem xét xung đột ghi hoặc upsert |
| `ServiceUnavailableException`, timeout hoặc lỗi mạng | Không truy cập được server đáng tin cậy | Báo lỗi hạ tầng, cân nhắc retry có giới hạn |
| Attribute bị thiếu hoặc rỗng | Entry có thể vẫn tồn tại | Phân biệt dữ liệu rỗng với DN không tồn tại |

Trong log chẩn đoán, có thể lưu mã thao tác (`lookup` / `modify` / `delete`), tên môi trường và mã lỗi đã chuẩn hóa. Hạn chế log DN chứa thông tin cá nhân, giá trị thuộc tính nhạy cảm hoặc credentials. Kết nối nên dùng LDAPS hoặc StartTLS với kiểm tra chứng chỉ và quyền LDAP tối thiểu cần thiết.

## 9. Các ca kiểm thử nên có

Kiểm thử trên LDAP server dành cho thử nghiệm (chẳng hạn instance độc lập hoặc môi trường tích hợp), với các entry được tạo và dọn dẹp trước/sau mỗi ca.

| Ca kiểm thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Tìm entry đang tồn tại | Tạo `uid=lan` với schema hợp lệ | `findByUid("lan")` trả `Optional` có giá trị |
| Tìm entry không có | Không tạo `uid=hoa`, nhưng giữ `ou=people` tồn tại | `findByUid("hoa")` trả `Optional.empty()` |
| Sửa entry không có | Chạy `updateEmailIfPresent("hoa", ...)` | Trả `false`; không tạo entry mới |
| Sửa entry có thật | Tạo `uid=lan` rồi cập nhật `mail` | Trả `true`; đọc lại thấy email mới |
| Xóa entry có thật | Tạo entry lá `uid=lan` | Trả `true`; lookup sau đó không tìm thấy |
| Xóa cùng entry lần thứ hai | Gọi xóa lại sau ca trên | Trả `false` theo hợp đồng của repository; không phát tán lỗi vắng mặt |
| Search filter không khớp | `ou=people` có thật, không có `uid=hoa` | Nhận danh sách rỗng |
| Search base sai | Truy vấn tại `ou=missing` | Nhận lỗi base không tồn tại theo mặc định |
| Thiếu quyền sửa/xóa | Dùng tài khoản chỉ đọc | Phát sinh lỗi quyền; **không** trả `false` như trường hợp entry vắng mặt |
| Xóa entry có con | Tạo entry cha chứa nhánh con | Xóa không đệ quy thất bại; các entry con không bị xóa |

Đừng viết một bài test chỉ kiểm tra `false` khi gọi repository với dữ liệu giả rồi kết luận LDAP đã xử lý đúng. Với chủ đề này, các bài kiểm thử tích hợp cho sự khác nhau giữa DN có/không tồn tại, search rỗng và lỗi ACL mang lại giá trị thực tế.

### Bài tập thực hành

Giả sử hệ thống có hai entry:

~~~text
uid=an,ou=people,dc=example,dc=org
uid=binh,ou=people,dc=example,dc=org
~~~

Hãy viết luồng xử lý cho các yêu cầu:

1. Cập nhật `mail` của `uid=an`; trả trạng thái cập nhật thành công.
2. Cập nhật `mail` của `uid=khong-co`; trả “không tìm thấy” và không tạo entry.
3. Xóa `uid=binh` hai lần; quyết định thông điệp cho cả lần đầu và lần sau theo chính sách idempotent.
4. Thay search base bằng `ou=unknown`; giải thích tại sao không nên hiển thị “không có nhân viên nào” khi thực ra cấu hình tìm kiếm sai.
5. Thử thao tác bằng tài khoản thiếu quyền; bảo đảm ngoại lệ không bị bắt như thể entry đã vắng mặt.

**Gợi ý tự đánh giá:** Một cách triển khai đáng tin cậy phải phân biệt được *entry vắng mặt*, *kết quả tìm kiếm rỗng*, *thiếu thuộc tính*, *thiếu quyền* và *lỗi hạ tầng*. Mỗi trường hợp dẫn tới quyết định nghiệp vụ khác nhau.

## 10. Tổng kết

Trong Spring LDAP, `LdapTemplate.lookupContext(...)`, `modifyAttributes(...)` và `unbind(...)` có thể báo `org.springframework.ldap.NameNotFoundException` khi DN liên quan không tồn tại. Hãy bắt ngoại lệ này ở đúng phạm vi thao tác rồi quyết định rõ hành vi: **trả Not Found cho cập nhật bắt buộc có entry**, **trả trạng thái vắng mặt cho lookup**, hoặc **chấp nhận xóa lặp lại** nếu mục tiêu chỉ là bảo đảm entry không còn.

Khi chẩn đoán, luôn xem xét DN, base DN và entry cha; giữ nguyên khả năng phân biệt các lỗi quyền, schema và kết nối. Đối với sửa/xóa, việc **thực hiện thao tác rồi xử lý kết quả** tránh được sự tin tưởng sai lầm vào bước kiểm tra tồn tại trước đó, vì dữ liệu LDAP có thể thay đổi giữa hai yêu cầu.

## Tài liệu tham khảo

- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): `lookupContext`, `modifyAttributes`, `unbind` và cấu hình `ignoreNameNotFoundException`.
- [Spring LDAP — NameNotFoundException API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/NameNotFoundException.html): ngoại lệ runtime ánh xạ từ JNDI.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource`, base DN và tùy chọn xử lý kết quả search.
- [RFC 4511 — Lightweight Directory Access Protocol](https://www.rfc-editor.org/rfc/rfc4511): mã kết quả LDAP và ngữ nghĩa các thao tác cơ bản.
