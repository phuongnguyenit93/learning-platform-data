# Thay đổi nhiều entry và ranh giới nguyên tử trong Spring Data LDAP

## 1. Bài toán: một nghiệp vụ có thể chạm nhiều entry

Trong **Spring Data LDAP**, mỗi bản ghi thư mục (*entry*) có Distinguished Name (**DN**), tập thuộc tính và các `objectClass` ràng buộc bởi schema. Ứng dụng Java có thể truy cập entry bằng repository hoặc `LdapTemplate` để tìm kiếm, thêm, sửa, xóa và đổi DN. Tuy nhiên, một thao tác nghiệp vụ của ứng dụng thường cần cập nhật **nhiều entry**.

Ví dụ, chuyển nhân viên Lan từ nhóm `engineers` sang nhóm `reviewers` có thể đòi hỏi hai sửa đổi:

1. Thêm DN của Lan vào thuộc tính `uniqueMember` của entry nhóm `reviewers`.
2. Xóa DN của Lan khỏi thuộc tính `uniqueMember` của entry nhóm `engineers`.

Nếu bước 1 thành công nhưng bước 2 lỗi, directory tạm thời ghi nhận Lan ở **cả hai nhóm**. Đây là vấn đề **ranh giới nguyên tử** (*atomicity boundary*): LDAP đảm bảo điều gì cho từng yêu cầu và những gì ứng dụng phải tự xử lý khi nhiều yêu cầu tạo thành một nghiệp vụ?

Bài học tập trung vào việc thiết kế cập nhật nhiều entry an toàn trong Spring Data LDAP, phân biệt tính nguyên tử của một yêu cầu LDAP với tính nhất quán toàn nghiệp vụ, đồng thời nhận diện vấn đề cạnh tranh ghi và đồng bộ giữa các directory replica.

## 2. Đơn vị nguyên tử của LDAP

**Nguyên tử** nghĩa là một nhóm thay đổi hoặc được áp dụng đầy đủ, hoặc không được áp dụng. Tuy nhiên, phải xác định rõ **nhóm thay đổi nào** đang được bảo đảm.

Theo LDAPv3 (RFC 4511), các thay đổi trong **một yêu cầu `Modify` đối với một entry** được thực hiện theo đúng thứ tự như một thao tác nguyên tử. Nếu phép sửa không thể hoàn tất do vi phạm schema, quyền truy cập hoặc điều kiện khác, entry không được ở trạng thái chỉ áp dụng một phần danh sách sửa đổi của yêu cầu đó.

Giả sử entry `uid=lan,ou=people,dc=example,dc=org` chứa:

| Thuộc tính | Giá trị trước |
| --- | --- |
| `mail` | `lan@old.example.org` |
| `telephoneNumber` | `1001` |

Một **yêu cầu Modify duy nhất** có thể thay `mail` và `telephoneNumber` cùng lúc. Nếu yêu cầu hợp lệ, cả hai thay đổi được áp dụng; nếu có lỗi làm yêu cầu thất bại, không chỉ một trong hai thuộc tính được cập nhật.

### Bảng phạm vi bảo đảm

| Thao tác | Ranh giới được bảo đảm theo giao thức | Điều không thể suy ra |
| --- | --- | --- |
| `Modify` một entry, chứa nhiều `ModificationItem` | Danh sách sửa đổi trong **một yêu cầu**, trên **một entry** | Hai lời gọi `modifyAttributes(...)` liên tiếp là một giao dịch |
| `Add` một entry | Một yêu cầu thêm entry | Tự động thêm thành công cả entry cha, nhóm và các entry liên quan |
| `Delete` một entry | Một yêu cầu xóa entry | Tự dọn sạch mọi liên kết giữa các entry khác |
| `ModifyDN` | Một yêu cầu đổi tên/di chuyển DN theo ngữ nghĩa và khả năng của server | Có giao dịch chung với các `Modify` hoặc `Add` khác |
| Nhiều yêu cầu gửi tuần tự | Mỗi yêu cầu có kết quả riêng | Toàn chuỗi tự động *all-or-nothing* |
| `Search` nhiều entry | Trả các entry khớp base DN, scope và filter | Kết quả là ảnh chụp nhất quán tại một thời điểm cho cả cây |

> **Điểm mấu chốt:** Một `ModifyRequest` có nhiều thay đổi thuộc tính trên **cùng entry** là một đơn vị nguyên tử. Một nghiệp vụ gửi hai `ModifyRequest` tới **hai entry khác nhau** không được LDAPv3 mặc định biến thành một giao dịch chung.

Khả năng bảo đảm nguyên tử của một yêu cầu không đồng nghĩa với đầy đủ các thuộc tính **ACID** cho toàn bộ workflow ứng dụng. Đặc biệt, không thể suy ra từ đó rằng các thao tác trên nhiều entry được cô lập khỏi người đọc khác, hay có thể rollback như một giao dịch cơ sở dữ liệu quan hệ.

## 3. Hai cách cập nhật khác nhau với `LdapTemplate`

Giả sử `LdapTemplate` đã được cấu hình `ContextSource` có base DN là `dc=example,dc=org`. Các đối số `Name` đưa vào ví dụ sau là **DN tương đối với base cấu hình**. Server dùng schema phù hợp, tài khoản bind có quyền sửa và entry đã tồn tại.

### 3.1. Sửa hai thuộc tính trên cùng một entry: một đơn vị nguyên tử

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;

public class DirectoryUpdater {
    private final LdapTemplate ldapTemplate;

    public DirectoryUpdater(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void updateContact(
            Name personDn,
            String newEmail,
            String newPhone) {

        ModificationItem[] changes = {
            new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("mail", newEmail)
            ),
            new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", newPhone)
            )
        };

        // Một yêu cầu LDAP Modify: hai thay đổi thuộc cùng một entry.
        ldapTemplate.modifyAttributes(personDn, changes);
    }
}
~~~

Ví dụ giá trị `personDn` là `new LdapName("uid=lan,ou=people")`. Phương thức `modifyAttributes(Name, ModificationItem[])` gửi **một** thao tác Modify cho entry; hai `ModificationItem` không biến thành hai request độc lập.

Có ba điểm cần chú ý:

- Nếu một thuộc tính bị schema cấm, hoặc tài khoản không có quyền thực hiện yêu cầu, server trả lỗi thay vì ghi một nửa danh sách sửa đổi.
- `REPLACE_ATTRIBUTE` thay **toàn bộ giá trị** của thuộc tính, kể cả khi thuộc tính được phép có nhiều giá trị. Không dùng thao tác này khi chỉ muốn thêm hoặc xóa **một phần tử** của thuộc tính đa trị.
- Tính nguyên tử được xét tại **một request**. Nếu `updateContact(...)` được gọi hai lần, hai lần đó vẫn là hai request độc lập.

### 3.2. Sửa hai entry nhóm: nghiệp vụ có thể dở dang

Đoạn mã sau minh họa chuyển thành viên giữa hai entry kiểu `groupOfUniqueNames`, sử dụng thuộc tính đa trị `uniqueMember`. Giá trị `memberFullDn` phải là **DN đầy đủ** của thành viên, chẳng hạn `uid=lan,ou=people,dc=example,dc=org`.

~~~java
public void moveMember(
        Name oldGroupDn,
        Name newGroupDn,
        String memberFullDn) {

    // Request 1: thêm Lan vào nhóm mới.
    ldapTemplate.modifyAttributes(newGroupDn,
        new ModificationItem[] {
            new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("uniqueMember", memberFullDn))
        });

    // Request 2: xóa Lan khỏi nhóm cũ.
    ldapTemplate.modifyAttributes(oldGroupDn,
        new ModificationItem[] {
            new ModificationItem(
                DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("uniqueMember", memberFullDn))
        });
}
~~~

Hai lời gọi trên là **hai request LDAP riêng**. Ví dụ:

~~~java
moveMember(
    new LdapName("cn=engineers,ou=groups"),
    new LdapName("cn=reviewers,ou=groups"),
    "uid=lan,ou=people,dc=example,dc=org"
);
~~~

Trong Java, có thể đặt `moveMember(...)` cùng lớp `DirectoryUpdater` ở ví dụ trước; cần thêm import `javax.naming.ldap.LdapName` ở đoạn gọi.

Nếu nhóm mới đã chứa Lan, thao tác `ADD_ATTRIBUTE` có thể trả `attributeOrValueExists`. Nếu nhóm cũ không chứa Lan, thao tác xóa một giá trị có thể trả `noSuchAttribute`. Việc xóa thành viên cuối cùng cũng có thể vi phạm schema của nhóm yêu cầu ít nhất một `uniqueMember`. Một workflow thực tế phải xử lý những trường hợp đó theo **trạng thái mong muốn** và quy tắc nghiệp vụ, không mặc định coi mọi lỗi là có thể bỏ qua.

## 4. Trạng thái dở dang và thứ tự thao tác

Với chiến lược **thêm vào nhóm mới trước, xóa khỏi nhóm cũ sau**, có thể xảy ra:

| Thời điểm | Trong `engineers` | Trong `reviewers` | Diễn giải |
| --- | :---: | :---: | --- |
| Trước khi bắt đầu | Có | Không | Trạng thái ban đầu |
| Sau request 1 | Có | Có | Trạng thái trung gian, hoặc trạng thái tồn dư khi request 2 thất bại |
| Sau request 2 thành công | Không | Có | Trạng thái đích |
| Request 1 thất bại | Có | Không | Chưa chuyển được |
| Request 2 thất bại | Có | Có | Chuyển **chưa hoàn tất**, cần xử lý tiếp |

~~~mermaid
flowchart TD
    A["Ban đầu: chỉ thuộc engineers"] --> B["Modify #1: thêm vào reviewers"]
    B -->|Thành công| C["Trung gian: thuộc cả hai nhóm"]
    B -->|Thất bại| E["Chưa thay đổi: báo lỗi"]
    C --> D["Modify #2: xóa khỏi engineers"]
    D -->|Thành công| F["Hoàn tất: chỉ thuộc reviewers"]
    D -->|Thất bại| G["Dở dang: ghi nhận và đối soát"]
~~~

Thứ tự thao tác phụ thuộc mục tiêu nghiệp vụ. **Thêm trước, xóa sau** hạn chế khoảng thời gian người dùng không thuộc nhóm nào, nhưng có thể tạm thời mở rộng quyền truy cập nếu nhóm gắn với quyền bảo mật. **Xóa trước, thêm sau** tránh đồng thời giữ cả hai quyền, nhưng lại có nguy cơ tạm thời mất quyền cần thiết. Không có một thứ tự luôn đúng cho mọi hệ thống.

Ngoài lỗi LDAP, ứng dụng có thể bị dừng, mất kết nối, hết thời gian chờ hoặc mất điện **sau khi server đã thực hiện request nhưng trước khi client nhận được phản hồi**. Khi gặp timeout, client không thể mặc định kết luận request chưa thành công; cần **đọc lại trạng thái thực tế** rồi mới retry hoặc bù trừ.

## 5. Vì sao `@Transactional` không tự giải quyết bài toán?

Spring Data LDAP hỗ trợ thao tác repository và `LdapTemplate`, còn **Spring LDAP** có cơ chế giao dịch bù trừ phía client thông qua các thành phần như `ContextSourceTransactionManager` khi ứng dụng cấu hình sử dụng. Cần phân biệt ba trường hợp:

| Cơ chế | Điều có thể cung cấp | Giới hạn quan trọng |
| --- | --- | --- |
| Không cấu hình LDAP transaction manager | Các thao tác LDAP độc lập | Lệnh thứ hai lỗi không tự đảo ngược lệnh thứ nhất |
| Spring LDAP *compensating transaction* | Ghi nhận thao tác để cố gắng thực hiện thao tác đảo ngược khi rollback | Không tạo giao dịch nguyên tử thực sự trên server; dữ liệu trung gian có thể bị quan sát; rollback có thể thất bại hoặc xung đột |
| LDAP Transaction extension, RFC 5805 | Cơ chế giao dịch trên server cho các thao tác được hỗ trợ, nếu server và client đều triển khai | Là phần mở rộng tùy chọn; không được mặc định có, không tự bật chỉ bằng `@Transactional` |

Annotation `@Transactional` chỉ có hiệu lực đúng với transaction manager được chọn và các tài nguyên mà manager đó quản lý. Nếu ứng dụng đang dùng JDBC transaction manager, việc thêm `@Transactional` quanh mã LDAP **không biến hai lần `ldapTemplate.modifyAttributes(...)` thành một giao dịch LDAP**.

Với cơ chế bù trừ, ví dụ request 1 thêm Lan vào nhóm mới, khi request 2 thất bại phần mềm có thể thử xóa Lan khỏi nhóm mới. Nhưng nếu một tác nhân khác vừa thay đổi nhóm đó, hành động bù trừ có thể xung đột hoặc đảo ngược một thay đổi hợp lệ. Bản thân bù trừ cũng có thể thất bại do mất mạng hoặc quyền truy cập. Vì vậy không được mô tả cách này như rollback ACID.

**RFC 5805** định nghĩa một phần mở rộng giao dịch LDAP phía server. Việc dùng được hay không cần kiểm tra khả năng quảng bá của server (ví dụ các OID liên quan trong `supportedExtension` của Root DSE), tài liệu triển khai, giới hạn hoạt động được hỗ trợ và kết quả kiểm thử tích hợp. Một client Spring LDAP thông thường không tự chuyển chuỗi thao tác thành giao dịch RFC 5805 khi chưa triển khai cơ chế chuyên biệt.

## 6. Cạnh tranh ghi: một entry cũng có thể bị mất cập nhật

Tính nguyên tử của một request **không ngăn lỗi lost update** khi nhiều client cùng đọc rồi ghi.

Giả sử thuộc tính `uniqueMember` của một nhóm lúc đầu chứa `[A]`:

1. Client X đọc `[A]` và chuẩn bị ghi `[A, B]`.
2. Client Y cũng đọc `[A]` và chuẩn bị ghi `[A, C]`.
3. X gửi `REPLACE_ATTRIBUTE(uniqueMember=[A, B])`, thành công.
4. Y gửi `REPLACE_ATTRIBUTE(uniqueMember=[A, C])`, thành công.

Kết quả cuối là `[A, C]`: phần tử `B` do X thêm đã bị ghi đè. **Mỗi request vẫn nguyên tử**, nhưng quy trình đọc–sửa–ghi của hai client không được bảo vệ khỏi cạnh tranh.

Khi chỉ muốn thêm hoặc xóa một giá trị thuộc tính đa trị, ưu tiên `ADD_ATTRIBUTE` / `REMOVE_ATTRIBUTE` để server áp dụng thay đổi **trực tiếp lên entry hiện tại**, tránh đọc toàn bộ danh sách rồi `REPLACE_ATTRIBUTE` bằng bản sao cũ.

Để kiểm soát thay đổi dựa trên một trạng thái đã đọc, LDAP có **Assertion Control** (RFC 4528): server chỉ thực hiện một thao tác nếu điều kiện assertion đúng tại thời điểm xử lý. Có thể dùng thuộc tính phiên bản/cập nhật nếu server hỗ trợ và cho phép đọc; nếu điều kiện không còn đúng, client nhận lỗi rồi đọc lại để tính toán lại thay đổi. Những thuộc tính như `modifyTimestamp`, `entryCSN` hoặc `uSNChanged` có mức hỗ trợ và ngữ nghĩa khác nhau giữa các directory; không được giả định chúng luôn là bộ đếm phiên bản duy nhất, có độ phân giải đủ cao hoặc hoạt động giống nhau trên mọi replica.

Một lời gọi `Compare` trước `Modify` **không thay thế** được assertion trong cùng thao tác: giữa hai request, entry vẫn có thể bị tác nhân khác sửa. Khóa ở phía ứng dụng cũng chỉ hữu ích khi **mọi bên ghi** đều tôn trọng cùng cơ chế khóa, kể cả công cụ quản trị và các dịch vụ khác.

## 7. Chiến lược bảo đảm nhất quán khi phải sửa nhiều entry

### 7.1. Ưu tiên mô hình dữ liệu có thể cập nhật trong một entry

Nếu quy tắc nghiệp vụ có thể biểu diễn bằng nhiều thuộc tính của **một entry**, gom các thay đổi vào **một** `ModifyRequest`. Chẳng hạn cập nhật đồng thời `mail` và `telephoneNumber` của một nhân viên sẽ có bảo đảm nguyên tử rõ ràng hơn so với cập nhật hai entry độc lập.

Không nên nhồi dữ liệu của nhiều đối tượng vào một entry chỉ để có nguyên tử: schema, kích thước thuộc tính, quyền truy cập và truy vấn phải vẫn phù hợp. Với quan hệ thành viên giữa **hai nhóm độc lập**, thường không thể loại bỏ hoàn toàn cập nhật nhiều entry.

### 7.2. Thiết kế workflow có thể khôi phục

Khi không có server-side transaction phù hợp, nên coi việc cập nhật nhiều entry là **quy trình nhiều bước** và định nghĩa rõ trạng thái đích.

Một workflow có thể triển khai theo thứ tự:

1. **Xác định đích:** ghi nhận yêu cầu chuyển Lan từ nhóm cũ sang nhóm mới, cùng mã thao tác duy nhất.
2. **Đọc và kiểm tra:** xác minh các DN, loại entry (`objectClass`), các thuộc tính bắt buộc, quyền cập nhật và trạng thái thành viên hiện tại.
3. **Thực hiện:** gửi các `ModifyRequest` riêng, theo thứ tự phù hợp chính sách an toàn/quyền truy cập.
4. **Xác minh:** đọc lại **cả hai nhóm** sau khi cập nhật; chỉ coi nghiệp vụ hoàn tất nếu trạng thái thực tế khớp trạng thái mong muốn.
5. **Khôi phục:** khi có lỗi hoặc timeout, ghi nhận kết quả chưa chắc chắn và thực hiện đối soát: hoàn thành bước còn thiếu hoặc bù trừ **sau khi kiểm tra trạng thái hiện thời**.

Khi nhiều hệ thống cùng phối hợp, nhật ký workflow nên được lưu ở **kho bền vững phù hợp** để tiến trình có thể phục hồi sau khi ứng dụng khởi động lại. Ghi nhật ký ở cơ sở dữ liệu ngoài LDAP và sửa LDAP là hai hệ thống riêng: chúng **không tự có một giao dịch ACID chung**. Thiết kế theo cơ chế sự kiện, outbox, saga hoặc đối soát định kỳ thường hướng tới **nhất quán cuối cùng**, với thao tác retry và xử lý trùng lặp được định nghĩa rõ.

### 7.3. Retry dựa trên trạng thái, không chạy lại mù quáng

Lỗi sau timeout có thể nghĩa là server đã thành công, nên retry phải đánh giá được điều kiện hoàn tất:

| Tình huống quan sát lại | Hành động có thể chọn |
| --- | --- |
| Lan chỉ ở nhóm cũ | Tiếp tục cập nhật theo thứ tự đã chọn |
| Lan ở cả hai nhóm | Nếu đích là chỉ nhóm mới, kiểm tra và xóa khỏi nhóm cũ |
| Lan chỉ ở nhóm mới | Đánh dấu hoàn tất; không thêm lại |
| Lan không ở nhóm nào | Xử lý theo chính sách an toàn, xác minh có tác nhân khác đang sửa |
| Nhóm/entry không còn tồn tại | Dừng, ghi nhận lỗi và xử lý thay đổi cấu trúc DN |

Không bắt mọi exception rồi mặc định coi là thành công. Chỉ xem các lỗi như `attributeOrValueExists` hoặc `noSuchAttribute` là **chấp nhận được** khi đã kiểm tra trạng thái cuối thật sự đúng và việc làm đó không che giấu lỗi schema, ACL hay thay đổi đồng thời.

### 7.4. Nếu cần nguyên tử trên nhiều entry thật sự

Với yêu cầu bắt buộc *all-or-nothing*, phải xác minh directory server có hỗ trợ giao dịch phía server tương thích (chẳng hạn RFC 5805) hay không, client có thực sự gửi thao tác trong giao dịch đó hay không, và phạm vi/giới hạn của giao dịch có đáp ứng nghiệp vụ hay không. Nếu không, ứng dụng cần thay đổi mô hình dữ liệu hoặc chấp nhận workflow có đối soát; không được hứa hẹn nguyên tử tuyệt đối chỉ bằng cơ chế retry hoặc bù trừ.

## 8. Tính nhất quán khi có nhiều LDAP replica

Trong hệ thống directory có replication, **thành công của một phép ghi trên một server không tự bảo đảm mọi replica đã thấy thay đổi ngay lập tức**. Ứng dụng có thể ghi vào nút A rồi tìm kiếm qua nút B và quan sát trạng thái cũ. Với thao tác nhiều entry, độ trễ replication còn có thể khiến người đọc nhìn thấy các tổ hợp trạng thái khác nhau.

Khi cần kiểm tra ngay sau khi ghi, hãy xác định rõ topology của directory:

- Có thể đọc lại cùng máy chủ đã nhận ghi hoặc dùng cơ chế bảo đảm nhất quán do server cung cấp.
- Tách lỗi ghi thật sự khỏi hiện tượng đọc từ replica chưa đồng bộ.
- Không lấy dữ liệu stale rồi lập tức ghi đè dữ liệu mới; khi cần, dùng kiểm soát đồng thời được server hỗ trợ.
- Xác định SLA đồng bộ, khoảng thời gian tối đa chấp nhận trạng thái trung gian và cơ chế xử lý khi đồng bộ kéo dài.

LDAP filter và search scope (`OBJECT`, `ONELEVEL`, `SUBTREE`) quyết định **entry nào được tìm**, còn replication và cấu hình server quyết định **phiên bản dữ liệu nào** client có thể nhìn thấy. Hai khái niệm này không thể thay thế nhau.

## 9. Kiểm thử các ranh giới nguyên tử

Chỉ kiểm thử trường hợp “cả hai lệnh đều thành công” là chưa đủ. Một bộ kiểm thử tích hợp nên chạy với directory tương thích với môi trường thật, chẳng hạn server LDAP thử nghiệm có schema và ACL tương ứng.

| Kịch bản | Cách kiểm tra | Điều cần xác nhận |
| --- | --- | --- |
| Một `Modify` gồm hai thuộc tính, thuộc tính thứ hai sai schema | Gửi cùng lúc hai thay đổi trong một request | Không có trạng thái chỉ thay đổi một thuộc tính |
| Cập nhật hai nhóm, request 2 bị từ chối | Cấu hình ACL/sai schema/giả lập lỗi có kiểm soát | Request 1 có thể đã được ghi; workflow phát hiện và phục hồi |
| Mất phản hồi sau request 1 | Giả lập timeout hoặc ngắt kết nối | Ứng dụng đọc lại trước khi retry, không tạo cập nhật sai |
| Hai client sửa cùng thuộc tính đa trị | Chạy đồng thời thao tác read–replace hoặc add/remove | Thấy nguy cơ lost update và xác minh cách xử lý |
| Hai client cùng chuyển thành viên | Thực hiện hai workflow có thể xung đột | Trạng thái đích rõ ràng, lỗi được đối soát, không hứa thứ tự không có bảo đảm |
| Có replica đọc chậm hơn nơi ghi | Đọc sau ghi trên các nút khác nhau | Ứng dụng xử lý được dữ liệu chưa đồng bộ |
| Cấu hình `@Transactional`/bù trừ | Làm request thứ hai thất bại và quan sát server | Không nhầm hành vi bù trừ với giao dịch server thật |

Trong kiểm thử, cần khẳng định **trạng thái trên directory sau lỗi**, thay vì chỉ khẳng định một exception đã bị ném ra. Đồng thời, với thao tác `uniqueMember`, bảo đảm nhóm thử nghiệm không vi phạm schema khi xóa thành viên; mọi nhận định về rollback phải dựa trên cấu hình transaction manager và khả năng LDAP server đang dùng.

## 10. Câu hỏi tự kiểm tra

1. Một request `Modify` có ba `ModificationItem` trên cùng entry thất bại ở bước kiểm tra schema. Entry có được giữ hai sửa đổi đầu tiên không? Vì sao?
2. Tại sao `@Transactional` bao quanh hai lời gọi `LdapTemplate.modifyAttributes(...)` chưa đủ để khẳng định atomicity trên hai entry?
3. Trong chuyển thành viên giữa hai nhóm, trường hợp thêm thành công nhưng xóa thất bại tạo trạng thái gì? Cần làm gì khi client nhận timeout?
4. Vì sao đọc `uniqueMember` rồi `REPLACE_ATTRIBUTE` cả danh sách dễ gây *lost update*? Khi nào nên dùng `ADD_ATTRIBUTE` / `REMOVE_ATTRIBUTE`?
5. Nếu ứng dụng ghi thành công vào replica A nhưng đọc trên replica B thấy dữ liệu cũ, liệu điều đó đã chứng minh thao tác ghi thất bại chưa?
6. Cơ chế bù trừ khác giao dịch server theo RFC 5805 về nguyên tử, khả năng quan sát trạng thái trung gian và khả năng phục hồi như thế nào?

## 11. Tổng kết

Trong Spring Data LDAP, **một yêu cầu Modify trên một entry** là ranh giới nguyên tử cơ bản có thể dựa vào. Khi nghiệp vụ thay đổi **nhiều entry**, phải xác định rõ trạng thái đích, rủi ro dở dang, cạnh tranh ghi và replication. Hãy ưu tiên một request khi mô hình dữ liệu cho phép; nếu không, lựa chọn giữa giao dịch server thực sự (khi được hỗ trợ) và workflow có retry, bù trừ, đối soát tùy yêu cầu nhất quán. Mọi phương án đều cần được kiểm chứng bằng directory và schema của hệ thống triển khai.

### Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol, mục 4.6 Modify Operation](https://www.rfc-editor.org/rfc/rfc4511#section-4.6).
- [RFC 4528 — Lightweight Directory Access Protocol (LDAP) Assertion Control](https://www.rfc-editor.org/rfc/rfc4528).
- [RFC 5805 — Lightweight Directory Access Protocol (LDAP) Transactions](https://www.rfc-editor.org/rfc/rfc5805).
- [Spring LDAP Reference — Transactions](https://docs.spring.io/spring-ldap/reference/transaction-support.html).
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html).
