# Tiêu chí chọn phương thức phù hợp để lưu kết quả trong Spring Cache

## Mục tiêu

Bài học giúp bạn xác định phương thức Java nào đáng lưu kết quả bằng Spring Cache, khi nào không nên cache, cách chọn khóa và chính sách làm mới, cách dùng @Cacheable/@CachePut/@CacheEvict, cũng như cách kiểm chứng lợi ích và độ đúng trước khi triển khai.

**Phạm vi:** Spring Framework Cache Abstraction lưu kết quả **ở mức lời gọi phương thức**, dựa trên khóa. Với @Cacheable, một lời gọi qua Spring proxy sẽ kiểm tra cache trước: nếu có giá trị (cache hit), phương thức có thể không được thực thi; nếu chưa có (cache miss), Spring gọi phương thức và có thể lưu kết quả trả về. Framework cung cấp hợp đồng Cache/CacheManager, còn TTL, giới hạn dung lượng, khả năng phân tán và eviction theo dung lượng do cache provider quyết định.

## 1. Khi nào việc lưu kết quả thực sự có ích?

Một ứng viên cache tốt cần thỏa mãn đồng thời hai nhóm điều kiện:

- **Tính đúng:** các lần gọi có cùng khóa phải được phép dùng lại cùng kết quả trong một khoảng thời gian xác định; việc bỏ qua thực thi không làm mất side effect quan trọng.
- **Lợi ích:** chi phí truy xuất cache và duy trì cache nhỏ hơn phần công việc tránh được; có đủ lần gọi lặp lại và hit ratio đủ cao.

Ví dụ, phương thức findProductById(42) tra cứu sản phẩm từ database có thể được gọi nhiều lần, có đầu ra tương đối ổn định và tốn truy vấn: thường là ứng viên tốt. Ngược lại, chargeCard() phải ghi nhận giao dịch mỗi khi được gọi: @Cacheable có thể khiến phương thức không chạy trên cache hit, nên **không phù hợp để bảo đảm nghiệp vụ thanh toán**.

Đừng quyết định chỉ vì một phương thức “chạy chậm”. Hỏi kỹ: kết quả có tái sử dụng được không, các lời gọi có trùng khóa không, người dùng có chấp nhận dữ liệu cũ không, và khi nguồn đổi thì ai làm mới cache?

## 2. Bảy tiêu chí chính để chọn phương thức

### 2.1. Kết quả ổn định theo khóa và ngữ cảnh

Kết quả phải có tính xác định tương đối: cùng tham số và cùng các điều kiện nghiệp vụ liên quan sẽ cho cùng giá trị trong cửa sổ cache. Ngoài tham số hiện diện trong chữ ký Java, kết quả đôi khi phụ thuộc tenant, người dùng đăng nhập, locale, cấu hình, quyền truy cập, phiên bản quy tắc, thời gian.

Nếu cache key chỉ chứa productId trong khi kết quả được tùy biến theo tenant hoặc locale, hai lời gọi khác ngữ cảnh có thể nhận nhầm dữ liệu. Giải pháp là chọn khóa đầy đủ, thiết kế namespace phù hợp hoặc không cache khi không thể cô lập an toàn. Ngược lại, đưa timestamp thay đổi mỗi mili giây vào khóa thường khiến cache hầu như không có hit.

### 2.2. Chi phí của lời gọi nguồn

Các ứng viên thường đáng cân nhắc: truy vấn database tốn kém, gọi HTTP/gRPC đến hệ thống khác, tập hợp dữ liệu từ nhiều nguồn, hoặc phép tính CPU nặng. Phương thức chỉ đọc một biến, cộng hai số hay thao tác đã rất rẻ có thể tốn nhiều overhead hơn khi đi qua cache.

Đo latency khi không cache (p50/p95/p99) và tỷ lệ request sử dụng cùng khóa. Ví dụ **giả định**: nguồn tốn 90 ms, cache hit tốn 3 ms, hit ratio 70%; latency trung bình xấp xỉ 0,7 × 3 + 0,3 × 90 = **29,1 ms**, chưa tính chi phí cache miss, ghi cache, mạng và invalidation. Nếu tỷ lệ hit chỉ 1%, kết quả sẽ khác hẳn.

### 2.3. Mức độ lặp lại và số lượng khóa

Cache có giá trị khi cùng key xuất hiện đủ thường xuyên. Tra cứu danh mục công khai hoặc cấu hình theo mã vùng thường có độ lặp cao. Tìm kiếm với query/page/sort/filter tự do, report theo timestamp hoặc dữ liệu cá nhân hóa sâu có thể tạo hàng triệu key ít khi lặp, tiêu tốn tài nguyên mà không tăng hit ratio.

Đếm distinct key, phân bố truy cập, tỷ lệ key chỉ xuất hiện một lần và tốc độ tăng số entry trước khi chọn cache.

### 2.4. Mức độ chấp nhận dữ liệu cũ

Xác định **độ trễ cập nhật tối đa** phù hợp nghiệp vụ. Danh mục sản phẩm có thể chấp nhận cũ vài phút; tồn kho có thể cần đồng bộ nhanh; số dư để xác nhận giao dịch hoặc kiểm tra phân quyền hiện thời có thể bắt buộc đọc nguồn.

TTL không đồng nghĩa dữ liệu lập tức chính xác sau khi cập nhật. Một entry vẫn có thể stale cho tới khi hết hạn hoặc bị chủ động xóa. Spring không có thuộc tính TTL chuẩn trên @Cacheable; TTL được cấu hình ở provider như Caffeine/Redis hoặc provider tương ứng.

### 2.5. Khả năng làm mới và xóa cache

Mọi phương thức đọc được cache phải có câu trả lời cho câu hỏi: “Khi nguồn thay đổi, cache được cập nhật bằng cách nào?”

- **TTL:** entry hết hạn sau thời lượng đã định, dễ vận hành nhưng có cửa sổ stale.
- **@CacheEvict:** xóa một key hoặc toàn vùng khi phương thức cập nhật nguồn đã thực thi thành công.
- **@CachePut:** luôn thực thi phương thức và ghi kết quả mới vào cache; phù hợp khi giá trị trả về chính là phiên bản cần giữ.
- **Sự kiện hoặc invalidation phân tán:** cần cân nhắc nếu nhiều instance dùng cache local riêng.

Trong transaction, xóa cache trước khi database commit có thể gây race hoặc stale repopulation; nếu transaction rollback, trạng thái cache cũng có thể không tương thích nguồn. Với dữ liệu nhạy về tính nhất quán, thiết kế thời điểm invalidation **sau commit** hoặc cơ chế transaction-aware thích hợp.

### 2.6. Kích thước và khả năng lưu trữ

Một giá trị cache lý tưởng nhỏ, đọc lặp nhiều, ít mutable. Tránh cache tùy tiện các blob lớn, stream, object chứa trạng thái request, JPA entity phụ thuộc persistence context/lazy proxy, hoặc dữ liệu chứa thông tin nhạy cảm không có chính sách cô lập. DTO bất biến thường dễ quản lý hơn entity sống.

Xem ngân sách RAM, max entries, TTL, cơ chế eviction, serializer/schema version, thời gian truyền mạng và cách làm sạch khi phát hành phiên bản mới. ConcurrentMapCacheManager tiện làm ví dụ và ứng dụng nhỏ nhưng không tự cung cấp TTL/max-size thích hợp cho production.

### 2.7. Tính an toàn khi bỏ qua thân phương thức

@Cacheable không phù hợp cho phương thức mà **mỗi lần gọi đều cần thực hiện side effect**: tạo đơn, gửi email, ghi audit bắt buộc, thu tiền, tăng bộ đếm nghiệp vụ, kiểm tra quyền hiện hành theo chính sách không chấp nhận stale. Cache kết quả một phương thức có side effect có thể khiến side effect không diễn ra.

Phương thức đọc cũng cần kiểm tra liệu có phụ thuộc thời gian/ngẫu nhiên hay không. Tính kết quả từ đầu vào ổn định có thể cache; sinh mã OTP ngẫu nhiên hoặc đọc trạng thái sống có thể không.

## 3. Ma trận ví dụ để chọn ứng viên

| Phương thức | Khuyến nghị | Giải thích/điều kiện |
| --- | --- | --- |
| findProductById(id) | Thường cache | Truy vấn lặp; cần invalidation khi sửa/xóa sản phẩm |
| listCategories(locale) | Thường cache | Ít thay đổi; khóa gồm locale; TTL theo độ mới chấp nhận |
| calculateQuote(ruleVersion, country, input) | Có thể cache | Kết quả xác định nhưng phải gồm phiên bản quy tắc |
| search(query, page, sort, filter) | Cân nhắc | Nhiều tổ hợp key; đo lặp lại và giới hạn entry |
| getInventory(productId) | Cân nhắc kỹ | Thường xuyên thay đổi; TTL ngắn/invalidation hoặc đọc nguồn |
| getUserDashboard(userId, tenantId) | Có điều kiện | Cần key cách ly user/tenant và làm mới khi quyền/dữ liệu đổi |
| chargeCard(), createOrder() | Không dùng @Cacheable | Thao tác ghi có side effect; cần xử lý idempotency ở tầng nghiệp vụ |
| now(), generateRandomToken() | Thường không | Giá trị thay đổi theo thời gian/ngẫu nhiên |
| add(int a, int b) | Thường không đáng | Chi phí tính toán quá nhỏ |

**Kết luận lựa chọn:** phương thức **đọc + tốn chi phí + lặp cùng key + chịu stale có kiểm soát + an toàn khi không chạy lại** là điểm xuất phát tốt nhất.

## 4. Chọn khóa cache chính xác

Spring mặc định sử dụng SimpleKeyGenerator:

- Không có tham số → SimpleKey.EMPTY.
- Một tham số → chính đối tượng tham số đó làm key.
- Nhiều tham số → SimpleKey gộp toàn bộ tham số.

Cách này phụ thuộc equals/hashCode của các đối tượng đầu vào. Nếu chữ ký có cả tham số không liên quan kết quả, hoặc kết quả phụ thuộc ngữ cảnh không nằm trong tham số, hãy dùng thuộc tính key (SpEL) hoặc KeyGenerator riêng. Ví dụ:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto findById(long productId) {
    return repository.findDtoById(productId);
}
~~~

**Đây là đoạn mã minh họa trong Spring service**, với repository và ProductDto đã tồn tại; không phải chương trình độc lập. Biểu thức #p0 lấy tham số thứ nhất nên key là productId.

Nếu phương thức cần tenantId:

~~~java
@Cacheable(cacheNames = "productsByTenant")
public ProductDto findByTenantAndId(String tenantId, long productId) {
    return repository.findForTenant(tenantId, productId);
}
~~~

Khi có hai tham số, key mặc định chứa cả tenantId lẫn productId. Điều này **chưa thay thế kiểm tra quyền**: cache hit vẫn phải tuân thủ mô hình bảo mật, và cả thao tác xóa/cập nhật phải sử dụng cùng logic key. Với cache phân tán, kiểm tra serializer, tên vùng cache và khả năng collision khi biến kiểu dữ liệu thành chuỗi.

## 5. Chọn annotation phù hợp với hành vi

| Nhu cầu | Annotation | Điều cần nhớ |
| --- | --- | --- |
| Trả lại kết quả cũ khi có cache hit | @Cacheable | Có thể bỏ qua toàn bộ thân phương thức |
| Thực thi phương thức rồi ghi kết quả mới | @CachePut | Thân phương thức vẫn chạy |
| Xóa entry/vùng sau thay đổi nguồn | @CacheEvict | Mặc định xóa sau khi phương thức hoàn tất thành công |
| Gom nhiều thao tác cache | @Caching | Khai báo nhiều thao tác cùng phương thức |
| Chia sẻ cấu hình ở cấp class | @CacheConfig | Chia sẻ cacheNames, keyGenerator... |

Với @Cacheable:

- **cacheNames:** chỉ định vùng cache logic.
- **key:** SpEL xác định key; #p0, #p1 lần lượt là tham số đầu và thứ hai.
- **condition:** quyết định có áp dụng caching dựa trên dữ liệu có trước khi gọi phương thức.
- **unless:** sau khi tính xong kết quả, có thể từ chối lưu; ví dụ unless = "#result == null".
- **sync = true:** có thể điều phối các request cùng miss một key để giảm tính toán trùng, nếu cache provider hỗ trợ; không mặc nhiên bảo đảm khóa phân tán trên mọi instance.

Không tùy tiện ghép @Cacheable với @CachePut trên cùng phương thức vì một annotation có thể ngăn thực thi còn annotation kia yêu cầu thực thi. Khi cần cập nhật sau ghi, thường chọn @CacheEvict hoặc @CachePut ở phương thức **ghi**, giữ @Cacheable trên phương thức **đọc**.

## 6. Ví dụ chạy được với Spring Framework và Java 17

Ví dụ tạo một ứng dụng console nhỏ dùng Spring Framework 6.2.19. Phương thức findProductName(id) mô phỏng truy vấn nguồn: mỗi lần thân phương thức chạy, biến đếm tăng. Gọi hai lần ID 42 sẽ minh họa cache hit.

**Cấu trúc dự án:**

~~~text
cache-selection-demo/
├── pom.xml
└── src/main/java/demo/CacheSelectionDemo.java
~~~

**pom.xml:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>cache-selection-demo</artifactId>
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
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**src/main/java/demo/CacheSelectionDemo.java:**

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheSelectionDemo {

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    public static class ProductService {
        private final AtomicInteger loadCounter = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0",
                   unless = "#result == null")
        public String findProductName(long productId) {
            int n = loadCounter.incrementAndGet();
            return "Product-" + productId + " [load " + n + "]";
        }

        public int sourceLoadCount() {
            return loadCounter.get();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            ProductService service = context.getBean(ProductService.class);

            System.out.println(service.findProductName(42));
            System.out.println(service.findProductName(42));
            System.out.println("Source loads: " + service.sourceLoadCount());
            System.out.println(service.findProductName(7));
            System.out.println("Source loads: " + service.sourceLoadCount());
        }
    }
}
~~~

Chạy từ thư mục dự án với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheSelectionDemo
~~~

**Stdout của chương trình:**

~~~text
Product-42 [load 1]
Product-42 [load 1]
Source loads: 1
Product-7 [load 2]
Source loads: 2
~~~

Với ID 42, lần đầu miss nên thân phương thức chạy và lưu “Product-42 [load 1]”; lần hai hit nên không tăng bộ đếm. ID 7 có key khác nên tạo lượt load thứ hai. @EnableCaching kích hoạt xử lý annotation; ConcurrentMapCacheManager lưu trong RAM của tiến trình để minh họa, không đại diện cho cấu hình production có TTL/giới hạn dung lượng.

**Lưu ý về proxy:** annotation caching trong chế độ proxy mặc định chỉ được áp dụng cho lời gọi đi qua Spring proxy. Nếu một phương thức cùng class gọi this.findProductName(42), Spring không chặn self-invocation đó theo cơ chế proxy mặc định. Tránh new đối tượng thủ công rồi kỳ vọng @Cacheable hoạt động; hãy gọi bean do Spring quản lý từ bean khác hoặc thiết kế ranh giới service phù hợp. Phương thức private/final cũng không phải điểm chặn proxy phù hợp.

## 7. Khi nguồn thay đổi: phải thống nhất key đọc và key xóa

Đây là **đoạn mã minh họa** cho một Spring-managed service (giả định repository và ProductDto tồn tại):

~~~java
@Cacheable(cacheNames = "productById", key = "#p0")
public ProductDto getProduct(long id) {
    return repository.findDtoById(id);
}

@CacheEvict(cacheNames = "productById", key = "#p0")
public void renameProduct(long id, String newName) {
    repository.rename(id, newName);
}
~~~

Hai thao tác dùng cùng cacheNames và cùng key ID. Sau khi phương thức renameProduct hoàn tất thành công, Spring mặc định xóa entry; lần đọc kế tiếp sẽ nạp lại dữ liệu. Nếu cập nhật nằm trong transaction, cần kiểm tra thời điểm commit trước khi quyết định chiến lược invalidation. Nếu phương thức ghi trả về chính DTO mới của key đó, @CachePut có thể phù hợp hơn, với điều kiện dữ liệu trả về đủ và chính xác.

Trong hệ thống nhiều instance, cache local trên máy A không tự biết máy B vừa xóa/cập nhật entry. Khi yêu cầu nhất quán giữa các node, cần dùng cache chia sẻ hoặc kênh invalidation đa node; chỉ gắn @CacheEvict trên từng tiến trình có thể chưa đủ.

## 8. Quy trình ra quyết định trong dự án

1. **Tìm ứng viên:** dùng tracing/profiling xác định phương thức đọc có latency/QPS/chi phí nguồn đáng kể.
2. **Đo lặp lại:** thống kê key, hit ratio tiềm năng, số lượng key khác nhau và các tham số tạo ra kết quả.
3. **Xác định hợp đồng đúng:** độ cũ tối đa, quyền truy cập, ngữ cảnh user/tenant, kích thước, khả năng bỏ qua thân phương thức.
4. **Thiết kế key và vùng cache:** đủ tham số; có tên vùng rõ ràng, quy tắc serialization/versioning và khóa nhất quán giữa đọc và cập nhật.
5. **Thiết kế làm mới:** TTL cho dữ liệu có thể stale, eviction hoặc put theo luồng ghi, cách xử lý transaction và multi-node.
6. **Chọn provider:** in-memory cục bộ hoặc shared/distributed tùy topology, max size, eviction, lỗi hạ tầng, chi phí mạng.
7. **Kiểm thử:** gọi hai lần cùng key phải hit; khác key phải miss; cập nhật xong phải đúng theo độ cũ cho phép; tenant/user phải cách ly; kiểm tra đồng thời và provider lỗi.
8. **Đo sau triển khai:** hit/miss, p95/p99, QPS nguồn, bộ nhớ/entry, eviction, stale data và lỗi provider. Nếu không có lợi ích ròng hoặc khó bảo đảm đúng dữ liệu, bỏ cache khỏi ứng viên đó.

### Checklist trước khi bật @Cacheable

- [ ] Phương thức chủ yếu **đọc**, không có side effect bắt buộc ở mỗi lời gọi.
- [ ] Kết quả cùng key có thể tái sử dụng an toàn trong thời gian xác định.
- [ ] Có số liệu về chi phí nguồn và mức lặp cùng key.
- [ ] Key bao gồm đủ ID, tenant, locale, quyền, filter, version khi ảnh hưởng kết quả.
- [ ] Có mức staleness cho phép, TTL và/hoặc cơ chế invalidation.
- [ ] Giá trị phù hợp lưu, kích thước và cardinality được kiểm soát.
- [ ] Lời gọi đi qua Spring proxy.
- [ ] Đã thử cache hit/miss, ghi dữ liệu, nhiều instance và phân quyền.
- [ ] Có metric để xác nhận cải thiện thực tế.

## 9. Lỗi phổ biến và cách tránh

**Cache mọi truy vấn đọc.** Đọc nhiều nhưng mỗi lần có key khác sẽ không tạo hit; hãy đo độ lặp trước.

**Quên ngữ cảnh trong key.** Kết quả theo tenant/user nhưng chỉ cache theo productId có thể rò rỉ dữ liệu; thiết kế key và kiểm tra quyền rõ ràng.

**Không xóa cache sau khi sửa nguồn.** Dữ liệu stale tồn tại đến TTL hoặc lâu hơn nếu provider không có TTL; liên kết luồng ghi với invalidation thích hợp.

**Giả định @Cacheable kiểm soát TTL.** Framework chỉ trừu tượng hóa thao tác; chọn và cấu hình provider cho dung lượng, TTL, eviction, topology.

**Gọi phương thức nội bộ trong cùng bean.** Self-invocation không đi qua proxy nên annotation caching có thể không có hiệu lực; tách service hoặc dùng phương án intercept phù hợp.

**Cache kết quả lỗi/null mà không có chủ đích.** Cân nhắc unless/condition và negative caching có TTL riêng khi phù hợp.

**Không xử lý cache stampede.** Nhiều request cùng miss một key có thể cùng chạy nguồn; sync=true giảm tính toán trùng khi provider hỗ trợ, nhưng không mặc nhiên phân tán giữa các node.

**Nhìn mỗi latency cache hit.** Cần tính cả miss, số entry, chi phí serialization/network, stale và rủi ro lỗi cache.

## 10. Câu hỏi tự kiểm tra

1. Phương thức tính toán nhanh, mỗi request có đầu vào hoàn toàn khác nhau có đáng cache không? **Thường không**: ít hit và tăng chi phí lưu.
2. Vì sao phương thức lấy cấu hình theo tenant không nên cache chỉ bằng ID? **Vì** các tenant có thể nhận kết quả khác nhau; key thiếu ngữ cảnh.
3. @CachePut có bỏ qua thân phương thức trên hit như @Cacheable không? **Không**: @CachePut luôn thực thi phương thức.
4. Có thể đặt TTL bằng thuộc tính chuẩn của @Cacheable không? **Không**: cấu hình TTL tại cache provider.
5. Khi cùng key bị miss đồng thời, @Cacheable mặc định đảm bảo chỉ tính một lần chứ? **Không**; cân nhắc sync=true và khả năng của provider.
6. Gọi this.getProduct(id) từ trong chính bean có chắc đi qua cache proxy không? **Không** trong chế độ proxy mặc định.

## Tài liệu tham khảo

- Spring Framework — Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Configuring the Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — TTL/TTI/Eviction policy: https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html
