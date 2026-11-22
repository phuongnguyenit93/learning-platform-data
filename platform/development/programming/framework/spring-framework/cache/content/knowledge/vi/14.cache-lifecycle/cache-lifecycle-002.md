# Rủi ro sửa đối tượng khả biến sau khi lấy từ cache

## Mục tiêu

Bài thuộc nhóm **Dữ liệu và vòng đời** của Spring Framework Cache. Sau bài học, bạn sẽ:

- Hiểu vì sao một giá trị trả về từ `@Cacheable` có thể là **chính cùng đối tượng trong cache**, chứ không phải bản sao độc lập.
- Nhận diện lỗi **shared mutable state**: một caller sửa `List`, `Map` hoặc thuộc tính của DTO, khiến caller tiếp theo nhận dữ liệu đã bị thay đổi ngoài ý muốn.
- Phân biệt **thay đổi trong cache**, **thay đổi ở nguồn dữ liệu** và **invalidating cache**; không nhầm việc sửa một Java object với việc cập nhật database.
- Phòng tránh bằng DTO bất biến, defensive copy đúng ranh giới, kiểm soát provider store-by-reference/store-by-value, và invalidation khi dữ liệu nguồn thay đổi.
- Chạy ví dụ Spring Boot Java 17+ tái hiện lỗi, so sánh bản sửa an toàn và kiểm tra đúng cache hit/miss.

**Nguyên tắc quan trọng:** `@Cacheable` bảo đảm phép tính có thể được tái sử dụng theo key; nó **không bảo đảm đối tượng trả về độc lập, bất biến, thread-safe hoặc tự đồng bộ với database**. Cách lưu và trả object phụ thuộc `Cache`/backend.

## 1. Vì sao sửa đối tượng sau khi lấy từ cache lại nguy hiểm?

Xét một service trả hồ sơ:

~~~java
@Cacheable(cacheNames = "profiles", key = "#p0")
public UserProfile findProfile(String userId) {
    return repository.find(userId);
}
~~~

Đoạn code là minh họa, với `UserProfile` và `repository` do ứng dụng định nghĩa. Giả sử kết quả có một danh sách vai trò có thể sửa:

~~~java
UserProfile p = profileService.findProfile("u1");
p.getRoles().add("admin");
~~~

Người viết có thể nghĩ mình chỉ chỉnh kết quả cho màn hình hiện tại. Tuy nhiên, nếu provider giữ **tham chiếu đến chính Java object** đã được cache, thao tác `add("admin")` sửa luôn trạng thái mà cache đang giữ. Lời gọi khác:

~~~java
UserProfile q = profileService.findProfile("u1");
~~~

có thể nhận cùng instance và thấy vai trò `admin`, **dù phương thức `findProfile` không chạy lại, database chưa cập nhật, và không ai gọi `@CachePut`**.

### Sơ đồ lỗi chia sẻ tham chiếu

~~~text
Lần đầu:
  Controller A ──findProfile("u1")──> cache MISS
                          │
                          └─ repository → object X
                                            ├─ roles: ["reader"]
                                            └─ được lưu bằng tham chiếu
  cache["u1"] ───────────────────────────────┘
  Controller A nhận chính object X

A thực hiện: X.roles.add("admin")

Lần sau:
  Controller B ──findProfile("u1")──> cache HIT
                           └──────> object X
                                      roles: ["reader","admin"]
                                      (KHÔNG truy vấn nguồn)
~~~

Điều này đặc biệt rõ với `ConcurrentMapCache` mặc định: API chính thức của Spring mô tả `isStoreByValue() == false` là chế độ mặc định, tức cache lưu **reference**. Vì vậy cache hit thường đưa ra cùng đối tượng đã lưu trong JVM, không clone nó.

**Đừng suy rộng cho mọi backend:** Redis và những provider sử dụng serialization thường làm việc với bytes rồi deserialize ra object mới cho từng lần đọc; các provider/local cache khác nhau có thể có chính sách copy khác nhau. Luôn xác minh cấu hình thực tế thay vì nghĩ “cache” luôn là bản sao hoặc luôn là tham chiếu.

## 2. Rủi ro xảy ra trong những tình huống nào?

### 2.1. Dữ liệu bị sửa xuyên request

Request A thêm phần tử vào list đã cache; request B đọc key đó và thấy phần tử vừa thêm. Nếu đây là quyền, giá hoặc giỏ hàng riêng người dùng, hậu quả có thể nghiêm trọng. Trạng thái không còn chỉ do nguồn dữ liệu quyết định.

### 2.2. Cache và database lệch nhau

Trong demo cache in-memory, sửa object trong cache **không tương đương** cập nhật database. Giá trị `cached.roles()` có thể là `["reader","admin"]` trong khi nguồn vẫn `["reader"]`. Lần `@CacheEvict` hoặc TTL hết hạn sẽ làm ứng dụng tải lại nguồn và “mất” thay đổi ngoài ý muốn.

Ngược lại, nếu giá trị cache là JPA entity còn đang được persistence context quản lý, sửa thuộc tính có thể tham gia **dirty checking** và gây update database lúc flush. Điều đó phụ thuộc transaction/EntityManager chứ không phải hành vi mặc định của `@Cacheable`. Vì thế cache trực tiếp mutable JPA entity là lựa chọn rủi ro và cần được xem xét kỹ.

### 2.3. Race condition giữa nhiều thread

`ConcurrentHashMap` có thread-safe operations đối với **map entries**; điều đó **không biến object bên trong thành thread-safe**. Hai request có thể đồng thời sửa một `ArrayList` hoặc Java bean được cache và gây lost update, dữ liệu quan sát không nhất quán hoặc lỗi khi duyệt collection. `@Cacheable(sync=true)` chỉ hỗ trợ phối hợp việc **nạp cùng key khi miss** nếu provider hỗ trợ; nó không khóa mọi lần chỉnh sửa của object sau khi trả về.

### 2.4. Tác dụng phụ “ẩn” của phương thức đọc

Một hàm chuẩn bị response dạng này là nguy hiểm nếu input là object lấy từ cache:

~~~java
// Minh họa anti-pattern; trả về DTO/collection có thể bị sửa.
public UserProfile personalize(UserProfile cached) {
    cached.getRoles().remove("internal");
    cached.setDisplayName("Hello " + cached.getDisplayName());
    return cached;
}
~~~

Dù tên phương thức là `personalize`, nó thay đổi trực tiếp shared instance. Một request khác có thể nhận tên đã chèn `"Hello"` nhiều lần hoặc danh sách vai trò đã bị lọc. **View/model transformation phải tạo dữ liệu mới, không sửa dữ liệu nguồn được chia sẻ.**

### 2.5. “Record là immutable” nhưng chứa tham chiếu mutable

~~~java
public record BookView(String id, List<String> tags) {}
~~~

Không thể gán lại trường `tags` sau khi record được tạo, nhưng vẫn có thể gọi `view.tags().add("changed")` nếu list bên trong là `ArrayList`. Record chỉ bảo đảm **các field reference cố định**, không tự đóng băng toàn bộ object graph. Cần bất biến từ gốc đến các đối tượng lồng nhau.

## 3. Hợp đồng cần nhớ: store-by-reference và store-by-value

| Khía cạnh | Store-by-reference | Store-by-value / serialization |
| --- | --- | --- |
| Giá trị được lưu | Thường giữ tham chiếu đến Java object. | Thường ghi một bản sao/serialized representation. |
| Người đọc nhận gì? | Có thể là cùng instance trong JVM với các caller khác. | Thường nhận object mới sau giải mã/copy khi hit. |
| Sửa DTO trả về | Có thể làm thay đổi chính nội dung cache. | Thường không sửa trực tiếp entry đã serialize, nhưng còn phụ thuộc provider và ranh giới. |
| Rủi ro concurrency | Shared mutable instance rất dễ bị truy cập cùng lúc. | Có thể giảm chia sẻ tham chiếu, nhưng không loại bỏ lỗi logic/staleness. |
| Đánh đổi | Ít copy, nhanh, nhưng nguy cơ aliasing. | Tốn serialization/CPU/bộ nhớ, yêu cầu dữ liệu phù hợp serializer. |
| Ví dụ | `ConcurrentMapCache` mặc định. | Cache có chính sách copy/serialization được cấu hình rõ; nhiều use case Redis. |

Trong Spring, `ConcurrentMapCache.isStoreByValue()` cho biết chính sách của implementation đó. `ConcurrentMapCacheManager` có thể được cấu hình store-by-value trên các phiên bản hỗ trợ, nhưng khi bật thường yêu cầu value có khả năng serialization và có chi phí copy. **Không coi đó là thiết kế bất biến cho cả hệ thống**: một API có đối tượng mutable vẫn có thể bị caller sửa ở tầng khác; quan trọng là hợp đồng sở hữu và cách xuất dữ liệu.

**Ngay cả ở lần cache miss:** Spring có thể trả trực tiếp object vừa được method tạo ra cho caller, đồng thời đưa object đó vào cache. Do đó chỉ copy trên đường cache hit (hoặc chỉ khi đọc qua một phương thức phụ) không chắc đã đủ. Bảo vệ **cả lúc ghi và lúc trả** hoặc dùng DTO bất biến ngay từ đầu.

## 4. Ví dụ chạy được: mutable reference làm “nhiễm” cache

Demo cố ý dùng `ConcurrentMapCacheManager` theo mặc định store-by-reference, Java 17+ và Spring Boot. “Database” là một `ConcurrentHashMap` chứa danh sách nguồn bất biến để quan sát rõ việc caller sửa cache **không làm đổi nguồn**.

Trong dự án Spring Boot Gradle hiện có, giữ plugin/version tương thích và bảo đảm có dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Tạo những file Java sau trong `src/main/java/example/mutablecache/`.

### 4.1. MutableProfile.java — đối tượng có collection sửa được

~~~java
package example.mutablecache;

import java.util.List;
import java.util.Objects;

public final class MutableProfile {
    private final String id;
    private final List<String> roles;

    public MutableProfile(String id, List<String> roles) {
        this.id = Objects.requireNonNull(id, "id");
        this.roles = Objects.requireNonNull(roles, "roles");
    }

    public String id() {
        return id;
    }

    // Cố ý trả thẳng list có thể sửa để minh họa lỗi.
    public List<String> roles() {
        return roles;
    }
}
~~~

Ở `MutableProfile`, trường `roles` là `final` nhưng **các phần tử của List vẫn thay đổi được** nếu caller giữ tham chiếu đến list sửa được. `final` không có nghĩa deep immutability.

### 4.2. ProfileSnapshot.java — record với defensive copy

~~~java
package example.mutablecache;

import java.util.List;
import java.util.Objects;

public record ProfileSnapshot(String id, List<String> roles) {
    public ProfileSnapshot {
        Objects.requireNonNull(id, "id");
        roles = List.copyOf(roles);
    }
}
~~~

`List.copyOf(roles)` tạo một danh sách không sửa được và tách khỏi nguồn **khi cần**; nếu nguồn là list mutable thì snapshot không bị ảnh hưởng bởi thay đổi sau đó của list nguồn. Trong demo, mỗi phần tử là `String` — kiểu bất biến — nên tầng list và phần tử đều an toàn. Với `List<MutableAddress>`, `List.copyOf` chỉ copy **cấu trúc list**, không clone từng `MutableAddress`; cần chuyển từng phần tử sang immutable value object.

### 4.3. CacheConfiguration.java — bật Spring Cache

~~~java
package example.mutablecache;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager(
                "mutableProfiles", "snapshotProfiles");
    }
}
~~~

Hai cache region có tên riêng để ta so sánh trên cùng ID mà không làm nhiễm kết quả của nhau. Không có TTL, distributed cache hoặc tự động sao chép object trong cấu hình này.

### 4.4. ProfileService.java — hai cách trả kết quả

~~~java
package example.mutablecache;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.Caching;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {
    private final Map<String, List<String>> source =
            new ConcurrentHashMap<>(Map.of(
                    "u1", List.of("reader")));

    private final AtomicInteger mutableLoads = new AtomicInteger();
    private final AtomicInteger snapshotLoads = new AtomicInteger();

    @Cacheable(cacheNames = "mutableProfiles", key = "#p0")
    public MutableProfile mutable(String id) {
        System.out.println("MUTABLE_LOAD #" +
                mutableLoads.incrementAndGet());
        return new MutableProfile(
                id, new ArrayList<>(loadRoles(id)));
    }

    @Cacheable(cacheNames = "snapshotProfiles", key = "#p0")
    public ProfileSnapshot snapshot(String id) {
        System.out.println("SNAPSHOT_LOAD #" +
                snapshotLoads.incrementAndGet());
        return new ProfileSnapshot(id, loadRoles(id));
    }

    // Trả danh sách nguồn bất biến cho mục đích kiểm chứng.
    public List<String> sourceRoles(String id) {
        return List.copyOf(loadRoles(id));
    }

    public int mutableReadCount() {
        return mutableLoads.get();
    }

    public int snapshotReadCount() {
        return snapshotLoads.get();
    }

    // Khi SOURCE được cập nhật hợp lệ, chủ động xóa entry
    // của cả hai vùng để lần đọc tiếp nạp snapshot mới.
    @Caching(evict = {
            @CacheEvict(cacheNames = "mutableProfiles", key = "#p0"),
            @CacheEvict(cacheNames = "snapshotProfiles", key = "#p0")
    })
    public void updateRoles(String id, List<String> newRoles) {
        if (!source.containsKey(id)) {
            throw new IllegalArgumentException("Unknown id: " + id);
        }
        source.put(id, List.copyOf(newRoles));
    }

    private List<String> loadRoles(String id) {
        List<String> roles = source.get(id);
        if (roles == null) {
            throw new IllegalArgumentException("Unknown id: " + id);
        }
        return roles;
    }
}
~~~

Giải thích các nhánh:

- `mutable("u1")` trả một `MutableProfile` mới có `ArrayList` có thể thay đổi. Kết quả được giữ trong `mutableProfiles["u1"]` theo tham chiếu.
- `snapshot("u1")` trả `ProfileSnapshot` với danh sách vai trò không sửa được; dù cache giữ reference, caller không có API bình thường để sửa trạng thái trong cache.
- `sourceRoles("u1")` đọc nguồn riêng và trả danh sách bất biến nhằm chứng minh việc chỉnh sửa cache không tự ghi ngược vào nguồn.
- `updateRoles(...)` là một đường cập nhật **có chủ đích**: đổi nguồn rồi `@Caching` kết hợp hai `@CacheEvict`, loại entry tương ứng sau khi method thành công. Đây là giải pháp cho thay đổi nguồn, **không phải lý do cho phép caller chỉnh object cache**.

### 4.5. MutableCacheApplication.java — quan sát kết quả

~~~java
package example.mutablecache;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MutableCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(MutableCacheApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ProfileService service) {
        return args -> {
            MutableProfile first = service.mutable("u1");
            MutableProfile second = service.mutable("u1");
            System.out.println("same reference = " + (first == second));

            first.roles().add("admin");
            System.out.println("unsafe cached roles = " +
                    service.mutable("u1").roles());
            System.out.println("source roles = " +
                    service.sourceRoles("u1"));
            System.out.println("mutable loads = " +
                    service.mutableReadCount());

            ProfileSnapshot safe = service.snapshot("u1");
            try {
                safe.roles().add("admin");
            } catch (UnsupportedOperationException ex) {
                System.out.println("snapshot mutation blocked");
            }
            System.out.println("safe cached roles = " +
                    service.snapshot("u1").roles());
            System.out.println("snapshot loads = " +
                    service.snapshotReadCount());

            service.updateRoles("u1", List.of("reader", "editor"));
            System.out.println("after update mutable = " +
                    service.mutable("u1").roles());
            System.out.println("after update snapshot = " +
                    service.snapshot("u1").roles());
        };
    }
}
~~~

Chạy trong thư mục dự án:

~~~bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
~~~

**Các dòng `System.out` của demo, theo thứ tự** (bỏ qua log Spring Boot/Gradle):

~~~text
MUTABLE_LOAD #1
same reference = true
unsafe cached roles = [reader, admin]
source roles = [reader]
mutable loads = 1
SNAPSHOT_LOAD #1
snapshot mutation blocked
safe cached roles = [reader]
snapshot loads = 1
MUTABLE_LOAD #2
after update mutable = [reader, editor]
SNAPSHOT_LOAD #2
after update snapshot = [reader, editor]
~~~

**Vì sao output này đúng?**

1. Lần đầu `mutable("u1")` là cache miss → in `MUTABLE_LOAD #1`, tạo đối tượng A và lưu A vào `mutableProfiles`.
2. Lần thứ hai cùng ID là hit, `first == second` bằng `true` vì provider mặc định giữ reference. Không in thêm `MUTABLE_LOAD`.
3. `first.roles().add("admin")` sửa trực tiếp list của A. Lần hit tiếp theo vẫn trả A nên thấy `[reader, admin]`, **trong khi nguồn là `[reader]`**. `mutable loads = 1` chứng minh method chưa chạy lại.
4. Lần đầu `snapshot("u1")` miss ở vùng độc lập; Java record `ProfileSnapshot` chứa list bất biến nên `add("admin")` ném `UnsupportedOperationException`, được demo bắt và in `snapshot mutation blocked`. Hit tiếp theo vẫn trả `[reader]`; `snapshot loads = 1`.
5. `updateRoles` đổi nguồn thành `[reader, editor]` và evict cả hai vùng. Lần `mutable` và `snapshot` tiếp theo đều miss, in `...LOAD #2` và nạp giá trị mới.

Các phép gọi đi từ `CommandLineRunner` sang Spring bean `ProfileService` nên qua proxy của caching interceptor. Nếu gọi `this.mutable(...)` trong cùng bean `ProfileService` ở chế độ proxy mặc định, annotation có thể bị bỏ qua; ví dụ sẽ không chứng minh được cơ chế cache.

**Phạm vi demo:** “database” chỉ là map trong một process, không có transaction/replica. Lệnh cập nhật nguồn và eviction là hai thao tác không atomically commit với database bên ngoài. Cần thiết kế thêm với giao dịch và nhiều instance ở production.

## 5. Bốn hướng phòng tránh phù hợp thực tế

### 5.1. Ưu tiên immutable DTO / snapshot

Đối với dữ liệu cache dùng chung, trả một **read-only snapshot**:

~~~java
public record CatalogItem(
        String id,
        String name,
        List<String> labels
) {
    public CatalogItem {
        labels = List.copyOf(labels);
    }
}
~~~

Người dùng không thể gọi `snapshot.labels().add(...)` thành công. Dữ liệu cache không phải entity để update trực tiếp. Với các thành phần lồng nhau, mọi phần tử cũng cần immutable hoặc được biến đổi thành immutable snapshot; `Collections.unmodifiableList(original)` chỉ là **view** của original, nên nếu original còn được bên khác sửa, view vẫn phản ánh các thay đổi ấy. `List.copyOf(original)` tách khỏi list có thể sửa, nhưng không deep-copy các phần tử mutable.

Khi cần thay đổi, hãy tạo instance mới, ví dụ `new CatalogItem(old.id(), "New", old.labels())`, và cập nhật source of truth qua service ghi.

### 5.2. Defensive copy ở cả đường vào và đường ra

Nếu không thể đổi API sang immutable, hãy xác định ranh giới ownership và tạo bản sao:

~~~java
// Giả sử CacheSnapshot là kiểu bất biến dùng nội bộ
// và MutableView là kiểu mutable dành cho caller.
public MutableView findForEditing(String id) {
    CacheSnapshot cached = cacheReader.findSnapshot(id);
    return toMutableView(cached);
}
~~~

Mã trên chỉ minh họa thiết kế; `cacheReader` và `toMutableView` là dependency/hàm nghiệp vụ. **Ý tưởng:** cache giữ đối tượng bất biến; mỗi caller nhận một view mutable **mới**. Sửa view không thể làm thay đổi cache. Nếu cache bắt buộc lưu object mutable, phải kiểm soát việc **copy trước khi put** và **copy sau khi get**, kể cả đường miss ban đầu; chỉ copy ở controller không bảo vệ mọi caller khác hoặc reference đã bị lộ.

Một defensive copy phải đủ sâu với những field có thể sửa. Copy outer object nhưng tiếp tục dùng chung `List<Address>` và `Address` mutable vẫn gây aliasing.

### 5.3. Cấu hình provider store-by-value khi cần, nhưng kiểm thử

Nếu hệ thống có cache cho object mutable, một backend serialize/deserialize hoặc store-by-value có thể giảm khả năng caller sửa trực tiếp cache entry. Tuy nhiên:

- Nó tiêu tốn tài nguyên và có điều kiện serialize/schema/version.
- Không phải mọi provider làm deep copy như nhau, và không nên giả định identity giữa hai lần đọc.
- Lần miss và đường ghi/phụ trợ vẫn cần kiểm tra: caller có thể giữ reference đến object trước khi serialize, hoặc có shared state ngoài cache.
- Không giải quyết việc **nguồn dữ liệu đã đổi** nhưng cache chưa evict/expire.
- Không tự làm logic truy cập dữ liệu hoặc mutable DTO thread-safe.

Để tránh lỗi, hãy có integration test chạy với **chính backend và cấu hình production**, không chỉ dựa trên kết quả của `ConcurrentMapCacheManager` trong test.

### 5.4. Tách read model khỏi write model

Một thiết kế dễ quản lý là:

~~~text
Database / Repository (source of truth)
           │
           ├── read → Immutable ProfileSnapshot → Cache → clients (read-only)
           │
           └── update command → validate → transaction → database
                                             │
                                             └── invalidate/update cache
~~~

**Không cho caller “sửa entity cache để lưu”.** Phương thức cập nhật có hợp đồng rõ, xác thực quyền, ghi database, điều phối `@CacheEvict`/`@CachePut` hoặc refresh sau commit theo yêu cầu hệ thống. Read-only DTO cũng hạn chế việc lộ entity lazy-loading, persistence context và trạng thái nội bộ.

## 6. Vì sao chỉ dùng @CacheEvict hoặc TTL chưa đủ?

`@CacheEvict` và TTL giải quyết **vòng đời entry**; chúng không bảo vệ object còn sống khỏi thay đổi tại chỗ.

Ví dụ caller vừa sửa `roles.add("admin")` và TTL còn 30 phút: trong 30 phút đó, các request hit cùng key có thể thấy trạng thái bị sửa. Giảm TTL có thể thu hẹp cửa sổ nhưng không bảo đảm mọi request đúng, còn tăng số lần đọc nguồn. Evict sau một update **có chủ đích** giúp nạp lại đúng source, nhưng không có annotation tự động phát hiện mọi thao tác `List.add` của caller và evict key.

Khi database đổi, **ngay cả immutable cached snapshot vẫn có thể stale**. Vì vậy cần cả hai lớp bảo vệ:

- **Bất biến/copy:** tránh tác dụng phụ không chủ đích từ caller lên cached value.
- **Invalidation/expiration:** duy trì độ mới khi source of truth thay đổi.

Với `@CachePut`, nếu code cập nhật cache bằng một object mutable còn được giữ bởi caller, object ấy có thể tiếp tục bị sửa **sau lần put** khi provider lưu reference. Muốn an toàn, đưa snapshot bất biến vào cache hoặc copy tại ranh giới lưu/trả.

## 7. Các tình huống chuyên sâu cần rà soát

### JPA entity và persistence context

- Không mặc định các entity từ `@Cacheable` vẫn được EntityManager quản lý ở mọi lần hit. Trạng thái managed/detached, lazy loading và dirty checking thay đổi theo ranh giới transaction và cách provider lưu/khôi phục.
- Cache trực tiếp mutable JPA entity dễ gây lỗi detached proxy, truy cập lazy ngoài session, thay đổi ngoài ý muốn hoặc trả trạng thái khác với database.
- Hướng phổ biến là map entity sang immutable DTO **trước khi đưa vào cache**, không cache object đang cần được sửa bởi ORM.

### Tham số key cũng mutable

Bài tập trung vào **value** nhưng còn một lỗi liên quan: nếu dùng mutable object làm **cache key** (đặc biệt trong hash-based map), thay đổi trường tham gia `equals/hashCode` sau khi put có thể khiến lookup/eviction thất bại. Dùng key bất biến như `String`, `Long` hoặc Java `record` với các component bất biến.

### Nested objects, arrays, Map và collection views

- `List.copyOf` không deep-copy các phần tử mutable.
- `Map.copyOf` không deep-copy values mutable.
- `byte[]`/array luôn có thể sửa nội dung dù reference là `final`; trả `array.clone()` ở boundary nếu cần bảo vệ.
- `Collections.unmodifiableList(list)` chặn sửa **qua view**, không ngăn bên sở hữu `list` gốc sửa nội dung.
- `Stream`/iterator trên collection mutable có thể quan sát thay đổi đồng thời hoặc ném exception; không coi đó là snapshot.

### Multi-tenant và bảo mật

Nếu entry là dữ liệu phân quyền theo user/tenant, việc dùng cache key chỉ có `id` đã là vấn đề riêng. Shared mutable object làm tình trạng nguy hiểm hơn: request này có thể sửa object mà request khác dùng. Key phải chứa đủ ngữ cảnh có ảnh hưởng kết quả và authorization phải được kiểm tra ở đường gọi có hiệu lực **cả khi cache hit**. Không coi cache hoặc `roles` có thể bị sửa từ response là nguồn quyết định quyền truy cập.

### Local cache, distributed cache và nhiều replica

Nếu cache lưu reference trong JVM, hai request ở **cùng JVM** có thể chia sẻ trực tiếp object; replica khác có cache local riêng. Redis serialized cache thường không chia sẻ cùng Java object reference giữa JVMs, nhưng vẫn có vấn đề stale data, xóa không đồng bộ, serialization schema và mutable object ở tầng ứng dụng. Không dựa vào một demo in-memory để kết luận hành vi của backend khác.

### Định danh object không phải là hợp đồng giá trị

Trong demo, `first == second` là `true` để lộ lỗi. Nhưng ở ứng dụng thật, `==` không phải tiêu chí duy nhất: backend store-by-value có thể trả hai instance khác nhau với nội dung giống nhau. Test cần kiểm tra **nội dung sau mutation**, **số lần load nguồn** và **nghĩa nghiệp vụ**, không chỉ identity.

## 8. Chiến lược kiểm thử

| Kịch bản | Thao tác | Kỳ vọng đúng |
| --- | --- | --- |
| Hai lượt đọc cùng key | Gọi `@Cacheable` hai lần | Lần đầu miss, lần hai hit; nguồn chạy một lần. |
| Cố sửa kết quả immutable | Gọi `snapshot.roles().add(...)` | `UnsupportedOperationException`; entry không đổi. |
| Sửa đối tượng mutable local | Gọi `mutable.roles().add(...)` | Demo tái hiện object cache bị thay đổi, để biết rủi ro. |
| Kiểm tra source of truth | Sau khi sửa mutable cache, đọc nguồn độc lập | Nguồn vẫn nguyên vẹn; không nhầm sửa cache với lưu DB. |
| Update dữ liệu hợp lệ | Gọi write service, evict/put phù hợp | Read tiếp theo nhận dữ liệu mới; không stale ngoài hợp đồng. |
| Collection lồng nhau | Thử sửa field của phần tử `List<Address>` | Immutable DTO cần bảo vệ được cả phần tử, không chỉ list. |
| Hai request đồng thời | Nhiều thread đọc/sửa cùng value | Không có data race vì API không lộ mutable shared reference. |
| Backend production | Chạy trên Redis/Caffeine/JCache theo cấu hình thực | Xác nhận copy, serializer, object identity và TTL thực tế. |
| Key/tenant khác nhau | Dùng cùng ID ở tenant khác | Không dùng nhầm cache entry hoặc state giữa tenant. |

Một integration test theo ý tưởng sau sẽ phát hiện thiết kế không an toàn:

~~~java
// Minh họa test logic, không phải file độc lập.
ProfileSnapshot first = service.snapshot("u1");
assertThrows(UnsupportedOperationException.class,
        () -> first.roles().add("admin"));
assertEquals(List.of("reader"), service.snapshot("u1").roles());
~~~

Đây là pseudocode theo phong cách JUnit 5; cần test dependency và import `assertThrows`/`assertEquals` nếu đưa vào dự án. Demo Spring Boot ở mục 4 đã cho đường chạy đầy đủ và stdout tương ứng.

### Checklist trước khi merge

1. [ ] Đã xác định `Cache`/provider lưu reference hay value, không đoán từ tên “cache”.
2. [ ] Kết quả `@Cacheable` là immutable snapshot hoặc có defensive copy tại ranh giới phù hợp.
3. [ ] Mọi collection, array và đối tượng lồng nhau đều được đánh giá về mutability; record + mutable list chưa an toàn.
4. [ ] Không trả trực tiếp cached JPA entity để controller sửa, nếu nghiệp vụ chỉ cần read model.
5. [ ] Các thao tác ghi dữ liệu có đường cập nhật riêng; phối hợp evict/put/TTL và ranh giới transaction.
6. [ ] Không dùng cache như cơ chế phân quyền; key, tenant và authorization được xác định đúng.
7. [ ] Kiểm thử cache hit/miss, hành vi khi caller cố sửa value, dữ liệu nguồn, concurrent requests và backend thật.
8. [ ] Theo dõi stale data, số lần load, TTL và consistency; không coi tỷ lệ hit cao là bằng chứng đúng đắn.

## Tài liệu chính thức

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — ConcurrentMapCache API (`isStoreByValue`): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework — Configuring Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
