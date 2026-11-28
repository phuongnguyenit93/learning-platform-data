# Thiết kế bộ lọc động có escape và giới hạn phạm vi

Trong **Spring Data LDAP**, ứng dụng Java có thể dùng `LdapRepository` để truy vấn entry theo các method cố định hoặc dùng `LdapTemplate` khi tiêu chí lọc thay đổi theo yêu cầu. Một chức năng tìm kiếm người dùng thường nhận nhiều điều kiện tùy chọn: họ, loại nhân viên, sự hiện diện của email hoặc một giá trị cần loại trừ. Nếu xây LDAP filter bằng cách nối chuỗi từ đầu vào không đáng tin, ứng dụng có thể gặp **LDAP injection**, tìm nhầm entry hoặc vô tình truy xuất cả một nhánh directory.

Bài **Thực hành** này xây dựng một chức năng tìm kiếm thực tế: **bộ lọc động có escape giá trị, giới hạn search base/scope, allowlist thuộc tính và kiểm tra kết quả**. Người học sẽ kết hợp mô hình DN, `objectClass`, schema, các phép AND/OR/NOT, `LdapTemplate`, quyền bind, kết nối TLS và kiểm thử với LDAP directory. Đây là ví dụ truy vấn **chỉ đọc**; các phương thức CRUD của repository cần ranh giới quyền riêng và không được bật chỉ vì giao diện có chức năng tìm kiếm.

## 1. Mục tiêu và yêu cầu của bài thực hành

Hãy thiết kế API nội bộ `POST /directory/people/search` cho bộ phận nhân sự. API chỉ được tìm các entry `inetOrgPerson` ở nhánh `ou=people,dc=example,dc=org`; nó không được tìm trong `ou=service-accounts`, `ou=groups` hoặc các naming context khác.

Tiêu chí hợp lệ:

1. **`surname`**: họ phải bằng giá trị được cung cấp, nếu có.
2. **`employeeTypes`**: loại nhân viên thuộc một tập giá trị cho phép; các lựa chọn được kết hợp bằng **OR**.
3. **`requireMail`**: bắt buộc entry có thuộc tính `mail`.
4. **`excludedMail`**: loại entry có email đúng bằng một giá trị bị chặn.

Các điều kiện ở tầng cao nhất được kết hợp bằng **AND**. Ứng dụng còn phải:

- Chỉ chấp nhận các tên trường/toán tử được lập trình sẵn; không cho client gửi raw LDAP filter hoặc raw base DN.
- Escape **giá trị** dùng trong equality filter theo cú pháp LDAP, kể cả ký tự `*`, `(`, `)`, `\`.
- Có ít nhất một điều kiện dương đủ hẹp ngoài `objectClass`; không cho truy vấn trống trả về tất cả người dùng.
- Giới hạn search scope, số kết quả, thời gian và thuộc tính trả về.
- Dùng tài khoản LDAP chỉ đọc qua LDAPS hoặc StartTLS có xác thực chứng chỉ; không log secret hoặc thông tin nhạy cảm.
- Kiểm thử logic và kiểm thử tích hợp trên directory, gồm cả trường hợp thiếu thuộc tính và đầu vào cố tình gây injection.

**Kết quả mong muốn:** một lớp Java có thể nhận tiêu chí hợp lệ, tạo filter theo cấu trúc rõ ràng, truy vấn bằng `LdapTemplate` và trả DTO nhỏ thay vì toàn bộ LDAP entry.

## 2. Chuẩn bị cây thư mục và dữ liệu thử

Giả sử LDAP server phục vụ naming context `dc=example,dc=org` với các entry:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=u1001  → Nguyen / An   / staff      / an@example.org
│   ├── uid=u1002  → Nguyen / Binh / contractor / blocked@example.org
│   ├── uid=u1003  → Tran   / An   / staff      / an.tran@example.org
│   ├── uid=u1004  → Le     / Chi  / intern     / (không có mail)
│   └── uid=u1005  → Nguyen / Dan  / staff      / (không có mail)
├── ou=groups
│   └── cn=developers
└── ou=service-accounts
    └── cn=svc-reader
```

Một entry mẫu ở dạng LDIF:

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
employeeType: staff
mail: an@example.org
```

Schema của `inetOrgPerson` có các thuộc tính như `cn`, `sn`, `givenName`, `mail` và `employeeType`; các thuộc tính bắt buộc hoặc tùy chọn phụ thuộc object class và schema server. Ở tập ví dụ này, `sn` và `cn` có giá trị theo yêu cầu của `person`, còn `mail` có thể vắng mặt. Những giá trị `employeeType` như `staff`, `contractor`, `intern` là **quy ước dữ liệu của ví dụ**, không phải danh sách enum chuẩn áp dụng cho mọi LDAP directory.

| UID | `sn` | `givenName` | `employeeType` | `mail` |
|---|---|---|---|---|
| `u1001` | Nguyen | An | staff | an@example.org |
| `u1002` | Nguyen | Binh | contractor | blocked@example.org |
| `u1003` | Tran | An | staff | an.tran@example.org |
| `u1004` | Le | Chi | intern | *Không có* |
| `u1005` | Nguyen | Dan | staff | *Không có* |

**Lưu ý:** mô hình bài này quy ước user nằm **trực tiếp** dưới `ou=people`. Vì vậy có thể dùng search scope **ONELEVEL** để giới hạn chặt hơn SUBTREE. Nếu directory thực tế chứa OU con, cần thiết kế phạm vi được duyệt trước khi thay đổi scope.

## 3. Đầu vào phải là cấu trúc nghiệp vụ, không phải filter thô

Một request mẫu:

```json
{
  "surname": "Nguyen",
  "employeeTypes": ["staff", "contractor"],
  "requireMail": true,
  "excludedMail": "blocked@example.org"
}
```

Không chấp nhận một request kiểu:

```json
{
  "baseDn": "dc=example,dc=org",
  "scope": "SUBTREE",
  "attribute": "userPassword",
  "filter": "(|(objectClass=*)(uid=*))",
  "resultLimit": 100000
}
```

Request thứ hai cho phép người dùng tự điều khiển **cây cần tìm**, **thuộc tính**, **filter** và **giới hạn kết quả**. Ngay cả khi có API escape giá trị, việc cho client đưa nguyên một filter sẽ làm mất ranh giới allowlist; escape không biến một ngôn ngữ truy vấn tùy ý thành chính sách truy cập an toàn.

Trong thiết kế an toàn, **server** quyết định:

| Thành phần | Giá trị được cố định/kiểm soát |
|---|---|
| LDAP endpoint | Máy chủ đã duyệt, kết nối bảo vệ bởi TLS |
| Context base | `dc=example,dc=org` |
| Search base | `ou=people`, tương đối với context base |
| Scope | `ONELEVEL` theo cây dữ liệu thực hành |
| Object class | `inetOrgPerson` |
| Field được lọc | `sn`, `employeeType`, `mail` |
| Toán tử | Equality, presence, AND, OR và NOT theo template đã lập trình |
| Thuộc tính trả về | `uid`, `cn`, `sn`, `mail` |
| Số kết quả | Giới hạn do server áp đặt, ứng dụng còn kiểm tra số entry thực tế |

Đầu vào chỉ cung cấp **giá trị** cho những điều kiện đó. Nếu ứng dụng hỗ trợ nhiều tenant/OU, phải ánh xạ tenant đã xác thực sang base/endpoint bằng cấu hình tin cậy, không cho người dùng cuối gửi DN bất kỳ để yêu cầu mở rộng tìm kiếm.

## 4. Ôn cú pháp filter LDAP: AND, OR, NOT và presence

LDAP filter dùng cú pháp riêng theo RFC 4515:

| Ý nghĩa | Filter minh họa |
|---|---|
| Họ là Nguyen | `(sn=Nguyen)` |
| Thuộc loại staff | `(employeeType=staff)` |
| Staff **hoặc** contractor | `(|(employeeType=staff)(employeeType=contractor))` |
| Họ Nguyen **và** loại staff | `(&(sn=Nguyen)(employeeType=staff))` |
| **Không** có email bị chặn | `(!(mail=blocked@example.org))` |
| Có ít nhất một giá trị mail | `(mail=*)` |

Với request mẫu ở phần 3, filter logic là:

```ldap
(&(objectClass=inetOrgPerson)
  (sn=Nguyen)
  (|(employeeType=staff)(employeeType=contractor))
  (mail=*)
  (!(mail=blocked@example.org)))
```

Để đưa lên giao thức, filter phải ở dạng **liền mạch, không thêm whitespace để trang trí**:

```ldap
(&(objectClass=inetOrgPerson)(sn=Nguyen)(|(employeeType=staff)(employeeType=contractor))(mail=*)(!(mail=blocked@example.org)))
```

Diễn giải từng bước:

1. Entry phải thuộc `objectClass=inetOrgPerson`.
2. `sn=Nguyen`.
3. `employeeType=staff` **hoặc** `contractor`.
4. Có `mail`.
5. `mail` không được bằng `blocked@example.org`.

Theo dữ liệu mẫu, chỉ **`u1001`** thỏa mọi điều kiện. `u1002` bị loại bởi NOT email; `u1005` bị loại bởi presence mail; `u1003` và `u1004` không đúng họ.

**NOT không đồng nghĩa `!=` trong SQL.** Một entry thiếu `mail` có thể vẫn thỏa bộ lọc phủ định `(!(mail=blocked@example.org))` theo ngữ nghĩa LDAP thông dụng. Khi yêu cầu email bắt buộc tồn tại, hãy thêm riêng `(mail=*)`. Cần kiểm thử trường hợp thuộc tính vắng mặt hoặc bị ACL che trên directory đích.

## 5. Escape LDAP filter đúng cách

Ký tự cấu trúc trong **giá trị filter** phải được xử lý theo quy tắc LDAP, không ghép trực tiếp chuỗi. Các ký tự thường gặp gồm:

| Ký tự trong giá trị | Biểu diễn escape RFC 4515 |
|---|---|
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| Dấu gạch chéo ngược | `\5c` |
| Byte NUL | `\00` |

Ví dụ người gọi nhập `surname` với giá trị:

```text
Nguyen*)(uid=*)
```

**Không an toàn** nếu nối chuỗi:

```java
// KHÔNG LÀM: đầu vào có thể phá cấu trúc bộ lọc.
String filter = "(sn=" + userInput + ")";
```

Cách an toàn là truyền `userInput` làm **giá trị** cho bộ tạo filter:

```java
import org.springframework.ldap.filter.EqualsFilter;

EqualsFilter safe = new EqualsFilter("sn", userInput);
String encoded = safe.encode();
```

Giá trị có các ký tự điều khiển sẽ được escape thành giá trị literal; nó **không thể tự tạo một nhóm OR mới**. Với giá trị thử ở trên, phần điều kiện tương đương:

```ldap
(sn=Nguyen\2a\29\28uid=\2a\29)
```

Trong Spring LDAP, `EqualsFilter` và API builder như `query().where("sn").is(userInput)` là lựa chọn phù hợp để escape **giá trị**. Đừng tự viết một hàm thay ký tự đơn giản rồi coi là filter parser đầy đủ, đặc biệt với Unicode hoặc dữ liệu không hợp lệ.

**Escape không thay thế validation:** vẫn cần giới hạn chiều dài, chặn ký tự điều khiển không được phép theo nghiệp vụ và quy định rõ field/toán tử. Ứng dụng tìm kiếm chính xác có thể chấp nhận dấu `*` như một ký tự dữ liệu thật; nếu muốn hỗ trợ **prefix/substring search**, hãy thiết kế một toán tử riêng với ranh giới wildcard được kiểm soát, không dùng input làm raw LDAP pattern.

**Escape DN khác escape filter:** khi xây `uid=u1001,ou=people`, hãy dùng `LdapNameBuilder` hoặc parser DN phù hợp. Không dùng chuỗi do client cung cấp làm DN đầy đủ hay xem `EqualsFilter` là công cụ escape RDN.

## 6. Thiết kế kiểu dữ liệu tìm kiếm và validation

Dùng **Java 17+** để khai báo các `record` bất biến. Cấu trúc đầu vào chỉ chứa tiêu chí nghiệp vụ:

```java
import java.util.List;

public record PersonSearchCriteria(
        String surname,
        List<String> employeeTypes,
        boolean requireMail,
        String excludedMail
) {}
```

Trong ứng dụng thực tế, DTO này có thể được gắn validation của tầng HTTP. Tuy nhiên **không chỉ dựa vào annotation validation**: service trực tiếp gọi directory vẫn phải kiểm tra dữ liệu hoặc chỉ tiếp nhận các đối tượng đã được tạo qua một bộ kiểm tra bắt buộc.

Quy tắc đề xuất:

- `surname`: tùy chọn, tối đa 80 ký tự, không nhận control character; `*` được coi là dữ liệu để thử escape.
- `employeeTypes`: tối đa 2 giá trị, chỉ nhận `staff` hoặc `contractor`, không có giá trị `intern` trong API này; loại bỏ phần tử trùng.
- `requireMail`: cờ do API chấp nhận.
- `excludedMail`: tùy chọn, tối đa 254 ký tự, không nhận control character. Nếu có giá trị này, phải yêu cầu `mail` tồn tại để tránh trả các entry thiếu email.
- Phải có **`surname` hoặc ít nhất một `employeeTypes` hợp lệ**. Một cờ `requireMail=true` đơn độc không đủ hạn chế tìm kiếm.
- Không nhận thuộc tính hoặc loại toán tử tùy ý từ request. Với nhu cầu mở rộng, hãy dùng enum/allowlist được kiểm soát trong code.

**Tại sao cho phép `surname` chứa `*` trong bản thử?** Vì đây là một ca quan trọng để chứng minh escape: ký tự `*` phải được xử lý như một ký tự dữ liệu, không tự biến truy vấn equality thành presence/substring.

## 7. Lời giải Java: tạo filter động với `LdapTemplate`

Ví dụ dưới đây giả định một `LdapTemplate` được cấu hình cho **tài khoản bind chỉ đọc** với context base `dc=example,dc=org`. Code cố định search base, scope, loại entry và danh sách thuộc tính. `EqualsFilter` xử lý escape giá trị; `AndFilter`, `OrFilter`, `NotFilter` và `PresentFilter` biểu diễn nhóm logic.

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.NotFilter;
import org.springframework.ldap.filter.OrFilter;
import org.springframework.ldap.filter.PresentFilter;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class SafePersonDirectorySearch {
    private static final Set<String> ALLOWED_TYPES =
            Set.of("staff", "contractor");
    private static final int MAX_RESULTS = 50;

    private final LdapTemplate readLdapTemplate;

    public record Criteria(
            String surname,
            List<String> employeeTypes,
            boolean requireMail,
            String excludedMail
    ) {}

    public record PersonHit(
            String uid, String commonName, String surname, String mail
    ) {}

    public SafePersonDirectorySearch(LdapTemplate readLdapTemplate) {
        this.readLdapTemplate =
                Objects.requireNonNull(readLdapTemplate);
    }

    public List<PersonHit> search(Criteria criteria) {
        Objects.requireNonNull(criteria, "criteria");

        String surname = optionalText(criteria.surname(), 80);
        String excludedMail = optionalText(criteria.excludedMail(), 254);

        List<String> requestedTypes = criteria.employeeTypes() == null
                ? List.of()
                : criteria.employeeTypes();

        if (requestedTypes.size() > 2) {
            throw new IllegalArgumentException(
                    "Too many employeeTypes");
        }

        Set<String> types = new LinkedHashSet<>();
        for (String type : requestedTypes) {
            if (!ALLOWED_TYPES.contains(type)) {
                throw new IllegalArgumentException(
                        "Unsupported employeeType");
            }
            types.add(type);
        }

        // Tránh truy vấn quét toàn bộ OU chỉ với objectClass/presence.
        if (surname == null && types.isEmpty()) {
            throw new IllegalArgumentException(
                    "At least one positive search criterion is required");
        }

        AndFilter all = new AndFilter();
        all.and(new EqualsFilter("objectClass", "inetOrgPerson"));

        if (surname != null) {
            all.and(new EqualsFilter("sn", surname));
        }

        if (!types.isEmpty()) {
            OrFilter allowedTypes = new OrFilter();
            for (String type : types) {
                allowedTypes.or(new EqualsFilter("employeeType", type));
            }
            all.and(allowedTypes);
        }

        // Bắt buộc mail tồn tại khi có phép phủ định theo mail.
        if (criteria.requireMail() || excludedMail != null) {
            all.and(new PresentFilter("mail"));
        }
        if (excludedMail != null) {
            all.and(new NotFilter(
                    new EqualsFilter("mail", excludedMail)));
        }

        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .timeLimit(2000)
                .countLimit(MAX_RESULTS + 1)
                .attributes("uid", "cn", "sn", "mail")
                .filter(all);

        AttributesMapper<PersonHit> mapper = attrs ->
                new PersonHit(
                        text(attrs, "uid"),
                        text(attrs, "cn"),
                        text(attrs, "sn"),
                        text(attrs, "mail"));

        List<PersonHit> result =
                readLdapTemplate.search(ldapQuery, mapper);

        if (result.size() > MAX_RESULTS) {
            throw new IllegalStateException(
                    "Search exceeds the permitted result limit");
        }
        return result;
    }

    private static String optionalText(String raw, int maxLength) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        String value = raw.trim();
        if (value.length() > maxLength) {
            throw new IllegalArgumentException("Search value too long");
        }
        for (int i = 0; i < value.length(); i++) {
            if (Character.isISOControl(value.charAt(i))) {
                throw new IllegalArgumentException(
                        "Control character is not permitted");
            }
        }
        return value;
    }

    private static String text(Attributes attrs, String key)
            throws NamingException {
        Attribute value = attrs.get(key);
        return value == null ? null : (String) value.get();
    }
}
```

### Vì sao lời giải này an toàn hơn nối chuỗi?

1. **Không có raw filter từ client**: `sn`, `employeeType` và `mail` là tên thuộc tính cố định trong code.
2. **Escape theo giá trị**: input đưa vào `EqualsFilter` thay vì chèn vào chuỗi LDAP filter do lập trình viên nối thủ công.
3. **Nhóm logic rõ**: OR của các `employeeType` nằm bên trong một AND. NOT chỉ phủ định equality theo `mail`.
4. **Không có truy vấn trống**: điều kiện dương là `surname` hoặc loại nhân viên được duyệt; `objectClass` một mình không đủ.
5. **Không cho đổi OU từ input**: `base("ou=people")` cố định tương đối với `LdapContextSource`.
6. **ONELEVEL**: chỉ tìm entry con trực tiếp dưới OU, phù hợp dữ liệu bài tập, thay vì mở rộng sang toàn domain.
7. **Giới hạn tài nguyên**: đặt time limit, count limit và kiểm tra kết quả; chỉ chọn các thuộc tính cần cho DTO.
8. **Không có write method**: lớp chỉ sở hữu `LdapTemplate` của tài khoản đọc, không cung cấp `bind`, `modifyAttributes`, `rename` hay `unbind`.

### Những giới hạn còn cần xử lý trong sản phẩm thật

`countLimit(MAX_RESULTS + 1)` là yêu cầu giới hạn gửi xuống LDAP; **không phải bảo đảm mọi server sẽ trả đúng 51 entry rồi dừng êm**. Directory có thể áp dụng size limit riêng hoặc trả lỗi giới hạn. Cần phân biệt **kết quả hoàn chỉnh** với **kết quả bị cắt**; không âm thầm xem một danh sách bị cắt là toàn bộ kết quả. Với dữ liệu lớn, thiết kế paging qua LDAP control tương thích và quy tắc phân trang riêng.

Trong code ví dụ, `text(...)` chỉ dùng cho thuộc tính văn bản đơn trị. Với attribute vắng mặt hoặc đa trị, schema/ACL cần được xem xét; không mặc định mọi thuộc tính luôn là `String`. Nếu kết quả dùng để quyết định quyền, phải có kiểm tra tính nhất quán và định danh ổn định, không dựa đơn thuần vào tên hiển thị.

## 8. Từng bước biến request thành filter

Với request:

```json
{
  "surname": "Nguyen",
  "employeeTypes": ["staff", "contractor"],
  "requireMail": true,
  "excludedMail": "blocked@example.org"
}
```

Các bước xây filter:

| Bước | Điều kiện thêm | Nhóm logic đang có |
|---|---|---|
| 1 | `(objectClass=inetOrgPerson)` | Bắt đầu AND |
| 2 | `(sn=Nguyen)` | AND loại entry + họ |
| 3 | `(|(employeeType=staff)(employeeType=contractor))` | AND với **một nhóm OR** |
| 4 | `(mail=*)` | Chỉ entry có email |
| 5 | `(!(mail=blocked@example.org))` | Loại email bị chặn |

Filter cuối cùng:

```ldap
(&(objectClass=inetOrgPerson)(sn=Nguyen)(|(employeeType=staff)(employeeType=contractor))(mail=*)(!(mail=blocked@example.org)))
```

Kết quả kỳ vọng theo dữ liệu thử: chỉ `uid=u1001,ou=people,dc=example,dc=org`.

**Khi bỏ qua `surname`:** filter vẫn hợp lệ nếu danh sách `employeeTypes` có giá trị. Nhưng bỏ cả `surname` và `employeeTypes` phải bị chặn **trước khi gửi LDAP request**, kể cả khi `requireMail=true`.

**Khi `employeeTypes` chỉ có một phần tử:** đoạn code vẫn tạo nhóm OR một nhánh. Về logic, OR một điều kiện tương đương chính điều kiện đó; nếu muốn tối ưu biểu diễn có thể dùng `EqualsFilter` trực tiếp. Không phải thay đổi về quyền.

## 9. Mở rộng điều kiện động mà không mở rộng quyền tùy tiện

Khi có thêm trường tìm kiếm, đừng cho client truyền tên thuộc tính trực tiếp:

```java
// Dễ bị lạm dụng nếu attributeName do client tự cung cấp.
new EqualsFilter(attributeNameFromClient, valueFromClient);
```

Thay bằng enum và mapping cố định:

```java
enum AllowedField {
    SURNAME,
    GIVEN_NAME,
    EMPLOYEE_TYPE
}

static String ldapAttribute(AllowedField field) {
    return switch (field) {
        case SURNAME -> "sn";
        case GIVEN_NAME -> "givenName";
        case EMPLOYEE_TYPE -> "employeeType";
    };
}
```

Sau đó validate các cặp **field + operator** hợp lệ, ví dụ:

| Field | EQUALS | PRESENT | PREFIX | NOT |
|---|---|---|---|---|
| Họ `sn` | Có | Không cho client chọn | Tùy chính sách | Tùy chính sách |
| Tên `givenName` | Có | Không cho client chọn | Tùy chính sách | Không |
| Loại `employeeType` | Chỉ giá trị allowlist | Không | Không | Không |
| Email `mail` | Chỉ trong workflow được duyệt | Cờ `requireMail` | Không | Chỉ kết hợp presence |
| `userPassword` | **Không** | **Không** | **Không** | **Không** |

Nếu hỗ trợ prefix search, cần phân biệt **wildcard do ứng dụng chủ động thêm** với dấu `*` được nhập như dữ liệu. Không nối `"(cn=" + input + "*)"`; phải dùng API filter builder hỗ trợ wildcard theo cách rõ ràng và được thử với input chứa `*`, `(`, `)`, `\` và Unicode.

Không tự phát triển “ngôn ngữ filter tùy ý” gồm ngoặc lồng nhau vô hạn. Nếu cần một DSL, đặt giới hạn **độ sâu cây điều kiện, số nhánh OR, số giá trị, độ dài, loại trường** và kiểm soát chi phí query từ đầu vào.

## 10. DN, base, scope và ACL: bốn giới hạn khác nhau

Một bộ lọc escape đúng vẫn có thể truy vấn quá rộng nếu **base/scope** không được giới hạn. Ví dụ:

```text
Context base: dc=example,dc=org
Search base:  ou=people
Scope:        ONELEVEL
Actual tree:  uid=u1001,ou=people,dc=example,dc=org
```

Trong `LdapTemplate`, `query().base("ou=people")` dùng base tương đối với context base đã cấu hình. Nếu context base đổi thành `ou=people,dc=example,dc=org`, phần base tương đối cần điều chỉnh; không gắn hậu tố `dc=example,dc=org` hai lần.

| Lớp | Quyết định điều gì? | Nếu cấu hình sai |
|---|---|---|
| **Naming context / suffix** | Server phục vụ phân vùng dữ liệu nào | Search có thể tới vùng ngoài khả năng phục vụ hoặc nhận referral |
| **Context base** | Gốc mặc định trong client Spring LDAP | DN tương đối bị ghép sai |
| **Search base/scope** | Bắt đầu ở đâu và tìm sâu tới đâu | Trả thiếu hoặc quá nhiều entry |
| **LDAP filter** | Điều kiện entry/attribute phải thỏa | Có thể mở rộng hoặc lọc sai |
| **Bind ACL** | Tài khoản được đọc entry/attribute nào | Dù filter đúng vẫn bị từ chối hoặc che dữ liệu |
| **Authorization ứng dụng** | Người gọi API được phép tìm những ai | Có thể lộ dữ liệu dù tài khoản dịch vụ đủ quyền đọc |

Vì vậy **giới hạn phạm vi không chỉ là `base("ou=people")`**. Cần tài khoản chỉ đọc có ACL giới hạn, endpoint đúng, HTTPS ở API, và chính sách người dùng cuối được phép tìm kiếm trong phạm vi nào.

Nếu một người được chuyển từ `ou=people` sang `ou=contractors`, query ONELEVEL tại OU cũ không còn thấy entry. **Không kết luận tài khoản bị xóa**, không tự mở search toàn domain để “tìm cho chắc”; phải theo quy tắc quyền và nguồn dữ liệu được phép.

## 11. Repository và ODM hỗ trợ được gì?

Spring Data LDAP dùng **Object–Directory Mapping** để ánh xạ entry thành Java object. Ví dụ entity:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "employeeType")
    private String employeeType;

    @Attribute(name = "mail")
    private String email;

    public DirectoryPerson() {}
    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }
    public String getEmployeeType() { return employeeType; }
    public void setEmployeeType(String employeeType) {
        this.employeeType = employeeType;
    }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

Một repository đơn giản có thể khai báo các truy vấn **cố định**:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findBySurname(String surname);

    List<DirectoryPerson> findBySurnameAndEmployeeType(
            String surname, String employeeType);
}
```

Query method được suy diễn từ property Java, ví dụ `surname` tương ứng LDAP attribute `sn`. Tuy nhiên, với số lượng tiêu chí **tùy chọn**, nhóm OR biến độ dài và quy tắc NOT/presence, việc viết mọi biến thể thành tên method sẽ khó quản lý. **`LdapTemplate` với filter builder** phù hợp hơn khi muốn tạo cây điều kiện có cấu trúc tường minh và giới hạn cố định.

`@Entry` và `@Id` không tự cấp ACL, tạo schema, quyết định scope cho mọi query hay thay thế việc validate input. Repository còn cung cấp các method CRUD trong interface kế thừa; **không cho REST controller gọi trực tiếp `save`/`delete`** từ dữ liệu tìm kiếm. Tách context chỉ đọc và context đọc–ghi nếu ứng dụng có các nghiệp vụ provisioning.

## 12. Kiểm thử unit cho cây filter và validation

Có hai mức kiểm thử:

1. **Unit test filter/validation:** kiểm tra kết quả xây filter, ca thiếu trường, giá trị vượt độ dài, input có ký tự đặc biệt và thứ tự nhóm AND/OR/NOT mà không cần directory.
2. **Integration test:** chạy truy vấn qua `LdapTemplate` trên LDAP server có schema/ACL thật để kiểm tra base, scope, kết quả, lỗi và tính an toàn trên giao thức.

Ở unit test, có thể tách logic tạo `Filter` thành một hàm riêng `buildFilter(criteria)`. Ví dụ kiểm tra giá trị equality:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

class LdapFilterEscapingTest {
    @Test
    void escapesWildcardsAndParenthesesAsData() {
        String userInput = "Nguyen*)(uid=*)";
        String encoded = new EqualsFilter("sn", userInput).encode();

        // Escape biểu diễn dấu * thành byte hex, không còn wildcard thô.
        assertTrue(encoded.contains("\\2a"));
        assertTrue(encoded.contains("\\29"));
        assertTrue(encoded.contains("\\28"));
        assertFalse(encoded.contains(")(uid=*)"));
    }
}
```

Kiểm thử này **chứng minh bộ mã hóa equality filter xử lý các ký tự đặc biệt**, nhưng không chứng minh base DN hoặc ACL của server đúng. Với unit test cho `buildFilter`, hãy kiểm tra **cấu trúc nhóm** từ đầu vào động và những trường hợp dẫn tới `IllegalArgumentException`.

Nên thử các case:

| Input | Kết quả mong muốn |
|---|---|
| `surname=Nguyen` | Có điều kiện equality `(sn=Nguyen)`, không mở rộng OU |
| `employeeTypes=[staff,contractor]` | Một nhóm OR chứa đúng hai equality filter |
| `excludedMail` được đặt | Có cả presence `(mail=*)` và NOT equality |
| `surname` chứa `*` | Dấu sao được escape như dữ liệu |
| `surname` chứa `)(uid=*)` | Không tạo được điều kiện OR/presence mới |
| `employeeTypes=[intern]` | Bị từ chối bởi allowlist |
| `employeeTypes` hơn 2 giá trị | Bị từ chối trước truy vấn LDAP |
| `surname` và `employeeTypes` đều rỗng | Bị từ chối, không query toàn OU |
| Có control character hoặc chuỗi quá dài | Bị từ chối |
| User gửi `baseDn`/raw filter ngoài DTO | Tầng API từ chối trường không hợp lệ hoặc bỏ qua một cách có kiểm soát theo contract |

## 13. Kiểm thử tích hợp với LDAP directory

Mock một `LdapTemplate` không đủ để phát hiện sai search scope, quyền LDAP hay sự khác biệt matching rule. Tạo directory thử nghiệm với đúng dữ liệu `u1001`–`u1005` và thêm **entry ngoài OU** để xác minh biên truy vấn.

| Tình huống | Điều kiện đầu vào | Kết quả mong đợi |
|---|---|---|
| AND + OR + NOT đầy đủ | `Nguyen`, `staff/contractor`, `requireMail=true`, chặn blocked | Chỉ `u1001` |
| Chỉ họ | `surname=Nguyen`, loại nhân viên rỗng, không có điều kiện mail | `u1001`, `u1002`, `u1005` |
| Chỉ loại nhân viên | `employeeTypes=[staff]` | `u1001`, `u1003`, `u1005` |
| Có email và bị chặn | `employeeTypes=[staff,contractor]`, yêu cầu mail, chặn blocked | `u1001`, `u1003` |
| Thiếu mail | `surname=Nguyen`, `requireMail=true` | `u1001`, `u1002` |
| Giá trị injection | `surname=Nguyen*)(uid=*)` | Không mở rộng kết quả sang toàn OU |
| Không có selector dương | Chỉ `requireMail=true` | Lỗi validation, không phát LDAP search |
| Entry nằm dưới OU con | Entry `uid=child,ou=team,ou=people,...` | ONELEVEL không trả entry này |
| Entry ngoài OU | Entry dưới `ou=service-accounts` hoặc `ou=groups` | Không xuất hiện ở kết quả |
| Bind account thiếu quyền | Tài khoản đọc bị chặn một số attribute | Lỗi/kết quả bị hạn chế đúng ACL, không tự nới quyền |
| TLS bị từ chối | Chứng chỉ server không hợp lệ | Kết nối thất bại, không fallback cleartext |
| Server áp size/time limit | Thêm nhiều entry được phép | Không coi kết quả cắt cụt là danh sách đầy đủ |

**Quan trọng về so sánh kết quả:** LDAP không bảo đảm thứ tự sắp xếp entry nếu chưa yêu cầu sorting phù hợp. Kiểm thử nên so **tập UID hoặc DN** thay vì so thứ tự list trả về.

Nếu directory thử nghiệm dùng schema hoặc matching rule khác production, kết quả equality, cách xử lý thuộc tính thiếu và giới hạn truy vấn có thể khác. Với Active Directory, tên thuộc tính như `sAMAccountName` và mô hình DN `CN=...` khác ví dụ `uid=...`; không sao chép nguyên mapping mà không kiểm tra schema.

## 14. Hiệu năng và vận hành bộ lọc động

Ngay cả khi filter an toàn trước injection, một truy vấn có quá nhiều nhánh OR hoặc base quá rộng vẫn có thể tạo tải lớn cho LDAP server. Những điểm cần đo:

- **Độ trễ** p50/p95/p99 của `LdapTemplate.search` và API tổng.
- **Số LDAP search operations thực** tại server, kể cả các trang/truy vấn bổ sung nếu có.
- **Số entry trả về**, tỷ lệ truy vấn bằng 0, số lần bị size/time limit và lỗi.
- **Cardinality của OR**, thuộc tính filter có index phù hợp hay không và độ lớn của payload.
- **Số connection/context**, thời gian chờ pool, bind/TLS handshake và timeout.

Ví dụ, tìm `(sn=Nguyen)` trong OU vài nghìn entry có thể chấp nhận được nhưng không nhất thiết có hiệu năng tốt trên mọi directory; cần kiểm tra index/matching rule của `sn` thực tế. Nếu một API có thể thêm hàng trăm OR branches, chỉ escape giá trị là chưa đủ để giới hạn chi phí.

Không ghi `surname`, `mail`, DN đầy đủ hoặc raw filter vào nhãn metric vì rủi ro thông tin cá nhân và cardinality. Có thể ghi loại filter `surname+employeeType+excludeMail`, số điều kiện, thời gian và mã lỗi thay vì toàn bộ giá trị.

**Dùng LDAPS hoặc StartTLS có xác minh chứng chỉ**; không tắt TLS để lấy benchmark nhanh hơn. Tài khoản bind cho search chỉ nên có ACL đọc thuộc tính được duyệt. Khi tăng giới hạn pool hoặc chuyển sang nhiều LDAP replica, đo lại tải và kiểm tra đúng ranh giới dữ liệu.

## 15. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Ghép `"(sn=" + input + ")"` | LDAP injection hoặc sai cú pháp khi input có ký tự đặc biệt | Dùng `EqualsFilter`/`LdapQueryBuilder` |
| Cho client chọn `attributeName` | Có thể truy vấn attribute nhạy cảm | Enum/allowlist từ code |
| Cho client chọn base DN | Có thể tìm ngoài OU/tenant được phép | Mapping từ danh tính đã xác thực tới base được duyệt |
| Cho `objectClass=*` làm điều kiện duy nhất | Có thể quét quá rộng và lộ thông tin | Yêu cầu tiêu chí dương cụ thể |
| Xây OR rỗng | Filter không có nghĩa/không hợp lệ theo server | Chỉ tạo OR khi có phần tử |
| Ghép `A OR B AND C` bằng chuỗi | Sai thứ tự/nhóm điều kiện | Dùng `AndFilter`/`OrFilter` lồng nhau |
| Dùng NOT mà quên attribute thiếu | Trả entry không có thuộc tính | Thêm `PresentFilter` khi nghiệp vụ yêu cầu |
| Bỏ qua size limit | Có thể coi kết quả bị cắt là đầy đủ | Giới hạn + kiểm tra completeness/paging |
| Dùng tài khoản admin để search | Lộ thêm thuộc tính/entry ngoài nhu cầu | Tài khoản chỉ đọc, ACL tối thiểu |
| Dùng `SUBTREE` vì “chắc ăn” | Tìm rộng hơn OU dự kiến | Scope phù hợp cây dữ liệu và hợp đồng nghiệp vụ |
| Coi `uid` là khóa duy nhất toàn forest | Nhầm entry giữa OU/naming context | Xác định DN/identity scope và khóa liên kết ổn định |
| Chỉ kiểm tra unit test | Không phát hiện sai ACL/TLS/schema | Thêm integration test với directory |

## 16. Bài tập nâng cao cho người học

Mở rộng chức năng để hỗ trợ **`givenName` tùy chọn** nhưng không làm thay đổi quyền truy cập:

1. Chỉ cho phép equality trên `givenName` trong OU `people`, không cho phép substring tùy ý.
2. Nếu cả `surname` và `givenName` được nhập, dùng AND; nếu nghiệp vụ yêu cầu tìm “một trong hai”, tạo nhóm OR riêng **và ghi rõ cấu trúc mong muốn**.
3. Bổ sung unit test với `givenName = "An)(objectClass=*)"` để xác nhận dữ liệu được escape, không tạo điều kiện mới.
4. Thêm một entry ở OU con để xác nhận ONELEVEL không bị thay đổi trong lúc mở rộng filter.
5. Giữ giới hạn số kết quả/timeout, thuộc tính response, account chỉ đọc và kiểm tra ACL.

**Tình huống phân quyền:** nếu người dùng A chỉ được xem nhân viên của đơn vị A, còn người dùng B xem đơn vị B, hãy mô tả cách ánh xạ đơn vị đã xác thực sang base DN và account/ACL phù hợp. Không giải bài bằng cách cho client gửi `baseDn` hoặc `filter` tùy ý.

**Tình huống hiệu năng:** nếu đội sản phẩm muốn hỗ trợ tìm bằng 500 giá trị `employeeType` qua OR, hãy đề xuất lại giới hạn và giao diện tìm kiếm dựa trên index, size limit, chi phí server, paging và mức ưu tiên nghiệp vụ. Không coi “đã escape” là lý do đủ để cho phép filter không giới hạn.

## 17. Checklist hoàn thành

Một lời giải đạt yêu cầu của bài thực hành phải trả lời được:

- [ ] Có **hợp đồng đầu vào** rõ ràng với những field/toán tử được phép.
- [ ] Có **validation chiều dài, số lượng, giá trị enum và điều kiện tối thiểu** trước khi gọi LDAP.
- [ ] Dùng **`EqualsFilter` hoặc builder LDAP** để escape giá trị; không nối raw LDAP filter.
- [ ] Biểu diễn **AND/OR/NOT/presence** bằng cây filter và kiểm thử nhóm ngoặc.
- [ ] Có **base DN, ONELEVEL scope, objectClass và danh sách thuộc tính cố định**.
- [ ] Dùng **read-only bind account**, ACL tối thiểu, LDAPS/StartTLS với chứng chỉ hợp lệ.
- [ ] Có **count/time limit**, kiểm tra lỗi cắt cụt và quy tắc không trả kết quả không đầy đủ như dữ liệu toàn bộ.
- [ ] Chỉ ánh xạ về **DTO cần thiết**, không lộ password/secret hoặc thuộc tính không được duyệt.
- [ ] Có **unit test escape/validation** và **integration test** về base, scope, ACL, schema và kết quả.
- [ ] Có metric, log phù hợp để theo dõi hiệu năng nhưng không đưa dữ liệu cá nhân vào log/label.

**Kết luận:** bộ lọc động an toàn trong Spring Data LDAP cần đồng thời **escape giá trị**, **allowlist cấu trúc truy vấn**, **giới hạn phạm vi directory** và **kiểm soát quyền thực tế trên LDAP server**. `LdapTemplate` cùng `AndFilter`, `OrFilter`, `NotFilter`, `PresentFilter` giúp tạo filter có cấu trúc; repository/ODM giúp ánh xạ entry phân cấp sang Java object. Chỉ khi kiểm thử cả logic filter lẫn directory thật, ứng dụng mới có thể mở tìm kiếm linh hoạt mà không mở quyền truy xuất hoặc làm quá tải LDAP.
