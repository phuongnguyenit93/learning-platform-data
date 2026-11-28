# ReferralException, PartialResultException và kết quả chưa đầy đủ

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập dịch vụ thư mục LDAP bằng Spring Data LDAP repository, `LdapTemplate` và các entity được ánh xạ từ entry có DN (*Distinguished Name*), `objectClass`, schema và thuộc tính. Khi tìm kiếm trong một nhánh nhỏ của directory, ứng dụng thường nhận các entry rồi ánh xạ thành DTO. Nhưng trong directory nhiều miền, nhiều naming context hoặc có phân tuyến tới LDAP server khác, một truy vấn còn có thể gặp **referral** hoặc **continuation reference**.

Điều nguy hiểm không chỉ là một exception xuất hiện: **ứng dụng có thể chỉ nhìn thấy một phần kết quả và vẫn tưởng đó là danh sách đầy đủ**. Đối với danh bạ hiển thị, kết quả thiếu có thể gây khó hiểu; với kiểm kê tài khoản, đồng bộ người dùng, ánh xạ nhóm để phân quyền hoặc quyết định xóa dữ liệu, việc coi “thiếu dữ liệu” thành “không có dữ liệu” có thể gây lỗi nghiêm trọng.

Bài thuộc chương **Xử lý lỗi**, giải thích chính xác sự khác biệt giữa `javax.naming.ReferralException`, `javax.naming.PartialResultException` và các runtime exception đã được Spring LDAP chuyển đổi; ý nghĩa của ba chế độ `ignore`/`follow`/`throw`; cách cấu hình `LdapContextSource`, `LdapTemplate`; ranh giới tin cậy khi theo referral; cách xử lý kết quả chưa đầy đủ mà không báo thành công giả.

Mục tiêu học tập:

- Hiểu referral response và search continuation reference trong LDAPv3.
- Biết vì sao `ReferralException` có thể xuất hiện khi **duyệt** `NamingEnumeration`, không chỉ khi gọi `search()`.
- Phân biệt `PartialResultException` với search rỗng và các lỗi size/time limit.
- Biết tác dụng **và rủi ro** của `setIgnorePartialResultException(true)`.
- Thiết kế chính sách **strict completeness** hoặc **best effort có nhãn rõ**, phù hợp từng nghiệp vụ.
- Xác minh endpoint, TLS, credential, ACL, phạm vi DN, referral hop khi có nhiều directory.
- Viết integration test chứng minh cả tình huống đầy đủ và không đầy đủ.

## 1. Referral là gì và nó xuất hiện khi nào?

LDAP tổ chức directory thành cây entry. Một server không nhất thiết nắm toàn bộ dữ liệu của mọi domain hoặc naming context. Nếu thao tác cần đi tới phần cây do server khác quản lý, server có thể trả về một **LDAP URL** để client biết nơi cần tiếp tục tìm.

Ví dụ topology:

```text
                     Client Java
                          |
                          v
              LDAP server A (dc=example,dc=org)
                    /               \
                   v                 v
        ou=employees             ou=partners
        dữ liệu tại A           referral tới server B
                                      |
                                      v
                        LDAP server B (dc=partner,dc=org)
```

Một LDAP URL được server trả về có thể trông như:

```text
ldap://ldap-partner.example.org:389/ou=people,dc=partner,dc=org
```

URL đó là **hướng dẫn đi tới directory khác**, không phải một entry người dùng thông thường. Nó có thể mang host, port, base DN, thuộc tính, scope hoặc filter tùy LDAP URL syntax. Client phải quyết định có theo hay không và theo bằng identity nào.

Trong LDAPv3 có hai tình huống liên quan nhưng không giống nhau:

| Loại | Thời điểm | Nội dung |
|---|---|---|
| **Referral result** | Server không thể thực hiện operation tại vị trí được yêu cầu và trả result code `referral (10)` | LDAP result có danh sách referral URLs |
| **SearchResultReference** (*continuation reference*) | Trong lúc đang duyệt một **search** có nhiều nhánh | Kết quả search gồm các entry thông thường **xen kẽ** tham chiếu tới nơi tìm tiếp |

Ví dụ:

```text
Search dc=example,dc=org, scope=SUBTREE
   |
   +-- SearchResultEntry: uid=lan,ou=employees,...
   +-- SearchResultEntry: uid=binh,ou=employees,...
   +-- SearchResultReference: ldap://ldap-partner.../ou=people,...
   +-- SearchResultDone
```

**Không phải cứ thấy hai entry là đã đọc hết directory.** Nếu có continuation reference chưa được theo, danh sách nhận từ server A chỉ đầy đủ **trong phạm vi server A đã xử lý**, không đầy đủ cho mục tiêu “mọi user ở mọi nhánh”.

### 1.1. Referral khác alias và DN

- **DN:** tên của entry trong LDAP namespace, ví dụ `uid=lan,ou=people,dc=example,dc=org`.
- **Alias:** một entry có thể dẫn đến entry khác trong cùng namespace theo semantics alias dereferencing; cấu hình alias khác referral.
- **Referral:** cơ chế trả đường dẫn LDAP URL, thường tới một server/naming context khác.
- **LDAP URL:** bao gồm endpoint và thông tin search, **không** thể thay thế trực tiếp bằng `LdapName`.

Không nhầm `ContextSource.base` với referral target. Việc chọn một base DN trong Spring LDAP chỉ định phần cây mà context gọi tương đối; nó **không đảm bảo** toàn bộ subtree đó được phục vụ trên cùng một physical server.

## 2. JNDI xử lý referral bằng ignore, follow hoặc throw

LDAP provider của JNDI đọc cấu hình `Context.REFERRAL`, tương đương khóa environment `java.naming.referral`:

```java
import javax.naming.Context;
import java.util.Hashtable;

Hashtable<String, Object> env = new Hashtable<>();
env.put(Context.REFERRAL, "ignore"); // Hoặc "follow", "throw".
```

Ba chế độ:

| Chế độ | Ý nghĩa | Đánh đổi |
|---|---|---|
| `ignore` | Bảo provider không theo referral | Kết quả có thể thiếu nhánh; một số server/provider vẫn trả `PartialResultException` |
| `follow` | Provider thử tự động theo referral | Có thể truy cập thêm LDAP host, tốn thời gian, đụng ACL/TLS/DNS/credentials; cần kiểm soát ranh giới tin cậy |
| `throw` | Ném JNDI `ReferralException` để ứng dụng tự quyết | Cần tự quản lý context, referral URLs, giới hạn hop, credential và resource |

Theo tài liệu JNDI, mặc định là `ignore` nếu không cấu hình. Khi `ignore` với LDAPv3, provider có thể gửi **Manage Referral/ManageDsaIT control** tới server để yêu cầu xem referral entry như entry thông thường. Nếu server vẫn trả referral/continuation reference mà không tuân theo control, provider có thể ném `PartialResultException`. Vì vậy:

> `ignore` không phải lời hứa rằng search luôn thành công hoặc dữ liệu được trả về đầy đủ.

Với `follow`, provider có thể theo referral sau khi đã trả các local entry của search. Với `throw`, `ReferralException` liên quan continuation reference có thể xuất hiện **ở cuối vòng duyệt**, sau một số entry bình thường. Cách ứng xử này khác với referral result làm operation bị chuyển hướng ngay.

### 2.1. Cấu hình trong Spring LDAP

`LdapContextSource` kế thừa `AbstractContextSource` và hỗ trợ:

```java
LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://ldap.example.org:636");
source.setBase("dc=example,dc=org");
source.setReferral("ignore"); // "follow" hoặc "throw" khi thiết kế đã duyệt.
```

`source.setReferral("ignore")` tác động đến **provider/JNDI context**, không phải nút bật/tắt hoàn toàn mọi ngoại lệ của `LdapTemplate`. Sau đó `LdapTemplate` còn có cờ riêng để quyết định có **bỏ qua** `PartialResultException` đã phát sinh hay không.

Không tạo một `LdapContextSource` mới cho từng request chỉ để đổi referral mode. Chọn chính sách theo **loại nghiệp vụ, directory và ranh giới quyền**; cấu hình qua bean/qualifier rõ ràng. Nếu phải dùng mode khác nhau, nên có context/template chuyên biệt thay vì thay đổi thuộc tính shared bean trong khi nhiều request đang chạy.

## 3. ReferralException: yêu cầu xử lý chuyển hướng

Trong JNDI:

```text
javax.naming.ReferralException
    |
    +-- javax.naming.ldap.LdapReferralException (provider/JNDI)
```

`ReferralException` là ngoại lệ có API để xử lý referral:

- `getReferralInfo()`: lấy thông tin hướng dẫn tham chiếu, thường là LDAP URL hoặc cấu trúc provider cung cấp.
- `getReferralContext()` hoặc `getReferralContext(env)`: lấy context tới referral target.
- `skipReferral()`: bỏ qua referral đang xét và xem có referral khác không.
- `retryReferral()`: thử lại referral hiện tại sau khi điều chỉnh thông tin.

Đây là các API **ở JNDI layer**. Khi dùng Spring `LdapTemplate`, `NamingException` checked của JNDI thường được chuyển sang **runtime exception** trong package `org.springframework.ldap`; ví dụ `org.springframework.ldap.ReferralException` hoặc `org.springframework.ldap.LdapReferralException`. Runtime wrapper không có cùng hợp đồng xử lý referral context như JNDI checked exception.

**Không viết code `catch (javax.naming.ReferralException)` quanh `ldapTemplate.search(...)` rồi kỳ vọng bắt được mọi referral**. Với đường xử lý chuẩn của Spring LDAP, hãy kiểm tra loại Spring runtime exception hoặc nguyên nhân gốc. Muốn kiểm soát vòng đời referral bằng `getReferralContext()`, thường cần đường JNDI trực tiếp hoặc một tích hợp provider chuyên biệt.

### 3.1. ReferralException có thể phát sinh giữa lúc duyệt

Ví dụ JNDI **cố ý không tự follow** để quan sát đúng điểm lỗi:

```java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.PartialResultException;
import javax.naming.ReferralException;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

public final class ReferralProbe {

    public static void main(String[] args) throws Exception {
        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
                "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL,
                "ldaps://ldap.example.org:636");
        env.put(Context.REFERRAL, "throw");
        env.put(Context.SECURITY_AUTHENTICATION, "simple");
        env.put(Context.SECURITY_PRINCIPAL,
                "cn=reader,ou=service,dc=example,dc=org");
        env.put(Context.SECURITY_CREDENTIALS,
                System.getenv("LDAP_BIND_PASSWORD"));

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid", "cn"});

        DirContext context = new InitialDirContext(env);
        NamingEnumeration<SearchResult> results = null;

        try {
            results = context.search(
                    "dc=example,dc=org",
                    "(objectClass=inetOrgPerson)",
                    controls);

            // hasMore() HOẶC next() có thể ném NamingException/referral.
            while (results.hasMore()) {
                SearchResult entry = results.next();
                System.out.println("local entry: " + entry.getName());
            }
        } catch (ReferralException ex) {
            // Đã thấy local entry chưa có nghĩa đã đọc hết directory.
            // Không tự follow URL chưa được xác minh!
            throw new IllegalStateException(
                    "Cần xử lý referral theo chính sách tin cậy", ex);
        } catch (PartialResultException ex) {
            throw new IllegalStateException(
                    "JNDI chỉ có một phần kết quả", ex);
        } finally {
            if (results != null) {
                results.close();
            }
            context.close();
        }
    }
}
```

Ví dụ dành cho **LDAP test directory**, giả định đã cấp đúng server URL, CA/truststore và password qua biến môi trường. Không bật debug in credential. Code cố ý **dừng** khi gặp referral, không theo referral; đây là một trình quan sát lỗi, **không phải bộ search xuyên directory hoàn chỉnh**.

Điểm đáng nhớ: `try/catch` bao quanh cả `context.search(...)` và vòng `while (results.hasMore())`. Nếu chỉ bắt lỗi ở lệnh gọi `search`, có thể bỏ sót `ReferralException` đến **sau các entry đầu tiên**.

### 3.2. Khi phải tự theo referral bằng JNDI

Quy trình an toàn ở mức thiết kế:

1. Nhận `ReferralException`, đọc referral information từ provider nhưng xem đó là **dữ liệu chưa tin cậy**.
2. Parse LDAP URL và áp dụng **allowlist host/port/protocol/naming context**; bảo đảm TLS certificate và hostname được xác minh.
3. Giới hạn số hop, số target, thời gian tìm kiếm, kích thước kết quả và xử lý vòng lặp.
4. Chọn **credential riêng có quyền tối thiểu** cho target; không mặc định chuyển bind password của server A sang server B.
5. Gọi `getReferralContext(env)` chỉ sau khi policy đã chấp nhận target; chạy lại operation với tham số phù hợp.
6. Đóng context/enumeration đúng cách, đánh dấu từng partition thành công/thất bại.
7. Nếu có target không đọc được, trả trạng thái **INCOMPLETE/FAILED**, không gộp vào thành “không có user”.

Oracle JNDI nêu rõ `getReferralContext()` không tham số có thể kế thừa environment từ context cũ, **bao gồm các thông tin bảo mật**. Với `follow` tự động, provider cũng có thể dùng credential gốc cho referral target theo cấu hình. Vì vậy, **credential forwarding** là vấn đề an toàn thực tế, không phải chỉ là lỗi mạng.

**Không triển khai logic thủ công dựa vào `ex.getReferralInfo().toString()` rồi nối với một URL tùy ý.** Referral info có cấu trúc do provider quyết định; một LDAP URL cần được parse đúng và kiểm chứng. Với workload nhạy cảm, chủ động cấu hình danh sách directory được phép rồi search từng endpoint có thể dễ audit hơn việc follow referral động.

## 4. PartialResultException: đã trả đủ kết quả hay chưa?

Trong JNDI:

```text
javax.naming.PartialResultException
```

Đây là một `NamingException` cho biết provider **không thể trả toàn bộ kết quả lẽ ra có thể có**. Với LDAP, nó thường xuất hiện khi không thể xử lý referral, ví dụ server vẫn trả continuation references dù mode là `ignore`.

Trong Spring LDAP, lỗi được chuyển thành runtime:

```text
org.springframework.ldap.PartialResultException
```

Hai lớp có **tên giống nhau nhưng ở hai package khác nhau**. Khi viết code catch ở tầng service đang dùng `LdapTemplate`, cần import đúng loại **Spring**:

```java
import org.springframework.ldap.PartialResultException;
```

### 4.1. “Partial” khác “không tìm thấy”

Ví dụ query tìm thành viên nhóm `cn=admins`:

```text
LDAP partition A:
  uid=lan,ou=employees,...
  uid=binh,ou=employees,...

LDAP partition B (được referral đến):
  uid=mai,ou=partners,...

Nếu chỉ lấy partition A, kết quả = [lan, binh].
Nếu mục tiêu là toàn bộ A + B, kết quả này là INCOMPLETE.
```

Không được suy ra:

```text
Không thấy uid=mai trong list
=> uid=mai không tồn tại
=> chắc chắn có thể xóa tài khoản/cấp quyền/thu hồi dữ liệu
```

Đúng hơn:

```text
Không thấy uid=mai trong nguồn đã khảo sát
+ có referral chưa xử lý
=> CHƯA ĐỦ THÔNG TIN để kết luận uid=mai không tồn tại.
```

Đối với API “tìm chính xác người trong OU nội bộ”, nếu OU nội bộ là **nguồn authoritative** và không cần đi theo referral ngoài OU, ứng dụng có thể chấp nhận phạm vi đó là đầy đủ **cho contract đã định nghĩa**. Nhưng với API “tìm mọi người trên cả forest”, không thể chấp nhận cùng một danh sách như kết quả toàn cục.

### 4.2. PartialResultException không nói rõ tỷ lệ kết quả còn thiếu

Đừng coi tên lỗi là “đã trả đúng 50% dữ liệu” hay “chỉ thiếu một entry”. Exception không chứa tỷ lệ phần trăm đáng tin cậy. Dữ liệu có thể đã được trả đến callback hoặc enumeration **trước khi lỗi xuất hiện**, song không có bảo đảm nó bao phủ mọi partition.

Một ngoại lệ khác có thể dẫn đến thiếu kết quả, ví dụ size/time limit, ACL, referral loop, server down, paged-results cookie lỗi. **Không dựa vào mỗi loại `PartialResultException` để chứng minh kết quả hoàn chỉnh**.

## 5. LdapTemplate.setIgnorePartialResultException(true): tác dụng và rủi ro

Spring LDAP có phương thức:

```java
LdapTemplate ldapTemplate = new LdapTemplate(contextSource);
ldapTemplate.setIgnorePartialResultException(true);
```

Theo Javadoc Spring LDAP, cờ mặc định là **`false`**. Khi bật `true`, `LdapTemplate` bỏ qua JNDI `PartialResultException` trong quá trình search — một workaround từng được dùng với một số topology Active Directory có hành vi referral khó xử lý.

**Điều cờ này KHÔNG làm:**

- Không tự động follow referral tới target khác.
- Không bổ sung entry từ partition không truy cập được.
- Không sửa lỗi DNS, TLS, ACL hoặc sai bind credential.
- Không đảm bảo `List<T>` trả về là **toàn bộ** kết quả mong đợi.
- Không cung cấp một cờ `partial=true` cho caller khi exception bị bỏ qua.

Khi bỏ qua, template có thể trả về **những entry đã thu thập được tới thời điểm lỗi**, hoặc không có entry phù hợp trong phần nó đã khảo sát. Caller không nên coi đó là một danh sách hoàn chỉnh của directory.

### 5.1. Hai cấu hình, hai contract khác nhau

**Cấu hình strict (mặc định đề xuất cho nghiệp vụ đòi completeness):**

```java
LdapTemplate strictTemplate = new LdapTemplate(contextSource);
strictTemplate.setIgnorePartialResultException(false);
strictTemplate.setIgnoreSizeLimitExceededException(false);
strictTemplate.setIgnoreNameNotFoundException(false);
```

**Cấu hình cho màn hình best-effort có chủ đích:**

```java
LdapTemplate bestEffortTemplate = new LdapTemplate(contextSource);
bestEffortTemplate.setIgnorePartialResultException(true);

// Không gọi template này từ luồng kiểm kê/cấp quyền cần dữ liệu đầy đủ.
```

Nếu bật `ignorePartialResultException=true`, **caller không biết chắc lần gọi vừa rồi có bị partial hay không** chỉ từ return value. Vì vậy API phải có contract cố định kiểu “danh sách trong vùng local / không đảm bảo toàn bộ forest”; không nên gắn cờ `complete=true` cho từng invocation mà bạn không thể chứng minh.

Đừng sửa một bean `LdapTemplate` toàn ứng dụng sang `ignore=true` chỉ để hết exception trên một màn hình; hành vi đó có thể thay đổi ngầm ý nghĩa của các chức năng khác, như đồng bộ danh bạ hay xác thực quyền nhóm.

### 5.2. Cảnh báo mặc định liên quan SizeLimitExceededException

`LdapTemplate` còn có:

```java
ldapTemplate.setIgnoreSizeLimitExceededException(false);
```

Javadoc Spring LDAP hiện hành nêu mặc định của **`ignoreSizeLimitExceededException` là `true`** (vì một số search chủ ý đặt count limit). Do đó, **một phép search không ném `PartialResultException` không đủ để bảo đảm completeness**: quá trình có thể bị giới hạn kết quả mà người viết không phát hiện theo chính sách mặc định.

Nếu nghiệp vụ cần biết **toàn bộ entry trong scope**, hãy kiểm tra cả `SearchControls.countLimit`, server-side administrative size limit, time limit, paging policy và cách hạ tầng trả các lỗi liên quan. Cờ `ignoreSizeLimitExceededException=false` giúp không âm thầm nuốt lỗi size limit khi server/provider phát sinh exception, nhưng không thay thế cơ chế phân trang hoặc snapshot consistency.

**Ví dụ:** `.countLimit(100)` cố tình đặt trần 100 kết quả. Ngay cả khi không có exception, nó chỉ có nghĩa “tối đa 100 entry”, **không** phải “directory chỉ có 100 entry”.

## 6. Chọn chính sách cho từng loại nghiệp vụ

Đề xuất phân biệt:

| Nghiệp vụ | Mức hoàn chỉnh yêu cầu | Chiến lược hợp lý |
|---|---|---|
| Autocomplete tên trong OU nội bộ | Có thể chấp nhận best effort | Giới hạn base rõ, trả tối đa N gợi ý, không suy ra uniqueness toàn forest |
| Trang danh bạ trong một domain authoritative | Đầy đủ **trong domain đó** | Search trực tiếp domain, kiểm tra ACL/limit, không hứa toàn forest |
| Danh sách tài khoản phục vụ audit | Cần đầy đủ theo scope audit | Strict; nếu một partition fail, báo incomplete/failed |
| Đồng bộ mọi tài khoản từ nhiều domain | Cần đầy đủ hoặc có checkpoint rõ | Fan-out tới nguồn tin cậy, ghi completion per source, reconciliation |
| Kiểm tra “user X không tồn tại trong tổ chức” | Cần dữ liệu đầy đủ toàn bộ nguồn liên quan | Không kết luận `false` chỉ từ một search partial |
| Tính thành viên nhóm để cấp quyền | Yêu cầu bảo mật cao | Dùng nguồn authoritative, fail closed nếu lookup nhóm thiếu; quy tắc nested/primary group rõ |
| Xóa bản ghi đích không còn tồn tại ở LDAP | Cực kỳ nhạy cảm với false negative | Không xóa nếu bất kỳ source liên quan chưa hoàn tất |

Điểm quan trọng là **định nghĩa completeness theo hợp đồng**:

```text
complete = tất cả nguồn có trách nhiệm cho phạm vi đã định
           được truy vấn/kiểm tra thành công
           với filter/scope/ACL/limit đã xác minh.
```

Không nhất thiết phải tìm **mọi entry trên mọi LDAP server** trong tất cả API. Nhưng phải biết rõ **nguồn nào authoritative** đối với từng yêu cầu và không gắn nhãn “đủ” khi còn referral/partition chưa được giải quyết.

## 7. Cấu hình Spring LDAP: mặc định nghiêm ngặt

Ví dụ Spring Boot + Java 17 với `LdapContextSource` riêng cho directory nội bộ, endpoint LDAPS, một tài khoản chỉ đọc và `LdapTemplate` có chính sách phát hiện lỗi.

**`DirectoryConfiguration.java`**

```java
package com.example.ldap;

import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConfiguration {

    @Bean("internalContextSource")
    LdapContextSource internalContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setReferral("ignore");
        source.setPooled(false); // Không trộn native JNDI pooling ngoài ý muốn.
        source.setBaseEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout", "3000",
                "com.sun.jndi.ldap.read.timeout", "5000"));
        return source;
    }

    @Bean("strictLdapTemplate")
    LdapTemplate strictLdapTemplate(
            @Qualifier("internalContextSource")
            LdapContextSource source) {

        LdapTemplate template = new LdapTemplate(source);
        template.setIgnorePartialResultException(false);
        template.setIgnoreSizeLimitExceededException(false);
        template.setIgnoreNameNotFoundException(false);
        return template;
    }
}
```

**`application.yml` — chỉ minh họa secret reference**

```yaml
app:
  ldap:
    url: ldaps://ldap.internal.example.org:636
    base: dc=example,dc=org
    bind-dn: cn=directory-reader,ou=service,dc=example,dc=org
    bind-password: ${LDAP_BIND_PASSWORD}
```

**Phải hiểu ý nghĩa cấu hình:** `source.setReferral("ignore")` nghĩa là scope của service **không chủ động theo referral**. Kết hợp `setIgnorePartialResultException(false)` cho phép báo lỗi khi provider nhận referral mà không xử lý được. Tuy nhiên, việc `ignore` cùng ManageDsaIT khiến provider/server không báo mọi referral là một exception trong mọi trường hợp; một search trả về bình thường **chỉ đủ cơ sở kết luận cho nguồn đã xác minh là authoritative**.

Không dùng một câu lệnh `source.setReferral("follow")` để biến toàn bộ hệ thống thành “cross-domain search an toàn” trước khi kiểm tra TLS, credential forwarding, hop limit, ACL và tính duy nhất của DN.

### 7.1. Nếu có hai chính sách, dùng hai bean

Để tránh side effect của việc thay đổi flags lúc runtime:

```java
@Bean("suggestionLdapTemplate")
LdapTemplate suggestionLdapTemplate(
        @Qualifier("internalContextSource")
        LdapContextSource source) {
    LdapTemplate template = new LdapTemplate(source);
    template.setIgnorePartialResultException(true);
    return template;
}
```

Đoạn này là **method bổ sung trong class cấu hình** ở trên. Việc tạo hai template không tự tạo hai LDAP endpoints; cả hai dùng một `ContextSource` nên có cùng `Context.REFERRAL` policy. Để chọn `follow`/`throw` theo nghiệp vụ, cần context source **riêng** được cấu hình rõ.

`suggestionLdapTemplate` chỉ hợp lý cho API có hợp đồng **best effort** và biết rõ không cần dữ liệu từ các referral. **Không** dùng cho tổng hợp số lượng user toàn tổ chức, quyết định cấp quyền hoặc xóa dữ liệu dựa trên việc không tìm thấy entry.

## 8. Service phân loại lỗi thay vì trả list rỗng

Một lỗi phổ biến:

```java
// KHÔNG làm thế này:
try {
    return ldapTemplate.search(query, mapper);
} catch (Exception ex) {
    return List.of(); // Biến LDAP outage/referral thành "không có user".
}
```

Thiết kế tốt hơn là chuyển exception từ tầng kết nối thành **lỗi có nghĩa với nghiệp vụ**, rồi phân biệt được:

- Tìm không có entry **sau một query hoàn chỉnh trong nguồn authoritative**.
- Không đọc được toàn bộ do referral, giới hạn hoặc timeout.
- Bind/ACL/schema sai.
- LDAP server tạm ngắt, có thể retry có kiểm soát.

### 8.1. Domain exception báo incompleteness

**`DirectoryIncompleteException.java`**

```java
package com.example.ldap;

public class DirectoryIncompleteException extends RuntimeException {
    public DirectoryIncompleteException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

**`DirectorySearchService.java`**

```java
package com.example.ldap;

import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.PartialResultException;
import org.springframework.ldap.ReferralException;
import org.springframework.ldap.SizeLimitExceededException;
import org.springframework.ldap.TimeLimitExceededException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class DirectorySearchService {
    private final LdapTemplate ldapTemplate;

    public DirectorySearchService(
            @Qualifier("strictLdapTemplate") LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findUidsWithinAuthoritativeOu(String surname) {
        if (surname == null || surname.isBlank()) {
            throw new IllegalArgumentException("surname không được rỗng");
        }

        LdapQuery search = query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("sn").is(surname);

        AttributesMapper<String> mapper = attrs ->
                (String) attrs.get("uid").get();

        try {
            return ldapTemplate.search(search, mapper);
        } catch (PartialResultException | ReferralException ex) {
            throw new DirectoryIncompleteException(
                    "Truy vấn LDAP không bao phủ đầy đủ phạm vi", ex);
        } catch (SizeLimitExceededException | TimeLimitExceededException ex) {
            throw new DirectoryIncompleteException(
                    "Truy vấn LDAP bị giới hạn trước khi hoàn tất", ex);
        }
    }
}
```

Trong code trên:

1. `PartialResultException` và `ReferralException` là các **runtime exception thuộc `org.springframework.ldap`**, khác các lớp `javax.naming.*` ở JNDI.
2. `.where("sn").is(surname)` xây filter đúng cú pháp từ dữ liệu input, tránh LDAP filter injection do nối chuỗi.
3. Service không trả một danh sách rỗng khi có lỗi; caller biết **không được dùng kết quả để kết luận người dùng vắng mặt**.
4. Những lỗi khác như `CommunicationException`, `AuthenticationException` hay `NoPermissionException` **không được biến thành “không tìm thấy”**; lớp API/global error handler phân loại riêng.
5. Phương thức vẫn chỉ có nghĩa **“trong OU authoritative”**. Một truy vấn chạy thành công không tự đảm bảo đầy đủ toàn forest nếu search policy không bao phủ các partition khác.

Ví dụ giả định entry có `uid` đơn trị, được trả về cho tài khoản bind. Khi `uid` thiếu/ẩn bởi ACL, mapper có thể phát sinh lỗi và phải được xử lý như lỗi dữ liệu/quyền, không tự trả `null` rồi coi entry không tồn tại.

### 8.2. Không biến incomplete thành 404

Với một HTTP API:

```text
GET /api/people?sn=Nguyen
    |
    +-- LDAP search complete, list=[] -> 200 [] (không khớp trong scope)
    |
    +-- LDAP partial/referral chưa giải quyết -> lỗi có ý nghĩa, ví dụ 503
    |
    +-- LDAP ACL không đủ quyền -> lỗi hệ thống/permission, không giả 404
    |
    +-- Query sai do input -> 400 theo validation của API
```

`503 Service Unavailable` có thể phù hợp với phụ thuộc directory không thể cung cấp dữ liệu cần thiết tại thời điểm đó. `502 Bad Gateway` cũng có thể phù hợp với một gateway tùy kiến trúc; đây là **quy ước API**, không phải LDAP result code. Nếu client được phép nhận dữ liệu một phần, thiết kế response kiểu `complete=false`, `coveredSources` và `failedSources` rõ ràng, không chỉ trả HTTP 200 cùng một danh sách trần.

Ví dụ contract JSON best effort:

```json
{
  "complete": false,
  "scope": "employee-directory",
  "coveredSources": ["domain-a"],
  "failedSources": ["domain-b"],
  "items": [
    {"uid": "lan", "displayName": "Lan Nguyen"}
  ]
}
```

**Không dùng response trên làm đầu vào duy nhất cho kiểm kê hay xóa tài khoản** nếu `complete=false`. Các trường được chọn là contract minh họa do ứng dụng định nghĩa, không phải response mặc định của `LdapTemplate`.

## 9. Không phải mọi kết quả thiếu đều ném PartialResultException

Một bộ kiểm tra độ đầy đủ cần xét nhiều nguyên nhân:

| Tình huống | Lỗi/biểu hiện thường gặp | Cần hiểu |
|---|---|---|
| JNDI mode `ignore` nhưng vẫn gặp continuation reference | `javax.naming.PartialResultException`; Spring chuyển thành runtime tương ứng | Một phần kết quả chưa được duyệt |
| Mode `throw` gặp referral | `javax.naming.ReferralException` (JNDI) | Cần xử lý referral hoặc tuyên bố incomplete |
| Mode `follow` nhưng referral target không truy cập được | Có thể có communication/authentication/naming error | Không suy ra empty; cần xác định partition nào fail |
| Server áp đặt size limit | `SizeLimitExceededException` hoặc tập kết quả bị chặn theo provider | Chưa chắc có toàn bộ entry |
| Server time limit | `TimeLimitExceededException` hoặc request timeout | Không coi phần đã nhận là hoàn tất |
| Client chủ động `countLimit(100)` | Tối đa 100 entry, có thể không có exception | Hợp đồng query có giới hạn; không kết luận chỉ có 100 |
| Paged-results cookie hết hạn | Lỗi control/cookie hoặc kết nối không còn cùng phiên | Batch chưa hoàn tất dù đã đọc vài trang |
| ACL không cho xem entry/attribute | Có thể search không trả entry hoặc thiếu thuộc tính | “Không nhìn thấy” khác “không tồn tại” |
| Base DN không tồn tại | `NameNotFoundException` nếu không bị bỏ qua | Search cấu hình sai hoặc nhánh đã đổi |
| Referral loop/hop limit | Lỗi provider hoặc vượt giới hạn referral | Không retry vô hạn |
| Entry đổi DN trong khi duyệt | Entry có thể bị bỏ sót/lặp tùy server và paging | Không có snapshot toàn cục mặc định |

Đặc biệt, `ignoreSizeLimitExceededException=true` mặc định ở `LdapTemplate` có thể làm workflow bị giới hạn mà không được xử lý theo mong đợi. Khi cần kiểm kê đầy đủ, phải **đặt rõ policy cho mọi giới hạn** và kiểm thử trên server thực.

**Một API có ít kết quả không đồng nghĩa với một API bị lỗi**: nếu hợp đồng chỉ tìm tối đa 20 gợi ý trong một nhánh cố định, list 20 có thể là phản hồi đúng **cho API gợi ý**. Vấn đề là dùng list đó như một bản sao đầy đủ của directory.

## 10. Active Directory, nhiều domain và Global Catalog

Trong Active Directory (AD), một forest có thể gồm nhiều domain/naming context. Search theo subtree qua một domain controller có thể gặp referral sang domain khác. Spring LDAP từng ghi rõ trường hợp AD tự động theo referral không hoạt động như kỳ vọng, dẫn đến `PartialResultException`.

**Không nên dùng workaround `ignorePartialResultException(true)` làm thiết kế chính cho tác vụ yêu cầu toàn forest.** Một số hướng tiếp cận:

- **Search đúng domain/naming context authoritative** khi nghiệp vụ chỉ cần domain đó.
- **Search qua Global Catalog** (thường LDAP ports 3268 hoặc LDAPS 3269) nếu hạ tầng AD và yêu cầu thuộc tính phù hợp. GC có **partial attribute set** và hành vi nhóm/quyền phụ thuộc AD; không mặc định mọi thuộc tính của mọi entry đều có.
- **Khai báo các domain endpoints tin cậy** và truy vấn từng domain bằng credential/ACL được phê duyệt, tổng hợp kết quả và completion state theo nguồn.
- Với đồng bộ yêu cầu không bỏ sót thay đổi, dùng **cơ chế change tracking/incremental sync** do AD/backend hỗ trợ và đối soát, không chỉ một lần search toàn cây.
- Với nested group, primary group hoặc group membership đặc thù AD, xác minh matching rules, `memberOf`/`tokenGroups` và giới hạn ACL trước khi dùng làm quyền.

Một DN đầy đủ có thể **không duy nhất trên hai directory độc lập** theo cách một ứng dụng multi-tenant kỳ vọng. Khi tổng hợp nhiều nguồn, định danh kết quả nên đi kèm **directory/source ID** và, nếu có, stable entry ID theo backend; không gộp mọi entry theo `uid` đơn lẻ.

### 10.1. Khi nào dùng follow?

`source.setReferral("follow")` có thể phù hợp khi:

- Referral targets **đều nằm trong mạng/tập endpoint được tin cậy**.
- Chính sách TLS/hostname và credential forwarding đã được rà soát.
- Referral depth, retry, timeout, kết quả đa nguồn và ACL có kiểm soát.
- Test chứng minh kết quả thực sự đầy đủ trong phạm vi nghiệp vụ.

Không nên bật `follow` từ một search input tùy ý với tài khoản bind có quyền cao. Referral URL được server trả về và có thể dẫn tới endpoint không mong đợi. Chọn `follow` không thay thế network allowlist, TLS và monitoring.

## 11. Thiết kế fan-out: tránh phụ thuộc referral động

Khi cần tổng hợp từ nhiều directory **đã biết trước**, một giải pháp dễ audit là cấu hình danh sách nguồn:

```text
                         DirectoryAggregationService
                          /           |             \
                         v            v              v
                Source A            Source B          Source C
                domain-a            domain-b          partner-x
                LDAPS               LDAPS             LDAPS
                  |                   |                 |
                COMPLETE            FAILED           COMPLETE
                  \                   |                 /
                   +------------------+----------------+
                                      |
                                      v
                Overall result: INCOMPLETE (không báo SUCCESS)
```

Thay vì một `LdapTemplate` bí mật follow URL bất kỳ, mỗi source có:

1. LDAP endpoint/naming context và source ID cố định.
2. Bind identity/credential tối thiểu, TLS policy riêng.
3. Search base, filter, returning attributes và giới hạn được kiểm chứng.
4. Status từng nguồn: `COMPLETE`, `INCOMPLETE` hoặc `FAILED`.
5. Chính sách dedup theo source/entry identity, không chỉ theo `uid`.
6. Timeout, retry, circuit breaker và quan sát từng source.

Ví dụ mô hình Java chỉ diễn tả **hợp đồng dữ liệu**, không phải một LDAP aggregator hoàn chỉnh:

```java
public enum SourceStatus {
    COMPLETE,
    INCOMPLETE,
    FAILED
}

public record SourceBatch<T>(
        String sourceId,
        SourceStatus status,
        java.util.List<T> entries
) {}

public record AggregationReport<T>(
        boolean complete,
        java.util.List<SourceBatch<T>> sources
) {}
```

Một báo cáo có `complete=true` chỉ khi **mọi source bắt buộc** đều complete theo chính sách nghiệp vụ; đừng bỏ một source bị timeout khỏi danh sách rồi báo mọi nguồn còn lại đã thành công.

**Cẩn trọng với side effects:** nếu đang duyệt một stream LDAP và ghi lần lượt vào database đích, `PartialResultException` xuất hiện ở cuối enumeration có thể khiến một số entry đã được ghi. Cần staging, batch status, checkpoint, idempotency và cơ chế commit/reconciliation; không chỉ catch exception ở cuối rồi giả sử hệ thống đích chưa thay đổi.

## 12. Kết quả partial và nguy cơ phân quyền sai

Một ví dụ nhạy cảm: ứng dụng xác định người dùng có thuộc `cn=app_editors` hay không bằng cách tìm nhóm LDAP. Nếu nguồn chứa nhóm được referral đến domain khác:

```text
LDAP A: tìm thấy user Lan
LDAP B: giữ nhóm app_editors, nhưng không truy cập được

Sai:
  findGroups(Lan) -> []
  "không có dữ liệu" = "không thuộc nhóm"

Đúng:
  tìm nhóm chưa đầy đủ
  -> không kết luận quyền một cách khẳng định
  -> áp dụng chính sách fail closed + báo lỗi hệ thống
```

**Fail closed** khi cấp quyền thường là không cấp quyền chưa được chứng minh. Nhưng cũng phải phân biệt:

- Không cấp thêm quyền đặc biệt vì nguồn chưa xác minh được là phù hợp.
- Không tự động **xóa vĩnh viễn** membership/hồ sơ đích chỉ vì LDAP search rỗng.
- Không dùng “missing due to partial” để suy ra một tài khoản không tồn tại.
- Không gán mọi LDAP outage là “sai mật khẩu”. Authentication server không sẵn sàng là tình huống khác `invalidCredentials`.

Đối với các thao tác xác thực, cập nhật session/authority cache hoặc thu hồi quyền, cần xác định TTL, replication delay và chính sách đọc nguồn authoritative. LDAP search hoàn chỉnh ở một replica cũng không tự có nghĩa đã nhìn thấy thay đổi mới nhất từ writable server.

## 13. Xử lý exception theo từng lớp

Hãy phân biệt lỗi có cùng tên ở JNDI và Spring LDAP:

| Tình huống | JNDI checked exception | Spring LDAP runtime counterpart |
|---|---|---|
| Referral cần xử lý | `javax.naming.ReferralException` | `org.springframework.ldap.ReferralException` (có thể có `LdapReferralException`) |
| Kết quả bị thiếu | `javax.naming.PartialResultException` | `org.springframework.ldap.PartialResultException` |
| Vượt size limit | `javax.naming.SizeLimitExceededException` | `org.springframework.ldap.SizeLimitExceededException` |
| Vượt time limit | `javax.naming.TimeLimitExceededException` | `org.springframework.ldap.TimeLimitExceededException` |
| Search base/entry không tồn tại | `javax.naming.NameNotFoundException` | `org.springframework.ldap.NameNotFoundException` |
| ACL từ chối | `javax.naming.NoPermissionException` | `org.springframework.ldap.NoPermissionException` |
| Giao tiếp lỗi | `javax.naming.CommunicationException` | `org.springframework.ldap.CommunicationException` |

Các lớp Spring là runtime wrapper theo cơ chế exception translation. Trong Spring Data LDAP repository, lỗi có thể đi qua proxy/abstraction khác hoặc được bọc trong `DataAccessException` tùy đường xử lý; khi viết catch đặc thù, hãy kiểm tra loại thực tế và **root cause** của phiên bản Spring LDAP đang dùng.

### 13.1. Đừng dựa vào message để phân loại

Không nên:

```java
// Sai: messages thay đổi theo provider, bản địa hóa và phiên bản.
if (ex.getMessage().contains("PartialResultException")) {
    return List.of();
}
```

Nên dựa vào **type + cause + operation context**, sau đó map thành error code riêng, ví dụ:

```text
DIRECTORY_REFERRAL_UNRESOLVED
DIRECTORY_INCOMPLETE
DIRECTORY_SIZE_LIMIT
DIRECTORY_TIME_LIMIT
DIRECTORY_PERMISSION_DENIED
DIRECTORY_UNAVAILABLE
DIRECTORY_ENTRY_NOT_FOUND
```

Các mã trên là **mã ứng dụng đề xuất**, không phải LDAP result code. Dùng error code ổn định cho HTTP response, audit và metric, không xuất DN/credential/referral URL chưa kiểm duyệt cho người dùng cuối.

### 13.2. Retry phải dựa vào bản chất lỗi

| Lỗi | Retry? | Lưu ý |
|---|---|---|
| Communication timeout thoáng qua | Có thể, với backoff/jitter và giới hạn | Query đọc có thể retry; tránh storm khi directory down |
| Referral cần theo nhưng target không được duyệt | **Không retry mù** | Cần cấu hình topology/allowlist/credential |
| `PartialResultException` do mode `ignore` | Không sửa được bằng retry vô hạn | Điều chỉnh scope/referral policy hoặc nguồn dữ liệu |
| Size limit | Không retry y nguyên query | Thu hẹp scope, projection, paging, tăng quota có kiểm soát |
| Time limit do filter đắt | Đầu tiên tối ưu filter/index/scope | Retry liên tục có thể làm server quá tải |
| ACL bị từ chối | Không retry với cùng identity | Cần quyền/config phù hợp |
| Search base không tồn tại | Không retry mù | Kiểm tra DN, naming context, rename, tenant |
| Truy vấn nhóm phục vụ phân quyền | Chỉ retry có giới hạn nếu tạm lỗi | Không cấp quyền khi chưa xác minh được |

Với một thao tác **ghi** LDAP như Add/Modify/Delete, lỗi mạng sau khi gửi yêu cầu có thể xảy ra **sau khi server đã commit**. Không áp dụng chính sách retry của search đọc cho ghi mà không có idempotency, revision guard hoặc kiểm tra outcome.

## 14. Quan sát kết quả chưa đầy đủ

Không thể vận hành an toàn nếu mọi exception đều bị nuốt và chỉ còn danh sách trống.

Metric/log nên có:

- Tổng số LDAP searches theo `sourceId`, `operation`, `resultStatus`.
- `referral_encountered`, `referral_follow_failed`, `partial_result_ignored` nếu instrumentation thực sự quan sát được.
- `ldap_search_duration` p50/p95/p99 và số entry trả về/trang.
- `size_limit_exceeded`, `time_limit_exceeded`, `communication_error`, `authentication_error`.
- Số partition bắt buộc, thành công, chưa hoàn tất trong aggregation job.
- Số job audit/sync ở trạng thái `COMPLETE`, `INCOMPLETE`, `FAILED`.

Khi `setIgnorePartialResultException(true)`, Spring LDAP có thể chỉ log ở mức debug rằng lỗi đã bị bỏ qua. **Không giả định có counter `partial_result_ignored` mặc định**; nếu cần metric chính xác, phải bổ sung instrumentation ở lớp phù hợp hoặc chọn strict mode để quan sát exception.

Ví dụ structured log:

```text
event=directory_search
source_id=domain-a
scope=employees
outcome=INCOMPLETE
reason=REFERRAL_UNRESOLVED
entry_count_so_far=25
request_id=abc123
```

Đây là mẫu log do ứng dụng định nghĩa. Không đưa full DN người dùng, LDAP bind password, raw LDAP filter có input cá nhân hoặc referral credentials vào metrics/tags/log không được bảo vệ. Referral URLs có thể làm lộ topology nên cần bảo vệ tương tự.

**Lưu ý về count:** `entry_count_so_far` chỉ là số đã quan sát trước lỗi. Nó không thể dùng làm `total_users`. Thậm chí một batch đã hoàn thành khi directory đang đổi liên tục cũng không mặc nhiên là một **snapshot có tính nhất quán tuyệt đối**.

## 15. Kiểm thử tích hợp có referral và partial results

Một unit test mock `LdapTemplate` ném `PartialResultException` kiểm tra được mapping ngoại lệ, nhưng **không chứng minh** LDAP provider hoạt động đúng khi referral xen kẽ với search result. Cần **directory test** hoặc test fixture mà bạn chủ động cấu hình referral/continuation reference.

### 15.1. Topology test

```text
LDAP-A (ldaps://ldap-a.test:636)
  base: dc=example,dc=org
  ou=employees
    uid=lan
    uid=binh
  referral/continuation -> LDAP-B

LDAP-B (ldaps://ldap-b.test:636)
  base: dc=partner,dc=org
  ou=people
    uid=mai
```

Các server test phải hỗ trợ tạo referral entry hoặc cấu hình continuation reference phù hợp. Không mặc định embedded LDAP server tự tạo referral khi bạn thêm một entry mang thuộc tính `ref`; cần cấu hình đúng schema và behavior của backend.

Test với từng chế độ:

| Kịch bản | Điều phải xác nhận |
|---|---|
| `ignore`, server hỗ trợ ManageDsaIT | Kết quả có thể chỉ thuộc partition A; không khẳng định đã bao phủ B |
| `ignore`, provider vẫn nhận referral | Có thể xuất hiện `PartialResultException` |
| `throw` | JNDI `ReferralException` xuất hiện tại invocation hoặc enumeration |
| `follow`, B online và đáng tin | Kết quả gồm đúng các nguồn được phép, không chuyển credential tới host ngoài allowlist |
| `follow`, B down hoặc TLS lỗi | Query báo lỗi/incomplete, không trả list rỗng như thành công |
| `ignorePartialResultException=false` | Spring surface exception phù hợp, service chuyển thành lỗi nghiệp vụ |
| `ignorePartialResultException=true` | Spring có thể trả local results; caller không được tự gắn `complete=true` |
| `ignoreSizeLimitExceededException=false` | Lỗi size limit nếu phát sinh không bị nuốt |
| Count limit 2 với 3+ entry | Không tuyên bố toàn directory chỉ có 2 user |
| Referral loop A → B → A | Có giới hạn hop/time và báo lỗi thay vì treo |
| Sai ACL trên B | Không coi user ở B là không tồn tại |
| DN giống nhau ở hai directory | Không dedup nhầm nếu source ID khác |

### 15.2. Kiểm thử service strict

Ví dụ **JUnit 5 + Mockito** (đoạn minh họa logic exception; cần dependency `spring-boot-starter-test` hoặc JUnit/Mockito phù hợp):

```java
package com.example.ldap;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.PartialResultException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.query.LdapQuery;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class DirectorySearchServiceTest {

    @Test
    void partialResultsMustNotLookLikeEmptyList() {
        LdapTemplate template = mock(LdapTemplate.class);

        when(template.search(
                any(LdapQuery.class),
                org.mockito.ArgumentMatchers.<AttributesMapper<String>>any()))
                .thenThrow(new PartialResultException(
                        new javax.naming.PartialResultException(
                                "unresolved referral")));

        DirectorySearchService service = new DirectorySearchService(template);

        assertThrows(DirectoryIncompleteException.class,
                () -> service.findUidsWithinAuthoritativeOu("Nguyen"));
    }
}
```

Test này xác minh service **không biến exception thành danh sách rỗng**. Cần xác nhận signature của constructor runtime wrapper và overload Mockito với dependency thực tế của dự án; nếu phiên bản Mockito không resolve generic matcher, có thể thay bằng test double đơn giản. Nó **không thay** integration test nhiều server với JNDI referral.

### 15.3. Kiểm thử mất dữ liệu sau khi callback có side effect

Thiết kế test:

1. Directory A trả hai entry, tiếp theo continuation reference tới B.
2. Callback xử lý từng entry và ghi vào một staging store riêng.
3. B bị ngắt hoặc từ chối ACL.
4. Search báo lỗi incomplete.
5. Assert staging batch có status `INCOMPLETE`, **chưa publish/commit như snapshot đầy đủ**.
6. Khi B hồi phục, chạy lại hoặc reconcile theo stable identity; không nhân bản dữ liệu đã xử lý.

Trường hợp này cho thấy một function call ném exception **không đồng nghĩa mọi side effect đã được rollback**. LDAP search và database đích thường không nằm trong cùng transaction ACID.

## 16. Câu hỏi tự đánh giá

1. Referral result khác `SearchResultReference` trong một LDAP search như thế nào?
2. Vì sao `ReferralException` có thể xuất hiện khi `NamingEnumeration.hasMore()` được gọi, dù `search()` đã thành công?
3. `Context.REFERRAL="ignore"` có luôn đảm bảo không phát sinh `PartialResultException` không? Vì sao?
4. `follow` khác `throw` về quyền xử lý referral như thế nào?
5. Vì sao không nên để provider tự forward service bind credential tới một referral URL chưa được phê duyệt?
6. `javax.naming.PartialResultException` khác `org.springframework.ldap.PartialResultException` ở điểm nào?
7. Tác động của `LdapTemplate.setIgnorePartialResultException(true)` là gì? Nó có làm kết quả đầy đủ hơn không?
8. Vì sao `ignoreSizeLimitExceededException` cũng ảnh hưởng khả năng phát hiện dữ liệu thiếu?
9. Nếu API tìm user trả list rỗng sau một referral chưa xử lý, có thể kết luận user không tồn tại không?
10. Khi nào autocomplete được phép best effort, nhưng kiểm kê hoặc phân quyền phải fail closed?
11. Đâu là điều kiện để một truy vấn được gọi là complete theo **phạm vi authoritative** của ứng dụng?
12. Vì sao Global Catalog của Active Directory không tự bảo đảm mọi thuộc tính và mọi loại membership đều đã được lấy đầy đủ?
13. Khi job đã ghi các entry từ LDAP A trước khi gặp lỗi với LDAP B, vì sao cần staging/reconciliation?
14. Thiết kế integration test nào chứng minh provider thực sự trả continuation reference và service không báo thành công giả?

**Ghi nhớ:** referral là lời chỉ dẫn sang nguồn LDAP khác; `ReferralException` xuất hiện khi JNDI được cấu hình để ứng dụng tự xử lý, còn `PartialResultException` báo rằng **chưa thể thu đủ kết quả** theo cơ chế provider. `LdapTemplate.setIgnorePartialResultException(true)` chỉ **bỏ qua lỗi**, không theo referral và không bảo đảm completeness. Muốn ra quyết định quan trọng từ dữ liệu LDAP, hãy xác định nguồn authoritative, kiểm soát TLS/credential/referral endpoints, không nuốt size/time limit, phân loại lỗi rõ ràng và chỉ công bố kết quả **COMPLETE** khi tất cả nguồn bắt buộc đã được xác minh.

### Tài liệu tham khảo

- IETF [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511): `SearchResultEntry`, `SearchResultReference`, referral result và SearchResultDone.
- IETF [RFC 4516 — LDAP URL Format](https://www.rfc-editor.org/rfc/rfc4516): cấu trúc LDAP URL dùng trong referral.
- IETF [RFC 3296 — Named Subordinate References in LDAP Directories](https://www.rfc-editor.org/rfc/rfc3296): Manage Referral/ManageDsaIT control.
- Oracle JNDI Tutorial — [Referrals in the JNDI](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/jndi.html): ba mode `ignore`/`follow`/`throw`, continuation references và `PartialResultException`.
- Oracle JNDI Tutorial — [Manually Following Referrals](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/throw.html): xử lý `ReferralException`, `getReferralContext`, vòng enumeration và chuyển credential.
- Spring LDAP API — [`LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `setIgnorePartialResultException`, `setIgnoreSizeLimitExceededException` và search error handling.
- Spring LDAP API — [`AbstractContextSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html): `setReferral` và `setBaseEnvironmentProperties`.
- Spring LDAP Reference — [Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): cấu hình referral và bỏ qua PartialResultException.
- Spring LDAP API — [`PartialResultException`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/PartialResultException.html), [`ReferralException`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/ReferralException.html): runtime exceptions của Spring.
- Oracle Java SE — [`javax.naming.ReferralException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ReferralException.html), [`javax.naming.PartialResultException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/PartialResultException.html).
