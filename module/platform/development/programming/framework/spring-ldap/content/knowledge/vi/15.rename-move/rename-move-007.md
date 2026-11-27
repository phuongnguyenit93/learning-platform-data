# Ảnh hưởng của referral và server capability khi rename/move trong Spring LDAP

Trong một dịch vụ thư mục LDAP, đổi tên entry (`rename`) và chuyển entry sang nhánh khác (`move`) thường trông đơn giản: cung cấp DN cũ và DN mới cho `LdapTemplate.rename(oldDn, newDn)`. Tuy nhiên, thao tác chỉ thành công khi **máy chủ đang xử lý yêu cầu có thể thực hiện phép đổi DN trong phạm vi dữ liệu mà nó quản lý**. Khi cây thư mục được chia thành nhiều naming context, nhiều backend hoặc nhiều máy chủ, **referral** và **server capability** trở thành những yếu tố quyết định.

Bài học này tập trung vào cách nhận biết ranh giới đó, cấu hình xử lý referral trong Spring LDAP/JNDI và kiểm tra khả năng của máy chủ trước khi đổi tên hoặc di chuyển entry. Mục tiêu là xây dựng tính năng quản trị thư mục dự đoán được kết quả, phân loại đúng lỗi và tránh giả định rằng mọi phép đổi DN đều được LDAP hỗ trợ.

## 1. Hiểu chính xác thao tác rename/move

Theo LDAPv3 (RFC 4511), đổi tên và di chuyển được thực hiện thông qua **Modify DN**, với các trường quan trọng:

| Trường trong ModifyDNRequest | Ý nghĩa |
| --- | --- |
| `entry` | DN hiện tại của entry cần đổi tên hoặc chuyển vị trí |
| `newrdn` | RDN mới, ví dụ `uid=an` hoặc `uid=an.nguyen` |
| `deleteoldrdn` | Có loại bỏ giá trị thuộc tính thuộc RDN cũ hay không |
| `newSuperior` (tùy chọn) | DN của entry cha mới nếu di chuyển sang nhánh khác |

Ví dụ cây thư mục:

~~~text
dc=example,dc=org
├── ou=people
│   └── uid=an
└── ou=alumni
~~~

Hai yêu cầu có ý nghĩa khác nhau:

- **Rename cùng cha:** `uid=an,ou=people,dc=example,dc=org` thành `uid=an.nguyen,ou=people,dc=example,dc=org`. Chỉ đổi RDN.
- **Move sang cha mới:** `uid=an,ou=people,dc=example,dc=org` thành `uid=an,ou=alumni,dc=example,dc=org`. Phần RDN vẫn giữ nguyên, `newSuperior` thay đổi.

Một thao tác có thể **vừa đổi RDN vừa chuyển cha**. Theo giao thức, entry được đổi DN có thể có entry con: yêu cầu có thể ảnh hưởng đến **cả subtree**, nếu server triển khai và cho phép thao tác đó.

~~~mermaid
flowchart TD
    A["Ứng dụng gọi LdapTemplate.rename"] --> B["JNDI gửi LDAP Modify DN"]
    B --> C{"Máy chủ quản lý được DN cũ và cha mới?"}
    C -->|Có| D{"Schema, ACL, tính năng và ràng buộc có cho phép?"}
    D -->|Có| E["Đổi DN và trả kết quả thành công"]
    D -->|Không| F["Trả lỗi LDAP phù hợp"]
    C -->|Không| G["Có thể trả referral hoặc lỗi phạm vi/multiple DSAs"]
    G --> H["Client cần diễn giải topology và chính sách referral"]
~~~

**Giới hạn nền tảng:** RFC 4511 nêu rõ client không được kỳ vọng có thể tùy ý chuyển entry hoặc subtree **giữa các server hay giữa các naming context**. Một lời gọi `rename` của Spring LDAP không tự tạo giao dịch chuyển dữ liệu qua hai máy chủ.

## 2. Referral là gì và vì sao ảnh hưởng đến move?

**Referral** là cơ chế để một LDAP server hướng client đến một LDAP endpoint khác khi dữ liệu hoặc nhánh được tham chiếu nằm ở nơi khác. Phản hồi có thể chứa một hay nhiều LDAP URL, ví dụ:

~~~text
ldap://ldap-branch.example.org/ou=people,dc=branch,dc=example,dc=org
~~~

Giả sử hệ thống có:

~~~text
Server A (dc=example,dc=org)
├── ou=people
│   └── uid=an
└── ou=external  --> referral tới Server B

Server B (dc=branch,dc=example,dc=org)
└── ou=external
~~~

Nếu client yêu cầu chuyển `uid=an` từ `ou=people` của Server A đến nhánh được quản lý ở Server B, vấn đề không đơn thuần là “tìm được Server B ở đâu”. **Server A có quyền và cơ chế thực hiện move xuyên phạm vi hay không** mới là điều quyết định. Việc tự động đi theo một URL referral không biến thao tác Modify DN ban đầu thành một giao dịch chuyển entry giữa hai server.

Cần phân biệt:

| Khái niệm | Bản chất | Ảnh hưởng đến rename/move |
| --- | --- | --- |
| **Referral** | Chỉ dẫn đến server/DN khác | Có thể khiến client kết nối endpoint được giới thiệu, nhưng không bảo đảm hỗ trợ move xuyên server |
| **Alias** | Entry trỏ tới một tên khác trong thư mục | Modify DN **không dereference alias** để tìm `entry` hoặc `newSuperior` theo RFC 4511 |
| **Replication** | Nhiều server lưu bản sao của một phạm vi dữ liệu | Bản sao có thể hỗ trợ đọc nhưng không nhất thiết nhận ghi; cần xác định điểm ghi |
| **Naming context / suffix** | Phạm vi tên mà một backend/server quản lý | Di chuyển qua ranh giới này có thể bị chặn dù hai DN dùng chung tên miền DNS |
| **Connection failover** | Đổi endpoint khi endpoint trước không khả dụng | Không đồng nghĩa với referral và không mở rộng khả năng Modify DN |

Với **named subordinate referral**, RFC 3296 còn đưa ra hướng xử lý cụ thể: nếu `newSuperior` là referral object hoặc nằm bên dưới referral object, server **nên** trả `affectsMultipleDSAs`. Điều này giải thích vì sao một yêu cầu move có thể bị từ chối ngay cả khi client đọc được URL của nhánh đích.

## 3. Cấu hình referral trong Spring LDAP và JNDI

Spring LDAP sử dụng `ContextSource` để tạo kết nối JNDI. Cấu hình `referral` của `LdapContextSource` (kế thừa `AbstractContextSource`) được chuyển thành thuộc tính JNDI `Context.REFERRAL` (`java.naming.referral`).

| Giá trị | Hành vi cơ bản của JNDI | Khi dùng với rename/move |
| --- | --- | --- |
| `ignore` | Không tự theo referral; với LDAPv3, nhà cung cấp JNDI tích hợp của Java thường gửi ManageDsaIT để xử lý referral entry như entry thông thường | Hữu ích khi phải thấy rõ ranh giới quản lý; không có nghĩa mọi lời gọi sẽ thành công |
| `follow` | JNDI cố gắng tự theo URL referral | Có thể kết nối server khác và gặp lỗi xác thực/TLS/khác naming context; không bảo đảm move xuyên server |
| `throw` | JNDI phát sinh `ReferralException` để caller chủ động quyết định cách xử lý | Phù hợp khi cần chủ động xác định endpoint, chính sách và từ chối chuyển hướng không mong muốn |

Trong JNDI LDAP provider thông dụng, mặc định là `ignore`. Một cấu hình Spring LDAP minh họa:

~~~java
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource contextSource = new LdapContextSource();
contextSource.setUrl("ldaps://ldap1.example.org:636");
contextSource.setBase("dc=example,dc=org");

// Chọn rõ chính sách xử lý referral trước khi context được khởi tạo:
contextSource.setReferral("throw");

// Trong ứng dụng Spring thực tế, cung cấp bind DN/credential
// từ cấu hình an toàn và để Spring khởi tạo bean ContextSource.
~~~

Nếu khai báo bằng Spring XML, thuộc tính cấu hình có thể viết:

~~~xml
<ldap:context-source
    url="ldaps://ldap1.example.org:636"
    base="dc=example,dc=org"
    referral="throw"
    username="${directory.bind-dn}"
    password="${directory.bind-password}" />
~~~

Phần XML này giả định ứng dụng đã bật Spring LDAP namespace và có cấu hình an toàn cho các property; các giá trị `directory.bind-dn`/`directory.bind-password` là tên property minh họa.

**Hai lưu ý quan trọng:**

1. `LdapTemplate` chuyển nhiều ngoại lệ JNDI sang hệ ngoại lệ Spring LDAP. Do đó, khi gọi `LdapTemplate.rename(...)`, đừng mặc định có thể bắt `javax.naming.ReferralException` trực tiếp giống như khi tự thao tác với `DirContext`. Nếu thật sự cần **tự theo từng referral**, phải thiết kế rõ cách lấy referral context, xác thực lại và xử lý lỗi ở tầng JNDI phù hợp.
2. `LdapTemplate.setIgnorePartialResultException(true)` là tùy chọn hỗ trợ một số **tình huống search** gặp partial results/referral, đặc biệt trong một số triển khai Active Directory. Nó **không phải** công tắc cho phép bỏ qua lỗi `rename` hay biến một move không hỗ trợ thành thành công.

Không bật `follow` một cách tự động cho mọi yêu cầu ghi mà chưa đánh giá endpoint được referral giới thiệu. Cần kiểm tra máy chủ đích tin cậy, DNS, đường truyền TLS, chứng chỉ, quyền bind và chính sách không tiết lộ credential cho đích lạ. Giới hạn số lần theo referral để tránh vòng chuyển hướng.

## 4. Server capability: server thực sự hỗ trợ thao tác gì?

LDAP có **giao thức** Modify DN, nhưng từng máy chủ/backend có thể đặt ra những giới hạn khác nhau về cấu trúc cây, schema, ACL, phân vùng dữ liệu và số lượng entry con. Khả năng hỗ trợ **rename cùng cha**, **move sang cha khác cùng suffix**, **move nguyên subtree** và **move xuyên naming context** không nhất thiết giống nhau.

Có thể bắt đầu kiểm tra từ **root DSE** (base DN rỗng, scope `base`). Root DSE có các thuộc tính vận hành như:

| Thuộc tính | Thông tin |
| --- | --- |
| `namingContexts` | Những naming context/suffix mà server công bố |
| `supportedLDAPVersion` | Các phiên bản LDAP được công bố |
| `supportedControl` | OID các LDAP control được hỗ trợ |
| `supportedExtension` | OID các extended operation được hỗ trợ |
| `supportedFeatures` | OID các feature được công bố |
| `supportedSASLMechanisms` | Cơ chế SASL hỗ trợ, hữu ích khi đánh giá xác thực |

Lệnh đọc minh họa (trên máy có `ldapsearch` và endpoint thử nghiệm):

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap1.example.org:636 \
  -b "" -s base "(objectClass=*)" \
  namingContexts supportedLDAPVersion supportedControl \
  supportedExtension supportedFeatures
~~~

Các thuộc tính root DSE là **operational attributes**, thường phải yêu cầu **tường minh theo tên**. Trên một số server, khả năng nhìn thấy giá trị còn phụ thuộc cấu hình hoặc quyền. Vì vậy, không thấy một giá trị trong phản hồi chưa đủ chứng minh server không hỗ trợ mọi tính năng liên quan.

Đặc biệt, **không có một cờ root DSE phổ quát mang ý nghĩa “có thể move tùy ý giữa mọi suffix/server”**. `supportedFeatures` hoặc `supportedControl` chỉ phản ánh các OID cụ thể. Muốn xác nhận việc đổi DN thực tế, cần đọc tài liệu đúng **sản phẩm + phiên bản + backend**, sau đó thử các tình huống hợp lệ trong môi trường kiểm thử.

### Trường hợp Active Directory

Active Directory hỗ trợ Modify DN với các ràng buộc riêng. Chuyển object **giữa các domain** khác với đổi OU **trong cùng domain**: theo tài liệu giao thức Microsoft, cross-domain move yêu cầu LDAP control chuyên dụng `LDAP_SERVER_CROSSDOM_MOVE_TARGET_OID` và các điều kiện về domain controller, role, object và quyền. Điều này **không được cung cấp tự động** chỉ bằng `LdapTemplate.rename(oldDn, newDn)` thông thường; AD LDS cũng không hỗ trợ cross-domain move theo cơ chế đó.

Không áp dụng quy tắc riêng của Active Directory như thể đó là quy tắc chung của OpenLDAP, 389 Directory Server hoặc các LDAP server khác.

## 5. Đánh giá trước khi rename/move

Trước khi chuyển một entry, thực hiện các kiểm tra sau với server sẽ nhận yêu cầu ghi:

1. **Tính DN và phạm vi:** DN cũ, RDN mới và DN cha mới có đúng schema và thuộc cùng phạm vi mà server cho phép xử lý không? Nếu `ContextSource` thiết lập base DN thì DN truyền cho `LdapTemplate` là tương đối với base này.
2. **Sự tồn tại:** entry nguồn có tồn tại, entry cha đích có tồn tại và DN đích có bị trùng không?
3. **Quyền:** bind account có quyền cần thiết với entry cũ, cha cũ, cha mới và các thuộc tính bị tác động không?
4. **Ràng buộc schema và cấu trúc:** lớp object có được phép nằm dưới kiểu parent mới, RDN mới có hợp lệ, và server có cho move subtree không?
5. **Ranh giới server:** DN đích là nhánh thực do server quản lý hay referral đến DSA khác? Có yêu cầu control hoặc API riêng cho server không?
6. **Hậu quả tham chiếu:** nhóm, ACL, ứng dụng hay hệ thống khác có lưu DN cũ không? Việc rewrite các tham chiếu này tùy sản phẩm/cấu hình và không thể giả định được xử lý hết.

Ví dụ minh họa **move trong cùng một naming context**, với `ContextSource` có base `dc=example,dc=org` và cả `ou=people` lẫn `ou=alumni` đều do cùng server quản lý:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryMoveService {

    private final LdapTemplate ldapTemplate;

    public DirectoryMoveService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void moveUserToAlumni(String uid) {
        String safeUid = requireUid(uid);
        Name oldDn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", safeUid)
            .build();

        Name newDn = LdapNameBuilder.newInstance()
            .add("ou", "alumni")
            .add("uid", safeUid)
            .build();

        // Gửi một yêu cầu Modify DN; server quyết định có cho phép hay không.
        ldapTemplate.rename(oldDn, newDn);
    }

    private static String requireUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }
        return uid;
    }
}
~~~

`LdapNameBuilder` xây dựng DN theo từng thành phần và xử lý escape giá trị RDN. Tuy nhiên, **nó không bảo đảm UID hợp lệ theo quy tắc nghiệp vụ hay chống mọi rủi ro phân quyền**. Trong ứng dụng thật, cần kiểm tra UID theo chính sách, giới hạn nhánh đích được phép và bảo vệ thao tác bằng kiểm tra quyền.

Một lời gọi `LdapTemplate.rename` không bảo đảm rằng server khác có thể tự tiếp nhận entry. Nếu muốn di chuyển từ `dc=example,dc=org` sang `dc=other,dc=org`, không thể chỉ đổi `newDn` trong ví dụ rồi coi đó là quy trình di chuyển đa hệ thống.

## 6. Phân tích lỗi: referral hay server capability?

LDAP server trả về result code; Spring LDAP/JNDI có thể chuyển nó thành ngoại lệ. Những trường hợp sau giúp phân biệt nguyên nhân, thay vì sửa bừa cấu hình referral:

| Kết quả LDAP | Nguyên nhân khả dĩ | Bước kiểm tra |
| --- | --- | --- |
| `referral` | DN hoặc nhánh thuộc endpoint được giới thiệu | Xem LDAP URL, naming context, chính sách `referral`, endpoint và xác thực |
| `affectsMultipleDSAs` | Yêu cầu ảnh hưởng tới nhiều DSA; đích là hoặc nằm dưới referral object theo tình huống RFC 3296 | Xác minh ranh giới server/naming context; không tự retry sang server khác |
| `unwillingToPerform` | Server từ chối theo chính sách hoặc hạn chế triển khai | Đọc thông báo chẩn đoán và tài liệu vendor; kiểm tra giới hạn move |
| `noSuchObject` | Entry nguồn hoặc cha đích không tồn tại/tên không khớp | Lookup đúng DN và xem `matchedDN` nếu được trả về |
| `entryAlreadyExists` | DN mới đã được chiếm | Kiểm tra entry đích và quy tắc đặt tên, không ghi đè |
| `insufficientAccessRights` | Tài khoản bind thiếu quyền cần thiết | Kiểm tra ACL trên source, target parent và policy liên quan |
| `namingViolation`, `objectClassViolation` | Tên hoặc vị trí mới vi phạm schema | Kiểm tra RDN, loại object, `nameForms`/quy tắc cha con khi áp dụng |
| `constraintViolation` hoặc lỗi triển khai khác | Một ràng buộc của server/backend bị vi phạm, tùy trường hợp | Kiểm tra chính xác result code, thông báo server và tài liệu của sản phẩm |

Không kết luận `referral` là lý do duy nhất khiến move thất bại: cùng một yêu cầu có thể vướng **ACL, schema, backend và policy**, trong khi một lời gọi tìm kiếm thông thường vẫn đọc được entry.

Đặc biệt, thử chuyển entry sang nhánh khác rồi nhận `affectsMultipleDSAs` **không có nghĩa** phải bật `Context.REFERRAL=follow`. Client cần quyết định liệu phép chuyển có được hỗ trợ hay phải áp dụng một quy trình di trú riêng.

## 7. Những tình huống thực tế

### 7.1. Đổi tên trong một OU

~~~text
uid=an,ou=people,dc=example,dc=org
    -> uid=an.nguyen,ou=people,dc=example,dc=org
~~~

Thường là trường hợp đơn giản nhất nếu server cho phép sửa RDN. Cần lưu ý `deleteoldrdn`, schema của `uid` và các ứng dụng tham chiếu DN cũ. Spring LDAP gọi `rename` thông qua JNDI; cách `deleteoldrdn` được thiết lập còn phụ thuộc JNDI provider và cấu hình. Không tự suy rằng mọi server giữ hoặc xóa giá trị RDN cũ giống nhau.

### 7.2. Chuyển user từ people sang alumni trong cùng suffix

~~~text
uid=an,ou=people,dc=example,dc=org
    -> uid=an,ou=alumni,dc=example,dc=org
~~~

Nếu cùng backend/server có quyền ghi và cha đích tồn tại, Modify DN có thể thực hiện yêu cầu. Nhưng schema, ACL hoặc chính sách vendor vẫn có thể từ chối. Kiểm tra lại cả DN cũ và DN mới, nhất là khi có replica hay cập nhật đồng thời.

### 7.3. Chuyển sang nhánh do server khác quản lý

~~~text
uid=an,ou=people,dc=example,dc=org       (Server A)
    -> uid=an,ou=staff,dc=branch,dc=org    (Server B)
~~~

Đây có thể là bài toán **di trú dữ liệu**, không phải rename thông thường. Nếu sản phẩm LDAP không có cơ chế move xuyên server được hỗ trợ chính thức, quy trình có thể cần:

1. Xác định mapping schema, parent, thuộc tính bắt buộc và quyền ở server đích.
2. Tạo entry mới trên server đích theo cơ chế provisioning được phê duyệt; xử lý thuộc tính không thể xuất/nhập trực tiếp.
3. Xác nhận entry đích, định danh, trạng thái ứng dụng và các nhóm/tham chiếu liên quan.
4. Chuyển hướng client hoặc cập nhật tham chiếu DN theo kế hoạch.
5. Chỉ gỡ entry nguồn sau khi xác nhận quá trình chuyển đổi đáp ứng yêu cầu.

Các bước `create -> verify -> update references -> delete` **không nguyên tử** giữa hai server; nếu lỗi giữa chừng có thể tồn tại bản sao hoặc tham chiếu chưa cập nhật. Cần cơ chế khôi phục, idempotency và nhật ký tiến trình. Không giả định có thể sao chép nguyên vẹn mật khẩu, thuộc tính do server quản lý, UUID, ACL hay thông tin đăng nhập.

## 8. Kiểm thử xác nhận giới hạn server

Trên LDAP test server có topology đại diện, hãy chuẩn bị các entry mẫu và chạy thử:

| Ca thử | Điều kiện | Quan sát cần ghi |
| --- | --- | --- |
| Rename cùng OU | Entry nguồn tồn tại, RDN đích chưa dùng | Thành công/thất bại; DN sau đổi; giá trị RDN cũ |
| Move sang OU cùng suffix | Cha đích tồn tại và cùng backend | Có hỗ trợ `newSuperior` không; ACL/schema; entry con nếu có |
| Move sang cha không tồn tại | DN đích có parent không có thật | Result code và `matchedDN` nếu có |
| Move sang referral subtree | Parent là/bên dưới referral entry | `referral` hoặc `affectsMultipleDSAs` và hành vi JNDI |
| Move sang suffix hoặc server khác | Hai naming context khác nhau | Server có từ chối hay có API/control đặc thù |
| Gặp referral với ba cấu hình | Lần lượt `ignore`, `throw`, `follow` | Hành vi client, target URL, quyền bind, lỗi thực tế |
| Đọc qua replica sau đổi DN | Server có replication | DN cũ/mới có thể hiển thị khác thời điểm; xác định điểm đọc |

Ở bước kiểm chứng, lookup trực tiếp tại DN cũ và DN mới để quan sát. `NameNotFoundException` từ lookup cũ là một tín hiệu DN cũ không còn **tại điểm đọc đó**, còn lỗi kết nối/quyền không chứng minh entry đã biến mất. Nếu LDAP được phân tán, đọc ngay ở replica có thể còn dữ liệu cũ do độ trễ đồng bộ.

Với từng lỗi, ghi lại tên operation, **result code**, diagnostic message đã loại bỏ dữ liệu nhạy cảm, endpoint xử lý và phạm vi DN. Tránh ghi password, session secret hoặc cả nội dung entry vào log. Khi cần retry, phân biệt lỗi mạng tạm thời với thao tác không hỗ trợ; retry liên tục `affectsMultipleDSAs` thường không giải quyết được ranh giới topology.

## 9. Bài tập vận dụng

Một hệ thống Spring LDAP có hai nhánh:

~~~text
Server A:
  dc=example,dc=org
  ├── ou=people
  │   └── uid=an
  └── ou=archive (referral tới Server B)

Server B:
  dc=archive,dc=org
  └── ou=archive
~~~

Hãy trả lời:

1. Nếu gọi `ldapTemplate.rename("uid=an,ou=people", "uid=an,ou=archive")` trên Server A, vì sao không thể chắc chắn thao tác thành công chỉ vì tên OU đích tồn tại dưới dạng referral?
2. Nếu server trả `affectsMultipleDSAs`, chuyển `referral` từ `ignore` sang `follow` có đảm bảo giải quyết được không?
3. Nếu root DSE công bố `supportedLDAPVersion: 3`, có thể suy ra server hỗ trợ mọi kiểu move không?
4. Vì sao `LdapTemplate.setIgnorePartialResultException(true)` không phải phương án sửa lỗi rename?
5. Trong trường hợp phải tạo entry ở Server B rồi xóa entry Server A, cần xác nhận và chuẩn bị khôi phục điều gì trước bước xóa nguồn?

**Gợi ý:** (1) referral cung cấp vị trí server khác, không cấp khả năng chuyển entry xuyên ranh giới; (2) không, lỗi phản ánh phạm vi DSA; (3) không, LDAPv3 có cú pháp Modify DN nhưng server có quyền từ chối theo topology/chính sách; (4) cờ này phục vụ trường hợp partial search results; (5) xác nhận entry đích, quyền, schema, thuộc tính và các tham chiếu nghiệp vụ, đồng thời chuẩn bị xử lý trạng thái chuyển đổi dở dang.

## 10. Ghi nhớ

- `LdapTemplate.rename(oldDn, newDn)` sử dụng khả năng **Modify DN** do LDAP server/JNDI cung cấp. Rename cùng OU, move cùng suffix và move xuyên server có các điều kiện hỗ trợ khác nhau.
- **Referral thông báo nơi cần tìm dữ liệu**; nó không tạo phép chuyển entry nguyên tử giữa hai máy chủ.
- `LdapContextSource.setReferral("ignore" | "follow" | "throw")` quyết định cách JNDI phản ứng với referral. Chọn dựa trên topology, bảo mật, quyền và khả năng kiểm soát endpoint đích.
- Đọc **root DSE** và tài liệu server giúp định hướng; khả năng move cụ thể phải được xác nhận trên đúng sản phẩm, backend và phiên bản. Không có cờ LDAP phổ quát xác nhận mọi kiểu move.
- Phân biệt `referral`, `affectsMultipleDSAs`, lỗi schema/ACL và lỗi kết nối để quyết định sửa cấu hình, đổi thiết kế hay thực hiện quy trình di trú riêng.

### Tài liệu tham khảo

- [RFC 4511 — LDAPv3, mục 4.9 Modify DN](https://www.rfc-editor.org/rfc/rfc4511.html#section-4.9)
- [RFC 3296 — Named Subordinate References, mục 5.6.2](https://www.rfc-editor.org/rfc/rfc3296.html#section-5.6.2)
- [RFC 4512 — Root DSE và các thuộc tính công bố khả năng](https://www.rfc-editor.org/rfc/rfc4512.html#section-5.1)
- [Oracle JNDI Tutorial — Referrals in the JNDI](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/jndi.html)
- [Spring LDAP — AbstractContextSource.setReferral](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextSource.html)
- [Spring LDAP — LdapTemplate.rename](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html)
- [Microsoft Open Specifications — Cross Domain Move](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/69e21ea9-05ef-4fcd-88f0-03104128891b)
