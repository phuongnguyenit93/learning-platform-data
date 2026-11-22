# Tranh chấp giữa đọc, cập nhật và xóa trong Spring Cache

## Mục tiêu và phạm vi

**Spring Cache không tự biến toàn bộ quy trình “đọc dữ liệu → ghi cache → cập nhật nguồn → xóa cache” thành một transaction nguyên tử.** Trong hệ thống có nhiều thread, nhiều request, nhiều instance hoặc cache phân tán, các thao tác **@Cacheable**, **@CachePut** và **@CacheEvict** có thể xen kẽ. Nếu không thiết kế thứ tự và tính nhất quán, một kết quả đọc **cũ** có thể xuất hiện trở lại trong cache **sau** khi dữ liệu nguồn đã được cập nhật, thậm chí **sau** khi đã evict.

Mục tiêu sau bài:
1. Phân biệt **thread-safe cache** với **nghiệp vụ có tính nhất quán khi đồng thời**.
2. Đọc được timeline của ba cuộc đua: **read–read**, **read–put**, **read–evict**, cũng như các biến thể **put–put** và **put–evict**.
3. Hiểu đúng **@Cacheable(sync = true)**: giảm các lượt tải trùng nhau cho một key khi provider hỗ trợ, **không** tạo một khóa toàn cục bảo vệ mọi cập nhật/xóa.
4. Phân tích **@CachePut** và **@CacheEvict(beforeInvocation = false/true)** cùng ranh giới transaction.
5. Tái hiện có kiểm soát hai race condition bằng **Java 17, Spring Framework và CountDownLatch**; không dựa vào sleep hay kết quả ngẫu nhiên.
6. Chọn giải pháp theo mức nhất quán cần thiết: versioned keys, invalidation sau commit, đồng bộ theo khóa, kiểm tra version/CAS, event và thử nghiệm đa luồng.

Bài này xét Spring Cache Abstraction, không giả định Redis/Caffeine/Ehcache có cùng khả năng khóa, độ trễ mạng hoặc tính atomic. Ví dụ dùng **ConcurrentMapCacheManager** của Spring Framework trong **một JVM** nhằm làm rõ trình tự; khi đổi cache provider phải kiểm tra lại semantics thực tế.

---

## 1. Năm thao tác tưởng đơn giản nhưng không nguyên tử khi ghép lại

Một thao tác **@Cacheable** thông thường diễn ra gần như sau:

~~~text
READ(key):
  1. Kiểm tra cache[key]
  2. HIT -> trả giá trị đã cache
  3. MISS -> gọi method thật đọc nguồn dữ liệu
  4. Nhận result từ method
  5. Ghi cache[key] = result
  6. Trả result
~~~

Nếu có một thread khác cập nhật/xóa cache giữa bước **3** và **5**, bước **5** có thể ghi vào cache một giá trị được đọc **trước** thời điểm cập nhật đó.

Một thao tác **@CachePut**:

~~~text
UPDATE_AND_PUT(key, next):
  1. Gọi method thật (ví dụ cập nhật database)
  2. Method hoàn thành và trả result
  3. Nếu condition/unless cho phép: put cache[key] = result
~~~

Một thao tác **@CacheEvict** mặc định:

~~~text
UPDATE_AND_EVICT(key):
  1. Gọi method thật (ví dụ cập nhật database)
  2. Method hoàn thành thành công
  3. Evict cache[key]
~~~

**Không có mặc định nào trong ba mô tả này bảo đảm các bước của các request khác nhau không xen kẽ.** Một lệnh put hoặc evict đơn lẻ có thể thread-safe theo provider; điều đó **không** làm chuỗi đọc nguồn và ghi cache thành một critical section thống nhất với hoạt động ghi/xóa.

Sơ đồ hai thread:

~~~text
Thread R (@Cacheable)                    Thread W (@CachePut)
---------------------                    --------------------
cache miss: key=P
đọc database: P=v1
                                       cập nhật database: P=v2
                                       cache.put(P, v2)
đọc hoàn tất: v1
cache.put(P, v1)
                                       database đang là v2
cache cuối cùng: P=v1  <-- STALE
~~~

Kết quả “ghi sau cùng thắng” của một map không đồng nghĩa với **“phiên bản dữ liệu mới nhất thắng”**. Thứ tự put vào cache có thể **khác** thứ tự thời điểm snapshot được đọc từ database.

## 2. Phân biệt ba thuộc tính: an toàn luồng, nguyên tử và nhất quán

| Tính chất | Câu hỏi cần trả lời | Điều không thể suy ra |
| --- | --- | --- |
| **Thread-safety** | Hai thread gọi put/get/evict có phá hỏng cấu trúc cache không? | Không bảo đảm giá trị cuối cùng là dữ liệu nghiệp vụ mới nhất |
| **Atomicity của một thao tác** | Một putIfAbsent/get-with-loader có được provider thực hiện nguyên tử không? | Không bao trùm toàn bộ database update + cache read/put/evict |
| **Consistency / freshness** | Sau cập nhật thành công, các lượt đọc thấy phiên bản nào và trong bao lâu? | Không tự được bảo đảm bởi @Cacheable/@CachePut/@CacheEvict |
| **Isolation** | Một request đọc có quan sát trạng thái đang thay đổi của request khác không? | Không tự có chỉ vì cache dùng ConcurrentHashMap |
| **Ordering** | Put, evict và commit được áp dụng theo thứ tự nào? | Không nhất thiết trùng thứ tự bắt đầu request |

**ConcurrentMapCache** dùng các cấu trúc an toàn luồng cho thao tác cache trong tiến trình. Nó không biết transaction database, thời điểm snapshot nghiệp vụ được lấy hay một bản ghi đã bị thu hồi quyền truy cập. Nói cách khác, **data-race-free** ở cấu trúc lưu trữ không loại bỏ **race condition** ở logic nghiệp vụ.

Trong nhiều hệ thống, cache là một lớp **tăng hiệu năng** với tính nhất quán cuối cùng, không phải nguồn dữ liệu có tính serializable. Cần xác định trước liệu vài mili giây dữ liệu cũ có chấp nhận được, hay yêu cầu đúng ngay sau khi write hoàn tất.

## 3. Tranh chấp read–read: hai request cùng miss

Giả sử key `P` chưa có trong cache. Hai thread cùng gọi @Cacheable:

~~~text
Thời gian       T1: read(P)                  T2: read(P)
----------      --------------------         --------------------
t0              cache.get(P) -> MISS
t1                                           cache.get(P) -> MISS
t2              loadFromDb(P)
t3                                           loadFromDb(P)
t4              cache.put(P, v1)
t5                                           cache.put(P, v1)
~~~

Nếu hai lần đọc cho cùng kết quả, cache cuối cùng đúng **nhưng database đã chịu hai lượt load**. Đây là **cache stampede** hoặc **thundering herd** cho cùng key; nhiều request có thể làm tải tăng đột ngột khi cache mới khởi động, TTL đồng loạt hết hạn hoặc entry vừa bị xóa.

Nếu nguồn dữ liệu thay đổi giữa t2 và t3, hai lời gọi còn có thể tính ra **hai phiên bản khác nhau**, rồi kết quả đến sau được ghi đè kết quả đến trước.

### Dùng @Cacheable(sync = true) đúng mục đích

~~~java
// Ví dụ annotation trên một method công khai của Spring bean.
@Cacheable(cacheNames = "profiles", key = "#p0", sync = true)
public Profile find(String profileId) {
    return repository.find(profileId);
}
~~~

Đây là **đoạn minh họa**, chưa phải chương trình chạy độc lập (Profile và repository do dự án định nghĩa). Với sync=true, Spring yêu cầu cache provider phối hợp **một lượt tải cho cùng khóa** khi nhiều thread cùng miss. Các request còn lại có thể chờ kết quả đã tính.

Nhưng cần nhớ:

- **sync=true chủ yếu điều phối các lượt tải đồng thời cho cùng key của @Cacheable**, không có nghĩa khóa cả @CachePut, @CacheEvict hay giao dịch database.
- Tính năng là **hint/capability của provider**; Spring nói các CacheManager tích hợp lõi của framework hỗ trợ, còn cache provider khác phải kiểm chứng tài liệu và test.
- Chế độ sync có các giới hạn: **không dùng unless**, **chỉ một cache** trên operation và **không phối hợp thêm cache operation khác** trên cùng method.
- Khi nhiều instance ứng dụng dùng cache local riêng, mỗi JVM có thể đồng bộ riêng nhưng **không tự có mutex phân tán toàn hệ thống**.
- Thay đổi một phương thức đọc sang sync=true **không khép lại mọi khoảng thời gian** giữa đọc database và writer thay đổi dữ liệu; cần phân tích cả update và eviction.

### Sai lầm cần tránh

~~~java
// Không được coi đây là bảo đảm "mọi thao tác cùng key đều tuần tự".
@Cacheable(cacheNames = "profiles", sync = true)
public Profile read(String id) { ... }
~~~

sync=true không đồng nghĩa với transaction serializable hay một distributed lock bao cả các phương thức viết dữ liệu khác. Mục tiêu chính của nó là hạn chế **nhiều loader chạy đồng thời** trong các trường hợp provider hỗ trợ.

## 4. Tranh chấp read–put: một kết quả cũ ghi đè kết quả mới

Đây là race phổ biến khi dùng **@Cacheable** cho đọc và **@CachePut** cho cập nhật.

Giả sử trước đó cache rỗng, database chứa profile P phiên bản **v1**:

~~~text
t0   Reader: @Cacheable("profiles", key="P") -> MISS
t1   Reader: đọc từ database -> snapshot v1
t2   Reader: xử lý tiếp chậm / chờ I/O
t3   Writer: @CachePut update(P, v2) cập nhật database thành v2
t4   Writer: cache.put("P", v2)
t5   Reader: hoàn tất và cache.put("P", v1)
t6   Reader khác: @Cacheable đọc cache -> HIT v1
~~~

**Quan sát:** @CachePut không sai về cách thực thi; nó đã đặt v2 vào cache. Vấn đề là một request @Cacheable cũ vẫn đang ở giữa quá trình load và **put v1 sau v2**.

Với concurrent map, **put sau sẽ thay value tại cùng key**, kể cả value đó được tính từ snapshot cũ. @CachePut không có built-in “chỉ cho phép ghi nếu result.version lớn hơn entry hiện tại”.

### Không phải lỗi “khóa cache không đúng”

Nếu key và cacheName đều chính xác mà kết quả vẫn stale, nguyên nhân vẫn có thể là **tranh chấp thời gian**. Đổi từ key String sang record, thêm hashCode hoặc tăng TTL **không giải quyết** việc v1 được ghi sau v2. Những điều đó chỉ giải quyết sai danh tính key hoặc tuổi thọ entry.

### Tranh chấp khi cập nhật hai lần song song

Còn một biến thể put–put:

~~~text
T1 bắt đầu update(P, v2)       T2 bắt đầu update(P, v3)
T1 ghi DB phiên bản v2
                               T2 ghi DB phiên bản v3
                               T2 @CachePut -> cache v3
T1 (trả về trễ) @CachePut -> cache v2
DB cuối v3, cache cuối v2
~~~

Timeline này mô tả **một interleaving có thể xảy ra**, không phải thứ tự mặc định mọi database áp dụng. Kết quả phụ thuộc thời điểm commit, thời điểm method trả về và thứ tự put thực tế. Ngay cả khi database tự bảo vệ bằng optimistic locking, **cache vẫn cần được cập nhật theo version/commit đúng**; nếu không, kết quả cũ có thể ghi đè entry mới.

## 5. Tranh chấp read–evict: dữ liệu cũ “hồi sinh” sau khi xóa

Nhiều lập trình viên cho rằng sau khi update xong chỉ cần @CacheEvict là mọi lượt đọc kế tiếp an toàn. Điều này thường đúng trong luồng **tuần tự**, nhưng không bảo đảm khi có **read đang bay (in-flight)**:

~~~text
Database ban đầu: P=v1           Cache ban đầu: rỗng

Reader                          Writer
--------------------------      ---------------------------
cache miss P
snapshot database P=v1
đang chờ xử lý
                                cập nhật database P=v2
                                @CacheEvict(P) -> xóa cache P
hoàn tất đọc snapshot v1
@Cacheable -> put(P, v1)
                                database hiện tại = v2
Cache cuối: P=v1  <-- entry cũ bị tái tạo sau eviction
~~~

Tình huống này gọi là **stale repopulation** hoặc **resurrection of stale cache value**. Lệnh evict có thể đã chạy **đúng**, nhưng nó chỉ xóa trạng thái cache **tại thời điểm ấy**; không thể tự hủy mọi kết quả load đã bắt đầu từ trước.

Vì thế, thêm @CacheEvict vào writer **không đủ để chứng minh** không bao giờ có stale data. Cần xét deadline, reader in-flight và cơ chế cô lập giữa read và write.

### @CacheEvict(beforeInvocation = false) hay true?

**Mặc định**:

~~~java
@CacheEvict(cacheNames = "profiles", key = "#p0")
public void updateAndInvalidate(String id, Profile next) {
    repository.save(next);
}
~~~

Trong lời gọi đồng bộ thông thường, Spring evict **sau khi method hoàn thành thành công**. Nếu method ném exception, operation evict theo cấu hình mặc định thường không được thực hiện. Với giao dịch database, “method thành công” và “đã commit” **chưa chắc là một thời điểm**; thứ tự advice và cấu hình transaction-aware ảnh hưởng kết quả.

Đổi sang:

~~~java
@CacheEvict(
    cacheNames = "profiles",
    key = "#p0",
    beforeInvocation = true
)
public void updateAndInvalidate(String id, Profile next) {
    repository.save(next);
}
~~~

Spring yêu cầu evict **trước** khi gọi method nghiệp vụ. Điều này có thể khiến reader khác **miss trước khi dữ liệu mới được ghi**, rồi load một snapshot cũ và đặt lại vào cache. Do vậy, **beforeInvocation=true không phải công tắc tránh race**. Ngoài ra, nó có thể xóa entry ngay cả khi method nghiệp vụ sau đó thất bại.

Hai method trên là **hai cấu hình minh họa độc lập**; Profile và repository chưa được cung cấp để chạy, không copy cả hai lên cùng method.

### So sánh theo yêu cầu

| Cấu hình | Thời điểm yêu cầu evict | Rủi ro cần cân nhắc |
| --- | --- | --- |
| @CacheEvict mặc định | Sau method thành công | Reader in-flight vẫn có thể put giá trị cũ sau eviction; commit có thể chưa hoàn tất |
| @CacheEvict(beforeInvocation=true) | Trước khi gọi method | Reader miss trong thời gian update rồi load dữ liệu cũ; method thất bại vẫn đã evict |
| Cache.evict(key) trực tiếp | Khi code gọi cache API | Tùy provider, eviction có thể deferred/async |
| Cache.evictIfPresent(key) trực tiếp | API kỳ vọng key lập tức không nhìn thấy sau thao tác | Vẫn không ngăn loader cũ put lại sau đó |
| Transaction-aware put/evict | Có thể hoãn đến after-commit khi transaction active | Giảm một số lỗi rollback/commit, không tự loại bỏ reader in-flight |

**Đừng gộp hai yêu cầu** “evict có hiệu lực ngay” và “không có ai được ghi lại dữ liệu cũ”: đó là hai bài toán khác nhau.

## 6. Ví dụ chạy được: hai race có kiểm soát bằng CountDownLatch

Ví dụ sau dùng Java 17, Spring Framework 6.2.19 và **ConcurrentMapCacheManager**. Không dùng Thread.sleep() để đoán thứ tự thread; thay vào đó, hai CountDownLatch cố định đúng điểm reader đã lấy snapshot nhưng **chưa trả result cho @Cacheable**.

Mục tiêu quan sát:
- **RACE_PUT**: writer đã cập nhật nguồn lên v2 và put v2; sau đó reader đang chờ put lại v1.
- **RACE_EVICT**: writer cập nhật nguồn lên v4 và evict; sau đó reader đang chờ put lại v3.
- Bộ đếm load bằng 2 chứng minh mỗi race đều có method đọc thật chạy.
- Các lời gọi @Cacheable/@CachePut/@CacheEvict đều đi qua **Spring bean proxy** lấy từ ApplicationContext; nếu tự new service hoặc self-invocation, kết quả sẽ khác.

### 6.1. Cấu trúc dự án

~~~text
spring-cache-race-demo/
├── pom.xml
└── src/main/java/demo/CacheRaceDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-cache-race-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. src/main/java/demo/CacheRaceDemo.java

~~~java
package demo;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class CacheRaceDemo {

    // Cho main biết reader đã lấy snapshot, nhưng chưa hoàn tất.
    public static final class Gate {
        final CountDownLatch snapshotTaken = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
    }

    public static class ProfileService {
        private final AtomicReference<String> source =
            new AtomicReference<>("v1");
        private final AtomicInteger reads = new AtomicInteger();
        private volatile Gate gate;

        // Phục vụ test; không phải cache operation.
        public void arm(Gate gate) {
            this.gate = gate;
        }

        // Thực hiện lời gọi khi cache miss.
        @Cacheable(cacheNames = "profiles", key = "#p0")
        public String read(String id) {
            String snapshot = source.get();
            reads.incrementAndGet();

            Gate currentGate = gate;
            if (currentGate != null) {
                currentGate.snapshotTaken.countDown();
                try {
                    if (!currentGate.release.await(
                            10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                            "Reader release timed out");
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                        "Reader interrupted", ex);
                }
            }
            return snapshot;
        }

        // Source thay đổi, rồi Spring put kết quả sau method.
        @CachePut(cacheNames = "profiles", key = "#p0")
        public String updateAndPut(String id, String nextValue) {
            source.set(nextValue);
            return nextValue;
        }

        // Source thay đổi, rồi Spring evict sau method thành công.
        @CacheEvict(cacheNames = "profiles", key = "#p0")
        public void updateAndEvict(String id, String nextValue) {
            source.set(nextValue);
        }

        // Chuẩn bị trạng thái cho race thứ hai.
        @CacheEvict(cacheNames = "profiles", key = "#p0")
        public void evictOnly(String id) {
            // Cache interceptor thực hiện eviction.
        }

        public void changeSourceOnly(String value) {
            source.set(value); // Không tác động cache.
        }

        public String sourceValue() {
            return source.get();
        }

        public int loadCount() {
            return reads.get();
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("profiles");
        }

        @Bean
        public ProfileService profileService() {
            return new ProfileService();
        }
    }

    private static FutureTask<String> startReader(
            ProfileService service) {
        FutureTask<String> task =
            new FutureTask<>(() -> service.read("P"));
        Thread thread = new Thread(task, "cache-reader");
        thread.start();
        return task;
    }

    private static void awaitSnapshot(Gate gate)
            throws InterruptedException {
        if (!gate.snapshotTaken.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "Snapshot was not taken");
        }
    }

    public static void main(String[] args) throws Exception {
        try (var ctx =
                 new AnnotationConfigApplicationContext(Config.class)) {
            // Quan trọng: lấy bean proxy từ Spring, không tự new.
            ProfileService service =
                ctx.getBean(ProfileService.class);
            Cache cache = ctx.getBean(CacheManager.class)
                .getCache("profiles");

            // Race A: @CachePut v2 xảy ra trước khi read v1 trả về.
            Gate first = new Gate();
            service.arm(first);
            FutureTask<String> readerA = startReader(service);
            awaitSnapshot(first); // Reader đã chụp snapshot v1.
            service.updateAndPut("P", "v2");
            first.release.countDown();
            String readA = readerA.get(10, TimeUnit.SECONDS);
            System.out.println("RACE_PUT read=" + readA
                + " source=" + service.sourceValue()
                + " cache=" + cache.get("P", String.class));

            // Race B: dọn key cũ, chuẩn bị nguồn v3.
            service.evictOnly("P");
            service.changeSourceOnly("v3");

            Gate second = new Gate();
            service.arm(second);
            FutureTask<String> readerB = startReader(service);
            awaitSnapshot(second); // Reader đã chụp snapshot v3.
            service.updateAndEvict("P", "v4");
            second.release.countDown();
            String readB = readerB.get(10, TimeUnit.SECONDS);
            System.out.println("RACE_EVICT read=" + readB
                + " source=" + service.sourceValue()
                + " cache=" + cache.get("P", String.class));
            System.out.println("loadCount="
                + service.loadCount());
        }
    }
}
~~~

Trong demo, **gate** được đặt qua public method không đánh dấu caching. Khi reader bắt đầu **@Cacheable**, Spring thấy cache miss và gọi method thật; method đọc source trước, sau đó dừng tại CountDownLatch. Writer update/evict hoàn tất, main mới cho reader tiếp tục. FutureTask.get đợi cả lời gọi **qua proxy** trả về, nên cả bước cache.put của @Cacheable đã được xử lý trước khi main in giá trị.

### 6.4. Biên dịch và chạy

Yêu cầu JDK 17+ và Maven. Tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheRaceDemo
~~~

Stdout kỳ vọng do chương trình in ra (không tính log riêng của Maven hoặc thư viện):

~~~text
RACE_PUT read=v1 source=v2 cache=v1
RACE_EVICT read=v3 source=v4 cache=v3
loadCount=2
~~~

Giải thích kết quả:

1. **RACE_PUT:** Reader chụp snapshot v1 nhưng chưa trả kết quả. Writer cập nhật source thành v2 và @CachePut ghi **v2**. Khi reader được release, @Cacheable ghi kết quả snapshot **v1**, thay entry v2. Kết quả source=v2, cache=v1.
2. **RACE_EVICT:** Đầu tiên xóa entry cũ rồi chuyển source sang v3; Reader chụp v3 và chờ. Writer đổi source sang v4, @CacheEvict xóa key P. Reader được release và @Cacheable **tạo lại entry v3**, dù source đã là v4.
3. **loadCount=2:** Hai lần @Cacheable miss thực sự đọc nguồn, mỗi race một lần; không có thao tác đọc nguồn nào bị cache hit trong hai tình huống.
4. **CountDownLatch** làm thứ tự thao tác có kiểm soát; đây không phải chứng minh hai interleaving trên luôn xảy ra với mọi tải thực tế. Race thực tế phụ thuộc thời điểm scheduler, I/O, transaction và provider; test xác định được đường đi mà ứng dụng phải xử lý.

Ví dụ không dùng transaction hoặc cache phân tán, nên **chỉ chứng minh race giữa Spring annotation cache operations và source in-memory**. AtomicReference bảo đảm thao tác đọc/ghi một reference riêng lẻ an toàn; nó **không** bảo đảm cập nhật source và cache là một operation nguyên tử.

### 6.5. Vì sao không dùng sleep để ép thứ tự?

Các test kiểu Thread.sleep(100) giữa hai lời gọi thường **flaky**: máy CI chậm hơn, GC hoặc tải hệ thống thay đổi lịch thread. Với CountDownLatch, ta biết chính xác một reader đã đi qua điểm lấy snapshot trước khi writer chạy. Có **timeout** để test không treo vĩnh viễn khi code gặp lỗi.

Trong test production, còn nên:
- Chạy trên **ApplicationContext thật** để bảo đảm annotation hoạt động qua proxy.
- Kiểm tra **giá trị nguồn lẫn giá trị trong cache**, không chỉ kết quả trả về.
- Dùng **Future/ExecutorService**, barriers/latches và bounded timeout.
- Test thêm trường hợp writer ném exception, rollback transaction và cache provider có độ trễ.
- Với Redis/Caffeine/Ehcache, chạy integration test trên đúng provider; không ngoại suy kết quả atomicity của ConcurrentMapCacheManager sang mọi môi trường.

## 7. Tổng hợp các interleaving dễ gây lỗi

| Tranh chấp | Đường diễn biến nguy hiểm | Kết quả không mong muốn |
| --- | --- | --- |
| **read–read** | Hai miss cùng key, hai loader chạy | Tải tăng; result đến sau có thể là snapshot cũ |
| **read–put** | Read snapshot cũ, @CachePut ghi mới, read cũ put sau | Cache quay lại phiên bản cũ |
| **read–evict** | Read snapshot cũ, writer evict, read cũ put sau | Entry stale bị tái tạo sau eviction |
| **put–put** | Hai cập nhật có thời điểm commit/result khác thứ tự put | Cache chứa phiên bản không mới nhất |
| **put–evict** | Put và eviction từ hai workflow khác nhau xen kẽ | Entry mới biến mất hoặc entry cũ còn tùy thứ tự |
| **clear–read** | Clear toàn cache khi reader vẫn đang load | Reader có thể put lại entry sau clear |
| **write–transaction** | Cache put trước commit hoặc evict chưa phù hợp rollback | Cache phản ánh trạng thái database chưa commit/đã rollback |
| **multi-node** | Node A cập nhật nguồn/cache local, node B còn entry cũ | Các node trả dữ liệu khác nhau |

Hai kết quả **put–evict** cần phân biệt: nếu put trước, evict sau, entry có thể bị xóa dù put là cập nhật đúng; nếu evict trước, put cũ sau, entry stale có thể tái xuất hiện. Cả hai có thể hợp lệ về thao tác Cache API nhưng **không đáp ứng mong muốn nghiệp vụ**.

### Khi value là object mutable

Nếu provider lưu tham chiếu object trong bộ nhớ thay vì serialize bản sao, một thread khác có thể sửa **trạng thái bên trong** object mà cache đang trả về. Đây là loại vấn đề khác với stale repopulation: người đọc có thể quan sát trạng thái thay đổi không đồng bộ, thậm chí một object ở trạng thái trung gian.

Nên ưu tiên **DTO/record bất biến** cho giá trị cache, hoặc dùng defensive copy theo yêu cầu. Tuy nhiên, **giá trị bất biến vẫn không khắc phục** tranh chấp ghi lại snapshot cũ; tính bất biến và version ordering là hai lớp bảo vệ khác nhau.

## 8. Giải pháp theo cấp độ nhất quán

Không có một annotation duy nhất chữa mọi race. Chọn biện pháp dựa trên việc cache là “best effort” hay dữ liệu phải có freshness/consistency nghiêm ngặt.

### 8.1. Cấp độ A: chấp nhận stale ngắn hạn, có TTL và quan sát

Đối với dữ liệu tra cứu ít thay đổi, đôi khi một khoảng stale có kiểm soát là hợp lý.

Giải pháp:
- Giữ TTL hữu hạn và phù hợp nghiệp vụ.
- Phân tán thời điểm TTL (jitter, nếu provider hỗ trợ) để giảm stampede.
- Theo dõi cache hit/miss, tuổi entry, lỗi provider, tỉ lệ gọi database, thời gian load.
- Có cơ chế invalidation theo sự kiện thay đổi khi phù hợp.
- Tài liệu hóa rằng **read-after-write consistency không được bảo đảm tuyệt đối**.

**Giới hạn:** TTL làm stale **có thể tự hết**, không loại bỏ cửa sổ race. Nếu dữ liệu liên quan phân quyền, giá cả ràng buộc, số dư hoặc trạng thái bảo mật, việc chấp nhận stale có thể không phù hợp.

### 8.2. Cấp độ B: hạn chế load trùng bằng sync=true

~~~java
@Cacheable(cacheNames = "profiles", key = "#p0", sync = true)
public Profile find(String id) {
    return repository.find(id);
}
~~~

Tác dụng mong đợi: khi nhiều thread đồng thời miss một key và provider hỗ trợ coordinated loader, giảm số lần truy vấn thật.

**Nhưng:** không có bảo đảm tổng quát rằng @CachePut và @CacheEvict tự chờ/khóa cùng cơ chế này. Không lấy sync=true làm bằng chứng rằng không thể có read–write race. Nếu dự án dùng cache nhiều lớp hoặc cache phân tán, kiểm tra semantics của từng provider cụ thể.

### 8.3. Cấp độ C: đồng bộ hóa quy trình theo key

Nếu chạy **một JVM** và cần loại bỏ interleaving trên một key cụ thể, có thể dùng **per-key lock** quanh toàn bộ đường đọc–ghi–xóa, bao gồm **đọc nguồn** và thao tác **ghi/xóa cache** liên quan.

Ý tưởng:

~~~text
lock(key)
  read:
    kiểm tra cache
    nếu MISS -> đọc nguồn -> ghi cache
unlock(key)

lock(key)
  update:
    cập nhật nguồn, xác nhận thành công
    refresh/evict cache theo chính sách
unlock(key)
~~~

Đây là **pseudocode kiến trúc**, không phải mô tả chính xác mọi implementation @Cacheable. Lock phải được các nhánh thao tác thực sự dùng chung; chỉ khóa method update mà không khóa reader loader thì race vẫn có thể xảy ra. Cần kiểm tra đường đi qua proxy để tránh bypass.

Các rủi ro:
- **Lock theo một key** tốt hơn một khóa global khi muốn mở rộng song song cho các key khác nhau.
- Giữ lock quá lâu khi chờ database/network khiến throughput giảm; cần timeout và quan sát contention.
- Cần quản lý vòng đời map các lock để không rò rỉ key vô hạn.
- **synchronized** hoặc ReentrantLock trong JVM **không đồng bộ nhiều instance**; muốn nhất quán liên node cần transaction/lock phân tán hoặc giao thức version thích hợp.

### 8.4. Cấp độ D: optimistic version, CAS và chống ghi đè phiên bản cũ

Một phương pháp mạnh hơn là gắn **version tăng đơn điệu** cho mỗi bản ghi (ví dụ optimistic locking của database). Khi một reader nhận phiên bản 7 trong lúc writer đã commit phiên bản 8, hệ thống có cơ sở để nhận diện reader cũ.

Ví dụ immutable value:

~~~java
public record ProfileSnapshot(
    String id,
    long version,
    String displayName
) {}
~~~

Đây là DTO Java 17 chạy được trong phạm vi khai báo record, nhưng **không tự thực hiện conditional cache write**.

Cách xử lý cần có thêm cơ chế:

~~~text
Reader load ProfileSnapshot(version=7)
Writer commit ProfileSnapshot(version=8)
Writer put/update cache với version=8

Reader định put version=7:
    so sánh version hiện tại hoặc token generation
    nếu 7 < 8 -> từ chối ghi cũ
    nếu hợp lệ -> ghi theo CAS/compute có bảo đảm atomic
~~~

**Quan trọng:** Spring Cache annotation mặc định không cung cấp tùy chọn **@Cacheable(onlyPutIfVersionNewer=true)**. Muốn từ chối ghi cũ, bạn cần triển khai ở **lớp cache provider, custom Cache/CacheManager, gateway/cache access layer, hoặc quy trình nghiệp vụ đồng bộ thích hợp**. Chỉ đọc version rồi gọi put riêng biệt **vẫn có TOCTOU** nếu hai bước không được phối hợp atomically.

Với Redis có thể cân nhắc một script/transaction phù hợp cho kiểm tra version + ghi atomic; với map trong JVM có thể dùng **compute**/CAS trên value wrapper; với hệ thống phân tán phải giải quyết thêm lỗi mạng, key version và cơ chế commit. Đây là các ý tưởng kiến trúc, **không có nghĩa mọi provider tự hỗ trợ nguyên xi**.

### 8.5. Cấp độ E: versioned cache keys

Thay vì cho reader cũ và reader mới tranh cùng một entry, có thể đưa version vào danh tính cache key:

~~~java
// Ví dụ minh họa: caller phải có version đúng, đáng tin cậy.
@Cacheable(cacheNames = "profilesByVersion",
           key = "#p0 + ':' + #p1")
public ProfileSnapshot findAtVersion(String id, long version) {
    return repository.loadVersion(id, version);
}
~~~

Đây là đoạn minh họa không độc lập. Hai version **P:7** và **P:8** khác key, nên loader của phiên bản 7 **không thể ghi đè slot P:8** chỉ vì trả kết quả trễ.

Tuy nhiên:
- Caller phải biết **version hiện hành từ nguồn đáng tin**; nếu vẫn lấy version cũ từ một cache khác thì có thể trả dữ liệu cũ.
- Phương thức đọc phải thực sự trả snapshot tương ứng với version yêu cầu (hoặc xác minh version), không lặng lẽ trả version khác.
- Entry của version cũ vẫn tồn tại cho đến khi TTL/eviction; cần cân nhắc dung lượng.
- Nếu dữ liệu nghiệp vụ không có lịch sử version, cần chiến lược mapping hiện hành và xử lý stale version riêng.

Versioned key giảm **ghi đè chéo giữa thế hệ entry**, không tự cung cấp read-after-write linearizability cho cả hệ thống.

### 8.6. Cấp độ F: invalidate sau commit và phát sự kiện nhất quán

Trong hệ thống có database transaction, bạn không nên coi việc method trả về là bằng chứng rằng transaction **đã commit**. Một hướng phổ biến:

~~~text
Transaction cập nhật source
  -> commit thành công
  -> phát tín hiệu invalidation / outbox event
  -> consumer xóa hoặc cập nhật cache
~~~

Các chiến lược tham khảo:
- **Transaction-aware CacheManager/decorator**: có thể hoãn put/evict/clear đến **after-commit** khi có transaction Spring active; không tự làm dữ liệu cache nguyên tử với database và không ngăn reader đã bắt đầu trước đó.
- **@TransactionalEventListener(phase = AFTER_COMMIT)**: thực hiện logic thích hợp sau commit trong cùng ứng dụng, song phải xét điều kiện phát event và đặc tính chạy.
- **Transactional outbox + message consumer**: ghi event cùng transaction nguồn, sau đó phân phối đến nhiều node/consumer; phù hợp đồng bộ bất đồng bộ nhưng có độ trễ và cần idempotency/ordering.
- **Write-through cache gateway** hoặc provider có compare-and-set: có thể giúp phối hợp cập nhật cache và nguồn trong ranh giới đã định.

Trong các giải pháp bất đồng bộ, hãy xét **out-of-order events**: invalidation phiên bản 7 đến sau update phiên bản 8 không được tùy tiện khôi phục giá trị cũ. Idempotency, generation token và phiên bản là công cụ quan trọng.

**Transaction-aware không đồng nghĩa với cache/database atomic transaction.** Nếu thao tác cache sau commit thất bại, database đã commit nhưng cache chưa được cập nhật. Hệ thống cần retry, TTL, reconciliation hoặc phương án an toàn khi thiếu cache.

## 9. Hiểu đúng semantics của Cache API và provider

Spring có abstraction **Cache**, nhưng từng provider có đặc trưng khác nhau:

| API / cấu hình | Ý nghĩa tổng quát | Điều cần xác minh |
| --- | --- | --- |
| **Cache.get(key)** | Lấy entry hiện có | Null, ValueWrapper, cache miss, provider/network error |
| **Cache.put(key,value)** | Gắn value với key | Đồng bộ hay bất đồng bộ, serialize, tính nhất quán giữa node |
| **Cache.evict(key)** | Yêu cầu xóa key | Có thể deferred/async trong một số provider/decorator |
| **Cache.evictIfPresent(key)** | API kỳ vọng entry không còn hiển thị ngay sau khi xử lý | Hỗ trợ provider, tính tức thời; **không ngăn future put** |
| **Cache.clear()** | Yêu cầu xóa toàn bộ | Có thể deferred; reader in-flight có thể tái điền |
| **Cache.invalidate()** | API kỳ vọng các entry không còn hiển thị ngay | Không bảo đảm chặn entry mới xuất hiện sau đó |
| **Cache.putIfAbsent(key,value)** | Thử ghi chỉ khi chưa có value | Mức atomicity thực tế tùy implementation |
| **Cache.get(key, Callable)** | Tìm hoặc load theo callback | Provider có hỗ trợ phối hợp loader không |
| **@Cacheable(sync=true)** | Gợi ý đồng bộ hóa việc tải cùng key | Không thay thế cơ chế nhất quán giữa read/write/evict |

Các API **evictIfPresent/invalidate** nói về **khả năng nhìn thấy lệnh xóa**, không phải “đợi tất cả các loader đang chạy hoàn tất và cấm put tương lai”. Do đó, ngay cả eviction có hiệu lực tức thì cũng không ngăn race read–evict trong mục 5.

### Cache local và cache phân tán

- **ConcurrentMapCacheManager:** thao tác dữ liệu trong JVM, rất thuận tiện để unit/integration test; không trao đổi thay đổi với các JVM khác.
- **Caffeine:** thường dùng cache cục bộ hiệu năng cao, có loader và chính sách eviction riêng; xác minh loader concurrency và invalidation theo API đang dùng.
- **Redis-backed CacheManager:** dữ liệu ở nơi lưu chung nhưng có round-trip mạng, serialization và có thể có nhiều thao tác riêng biệt. Một lệnh Redis đơn lẻ atomic theo cơ chế Redis không biến chuỗi database read → Redis put thành transaction nguyên tử xuyên hai hệ thống.
- **Near-cache/L1+L2:** có thêm bài toán invalidation liên tầng và giữa node; cần xác minh thứ tự propagation.

Điều nguy hiểm là lấy kết quả test chạy với ConcurrentMapCacheManager rồi **tuyên bố hệ thống Redis nhiều node cũng có cùng thứ tự visibility**. Chúng có thể hoàn toàn khác.

## 10. Đọc–ghi–xóa trong transaction: cửa sổ nào còn mở?

Ví dụ update có @Transactional và @CacheEvict:

~~~java
// Ví dụ minh họa, cần service, repository, transaction manager và cache manager.
@Transactional
@CacheEvict(cacheNames = "profiles", key = "#p0")
public void updateProfile(String id, ProfileInput input) {
    repository.update(id, input);
}
~~~

Hãy phân biệt ba mốc:
1. **Method trả về** từ lời gọi Java.
2. **Transaction commit thành công**.
3. **Cache eviction/put thực sự có hiệu lực và được node khác nhìn thấy**.

Thứ tự giữa các mốc phụ thuộc **advice ordering** và transaction-aware integration. Nếu eviction chạy trước commit, một thread khác có thể miss cache nhưng chưa nhìn thấy dữ liệu mới (vì isolation), rồi nạp lại dữ liệu cũ. Nếu evict bị defer đến after-commit, loại bỏ được một số cửa sổ sai, **nhưng loader cũ đang chạy vẫn có thể put sau**.

### Đặt kỳ vọng nhất quán rõ ràng

| Yêu cầu nghiệp vụ | Có thể cân nhắc |
| --- | --- |
| Dữ liệu tham khảo, stale vài giây chấp nhận | Cache-aside + TTL + metrics + invalidation có retry |
| Nhiều request cùng đọc key nóng | sync=true / single-flight theo provider để giảm load |
| Writer và reader cần tuần tự trong một instance | Per-key lock bao cả critical section |
| Nhiều instance, phải tránh stale overwrite | Version/CAS hoặc cơ chế phối hợp phân tán |
| Cần không phát dữ liệu chưa commit | Invalidation/write phối hợp sau commit, kiểm chứng isolation |
| Dữ liệu nhạy cảm, không chấp nhận stale | Thiết kế đọc có xác thực/kiểm tra version với authoritative source; có thể bỏ cache khỏi đường quyết định |

Không có một cấu hình @CacheEvict(beforeInvocation=...) nào thay thế việc phân tích **thứ tự commit**, reader in-flight và yêu cầu nhất quán.

## 11. Những phương án dễ mắc bẫy

### “Cứ bật @Cacheable(sync=true) là xong”

Không. Cờ này đặc biệt hữu ích với **read–read duplicate load**, nhưng không phải mutex toàn cục cho update/evict. Test cả read–put và read–evict trước khi xem là đủ.

### “Evict trước khi ghi database để tránh stale”

Đôi khi còn nguy hiểm hơn: reader miss ngay sau evict có thể nhìn dữ liệu cũ chưa update, rồi put kết quả cũ. Với afterInvocation cũng có race in-flight; cần thiết kế hơn là đổi một boolean.

### “Database có optimistic lock nên cache không thể stale”

Optimistic locking bảo vệ thứ tự cập nhật **database** theo version, không mặc nhiên ràng buộc thứ tự **cache.put** của các reader/writer. Cần dùng version tại cache boundary hoặc khóa phối hợp.

### “ConcurrentHashMap đảm bảo cache luôn đúng”

ConcurrentHashMap bảo vệ thao tác map; không biết kết quả v1/v2 từ snapshot database nào. **Atomic map operation ≠ atomic business workflow**.

### “Tăng TTL sẽ tự hết lỗi”

TTL dài có thể khiến stale tồn tại lâu hơn; TTL ngắn làm DB chịu tải và tăng stampede. TTL là một chính sách hết hạn, **không giải quyết thứ tự put**.

### “Chỉ cần đặt @CacheEvict lên phương thức private trong cùng class”

Trong Spring AOP proxy mode, annotation cần được thực thi qua proxy; self-invocation/private method không tự được cache interceptor xử lý. Cần xác nhận bean và đường gọi trước khi debug concurrency.

### “Xóa cả cache với allEntries=true thì chắc chắn không ai có thể trả dữ liệu cũ”

~~~java
@CacheEvict(cacheNames = "profiles", allEntries = true)
public void resetAllProfiles() {
    repository.refreshAll();
}
~~~

Đây là đoạn minh họa. allEntries yêu cầu xóa toàn cache, không làm tất cả các loader đang chạy tự ngừng và không bảo đảm không có entry cũ được put sau khi clear. Ngoài ra, clear rộng có thể gây thundering herd và tạo tải lớn.

### “Dùng @CachePut cho mọi update là tự động nhất quán”

@CachePut luôn gọi method và put kết quả theo operation. Nó không tự có version compare, không kiểm soát reader cũ, và cần **cùng cacheNames, CacheManager và key logic** với phương thức @Cacheable. Nếu @CachePut và @CacheEvict tính key khác nhau, một entry cũ có thể tồn tại vô hạn cho đến TTL.

## 12. Checklist triển khai và kiểm thử

Trước khi chấp nhận một thiết kế cache có read/write/evict song song, xác nhận:

1. **Định danh nhất quán:** Mọi operation liên quan dùng cùng cache name, cache manager/resolver và quy tắc key (tenant, locale, version nếu cần).
2. **Đường gọi đúng:** Những method gắn caching annotation được gọi qua bean proxy do Spring quản lý.
3. **Nguồn dữ liệu thực:** Biết thời điểm bản ghi được đọc và commit; không đồng nhất “method đã trả về” với “database đã commit”.
4. **Read–read:** Nhiều thread cùng miss có thể load trùng không? sync=true/provider loader có đủ theo yêu cầu tải không?
5. **Read–put:** Reader lấy snapshot trước update nhưng trả về sau @CachePut sẽ thế nào?
6. **Read–evict:** Reader lấy snapshot trước eviction nhưng trả về sau eviction có tái điền entry cũ không?
7. **Put–put:** Hai phiên bản cập nhật đồng thời có thể ghi cache đảo thứ tự không? Có version/CAS/serialization strategy?
8. **Put–evict:** Một request put và request khác evict cùng key có thể tạo miss hoặc stale nào?
9. **Rollback:** Có cache update/evict trước commit? Nếu transaction rollback, cache còn đúng không?
10. **Provider:** Có đảm bảo atomic callback, hỗ trợ sync, eviction immediate và visibility giữa node? Có serialization hoặc async delay?
11. **Race test:** Dùng latch/barrier, kiểm tra **source + cache + result**, bounded timeout, test trên provider thật.
12. **Quan sát:** Có metrics cho hit/miss, stale read, invalidation delay, version mismatch và retry không?
13. **Chiến lược sửa:** Nếu freshness quan trọng, có giao thức version/lock hoặc authoritative read path, không chỉ TTL?
14. **Phục hồi:** Khi ghi/evict cache lỗi sau commit, hệ thống có thể retry, reconcile hoặc để TTL phục hồi không?
15. **Bảo mật:** Đối với thông tin phân quyền/quyền truy cập, stale có thể gây sai chính sách; đánh giá nghiêm ngặt thay vì coi cache chỉ là tối ưu hiệu năng.

### Bài tập gợi ý

**Bài 1 — tái hiện race:** Chạy ví dụ ở mục 6 và giải thích vì sao RACE_EVICT vẫn có cache=v3 sau khi method writer đã gọi @CacheEvict.

**Bài 2 — thử sync:** Đổi annotation read sang @Cacheable(sync=true), chạy lại test. Không giả định kết quả chỉ từ tên sync: kiểm tra semantics thực tế của provider và điều kiện đưa entry trở lại sau update/evict. Lưu ý sync=true không hỗ trợ unless và không nên kết hợp thêm cache operation trên cùng method.

**Bài 3 — thiết kế version:** Thêm version vào source (v1→v2 tương ứng version 1→2). Mô tả cách một cache layer có compare-and-set/compute **nguyên tử** từ chối put snapshot version=1 khi entry đã là version=2.

**Bài 4 — nhiều node:** Giả sử node A và B dùng cache local khác nhau; A cập nhật database rồi evict trên A. B sẽ biết để xóa entry cũ bằng cách nào? Đề xuất sự kiện invalidation, versioned key, TTL hoặc không cache dữ liệu cần nhất quán mạnh.

**Bài 5 — after-commit:** Mô tả trường hợp writer rollback mà cache đã put value mới. Xác định transaction-aware cache hoặc after-commit event có thể giúp điều gì và **không** giải quyết race nào.

## 13. Câu hỏi tự kiểm tra

**1.** @Cacheable và @CachePut dùng cùng key "P". Reader đã bắt đầu load v1; writer hoàn tất put v2; reader sau đó put v1. Cache cuối có thể là gì?

**Đáp:** **v1**. Thread-safe put không kiểm tra phiên bản của value; kết quả cũ có thể ghi đè kết quả mới.

**2.** @CacheEvict chạy thành công có loại bỏ hoàn toàn khả năng entry cũ quay lại không?

**Không.** Một @Cacheable đang load snapshot cũ có thể hoàn tất và put lại key **sau khi** evict chạy.

**3.** @Cacheable(sync=true) loại bỏ loại tranh chấp nào chủ yếu?

**Đáp:** Giúp phối hợp **nhiều lượt tải cùng key** khi concurrent cache miss, trong phạm vi provider hỗ trợ. Không phải giải pháp tổng quát cho tranh chấp với @CachePut/@CacheEvict hoặc transaction.

**4.** @CacheEvict(beforeInvocation=true) có bắt buộc tạo kết quả mới nhất không?

**Không.** Eviction xảy ra trước method, nên reader khác có thể miss và tải dữ liệu cũ trong cửa sổ update chưa hoàn tất.

**5.** Vì sao TTL không chứng minh hệ thống không stale?

TTL chỉ định thời gian entry có thể tồn tại hoặc hết hạn; nó không đảm bảo thứ tự đọc dữ liệu, commit và cache put giữa nhiều thread.

**6.** Nếu tất cả các thao tác cache đều thread-safe, tại sao vẫn xảy ra read–put race?

Vì chuỗi **cache miss → đọc database → cache put** không được thực hiện như một transaction nguyên tử với chuỗi **cập nhật database → cache put**.

**7.** Có phải Spring Cache có tùy chọn sẵn để từ chối ghi khi result.version nhỏ hơn current.version?

Không có cơ chế chung kiểu annotation **onlyPutIfVersionNewer**. Cần triển khai ở lớp phối hợp/cache provider hoặc kiến trúc version/CAS phù hợp.

**8.** Cần kiểm tra những giá trị nào trong integration test race?

Ít nhất gồm **nguồn dữ liệu hiện tại**, **cache entry hiện tại**, **kết quả từng caller**, **số lần loader chạy** và **thứ tự commit/evict/put** đã được dàn dựng.

## Kết luận

**Spring Cache cung cấp annotation để đọc, ghi và xóa cache; nó không mặc định tuần tự hóa mọi workflow nghiệp vụ giữa các thread.** Các cuộc đua read–read có thể gây load trùng, còn read–put và read–evict có thể làm **snapshot cũ đè hoặc hồi sinh sau update/eviction**. Bật @Cacheable(sync=true) có ích với concurrent cold loads nhưng không tạo consistency contract cho writer. Giải pháp thật sự tùy yêu cầu: **TTL nếu chấp nhận stale**, **per-key lock nếu cần thứ tự trong một process**, **version/CAS/đồng bộ phân tán nếu cần chống ghi đè cũ**, và **after-commit invalidation/retry** nếu có transaction và nhiều node.

### Tài liệu chính thức

- Spring Framework 6.2 – Annotation-based caching, synchronized caching, @CachePut và @CacheEvict: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework 6.2 – @Cacheable.sync Javadoc và các giới hạn của sync=true: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework – Cache interface: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework – TransactionAwareCacheDecorator (deferred operations after commit): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
- Spring Framework – @CacheEvict API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
