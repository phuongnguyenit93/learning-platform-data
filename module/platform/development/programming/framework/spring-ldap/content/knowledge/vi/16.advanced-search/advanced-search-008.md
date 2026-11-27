# Search continuation, referral và partial result trong Spring LDAP

Khi tìm kiếm LDAP trong một cây thư mục nhỏ, ứng dụng Spring LDAP thường gọi `LdapTemplate.search(...)` và nhận danh sách entry khớp filter. Nhưng trong hệ thống lớn, các nhánh dữ liệu có thể nằm ở **nhiều server hoặc naming context**. Máy chủ mà ứng dụng đang kết nối có thể trả về những entry nó quản lý và đồng thời giới thiệu thêm nơi cần tìm. Nếu client không xử lý được những hướng dẫn đó, kết quả tìm kiếm có thể **chỉ là một phần** của dữ liệu mong đợi.

Bài này giải thích ba khái niệm thường gặp trong **Search nâng cao**:

- **Search continuation reference**: thông điệp LDAP chứa địa chỉ của nơi có thể tiếp tục tìm kiếm khi một phần phạm vi thuộc nguồn khác.
- **Referral**: chỉ dẫn tới server hoặc dịch vụ khác, có thể xuất hiện như mã kết quả của một thao tác hoặc được dùng trong continuation reference của search.
- **Partial result**: tình huống client không nhận được đầy đủ dữ liệu theo phạm vi truy vấn, thường biểu hiện ở Java/JNDI qua `PartialResultException`.

Với Spring LDAP, hiểu đúng ba khái niệm này giúp thiết kế tìm kiếm theo DN, filter, scope, `ContextSource`, TLS và ACL mà không vô tình công bố kết quả thiếu là kết quả đầy đủ.

## 1. Bối cảnh: một cây LDAP, nhiều nơi quản lý

Giả sử công ty chia dữ liệu nhân sự theo các miền thư mục:

~~~text
LDAP Server A
dc=example,dc=org
├── ou=people          (lưu tại Server A)
│   ├── uid=an
│   └── uid=binh
└── ou=partners        (điểm tham chiếu đến Server B)

LDAP Server B
ou=partners,dc=example,dc=org
├── uid=chi
└── uid=dung
~~~

Ứng dụng hỏi Server A: tìm mọi entry `(objectClass=inetOrgPerson)` dưới `dc=example,dc=org` với search scope `SUBTREE`. Server A có thể tìm `an` và `binh`, nhưng không tự tìm dữ liệu `chi`, `dung` tại Server B. Thay vì gửi những entry nó không có, server có thể trả **SearchResultReference** chứa LDAP URL hướng dẫn client tới Server B.

Nếu ứng dụng chỉ lấy hai entry tại Server A rồi công bố “toàn bộ danh sách có hai người”, kết luận đó có thể sai. Cách ứng dụng phải xử lý phụ thuộc yêu cầu: tìm **chỉ nhân viên nội bộ của Server A**, hay tìm **toàn bộ đối tượng trong tất cả nhánh**, kể cả nguồn được giới thiệu.

## 2. Ba loại thông điệp khi LDAP search

LDAPv3 mô tả chuỗi phản hồi tìm kiếm bằng các kiểu thông điệp riêng:

| Thông điệp / kết quả | Khi nào xuất hiện | Ý nghĩa đối với client |
| --- | --- | --- |
| `SearchResultEntry` | Máy chủ tìm thấy entry khớp filter | Entry dữ liệu thực tế được trả về |
| `SearchResultReference` | Máy chủ đã định vị được search base nhưng một phần đối tượng trong phạm vi tìm kiếm là dữ liệu không nằm ở nguồn mà nó sẽ tìm tiếp | Chứa một hay nhiều LDAP URL để client có thể tìm tiếp ở nguồn khác |
| `SearchResultDone` | Máy chủ kết thúc phần xử lý search của mình | Mang LDAP result code cho phần thao tác đó; không đồng nghĩa mọi server liên quan đều đã được truy vấn |
| `SearchResultDone` với result code `referral` | Search base không nằm tại máy chủ được hỏi nhưng máy chủ biết nơi phù hợp khác | Giới thiệu nơi thực hiện lại truy vấn, thay vì đã tìm base rồi gửi continuation references |

Theo RFC 4511, nếu máy chủ **đã tìm được `baseObject`** nhưng không thể hoặc không muốn tìm một số entry không cục bộ, nó có thể trả một hay nhiều `SearchResultReference`. Nếu **không tìm được search base**, máy chủ không được trả continuation reference theo cách đó; nó có thể kết thúc bằng `referral` hoặc `noSuchObject`, tùy thông tin mà nó biết.

### 2.1. Trình tự phản hồi minh họa

~~~text
Client                           LDAP Server A               LDAP Server B
  |                                   |                            |
  |-- SearchRequest (subtree) ------->|                            |
  |<-- SearchResultEntry(uid=an) -----|                            |
  |<-- SearchResultEntry(uid=binh) ---|                            |
  |<-- SearchResultReference ---------|                            |
  |      ldap://server-b/...          |                            |
  |<-- SearchResultDone (success) ----|                            |
  |                                   |                            |
  |-- SearchRequest (theo URL tham chiếu) ------------------------->|
  |<-- SearchResultEntry(uid=chi) ---------------------------------|
  |<-- SearchResultEntry(uid=dung) --------------------------------|
  |<-- SearchResultDone (success) ---------------------------------|
~~~

Đây là sơ đồ **luồng logic**: JNDI có thể tự theo referral khi được cấu hình, hoặc ứng dụng phải chủ động truy vấn nguồn khác. Kết quả `success` của Server A xác nhận phần tìm kiếm do Server A xử lý, nhưng **không tự xác nhận** rằng Server B đã được truy cập.

### 2.2. Continuation reference khác với paging cookie

Tên “continuation” dễ bị nhầm với **phân trang kết quả**:

| Tiêu chí | Search continuation reference | Paged results (RFC 2696) |
| --- | --- | --- |
| Cần tiếp tục ở đâu? | Server hoặc nhánh LDAP khác theo LDAP URL | Phần tiếp theo của một phiên tìm kiếm có phân trang |
| Dữ liệu điều hướng | Một hoặc nhiều LDAP URL | Cookie dạng byte do server cấp |
| Mục tiêu | Khám phá và truy vấn phần dữ liệu không được server hiện tại tìm trực tiếp | Chia một tập kết quả lớn thành những trang |
| Điều kiện hoàn tất | Các nguồn cần thiết đã được truy vấn thành công theo hợp đồng nghiệp vụ | Nhận được cookie rỗng ở trang cuối theo giao thức phân trang |
| Có thể thay thế cho nhau? | Không | Không |

Một server hoàn toàn có thể vừa trả trang kết quả vừa phát sinh continuation reference. **Cookie rỗng không chứng minh rằng mọi referral ngoài nguồn đã được theo**. Ngược lại, đi theo các continuation reference không có nghĩa là client đã lấy đủ mọi trang tại nguồn được giới thiệu.

## 3. Điều khiển referral của JNDI

Spring LDAP sử dụng JNDI phía dưới `ContextSource`. Thuộc tính JNDI `Context.REFERRAL` (tên môi trường `java.naming.referral`) quyết định cách provider xử lý cả **referral response** lẫn **continuation references**.

| Giá trị | Hành vi cơ bản | Hệ quả trong tìm kiếm |
| --- | --- | --- |
| `ignore` | Không tự theo URL referral; giá trị mặc định của JNDI LDAP provider thông dụng | Có thể chỉ tìm phần cục bộ; nếu server vẫn trả referral mà provider không xử lý được, có thể phát sinh `PartialResultException` |
| `follow` | Provider cố gắng tự đi theo referral | Có thể tìm thêm dữ liệu nhưng phụ thuộc DNS, kết nối, TLS, quyền xác thực, chính sách server và việc theo referral thành công |
| `throw` | Provider ném `ReferralException` để caller quyết định | Có thể phục vụ nhu cầu điều phối referral thủ công ở tầng JNDI; cần quản lý các URL và context liên quan |

Với **LDAPv3**, nhà cung cấp LDAP JNDI điển hình sẽ gửi **ManageDsaIT control** khi `Context.REFERRAL=ignore`, để server xử lý referral entry như entry thông thường thay vì tự trả referral. Tuy nhiên, nếu server không hỗ trợ cơ chế tương ứng hoặc vẫn trả continuation reference, client **vẫn có thể gặp** `PartialResultException`.

Không nên hiểu `ignore` là “bảo đảm lấy được toàn bộ dữ liệu” hoặc `follow` là “bảo đảm truy vấn hết mọi nơi”. Đó chỉ là **chính sách xử lý chuyển hướng** của client.

### 3.1. Cấu hình trong LdapContextSource

~~~java
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://ldap-a.example.org:636");
source.setBase("dc=example,dc=org");
source.setReferral("ignore"); // Có thể là "follow" hoặc "throw"

// Trong ứng dụng thực, cấu hình bind DN và credential qua nguồn bí mật
// phù hợp; để Spring khởi tạo bean ContextSource trước khi sử dụng.
~~~

Khi cấu hình `base = dc=example,dc=org`, các `base` truyền vào phương thức tìm kiếm Spring LDAP thường **tương đối với DN này**. Ví dụ `"ou=people"` trỏ tới `ou=people,dc=example,dc=org`, còn `""` biểu thị chính base đã cấu hình.

Để tìm referral theo cách có kiểm soát, chỉ bật `follow` khi các endpoint được giới thiệu là nguồn đáng tin cậy. Cần xác thực TLS, kiểm tra host và chứng chỉ, tránh gửi credential tới server không được phép và giới hạn số lần chuyển hướng. LDAP URL có thể chứa base DN, scope hoặc filter cần được provider xử lý; ứng dụng không nên tự nối URL không được kiểm tra vào filter/host của mình.

### 3.2. Nếu cần chủ động xử lý referral

Với JNDI thuần, `Context.REFERRAL="throw"` có thể làm xuất hiện `javax.naming.ReferralException` khi duyệt `NamingEnumeration`. Theo quy trình JNDI, ứng dụng có thể xem referral information, quyết định có cho phép server đích hay không, rồi lấy `referral context` để tiếp tục tìm.

`LdapTemplate` là lớp trừu tượng giúp quản lý context và chuyển ngoại lệ JNDI thành ngoại lệ Spring LDAP; nó **không cung cấp một luồng đơn giản để lựa chọn từng URL referral** trong kết quả search. Nếu nghiệp vụ đòi hỏi kiểm soát từng nguồn, có thể thiết kế điều phối theo danh sách server được phép và gọi các `ContextSource` riêng, hoặc thao tác JNDI cấp thấp có kiểm soát. Không mặc định rằng bắt `javax.naming.ReferralException` trực tiếp quanh `ldapTemplate.search(...)` là đủ.

## 4. PartialResultException thực sự báo điều gì?

Trong JNDI, `javax.naming.PartialResultException` mô tả tình huống **không thể hoàn tất việc trả toàn bộ kết quả**. Spring LDAP chuyển lỗi tương ứng thành ngoại lệ runtime `org.springframework.ldap.PartialResultException`.

Một tình huống hay gặp với Active Directory: truy vấn subtree vượt qua những nhánh có referral, nhưng provider JNDI không tự theo referral thành công. Khi duyệt kết quả, nó có thể phát sinh `PartialResultException` mặc dù đã trả về một số entry cục bộ.

Điều này dẫn đến các phân biệt quan trọng:

- **Kết quả đã nhìn thấy**: các entry client nhận được trước khi gặp vấn đề.
- **Kết quả đầy đủ**: mọi phần thuộc phạm vi mà hợp đồng nghiệp vụ yêu cầu đã được tìm thành công.
- **Ngoại lệ partial**: client không thể khẳng định điều kiện đầy đủ nói trên bằng lần tìm kiếm hiện tại.

`PartialResultException` **không đồng nghĩa** `sizeLimitExceeded`, `timeLimitExceeded` hay `adminLimitExceeded`. Các trường hợp giới hạn có result code và cách xử lý riêng; không được gộp mọi lỗi tìm kiếm thành “referral”.

## 5. Cờ ignorePartialResultException của Spring LDAP

`LdapTemplate` có cấu hình:

~~~java
ldapTemplate.setIgnorePartialResultException(false); // Mặc định
ldapTemplate.setIgnorePartialResultException(true);  // Cho phép bỏ qua ngoại lệ
~~~

Khi là `false`, ngoại lệ partial khiến lời gọi search báo lỗi; ứng dụng có thể thông báo rằng chưa xác nhận được kết quả hoàn chỉnh. Khi là `true`, `LdapTemplate` bỏ qua `PartialResultException` phát sinh trong quá trình tìm và phương thức có thể trả về **những entry thu thập được trước đó**.

Spring LDAP ghi nhận đây là một giải pháp thực dụng cho một số trường hợp Active Directory gặp vấn đề referral. Tuy nhiên:

> **Bỏ qua ngoại lệ không có nghĩa là đã tìm được toàn bộ nhánh.** Nếu API nghiệp vụ cần kết quả đầy đủ, đừng bật tùy chọn này như cách “sửa” dữ liệu thiếu.

Đặc biệt, `LdapTemplate` không cung cấp một cờ kết quả đơn giản cho biết đã bỏ qua bao nhiêu referral hoặc nhánh nào chưa được duyệt (ngoài thông tin chẩn đoán trong log). Vì thế không nên trả về `complete=true` chỉ vì một lời gọi với `ignorePartialResultException(true)` không ném ngoại lệ.

### 5.1. Trường hợp có thể cân nhắc bỏ qua

Một giao diện danh bạ **chỉ cần những tài khoản cục bộ tại một miền đã xác định**, đã có điều kiện phạm vi rõ ràng và chấp nhận kết quả giới hạn theo chính sách, đôi khi có thể chấp nhận cách xử lý partial này. Nhưng nên ưu tiên tìm tại search base thực sự nằm dưới nhánh được quản lý, với filter và scope chính xác, để tránh chạm referral không cần thiết.

Ngược lại, chức năng **kiểm kê tài khoản, kiểm tra quyền, thống kê toàn tổ chức hoặc đồng bộ toàn bộ dữ liệu** phải biết chính xác nguồn nào được quét và liệu có nguồn nào lỗi. Với các chức năng đó, nuốt `PartialResultException` có thể tạo dữ liệu sai mà không có tín hiệu rõ ràng.

### 5.2. Đừng nhầm với giới hạn số lượng và thời gian

`LdapTemplate` còn có các tùy chọn độc lập:

~~~java
ldapTemplate.setIgnoreSizeLimitExceededException(false);
ldapTemplate.setDefaultCountLimit(0);
ldapTemplate.setDefaultTimeLimit(0);
~~~

`defaultCountLimit=0` và `defaultTimeLimit=0` có nghĩa là **không áp hạn mức tương ứng ở phía client theo các thiết lập này**, không tắt hạn mức do server hoặc chính sách quản trị áp đặt. Theo API Spring LDAP, `ignoreSizeLimitExceededException` mặc định là `true`; nếu cần nhận biết truy vấn bị cắt bởi giới hạn số lượng, hãy cân nhắc đặt `false` và xử lý riêng `SizeLimitExceededException`. Với hệ thống thực, vẫn nên giới hạn scope, timeout và số entry tối đa theo SLA.

## 6. Ví dụ Java: tìm kiếm và không nuốt lỗi partial

Ví dụ sau dùng `LdapTemplate.search` với search base tương đối `ou=people`. Service chỉ trả danh sách nếu lời gọi search hoàn tất mà không báo `PartialResultException`; các lỗi LDAP khác vẫn được truyền ra để tầng ứng dụng phân loại.

~~~java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.PartialResultException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class PeopleSearchService {

    public record PersonView(String uid, String cn) {}

    private final LdapTemplate ldapTemplate;

    public PeopleSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonView> findPeople() {
        try {
            return ldapTemplate.search(
                "ou=people",
                "(objectClass=inetOrgPerson)",
                SearchControls.SUBTREE_SCOPE,
                new String[] {"uid", "cn"},
                (AttributesMapper<PersonView>) attributes ->
                    new PersonView(
                        stringValue(attributes, "uid"),
                        stringValue(attributes, "cn")
                    )
            );
        } catch (PartialResultException partial) {
            // Tầng gọi quyết định báo tìm kiếm chưa hoàn tất hoặc
            // chuyển sang quy trình tìm ở các nguồn LDAP được phép.
            throw new IllegalStateException(
                "Tìm kiếm LDAP chưa xác nhận được đầy đủ kết quả",
                partial
            );
        }
    }

    private static String stringValue(Attributes attributes, String id)
            throws NamingException {
        Attribute attribute = attributes.get(id);
        return attribute == null ? null : (String) attribute.get();
    }
}
~~~

Để bật chính sách phát hiện rõ lỗi partial và lỗi giới hạn kết quả, cấu hình `LdapTemplate` như sau:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;

@Configuration
public class DirectorySearchConfiguration {

    @Bean
    public LdapTemplate ldapTemplate(ContextSource source) {
        LdapTemplate template = new LdapTemplate(source);
        template.setIgnorePartialResultException(false);
        template.setIgnoreSizeLimitExceededException(false);
        return template;
    }
}
~~~

Đoạn mã giả định `ContextSource` đã có endpoint, bind account, TLS và base DN hợp lệ. Trường `uid`/`cn` trong ví dụ được ép kiểu `String` theo schema người dùng thường gặp; với thuộc tính nhị phân cần cách đọc phù hợp. `PersonView` là cấu trúc dữ liệu hiển thị; trong hệ thống thật có thể cần cả DN, định danh ổn định và thông tin nguồn để tránh trùng khi tìm nhiều server.

**Lưu ý về hợp đồng API:** đoạn mã ném lỗi nếu thư viện **phát hiện** partial result. Nếu một nguồn khác hoàn toàn không được khai báo trong cấu hình và server không gửi continuation reference, API không thể suy ra rằng nguồn đó tồn tại. Bảo đảm đầy đủ còn phụ thuộc định nghĩa **tất cả những nguồn cần tìm** của ứng dụng.

## 7. Thiết kế tìm kiếm qua nhiều nguồn một cách có kiểm soát

Khi phải tìm nhiều miền LDAP, một thiết kế tường minh thường dễ kiểm toán hơn việc mặc định theo mọi referral:

~~~mermaid
flowchart TD
    A["Yêu cầu tìm kiếm"] --> B["Xác định các nguồn được phép và search base"]
    B --> C["Gửi search tới từng nguồn với TLS, ACL, scope và filter đã kiểm soát"]
    C --> D{"Nguồn có lỗi/referral/giới hạn?"}
    D -->|Không| E["Ghi nhận kết quả và trạng thái nguồn"]
    D -->|Có| F["Đánh dấu nguồn chưa hoàn tất hoặc xử lý theo chính sách"]
    E --> G["Gộp và khử trùng lặp bằng định danh phù hợp"]
    F --> G
    G --> H{"Tất cả nguồn bắt buộc đã hoàn tất?"}
    H -->|Có| I["Trả kết quả đã xác nhận theo hợp đồng"]
    H -->|Không| J["Trả trạng thái không đầy đủ hoặc báo lỗi"]
~~~

Trong ứng dụng quy mô lớn, nên tách việc **tìm kiếm từng nguồn** khỏi việc **điều phối kết quả**:

1. Định nghĩa phạm vi nguồn bắt buộc, chẳng hạn `dc=corp,dc=example,dc=org` và `dc=partners,dc=example,dc=org`, cùng các endpoint/credential đủ quyền.
2. Dùng đúng `ContextSource` và cấu hình TLS cho từng nguồn. Không tự động sử dụng referral URL do một server lạ cung cấp.
3. Kiểm soát filter, search base và scope. Với dữ liệu đầu vào của người dùng, sử dụng `LdapQueryBuilder`/filter builder hoặc escape đúng RFC 4515, tránh ghép chuỗi filter từ đầu vào không tin cậy.
4. Ghi nhận cho từng nguồn: số entry đã nhận, trạng thái thành công/không đầy đủ, loại lỗi, thời gian và endpoint được gọi.
5. Nếu nhiều nguồn có thể trả cùng một entry, dùng định danh ổn định và có namespace nguồn khi gộp; DN và `uid` có thể không duy nhất giữa các directory khác nhau.
6. Chỉ đánh dấu kết quả **đầy đủ** nếu mọi nguồn **bắt buộc** theo hợp đồng đã hoàn tất và các giới hạn liên quan không làm cắt bớt kết quả.

Nếu ứng dụng hỗ trợ trạng thái từng nguồn, một response thiết kế ở tầng nghiệp vụ có thể mang dữ liệu như:

~~~json
{
  "items": [
    {"source": "corp", "uid": "an"},
    {"source": "corp", "uid": "binh"}
  ],
  "complete": false,
  "sources": [
    {"name": "corp", "status": "SUCCESS"},
    {"name": "partners", "status": "PARTIAL_OR_FAILED"}
  ]
}
~~~

Đây là **ví dụ hợp đồng ứng dụng tự thiết kế**, không phải JSON do LDAP hoặc `LdapTemplate` tự tạo. Nếu nguồn `partners` chưa hoàn tất, không được âm thầm bỏ trường `complete` rồi khiến caller hiểu danh sách là toàn bộ tổ chức.

## 8. Phân biệt partial result với các sự cố khác

| Triệu chứng | Nguyên nhân cần xem xét | Hướng xử lý |
| --- | --- | --- |
| Search trả một số entry rồi ném `PartialResultException` | Continuation reference/referral chưa được xử lý; đặc biệt trong một số môi trường Active Directory | Kiểm tra search base, `java.naming.referral`, các nhánh không cục bộ và chính sách completeness |
| Search trả danh sách nhưng thiếu entry ở server khác | Referral bị bỏ qua, server không giới thiệu nguồn hoặc ứng dụng chỉ quét nguồn cục bộ | So danh sách nguồn cần tìm và kiểm chứng độc lập các endpoint |
| `SizeLimitExceededException` | Giới hạn entry phía server hoặc client | Giảm scope/filter, xem paged results, xử lý cờ giới hạn riêng |
| `TimeLimitExceededException` | Vượt thời hạn tìm kiếm | Tối ưu filter/index, giảm phạm vi, xem timeout/server policy |
| `LimitExceededException` | Có thể vượt giới hạn quản trị hoặc referral-hop limit của JNDI | Kiểm tra diagnostic message và giới hạn cụ thể |
| `NameNotFoundException` | Search base không tồn tại hoặc không đúng base DN | Xác minh DN tương đối/tuyệt đối và naming context |
| `CommunicationException` hoặc lỗi TLS | Không kết nối được endpoint, chứng chỉ không hợp lệ hoặc timeout mạng | Kiểm tra DNS, TLS, mạng; không quy kết “0 kết quả” |
| Có kết quả trùng sau khi theo referral | Nguồn được truy vấn trùng nhau, cùng entry có nhiều đường tới | Dedupe theo định danh và nguồn, phân tích topology |

**Không có ngoại lệ** chưa đủ chứng minh dữ liệu đầy đủ nếu chính ứng dụng đã cấu hình bỏ qua lỗi hoặc không biết hết các nguồn cần truy vấn. Ngoài ra, kết quả tìm kiếm luôn chịu giới hạn bởi ACL: account chỉ có quyền đọc một phần cây không thể dùng kết quả để khẳng định không tồn tại các entry bị ẩn.

## 9. Kiểm thử tích hợp referral và partial result

Để kiểm thử có giá trị, cần môi trường LDAP thử nghiệm có topology đại diện: ít nhất một nhánh dữ liệu cục bộ và một nhánh referral/continuation tới nguồn khác, cùng account có quyền đã biết.

| Ca kiểm thử | Thiết lập | Điều cần khẳng định |
| --- | --- | --- |
| Tìm cục bộ | Search base chỉ chứa entry tại Server A | Danh sách đúng với dữ liệu cục bộ, không phát sinh referral |
| Search subtree qua nhánh không cục bộ | Server A giới thiệu Server B | Quan sát continuation reference và hành vi JNDI/Spring LDAP |
| `referral=ignore` | Không theo server được giới thiệu | Không nhầm tập cục bộ thành tập đầy đủ; ghi nhận exception nếu có |
| `referral=follow` | Server B cho phép kết nối và bind | Có thể nhận thêm kết quả; xác minh TLS, quyền và tổng tập |
| `referral=throw` | Provider phát sinh referral để caller xử lý | Luồng chủ động xử lý referral theo tầng JNDI được thiết kế |
| `ignorePartialResultException=true` | Dựng trường hợp provider báo partial | Method có thể trả dữ liệu cục bộ; nghiệp vụ không gắn nhãn complete |
| Server giới hạn số entry | Đặt size limit thấp hoặc tạo nhiều kết quả | Tách lỗi size limit khỏi partial/referral, không chấp nhận thống kê bị cắt |
| Paging kết hợp referral | Nguồn hỗ trợ RFC 2696 | Hết cookie không được xem là đã theo mọi referral |

Tại mỗi bước, đối chiếu số lượng và định danh entry với dữ liệu seed, không chỉ kiểm tra lời gọi search trả `List`. Nếu ứng dụng có nhiều node hoặc replica, cố định endpoint kiểm thử khi cần để tránh độ trễ replication làm nhiễu kết luận. Không dùng tài khoản production hoặc ghi credential/LDAP URL chứa bí mật vào log.

## 10. Bài tập vận dụng

Một ứng dụng dùng `ContextSource` với `base=dc=example,dc=org` và `referral=ignore`. Truy vấn subtree bắt đầu từ `""`, Server A có 120 entry cục bộ và Server B có thêm 35 entry trong nhánh được referral.

1. Nếu Server A trả 120 `SearchResultEntry` và một `SearchResultReference`, **120** có thể được khẳng định là tổng toàn hệ thống không? Vì sao?
2. Nếu JNDI phát sinh `PartialResultException`, bật `setIgnorePartialResultException(true)` có khiến Server B được tìm tự động không?
3. Nếu ứng dụng cần đúng toàn bộ **155 entry**, nên thay đổi chiến lược tìm kiếm và kiểm tra kết quả như thế nào?
4. Nếu Server A trả 120 entry kèm paging cookie rỗng, có thể kết luận đã nhận 35 entry ở Server B chưa?
5. Vì sao lỗi `SizeLimitExceededException` và `TimeLimitExceededException` phải được xử lý riêng với `PartialResultException`?

**Gợi ý:** (1) không, 120 chỉ là số entry đã nhận từ phần cục bộ; (2) không, tùy chọn chỉ bỏ qua ngoại lệ trong search; (3) theo referral hợp lệ hoặc tìm tường minh từng nguồn tin cậy, kiểm tra hoàn tất từng nguồn rồi gộp/dedupe; (4) không, cookie rỗng thuộc cơ chế phân trang; (5) chúng phản ánh giới hạn số lượng/thời gian với nguyên nhân, biện pháp khắc phục và mức bảo đảm khác nhau.

## 11. Ghi nhớ

- `SearchResultReference` là **gợi ý tiếp tục search ở nguồn khác**, khác với `SearchResultDone` có mã `referral` khi search base không nằm tại server và khác với paging cookie của RFC 2696.
- Chính sách `Context.REFERRAL` gồm **`ignore`**, **`follow`** và **`throw`**, áp dụng cho referral và continuation references; hành vi thực tế còn phụ thuộc JNDI provider và LDAP server.
- `LdapTemplate.setIgnorePartialResultException(true)` là cách bỏ qua ngoại lệ partial trong search, **không tự bảo đảm tính đầy đủ** hay tìm tất cả các nguồn.
- Phân biệt `PartialResultException` với lỗi giới hạn kích thước, thời gian, quyền và kết nối. Khi dữ liệu phải đầy đủ, hãy phát hiện riêng mỗi loại lỗi và xác minh tất cả nguồn cần thiết.
- Với truy vấn xuyên nhiều directory, xác định rõ scope, filter, endpoint, TLS, quyền đọc, dedupe và **trạng thái hoàn tất từng nguồn** trước khi công bố kết quả.

### Tài liệu tham khảo

- [RFC 4511 — LDAPv3, mục 4.5.3: Continuation References](https://www.rfc-editor.org/rfc/rfc4511.html#section-4.5.3)
- [RFC 2696 — Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696)
- [Oracle JNDI Tutorial — Referrals in the JNDI](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/jndi.html)
- [Oracle JNDI Tutorial — Manually Following Referrals](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/throw.html)
- [Oracle JNDI — LDAP Status Codes and Exceptions](https://docs.oracle.com/javase/jndi/tutorial/ldap/models/exceptions.html)
- [Spring LDAP — LdapTemplate API và setIgnorePartialResultException](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP — AbstractContextSource.setReferral](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextSource.html)
- [Spring LDAP — PartialResultException API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/PartialResultException.html)
