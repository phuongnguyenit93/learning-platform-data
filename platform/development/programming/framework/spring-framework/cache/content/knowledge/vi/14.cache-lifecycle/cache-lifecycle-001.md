# Spring Cache: lưu theo tham chiếu và lưu bản sao giá trị

## 1. Tại sao cùng một cache key vẫn có thể cho ra các hành vi khác nhau?

Trong Spring Framework, `@Cacheable` có thể tránh thực thi lại phương thức bằng cách trả về giá trị đã lưu theo key. Nhưng việc cache **giữ cùng một object Java hay tạo bản sao của object** không do annotation quyết định; nó phụ thuộc vào cache provider và cấu hình lưu trữ.

Giả sử method trả object `Book` có thuộc tính `title` thay đổi được. Caller lấy `Book("Original")` từ cache rồi gọi `setTitle("Edited")`. Một caller khác truy cập cùng key có thấy `Edited` hay không? Đó là sự khác biệt giữa hai mô hình:

- **Store-by-reference (lưu theo tham chiếu):** cache giữ tham chiếu đến chính instance Java. Với cache nội bộ trong cùng JVM, bên nạp và bên đọc có thể cùng giữ tham chiếu đến object đó. Thay đổi object có thể làm entry cache thay đổi mà không hề có thao tác `Cache.put` mới.
- **Store-by-value (lưu bản sao giá trị):** cache lưu một bản sao/snapshot và trả giá trị được sao chép theo contract của backend. Một caller sửa object vừa được trả không làm thay đổi bản snapshot bên trong cache. Với `ConcurrentMapCacheManager` của Spring, chế độ này được thực hiện thông qua Java serialization.

Luồng minh họa:

~~~text
STORE-BY-REFERENCE:
Caller A ------+
               v
          [Book instance X, title="Original"] <---- Cache["b1"]
               ^
Caller B ------+
Caller A sửa X.title="Edited"
=> Caller B đọc cùng object X và thấy "Edited"


STORE-BY-VALUE:
Book X ("Original") -- copy khi put --> Cache snapshot ("Original")
                                         |
                                      copy khi get
                                         v
                                    Book Y ("Original")
                                    Caller sửa Y
=> Snapshot trong cache vẫn là "Original"
~~~

**Hai lưu ý quan trọng:** Cache hit không bắt buộc trả về **cùng identity object**; và việc có snapshot không đồng nghĩa snapshot ấy đã cập nhật theo database. Cả hai mô hình vẫn cần quản lý cache invalidation và vòng đời dữ liệu.

## 2. So sánh cơ chế lưu trữ

| Tiêu chí | Theo tham chiếu | Theo bản sao giá trị |
| --- | --- | --- |
| Giá trị lưu | Reference tới instance trong JVM. | Bản sao/biểu diễn của value. |
| Đọc cùng key | Với in-memory reference cache, có thể trả đúng instance đã lưu. | Có thể tái tạo một instance mới từ snapshot. |
| Caller sửa object nhận được | Có thể vô tình sửa luôn object trong cache. | Không trực tiếp sửa snapshot đã lưu. |
| Caller sửa object sau khi `put` | Có thể thấy thay đổi ở lần `get`. | Snapshot đã sao chép khi lưu không đổi theo object gốc. |
| Chi phí | Ít copy, thấp CPU/GC, phù hợp dữ liệu bất biến. | Copy/serialization tăng CPU, memory, cấp phát và latency. |
| Hạn chế | Mutable aliasing, race condition, biến đổi ngầm. | Lỗi serialization, object graph phức tạp, snapshot vẫn stale. |
| Dữ liệu ở backend | Thường dùng với local in-process cache. | Có thể là copy local hoặc dữ liệu serialized trong remote cache. |

Spring Cache chỉ định nghĩa **abstraction**. Cách lưu của `ConcurrentMapCache` không tự áp dụng cho Caffeine, Redis hay mọi JCache provider. Khi đổi backend, cần kiểm tra semantics cụ thể thay vì giả định hai lần `get` luôn cho ra cùng instance hoặc luôn cho bản sao.

### 2.1. Shared reference và aliasing

Aliasing nghĩa là nhiều biến giữ cùng một tham chiếu. Ví dụ giả định `cache` là `org.springframework.cache.Cache` dùng chế độ tham chiếu, `Book` là class mutable:

~~~java
Book book = new Book("Original");
cache.put("b1", book);
Book cachedBook = cache.get("b1", Book.class);

System.out.println(book == cachedBook); // true với cache local theo reference
cachedBook.setTitle("Edited");
System.out.println(book.getTitle());    // Edited
~~~

Đây **chỉ là trích đoạn**; chưa phải chương trình Java độc lập. Khi `cache.put` không sao chép value, cả người ghi lẫn người đọc giữ cùng instance. Vì vậy không chỉ caller sửa sau `get` gây thay đổi; người ghi sửa object gốc **sau khi `put`** cũng có thể tác động tới cache mà không chủ động cập nhật cache.

Nếu database vẫn lưu `Original` nhưng reference cache đã hiển thị `Edited`, đây là sự thay đổi **không được đồng bộ với nguồn dữ liệu**. Hiện tượng ấy có thể khiến lỗi khó tái hiện hoặc khiến hệ thống trả dữ liệu không nhất quán.

### 2.2. Snapshot và copy-on-write/copy-on-read

Một backend store-by-value đúng nghĩa có thể tạo bản sao ở ranh giới lưu và ranh giới trả về:

~~~text
T0: object nguồn có title="Original"
T1: cache.put(key, object) -> lưu snapshot="Original"
T2: object nguồn đổi thành "Edited"
T3: cache.get(key) -> trả bản sao="Original"
T4: caller sửa bản sao thành "Other"
T5: cache.get(key) -> bản sao mới vẫn="Original"
~~~

Copy giúp **cách ly thay đổi trên object**, chứ không theo dõi biến đổi ở database. Nếu nguồn dữ liệu được cập nhật hợp lệ thì snapshot cũ vẫn cần được xóa, thay thế hoặc hết hạn để lần đọc sau lấy dữ liệu mới.

### 2.3. Trường hợp đặc biệt: lượt `@Cacheable` bị miss

Trong luồng đồng bộ của Spring Cache, lượt miss thực thi method rồi lưu giá trị và trả kết quả mới tạo. Với `ConcurrentMapCache` ở chế độ copy, việc lưu đã tạo snapshot, nhưng object được trả **ở lượt miss** thường vẫn là object gốc vừa được method trả ra, không bắt buộc là bản deserialized.

Điều này không làm mất tính cách ly: sửa object được caller giữ **sau lượt miss** không sửa snapshot đã lưu qua serialization. Lượt hit tiếp theo nhận bản sao khác. Ví dụ phần 4 cho thấy `value1 == value2` là `false`, dù hai lượt gọi có cùng key.

## 3. Cấu hình `ConcurrentMapCacheManager` của Spring

`ConcurrentMapCacheManager` là cache manager in-process sử dụng cơ chế map đồng thời của Java. Nó phù hợp demo hoặc ứng dụng đơn giản, **không mặc định cung cấp TTL, persistence hoặc đồng bộ dữ liệu giữa các JVM**.

Theo Javadoc Spring Framework 6.x:

- `setStoreByValue(false)`: lưu theo reference; **mặc định** là `false`.
- `setStoreByValue(true)`: lưu các bản sao, dùng serialization cho cache entries.
- `isStoreByValue()`: kiểm tra chế độ đang cấu hình.
- Khi bật store-by-value, value phải **serializable**.
- Đổi thiết lập store-by-value sau khi cache đã được tạo có thể **reset các cache hiện hữu**, nên đặt lúc khởi tạo và không bật/tắt tùy tiện khi hệ thống đang chạy.

Ví dụ cấu hình Spring:

~~~java
@Bean
ConcurrentMapCacheManager cacheManager() {
    ConcurrentMapCacheManager manager =
            new ConcurrentMapCacheManager("books");
    manager.setStoreByValue(true);
    return manager;
}
~~~

Đoạn này giả định đang nằm trong class `@Configuration` và có import `@Bean` cùng `ConcurrentMapCacheManager`. Nó bật chế độ copy cho các cache của manager; đây **không phải thuộc tính của `@Cacheable`**. Không có một flag `@Cacheable(storeByValue=true)` dùng chung cho mọi provider.

### 3.1. Serialization có yêu cầu gì?

Đối với chế độ copy của `ConcurrentMapCacheManager`, class value thường cần `implements java.io.Serializable`. Không chỉ outer object: những object liên quan trong graph cũng cần serialize được, hoặc được xử lý bằng `transient`/serialization tùy chỉnh.

Các vấn đề có thể gặp:

1. Một field giữ đối tượng không `Serializable` khiến ghi cache thất bại.
2. Field `transient` không được serialize, nên object được khôi phục có thể thiếu dữ liệu kỳ vọng.
3. Một object giữ socket, thread, file handle, DB connection hoặc lazy-loading proxy thường không phải giá trị cache phù hợp.
4. Graph quá lớn làm việc serialize/deserialize tốn thời gian và bộ nhớ.
5. Nếu backend lưu serialized data qua nhiều phiên bản triển khai, đổi schema/class có thể gây lỗi tương thích; cần quy tắc versioning riêng.

`Serializable` **không làm object bất biến**. Nó chỉ cho phép provider sao chép/biểu diễn trạng thái theo cơ chế tương ứng.

## 4. Ví dụ Java 17+ và Spring Boot 3: cùng key nhưng khác chế độ

Ứng dụng dưới đây tạo **hai manager** riêng biệt:

- `referenceCacheManager` quản lý vùng `byReference`, `storeByValue=false`.
- `copyCacheManager` quản lý vùng `byValue`, `storeByValue=true`.

Cả hai method nhận ID `"b1"`, tạo object `MutableBook("Original")` nếu bị miss. Sau đó chương trình sửa instance đã nhận và gọi lại. `MutableBook` implements `Serializable` để cache copy có thể dùng Java serialization.

**Tệp `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

**Tệp `src/main/java/demo/StoreSemanticsApplication.java`:**

~~~java
package demo;

import java.io.Serial;
import java.io.Serializable;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@SpringBootApplication
@EnableCaching
public class StoreSemanticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(StoreSemanticsApplication.class, args);
    }

    @Bean("referenceCacheManager")
    @Primary
    CacheManager referenceCacheManager() {
        ConcurrentMapCacheManager manager =
                new ConcurrentMapCacheManager("byReference");
        manager.setStoreByValue(false);
        return manager;
    }

    @Bean("copyCacheManager")
    CacheManager copyCacheManager() {
        ConcurrentMapCacheManager manager =
                new ConcurrentMapCacheManager("byValue");
        manager.setStoreByValue(true);
        return manager;
    }

    @Bean
    BookService bookService() {
        return new BookService();
    }

    @Bean
    CommandLineRunner demo(BookService service) {
        return args -> {
            MutableBook ref1 = service.loadReference("b1");
            System.out.println("ref first = " + ref1.title());

            ref1.rename("Edited by caller");
            MutableBook ref2 = service.loadReference("b1");
            System.out.println("ref same instance = " + (ref1 == ref2));
            System.out.println("ref second = " + ref2.title());

            MutableBook value1 = service.loadValue("b1");
            System.out.println("value first = " + value1.title());

            value1.rename("Edited by caller");
            MutableBook value2 = service.loadValue("b1");
            System.out.println("value same instance = "
                    + (value1 == value2));
            System.out.println("value second = " + value2.title());

            value2.rename("Edited after hit");
            MutableBook value3 = service.loadValue("b1");
            System.out.println("value third = " + value3.title());
        };
    }

    public static class BookService {
        @Cacheable(
                cacheNames = "byReference",
                cacheManager = "referenceCacheManager",
                key = "#p0")
        public MutableBook loadReference(String id) {
            System.out.println("LOAD reference " + id);
            return new MutableBook("Original");
        }

        @Cacheable(
                cacheNames = "byValue",
                cacheManager = "copyCacheManager",
                key = "#p0")
        public MutableBook loadValue(String id) {
            System.out.println("LOAD value " + id);
            return new MutableBook("Original");
        }
    }

    public static final class MutableBook implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private String title;

        public MutableBook(String title) {
            this.title = title;
        }

        public String title() {
            return title;
        }

        public void rename(String newTitle) {
            this.title = newTitle;
        }
    }
}
~~~

**Cách chạy:** dùng `./gradlew bootRun` nếu dự án có Gradle Wrapper (Windows: `gradlew.bat bootRun`) hoặc `gradle bootRun` nếu đã cài Gradle tương thích. Cần có JDK 17+ và tải dependencies trong lần chạy đầu. Version Gradle/Spring Boot ở đây mang tính minh họa; dự án production nên chọn bản được hỗ trợ và cập nhật bảo mật.

Bỏ qua banner/log khởi động của Spring Boot. **Những dòng demo chủ động in ra** theo thứ tự:

~~~text
LOAD reference b1
ref first = Original
ref same instance = true
ref second = Edited by caller
LOAD value b1
value first = Original
value same instance = false
value second = Original
value third = Original
~~~

**Giải thích theo dòng:**

1. Lần đầu `loadReference("b1")` miss, tạo `MutableBook("Original")` và lưu cùng instance trong cache `byReference`.
2. `ref1.rename(...)` làm instance đang được cache đổi title. Lần thứ hai hit, `ref1 == ref2` là `true` và title hiển thị `Edited by caller`. Không có `LOAD reference b1` thêm.
3. Lần đầu `loadValue("b1")` miss, tạo object `Original`; manager copy lưu snapshot có thể serialize.
4. Caller sửa `value1` sau miss. Snapshot vẫn là `Original`. Lần hit thứ hai deserialize thành object khác: `value1 == value2` là `false`.
5. Caller sửa `value2` sau hit rồi gọi lại. `value3` lại nhận title `Original` do cache vẫn giữ snapshot; không có `LOAD value b1` lần thứ hai.

Hai tên cache khác nhau là có chủ đích: cùng key `"b1"` không đồng nghĩa hai vùng cache chia sẻ entry. Phương thức `@Cacheable` chỉ rõ `cacheManager` bằng tên bean; `@Primary` dành cho manager mặc định khi Spring cần giải quyết nhiều candidate. `CommandLineRunner` gọi qua `BookService` được Spring quản lý, để cache interceptor hoạt động; gọi nội bộ bằng `this.loadValue(...)` trong chính service sẽ bypass proxy ở chế độ proxy thông thường.

So sánh `==` ở ví dụ này chỉ minh họa **identity trong implementation `ConcurrentMapCache`**. Không được lấy `==` làm kiểm tra tổng quát cho mọi cache provider: immutable object có thể được tái sử dụng, serializer và cơ chế copy có thể khác nhau.

## 5. “Bản sao” khác “đổi biến” hoặc shallow copy như thế nào?

| Thao tác | Có tách object không? |
| --- | --- |
| `Book b = a;` | Không, chỉ sao chép reference. |
| Tạo shallow copy có cùng danh sách mutable bên trong | Object ngoài khác, nhưng nested list vẫn có thể chia sẻ. |
| Copy bằng serialization phù hợp | Có thể tái tạo object graph có thể tuần tự hóa dưới dạng object mới. |
| Immutable DTO | Không cần copy để ngăn caller sửa trạng thái nếu toàn bộ trạng thái có thể quan sát đều bất biến. |

Một object `Book` có field `List<Chapter>`: nếu chỉ clone lớp ngoài mà vẫn giữ cùng `List` hoặc các `Chapter` mutable, việc sửa nested object có thể tác động tới bản gốc. Cách xử lý phải xem xét **cả object graph**, không chỉ reference ở tầng cao nhất.

Với Java 17+, DTO bất biến có thể là:

~~~java
public record BookView(String id, String title)
        implements java.io.Serializable {
}
~~~

Đây là **đoạn Java độc lập về cú pháp**, cần đặt thành `BookView.java` nếu dùng ở cấp top-level. Khi chỉ gồm các `String` bất biến, việc dùng chung instance thường ít rủi ro. Với record chứa collection hoặc thành phần mutable, record chỉ bất biến **nông**; nên defensive-copy các collection (ví dụ `List.copyOf`) và dùng phần tử immutable.

Một lựa chọn khác là DTO dạng class final có các field final, không có setter, và validate khi tạo. “Immutable by design” thường rõ hơn việc yêu cầu mọi consumer nhớ không sửa object từ cache.

## 6. Hiệu năng, đa luồng và vòng đời dữ liệu

### 6.1. Thread-safe map không đồng nghĩa thread-safe value

`ConcurrentMapCache` dựa trên cấu trúc map đồng thời. Các thao tác đưa/lấy entry được đồng bộ theo cơ chế của map, nhưng **object mutable đang nằm trong value không tự được bảo vệ khỏi race condition**.

Ví dụ một thread đọc hai trường `price` và `currency` trong object chung, thread khác sửa chúng ở hai bước. Thread đọc có thể thấy giá trị không cùng phiên bản nếu không có đồng bộ hoặc immutable snapshot. Không nên dùng store-by-reference cho object mutable chia sẻ rộng rãi mà không có contract thread-safety.

Store-by-value giúp mỗi caller giữ bản sao, giảm khả năng caller này sửa object gây ảnh hưởng ngay cho caller khác. Tuy nhiên, việc snapshot được serialize trong lúc một thread khác **đang sửa object nguồn** cũng không tự bảo đảm nhất quán: phải có cơ chế xây dựng snapshot từ trạng thái ổn định.

### 6.2. Chi phí copy

Store-by-reference tiết kiệm CPU và cấp phát vì không serialize mỗi lần cache get/put. Store-by-value có thể tăng CPU, memory, pressure lên GC, độ trễ và kích thước dữ liệu serialized. Nếu object graph lớn hoặc tần suất hit cao, chi phí này có thể xóa bớt lợi ích performance của caching. Hãy benchmark với dữ liệu thực, theo dõi hit rate, latency, throughput và GC.

Chọn **immutable DTO + local reference cache** thường là phương án tốt khi hiệu năng là ưu tiên, nhưng vẫn phải quản lý TTL và invalidation đúng.

### 6.3. Copy không có nghĩa dữ liệu luôn mới

~~~text
T0: Database title="Original"; cache snapshot="Original"
T1: Database được cập nhật thành "Updated"
T2: Cache hit -> vẫn trả "Original" nếu chưa có invalidation
T3: @CacheEvict đúng key hoặc @CachePut lưu giá trị mới
T4: Đọc lại -> "Updated" theo logic caching
~~~

Store-by-value bảo vệ snapshot trước việc sửa object ở phía caller, nhưng snapshot vẫn có thể **stale** so với nguồn dữ liệu. Store-by-reference cũng không tự xử lý việc database thay đổi từ nơi khác; đôi khi nó làm cache trông có vẻ mới chỉ vì ai đó sửa shared object, dù database chưa commit.

Các chính sách về `@CacheEvict`, `@CachePut`, TTL, đồng bộ nhiều instance và thời điểm transaction commit phải được thiết kế độc lập với ngữ nghĩa store-by-value. Local `ConcurrentMapCacheManager` không chia sẻ entry giữa các JVM.

### 6.4. Mutable key là vấn đề riêng

Nếu dùng object mutable làm cache key, việc sửa thuộc tính tham gia `equals` hoặc `hashCode` sau khi đưa vào hash map có thể khiến tra cứu sai hoặc không tìm lại được entry. Sao chép **value** không tự sửa được key mutable. Ưu tiên ID ổn định như `String`, `UUID` hoặc immutable key record có hash/equals nhất quán.

## 7. Không được suy rộng tùy tiện sang cache provider khác

| Provider / mô hình | Điều cần kiểm chứng |
| --- | --- |
| Spring `ConcurrentMapCacheManager` | Mặc định store-by-reference; bật copy bằng `setStoreByValue(true)` và yêu cầu serializable. |
| Caffeine local thông dụng | Thường giữ cùng object trong JVM; không giả định mỗi lần `get` tự deep copy. |
| Redis/remote serialized cache | Dữ liệu thường đi qua serializer khi truyền mạng; object Java ở hai tiến trình không thể chia sẻ reference local trực tiếp. |
| JCache (JSR-107) / backend khác | Xem cấu hình `storeByValue`, implementation, serializer và contract tương ứng. |

Remote serialization thường khiến hai lần đọc tái tạo hai instance Java khác nhau, nhưng **không chứng minh dữ liệu đang mới**. Nếu Redis chứa snapshot cũ, deserialize bao nhiêu lần vẫn trả giá trị cũ. Khi chuyển provider, cần kiểm thử serialization, schema compatibility, TTL, eviction và behavior khi backend mất kết nối.

## 8. Các lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Caller sửa object từ cache, người khác thấy thay đổi không có ghi database. | Shared reference tới value mutable. | Immutable DTO, defensive copy hoặc store-by-value. |
| Bật store-by-value làm thao tác cache lỗi. | Value/nested field không serialize được. | Cache DTO serializable phù hợp, kiểm tra graph và trường transient. |
| Caller sửa object sau cache hit nhưng lần sau không thấy cập nhật. | Chỉ sửa bản sao, không ghi nguồn/cập nhật cache. | Cập nhật nguồn chính thức, kết hợp `@CachePut` hoặc `@CacheEvict`. |
| Đọc cache vẫn thấy dữ liệu cũ dù đã bật copy. | Snapshot không tự theo database. | TTL, eviction hoặc update đúng key, tính đến transaction. |
| Cache local an toàn với đa thread nhưng value bị ghi đè/trộn trạng thái. | Map thread-safe nhưng object mutable không thread-safe. | Immutable snapshot, đồng bộ hoặc phân quyền sở hữu. |
| `setStoreByValue` thay đổi khi đang chạy làm entries biến mất. | Manager reset cache để thay đổi chế độ. | Cấu hình khi khởi động; xử lý thay đổi có kế hoạch. |
| Key đang sử dụng bỗng không tìm thấy. | Key mutable làm thay đổi `hashCode/equals`. | Key bất biến, định danh rõ ràng. |
| Cache remote trả object mới mỗi lần nhưng giá vẫn sai. | Deserialization tái tạo object từ snapshot cũ. | Kiểm tra dữ liệu gốc và invalidation. |

## 9. Checklist triển khai và tự kiểm tra

**Checklist thực hành:**

1. Xác nhận backend đang dùng và tài liệu của provider về reference/value, thay vì chỉ dựa vào annotation.
2. Gọi một method `@Cacheable` hai lần cùng key; phân biệt hit/miss bằng log thân method.
3. Sau miss, sửa object nhận được rồi đọc lại; quan sát trạng thái và identity.
4. Sau hit, sửa object nhận được rồi đọc lần thứ ba; kiểm tra snapshot.
5. Nếu dùng copy mode, kiểm tra nested object, null, transient và serializable contract.
6. Khi dữ liệu nguồn thay đổi, kiểm tra đường `@CacheEvict`/`@CachePut` hoặc TTL.
7. Thử nhiều thread để phát hiện value mutable bị chia sẻ, và đo latency/GC của copy mode.

**Câu hỏi 1:** Tại sao `ref1 == ref2` là `true` trong demo?

**Trả lời:** Vì `ConcurrentMapCacheManager` ở mode tham chiếu lưu/đọc cùng object Java trong JVM, và cùng key `b1` dẫn tới cùng entry.

**Câu hỏi 2:** Tại sao sửa `value1` sau lượt miss vẫn không làm thay đổi dữ liệu ở lượt hit?

**Trả lời:** Khi xử lý miss, cache đã serialize một bản sao của giá trị gốc. Sửa `value1` không sửa snapshot đó; lần hit mới deserialize ra bản sao độc lập.

**Câu hỏi 3:** Bật `setStoreByValue(true)` có giải quyết cache stale không?

**Trả lời:** Không. Copy chỉ cách ly object mutation; dữ liệu nguồn thay đổi vẫn đòi TTL, eviction hoặc cập nhật cache phù hợp.

**Câu hỏi 4:** `ConcurrentHashMap` thread-safe có làm `MutableBook` bên trong tự thread-safe không?

**Trả lời:** Không. Thread safety của map không bảo vệ field mutable của value.

**Câu hỏi 5:** Một object không `Serializable` dùng được với chế độ copy trong `ConcurrentMapCacheManager` không?

**Trả lời:** Không theo cơ chế serialization mặc định này; cần một value/object graph có thể serialize hoặc đổi thiết kế lưu trữ/provider.

**Ghi nhớ:** Trong Spring Cache, cách chọn key và cách lưu value là hai vấn đề tách biệt. Với `ConcurrentMapCacheManager`, **store-by-reference là mặc định**, còn **store-by-value phải bật và có chi phí serialization**. Chọn object bất biến, xây dựng invalidation đúng key và xác nhận behavior của backend trước khi vận hành.

## Tài liệu tham khảo

- [Spring Framework 6.2 — ConcurrentMapCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html).
- [Spring Framework 6.2 — ConcurrentMapCache Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html).
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html).
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html).
