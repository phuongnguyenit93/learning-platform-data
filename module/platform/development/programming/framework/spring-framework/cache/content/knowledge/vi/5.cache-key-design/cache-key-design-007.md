# Khóa cache theo người dùng, tổ chức hoặc phạm vi dữ liệu trong Spring Cache

## Mục tiêu học tập

Sau bài này, bạn có thể thiết kế một khóa cache phản ánh đúng **người dùng**, **tổ chức (tenant)** và **phạm vi dữ liệu được phép xem**; phân biệt dữ liệu có thể dùng chung với dữ liệu cá nhân hóa; tránh trả nhầm dữ liệu qua ranh giới phân quyền; và bảo đảm thao tác `@Cacheable`, `@CachePut`, `@CacheEvict` dùng cùng định danh cache khi cần. Bài tập trung vào **thiết kế khóa** trong Spring Cache. Ví dụ sử dụng Java 17, Spring Boot 3.3 và cache bộ nhớ để quan sát hành vi một cách trực tiếp.

Một nguyên tắc cần nhớ từ đầu: **cache chỉ là cơ chế tối ưu hiệu năng, không phải ranh giới cấp quyền**. Cần xác thực và kiểm tra quyền trước khi trả kết quả, kể cả khi kết quả đã có sẵn trong cache. Khóa đúng giúp ngăn kết quả của hai phạm vi bị trộn lẫn, nhưng tự nó không chứng minh người gọi được phép truy cập.

## 1. Xác định danh tính của một mục cache

Trong Spring Cache, một mục được định danh về mặt logic bằng cặp:

~~~text
(cacheName, key) -> cachedValue
~~~

`cacheName` chỉ vùng lưu trữ, còn `key` do biểu thức `key` hoặc `KeyGenerator` tạo ra từ lời gọi. Ví dụ một phương thức `readDocument(organizationId, userId, documentId)` trả nội dung được lọc theo người xem.

~~~text
viewerDocuments
├── (acme, alice, D1) -> bản hiển thị của Alice tại Acme
├── (acme, bob,   D1) -> bản hiển thị của Bob tại Acme
└── (beta, alice, D1) -> bản hiển thị của Alice tại Beta
~~~

Ba mục có cùng `documentId = D1`, nhưng khác tổ chức hoặc người dùng. Nếu bạn chỉ dùng `"D1"` làm khóa trong cùng cache `"viewerDocuments"`, người đến sau có thể nhận kết quả của người trước.

Điểm mấu chốt là xác định một hàm ánh xạ:

~~~text
key = f(định danh dữ liệu, ngữ cảnh ảnh hưởng tới kết quả)
~~~

Hai lời gọi chỉ được dùng **chung một khóa** khi kết quả cache có thể thay thế cho nhau theo đúng hợp đồng nghiệp vụ. Nếu kết quả có thể khác nhau theo tenant, người dùng, quyền truy cập, locale, các bộ lọc hoặc phiên bản chính sách, phải tính đến các yếu tố đó.

### Ba phạm vi thường gặp

| Kiểu dữ liệu | Ví dụ | Những thành phần khóa thường cần |
| --- | --- | --- |
| **Công khai, giống nhau cho mọi người** | Tỷ giá công khai tại cùng thời điểm, danh sách loại sản phẩm công khai | Định danh tài nguyên, locale/đơn vị/phiên bản nếu có ảnh hưởng |
| **Chung trong một tổ chức** | Cấu hình hiển thị chung của tổ chức, báo cáo không phụ thuộc từng thành viên | `organizationId` + định danh tài nguyên + các tham số ảnh hưởng |
| **Theo người dùng hoặc quyền cụ thể** | Trang chủ cá nhân, danh sách tài liệu được lọc, bản xuất có ẩn cột | `organizationId` + `userId` hoặc dấu vết quyền phù hợp + định danh tài nguyên/bộ lọc |

`userId` không luôn cần thiết: thêm user vào cache dùng chung làm giảm tỷ lệ hit mà không tăng độ đúng. Ngược lại, nếu kết quả thật sự khác theo user mà khóa chỉ có `organizationId`, bạn có nguy cơ chia sẻ nhầm kết quả. **Phạm vi của key phải khớp phạm vi của chính dữ liệu trả về.**

## 2. Thiết kế khóa cho hệ thống nhiều tenant

Giả sử cả Acme và Beta đều có tài liệu mã `"D1"`.

~~~java
// Sai khi cache name dùng chung và D1 có thể xuất hiện ở nhiều tenant.
// Đây là đoạn minh họa, không phải chương trình chạy độc lập.
@Cacheable(cacheNames = "documents", key = "#p1")
public Document read(String organizationId, String documentId) {
    return repository.find(organizationId, documentId);
}
~~~

Với lời gọi `read("acme", "D1")` rồi `read("beta", "D1")`, biểu thức `#p1` đều trả `"D1"`. Nếu lời gọi đầu được cache, lời gọi tiếp theo có thể lấy sai dữ liệu mà không chạy `repository.find(...)`.

Cách đơn giản là đưa cả hai tham số vào khóa:

~~~java
// Minh họa: tên cache cố định, khóa ghép hai đối số.
@Cacheable(cacheNames = "documents")
public Document read(String organizationId, String documentId) {
    return repository.find(organizationId, documentId);
}
~~~

Khi không khai báo `key`, `SimpleKeyGenerator` mặc định của Spring lấy **toàn bộ các đối số**: với nhiều đối số, Spring sử dụng `SimpleKey`. Trong ví dụ này, `(acme, D1)` và `(beta, D1)` khác nhau. Tuy nhiên nếu phương thức còn nhận thêm dữ liệu không ảnh hưởng kết quả như traceId, các traceId khác nhau sẽ tạo khóa khác không cần thiết; khi đó nên khai báo rõ thành phần định danh.

Một cách khác là tách **cache name theo tenant**, ví dụ `"documents.acme"` và `"documents.beta"`, rồi chỉ dùng `"D1"` trong từng vùng. Trường hợp này thường cần `CacheResolver` và chính sách đặt tên/giới hạn vùng. Đối với số tenant lớn, một vùng ổn định cùng khóa ghép tenant thường dễ quản trị hơn tạo hàng nghìn vùng. Dù chọn cách nào, **đọc, ghi và xóa** phải cùng nhắm đúng `(cacheName, key)`.

### Cẩn thận với chuỗi nối đơn giản

~~~java
// Ngắn gọn nhưng chỉ an toàn nếu định danh không thể gây nhập nhằng.
@Cacheable(cacheNames = "documents", key = "#p0 + ':' + #p1")
~~~

Nếu `organizationId="a:b", documentId="c"` và `organizationId="a", documentId="b:c"`, cả hai đều tạo chuỗi `"a:b:c"`. Dùng cách mã hóa có độ dài thành phần, escaping đúng quy tắc, hoặc tốt hơn là **kiểu khóa cấu trúc bất biến** như Java `record` khi backend hỗ trợ. Không dùng một số nguyên `hashCode()` trần làm danh tính vì có thể xảy ra va chạm hash.

## 3. Khóa theo người dùng khi kết quả có cá nhân hóa

Xét phương thức `getDashboard(orgId, userId, period)`. Hai thành viên của cùng tổ chức có thể thấy chỉ số khác nhau. Khóa chỉ có `(orgId, period)` là không đủ, vì `userId` ảnh hưởng trực tiếp đến giá trị.

~~~text
getDashboard("acme", "alice", "2026-11")
    -> (acme, alice, 2026-11)

getDashboard("acme", "bob", "2026-11")
    -> (acme, bob, 2026-11)
~~~

Đưa `userId` vào khóa là hợp lý khi:

- Kết quả chứa thuộc tính cá nhân, cài đặt riêng hoặc quyền xem khác nhau giữa các user.
- Hệ thống không có một nhóm quyền chia sẻ được chứng minh là tạo **cùng một kết quả**.
- Cần loại bỏ cache riêng của một user khi thay đổi dữ liệu cá nhân hóa của user đó.

**Không lấy trực tiếp user ID do client tự gửi để coi như đã được xác thực.** Backend phải lấy định danh từ principal/session/token đã xác minh và kiểm tra người đó có quyền truy cập tổ chức, tài nguyên, hành động yêu cầu. Một tham số như `requestedUserId` trong HTTP path không phải bằng chứng về danh tính người gọi.

### Một người có thể thuộc nhiều tổ chức

Nếu user `"alice"` đồng thời thuộc Acme và Beta, khóa `(alice, D1)` vẫn có nguy cơ trùng giữa hai tổ chức. Thường cần `(orgId, userId, documentId)`. Ngay cả khi `userId` có tính duy nhất toàn hệ thống, ngữ cảnh làm việc hiện tại (`activeOrganizationId`) vẫn có thể quyết định dữ liệu và phải được phản ánh nếu kết quả phụ thuộc tổ chức đó.

Cũng cần xác định trường hợp **quản trị viên xem thay người khác**: khóa theo người **yêu cầu**, người **sở hữu dữ liệu**, hay cả hai? Câu trả lời phụ thuộc việc nội dung được lọc theo ai. Hãy đặt tên rõ `viewerId`, `ownerId`, `subjectId` thay vì một biến mơ hồ `userId`.

## 4. Phạm vi dữ liệu còn bao gồm quyền, bộ lọc và ngữ cảnh hiển thị

Tenant và user thường chưa đủ. Hai lần gọi của cùng user có thể trả kết quả khác nếu một trong các yếu tố sau thay đổi:

| Yếu tố | Khi nào tham gia cache identity? | Ví dụ |
| --- | --- | --- |
| Quyền hoặc chính sách | Kết quả thay đổi theo quyền đã cấp hoặc cách ẩn trường | Chế độ `FULL` so với `REDACTED`; `policyVersion` |
| Vai trò/nhóm | Vai trò thực sự quyết định chính xác phần dữ liệu trả về | Người duyệt thấy thêm trường, người đọc không thấy |
| Bộ lọc và phân trang | Thay đổi danh sách hoặc thứ tự trả về | `status`, `sort`, `page`, `size` |
| Locale và timezone | Chúng làm thay đổi nội dung đã render | Bản tiếng Việt/tiếng Anh; ngày theo múi giờ |
| Feature flag/version | Phiên bản xử lý hoặc giao diện trả kết quả khác | `projectionVersion=2` |
| Tổ chức/địa bàn/chi nhánh | Phạm vi dữ liệu thay đổi theo ngữ cảnh | `organizationId`, `branchId` |

Một ví dụ báo cáo có thể dùng cache identity:

~~~text
(
  namespace = "report:v2",
  organizationId = "acme",
  viewerId = "alice",
  permissionVersion = 7,
  reportId = "R1",
  statusFilter = "OPEN",
  page = 0,
  size = 20,
  locale = "vi-VN"
)
~~~

Đây là **ví dụ phân tích**, không có nghĩa mọi hàm đều cần tất cả các trường. Chỉ đưa vào những trường quyết định giá trị kết quả. Các tham số không ảnh hưởng kết quả như `traceId`, `requestId`, logger hoặc timestamp của mỗi HTTP request thường nên bỏ khỏi khóa.

### Có nên dùng role thay cho userId?

Chỉ khi bạn chứng minh mọi user cùng role thấy cùng tập dữ liệu và cùng mức ẩn/hiện. Trong nhiều hệ thống, hai người cùng role `"MANAGER"` vẫn khác chi nhánh, danh sách dự án, ngoại lệ cấp quyền hoặc danh sách tài liệu được chia sẻ. Khóa `(orgId, role, documentId)` lúc đó không đủ. Với dữ liệu nhạy cảm hoặc quyền phức tạp, per-user key thường dễ suy luận hơn; nhưng **vẫn phải kiểm tra quyền trên từng yêu cầu**.

Một `permissionFingerprint` hoặc `policyVersion` chỉ hợp lý nếu được tính từ trạng thái quyền tin cậy, cập nhật khi chính sách đổi, có ngữ nghĩa ổn định và quản lý được việc hết hạn. Không lấy role hoặc permission string do client tự khai báo.

## 5. Cache hit có thể bỏ qua kiểm tra quyền đặt bên trong phương thức

Đây là lỗi thiết kế nguy hiểm:

~~~java
// PHẢN VÍ DỤ: không dùng trong hệ thống có dữ liệu phân quyền.
// Hàm checkPermission nằm trong thân phương thức sẽ không chạy khi cache hit.
@Cacheable(cacheNames = "documents", key = "#p0")
public Document read(String documentId) {
    checkCurrentUserCanRead(documentId);
    return loadDocument(documentId);
}
~~~

Khi cache hit, `@Cacheable` thông thường trả giá trị được lưu mà **không thực thi thân phương thức**. Nếu việc kiểm tra quyền chỉ nằm trong thân đó, kiểm tra có thể bị bỏ qua. Việc mở rộng key thành `(userId, documentId)` giúp cô lập kết quả, nhưng **không tự xử lý thu hồi quyền**: một user từng được phép xem có thể vẫn hit dữ liệu cũ sau khi quyền đã bị rút nếu không có một bước kiểm tra quyền chạy mỗi lần.

### Thiết kế luồng an toàn hơn

Tách một lớp **kiểm tra truy cập mỗi lời gọi** và một bean **cache dữ liệu đã được phép dùng**:

~~~text
HTTP / job / caller
       |
       v
Xác thực danh tính và ngữ cảnh tổ chức (trusted principal)
       |
       v
DocumentFacade
 - xác minh thuộc tổ chức
 - kiểm tra quyền xem tài liệu cho yêu cầu này
 - chọn viewer/organization/scope hợp lệ
       |
       v
ScopedDocumentCache (@Cacheable)
 - tạo khóa từ scope đã kiểm tra
 - hit: trả nội dung tương ứng
 - miss: lấy và tạo kết quả
~~~

Chỉ để các entrypoint được phép gọi qua facade; không phơi trực tiếp cached service thành API cho request chưa được kiểm tra quyền. Cần đặc biệt kiểm thử thứ tự advice nếu phối hợp `@PreAuthorize` với caching trên **cùng method**; đừng dựa vào giả định ngầm rằng interceptor kiểm tra quyền luôn chạy trước cache interceptor. Một lớp facade độc lập giúp ranh giới rõ ràng hơn.

**Đồng thời, lớp dữ liệu vẫn phải thực thi giới hạn tenant/quyền khi truy vấn nguồn.** Cache key ngăn trộn dữ liệu của những lời gọi, nhưng không ngăn một truy vấn SQL thiếu `tenant_id` lấy sai hàng từ database.

## 6. Ví dụ Java 17 chạy được: cô lập tổ chức và người xem

Ví dụ sử dụng Spring Boot 3.3.5, Java 17 và `ConcurrentMapCacheManager` (cache trong một JVM). Hai người của cùng tổ chức thấy kết quả riêng; một người có cùng ID ở tổ chức khác cũng có khóa khác. Facade kiểm tra ranh giới tổ chức **trước mỗi lời gọi**, kể cả khi dữ liệu đã được cache. Trong sản phẩm thực, facade còn phải kiểm tra ACL/quyền trên **từng tài liệu**; demo chỉ mô phỏng kiểm tra thành viên tổ chức để tập trung vào khóa.

Cấu trúc dự án:

~~~text
scoped-cache-demo/
├── pom.xml
└── src/main/java/example/scopedcache/
    ├── DemoApplication.java
    ├── DocumentFacade.java
    └── ScopedDocumentCache.java
~~~

### `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>scoped-cache-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### `src/main/java/example/scopedcache/DemoApplication.java`

~~~java
package example.scopedcache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("viewerDocuments");
    }

    // Tên method không nằm trong khóa: read và evict cùng định danh.
    @Bean("viewerDocumentKey")
    KeyGenerator viewerDocumentKey() {
        return (target, method, params) -> {
            if (params.length != 3
                    || !(params[0] instanceof String org)
                    || !(params[1] instanceof String viewer)
                    || !(params[2] instanceof String document)) {
                throw new IllegalArgumentException(
                        "Expected orgId, viewerId and documentId");
            }
            return new ScopeKey("v1", org, viewer, document);
        };
    }

    // Record là khóa cấu trúc bất biến; equals/hashCode do Java sinh.
    private record ScopeKey(String version, String orgId,
                            String viewerId, String documentId) {}

    @Bean
    CommandLineRunner demo(DocumentFacade facade) {
        return args -> {
            var aliceAcme = new DocumentFacade.Caller("alice", "acme");
            var bobAcme = new DocumentFacade.Caller("bob", "acme");
            var aliceBeta = new DocumentFacade.Caller("alice", "beta");

            System.out.println(facade.read(aliceAcme, "acme", "D1"));
            System.out.println(facade.read(aliceAcme, "acme", "D1"));
            System.out.println(facade.read(bobAcme, "acme", "D1"));
            System.out.println(facade.read(aliceBeta, "beta", "D1"));

            facade.invalidate(aliceAcme, "acme", "D1");
            System.out.println(facade.read(aliceAcme, "acme", "D1"));

            try {
                facade.read(aliceAcme, "beta", "D1");
            } catch (SecurityException expected) {
                System.out.println("DENIED: " + expected.getMessage());
            }
        };
    }
}
~~~

### `src/main/java/example/scopedcache/DocumentFacade.java`

~~~java
package example.scopedcache;

import org.springframework.stereotype.Service;

@Service
public class DocumentFacade {
    private final ScopedDocumentCache cache;

    public DocumentFacade(ScopedDocumentCache cache) {
        this.cache = cache;
    }

    // Demo: trong ứng dụng thật, Caller phải đến từ identity đã xác thực.
    public record Caller(String userId, String orgId) {}

    public String read(Caller caller, String requestedOrg,
                       String documentId) {
        authorize(caller, requestedOrg);
        // Ở production còn kiểm tra ACL của documentId ở mỗi request.
        return cache.read(requestedOrg, caller.userId(), documentId);
    }

    public void invalidate(Caller caller, String requestedOrg,
                           String documentId) {
        authorize(caller, requestedOrg);
        cache.evict(requestedOrg, caller.userId(), documentId);
    }

    private void authorize(Caller caller, String requestedOrg) {
        if (caller == null || !caller.orgId().equals(requestedOrg)) {
            throw new SecurityException("organization mismatch");
        }
    }
}
~~~

### `src/main/java/example/scopedcache/ScopedDocumentCache.java`

~~~java
package example.scopedcache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ScopedDocumentCache {
    private final AtomicInteger loads = new AtomicInteger();

    @Cacheable(cacheNames = "viewerDocuments",
               keyGenerator = "viewerDocumentKey")
    public String read(String orgId, String viewerId, String documentId) {
        int number = loads.incrementAndGet();
        return orgId + "/" + viewerId + "/" + documentId
                + " -> load#" + number;
    }

    @CacheEvict(cacheNames = "viewerDocuments",
                keyGenerator = "viewerDocumentKey")
    public void evict(String orgId, String viewerId, String documentId) {
        // Demo chỉ xóa cache; dữ liệu nguồn không thay đổi.
    }
}
~~~

Chạy tại thư mục `scoped-cache-demo` bằng JDK 17+ và Maven:

~~~bash
mvn -q spring-boot:run
~~~

Ngoài log khởi động Spring, `CommandLineRunner` in chính xác các dòng:

~~~text
acme/alice/D1 -> load#1
acme/alice/D1 -> load#1
acme/bob/D1 -> load#2
beta/alice/D1 -> load#3
acme/alice/D1 -> load#4
DENIED: organization mismatch
~~~

Giải thích:

1. Lần đầu của Alice/Acme là cache miss, chạy `ScopedDocumentCache.read` và lưu key `(v1, acme, alice, D1)`.
2. Lần thứ hai của Alice/Acme hit nên bộ đếm không tăng, vẫn trả `load#1`. **`DocumentFacade.authorize` vẫn được gọi lại trước cache hit**.
3. Bob/Acme tạo key `(v1, acme, bob, D1)` và nhận `load#2`.
4. Alice/Beta có cùng `viewerId` và `documentId` nhưng khác `orgId`; tạo key riêng, nhận `load#3`.
5. Xóa Alice/Acme bằng **cùng `cacheNames` và `KeyGenerator`** với đọc làm mất đúng mục; đọc lại trả `load#4`. Các mục Bob/Acme và Alice/Beta vẫn tồn tại.
6. Alice đang thuộc Acme yêu cầu dữ liệu Beta sẽ bị facade chặn với `SecurityException`, trước khi truy vấn cache.

`ScopeKey` là một Java `record` bất biến, có `equals()`/`hashCode()` tương ứng với các thành phần. `"v1"` là namespace phiên bản để minh họa; muốn tăng phiên bản cần có kế hoạch xóa các mục cũ. `ConcurrentMapCacheManager` có thể dùng object key trực tiếp trong JVM; backend Redis hoặc cache phân tán có thể đòi hỏi chuyển đổi/serialize khác, không mặc định hiểu record này.

**Giới hạn an ninh của demo:** `Caller` được tạo thủ công để minh họa, chưa tích hợp Spring Security và chưa kiểm tra ACL từng tài liệu. Trong hệ thống thật, chỉ cho controller/entrypoint đi qua facade, tạo identity từ principal đã được xác thực, kiểm tra membership/ACL thật và hạn chế gọi trực tiếp `ScopedDocumentCache` từ các đường chưa được ủy quyền. Demo không chứng minh người dùng có quyền xem mọi tài liệu trong một tổ chức.

## 7. Khi nào dùng khóa mặc định, SpEL hoặc `KeyGenerator`?

Spring Cache mặc định sử dụng `SimpleKeyGenerator` nếu annotation không khai báo `key` hoặc `keyGenerator`:

| Phương thức | Khóa mặc định về mặt logic | Khi nào phù hợp? |
| --- | --- | --- |
| `get(String org, String id)` | `SimpleKey(org, id)` | Cả hai tham số quyết định kết quả |
| `get(String org, String user, String id)` | `SimpleKey(org, user, id)` | Kết quả cá nhân hóa theo user |
| `get(String org, String user, String id, String traceId)` | `SimpleKey` của cả bốn tham số | **Không phù hợp** nếu traceId không ảnh hưởng kết quả |
| `find(String id)` | Đối tượng `id` trực tiếp | Chỉ an toàn nếu phạm vi dữ liệu không bị bỏ sót |

Nếu các tham số đã đúng cấu trúc định danh, không nhất thiết phải viết generator riêng. Nhưng nếu cấu trúc lời gọi có thêm đối số không ảnh hưởng kết quả, hoặc cần chuẩn hóa namespace, custom key sẽ rõ ràng hơn.

### Dùng SpEL cho trường hợp đơn giản

~~~java
// Minh họa phương thức đã kiểm tra quyền bên ngoài.
// Khóa phụ thuộc ba tham số đầu; requestId không ảnh hưởng dữ liệu.
@Cacheable(
    cacheNames = "viewerDocuments",
    key = "T(java.util.List).of(#p0, #p1, #p2)"
)
public String read(String orgId, String viewerId, String docId,
                   String requestId) {
    return loadDocument(orgId, viewerId, docId);
}
~~~

`#p0`, `#p1`, `#p2` tương ứng với org, viewer, document. `List.of` trả danh sách bất biến có `equals` dựa trên các phần tử và không chấp nhận `null`; các định danh phải được xác thực/chuẩn hóa trước. Đây là **minh họa Spring Expression Language trong cache nội bộ**, không phải gợi ý dùng `List` trực tiếp làm key cho mọi backend. Các kiểu `loadDocument`, repository và quyền truy cập thuộc ứng dụng thực.

Với nhiều operation có thứ tự tham số khác nhau, `KeyGenerator` có thể trích các trường cần dùng một cách có chủ đích; cách này giúp xây dựng record key rõ nghĩa, nhưng **generator trong ví dụ chạy được yêu cầu đúng ba tham số**. Nếu thêm method `update(..., payload)` có bốn tham số, cần chủ động sửa generator hoặc dùng `key` riêng để hai operation cùng tạo **một** `ScopeKey` theo org/viewer/docId. Không sao chép generator ba tham số vào method bốn tham số rồi kỳ vọng hoạt động.

**`key` và `keyGenerator` loại trừ nhau trên cùng một annotation.** Chúng chỉ ảnh hưởng khóa; việc chọn tên cache do `cacheNames` hoặc `CacheResolver` đảm nhiệm.

## 8. Thay đổi quyền: tránh cache đúng khóa nhưng sai chính sách

Giả sử Alice đã có quyền xem trường `salary`. Phương thức `readForViewer(acme, alice, D1)` ghi kết quả có trường đó vào cache. Sau đó quyền của Alice bị giảm.

- **Chỉ có `userId` trong key:** cache cũ có thể vẫn chứa trường `salary`. Nếu quyền không được kiểm tra lại trên hit, đây là rò rỉ. Ngay cả khi quyền xem tài liệu vẫn còn, nội dung cần ẩn có thể khác đi.
- **Thêm `role` vào key:** có thể tạo khóa mới nếu role thay đổi, nhưng không đủ khi quyền dựa trên team, branch, ACL riêng, ABAC hoặc dữ liệu liên quan. Không nên xem role là fingerprint hoàn chỉnh.
- **Thêm `permissionVersion` đáng tin:** khi phiên bản thay đổi, key chuyển sang vùng giá trị mới; vẫn phải cập nhật version đúng lúc và xử lý các entry cũ.
- **Evict mục bị ảnh hưởng:** khi thay đổi quyền, xóa các mục cần thiết trước khi chúng tiếp tục được dùng; có thể phải xóa theo người dùng, tài liệu, tenant hoặc cả vùng tùy cấu trúc khóa/provider.
- **Kiểm tra quyền ở facade mỗi lần:** là lớp bảo vệ thiết yếu đối với quyền truy cập. Với nội dung đã được cache theo projection cũ, vẫn phải **không trả** projection có trường không còn được phép.

TTL chỉ giới hạn tuổi entry, **không tự bảo đảm việc thu hồi quyền có hiệu lực ngay**. Các hệ thống có yêu cầu thu hồi tức thời cần phối hợp authorization, invalidation/version và chính sách đồng bộ giữa nhiều instance.

### Quyền thay đổi trong khi request đang chạy

Có thể có race giữa lúc kiểm tra quyền và lúc lấy kết quả từ cache hoặc database. Với nghiệp vụ nhạy cảm, cần xác định mức đảm bảo nhất quán: transaction, version check, policy snapshot, kiểm tra lần cuối trước phát hành kết quả, hoặc cơ chế không trả dữ liệu nếu phiên bản quyền không khớp. Thiết kế cache key chỉ là một phần trong chiến lược nhất quán.

## 9. Đồng bộ khóa khi `@Cacheable`, `@CachePut`, `@CacheEvict`

Cần xác định **cache identity** chung cho thao tác đọc và thao tác thay đổi cùng dữ liệu. Trong ví dụ chạy được, `read` và `evict` có cùng chữ ký `(orgId, viewerId, documentId)` và cùng generator nên tạo cùng `ScopeKey`.

Với một phương thức cập nhật có thêm payload:

~~~java
// Minh họa: chữ ký thuộc service ứng dụng, không phải chương trình độc lập.
@CachePut(cacheNames = "viewerDocuments",
          key = "T(java.util.List).of(#p0, #p1, #p2)")
public ViewDto updateView(String orgId, String viewerId,
                          String documentId, UpdateRequest request) {
    return persistAndRender(orgId, viewerId, documentId, request);
}
~~~

Đoạn này chỉ đồng nhất với phương thức đọc **nếu phương thức đọc cũng dùng cùng kiểu key là `List.of(...)`**. Nó **không tương thích** với `ScopeKey` record ở ví dụ chạy được: cùng thông tin logic nhưng khác kiểu đối tượng thì các key không bằng nhau. Trong một ứng dụng hãy chọn **một chuẩn khóa thống nhất** và áp dụng cho tất cả operation liên quan, kể cả các phương thức evict theo sự kiện thay đổi dữ liệu.

Các lưu ý khác:

- `@CachePut` luôn thực thi method rồi đưa kết quả vào cache; tránh tự cập nhật kết quả của user khác khi chưa kiểm tra quyền.
- `@CacheEvict` có thể dùng `key` hoặc `keyGenerator`; mặc định evict sau khi method hoàn thành thành công. `beforeInvocation=true` thay đổi thời điểm nhưng không sửa được lỗi sai khóa.
- `@CacheEvict(allEntries=true)` xóa cả vùng. Với vùng dùng chung nhiều user/tenant, thao tác này có thể xóa rộng hơn dự kiến, dù không tự làm lộ dữ liệu.
- Một cập nhật tài liệu có thể ảnh hưởng **nhiều bản chiếu theo người dùng**. Xóa key của người sửa thôi có thể chưa đủ; cần thiết kế invalidation đa user, version theo tài liệu, TTL kết hợp hoặc cơ chế evict theo chính sách.
- Khi dùng cache phân tán nhiều instance, việc evict phải thực sự tác động tới kho cache chung; cache bộ nhớ trong mỗi JVM không đồng bộ eviction giữa các JVM.

## 10. Bảo mật thông tin trong chính khóa cache

Khóa có thể xuất hiện trong logs, dashboard, metrics, trace hoặc được serialize thành tên key vật lý trong Redis. Vì vậy:

1. **Không đưa token truy cập, mật khẩu, session secret, cookie hoặc dữ liệu nhạy cảm thô** vào cache key. Những giá trị này cũng thay đổi thường xuyên khiến hit rate thấp.
2. Ưu tiên định danh nội bộ ổn định, không mang thông tin nhạy cảm trực tiếp. Một opaque ID giúp giảm lộ dữ liệu so với email/tên thật, nhưng không tự tạo cơ chế phân quyền.
3. Khi cần khóa kiểu chuỗi cho Redis, chọn codec rõ ràng, không nhập nhằng và có namespace/version. Kiểm tra quy tắc serializer và cách provider thêm prefix.
4. Tránh khóa chứa object mutable, collection có thể sửa sau khi insert, hoặc class dùng `equals/hashCode` theo địa chỉ object. Java record bất biến thường thuận tiện cho in-memory.
5. Không log nguyên cache key khi nó có danh tính người dùng; chỉ log thông tin an toàn, giảm độ chi tiết và ẩn danh/giảm nhạy cảm phù hợp.
6. Không dùng hash không khóa của một dữ liệu bí mật rồi cho rằng dữ liệu đã được bảo vệ tuyệt đối: một số đầu vào có thể đoán và đối chiếu hash. Chính sách xử lý key/log phải phù hợp với mức nhạy cảm thực tế.

### Chú ý khi deploy nhiều instance

`ConcurrentMapCacheManager` của ví dụ lưu dữ liệu trong **bộ nhớ từng JVM**. Nó không tự đồng bộ cache giữa các replica và không cung cấp TTL theo yêu cầu. Với Caffeine, Redis hoặc backend khác, hành vi serializer, TTL, cache key conversion, giới hạn dung lượng và invalidation cần được kiểm chứng thực tế. Dùng Java record làm object key không đảm bảo backend phân tán có thể serialize record ấy theo cùng một cách ổn định.

## 11. Test những ranh giới bắt buộc

Không chỉ kiểm tra cache hit. Một bộ test đủ ý nghĩa nên chứng minh:

| Tình huống | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Cùng user, org và tài nguyên | Alice/Acme/D1 gọi lại | Hit, không đọc nguồn lần nữa |
| Hai user cùng org | Alice/Acme/D1 rồi Bob/Acme/D1 | Không dùng chung entry nếu view cá nhân hóa |
| Cùng user ID ở hai org | Alice/Acme/D1 rồi Alice/Beta/D1 | Không dùng chung entry |
| Yêu cầu vượt tổ chức | Caller của Acme yêu cầu Beta/D1 | Bị từ chối **trước** cả cache hit |
| Thu hồi quyền | User vừa bị rút quyền xem tài liệu | Không trả dữ liệu dù entry cũ vẫn còn |
| Thay quyền hiển thị | Role/ACL/permission version thay đổi | Không trả projection cũ có trường không được xem |
| Evict sau cập nhật | Sửa D1 rồi đọc lại | Không nhận giá trị cũ của mục bị ảnh hưởng |
| Hai phương thức khác nhau | Cùng cache name và tham số giống nhau | Không trùng ngữ nghĩa nếu kết quả khác nhau |
| Key serializer backend | Ghi ở một instance, đọc ở instance khác | Key được diễn giải nhất quán, không lộ data cross-tenant |
| Cache lỗi/miss | Provider timeout hoặc không có entry | Hệ thống vẫn áp dụng xác thực và phân quyền đúng |

Đối với cache chia sẻ nhiều tenant, luôn có test chứng minh `(tenant A, id X)` và `(tenant B, id X)` không trỏ chung entry. Khi có kết quả phân quyền, thêm test user bị **thu hồi quyền ngay trước một lời gọi vốn sẽ hit cache**. Một test chỉ chạy `@Cacheable` với cùng tham số hai lần không thể phát hiện rò rỉ phạm vi.

### Chẩn đoán sự cố

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Người dùng A thấy dữ liệu của B | Key bỏ qua user, org hoặc quyền ảnh hưởng kết quả | So sánh toàn bộ cacheName + key + scope của hai lời gọi |
| Khác tenant nhưng cùng cache hit | ID chỉ duy nhất trong từng tenant, key không có tenant | Bổ sung tenant hoặc tách cache theo tenant |
| Hit đúng user nhưng trả trường đã bị thu hồi | Không evict/version projection theo quyền hoặc kiểm tra quyền chỉ ở thân method | Bổ sung kiểm tra mỗi request và chiến lược invalidation |
| Cache hit rate rất thấp | Key chứa requestId, timestamp, object không có equals/hashCode phù hợp | Loại bỏ tham số không ảnh hưởng kết quả |
| Evict không có hiệu lực | Key read/evict khác kiểu, khác thứ tự hoặc khác cache name | Kiểm tra record/List/string và đúng thứ tự trường |
| Dữ liệu lẫn nhau sau khi chuyển tổ chức | Dùng userId mà thiếu activeOrganizationId | Thêm phạm vi tổ chức đã xác thực vào key |
| Backend Redis lỗi chuyển đổi key | Object key chỉ hoạt động trong ConcurrentMap | Định nghĩa serialization và kiểm thử nhiều instance |
| Không thấy interceptor chạy | Thiếu `@EnableCaching`, self-invocation hoặc bean không được Spring quản lý | Gọi qua bean/proxy khác và kiểm tra cấu hình |

## 12. Bài tập tự kiểm tra

**Bài 1 — Báo cáo tổ chức.** Hàm `getRevenue(String orgId, YearMonth month)` trả đúng một báo cáo chung cho mọi thành viên được phép xem trong tổ chức. Có cần đưa `userId` vào khóa không?  
**Đáp án:** thường không, vì nội dung không cá nhân hóa. Khóa `(orgId, month)` đủ nếu mọi tham số có ảnh hưởng đã được xét. Việc **được phép gọi** vẫn phải kiểm tra riêng mỗi lần.

**Bài 2 — Danh sách tài liệu.** Hai nhân viên cùng role `"EDITOR"` trong Acme, nhưng một người chỉ xem dự án X và người kia chỉ xem dự án Y. Có thể dùng `(orgId, role, page)` không?  
**Đáp án:** không đủ. Role không mô tả đầy đủ ACL/dự án; dùng khóa theo người xem hoặc phiên bản/chữ ký quyền được chứng minh đại diện đúng phạm vi truy cập, cùng kiểm tra quyền trước mỗi request.

**Bài 3 — Đổi quyền.** Alice từng thấy báo cáo có cột lương, sau đó bị đổi quyền. Key `(orgId, userId, reportId)` có đủ không?  
**Đáp án:** không đủ nếu entry cũ vẫn tồn tại và hệ thống không kiểm tra quyền/phiên bản nội dung. Cần kiểm tra quyền mỗi lời gọi và evict/re-key dữ liệu khi projection bị đổi; TTL chỉ giới hạn độ trễ.

**Bài 4 — Invalidation.** Method đọc dùng `record ScopeKey(org, user, id)`, còn method update dùng chuỗi `org + ":" + user + ":" + id`. Dữ liệu có được cập nhật cùng cache entry không?  
**Đáp án:** không, vì kiểu khóa và `equals` khác nhau, dù chữ có vẻ giống. Phải dùng cùng định dạng, cùng `cacheName` và cùng chính sách scope cho các operation liên quan.

**Bài 5 — Câu hỏi thiết kế.** Tại sao không dùng giá trị `SecurityContextHolder.getContext()` làm toàn bộ key?  
**Gợi ý:** đó là một object ngữ cảnh có thể chứa trạng thái không ổn định, thông tin nhạy cảm, không bảo đảm `equals/hashCode` theo định danh dữ liệu; trong async/background context còn có thể không truyền qua. Hãy trích những định danh **đã xác thực và ảnh hưởng kết quả** thành một khóa ổn định.

## Tài liệu tham khảo

- Spring Framework, Declarative Annotation-based Caching (`@Cacheable`, `KeyGenerator`, SpEL, proxy semantics): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework, Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Security, Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Boot, Caching Providers: https://docs.spring.io/spring-boot/reference/io/caching.html

**Ghi nhớ:** khóa cache cần biểu diễn đầy đủ *phạm vi quyết định nội dung kết quả*, thường bao gồm tenant và đôi khi người xem/quyền. Thao tác kiểm tra quyền phải chạy cả trên cache hit; các đường đọc, cập nhật và evict phải sử dụng cùng định danh. Cách ly cache, kiểm tra quyền và giới hạn truy vấn dữ liệu cần bổ trợ cho nhau.