# Giới hạn số kết quả và thời gian thực thi

Một chức năng tra cứu danh bạ bằng **Spring Data LDAP** thường có vẻ đơn giản: nhận từ khóa, tạo LDAP filter, gọi repository hoặc `LdapTemplate` rồi trả danh sách người dùng. Nhưng nếu người dùng nhập tiêu chí quá rộng, directory có hàng trăm nghìn entry hoặc kết nối chậm, một phép Search có thể trả quá nhiều dữ liệu, chiếm tài nguyên server và kéo dài thời gian đáp ứng HTTP.

LDAP hỗ trợ giới hạn **số lượng entry** và **thời gian Search** ngay trong yêu cầu. Spring LDAP cung cấp `LdapQueryBuilder.countLimit(...)`, `timeLimit(...)` và các tùy chọn mặc định của `LdapTemplate`. Tuy nhiên, hai loại giới hạn này **không tương đương với phân trang**, **không kiểm soát mọi loại timeout**, và có thể dẫn đến **kết quả chưa đầy đủ** phải được xử lý công khai.

Bài học thuộc chương **Tìm kiếm** của `SPRING_DATA_LDAP`. Chúng ta sẽ đi từ mô hình `LDAP SearchRequest`, DN, scope, `objectClass` và filter an toàn tới cấu hình Spring Boot, ví dụ Java, xử lý exception, kiểm thử directory và thiết kế API tránh công bố danh sách thiếu dữ liệu như kết quả hoàn chỉnh.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `sizeLimit` của giao thức LDAP với `countLimit` của Spring LDAP/JNDI, hiểu ý nghĩa giá trị `0`.
2. Phân biệt `timeLimit` của LDAP SearchRequest (**giây**) với `timeLimit` của Spring LDAP/JNDI SearchControls (**mili giây**).
3. Giới hạn base, search scope, filter, thuộc tính trả về, count và thời gian trong một `LdapQuery`.
4. Hiểu cách `LdapTemplate` áp dụng các giới hạn mặc định khi query không khai báo chúng.
5. Giải thích `sizeLimitExceeded (4)`, `timeLimitExceeded (3)` và `adminLimitExceeded (11)`, cũng như giới hạn do LDAP server tự áp đặt.
6. Nhận diện nguy cơ khi `SizeLimitExceededException` bị bỏ qua: client có dữ liệu nhưng **không biết danh sách có đầy đủ hay không**.
7. Tách giới hạn Search khỏi **TCP connect timeout**, **socket/read timeout** và **HTTP request deadline**.
8. Biết khi nào chuyển từ giới hạn kết quả sang **Simple Paged Results Control** thay vì tự cắt một danh sách lớn.
9. Thiết kế service/REST API và test kiểm tra lượng dữ liệu, độ trễ, kết quả một phần, ACL, TLS và filter injection.

## 2. Tình huống: danh bạ tăng từ vài người lên hàng nghìn entry

Giả sử directory có cây:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   ├── uid=minh
│   ├── uid=mai
│   └── ... hàng chục nghìn nhân viên
├── ou=contractors
│   └── ... nhà thầu
└── ou=groups
    └── cn=engineering
~~~

Một entry người dùng:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
title: Backend Developer
~~~

Ví dụ khách hàng gửi:

~~~http
GET /api/v1/people?sn=Nguyen&limit=50
~~~

Phía API chỉ muốn trả tối đa 50 người có họ `Nguyen` trong nhánh `ou=people`, không mở rộng sang nhà thầu/nhóm và không chờ vô hạn.

Nếu không có giới hạn, filter rộng như `(objectClass=inetOrgPerson)` có thể làm LDAP server gửi rất nhiều entry. Chỉ định `countLimit(50)` giúp giới hạn số entry được yêu cầu; `timeLimit(2_000)` giới hạn thời gian Search ở tầng API Java. Nhưng **một phản hồi có 50 người chưa chứng minh toàn directory chỉ có 50 người phù hợp**.

## 3. LDAP SearchRequest có những tham số nào?

Theo RFC 4511, một `SearchRequest` bao gồm:

~~~text
SearchRequest
├── baseObject        DN bắt đầu tìm kiếm
├── scope             base / one level / subtree
├── derefAliases      Chính sách xử lý alias
├── sizeLimit         Số entry tối đa yêu cầu trả về
├── timeLimit         Thời gian Search theo giao thức (giây)
├── typesOnly         Chỉ tên attribute hay cả giá trị
├── filter            Điều kiện tìm kiếm
└── attributes        Những thuộc tính cần trả về
~~~

Spring LDAP ánh xạ các cấu hình chính sang `LdapQueryBuilder`.

| Thành phần | Ví dụ | Giúp giảm tải như thế nào? |
| --- | --- | --- |
| Base DN | `ou=people,dc=example,dc=org` | Không tìm ngoài nhánh danh bạ. |
| Scope | `ONELEVEL` hoặc `SUBTREE` | Tránh duyệt những tầng không cần thiết. |
| Filter | `(&(objectClass=inetOrgPerson)(sn=Nguyen))` | Hạn chế entry phù hợp tiêu chí. |
| Attribute selection | `uid,cn,sn,mail` | Không truyền về mọi thuộc tính LDAP. |
| Size/count limit | `50` | Đặt trần số entry được trả cho yêu cầu. |
| Search time limit | `2_000` ms ở Spring LDAP | Giới hạn thời gian xử lý/chờ của Search theo API Java. |

**Giới hạn Search là một phần của thiết kế tài nguyên**, không thay thế ACL, phân quyền API hoặc filter escaping.

### Các scope khác nhau

| Scope | Phạm vi | Ví dụ |
| --- | --- | --- |
| `OBJECT` | Chỉ entry ở base DN. | Kiểm tra một entry cụ thể. |
| `ONELEVEL` | Chỉ con trực tiếp của base. | Nhân viên đặt ngay dưới `ou=people`. |
| `SUBTREE` | Base và mọi hậu duệ. | Nhân viên nằm trong nhiều OU phòng ban. |

Nếu người dùng được tổ chức theo `uid=lan,ou=engineering,ou=people,...`, truy vấn `ONELEVEL` từ `ou=people` **không thấy** Lan; `SUBTREE` có thể thấy. Không nên chuyển sang `SUBTREE` chỉ để “hết lỗi” mà chưa đánh giá dữ liệu, ACL và số entry sẽ duyệt.

## 4. SizeLimit của LDAP khác countLimit của ứng dụng thế nào?

### 4.1. Trường sizeLimit ở giao thức

RFC 4511 định nghĩa `SearchRequest.sizeLimit` là **số entry tối đa client yêu cầu server trả về**.

- `sizeLimit=50`: client yêu cầu tối đa 50 entry.
- `sizeLimit=0`: **không có giới hạn kích thước do chính client yêu cầu**.
- Server vẫn có thể áp **giới hạn quản trị riêng**, chặt hơn client.
- Directory không phải gửi mọi entry phù hợp khi quyền ACL hoặc search scope không cho phép.

**Đừng hiểu `0` là “bắt buộc trả toàn bộ directory”.** Nó chỉ loại bỏ trần do client yêu cầu; server có thể từ chối hoặc dừng sớm khi đạt policy.

### 4.2. countLimit ở Spring LDAP

Ở Java:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .countLimit(50)
        .where("objectClass").is("inetOrgPerson");
~~~

`countLimit(50)` yêu cầu tối đa 50 entry cho Search được tạo. Giá trị `0` tương ứng không đặt giới hạn count của ứng dụng ở mức query/template, nhưng không vô hiệu hóa giới hạn server.

**Không phải SQL `LIMIT/OFFSET`:** LDAP Search cơ bản không có SQL offset. Nếu client gửi lại cùng filter với `countLimit(50)` lần hai, nó **không tự nhận nhóm 50 người tiếp theo**. Việc gọi lặp có thể trả cùng tập hoặc tập khác do thay đổi dữ liệu/thứ tự xử lý.

### 4.3. countLimit và page size là hai mục đích khác nhau

| Nhu cầu | Dùng gì? | Không được suy ra |
| --- | --- | --- |
| Chặn một Search trả quá nhiều entry | `countLimit` | Không tạo trang 2 tự động. |
| Duyệt tập entry lớn theo từng trang | Paged Results Control nếu directory hỗ trợ | Không phải offset của SQL. |
| Trả danh sách có giới hạn cho giao diện | Limit + thông tin “có thể còn kết quả” | Không có tổng số chính xác nếu chưa tính/kiểm chứng. |
| Đồng bộ mọi entry của directory | Phân trang + checkpoint/đối soát | Không có snapshot nhất quán chỉ nhờ paging. |

## 5. Giới hạn thời gian: đơn vị rất dễ nhầm

Có **hai đơn vị khác nhau** phải ghi nhớ.

| Cấu hình | Đơn vị | Ví dụ |
| --- | --- | --- |
| `SearchRequest.timeLimit` trong LDAPv3 (RFC 4511) | **Giây** | `timeLimit=2` nghĩa là 2 giây. |
| `SearchControls.setTimeLimit(int)` của JNDI | **Mili giây** | `setTimeLimit(2_000)` nghĩa là 2.000 ms. |
| `LdapQueryBuilder.timeLimit(int)` / `LdapTemplate.setDefaultTimeLimit(int)` | **Mili giây** theo tầng Spring LDAP/JNDI | `timeLimit(2_000)` là 2 giây. |
| `com.sun.jndi.ldap.connect.timeout` | Mili giây theo JNDI provider tương ứng | `2000` là 2 giây connect. |
| `com.sun.jndi.ldap.read.timeout` | Mili giây theo JNDI provider tương ứng | `4000` là giới hạn chờ đọc ở provider. |

**Không viết `.timeLimit(2)` nếu muốn Search được phép chạy 2 giây:** trong tầng Spring LDAP/JNDI, `2` là 2 mili giây. Cũng không truyền `.timeLimit(2_000)` rồi hiểu đó là “2.000 giây”.

### 5.1. Vì sao có sự khác biệt?

LDAP SearchRequest ở wire protocol lưu `timeLimit` bằng số **giây**. Java JNDI dùng `SearchControls` với trường thời gian tính bằng **mili giây**; Spring LDAP xây trên tầng đó.

Provider thực hiện chuyển đổi giữa hai mức độ chính xác. **Không dựa vào giới hạn 1–100 ms để bảo đảm deadline toàn hệ thống**, vì cách chuyển đổi sang protocol, lịch thực thi server, network và kiểm tra timeout có thể khác nhau. Thay vì yêu cầu “Search chắc chắn dừng đúng tại 100 ms”, cần thiết kế nhiều lớp timeout và đo thời gian thực tế.

### 5.2. Giá trị 0 nghĩa là gì?

- `timeLimit(0)`: không đặt giới hạn thời gian Search ở tầng cấu hình đó.
- Server vẫn có thể có `timelimit` hoặc policy mặc định.
- Socket/read timeout và deadline HTTP (nếu được cấu hình) vẫn có thể cắt yêu cầu.
- Không nên đặt `0` làm “vô hạn” cho các Search công khai chỉ vì dữ liệu hiện tại còn ít.

## 6. Cấu hình một LdapQuery đủ các tham số

Với Spring LDAP:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .countLimit(50)
        .timeLimit(2_000) // mili giây
        .attributes("uid", "cn", "sn", "mail")
        .where("objectClass").is("inetOrgPerson")
        .and("sn").is("Nguyen");
~~~

Giải thích:

1. `.base("ou=people")` là base **tương đối với `spring.ldap.base=dc=example,dc=org`**.
2. `ONELEVEL` chỉ tìm những người nằm trực tiếp dưới OU đó.
3. `countLimit(50)` đặt trần 50 entry cho Search.
4. `timeLimit(2_000)` yêu cầu Search không kéo dài quá mức ở tầng API Java.
5. `attributes(...)` chỉ lấy các thuộc tính dùng trong DTO, giảm payload.
6. `.where(...).is(...)` xây filter qua API Spring LDAP, không ghép raw input.
7. Các thuộc tính base/scope/count/time/attributes phải được chỉ định **trước** khi bắt đầu xây điều kiện filter, đúng quy tắc `LdapQueryBuilder`.

### Thứ tự cấu hình trong query builder

Nên viết:

~~~java
LdapQuery valid = LdapQueryBuilder.query()
        .base("ou=people")
        .countLimit(25)
        .timeLimit(1_500)
        .where("uid").is(userInput);
~~~

Không nên bắt đầu `.where("uid").is(...)` rồi mới gọi `.countLimit(25)` trên cùng builder. API builder có ràng buộc việc thay đổi tham số phi-filter sau khi tạo filter.

## 7. Dùng SearchControls khi cần giao diện JNDI tường minh

Spring LDAP cũng cho phép truyền `javax.naming.directory.SearchControls` vào các overload của `LdapTemplate.search(...)`.

~~~java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
controls.setCountLimit(50L);
controls.setTimeLimit(2_000); // mili giây
controls.setReturningAttributes(
        new String[] {"uid", "cn", "sn", "mail"});
~~~

Cách này giúp thấy rõ các trường của JNDI:

- `setCountLimit(long)` đặt giới hạn số entry.
- `setTimeLimit(int)` đặt giới hạn thời gian **theo ms**.
- `setReturningAttributes(...)` hạn chế tập thuộc tính được trả.
- `setSearchScope(...)` giới hạn cấp độ duyệt.

Không nhất thiết phải dùng trực tiếp `SearchControls` nếu `LdapQueryBuilder` đã diễn đạt đầy đủ nhu cầu. **Hai đoạn trên là hai cách khác nhau để tạo một Search**, không phải hai bộ giới hạn cần cộng dồn.

## 8. Cấu hình giới hạn mặc định ở LdapTemplate

`LdapQueryBuilder` có thể không chỉ rõ count/time. Khi đó `LdapTemplate` dùng giá trị mặc định được cấu hình.

Theo tài liệu API Spring LDAP:

| Mặc định của LdapTemplate | Giá trị nếu không cấu hình | Ý nghĩa |
| --- | --- | --- |
| `defaultCountLimit` | `0` | Không có giới hạn số entry do template đặt. |
| `defaultTimeLimit` | `0` | Không có giới hạn thời gian Search do template đặt. |
| `defaultSearchScope` | `SUBTREE` | Mặc định duyệt cả subtree. |
| `ignoreSizeLimitExceededException` | **`true`** | Có thể bỏ qua exception khi Search vượt giới hạn kích thước. |
| `ignorePartialResultException` | `false` | Không mặc định bỏ qua lỗi kết quả một phần do referral. |
| `ignoreNameNotFoundException` | `false` | Không mặc định bỏ qua lỗi Search base không tồn tại. |

Nếu một ứng dụng có các Search public mà không truyền `countLimit` hay `timeLimit`, mặc định `0/0` có thể làm truy vấn rộng và lâu hơn dự kiến.

### 8.1. Bean Java với giới hạn mặc định

~~~java
import javax.naming.directory.SearchControls;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;

@Configuration
public class BoundedLdapConfig {

    @Bean
    public LdapTemplate ldapTemplate(ContextSource contextSource) {
        LdapTemplate template = new LdapTemplate(contextSource);
        template.setDefaultCountLimit(100);
        template.setDefaultTimeLimit(3_000);
        template.setDefaultSearchScope(
                SearchControls.ONELEVEL_SCOPE);

        // Với API không chấp nhận dữ liệu thiếu, đừng nuốt lỗi 4.
        template.setIgnoreSizeLimitExceededException(false);
        template.setIgnorePartialResultException(false);
        return template;
    }
}
~~~

Ví dụ giả định bean này là **LdapTemplate chủ đạo** của ứng dụng. Nếu Spring Boot cũng auto-configure `LdapTemplate`, hãy kiểm tra bean thực tế và cấu hình injection/repository để không có một template khác với limit `0/0` vô tình được sử dụng.

Giới hạn trên `LdapTemplate` là **mặc định**: query riêng có `countLimit(20)` hoặc `timeLimit(1_000)` có thể ghi đè từng giá trị. Service nhạy cảm nên khai báo giới hạn tường minh để policy không phụ thuộc một bean khác đang được inject.

### 8.2. Qua cấu hình Spring Boot

Trong các phiên bản Spring Boot có các thuộc tính template tương ứng, có thể chọn chính sách không nuốt exception giới hạn:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-reader,ou=service,dc=example,dc=org
    password: "${LDAP_BIND_PASSWORD}"
    template:
      ignore-size-limit-exceeded-exception: false
      ignore-partial-result-exception: false
      ignore-name-not-found-exception: false
~~~

Các mục `ignore-*` quyết định cách `LdapTemplate` xử lý một số exception, **không đặt `countLimit` và `timeLimit` cho từng query**. Hãy đặt count/time trong `LdapQueryBuilder` hoặc cấu hình `LdapTemplate` rõ ràng.

Tùy phiên bản Spring Boot, kiểm tra lại hỗ trợ cấu hình thuộc tính và bean auto-configuration. Không để một property chưa được nhận tạo cảm giác “đã giới hạn Search”.

## 9. Điều ít được chú ý: SizeLimitExceededException có thể bị bỏ qua

Đây là phần cần đặc biệt cẩn trọng.

`LdapTemplate.setIgnoreSizeLimitExceededException(true)` là **mặc định được Javadoc Spring LDAP mô tả**. Nếu directory/JNDI ném `SizeLimitExceededException` và tùy chọn này đang bật, `LdapTemplate` có thể bỏ qua exception để trả về **những entry đã thu thập được trước khi bị giới hạn**.

Với giao diện “xem nhanh tối đa 50 người”, có thể chấp nhận trả một tập có giới hạn **nếu hợp đồng API nói rõ không phải danh sách đầy đủ**. Nhưng với API đồng bộ nhân viên hoặc kiểm tra “có bao nhiêu người đúng điều kiện?”, bỏ qua lỗi có thể gây ra kết luận sai.

### Ví dụ kết quả thiếu dữ liệu

~~~text
Directory có 120 entry phù hợp filter.
Client đặt countLimit = 50.
Directory/JNDI chỉ trả 50 entry rồi thông báo giới hạn.
LdapTemplate ignoreSizeLimitExceededException = true.
Service nhận List có 50 entry.
~~~

**Không được kết luận directory có đúng 50 người.** Mã nghiệp vụ cũng không thể luôn suy luận “đã có trang tiếp theo” chỉ từ kích thước danh sách: thứ tự và hành vi exception phụ thuộc server/provider.

### Ba cách thiết kế hợp đồng

| Mục đích | Cách xử lý | Cảnh báo |
| --- | --- | --- |
| Tra cứu nhanh, “hiển thị tối đa N” | Có thể trả tối đa N và gắn nhãn tập giới hạn. | Không nói kết quả đầy đủ. |
| Xuất dữ liệu/báo cáo cần đầy đủ | `ignoreSizeLimitExceededException=false`, hoặc dùng paging. | Gặp limit phải báo lỗi/chưa hoàn tất. |
| Đồng bộ toàn bộ directory | Paged Results Control hoặc cơ chế phù hợp server. | Theo dõi cookie, scope, thời gian, retry và trạng thái thay đổi. |

### 9.1. Nếu danh sách có đúng N phần tử thì sao?

Giả sử `countLimit=50` và thực tế Search trả đúng 50 phần tử, không có exception. Ta vẫn **chưa chứng minh** chỉ có đúng 50 entry khớp: client có thể đã dừng tại trần, directory có thể có entry thứ 51.

Một cờ phản hồi có thể đặt tên `limitReached` hoặc `mayBeTruncated`, nhưng phải giải thích:

~~~json
{
  "limit": 50,
  "returned": 50,
  "mayBeTruncated": true
}
~~~

**`mayBeTruncated=true` không có nghĩa chắc chắn còn entry tiếp theo.** Cũng không nên tự đặt `complete=true` nếu từng bỏ qua `SizeLimitExceededException` hay `PartialResultException`.

### 9.2. Đối với workflow phải đủ dữ liệu

Với quy trình xác định tất cả nhân viên cần chuyển nhóm hoặc đồng bộ hệ thống, **fail closed**:

- Không bỏ qua exception về limit/time/referral ngoài chính sách.
- Không commit một batch “đã đồng bộ xong” khi chỉ nhận một phần entry.
- Không suy luận tổng số bằng `results.size()` của truy vấn giới hạn.
- Dùng phân trang được directory hỗ trợ và có checkpoint/đối soát.

## 10. Mã kết quả LDAP khi vượt giới hạn

LDAP có các mã khác nhau:

| Mã | Tên | Ý nghĩa thường gặp |
| ---: | --- | --- |
| `0` | `success` | Search hoàn tất theo điều kiện/semantics được áp dụng, có thể trả 0 entry. |
| `3` | `timeLimitExceeded` | Server vượt giới hạn thời gian Search. |
| `4` | `sizeLimitExceeded` | Search vượt giới hạn số entry, có thể đã có một phần kết quả. |
| `11` | `adminLimitExceeded` | Server áp một giới hạn quản trị khác. |
| `10` | `referral` | Có đích khác cần xử lý theo chính sách. |
| `32` | `noSuchObject` | Base DN/entry mục tiêu không tồn tại hoặc không được phân giải. |
| `50` | `insufficientAccessRights` | Bind DN không đủ quyền Search/read dữ liệu. |

**Không có quy tắc “hễ đạt N bản ghi thì chắc chắn trả mã 4”.** Tùy server, query, giới hạn của client/server và việc còn entry khớp hay không, response có thể khác nhau. Test không nên yêu cầu một mã duy nhất khi điều kiện chưa được kiểm soát.

### ResultCode và exception Java

| Tầng | Ví dụ |
| --- | --- |
| LDAP server | `sizeLimitExceeded (4)`, `timeLimitExceeded (3)`. |
| JNDI | `javax.naming.SizeLimitExceededException`, `javax.naming.TimeLimitExceededException`. |
| Spring LDAP | `org.springframework.ldap.SizeLimitExceededException`, `org.springframework.ldap.TimeLimitExceededException`. |
| HTTP API | Lỗi `SEARCH_LIMIT_EXCEEDED`, `DIRECTORY_SEARCH_TIMEOUT` theo hợp đồng. |

Spring LDAP thường **dịch JNDI checked exception sang unchecked exception**. Không parse chuỗi lỗi `"LDAP error code 4"` hoặc trả nguyên `getMessage()` cho client.

Khi bị giới hạn, server có thể đã gửi một số `SearchResultEntry` **trước** `SearchResultDone` báo lỗi. Ứng dụng không được đánh giá một danh sách mới nhận là “đầy đủ” khi chưa kiểm tra trạng thái hoàn tất.

## 11. Một Search có thể bị timeout ở nhiều lớp

Hãy tách rõ:

~~~mermaid
flowchart TD
    A["HTTP request đến API"] --> B["Application deadline / rate limit"]
    B --> C["LDAP kết nối: DNS/TCP/TLS/Bind"]
    C --> D["Connect timeout"]
    C --> E["Socket/Read timeout"]
    C --> F["LDAP SearchRequest"]
    F --> G["sizeLimit/countLimit"]
    F --> H["timeLimit của Search"]
    F --> I["Server-side limits/ACL"]
    D --> J["Phân loại lỗi theo tầng"]
    E --> J
    G --> J
    H --> J
    I --> J
    J --> K["HTTP response/cảnh báo incomplete"]
~~~

### 11.1. Search time limit không bao trùm TCP/TLS

`timeLimit(2_000)` giới hạn thời gian Search theo API LDAP/JNDI; nó không phải một deadline tuyệt đối cho:

- DNS lookup và TCP connection.
- TLS handshake hoặc Bind.
- Chờ network khi server không trả response.
- Các bước application mapping/serialization.
- Nhiều Search liên tiếp trong một HTTP request.

Vì vậy **không được khẳng định API chắc chắn đáp ứng trong 2 giây** chỉ vì Search time limit là 2.000 ms.

### 11.2. Timeout ở JNDI provider

Với môi trường dùng JNDI LDAP provider phổ biến của JDK, có thể cấu hình:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-reader,ou=service,dc=example,dc=org
    password: "${LDAP_BIND_PASSWORD}"
    base-environment:
      "[com.sun.jndi.ldap.connect.timeout]": "2000"
      "[com.sun.jndi.ldap.read.timeout]": "4000"
~~~

Ý nghĩa của `com.sun.jndi.ldap.*` phụ thuộc provider/JDK triển khai, **không phải property chuẩn giao thức LDAP**. Kiểm tra binder và các giá trị environment thực tế của `ContextSource` trong phiên bản Spring Boot/JDK đang dùng. Nếu đã có cấu hình `spring.ldap` ở mục khác, **gộp các khóa vào một nhánh YAML**; đừng khai báo nhiều `spring:` hoặc `ldap:` cạnh nhau.

- `connect.timeout`: giới hạn chờ kết nối theo provider.
- `read.timeout`: giới hạn chờ phản hồi/đọc trên socket theo provider.
- `timeLimit(...)`: giới hạn của Search operation.
- HTTP/server deadline: giới hạn tổng luồng nghiệp vụ do application/infrastructure thực thi.

Với ứng dụng truy vấn nhiều vùng LDAP, deadline tổng nên nhỏ hơn SLA của HTTP, còn giới hạn từng bước phải nằm trong ngân sách tổng. Hãy đo bằng integration test; không cộng thời gian cơ học rồi bảo đảm độ trễ tối đa trong mọi điều kiện.

### 11.3. Đo thời gian thực thi thực tế

Có thể đo ở tầng service:

~~~java
long started = System.nanoTime();
try {
    return ldapTemplate.search(query, mapper);
} finally {
    long durationNanos = System.nanoTime() - started;
    // Ghi duration ở metrics/observability;
    // không log DN hoặc attribute nhạy cảm.
}
~~~

Đây là **elapsed time quan sát được ở ứng dụng**, bao gồm công việc mà lời gọi thực hiện. Nó không thay thế `timeLimit` và không tự cắt lệnh Search đang treo. Với Micrometer/Spring Boot Actuator, có thể đặt tên metric `directory.search.duration` theo operation, kết quả và vùng, tránh dùng UID làm tag vì cardinality và rủi ro riêng tư.

## 12. Thiết kế service tra cứu có giới hạn thực tế

Một API danh bạ chỉ cho truy vấn theo họ, trả tối đa 50 entry và không cho client tự đặt timeLimit vô hạn. Service sau sử dụng `LdapTemplate`, giữ các lựa chọn về base/scope/time/count ở phía server.

`api/PersonSummary.java`:

~~~java
package com.example.directory.api;

public record PersonSummary(
        String uid,
        String fullName,
        String surname,
        String email
) {}
~~~

`api/BoundedPeopleResponse.java`:

~~~java
package com.example.directory.api;

import java.util.List;

public record BoundedPeopleResponse(
        List<PersonSummary> items,
        int requestedLimit,
        boolean mayBeTruncated
) {}
~~~

`service/PeopleSearchService.java`:

~~~java
package com.example.directory.service;

import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

import com.example.directory.api.BoundedPeopleResponse;
import com.example.directory.api.PersonSummary;

@Service
public class PeopleSearchService {

    private static final int MAX_PAGE_SIZE = 50;
    private static final int SEARCH_TIME_MS = 2_000;

    private final LdapTemplate ldapTemplate;

    public PeopleSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public BoundedPeopleResponse findBySurname(
            String surname, int requestedLimit) {

        if (surname == null || surname.isBlank()
                || surname.strip().length() > 100) {
            throw new IllegalArgumentException("Invalid surname");
        }
        if (requestedLimit < 1 || requestedLimit > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("Invalid result limit");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .countLimit(requestedLimit)
                .timeLimit(SEARCH_TIME_MS)
                .attributes("uid", "cn", "sn", "mail")
                .where("objectClass").is("inetOrgPerson")
                .and("sn").is(surname.strip());

        // Cấu hình LdapTemplate để KHÔNG nuốt SizeLimitExceeded
        // nếu use case cần biết rằng Search vượt giới hạn.
        List<PersonSummary> found = ldapTemplate.search(
                query,
                (AttributesMapper<PersonSummary>) attrs ->
                        new PersonSummary(
                                value(attrs, "uid"),
                                value(attrs, "cn"),
                                value(attrs, "sn"),
                                value(attrs, "mail"))
        );

        // Đạt đúng trần KHÔNG có nghĩa chắc chắn còn kết quả.
        // Chỉ biểu thị chưa thể kết luận đầy đủ.
        boolean mayBeTruncated =
                found.size() >= requestedLimit;

        return new BoundedPeopleResponse(
                List.copyOf(found),
                requestedLimit,
                mayBeTruncated
        );
    }

    private static String value(Attributes attrs, String name)
            throws javax.naming.NamingException {
        Attribute attr = attrs.get(name);
        return attr == null ? null : (String) attr.get();
    }
}
~~~

### Đọc ví dụ theo từng lớp

1. **Đầu vào được kiểm tra:** `requestedLimit` nằm trong `1..50`, không thể dùng `0` để bỏ giới hạn.
2. **Search base cố định:** client không được chọn `dc` hoặc `ou` tùy ý.
3. **Scope tường minh:** `ONELEVEL` ngăn vô tình duyệt các OU con.
4. **Filter builder an toàn:** `is(surname.strip())` escape giá trị đúng API, tránh LDAP filter injection.
5. **Giới hạn theo từng request:** count/time không phụ thuộc default của template.
6. **Chỉ lấy thuộc tính công khai:** không yêu cầu `userPassword` hoặc metadata không cần.
7. **Không khẳng định completeness:** `mayBeTruncated` được bật khi trả đúng số lượng tối đa; chưa chứng minh có trang sau.

**Quan trọng:** nếu template được cấu hình `ignoreSizeLimitExceededException=false` và directory phát exception, phương thức trên **không trả `BoundedPeopleResponse`** mà để lỗi đi lên handler. Đó là hành vi có chủ đích cho API không muốn âm thầm cắt kết quả. Không nên bắt exception rồi trả một danh sách rỗng.

### Lưu ý: không gọi đây là phân trang

Dù record đặt tên “response có giới hạn”, `countLimit` **không tạo offset hoặc cookie**. Một client muốn “trang 2” không thể chỉ tăng requestedLimit lên 100 hoặc gọi lại cùng query. Nếu sản phẩm cần nhiều trang, hãy dùng phương thức paging thật ở mục 15.

## 13. Controller và xử lý lỗi của Search

`web/PeopleSearchController.java`:

~~~java
package com.example.directory.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.example.directory.api.BoundedPeopleResponse;
import com.example.directory.service.PeopleSearchService;

@RestController
@RequestMapping("/api/v1/people")
public class PeopleSearchController {

    private final PeopleSearchService service;

    public PeopleSearchController(PeopleSearchService service) {
        this.service = service;
    }

    @GetMapping
    public BoundedPeopleResponse findBySurname(
            @RequestParam String sn,
            @RequestParam(defaultValue = "25") int limit) {
        return service.findBySurname(sn, limit);
    }
}
~~~

Ví dụ:

~~~http
GET /api/v1/people?sn=Nguyen&limit=25
~~~

Nếu truy vấn chỉ tìm thấy một người phù hợp, phản hồi minh họa:

~~~json
{
  "items": [
    {
      "uid": "lan",
      "fullName": "Nguyen Thi Lan",
      "surname": "Nguyen",
      "email": "lan@example.org"
    }
  ],
  "requestedLimit": 25,
  "mayBeTruncated": false
}
~~~

Ví dụ chỉ có **một entry được trả**, nên `mayBeTruncated=false` vì `1 < 25`. Nếu trả **đúng 25 entry**, `mayBeTruncated` phải là `true` trong cách triển khai đã cho.

### 13.1. Ánh xạ lỗi có kiểm soát

~~~java
package com.example.directory.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.ldap.SizeLimitExceededException;
import org.springframework.ldap.TimeLimitExceededException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DirectorySearchErrorHandler {

    public record ApiError(String code, String message) {}

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiError> invalidSearch() {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_SEARCH",
                        "Search parameters are invalid"));
    }

    @ExceptionHandler(SizeLimitExceededException.class)
    public ResponseEntity<ApiError> tooBroad() {
        return ResponseEntity.status(
                HttpStatus.UNPROCESSABLE_ENTITY).body(
                new ApiError(
                        "SEARCH_LIMIT_EXCEEDED",
                        "Narrow the search criteria"));
    }

    @ExceptionHandler(TimeLimitExceededException.class)
    public ResponseEntity<ApiError> timedOut() {
        return ResponseEntity.status(
                HttpStatus.GATEWAY_TIMEOUT).body(
                new ApiError(
                        "DIRECTORY_SEARCH_TIMEOUT",
                        "Directory search timed out"));
    }
}
~~~

Đây là mã HTTP **gợi ý theo hợp đồng của ví dụ**, không có quy tắc chuyển đổi cứng LDAP result code sang HTTP status. Trong dự án thật phải xử lý thêm `PartialResultException`, server unavailable, lỗi TLS, kết nối bị từ chối và các vấn đề authorization. Không trả nguyên `exception.getMessage()`: diagnostic của LDAP có thể chứa DN, hostname hoặc thông tin hạ tầng.

### 13.2. Không che tình huống partial result

| Tình huống | Hành vi mong muốn |
| --- | --- |
| Query trả 7 entry, limit 25, không có lỗi | Có thể trả 7 entry; trong phạm vi Search đã thực thi, không chạm limit. |
| Query trả 25 entry, limit 25, không có lỗi | Trả dữ liệu với `mayBeTruncated=true`; chưa biết có entry thứ 26. |
| Server báo size limit vượt | Không âm thầm tuyên bố đầy đủ; trả lỗi hoặc chỉ trả partial nếu API định nghĩa rõ. |
| Server báo time limit vượt | Không biến thành `[]`; trả lỗi/partial theo chính sách. |
| Referral chưa được theo | Không đánh dấu kết quả liên vùng là đầy đủ. |
| ACL che entry | Không suy luận “không tồn tại” chỉ từ kết quả rỗng. |

## 14. Bốn giới hạn cần thiết kế cùng nhau

Chỉ đặt count/time chưa đủ. Một thiết kế tìm kiếm hiệu quả cần kết hợp:

~~~mermaid
flowchart LR
    A["Danh bạ LDAP"] --> B["Base + Scope"]
    B --> C["Filter có chọn lọc"]
    C --> D["Attribute projection"]
    D --> E["Count + Search time limit"]
    E --> F["Timeout mạng + HTTP deadline"]
    F --> G["Result DTO + trạng thái completeness"]
~~~

### 14.1. Giới hạn base DN

Nếu ứng dụng chỉ quản lý `ou=people`, Search không cần bắt đầu từ `dc=example,dc=org` khi có cả nhóm, service account và OU khác. Việc thu hẹp base còn giúp thực thi ACL và chính sách dữ liệu.

### 14.2. Giới hạn scope

`ONELEVEL` phù hợp khi các entry người dùng nằm ngay dưới `ou=people`. `SUBTREE` dành cho cấu trúc có OU con, nhưng cần kiểm tra index và trần tài nguyên.

### 14.3. Filter chính xác và có index

- Dùng `(&(objectClass=inetOrgPerson)(uid=lan))` cho tìm kiếm mã người dùng cụ thể.
- Với search theo họ, `(sn=Nguyen)` có thể có nhiều kết quả; cần count/time limit.
- Prefix/wildcard như `(cn=Ng*)` dễ trả nhiều entry hơn equality; muốn cho phép phải có chính sách cụ thể.
- Index LDAP trên `uid`, `cn`, `sn` hoặc thuộc tính được tìm thường xuyên có thể giảm thời gian; index phụ thuộc khả năng/cấu hình directory.

Không vì muốn tăng tốc mà gửi trực tiếp raw filter do HTTP client cung cấp. Dùng `LdapQueryBuilder.where(...).is(...)` hoặc filter class để escape giá trị theo RFC 4515.

### 14.4. Attribute projection

~~~java
.attributes("uid", "cn", "sn", "mail")
~~~

giúp giảm payload và tránh ánh xạ thuộc tính không sử dụng. Nhưng nó **không phải cơ chế bảo mật thay ACL**: Bind account vẫn phải có quyền đọc đúng tập thông tin được phê duyệt, và service cần chuyển sang DTO công khai.

## 15. Khi nào cần Simple Paged Results Control?

Giả sử một công cụ quản trị được phép **duyệt 20.000 nhân viên**. Đặt `countLimit(50)` rồi gọi lại giống hệt 400 lần **không phải paging**.

LDAP có cơ chế tùy chọn **Simple Paged Results Control** (RFC 2696): client yêu cầu kích thước trang, server trả entry và một **cookie** để tiếp tục truy vấn. Client gửi cookie đó trong request tiếp theo cho tới khi server báo hết.

~~~mermaid
sequenceDiagram
    participant C as Spring LDAP client
    participant D as LDAP server
    C->>D: Search + paged control(size=50, cookie=rỗng)
    D-->>C: Trang 1 + cookie A
    C->>D: Search + paged control(size=50, cookie A)
    D-->>C: Trang 2 + cookie B
    C->>D: Search + paged control(size=50, cookie B)
    D-->>C: Trang cuối + cookie rỗng
    Note over C: Tổng số chỉ đầy đủ sau khi mọi trang thành công
~~~

### 15.1. Các quy tắc paging

- Directory phải **hỗ trợ control** tương ứng; không phải server nào cũng hỗ trợ như nhau.
- Cookie do server trả về là trạng thái điều khiển **opaque**: không tự giải mã, sửa hoặc coi là số trang.
- Cần giữ **cùng underlying LDAP connection** trong chuỗi yêu cầu paging khi processor/provider của Spring LDAP yêu cầu; tài liệu Spring LDAP nêu cách dùng `SingleContextSource`.
- Mỗi trang phải chịu giới hạn tài nguyên, số lần gọi, timeout và quyền ACL.
- Nếu directory thay đổi giữa các trang, paging thông thường **không bảo đảm snapshot nhất quán**.
- Không lưu/đưa cookie vào log công khai; nếu lộ qua HTTP, cần đóng gói/ký/ràng buộc với filter, caller, scope và thời hạn theo chính sách.
- Khi mất kết nối hoặc hết hạn cookie, không tự đánh dấu quá trình đồng bộ hoàn tất; cần retry/khởi động lại theo quy trình đã thiết kế.

Spring LDAP có các lớp hỗ trợ paged search (chẳng hạn `PagedResultsDirContextProcessor` hoặc API tương ứng trong tài liệu phiên bản đang dùng). **Tên lớp, tình trạng deprecated và chữ ký processor thay đổi theo version**; hãy đối chiếu documentation của Spring LDAP đang cài trước khi sao chép ví dụ phân trang.

### 15.2. countLimit và paging có thể tương tác

Không nên áp một `countLimit` tổng quá nhỏ rồi kỳ vọng paging đủ các trang. Server có thể kết hợp các giới hạn request, control và giới hạn quản trị theo cách khác nhau. Cần kiểm thử cụ thể:

1. Page size `50` và Search scope/filter.
2. Server limit cho toàn yêu cầu/phiên.
3. Cookie sau mỗi trang.
4. Lỗi size/time limit trên một trang.
5. Tổng số entry thu được và khả năng đếm trùng khi dữ liệu biến đổi.

**Không dùng `countLimit` để thay `pageSize`.** Hai tham số mang ngữ nghĩa khác nhau.

## 16. Truy vấn qua Spring Data LDAP Repository có tự áp giới hạn không?

Một entity thường dùng:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    // Getter/setter trong ứng dụng thực tế.
}
~~~

Repository:

~~~java
import java.util.List;

import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findBySurname(String surname);
}
~~~

Ở entity này, tên field Java `surname` được ánh xạ sang thuộc tính LDAP `sn`; các phương thức derived query có thể dựa vào mapping đó.

**Không mặc định suy luận rằng mọi repository method đều tự có count/time limit, phân trang hoặc timeout HTTP.** Cách Spring Data LDAP thực thi và tính năng repository tùy phiên bản. Với endpoint yêu cầu kiểm soát Search chính xác, có thể dùng `LdapTemplate` tường minh như mục 12 hoặc thiết kế repository configuration có giới hạn mặc định và kiểm thử wiring.

Nếu `LdapTemplate` có các default được áp cho repository, vẫn cần xác nhận repository thực sự dùng **đúng template/ContextSource**, nhất là khi hệ thống có nhiều LDAP server hoặc nhiều tài khoản Bind.

### Khi nào dùng repository và khi nào dùng LdapTemplate?

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Lấy một entity theo DN/định danh đã biết | Repository hoặc `LdapTemplate.findByDn`. |
| Query danh bạ cần base/scope/count/time/attribute rõ ràng | `LdapQueryBuilder` với `LdapTemplate.search`. |
| Search lấy tập rất lớn | Paged Results Control/luồng xử lý chuyên biệt. |
| CRUD entry theo entity | Repository/ODM, có schema và ACL phù hợp. |
| Điều khiển LDAP cấp thấp, custom controls | `LdapTemplate`/JNDI với API được hỗ trợ. |

## 17. Phân biệt giới hạn Search với giới hạn UI/API

Một yêu cầu HTTP từ client:

~~~http
GET /api/v1/people?sn=Nguyen&limit=1000000
~~~

không nên được chuyển thẳng thành `.countLimit(1_000_000)`.

Chính sách gợi ý:

- Đặt trần server-side, ví dụ **50 người/request** cho tra cứu tương tác.
- Trả **400 Bad Request** nếu client yêu cầu ngoài khoảng cho phép hoặc áp clamp rõ ràng trong hợp đồng.
- Giới hạn độ dài/chất lượng của điều kiện tìm kiếm, tránh filter quá rộng.
- Không cho client tự đặt `baseDn`, `searchScope` hoặc timeout vô hạn.
- Áp authentication/authorization HTTP, rate limiting và bảo vệ chống scraping danh bạ.
- Dùng DTO chỉ chứa thuộc tính công khai; không trả DN, mật khẩu hay data nội bộ không cần thiết.
- Gắn request ID cho lỗi; không lộ Bind DN hoặc LDAP diagnostic từ server.

### Nếu muốn hiển thị “đang có bao nhiêu người”?

`countLimit` không phải câu lệnh đếm toàn bộ. Nếu UI cần tổng số chính xác, phải có thiết kế tính toán riêng, cân nhắc chi phí, độ trễ và chính sách bảo vệ dữ liệu. Không dùng `items.size()` sau khi cắt tại 50 làm `totalCount` chính xác.

## 18. Kiểm tra trực tiếp bằng ldapsearch

Trong một directory test, có thể dùng LDAP CLI để đối chiếu với Spring LDAP. Giả định service account `cn=svc-reader,ou=service,dc=example,dc=org` có quyền Search trong `ou=people` và server hỗ trợ LDAPS.

### 18.1. Giới hạn số entry và thời gian

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  -z 10 -l 3 \
  "(&(objectClass=inetOrgPerson)(sn=Nguyen))" \
  dn uid cn sn mail
~~~

Trong OpenLDAP `ldapsearch`:

- `-z 10`: yêu cầu size limit **10 entry**.
- `-l 3`: yêu cầu time limit **3 giây**.
- `-s one`: chỉ entry con trực tiếp của base.
- `-W`: nhập mật khẩu an toàn hơn so với đưa password trực tiếp trên command line.

**So sánh đơn vị:** `ldapsearch -l 3` là **3 giây**, trong khi Spring LDAP dùng `.timeLimit(3_000)` là **3.000 mili giây**. Cả hai nhắm đến khoảng thời gian danh nghĩa tương đương, nhưng provider/server có thể xử lý khác nhau.

### 18.2. Thử giới hạn nhỏ hơn số người phù hợp

Nếu fixture có ít nhất 20 người cùng họ `Nguyen`:

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  -z 3 \
  "(&(objectClass=inetOrgPerson)(sn=Nguyen))" \
  dn uid cn
~~~

Kết quả có thể xuất hiện một số entry và cuối cùng là trạng thái giới hạn kích thước. **Không bắt buộc mọi server đều biểu diễn cùng một dòng lỗi**, nên cần đọc cả exit status/diagnostic và các entry đã nhận.

### 18.3. Thử search scope

Nếu có `uid=mai,ou=engineering,ou=people,dc=example,dc=org`, so sánh:

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(uid=mai)" dn uid
~~~

với `-s sub`. ONELEVEL không thấy entry ở OU cháu, còn SUBTREE có thể thấy nếu ACL và filter cho phép. Không đổ lỗi cho count/time khi thực chất search scope sai.

## 19. Kiểm thử tích hợp với directory có fixture lớn

Để xác minh limit, dùng server LDAP thử nghiệm có schema `inetOrgPerson` và tạo một tập dữ liệu có kiểm soát (ví dụ 120 entry có cùng `sn` dưới `ou=people`).

### 19.1. Bộ ca kiểm thử

| Test case | Kỳ vọng |
| --- | --- |
| 5 entry phù hợp, `countLimit=50` | Có thể trả cả 5 nếu không có lỗi; không chạm trần. |
| 120 entry phù hợp, `countLimit=50` | Không nhận quá 50 entry; có thể có exception tùy cấu hình. |
| Đúng 50 entry phù hợp, `countLimit=50` | Không kết luận chắc chắn còn kết quả; kiểm tra cờ giới hạn. |
| Server admin limit nhỏ hơn client limit | Nhận giới hạn của server; không tăng client limit để vượt policy. |
| `timeLimit=2_000` | Xác nhận giá trị truyền đúng đơn vị; kết quả tùy tốc độ server. |
| Search thực sự lâu hơn giới hạn server | Nếu server báo timeout, không trả dữ liệu như hoàn tất. |
| Search base không tồn tại | Phân biệt `noSuchObject` với 0 entry phù hợp. |
| ONELEVEL dưới `ou=people` | Không thấy entry ở OU cháu. |
| SUBTREE dưới `ou=people` | Có thể thấy entry ở OU cháu theo ACL. |
| Client truyền limit=0 hoặc >50 | Service từ chối trước khi gọi LDAP. |
| Client truyền filter injection | Giá trị được escape hoặc validation từ chối. |
| Reader account không có quyền đọc một thuộc tính | Không trả thuộc tính đó; không nâng quyền. |
| Referral không được xử lý | Không đánh dấu kết quả là đầy đủ. |
| Server dừng trước request | Lỗi kết nối, không coi là Search rỗng. |
| TLS certificate sai | Kết nối thất bại, không fallback plaintext. |
| Read timeout nhỏ hơn thời gian server phản hồi | Lỗi tầng client/provider, không bịa `LDAP 3`. |
| HTTP request quá thời gian | Trả lỗi/timeout phù hợp và xử lý hủy tài nguyên. |
| Paged Results với nhiều trang | Đọc cookie đúng, không bỏ trang hoặc tự coi count limit là paging. |

### 19.2. Test giới hạn số bản ghi

Một ví dụ JUnit 5 với Spring Boot Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.SizeLimitExceededException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

@SpringBootTest
class BoundedSearchIntegrationTest {

    @Autowired LdapTemplate ldapTemplate;

    @Test
    void neverReturnsMoreThanConfiguredCount() {
        // Fixture có ít nhất 20 người sn=Nguyen.
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .countLimit(3)
                .timeLimit(2_000)
                .where("sn").is("Nguyen");

        try {
            List<String> results = ldapTemplate.search(
                    query,
                    (AttributesMapper<String>) attrs ->
                            (String) attrs.get("cn").get()
            );
            assertTrue(results.size() <= 3);
        } catch (SizeLimitExceededException expectedWhenNotIgnored) {
            // Một số cấu hình cố ý ném lỗi khi chạm limit.
            // Đây KHÔNG phải kết quả Search đầy đủ.
        }
    }
}
~~~

Test này xác minh **không trả nhiều hơn giới hạn**, đồng thời cho phép cấu hình strict ném exception. Tuy nhiên, để bảo đảm cơ chế xử lý lỗi đúng, bạn phải có **test riêng** cho đường exception/HTTP, thay vì chỉ bắt exception rồi coi mọi trường hợp là pass.

Nếu không đủ entry, test không thực sự kiểm chứng limit. Chuẩn bị fixture nhiều hơn trần và chạy bằng đúng Bind DN reader.

### 19.3. Test định tuyến lỗi HTTP

Viết kiểm thử MockMvc/handler:

- Request `limit=0` → HTTP 400 và không gọi LDAP.
- Request `limit=5000` → HTTP 400 và không gọi LDAP.
- Mock `SizeLimitExceededException` → lỗi `SEARCH_LIMIT_EXCEEDED`, **không** HTTP 200 với danh sách rỗng.
- Mock `TimeLimitExceededException` → lỗi `DIRECTORY_SEARCH_TIMEOUT`, không đưa diagnostic nội bộ ra ngoài.
- Đúng 50 entry → `mayBeTruncated=true`, không ghi `totalCount=50`.
- Khi server không sẵn sàng → response thuộc loại lỗi directory, không phải “người dùng không tồn tại”.

### 19.4. Kiểm thử timeout không nên phụ thuộc may rủi

Không nên dựng test “server phải phát `timeLimitExceeded` trong 1 ms” rồi cho rằng code sai nếu nó Search quá nhanh. LDAP wire time limit được mô tả bằng giây, việc xử lý trên JNDI/provider và server có thể có độ phân giải khác.

Muốn kiểm tra chính sách timeout:

1. Unit test kiểm tra `query.timeLimit() == 2_000`.
2. Test integration đo response trong môi trường có dữ liệu và tải đủ lớn; đừng yêu cầu thời gian chính xác từng mili giây.
3. Test riêng lỗi `TimeLimitExceededException` tại tầng service/handler.
4. Test lỗi connect/read timeout bằng điều kiện network giả lập có kiểm soát.
5. Không chạy fault injection trên directory của người dùng thật.

## 20. Các lỗi và hiểu lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| `.timeLimit(2)` với ý định 2 giây | Giới hạn ở tầng API chỉ 2 ms. | Dùng `.timeLimit(2_000)`. |
| `countLimit(0)` để “lấy hết an toàn” | Không có giới hạn do client đặt; server vẫn có limit. | Đặt trần phù hợp, dùng paging cho dữ liệu lớn. |
| Gọi lại cùng query nhiều lần để lấy “trang sau” | Có thể lặp lại cùng entry. | Dùng Paged Results Control/cookie nếu server hỗ trợ. |
| Bỏ qua `SizeLimitExceededException` rồi báo hoàn tất | Có thể dùng danh sách thiếu mà không biết. | Chọn policy strict hoặc trả tập có giới hạn rõ ràng. |
| Dùng `results.size()` làm tổng số directory | Đếm sai khi chạm cap hoặc còn trang. | Thiết kế count riêng theo yêu cầu. |
| Đặt `SearchScope.SUBTREE` ở gốc domain cho mọi API | Duyệt quá nhiều OU và entry. | Thu hẹp base/scope. |
| Chỉ dùng timeout Search | Kết nối/TLS/network vẫn có thể chậm. | Kết hợp connect/read timeout và deadline API. |
| Bật ignore partial result không suy nghĩ | Có thể mất entry ở vùng referral. | Đánh dấu partial hoặc xử lý topology an toàn. |
| Cho client gửi raw LDAP filter | Nguy cơ injection, truy vấn rộng. | `LdapQueryBuilder`, whitelist thuộc tính, validation. |
| Đòi server trả đủ bằng cách tăng limit vô hạn | Gây tải lớn, có thể vượt admin policy. | Index, filter, paging, batch. |
| Bắt mọi exception rồi trả `[]` | Che mất sự cố và gây quyết định nghiệp vụ sai. | Phân loại lỗi, fail closed khi cần dữ liệu đầy đủ. |
| Bỏ hết attribute projection | Payload lớn, có thể lộ thuộc tính không cần. | Chỉ chọn trường dùng trong DTO và kiểm soát ACL. |
| Chỉ kiểm tra trên fixture 2 entry | Không thể xác nhận limit/time. | Test với dữ liệu lớn và fault injection có kiểm soát. |
| Xem 50 entry được trả là 50 entry đầu theo thứ tự ổn định | LDAP Search không mặc định cam kết thứ tự. | Nếu cần thứ tự, dùng cơ chế sorting server/client có kiểm soát và test. |

## 21. Cân bằng giới hạn với bảo mật và khả năng vận hành

Giới hạn dữ liệu không chỉ để tăng tốc độ mà còn giảm nguy cơ **quét danh bạ và tiêu thụ tài nguyên**:

- Chỉ cho phép client đã xác thực, được phân quyền sử dụng endpoint Search.
- Rate limit, quota và giám sát truy vấn lặp lại/wildcard rộng.
- Bind bằng tài khoản **chỉ đọc**, ACL chỉ cấp thuộc tính được phép.
- Dùng **LDAPS** hoặc **StartTLS hoàn tất trước Simple Bind**, xác minh CA và hostname.
- Không để client chọn arbitrary base DN hoặc referral destination.
- Dùng query/filter builder để xử lý ký tự đặc biệt theo RFC 4515.
- Chỉ map những trường công khai sang DTO, không trả `userPassword`, metadata hoặc DN nhạy cảm.
- Quan sát tỉ lệ timeout, `sizeLimitExceeded`, `adminLimitExceeded` và truy vấn đạt cap; không log filter chứa dữ liệu riêng tư chưa xử lý.
- Tuning index LDAP nên có baseline trước/sau; tăng số lượng connection hoặc timeout vô hạn không phải lời giải cho filter không hiệu quả.

### Checklist triển khai

| Yêu cầu | Tiêu chí đạt |
| --- | --- |
| Count limit | Mọi Search công khai có trần khác 0 và không cho client tăng vô hạn. |
| Search time | `timeLimit` truyền đúng **mili giây** ở Java. |
| Network timeout | Connect/read timeout được kiểm tra với JDK/provider. |
| Application deadline | Có giới hạn tổng của HTTP request/workflow, độc lập với LDAP Search. |
| Base/scope | Chỉ tìm nhánh và tầng cần thiết. |
| Filter | Điều kiện hợp lệ, giá trị escape an toàn, có index khi phù hợp. |
| Projection | Chỉ yêu cầu các attribute thật sự cần trả. |
| ACL | Service account chỉ đọc được phần được phép. |
| Exception policy | Không bỏ qua size/time/partial lỗi khi hợp đồng cần dữ liệu đầy đủ. |
| Completeness | Kết quả đúng cap không bị khẳng định “đã lấy hết”. |
| Paging | Nếu duyệt nhiều trang, cookie và connection được xử lý đúng. |
| Observability | Có count/latency/error metrics, request ID và không log secret. |
| Integration tests | Có dữ liệu nhiều hơn cap và kịch bản server/network/ACL. |

## 22. Bài tập thực hành

**Bài 1 — Đơn vị timeout.** Viết hai đoạn Java tương đương ý định Search trong 3 giây bằng `LdapQueryBuilder` và `SearchControls`. Giải thích vì sao `ldapsearch -l 3` không dùng cùng con số đơn vị với `.timeLimit(3_000)`.

**Bài 2 — Kết quả bị giới hạn.** Tạo 120 entry `inetOrgPerson` cùng `sn=Nguyen` trong directory test. Thực hiện Search với `countLimit(50)`. Quan sát danh sách, mã/exception theo cấu hình template và giải thích tại sao không thể đặt `total=50`.

**Bài 3 — Ignore/strict.** So sánh `setIgnoreSizeLimitExceededException(true)` và `false` trên cùng directory. Nêu ưu/nhược của từng chế độ với UI tra cứu nhanh và job đồng bộ dữ liệu.

**Bài 4 — Search scope.** Chuyển một nhân viên vào `ou=engineering,ou=people`. So sánh ONELEVEL và SUBTREE; xác định base/scope hẹp nhất đáp ứng yêu cầu.

**Bài 5 — API giới hạn.** Xây controller `GET /api/v1/people?sn=...&limit=...`, chỉ nhận `limit` từ 1 đến 50. Khi client gửi 0/5000, API trả 400 trước khi chạm LDAP.

**Bài 6 — Timeout nhiều lớp.** Đặt `Search timeLimit=2_000`, connect timeout 2.000 ms và read timeout 4.000 ms. Giả lập server không phản hồi và phân biệt exception do LDAP server trả với lỗi socket mà client tự phát hiện.

**Bài 7 — Paging.** Thử Simple Paged Results Control với page size 25 trên directory có 120 người, đọc cookie tới khi kết thúc, kiểm tra không thiếu/trùng trong một môi trường không thay đổi. Sau đó chỉnh dữ liệu giữa hai trang và thảo luận tính nhất quán.

**Bài 8 — Bảo mật.** Viết filter equality theo `sn` từ HTTP input bằng `LdapQueryBuilder`, giới hạn Search đến `ou=people` và chọn bốn thuộc tính trả về. Chứng minh API không mở quyền đọc `userPassword` dù client yêu cầu.

## 23. Câu hỏi tự ôn tập

1. `SearchRequest.sizeLimit=0` có nghĩa LDAP server bắt buộc trả vô hạn entry không?
2. `countLimit` của Spring LDAP có phải SQL `LIMIT/OFFSET` không?
3. Tại sao `timeLimit(2000)` trong Java khác `SearchRequest.timeLimit=2000` trên wire?
4. `SearchControls.setTimeLimit` sử dụng đơn vị gì?
5. Tại sao một API có Search time limit vẫn cần connect và read timeout?
6. `ONELEVEL` và `SUBTREE` khác nhau thế nào khi người dùng nằm trong OU con?
7. Vì sao query trả đúng 50 entry với limit=50 chưa chứng minh còn trang tiếp theo?
8. Tại sao `LdapTemplate` có thể trả danh sách thiếu nếu cấu hình ignore-size-limit đang bật?
9. `sizeLimitExceeded (4)` có luôn xảy ra khi trả đúng số entry bằng cap không?
10. `timeLimitExceeded (3)` khác timeout TLS/TCP ở điểm nào?
11. `adminLimitExceeded (11)` thể hiện chính sách của client hay server?
12. Vì sao việc chọn `attributes("uid","cn","mail")` không thay thế ACL?
13. Vì sao không được coi `results.size()` của query giới hạn là tổng số chính xác?
14. Simple Paged Results Control dùng cookie để làm gì?
15. Paging có bảo đảm snapshot nhất quán khi entry thay đổi giữa các trang không?
16. Nếu gặp referral và client không theo, có thể coi Search trong toàn topology là đầy đủ không?
17. Những trường thông tin nào nên ghi vào metric/log mà không làm lộ dữ liệu cá nhân?
18. Cần kiểm thử điều gì để bảo đảm API không chờ vô hạn khi server không phản hồi?

**Ghi nhớ:** giới hạn Search nên được thiết kế theo **base + scope + filter + attributes + countLimit + timeLimit**, cộng thêm **connect/read timeout, HTTP deadline và chính sách kết quả chưa đầy đủ**. Trong Spring LDAP/JNDI, `timeLimit` dùng **mili giây**, còn LDAP SearchRequest dùng **giây**. **`countLimit` không phải phân trang**; khi đã chạm giới hạn hoặc có lỗi partial, đừng tuyên bố đã đọc đủ danh bạ.

### Tài liệu tham khảo

- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest.sizeLimit, timeLimit (giây), SearchResultDone và các resultCode.
- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696): phân trang LDAP bằng cookie.
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): `LdapQueryBuilder` và các tham số base/scope/count/time/attributes.
- [Spring LDAP — LdapQueryBuilder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html): `countLimit`, `timeLimit`, `attributes` và filter an toàn.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): default count/time/scope và `ignoreSizeLimitExceededException`.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): giới hạn mặc định của template.
- [Spring LDAP — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): Simple Paged Results, cookie và connection lifecycle.
- [Java SE — SearchControls API](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/SearchControls.html): `setCountLimit` và `setTimeLimit` (mili giây).
- [Oracle JNDI — Time Limit](https://docs.oracle.com/javase/tutorial/jndi/ops/timelimit.html): ý nghĩa timeout Search trong JNDI.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.ldap.base-environment` và các thuộc tính `spring.ldap.template.ignore-*`.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và ODM cho entity phân cấp.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): escape giá trị filter khi tìm kiếm.
