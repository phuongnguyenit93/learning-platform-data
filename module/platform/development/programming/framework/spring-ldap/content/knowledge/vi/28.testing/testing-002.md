# Kiểm thử LdapTemplate với context source giả lập

Trong **Spring LDAP**, `LdapTemplate` nhận `ContextSource` để tạo ngữ cảnh JNDI (`DirContext`), thực hiện tìm kiếm hoặc thao tác entry, sau đó giải phóng tài nguyên. Khi cần kiểm tra mã Java tạo truy vấn, gọi `LdapTemplate` và xử lý kết quả, không nhất thiết phải khởi động một LDAP server. Ta có thể **giả lập `ContextSource` và `DirContext`**, cung cấp các `SearchResult` ngay trong bộ nhớ, trong khi vẫn chạy `LdapTemplate` thật.

Bài học thuộc chương **Testing** của module **SPRING_LDAP**. Mục tiêu là tạo được kiểm thử đơn vị cho luồng tìm kiếm `LdapTemplate`, kiểm tra base DN, filter, scope, chuyển đổi kết quả và giải phóng tài nguyên. Các phần liên quan đến schema, xác thực, kết nối TLS, pooling, quyền truy cập, và hành vi của LDAP server thật vẫn cần kiểm thử tích hợp.

## 1. Phạm vi và kiến trúc của bài kiểm thử

Luồng hoạt động thông thường:

```text
DirectoryService / Repository
        │
        ▼
   LdapTemplate
        │
        ▼
  ContextSource
        │  getReadOnlyContext()
        ▼
    DirContext ─────► LDAP server
        │
        ▼
 NamingEnumeration<SearchResult>
        │
        ▼
  AttributesMapper / ContextMapper
        │
        ▼
  List<DTO>
```

Trong unit test, giữ **`LdapTemplate` thật** và thay hai thành phần giao tiếp JNDI bằng Mockito:

```text
DirectoryService / Repository thật
        │
        ▼
   LdapTemplate thật
        │
        ▼
ContextSource mock ─────► DirContext mock
                               │
                               ▼
                    SearchResult tạo trong JVM
                               │
                               ▼
                       Mapper thật → DTO
```

Như vậy ta kiểm tra được `LdapTemplate` thực sự gọi `DirContext.search(...)` với tham số nào, phần mapping trả về dữ liệu gì, và tài nguyên có được đóng hay không. Ta **không** kiểm tra server có chấp nhận filter, schema có trả về thuộc tính mong muốn hay bind/TLS có thành công hay không.

| Thành phần | Dùng thật hay giả lập? | Mục đích |
| --- | --- | --- |
| Lớp repository/service của ứng dụng | Thật | Kiểm thử hành vi nghiệp vụ |
| `LdapTemplate` | Thật | Kiểm thử cách điều phối lệnh JNDI và mapping |
| `ContextSource` | Mock | Cấp `DirContext` giả, không tạo socket |
| `DirContext` | Mock | Trả về kết quả tìm kiếm hoặc ném lỗi giả lập |
| `NamingEnumeration<SearchResult>` | Fixture trong bộ nhớ | Tái hiện tập kết quả và trạng thái đóng tài nguyên |
| `AttributesMapper` | Thật | Kiểm tra chuyển đổi thuộc tính sang DTO |

**Điều kiện ví dụ:** Java 17+, Spring LDAP Core, JUnit Jupiter (JUnit 5) và Mockito. Các lớp Java đặt trong package `com.example.ldap`. Khai báo dependency `org.springframework.ldap:spring-ldap-core`, `org.junit.jupiter:junit-jupiter` và `org.mockito:mockito-core`; dùng phiên bản do BOM của dự án quản lý hoặc khai báo phiên bản tương thích một cách tường minh. Nếu sử dụng Gradle, cần bật `useJUnitPlatform()` cho JUnit 5.

## 2. Xây dựng repository sử dụng LdapTemplate thật

Giả sử ứng dụng cần tìm người dùng dựa trên `uid` dưới `ou=people` và trả về mã cùng tên hiển thị. Ta đặt truy vấn trong repository và trả kết quả bằng record `Person`.

Tạo `src/main/java/com/example/ldap/PersonDirectory.java`:

```java
package com.example.ldap;

import java.util.List;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PersonDirectory {

    private final LdapTemplate ldapTemplate;

    public record Person(String uid, String fullName) {}

    public PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<Person> findByUid(String uid) {
        AttributesMapper<Person> mapper = (Attributes attrs) ->
                new Person(
                        (String) attrs.get("uid").get(),
                        (String) attrs.get("cn").get()
                );

        return ldapTemplate.search(
                query()
                        .base("ou=people")
                        .searchScope(SearchControls.SUBTREE_SCOPE)
                        .where("uid").is(uid),
                mapper
        );
    }
}
```

Ở đây:

- `query().base("ou=people")` xác định base DN tương đối với cấu hình `ContextSource` của ứng dụng.
- `searchScope(SearchControls.SUBTREE_SCOPE)` yêu cầu tìm trong cả cây con.
- `where("uid").is(uid)` tạo filter bằng query builder của Spring LDAP, có xử lý escape cho giá trị.
- `AttributesMapper<Person>` biến các thuộc tính trả về thành record `Person`.

Mapper trong ví dụ tập trung vào dữ liệu hợp lệ, giả định `uid` và `cn` tồn tại và là chuỗi. Trong dự án thật, cần có quy tắc rõ ràng với thuộc tính thiếu, rỗng, nhiều giá trị và kiểu `byte[]`; các trường hợp ấy nên có unit test mapper riêng. Việc dùng `LdapQueryBuilder` tránh ghép một filter LDAP từ input chưa escape.

## 3. Giả lập ContextSource và DirContext bằng Mockito

`ContextSource` là điểm cấp ngữ cảnh cho `LdapTemplate`. Với tác vụ đọc, `LdapTemplate` lấy context qua `getReadOnlyContext()`. Ta cho phương thức này trả về một `DirContext` mock:

```java
ContextSource contextSource = mock(ContextSource.class);
DirContext context = mock(DirContext.class);

when(contextSource.getReadOnlyContext()).thenReturn(context);

LdapTemplate ldapTemplate = new LdapTemplate(contextSource);
PersonDirectory directory = new PersonDirectory(ldapTemplate);
```

Không cần `LdapContextSource` thật, host, port, password hay một lệnh bind thực tế. Tuy nhiên chỉ mock `ContextSource` là chưa đủ: nếu `DirContext.search(...)` không được stub, Mockito thường trả về `null`, không phải một tập kết quả JNDI có thể duyệt. Cần tạo dữ liệu `SearchResult` và `NamingEnumeration` tương ứng.

### Fixture NamingEnumeration tái sử dụng

JNDI trả về `NamingEnumeration<SearchResult>` thay vì một `List`. Để tránh phụ thuộc vào cách Mockito mô phỏng chuỗi lần gọi `hasMore()` và `next()`, ta viết một fixture nhỏ hoạt động như một enumeration thực.

Đặt class sau **bên trong** class kiểm thử `PersonDirectoryTest` (được trình bày đầy đủ ở phần tiếp theo):

```java
private static final class InMemoryResults
        implements NamingEnumeration<SearchResult> {

    private final Iterator<SearchResult> iterator;
    boolean closed;

    InMemoryResults(SearchResult... entries) {
        iterator = List.of(entries).iterator();
    }

    @Override
    public boolean hasMore() {
        return iterator.hasNext();
    }

    @Override
    public SearchResult next() {
        return iterator.next();
    }

    @Override
    public boolean hasMoreElements() {
        return hasMore();
    }

    @Override
    public SearchResult nextElement() {
        return next();
    }

    @Override
    public void close() {
        closed = true;
    }
}
```

Fixture này đủ cho việc trả lần lượt từng entry, báo hết kết quả và ghi nhận `close()`. Đây là mô phỏng ở mức **JNDI API**, không phải một LDAP server giả có schema, index hay quy tắc matching.

## 4. Viết bộ kiểm thử JUnit 5

Tạo `src/test/java/com/example/ldap/PersonDirectoryTest.java`. Đoạn mã bên dưới là **file test hoàn chỉnh**, đã gồm fixture `InMemoryResults` ở trên.

```java
package com.example.ldap;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import javax.naming.Name;
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;

class PersonDirectoryTest {

    private ContextSource contextSource;
    private DirContext context;
    private PersonDirectory directory;

    @BeforeEach
    void setUp() {
        contextSource = mock(ContextSource.class);
        context = mock(DirContext.class);

        when(contextSource.getReadOnlyContext()).thenReturn(context);
        directory = new PersonDirectory(new LdapTemplate(contextSource));
    }

    @Test
    void returnsMappedPersonAndUsesExpectedSearchParameters()
            throws Exception {

        Attributes attributes = new BasicAttributes(true);
        attributes.put("uid", "u01");
        attributes.put("cn", "Nguyễn An");

        InMemoryResults results = new InMemoryResults(
                new SearchResult("uid=u01", null, attributes));

        when(context.search(
                any(Name.class),
                eq("(uid=u01)"),
                any(SearchControls.class)
        )).thenReturn(results);

        List<PersonDirectory.Person> actual = directory.findByUid("u01");

        assertEquals(
                List.of(new PersonDirectory.Person("u01", "Nguyễn An")),
                actual
        );

        ArgumentCaptor<Name> baseCaptor =
                ArgumentCaptor.forClass(Name.class);
        ArgumentCaptor<SearchControls> controlsCaptor =
                ArgumentCaptor.forClass(SearchControls.class);

        verify(context).search(
                baseCaptor.capture(),
                eq("(uid=u01)"),
                controlsCaptor.capture()
        );

        assertEquals(new LdapName("ou=people"), baseCaptor.getValue());
        assertEquals(
                SearchControls.SUBTREE_SCOPE,
                controlsCaptor.getValue().getSearchScope()
        );
        assertTrue(results.closed);
        verify(context).close();
    }

    @Test
    void returnsEmptyListWhenSearchHasNoMatches() throws Exception {
        InMemoryResults results = new InMemoryResults();

        when(context.search(
                any(Name.class),
                eq("(uid=missing)"),
                any(SearchControls.class)
        )).thenReturn(results);

        assertTrue(directory.findByUid("missing").isEmpty());
        assertTrue(results.closed);
        verify(context).close();
    }

    @Test
    void escapesUserSuppliedFilterValue() throws Exception {
        InMemoryResults results = new InMemoryResults();

        when(context.search(
                any(Name.class),
                anyString(),
                any(SearchControls.class)
        )).thenReturn(results);

        directory.findByUid("a*)(uid=*");

        ArgumentCaptor<String> filterCaptor =
                ArgumentCaptor.forClass(String.class);

        verify(context).search(
                any(Name.class),
                filterCaptor.capture(),
                any(SearchControls.class)
        );

        // Chuỗi đầu vào là một giá trị uid, không phải cú pháp filter.
        // Chuẩn hóa chữ hoa của ký tự hex để assert ít phụ thuộc biểu diễn.
        assertEquals(
                "(uid=a\\2a\\29\\28uid=\\2a)",
                filterCaptor.getValue().toLowerCase(Locale.ROOT)
        );
        assertTrue(results.closed);
        verify(context).close();
    }

    @Test
    void translatesJndiCommunicationFailureAndClosesContext()
            throws Exception {

        when(context.search(
                any(Name.class),
                anyString(),
                any(SearchControls.class)
        )).thenThrow(
                new javax.naming.CommunicationException("LDAP unavailable")
        );

        assertThrows(
                org.springframework.ldap.CommunicationException.class,
                () -> directory.findByUid("u01")
        );
        verify(context).close();
    }

    private static final class InMemoryResults
            implements NamingEnumeration<SearchResult> {

        private final Iterator<SearchResult> iterator;
        boolean closed;

        InMemoryResults(SearchResult... entries) {
            iterator = List.of(entries).iterator();
        }

        @Override
        public boolean hasMore() {
            return iterator.hasNext();
        }

        @Override
        public SearchResult next() {
            return iterator.next();
        }

        @Override
        public boolean hasMoreElements() {
            return hasMore();
        }

        @Override
        public SearchResult nextElement() {
            return next();
        }

        @Override
        public void close() {
            closed = true;
        }
    }
}
```

### Giải thích bốn ca kiểm thử

| Ca kiểm thử | Điều được xác minh | Nếu thất bại, nên kiểm tra |
| --- | --- | --- |
| Kết quả hợp lệ | Filter `(uid=u01)`, base `ou=people`, scope `SUBTREE_SCOPE`, mapper trả DTO đúng | Query builder, tên thuộc tính, cách tạo `SearchControls` |
| Không có kết quả | Trả danh sách rỗng, vẫn đóng enumeration/context | Cách duyệt `NamingEnumeration` và xử lý danh sách |
| Giá trị có ký tự filter | Các ký tự đặc biệt trong `uid` được escape trước khi giao cho JNDI | Mã ghép filter thủ công hoặc bỏ qua `LdapQueryBuilder` |
| Lỗi giao tiếp JNDI | `LdapTemplate` chuyển checked exception của JNDI thành exception Spring LDAP và đóng context | Stubbing `DirContext`, phân loại exception hoặc resource cleanup |

Cả bốn ca sử dụng `LdapTemplate` thật, nên kiểm tra được nhiều hơn một mock của `LdapOperations` chỉ trả DTO dựng sẵn. Mặt khác, vì `DirContext` là mock, kết quả tìm kiếm hoàn toàn do test quyết định, bất kể filter có thật sự khớp dữ liệu LDAP trên server hay không.

### Vì sao bắt tham số thay vì chỉ so sánh DTO?

Một kiểm thử chỉ khẳng định `List<Person>` có đúng một người có thể vẫn thành công khi repository tạo **sai** base DN hoặc scope, vì mock trả về dữ liệu do test chuẩn bị. `ArgumentCaptor<Name>` và `ArgumentCaptor<SearchControls>` cho phép kiểm tra lệnh tìm kiếm thực sự được tạo. Dùng `new LdapName("ou=people")` để so sánh DN có ý nghĩa cấu trúc; tránh tách DN thủ công bằng dấu phẩy.

Test filter dùng input chứa `*`, `(` và `)` để chỉ ra sự khác nhau giữa **giá trị** cần tìm và **cú pháp** filter. Tình huống có dấu gạch chéo ngược hoặc byte NUL cũng đáng bổ sung, đặc biệt với mã nhận filter value từ người dùng. Kiểm tra escape bằng mock giúp phát hiện lỗi dựng filter, nhưng không thay thế các phép thử trên schema và server thật.

## 5. Những điểm dễ gây sai lệch khi giả lập ContextSource

### Phân biệt phương thức đọc và ghi

Với các thao tác đọc như `search`, `LdapTemplate` sử dụng ngữ cảnh chỉ đọc từ `getReadOnlyContext()`. Với những thao tác thay đổi entry, phần cần giả lập có thể là `getReadWriteContext()` và các phương thức JNDI tương ứng như `bind`, `modifyAttributes` hoặc `unbind`. Không tái sử dụng nguyên trạng stub của phép tìm kiếm cho phép ghi rồi kết luận sai rằng mã production không gọi context.

### Chú ý overload của DirContext.search

JNDI cung cấp nhiều overload, chẳng hạn:

```java
NamingEnumeration<SearchResult> search(
        Name name, String filter, SearchControls controls);

NamingEnumeration<SearchResult> search(
        String name, String filter, SearchControls controls);

NamingEnumeration<SearchResult> search(
        Name name, String filterExpr, Object[] filterArgs,
        SearchControls controls);
```

Chúng là các phương thức khác nhau đối với Mockito. Ví dụ trong bài stub dạng `search(Name, String, SearchControls)`, phù hợp với đường gọi của `LdapTemplate` thông qua `Name`. Nếu thay cách gọi API hay phiên bản mã đang dùng, phải kiểm tra lại overload mà ứng dụng thực sự gọi. Một stub sai overload thường biểu hiện bằng kết quả `null` hoặc một lỗi khi duyệt enumeration, không phải lỗi LDAP server.

### Tạo SearchResult theo đúng dữ liệu mapper dùng

`new SearchResult("uid=u01", null, attributes)` cung cấp tên tương đối và các `Attributes`. Với `AttributesMapper` trong ví dụ, các thuộc tính là phần quan trọng. Nếu đổi sang `ContextMapper` và đọc DN từ `DirContextOperations`, cần xem xét cả base DN, tên của `SearchResult`, tính tương đối của tên (`isRelative`) và thông tin context được Spring LDAP dựng lại. Một mock chỉ đủ dữ liệu cho `AttributesMapper` có thể không đủ để kiểm thử DN trong `ContextMapper`.

### Tài nguyên cũng là hành vi cần kiểm tra

Sau tìm kiếm thành công hoặc hết kết quả, `LdapTemplate` có trách nhiệm đóng `NamingEnumeration` và trả/đóng `DirContext`. Khi xảy ra lỗi, context cũng cần được giải phóng. Các assertion `assertTrue(results.closed)` và `verify(context).close()` cho thấy mã đi qua nhánh dọn dẹp. Với pooling, gọi `close()` trên proxy có thể tương ứng với **trả context về pool**, vì thế kiểm thử mock chỉ xác minh lời gọi đóng, không xác minh vận hành thực tế của pool.

### Đừng để mock che đi lỗi cấu hình

Một `ContextSource` giả lập không có host, credentials, cấu hình TLS hoặc base suffix. Nếu code thực dùng `LdapContextSource` với base `dc=example,dc=org`, hãy hiểu rằng base `ou=people` trong unit test có thể là base tương đối; địa chỉ truy vấn đầy đủ do cấu hình môi trường và lớp context quyết định. Unit test kiểm tra phần do repository tạo; phép thử tích hợp kiểm tra đường đi đầy đủ đến thư mục.

## 6. Chọn loại kiểm thử phù hợp với mục tiêu

| Mục tiêu | Cách kiểm thử | Cần LDAP server? |
| --- | --- | --- |
| Quy tắc chuyển một `Attributes` thành DTO | Gọi `AttributesMapper` trực tiếp với `BasicAttributes` | Không |
| Repository tạo query và map kết quả qua `LdapTemplate` | `LdapTemplate` thật + `ContextSource`/`DirContext` mock | Không |
| Service xử lý kết quả từ repository | Mock repository hoặc `LdapOperations` tại ranh giới service | Không |
| Filter, schema, scope có trả đúng entry trong thư mục | Integration test với LDAP phục vụ kiểm thử | Có |
| Xác thực, quyền đọc/ghi, LDAPS/StartTLS, pooling, referral | Integration test với cấu hình LDAP phù hợp | Có |
| ODM thực sự ánh xạ annotation và ghi/đọc entry | Kiểm thử tích hợp đường ODM (hoặc hạ tầng chuyên dụng của ODM) | Thường có |

Không nên gọi kiểm thử có `ContextSource` mock là *integration test với LDAP*: nó không mở kết nối mạng. Đồng thời không cần khởi chạy Spring ApplicationContext cho ví dụ này vì constructor injection của `LdapTemplate` và repository đã đủ để ghép các thành phần vào bài test. Nếu ứng dụng có cấu hình bean phức tạp, hãy kiểm thử cấu hình ở một lớp riêng.

## 7. Bài tập thực hành

1. Bổ sung trường `mail` vào record `Person`; quyết định giá trị khi thuộc tính này vắng mặt rồi thêm unit test.
2. Thêm hai `SearchResult` vào `InMemoryResults` và xác minh `findByUid` trả đúng hai DTO theo thứ tự enumeration cung cấp (trong khi lưu ý server không bảo đảm thứ tự nếu không có cơ chế sắp xếp riêng).
3. Sửa repository tạm thời từ `SUBTREE_SCOPE` sang `ONELEVEL_SCOPE`; quan sát assertion của `SearchControls` phát hiện thay đổi.
4. Tạo một `SearchResult` thiếu `cn` để quan sát lỗi mapping và xác định contract lỗi phù hợp cho ứng dụng.
5. Viết integration test với LDAP test server, cùng dữ liệu fixture, để xác nhận filter, base DN, schema và các quyền truy cập thực tế.

**Tiêu chí hoàn thành:** người học có thể giải thích ranh giới giữa `ContextSource` mock và LDAP server thật, dựng được `SearchResult` cùng `NamingEnumeration` trong bộ nhớ, kiểm thử đường gọi `LdapTemplate` với Mockito/JUnit 5, xác nhận filter và phạm vi tìm kiếm, kiểm tra đóng tài nguyên, rồi chỉ ra những hành vi còn phải xác minh bằng integration test.

