# Khám phá cache bằng endpoint `caches` và phạm vi thao tác xóa cache

## 1. Hiểu đúng đối tượng đang quan sát

Bộ nhớ đệm (cache) giữ kết quả để ứng dụng có thể dùng lại thay vì tính toán hoặc đọc nguồn dữ liệu cho mỗi yêu cầu. Trong Spring, một `CacheManager` quản lý các cache có tên; mỗi cache chứa những phần tử được xác định bằng khóa (key).

Ví dụ một ứng dụng bán hàng có cấu trúc:

~~~text
Ứng dụng
├── inventoryCacheManager
│   ├── products
│   │   ├── p1 → inventory-1
│   │   └── p2 → inventory-2
│   └── categories
│       └── c1 → hardware
└── partnerCacheManager
    └── products
        └── p1 → partner-1
~~~

Có hai cache cùng tên `products`, nhưng chúng thuộc hai bộ quản lý khác nhau. Vì vậy, định danh thao tác đáng tin cậy là **cặp tên CacheManager và tên cache**, không chỉ tên cache.

Endpoint tích hợp `caches` của Spring Boot Actuator giúp người vận hành tìm cache mà ứng dụng đang quản lý và yêu cầu làm rỗng cache. Nó kết nối thông tin vận hành với lớp trừu tượng cache của Spring; thư viện cung cấp cache bên dưới mới quyết định cách lưu và xóa dữ liệu thực tế.

Ba việc cần phân biệt:

- **Khám phá cache:** biết có những bộ quản lý và cache nào.
- **Đọc phần tử:** lấy giá trị ứng với một khóa.
- **Làm rỗng cache:** loại bỏ mọi phần tử trong phạm vi được chọn.

`caches` hỗ trợ việc thứ nhất và thứ ba. Nó không cung cấp API duyệt khóa hay xem giá trị phần tử. Tên lớp trong trường `target` mô tả đối tượng cache gốc, không phải nội dung lưu trong cache. Xem [hợp đồng HTTP của endpoint trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/caches.html).

Bài này dùng Spring Boot **3.3.x**, Java **17 trở lên**. Ví dụ chạy được bên dưới cố định Boot **3.3.0** và Spring Framework **6.1.8** để quan sát hành vi cụ thể.

## 2. Điều kiện để gọi qua HTTP

Trong một ứng dụng web Spring Boot, cần có Actuator và các `CacheManager` được đăng ký thành bean. Ví dụ khai báo các dependency Gradle sau trong dự án đã được quản lý phiên bản Spring Boot 3.3:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Đây là đoạn cấu hình ghép vào dự án Spring Boot hiện có, không phải một dự án Gradle độc lập.

Ví dụ cấu hình lab tại `application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    caches:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,caches
~~~

Trong Boot 3.3, **enabled** và **exposed** là hai điều kiện riêng: bật endpoint không đồng nghĩa đã công bố qua HTTP. Mặc định chỉ `health` được công bố qua HTTP; nếu có cấu hình `exclude`, nó được ưu tiên hơn `include`. Các URL trong bài giả định cổng `8080`, đường dẫn quản trị `/actuator` và không có tiền tố context path khác. Nguồn: [cấu hình và công bố endpoint của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

`@EnableCaching` dùng để kích hoạt cơ chế xử lý các annotation như `@Cacheable`. Không nên coi nó là công tắc của Actuator: nếu tự đăng ký `CacheManager` rồi dùng trực tiếp API `Cache`, vẫn có thể quan sát các cache đó mà không cần dùng annotation cache.

Đoạn Java sau minh họa hai bean phù hợp với sơ đồ trên. Ghép các method này vào một lớp `@Configuration` của ứng dụng web; cần import `Bean`, `CacheManager`, `ConcurrentMapCacheManager` và `Objects` tương ứng:

~~~java
@Bean
CacheManager inventoryCacheManager() {
    var manager = new ConcurrentMapCacheManager("products", "categories");
    Objects.requireNonNull(manager.getCache("products"))
            .put("p1", "inventory-1");
    Objects.requireNonNull(manager.getCache("categories"))
            .put("c1", "hardware");
    return manager;
}

@Bean
CacheManager partnerCacheManager() {
    var manager = new ConcurrentMapCacheManager("products");
    Objects.requireNonNull(manager.getCache("products"))
            .put("p1", "partner-1");
    return manager;
}
~~~

Tên bean mặc định là tên method, nên giá trị dùng trong tham số `cacheManager` là `inventoryCacheManager` hoặc `partnerCacheManager`.

Với `ConcurrentMapCacheManager`, constructor nhận danh sách tên tạo tập cache cố định cho lab. Constructor không tham số cho phép tạo cache động khi ứng dụng yêu cầu chúng; lúc quan sát, cần phân biệt cache đã được bộ quản lý biết đến với tên cache chỉ mới được dự kiến trong thiết kế. Nguồn: [API ConcurrentMapCacheManager](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html).

## 3. Khám phá trước khi chọn phạm vi

### 3.1. Liệt kê các cache

Trong terminal, gọi:

~~~shell
curl -i "http://localhost:8080/actuator/caches"
~~~

Nếu dùng Windows PowerShell có alias `curl`, dùng `curl.exe` để gọi đúng công cụ dòng lệnh. Các lệnh HTTP trong bài giả định đã được cấp quyền truy cập.

Phần thân JSON tương ứng với hai bean ở trên có cấu trúc sau; thứ tự các thuộc tính JSON không phải điều kiện để xác định đúng kết quả:

~~~json
{
  "cacheManagers": {
    "inventoryCacheManager": {
      "caches": {
        "products": {
          "target": "java.util.concurrent.ConcurrentHashMap"
        },
        "categories": {
          "target": "java.util.concurrent.ConcurrentHashMap"
        }
      }
    },
    "partnerCacheManager": {
      "caches": {
        "products": {
          "target": "java.util.concurrent.ConcurrentHashMap"
        }
      }
    }
  }
}
~~~

Đọc từ ngoài vào trong: tên bộ quản lý → `caches` → tên cache → `target`. Khi làm việc với endpoint, hãy lấy tên bộ quản lý từ kết quả thực tế thay vì suy ra từ tên loại Java.

### 3.2. Xem một cache cụ thể

~~~shell
curl -i "http://localhost:8080/actuator/caches/products?cacheManager=inventoryCacheManager"
~~~

Phần thân:

~~~json
{
  "target": "java.util.concurrent.ConcurrentHashMap",
  "name": "products",
  "cacheManager": "inventoryCacheManager"
}
~~~

Với tên duy nhất như `categories`, có thể bỏ tham số `cacheManager`. Với `products` xuất hiện ở cả hai bộ quản lý, phải chỉ rõ bộ quản lý. Các trường và quy tắc định danh này thuộc [hợp đồng endpoint caches](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/caches.html#caches.retrieving-by-name).

**Không suy luận số phần tử từ JSON trên.** Một cache có hàng nghìn phần tử và một cache vừa được làm rỗng vẫn có thể trả cùng metadata. Muốn biết một khóa còn được lưu hay không, phải quan sát qua ứng dụng hoặc cơ chế riêng của nhà cung cấp cache.

## 4. Bốn thao tác và phạm vi tương ứng

| Yêu cầu HTTP | Phạm vi |
| --- | --- |
| `GET /actuator/caches` | Metadata các cache mà endpoint nhìn thấy |
| `GET /actuator/caches/{name}?cacheManager={manager}` | Metadata một cache đã định danh |
| `DELETE /actuator/caches/{name}?cacheManager={manager}` | Mọi phần tử của đúng cache đó |
| `DELETE /actuator/caches` | Mọi phần tử trong tất cả cache mà endpoint nhìn thấy, qua các bộ quản lý của nó |

### 4.1. Xóa một cache theo tên là xóa mọi phần tử trong cache đó

~~~shell
curl -i -X DELETE "http://localhost:8080/actuator/caches/products?cacheManager=inventoryCacheManager"
~~~

Trong ví dụ, thao tác loại bỏ cả `p1` và `p2` của cache `products` thuộc kho hàng. Nó giữ nguyên cache `categories` và cache `products` của đối tác.

Tên `products` chỉ vùng cache, không phải khóa phần tử. Nếu chỉ muốn loại bỏ `p1`, ứng dụng cần thao tác có phạm vi khóa, chẳng hạn `cache.evict("p1")` hoặc một hành động nghiệp vụ dùng `@CacheEvict`. Endpoint tích hợp này không có tham số `key` và không có đường dẫn chuẩn `/actuator/caches/products/p1` để làm việc đó.

### 4.2. Xóa ở đường dẫn gốc có phạm vi rộng hơn

~~~shell
curl -i -X DELETE "http://localhost:8080/actuator/caches"
~~~

Trong lab, cả hai cache `products` và cache `categories` đều bị làm rỗng.

**Tham số `cacheManager` chỉ định danh cho thao tác theo tên cache.** Không dùng `DELETE /actuator/caches?cacheManager=inventoryCacheManager` để thể hiện “xóa mọi cache trong một bộ quản lý”: thao tác gốc `clearCaches()` không nhận tham số bộ quản lý và không cung cấp bộ lọc đó. Muốn xử lý một bộ quản lý, phải xác định rõ các cache của nó và thao tác từng cache, hoặc thiết kế một hành động quản trị riêng với hợp đồng rõ ràng. Đối chiếu chữ ký và phạm vi tại [API CachesEndpoint của Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/cache/CachesEndpoint.html).

### 4.3. Làm rỗng không xóa định nghĩa cache

Với bộ quản lý trong lab, sau DELETE:

- Đối tượng cache và tên `products` vẫn tồn tại.
- Các phần tử cũ của cache đã chọn không còn.
- Một lần ghi hoặc nạp dữ liệu sau đó có thể đưa phần tử mới vào cache.

Bởi vậy, `GET /actuator/caches/products?cacheManager=inventoryCacheManager` tiếp tục trả metadata là kết quả phù hợp. Việc tên cache vẫn xuất hiện không chứng minh DELETE thất bại.

## 5. Cơ chế chọn cache và ý nghĩa trạng thái HTTP

Có thể đọc luồng xử lý theo tên như sau:

~~~text
Nhận tên cache và bộ quản lý tùy chọn
    ↓
Tìm các cache phù hợp trong các CacheManager
    ↓
0 kết quả → không tìm thấy
1 kết quả → đọc metadata hoặc gọi Cache.clear()
nhiều kết quả → yêu cầu mơ hồ, không tự chọn một cache
~~~

Trong Spring Boot 3.3, lớp `CachesEndpointWebExtension` chuyển kết quả tìm kiếm và xóa theo tên sang mã HTTP:

| Tình huống | GET theo tên | DELETE theo tên |
| --- | --- | --- |
| Định danh được một cache | `200` kèm metadata | `204`, không có phần thân |
| Không tìm thấy cache phù hợp | `404` | `404` |
| Nhiều cache trùng tên, thiếu bộ quản lý | `400` | `400` |

Các mã này giả định yêu cầu đã đi qua lớp bảo mật và định tuyến đến đúng endpoint. `@Primary` giải quyết việc chọn bean trong những ngữ cảnh tiêm phụ thuộc thích hợp; nó không thay thế tham số `cacheManager` để bỏ qua sự mơ hồ trong phép tìm kiếm của endpoint.

`204` không cho biết số phần tử vừa xóa. Một cache đã trống vẫn có thể nhận DELETE thành công. Ngược lại, tên bộ quản lý sai dẫn tới không tìm thấy cặp phù hợp, dù cache cùng tên tồn tại ở bộ quản lý khác.

Các kết quả theo tên được kiểm chứng bằng ví dụ chạy ở phần tiếp theo. Hợp đồng Java về trường hợp không tìm thấy và tên không duy nhất được mô tả tại [API CachesEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/cache/CachesEndpoint.html#cache(java.lang.String,java.lang.String)).

## 6. Thí nghiệm Java chạy độc lập để nhìn thấy dữ liệu trước và sau xóa

Ví dụ này gọi trực tiếp chính `CachesEndpoint` và lớp mở rộng web của Actuator. Nó **không khởi động máy chủ HTTP**; các số in ra là trạng thái do lớp mở rộng web trả về. Cách làm này giúp quan sát chính xác dữ liệu trong bộ nhớ mà không cần tạo API đọc giá trị cache cho người vận hành.

Tạo thư mục lab riêng với `pom.xml` và `CachesScopeDemo.java` ở cùng cấp. Đây là một chương trình Java độc lập, không ghép vào module Spring Boot đang chạy.

### 6.1. Dependency cho lab

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>caches-scope-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator</artifactId>
            <version>3.3.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.8</version>
        </dependency>
    </dependencies>
</project>
~~~

Maven chỉ dùng để lấy classpath dependency; lệnh bên dưới dùng trực tiếp `javac` và `java` để biên dịch và chạy.

### 6.2. Chương trình đầy đủ

~~~java
import java.util.Map;
import java.util.Objects;
import org.springframework.boot.actuate.cache.CachesEndpoint;
import org.springframework.boot.actuate.cache.CachesEndpointWebExtension;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;

public class CachesScopeDemo {
    public static void main(String[] args) {
        CacheManager inventory =
                new ConcurrentMapCacheManager("products", "categories");
        CacheManager partner =
                new ConcurrentMapCacheManager("products");
        Cache products = Objects.requireNonNull(inventory.getCache("products"));
        Cache categories = Objects.requireNonNull(inventory.getCache("categories"));
        Cache partnerProducts = Objects.requireNonNull(partner.getCache("products"));

        products.put("p1", "inventory-1");
        products.put("p2", "inventory-2");
        categories.put("c1", "hardware");
        partnerProducts.put("p1", "partner-1");

        CachesEndpoint endpoint = new CachesEndpoint(Map.of(
                "inventoryCacheManager", inventory,
                "partnerCacheManager", partner));
        CachesEndpointWebExtension web = new CachesEndpointWebExtension(endpoint);

        System.out.println("GET ambiguous = " + web.cache("products", null).getStatus());
        System.out.println("DELETE ambiguous = " + web.clearCache("products", null).getStatus());
        System.out.println("after ambiguous p1 = " + products.get("p1", String.class));

        System.out.println("DELETE selected = "
                + web.clearCache("products", "inventoryCacheManager").getStatus());
        System.out.println("inventory p1 = " + products.get("p1", String.class));
        System.out.println("inventory p2 = " + products.get("p2", String.class));
        System.out.println("partner p1 = " + partnerProducts.get("p1", String.class));
        System.out.println("category c1 = " + categories.get("c1", String.class));
        System.out.println("GET cleared cache = "
                + web.cache("products", "inventoryCacheManager").getStatus());
        System.out.println("DELETE again = "
                + web.clearCache("products", "inventoryCacheManager").getStatus());
        System.out.println("DELETE missing = "
                + web.clearCache("missing", "inventoryCacheManager").getStatus());

        endpoint.clearCaches();
        System.out.println("after all partner p1 = "
                + partnerProducts.get("p1", String.class));
        System.out.println("after all category c1 = "
                + categories.get("c1", String.class));
        System.out.println("GET after all = "
                + web.cache("products", "partnerCacheManager").getStatus());
    }
}
~~~

`Map.of(...)` truyền tên bộ quản lý vào endpoint theo cách tường minh. Trong ứng dụng Spring Boot thật, cơ chế tự cấu hình cung cấp các `CacheManager` bean cho endpoint.

### 6.3. Biên dịch và chạy

Yêu cầu JDK 17+ và Maven; lần đầu tải dependency cần kết nối kho Maven.

Windows PowerShell:

~~~powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$cacheClasspath = (Get-Content -LiteralPath .\classpath.txt -Raw).Trim()
javac --release 17 -cp "$cacheClasspath" CachesScopeDemo.java
java -cp ".;$cacheClasspath" CachesScopeDemo
~~~

Linux/macOS:

~~~shell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
cache_classpath="$(cat classpath.txt)"
javac --release 17 -cp "$cache_classpath" CachesScopeDemo.java
java -cp ".:$cache_classpath" CachesScopeDemo
~~~

Stdout của chương trình:

~~~text
GET ambiguous = 400
DELETE ambiguous = 400
after ambiguous p1 = inventory-1
DELETE selected = 204
inventory p1 = null
inventory p2 = null
partner p1 = partner-1
category c1 = hardware
GET cleared cache = 200
DELETE again = 204
DELETE missing = 404
after all partner p1 = null
after all category c1 = null
GET after all = 200
~~~

Diễn giải theo các mốc của thí nghiệm:

1. Thiếu bộ quản lý khi tên bị trùng tạo kết quả `400`; `inventory-1` còn nguyên, nên phép xóa mơ hồ không âm thầm chọn một cache.
2. Chỉ định `inventoryCacheManager` làm mất cả `p1` và `p2` của cache đã chọn. Dữ liệu đối tác và danh mục vẫn còn.
3. GET cache đã làm rỗng trả `200`, và DELETE lần nữa trả `204`: “cache tồn tại” khác với “cache còn phần tử”.
4. Cache `missing` trả `404`. Khi gọi `clearCaches()`, dữ liệu của đối tác và danh mục cũng mất; metadata của cache đối tác vẫn đọc được.

Ví dụ dùng dữ liệu trong bộ nhớ, không có luồng ghi đồng thời. Kết quả `null` thể hiện không còn giá trị String cho khóa đó trong các cache của lab.

## 7. Giới hạn cần hiểu trước khi suy luận về hệ thống thật

### 7.1. Phạm vi phát hiện do các CacheManager quyết định

Endpoint làm việc với lớp trừu tượng `CacheManager` và `Cache` của Spring. Một `Map` tự tạo, cache của thư viện riêng không tích hợp qua các bộ quản lý này, HTTP cache của trình duyệt hay CDN không tự trở thành đối tượng được điều khiển bởi `caches`.

Danh sách mà bộ quản lý trả về ở thời điểm quan sát mới là căn cứ thao tác. Với cache tạo lười, đừng kết luận một tên chưa xuất hiện có nghĩa toàn bộ cơ chế cache của ứng dụng bị tắt.

### 7.2. Phạm vi dữ liệu còn phụ thuộc nơi lưu

Thí nghiệm dùng `ConcurrentMapCacheManager`, nên dữ liệu nằm trong tiến trình Java hiện tại. Nếu có hai bản sao ứng dụng dùng bộ nhớ riêng, gửi DELETE tới bản sao A không tự xóa bộ nhớ của bản sao B.

Nếu các bản sao dùng chung kho cache từ xa, tác động có thể được các bản sao khác quan sát qua vùng dữ liệu dùng chung. Cần xác minh bộ quản lý, tiền tố tên, kho dữ liệu và cách triển khai thực tế. Không được suy ra “xóa toàn cụm” hoặc “chỉ xóa một máy” từ URL endpoint đơn thuần.

### 7.3. Xóa cache không phải một giao dịch cập nhật dữ liệu nghiệp vụ

Với lab, dữ liệu chỉ nằm trong cache. Trong ứng dụng dùng cơ sở dữ liệu làm nguồn chính, thao tác cache không tự sửa bản ghi nguồn; lần đọc tiếp theo có thể nạp lại giá trị từ nguồn đó.

Vì vậy, nếu nguồn dữ liệu vẫn sai, xóa cache không chữa được nguyên nhân. Nếu cần xóa một khóa sau một cập nhật nghiệp vụ, hãy đặt quy tắc vô hiệu hóa cache ở đúng luồng nghiệp vụ thay vì phụ thuộc vào người vận hành xóa toàn vùng.

### 7.4. Thành công không cam kết cache giữ trạng thái trống mãi

Mã triển khai Boot 3.3 gọi `Cache.clear()` cho cache được chọn. Hợp đồng của `clear()` cho phép nhà cung cấp hoặc lớp bọc trì hoãn việc xóa; không nên tự nâng ý nghĩa của mã thành công thành một hàng rào đồng bộ cho mọi nhà cung cấp. Xem [hợp đồng Cache.clear() của Spring Framework](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/cache/Cache.html#clear()).

Ngoài ra, yêu cầu ứng dụng khác có thể nạp lại phần tử ngay sau lúc xóa. Đối với thao tác gốc, cũng không có hợp đồng một giao dịch nguyên tử bao trùm mọi cache và mọi bộ quản lý. Nếu một nhà cung cấp gặp lỗi giữa chừng, phải kiểm tra lại từng phạm vi thay vì giả định tất cả đã được hoàn tác.

## 8. Phân biệt lỗi cấu hình, bảo mật và lỗi chọn cache

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| GET gốc trả `404` | Actuator có mặt chưa; endpoint có được bật/công bố không; cổng và base path có đúng không |
| GET gốc không có cache mong đợi | Bean CacheManager nào đang được endpoint nhìn thấy; tên cache đã được bộ quản lý biết đến chưa |
| GET hoặc DELETE theo tên trả `400` | Kiểm tra trùng tên giữa các bộ quản lý; thêm đúng `cacheManager` |
| Yêu cầu theo tên trả `404` | Kiểm tra cả tên cache lẫn tên bộ quản lý, không chỉ một trong hai |
| GET được nhưng DELETE trả `403` | Kiểm tra quyền thao tác và CSRF trước khi kết luận nhà cung cấp cache không xóa được |
| DELETE thành công nhưng GET vẫn thấy tên | GET đang trả metadata; kiểm tra phần tử qua thí nghiệm hoặc hành vi ứng dụng |
| Xóa xong dữ liệu nhanh chóng xuất hiện lại | Kiểm tra yêu cầu nạp lại, tác vụ nền, nhiều bản sao và phạm vi kho lưu thực tế |

Nếu Spring Security có mặt, việc công bố endpoint không tự cấp quyền truy cập. CSRF mặc định có thể chặn DELETE, kể cả khi đã xác thực. Cấu hình cho người đọc metadata và người có quyền xóa cần phản ánh trách nhiệm vận hành; không vô hiệu hóa CSRF toàn ứng dụng chỉ để làm một lệnh DELETE chạy được. Nguồn: [bảo mật và CSRF của Actuator trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

## 9. Chọn phạm vi thao tác trong một tình huống cụ thể

Giả sử giá sản phẩm trong nguồn dữ liệu đã được sửa, nhưng chỉ dữ liệu cache của kho hàng bị cũ. Cache đối tác và danh mục vẫn đúng.

Quy trình có thể kiểm chứng:

1. GET danh sách để xác nhận cặp `inventoryCacheManager/products`.
2. Kiểm tra liệu cần xóa một khóa hay thực sự cần làm rỗng toàn bộ cache sản phẩm.
3. Nếu cần làm rỗng toàn bộ cache sản phẩm kho hàng, gọi DELETE theo tên kèm bộ quản lý.
4. Quan sát lần đọc nghiệp vụ tiếp theo để xác nhận giá được nạp lại từ nguồn đúng.
5. Kiểm tra các phạm vi còn lại khi cần, đặc biệt nếu có nhiều bản sao ứng dụng hoặc cache từ xa.

Chọn DELETE gốc trong tình huống này sẽ làm mất cả dữ liệu danh mục và đối tác dù chúng vẫn đúng. Hậu quả có thể là nhiều yêu cầu cùng phải đọc lại cơ sở dữ liệu, làm tăng độ trễ và tải nguồn. Chỉ mở rộng phạm vi khi có lý do cụ thể.

**Bài tập tự kiểm tra:**

- Chạy chương trình và giải thích vì sao DELETE `products` thiếu bộ quản lý trả `400` dù đã có đúng tên cache.
- Thay tên bộ quản lý ở lệnh xóa đã chọn bằng tên không tồn tại. Dự đoán mã trả về và cache nào giữ dữ liệu.
- Chèn lại một phần tử vào `products` sau lần DELETE thành công. Giải thích vì sao điều đó không mâu thuẫn với kết quả `204`.
- Với hai tiến trình dùng `ConcurrentMapCacheManager` độc lập, xác định phải quan sát tiến trình nào để kiểm tra tác động của một lệnh xóa.

Khi trả lời, luôn chỉ rõ **bộ quản lý, cache và nơi lưu dữ liệu**. Ba yếu tố đó quyết định phạm vi thực tế của thao tác.
