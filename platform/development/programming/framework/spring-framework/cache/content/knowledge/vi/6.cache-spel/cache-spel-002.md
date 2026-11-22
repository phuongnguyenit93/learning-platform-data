# Truy cập `#p0`, `#a0` và tên tham số trong Spring Cache SpEL

> **Chủ đề:** Spring Framework – Cache Abstraction · **Nhóm:** Biểu thức SpEL  
> **Trọng tâm:** Cách tham chiếu đối số của phương thức từ các thuộc tính biểu thức như `key`, `condition` và `unless` trên annotation caching; điều kiện để dùng **tên tham số** ổn định.

## 1. Vì sao cần truy cập đối số trong SpEL?

Một phương thức có thể nhận nhiều tham số nhưng chỉ một số tham số thực sự xác định kết quả cần cache. Spring cho phép viết **Spring Expression Language (SpEL)** ngay trong các annotation cache để lấy giá trị đối số làm cache key, quyết định có lưu cache hay loại bỏ entry.

Ví dụ:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public String findBook(String isbn) {
    return queryBook(isbn);
}
~~~

Đoạn này chỉ minh họa một phương thức; `queryBook` cần được định nghĩa trong ứng dụng thực tế. Khi Spring intercept lời gọi `findBook("9780134685991")`, `#p0` được đánh giá thành `"9780134685991"`. Chuỗi đó là **entry key** trong cache `books`. Khi lời gọi sau tạo cùng key và đã có giá trị, Spring có thể trả kết quả cache mà không gọi lại phần thân method.

Cần tách rõ:

- `cacheNames = "books"`: tên **vùng cache** cần truy xuất từ `CacheManager`.
- `key = "#p0"`: **biểu thức SpEL** chọn key bên trong vùng cache.
- `findBook(String isbn)`: đối số thực của lời gọi là nguồn dữ liệu để SpEL đánh giá.
- `@Cacheable` cần caching infrastructure hoạt động, chẳng hạn `@EnableCaching`, và lời gọi phải đi qua interceptor/proxy tương ứng.

## 2. Ba cách gọi cùng một đối số

Giả sử phương thức được gọi như sau:

~~~java
public String findBook(String isbn, boolean includeArchived) {
    return "...";
}

// Lời gọi: findBook("BK-17", true)
~~~

Spring Cache đưa các đối số vào **evaluation context** dành riêng cho caching:

| Biểu thức | Đối tượng nó trỏ tới | Giá trị trong ví dụ | Điều kiện sử dụng |
| --- | --- | --- | --- |
| `#p0` | Đối số **thứ nhất** (index 0) | `"BK-17"` | Theo vị trí, không cần giữ tên tham số |
| `#a0` | Đối số **thứ nhất** (alias của `#p0`) | `"BK-17"` | Theo vị trí, không cần giữ tên tham số |
| `#isbn` | Đối số có tên Java là `isbn` | `"BK-17"` | Spring phải khám phá được tên tham số |
| `#p1` | Đối số **thứ hai** (index 1) | `true` | Theo vị trí |
| `#a1` | Đối số **thứ hai** (alias của `#p1`) | `true` | Theo vị trí |
| `#includeArchived` | Tham số có tên `includeArchived` | `true` | Cần metadata tên tham số |
| `#root.args[0]` | Phần tử đầu tiên của mảng arguments | `"BK-17"` | Không cần tên tham số |
| `#root.args[1]` | Phần tử thứ hai | `true` | Không cần tên tham số |

**Quy tắc quan trọng:** chỉ số bắt đầu từ **0**. Chữ `p` nghĩa là *parameter*, `a` nghĩa là *argument*; trong Spring Cache SpEL, `#pN` và `#aN` là **hai cách đặt tên alias cho cùng đối số ở vị trí N**, không đại diện cho hai nguồn dữ liệu khác nhau.

Với cùng lời gọi, ba biểu thức `#p0`, `#a0`, `#isbn` có thể cùng cho ra một giá trị. Tuy nhiên, `#isbn` chỉ hoạt động đúng khi runtime có đủ thông tin về tên tham số.

### Cú pháp: vì sao phải có `#`?

Trong SpEL, ký tự `#` chỉ biến trong evaluation context. Do đó:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")   // Đúng: biến p0
@Cacheable(cacheNames = "books", key = "#a0")   // Đúng: alias a0
@Cacheable(cacheNames = "books", key = "#isbn") // Đúng nếu khám phá được tên isbn
~~~

Các annotation trên là **những lựa chọn thay thế** để minh họa, không phải ba annotation đồng thời gắn trên cùng phương thức.

Không viết `key = "p0"` nếu muốn dùng đối số đầu tiên: thiếu `#` sẽ làm SpEL hiểu theo ngữ nghĩa khác, dẫn tới lỗi hoặc key không mong muốn. Biểu thức `key = "'fixed'"` mới trả về chuỗi hằng `fixed`; dấu nháy đơn bên trong thuộc cú pháp literal của SpEL.

## 3. Cách Spring cung cấp `#p0`, `#a0` và tên thật

Khi một caching operation được thực thi, Spring tạo một evaluation context cho SpEL. Context có metadata về phương thức và đối số, trong đó:

1. Danh sách đối số thực được giữ theo **vị trí gọi**.
2. Spring đăng ký alias theo index như `p0`, `a0`, `p1`, `a1`, ...
3. Nếu có thể xác định tên tham số của method, Spring đồng thời cho phép truy cập theo tên như `isbn`, `includeArchived`.
4. Cơ chế tính key hoặc condition đọc các biến đó tại thời điểm phù hợp với thao tác cache.

Vì các alias vị trí không lệ thuộc vào tên Java, `#p0`/`#a0` thường an toàn hơn khi không kiểm soát được cách dependency đã được biên dịch. Ngược lại, tên có nghĩa như `#isbn` hoặc `#customerId` khiến biểu thức dễ đọc và dễ review hơn nếu build luôn giữ metadata.

Các dạng truy cập khác cũng hợp lệ:

~~~java
// Những đoạn dưới đây là ví dụ annotation riêng rẽ.
@Cacheable(cacheNames = "books", key = "#root.args[0]")
@Cacheable(cacheNames = "books", key = "#p0.toUpperCase()")
@Cacheable(cacheNames = "books", key = "#isbn.toUpperCase()")
~~~

Trong đó hai biểu thức có `toUpperCase()` yêu cầu đối số là chuỗi khác `null`. Khi dữ liệu có thể null, cần đặt điều kiện hoặc lựa chọn key phù hợp; gọi phương thức trực tiếp trên null có thể làm SpEL đánh giá thất bại.

### `#root` là gì?

Spring Cache còn cung cấp root object, chẳng hạn:

- `#root.args[0]`: đối số theo vị trí, không cần tên Java.
- `#root.methodName`: tên phương thức đang được gọi.
- `#root.method`: đối tượng `java.lang.reflect.Method`.
- `#root.target`: đối tượng đích.
- `#root.targetClass`: lớp của đối tượng đích.
- `#root.caches`: các cache liên quan đến operation.

**Không nhầm** `#root.args[0]` (mảng đối số của lời gọi) với `#root.caches[0]` (vùng cache được resolve). Cả hai thuộc root object nhưng phục vụ mục đích khác nhau.

## 4. Vì sao tên tham số `#isbn` đôi khi không hoạt động?

Trong Java, việc người viết thấy `findBook(String isbn)` trong mã nguồn **không đảm bảo** tên `isbn` có sẵn qua reflection tại runtime. JVM luôn biết *số lượng, thứ tự và kiểu* tham số trong method descriptor, nhưng tên nguồn cần được giữ khi biên dịch.

Với Java, cách chuẩn là dùng cờ:

~~~bash
javac -parameters BookService.java
~~~

Lệnh trên minh họa cờ compiler; tệp `BookService.java` vẫn cần toàn bộ dependencies/import tương ứng nếu chứa Spring annotations. Không thể lấy tên từ câu lệnh này nếu biên dịch một file Spring trơ không có classpath.

**Gradle (Groovy DSL):**

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

**Maven:**

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Các đoạn cấu hình trên chỉ thể hiện phần bật giữ tên; với dự án thực tế, cần đảm bảo chúng nằm đúng `build.gradle` hoặc `pom.xml` và build lại class.

### Kiểm tra tên tham số đã được giữ chưa

Java reflection có thể xác minh:

~~~java
Method method = BookService.class.getMethod("findBook", String.class);
Parameter parameter = method.getParameters()[0];

System.out.println(parameter.isNamePresent());
System.out.println(parameter.getName());
~~~

Đoạn minh họa này cần import `java.lang.reflect.Method` và `java.lang.reflect.Parameter`, cùng lớp `BookService` có phương thức public `findBook(String)`. Khi class được biên dịch với `-parameters`, kết quả mong đợi là:

~~~text
true
isbn
~~~

Nếu không giữ metadata, Java reflection thường chỉ hiển thị tên tổng hợp như `arg0` và `isNamePresent()` trả `false`. **`arg0` không phải là alias chuẩn `#a0`**: đừng biến một tên do reflection tự sinh thành giả định về biến SpEL.

Với các phiên bản Spring Framework hiện đại (đặc biệt Spring 6.1+), nên chủ động biên dịch Java với `-parameters` nếu muốn dựa vào tên tham số. Đừng dựa vào debug symbols của compiler như một bảo đảm thay thế. Với Kotlin, proxy hoặc các lớp được tạo mã tự động, cơ chế khám phá tên có thể khác; nên kiểm tra runtime thay vì giả định.

## 5. Ví dụ hoàn chỉnh Java 17+: ba cách truy cập

Ví dụ sau dùng **Spring Framework 6.2.14** và Gradle, tạo `ConcurrentMapCacheManager` với vùng `books` rồi gọi ba phương thức có cache. Một phương thức dùng `#p0`, một dùng `#a0`, một dùng tên `#code`. Các tiền tố key khác nhau giúp quan sát ba ví dụ mà không để entry của phương thức này che kết quả phương thức kia.

Tạo hai tệp đúng đường dẫn:

**`build.gradle`**

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

// Bắt buộc cho ví dụ truy cập biến tên #code.
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

application {
    mainClass = 'demo.ArgumentKeyDemo'
}
~~~

**`src/main/java/demo/ArgumentKeyDemo.java`**

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ArgumentKeyDemo {

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

    public static class BookService {
        private int positionCalls;
        private int aliasCalls;
        private int namedCalls;

        @Cacheable(cacheNames = "books", key = "'p:' + #p0")
        public String byPosition(String code) {
            return "position-load-" + (++positionCalls);
        }

        @Cacheable(cacheNames = "books", key = "'a:' + #a0")
        public String byAlias(String code) {
            return "alias-load-" + (++aliasCalls);
        }

        @Cacheable(cacheNames = "books", key = "'name:' + #code")
        public String byName(String code) {
            return "name-load-" + (++namedCalls);
        }
    }

    public static void main(String[] args) throws Exception {
        boolean namesPresent = BookService.class
                .getMethod("byName", String.class)
                .getParameters()[0]
                .isNamePresent();
        System.out.println("parameter names: " + namesPresent);

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            // Lấy bean qua Spring để lời gọi đi qua caching proxy.
            BookService service = context.getBean(BookService.class);

            System.out.println(service.byPosition("J17"));
            System.out.println(service.byPosition("J17"));

            System.out.println(service.byAlias("J17"));
            System.out.println(service.byAlias("J17"));

            System.out.println(service.byName("J17"));
            System.out.println(service.byName("J17"));
        }
    }
}
~~~

Chạy ở thư mục có `build.gradle`, với JDK 17+ và Gradle tương thích:

~~~bash
gradle run --quiet
~~~

**Stdout ứng dụng dự kiến** (không tính log môi trường/build ngoài chương trình):

~~~text
parameter names: true
position-load-1
position-load-1
alias-load-1
alias-load-1
name-load-1
name-load-1
~~~

**Phân tích:**

1. `parameter names: true` xác nhận option `-parameters` đã được áp dụng.
2. Ở lời gọi `byPosition("J17")` đầu tiên, key là `"p:J17"`; lời gọi thứ hai cùng key trả cache hit và `positionCalls` không tăng.
3. Với `byAlias("J17")`, `#a0` trỏ đến đối số đầu như `#p0`; key là `"a:J17"` và lần hai cũng hit.
4. Với `byName("J17")`, Spring biết tên `code` và tính key `"name:J17"`; lời gọi lặp lại cũng hit.
5. Cả ba phương thức dùng cùng vùng `books`, nhưng các tiền tố `p:`, `a:`, `name:` cố ý tạo ra **ba key khác nhau** để demo. Điều này **không** có nghĩa `#p0` và `#a0` tạo ra kết quả khác nhau; chúng cùng trỏ đến đối số số 0.

Cấu hình `@EnableCaching` kích hoạt caching interceptor. Ở mode proxy mặc định, gọi một method cacheable từ một method khác trên chính cùng đối tượng (`this.byName(...)`) có thể bỏ qua proxy và do đó bỏ qua cache. Ví dụ gọi từ `main` qua bean Spring để quan sát đúng hành vi.

## 6. Chọn theo vị trí hay theo tên?

| Tiêu chí | `#p0`, `#a0` | `#isbn`, `#userId` |
| --- | --- | --- |
| Khả năng đọc hiểu | Cần đối chiếu chữ ký hàm để biết `0` là gì | Tên mang ý nghĩa nghiệp vụ, dễ review |
| Metadata compiler | Không cần tên nguồn trong bytecode | Cần Spring tìm thấy tên thực |
| Đổi tên tham số | Thường không đổi ý nghĩa | Phải sửa expression nếu tên đổi |
| Đổi thứ tự tham số | Có thể âm thầm chuyển sang đối số khác | Ít phụ thuộc thứ tự nếu tên vẫn ổn định |
| Dùng với thư viện biên dịch không kiểm soát | Thường dễ dự đoán hơn | Phải kiểm tra metadata lúc chạy |
| Khuyến nghị | Hữu ích cho method nhỏ, tham số ít, hoặc thiếu metadata | Hữu ích cho mã ứng dụng do mình quản lý và luôn bật `-parameters` |

Ví dụ:

~~~java
// Chỉ là các chữ ký/annotation minh họa, không phải chương trình độc lập.
@Cacheable(cacheNames = "customers", key = "#p0")
public Customer load(long customerId, boolean includeDetails) { /* ... */ }

@Cacheable(cacheNames = "customers", key = "#customerId")
public Customer load(long customerId, boolean includeDetails) { /* ... */ }
~~~

Cả hai expression chọn `customerId` nếu tên metadata tồn tại. Nhưng **cần xem lại thiết kế key** nếu `includeDetails` làm thay đổi dữ liệu trả về: dùng mỗi `customerId` khi đó có thể đưa kết quả không đúng biến thể vào cache. Các tham số ảnh hưởng đến kết quả cần được phản ánh trong key hoặc tách vùng cache.

Ví dụ method có hai tham số cùng ảnh hưởng đến kết quả:

~~~java
@Cacheable(cacheNames = "prices")
public String price(String sku, String currency) {
    return queryPrice(sku, currency);
}
~~~

Nếu không chỉ định `key`, `SimpleKeyGenerator` mặc định kết hợp các đối số thành một key phù hợp (trong tình huống hai tham số). Với `key = "#p0"`, tiền tệ bị bỏ qua, rất dễ khiến giá USD được trả cho lời gọi EUR cùng SKU. Chỉ tự chọn một đối số khi chắc chắn đó là định danh kết quả.

## 7. Các biểu thức ứng dụng thường gặp

| Mục đích | Ví dụ SpEL trong annotation | Ý nghĩa / điều kiện |
| --- | --- | --- |
| Lấy đối số đầu | `key = "#p0"` hoặc `key = "#a0"` | Key là đối số thứ nhất |
| Lấy đối số thứ hai | `key = "#p1"` hoặc `key = "#a1"` | Key là đối số thứ hai |
| Lấy bằng tên | `key = "#customerId"` | Cần khám phá được tên `customerId` |
| Lấy thuộc tính | `key = "#p0.id"` hoặc `key = "#customer.id"` | Đối số đầu là object có property `id` và không null |
| Root args | `key = "#root.args[0]"` | Cách khác để lấy đối số theo vị trí |
| Cache có điều kiện | `condition = "#p1 == true"` | Chỉ cache khi đối số thứ hai là true |
| Loại bỏ giá trị null sau khi chạy | `unless = "#result == null"` | Không ghi kết quả null vào cache |
| Phân biệt method trong một vùng cache | `key = "#root.methodName + ':' + #p0"` | Phù hợp khi hai method có thể dùng cùng vùng nhưng cần key khác nhau |

Các ví dụ trên là chuỗi expression **riêng lẻ**, cần đặt vào annotation hợp lệ với phương thức có đủ đối số/kiểu dữ liệu. Không gọi `#p1` nếu method chỉ có một đối số. Với `#p0.id`, property phải thực sự truy cập được từ SpEL (ví dụ getter JavaBean), và giá trị ID phải ổn định.

Sự khác biệt thời điểm đánh giá:

- `@Cacheable(key = "...")` và `condition = "..."` thường dùng thông tin có sẵn **trước** khi thực thi method.
- `unless = "..."` được đánh giá **sau** khi có kết quả; khi phù hợp, biến `#result` tham chiếu kết quả nghiệp vụ.
- `#result` **không** phải biến đầu vào để viết `@Cacheable(key = "#result")`; ở thời điểm lookup cacheable thông thường, method chưa được gọi và chưa có result.
- Với `@CachePut`, biểu thức key có thể dùng `#result` theo thời điểm đặc thù của thao tác; đây là quy tắc riêng của caching operation, không thay đổi cách dùng `#p0`/`#a0`.

## 8. Những lỗi thường gặp và cách xử lý

### Lỗi 1: `#isbn` không được nhận diện dù Java method có tham số `isbn`

**Biểu hiện:** Biểu thức lấy tên trả về null hoặc lỗi tạo cache key, trong khi `#p0` vẫn chạy.

**Nguyên nhân thường gặp:** Class được biên dịch thiếu `-parameters`; method được phát hiện qua proxy/interface hoặc mã sinh với metadata không như dự đoán.

**Cách xử lý:** Thêm `-parameters` vào Java compile task, clean/rebuild artifact chứa method, kiểm tra `Parameter.isNamePresent()`. Khi không kiểm soát class được biên dịch, dùng `#p0` hoặc `#a0` và xác minh đúng index. Đừng sửa bằng cách giả định biến `#arg0`.

### Lỗi 2: Nhầm 0-based index

Với `findBook(String isbn, boolean includeArchived)`, `#p0` là `isbn`; `#p1` là `includeArchived`. `#p2` không phải tham số thứ hai mà là vị trí thứ ba, không tồn tại. Kiểm tra chữ ký theo thứ tự thực tế để tránh lỗi hoặc key sai.

### Lỗi 3: Key bỏ sót tham số ảnh hưởng đến kết quả

~~~java
// Sai nếu currency làm thay đổi giá trả về:
@Cacheable(cacheNames = "prices", key = "#sku")
public String price(String sku, String currency) {
    return queryPrice(sku, currency);
}
~~~

Biểu thức này bỏ `currency` nên hai lời gọi cùng SKU nhưng khác tiền tệ có thể dùng chung entry. Hãy đưa đủ thông tin vào key, hoặc để mặc định `SimpleKeyGenerator` kết hợp mọi đối số khi đó là lựa chọn đúng. **Dùng tên đúng chưa đủ; phải chọn đúng dữ liệu định danh kết quả.**

### Lỗi 4: Đối số hoặc property bằng `null`

`#p0.id` sẽ không thể truy cập `id` nếu đối số đầu null. `#p0?.id` dùng safe navigation có thể trả null, nhưng nhiều cache manager không cho phép **key null**. Không coi safe navigation là cách giải quyết hoàn chỉnh cho null key; cần `condition` để bỏ qua caching trong tình huống đó, hoặc thiết kế giá trị key thay thế không gây va chạm.

Ví dụ method có thể nhận null:

~~~java
@Cacheable(cacheNames = "books",
           condition = "#p0 != null",
           key = "#p0")
public String findBook(String isbn) {
    return queryBook(isbn);
}
~~~

Đây là minh họa mức method (cần định nghĩa `queryBook`). Khi điều kiện false, Spring không sử dụng caching cho lời gọi đó; code nghiệp vụ vẫn phải xử lý null theo contract của chính method.

### Lỗi 5: Gọi annotation nội bộ trong cùng class

Một method trên bean gọi `this.findBook(...)` thường không đi qua proxy cache của Spring trong chế độ proxy mặc định. Khi đó có thể tưởng rằng `#p0` sai vì cache không hit. Hãy kiểm tra caching infrastructure/proxy trước khi thay đổi expression.

### Lỗi 6: Nhầm SpEL của caching với môi trường SpEL khác

`#p0`, `#a0` là biến được cung cấp bởi **context của cache operation**. Không mặc định chúng tồn tại trong mọi nơi dùng SpEL, như `@Value`, security expression hay một parser SpEL tự khởi tạo. Biến nào hiện diện phụ thuộc evaluation context đã được framework chuẩn bị.

### Lỗi 7: Key có thể thay đổi sau khi lưu

Nếu key là object mutable, `equals()`/`hashCode()` của nó thay đổi theo trạng thái, entry có thể khó tìm lại hoặc sai định danh. Cân nhắc lấy trường ID bất biến: `key = "#p0.id"` (khi non-null và hợp lệ) thay vì dùng toàn bộ object làm key. Tránh gọi hàm có side effect trong SpEL key.

## 9. Cách tự kiểm tra một expression trên ứng dụng thực tế

Khi không cache hit hoặc nhận lỗi key, hãy lần lượt kiểm tra:

1. **Method signature:** đối số thứ nhất và thứ hai là gì, kiểu nào, có thể null không?
2. **Expression:** có `#` ở trước tên biến không; `#p0`/`#a0` hay `#p1` có đúng index không?
3. **Metadata tên:** nếu expression viết `#isbn`, class có được biên dịch với `-parameters` không? Reflection `isNamePresent()` cho kết quả gì?
4. **Định danh cache:** `cacheNames` là vùng nào; có nhiều method dùng chung vùng và vô tình tạo cùng key không?
5. **Proxy và điều kiện:** `@EnableCaching` có hiệu lực, lời gọi có qua Spring bean/proxy, `condition`/`unless` có chặn lưu cache không?
6. **Key bao phủ dữ liệu:** mọi tham số ảnh hưởng đến kết quả đã nằm trong key chưa? Giá trị key có ổn định và được provider chấp nhận không?

Để kiểm chứng sự khác nhau giữa tên và vị trí, có thể tạm đổi `key = "#isbn"` thành `key = "#p0"` trong một ví dụ xác định rõ đối số đầu là ISBN. Nếu chỉ biến tên thất bại, ưu tiên kiểm tra metadata/parameter name discovery. Nếu cả hai thất bại, cần điều tra rộng hơn về Spring proxy, cache manager và kiểu key.

## 10. Bài tập tự kiểm tra

**Bài 1.** Cho:

~~~java
public String search(String keyword, int page, boolean exact) {
    return "...";
}
~~~

Với lời gọi `search("spring", 2, true)`, `#p0` bằng gì? `#a1` bằng gì? `#root.args[2]` bằng gì?

**Đáp án:** `"spring"`, `2`, `true`.

**Bài 2.** `#p0` và `#a0` có cần flag `-parameters` không? Hai biến có khác đối số không?

**Đáp án:** Không cần flag để lấy theo vị trí; cả hai cùng tham chiếu đối số index 0.

**Bài 3.** Muốn dùng `key = "#keyword"` cho bài 1, cần điều kiện nào?

**Đáp án:** Spring phải tìm được tên tham số `keyword`, ví dụ class Java được biên dịch với `-parameters`. Đồng thời phải chắc rằng chỉ keyword đủ xác định kết quả; nếu page hoặc exact thay đổi kết quả, key phải phản ánh các thông tin ấy.

**Bài 4.** Vì sao `#result` không dùng làm `key` của `@Cacheable` theo cách thông thường?

**Đáp án:** Lookup cache xảy ra trước khi thực thi phần thân khi có thể hit, nên chưa có result; `#result` thích hợp ở những context sau thực thi như `unless` theo quy định Spring.

## 11. Ghi nhớ và nguồn chính thức

- `#p0` = `#a0` = **đối số thứ nhất**; `#p1` = `#a1` = **đối số thứ hai**. Index bắt đầu từ 0.
- `#thamSo` như `#isbn`/`#customerId` dễ đọc nhưng cần metadata tên tham số. Với Java hiện đại, **`-parameters`** là lựa chọn chuẩn.
- `#root.args[0]` là cách khác để lấy đối số theo index.
- Biểu thức đặt trong `key`, `condition`, `unless` thuộc **evaluation context của Spring caching**; `#result` chỉ sẵn có ở những thời điểm phù hợp.
- Chọn key phải phản ánh đầy đủ các tham số ảnh hưởng đến kết quả; một cú pháp SpEL đúng chưa đồng nghĩa thiết kế cache đúng.

**Tài liệu Spring:**

- [Declarative Annotation-based Caching — tham số và evaluation context](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Cache — @Cacheable API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Java Compiler — chuẩn `-parameters`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
