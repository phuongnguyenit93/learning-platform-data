# Điều kiện trước khi cập nhật hoặc xóa entry bằng Spring LDAP

Trong Spring LDAP, **LdapTemplate.modifyAttributes(...)** cập nhật thuộc tính của một entry và **LdapTemplate.unbind(...)** xóa entry tại một distinguished name (DN). Hai lời gọi trông đơn giản, nhưng ở môi trường nhiều người dùng, thao tác ghi chỉ đúng khi ứng dụng xác định được **entry nào** đang bị tác động, **ai** có quyền tác động, **trạng thái nào** cho phép thay đổi và **dữ liệu còn giống lúc người dùng ra quyết định hay không**.

Ví dụ, quản trị viên muốn đổi tên hiển thị của nhân viên có mã **E102** ở DN **uid=an,ou=people,dc=example,dc=org**. Trong lúc yêu cầu đang xử lý, tài khoản đó có thể đã chuyển bộ phận, đổi trạng thái, bị xóa hoặc được tạo lại tại cùng DN. Nếu chỉ nhìn vào chuỗi DN và thực hiện update/delete ngay, ứng dụng có nguy cơ sửa hoặc xóa sai đối tượng.

Bài này tập trung vào cách thiết kế và kiểm tra **điều kiện trước khi cập nhật hoặc xóa** trong module **SPRING_LDAP**, kết hợp nền tảng DN, schema, ACL, xác thực và thao tác entry bằng **LdapTemplate**. Các bước kiểm tra phía ứng dụng giúp phát hiện lỗi và áp dụng quy tắc nghiệp vụ; khi cần đảm bảo không có thay đổi xen giữa kiểm tra và ghi, phải dùng cơ chế điều kiện được **LDAP server thực thi trong cùng thao tác ghi**.

## 1. Phân biệt các loại điều kiện

Một yêu cầu cập nhật/xóa nên xác định rõ những điều kiện sau:

| Nhóm điều kiện | Câu hỏi phải trả lời | Ví dụ |
| --- | --- | --- |
| **Định danh và phạm vi** | DN có thuộc nhánh ứng dụng quản lý? Entry có đúng đối tượng được yêu cầu? | Chỉ tác động trong **ou=people**, kiểm tra **employeeNumber=E102**. |
| **Tồn tại** | Entry hiện còn tồn tại và có thể đọc đúng DN? | Trả **NOT_FOUND** nếu không còn entry. |
| **Trạng thái nghiệp vụ** | Trạng thái hiện tại có cho phép thao tác? | Chỉ xóa sau khi đã thu hồi quyền và qua thời gian lưu giữ. |
| **Schema và tính hợp lệ** | Thay đổi có tuân thủ objectClass, kiểu dữ liệu, tính đơn trị/đa trị và thuộc tính bắt buộc? | Không xóa thuộc tính **sn** khi schema của entry còn yêu cầu nó. |
| **Quyền truy cập** | Người gọi được ứng dụng cho phép, và danh tính kết nối LDAP có quyền ghi phù hợp? | Quản trị viên chỉ sửa nhánh được phân quyền. |
| **Cạnh tranh ghi** | Entry có giữ nguyên trạng thái đã được người dùng xác nhận không? | Phiên bản mong đợi bằng phiên bản hiện tại trước khi **Modify/Delete**. |
| **Ràng buộc liên quan** | Có entry con, nhóm hoặc hệ thống khác đang phụ thuộc? | Không xóa OU chứa entry con; xử lý tham chiếu nhóm theo chính sách. |
| **Vận hành và kiểm toán** | Nếu timeout hoặc xảy ra lỗi, có cách xác định kết quả cuối? | Lưu request ID, DN/ID bất biến, người thực hiện và trạng thái đối soát. |

Đây không phải một tập hợp điều kiện cần kiểm tra theo cùng một cách. **Input validation** nên thực hiện ở ứng dụng; **schema và quyền LDAP** phải được LDAP server kiểm tra; **điều kiện cạnh tranh** muốn có tính nguyên tử phải được thực thi ở thời điểm server xử lý lệnh ghi.

## 2. Xác định đúng DN và đúng danh tính entry

### Tạo DN có cấu trúc và giới hạn phạm vi

Giả sử **ContextSource** có base DN **dc=example,dc=org**. Khi sửa một người dùng, ứng dụng có thể tạo DN tương đối như sau:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String uid = "an"; // Đã kiểm tra và chuẩn hóa theo quy tắc nghiệp vụ.
Name personDn = LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("uid", uid)
        .build();
// uid=an,ou=people (tương đối với base của ContextSource)
~~~

Sử dụng **LdapNameBuilder** để tạo RDN và escape giá trị theo quy tắc LDAP; tránh ghép DN từ chuỗi người dùng nhập. Trong API quản trị, không nên cho client truyền tùy ý một DN đầy đủ để xóa: hãy ánh xạ mã định danh nghiệp vụ sang đúng nhánh đã cấu hình. Nếu phải nhận DN, cần phân tích bằng **LdapName** và kiểm tra quan hệ tổ tiên/hậu duệ theo thành phần RDN, thay vì so sánh bằng **endsWith** trên chuỗi thuần.

DN xác định **vị trí**, nhưng không luôn đủ để xác định **danh tính lâu dài**. Entry có thể được đổi DN (rename/move), bị xóa rồi tạo lại cùng tên (tình huống **ABA**), hoặc bị cấp lại **uid**. Với thao tác nhạy cảm, lưu một định danh bất biến hoặc không tái sử dụng, chẳng hạn ID nghiệp vụ do hệ thống quản lý hoặc **entryUUID** nếu server cung cấp; một số directory dùng thuộc tính khác như **objectGUID**. Luôn xác minh danh tính mong đợi trước khi ghi.

### Không suy diễn từ việc nhìn thấy entry

Đọc được entry không có nghĩa người gọi có quyền sửa/xóa. Ứng dụng phải kiểm tra quyền của **người gửi yêu cầu** theo nghiệp vụ; LDAP server vẫn phải kiểm tra ACL của **tài khoản đang kết nối**. Tài khoản kết nối có nhiều quyền không thay thế được việc xác thực và phân quyền ở tầng API.

Trước khi thực hiện thao tác, xác định rõ:

1. **Đích:** DN nằm trong nhánh cho phép và khớp ID bất biến.
2. **Dữ liệu:** thuộc tính mới đã qua kiểm tra độ dài, định dạng, giá trị được phép và quy tắc schema.
3. **Trạng thái:** tình trạng tài khoản và các phụ thuộc cho phép sửa/xóa.
4. **Phiên bản mong đợi:** với thao tác có nguy cơ xung đột, request phải mang thông tin để phát hiện thay đổi từ lúc người dùng đọc dữ liệu.

## 3. Kiểm tra trước khi Modify

Các phương thức **modifyAttributes(...)** gửi LDAP Modify để thay đổi một hoặc nhiều thuộc tính trên entry. LDAP server áp dụng schema/ACL và xử lý danh sách thay đổi của **một thao tác Modify**; server không tự hiểu các quy tắc nghiệp vụ như “chỉ được sửa người đang hoạt động” nếu quy tắc đó không được biểu diễn ở phía server.

| Loại thao tác | Điều kiện nên xem xét | Rủi ro nếu bỏ qua |
| --- | --- | --- |
| **REPLACE_ATTRIBUTE** | Giá trị hợp lệ; người dùng có quyền sửa; phiên bản phù hợp. | Ghi đè một thay đổi vừa được thực hiện ở phiên khác. |
| **ADD_ATTRIBUTE** | Thuộc tính có cho phép thêm giá trị? Giá trị đã tồn tại chưa? | Lỗi **typeOrValueExists** hoặc làm sai nghiệp vụ tập giá trị. |
| **REMOVE_ATTRIBUTE** | Thuộc tính/giá trị có tồn tại? Có thuộc schema bắt buộc hoặc được thao tác khác sử dụng? | Lỗi **noSuchAttribute**/**objectClassViolation**; mất thông tin quan trọng. |
| **Nhiều thay đổi trong một Modify** | Các thay đổi tạo ra trạng thái cuối hợp lệ; thứ tự và điều kiện kỳ vọng được thiết kế rõ. | Không đảm bảo ràng buộc liên entry hoặc liên dịch vụ dù một Modify thành công. |

Ví dụ: khi chỉnh **displayName**, ứng dụng có thể thay thế đúng thuộc tính này, tránh gửi một bản sao của toàn bộ entry và vô tình ghi đè các thuộc tính không liên quan.

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ModificationItem[] changes = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("displayName", "An Nguyen"))
};

ldapTemplate.modifyAttributes(personDn, changes);
~~~

**Cảnh báo:** Ví dụ chỉ là cú pháp Modify. Tự nó chưa đảm bảo các điều kiện “đúng người”, “đúng trạng thái” hoặc “không ai vừa cập nhật”. Để có điều kiện ghi, cần thêm kiểm tra và, nếu cần tính nguyên tử, cơ chế ở phần 5.

## 4. Kiểm tra trước khi Delete

Xóa entry nguy hiểm hơn sửa một thuộc tính vì có thể mất toàn bộ thông tin ở DN đó. Trước khi gọi **ldapTemplate.unbind(dn)**, nên có một chính sách xóa rõ ràng:

- **Đúng mục tiêu:** DN ở nhánh được phép và ID bất biến vẫn khớp. Không xóa dựa trên kết quả tìm kiếm rộng hoặc chỉ dựa vào tên hiển thị.
- **Được phép xóa:** người dùng có quyền tương ứng; không nằm trong tập đối tượng được bảo vệ; quy tắc lưu giữ dữ liệu và phê duyệt (nếu có) đã được thỏa.
- **Không còn phụ thuộc bị bỏ sót:** xem xét nhóm, thuộc tính tham chiếu, danh tính liên kết với ứng dụng khác hoặc quy trình đồng bộ. LDAP không tự đảm bảo dọn dẹp mọi tham chiếu nghiệp vụ.
- **Đúng thời điểm:** chỉ xóa nếu trạng thái/phiên bản chưa đổi từ lần xác nhận. Xóa tại một DN sau khi entry cũ đã bị thay thế có thể xóa nhầm một entry mới.
- **Kiểu xóa phù hợp:** **unbind(dn)** nhắm đến một entry. LDAP Delete thông thường không xóa được entry đang có entry con; server có thể báo **notAllowedOnNonLeaf**. Không bật cơ chế xóa đệ quy nếu không có yêu cầu và kiểm soát rõ ràng.

~~~java
// Chỉ gọi sau khi đã xác minh điều kiện theo thiết kế.
ldapTemplate.unbind(personDn);
~~~

**Hard delete** (xóa khỏi LDAP) và **soft delete** (đánh dấu vô hiệu hóa/di chuyển sang nhánh lưu trữ) là quyết định nghiệp vụ khác nhau. Soft delete chỉ khả thi khi schema, chính sách directory, ACL và các hệ thống liên quan hỗ trợ trạng thái hoặc vị trí lưu trữ đó. Đừng tự thêm thuộc tính **deleted** vào entry nếu schema không cho phép.

Khi xử lý lại một yêu cầu xóa, **NameNotFoundException** có thể có nghĩa “lệnh trước đã xóa thành công” hoặc “DN/ID vốn đã sai”. Chỉ coi kết quả là idempotent success khi hệ thống có bằng chứng về danh tính đích và chính sách xóa lặp cho phép; nếu không, cần đối soát.

## 5. Race condition: kiểm tra rồi ghi chưa phải là ghi có điều kiện

Một luồng thường gặp:

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant S as LDAP server
    participant B as Client B
    A->>S: Lookup uid=an, trạng thái active, version 17
    S-->>A: Đọc thành công
    B->>S: Modify trạng thái disabled, version 18
    S-->>B: Ghi thành công
    A->>S: Delete uid=an
    S-->>A: Xóa thành công (nếu không có precondition trên server)
~~~

Client A đã kiểm tra trạng thái **active** nhưng kết quả chỉ đúng tại thời điểm đọc. Đây là **time-of-check to time-of-use (TOCTOU)**. Gọi **lookup(...)** rồi **modifyAttributes(...)** hoặc **unbind(...)** là hai yêu cầu LDAP độc lập; giữa hai yêu cầu, tiến trình khác có thể ghi.

### Cách mạnh hơn: LDAP Assertion Control

**LDAP Assertion Control** theo **RFC 4528**, OID **1.3.6.1.1.12**, cho phép gửi một biểu thức lọc đi kèm thao tác Modify hoặc Delete. Nếu server hỗ trợ và quyền của request hợp lệ, server đánh giá bộ lọc trên entry mục tiêu tại thời điểm xử lý thao tác; chỉ ghi khi điều kiện khớp. Nếu không khớp, server trả **assertionFailed (122)**. Đây là cơ chế hữu ích để hiện thực **compare-and-set (CAS)** khi ứng dụng cần tránh ghi dựa trên dữ liệu cũ.

Ví dụ về *ý tưởng giao thức*, không phải cú pháp Java chạy trực tiếp:

~~~text
Request đã đọc trước đó:
  DN:         uid=an,ou=people
  entryUUID:  6d321...     (ID bất biến, ví dụ của server hỗ trợ)
  appVersion: 17           (thuộc tính phiên bản riêng được schema cho phép)

LDAP Modify một lần:
  assertion filter: (&(entryUUID=6d321...)(appVersion=17))
  replace displayName: "An Nguyen"
  replace appVersion:  "18"

LDAP Delete một lần:
  assertion filter: (&(entryUUID=6d321...)(appVersion=17))
  delete entry uid=an,ou=people
~~~

Trạng thái điều kiện và thao tác ghi được xử lý ở **cùng một LDAP operation**. Khi hai client cùng chờ phiên bản 17, client ghi trước có thể đưa entry sang phiên bản 18; client còn lại sẽ bị từ chối vì assertion không còn khớp. Nếu xóa rồi tạo lại ở cùng DN với **entryUUID** khác, assertion cũ cũng không được phép xóa entry mới.

Có một số điều kiện triển khai quan trọng:

1. **Kiểm tra hỗ trợ server:** đọc khả năng server quảng bá ở Root DSE (**supportedControl**) hoặc theo tài liệu nhà cung cấp; đừng giả định mọi LDAP server, phiên bản hay cấu hình đều hỗ trợ Assertion Control.
2. **Kiểm tra schema:** **appVersion** ở ví dụ là thuộc tính giả định của ứng dụng, phải được schema cho phép và chỉ các luồng ghi được kiểm soát mới được sửa. **entryUUID** hoặc **objectGUID** phụ thuộc directory và có thể không truy xuất hoặc dùng trong filter giống nhau.
3. **Không biến chuỗi filter thành byte control tùy tiện:** filter của Assertion Control phải được mã hóa theo định dạng giao thức LDAP/BER. Khi tích hợp qua Spring LDAP/JNDI, dùng cơ chế request control và context processing tương thích của phiên bản thư viện và provider; không coi UTF-8 của chuỗi filter là payload ASN.1 hợp lệ.
4. **Không âm thầm bỏ điều kiện:** nếu thao tác nguy hiểm yêu cầu CAS mà server không hỗ trợ hoặc từ chối control, hãy báo không hỗ trợ/đưa vào quy trình phù hợp. Không tự chuyển về check-then-write như thể vẫn còn bảo đảm nguyên tử.
5. **Chọn phiên bản đáng tin cậy:** **modifyTimestamp** là thuộc tính vận hành có ích cho theo dõi nhưng độ phân giải, cách cập nhật và sự khác biệt giữa directory có thể không đáp ứng yêu cầu CAS; nó không luôn là bộ đếm phiên bản. Nên sử dụng version monotonic do hệ thống kiểm soát hoặc cơ chế đồng thời do server cung cấp nếu cần bảo đảm chặt chẽ.

**Pre-Read/Post-Read Control** (RFC 4527), khi được server hỗ trợ, có thể giúp lấy ảnh chụp giá trị trước/sau một thao tác. Chúng **không tự thay thế** điều kiện Assertion Control. Tương tự, gửi thao tác **LDAP Compare** trước Modify/Delete vẫn là hai round trip độc lập, có cùng cửa sổ TOCTOU.

## 6. Ví dụ Spring LDAP: kiểm tra nghiệp vụ trước thao tác

Đoạn mã sau cho thấy một service kiểm tra **DN**, định danh người và trạng thái trước khi sửa hoặc xóa. Giả định server có base DN **dc=example,dc=org**, entry cha **ou=people** tồn tại, **uid**/ **employeeNumber** là các thuộc tính một giá trị, và **accountStatus** là thuộc tính được schema của môi trường cho phép. Dùng giá trị **active** chỉ là ví dụ về chính sách ứng dụng.

~~~java
import java.util.Objects;
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class GuardedPersonOperations {
    private final LdapTemplate ldapTemplate;

    public GuardedPersonOperations(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record ExpectedPerson(String uid, String employeeNumber) { }
    private record Snapshot(String uid, String employeeNumber, String status) { }

    public void updateDisplayName(ExpectedPerson person, String newName) {
        Name dn = personDn(person);
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("displayName không hợp lệ");
        }
        checkPerson(dn, person);

        ModificationItem[] changes = {
            new ModificationItem(
                    DirContext.REPLACE_ATTRIBUTE,
                    new BasicAttribute("displayName", newName))
        };
        ldapTemplate.modifyAttributes(dn, changes);
    }

    public void deleteLeaf(ExpectedPerson person) {
        Name dn = personDn(person);
        checkPerson(dn, person);
        // Một LDAP Delete đơn; server từ chối nếu entry còn entry con.
        ldapTemplate.unbind(dn);
    }

    private Name personDn(ExpectedPerson person) {
        Objects.requireNonNull(person, "person");
        if (person.uid() == null
                || !person.uid().matches("[a-z0-9._-]{1,64}")
                || person.employeeNumber() == null
                || person.employeeNumber().isBlank()) {
            throw new IllegalArgumentException("Thông tin định danh sai");
        }
        return LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", person.uid())
                .build();
    }

    private void checkPerson(Name dn, ExpectedPerson expected) {
        Snapshot actual = ldapTemplate.lookup(
                dn,
                (AttributesMapper<Snapshot>) attrs ->
                    new Snapshot(
                            stringAttr(attrs, "uid"),
                            stringAttr(attrs, "employeeNumber"),
                            stringAttr(attrs, "accountStatus"))
        );
        if (!expected.uid().equals(actual.uid())
                || !expected.employeeNumber().equals(actual.employeeNumber())) {
            throw new IllegalStateException("Định danh entry không khớp");
        }
        if (!"active".equalsIgnoreCase(actual.status())) {
            throw new IllegalStateException("Trạng thái không cho phép sửa/xóa");
        }
    }

    private static String stringAttr(Attributes attrs, String name)
            throws NamingException {
        Attribute value = attrs.get(name);
        return (value == null || value.size() != 1)
                ? null : String.valueOf(value.get());
    }
}
~~~

Ví dụ này minh họa cách tách bước kiểm tra đầu vào khỏi bước kiểm tra trạng thái hiện tại. **Nó chưa phải CAS an toàn khi nhiều client ghi đồng thời**: giữa **lookup** và **modifyAttributes/unbind** vẫn có cửa sổ TOCTOU. Khi yêu cầu an toàn cao, thêm Assertion Control cùng điều kiện ID/phiên bản vào thao tác ghi thực tế, hoặc tổ chức quyền sở hữu và hàng đợi xử lý ghi bảo đảm được điều kiện đồng thời cần thiết.

Trong ứng dụng thực tế, quy tắc xóa có thể khác quy tắc sửa: chẳng hạn chỉ **disabled** mới được xóa, trong khi chỉ **active** mới được đổi tên hiển thị. Vì vậy nên tách thành các chính sách kiểm tra có tên rõ ràng (ví dụ **canUpdate**, **canDelete**) và kiểm thử riêng. **accountStatus** là thuộc tính minh họa, không phải thuộc tính chuẩn có mặt trong mọi schema LDAP.

## 7. Xử lý lỗi và kết quả không chắc chắn

| Tình huống | Cách phản hồi hoặc xử lý |
| --- | --- |
| Không tìm thấy DN khi lookup | **NOT_FOUND**; trong API có thể ánh xạ **HTTP 404** nếu phù hợp. |
| ID bất biến hoặc trạng thái nghiệp vụ không khớp | **CONFLICT** hoặc **PRECONDITION_FAILED**; không ghi. |
| Assertion Control trả **assertionFailed (122)** | Đọc lại và hiển thị thay đổi mới nhất, yêu cầu người dùng xác nhận lại; API có thể dùng **HTTP 412** khi đã có điều kiện phiên bản. |
| Dữ liệu vi phạm schema (**constraintViolation**, **objectClassViolation**) | Báo lỗi dữ liệu hoặc cấu hình, không retry mù quáng. |
| LDAP trả **insufficientAccessRights** | Kiểm tra quyền của danh tính kết nối và chính sách ứng dụng; không thử lại bằng tài khoản có quyền cao hơn một cách tự động. |
| LDAP Delete trả **notAllowedOnNonLeaf** | Entry còn con; xác minh chính sách xử lý cây thư mục, không tự bật xóa đệ quy. |
| Timeout hoặc rớt kết nối lúc Modify/Delete | **UNKNOWN**: có thể server đã ghi xong. Đọc lại, so sánh ID/phiên bản/trạng thái, ghi log và đối soát trước khi kết luận. |

Không nên coi mọi lỗi là lỗi có thể retry. Với lỗi tạm thời, retry có backoff và giới hạn thời gian có thể thích hợp, nhưng phải thiết kế theo **tính lặp an toàn của từng thao tác**:

- **REPLACE** cùng một giá trị có thể cho cùng trạng thái thuộc tính cuối, nhưng vẫn có thể tạo sự kiện, cập nhật thuộc tính vận hành hoặc làm sai kỳ vọng phiên bản.
- **ADD** một giá trị đã có có thể báo **typeOrValueExists**; **REMOVE** một giá trị đã mất có thể báo **noSuchAttribute**. Không kết luận thành công chỉ dựa vào exception khi chưa đối soát.
- **Delete** bị timeout rồi nhận **not found** trong lần retry tiếp theo chưa đủ chứng minh lần trước thành công, nhất là khi DN có thể được sử dụng lại hoặc hệ thống có replica đọc trễ.
- Với thao tác có assertion theo version, một lần retry sau khi yêu cầu trước đã thành công có thể gặp **assertionFailed** do version đã đổi. Đối soát bằng mã yêu cầu, định danh bất biến và trạng thái cuối mong muốn; không vội kết luận xung đột khi chưa xác định được lần ghi trước.

Một phương án quản lý kết quả ở tầng ứng dụng là ghi bền vững **request ID**, đối tượng mục tiêu, phiên bản mong đợi và kết quả cuối. Định nghĩa chính sách **CREATED/UPDATED/DELETED**, **NO_CHANGE**, **NOT_FOUND**, **CONFLICT**, **UNKNOWN** theo ngữ nghĩa API thực tế. Khi một thao tác qua mạng có kết quả chưa rõ, việc lưu **UNKNOWN** rồi đối soát an toàn hơn việc báo thành công hoặc thất bại một cách chắc chắn.

## 8. Bảo mật, kiểm toán và kiểm thử

Để ngăn thao tác sai ngoài ý muốn, tài khoản truy cập LDAP thông qua **ContextSource** nên có quyền tối thiểu ở đúng nhánh cần quản lý. Dùng **LDAPS hoặc StartTLS** phù hợp với directory; không truyền mật khẩu hoặc token ra log. Audit nên lưu người khởi tạo, request ID, định danh entry, DN tại thời điểm thực hiện, thao tác, phiên bản mong đợi, kết quả và mã lỗi đã được làm sạch. Việc đọc thuộc tính nhạy cảm để kiểm tra điều kiện phải tuân thủ ACL và chính sách dữ liệu.

Các kịch bản kiểm thử tích hợp quan trọng:

| Kịch bản | Kỳ vọng |
| --- | --- |
| DN/uid không hợp lệ hoặc ngoài phạm vi | Từ chối trước khi ghi; không thay đổi directory. |
| DN hợp lệ nhưng **employeeNumber** khác | Từ chối vì sai danh tính; entry giữ nguyên. |
| Trạng thái không cho phép thao tác | Từ chối; không gọi Modify/Delete thành công. |
| Update giá trị hợp lệ trên entry đúng người | Chỉ thuộc tính được chỉ định thay đổi; schema vẫn hợp lệ. |
| Thử xóa entry cha đang có entry con | Server từ chối; không xóa đệ quy. |
| Hai client cùng gửi update với phiên bản 17 qua assertion | Chỉ thao tác phù hợp điều kiện tại lúc ghi thành công; thao tác còn lại nhận **assertionFailed**. |
| Một client đọc trạng thái active, client khác đổi disabled rồi client đầu xóa | Nếu dùng điều kiện nguyên tử, thao tác xóa bị từ chối đúng cách. |
| Entry bị xóa rồi được tạo lại tại DN cũ với ID mới | Yêu cầu cũ không được sửa/xóa entry mới. |
| Response bị mất sau khi server đã ghi | Hệ thống có thể đối soát và không thực hiện thao tác nguy hiểm sai đối tượng. |
| Server không hỗ trợ Assertion Control | Đường đi yêu cầu CAS dừng với lỗi rõ ràng; không âm thầm hạ cấp mức bảo vệ. |

Khi chạy test, nên dùng LDAP server đủ gần môi trường triển khai để xác minh schema, ACL, request control và mã lỗi cụ thể. **Mock LdapTemplate** chỉ kiểm tra được logic gọi hàm phía Java, không chứng minh được cơ chế đồng thời và hành vi của LDAP server.

## Ghi nhớ

Trước mỗi **Modify** hoặc **Delete** trong Spring LDAP, phải xác định **đúng DN, đúng danh tính, đúng quyền, đúng trạng thái và dữ liệu hợp lệ**. Kiểm tra bằng **lookup(...)** hữu ích cho thông báo lỗi và chính sách nghiệp vụ nhưng không tránh được cạnh tranh giữa đọc và ghi. Với thao tác cần tiền điều kiện nguyên tử, hãy dùng cơ chế server hỗ trợ như **LDAP Assertion Control** kết hợp định danh bất biến và phiên bản được quản lý. Với timeout hoặc retry, lưu trạng thái chưa xác định và đối soát trước khi tiếp tục để tránh cập nhật hay xóa nhầm entry.
