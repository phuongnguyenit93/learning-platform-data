# Phân biệt LDAP với cơ sở dữ liệu quan hệ và hệ thống xác thực

Khi xây dựng một ứng dụng nội bộ, ta thường gặp ba yêu cầu: tìm thông tin nhân viên, lưu dữ liệu nghiệp vụ và cho phép người dùng đăng nhập. Ba yêu cầu có thể cùng liên quan đến một người dùng nhưng không nhất thiết do cùng một công nghệ đảm nhiệm. Hiểu đúng ranh giới này giúp lựa chọn nơi lưu dữ liệu, thiết kế luồng xác thực và sử dụng **Spring LDAP** đúng mục đích.

Chẳng hạn, trong một doanh nghiệp, danh bạ tập trung chứa tên, email và phòng ban; hệ thống bán hàng lưu đơn hàng trong PostgreSQL; còn cổng đăng nhập một lần (SSO) xác thực nhân viên và cấp phiên đăng nhập. Ứng dụng Java có thể dùng **Spring LDAP** để tra cứu danh bạ, dùng JDBC/JPA để làm việc với PostgreSQL và dùng Spring Security cùng OpenID Connect để đăng nhập. Các thành phần có thể kết hợp, không phải lựa chọn loại trừ nhau.

## 1. Ba khái niệm thuộc ba lớp khác nhau

| Khái niệm | Bản chất | Câu hỏi chính mà nó giải quyết | Ví dụ |
| --- | --- | --- | --- |
| **LDAP** (Lightweight Directory Access Protocol) | Giao thức truy cập và thay đổi dữ liệu trong dịch vụ thư mục | “Tìm entry của nhân viên có mã này ở đâu? Nhân viên thuộc nhóm nào?” | Gửi yêu cầu LDAP đến OpenLDAP hoặc Active Directory Domain Services |
| **Cơ sở dữ liệu quan hệ** (RDBMS) | Hệ quản trị dữ liệu theo bảng, quan hệ và truy vấn SQL | “Đơn hàng nào thuộc khách hàng này? Giao dịch cần cập nhật những bảng nào?” | PostgreSQL, MySQL, SQL Server |
| **Hệ thống xác thực / nhà cung cấp danh tính** (authentication system / identity provider, IdP) | Thành phần xác minh danh tính và thường quản lý quy trình đăng nhập | “Người dùng này là ai, đã đăng nhập hợp lệ chưa, ứng dụng nhận bằng chứng gì?” | IdP hỗ trợ OpenID Connect, hệ thống Kerberos hoặc dịch vụ đăng nhập doanh nghiệp |

**Điểm dễ nhầm:** LDAP là **giao thức**, còn *LDAP directory/server* là dịch vụ thư mục triển khai giao thức đó. Dịch vụ thư mục thực sự lưu trữ dữ liệu theo cấu trúc entry, thuộc tính và cây phân cấp; nó có thể hỗ trợ thao tác xác thực bằng **bind**. Nhưng chỉ có một máy chủ LDAP chưa đồng nghĩa đã có mọi tính năng của một nền tảng đăng nhập hiện đại, chẳng hạn SSO trên trình duyệt, MFA, quản lý phiên hay phát hành token.

Tương tự, một RDBMS có thể lưu bảng người dùng và mật khẩu đã băm, còn IdP có thể lấy thông tin người dùng từ LDAP hoặc cơ sở dữ liệu. Vì thế, cần phân biệt **nơi lưu danh tính**, **cách kiểm tra danh tính** và **cách ứng dụng sử dụng kết quả xác thực**.

## 2. Mô hình dữ liệu: cây entry so với bảng quan hệ

### 2.1. Dịch vụ thư mục LDAP

Một thư mục LDAP tổ chức dữ liệu thành **Directory Information Tree (DIT)**. Mỗi nút là một **entry**, có **Distinguished Name (DN)** để định vị duy nhất trong cây và một tập thuộc tính (*attributes*). **Relative Distinguished Name (RDN)** là thành phần phân biệt entry với các entry cùng cha. Các **objectClass** quyết định những loại thuộc tính nào bắt buộc hoặc được phép xuất hiện theo schema của máy chủ.

Ví dụ dữ liệu minh họa ở định dạng LDIF:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: cn=editors,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: editors
member: uid=linh,ou=people,dc=example,dc=org
~~~

Ở đây, `uid=linh,ou=people,dc=example,dc=org` là DN của một người dùng; `uid=linh` là RDN; `mail` là một thuộc tính; còn `groupOfNames` biểu thị một nhóm chứa DN thành viên qua thuộc tính `member`. Các entry gốc như `dc=example,dc=org` được giả định đã tồn tại. Đây là dữ liệu minh họa, không phải cấu hình chạy trực tiếp trên mọi máy chủ.

Một thuộc tính LDAP có thể có nhiều giá trị, ví dụ một entry có nhiều số điện thoại. Cách lưu nhóm cũng không đồng nhất giữa các sản phẩm: có nơi dùng `member`, `uniqueMember`, `memberUid`, hoặc thuộc tính dẫn xuất `memberOf`. Đặc biệt, **`memberOf` không phải thuộc tính luôn tồn tại trên mọi máy chủ LDAP**. Schema, quyền truy cập và các tính năng mở rộng quyết định cách dùng thực tế.

### 2.2. Cơ sở dữ liệu quan hệ

Cùng thông tin đó có thể được biểu diễn thành các bảng:

~~~sql
CREATE TABLE employee (
    id BIGINT PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    email VARCHAR(320)
);

CREATE TABLE app_group (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE employee_group (
    employee_id BIGINT REFERENCES employee(id),
    group_id BIGINT REFERENCES app_group(id),
    PRIMARY KEY (employee_id, group_id)
);
~~~

Trong RDBMS, các bản ghi được nối với nhau qua khóa và quan hệ; truy vấn thường dùng `JOIN`, `GROUP BY`, các phép tổng hợp và giao dịch. RDBMS thích hợp với dữ liệu nghiệp vụ cần ràng buộc tham chiếu và cập nhật nhiều bảng trong một giao dịch.

| Khía cạnh | Dịch vụ thư mục LDAP | RDBMS |
| --- | --- | --- |
| Đơn vị dữ liệu | Entry với DN và attributes | Hàng trong bảng, có cột và khóa |
| Tổ chức | Cây phân cấp DIT | Bảng liên kết qua khóa |
| Định danh | DN định vị entry trong cây | Khóa chính định danh hàng |
| Truy vấn | Base DN, search scope, LDAP filter, thuộc tính trả về | SQL, điều kiện `WHERE`, `JOIN`, tổng hợp |
| Thay đổi | Thêm, sửa thuộc tính, xóa, đổi tên/di chuyển entry | `INSERT`, `UPDATE`, `DELETE`, giao dịch |
| Ràng buộc | Schema LDAP và quy tắc của máy chủ; liên kết DN tùy cách triển khai | Khóa chính, khóa ngoại, `CHECK`, các cơ chế giao dịch |
| Mẫu sử dụng thường gặp | Đọc và tra cứu danh tính, thông tin tổ chức, nhóm | Dữ liệu nghiệp vụ, quan hệ phức tạp, báo cáo và giao dịch |

**Không nên suy ra** LDAP không thể ghi dữ liệu hoặc RDBMS không phù hợp để đọc nhiều. Cả hai đều có cơ chế tìm kiếm và cập nhật. Khác biệt nằm ở **mô hình dữ liệu, giao thức và các loại truy vấn được tối ưu hóa**, chứ không phải một hệ chỉ đọc còn hệ kia chỉ ghi. Các khả năng về giao dịch nhiều entry, ràng buộc liên kết hay đồng bộ bản sao còn phụ thuộc sản phẩm LDAP cụ thể.

## 3. So sánh cách tìm kiếm

Giả sử ứng dụng cần lấy tên và email của nhân viên có `uid=linh`.

Với LDAP, cần xác định **base DN**, **phạm vi tìm kiếm (scope)**, **filter** và **những thuộc tính muốn lấy**:

~~~text
Base DN: ou=people,dc=example,dc=org
Scope:   SUBTREE
Filter:  (&(objectClass=inetOrgPerson)(uid=linh))
Attrs:   cn, mail
~~~

Trong filter, `&` nghĩa là AND; chỉ những entry thỏa cả hai điều kiện mới được trả về. Scope `SUBTREE` tìm trong toàn bộ cây con của base; `ONELEVEL` chỉ xét con trực tiếp; `OBJECT` chỉ xét chính entry được chỉ định. Nếu muốn tìm nhân viên theo họ, phòng ban hoặc nhóm, phải biết thuộc tính và schema mà máy chủ thực sự cung cấp.

Truy vấn gần tương ứng trong SQL:

~~~sql
SELECT display_name, email
FROM employee
WHERE username = :uid;
~~~

Hai truy vấn có mục tiêu gần giống nhau nhưng **LDAP search không phải SQL**. LDAP filter không hỗ trợ `JOIN` hay `GROUP BY` theo cách SQL thực hiện. Khi cần kết hợp dữ liệu thư mục với đơn hàng, phân quyền ứng dụng hoặc lịch sử giao dịch, ứng dụng thường tra cứu danh tính qua LDAP rồi xử lý dữ liệu nghiệp vụ trong RDBMS.

Khi viết ứng dụng, **không nối trực tiếp input người dùng vào LDAP filter hoặc DN**. Các ký tự như `*`, `(`, `)`, `\` và ký tự NUL có ý nghĩa đặc biệt trong cú pháp filter; ghép chuỗi sai có thể gây **LDAP injection**. Hãy dùng API tạo filter và DN có cơ chế escape phù hợp; việc escape DN và escape filter là hai bài toán khác nhau.

## 4. Xác thực khác gì với tra cứu thư mục?

**Tra cứu thư mục (directory lookup)** là lấy thông tin entry; **xác thực (authentication)** là xác minh người dùng đã cung cấp bằng chứng hợp lệ; **phân quyền (authorization)** là quyết định người dùng được làm gì. Chúng có thể đi cùng nhau nhưng không tương đương.

### 4.1. Xác thực trực tiếp qua LDAP bind

Một luồng đăng nhập LDAP phổ biến gồm các bước:

1. Ứng dụng dùng một kết nối được cấp quyền tra cứu tối thiểu để tìm DN của tài khoản theo định danh người dùng (ví dụ `uid`).
2. Ứng dụng thử **bind** đến máy chủ LDAP với DN tìm được và mật khẩu người dùng đã nhập, trên kênh TLS được xác minh chứng chỉ.
3. Máy chủ LDAP trả về kết quả bind. Ứng dụng xử lý thành công/thất bại theo chính sách bảo mật của mình.
4. Nếu đăng nhập thành công, ứng dụng quyết định quyền truy cập, tạo phiên hoặc chuyển kết quả cho thành phần bảo mật phù hợp.

Ví dụ trên mô tả **simple bind** bằng DN/mật khẩu; LDAP còn có các cơ chế SASL và chính sách xác thực khác. Việc tìm DN bằng tài khoản dịch vụ chỉ cần thiết khi ứng dụng chưa biết DN; không phải mọi kiến trúc đều phải có bước đó.

**Không đọc thuộc tính `userPassword` rồi tự so sánh với mật khẩu nhập vào.** Máy chủ có thể không cho đọc thuộc tính này, hoặc lưu giá trị theo cơ chế riêng. Trong đăng nhập LDAP thông thường, máy chủ thực hiện kiểm tra qua bind. Kết quả bind cũng phải được đánh giá cùng trạng thái tài khoản, quyền truy cập và chính sách của hệ thống.

### 4.2. Xác thực qua Identity Provider và SSO

Một IdP hiện đại thường cung cấp cơ chế đăng nhập tập trung, MFA, chính sách tài khoản và giao thức đăng nhập dành cho ứng dụng. Với **OpenID Connect (OIDC)**, ứng dụng có thể chuyển người dùng đến IdP, nhận kết quả của luồng đăng nhập và kiểm tra **ID token** theo các yêu cầu giao thức (chẳng hạn chữ ký, issuer, audience và thời hạn). Ứng dụng sau đó quản lý phiên hoặc xử lý token theo kiến trúc đã chọn.

IdP có thể tra cứu LDAP ở phía sau để tìm người dùng hoặc kiểm tra thông tin đăng nhập, nhưng **trình duyệt và ứng dụng thường giao tiếp với IdP qua OIDC/SAML, không trực tiếp gửi LDAP search**. LDAP, OIDC và SAML thuộc các lớp giao thức khác nhau. OAuth 2.0 chủ yếu là khung **ủy quyền truy cập**; OIDC bổ sung lớp xác thực danh tính dựa trên OAuth 2.0.

~~~mermaid
flowchart TD
    U["Người dùng"] --> APP["Ứng dụng Spring"]
    APP -->|"Tra cứu profile/nhóm qua Spring LDAP"| DIR["Dịch vụ thư mục LDAP"]
    APP -->|"Đăng nhập SSO qua OIDC"| IDP["Identity Provider"]
    IDP -.->|"Có thể tra cứu hoặc kiểm tra danh tính"| DIR
    APP -->|"Đọc, ghi dữ liệu nghiệp vụ"| DB["RDBMS"]
~~~

Sơ đồ cho thấy ba đường tích hợp phục vụ ba nhu cầu. Nó không bắt buộc IdP phải dùng LDAP; nhiều IdP dùng kho người dùng riêng, LDAP, hoặc nhiều nguồn kết hợp.

### 4.3. Phân quyền không tự xuất hiện từ LDAP

Một entry có thể thuộc nhóm `cn=editors,ou=groups,dc=example,dc=org`, nhưng điều đó **chưa tự động cho phép** người dùng sửa bài viết trong mọi ứng dụng. Ứng dụng phải ánh xạ nhóm sang quyền cụ thể, chẳng hạn `ROLE_EDITOR`, rồi kiểm tra quyền ở endpoint hoặc nghiệp vụ. Cần xét cả nhóm lồng nhau, độ trễ đồng bộ và cách máy chủ thể hiện membership nếu hệ thống có các đặc điểm đó.

Cũng cần phân biệt **Active Directory Domain Services (AD DS)** với **LDAP**: AD DS là dịch vụ thư mục của Microsoft hỗ trợ LDAP để truy cập dữ liệu; môi trường Active Directory còn có thể dùng Kerberos và các cơ chế khác cho xác thực. Vì vậy, “đăng nhập bằng AD” không có nghĩa mọi giao tiếp đều dùng LDAP.

## 5. Spring LDAP nằm ở đâu trong kiến trúc Spring?

Trong hệ sinh thái Spring, **Spring LDAP** cung cấp API để kết nối và thao tác với thư mục LDAP bằng Java:

| Thành phần | Trách nhiệm |
| --- | --- |
| `ContextSource` (thường là `LdapContextSource`) | Cấu hình cách tạo LDAP context, máy chủ, base DN và thông tin kết nối |
| `LdapTemplate` | Thực hiện search, bind, modify, unbind, rename và các thao tác thư mục, giảm mã JNDI lặp lại |
| `LdapClient` | API dạng fluent cho các thao tác LDAP trong phiên bản Spring LDAP có hỗ trợ |
| LDAP ODM | Ánh xạ LDAP entry và thuộc tính sang các đối tượng Java khi mô hình dữ liệu phù hợp |
| Spring Security | Tích hợp cơ chế xác thực, phiên và phân quyền; có thể dùng LDAP hoặc OIDC tùy yêu cầu |

Ví dụ một service dùng `LdapTemplate` để tìm email theo `uid`:

~~~java
import java.util.List;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public class EmployeeDirectoryService {
    private final LdapTemplate ldapTemplate;

    public EmployeeDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findEmails(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(query, (AttributesMapper<String>) attrs -> {
            Attribute mail = attrs.get("mail");
            return mail == null ? null : (String) mail.get();
        });
    }
}
~~~

Ví dụ giả định `LdapContextSource` đã cấu hình base DN `dc=example,dc=org`, nên `ou=people` trong truy vấn là **đường dẫn tương đối**. API dựng query giúp biểu diễn điều kiện tìm kiếm mà không tự nối chuỗi filter từ `uid`. Trong hệ thống thực tế, nên trả về một DTO thay vì để `null` trong danh sách, đồng thời xử lý trường hợp không tìm thấy entry, dữ liệu thiếu, quyền truy cập và lỗi kết nối.

Đoạn mã trên **chỉ tra cứu thông tin**. Nó không chứng minh người dùng đã đăng nhập và cũng không tạo phiên bảo mật. Khi cần xác thực bằng LDAP, có thể sử dụng các khả năng authentication tương ứng của Spring LDAP hoặc tích hợp **Spring Security LDAP**; khi cần SSO web, thường tích hợp Spring Security với OIDC theo chính sách doanh nghiệp.

Với kết nối thực tế, phải xem xét **LDAPS hoặc StartTLS**, xác minh chứng chỉ máy chủ, giới hạn quyền tài khoản tra cứu, timeout, kiểm soát kết nối và bảo vệ dữ liệu cá nhân. Pooling cần được cấu hình theo ngữ cảnh sử dụng, đặc biệt tránh tái sử dụng sai kết nối mang danh tính người dùng. Không đưa mật khẩu vào log hoặc chèn thẳng vào lệnh, chuỗi kết nối.

## 6. Khi nào chọn giải pháp nào?

Giả sử doanh nghiệp vận hành một cổng nhân sự, hệ thống đặt hàng và nhiều ứng dụng web:

| Nhu cầu | Thành phần nên cân nhắc | Lý do |
| --- | --- | --- |
| Danh bạ nhân viên dùng chung: DN, email, đơn vị, nhóm | Dịch vụ thư mục LDAP | Phù hợp với cấu trúc danh bạ và tra cứu thuộc tính tập trung |
| Đơn hàng, thanh toán, tồn kho cần giao dịch và báo cáo | RDBMS | Phù hợp quan hệ nghiệp vụ, SQL, ràng buộc và giao dịch |
| Nhân viên đăng nhập một lần vào nhiều ứng dụng | IdP hỗ trợ OIDC hoặc SAML | Cung cấp luồng SSO và cơ chế danh tính dành cho ứng dụng |
| Backend Java cần đọc phòng ban hoặc nhóm hiện tại từ thư mục | Spring LDAP | Giao tiếp với dịch vụ thư mục qua LDAP API |
| Ứng dụng cần áp dụng quyền “được duyệt đơn hàng” | Quy tắc phân quyền tại ứng dụng hoặc dịch vụ chính sách | Quyền nghiệp vụ không suy ra trực tiếp chỉ từ khả năng bind LDAP |

Một kiến trúc thường gặp là **LDAP quản lý dữ liệu nhân viên → IdP dùng nguồn danh tính đó khi cần → ứng dụng nhận kết quả đăng nhập qua OIDC → ứng dụng dùng RDBMS cho dữ liệu nghiệp vụ**. Spring LDAP chỉ cần xuất hiện ở những dịch vụ phải đọc hoặc quản lý entry LDAP trực tiếp.

## 7. Những nhầm lẫn cần tránh

1. **“LDAP là một loại SQL database.”** Sai ở mức mô hình: LDAP là giao thức truy cập thư mục, còn RDBMS dùng bảng và SQL; không thể chuyển nguyên câu SQL thành LDAP filter.
2. **“Có LDAP thì không cần hệ thống đăng nhập.”** Không chính xác: LDAP bind có thể tham gia xác thực nhưng một giải pháp SSO thường cần thêm IdP, token, phiên và chính sách bảo mật.
3. **“Tìm thấy người dùng trong LDAP nghĩa là đã xác thực.”** Sai: search trả về thông tin entry, không chứng minh người nhập tên tài khoản biết mật khẩu hoặc có phiên hợp lệ.
4. **“Có `memberOf` thì mọi ứng dụng tự có quyền.”** Sai: thuộc tính này có thể không tồn tại; khi tồn tại, ứng dụng vẫn phải kiểm tra và ánh xạ sang quyền nghiệp vụ.
5. **“Spring LDAP thay thế Spring Security.”** Không: Spring LDAP thao tác thư mục; Spring Security cung cấp khung xác thực và phân quyền cho ứng dụng Spring.
6. **“Có thể simple bind qua kết nối không mã hóa.”** Không nên: thông tin đăng nhập có thể bị lộ. Cần cấu hình TLS đúng, xác minh chứng chỉ và không âm thầm hạ cấp sang kết nối không bảo vệ.

## 8. Bài tập thiết kế ngắn

**Tình huống:** Một công ty có 30 ứng dụng nội bộ, đã quản lý hồ sơ nhân viên trong LDAP. Nhân viên muốn đăng nhập một lần; mỗi ứng dụng có dữ liệu giao dịch riêng và quy tắc phân quyền riêng.

**Câu hỏi:** Nên đặt hồ sơ nhân viên, giao dịch, đăng nhập và quyền nghiệp vụ ở đâu?

**Hướng giải:**

- Giữ thông tin danh bạ tập trung trong **dịch vụ thư mục** và dùng Spring LDAP ở những backend thực sự cần tra cứu entry/nhóm.
- Dùng **IdP hỗ trợ SSO** làm điểm đăng nhập thống nhất; IdP có thể tích hợp với LDAP như nguồn người dùng.
- Lưu **giao dịch và quan hệ nghiệp vụ** trong RDBMS của từng ứng dụng hoặc dịch vụ sở hữu dữ liệu.
- Kiểm tra **quyền nghiệp vụ** tại ứng dụng/dịch vụ chính sách; chỉ dùng nhóm LDAP như một nguồn thông tin để ánh xạ khi phù hợp.
- Đặt kết nối LDAP dưới TLS, kiểm soát tài khoản dịch vụ, quyền đọc và xử lý lỗi để việc tra cứu thư mục không làm lộ dữ liệu.

Tự kiểm tra: nếu ứng dụng tra cứu được `uid=linh` nhưng bind của người dùng thất bại, liệu có được mở phiên đăng nhập? **Không.** Nếu bind thành công nhưng người dùng không có quyền duyệt đơn, có được gọi API duyệt đơn? **Không.** Hai trường hợp nhấn mạnh rằng **tra cứu**, **xác thực** và **phân quyền** là ba quyết định riêng biệt.

