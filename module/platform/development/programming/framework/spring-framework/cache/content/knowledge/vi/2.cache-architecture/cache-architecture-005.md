# CacheInterceptor, metadata annotation và luồng xử lý lời gọi trong Spring Framework

## 1. Mục tiêu và bức tranh tổng quan

Spring Cache là **lớp trừu tượng** để áp dụng caching cho lời gọi phương thức. Annotation khai báo *khi nào đọc/ghi/xóa cache*; Spring AOP chặn lời gọi, rồi giao tiếp với cache provider thông qua các interface của Spring. Spring không tự quy định thời gian sống (TTL), chính sách loại bỏ theo dung lượng, tính bền vững hay việc phân tán dữ liệu: các khả năng đó thuộc về cache backend (ConcurrentMap, Caffeine, Redis, v.v.).

Tập trung vào ba câu hỏi:

1. Vì sao một lời gọi `service.findById(42)` có thể trả kết quả mà không chạy thân phương thức?
2. Spring tìm và diễn giải metadata từ `@Cacheable`, `@CachePut`, `@CacheEvict`, `@Caching` và `@CacheConfig` như thế nào?
3. Trong một lời gọi thực tế, `CacheInterceptor` quyết định thứ tự tra cache, gọi business method và cập nhật cache ra sao?

**Phân biệt cốt lõi:** `CacheInterceptor` là advice chặn phương thức; `CacheOperationSource` trả về *định nghĩa hoạt động* từ annotation; `CacheAspectSupport` xử lý luồng thực thi; `CacheResolver` chọn những cache cụ thể; `KeyGenerator` hoặc SpEL chọn key; `CacheManager` và `Cache` cung cấp nơi lưu dữ liệu.

## 2. Các thành phần và trách nhiệm

| Thành phần | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `@EnableCaching` | Kích hoạt hạ tầng caching dựa trên annotation trong Spring context. | Có annotation trên method thôi chưa đủ; phải có cấu hình caching và cache phù hợp. |
| `BeanFactoryCacheOperationSourceAdvisor` cùng pointcut | Cho Spring AOP biết phương thức nào có cache operation và cần advice. | Dựa vào `CacheOperationSource`; chỉ lời gọi đi qua proxy mới được chặn trong proxy mode mặc định. |
| `CacheInterceptor` | AOP Alliance `MethodInterceptor` nhận `MethodInvocation` và chuyển sang cơ chế xử lý caching. | Lớp này kế thừa `CacheAspectSupport`; logic cache chủ yếu ở lớp cha, không nằm trong business method. |
| `CacheOperationSource` | Tra metadata phù hợp với method và target class. | Triển khai annotation phổ biến là `AnnotationCacheOperationSource`. |
| `SpringCacheAnnotationParser` | Chuyển annotation/cấu hình thành các đối tượng mô tả cache operation. | Hỗ trợ cả annotation tổng hợp và meta-annotation; `@Caching` có thể khai báo nhiều operation. |
| `CacheOperation` | Mô hình metadata bất biến cho một hoạt động: cache names, key, condition, resolver, v.v. | Các dạng gồm `CacheableOperation`, `CachePutOperation`, `CacheEvictOperation`. |
| `CacheAspectSupport` | Xây ngữ cảnh từng lời gọi, kiểm tra hit/miss, điều kiện, điều phối invoke/put/evict. | Xử lý metadata và SpEL, kể cả một số nhánh xử lý đồng bộ/bất đồng bộ. |
| `CacheResolver` | Quyết định tập `Cache` dùng cho operation. | `SimpleCacheResolver` thường lấy cache theo tên từ `CacheManager`. |
| `KeyGenerator` | Tạo key từ target, method và arguments khi không có SpEL `key`. | Mặc định `SimpleKeyGenerator`. |
| `CacheManager` / `Cache` | Cung cấp vùng cache và các thao tác `get`, `put`, `evict`, `clear`. | Hành vi TTL, serialization, chia sẻ giữa node và atomicity tùy provider. |
| `CacheErrorHandler` | Chính sách xử lý lỗi khi thao tác với cache. | Mặc định `SimpleCacheErrorHandler` sẽ ném lỗi cache lên caller. |

### Hai pha cần phân biệt

**Pha cấu hình:** Spring xử lý `@EnableCaching`, tạo `CacheOperationSource`, interceptor và advisor; AOP quyết định bean/phương thức nào cần proxy. Cơ chế chính trong proxy mode bao gồm `ProxyCachingConfiguration`, `CacheInterceptor` và advisor. Spring có thể kiểm tra cache metadata để khớp pointcut.

**Pha gọi phương thức:** Caller gọi bean qua proxy. Interceptor lấy method, target và arguments, tra `CacheOperationSource` rồi thực thi theo operation. Việc quét annotation không nhất thiết lặp lại nguyên vẹn ở mỗi request: `AbstractFallbackCacheOperationSource` cache kết quả phân giải theo method/target class; `CacheAspectSupport` cũng giữ metadata đã chuẩn bị như key generator và resolver.

## 3. Từ annotation thành metadata thực thi

Ví dụ khai báo:

~~~java
@CacheConfig(cacheNames = "products")
public class ProductService {
    @Cacheable(key = "#p0", condition = "#p0 > 0",
               unless = "#result == null")
    public Product find(long id) {
        // Đọc từ kho dữ liệu
        return repository.findById(id).orElse(null);
    }
}
~~~

Đoạn này là **minh họa bên trong một ứng dụng Spring đã có `Product`, `repository` và cấu hình cache**, chưa phải một file Java độc lập.

Một cách khái niệm, các bước phân giải metadata là:

1. `CacheOperationSource` nhận cặp `(Method, targetClass)`, tìm phương thức triển khai cụ thể và các khai báo phù hợp trên method/class theo quy tắc của Spring.
2. `AnnotationCacheOperationSource` dùng parser hiểu `@Cacheable` và các annotation liên quan; ghép các mặc định cấp lớp từ `@CacheConfig` khi cần.
3. Spring xây đối tượng `CacheableOperation` chứa tên cache `products`, chuỗi SpEL `#p0`, `condition` và `unless`; không phải kết quả evaluate SpEL của một lần gọi cụ thể.
4. `CacheAspectSupport` phân giải và có thể cache `CacheOperationMetadata`, bao gồm cấu hình `CacheResolver`/`KeyGenerator` cho operation; mỗi lần gọi lại tạo ngữ cảnh để đánh giá trên arguments, target và kết quả hiện tại.
5. `@CacheConfig` chỉ là cấu hình mặc định; **tự nó không tạo hoạt động cache**. Giá trị trên annotation method được ưu tiên hơn mặc định cấp lớp; cấu hình chung đặt qua `CachingConfigurer` hoặc cache infrastructure là mức còn lại.

Ví dụ `@Cacheable(cacheNames = "products", key = "#p0")` khai báo cách tạo key; trong lúc runtime, `#p0` mới được thay bằng argument thứ nhất của lần gọi, chẳng hạn `42`. Vì vậy **annotation metadata ổn định** và **giá trị key/condition của invocation** là hai thứ khác nhau.

### Các annotation tương ứng với operation nào?

| Annotation | Cách xử lý chính | Thời điểm có ý nghĩa |
| --- | --- | --- |
| `@Cacheable` | Đọc cache trước; nếu hit hợp lệ có thể không gọi method; nếu miss, gọi method rồi put. | `condition` trước khi đọc; `unless` sau khi có kết quả, trước khi put. |
| `@CachePut` | Vẫn gọi method; sau đó ghi kết quả vào cache nếu thỏa điều kiện. | Phù hợp cập nhật hoặc làm mới dữ liệu, không thay thế việc chạy method. |
| `@CacheEvict` | Xóa một key hoặc toàn bộ entries của một vùng cache. | Mặc định sau khi method hoàn thành thành công; `beforeInvocation = true` xóa trước. |
| `@Caching` | Gom nhiều khai báo cache operation trên một method. | Mỗi operation có tên cache/key/condition riêng. |
| `@CacheConfig` | Khai báo defaults tại cấp class: cache names, manager, resolver, key generator. | Không thực thi get/put/evict nếu thiếu annotation operation. |

Có thể định nghĩa **meta-annotation** gắn `@Cacheable` lên annotation tự tạo để tái sử dụng chính sách, ví dụ `@Retention(RUNTIME)` và `@Target(METHOD)` kết hợp với `@Cacheable("products")`. Đừng nhầm metadata annotation với dữ liệu cache: metadata mô tả *quy tắc*, còn `Cache` lưu các *giá trị đã tính*.

## 4. Luồng gọi chi tiết của CacheInterceptor

### 4.1. Đường đi thông thường của `@Cacheable`

~~~mermaid
sequenceDiagram
    participant Caller
    participant Proxy as Spring AOP proxy
    participant I as CacheInterceptor
    participant S as CacheOperationSource
    participant R as CacheResolver/Key logic
    participant C as Cache
    participant T as Target method

    Caller->>Proxy: find(42)
    Proxy->>I: invoke(MethodInvocation)
    I->>S: getCacheOperations(method, targetClass)
    S-->>I: CacheableOperation
    I->>R: evaluate condition, resolve caches and key
    R-->>I: cache products, key 42
    I->>C: get(42)
    alt Cache hit
        C-->>I: cached value
        I-->>Proxy: cached value
    else Cache miss
        C-->>I: missing entry
        I->>T: invocation.proceed()
        T-->>I: computed value
        I->>I: evaluate unless against result
        opt Put is allowed
            I->>C: put(42, computed value)
        end
        I-->>Proxy: computed value
    end
    Proxy-->>Caller: return value
~~~

Sơ đồ biểu diễn nhánh cơ bản của một `@Cacheable` đồng bộ, một cache, không kết hợp operation khác; triển khai nội bộ có nhiều nhánh tối ưu và trường hợp đặc biệt. Nếu `condition` sai thì method vẫn chạy, không thực hiện caching cho `@Cacheable` đó. Khi hit, `unless` không phải bước kiểm tra lại bản ghi cũ: nó dùng **kết quả mới sau invoke** để quyết định có put hay không.

Ở mức API nội bộ:

- `CacheInterceptor.invoke(MethodInvocation)` cung cấp bộ gọi business method dựa trên `invocation.proceed()`, rồi đi vào `CacheAspectSupport.execute(...)`.
- `execute` thu thập operation hợp lệ, tạo `CacheOperationContext` với method, args, target, caches và metadata. `CacheAspectSupport` sử dụng `invokeOperation` khi cần gọi target.
- Với `@Cacheable`, thực thi kiểm tra điều kiện trước, tìm giá trị đã cache, phân biệt miss và giá trị cache hợp lệ; trên miss, gọi target, xét `unless` và ghi cache nếu được phép.
- Ngoài luồng trên còn có xử lý evict trước/sau, put request, đồng bộ `sync=true`, kết quả dạng bất đồng bộ, lỗi cache và việc phối hợp nhiều operation. Không nên tự suy diễn thuật toán thành một câu “interceptor luôn get → invoke → put”.

### 4.2. Khi hit và khi miss khác nhau điều gì?

| Hiện tượng | Cache hit hợp lệ | Cache miss |
| --- | --- | --- |
| Tìm metadata/kiểm tra điều kiện | Có | Có |
| Tính key và tra cache | Có | Có |
| Thân `find(...)` | **Không chạy** trong nhánh cacheable thông thường | **Chạy** |
| Kết quả trả về | Từ cache | Từ target method |
| Ghi cache | Không cần trong trường hợp một cache đã hit; với nhiều cache có thể bổ sung cache còn thiếu | Ghi sau invoke nếu không bị `unless` chặn |

Một `@Cacheable` chỉ thực sự có lợi khi lời gọi đi qua caching advice, key phản ánh đúng dữ liệu cần phân biệt, giá trị được cache còn hợp lệ và cache backend đáp ứng tính nhất quán mong muốn.

### 4.3. `@CachePut` và `@CacheEvict` trên cùng đường đi

- **`@CachePut`:** không dùng cache hit để bỏ qua business method; method vẫn thực thi, kết quả cuối cùng được put nếu operation hợp lệ. Ví dụ cập nhật entity rồi `@CachePut(cacheNames = "products", key = "#result.id")` để làm mới bản ghi vừa lưu. `#result` có sau invoke và cần xử lý kết quả null.
- **`@CacheEvict` mặc định:** chạy method trước, nếu thành công thì evict key; nếu method ném exception, eviction sau lời gọi thường không chạy. `@CacheEvict(beforeInvocation = true)` làm eviction **trước** khi chạy method, kể cả khi sau đó method thất bại.
- **`allEntries = true`:** xóa toàn bộ entries của cache đã chọn, không dùng key cho thao tác xóa này; cần cân nhắc tác động lên tất cả caller.
- **Nhiều operation:** `@Caching` cho phép khai báo nhiều put/evict khác nhau, nhưng việc ghép `@Cacheable` và `@CachePut` trên cùng method thường tạo kỳ vọng mâu thuẫn: một cái có thể bỏ qua invoke, cái kia cần invoke. Chỉ dùng khi đã phân tích và kiểm thử điều kiện loại trừ.

## 5. Key, cache resolution và SpEL trong invocation

### 5.1. Tạo key

Nếu không đặt `key` và không chỉ định `keyGenerator`, `SimpleKeyGenerator` mặc định tạo:

- Không argument: `SimpleKey.EMPTY`.
- Một argument: chính argument đó (với một số xử lý riêng cho array).
- Nhiều arguments: một `SimpleKey` chứa các argument theo thứ tự.

Key phải ổn định và có ý nghĩa theo `equals()/hashCode()`. Nếu một object có trạng thái biến đổi sau khi được dùng làm key, hoặc key bỏ sót tenant, locale, vai trò người dùng, pagination hay một tham số ảnh hưởng kết quả, cache có thể trả dữ liệu sai hoặc rò rỉ dữ liệu giữa ngữ cảnh. Tên cache không tự động bổ sung các yếu tố đó vào key.

Cách viết SpEL minh họa:

~~~java
@Cacheable(cacheNames = "catalog", key = "#p0 + ':' + #p1")
public Product lookup(String tenantId, String sku) {
    // ...
}

@Cacheable(cacheNames = "catalog", key = "#root.methodName + ':' + #p0")
public Product lookupById(long id) {
    // ...
}
~~~

Đây là các **method minh họa**, cần đặt trong Spring bean có implementation tương ứng. Có thể dùng `#a0` hoặc `#p0` theo vị trí; dùng `#argumentName` chỉ khi tên parameter thực sự có trong metadata biên dịch, thường cần `-parameters`. `#root.methodName`, `#root.targetClass`, `#root.args` và `#root.caches` cung cấp ngữ cảnh cho SpEL.

`key = "..."` và `keyGenerator = "beanName"` loại trừ nhau. Chỉ định một chính sách rõ ràng; nếu tạo custom `KeyGenerator`, nên kiểm thử sự ổn định của key qua nhiều node và nhiều phiên bản code.

### 5.2. Chọn cache

`cacheNames = "products"` chỉ tên vùng cache. `CacheResolver` chọn đối tượng `Cache` cụ thể; mặc định resolver dùng `CacheManager` đã cấu hình. Có thể chọn `cacheManager` hoặc `cacheResolver` trên operation, nhưng không khai báo đồng thời hai thuộc tính loại trừ nhau. Trường hợp multi-tenant/multi-region có thể cần custom resolver, song phải đảm bảo mỗi request được gán đúng cache.

Nếu `@Cacheable` cấu hình **nhiều cache**, Spring có thể kiểm tra từng cache để tìm hit và đồng bộ giá trị sang cache chưa có dữ liệu; không nên mặc định rằng tất cả provider có cùng đặc tính tra cứu, đặc biệt với cache bất đồng bộ.

### 5.3. `condition`, `unless` và `#result`

~~~java
@Cacheable(cacheNames = "catalog",
           key = "#p0",
           condition = "#p0 > 0",
           unless = "#result == null")
public Product find(long id) {
    // ...
}
~~~

- `condition` kiểm tra trước lookup: `id <= 0` thì bỏ qua caching operation.
- `unless` kiểm tra sau khi method trả kết quả: ví dụ không ghi kết quả `null`.
- `#result` khả dụng trong `unless`, một số expression của `@CachePut` và `@CacheEvict` sau invocation; không lấy `#result` làm biến có sẵn trong `condition` trước khi method chạy.
- Với return type `Optional<T>` được Spring hỗ trợ, `#result` biểu diễn giá trị bên trong chứ không phải wrapper `Optional`.

## 6. Ví dụ runnable: quan sát hit, put và evict

Ví dụ dùng Java 17+, Spring Framework 7.0.9 và `ConcurrentMapCacheManager` (cache trong bộ nhớ của chính tiến trình). Chỉ cần JDK 17+ và Maven. Tạo hai file sau.

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-interceptor-flow</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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

**`src/main/java/demo/CacheFlowDemo.java`**

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheFlowDemo {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("items");
    }

    @Bean
    ItemService itemService() {
        return new ItemService();
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(CacheFlowDemo.class)) {
            ItemService service = context.getBean(ItemService.class);

            System.out.println(service.find(42));
            System.out.println(service.find(42));
            System.out.println(service.refresh(42));
            System.out.println(service.find(42));
            service.evict(42);
            System.out.println(service.find(42));
        }
    }

    public static class ItemService {
        private int calls;

        @Cacheable(cacheNames = "items", key = "#p0")
        public String find(int id) {
            System.out.println("DB read " + id + " #" + (++calls));
            return "item-" + id + "-v" + calls;
        }

        @CachePut(cacheNames = "items", key = "#p0")
        public String refresh(int id) {
            System.out.println("refresh " + id + " #" + (++calls));
            return "item-" + id + "-v" + calls;
        }

        @CacheEvict(cacheNames = "items", key = "#p0")
        public void evict(int id) {
            System.out.println("evict " + id);
        }
    }
}
~~~

Chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheFlowDemo
~~~

Các dòng do chương trình in ra theo thứ tự (không tính log tùy môi trường):

~~~text
DB read 42 #1
item-42-v1
item-42-v1
refresh 42 #2
item-42-v2
item-42-v2
evict 42
DB read 42 #3
item-42-v3
~~~

**Giải thích từng giai đoạn:**

1. `find(42)` lần đầu miss, interceptor gọi `ItemService.find`, thấy `DB read 42 #1` rồi ghi key `42` vào `items`.
2. `find(42)` lần hai hit nên **không** thấy `DB read` lần nữa.
3. `refresh(42)` luôn chạy, tạo `item-42-v2` và cập nhật cache nhờ `@CachePut`.
4. `find(42)` kế tiếp lấy `item-42-v2` từ cache; không tăng `calls`.
5. `evict(42)` hoàn thành, xóa key; lần `find(42)` tiếp theo miss và chạy thân method tạo phiên bản `v3`.

Ví dụ cố ý dùng bean lấy từ `context.getBean(...)` để lời gọi qua proxy. Nếu thay thành `new ItemService().find(42)` thì object không thuộc Spring context, không có advice caching; nếu gọi `this.find(42)` từ một method khác của chính `ItemService`, đó cũng là trường hợp self-invocation bypass proxy.

## 7. Giới hạn và tình huống khó trong thực tế

### 7.1. Proxy và lời gọi nội bộ

Trong `@EnableCaching` mặc định (`mode = PROXY`), Spring chỉ chặn lời gọi **đi qua proxy của bean**. Các trường hợp phổ biến làm annotation có vẻ “không chạy”:

- Tự tạo instance bằng `new` thay vì lấy Spring bean.
- Một method gọi method cùng instance bằng `this.method()` (self-invocation), dù method đích có `@Cacheable`.
- Annotation đặt lên method private hoặc method không thể được proxy chặn theo cấu hình hiện có.
- Caching chưa được bật, bean không nằm trong context được cấu hình, hoặc class/method và kiểu proxy không tương thích.
- Mong đợi interceptor xử lý trong giai đoạn khởi tạo bean trước khi proxy sẵn sàng, ví dụ gọi từ `@PostConstruct`.

Cách sửa thường là chuyển method cacheable sang một Spring bean riêng, gọi bean đó qua dependency injection. `mode = ASPECTJ` có thể chặn self-invocation bằng weaving nhưng cần cấu hình AspectJ tương ứng; không bật chỉ để giải quyết một lời gọi nhỏ. Nên đặt cache annotation trên method public của class concrete để dễ dự đoán hơn.

### 7.2. Concurrent miss và `sync = true`

Mặc định, hai request đồng thời cùng miss một key có thể **cùng tính lại** dữ liệu. `@Cacheable(sync = true)` yêu cầu cache provider phối hợp để một request tính còn các request khác chờ giá trị; hỗ trợ thực tế tùy provider. Đây không phải khóa toàn cục do `CacheInterceptor` tự duy trì.

`sync = true` có các giới hạn: chỉ một cache; không dùng `unless`; không kết hợp thêm các cache operation khác trên cùng method theo nhánh synchronized này. Kiểm tra provider trước khi dựa vào nó để chống cache stampede.

### 7.3. Lỗi cache, ngoại lệ business và giá trị null

- Business method ném exception: lời gọi `@Cacheable` thông thường không tạo một kết quả thành công để ghi cache. Đừng mặc định Spring sẽ cache exception.
- Cache backend lỗi: `SimpleCacheErrorHandler` mặc định truyền lỗi lên caller; custom `CacheErrorHandler` có thể chọn bỏ qua lỗi truy cập cache để tiếp tục tính giá trị, nhưng phải cân nhắc rủi ro nhất quán và khả năng quan sát.
- Provider có thể hỗ trợ cache `null`; một cache hit chứa giá trị null cần được phân biệt với miss. Kiểm tra chính sách null của từng `Cache`/provider.
- `@CacheEvict(beforeInvocation = true)` xóa trước, kể cả khi business method sau đó thất bại; dùng khi thực sự chấp nhận điều đó.

### 7.4. Đồng bộ cache với thay đổi dữ liệu

Cache là bản sao suy ra từ nguồn dữ liệu. `@CachePut` và `@CacheEvict` cần đúng key, đúng cache name và đúng thời điểm khi dữ liệu đổi. Với transaction cơ sở dữ liệu, chú ý thứ tự advice `@Transactional`/cache: xóa hoặc ghi cache trước khi commit có thể khiến request khác thấy dữ liệu cũ. Xem xét cơ chế transaction-aware cache, invalidation sau commit, hoặc chiến lược nhất quán tương ứng với hệ thống.

Spring Cache không tự cung cấp TTL, write-through database, invalidation liên node hay bảo đảm giao dịch giữa database và cache. Những điều này phải được thiết kế cùng provider và đường cập nhật dữ liệu.

### 7.5. Async và reactive

Từ Spring Framework 6.1, caching annotations hỗ trợ thích ứng với `CompletableFuture` và một số return type reactive: việc lấy/đưa vào cache gắn với giá trị được hoàn thành, không nên hiểu đơn giản rằng luôn lưu nguyên đối tượng `Mono`/`Flux`. Tính năng cụ thể còn phụ thuộc cache provider và cấu hình; thử riêng trường hợp async thay vì áp dụng sơ đồ đồng bộ ở mục 4 một cách máy móc.

## 8. Cách kiểm tra và xử lý sự cố

Khi một method đã chú thích `@Cacheable` nhưng vẫn truy cập database nhiều lần, kiểm tra theo thứ tự:

1. **Có proxy không?** Lấy bean từ Spring, xem lời gọi có đi từ ngoài bean qua proxy không. Phân biệt self-invocation và direct constructor.
2. **Có đúng operation metadata không?** Kiểm tra `@EnableCaching`, tên class/method, annotation, `@CacheConfig`, phương thức public và việc pointcut chọn method.
3. **Key có lặp đúng không?** Xác nhận `#p0`, các tham số thực sự ảnh hưởng kết quả, kiểu dữ liệu và `equals()/hashCode()`. Khác tenant/locale/permission thì cần khác key khi kết quả phụ thuộc các yếu tố ấy.
4. **Đã chọn đúng cache chưa?** Soát tên `cacheNames`, `CacheManager`/`CacheResolver`, tên bean và cấu hình provider.
5. **Có điều kiện ngăn cache không?** `condition` false dẫn đến bỏ qua cache; `unless` true ngăn put. Chú ý `#result` và null.
6. **Có writer/eviction không?** `@CachePut`, `@CacheEvict`, TTL/eviction policy của provider hoặc restart ứng dụng có thể giải thích lần miss tiếp theo.
7. **Có nhiều node hoặc concurrent calls không?** `ConcurrentMapCacheManager` mỗi process giữ dữ liệu riêng; test concurrent miss để xác định có cần `sync=true` hoặc cơ chế bên ngoài.
8. **Có lỗi backend hay transaction không?** Kiểm tra cache error handling, serialization, độ trễ, dữ liệu chưa commit và timing của invalidate.

Một bộ kiểm thử hành vi nhỏ nên chứng minh: lần đầu miss (method chạy một lần), lần hai hit (method không chạy), `@CachePut` làm mới value, `@CacheEvict` làm lần đọc tiếp theo miss, `condition/unless` có nhánh đúng, và self-invocation được xử lý theo thiết kế. Tránh kiểm thử chỉ bằng cách nhìn annotation; cần quan sát số lần **target method thực sự được gọi** và nội dung cache.

## 9. Những hiểu nhầm dễ mắc

- **“Có `@Cacheable` thì tất cả lời gọi đều được cache.”** Sai khi self-invocation, object không phải Spring bean, cấu hình AOP thiếu hoặc `condition` false.
- **“`CacheInterceptor` đọc annotation từ reflection ở mọi request.”** Không chính xác: Spring có cơ chế phân giải và cache metadata theo method/target class; còn key và condition vẫn được đánh giá cho lời gọi cụ thể.
- **“`@CachePut` giống `@Cacheable`.”** `@CachePut` không bỏ qua method; `@Cacheable` có thể bỏ qua.
- **“`unless` quyết định có gọi method không.”** Với `@Cacheable`, `unless` quyết định có **ghi kết quả mới** sau method hay không; `condition` ảnh hưởng việc áp dụng cache từ trước.
- **“Cache hit chắc chắn đồng nghĩa dữ liệu mới nhất.”** Không có bảo đảm đó nếu chiến lược TTL/invalidation/transaction chưa đúng.
- **“`sync=true` luôn loại bỏ mọi race condition.”** Chỉ điều phối quá trình tải một entry theo khả năng của provider, không thay thế cơ chế nhất quán dữ liệu.
- **“Nếu cache lỗi, Spring tự fallback sang DB.”** Mặc định lỗi có thể được ném ra; cần chính sách `CacheErrorHandler` riêng nếu muốn degrade.

## 10. Tài liệu đối chiếu

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): annotation, cache key, SpEL, sync, proxy mode và các quy tắc điều kiện.
- [CacheInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/CacheInterceptor.html): triển khai `MethodInterceptor` và kế thừa `CacheAspectSupport`.
- [CacheAspectSupport Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/CacheAspectSupport.html): luồng `execute(...)`, `invokeOperation(...)`, metadata/context.
- [AnnotationCacheOperationSource Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/AnnotationCacheOperationSource.html): chuyển cache annotations thành `CacheOperation`.

**Điểm cần nắm:** `annotation → CacheOperation metadata → AOP proxy/CacheInterceptor → chọn cache và key → hit/miss → (nếu cần) gọi target → put/evict`. Khi debug, luôn xác định đang đứng ở pha **phân giải metadata**, **tính key**, **tra cache** hay **thực thi business method**.