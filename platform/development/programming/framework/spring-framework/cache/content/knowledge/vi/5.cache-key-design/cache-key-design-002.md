# Trường hợp đối số null, đối số mảng và khóa tổng hợp trong Spring Cache

> **Ngữ cảnh:** Spring Framework → Cache → Thiết kế khóa.  
> Bài này tập trung vào việc biến tham số method thành cache key một cách đúng đắn: phân biệt **không có tham số** với **tham số `null`**, hiểu cách xử lý **mảng**, và tạo **khóa tổng hợp** không va chạm khi có nhiều đối số hoặc chạy với cache phân tán.

## 1. Vì sao thiết kế khóa quyết định tính đúng của cache?

Với một method có `@Cacheable`, Spring tính **cache key** từ lời gọi method để tìm entry trong một vùng cache (`cacheNames`). Nếu tồn tại entry tương ứng, method có thể không chạy mà trả lại kết quả đã cache; nếu không có, Spring chạy method rồi lưu kết quả theo chính sách.

Vì vậy, cache key phải biểu diễn **đầy đủ nhưng vừa đủ** các yếu tố làm thay đổi kết quả. Có hai nhóm lỗi đặc biệt nguy hiểm:

- **False hit (trùng khóa sai):** hai lời gọi về mặt nghiệp vụ khác nhau tạo ra cùng khóa, khiến hệ thống trả dữ liệu của lời gọi khác. Ví dụ bỏ `tenantId` khỏi khóa rồi dùng chung cache giữa nhiều tenant có thể dẫn đến rò rỉ dữ liệu.
- **False miss (khóa khác nhau dù cùng ý nghĩa):** hai lời gọi tương đương tạo khóa khác nhau, làm mất lợi ích cache. Ví dụ dùng trực tiếp địa chỉ của mảng làm key thay vì nội dung mảng khiến `new int[]{1, 2}` ở hai lần gọi tạo ra hai key khác nhau.

Cả hai nguy cơ xuất hiện khi tham số có `null`, mảng, danh sách/đối tượng có thể sửa đổi, hoặc khi phải ghép nhiều trường thành một khóa. Việc chọn cache backend (ConcurrentMap, Caffeine, Redis...) còn quyết định dạng key được chấp nhận và cách chuyển key sang định dạng lưu trữ.

## 2. Thuật toán khóa mặc định: `SimpleKeyGenerator`

Khi `@Cacheable` không khai báo `key` hay `keyGenerator` và không có generator mặc định tùy biến, Spring dùng `org.springframework.cache.interceptor.SimpleKeyGenerator`.

| Tham số của method | Khóa mặc định | Ý nghĩa thực tế |
|---|---|---|
| **0 đối số** | `SimpleKey.EMPTY` | Tất cả lời gọi không đối số dùng cùng key trong cùng một cache name. |
| **1 đối số khác `null`, không phải mảng** | Chính đối tượng đối số đó | Cần `equals()`/`hashCode()` hợp lệ và không thay đổi khi đang làm key. |
| **1 đối số là `null`** | Một `SimpleKey` chứa phần tử `null` | Không trả chính `null` làm key; phân biệt được với trường hợp không có đối số. |
| **1 đối số là mảng** | Một `SimpleKey` chứa mảng đó | So sánh nội dung mảng theo cơ chế deep equality của `SimpleKey`. |
| **2 đối số trở lên** | Một `SimpleKey` chứa các đối số theo thứ tự | Giữ cả `null` và mảng bên trong; vị trí/thứ tự của các phần tử có ý nghĩa. |

Về bản chất, logic tương ứng với dạng rút gọn sau:

```java
// Minh họa logic mặc định, không phải mã cần sao chép để thay Spring:
if (params.length == 0) {
    return SimpleKey.EMPTY;
}
if (params.length == 1
        && params[0] != null
        && !params[0].getClass().isArray()) {
    return params[0];
}
return new SimpleKey(params);
```

Lưu ý điểm tinh tế: tài liệu thường nói “một đối số thì dùng chính đối số đó”, nhưng **source code có ngoại lệ cho `null` và mảng**. Vì `null` hoặc mảng được bọc trong `SimpleKey`, key mặc định an toàn hơn trong một bộ cache dạng map so với khi tự đặt `key="#p0"`.

### Các quy tắc về danh tính

- `SimpleKey.EMPTY` **khác** `new SimpleKey((Object) null)`.
- Một mảng `new int[]{1, 2}` và một mảng khác có cùng nội dung sẽ tạo `SimpleKey` bằng nhau; trực tiếp dùng hai mảng Java làm key thì `array1.equals(array2)` thường trả `false`, vì array kế thừa so sánh tham chiếu.
- `new SimpleKey("T1", "SKU7")` khác `new SimpleKey("SKU7", "T1")` và khác `new SimpleKey("T2", "SKU7")`.
- Một `List` hoặc `Map` duy nhất **không phải array** nên `SimpleKeyGenerator` thường trả chính collection/map đó. Java collections thông dụng có phép so sánh theo phần tử, nhưng khả năng sửa đổi sau khi làm key và khả năng convert sang key backend vẫn cần xem xét.
- `SimpleKeyGenerator` mặc định **không thêm tên method, tên class hoặc bean vào key**. Tên cache tách các không gian key; nếu hai method có ý nghĩa khác nhau dùng cùng `cacheNames` và cùng bộ tham số thì có thể vô tình dùng chung entry.

## 3. Trường hợp đối số `null`

### 3.1. Không có đối số và có một đối số `null` là hai tình huống khác nhau

Xét hai method:

```java
@Cacheable("settings")
public String defaultTheme() { /* ... */ }

@Cacheable("settings")
public String themeFor(String accountId) { /* ... */ }
```

Đây là các method minh họa, không phải file Java độc lập.

- Lời gọi `defaultTheme()` không có argument: key là `SimpleKey.EMPTY`.
- Lời gọi `themeFor(null)` có **một argument với giá trị null**: key là `SimpleKey` chứa một phần tử `null`.
- Lời gọi `themeFor("A1")` có một argument String: key là `"A1"`.

Không nhầm lời gọi một argument null thành lời gọi zero-argument; nếu phân tích key qua debugger, kiểm tra cả **số lượng tham số lẫn giá trị**.

### 3.2. Lỗi khi ép `key` thành một biểu thức trả `null`

Ví dụ này có vấn đề nếu `customerId == null`:

```java
@Cacheable(cacheNames = "customers", key = "#p0")
public Customer find(String customerId) {
    // ...
}
```

`#p0` trực tiếp trả `null`. Spring Cache yêu cầu key hợp lệ, không chấp nhận kết quả tính key bằng `null` cho cache operation, nên có thể ném lỗi `IllegalArgumentException` kiểu “Null key returned for cache operation”. Việc **method nhận null** không có nghĩa **key được phép null**.

Có ba cách xử lý tùy nghiệp vụ:

1. **Cho phép null là một đầu vào có nghĩa:** giữ key mặc định (`SimpleKeyGenerator` bọc null), hoặc tạo composite key có trường null rõ ràng.
2. **Không cache các lời gọi có argument null:** dùng `condition` để bỏ qua việc cache nhưng vẫn thực thi method.

   ```java
   @Cacheable(cacheNames = "customers", condition = "#p0 != null")
   public Customer find(String customerId) {
       // ...
   }
   ```

3. **Ánh xạ null thành sentinel:** chỉ làm khi sentinel không thể trùng giá trị dữ liệu thực. Ví dụ `key="#p0 ?: 'UNKNOWN'"` **không an toàn** nếu một customerId hợp lệ có thể bằng chính `"UNKNOWN"`. Tốt hơn là có tag phân biệt null với chuỗi thực, hoặc cấu trúc key có kiểu rõ ràng.

**Hai loại null không giống nhau:**

- **Null trong *tham số*** ảnh hưởng đến việc tạo cache key.
- **Null là *kết quả trả về*** liên quan đến chính sách cache value (`allowNullValues`, cách nhà cung cấp lưu null, hoặc `unless = "#result == null"`). Một provider cấm cache null value **không đồng nghĩa** tất cả method có argument null bị cấm.

Với `@Cacheable`, `condition` được đánh giá trước khi gọi method để quyết định có cache hay không; `unless` được đánh giá sau khi method hoàn thành để quyết định có lưu **kết quả** hay không. Đừng dùng `unless` để sửa lỗi key expression trả null.

### 3.3. Null trong khóa tổng hợp

Với chữ ký `lookup(String tenant, String language)`, cặp `("T1", null)` và cặp `(null, "T1")` phải tạo khóa khác nhau. `new SimpleKey("T1", null)` và `new SimpleKey(null, "T1")` phân biệt đúng nhờ giữ cả **vị trí** và **giá trị null**.

Nếu tự ghép chuỗi kiểu `tenant + ":" + language`, Java biến `null` thành chuỗi `"null"`: nó có thể trùng với giá trị literal `"null"` thật. Khi null có ý nghĩa nghiệp vụ, dùng bộ mã hóa có **tag kiểu dữ liệu hoặc độ dài** để phân biệt.

## 4. Trường hợp đối số mảng

### 4.1. Java array có `equals` theo tham chiếu

```java
int[] first = {1, 2};
int[] second = {1, 2};

System.out.println(first == second);                 // false
System.out.println(first.equals(second));           // false
System.out.println(java.util.Arrays.equals(first, second)); // true
```

Đoạn Java trên là snippet (có thể đặt trong `main` của một class); các kết quả comment là đúng với hai mảng mới tạo.

Khi ghi:

```java
@Cacheable(cacheNames = "recommendations", key = "#p0")
public String recommend(int[] selectedCategories) {
    // ...
}
```

`key="#p0"` trả trực tiếp đối tượng array, vì vậy với cache local dùng `Map` các mảng mới cùng nội dung có thể **miss liên tục**. Tương tự, cách dùng `#p0.toString()` tạo chuỗi dạng `[I@...` dựa trên identity, không phải mảng số, và không thích hợp làm khóa nghiệp vụ.

Ngược lại, nếu **không khai báo `key`**, `SimpleKeyGenerator` nhìn thấy argument là array và bọc nó trong `SimpleKey`; `SimpleKey` sử dụng so sánh băm sâu đối với các phần tử. Hai mảng có cùng kiểu và cùng nội dung vì thế có thể hit cùng entry trong local cache.

### 4.2. Mảng một chiều, mảng lồng nhau, primitive và object array

| Đầu vào | Điểm cần lưu ý |
|---|---|
| `int[]{1, 2}` | `Arrays.equals(int[], int[])` so theo giá trị; key mặc định bọc trong `SimpleKey`. |
| `String[]{"a", "b"}` | Mỗi phần tử được so sánh theo `equals`; thứ tự khác nghĩa là key khác. |
| `int[][]{{1, 2}, {3}}` | `SimpleKey` dùng cơ chế deep equality, phù hợp với mảng lồng nhau khi phần tử có semantics ổn định. |
| `Object[]{someDto, ...}` | DTO bên trong vẫn phải có `equals`/`hashCode` nhất quán; không tự có value semantics chỉ vì bọc trong mảng. |
| Mảng rỗng `new int[0]` | Khác argument null và khác trường hợp method không có đối số. |
| Mảng có phần tử `null` | Null của phần tử được giữ trong phép so sánh deep; không tự bỏ các phần tử null. |
| `List<Integer>` hoặc `Map<...>` | Đây là collections, **không phải array**; một collection đơn lẻ thường được trả nguyên làm key. |

**Mảng là dữ liệu có thể thay đổi.** Không nên sửa array hoặc đối tượng bên trong nó sau khi key đã được tạo và lưu vào cache. `SimpleKey` lưu cấu trúc key và tính hash từ những giá trị ban đầu; thay đổi nội dung object tham chiếu có thể làm `equals/hashCode` không nhất quán, khiến entry không còn tra cứu đúng. Các chiến lược an toàn hơn gồm: chuyển đầu vào thành giá trị bất biến, tạo snapshot/copy khi xây key, hoặc chuẩn hóa thành String đã encode.

### 4.3. Mảng có thứ tự hay tập hợp không thứ tự?

Hai yêu cầu `tags = [1, 2]` và `tags = [2, 1]` có thể là:

- **Khác nghiệp vụ**, nếu thứ tự ảnh hưởng kết quả: giữ nguyên thứ tự trong key.
- **Tương đương**, nếu đây là bộ lọc tập hợp: chuẩn hóa trước khi tạo key, ví dụ loại phần tử trùng nếu nghiệp vụ cho phép rồi sort trên **bản sao** của mảng, tránh sửa object mà caller truyền vào.

Phải làm quyết định này dựa trên semantics thật. Không tự động sort mọi mảng: với giỏ hàng, pipeline xử lý, đường đi, hoặc query có thứ tự ưu tiên, sort có thể làm trùng khóa sai.

## 5. Khóa tổng hợp (composite key) khi có nhiều đối số

Giả sử một service có chữ ký:

```java
@Cacheable(cacheNames = "prices")
public Price price(String tenantId, String sku, String currency) {
    // ...
}
```

Với ba argument, Spring mặc định tạo `SimpleKey(tenantId, sku, currency)`. Đây là lựa chọn hợp lý **nếu tất cả ba trường đều ảnh hưởng đến kết quả**.

Tuy nhiên, nhiều chữ ký có arguments mang tính kỹ thuật như `traceId`, `debug`, `pageRequest` hoặc locale chỉ để log. Nếu các trường đó **không ảnh hưởng** kết quả, đưa chúng vào khóa gây false miss. Ngược lại, nếu `currency` hoặc `tenantId` có ảnh hưởng mà lại bỏ đi thì có thể gây false hit.

### 5.1. Chọn thành phần khóa theo kết quả nghiệp vụ

| Thành phần | Có nên đưa vào key? | Lý do |
|---|---|---|
| `tenantId` khi dữ liệu tenant bị cô lập | **Phải có** | Tránh đọc dữ liệu tenant khác. |
| `sku`, `productId` | Thường có | Xác định thực thể đang truy vấn. |
| `currency`, `locale`, `region` | Có nếu làm thay đổi dữ liệu trả về | Cùng SKU có thể có nhiều giá/định dạng/quy tắc theo khu vực. |
| `page`, `size`, `sort`, filters | Có khi thay đổi kết quả | Hai trang/filter khác nhau phải có key khác nhau. |
| `traceId` chỉ phục vụ theo dõi | Thường bỏ | Trace ID biến đổi mỗi request gây miss liên tục. |
| `timeout` chỉ điều khiển thời gian chờ, không thay đổi dữ liệu | Tùy hợp đồng method | Không cần nếu kết quả không phụ thuộc timeout; cần nếu nghiệp vụ thực sự thay đổi. |
| `userId` hoặc permission context | Có nếu quyết định kết quả/khả năng đọc | Tránh cache chia sẻ thông tin theo quyền. |

**Tách rõ key namespace và key body.** Cùng key `"P42"` ở `cacheNames="products"` và `cacheNames="stock"` thuộc hai cache khác nhau. Nhưng hai method khác nhau dùng **cùng** cache name và cùng key `"P42"` có thể va chạm. Đặt cache name đúng phạm vi hoặc có prefix miền nghiệp vụ/version trong key. Khi dùng Redis, prefix của cache manager có thể giúp cách ly namespace, nhưng không thay thế việc định nghĩa đầy đủ các trường của key.

### 5.2. Không ghép chuỗi một cách mơ hồ

Đây là cách dễ viết nhưng dễ va chạm:

```java
String key = tenant + ":" + sku;
```

Ví dụ:

- `tenant = "A:B"`, `sku = "C"` → `"A:B:C"`.
- `tenant = "A"`, `sku = "B:C"` → `"A:B:C"`.

Hai cặp khác nhau tạo cùng key. Ghép trực tiếp cũng gây nhầm `null` với literal `"null"`, hoặc number `1` và text `"1"` nếu không gắn tag kiểu.

Có ba chiến lược:

1. **Local cache, composite nhỏ và value semantics rõ ràng:** dùng mặc định `SimpleKey` hoặc một immutable key object/record với các trường phù hợp.
2. **Chỉ cần chọn một tập arguments:** dùng biểu thức SpEL `key` để chọn các thành phần, nhưng bảo đảm biểu thức không trả `null` và không làm mất thông tin.
3. **Key phức tạp hoặc chia sẻ liên dịch vụ:** dùng `KeyGenerator` hoặc hàm encode chuẩn hóa, có version, tag kiểu, escape/length-prefix và tài liệu hóa format.

**Lưu ý với Java `record`:** record có `equals/hashCode` tự sinh theo từng component, nhưng **component kiểu array vẫn có phép so sánh identity**, không tự biến mảng thành giá trị so sánh sâu. Nếu record giữ mảng, cần chọn cấu trúc bất biến theo giá trị (chẳng hạn `List<Integer>` snapshot) hoặc tự triển khai equality/hash đúng.

## 6. Ví dụ đầy đủ chạy được: `null`, mảng và composite trong Spring Framework

Ví dụ này dùng **Java 17+**, **Maven**, **Spring Framework 6.2.12** và cache trong bộ nhớ `ConcurrentMapCacheManager`. Nó chạy độc lập, không cần Redis hoặc database. Các phiên bản được cố định cho khả năng tái lập; khi áp dụng dự án thật, dùng phiên bản được dự án quản lý và tương thích.

Cây thư mục:

```text
spring-cache-key-cases/
├── pom.xml
└── src/main/java/dev/example/cachekeys/
    ├── CacheKeyLesson.java
    └── StableSearchKey.java
```

### 6.1. Maven dependencies

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>spring-cache-key-cases</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>dev.example.cachekeys.CacheKeyLesson</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. Bộ tạo String key ổn định cho một search có thể nhận null và mảng

**`src/main/java/dev/example/cachekeys/StableSearchKey.java`**

```java
package dev.example.cachekeys;

import java.util.StringJoiner;

public final class StableSearchKey {
    private StableSearchKey() {
    }

    public static String of(String tenant, int[] filters) {
        return "search:v1|" + encodeText(tenant) + "|" + encodeInts(filters);
    }

    private static String encodeText(String text) {
        return text == null ? "N" : "S" + text.length() + ":" + text;
    }

    private static String encodeInts(int[] values) {
        if (values == null) {
            return "N";
        }
        StringJoiner joiner = new StringJoiner(",", "A" + values.length + ":", "");
        for (int value : values) {
            joiner.add(Integer.toString(value));
        }
        return joiner.toString();
    }
}
```

Quy ước mã hóa này phân biệt các trường hợp:

- `null` text → `N`; text literal `"N"` → `S1:N`.
- Mảng `null` → `N`; mảng rỗng → `A0:`; mảng `[1, 2]` → `A2:1,2`.
- Prefix `search:v1` đánh dấu domain và version của format key; nếu thay format cần version hóa/invalidate nhất quán.
- `String.length()` là chiều dài UTF-16 của Java. Với hệ thống nhiều ngôn ngữ, phải thống nhất một chuẩn length/encoding được các bên thực thi giống nhau trước khi chia sẻ key.

Đây là format có chủ đích cho ví dụ `String` + `int[]`; **không** phải một serializer tổng quát cho mọi kiểu object. Bộ lọc hiện giữ nguyên thứ tự vì giả định thứ tự ảnh hưởng kết quả. Nếu filters mang tính tập hợp, hãy chuẩn hóa một **bản sao** trước khi encode.

### 6.3. Cấu hình annotation caching và gọi method

**`src/main/java/dev/example/cachekeys/CacheKeyLesson.java`**

```java
package dev.example.cachekeys;

import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.SimpleKey;
import org.springframework.cache.interceptor.SimpleKeyGenerator;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheKeyLesson {
    public static void main(String[] args) {
        // Tạo key mặc định trực tiếp để thấy các trường hợp ngoại lệ.
        Object noArgs = SimpleKeyGenerator.generateKey();
        Object oneNull = SimpleKeyGenerator.generateKey((Object) null);
        Object array1 = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});
        Object array2 = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});
        Object pair1 = SimpleKeyGenerator.generateKey("T1", "SKU7");
        Object pair2 = SimpleKeyGenerator.generateKey("T1", "SKU7");

        System.out.println("zeroKey=" + noArgs.equals(SimpleKey.EMPTY));
        System.out.println("nullKeyIsSimpleKey=" + (oneNull instanceof SimpleKey));
        System.out.println("arrayKeysEqual=" + array1.equals(array2));
        System.out.println("pairKeysEqual=" + pair1.equals(pair2));

        System.out.println("nullVsLiteral=" +
                !StableSearchKey.of(null, new int[] {1, 2})
                    .equals(StableSearchKey.of("N", new int[] {1, 2})));

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(CacheConfig.class)) {
            LookupService service = context.getBean(LookupService.class);

            System.out.println("nullable1=" + service.byNullable(null));
            System.out.println("nullable2=" + service.byNullable(null));

            System.out.println("array1=" + service.byArray(new int[] {1, 2}));
            System.out.println("array2=" + service.byArray(new int[] {1, 2}));

            System.out.println("composite1=" + service.byComposite("T1", "SKU7"));
            System.out.println("composite2=" + service.byComposite("T1", "SKU7"));
            System.out.println("composite3=" + service.byComposite("T2", "SKU7"));

            System.out.println("search1=" + service.search(null, new int[] {1, 2}));
            System.out.println("search2=" + service.search(null, new int[] {1, 2}));
            System.out.println("search3=" + service.search("N", new int[] {1, 2}));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                    "nullable", "arrays", "composite", "search");
        }

        @Bean
        public LookupService lookupService() {
            return new LookupService();
        }
    }

    public static class LookupService {
        private final AtomicInteger nullableLoads = new AtomicInteger();
        private final AtomicInteger arrayLoads = new AtomicInteger();
        private final AtomicInteger compositeLoads = new AtomicInteger();
        private final AtomicInteger searchLoads = new AtomicInteger();

        @Cacheable(cacheNames = "nullable")
        public String byNullable(String value) {
            return "nullable#" + nullableLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "arrays")
        public String byArray(int[] values) {
            return "sum" + Arrays.stream(values).sum()
                    + "#" + arrayLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "composite")
        public String byComposite(String tenant, String sku) {
            return "item-" + tenant + "-" + sku
                    + "#" + compositeLoads.incrementAndGet();
        }

        @Cacheable(
                cacheNames = "search",
                key = "T(dev.example.cachekeys.StableSearchKey).of(#p0, #p1)")
        public String search(String tenant, int[] filters) {
            return "search#" + searchLoads.incrementAndGet();
        }
    }
}
```

**Chạy dự án:** đặt đúng hai file Java và `pom.xml` như trên, rồi mở terminal tại thư mục `spring-cache-key-cases`.

```bash
mvn -q compile exec:java
```

**Stdout của các dòng `System.out.println`** trong một lần chạy mới (không tính log môi trường/Maven):

```text
zeroKey=true
nullKeyIsSimpleKey=true
arrayKeysEqual=true
pairKeysEqual=true
nullVsLiteral=true
nullable1=nullable#1
nullable2=nullable#1
array1=sum3#1
array2=sum3#1
composite1=item-T1-SKU7#1
composite2=item-T1-SKU7#1
composite3=item-T2-SKU7#2
search1=search#1
search2=search#1
search3=search#2
```

### 6.4. Điều gì được chứng minh?

- **Null argument:** hai lần `byNullable(null)` dùng cùng `SimpleKey` chứa null, nên method chỉ tăng bộ đếm một lần.
- **Array argument:** mỗi lần tạo `new int[]{1, 2}`, nhưng key mặc định bọc mảng theo giá trị nên lần hai hit.
- **Composite mặc định:** `("T1", "SKU7")` hit khi lặp lại; `("T2", "SKU7")` là khóa khác nên miss.
- **Composite String theo format riêng:** `search(null, [1,2])` hit khi lặp; `search("N", [1,2])` miss, vì null và literal `N` được encode khác nhau.
- **Proxy:** các lời gọi đi từ `main` qua Spring bean proxy; `@EnableCaching` có hiệu lực. Tạo object bằng `new LookupService()` ngoài context hoặc tự gọi `this.byArray(...)` trong cùng bean sẽ không đi qua cache interceptor mặc định.

**Chú ý Java varargs khi thử `SimpleKeyGenerator.generateKey` trực tiếp:** phải cast một tham số null thành `(Object) null` để truyền **một argument null**. Viết `generateKey(null)` có thể bị compiler coi là một **mảng varargs null**, không biểu diễn trường hợp đang muốn thử. Với một argument kiểu array, `(Object) new int[]{...}` giúp diễn đạt rõ rằng toàn bộ mảng là **một** argument.

## 7. Dùng SpEL `key` hay `KeyGenerator` khi nào?

### 7.1. Chọn một phần arguments bằng SpEL

Giả sử dữ liệu phụ thuộc `tenant` và `sku`, còn `traceId` chỉ dùng để quan sát:

```java
@Cacheable(cacheNames = "products",
           key = "new org.springframework.cache.interceptor.SimpleKey(#p0, #p1)")
public Product load(String tenant, String sku, String traceId) {
    // ...
}
```

Đoạn này **minh họa trên một service đã có `Product` và repository**. SpEL gọi constructor `SimpleKey` với hai đối số, cho phép giữ cả thành phần null mà không phải ghép chuỗi. `traceId` bị loại vì không làm thay đổi kết quả. Tương tự, có thể viết `key = "#p0"` khi chỉ chọn một argument **đã được bảo đảm khác null và có equality ổn định**.

Cú pháp tham số:

- `#p0` hoặc `#a0`: tham số thứ nhất.
- `#p1` hoặc `#a1`: tham số thứ hai.
- `#root.args[0]`: truy cập qua mảng argument của invocation.
- `#tenant`: dùng tên biến chỉ khi metadata tên tham số khả dụng, chẳng hạn khi biên dịch với `-parameters`. Dùng `#p0` giúp ví dụ không phụ thuộc cấu hình lưu tên tham số.

**Không đặt đồng thời `key` và `keyGenerator` trên cùng cache operation.** Hai tùy chọn này loại trừ nhau.

### 7.2. Tái sử dụng logic và mã hóa cho cache phân tán

Khi nhiều method dùng cùng một quy tắc, hoặc cần mã hóa có version/escape/length-prefix, khai báo bean `KeyGenerator`:

```java
@Bean("searchKeyGenerator")
public KeyGenerator searchKeyGenerator() {
    return (target, method, params) ->
            StableSearchKey.of((String) params[0], (int[]) params[1]);
}
```

Đây là **method cấu hình minh họa**, cần import `org.springframework.cache.interceptor.KeyGenerator` và class `StableSearchKey` đã có ở ví dụ trước. Sử dụng:

```java
@Cacheable(cacheNames = "search", keyGenerator = "searchKeyGenerator")
public SearchResult search(String tenant, int[] filters) {
    // ...
}
```

Đoạn service này cũng là **minh họa**, không phải chương trình chạy độc lập. Đặt generator có tên giúp nhiều nơi dùng chung quy tắc key. Nếu có `@CacheEvict` hoặc `@CachePut` cho cùng entry, **phải tạo ra cùng một key** khi làm thao tác cập nhật/xóa. Không thêm method name vào khóa một cách tùy tiện: method đọc và method xóa thường khác tên.

Với Redis hoặc distributed cache, key cuối cùng thường phải chuyển thành bytes hoặc String; một object Java được dùng tốt trong local map **không mặc định** có representation ổn định giữa node/phiên bản. Khi chọn key cho Redis, kiểm tra conversion service, key prefix, serializer và encoding của phiên bản Spring Data Redis đang dùng. Một format String cụ thể do ứng dụng kiểm soát thường dễ kiểm tra bằng công cụ vận hành.

## 8. Va chạm và nhất quán với `@CachePut` / `@CacheEvict`

Một entry được xác định bởi **cache name + key**. Hai đường đọc và xóa phải thống nhất chính xác.

**Ví dụ nguy hiểm** (minh họa):

```java
@Cacheable(cacheNames = "products")
public Product find(String tenant, String sku) {
    // key mặc định: SimpleKey(tenant, sku)
}

@CacheEvict(cacheNames = "products", key = "#p1")
public void update(String tenant, String sku, ProductUpdate update) {
    // key xóa: sku, không khớp SimpleKey(tenant, sku)
}
```

Nếu chỉ xóa bằng `sku`, entry đã được cache bằng composite key vẫn còn, nên đọc tiếp có thể trả dữ liệu cũ.

**Cách nhất quán** là dùng một quy tắc composite cho cả hai thao tác:

```java
@Cacheable(
        cacheNames = "products",
        key = "new org.springframework.cache.interceptor.SimpleKey(#p0, #p1)")
public Product find(String tenant, String sku) {
    // ...
}

@CacheEvict(
        cacheNames = "products",
        key = "new org.springframework.cache.interceptor.SimpleKey(#p0, #p1)")
public void update(String tenant, String sku, ProductUpdate update) {
    // ...
}
```

Các đoạn này nằm trong service có dependency được khai báo; không phải file standalone. Chúng minh họa **cùng một key expression** cho cache read và evict. Với cập nhật dữ liệu thật, còn phải quan tâm thời điểm commit database transaction, race giữa đọc/ghi, TTL và các bên khác cùng sửa dữ liệu.

Lưu ý `SimpleKeyGenerator` không tự bao gồm method name, nên **hai method khác nhau trong cùng `cacheNames`** có cùng parameters có thể trỏ tới cùng cache entry. Nếu nội dung trả về khác nhau, hãy dùng cache names khác hoặc prefix rõ ràng theo nghiệp vụ.

## 9. Những lỗi thường gặp, cách phát hiện và sửa

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `@Cacheable(key="#p0")` lỗi khi argument null | SpEL trả null làm key | Cho phép key mặc định bọc null, hoặc bỏ caching null input qua `condition`, hoặc dùng key encoder tách null rõ ràng. |
| Hai mảng cùng phần tử nhưng không hit | `key="#p0"` trả object array, equality theo identity | Dùng key mặc định cho mảng hoặc tạo snapshot + encode theo nội dung. |
| Mỗi lần request cùng filter đều miss | Dùng `toString()` của array hoặc DTO không ổn định | Chuẩn hóa object theo các trường cần thiết, dùng format key ổn định. |
| Key đã lưu không tìm lại được sau khi sửa array/map | Object key bị mutate, `equals/hashCode` thay đổi | Dùng dữ liệu bất biến hoặc copy trước khi tạo key. |
| Giá của tenant A hiện ra ở tenant B | Bỏ `tenantId` hoặc quyền truy cập khỏi key | Thêm mọi yếu tố phân vùng/bảo mật ảnh hưởng kết quả; audit cache name và sharing. |
| Hai cặp field khác nhau tạo cùng key String | Ghép không escape, không có length-prefix | Dùng component có tag kiểu + độ dài hoặc một encoding được kiểm thử injective. |
| Data update nhưng `@CacheEvict` không xóa entry | Key xóa và key đọc dùng quy tắc khác nhau | Tập trung hóa key generation, test cặp read/evict trên cùng bộ input. |
| Local cache chạy, Redis báo lỗi đổi key | Provider cần converter/serializer phù hợp | Tạo String key ổn định hoặc đăng ký conversion đúng kiểu; kiểm tra namespace và byte encoding. |
| Hai method khác nghiệp vụ dùng chung entry | Cùng cache name và cùng key, mặc định không kèm method | Tách cache name, thêm domain prefix hoặc namespace. |
| Thứ tự filters khác nhau gây miss không cần thiết | Key giữ order trong khi nghiệp vụ xem filters là tập hợp | Chuẩn hóa bằng sort/deduplicate trên bản sao nếu semantics cho phép. |
| Record chứa array vẫn miss với nội dung giống nhau | Record-generated equality với array vẫn dựa trên identity | Chuyển array thành immutable value-based collection hoặc tự cài equality/hash theo nội dung. |

## 10. Kiểm thử khóa và lưu ý khi triển khai thật

### 10.1. Test cases tối thiểu

Với mỗi method cacheable có arguments phức tạp, kiểm chứng ít nhất:

1. **Zero args, one null, one empty array:** không nhầm các trạng thái này.
2. **Array value equality:** hai instance array cùng nội dung hit cùng entry nếu nghiệp vụ tương đương; khác nội dung miss.
3. **Thứ tự phần tử:** kiểm chứng `[1, 2]` và `[2, 1]` tương đương hay khác nhau đúng theo nghiệp vụ.
4. **Composite pair:** cùng tuple hit; thay từng field liên quan phải miss. Đặc biệt thử thay `tenantId` và trường phân quyền.
5. **Null vs literal:** `null`, `"null"`, `""` và sentinel đều được phân biệt nếu nghiệp vụ yêu cầu.
6. **Ký tự phân cách:** các trường có `:`, `|`, dấu cách, tiếng Việt, Unicode; tránh ghép chuỗi collision.
7. **Mutation:** sửa mảng/collection sau khi tạo key và chứng minh hệ thống đã tránh phụ thuộc object mutable, hoặc chặn việc sửa.
8. **Key generation vs eviction:** gọi đọc, update/evict, rồi đọc lại và đo loader có chạy đúng.
9. **Nhiều cache methods:** hai method khác nhau dùng chung `cacheNames` không vô tình chia sẻ entry có loại dữ liệu khác nhau.
10. **Provider thật:** chạy cùng test trên Caffeine/Redis nếu dự án có; kiểm tra key conversion, serialization, key prefix, tên cache, deploy nhiều node.
11. **Version thay đổi:** key format mới có thể sống song song với dữ liệu cũ; version prefix/invalidation phải được thiết kế trước khi deploy.
12. **Hiệu năng và bảo mật:** key không chứa token/password/PII thô nếu có thể tránh; cân nhắc kích thước key, cardinality, số lượng entry và thời gian giữ dữ liệu.

### 10.2. Nguyên tắc khi tự định nghĩa key encoder

Một key encoder tốt cần các tính chất sau:

- **Deterministic:** cùng đầu vào về mặt nghiệp vụ cho ra cùng key giữa lần gọi, JVM và node.
- **Complete:** các biến ảnh hưởng đến kết quả được đưa vào; có trường hợp như tenant/permission không thể bỏ.
- **Unambiguous:** các tuple khác nhau không vô tình hợp thành cùng key; null, empty và literal sentinel phải phân biệt.
- **Immutable/canonical:** không phụ thuộc địa chỉ object, hash ngẫu nhiên, locale JVM hay dữ liệu đang bị mutate.
- **Versioned và vận hành được:** có namespace, format rõ ràng, độ dài hợp lý, quy tắc migrate/invalidate khi schema đổi.
- **Consistent ở các thao tác:** `@Cacheable`, `@CachePut` và `@CacheEvict` cùng hiểu key tương ứng.

Một **hash của dữ liệu** có thể giảm kích thước key nhưng phải chọn thuật toán phù hợp và vẫn xem xét xác suất collision, representation canonical, encoding và khả năng debug. `Object.hashCode()` hoặc một chuỗi nối mơ hồ **không phải** định danh ổn định cho dữ liệu nghiệp vụ phân tán.

## 11. Checklist quyết định nhanh

Khi thiết kế caching cho một method, trả lời theo thứ tự:

1. **Kết quả có phụ thuộc những tham số nào?** Ghi ra đầy đủ, kể cả tenant, auth scope, locale hoặc filter.
2. **Có `null` không?** Quyết định null có giá trị nghiệp vụ hay phải bỏ caching; tránh để SpEL key trả null.
3. **Có array/list/map không?** Xác định thứ tự có ý nghĩa không, object có mutable không, equality có theo giá trị không.
4. **Có nhiều trường không?** Nếu dùng `SimpleKey` mặc định, chỉ yên tâm khi mọi argument tương ứng với kết quả; nếu chọn subset, đặt key rõ ràng.
5. **Backend nào sẽ nhận key?** Với cache local, object key phù hợp khi equality ổn định; với Redis/distributed, định nghĩa conversion/String format cụ thể.
6. **Làm sao invalidation tái tạo đúng key?** Đảm bảo method update/evict có đủ tham số và dùng cùng quy tắc.
7. **Test đã bao phủ collision và false miss chưa?** Ít nhất thử null, mảng bằng nội dung, mảng khác thứ tự, tenant khác nhau và ký tự phân cách.

### Tài liệu chính thức

- Spring Framework — Default Key Generation và SpEL key: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- `SimpleKeyGenerator` Javadoc (Spring Framework 6.2.x): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html
- `SimpleKey` Javadoc (Spring Framework 6.2.x): https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/cache/interceptor/SimpleKey.html
- Spring Data Redis — Cache key conversion và cấu hình: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
