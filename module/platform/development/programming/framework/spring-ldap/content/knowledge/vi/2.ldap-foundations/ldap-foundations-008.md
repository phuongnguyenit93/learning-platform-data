# Alias, referral và khác biệt giữa dữ liệu cục bộ với dữ liệu được trỏ tới

Khi tìm kiếm một nhân viên trong thư mục LDAP, ứng dụng có thể gặp ba tình huống: **entry thật nằm ngay trong vùng dữ liệu đang tra cứu**, **một alias trỏ tới entry khác**, hoặc **máy chủ trả về referral chỉ nơi tiếp tục truy cập**. Cả ba đều có thể trông giống “tìm thêm ở chỗ khác”, nhưng ý nghĩa, kết quả trả về và trách nhiệm của client hoàn toàn khác nhau.

Trong Spring LDAP, nhầm lẫn những tình huống này có thể khiến `LdapTemplate` trả về dữ liệu khác dự kiến, bỏ sót kết quả, truy cập nhầm máy chủ, hoặc phát sinh lỗi referral khó chẩn đoán. Bài học thuộc phần **LDAP nền tảng**, giúp người học nhận diện alias/referral, phân biệt dữ liệu trực tiếp với dữ liệu được tham chiếu, và thiết kế truy vấn an toàn trước khi tiến tới cấu hình `ContextSource`, xác thực, TLS, pooling và kiểm thử.

## 1. Bắt đầu từ entry và naming context

Mỗi entry LDAP có một **Distinguished Name (DN)** xác định vị trí trong **Directory Information Tree (DIT)**. Chẳng hạn:

~~~text
dc=example,dc=org
├── ou=people
│   └── uid=linh                  (entry người dùng thật)
├── ou=shortcuts
│   └── cn=contact-linh          (alias tới uid=linh)
└── ou=partners                  (điểm tham chiếu sang vùng dữ liệu khác)
~~~

Trong tình huống minh họa:

- `uid=linh,ou=people,dc=example,dc=org` chứa trực tiếp các thuộc tính như `uid`, `cn`, `mail`; đó là **entry dữ liệu thật**.
- `cn=contact-linh,ou=shortcuts,dc=example,dc=org` có DN riêng nhưng chứa thông tin **trỏ tới một DN khác**; nó là **alias entry**.
- `ou=partners,dc=example,dc=org` có thể được quản trị máy chủ LDAP cấu hình để hướng truy vấn sang một naming context khác qua **referral**.

Một **naming context** (còn gọi là naming partition/suffix tùy hệ triển khai) là phần cây thư mục mà máy chủ phục vụ như một vùng tên có thẩm quyền. Hai suffix có thể nằm trên cùng máy chủ hoặc các máy chủ khác nhau. Do đó, **“cục bộ” là nơi máy chủ đang xử lý truy vấn quản lý dữ liệu**, không nhất thiết là một cơ sở dữ liệu vật lý duy nhất.

| Tình huống | Bản chất | Dữ liệu hiển thị cho client |
| --- | --- | --- |
| Entry thật | Thuộc tính của đối tượng được lưu và phục vụ trong thư mục | Entry và các thuộc tính được cấp quyền đọc |
| Alias | Một entry có DN riêng, chứa `aliasedObjectName` là DN đích | Alias hoặc entry đích, **phụ thuộc chính sách dereference** |
| Referral | Thông tin tham chiếu đến vị trí LDAP khác có thể xử lý yêu cầu | Referral/LDAP URL, hoặc kết quả tiếp theo nếu client chủ động theo referral |

**Phân biệt then chốt:** Alias biểu thị một **tên thay thế** cho một đối tượng trong hệ thống tên LDAP; referral biểu thị **nơi tiếp tục xử lý yêu cầu**. Cả hai đều không đồng nghĩa sao chép nội dung entry đích vào vị trí trỏ.

## 2. Alias: tên thay thế cho entry

### 2.1. Cấu trúc alias entry

LDAP có object class `alias` cùng thuộc tính bắt buộc `aliasedObjectName` để lưu DN của đối tượng được tham chiếu. Ví dụ LDIF minh họa:

~~~ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org

dn: cn=contact-linh,ou=shortcuts,dc=example,dc=org
objectClass: top
objectClass: alias
objectClass: extensibleObject
cn: contact-linh
aliasedObjectName: uid=linh,ou=people,dc=example,dc=org
~~~

Ở đây:

- DN `cn=contact-linh,ou=shortcuts,dc=example,dc=org` định danh **chính alias**.
- Thuộc tính `aliasedObjectName` chứa **DN đích**, `uid=linh,ou=people,dc=example,dc=org`.
- Tên `contact-linh` chỉ là một điểm truy cập thuận tiện; cập nhật `mail` ở entry đích không đòi hỏi “đồng bộ” một bản sao `mail` trên alias.

Ví dụ giả định các entry cha `dc=example,dc=org`, `ou=people` và `ou=shortcuts` đã tồn tại. `extensibleObject` được dùng để minh họa khả năng gắn `cn` với alias; máy chủ thực tế có thể có quy tắc schema hoặc hạn chế riêng đối với alias. Không phải sản phẩm LDAP nào cũng hỗ trợ cùng mức độ các alias entry.

**Alias không phải một bản ghi người dùng khác.** Không nên đếm một alias như một tài khoản độc lập, áp chính sách tài khoản riêng cho alias, hoặc giả định các thuộc tính của đích nằm sẵn trên alias khi không dereference.

### 2.2. Dereference alias thay đổi kết quả search như thế nào?

Khi thực hiện LDAP `SearchRequest`, client có thể truyền chính sách **derefAliases**. Bốn giá trị chuẩn:

| Tùy chọn LDAP | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `neverDerefAliases` | `0` | Không tự giải alias khi tìm kiếm |
| `derefInSearching` | `1` | Giải alias gặp phải trong quá trình duyệt tập kết quả |
| `derefFindingBaseObj` | `2` | Giải alias nếu **base DN** của search là alias |
| `derefAlways` | `3` | Giải alias cả ở base và khi duyệt tìm kiếm |

Hai khía cạnh cần tách riêng:

1. **Base object**: client bắt đầu search tại DN nào? Nếu base chính là alias, tùy chọn `derefFindingBaseObj` ảnh hưởng việc tìm base đích.
2. **Các entry gặp trên đường duyệt**: khi search dưới một nhánh chứa alias, `derefInSearching` ảnh hưởng việc máy chủ tìm theo đích thay vì xem alias là entry thông thường.

Ví dụ truy vấn minh họa:

~~~text
Search base: ou=shortcuts,dc=example,dc=org
Scope:       ONELEVEL
Filter:      (objectClass=*)
derefAliases: neverDerefAliases
~~~

Với cấu hình không dereference, kết quả phù hợp có thể là **entry alias** `cn=contact-linh,...`, chứa `aliasedObjectName` chứ không tự xuất hiện `mail` của nhân viên. Nếu bật dereference trong tìm kiếm, máy chủ có thể duyệt tới entry `uid=linh,ou=people,...` và trả về DN/thuộc tính của **đích** theo quy tắc tìm kiếm, quyền truy cập và cách triển khai.

Kết quả cụ thể còn phụ thuộc việc server hỗ trợ dereference, search scope, ACL và alias có hợp lệ hay không. Alias không đảm bảo client luôn nhận đúng một kết quả hoặc luôn có thể vượt qua giới hạn vùng tên.

### 2.3. Những tình huống cần chú ý

- **Đích không tồn tại hoặc không thể truy cập:** dereference có thể thất bại; đừng mặc định alias luôn còn hiệu lực sau khi entry đích bị xóa hoặc chuyển DN.
- **Vòng tham chiếu:** alias trỏ vòng hoặc những cấu trúc không hợp lệ có thể gây lỗi; máy chủ có trách nhiệm thực thi các ràng buộc và giới hạn liên quan.
- **Quyền truy cập:** đọc được alias chưa có nghĩa được đọc thông tin nhạy cảm của entry đích. ACL vẫn có hiệu lực.
- **Đổi DN đích:** nếu quy trình quản trị không duy trì tham chiếu, `aliasedObjectName` có thể trở nên lỗi thời.
- **Khác biệt sản phẩm:** một số server không triển khai alias theo cách giống OpenLDAP; không đưa ra giả định chỉ từ tên sản phẩm hay object class.

Trong giao thức LDAP có các mã lỗi như `aliasProblem (33)` và `aliasDereferencingProblem (36)`. Ý nghĩa chính xác của lỗi và kiểu ngoại lệ ứng dụng nhận được phụ thuộc vào thao tác, server và lớp thư viện Java đang sử dụng.

## 3. Referral: thông tin chỉ nơi tiếp tục truy cập

### 3.1. Referral không phải alias

Giả sử LDAP server `directory.example.org` phục vụ `dc=example,dc=org`, còn dữ liệu của đối tác được quản trị trong `dc=partner,dc=example` tại `directory.partner.example`. Máy chủ thứ nhất có thể trả về **referral** khi client truy vấn tới vùng dữ liệu không thuộc trách nhiệm của nó.

Một referral có thể chứa LDAP URL, ví dụ:

~~~text
ldap://directory.partner.example/ou=people,dc=partner,dc=example
~~~

URL chỉ **điểm LDAP và DN tham chiếu**. LDAP URL có thể còn biểu diễn danh sách thuộc tính, scope, filter hoặc extension tùy trường hợp. Ví dụ dùng `ldap://` chỉ để làm rõ cú pháp; **không được tự động chuyển mật khẩu hoặc dữ liệu nhạy cảm qua kết nối không mã hóa** khi triển khai thật.

Referral có thể xuất hiện dưới hai dạng phổ biến ở cấp giao thức:

1. **`referral` result code (10):** LDAP server báo yêu cầu cần được xử lý ở nơi khác và cung cấp các URL tham chiếu.
2. **`SearchResultReference`:** trong một phép search, server có thể trả các tham chiếu để client tiếp tục tìm ở vùng khác, bên cạnh những entry tìm được cục bộ.

Đây là các phần của **kết quả giao thức**, không phải cùng kiểu dữ liệu với `SearchResultEntry` thông thường. Một truy vấn có thể tìm được vài entry cục bộ **và** gặp referral cho nhánh khác; không nên diễn giải referral thành “không có dữ liệu”.

### 3.2. Referral entry trong thư mục

Một số dịch vụ thư mục cho phép lưu **referral entry** để đại diện cho vị trí tham chiếu. Ví dụ mang tính minh họa, phụ thuộc server/schema:

~~~ldif
dn: ou=partners,dc=example,dc=org
objectClass: top
objectClass: referral
objectClass: extensibleObject
ou: partners
ref: ldap://directory.partner.example/ou=people,dc=partner,dc=example
~~~

Thuộc tính `ref` chứa URL của điểm được giới thiệu. Với server hỗ trợ referral entry, khi client truy cập vùng đó, server có thể phát referral thay vì trả entry có `objectClass=referral` như dữ liệu bình thường. Nếu cần quản trị và đọc chính referral entry, có thể cần cơ chế **ManageDsaIT control** (nếu server hỗ trợ), thay vì tìm kiếm thông thường.

**Không được đồng nhất referral entry với mọi `SearchResultReference`**: tham chiếu ở cấp giao thức có thể sinh ra do cấu hình naming context hoặc chính sách của server, kể cả khi client không nhìn thấy entry referral theo kiểu LDIF minh họa.

### 3.3. Theo referral (referral chasing) có nghĩa gì?

Client nhận referral có thể lựa chọn:

- **Không theo:** báo kết quả có referral, giữ URL làm thông tin định tuyến/khắc phục sự cố và trả về một trạng thái rõ ràng.
- **Theo có kiểm soát:** kiểm tra URL và chính sách tin cậy, kết nối đến điểm được chỉ, thực hiện lại thao tác cần thiết, rồi tổng hợp kết quả phù hợp.
- **Theo tự động thông qua LDAP provider:** nhờ thư viện thực hiện một phần quy trình, nhưng vẫn phải biết chính sách xác thực, TLS, vòng lặp và cách xử lý lỗi.

Việc theo referral phát sinh **yêu cầu mạng mới**. Máy chủ được trỏ tới có thể có chứng chỉ, tài khoản dịch vụ, ACL, schema, giới hạn truy vấn và chính sách bảo mật khác. **Không mặc nhiên tái sử dụng credential của máy chủ gốc với máy chủ bất kỳ có trong referral**. Cần allowlist đích tin cậy, xác minh TLS, giới hạn độ sâu/số lần chuyển hướng, timeout và phương án xử lý vòng lặp.

Một referral không bắt buộc phải hướng sang máy chủ vật lý khác; nó có thể chỉ một naming context khác trên cùng hạ tầng. Điểm quan trọng là **máy chủ đang trả lời không trực tiếp trả dữ liệu đó như một entry cục bộ của yêu cầu hiện tại**.

## 4. So sánh ba kiểu kết quả bằng ví dụ

Giả sử có hai nhánh nội bộ và một nhánh đối tác:

~~~mermaid
flowchart LR
    C["Ứng dụng Spring LDAP"] -->|"Search ou=people"| S["LDAP server A"]
    S -->|"SearchResultEntry: uid=linh"| C
    C -->|"Search ou=shortcuts"| S
    A["Alias: cn=contact-linh"] -.->|"aliasedObjectName"| P["Entry thật: uid=linh"]
    S --> A
    S --> P
    C -->|"Search ou=partners"| S
    S -.->|"Referral: LDAP URL"| C
    C -.->|"Chỉ khi chính sách cho phép"| B["LDAP server / naming context B"]
~~~

| Câu hỏi | Dữ liệu cục bộ | Alias | Referral |
| --- | --- | --- | --- |
| Đang đọc gì? | Thuộc tính của entry được trả trực tiếp | Alias entry hoặc entry đích tùy dereference | URL/chỉ dẫn tiếp tục truy vấn, hoặc dữ liệu từ điểm được theo |
| Có DN tại nhánh đang tìm? | Có DN của entry thật | Có DN riêng của alias | Có thể có referral entry, nhưng client thường thấy tham chiếu giao thức |
| Có tự tạo bản sao đối tượng không? | Không áp dụng | Không | Không |
| Có cần kết nối server khác? | Không vì chính entry đang được server phục vụ | Không phải chức năng của alias | Có thể cần, phụ thuộc URL và nơi lưu naming context |
| Có bị chi phối bởi ACL? | Có | Có trên alias/đích theo quy tắc server | Có ở cả điểm bắt đầu và đích khi client tiếp tục |
| Client cần quyết định gì? | Chọn filter/attribute/scope | Có dereference, đọc alias hay đích? | Có theo referral, tới đâu, bằng thông tin đăng nhập nào? |

**Ví dụ “thấy DN” không đồng nghĩa “có dữ liệu”:** Nếu một kết quả search chỉ cung cấp `aliasedObjectName`, bạn chưa chắc đã đọc được `mail` ở DN đích. Nếu kết quả là referral URL, bạn chưa nhận được entry đích nào cả. Chỉ khi server trả `SearchResultEntry` chứa thuộc tính được phép đọc, ứng dụng mới có chính dữ liệu cần thiết.

## 5. Search scope, filter và DN kết hợp với alias/referral

Một search LDAP được xác định tối thiểu bởi **base DN**, **scope**, **filter**, **thuộc tính yêu cầu**, cùng những thiết lập bổ sung như **derefAliases**, thời gian chờ và giới hạn kết quả.

~~~text
Base DN:       dc=example,dc=org
Scope:         SUBTREE
Filter:        (&(objectClass=inetOrgPerson)(uid=linh))
Attributes:    uid, cn, mail
Deref aliases: neverDerefAliases (minh họa)
~~~

Với dereference tắt, filter chỉ nhận các entry khớp điều kiện; alias dùng `objectClass=alias` sẽ không tự biến thành một `inetOrgPerson`. Bật dereference có thể làm search xét tới đối tượng đích. Nếu có referral tới nhánh khác, client còn phải quyết định có truy vấn bên đó hay không; chỉ đổi `derefAliases` **không** đồng nghĩa đã bật referral chasing.

Một số nguyên tắc thiết kế:

1. **Giới hạn base DN và scope** theo nhu cầu; không tra cứu cả cây khi chỉ cần `ou=people`.
2. **Dùng filter builder** để tạo điều kiện từ input người dùng, tránh LDAP injection; escaping cho filter khác escaping cho DN.
3. **Không đồng nhất DN của alias với DN của người dùng thật** khi tạo khóa tham chiếu hoặc phân quyền.
4. **Chỉ tổng hợp kết quả từ nhiều máy chủ** khi đã xác định được danh tính, tính duy nhất, quyền đọc và thứ tự ưu tiên của các nguồn dữ liệu.
5. **Phân biệt dữ liệu thiếu với dữ liệu chưa thể lấy** do referral, ACL, timeout hoặc lỗi mạng.

## 6. Trong Spring LDAP, xử lý như thế nào?

### 6.1. `LdapTemplate` truy vấn entry, nhưng không quyết định chính sách referral thay bạn

Ví dụ Java sau tìm tài khoản từ nhánh người dùng, dùng `LdapQueryBuilder` tạo filter thay vì ghép chuỗi:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public class EmployeeDirectoryReader {
    private final LdapTemplate ldapTemplate;

    public EmployeeDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<Employee> findByUid(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(query, (AttributesMapper<Employee>) attrs ->
                new Employee(
                        (String) attrs.get("uid").get(),
                        (String) attrs.get("cn").get()));
    }

    public record Employee(String uid, String name) {}
}
~~~

Ví dụ giả định `ContextSource` đã đặt base DN `dc=example,dc=org`, nên `ou=people` trong query là DN **tương đối**. `AttributesMapper` chỉ ánh xạ thuộc tính được trả về và được phép đọc. Trong thực tế cần xử lý attribute vắng mặt, nhiều kết quả trùng định danh, quy tắc về DN và ngoại lệ từ server.

Đoạn code **không tự đặt chế độ dereference alias**, **không tự bảo đảm referral được theo an toàn** và không thực hiện xác thực người dùng. Chính sách truy cập phụ thuộc vào `ContextSource`, LDAP provider, `SearchControls`/request tương ứng và cấu hình của server.

### 6.2. Hai nhóm cấu hình phải suy nghĩ riêng

| Nhóm | Ý nghĩa | Ví dụ trong LDAP/JNDI |
| --- | --- | --- |
| **Alias dereference** | Alias có được giải khi tìm base và/hoặc khi duyệt search không? | LDAP search `derefAliases`; với JNDI LDAP provider có thể có thiết lập `java.naming.ldap.derefAliases` với các giá trị như `never`, `searching`, `finding`, `always` |
| **Referral handling** | Client bỏ qua, tự theo hoặc yêu cầu đưa referral ra để ứng dụng xử lý? | JNDI `Context.REFERRAL` (`java.naming.referral`) thường nhận `ignore`, `follow`, `throw` |

Đây là **hai chính sách khác nhau**. Mặc định và hỗ trợ cụ thể tùy JDK/LDAP provider, phiên bản Spring LDAP và máy chủ. Khi cấu hình `LdapContextSource`, cần đọc tài liệu của đúng phiên bản được dùng và kiểm chứng bằng test tích hợp; không sao chép một giá trị property từ JNDI sang Spring mà chưa xác định đường truyền cấu hình.

Với JNDI, `throw` cho referral có thể khiến provider báo ngoại lệ cần được xử lý có chủ đích. `follow` có thể thực hiện truy vấn tới máy chủ khác. `ignore` không nên được hiểu là “mọi dữ liệu đã được lấy đầy đủ”; một số tình huống còn gây **partial result**. Spring LDAP thường chuyển đổi ngoại lệ JNDI thành hệ ngoại lệ truy cập LDAP của Spring, vì thế không được giả định `javax.naming.ReferralException` luôn đi thẳng tới service.

**Không nên bật `LdapTemplate#setIgnorePartialResultException(true)` chỉ để che lỗi.** Tùy hệ thống, lựa chọn này có thể làm mất dấu kết quả chưa hoàn chỉnh. Chỉ dùng khi đã hiểu rõ trường hợp server cụ thể và chấp nhận bỏ qua phần dữ liệu không truy xuất được.

### 6.3. Chọn chính sách thực tế

Đối với ứng dụng chỉ cần người dùng nội bộ từ một suffix đáng tin cậy, cách tiếp cận thường dễ kiểm soát là:

- Cấu hình `LdapContextSource` trỏ tới máy chủ đáng tin cậy bằng **LDAPS hoặc StartTLS**; xác minh hostname và chứng chỉ TLS.
- Dùng tài khoản bind tối thiểu quyền, lấy secret từ kho cấu hình bảo mật, không đưa credential vào source code và log.
- Chọn base DN giới hạn trong vùng dữ liệu thực sự quản lý; quyết định rõ có sử dụng alias hay không.
- Khi gặp referral, chỉ theo nếu ứng dụng cần dữ liệu từ suffix khác **và** có chính sách kiểm tra đích, TLS, credentials, timeout và giới hạn hop.
- Trả trạng thái riêng cho “không có entry”, “bị từ chối quyền”, “đang có referral chưa xử lý” và “lỗi kết nối”, tránh coi tất cả là danh sách rỗng.

Các tiện ích Spring LDAP như `LdapClient` hoặc LDAP ODM giúp cách viết thao tác và ánh xạ dữ liệu rõ ràng hơn, nhưng **không loại bỏ** các quyết định cấp giao thức về alias, referral, ACL và TLS.

## 7. Chẩn đoán sự cố khi truy vấn tham chiếu

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Search dưới `ou=shortcuts` trả alias nhưng không có `mail` | Không dereference alias | Kiểm tra `derefAliases`, filter, schema và DN đích |
| Search trả DN khác với DN bắt đầu | Alias được dereference | Ghi rõ DN thực tế trả về và đối chiếu `aliasedObjectName` |
| Có kết quả cục bộ nhưng thiếu nhân viên nhánh khác | Referral/search reference chưa được xử lý | Kiểm tra response result code/reference, naming context và chính sách referral |
| Client gặp lỗi referral/partial result | Provider đang báo tham chiếu chưa theo hoặc chỉ trả một phần | Kiểm tra `Context.REFERRAL`, log đã ẩn dữ liệu nhạy cảm và server trace |
| Đọc alias được nhưng không đọc entry đích | ACL trên entry đích, DN sai hoặc đích không tồn tại | Kiểm tra với tài khoản bind của ứng dụng và quyền theo từng entry |
| Referral dẫn tới lỗi TLS hoặc timeout | Endpoint khác chứng chỉ, kết nối, firewall hoặc DNS | Xác minh host, CA, timeout và danh sách máy chủ được phép |
| Truy vấn lặp qua nhiều referral | Cấu hình hướng tham chiếu vòng hoặc thiếu giới hạn | Giới hạn số hop/thời gian và kiểm tra cấu hình suffix |

Không lấy toàn bộ referral URL hoặc DN nhạy cảm đưa vào log công khai nếu chúng tiết lộ cấu trúc tổ chức. Mã lỗi LDAP hữu ích cho chẩn đoán, nhưng cần tránh lộ chi tiết hệ thống cho người dùng cuối.

## 8. Thực hành và kiểm thử

**Bối cảnh:** Bạn có một LDAP server thử nghiệm hỗ trợ alias và referral. Thiết lập `ou=people`, `ou=shortcuts`, một entry người dùng thật `uid=linh` và một alias `cn=contact-linh`. Nếu server hỗ trợ referral entry, cấu hình thêm `ou=partners` trỏ đến một dịch vụ LDAP kiểm thử thứ hai.

Thực hiện các lượt kiểm tra có mục đích:

1. **Đọc entry thật:** search `uid=linh` dưới `ou=people`, yêu cầu `uid`, `cn`, `mail`; ghi lại DN trả về.
2. **Đọc alias khi không dereference:** search nhánh `ou=shortcuts`, quan sát alias và `aliasedObjectName`; không mặc định alias chứa email.
3. **Bật dereference trong search:** lặp lại truy vấn với chính sách phù hợp, so sánh DN và thuộc tính kết quả, ghi lại khác biệt của server đang dùng.
4. **Thử đổi hoặc xóa entry đích trên môi trường thử nghiệm:** quan sát ảnh hưởng tới alias và mã lỗi khi dereference; khôi phục dữ liệu sau test.
5. **Kiểm thử referral:** truy vấn `ou=partners` với chính sách không tự theo, rồi thử theo có kiểm soát tới endpoint test đã tin cậy; so sánh kết quả và lỗi.
6. **Kiểm tra bảo mật:** từ chối referral sang host ngoài allowlist; từ chối kênh TLS không hợp lệ; xác nhận không làm lộ credential.
7. **Kiểm tra quyền và lỗi:** dùng tài khoản thiếu quyền đọc entry đích, gây timeout có kiểm soát và bảo đảm ứng dụng không trả “không tìm thấy” cho mọi trường hợp.

Không phải LDAP server nhúng dùng để test nào cũng hỗ trợ referral entry hoặc dereference alias đầy đủ. Khi cần xác minh hành vi của server sản xuất, nên kiểm thử tích hợp với **đúng loại server và schema** trong môi trường cô lập, không rút kết luận chỉ từ mock `LdapTemplate`.

### Câu hỏi tự đánh giá

**Câu 1:** Alias `cn=contact-linh` trỏ tới `uid=linh`. Khi đọc alias với dereference tắt, có chắc nhận được `mail` của Linh không?

**Đáp án:** Không. Client có thể nhận chính alias và `aliasedObjectName`; chỉ khi truy cập được entry đích theo chính sách thích hợp mới lấy được `mail`.

**Câu 2:** Server trả LDAP referral URL tới một server khác. Đây có phải bằng chứng người dùng đã được xác thực không?

**Đáp án:** Không. Referral chỉ cung cấp địa chỉ tham chiếu cho truy vấn. Xác thực bằng LDAP bind hoặc cơ chế IdP là vấn đề riêng; không gửi lại mật khẩu tới đích referral chưa được tin cậy.

**Câu 3:** Bật `derefAlways` có tự động theo referral không?

**Đáp án:** Không. `derefAliases` chi phối xử lý alias, trong khi chính sách referral chi phối cách client xử lý tham chiếu tới nơi khác.

**Câu 4:** Vì sao nên phân biệt “không có kết quả” và “partial result”?

**Đáp án:** Vì partial result có thể nghĩa là **vẫn còn vùng dữ liệu chưa truy cập được** do referral, ACL hoặc lỗi truy cập; trả danh sách rỗng như kết quả đầy đủ sẽ khiến ứng dụng đưa ra quyết định dựa trên thông tin thiếu.

Khi thiết kế ứng dụng Spring LDAP, hãy bắt đầu bằng câu hỏi: **“Tôi đang đọc entry tại DN này, giải một alias để đọc DN khác, hay nhận referral để quyết định tiếp tục truy vấn ở nơi khác?”** Câu trả lời quyết định cấu hình search, cách diễn giải kết quả và ranh giới tin cậy của kết nối.
