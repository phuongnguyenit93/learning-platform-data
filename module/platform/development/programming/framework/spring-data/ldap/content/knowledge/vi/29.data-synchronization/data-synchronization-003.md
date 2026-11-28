# Nhập hoặc xuất dữ liệu LDIF theo phạm vi được phép

Trong một dự án **Spring Data LDAP**, dữ liệu danh tính và nhóm thường được truy vấn qua `LdapRepository` hoặc `LdapTemplate`. Tuy nhiên, khi cần khởi tạo directory thử nghiệm, di chuyển một tập entry, đối soát dữ liệu hoặc bàn giao bản sao phục vụ kiểm thử, định dạng **LDAP Data Interchange Format (LDIF)** thường thuận tiện hơn việc gọi từng phương thức CRUD thủ công.

Vấn đề quan trọng nhất không phải chỉ là xuất được file hay nhập được entry, mà là **chỉ tác động tới đúng phạm vi đã được cho phép**: đúng directory, đúng naming context/base DN, đúng nhánh OU, đúng đối tượng, đúng thuộc tính và đúng loại thao tác. Một file LDIF có thể chứa dữ liệu cá nhân hoặc yêu cầu xóa, đổi tên, thay thế thuộc tính; xử lý sai có thể làm lộ thông tin hoặc thay đổi hàng loạt tài khoản.

Bài thuộc chương **Đồng bộ dữ liệu** này giúp bạn đọc cấu trúc LDIF, lập hợp đồng xuất/nhập, dùng các công cụ LDAP phù hợp, phân biệt bản chụp với change record, áp dụng kiểm tra an toàn trước khi ghi, liên hệ với Spring Data LDAP, và xác minh kết quả trên directory thử nghiệm.

## 1. LDIF là gì? Hai dạng file cần phân biệt

**LDIF** là định dạng văn bản để biểu diễn dữ liệu LDAP (RFC 2849). Hai dạng thường gặp là:

1. **Content LDIF**: mô tả entry bằng `dn` và các cặp `attribute: value`; phù hợp với kết quả export, khởi tạo dữ liệu hoặc nhập **entry mới**.
2. **Change LDIF**: mô tả thao tác thay đổi với `changetype: add`, `modify`, `delete` hoặc `modrdn`/`moddn`; phù hợp với luồng áp dụng thay đổi có kiểm soát.

Đây là một **content LDIF** minh họa:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
givenName: An
mail: an.nguyen@example.org

dn: uid=u1002,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1002
cn: Binh Tran
sn: Tran
givenName: Binh
mail: binh.tran@example.org
```

Mỗi bản ghi bắt đầu bằng **`dn:`**; một dòng trống phân tách hai entry. Một thuộc tính **đa trị** được biểu diễn bằng nhiều dòng cùng tên, ví dụ nhiều `objectClass:` hoặc nhiều `member:`. LDIF không dùng cú pháp JSON/CSV: cấu trúc phân cấp nằm ở DN, không ở vị trí dòng trong file.

**Change LDIF** khác về ý nghĩa:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
changetype: modify
replace: mail
mail: an.new@example.org
-
```

Bản ghi này yêu cầu **thay** thuộc tính `mail` của một entry đã tồn tại. Nó không phải là một bản chụp entry đầy đủ. Các thao tác từ change LDIF chỉ được áp dụng khi có quyền ghi thích hợp và đã kiểm chứng mục tiêu.

| Đặc tính | Content LDIF | Change LDIF |
|---|---|---|
| Ý nghĩa chính | Mô tả trạng thái thuộc tính của entry | Mô tả hành động cần thực hiện |
| Trường đặc trưng | `dn`, `objectClass`, thuộc tính | `dn`, `changetype`, chỉ thị `add`/`replace`/`delete` |
| Trường hợp dùng | Snapshot, khởi tạo entry, xuất dữ liệu | Cập nhật thuộc tính, xóa entry, rename/move |
| Rủi ro khi chạy lại | Tạo entry trùng hoặc lỗi entry đã tồn tại | Thay giá trị, xóa hoặc đổi DN ngoài ý muốn |
| Có bảo đảm tự đồng bộ hai chiều? | Không | Không |

**LDIF là định dạng trao đổi**, không phải công cụ giải quyết xung đột hoặc cơ chế replication. Quyền sở hữu dữ liệu, thứ tự cập nhật và cách xử lý sai lệch vẫn phải được định nghĩa ở tầng nghiệp vụ.

## 2. Các quy tắc cú pháp LDIF cần nắm

Một số chi tiết khiến file trông đúng nhưng không thể nhập hoặc bị biến đổi dữ liệu:

- **DN phải chính xác:** `uid=u1001,ou=people,dc=example,dc=org` khác `uid=u1001,ou=contractors,dc=example,dc=org`. DN thay đổi nếu đổi RDN hoặc di chuyển entry giữa các OU.
- **Dòng trống tách bản ghi:** thiếu dòng trống có thể làm hai entry bị đọc như một bản ghi.
- **Thuộc tính đa trị:** lặp dòng thuộc tính để biểu diễn nhiều giá trị, không tự nối bằng dấu phẩy.
- **Giá trị nhị phân hoặc không an toàn để ghi trực tiếp:** LDIF hỗ trợ cú pháp `attribute:: <base64>`; công cụ xuất chuẩn sẽ mã hóa khi cần, ví dụ với dữ liệu nhị phân, ký tự đặc biệt ở đầu giá trị hoặc dữ liệu UTF-8 cần mã hóa.
- **Dòng dài có thể được gấp:** dòng tiếp theo bắt đầu bằng một dấu cách là phần nối của dòng trước theo quy tắc LDIF; không tùy tiện cắt bằng editor.
- **Đọc/ghi UTF-8:** dùng parser và serializer LDIF phù hợp, không tự ghi thô các giá trị LDAP không rõ encoding.
- **Cú pháp `attribute:< <URL>`:** có thể tham chiếu giá trị từ URL; không tự động cho phép parser tải nội dung từ URL không đáng tin. Tùy công cụ, hãy chặn hoặc kiểm soát kiểu nguồn giá trị này.
- **Thuộc tính và `objectClass`:** entry nhập phải đáp ứng các thuộc tính bắt buộc (MUST), được phép (MAY), kiểu dữ liệu và matching rule của schema server đích.

Ví dụ một giá trị ở dạng base64 trong LDIF:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
cn:: QW4gTmd1eWVu
```

Trong ví dụ, `cn::` biểu thị giá trị được mã hóa base64; việc dùng `::` **không có nghĩa giá trị gốc đã được mã hóa bảo mật**. Base64 chỉ là cách biểu diễn dữ liệu, ai đọc được file vẫn có thể giải mã.

## 3. “Phạm vi được phép” gồm những chiều nào?

Một yêu cầu “export tài khoản LDAP” **chưa đủ cụ thể** để thực thi an toàn. Cần ghi nhận phạm vi theo nhiều trục:

| Trục phạm vi | Ví dụ ràng buộc | Vì sao cần |
|---|---|---|
| **Directory endpoint** | Chỉ LDAP test `ldap-stage.example.org` | Tránh đọc/ghi nhầm production hoặc DC khác |
| **Naming context / suffix** | Chỉ `dc=example,dc=org` | Không tự truy cập partition khác |
| **Base DN** | `ou=people,dc=example,dc=org` | Chỉ tập đối tượng nằm trong vùng được duyệt |
| **Search scope** | `base`, `one`, hoặc `sub` | Giới hạn độ sâu tìm kiếm |
| **LDAP filter** | Chỉ `inetOrgPerson` với UID đã được duyệt | Không xuất cả OU khi chỉ cần một người |
| **Thuộc tính** | `dn,objectClass,uid,cn,sn,givenName,mail` | Tránh xuất mật khẩu, secret hoặc thông tin không cần |
| **Loại thao tác** | Đọc/xuất; hoặc chỉ cho phép thêm mới | Ngăn `modify`/`delete` ngoài thẩm quyền |
| **Số lượng** | Tối đa 20 entry đã duyệt | Giới hạn phạm vi nếu filter sai |
| **Thời gian và người thực hiện** | Cửa sổ bảo trì, tài khoản dịch vụ riêng | Kiểm soát vòng đời và truy vết |
| **Đích nhận file** | Kho lưu nội bộ mã hóa, thời hạn lưu rõ ràng | Bảo vệ dữ liệu sau khi rời LDAP |

**Base DN và filter không phải là lớp bảo mật duy nhất.** Tài khoản bind phải được cấp **ACL tối thiểu** phù hợp cả phạm vi entry lẫn thuộc tính. Ứng dụng cũng phải xác minh rằng người dùng yêu cầu thao tác có quyền nghiệp vụ tương ứng. Ngay cả khi tài khoản LDAP có quyền đọc toàn domain, một nghiệp vụ xuất một nhóm nhỏ vẫn phải tự giới hạn truy vấn.

Một mẫu hợp đồng có thể mô tả:

```text
Nguồn:          ldap-stage.example.org:636 (LDAPS)
Naming context: dc=example,dc=org
Base DN:        ou=people,dc=example,dc=org
Scope:          sub
Filter:         (&(objectClass=inetOrgPerson)(uid=u1001))
Attributes:     dn, objectClass, uid, cn, sn, givenName, mail
Quyền:          export read-only; không bao gồm password/secret
Số bản ghi:     dự kiến đúng 1; nếu 0 hoặc >1 thì dừng và điều tra
Đích:          môi trường thử nghiệm có schema tương thích
Lưu file:       vị trí truy cập hạn chế; xóa khi hết hạn
```

Trước khi bắt đầu, đối chiếu danh sách DN/số bản ghi với yêu cầu đã được phê duyệt. Với thao tác ghi, cần có bản chụp/khả năng khôi phục phù hợp, kế hoạch rollback và sự chấp thuận của chủ sở hữu directory.

## 4. Chọn search base và scope để tránh xuất quá rộng

Giả sử trong directory tồn tại:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=u1001
│   └── uid=u1002
├── ou=groups
│   └── cn=developers
└── ou=service-accounts
    └── cn=svc-app
```

Các **scope** của LDAP:

| Scope | Tác dụng | Nếu base là `ou=people,dc=example,dc=org` |
|---|---|---|
| `base` | Chỉ entry ở base | Chỉ entry OU `people` |
| `one` | Chỉ các entry con trực tiếp | `uid=u1001`, `uid=u1002` |
| `sub` | Base và toàn bộ cây con | OU `people` và các entry phía dưới, kể cả OU con |

Ngay cả khi filter đã đủ chặt, chọn base DN rộng như `dc=example,dc=org` có thể khiến truy vấn đi qua nhóm hoặc tài khoản dịch vụ. Ngược lại, base `ou=people` không tự nhìn thấy `ou=groups` (nằm ở nhánh ngang). Trường hợp entry nằm ở naming context khác có thể cần endpoint/referral riêng; **không suy ra subtree search sẽ tự động vượt qua mọi partition**.

Nếu đã biết chính xác DN và được phép đọc đúng một entry, dùng **base-object search** hoặc `LdapTemplate.lookup` thay cho tìm trên toàn cây. Nếu chỉ có UID hoặc email mà không biết DN hiện tại, sử dụng search filter an toàn trong OU/NC đã thống nhất.

## 5. Xuất LDIF bằng công cụ LDAP theo phạm vi hẹp

Các lệnh `ldapsearch` dưới đây minh họa **cú pháp công cụ OpenLDAP CLI** trong shell kiểu POSIX, không được thực thi trong bài. Tên host, bind DN, dữ liệu và file là ví dụ; hãy xác nhận hỗ trợ CLI và cấu hình TLS trên máy chạy thật.

### 5.1. Xuất đúng một entry bằng DN

```bash
ldapsearch -LLL -x \
  -H ldaps://ldap-stage.example.org:636 \
  -D 'cn=svc-export,ou=service-accounts,dc=example,dc=org' -W \
  -b 'uid=u1001,ou=people,dc=example,dc=org' \
  -s base '(objectClass=*)' \
  dn objectClass uid cn sn givenName mail \
  > person-u1001.ldif
```

Ý nghĩa của các tham số:

- `-H`: endpoint LDAP; dùng LDAPS và xác thực chứng chỉ theo trust store/CA.
- `-D`: danh tính bind của tài khoản được phép xuất; `-W` yêu cầu nhập mật khẩu tương tác thay vì đặt trong command line.
- `-b`: DN gốc tìm kiếm; trong ví dụ chính là DN của **một entry**.
- `-s base`: không tìm toàn bộ OU; chỉ đọc entry tại DN được chỉ định.
- `'(objectClass=*)'`: presence filter thường dùng để đọc entry bất kể object class cụ thể.
- Danh sách cuối chỉ lấy các thuộc tính được phép; không dùng `*` cho toàn bộ thuộc tính nếu hợp đồng chỉ duyệt một tập nhỏ.
- `-LLL`: giảm các dòng chú thích/metadata trong output LDIF của `ldapsearch`.

**Không mặc định xuất `userPassword`, `unicodePwd`, `objectGUID`, ACL, token hoặc thuộc tính nhạy cảm.** Một số thuộc tính vận hành/binary cần cú pháp và quyền đặc thù; giá trị có thể không đọc được ngay cả khi entry vẫn tồn tại.

### 5.2. Xuất một tập entry đã được duyệt trong OU

Ví dụ quy tắc cho phép đọc tất cả `inetOrgPerson` trong OU thử nghiệm `people`, không bao gồm groups:

```bash
ldapsearch -LLL -x \
  -H ldaps://ldap-stage.example.org:636 \
  -D 'cn=svc-export,ou=service-accounts,dc=example,dc=org' -W \
  -b 'ou=people,dc=example,dc=org' \
  -s sub '(objectClass=inetOrgPerson)' \
  dn objectClass uid cn sn givenName mail \
  > approved-people.ldif
```

Đây là **truy vấn rộng hơn** ví dụ 5.1; chỉ chạy khi danh sách/loại tài khoản trong OU đã được cho phép đầy đủ. Muốn hẹp hơn, thêm điều kiện equality hoặc danh sách UID đã duyệt bằng filter builder phù hợp. **Không ghép LDAP filter thô từ input không tin cậy.**

Nếu lượng dữ liệu lớn và server hỗ trợ **Simple Paged Results Control**, một số phiên bản `ldapsearch` hỗ trợ tùy chọn:

```bash
# Ví dụ cú pháp OpenLDAP CLI; phải kiểm tra server hỗ trợ control.
ldapsearch -LLL -x \
  -H ldaps://ldap-stage.example.org:636 \
  -D 'cn=svc-export,ou=service-accounts,dc=example,dc=org' -W \
  -E pr=200/noprompt \
  -b 'ou=people,dc=example,dc=org' -s sub \
  '(objectClass=inetOrgPerson)' \
  dn objectClass uid cn sn givenName mail \
  > approved-people-paged.ldif
```

Paging giúp lấy nhiều trang kết quả khi được directory hỗ trợ, nhưng **không vượt qua ACL**, không làm filter an toàn hơn và không bảo đảm snapshot nhất quán nếu dữ liệu thay đổi trong lúc export. Không coi một lệnh kết thúc thành công là đủ để khẳng định đã xuất hết dữ liệu nếu có size limit, time limit, lỗi referral hoặc cảnh báo trên stderr. Cần kiểm tra exit code, log, số bản ghi và giới hạn server.

### 5.3. Xuất nhóm: kiểm soát thuộc tính đa trị

Một group entry có thể có:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=u1001,ou=people,dc=example,dc=org
member: uid=u1002,ou=people,dc=example,dc=org
```

`member` là thuộc tính đa trị chứa **DN của các thành viên**, không phải tên UID độc lập với OU. Khi di chuyển dữ liệu sang suffix khác, các DN thành viên có thể cần ánh xạ lại; copy nguyên nhóm mà không kiểm tra các DN tham chiếu có thể tạo thành viên sai hoặc không được server chấp nhận. Schema `groupOfNames` yêu cầu những thuộc tính nhất định; group rỗng có thể cần mô hình khác tùy directory.

## 6. Kiểm tra file đã xuất trước khi chuyển giao hoặc nhập

Không nên mặc định `ldapsearch > file.ldif` đồng nghĩa file đã được phép sử dụng. Ít nhất cần:

1. **Đối chiếu phạm vi:** mọi `dn:` nằm trong base/NC được duyệt; không có `ou=service-accounts` hoặc entry ở ngoài danh sách.
2. **Đếm bản ghi và đối chiếu định danh:** số DN, tập UID, trường hợp trùng hoặc thiếu thuộc tính bắt buộc.
3. **Rà soát thuộc tính:** chỉ có danh sách đã phê duyệt; không có password, khóa, token, secret, thuộc tính vận hành không cần thiết.
4. **Kiểm tra encoding:** không làm hỏng base64, ký tự UTF-8, dấu cách gấp dòng và thuộc tính đa trị.
5. **Kiểm tra độ đầy đủ:** tìm lỗi LDAP, paging, referral, size/time limit và tình trạng export dở.
6. **Đối chiếu schema đích:** `objectClass`, MUST/MAY, cú pháp thuộc tính và ràng buộc khác biệt giữa directory nguồn/đích.
7. **Kiểm soát file:** lưu nơi mã hóa hoặc được bảo vệ truy cập, giới hạn người nhận, ghi nhận checksum, thời hạn lưu và cách hủy sau sử dụng.

Checksum (ví dụ SHA-256) chứng minh hai bản sao file có cùng nội dung trong quá trình bàn giao; nó **không** xác nhận dữ liệu bên trong được phép xuất, không nhạy cảm hoặc chính xác về nghiệp vụ. Không đưa file chứa dữ liệu cá nhân vào kho mã nguồn hoặc artifact CI công khai.

Khi cần xác minh quy mô dữ liệu, đếm bằng parser LDIF hiểu continuation lines thay vì chỉ `grep '^dn:'` một cách thiếu kiểm chứng: LDIF có biểu diễn DN bằng base64 và có những trường hợp đặc thù cần xử lý chuẩn.

## 7. Nhập content LDIF: thêm mới có kiểm soát

Nhập content LDIF thường được dùng để khởi tạo **entry chưa tồn tại** trong directory test hoặc đích được phép. Trước khi import:

- **Đích được xác nhận:** kiểm tra chính xác hostname, chứng chỉ, suffix/NC và OU đích. Không lấy một file export từ production rồi tự ý nhập vào production khác.
- **Parent entry tồn tại:** ví dụ `ou=people,dc=example,dc=org` phải có trước khi thêm `uid=u1001` dưới nó; thường cần nạp dữ liệu cha trước dữ liệu con.
- **Schema tương thích:** giữ các `objectClass` phù hợp, thuộc tính MUST đầy đủ, loại bỏ hoặc chuyển đổi các thuộc tính chỉ server nguồn quản lý.
- **DN không trùng:** nếu đích đã có entry cùng DN, thao tác add thông thường sẽ thất bại với lỗi entry đã tồn tại.
- **ACL được cấp vừa đủ:** tài khoản import cần quyền add trong nhánh đã duyệt, không cần quyền admin toàn directory nếu có thể phân quyền hẹp.

Ví dụ **trong môi trường LDAP thử nghiệm** và file `approved-new-people.ldif` chỉ chứa các entry **mới**:

```bash
ldapadd -x \
  -H ldaps://ldap-stage.example.org:636 \
  -D 'cn=svc-import,ou=service-accounts,dc=example,dc=org' -W \
  -f approved-new-people.ldif
```

`ldapadd` theo cú pháp OpenLDAP CLI thực hiện các **add operation**; không xem đây là lệnh merge tự động với entry cũ. File export có thể phải được **lọc và biến đổi** cho phù hợp directory đích trước khi thêm, nhất là khi có các thuộc tính vận hành hoặc khác biệt schema.

**Điểm chặn trước khi ghi:** trên môi trường staging, lập danh sách DN dự kiến tạo, kiểm tra số bản ghi và quyền, xác nhận từng DN không nằm ngoài OU được cấp phép. Sau khi hoàn tất, lookup lại bằng tài khoản đọc của ứng dụng để xác minh entry và thuộc tính thực sự tồn tại.

## 8. Nhập change LDIF: add, modify, delete, modrdn

Khi cần cập nhật entry đã tồn tại, **không dùng content LDIF như thể là bản sửa đổi tự động**. Hãy tạo change LDIF rõ loại thao tác và phạm vi:

| `changetype` | Công dụng | Rủi ro cần quản lý |
|---|---|---|
| `add` | Tạo entry mới với bộ thuộc tính ban đầu | Trùng DN, sai schema hoặc sai parent |
| `modify` | Thêm/thay/xóa giá trị thuộc tính | Ghi đè dữ liệu do hệ thống khác sở hữu |
| `delete` | Xóa một entry | Mất dữ liệu, tham chiếu và quyền liên quan |
| `modrdn` / `moddn` | Đổi RDN hoặc di chuyển entry tùy hỗ trợ | DN thay đổi, nhóm/tham chiếu cần kiểm tra |

### 8.1. Thay một thuộc tính bằng `modify`

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
changetype: modify
replace: mail
mail: an.new@example.org
-
```

Chỉ `mail` được yêu cầu thay đổi; các thuộc tính không nêu trong record không có nghĩa phải bị xóa. Một record `modify` có thể gồm nhiều thao tác con `add`, `replace`, `delete`, được phân cách bằng dòng `-`; không nhầm `delete: mail` (xóa thuộc tính/giá trị) với `changetype: delete` (xóa **entry**).

### 8.2. Tạo mới bằng `changetype: add`

```ldif
dn: uid=u1003,ou=people,dc=example,dc=org
changetype: add
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1003
cn: Chi Le
sn: Le
```

Với change records như trên, công cụ OpenLDAP thường dùng `ldapmodify`:

```bash
ldapmodify -x \
  -H ldaps://ldap-stage.example.org:636 \
  -D 'cn=svc-import,ou=service-accounts,dc=example,dc=org' -W \
  -f approved-changes.ldif
```

Lệnh chỉ nên dùng khi **file đã được thẩm định**. Một số phiên bản `ldapmodify` có tùy chọn `-n` để hiển thị thao tác mà **không thực hiện ghi**; điều này hữu ích cho việc kiểm tra cấu trúc nhưng **không bảo đảm** ACL, schema và tất cả quy tắc server sẽ chấp nhận khi ghi thật. Kiểm thử tốt nhất vẫn là áp dụng trên directory thử nghiệm tương đồng.

### 8.3. Xóa entry và đổi DN

LDIF có thể biểu diễn xóa một entry:

```ldif
dn: uid=u1003,ou=people,dc=example,dc=org
changetype: delete
```

Hoặc đổi RDN:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
changetype: modrdn
newrdn: uid=u1001-renamed
deleteoldrdn: 1
```

**Hai ví dụ trên chỉ để hiểu cú pháp, không phải thao tác cần chạy mặc định.** Không sinh lệnh `delete` hàng loạt chỉ dựa vào kết quả export thiếu entry: entry có thể không xuất hiện vì filter, ACL, timeout, paging hoặc sai base. Việc đổi DN làm thay đổi các tham chiếu dùng DN; mức độ cập nhật tự động ở nhóm/phần mềm phụ thuộc directory và ứng dụng.

## 9. Chuyển dữ liệu giữa hai suffix hoặc hai loại LDAP server

Giả sử nguồn có DN `uid=u1001,ou=people,dc=old,dc=example`, còn đích phải dùng `uid=u1001,ou=people,dc=new,dc=example`. Thay chữ `old` bằng `new` trong toàn bộ file bằng thao tác thay chuỗi đơn giản **không an toàn**:

- DN có cú pháp escape; thay chuỗi có thể sửa cả giá trị thuộc tính văn bản không phải DN.
- Các thuộc tính nhóm như `member` hoặc `uniqueMember` có thể chứa **DN tham chiếu** cần được chuyển đổi có cấu trúc.
- Các entry có thể tham chiếu đối tượng nằm ngoài vùng chuyển hoặc naming context không được phép.
- Schema đích có thể thiếu `objectClass` hoặc thuộc tính riêng của server nguồn.
- Thuộc tính do server quản lý như `entryUUID`, `creatorsName`, `createTimestamp`, `modifyTimestamp` thường không nên/không thể tái nhập trực tiếp. AD có các thuộc tính riêng như `objectGUID`, `objectSid` và quy trình quản lý password/tài khoản đặc thù.

Quy trình an toàn hơn:

1. Parse file LDIF bằng thư viện đúng chuẩn, **nhận dạng mọi DN và thuộc tính được phép**.
2. Lập bảng ánh xạ chính xác source DN → target DN và kiểm tra không va chạm.
3. Chuyển đổi **các giá trị kiểu DN** (ví dụ member) theo bảng ánh xạ nếu thuộc phạm vi được phép, không sửa text bất kỳ.
4. Loại bỏ thuộc tính vận hành/không tương thích và thêm thuộc tính bắt buộc theo schema đích; không giả định có thể copy mật khẩu giữa sản phẩm.
5. Tạo entry cha trước, rồi entry con, sau đó cập nhật liên kết nhóm khi các target DN đã tồn tại.
6. Kiểm thử bằng tài khoản đích, xác minh số entry, objectClass, thuộc tính và liên kết tham chiếu.

Nếu hai directory dùng những object class khác nhau, việc chuyển đổi có thể cần **định nghĩa mapping nghiệp vụ** thay vì giữ nguyên LDIF đầu vào. Một bản xuất LDIF cũng không tự mang theo đầy đủ chính sách ACL, trạng thái mật khẩu, index, replication, certificate hoặc cấu hình server.

## 10. Liên hệ với Spring Data LDAP: repository, LdapTemplate và LDIF

**Spring Data LDAP** giúp ánh xạ entry phân cấp sang Java object qua ODM (`@Entry`, `@Id`, `@Attribute`) và tạo repository truy vấn/CRUD. **`LdapTemplate`** cung cấp cách thao tác cụ thể hơn như search, lookup, bind, modify, rename và unbind. Tuy nhiên, **repository hoặc `LdapTemplate` không nên bị coi là công cụ import/export LDIF hoàn chỉnh**: xử lý cú pháp LDIF, base64, continuation lines, change records, thứ tự import và kiểm tra phạm vi cần thành phần riêng hoặc CLI chuyên dụng.

Ví dụ một entity đọc từ LDAP:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(base = "ou=people", objectClasses = {"inetOrgPerson"})
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    public DirectoryPerson() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) { this.commonName = commonName; }
    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }
}
```

Với base DN ở `LdapContextSource` là `dc=example,dc=org`, ứng dụng có thể **đọc dữ liệu đầu vào cho một bản xuất được kiểm soát** bằng `LdapTemplate`:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class ApprovedPersonReader {
    private final LdapTemplate ldapTemplate;

    public record PersonSummary(String uid, String cn, String sn) {}

    public ApprovedPersonReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // approvedUid đã được kiểm tra với danh sách được phép ở tầng nghiệp vụ.
    public List<PersonSummary> readApprovedPerson(String approvedUid) {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .attributes("uid", "cn", "sn")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(approvedUid);

        AttributesMapper<PersonSummary> mapper = attrs ->
                new PersonSummary(
                        (String) attrs.get("uid").get(),
                        (String) attrs.get("cn").get(),
                        (String) attrs.get("sn").get());

        return ldapTemplate.search(ldapQuery, mapper);
    }
}
```

Đoạn code **chỉ minh họa đọc dữ liệu đã giới hạn**, chưa phải chức năng xuất LDIF: `PersonSummary` chưa chứa DN đầy đủ, `objectClass` và toàn bộ thuộc tính cần thiết để tạo entry. Nếu thực sự xuất LDIF bằng Java, cần:

- Lấy đúng **DN đầy đủ** cho từng entry, dựa trên context/base một cách chắc chắn.
- Lấy chỉ các thuộc tính theo allowlist, giữ đúng giá trị binary và đa trị.
- Dùng **LDIF writer/serializer phù hợp** để mã hóa, gấp dòng và biểu diễn entry chuẩn, thay vì tự nối chuỗi `"dn: ...\n"`.
- Kiểm tra danh sách DN, số bản ghi và xác nhận file đã tạo không vượt phạm vi.

Khi **nhập LDIF bằng Java**, dùng parser chuẩn để đọc records, xác thực DN/thuộc tính và chuyển từng record thành thao tác `LdapTemplate` phù hợp. Ví dụ import entry mới được thực thi bằng `bind`, thay thuộc tính bằng `modifyAttributes`, đổi DN bằng `rename`, xóa entry bằng `unbind`. **Không cho nội dung file tự quyết định quyền**: mỗi operation phải qua chính sách cho phép và ACL server; thao tác `delete`/`modrdn` thường cần được chặn mặc định.

Nếu dùng `LdapRepository<DirectoryPerson>`, `save` không phải trình nạp LDIF: nó thao tác trên entity theo cách xác định entry mới/cũ của repository, không hiểu `changetype` hoặc thay thế toàn bộ directory như một bản restore.

## 11. Luồng nhập an toàn: validate, đối chiếu, staging, áp dụng, kiểm chứng

Một pipeline nhập LDIF nên hoạt động như sau:

```text
File LDIF được duyệt
        │
        ▼
Parse đúng định dạng + chặn URL value ngoài chính sách
        │
        ▼
Validate DN nằm trong base/OU + attribute allowlist + changetype
        │
        ▼
Đếm record, kiểm tra trùng DN / xung đột / schema
        │
        ▼
Đối chiếu entry đích + tạo bảng thay đổi dự kiến (dry-run)
        │
        ▼
Áp dụng ở staging / directory thử nghiệm
        │
        ▼
Phê duyệt thay đổi cụ thể trước khi ghi vào đích được phép
        │
        ▼
Ghi thật có audit + kiểm chứng hậu thao tác + xử lý sai lệch
```

Các bước chặn nên có quy tắc rõ ràng:

| Kiểm tra | Quy tắc mẫu |
|---|---|
| Phạm vi DN | Tất cả DN phải bằng hoặc nằm dưới `ou=people,dc=example,dc=org` theo parser DN |
| Loại thay đổi | Mặc định chỉ `add`; `modify` cần duyệt trường, `delete`/`modrdn` bị từ chối |
| Thuộc tính | Chỉ `objectClass,uid,cn,sn,givenName,mail`; loại bỏ thuộc tính phát sinh từ server |
| Số bản ghi | Không vượt số lượng đã phê duyệt; không âm thầm bỏ qua bản ghi lỗi |
| Trùng định danh | Dừng khi DN hoặc khóa đối chiếu nghiệp vụ bị trùng |
| Thao tác ghi | Dừng khi server từ chối schema/ACL; ghi nhận DN và lỗi đã ẩn dữ liệu nhạy cảm |
| Khả năng khôi phục | Có phương án rollback/restore theo từng thay đổi, không giả định rollback tự động |

**Không mặc định LDAP hỗ trợ giao dịch ACID xuyên hàng trăm entry.** Một file chứa 100 thay đổi có thể thành công ở 60 bản ghi rồi lỗi ở bản ghi 61. Do đó cần ghi tiến độ, hậu kiểm, xác định thao tác nào có thể chạy lại an toàn và kế hoạch bù trừ. Việc `add` chạy lại có thể lỗi entry đã tồn tại; `modify`/xóa cũng không tự idempotent trong mọi trường hợp.

## 12. Export định kỳ và đồng bộ gia tăng: không nhầm snapshot với delta

Một file xuất bằng `ldapsearch` thường là **snapshot của kết quả truy vấn tại thời điểm thực hiện** (và thậm chí có thể không hoàn toàn nguyên tử khi đọc nhiều entry). File đó **không tự ghi lại lịch sử các thao tác** add/modify/delete.

Khi dùng LDIF cho đồng bộ:

- **Full export:** lấy trạng thái của một phạm vi để khởi tạo hoặc đối soát, kiểm tra completeness và lưu timestamp/checkpoint phía quy trình.
- **Delta export:** chỉ nhận thay đổi kể từ lần trước nếu server có changelog/LDAP Sync control hoặc cơ chế tương đương đáng tin cậy; hỗ trợ khác nhau theo sản phẩm.
- **Change LDIF:** mô tả thay đổi sẽ áp dụng, nhưng không tự được sinh đầy đủ từ một snapshot thông thường.
- **Phát hiện xóa:** một entry không có trong lần export mới có thể do filter, ACL, OU, referral, paging hay lỗi, **chưa chắc đã bị xóa ở nguồn**.

Thuộc tính `modifyTimestamp` có thể hữu ích để tham khảo nhưng không đủ để xây một hệ thống incremental sync chắc chắn trong mọi trường hợp: có thể bỏ sót xóa, đổi DN, các bản ghi trùng timestamp hoặc thay đổi giữa các trang. Nếu yêu cầu độ tin cậy cao, cần thiết kế checkpoint, replay, reconciliation và cơ chế phát hiện thay đổi tương thích với directory thực tế.

**LDAP replication khác nhập/xuất LDIF:** replication duy trì dữ liệu giữa các replica theo cơ chế server; LDIF là phương thức trao đổi/batch ở mức ứng dụng. Không giả định một lần import tương đương khôi phục đầy đủ trạng thái replication, ACL, schema và cấu hình server.

## 13. Bảo mật dữ liệu LDIF trên toàn vòng đời

**LDIF có thể chứa dữ liệu cá nhân và thông tin bảo mật**, ngay cả khi tệp chỉ là bản xuất từ directory thử nghiệm. Cần kiểm soát từ lúc tạo đến lúc hủy:

1. **Kết nối:** LDAPS hoặc StartTLS với xác thực chứng chỉ máy chủ; không tắt TLS để export/import nhanh hơn.
2. **Bind credentials:** tránh đặt mật khẩu trên command line, biến môi trường không được bảo vệ hoặc log; dùng tài khoản riêng, quyền tối thiểu và cơ chế secret phù hợp.
3. **Giới hạn trường:** xuất các thuộc tính cần thiết, kiểm tra `userPassword`, thuộc tính AD nhạy cảm, dữ liệu binary, token và thông tin riêng tư.
4. **Quyền file:** đặt umask/quyền truy cập chặt trên máy chạy export; mã hóa khi lưu hoặc truyền, không đính kèm email công khai và không commit vào Git.
5. **Audit:** ghi ai xuất/nhập, nguồn/đích, base, filter, attribute allowlist, số entry, thời điểm, checksum, kết quả và lý do nghiệp vụ; không cần log toàn bộ giá trị nhạy cảm.
6. **Lưu trữ và hủy:** xác định thời hạn lưu theo chính sách tổ chức, thu hồi quyền chia sẻ và xóa file tạm sau khi hoàn tất.
7. **Người được phép xem:** quyền đọc LDAP tại server không đồng nghĩa quyền trích xuất và phát tán dữ liệu ra file; phải có phê duyệt sử dụng dữ liệu ngoài directory.

Nếu dùng dữ liệu production để tái tạo môi trường test, ưu tiên **dữ liệu giả lập hoặc khử định danh** theo chính sách. Không chép nguyên mật khẩu, nhóm đặc quyền, email thật hoặc các thuộc tính nhạy cảm sang môi trường phát triển.

## 14. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
|---|---|---|
| Export ra 0 entry | Sai base/scope/filter, ACL hoặc nhầm directory | Xác minh RootDSE, DN và thử base-object search bằng đúng bind account |
| Export thiếu nhiều entry | Size/time limit, paging, referral, network timeout | Xem exit code, server log, số trang và tổng DN đối chiếu |
| LDIF import báo “already exists” | DN đích đã có entry | Dừng, so với hợp đồng; không tự xóa để import lại |
| “No such object” khi import | Chưa có parent, sai suffix hoặc DN không thuộc đích | Tạo parent trong phạm vi được phép, sửa ánh xạ DN có kiểm chứng |
| Lỗi objectClass/schema | Thiếu MUST attr, lớp/thuộc tính không hỗ trợ | Mapping schema, sửa bản nhập trước khi thử lại |
| “Insufficient access rights” | ACL không cho phép add/modify | Kiểm tra quyền và chủ sở hữu, không dùng admin để vượt kiểm soát |
| Thông tin Unicode sai | Tự ghi LDIF không đúng encoding/base64/gấp dòng | Dùng LDIF writer chuẩn; kiểm tra từng attribute |
| Nhập nhóm nhưng member không hợp lệ | DN tham chiếu chưa có hoặc chưa ánh xạ | Tạo target entry trước rồi cập nhật liên kết theo quy tắc |
| Nhập thành công nhưng ứng dụng không thấy | Ứng dụng dùng base khác, replication delay hoặc filter `objectClass` khác | Kiểm tra đúng endpoint, DN, OU, search scope, ACL và consistency |
| Chạy lại file gây lỗi hoặc ghi đè | Thiếu chính sách idempotency/diff | Lưu checkpoint, đối chiếu trước khi áp dụng, tách thao tác được phép chạy lại |

Đối với lỗi trên AD, OpenLDAP hoặc 389 Directory Server, mã lỗi LDAP có thể tương tự nhưng thao tác tạo tài khoản, nhóm, mật khẩu, object class và thuộc tính vận hành khác nhau. Không tái nhập máy móc tất cả thuộc tính AD bằng LDIF sang một LDAP server khác.

## 15. Kiểm thử thực tế theo phạm vi được phép

Trước khi triển khai quy trình xuất/nhập, hãy có **directory test** với schema, ACL và cấu trúc DN phù hợp, ví dụ `dc=example,dc=org`, `ou=people` và `ou=groups`. Kiểm thử tối thiểu:

| Ca kiểm thử | Dữ liệu đầu vào | Kỳ vọng |
|---|---|---|
| Export một entry | DN `uid=u1001,ou=people,...`, scope base | Chính xác một DN và các thuộc tính allowlist |
| Export cả OU | Filter chỉ `inetOrgPerson` trong `ou=people` | Không chứa nhóm hoặc service account ngoài phạm vi |
| Sai base/scope | Tìm dưới `ou=groups` thay vì `ou=people` | Không vô tình nới rộng search để tìm bằng mọi giá |
| Thuộc tính nhạy cảm | Directory có userPassword hoặc trường đặc thù | File xuất không chứa trường ngoài allowlist |
| Nội dung base64/UTF-8 | Entry có ký tự đặc biệt hoặc giá trị binary được cho phép | Parser/serializer đọc lại đúng dữ liệu |
| Import mới | Parent tồn tại, entry chưa có, schema hợp lệ | Add thành công; lookup trả đúng DN và giá trị |
| Import trùng | Entry đã tồn tại cùng DN | Dừng/báo lỗi; không tự overwrite |
| Modify thuộc tính | File chỉ duyệt `mail` | Chỉ `mail` thay đổi; trường khác giữ nguyên |
| Change record bị chặn | `changetype: delete` ngoài chính sách | Bộ kiểm tra chặn trước khi gửi LDAP request |
| DN ngoài nhánh | `uid=...,ou=admins,dc=example,dc=org` | Bị từ chối dù tài khoản bind tình cờ có quyền |
| Import nhiều entry có một lỗi | Một record vi phạm schema | Phát hiện partial success, ghi nhận và khôi phục theo kế hoạch |
| Tham chiếu nhóm | Member DN cần ánh xạ sang suffix mới | Nhóm chứa đúng target DN sau import |
| LDAP không khả dụng | TLS lỗi hoặc server down | Không đánh dấu hoàn tất, không tự giảm mức bảo mật |

Kiểm thử phải dùng **tài khoản có ACL tương tự tài khoản vận hành**, không chỉ dùng admin. Kiểm chứng sau thao tác bằng `ldapsearch` có base/scope hẹp, so tập DN, `objectClass`, thuộc tính và các tham chiếu; đếm số record thành công, lỗi và số record chưa xử lý.

## 16. Bài tập tình huống

Một nhóm phát triển cần khởi tạo LDAP test bằng đúng hai tài khoản `u1001`, `u1002` trong `ou=people,dc=example,dc=org`. Họ được phép đọc các thuộc tính `objectClass,uid,cn,sn,mail` ở nguồn; đích là `ldap-stage.example.org` và chỉ cho phép **add entry mới**. Họ không được phép xuất nhóm, mật khẩu hoặc xóa tài khoản.

Hãy trả lời:

1. Cần ràng buộc **endpoint, base DN, scope, filter và attribute allowlist** thế nào để chỉ xuất hai người được duyệt?
2. Sự khác nhau giữa content LDIF và change LDIF trong tình huống này là gì? Có nên tạo `changetype: delete` cho entry ở test nhưng không thấy ở nguồn không?
3. Trước khi nhập, cần kiểm tra gì về parent DN, schema, quyền add và DN đã tồn tại?
4. Nếu bản ghi `u1001` được nhập nhưng `u1002` lỗi, quy trình có được tự báo “thành công” không? Cần ghi nhận những gì?
5. Nếu một người được chuyển OU ở nguồn, vì sao không thể chỉ so snapshot theo DN cũ rồi coi người đó đã bị xóa?
6. Nếu dùng Spring Data LDAP, phần nào do repository/`LdapTemplate` đảm nhận và phần nào bắt buộc phải do trình parse/serialize LDIF và chính sách nghiệp vụ xử lý?

**Gợi ý đối chiếu:** ràng buộc base tại `ou=people,dc=example,dc=org`, scope phù hợp cấu trúc entry và filter chỉ chọn các UID trong danh sách đã duyệt; đặt allowlist thuộc tính thay vì xuất `*`. Content LDIF cho phép đưa dữ liệu entry mới vào môi trường thử nghiệm; change records có thể tạo thay đổi mạnh hơn nên cần chặn theo chính sách. Không suy ra xóa từ việc vắng mặt trong snapshot; khi import lỗi một phần, cần hậu kiểm và xử lý bù trừ. `LdapTemplate` thao tác LDAP, còn LDIF parser, kiểm tra phạm vi và audit là các trách nhiệm bổ sung.

## 17. Checklist và kết luận

Trước khi đánh dấu một lần nhập/xuất LDIF là hoàn tất, hãy xác nhận:

- Đúng **directory endpoint**, naming context, base DN, scope, filter và tập thuộc tính được phép.
- Đúng **tài khoản bind/ACL**, TLS hợp lệ, quyền người yêu cầu và cửa sổ thao tác.
- Đúng **loại LDIF**: snapshot/content hay change record; chỉ cho phép `changetype` đã phê duyệt.
- Đã xác minh **DN, schema, objectClass, parent, số bản ghi, thuộc tính nhạy cảm và kiểu dữ liệu đa trị/binary**.
- Đã thử trên directory test, xử lý collision, partial success, rollback/idempotency và tham chiếu nhóm.
- Đã đối soát **số DN và nội dung hậu thao tác**, lưu audit/chỉ số kiểm chứng và bảo vệ/hủy file theo chính sách.

**Kết luận:** LDIF giúp trao đổi entry và thay đổi LDAP nhưng **không tự giới hạn quyền truy cập, bảo đảm tính nhất quán hay thay thế chính sách đồng bộ**. Khi dùng với Spring Data LDAP, cần kết hợp hiểu biết về DN, `objectClass`, schema, repository/`LdapTemplate`, LDAP filter an toàn và kiểm thử directory để chỉ nhập/xuất đúng dữ liệu được phép, bảo vệ hệ thống nguồn và dữ liệu danh tính.
