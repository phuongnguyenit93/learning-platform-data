# Spring Cache: Chế độ AspectJ và điều kiện dệt mã

## Mục tiêu bài học

Trong Spring Framework, các annotation như `@Cacheable`, `@CachePut` và `@CacheEvict` không tự thực thi cơ chế cache chỉ nhờ xuất hiện trên phương thức. Spring cần một cách **chặn lời gọi phương thức** để quyết định đọc, ghi hoặc xóa cache. Chế độ mặc định dùng **Spring AOP proxy**; chế độ thay thế dùng **AspectJ weaving** để thay đổi bytecode của những lớp phù hợp.

Bài học này tập trung vào **chế độ AspectJ và các điều kiện bắt buộc để dệt mã (weaving) thực sự có hiệu lực**, đặc biệt trong bài toán self-invocation của Spring Cache. Sau bài học, bạn có thể:

- Giải thích khác biệt giữa lời gọi đi qua **proxy** và lời gọi được **AspectJ woven**.
- Biết khi nào `@EnableCaching(mode = AdviceMode.ASPECTJ)` là phù hợp.
- Phân biệt **compile-time weaving (CTW)**, **post-compile weaving** và **load-time weaving (LTW)**.
- Chuẩn bị đúng `spring-aspects`, **AspectJ weaver/agent**, cấu hình Spring và phạm vi class cần dệt.
- Hiểu vì sao `@EnableAspectJAutoProxy` hoặc thêm `aspectjweaver.jar` mà không kích hoạt weaving **chưa đủ**.
- Chạy ví dụ Java 17 cho thấy **self-invocation vẫn được cache khi weaving hoạt động**.
- Chẩn đoán các lỗi: phương thức chạy lại dù có `@Cacheable`, annotation chỉ đặt trên interface, agent không hoạt động, lớp đã load trước khi weaving, và cấu hình cache chưa sẵn sàng.

> **Ý chính:** `AdviceMode.ASPECTJ` chọn **cách áp dụng advice** của Spring Cache; nó **không tự sửa bytecode**. Để hoạt động, ứng dụng cần Spring caching aspect trong `spring-aspects.jar` **và** một bước AspectJ weaving thật sự (khi biên dịch hoặc lúc class được JVM nạp).

## 1. Vì sao Spring Cache thường gặp giới hạn self-invocation?

Hãy tưởng tượng một bean có hai phương thức:

~~~java
public class PriceService {
    public String checkoutPrice(String sku) {
        return findPrice(sku); // gọi nội bộ trên chính đối tượng
    }

    @Cacheable(cacheNames = "prices", key = "#p0")
    public String findPrice(String sku) {
        return repository.findPrice(sku);
    }
}
~~~

Đây là **đoạn minh họa**; `repository` và cấu hình cache chưa được định nghĩa trong đoạn này.

Trong **proxy mode** mặc định, đối tượng mà các bean khác nhận được có thể là một Spring proxy. Lời gọi từ bên ngoài vào `proxy.findPrice("A")` đi qua caching interceptor. Nhưng khi đang ở bên trong `PriceService`, lời gọi `this.findPrice("A")` hoặc `findPrice("A")` gọi trực tiếp phương thức trên đối tượng đích, **không quay lại proxy**. Do đó annotation cache trên `findPrice` không được áp dụng cho lời gọi nội bộ ấy.

### Sơ đồ so sánh

~~~text
PROXY MODE:

Caller -> Spring proxy -> cache advice -> target.findPrice()
                                      |
                         cache hit có thể bỏ qua target

Caller -> Spring proxy -> target.checkoutPrice()
                                |
                                +-- this.findPrice()
                                    (bỏ qua cache advice)


ASPECTJ MODE (class đã được weave):

Caller -> PriceService.checkoutPrice()
                       |
                       +-- this.findPrice()
                                  |
                       advice đã dệt vào bytecode
                                  |
                            cache hit/miss
~~~

Với AspectJ, advice được áp dụng ở **join point của phương thức đã dệt mã**, không lệ thuộc việc lời gọi có đi qua một Spring proxy hay không. Vì thế self-invocation trên một phương thức được AspectJ caching aspect nhận diện **có thể kích hoạt cache**.

Không nên chuyển toàn ứng dụng sang AspectJ chỉ vì một lời gọi nội bộ. Trước tiên hãy cân nhắc tách các trách nhiệm thành những Spring bean khác nhau để lời gọi đi qua proxy, hoặc thiết kế lại ranh giới caching. AspectJ cần quy trình build/triển khai phức tạp hơn và có chi phí kiểm thử, vận hành riêng.

## 2. Hai chế độ xử lý caching annotation

Bật cache theo mặc định:

~~~java
@Configuration
@EnableCaching
public class CacheConfig {
    // Đăng ký CacheManager ...
}
~~~

Tương đương về ý định với:

~~~java
@EnableCaching(mode = AdviceMode.PROXY)
~~~

Để yêu cầu AspectJ mode:

~~~java
import org.springframework.context.annotation.AdviceMode;
import org.springframework.cache.annotation.EnableCaching;

@EnableCaching(mode = AdviceMode.ASPECTJ)
~~~

Các đoạn trên là **cú pháp cấu hình minh họa**, không phải file Java hoàn chỉnh.

| Đặc điểm | `AdviceMode.PROXY` | `AdviceMode.ASPECTJ` |
| --- | --- | --- |
| Cơ chế | Spring AOP tạo proxy bao quanh bean | AspectJ thay đổi bytecode lớp đích |
| Lời gọi từ bên ngoài qua bean proxy | Được intercept nếu phù hợp | Được intercept nếu lớp/method đã weave và khớp aspect |
| Self-invocation trong cùng đối tượng | Không đi qua proxy nên thường không cache | Có thể được intercept vì advice nằm ở method execution |
| Cần `spring-aspects`? | Không riêng cho Spring Cache proxy | Có |
| Cần bước weave bytecode? | Không | Có: CTW, post-compile weaving hoặc LTW |
| `proxyTargetClass` có điều khiển cách weave không? | Có tác dụng với lựa chọn proxy theo cấu hình | **Không**; bị bỏ qua trong AspectJ mode |
| Annotation trên interface | Một số trường hợp proxy nhận biết được | **Không nên dùng**; AspectJ caching aspect không nhận diện annotation chỉ đặt trên interface |
| Phương thức non-public | Proxy caching thông thường không hỗ trợ theo cách mong đợi | AspectJ có thể dệt lời gọi phù hợp, tùy pointcut và môi trường |
| Độ phức tạp build/run | Thấp hơn | Cao hơn; cần kiểm tra agent, class loader, runtime weaving |
| Khả năng áp dụng lên đối tượng không đi qua proxy | Không theo semantics proxy | Có thể nếu lớp được weave và aspect đã được cấu hình đúng |

**Đừng nhầm:** `@EnableAspectJAutoProxy` chỉ bật hỗ trợ **Spring AOP dựa trên cú pháp @AspectJ**, tức vẫn tạo **proxy**. Tên annotation có chữ “AspectJ” nhưng **không tự kích hoạt AspectJ bytecode weaving**. Nó không phải bước thay thế cho agent hoặc compiler của AspectJ.

Tương tự, `@EnableCaching(proxyTargetClass = true)` chỉ thay đổi cách tạo proxy khi đang ở proxy mode. Dùng proxy dựa trên class (CGLIB) cũng **không giải quyết self-invocation**; lệnh gọi `this.method()` vẫn bỏ qua proxy.

## 3. Ba dạng dệt mã và sự khác nhau

*Weaving* là quá trình kết hợp advice/aspect với những điểm thực thi phù hợp của một class. Cùng một `@Cacheable`, AspectJ có thể tạo hiệu ứng bằng những thời điểm dệt mã khác nhau.

### 3.1. Compile-time weaving (CTW)

AspectJ compiler (`ajc`) biên dịch và dệt aspect vào **bytecode ngay trong quá trình build**. Bản `.class` hoặc JAR đầu ra đã được thay đổi. Khi chạy, thường không cần dùng `-javaagent` riêng cho những class đã weave đủ.

Cần:

- AspectJ compiler/plugin phù hợp phiên bản JDK và bytecode.
- `spring-aspects` có mặt trên **aspect path** để compiler biết aspect cần áp dụng.
- Class của ứng dụng được xử lý đúng bởi compiler, không chỉ compile bằng `javac` rồi bỏ qua bước weaving.
- Đóng gói các runtime dependencies Spring/AspectJ theo đúng ứng dụng.

Ưu điểm: có thể kiểm tra weaving trong build, tránh biến đổi lớp lúc startup. Nhược điểm: cấu hình pipeline phức tạp hơn, phải bảo đảm **mọi class cần intercept đã thực sự được weave**. Nếu build có module phát hành JAR riêng, các class thuộc module đó cũng cần được tính đến.

### 3.2. Post-compile weaving

Code Java được biên dịch thành bytecode trước, sau đó một bước AspectJ weaving xử lý **class/JAR đã biên dịch**. Dạng này hữu ích khi muốn giữ bước compile chuẩn nhưng vẫn đưa weaving vào quy trình build.

Không nên chỉ thêm một Maven plugin tên AspectJ rồi mặc định rằng mọi module đã được dệt: phải kiểm tra **inpath/aspectpath, output class, thứ tự plugin và artifact thực sự triển khai**. Nếu đóng gói nhầm bản JAR chưa weave, ứng dụng có thể khởi động nhưng self-invocation không được cache.

### 3.3. Load-time weaving (LTW)

AspectJ weaver biến đổi bytecode **khi JVM nạp class**, trước khi class được định nghĩa để thực thi. Với một ứng dụng Java độc lập, cách phổ biến là khởi động JVM kèm Java agent:

~~~bash
java -javaagent:/path/to/aspectjweaver.jar -cp "..." demo.Main
~~~

Lệnh này chỉ là **mẫu cú pháp**; ví dụ runnable cụ thể ở mục 6.

Đối với LTW, cần:

1. `aspectjweaver.jar` ở phiên bản hỗ trợ bytecode/JDK đang chạy.
2. JVM **thực sự** được khởi động với agent hoặc một cơ chế load-time weaving có `ClassFileTransformer` thích hợp.
3. Aspect cần dệt (Spring caching aspect từ `spring-aspects.jar`) có trên classpath và được khai báo để AspectJ nhận diện.
4. Class cần dệt được nạp **qua class loader chịu sự điều khiển của weaver**; class đã được định nghĩa trước khi agent/weaver tham gia không tự được retroactively weave bằng cấu hình LTW thông thường.
5. Phần Spring caching infrastructure được cấu hình (ví dụ `@EnableCaching(mode = AdviceMode.ASPECTJ)` và `CacheManager`) trước khi phương thức có cache advice được gọi.

LTW thuận tiện khi không muốn chỉnh pipeline biên dịch nhưng phụ thuộc vào **cách start JVM**. Trong container, test runner, IDE, server hoặc lệnh `java` chạy thật, phải xác nhận JVM đó nhận đúng `-javaagent`.

### So sánh theo vòng đời

~~~text
Java source
    |
    +--> ajc / compile-time weaving --------> woven .class --> JVM
    |
    +--> javac --> ordinary .class
                      |
                      +--> post-compile weave --> woven .class --> JVM
                      |
                      +--> JVM + AspectJ agent
                                      |
                                load-time weave
                                      |
                                woven loaded class
~~~

Ba đường triển khai **không bắt buộc dùng đồng thời**. Chọn một đường rõ ràng cho lớp cần intercept và kiểm chứng đầu ra. Việc weave trùng lớp trong nhiều giai đoạn có thể tạo cảnh báo hoặc hành vi khó chẩn đoán.

## 4. Điều kiện cần để Spring Cache AspectJ thật sự hoạt động

### Điều kiện A — chọn đúng caching advice mode

Một Spring `@Configuration` cần khai báo:

~~~java
@EnableCaching(mode = AdviceMode.ASPECTJ)
~~~

Spring sẽ cấu hình hạ tầng AspectJ caching thay cho proxy caching thông thường. Nếu giữ mặc định `PROXY`, việc thêm `spring-aspects` hoặc chạy một agent không tự biến **cơ chế cache được Spring cấu hình** thành AspectJ mode.

### Điều kiện B — có Spring caching aspect

Module `org.springframework:spring-aspects` chứa Spring AspectJ aspects, bao gồm:

~~~text
org.springframework.cache.aspectj.AnnotationCacheAspect
~~~

Nó khác `org.springframework:spring-aop` (hỗ trợ cơ chế proxy AOP của Spring).

Với chương trình Java độc lập trong bài, `spring-aspects` **có cùng phiên bản với Spring Framework** để tránh mismatch API. Ví dụ `spring-context:6.2.10` đi cùng `spring-aspects:6.2.10`.

`spring-aspects.jar` cũng mang theo cấu hình AspectJ `META-INF/aop.xml` định danh các aspect. Trong cấu hình LTW cơ bản với Spring aspects, **không cần tự tạo một file `aop.xml` khác** chỉ để kích hoạt `AnnotationCacheAspect`; bạn cần kiểm tra file bên trong JAR nằm trên runtime classpath.

### Điều kiện C — có cơ chế weave thực sự

Chỉ thêm dependency:

~~~xml
<dependency>
  <groupId>org.aspectj</groupId>
  <artifactId>aspectjweaver</artifactId>
  <version>1.9.22.1</version>
</dependency>
~~~

**chưa đủ** để weaving xảy ra. Dependency đưa thư viện vào classpath, nhưng class sẽ không tự biến đổi nếu không có agent/transformer hoặc bước build sử dụng `ajc`. Trong ví dụ LTW, `-javaagent:...` là mắt xích bắt buộc.

`spring-boot-starter-aop` hoặc `@EnableAspectJAutoProxy` cũng không phải tên gọi thay thế cho AspectJ LTW. Chúng thường phục vụ Spring proxy AOP.

### Điều kiện D — annotation được đặt trên class/method cụ thể

Spring khuyến nghị đặt `@Cacheable`, `@CachePut`, `@CacheEvict` trên **method của concrete class**, không chỉ trên interface:

~~~java
public interface Catalog {
    String lookup(String sku);
}

public class CatalogService implements Catalog {
    @Cacheable(cacheNames = "items", key = "#p0")
    public String lookup(String sku) {
        return "item-" + sku;
    }
}
~~~

Trong ví dụ minh họa trên, annotation được đặt **trực tiếp trên implementation**, phù hợp cho AspectJ weaving. Nếu chỉ gắn `@Cacheable` lên `Catalog.lookup` mà implementation không có annotation, **weaving-based caching aspect không nhận diện như bạn kỳ vọng**, vì annotation trên interface không được Java kế thừa xuống implementation method.

### Điều kiện E — đối tượng và hạ tầng Spring đã sẵn sàng

Khi method có cache advice được gọi, aspect phải được Spring cấu hình với `CacheManager`/`CacheResolver` và các thành phần như key generator, error handler. Trong ví dụ chạy từ `ApplicationContext`, ta lấy bean **sau khi context hoàn tất khởi tạo**.

Không gọi method có cache annotation trong constructor/`@PostConstruct` rồi kỳ vọng giống một lời gọi nghiệp vụ bình thường. Với proxy mode, bean chưa sẵn sàng qua proxy; với AspectJ, bytecode có thể đã weave nhưng caching aspect có thể chưa được cấu hình đầy đủ. Khởi tạo và vận hành là hai giai đoạn khác nhau.

## 5. Khi nào nên cân nhắc AspectJ thay cho proxy?

`AdviceMode.ASPECTJ` thường có giá trị nếu:

- Có những **self-invocation thực sự bắt buộc** phải đi qua cache advice mà việc tách bean không hợp lý.
- Cần interception các method mà proxy Spring không dễ áp dụng, sau khi đã kiểm tra điểm cắt thực tế của `AnnotationCacheAspect`.
- Ứng dụng đã có **pipeline AspectJ CTW/LTW** được kiểm thử và vận hành ổn định.
- Team đủ khả năng quản lý version weaving agent, JPMS/class loader, logging, CI và build/deploy.

Không nên chọn AspectJ chỉ vì:

- Muốn bật `@Cacheable` cho một method `public` được gọi từ bean khác: proxy mode đã đáp ứng.
- Nghĩ `proxyTargetClass = true` hoặc `@EnableAspectJAutoProxy` đương nhiên là weaving.
- Muốn cache mọi hàm, kể cả hàm có side effect hoặc trả kết quả không ổn định.
- Muốn cache hoạt động “tự động” khi Spring Context chưa được khởi tạo hoặc trong object lifecycle chưa phù hợp.

**Ưu tiên đơn giản:** Nếu chỉ cần giải quyết self-invocation ở một service, tách phương thức đã cache sang một bean khác thường ít phức tạp hơn thay đổi toàn bộ JVM/build.

## 6. Ví dụ Java 17 chạy được: self-invocation được cache nhờ LTW

Dự án sau dùng **Java 17, Maven, Spring Framework 6.2.10** và **AspectJ Weaver 1.9.22.1**. Nó đăng ký `@EnableCaching(mode = AdviceMode.ASPECTJ)` và dùng JVM `-javaagent` để dệt mã ở thời điểm load class.

Ví dụ sử dụng `ConcurrentMapCacheManager` lưu cache trong RAM để dễ quan sát. Không cần Spring Boot, Redis hay database.

### 6.1. Cấu trúc thư mục

~~~text
spring-cache-aspectj/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AspectjCachingDemo.java
~~~

Không cần tự tạo `META-INF/aop.xml` riêng cho ví dụ này vì JAR `spring-aspects` đã mang theo cấu hình aspect tương ứng.

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-cache-aspectj</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-aspects</artifactId>
      <version>6.2.10</version>
    </dependency>
    <dependency>
      <groupId>org.aspectj</groupId>
      <artifactId>aspectjweaver</artifactId>
      <version>1.9.22.1</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-dependency-plugin</artifactId>
        <version>3.8.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Maven biên dịch code Java bằng compiler plugin; sau đó dependency plugin đưa các JAR runtime vào `target/dependency`. **Dệt mã xảy ra khi JVM chạy kèm agent**, không phải vì Maven compiler tự biết về AspectJ.

### 6.3. src/main/java/demo/AspectjCachingDemo.java

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class AspectjCachingDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching(mode = AdviceMode.ASPECTJ)
    public static class Config {

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("items");
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "items", key = "#p0")
        public String load(String sku) {
            int n = loads.incrementAndGet();
            return "Item-" + sku + " (load=" + n + ")";
        }

        // Lời gọi NỘI BỘ: không đi qua Spring proxy.
        public String loadInternally(String sku) {
            return this.load(sku);
        }

        public int sourceLoads() {
            return loads.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            CatalogService service =
                context.getBean(CatalogService.class);

            System.out.println("First self: " +
                service.loadInternally("A"));
            System.out.println("Second self: " +
                service.loadInternally("A"));
            System.out.println("Direct: " + service.load("A"));
            System.out.println(
                "Source loads: " + service.sourceLoads());

            System.out.println("Other key: " +
                service.loadInternally("B"));
            System.out.println(
                "Source loads: " + service.sourceLoads());
        }
    }
}
~~~

Các chỗ quan trọng:

1. `Config` dùng `@EnableCaching(mode = AdviceMode.ASPECTJ)`: chọn caching aspect thay cho proxy advice.
2. `spring-aspects` cung cấp `AnnotationCacheAspect`.
3. Lệnh chạy JVM phải có **AspectJ agent** để `CatalogService.load` thực sự được weave.
4. `loadInternally` dùng `this.load(sku)`. Đây là nơi **proxy mode** thường bỏ qua annotation. Nếu weaving hoạt động, AspectJ advice chặn thực thi `load` dù được gọi trong cùng đối tượng.
5. `loads` đo số lần thân method thực sự chạy. Cache hit trả lại giá trị ban đầu mà không tăng bộ đếm.
6. Service được Spring quản lý và lấy từ context trước khi gọi nghiệp vụ.

### 6.4. Chạy trên Linux/macOS với Java 17

Tại thư mục chứa `pom.xml`:

~~~bash
mvn -q -DskipTests package dependency:copy-dependencies
java -javaagent:target/dependency/aspectjweaver-1.9.22.1.jar \
     -cp "target/classes:target/dependency/*" \
     demo.AspectjCachingDemo
~~~

`-javaagent` là **JVM argument**, phải đặt trước tên main class. Dấu `:` trong classpath là ký tự phân tách trên Linux/macOS.

Trên **Windows PowerShell**, dùng dấu `;` cho classpath:

~~~powershell
mvn -q -DskipTests package dependency:copy-dependencies
java -javaagent:target/dependency/aspectjweaver-1.9.22.1.jar -cp "target/classes;target/dependency/*" demo.AspectjCachingDemo
~~~

Dùng đường dẫn `target/dependency` thay vì tự đoán nơi Maven lưu artifact: lệnh `dependency:copy-dependencies` đã tạo bản JAR runtime ở thư mục đó. Nếu dùng IDE/Gradle/Fat JAR, cơ chế start JVM và vị trí của weaver JAR sẽ khác, nhưng nguyên tắc agent và runtime classpath vẫn giữ nguyên.

### 6.5. Kết quả mong đợi

Những dòng **chương trình tự in ra** (không tính thông báo của JVM/weaver và Maven) là:

~~~text
First self: Item-A (load=1)
Second self: Item-A (load=1)
Direct: Item-A (load=1)
Source loads: 1
Other key: Item-B (load=2)
Source loads: 2
~~~

Giải thích:

- `loadInternally("A")` lần đầu gọi `load("A")`, key `"A"` chưa có nên `loads` tăng thành 1; kết quả được lưu trong cache `items`.
- Lần thứ hai gọi **trong cùng đối tượng**, nhưng do `load` đã được weave, advice xử lý cache hit; thân method không chạy lại.
- Lời gọi trực tiếp `service.load("A")` cũng hit cùng entry `"A"`, kết quả vẫn mang `load=1`.
- `loadInternally("B")` sinh key khác nên miss, `loads` tăng thành 2.

Nếu chỉ thay `@EnableCaching(mode = AdviceMode.ASPECTJ)` nhưng **quên agent hoặc bước weaving**, không được coi output trên là bảo đảm. Ứng dụng có thể khởi động nhưng không intercept đúng phương thức, hoặc có lỗi cấu hình khác. Phải dùng integration test quan sát số lần phương thức nguồn chạy và xác nhận weaving trong log/bytecode.

### 6.6. Điều kiện để ví dụ hợp lệ

- Cả `spring-context` và `spring-aspects` dùng cùng Spring Framework version.
- JDK thực thi là 17 hoặc phiên bản được bộ AspectJ weaver đã chọn hỗ trợ.
- Java agent **được nạp vào JVM thực thi ứng dụng**, không chỉ JVM thực thi một lệnh build khác.
- `spring-aspects` có trên runtime classpath để weaver tìm thấy caching aspect.
- `CatalogService` được nạp sau khi weaver sẵn sàng và method được weave thành công.
- `@Cacheable` đặt trên **concrete method** `CatalogService.load`, không chỉ interface.
- `CacheManager` có vùng `items`, và `ApplicationContext` hoàn thành trước khi gọi.
- Ví dụ dùng một thread; khi đưa vào môi trường concurrent, cache stampede và transaction là vấn đề độc lập.

## 7. META-INF/aop.xml dùng để làm gì?

AspectJ LTW có thể đọc một hoặc nhiều file `META-INF/aop.xml` trên classpath. File này khai báo các aspect và tùy chọn weaving, chẳng hạn giới hạn phạm vi những class sẽ được dệt.

Trong trường hợp **Spring Cache AspectJ chuẩn**, `spring-aspects.jar` có `META-INF/aop.xml` khai báo `org.springframework.cache.aspectj.AnnotationCacheAspect` cùng một số aspect khác của Spring. Vì vậy demo mục 6 không yêu cầu bạn tự thêm file cấu hình riêng.

Một ví dụ **minh họa** về cấu trúc cấu hình LTW cho một aspect tự phát triển:

~~~xml
<!DOCTYPE aspectj PUBLIC "-//AspectJ//DTD//EN"
  "https://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
  <weaver options="-showWeaveInfo">
    <include within="demo..*"/>
  </weaver>
  <aspects>
    <aspect name="demo.PerformanceAspect"/>
  </aspects>
</aspectj>
~~~

Đây **không phải file cần tạo cho demo caching**; `demo.PerformanceAspect` chỉ là tên ví dụ và không nằm trong dự án runnable. Khi tự quản lý `aop.xml` trong một dự án khác, phải dùng tên aspect có thật, xét các `aop.xml` đã có trong JAR phụ thuộc, tránh khai báo trùng hoặc phạm vi weave mâu thuẫn.

Giới hạn phạm vi weave có thể giúp giảm chi phí startup, warning và tránh tác động lên những thư viện không cần thiết. Tuy nhiên, cấu hình filter quá hẹp cũng khiến class có `@Cacheable` **không được weave**, và hành vi cache không xuất hiện.

### Kiểm tra cấu hình của JAR

Trên hệ thống có JDK, có thể kiểm tra đường dẫn file:

~~~bash
jar tf target/dependency/spring-aspects-6.2.10.jar
~~~

Tìm mục `META-INF/aop.xml` trong danh sách. Đây là **bước chẩn đoán classpath**, không khẳng định agent đã thực hiện weaving.

## 8. Có cần @EnableLoadTimeWeaving hoặc spring-instrument không?

Spring còn cung cấp cơ chế **Spring-managed load-time weaving** thông qua `@EnableLoadTimeWeaving`, `LoadTimeWeaver`, `InstrumentationLoadTimeWeaver` và các lớp tích hợp container. Cơ chế này khác việc khởi động trực tiếp JVM với **AspectJ agent**.

Hai đường thường gặp:

1. **AspectJ agent trực tiếp** (`-javaagent:aspectjweaver.jar`): agent tự lắp bộ biến đổi class theo cơ chế của AspectJ. Đây là đường được trình bày ở demo. Không cần thêm `@EnableLoadTimeWeaving` chỉ để minh họa luồng này.
2. **Spring-managed LTW**: Spring cấu hình `LoadTimeWeaver` trên class loader thích hợp. Một số môi trường ứng dụng hỗ trợ instrumentation trực tiếp; trong môi trường Java độc lập, có thể cần `-javaagent:spring-instrument.jar` để cung cấp JVM instrumentation cho cơ chế này. Vẫn phải có AspectJ weaving infrastructure và caching aspect phù hợp.

**Không coi hai loại agent là đồng nhất:** `spring-instrument.jar` hỗ trợ cơ chế instrumentation do Spring quản lý; `aspectjweaver.jar` chứa bộ dệt mã AspectJ. Tùy đường thiết lập LTW, các yêu cầu agent và transformer khác nhau. Đừng thêm nhiều agent vô điều kiện để “chắc chắn chạy”; hãy chọn một mô hình và kiểm chứng classloader thực tế.

### Chú ý trong ứng dụng Spring Boot

Spring Boot tạo và đóng gói classpath theo cơ chế riêng (fat JAR/nested JAR). Khi triển khai bằng `java -jar`, phải xác minh **agent được truyền cho đúng JVM** và có thể nhìn thấy metadata/aspect/class cần weave. Trong container, startup script, Kubernetes hoặc IDE, kiểm tra danh sách JVM arguments thực tế; chỉ đặt dependency trong `pom.xml` không đảm bảo agent được bật.

## 9. AspectJ và các loại phương thức đặc biệt

### 9.1. Annotation chỉ đặt trên interface

~~~java
public interface ItemReader {
    @Cacheable(cacheNames = "items")
    String load(String code);
}

public class ItemReaderImpl implements ItemReader {
    @Override
    public String load(String code) {
        return "item-" + code;
    }
}
~~~

Đây là **phản ví dụ đối với AspectJ mode**. Java không kế thừa annotation trên interface method vào implementation method. Caching aspect dựa trên weaving không nhận diện cấu hình chỉ được khai báo trên interface theo cách bạn mong đợi. Di chuyển annotation xuống method trong concrete class.

### 9.2. Phương thức non-public

Proxy caching thường chỉ hỗ trợ các public method theo khuyến nghị của Spring. AspectJ bytecode weaving có thể xử lý những join point mà proxy không có cách intercept, bao gồm một số phương thức không public, **khi aspect pointcut khớp**. Nhưng không suy ra rằng mọi private/static/constructor đều được xử lý bởi Spring Cache.

`@Cacheable` là annotation cho **method** và Spring caching aspect có phạm vi pointcut cụ thể. Với những trường hợp non-public hoặc bytecode do framework khác sinh ra, kiểm tra log weave và integration test thay vì chỉ nhìn annotation.

### 9.3. Class và method final

Proxy dựa trên subclass không thể override method final. AspectJ weaving sửa bytecode ở class đích nên không phụ thuộc vào subclass override theo cách đó. Tuy nhiên, cần kiểm thử class thực tế với bytecode của Kotlin/records/final classes, module boundaries và công cụ tạo mã.

### 9.4. Đối tượng không được khởi tạo bằng Spring

AspectJ weaving là cơ chế biến đổi class nên không chỉ phụ thuộc vào việc object được Spring proxy. Nhưng Spring Cache advice vẫn cần các thành phần caching infrastructure đã cấu hình và một cache name/key hợp lệ. Đừng coi khả năng weave class là bảo đảm object bất kỳ, ở bất cứ thời điểm nào, đều cache đúng theo ngữ cảnh nghiệp vụ hoặc transaction.

### 9.5. Custom/meta-annotation

Spring Cache có thể hỗ trợ custom/meta-annotation trong proxy-based infrastructure, nhưng caching aspect chuẩn từ `spring-aspects` chủ yếu được thiết kế cho **những annotation cache chuẩn**. Nếu dùng annotation tự định nghĩa và mong AspectJ nhận diện, có thể phải xây dựng/customize aspect hoặc pointcut phù hợp. Không giả định chỉ vì proxy mode hiểu một meta-annotation thì AspectJ aspect sẽ áp dụng y hệt.

## 10. Chẩn đoán khi đã bật AspectJ mà cache không có hiệu lực

Thực hiện kiểm tra có thứ tự:

1. **Chế độ đúng chưa?** Xác nhận config đang chạy có `@EnableCaching(mode = AdviceMode.ASPECTJ)`, không phải cấu hình `PROXY` khác ghi đè ngoài dự kiến.
2. **Có `spring-aspects` đúng version không?** Xác nhận JAR có ở runtime classpath và chứa `AnnotationCacheAspect` cùng `META-INF/aop.xml`.
3. **JVM chạy thật có agent không?** Xem startup command/process arguments của JVM ứng dụng. Lệnh Maven build hoặc một IDE runner khác không thể thay cho agent ở JVM phục vụ request.
4. **Agent có tương thích bytecode/JDK không?** Kiểm tra AspectJ version, JVM version và warning về class file format.
5. **Class có bị load quá sớm không?** LTW thường chỉ dệt lúc class được nạp; nếu class đã load trước khi transformer hoạt động, cấu hình mới không thay đổi class ấy.
6. **Pointcut có match không?** Kiểm tra annotation có trên concrete method hay chỉ interface, method signature, scope weave, exclude/include filter.
7. **Spring caching aspect đã được cấu hình chưa?** Xác nhận context sẵn sàng, `CacheManager`/`CacheResolver` được đăng ký và tên cache tồn tại.
8. **Lời gọi có thực sự đi đến method được annotate không?** Test qua business path thật; không dựa vào reflection hay unit test chỉ đọc annotation.
9. **Có một layer caching khác đang can thiệp?** Khi proxy caching và AspectJ advice cùng tồn tại do cấu hình chồng chéo, có nguy cơ hành vi khó đoán. Tách rõ trách nhiệm.
10. **Có ngoại lệ cache provider không?** Tên cache không tồn tại, key sai, backend timeout hoặc error handler có thể tạo triệu chứng giống “cache không chạy”.

### Cách chứng minh weaving thực sự diễn ra

Đừng chỉ đo thời gian response. Dùng một **counter trong thân phương thức** như demo: cùng key gọi hai lần nhưng counter tăng một lần nếu caching hoạt động.

Có thể bật logging/information của AspectJ weaver theo cơ chế cấu hình phù hợp để quan sát các join point đã weave. Với ứng dụng production, nên tắt log weave quá chi tiết sau khi chẩn đoán.

### Phân biệt 3 kiểu lỗi

| Dấu hiệu | Khả năng | Kiểm tra |
| --- | --- | --- |
| Self-invocation chạy thân method mỗi lần, không exception | Method chưa được weave hoặc chưa có advice đúng | JVM agent, aop.xml, pointcut, config mode |
| Có cache advice nhưng ném lỗi “Cannot find cache...” | Tên cache không được manager giải quyết | CacheManager, cacheNames, profile |
| Method cache hit nhưng dữ liệu sai/cũ | Key/invalidation/business data không đúng | Key generator, TTL, @CacheEvict, transaction |
| JVM crash/không khởi động khi bật agent | Agent/JDK/class loader/module không tương thích | Version weaver, JVM flags, logs |
| Annotation trên interface hoạt động ở proxy nhưng không ở AspectJ | Annotation không có trên concrete implementation | Di chuyển annotation |
| `@EnableAspectJAutoProxy` bật nhưng self-invocation không cache | Đang dùng proxy, không có bytecode weaving | `AdviceMode.ASPECTJ` + weave thực tế |

## 11. Ảnh hưởng đến transaction, concurrency và hiệu năng

AspectJ giải quyết **cách intercept**; nó **không giải quyết mọi tính chất của cache**:

- **Stale data:** `@Cacheable` chỉ tái sử dụng dữ liệu; khi database đổi, vẫn phải có chính sách `@CacheEvict`, `@CachePut`, TTL hoặc invalidation phù hợp.
- **Transaction:** bytecode đã weave không biến database update và cache put/evict thành một giao dịch nguyên tử. Cần xét commit order, rollback và transaction-aware cache.
- **Concurrency:** nhiều request miss cùng key có thể gây load trùng hoặc cache stampede; giải quyết bằng cache/provider hoặc `sync` khi đáp ứng điều kiện, không phải chỉ bật AspectJ.
- **Performance:** LTW có thể tăng thời gian startup/chi phí transformer; CTW tăng chi phí build. Method interception và cache operations vẫn có overhead ở runtime. Đo bằng benchmark phù hợp workload.
- **Tracing/debugging:** stack trace, bytecode và thứ tự advice có thể khác proxy mode. Nếu đang dùng security/transaction/retry aspects, cần kiểm thử thứ tự tương tác và khả năng lỗi.
- **Native image/AOT/JPMS:** các môi trường không hỗ trợ sửa bytecode động như JVM thông thường có thể yêu cầu thiết kế khác; không coi LTW là mặc định tương thích mọi deployment.
- **Scope:** weaving quá rộng gây overhead hoặc warning không cần thiết; weaving quá hẹp bỏ sót các class cần cache.

Không nên dùng annotation caching để “bỏ qua” phương thức có side effect bắt buộc. AspectJ làm interception diễn ra trên nhiều đường gọi hơn, nên những side effect bị bỏ qua bởi cache hit cũng có thể xuất hiện ở **nhiều vị trí trước đây không được cache**. Khi chuyển chế độ, cần kiểm tra lại tính thuần của method.

## 12. Checklist chuyển từ PROXY sang ASPECTJ

### Kiểm tra trước khi đổi

- [ ] Có vấn đề thực sự mà proxy mode không giải quyết hợp lý (chẳng hạn self-invocation bắt buộc).
- [ ] Đã cân nhắc giải pháp tách bean, thay vì đổi hạ tầng weave toàn ứng dụng.
- [ ] Các method có cache annotation không phụ thuộc vào side effect mỗi lần gọi.
- [ ] `@Cacheable/@CachePut/@CacheEvict` nằm trên concrete method cần được weave.
- [ ] Biết Spring Framework version, JDK version và AspectJ version sẽ triển khai.
- [ ] Chọn duy nhất đường **CTW/post-compile weaving** hoặc **LTW** có thể kiểm chứng.

### Kiểm tra cấu hình

- [ ] `@EnableCaching(mode = AdviceMode.ASPECTJ)` nằm trong Spring context phù hợp.
- [ ] `spring-aspects` trên runtime/aspect path, cùng version với Spring Framework.
- [ ] Nếu dùng LTW, JVM thực thi nhận đúng agent/transformer.
- [ ] `META-INF/aop.xml` có khai báo caching aspect, hoặc cấu hình tương đương đã kiểm chứng.
- [ ] Lớp cần weave được nạp trong phạm vi weaver hoạt động.
- [ ] CacheManager/CacheResolver, cacheNames, key generator có cấu hình hợp lệ.
- [ ] Không kỳ vọng `@EnableAspectJAutoProxy` hoặc `proxyTargetClass` thay thế weaving.

### Kiểm tra sau deploy

- [ ] Test trực tiếp **self-invocation**: cùng key hai lần, thân method chỉ chạy một lần.
- [ ] Test gọi từ bean khác và trường hợp nhiều key khác nhau.
- [ ] Test cache put/evict, kết quả null/exception theo business contract.
- [ ] Test transaction rollback, cache backend error và lời gọi concurrent.
- [ ] Test startup ở đúng runtime thực tế: IDE, jar/container, server/test runner.
- [ ] Kiểm tra logs/metrics cho cache hit/miss và thông tin weave phù hợp.
- [ ] Có rollback plan về proxy mode nếu weaving không tương thích môi trường.

## 13. Câu hỏi tự kiểm tra

**1.** `@EnableCaching(mode = AdviceMode.ASPECTJ)` có tự sửa bytecode class không?  
**Đáp án:** Không. Nó chọn cấu hình caching AspectJ; vẫn cần `spring-aspects` và quá trình weaving thực tế.

**2.** Vì sao `this.load(id)` thường bỏ qua `@Cacheable` ở proxy mode?  
**Đáp án:** Lời gọi nội bộ không đi qua Spring proxy. Với AspectJ, advice có thể nằm trong bytecode method đã weave.

**3.** Chỉ thêm `aspectjweaver` dependency vào Maven có đủ để LTW hoạt động không?  
**Đáp án:** Không. Phải bật agent hoặc một cơ chế LTW có transformer phù hợp tại JVM nạp class.

**4.** `@EnableAspectJAutoProxy` có tương đương native AspectJ weaving không?  
**Đáp án:** Không. Nó cấu hình Spring AOP proxy, dù dùng cú pháp @AspectJ.

**5.** Trong CTW, Java agent lúc chạy có luôn bắt buộc không?  
**Đáp án:** Không, nếu các class cần advice đã được weave đầy đủ trong build và runtime có các thư viện cần thiết.

**6.** Có nên đặt `@Cacheable` chỉ trên interface khi dùng AspectJ mode?  
**Đáp án:** Không. Đặt annotation trên implementation method/concrete class.

**7.** Vì sao cách dùng `proxyTargetClass=true` không chữa self-invocation?  
**Đáp án:** Nó chỉ điều khiển loại proxy, không biến lời gọi `this.method()` thành lời gọi đi qua proxy.

**8.** `spring-aspects.jar` cung cấp gì cho caching AspectJ?  
**Đáp án:** Spring caching aspect, trong đó có `AnnotationCacheAspect`, cùng cấu hình AspectJ để nhận diện aspect.

**9.** Một class đã được JVM định nghĩa trước khi bật LTW có tự weave lại không?  
**Đáp án:** Không theo cơ chế LTW thông thường. Cần agent/weaver hoạt động trước thời điểm nạp class cần intercept.

**10.** Vì sao output demo nên dựa vào bộ đếm thay vì chỉ nhìn thời gian chạy?  
**Đáp án:** Bộ đếm cho thấy trực tiếp số lần thân phương thức chạy, chứng minh được cache hit khi self-invocation.

**11.** Nếu class đã weave nhưng cache không tồn tại, AspectJ có tự tạo vùng cache đúng không?  
**Đáp án:** Không. Việc tìm/tạo vùng cache vẫn do CacheManager/CacheResolver và chính sách provider quyết định.

**12.** Đổi sang AspectJ có làm cache put/evict và DB transaction nguyên tử không?  
**Đáp án:** Không. AspectJ thay cơ chế interception, không thay thiết kế nhất quán dữ liệu và transaction.

## Tài liệu tham khảo

- Spring Framework Reference — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — Using AspectJ with Spring Applications: https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html
- Spring Framework Reference — Enabling @AspectJ Support (phân biệt proxy với weaving): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework API — EnableCaching: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/annotation/EnableCaching.html
- Spring Framework spring-aspects META-INF/aop.xml: https://github.com/spring-projects/spring-framework/blob/main/spring-aspects/src/main/resources/META-INF/aop.xml
- AspectJ project — Java bytecode/JDK compatibility: https://github.com/eclipse-aspectj/aspectj/blob/master/docs/release/JavaVersionCompatibility.adoc
