# Kiểm soát cache dữ liệu thư mục và thời gian hết hạn

## 1. Vì sao cache LDAP phải là quyết định thiết kế ứng dụng?

Một ứng dụng dùng **Spring LDAP** thường tra cứu cùng tài khoản nhiều lần: lấy tên hiển thị để dựng giao diện, đọc email công việc, xác định phòng ban, kiểm tra nhóm hoặc tìm DN của một entry. Đọc trực tiếp từ directory cho mọi request tạo độ trễ mạng, tiêu thụ connection của **ContextSource**, tăng tải LDAP server và khiến ứng dụng nhạy cảm với các đợt chậm kết nối.

Cache giúp giảm số lần truy vấn nhưng tạo ra một nguồn dữ liệu **có thể cũ hơn directory**. Ví dụ:

1. Lúc 09:00, ứng dụng cache nhóm LDAP của nhân viên Lan với TTL 5 phút.
2. Lúc 09:01, quản trị viên xóa Lan khỏi nhóm được phép truy cập tài liệu mật.
3. Lúc 09:03, API vẫn đọc group membership từ cache.
4. Nếu API dùng kết quả cũ để cấp quyền, Lan có thể tiếp tục truy cập dù đã bị thu hồi quyền trên directory.

TTL 5 phút có thể chấp nhận được với **tên hiển thị**, nhưng thường không đáp ứng yêu cầu **thu hồi quyền ngay lập tức**. Vì vậy câu hỏi không chỉ là *“bật cache ở đâu?”* mà là *“dữ liệu nào được cache, cũ tối đa bao lâu, ai được dùng kết quả cũ và khi nào phải đọc LDAP?”*

Trong chương **Thiết kế ứng dụng**, chúng ta xây ranh giới giữa **domain/application service** và LDAP adapter, quy định tính tươi mới theo loại dữ liệu, dùng **LdapTemplate** cùng Caffeine cho cache có TTL, xử lý invalidation, outage, multi-instance và kiểm thử. Kiến thức này cũng áp dụng nếu đổi sang **LdapClient** hoặc Spring LDAP ODM: công nghệ truy vấn có thể thay đổi, còn hợp đồng về độ tươi mới và an toàn phải được giữ.

## 2. Các khái niệm cần phân biệt

| Thuật ngữ | Ý nghĩa | Hệ quả thiết kế |
| --- | --- | --- |
| **Cache hit** | Có kết quả trong cache còn hiệu lực | Không phải gọi LDAP cho request đó |
| **Cache miss** | Không có kết quả hoặc đã hết hạn | Phải đọc nguồn dữ liệu theo chính sách |
| **TTL (Time To Live)** | Khoảng thời gian một bản cache được xem là hợp lệ | Giới hạn tuổi bản cache trong hệ thống đang lưu |
| **Expire after write** | Hết hạn sau một khoảng từ lúc ghi/cache refresh | Người dùng truy cập liên tục vẫn không làm dữ liệu sống mãi |
| **Expire after access** | Gia hạn thời gian tồn tại sau mỗi lần truy cập | Dễ giữ dữ liệu cũ rất lâu nếu request thường xuyên |
| **Negative caching** | Cache kết quả hợp lệ “không tìm thấy” | Giảm tải miss lặp lại nhưng làm chậm việc nhận ra entry mới |
| **Invalidation** | Chủ động loại một key/nhóm key khỏi cache | Giảm độ trễ cập nhật khi có sự kiện đáng tin cậy |
| **Stale data** | Dữ liệu còn trong cache nhưng không còn giống nguồn | Có thể chỉ ảnh hưởng hiển thị hoặc gây lỗi phân quyền |
| **Cache stampede** | Nhiều request cùng đọc lại một key khi hết hạn | Tạo đỉnh tải LDAP nếu không đồng bộ việc nạp cache |

TTL của cache cục bộ **không bảo đảm** dữ liệu phản ánh thay đổi từ LDAP trong chính khoảng thời gian đó nếu LDAP đang trả dữ liệu cũ từ một replica, có quá trình đồng bộ upstream, hoặc ứng dụng có thêm cache khác. Độ trễ tổng thể phải xem cả đường đi từ **nguồn ghi → LDAP/replica → cache → người dùng**.

## 3. Phân loại dữ liệu trước khi đặt TTL

Không nên dùng một TTL chung cho mọi thuộc tính LDAP. Một chính sách ban đầu có thể như sau; **các giá trị chỉ là ví dụ để thảo luận**, phải được điều chỉnh theo SLA, tần suất thay đổi và mức rủi ro thực tế.

| Loại dữ liệu | Ví dụ | Chính sách minh họa | Khi dữ liệu cũ |
| --- | --- | --- | --- |
| Hồ sơ phục vụ hiển thị | **cn**, tên hiển thị, ảnh đại diện nhỏ | Cache 2–10 phút, có invalidation | Tên/ảnh xuất hiện muộn; thường chấp nhận được |
| Thuộc tính liên hệ | **mail**, phòng ban, số điện thoại công việc | Cache 1–5 phút tùy nghiệp vụ | Có thể gửi thông báo sai người, nên thận trọng |
| Danh mục tổ chức | Tên đơn vị, OU phục vụ tìm kiếm | Cache có hạn và làm mới định kỳ | Cấu trúc cây hoặc đường dẫn entry thay đổi |
| Kết quả tìm kiếm không có entry | Không tìm thấy **uid=lan** | Negative TTL rất ngắn, ví dụ 5–15 giây | Entry mới tạo chưa được thấy ngay |
| Group/entitlement phục vụ giao diện | Nhóm hiển thị trong trang quản trị | TTL ngắn và invalidation | Giao diện hiển thị vai trò cũ |
| Group/entitlement quyết định quyền | **member**, **memberOf** hoặc thông tin thu hồi quyền | Không tùy tiện dùng cache hồ sơ; cần freshness contract riêng, có thể kiểm tra nguồn trực tiếp | Có nguy cơ cấp quyền sau khi bị thu hồi |
| Trạng thái khóa/vô hiệu hóa tài khoản | Account disabled, trạng thái xác thực | Chính sách an ninh riêng, ưu tiên kiểm tra đáng tin cậy ở điểm ra quyết định | Rủi ro cho phép tài khoản đã bị khóa |
| Mật khẩu, credential, kết quả bind mật khẩu | Password, kết quả đăng nhập | **Không cache** bằng cơ chế cache hồ sơ | Rủi ro bảo mật và che thay đổi credential |

Nếu ứng dụng có giới hạn “thu hồi quyền phải có hiệu lực trong 30 giây”, hãy thiết kế toàn bộ chuỗi đọc và invalidation đáp ứng giới hạn đó. TTL cục bộ 30 giây **chưa đủ** nếu directory replica chậm thêm 60 giây. Trong các use case cực kỳ nhạy cảm, cần kiểm tra trực tuyến tại nguồn được tin cậy, cơ chế session/token revocation hoặc chính sách **fail closed** khi không thể xác minh quyền.

### Độ tươi mới là yêu cầu của use case

Một trang hồ sơ có thể chấp nhận **displayName** cũ 5 phút. Nhưng API **DeleteDocument** không nên tự động dùng bản group membership 5 phút đó để quyết định quyền xóa. Thiết kế phù hợp là tách **DirectoryProfileReader** và **DirectoryAuthorizationReader** hoặc đặt chính sách freshness rõ ở những port khác nhau.

Đừng trả một DTO gồm email, tên, nhóm và cờ khóa tài khoản từ một cache chung rồi dùng mọi trường cho mọi loại quyết định. Cách này khiến TTL của thuộc tính ít rủi ro vô tình chi phối kết quả bảo mật.

## 4. Cache nằm ở lớp nào?

~~~mermaid
flowchart TB
    API["REST / UI"]
    UC["Application service"]
    PORT["DirectoryPersonReader (port)"]
    CACHE["CachedDirectoryPersonReader (decorator)"]
    LDAP["SpringLdapDirectoryPersonReader (adapter)"]
    TPL["LdapTemplate / LdapClient"]
    CS["ContextSource + TLS"]
    DIR[("LDAP directory")]
    EVICT["Event/invalidation handler"]

    API --> UC --> PORT
    CACHE -. "implements" .-> PORT
    CACHE --> LDAP --> TPL --> CS --> DIR
    EVICT -. "invalidate" .-> CACHE
~~~

**Domain** không biết dữ liệu đến từ cache hay LDAP. **Port** mô tả dữ liệu nghiệp vụ; **LDAP adapter** quản lý DN, schema, filter, **LdapTemplate** và các exception thư mục. **Cache decorator** quản lý key, TTL, giới hạn số entry và invalidation.

Tách cache khỏi LDAP adapter mang lại ba lợi ích:

1. Có thể kiểm thử logic cache bằng một fake port mà không dựng LDAP server.
2. Có thể đổi Caffeine sang Redis hoặc Spring Cache mà không sửa domain.
3. Có thể tắt cache cho một use case nhạy cảm nhưng vẫn tái sử dụng adapter truy vấn LDAP.

Nếu ứng dụng có nhiều nguồn directory, cache phải phân biệt **directory source** và **tenant** tương ứng. Nếu kết quả tìm kiếm phụ thuộc vào quyền đọc của principal đang bind, cache kết quả dùng chung giữa principal có thể làm lộ dữ liệu. Chỉ dùng cache chung khi dữ liệu và quyền đọc của mọi consumer trong phạm vi đó thực sự tương đương.

## 5. Thiết kế cache key: không dùng mỗi tên hiển thị

Cache key quyết định hai request có được dùng cùng một kết quả hay không. Cần bao gồm mọi yếu tố làm thay đổi ý nghĩa của truy vấn:

| Yếu tố | Vì sao quan trọng? |
| --- | --- |
| **Directory source ID** | Cùng login có thể thuộc hai directory độc lập |
| **Tenant hoặc phạm vi tổ chức** | Các tenant có thể dùng cùng login |
| **Loại truy vấn** | Tìm theo **uid** khác tìm theo email hoặc DN |
| **Định danh truy vấn** | Login, entry UUID hoặc group ID theo hợp đồng |
| **Phạm vi/search base** | Query trong **ou=people** khác truy vấn toàn bộ cây |
| **Projection / bộ attribute** | Cache hồ sơ công khai không được trả thay cho kết quả chứa thuộc tính quản trị |
| **Ngữ cảnh quyền đọc nếu có** | Không chia sẻ dữ liệu vốn bị giới hạn theo principal hoặc ACL |

Ví dụ key cho ứng dụng một directory: **(sourceId="corp-ldap", lookupType="uid", login="lan")**. Nếu cần cache theo ID bền vững, dùng **entryUUID** (theo schema OpenLDAP) hoặc **objectGUID** (Active Directory) kèm source ID. **DN có thể đổi khi rename hoặc move OU**, nên không nên mặc định là identity ổn định; nếu cache DN tạm để thao tác entry, cần invalidation khi entry di chuyển.

Với login có phân biệt chữ hoa/chữ thường theo schema, không tự động gọi **toLowerCase()** khi chưa xác định matching rule. Chuẩn hóa key phải nhất quán với cách LDAP tra cứu. Việc chuyển **" Lan "** thành **"lan"** hay gộp các Unicode variant chỉ hợp lệ nếu domain và directory cùng quy định. Một lựa chọn an toàn ban đầu là **giữ chính xác giá trị đầu vào đã qua validation**, chấp nhận một số cache miss bổ sung.

**Không tạo key từ mật khẩu, token, secret hoặc raw filter**. Nếu dữ liệu phục vụ nhiều loại search, dùng key có cấu trúc thay vì ghép chuỗi không có delimiter rõ ràng.

## 6. Xây port đọc directory và adapter Spring LDAP

Ví dụ dùng **Java 17**, **Spring LDAP** và một OpenLDAP giả định có **uid**, **cn**, **mail**, **entryUUID**. Mỗi khai báo **public** thuộc một file Java riêng.

~~~java
// domain/DirectorySubject.java
package com.example.directory.domain;

public record DirectorySubject(String sourceId, String entryId) {}
~~~

~~~java
// domain/DirectoryPerson.java
package com.example.directory.domain;

public record DirectoryPerson(
        DirectorySubject subject,
        String login,
        String displayName,
        String email
) {}
~~~

~~~java
// application/DirectoryPersonReader.java
package com.example.directory.application;

import com.example.directory.domain.DirectoryPerson;
import java.util.Optional;

public interface DirectoryPersonReader {
    Optional<DirectoryPerson> findByLogin(String login);
}
~~~

Lỗi kỹ thuật được chuyển thành lỗi ứng dụng, để cache không cần phân tích exception của Spring LDAP:

~~~java
// application/DirectoryFailure.java
package com.example.directory.application;

public final class DirectoryFailure extends RuntimeException {
    public enum Code { UNAVAILABLE, ACCESS_DENIED, INVALID_DATA, OPERATION_FAILED }

    private final Code code;

    public DirectoryFailure(Code code, Throwable cause) {
        super("Directory operation failed: " + code, cause);
        this.code = code;
    }

    public DirectoryFailure(Code code, String message) {
        super(message);
        this.code = code;
    }

    public Code code() { return code; }
}
~~~

Adapter chịu trách nhiệm giao tiếp directory và ánh xạ sang model:

~~~java
// infrastructure/ldap/SpringLdapDirectoryPersonReader.java
package com.example.directory.infrastructure.ldap;

import com.example.directory.application.DirectoryFailure;
import com.example.directory.application.DirectoryPersonReader;
import com.example.directory.domain.DirectoryPerson;
import com.example.directory.domain.DirectorySubject;
import java.util.List;
import java.util.Optional;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Repository;

@Repository("ldapPersonReader")
public final class SpringLdapDirectoryPersonReader
        implements DirectoryPersonReader {

    private final LdapTemplate ldap;

    public SpringLdapDirectoryPersonReader(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    @Override
    public Optional<DirectoryPerson> findByLogin(String login) {
        if (login == null || login.isBlank()) {
            throw new IllegalArgumentException("Login không được rỗng");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("uid", "cn", "mail", "entryUUID")
                .where("uid").is(login);

        try {
            List<DirectoryPerson> rows = ldap.search(
                    query,
                    (ContextMapper<DirectoryPerson>) context -> {
                        DirContextOperations entry =
                                (DirContextOperations) context;
                        String id = entry.getStringAttribute("entryUUID");
                        String uid = entry.getStringAttribute("uid");
                        if (id == null || id.isBlank()
                                || uid == null || uid.isBlank()) {
                            throw new DirectoryFailure(
                                    DirectoryFailure.Code.INVALID_DATA,
                                    "Entry thiếu định danh bắt buộc");
                        }
                        return new DirectoryPerson(
                                new DirectorySubject("corp-ldap", id),
                                uid,
                                entry.getStringAttribute("cn"),
                                entry.getStringAttribute("mail"));
                    });

            if (rows.size() > 1) {
                throw new DirectoryFailure(
                        DirectoryFailure.Code.INVALID_DATA,
                        "Có nhiều entry trùng login");
            }
            return rows.stream().findFirst();
        } catch (org.springframework.ldap.CommunicationException ex) {
            throw new DirectoryFailure(
                    DirectoryFailure.Code.UNAVAILABLE, ex);
        } catch (org.springframework.ldap.AuthenticationException ex) {
            throw new DirectoryFailure(
                    DirectoryFailure.Code.ACCESS_DENIED, ex);
        } catch (org.springframework.ldap.NamingException ex) {
            throw new DirectoryFailure(
                    DirectoryFailure.Code.OPERATION_FAILED, ex);
        }
    }
}
~~~

Đây là adapter đọc **một nguồn LDAP**. Với nhiều directory, chọn adapter/ContextSource theo source ID đã được xác thực ở application layer. Với Active Directory, mapper **objectGUID** thường đọc kiểu nhị phân; không dùng code đọc **entryUUID** của OpenLDAP cho mọi server.

**LdapQueryBuilder** escape giá trị filter; không nối chuỗi filter từ login. **base("ou=people")** trong ví dụ tương đối với **ContextSource.base = dc=example,dc=org**. Nếu truy vấn không có entry, adapter trả **Optional.empty()**; lỗi mạng, bind thiếu quyền hoặc dữ liệu sai **không được chuyển thành kết quả rỗng**.

## 7. Cache decorator với TTL riêng cho kết quả có và không có tài khoản

Ví dụ dùng **Caffeine 3.x** làm cache in-memory trong ứng dụng Spring. Bổ sung dependency Caffeine và hỗ trợ tạo bean của ứng dụng theo công cụ build đang dùng. Ví dụ không yêu cầu bật annotation **@EnableCaching**, vì chúng ta dùng trực tiếp Caffeine API.

Ta đặt **TTL 3 phút cho hồ sơ tồn tại**, **TTL 10 giây cho kết quả không tìm thấy**, và **maximumSize 10.000 entry**. Caffeine dùng thời gian đơn điệu cho expiry qua **Ticker**, tránh phụ thuộc thay đổi đồng hồ hệ thống.

~~~java
// infrastructure/cache/CachedDirectoryPersonReader.java
package com.example.directory.infrastructure.cache;

import com.example.directory.application.DirectoryPersonReader;
import com.example.directory.domain.DirectoryPerson;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.Expiry;
import com.github.benmanes.caffeine.cache.Ticker;
import java.time.Duration;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

@Component
@Primary
public final class CachedDirectoryPersonReader
        implements DirectoryPersonReader {

    private static final String SOURCE_ID = "corp-ldap";
    private static final long POSITIVE_TTL =
            Duration.ofMinutes(3).toNanos();
    private static final long NEGATIVE_TTL =
            Duration.ofSeconds(10).toNanos();

    private final DirectoryPersonReader delegate;
    private final Cache<LookupKey, LookupValue> cache;

    @Autowired
    public CachedDirectoryPersonReader(
            @Qualifier("ldapPersonReader") DirectoryPersonReader delegate) {
        this(delegate, Ticker.systemTicker());
    }

    // Constructor có thể dùng trong unit test với fake ticker.
    CachedDirectoryPersonReader(
            DirectoryPersonReader delegate, Ticker ticker) {
        this.delegate = delegate;
        this.cache = Caffeine.newBuilder()
                .maximumSize(10_000)
                .recordStats()
                .ticker(ticker)
                .expireAfter(new Expiry<LookupKey, LookupValue>() {
                    @Override
                    public long expireAfterCreate(
                            LookupKey key, LookupValue value,
                            long currentTime) {
                        return value.person().isPresent()
                                ? POSITIVE_TTL : NEGATIVE_TTL;
                    }

                    @Override
                    public long expireAfterUpdate(
                            LookupKey key, LookupValue value,
                            long currentTime, long currentDuration) {
                        return value.person().isPresent()
                                ? POSITIVE_TTL : NEGATIVE_TTL;
                    }

                    @Override
                    public long expireAfterRead(
                            LookupKey key, LookupValue value,
                            long currentTime, long currentDuration) {
                        // Đọc không kéo dài TTL của bản ghi.
                        return currentDuration;
                    }
                })
                .build();
    }

    @Override
    public Optional<DirectoryPerson> findByLogin(String login) {
        if (login == null || login.isBlank()) {
            throw new IllegalArgumentException("Login không được rỗng");
        }

        LookupKey key = new LookupKey(SOURCE_ID, login);
        return cache.get(
                key,
                ignored -> new LookupValue(delegate.findByLogin(login))
        ).person();
    }

    public void invalidate(String login) {
        cache.invalidate(new LookupKey(SOURCE_ID, login));
    }

    private record LookupKey(String sourceId, String login) {}
    private record LookupValue(Optional<DirectoryPerson> person) {}
}
~~~

**Giải thích hành vi:**

1. **Caffeine.get(key, mappingFunction)** thực hiện nạp đồng bộ theo key khi miss, giúp giảm nhiều request cùng lúc đổ vào LDAP cho *một key* (single-flight trong phạm vi một cache instance).
2. **LookupValue(Optional.empty())** là negative cache thật sự; không dựa vào cách một abstraction khác xử lý giá trị **null**.
3. Kết quả thành công được cache theo **expire-after-write**. Nhiều lượt đọc không gia hạn TTL vô hạn.
4. Nếu delegate ném **DirectoryFailure**, hàm nạp không trả **LookupValue**, vì vậy **lỗi kết nối/permission không được cache thành “không có tài khoản”**.
5. Dùng **@Primary** để application inject port mặc định được cache; **@Qualifier("ldapPersonReader")** giúp decorator gọi adapter thật thay vì tự tham chiếu.
6. Constructor nhận **Ticker** cho phép unit test TTL mà không phải gọi **Thread.sleep()**. Trong sản phẩm có thể đưa cấu hình TTL/size ra properties riêng theo loại dữ liệu.

**Giới hạn ví dụ:** đây là cache cục bộ cho một directory source và dữ liệu hồ sơ hiển thị. Lớp này không xử lý phân quyền, không cung cấp freshness mạnh, không tự phát sự kiện invalidation sang các node khác. Không sử dụng cùng cache này để quyết định cho phép một tài khoản đã bị khóa truy cập dữ liệu nhạy cảm.

**Chú ý thiết kế:** nếu có một command vừa ghi LDAP vừa sửa dữ liệu cache, giá trị trong cache vẫn có thể cũ vì request đang nạp hoặc một thay đổi từ bên ngoài. Invalidation làm giảm xác suất đọc dữ liệu cũ nhưng không thay thế cơ chế đảm bảo thứ tự/phiên bản khi cần tính nhất quán chặt.

## 8. TTL nên bắt đầu từ giới hạn dữ liệu cũ được phép

Một TTL tốt không chỉ dựa trên tỷ lệ cache hit. Hãy đặt **ngân sách độ trễ tươi mới** theo use case.

Ví dụ công ty yêu cầu email hiển thị cập nhật trong tối đa 4 phút sau khi HR sửa:

~~~text
Tổng độ trễ tối đa (ước tính) =
  độ trễ từ HR sang directory
  + độ trễ LDAP replication/nguồn đọc
  + tuổi bản cache
  + độ trễ giao diện/những cache tiếp theo
~~~

Giả sử quá trình HR→LDAP có thể mất 60 giây, LDAP replica mất thêm 30 giây và frontend cache 30 giây. Khi đó backend cache **4 phút** sẽ vượt ngân sách 4 phút trong trường hợp xấu nhất. Cần cân bằng các thành phần, thường bằng TTL ngắn hơn và invalidation dựa trên sự kiện đáng tin cậy.

### Expire after write và expire after access

Với directory, **expireAfterWrite** thường là điểm khởi đầu rõ ràng hơn vì một bản hồ sơ phải được làm mới sau thời gian cố định dù bị truy cập liên tục. **ExpireAfterAccess** hữu ích cho thu hồi bộ nhớ của dữ liệu ít truy cập nhưng không nên dùng như **chính sách freshness duy nhất** cho thông tin có thể thay đổi.

**Refresh ahead / refreshAfterWrite** có thể làm tải phân bố đều hơn, song cần hiểu semantics của thư viện: kết quả cũ đôi khi tiếp tục được phục vụ trong lúc refresh bất đồng bộ, còn refresh thất bại có thể khiến bản cũ tiếp tục tồn tại cho đến khi bị loại. Đừng coi **refreshAfterWrite** là một hard TTL cho quyền truy cập. Nếu cần giới hạn cứng, thiết kế thời điểm hết hạn tuyệt đối và hành vi khi refresh không thành công.

### TTL âm (negative TTL) cần ngắn

Nếu directory trả lời “chưa có uid=lan” và ứng dụng cache 10 phút, một người vừa được provisioning sẽ không thấy tài khoản mới dù LDAP đã tạo. Negative TTL nên ngắn hơn positive TTL trong nhiều hệ thống; với luồng đăng ký quan trọng có thể **không cache kết quả vắng mặt**.

Negative caching còn có rủi ro khi LDAP đang dùng search base sai hoặc ACL che kết quả. Chỉ cache **empty từ một truy vấn hoàn tất thành công với cấu hình/semantics được kiểm chứng**, không cache exception hoặc tự suy diễn mọi search rỗng là user bị xóa.

## 9. Invalidation khi LDAP hoặc ứng dụng thay đổi

TTL là **cơ chế dự phòng**. Nếu ứng dụng vừa ghi thành công dữ liệu directory, nên chủ động invalidate key liên quan:

~~~java
// Trong tầng application/infrastructure sau khi LDAP write được xác nhận:
ldapWriter.replaceEmail(subject, "new@example.org");
cachedDirectoryPersonReader.invalidate(oldLogin);
// Nếu login đã đổi: invalidate cả key cũ và key mới.
~~~

Khi cập nhật một tài khoản, nhiều cache key có thể cùng tham chiếu đến nó: **uid**, email, stable ID, danh sách thuộc OU và nhóm có chứa entry đó. Nếu chỉ invalidate **cache tìm theo uid** mà quên **cache tìm theo email**, dữ liệu vẫn có thể cũ ở một đường truy vấn khác.

| Nguồn thay đổi | Phương án invalidation |
| --- | --- |
| Ứng dụng ghi attribute bằng LdapTemplate/ODM | Sau khi xác nhận thao tác thành công, invalidate các key bị ảnh hưởng |
| Đổi DN, đổi login hoặc move OU | Invalidate khóa theo tên cũ và mới, các projection và cache group liên quan |
| Quản trị viên sửa trực tiếp trên LDAP | Dùng change notification/sync feed nếu directory hỗ trợ, hoặc đối soát/TTL |
| HR/IdM sửa LDAP qua hệ thống khác | Nhận sự kiện có nguồn tin cậy, xử lý idempotent và đối soát |
| Directory replica chậm | Xác minh thay đổi trên nguồn đọc phù hợp, không nạp lại từ replica cũ rồi tin đã mới |
| Cập nhật có kết quả không xác định do timeout | Không tự điền cache bằng dữ liệu lệnh mong muốn; đọc lại/xác minh rồi invalidate |

**Sự kiện invalidation có thể đến muộn, trùng hoặc sai thứ tự.** Nếu có thể, dùng event ID và version/sequence do hệ thống nguồn thực sự bảo đảm để deduplicate và xác định phiên bản mới. Không mặc định mọi LDAP server có change log hoặc sequence toàn cục.

Trong ứng dụng nhiều instance, gọi **invalidate()** trên một node chỉ xóa cache của node đó. Cần cơ chế broadcast (message bus/pub-sub), một cache dùng chung với quy định nhất quán phù hợp, hoặc TTL đủ ngắn để thỏa yêu cầu. Nếu event mất, TTL và job đối soát là tuyến phòng vệ bổ sung.

## 10. Tránh dữ liệu cũ ghi đè bản mới sau invalidation

Xét một tình huống race:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant Cache as Cache
    participant LDAP as LDAP
    participant B as Directory update / event
    A->>Cache: miss(uid=lan)
    Cache->>LDAP: search(uid=lan)
    Note over LDAP: Trả dữ liệu cũ
    B->>LDAP: cập nhật mail
    B->>Cache: invalidate(uid=lan)
    LDAP-->>Cache: dữ liệu cũ đến trễ
    Note over Cache: Loader có thể làm xuất hiện lại bản cũ
    A-->>Cache: đọc kết quả
~~~

Với cache đơn giản, **invalidate một key chưa tự tạo cam kết mạnh rằng mọi request đang chạy sẽ không nạp lại phiên bản cũ**. Hành vi cụ thể phụ thuộc việc nạp cache có đồng bộ hay không, thiết kế event và thứ tự thao tác. Cần xác định yêu cầu của hệ thống trước khi chọn cơ chế:

- Nếu chỉ dùng cho hiển thị, có thể chấp nhận stale tối đa theo TTL và dựa thêm vào invalidation.
- Nếu cần **read-your-writes** trong cùng một use case, có thể trả model vừa được server xác nhận từ thao tác ghi, hoặc buộc đọc từ nguồn nhất quán phù hợp thay vì lấy qua cache dùng chung.
- Nếu bắt buộc loại bỏ version cũ sau một sự kiện, dùng **version/epoch theo subject** và từ chối lưu kết quả nạp mang epoch cũ; điều này cần triển khai đồng bộ và thử race thực tế.
- Nếu cần **thu hồi quyền ngay**, không đặt tính đúng đắn của authorization phụ thuộc vào cache hồ sơ không có freshness guarantee.

Khác biệt giữa **đã invalidate** và **đã quan sát được bản mới** cần được thể hiện rõ trong API nội bộ, giám sát và kiểm thử.

## 11. Tình huống LDAP không khả dụng: có được dùng cache cũ?

Một outage có thể xảy ra do lỗi mạng, timeout, service account không bind được hoặc certificate TLS hết hạn. Hệ thống phải định nghĩa chính sách riêng cho từng use case.

| Use case | Có thể dùng dữ liệu cũ? | Lý do |
| --- | --- | --- |
| Hiển thị tên trong trang lịch sử | Có thể, kèm nhãn thời điểm dữ liệu được lấy nếu cần | Sai lệch hiển thị thường ít nghiêm trọng |
| Gửi email công việc | Tùy chính sách; cân nhắc kiểm tra lại | Email cũ có thể gửi sai người |
| Đăng ký thành viên mới theo danh tính LDAP | Thường phải xác minh danh tính hiện hành | Cache có thể giữ account đã xóa hoặc đổi |
| Kiểm tra nhóm để cấp quyền nhạy cảm | **Không fallback tùy tiện** | Có nguy cơ duy trì quyền bị thu hồi |
| Xác thực mật khẩu | **Không dùng cache hồ sơ để xác thực** | Bind/IdP cần cơ chế xác thực riêng |

**Stale-if-error** có thể là một tính năng có ích cho dữ liệu phi bảo mật, nhưng phải được thiết kế tường minh: lưu timestamp **fetchedAt**, quy định **maxStale**, loại lỗi nào cho phép fallback, và phản hồi cho consumer rằng dữ liệu đang cũ. Cache với hard TTL trong ví dụ Caffeine phía trên **không có stale-if-error**; khi quá hạn, việc load lỗi được truyền ra ngoài.

Đừng bắt **CommunicationException** rồi trả **Optional.empty()** hoặc trả mặc định “không thuộc nhóm nào” cho mọi trường hợp. **Không tìm thấy**, **không thể xác minh** và **không có quyền** là các trạng thái khác nhau. Với quyết định bảo mật, chính sách thường phải từ chối nếu không thể xác minh, đồng thời trả lỗi dịch vụ phù hợp thay vì báo sai rằng account đã biến mất.

## 12. Cấu hình LDAP an toàn và hiệu năng

Ví dụ Spring Boot cấu hình connection với **LDAPS**:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Các nguyên tắc hạ tầng ảnh hưởng trực tiếp tới cache:

1. **LDAPS hoặc StartTLS** phải được cấu hình đúng và xác minh certificate/hostname; không tắt TLS verification chỉ để giảm timeout.
2. **ContextSource** dùng principal có quyền tối thiểu. Nếu ACL tạo ra tập kết quả khác nhau theo tài khoản bind, không chia sẻ cache ngoài phạm vi quyền tương đương.
3. Đặt **connect/read timeout**, giới hạn search base/filter, kích thước kết quả và cách xử lý referral. Một cache miss không được biến thành request LDAP không giới hạn thời gian.
4. **Pooling** giảm chi phí connection nhưng phải tương thích TLS/StartTLS và trạng thái bind. Không chia sẻ bừa bãi connection đã xác thực bằng principal khác.
5. Khi chọn **LdapTemplate** hay **LdapClient/ODM**, giữ mapper dữ liệu trong adapter; cache chứa DTO ứng dụng tối thiểu thay vì **DirContextOperations**, **Attributes**, context kết nối hoặc đối tượng có vòng đời truy cập LDAP.
6. **Không cache** mật khẩu, password hash, userPassword, token, bind credential hoặc exception thô. Cân nhắc hạn chế **PII** trong memory dump, Redis, log và backup.

Nếu dùng cache phân tán như Redis, cần cân nhắc **TLS**, authentication, namespace tenant, ACL, mã hóa dữ liệu nhạy cảm khi cần, giới hạn TTL, eviction policy và dung lượng lưu trữ. Cache phân tán tạo một phụ thuộc vận hành mới; không vì vậy mà bỏ qua giới hạn freshness của LDAP.

## 13. Giới hạn dung lượng, chống stampede và đo hiệu quả

TTL không tự giới hạn bộ nhớ. Một endpoint cho phép tìm vô số login ngẫu nhiên có thể tạo rất nhiều negative entry. Cần **maximumSize**, hạn chế query đầu vào, rate limiting và TTL âm ngắn.

**Cache stampede:** sau một đợt hết hạn hàng loạt, nhiều request cùng miss và cùng truy vấn LDAP. Ví dụ Caffeine dùng **Cache.get(key, loader)** để giảm tải cho một key trong cùng process. Với nhiều node, mỗi node vẫn có thể gọi LDAP một lần cho cùng key; khi số node lớn, cân nhắc jitter TTL, prewarming có kiểm soát hoặc cơ chế distributed coordination phù hợp.

**Không prewarm toàn bộ directory** nếu không có nhu cầu thật, vì có thể gây tải lớn, lưu dữ liệu nhạy cảm không cần thiết và giữ các entry hiếm dùng trong bộ nhớ. Với danh sách LDAP lớn, còn phải lưu ý pagination, server size limit, dữ liệu thay đổi giữa các trang; cache một trang kết quả không mặc định tạo snapshot nhất quán.

Theo dõi tối thiểu:

| Chỉ số | Dùng để chẩn đoán |
| --- | --- |
| **Hit/miss ratio** theo loại key | Cache có thực sự giảm số lần truy vấn không |
| **LDAP request rate / p95–p99 latency** | Tải và độ trễ tại miss, phát hiện stampede |
| **Cache size / eviction count** | Dung lượng và mức churn |
| **Negative cache hit rate** | Có nhiều lookup không tồn tại hoặc truy vấn bất thường không |
| **Age of data / staleness incidents** | Có vi phạm freshness SLA không |
| **Invalidation lag / event backlog** | Sự kiện từ IdM/HR tới các node có chậm không |
| **Directory error rate** | Phân biệt outage với dữ liệu không tồn tại |
| **Authorization decision freshness** | Kiểm soát riêng với các quyết định quyền, nếu có cache chuyên biệt |

Không ghi login, email hoặc DN đầy đủ như **metric label** vì cardinality rất cao và có thể làm lộ dữ liệu cá nhân. Dùng directory source, loại thao tác, mã lỗi và nhóm mức tuổi dữ liệu; log chi tiết chỉ khi thật cần và phải kiểm soát truy cập.

## 14. Kiểm thử TTL và invalidation

### 14.1. Unit test với fake port và fake ticker

Ví dụ constructor package-private nhận **Ticker** ở phần 7 cho phép kiểm thử thời gian mà không chờ thực:

~~~java
// Trong package infrastructure.cache; mã minh họa cho @Test của JUnit 5.
java.util.concurrent.atomic.AtomicInteger reads =
        new java.util.concurrent.atomic.AtomicInteger();
java.util.concurrent.atomic.AtomicLong nanos =
        new java.util.concurrent.atomic.AtomicLong();

com.github.benmanes.caffeine.cache.Ticker ticker = nanos::get;
DirectoryPersonReader fake = login -> {
    reads.incrementAndGet();
    return java.util.Optional.of(new DirectoryPerson(
            new DirectorySubject("corp-ldap", "stable-123"),
            login, "Nguyễn Lan", "lan@example.org"));
};

CachedDirectoryPersonReader cached =
        new CachedDirectoryPersonReader(fake, ticker);

cached.findByLogin("lan");
cached.findByLogin("lan");
org.junit.jupiter.api.Assertions.assertEquals(1, reads.get());

nanos.addAndGet(java.time.Duration.ofMinutes(4).toNanos());
cached.findByLogin("lan");
org.junit.jupiter.api.Assertions.assertEquals(2, reads.get());
~~~

Các test khác cần kiểm tra **Optional.empty()** hết hạn sau 10 giây; **DirectoryFailure** không bị cache; gọi **invalidate("lan")** khiến request kế tiếp đọc lại LDAP; hai login khác nhau tạo hai key; truy cập nhiều lần **không gia hạn TTL**.

### 14.2. Integration test với directory thật hoặc test container

| Kịch bản | Kỳ vọng |
| --- | --- |
| LDAP có một entry | Cache dữ liệu, lần đọc tiếp theo không truy vấn LDAP trong TTL |
| Không có entry | Negative cache tồn tại ngắn, rồi được refresh |
| Tạo account sau một negative hit | Entry mới được thấy khi invalidate hoặc negative TTL hết |
| Sửa **cn/mail** ngoài ứng dụng | Giao diện cập nhật khi có invalidation/TTL phù hợp |
| Đổi **uid** hoặc chuyển OU | Các key liên quan được invalidate; không tái dùng DN cũ |
| Group bị thu hồi | Authorization tuân theo freshness contract riêng, không chấp nhận cache hồ sơ cũ |
| LDAP server dừng đột ngột | Miss trả lỗi hạ tầng; không biến thành empty |
| LDAP thiếu quyền hoặc TLS lỗi | Lỗi phân loại rõ và không bị cache như kết quả |
| Nhiều request cùng miss một key | Không tạo số lượng search tương đương số request trong một node |
| Hai node cùng cache rồi có sự kiện đổi tài khoản | Cả hai node nhận invalidation hoặc hết TTL theo SLA |

### 14.3. Kiểm thử race condition và failure

Thực hiện các tình huống có thứ tự kiểm soát: request A bắt đầu load trước, B sửa LDAP và invalidate, A hoàn tất muộn; một sự kiện bị gửi hai lần; một node lỡ sự kiện; replica còn trả dữ liệu cũ; cache backend unavailable; và LDAP đồng thời cũng unavailable. Kiểm tra chính sách fallback theo từng use case, không chỉ kiểm tra cache hit.

Nếu dùng Spring Cache annotation **@Cacheable**, cần lưu ý proxy của Spring (self-invocation có thể không đi qua cache), key expression, null/Optional handling của provider, TTL của cache manager và cách **@CacheEvict** hoạt động giữa các node. Việc thêm annotation không tự mang lại freshness, negative cache TTL khác nhau hoặc distributed invalidation.

## 15. Những lỗi thường gặp

| Lỗi thiết kế | Hệ quả | Cách sửa |
| --- | --- | --- |
| Cache mọi thuộc tính LDAP bằng một TTL 10 phút | Group/quyền và hồ sơ cùng stale | Phân loại theo mục đích sử dụng và freshness SLA |
| Dùng **expireAfterAccess** cho dữ liệu phân quyền | Request thường xuyên giữ quyền cũ mãi | Giới hạn tuổi tuyệt đối và chính sách thu hồi quyền riêng |
| Cache kết quả bind/mật khẩu | Sai mô hình bảo mật, có thể che thay đổi credential | Xác thực trực tiếp qua cơ chế chuyên trách |
| Cache empty quá lâu | User mới tạo bị coi là không tồn tại | Negative TTL ngắn, invalidate khi provisioning |
| Bắt exception LDAP rồi cache **Optional.empty()** | Outage bị coi là user đã xóa | Lỗi hạ tầng không đi vào cache kết quả |
| Chỉ dùng **login** làm key trong multi-tenant | Rò rỉ dữ liệu giữa nguồn/tenant | Key gồm source, tenant và ngữ cảnh truy vấn |
| Chỉ xóa cache ở một instance | Node khác tiếp tục trả dữ liệu cũ | Broadcast invalidation/cache chung cùng TTL phòng vệ |
| Invalidate chỉ cache theo UID khi email đổi | Các đường truy vấn khác còn stale | Xác định mọi index/key bị ảnh hưởng |
| Tưởng cache hit ratio cao là đủ | Có thể tăng sự cố quyền truy cập | Đo freshness và lỗi stale theo use case |
| Dùng cache hồ sơ làm nguồn cấp quyền | Quyền bị thu hồi muộn | Cổng authorization và freshness contract riêng |
| Không giới hạn negative entry hoặc query rate | Tốn RAM và tăng tải directory | Maximum size, input validation, rate limit |

## 16. Bài tập thực hành

Một công ty dùng OpenLDAP quản lý nhân viên và nhóm. Ứng dụng Spring Boot cho phép xem hồ sơ, mời nhân viên vào workspace và truy cập tài liệu mật. Tên hiển thị được phép chậm 5 phút; sau khi bị xóa khỏi nhóm **confidential-readers**, nhân viên phải bị từ chối truy cập trong tối đa 30 giây. Ứng dụng có ba instance, đọc từ hai LDAP replica với độ trễ replication không cố định.

Hãy thiết kế:

1. **Hai port hoặc hai chính sách đọc**: hồ sơ hiển thị và quyền truy cập. Chọn dữ liệu nào được cache, TTL và hành vi khi LDAP mất kết nối.
2. **Cache key** bao gồm directory source, tenant, loại truy vấn và ID; giải thích vì sao login, DN và stable ID có vòng đời khác nhau.
3. **Negative cache** cho lookup user: TTL bao nhiêu để không làm chậm provisioning? Khi có sự kiện create/delete sẽ invalidate key nào?
4. **Invalidation cho ba instance**: cách nhận event, xử lý event trùng/bị mất, fallback TTL và giám sát độ trễ.
5. **Trường hợp replica trễ hơn 30 giây**: thay đổi nguồn kiểm tra quyền hoặc cơ chế thu hồi quyền thế nào để vẫn đáp ứng SLA?
6. **Unit/integration test** dùng fake ticker, LDAP test server, mô phỏng outage, cache stampede, stale dữ liệu và race giữa load với invalidate.

Tự đánh giá thiết kế qua bốn câu hỏi: **Bản cache cũ tối đa bao lâu? Ai được phép dùng dữ liệu cũ? Khi dữ liệu thay đổi, những key nào bị vô hiệu? Khi directory không xác minh được, hệ thống phản hồi thế nào?**

**Kết luận:** cache LDAP là một phần của hợp đồng dữ liệu trong ứng dụng, không chỉ là tối ưu hiệu năng. Thiết kế tốt tách cache khỏi adapter Spring LDAP, dùng key đủ ngữ cảnh, TTL dương và âm phù hợp, invalidation có kiểm soát và cơ chế đối phó race/outage. Dữ liệu hồ sơ có thể chấp nhận stale theo SLA hiển thị; thông tin xác thực và phân quyền cần chính sách tươi mới chặt chẽ hơn, nhất là khi quyền bị thu hồi.
