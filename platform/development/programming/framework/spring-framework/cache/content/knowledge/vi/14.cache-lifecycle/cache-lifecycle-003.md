# Chọn DTO hoặc dữ liệu bất biến để lưu trong Spring Cache

> **Spring Framework – Cache Abstraction · Nhóm: Dữ liệu và vòng đời.** Bài học giải thích tại sao giá trị cache nên là **DTO/snapshot không thể thay đổi ngoài ý muốn**, khi nào không nên cache trực tiếp entity có trạng thái thay đổi, cách thiết kế đối tượng bất biến trong Java 17+, và cách duy trì tính đúng đắn của cache khi dữ liệu nguồn được cập nhật.

## 1. Bài toán: cache không tự biến giá trị thành bản sao an toàn

Một lần gọi `@Cacheable` có thể trả về đối tượng Java chứa nhiều trường. Spring Cache Abstraction điều phối việc tìm key và lưu kết quả nhưng **không bảo đảm mọi cache backend đều sao chép sâu hoặc đóng băng đối tượng**. Với cache cục bộ lưu theo tham chiếu, object được đặt vào cache có thể chính là object mà code ứng dụng vẫn giữ.

Giả sử:

1. `getBook("BK-1")` tải một đối tượng `Book` có tên `"Java Basics"`.
2. Spring đưa đối tượng đó vào cache `books` theo key `"BK-1"`.
3. Code khác nhận object và sửa trực tiếp `book.setTitle("Changed")`.
4. Nếu cache giữ **cùng tham chiếu object**, lượt đọc tiếp theo có thể nhận `"Changed"` dù nguồn dữ liệu không hề được cập nhật tương ứng.

Hệ quả có thể gồm: dữ liệu bị thay đổi ngoài đường ghi chính thức; cache trở nên không đồng nhất với database; object giữa các request bị chia sẻ trạng thái; khó tái hiện lỗi đồng thời; vô tình trả thông tin phụ thuộc request này cho request khác.

Sơ đồ:

~~~text
DAO / Service
    |
    | @Cacheable trả về MutableBook
    v
Cache cục bộ lưu theo reference
    |
    +----> Request A nhận object ----> sửa title/tags
    |
    +----> Request B đọc cùng key ----> nhìn thấy state đã bị A sửa
~~~

**Nguyên tắc thiết kế:** cache những **giá trị mô tả trạng thái tại một thời điểm** thay vì chia sẻ các object có thể bị chỉnh sửa tùy ý. DTO bất biến, record được sao chép phòng vệ và những kiểu giá trị như `String` hoặc `BigDecimal` thường thích hợp hơn entity có vòng đời và trạng thái ORM.

Điều này không loại bỏ yêu cầu TTL, cập nhật và eviction. **Bất biến giúp ngăn mutation ngoài ý muốn; nó không tự làm dữ liệu cached trở nên mới khi nguồn thay đổi.**

## 2. DTO và immutable snapshot là gì?

**DTO (Data Transfer Object)** là đối tượng mang dữ liệu phục vụ trao đổi giữa các tầng hoặc trả cho client. DTO thường có một tập trường đã được chọn lọc thay vì toàn bộ quan hệ và behavior của entity.

**Immutable object** là đối tượng có trạng thái quan sát được không thay đổi sau khi tạo. Một lần trả về `BookView` đại diện snapshot lúc đọc; nếu nguồn được cập nhật, thay vì sửa object đã cache, ứng dụng tạo snapshot mới và xử lý invalidation.

Ví dụ dữ liệu nghiệp vụ:

~~~java
public record BookView(
        String isbn,
        String title,
        java.util.List<String> tags
) {
    public BookView {
        tags = java.util.List.copyOf(tags);
    }
}
~~~

`BookView` ở đây là **đoạn khai báo record độc lập về mặt cú pháp**, cần đặt trong tệp `BookView.java` hoặc làm nested record của class phù hợp. Với Java 17:

- Các thành phần record tạo field `final` và accessor như `isbn()`, `title()`, `tags()`.
- `String` là immutable, nên `isbn` và `title` không bị sửa nội tại.
- `List.copyOf(tags)` tạo danh sách **không cho phép mutation qua API list** và tránh chia sẻ danh sách nguồn có thể đổi, miễn các phần tử bên trong cũng immutable.
- `BookView` không cung cấp setter; để thể hiện bản mới cần tạo object `BookView` mới.

**Quan trọng:** từ khóa `record` chỉ bảo đảm tính final của tham chiếu thành phần, **không tự tạo deep immutability** cho đối tượng bên trong. Nếu `tags` là `ArrayList` và không thực hiện copy, caller vẫn có thể gọi `bookView.tags().add("unexpected")` làm thay đổi nội dung quan sát được. Vì vậy ví dụ đặt `List.copyOf` trong compact constructor.

### DTO không mặc nhiên bất biến

Đây là một DTO **mutable**:

~~~java
public class MutableBookDto {
    private String title;

    public MutableBookDto(String title) {
        this.title = title;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

Nếu đối tượng này được cache bằng backend lưu reference, caller có thể thay đổi `title`. Chỉ đổi tên entity thành DTO **không đủ**; phải xem cả cấu trúc trường, API cho phép sửa và cách cache provider lưu giá trị.

## 3. Vì sao thường tránh cache trực tiếp JPA entity?

Một JPA entity không phải lúc nào cũng nguy hiểm, nhưng việc đưa nó trực tiếp vào Spring Cache cần đánh giá kỹ những điểm sau:

| Rủi ro | Khi cache entity/proxy mutable | Khi cache DTO snapshot phù hợp |
| --- | --- | --- |
| Mutation ngoài quy trình cập nhật | Setter trên entity có thể sửa object cached trong bộ nhớ | Không có setter; tạo snapshot mới khi thay đổi |
| Lazy association | Proxy/collection lazy có thể cần session để đọc | Chỉ đưa trường đã materialize và thực sự cần |
| Persistence context | Entity có trạng thái managed/detached và lifecycle gắn ORM | DTO độc lập session/persistence context |
| Biểu diễn JSON | Quan hệ vòng, lazy initialization hoặc dữ liệu dư thừa | Cấu trúc phẳng, rõ schema |
| Serializability | Provider phân tán có thể không serialize được proxy/association | DTO được thiết kế/kiểm thử riêng cho codec |
| Kích thước cache | Graph quan hệ có thể giữ nhiều dữ liệu không cần thiết | Chỉ giữ trường cần cho use case |
| Nhạy cảm dữ liệu | Entity có thể chứa trường nội bộ không nên cache hoặc trả về | Chọn lọc trường theo nguyên tắc tối thiểu |

Ví dụ một `OrderEntity` có thể chứa thông tin thanh toán, địa chỉ, quan hệ lazy với hàng trăm order items, và trạng thái dirty checking. Nếu màn hình chỉ cần `orderId`, `total` và `status`, hãy tạo `OrderSummary` từ dữ liệu đã tải. Snapshot này dễ đo kích thước, quản lý phiên bản schema và làm chủ vòng đời hơn.

**Phân biệt hai tầng cache:** Spring Cache (`@Cacheable`) là cache cấp ứng dụng do Spring điều phối; JPA/Hibernate **second-level cache** và first-level persistence context là những cơ chế ORM khác. Hướng dẫn chọn DTO tại đây nhằm xử lý **giá trị lưu trong Spring Cache**, không phải hướng dẫn tắt/bật JPA second-level cache.

### Một số trường hợp có thể cache entity?

Không phải mọi entity đều bị cấm tuyệt đối. Một object thật sự bất biến, không dính lazy proxy khó kiểm soát, có vòng đời rõ ràng và tương thích backend có thể được cân nhắc. Nhưng khi cần chính sách dễ review giữa nhiều team, **DTO snapshot đơn giản, có hợp đồng rõ ràng thường là mặc định an toàn hơn**. Đừng cache object đang attached vào một phiên truy cập DB rồi giả định entity có thể dùng nguyên trạng ở mọi request.

## 4. Bất biến phải xét đến cả object graph

### 4.1. Final không làm phần tử bên trong tự bất biến

~~~java
import java.util.List;

public record UnsafeBookView(String isbn, List<String> tags) {
}
~~~

`UnsafeBookView` chỉ có field tham chiếu `tags` là final. Nếu caller truyền vào `ArrayList`, có thể thay đổi nội dung list thông qua `view.tags().add("new")` hoặc một tham chiếu được giữ từ bên ngoài.

Một phiên bản an toàn cho dữ liệu gồm `String`:

~~~java
import java.util.List;

public record SafeBookView(String isbn, List<String> tags) {
    public SafeBookView {
        tags = List.copyOf(tags);
    }
}
~~~

Ví dụ này là **định nghĩa record dùng trong tệp Java phù hợp**, không phải chương trình có main. Với list chứa String:

- Mutation list nguồn sau khi tạo record không thay đổi snapshot.
- Caller không thể `add`, `remove` hoặc `set` phần tử thông qua `tags()`.
- Cần quyết định rõ cách xử lý `null`: `List.copyOf` không chấp nhận collection hoặc phần tử null.

`Collections.unmodifiableList(sourceList)` **khác về ý nghĩa**: đó có thể là view không sửa được *qua tham chiếu ấy*, nhưng nếu `sourceList` phía sau bị chỉnh sửa thì view vẫn phản ánh thay đổi. `List.copyOf` lấy một bản sao không sửa được theo contract; với nguồn đã là immutable list, JDK có thể tái sử dụng instance mà vẫn an toàn theo hợp đồng bất biến.

### 4.2. List.copyOf chỉ sao chép cấu trúc list

Nếu list chứa object mutable:

~~~java
import java.util.List;

public record Address(String street) {
}

public record CustomerView(String customerId, List<Address> addresses) {
    public CustomerView {
        addresses = List.copyOf(addresses);
    }
}
~~~

Trong ví dụ trên, `Address` là record chỉ chứa `String`, nên từng phần tử cũng bất biến theo thiết kế. Nếu `Address` là một class có setter mutable, `List.copyOf` chỉ giữ các tham chiếu phần tử, **không sao chép sâu mỗi Address**. Khi đó cần chuyển từng phần tử sang một value object bất biến trước khi tạo list.

Một pattern chuyển dữ liệu, khi `MutableAddress` có phương thức `getStreet()`:

~~~java
List<Address> snapshots = addressesFromSource.stream()
        .map(address -> new Address(address.getStreet()))
        .toList();
CustomerView view = new CustomerView("C-1", snapshots);
~~~

Đây là đoạn **mapping minh họa trong method**, cần biến `addressesFromSource` và kiểu `MutableAddress` từ ứng dụng thật. Method `toList()` (Java 16+) tạo list không hỗ trợ mutation, và constructor `CustomerView` thực hiện `List.copyOf` để thể hiện quy tắc snapshot ngay tại ranh giới DTO.

### 4.3. Trường ngày giờ, số và collection

Ưu tiên kiểu giá trị vốn immutable khi có thể:

- `String`, `BigDecimal`, `UUID`, `LocalDate`, `Instant`: dễ suy luận hơn các class mutable tương ứng.
- `LocalDateTime`/`Instant` trong `java.time` là immutable; với dữ liệu thời điểm phân tán, nêu rõ timezone/UTC và cách biểu diễn.
- Nếu dữ liệu nguồn dùng `java.util.Date` mutable, chuyển sang `Instant` hoặc copy phòng vệ khi vào DTO.
- `List.copyOf`, `Set.copyOf`, `Map.copyOf` có ích cho collection khi **key và value bên trong cũng an toàn**; các hàm này không deep copy object lồng nhau.
- Không đưa trực tiếp `InputStream`, `EntityManager`, `Session`, `Connection`, `HttpServletRequest` hay thread-bound context vào cache value. Chúng mang tài nguyên/vòng đời thay vì một snapshot dữ liệu thuần.

Không biến bất biến thành một quy tắc máy móc gây copy quá mức. Với collection lớn, cần xét memory và chi phí copy; khi value thực sự immutable từ đầu, có thể tái sử dụng một kiểu immutable chuyên dụng.

## 5. Ví dụ hoàn chỉnh Java 17+: cache DTO bất biến thay vì object nguồn mutable

Ví dụ sử dụng **Spring Framework 6.2.14**, `ConcurrentMapCacheManager` và Java 17. Dữ liệu nguồn được mô phỏng bằng một class mutable chứa `title` và `ArrayList<String> tags`. Phương thức `@Cacheable` tạo **BookView record bất biến** trước khi cache; `@CacheEvict` xóa key khi nguồn thay đổi.

Mục tiêu quan sát:

1. Hai lần đọc cùng ISBN qua proxy dùng một entry cache.
2. Cố sửa `tags` qua DTO bị từ chối.
3. Khi nguồn thay đổi, DTO cũ **không bị sửa theo**.
4. Eviction loại bỏ entry cũ; lần đọc sau tạo DTO mới đúng nguồn.

Tạo hai tệp như sau.

**Tệp `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ImmutableCacheValueDemo'
}
~~~

**Tệp `src/main/java/demo/ImmutableCacheValueDemo.java`:**

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ImmutableCacheValueDemo {

    // Giá trị cache: snapshot theo ISBN, không chia sẻ list mutable.
    public record BookView(String isbn, String title, List<String> tags) {
        public BookView {
            Objects.requireNonNull(isbn, "isbn");
            Objects.requireNonNull(title, "title");
            tags = List.copyOf(tags);
        }
    }

    // Chỉ dùng để mô phỏng entity/record nguồn có thể cập nhật.
    static final class MutableBook {
        String title;
        final List<String> tags;

        MutableBook(String title, List<String> tags) {
            this.title = title;
            this.tags = new ArrayList<>(tags);
        }
    }

    public static class BookService {
        private final Map<String, MutableBook> source =
                new ConcurrentHashMap<>(Map.of(
                        "BK-1",
                        new MutableBook("Effective Java", List.of("java", "books"))
                ));
        private int sourceReads;

        @Cacheable(cacheNames = "books", key = "#p0")
        public BookView getBook(String isbn) {
            sourceReads++;
            MutableBook book = source.get(isbn);
            if (book == null) {
                return null;
            }
            return new BookView(isbn, book.title, book.tags);
        }

        @CacheEvict(cacheNames = "books", key = "#p0")
        public void renameBook(String isbn, String newTitle) {
            if (newTitle == null || newTitle.isBlank()) {
                throw new IllegalArgumentException("new title is blank");
            }
            MutableBook book = Objects.requireNonNull(
                    source.get(isbn), "unknown isbn"
            );
            book.title = newTitle;
            book.tags.add("revised");
        }

        public int sourceReads() {
            return sourceReads;
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("books");
        }

        @Bean
        public BookService bookService() {
            return new BookService();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            BookService service = context.getBean(BookService.class);
            CacheManager manager = context.getBean(CacheManager.class);
            Cache books = Objects.requireNonNull(manager.getCache("books"));

            BookView first = service.getBook("BK-1");
            BookView second = service.getBook("BK-1");

            System.out.println("first: " + first);
            System.out.println("same object on hit: " + (first == second));
            System.out.println("source reads before update: " +
                    service.sourceReads());

            boolean blocked = false;
            try {
                first.tags().add("injected");
            } catch (UnsupportedOperationException ex) {
                blocked = true;
            }
            System.out.println("mutation blocked: " + blocked);

            service.renameBook("BK-1", "Effective Java 4");
            System.out.println("cache entry after update: " +
                    (books.get("BK-1") != null));
            System.out.println("old snapshot title: " + first.title());

            BookView fresh = service.getBook("BK-1");
            System.out.println("fresh: " + fresh);
            System.out.println("source reads after update: " +
                    service.sourceReads());
        }
    }
}
~~~

Chạy ở thư mục chứa `build.gradle`, với JDK 17+ và Gradle tương thích:

~~~bash
gradle run --quiet
~~~

**Stdout dự kiến của chương trình** (không tính log của Gradle hoặc môi trường ngoài):

~~~text
first: BookView[isbn=BK-1, title=Effective Java, tags=[java, books]]
same object on hit: true
source reads before update: 1
mutation blocked: true
cache entry after update: false
old snapshot title: Effective Java
fresh: BookView[isbn=BK-1, title=Effective Java 4, tags=[java, books, revised]]
source reads after update: 2
~~~

### Giải thích từng kết quả

1. `getBook("BK-1")` lần đầu chạy thân method và tạo `BookView` chứa bản sao danh sách. Lần hai cùng key hit `books` nên không chạy thân method; `sourceReads = 1`.
2. `same object on hit: true` đúng **trong ví dụ dùng `ConcurrentMapCacheManager` mặc định với kiểu lưu theo tham chiếu**. Không khẳng định identity của object là true ở tất cả backend phân tán hoặc backend lưu theo value/serialization.
3. `first.tags().add("injected")` ném `UnsupportedOperationException` bởi list nhận từ `List.copyOf`, nên chương trình in `mutation blocked: true`. Nếu chọn Mutable DTO, thao tác sửa có thể ảnh hưởng object cache đang được chia sẻ.
4. `renameBook` sửa **nguồn** và thêm nhãn `"revised"`, rồi Spring `@CacheEvict` xóa entry cùng key theo mặc định sau khi method thành công. Vì thế `books.get("BK-1")` trả null (không có entry).
5. Biến `first` vẫn tham chiếu bản snapshot cũ với title `"Effective Java"`. Nó **không tự đổi** sau khi nguồn được sửa.
6. `getBook("BK-1")` sau eviction lại chạy thân method, tạo snapshot mới có `"Effective Java 4"` và thêm tag `"revised"`; `sourceReads` tăng lên 2.

Ví dụ có chủ đích đơn luồng để tập trung vào lựa chọn cache value. Trong ứng dụng thực, thao tác cập nhật nguồn và eviction phải xét transaction, concurrency và quy tắc invalidation cụ thể. `@EnableCaching` và việc lấy bean qua `AnnotationConfigApplicationContext` giúp lời gọi đi qua caching proxy. Nếu gọi phương thức `getBook` nội bộ bằng `this.getBook("BK-1")` trong cùng bean, chế độ proxy mặc định có thể bỏ qua annotation.

## 6. Snapshot bất biến không thay thế chiến lược vòng đời cache

Một `BookView` bất biến ngăn caller sửa object cached, nhưng nếu DB đổi tên sách từ `"Effective Java"` thành tên mới, snapshot cũ vẫn là **một bản đúng ở thời điểm cũ**, không tự thành dữ liệu mới.

Các yếu tố cần thiết:

### 6.1. Key phải ổn định và đủ định danh dữ liệu

Với ví dụ, `key = "#p0"` là ISBN. Nếu dữ liệu trả về còn phụ thuộc tenant, ngôn ngữ, quyền truy cập hoặc tham số khác, key phải phản ánh **đầy đủ** những yếu tố ảnh hưởng đến kết quả. Ví dụ cùng `bookId` nhưng mỗi tenant có trạng thái riêng mà cache chỉ key theo bookId có thể trả nhầm dữ liệu sang tenant khác.

Không cache trực tiếp object đầu vào mutable làm key nếu `equals()`/`hashCode()` phụ thuộc trạng thái có thể đổi. Ưu tiên `String`/ID ổn định hoặc value object immutable được định nghĩa rõ.

### 6.2. Xóa hoặc cập nhật entry sau khi nguồn thay đổi

`@CacheEvict(cacheNames = "books", key = "#p0")` phù hợp khi update thành công làm snapshot cũ mất hiệu lực. `@CachePut` có thể thay thế nếu method update luôn trả đúng DTO mới và cấu trúc cache phù hợp, nhưng không dùng nó chỉ vì muốn tránh evict mà không có giá trị trả về tương ứng.

Với `@Transactional`, eviction sau khi method thành công **không mặc nhiên** bảo đảm DB đã commit. Thiết kế yêu cầu nhất quán cao nên kiểm soát việc invalidation sau commit và các race giữa reader/writer. `TransactionAwareCacheManagerProxy` hoặc xử lý sau commit là các hướng cần kiểm chứng theo provider và transaction boundary.

### 6.3. TTL và khả năng giữ dữ liệu cũ

TTL/TTI, eviction do dung lượng và persistence của cache là chính sách **phụ thuộc provider**. Một DTO bất biến có thể vẫn stale nếu TTL quá dài hoặc ứng dụng quên invalidation.

- Dữ liệu thường xuyên cập nhật: cần TTL ngắn hơn hoặc event-driven invalidation.
- Dữ liệu đọc nhiều nhưng thay đổi hiếm: TTL dài hơn có thể giảm chi phí tải nguồn.
- Dữ liệu nhạy cảm: không giữ lâu hơn vòng đời được phép và không cache thông tin mà mọi caller có thể đọc nhầm.

Spring Cache abstraction không cung cấp một TTL đồng nhất áp dụng cho mọi backend chỉ bằng `@Cacheable`; cần cấu hình cache provider.

### 6.4. DTO schema và cách serialize

Với cache phân tán như Redis, dữ liệu thường được serialize thành JSON hoặc binary. Khi đổi schema DTO giữa hai phiên bản deploy, bản cache cũ có thể không deserialize được hoặc thiếu trường quan trọng.

Cân nhắc version cache name/key, codec đã kiểm thử, migration/eviction khi deploy và compatibility giữa producer/consumer. Record immutable giúp dễ nhìn schema nhưng không tự giải quyết mọi vấn đề về serializer.

### 6.5. Kích thước, độ sâu và bảo mật

DTO nên chứa dữ liệu **đủ dùng** cho method, không phải copy toàn bộ entity graph. Cache quá nhiều trường tăng memory footprint, network payload và thời gian serialize. Ngược lại, DTO thiếu các trường mà method đã hứa trả về có thể gây lỗi chức năng.

Đặc biệt tránh đưa password, token, session-bound object hoặc dữ liệu riêng người dùng vào vùng cache dùng key thiếu tenant/user context. Bất biến **không thay thế** access control và cách phân vùng cache.

## 7. So sánh các lựa chọn cache value

| Lựa chọn | Ưu điểm | Hạn chế / lưu ý | Khi cân nhắc |
| --- | --- | --- | --- |
| JPA entity mutable | Ít mapping ban đầu | Có setter, proxy lazy, trạng thái ORM, dữ liệu dư | Chỉ khi có chính sách rõ về lifecycle và provider |
| DTO class mutable | Dễ tích hợp thư viện cũ | Caller có thể sửa field/list; không giải quyết reference sharing | Khi boundary có defensive copying và kiểm soát mutation |
| Java `record` với trường immutable | Gọn, rõ constructor/accessor, giá trị dễ đọc | Record chỉ shallow immutable nếu lồng object mutable | Ưu tiên cho cache snapshot thuần dữ liệu |
| `record` + copy collection / element | Hạn chế mutation cả collection và phần tử | Tốn chi phí copy/mapping, cần xử lý null | Mặc định tốt cho dữ liệu có nested collections |
| Serialized value (Redis hoặc store-by-value) | Tách identity theo nhiều thao tác đọc/ghi | Codec, schema, độ trễ, copy/serialization không thay thế invalidation | Cache đa instance cần chia sẻ |
| Cache ID, tải entity ở tầng khác | Giá trị cache nhẹ | Có thể không giảm đủ truy vấn và độ trễ | Dữ liệu phức tạp, cần tách lookup khỏi object graph |

**Khuyến nghị thực hành:** bắt đầu với DTO bất biến chứa **đúng những field read path cần**, tạo trong tầng đọc sau khi đã materialize dữ liệu liên quan; chỉ mở rộng khi đo đạc cho thấy cần lưu nhiều hơn.

## 8. Cách thiết kế mapping ở ranh giới cache

Một pipeline rõ ràng:

~~~text
Repository / API nguồn
         |
         | Tải dữ liệu theo nghiệp vụ
         v
  Entity / model mutable
         |
         | Map + materialize lazy fields cần thiết
         | Copy collection / element mutable
         v
    Immutable DTO
         |
         | @Cacheable đặt vào cache theo key
         v
 Cache chứa snapshot
         |
         | Nhiều caller đọc cùng DTO
         v
  Không thể sửa snapshot ngoài ý muốn
~~~

Nếu mapping có chi phí lớn, quyết định **nơi đặt `@Cacheable`** cũng quan trọng. Đặt annotation trên method trả immutable DTO để cache chứa kết quả sau mapping, thay vì cache entity rồi mỗi request phải map lại hoặc vô tình lộ ra object mutable từ cache.

**Cần lưu ý ownership:** bản DTO có thể được chia sẻ giữa request nếu cache lưu theo reference. Thiết kế nên giả định caller sẽ đọc nhưng không được phép sửa nó. Record với collection được copy và phần tử immutable đáp ứng điều đó tốt hơn việc dựa vào quy ước “mọi người đừng gọi setter”.

Đừng đưa entity lazy vào cache rồi xử lý lỗi lazy-load bằng cách mở rộng session sang request hoặc bật eager toàn bộ quan hệ không cần thiết. Hãy xác định rõ dữ liệu mà DTO cần, truy vấn đúng dữ liệu ấy rồi tạo snapshot trong transaction boundary thích hợp.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Trả từ cache nhưng title/tags bị request khác sửa | Cache lưu object mutable theo reference | DTO immutable; defensive copy list và nested values |
| Dùng record mà list vẫn đổi | Record shallow immutable, chứa list gốc mutable | `List.copyOf` trong constructor; kiểm tra phần tử |
| Dùng `Collections.unmodifiableList` nhưng dữ liệu vẫn thay đổi | View bọc list gốc và list gốc bị sửa từ nơi khác | Tạo snapshot riêng bằng `List.copyOf` hoặc copy tương đương |
| Cache trực tiếp entity, serialize lỗi | Lazy proxy, bidirectional relationship hoặc serializer không phù hợp | Map sang DTO rõ schema, kiểm thử codec |
| Dữ liệu trong cache khác DB sau update | Bất biến không đồng nghĩa freshness | `@CacheEvict`/`@CachePut`, TTL, xử lý commit |
| Hai tenant nhìn thấy cùng giá trị | Cache key thiếu tenant/user discriminator | Bổ sung thành phần key và kiểm soát quyền |
| `List.copyOf` ném `NullPointerException` | Collection đầu vào có null hoặc bản thân list null | Chuẩn hóa hoặc từ chối null theo hợp đồng DTO |
| Memory cache tăng nhanh | DTO chứa graph dữ liệu quá lớn hoặc TTL quá dài | Chỉ giữ trường cần thiết, giới hạn size, cấu hình eviction |
| Record cũ không deserialize được sau deploy | Schema/codec không tương thích | Chiến lược schema versioning, test migration/eviction |
| Annotation không hoạt động khi gọi cùng bean | Self-invocation bỏ qua Spring proxy | Gọi qua bean proxy khác hoặc thiết kế lại tầng service |

### Kiểm tra trước khi đưa một kiểu dữ liệu vào cache

Hãy trả lời:

1. **Có setter hoặc collection mutable không?** Nếu có, caller hoặc luồng khác có sửa được trạng thái cached không?
2. **Có lazy association, DB session hoặc tài nguyên sống không?** Nếu có, nên map dữ liệu cần thiết ra ngoài vòng đời đó.
3. **Có dữ liệu không nên chia sẻ không?** Nếu có, cắt bỏ khỏi DTO hoặc bảo đảm phân vùng/key và quyền truy cập đúng.
4. **Key và vòng đời thế nào?** Nếu nguồn đổi, đường ghi nào sẽ evict/update? Cache expire khi nào?
5. **Có serialize được không?** Nếu backend remote, test đọc/ghi và deploy khác phiên bản.
6. **Có đáng cache cả object không?** Đo memory, tỷ lệ hit và thời gian mapping/tải nguồn.

Không cần biến mọi giá trị thành một cây deep-copy lớn. Cần một **hợp đồng bất biến rõ ràng ở ranh giới mà object được chia sẻ**, có đánh giá chi phí và mô hình vòng đời tương ứng.

## 10. Bài tập tự kiểm tra

**Bài 1.** `record ProductView(String id, List<String> tags)` có tự bảo đảm rằng `tags()` không thể thay đổi không?

**Đáp án:** Không. Record giữ tham chiếu cuối cùng nhưng list có thể mutable. Nên copy thành `List.copyOf(tags)` trong constructor hoặc dùng collection immutable theo hợp đồng.

**Bài 2.** Tại sao cache trực tiếp JPA entity đang managed có thể gây vấn đề dù key đúng?

**Đáp án:** Entity có trạng thái mutable, quan hệ lazy và vòng đời liên quan persistence context. Một object được chia sẻ qua cache có thể bị sửa ngoài ý muốn hoặc không dùng được ngoài session. DTO snapshot giảm những ràng buộc ấy.

**Bài 3.** Có `List.copyOf` cho list chứa đối tượng `MutableAddress` có setter; DTO đã deep immutable chưa?

**Đáp án:** Chưa. List không sửa được về cấu trúc nhưng phần tử vẫn có thể bị đổi. Cần chuyển phần tử sang value object immutable hoặc copy phòng vệ sâu hơn.

**Bài 4.** Sau update thành công, cache đang giữ `BookView` immutable có tự đổi title theo DB không?

**Đáp án:** Không. Cần evict/update entry và chính sách TTL/invalidation phù hợp. Immutable chỉ ngăn mutation ngoài ý muốn, không làm dữ liệu luôn mới.

**Bài 5.** Trong ví dụ sử dụng `ConcurrentMapCacheManager` mặc định, vì sao `first == second` có thể là true?

**Đáp án:** `ConcurrentMapCache` mặc định lưu theo reference trong cùng JVM; cache hit có thể trả lại cùng instance. Với backend có serialization hoặc store-by-value, identity không nhất thiết được giữ.

## 11. Tổng kết và nguồn chính thức

**Điểm cần nhớ:**

- **Spring Cache không mặc định bảo đảm deep copy hay biến cached value thành immutable.**
- DTO chỉ là tên gọi; **DTO mutable vẫn có nguy cơ** nếu backend giữ cùng tham chiếu.
- Với Java 17+, `record` là lựa chọn dễ đọc cho snapshot; cần bảo vệ collection và nested object bằng copy phù hợp.
- Tránh lưu trực tiếp entity lazy/managed nếu cache value phải độc lập với ORM lifecycle và chạy qua nhiều request hoặc instance.
- **Immutability ≠ freshness**: vẫn cần cache key đúng, `@CacheEvict`/`@CachePut`, TTL và chiến lược sau commit.
- Cache chỉ những trường thực sự cần, kiểm tra serialization, bảo mật và kích thước.

**Tham khảo:**

- [Spring Framework 6.2 – Cache Abstraction](https://docs.spring.io/spring-framework/reference/6.2/integration/cache.html)
- [Spring Framework 6.2 – Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html)
- [Spring Framework – ConcurrentMapCache API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html)
- [Java 17 – List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
- [Java 17 – Records](https://docs.oracle.com/en/java/javase/17/language/records.html)
