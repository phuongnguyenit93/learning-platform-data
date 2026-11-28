# Xác định hệ thống nguồn và chiều đồng bộ

Trong một tổ chức, thông tin nhân viên có thể xuất hiện đồng thời ở hệ thống nhân sự (HRIS), dịch vụ quản lý danh tính (IAM), thư mục LDAP và nhiều ứng dụng. Các hệ thống này cần trao đổi dữ liệu, nhưng không thể để bất kỳ nơi nào cũng tùy ý sửa mọi thuộc tính: nếu tên, phòng ban hoặc quyền truy cập bị sửa ở hai phía, giá trị nào sẽ được giữ lại?

Bước đầu tiên khi thiết kế **đồng bộ dữ liệu** là xác định **hệ thống nguồn có thẩm quyền (system of record/source of truth)** cho từng loại thông tin, **hệ thống nhận dữ liệu** và **chiều đồng bộ**. Với **Spring Data LDAP**, quyết định này cho biết ứng dụng chỉ nên đọc entry LDAP qua repository/`LdapTemplate` hay được phép thực hiện các thao tác tạo, cập nhật, đổi DN và xóa entry. ODM giúp ánh xạ entry phân cấp sang đối tượng Java; bản thân ODM không quyết định dữ liệu của hệ thống nào là đúng.

Sau bài học, bạn có thể phân biệt nguồn và bản sao, mô tả luồng một chiều/hai chiều, lập ma trận quyền sở hữu thuộc tính và đề xuất cách xử lý sai lệch, xung đột, thay đổi DN, cập nhật nhóm và ngừng cấp quyền.

## 1. Từ một bài toán điển hình

Giả sử công ty vận hành:

- **HRIS** lưu mã nhân viên, họ tên, phòng ban và trạng thái làm việc.
- **IAM** tạo tài khoản, điều phối cấp/thu hồi quyền, gắn định danh tài khoản với mã nhân viên.
- **LDAP directory** lưu các entry người dùng/nhóm; ứng dụng sử dụng LDAP để tra cứu danh tính hoặc làm việc với dịch vụ xác thực.
- **Ứng dụng nghiệp vụ** đọc tên hiển thị, email và nhóm truy cập để xây dựng giao diện và kiểm soát quyền.

Một thiết kế có thể có luồng:

```text
HRIS ──(thông tin nhân sự)──> IAM ──(cấp phát tài khoản)──> LDAP
                                                              │
                                                     (đọc người/nhóm)
                                                              ▼
                                                      Ứng dụng Java
                                                   Spring Data LDAP
```

Trong mô hình trên, HRIS quyết định nhân viên còn làm việc hay không; IAM quyết định cách biến trạng thái đó thành thao tác cấp quyền; LDAP là nơi ứng dụng đọc dữ liệu danh tính đã được cung cấp. **LDAP không đương nhiên là nguồn gốc của mọi thuộc tính chỉ vì ứng dụng truy vấn LDAP.**

Một mô hình khác cũng hợp lệ: tổ chức trực tiếp quản trị nhóm trong LDAP, khi đó LDAP có thể là nguồn có thẩm quyền cho **thành viên nhóm** trong khi HRIS vẫn là nguồn cho **phòng ban**. Phải xác định quyền sở hữu **theo tập dữ liệu hoặc theo thuộc tính**, không chỉ chọn một “hệ thống chính” cho toàn bộ người dùng.

## 2. Hiểu đúng những vai trò trong đồng bộ

| Thuật ngữ | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| Hệ thống nguồn có thẩm quyền | Nơi được phép quyết định giá trị đúng của thuộc tính theo quy tắc nghiệp vụ | Ai được thay đổi giá trị này và thay đổi ở đâu? |
| Hệ thống đích | Nơi nhận bản sao hoặc dữ liệu suy ra để phục vụ nghiệp vụ | Đích cần những trường nào và với độ trễ bao nhiêu? |
| Bản sao/consumer | Hệ thống chỉ đọc hoặc lưu bản sao để tra cứu | Có được ghi ngược về nguồn hay không? |
| Chủ sở hữu thuộc tính | Dịch vụ/nhóm chịu trách nhiệm duy trì một thuộc tính | `mail`, `departmentNumber` hay `member` thuộc ai? |
| Khóa đối chiếu | Định danh để nhận ra cùng một người/tài khoản qua các hệ thống | Nếu DN hoặc email đổi, có còn nhận đúng tài khoản không? |
| Chiều đồng bộ | Đường dữ liệu được phép truyền giữa các bên | A → B, B → A, hay hai chiều có điều kiện? |
| Quy tắc xung đột | Cách quyết định khi hai nguồn có dữ liệu khác nhau | Hệ thống nào thắng, có cần duyệt thủ công không? |
| Độ trễ chấp nhận | Khoảng thời gian tối đa cho phép dữ liệu ở đích chậm hơn nguồn | Thu hồi quyền cần trong vài phút hay chấp nhận qua đêm? |

Phân biệt thêm **nguồn có thẩm quyền** với **hệ thống trực tiếp cung cấp dữ liệu cho chương trình**. Một ứng dụng có thể đọc `departmentNumber` trực tiếp từ LDAP, nhưng giá trị vẫn do HRIS sở hữu và được IAM truyền tới LDAP. Nếu phát hiện sai phòng ban trong LDAP, cách sửa bền vững thường là sửa ở HRIS hoặc luồng IAM tương ứng, sau đó đồng bộ lại.

## 3. Xác định hệ thống nguồn bằng ma trận thuộc tính

Thay vì ghi “LDAP là master”, hãy lập bảng quyết định theo từng trường. Ví dụ sau là **giả định thiết kế** cho một tổ chức; nguồn thật và các thuộc tính được phép ghi phải được xác nhận với đơn vị vận hành directory.

| Dữ liệu | Nguồn có thẩm quyền đề xuất | Luồng được phép | Ứng dụng Spring Data LDAP được làm gì? |
|---|---|---|---|
| Mã nhân viên (`employeeNumber`) | HRIS | HRIS → IAM → LDAP → ứng dụng | Đọc để đối chiếu; không sửa mã nhân viên |
| Họ, tên (`givenName`, `sn`, `cn`) | HRIS, qua quy tắc chuyển đổi của IAM | HRIS → IAM → LDAP → ứng dụng | Đọc; báo sai lệch về nguồn |
| Tên đăng nhập (`uid`) | IAM | IAM → LDAP → ứng dụng | Tra cứu; không tự đổi `uid` hoặc RDN |
| Email (`mail`) | Dịch vụ quản lý email hoặc IAM, tùy tổ chức | Chủ sở hữu email → IAM/LDAP → ứng dụng | Đọc; không mặc định sửa tại LDAP |
| Thành viên nhóm (`member`, `uniqueMember`) | IAM hoặc quản trị nhóm LDAP | Nguồn được chỉ định → LDAP → ứng dụng | Đọc nhóm; chỉ ghi khi được phân quyền rõ |
| Trạng thái còn làm việc | HRIS; IAM quyết định chính sách tài khoản | HRIS → IAM → directory/ứng dụng | Không tự suy ra rằng xóa entry là cách nghỉ việc |
| Cấu hình riêng của ứng dụng | Chính ứng dụng | Nội bộ ứng dụng | Lưu ở kho dữ liệu ứng dụng; không tùy tiện đẩy vào LDAP |

Các thuộc tính LDAP là một phần của **schema**: `objectClass` quy định tập thuộc tính bắt buộc và được phép. Không thể thêm một trường tùy ý vào entry chỉ vì đã thống nhất nó là “nguồn”. Ví dụ, muốn lưu mã đối chiếu riêng như `externalHrId`, phải kiểm tra schema có hỗ trợ hay cần mở rộng schema. Cũng không thể coi `mail`, `uid` hoặc tên hiển thị mặc nhiên là duy nhất giữa tất cả directory.

Khi lập ma trận, ghi rõ ít nhất: tên thuộc tính, nguồn có thẩm quyền, hệ thống nhận, quy tắc chuyển đổi, quyền đọc/ghi, khóa đối chiếu, tần suất cập nhật, cách xử lý khi mất dữ liệu và người chịu trách nhiệm vận hành.

## 4. Chọn chiều đồng bộ: một chiều, hai chiều và luồng nhiều chặng

### 4.1. Một chiều A → B

Đây là lựa chọn mặc định khi đã có một hệ thống sở hữu rõ ràng. Ví dụ:

```text
HRIS (nguồn phòng ban) ──> IAM ──> LDAP (bản sao) ──> App (chỉ đọc)
```

Nhân viên đổi phòng ban: HRIS phát sinh thay đổi; IAM chuẩn hóa giá trị rồi cập nhật entry LDAP; ứng dụng đọc giá trị mới. Nếu ai đó sửa `departmentNumber` trực tiếp trong LDAP, lần đối soát sau có thể ghi đè bằng giá trị HRIS. Cần quy định điều này công khai để tránh vòng lặp sửa sai.

**Ưu điểm:** nguồn rõ ràng, ít xung đột, dễ truy vết. **Đánh đổi:** nếu nguồn hoặc kênh đồng bộ ngừng hoạt động, đích sẽ có độ trễ; cần hàng đợi, retry hoặc đối soát.

### 4.2. Một chiều B → A

Chiều ngược lại hoàn toàn hợp lệ khi **LDAP là nguồn thật** của dữ liệu đang xét. Ví dụ, nhóm `cn=approvers,ou=groups,...` được quản trị trực tiếp bởi đội IAM trong directory, còn ứng dụng nghiệp vụ chỉ cần nạp danh sách thành viên để xét quyền. Khi đó luồng là **LDAP → ứng dụng** cho dữ liệu thành viên nhóm. Không nên đổi chiều chỉ vì ứng dụng cũng có nút “thêm thành viên”; nếu cần thay đổi nhóm, nút đó nên tạo yêu cầu tới hệ thống quản lý nhóm có thẩm quyền.

### 4.3. Hai chiều A ↔ B

Đồng bộ hai chiều cần nhiều quy tắc hơn một mũi tên trên sơ đồ. Chỉ nên cho phép khi yêu cầu nghiệp vụ thật sự cần dữ liệu thay đổi ở cả hai phía và có cơ chế giải quyết xung đột:

- **Chia quyền theo trường:** hệ thống A sở hữu `displayName`; hệ thống B sở hữu trường liên hệ do người dùng tự cập nhật. Mỗi bên chỉ ghi trường mình quản lý. Đây là hai luồng một chiều có phân quyền rõ.
- **Chia quyền theo đối tượng:** một số tài khoản do HRIS quản lý, tài khoản dịch vụ do IAM quản lý; nguồn được xác định theo loại tài khoản.
- **Cùng một trường có thể được sửa ở hai nơi:** phải xác định phiên bản, nguồn ưu tiên, điều kiện từ chối, cách hợp nhất hoặc quy trình duyệt thủ công. Không nên áp dụng “ai sửa sau thắng” chỉ vì dễ triển khai.

Với cùng thuộc tính như `sn` hoặc `member`, hai bên cùng sửa mà không có hợp đồng đồng bộ sẽ gây vòng lặp: A ghi B, B phát hiện thay đổi lại ghi A. Cần lưu nguồn gốc sự kiện, phiên bản/checkpoint và kiểm soát không phát lại thay đổi do chính mình tạo.

### 4.4. Luồng nhiều chặng

Sơ đồ **HRIS → IAM → LDAP → ứng dụng** gồm các hop có trách nhiệm khác nhau: HRIS cung cấp dữ liệu nhân sự, IAM ánh xạ và cấp quyền, LDAP lưu entry, ứng dụng tiêu thụ. Đừng coi các hop độc lập thành “mọi nơi đều có quyền sửa”. Nếu IAM là hệ thống trung gian, tài liệu thiết kế phải mô tả cả đường đi, biến đổi dữ liệu và cách báo lỗi ở từng chặng.

> **Cách gọi chiều dễ gây nhầm:** “Inbound” và “outbound” luôn phụ thuộc vào hệ thống đang xét. Với ứng dụng Java đọc LDAP, đó là **inbound vào ứng dụng** và **outbound từ LDAP**. Hãy viết rõ `LDAP → App` hoặc `HRIS → LDAP` trong tài liệu để tránh hiểu ngược.

## 5. Cách quyết định chiều đồng bộ theo từng bước

1. **Liệt kê hệ thống và dữ liệu:** ứng dụng nào dùng LDAP, ai tạo tài khoản, ai quản lý nhân viên/nhóm, có directory nào khác (ví dụ Active Directory) không?
2. **Xác định nguồn có thẩm quyền:** ai có quy trình nghiệp vụ và quyền chịu trách nhiệm cho từng thuộc tính? Quyết định theo từng trường và nhóm đối tượng.
3. **Xác định người nhận và nhu cầu:** đích dùng dữ liệu để đăng nhập, phân quyền, hiển thị hay báo cáo? Đích có cần sửa giá trị không?
4. **Chốt chiều và quyền ghi:** vẽ mũi tên cho mỗi tập thuộc tính, phân biệt chỉ đọc với quyền ghi; quy định ai được tạo/sửa/xóa entry.
5. **Chọn khóa đối chiếu ổn định:** ánh xạ cùng một tài khoản giữa HRIS, IAM và LDAP mà không dựa duy nhất vào thuộc tính có thể thay đổi như `cn`, `mail` hay DN.
6. **Quy định thời điểm và cách phát hiện thay đổi:** đồng bộ theo sự kiện, theo lịch hoặc đối soát toàn phần; ghi rõ mục tiêu độ trễ.
7. **Định nghĩa xử lý lỗi và xung đột:** nguồn nào thắng, khi nào retry, khi nào cách ly bản ghi, khi nào cần người xử lý, xóa và ngừng cấp quyền ra sao.
8. **Kiểm chứng với directory thực tế:** đối chiếu schema, quyền tài khoản bind, đặc tính đổi DN, hỗ trợ phát hiện thay đổi, dữ liệu đa trị và giới hạn kết quả tìm kiếm.

Một câu hỏi quyết định quan trọng là: **“Nếu LDAP và HRIS đang có hai giá trị khác nhau cho phòng ban, hệ thống nào được phép tự động sửa bên còn lại?”** Nếu chưa trả lời được, chưa đủ cơ sở để bật đồng bộ tự động thuộc tính đó.

## 6. Chọn khóa đối chiếu: DN không phải ID nghiệp vụ bất biến

LDAP lưu entry theo **Distinguished Name (DN)**, chẳng hạn:

```ldif
dn: uid=an.nguyen,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an.nguyen
cn: An Nguyen
sn: Nguyen
employeeNumber: HR-00421
mail: an.nguyen@example.org
```

Ở ví dụ này, DN giúp định vị entry trong cây; `uid` là thành phần của RDN, `employeeNumber` là mã liên kết với nhân sự. Nếu người dùng đổi tên đăng nhập hoặc chuyển từ `ou=people` sang `ou=alumni`, **DN thay đổi** dù con người không đổi. Nếu email đổi, `mail` cũng không còn dùng được làm khóa đối chiếu cũ.

Một thiết kế thường cần **mã định danh ổn định do hệ thống nguồn quản lý**, ví dụ mã nhân viên bất biến của HRIS hoặc một ID định danh được IAM phát hành. Trước khi dùng `employeeNumber` làm khóa đối chiếu, phải kiểm tra tính đầy đủ, duy nhất, khả năng bị tái sử dụng và chính sách thay đổi của tổ chức; LDAP schema không tự bảo đảm tính duy nhất toàn cục cho mọi thuộc tính.

Một số directory cung cấp ID nội bộ như `entryUUID` (tùy máy chủ LDAP) hoặc `objectGUID` (Active Directory). Chúng có thể hữu ích để theo dõi entry, nhưng phải kiểm tra khả năng hỗ trợ, quyền đọc và vòng đời ID khi di chuyển, xóa hoặc tạo lại entry. Không coi tên thuộc tính hoặc định dạng của chúng là phổ quát cho mọi LDAP server.

**Nguyên tắc:** khóa đối chiếu người/tài khoản giữa hệ thống cần ổn định theo nghiệp vụ; DN là địa chỉ hiện tại của entry. Hãy lưu mối liên hệ giữa hai giá trị và xử lý rõ sự kiện rename/move.

## 7. Thiết kế ranh giới truy cập với Spring Data LDAP

Giả sử ứng dụng Java là **consumer chỉ đọc** của LDAP, còn IAM có quyền provision tài khoản. Ta ánh xạ entry về đối tượng Java với ODM và giới hạn thao tác của tầng ứng dụng vào đọc/truy vấn.

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(objectClasses = {"inetOrgPerson"})
public class DirectoryAccount {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String username;

    @Attribute(name = "employeeNumber")
    private String employeeNumber;

    @Attribute(name = "mail")
    private String email;

    public DirectoryAccount() {}

    public Name getDn() { return dn; }
    public String getUsername() { return username; }
    public String getEmployeeNumber() { return employeeNumber; }
    public String getEmail() { return email; }
}
```

Ví dụ dùng repository để tra cứu:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryAccountRepository
        extends LdapRepository<DirectoryAccount> {
    List<DirectoryAccount> findByEmployeeNumber(String employeeNumber);
}
```

`findByEmployeeNumber(...)` giúp ứng dụng tra cứu entry dựa trên thuộc tính LDAP đã ánh xạ. Dù phương thức trả về một hoặc nhiều kết quả, ứng dụng vẫn phải kiểm tra yêu cầu **duy nhất** trước khi nhận đây là một tài khoản xác định; không được lấy phần tử đầu tiên và bỏ qua bản ghi trùng.

Khi cần chỉ rõ vùng tìm kiếm, có thể dùng `LdapTemplate` cùng trình xây dựng LDAP filter:

```java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class AccountDirectoryReader {
    private final LdapTemplate ldapTemplate;

    public AccountDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryAccount> findByEmployeeNumber(String hrId) {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .where("employeeNumber").is(hrId);
        return ldapTemplate.find(ldapQuery, DirectoryAccount.class);
    }
}
```

Giả định `LdapContextSource` đã cấu hình base DN `dc=example,dc=org`, nên `ou=people` là nhánh tương đối với base đó; thư mục thực tế phải hỗ trợ thuộc tính và object class được sử dụng. `LdapQueryBuilder` giúp escape giá trị filter đúng cách, tránh việc nối chuỗi nguy hiểm như `"(employeeNumber=" + hrId + ")"`. Nếu cần xây DN, hãy dùng `LdapNameBuilder` thay vì ghép chuỗi từ input.

**Không nên xem việc kế thừa `LdapRepository` là hàng rào quyền:** interface vẫn cung cấp các thao tác ghi như `save` hoặc `delete`. Trong kiến trúc chỉ đọc, tầng service chỉ công khai thao tác tra cứu, không gọi phương thức ghi và dùng **tài khoản bind LDAP chỉ có quyền đọc**. Quyền trên directory là lớp kiểm soát cuối cùng. Khi triển khai, cần cấu hình kết nối bảo vệ bằng LDAPS/StartTLS cùng xác thực chứng chỉ máy chủ.

Nếu hệ thống được chỉ định làm **writer vào LDAP**, tách riêng thành dịch vụ provision có trách nhiệm áp dụng thay đổi. Khi đó cần quyết định trước thao tác `LdapTemplate.bind(...)`/tạo mới, `modifyAttributes(...)`/sửa thuộc tính, `rename(...)`/đổi DN và `unbind(...)`/xóa, cùng cách repository nhận biết entry mới. Đó là các thao tác LDAP chịu schema và ACL; đừng xem chúng là `INSERT`/`UPDATE` SQL đơn giản.

## 8. Hợp đồng đồng bộ phải quy định trạng thái, xung đột và xóa

Giả sử quy tắc là **HRIS có thẩm quyền cho phòng ban**, **IAM có thẩm quyền cho `uid` và cấp quyền**, còn LDAP lưu trạng thái đã provision. Một hợp đồng đồng bộ đủ rõ có thể quy định:

| Tình huống | Quyết định | Hành động kỳ vọng |
|---|---|---|
| HRIS đổi phòng ban | HRIS thắng cho thuộc tính phòng ban | IAM chuyển đổi, cập nhật LDAP, ghi nhận phiên bản đã áp dụng |
| Ứng dụng sửa tên hiển thị cục bộ | Chỉ thay đổi dữ liệu cục bộ nếu ứng dụng sở hữu trường đó | Không tự ghi `cn` ngược vào LDAP |
| LDAP có phòng ban khác HRIS | Sai lệch tại bản sao LDAP | Ghi log chẩn đoán, đối soát và áp lại giá trị nguồn theo chính sách |
| Hai nhân viên trỏ tới cùng khóa đối chiếu | Không xác định được tài khoản duy nhất | Cách ly bản ghi, báo lỗi dữ liệu; không cập nhật bừa |
| `uid` hoặc OU thay đổi | IAM quản lý tên/vị trí entry | Đổi DN có kiểm soát, cập nhật liên kết hoặc tham chiếu cần thiết |
| Nhân viên nghỉ việc | HRIS quyết định trạng thái; IAM quyết định cách thu hồi | Vô hiệu hóa/thu hồi quyền theo loại directory, chính sách lưu trữ và kiểm toán |
| Bản ghi bị mất khỏi đợt đồng bộ gia tăng | Chưa đủ kết luận là đã xóa ở nguồn | Đối soát lại; chỉ xóa khi có sự kiện xóa hoặc chứng cứ đầy đủ |

Đặc biệt, **“xóa khỏi nguồn”**, **“không thấy trong kết quả tìm kiếm”**, **“vô hiệu hóa tài khoản”** và **“xóa entry LDAP”** là bốn sự kiện khác nhau. Một LDAP search có thể không trả entry vì search base, quyền ACL hoặc giới hạn kết quả; do đó không được biến một lần tìm kiếm không thấy thành lệnh xóa. Cách khóa tài khoản cũng phụ thuộc directory/schema; không có một thuộc tính `disabled` chuẩn chung cho mọi LDAP server.

Với nhóm LDAP, thành viên thường được biểu diễn bằng thuộc tính đa trị như `member` hoặc `uniqueMember` trên entry nhóm (tùy object class). Nếu đồng bộ nhóm từ IAM, hãy phân biệt **thay thế toàn bộ tập thành viên** với **thêm/bớt một thành viên**; bản sao một phần hoặc cập nhật đồng thời có thể làm mất thành viên hợp lệ.

## 9. Chọn cơ chế đồng bộ theo yêu cầu độ trễ

Sau khi xác định nguồn và chiều, mới chọn cách vận chuyển dữ liệu:

| Cơ chế | Phù hợp khi | Rủi ro và cách bù |
|---|---|---|
| Theo sự kiện từ nguồn | Cần cập nhật nhanh khi HRIS/IAM phát sinh thay đổi | Sự kiện có thể trễ, mất hoặc đến nhiều lần; cần retry và đối soát |
| Theo lịch/polling | Nguồn không phát sự kiện hoặc chấp nhận độ trễ | Phải có checkpoint an toàn, phân trang và phát hiện xóa |
| Đồng bộ đầy đủ/reconciliation | Khởi tạo hoặc sửa sai lệch định kỳ | Tốn tài nguyên; phải phân biệt thiếu dữ liệu vì lỗi đọc với xóa thật |
| Delta từ directory | LDAP server có cơ chế change log, sync control hoặc API thay đổi phù hợp | Hỗ trợ và ngữ nghĩa phụ thuộc máy chủ; cần xử lý mất checkpoint |

Một số directory cung cấp `modifyTimestamp` và các cơ chế đồng bộ thay đổi riêng. **Chỉ dựa vào thời điểm sửa gần nhất thường chưa đủ** để bảo đảm không bỏ sót: có khác biệt đồng hồ, giới hạn kết quả, trùng thời điểm và trường hợp entry bị xóa/di chuyển. Không mặc định mọi LDAP server đều có changelog hay hỗ trợ cùng một LDAP Sync control. Hãy kiểm tra khả năng thực tế của server rồi chọn cách lưu checkpoint và đối soát.

**LDAP replication** (sao chép giữa các máy chủ directory) cũng khác **đồng bộ nghiệp vụ** giữa HRIS, IAM, LDAP và ứng dụng. Replication giữ dữ liệu trong hạ tầng directory; nó không tự giải quyết ai có thẩm quyền cho phòng ban hay cách xử lý xung đột giữa HRIS và IAM.

### Ví dụ quy trình đồng bộ một chiều từ nguồn tới LDAP

Mô tả ở mức quy trình, không phải mã API chạy trực tiếp:

```text
1. Nhận bản ghi thay đổi từ HRIS/IAM kèm sourceId và version.
2. Kiểm tra quyền sở hữu trường; validate dữ liệu và mapping LDAP schema.
3. Tìm entry bằng khóa đối chiếu đã thống nhất; phát hiện 0/1/n kết quả.
4. Nếu chưa có và được phép cấp phát: tạo entry với DN hợp lệ.
5. Nếu đã có: chỉ cập nhật thuộc tính do nguồn này sở hữu.
6. Nếu cần đổi uid/OU: thực hiện rename/move theo chính sách.
7. Nếu nghỉ việc hoặc bị xóa ở nguồn: áp dụng chính sách thu hồi quyền.
8. Ghi kết quả, lỗi, version/checkpoint; chỉ xác nhận hoàn tất sau khi ghi thành công.
9. Định kỳ đối soát đầy đủ để phát hiện và sửa sai lệch.
```

Các bước cần **idempotent**: phát lại cùng sự kiện không được tạo thêm tài khoản hoặc nhân đôi thành viên nhóm. Nếu cập nhật nhiều entry, không mặc định có giao dịch ACID trải nhiều entry như RDBMS; cần lưu tiến độ, retry có giới hạn và quy trình bù trừ khi một phần thành công.

## 10. Kiểm thử thiết kế nguồn và chiều đồng bộ

Trước khi cho một luồng tự động ghi vào LDAP thật, hãy chuẩn bị directory thử nghiệm có schema/ACL tương đồng và kiểm tra:

1. **Nguồn đúng:** sửa phòng ban tại nguồn có thẩm quyền, xác nhận đích nhận; sửa trái phép tại bản sao không ghi ngược vào nguồn.
2. **Định danh:** đổi email, `uid` hoặc OU, bảo đảm vẫn khớp đúng người và không tạo tài khoản trùng.
3. **Tạo và cập nhật:** object class, thuộc tính MUST/MAY, thuộc tính đơn trị/đa trị, RDN và base DN phù hợp.
4. **Xung đột:** hai hệ thống sửa cùng trường, sự kiện đến sai thứ tự, nhận trùng và nhận lại sự kiện cũ.
5. **Ngừng cấp quyền:** nhân viên nghỉ việc, nhóm bị thu hồi, tìm kiếm không thấy tạm thời, bảo đảm không xóa nhầm.
6. **Khả năng phục hồi:** directory không truy cập được, giới hạn kích thước search, mất kết nối giữa chừng, checkpoint bị lệch.
7. **Bảo mật:** chứng chỉ LDAPS/StartTLS, tài khoản bind quyền tối thiểu, dữ liệu nhạy cảm, ký tự đặc biệt trong LDAP filter/DN và audit thao tác ghi.

Một hệ thống đồng bộ không chỉ cần “dữ liệu cuối cùng giống nhau”, mà còn phải trả lời: **dữ liệu đó đến từ nguồn nào, ai có quyền đổi, cập nhật nào bị bỏ qua, và có thể truy vết vì sao không?** Bên cạnh log kỹ thuật, nên theo dõi số lượng bản ghi đã xử lý, độ trễ, số xung đột, số lần retry, lỗi schema/ACL và số tài khoản bị cách ly.

## 11. Bài tập thiết kế

Hệ thống có HRIS quản lý hồ sơ nhân viên, IAM cấp phát tài khoản LDAP và một ứng dụng dùng Spring Data LDAP đọc người dùng/nhóm. Một nhân viên đổi phòng ban, đồng thời quản trị viên ứng dụng sửa phòng ban ngay trên màn hình ứng dụng. Sau đó tài khoản được chuyển từ `ou=people` sang `ou=alumni`.

Hãy tự trả lời:

1. Nguồn nào có quyền quyết định phòng ban, nguồn nào quyết định OU/tình trạng tài khoản?
2. Ứng dụng nên viết thẳng về LDAP hay gửi yêu cầu đến hệ thống có thẩm quyền?
3. Khóa nào giữ được liên kết người dùng khi DN đổi? Cần bảo đảm đặc tính gì của khóa?
4. Nếu một lần search LDAP không thấy entry, có đủ căn cứ xóa tài khoản khỏi ứng dụng không?
5. Bảng ma trận và log đồng bộ phải ghi gì để xác minh luồng đang hoạt động đúng?

**Gợi ý đối chiếu:** Trong thiết kế ví dụ, HRIS sở hữu phòng ban, IAM chịu trách nhiệm provision và chính sách chuyển OU, ứng dụng chỉ đọc LDAP. Khóa liên kết nên là định danh nghiệp vụ ổn định đã kiểm chứng tính duy nhất; không dựa duy nhất vào DN hoặc email. Việc không tìm thấy entry phải được xác minh trong bối cảnh base DN, ACL và trạng thái đồng bộ trước khi quyết định vô hiệu hóa/xóa bản sao.

**Ghi nhớ:** Với Spring Data LDAP, trước khi viết repository, `LdapTemplate` hay luồng CRUD, hãy thống nhất **ai sở hữu dữ liệu nào, dữ liệu đi theo chiều nào và điều gì xảy ra khi hai nơi khác nhau**. LDAP là thư mục entry theo DN, `objectClass` và schema; sự tiện lợi của ánh xạ Java không thay thế các quyết định về nguồn dữ liệu, quyền ghi, bảo mật và kiểm thử đồng bộ.
