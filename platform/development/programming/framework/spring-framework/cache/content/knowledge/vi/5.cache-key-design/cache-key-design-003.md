# Hợp đồng equals–hashCode của khóa trong Spring Cache

## Mục tiêu

Sau bài học, bạn có thể giải thích vì sao **equals()** và **hashCode()** quyết định tính đúng đắn của khóa cache trong JVM, tự thiết kế khóa bất biến cho Spring Cache, nhận diện lỗi khi dùng object làm khóa, và phân biệt quy tắc của Java với cơ chế định danh khóa của cache provider phân tán.

Ngữ cảnh: Spring Framework Cache Abstraction, đặc biệt là các cache trong bộ nhớ dùng cấu trúc băm như ConcurrentMapCache và Caffeine ở chế độ khóa mạnh mặc định. Spring Cache cung cấp giao diện Cache, CacheManager và annotation; Spring không thay thế hợp đồng equals–hashCode của các đối tượng Java được dùng làm key.

## 1. Vì sao một khóa cache cần equals() và hashCode()?

Giả sử một phương thức đọc giá sản phẩm theo hai thành phần: mã sản phẩm và đơn vị tiền. Hai request khác nhau tạo hai object riêng, nhưng cùng mã và cùng tiền tệ. Chúng phải tra cứu **cùng một entry**, để không tính lại dữ liệu và không tạo hai entry dư thừa. Ngược lại, cùng mã sản phẩm nhưng tiền tệ khác phải tra cứu **hai entry khác nhau**.

Với cache kiểu bảng băm trong JVM, ý tưởng là:

~~~text
price(new PriceKey("P42", "VND"))
   -> Spring tính key
   -> CacheManager lấy cache "prices"
   -> cache sử dụng hashCode() để chọn vị trí/tập ứng viên
   -> sử dụng equals() để xác nhận key tương đương
   -> HIT hoặc MISS
~~~

**hashCode()** cung cấp mã băm kiểu int để tổ chức tra cứu. **equals()** quyết định hai key có đại diện cho cùng danh tính logic hay không. Một cache dùng cấu trúc băm có thể trả sai hit/miss nếu triển khai hai phương thức này không tương thích hoặc nếu key thay đổi trong lúc nằm trong cache.

Không nên hiểu rằng mọi provider đều dùng trực tiếp Java hashCode(). Ví dụ, Redis nhận khóa được chuyển thành bytes và tra cứu theo bytes trên server. Quy tắc của Java là nền tảng đối với các cache Java in-memory, còn cache từ xa cần thêm tính ổn định của **biểu diễn khóa sau serialization**.

## 2. Hợp đồng equals() của Java

Một cách triển khai equals() đúng phải tuân thủ các tính chất:

1. **Phản xạ:** Với mọi tham chiếu x khác null, x.equals(x) là true.
2. **Đối xứng:** x.equals(y) và y.equals(x) phải cho cùng kết quả.
3. **Bắc cầu:** Nếu x.equals(y) và y.equals(z) là true thì x.equals(z) phải true.
4. **Nhất quán:** Khi dữ liệu dùng để so sánh không đổi, nhiều lần gọi equals() phải cho cùng kết quả.
5. **So với null:** Với x khác null, x.equals(null) là false.

Giá trị x và y được xem là **bằng nhau về logic**, không nhất thiết cùng một object. Toán tử **==** trên hai tham chiếu chỉ kiểm tra chúng có trỏ tới cùng object hay không. Một đối tượng key mặc định kế thừa Object.equals() thực hiện so sánh danh tính tham chiếu; điều này hợp lệ theo hợp đồng Java nhưng **có thể không phù hợp với cache**, vì hai request tạo object mới sẽ không hit lẫn nhau dù chứa cùng dữ liệu.

Ví dụ: new PriceKey("P42", "VND") được tạo lần một và lần hai là hai instance khác nhau. Nếu PriceKey là record, hai instance này sẽ equals() bằng nhau nhờ giá trị thành phần. Nếu là class không override equals(), chúng thường không bằng nhau vì so sánh tham chiếu.

## 3. Hợp đồng hashCode() và quan hệ bắt buộc với equals()

Quy tắc cốt lõi:

> Nếu x.equals(y) == true thì x.hashCode() **bắt buộc** bằng y.hashCode().

Ngoài ra, khi những thuộc tính dùng cho equals() không đổi, hashCode() phải trả kết quả nhất quán trong cùng quá trình thực thi. Điều ngược lại **không bắt buộc**: hai object không bằng nhau vẫn có thể trùng hashCode(), gọi là **va chạm băm** (hash collision). Cấu trúc băm cần equals() để phân biệt chúng.

Ví dụ hai String khác nhau có thể cùng mã băm:

~~~java
System.out.println("Aa".hashCode() == "BB".hashCode()); // true
System.out.println("Aa".equals("BB"));                 // false
~~~

Đây là đoạn minh họa biểu thức trong Java; output hai dòng lần lượt là true và false. Một hệ thống dùng **duy nhất hashCode() làm key** hoặc xem hashCode là định danh duy nhất có nguy cơ trộn dữ liệu khi va chạm.

Bảng quy tắc kiểm tra:

| Tình huống | Có hợp lệ về hợp đồng? | Ý nghĩa |
| --- | --- | --- |
| equals() true, hashCode() bằng nhau | Bắt buộc | Bảo đảm cùng key logic có thể được tra cứu |
| equals() true, hashCode() khác nhau | **Sai** | Có thể lưu/truy xuất khác bucket, cache miss sai |
| equals() false, hashCode() bằng nhau | **Hợp lệ** | Collision; equals() phân biệt khi tra cứu |
| equals() false, hashCode() khác nhau | Hợp lệ | Phân tán khóa thông thường |
| hashCode() thay đổi sau khi key đã được đưa vào cache | Nguy hiểm | Entry có thể không được tìm thấy theo key đã biến đổi |

Nói chính xác hơn: hashCode() không cần duy nhất; nó phải **phù hợp với equals()** và **ổn định đối với trạng thái đang dùng để định danh**.

## 4. Cách thiết kế khóa bất biến bằng Java record

Với Java 17+, record là lựa chọn phù hợp khi key chỉ gồm các thành phần giá trị bất biến. Compiler tự sinh equals() và hashCode() theo các component đã khai báo.

~~~java
import java.util.Objects;

public record PriceKey(String productId, String currency) {
    public PriceKey {
        Objects.requireNonNull(productId, "productId");
        Objects.requireNonNull(currency, "currency");
    }
}
~~~

Đây là **đoạn định nghĩa kiểu**; để biên dịch riêng, lưu thành PriceKey.java và dùng lệnh javac PriceKey.java (yêu cầu Java 17+). String không thể bị sửa nội dung sau khi tạo; hai thành phần của record cũng là final. Do đó, hai instance có productId và currency bằng nhau sẽ có equals() true và hashCode() tương ứng bằng nhau.

Ví dụ ba khóa:

~~~text
PriceKey("P42", "VND") ==logic== PriceKey("P42", "VND")
PriceKey("P42", "VND") !=logic!= PriceKey("P42", "USD")
~~~

Khóa phải bao gồm **đầy đủ các yếu tố làm thay đổi kết quả phương thức**. Nếu cùng sản phẩm nhưng khác currency, locale, tenant, version dữ liệu hoặc chính sách giá tạo ra đầu ra khác nhau, những yếu tố liên quan cần nằm trong key, trừ khi tên cache hoặc namespace đã phân tách chúng một cách bảo đảm.

### Record không đồng nghĩa bất biến sâu

Record chỉ cố định **tham chiếu thành phần**. Nếu thành phần là List có thể thay đổi, array hoặc object mutable thì dữ liệu bên trong vẫn đổi được. Khi ấy equals() và hashCode() của record cũng có thể thay đổi theo nội dung mutable.

Ví dụ không an toàn:

~~~java
record SearchKey(java.util.List<String> tags) {}

var tags = new java.util.ArrayList<>(java.util.List.of("java"));
var key = new SearchKey(tags);
tags.add("spring"); // Đã thay đổi trạng thái tham gia equals/hashCode của key.
~~~

Muốn dùng List làm key, hãy tạo bản sao bất biến ở ranh giới tạo khóa:

~~~java
record SearchKey(java.util.List<String> tags) {
    public SearchKey {
        tags = java.util.List.copyOf(tags);
    }
}
~~~

Đây vẫn chỉ là **bất biến nông đối với phần tử của List**. Nếu các phần tử bên trong là object mutable và có ảnh hưởng tới equals/hashCode, cần snapshot sâu hơn hoặc chuẩn hóa thành các String/id bất biến. Tránh đưa array mutable vào key; bản thân array trong Java dùng equals/hashCode theo danh tính tham chiếu nếu không bọc/so sánh nội dung đúng cách.

## 5. Nếu viết class thường, phải triển khai cả hai phương thức

Không phải dự án nào cũng muốn public key dưới dạng record. Khi dùng class, các trường nhận diện nên private final; equals() và hashCode() phải sử dụng **cùng bộ thuộc tính**.

~~~java
import java.util.Objects;

public final class PriceKey {
    private final String productId;
    private final String currency;

    public PriceKey(String productId, String currency) {
        this.productId = Objects.requireNonNull(productId);
        this.currency = Objects.requireNonNull(currency);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof PriceKey that)) return false;
        return productId.equals(that.productId)
            && currency.equals(that.currency);
    }

    @Override
    public int hashCode() {
        return Objects.hash(productId, currency);
    }
}
~~~

Đây là class độc lập có thể biên dịch trên Java 17+ khi lưu vào PriceKey.java. **equals() và hashCode() cùng xét productId, currency**. Không chọn chỉ một trường trong hashCode rồi tuyên bố sai hợp đồng: hashCode ít trường hơn vẫn có thể hợp lệ vì chỉ làm tăng collision, nhưng chất lượng phân bố có thể kém. Lỗi thật sự là khi hai object được equals() xem là bằng nhau nhưng hashCode khác nhau, hoặc khi bộ trường so sánh thiếu dữ liệu quyết định bản sắc của key.

Với các class có kế thừa, hãy cẩn trọng khi dùng instanceof và khi subclass bổ sung trường vào equals(): thiết kế không nhất quán giữa parent/child dễ phá **tính đối xứng hoặc bắc cầu**. Với key của cache, final class hoặc record với ngữ nghĩa giá trị rõ ràng thường dễ an toàn hơn.

## 6. Ví dụ Java 17: HashMap cho thấy cùng khóa logic và collision

Trước khi đi vào annotation Spring, có thể xác minh hợp đồng bằng JDK thuần. Tạo file **KeyContractDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class KeyContractDemo {
    record PriceKey(String product, String currency) {
        PriceKey {
            Objects.requireNonNull(product);
            Objects.requireNonNull(currency);
        }
    }

    public static void main(String[] args) {
        PriceKey first = new PriceKey("P42", "VND");
        PriceKey same = new PriceKey("P42", "VND");
        PriceKey other = new PriceKey("P42", "USD");

        System.out.println("equals=" + first.equals(same));
        System.out.println("sameHash="
            + (first.hashCode() == same.hashCode()));

        Map<PriceKey, String> cache = new HashMap<>();
        cache.put(first, "price-in-vnd");
        System.out.println("hit=" + cache.get(same));
        System.out.println("otherCurrency=" + cache.get(other));

        Map<String, String> collisions = new HashMap<>();
        collisions.put("Aa", "first");
        collisions.put("BB", "second");
        System.out.println("collision="
            + ("Aa".hashCode() == "BB".hashCode()));
        System.out.println("collisionEntries=" + collisions.size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 KeyContractDemo.java
java KeyContractDemo
~~~

Kết quả stdout chính xác:

~~~text
equals=true
sameHash=true
hit=price-in-vnd
otherCurrency=null
collision=true
collisionEntries=2
~~~

Giải thích:
- first và same là hai instance riêng nhưng **equals() true và cùng hash**, nên get(same) đọc lại entry của first.
- other có currency khác, nên không tìm được entry, get() trả null.
- Hai String "Aa" và "BB" có cùng hashCode nhưng không equals(); HashMap vẫn giữ hai entry. HashMap minh họa nguyên lý tra cứu khóa, **không phải toàn bộ cơ chế Spring Cache** (không có annotation, interception, TTL hay eviction).

## 7. Spring Cache tạo key mặc định như thế nào?

Khi không khai báo key hoặc keyGenerator tùy chỉnh, annotation-based caching dùng cơ chế mặc định dựa trên các tham số phương thức (SimpleKeyGenerator trong cấu hình mặc định thông thường).

| Dạng tham số | Khóa mặc định | Tác động của equals/hashCode |
| --- | --- | --- |
| Không tham số | SimpleKey.EMPTY | Mọi lần gọi cùng tên cache với dạng key này có cùng key |
| Một tham số khác null và không phải array | Chính object tham số đó | Nếu là object nghiệp vụ, equals/hashCode của nó trực tiếp quyết định hit/miss |
| Một tham số null hoặc một array | Một SimpleKey chứa danh sách tham số | Phụ thuộc cách SimpleKey so sánh các thành phần; tránh giả định rằng key là tham số trần |
| Từ hai tham số trở lên | SimpleKey gồm các tham số | Các thành phần tham số cần có ngữ nghĩa bằng nhau đúng; Spring xử lý cấu trúc key nhiều tham số |

SimpleKey của Spring thực hiện so sánh thành phần theo ngữ nghĩa sâu cho cấu trúc phần tử được chứa, nhưng **không sửa được** equals/hashCode sai của những object nghiệp vụ ở bên trong. Một danh sách tham số đa dạng hoặc object mutable cũng có thể tạo key khó ổn định; cần chọn biểu diễn an toàn.

Ví dụ:

~~~java
@Cacheable(cacheNames = "prices")
public String price(PriceKey key) {
    return loadFromSource(key);
}
~~~

Đoạn trên là minh họa annotation, chưa là class hoàn chỉnh. Vì PriceKey là tham số đơn và không phải array, key mặc định chính là PriceKey; hai record có cùng productId và currency sẽ được xem là một khóa logic. Phần cacheNames định vị **kho cache**, còn equals/hashCode định vị **entry** bên trong kho dùng kiểu key này.

### Các phương thức khác nhau có thể trùng key trong cùng cache

CacheManager và Cache **không tự động thêm tên method/class vào key mặc định**. Giả sử hai method đều dùng @Cacheable(cacheNames = "prices") và đều nhận String "P42": mặc định chúng có thể tạo cùng key "P42". Nếu hai method trả hai loại dữ liệu khác nhau, có nguy cơ trộn kết quả.

Giải pháp tùy ngữ cảnh: dùng cache name khác nhau; dùng cấu trúc key có namespace/operation phù hợp; hoặc keyGenerator tùy chỉnh dùng nhất quán. Không nên thay thế key bằng số hashCode của method/argument vì hash collision vẫn có thể xảy ra.

## 8. Ví dụ Spring Framework hoàn chỉnh: hai object bằng nhau dùng chung cache entry

Dự án demo dùng **Java 17+, Maven và Spring Framework**, không cần Spring Boot. Kết quả thử nghiệm cho thấy CacheManager lưu trữ theo key có equals/hashCode đúng, sau đó @CacheEvict xóa được entry dù dùng một object tương đương khác.

Cấu trúc:

~~~text
spring-cache-key-contract/
├── pom.xml
└── src/main/java/demo/CacheKeyApp.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-cache-key-contract</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
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

**src/main/java/demo/CacheKeyApp.java**:

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class CacheKeyApp {
    public record PriceKey(String productId, String currency) {
        public PriceKey {
            Objects.requireNonNull(productId);
            Objects.requireNonNull(currency);
        }
    }

    public static class PriceService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "prices")
        public String price(PriceKey key) {
            int call = loads.incrementAndGet();
            return key.productId() + "/" + key.currency() + " #" + call;
        }

        @CacheEvict(cacheNames = "prices", key = "#p0")
        public void invalidate(PriceKey key) {
            // Trong ứng dụng thật, hành động cập nhật nguồn được xử lý
            // theo transaction và quy tắc nhất quán phù hợp.
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("prices");
        }

        @Bean
        public PriceService priceService() {
            return new PriceService();
        }
    }

    public static void main(String[] args) {
        PriceKey a = new PriceKey("P42", "VND");
        PriceKey b = new PriceKey("P42", "VND");
        PriceKey c = new PriceKey("P42", "USD");

        System.out.println("sameLogicalKey=" + a.equals(b));
        System.out.println("sameHash=" + (a.hashCode() == b.hashCode()));

        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            PriceService service = ctx.getBean(PriceService.class);
            System.out.println(service.price(a));
            System.out.println(service.price(b));
            System.out.println(service.price(c));
            service.invalidate(b);
            System.out.println(service.price(a));
        }
    }
}
~~~

Chạy trong thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheKeyApp
~~~

Stdout từ code demo (không tính thông báo riêng của Maven):

~~~text
sameLogicalKey=true
sameHash=true
P42/VND #1
P42/VND #1
P42/USD #2
P42/VND #3
~~~

Phân tích từng lệnh:
1. a và b khác instance, nhưng equals() true và hashCode tương ứng bằng nhau.
2. price(a) cache miss, mã thật chạy và tăng loads thành 1.
3. price(b) cache hit vì b là key **tương đương theo giá trị**, kết quả vẫn "#1".
4. price(c) cache miss vì currency khác, tăng loads thành 2.
5. invalidate(b) dùng **cùng cache name** và key "#p0" là PriceKey b; equals/hashCode cho phép xóa entry gốc đặt bằng a.
6. price(a) không còn entry, mã thật chạy lần thứ ba.

**Đúng phạm vi minh họa:** ConcurrentMapCacheManager có cache in-memory và sử dụng key Java; ví dụ không kiểm tra TTL, serialization, multi-instance hoặc transaction. Để annotation chạy, phải gọi PriceService được **lấy từ Spring container qua proxy**. Tự gọi method có annotation từ một method khác trong cùng instance (self-invocation) thường bỏ qua Spring proxy mặc định.

## 9. Ví dụ khóa sai: override equals() nhưng quên hashCode()

Giả sử lập trình viên tạo class:

~~~java
final class BrokenKey {
    private final String id;
    BrokenKey(String id) { this.id = id; }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof BrokenKey other
            && java.util.Objects.equals(id, other.id);
    }

    // Không override hashCode(): vẫn dùng Object.hashCode().
}
~~~

Hai instance cùng id sẽ equals() true nhưng **không được bảo đảm cùng hashCode()**; chúng thường có các mã băm danh tính khác nhau. Như vậy class vi phạm hợp đồng Java. Tùy hash và cấu trúc map, get() với instance tương đương có thể miss mặc dù entry đã tồn tại.

Cách sửa là override hashCode() tương ứng:

~~~java
@Override
public int hashCode() {
    return java.util.Objects.hashCode(id);
}
~~~

Đây là đoạn sửa **bổ sung vào class BrokenKey**, không phải chương trình độc lập. Nếu dùng IDE, tính năng Generate equals() and hashCode() hoặc chuyển thành record giúp tránh quên một phương thức; vẫn cần kiểm tra tập field mang ý nghĩa định danh.

### Lỗi ngược lại: equals() so sánh thiếu dữ liệu

Ví dụ key cho giá sản phẩm gồm productId và currency, nhưng equals() chỉ so productId. Khi đó hai request "P42/VND" và "P42/USD" bị coi là cùng một key, có thể hit dữ liệu sai. Dù hashCode() cũng chỉ dùng productId và hợp đồng Java **không bị vi phạm**, thiết kế khóa vẫn **sai về nghiệp vụ**.

Cần phân biệt hai tiêu chí độc lập:
- **Tính hợp lệ của hợp đồng Java:** equals/hashCode có tương thích, ổn định và tuân thủ các tính chất hay không?
- **Tính đúng của định danh cache:** những trường tham gia key có đủ để phân biệt mọi đầu ra nghiệp vụ khác nhau hay không?

Hai lớp kiểm tra đều bắt buộc khi thiết kế key.

## 10. Khóa mutable: lỗi nguy hiểm dù equals/hashCode viết đúng

Xét class có trường id thay đổi được:

~~~java
import java.util.Objects;

final class MutableKey {
    String id;
    MutableKey(String id) { this.id = id; }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey that
            && Objects.equals(id, that.id);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(id);
    }
}
~~~

Trong cùng một thời điểm, equals() và hashCode() đang tương thích. Nhưng nếu đưa object vào HashMap/ConcurrentMapCache rồi **sửa id**, hashCode() thay đổi. Map có thể đã đặt key trong cấu trúc dựa trên mã băm cũ; tìm bằng mã băm mới sẽ không thấy entry, thậm chí tìm lại bằng chính object gốc cũng có thể thất bại.

~~~java
MutableKey key = new MutableKey("old");
map.put(key, "cached");
key.id = "new";               // Phá tính ổn định của key đã lưu.
// map.get(key) lúc này không còn được bảo đảm trả "cached".
~~~

Đây là **đoạn minh họa** với biến map giả định đã được khai báo. Trong thực tế không nên dựa vào bất kỳ kết quả nào của lần tra cứu sau khi sửa key. Với key chứa collection, Date hoặc object nghiệp vụ có getter thay đổi theo thời gian, rủi ro tương tự xảy ra ở tầng lồng nhau.

Nguyên tắc: **đừng sửa trạng thái ảnh hưởng tới equals/hashCode trong suốt thời gian object được dùng làm key**. Tạo snapshot key bất biến từ input thay vì lấy trực tiếp một entity JPA/DTO mutable hoặc object có trường lazy-loading/thay đổi.

## 11. Khóa nhiều tham số và KeyGenerator tùy chỉnh

Với chữ ký phương thức nhận productId, currency và tenantId, lựa chọn đơn giản là để Spring sinh SimpleKey từ ba tham số:

~~~java
@Cacheable(cacheNames = "prices")
public String price(String productId, String currency, String tenantId) {
    // Đoạn minh họa: gọi nguồn dữ liệu.
    return findPrice(productId, currency, tenantId);
}
~~~

Nếu tất cả tham số là String bất biến và có vai trò định danh, khóa mặc định thường hợp lý. Tránh vô tình dùng object khác nhau về equals() mà nghiệp vụ coi là một giá trị hoặc ngược lại. Ví dụ BigDecimal("1.0") và BigDecimal("1.00") có equals() **false** dù compareTo() trả 0; nếu giá trị được dùng làm một phần key, cần quyết định rõ có chuẩn hóa scale hay không.

Khi một phương thức nhận nhiều object phức tạp, hãy chuyển về record chứa các trường định danh đúng, hoặc dùng **KeyGenerator** để gom logic chuẩn hóa vào một nơi. Đoạn minh họa:

~~~java
@Bean("priceKeyGenerator")
KeyGenerator priceKeyGenerator() {
    return (target, method, params) -> {
        String productId = (String) params[0];
        String currency = (String) params[1];
        String tenantId = (String) params[2];
        return new PriceKeyWithTenant(
            tenantId.trim(),
            productId.trim(),
            currency.trim().toUpperCase(java.util.Locale.ROOT)
        );
    };
}

record PriceKeyWithTenant(String tenantId,
                          String productId,
                          String currency) {}
~~~

Đây là **đoạn cấu hình minh họa**, yêu cầu khai báo bean trong class @Configuration với import org.springframework.cache.interceptor.KeyGenerator và org.springframework.context.annotation.Bean. Ví dụ trên chỉ hợp lệ khi ba đối số thực sự là String khác null, đúng thứ tự và phép chuẩn hóa phản ánh quy tắc nghiệp vụ (đừng trim hoặc đổi chữ hoa nếu mã là case-sensitive).

Phương thức sử dụng:

~~~java
@Cacheable(cacheNames = "prices", keyGenerator = "priceKeyGenerator")
public String price(String productId, String currency, String tenantId) {
    return findPrice(productId, currency, tenantId);
}
~~~

**Quan trọng:** @CacheEvict hoặc @CachePut liên quan phải tạo **đúng cùng key** (cùng thành phần, thứ tự, chuẩn hóa, tên cache), kể cả khi chữ ký phương thức cập nhật có thêm tham số phụ. Nếu operation dùng chữ ký khác, KeyGenerator cần xử lý tách biệt hoặc dùng biểu thức key cụ thể sao cho kết quả đồng nhất. Tránh sử dụng hashCode() riêng lẻ, String ghép không có ranh giới rõ ràng hoặc toString() mặc định của Object làm khóa; chúng có thể collision, không ổn định hoặc phụ thuộc địa chỉ object.

## 12. Khóa Java in-memory khác khóa đã serialization

Không nên áp dụng máy móc kết luận của ConcurrentMapCacheManager cho mọi hệ thống cache:

| Cache / phương thức lưu | Định danh tra cứu chính | Điều cần kiểm tra |
| --- | --- | --- |
| ConcurrentMapCache | Java key trong ConcurrentMap | equals(), hashCode(), tính bất biến, null-key policy |
| Caffeine với strong keys mặc định | Java equality/hash | Các nguyên tắc Java giống key của map; expire/evict là chính sách riêng |
| Caffeine với weakKeys | So sánh theo **identity**, không phải equals() giá trị | Hai object value-equal nhưng khác identity có thể không hit cùng entry |
| Redis thông qua Spring Data Redis | Chuỗi/bytes key được serialize + prefix | Format ổn định, namespace, serializer, tương thích giữa instance và phiên bản |
| Kho phân tán/provider khác | Tùy provider và bộ mã hóa | Kiểm tra tài liệu API và cấu hình thực tế |

Ở Redis, hai Java object equals() true **chưa đủ** để chắc chắn chúng tạo ra cùng byte sequence nếu serializer, chuẩn hóa hoặc cấu hình prefix khác nhau. Ngược lại, không cần Java hashCode() duy nhất trên Redis server; điều quan trọng là **khóa sau serialization phải giống nhau cho cùng danh tính logic và khác nhau cho danh tính khác**.

Ví dụ nguy hiểm khi tự ghép khóa:

~~~text
tenant="a:b", product="c"  -> "a:b:c"
tenant="a", product="b:c"  -> "a:b:c"
~~~

Cách tốt hơn: dùng cấu trúc có ranh giới rõ, encoding có độ dài, escaping đúng hoặc serializer/canonicalizer đã kiểm thử. Nếu khóa chứa dữ liệu nhạy cảm, cân nhắc tránh để lộ thông tin trong key quan sát được trên cache server/log/metrics.

## 13. Bộ kiểm thử hợp đồng và hành vi cache

Kiểm tra equals/hashCode ở cấp unit và kiểm tra hit/miss ở cấp Spring integration là hai bước khác nhau. Đối với một kiểu PriceKey, kiểm thử ít nhất các ca sau:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| a.equals(a) | true |
| a và b cùng mọi trường định danh | equals() true; hashCode() bằng nhau |
| b và a cùng giá trị | đối xứng: b.equals(a) true |
| a, b, c cùng giá trị | bắc cầu: a.equals(c) true |
| Một trường định danh khác nhau | equals() false |
| a.equals(null) | false |
| Truy xuất map bằng instance khác nhưng equals() bằng nhau | cache hit đúng |
| Thay một trường định danh trong bản key được tạo mới | cache miss đúng |
| Evict bằng key mới nhưng equals() bằng key cũ | xóa đúng entry |
| Multi-tenant và locale/currency | không trộn dữ liệu giữa ngữ cảnh khác nhau |

Trong Spring, có thể kiểm chứng bằng một bộ đếm số lần gọi phương thức thật như ví dụ mục 8. Khi kiểm thử tích hợp, nên lấy service từ ApplicationContext để annotation được proxy áp dụng. Cần xác minh cả **dương tính** (khóa logic tương đương thì hit) và **âm tính** (ngữ cảnh khác thì miss).

Các kiểm tra bổ sung có giá trị:
- Vẽ ra tập trường tạo ra kết quả: query params, tenant, user scope, locale, permission, feature state, version; chỉ đưa những trường thực sự cần vào key.
- Xác định ai tạo khóa, ai xóa khóa và có dùng cùng chuẩn hóa hay không.
- Với hệ thống multi-instance, kiểm tra serializer, prefix và tính ổn định sau deploy.
- Nếu cấu trúc key đổi giữa các phiên bản, đặt version trong namespace hoặc dùng chiến lược invalidate/migration rõ ràng, tránh vô tình đọc dữ liệu cũ theo định dạng mới.
- Nếu dùng weakKeys hoặc cache provider có identity semantics, điều chỉnh kỳ vọng hit/miss; equals/hashCode đúng không làm hai object riêng biệt trở thành cùng identity.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Hai object có giá trị giống nhau nhưng cache miss | Class chưa override equals/hashCode hoặc dùng object identity | Dùng record, final value object, hoặc implement đầy đủ equals và hashCode |
| equals() true nhưng tìm cache không ra | hashCode vi phạm hợp đồng hoặc key bị mutate | Sửa hashCode theo trường equals; chụp snapshot immutable |
| Cache hit nhưng dữ liệu sai tenant/currency | Thiếu trường phân biệt bản sắc nghiệp vụ | Bổ sung tenant/currency/locale vào khóa hoặc phân vùng cache |
| Cache hit sai giữa hai phương thức | Cùng cacheNames và cùng key mặc định nhưng output khác nhau | Tách cache name hoặc namespace key theo operation |
| Xóa cache rồi vẫn hit | @CacheEvict sinh key khác hoặc không đi qua proxy; có nhiều cache/instance | Đồng bộ key strategy; xác minh proxy và topology |
| Tự ghép String key bị trùng | Dùng delimiter không escape hoặc trường không có ranh giới | Dùng key có schema xác định, encoding rõ và test collision |
| Key có List/array/entity | Mutable hoặc cách so sánh không như dự định | Sao chép bất biến, chuẩn hóa thành ID/value; tránh array trần |
| Chuyển từ local cache sang Redis bị miss bất thường | Serializer/prefix/canonical form khác | Kiểm tra bytes key, version và cấu hình namespace |
| Hiểu hashCode trùng là cùng key | Nhầm hash collision với equality | Dùng equals() đầy đủ; không lưu theo hashCode duy nhất |

## 15. Câu hỏi tự kiểm tra

**1.** Hai PriceKey("P42","VND") tạo ở hai request khác nhau có equals() true. Nhưng hashCode() khác nhau. Đây là lỗi gì?

**Đáp:** Vi phạm hợp đồng equals–hashCode. Hai khóa được cho là bằng nhau bắt buộc có mã băm giống nhau; cache dùng cấu trúc băm có thể miss sai.

**2.** Hai object khác nhau có cùng hashCode(). Có bắt buộc chúng phải hit cùng một entry không?

**Đáp:** Không. Collision hợp lệ; equals() phải phân biệt hai key khác logic.

**3.** Một record chứa List mutable có an toàn tuyệt đối để làm khóa không?

**Đáp:** Không. Record giữ tham chiếu final nhưng List còn sửa được. Cần snapshot bất biến và bảo đảm các phần tử tham gia equality cũng ổn định.

**4.** Vì sao @Cacheable trên hai method cùng cache name có thể dùng chung key dù method khác tên?

**Đáp:** Key mặc định dựa trên đối số, không tự động thêm tên class/method. Cần thiết kế namespace hoặc cache name tương ứng với nghĩa của dữ liệu.

**5.** Với Redis, equals/hashCode của Java có tự bảo đảm hai instance tạo cùng khóa Redis không?

**Đáp:** Không. Redis tra cứu theo bytes đã serialize. Cần kiểm tra định dạng key, prefix, phiên bản serializer và logic chuẩn hóa giữa các instance.

## Kết luận

Một khóa cache tốt phải thỏa mãn **hai điều kiện đồng thời**: đúng hợp đồng Java (equals/hashCode và tính ổn định), và đúng **danh tính nghiệp vụ** (cùng request logic tạo cùng key; request khác kết quả tạo key khác). Với cache trong JVM, record bất biến hoặc value object final là điểm khởi đầu an toàn. Với cache từ xa, bổ sung hợp đồng serialization và namespace nhất quán.

### Tài liệu tham khảo

- Java Object.equals()/hashCode() – https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html
- Java records – https://docs.oracle.com/en/java/javase/17/language/records.html
- Spring Framework caching annotations – https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework cache key generation – https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html#cache-annotations-cacheable-default-key
