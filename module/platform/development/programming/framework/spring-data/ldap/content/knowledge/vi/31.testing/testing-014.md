# Cô lập cây dữ liệu và dọn tài nguyên kiểm thử

LDAP lưu dữ liệu theo cây entry. Một entry được xác định bằng distinguished name (DN), trong đó DN của entry con chứa đường dẫn tới các entry cha. Vì vậy, hai bài kiểm thử cùng tạo `uid=alice,ou=people,dc=example,dc=test` trên một directory sẽ đụng nhau, dù chúng chạy ở hai lớp test khác nhau. Một bài test có thể đọc nhầm dữ liệu do bài khác tạo, hoặc thao tác dọn dẹp có thể xóa fixture mà bài khác đang dùng.

Với Spring Data LDAP, kiểm thử đáng tin cậy cần quản lý cả vòng đời của LDAP server, namespace DN, dữ liệu fixture và kết nối. Cấu hình cô lập phải phù hợp với cách ứng dụng tạo DN qua `@Entry`, `ContextSource`, repository và `LdapTemplate`. Việc chỉ xóa dữ liệu sau khi test chạy xong là chưa đủ nếu các test vẫn dùng chung DN trong lúc chạy.

## Vì sao phải cô lập theo cây DN?

Một directory có thể chứa nhiều nhánh nghiệp vụ, ví dụ:

```text
dc=example,dc=test
├── ou=employees
│   ├── uid=alice
│   └── uid=bob
└── ou=partners
    └── uid=alice
```

`uid=alice` có thể xuất hiện ở hai nhánh khác nhau vì DN đầy đủ khác nhau. Nhưng nếu nhiều test cùng dùng một nhánh `ou=employees` và cùng DN của nhân viên Alice, các test có thể gặp lỗi entry đã tồn tại, ghi đè hoặc xóa dữ liệu của nhau. Xóa entry cha còn có thể thất bại khi entry con vẫn tồn tại, bởi thao tác LDAP Delete thông thường chỉ xóa được entry lá.

Một test nên có namespace riêng, có thể là một server riêng, một base DN riêng hoặc một nhánh con riêng dưới suffix kiểm thử. Namespace đó cần được tạo trước khi seed dữ liệu và dọn sau khi hoàn thành, kể cả khi assertion thất bại.

## Chọn mức cô lập phù hợp

| Cách cô lập | Phạm vi phù hợp | Điểm cần lưu ý |
|---|---|---|
| LDAP server/container riêng cho từng test hoặc test class | Kiểm thử tích hợp cần cô lập mạnh, chạy song song hoặc thay đổi schema/cấu hình | Tốn thời gian khởi động và tài nguyên hơn; cần đóng container và kết nối đúng vòng đời. |
| Base DN riêng cho từng test class | Nhiều test dùng cùng server nhưng cần tách cây dữ liệu | Tạo nhánh gốc trước khi repository hoạt động; cấu hình `ContextSource` với base DN tương ứng trước khi Spring tạo repository. |
| OU riêng cho từng test method | Test dùng chung server và cùng `ContextSource` | Dùng DN có mã định danh duy nhất; mọi fixture phải nằm dưới OU đó để có thể dọn đúng phạm vi. |
| Attribute hoặc RDN duy nhất cho từng fixture | Repository có `@Entry.base` cố định | Sinh khóa duy nhất cho mỗi test và xóa đúng các entry đã tạo; không dùng dữ liệu dùng chung có thể bị test khác sửa. |

Đối với kiểm thử repository, server hoặc base DN riêng theo test class thường dễ quản lý hơn. Annotation `@Entry(base = "ou=employees")` khai báo nhánh tương đối cố định. Nếu muốn thay đổi base DN cho từng test method, cần một `ContextSource` và repository configuration riêng cho namespace đó; không nên thay đổi base DN của bean đang được nhiều test hoặc nhiều luồng sử dụng.

## Chuẩn bị LDAP server và suffix kiểm thử

Hãy dùng LDAP server có schema tương thích với directory đích. Embedded server phù hợp cho test nhanh, còn Testcontainers hoặc server thử nghiệm độc lập hữu ích khi cần xác minh hành vi của một sản phẩm LDAP cụ thể. Pin phiên bản image hoặc server để kết quả test có thể tái lập.

Suffix dành cho test nên tách khỏi dữ liệu phát triển và dữ liệu thật, ví dụ `dc=example,dc=test`. Khởi tạo suffix cùng các schema cần thiết trước khi chạy test. Tài khoản bind của test chỉ nên có quyền trên suffix này. Nếu kiểm thử ACL hoặc quyền bị từ chối, tạo một tài khoản và policy dành riêng cho tình huống đó.

Ví dụ cấu hình `ContextSource` trong test có thể nhận giá trị từ property riêng:

```yaml
app:
  ldap:
    url: ${TEST_LDAP_URL}
    base: dc=example,dc=test
    user-dn: ${TEST_LDAP_BIND_DN}
    password: ${TEST_LDAP_PASSWORD}
```

Không trỏ test vào directory production. Dùng thông tin xác thực riêng cho môi trường test và đóng LDAP container sau khi Spring context đã ngừng sử dụng connection pool. Nếu ứng dụng tự tạo `ContextSource` hoặc pool, bảo đảm bean có lifecycle đóng tài nguyên tương ứng.

## Tạo nhánh riêng cho từng test method

Khi nhiều test dùng chung một `LdapTemplate` có base DN là `dc=example,dc=test`, có thể tạo OU có mã định danh riêng cho mỗi test. `LdapNameBuilder` giúp xây dựng DN và xử lý escaping cho giá trị RDN, thay vì nối chuỗi DN từ dữ liệu đầu vào.

Ví dụ dưới đây tạo một nhánh kiểm thử, thêm một OU con và một person entry. Sau test, `unbind` với `recursive = true` xóa toàn bộ cây bắt đầu từ nhánh riêng đó:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class DirectoryTreeIntegrationTest {

    @Autowired
    private LdapTemplate ldapTemplate;

    private Name testBranch;
    private String branchRdn;
    private boolean branchCreated;

    @BeforeEach
    void createIsolatedBranch() {
        branchRdn = "it-" + UUID.randomUUID().toString().replace("-", "");
        testBranch = LdapNameBuilder.newInstance()
                .add("ou", branchRdn)
                .build();

        ldapTemplate.bind(testBranch, null, organizationalUnit(branchRdn));
        branchCreated = true;
    }

    @Test
    void readsAnEntryInsideItsOwnBranch() {
        Name peopleDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("ou", branchRdn)
                .build();
        ldapTemplate.bind(peopleDn, null, organizationalUnit("people"));

        String uid = "user-" + branchRdn;
        Name personDn = LdapNameBuilder.newInstance()
                .add("uid", uid)
                .add("ou", "people")
                .add("ou", branchRdn)
                .build();
        ldapTemplate.bind(personDn, null, personAttributes(uid));

        String commonName = ldapTemplate.lookup(
                personDn,
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("cn").get());

        assertEquals("Test " + uid, commonName);
    }

    @AfterEach
    void removeIsolatedBranch() {
        if (branchCreated) {
            ldapTemplate.unbind(testBranch, true);
            branchCreated = false;
        }
    }

    private Attributes organizationalUnit(String ou) {
        Attributes attributes = new BasicAttributes(true);
        BasicAttribute objectClasses = new BasicAttribute("objectClass");
        objectClasses.add("top");
        objectClasses.add("organizationalUnit");
        attributes.put(objectClasses);
        attributes.put("ou", ou);
        return attributes;
    }

    private Attributes personAttributes(String uid) {
        Attributes attributes = new BasicAttributes(true);
        BasicAttribute objectClasses = new BasicAttribute("objectClass");
        objectClasses.add("top");
        objectClasses.add("person");
        objectClasses.add("organizationalPerson");
        objectClasses.add("inetOrgPerson");
        attributes.put(objectClasses);
        attributes.put("uid", uid);
        attributes.put("cn", "Test " + uid);
        attributes.put("sn", uid);
        return attributes;
    }
}
```

Ví dụ giả định `ContextSource` đã cấu hình base DN `dc=example,dc=test` và suffix này đã tồn tại trên server. Các `Name` được truyền vào `LdapTemplate` là DN tương đối với base DN đó. Tên OU và UID có mã UUID để tránh va chạm khi JUnit chạy test song song. Schema server phải cho phép các objectClass và attribute được dùng trong fixture.

`branchCreated` chỉ được đặt thành `true` sau khi bind nhánh gốc thành công. Nếu bước tạo nhánh lỗi, teardown không cố xóa một DN chưa được tạo. Khi test đã tạo nhánh, thao tác dọn dẹp xóa cả các entry con, kể cả khi assertion ném lỗi.

## Cô lập kiểm thử Spring Data repository

Repository ODM ánh xạ entity theo `@Entry`. Ví dụ:

```java
@Entry(base = "ou=employees", objectClasses = {"inetOrgPerson"})
public class Employee {

    @Id
    private Name id;

    @Attribute(name = "uid")
    private String username;

    @Attribute(name = "cn")
    private String commonName;
}
```

Với entity này, repository tìm entry dưới nhánh `ou=employees` tương đối với base DN của `ContextSource`. Có hai cách phổ biến để tránh xung đột:

1. Cấu hình base DN riêng cho test class, chẳng hạn `ou=it-suite-a,dc=example,dc=test`, rồi tạo nhánh `ou=employees` bên dưới đó trước khi repository được dùng. Mỗi test class có namespace riêng và có thể seed dữ liệu theo LDIF hoặc fixture builder.
2. Giữ base DN cố định nhưng tạo `uid` duy nhất cho mỗi test. Lưu lại DN hoặc ID đã tạo để xóa đúng entry đó sau test. Nếu test tạo thêm group hoặc OU con, gom tất cả entry dưới một nhánh có thể dọn riêng.

Không thay đổi `ContextSource` base DN giữa các test method khi repository và connection pool đang dùng chung application context. Spring Test có thể cache application context, vì vậy hai lớp test với property khác nhau cần có cấu hình context phân biệt rõ. Nếu cần namespace riêng theo class, hãy cung cấp property trước khi context và repository được khởi tạo.

Một test repository nên xác minh cả đường đi DN lẫn dữ liệu trả về. Ví dụ, sau khi lưu entity, kiểm tra entry xuất hiện đúng dưới `ou=employees` của test base; sau khi xóa, kiểm tra DN đó không còn tồn tại. Điều này phát hiện trường hợp repository vô tình dùng nhầm `LdapTemplate` hoặc base DN.

## Dọn cây LDAP theo đúng thứ tự

LDAP không cho phép xóa entry cha khi vẫn còn entry con bằng thao tác Delete thông thường. Một cây có `ou=employees` chứa nhiều person entry phải được dọn từ các entry lá trước, rồi mới xóa OU cha.

Với Spring LDAP, `LdapTemplate` có overload `unbind(Name, boolean recursive)` để yêu cầu xóa đệ quy một nhánh. Chỉ gọi nó với DN gốc thuộc namespace test do test hiện tại sở hữu:

```java
ldapTemplate.unbind(testBranch, true);
```

Nếu cần tự kiểm soát thứ tự hoặc kiểm tra từng bước, hãy liệt kê các DN thuộc nhánh test, sắp xếp theo độ sâu giảm dần và xóa từng entry con trước entry cha. Sau khi xóa, xác minh nhánh gốc không còn tồn tại. Khi thao tác thủ công, không giữ `NamingEnumeration` hoặc `DirContext` mở lâu hơn cần thiết; đóng tài nguyên trong `finally` hoặc dùng API quản lý lifecycle phù hợp.

Một số nguyên tắc cần giữ:

- Chỉ xóa DN nằm dưới suffix kiểm thử và có namespace do test hiện tại tạo.
- Không xóa `dc=example,dc=test`, Root DSE hoặc nhánh fixture dùng chung của suite.
- Không dùng filter rộng để xóa toàn bộ entry có objectClass phổ biến như `inetOrgPerson`.
- Tạo parent entry trước child entry; xóa child entry trước parent entry.
- Nếu cleanup thất bại, để test suite báo lỗi rõ ràng. Không nuốt ngoại lệ khiến dữ liệu tồn dư bị che giấu.
- Với test cần xác minh hành vi xóa, đừng để teardown xóa fixture trước khi assertion kiểm tra kết quả nghiệp vụ hoàn tất.

Đối với một số LDAP server, quyền xóa subtree có thể khác quyền xóa từng entry. Hãy dùng tài khoản test được cấp quyền đúng phạm vi và kiểm thử riêng trường hợp ACL từ chối xóa. Không giả định một thao tác recursive luôn được server thực hiện nguyên tử; một lỗi giữa quá trình có thể để lại một phần cây dữ liệu.

## Chạy test song song mà không tranh chấp dữ liệu

Chạy song song giúp giảm thời gian suite, nhưng chỉ an toàn khi mỗi worker có namespace độc lập. UUID là cách đơn giản để sinh RDN riêng cho từng test. Với pipeline CI, có thể thêm run ID hoặc worker ID vào namespace để dễ truy vết dữ liệu còn sót sau một lần chạy bị hủy.

Nếu dùng một base DN cố định cho repository, tạo khóa duy nhất cho mỗi fixture và không tái sử dụng DN tĩnh như `uid=alice`. Nếu dùng namespace theo test class, mỗi class cần base DN riêng và teardown class chỉ xóa nhánh của chính class đó. Tránh một test dọn thư mục cha chứa dữ liệu của test khác.

Một số tài nguyên cũng cần giới hạn song song:

- LDAP server/container có thể dùng chung nếu dữ liệu được tách biệt, nhưng schema hoặc cấu hình toàn server không nên bị nhiều test sửa đồng thời.
- Không đổi schema, ACL hoặc cấu hình global trong một test chạy đồng thời với test khác.
- Mỗi test phải đóng connection hoặc context do chính nó tạo; không đóng bean `ContextSource` dùng chung khi test method kết thúc.
- Pool cần được đóng cùng application context hoặc container, sau khi các thao tác LDAP đã kết thúc.

## Xử lý lỗi giữa setup, assertion và cleanup

Setup có thể thất bại sau khi đã tạo một vài entry. Vì vậy, tạo một nhánh gốc trước, rồi đặt mọi fixture con dưới nhánh đó. Nếu bước seed tiếp theo thất bại, teardown chỉ cần xóa nhánh gốc để thu hồi phần dữ liệu đã tạo thành công.

Với fixture phức tạp, nên dùng helper hoặc JUnit extension quản lý tài nguyên. Helper cần ghi nhận DN gốc ngay khi nhánh được tạo thành công, cung cấp phương thức seed và luôn thực hiện cleanup khi kết thúc. Nếu test bị hủy do timeout hoặc JVM dừng đột ngột, teardown trong process có thể không chạy; namespace theo run ID giúp một bước dọn dẹp CI có thể nhận diện và xử lý dữ liệu tồn dư an toàn.

Không nên dựa vào `@Transactional` để rollback thao tác LDAP. Giao dịch Spring quản lý cho database không tự biến các thao tác LDAP thành giao dịch có rollback. Tương tự, `@DirtiesContext` chỉ loại bỏ hoặc làm mới Spring application context; nó không xóa entry đã ghi trên LDAP server bên ngoài context. Cần có cleanup dữ liệu rõ ràng.

## Kiểm tra dữ liệu và tài nguyên sau test

Sau mỗi test hoặc test class, kiểm tra rằng:

1. DN gốc thuộc namespace test không còn tồn tại sau cleanup.
2. Không còn child entry dưới nhánh test.
3. Fixture của namespace khác vẫn tồn tại và không bị thay đổi.
4. Không còn connection, context hoặc enumeration do test tự mở mà chưa đóng.
5. LDAP server/container được dừng sau khi mọi client đã ngừng sử dụng nó.

Trong CI, có thể ghi lại run ID, namespace DN và kết quả cleanup để truy vết. Nếu cleanup thất bại, báo DN gốc và lỗi LDAP result code để người bảo trì biết nhánh nào còn tồn tại. Tránh log mật khẩu bind hoặc dữ liệu nhạy cảm trong entry.

## Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `EntryAlreadyExistsException` | Nhiều test dùng cùng DN hoặc cleanup lần trước chưa hoàn tất | Dùng namespace/UID duy nhất; kiểm tra DN tồn dư trước khi seed. |
| `ContextNotEmptyException` hoặc lỗi không xóa được entry cha | Còn child entry trong nhánh | Xóa từ leaf lên hoặc dùng recursive unbind trong phạm vi an toàn. |
| Test đọc thấy dữ liệu của test khác | Dùng chung base DN và fixture có khóa cố định | Tách server, base DN, OU hoặc khóa fixture. |
| Test chạy riêng thì pass nhưng chạy song song thì fail | DN, schema hoặc cấu hình global bị chia sẻ | Dùng namespace riêng; không sửa schema/global state đồng thời. |
| Dữ liệu còn lại sau `@DirtiesContext` | Context bị đóng nhưng LDAP server vẫn giữ entry | Thêm cleanup trên LDAP hoặc tái tạo server/container. |
| Cleanup xóa nhầm fixture chung | DN cleanup quá rộng hoặc root DN không được kiểm tra | Ghi nhớ DN gốc do test tạo và giới hạn cleanup dưới suffix test. |

## Checklist thiết kế test

- [ ] LDAP server và suffix test được tách khỏi môi trường thật.
- [ ] Schema và objectClass cần thiết được nạp trước khi tạo fixture.
- [ ] Mỗi test hoặc test class sở hữu namespace DN riêng.
- [ ] DN được xây bằng API hỗ trợ escaping, không nối chuỗi từ input tùy ý.
- [ ] Fixture được tạo theo thứ tự parent trước child.
- [ ] Cleanup chạy kể cả khi assertion thất bại và chỉ xóa namespace của test.
- [ ] Cây được xóa từ leaf lên hoặc dùng recursive unbind trong phạm vi đã xác nhận.
- [ ] Test song song không chia sẻ DN, fixture hoặc thay đổi cấu hình global.
- [ ] Connection pool, context và container được đóng đúng lifecycle.
- [ ] Không dựa vào `@Transactional` hoặc `@DirtiesContext` để xóa dữ liệu LDAP.

Cô lập cây dữ liệu là một phần của thiết kế test, không phải bước vệ sinh tùy chọn. Khi mỗi test sở hữu một namespace rõ ràng, có setup và cleanup theo DN gốc, các kiểm thử Spring Data LDAP sẽ ổn định hơn, chạy song song an toàn hơn và dễ truy tìm nguyên nhân khi có dữ liệu tồn dư.
