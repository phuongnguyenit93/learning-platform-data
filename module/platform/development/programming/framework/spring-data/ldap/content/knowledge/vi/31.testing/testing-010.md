# Kiểm thử phân trang, giới hạn máy chủ và referral

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập directory theo DN (*Distinguished Name*), `objectClass` và schema. Một truy vấn có thể trả về hàng trăm hoặc hàng nghìn entry, trải qua nhiều naming context, hoặc bị giới hạn bởi cấu hình của directory server. Vì vậy, kiểm thử search không chỉ dừng ở việc xác nhận filter trả đúng một vài entry.

Một bài kiểm thử đáng tin cậy cần chứng minh rằng:

- Client nhận đủ các page theo cookie và không lặp/mất entry trong điều kiện dữ liệu ổn định.
- Ứng dụng nhận biết giới hạn số lượng và thời gian của search.
- Kết quả một phần không bị nhầm thành kết quả đầy đủ.
- Referral được theo đúng chính sách hoặc được báo rõ là chưa xử lý.
- Hành vi khác nhau giữa OpenLDAP, Active Directory và các server khác được kiểm tra trên đúng loại directory triển khai.

Sau bài này, bạn có thể thiết kế integration test cho RFC 2696 Paged Results, kiểm tra `sizeLimit`/`timeLimit`/`adminLimitExceeded`, cấu hình referral `ignore`/`follow`/`throw`, và xác minh cách Spring LDAP biểu diễn partial result.

## 1. Chọn đúng tầng kiểm thử

Không phải mọi lỗi phân trang hay referral đều có thể phát hiện bằng unit test. Hãy tách trách nhiệm kiểm thử:

| Tầng | Điều cần kiểm tra | Công cụ phù hợp |
|---|---|---|
| Unit test | Mapper, logic xử lý page, phát hiện UID trùng, trạng thái hoàn tất | JUnit, AssertJ, mock |
| Integration test với LDAP | Search scope/filter, cookie, page size, giới hạn, response controls | `LdapTemplate`, `LdapContextSource`, LDAP test server |
| Topology test | Referral sang server khác, DNS, TLS, credential và naming context | Ít nhất hai LDAP server riêng |
| Compatibility test | Hành vi thật của OpenLDAP/AD, hard limit, referral, paging control | Directory server cùng họ/phiên bản triển khai |
| End-to-end test | API ứng dụng trả trang đầy đủ, trạng thái incomplete và lỗi vận hành | Spring Boot test + directory test environment |

Một embedded LDAP server có thể hữu ích cho CRUD và mapping nhưng không mặc định hỗ trợ đầy đủ RFC 2696, referral hoặc giới hạn quản trị giống production. Nếu tính năng phụ thuộc vào một control hoặc hành vi server cụ thể, hãy kiểm tra khả năng của server test trước khi viết assertion.

## 2. Chuẩn bị fixture đủ lớn và có thể kiểm soát

Hãy dùng dữ liệu có số lượng đã biết, UID duy nhất và DN dễ truy vết. Ví dụ:

```text
dc=example,dc=org
└── ou=people
    ├── uid=user-0001
    ├── uid=user-0002
    ├── uid=user-0003
    ├── ...
    └── uid=user-0237
```

Fixture nên có:

- Ít nhất vài page, ví dụ 237 entry với page size 37.
- Một thuộc tính định danh duy nhất như `uid`.
- Một số entry có `cn` trùng nhau để tránh test phụ thuộc thứ tự không ổn định.
- Một OU riêng cho các test giới hạn và referral.
- Một tập dữ liệu không bị ghi đồng thời trong test pagination cơ bản.

Không dùng dữ liệu production hoặc thông tin định danh thật. Test phải tự tạo và xóa dữ liệu trong naming context dành riêng cho test.

### 2.1. Ghi rõ cấu hình SearchRequest

Khi kiểm tra kết quả, lưu lại các tham số:

| Thành phần | Ví dụ |
|---|---|
| Endpoint | `ldap://localhost:1389` |
| Base DN | `ou=people,dc=example,dc=org` |
| Scope | `SUBTREE` |
| Filter | `(objectClass=inetOrgPerson)` |
| Attributes | `uid`, `cn` |
| Page size | 37 |
| Client count limit | 0 hoặc giá trị được test riêng |
| Client time limit | 0 hoặc giá trị được test riêng |
| Referral policy | `ignore`, `follow` hoặc `throw` |

Giữ nguyên base, scope, filter, requested attributes và controls giữa các page trong cùng một chuỗi. Nếu thay filter hoặc scope giữa chừng, cookie không còn đại diện cho cùng SearchRequest.

## 3. Kiểm thử Paged Results theo RFC 2696

Paged Results control cho phép client yêu cầu server trả một phần kết quả và tiếp tục bằng cookie do server cấp. OID của control là `1.2.840.113556.1.4.319`.

Client gửi page size và cookie ban đầu rỗng. Sau mỗi page, server trả cookie mới. Client phải:

1. Giữ cookie mới nhất từ `SearchResultDone`.
2. Gửi lại cùng SearchRequest, ngoại trừ message ID, cookie và page size có thể thay đổi.
3. Không tự giải mã hoặc sửa cookie.
4. Dừng khi cookie rỗng.
5. Không sử dụng cookie cũ sau khi chuỗi paging hoàn tất.

RFC 2696 cũng cho phép hủy chuỗi paging bằng request có page size bằng 0 và cookie mới nhất. Cookie không phải offset hoặc số trang.

### 3.1. Kiểm tra đủ page và không trùng entry

Với fixture có 237 entry và page size 37, test kỳ vọng:

- Tổng số entry nhận được là 237.
- Mỗi UID xuất hiện đúng một lần khi dữ liệu không thay đổi.
- Có 7 page: 6 page đủ 37 entry và page cuối có 15 entry.
- Cookie kết thúc ở page cuối.

Spring LDAP cung cấp `PagedResultsControlExchangeDirContextProcessor` để tạo request control, nhận response control và quản lý cookie. Cần dùng cùng underlying LDAP connection cho tất cả page. Spring LDAP minh họa việc này bằng `SingleContextSource` hoặc `ContextSourceTransactionManager` cùng `TransactionAwareContextSourceProxy`.

Ví dụ integration test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;

import javax.naming.directory.SearchControls;

import org.springframework.beans.factory.annotation.Autowired;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapOperations;
import org.springframework.ldap.core.support.LdapOperationsCallback;
import org.springframework.ldap.core.support.SingleContextSource;

class PagedSearchIntegrationTest {

    private static final int PAGE_SIZE = 37;
    private static final int EXPECTED_ENTRIES = 237;

    private final ContextSource contextSource;

    @Autowired
    PagedSearchIntegrationTest(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    @Test
    void retrievesEveryEntryAcrossPages() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[]{"uid"});

        List<Integer> pageSizes = new ArrayList<>();

        List<String> allUids = SingleContextSource.doWithSingleContext(
                contextSource,
                (LdapOperationsCallback<List<String>>) operations -> {
                    List<String> result = new ArrayList<>();
                    PagedResultsControlExchangeDirContextProcessor paging =
                            new PagedResultsControlExchangeDirContextProcessor(
                                    PAGE_SIZE);

                    do {
                        List<String> page = operations.search(
                                "ou=people",
                                "(objectClass=inetOrgPerson)",
                                controls,
                                attrs -> (String) attrs.get("uid").get(),
                                paging);

                        pageSizes.add(page.size());
                        result.addAll(page);
                    } while (paging.hasMore());

                    return result;
                });

        assertThat(allUids).hasSize(EXPECTED_ENTRIES);
        assertThat(allUids).doesNotHaveDuplicates();
        assertThat(pageSizes).containsExactly(37, 37, 37, 37, 37, 37, 15);
    }
}
```

Test này kiểm tra hành vi paging end-to-end với directory server. Nó không phải unit test cho cookie: processor thật gửi control và đọc response control từ `LdapContext`.

Ví dụ giả định Spring TestContext đã được kích hoạt (chẳng hạn qua `@SpringJUnitConfig`) và có bean `ContextSource` cho directory test. Test fixture phải cấu hình server không áp dụng page cap nhỏ hơn 37.

Nếu server trả page cuối nhỏ hơn dự kiến nhưng tổng số entry vẫn đúng, hãy kiểm tra page size, server policy và việc có thay đổi dữ liệu trong lúc test. Đừng khẳng định server luôn phải trả page cuối có đúng số phần tử cụ thể nếu fixture hoặc policy có thể thay đổi.

### 3.2. Xác nhận cùng một kết nối được sử dụng

Paged Results cookie có thể gắn với trạng thái search trên server. Spring LDAP yêu cầu dùng cùng underlying connection cho các request tiếp theo. Nếu mỗi page lấy một context mới, test có thể thất bại với cookie không hợp lệ hoặc trả kết quả sai.

Trong test, hãy đặt toàn bộ vòng lặp `do/while` bên trong một callback `SingleContextSource.doWithSingleContext(...)`. Không tạo `SingleContextSource` mới cho từng page.

Nếu dùng transaction-aware context, xác nhận `ContextSourceTransactionManager` và `TransactionAwareContextSourceProxy` đang trỏ đến đúng `ContextSource` mà `LdapTemplate` sử dụng.

### 3.3. Kiểm tra page size không phải hard size limit

Page size là số entry client muốn nhận trong một lần trả kết quả. Nó không thay thế `SearchRequest.sizeLimit` và cũng không xóa giới hạn do server quản trị.

RFC 2696 nêu rằng page size có thể nhỏ hơn `sizeLimit` trong SearchRequest. Nếu page size lớn hơn hoặc bằng `sizeLimit`, server nên bỏ qua paging control vì request có thể được thỏa mãn trong một page.

Vì vậy:

- Với test paging cơ bản, đặt count limit bằng 0 (không giới hạn phía client).
- Chọn page size nhỏ hơn hard size limit của test server.
- Test count limit riêng, không trộn hai biến trong cùng một assertion.
- Xác minh server thực sự trả Paged Results response control.

Không suy ra paging đã hoạt động chỉ vì client nhận được một list có số phần tử nhỏ.

### 3.4. Cookie và dữ liệu thay đổi giữa các page

RFC 2696 không cung cấp snapshot transaction. Nếu tập kết quả thay đổi sau request đầu tiên, client có thể nhận một entry nhiều lần hoặc bỏ lỡ entry phù hợp với filter.

Hãy tách hai test:

- **Stable fixture test:** không ghi dữ liệu trong khi paging; yêu cầu đủ và không trùng UID.
- **Concurrent mutation test:** thêm, xóa hoặc sửa một entry giữa các page; ghi nhận hành vi thực tế của directory, không khẳng định kết quả luôn là snapshot.

Test concurrent mutation nên mô tả tính chất eventual/operational của directory. Nếu nghiệp vụ yêu cầu snapshot nhất quán, cần cơ chế snapshot/export khác phù hợp với server.

## 4. Kiểm thử client limit và server limit

LDAP Search có hai giới hạn do client yêu cầu và server áp dụng:

- `sizeLimit`: số entry tối đa server được yêu cầu trả về cho Search.
- `timeLimit`: thời gian tối đa server được yêu cầu dành cho Search.

Giá trị 0 trong SearchRequest nghĩa là client không yêu cầu giới hạn tương ứng. Server vẫn có thể áp dụng hard limit của chính nó.

Ngoài ra, server có thể áp dụng giới hạn quản trị phức tạp hơn và trả `adminLimitExceeded (11)`.

### 4.1. Các result code cần nhận biết

| LDAP result code | Ý nghĩa | Điều cần xác minh |
|---|---|---|
| `success (0)` | Search hoàn tất thành công | Đã lấy đủ page/cookie chưa? |
| `timeLimitExceeded (3)` | Vượt giới hạn thời gian | SearchRequest time limit hay hard time limit của server? |
| `sizeLimitExceeded (4)` | Vượt giới hạn số entry | Client count limit hay server size limit? |
| `referral (10)` | Cần tiếp tục ở server khác | Client có follow referral không? |
| `adminLimitExceeded (11)` | Vượt giới hạn quản trị | Server giới hạn subtree, filter, page hoặc tài nguyên nào? |
| `unavailableCriticalExtension (12)` | Server không hỗ trợ control critical | Control paging có được hỗ trợ không? |

`timeLimitExceeded` và `sizeLimitExceeded` là kết quả Search chưa hoàn tất. Một server hoặc provider có thể đã chuyển một số entry trước khi báo lỗi. Vì vậy, không được coi phần dữ liệu đã nhận là toàn bộ kết quả.

### 4.2. Đặt count limit và time limit trong SearchControls

`SearchControls.setCountLimit(long)` đặt số entry tối đa phía client yêu cầu. `setTimeLimit(int)` nhận thời gian theo milliseconds ở JNDI `SearchControls`.

Ví dụ:

```java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[]{"uid", "cn"});
controls.setCountLimit(50);
controls.setTimeLimit(2_000);
```

Hai giá trị trên là giới hạn của request. Chúng không buộc server phải trả đủ 50 entry và không thể nâng hard limit của server. `timeLimit` cũng không phải timeout end-to-end của HTTP request; tầng ứng dụng vẫn cần timeout riêng cho toàn bộ workflow.

### 4.3. Spring LDAP có thể bỏ qua SizeLimitExceededException

`LdapTemplate` hiện hành có các default đáng chú ý:

| Property | Default | Hành vi |
|---|---:|---|
| `ignoreNameNotFoundException` | `false` | Base DN không tồn tại được giữ như lỗi |
| `ignorePartialResultException` | `false` | Partial result được giữ như lỗi |
| `ignoreSizeLimitExceededException` | `true` | `SizeLimitExceededException` được bỏ qua và phần kết quả đã nhận có thể được trả về |
| `defaultCountLimit` | `0` | Không đặt count limit mặc định |
| `defaultTimeLimit` | `0` | Không đặt time limit mặc định |

Khi test tính đầy đủ, nên cấu hình rõ `ignoreSizeLimitExceededException(false)` để không âm thầm biến một search bị giới hạn thành một list có vẻ hoàn chỉnh.

```java
import org.springframework.ldap.core.LdapTemplate;

LdapTemplate strictTemplate = new LdapTemplate(contextSource);
strictTemplate.setIgnoreNameNotFoundException(false);
strictTemplate.setIgnorePartialResultException(false);
strictTemplate.setIgnoreSizeLimitExceededException(false);
```

Trong một test riêng, có thể đặt `ignoreSizeLimitExceededException(true)` để kiểm tra ứng dụng có đánh dấu kết quả là partial hay không. Nếu API trả một list partial mà không kèm trạng thái incomplete, tầng gọi rất dễ dùng dữ liệu thiếu như dữ liệu đầy đủ.

### 4.4. Test size limit theo hai chế độ

Giả sử fixture có 20 entry và test đặt count limit là 5:

Đoạn test giả định Spring TestContext đã được kích hoạt (qua `SpringJUnitConfig`/`SpringExtension`) và cung cấp bean `ContextSource` cho directory test.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import javax.naming.directory.SearchControls;

import org.springframework.beans.factory.annotation.Autowired;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.SizeLimitExceededException;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;

class SearchLimitIntegrationTest {

    private final ContextSource contextSource;

    @Autowired
    SearchLimitIntegrationTest(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    @Test
    void strictModeReportsSizeLimit() {
        LdapTemplate template = new LdapTemplate(contextSource);
        template.setIgnoreSizeLimitExceededException(false);

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setCountLimit(5);

        assertThatThrownBy(() -> template.search(
                "ou=people",
                "(objectClass=inetOrgPerson)",
                controls,
                attrs -> attrs.get("uid").get()))
                .isInstanceOf(SizeLimitExceededException.class);
    }

    @Test
    void lenientModeMustBeTreatedAsPartial() {
        LdapTemplate template = new LdapTemplate(contextSource);
        template.setIgnoreSizeLimitExceededException(true);

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setCountLimit(5);

        var returned = template.search(
                "ou=people",
                "(objectClass=inetOrgPerson)",
                controls,
                attrs -> attrs.get("uid").get());

        assertThat(returned).hasSizeLessThanOrEqualTo(5);
        // Test/service phải gắn trạng thái PARTIAL hoặc LIMIT_REACHED.
    }
}
```

Kết quả chính xác phụ thuộc provider và server. Test phải chạy với server được cấu hình để có nhiều hơn 5 entry phù hợp; nếu fixture chỉ có 5 entry thì không có lý do để vượt limit.

`ignoreSizeLimitExceededException(true)` chỉ thay đổi cách Spring LDAP xử lý exception. Nó không làm server trả thêm dữ liệu và không biến kết quả thành đầy đủ.

### 4.5. Test time limit và admin limit

Không dùng `Thread.sleep()` trong test để cố tạo timeout. Kết quả sẽ phụ thuộc tải máy, scheduler và tốc độ directory.

Để kiểm tra `timeLimitExceeded (3)`:

1. Dùng một directory test có thể cấu hình giới hạn thời gian Search.
2. Tạo dataset đủ lớn hoặc filter có chi phí đã biết trong fixture.
3. Đặt time limit ở server/test profile có thể tái lập.
4. Gửi SearchRequest với `SearchControls.setTimeLimit(...)`.
5. Xác minh client nhận timeout/partial-result behavior đúng với provider.

Để kiểm tra `adminLimitExceeded (11)`, cấu hình hard administrative limit của directory test rồi chạy Search vượt ngưỡng. Không giả định mọi server dùng cùng một ngưỡng hoặc cùng một result code cho mọi loại giới hạn.

Trong Spring LDAP, `defaultTimeLimit` và `defaultCountLimit` có thể đặt cho `LdapTemplate`; giá trị mặc định của cả hai là 0. XML configuration hiện hành mô tả `time-limit` theo milliseconds và `count-limit` bằng 0 là không giới hạn.

### 4.6. Không dùng một list partial làm bằng chứng paging thành công

Paged Results và size limit là hai cơ chế khác nhau:

- Page size kiểm soát số entry trong mỗi response page.
- Count/size limit giới hạn tổng số entry Search được phép trả theo request/server policy.
- Time limit giới hạn thời gian xử lý Search.
- Administrative limit có thể từ chối search do chính sách tài nguyên.

Nếu page 1 thành công nhưng page tiếp theo bị `sizeLimitExceeded`, `timeLimitExceeded` hoặc `adminLimitExceeded`, chuỗi paging chưa hoàn tất. API nên trả trạng thái lỗi/incomplete rõ ràng thay vì trả list đã gom và coi như thành công.

## 5. Kiểm thử referral và continuation reference

Referral xuất hiện khi server được hỏi không thể hoặc không muốn xử lý toàn bộ operation và chỉ ra server khác có thể tiếp tục.

Trong LDAP Search, referral có hai dạng cần phân biệt:

- **Referral result:** `SearchResultDone` có result code `referral (10)`, thường khi server không tìm thấy base cục bộ nhưng biết nơi khác có thể xử lý.
- **SearchResultReference:** continuation reference có thể xuất hiện xen kẽ với `SearchResultEntry` khi server tìm thấy base nhưng cần hỏi server khác để hoàn tất subtree search.

Vì vậy, một Search có thể đã trả một số entry rồi mới gặp referral. Test chỉ kiểm tra số entry đầu tiên có thể bỏ sót phần dữ liệu nằm ở naming context khác.

### 5.1. JNDI có ba chính sách referral

`Context.REFERRAL` hỗ trợ:

| Giá trị | Hành vi |
|---|---|
| `ignore` | Bỏ qua referral |
| `follow` | Tự động theo referral |
| `throw` | Ném `ReferralException` để caller xử lý |

Nếu không cấu hình, JNDI mặc định là `ignore`. Spring LDAP cho phép cấu hình referral qua `AbstractContextSource.setReferral(...)` hoặc thuộc tính `referral` trên context source. Ở chế độ ignore, provider thường yêu cầu server trả referral như entry thường qua Manage Referral control; nếu server không hỗ trợ cơ chế đó và vẫn gửi referral, JNDI có thể ném `PartialResultException`.

```java
LdapContextSource contextSource = new LdapContextSource();
contextSource.setUrl("ldap://directory-a.test:1389");
contextSource.setBase("dc=example,dc=org");
contextSource.setUserDn("cn=app-reader,ou=service,dc=example,dc=org");
contextSource.setPassword(System.getenv("LDAP_TEST_PASSWORD"));
contextSource.setReferral("follow");
contextSource.afterPropertiesSet();
```

Ví dụ dùng `follow` cho topology test. Referral target phải truy cập được qua DNS/network, phải có TLS trust phù hợp nếu dùng LDAPS/StartTLS và phải chấp nhận danh tính xác thực của client.

### 5.2. Thiết kế topology có ít nhất hai server

Để kiểm thử referral thực tế, chuẩn bị:

```text
Directory A: ldap://directory-a.test:1389
  dc=example,dc=org
  ├── ou=people
  │   └── uid=local-user
  └── ou=remote
      └── referral -> Directory B

Directory B: ldap://directory-b.test:2389
  dc=remote,dc=example,dc=org
  ├── uid=remote-001
  └── uid=remote-002
```

Search từ Directory A với scope `SUBTREE` phải có thể gặp:

- Entry local trong `ou=people`.
- Referral/continuation reference trỏ sang Directory B.
- Entry remote nếu referral được follow thành công.

Fixture phải tạo dữ liệu remote độc lập để assertion biết chính xác entry nào đến từ server nào. Test topology nên dùng cùng họ directory hoặc server thực tế mà production đang chạy.

### 5.3. Test follow referral

Với `referral=follow`, test xác minh:

1. Search trên Directory A nhận được entry local.
2. Client theo referral đến Directory B.
3. Entry remote xuất hiện trong kết quả nếu Bind identity có quyền và endpoint truy cập được.
4. Không lặp referral vô hạn giữa hai server.
5. TLS/credential của referral target được xử lý theo chính sách triển khai.

Không chỉ assert tổng số entry. Hãy kiểm tra tập UID hoặc DN kỳ vọng để phát hiện trường hợp local entries có nhưng remote entries bị thiếu.

### 5.4. Test ignore referral

Với `referral=ignore`, client không tiếp tục tìm ở server được referral chỉ ra. Kết quả có thể thiếu entry remote dù Search ở server ban đầu không ném exception.

Test cần xác nhận ứng dụng biểu diễn đây là kết quả theo phạm vi server đã truy cập, hoặc đánh dấu kết quả chưa đầy đủ nếu nghiệp vụ yêu cầu toàn bộ naming context.

Không dùng `ignore` làm cấu hình mặc định cho một API được quảng bá là tìm toàn bộ directory phân tán nếu ứng dụng không có cơ chế thông báo dữ liệu remote bị bỏ qua.

### 5.5. Test throw referral

Với `referral=throw`, JNDI có thể trả các entry local trong enumeration trước khi ném `ReferralException` khi gặp continuation reference. Khi Spring LDAP dịch lỗi qua `LdapTemplate`, exception có thể được bọc trong hierarchy của Spring LDAP; hãy kiểm tra root cause và provider đang dùng.

Test nên dùng một request riêng để xác minh:

- Có entry local trước khi referral được phát hiện.
- Caller nhận được exception/partial-result indication theo provider.
- Ứng dụng không trả list local như thể Search đã hoàn tất.

Không giả định mọi provider đều ném cùng một lớp exception hoặc ném ở cùng thời điểm. Dùng integration test trên JNDI provider thực tế trong runtime.

## 6. PartialResultException và hành vi riêng của Spring LDAP

Spring LDAP `LdapTemplate` hiện hành có `ignorePartialResultException` mặc định là `false`. Khi directory/provider không theo referral thành công và ném `PartialResultException`, `LdapTemplate` sẽ giữ lỗi này.

Một số Active Directory server không xử lý referral tự động như JNDI mong đợi. Spring LDAP ghi nhận trường hợp này có thể làm phát sinh `PartialResultException`.

Có thể đặt:

```java
LdapTemplate ldapTemplate = new LdapTemplate(contextSource);
ldapTemplate.setIgnorePartialResultException(true);
```

Đây là workaround để search tiếp tục trả về kết quả đã nhận khi provider ném `PartialResultException`. Tuy nhiên, tài liệu Spring LDAP cảnh báo khi bật cờ này, các referral đều bị bỏ qua và không có thông báo trực tiếp rằng exception đã xảy ra (ngoài log). `LdapTemplate` hiện không cung cấp cơ chế thủ công đơn giản để nhận từng `ReferralException` và tự điều phối referral.

Vì vậy, test cần hai cấu hình:

| Cấu hình | Điều cần xác nhận |
|---|---|
| `ignorePartialResultException=false` | Partial result được báo lỗi; caller không coi search là hoàn chỉnh |
| `ignorePartialResultException=true` | Method có thể trả phần kết quả đã nhận; telemetry/log phải cho biết referral bị bỏ qua |

Không bật cờ ignore chỉ để làm test pass. Nếu nghiệp vụ cần kết quả từ mọi naming context, phải kiểm tra `follow` và topology thực tế; bỏ qua partial result sẽ làm mất dữ liệu remote.

### 6.1. Test referral bị hỏng hoặc không truy cập được

Tạo referral trỏ tới host/port không tồn tại trong directory test. Với `follow`, test phải xác minh lỗi kết nối hoặc partial result được báo rõ; không biến thành thành công giả.

Tạo thêm trường hợp:

- Referral URL không phân giải DNS.
- Referral target từ chối Bind.
- TLS certificate của target không được trust.
- Referral trỏ vòng lặp A → B → A.
- Referral target không chứa base DN được chỉ ra.

Các trường hợp này giúp kiểm tra hành vi thực tế của provider, nhưng nên chạy trong test profile riêng để không phụ thuộc mạng bên ngoài.

### 6.2. Kiểm tra bảo mật khi follow referral

Referral URL có thể chứa hostname, port, DN hoặc thông tin định tuyến nhạy cảm. Không log toàn bộ URL và credential. Hãy:

- Chỉ follow referral đến domain/endpoint được tổ chức cho phép.
- Xác minh TLS certificate của mỗi target.
- Kiểm tra Bind identity và quyền trên từng server.
- Không giả định service account có cùng quyền trên tất cả naming context.
- Không để referral do dữ liệu không tin cậy điều khiển client kết nối tùy ý.

## 7. Kết hợp paging và referral trong test

Đây là tổ hợp dễ phát hiện lỗi nhất vì paging cookie, continuation reference và underlying connection có thể tương tác.

Một số điểm cần kiểm tra:

- Paging control được gửi cho từng SearchRequest thuộc chuỗi page.
- Cookie mới nhất được gửi tiếp theo đúng RFC 2696.
- Referral target có hỗ trợ paged-results control tương ứng hay không.
- Cùng kết nối được giữ cho chuỗi page theo yêu cầu Spring LDAP.
- Client có theo continuation reference trước khi đánh dấu Search hoàn tất hay không.
- Kết quả không bị lặp khi server trả local entries và remote entries ở các nhánh khác nhau.

Không giả định cookie từ server A có thể được dùng để tiếp tục Search trên server B. Cookie là opaque và thuộc trạng thái do server cấp; khi referral được theo, JNDI provider có thể quản lý continuation riêng. Hãy test trên đúng provider/server combination.

Ma trận integration test tối thiểu:

| Paging | Referral | Kết quả cần xác minh |
|---|---|---|
| Tắt | `ignore` | Chỉ entry nhìn thấy ở server ban đầu |
| Tắt | `follow` | Local và remote entries theo topology |
| Tắt | `throw` | Partial entries và referral exception |
| Bật | `ignore` | Cookie/page hoạt động trên server ban đầu; remote có thể bị thiếu |
| Bật | `follow` | Không mất/nhân đôi entry qua các page và referral |
| Bật | `throw` | Chuỗi paging kết thúc với trạng thái partial/error rõ ràng |

Nếu server hoặc provider không hỗ trợ kết hợp hai tính năng, test phải ghi rõ giới hạn tương thích thay vì bỏ qua lỗi.

## 8. Một bộ test case nên có trước khi phát hành

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| PAG-01 | Fixture nhỏ hơn một page | Một page, cookie kết thúc |
| PAG-02 | Fixture bằng đúng page size | Không tạo page rỗng ngoài dự kiến |
| PAG-03 | Fixture lớn hơn nhiều page | Nhận đủ entry, không trùng UID |
| PAG-04 | Cookie được tiếp tục trên cùng context | Search tiếp tục đúng |
| PAG-05 | Mở context mới cho cookie cũ | Test phát hiện lỗi/không hỗ trợ tiếp tục |
| PAG-06 | Cookie rỗng ở page cuối | Dừng vòng lặp |
| PAG-07 | SearchRequest thay đổi filter giữa page | Không tiếp tục chuỗi cũ |
| PAG-08 | Dataset thay đổi giữa page | Ghi nhận khả năng duplicate/missing theo RFC 2696 |
| LIM-01 | Count limit thấp hơn số entry match | Nhận size limit/partial behavior |
| LIM-02 | Ignore size limit bật | List partial được đánh dấu incomplete |
| LIM-03 | Ignore size limit tắt | Lỗi được truyền lên |
| LIM-04 | Server hard size limit thấp | Client không vượt được giới hạn server |
| LIM-05 | Time limit của server bị vượt | Nhận timeout/partial behavior |
| LIM-06 | Admin limit bị vượt | Lỗi quản trị được quan sát và phân loại |
| REF-01 | Referral ignore | Remote entries không được trả |
| REF-02 | Referral follow | Remote entries được trả nếu Bind/TLS hợp lệ |
| REF-03 | Referral throw | Caller nhận referral/partial exception |
| REF-04 | Referral target unreachable | Lỗi kết nối được báo |
| REF-05 | Referral target từ chối Bind | Lỗi xác thực được báo |
| REF-06 | Referral loop | Client không lặp vô hạn |
| REF-07 | AD PartialResultException | Hành vi ignore flag được xác minh |
| MIX-01 | Paging + follow referral | Kiểm tra đủ entry và không trùng |
| MIX-02 | Paging + referral bị lỗi | Không trả kết quả partial như hoàn chỉnh |

## 9. Cách ghi nhận kết quả test và quan sát production

Khi search có thể bị giới hạn hoặc có referral, log/metric cần phân biệt:

- Số page đã nhận.
- Số entry mỗi page và tổng số entry.
- Có cookie tiếp tục hay đã kết thúc.
- Search result code.
- `SizeLimitExceededException`, `TimeLimitExceededException`, `PartialResultException` hoặc lỗi referral.
- Referral policy đang dùng.
- Server/endpoint đã được hỏi và target được follow (dùng mã định danh đã che thông tin nhạy cảm).
- Search có hoàn tất đầy đủ hay chỉ trả một phần.

Không log password, bind token, toàn bộ DN hoặc referral URL có thể tiết lộ cấu trúc nội bộ. Dùng request ID, mã principal đã pseudonymize và tên môi trường để đối chiếu.

Một API service có thể biểu diễn kết quả theo trạng thái:

```java
enum SearchCompletion {
    COMPLETE,
    PARTIAL_LIMIT,
    PARTIAL_REFERRAL,
    FAILED
}

record DirectorySearchResult<T>(
        List<T> entries,
        SearchCompletion completion,
        int pagesRead) {}
```

Kiểu dữ liệu này nhắc tầng gọi rằng `entries` không nhất thiết là toàn bộ dữ liệu. Không chuyển `PARTIAL_LIMIT` hoặc `PARTIAL_REFERRAL` thành HTTP success giống `COMPLETE` nếu nghiệp vụ cần đầy đủ kết quả.

## 10. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách xử lý |
|---|---|---|
| Test chỉ kiểm tra page đầu | Không phát hiện cookie sai hoặc mất page | Duyệt đến cookie rỗng |
| Dùng fixture nhỏ hơn page size | Không test continuation | Tạo nhiều page |
| Mỗi page tạo connection mới | Cookie có thể không hợp lệ | Dùng `SingleContextSource` |
| Coi page size là server size limit | Test sai semantics | Kiểm tra hai limit riêng |
| Bật `ignoreSizeLimitExceededException` rồi coi list là đầy đủ | Dữ liệu thiếu âm thầm | Đánh dấu partial hoặc fail |
| Bật `ignorePartialResultException` để né referral lỗi | Mất remote entries mà không rõ | Test follow và topology |
| Dùng một embedded server để kết luận AD/OpenLDAP giống nhau | Bỏ sót khác biệt sản phẩm | Compatibility test theo server |
| Dùng `Thread.sleep()` để tạo time limit | Test chập chờn | Cấu hình server limit tái lập |
| Không test referral target | Không phát hiện lỗi DNS/TLS/Bind | Dùng topology hai server |
| Chỉ assert tổng số entry | Có thể có UID trùng và UID thiếu | Assert tập UID/DN duy nhất |
| Dùng cookie cũ sau khi hoàn tất | Hành vi không xác định | Chỉ dùng cookie mới nhất trong chuỗi đang mở |
| Follow referral tùy ý | Nguy cơ kết nối ngoài phạm vi tin cậy | Allowlist target và xác minh TLS |

## 11. Câu hỏi tự đánh giá

1. Vì sao cần giữ cùng underlying connection trong chuỗi Paged Results của Spring LDAP?
2. Cookie RFC 2696 có phải offset hoặc page number không?
3. Khi nào cookie được xem là hết hiệu lực?
4. Vì sao page size không thay thế `sizeLimit` của SearchRequest?
5. LDAP phân biệt `sizeLimitExceeded`, `timeLimitExceeded` và `adminLimitExceeded` như thế nào?
6. Vì sao `ignoreSizeLimitExceededException=true` có thể làm ứng dụng trả một list partial?
7. `SearchControls.setTimeLimit()` nhận đơn vị nào?
8. Referral result và `SearchResultReference` khác nhau ở đâu?
9. JNDI `ignore`, `follow`, `throw` có hành vi gì?
10. Vì sao `ignorePartialResultException=true` có thể làm mất entry từ referral?
11. Vì sao Active Directory có thể phát sinh `PartialResultException` khi theo referral?
12. Làm sao kiểm thử paging và referral đồng thời?
13. Vì sao integration test cần ít nhất hai LDAP server để kiểm tra referral thực tế?
14. Những thông tin nào nên ghi log khi search không hoàn tất?

**Ghi nhớ:** test phân trang phải duyệt hết cookie, giữ cùng kết nối và kiểm tra đủ/không trùng entry. Test giới hạn phải phân biệt page size, client `sizeLimit`/`timeLimit` và hard limit của server. Test referral phải kiểm tra `ignore`/`follow`/`throw`, partial results và topology thật. Nếu Spring LDAP được cấu hình bỏ qua `SizeLimitExceededException` hoặc `PartialResultException`, ứng dụng phải có cách nhận biết kết quả chỉ là một phần.

### Tài liệu tham khảo

- IETF [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696): page size, cookie opaque, request tiếp theo, kết thúc và hủy chuỗi paging.
- IETF [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest size/time limit, result codes, referral và SearchResultReference.
- Spring LDAP Reference — [Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): `DirContextProcessor`, `PagedResultsControlExchangeDirContextProcessor`, cookie và `SingleContextSource`.
- Spring LDAP Reference — [Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource` referral strategy, `LdapTemplate` count/time limit và các cờ ignore exception.
- Spring LDAP API — [LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): default và cách xử lý `SizeLimitExceededException`, `PartialResultException`, `NameNotFoundException`.
- Oracle JNDI Tutorial — [Referrals in the JNDI](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/jndi.html): `Context.REFERRAL` với `ignore`, `follow`, `throw`, continuation reference và `PartialResultException`.
