# NameAwareAttributeMapper và DN-aware mapping trong Spring LDAP

Khi đọc LDAP, ứng dụng thường chuyển một entry thành DTO hoặc đối tượng nghiệp vụ: lấy **uid**, **cn**, **mail** từ attributes rồi trả về Java object. Cách này đủ cho màn hình chỉ hiển thị thông tin. Tuy nhiên, khi cần cập nhật, xóa, đổi DN, phân biệt những người dùng trùng tên ở các OU khác nhau hoặc lưu liên kết đến một entry, đối tượng được map còn cần **Distinguished Name (DN)** của entry đó.

Chủ đề **NameAwareAttributeMapper và DN-aware mapping** trong chương **Resolver và accessor** đề cập đến việc **map cả DN và attributes** thay vì chỉ lấy thuộc tính. Với **SPRING_LDAP**, cách triển khai chuẩn là sử dụng **ContextMapper** và **DirContextOperations/DirContextAdapter**, hoặc tự tạo một adapter có hai tham số **(Attributes, Name)** nếu muốn tái sử dụng kiểu mapper thuần attributes.

> **Phân biệt tên API:** Trong Javadoc công khai của các phiên bản Spring LDAP phổ biến/hiện hành, không có interface tiêu chuẩn mang đúng tên **NameAwareAttributeMapper**. Đừng import một class giả định như **org.springframework.ldap.core.NameAwareAttributeMapper**. Đây có thể là tên gọi ý tưởng hoặc interface do dự án tự định nghĩa. Spring LDAP có **NameAwareAttribute** và **NameAwareAttributes**, nhưng đó là các lớp hỗ trợ *giá trị thuộc tính kiểu DN* trong **DirContextAdapter**, **không phải** mapper nhận DN của entry.

## 1. Vì sao AttributesMapper chưa đủ khi cần DN?

Giả sử directory có hai entry:

~~~text
uid=an,ou=engineering,ou=people,dc=example,dc=org
uid=an,ou=sales,ou=people,dc=example,dc=org
~~~

Nếu API chỉ map **uid=an**, cả hai có thể trở thành những đối tượng khó phân biệt. Nếu cần xóa một entry nhưng ứng dụng đoán DN từ **uid**, nó có thể chọn sai nhánh.

**AttributesMapper<T>** trong Spring LDAP có chữ ký:

~~~java
T mapFromAttributes(Attributes attributes) throws NamingException;
~~~

Nó nhận **Attributes** của từng kết quả tìm kiếm, không có tham số DN. Một mapper có thể trả về:

~~~java
(AttributesMapper<String>) attrs ->
        String.valueOf(attrs.get("cn").get());
~~~

Nhưng với chỉ các tham số này, mapper **không được bảo đảm** biết entry đang nằm ở OU nào. DN là **tên định danh của entry trong cây LDAP**, không phải thuộc tính thường tên **dn** được bảo đảm có mặt trong **Attributes**. Một số directory có thuộc tính vận hành như **entryDN**, nhưng sự hỗ trợ, ACL và cách yêu cầu trả về khác nhau; không nên dùng nó làm cách chung để khôi phục DN.

| Cách map | Mapper nhận được | Dùng khi nào |
| --- | --- | --- |
| **AttributesMapper<T>** | **Attributes** của entry | DTO chỉ có thông tin thuộc tính, không cần biết DN. |
| **ContextMapper<T>** | Object context, mặc định thường là **DirContextAdapter** | Cần **DN + attributes**, hoặc muốn dùng accessor của **DirContextOperations**. |
| **NameAwareAttributeMapper<T> tự định nghĩa** | **Attributes + Name** sau khi được adapter lấy từ context | Muốn giữ nghiệp vụ map theo thuộc tính nhưng cũng nhận DN tường minh. |

Chỉ khi đã xác định đúng nhu cầu mới nên chọn mapper; việc đổi từ AttributesMapper sang ContextMapper chủ yếu là để **giữ metadata định danh**, không tự động biến search thành thao tác bảo đảm duy nhất hay an toàn đồng thời.

## 2. DN tương đối và DN đầy đủ có ý nghĩa khác nhau

Giả sử **ContextSource** cấu hình base DN:

~~~text
dc=example,dc=org
~~~

Ứng dụng gọi **LdapTemplate.search(...)** với search base **ou=people**. Một kết quả có thể được biểu diễn bằng:

~~~text
DN đầy đủ (absolute DN):
  uid=an,ou=engineering,ou=people,dc=example,dc=org

DN tương đối với base của ContextSource:
  uid=an,ou=engineering,ou=people

Search base tương đối:
  ou=people
~~~

Với **DirContextOperations**, hai accessor đáng nhớ là:

- **getDn():** trả **javax.naming.Name** tương đối với **base LDAP path của ContextSource**; không mặc nhiên chỉ là phần **uid=an** hay tương đối với search base **ou=people**.
- **getNameInNamespace():** trả chuỗi DN đầy đủ trong namespace theo ngữ cảnh directory/provider, thường dùng khi cần danh tính LDAP đầy đủ, ví dụ đối chiếu member DN hoặc thao tác bind xác thực.

Ví dụ cách hiển thị (giả sử ContextSource và directory như trên):

~~~text
ctx.getDn()               -> uid=an,ou=engineering,ou=people
ctx.getNameInNamespace()  -> uid=an,ou=engineering,ou=people,dc=example,dc=org
~~~

Không gắn base DN hai lần. Nếu cần xây DN mới, dùng **LdapName** hoặc **LdapNameBuilder** thay vì nối chuỗi từ dữ liệu người dùng. Nếu thay **ContextSource** base hoặc chuyển môi trường, một DN tương đối có thể thay đổi ngữ nghĩa; hãy ghi rõ loại DN được lưu trong DTO, cache và API.

## 3. Ví dụ chuẩn: ContextMapper lấy cả DN và attributes

Đoạn mã dưới đây dùng **LdapTemplate** với **DefaultDirObjectFactory** (cấu hình mặc định phổ biến của Spring LDAP). Một kết quả search được chuyển thành **DirContextAdapter**, qua interface **DirContextOperations**. Ví dụ dùng Java 17+ để biểu diễn DTO dưới dạng **record**.

~~~java
import java.util.List;
import javax.naming.Name;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonDirectory {
    private final LdapTemplate ldapTemplate;

    public PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // Giữ cả hai loại DN để bên gọi không phải tự đoán đường dẫn.
    public record PersonEntry(
            Name relativeDn,
            String absoluteDn,
            String uid,
            String cn,
            String mail) { }

    private static final ContextMapper<PersonEntry> MAPPER = object -> {
        DirContextOperations entry = (DirContextOperations) object;

        // Clone Name để DTO sở hữu bản sao, tránh sửa nhầm Name trong adapter.
        Name dn = (Name) entry.getDn().clone();

        return new PersonEntry(
                dn,
                entry.getNameInNamespace(),
                entry.getStringAttribute("uid"),
                entry.getStringAttribute("cn"),
                entry.getStringAttribute("mail"));
    };

    public List<PersonEntry> findPeople() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningObjFlag(true);
        controls.setReturningAttributes(
                new String[] {"uid", "cn", "mail"});
        controls.setTimeLimit(3000); // Mỗi search, tính bằng ms.

        return ldapTemplate.search(
                "ou=people", // DN tương đối với base ContextSource
                "(&(objectClass=inetOrgPerson)(uid=*))",
                controls,
                MAPPER);
    }
}
~~~

Ví dụ này trả đúng DN của **mỗi entry**, kể cả khi tìm dưới nhiều OU con. Nếu kết quả chứa hai người có cùng **uid** nhưng ở những nhánh khác nhau, trường **relativeDn** vẫn phân biệt họ.

**Cách hoạt động:**

1. **SearchControls.SUBTREE_SCOPE** cho phép tìm trong các OU con của **ou=people**. Chọn scope phù hợp với bài toán, tránh search toàn domain khi chỉ cần một OU.
2. **setReturningObjFlag(true)** giúp lấy context object cho **ContextMapper** ở overload search nhận **SearchControls**; **DefaultDirObjectFactory** thường tạo **DirContextAdapter**. Nếu dự án thay object factory, cần kiểm tra loại object trước khi cast.
3. **entry.getDn()** lấy tên để dùng tiếp với các thao tác của **LdapTemplate** cùng **ContextSource base**; **getNameInNamespace()** cung cấp DN đầy đủ.
4. **getStringAttribute(...)** truy cập thuộc tính một giá trị. Thuộc tính **mail** có thể vắng mặt nên mapper phải chấp nhận **null** nếu nghiệp vụ cho phép. Với thuộc tính đa trị dùng **getStringAttributes(...)** hoặc accessor tương ứng.
5. **setReturningAttributes(...)** chỉ yêu cầu những thuộc tính cần thiết để giảm truyền tải, và **không xóa DN** khỏi context. Không thêm **userPassword**, token hoặc thuộc tính nhạy cảm nếu DTO không cần.

**Giới hạn:** Mapper trả DN hiện tại **tại thời điểm đọc**. Nếu entry bị rename/move trước khi API gọi update/delete, DN lưu trong DTO có thể đã cũ. Với thao tác ghi quan trọng cần kiểm tra lại định danh bất biến, trạng thái và quy tắc cạnh tranh phù hợp.

### Lookup một entry đã biết DN

Nếu đã có một **Name** tương đối với ContextSource base, dùng **lookup** cùng mapper:

Đặt phương thức sau **bên trong class PersonDirectory** ở ví dụ trên:

~~~java
public PersonEntry findAtUid(String uid) {
    if (uid == null || !uid.matches("[a-z0-9._-]{1,64}")) {
        throw new IllegalArgumentException("uid không hợp lệ");
    }

    Name personDn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", uid)
            .build();

    return ldapTemplate.lookup(personDn, MAPPER);
}
~~~

Phương thức này dùng **LdapNameBuilder** đã được import trong class **PersonDirectory**.

Ở đây DN đã được cung cấp trước khi lookup, nhưng **ContextMapper** vẫn hữu ích để áp dụng một quy tắc mapping thống nhất cho cả **search** và **lookup**. Nếu **uid=an** thực tế nằm dưới **ou=engineering,ou=people**, phải lookup đúng DN đầy đủ *tương đối với ContextSource*, không tự đoán vị trí.

## 4. Tự định nghĩa NameAwareAttributeMapper khi muốn nhận hai tham số

Đôi khi dự án có thư viện map DTO riêng nhận **Attributes** và **Name**. Có thể tạo một interface của ứng dụng tên **NameAwareAttributeMapper<T>** và cầu nối sang **ContextMapper<T>**. **Đây là mã ứng dụng tự định nghĩa, không phải import từ Spring LDAP.**

~~~java
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

public final class DnAwareMapping {
    private DnAwareMapping() { }

    // Interface do ứng dụng định nghĩa.
    @FunctionalInterface
    public interface NameAwareAttributeMapper<T> {
        T map(Attributes attributes, Name relativeDn)
                throws NamingException;
    }

    // Chuyển mapper tùy biến thành mapper mà LdapTemplate hỗ trợ.
    public static <T> ContextMapper<T> adapt(
            NameAwareAttributeMapper<T> mapper) {
        return object -> {
            DirContextOperations entry = (DirContextOperations) object;
            Name dn = (Name) entry.getDn().clone();
            return mapper.map(entry.getAttributes(), dn);
        };
    }
}
~~~

Sử dụng:

~~~java
import javax.naming.directory.Attribute;
import org.springframework.ldap.core.ContextMapper;

// Kiểu record được định nghĩa trong ứng dụng.
record BriefPerson(String relativeDn, String cn) { }

ContextMapper<BriefPerson> mapper = DnAwareMapping.adapt(
        (attrs, dn) -> {
            Attribute cn = attrs.get("cn");
            return new BriefPerson(
                    dn.toString(),
                    cn == null ? null : String.valueOf(cn.get()));
        });

List<BriefPerson> rows = ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        mapper);
~~~

Adapter giúp tách phần **lấy DN từ context** khỏi phần **map thuộc tính**. Vì **Attributes** không tự kèm DN theo hợp đồng của **AttributesMapper**, adapter phải lấy **Name** từ **DirContextOperations**, không được tự đoán DN từ **cn**, **uid** hoặc search filter.

Nếu mục tiêu chỉ là map **Attributes** thành DTO và không cần DN, **AttributesMapper** gốc đơn giản hơn. Nếu cần nhiều thông tin từ context ngoài DN, ví dụ **getStringAttributes(...)**, **getNameInNamespace()** hoặc thông tin referral, sử dụng thẳng **ContextMapper** thường rõ ràng hơn việc xây interface tùy biến.

## 5. Một số nhầm lẫn liên quan đến tên “NameAware”

Tên **NameAwareAttributeMapper** dễ bị nhầm với các API có thật:

| Tên | Vai trò thực tế | Có trả DN của entry cho mapper? |
| --- | --- | --- |
| **AttributesMapper** | Map các **Attributes** do search/lookup trả về. | **Không có tham số DN**. |
| **ContextMapper** | Map một **context object**, thường là **DirContextAdapter**. | **Có thể** lấy DN qua **DirContextOperations**. |
| **DirContextAdapter** | Gói attributes, DN và hỗ trợ theo dõi thay đổi thuộc tính. | **Có**, qua **getDn()** và **getNameInNamespace()**. |
| **NameAwareAttribute** | Hỗ trợ xử lý **Name làm giá trị attribute**, chẳng hạn member DN. | **Không phải mapper**. |
| **NameAwareAttributes** | Container attributes hỗ trợ **NameAwareAttribute**, được dùng trong adapter. | **Không phải mapper**. |
| **LdapAttributes** | Lớp attributes bổ sung trường DN và API **getName()** khi được dùng. | Chỉ khi đối tượng nhận được thực sự là loại đó và name đã được gán; **không giả định Attributes bất kỳ đều như vậy**. |
| **LdapName / Rdn** | Phân tích, so sánh, xây dựng DN/RDN có cấu trúc. | Là kiểu biểu diễn tên, không phải callback mapping. |

**NameAwareAttribute** đặc biệt hữu ích với thuộc tính **member** trong nhóm LDAP: giá trị **cn=An,ou=people,dc=example,dc=org** và **CN=An, OU=people, DC=example, DC=org** có thể biểu diễn cùng một DN. Khi sửa nhóm qua **DirContextAdapter**, truyền **Name** (ví dụ **LdapName**) thay vì chuỗi thô vào **addAttributeValue(...)** giúp so sánh các giá trị DN theo quy tắc tương ứng của adapter. Điều này **khác** việc cần biết DN của **entry được map**.

## 6. Đọc DN như một cấu trúc, không tách bằng split()

DN dùng dấu phẩy để phân tách **RDN**, nhưng dấu phẩy cũng có thể xuất hiện *bên trong giá trị* đã escape. Một **multi-valued RDN** còn dùng dấu cộng để ghép nhiều AVA trong cùng RDN:

~~~text
cn=An\, Binh+uid=an,ou=people,dc=example,dc=org
~~~

Nếu cần lấy RDN lá, dùng **LdapName/Rdn** của JNDI:

~~~java
import javax.naming.directory.Attributes;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName dn = new LdapName(
        "cn=An\\, Binh+uid=an,ou=people,dc=example,dc=org");

Rdn leaf = dn.getRdn(dn.size() - 1);
Attributes namingParts = leaf.toAttributes();

System.out.println(leaf.size());              // 2 AVA trong RDN lá
System.out.println(namingParts.get("cn").get());  // An, Binh
System.out.println(namingParts.get("uid").get()); // an
~~~

**Lưu ý với Java string:** **\\,** trong string literal tạo ký tự **\,** ở DN, nghĩa là dấu phẩy thuộc về giá trị **cn**, không phải dấu phân cách RDN. Tránh tự viết **dn.split(",")** hay **dn.split("+")** để trích xuất uid/OU.

Nếu **Rdn** chứa nhiều AVA, dùng **toAttributes()** để đọc đủ từng thành phần. Tùy trường hợp, **Rdn.getType()/getValue()** chỉ phản ánh một AVA, không phù hợp để lấy tất cả thuộc tính của RDN nhiều giá trị. Không mặc định mọi DN có RDN lá là **uid**; thiết kế schema có thể dùng **cn**, **mail** hoặc RDN ghép.

## 7. Lưu và sử dụng DN đúng cách sau mapping

DN rất hữu ích trong DTO, nhưng các tầng ứng dụng cần thống nhất **ý nghĩa và vòng đời** của nó:

**Khi đọc và hiển thị:** Có thể lưu **relativeDn** để gọi lại qua **LdapTemplate** dùng cùng ContextSource, hoặc **absoluteDn** để hiển thị/log có kiểm soát và làm tham chiếu LDAP đầy đủ. Nên trả một **ID nghiệp vụ ổn định** riêng (ví dụ mã nhân viên) để UI không dùng DN như một mã vĩnh viễn.

**Khi cập nhật/xóa:** Dùng DN vừa map làm điểm bắt đầu, nhưng **rename/move** có thể làm DN thay đổi. Kiểm tra đúng identity (ví dụ **entryUUID** nếu server hỗ trợ hoặc ID bất biến trong schema), quyền và trạng thái trước khi ghi. **Lookup rồi modify** là hai LDAP operations có cửa sổ cạnh tranh; khi cần tiền điều kiện nguyên tử phải dùng cơ chế server hỗ trợ như **Assertion Control** hoặc quy tắc đồng thời phù hợp.

**Khi lưu tham chiếu nhóm:** Thuộc tính **member** thường cần DN đầy đủ trong namespace, không phải DN tương đối với ContextSource. Nếu một entry được đổi DN, tham chiếu nhóm có thể cần được cập nhật tùy tính năng server. Đừng mặc định mọi directory tự duy trì referential integrity.

**Khi cache:** Key là DN có thể trở nên lỗi thời sau rename/move hoặc thay base. Nếu tổ chức hỗ trợ ID bất biến, hãy cân nhắc cache theo ID đó và lưu DN hiện hành làm dữ liệu có thể làm mới. Không dùng **cn** hoặc **uid** đơn lẻ làm định danh duy nhất khi chúng không được đảm bảo unique theo phạm vi hệ thống.

**Khi logging và bảo mật:** DN có thể chứa tên người, email hoặc cấu trúc tổ chức. Chỉ log thông tin cần thiết; áp dụng ACL, xác thực, **LDAPS/StartTLS** theo cấu hình. Không nhận DN tùy ý từ client rồi truyền trực tiếp sang **unbind(...)** hoặc **modifyAttributes(...)**; phải xác minh nhánh được quản lý và quyền ứng dụng.

## 8. Xử lý ngoại lệ và giới hạn của dữ liệu được map

| Trường hợp | Cách xử lý |
| --- | --- |
| **Không thấy thuộc tính được yêu cầu** | Accessor có thể trả **null**; xác định thuộc tính bắt buộc/không bắt buộc, kiểm tra schema và ACL. |
| **Thuộc tính đa trị** | Dùng **getStringAttributes(...)** hoặc API object values; không chỉ lấy phần tử đầu rồi xem là toàn bộ dữ liệu. |
| **DirObjectFactory tùy biến** | **ContextMapper** nhận Object khác **DirContextAdapter**; sửa mapper/cấu hình phù hợp trước khi cast. |
| **DN không hợp lệ trong dữ liệu đưa từ ngoài vào** | Sử dụng **LdapName/Rdn**, từ chối input lỗi; phân biệt escaping DN với escaping filter. |
| **Entry bị rename/move sau lúc đọc** | DN trong DTO đã cũ; lookup lại theo ID bền vững hoặc xử lý xung đột. |
| **Referral hoặc nhiều naming context** | **getNameInNamespace()** và hành vi điều hướng tùy provider/server; kiểm tra đích và phạm vi quyền. |
| **Có hai entry cùng uid ở hai OU** | Dùng DN đầy đủ và/hoặc ID nghiệp vụ unique; không gộp hai kết quả theo uid không đủ duy nhất. |
| **Không có quyền đọc thuộc tính** | LDAP có thể không trả dữ liệu hoặc trả lỗi theo ACL; mapper không được suy diễn giá trị bị ẩn. |

Nếu ứng dụng sử dụng **LdapClient** thay cho **LdapTemplate**, ý tưởng vẫn giống nhau: chọn phiên bản **map(ContextMapper<T>)** để lấy context chứa DN thay vì chỉ **map(AttributesMapper<T>)**. API cụ thể của builder có thể khác theo phiên bản; đừng gán cho **AttributesMapper** một tham số DN mà interface không có.

## 9. Kịch bản kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Search **SUBTREE_SCOPE** có cùng uid ở hai OU khác nhau | Hai DTO giữ hai **relativeDn/absoluteDn** khác nhau. |
| ContextSource có base **dc=example,dc=org** | **getDn()** tương đối với base đó; **getNameInNamespace()** phản ánh DN đầy đủ theo provider. |
| Search base **ou=people** và entry nằm trong OU con | Mapper **không** làm mất **ou=engineering** trong DN. |
| Thuộc tính **mail** vắng mặt | Mapper xử lý **null** theo hợp đồng DTO. |
| Mapper dùng **ContextMapper** cùng **setReturningObjFlag(true)** | Có thể nhận context từ DefaultDirObjectFactory và đọc DN/attributes. |
| Thay bằng **DirObjectFactory** tùy biến | Có kiểm thử loại object được đưa vào ContextMapper; không cast mù quáng. |
| DN có dấu phẩy escape và RDN hai AVA | **LdapName/Rdn** phân tích đúng từng thành phần. |
| Update nhóm dùng **Name** là member value | Không tạo modification trùng chỉ do khác biểu diễn chuỗi DN, theo tính năng adapter/server. |
| Entry đổi DN sau khi ứng dụng lưu DTO | Tầng ghi phát hiện DN cũ và xử lý theo identity/quy tắc cạnh tranh. |
| LDAP trả về thuộc tính nhạy cảm hoặc thiếu quyền | DTO chỉ chứa thuộc tính cho phép; không log dữ liệu bị bảo vệ. |

Unit test có thể tạo **DirContextAdapter** mẫu để kiểm tra **ContextMapper** và adapter **NameAwareAttributeMapper** tự định nghĩa. Integration test cần LDAP server tương thích để xác minh **getNameInNamespace()**, hành vi khi base DN khác nhau, search scope, ACL và rename/move thực tế.

## Ghi nhớ

**DN-aware mapping** nghĩa là kết quả map giữ **định danh LDAP** cùng với các thuộc tính của entry. **AttributesMapper** chỉ nhận **Attributes**; để biết DN của từng search result trong Spring LDAP, dùng **ContextMapper** kết hợp **DirContextOperations.getDn()** hoặc **getNameInNamespace()**. Nếu muốn API **NameAwareAttributeMapper**, hãy **tự định nghĩa interface và adapter** với đầu vào **(Attributes, Name)**, vì đó không phải interface mapper chuẩn đang được Javadoc Spring LDAP công bố. Luôn phân biệt DN tương đối và DN đầy đủ, xử lý cấu trúc DN bằng **LdapName/Rdn**, và kiểm tra identity/ACL trước thao tác ghi.

## Tài liệu tham khảo

- [Spring LDAP – AttributesMapper API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/AttributesMapper.html).
- [Spring LDAP – ContextMapper API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/ContextMapper.html).
- [Spring LDAP – DirContextOperations API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/DirContextOperations.html).
- [Spring LDAP – Simplifying Attribute Access and Manipulation with DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html).
- [Spring LDAP – NameAwareAttribute API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/NameAwareAttribute.html).
