# Đối tượng bất biến và công bố dữ liệu an toàn trong Spring Framework

Một bean `@Service` có thể chỉ có một instance trong Spring container nhưng được nhiều request, tác vụ `@Async` hoặc job `@Scheduled` gọi đồng thời. Câu hỏi then chốt không chỉ là “bean có `singleton` không?”, mà còn là: **trạng thái nào được chia sẻ, trạng thái đó có thể thay đổi không, và thread đọc có chắc nhìn thấy dữ liệu đã khởi tạo hoặc cập nhật đúng cách không?**

Bài học này tập trung vào **đối tượng bất biến (immutable object)** và **công bố dữ liệu an toàn (safe publication)** khi thiết kế trạng thái bean trong Spring. Nền tảng lý thuyết là **Java Memory Model (JMM)**, đặc biệt các quy tắc `happens-before` và ngữ nghĩa của trường `final`. Mục tiêu thực hành là xây dựng bean có state dễ suy luận, cập nhật an toàn và tránh phụ thuộc vào may rủi của việc thread chạy theo thứ tự nào.

## 1. Bean scope không đồng nghĩa thread safety

Spring mặc định dùng scope `singleton`: **một đối tượng cho một bean definition trong một IoC container**. Nhiều controller, request và worker có thể tham chiếu cùng bean đó. Đây không phải “một instance duy nhất trong toàn bộ JVM” và càng không bảo đảm trạng thái thay đổi bên trong bean tự động thread-safe.

Ví dụ một service sai:

```java
import org.springframework.stereotype.Service;

@Service
public class UnsafeGreetingService {
    private String lastName;

    public String greet(String name) {
        lastName = name;
        return "Hello, " + lastName;
    }
}
```

Giả sử request A gọi `greet("An")`, request B gọi `greet("Binh")`. Nếu A gán `lastName = "An"`, B gán `lastName = "Binh"` rồi A mới đọc, A có thể trả lời `Hello, Binh`. Đây là **race condition** trên instance field chia sẻ. Không nên dựa vào việc một test đơn luồng “chạy đúng” để suy ra ứng dụng web an toàn.

Phiên bản tốt hơn cho dữ liệu chỉ phục vụ một lời gọi:

```java
@Service
public class GreetingService {
    public String greet(String name) {
        String currentName = name; // Biến local, riêng cho mỗi lời gọi
        return "Hello, " + currentName;
    }
}
```

Không có lý do nghiệp vụ để giữ tên người dùng ở instance field. **Giữ request state trong biến local** là cách đơn giản nhất giảm shared mutable state. Nếu phải giữ trạng thái lâu dài, lựa chọn cấu trúc dữ liệu và cơ chế công bố/cập nhật là phần trách nhiệm của ứng dụng.

## 2. Immutable object là gì?

Một đối tượng **bất biến** có trạng thái quan sát được không thay đổi sau khi khởi tạo hợp lệ. Khi nhiều thread cùng đọc một đối tượng thực sự bất biến, chúng không cần khóa chỉ để bảo vệ các thao tác đọc.

Trong Java, một thiết kế immutable điển hình có các đặc điểm:

1. Toàn bộ trạng thái logic được xác lập khi xây dựng đối tượng; sau đó không có phương thức nào sửa nó.
2. Dùng trường `private final` khi thích hợp và không để tham chiếu `this` thoát ra ngoài trong quá trình constructor chạy.
3. Không giữ trực tiếp tham chiếu đến dữ liệu mutable do caller sở hữu nếu caller còn sửa được; dùng **defensive copy**.
4. Không trả trực tiếp cấu trúc mutable bên trong cho caller sửa; dùng bản sao hoặc cấu trúc immutable.
5. Kiểm soát tính kế thừa nếu subclass có thể thêm hành vi khiến hợp đồng bất biến bị phá vỡ, chẳng hạn dùng `final class` hoặc `record` cho value object phù hợp.

Ví dụ **shallow immutability** không đủ:

```java
final class WeakPolicy {
    private final java.util.Map<String, String> values;

    WeakPolicy(java.util.Map<String, String> values) {
        this.values = values; // Giữ tham chiếu mutable của caller
    }

    java.util.Map<String, String> values() {
        return values; // Trả lại cùng Map mutable
    }
}
```

`final` ở đây chỉ ngăn **gán lại trường `values`**; nó không ngăn `values.put(...)` thay đổi nội dung của Map. Một thread đang đọc có thể đụng race với thread khác sửa Map, và `HashMap` không được thiết kế cho truy cập đọc/ghi đồng thời thiếu phối hợp.

Thiết kế tốt hơn khi key/value đều immutable:

```java
import java.util.Map;
import java.util.Objects;

public record Policy(String name, Map<String, String> values) {
    public Policy {
        Objects.requireNonNull(name, "name");
        values = Map.copyOf(Objects.requireNonNull(values, "values"));
    }
}
```

Khi tạo `new Policy("standard", originalMap)`, constructor chụp một bản sao bất biến của các entry; thay đổi `originalMap` sau đó không thay đổi `Policy`. Accessor `values()` trả Map không cho sửa nội dung bằng `put` hoặc `remove`.

**Lưu ý về sao chép nông:** `Map.copyOf` ngăn sửa cấu trúc Map và tách trạng thái Map khỏi các thao tác thay đổi trên Map gốc, nhưng **không tự biến các object value thành immutable**. Với `Map<String, List<String>>`, một `List` mutable bên trong vẫn có thể bị sửa từ tham chiếu khác; phải sao chép từng value hoặc dùng mô hình bất biến đến tận các lớp dữ liệu cần bảo vệ. `List.copyOf` và `Set.copyOf` cũng có giới hạn tương tự. Các phương thức `copyOf` từ chối phần tử null không hợp lệ theo hợp đồng của chúng.

### Record và final không phải “bùa thread-safe”

- `record Person(String name, List<String> tags)` tự sinh các field `final`, nhưng `tags` có thể vẫn là List mutable; record **không tự động deep copy**.
- `final List<String> tags = new ArrayList<>()` là tham chiếu ổn định tới một danh sách có thể thay đổi.
- `Collections.unmodifiableList(source)` tạo **view không sửa được qua view**, nhưng nếu thread khác sửa `source`, nội dung view vẫn thay đổi. Muốn snapshot độc lập, ưu tiên `List.copyOf(source)` khi các phần tử đáp ứng yêu cầu.
- `String`, `LocalDate`, `BigDecimal` là những ví dụ đối tượng bất biến hữu ích cho value object. Với mảng `byte[]`, `Date` cũ hoặc DTO mutable, cần cách ly dữ liệu.

Hợp đồng quan trọng là **không có đường nào cho thread khác thay đổi trạng thái quan sát được**, chứ không chỉ kiểm tra số lần xuất hiện của từ khóa `final`.

## 3. Công bố một đối tượng là gì?

**Publication (công bố)** là lúc một tham chiếu tới object trở nên truy cập được từ thread khác. Ví dụ: đưa vào field của singleton bean, cache dùng chung, registry static, queue hoặc Future.

Hai câu hỏi khác nhau cần phân biệt:

- **Đối tượng có được khởi tạo hoàn chỉnh không?** Constructor đã thiết lập đúng state và bảo vệ phần dữ liệu mutable hay chưa?
- **Thread khác nhìn thấy những ghi dữ liệu nào?** Java Memory Model có một quan hệ đồng bộ hóa phù hợp giữa bên ghi/bên công bố và bên đọc hay không?

Nếu một thread ghi các field rồi gán object vào một biến chia sẻ thông thường, thread khác đọc biến đó **không tự động có bảo đảm visibility** đối với mọi lần ghi trước đó. Khi thiếu quan hệ `happens-before`, chương trình có thể xuất hiện stale read, giá trị mặc định hoặc quan sát không nhất quán; kết quả không ổn định, nên không thể dựa vào “máy tôi luôn ra đúng”.

### 3.1. Happens-before là bảo đảm gì?

Quan hệ `happens-before` (viết tắt HB) xác định thứ tự quan sát mà JMM bảo đảm. Nếu thao tác ghi W `happens-before` thao tác đọc R, các tác động của W được bảo đảm có hiệu lực theo các quy tắc memory model tại R, trừ khi có các ghi khác hợp lệ xen vào.

Một số cơ chế tạo quan hệ HB quen thuộc:

- **Cùng thread:** các thao tác đứng trước trong thứ tự chương trình xảy ra HB các thao tác sau.
- **`synchronized`:** hành động unlock một monitor xảy ra HB hành động lock tiếp theo của *cùng monitor*.
- **`volatile`:** ghi vào một biến volatile xảy ra HB các lần đọc tiếp theo của chính biến đó theo thứ tự đồng bộ hóa.
- **`Thread.start()`:** hành động trước lúc gọi `start()` xảy ra HB các hành động của thread được start; hành động của thread kết thúc HB việc thread khác hoàn thành `join()` trên nó.
- **java.util.concurrent:** các cấu trúc như `BlockingQueue`, `ConcurrentHashMap`, `ExecutorService` và `Future.get()` có các memory-consistency effects được mô tả trong hợp đồng API.

HB **không yêu cầu mỗi thread chạy lần lượt**. Nó là ràng buộc về khả năng quan sát dữ liệu, không phải một lời hứa về thời gian chạy nhanh/chậm hay thứ tự log toàn hệ thống.

### 3.2. Vai trò đặc biệt của `final`

JMM có quy tắc riêng cho **final-field semantics**. Với đối tượng được xây dựng đúng cách, khi constructor kết thúc sẽ có “freeze” cho các final field được thiết lập trong quá trình khởi tạo. Thread khác nắm được tham chiếu đến object đã xây dựng đúng có bảo đảm mạnh hơn khi quan sát giá trị các final field, dù cách truyền tham chiếu chưa được đồng bộ hóa theo cách thông thường.

Ví dụ:

```java
final class HostInfo {
    final String host;
    final int port;

    HostInfo(String host, int port) {
        this.host = host;
        this.port = port;
    }
}
```

Các final field của `HostInfo` có ngữ nghĩa khởi tạo được JMM bảo vệ nếu object được xây dựng đúng và `this` không thoát ra trong constructor. Nhưng cần nhớ:

1. Điều này **không bảo đảm thread khác sẽ nhìn thấy ngay tham chiếu mới** nếu biến dùng để công bố tham chiếu bị đọc/ghi racy.
2. Nếu final field trỏ tới object mutable, các **sửa đổi về sau** của object đó không được final-field semantics tự động bảo vệ.
3. Final field không thay thế synchronization cho protocol cập nhật, phối hợp nhiều field hoặc shared mutable state khác.
4. Không được công bố `this` trong constructor, ví dụ ghi nó vào registry static, đăng ký listener gọi ngược ngay hoặc start task có thể truy cập object trước khi constructor hoàn tất.

**Kết luận:** final field giúp bảo đảm trạng thái khởi tạo của object immutable được đọc đúng; safe publication vẫn là cách rõ ràng để chuyển giao tham chiếu, bảo đảm thời điểm nhìn thấy cập nhật và xử lý các object không bất biến hoàn toàn.

## 4. Những cách công bố dữ liệu an toàn

### 4.1. Khởi tạo static

Class initialization có cơ chế đồng bộ hóa do JVM quản lý. Dữ liệu tạo khi khởi tạo class được công bố an toàn theo quy tắc class initialization.

```java
final class Defaults {
    static final Policy POLICY =
            new Policy("default", java.util.Map.of("mode", "safe"));

    private Defaults() {}
}
```

Mẫu này hợp với cấu hình cố định dùng trong class. Không giải quyết nhu cầu thay đổi snapshot lúc runtime.

### 4.2. Truyền tham chiếu qua `volatile`

`volatile` phù hợp khi một biến đại diện **một giá trị/snapshot độc lập**, writer thay cả tham chiếu và reader đọc một lần:

```java
import java.util.Map;

final class PolicyStore {
    private volatile Policy current = new Policy("v1", Map.of("level", "basic"));

    public Policy snapshot() {
        return current;            // volatile read
    }

    public void replace(Policy next) {
        current = java.util.Objects.requireNonNull(next); // volatile write
    }
}
```

Giả sử một thread gọi `replace(new Policy(...))`, thread khác đọc tham chiếu mới qua `snapshot()`, nó nhìn thấy state được khởi tạo trước phép ghi volatile. Mỗi reader có thể tiếp tục sử dụng snapshot cũ mà không bị thay đổi bên dưới; một reader đến trước hoặc sau một lượt thay thế có thể thấy **phiên bản khác nhau**, nhưng không thấy “nửa Map cũ, nửa Map mới” bên trong một snapshot bất biến.

**Giới hạn:** `volatile` chỉ bảo đảm visibility và tính nguyên tử cho **một lần đọc/ghi tham chiếu**, không biến chuỗi thao tác “đọc → sửa → ghi” thành một thao tác atomic. Nếu hai writer đồng thời làm `current = modify(current)`, một cập nhật có thể bị ghi đè.

### 4.3. `synchronized` với cùng lock

`synchronized` thiết lập cả loại trừ đồng thời và visibility qua lock/unlock:

```java
final class LockedCounter {
    private long count;

    public synchronized void increment() {
        count++;
    }

    public synchronized long get() {
        return count;
    }
}
```

Hai method phải dùng cùng monitor (ở đây là `this`) để bảo vệ chung state. `synchronized` là lựa chọn đơn giản cho invariant có nhiều bước hoặc nhiều field. Đừng trả ra ngoài một object mutable nội bộ rồi tiếp tục tin rằng khóa ở getter đã bảo vệ mọi thay đổi sau đó.

### 4.4. Handoff qua cấu trúc concurrent

Đưa dữ liệu vào `BlockingQueue` và lấy từ queue, hoàn thành `Future` rồi tiêu thụ qua `get()`, hay thực hiện các thao tác thích hợp với concurrent collection đều là những cách **chuyển giao/công bố an toàn** theo hợp đồng API cụ thể. Ví dụ producer xây dựng job object xong rồi `queue.put(job)`; consumer `queue.take()` nhận job với các ghi trước lúc đưa vào queue đã được công bố phù hợp.

Cần tách **hành vi thread-safe của container** khỏi hành vi của element: `ConcurrentHashMap<String, MutableReport>` không khiến việc sửa từng `MutableReport` trở nên an toàn. Dữ liệu lấy từ map vẫn phải immutable hoặc có cơ chế đồng bộ hóa riêng nếu còn thay đổi.

### 4.5. `AtomicReference` và thay thế snapshot bằng CAS

Khi có nhiều writer cùng cập nhật từ state cũ, dùng `AtomicReference<Snapshot>` với `updateAndGet` hoặc vòng lặp `compareAndSet`. Cơ chế CAS có thể thử lại khi một writer khác cập nhật trước; nó tránh việc hai writer độc lập đọc cùng state cũ rồi cùng ghi đè một kết quả.

```text
State v4
  ├── Writer A muốn thêm cờ A ──┐
  └── Writer B muốn thêm cờ B ──┼── CAS: một writer thắng
                                └── Writer còn lại đọc snapshot mới, tính lại và CAS
State cuối: chứa cả hai cập nhật (nếu quy tắc merge đúng)
```

Điều kiện: hàm cập nhật phải **không có side effect không lặp lại được**, vì `updateAndGet` có thể gọi lại hàm khi tranh chấp. Không gửi email, ghi database hay gọi dịch vụ bên ngoài ngay trong lambda cập nhật.

## 5. Java 17+ runnable: immutable snapshot + safe publication + nhiều writer

Ví dụ này xây dựng snapshot với `record`, sao chép phòng vệ bằng `Map.copyOf` và dùng `AtomicReference.updateAndGet` để 4 worker cùng tăng bộ đếm mà không làm mất cập nhật. Snapshot đã đọc trước đó không bị thay đổi.

Lưu là **ImmutablePublicationDemo.java**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

public class ImmutablePublicationDemo {
    public record Snapshot(int version, Map<String, Integer> counts) {
        public Snapshot {
            counts = Map.copyOf(counts);
        }

        public int count(String key) {
            return counts.getOrDefault(key, 0);
        }
    }

    private static final class Store {
        private final AtomicReference<Snapshot> current =
                new AtomicReference<>(new Snapshot(0, Map.of("views", 0)));

        Snapshot read() {
            return current.get();
        }

        void increment() {
            current.updateAndGet(old -> {
                Map<String, Integer> copy = new HashMap<>(old.counts());
                copy.merge("views", 1, Integer::sum);
                return new Snapshot(old.version() + 1, copy);
            });
        }
    }

    public static void main(String[] args) throws Exception {
        Map<String, Integer> input = new HashMap<>();
        input.put("views", 7);
        Snapshot copy = new Snapshot(5, input);
        input.put("views", 999);
        System.out.println("defensive copy: " + copy.count("views"));

        Store store = new Store();
        Snapshot before = store.read();

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> tasks = new ArrayList<>();

            for (int worker = 0; worker < 4; worker++) {
                tasks.add(pool.submit(() -> {
                    for (int i = 0; i < 100; i++) {
                        store.increment();
                    }
                }));
            }

            for (Future<?> task : tasks) {
                task.get();
            }
        } finally {
            pool.shutdown();
        }

        Snapshot after = store.read();
        System.out.println("before: " + before.version()
                + "/" + before.count("views"));
        System.out.println("after: " + after.version()
                + "/" + after.count("views"));
        System.out.println("old snapshot remains: " + before.count("views"));
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac ImmutablePublicationDemo.java
java ImmutablePublicationDemo
```

**Stdout xác định:**

```text
defensive copy: 7
before: 0/0
after: 400/400
old snapshot remains: 0
```

Vì sao kết quả đúng?

1. `Snapshot` là record chứa số `int` và Map có key `String`, value `Integer`, đều bất biến; compact constructor dùng `Map.copyOf` để ngăn bên ngoài thay đổi Map snapshot. Bản `copy` vẫn giữ 7 dù `input` bị đổi thành 999.
2. `Store.read()` đọc một tham chiếu hiện tại qua `AtomicReference.get()`; mỗi snapshot là **một trạng thái hoàn chỉnh**.
3. Mỗi `increment()` dựng Map mới, tạo Snapshot mới rồi `updateAndGet` thực hiện cập nhật atomic với CAS/retry. Không chia sẻ Map đang bị sửa giữa các thread.
4. Bốn worker thực hiện tổng cộng 400 lần tăng. `Future.get()` bảo đảm task đã hoàn tất, đồng thời cung cấp quan hệ memory consistency thích hợp trước khi main đọc kết quả.
5. Snapshot `before` vẫn có version 0 và `views=0`: object cũ không bị sửa. Các writer chỉ thay tham chiếu hiện tại tới snapshot mới.

Lưu ý: **CAS có thể gọi lại lambda** nhiều lần; mọi thao tác bên trong lambda ở đây chỉ tính toán bộ nhớ cục bộ và tạo object mới. Cách này không tự loại bỏ các yêu cầu nghiệp vụ về persistence, transaction hoặc độ bền dữ liệu sau restart.

## 6. Đưa mô hình snapshot vào Spring singleton bean

### 6.1. Bean đọc nhiều, cập nhật cấu hình trong runtime

Ví dụ service quản lý feature flags. Đọc một snapshot immutable, ghi bằng CAS, giữ phiên bản để quan sát thay đổi. Đây là fragment cho dự án Spring Framework 6+/Spring Boot 3+, cần dependency Spring và nằm trong **src/main/java/com/example/demo/FeatureFlagService.java**; không chạy bằng `javac` độc lập nếu thiếu Spring trên classpath.

```java
package com.example.demo;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Service;

@Service
public class FeatureFlagService {
    private final AtomicReference<Flags> current =
            new AtomicReference<>(new Flags(0, Map.of()));

    public boolean enabled(String name) {
        Objects.requireNonNull(name, "name");
        Flags snapshot = current.get();
        return snapshot.values().getOrDefault(name, false);
    }

    public Flags snapshot() {
        return current.get();
    }

    public void setFlag(String name, boolean enabled) {
        Objects.requireNonNull(name, "name");
        current.updateAndGet(old -> {
            Map<String, Boolean> next = new HashMap<>(old.values());
            next.put(name, enabled);
            return new Flags(old.version() + 1, next);
        });
    }

    public record Flags(long version, Map<String, Boolean> values) {
        public Flags {
            values = Map.copyOf(Objects.requireNonNull(values, "values"));
        }
    }
}
```

Một controller/request thread có thể gọi `enabled("newCheckout")` trong khi scheduler/admin thread gọi `setFlag(...)`. Mỗi lần đọc lấy **một snapshot nhất quán**; không có Map đang bị sửa tại chỗ để gây race. Hai writer cập nhật **hai tên cờ khác nhau** không đánh rơi cập nhật do CAS phải tính lại từ state mới khi tranh chấp. Tuy nhiên, hai writer cùng đặt **một cờ** sang giá trị khác nhau vẫn có kết quả “lần cập nhật nào linearize sau cùng thắng”; đó là **quy tắc nghiệp vụ**, không phải lỗi JMM.

Điểm cần chú ý:

- Có thể tiêm `FeatureFlagService` vào nhiều controller và job vì một instance singleton phục vụ truy cập đồng thời; thread safety đến từ immutable snapshots và AtomicReference, không đến từ `@Service`.
- Mỗi lần cập nhật copy toàn bộ Map, có chi phí bộ nhớ và CPU tỷ lệ với kích thước Map. Phù hợp **read-heavy/write-rarely** như feature flags/cấu hình; nếu ghi liên tục với dữ liệu rất lớn, cần đánh giá mô hình khác như `ConcurrentHashMap`, phân vùng dữ liệu, event stream hoặc lock có phạm vi hợp lý.
- Nếu cặp `values + version` phải luôn cùng snapshot, cho chúng vào **cùng một object Flags** như trên. Hai field volatile độc lập không bảo đảm các lần đọc tạo thành một cặp nhất quán.
- Expose `snapshot()` ở đây vẫn an toàn vì bản thân `Flags` immutable với `String/Boolean`. Nếu value mutable, phải sửa chiến lược copy.
- Khi update gắn với database, event hoặc network, không thực hiện side effect trong lambda CAS; thực hiện sau khi cập nhật thành công và phải thiết kế riêng semantics khi bị thất bại.

### 6.2. Constructor injection + final dependency

Một Spring singleton bean khác có thể không có mutable state:

```java
import org.springframework.stereotype.Service;

@Service
public class PriceService {
    private final TaxPolicy taxPolicy;

    public PriceService(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
    }

    public long totalWithTax(long amount) {
        return taxPolicy.apply(amount);
    }
}
```

Đây là **fragment** minh họa DI; `TaxPolicy` là một abstraction giả định đã được định nghĩa ở nơi khác. Field `final` bảo đảm `PriceService` không thay tham chiếu dependency sau constructor; việc `PriceService` có thread-safe hay không còn phụ thuộc **`TaxPolicy` có trạng thái mutable hay không** và cách method `apply` hoạt động. Nếu dependency là immutable hoặc thread-safe và method không giữ state chia sẻ khác, mô hình này rất dễ dùng đồng thời.

**Đừng coi “field chứa dependency là final” đồng nghĩa “toàn bộ object graph immutable”.** Một field final trỏ tới một cache mutable vẫn phải có quy tắc đồng bộ hóa riêng cho cache đó.

## 7. Công bố bean trong Spring lifecycle

Trong vòng đời chuẩn, Spring tạo bean, xử lý dependency injection, gọi initialization callbacks (như `@PostConstruct`) rồi công bố bean đã sẵn sàng sử dụng qua container. Tài liệu Spring cho biết state cấu hình chỉ được thay đổi **trong giai đoạn khởi tạo** có bảo đảm visibility thích hợp khi container công bố singleton hoàn tất; các field cấu hình kiểu thường không nhất thiết phải đánh dấu volatile chỉ vì setter injection diễn ra lúc khởi tạo.

Tuy nhiên, phải phân biệt rõ:

| Tình huống | Đánh giá |
| --- | --- |
| Bean constructor nhận dependency vào field `final`, không sửa về sau | Thiết kế tốt cho cấu hình/dependency cố định |
| Setter hoặc `@PostConstruct` thiết lập state rồi không sửa tiếp; bean được Spring công bố bình thường sau khi init | Container công bố trạng thái khởi tạo của bean theo lifecycle của nó |
| Một thread bất kỳ sửa field thường **sau** khi bean đã khởi tạo | Không có bảo đảm visibility/thread safety chỉ nhờ bean là singleton |
| Field runtime thay đổi được và có nhiều reader | Cần `volatile`, lock, atomic, concurrent structure hoặc cơ chế phù hợp |
| Bean gửi `this` sang static registry/thread khác khi đang constructor/init | Có nguy cơ công bố sớm trước khi khởi tạo hoàn chỉnh |
| Circular dependency buộc Spring expose bean sớm trước khi hoàn tất initialization | Có thể tạo ngoại lệ với quy tắc công bố thông thường; tránh vòng phụ thuộc |

### 7.1. Vì sao `@PostConstruct` không thay thế concurrency control?

`@PostConstruct` chạy trong lifecycle initialization. Phương thức này thích hợp để kiểm tra cấu hình hoặc tạo cấu trúc dữ liệu ban đầu. Sau khi hoàn tất, container mới xem bean là initialized trong quy trình chuẩn. Nhưng nếu method nào đó tiếp tục sửa Map hoặc field thường khi nhiều request đang dùng bean, **visibility cho các cập nhật runtime không tự phát sinh**. Cần thiết kế synchronization tương ứng.

Không nên tự start worker, đăng ký listener callback ngay hoặc trao `this` cho thành phần chưa được kiểm soát khi constructor/init chưa xong. Nếu cần thực hiện công việc tốn thời gian sau khi các singleton đã hoàn thành khởi tạo, cân nhắc lifecycle hook phù hợp như `SmartInitializingSingleton.afterSingletonsInstantiated()`, `ContextRefreshedEvent` hoặc `SmartLifecycle`; chúng giải quyết **thời điểm khởi động**, còn việc chia sẻ state runtime vẫn phải bảo đảm theo JMM.

### 7.2. Scope prototype/request có giải quyết được không?

`prototype` tạo instance mới mỗi lần container trực tiếp resolve bean, nhưng nếu tiêm một prototype bean một lần vào singleton, singleton thường giữ đúng instance đã được tiêm đó. Scope `request` có một instance theo request trong web context phù hợp, nhưng vẫn có thể chia sẻ dữ liệu mutable qua dependency, cache hoặc async handoff. Vì vậy, scope là công cụ **định nghĩa vòng đời và phạm vi chia sẻ**, không phải một cơ chế synchronization tổng quát.

## 8. Chọn cơ chế theo kiểu trạng thái bean

| Loại state | Hướng thiết kế nên ưu tiên | Điều cần tránh |
| --- | --- | --- |
| Tham số gắn với một request/lời gọi | Biến local, immutable DTO | Lưu user/request hiện tại vào instance field của singleton |
| Cấu hình không thay đổi sau bootstrap | Constructor injection, `final`, immutable value object | Giữ tham chiếu tới input Map/List mutable |
| Cấu hình thay toàn bộ theo phiên bản, đọc nhiều | Immutable snapshot trong `volatile` / `AtomicReference` | Sửa Map của snapshot cũ tại chỗ |
| Nhiều writer sửa từ state trước đó | `AtomicReference.updateAndGet` / CAS hoặc lock | `volatile` cộng `state = derive(state)` khi có cạnh tranh |
| Bộ đếm/giá trị nguyên tử đơn lẻ | `AtomicLong`, `LongAdder` tùy yêu cầu đọc chính xác | `count++` trên `volatile long`, vì đây không phải phép tăng atomic |
| Map cần cập nhật độc lập theo key, tần suất cao | `ConcurrentHashMap.compute` hoặc `merge` | `get` rồi `put` và giả định tổ hợp đó atomic |
| Nhiều field có invariant chung | Lock bảo vệ toàn bộ thao tác hoặc snapshot gộp | Mỗi field volatile riêng rồi đọc ghép thành state “hỗn hợp” |
| Giao việc giữa thread | Executor, queue, Future với hợp đồng HB rõ ràng | Chia sẻ một object mutable rồi bỏ mặc đồng bộ hóa |

**Ví dụ invariant:** nếu `min <= max` phải luôn đúng, việc đặt `min` và `max` là hai biến volatile không bảo đảm mỗi reader nhìn thấy một cặp hợp lệ cùng phiên bản. Có thể dùng record `Range(int min, int max)`, kiểm tra invariant trong constructor và thay toàn bộ `volatile Range`/`AtomicReference<Range>` trong một bước, hoặc khóa chung khi đọc/ghi hai field.

### Lưu ý hiệu năng

Immutable snapshot thường đổi chi phí **mỗi lần cập nhật** lấy đường đọc nhanh và đơn giản, rất tốt cho cấu hình ít ghi. Với state thay đổi liên tục và kích thước lớn, copy cả Map mỗi lần sẽ không tối ưu. Việc chọn atomic, lock, concurrent collection hay snapshot phải xuất phát từ tỉ lệ đọc/ghi, độ lớn state, invariant cần bảo vệ và yêu cầu latency; không có một cơ chế luôn tốt nhất.

## 9. Những lỗi phổ biến

**Lỗi 1 — Nghĩ rằng singleton = thread-safe.** Singleton chỉ nói về số instance do container quản lý. Nếu các request sửa cùng field, vẫn có race.

**Lỗi 2 — Dùng `final HashMap` rồi sửa bằng `put`.** `final` giữ tham chiếu, không đóng băng nội dung HashMap. Dùng immutable Map, đồng bộ hóa hoặc collection concurrent theo nhu cầu.

**Lỗi 3 — Dùng `Collections.unmodifiableMap` trên source Map còn bị sửa.** View không sửa được qua API của nó nhưng vẫn phản ánh thay đổi của source. Nếu cần snapshot tách biệt, copy dữ liệu.

**Lỗi 4 — Đưa object ra ngoài trước khi constructor hoàn thành.** Việc đăng ký listener, lưu `this` vào static hoặc chạy task từ constructor có thể cho thread khác nhìn thấy object chưa xây dựng xong, phá điều kiện của final-field guarantee.

**Lỗi 5 — Cho rằng `@PostConstruct` làm mọi cập nhật sau này visible.** Lợi ích công bố state ban đầu của container không bao trùm các mutation runtime. Cần memory barrier/synchronization phù hợp.

**Lỗi 6 — Chỉ đánh dấu `volatile` cho Map rồi tiếp tục `map.put`.** Volatile reference không làm operations bên trong `HashMap` atomic hay an toàn. Thay toàn bộ immutable snapshot hoặc dùng cấu trúc/thread coordination thích hợp.

**Lỗi 7 — Dùng `volatile count++`.** Phép tăng gồm đọc, cộng, ghi nên có thể mất update. `AtomicLong.incrementAndGet()` hoặc synchronized bảo đảm atomicity cho một counter.

**Lỗi 8 — Không phân biệt safe publication và safe mutation.** Công bố an toàn cho phép consumer thấy trạng thái *tại thời điểm bàn giao*; nếu object còn mutable và bị writer sửa về sau, việc truy cập các sửa đổi đó vẫn đòi hỏi thread safety.

**Lỗi 9 — Nghe “concurrent collection” rồi đặt dữ liệu mutable bên trong.** Map thread-safe không tự bảo vệ trạng thái của mỗi value. Cần immutable values hoặc synchronization cụ thể.

**Lỗi 10 — Gọi DB/HTTP bên trong `AtomicReference.updateAndGet`.** Lambda có thể bị thực thi lại trong quá trình CAS retry, tạo side effect lặp. Chỉ tính object mới trong lambda; phối hợp với I/O theo giao thức rõ ràng.

**Lỗi 11 — Đọc hai snapshot khác nhau trong cùng một quyết định.** Nếu hai lời gọi `store.snapshot()` có thể trả hai phiên bản, business logic dễ ghép dữ liệu không nhất quán. Lấy snapshot **một lần** ở đầu một quyết định cần tính nhất quán và dùng nó xuyên suốt.

**Lỗi 12 — Hiểu nhầm visibility thành persistence.** Volatile và CAS bảo đảm trật tự bộ nhớ giữa thread trong cùng JVM; chúng không tự lưu state sau khi restart và không đồng bộ hóa trạng thái giữa nhiều Spring Boot replica. Những vấn đề này cần database, message broker hoặc cơ chế phân tán.

## 10. Tự kiểm tra hiểu bài

**Câu 1.** Một Spring `@Service` có `private final Map<String, Integer> totals = new HashMap<>();`. Các request cùng gọi `totals.merge(...)`. Có thread-safe không?

**Đáp án:** Không. Field final chỉ giữ nguyên tham chiếu Map; HashMap mutable không an toàn cho cập nhật đồng thời. Tùy yêu cầu, dùng concurrent map với `merge/compute`, lock hoặc immutable snapshot thay thế bằng CAS.

**Câu 2.** `record Config(List<String> servers)` có luôn immutable sâu không?

**Đáp án:** Không. Record không tự copy danh sách. Constructor có thể dùng `servers = List.copyOf(servers)` cho một danh sách phần tử String immutable và tránh trả ra dữ liệu mutable nội bộ.

**Câu 3.** Khi một thread gán `volatile Config current` bằng object mới được xây dựng xong, reader lấy object qua chính biến volatile đó có nhìn thấy state đã khởi tạo không?

**Đáp án:** Có, với các ghi xảy ra trước volatile write và volatile read tương ứng theo quan hệ HB. Nếu object sau đó bị sửa qua đường khác thiếu đồng bộ hóa, bảo đảm này không tự bảo vệ mọi mutation sau đó.

**Câu 4.** Vì sao `volatile long counter; counter++;` có thể mất số lần tăng?

**Đáp án:** Vì volatile không gộp read-modify-write thành một hành động atomic. Hai thread có thể đọc cùng giá trị cũ rồi ghi cùng giá trị mới; dùng atomic counter hoặc khóa.

**Câu 5.** Vì sao một immutable snapshot cũ vẫn dùng được khi bean đổi sang snapshot mới?

**Đáp án:** Writer tạo object mới và chỉ thay tham chiếu hiện tại. Reader đang giữ object cũ vẫn thấy trạng thái cũ nhất quán, miễn graph trạng thái thực sự immutable và object được khởi tạo/công bố đúng.

**Câu 6.** Spring có bảo đảm singleton được công bố sau khi hoàn tất quy trình khởi tạo chuẩn; như vậy field thường có thể bị nhiều request sửa không đồng bộ hóa không?

**Đáp án:** Không. Công bố ban đầu và các cập nhật runtime là hai vấn đề khác nhau. Sau khởi tạo, shared mutable state vẫn phải có cơ chế thread safety/visibility thích hợp.

## 11. Checklist trước khi đưa bean vào production

1. Xác định chính xác field nào là **per-request**, field nào là **shared**, và có writer nào ngoài request thread (scheduler, async, listener) không.
2. Nếu chỉ cần đọc, thiết kế **immutable value objects**, defensive copy cho cấu trúc lồng nhau và constructor injection cho dependency bắt buộc.
3. Tránh cho `this` hoặc reference mutable nội bộ thoát ra trước khi object được khởi tạo hoàn chỉnh.
4. Nếu cập nhật động, chọn **volatile snapshot** cho thay thế đơn giản hoặc **CAS/lock** cho cập nhật phụ thuộc state trước đó; giữ invariant trong cùng một snapshot.
5. Bảo đảm object và các phần tử được chia sẻ thực sự immutable hoặc có protocol synchronization rõ ràng; đừng tin vào từ khóa `final` một cách máy móc.
6. Kiểm tra hành vi khi nhiều writer cạnh tranh, khi async job chạy muộn, khi khởi động lại instance và khi nhiều replica cùng hoạt động.
7. Tách yêu cầu **thread safety trong JVM** khỏi **độ bền dữ liệu và nhất quán phân tán**.

**Ghi nhớ:** *Immutability* loại bỏ việc sửa trạng thái sau khi xây dựng; *safe publication* tạo bảo đảm rằng thread khác nhận được trạng thái khởi tạo/cập nhật theo đúng quan hệ bộ nhớ; *Spring bean scope* quy định đối tượng được chia sẻ trong phạm vi nào. Kết hợp ba góc nhìn này giúp lập luận đúng về concurrency trong ứng dụng Spring.

## Tài liệu đối chiếu

- Java Language Specification, Chapter 17 — Threads and Locks; `17.4 (Memory Model)`, `17.5 (Final Field Semantics)`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- Spring Framework — Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — Dependency Injection (constructor injection, circular references): https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html
- Spring Framework — Customizing the Nature of a Bean (init/publication and runtime state): https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Java SE API — `java.util.concurrent`, `AtomicReference`, `Future`, `ConcurrentHashMap` và `BlockingQueue`.
