# DN có multi-valued RDN khi rename và move trong Spring LDAP

Trong LDAP, mỗi entry được định vị bằng một **Distinguished Name (DN)**. DN được ghép từ các **Relative Distinguished Name (RDN)**, đi từ entry cụ thể đến các cấp cha. Phần lớn ví dụ nhập môn dùng RDN có một cặp thuộc tính–giá trị, như **uid=an**; tuy nhiên, LDAP cũng hỗ trợ **multi-valued RDN**: một RDN chứa **từ hai cặp thuộc tính–giá trị trở lên** cùng góp phần định danh entry.

Điều này ảnh hưởng trực tiếp đến thao tác **rename** (đổi RDN) và **move** (đổi entry cha) trong Spring LDAP. Nếu phân tích nhầm dấu **+** thành dấu **,**, ứng dụng có thể trỏ đến một DN hoàn toàn khác; nếu chỉ sửa một thuộc tính nhưng quên phần còn lại của RDN, thao tác đổi tên có thể thất bại hoặc thay đổi định danh ngoài ý muốn.

Bài này thuộc chương **Rename và move** của module **SPRING_LDAP**. Ta sẽ sử dụng quy tắc DN của LDAP, thư viện **javax.naming.ldap.LdapName/Rdn** của JNDI và thao tác **LdapTemplate.rename(...)** trong Spring LDAP để tạo, đọc, đổi tên và di chuyển entry có RDN nhiều giá trị một cách có kiểm soát.

## 1. Đọc cấu trúc DN: dấu phẩy khác dấu cộng

Xét DN:

~~~text
cn=An Nguyen+uid=an,ou=people,dc=example,dc=org
~~~

DN trên có **bốn RDN**, không phải năm:

| Vị trí | RDN | Số cặp thuộc tính–giá trị (AVA) |
| --- | --- | --- |
| Entry đích | **cn=An Nguyen+uid=an** | 2: **cn=An Nguyen**, **uid=an** |
| Entry cha | **ou=people** | 1 |
| Cấp domain | **dc=example** | 1 |
| Cấp domain | **dc=org** | 1 |

**AVA (Attribute Value Assertion)** ở đây là một cặp tên thuộc tính và giá trị trong RDN. Dấu **+** ngăn cách các AVA **trong cùng một RDN**; dấu **,** ngăn cách **các RDN khác nhau**.

~~~text
DN
├─ RDN 1: cn=An Nguyen + uid=an       (multi-valued RDN)
├─ RDN 2: ou=people                   (single-valued RDN)
├─ RDN 3: dc=example
└─ RDN 4: dc=org
~~~

**cn=An Nguyen+uid=an** và **uid=an+cn=An Nguyen** biểu diễn cùng tập AVA trong một RDN. Theo quy tắc của multi-valued RDN, **thứ tự các AVA không tạo ra hai RDN khác nhau**. Ngược lại:

~~~text
cn=An Nguyen+uid=an,ou=people,dc=example,dc=org
uid=an,cn=An Nguyen,ou=people,dc=example,dc=org
~~~

là **hai DN có cấu trúc khác nhau**: dòng đầu có một RDN hai AVA tại vị trí lá; dòng sau có **hai RDN một AVA** liên tiếp. Vì vậy không được dùng dấu phẩy thay cho dấu cộng để “tách cho dễ đọc”.

> Multi-valued RDN **không đồng nghĩa** với thuộc tính nhiều giá trị. Một RDN có thể kết hợp **cn** và **uid** dù mỗi thuộc tính trong entry chỉ có một giá trị. Ngược lại, thuộc tính **memberOf** có thể mang nhiều giá trị nhưng không nhất thiết xuất hiện trong RDN.

## 2. Giá trị có dấu cộng không tự động tạo multi-valued RDN

Khi một tên hiển thị thực sự chứa ký tự **+**, ký tự đó là **dữ liệu** và phải được escape trong chuỗi DN theo quy tắc RFC 4514.

| Chuỗi DN | Ý nghĩa |
| --- | --- |
| <code>cn=An+uid=an,ou=people</code> | Lá có **2 AVA**: cn=An và uid=an. |
| <code>cn=An\+Binh,ou=people</code> | Lá có **1 AVA**: cn có giá trị **An+Binh**. |
| <code>cn=An\+Binh+uid=an,ou=people</code> | Lá có **2 AVA**; giá trị **cn** chứa dấu cộng thật. |
| <code>cn=An\, Binh+uid=an,ou=people</code> | Lá có **2 AVA**; giá trị **cn** chứa dấu phẩy thật. |

Ngoài dấu cộng và dấu phẩy, cú pháp DN còn có các quy tắc escape khác cho dấu bằng, dấu gạch chéo ngược, dấu nháy kép, khoảng trắng đầu/cuối và một số ký tự đặc biệt. **Không tự viết hàm thay chuỗi** kiểu <code>replace("+", "\+")</code>: dấu cộng có thể là dấu phân cách hợp lệ hoặc là dữ liệu, và các ký tự khác vẫn cần xử lý.

Cách an toàn là xây RDN từ giá trị thô bằng **Rdn**, để thư viện tạo chuỗi DN đúng cú pháp. Cũng không nên so sánh hai DN bằng chuỗi nguyên văn vì thứ tự AVA và cách biểu diễn escape có thể khác dù cấu trúc tương đương.

## 3. Dùng JNDI để phân tích multi-valued RDN

**LdapName** biểu diễn DN dưới dạng chuỗi RDN có cấu trúc; **Rdn** biểu diễn một RDN, gồm một hoặc nhiều AVA. Ví dụ:

~~~java
import javax.naming.directory.Attributes;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName dn = new LdapName(
        "cn=An Nguyen+uid=an,ou=people,dc=example,dc=org");

System.out.println(dn.size());              // 4 RDN

// Chỉ số LdapName bắt đầu từ RDN ít cụ thể nhất (bên phải).
Rdn leaf = dn.getRdn(dn.size() - 1);
System.out.println(leaf.size());             // 2 AVA

Attributes namingAttrs = leaf.toAttributes();
System.out.println(namingAttrs.get("cn").get());  // An Nguyen
System.out.println(namingAttrs.get("uid").get()); // an

LdapName equivalent = new LdapName(
        "uid=an+cn=An Nguyen,ou=people,dc=example,dc=org");
System.out.println(dn.equals(equivalent));   // true
~~~

**Lưu ý API:** Trong JNDI, phương thức lấy **tất cả AVA** từ **Rdn** là **toAttributes()**. **Rdn.getType()** và **Rdn.getValue()** phù hợp hơn với RDN một AVA; với RDN nhiều AVA, chúng không đại diện cho toàn bộ RDN. Luôn đọc **toAttributes()** nếu cần kiểm tra mọi thành phần.

So sánh bằng **LdapName.equals(...)** xử lý sự khác biệt trong cách biểu diễn DN tốt hơn so sánh chuỗi. Tuy nhiên, không được coi thuật toán so sánh phía Java là thay thế hoàn toàn các **matching rule** và quy tắc chuẩn hóa danh tính của LDAP server. Khi thiết kế logic phân quyền, cần kiểm tra danh tính entry thực tế và quan hệ với base DN, thay vì chỉ dựa trên một chuỗi được client cung cấp.

### Tạo multi-valued RDN đúng cách

Với **Rdn(Attributes)**, ta có thể tạo một RDN gồm hai AVA mà không cần ghép dấu cộng:

~~~java
import javax.naming.directory.BasicAttributes;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

String uid = "an";
String cn = "An + Binh, Kỹ thuật";

BasicAttributes naming = new BasicAttributes(true);
naming.put("uid", uid);
naming.put("cn", cn);

Rdn leaf = new Rdn(naming); // Một RDN chứa cả uid và cn.
LdapName dn = new LdapName("ou=people,dc=example,dc=org");
dn.add(leaf);               // Thêm RDN tại vị trí lá.

System.out.println(dn);
// Giá trị cn chứa '+' và ',' sẽ được escape khi biểu diễn DN.
// Không phụ thuộc vào thứ tự hiển thị của uid và cn.
~~~

Phân biệt rõ với:

~~~java
// LƯU Ý: Đây là HAI RDN một AVA, không phải một multi-valued RDN.
// Phương thức add(...) của LdapNameBuilder thêm từng cấp RDN.
// LdapNameBuilder.newInstance()
//     .add("ou", "people")
//     .add("cn", cn)
//     .add("uid", uid)
//     .build();
~~~

Khi cần một RDN có nhiều AVA, phải chủ động dựng **một Rdn** rồi đưa nó vào vị trí lá. Trong Spring LDAP, DN truyền cho **LdapTemplate** thường là **DN tương đối với base** đã cấu hình trong **ContextSource**; tránh ghép lặp **dc=example,dc=org** nếu ContextSource đã dùng base đó.

## 4. Rename và move tác động lên RDN nào?

LDAP hỗ trợ thao tác đổi DN thông qua **Modify DN** (thường gọi ModDN/ModifyRDN). Về mặt ý nghĩa:

- **Rename:** thay **RDN lá** trong khi giữ nguyên parent DN.
- **Move:** thay **parent DN** của entry, có thể giữ nguyên RDN lá.
- **Rename + move:** đổi cả RDN lá và parent DN trong một yêu cầu khi LDAP server hỗ trợ trường hợp đó.

Ví dụ với một entry có multi-valued RDN:

| Tình huống | DN cũ (tương đối với base) | DN mới |
| --- | --- | --- |
| Đổi giá trị cn | <code>cn=An Nguyen+uid=an,ou=people</code> | <code>cn=An N.+uid=an,ou=people</code> |
| Chuyển sang OU khác | <code>cn=An Nguyen+uid=an,ou=people</code> | <code>cn=An Nguyen+uid=an,ou=alumni</code> |
| Đổi cn và chuyển OU | <code>cn=An Nguyen+uid=an,ou=people</code> | <code>cn=An N.+uid=an,ou=alumni</code> |

Ở dòng thứ nhất, **uid=an** vẫn là một phần của RDN mới. Nếu chỉ gửi RDN mới là **cn=An N.**, bạn đã yêu cầu thay RDN kép bằng RDN đơn; đây là thay đổi định danh, không đơn thuần là sửa mỗi giá trị cn.

~~~mermaid
flowchart TB
    root["dc=example,dc=org"]
    people["ou=people"]
    alumni["ou=alumni"]
    old["cn=An Nguyen+uid=an"]
    moved["cn=An Nguyen+uid=an"]
    root --> people
    root --> alumni
    people --> old
    alumni --> moved
    old -.->|"Move: giữ cả hai AVA của RDN"| moved
~~~

**Điều kiện đi kèm:** entry đích mới chưa tồn tại, entry cha mới đã tồn tại, schema chấp nhận RDN mới, tài khoản LDAP có quyền đổi tên/di chuyển và server cho phép thao tác trong phạm vi liên quan. Move qua ranh giới partition/naming context hoặc nhiều directory server có thể bị từ chối; **LdapTemplate.rename(...)** không tự sao chép rồi xóa thay cho LDAP server.

## 5. Ví dụ Spring LDAP: đổi tên và chuyển OU

Giả định ứng dụng có bean **LdapTemplate**, cấu hình **ContextSource** base DN là **dc=example,dc=org**. Các OU **ou=people** và **ou=alumni** đều tồn tại, và entry dùng **cn**, **uid** làm RDN theo schema hiện hành.

~~~java
import javax.naming.Name;
import javax.naming.InvalidNameException;
import javax.naming.directory.BasicAttributes;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class PersonDnService {
    private final LdapTemplate ldapTemplate;

    public PersonDnService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // Tạo DN TƯƠNG ĐỐI với base của ContextSource.
    private static Name personDn(String ou, String uid, String cn)
            throws InvalidNameException {
        // OU chỉ nhận từ tập giá trị nghiệp vụ cho phép.
        if (!"people".equals(ou) && !"alumni".equals(ou)) {
            throw new IllegalArgumentException("OU không được phép");
        }
        if (uid == null || !uid.matches("[a-z0-9._-]{1,64}")
                || cn == null || cn.isBlank()) {
            throw new IllegalArgumentException("uid/cn không hợp lệ");
        }

        BasicAttributes naming = new BasicAttributes(true);
        naming.put("cn", cn);
        naming.put("uid", uid);

        LdapName dn = new LdapName("ou=" + ou);
        dn.add(new Rdn(naming));
        return dn;
    }

    public void renameDisplayName(
            String uid, String currentCn, String newCn)
            throws InvalidNameException {
        Name oldDn = personDn("people", uid, currentCn);
        Name newDn = personDn("people", uid, newCn);
        ldapTemplate.rename(oldDn, newDn);
    }

    public void moveToAlumni(String uid, String cn)
            throws InvalidNameException {
        Name oldDn = personDn("people", uid, cn);
        Name newDn = personDn("alumni", uid, cn);
        ldapTemplate.rename(oldDn, newDn);
    }
}
~~~

Ở ví dụ trên:

1. **personDn(...)** xây đúng một **Rdn** chứa cả **cn** và **uid**; **uid** được chuẩn hóa theo quy tắc minh họa, còn **cn** có thể chứa dấu phẩy hoặc dấu cộng mà không cần nối chuỗi thủ công.
2. **renameDisplayName(...)** chỉ thay AVA **cn** trong RDN lá, vẫn giữ AVA **uid**, cùng parent **ou=people**.
3. **moveToAlumni(...)** giữ nguyên RDN lá và đổi parent từ **ou=people** sang **ou=alumni**.
4. **ldapTemplate.rename(oldDn, newDn)** thực hiện yêu cầu đổi DN qua kết nối LDAP. Đây **không** phải lệnh cập nhật thuộc tính tùy ý; nếu cần sửa các thuộc tính khác, phải lập kế hoạch cho thao tác đó riêng.

**Giới hạn của ví dụ:** Chữ ký nhận **currentCn** từ client để dựng DN đích cũ. Trong ứng dụng thực tế, nên **lookup bằng ID bền vững** hoặc lấy DN hiện tại từ directory, xác minh đúng entry và quyền truy cập rồi mới đổi DN. Việc tìm DN hiện tại và rename là hai thao tác có thể bị xen giữa bởi thay đổi khác; nếu cần bảo vệ trước ghi đồng thời, dùng chiến lược concurrency phù hợp với server và các request control được hỗ trợ.

## 6. Rename tác động đến các thuộc tính trong entry ra sao?

LDAP yêu cầu các giá trị góp phần tạo nên RDN phải phù hợp với thuộc tính của entry. Khi đổi RDN, server có thể phải **bổ sung giá trị từ RDN mới** và **giữ hoặc loại giá trị của RDN cũ** theo tham số **deleteOldRDN** của thao tác Modify DN.

Ví dụ đổi:

~~~text
RDN cũ: cn=An Nguyen+uid=an
RDN mới: cn=An N.+uid=an
~~~

| Thiết lập deleteOldRDN | Ý nghĩa đối với AVA cũ |
| --- | --- |
| **true** | Server được yêu cầu xóa giá trị RDN cũ không còn dùng trong RDN mới, theo quy tắc LDAP; ví dụ **cn=An Nguyen** có thể bị loại khỏi **cn**. **uid=an** vẫn là thành phần của RDN mới. |
| **false** | Giữ lại các giá trị RDN cũ khi có thể; ví dụ **cn** có thể chứa cả **An Nguyen** và **An N.** nếu schema cho phép nhiều giá trị. |

Quy tắc này **không đồng nghĩa** với việc toàn bộ thuộc tính **cn** bị xóa rồi tạo lại. Server áp dụng các giới hạn schema (ví dụ thuộc tính đơn trị/đa trị và thuộc tính bắt buộc). Nếu **cn** là thuộc tính bắt buộc, việc xóa giá trị cũ vẫn phải để lại giá trị hợp lệ theo schema. Đừng suy đoán kết quả của rename nếu entry có nhiều giá trị cho cùng một thuộc tính.

Trong JNDI LDAP provider, cách xử lý **deleteOldRDN** có liên quan đến thuộc tính môi trường **java.naming.ldap.deleteRDN**; giá trị mặc định thường là **true**. **LdapTemplate.rename(...)** không phơi ra tham số **deleteOldRDN** trực tiếp, nên ứng dụng cần kiểm tra cấu hình **ContextSource/provider**, khả năng của server và kết quả thực tế trong môi trường triển khai. Không thay đổi thuộc tính môi trường của kết nối dùng chung giữa các request nếu điều đó có thể tạo hành vi khó đoán.

Sau rename/move, nên **đọc lại entry tại DN mới** và xác nhận:

- DN cũ không còn trỏ đến entry đó, DN mới trỏ đúng entry cần thao tác.
- Các AVA trong RDN mới có giá trị tương ứng ở entry.
- Các thuộc tính ngoài RDN vẫn giữ nguyên theo kỳ vọng.
- Thuộc tính dùng trong RDN cũ được giữ/xóa theo chính sách đã cấu hình.

Nếu nghiệp vụ chỉ muốn sửa **cn** mà **không muốn đổi DN**, hãy cân nhắc thiết kế entry có RDN ổn định như **uid=an** ngay từ đầu, rồi cập nhật **cn** bằng **modifyAttributes(...)**. Với entry đang có multi-valued RDN chứa **cn**, chỉ thay thuộc tính **cn** mà bỏ qua RDN có thể gây lỗi schema hoặc khiến DN và dữ liệu không còn nhất quán.

## 7. Những rủi ro riêng của multi-valued RDN

### Danh tính và tham chiếu sau đổi DN

Một số hệ thống lưu DN dưới dạng tham chiếu, chẳng hạn thuộc tính nhóm **member**, các rule phân quyền hoặc bản ghi ở ứng dụng ngoài LDAP. Sau rename/move, DN cũ có thể không còn truy xuất được, trong khi các tham chiếu đó chưa chắc tự cập nhật. Một số directory server hỗ trợ cơ chế duy trì tham chiếu, nhưng **không nên mặc định** mọi server hoặc ứng dụng tích hợp đều làm như vậy.

Nếu có thể, lưu **ID bất biến** tách khỏi DN cho nghiệp vụ dài hạn; kiểm tra lại nhóm, liên kết hệ thống và cache sau khi đổi DN. Trong phạm vi LDAP directory, **entryUUID** hoặc thuộc tính định danh nội bộ tương đương có thể hữu ích nếu server hỗ trợ và giá trị được duy trì ổn định trong kiểu move đang dùng.

### Cạnh tranh ghi và lỗi kết quả không chắc chắn

Hai client có thể cùng đổi RDN lá sang các giá trị khác nhau. Nếu client thứ nhất thành công, client thứ hai có thể không tìm thấy **oldDn** ban đầu, hoặc đụng một entry đang tồn tại ở **newDn**. Mã lỗi không tự cho biết thao tác nào trong các request trước đã thành công khi client gặp timeout.

Một chính sách thực hành:

1. Kiểm tra người gọi có quyền đổi DN và vùng OU đích nằm trong phạm vi cho phép.
2. Đọc DN và **ID bất biến** hiện tại; kiểm tra thuộc tính RDN, schema, parent mới và quy tắc nghiệp vụ.
3. Nếu cần kiểm tra trạng thái đúng **tại thời điểm ghi**, dùng cơ chế concurrency được LDAP server hỗ trợ; một lần **lookup** trước **rename** không bảo đảm nguyên tử cho toàn bộ chuỗi.
4. Gửi **ldapTemplate.rename(...)** và xử lý lỗi theo loại.
5. Nếu mất phản hồi, **không tự động tạo entry mới**: tìm/đối soát bằng ID bất biến ở DN cũ và DN mới, xác minh kết quả rồi mới retry.

| Tình huống | Hành động phù hợp |
| --- | --- |
| **noSuchObject (32)** | Kiểm tra entry nguồn và parent đích; xác định xem có ai đã move trước đó. |
| **entryAlreadyExists (68)** | Kiểm tra DN đích, không ghi đè hoặc xóa entry đích để “nhường chỗ”. |
| **namingViolation (64)** hoặc **objectClassViolation (65)** | Rà schema, RDN mới, attributes bắt buộc và quy tắc đặt tên của server. |
| **insufficientAccessRights (50)** | Kiểm tra quyền rename/move của tài khoản LDAP và quyền nghiệp vụ. |
| **affectsMultipleDSAs (71)** hoặc hạn chế phân vùng | Xem xét ranh giới naming context/server và khả năng hỗ trợ move. |
| Timeout/mất kết nối | Ghi nhận **UNKNOWN**, đối soát trước khi retry với các định danh nhất quán. |

Với entry có entry con, một số directory có thể cho phép đổi DN cho cả nhánh, trong khi server/điều kiện khác có thể từ chối. Cần kiểm tra hạn chế cụ thể, kích thước cây, ACL và tác động lên các DN con trước khi di chuyển OU hay entry dạng container. Không suy luận một lệnh **rename** luôn xử lý thành công cả cây.

### Bảo mật khi thao tác với DN

Sử dụng **LDAPS hoặc StartTLS** nếu môi trường yêu cầu bảo vệ kênh; dùng quyền tối thiểu tại nhánh nguồn và nhánh đích. Không ghép giá trị do client truyền trực tiếp thành DN hay LDAP filter. **Rdn** giúp encode giá trị cho cú pháp DN, nhưng **không thay thế** bước kiểm tra quyền, giới hạn OU hoặc escaping khi cùng dữ liệu được đưa sang **LDAP filter** (filter có quy tắc escape khác với DN).

## 8. Bài kiểm thử cần có

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Phân tích **cn=An Nguyen+uid=an,ou=people** | RDN lá có đúng **2 AVA**, không bị tách thành hai cấp. |
| Đảo thứ tự AVA trong cùng RDN | **LdapName.equals(...)** nhận diện DN tương đương theo cú pháp JNDI. |
| Giá trị **cn** chứa dấu **+**, **,** | Dựng DN bằng **Rdn** và đọc lại được đúng giá trị gốc. |
| Dùng nhiều lần **LdapNameBuilder.add(...)** | Nhận ra đây là các RDN riêng, không nhầm thành multi-valued RDN. |
| Rename từ **cn=A+uid=u** sang **cn=B+uid=u** | Đổi thành công, **uid=u** còn trong RDN lá. |
| Move cùng RDN từ **ou=people** sang **ou=alumni** | Entry ở DN mới, cùng định danh nghiệp vụ, không có bản sao ngoài ý muốn. |
| Kiểm tra **deleteOldRDN** | Các giá trị naming attribute giữ/xóa đúng chính sách và schema. |
| DN đích đã tồn tại hoặc OU đích không có | Nhận lỗi phù hợp, dữ liệu không bị ghi đè. |
| Không đủ quyền hoặc move qua ranh giới bị hạn chế | Thao tác bị từ chối, ứng dụng báo đúng nguyên nhân. |
| Mất kết nối sau khi server đã rename | Đối soát bằng ID bất biến xác định được trạng thái cuối trước khi retry. |
| Entry có DN được hệ thống khác tham chiếu | Phát hiện và xử lý các tham chiếu ảnh hưởng sau rename/move. |

Nên kiểm thử các trường hợp này trên LDAP test server có schema, ACL và khả năng **Modify DN** gần môi trường sử dụng thật. Unit test cho **Rdn/LdapName** xác minh cú pháp và cấu trúc DN; integration test với server mới xác minh được quyền truy cập, quy tắc **deleteOldRDN**, lỗi khi move và việc duy trì các giá trị thuộc tính.

## Ghi nhớ

**Multi-valued RDN** là **một RDN chứa nhiều AVA**, nối nhau bằng dấu **+**; nó khác hoàn toàn với nhiều RDN nối bằng dấu phẩy. Khi đổi tên hoặc di chuyển entry trong Spring LDAP, cần dựng và so sánh DN bằng **LdapName/Rdn**, giữ lại các AVA phải có trong RDN mới, hiểu chính sách **deleteOldRDN**, xác minh schema và quyền của LDAP server, và kiểm tra các tham chiếu sau thao tác. Một thay đổi của **cn** chỉ là update thuộc tính nếu **cn** không góp phần vào DN; khi **cn** là thành phần của RDN, cần thiết kế rename hoặc điều chỉnh mô hình đặt tên để tránh thay đổi danh tính ngoài ý muốn.
