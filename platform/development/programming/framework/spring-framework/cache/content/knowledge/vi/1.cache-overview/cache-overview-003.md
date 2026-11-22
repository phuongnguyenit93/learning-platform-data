# Cache hit, cache miss và dữ liệu cũ trong Spring Framework

## 1. Ba khái niệm cần phân biệt

Cache lưu tạm kết quả theo cặp **khóa (key) → giá trị (value)** để tránh lặp lại thao tác tốn chi phí như đọc cơ sở dữ liệu hoặc gọi API. Trong Spring Framework, `@Cacheable` diễn tả quy tắc tra cứu và lưu kết quả; việc chứa dữ liệu, hết hạn và phân tán cache phụ thuộc vào `CacheManager` cùng nhà cung cấp cache được cấu hình.

| Hiện tượng | Điều gì xảy ra khi đọc? | Tác động thường gặp |
| --- | --- | --- |
| **Cache hit (trúng cache)** | Khóa đã có một giá trị hợp lệ theo chính sách cache; trả giá trị từ cache, thông thường không thực thi thân phương thức được gắn `@Cacheable`. | Phản hồi nhanh, ít tải lên nguồn dữ liệu. |
| **Cache miss (trượt cache)** | Không có giá trị dùng được cho khóa, ví dụ chưa lưu, vừa bị xóa hoặc đã hết hạn. Spring gọi phương thức để lấy dữ liệu; kết quả có thể được lưu theo cấu hình. | Có chi phí đọc nguồn dữ liệu, thường chậm hơn hit. |
| **Stale data (dữ liệu cũ)** | Cache trả một phiên bản không còn khớp với dữ liệu mới nhất tại nguồn. | Đọc có thể rất nhanh nhưng **sai về độ mới**. |

**Hit/miss nói về kết quả tra cứu cache; stale nói về tính mới của nội dung.** Một cache hit hoàn toàn có thể trả dữ liệu cũ. Cache miss không mặc nhiên là lỗi, cũng không bảo đảm dữ liệu nguồn luôn mới tuyệt đối (nguồn có thể đang đọc replica chậm đồng bộ).

Khi lời gọi đi qua Spring cache interceptor, luồng thông dụng của `@Cacheable` là:

1. Xác định tên cache và khóa từ tham số phương thức.
2. Hỏi cache có giá trị cho khóa đó hay không.
3. **Hit:** trả kết quả đã lưu mà không chạy phần thân phương thức.
4. **Miss:** chạy phần thân, nhận kết quả rồi cân nhắc lưu vào cache theo `condition`, `unless`, khả năng lưu `null` và quy tắc của provider.
5. Các lời gọi sau cho cùng khóa có thể trở thành hit cho đến khi phần tử bị xóa, hết hạn hoặc cache bị thay thế.

Luồng này là mô hình thông thường, không phải cam kết một lần tải duy nhất dưới mọi tình huống đồng thời: nhiều yêu cầu đến ngay lúc cùng miss có thể cùng thực thi phương thức nếu provider/chính sách không gom các lượt tải.

## 2. Dữ liệu trở nên cũ như thế nào?

Giả sử dữ liệu của sản phẩm `p1` ở cơ sở dữ liệu ban đầu là `"Bản A"`, và cache dùng khóa `p1`:

| Thời điểm | Hành động | Cache | Nguồn dữ liệu | Kết quả đọc |
| --- | --- | --- | --- | --- |
| T0 | Gọi đọc `p1` lần đầu | Chưa có khóa → **miss**, nạp `"Bản A"` | `"Bản A"` | `"Bản A"` |
| T1 | Gọi đọc `p1` lần hai | Có khóa → **hit** | `"Bản A"` | `"Bản A"` |
| T2 | Một đường ghi khác sửa nguồn | Cache **vẫn là** `"Bản A"` | **`"Bản B"`** | Chưa đọc |
| T3 | Gọi đọc `p1` lần ba | **Hit**, nhưng trả bản cũ | `"Bản B"` | **`"Bản A"` (stale)** |
| T4 | Ghi dữ liệu và xóa cache cùng khóa | Khóa `p1` bị evict | `"Bản C"` | Chưa đọc |
| T5 | Đọc `p1` tiếp theo | **Miss**, nạp bản mới | `"Bản C"` | `"Bản C"` |
| T6 | Đọc `p1` thêm lần nữa | **Hit** | `"Bản C"` | `"Bản C"` |

Ở T3, cache vẫn hoạt động đúng theo chức năng tra cứu, nhưng quá trình cập nhật nguồn đã **không đồng bộ hóa** phiên bản trong cache. Đây là lỗi nhất quán dữ liệu, không phải một cache miss.

Độ cũ có thể xuất phát từ cập nhật trực tiếp vào database, tác vụ nền, một service khác, một instance ứng dụng khác chỉ có cache cục bộ, hoặc chính sách TTL chưa hết hạn. TTL giới hạn khoảng thời gian một giá trị được giữ theo quy tắc provider; TTL tự nó **không** đồng nghĩa dữ liệu sẽ được cập nhật ngay khi nguồn thay đổi.

## 3. Ví dụ Java 17+ với Spring Boot và Spring Cache

Tạo một ứng dụng Spring Boot 3.x có dependency `org.springframework.boot:spring-boot-starter-cache`, dùng Java 17 trở lên. Dưới đây là toàn bộ mã cho một file `src/main/java/com/example/cachedemo/CacheDemoApplication.java`. Dự án cần cấu hình plugin Spring Boot và Gradle như ứng dụng Spring Boot thông thường.

~~~java
package com.example.cachedemo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableCaching
public class CacheDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    CommandLineRunner demo(ProductService service, ProductStore store) {
        return args -> {
            System.out.println("1: " + service.getName("p1"));
            System.out.println("2: " + service.getName("p1"));

            // Mô phỏng một hệ thống khác ghi nguồn mà không xóa cache.
            store.save("p1", "Bản B");
            System.out.println("3: " + service.getName("p1"));

            // Đường ghi có quản lý invalidation.
            service.updateName("p1", "Bản C");
            System.out.println("4: " + service.getName("p1"));
            System.out.println("5: " + service.getName("p1"));
        };
    }
}

@Repository
class ProductStore {
    private final ConcurrentMap<String, String> data =
            new ConcurrentHashMap<>(Map.of("p1", "Bản A"));

    String findName(String id) {
        System.out.println("LOAD " + id);
        return data.get(id);
    }

    void save(String id, String name) {
        data.put(id, name);
    }
}

@Service
class ProductService {
    private final ProductStore store;

    ProductService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public String getName(String id) {
        return store.findName(id);
    }

    @CacheEvict(cacheNames = "products", key = "#p0")
    public void updateName(String id, String name) {
        store.save(id, name);
    }
}
~~~

Nếu dùng Gradle Groovy trong dự án Boot đã cấu hình, cần có dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Chạy ứng dụng bằng `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Bỏ qua thông báo khởi động của Spring Boot, **các dòng do đoạn demo chủ động in ra** theo đúng thứ tự là:

~~~text
LOAD p1
1: Bản A
2: Bản A
3: Bản A
LOAD p1
4: Bản C
5: Bản C
~~~

Diễn giải:

- Lần **1**: `products[p1]` chưa có → miss → `ProductStore.findName` chạy và in `LOAD p1`; Spring lưu `"Bản A"`.
- Lần **2**: hit → lấy `"Bản A"` trực tiếp; không có thêm dòng `LOAD`.
- Lần **3**: `store.save` đã thay nguồn thành `"Bản B"` nhưng cache chưa đổi → hit trả `"Bản A"` (**stale**).
- `service.updateName` cập nhật `"Bản C"` và `@CacheEvict` xóa đúng `products[p1]` sau khi phương thức hoàn thành thành công theo chế độ mặc định.
- Lần **4**: miss sau eviction → tải `"Bản C"`. Lần **5**: hit với `"Bản C"`.

Chú ý: `#p0` là tham số thứ nhất, nên ví dụ không phụ thuộc vào việc compiler giữ tên tham số `id`. `ConcurrentMapCacheManager` chỉ là cache trong bộ nhớ từng tiến trình, **không có TTL tự động** và không chia sẻ nội dung giữa các instance; ví dụ cố ý sử dụng nó để nhìn rõ hit, miss và stale. Trong ứng dụng thực tế, có thể chọn Caffeine, Redis hoặc provider tương thích tùy nhu cầu.

## 4. Làm gì để tránh hoặc giới hạn stale data?

Không có một chính sách cache hợp lý cho mọi loại dữ liệu. Chọn theo độ mới bắt buộc, tải hệ thống, chi phí nguồn và khả năng nhiều bên cùng cập nhật.

| Cách xử lý | Cơ chế | Điều cần nhớ |
| --- | --- | --- |
| **Evict khi ghi** | Sau thay đổi thành công, xóa khóa bị ảnh hưởng bằng `@CacheEvict(cacheNames = "products", key = "#p0")`; lần đọc kế tiếp sẽ miss và tải lại. | Phải bao phủ **mọi** đường ghi quan trọng, bao gồm tiến trình và service ngoài ứng dụng. |
| **Cập nhật cache khi ghi** | `@CachePut` luôn thực thi phương thức và đưa **giá trị trả về** vào cache theo khóa. | Đảm bảo giá trị trả về chính là bản muốn cache; tránh cập nhật nguồn và cache lệch nhau. |
| **TTL / hết hạn** | Provider tự coi phần tử hết hạn sau một khoảng thời gian; lần đọc sau đó tải lại. | Chọn TTL theo yêu cầu độ mới; ngắn quá gây nhiều miss, dài quá kéo dài stale. Spring Cache abstraction không tự đặt TTL chung cho mọi provider. |
| **Sự kiện invalidation** | Khi dữ liệu thay đổi, phát thông báo để các instance xóa hoặc cập nhật khóa liên quan. | Cần tính đến trễ, mất sự kiện, đua tranh và cơ chế khôi phục. |
| **Cache chung / có phối hợp** | Các instance dùng chung backend cache hoặc đồng bộ invalidation. | Giảm lệch cache giữa instance, nhưng vẫn cần quy tắc khi dữ liệu nguồn đổi. |
| **Không cache dữ liệu cần độ mới tuyệt đối** | Đọc trực tiếp nguồn nhất quán phù hợp, hoặc thiết kế giao thức kiểm tra phiên bản trước khi trả kết quả. | Chấp nhận thêm độ trễ/chi phí để đổi lấy tính đúng đắn. |

Với một bản ghi được cập nhật, ưu tiên khóa đủ cụ thể: xóa `products[p1]` thay vì xóa mọi phần tử khi quan hệ dữ liệu cho phép. `@CacheEvict(allEntries = true)` chỉ hợp lý khi thay đổi thật sự làm vô hiệu toàn bộ cache; xóa rộng gây bùng nổ miss.

Nếu cập nhật database nằm trong transaction, cần phân tích **thời điểm commit và thời điểm invalidation**. Một thao tác evict chạy trước khi transaction commit có thể khiến yêu cầu khác tải lại dữ liệu cũ. Với yêu cầu nhất quán chặt, triển khai cơ chế evict sau commit hoặc phối hợp transaction/cache một cách rõ ràng; đừng suy luận rằng thêm `@Transactional` và `@CacheEvict` bất kỳ là luôn an toàn.

## 5. Đọc đúng các số đo và tín hiệu

Để kiểm chứng cache, quan sát ít nhất **hit, miss, lần tải nguồn, độ trễ và độ mới dữ liệu**. Khi provider cung cấp số đếm, hit ratio thường được tính:

`hit ratio = hits / (hits + misses)` (chỉ khi mẫu số lớn hơn 0).

Ví dụ 80 hit và 20 miss cho tỷ lệ hit 80%, nhưng **không nói gì về việc 80 hit đó có stale hay không**. Tỷ lệ hit cao chỉ chứng tỏ nhiều lượt đọc được phục vụ từ cache. Nên gắn thêm chỉ số nghiệp vụ như tuổi dữ liệu, phiên bản, thời điểm cập nhật nguồn, tần suất eviction và lỗi đồng bộ. Không mặc định mọi provider đều tự phát số đo hit/miss cho Spring; khả năng quan sát phụ thuộc cấu hình cache và metrics.

Một số dấu hiệu khi kiểm thử:

- Phương thức tải dữ liệu chỉ in log ở lượt đầu, các lượt sau không in → phù hợp mẫu hit sau miss.
- Sau khi thay đổi nguồn, lần đọc kế tiếp vẫn trả giá trị cũ → có stale hoặc nguồn đọc chưa được đồng bộ.
- Sau eviction, lượt đầu tải lại và lượt sau không tải → phù hợp mẫu miss rồi hit.
- Mỗi lần đều tải nguồn → có thể key khác nhau, cache không được bật, không qua proxy, dữ liệu bị evict/expire hoặc không được lưu.

## 6. Những nhầm lẫn thường gặp trong Spring Cache

1. **“Cache hit là dữ liệu mới nhất.”** Không đúng: hit chỉ nói rằng cache đang giữ giá trị cho khóa, không chứng minh giá trị đồng bộ với nguồn.
2. **“Sửa database thì `@Cacheable` tự biết.”** Không đúng: Spring không tự theo dõi mọi thay đổi của nguồn dữ liệu. Cần invalidation, cập nhật cache hoặc cơ chế phối hợp riêng.
3. **“Cache miss luôn tạo một bản ghi cache.”** Không hẳn: lỗi trong phương thức, `condition`/`unless`, xử lý `null` hoặc chính sách provider có thể khiến không lưu.
4. **“Gọi `this.getName(...)` trong cùng bean vẫn được `@Cacheable`.”** Với Spring proxy mode thông dụng, self-invocation không đi qua proxy nên lời gọi đó không được interceptor xử lý.
5. **“Một key miss chỉ chạy backend một lần khi có nhiều request đồng thời.”** Không có bảo đảm chung. `@Cacheable(sync = true)` có thể gom các lượt tải cùng key khi provider hỗ trợ đúng contract, nhưng cần kiểm tra provider, lỗi và điều kiện thực tế.
6. **“Cache cục bộ ở các instance luôn giống nhau.”** Không đúng: `ConcurrentMapCacheManager` hay local Caffeine ở mỗi process có trạng thái riêng; một instance xóa cache không tự xóa cache ở instance khác.
7. **“Chỉ cần TTL là không còn stale.”** TTL thường chỉ giới hạn thời gian giữ bản cũ theo cấu hình, không loại bỏ cửa sổ stale trước khi hết hạn.

## 7. Tự kiểm tra

Xét một khóa `user:42`. Sau lần đọc đầu, cache chứa phiên bản `V1`. Một tác vụ nền cập nhật nguồn thành `V2` mà không xóa cache.

- Lần đọc kế tiếp qua cache là **hit hay miss**? → **Hit** nếu phần tử chưa hết hạn/bị xóa.
- Giá trị trả về có thể là gì? → **V1**, tức dữ liệu **stale** dù hit thành công.
- Nếu xóa `user:42` rồi đọc lại? → **Miss**, tải từ nguồn và có thể lưu **V2** (giả sử nguồn đã thấy V2 và chính sách cho phép lưu).
- Nếu chỉ giảm TTL xuống 5 giây? → Có thể giảm thời gian stale nhưng tăng miss/tải nguồn; không bảo đảm phản ánh thay đổi ngay thời điểm cập nhật.

**Điểm cần nhớ:** Tối ưu cache chỉ có ý nghĩa khi độ mới dữ liệu vẫn đáp ứng yêu cầu nghiệp vụ. Khi thiết kế một đường ghi, hãy xác định rõ khóa cache liên quan, ai có quyền sửa dữ liệu nguồn, khi nào invalidation chạy và làm sao chứng minh kết quả đọc không quá cũ.
