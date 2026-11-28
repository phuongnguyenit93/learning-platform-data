# SizeLimitExceededException và TimeLimitExceededException

Trong **Spring Data LDAP**, ứng dụng có thể tra cứu entry qua repository hoặc qua **`LdapTemplate` của Spring LDAP**. Một truy vấn đúng cú pháp, đúng `objectClass` và trả kết quả bình thường với vài trăm entry có thể gặp lỗi khi directory tăng lên hàng trăm nghìn entry. Hai trường hợp thường gặp là:

- **`SizeLimitExceededException`:** số entry mà thao tác tìm kiếm được phép trả về đã chạm hoặc vượt giới hạn trước khi có thể hoàn tất.
- **`TimeLimitExceededException`:** thời gian cho phép đối với search đã hết trước khi thao tác hoàn tất.

Điểm nguy hiểm không chỉ là xuất hiện exception. **Một phần kết quả có thể đã được gửi đến client trước khi giới hạn bị phát hiện**. Nếu ứng dụng bỏ qua lỗi rồi trả dữ liệu đó như một kết quả hoàn chỉnh, API danh bạ, quy trình đồng bộ hoặc nghiệp vụ phân quyền có thể ra quyết định sai.

Bài học này phân biệt chính xác hai giới hạn, chỉ ra cách chúng xuất hiện ở các tầng **LDAP → JNDI → Spring LDAP → Spring Data LDAP**, và hướng dẫn xử lý theo ý nghĩa nghiệp vụ thay vì chỉ `catch` rồi trả danh sách rỗng.

Sau bài học, bạn có thể:

1. Nhận diện LDAP result code **`timeLimitExceeded (3)`** và **`sizeLimitExceeded (4)`** theo RFC 4511.
2. Phân biệt exception **JNDI checked** với exception **Spring LDAP runtime** cùng tên.
3. Thiết lập `countLimit` và `timeLimit` trong `LdapQueryBuilder`/`SearchControls` đúng đơn vị và đúng kỳ vọng.
4. Giải thích tác động của **`LdapTemplate.setIgnoreSizeLimitExceededException(...)`**, nhất là giá trị mặc định.
5. Quyết định khi nào kết quả giới hạn có thể hiển thị một phần, khi nào phải **fail closed**, và khi nào nên phân trang.
6. Chẩn đoán nguyên nhân filter/index, search scope, server policy, pool hay network timeout thay vì retry mù quáng.
7. Thiết kế logging, metric, phản hồi API và kiểm thử tích hợp để không che giấu kết quả thiếu.

## 1. Một thao tác LDAP Search có những giới hạn nào?

Giả sử một LDAP directory phục vụ cây:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   ├── uid=minh
│   ├── uid=mai
│   └── ... hàng chục nghìn người dùng
├── ou=groups
└── ou=services
```

Ứng dụng muốn tìm các entry `inetOrgPerson` trong `ou=people`:

```text
Search base : ou=people,dc=example,dc=org
Scope       : SUBTREE
Filter      : (objectClass=inetOrgPerson)
Attributes  : uid, cn
Size limit  : 100 entries
Time limit  : 2 seconds (mức giao thức, xem giải thích phía dưới)
```

LDAP SearchRequest có các tham số chính:

| Tham số | Chức năng | Nếu chọn sai |
| --- | --- | --- |
| `baseObject` | DN gốc của vùng tìm | Tìm sai nhánh hoặc không tìm thấy entry |
| `scope` | Base, con trực tiếp hay toàn subtree | Quét nhiều OU ngoài nhu cầu |
| `filter` | Biểu thức điều kiện entry | Khớp quá rộng hoặc không tận dụng index |
| `attributes` | Thuộc tính muốn nhận | Tải nhiều dữ liệu hơn cần thiết |
| `sizeLimit` | Giới hạn **số entry kết quả** | Search bị cắt trước khi hoàn tất |
| `timeLimit` | Giới hạn **thời gian tìm kiếm** | Search kết thúc trước khi hoàn tất |

**Size limit không phải giới hạn kích thước byte của một entry.** Một entry có `jpegPhoto` 3 MiB vẫn chỉ là **một entry**, nhưng có thể làm mạng/JVM chậm hoặc tăng bộ nhớ. **Time limit cũng không phải toàn bộ HTTP timeout**, và chưa chắc bao gồm mọi thời gian chờ connection pool, TLS hay xử lý Java.

### 1.1. Ai có thể đặt giới hạn?

Giới hạn có thể xuất hiện ở nhiều tầng:

```text
HTTP/API deadline
       │
       ▼
Spring service / repository / LdapTemplate
       │    LdapQuery.countLimit(...)
       │    LdapQuery.timeLimit(...)
       ▼
JNDI SearchControls
       │    countLimit, timeLimit
       ▼
LDAP SearchRequest
       │    sizeLimit, timeLimit
       ▼
Directory server
       │    giới hạn do client yêu cầu
       │    và chính sách server/ACL/administrative limits
       ▼
SearchResultEntry* → SearchResultDone (result code)
```

Một client yêu cầu 1.000 entry nhưng server áp trần 500 entry vẫn có thể bị giới hạn ở 500. Ngược lại, client tự yêu cầu 100 entry dù server cho phép nhiều hơn thì ứng dụng phải hiểu mình đã **chủ động đặt giới hạn kết quả**. Giá trị `0` ở cấu hình JNDI/Spring LDAP thường nghĩa là **không đặt giới hạn phía client**, **không** phải yêu cầu server bỏ mọi giới hạn quản trị.

## 2. Hai LDAP result code theo RFC 4511

LDAP giao tiếp bằng message. Trong một search, server có thể gửi nhiều `SearchResultEntry` rồi gửi `SearchResultDone` chứa kết quả cuối.

```text
LDAP client                          LDAP server
    |---- SearchRequest ---------------->|
    |<--- SearchResultEntry #1 ---------|
    |<--- SearchResultEntry #2 ---------|
    |<--- ... --------------------------|
    |<--- SearchResultDone ------------ |
               resultCode = 3 hoặc 4
```

| Result code | Tên LDAP | Ý nghĩa |
| --- | --- | --- |
| `0` | `success` | Search hoàn thành theo các điều kiện được thực thi |
| **`3`** | **`timeLimitExceeded`** | Search vượt thời hạn được áp dụng trước khi có thể hoàn thành |
| **`4`** | **`sizeLimitExceeded`** | Search vượt giới hạn số entry được phép trả trước khi hoàn thành |

RFC 4511 mô tả mã **3** và **4** trong ngữ cảnh giới hạn do client yêu cầu; trong triển khai thực tế, server cũng có thể áp dụng giới hạn quản trị và trả các mã này hoặc cách báo lỗi đặc thù. Luôn xác minh hành vi của **sản phẩm LDAP/phiên bản/cấu hình** đang sử dụng.

### 2.1. SizeLimitExceededException trong thực tế

Ví dụ giả định:

```text
Directory có 20.000 người dùng.
Filter:        (objectClass=inetOrgPerson)
Client limit:  100

Client nhận được một số SearchResultEntry,
sau đó bị báo kết quả chưa hoàn tất vì giới hạn số entry.
```

Không có bảo đảm rằng 100 entry đã nhận là “100 người đầu tiên” theo một thứ tự ổn định. **LDAP Search thông thường không tự bảo đảm thứ tự kết quả**. Nếu cần sắp xếp hoặc phân trang có trật tự, phải dùng khả năng phù hợp của server và thiết kế thứ tự/id ổn định.

### 2.2. TimeLimitExceededException trong thực tế

Ví dụ giả định:

```text
Filter:      (cn=*an*)
Scope:       SUBTREE
Time limit:  2.000 ms phía Spring/JNDI
Directory:   hàng trăm nghìn entry

Server hoặc JNDI xác định thời gian cho phép đã hết
trước khi trả trọn tập kết quả.
```

Một filter chứa `*an*` có thể rất ít chọn lọc nếu thiếu substring index phù hợp; server phải duyệt nhiều ứng viên. Nhưng **không được suy ra mọi time limit đều do thiếu index**: backend quá tải, referral, network, kích thước kết quả hoặc giới hạn server có thể đóng vai trò.

### 2.3. Kết quả đã nhận không chứng minh search hoàn chỉnh

Đối với cả hai lỗi:

- Một số entry **có thể đã được gửi** trước kết quả cuối.
- Ứng dụng có thể đã chạy callback hoặc mapper trên các entry đó.
- Nếu method ném exception, caller có thể không nhận được `List<T>` bình thường.
- Nếu exception bị bỏ qua, caller có thể nhận một danh sách **không đầy đủ** nhưng không thấy tín hiệu lỗi.

Vì thế, “có 80 phần tử trong list” **không** chứng minh directory chỉ có 80 entry khớp.

## 3. Exception JNDI và Spring LDAP có cùng tên nhưng khác package

Ở tầng Java, hai nhóm exception rất dễ bị import nhầm.

### 3.1. JNDI: checked exceptions

```java
javax.naming.SizeLimitExceededException
javax.naming.TimeLimitExceededException
```

Chúng thuộc `javax.naming`, kế thừa qua `javax.naming.LimitExceededException` và cuối cùng từ `javax.naming.NamingException`. Đây là **checked exceptions** của API JNDI, phải được xử lý hoặc khai báo khi dùng trực tiếp các API ném `NamingException`.

### 3.2. Spring LDAP: runtime exceptions

```java
org.springframework.ldap.SizeLimitExceededException
org.springframework.ldap.TimeLimitExceededException
```

Chúng thuộc `org.springframework.ldap`, kế thừa từ `org.springframework.ldap.LimitExceededException` và hệ phân cấp runtime exception của Spring LDAP. `LdapTemplate` thường chuyển lỗi JNDI sang Spring LDAP exception tương ứng để người gọi không phải trực tiếp quản lý exception checked.

| Nguồn lỗi | Loại exception | Kiểu Java | Thường gặp khi |
| --- | --- | --- | --- |
| JNDI | `javax.naming.SizeLimitExceededException` | Checked | Gọi `DirContext.search(...)`/duyệt enumeration trực tiếp |
| JNDI | `javax.naming.TimeLimitExceededException` | Checked | Dùng `SearchControls` trực tiếp |
| Spring LDAP | `org.springframework.ldap.SizeLimitExceededException` | Runtime | Search qua `LdapTemplate` và lỗi không bị bỏ qua |
| Spring LDAP | `org.springframework.ldap.TimeLimitExceededException` | Runtime | Search qua `LdapTemplate`, được dịch từ lỗi JNDI phù hợp |

**Đừng viết `catch (javax.naming.TimeLimitExceededException ex)` quanh `ldapTemplate.search(...)` rồi tin rằng sẽ bắt được lỗi Spring LDAP.** Phải import đúng loại exception thuộc `org.springframework.ldap`.

### 3.3. Ví dụ bắt exception đúng package

```java
import org.springframework.ldap.SizeLimitExceededException;
import org.springframework.ldap.TimeLimitExceededException;

try {
    // ldapTemplate.search(...) hoặc lời gọi liên quan.
} catch (SizeLimitExceededException ex) {
    // Search không hoàn chỉnh vì giới hạn số entry.
} catch (TimeLimitExceededException ex) {
    // Search không hoàn chỉnh vì thời hạn tìm kiếm.
}
```

Nếu cần phân tích sâu, có thể kiểm tra `ex.getCause()`, log server và thông tin LDAP result code do provider cung cấp. Không giả định mọi ngoại lệ mạng đều được chuyển thành `TimeLimitExceededException`; phần timeout mạng được phân biệt ở mục 7.

## 4. countLimit và timeLimit trong LdapQueryBuilder

Spring LDAP cung cấp `LdapQueryBuilder` để chọn base/scope/filter và giới hạn tìm kiếm.

```java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn")
        .countLimit(100)
        .timeLimit(2_500)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("lan");
```

Giả sử `LdapContextSource` base `dc=example,dc=org`, thì `.base("ou=people")` chọn nhánh tương đối. Mục tiêu code là thể hiện **giới hạn tại query**, không phải chạy benchmark.

| API | Tham số | Đơn vị | Giá trị 0 |
| --- | --- | --- | --- |
| `LdapQueryBuilder.countLimit(int)` | Số entry tối đa | Entry | Không đặt giới hạn phía client |
| `LdapQueryBuilder.timeLimit(int)` | Thời gian search | **Millisecond** | Không đặt giới hạn phía client |
| `SearchControls.setCountLimit(long)` | Số kết quả trả về | Entry | Không đặt giới hạn phía client |
| `SearchControls.setTimeLimit(int)` | Thời gian search | **Millisecond** | Không đặt giới hạn phía client |
| LDAP `SearchRequest.sizeLimit` | Giới hạn kết quả trên giao thức | Entry | Không có giới hạn do client yêu cầu |
| LDAP `SearchRequest.timeLimit` | Thời gian tối đa trên giao thức | **Giây** | Không có giới hạn do client yêu cầu |

**Phân biệt đơn vị cực kỳ quan trọng:** `.timeLimit(2_500)` trong Spring LDAP là **2.500 ms**, không phải 2.500 giây. Giao thức LDAP biểu diễn time limit theo **giây**; cách JNDI/provider chuyển hoặc áp dụng mức millisecond có thể phụ thuộc triển khai. Không kỳ vọng một timeout millisecond rất nhỏ được server thực thi chính xác từng millisecond trong mọi directory.

### 4.1. Cấu hình mặc định ở LdapTemplate

```java
import org.springframework.ldap.core.LdapTemplate;

LdapTemplate ldapTemplate = new LdapTemplate(contextSource);
ldapTemplate.setDefaultCountLimit(0);    // Không đặt limit mặc định phía client.
ldapTemplate.setDefaultTimeLimit(2_500); // 2,5 giây cho search không override.
```

Những giá trị này áp dụng khi search không chỉ định giới hạn riêng. LdapQuery chỉ rõ `countLimit`/`timeLimit` có thể ghi đè thiết lập tương ứng của template.

**Không thay đổi cấu hình mặc định của một `LdapTemplate` singleton theo từng HTTP request** để phục vụ hai người dùng khác nhau; việc đó tạo cấu hình mutable chia sẻ giữa thread. Hãy đặt chính sách nhất quán ở bean hoặc dùng limit theo từng `LdapQuery`.

### 4.2. Lưu ý filter và quyền

Giới hạn chỉ là **hàng rào tải**, không thay thế filter chính xác:

```ldap
# Bỏ quá nhiều entry có thể là kết quả của filter rộng:
(objectClass=inetOrgPerson)

# Tìm đúng mã người dùng thì dùng equality:
(&(objectClass=inetOrgPerson)(uid=lan))
```

Với input từ client, dùng `where("uid").is(userInput)` hoặc API có escaping để tránh LDAP filter injection. Đừng tạo filter bằng `"(uid=" + userInput + ")"`: dấu `*`, ngoặc và dấu gạch chéo ngược có thể thay đổi ý nghĩa truy vấn.

## 5. Điểm bẫy lớn: LdapTemplate mặc định bỏ qua SizeLimitExceededException

Theo Javadoc chính thức của `LdapTemplate.setIgnoreSizeLimitExceededException(boolean)`, thuộc tính **`ignoreSizeLimitExceededException` có giá trị mặc định `true`** trong các phiên bản được tài liệu hóa hiện hành.

```java
// LdapTemplate thông thường có hành vi mặc định:
// ignoreSizeLimitExceededException = true
```

Điều này có lý do lịch sử: khi client **cố ý giới hạn số entry** để hiển thị kết quả ngắn, một số server/JNDI báo `SizeLimitExceededException` lúc chạm giới hạn; người dùng thường muốn nhận những entry đã tìm thấy thay vì toàn bộ thao tác ném lỗi.

Nhưng hệ quả với ứng dụng **đòi hỏi tập kết quả đầy đủ** là nghiêm trọng:

```text
Danh sách LDAP thực tế:  10.000 entries
Client/server giới hạn:   500 entries
LdapTemplate:             ignoreSizeLimitExceededException = true

Method search có thể trả danh sách entries đã đọc,
trong khi 9.500 entries còn lại chưa được duyệt.

Nếu caller hiểu đó là danh sách ĐẦY ĐỦ → sai nghiệp vụ.
```

**Không được mặc định một `List<T>` được trả về không exception là bằng chứng search hoàn thành toàn bộ.** Việc bỏ qua lỗi size limit là một lựa chọn **ngữ nghĩa** của ứng dụng, không chỉ lựa chọn “giảm noise trong log”.

### 5.1. Khi nào có thể cho phép bỏ qua?

Ví dụ **autocomplete** chỉ hiển thị một số kết quả đầu, UI ghi rõ “tối đa 20 kết quả”, không khẳng định danh sách đầy đủ. Trong trường hợp này, việc chấp nhận một tập được giới hạn **có thể đúng với hợp đồng API**, miễn đã kiểm tra server có cho phép thao tác và xử lý rõ `hasMore/possiblyTruncated`.

Nhưng đối với:

- Xác định **tất cả** nhóm mà user thuộc về để tính quyền.
- Đồng bộ **toàn bộ** danh sách nhân viên sang hệ thống khác.
- Kiểm tra không còn entry nào phụ thuộc một OU trước khi xóa.
- Thống kê tuân thủ hoặc kiểm tra dữ liệu không được thiếu.
- Batch cần áp dụng cùng một thay đổi cho **mọi** entry khớp.

thì việc lặng lẽ nhận dữ liệu một phần **không chấp nhận được**. Cần fail closed hoặc dùng một quy trình phân trang/tìm kiếm hoàn chỉnh có xác minh.

### 5.2. Muốn không bỏ qua size limit thì cấu hình false

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;

@Configuration
public class StrictLdapConfiguration {

    @Bean("strictDirectoryLdapTemplate")
    public LdapTemplate strictDirectoryLdapTemplate(
            BaseLdapPathContextSource contextSource) {

        LdapTemplate template = new LdapTemplate(contextSource);
        template.setIgnoreSizeLimitExceededException(false);
        return template;
    }
}
```

Giả định ứng dụng đã có bean `BaseLdapPathContextSource` sử dụng LDAPS/StartTLS và principal phù hợp. Bean này được đặt tên riêng để chỉ dùng ở nơi yêu cầu **phát hiện search chưa hoàn tất**. Nếu Spring Boot tự tạo một `LdapTemplate` khác, phải xác minh service/repository **thực sự dùng bean nghiêm ngặt**; khai báo bean mới nhưng tiếp tục inject bean cũ có thể không đổi hành vi thực tế.

**Cấu hình `false` không bảo đảm mọi cơ chế giới hạn đều ném chính xác exception này.** Một số server có thể cắt kết quả hoặc dùng response/control khác; cần kiểm thử với directory thật và xem log server. Ngoài ra, count limit do client tự đặt vẫn là sự thật nghiệp vụ: một truy vấn trả đúng 100 entry khi limit=100 **không chứng minh** chỉ có 100 entry khớp.

### 5.3. Không nhầm với PartialResultException

`LdapTemplate` còn có:

```java
template.setIgnorePartialResultException(true);
```

Điều này chủ yếu liên quan **`PartialResultException` do referral**, đặc biệt trong một số trường hợp Active Directory, **không phải** thay thế cho `setIgnoreSizeLimitExceededException(...)` và cũng không khắc phục `TimeLimitExceededException`.

Tên “partial result” rất dễ gây nhầm: danh sách thiếu vì **size/time limit** và exception kiểu `PartialResultException` của JNDI/Spring LDAP là **hai vấn đề khác nhau**. Không bật các tùy chọn ignore hàng loạt chỉ để cho API ngừng báo lỗi.

## 6. Thiết kế service xử lý rõ hai exception

Ví dụ dưới đây dành cho **Spring LDAP 3.x**, Java 17+, với bean `LdapTemplate` đã được cấu hình **`setIgnoreSizeLimitExceededException(false)`** ở phần trước.

### 6.1. Mô hình lỗi nghiệp vụ

Không nên để API tầng trên tự kết luận từ một `List<T>` rỗng rằng “không tìm thấy dữ liệu”. Ta định nghĩa một lỗi riêng thể hiện **kết quả chưa đầy đủ**.

```java
public enum DirectorySearchLimit {
    SIZE,
    TIME
}

public final class DirectorySearchIncompleteException
        extends RuntimeException {

    private final DirectorySearchLimit limit;

    public DirectorySearchIncompleteException(
            DirectorySearchLimit limit, Throwable cause) {
        super("LDAP search was not completed: " + limit, cause);
        this.limit = limit;
    }

    public DirectorySearchLimit getLimit() {
        return limit;
    }
}
```

Hai class là các ví dụ **độc lập**, nên đặt trong hai file Java tương ứng nếu cùng package và đều khai báo `public`. Thông điệp lỗi có **loại giới hạn**, không chứa raw filter hoặc định danh người dùng.

### 6.2. Service với query được giới hạn

```java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.SizeLimitExceededException;
import org.springframework.ldap.TimeLimitExceededException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

record PersonSummary(String uid, String fullName) {}

public class DirectoryPeopleSearch {
    private final LdapTemplate ldapTemplate;

    public DirectoryPeopleSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> searchBySurnamePrefix(String prefix) {
        if (prefix == null || prefix.trim().length() < 3) {
            throw new IllegalArgumentException("Prefix is too short");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn")
                .countLimit(200)
                .timeLimit(2_500)
                .filter("(&(objectClass=inetOrgPerson)(sn={0}*))", prefix);

        try {
            return ldapTemplate.search(query,
                    (AttributesMapper<PersonSummary>) attrs ->
                            new PersonSummary(
                                    getText(attrs, "uid"),
                                    getText(attrs, "cn")));
        } catch (SizeLimitExceededException ex) {
            throw new DirectorySearchIncompleteException(
                    DirectorySearchLimit.SIZE, ex);
        } catch (TimeLimitExceededException ex) {
            throw new DirectorySearchIncompleteException(
                    DirectorySearchLimit.TIME, ex);
        }
    }

    private static String getText(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        return attr == null || attr.size() == 0
                ? null
                : (String) attr.get();
    }
}
```

**Giải thích kỹ thuật:**

- `.filter("...{0}*", prefix)` dùng **tham số được escape** ở vị trí giá trị, còn dấu `*` do ứng dụng đặt cố định để chủ động tìm tiền tố. Không ghép `prefix` trực tiếp vào LDAP filter.
- `.countLimit(200)` giới hạn số entry; `.timeLimit(2_500)` giới hạn search **2,5 giây** phía Spring/JNDI.
- Search trả thành công khi server/provider không báo lỗi giới hạn; nhưng nếu đã chạm đúng ngưỡng 200, kết quả **vẫn không tự chứng minh** đã gồm hết mọi entry có thể khớp.
- Khi giới hạn được báo bằng exception, service **không trả danh sách rỗng** và không gắn nhãn “không có người dùng”.
- Caller nhận một lỗi được phân loại, có thể chuyển thành mã API phù hợp mà không tiết lộ DN/filter.
- Ví dụ `getText` xử lý attribute không tồn tại; ứng dụng thật cần policy cho các field bị ACL che giấu, `null` và dữ liệu sai schema.

**Chú ý:** Spring LDAP có thể dùng `LdapTemplate` khác cho repository. Nếu service dùng `LdapRepository<Person>`, khả năng ném và bỏ qua size limit phụ thuộc `LdapTemplate`/`LdapOperations` mà repository thực sự sử dụng. Đừng chỉ thay đổi một bean không được đường gọi nào tham chiếu.

### 6.3. Không gộp hai lỗi thành “Không tìm thấy”

| Tình huống | Phản hồi tầng nghiệp vụ nên thể hiện |
| --- | --- |
| Search hoàn tất và trả 0 entry | “Không tìm thấy entry phù hợp” |
| Có size limit, kết quả chưa đủ | “Truy vấn trả nhiều kết quả hơn giới hạn; cần thu hẹp/phân trang” |
| Có time limit, kết quả chưa đủ | “Không hoàn tất truy vấn trong thời hạn; hãy thử lại hoặc giảm phạm vi” |
| Không thể kết nối LDAP server | “Directory tạm thời không sẵn sàng” |
| LDAP server từ chối vì ACL | “Không được phép truy xuất”, hoặc lỗi được bảo vệ theo chính sách |

Mã HTTP **không có ánh xạ chuẩn một-một** từ LDAP result code. Với search quá rộng, một API có thể chọn `400/422` nếu chính sách yêu cầu client giảm phạm vi; với hạ tầng quá tải, có thể chọn `503` hoặc `504` theo SLA và gateway thực tế. **Không dùng `413 Payload Too Large` chỉ vì số entry LDAP vượt size limit**: `413` liên quan kích thước payload HTTP request, không phải số entry tìm thấy ở backend.

## 7. TimeLimitExceededException khác timeout kết nối/mạng

“Timeout” là tên gọi chung cho nhiều sự cố, nhưng chúng xuất hiện ở những giai đoạn khác nhau:

```text
HTTP request bắt đầu
   │
   ├── Chờ lấy context từ pool
   │      └── pool borrow timeout (nếu pool có giới hạn chờ)
   │
   ├── Mở kết nối TCP/TLS, bind
   │      └── connection timeout / handshake/auth failure
   │
   ├── DirContext.search(...)
   │      ├── timeLimit của SearchRequest/SearchControls
   │      │      └── TimeLimitExceededException
   │      └── read/socket timeout của JNDI/provider
   │             └── thường là communication/provider exception
   │
   └── Mapping dữ liệu và xử lý HTTP
          └── application/API deadline
```

| Giới hạn | Vị trí cấu hình | Đơn vị | Khi quá hạn có thể thấy |
| --- | --- | --- | --- |
| Search time limit | `LdapQueryBuilder.timeLimit(int)` | ms | `TimeLimitExceededException` |
| JNDI search time limit | `SearchControls.setTimeLimit(int)` | ms | JNDI `TimeLimitExceededException` |
| Connect timeout | `java.naming.ldap.connect.timeout` | ms dưới dạng string | `CommunicationException`/provider error |
| Read timeout | `java.naming.ldap.read.timeout` | ms dưới dạng string | `CommunicationException`/I/O/provider error |
| Pool borrow timeout | Cấu hình của pool | Theo API pool | Pool exhaustion hoặc pool-specific exception |
| HTTP/request deadline | Server/framework/gateway | Theo framework | Client disconnect, gateway timeout hoặc cancellation |
| Server administrative time limit | Directory server | Tùy sản phẩm | LDAP result code 3 hoặc hành vi liên quan |

Ví dụ cấu hình JNDI thông qua `LdapContextSource`:

```java
import java.util.Map;
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://directory.example.org:636");
source.setBase("dc=example,dc=org");
source.setBaseEnvironmentProperties(Map.of(
        "java.naming.ldap.connect.timeout", "3000",
        "java.naming.ldap.read.timeout", "5000"
));
// Bổ sung bind DN/credential qua secret store và cấu hình TLS đúng.
```

**Giới hạn search không thay thế timeout mạng, và timeout mạng không thay thế giới hạn xử lý search.** Kết nối TLS phải xác minh chứng chỉ/hostname; không vô hiệu xác minh để “giảm timeout”. Các giá trị trong ví dụ là lựa chọn minh họa, cần được chọn theo độ trễ thực, deadline API và khả năng của directory.

### 7.1. Vì sao timeLimitExceeded không có nghĩa server “down”?

Nếu `(uid=lan)` được index và tìm trong `ou=people`, search có thể rất nhanh. Nhưng `(cn=*an*)` trên toàn naming context không có substring index có thể gây quét rất lớn. Khi đó tăng `timeLimit` lên gấp đôi đôi khi chỉ làm hệ thống chịu tải lâu hơn, không giải quyết nguyên nhân.

Các bước điều tra:

1. Kiểm tra filter thực tế (ẩn giá trị nhạy cảm khi ghi log).
2. Giới hạn search base vào OU nghiệp vụ và chọn `ONELEVEL`/`SUBTREE` đúng nhu cầu.
3. Kiểm tra equality/substring index theo backend, schema và matching rule.
4. Quan sát số entry khớp và số entry được xét nếu server log hỗ trợ.
5. Kiểm tra pool wait, connect/read timeout và thời gian mapping Java.
6. Chỉ điều chỉnh giới hạn time sau khi có dữ liệu đo đạc.

## 8. Khác biệt giữa “trả tối đa N entry” và “lấy toàn bộ entry”

Hai yêu cầu này có hợp đồng khác nhau.

### 8.1. Trường hợp UI chấp nhận giới hạn

Một ô tìm kiếm người dùng chỉ hiển thị **20 kết quả**. API có thể trả:

```json
{
  "items": [
    {"uid": "lan", "fullName": "Nguyen Thi Lan"}
  ],
  "limit": 20,
  "complete": false,
  "message": "Kết quả được giới hạn; vui lòng lọc cụ thể hơn"
}
```

JSON chỉ mang tính minh họa về **hợp đồng phản hồi**. Giá trị `complete=false` phải được quyết định từ **tín hiệu đáng tin cậy**, không đơn giản vì số kết quả lớn. Nếu ứng dụng chỉ nhận tối đa 20 entry nhưng không biết còn entry khác hay không, dùng trạng thái như `"completeness": "unknown"` thay vì khẳng định đầy đủ hoặc thiếu một cách không có cơ sở.

Với UI hữu hạn, có thể chấp nhận danh sách được cắt nếu công khai giới hạn và không dùng nó cho nghiệp vụ đòi hỏi tập đầy đủ.

### 8.2. Trường hợp cần kết quả hoàn chỉnh

Đồng bộ tất cả user, kiểm tra membership phân quyền, xuất dữ liệu pháp lý hoặc xóa subtree sau khi kiểm tra phụ thuộc đều cần **tính toàn vẹn của kết quả**. Chiến lược nên là:

- Dùng query chọn lọc và index thích hợp.
- Nếu có nhiều entry, dùng **LDAP paged results control** được server hỗ trợ.
- Chỉ coi việc đọc hoàn tất khi có tín hiệu **không còn trang tiếp theo** và không phát sinh lỗi giới hạn.
- Khi server trả lỗi hoặc response không đầy đủ, không kết luận “đã kiểm tra xong”.

**Chia truy vấn thành nhiều nhánh OU không tự tạo snapshot nhất quán**: trong lúc đọc, entry có thể được thêm/xóa/di chuyển. Nếu cần tính nhất quán nghiêm ngặt tại một thời điểm, phải xem khả năng snapshot/transaction/chính sách đồng bộ của directory thực tế.

## 9. Phân trang LDAP để vượt giới hạn một trang, không bỏ qua lỗi

**RFC 2696 — Simple Paged Results** định nghĩa một request control để nhận các kết quả theo trang và một **cookie opaque** do server cấp cho lượt tiếp theo.

```text
Search page 1: pageSize=100, cookie=empty
   -> 100 entries + responseCookie=A

Search page 2: pageSize=100, cookie=A
   -> 100 entries + responseCookie=B

Search page 3: pageSize=100, cookie=B
   -> 12 entries + responseCookie=empty

Client xác định không còn trang khác
```

Giả định trong sơ đồ là directory có 212 entry nhìn thấy được và server thực hiện control đúng chuẩn. Cookie là **dữ liệu opaque**, không được parse hoặc tự chế từ `uid`/DN. Server có thể trả **ước lượng** tổng số entry hoặc không trả ước lượng; không dùng `getResultSize()` như số đếm tuyệt đối.

### 9.1. Spring LDAP có DirContextProcessor cho paging

Trong Spring LDAP, các lớp phù hợp gồm:

- `PagedResultsDirContextProcessor` (có ở nhiều phiên bản Spring LDAP; phiên bản mới có thể đánh dấu deprecated).
- `PagedResultsControlExchangeDirContextProcessor` ở các phiên bản có API mới hơn.
- `SingleContextSource` để giữ **cùng một kết nối cơ sở** trong chuỗi request paging.

**Ví dụ sau dùng API `PagedResultsDirContextProcessor` phổ biến**; hãy đối chiếu Javadoc với phiên bản dự án:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.control.PagedResultsDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.SingleContextSource;

public List<String> readPersonUids(ContextSource source) {
    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setReturningAttributes(new String[] {"uid"});

    PagedResultsDirContextProcessor processor =
            new PagedResultsDirContextProcessor(100);

    return SingleContextSource.doWithSingleContext(source, operations -> {
        List<String> all = new ArrayList<>();
        do {
            List<String> page = operations.search(
                    "ou=people",
                    "(objectClass=inetOrgPerson)",
                    controls,
                    (AttributesMapper<String>) attrs ->
                            (String) attrs.get("uid").get(),
                    processor);
            all.addAll(page);
        } while (processor.hasMore());
        return all;
    });
}
```

Ví dụ làm rõ nguyên lý **lặp theo `hasMore()` và tái sử dụng cùng context**; nó chủ động gom `all` vào bộ nhớ cho dễ hiểu. Trong sản phẩm thật, không giữ một `List` vô hạn: hãy giới hạn tổng số trang/entry theo hợp đồng, xử lý từng trang, kiểm soát backpressure và có cơ chế resume/checkpoint phù hợp.

**Các điều kiện để paging đáng tin cậy:**

1. Directory phải hỗ trợ RFC 2696; server/ACL có thể giới hạn việc phân trang.
2. **Cookie và kết nối phải được quản lý đúng** theo yêu cầu provider/server; Spring LDAP hướng dẫn `SingleContextSource` hoặc context phù hợp.
3. Phải lặp với **cùng search base/filter/controls** trong một chuỗi paging (ngoại trừ phần page cookie/pageSize cho phép).
4. Chỉ hoàn thành khi response cookie cho thấy **không còn trang**, không có lỗi giới hạn.
5. Page size không phải cách vượt qua mọi trần server; nếu server từ chối, phải điều chỉnh query/quyền/cấu hình theo chính sách.
6. Nếu dữ liệu thay đổi giữa các trang, có thể có trùng/bỏ sót theo cơ chế directory; cần thiết kế thêm nếu nghiệp vụ yêu cầu snapshot.
7. Nếu processor bị dừng vì lỗi giữa chừng, **các trang đã xử lý là một kết quả dở dang**, không tự xem là đồng bộ thành công.

### 9.2. Phân biệt paging với countLimit

| Cơ chế | Ý nghĩa | Có tự lấy toàn bộ directory? |
| --- | --- | --- |
| `countLimit(100)` | Chỉ yêu cầu tối đa 100 entry trong một search | **Không** |
| `timeLimit(2_500)` | Hạn chế thời gian một search | **Không** |
| `PagedResults...Processor(100)` | Yêu cầu theo trang 100 entry khi server hỗ trợ | **Chưa**, phải duyệt cookie cho tới khi hết |
| `SingleContextSource` | Giữ context/connection phù hợp giữa các trang | Không thay thế vòng lặp paging |

Không cố lấy tất cả dữ liệu bằng cách tăng `countLimit` lên giá trị cực lớn; server vẫn có giới hạn quản trị và ứng dụng có thể hết bộ nhớ. Paging có kiểm soát giúp giảm dữ liệu mỗi lượt, nhưng cũng phải có giới hạn thời gian và số trang ở cấp nghiệp vụ.

## 10. Xử lý dữ liệu một phần trong callback/stream

Với `LdapTemplate.search(query, AttributesMapper<T>)`, ứng dụng thường chỉ nhận `List<T>` sau khi search kết thúc. Nhưng `LdapTemplate` còn có **callback handler** hoặc API stream, và dữ liệu có thể được xử lý dần:

```text
LDAP server trả entry #1  → callback ghi vào DB
LDAP server trả entry #2  → callback ghi vào DB
...
LDAP server báo timeLimitExceeded ở entry #95

Đã ghi 94 entry vào DB; search tổng thể thất bại.
```

Khi đó:

- Catch exception **không rollback** các thao tác I/O/DB mà callback đã thực hiện.
- Một bộ xử lý đồng bộ cần **idempotency** theo ID ổn định, checkpoint và khả năng retry/reconcile.
- Không gửi sự kiện “sync_completed” trước khi chắc chắn đã duyệt hết nguồn dữ liệu.
- Không xóa các entry đích “không xuất hiện trong batch” nếu batch có thể thiếu dữ liệu.
- Với thao tác truy vấn phục vụ quyền, không giữ các role có vẻ tìm thấy rồi coi mọi nhóm khác không tồn tại.

**Size/time limit của một search là vấn đề hoàn chỉnh dữ liệu**, không chỉ là exception Java cần log.

## 11. Chiến lược retry: đừng lặp lại cùng truy vấn rộng

Không phải lỗi nào cũng hợp lý để retry.

| Lỗi | Retry ngay cùng filter? | Hướng xử lý tốt hơn |
| --- | --- | --- |
| Size limit do quá nhiều entry | Thường **không** | Thu hẹp base/filter, phân trang, hoặc xin thay đổi policy được phê duyệt |
| Time limit do filter không có index | Thường **không** | Tối ưu filter/index/scope, giảm số kết quả |
| Time limit do server tải cao nhất thời | Có thể cân nhắc **hạn chế** | Retry có backoff/jitter, hạn số lần, deadline chung |
| Read/connect timeout mạng | Tùy nghiệp vụ và độ an toàn | Kiểm tra tình trạng server, retry đọc idempotent nếu phù hợp |
| ACL từ chối | **Không** | Sửa quyền được cấp hợp lệ hoặc nghiệp vụ |
| Invalid search base | **Không** | Sửa DN/base/referral |

**Retry không được vượt quá thời gian cam kết của API.** Nếu HTTP request có deadline 3 giây, một search mất 2,5 giây mà bị time limit không thể vô hạn retry trong request đó.

Với **thao tác ghi** như Add/Modify/Delete/Modify DN, timeout có thể xảy ra sau khi server đã nhận và áp dụng request nhưng trước khi client nhận phản hồi. Không retry mù quáng; phải đọc lại trạng thái entry và thiết kế idempotency/compensation. Chủ đề bài là **search size/time limit**, nhưng nguyên tắc này giúp tránh áp dụng cùng quy tắc retry lên mọi LDAP operation.

## 12. Logging, metrics và quan sát lỗi

Một lỗi search nên được ghi nhận đủ để điều tra mà không làm lộ dữ liệu cá nhân.

### 12.1. Những trường hữu ích

| Thông tin | Ví dụ | Ghi chú |
| --- | --- | --- |
| `ldap.operation` | `search` | Tập giá trị hữu hạn |
| `ldap.query.kind` | `people-by-prefix` | Mô tả loại filter, không ghi raw filter |
| `ldap.scope` | `subtree` | Giúp phát hiện query quá rộng |
| `ldap.branch` | `people` | Nhánh nghiệp vụ được allowlist |
| `ldap.limit.kind` | `size` / `time` | Phân biệt hai lỗi |
| `ldap.count.limit` | `200` | Giá trị cấu hình, không phải số kết quả thực tế |
| `ldap.time.limit.ms` | `2500` | Giúp so với p95/p99 |
| `traceId` | ID tương quan của request | Không dùng làm metric tag cardinality thấp |
| `durationMs` | Thời gian phía client | Có thể bao gồm overhead mạng |

**Không** đưa raw LDAP filter, password, `uid`, email, nhóm quyền nhạy cảm hoặc full DN vào log/metric labels một cách tùy tiện. Những giá trị đó có cardinality cao và có thể là dữ liệu cá nhân.

### 12.2. Đừng nhầm metric phía ứng dụng với log server

Một `TimeLimitExceededException` trong ứng dụng có thể liên quan:

- Search server thực thi lâu.
- Provider/JNDI giới hạn quá ngắn.
- Network/read timeout hoặc kết nối thiếu ổn định (có thể là exception khác).
- Pool cạn khiến tổng HTTP latency tăng, dù bản thân search không lâu.

Vì vậy hãy đo **HTTP latency**, **thời gian mượn context**, **LDAP operation latency**, **số kết quả** và **mã lỗi** riêng nếu hạ tầng observability hỗ trợ. LDAP server access log có thể cho biết operation time, limit, base/filter và số entry trả về, nhưng phải kiểm soát quyền xem và redaction.

### 12.3. Đặt cảnh báo theo xu hướng

Một dashboard thực tế có thể phân tách:

```text
ldap_search_requests_total{result="success"}
ldap_search_requests_total{result="size_limit"}
ldap_search_requests_total{result="time_limit"}
ldap_search_duration_seconds (p50/p95/p99)
ldap_pool_wait_duration_seconds
```

Đây là **tên metric minh họa do ứng dụng tự đặt**, không phải metric được Spring Data LDAP mặc định xuất với chính xác các tên này. Khi cảnh báo tỷ lệ lỗi tăng, kiểm tra cùng thời điểm các thay đổi schema/index, lượng dữ liệu, release code và chính sách server.

## 13. Bảng chẩn đoán nhanh

| Triệu chứng | Giải thích có thể | Bước kiểm tra đầu tiên |
| --- | --- | --- |
| Search trả đúng 100 entry mọi lần | Client countLimit 100 hoặc server cap 100 | Kiểm tra giới hạn và có chứng cứ completeness không |
| Search trả 100 entry, không exception | `ignoreSizeLimitExceededException=true` hoặc server trả success tại ngưỡng | Kiểm tra template setting và thử dữ liệu vượt limit |
| Catch `SizeLimitExceededException` không chạy | Import JNDI sai package hoặc template đang ignore | Kiểm tra `org.springframework.ldap.*` và ignore flag |
| Có `TimeLimitExceededException` với filter `*term*` | Query quá rộng, thiếu substring index hoặc server quá tải | Đo filter/base/scope/index |
| Timeout mạng nhưng không vào catch time limit | Connect/read timeout thường là communication/provider exception | Kiểm tra JNDI env và nguyên nhân lỗi |
| HTTP deadline 2 giây dù query timeLimit 5 giây | Gateway/application deadline khác search deadline | Điều chỉnh deadline nhất quán |
| `.timeLimit(2)` không cho kết quả mong muốn | Nhầm milliseconds với seconds | Dùng `2_000` cho 2 giây |
| Thêm paging nhưng vẫn thiếu kết quả | Không lặp cookie, kết nối thay đổi hoặc server áp cap | Kiểm tra response cookie/processor và giới hạn server |
| Paging trả tổng 0 nhưng vẫn có entry | Tổng ước lượng từ control có thể không được server cung cấp | Không dựa `getResultSize()` làm số đếm |
| Đếm số người bằng `search(...).size()` với count limit | Chỉ đếm kết quả đã nhận, không phải toàn directory | Chọn strategy đếm đúng và phạm vi có kiểm soát |
| Mất kết quả khi user chuyển OU | Search base chỉ bao gồm nhánh cũ | Kiểm tra DN/OU và search scope |
| Search chậm sau khi thêm pool | Pool không cải thiện filter/index và server query | Đo thời gian chờ pool riêng với server time |
| API “không có nhóm” sau timeout | Lỗi đã bị quy về list rỗng | Fail closed, giữ lỗi nghiệp vụ riêng |

## 14. Kiểm thử tích hợp với directory test

Để kiểm thử thật, cần directory thử nghiệm có **đủ entry**, ACL và chính sách limit mà bạn kiểm soát. Không thử thay giới hạn trên LDAP server production chỉ để tái hiện lỗi.

### 14.1. Bộ dữ liệu

Tạo:

```text
dc=example,dc=org
└── ou=people
    ├── uid=person001
    ├── uid=person002
    ├── ...
    └── uid=person500
```

Các entry phải hợp lệ theo `objectClass`/schema, dùng dữ liệu giả. Hai principal test:

- **Directory reader:** chỉ có quyền đọc các trường cần thiết.
- **Directory admin test:** dùng để khởi tạo dữ liệu và cấu hình giới hạn test, không dùng làm bind account cho API.

### 14.2. Kiểm thử size limit

1. Đảm bảo có **nhiều hơn 10 entry** khớp một filter đã biết.
2. Gọi search với `countLimit(10)` và template có `setIgnoreSizeLimitExceededException(false)`.
3. Ghi nhận directory/JNDI **có trả lỗi giới hạn hay không**; một số triển khai có thể dừng thành công tại ngưỡng do client yêu cầu.
4. Nếu lỗi được báo, xác minh application catch **Spring LDAP SizeLimitExceededException** và chuyển thành lỗi “kết quả chưa hoàn chỉnh”.
5. Cấu hình template **ignore=true** riêng trong môi trường test để thấy sự khác biệt; không coi kết quả trả về là đầy đủ.
6. Bỏ count limit phía client nhưng đặt server administrative cap trong **directory test**, xác minh response/result code và khả năng phát hiện kết quả thiếu.
7. Thử query trả chính xác 10 entry: nếu có 10 phần tử với limit=10, **không được suy ra** từ số lượng rằng directory không còn entry thứ 11.

### 14.3. Kiểm thử time limit

1. Chọn filter/search base đủ rộng để tái hiện một truy vấn chậm trong directory test.
2. Thiết lập `timeLimit(...)` đủ nhỏ nhưng hợp lý cho provider, chẳng hạn `1_000` ms; không kỳ vọng môi trường cực nhanh chắc chắn phát sinh exception.
3. Nếu server không thể tái hiện tự nhiên, dùng **policy/time cap test** hoặc cơ chế kiểm thử có kiểm soát của directory, không dùng dữ liệu production.
4. Xác nhận exception được chuyển thành **Spring LDAP TimeLimitExceededException** khi đường thực thi hỗ trợ; phân biệt với JNDI/communication timeout.
5. Tối ưu filter, index và search base, đo lại p50/p95 để kiểm chứng nguyên nhân thay vì chỉ tăng time limit.
6. Thử `java.naming.ldap.read.timeout` để thấy lỗi transport có thể khác `TimeLimitExceededException`.

### 14.4. Kiểm thử theo nghiệp vụ

| Bài test | Kỳ vọng |
| --- | --- |
| Search đúng 1 uid có index | Hoàn tất, trả entry chính xác |
| Search rộng vượt giới hạn | Không báo “hoàn tất” khi chưa có chứng cứ |
| Search timeout | Trả lỗi có phân loại, không trả 0 người |
| Không có kết quả thật | Trả danh sách rỗng **vì search hoàn tất** |
| Người dùng không có quyền đọc | Không suy thành “không tồn tại” khi lỗi ACL |
| Xác định nhóm phân quyền | Không cấp quyền dựa trên danh sách nhóm chưa đủ |
| Đồng bộ nhiều trang | Chỉ đánh dấu complete khi cookie cho biết hết trang |
| Thất bại ở trang thứ ba | Giữ checkpoint và trạng thái partial, không xóa dữ liệu đích |
| Mất kết nối sau search write | Không retry thao tác ghi mù quáng |
| Logging/tracing | Không chứa password, DN cá nhân hoặc raw filter nhạy cảm |

### 14.5. Thử trực tiếp bằng ldapsearch

Với directory test có quyền đọc, có thể dùng công cụ OpenLDAP `ldapsearch`:

```bash
ldapsearch -x \
  -H "ldaps://directory.example.org:636" \
  -D "uid=directory-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  -z 10 -l 1 \
  "(objectClass=inetOrgPerson)" dn uid
```

Ở công cụ `ldapsearch` thông dụng, `-z 10` đặt size limit 10 entry, còn `-l 1` đặt time limit 1 giây. **Đây không phải đơn vị millisecond của `LdapQueryBuilder.timeLimit(...)`.** `-W` yêu cầu nhập password tương tác thay vì viết password trong command line.

Giá trị limit không bảo đảm mọi server sẽ sinh result code 3/4 trong mọi test; kiểm tra stderr, result code và access log của server. Với môi trường thật, phải dùng kết nối TLS được xác minh đầy đủ.

## 15. Câu hỏi tự luyện

**Câu 1.** Một LDAP search trả 100 user khi `countLimit=100`. Có thể khẳng định directory chỉ có 100 user không?

*Đáp án gợi ý:* **Không.** Có thể còn nhiều entry khác. Cần tín hiệu đầy đủ đáng tin, filter thu hẹp hoặc paging được xử lý tới hết.

**Câu 2.** `SizeLimitExceededException` có LDAP result code nào và khác `TimeLimitExceededException` ra sao?

*Đáp án gợi ý:* Size là **4**, giới hạn số entry; time là **3**, giới hạn thời gian. Hai lỗi có thể xuất hiện sau khi một số entry đã được gửi.

**Câu 3.** Vì sao `catch (javax.naming.SizeLimitExceededException ex)` có thể không bắt lỗi từ `LdapTemplate.search(...)`?

*Đáp án gợi ý:* `LdapTemplate` thường dịch exception JNDI thành runtime exception **`org.springframework.ldap.SizeLimitExceededException`**; hơn nữa mặc định có thể **ignore size-limit exception**.

**Câu 4.** Theo Javadoc, `LdapTemplate.setIgnoreSizeLimitExceededException(...)` mặc định là gì? Có rủi ro nào?

*Đáp án gợi ý:* **`true`**. Search có thể trả danh sách đã nhận mà không báo lỗi size limit cho caller; nghiệp vụ cần đủ dữ liệu có thể hiểu nhầm danh sách là hoàn chỉnh.

**Câu 5.** `timeLimit(2_500)` nghĩa là 2.500 giây hay 2,5 giây?

*Đáp án gợi ý:* **2,5 giây**, do Spring/JNDI API dùng đơn vị millisecond; LDAP SearchRequest trên giao thức dùng đơn vị giây.

**Câu 6.** Có nên bắt `TimeLimitExceededException` rồi trả `List.of()` cho chức năng tính quyền không?

*Đáp án gợi ý:* **Không.** Danh sách rỗng sau search hoàn tất có ý nghĩa khác lỗi search chưa hoàn tất. Cần fail closed và giữ được lý do lỗi.

**Câu 7.** Một filter `(cn=*an*)` liên tục quá thời gian. Tăng time limit lên 60 giây đã tối ưu chưa?

*Đáp án gợi ý:* Chưa. Cần kiểm tra index substring, độ chọn lọc, base/scope và tải server; tăng time limit không loại bỏ nguyên nhân quét rộng.

**Câu 8.** `java.naming.ldap.read.timeout` có tương đương `SearchControls.setTimeLimit(...)` không?

*Đáp án gợi ý:* **Không.** Read timeout là giới hạn chờ I/O của provider, còn search time limit liên quan thời gian tìm kiếm; exception cụ thể có thể khác.

**Câu 9.** RFC 2696 paged results có tự mang lại snapshot nhất quán nếu dữ liệu LDAP đang thay đổi không?

*Đáp án gợi ý:* Không bảo đảm. Cần xem chính sách và khả năng directory. Paging chỉ tổ chức nhận kết quả theo trang và cookie, không mặc nhiên khóa toàn bộ dữ liệu.

**Câu 10.** Nếu đồng bộ LDAP xử lý được 3 trang rồi trang 4 bị `TimeLimitExceededException`, có nên phát sự kiện “sync_complete” không?

*Đáp án gợi ý:* Không. Cần đánh dấu **partial/failed**, lưu trạng thái đã xử lý và chỉ hoàn tất khi toàn bộ dữ liệu cần thiết đã được đọc và xác minh.

## 16. Ghi nhớ

- **`SizeLimitExceededException`** và **`TimeLimitExceededException`** cùng báo **search không hoàn thành do giới hạn**, nhưng một bên là **số entry**, một bên là **thời gian**.
- Theo RFC 4511, result code tương ứng là **4** (size) và **3** (time).
- Trong JNDI, đây là **checked exceptions** ở `javax.naming`; trong Spring LDAP, chúng là **runtime exceptions** ở `org.springframework.ldap`.
- `countLimit` đo **số entry**, `timeLimit` của Spring/JNDI đo **millisecond**, còn LDAP SearchRequest time limit biểu diễn bằng **giây**.
- **`LdapTemplate` mặc định bỏ qua `SizeLimitExceededException` theo Javadoc**; nếu cần phát hiện kết quả chưa hoàn tất, phải xem xét `setIgnoreSizeLimitExceededException(false)` và kiểm chứng với server.
- Không đánh đồng kết quả được giới hạn với tập kết quả đầy đủ; một danh sách có N phần tử khi limit=N **không chứng minh** không còn entry nào khác.
- **Không catch rồi trả rỗng** cho nghiệp vụ cần toàn vẹn dữ liệu hoặc quyền truy cập. Giữ lỗi được phân loại và fail closed nếu không thể xác minh kết quả.
- Khi cần đọc nhiều entry, dùng **filter/index/base phù hợp + phân trang RFC 2696 + xác nhận hết cookie**; paging không tự vượt mọi giới hạn của server và không bảo đảm snapshot.
- Search time limit, connect/read timeout, pool wait và HTTP deadline là **những giới hạn khác nhau**; hãy đo từng tầng trước khi điều chỉnh.

**Tài liệu tham khảo chính thức:**

- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): `SearchRequest`, mã `timeLimitExceeded (3)` và `sizeLimitExceeded (4)`.
- [Spring LDAP Javadoc — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `setIgnoreSizeLimitExceededException`, mặc định `true`, `setDefaultCountLimit` và `setDefaultTimeLimit`.
- [Spring LDAP Javadoc — SizeLimitExceededException](https://docs.spring.io/spring-ldap/docs/3.3.x/api/org/springframework/ldap/SizeLimitExceededException.html): runtime exception Spring LDAP.
- [Spring LDAP Javadoc — TimeLimitExceededException](https://docs.spring.io/spring-ldap/docs/3.3.x/api/org/springframework/ldap/TimeLimitExceededException.html): runtime exception Spring LDAP.
- [Spring LDAP Reference — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): `base`, `searchScope`, `countLimit` và `timeLimit`.
- [Spring LDAP Javadoc — LdapQueryBuilder](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html): fluent search builder và escaping filter.
- [Spring LDAP Reference — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): paging với `DirContextProcessor` và `SingleContextSource`.
- [RFC 2696 — Simple Paged Results Control](https://www.rfc-editor.org/rfc/rfc2696): page cookie, page size và response control.
- [Oracle JNDI Tutorial — Search Time Limits](https://docs.oracle.com/javase/tutorial/jndi/ops/timelimit.html): `SearchControls.setTimeLimit` tính bằng millisecond.
- [Java API — SearchControls](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/SearchControls.html): `setCountLimit`, `setTimeLimit` và scope.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và thao tác LDAP qua entity.
