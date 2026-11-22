# JCache: Khác biệt về ngoại lệ được lưu và thời điểm xóa

## Mục tiêu học tập

Khi làm việc với **JCache (JSR-107)** trong Spring Framework, hai điểm dễ gây nhầm nhất so với annotation cache của Spring là:

1. **@CacheResult có thể lưu một số ngoại lệ đã ném ra** vào một cache riêng, để những lời gọi sau với cùng khóa nhận lại ngoại lệ đó mà không chạy method thật.
2. **@CacheRemove và @CacheRemoveAll điều khiển thời điểm xóa** bằng afterInvocation, đồng thời có **evictFor/noEvictFor** để quyết định liệu việc xóa có diễn ra khi method ném ngoại lệ hay không. Spring **@CacheEvict** có beforeInvocation nhưng không có hai bộ lọc ngoại lệ tương đương trên annotation.

JCache **@CachePut** còn có afterInvocation và cacheFor/noCacheFor: đây là nhánh **ghi vào cache**, có quy tắc trước/sau và khi lỗi tương tự nhưng không phải thao tác xóa. Vì ba nhóm annotation thường xuất hiện trong cùng một nghiệp vụ, bài này sẽ liên hệ chúng ở những chỗ cần thiết.

Kết thúc bài, bạn sẽ:
- Phân biệt **cache chứa kết quả**, **cache chứa ngoại lệ** và **xóa entry/cache**.
- Giải thích đầy đủ vai trò của **exceptionCacheName**, **cachedExceptions**, **nonCachedExceptions**, **skipGet** trong @CacheResult.
- Xác định chính xác thời điểm @CacheRemove/@CacheRemoveAll xóa đối với **thành công, thất bại, afterInvocation=true/false, evictFor và noEvictFor**.
- Phân biệt **JCache @CachePut lấy @CacheValue từ tham số** với **Spring @CachePut lấy result trả về**.
- Chạy ví dụ Java 17 + Spring Framework 6.2.19 + javax.cache API 1.1.1, tự quan sát số lượt gọi method, exception được replay và cache bị xóa.
- Tránh hiểu nhầm rằng xóa sau method đồng nghĩa với **xóa sau database commit**, hoặc rằng cached exception tự hết hạn khi dữ liệu nguồn được sửa.

**Phạm vi:** dùng annotation **javax.cache.annotation** của JCache 1.1.x thông qua Spring Framework 6.2.x. Spring hỗ trợ các annotation này ngay trên **Spring CacheManager**; ví dụ không cần JCache native provider. Nếu dùng một JCache provider thực sự (Ehcache, Hazelcast, Infinispan…), phải xét thêm hợp đồng TTL, serialization, transaction và visibility của provider.

## 1. Phân biệt ngoại lệ nghiệp vụ với ngoại lệ của bộ nhớ đệm

Ba tình huống cần phân biệt:

| Tình huống | Ví dụ | Có nhất thiết nên lưu? |
| --- | --- | --- |
| **Method nghiệp vụ trả result** | Tìm sản phẩm thành công | Thường có thể cache result |
| **Method nghiệp vụ ném ngoại lệ** | Mã đầu vào không hợp lệ; service tạm lỗi | Có thể cache **một số lỗi ổn định**, không nên cache lỗi tạm thời |
| **Cache infrastructure gặp lỗi** | Timeout Redis, lỗi serialize, không tìm thấy cacheName | Không coi đó là ngoại lệ nghiệp vụ được @CacheResult quản lý theo cách thông thường |

**Exception caching** trong JCache là việc chủ động lưu một đối tượng ngoại lệ phù hợp trong **exception cache** của một operation @CacheResult. Nó không có nghĩa “Spring lưu mọi Throwable do bất kỳ bean nào ném”, không phải cách chữa lỗi cache provider và cũng không đồng nghĩa **negative caching giá trị null**.

Ví dụ một ID không đúng định dạng luôn cho cùng lỗi nghiệp vụ có thể phù hợp để tránh lặp một phép tính validation tốn kém. Ngược lại, timeout của dịch vụ upstream thường chỉ xảy ra tạm thời: lưu ngoại lệ này quá lâu có thể biến outage ngắn thành lỗi kéo dài dù upstream đã hồi phục.

Với cùng khóa, hãy tách rõ:
- **Value cache**: kết quả thành công của method.
- **Exception cache**: một exception đã được cấu hình cho phép cache.
- **Nguồn dữ liệu thật**: database hoặc hệ thống nghiệp vụ, không tự thay đổi theo trạng thái hai cache kia.

## 2. JCache trong Spring: đúng namespace và hạ tầng

Các annotation theo chuẩn JCache 1.1.1 dùng package:

~~~java
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheRemove;
import javax.cache.annotation.CacheRemoveAll;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CacheValue;
import javax.cache.annotation.CacheDefaults;
~~~

Chúng **khác** các annotation:

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.CacheConfig;
~~~

Cụ thể:
- **JCache @CacheResult** gần với **Spring @Cacheable**, nhưng có cơ chế **exception cache** và **skipGet**.
- **JCache @CacheRemove** gần với **Spring @CacheEvict**, nhưng JCache có **evictFor/noEvictFor** đối với lỗi method.
- **JCache @CacheRemoveAll** gần với **Spring @CacheEvict(allEntries=true)**.
- **Cả hai đều có tên @CachePut**, nhưng API và giá trị được cache **khác nhau**: JCache dùng tham số đánh dấu @CacheValue; Spring dùng result trả về của method.
- **JCache @CacheDefaults** tương đương về ý tưởng chia sẻ cấu hình lớp với **Spring @CacheConfig**, không phải hai annotation có cùng tập thuộc tính.

**Không dùng nhầm import**: nếu code muốn khai báo cacheFor, noCacheFor hay afterInvocation trên JCache @CachePut nhưng IDE tự import org.springframework.cache.annotation.CachePut, sẽ không có các thuộc tính đó.

### Kích hoạt trong Spring Framework

Theo tài liệu Spring, **@EnableCaching** đồng thời kích hoạt JCache annotation support khi có **JSR-107 API** và module **spring-context-support** trên classpath.

~~~java
@Configuration
@EnableCaching
public class CachingConfig {
    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("records", "recordFailures");
    }
}
~~~

Đoạn trên minh họa, cần imports; ví dụ đầy đủ ở phần sau. CacheManager ở đây là **org.springframework.cache.CacheManager**, còn ConcurrentMapCacheManager thuộc Spring. **Không bắt buộc cấu hình javax.cache.CacheManager** chỉ để chạy JCache annotations bằng interceptor của Spring.

Spring proxy mode vẫn áp dụng: method phải được gọi qua **Spring-managed proxy bean**. Một method gọi this.otherMethod(...) trong cùng target thường bypass caching advice, kể cả khi otherMethod có @CacheResult hoặc @CacheRemove.

## 3. @CacheResult: result cache và exception cache khác nhau

Cấu hình cơ bản:

~~~java
@CacheResult(
    cacheName = "records",
    exceptionCacheName = "recordFailures",
    cachedExceptions = InvalidIdException.class
)
public String find(@CacheKey String id) {
    return repository.find(id);
}
~~~

Đây là snippet minh họa: repository và InvalidIdException do ứng dụng định nghĩa.

- **cacheName="records"**: nơi lưu kết quả thành công.
- **exceptionCacheName="recordFailures"**: nơi lưu các ngoại lệ được chọn.
- **cachedExceptions=InvalidIdException.class**: bộ lọc loại ngoại lệ có thể được ghi vào exception cache.
- **@CacheKey String id**: chỉ định id là thành phần tham gia key do JCache CacheKeyGenerator tạo.

### Luồng khi không có cache hit

~~~text
caller -> Spring/JCache interceptor -> tính key theo JCache
                                    |
                                    +-- value cache có result?
                                    |      Có -> trả result, bỏ qua method
                                    |      Không -> xét exception cache (nếu bật)
                                    |
                                    +-- exception cache có exception tương ứng?
                                    |      Có -> ném lại exception đã cache
                                    |      Không -> gọi target method
                                    |
                                    +-- method thành công -> cache result
                                    |
                                    +-- method ném exception
                                           |
                                           +-- đủ điều kiện cache -> lưu exception
                                           +-- không đủ điều kiện -> không lưu
                                           +-- vẫn truyền ngoại lệ đến caller
~~~

Đây là flow theo ý nghĩa nghiệp vụ, không nhằm ấn định thứ tự đọc hai cache khi hai entry trái ngược cùng tồn tại do thao tác ngoài luồng. Trong thiết kế bình thường, một khóa không nên đồng thời có result lỗi thời và cached exception mâu thuẫn nhau; khi sửa nguồn dữ liệu cần invalidation có kiểm soát.

### Không cấu hình exceptionCacheName: mặc định KHÔNG cache ngoại lệ

~~~java
@CacheResult(cacheName = "records")
public String find(String id) {
    if (id.isBlank()) throw new IllegalArgumentException("empty");
    return id;
}
~~~

Nếu lời gọi ném ngoại lệ, **ngoại lệ không được lưu mặc định**. Điều này đúng ngay cả khi một nơi khác dùng @Cacheable trên một cache cùng tên: mỗi annotation có semantics riêng.

**Cảnh báo:** chỉ đặt cachedExceptions mà không có **exceptionCacheName** không tự bật việc cache ngoại lệ. exceptionCacheName trống thì không có nơi lưu exception được cấu hình cho operation.

### Phải tồn tại và resolve được exception cache

Nếu dùng ConcurrentMapCacheManager ở **static mode** với tên chỉ có "records" mà quên tạo "recordFailures", Spring có thể không resolve được exception cache, dẫn đến lỗi cấu hình. Hãy đăng ký **cả hai cache names**; một exception cache không phải “khu vực ẩn” luôn tồn tại mặc định.

## 4. Bộ lọc ngoại lệ của @CacheResult

Ba thuộc tính đáng chú ý:

| Thuộc tính | Kiểu | Mặc định | Ý nghĩa |
| --- | --- | --- | --- |
| **exceptionCacheName** | String | Chuỗi rỗng | Khi không khai báo, exception caching bị tắt |
| **cachedExceptions** | Mảng Class<? extends Throwable> | Mảng rỗng | Các loại Throwable cho phép cache |
| **nonCachedExceptions** | Mảng Class<? extends Throwable> | Mảng rỗng | Các loại Throwable không cache |

**Khi exceptionCacheName khác rỗng**, quy tắc JCache 1.1.1:

| cachedExceptions | nonCachedExceptions | Ngoại lệ nào được cache? |
| --- | --- | --- |
| Rỗng | Rỗng | **Tất cả** exception được ném từ target method đủ điều kiện |
| Có danh sách | Rỗng | Chỉ exception thuộc các loại trong **cachedExceptions** |
| Rỗng | Có danh sách | Tất cả, **trừ** exception thuộc **nonCachedExceptions** |
| Cả hai có danh sách | Cả hai có danh sách | Phải khớp **cachedExceptions** **và không khớp nonCachedExceptions** |

Việc khớp loại xét theo kiểu ngoại lệ và quan hệ kế thừa, tương đương tư duy **instanceof** chứ không chỉ kiểm tra tên class bằng equals. Khi một exception khớp cả danh sách cho phép và danh sách cấm, **nonCachedExceptions loại trừ nó**.

Ví dụ:

~~~java
@CacheResult(
    cacheName = "profiles",
    exceptionCacheName = "profileFailures",
    cachedExceptions = RuntimeException.class,
    nonCachedExceptions = TemporaryFailureException.class
)
public Profile find(String id) {
    return repository.load(id);
}
~~~

Đây là snippet minh họa; Profile, TemporaryFailureException và repository do dự án cung cấp. Ở đây:
- InvalidProfileException extends RuntimeException → có thể được cache.
- TemporaryFailureException extends RuntimeException nhưng nằm trong nonCachedExceptions → **không** cache.
- IOException checked exception không phải RuntimeException → **không** cache theo filter này.
- Nếu không đặt exceptionCacheName, **cả hai bộ lọc không kích hoạt ngoại lệ cache**.

**Rủi ro thường gặp:** chỉ thêm exceptionCacheName mà bỏ trống hai danh sách thì theo quy tắc JCache, có thể **cache mọi ngoại lệ**. Đó là lựa chọn rất nguy hiểm nếu method còn ném timeout, IllegalStateException tạm thời hoặc lỗi phụ thuộc bên ngoài. Nên khai báo whitelist lỗi ổn định một cách chủ đích.

### Ngoại lệ có được “ném lại” hay biến thành result?

Một cached exception không biến thành String, null hay một result bình thường. Với cùng key, interceptor có thể **ném lại ngoại lệ đã cache**; do đó caller vẫn thấy đường lỗi. Điểm khác biệt là **method thật không chạy lại**. Có thể đo điều này bằng bộ đếm method invocations.

Ngoại lệ có thể có stack trace/metadata gắn với lần tạo ban đầu; vì vậy **không nên dựa vào việc ngoại lệ được cache có một stack trace mới** giống mỗi lần thực thi method. Tránh nhét session-specific, secret token hay chi tiết cá nhân vào exception object định cache, đặc biệt nếu provider serialize/store-by-value hoặc lưu ngoài tiến trình.

### skipGet=true

~~~java
@CacheResult(
    cacheName = "records",
    exceptionCacheName = "recordFailures",
    cachedExceptions = InvalidIdException.class,
    skipGet = true
)
public String refresh(String id) {
    return repository.refresh(id);
}
~~~

Đây là snippet minh họa. **skipGet=true** khiến method được thực thi **bất kể result cache hit**, và việc tra **exception cache trước invocation** cũng bị bỏ qua. Khi method thành công, result vẫn được cache theo quy tắc; khi ném exception, exception vẫn có thể được cache nếu khớp filter.

**skipGet không đồng nghĩa với “tắt cache hoàn toàn”**: nó tắt nhánh đọc trước khi thực thi, không tự tắt việc ghi kết quả hoặc ghi ngoại lệ.

## 5. Khóa cache: ngoại lệ và kết quả phải dùng cùng danh tính lời gọi

JCache sinh cache key dựa trên các tham số của method, với **@CacheKey** cho phép chỉ định chính xác thành phần tham gia key. Khi có ít nhất một @CacheKey, những tham số được đánh dấu quyết định generated key theo JCache CacheKeyGenerator. Nếu không đặt @CacheKey nào, các tham số thích hợp (trừ @CacheValue đối với JCache @CachePut) được xét theo mặc định.

~~~java
@CacheResult(cacheName = "records",
             exceptionCacheName = "recordFailures",
             cachedExceptions = InvalidIdException.class)
public String find(@CacheKey String id, boolean validateOnly) {
    return repository.load(id, validateOnly);
}
~~~

Đây là snippet minh họa. Ở ví dụ này key chỉ gồm **id**. Nếu validateOnly làm thay đổi kết quả nghiệp vụ hoặc khả năng ném ngoại lệ, **không nên loại validateOnly khỏi key**, vì một exception hoặc result cho validateOnly=true có thể bị dùng sai khi validateOnly=false.

Quy tắc thiết kế: **Tất cả dữ liệu đầu vào có khả năng làm thay đổi kết quả/lỗi được cache phải tham gia cache key hoặc cache namespace phù hợp** (tenant, locale, phiên bản tài liệu, quyền hạn, feature flags… khi liên quan). Một cached exception sai key có thể nguy hiểm hơn cached result sai key vì nó làm đường phục hồi bị chặn lâu dài.

**JCache key generation không mặc nhiên giống Spring KeyGenerator.** Khi trộn JCache annotations và Spring annotations trên cùng cache store, hãy đặt hoặc kiểm tra một chiến lược key thống nhất; không giả định String key người đọc tự chọn luôn equals với GeneratedCacheKey do interceptor dùng.

## 6. @CacheRemove: thời điểm xóa một entry

JCache **@CacheRemove** tương tự **Spring @CacheEvict** trên một key. Thuộc tính quan trọng là:

~~~java
@CacheRemove(cacheName = "records", afterInvocation = true)
public void delete(@CacheKey String id) {
    repository.delete(id);
}
~~~

Đây là snippet minh họa; repository chưa được định nghĩa.

**afterInvocation=true là mặc định**:
- Method nghiệp vụ chạy trước.
- Nếu method hoàn thành thành công, interceptor yêu cầu xóa entry tương ứng.
- Nếu method ném ngoại lệ, **mặc định không xóa**.
- Có thể thay đổi quyết định trên đường lỗi bằng **evictFor/noEvictFor**.

So sánh:

~~~java
@CacheRemove(cacheName = "records", afterInvocation = false)
public void deleteEarly(@CacheKey String id) {
    repository.delete(id);
}
~~~

**afterInvocation=false**:
- Xóa entry **trước** khi gọi target method.
- Nếu method sau đó ném exception, thao tác xóa **đã được yêu cầu thực hiện**; không đảo ngược mặc định.
- Hai bộ lọc ngoại lệ **evictFor và noEvictFor không tham gia** khi afterInvocation=false, vì khi xóa, exception của target method chưa xảy ra.

Đây là khác biệt lớn giữa **thời điểm yêu cầu xóa** và **kết quả thực tế của nghiệp vụ**. Chọn afterInvocation=false chỉ khi việc xóa phải được thực hiện ngay cả nếu method không thành công, và chấp nhận các hệ quả khi reader khác miss trong lúc nguồn dữ liệu chưa cập nhật.

### Bảng hành vi xóa của @CacheRemove

| afterInvocation | Kết quả target method | Filter mặc định | Có evict? |
| --- | --- | --- | --- |
| **true** | Thành công | Không cần filter | **Có**, sau method |
| **true** | Ném exception | evictFor, noEvictFor đều rỗng | **Không** |
| **true** | Ném exception thuộc evictFor | Không bị noEvictFor loại trừ | **Có**, dù method lỗi |
| **true** | Ném exception không khớp filter | — | **Không** |
| **false** | Thành công | Filter không xét | **Có**, trước method |
| **false** | Ném exception | Filter không xét | **Có**, trước method |

**Không nên gọi afterInvocation=true là “xóa sau commit”**. Nó chỉ là thời điểm tương đối với **method invocation của interceptor**; transaction có thể commit ở thời điểm khác tùy thứ tự advice.

## 7. evictFor và noEvictFor: xóa tùy loại lỗi

Các thuộc tính **evictFor** và **noEvictFor** chỉ có tác dụng với **afterInvocation=true**. Quy tắc của JCache:

| evictFor | noEvictFor | Khi target ném exception, trường hợp nào vẫn xóa? |
| --- | --- | --- |
| Rỗng | Rỗng | **Không ngoại lệ nào**; lỗi thì giữ entry |
| Có danh sách | Rỗng | Chỉ exception khớp **evictFor** |
| Rỗng | Có danh sách | Tất cả exception **trừ** loại khớp **noEvictFor** |
| Có danh sách | Có danh sách | Khớp **evictFor** và **không khớp noEvictFor** |

Ví dụ xóa khi đã phát hiện lỗi “bản ghi không còn hợp lệ”:

~~~java
@CacheRemove(
    cacheName = "records",
    evictFor = StaleRecordException.class
)
public void verifyAndDelete(@CacheKey String id) {
    repository.verifyAndDelete(id);
}
~~~

Đây là snippet minh họa. Nếu StaleRecordException được ném, interceptor vẫn xóa entry, đồng thời **exception tiếp tục được ném ra cho caller**; xóa entry không chuyển một operation thất bại thành thành công.

Ví dụ blacklist lỗi không được xóa:

~~~java
@CacheRemove(
    cacheName = "records",
    noEvictFor = DatabaseUnavailableException.class
)
public void delete(@CacheKey String id) {
    repository.delete(id);
}
~~~

Ở đây nếu method ném DatabaseUnavailableException thì **không xóa**. Theo quy tắc filter khi chỉ có noEvictFor, các exception khác không thuộc blacklist **có thể làm xóa**, dù method thất bại. Đây là điều dễ bị hiểu sai: **noEvictFor không chỉ bổ sung một ngoại lệ vào quy tắc mặc định**, mà xác lập tập loại trừ khỏi cơ chế cho phép xóa khi lỗi. Nếu chỉ muốn xóa khi thành công, giữ mặc định và không đặt filter.

### Nếu cùng khớp hai danh sách?

Giả sử evictFor=RuntimeException.class và noEvictFor=TransientFailureException.class. Một TransientFailureException extends RuntimeException **không gây evict** vì danh sách loại trừ được áp dụng. Cách kiểm tra là theo subclass/instanceof, không chỉ equality của Class.

## 8. @CacheRemoveAll: xóa cả cache, không có key

**@CacheRemoveAll(cacheName="records")** có semantics xóa **tất cả các entry của region**, tương đương ý tưởng **Spring @CacheEvict(allEntries=true)**.

~~~java
@CacheRemoveAll(
    cacheName = "records",
    afterInvocation = true,
    evictFor = CacheRefreshException.class
)
public void rebuildIndex() {
    repository.rebuildIndex();
}
~~~

Đây là minh họa. Nếu method thành công thì clear region; nếu ném CacheRefreshException thì cũng có thể clear vì evictFor. Với một exception khác không khớp filter, không clear.

- **afterInvocation=true**: xóa sau method, mặc định chỉ khi thành công.
- **afterInvocation=false**: yêu cầu xóa toàn region trước method, bất kể method sau đó thành công hay thất bại.
- **evictFor/noEvictFor**: cùng logic filter như @CacheRemove, chỉ xét với afterInvocation=true.
- Không có key riêng cho @CacheRemoveAll; đừng dùng **@CacheKey** để kỳ vọng nó chỉ xóa subset entries.
- Xóa cả region có thể gây **thundering herd** vì rất nhiều request đồng thời phải load lại cache.

**@CacheRemove(cacheName="recordFailures")** hoặc **@CacheRemoveAll(cacheName="recordFailures")** dành cho **exception cache** nếu bạn muốn invalidation các ngoại lệ đã lưu. **Xóa value cache "records" không tự động xóa exception cache "recordFailures"**: chúng là hai vùng được cấu hình riêng.

## 9. JCache @CachePut: “thời điểm ghi” cũng phụ thuộc ngoại lệ

Trong JCache, **@CachePut** lấy **giá trị cần cache từ tham số @CacheValue**, không phải result trả về như Spring @CachePut.

~~~java
@CachePut(cacheName = "records", afterInvocation = true)
public void update(
    @CacheKey String id,
    @CacheValue String nextValue
) {
    repository.save(id, nextValue);
}
~~~

Đây là minh họa.

**afterInvocation=true** (mặc định):
- Method chạy trước, sau đó ghi nextValue nếu thành công.
- Khi method ném exception, mặc định không put.
- **cacheFor/noCacheFor** cho phép một số exception vẫn gây put sau method.

**afterInvocation=false**:
- Cache được put **trước** khi method chạy.
- Nếu method sau đó lỗi, giá trị đã được put; filter **cacheFor/noCacheFor** không được dùng để rollback.
- Đừng dùng chỉ vì muốn cập nhật cache “nhanh hơn”: reader khác có thể thấy nextValue trước khi database transaction hoàn tất hoặc sau khi database update thất bại.

Bộ lọc trên đường lỗi:

| cacheFor | noCacheFor | Khi method ném exception, có put? |
| --- | --- | --- |
| Rỗng | Rỗng | **Không** theo mặc định |
| Có danh sách | Rỗng | Chỉ exception khớp **cacheFor** |
| Rỗng | Có danh sách | Tất cả, trừ exception khớp **noCacheFor** |
| Có danh sách | Có danh sách | Khớp cacheFor và không khớp noCacheFor |

**Không đánh đồng bộ lọc**:
- @CacheResult: **cachedExceptions/nonCachedExceptions** quyết định lưu **exception**.
- JCache @CachePut: **cacheFor/noCacheFor** quyết định lưu **tham số @CacheValue** sau lỗi.
- @CacheRemove/@CacheRemoveAll: **evictFor/noEvictFor** quyết định **xóa** sau lỗi.

Cả ba có thể làm thay đổi cache khi method ném ngoại lệ, nhưng **thứ được thay đổi hoàn toàn khác nhau**.

## 10. Đặt cạnh annotation Spring để tránh nhầm

| Tình huống | **JCache (javax.cache.annotation)** | **Spring Cache annotation** |
| --- | --- | --- |
| Cache kết quả method | @CacheResult | @Cacheable |
| Cache exception nghiệp vụ được chọn | @CacheResult(exceptionCacheName, cachedExceptions, nonCachedExceptions) | @Cacheable **không có** cặp thuộc tính này |
| Luôn chạy method, vẫn ghi result | @CacheResult(skipGet=true) dùng result | Spring @CachePut luôn chạy method và ghi result |
| Ghi tham số value vào cache | JCache @CachePut với **@CacheValue** | Spring @CachePut **ghi result**, không có @CacheValue |
| Ghi trước/sau method | JCache @CachePut(afterInvocation=false/true) | Spring @CachePut thông thường ghi sau method |
| Xóa một key | @CacheRemove | @CacheEvict |
| Xóa tất cả entries | @CacheRemoveAll | @CacheEvict(allEntries=true) |
| Xóa trước method | afterInvocation=false | beforeInvocation=true |
| Xóa sau method | afterInvocation=true (default) | beforeInvocation=false (default) |
| Xóa khi method ném loại exception được chọn | evictFor/noEvictFor | Không có thuộc tính annotation tương đương |
| Mặc định lớp | @CacheDefaults | @CacheConfig |
| Chọn thành phần key | @CacheKey trên parameter | SpEL key / KeyGenerator |
| Kích hoạt trong Spring | @EnableCaching + javax.cache API + spring-context-support | @EnableCaching + hạ tầng Spring Cache |

**Tên dễ nhầm:** JCache **afterInvocation=false** tương ứng về thời điểm với Spring **beforeInvocation=true**. Không phải hai boolean có cùng tên hay cùng chiều.

**Quan trọng:** JCache API và Spring Cache abstraction có thể dùng cùng store nhưng **key generation mặc định không nhất thiết tương thích**. Khi trộn hai annotation trong một hệ thống, kiểm tra cacheName, key và manager/resolver đúng với nhau.

## 11. Các timeline giúp dự đoán hành vi

### 11.1. @CacheResult lưu ngoại lệ

~~~text
Lượt 1: find("BAD")
  -> result cache miss
  -> exception cache miss
  -> target chạy, ném InvalidIdException
  -> filter cho phép -> lưu exception tại recordFailures[generatedKey]
  -> caller nhận InvalidIdException

Lượt 2: find("BAD")
  -> interceptor tìm thấy cached exception
  -> target KHÔNG chạy
  -> caller vẫn nhận InvalidIdException
~~~

Nếu chỉ nhìn log lỗi bên ngoài, bạn có thể tưởng cả hai lần method đều gọi database. Thực tế **cache có thể đang chủ động replay lỗi**. Muốn kiểm chứng, đo method invocation count, quan sát exception cache hoặc thử invalidation đúng key.

### 11.2. @CacheRemove mặc định khi lỗi

~~~text
Value cache đang có records[K] = v1

remove(K) gọi target
  -> target ném IllegalStateException
  -> afterInvocation=true, evictFor/noEvictFor rỗng
  -> không xóa

Sau đó get(K) -> vẫn HIT v1
~~~

Giữ entry có thể đúng nếu update/delete thật sự rollback, nhưng có thể sai nếu source đã bị thay đổi một phần trước khi exception. Annotation không tự biết nghiệp vụ có transaction hay không.

### 11.3. @CacheRemove(evictFor=...) khi lỗi

~~~text
Value cache đang có records[K] = v1

remove(K) gọi target
  -> ném IllegalStateException
  -> exception khớp evictFor
  -> xóa records[K] dù method lỗi
  -> exception vẫn được ném tới caller

Sau đó get(K) -> MISS, chạy target read mới
~~~

### 11.4. @CacheRemove(afterInvocation=false) khi lỗi

~~~text
Value cache có records[K] = v1

interceptor yêu cầu xóa records[K] TRƯỚC
target bắt đầu delete(K)
target ném exception
caller thấy exception, nhưng cache entry đã bị evict
~~~

Lưu ý sự kiện **xóa trước** không chứng minh database đã có trạng thái mới. Một reader khác có thể miss trong khi delete chưa thành công rồi tải dữ liệu cũ.

## 12. Ví dụ Java 17 + Maven chạy được với Spring Framework

Demo dùng **Spring ConcurrentMapCacheManager** cho cả region **records** và **recordFailures**. Dữ liệu nghiệp vụ giả lập bằng bộ đếm và chuỗi; không cần database hay nhà cung cấp JCache native. Mục đích là quan sát rõ:
1. Result được cache khi thành công.
2. InvalidIdException được lưu và replay; TemporaryFailure không được cache.
3. Xóa **riêng exception cache** làm method lỗi được chạy lại.
4. @CacheRemove mặc định **giữ entry khi lỗi**, evictFor khiến **xóa dù lỗi**, afterInvocation=false **xóa trước method**.
5. JCache @CachePut mặc định **không ghi khi lỗi**, cacheFor có thể **ghi dù lỗi**, afterInvocation=false **ghi trước method**.
6. @CacheRemoveAll có cùng quy tắc error filter khi clear toàn region, **không tự xóa exception cache riêng**.

### 12.1. Cấu trúc thư mục

~~~text
spring-jcache-exception-demo/
├── pom.xml
└── src/main/java/demo/JCacheExceptionDemo.java
~~~

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-jcache-exception-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>javax.cache</groupId>
            <artifactId>cache-api</artifactId>
            <version>1.1.1</version>
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

**Không có native JCache provider trong pom.xml** vì Spring JCache interceptor dùng Spring CacheManager để xử lý các annotation. Nếu bạn muốn dùng **javax.cache.CacheManager** và JCache provider thực sự thì cần dependencies/cấu hình của provider ấy, không thay ngẫu nhiên CacheManager trong demo.

### 12.3. src/main/java/demo/JCacheExceptionDemo.java

~~~java
package demo;

import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheRemove;
import javax.cache.annotation.CacheRemoveAll;
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheValue;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.atomic.AtomicInteger;

public class JCacheExceptionDemo {

    public static final class InvalidIdException
            extends IllegalArgumentException {
        public InvalidIdException() {
            super("invalid id");
        }
    }

    public static final class TemporaryFailure
            extends IllegalStateException {
        public TemporaryFailure() {
            super("temporary failure");
        }
    }

    public static class RecordService {
        private final AtomicInteger loads = new AtomicInteger();

        @CacheResult(
            cacheName = "records",
            exceptionCacheName = "recordFailures",
            cachedExceptions = InvalidIdException.class,
            nonCachedExceptions = TemporaryFailure.class
        )
        public String find(@CacheKey String id) {
            int run = loads.incrementAndGet();
            if ("BAD".equals(id)) {
                throw new InvalidIdException();
            }
            if ("TEMP".equals(id)) {
                throw new TemporaryFailure();
            }
            return "load-" + run;
        }

        public int loadCount() {
            return loads.get();
        }

        // Xóa duy nhất cached exception của cùng generated key.
        @CacheRemove(cacheName = "recordFailures")
        public void invalidateFailure(@CacheKey String id) {
        }

        // Lỗi => mặc định KHÔNG xóa cache entry.
        @CacheRemove(cacheName = "records")
        public void failDefaultRemove(@CacheKey String id) {
            throw new IllegalStateException("delete failed");
        }

        // Lỗi khớp evictFor => vẫn xóa sau method.
        @CacheRemove(
            cacheName = "records",
            evictFor = IllegalStateException.class
        )
        public void failButRemove(@CacheKey String id) {
            throw new IllegalStateException("forced remove");
        }

        // Xóa trước method => xóa dù target ném exception.
        @CacheRemove(
            cacheName = "records",
            afterInvocation = false
        )
        public void removeBeforeFailure(@CacheKey String id) {
            throw new IllegalStateException("failed later");
        }

        // JCache @CachePut lấy value từ tham số @CacheValue.
        @CachePut(cacheName = "records")
        public void putDefaultFailure(
                @CacheKey String id, @CacheValue String value) {
            throw new IllegalStateException("put failed");
        }

        @CachePut(
            cacheName = "records",
            cacheFor = IllegalStateException.class
        )
        public void putEvenIfFailure(
                @CacheKey String id, @CacheValue String value) {
            throw new IllegalStateException("put despite failure");
        }

        @CachePut(
            cacheName = "records",
            afterInvocation = false
        )
        public void putBeforeFailure(
                @CacheKey String id, @CacheValue String value) {
            throw new IllegalStateException("failed after put");
        }

        @CacheRemoveAll(cacheName = "records")
        public void clearDefaultFailure() {
            throw new IllegalStateException("clear failed");
        }

        @CacheRemoveAll(
            cacheName = "records",
            evictFor = IllegalStateException.class
        )
        public void clearEvenIfFailure() {
            throw new IllegalStateException("clear despite failure");
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                "records", "recordFailures");
        }

        @Bean
        public RecordService recordService() {
            return new RecordService();
        }
    }

    @FunctionalInterface
    public interface Operation {
        void run();
    }

    private static String errorName(Operation action) {
        try {
            action.run();
            return "NONE";
        } catch (RuntimeException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        try (var ctx =
                 new AnnotationConfigApplicationContext(Config.class)) {
            RecordService service = ctx.getBean(RecordService.class);

            System.out.println("ok1=" + service.find("OK"));
            System.out.println("ok2=" + service.find("OK"));
            System.out.println("loads-after-ok="
                + service.loadCount());

            System.out.println("bad1="
                + errorName(() -> service.find("BAD")));
            System.out.println("bad2="
                + errorName(() -> service.find("BAD")));
            System.out.println("loads-after-bad="
                + service.loadCount());

            System.out.println("temp1="
                + errorName(() -> service.find("TEMP")));
            System.out.println("temp2="
                + errorName(() -> service.find("TEMP")));
            System.out.println("loads-after-temp="
                + service.loadCount());

            service.invalidateFailure("BAD");
            System.out.println("bad-after-evict="
                + errorName(() -> service.find("BAD")));
            System.out.println("loads-after-bad-evict="
                + service.loadCount());

            System.out.println("remove-default="
                + errorName(() -> service.failDefaultRemove("OK")));
            System.out.println("ok-retained="
                + service.find("OK"));

            System.out.println("remove-on-error="
                + errorName(() -> service.failButRemove("OK")));
            System.out.println("ok-reloaded="
                + service.find("OK"));

            System.out.println("remove-before="
                + errorName(() ->
                    service.removeBeforeFailure("OK")));
            System.out.println("ok-after-early-remove="
                + service.find("OK"));

            System.out.println("put-default="
                + errorName(() ->
                    service.putDefaultFailure("P", "P-CACHED")));
            System.out.println("p-after-failed-put="
                + service.find("P"));

            System.out.println("put-on-error="
                + errorName(() ->
                    service.putEvenIfFailure("P", "P-FORCED")));
            System.out.println("p-after-forced-put="
                + service.find("P"));

            System.out.println("put-before="
                + errorName(() ->
                    service.putBeforeFailure("Q", "Q-EARLY")));
            System.out.println("q-after-early-put="
                + service.find("Q"));

            System.out.println("clear-default="
                + errorName(service::clearDefaultFailure));
            System.out.println("p-retained-after-clear-failure="
                + service.find("P"));

            System.out.println("clear-on-error="
                + errorName(service::clearEvenIfFailure));
            System.out.println("p-after-clear="
                + service.find("P"));
            System.out.println("bad-still-cached="
                + errorName(() -> service.find("BAD")));
            System.out.println("loads-total="
                + service.loadCount());
        }
    }
}
~~~

**Vì sao demo có thể được Spring intercept:** RecordService là bean do context tạo, mọi lời gọi ở main thông qua **ctx.getBean(RecordService.class)**, các method là public và không final; @EnableCaching kích hoạt JCache support khi có cache-api + spring-context-support. Không có self-invocation; không tự tạo new RecordService ngoài Spring để gọi.

**Vì sao key của find và các method xóa/ghi nhất quán:** mỗi operation chọn **chính id** bằng @CacheKey; @CacheValue không tham gia generated key. Các tham số dùng để trigger exception đã được loại bỏ khỏi demo bằng cách tách các method thao tác, tránh vô ý tạo key khác.

### 12.4. Biên dịch và chạy

Yêu cầu JDK 17+ và Maven. Trong thư mục có pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JCacheExceptionDemo
~~~

**Stdout kỳ vọng từ System.out.println**, không tính log riêng Maven/thư viện:

~~~text
ok1=load-1
ok2=load-1
loads-after-ok=1
bad1=InvalidIdException
bad2=InvalidIdException
loads-after-bad=2
temp1=TemporaryFailure
temp2=TemporaryFailure
loads-after-temp=4
bad-after-evict=InvalidIdException
loads-after-bad-evict=5
remove-default=IllegalStateException
ok-retained=load-1
remove-on-error=IllegalStateException
ok-reloaded=load-6
remove-before=IllegalStateException
ok-after-early-remove=load-7
put-default=IllegalStateException
p-after-failed-put=load-8
put-on-error=IllegalStateException
p-after-forced-put=P-FORCED
put-before=IllegalStateException
q-after-early-put=Q-EARLY
clear-default=IllegalStateException
p-retained-after-clear-failure=P-FORCED
clear-on-error=IllegalStateException
p-after-clear=load-9
bad-still-cached=InvalidIdException
loads-total=9
~~~

### 12.5. Giải thích từng nhóm output

**Nhóm 1 – result và exception caching:**
- **ok1/ok2** đều load-1: result của "OK" được cache sau lần đầu, không gọi method thật lần hai.
- **bad1/bad2** đều InvalidIdException, nhưng **loads-after-bad=2**: chỉ một lượt mới cho "BAD"; lỗi lần hai được lấy từ **recordFailures**, không gọi method thật.
- **temp1/temp2** đều TemporaryFailure nhưng **loads-after-temp=4**: "TEMP" chạy method thật hai lần vì ngoại lệ **không khớp cachedExceptions** và còn bị nonCachedExceptions loại trừ.
- **invalidateFailure("BAD")** xóa đúng exception cache; **bad-after-evict** buộc method "BAD" chạy lại, tăng bộ đếm lên 5 rồi lưu exception mới.

**Nhóm 2 – thời điểm xóa:**
- **failDefaultRemove("OK")** ném IllegalStateException, nên mặc định afterInvocation=true **không xóa**; find("OK") vẫn đọc cache load-1.
- **failButRemove("OK")** ném IllegalStateException thuộc **evictFor**, nên vẫn xóa; find("OK") chạy mới thành load-6.
- **removeBeforeFailure("OK")** xóa trước target; mặc dù target ném lỗi, find("OK") chạy mới thành load-7.

**Nhóm 3 – @CachePut của JCache:**
- **putDefaultFailure("P","P-CACHED")** lỗi nên không put; lần find("P") load thật tạo load-8.
- **putEvenIfFailure("P","P-FORCED")** lỗi khớp **cacheFor**, nên tham số **@CacheValue** P-FORCED được put dù method thất bại.
- **putBeforeFailure("Q","Q-EARLY")** put trước method; lỗi xảy ra sau không hủy entry; find("Q") nhận Q-EARLY mà không tăng loader count.

**Nhóm 4 – xóa toàn cache và sự độc lập của exception cache:**
- **clearDefaultFailure()** lỗi theo mặc định nên **không clear records**; P-FORCED vẫn nằm trong cache.
- **clearEvenIfFailure()** lỗi khớp evictFor nên **clear records**; find("P") mới phải load thật, thành load-9.
- **bad-still-cached** vẫn trả InvalidIdException từ exception cache vì clear xảy ra với **records**, không phải **recordFailures**; tổng số lượt target find thực thi vẫn là 9.

**Giới hạn:** Đây là ví dụ định hướng theo Spring JCache interceptor sử dụng ConcurrentMapCacheManager, chạy tuần tự một tiến trình để có stdout xác định. Nó không minh họa TTL, database transaction, cache phân tán, serialization hoặc các race condition. Các cache provider khác có thể có chi tiết về visibility/exception serialization khác; phải kiểm chứng trên provider thực tế.

## 13. Cẩn thận: exception cache và result cache có lifecycle riêng

Một cached exception ổn định ngày hôm nay **không nhất thiết ổn định mãi mãi**. Ví dụ:
- User ID chưa tồn tại, sau đó được tạo mới.
- Một feature flag hoặc policy validation thay đổi.
- Mã đơn hàng trước kia không hợp lệ, sau deploy lại hợp lệ.
- Quyền truy cập của caller hoặc tenant thay đổi.
- Upstream sửa lỗi nhưng cache vẫn giữ exception của lần lỗi cũ.

Nếu hệ thống vẫn tìm thấy cached exception ở cùng key, target method **không có cơ hội xác định thực tế mới**. Cần chọn:
1. **TTL cho exception cache**, thường ngắn và phù hợp rủi ro.
2. **Invalidation trên đúng exception cache** khi nguồn trạng thái thay đổi.
3. **Version/tenant/locale/permission context trong key**, nếu chúng ảnh hưởng kết quả lỗi.
4. **Không cache lỗi tạm thời** (network timeout, rate-limit tạm, service overload).
5. **Theo dõi tỷ lệ cached exception hits** để tránh đánh đồng “service khỏe vì ít chạy” với “lỗi đang bị replay”.

**Không nhầm exception cache với negative cache null.** @CacheResult mặc định có cacheNull, nhưng liệu null có được provider lưu và phân biệt miss hay không còn phụ thuộc cache implementation. Exception caching là một cơ chế khác với việc lưu giá trị null của result.

### Những ngoại lệ không nên lưu bừa bãi

- **SecurityException / AccessDeniedException** có thể phụ thuộc caller, role và token.
- **TemporaryFailure / IOException do upstream** cần có đường retry có kiểm soát.
- **IllegalStateException mang trạng thái request** có thể chỉ hợp lệ tại thời điểm cụ thể.
- **Exception chứa request body, credentials hoặc PII** không nên đưa vào cache dùng chung.

Nếu một lỗi chỉ đúng với cặp **(tenantId, userId, resourceId, policyVersion)** thì cache key chỉ chứa resourceId có thể replay lỗi sai cho người khác. Đối với nghiệp vụ phân quyền, ưu tiên kiểm tra lại nguồn có thẩm quyền thay vì cache bừa kết quả exception.

## 14. Thời điểm xóa không phải thời điểm commit

Trong hệ thống dùng **@Transactional** và cache annotation trên cùng method, phải tách ba mốc:

~~~text
Method nghiệp vụ chạy
  -> database thay đổi trong transaction
  -> method return/throw
  -> transaction commit hoặc rollback
  -> cache put/remove trở nên quan sát được
~~~

Thứ tự thực tế của các mốc **phụ thuộc thứ tự advice, transaction-aware CacheManager và provider**. **afterInvocation=true** không tự có nghĩa **“sau commit thành công”**. Một method đã trả về bình thường ở bên trong transaction advice nhưng commit sau đó lại thất bại thì cache operation có thể đã xảy ra không đúng kỳ vọng nếu không được phối hợp.

### Hai lỗi điển hình

**Evict quá sớm:**

~~~text
Writer cập nhật DB trong transaction nhưng chưa commit
Cache entry đã bị evict
Reader khác cache MISS, đọc phiên bản DB cũ do isolation
Reader put lại dữ liệu cũ vào cache
Writer commit
Cache vẫn có thể mang snapshot cũ
~~~

**Evict có chạy nhưng loader cũ đi sau:**

~~~text
Reader R cache MISS, chụp snapshot v1
Writer W cập nhật DB v2 và evict
Reader R hoàn tất, put v1 sau eviction
Cache lại chứa dữ liệu cũ
~~~

Do đó afterInvocation=true/false và evictFor/noEvictFor giải quyết câu hỏi **khi nào yêu cầu xóa đối với một method**, chứ không giải quyết toàn bộ bài toán nhất quán giữa nhiều request.

### Cách thiết kế cho transaction

Cân nhắc transaction-aware cache operations, after-commit invalidation, outbox event, versioned key, version check/CAS hoặc per-key coordination theo mức nhất quán mong muốn. Mỗi cách có trade-off; không một annotation đơn lẻ tạo transaction nguyên tử xuyên database và cache.

Nếu method đã thay đổi một phần trạng thái rồi ném exception nhưng transaction thực sự rollback, **evictFor** có thể tạo miss không cần thiết. Nếu method đã commit một phần bên ngoài transaction trước khi ném exception, **giữ cache theo mặc định** có thể trả dữ liệu cũ. Phải dựa vào **semantics nghiệp vụ của lỗi** chứ không chỉ tên loại exception.

## 15. Các lỗi thường gặp

### 15.1. Nhầm exceptionCacheName với cacheName

~~~java
@CacheResult(
    cacheName = "records",
    exceptionCacheName = "recordFailures",
    cachedExceptions = InvalidIdException.class
)
~~~

**records** chứa kết quả thành công; **recordFailures** chứa ngoại lệ. Xóa records không tự xóa recordFailures. Nếu bạn sửa lỗi nhưng người dùng vẫn thấy exception cũ, hãy kiểm tra **exception cache**, không chỉ result cache.

### 15.2. Quên exceptionCacheName

~~~java
@CacheResult(
    cacheName = "records",
    cachedExceptions = IllegalArgumentException.class
)
~~~

Dù có whitelist, vì **exceptionCacheName chưa cấu hình**, không nên kỳ vọng exception được lưu. Cần tên exception cache và cơ chế resolve region đó.

### 15.3. Chỉ đặt exceptionCacheName, vô tình lưu mọi lỗi

~~~java
@CacheResult(
    cacheName = "records",
    exceptionCacheName = "recordFailures"
)
~~~

Khi exception cache được bật và cả hai filter rỗng, theo quy tắc JCache có thể cache **mọi ngoại lệ target**. Thường nên whitelist những lỗi ổn định qua cachedExceptions, thay vì để mặc định này.

### 15.4. Tưởng afterInvocation=false là “xóa sau method”

Trong JCache, **false nghĩa là xóa trước**; trong Spring @CacheEvict, **beforeInvocation=false nghĩa là xóa sau**. Hai thuộc tính có tên khác nhau và chiều logic ngược nhau.

### 15.5. Dùng evictFor khi đã chọn afterInvocation=false

Khi xóa trước, bộ lọc ngoại lệ của method **không có dữ liệu để xét**. evictFor/noEvictFor chỉ có ý nghĩa ở nhánh **afterInvocation=true**.

### 15.6. Tưởng evictFor biến method lỗi thành thành công

evictFor chỉ quyết định cache có được xóa khi method ném lỗi. Ngoại lệ **vẫn được truyền đến caller**; transaction/HTTP response không tự biến thành success.

### 15.7. Cho rằng @CacheRemoveAll xóa mọi region

@CacheRemoveAll(cacheName="records") chỉ nhắm **records**. Exception cache recordFailures là region khác. Nếu muốn dọn cả hai, phải có chiến lược invalidation cho cả hai, kiểm tra quyền sở hữu và tránh clear rộng gây tải lớn.

### 15.8. Import sai @CachePut

~~~java
// JCache: dùng @CacheValue từ javax.cache.annotation.
@CachePut(cacheName = "records", afterInvocation = false)
public void save(@CacheKey String id, @CacheValue String value) {
    // ...
}
~~~

Nếu IDE chọn Spring @CachePut, các thuộc tính cacheName/afterInvocation và @CacheValue theo JCache **không phải API của Spring @CachePut**.

### 15.9. Dùng JCache @CacheKey sai, không xóa được entry

Nếu @CacheResult dùng @CacheKey cho id nhưng @CacheRemove sử dụng một bộ tham số key khác, hai operation có thể chọn **hai generated keys khác nhau**. Dù cùng cacheName, xóa sẽ miss. Kiểm tra key generator, danh sách @CacheKey, kiểu tham số, tenant/namespace và equality.

### 15.10. Cache ngoại lệ phụ thuộc ngữ cảnh

Khi một lỗi phụ thuộc user/tenant/permission nhưng key không chứa các yếu tố đó, hệ thống có thể trả cached exception của một caller khác. Đừng cache lỗi phân quyền trên key dùng chung thiếu ngữ cảnh; nhiều trường hợp nên không cache những lỗi này.

### 15.11. Không có proxy interception

Java annotation không tự chạy. Cần Spring @EnableCaching, JCache API và spring-context-support; method phải được gọi **qua Spring bean proxy**. Self-invocation trong proxy mode có thể khiến cả exception caching và eviction bị bỏ qua.

### 15.12. Đánh đồng CacheException với nghiệp vụ exception

**javax.cache.CacheException** là lỗi của Cache API/provider. Caching business exception trong @CacheResult không hứa hấp thụ lỗi kết nối Redis hoặc lỗi serialize. Khi debug, phân biệt lỗi từ target method với lỗi của cache implementation.

## 16. Checklist kiểm thử tích hợp

| Test | Chuẩn bị | Kết quả cần xác minh |
| --- | --- | --- |
| Result hit | @CacheResult gọi cùng key hai lần | Method thật chạy một lần, result được tái sử dụng |
| Exception cache hit | Lỗi thuộc cachedExceptions, exceptionCacheName hợp lệ | Lần hai ném lỗi nhưng **không** chạy target |
| Exception bị loại trừ | Lỗi thuộc nonCachedExceptions | Hai lần đều chạy target, không lưu ngoại lệ |
| Chỉ có exceptionCacheName | Hai bộ lọc rỗng | Cân nhắc đặc tính mặc định có thể cache mọi lỗi |
| Thiếu exceptionCacheName | Chỉ khai báo cachedExceptions | Không kỳ vọng exception caching |
| skipGet | Bật skipGet=true | Bỏ qua lookup result/exception trước method, target luôn chạy |
| Remove thành công | @CacheRemove default | Entry được xóa sau method |
| Remove thất bại mặc định | Method ném lỗi, filter rỗng | Entry giữ nguyên |
| Remove thất bại khớp evictFor | afterInvocation=true | Entry bị xóa dù lỗi |
| Remove thất bại khớp noEvictFor | afterInvocation=true | Entry không bị xóa |
| Remove trước | afterInvocation=false | Xóa trước method, không phụ thuộc exception xảy ra sau |
| RemoveAll thất bại mặc định | Method ném lỗi | Region không bị clear |
| RemoveAll với evictFor | Method ném lỗi khớp filter | Region bị clear |
| Put thất bại mặc định | JCache @CachePut afterInvocation=true | Không ghi @CacheValue |
| Put khi lỗi thuộc cacheFor | JCache @CachePut afterInvocation=true | Ghi @CacheValue dù lỗi |
| Put trước method | afterInvocation=false | Entry có thể được ghi ngay cả khi method sau lỗi |
| Exception cache lifecycle | Xóa result cache nhưng không xóa exception cache | Cached exception vẫn có thể được replay |
| Transaction boundary | Thử rollback/commit và cache event | Xác minh thời điểm thật, không suy từ annotation |
| Concurrent reader | Reader đang load trong lúc evict | Kiểm tra stale repopulation và chiến lược xử lý |
| Multi-instance/provider | Provider production, nhiều node | Kiểm tra TTL/serialization/visibility/invalidation |

**Ưu tiên integration test bằng Spring ApplicationContext** để xác minh annotation đã được intercept, thay vì chỉ unit test gọi thẳng vào target object. Với JCache, phải đặt đúng tên cache và kiểm tra cả **data region** lẫn **exception region**. Dùng bộ đếm method thật trong test để phát hiện exception đang được replay.

## 17. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** @CacheResult(cacheName="a", exceptionCacheName="b") nhưng cả cachedExceptions và nonCachedExceptions đều rỗng. Exception target có thể bị cache không?

**Đáp:** Có. Khi exception cache đã bật và cả hai filter rỗng, quy tắc JCache cho phép lưu mọi ngoại lệ target theo cấu hình.

**Câu 2.** @CacheResult có cachedExceptions=InvalidIdException.class nhưng exceptionCacheName chưa đặt. Lỗi có được cache không?

**Đáp:** Không tự được bật. Cần exceptionCacheName để có cache chuyên lưu exception.

**Câu 3.** cachedExceptions=RuntimeException.class, nonCachedExceptions=TimeoutException.class, và TimeoutException extends RuntimeException. TimeoutException có được cache không?

**Đáp:** Không; thuộc loại loại trừ. Mọi exception cache còn phải có exceptionCacheName.

**Câu 4.** JCache @CacheRemove(afterInvocation=true) mặc định gặp exception trong method. Có xóa không?

**Đáp:** Không. Mặc định khi method ném exception, việc xóa không xảy ra; có thể cấu hình evictFor/noEvictFor nếu cần.

**Câu 5.** JCache @CacheRemove(afterInvocation=false, evictFor=IllegalStateException.class) rồi method ném IOException. Có xóa không?

**Đáp:** Có thể đã xóa từ trước khi method chạy; filter evictFor không được xét vì afterInvocation=false. Việc cache provider áp dụng xóa có hiệu lực khi nào còn phụ thuộc implementation.

**Câu 6.** JCache @CacheRemove(evictFor=RuntimeException.class, noEvictFor=TemporaryFailure.class), method ném TemporaryFailure extends RuntimeException. Có xóa không?

**Đáp:** Không, vì noEvictFor loại trừ loại exception đó.

**Câu 7.** Spring @CacheEvict(beforeInvocation=true) tương ứng với JCache setting nào?

**Đáp:** **@CacheRemove(afterInvocation=false)** về thời điểm xóa key. Hai annotation không hoàn toàn tương đương ở khả năng filter khi method ném exception.

**Câu 8.** JCache @CachePut(afterInvocation=true) cần chọn giá trị sẽ ghi từ đâu?

**Đáp:** Từ **tham số đánh dấu @CacheValue**, khác Spring @CachePut lấy **giá trị method trả về**.

**Câu 9.** Khi JCache @CachePut có cacheFor=IllegalStateException.class và method ném IllegalStateException, method có thành công không?

**Đáp:** Không. Method vẫn ném lỗi; cacheFor chỉ cho phép ghi @CacheValue dù invocation thất bại.

**Câu 10.** Xóa data cache đã đồng nghĩa xóa cached exception cho cùng key chưa?

**Đáp:** Chưa. Hai cache regions độc lập; cần xử lý exceptionCacheName tương ứng, TTL hoặc versioned key.

**Câu 11.** @CacheResult(skipGet=true) có còn cache exception mới sau invocation không?

**Đáp:** Có thể, nếu exceptionCacheName và filter cho phép. skipGet chỉ bỏ qua lookup trước invocation.

**Câu 12.** Vì sao afterInvocation=true không chứng minh xóa sau commit?

**Đáp:** Vì method invocation boundary và database transaction commit boundary có thể khác nhau do thứ tự advice/provider; phải kiểm thử thực tế hoặc dùng phối hợp after-commit rõ ràng.

## Tổng kết

- JCache **@CacheResult** có thể lưu **ngoại lệ nghiệp vụ được chọn** trong **exceptionCacheName** riêng; thiếu exceptionCacheName thì không có exception caching. Khi đã bật exception cache nhưng để hai filter rỗng, quy tắc JCache có thể cache **tất cả ngoại lệ**.
- **cachedExceptions/nonCachedExceptions** là bộ lọc **lưu Throwable**; **evictFor/noEvictFor** của @CacheRemove/@CacheRemoveAll là bộ lọc **xóa khi lỗi**; **cacheFor/noCacheFor** của JCache @CachePut là bộ lọc **ghi @CacheValue khi lỗi**.
- JCache **afterInvocation=true** (mặc định) yêu cầu xóa/ghi sau method, mặc định không thao tác nếu method ném ngoại lệ; cấu hình filter có thể thay đổi nhánh lỗi. **afterInvocation=false** làm thao tác trước invocation, filter lỗi không áp dụng.
- Spring **@CacheEvict(beforeInvocation=true)** tương ứng với JCache **@CacheRemove(afterInvocation=false)** về hướng thời điểm, nhưng **không** có evictFor/noEvictFor trên annotation Spring.
- Exception cache và result cache có **lifecycle riêng**. Xóa một cache không tự xóa cache kia; luôn xét key, TTL, invalidation, transaction và race condition trước khi đưa lên production.

### Tài liệu tham khảo

- Spring Framework 6.2 – JCache (JSR-107) annotations và sự khác biệt với annotation Spring: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/jsr-107.html
- Spring Framework 6.2 – Spring @CacheEvict và beforeInvocation: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- JSR-107 CacheResult Javadoc 1.1.1 (exceptionCacheName, cachedExceptions, nonCachedExceptions, skipGet): https://javadoc.io/doc/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheResult.html
- JSR-107 CacheRemove Javadoc 1.1.1 (afterInvocation, evictFor, noEvictFor): https://javadoc.io/doc/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheRemove.html
- JSR-107 CacheRemoveAll Javadoc 1.1.1: https://javadoc.io/doc/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheRemoveAll.html
- JSR-107 CachePut Javadoc 1.1.1 (CacheValue, afterInvocation, cacheFor, noCacheFor): https://javadoc.io/doc/javax.cache/cache-api/1.1.1/javax/cache/annotation/CachePut.html
- Spring Framework – DefaultJCacheOperationSource và hỗ trợ Spring CacheManager: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/jcache/interceptor/DefaultJCacheOperationSource.html
