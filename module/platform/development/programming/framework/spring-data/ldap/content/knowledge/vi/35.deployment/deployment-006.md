# Thay đổi schema hoặc cấu trúc DN khi nhiều phiên bản ứng dụng cùng chạy

> **Chương:** Triển khai  
> **Module:** `SPRING_DATA_LDAP` — truy cập directory LDAP thông qua Spring Data LDAP, ánh xạ entry phân cấp sang Java entity, sử dụng `LdapRepository`/`LdapTemplate` để truy vấn và CRUD.

Trong hệ thống triển khai theo kiểu **rolling update**, canary hoặc blue–green, nhiều phiên bản ứng dụng có thể cùng kết nối đến một LDAP directory trong một khoảng thời gian. Khi đó, thay đổi schema hoặc di chuyển entry sang DN mới không còn là việc sửa một annotation Java hay đổi một giá trị cấu hình: một phiên bản cũ có thể vẫn tìm kiếm ở nhánh cũ, ghi các thuộc tính theo mô hình cũ hoặc giả định một `objectClass` nhất định.

Ví dụ ứng dụng nhân sự đang lưu nhân viên trực tiếp dưới:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Phiên bản mới muốn phân loại nhân viên vào OU chuyên biệt:

~~~text
uid=lan,ou=employees,ou=people,dc=example,dc=org
~~~

Nếu lập tức `rename` entry sang DN mới, những instance chưa được nâng cấp và vẫn dùng `userDnPatterns("uid={0},ou=people")` hoặc `lookup("uid=lan,ou=people")` có thể không tìm thấy tài khoản. Nếu cùng lúc thay đổi schema, code cũ còn có thể thất bại khi đọc, sửa hoặc ghi lại những thuộc tính mới.

Bài học này trình bày một cách triển khai có kiểm soát: **mở rộng tương thích → hỗ trợ hai dạng dữ liệu → di chuyển có kiểm chứng → chuyển luồng ghi/đọc → thu hẹp mô hình cũ** (*expand–migrate–contract*). Đây là một mẫu thiết kế, không phải khả năng giao dịch đa entry do LDAP tự cung cấp.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **thay đổi schema**, **thay đổi DN/RDN**, **di chuyển nhánh** và **đổi structural object class**.
2. Phân tích tương thích giữa phiên bản V1/V2 đang cùng hoạt động trên một directory.
3. Thiết kế kế hoạch **expand–migrate–contract** cho thuộc tính mới và cấu trúc DN mới.
4. Viết lớp truy cập LDAP hỗ trợ giai đoạn chuyển tiếp mà không ghép filter/DN từ chuỗi không an toàn.
5. Dùng `LdapTemplate.rename(...)` đúng phạm vi, nhận diện rủi ro với nhóm, ACL, ứng dụng khác và replication.
6. Xử lý read fallback, chuyển nguồn ghi, kiểm tra xung đột, retry và rollback.
7. Lập ma trận kiểm thử chạy đồng thời nhiều phiên bản ứng dụng trên directory test.

## 2. Bối cảnh: một directory, nhiều phiên bản ứng dụng

Giả sử hệ thống có ba loại consumer:

- **Ứng dụng V1:** chỉ biết nhân viên tại `ou=people`, đọc thuộc tính `uid`, `cn`, `sn` và `mail`.
- **Ứng dụng V2:** hỗ trợ thuộc tính nghiệp vụ mới `employeeNumber` và có thể tìm cả cấu trúc DN cũ/lẫn mới.
- **Batch job:** truy vấn hoặc đồng bộ nhóm bằng `member`, có thể vẫn lưu DN cũ trong dữ liệu và cache.

Trong một lần rolling deployment, các instance có thể cùng tồn tại:

~~~mermaid
flowchart TD
    LB["Load balancer / job scheduler"]
    LB --> A["Ứng dụng V1<br/>chỉ biết DN cũ"]
    LB --> B["Ứng dụng V2<br/>đọc được hai cấu trúc"]
    A --> DIR["LDAP directory dùng chung"]
    B --> DIR
    JOB["Batch job / service khác"] --> DIR
    DIR --> OLD["ou=people"]
    DIR --> NEW["ou=employees,ou=people"]
~~~

**Tình huống gây lỗi:** một instance V2 di chuyển `uid=lan` sang `ou=employees` trong khi V1 vẫn xử lý request. V1 không có cơ chế tìm ở vị trí mới nên trả `noSuchObject` hoặc “không tồn tại”, mặc dù entry đã được di chuyển thành công.

**Tình huống khó phát hiện hơn:** V1 có chức năng `repository.save(entity)` ghi lại toàn bộ entity đã tải. Khi V2 thêm thuộc tính mới, cách V1 lưu một entity không hiểu thuộc tính ấy có thể làm rơi dữ liệu, tùy mapping và semantics của thư viện. Không giả định entity cũ tự bảo toàn những trường chưa được tải.

Ranh giới quan trọng nhất: **cùng một directory không có nghĩa các phiên bản ứng dụng có cùng cách hiểu dữ liệu**.

## 3. Bốn loại thay đổi thường bị nhầm với nhau

| Loại thay đổi | Ví dụ | Ảnh hưởng chính | Mức độ cần kiểm soát |
|---|---|---|---|
| **Thêm thuộc tính tương thích** | Dùng `employeeNumber` vốn được schema cho phép | Code cũ phải chấp nhận entry có trường mới | Thường có thể triển khai dần nếu không làm mất dữ liệu |
| **Thêm object class phụ trợ** | Gắn AUXILIARY class đã đăng ký để chứa trường mở rộng | Client đọc/ghi `objectClass`, schema/DIT content rules | Cần xác nhận lớp được phép và code cũ bảo toàn |
| **Đổi vị trí DN** | `uid=lan,ou=people` → `uid=lan,ou=employees,ou=people` | Lookup, search base, group membership, DN cache, ACL | Rủi ro cao khi V1 vẫn dùng DN cũ |
| **Đổi structural class** | Chuyển mô hình từ `person` sang lớp structural khác | Quy tắc schema và identity của entry | Thường phải thiết kế migration riêng, không xem là Modify thông thường |

**Đặc biệt:** một LDAP entry thông thường có **structural object class** xác định khi tạo; không thể tùy tiện đổi structural class bằng một lệnh Modify như sửa `mail`. Nhiều server còn công bố `structuralObjectClass` dưới dạng operational attribute được server quản lý.

Nếu yêu cầu đổi hẳn chuỗi structural class, cần khảo sát cách migration được server hỗ trợ và có thể phải tạo entry khác, chuyển dữ liệu/quan hệ rồi thay thế có kiểm soát. **Đổi DN bằng `ModifyDN` không tự biến structural class thành lớp khác.**

## 4. Phân loại thay đổi theo khả năng tương thích

Không phải mọi thay đổi “thêm” đều an toàn với phiên bản cũ:

| Thay đổi | Khi nào tương thích ngược? | Trường hợp phải thận trọng |
|---|---|---|
| Thêm một attribute tùy chọn đã được schema cho phép | V1 bỏ qua thuộc tính không sử dụng và không xóa nó khi ghi | V1 map/serialize objectClass hoặc whole-entry save theo chính sách không tương thích |
| Đăng ký attribute type mới | Chỉ thêm định nghĩa schema; V1 không phụ thuộc tên đó | Dùng OID sai hoặc thay đổi definition cũ đang được dùng |
| Thêm auxiliary class vào entry | V1 có thể đọc và bảo toàn `objectClass` mới | V1 kiểm tra danh sách class cứng hoặc ghi đè `objectClass` |
| Bắt đầu ghi thuộc tính mới | V1 đọc vẫn ổn, không làm mất giá trị và không hiểu sai nó | V1 ghi đè entry làm mất trường mới |
| Bắt buộc thuộc tính mới cho mọi entry | Tất cả producer, consumer và dữ liệu đã tương thích | V1 còn tạo entry thiếu MUST mới |
| Di chuyển entry sang OU mới | Không còn V1 đọc DN cũ, hoặc có lớp tương thích đã được chứng minh | V1 dùng `lookup`/DN pattern cũ, nhóm tham chiếu DN cũ |
| Xóa thuộc tính/OU cũ | Mọi consumer đã ngừng sử dụng | Batch job hoặc phiên bản rollback còn phụ thuộc |
| Đổi RDN `uid` | Có cơ chế đổi identity, group refs, cache và định danh ngoài LDAP | Hệ thống khác lưu DN/username như khóa bất biến |

**Tương thích ngược** không chỉ nghĩa là “V2 đọc được dữ liệu V1”. Trong thời gian hai phiên bản cùng chạy, cần kiểm tra cả:

- V1 **đọc dữ liệu do V2 ghi** được không?
- V1 **ghi lên entry được V2 mở rộng** có an toàn không?
- V2 **đọc dữ liệu cũ** được không?
- V2 có còn hoạt động nếu **roll back** thành V1 không?
- Các consumer ngoài web service có dùng DN, thuộc tính hoặc group reference cũ không?

## 5. Chiến lược expand–migrate–contract

Một lộ trình giảm rủi ro được tách thành ba pha:

~~~mermaid
flowchart LR
    A["EXPAND<br/>schema tương thích<br/>V2 biết dữ liệu cũ + mới"]
    B["MIGRATE<br/>di chuyển có kiểm chứng<br/>theo lô / idempotent"]
    C["CONTRACT<br/>đóng cách cũ<br/>sau khi mọi consumer sẵn sàng"]
    A --> B --> C
~~~

### Pha EXPAND — chuẩn bị trước khi chuyển dữ liệu

- Đăng ký schema bổ sung, chỉ dùng thuộc tính/class có khả năng tương thích với entry cũ.
- Deploy code mới biết **đọc cả hai cấu trúc**, nhưng vẫn duy trì dữ liệu ở vị trí cũ nếu V1 còn cần.
- Nếu thêm field mới, trong giai đoạn chuyển tiếp field nên **optional** hoặc có mặc định được thỏa thuận; đừng lập tức yêu cầu V1 cung cấp.
- Viết và chạy integration test gồm cả V1 và V2; kiểm tra `save`/Modify không làm mất thuộc tính mới.
- Chuẩn bị OU mới, ACL, index, search base, group queries và kế hoạch backfill.

### Pha MIGRATE — chuyển dữ liệu có kiểm soát

- Chỉ di chuyển DN khi các consumer cần DN cũ đã được nâng cấp/loại khỏi traffic, hoặc đã có chiến lược tương thích hoạt động thật.
- Ghi migration marker ở hệ thống điều phối hoặc trong thuộc tính phù hợp đã được schema cho phép; có thể resume sau lỗi.
- Mỗi entry cần kiểm tra điều kiện trước khi di chuyển: nguồn tồn tại, đích chưa trùng, entry không bị thay đổi trái phép và các tham chiếu liên quan đã được xác định.
- Sau thao tác, đọc lại từ DN đích, xác minh thuộc tính, quyền và group membership.
- Tiến hành theo lô có giới hạn, theo dõi lỗi và dừng khi vượt ngưỡng.

### Pha CONTRACT — ngừng hỗ trợ mô hình cũ

- Chỉ đóng đường đọc/ghi cũ khi mọi consumer được kiểm kê đều hỗ trợ DN và schema mới.
- Loại bỏ search fallback, cấu hình DN cũ và quyền không còn cần thiết theo lộ trình.
- Xem xét việc xóa thuộc tính cũ hoặc schema cũ **riêng biệt**; xóa định nghĩa schema thường khó rollback hơn xóa config.
- Đảm bảo không còn deployment rollback dự kiến yêu cầu dữ liệu theo mô hình cũ.

**Không gộp ba pha thành một thay đổi duy nhất** nếu có khả năng hai phiên bản cùng hoạt động.

## 6. Ví dụ schema: mở rộng từ từ, không đổi MUST đột ngột

Giả sử V1 dùng entry `inetOrgPerson`:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Tran Thi Lan
sn: Tran
mail: lan@example.org
~~~

V2 muốn dùng thêm `employeeNumber`. Trong schema tiêu chuẩn của `inetOrgPerson`, `employeeNumber` là thuộc tính được phép (MAY), không phải một giá trị mặc nhiên bắt buộc. Có thể cập nhật dữ liệu dần:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
changetype: modify
add: employeeNumber
employeeNumber: E-1024
~~~

Lệnh LDIF trên là một **thao tác Modify**, không phải một entry đầy đủ. Trên directory test cần bind account có quyền sửa `employeeNumber`; đồng thời phải kiểm tra không có giá trị trùng hoặc chính sách xác định duy nhất khác.

Tại thời điểm chuyển tiếp:

| Phiên bản | Entry chưa có employeeNumber | Entry đã có employeeNumber |
|---|---|---|
| V1 | Xử lý như trước | Phải đọc được và không làm mất thuộc tính mới |
| V2 | Chấp nhận null/missing hoặc fallback rõ ràng | Sử dụng giá trị nếu hợp lệ |

Không biến thuộc tính optional thành **required trong logic V2** trước khi backfill và hoàn thành migration. Nếu một API V2 yêu cầu bắt buộc có `employeeNumber`, cần tách yêu cầu đó khỏi nghiệp vụ V1 hoặc có cơ chế sinh/gán giá trị đúng và xử lý entry chưa di chuyển.

### Thêm auxiliary class

Nếu cần thuộc tính không có trong schema chuẩn, có thể định nghĩa attribute type và AUXILIARY object class của tổ chức rồi áp dụng cho entry khi directory cho phép. Khi đó phải kiểm tra:

1. OID thuộc quyền sở hữu của tổ chức và schema đã được triển khai trên **mọi node cần xử lý ghi/tìm**.
2. Auxiliary class hợp lệ với structural class theo schema/DIT content rule.
3. Mọi thuộc tính MUST của auxiliary class được đáp ứng.
4. V1 có xử lý được entry chứa class bổ sung, đặc biệt khi V1 có logic cập nhật `objectClass`.
5. Không vô tình mở rộng ACL hoặc tạo quyền ghi không mong muốn.

**Đừng sửa định nghĩa hiện có tại chỗ rồi mặc định mọi client đều tương thích.** Thay syntax hoặc matching rule của một attribute type đang được sử dụng có thể làm giá trị cũ không hợp lệ hoặc thay đổi kết quả filter. Thường an toàn hơn khi khai báo type/class mới có kế hoạch chuyển dữ liệu rõ ràng.

## 7. Vấn đề DN: tên, vị trí và tham chiếu

Một DN vừa xác định **tên và vị trí** của entry trong Directory Information Tree (DIT). Ví dụ:

~~~text
Cũ: uid=lan,ou=people,dc=example,dc=org
Mới: uid=lan,ou=employees,ou=people,dc=example,dc=org
~~~

Khi đổi vị trí:

- `lookup(...)` theo DN cũ sẽ không tự tìm thấy entry mới.
- Search base `ou=people` với `ONELEVEL` sẽ không bao phủ `ou=employees,ou=people`.
- Search base `ou=people` với `SUBTREE` **có thể** bao phủ OU con, nhưng còn phụ thuộc filter, quyền, alias/referral và cấu hình cụ thể.
- `@Entry(base = "...")` của Spring Data LDAP và các `userDnPatterns` trong Spring Security LDAP có thể đang chỉ đúng nhánh cũ.
- Các thuộc tính tham chiếu DN như `member` của `groupOfNames` có thể vẫn chứa DN cũ.
- Cache và hệ thống bên ngoài có thể sử dụng DN như khóa, nên bị ảnh hưởng dù entry vẫn tồn tại.

**DN không nên được xem là mã định danh nghiệp vụ bất biến.** Nếu có yêu cầu di chuyển DN, API nên sử dụng một mã ổn định không phụ thuộc OU, ví dụ mã nhân viên có chính sách duy nhất rõ ràng. `employeeNumber` không tự được LDAP bảo đảm duy nhất trên toàn directory; hệ thống phải thiết kế hoặc kiểm tra ràng buộc duy nhất phù hợp.

### Chuẩn bị OU đích

Parent `ou=employees,ou=people,dc=example,dc=org` phải tồn tại, được phép chứa loại entry đích theo quy tắc DIT và được cấp ACL đúng. Không coi việc tạo parent OU là việc mà `LdapTemplate.rename(...)` sẽ thực hiện thay ứng dụng.

Nếu OU mới thuộc naming context, partition hoặc directory server khác, thao tác `ModifyDN` có thể không được hỗ trợ xuyên ranh giới. Khi đó cần đánh giá quy trình copy/provision + cập nhật tham chiếu + ngừng bản cũ riêng, không giả định `rename(...)` hoạt động trên mọi topology.

## 8. Ma trận tương thích khi rolling deployment

Với chiến lược V1 chỉ biết DN cũ và V2 hỗ trợ DN cũ/mới:

| Giai đoạn | V1 còn chạy? | Dữ liệu nằm ở đâu? | V1 đọc được? | V2 đọc được? |
|---|---|---|---|---|
| Trước rollout | Có | OU cũ | Có | Chưa triển khai |
| Deploy V2 đọc hai nơi | Có | OU cũ | Có | Có |
| V2 đã triển khai hết, chưa di chuyển | Không | OU cũ | Không còn consumer V1 | Có |
| Di chuyển theo lô | Không | Một phần OU cũ, một phần OU mới | Không áp dụng | Có |
| Sau migration | Không | OU mới | Không áp dụng | Có |
| Contract | Không | OU mới | Không hỗ trợ | Có |

**Giai đoạn nguy hiểm:** V1 còn chạy mà một entry nó cần đã chuyển hẳn sang OU mới. Trừ khi có một cơ chế tương thích được triển khai, kiểm thử và được tất cả request V1 sử dụng, phải coi đây là **không tương thích**.

Một số tổ chức áp dụng dual-write để đồng thời duy trì hai entry. Cách này tạo hai DN và có nguy cơ hai bản dữ liệu khác nhau, trùng danh tính, xung đột cập nhật và không có transaction chuẩn xuyên hai entry. **Dual-write không nên là giải pháp mặc định** chỉ để V1 nhìn thấy DN cũ; nếu bắt buộc, phải có ownership, reconciliation và rollback rõ ràng.

## 9. Ứng dụng V2 đọc được hai cấu trúc DN như thế nào?

Đối với giai đoạn V2 đọc cả OU cũ và OU mới, có thể dùng một **compatibility adapter**. Ví dụ đơn giản dưới đây giả định UID không thay đổi trong quá trình di chuyển, và `spring.ldap.base=dc=example,dc=org`.

~~~java
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonLocationReader {

    private final LdapTemplate ldapTemplate;

    public PersonLocationReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public PersonInfo findByUid(String uid) {
        validateUid(uid);

        Name newDn = newDn(uid);
        try {
            return readEntry(newDn);
        } catch (NameNotFoundException notAtNewLocation) {
            // Chỉ fallback khi DN không tồn tại tại OU mới.
            // Lỗi kết nối, ACL hoặc schema không được che giấu.
            return readEntry(oldDn(uid));
        }
    }

    private PersonInfo readEntry(Name dn) {
        return ldapTemplate.lookup(
                dn,
                (AttributesMapper<PersonInfo>) attrs ->
                        new PersonInfo(
                                requiredText(attrs, "uid"),
                                requiredText(attrs, "cn"),
                                requiredText(attrs, "sn")));
    }

    private static String requiredText(
            Attributes attrs, String attribute)
            throws NamingException {

        Attribute value = attrs.get(attribute);
        if (value == null || value.size() != 1) {
            throw new IllegalStateException(
                    "Missing or ambiguous LDAP attribute: " + attribute);
        }
        Object raw = value.get();
        if (!(raw instanceof String text) || text.isBlank()) {
            throw new IllegalStateException(
                    "Invalid LDAP string for: " + attribute);
        }
        return text;
    }

    private static Name oldDn(String uid) {
        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }

    private static Name newDn(String uid) {
        return LdapNameBuilder
                .newInstance("ou=employees,ou=people")
                .add("uid", uid)
                .build();
    }

    private static void validateUid(String uid) {
        if (uid == null
                || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException(
                    "Invalid uid");
        }
    }

    public record PersonInfo(String uid, String cn, String sn) {
    }
}
~~~

Phân tích:

- `LdapNameBuilder` escape giá trị RDN đúng cú pháp; code không nhận DN từ client.
- `newDn(uid)` được thử trước, sau đó `oldDn(uid)` nếu nhận lỗi **NameNotFound**.
- Các lỗi bind, timeout, thiếu ACL hoặc sai schema không tự động chuyển thành fallback vì điều đó có thể che sự cố thực tế.
- Đọc entry chỉ lấy thuộc tính cần thiết; nếu một field cần có nhiều giá trị, thay hợp đồng DTO/mapping tương ứng.
- Nếu cả hai DN cùng tồn tại và chứa dữ liệu khác nhau, cách “ưu tiên mới” có thể che xung đột. Vì vậy cần **kiểm tra trùng danh tính ở migration**, không dựa riêng vào adapter này.
- Đoạn code là ví dụ đọc trong giai đoạn chuyển tiếp, **chưa có phương thức ghi**; không suy rằng chỉ cần có fallback là toàn bộ CRUD đã tương thích.

### Vì sao không chỉ mở rộng search base?

Nếu mã cũ dùng `ONELEVEL` dưới `ou=people`, thêm OU con không khiến kết quả tự mở rộng. Chuyển sang `SUBTREE` có thể đọc được cả hai nhánh nhưng cũng có thể đưa vào kết quả từ OU không liên quan và gây trùng `uid`.

Khi dùng `LdapQueryBuilder.query().base(...).searchScope(...)`, cần xem ranh giới tenant, ACL và tính duy nhất; đôi khi hai truy vấn có base cụ thể dễ kiểm soát hơn một truy vấn SUBTREE quá rộng.

## 10. Chuyển luồng ghi: phải có một nguồn sự thật

Đọc hai nơi chỉ giải quyết một phần vấn đề. Nếu V1 và V2 cùng ghi, cần quy định **vị trí ghi chuẩn** tại mỗi giai đoạn.

| Giai đoạn | Luồng đọc | Luồng ghi an toàn theo ví dụ |
|---|---|---|
| EXPAND: V1 và V2 cùng chạy | V1 đọc cũ; V2 đọc cả hai | **Cùng ghi entry ở DN cũ** |
| Sau khi V1 ngừng chạy | V2 đọc cả hai | Bắt đầu chuyển từng entry có kiểm soát |
| MIGRATE | V2 có khả năng đọc cũ/mới | Ghi vào vị trí thực tế của entry, dùng coordination/serialization để tránh đụng thao tác move |
| Sau khi hoàn tất | V2 đọc mới | Chỉ ghi DN mới |
| CONTRACT | V2/V3 đọc mới | Chỉ ghi mới, bỏ fallback cũ |

**Không dùng thuật toán “lookup ở DN mới, không thấy thì create ở DN mới”** khi entry vẫn tồn tại ở DN cũ. Nếu không có kiểm tra và khóa/coordinator thích hợp, hai request có thể tạo **hai entry cho cùng một người**, làm mất tính duy nhất ở mức nghiệp vụ.

### Dual-write có thể cần nhưng không tự an toàn

Nếu bắt buộc duy trì hai bản entry khác DN cho V1/V2:

1. Xác định bản nào là **source of truth**.
2. Áp dụng ID nghiệp vụ ổn định để liên kết hai entry.
3. Định nghĩa thứ tự ghi, cơ chế retry và reconciliation khi bước thứ hai thất bại.
4. Ngăn cấp hai tài khoản đăng nhập độc lập ngoài ý muốn.
5. Kiểm tra group membership, ACL và các tham chiếu DN ở cả hai bản.
6. Định nghĩa tiêu chí gỡ bản cũ và điều kiện rollback.

LDAP Modify trên **một entry** có ngữ nghĩa atomic ở cấp thao tác; **hai entry không nằm trong một transaction LDAP tiêu chuẩn**. Vì vậy dual-write cần công cụ điều phối và giám sát riêng.

## 11. Sử dụng LdapTemplate.rename cho di chuyển DN

Khi các ứng dụng còn phụ thuộc DN cũ đã được nâng cấp hoặc rút khỏi traffic, có thể chuyển một entry trong cùng phạm vi server hỗ trợ bằng `ModifyDN`. Spring LDAP cung cấp `LdapTemplate.rename(...)`.

Ví dụ:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonMover {

    private final LdapTemplate ldapTemplate;

    public PersonMover(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void moveToEmployeesOu(String uid) {
        if (uid == null ||
                !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid uid");
        }

        Name oldDn = LdapNameBuilder
                .newInstance("ou=people")
                .add("uid", uid)
                .build();

        Name newDn = LdapNameBuilder
                .newInstance("ou=employees,ou=people")
                .add("uid", uid)
                .build();

        ldapTemplate.rename(oldDn, newDn);
    }
}
~~~

Trong ví dụ, hai DN đều **tương đối với** `ContextSource` có base `dc=example,dc=org`. Nếu directory không hỗ trợ move tới parent khác trong điều kiện này, cần thiết kế giải pháp khác. Trước thao tác phải bảo đảm OU đích tồn tại, DN mới chưa trùng, bind account có quyền phù hợp và server cho phép thay đổi tên/vị trí.

**Quan trọng về tính đúng đắn:**

- `rename` đổi tên hoặc vị trí entry; nó **không tạo OU cha**, không tự cập nhật mọi DN tham chiếu trong `member`, không tự sửa cấu hình search của các client.
- Nếu chuyển sang naming context/server khác, LDAP ModifyDN có giới hạn và có thể không phù hợp.
- LDAP server có thể cấm rename vì ACL, DIT structure rule, entry con hoặc đặc điểm của directory.
- Trong một số môi trường, thao tác đổi RDN còn thay các giá trị RDN của entry theo `deleteOldRDN`; code dùng API đơn giản cần được kiểm thử đúng semantics của server nếu đổi cả RDN chứ không chỉ move.
- Không thực hiện move rồi giả định ứng dụng V1 vẫn truy cập được bằng DN cũ. **LDAP không có cơ chế chuyển hướng DN mặc định cho mọi server.**

### Có nên tạo LDAP alias tại DN cũ?

LDAP có kiểu entry alias và cơ chế dereference trong những server hỗ trợ, nhưng không được coi alias là giải pháp tương thích mặc định. Ứng dụng có thể đang dùng `lookup`, `search` với `derefAliases` khác nhau, hoặc thao tác Modify/Delete không có semantics như direct entry. Còn có ràng buộc object class, ACL và nguy cơ vòng alias.

Chỉ lựa chọn alias nếu đã kiểm tra cụ thể server, schema, toàn bộ thao tác V1 và các client liên quan. Với hệ thống đơn giản, **chờ V1 rút khỏi traffic trước khi move** là chiến lược an toàn hơn.

## 12. Tham chiếu DN trong group, ACL và các hệ thống phụ thuộc

Nếu nhóm đang lưu DN người dùng:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
~~~

sau khi chuyển Lan sang OU mới, thuộc tính `member` có thể vẫn chỉ tới DN cũ. Một số directory có plugin **referential integrity** giúp cập nhật tham chiếu khi đổi DN; phải xác nhận plugin thực sự bật, phạm vi áp dụng và độ trễ. Không mặc định server nào cũng cập nhật `member`.

### Thay đúng một giá trị member

Nếu cần cập nhật thủ công theo chính sách và ACL, có thể dùng **một LDAP Modify operation** chứa hai thay đổi trên cùng group entry:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

Name groupDn = LdapNameBuilder
        .newInstance("ou=groups")
        .add("cn", "developers")
        .build();

String oldMemberDn = "uid=lan,ou=people,dc=example,dc=org";
String newMemberDn =
        "uid=lan,ou=employees,ou=people,dc=example,dc=org";

ModificationItem[] changes = {
    new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("member", newMemberDn)),
    new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("member", oldMemberDn))
};

ldapTemplate.modifyAttributes(groupDn, changes);
~~~

Đoạn này là **minh họa** đặt trong service đã có `ldapTemplate` và import `LdapNameBuilder`. Nó giả định group `developers` tồn tại, có giá trị `oldMemberDn`, chưa có giá trị `newMemberDn` và schema/ACL cho phép.

**Không dùng mẫu này mù quáng:** nếu đã có new DN trong member hoặc old DN đã được plugin tự thay, Add hoặc Remove có thể trả `attributeOrValueExists (20)` hoặc `noSuchAttribute (16)`. Cần viết logic **idempotent** dựa trên trạng thái hiện tại và kiểm tra server, hoặc dùng cơ chế cập nhật tham chiếu đã được hỗ trợ. Một thao tác Modify trên group và một thao tác rename trên person **không tạo thành transaction chung**.

Ngoài `member`, cần kiểm kê `uniqueMember`, DN trong dữ liệu phân quyền, ACL dựa trên subtree, thuộc tính tham chiếu riêng, LDAP authentication search, cache, LDAP group mapping và các hệ thống downstream. **Group membership không chỉ là dữ liệu phụ**: một DN sai có thể làm người dùng đăng nhập thành công nhưng không còn quyền ứng dụng.

## 13. Spring Security LDAP khi đổi search base hoặc DN pattern

Một cấu hình xác thực LDAP có thể sử dụng DN pattern:

~~~java
factory.setUserDnPatterns("uid={0},ou=people");
~~~

Nếu chuyển user xuống `ou=employees,ou=people`, DN pattern này không còn đúng. Trong giai đoạn chuyển tiếp, có thể đánh giá sử dụng **user search** thay vì một DN pattern cố định:

~~~java
factory.setUserSearchBase("ou=people");
factory.setUserSearchFilter(
        "(&(objectClass=inetOrgPerson)(uid={0}))");
~~~

Tuy nhiên, cần kiểm tra **search scope** do cơ chế tìm người dùng thực tế sử dụng, quyền bind account và khả năng tìm trong OU con. Nếu OU chứa nhiều tenant hoặc có UID trùng nhau, mở rộng base có thể dẫn đến kết quả không duy nhất và rủi ro xác thực sai người.

**Không tự coi LDAP search rộng hơn là an toàn.** V2 cần xác định ranh giới người dùng được phép đăng nhập và bảo đảm kết quả user search là duy nhất trong phạm vi nghiệp vụ. Khi thay `userDnPatterns` bằng `userSearchFilter`, kiểm thử cả đăng nhập thành công, thất bại, quyền group và cách xử lý tài khoản có cùng UID ở hai nhánh.

Đối với Spring Data LDAP ODM, `@Entry(base = "...")` cũng có thể cố định nhánh. Trong giai đoạn migration, đôi khi nên dùng `LdapTemplate` với DN explicit ở compatibility layer, thay vì buộc một entity repository mặc định tự tìm và cập nhật được mọi vị trí.

## 14. Khi schema và cấu trúc DN thay đổi đồng thời

Đổi schema và DN trong cùng một deployment làm tăng số trạng thái cần kiểm tra. Ví dụ:

- V1: entry dưới `ou=people`, chỉ biết `mail`.
- V2: biết `employeeNumber`, đọc cả hai OU.
- V3: muốn chỉ dùng OU mới và yêu cầu `employeeNumber`.

Các bước nên tách:

1. **Triển khai schema bổ sung** sao cho những entry V1 đang sử dụng vẫn hợp lệ.
2. **Deploy V2 tương thích:** đọc cũ/mới, coi trường mới là tùy chọn, tiếp tục ghi tại nguồn đang được V1 sử dụng.
3. **Backfill thuộc tính** trên entry ở OU cũ hoặc tại vị trí được chọn; giám sát lỗi dữ liệu và ACL.
4. **Ngừng V1**, gồm instance web, job, worker dài hạn, script và các consumer khác.
5. **Bắt đầu di chuyển DN theo lô** với V2 hỗ trợ hai đường dẫn và có chính sách ghi ổn định.
6. **Xác nhận toàn bộ entry đạt schema mới**, không còn tham chiếu DN cũ và không còn bản trùng.
7. **Bật yêu cầu mới** ở V3 sau khi dữ liệu đã đáp ứng; bỏ fallback theo kế hoạch riêng.
8. **Thu hẹp schema/quyền cũ** chỉ khi có quy trình và bằng chứng an toàn.

Đừng đồng thời xóa trường cũ, đổi `objectClass`, di chuyển DN và buộc tất cả client sử dụng API mới trong cùng một lần release. Khi lỗi xuất hiện, việc truy ra nguyên nhân và rollback trở nên rất khó.

## 15. Đồng thời, idempotency và consistency trong quá trình migration

Một migration tool chạy song song với traffic ứng dụng có thể gặp:

- **Entry bị sửa trong lúc move:** request PUT cập nhật attribute ở DN cũ ngay trước/sau khi migration rename; request có thể nhận lỗi không tìm thấy hoặc cập nhật sai trạng thái.
- **Hai worker cùng move một UID:** một worker thành công, worker khác nhận nguồn không còn/đích đã tồn tại.
- **Lỗi sau rename nhưng trước cập nhật group:** entry đã ở DN mới nhưng group vẫn tham chiếu DN cũ.
- **Mất phản hồi từ server:** client không biết rename đã xảy ra hay chưa.
- **Replica chưa đồng bộ:** đọc từ một replica chưa thấy thay đổi được thực hiện trên node khác.
- **Cache chưa vô hiệu:** ứng dụng vẫn giữ bản DN cũ dù server đã di chuyển.

### Điều phối theo entry

Với mỗi UID, thiết kế state machine minh họa:

~~~mermaid
flowchart TD
    A["PENDING: entry ở OU cũ"] --> B["PRECHECKED: đích và điều kiện hợp lệ"]
    B --> C["RENAMED: entry ở OU mới"]
    C --> D["REFERENCES_UPDATED: nhóm/ACL downstream đã xử lý"]
    D --> E["VERIFIED: đọc lại và kiểm tra dữ liệu"]
    E --> F["COMPLETED"]
    B --> X["FAILED: dừng/điều tra"]
    C --> X
    D --> X
    E --> X
~~~

State có thể được lưu trong **migration ledger bên ngoài directory** hoặc trong attribute được schema cho phép, tùy kiến trúc. Mọi bước cần có câu trả lời rõ khi chạy lại:

| Trạng thái thực tế | Hành động khi retry |
|---|---|
| Có DN cũ, không có DN mới | Có thể thử rename sau precheck |
| Không có DN cũ, có DN mới | Không rename lần nữa; xác minh identity và tiếp tục cập nhật references |
| Cả hai DN cùng tồn tại | **Dừng/điều tra**, không xóa bản nào tự động |
| Không có cả hai DN | Dừng; kiểm tra lỗi, replication và nguồn dữ liệu |
| Đã update một số group | Tiếp tục theo trạng thái, tránh thêm/xóa trùng member |
| Không thể chứng minh consistency | Chuyển sang xử lý thủ công hoặc rollback theo runbook |

Cần tránh dựa duy nhất vào “đọc rồi ghi” để chống tranh chấp. Nếu yêu cầu ngăn lost update một cách nguyên tử, cần tính năng server hỗ trợ phù hợp (ví dụ LDAP Assertion Control theo RFC 4528) hoặc cơ chế serialization/coordinator được kiểm chứng.

**Không có transaction LDAP chuẩn bao trùm toàn bộ các entry group, person, ACL và external systems.** Kế hoạch migration phải chấp nhận trạng thái trung gian có kiểm soát và có cơ chế sửa/hoàn tác.

## 16. Replication, caching và nhiều endpoint LDAP

Một hệ thống production có thể có nhiều LDAP server/replica hoặc directory proxy. Việc một lệnh ModifyDN trả thành công trên một endpoint không chứng minh các node khác đã đồng bộ.

Các điểm cần kiểm tra:

| Vấn đề | Triệu chứng | Cách kiểm chứng |
|---|---|---|
| Replication lag | DN mới chưa xuất hiện trên một replica | Đọc lại từng endpoint phù hợp, ghi nhận độ trễ |
| Referral/naming context | Rename không được phép hoặc truy vấn bị referral | Kiểm tra DIT/naming context và cấu hình client |
| Pool giữ context cũ | Một số instance vẫn dùng kết nối/cấu hình trước rollout | Tạo mới context/pool khi cần và kiểm tra từng instance |
| Search result cache | Kết quả vẫn là DN cũ | Vô hiệu hóa cache, kiểm tra TTL hoặc version |
| Authorization cache | Nhóm/role chậm cập nhật | Reauthentication hoặc chính sách refresh quyền |
| Index chưa sẵn sàng | Truy vấn V2 chậm hơn khi tìm ở OU mới | Kiểm tra index, search base, scope, latency |
| ACL khác OU | Bind thành công nhưng lookup/modify DN mới bị từ chối | Thử account có đặc quyền tối thiểu trong OU mới |

Thời điểm quét kiểm tra hoặc bật feature flag phải tính đến mô hình consistency của directory, không chỉ kết quả tức thời của một request. Trong hệ thống cần read-after-write mạnh, cân nhắc routing đọc về node phù hợp hoặc chờ xác nhận theo cơ chế server hỗ trợ.

## 17. Rollout theo feature flag và điều kiện dừng

Một cách tách rủi ro là triển khai các cờ **có ngữ nghĩa rõ**:

| Cờ ví dụ | Trạng thái đầu tiên | Khi bật |
|---|---|---|
| `ldap.read-new-location` | Off | V2 thử đọc ở OU mới rồi fallback cũ |
| `ldap.write-new-location` | Off | Chỉ bật sau khi điều phối migration/consumer cho phép |
| `ldap.require-employee-number` | Off | V2/V3 yêu cầu dữ liệu mới sau backfill |
| `ldap.disable-old-location` | Off | Dừng fallback chỉ sau khi mọi entry/consumer đã chuyển |

Đây là **tên flag do ứng dụng tự thiết kế**, không phải thuộc tính Spring Boot có sẵn. Các cờ phải được quản lý thống nhất qua cấu hình triển khai; không để mỗi pod áp dụng trạng thái khác nhau không có chủ đích.

Điều kiện dừng rollout/migration cần cụ thể:

- Tỷ lệ lỗi `noSuchObject` hoặc `invalidDNSyntax` tăng bất thường.
- Tỷ lệ LDAP bind/search/modify timeout tăng, connection pool bị cạn.
- Có trường hợp **cả hai DN cùng tồn tại** cho cùng mã nghiệp vụ.
- Group membership/authorization bị thay đổi ngoài dự kiến.
- Schema validation hoặc objectClass violation khi bản cũ/bản mới cùng ghi.
- Readback không khớp dữ liệu nguồn hoặc xảy ra replication lag quá ngưỡng.
- Một consumer chưa nâng cấp vẫn yêu cầu DN cũ.

**Không tiếp tục migrate chỉ vì tỷ lệ thành công tổng thể cao.** Một lỗi mất quyền truy cập của nhóm nhỏ người dùng hoặc mất dữ liệu thuộc tính quan trọng có thể là lý do phải dừng toàn bộ lô.

## 18. Runbook triển khai và rollback

### Runbook trước khi thay đổi

1. **Kiểm kê consumer:** web apps, batch jobs, Spring Security LDAP, công cụ quản trị, tích hợp bên ngoài và những service lưu DN/group membership.
2. **Chụp trạng thái:** danh sách DN, objectClass, thuộc tính bắt buộc, nhóm tham chiếu, ACL, search base, thống kê entry và backup được kiểm thử phục hồi.
3. **Kiểm tra schema trên mọi server:** phiên bản schema, attribute type, auxiliary class, DIT rule và replication.
4. **Thiết lập directory test:** dữ liệu có nhiều OU, nhóm, vài entry đặc biệt, ACL tương đương production.
5. **Triển khai V2 ở chế độ tương thích:** xác nhận V1 và V2 cùng đọc/ghi an toàn trong giai đoạn overlap.
6. **Đặt migration ledger:** trạng thái theo entry, batch size, retry, audit, ngưỡng dừng và người chịu trách nhiệm.
7. **Xác nhận kế hoạch rollback:** tách trường hợp chưa move, đã move, đã cập nhật group và đã contract.
8. **Bắt đầu từng lô nhỏ:** thử canary, so sánh dữ liệu trước/sau, theo dõi latency và lỗi LDAP.

### Rollback khác nhau theo từng thời điểm

| Thời điểm | Phương án rollback khả thi | Giới hạn |
|---|---|---|
| Chỉ mới thêm schema/thuộc tính optional | Có thể revert ứng dụng nhưng vẫn giữ schema mở rộng | V1 phải bảo toàn dữ liệu và không bị rule mới làm lỗi |
| V2 deploy nhưng chưa move DN | Trả traffic về V1 theo kế hoạch | Mọi dữ liệu V2 ghi phải tương thích V1 |
| Đã move một số entry | Có thể cần **reverse ModifyDN** và cập nhật group/reference về DN cũ | Không chỉ rollback binary; cần đảm bảo không xung đột và đủ ACL |
| Đã tắt consumer V1 nhưng chưa contract | Có thể tiếp tục dùng V2 dual-read và hoàn tác từng lô | V1 không tự đọc DN mới |
| Đã xóa thuộc tính/OU hoặc schema cũ | Có thể phải restore dữ liệu/schema và tái triển khai | Rủi ro cao; rollback phức tạp, thường cần kế hoạch riêng |

**Nguyên tắc:** rollback code không đồng nghĩa rollback dữ liệu LDAP. Sau khi DN và tham chiếu đã thay, bản ứng dụng cũ có thể không thể sử dụng dữ liệu mới, dù deployment thành công về mặt kỹ thuật.

### Reverse move phải được kiểm soát

Trước khi chuyển một DN từ mới về cũ:

- Xác nhận DN cũ chưa bị chiếm bởi entry khác.
- Xác minh entry ở DN mới đúng là entry đã được chuyển, dựa trên định danh ổn định và migration ledger.
- Kiểm tra những cập nhật nghiệp vụ phát sinh sau move; tránh ghi đè dữ liệu mới.
- Điều phối nhóm, ACL, cache và tham chiếu về DN cũ.
- Đọc lại entry/nhóm sau reverse move; không đánh dấu thành công khi mới hoàn thành `rename(...)`.

Trong tình huống khó, **giữ V2 có khả năng dual-read và dừng migration** có thể an toàn hơn cố đảo ngược hàng loạt khi chưa đủ thông tin.

## 19. Kiểm thử nhiều phiên bản ứng dụng cùng chạy

Unit test riêng cho V2 không chứng minh compatibility. Cần kiểm thử cả **V1 trên dữ liệu mới** và **V2 trên dữ liệu cũ**, kèm các thao tác ghi.

### Ma trận kiểm thử nền tảng

| Kịch bản | Bố trí | Kết quả mong đợi |
|---|---|---|
| V1 đọc entry cũ | Chỉ có DN cũ | Thành công như trước |
| V2 đọc entry cũ | V2 có fallback | Thành công |
| V2 đọc entry mới | Chỉ có DN mới | Thành công |
| V1 gặp entry đã move | DN mới, V1 DN pattern cũ | Thất bại dự kiến; dùng để chứng minh không move khi V1 còn traffic |
| V1 cập nhật entry có attribute mới | V2 đã thêm `employeeNumber` | Thuộc tính mới không bị xóa/ghi sai |
| V2 gặp entry chưa backfill | Không có `employeeNumber` | Xử lý optional hợp lệ |
| V2 đòi field sau backfill | Entry đã backfill | Validate đủ field |
| Đích DN đã có | Có hai entry/xung đột UID | Migration dừng, không xóa tự động |
| Rename thành công | Entry nguồn có mặt, đích trống | Nguồn không còn, đích có dữ liệu kỳ vọng |
| Group reference | Nhóm chứa `member=DN cũ` | Được cập nhật/đối chiếu theo plugin hoặc tool migration |
| V1 login sau move | DN pattern cũ | Kiểm tra lỗi dự kiến; xác nhận không còn V1 traffic |
| Spring Security V2 login | User search tìm vị trí mới | Xác thực và quyền nhóm đúng |
| ACL khác OU | Account chỉ có quyền ở OU cũ | Move/read mới phải báo lỗi thay vì nới quyền tự động |
| Replica lag | Đọc hai node sau move | Hành vi/độ trễ được ghi nhận |
| Retry giữa chừng | Rename xong, update nhóm chưa xong | Có thể tiếp tục theo migration ledger |
| Rollback reverse move | Đích mới → cũ sau một lô test | Đảm bảo tham chiếu và dữ liệu không mất |

### Integration test cho compatibility reader

Ví dụ kiểm tra lớp `PersonLocationReader` trên một directory test độc lập:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class PersonLocationReaderIntegrationTest {

    @Autowired
    private PersonLocationReader reader;

    @Test
    void readsPersonFromOldLocationDuringTransition() {
        // Fixture đã tạo uid=lan-test tại ou=people
        // và chưa tạo cùng uid trong ou=employees,ou=people.
        PersonLocationReader.PersonInfo info =
                reader.findByUid("lan-test");

        assertEquals("lan-test", info.uid());
    }

    @Test
    void readsPersonFromNewLocationAfterMove() {
        // Fixture độc lập đã tạo uid=binh-test tại
        // ou=employees,ou=people và không còn DN cũ.
        PersonLocationReader.PersonInfo info =
                reader.findByUid("binh-test");

        assertEquals("binh-test", info.uid());
    }
}
~~~

Đây là test khung, giả định đã có fixture phù hợp, bean reader được đăng ký và profile test kết nối đúng LDAP test. Trong code mục 9, `PersonLocationReader` là một class Java thông thường; muốn `@Autowired` trong test thì phải đăng ký nó làm Spring bean, ví dụ qua `@Bean` hoặc `@Component`. Không coi ví dụ test là ứng dụng chạy độc lập nếu chưa cấu hình bean và dữ liệu fixture.

**Kiểm thử migration đầy đủ** phải tạo OU cha và entry, chạy `LdapTemplate.rename(...)`, đọc từ cả hai DN, kiểm tra group membership, kiểm tra ACL, rồi dọn dữ liệu. Chỉ test một phương thức `findByUid(...)` không đủ chứng minh hệ thống an toàn khi move.

## 20. Giám sát và chẩn đoán khi phát hành

Các tín hiệu có ích sau khi bật schema hoặc DN mới:

| Metric / tín hiệu | Vì sao cần theo dõi? |
|---|---|
| Số entry ở OU cũ/mới | Theo dõi tiến độ, phát hiện mất/trùng entry |
| Số cặp DN cũ và mới cùng identity | Phát hiện dual-write/trùng dữ liệu |
| Số entry thiếu `employeeNumber` | Đánh giá mức hoàn thành backfill |
| Số kết quả fallback sang OU cũ | Cho biết còn phụ thuộc legacy path |
| LDAP `noSuchObject` | Sai DN, parent chưa tồn tại hoặc consumer cũ bị ảnh hưởng |
| `objectClassViolation` / `invalidAttributeSyntax` | Schema mới chưa đồng bộ hoặc mapping sai |
| LDAP `insufficientAccessRights` | ACL OU mới, group hoặc service account chưa đủ |
| Thời gian lookup/search/modify/rename | Phát hiện ảnh hưởng tới hiệu năng |
| Lỗi bind/authentication và quyền group | Phát hiện người dùng mất đăng nhập hoặc role |
| Replica lag/cache stale | Tránh đánh dấu sai trạng thái migration |
| Tỉ lệ phiên bản V1 còn traffic | Tiêu chí quyết định có được bắt đầu move không |
| Tỉ lệ migration failed/retried | Cảnh báo và dừng theo ngưỡng |

Không log password, raw LDAP attributes chứa dữ liệu cá nhân, hoặc toàn bộ DN nếu không cần. Có thể dùng mã entry đã được xử lý theo chính sách audit, correlation ID, migration batch ID và mã lỗi đã giới hạn thông tin nhạy cảm.

Khi báo cáo kết quả, phân biệt **“schema đã đăng ký”**, **“entry đã được backfill”**, **“DN đã move”**, **“group references đã sửa”** và **“mọi consumer đã chuyển”**. Một chỉ số duy nhất không thể thay thế toàn bộ các điều kiện này.

## 21. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| V1 trả 404 sau rollout V2 | Entry đã move, V1 vẫn lookup DN cũ | Dừng move, kiểm kê consumer; không chỉ restart V1 |
| V2 không thấy entry mới | Search base/scope, `@Entry(base)` hoặc ACL sai | Kiểm tra DN hiệu lực, ONELEVEL/SUBTREE và quyền |
| Hai bản entry cho cùng UID | Dual-write hoặc create sai vị trí | Dừng writer, đối soát stable ID; không xóa đại một bản |
| Field mới biến mất sau save của V1 | Whole-entity update/projection không tương thích | Chuyển sang Modify có chủ đích; test dữ liệu mới |
| `objectClassViolation (65)` | Thay schema/class không tương thích hoặc thiếu MUST | Kiểm tra SUP, structural/auxiliary, schema deployment |
| `noSuchObject (32)` khi rename | DN nguồn hoặc OU đích chưa tồn tại | Kiểm tra parent và trạng thái migration |
| `entryAlreadyExists (68)` | DN đích trùng | Dừng; kiểm tra xung đột identity |
| `insufficientAccessRights (50)` | Không có quyền move/ghi ở OU mới | Sửa ACL có kiểm soát, không dùng root bind mặc định |
| `notAllowedOnNonLeaf (66)` | Thao tác bị server cấm với entry có con | Kiểm tra khả năng move và mô hình DIT |
| Group không còn nhận user | `member` vẫn chứa DN cũ | Kiểm tra referential integrity và migration nhóm |
| V2 login được nhưng role mất | Group search/authority mapping chưa cập nhật | Test DN membership và quyền đọc group |
| Directory replica trả dữ liệu khác nhau | Replication lag hoặc cấu hình lệch | Đo từng endpoint, chờ đồng bộ có kiểm chứng |
| Rollback V1 nhưng dữ liệu lỗi | Dữ liệu đã contract/move | Cần rollback data hoặc duy trì compatibility layer |

Tùy directory server và API, cùng một tình huống có thể được báo bằng các mã hoặc exception khác nhau. Không viết `catch (Exception) { return oldValue; }` để che lỗi ACL, schema hoặc kết nối.

## 22. Bài tập thực hành

**Bối cảnh:** ứng dụng dùng Spring Data LDAP lưu user dưới `ou=people,dc=example,dc=org`. Phiên bản mới muốn chuyển user sang `ou=employees,ou=people` và sử dụng `employeeNumber`. Một web instance V1 và một batch job cũ vẫn có thể chạy trong đợt rollout.

Thực hiện trên directory test độc lập:

1. Tạo entry `uid=lan` thuộc `inetOrgPerson` dưới OU cũ; tạo nhóm `developers` có `member` trỏ tới DN này.
2. Kiểm tra schema `employeeNumber` được phép trong `inetOrgPerson`; thêm attribute bằng Modify mà không đổi structural class.
3. Tạo `PersonLocationReader` biết cả DN cũ và DN mới, với fallback **chỉ khi NameNotFound**.
4. Kiểm tra V1 và V2 cùng đọc/ghi dữ liệu khi entry chưa move.
5. Cố ý move một entry test trong lúc V1 dùng DN pattern cũ; quan sát lỗi để giải thích vì sao phải đợi V1 ngừng phục vụ.
6. Chuẩn bị OU mới, ACL và fixture; dùng `LdapTemplate.rename(...)` chuyển một entry sau khi mô phỏng V1 đã rút khỏi traffic.
7. Đọc lại entry ở DN mới, xác nhận DN cũ không còn và `employeeNumber` được bảo toàn.
8. Kiểm tra `member` của nhóm: nếu không có plugin referential integrity, hãy cập nhật đúng giá trị DN có kiểm tra trạng thái.
9. Chạy một migration batch có ledger; ngắt sau rename rồi chạy lại, kiểm tra idempotency.
10. Thử tình huống có cả DN cũ và DN mới cùng UID; bảo đảm migration **dừng** thay vì chọn entry tùy ý.
11. Kiểm tra Spring Security LDAP bind, group-role mapping và ACL của bind account ở OU mới.
12. Viết kế hoạch rollback sau khi move một phần, bao gồm reverse DN và group reference.
13. Định nghĩa dashboard giám sát số entry cũ/mới, lỗi LDAP và mức phụ thuộc fallback.
14. Đề xuất thời điểm tắt đọc cũ, yêu cầu trường mới và bỏ quyền trên nhánh legacy.

**Tiêu chí hoàn thành:** người học phân biệt được schema expand với DN migration, thiết kế lộ trình triển khai có thể kiểm thử khi nhiều phiên bản cùng chạy, không mất dữ liệu, không mất quyền và biết vì sao rollback ứng dụng không đủ để rollback directory.

## 23. Tổng kết và tài liệu tham khảo

**Thay đổi schema hoặc DN trong LDAP là một thay đổi dữ liệu có ảnh hưởng xuyên nhiều phiên bản ứng dụng.** Thêm thuộc tính tùy chọn thường dễ triển khai hơn di chuyển DN hoặc thay structural class, nhưng vẫn cần kiểm tra code cũ có bảo toàn dữ liệu mới khi ghi hay không.

Một chiến lược vững chắc là:

~~~text
EXPAND
  -> Server hỗ trợ schema mới, V2 đọc được dạng cũ và mới
  -> V1 vẫn hoạt động an toàn trên entry cũ
MIGRATE
  -> Rút V1 khỏi traffic hoặc có compatibility đã kiểm chứng
  -> Di chuyển theo lô + cập nhật references + readback
CONTRACT
  -> Xác minh mọi consumer đã chuyển
  -> Bỏ fallback và phụ thuộc dữ liệu cũ theo kế hoạch
~~~

Luôn nhớ rằng `@Entry`, `LdapRepository` và `LdapTemplate` chỉ là lớp truy cập từ Java. Directory server vẫn thực thi schema, ACL, ranh giới naming context và LDAP protocol; `ModifyDN` không tự cập nhật toàn bộ group references hay thực hiện transaction nhiều entry. Trong rollout nhiều phiên bản, **hợp đồng giữa các phiên bản và trạng thái dữ liệu thực tế** mới là căn cứ quyết định có được chuyển bước hay không.

Nguồn tham khảo:

- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): ODM, `@Entry`, `LdapRepository`, cách ánh xạ entity và repository.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `LdapContextSource`, search, modify, rename và xây DN.
- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): DN pattern/user search và group authority khi thay cấu trúc directory.
- [RFC 4511 — Lightweight Directory Access Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search, Modify, ModifyDN và mã kết quả LDAP.
- [RFC 4512 — Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): schema, structural class, DIT và naming context.
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): biểu diễn/escaping DN.
- [RFC 4515 — Search Filter Syntax](https://www.rfc-editor.org/rfc/rfc4515): escaping và filter LDAP.
- [RFC 4528 — Assertion Control](https://www.rfc-editor.org/rfc/rfc4528): hỗ trợ điều kiện nguyên tử trên một số thao tác khi client và server triển khai.
