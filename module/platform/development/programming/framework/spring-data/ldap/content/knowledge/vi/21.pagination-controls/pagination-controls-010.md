# Đóng tài nguyên và xử lý dừng sớm giữa quá trình phân trang

## 1. Dừng đọc kết quả không chỉ là thoát khỏi vòng lặp

Giả sử ứng dụng cần đồng bộ 50.000 user từ LDAP. Thay vì yêu cầu server trả toàn bộ kết quả trong một lần, ứng dụng dùng paged results, mỗi trang 500 entry:

```text
Search page 1 -> 500 entries + cookie A
Search page 2 -> 500 entries + cookie B
Search page 3 -> 500 entries + cookie C
...
Search page N -> final entries + empty cookie
```

Trong lúc xử lý trang thứ ba, người dùng có thể hủy tác vụ, deadline có thể hết hoặc service có thể đạt giới hạn số lượng cần xử lý. Khi đó ứng dụng phải giải quyết hai việc:

1. **Đóng tài nguyên phía client:** đóng NamingEnumeration, DirContext/LdapContext, stream và các wrapper đang giữ kết nối.
2. **Kết thúc paged search phía server:** nếu đã nhận cookie của trang trước, gửi yêu cầu hủy chuỗi paging theo RFC 2696 khi có thể.

Hai việc này liên quan nhưng không giống nhau. Đóng enumeration và context giải phóng tài nguyên client; nó không tự động chứng minh server đã nhận yêu cầu kết thúc paged-results cursor.

Trong module **SPRING_DATA_LDAP**, Spring LDAP LdapTemplate giúp quản lý context và enumeration cho từng operation. Tuy nhiên, paged results có cookie gắn với chuỗi SearchRequest và thường yêu cầu giữ cùng kết nối giữa các trang. Vì vậy, vòng đời của connection, cookie và điểm dừng phải được thiết kế cùng nhau.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt đóng tài nguyên JNDI với hủy paged-results sequence.
2. Mô tả vòng đời cookie của RFC 2696.
3. Giải thích vì sao các trang của cùng một sequence cần dùng cùng LDAP connection.
4. Dùng SingleContextSource.doWithSingleContext để giữ connection trong vòng lặp paging.
5. Hiểu LdapTemplate tự đóng NamingEnumeration và context sau mỗi lần search.
6. Xử lý dừng sau một trang hoàn chỉnh và gửi page-size-zero cancellation.
7. Phân biệt dừng giữa trang với dừng khi server vẫn đang gửi trang hiện tại.
8. Dùng try-with-resources cho stream hoặc JNDI resource tự quản lý.
9. Viết integration test cho hoàn tất bình thường, dừng sớm, exception và cleanup.

## 2. Ba vòng đời cần quản lý

Một paged search có ba vòng đời riêng:

| Thành phần | Được tạo khi nào? | Kết thúc khi nào? | Ai chịu trách nhiệm? |
| --- | --- | --- | --- |
| NamingEnumeration<SearchResult> | Một SearchRequest trả về kết quả. | Đã duyệt hết hoặc client đóng enumeration. | LdapTemplate nếu dùng API template; ứng dụng nếu gọi JNDI trực tiếp. |
| DirContext/LdapContext | Lấy context từ ContextSource hoặc tạo JNDI context. | Context được đóng hoặc wrapper trả connection về pool. | LdapTemplate, SingleContextSource hoặc ứng dụng tùy cách mở. |
| Paged-results sequence/cookie | Server nhận SearchRequest có paged-results control. | Cookie rỗng ở trang cuối hoặc client gửi cancellation với page size 0 và cookie cuối. | Client phải theo dõi cookie và kết thúc sequence khi dừng sớm. |

Hình dung:

```text
Paged search sequence
    |
    +-- Page 1
    |     +-- NamingEnumeration #1 (close sau trang)
    |     +-- cookie A
    |
    +-- Page 2
    |     +-- NamingEnumeration #2 (close sau trang)
    |     +-- cookie B
    |
    +-- Page 3
          +-- NamingEnumeration #3 (close sau trang)
          +-- cookie C
                    |
                    +-- Continue: gửi trang tiếp theo với cookie C
                    |
                    +-- Stop: gửi pageSize=0 với cookie C
```

Mỗi trang có enumeration riêng. Cookie là trạng thái của chuỗi paging, không phải handle của enumeration và cũng không phải đối tượng context.

### 2.1. Đóng enumeration không đồng nghĩa xóa cookie

NamingEnumeration.close() kết thúc việc đọc kết quả của một search hiện tại. Cookie của RFC 2696 được server trả trong response control để client yêu cầu trang tiếp theo hoặc hủy sequence.

Do đó:

- Đóng enumeration sau khi đã đọc hết một trang là bình thường; cookie vẫn được dùng để lấy trang kế tiếp.
- Đóng context sau khi kết thúc toàn bộ callback sẽ giải phóng connection phía client.
- Nếu dừng sau một trang và còn cookie, có thể gửi một SearchRequest với page size bằng 0 để thông báo server kết thúc sequence.

Không giữ enumeration mở qua nhiều trang. Cũng không giữ một context vô thời hạn chỉ vì cookie còn tồn tại.

## 3. LdapTemplate quản lý tài nguyên nào?

LdapTemplate được thiết kế để giảm lỗi thường gặp khi dùng JNDI: lấy context, duyệt NamingEnumeration, chuyển exception và đóng tài nguyên.

Trong luồng search, Spring LDAP thực hiện các bước:

1. Lấy read-only DirContext từ ContextSource.
2. Gọi DirContextProcessor.preProcess nếu có.
3. Gửi SearchRequest và nhận NamingEnumeration.
4. Duyệt kết quả, chuyển từng entry qua callback/mapper.
5. Gọi DirContextProcessor.postProcess để đọc response controls.
6. Đóng enumeration và context trong khối finally.

Điều này áp dụng cả khi search hoặc callback ném exception: phần cleanup trong finally vẫn được thực hiện.

### 3.1. API mapper trả List

Ví dụ:

```java
List<Person> page = ldapTemplate.search(
    base,
    filter,
    searchControls,
    personMapper,
    processor
);
```

LdapTemplate duyệt và map các entry của trang hiện tại, thu thập thành List, gọi postProcess, rồi đóng enumeration/context trước khi trả về. Với page size vừa phải, cách này thuận tiện để xử lý xong một trang rồi mới quyết định có lấy trang tiếp theo không.

Ưu điểm cho early stop:

- Cookie của trang hiện tại đã được lấy qua postProcess.
- Enumeration của trang đã được duyệt hết và đóng.
- Ứng dụng có thể xử lý một phần List trong bộ nhớ.
- Nếu dừng, ứng dụng có thể gửi cancellation bằng cookie mới nhất trước khi rời vùng giữ connection.

Giới hạn là mỗi trang được materialize thành List; chọn page size để cân bằng bộ nhớ và số lần round-trip.

### 3.2. API callback

LdapTemplate.search(..., NameClassPairCallbackHandler) xử lý từng kết quả bằng callback, không cần giữ toàn bộ page trong một List:

```java
ldapTemplate.search(
    base,
    filter,
    searchControls,
    callbackHandler,
    processor
);
```

LdapTemplate vẫn chịu trách nhiệm đóng enumeration/context khi operation kết thúc. Tuy nhiên, callback không có giá trị trả về kiểu false để yêu cầu dừng enumeration một cách bình thường.

Nếu callback ném exception để thoát giữa trang:

- Search hiện tại bị kết thúc sớm.
- LdapTemplate vẫn chạy cleanup trong finally.
- Enumeration có thể bị đóng khi chưa đọc hết response.
- postProcess có thể không nhận được response control hoàn chỉnh/cookie mới của trang đó.

Vì vậy, khi cần hủy paged sequence có kiểm soát, ưu tiên dừng **sau khi một trang hoàn chỉnh đã được đọc**, thay vì ném exception giữa enumeration.

### 3.3. Gọi JNDI trực tiếp

Nếu tự gọi DirContext.search, ứng dụng phải đóng enumeration và context:

```java
NamingEnumeration<SearchResult> results = null;
try {
    results = ldapContext.search(base, filter, searchControls);
    while (results.hasMore()) {
        SearchResult result = results.next();
        // Xử lý entry.
    }
} finally {
    if (results != null) {
        results.close();
    }
    ldapContext.close();
}
```

Không đóng context trong mỗi lần lấy trang nếu cookie cần dùng trên cùng connection. Trong paged loop, context phải sống qua tất cả page request và chỉ đóng sau khi sequence hoàn tất hoặc đã gửi cancellation.

## 4. Cookie của RFC 2696

Paged results control có OID:

```text
1.2.840.113556.1.4.319
```

Control mang hai trường:

- size: số entry client muốn nhận ở trang kế tiếp; response có thể dùng trường này làm ước lượng tổng số entry.
- cookie: opaque octet string do server cấp để tiếp tục hoặc hủy chuỗi paging.

Client không được phân tích nội dung cookie hoặc tự tạo cookie. Cookie chỉ được dùng lại theo response gần nhất của sequence tương ứng.

### 4.1. Luồng bình thường

```text
Client                              LDAP server
  |                                      |
  | Search + pageSize=200, cookie=""     |
  |------------------------------------->|
  |                 200 entries          |
  |<-------------------------------------|
  | SearchResultDone + cookie=A          |
  |<-------------------------------------|
  |                                      |
  | Search + pageSize=200, cookie=A      |
  |------------------------------------->|
  |                 200 entries          |
  |<-------------------------------------|
  | SearchResultDone + cookie=B          |
  |<-------------------------------------|
  |                                      |
  | Search + pageSize=200, cookie=B      |
  |------------------------------------->|
  |                 35 entries           |
  |<-------------------------------------|
  | SearchResultDone + cookie=""         |
  |<-------------------------------------|
  |                                      |
  | Sequence completed                  |
```

Cookie rỗng ở response cuối cho biết không còn trang tiếp theo. Không dựa vào tổng số ước lượng để kết luận đã hết dữ liệu: server có thể trả estimate bằng 0 nếu không thể ước lượng.

### 4.2. Luồng dừng sớm

Nếu ứng dụng đã xử lý đủ dữ liệu sau trang thứ hai, client cần gửi một SearchRequest có cùng tham số search nhưng control với pageSize=0 và cookie cuối:

```text
Client                              LDAP server
  |                                      |
  | Page 1 -> cookie=A                   |
  | Page 2 -> cookie=B                   |
  |                                      |
  | Stop requested                      |
  |                                      |
  | Search + pageSize=0, cookie=B       |
  |------------------------------------->|
  | SearchResultDone                    |
  |<-------------------------------------|
  |                                      |
  | Paged-results sequence abandoned   |
```

RFC 2696 quy định cách hủy sequence bằng page size bằng 0 và cookie cuối server đã trả. Đây là **một SearchRequest hủy cursor**, không phải LDAP Abandon operation cho request đang chạy.

### 4.3. Không dùng cookie cũ

Khi server trả cookie mới:

- Dùng cookie mới nhất cho trang kế tiếp.
- Không lưu và tái sử dụng cookie từ các trang cũ.
- Không chuyển cookie sang query khác, filter khác, base DN khác hoặc bind identity khác.
- Không giả định cookie có thể tiếp tục sau khi connection bị thay thế.

Cookie là dữ liệu opaque và gắn với sequence do server quản lý. Không đưa cookie vào log công khai hoặc dùng như token phân trang bền vững cho client HTTP nếu không có lớp quản lý trạng thái/connection riêng.

## 5. Vì sao các trang cần cùng một connection?

Spring LDAP đóng context sau mỗi lời gọi LdapTemplate theo mặc định. Trong paged results, server có thể gắn trạng thái cookie với connection; vì vậy các SearchRequest dùng cùng sequence phải đi qua cùng underlying LDAP connection.

Spring LDAP cung cấp hai cách thường dùng:

1. SingleContextSource.doWithSingleContext(...): giữ một context cho chuỗi thao tác trong callback rồi dispose khi callback kết thúc.
2. ContextSourceTransactionManager kết hợp TransactionAwareContextSourceProxy: giữ context trong transaction scope.

Với một job paging tuần tự, SingleContextSource thường dễ hiểu và giới hạn phạm vi connection rõ ràng.

### 5.1. Không tạo processor mới cho mỗi trang

Processor giữ trạng thái request/response control và cookie. Dùng cùng một PagedResultsControlExchangeDirContextProcessor trong toàn bộ vòng lặp.

Không viết:

```java
while (more) {
    // Sai: processor mới không có cookie của trang trước.
    PagedResultsControlExchangeDirContextProcessor processor =
        new PagedResultsControlExchangeDirContextProcessor(PAGE_SIZE);
    // ...
}
```

Tạo processor một lần trước vòng lặp và để postProcess cập nhật exchange sau mỗi page response.

### 5.2. Không chạy các page request song song

Một sequence có cookie tuần tự:

```text
Page 1 -> cookie A -> Page 2 -> cookie B -> Page 3
```

Không gửi đồng thời page 2 và page 3 bằng cùng cookie A. Server có thể chỉ cho phép tiếp tục bằng cookie cuối cùng và việc tái sử dụng cookie cũ có hành vi không xác định theo RFC.

## 6. Paging với Spring LDAP 4.1+

Spring LDAP 4.1 giới thiệu PagedResultsControlExchangeDirContextProcessor. API này dùng ControlExchange để quản lý request/response control và cung cấp hasMore().

Ví dụ sau thu thập tất cả tên user, mỗi lần chỉ nhận một trang:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.support.SingleContextSource;

public List<String> readAllNames() {
    int pageSize = 200;
    String base = "ou=people";
    String filter = "(objectClass=inetOrgPerson)";

    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setReturningAttributes(new String[] {"cn"});

    return SingleContextSource.doWithSingleContext(
        contextSource,
        operations -> {
            List<String> allNames = new ArrayList<>();
            PagedResultsControlExchangeDirContextProcessor processor =
                new PagedResultsControlExchangeDirContextProcessor(pageSize);

            do {
                List<String> page = operations.search(
                    base,
                    filter,
                    controls,
                    attrs -> (String) attrs.get("cn").get(),
                    processor
                );
                allNames.addAll(page);
            } while (processor.hasMore());

            return allNames;
        }
    );
}
```

Điểm cần chú ý:

- SingleContextSource.doWithSingleContext giữ connection xuyên suốt callback.
- processor được tạo một lần và dùng cho tất cả page.
- operations.search đọc xong một trang và trả List.
- LdapTemplate đóng enumeration sau mỗi page.
- processor.hasMore() dựa vào cookie response, không dựa vào số lượng entry trả về.
- Khi callback kết thúc, SingleContextSource dispose context underlying.

Ví dụ thu thập tất cả kết quả nên dùng khi tập dữ liệu có giới hạn phù hợp với bộ nhớ. Nếu dữ liệu lớn, hãy xử lý/ghi từng page ra sink thay vì cộng dồn tất cả vào một List.

## 7. Dừng sau một trang và hủy sequence đúng cách

Đây là mẫu phù hợp khi ứng dụng biết muốn dừng sau khi đã nhận một trang hoàn chỉnh:

1. Gửi SearchRequest cho trang hiện tại.
2. Đọc hết trang và để LdapTemplate gọi postProcess.
3. Xử lý các entry trong List của trang.
4. Nếu điều kiện dừng đã đạt và processor còn cookie, gửi cancellation với page size bằng 0.
5. Kết thúc callback; SingleContextSource đóng underlying context.

Điểm quan trọng là cookie phải là cookie mới nhất từ response của một trang đã hoàn tất.

### 7.1. Ví dụ dừng sau một số entry

Giả sử service chỉ cần xử lý tối đa 350 người. Page size là 200; sau trang thứ hai, ứng dụng xử lý đủ 350 người và không muốn yêu cầu trang thứ ba:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;

import javax.naming.directory.SearchControls;
import javax.naming.ldap.PagedResultsResponseControl;

import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.LdapOperations;
import org.springframework.ldap.core.support.SingleContextSource;

public List<Person> readUntil(
        Predicate<Person> shouldContinue,
        int pageSize) {

    String base = "ou=people";
    String filter = "(objectClass=inetOrgPerson)";

    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setReturningAttributes(
        new String[] {"uid", "cn", "mail"}
    );

    return SingleContextSource.doWithSingleContext(
        contextSource,
        operations -> {
            List<Person> processed = new ArrayList<>();
            PagedResultsControlExchangeDirContextProcessor processor =
                new PagedResultsControlExchangeDirContextProcessor(pageSize);

            do {
                List<Person> page = operations.search(
                    base,
                    filter,
                    controls,
                    personMapper,
                    processor
                );

                // Trang đã được đọc đầy đủ; giờ mới quyết định dừng.
                for (Person person : page) {
                    if (!shouldContinue.test(person)) {
                        cancelIfMore(
                            operations,
                            base,
                            filter,
                            controls,
                            processor
                        );
                        return processed;
                    }
                    processed.add(person);
                }
            } while (processor.hasMore());

            return processed;
        }
    );
}
```

Ở đây, predicate trả về false khi entry hiện tại không cần xử lý tiếp. Trang LDAP đã được đọc hoàn chỉnh trước khi predicate chạy, nên processor đã có response control/cookie của trang đó. Nếu còn trang, helper gửi yêu cầu hủy.

### 7.2. Lấy cookie cuối từ processor

Trong Spring LDAP 4.1+, processor dùng ControlExchange. Response control chứa cookie:

```java
private byte[] lastCookie(
        PagedResultsControlExchangeDirContextProcessor processor) {

    PagedResultsResponseControl response =
        processor.getExchange().getResponse();

    return response == null ? null : response.getCookie();
}
```

Cookie có thể null hoặc rỗng khi không còn trang tiếp theo. Không giải mã, parse hoặc sửa byte array cookie.

### 7.3. Gửi page-size-zero cancellation trên cùng connection

Spring LDAP 4.1+ cung cấp processor để tiếp tục paging, nhưng thao tác hủy sequence có thể được gửi trực tiếp bằng JNDI control:

```java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import javax.naming.NamingEnumeration;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;
import javax.naming.ldap.Control;
import javax.naming.ldap.LdapContext;
import javax.naming.ldap.PagedResultsControl;

private void cancelIfMore(
        LdapOperations operations,
        String base,
        String filter,
        SearchControls searchControls,
        PagedResultsControlExchangeDirContextProcessor processor) {

    if (!processor.hasMore()) {
        return;
    }

    byte[] cookie = lastCookie(processor);
    if (cookie == null || cookie.length == 0) {
        return;
    }
    boolean critical = processor.getExchange().getRequest().isCritical();

    operations.executeReadOnly(context -> {
        if (!(context instanceof LdapContext)) {
            throw new IllegalStateException(
                "Paging controls require an LdapContext"
            );
        }

        LdapContext ldapContext = (LdapContext) context;
        List<Control> requestControls = new ArrayList<>();
        Control[] currentControls = ldapContext.getRequestControls();

        // Giữ các control khác; thay paged-results control bằng size=0.
        if (currentControls != null) {
            for (Control control : currentControls) {
                if (!PagedResultsControl.OID.equals(control.getID())) {
                    requestControls.add(control);
                }
            }
        }

        try {
            requestControls.add(
                new PagedResultsControl(
                    0,
                    cookie,
                    critical
                )
            );
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot encode paged-results cancellation control",
                ex
            );
        }

        ldapContext.setRequestControls(
            requestControls.toArray(new Control[0])
        );

        NamingEnumeration<SearchResult> cancellationResponse = null;
        try {
            // Base, filter và SearchControls phải giống search sequence.
            cancellationResponse = ldapContext.search(
                base,
                filter,
                searchControls
            );

            // Đọc tới SearchResultDone để request cancellation hoàn tất.
            while (cancellationResponse.hasMore()) {
                cancellationResponse.next();
            }
        } finally {
            if (cancellationResponse != null) {
                cancellationResponse.close();
            }
        }

        return null;
    });
}
```

Các điều kiện của ví dụ:

- ContextSource phải cấp LdapContext, thường dùng LdapContextSource khi làm việc với LDAP controls.
- Hàm cancel được gọi bên trong callback của SingleContextSource, nên context vẫn là connection đã dùng cho các page trước.
- Base DN, filter và SearchControls phải giống request paging ban đầu; chỉ page size và cookie của paged-results control thay đổi.
- Các request control khác được giữ lại. Nếu ứng dụng có sort hoặc control khác, phải giữ nguyên chúng theo đúng sequence.
- Cancellation phải hoàn tất trước khi callback của SingleContextSource kết thúc.

JNDI PagedResultsControl cho phép page size bằng 0 cùng cookie cuối để hủy sequence. Nếu server không chấp nhận control hoặc trả lỗi, ghi nhận cleanup failure; khi callback kết thúc, SingleContextSource vẫn đóng context client.

### 7.4. Khác biệt API giữa Spring LDAP 3.x và 4.1+

Ví dụ chính trong bài dùng API mới:

- Spring LDAP 4.1+: PagedResultsControlExchangeDirContextProcessor và processor.getExchange().getResponse().getCookie().
- Spring LDAP 3.3.x: PagedResultsDirContextProcessor và wrapper PagedResultsCookie.

Ví dụ khởi tạo processor trong Spring LDAP 3.3.x:

```java
PagedResultsDirContextProcessor processor =
    new PagedResultsDirContextProcessor(pageSize);

// Sau một page search đã hoàn tất:
PagedResultsCookie cookieHolder = processor.getCookie();
byte[] cookie = cookieHolder == null
    ? null
    : cookieHolder.getCookie();
```

PagedResultsDirContextProcessor và PagedResultsCookie được đánh dấu deprecated trong Spring LDAP 4.1+ để chuyển sang ControlExchange API. Không trộn processor của 3.x với API exchange của 4.x; chọn theo version Spring LDAP mà Spring Boot dependency management đưa vào.

### 7.5. Phân biệt đã hủy với chỉ đóng connection

| Hành động | Tác dụng |
| --- | --- |
| Đóng NamingEnumeration | Ngừng đọc kết quả của search hiện tại. |
| Đóng LdapContext | Đóng connection phía client. |
| Gửi pageSize=0 + cookie cuối | Thông báo server hủy paged-results sequence. |
| Không gửi thêm trang và chờ server timeout | Dừng client; server tự giải phóng trạng thái theo cơ chế/timeout của implementation. |

Nếu đã có cookie cuối và connection còn dùng được, ưu tiên gửi cancellation rõ ràng. Nếu connection đã mất hoặc chưa có cookie hợp lệ, không thể gửi cancellation đáng tin cậy; hãy đóng tài nguyên client và để server quản lý trạng thái hết hạn.

## 8. Dừng giữa trang hiện tại khác với dừng giữa hai trang

Đây là ranh giới quan trọng nhất của early stop.

### 8.1. Dừng giữa hai trang

Sau khi SearchRequest của trang hiện tại hoàn tất:

- LdapTemplate đã duyệt hết enumeration.
- postProcess đã đọc response control.
- Cookie mới nhất đã có.
- Ứng dụng có thể quyết định tiếp tục hoặc gửi cancellation.

Đây là thời điểm an toàn và dễ kiểm soát nhất để dừng.

### 8.2. Dừng khi enumeration của trang chưa đọc hết

Nếu callback ném exception khi đang xử lý entry thứ 20 trong page size 200:

- SearchRequest hiện tại có thể chưa nhận SearchResultDone.
- Response control của trang có thể chưa sẵn sàng.
- Cookie mới nhất của sequence có thể vẫn là cookie từ trang trước.
- Đóng enumeration có thể khiến provider abandon search request đang chạy.

RFC 2696 cảnh báo LDAP Abandon operation cho một paged search request đang chạy có thể làm cookie mất hiệu lực. Vì vậy, không lấy cookie cũ rồi giả định có thể hủy sequence hiện tại như thể trang vừa hoàn tất.

Nếu bắt buộc phải xử lý callback theo từng entry nhưng vẫn muốn hủy sequence sạch:

1. Khi điều kiện dừng đạt, đánh dấu cờ stop.
2. Ngừng xử lý nghiệp vụ các entry còn lại của page.
3. Tiếp tục đọc/discard các entry còn lại để search hiện tại hoàn tất.
4. Để processor nhận response control/cookie.
5. Sau khi search trả về, gửi page-size-zero cancellation bằng cookie mới.

Với cách này, callback không dừng enumeration giữa chừng; nó chỉ dừng xử lý nghiệp vụ. Nếu không thể drain page, hãy coi request hiện tại đã bị abandon, đóng connection và không tái sử dụng cookie như một cursor chắc chắn còn hợp lệ.

### 8.3. Vì sao không ném exception giả để break callback?

Mẫu sau có thể dùng để thoát một callback thông thường:

```java
throw new StopSearchException();
```

LdapTemplate vẫn chạy finally và đóng enumeration/context. Nhưng trong paged search, việc thoát giữa page có thể ngăn response control hoàn tất. Exception sentinel không phải cơ chế hủy paged-results sequence theo RFC 2696.

Chỉ dùng cách này nếu chấp nhận bỏ sequence đang chạy và không cần gửi page-size-zero cancellation bằng cookie hiện tại. Với paging có trạng thái, ưu tiên dừng ở ranh giới page.

## 9. Stream và try-with-resources

Spring LDAP có API trả Java Stream cho một số search; Spring Data repository cũng có thể khai báo method trả Stream nếu module/version hỗ trợ.

Một Stream có thể giữ tài nguyên underlying. Vì vậy, phải đóng stream khi dùng, kể cả khi terminal operation dừng sớm:

```java
try (var stream = ldapTemplate.searchForStream(
        query,
        personMapper)) {

    stream
        .limit(100)
        .forEach(this::process);
}
```

Try-with-resources gọi close khi:

- Stream được tiêu thụ hết.
- Terminal operation ném exception.
- limit hoặc findFirst khiến xử lý dừng sớm.

Tuy nhiên, đóng Stream không tự động tương đương page-size-zero cancellation của RFC 2696. Nếu Stream đang đọc một SearchRequest có paged-results control, vẫn phải hiểu cách processor/cookie được quản lý và cách server sequence được kết thúc.

### 9.1. Stream không tự động là server-side paging

Stream API là cách biểu diễn kết quả để xử lý tuần tự. Paged-results control là cơ chế protocol để server chia SearchResult thành nhiều trang. Hai khái niệm khác nhau:

- Stream có thể chỉ là view của tập kết quả đã được materialize.
- Paging control yêu cầu server trả từng page và client gửi cookie cho page tiếp theo.
- limit(100) dừng Stream pipeline; nó không tự tạo SearchRequest có page size bằng 0.

Nếu cần kiểm soát số entry tải từ server, dùng paged-results control và quản lý cookie rõ ràng.

### 9.2. LdapClient

LdapClient cung cấp API Stream-oriented cho search trong các phiên bản Spring LDAP mới. Hãy dùng try-with-resources cho Stream trả về. Khi kết hợp với paged controls hoặc custom controls, kiểm tra API/version hỗ trợ processor và bảo đảm connection affinity giống khi dùng LdapTemplate.

Không để Stream thoát khỏi scope của connection/transaction đã tạo nó. Không trả Stream gắn với LDAP context cho controller để serialize sau khi method service đã kết thúc.

## 10. Transaction-aware connection

Thay vì SingleContextSource, ứng dụng có thể cấu hình:

- ContextSourceTransactionManager.
- TransactionAwareContextSourceProxy bọc ContextSource.
- LdapTemplate dùng proxy đó.

Các page request chạy trong cùng transaction/context scope có thể dùng chung connection. Tuy nhiên, transaction support của Spring LDAP chủ yếu giúp quản lý connection/context; không biến LDAP paging thành transaction dữ liệu có rollback các SearchRequest.

Nếu dùng transaction:

- Đặt toàn bộ vòng lặp page trong cùng transaction boundary.
- Không giữ transaction mở trong thời gian chờ người dùng hoặc gọi HTTP service chậm.
- Không để cookie vượt khỏi connection scope nếu server yêu cầu connection affinity.
- Đảm bảo transaction kết thúc dù xử lý page ném exception.

Với job batch có thể chạy lâu, SingleContextSource.doWithSingleContext thường làm rõ phạm vi giữ connection hơn một transaction nghiệp vụ kéo dài.

## 11. Trường hợp lỗi và cleanup

| Tình huống | Tài nguyên/cookie | Cách xử lý |
| --- | --- | --- |
| Search page thành công, còn cookie | Enumeration đã đóng; connection còn trong SingleContextSource | Tiếp tục page hoặc gửi cancellation. |
| Trang cuối, cookie rỗng | Sequence hoàn tất | Không gửi cancellation; kết thúc callback và đóng connection. |
| Consumer yêu cầu stop sau khi page đã đọc xong | Có cookie mới nhất | Gửi page-size-zero cancellation, sau đó đóng context. |
| Mapper ném exception giữa page | Có thể chưa có response control của page hiện tại | LdapTemplate cleanup; không giả định cookie mới đã có. Đóng context khi callback thoát. |
| Network timeout trước response | Trạng thái page có thể chưa xác định | Không retry cookie cũ mù quáng; kết thúc connection/sequence và bắt đầu search mới nếu nghiệp vụ cho phép. |
| Cancellation request bị lỗi | Client vẫn phải đóng context | Ghi nhận lỗi cleanup; không tiếp tục dùng cookie. |
| Server không hỗ trợ paged-results control | Có thể trả unsupportedCriticalExtension nếu control critical; nếu noncritical có thể bỏ qua | Phát hiện trong capability/integration test; dùng fallback có giới hạn. |
| Connection bị thay thế giữa hai page | Cookie có thể không dùng được | Bắt đầu sequence mới; không dùng cookie trên connection khác. |
| Search bị hủy bằng LDAP Abandon | Cookie có thể mất hiệu lực | Không tái sử dụng cookie; xử lý như sequence đã kết thúc. |

### 11.1. Không retry vô hạn với cùng cookie

Cookie không phải offset số nguyên và không thể suy ra trang tiếp theo. Nếu server từ chối cookie hoặc connection bị thay:

- Không tự sửa byte array.
- Không quay lại cookie cũ.
- Không tự tăng page index rồi giả định bỏ qua số entry tương ứng.
- Khởi tạo một paged sequence mới với cookie rỗng, nếu có thể chấp nhận đọc lại.
- Dùng checkpoint nghiệp vụ (ví dụ last processed stable ID hoặc watermark) để tránh xử lý trùng khi restart.

RFC 2696 cũng lưu ý nếu tập kết quả thay đổi trong lúc paging, client có thể nhận một entry nhiều lần hoặc không nhận đủ mọi entry. Paged results không phải snapshot transaction nhất quán của toàn directory.

### 11.2. Cleanup không che mất exception gốc

Khi mapper/consumer đã ném exception, cancellation cũng có thể thất bại. Không nên để lỗi cleanup che mất lỗi xử lý chính:

```java
RuntimeException primaryFailure = null;
try {
    processPages();
} catch (RuntimeException ex) {
    primaryFailure = ex;
    throw ex;
} finally {
    try {
        cancelIfNeeded();
    } catch (RuntimeException cleanupFailure) {
        if (primaryFailure != null) {
            primaryFailure.addSuppressed(cleanupFailure);
        } else {
            throw cleanupFailure;
        }
    }
}
```

Đây là mẫu khái niệm cho cleanup do ứng dụng tự quản lý. Nếu LdapTemplate đã tự đóng context/enumeration, không đóng lại cùng resource một cách tùy tiện. Hãy phân biệt lỗi xử lý chính với lỗi cancellation.

## 12. Giới hạn tài nguyên và kiểm soát tốc độ

Paged results giúp điều tiết số entry server gửi mỗi response, nhưng không tự đặt giới hạn cho toàn bộ job.

Nên cấu hình:

- Page size phù hợp RAM và kích thước attribute.
- SearchControls count limit/time limit theo use case.
- Timeout kết nối/đọc theo client provider.
- Giới hạn số page hoặc số entry của job.
- Deadline tổng và cancellation token ở tầng ứng dụng.
- Giới hạn số paged sequence đồng thời trên mỗi worker.
- Backpressure khi downstream xử lý chậm.

Page size lớn giảm số round-trip nhưng tăng bộ nhớ và thời gian xử lý một page. Page size nhỏ giảm lượng dữ liệu mỗi lần nhưng tăng số request và có thể giữ server-side cursor lâu hơn.

Không nhầm:

| Tham số | Ý nghĩa |
| --- | --- |
| Page size | Số entry server trả trong một response của paged-results control. |
| SearchControls countLimit | Giới hạn số kết quả của SearchRequest theo JNDI. |
| SearchControls timeLimit | Thời gian server được phép thực hiện search theo SearchRequest. |
| Job deadline | Giới hạn thời gian nghiệp vụ của toàn bộ vòng lặp paging. |

Count limit nhỏ hơn page size hoặc server size limit có thể làm search kết thúc theo quy tắc riêng; cần kiểm tra response/result code và không coi đó là một trang hoàn tất bình thường.

## 13. Test integration cho paging và dừng sớm

Unit test có thể mock processor/callback để kiểm tra logic dừng, nhưng chỉ integration test mới xác minh server trả cookie, connection affinity và page-size-zero cancellation.

### 13.1. Fixture test

Tạo LDAP test directory có base DN và tối thiểu vài trăm entry để page size nhỏ hơn tổng số entry. Ví dụ:

```text
Base: ou=people,dc=example,dc=org
Entries: uid=user-0001 ... uid=user-0250
Page size: 50
Expected pages: 5
```

Test phải dùng LDAP server hỗ trợ RFC 2696. Không giả định mọi embedded server hoặc mock context đều hỗ trợ paged-results control.

### 13.2. Test hoàn tất hết các trang

```java
@Test
void readsAllPagesAndStopsWhenCookieIsEmpty() {
    List<Person> people = service.readAllPeople();

    assertThat(people).hasSize(250);
    assertThat(people)
        .extracting(Person::getUid)
        .doesNotHaveDuplicates();
}
```

Test này kiểm tra số lượng, duplicate và termination. Không dùng result-size estimate làm assertion duy nhất vì server có thể không trả estimate chính xác.

### 13.3. Test dừng sau một phần kết quả

```java
import java.util.concurrent.atomic.AtomicInteger;

@Test
void stopsAfterRequestedCountAndCancelsRemainingPages() {
    AtomicInteger processed = new AtomicInteger();

    List<Person> result = service.readUntil(person ->
        processed.incrementAndGet() <= 75
    , 50);

    assertThat(result).hasSize(75);
    assertThat(processed.get()).isEqualTo(76);
}
```

Ví dụ predicate được gọi thêm một lần cho entry làm điều kiện dừng chuyển sang false; điều chỉnh contract của service nếu muốn predicate đếm khác. Điều quan trọng của test integration là server đã trả cookie sau trang thứ hai và client gửi cancellation trước khi connection scope kết thúc.

### 13.4. Kiểm tra cancellation control

Nếu cần xác minh request hủy thực sự được gửi:

1. Dùng LDAP server test có thể ghi nhận controls hoặc bật protocol trace.
2. Chạy paging với page size nhỏ.
3. Dừng sau một trang chưa phải trang cuối.
4. Xác nhận request tiếp theo có paged-results control OID 1.2.840.113556.1.4.319, size 0 và cookie cuối.
5. Xác nhận service đóng context khi callback kết thúc.

Không log cookie thật trong log ứng dụng; test có thể assert kích thước/giá trị từ fixture test hoặc kiểm tra control tại server harness.

### 13.5. Test exception trong lúc xử lý page

Tạo consumer ném exception sau khi page đã được tải:

- Xác minh exception gốc được trả về.
- Xác minh SingleContextSource kết thúc và connection được đóng.
- Nếu cookie đã có và cleanup cancellation được cấu hình, xác minh cancellation được thử.
- Nếu exception xảy ra trong khi SearchRequest chưa hoàn tất, không yêu cầu test tái sử dụng cookie của request đó.

## 14. Ma trận kiểm thử

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Không có entry | Search hoàn tất; cookie cuối rỗng hoặc không còn trang. |
| Ít entry hơn page size | Một page; processor.hasMore false. |
| Nhiều page | Dùng cùng connection và cùng processor; đọc hết đúng số entry. |
| Dừng sau page hoàn chỉnh | Page-size-zero cancellation dùng cookie mới nhất. |
| Dừng sau một phần List của page | Page đã được tải xong; cancellation vẫn dùng cookie response của page. |
| Callback ném exception giữa enumeration | Enumeration/context được cleanup; không giả định cookie hiện tại hợp lệ. |
| Cancellation request lỗi | Context vẫn đóng; lỗi cleanup được ghi nhận. |
| Connection mất giữa các page | Không tái sử dụng cookie trên connection mới. |
| Server không hỗ trợ control | Phát hiện qua error/capability test; không âm thầm tin rằng paging đã được áp dụng. |
| Tập kết quả thay đổi trong lúc paging | Chấp nhận khả năng duplicate/missing theo RFC; reconcile nếu nghiệp vụ yêu cầu. |

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Trang thứ hai lỗi dù cookie có vẻ đúng | Connection khác connection đã nhận cookie. | Giữ cùng connection bằng SingleContextSource hoặc transaction-aware proxy. |
| Lấy lại dữ liệu trang đầu | Processor bị tạo mới mỗi vòng hoặc cookie không được giữ. | Dùng một processor xuyên suốt sequence. |
| Dừng sớm nhưng server vẫn giữ cursor | Chỉ đóng enumeration/context, chưa gửi page-size-zero cancellation. | Dùng cookie cuối để hủy sequence khi có thể. |
| Cookie null nhưng code vẫn gọi cancellation | Đã đến trang cuối hoặc response control không có cookie. | Chỉ cancel khi processor.hasMore và cookie không rỗng. |
| Cancellation báo lỗi | Dùng cookie cũ, request parameters khác hoặc connection đã mất. | Dùng cookie cuối, cùng search parameters và cùng connection. |
| Callback break làm mất cookie | Enumeration bị đóng trước SearchResultDone. | Dừng ở ranh giới page hoặc drain phần còn lại của page. |
| Context bị đóng giữa paging | LdapTemplate dùng context mới cho từng page. | Bọc toàn bộ vòng lặp trong SingleContextSource. |
| Server trả ít hơn page size | Đó có thể là trang cuối hoặc server size/time limit. | Kiểm tra cookie và LDAP result code, không chỉ đếm entry. |
| Tổng estimate bằng 0 | Server không cung cấp estimate. | Dùng cookie/hasMore để xác định còn trang. |
| Test pass với mock nhưng lỗi production | Mock không mô phỏng connection affinity/control response. | Chạy integration test trên server hỗ trợ RFC 2696. |

## 16. Checklist triển khai

- [ ] Dùng server có hỗ trợ paged-results control.
- [ ] Dùng LdapContextSource khi thao tác LDAPv3 controls.
- [ ] Dùng cùng connection cho mọi request trong một paged sequence.
- [ ] Dùng một PagedResults processor xuyên suốt vòng lặp.
- [ ] Chỉ dùng cookie mới nhất từ response đã hoàn tất.
- [ ] Không parse hoặc tự tạo cookie.
- [ ] Để LdapTemplate quản lý enumeration/context nếu dùng API template.
- [ ] Đóng Stream bằng try-with-resources nếu API trả Stream.
- [ ] Khi dừng, ưu tiên dừng sau một page hoàn chỉnh.
- [ ] Nếu còn cookie, gửi pageSize=0 cùng cookie cuối để hủy sequence.
- [ ] Giữ nguyên base, filter, SearchControls và các control khác khi gửi cancellation.
- [ ] Không dùng LDAP Abandon như cách thay thế mặc định cho page-size-zero cancellation.
- [ ] Nếu connection đã mất hoặc chưa có cookie hợp lệ, không tái sử dụng cookie.
- [ ] Đóng context ở cuối SingleContextSource callback hoặc transaction scope.
- [ ] Có integration test cho full paging, early stop, exception và cancellation.

## 17. Bài tập vận dụng

1. Vẽ vòng đời của một NamingEnumeration trong một page và cookie trong toàn bộ paged sequence.
2. Giải thích tại sao LdapTemplate có thể đóng context sau mỗi lần search nhưng paged results vẫn cần giữ connection.
3. Viết vòng lặp paging dùng PagedResultsControlExchangeDirContextProcessor và SingleContextSource.
4. Thêm điều kiện dừng sau 75 entry khi page size là 50. Vì sao nên dừng sau khi đã nhận đầy đủ trang thứ hai?
5. Viết helper gửi PagedResultsControl có page size bằng 0 và cookie cuối.
6. Vì sao không thể dùng cookie trang đầu sau khi server đã trả cookie trang hai?
7. Điều gì xảy ra nếu callback ném exception ở entry thứ 10 trong page size 100?
8. So sánh đóng NamingEnumeration, đóng LdapContext và hủy sequence bằng page-size-zero control.
9. Thiết kế test kiểm tra connection affinity giữa hai trang.
10. Một job timeout khi SearchRequest đang chạy và chưa nhận SearchResultDone. Có thể kết luận cookie nào hợp lệ? Nêu cách phục hồi.
11. Vì sao result-size estimate bằng 0 không có nghĩa search không có entry?
12. Khi nào nên dùng transaction-aware proxy thay vì SingleContextSource?

## 18. Tài liệu tham khảo

- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696): cookie lifecycle, page size, tiếp tục và hủy sequence.
- [Spring LDAP — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): DirContextProcessor, paged search, SingleContextSource và connection affinity.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): search callback, mapper, processor và cleanup context/enumeration.
- [Spring LDAP API — PagedResultsControlExchangeDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html): processor cho paged-results control trong Spring LDAP 4.1+.
- [Spring LDAP API — PagedResultsControlExchange](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchange.html): request/response control exchange và cookie response.
- [Spring LDAP 3.3 API — PagedResultsDirContextProcessor](https://docs.spring.io/spring-ldap/docs/3.3.x/api/org/springframework/ldap/control/PagedResultsDirContextProcessor.html): processor paged-results dùng trong Spring LDAP 3.x.
- [Spring LDAP 3.3 API — PagedResultsCookie](https://docs.spring.io/spring-ldap/docs/3.3.x/api/org/springframework/ldap/control/PagedResultsCookie.html): wrapper cookie của API cũ.
- [Spring LDAP API — SingleContextSource](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/SingleContextSource.html): giữ một connection qua nhiều LdapOperations.
- [Oracle Java SE — PagedResultsControl](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/PagedResultsControl.html): JNDI control và constructor page size bằng 0 để hủy sequence.
- [Oracle Java SE — NamingEnumeration](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/NamingEnumeration.html): đóng enumeration.
- [Spring Data — Streaming Query Results](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): đóng Stream bằng close hoặc try-with-resources.
