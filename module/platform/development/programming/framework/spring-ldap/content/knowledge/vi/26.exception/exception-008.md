# PartialResultException, referral và kết quả không đầy đủ

Trong ứng dụng **SPRING_LDAP**, một phép tìm kiếm có thể đọc được một số entry rồi gặp **referral**: LDAP server cho biết cần tiếp tục tìm ở một server hoặc naming context khác. Nếu client không xử lý được phần tiếp theo, JNDI có thể ném `PartialResultException`. Đây là trường hợp nguy hiểm vì kết quả đang có **không nhất thiết bao phủ toàn bộ phạm vi người dùng yêu cầu**.

Ví dụ, một hệ thống tìm nhân viên để lập báo cáo có thể nhìn thấy người dùng trong một domain nhưng bỏ sót những domain khác. Nếu code bắt exception rồi trả danh sách vừa nhận như thể đã tìm đủ, báo cáo sai; nguy hiểm hơn, nếu hệ thống dùng kết quả này để quyết định quyền, người dùng hoặc nhóm có thể bị phân loại không chính xác.

Bài thuộc chương **Exception**, giải thích quan hệ giữa **`PartialResultException`, referral và tính đầy đủ của dữ liệu** khi làm việc với `ContextSource`, `LdapTemplate`, `LdapClient` hoặc Object–Directory Mapping (ODM). Người học sẽ thực hành lựa chọn chính sách referral, hiểu các tùy chọn bỏ qua exception, cân nhắc LDAP paging/giới hạn và kiểm thử truy cập thư mục an toàn qua TLS, tài khoản bind và nhiều server.

## 1. Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt `javax.naming.PartialResultException` và `org.springframework.ldap.PartialResultException`; biết chúng khác `ReferralException`.
2. Giải thích **LDAP referral result (10)** và **`SearchResultReference`** trong kết quả tìm kiếm, phân biệt với một tìm kiếm trả `0` entry.
3. Hiểu ba giá trị của JNDI `java.naming.referral`: `ignore`, `follow` và `throw`, cùng tác động lên kết quả và thông tin xác thực.
4. Cấu hình `LdapContextSource.setReferral(...)` và `LdapTemplate.setIgnorePartialResultException(...)` theo mục tiêu truy vấn.
5. Phân biệt **kết quả bị thiếu do referral** với **size limit**, **time limit**, **search base sai**, **lỗi mạng** và **khác biệt giữa các replica**.
6. Thiết kế API biểu diễn kết quả có thể không đầy đủ, tránh tự động sử dụng dữ liệu thiếu cho báo cáo, đồng bộ hoặc kiểm tra phân quyền.
7. Xây kịch bản kiểm thử nhiều naming context, kiểm tra tính đầy đủ và tránh kết nối theo referral đến đích không tin cậy.

## 2. Referral là gì?

Một thư mục LDAP có thể được chia thành nhiều **naming context** hoặc nhiều LDAP server. Server được hỏi đôi khi chỉ biết một phần cây thư mục hoặc biết nơi cần gửi tiếp yêu cầu.

Giả sử ứng dụng truy vấn toàn bộ nhân viên:

```text
                  dc=example,dc=org
                         │
              LDAP server / domain A
                 ├── ou=people    → trả một số entry
                 └── dc=branch   → không giữ toàn bộ dữ liệu
                         │
                         └── referral tới LDAP server / domain B
                                             │
                                             └── trả các entry còn lại
```

Server A có thể trả các entry mà nó biết, đồng thời cho client biết **cần tiếp tục ở địa chỉ khác**. Referral không tự nó có nghĩa “search thất bại” hay “user không tồn tại”; đó là một chỉ dẫn về vị trí dữ liệu.

### 2.1. Hai dạng referral trong LDAP

| Dạng | Xuất hiện khi nào? | Ý nghĩa |
| --- | --- | --- |
| **LDAP resultCode `referral (10)`** | Một thao tác nhận phản hồi kết thúc với mã referral | Server hướng client tới nơi có khả năng xử lý yêu cầu |
| **`SearchResultReference`** (*continuation reference*) | Có thể xen giữa các `SearchResultEntry` trong một phép Search | Client đã nhận một số entry và cần tiếp tục phần tìm kiếm ở nơi khác |

Theo RFC 4511, `SearchResultReference` là một loại thông điệp trong **kết quả tìm kiếm**, không phải một entry người dùng. Một phép tìm kiếm có thể có các entry bình thường, continuation reference, rồi `SearchResultDone`. Do đó **nhận được một số entry không chứng minh toàn bộ phạm vi đã được duyệt**.

Ví dụ luồng:

```text
Client ── Search(base=dc=example,dc=org) ──> Server A
Client <── SearchResultEntry(user An) ─────── Server A
Client <── SearchResultEntry(user Bình) ───── Server A
Client <── SearchResultReference(ldap://B/...) Server A
Client <── SearchResultDone(success) ──────── Server A

Nếu client không theo được reference sang B:
    {An, Bình} chỉ là phần dữ liệu lấy được từ A.
```

Ngay cả khi `SearchResultDone` của phần tìm kiếm tại A mang mã `success (0)`, yêu cầu tổng thể vẫn có thể chưa hoàn tất nếu continuation references cần thiết chưa được xử lý.

### 2.2. Referral không phải alias, replication hay paging

| Khái niệm | Đặc điểm |
| --- | --- |
| **Referral** | Chỉ dẫn client đến LDAP URL/naming context khác để tiếp tục thao tác |
| **Alias** | Entry tham chiếu một entry khác trong cơ chế dereference alias của LDAP; không tương đương referral |
| **Replica** | Bản sao dữ liệu tại server khác; có thể bị chậm đồng bộ và đưa ra kết quả khác nhau |
| **Paging** | Chia một tập kết quả của phép Search thành các trang; một trang không phải toàn bộ kết quả |
| **Search scope** | `OBJECT`, `ONELEVEL`, `SUBTREE` giới hạn các entry cần duyệt; chọn scope hẹp là giới hạn chủ động |

Một ứng dụng có thể vừa gặp referral, vừa phân trang, vừa dùng replica. Mỗi vấn đề cần được xử lý riêng khi đánh giá mức độ đầy đủ của dữ liệu.

## 3. `PartialResultException` trong JNDI và Spring LDAP

### 3.1. Hai lớp exception khác package

| Lớp | Hệ thư viện | Đặc điểm |
| --- | --- | --- |
| `javax.naming.PartialResultException` | Java JNDI | **Checked exception**, kế thừa `javax.naming.NamingException`; báo không thể hoàn tất toàn bộ kết quả |
| `org.springframework.ldap.PartialResultException` | Spring LDAP | **Runtime exception**, kế thừa `org.springframework.ldap.NamingException`; được chuyển từ JNDI |
| `javax.naming.ReferralException` | Java JNDI | Exception cho việc client xử lý referral theo chế độ `throw` |
| `org.springframework.ldap.ReferralException` / `LdapReferralException` | Spring LDAP | Các runtime exception tương ứng trong hệ Spring LDAP |

Spring LDAP chuyển các exception JNDI qua cơ chế `LdapUtils.convertLdapException(...)`. Vì vậy, code dùng `LdapTemplate` thường bắt:

```java
import org.springframework.ldap.PartialResultException;
```

Không bắt nhầm `javax.naming.PartialResultException` trong service gọi `LdapTemplate`. Nếu gọi `DirContext` trực tiếp, loại JNDI là loại cần xem xét.

### 3.2. Vì sao exception xuất hiện khi đọc kết quả?

Các API tìm kiếm thường xử lý kết quả **theo từng phần**. JNDI có thể gặp referral trong lúc duyệt `NamingEnumeration` và phát hiện không thể theo tới những kết quả còn lại.

```text
Server trả entry đầu tiên
          │
          ▼
JNDI duyệt các kết quả tiếp theo
          │
          ├── Có thể tiếp tục → thêm entry
          └── Không thể xử lý referral
                        │
                        ▼
           javax.naming.PartialResultException
                        │
                        ▼
           org.springframework.ldap.PartialResultException
```

`PartialResultException` cho biết **có khả năng còn kết quả chưa được truy xuất**, chứ không chứng minh các entry đã đọc trước đó đều sai. Tuy nhiên, caller **không thể tự xem kết quả đang có là đầy đủ** nếu không có chính sách xác minh phạm vi.

### 3.3. Lưu ý về mã LDAP `9` và `10`

Tài liệu hướng dẫn **JNDI/LDAP provider** cũ có bảng ánh xạ mã `partialResults (9)` sang `PartialResultException`. Tuy nhiên, **RFC 4511 (LDAPv3) dành mã `9` ở trạng thái reserved**, còn `referral (10)` và `SearchResultReference` là các cơ chế referral cần quan tâm trong LDAPv3. Vì vậy, **không được định nghĩa `PartialResultException` chỉ bằng một mã LDAP `9`**.

Khi phân tích lỗi thực tế, hãy căn cứ vào **loại exception, referral mode, thao tác Search, phản hồi từ server và root cause**; không parse cố định chuỗi `"error code 9"` hay `"error code 10"` trong `getMessage()`.

## 4. Ba chính sách referral của JNDI

JNDI dùng thuộc tính môi trường `Context.REFERRAL` (tên đầy đủ: `java.naming.referral`). Các giá trị phổ biến là:

| Giá trị | Hành vi dự kiến | Giới hạn/rủi ro |
| --- | --- | --- |
| `ignore` | Không tự động theo referral. Với LDAPv3, JNDI provider thường gửi ManageDsaIT control để yêu cầu xử lý referral entry theo cách đặc biệt | Nếu server vẫn trả referral hoặc continuation reference, có thể phát sinh `PartialResultException` |
| `follow` | JNDI provider cố tự động theo các referral được server trả | Phải xác minh địa chỉ được chuyển đến, DNS/TLS, credential, ACL, latency và referral loop |
| `throw` | JNDI chuyển referral thành `ReferralException` để caller xử lý có chủ đích | Cần code điều khiển ở tầng JNDI; `LdapTemplate` thông thường không cung cấp một workflow đầy đủ để tự xử lý từng referral |

Mặc định của JNDI LDAP provider là **`ignore`** nếu chưa chỉ định, nhưng cần xác nhận hành vi thực tế của `ContextSource`, provider và server đang sử dụng. `ignore` không bảo đảm “không có exception”; nó cũng không bảo đảm trả tất cả entry.

### 4.1. `ignore` và ManageDsaIT

Theo tài liệu JNDI, khi `Context.REFERRAL="ignore"` với LDAPv3, provider thường gửi **ManageDsaIT control** để LDAP server trả referral entry như entry thông thường, thay vì tự động gửi referral để client tiếp tục. Nếu server **không hỗ trợ hoặc không tuân theo** yêu cầu này và vẫn trả referral, JNDI có thể ném `PartialResultException`.

Vì vậy không nên diễn giải “ignore” là “chắc chắn lấy được dữ liệu cục bộ và không có lỗi”. Cần kiểm tra hành vi của LDAP server thực tế.

### 4.2. `follow` không phải lựa chọn luôn đúng

Tự theo referral nghe có vẻ tiện, nhưng cần đánh giá:

- **Đích đến:** referral có thể trỏ tới hostname/port ngoài phạm vi LDAP server mà ứng dụng dự kiến truy cập.
- **Bảo mật kênh:** mỗi đích cần được đánh giá TLS/LDAPS/StartTLS và chứng chỉ. Không tự động hạ từ TLS xuống kết nối không bảo vệ chỉ để lấy đủ kết quả.
- **Thông tin xác thực:** provider và cơ chế bind theo referral cần được kiểm soát; không để tài khoản đặc quyền hoặc mật khẩu đi tới endpoint không tin cậy.
- **Phân quyền:** tài khoản có thể thấy entry ở server A nhưng không có quyền search server B.
- **Thời gian và số bước:** referral chain có thể dài, bị vòng lặp hoặc trỏ endpoint không khả dụng.
- **Ngữ nghĩa dữ liệu:** cùng entry có thể xuất hiện qua nhiều nguồn, có thay đổi hoặc độ trễ đồng bộ; cần quy tắc chống trùng phù hợp.

Chỉ bật `follow` khi đã có **chính sách tin cậy cho referral targets**, giới hạn thời gian/hops và kết nối an toàn. Trong hệ thống nhiều domain có quy định chặt chẽ, truy vấn từng directory endpoint được cấu hình rõ ràng có thể dễ kiểm soát hơn theo referral tùy ý.

### 4.3. `throw` và tự xử lý referral

Ở tầng **JNDI trực tiếp**, `Context.REFERRAL="throw"` có thể làm `ReferralException` xuất hiện, để code quyết định có truy cập đích được giới thiệu hay không. Việc dùng `ReferralException.getReferralContext(...)` đòi hỏi hiểu rõ vòng đời context, URL, credential, giới hạn chuyển hướng và điều kiện dừng; không thể chỉ `catch` rồi gọi lại `search` vô hạn.

Với **`LdapTemplate`**, không nên nghĩ `setReferral("throw")` sẽ khiến mọi thông tin referral trở thành một danh sách URL dễ lấy qua API cấp cao. Javadoc `LdapTemplate` lưu ý các hạn chế khi xử lý thủ công referral; nếu cần điều phối referral phức tạp, cân nhắc xử lý JNDI ở tầng được kiểm soát hoặc truy vấn explicit tới các directory endpoint tin cậy.

## 5. Cấu hình `ContextSource` và `LdapTemplate`

### 5.1. Ví dụ cấu hình strict mode

Giả sử `ContextSource` có base DN `dc=example,dc=org`. Đây là ví dụ tạo bean bằng Java; `ldapUrl`, principal và secret đến từ cấu hình bảo mật của ứng dụng:

```java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

public final class LdapSearchConfiguration {
    private LdapSearchConfiguration() {}

    public static LdapTemplate strictTemplate(
            String ldapUrl,
            String baseDn,
            String serviceDn,
            String servicePassword) throws Exception {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(ldapUrl);
        source.setBase(baseDn);
        source.setUserDn(serviceDn);
        source.setPassword(servicePassword);

        // Truy vấn trong phạm vi LDAP cục bộ, không tự theo referral.
        source.setReferral("ignore");

        // Khi khởi tạo thủ công, gọi lifecycle hook.
        // Trong Spring IoC, container gọi sau khi cấu hình bean.
        source.afterPropertiesSet();

        LdapTemplate template = new LdapTemplate(source);
        template.setIgnorePartialResultException(false);
        template.setIgnoreNameNotFoundException(false);
        template.setIgnoreSizeLimitExceededException(false);
        return template;
    }
}
```

Trong chế độ này, nếu provider báo `PartialResultException`, caller thấy lỗi thay vì âm thầm nhận kết quả được coi là đầy đủ. `setIgnorePartialResultException(false)` chính là giá trị **mặc định** theo Javadoc `LdapTemplate`; viết tường minh giúp người đọc thấy chính sách.

Lưu ý: cấu hình `setReferral("ignore")` **không** khiến search tự động bao phủ domain hoặc partition khác. `setIgnoreSizeLimitExceededException(false)` được đặt thêm để không âm thầm chấp nhận size limit; theo Javadoc Spring LDAP, **mặc định của tùy chọn này là `true`**, trong khi `ignorePartialResultException` mặc định là `false`.

Nếu mục tiêu phải bao gồm các naming context khác, cần xem lại `referral`, endpoint, lựa chọn query scope hoặc thiết kế tổng hợp; **strict mode chỉ phát hiện được một số tín hiệu không hoàn chỉnh, không chứng nhận tính đầy đủ toàn cục**.

### 5.2. Có thể bật chế độ `follow` thế nào?

Thay chính sách referral của `ContextSource` bằng:

```java
source.setReferral("follow");
```

Đây là cấu hình để JNDI provider **cố theo referral**. Nó không sửa quyền, schema, DNS hoặc TLS của server đích. Nếu chưa tin tưởng toàn bộ referral targets, không tự động chuyển production sang `follow` chỉ để exception biến mất.

### 5.3. `setIgnorePartialResultException(true)` thực sự làm gì?

`LdapTemplate` cung cấp:

```java
template.setIgnorePartialResultException(true);
```

Tùy chọn này là một **workaround có chủ đích**, được tài liệu Spring LDAP nhắc đến với những server như Active Directory khi referral không được theo đầy đủ. Nó cho phép phương thức `search` **trả về bình thường** trong các trường hợp `PartialResultException` được bỏ qua.

Tuy nhiên:

1. **Không đồng nghĩa với đã theo referral thành công**; có thể thiếu entry thuộc các naming context khác.
2. `List<T>` trả về từ `search` không có trường `complete=true/false` để caller tự biết một referral đã bị bỏ qua.
3. Không làm biến mất `NameNotFoundException`, `CommunicationException`, `SizeLimitExceededException` hoặc các lỗi khác; mỗi loại có cơ chế xử lý riêng.
4. Nếu bật chung cho mọi search, một báo cáo tưởng đã lấy đủ nhân viên có thể chỉ chứa nhân viên từ domain cục bộ.
5. Cần ghi rõ **phạm vi dữ liệu được chấp nhận** và dùng thông số/metric riêng cho những endpoint chấp nhận khả năng thiếu dữ liệu.

Chỉ bật tùy chọn này cho những **truy vấn mà kết quả cục bộ hoặc có thể không đầy đủ vẫn hữu ích**, đồng thời trình bày trạng thái đó rõ ràng cho caller. Truy vấn kiểm kê, cấp quyền, đồng bộ danh tính và đối soát thường phải có chính sách chặt chẽ hơn.

## 6. Ví dụ service: không nuốt `PartialResultException`

Ví dụ tìm `cn` theo `uid` ở `ou=people`, sử dụng query builder để escape giá trị filter. Service này có hợp đồng: **trả về kết quả hợp lệ trong phạm vi đã xác định hoặc báo rằng không thể xác nhận tính đầy đủ**.

```java
import java.util.List;
import javax.naming.directory.Attribute;

import org.springframework.ldap.PartialResultException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class DirectoryPeopleSearch {
    private final LdapTemplate ldapTemplate;

    public DirectoryPeopleSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNames(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        try {
            return ldapTemplate.search(
                    query().base("ou=people").where("uid").is(uid),
                    (AttributesMapper<String>) attrs -> {
                        Attribute cn = attrs.get("cn");
                        if (cn == null || cn.size() == 0) {
                            throw new IllegalStateException(
                                    "Entry tồn tại nhưng không có cn");
                        }
                        return cn.get().toString();
                    });
        } catch (PartialResultException ex) {
            throw new DirectoryCoverageException(
                    "Không thể xác nhận kết quả LDAP đầy đủ", ex);
        }
    }

    public static final class DirectoryCoverageException
            extends RuntimeException {
        public DirectoryCoverageException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

Giải thích:

- `query().where("uid").is(uid)` dùng **filter builder**, tránh ghép chuỗi gây sai escape và nguy cơ LDAP injection.
- `search` không khớp entry nào trong base hợp lệ thường trả **danh sách rỗng**. Đây là tình huống khác với exception referral.
- `PartialResultException` được chuyển thành exception miền có thông điệp rõ, giữ `cause` để chẩn đoán.
- Không dùng `catch (org.springframework.ldap.NamingException)` rồi trả `List.of()`; hành vi đó sẽ che cả lỗi mạng, schema, phân quyền hoặc DN.
- Nếu cấu hình `LdapTemplate` đã **bỏ qua** `PartialResultException` bằng `setIgnorePartialResultException(true)`, khối `catch` này **sẽ không biết** có referral nào vừa bị bỏ qua. Chính sách completeness phải đặt từ cấu hình đến API, không thể chỉ xử lý bằng try/catch.

### 6.1. Ví dụ hợp đồng khi chấp nhận dữ liệu cục bộ

Một trang quản trị có thể chỉ cần một danh sách mang tính tham khảo trong **domain cục bộ**, không dùng để xác định tổng số người dùng. Khi chọn policy bỏ qua partial result, nên diễn đạt phạm vi cho caller:

```java
import java.util.List;

public record DirectorySearchPage(
        List<String> names,
        String coverage) {
    // coverage = "LOCAL_SCOPE_POSSIBLY_INCOMPLETE"
}
```

Ví dụ giá trị `coverage` là **khả năng thiếu dữ liệu theo chính sách**, không phải bằng chứng exception thực tế đã xảy ra. `LdapTemplate` thông thường không cung cấp cho service một cờ cho biết `PartialResultException` đã bị bỏ qua. Nếu cần trạng thái `complete` được bảo đảm, phải thiết kế cơ chế truy vấn/kiểm soát phạm vi và xác minh riêng.

Trong API, có thể trả:

```json
{
  "names": ["An Nguyen", "Binh Tran"],
  "coverage": "LOCAL_SCOPE_POSSIBLY_INCOMPLETE",
  "searchedBase": "ou=people",
  "requestId": "req-6d3a"
}
```

Đây là dữ liệu minh họa. Không công khai DN, membership hoặc thông tin định danh nhạy cảm nếu caller không có quyền đọc; `searchedBase` chỉ nên là tên phạm vi logic được phép tiết lộ.

## 7. Referral với Active Directory và nhiều domain

Active Directory (AD) thường có nhiều domain và naming context. Một truy vấn đi qua domain controller có thể chỉ trả dữ liệu của domain hiện tại hoặc gặp continuation reference khi tìm sang partition/domain khác.

Ví dụ:

```text
Forest example.org
    ├── Domain A: dc=corp,dc=example,dc=org
    └── Domain B: dc=branch,dc=example,dc=org

Ứng dụng kết nối DC của Domain A
    ├── đọc các entry của Domain A
    └── muốn đọc Domain B → có thể cần referral
```

Spring LDAP có ghi chú trong Javadoc `LdapTemplate` rằng một số trường hợp xử lý referral với AD có thể tạo `PartialResultException`; bật `ignorePartialResultException=true` là một workaround thường được sử dụng. **Workaround này không biến query thành tìm kiếm xuyên toàn bộ forest**.

### 7.1. Các chiến lược thường dùng

| Nhu cầu | Phương án cân nhắc | Điều phải kiểm tra |
| --- | --- | --- |
| Chỉ tìm trong một domain xác định | Kết nối đúng DC/base DN của domain đó | ACL, scope, search base và kết quả domain cục bộ |
| Cần tiếp tục theo referral đã biết, tin cậy | Cấu hình `follow` có kiểm soát | TLS, credential, DNS, thời gian, recursion/hop limit, quyền ở đích |
| Cần tổng hợp từ một số domain đã định nghĩa | Truy vấn từng directory endpoint trong allowlist rồi tổng hợp | Duplicate, failure từng nguồn, tính nhất quán và coverage |
| Cần search trong forest AD | Cân nhắc Global Catalog khi phù hợp | Phạm vi, attribute set có trong GC, quyền, kênh bảo mật và kết quả thực tế |
| Chỉ hiển thị dữ liệu tham khảo từ domain cục bộ | Có thể chấp nhận bỏ qua partial result với cảnh báo coverage | Không dùng dữ liệu thiếu cho xác thực/phân quyền/đối soát |

**Global Catalog** là một giải pháp tra cứu forest của AD trong một số trường hợp nhưng không mặc định chứa **tất cả thuộc tính** giống mỗi domain controller. Sự khác nhau về attribute set và cách xác thực cần được kiểm thử. Nếu nghiệp vụ cần các attribute không có trong GC, phải thiết kế truy vấn bổ sung.

### 7.2. Đừng nhầm “không có user” với “chưa tìm hết domain”

Một search trả danh sách rỗng có thể nghĩa là:

- Không có user khớp trong **domain đã tìm thành công**.
- Search base, scope hoặc filter không phù hợp.
- Account bind không được phép thấy entry/attribute đó.
- Referral sang domain khác chưa được theo.
- Dữ liệu chưa đồng bộ trên replica được hỏi.

Vì vậy, với những yêu cầu cần kết quả **toàn forest** hoặc nhiều domain, không thể kết luận user không tồn tại chỉ từ một query cục bộ trả rỗng.

## 8. Không đầy đủ còn đến từ size limit, time limit và paging

`PartialResultException` không phải loại exception duy nhất liên quan **kết quả thiếu**.

| Dấu hiệu | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| `PartialResultException` | Có thể chưa xử lý hết referral/continuation reference | Chọn chính sách referral, phạm vi coverage hoặc báo chưa đủ |
| `SizeLimitExceededException`, LDAP `4` | Số entry vượt giới hạn được áp dụng | Paging, thu hẹp scope/filter, kiểm tra giới hạn server |
| `TimeLimitExceededException`, LDAP `3` | Tìm kiếm quá giới hạn thời gian | Tối ưu filter/index, giới hạn scope và thời gian |
| `LimitExceededException`, LDAP `11` hoặc referral hop limit | Vượt hạn mức của server/client | Kiểm tra giới hạn, kiến trúc truy vấn và referral chain |
| `CommunicationException` | Kết nối/response không hoàn tất | Chẩn đoán mạng/TLS; không coi dữ liệu đã nhận là đầy đủ |
| `NameNotFoundException`, LDAP `32` | Search base không tồn tại | Sửa base/OU; không trả list rỗng một cách máy móc |
| Trang đầu của paged results | Chỉ có **một trang** của phép tìm kiếm | Duyệt theo cookie đến khi kết thúc đúng quy tắc |

### 8.1. `setIgnoreSizeLimitExceededException` cũng ảnh hưởng tính đầy đủ

Theo Javadoc `LdapTemplate`, `setIgnoreSizeLimitExceededException(boolean)` mặc định là **`true`** trong nhiều phiên bản hiện hành. Điều này có thể phù hợp khi ứng dụng **cố ý** đặt count limit để lấy một số kết quả đầu, nhưng cũng dễ khiến người đọc tưởng đó là toàn bộ danh sách.

Nếu mục tiêu là **lấy đủ tất cả entry** trong phạm vi đã cam kết, phải cân nhắc đặt:

```java
template.setIgnoreSizeLimitExceededException(false);
```

Chỉ đổi cờ không giúp server trả vô hạn dữ liệu; cần giới hạn/kiểm tra yêu cầu và dùng paging nếu server hỗ trợ. Tương tự, bỏ qua time limit hoặc retry query quá rộng không tự giải quyết nguyên nhân thiếu kết quả.

### 8.2. Paged results không tự động giải quyết referral

Với LDAP Simple Paged Results Control (RFC 2696), client yêu cầu từng trang theo cookie do server trả. Một luồng tìm đầy đủ thường là:

```text
Search page 1 ──> entries + cookie₁
Search page 2 (cookie₁) ──> entries + cookie₂
...
Search page N (cookieₙ₋₁) ──> entries + cookie rỗng
```

Ứng dụng phải tiếp tục lấy trang cho đến khi quy trình phân trang được kết thúc đúng cách. Tuy nhiên, **paging và referral là hai cơ chế khác nhau**: lấy hết trang của server A vẫn không bảo đảm đã theo mọi reference sang server B. Việc paging qua nhiều server/partition cần thiết kế trạng thái và giới hạn riêng.

Khi tính tổng số, hãy chú ý:

- Hạn mức kích thước/truy vấn của server và cơ chế cookie.
- Kết quả thay đổi trong lúc đang lấy nhiều trang (không chắc là một snapshot).
- Trùng entry khi lấy từ nhiều nguồn; cần định danh ổn định hoặc DN chuẩn hóa theo quy tắc hệ thống.
- Một nguồn lỗi thì kết quả tổng hợp nên thể hiện nguồn đó **chưa hoàn tất**, thay vì chỉ cộng các kết quả nhận được.

## 9. Bảo mật khi xử lý referral

Referral có thể khiến client kết nối đến một **địa chỉ khác** với endpoint ban đầu, vì vậy phải xem referral như một chỉ dẫn **cần được kiểm soát**, không mặc nhiên là nơi đáng tin.

Những kiểm soát quan trọng:

1. **Danh sách đích tin cậy:** chỉ cho phép LDAP host/domain/partition được quản trị chấp thuận; cân nhắc chặn đích ngoài mạng nội bộ hoặc địa chỉ không mong đợi.
2. **TLS và hostname verification:** kiểm tra chứng chỉ cho từng endpoint; tránh hạ cấp từ LDAPS/StartTLS xuống LDAP không được bảo vệ.
3. **Thông tin xác thực:** chỉ dùng danh tính có quyền tối thiểu cần thiết; không chia sẻ password của tài khoản đặc quyền sang referral target chưa được xác thực.
4. **Giới hạn hops, timeout và số lượng request:** ngăn vòng lặp referral, truy vấn kéo dài hoặc tải vượt ngưỡng.
5. **ACL độc lập:** quyền đọc domain A không cho phép suy rằng account có cùng quyền ở domain B.
6. **Audit và dữ liệu nhạy cảm:** log các đích ở dạng đã được kiểm soát; không đưa credential, query chứa dữ liệu nhạy cảm hay toàn bộ referral URL từ directory chưa tin cậy ra API công khai.

Trong hệ thống authentication/authorization, **kết quả thiếu có thể gây hậu quả bảo mật**. Ví dụ “không tìm thấy membership” có thể là do phần directory chứa nhóm chưa được truy vấn. Hãy quyết định rõ mô hình an toàn cho việc không thể xác minh quyền, thường là **không cấp quyền mới dựa trên kết quả chưa xác minh**, và đồng thời báo lỗi hệ thống thay vì cố diễn giải như kết quả nghiệp vụ hoàn chỉnh.

### 9.1. Referral và credential của `ContextSource`

Một `ContextSource` thường dùng tài khoản dịch vụ để search. Khi `follow` được bật, cách provider tạo context/đăng nhập ở server đích cần được hiểu và kiểm thử kỹ. Không nên suy rằng referral luôn sử dụng an toàn cùng principal hoặc rằng provider sẽ luôn bảo vệ credential phù hợp ở mọi scheme/host.

Trong trường hợp có nhiều vùng tin cậy, giải pháp dễ kiểm soát có thể là **các `ContextSource` riêng biệt** cho từng endpoint, mỗi nguồn có credential/ACL và TLS riêng, thay vì theo referral tùy ý.

## 10. Xử lý lỗi theo yêu cầu nghiệp vụ

| Yêu cầu nghiệp vụ | Có chấp nhận bỏ qua `PartialResultException` không? | Hành vi hợp lý |
| --- | --- | --- |
| Trang quản trị chỉ xem nhanh người dùng trong OU cục bộ | Có thể, nếu scope/coverage được ghi rõ | Hiển thị nhãn dữ liệu cục bộ, không khẳng định tổng số |
| Báo cáo toàn domain/forest | Thường không | Báo lỗi nguồn chưa đủ hoặc tổng hợp đủ các nguồn |
| Quyết định cấp quyền dựa trên membership | Không nên | Không coi kết quả thiếu như chứng minh membership không tồn tại |
| Đồng bộ tài khoản và xóa tài khoản không thấy trong nguồn | Không | Tránh xóa hàng loạt do nguồn tạm thời không trả đủ |
| Tìm kiếm theo một DN cụ thể trong một naming context đã xác định | Tùy phạm vi | Phân biệt `NameNotFoundException` với referral/availability |
| Thống kê tổng số group/user | Không nếu cần con số chính xác | Kiểm soát mọi partition, paging, limits và đồng bộ |

### 10.1. Xử lý HTTP

Nếu kết quả không thể được bảo đảm theo hợp đồng, service có thể ném exception miền (như ví dụ `DirectoryCoverageException`), rồi tầng HTTP trả lỗi phụ thuộc hạ tầng phù hợp (`502`/`503`/`504` tùy kiến trúc), kèm correlation ID.

Đừng trả `404 Not Found` hoặc `200 OK + []` chỉ vì một phần tìm kiếm chưa thấy user. Nếu API chấp nhận dữ liệu cục bộ, nên công khai trạng thái **partial possible** trong metadata thay vì ghi giả `complete=true`. Đồng thời không trả nguyên thông báo referral, internal LDAP URL, DN hoặc stack trace cho caller.

### 10.2. Retry có sửa được `PartialResultException` không?

Không nên retry nguyên query vô hạn khi nguyên nhân là **referral policy** hoặc endpoint không thể truy cập vì DNS/TLS/ACL; retry nhiều lần thường chỉ lặp lỗi. Nếu nguyên nhân thực sự là server đích mất kết nối thoáng qua, có thể áp dụng retry có điều kiện, với deadline, backoff và giới hạn số lần; vẫn phải đảm bảo query không trả một tập kết quả giả là đầy đủ.

Đối với các thao tác ghi (Add/Modify/Delete), referral còn mang rủi ro về **đích ghi** và **trạng thái sau timeout**. Mất kết nối sau khi gửi một yêu cầu ghi không chứng minh server chưa thực hiện; phải đối soát trạng thái trước khi retry và kiểm soát quyền ở directory đích.

## 11. Quy trình chẩn đoán thực tế

Khi gặp `PartialResultException` trong Spring LDAP:

1. **Xác định query:** base DN, scope, filter, attribute cần lấy, host/port, cách dùng `ContextSource` và thời điểm exception.
2. **Xem package và root cause:** JNDI `javax.naming.PartialResultException` hay Spring `org.springframework.ldap.PartialResultException`? Có referral, lỗi DNS/TLS hay timeout đi kèm không?
3. **Xem referral mode:** `ignore`, `follow` hoặc `throw` có thực sự được áp dụng lên context trong lúc chạy không?
4. **Xác định phạm vi kỳ vọng:** chỉ một OU/domain, nhiều naming context hay toàn forest? Những partition nào đã và chưa được duyệt?
5. **Kiểm tra đích referral:** chỉ truy cập endpoint tin cậy, với TLS, DNS, credential và ACL phù hợp.
6. **Kiểm tra các giới hạn khác:** size/time limit, paged results chưa lấy hết, referral hop limit, search base và kết nối pool.
7. **Kiểm tra chính sách Spring LDAP:** `ignorePartialResultException` và `ignoreSizeLimitExceededException` có bị bật để che lỗi không?
8. **Đánh giá dữ liệu hiện có:** có đủ cho nghiệp vụ hiện tại không; có thể đánh dấu partial hay phải từ chối đưa ra kết luận?
9. **Đo và quan sát:** thống kê số query gặp referral/partial, lỗi theo endpoint, độ trễ và số nguồn chưa hoàn tất; không log dữ liệu nhạy cảm.

Ví dụ log có cấu trúc:

```json
{
  "event": "ldap_search_incomplete",
  "operation": "search",
  "directoryAlias": "corp-ldap",
  "expectedCoverage": "all-configured-domains",
  "referralMode": "ignore",
  "exceptionType": "org.springframework.ldap.PartialResultException",
  "completedSources": 1,
  "expectedSources": 2,
  "correlationId": "req-42fa"
}
```

Các số trên chỉ là ví dụ khi ứng dụng **có cơ chế theo dõi nguồn độc lập**; `LdapTemplate` mặc định không cung cấp `completedSources` hay `expectedSources`. Không tự điền số nguồn hoặc đặt `complete=true` nếu không có bằng chứng. Tránh ghi referral URL, credential, DN hoặc filter chứa thông tin cá nhân trong log phổ biến.

## 12. Kiểm thử `PartialResultException` và completeness

Unit test giúp kiểm tra service **không nuốt lỗi partial**. Integration test với directory test có nhiều naming context hoặc hệ thống AD test cô lập giúp xác minh referral thực tế.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Search trong OU hợp lệ, không có entry khớp, không gặp referral | Danh sách rỗng là kết quả hợp lệ trong scope đã xác định |
| Server có entry cục bộ và continuation reference | Client strict phải phát hiện không thể xác nhận đủ nếu reference không được theo |
| `LdapTemplate` ném `PartialResultException` | Service đưa ra lỗi coverage riêng, không trả `List.of()` |
| `ignorePartialResultException=true` | API chỉ thể hiện phạm vi/khả năng thiếu, không khẳng định đủ |
| `ContextSource` referral `follow` tới server đã được tin cậy | Kết nối theo chính sách, có kiểm soát TLS/ACL, kết quả được xác minh |
| Referral tới hostname không được phép | Không tự gửi credential hoặc search đến đích đó |
| Referral loop hoặc đích mất kết nối | Có giới hạn hop/time và báo lỗi rõ |
| `SizeLimitExceededException` | Không coi tập entry nhận được là toàn bộ |
| Search nhiều trang dừng trước cookie kết thúc | Kết quả được đánh dấu/chặn là chưa đủ |
| Domain B không phản hồi trong tổng hợp A+B | Không báo tổng số A là tổng số A+B |
| Replica chậm đồng bộ | Không kết luận entry chắc chắn không tồn tại trên toàn hệ thống |
| Query tìm membership quyết định quyền | Trạng thái chưa hoàn tất không dẫn tới cấp quyền ngoài dự kiến |

### 12.1. Unit test minh họa

Ví dụ JUnit 5 và Mockito kiểm tra service chuyển Spring LDAP `PartialResultException` thành lỗi coverage. Constructor của exception Spring LDAP nhận nguyên nhân JNDI:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.PartialResultException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

class DirectoryPeopleSearchTest {
    @Test
    @SuppressWarnings("unchecked")
    void partialResultIsReportedAsIncomplete() {
        LdapTemplate ldapTemplate = mock(LdapTemplate.class);

        when(ldapTemplate.search(
                any(LdapQuery.class),
                any(AttributesMapper.class)))
                .thenThrow(new PartialResultException(
                        new javax.naming.PartialResultException(
                                "Referral cannot be completed")));

        DirectoryPeopleSearch service =
                new DirectoryPeopleSearch(ldapTemplate);

        assertThrows(
                DirectoryPeopleSearch.DirectoryCoverageException.class,
                () -> service.findCommonNames("an"));
    }
}
```

Ví dụ này kiểm tra **chính sách service**, không thay thế integration test. Khi `ignorePartialResultException=true`, ngoại lệ có thể đã bị `LdapTemplate` bỏ qua trước khi service thấy nó; unit test không đủ chứng minh kết quả đầy đủ hay referral đã được xử lý chính xác.

Đối với kiểm thử integration:

1. Tạo hai LDAP naming context hoặc dùng directory test có referral được cấu hình an toàn.
2. Tạo entry phân biệt ở từng nguồn, ví dụ user A chỉ có ở source A và user B chỉ có ở source B.
3. Chạy các chế độ `ignore`/`follow`/`throw` và xác minh hành vi provider, số nguồn được duyệt và coverage thực tế.
4. Mô phỏng một referral target tạm mất kết nối; kiểm tra timeout, log và việc không trả tổng số sai.
5. Xác minh TLS và account có quyền tối thiểu; không đưa password thật vào source, exception message hoặc log test.

## 13. Những sai lầm thường gặp

1. **Bắt `PartialResultException` rồi trả `[]`.** Có thể biến query thiếu dữ liệu thành “không tìm thấy người dùng”.
2. **Bật `ignorePartialResultException(true)` và coi mọi kết quả đầy đủ.** Cờ này bỏ qua exception, không theo referral giúp bạn.
3. **Coi `PartialResultException` luôn là mã LDAP `9`.** LDAPv3 RFC 4511 để mã `9` ở trạng thái reserved; referral có cơ chế riêng.
4. **Nhầm continuation reference với entry thường.** `SearchResultReference` chỉ dẫn phần cần tìm tiếp, không phải dữ liệu người dùng.
5. **Cho rằng `follow` luôn an toàn.** Referral có thể dẫn đến host, kênh TLS, quyền và credential khác.
6. **Không phân biệt size limit với partial referral.** Mỗi cơ chế có cách kiểm soát và exception riêng.
7. **Lấy một trang rồi kết luận đủ toàn bộ.** Paging yêu cầu hoàn thành quy trình cookie và vẫn có thể cần xử lý referral.
8. **Tưởng GC của AD chứa mọi attribute ở mọi domain.** Phải xác minh attribute set, scope và quyền.
9. **Dùng một query cục bộ để quyết định không có membership toàn forest.** Có thể bỏ sót nguồn quan trọng.
10. **Dùng `catch (Exception)` để giữ hệ thống “luôn trả thành công”.** Mất thông tin về TLS, mạng, ACL, base DN và tính đầy đủ.
11. **Cố parse chuỗi thông báo referral từ server.** Diagnostic message không phải API ổn định; dùng loại exception và cơ chế protocol.
12. **Đưa internal LDAP URL/credential vào log hoặc phản hồi HTTP.** Có thể lộ cấu trúc mạng và dữ liệu định danh.

## 14. Câu hỏi tự đánh giá

**Câu 1.** `PartialResultException` có phải lúc nào cũng nghĩa là LDAP server không trả entry nào không?

**Đáp án:** Không. Một phần entry có thể đã được nhận, nhưng client chưa thể hoàn tất phạm vi tìm kiếm.

**Câu 2.** Chế độ `java.naming.referral="ignore"` có bảo đảm không ném `PartialResultException` không?

**Đáp án:** Không. Nếu server vẫn trả referral hoặc continuation reference mà provider không xử lý được, exception vẫn có thể xảy ra.

**Câu 3.** `LdapTemplate.setIgnorePartialResultException(true)` có tự tìm entry ở domain được giới thiệu không?

**Đáp án:** Không. Nó cho phép bỏ qua exception trong search; kết quả vẫn có thể thiếu dữ liệu ở domain khác.

**Câu 4.** `SearchResultReference` và LDAP `referral (10)` có phải cùng một thông điệp không?

**Đáp án:** Không. Mã `10` thuộc dạng kết quả referral của thao tác; `SearchResultReference` là thông điệp continuation reference có thể xuất hiện trong các phản hồi của Search.

**Câu 5.** Nếu search trả `20` người dùng của domain A và có referral sang domain B chưa theo, có thể công bố tổng số toàn hệ thống là `20` không?

**Đáp án:** Không, trừ khi đã có bằng chứng domain B không thuộc phạm vi hoặc không có dữ liệu phù hợp. Tổng số toàn hệ thống chưa được xác minh.

**Câu 6.** Vì sao `follow` referral cần kiểm soát an toàn?

**Đáp án:** Nó có thể làm client truy cập đích khác; cần kiểm soát host, TLS, credential, ACL, timeout/hops và quyền xử lý dữ liệu.

**Câu 7.** Lấy hết trang với LDAP paging có bảo đảm không còn referral không?

**Đáp án:** Không. Paging và referral độc lập; có thể hoàn thành các trang cục bộ mà chưa duyệt các naming context khác.

**Câu 8.** Nếu một bước kiểm tra membership gặp `PartialResultException`, có nên coi user chắc chắn không có quyền không?

**Đáp án:** Không nên kết luận membership không tồn tại. Cần báo trạng thái không thể xác minh đầy đủ và áp dụng chính sách truy cập an toàn của hệ thống.

## 15. Tài liệu tham khảo

- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): `referral (10)`, `SearchResultReference`, kết quả tìm kiếm và các mã lỗi.
- [Oracle JNDI — Referrals in the JNDI](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/jndi.html): `Context.REFERRAL`, ba chế độ `ignore`/`follow`/`throw` và ManageDsaIT.
- [Oracle JNDI — LDAP Status Codes and JNDI Exceptions](https://docs.oracle.com/javase/jndi/tutorial/ldap/models/exceptions.html): ánh xạ JNDI exception và mã LDAP theo tài liệu provider.
- [Java SE API — `javax.naming.PartialResultException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/PartialResultException.html): exception checked của JNDI.
- [Spring LDAP API — `PartialResultException`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/PartialResultException.html): runtime exception Spring LDAP tương ứng.
- [Spring LDAP API — `LdapTemplate`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): `setIgnorePartialResultException`, `setIgnoreSizeLimitExceededException` và các thao tác tìm kiếm.
- [Spring LDAP API — `AbstractContextSource`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextSource.html): `setReferral` và cấu hình base DN.
- [Spring LDAP Reference — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): cấu hình referral, search limits và context.
- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696): cookie và phân trang kết quả LDAP.

**Ghi nhớ:** `PartialResultException` là tín hiệu rằng **kết quả tìm kiếm có thể chưa đầy đủ**, thường liên quan referral không được xử lý hết. `ignore`, `follow` và `throw` tạo ra các hành vi khác nhau; `setIgnorePartialResultException(true)` chỉ bỏ qua lỗi, **không tự làm dữ liệu đầy đủ**. Hãy xác định phạm vi, bảo vệ referral targets và thể hiện rõ khả năng thiếu kết quả trước khi dùng dữ liệu cho báo cáo, đồng bộ hay quyết định quyền truy cập.
