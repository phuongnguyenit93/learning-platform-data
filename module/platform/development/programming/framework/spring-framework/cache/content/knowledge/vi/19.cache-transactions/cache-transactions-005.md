# Giới hạn của putIfAbsent và các thao tác cần hiệu lực tức thời

> **Ngữ cảnh:** Spring Framework Cache — mục **Giao dịch**. Bài học giải thích một khác biệt dễ gây lỗi giữa các thao tác cache có thể trì hoãn đến lúc **giao dịch commit** (`put`, `evict`, `clear`) và những thao tác cần hiệu lực **ngay ở thời điểm gọi** (`putIfAbsent`, `evictIfPresent`, `invalidate`). Trọng tâm là giới hạn nguyên tử của `putIfAbsent`, mối liên hệ với `TransactionAwareCacheDecorator` và cách kiểm thử tính nhất quán DB–cache khi commit/rollback.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **đăng ký thao tác cache** và **thời điểm thay đổi thực sự nhìn thấy được**.
2. Giải thích vì sao `Cache.putIfAbsent` không chỉ là cách viết ngắn của `get` rồi `put`, và vì sao tính nguyên tử còn phụ thuộc implementation.
3. Chọn đúng cặp thao tác: `put`/`putIfAbsent`, `evict`/`evictIfPresent`, `clear`/`invalidate`.
4. Hiểu cơ chế `TransactionAwareCacheDecorator`/`TransactionAwareCacheManagerProxy` hoãn một số thao tác đến **after-commit**.
5. Nhận ra các thao tác tức thời **không được rollback cùng JDBC transaction**, nên có thể khiến cache lệch dữ liệu nguồn.
6. Hiểu ý nghĩa thực tế của các giá trị trả về như `Cache.ValueWrapper` và `boolean`, cùng những giới hạn khi backend không xác định được trạng thái trước đó.
7. Chạy một ví dụ Java 17 dùng Spring Framework, H2 in-memory, `DataSourceTransactionManager` và `TransactionTemplate` để quan sát commit/rollback thật.
8. Thiết kế kiểm thử và chọn cách xử lý cập nhật cache cho nghiệp vụ đòi hỏi tính nhất quán.

## 2. Spring Cache và transaction không phải cùng một kho dữ liệu

Spring Cache được thiết kế chủ yếu làm **cache abstraction**. Database transaction do JDBC/JPA transaction manager quản lý; cache provider có thể nằm trong JVM, Redis hoặc một hệ thống khác. Việc ứng dụng sử dụng `@Transactional` **không tự biến DB và cache thành một giao dịch nguyên tử**.

```text
Client
  |
  v
Service / TransactionTemplate / @Transactional
  |
  +---- JDBC / JPA -----------------> Database
  |                                    COMMIT / ROLLBACK
  |
  +---- Spring Cache API ------------> Cache decorator
                                         |
                                         +-- deferred put/evict/clear
                                         |    sau COMMIT nếu được cấu hình
                                         |
                                         +-- immediate putIfAbsent
                                         +-- immediate evictIfPresent
                                         +-- immediate invalidate
                                              |
                                              v
                                        Provider cache
```

Điều quan trọng:

- Một **giao dịch DB** có thể rollback dữ liệu DB.
- Nếu cache đã thay đổi **tức thời**, rollback DB không tự quay ngược sự thay đổi trong cache.
- Một decorator **transaction-aware** có thể trì hoãn một số lệnh cache đến sau commit để giảm rủi ro này, nhưng không thể trì hoãn mọi lệnh vì có những API đòi kết quả ngay.
- Ngay cả khi cache cập nhật sau commit, cập nhật cache vẫn có thể thất bại, mất kết nối hoặc xảy ra race; đó không phải XA transaction giữa DB và cache.

Vì vậy câu hỏi đúng không chỉ là “có dùng `@Transactional` không”, mà là **lệnh cache được thực hiện ở giai đoạn nào và có yêu cầu quan sát tức thời hay không**.

## 3. put và putIfAbsent: khác nhau ở cả ngữ nghĩa lẫn thời điểm

### 3.1. Cache.put(key, value)

```java
cache.put("A", 20);
```

Lệnh `put` đặt hoặc thay value cho key. Theo giao diện `Cache` của Spring, việc đưa mục vào cache **có thể được thực hiện bất đồng bộ hoặc trì hoãn**. Trong một `TransactionAwareCacheDecorator`, nếu giao dịch Spring đang hoạt động và có synchronization, `put` sẽ được hẹn thực hiện ở **after-commit của giao dịch thành công**.

Ví dụ:
1. Trước transaction: cache chưa có key `A`.
2. Bên trong transaction: `cache.put("A", 20)`.
3. Tra cache ngay sau dòng này có thể **vẫn miss** vì thao tác chưa được áp dụng lên store thật.
4. Transaction commit: thao tác `put` mới được áp dụng.
5. Transaction rollback: thao tác `put` đã đăng ký không được thực hiện.

Đây là hành vi của decorator được cấu hình **transaction-aware**, không phải cam kết của mọi `Cache`. Với `ConcurrentMapCache` sử dụng trực tiếp, `put` thường ghi ngay vào map kể cả khi JDBC transaction đang mở.

### 3.2. Cache.putIfAbsent(key, value)

```java
Cache.ValueWrapper prior = cache.putIfAbsent("A", 20);
```

`putIfAbsent` có hai yêu cầu:
- **Chỉ ghi nếu chưa có entry** cho key.
- **Trả thông tin về giá trị đã tồn tại** (nếu có) ngay trong lời gọi.

Nó được dùng khi caller cần biết “key đã được chiếm chưa?” tại thời điểm thao tác. Vì cần hiệu lực và kết quả **tức thời**, `TransactionAwareCacheDecorator` **không hoãn** thao tác này đến after-commit; nó chuyển việc thực hiện trực tiếp tới cache thực.

Ví dụ:
- Cache chưa có A; `putIfAbsent("A", 20)` có thể lập tức tạo A=20 và trả `null` (không có wrapper trước đó).
- Lần hai `putIfAbsent("A", 30)` thấy A tồn tại, trả wrapper của 20 và **không thay** A bằng 30.
- Nếu cả hai xảy ra bên trong một JDBC transaction rồi transaction rollback, dữ liệu cache đã được đặt **không tự bị rollback**.

**Điểm mấu chốt:** “cần hiệu lực ngay” và “an toàn với rollback” là hai mục tiêu khác nhau. Một thao tác có thể đúng về tính atomic trong cache nhưng **không atomic với database**.

## 4. putIfAbsent có thực sự atomic không?

JavaDoc `Cache.putIfAbsent` mô tả hành vi như một tổ hợp nguyên tử tương đương về ý tưởng với:

```java
Cache.ValueWrapper existing = cache.get(key);
if (existing == null) {
    cache.put(key, value);
}
return existing;
```

Nhưng đoạn ba bước trên **không atomic** nếu tự viết. Giữa `get` và `put`, một thread khác có thể ghi cùng key. Hai thread cùng thấy miss và đều `put`; thread ghi sau có thể đè lên thread trước.

`putIfAbsent` được tạo để nhà cung cấp cache có cơ hội thực hiện “check + insert” như **một thao tác atomic**. Tuy nhiên JavaDoc Spring nói rõ implementation mặc định của interface có thể dùng hai bước `get` rồi `put`; **không phải mọi provider tùy chỉnh đều bảo đảm atomicity**.

### Khi nào có thể dựa vào atomicity?

- `ConcurrentMapCache` của Spring dùng cấu trúc concurrent trong một JVM và hỗ trợ put-if-absent dựa trên map atomic, phù hợp cho ví dụ trong bài này.
- Với Caffeine, Redis, JCache hoặc cache manager tự viết, phải đọc hợp đồng của provider/adapter đang chạy; một API có cùng tên không bảo đảm cùng mức atomicity hoặc phạm vi phối hợp.
- “Atomic trong cache” không có nghĩa “atomic với DB”, “khóa toàn bộ cluster”, “đúng một lần nghiệp vụ” hoặc “có thể đảo ngược khi rollback”.

Vì vậy, đừng dùng `putIfAbsent` làm cơ chế chống ghi trùng thanh toán, đảm bảo tồn kho hay idempotency nghiệp vụ quan trọng **nếu chưa có ràng buộc ở nguồn chuẩn** như unique constraint, transaction, optimistic lock hoặc idempotency key được lưu bền.

### Ví dụ hai thread cạnh tranh cùng key

Giả sử cache `locks` trống:

```text
Thread A: putIfAbsent("order-42", "A") -> null
Thread B: putIfAbsent("order-42", "B") -> wrapper("A")
Cache: "order-42" = "A"
```

Đây là một **kịch bản thứ tự chạy có thể xảy ra** trên cache có put-if-absent atomic; thứ tự A/B không cố định. Kết quả chính cần quan tâm là **chỉ một value được ghi đầu tiên** khi hai lời gọi cạnh tranh trên cùng phạm vi atomicity của provider.

Nhưng nếu A thắng put-if-absent rồi transaction DB của A rollback, cache có thể còn key `order-42` mặc dù nghiệp vụ của A không tồn tại ở DB. Khi đó B bị từ chối không phải vì DB đã commit một đơn hợp lệ, mà chỉ vì cache vẫn có một dấu tạm thời.

## 5. ValueWrapper và ý nghĩa của kết quả trả về

Phần lớn API Spring Cache phân biệt **entry chưa tồn tại** với **entry tồn tại nhưng value null** thông qua `Cache.ValueWrapper`.

```java
Cache.ValueWrapper old = cache.putIfAbsent("item-1", "new");

if (old == null) {
    System.out.println("No prior cache entry");
} else {
    System.out.println("Prior value = " + old.get());
}
```

- `old == null` thường biểu thị không có mapping trước thao tác, nên value vừa được liên kết.
- `old != null` biểu thị đã có một mapping; `old.get()` có thể là null nếu provider cho phép cache null.
- Không dùng `old.get() == null` làm đồng nghĩa với “chưa có mapping”: cached null cũng có thể được bao bởi wrapper.
- Trả về wrapper mô tả **trạng thái của cache**, không mô tả trạng thái commit của database.

Nếu method khác cần đọc value ngay sau `putIfAbsent`, đọc lại từ cache thường quan sát được mapping mới trên provider hỗ trợ immediate put. Nếu cache có behavior bất đồng bộ/đa node, phải xác minh tính nhìn thấy được thực tế.

## 6. Ba cặp API: trì hoãn được hay phải tức thời?

| Thao tác thông thường | Biến thể cần hiệu lực ngay | Hành vi được phép của API |
| --- | --- | --- |
| `put(key, value)` | `putIfAbsent(key, value)` | `put` có thể trì hoãn; `putIfAbsent` nhằm đặt ngay nếu chưa có và trả mapping cũ |
| `evict(key)` | `evictIfPresent(key)` | `evict` có thể trì hoãn; `evictIfPresent` kỳ vọng key **không còn nhìn thấy ngay** |
| `clear()` | `invalidate()` | `clear` có thể trì hoãn; `invalidate` kỳ vọng toàn bộ mapping **không còn nhìn thấy ngay** |

Ba dạng tức thời có giá trị khi caller cần một hậu điều kiện ngay sau lời gọi. Nhưng mặt trái là thay đổi trên store có thể xảy ra **trước khi giao dịch DB commit**, thậm chí tồn tại sau rollback.

### 6.1. evict và evictIfPresent

```java
cache.evict("A");
```

`evict` yêu cầu xóa mapping nhưng actual eviction có thể deferred hoặc asynchronous. Với `TransactionAwareCacheDecorator`, `evict` trong transaction được đẩy đến after-commit. Gọi `cache.get("A")` ngay bên trong transaction có thể **vẫn thấy entry cũ**.

```java
boolean existed = cache.evictIfPresent("A");
```

`evictIfPresent` yêu cầu mapping không còn nhìn thấy **ngay lập tức** sau lời gọi. Nó không đợi transaction commit. Nếu DB rollback, key bị xóa **không được tự khôi phục**. Đây có thể gây cache miss và tải lại nguồn; nếu một request khác tải nguồn cũ trước commit, còn có thể phát sinh stale entry.

**Giá trị trả về `boolean`:** true nếu provider **biết chắc** key đã có mapping trước khi xóa; false nếu không có hoặc provider **không xác định được trạng thái trước đó**. Không diễn giải false là bằng chứng tuyệt đối key không tồn tại. Implementation mặc định của interface có thể delegate sang `evict` và không xác định chính xác trạng thái cũ; hãy kiểm tra provider nếu ứng dụng cần hậu điều kiện mạnh.

### 6.2. clear và invalidate

```java
cache.clear();
```

`clear()` yêu cầu xóa tất cả entry của cache logic, nhưng có thể được thực hiện chậm/hoãn. `TransactionAwareCacheDecorator` có thể đăng ký clear để làm sau commit.

```java
boolean hadEntries = cache.invalidate();
```

`invalidate()` yêu cầu **mọi entry trở nên vô hình ngay** khi lời gọi hoàn tất, theo hợp đồng immediate của API. Nó không bị hoãn bởi transaction-aware decorator. Giá trị trả về true khi biết trước đó có mapping, false khi cache trống **hoặc không xác định được**; không dùng nó như một số liệu tuyệt đối cho độ đầy của cache.

Nếu rollback sau một `invalidate()`, các mục đã bị xóa không tự xuất hiện trở lại. Với cache lớn, invalidate toàn bộ có thể gây cache stampede, tăng tải DB và làm mất nhiều kết quả còn hợp lệ, nên cân nhắc phạm vi key và chính sách phục hồi.

## 7. TransactionAwareCacheDecorator hoạt động thế nào?

Lớp Spring:

```java
import org.springframework.cache.transaction.TransactionAwareCacheDecorator;
```

Nó bao một `Cache` thật:

```java
Cache underlying = new ConcurrentMapCache("balances");
Cache transactional = new TransactionAwareCacheDecorator(underlying);
```

Khi có **Spring-managed transaction synchronization** đang active:

- `transactional.put(key, value)` → đăng ký callback thực hiện **sau commit thành công**.
- `transactional.evict(key)` → đăng ký callback **sau commit**.
- `transactional.clear()` → đăng ký callback **sau commit**.
- `transactional.putIfAbsent(...)` → thực thi **ngay** lên cache thật.
- `transactional.evictIfPresent(...)` → thực thi **ngay** lên cache thật.
- `transactional.invalidate()` → thực thi **ngay** lên cache thật.

Nếu **không có transaction synchronization**, các thao tác `put`, `evict`, `clear` chạy ngay như thông thường. Đây là một lớp trang trí bổ sung, không phải hành vi bắt buộc của mọi `CacheManager` trong Spring.

### Bảng trạng thái với transaction

| Operation trong transaction | Có thể thấy tác động trước commit? | Nếu rollback trước commit |
| --- | --- | --- |
| `put("A", 20)` qua transaction-aware decorator | Thường **chưa thấy** | Put đã hẹn bị bỏ |
| `evict("A")` | Entry cũ có thể vẫn nhìn thấy | Eviction đã hẹn bị bỏ |
| `clear()` | Các entry cũ có thể vẫn nhìn thấy | Clear đã hẹn bị bỏ |
| `putIfAbsent("B", 99)` | **Thấy ngay** nếu provider hỗ trợ immediate | Entry đã put không tự rollback |
| `evictIfPresent("B")` | **Bị xóa ngay** | Entry đã xóa không tự khôi phục |
| `invalidate()` | **Xóa toàn cache ngay** | Không tự khôi phục entry |

Bảng giả định decorator thực sự bao provider, transaction được quản lý bằng Spring và các callback/operation chạy thành công. Giao dịch **không biến cache thành một nơi tự có snapshot read-your-writes**: một `put` đã hẹn nhưng chưa commit thường không đọc thấy qua chính decorator trong transaction.

### Phân biệt với TransactionAwareCacheManagerProxy

Thay vì tự bọc từng cache:

```java
@Bean
CacheManager cacheManager() {
    CacheManager target = new ConcurrentMapCacheManager("balances");
    return new TransactionAwareCacheManagerProxy(target);
}
```

Đây là **đoạn cấu hình bean**, cần import Spring Cache Manager, ConcurrentMapCacheManager, TransactionAwareCacheManagerProxy và @Bean. `TransactionAwareCacheManagerProxy` bọc cache trả về từ manager bằng decorator transaction-aware. Khi Spring Cache interceptor truy cập các cache qua manager này, thao tác put/evict/clear có thể được hoãn đến after-commit.

Với một số provider, có cơ chế **transaction-aware riêng** thay vì cần tạo proxy; phải kiểm tra cấu hình thực tế. Nếu dùng Spring Boot, tự khai báo bean manager có thể làm thay đổi nhánh auto-configuration, nên kiểm tra manager/resolver được sử dụng.

**Không hiểu nhầm:** proxy không khiến cache trở thành một resource tham gia commit nguyên tử cùng database. Việc ghi cache có thể lỗi sau khi DB đã commit; lúc đó không còn cách tự động rollback DB chỉ vì cache put lỗi.

## 8. Ví dụ Java 17 chạy được: commit/rollback bằng JDBC thật

Thí nghiệm dùng:
- **Spring Framework 6.2.14**: cache decorator, `TransactionTemplate`, JDBC transaction manager.
- **H2 in-memory 2.3.232**: database thực sự hỗ trợ transaction và rollback trong một JVM.
- **Java 17** và **Maven**.
- **ConcurrentMapCache** làm cache local, được bọc `TransactionAwareCacheDecorator`.
- **JUnit 5** để khẳng định chính xác trạng thái DB và cache.

Không có server Redis, Spring Boot hoặc database ngoài tiến trình. Các thao tác thực hiện trực tiếp qua `Cache` API để tách rõ behavior của decorator khỏi thứ tự advice của annotation.

### 8.1. Cấu trúc

```text
cache-transaction-immediate/
├── pom.xml
└── src/
    ├── main/java/demo/cache/CacheTransactionDemo.java
    └── test/java/demo/cache/CacheTransactionDemoTest.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-transaction-immediate</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.14</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.cache.CacheTransactionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Giữ các module Spring cùng phiên bản để tránh incompatibility. Khi đưa ví dụ vào ứng dụng Boot thật, nên để BOM/parent của Boot quản lý phiên bản Spring đồng bộ.

### 8.3. src/main/java/demo/cache/CacheTransactionDemo.java

```java
package demo.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.transaction.TransactionAwareCacheDecorator;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class CacheTransactionDemo {

    private static final AtomicInteger NEXT_DB = new AtomicInteger();

    public static class Scenario {
        final JdbcTemplate jdbc;
        final TransactionTemplate transactions;
        final Cache raw;
        final Cache cache;

        public Scenario() {
            // Mỗi Scenario dùng một H2 database để tách các test.
            String url = "jdbc:h2:mem:txcache"
                    + NEXT_DB.incrementAndGet()
                    + ";DB_CLOSE_DELAY=-1";

            var dataSource = new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl(url);
            dataSource.setUsername("sa");
            dataSource.setPassword("");

            jdbc = new JdbcTemplate(dataSource);
            transactions = new TransactionTemplate(
                    new DataSourceTransactionManager(dataSource));

            jdbc.execute(
                    "CREATE TABLE accounts ("
                    + "id VARCHAR(32) PRIMARY KEY,"
                    + "balance INT NOT NULL)");

            jdbc.update(
                    "INSERT INTO accounts(id, balance) VALUES (?, ?)",
                    "A", 10);
            jdbc.update(
                    "INSERT INTO accounts(id, balance) VALUES (?, ?)",
                    "B", 10);

            raw = new ConcurrentMapCache("balances");
            cache = new TransactionAwareCacheDecorator(raw);
        }

        public int balance(String id) {
            Integer value = jdbc.queryForObject(
                    "SELECT balance FROM accounts WHERE id = ?",
                    Integer.class,
                    id);
            if (value == null) {
                throw new IllegalStateException("Missing account");
            }
            return value;
        }

        public void update(String id, int newBalance) {
            jdbc.update(
                    "UPDATE accounts SET balance = ? WHERE id = ?",
                    newBalance, id);
        }

        public Integer cached(String id) {
            return cache.get(id, Integer.class);
        }
    }

    public static void main(String[] args) {
        Scenario s = new Scenario();

        System.out.println("initial dbA=" + s.balance("A")
                + ",cacheA=" + s.cached("A"));

        // 1. put() trong transaction chỉ xuất hiện sau commit.
        s.transactions.executeWithoutResult(status -> {
            s.update("A", 20);
            s.cache.put("A", 20);
            System.out.println("inside deferred put cacheA="
                    + s.cached("A"));
        });
        System.out.println("after commit dbA=" + s.balance("A")
                + ",cacheA=" + s.cached("A"));

        // 2. put() đã hẹn không chạy nếu DB transaction rollback.
        s.transactions.executeWithoutResult(status -> {
            s.update("A", 30);
            s.cache.put("A", 30);
            status.setRollbackOnly();
        });
        System.out.println("after rollback put dbA=" + s.balance("A")
                + ",cacheA=" + s.cached("A"));

        // 3. putIfAbsent() thực hiện NGAY, ngay cả khi DB sẽ rollback.
        s.transactions.executeWithoutResult(status -> {
            s.update("B", 99);
            Cache.ValueWrapper old = s.cache.putIfAbsent("B", 99);
            System.out.println("putIfAbsent old="
                    + (old == null ? "none" : old.get()));
            System.out.println("inside immediate cacheB="
                    + s.cached("B"));
            status.setRollbackOnly();
        });
        System.out.println("after rollback immediate dbB="
                + s.balance("B") + ",cacheB=" + s.cached("B"));

        // 4. evictIfPresent() cũng không đợi commit.
        s.transactions.executeWithoutResult(status -> {
            boolean existed = s.cache.evictIfPresent("B");
            System.out.println("evictIfPresent existed=" + existed);
            status.setRollbackOnly();
        });
        System.out.println("after rollback evict cacheB="
                + s.cached("B"));

        // 5. clear() trì hoãn, rollback bỏ yêu cầu clear.
        s.cache.put("X", 1); // ngoài transaction: ghi ngay
        s.transactions.executeWithoutResult(status -> {
            s.cache.clear();
            System.out.println("inside deferred clear cacheX="
                    + s.cached("X"));
            status.setRollbackOnly();
        });
        System.out.println("after rollback clear cacheX="
                + s.cached("X"));

        // 6. invalidate() xóa NGAY dù transaction sẽ rollback.
        s.transactions.executeWithoutResult(status -> {
            s.cache.invalidate();
            System.out.println("inside immediate invalidate cacheX="
                    + s.cached("X"));
            status.setRollbackOnly();
        });
        System.out.println("after rollback invalidate cacheX="
                + s.cached("X"));
    }
}
```

**Giải thích các thành phần:**
- H2 là nguồn dữ liệu chính thức trong thí nghiệm. JDBC transaction được điều khiển bằng `DataSourceTransactionManager` và `TransactionTemplate`.
- `DriverManagerDataSource` tạo connection theo yêu cầu; Spring `JdbcTemplate` dùng connection gắn với transaction trên thread hiện tại.
- `ConcurrentMapCache` là cache thật; `TransactionAwareCacheDecorator` quyết định điều gì deferred sau commit.
- `Scenario.cached` đọc qua decorator. Với một `put` chưa commit, nó **không tự có read-your-writes**.
- `status.setRollbackOnly()` yêu cầu Spring rollback transaction đang thực thi; đây là rollback JDBC thật, không phải mô phỏng bằng cách gán lại biến.
- Cache dùng một JVM nên hành vi immediate/atomic của `ConcurrentMapCache` trong ví dụ không tự mở rộng ra mọi provider phân tán.

### 8.4. Lệnh biên dịch và chạy

Cần Java 17+, Maven và khả năng tải dependency từ Maven Central khi chạy lần đầu:

```bash
java -version
mvn -q compile exec:java
```

Các dòng **do chính chương trình in ra** (không bao gồm log Maven/Spring):

```text
initial dbA=10,cacheA=null
inside deferred put cacheA=null
after commit dbA=20,cacheA=20
after rollback put dbA=20,cacheA=20
putIfAbsent old=none
inside immediate cacheB=99
after rollback immediate dbB=10,cacheB=99
evictIfPresent existed=true
after rollback evict cacheB=null
inside deferred clear cacheX=1
after rollback clear cacheX=1
inside immediate invalidate cacheX=null
after rollback invalidate cacheX=null
```

Điều cần nhận ra:

1. **After-commit put:** bên trong transaction cache A còn null, sau commit A=20.
2. **Rollback với put:** DB không nhận giá trị 30 và cache không bị thay 30; cả hai còn 20.
3. **Rollback với putIfAbsent:** DB B trở lại 10 nhưng cache B đã mang 99. Đây là một tình trạng lệch dữ liệu do thao tác immediate.
4. **Rollback với evictIfPresent:** B bị xóa khỏi cache ngay và không tự khôi phục sau rollback.
5. **Rollback với clear:** thao tác dọn cache được hẹn nhưng không chạy; key X vẫn có giá trị 1.
6. **Rollback với invalidate:** X bị xóa ngay và không tự khôi phục.
7. Phạm vi của phép thử là **chính Cache API và decorator được cấu hình**. Nó không suy ra mọi annotation `@CachePut`, `@CacheEvict` có cùng thứ tự advice ở mọi ứng dụng nếu không xem thêm cấu hình proxy/transaction cụ thể.

Đoạn output chứng minh “hiệu lực tức thời” **không có nghĩa “an toàn với rollback”**.

## 9. Kiểm thử JUnit 5: commit, rollback, immediate và deferred

Tạo `src/test/java/demo/cache/CacheTransactionDemoTest.java`:

```java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.cache.Cache;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CacheTransactionDemoTest {

    @Test
    void putIsPublishedAfterCommitAndDiscardedOnRollback() {
        var s = new CacheTransactionDemo.Scenario();

        s.transactions.executeWithoutResult(status -> {
            s.update("A", 20);
            s.cache.put("A", 20);
            assertEquals(20, s.balance("A"));
            assertNull(s.cached("A")); // chưa commit
        });
        assertEquals(20, s.balance("A"));
        assertEquals(20, s.cached("A"));

        s.transactions.executeWithoutResult(status -> {
            s.update("A", 30);
            s.cache.put("A", 30);
            status.setRollbackOnly();
        });
        assertEquals(20, s.balance("A"));
        assertEquals(20, s.cached("A"));
    }

    @Test
    void putIfAbsentWritesImmediatelyDespiteDbRollback() {
        var s = new CacheTransactionDemo.Scenario();

        s.transactions.executeWithoutResult(status -> {
            s.update("B", 99);
            Cache.ValueWrapper previous =
                    s.cache.putIfAbsent("B", 99);

            assertNull(previous); // key B chưa tồn tại
            assertEquals(99, s.cached("B"));
            status.setRollbackOnly();
        });

        assertEquals(10, s.balance("B")); // DB đã rollback
        assertEquals(99, s.cached("B"));  // cache không rollback

        Cache.ValueWrapper previous =
                s.cache.putIfAbsent("B", 88);
        assertEquals(99, previous.get());
        assertEquals(99, s.cached("B")); // không ghi đè
    }

    @Test
    void deferredEvictAndClearDifferFromImmediateRemoval() {
        var s = new CacheTransactionDemo.Scenario();
        s.cache.put("A", 10);
        s.cache.put("B", 10);

        s.transactions.executeWithoutResult(status -> {
            s.cache.evict("A");
            assertEquals(10, s.cached("A"));
            s.cache.clear();
            assertEquals(10, s.cached("B"));
            status.setRollbackOnly();
        });
        assertEquals(10, s.cached("A"));
        assertEquals(10, s.cached("B"));

        s.transactions.executeWithoutResult(status -> {
            assertTrue(s.cache.evictIfPresent("A"));
            assertNull(s.cached("A"));
            s.cache.invalidate();
            assertNull(s.cached("B"));
            status.setRollbackOnly();
        });
        assertNull(s.cached("A"));
        assertNull(s.cached("B"));
    }
}
```

Chạy:

```bash
mvn -q test
```

Kết quả kỳ vọng: JUnit tests thành công, Maven trả exit code 0. Các test dùng H2 database **riêng biệt** qua tên tạo trong `Scenario` nên không dùng chung transaction hoặc cache giữa các phương thức test. Mã `assertNull`/`assertEquals` kiểm chứng state có thể quan sát thay vì đo thời gian hoặc phụ thuộc vào thứ tự chạy thread.

### Vì sao cần integration test chứ không chỉ unit test mock?

Nếu chỉ mock `Cache.put` và assert method đã được gọi, bạn không biết dữ liệu đã xuất hiện **trước** hay **sau** transaction commit. Ở đây, JDBC manager chạy transaction thực; decorator đăng ký synchronization thật; H2 rollback thật; cache local cho phép đọc trực tiếp state. Bài test vẫn không thay thế phép thử với Redis, Caffeine, JPA transaction manager hoặc nhiều instance trong sản phẩm.

## 10. Đừng dùng putIfAbsent như một giao dịch hai pha

Một nhầm lẫn nguy hiểm:

```text
begin DB transaction
  nếu cache.putIfAbsent(orderId, "processing") == null:
      INSERT order
commit DB
```

Nếu phần INSERT hoặc commit DB thất bại:
- Cache vẫn có `orderId -> processing`.
- Lần retry sau nhìn thấy marker và có thể bị từ chối, dù DB không có đơn hàng hợp lệ.
- Nếu không đặt TTL/giải pháp phục hồi, trạng thái sai có thể tồn tại rất lâu.

Thậm chí khi putIfAbsent thực sự atomic trong cache, nó chỉ bảo đảm **không ghi đè entry cùng key tại điểm cache**, không bảo đảm DB đã commit hoặc lệnh kinh doanh thành công. Với nghiệp vụ tài chính, thanh toán, gửi hàng hoặc inventory, hãy dùng:
- Unique constraint và transaction ở DB cho nguồn chuẩn.
- Bảng idempotency với trạng thái, khóa/phiên bản và timeout rõ ràng.
- Outbox pattern hoặc phát sự kiện sau commit khi đồng bộ bất đồng bộ cần tin cậy.
- Redis lock hoặc distributed coordination được thiết kế riêng nếu thật sự cần, có TTL, fencing token và xử lý chủ sở hữu; không coi một cache value tạm là khóa bền vững.

`putIfAbsent` hữu ích như một thao tác cache, **không tự trở thành khóa nghiệp vụ có độ bền và tính nhất quán cao**.

## 11. Đọc lại sau put: read-your-writes và giới hạn của deferred operations

Nếu bên trong một transaction:

```java
cache.put("A", 20);
Integer sameTransactionRead = cache.get("A", Integer.class);
```

Với transaction-aware decorator, giá trị `sameTransactionRead` có thể vẫn là **giá trị cũ hoặc null**, bởi `put` chưa thực thi lên store. Điều này không phải bug của Spring mà là kết quả trực tiếp của defer đến after-commit.

Ngược lại:

```java
cache.putIfAbsent("B", 99);
Integer immediateRead = cache.get("B", Integer.class);
```

Trên provider local có immediate write, `immediateRead` có thể là 99 ngay. Chính vì khác biệt đó, code trong một transaction không nên dựa vào cache để đọc lại dữ liệu **chưa commit**, nhất là khi business logic cần kiểm tra trạng thái đang cập nhật ở DB.

Nếu cần đọc state của transaction, hãy đọc qua repository/JPA EntityManager gắn với transaction, hoặc giữ một giá trị local phù hợp. Cache thường dùng để **tái sử dụng dữ liệu đã được xác nhận có thể công bố**, không thay cho “transactional workspace” của DB.

## 12. Không phải mọi triển khai đều bảo đảm giống nhau

### 12.1. Atomicity của putIfAbsent

JavaDoc Spring cho phép default implementation dùng `get` rồi `put`, nên có thể **không atomic**. Với cache provider chuyên dụng, kiểm tra:
- Có sử dụng native operation thực sự atomic không?
- Atomicity chỉ trong một JVM hay trên server phân tán?
- Nếu có replication, dữ liệu được đọc từ replica hay primary?
- Có TTL/eviction làm key biến mất ngay sau thao tác không?
- Nếu cache bị lỗi, exception có được trả về hay bị `CacheErrorHandler` che đi?

Không sử dụng kết quả một test với `ConcurrentMapCache` để khẳng định atomicity của cache tự viết hoặc một hệ thống phân tán.

### 12.2. Immediate visibility của evictIfPresent và invalidate

Giao diện mô tả kỳ vọng “key không còn nhìn thấy ngay” hoặc “mọi entry không còn nhìn thấy ngay”. Provider và đặc biệt cache decorator **được khuyến khích thực hiện semantics này**. Tuy nhiên nếu provider ngoài tiến trình có replication, asynchronous invalidation hoặc adapter custom chưa hỗ trợ đúng, cần test hậu điều kiện theo phạm vi client thực tế.

Các giá trị boolean không đủ để chứng minh đồng bộ toàn cluster. Với `evictIfPresent`, false có thể do không tìm thấy trước đó **hoặc không xác định được trạng thái cũ**. Với `invalidate` cũng tương tự đối với toàn cache.

### 12.3. @Cacheable(sync = true) không đồng nghĩa putIfAbsent

`@Cacheable(sync = true)` phối hợp **việc tính kết quả cho key bị miss** qua `Cache.get(key, Callable)` khi provider hỗ trợ. Nó không phải `putIfAbsent` của DB transaction và không cho phép suy ra exactly-once business operation.

`@Cacheable(sync=true)` còn có những giới hạn annotation riêng (một cache, không `unless`, không ghép operation khác trên cùng method). Chọn `sync=true` để giảm loader duplicate chứ không để thay transaction/rollback.

### 12.4. Cache transaction-aware không tự sửa trình tự advice

Khi dùng đồng thời `@Transactional` và `@CachePut`/`@CacheEvict`, thứ tự advisor và manager configuration ảnh hưởng mốc thao tác. Nếu cache manager không bọc transaction-aware, cache update có thể chạy **trước khi commit**. Nếu cache được bọc đúng, put/evict/clear sẽ đăng ký after-commit khi có active synchronization; nhưng thao tác immediate không được chuyển thành deferred.

Test phải chạy qua Spring proxy và manager thật, kiểm tra:
- Đường gọi nào mở transaction?
- Cache manager mà interceptor thật sự sử dụng có transaction-aware không?
- Put/evict áp dụng lúc nào?
- Sau rollback, cache còn entry hay không?
- Một request khác có thể thấy stale value trong khoảng transaction đang mở không?

## 13. Chiến lược an toàn khi DB và cache cần nhất quán

### Cách A — Commit DB trước, rồi invalidate cache

Cho nhiều hệ thống cache-aside, cách dễ hiểu là cập nhật nguồn chuẩn trong DB, sau đó **invalidating key liên quan khi commit thành công**. Có thể dùng transaction synchronization sau commit hoặc một cơ chế event/outbox để phối hợp.

```text
begin DB transaction
  UPDATE product
commit thành công
  evict cache(productId)
lần đọc sau
  MISS -> đọc DB đã commit -> cache lại
```

Nhưng đây cũng không phải atomic hoàn hảo:
- Sau commit và trước eviction có một khoảng ngắn cache còn stale.
- Nếu process chết sau DB commit trước lúc invalidate, cache có thể không được xóa.
- Nếu cần độ tin cậy cao, sử dụng outbox/event retry/version hoặc cơ chế invalidation bền vững.

### Cách B — Put canonical result sau commit

Nếu lệnh cập nhật có giá trị canonical đã được DB xác nhận, có thể put giá trị mới sau commit. Cần đảm bảo giá trị được put phản ánh đúng transaction đã commit và không bị các request khác ghi đè theo thứ tự sai.

### Cách C — Khi cần immediate, kiểm soát rủi ro rollback

Nếu thật sự cần `evictIfPresent` hoặc `invalidate` ngay, phải chấp nhận cache có thể biến mất dù transaction rollback; đó thường là **chi phí tải lại**, nhưng cũng có thể tạo race khi request khác nạp dữ liệu cũ trong lúc DB chưa commit.

Nếu dùng `putIfAbsent` ngay để đánh dấu một trạng thái tạm thời, phải có chiến lược:
- Xóa marker khi rollback/timeout.
- TTL ngắn, ownership/token và không xóa marker của chủ sở hữu khác.
- Nguồn chuẩn trong DB vẫn quyết định kết quả nghiệp vụ cuối cùng.
- Kiểm thử retry, crash, concurrent requests và transaction rollback.

### Cách D — Không yêu cầu cùng lúc “atomic cache insert ngay” và “rollback như DB” nếu provider không hỗ trợ

Một API muốn *vừa* trả kết quả đặt key ngay *vừa* hoãn tác động tới sau commit có mâu thuẫn nội tại. Thay đổi thiết kế có thể cần:
- Chuyển việc quyết định trùng lặp vào DB với unique key.
- Dùng outbox và xử lý sau commit.
- Tách read model/cache khỏi write model.
- Thiết kế một transaction protocol riêng nếu các hệ thống thực sự phải đồng bộ chặt.

## 14. Bảng lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Kiểm tra/xử lý |
| --- | --- | --- |
| Trong transaction gọi `put` rồi `get` vẫn miss | Decorator hoãn put đến after-commit | Kiểm tra TransactionAwareCacheDecorator và đừng kỳ vọng read-your-writes |
| Sau DB rollback, cache vẫn có marker | `putIfAbsent` thực thi ngay | Cleanup và chính sách idempotency ở nguồn chuẩn |
| Sau rollback, một key cache mất | `evictIfPresent` thực thi ngay | Hiểu immediate không có rollback; kiểm tra race/eviction |
| Clear trong tx rồi get vẫn thấy dữ liệu | `clear` deferred | Nếu thực sự cần immediate, cân nhắc `invalidate` và rủi ro rollback |
| `evictIfPresent` trả false dù nghĩ đã có mục | Cache không biết chắc prior presence hoặc key sai | Kiểm tra key/provider và hậu điều kiện truy cập |
| Hai thread cùng “thắng” put-if-absent | Provider custom không atomic hoặc phạm vi phân tán khác | Xác minh native atomic operation và test concurrency |
| Cả DB và cache sai sau cập nhật | Cache put quá sớm, key sai hoặc after-commit callback lỗi | Kiểm tra transaction boundary, error handling, version |
| Dữ liệu cache không đồng bộ giữa nodes | Local cache riêng hoặc replica propagation | Kiểm tra topology, invalidation và consistency model |
| Dùng `@Cacheable(sync=true)` rồi nghĩ đã khóa nghiệp vụ | Đồng bộ loader cache khác transaction/idempotency | Chuyển yêu cầu đúng một lần sang nguồn chuẩn |
| `@Transactional` có nhưng cache vẫn cập nhật ngay | CacheManager không transaction-aware hoặc dùng immediate API | Xác minh manager thực tế và operation được gọi |

## 15. Checklist thiết kế

1. **Nguồn chuẩn** có phải là DB hay cache? Ai chịu trách nhiệm quyết định giao dịch thành công?
2. Có một transaction synchronization Spring thực sự active khi thao tác cache diễn ra không?
3. Cache được bọc `TransactionAwareCacheDecorator` hoặc manager transaction-aware chưa?
4. Lời gọi là `put`/`evict`/`clear` hay `putIfAbsent`/`evictIfPresent`/`invalidate`?
5. Caller có bắt buộc quan sát tác động ngay không? Nếu không, ưu tiên cơ chế sau commit theo nhu cầu.
6. Nếu put-if-absent là điểm quyết định concurrency, provider có **atomic** thực sự trên phạm vi mong muốn không?
7. Nếu cache lưu null, đã phân biệt `ValueWrapper` với `get() == null` chưa?
8. Khi DB rollback, cache có thể bị ghi hoặc xóa trước đó không? Có cleanup/retry/TTL phù hợp không?
9. Khi cache write **sau commit** bị lỗi, có đường phục hồi hoặc invalidation lại không?
10. Key có đủ phân biệt tenant, role, locale và các chiều làm thay đổi kết quả không?
11. Test đã xác nhận DB **và** cache trước commit, sau commit và sau rollback chưa?
12. Hệ thống có nhiều instance/replica cần kiểm thử cache visibility xuyên node không?
13. Có phân biệt cache local, Redis hay provider tự viết? Không khái quát từ implementation thử nghiệm.
14. Có thống nhất API với chiến lược transaction khi refactor từ annotation sang gọi Cache trực tiếp không?

## 16. Bài tập tự luyện

**Câu 1.** Với `TransactionAwareCacheDecorator` và transaction đang mở, sau `cache.put("A", 10)` thì `cache.get("A")` có chắc trả 10 ngay không?  
**Đáp án:** Không. Put có thể được hẹn đến after-commit, do đó trong transaction vẫn thấy old value/miss.

**Câu 2.** `putIfAbsent("A", 10)` trả null. Có thể suy ra JDBC transaction đã commit không?  
**Đáp án:** Không. Chỉ thể hiện cache chưa có entry trước put và value đã được liên kết theo provider. DB có thể đang chưa commit hoặc sẽ rollback.

**Câu 3.** Vì sao `cache.get(key)` rồi `cache.put(key, value)` không thay thế được atomic `putIfAbsent` khi có nhiều thread?  
**Đáp án:** Giữa check và put có cửa sổ race; nhiều thread có thể cùng thấy miss rồi đều put.

**Câu 4.** Có phải mọi implementation của Spring `Cache.putIfAbsent` đều atomic không?  
**Đáp án:** Không. Default implementation có thể chia thành hai bước. Cần kiểm tra provider; ConcurrentMapCache hỗ trợ atomic trong phạm vi JVM ở ví dụ.

**Câu 5.** Lệnh nào cho hậu điều kiện xóa một key ngay: `evict` hay `evictIfPresent`?  
**Đáp án:** `evictIfPresent` được thiết kế cho immediate removal; `evict` có thể deferred/asynchronous.

**Câu 6.** Lệnh nào dùng để yêu cầu toàn cache vô hình ngay: `clear` hay `invalidate`?  
**Đáp án:** `invalidate`; `clear` có thể deferred/asynchronous.

**Câu 7.** `evictIfPresent` trả false có chứng minh chắc chắn key không tồn tại trước đó không?  
**Đáp án:** Không. False cũng có thể có nghĩa implementation không xác định được prior presence.

**Câu 8.** DB transaction rollback sau `putIfAbsent("B", 99)`, điều gì xảy ra với cache?  
**Đáp án:** Cache entry được put tức thời không tự rollback. Bản thử nghiệm cho thấy DB B về 10 nhưng cache B vẫn có 99.

**Câu 9.** Vì sao transaction-aware không phải XA cache+DB?  
**Đáp án:** Nó hoãn một số thao tác tới sau commit DB, chứ không tạo cơ chế commit/rollback nguyên tử giữa hai tài nguyên.

## Tài liệu chính thức

- [Spring Framework — Cache interface JavaDoc (put, putIfAbsent, evict, evictIfPresent, clear, invalidate)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework — TransactionAwareCacheDecorator JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html)
- [Spring Framework — TransactionAwareCacheManagerProxy JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)

**Ghi nhớ:** `putIfAbsent` được thiết kế để có hiệu lực ngay và trả thông tin mapping cũ, nhưng tính atomic còn phụ thuộc provider; nó **không thể được trì hoãn theo transaction** trong `TransactionAwareCacheDecorator`. `evictIfPresent` và `invalidate` cũng mang semantics tức thời. Trái lại, `put`, `evict` và `clear` có thể hoãn tới after-commit. Khi transaction DB rollback, **cache immediate operations không tự rollback**: phải thiết kế tính nhất quán, retry và kiểm thử phù hợp, thay vì mặc định mọi thao tác cache là một phần của giao dịch database.