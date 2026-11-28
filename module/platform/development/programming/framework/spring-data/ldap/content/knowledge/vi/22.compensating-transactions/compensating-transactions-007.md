# Đổi tên tạm thời và TempEntryRenamingStrategy

Trong **Spring Data LDAP**, một ứng dụng Java có thể dùng `LdapRepository` hoặc `LdapTemplate` để tìm kiếm, đọc và cập nhật những entry nằm trong cây LDAP. Khi một quy trình phải thực hiện **nhiều thay đổi liên tiếp**, ta thường muốn có khả năng hoàn tác nếu bước sau thất bại. Tuy nhiên, không thể mặc nhiên áp dụng cách suy nghĩ về `COMMIT`/`ROLLBACK` của cơ sở dữ liệu quan hệ cho LDAP.

**Spring LDAP** cung cấp cơ chế **giao dịch bù trừ phía client** (*client-side compensating transactions*). Đối với các thao tác như `unbind` (xóa entry) và `rebind` (thay entry), thư viện có thể **đổi tên entry gốc sang một DN tạm thời** trước khi quyết định xóa hẳn hoặc khôi phục nó. Chính sách tạo DN tạm được định nghĩa bởi interface **`TempEntryRenamingStrategy`**.

Bài học thuộc chương **Giao dịch bù trừ**, tập trung vào cách đổi tên tạm thời hoạt động, hai chiến lược sẵn có, cấu hình với `ContextSourceTransactionManager`, các ràng buộc schema/ACL và phương pháp kiểm thử. Nội dung này liên quan trực tiếp tới Spring Data LDAP, nhưng phần transaction nằm trong **Spring LDAP Core**; **repository không tự có rollback kiểu JDBC** nếu chưa được nối đúng cơ chế.

Sau bài học, bạn có thể:

1. Giải thích vì sao hoàn tác một thao tác LDAP `unbind` khó hơn hoàn tác một `rename`.
2. Mô tả các bước **ghi nhận – chuẩn bị – commit/rollback** của giao dịch bù trừ.
3. Hiểu interface `TempEntryRenamingStrategy.getTemporaryName(Name)` và phạm vi sử dụng cho `unbind`/`rebind`.
4. Phân biệt `DefaultTempEntryRenamingStrategy` và `DifferentSubtreeTempEntryRenamingStrategy`.
5. Cấu hình `TransactionAwareContextSourceProxy`, `LdapTemplate` và `ContextSourceTransactionManager` đúng quan hệ.
6. Chọn nơi lưu tạm có ACL và naming context phù hợp; tránh collision, lỗi xóa cây và lộ entry tạm trong search.
7. Kiểm thử commit, rollback, lỗi mạng, tính đồng thời và giải quyết entry tạm còn sót.

## 1. Giao dịch bù trừ LDAP là gì?

Giả sử một hệ thống nhân sự cần xóa một tài khoản trong LDAP và cập nhật nhóm quyền:

```text
1. Xóa uid=lan,ou=people,dc=example,dc=org
2. Sửa cn=developers,ou=groups,dc=example,dc=org
3. Hoàn tất yêu cầu
```

Nếu bước 2 thất bại sau khi bước 1 đã xóa entry thật, ứng dụng không thể đơn giản gọi `ROLLBACK` lên LDAP server rồi mong mọi trạng thái quay về ban đầu. Mỗi LDAP Add/Modify/Delete/Modify DN có semantics riêng; giao thức LDAP cơ bản **không cung cấp một giao dịch ACID tự động cho nhiều request** giống JDBC.

Spring LDAP xử lý một số trường hợp bằng cách **ghi nhận thao tác ngược** và cố thực hiện nó khi giao dịch ứng dụng thất bại:

```text
Phía ứng dụng
  @Transactional("ldapTxManager")
             |
             v
  ContextSourceTransactionManager
             |
             v
  Ghi nhận thao tác và dữ liệu hoàn tác
             |
             +--> Nếu thành công: commit những bước còn chờ
             |
             +--> Nếu lỗi: chạy các thao tác bù trừ (rollback)
             v
  LDAP server (các operation thực tế)
```

**Quan trọng:** đây là **cơ chế nỗ lực khôi phục (*best effort*) phía client**, không phải một transaction thực được server giữ kín:

- Server và các client khác có thể **nhìn thấy những thay đổi trung gian**.
- Trong một giao dịch dài, các client khác có thể sửa entry liên quan và gây xung đột.
- Nếu mất kết nối đúng lúc cần rollback, Spring LDAP **không bảo đảm** khôi phục được.
- Crash, timeout hoặc quyền bị thu hồi có thể làm entry ở lại DN tạm.
- `@Transactional` chỉ có tác dụng nếu luồng gọi đi qua đúng transaction manager, proxy và connection source.

**Ngoại lệ cần biết:** RFC 5805 mô tả một **LDAP Transaction extension mang tính Experimental**; nó không phải tính năng có thể mặc định giả định ở mọi LDAP server, và cơ chế bù trừ `ContextSourceTransactionManager` được bàn ở đây **không phải** triển khai giao thức RFC 5805.

## 2. Vì sao xóa entry cần đổi tên tạm thời?

Xét entry:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
```

Nếu gọi `ldapTemplate.unbind(dn)` theo cách thông thường, server xóa entry. Khi muốn khôi phục, ứng dụng cần biết **toàn bộ dữ liệu gốc**, nhưng có thể không được phép đọc các thuộc tính nhạy cảm, operational attributes hoặc thuộc tính do server tự quản lý. Việc tạo lại bằng bản sao vài thuộc tính đọc được **không chứng minh** khôi phục đầy đủ trạng thái.

Spring LDAP chọn một lối khác cho thao tác `unbind` nằm trong giao dịch bù trừ:

```text
Entry ban đầu:
uid=lan,ou=people,dc=example,dc=org

    Transaction chuẩn bị xóa
               |
               v
Rename sang DN tạm
uid=lan_temp,ou=people,dc=example,dc=org

        /                     \
       /                       \
  COMMIT                      ROLLBACK
     |                           |
     v                           v
Unbind DN tạm                Rename DN tạm
(xóa hẳn entry)              về DN ban đầu
```

Đây là lý do tên **`TempEntryRenamingStrategy`** có từ “đổi tên”: thay vì xóa rồi tìm cách dựng lại toàn bộ attributes, thư viện **giữ entry gốc ở một DN tạm** cho tới khi biết có nên xóa thật không.

### 2.1. Ba thời điểm phải phân biệt

| Thời điểm | Trạng thái ở DN gốc | Trạng thái ở DN tạm |
| --- | --- | --- |
| Trước giao dịch | Có entry cũ | Chưa có |
| Sau bước chuẩn bị `unbind` | Không còn ở DN gốc | Entry cũ đang nằm ở đây |
| Sau **commit** thành công | Không có | Đã bị xóa |
| Sau **rollback** thành công | Entry cũ trở về | Không còn |

Ngay khi entry chuyển sang DN tạm, **các lookup theo DN gốc có thể không tìm thấy nó**. Điều này giúp gần giống cảm giác “đã xóa”, nhưng không có isolation: search ở nhánh chứa DN tạm vẫn có thể đọc được entry, hoặc referral/reference có thể hành xử khác.

### 2.2. Rebind cũng dùng DN tạm

`rebind` là thao tác **thay entry hiện có** bằng object/attributes mới. Khi thực hiện trong giao dịch bù trừ, thư viện cũng có thể **đổi tên entry cũ sang nơi tạm**, rồi khi commit mới tạo nội dung mới tại DN gốc và loại bỏ entry tạm.

Nếu rollback trước commit, entry gốc được đổi tên trở lại. **Không phải** vì `rebind` tự sinh bản snapshot toàn bộ attributes; cơ chế đổi tên tạm chính là cách giữ entry gốc.

## 3. Vòng đời những thao tác LDAP khi dùng transaction manager

Theo tài liệu Spring LDAP, mỗi operation có thể gồm các pha **recording**, **preparation**, **commit** và **rollback**. Bảng sau tóm lược hành vi ở mức khái niệm:

| Thao tác LDAP | Ghi nhận | Bước chuẩn bị/thực thi | Commit | Rollback |
| --- | --- | --- | --- | --- |
| `bind` | DN được tạo | Bind entry mới | Không cần thao tác thêm | Unbind DN vừa tạo |
| `rename` | DN nguồn và DN đích | Rename ngay | Không cần thao tác thêm | Rename từ đích về nguồn |
| **`unbind`** | DN nguồn, tính DN tạm | **Rename entry sang DN tạm** | **Unbind entry tạm** | **Rename DN tạm về nguồn** |
| **`rebind`** | DN nguồn, attributes mới, DN tạm | **Rename entry cũ sang DN tạm** | Thay entry tại DN gốc, dọn entry tạm | Khôi phục entry cũ từ DN tạm |
| `modifyAttributes` | DN và các modification bù trừ | Modify attributes | Không cần thao tác thêm | Apply modifications ngược |

Không nên đọc bảng này như một lời hứa về **độ nguyên tử tuyệt đối**. Chẳng hạn, commit của `rebind` gồm nhiều operation; lỗi ở một operation giữa chừng có thể để lại trạng thái cần xử lý thủ công.

### 3.1. TempEntryRenamingStrategy được gọi khi nào?

**Chỉ một số thao tác cần DN tạm**, nhất là `unbind` và `rebind`. Nó không phải thuật toán đổi tên cho mọi lần gọi `ldapTemplate.rename(oldDn, newDn)`; lệnh rename trực tiếp có rollback là **rename ngược**, không cần chọn DN tạm từ strategy.

Đây là khác biệt quan trọng khi đọc trace:

```text
Ứng dụng gọi unbind(uid=lan)
     |
     v
Transaction interceptor
     |
     +-- strategy.getTemporaryName(uid=lan)
     |
     +-- server nhận Modify DN sang tên tạm
     |
     +-- commit mới nhận Delete tên tạm
```

Một audit log của server có thể thấy **Modify DN trước Delete** dù mã nguồn chỉ gọi một `unbind`. Đây không nhất thiết là hoạt động bất thường; nó có thể là hành vi chủ đích của giao dịch bù trừ.

## 4. Interface TempEntryRenamingStrategy

Interface thuộc package:

```java
org.springframework.ldap.transaction.compensating.TempEntryRenamingStrategy
```

Hợp đồng chính:

```java
import javax.naming.Name;

public interface TempEntryRenamingStrategy {
    Name getTemporaryName(Name originalName);
}
```

Phương thức nhận một **`Name` gốc** và trả về **`Name` tạm**. Trong trường hợp `ContextSource` có base `dc=example,dc=org`, tên được sử dụng trong `LdapTemplate` và strategy thường được hiểu **tương đối với base của context**.

**Ví dụ ý tưởng:**

```text
originalName = uid=lan,ou=people
temporaryName = uid=lan_temp,ou=people
```

Strategy **chỉ quyết định tên**; bản thân `getTemporaryName(...)` không tự gọi LDAP để rename và không tạo OU tạm. Việc áp dụng rename/commit/rollback do các thành phần giao dịch khác quản lý.

### 4.1. Những điều một strategy tốt cần thỏa mãn

- **DN hợp lệ:** tên do strategy trả về phải parse được, có RDN/parent đúng.
- **Destination hợp lệ:** parent của DN tạm phải tồn tại, cùng vùng LDAP mà thao tác Modify DN được hỗ trợ.
- **Quyền truy cập:** bind account phải đủ quyền rename sang nơi tạm, rename ngược và xóa khi commit.
- **Tránh xung đột:** DN tạm không được trùng entry có sẵn hoặc một giao dịch khác đang dùng.
- **Không mở rộng phạm vi truy vấn:** dữ liệu tạm không nên xuất hiện trong các search phục vụ nghiệp vụ khi đáng lẽ entry đã bị xóa/thay thế.
- **Có khả năng dọn dẹp:** khi ứng dụng crash hoặc mạng đứt, có phương án nhận diện entry tạm còn sót và đối soát, không xóa nhầm dữ liệu thật.

Các yêu cầu trên **không tự được bảo đảm** chỉ bằng việc triển khai một hàm Java trả về `Name`.

## 5. DefaultTempEntryRenamingStrategy: thêm hậu tố vào RDN

Spring LDAP cung cấp class:

```java
org.springframework.ldap.transaction.compensating.support.DefaultTempEntryRenamingStrategy
```

Đây là **strategy mặc định** của `ContextSourceTransactionManager`. Nó thêm hậu tố **`_temp`** vào phần cụ thể nhất (leaf RDN) và giữ nguyên parent.

```text
Trước:
uid=lan,ou=people,dc=example,dc=org

Tạm thời:
uid=lan_temp,ou=people,dc=example,dc=org
```

### 5.1. Dùng class trực tiếp để xem DN tạm

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.springframework.ldap.transaction.compensating.support.DefaultTempEntryRenamingStrategy;

DefaultTempEntryRenamingStrategy strategy =
        new DefaultTempEntryRenamingStrategy();

Name original = new LdapName(
        "uid=lan,ou=people,dc=example,dc=org");
Name temporary = strategy.getTemporaryName(original);

System.out.println(temporary);
// uid=lan_temp,ou=people,dc=example,dc=org
```

Đoạn code này **chỉ tính tên**; không làm thay đổi directory.

### 5.2. Tùy chỉnh hậu tố

```java
DefaultTempEntryRenamingStrategy strategy =
        new DefaultTempEntryRenamingStrategy();
strategy.setTempSuffix("_pending_delete");

Name temporary = strategy.getTemporaryName(
        new LdapName("uid=lan,ou=people"));

// uid=lan_pending_delete,ou=people
```

`setTempSuffix(String)` thay hậu tố cố định. Đây **không** phải cơ chế đảm bảo tên duy nhất; nếu đã có entry `uid=lan_pending_delete,ou=people` hoặc hai transaction đồng thời xử lý cùng DN, thao tác có thể bị từ chối hoặc gây xung đột.

### 5.3. Vì sao chiến lược mặc định có nhược điểm?

**Entry tạm vẫn nằm trong cùng subtree**. Ví dụ code nghiệp vụ tìm người:

```text
Base  : ou=people,dc=example,dc=org
Scope : SUBTREE
Filter: (objectClass=inetOrgPerson)
```

Trong khi `uid=lan` bị đổi thành `uid=lan_temp`, entry tạm vẫn có thể khớp `(objectClass=inetOrgPerson)`. Search từ một request khác — hoặc ngay trong cùng transaction — có thể **vẫn thấy người mà nghiệp vụ tưởng đã xóa**.

Những hệ quả có thể xảy ra:

- Một bộ đếm người dùng vẫn đếm entry tạm.
- Một quy trình đồng bộ khác nhận `uid=lan_temp` như một user mới.
- Code kiểm tra “không còn entry nào dưới OU” trả kết quả sai.
- Sự trùng DN tạm khi retry/crash làm lần sau thất bại.
- ACL hoặc quy tắc ứng dụng phân quyền theo OU có thể đối xử entry tạm như user bình thường.

**Không nên chỉ lọc `(uid=*_temp)` để chữa mọi vấn đề**: tên thật có thể chứa hậu tố đó, và cách lọc này còn bỏ sót những tên tạm tùy chỉnh hoặc kiểu RDN khác.

## 6. DifferentSubtreeTempEntryRenamingStrategy: chuyển sang nhánh tạm riêng

Spring LDAP có class thứ hai:

```java
org.springframework.ldap.transaction.compensating.support.DifferentSubtreeTempEntryRenamingStrategy
```

Thay vì giữ entry tạm trong cùng OU nghiệp vụ, strategy này chuyển entry sang **một subtree tạm đã tồn tại**:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
└── ou=tx-staging
    └── (nơi giữ các entry tạm trong transaction)
```

Khi `uid=lan,ou=people` bị `unbind` trong một transaction, mục đích là chuyển nó đến vùng:

```text
uid=lan<suffix>,ou=tx-staging,dc=example,dc=org
```

Theo Javadoc hiện hành, strategy có thể thêm **hậu tố số thứ tự** vào RDN để giảm nguy cơ trùng tên, ví dụ `uid=lan1,ou=tx-staging`. **Không dựa vào tên chính xác `uid=lan1` trong code nghiệp vụ**: chỉ nên đối chiếu API và kiểm tra DN nằm dưới subtree tạm. Khả năng tránh collision trong một tiến trình cũng không bảo đảm **duy nhất toàn cục** qua nhiều instance hoặc sau restart.

### 6.1. Cách khởi tạo

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.springframework.ldap.transaction.compensating.support.DifferentSubtreeTempEntryRenamingStrategy;

DifferentSubtreeTempEntryRenamingStrategy strategy =
        new DifferentSubtreeTempEntryRenamingStrategy("ou=tx-staging");

Name original = new LdapName("uid=lan,ou=people");
Name temporary = strategy.getTemporaryName(original);

System.out.println(temporary);
// Ví dụ có thể là uid=lan1,ou=tx-staging;
// hậu tố cụ thể phụ thuộc việc cấp tên tạm của implementation.
```

**Chú ý:** `"ou=tx-staging"` trong code là DN tương đối dưới base `dc=example,dc=org` của `ContextSource`. Nếu cấu hình `ContextSource` khác, phải tính đúng tên theo **cùng naming context**. Strategy chỉ đổi tên theo quy tắc; **không tự tạo** OU `tx-staging`.

### 6.2. Tạo parent tạm trước khi giao dịch

Directory test phải có một container thích hợp, ví dụ:

```ldif
dn: ou=tx-staging,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: tx-staging
description: Temporary staging area for compensating LDAP transactions
```

Hãy tạo OU này qua quy trình **quản trị directory** được cấp quyền (ví dụ seed LDIF trong test), không để mỗi HTTP request tự tạo/đổi schema. Container tạm không tự xuất hiện sau khi tạo bean Java.

### 6.3. Vì sao việc chuyển subtree có lợi?

Nếu mọi search phục vụ người dùng đều giới hạn `base("ou=people")`, entry đang ở `ou=tx-staging` sẽ **không còn nằm trong phạm vi search đó**. Điều này phù hợp hơn với ý định logic “entry đã bị xóa tạm thời”.

Tuy nhiên, nếu một search dùng base `dc=example,dc=org` với `SUBTREE`, entry tạm **vẫn có thể xuất hiện**. Do đó, kiến trúc phải kết hợp:

- Search base phù hợp từng use case.
- ACL trên `ou=tx-staging` để ngăn client nghiệp vụ đọc dữ liệu tạm.
- Quy tắc lọc và quyền truy cập tránh lộ những entry chưa commit.
- Tránh dùng search trên toàn DIT cho những thao tác quyết định quyền.

### 6.4. Hạn chế của việc move sang subtree

Một thao tác chuyển entry giữa hai parent có thể bị từ chối nếu:

1. Parent `ou=tx-staging` chưa tồn tại.
2. DN mới trùng entry khác.
3. Tài khoản bind không có quyền **rename/move** vào subtree, rename về source hoặc xóa sau commit.
4. Source và destination nằm ở **naming contexts/DSA khác nhau** mà server không hỗ trợ Modify DN xuyên nhánh.
5. Schema, objectClass hoặc naming rules không chấp nhận vị trí/RDN mới.
6. Entry có con hoặc server áp quy tắc đặc thù về Modify DN đối với subtree.
7. Referentials như `member`, `manager` hoặc server-side referential integrity plugin có side effect khi DN đổi.

**Không giả định một subtree tạm riêng sẽ giải quyết mọi hạn chế**. Nó cải thiện phạm vi search và một số quy trình xóa cây, nhưng đổi lại cần quản trị OU/ACL, xét naming context và đối soát dữ liệu.

## 7. So sánh hai strategy

| Tiêu chí | DefaultTempEntryRenamingStrategy | DifferentSubtreeTempEntryRenamingStrategy |
| --- | --- | --- |
| Cách tạo DN tạm | Thêm hậu tố vào leaf RDN; giữ parent | Chuyển entry sang subtree tạm đã cấu hình |
| Ví dụ | `uid=lan_temp,ou=people` | `uid=lan1,ou=tx-staging` (minh họa) |
| Cần tạo OU tạm riêng | Không | **Có**, trước khi dùng |
| Có thể thấy trong search gốc `ou=people` | **Có** nếu filter vẫn khớp | Thường **không** |
| Nguy cơ collision | Có, nhất là suffix cố định | Có thể giảm bằng hậu tố số nhưng không triệt tiêu |
| Phù hợp xóa subtree đệ quy trong mô hình được tài liệu Spring LDAP mô tả | Có thể **thất bại** | Thường phù hợp hơn, nhưng cần thử với server |
| Phụ thuộc ACL của parent khác | Chủ yếu parent hiện tại | **Có**, ở subtree đích và khi hoàn nguyên |
| Rủi ro cross-DSA/naming context | Thấp hơn khi ở cùng parent | Cần kiểm tra rõ trước khi dùng |
| Hoạt động khi mất mạng giữa rollback | **Không được bảo đảm** | **Không được bảo đảm** |

**Tóm lại:** nếu dùng `unbind/rebind` bù trừ cho nghiệp vụ có subtree, hoặc không muốn entry tạm xuất hiện trong các query thông thường, **DifferentSubtree** thường là lựa chọn hợp lý hơn. Nếu dùng Default, phải chấp nhận và kiểm soát chuyện entry tạm ở cùng subtree, cũng như va chạm tên.

## 8. Vì sao xóa cây có thể thất bại với chiến lược mặc định?

Giả sử cần xóa một OU và toàn bộ entry con:

```text
ou=obsolete,dc=example,dc=org
├── uid=user01
└── uid=user02
```

Với thao tác xóa cây đệ quy, chương trình thường xử lý từ **lá lên gốc** (*depth-first*), vì nhiều directory không cho phép xóa trực tiếp một entry còn con bằng Delete thông thường.

Ở chế độ bù trừ với **DefaultTempEntryRenamingStrategy**, khi định “xóa” `uid=user01`, Spring LDAP tạm rename thành `uid=user01_temp` **vẫn nằm dưới `ou=obsolete`**. Dù ứng dụng tưởng đã xóa các leaf, OU cha vẫn có **entry tạm**:

```text
ou=obsolete,dc=example,dc=org
├── uid=user01_temp
└── uid=user02_temp
```

Khi đến bước xóa OU cha, nó **vẫn còn con** và dễ gặp lỗi `notAllowedOnNonLeaf` hoặc lỗi tương đương. Tài liệu Spring LDAP đặc biệt khuyến nghị **DifferentSubtreeTempEntryRenamingStrategy** cho xóa subtree trong mô hình transaction bù trừ này.

Nếu các leaf được chuyển khỏi cây sang `ou=tx-staging`, OU cũ có thể trở thành rỗng trước khi xóa. Tuy nhiên:

- Server phải cho phép move từng entry như dự kiến.
- Cần quản lý các **subtree node còn con**, kể cả các entry có con sâu hơn.
- Nếu dùng các thao tác xóa recursive của API, phải kiểm thử đúng đường thực thi, không chỉ dựng một ví dụ hình vẽ.
- Nếu crash giữa chừng, cả cây nguồn lẫn subtree tạm có thể ở trạng thái dở dang và cần đối soát.

Đừng tự triển khai “recursive delete + rename tạm” trên dữ liệu production khi chưa kiểm chứng backup/restore, ACL, transaction boundaries và hành vi trên server thực tế.

## 9. Cấu hình Java cho transaction manager và renaming strategy

Spring LDAP sử dụng ba thành phần có quan hệ **rất cụ thể**:

1. **`LdapContextSource` gốc:** nơi kết nối thực sự tới LDAP server.
2. **`TransactionAwareContextSourceProxy`:** bọc source gốc để các thao tác `DirContext` có thể ghi nhận operation bù trừ.
3. **`ContextSourceTransactionManager`:** điều phối giao dịch và strategy; nhận **source gốc**, **không phải proxy**.

```text
                  @Transactional
                        |
                        v
             ContextSourceTransactionManager
                        |
                        | nhận target ContextSource
                        v
                LdapContextSource

Application service
        |
        v
    LdapTemplate
        |
        v
TransactionAwareContextSourceProxy
        |
        | wrap
        v
  LdapContextSource (cùng object phía trên)
        |
        v
      LDAP server
```

Nếu template trỏ **trực tiếp** vào `LdapContextSource` mà không qua transaction-aware proxy, các thao tác có thể không được intercept để ghi nhận hoàn tác. Nếu transaction manager trỏ **nhầm một source khác**, transaction và template không dùng chung tài nguyên dự kiến.

### 9.1. Ví dụ Spring Java Config

Ví dụ dưới đây dùng Java configuration với Spring LDAP có những API transaction đã nêu, và giả định có Spring transaction support tương thích:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.transaction.compensating.manager.ContextSourceTransactionManager;
import org.springframework.ldap.transaction.compensating.manager.TransactionAwareContextSourceProxy;
import org.springframework.ldap.transaction.compensating.support.DifferentSubtreeTempEntryRenamingStrategy;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement
public class LdapCompensationConfiguration {

    @Bean("targetContextSource")
    public LdapContextSource targetContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase("dc=example,dc=org");
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setPooled(false);
        return source;
    }

    @Bean("transactionAwareContextSource")
    public ContextSource transactionAwareContextSource(
            @Qualifier("targetContextSource") ContextSource target) {
        return new TransactionAwareContextSourceProxy(target);
    }

    @Bean("ldapTemplate")
    public LdapTemplate ldapTemplate(
            @Qualifier("transactionAwareContextSource") ContextSource source) {
        return new LdapTemplate(source);
    }

    @Bean("ldapTxManager")
    public ContextSourceTransactionManager ldapTxManager(
            @Qualifier("targetContextSource") ContextSource target) {

        ContextSourceTransactionManager manager =
                new ContextSourceTransactionManager(target);
        manager.setRenamingStrategy(
                new DifferentSubtreeTempEntryRenamingStrategy(
                        "ou=tx-staging"));
        return manager;
    }
}
```

Tương ứng một cấu hình ví dụ cho môi trường thử nghiệm:

```yaml
app:
  ldap:
    url: ldaps://directory.example.org:636
    bind-dn: uid=transaction-writer,ou=services,dc=example,dc=org
    bind-password: ${LDAP_TX_WRITER_PASSWORD}
```

**Các điều kiện để dùng mẫu code:**

- Bean `targetContextSource` do Spring khởi tạo và gọi lifecycle cần thiết. Nếu tự `new LdapContextSource()` ngoài container, cần hoàn tất cấu hình và `afterPropertiesSet()` trước khi dùng.
- `ou=tx-staging,dc=example,dc=org` **đã tồn tại** và nằm trong vùng server cho phép di chuyển entry.
- Tài khoản bind có quyền phù hợp cho rename, unbind ở subtree tạm và rename ngược.
- LDAPS có chứng chỉ/truststore/hostname validation hợp lệ; không hardcode password hay dùng trust-all TLS.
- `ldapTemplate` thực sự inject **transaction-aware source**, không tự động bị Spring Boot tạo thêm một bean khác làm service dùng nhầm.
- Nếu có nhiều `PlatformTransactionManager`, các method phải **chỉ định `transactionManager = "ldapTxManager"`** để tránh chọn nhầm transaction JDBC.

**Không dùng cả proxy và target một cách tùy tiện cho cùng workflow.** Nên đặt tên bean đủ rõ và có integration test xác nhận thao tác đi qua đường transaction-aware. Nếu kết hợp Spring Data LDAP repository, phải kiểm tra repository đang tham chiếu `LdapTemplate` nào (ví dụ qua `@EnableLdapRepositories(ldapTemplateRef = "ldapTemplate")` khi cấu hình thủ công).

### 9.2. Thay strategy mặc định khi cần

Nếu dự án chỉ cần chiến lược thêm suffix và đã chấp nhận giới hạn của nó:

```java
import org.springframework.ldap.transaction.compensating.support.DefaultTempEntryRenamingStrategy;

DefaultTempEntryRenamingStrategy strategy =
        new DefaultTempEntryRenamingStrategy();
strategy.setTempSuffix("_pending");
manager.setRenamingStrategy(strategy);
```

Ví dụ này giả định biến `manager` có kiểu `ContextSourceTransactionManager` ở cấu hình trước; nó là đoạn **thay thế lựa chọn strategy**, không phải một bean độc lập.

## 10. Ví dụ service: unbind rồi phát sinh lỗi để kiểm tra rollback

Giả sử entry `uid=lan,ou=people,dc=example,dc=org` tồn tại trong **directory test**. Phương thức service sau được gọi **từ một bean Spring khác**, đi qua transaction proxy:

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DirectoryRemovalService {

    private final LdapTemplate ldapTemplate;

    public DirectoryRemovalService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Transactional(transactionManager = "ldapTxManager")
    public void removeUser(String uid, boolean failAfterStaging) {
        Name userDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        // Trong transaction-aware context:
        // Spring LDAP tạm rename entry thay vì xóa ngay.
        ldapTemplate.unbind(userDn);

        if (failAfterStaging) {
            // Chỉ để minh họa lỗi và rollback trong môi trường test.
            throw new IllegalStateException("Simulated failure after unbind");
        }

        // Các thao tác LDAP khác của cùng transaction có thể ở đây.
        // Khi method thành công, transaction manager commit:
        // entry ở DN tạm sẽ bị xóa.
    }
}
```

### 10.1. Khi method thành công

```text
Gọi: removeUser("lan", false)

Trước:     uid=lan,ou=people tồn tại
Trong TX:  uid=lan chuyển sang ou=tx-staging
Commit:    unbind entry tạm
Sau:       uid=lan không còn tại DN gốc
            entry tạm cũng không còn
```

### 10.2. Khi method ném RuntimeException

```text
Gọi: removeUser("lan", true)

Trước:      uid=lan,ou=people tồn tại
Trong TX:   uid=lan chuyển sang ou=tx-staging
Exception:  IllegalStateException
Rollback:   rename entry tạm về uid=lan,ou=people
Sau:        uid=lan trở lại nếu rollback thành công
```

**Điều kiện quan trọng:** đây là kỳ vọng trong **môi trường ổn định**. Khi kết nối đứt, server từ chối rename ngược hoặc có client khác chiếm lại DN gốc, rollback có thể thất bại. Đừng ghi log “rollback thành công” chỉ vì Java method ném exception.

### 10.3. Những trường hợp @Transactional không bảo vệ

| Tình huống | Hậu quả |
| --- | --- |
| Gọi `this.removeUser(...)` từ method cùng class | Có thể bypass Spring AOP proxy |
| Template không dùng `TransactionAwareContextSourceProxy` | Không có interception để ghi nhận thao tác bù trừ |
| `@Transactional` không chỉ định đúng manager khi có nhiều manager | Dùng sai transaction manager |
| Lỗi bị catch và nuốt trong service | Transaction có thể commit vì method trả về bình thường |
| Thread mới chạy thao tác LDAP nhưng không truyền transaction context | Có thể thao tác ngoài transaction hiện hành |
| Chạy hai LDAP directory độc lập trong cùng method | Không tự có rollback/atomicity chung giữa hai server |
| Thao tác ngoài danh sách được Spring LDAP intercept | Không thể mặc định được bù trừ bởi manager |
| Lỗi xảy ra sau khi commit đã bắt đầu dọn DN tạm | Có thể không khôi phục hoàn chỉnh; cần đối soát |

Spring transaction mặc định rollback trên **unchecked exceptions** (`RuntimeException`/`Error`); với checked exceptions, cần cấu hình rollback rules phù hợp. Khi thử nghiệm, dùng RuntimeException có chủ đích để thấy rõ ranh giới.

## 11. “Đổi tên tạm thời” không đồng nghĩa “đổi tên nghiệp vụ”

Hai lệnh sau có mục đích khác nhau:

```java
ldapTemplate.rename(oldDn, newDn); // Modify DN nghiệp vụ.
ldapTemplate.unbind(oldDn);         // Xóa entry nghiệp vụ.
```

Trong transaction manager:

- `rename(oldDn, newDn)` là **một thao tác đổi DN thực sự**. Nếu rollback, manager có thể rename ngược.
- `unbind(oldDn)` có thể được **triển khai tạm thời bằng rename**, vì cần giữ nội dung gốc đến lúc commit.
- `rebind(...)` cũng có thể cần DN tạm để giữ bản gốc.

Một audit trail phía LDAP server thấy Modify DN chưa đủ để kết luận code nghiệp vụ gọi `rename`. Cần đối chiếu trace/request, bean/config và trạng thái trước/sau.

### 11.1. RDN cũ và các thuộc tính tên

LDAP Modify DN có thể tác động lên các giá trị thuộc tính tạo nên RDN, tùy request `deleteoldrdn` và hành vi server. Ví dụ đổi `uid=lan` sang `uid=lan_temp` có thể làm tập giá trị `uid` trên entry thay đổi theo quy tắc protocol/server.

Do đó, “giữ nguyên entry bằng cách đổi DN” **không có nghĩa mọi thuộc tính và tham chiếu đều bất biến bit-for-bit**. Cần xác minh:

- Giá trị `uid`, `cn` hoặc naming attribute sau round-trip.
- Operational attributes như `modifyTimestamp` / `modifiersName`.
- Group membership `member` / `uniqueMember` hoặc tham chiếu `manager`.
- Server-side plugins tự động cập nhật tham chiếu khi DN đổi.

Đây cũng là lý do không thể dùng suffix-renaming tạm **bừa bãi** cho entity đang dùng làm khóa phân quyền hoặc ràng buộc định danh bên ngoài.

## 12. Sự cố thường gặp khi dùng DN tạm

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `NameNotFoundException` khi chuyển sang subtree tạm | Parent `ou=tx-staging` chưa tồn tại hoặc base DN sai | Seed OU đúng trước khi dùng, kiểm tra DN tương đối |
| `NameAlreadyBoundException` / `entryAlreadyExists (68)` | DN tạm trùng tên | Kiểm tra collision và strategy; không xóa DN đang tồn tại mù quáng |
| `InsufficientAccessRightsException` / result code 50 | Thiếu quyền move/rename/unbind/rollback | Cấu hình ACL đúng tối thiểu, không dùng admin credential rộng vô cớ |
| `NamingViolationException` / result code 64 | Tên hoặc vị trí mới vi phạm naming rule | Xem schema/objectClass và RDN |
| `ObjectClassViolationException` / result code 65 | Attribute/RDN mới không được schema cho phép | Kiểm tra objectClass và naming attribute |
| `affectsMultipleDSAs (71)` | Move vượt DSA/naming context hỗ trợ | Đặt staging subtree cùng naming context được hỗ trợ |
| Search vẫn trả user “đã xóa” | Dùng Default, entry tạm còn ở `ou=people` | Dùng subtree riêng hoặc điều chỉnh search/ACL |
| Xóa OU cha thất bại vì còn child | Default giữ child tạm trong cây | Dùng DifferentSubtree trong workflow test phù hợp |
| Rollback không khôi phục entry | Mất mạng, DN gốc bị chiếm, ACL đổi hoặc entry tạm bị sửa/xóa | Đối soát bằng DN/ID, alert và quy trình khôi phục có kiểm soát |
| Temp subtree còn nhiều entry sau crash | Transaction chưa commit/rollback hoàn chỉnh | Có job inventory/reconciliation, không xóa tự động khi chưa điều tra |
| Hai instance ứng dụng đụng DN tạm | Chiến lược đặt tên không duy nhất toàn cục | Thiết kế identity/collision handling, kiểm thử concurrent |
| Log/trace rò rỉ thông tin user | Ghi full DN, attrs, mật khẩu hoặc dữ liệu gốc | Log source/operation/result code và correlation ID, áp dụng redaction |
| Dữ liệu group không nhất quán sau rename | Referential integrity plugin thay DN tham chiếu | Kiểm thử đường rename/rollback với group thật |
| Application đánh dấu xóa hoàn tất quá sớm | Gửi event trước khi commit dọn entry tạm | Phát sự kiện theo trạng thái xác minh, có outbox/reconcile nếu cần |

**Mã lỗi LDAP** là dấu hiệu tham khảo; Spring LDAP có thể chuyển sang exception tương ứng, và hành vi/diagnostic text phụ thuộc server. Không dùng riêng một mã lỗi để tự động xóa entry tạm.

## 13. Vì sao không nên tự dọn entry tạm một cách mù quáng?

Sau một lần crash, có thể nhìn thấy:

```text
ou=tx-staging,dc=example,dc=org
├── uid=lan17
├── uid=minh18
└── uid=mai19
```

Không có bảo đảm rằng:

- Mọi entry tạm đều “rác” sau N phút.
- Mọi entry đã được commit xong.
- Tên có hậu tố số luôn do cùng một version của ứng dụng sinh ra.
- Chỉ cần tìm `uid=*17` là biết transaction nào đã tạo entry.

Một quy trình reconciliation an toàn nên:

1. Xác định **nguồn logic, DN, loại operation và thời điểm** bằng log/trace/audit có quyền truy cập.
2. Kiểm tra entry tại DN tạm **và** DN gốc, cùng định danh bền vững nếu server cung cấp (ví dụ `entryUUID` hoặc `objectGUID`).
3. Xem transaction/request nào đã bắt đầu, có commit hay rollback đã được xác nhận không.
4. Kiểm tra group memberships, tham chiếu DN và side effect ở các hệ thống khác.
5. Dừng hoặc hạn chế write cạnh tranh trong lúc phục hồi.
6. Quyết định **khôi phục**, **hoàn tất xóa**, hoặc **cách ly để điều tra** theo quy trình được phê duyệt.
7. Ghi lại audit sự kiện khôi phục và kiểm chứng sau thao tác.

Đừng cho một cron job tự `ldapTemplate.unbind(...)` toàn bộ subtree tạm theo TTL khi chưa có quy tắc xác định tính sở hữu. Lỗi dọn dẹp có thể **phá hủy bản gốc duy nhất** của một entry được giữ lại nhằm rollback.

## 14. Tính nhất quán khi nhiều client cùng thao tác

Hãy xét một tình huống:

```text
T0: App A bắt đầu xóa uid=lan.
T1: App A rename uid=lan -> uid=lan_temp.
T2: App B thấy DN gốc không tồn tại, tạo uid=lan mới.
T3: App A phát sinh lỗi và muốn rollback.
T4: Rename uid=lan_temp -> uid=lan thất bại vì DN đích đã có.
```

Đây là một ví dụ **race condition** do thiếu transaction isolation. Ngay cả khi hai ứng dụng dùng `ContextSourceTransactionManager`, LDAP server vẫn không biết chúng là hai transaction phải lock chung.

Biện pháp giảm rủi ro:

- Định danh entry bằng một khóa ổn định nếu directory hỗ trợ; DN có thể thay đổi.
- Đặt lock ở tầng ứng dụng/hệ thống điều phối **nếu phù hợp**, nhưng lock ngoài LDAP cũng cần xử lý crash và hết hạn.
- Dùng kiểm tra trạng thái trước/sau operation và các LDAP assertion controls nếu server hỗ trợ.
- Giảm thời gian giữ transaction; tránh gọi HTTP chậm bên trong.
- Thiết kế xử lý conflict và manual remediation cho thao tác không thể bù trừ.

**Không xem một tên tạm unique là cơ chế isolation**. Nó chỉ giảm va chạm ở chỗ lưu entry; không ngăn bên thứ ba sửa cùng entry hoặc tái tạo DN cũ.

## 15. Quyền, bảo mật và vận hành subtree tạm

Vì entry tạm có thể chứa dữ liệu người dùng đầy đủ, ví dụ email, ảnh, thông tin nhóm, chứng chỉ hoặc attributes nhạy cảm, subtree tạm phải được coi như **dữ liệu sản xuất**, không phải “thùng rác công khai”.

| Nguy cơ | Giảm thiểu |
| --- | --- |
| Anonymous user đọc được staging OU | ACL chỉ cho service account/quản trị được phép; không cho public search |
| Service account có quá nhiều quyền | Cấp quyền rename/move/unbind đúng nguồn và đích; kiểm soát audit |
| Staging OU nằm ngoài domain quản lý | Đặt đúng naming context/DSA, không tạo trên server khác |
| Chứng chỉ TLS giả mạo | LDAPS/StartTLS với CA/truststore và hostname verification hợp lệ |
| Log chứa DN nhạy cảm | Dùng định danh correlation được quản lý, operation type, server alias và mã lỗi |
| Đối soát tự động làm mất entry | Yêu cầu quyết định/approval cho các trường hợp không xác định |
| Group membership bị thay đổi ngoài ý muốn | Test referential integrity plugin, các DN tham chiếu và ACL |
| Tính năng xóa/rename bị lạm dụng | Kiểm tra authorization nghiệp vụ trước khi gọi `LdapTemplate.unbind` |

Không dùng một LDAP admin credential có quyền không giới hạn chỉ vì `DifferentSubtreeTempEntryRenamingStrategy` cần move. Hãy thiết kế OU tạm và ACL hợp lý để vừa thực thi được compensation vừa tránh tăng quyền quá mức.

## 16. Kiểm thử unit cho các strategy

Unit test có thể xác minh **cấu trúc DN tạm** mà không cần LDAP server.

### 16.1. Default strategy thêm suffix

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.springframework.ldap.transaction.compensating.support.DefaultTempEntryRenamingStrategy;

DefaultTempEntryRenamingStrategy strategy =
        new DefaultTempEntryRenamingStrategy();

Name original = new LdapName("uid=lan,ou=people");
Name temporary = strategy.getTemporaryName(original);

if (!temporary.equals(new LdapName("uid=lan_temp,ou=people"))) {
    throw new AssertionError("Unexpected default temporary DN");
}

if (!original.equals(new LdapName("uid=lan,ou=people"))) {
    throw new AssertionError("Original DN was modified");
}
```

Kiểm thử này giúp phát hiện sai suffix và kiểm tra tham số nguồn không bị thay đổi. Nó **không chứng minh** server cho phép rename sang DN đó.

### 16.2. DifferentSubtree strategy đặt entry ra khỏi source OU

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.springframework.ldap.transaction.compensating.support.DifferentSubtreeTempEntryRenamingStrategy;

DifferentSubtreeTempEntryRenamingStrategy strategy =
        new DifferentSubtreeTempEntryRenamingStrategy("ou=tx-staging");

Name original = new LdapName("uid=lan,ou=people");
Name temporary = strategy.getTemporaryName(original);

Name parent = temporary.getPrefix(temporary.size() - 1);

if (!parent.equals(new LdapName("ou=tx-staging"))) {
    throw new AssertionError("Temporary DN is outside staging subtree");
}
if (temporary.equals(original)) {
    throw new AssertionError("Temporary DN must differ from source");
}
```

Trong JNDI `LdapName`, RDN bên phải nhất có index 0, leaf ở `size() - 1`; do đó `getPrefix(size() - 1)` lấy **parent DN**, không phải chuỗi bên trái.

Test **không so cứng suffix số** vì strategy có thể dùng sequence; điều cần xác minh là tên tạm có parent đúng và không bằng tên nguồn. Nếu app yêu cầu uniqueness mạnh khi chạy nhiều instance, cần thêm integration test cạnh tranh.

## 17. Integration test cho commit và rollback trên directory test

Để xác minh end-to-end, cần một **LDAP server test** cho phép Modify DN và ACL liên quan. Một unit test `getTemporaryName` **không đủ**.

### 17.1. Chuẩn bị DIT

```text
dc=example,dc=org
├── ou=people
│   └── uid=lan
├── ou=groups
│   └── cn=developers
└── ou=tx-staging
```

Tạo dữ liệu giả, với `ou=tx-staging` được tạo **trước khi bắt đầu transaction**. Bind account test phải có quyền đọc/rename/xóa entry ở nhánh phù hợp.

### 17.2. Các trường hợp bắt buộc

| Case | Thao tác | Kiểm tra sau cùng |
| --- | --- | --- |
| Commit `unbind` | `removeUser("lan", false)` | DN gốc không còn; không còn entry tạm của Lan |
| Rollback `unbind` | `removeUser("lan", true)` | DN gốc khôi phục; không còn entry tạm tương ứng |
| Parent tạm thiếu | Xóa OU staging **trong test fixture**, không trong transaction | Có lỗi rõ; không đánh dấu delete hoàn tất |
| ACL move bị từ chối | Dùng service principal thiếu quyền | Không mất entry gốc hoặc phải phát hiện trạng thái dở dang |
| DN tạm trùng | Seed trùng tên theo strategy phù hợp | Có tín hiệu collision; không overwrite entry khác |
| Mất kết nối giữa thao tác | Mô phỏng server/network failure có kiểm soát | Báo trạng thái không xác định; yêu cầu reconciliation |
| Concurrent transaction | Hai worker cùng tác động một DN | Nhận diện conflict, không giả định rollback chắc chắn |
| Search với Default | Query dưới `ou=people` trong khi entry đang staged | Thấy rủi ro entry tạm còn nằm trong subtree |
| Search với DifferentSubtree | Query dưới `ou=people` trong khi entry staged | Entry tạm không nằm trong subtree business |
| Xóa recursive | Có cây nhiều tầng | Verify strategy phù hợp, không fail vì entry con tạm còn lại |
| Rebind commit/rollback | Thay attributes trong transaction | Đọc lại entry/attributes và so với dữ liệu trước |
| DN tham chiếu | Group có `member: uid=lan,...` | Verify plugin và membership sau rename/rollback |

**Quan trọng:** không thể quan sát được trạng thái “đang staged” chỉ bằng cách gọi hàm transactional rồi đợi nó trả về; phải dùng test hook hoặc phối hợp thread có kiểm soát **trước commit** trong môi trường test. Không chèn `Thread.sleep` dài vào production transaction.

### 17.3. Kiểm tra DN nguồn và staging bằng lookup

Sau khi transaction kết thúc, có thể kiểm tra hai vùng bằng `LdapTemplate.search`/`lookup`. Tuy nhiên, strategy DifferentSubtree có thể thêm suffix số, nên **không dựa vào phép lookup với một DN tạm đoán trước**. Hãy:

1. Đối chiếu DIT trên directory test trước/sau.
2. Nếu đang kiểm tra trong transaction, ghi lại DN do strategy tính ra ở chính test.
3. Tra cứu staging OU trong phạm vi hẹp, có giới hạn và account test phù hợp.
4. So sánh đúng entry bằng các thuộc tính/ID không nhạy cảm được phép đọc.
5. Khi kiểm thử rollback, đọc lại cả những giá trị tên và DN references dễ bị server plugin thay đổi.

Không bật tự động dọn staging OU ở cuối test nếu một assertion thất bại mà không ghi lại đủ trạng thái để chẩn đoán; việc dọn fixture phải chắc chắn chỉ diễn ra trên directory test.

## 18. Bài thực hành

### Bài 1. Dự đoán DN tạm

Cho:

```text
original = cn=Backend Team,ou=groups,dc=example,dc=org
strategy = DefaultTempEntryRenamingStrategy
suffix   = _temp
```

**Câu hỏi:** DN tạm là gì và có còn nằm trong `ou=groups` không?

*Đáp án gợi ý:* `cn=Backend Team_temp,ou=groups,dc=example,dc=org`; **có**, vì chỉ leaf RDN đổi.

### Bài 2. Vì sao bỏ suffix không đủ?

Code search `(objectClass=groupOfNames)` dưới `ou=groups` vẫn thấy group đã unbind tạm. Tại sao filter `(cn=*_temp)` không phải cách bảo vệ hoàn chỉnh?

*Đáp án gợi ý:* Search có thể thấy entry tạm; suffix cố định có thể trùng tên thật và không áp dụng cho mọi strategy. Thiết kế subtree tạm riêng cùng ACL/base đúng thường rõ ràng hơn.

### Bài 3. Chọn strategy cho recursive delete

Một OU cần xóa cùng các entry con trong giao dịch bù trừ. Tại sao Default có thể làm xóa OU cha thất bại?

*Đáp án gợi ý:* Những entry con đã “xóa” vẫn tồn tại dưới cùng OU với tên tạm, nên OU cha chưa rỗng. DifferentSubtree di chuyển các entry con ra ngoài cây nguồn, nhưng vẫn cần test hỗ trợ Modify DN/ACL/server.

### Bài 4. Phân biệt manager và proxy

Một bean transaction manager nhận `TransactionAwareContextSourceProxy`, còn `LdapTemplate` lại nhận thẳng `LdapContextSource` gốc. Sai ở đâu?

*Đáp án gợi ý:* Wiring đảo vai trò. Manager phải nhận **target ContextSource**; template nhận **transaction-aware proxy** được bọc quanh cùng target.

### Bài 5. Commit và rollback khác nhau ra sao?

Sau `ldapTemplate.unbind(dn)` trong transaction, khi nào server thực sự nhận lệnh Delete cho entry ở DN tạm?

*Đáp án gợi ý:* Trong **pha commit**. Ở pha chuẩn bị Spring LDAP dùng Rename; rollback cố Rename về DN ban đầu.

### Bài 6. Rollback sau mất mạng

App A đổi `uid=lan` sang staging, rồi mất kết nối trước khi rollback. Có thể trả HTTP “đã hoàn tác” ngay không?

*Đáp án gợi ý:* Không. Phải xem trạng thái không xác định, phát cảnh báo và đối soát dữ liệu thực tế.

### Bài 7. Định danh bền vững

Vì sao không chỉ dựa vào `uid=lan_temp` để nhận dạng entry cần phục hồi?

*Đáp án gợi ý:* DN là tên có thể đổi, suffix có thể collision, client khác có thể tạo DN trùng. Cần kết hợp transaction audit và định danh ổn định nếu server hỗ trợ, cùng kiểm tra nội dung/ACL.

### Bài 8. Quyền trên staging subtree

Tài khoản nghiệp vụ có quyền delete dưới `ou=people` nhưng không có quyền move sang `ou=tx-staging`. Kết quả gì có thể xảy ra?

*Đáp án gợi ý:* Bước chuẩn bị rename thất bại dù một lệnh delete bình thường có thể thành công. Cần thiết kế ACL tối thiểu đúng cho cả move, rollback và commit, không mở quyền toàn cây.

## 19. Ghi nhớ

- **`TempEntryRenamingStrategy`** thuộc Spring LDAP, có phương thức **`Name getTemporaryName(Name originalName)`**; nó **chỉ tính DN tạm**, không tự rename LDAP entry.
- Cơ chế bù trừ cho **`unbind`/`rebind`** dùng **rename tạm để giữ entry gốc**, rồi khi commit mới hoàn tất delete/replace; rollback cố đổi tên về DN ban đầu.
- **`DefaultTempEntryRenamingStrategy`** thêm hậu tố **`_temp`** (có thể tùy chỉnh) vào leaf RDN, giữ entry trong **cùng subtree**, có rủi ro lọt vào search hoặc cản xóa cây.
- **`DifferentSubtreeTempEntryRenamingStrategy`** chuyển entry sang một **subtree khác đã tồn tại**, phù hợp hơn khi cần loại entry tạm khỏi search ở nhánh nghiệp vụ. Strategy có thể thêm hậu tố số nhưng **không cam kết uniqueness tuyệt đối**.
- Dùng **`ContextSourceTransactionManager(target)`** cùng **`TransactionAwareContextSourceProxy(target)`** cho `LdapTemplate`; xác minh đúng bean và `@Transactional(transactionManager = "ldapTxManager")`.
- Đây là **client-side compensating transaction**, **không phải XA hay transaction ACID đa thao tác được server bảo đảm**. Không có isolation; lỗi mạng/cạnh tranh/ACL có thể khiến rollback thất bại.
- Khi có staging OU, cần **naming context, schema, ACL, TLS, giám sát và reconciliation**. Tuyệt đối không tự dọn toàn bộ staging như “rác” nếu chưa xác minh trạng thái giao dịch.
- Kiểm thử đầy đủ **commit, rollback, collision, xóa subtree, quyền, lỗi mạng, concurrent writes và tham chiếu DN** với directory test trước khi triển khai.

**Tài liệu tham khảo chính thức:**

- [Spring LDAP — Transaction Support](https://docs.spring.io/spring-ldap/reference/transaction-support.html): giao dịch bù trừ, vòng đời các operation và renaming strategies.
- [Spring LDAP Javadoc — TempEntryRenamingStrategy](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/transaction/compensating/TempEntryRenamingStrategy.html): contract `getTemporaryName(Name)`.
- [Spring LDAP Javadoc — DefaultTempEntryRenamingStrategy](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/transaction/compensating/support/DefaultTempEntryRenamingStrategy.html): suffix `_temp` và caveat tìm kiếm entry tạm.
- [Spring LDAP Javadoc — DifferentSubtreeTempEntryRenamingStrategy](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/transaction/compensating/support/DifferentSubtreeTempEntryRenamingStrategy.html): subtree staging, constructor và suffix sequence.
- [Spring LDAP Javadoc — ContextSourceTransactionManager](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/transaction/compensating/manager/ContextSourceTransactionManager.html): manager, setRenamingStrategy và giới hạn rollback/isolation.
- [Spring LDAP Javadoc — TransactionAwareContextSourceProxy](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/transaction/compensating/manager/TransactionAwareContextSourceProxy.html): interception của DirContext.
- [Spring LDAP Javadoc — UnbindOperationExecutor](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/transaction/compensating/UnbindOperationExecutor.html): rename trước, delete khi commit.
- [Spring LDAP Javadoc — RebindOperationExecutor](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/transaction/compensating/RebindOperationExecutor.html): thay thế entry bằng cơ chế tạm.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và ODM.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): LDAP Modify DN/Delete và result codes.
- [RFC 4514 — Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): RDN, DN và escaping.
- [RFC 5805 — LDAP Transactions (Experimental)](https://www.rfc-editor.org/rfc/rfc5805): extension về transaction, không đồng nhất với client-side compensation.
