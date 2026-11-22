# Phạm vi ổn định qua restart context và giới hạn khi restart tiến trình

Spring Boot có `RandomValuePropertySource` để tạo giá trị ngẫu nhiên trong `Environment`. Spring Cloud Context bổ sung `CachedRandomPropertySource`, cho phép giữ lại kết quả ngẫu nhiên theo một khóa cache. Hai cơ chế giải quyết hai nhu cầu khác nhau: tạo giá trị ngẫu nhiên khi cần, hoặc dùng lại một giá trị đã sinh trong suốt vòng đời của cùng tiến trình Java.

Điểm quan trọng là **ổn định qua restart ApplicationContext không đồng nghĩa với lưu bền qua restart JVM**. `CachedRandomPropertySource` giữ kết quả trong cache của tiến trình. Khi JVM/container kết thúc, cache trong bộ nhớ mất đi; lần khởi động sau có thể sinh giá trị khác. Nếu cần một giá trị tồn tại qua nhiều lần triển khai hoặc dùng chung giữa nhiều replica, phải lưu nó ở một nguồn dữ liệu bền vững.

Bài học thuộc chương **Giá trị ngẫu nhiên** của module **SPRING_CLOUD_CORE**. Nội dung giải thích `random.*` và `cachedrandom.*`, vòng đời của cache, cách chọn khóa, kiểm thử context restart, giới hạn ở process restart và phương án lưu trữ khi cần tính bền vững thực sự.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt `RandomValuePropertySource` của Spring Boot với `CachedRandomPropertySource` của Spring Cloud Context.
- Sử dụng các kiểu giá trị `value`, `int`, `long`, `uuid` và số ngẫu nhiên trong một khoảng.
- Viết property theo cú pháp `cachedrandom.[yourkey].[type]`.
- Giải thích vì sao cùng cache key trả lại cùng giá trị khi ApplicationContext được tạo lại trong cùng JVM.
- Phân biệt restart context, refresh context, restart JVM và tạo lại container/pod.
- Hiểu vì sao `cachedrandom` không cung cấp persistence qua process restart hoặc chia sẻ giá trị giữa nhiều replica.
- Thiết kế kiểm thử cho hai vòng đời khác nhau.
- Chọn database, secret manager hoặc nguồn cấu hình bền vững khi ứng dụng cần giữ giá trị qua nhiều lần triển khai.

## 2. RandomValuePropertySource của Spring Boot

Spring Boot thêm một `RandomValuePropertySource` vào `Environment`. Có thể tham chiếu các giá trị bằng placeholder:

```yaml
app:
  secret: "${random.value}"
  number: "${random.int}"
  big-number: "${random.long}"
  uuid: "${random.uuid}"
  number-less-than-ten: "${random.int(10)}"
  number-in-range: "${random.int[1024,65536]}"
```

Các kiểu thường dùng:

| Placeholder | Kết quả |
| --- | --- |
| `${random.value}` | Giá trị ngẫu nhiên dạng chuỗi/byte theo implementation của Spring Boot |
| `${random.int}` | Số nguyên ngẫu nhiên |
| `${random.long}` | Số nguyên dài ngẫu nhiên |
| `${random.uuid}` | UUID ngẫu nhiên |
| `${random.int(10)}` | Số nguyên trong khoảng từ 0 đến nhỏ hơn 10 |
| `${random.int[1024,65536]}` | Số nguyên từ 1024 đến nhỏ hơn 65536 |

Cú pháp range của `random.int` và `random.long` có dạng `OPEN value (,max) CLOSE`. Ký tự mở và đóng có thể là `(`, `)`, `[` hoặc `]`; nếu chỉ có một giới hạn, Spring Boot dùng 0 làm cận dưới và giới hạn đã cho làm cận trên. Nếu có hai giới hạn, cận dưới được tính vào khoảng còn cận trên bị loại trừ.

Ví dụ trong file `application.properties`:

```properties
app.port=${random.int[20000,30000]}
app.retry-limit=${random.int(5)}
app.instance-id=${random.uuid}
```

`RandomValuePropertySource` sinh giá trị khi được hỏi. Nó không phải cache theo tên property. Vì vậy, không nên dùng `random.*` với kỳ vọng một lần tra cứu sau này luôn nhận lại đúng giá trị đã sinh trước đó. Khi cần giữ cùng một giá trị theo khóa trong cùng tiến trình, dùng cơ chế cached random của Spring Cloud Context.

## 3. CachedRandomPropertySource của Spring Cloud Context

Spring Cloud Context bổ sung một `PropertySource` tên `CachedRandomPropertySource`. Ngoài hành vi cache, nó sử dụng cùng các kiểu giá trị mà Spring Boot hỗ trợ.

Để sử dụng property source này, bảo đảm `spring-cloud-context` có trên classpath. Nếu dự án quản lý dependency bằng Spring Cloud BOM, không cần tự ghim version riêng:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-context</artifactId>
</dependency>
```

Nhiều Spring Cloud starter đã kéo module này theo dependency bắc cầu. Khi ứng dụng chỉ có Spring Boot mà không có Spring Cloud Context, `random.*` vẫn có thể hoạt động nhưng `cachedrandom.*` không được cung cấp.

Spring Cloud Context đăng ký property source này trong giai đoạn xử lý `Environment` bằng `EnvironmentPostProcessor`. Ứng dụng thông thường chỉ cần dependency phù hợp trên classpath; không cần tự tạo một bean `CachedRandomPropertySource`.

Cú pháp:

```text
cachedrandom.[yourkey].[type]
```

Trong đó:

- `cachedrandom` là prefix để chọn property source có cache.
- `yourkey` là tên mục cache, dùng để nhận diện giá trị cần giữ lại.
- `type` là kiểu giá trị do `RandomValuePropertySource` hỗ trợ.

Ví dụ:

```yaml
app:
  instance-id: "${cachedrandom.catalog-instance.uuid}"
  bootstrap-token: "${cachedrandom.catalog-token.value}"
  local-port: "${cachedrandom.catalog-port.int[20000,30000]}"
```

Lần đầu một cache key được đọc, Spring Cloud tạo giá trị ngẫu nhiên và lưu kết quả trong cache. Những lần đọc tiếp theo với cùng key sẽ nhận lại kết quả đã lưu. Nếu dùng key khác, cache sẽ tạo một mục khác.

`yourkey` là nhãn cache, không phải seed mật mã. Việc đổi tên key không tái tạo giá trị cũ; nó tạo một mục cache mới và có thể sinh một giá trị mới. Hai ứng dụng có cùng tên key nhưng chạy trong hai JVM riêng cũng không tự chia sẻ kết quả.

### 3.1. Dùng cùng key khi cần cùng một giá trị

Giả sử nhiều property cần tham chiếu cùng một mã nhận diện:

```yaml
app:
  node-id: "${cachedrandom.catalog-node.uuid}"
  node-id-for-metrics: "${cachedrandom.catalog-node.uuid}"
  node-id-for-log-context: "${cachedrandom.catalog-node.uuid}"
```

Cả ba placeholder dùng chung cache key `catalog-node` và type `uuid`, nên nhận cùng một giá trị trong phạm vi cache hiện tại.

Nếu dùng các key khác nhau:

```yaml
app:
  node-id: "${cachedrandom.catalog-node.uuid}"
  worker-id: "${cachedrandom.catalog-worker.uuid}"
```

hai giá trị được cache độc lập. Hãy đặt tên key có ý nghĩa và ổn định; không thay tên key tùy tiện khi muốn giữ nguyên định danh trong suốt vòng đời tiến trình.

## 4. Vì sao cached random ổn định khi ApplicationContext restart?

`CachedRandomPropertySource` cache giá trị theo key trong phạm vi tiến trình. Khi Spring tạo lại `ApplicationContext` trong cùng JVM/classloader, cache đó vẫn tồn tại. Context mới có thể tra cứu lại cùng cache key và nhận lại giá trị đã sinh trước đó.

Ví dụ một ứng dụng tạo context hai lần trong cùng tiến trình:

```java
String firstValue = firstContext.getEnvironment()
    .getProperty("app.instance-id");

firstContext.close();

try (ConfigurableApplicationContext secondContext =
         new SpringApplicationBuilder(Application.class).run()) {

    String secondValue = secondContext.getEnvironment()
        .getProperty("app.instance-id");

    // Same cache key in the same JVM keeps the cached value.
    assertEquals(firstValue, secondValue);
}
```

Ví dụ trên mô tả vòng đời context, không phải khởi động lại tiến trình. Cache key phải giữ nguyên giữa hai lần tạo context. Nếu ứng dụng đổi cấu hình sang một key khác, kết quả sẽ thuộc một mục cache mới.

### 4.1. Context refresh và context restart

Ba thao tác cần phân biệt:

- **Refresh Environment:** cập nhật property sources và rebind cấu hình trong context đang hoạt động.
- **Restart ApplicationContext:** đóng context hiện tại và tạo context mới trong cùng JVM.
- **Restart process:** kết thúc JVM và khởi động một JVM mới.

Với cùng cache key, `CachedRandomPropertySource` được thiết kế để trả lại giá trị đã cache khi context được khởi tạo lại trong cùng tiến trình. Cơ chế này không biến random value thành dữ liệu được ghi xuống đĩa hoặc gửi sang một process khác.

## 5. Ranh giới của cache khi JVM restart

Cache của `CachedRandomPropertySource` nằm trong bộ nhớ của tiến trình. Nó không phải database, file store, distributed cache hoặc secret manager.

Khi JVM dừng:

1. Các object và static cache trong classloader của JVM bị giải phóng.
2. Tiến trình mới khởi động với bộ nhớ mới.
3. `CachedRandomPropertySource` bắt đầu với cache chưa có mục cũ.
4. Lần đọc đầu tiên của cache key sẽ sinh một giá trị mới.

Do đó, các trường hợp sau không được bảo đảm giữ lại cùng giá trị:

- `java -jar` chạy lại sau khi process trước kết thúc.
- Container bị restart hoặc được tạo lại.
- Pod Kubernetes bị thay thế/reschedule và JVM khởi động mới.
- Deployment rolling update tạo replica mới.
- Máy chủ hoặc node bị reboot.

Sự ổn định qua context restart chỉ có ý nghĩa trong cùng phạm vi JVM/classloader còn giữ cache. Không dùng nó như một cơ chế lưu định danh lâu dài.

## 6. Phân biệt theo vòng đời

| Sự kiện | `random.*` | `cachedrandom.*` |
| --- | --- | --- |
| Đọc property lần đầu | Sinh giá trị ngẫu nhiên | Sinh và lưu theo cache key |
| Đọc lại cùng property source | Có thể sinh giá trị mới khi được hỏi lại | Trả giá trị đã cache theo key |
| Tạo lại ApplicationContext trong cùng JVM | Không bảo đảm giữ giá trị | Giữ giá trị theo cache key |
| Refresh cấu hình trong cùng tiến trình | Không có cache theo key | Cache key đã có tiếp tục trả giá trị đã lưu |
| Restart JVM/process | Sinh giá trị trong tiến trình mới | Cache mới, có thể sinh giá trị khác |
| Tạo replica ở JVM khác | Giá trị độc lập | Cache độc lập, giá trị có thể khác |
| Cần giá trị bền qua deployment | Không phù hợp | Không phù hợp nếu không có lưu trữ bên ngoài |

Bảng này mô tả vòng đời của property source. Giá trị đã được bind vào một bean hoặc lưu vào một object có thể tiếp tục tồn tại theo vòng đời riêng của bean đó; điều này không có nghĩa property source đã lưu giá trị bền vững.

## 7. Cache key không phải cơ chế đồng bộ nhiều instance

Giả sử ba replica cùng khai báo:

```yaml
app:
  cluster-token: "${cachedrandom.shared-token.uuid}"
```

Mỗi replica chạy trong JVM riêng. Mỗi JVM có cache riêng, nên cả ba có thể tạo ba UUID khác nhau. Chuỗi `shared-token` chỉ là tên cache key cục bộ; nó không phải một kênh chia sẻ giữa các replica.

Điều này cũng đúng khi:

- Các replica dùng chung Config Server.
- Các replica dùng cùng một file `application.yml`.
- Các replica có cùng `spring.application.name`.
- Các replica được triển khai cùng một Kubernetes Deployment.

Nếu cần mọi replica nhận cùng một giá trị, hãy tạo giá trị một lần rồi lưu ở nguồn chung có tính bền vững, sau đó để các replica đọc giá trị đó.

## 8. Chọn random hay cached random theo mục đích

| Nhu cầu | Cơ chế nên dùng | Lý do |
| --- | --- | --- |
| Tạo số thử nghiệm khi khởi động | `random.int` | Giá trị ngẫu nhiên mới phù hợp test |
| Tạo UUID cục bộ cho một tiến trình | `cachedrandom.node-id.uuid` | Giữ cùng UUID khi context được dựng lại trong JVM |
| Tạo giá trị tạm cho một lần chạy | `random.uuid` | Không cần giữ qua context restart |
| Giữ mã nhận diện qua context restart | `cachedrandom.<key>.uuid` | Cache theo key trong tiến trình |
| Giữ ID qua JVM restart | Database hoặc persistent store | Cache trong JVM không đủ |
| Chia sẻ token giữa nhiều replica | Secret manager hoặc config store dùng chung | Các JVM riêng không chia sẻ cache |
| Tạo credential dài hạn | Secret manager/credential service | Cần vòng đời, phân phối, rotation và audit |

Không dùng `cachedrandom` để tạo password database hoặc API credential dài hạn nếu hệ thống phụ thuộc cần dùng lại credential sau khi process restart. Khi tiến trình mới sinh giá trị mới, dịch vụ đích vẫn có thể đang lưu credential cũ và xác thực sẽ thất bại.

## 9. Lưu giá trị bền vững qua process restart

Khi yêu cầu nghiệp vụ đòi hỏi giá trị không đổi sau khi JVM khởi động lại, hãy dùng một nguồn lưu trữ có vòng đời phù hợp.

Các lựa chọn thường gặp:

- **Database:** lưu một ID hoặc token theo application/environment; dùng transaction và unique constraint để tránh hai replica cùng tạo hai giá trị đầu tiên.
- **Secret manager:** lưu credential hoặc key cần được phân phối an toàn, có version và rotation.
- **Persistent volume:** lưu một file hoặc dữ liệu cục bộ nếu định danh gắn với một node và volume có vòng đời ổn định.
- **Config Server hoặc nguồn cấu hình tập trung:** lưu giá trị đã được tạo và quản lý bằng revision.
- **Kubernetes Secret/ConfigMap:** dùng khi giá trị cần được phân phối qua Kubernetes; Secret phù hợp hơn với dữ liệu nhạy cảm và vẫn cần cấu hình RBAC/encryption-at-rest thích hợp.

Một mẫu khởi tạo bền vững là:

1. Kiểm tra nguồn lưu trữ đã có giá trị cho application/environment chưa.
2. Nếu đã có, đọc và sử dụng giá trị đó.
3. Nếu chưa có, tạo giá trị ngẫu nhiên bằng API phù hợp.
4. Lưu giá trị theo transaction hoặc thao tác create-if-absent.
5. Đọc lại giá trị đã được lưu để mọi replica cùng sử dụng.
6. Không ghi plaintext secret vào log.

`cachedrandom` có thể hữu ích để giữ một giá trị tạm trong giai đoạn khởi tạo context, nhưng không thay thế bước lưu bền vững.

## 10. Ví dụ cấu hình hoàn chỉnh

Giả sử ứng dụng cần hai loại giá trị:

- Một `instance-id` ổn định khi context được tạo lại trong cùng JVM.
- Một `startup-marker` mới cho mỗi lần process khởi động.

Cấu hình:

```yaml
app:
  identity:
    instance-id: "${cachedrandom.catalog-instance.uuid}"
    startup-marker: "${random.uuid}"
```

Bean đọc các giá trị:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ApplicationIdentity {

    private final String instanceId;
    private final String startupMarker;

    public ApplicationIdentity(
            @Value("${app.identity.instance-id}") String instanceId,
            @Value("${app.identity.startup-marker}") String startupMarker) {
        this.instanceId = instanceId;
        this.startupMarker = startupMarker;
    }

    public String getInstanceId() {
        return instanceId;
    }

    public String getStartupMarker() {
        return startupMarker;
    }
}
```

Trong cùng JVM, khi context được dựng lại và cùng cache key vẫn được dùng, `instance-id` được lấy lại từ cache. `startup-marker` được tạo từ `random.uuid` khi cấu hình được resolve trong lần khởi động context mới.

Khi JVM mới khởi động, cả hai giá trị có thể khác so với process trước. Nếu `instance-id` phải tồn tại qua process restart, thay `cachedrandom` bằng một giá trị được đọc từ persistent store.

## 11. Kiểm thử vòng đời cache

Một bộ kiểm thử nên phân biệt rõ ba tình huống:

### 11.1. Cùng cache key trong cùng JVM

- Khởi tạo context đầu tiên.
- Đọc property `${cachedrandom.test-instance.uuid}`.
- Đóng context.
- Tạo context thứ hai trong cùng JVM/classloader.
- Đọc lại cùng property.
- Xác nhận hai giá trị bằng nhau.

Nếu kiểm thử nhiều lần, cần cô lập cache key giữa các test. `CachedRandomPropertySource` có API `clearCache()` trong các phiên bản cung cấp phương thức này; kiểm tra API của release train dự án trước khi sử dụng. Vì đây là thao tác cache toàn cục của class, không gọi tùy tiện khi các context khác đang hoạt động hoặc khi test chạy song song.

### 11.2. Cùng process nhưng key khác

- Đọc `cachedrandom.test-a.uuid`.
- Đọc `cachedrandom.test-b.uuid`.
- Xác nhận hai key là hai mục cache riêng.
- Đọc lại từng key và xác nhận giá trị tương ứng được giữ nguyên.

Không viết test dựa trên giả định hai UUID khác nhau tuyệt đối trong mọi lần chạy; xác suất trùng rất nhỏ nhưng về mặt toán học không bằng không. Hãy tập trung kiểm tra việc cùng key trả lại cùng giá trị.

### 11.3. Process mới

- Khởi chạy ứng dụng ở process thứ nhất và ghi nhận UUID thử nghiệm.
- Kết thúc hoàn toàn process đó.
- Khởi chạy process thứ hai với cùng cấu hình và cùng cache key.
- Quan sát giá trị được tạo lại trong JVM mới.

Nếu mục tiêu kiểm thử là giá trị phải giữ qua process restart, test cần đọc từ nguồn persistence thực tế và xác nhận giá trị được khôi phục từ nguồn đó. `cachedrandom` không thể chứng minh yêu cầu này.

## 12. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Giá trị đổi sau khi restart container | JVM mới có cache mới | Dùng persistent store nếu cần giữ qua process restart |
| Hai pod có cùng cache key nhưng giá trị khác | Cache nằm riêng trong từng JVM | Đọc một giá trị từ nguồn lưu trữ dùng chung |
| Giá trị đổi sau khi đổi tên key | Cache key mới chưa có giá trị | Giữ nguyên key nếu muốn dùng lại mục cache hiện tại |
| Giá trị không đổi sau khi tạo lại context | Cache vẫn còn trong cùng tiến trình | Đây là hành vi mong đợi của `cachedrandom` |
| Test mong đợi `random.*` ổn định nhưng bị thay đổi | `RandomValuePropertySource` sinh giá trị khi được hỏi | Dùng `cachedrandom` hoặc tự lưu kết quả |
| Giá trị cached không được resolve | Thiếu Spring Cloud Context hoặc cú pháp sai | Kiểm tra dependency, prefix `cachedrandom.` và type |
| Hai property cần cùng giá trị nhưng nhận khác nhau | Dùng hai cache key khác nhau hoặc một property dùng `random.*` | Dùng cùng cache key và type |
| Credential thay đổi sau redeploy làm service lỗi | Dùng cached random làm credential dài hạn | Chuyển credential sang secret manager hoặc database |
| Giá trị cũ vẫn còn trong bean sau refresh | Bean giữ giá trị đã bind hoặc chưa được tạo lại | Kiểm tra cơ chế rebind/lifecycle của bean; không suy ra cache đã được lưu bền |

## 13. Bài tập vận dụng

Một dịch vụ `catalog-service` có cấu hình:

```yaml
catalog:
  instance-id: "${cachedrandom.catalog-instance.uuid}"
  api-key: "${cachedrandom.catalog-api-key.value}"
```

Ứng dụng chạy hai replica. Sau khi rollout, cả hai replica đều có `instance-id` khác lần chạy trước; API key cũng thay đổi khiến dịch vụ phụ thuộc từ chối request.

Hãy thực hiện:

1. Giải thích vì sao `cachedrandom` giữ giá trị qua context restart nhưng không giữ qua process restart.
2. Phân biệt cache của hai replica chạy trong hai JVM.
3. Thay `instance-id` bằng một ID được lưu trong database hoặc nguồn persistent phù hợp với mô hình triển khai.
4. Chuyển `api-key` sang secret manager hoặc nguồn credential dùng chung.
5. Kiểm thử restart context trong cùng JVM và xác nhận cache key trả lại giá trị cũ.
6. Kiểm thử process restart và xác nhận giá trị persistence được khôi phục.
7. Đổi tên cache key và quan sát vì sao cache tạo một mục mới.
8. Thiết kế kiểm thử cho nhiều replica để xác nhận chúng cùng đọc một giá trị từ nguồn dùng chung.

**Tiêu chí hoàn thành:** phân biệt được random value, cached random và persistent value; xác định đúng phạm vi JVM của cache; không dùng cached random như cơ chế lưu secret hoặc đồng bộ giữa replica; có kiểm thử cho context restart và process restart.

## 14. Ghi nhớ

- `RandomValuePropertySource` của Spring Boot tạo `random.*` khi property được hỏi; nó không phải cache ổn định theo key.
- `CachedRandomPropertySource` của Spring Cloud Context cache giá trị theo cú pháp `cachedrandom.[yourkey].[type]`.
- `yourkey` là tên mục cache, không phải seed để tái tạo giá trị trên máy khác.
- Cùng cache key được giữ ổn định khi ApplicationContext được tạo lại trong cùng tiến trình JVM.
- Cache trong bộ nhớ không tồn tại sau khi JVM/process kết thúc.
- Các replica có cache riêng; cùng cache key không làm chúng tự chia sẻ cùng một giá trị.
- `cachedrandom` phù hợp cho giá trị tạm ổn định trong vòng đời process, không phải persistence hoặc secret distribution.
- Muốn giữ giá trị qua process restart, dùng database, secret manager, persistent volume hoặc nguồn cấu hình tập trung.
- Kiểm thử riêng context restart, process restart và nhiều replica để xác nhận đúng vòng đời mà ứng dụng cần.

## 15. Tài liệu tham khảo

- [Spring Cloud Commons — CachedRandomPropertySource](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/cachedrandompropertysource.html): cú pháp `cachedrandom.[yourkey].[type]` và hành vi cache qua ApplicationContext restart.
- [Spring Boot — Externalized Configuration, Configuring Random Values](https://docs.spring.io/spring-boot/reference/features/external-config.html): `random.value`, `random.int`, `random.long`, `random.uuid` và cú pháp range.
- [Spring Boot — RandomValuePropertySource API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/env/RandomValuePropertySource.html): các kiểu giá trị mà random property source hỗ trợ.
- [Spring Cloud Context — CachedRandomPropertySource API](https://javadoc.io/doc/org.springframework.cloud/spring-cloud-context/3.1.9/org/springframework/cloud/util/random/CachedRandomPropertySource.html): API cache và phương thức `clearCache()` trong phiên bản được tài liệu hóa.

