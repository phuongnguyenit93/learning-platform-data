# LDAP controls và matching rule đặc thù

Khi một ứng dụng tìm kiếm hoặc cập nhật entry LDAP, filter thông thường chỉ mô tả điều kiện chọn dữ liệu. Trong nhiều tình huống, ứng dụng còn cần yêu cầu server **phân trang kết quả, sắp xếp ở phía server, kiểm tra một điều kiện trước khi ghi, trả về entry trước/sau khi cập nhật, đọc object đã xóa hoặc đánh giá một phép so sánh đặc biệt**. LDAP cung cấp hai cơ chế để mở rộng những nhu cầu này: **controls** gắn với operation và **matching rules** dùng trong filter/compare.

Hai cơ chế này có vai trò khác nhau. **LDAP control** là metadata đi kèm một LDAP message để thay đổi hoặc bổ sung hành vi của operation. **Matching rule** xác định cách server so sánh attribute value với assertion value, ví dụ so sánh không phân biệt hoa thường, so sánh số nguyên hoặc kiểm tra bit flag. Matching rule có thể được gọi bằng OID trong extensible match filter.

Trong module **SPRING_DATA_LDAP**, người học cần biết Spring LDAP truyền/nhận control qua **DirContextProcessor**, cách kiểm tra khả năng server qua Root DSE và schema, cũng như cách tách phần portable theo RFC khỏi phần riêng của OpenLDAP, Active Directory và từng phiên bản server.

> **Quy tắc triển khai:** Không giả định hai LDAP server hỗ trợ cùng OID hoặc cùng ngữ nghĩa. Hãy discovery capability, kiểm tra criticality và response control, rồi kiểm thử trên đúng server/version sẽ triển khai.

## 1. Phân biệt LDAP control và matching rule

| Cơ chế | Gắn ở đâu? | Dùng để làm gì? | Ví dụ |
| --- | --- | --- | --- |
| **Request control** | LDAP request message | Yêu cầu server thực hiện thêm hành vi | Simple paged results, server-side sort |
| **Response control** | LDAP response message | Trả kết quả/trạng thái của control | Sort result, paging cookie |
| **Matching rule** | Filter assertion hoặc Compare operation | Quy định phép so sánh attribute với assertion | **caseIgnoreMatch**, **integerMatch** |
| **Extensible match** | Một nhánh của Search filter | Gọi matching rule cụ thể bằng tên/OID | AD bitwise AND, transitive membership |

Ví dụ:

~~~text
Request control:
  SearchRequest + PagedResultsControl
  -> server trả một trang và cookie

Matching rule:
  (userAccountControl:1.2.840.113556.1.4.803:=2)
  -> server kiểm tra bit 0x2 có được đặt hay không
~~~

Control không phải một phần của filter text. Matching rule cũng không phải một request control. Hai cơ chế có thể cùng xuất hiện trong một SearchRequest, nhưng mỗi cơ chế vẫn giữ hợp đồng riêng.

## 2. Cấu trúc control trong LDAPv3

Theo RFC 4511, một LDAP message có thể mang một hoặc nhiều control. Một control gồm:

| Trường | Ý nghĩa |
| --- | --- |
| **controlType** | OID dạng dotted-decimal định danh control |
| **criticality** | Cho biết operation có được phép tiếp tục nếu không áp dụng control hay không |
| **controlValue** | OCTET STRING chứa dữ liệu control theo định dạng do specification của OID quy định |

Client gửi **request control** trong LDAP request. Server có thể trả **response control** trong LDAP response. Một request control có thể có response control cùng OID hoặc một OID riêng, tùy specification.

Một control chỉ ảnh hưởng LDAP message mà nó được gắn vào. Ví dụ control gắn vào SearchRequest không tự động áp dụng cho BindRequest kế tiếp. Nếu cần dùng control cho nhiều lần search, ứng dụng phải gửi lại control cho từng request theo đúng API.

### 2.1. OID và controlValue

OID là định danh duy nhất của loại control. **controlValue** không phải chuỗi tùy ý: specification có thể yêu cầu BER-encoded ASN.1, byte cookie, integer hoặc không có value. Client không được tự đoán cấu trúc value từ OID.

Ví dụ một số OID thường gặp:

| Control | OID | Specification/nhà cung cấp |
| --- | --- | --- |
| Simple Paged Results | **1.2.840.113556.1.4.319** | RFC 2696 |
| Server-side Sort request | **1.2.840.113556.1.4.473** | RFC 2891 |
| Server-side Sort response | **1.2.840.113556.1.4.474** | RFC 2891 |
| Assertion Control | **1.3.6.1.1.12** | RFC 4528 |
| Pre-Read | **1.3.6.1.1.13.1** | RFC 4527 |
| Post-Read | **1.3.6.1.1.13.2** | RFC 4527 |
| ManageDsaIT | **2.16.840.1.113730.3.4.2** | LDAPv3 control |

Các OID trong bảng là định danh protocol; việc server có triển khai chúng hay không vẫn phải kiểm tra.

## 3. Criticality quyết định cách xử lý khi server không hỗ trợ

Trường **criticality** có ý nghĩa đặc biệt với request control:

- **criticality = TRUE**: nếu server không nhận ra control, không áp dụng được control hoặc không chấp nhận control cho operation đó, server **không được thực hiện operation** và phải trả **unavailableCriticalExtension**.
- **criticality = FALSE** hoặc bỏ trống: server có thể bỏ qua control không được hỗ trợ và tiếp tục operation theo hành vi thông thường.

Điều này ảnh hưởng trực tiếp đến tính đúng đắn của ứng dụng. Nếu yêu cầu nghiệp vụ chỉ đúng khi server sort kết quả, gửi sort control dạng non-critical rồi nhận một danh sách chưa sort có thể làm ứng dụng xử lý sai. Nếu control chỉ tối ưu hiệu năng và fallback vẫn đúng, non-critical có thể phù hợp.

### 3.1. Không suy ra control đã được áp dụng chỉ từ SearchResult

Một SearchRequest có thể thành công nhưng server bỏ qua control non-critical. Một số control còn trả response control chứa kết quả riêng, độc lập với result code của operation. Vì vậy:

- Kiểm tra response control nếu specification có định nghĩa.
- Với server-side sort, đọc **SortResponseControl** và xác nhận **resultCode** là success.
- Với paged results, kiểm tra response cookie và trạng thái còn trang.
- Ghi nhận trường hợp response control bị thiếu hoặc server không trả control như mong đợi.

### 3.2. Không ghép tùy tiện nhiều control

Một LDAP message có thể mang nhiều control, nhưng mọi tổ hợp không mặc nhiên hợp lệ. Nếu specification không định nghĩa cách phối hợp hoặc thứ tự xử lý, server có thể trả **protocolError**. Đặc biệt khi kết hợp paging, sort, VLV và các control riêng máy chủ, phải đọc quy tắc phối hợp của từng RFC/vendor.

## 4. Discovery capability qua Root DSE và subschema

Không nên chọn control hoặc matching rule dựa trên tên sản phẩm LDAP. Hãy truy vấn Root DSE trước khi bật tính năng.

### 4.1. Root DSE cung cấp những gì?

Root DSE là entry đặc biệt tại base DN rỗng. Các attribute operational thường hữu ích:

| Attribute | Thông tin |
| --- | --- |
| **supportedLDAPVersion** | Phiên bản LDAP được hỗ trợ |
| **supportedControl** | Các control OID server công bố |
| **supportedExtension** | Các extended operation được hỗ trợ |
| **supportedFeatures** | Các protocol feature OID |
| **supportedSASLMechanisms** | Cơ chế SASL được hỗ trợ |
| **namingContexts** | Các naming context/base DN do server phục vụ |
| **subschemaSubentry** | DN của subschema entry để tra cứu schema |

**supportedExtension** là danh sách extended operation, không phải control. **supportedControl** cũng không phải danh sách matching rule.

### 4.2. Truy vấn Root DSE bằng ldapsearch

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.test:636 \
  -b "" -s base "(objectClass=*)" \
  supportedLDAPVersion supportedControl supportedExtension \
  supportedFeatures supportedSASLMechanisms namingContexts \
  subschemaSubentry
~~~

Ví dụ kết quả có thể chứa:

~~~text
dn:
supportedLDAPVersion: 3
supportedControl: 1.2.840.113556.1.4.319
supportedControl: 1.3.6.1.1.12
supportedControl: 1.3.6.1.1.13.1
supportedControl: 1.3.6.1.1.13.2
subschemaSubentry: cn=Subschema
~~~

Đây chỉ là ví dụ minh họa; OID thực tế phụ thuộc server, phiên bản, cấu hình và backend.

### 4.3. Tra cứu matching rule trong schema

Nếu Root DSE trả **subschemaSubentry**, đọc các attribute schema tại DN đó:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.test:636 \
  -b "cn=Subschema" -s base "(objectClass=subschema)" \
  matchingRules matchingRuleUse attributeTypes
~~~

Thay **cn=Subschema** bằng đúng DN được trả trong **subschemaSubentry**. Trong schema:

- **matchingRules** mô tả OID, tên và assertion syntax của matching rule.
- **matchingRuleUse** mô tả những attribute type phù hợp để dùng rule trong extensibleMatch.
- **attributeTypes** khai báo syntax cùng các rule mặc định **EQUALITY**, **ORDERING**, **SUBSTR**.

Một số server không công bố đầy đủ schema hoặc không cho phép anonymous đọc subschema. Khi đó cần dùng tài liệu server, tài khoản được cấp quyền đọc schema và integration test.

### 4.4. Matching rule không nhất thiết được quảng bá ở Root DSE

RFC 4512 định nghĩa subschema và **matchingRuleUse**, nhưng Active Directory không cung cấp attribute Root DSE để liệt kê các matching rule được hỗ trợ. Với AD, cần đối chiếu tài liệu theo phiên bản DC/AD DS/AD LDS và kiểm thử filter thực tế. Không lấy việc một OID xuất hiện trong **supportedControl** làm bằng chứng matching rule cùng OID có tồn tại.

## 5. Dùng controls trong Spring LDAP

Spring LDAP tích hợp control vào search qua **DirContextProcessor**. **LdapTemplate** gọi:

1. **preProcess(ctx)** trước khi thực hiện search để gắn request control.
2. Thực hiện search và duyệt hết **NamingEnumeration**.
3. **postProcess(ctx)** sau search để lấy response control.

Ví dụ chữ ký rút gọn:

~~~java
public interface DirContextProcessor {
    void preProcess(DirContext ctx) throws NamingException;
    void postProcess(DirContext ctx) throws NamingException;
}
~~~

Khi dùng LDAPv3 controls, cấu hình **LdapContextSource** để operation nhận **LdapContext**. Spring LDAP yêu cầu **LdapContext** vì JNDI Control API thuộc LDAPv3; một context chỉ là **DirContext** thông thường sẽ không đủ.

### 5.1. Search có processor

~~~java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[]{"uid", "cn", "mail"});

List<Person> people = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    controls,
    personAttributesMapper,
    dirContextProcessor
);
~~~

**dirContextProcessor** được gọi trước và sau operation. Không giữ context hoặc response control trong một singleton mutable processor cho nhiều search đồng thời; tạo processor/exchange riêng cho từng operation, trừ khi API cụ thể được thiết kế bất biến và có lifecycle rõ ràng.

### 5.2. Control trên update operation

**DirContextProcessor** được gọi quanh search. Với control gắn vào Modify/Delete/ModifyDN, có thể dùng callback **LdapTemplate.executeReadWrite(...)** để thao tác trên **LdapContext**. Request control phải được tạo với controlValue đúng định dạng của RFC/vendor; riêng Assertion Control yêu cầu BER-encoded LDAP Filter. Không truyền filter text thuần làm controlValue.

Ví dụ dưới đây minh họa vòng đời JNDI khi adapter đã tạo **javax.naming.ldap.Control** đúng OID và BER value theo RFC 4528. JNDI **BasicControl** có thể bọc byte BER do encoder LDAP chuyên dụng tạo ra; không đưa filter text thuần vào byte array:

~~~java
import java.util.Arrays;
import javax.naming.ldap.BasicControl;
import javax.naming.ldap.Control;
import javax.naming.ldap.LdapContext;

Control assertionControl = new BasicControl(
    "1.3.6.1.1.12", true, assertionControlValueBer
);

ldapTemplate.executeReadWrite(ctx -> {
    LdapContext ldapContext = (LdapContext) ctx;
    Control[] previous = ldapContext.getRequestControls();
    Control[] requestControls;

    if (previous == null || previous.length == 0) {
        requestControls = new Control[]{assertionControl};
    } else {
        requestControls = Arrays.copyOf(
            previous, previous.length + 1
        );
        requestControls[previous.length] = assertionControl;
    }

    try {
        ldapContext.setRequestControls(requestControls);
        ldapContext.modifyAttributes(relativeDn, modifications);
        return null;
    } finally {
        // Tránh để control của operation này ảnh hưởng lần mượn context sau.
        ldapContext.setRequestControls(previous);
    }
});
~~~

**assertionControl**, **relativeDn** và **modifications** là dữ liệu đã được ứng dụng chuẩn bị; đoạn code không tự encode Assertion Control. Assertion Control theo RFC 4528 **không có response control**: nếu assertion sai hoặc undefined, server trả result code **assertionFailed (122)** và không thực hiện update. Khi dùng connection pool, việc khôi phục request controls trước khi context được trả về pool là đặc biệt quan trọng. Với các control khác có response control, đọc response ngay trong callback và kiểm tra đúng OID/result.

### 5.3. Spring LDAP 4.1 trở lên

Spring LDAP 4.1 bổ sung abstraction **ControlExchange** và **ControlExchangeDirContextProcessor** để ghép request control với response control. Các lớp chuyên dụng gồm:

- **PagedResultsControlExchangeDirContextProcessor**
- **PagedResultsControlExchange**
- **SortControlExchange**

**SortControlDirContextProcessor** và một số processor cũ đã deprecated; với phiên bản mới, ưu tiên **ControlExchangeDirContextProcessor** cùng **SortControlExchange**. Nếu project dùng Spring LDAP 3.x hoặc 4.0, API có thể khác; hãy theo đúng BOM/version đang chạy.

## 6. Simple Paged Results: chia search thành nhiều trang

Simple Paged Results theo RFC 2696 dùng control OID **1.2.840.113556.1.4.319**. Client gửi page size và cookie; server trả một phần kết quả cùng cookie để lấy trang kế tiếp. Cookie là dữ liệu opaque: client không đọc hoặc tự sửa nội dung.

Paging giúp kiểm soát kích thước response và memory. Nó không phải phân trang ngẫu nhiên kiểu SQL OFFSET, không tự tạo snapshot nhất quán cho toàn bộ directory và không đảm bảo mọi server giữ cùng một tập kết quả nếu directory thay đổi giữa các trang.

### 6.1. Ví dụ paging bằng Spring LDAP 4.1+

~~~java
List<Person> getAllPeople() {
    SearchControls searchControls = new SearchControls();
    searchControls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    searchControls.setReturningAttributes(new String[]{"uid", "cn"});

    PagedResultsControlExchangeDirContextProcessor processor =
        new PagedResultsControlExchangeDirContextProcessor(200);

    return SingleContextSource.doWithSingleContext(
        contextSource,
        operations -> {
            List<Person> result = new LinkedList<>();
            do {
                List<Person> page = operations.search(
                    "ou=people",
                    "(&(objectClass=inetOrgPerson))",
                    searchControls,
                    personAttributesMapper,
                    processor
                );
                result.addAll(page);
            } while (processor.hasMore());
            return result;
        }
    );
}
~~~

Ví dụ giả định **contextSource** và **personAttributesMapper** là dependency của service. Các biến **searchControls** và **processor** được tạo riêng trong mỗi lần gọi; không dùng chung cookie của hai request.

### 6.2. Paging cần cùng connection

Cookie của paged results tiếp tục trạng thái server trên connection. Spring LDAP yêu cầu dùng cùng underlying connection giữa các trang. **SingleContextSource.doWithSingleContext(...)** hoặc transaction-aware context có thể giữ connection trong toàn bộ chuỗi. Không mở một context mới cho từng trang rồi chuyển cookie cũ sang connection khác.

### 6.3. Điều cần kiểm tra

- Server có công bố/triển khai OID paging không?
- Page size có bị giới hạn bởi server policy không?
- Cookie có được trả lại sau mỗi trang và cuối cùng trở thành rỗng không?
- Search base, filter, attributes và sort keys có giữ nguyên giữa các trang không?
- Kết quả có bị lặp/bỏ sót khi entry được thêm, sửa hoặc xóa trong lúc paging không?
- Ứng dụng có kết thúc paging và giải phóng context khi client hủy request không?

## 7. Server-side Sort: sắp xếp ở phía LDAP server

RFC 2891 định nghĩa server-side sort:

| Control | OID | Vai trò |
| --- | --- | --- |
| Sort request | **1.2.840.113556.1.4.473** | Gửi danh sách sort key và chiều sắp xếp |
| Sort response | **1.2.840.113556.1.4.474** | Báo sort thành công hoặc mã lỗi |

Server sort hữu ích khi client muốn nhận kết quả theo một ordering rule của LDAP attribute. Server phải biết ordering matching rule phù hợp với attribute sort key; nếu attribute hoặc rule không phù hợp, response control có thể báo **noSuchAttribute** hoặc **inappropriateMatching**.

### 7.1. Ví dụ sort bằng Spring LDAP 4.1+

~~~java
import javax.naming.directory.SearchControls;
import javax.naming.ldap.SortControl;
import javax.naming.ldap.SortResponseControl;
import org.springframework.ldap.control.ControlExchangeDirContextProcessor;
import org.springframework.ldap.control.SortControlExchange;

SearchControls searchControls = new SearchControls();
searchControls.setSearchScope(SearchControls.SUBTREE_SCOPE);

SortControlExchange exchange =
    new SortControlExchange("sn", "givenName");

ControlExchangeDirContextProcessor<SortControl, SortResponseControl>
    processor = new ControlExchangeDirContextProcessor<>(exchange);

List<Person> people = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    searchControls,
    personAttributesMapper,
    processor
);

SortResponseControl sortResponse =
    processor.getExchange().getResponse();

if (sortResponse == null || sortResponse.getResultCode() != 0) {
    throw new IllegalStateException(
        "LDAP server did not confirm the requested sort"
    );
}
~~~

Đoạn code thể hiện API Spring LDAP 4.1+; import các type **SortControl**, **SortResponseControl**, **SortControlExchange** và **ControlExchangeDirContextProcessor** từ JNDI/Spring LDAP tương ứng. Nếu server không hỗ trợ sort, không được tự coi kết quả là đã sort. Nếu cần fallback, sắp xếp client-side trên tập kết quả đã được giới hạn hoặc trả lỗi theo hợp đồng API.

### 7.2. Kết hợp sort với paging

Khi kết hợp sort control với paged results:

- Gửi cùng danh sách sort key trong mọi SearchRequest của cùng chuỗi paging.
- Không đổi thứ tự key giữa các trang.
- Server phải sort toàn bộ tập kết quả logic, không chỉ sort riêng từng page.
- Kiểm tra sort response control để xác nhận server đã áp dụng sort.
- Duy trì connection và paging cookie đúng vòng đời.

Nếu server chỉ sort từng trang, kết quả tổng hợp có thể không được sắp xếp toàn cục. RFC 2891 quy định hành vi phối hợp sort và paging để tránh lỗi này.

## 8. Assertion Control: cập nhật có điều kiện

Assertion Control theo RFC 4528 có OID **1.3.6.1.1.12**. Control value là filter được BER-encode. Server chỉ thực hiện update nếu filter assertion đúng với entry tại thời điểm operation.

Đây là cách thực hiện kiểu **compare-and-set** ở cấp LDAP operation. Ví dụ ứng dụng muốn chỉ đổi **description** khi **version** hiện tại vẫn là **42**:

~~~text
ModifyRequest:
  DN: uid=linh,ou=people,dc=example,dc=com
  Modification:
    replace description = "Updated"

Assertion Control:
  (version=42)
~~~

Nếu entry đã có **version=43**, server từ chối update thay vì ghi đè thay đổi của client khác. Assertion control có thể gắn với Add, Compare, Delete, Modify, ModifyDN và Search; không dùng cho Abandon, Bind, Unbind hoặc StartTLS.

### 8.1. Phân biệt assertion control với filter của SearchRequest

Filter trong SearchRequest chọn những entry cần tìm. Assertion control gắn vào operation để kiểm tra điều kiện trên target entry ngay khi server thực hiện operation. Hai filter có cú pháp LDAP nhưng có vị trí và tác dụng khác nhau.

### 8.2. Không giả định mọi server hỗ trợ

Kiểm tra **supportedControl** có OID **1.3.6.1.1.12**. Khi assertion là điều kiện bắt buộc để tránh lost update, gửi control critical và xử lý **unavailableCriticalExtension**/assertion failed đúng cách. Không âm thầm bỏ control rồi tiếp tục ghi.

## 9. Pre-Read và Post-Read: lấy trạng thái entry trong cùng update

RFC 4527 định nghĩa hai control để server trả lại bản sao entry trước hoặc sau khi update:

| Control | OID | Dùng với operation |
| --- | --- | --- |
| Pre-Read request/response | **1.3.6.1.1.13.1** | Modify, Delete, ModifyDN |
| Post-Read request/response | **1.3.6.1.1.13.2** | Add, Modify, ModifyDN |

Client gửi danh sách attribute cần đọc trong control value. Server trả một SearchResultEntry trong response control. Việc đọc và update được xử lý như một hành động atomic/isolation theo specification của control, chịu sự chi phối của ACL và các ràng buộc khác.

### 9.1. Khi nào dùng Pre-Read?

Pre-Read hữu ích khi cần biết giá trị trước update mà không muốn gửi một SearchRequest riêng ngay trước ModifyRequest. Ví dụ ứng dụng thay đổi trạng thái account nhưng cần lưu lại giá trị **description** và **modifyTimestamp** trước khi cập nhật.

### 9.2. Khi nào dùng Post-Read?

Post-Read hữu ích khi cần đọc giá trị server đã ghi sau Add/Modify/ModifyDN, bao gồm operational attribute như **modifyTimestamp** hoặc **entryUUID** nếu server cho phép trả về. Điều này giúp ứng dụng nhận trạng thái đã được server commit trong cùng update response.

### 9.3. Giới hạn và quyền truy cập

- Chỉ yêu cầu các attribute cần thiết, tránh lấy dữ liệu nhạy cảm không liên quan.
- Server vẫn áp dụng ACL; control không vượt qua quyền đọc.
- Nếu update thất bại, response control tương ứng không được trả như một update thành công.
- Không giả định server hỗ trợ RFC 4527 chỉ vì hỗ trợ RFC 4511.

## 10. ManageDsaIT: thao tác trên referral entry

**ManageDsaIT** có OID **2.16.840.1.113730.3.4.2**. Control này thay đổi cách server xử lý referral entry trong một số operation, để client có thể quản lý referral object như một entry directory thay vì để server tự xử lý referral theo hành vi thông thường.

Control hữu ích cho công cụ quản trị directory cần đọc hoặc sửa referral entry. Nó không phải cách tắt referral một cách tổng quát cho mọi thao tác, và không thay thế việc cấu hình referral/chaining đúng cách.

Trước khi dùng:

- Kiểm tra server công bố OID ManageDsaIT trong **supportedControl**.
- Xác định operation nào chấp nhận control.
- Kiểm tra client/provider có gửi control trên đúng LDAP message không.
- Không cho request bên ngoài tự bật ManageDsaIT để vượt qua logic quản trị referral của ứng dụng.

## 11. Một số control chuẩn và tình huống sử dụng

| Control | OID | Tình huống | Điểm cần lưu ý |
| --- | --- | --- | --- |
| Simple Paged Results | **1.2.840.113556.1.4.319** | Đọc tập kết quả lớn theo page | Cookie opaque; nhiều server yêu cầu cùng connection |
| Server-side Sort | **1.2.840.113556.1.4.473** | Sắp xếp kết quả tại server | Đọc response OID **.474** để xác nhận |
| Assertion | **1.3.6.1.1.12** | Conditional update | Filter assertion được đánh giá trong operation |
| Pre-Read | **1.3.6.1.1.13.1** | Đọc entry trước update | Chỉ phù hợp operation được RFC chỉ định |
| Post-Read | **1.3.6.1.1.13.2** | Đọc entry sau update | Chịu ACL và attribute selection |
| ManageDsaIT | **2.16.840.1.113730.3.4.2** | Quản lý referral entry | Phụ thuộc server/provider |

Các control trên có specification hoặc lịch sử triển khai riêng. Một số server hỗ trợ một phần; một số server yêu cầu quyền hoặc cấu hình đặc biệt. Hãy dùng Root DSE và test thực tế thay vì hard-code một ma trận capability cho mọi môi trường.

## 12. Matching rule xác định phép so sánh

Matching rule định nghĩa cách chuẩn hóa và so sánh một attribute value với assertion value. Schema của attribute type có thể chỉ định:

- **EQUALITY**: phép so sánh bằng.
- **ORDERING**: phép so sánh thứ tự, dùng với filter greater-than-or-equal và less-than-or-equal.
- **SUBSTR**: phép so sánh substring, dùng với filter có wildcard.

Ví dụ attribute **cn** có thể dùng **caseIgnoreMatch** cho equality và **caseIgnoreSubstringsMatch** cho substring. Do đó **cn=Alice** có thể match **alice** tùy schema/matching rule.

Matching rule không phải quy tắc chung cho toàn bộ directory. Cùng một ký tự hoặc chuỗi có thể được so sánh khác nhau ở attribute có syntax hoặc rule khác nhau.

### 12.1. Ví dụ các rule thường gặp

| Matching rule | OID | Loại | Ý nghĩa |
| --- | --- | --- | --- |
| **distinguishedNameMatch** | **2.5.13.1** | Equality | So sánh DN |
| **caseIgnoreMatch** | **2.5.13.2** | Equality | Chuỗi không phân biệt hoa thường |
| **caseIgnoreOrderingMatch** | **2.5.13.3** | Ordering | Ordering không phân biệt hoa thường |
| **caseIgnoreSubstringsMatch** | **2.5.13.4** | Substrings | Substring không phân biệt hoa thường |
| **caseExactMatch** | **2.5.13.5** | Equality | So sánh phân biệt hoa thường |
| **caseExactOrderingMatch** | **2.5.13.6** | Ordering | Ordering phân biệt hoa thường |
| **caseExactSubstringsMatch** | **2.5.13.7** | Substrings | Substring phân biệt hoa thường |
| **integerMatch** | **2.5.13.14** | Equality | So sánh số nguyên |
| **integerOrderingMatch** | **2.5.13.15** | Ordering | So sánh thứ tự số nguyên |

Danh sách này minh họa các rule chuẩn được định nghĩa trong RFC 4517; server và schema có thể triển khai thêm rule khác.

### 12.2. Matching rule phải tương thích syntax

Một rule chỉ có thể dùng với attribute/assertion syntax mà nó hỗ trợ. Ví dụ integer ordering không có ý nghĩa trên một attribute chứa arbitrary binary. Nếu rule không phù hợp, server có thể trả **inappropriateMatching**. Không đổi OID để thử ngẫu nhiên cho tới khi filter chạy; hãy kiểm tra schema và specification.

## 13. Schema mô tả matching rule mặc định của attribute

Một AttributeTypeDescription có thể khai báo các thành phần:

~~~text
attributeType (
  1.2.3.4
  NAME 'employeeNumber'
  EQUALITY integerMatch
  ORDERING integerOrderingMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.27
  SINGLE-VALUE
)
~~~

Trong ví dụ:

- Attribute có syntax integer.
- Equality sử dụng **integerMatch**.
- Ordering sử dụng **integerOrderingMatch**.
- Attribute chỉ có một giá trị.

Đây là schema minh họa, OID attribute **1.2.3.4** chỉ là OID ví dụ. Không đăng ký OID này trong production schema; tổ chức phải dùng OID được cấp cho namespace của mình.

### 13.1. matchingRuleUse

**matchingRuleUse** mô tả những attribute type phù hợp để sử dụng một matching rule trong extensibleMatch. Đây là thông tin schema, không phải control capability. Nếu server không công bố **matchingRuleUse**, điều đó không tự chứng minh rule không tồn tại; cần đọc tài liệu và thử truy vấn phù hợp.

### 13.2. Vì sao hai server có thể cho kết quả khác nhau?

- Schema attribute có thể khác **EQUALITY**, **ORDERING**, **SUBSTR**.
- Một server có thể triển khai custom matching rule, server khác không có.
- Syntax/normalization của giá trị có thể khác.
- Matching rule có thể được hỗ trợ nhưng chỉ áp dụng cho một số attribute type.
- Matching rule OID vendor-specific có thể chỉ hoạt động trên một dòng/version server.

Vì vậy, khi di chuyển directory hoặc thay LDAP server, phải kiểm thử lại các query phụ thuộc matching rule.

## 14. ExtensibleMatch: gọi matching rule trực tiếp trong filter

LDAPv3 có extensible match filter. Cú pháp tổng quát:

~~~text
(attribute[:dn][:matchingRuleOID]:=assertionValue)
~~~

Các phần:

- **attribute**: attribute description, có thể bỏ nếu rule cho phép.
- **dn**: tùy chọn yêu cầu kiểm tra các attribute xuất hiện trong DN của entry.
- **matchingRuleOID**: tên hoặc OID của matching rule.
- **assertionValue**: giá trị assertion có syntax tương thích với rule.

Ví dụ:

~~~text
(cn:2.5.13.5:=Alice)
~~~

Filter yêu cầu so sánh **cn** bằng **caseExactMatch**. Tên rule có thể được dùng thay OID nếu server nhận diện descriptor đó.

### 14.1. Cờ dnAttributes

Ví dụ:

~~~text
(cn:dn:2.5.13.5:=Alice)
~~~

Phần **dn** yêu cầu server xét attribute **cn** trong DN của entry ngoài attribute value thông thường, theo semantics extensibleMatch. Đây không phải cú pháp để so sánh một DN; rule được gọi vẫn là **caseExactMatch**.

### 14.2. Không thể dùng bất kỳ matching rule nào với mọi attribute

Rule phải chấp nhận syntax của assertion value và phù hợp attribute. Server cũng có thể giới hạn extensibleMatch hoặc giới hạn rule chỉ dùng trên một số attribute. Kiểm tra **matchingRuleUse**, tài liệu vendor và integration test trước khi đưa filter vào production.

## 15. Matching rule chuẩn trong OpenLDAP

OpenLDAP 2.6 hỗ trợ nhiều matching rule chuẩn, ví dụ:

- **caseIgnoreMatch** và **caseIgnoreSubstringsMatch** cho directory string.
- **caseExactMatch** cho phép so sánh phân biệt hoa thường.
- **distinguishedNameMatch** cho giá trị DN.
- **integerMatch** và **integerOrderingMatch** cho integer syntax.
- **numericStringMatch** cho numeric string.
- **octetStringMatch** cho dữ liệu octet.

Các rule mặc định được schema attribute tham chiếu qua **EQUALITY**, **ORDERING** và **SUBSTR**. OpenLDAP cũng cho phép mở rộng schema và nạp module matching rule tùy chỉnh nếu có implementation tương ứng.

### 15.1. Kiểm tra schema trên OpenLDAP

Đọc **subschemaSubentry** từ Root DSE, sau đó truy vấn **matchingRules**, **matchingRuleUse** và **attributeTypes**. Nếu dùng dynamic configuration, schema có thể được nạp thông qua cấu hình cn=config hoặc file schema tùy cách cài đặt.

Không giả định một schema tùy chỉnh đã được nạp chỉ vì file LDIF schema nằm trên filesystem. Xác nhận server khởi động với schema đó và truy vấn Root DSE/subschema sau khi reload.

### 15.2. Controls trên OpenLDAP có thể phụ thuộc backend

OpenLDAP 2.6 có các control như assertion, paging, pre-read/post-read và permissive modify tùy build/cấu hình/backend. Tài liệu Monitor có thể liệt kê **supportedControl** trên từng backend object; điều đó hữu ích khi một server có nhiều database/backend với tập control khác nhau.

Không suy từ một backend MDB hỗ trợ control rằng mọi backend hoặc mọi database trên cùng slapd đều hỗ trợ giống nhau. Hãy kiểm tra Root DSE, monitor data khi được bật, và chạy test trên database đích.

## 16. Matching rule đặc thù của Active Directory

Active Directory bổ sung một số matching rule hữu ích cho thuộc tính số và liên kết DN. Các rule này không phải matching rule chuẩn portable của mọi LDAP server.

| Tên Microsoft | OID | Hỗ trợ theo tài liệu Microsoft |
| --- | --- | --- |
| **LDAP_MATCHING_RULE_BIT_AND** | **1.2.840.113556.1.4.803** | AD DS/AD LDS |
| **LDAP_MATCHING_RULE_BIT_OR** | **1.2.840.113556.1.4.804** | AD DS/AD LDS |
| **LDAP_MATCHING_RULE_IN_CHAIN / TRANSITIVE_EVAL** | **1.2.840.113556.1.4.1941** | Windows Server 2008 trở lên |
| **LDAP_MATCHING_RULE_DN_WITH_DATA** | **1.2.840.113556.1.4.2253** | Windows Server 2012 R2 trở lên |

Microsoft nêu rõ các matching rule này được gọi trong extensibleMatch của SearchRequest; danh sách rule không được công bố qua một attribute Root DSE riêng.

Theo ma trận phiên bản Microsoft, BIT_AND và BIT_OR đã có từ Windows 2000/ADAM; IN_CHAIN có từ Windows Server 2008 trong AD DS và AD LDS; DN_WITH_DATA có từ Windows Server 2012 R2 trong AD DS và AD LDS. Kiểm tra phiên bản DC/AD LDS thực tế trước khi dùng.

### 16.1. Bitwise AND: kiểm tra cờ tài khoản

**LDAP_MATCHING_RULE_BIT_AND** trả TRUE khi mọi bit được đặt trong assertion value cũng được đặt trong attribute. Ví dụ **userAccountControl** có cờ **ACCOUNTDISABLE = 0x2 = 2**:

~~~text
(&(objectCategory=person)
  (objectClass=user)
  (userAccountControl:1.2.840.113556.1.4.803:=2))
~~~

Filter tìm user có bit disable được đặt. Assertion value phải là số thập phân, không truyền chuỗi hex hoặc tên constant.

### 16.2. Bitwise OR: kiểm tra ít nhất một cờ

**LDAP_MATCHING_RULE_BIT_OR** trả TRUE nếu có ít nhất một bit trong assertion value cũng được đặt ở attribute:

~~~text
(groupType:1.2.840.113556.1.4.804:=2147483648)
~~~

Ví dụ kiểm tra bit security-enabled trong **groupType**. Giá trị decimal **2147483648** tương ứng hằng số hex **0x80000000**.

### 16.3. IN_CHAIN: truy vấn quan hệ nhóm lồng nhau

**LDAP_MATCHING_RULE_IN_CHAIN** lần theo chuỗi liên kết DN để kiểm tra quan hệ tổ tiên/nhóm lồng nhau. Ví dụ tìm user là thành viên trực tiếp hoặc gián tiếp của group:

~~~text
(memberOf:1.2.840.113556.1.4.1941:=CN=Engineering,OU=Groups,DC=example,DC=com)
~~~

Rule này chỉ phù hợp với các attribute kiểu DN/link được AD hỗ trợ; không dùng nó như một phép tìm chuỗi tổng quát. Cần kiểm tra quyền đọc link, base DN và tải truy vấn trên directory lớn.

### 16.4. DN_WITH_DATA: so sánh giá trị DN kèm dữ liệu

**LDAP_MATCHING_RULE_DN_WITH_DATA** áp dụng cho link attribute có syntax **Object(DN-String)** hoặc **Object(DN-Binary)**. Rule so sánh phần DN và phần string/byte dữ liệu của value; nó không phải phép so sánh DN tổng quát và không dùng cho attribute DN thông thường.

Ví dụ minh họa với attribute AD **msDS-HasInstantiatedNCs**:

~~~text
(msDS-HasInstantiatedNCs:1.2.840.113556.1.4.2253:=B:8:0000000D:CN=Schema,CN=Configuration,DC=example,DC=com)
~~~

Value dạng DN-Binary chứa phần dữ liệu nhị phân và DN. Cần dùng đúng encoding/value format do AD quy định cho attribute; không tự suy diễn chuỗi B:... cho attribute khác.

### 16.5. Giới hạn extensibleMatch riêng của AD

Active Directory chỉ công bố bốn matching rule vendor-specific trong danh sách trên cho extensibleMatch. Các rule so sánh thông thường của AD (ví dụ equality/ordering của Unicode string) được mô tả theo từng syntax nhưng không được expose thành OID extensibleMatch chung như **caseExactMatch** hoặc **caseIgnoreMatch** của RFC 4517.

Ngoài ra, AD **bỏ qua cờ dnAttributes** trong MatchingRuleAssertion và luôn xử lý như FALSE. Vì vậy filter dạng **(cn:dn:2.5.13.5:=Alice)** ở mục 14 không phải query portable cho AD. AD cũng triển khai **approxMatch** giống equalityMatch, không thực hiện so sánh gần đúng thực sự.

## 17. Controls riêng của Active Directory

Active Directory công bố nhiều control OID qua Root DSE **supportedControl**. Một số control tiêu biểu:

| Control | OID | Tác dụng |
| --- | --- | --- |
| Paged Results | **1.2.840.113556.1.4.319** | Chia kết quả search thành page |
| Show Deleted | **1.2.840.113556.1.4.417** | Hiển thị tombstone/deleted object |
| Show Recycled | **1.2.840.113556.1.4.2064** | Hiển thị recycled object |
| Show Deactivated Link | **1.2.840.113556.1.4.2065** | Hiển thị link attribute trỏ tới deleted object |
| Sort request | **1.2.840.113556.1.4.473** | Sort kết quả tại DC |
| Extended DN | **1.2.840.113556.1.4.529** | Trả DN mở rộng chứa objectGUID và có thể objectSid |
| DirSync | **1.2.840.113556.1.4.841** | Lấy thay đổi kể từ cookie trước |
| SD Flags | **1.2.840.113556.1.4.801** | Chọn phần security descriptor cần đọc/ghi |
| Permissive Modify | **1.2.840.113556.1.4.1413** | Thay đổi cách xử lý một số modify lặp/không tồn tại |

Đây là control riêng AD, không nên coi chúng là phần bắt buộc của LDAPv3 portable.

### 17.1. DirSync: đồng bộ thay đổi theo cookie

DirSync dùng control OID **1.2.840.113556.1.4.841** để truy vấn object đã thay đổi kể từ lần đồng bộ trước. Server trả cookie opaque; client lưu cookie và gửi lại ở lần tiếp theo.

Các điểm quan trọng:

- DirSync được thiết kế để theo dõi thay đổi trên toàn bộ naming context replica, không phải thay thế cho search subtree bất kỳ.
- Cookie do DC cấp, client không diễn giải nội dung.
- Cookie phải được lưu cùng định danh domain/DC và trạng thái đồng bộ phù hợp; xử lý khi cookie hết hiệu lực hoặc replication topology thay đổi.
- Quyền đọc change set và cờ control ảnh hưởng dữ liệu server trả về.
- Không nhầm DirSync với paged results: paging chia một kết quả search, DirSync lấy thay đổi kể từ một trạng thái trước.

### 17.2. Show Deleted: đọc tombstone

Control **1.2.840.113556.1.4.417** yêu cầu DC hiển thị tombstone/deleted object phù hợp với filter. Deleted object giữ lại một tập attribute giới hạn trong thời gian retention trước khi garbage collection loại bỏ nó. Recycled object cần control **1.2.840.113556.1.4.2064**; link attribute trỏ tới deleted object cần control **1.2.840.113556.1.4.2065** theo đúng tổ hợp control mà AD quy định.

Không coi control này là chức năng khôi phục object đầy đủ. Quyền đọc deleted object, naming context, trạng thái tombstone/recycled object và retention policy đều ảnh hưởng kết quả. Một số loại deleted/recycled object cần control khác và điều kiện phiên bản riêng.

### 17.3. Extended DN: nhận GUID/SID cùng DN

Control **1.2.840.113556.1.4.529** yêu cầu DC trả DN theo định dạng mở rộng có thể chứa **objectGUID** và **objectSid**:

~~~text
<GUID=...>;<SID=...>;CN=SomeGroup,OU=Groups,DC=example,DC=com
~~~

Định dạng này hữu ích khi DN có thể thay đổi do rename/move nhưng ứng dụng cần định danh ổn định theo GUID/SID. Extended DN là định dạng **server trả về**, không phải DN thay thế để gửi trong request; parser của ứng dụng phải tách GUID/SID và DN thông thường, không đưa nguyên chuỗi extended DN vào API chỉ chấp nhận DN RFC 4514.

### 17.4. SD Flags: chọn phần security descriptor

Control **1.2.840.113556.1.4.801** chọn phần security descriptor được đọc hoặc cập nhật: OWNER, GROUP, DACL, SACL. Nếu không gửi control, giá trị mặc định của AD là **15 (0x0000000F)**, tức cả bốn phần OWNER, GROUP, DACL và SACL. Ứng dụng nên chỉ yêu cầu phần thực sự cần thiết.

Với Search, server trả security descriptor khi attribute SD được yêu cầu tường minh hoặc search yêu cầu tất cả attribute. Với Modify, chỉ các phần được đánh dấu trong control mới được cập nhật; các phần khác trong giá trị gửi lên bị bỏ qua. Nếu control được gửi cùng Add, AD bỏ qua control.

Đọc/ghi SACL và các thành phần security descriptor yêu cầu quyền phù hợp, thường có yêu cầu đặc biệt như quyền đọc audit. Không dùng control này như cách vượt ACL; DC vẫn áp dụng access check.

## 18. Tạo filter matching rule trong Spring LDAP

Với matching rule vendor-specific, giữ OID và cấu trúc filter ở phía ứng dụng. Không nhận OID hoặc đoạn filter tùy ý từ client.

Ví dụ AD bitwise AND:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;
import org.springframework.ldap.query.LdapQuery;

LdapQuery disabledUsers = query().filter(
    "(&(objectCategory=person)(objectClass=user)"
    + "(userAccountControl:1.2.840.113556.1.4.803:=2))"
);
~~~

Ví dụ IN_CHAIN với group DN đã được kiểm tra:

~~~java
LdapQuery members = query().filter(
    "(memberOf:1.2.840.113556.1.4.1941:={0})",
    validatedGroupDn
);
~~~

Overload **filter(format, params)** sử dụng MessageFormat và encode các parameter value theo Spring LDAP. Template filter và matching rule OID vẫn phải là literal do ứng dụng kiểm soát. Nếu cần dynamic attribute/rule, map một enum sang allowlist các filter template đã định nghĩa.

### 18.1. Không dùng derived query để thay thế matching rule vendor

Tên method kiểu **findByUserAccountControl(...)** thường biểu diễn equality/keyword mà store hỗ trợ; nó không tự diễn tả extensibleMatch với OID AD. Khi cần bitwise hoặc transitive matching, dùng filter tường minh qua LdapQueryBuilder hoặc custom repository implementation.

### 18.2. Không parameterize OID như assertion value

OID matching rule là một phần cấu trúc filter. Không truyền OID từ input như một parameter value và kỳ vọng framework encode sẽ bảo vệ cú pháp. Hãy chọn OID từ allowlist code, rồi bind/encode riêng assertion value.

## 19. Khác biệt server, lỗi thường gặp và kiểm thử

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| **unavailableCriticalExtension** | Server không hỗ trợ control critical | Kiểm tra Root DSE/version; bỏ control chỉ khi nghiệp vụ cho phép |
| Search thành công nhưng không có sort | Sort control non-critical bị bỏ qua hoặc response báo lỗi | Kiểm tra SortResponseControl/resultCode |
| Paging cookie invalid | Dùng connection khác hoặc cookie bị dùng lại/sai chuỗi | Giữ cùng connection; tạo processor riêng |
| **inappropriateMatching** | Matching rule không tương thích attribute syntax | Kiểm tra schema EQUALITY/ORDERING/SUBSTR và matchingRuleUse |
| **protocolError** | Filter extensibleMatch sai cú pháp hoặc tổ hợp control không hợp lệ | Kiểm tra phần matching rule delimiter và cờ dnAttributes |
| AD bitwise filter không match | Dùng hex/string thay decimal hoặc sai bit flag | Chuyển value sang decimal và xác nhận attribute |
| IN_CHAIN trả thiếu kết quả | Attribute không phải link phù hợp, quyền đọc link hoặc phiên bản không hỗ trợ | Kiểm tra AD DS version, link attribute và ACL |
| Show Deleted trả ít attribute | Tombstone giữ lại subset attribute | Kiểm tra lifecycle/retention; không kỳ vọng object nguyên vẹn |
| Root DSE không có OID mong đợi | Control chưa được cấu hình, backend khác hoặc server không công bố | Kiểm tra vendor docs, monitor/backend và integration test |
| Sort + paging cho kết quả không toàn cục | Server/client sort từng trang hoặc đổi sort key giữa page | Giữ sort key ổn định; xác nhận hỗ trợ phối hợp RFC 2891/RFC 2696 |

### 19.1. Kiểm thử theo capability

Với mỗi server/version được hỗ trợ, tạo integration test riêng:

1. Đọc Root DSE và lưu danh sách **supportedControl**, **supportedExtension**, **supportedFeatures**.
2. Đọc subschema để xác nhận syntax, **EQUALITY**, **ORDERING**, **SUBSTR** và **matchingRuleUse** nếu được công bố.
3. Thực hiện một request thử cho control với dữ liệu fixture nhỏ.
4. Kiểm tra cả operation result code và response control.
5. Kiểm tra hành vi khi control không được hỗ trợ ở chế độ critical và non-critical.
6. Kiểm thử matching rule với dữ liệu có khác biệt hoa thường, số, DN và bit flag.
7. Xác minh filter vendor-specific chỉ chạy trên đúng server/version và trả lỗi rõ ràng trên server khác.

### 19.2. Không dùng dữ liệu production để thử control nguy hiểm

Các control như Show Deleted, SD Flags, DirSync, Tree Delete hoặc controls quản trị có thể truy cập dữ liệu nhạy cảm hoặc thay đổi trạng thái directory. Kiểm thử trong directory lab với bind identity và ACL được kiểm soát. Log OID, operation, server version và result code; tránh log cookie nhạy cảm, security descriptor hoặc dữ liệu cá nhân đầy đủ.

## 20. Checklist, bài thực hành và câu hỏi ôn tập

### 20.1. Checklist trước triển khai

~~~text
[ ] Đã truy vấn Root DSE của đúng server/endpoint
[ ] Phân biệt supportedControl, supportedExtension và supportedFeatures
[ ] Đã đọc subschemaSubentry khi cần kiểm tra matching rule
[ ] Không giả định supportedControl là danh sách matching rule
[ ] Đã xác nhận criticality phù hợp với yêu cầu nghiệp vụ
[ ] Đã đọc response control khi specification yêu cầu
[ ] Paging giữ cùng connection và cookie đúng vòng đời
[ ] Sort response được kiểm tra, không mặc định server đã sort
[ ] Assertion control được dùng khi cần conditional update
[ ] Pre-read/post-read chỉ dùng với operation được RFC cho phép
[ ] OID vendor-specific được allowlist trong code
[ ] AD bitwise value truyền ở dạng decimal
[ ] IN_CHAIN chỉ dùng với link attribute phù hợp
[ ] OpenLDAP backend/database đích đã được kiểm tra riêng
[ ] Integration test chạy trên từng server/version được hỗ trợ
[ ] ACL và quyền đọc/ghi vẫn được kiểm tra độc lập với control
~~~

### 20.2. Bài thực hành

1. Dùng ldapsearch đọc Root DSE và ghi lại supportedControl, supportedExtension, namingContexts, subschemaSubentry.
2. Đọc subschema và xác định EQUALITY, ORDERING, SUBSTR của cn, uid, member và một attribute số.
3. Tạo search có paged results control và đọc hết các trang bằng Spring LDAP 4.1+.
4. Thêm server-side sort, kiểm tra response control và thử trường hợp sort key không có ordering rule phù hợp.
5. Dùng Assertion Control để chỉ modify khi version attribute vẫn có giá trị cũ.
6. Dùng Pre-Read/Post-Read để lấy giá trị trước và sau một ModifyRequest.
7. Trên OpenLDAP lab, so sánh control được công bố ở Root DSE và monitor backend.
8. Trên Active Directory lab, tìm user disabled bằng bitwise AND.
9. Truy vấn thành viên nhóm lồng nhau bằng IN_CHAIN.
10. Thử DirSync với cookie được lưu và tiếp tục qua lần search sau.
11. Thử Show Deleted trong lab, xác minh tombstone không chứa toàn bộ attribute gốc.
12. Viết capability test để ứng dụng từ chối bật OID không nằm trong allowlist của server/version.

### 20.3. Câu hỏi ôn tập

1. Request control và response control khác nhau ở đâu?
2. OID, criticality và controlValue có ý nghĩa gì?
3. Khi criticality là TRUE và server không hỗ trợ control, kết quả phải như thế nào?
4. Vì sao SearchResult thành công chưa chứng minh server đã áp dụng sort control?
5. supportedControl khác supportedExtension và supportedFeatures thế nào?
6. Vì sao matching rule không thể được suy ra từ danh sách control?
7. Schema EQUALITY, ORDERING, SUBSTR mô tả điều gì?
8. matchingRuleUse có vai trò gì trong extensibleMatch?
9. Cú pháp extensibleMatch và cờ dnAttributes hoạt động ra sao?
10. Vì sao paged results cần cùng underlying connection?
11. Assertion Control giải quyết vấn đề lost update ở cấp LDAP operation thế nào?
12. Pre-Read và Post-Read áp dụng cho những update operation nào?
13. Bitwise AND và Bitwise OR của AD khác nhau thế nào?
14. IN_CHAIN có giới hạn với loại attribute nào?
15. DirSync khác paged results ở mục đích và vòng đời cookie ra sao?

### 20.4. Ghi nhớ

**Controls mở rộng hành vi của LDAP operation; matching rules mở rộng cách server so sánh giá trị.** OID nhận diện cơ chế, criticality quyết định server có được phép bỏ qua control hay không, còn response control có thể chứa trạng thái riêng cần được kiểm tra. Spring LDAP dùng **DirContextProcessor** để gắn request control và đọc response control; từ 4.1 có **ControlExchangeDirContextProcessor** cùng các exchange chuyên dụng cho paging và sort.

Matching rule mặc định đến từ schema attribute qua **EQUALITY**, **ORDERING**, **SUBSTR**; extensibleMatch cho phép gọi rule theo tên/OID. OpenLDAP có tập rule chuẩn và schema mở rộng; Active Directory bổ sung bitwise AND/OR, IN_CHAIN và DN_WITH_DATA cùng nhiều control riêng như DirSync, Show Deleted, Extended DN và SD Flags. Không có một bộ OID dùng được cho mọi server. Discovery Root DSE/schema, kiểm tra response control, ACL và integration test theo server/version là điều kiện để triển khai an toàn.

## Tài liệu tham khảo

- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): LDAP message, request/response control, criticality và SearchRequest.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): Root DSE, subschema, matchingRules và matchingRuleUse.
- [RFC 4517 — LDAP Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517.html): equality, ordering, substring và extensible matching rules chuẩn.
- [RFC 2696 — Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696.html): paging cookie và tương tác client/server.
- [RFC 2891 — Server Side Sorting](https://www.rfc-editor.org/rfc/rfc2891.html): sort request/response control và phối hợp paging.
- [RFC 4528 — Assertion Control](https://www.rfc-editor.org/rfc/rfc4528.html): conditional operation bằng filter assertion.
- [RFC 4527 — Read Entry Controls](https://www.rfc-editor.org/rfc/rfc4527.html): Pre-Read và Post-Read.
- [RFC 3296 — Named Subordinate References in LDAP Directories](https://www.rfc-editor.org/rfc/rfc3296.html): ManageDsaIT control và referral entry.
- [IANA LDAP Parameters](https://www.iana.org/assignments/ldap-parameters): registry OID LDAP controls, extensions và filter features.
- [Spring LDAP — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): DirContextProcessor, controls và paging.
- [Spring LDAP — ControlExchangeDirContextProcessor API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/ControlExchangeDirContextProcessor.html): lifecycle request/response control.
- [Spring LDAP — SortControlExchange API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/SortControlExchange.html): server-side sort exchange.
- [OpenLDAP 2.6 Administrator's Guide](https://www.openldap.org/doc/admin26/guide.html): schema matching rules và control theo backend.
- [Microsoft — LDAP Matching Rules (extensibleMatch)](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/4e638665-f466-4597-93c4-12f2ebfabab5): OID matching rules riêng của AD và version support.
- [Microsoft — Search Filters](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/0bb88bda-ed8d-4af7-9f7b-813291772990): giới hạn extensibleMatch, dnAttributes và approxMatch của AD.
- [Microsoft — LDAP_MATCHING_RULE_DN_WITH_DATA](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/e5bfc285-05b9-494e-a123-c5c4341c450e): so khớp giá trị Object(DN-String) và Object(DN-Binary).
- [Microsoft — SD Flags Control](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/932a7a8d-8c93-4448-8093-c79b7d9ba499): các phần security descriptor và giá trị mặc định.
- [Microsoft — LDAP Extended Controls](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/3c5e87db-4728-4f29-b164-01dd7d7391ea): danh sách control AD và OID.
- [Microsoft — LDAP_SERVER_DIRSYNC_OID](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/2213a7f2-0a36-483c-b2a4-8574d53aa1e3): incremental synchronization và cookie.
- [Microsoft — LDAP_SERVER_SHOW_DELETED_OID](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/4b8f2a0e-9ea6-4be3-b639-4b019948c568): truy vấn tombstone và deleted object.
