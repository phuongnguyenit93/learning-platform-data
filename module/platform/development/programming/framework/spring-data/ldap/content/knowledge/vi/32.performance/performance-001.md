# Đo độ trễ, thông lượng và số yêu cầu LDAP thực tế

Khi ứng dụng dùng **Spring Data LDAP** để đọc người dùng, nhóm hoặc cập nhật entry, thời gian trả lời chậm có thể đến từ kết nối mạng, bước lấy kết nối, xử lý ở máy chủ LDAP, số lần truy vấn, kích thước kết quả hoặc chính phần ánh xạ entry thành đối tượng Java. Chỉ quan sát rằng `repository.findByUid(...)` “chạy mất 100 ms” chưa đủ để biết phải tối ưu ở đâu.

Trong chương **Hiệu năng**, bài học này hướng dẫn đo ba đại lượng nền tảng: **độ trễ**, **thông lượng** và **số yêu cầu LDAP thực tế**. Mục tiêu là thiết lập phép đo có thể kiểm chứng từ ứng dụng Java tới dịch vụ thư mục, giải thích đúng DN, `objectClass`, schema, phạm vi tìm kiếm và số entry trả về; sau đó dùng bằng chứng để quyết định có cần điều chỉnh repository, `LdapTemplate`, kết nối hay truy vấn không.

## 1. Đặt câu hỏi đo lường trước khi tối ưu

Giả sử API `GET /users/{uid}` của một ứng dụng:

1. Nhận HTTP request.
2. Tra cứu tài khoản theo `uid` trong LDAP.
3. Đọc nhóm của người dùng để xác định quyền.
4. Ánh xạ LDAP entry về Java object.
5. Trả JSON cho client.

Một lần gọi API có thể phát sinh **nhiều thao tác LDAP**. Nếu mỗi nhóm lại cần một lookup bổ sung, độ trễ tăng lên cùng số nhóm; nếu dùng cơ chế phân trang, một tìm kiếm logic có thể tạo nhiều lần gửi yêu cầu search tới LDAP server. Ngược lại, khi đã dùng kết nối tái sử dụng, có thể không phát sinh thao tác bind mới ở mỗi request.

```text
Client
  │ GET /users/u1001
  ▼
HTTP Controller ─── Service ─── Repository / LdapTemplate
                          │
                          ├── LDAP search: người dùng
                          ├── LDAP search: nhóm
                          └── LDAP search: nhóm bổ sung (nếu có)
                                            │
                                            ▼
                                 LDAP directory server
```

Để đo có ý nghĩa, mỗi lần thực nghiệm phải nêu rõ: **nghiệp vụ đang đo**, **biên đo**, **loại thao tác LDAP**, **tập dữ liệu**, **cường độ tải**, **thời gian quan sát** và **điều kiện kết nối**.

## 2. Ba đại lượng phải phân biệt

| Đại lượng | Định nghĩa | Đơn vị thường dùng | Trả lời câu hỏi |
|---|---|---|---|
| Độ trễ (latency) | Thời gian từ lúc bắt đầu tới lúc kết thúc một thao tác theo biên đã chọn | ms, s | Một lời gọi mất bao lâu? |
| Thông lượng (throughput) | Số thao tác hoàn tất trong một khoảng thời gian | requests/s, LDAP operations/s | Hệ thống xử lý được bao nhiêu thao tác mỗi giây? |
| Số yêu cầu LDAP thực tế | Số thao tác giao thức được client gửi tới directory server trong cửa sổ đo | search, bind, modify, ... | Một nghiệp vụ đã tạo bao nhiêu tương tác LDAP? |

Ngoài ra cần đo **tỷ lệ lỗi**, **số entry trả về**, **kích thước response**, **số kết nối**, **hàng đợi chờ kết nối**, **timeout** và **cường độ truy cập đồng thời** để giải thích ba đại lượng trên.

### 2.1. Độ trễ: trung bình chưa đủ

Với `N` phép đo thời gian `t₁, t₂, ..., tₙ`:

```text
Độ trễ trung bình = (t₁ + t₂ + ... + tₙ) / N
```

Thường theo dõi thêm **p50**, **p95** và **p99**. Nếu p95 = 120 ms, có thể hiểu khoảng 95% phép đo hoàn tất trong **không quá** 120 ms, theo cách định nghĩa percentile của hệ thống đo. p99 mô tả phần đuôi chậm, hữu ích khi một số ít yêu cầu bị trì hoãn rất lâu. Những percentile này phải được tính từ dữ liệu đủ lớn trong cùng giai đoạn đo; p99 từ vài chục mẫu thường không đáng tin.

Ví dụ minh họa (không phải kết quả đo thật):

| Thước đo | LDAP lookup trong ứng dụng | Toàn bộ HTTP request |
|---|---:|---:|
| p50 | 18 ms | 35 ms |
| p95 | 68 ms | 110 ms |
| p99 | 145 ms | 260 ms |

Không lấy p95 của từng bước cộng lại để suy ra p95 toàn tuyến: các bước có phân phối và tương quan khác nhau. Hãy đo **toàn bộ đường đi** nếu mục tiêu là SLO của API.

### 2.2. Thông lượng: cần nói rõ đang đếm gì

```text
Thông lượng = Số thao tác hoàn tất / Thời gian quan sát (giây)
```

Ví dụ trong một cửa sổ ổn định 60 giây:

- Hoàn tất 1.200 HTTP request ⇒ **20 HTTP requests/s**.
- Máy chủ LDAP ghi nhận 3.000 thao tác từ luồng tải đang thử ⇒ **50 LDAP operations/s**.
- Trung bình mỗi HTTP request tạo **3.000 / 1.200 = 2,5 thao tác LDAP**.

Ba con số này chỉ liên hệ trực tiếp khi toàn bộ 3.000 thao tác LDAP thực sự thuộc đúng 1.200 request đó, không bị lẫn traffic nền, hoạt động quản trị hoặc client khác. Vì vậy, phải xác định cách lọc/correlation nguồn đo.

**Throughput cao không đồng nghĩa hiệu năng tốt** nếu tỷ lệ lỗi, độ trễ p99 hoặc số lần timeout tăng. Khi đo tải, công bố cả throughput thành công lẫn tổng số thao tác hoàn tất, đồng thời theo dõi tỷ lệ lỗi riêng.

### 2.3. “Số yêu cầu LDAP” có nhiều cách đếm

| Đơn vị được đếm | Ví dụ | Có đại diện cho yêu cầu LDAP thực tế không? |
|---|---|---|
| HTTP request | `GET /users/u1001` | Không; có thể không có hoặc có nhiều thao tác LDAP |
| Lần gọi repository | `findByUid(...)` | Không chắc; một method không bảo đảm đúng một thao tác giao thức |
| Lần gọi `LdapTemplate` | `find(query, Person.class)` | Chỉ đo lời gọi client ở mức API; có thể có thêm bind, referral, page, retry |
| LDAP search operation trên dây | Search request theo LDAP protocol | Có, với loại thao tác **search** |
| LDAP bind/modify/add/delete/compare/modifyDN | Các thao tác giao thức khác | Có, nhưng phải thống nhất chúng có được đưa vào tổng hay không |
| Entry tìm được | `nentries=400` | Không; một search có thể trả nhiều entry |
| Dòng log của server | Một dòng SEARCH và một dòng RESULT | Không; có thể là hai dòng cho cùng một operation |

Một **LDAP search** có thể trả 0, 1 hoặc hàng nghìn entry; số entry và số search request là hai số khác nhau. Nếu phân trang ở phía LDAP, client thường phát sinh **một search request cho mỗi trang**. Nếu tìm kiếm kéo theo referral tới server khác hoặc retry khi lỗi, tổng số thao tác trên tất cả máy chủ cũng có thể cao hơn số lời gọi Java.

Hãy đặt tên metric theo đúng thực thể đang đếm, ví dụ `ldap.client.logical.calls` và `ldap.server.search.operations`, thay vì dùng tên mơ hồ như `ldap.requests`.

## 3. Định nghĩa biên đo và chia độ trễ theo tầng

Đối với ứng dụng Java, nên chọn ít nhất ba biên đo:

1. **End-to-end API:** từ lúc request tới ứng dụng đến lúc response hoàn tất. Bao gồm logic nghiệp vụ, LDAP và serialization.
2. **LDAP client call:** bao quanh lời gọi repository hoặc `LdapTemplate`; bao gồm phần xử lý ở client, lấy kết nối nếu có, giao tiếp mạng, chờ server và ODM mapping.
3. **LDAP server operation:** thời gian server xử lý search/modify theo cơ chế đo của server. Không nhất thiết bao gồm toàn bộ RTT mạng và thời gian ứng dụng ánh xạ kết quả.

```text
|<---------------------- API latency ---------------------->|
   xác thực       xử lý nghiệp vụ        serialize response
                    |<--- LDAP client latency --->|
                      lấy context / connection
                      |<-- mạng + server + mạng -->|
                                |<server time>|
                                ánh xạ LDAP entry → Java object
```

Sơ đồ chỉ minh họa các thành phần thời gian; từng bước có thể chồng lấn hoặc xen kẽ. Nếu chỉ đo `LdapTemplate.find(...)`, bạn có thể biết lời gọi LDAP ở phía ứng dụng chậm, nhưng **chưa thể kết luận LDAP server chậm**. Cần đối chiếu thời gian xử lý tại server, số kết nối, trạng thái mạng và profile của JVM.

Khi đo một thao tác trong code Java, ưu tiên đồng hồ **monotonic** (`System.nanoTime()` hoặc `Micrometer Timer`) thay vì lấy chênh lệch `System.currentTimeMillis()`, vì đồng hồ lịch có thể bị hiệu chỉnh. Với các log giữa nhiều máy chủ, nên đồng bộ thời gian hệ thống và dùng correlation ID; chênh lệch timestamp không chính xác nếu đồng hồ lệch nhau.

## 4. Gắn metric vào Spring Data LDAP ở mức ứng dụng

Giả sử thư mục có các entry `inetOrgPerson` dưới `ou=people,dc=example,dc=org`; ứng dụng cấu hình `LdapContextSource` với base `dc=example,dc=org`. Một entity ODM tối giản:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(objectClasses = {"inetOrgPerson"})
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    public DirectoryPerson() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) { this.commonName = commonName; }
}
```

Đo thời gian một truy vấn bằng **Micrometer `Timer`**:

```java
import java.util.List;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class DirectoryLookupService {
    private final LdapTemplate ldapTemplate;
    private final MeterRegistry metrics;

    public DirectoryLookupService(LdapTemplate ldapTemplate,
                                  MeterRegistry metrics) {
        this.ldapTemplate = ldapTemplate;
        this.metrics = metrics;
    }

    public List<DirectoryPerson> findByUid(String uid) {
        Timer.Sample sample = Timer.start(metrics);
        String outcome = "error";

        try {
            LdapQuery ldapQuery = query()
                    .base("ou=people")
                    .where("uid").is(uid);

            List<DirectoryPerson> people =
                    ldapTemplate.find(ldapQuery, DirectoryPerson.class);

            outcome = "success";
            return people;
        } finally {
            sample.stop(metrics.timer(
                    "ldap.client.logical.duration",
                    "operation", "search_by_uid",
                    "outcome", outcome));
        }
    }
}
```

Mỗi lần phương thức kết thúc, `Timer` lưu **số phép đo**, **tổng thời gian** và dữ liệu phân phối theo cấu hình hệ thống metric. Để lấy p95/p99 từ hệ thống giám sát, cần cấu hình histogram/SLO phù hợp với backend được dùng; không phải mọi exporter đều có sẵn percentile mặc định.

Ở đây, nhãn `operation=search_by_uid` chỉ ra **loại nghiệp vụ**; `outcome` phân biệt thành công/lỗi. Đừng gắn trực tiếp giá trị `uid`, DN, email hoặc filter đầy đủ thành nhãn metric: chúng vừa có thông tin nhạy cảm vừa tạo **cardinality rất cao**. Cũng không nên log nguyên văn mật khẩu bind.

**Giới hạn của phép đo này:** `Timer.count()` là số lần gọi `findByUid` được đo, **không phải** số LDAP search/bind thực sự trên mạng. Để xác nhận số request giao thức, cần nguồn dữ liệu khác ở phần tiếp theo.

Đo repository tương tự: đặt `Timer` ở service gọi `LdapRepository`. Nếu muốn phân rã kỹ hơn, đặt instrumentation tại tầng truy cập LDAP dùng chung, nhưng cần tránh đếm kép khi một service gọi nhiều method cùng lớp. Không tùy tiện thay thế hạ tầng Spring LDAP bằng wrapper tự chế nếu nó làm thay đổi xử lý kết nối, transaction hay exception.

## 5. Đếm thao tác LDAP thực tế: đối chiếu phía client và server

Khi câu hỏi là **“1.000 request nghiệp vụ đã tạo bao nhiêu LDAP search/bind/modify?”**, cần có số đo đáng tin từ đường giao tiếp LDAP:

| Nguồn quan sát | Thu được gì? | Giới hạn cần biết |
|---|---|---|
| Log truy cập của LDAP server | Thao tác `SEARCH`, `BIND`, `MODIFY`, kết quả, mã lỗi, có thể có thời gian | Cú pháp và khả năng log tùy loại server; phải lọc đúng client/cửa sổ |
| Bộ đếm/monitoring của directory | Lưu lượng thao tác, số kết nối, lỗi, tài nguyên server | Có thể chỉ là tổng toàn server, thiếu nhãn theo ứng dụng |
| Instrumentation ở tầng LDAP client | Lần gửi thao tác, retry, phân trang, referral nếu được công cụ ghi nhận đúng | Khả năng can thiệp tùy thư viện/provider; wrapper API không luôn nhìn thấy thao tác giao thức |
| Network capture | Kết nối, kích thước và thời gian truyền tải | Khi dùng LDAPS/StartTLS, nội dung giao thức được mã hóa; không đọc được search/bind chỉ từ gói tin đã mã hóa |
| Trace của ứng dụng | Mối liên hệ giữa HTTP request và lời gọi LDAP logic, thời gian từng span | Chỉ là số request LDAP thật nếu instrumentation thực sự bắt được từng thao tác protocol |

Ví dụ trên **OpenLDAP** khi bật mức ghi log thống kê phù hợp, máy chủ có thể ghi các sự kiện biểu thị `conn`, `op`, `SEARCH` và `RESULT`. Hai dòng với cùng `conn/op` thường mô tả **một** search và kết quả tương ứng; không được cộng cả hai làm hai request. Với Active Directory, 389 Directory Server hoặc sản phẩm khác, tên trường, cách cấu hình log và độ đầy đủ khác nhau. Hãy dùng khả năng quan sát mà máy chủ cụ thể hỗ trợ.

Để có số lượng chính xác hơn, nên thực hiện:

1. Chọn một **cửa sổ thời gian** rõ ràng, ví dụ 10 phút tải ổn định sau warm-up.
2. Phân biệt client/ứng dụng bằng tài khoản bind, địa chỉ mạng, kết nối hoặc correlation được hệ thống hỗ trợ. Nếu nhiều ứng dụng dùng chung account/IP, chỉ lọc account/IP có thể vẫn sai.
3. Đếm **operation** theo loại, dựa trên mã định danh operation trong log hoặc bộ đếm thích hợp; loại bỏ bản ghi kết quả trùng với bản ghi yêu cầu.
4. Nếu có nhiều replica, referral hoặc proxy LDAP, tổng hợp đúng các server liên quan; một server đơn lẻ có thể không thấy toàn bộ request.
5. So với số request nghiệp vụ và số lần gọi LDAP logic trong cùng cửa sổ. Ghi nhận traffic nền và các đợt đối soát khác.
6. Xác minh tính hợp lý: số lượng search có khớp chiến lược lookup không? Có nhiều `BIND` bất thường? Có trang kết quả hoặc retry làm số operation tăng không?

**Phân biệt `bind` với “người dùng đăng nhập”:** LDAP bind là thao tác xác thực/kết nối tới directory. Một pool kết nối có thể bind lúc tạo kết nối; một ứng dụng có thể xác thực người dùng qua bind riêng hoặc sử dụng cơ chế khác. Do đó, số LDAP bind không nhất thiết bằng số lần người dùng bấm đăng nhập.

### Ví dụ bảng đối chiếu có thể kiểm toán

Giả sử một bài kiểm tra trong đúng 60 giây và cô lập được traffic của ứng dụng:

| Phép đếm trong cùng cửa sổ | Giá trị minh họa |
|---|---:|
| HTTP request đã hoàn tất | 1.200 |
| Lần gọi `findByUid` được ghi metric | 1.200 |
| Search request LDAP tới các server liên quan | 2.400 |
| Bind request LDAP | 80 |
| Other LDAP operations | 20 |
| Tổng LDAP operations | 2.500 |
| LDAP operations / HTTP request | ~2,08 |
| LDAP search operations / `findByUid` call | 2,0 |

**Không kết luận vội:** `2,0 search/call` là dấu hiệu cần điều tra, không chứng minh method `findByUid` tự thực hiện hai search. Các search khác của cùng HTTP request, phân trang, lookup nhóm, retry hoặc traffic nền chưa lọc hết đều có thể tạo ra tỷ lệ đó. Cần trace/correlation và kiểm tra log để gán chính xác mỗi thao tác về nguồn.

## 6. Đo thông lượng và độ trễ dưới tải tăng dần

Một phép đo đơn lẻ từ môi trường phát triển chỉ cho biết thời gian trong điều kiện hiện tại. Để hiểu hiệu năng ở tải thực tế, cần thiết kế thử nghiệm có thể lặp lại:

**Thiết lập môi trường:**

- Dùng directory thử nghiệm với **schema, kích thước cây, objectClass, chỉ mục (index), kích thước nhóm và ACL** gần với môi trường sẽ vận hành. Giữ mật khẩu và dữ liệu cá nhân thật ngoài bộ thử.
- Ghi rõ phiên bản ứng dụng, JVM, cấu hình `LdapContextSource`, base DN, filter, search scope, connection pooling, TLS, số replica và giới hạn size/time của LDAP server.
- Phân loại truy vấn **tìm thấy 1 entry**, **không tìm thấy**, **trả nhiều entry**; dữ liệu thử phải đại diện để tránh đo toàn bộ trên một entry đã được cache.
- Phân biệt thao tác chỉ đọc với ghi. Chỉ kiểm tra `add`/`modify`/`delete` trên dữ liệu và directory được phép dùng cho test.

**Kịch bản tải minh họa:**

| Pha | Tải được phát | Thời gian đề xuất | Mục tiêu |
|---|---|---|---|
| Warm-up | Tải thấp, ổn định | Vài phút | Ổn định JIT, pool kết nối và cache |
| Baseline | 1–5 business requests/s | Đủ mẫu | Có số tham chiếu khi server chưa bão hòa |
| Tăng tải | 10, 20, 40 requests/s (ví dụ) | Mỗi mức đủ lâu | Xem p95/p99, lỗi và thông lượng biến đổi |
| Tải mục tiêu | Mức dự kiến vận hành | Nhiều phút liên tục | Kiểm tra đạt SLO ở tải mục tiêu |
| Hồi phục | Giảm tải về baseline | Đủ thời gian | Kiểm tra timeout/hàng đợi và tài nguyên hồi phục |

Các mức trên chỉ là **ví dụ**, không phải giá trị mặc định phù hợp mọi directory. Thời gian và mức tải phải tương ứng dung lượng môi trường, mục tiêu nghiệp vụ và giới hạn vận hành.

Ở mỗi mức tải, ghi riêng: số request được phát, số request hoàn tất, số thành công, số lỗi, throughput thành công, p50/p95/p99 end-to-end, p95 thời gian LDAP client, số LDAP operations, tỷ lệ operations/business request và tài nguyên của ứng dụng/LDAP server. Khi tăng tải, có thể thấy số concurrent request tăng nhưng throughput đứng yên, p99 và timeout tiếp tục tăng — dấu hiệu hệ thống đang gặp nút thắt.

Không so sánh hai lần đo nếu một bên dùng kết nối mới và bên kia dùng pool nóng, hoặc một bên tìm một user còn bên kia tìm nhóm hàng nghìn thành viên, mà không ghi rõ sự khác biệt đó.

## 7. Thiết kế truy vấn ảnh hưởng trực tiếp đến số yêu cầu và thời gian

### 7.1. Search base và phạm vi tìm kiếm

LDAP tìm entry trong cây theo DN, base và search scope. Với cấu hình context base `dc=example,dc=org`, một truy vấn:

```java
LdapQuery ldapQuery = query()
    .base("ou=people")
    .where("uid").is(userInput);
```

chỉ định vùng tìm kiếm `ou=people` tương đối với context base. Nếu dữ liệu cần tìm chỉ ở một OU, thu hẹp base có thể giảm số entry cần xét. Scope `ONELEVEL` chỉ quét các entry con trực tiếp; scope `SUBTREE` tìm trong cả cây con. Chọn theo cấu trúc DN thực tế; dùng scope hẹp quá có thể bỏ sót entry, dùng scope rộng quá có thể tăng chi phí.

Filter builder của Spring LDAP xử lý escaping giá trị theo cú pháp LDAP filter; **không nối chuỗi** `"(uid=" + userInput + ")"`. Ngoài rủi ro LDAP injection, bộ lọc tùy tiện có thể vô tình mở rộng phạm vi tìm kiếm và làm sai phép đo.

### 7.2. Index và schema

Một search `(uid=u1001)` có thể nhanh hơn trên directory có index phù hợp, nhưng index cụ thể và hành vi tối ưu hóa **phụ thuộc LDAP server**. Cần kiểm tra bằng số liệu server, không giả định mọi thuộc tính đã được index. `objectClass`, matching rule và kiểu thuộc tính ảnh hưởng đến cách so khớp; filter tìm substring/wildcard có thể đắt hơn equality filter.

Index không làm giảm số LDAP request của một lookup, nhưng thường có thể giảm thời gian xử lý tại server. Vì vậy, khi **số request gần như không đổi nhưng server time giảm**, đó là kiểu cải thiện khác với việc loại bỏ một lookup thừa.

### 7.3. N+1 search khi đọc nhóm

Giả sử một user thuộc 20 nhóm, ứng dụng lấy user rồi lần lượt tải từng nhóm:

```text
1 search user + 20 search nhóm = 21 search operations (trong ví dụ đơn giản)
```

Đây là mô hình N+1 ở tầng truy vấn directory. Đọc nhóm bằng filter phù hợp, lấy các thuộc tính cần thiết theo khả năng server, hoặc điều chỉnh thiết kế truy cập có thể giảm request; tuy nhiên cần kiểm chứng quyền ACL, tính nhất quán và độ lớn kết quả. **Không mặc định LDAP hỗ trợ join quan hệ hay JPA lazy loading** khi ODM ánh xạ entry.

### 7.4. Phân trang, giới hạn kết quả và thuộc tính đa trị

Một truy vấn trả 5.000 entry có thể bị server giới hạn hoặc phải phân trang; khi đó **1 lời gọi nghiệp vụ** có thể dẫn tới nhiều search requests hoặc nhiều round trip. Cần đo đồng thời `nentries`, số trang, số bytes, số query và thời gian mapping.

Với entry nhóm có nhiều giá trị `member`, payload và xử lý phía client có thể lớn dù chỉ có một entry trả về. Số entry thấp không đồng nghĩa payload nhỏ. Directory khác nhau cũng có quy định riêng về cách lấy các thuộc tính nhiều giá trị lớn; không được mặc định mọi server trả toàn bộ giá trị theo cùng cách.

### 7.5. Kết nối, bind và TLS

Nếu ứng dụng mở kết nối và thực hiện bind mới cho hầu hết request, chi phí kết nối/TLS/bind có thể lấn át chi phí search. Pooling và tái sử dụng kết nối có thể giúp, nhưng phải đo thêm số kết nối đang dùng, thời gian chờ pool, timeout, số bind và giới hạn kết nối trên server.

**Không tắt LDAPS/StartTLS hoặc bỏ xác thực chứng chỉ để lấy số benchmark đẹp** rồi dùng kết quả đó làm căn cứ vận hành. Bảo mật kết nối là một phần của điều kiện tải thực tế.

## 8. Tách lỗi khỏi chậm và tránh các kết luận sai

LDAP có thể trả lỗi do schema, DN, filter, timeout, ACL hoặc kết nối. Một thống kê chỉ lấy các request thành công có thể che giấu việc nhiều request chậm đã timeout. Đối với từng loại operation, ghi:

```text
attempted = success + failure + cancelled/timed-out (theo quy ước đo)
error_rate = failure / attempted
```

Cần thống nhất cách tính timeout và hủy yêu cầu: một **timeout ở phía Java** không chứng minh LDAP server đã hủy xử lý đúng thời điểm; thao tác có thể vẫn tiếp tục ở server. Đặt tên riêng cho timeout phía ứng dụng và lỗi trả về từ LDAP để tránh nhầm.

Một số cách diễn giải sai thường gặp:

| Quan sát | Kết luận thiếu căn cứ | Cách kiểm tra tiếp |
|---|---|---|
| `findByUid` p95 tăng | LDAP server chắc chắn chậm | So client latency với server time, network và pool wait |
| 1 repository call | Chắc chắn chỉ 1 LDAP request | Đếm search/bind/paging/referral ở tầng giao thức |
| Server trả 2.000 entry | Đã phát 2.000 request | Xem số operation; một search có thể trả nhiều entry |
| Average latency giảm | Trải nghiệm người dùng tốt hơn | Xem p95/p99, timeout, error rate ở tải tương đương |
| Throughput tăng khi tăng concurrency | Có thể tăng không giới hạn | Kiểm tra điểm bão hòa, queue, lỗi, CPU và connection limit |
| Search trả 0 entry rất nhanh | Truy vấn tối ưu | Xác nhận đúng base DN, ACL, filter và dữ liệu thử |
| Thời gian server thấp, client cao | LDAP là nút thắt | Kiểm tra truyền tải, TLS, mapping, pool và kích thước payload |

Khi có nhiều LDAP replica, hãy xem **phân bố lưu lượng và latency theo từng endpoint**. Một replica lỗi hoặc bị lag có thể làm tăng p99 mặc dù tổng trung bình vẫn tốt. Nếu chọn một endpoint cho test và vận hành qua load balancer nhiều endpoint, kết quả không hoàn toàn tương đương.

## 9. Ví dụ thử nghiệm có thể lặp lại

Giả sử yêu cầu nghiệp vụ là: **ở tải 20 API requests/s, p95 của API tìm user dưới 200 ms, tỷ lệ lỗi dưới 0,5%, và trung bình không quá 3 LDAP search trên một API request**. Đây là mục tiêu minh họa, không phải SLO mặc định của Spring Data LDAP.

**Bước 1 — Chốt workload:** 80% tìm user có tồn tại, 20% không tồn tại; một phần user có 0 nhóm và một phần có nhiều nhóm. Dữ liệu được giữ cố định giữa các lượt chạy, trừ khi đang thử CRUD.

**Bước 2 — Đo ở ứng dụng:** ghi `http.server.requests` (nếu ứng dụng có instrumentation), `ldap.client.logical.duration`, response status và thời gian tầng service. Cần có một correlation ID ở ranh giới API để đối chiếu log; tránh ghi thông tin nhận dạng cá nhân vào nhãn.

**Bước 3 — Đo ở directory:** lấy access log hoặc metrics cho chính kết nối/tài khoản thử nghiệm, đếm search/bind/modify và các kết quả theo server. Nếu directory dùng nhiều node, thu thập đủ node.

**Bước 4 — Chạy warm-up rồi tải ổn định:** dùng cùng kịch bản, cùng cấu hình pool/TLS, cùng số client và cùng tập tài khoản; đo lặp lại để thấy độ dao động. Không dùng một truy vấn thủ công đơn lẻ làm số liệu thay thế toàn bộ workload.

**Bước 5 — Lập bảng kết quả:** ví dụ tổng hợp sau đây đều là **số liệu giả định**:

| Thước đo | 5 requests/s | 20 requests/s | 40 requests/s |
|---|---:|---:|---:|
| Throughput API hoàn tất | 5/s | 20/s | 33/s |
| API p95 | 48 ms | 132 ms | 510 ms |
| API p99 | 88 ms | 245 ms | 1.200 ms |
| LDAP client p95 | 30 ms | 84 ms | 360 ms |
| LDAP search / API request | 2,0 | 2,1 | 2,2 |
| Tỷ lệ API lỗi | 0% | 0,1% | 4,0% |

Theo dữ liệu giả định, mức 20 requests/s đạt các mục tiêu p95, tỷ lệ lỗi và số search; mức 40 requests/s không giữ nổi throughput tương ứng với tải phát, trong khi p95/p99 và lỗi tăng. Bước tiếp theo là so server time, pool wait, giới hạn search/index và tài nguyên JVM/directory ở mức tải 40/s để tìm đúng nút thắt. Bảng này không đủ để kết luận tăng pool hay thêm node sẽ chắc chắn giải quyết vấn đề.

## 10. Checklist trước khi báo cáo kết quả

Một báo cáo đo hiệu năng Spring Data LDAP có thể được người khác kiểm tra lại nếu nêu:

1. **Mục tiêu:** thao tác nghiệp vụ, SLO và lý do cần đo (chậm, lỗi, chi phí directory).
2. **Môi trường:** app/JVM, Spring Data LDAP và directory, schema/index, số bản ghi, OU, TLS, pooling, network và replica.
3. **Workload:** tỷ lệ tìm thấy/không tìm thấy, lọc theo thuộc tính nào, độ lớn nhóm, số client, concurrency, thời gian warm-up/steady-state.
4. **Định nghĩa metric:** biên đo độ trễ, kiểu operation được đếm, cách tính throughput, cách tính lỗi và cách tổng hợp percentile.
5. **Nguồn số liệu:** metric ứng dụng, access log/counter của directory, trace/correlation, thời điểm và cách lọc traffic.
6. **Kết quả:** p50/p95/p99, successful throughput, error rate, LDAP operations theo loại, operations/business request, thời gian và tài nguyên server.
7. **Giới hạn:** traffic khác không tách hết, log thiếu, clock lệch, ít mẫu, chỉ đo một replica, filter khác workload thật hoặc workload phụ thuộc cache.
8. **Giả thuyết cần thử:** ví dụ bỏ lookup nhóm lặp, giảm search scope, thêm index theo đặc tính server hoặc điều chỉnh connection pool — mỗi thay đổi được đo lại trong cùng điều kiện.

**Câu hỏi tự kiểm tra:**

- `findByUid()` trả một entry nhưng log có ba search. Hãy nêu ít nhất ba nguyên nhân khả dĩ và cách phân biệt.
- Vì sao `Timer.count()` ở repository không thể thay thế access log LDAP khi muốn biết số protocol request?
- Một lần chạy có p50 = 15 ms và p99 = 2 s. Báo cáo riêng thời gian trung bình có thể bỏ sót vấn đề gì?
- Nếu tăng concurrency từ 20 lên 100 mà throughput chỉ tăng nhẹ, cần theo dõi những metric nào trước khi điều chỉnh pool?
- Trong truy vấn có input từ người dùng, vì sao phải dùng filter builder và giới hạn base/scope trước khi tối ưu tốc độ?

**Ghi nhớ:** đo **thời gian mỗi nghiệp vụ**, **số nghiệp vụ hoàn tất mỗi giây** và **số LDAP operation thật trên server** là ba việc khác nhau. Spring Data LDAP cung cấp repository và `LdapTemplate` để đọc/ghi entry qua DN, `objectClass`, schema và LDAP filter; instrumentation ở Java cho biết thời gian lời gọi logic, còn log/counter của directory giúp kiểm chứng số thao tác giao thức. Chỉ khi ghép các nguồn đo trong cùng workload mới có thể tối ưu đúng nguyên nhân và xác nhận cải thiện bằng số liệu.
