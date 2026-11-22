# Context failure threshold là hệ quả của lần nạp thất bại trước

Khi Spring TestContext không thể tạo `ApplicationContext` cho một test, lỗi đầu tiên thường chứa nguyên nhân thật: thiếu bean, cấu hình sai, database không truy cập được, migration thất bại hoặc resource khởi tạo không thành công. Những test khác có cùng cấu hình context có thể tiếp tục yêu cầu đúng context đó. Nếu Spring cứ thử nạp lại sau mỗi lần thất bại, log sẽ lặp lại rất nhiều stack trace giống nhau và suite mất thời gian.

Từ Spring Framework 6.1, TestContext có **context failure threshold** để giới hạn số lần thử nạp một context có cùng cache key. Mặc định threshold là `1`: sau lần nạp thất bại đầu tiên, những lần yêu cầu tiếp theo cho cùng cấu hình sẽ bị bỏ qua ngay và Spring ném `IllegalStateException` thông báo failure threshold đã vượt ngưỡng.

Thông báo threshold là hệ quả của lần nạp trước, không phải nguyên nhân gốc. Khi gặp nó, hãy tìm stack trace của lần load đầu tiên cho cùng context configuration và sửa lỗi đó trước.

## 1. Failure threshold hoạt động như thế nào?

Spring TestContext cache `ApplicationContext` để các test có cấu hình tương đương có thể dùng chung context. Cache nhận diện context bằng một tập hợp cấu hình đã merge, chẳng hạn:

- Resource locations hoặc cấu hình class được nạp.
- Context initializer classes.
- Context customizers.
- Context loader.
- Parent context.
- Active profiles.
- Property source descriptors và inline properties.
- Web resource base path nếu là web context.

Tập hợp này tạo thành cache key (`MergedContextConfiguration`). Với mỗi key, Spring theo dõi số lần tạo context thất bại. Khi một lần load thất bại, failure count của key đó tăng lên.

Với threshold mặc định bằng `1`, diễn tiến có thể hình dung như sau:

```text
Test A yêu cầu context K
        |
        v
Spring bắt đầu load context K
        |
        v
Load thất bại (failure count = 1)
        |
        v
Test B yêu cầu cùng context K
        |
        v
Failure count đã đạt threshold = 1
        |
        v
Spring bỏ qua lần load tiếp theo
và ném IllegalStateException
```

Ví dụ hai test class dùng chung cấu hình:

```java
@SpringBootTest
class CatalogServiceTests {
    // Test dùng Spring application context.
}

@SpringBootTest
class OrderServiceTests {
    // Cấu hình tương đương nên có thể dùng cùng cache key.
}
```

Nếu lần đầu Spring không tạo được context, test class sau có cùng merged configuration có thể nhận lỗi dạng:

```text
java.lang.IllegalStateException:
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for [...]
```

Thông báo cho biết Spring đã ngừng thử lại context có key đó. Nó không cho biết vì sao lần load đầu thất bại. Nguyên nhân gốc nằm trong exception và stack trace xuất hiện ở lần thử đầu tiên.

## 2. Phân biệt lỗi nạp context với lỗi trong test method

Failure threshold chỉ áp dụng cho việc **tải `ApplicationContext`**. Nó không phải bộ đếm tất cả test failure.

| Tình huống | Có làm tăng context failure count không? | Lý do |
|---|---:|---|
| Bean creation thất bại khi refresh context | Có | ApplicationContext không được tạo thành công |
| `@Configuration` hoặc property khiến context không khởi động | Có | Lỗi xảy ra trong quá trình load context |
| Context initializer hoặc context customizer ném exception | Có | Spring không hoàn tất được việc tạo context |
| Database hoặc external resource làm bean khởi tạo thất bại | Có, nếu khiến context load thất bại | Lỗi nằm trong quá trình khởi tạo context |
| Assertion trong test method thất bại sau khi context đã tạo | Không | Context đã load thành công; test method mới là phần thất bại |
| Service ném exception khi test gọi method | Không, nếu context đã load thành công | Đây là lỗi thực thi test, không phải lỗi load context |
| HTTP response trả 500 trong một request sau khi context đã chạy | Không tự động | Request failure không đồng nghĩa context load failure |

Vì vậy, nếu test method thất bại do assertion hoặc nghiệp vụ, thay đổi `spring.test.context.failure.threshold` sẽ không sửa được vấn đề. Hãy phân loại lỗi trước khi điều chỉnh threshold.

## 3. Giá trị mặc định và cách thay đổi threshold

Thuộc tính điều khiển ngưỡng là:

```properties
spring.test.context.failure.threshold=1
```

Spring Framework 6.1 trở lên mặc định dùng giá trị `1`. Có thể đặt giá trị lớn hơn nếu muốn cho phép nhiều lần thử load cùng context key trước khi các lần tiếp theo bị bỏ qua.

Ví dụ đặt threshold bằng `2` cho test task của Gradle (Groovy DSL):

```groovy
tasks.withType(Test).configureEach {
    systemProperty 'spring.test.context.failure.threshold', '2'
}
```

Với Gradle Kotlin DSL:

```kotlin
tasks.withType<Test>().configureEach {
    systemProperty("spring.test.context.failure.threshold", "2")
}
```

Có thể đặt JVM system property trực tiếp khi khởi chạy test JVM, hoặc cấu hình qua cơ chế `SpringProperties` của Spring. Điều quan trọng là property phải có mặt trước khi Spring Test bắt đầu load context.

Đây là thuộc tính của Spring TestContext, được đọc qua cơ chế `SpringProperties`; nó không phải một property ứng dụng thông thường. Đặt nó trong `@SpringBootTest(properties = ...)` hoặc `@TestPropertySource` không phải cách cấu hình phù hợp cho failure threshold, vì các property đó thuộc `Environment` của application context đang được tạo.

Giá trị lớn như `1000000` có thể được dùng để gần như vô hiệu hóa ngưỡng trong lúc chẩn đoán, vì Spring sẽ cho phép nhiều lần thử hơn. Hãy chỉ làm điều này tạm thời và có chủ đích; nó có thể khiến cùng một lỗi cấu hình lặp lại trên nhiều test, tạo log dài và làm suite chậm.

## 4. Threshold được tính theo cache key

Failure count gắn với cấu hình context đã merge, không phải một bộ đếm chung cho tất cả test trong JVM.

Ví dụ:

```java
@SpringBootTest
class CatalogTests {
}

@SpringBootTest
class OrderTests {
}

@SpringBootTest(properties = "feature.experimental=true")
class ExperimentalTests {
}
```

Nếu hai class đầu có cùng các thuộc tính cấu hình sau khi merge, chúng có thể dùng chung context cache key. Class thứ ba có inline property khác nên thường tạo một cache key khác. Thất bại của key thứ nhất không tự động khiến key thứ hai bị skip.

Các khác biệt như active profiles, cấu hình class, property source, initializer hoặc context customizer có thể tạo key khác. Ngược lại, hai test class khác tên vẫn có thể chia sẻ cùng context nếu cấu hình đã merge tương đương.

Không nên cố tình thêm property ngẫu nhiên hoặc initializer khác nhau để né failure threshold. Cách đó chỉ tạo thêm cache key và có thể làm nhiều context giống nhau được nạp lặp lại, che khuất lỗi cấu hình ban đầu.

## 5. Vì sao Spring bỏ qua lần thử tiếp theo?

Khi threshold đã đạt, Spring không gọi lại quá trình load cho cache key đó trong lần yêu cầu hiện tại. Điều này tránh lặp lại một thao tác đã thất bại và giúp báo lỗi nhanh cho những test dùng cùng context.

Hành vi này đặc biệt hữu ích trong suite lớn:

- Một lỗi cấu hình không tạo ra hàng trăm stack trace giống nhau.
- Những test sau không lãng phí thời gian khởi động cùng một context chắc chắn đang bị đánh dấu thất bại theo ngưỡng.
- Log thể hiện rõ rằng một lần load trước đã thất bại và những lần thử tiếp theo bị skip.

Threshold không phải retry policy cho database, container hoặc HTTP service. Nó không tự kiểm tra xem external resource đã sẵn sàng hay chưa, cũng không đợi một dependency phục hồi. Nếu lần load đầu thất bại do service chưa sẵn sàng, cần sửa readiness/wait strategy hoặc lifecycle của resource để service sẵn sàng trước khi context tạo bean phụ thuộc vào nó.

## 6. Tìm nguyên nhân gốc từ lần load đầu tiên

Khi thấy `ApplicationContext failure threshold exceeded`, hãy tìm lần xuất hiện đầu tiên của lỗi load cùng cấu hình. Đọc từ exception gốc lên stack trace để xác định bean hoặc bước khởi tạo thất bại.

Những nguyên nhân thường gặp:

| Dấu hiệu trong lỗi đầu tiên | Khu vực cần kiểm tra |
|---|---|
| `NoSuchBeanDefinitionException` | Component scan, `@Import`, profile hoặc test configuration chưa đăng ký bean |
| `UnsatisfiedDependencyException` | Constructor dependency của bean không thể được resolve; xem nested cause để biết bean nào thiếu |
| `BeanCreationException` | `@Bean` factory method, constructor, init method hoặc cấu hình bean ném exception |
| `Could not resolve placeholder` | Thiếu property, sai tên property hoặc property source chưa được nạp |
| Connection refused / timeout | Database, broker, mock server hoặc external service chưa khởi động hoặc sai host/port |
| Migration hoặc schema validation thất bại | Database rỗng/sai version, migration không tương thích hoặc test dùng nhầm schema |
| Address already in use | Server test bind cổng cố định hoặc resource trước đó chưa được giải phóng |
| Exception từ initializer/customizer | Logic mở rộng TestContext chạy trước refresh có lỗi hoặc phụ thuộc trạng thái không sẵn sàng |
| Lỗi chỉ xuất hiện khi chạy song song | Dữ liệu, cổng, file, singleton bean hoặc external resource bị chia sẻ giữa các test |

Đừng bắt đầu bằng cách tăng threshold. Trước tiên, xác định liệu lỗi đầu tiên có phải lỗi cấu hình xác định hay một dependency tạm thời chưa sẵn sàng.

## 7. Phân tích tình huống test dùng chung context

Giả sử `CatalogTests` và `OrderTests` cùng dùng `@SpringBootTest` với cùng profiles và properties. `CatalogTests` khởi động trước, nhưng bean `InventoryClient` không thể được tạo vì `inventory.base-url` chưa được cấu hình.

```text
CatalogTests
  -> yêu cầu context K
  -> InventoryClient không resolve được inventory.base-url
  -> context K load thất bại
  -> failure count(K) = 1

OrderTests
  -> yêu cầu context K
  -> threshold mặc định = 1 đã đạt
  -> Spring skip lần load tiếp theo
  -> IllegalStateException: failure threshold exceeded
```

Sửa property hoặc cấu hình `InventoryClient` là cách giải quyết. Tăng threshold lên `2` chỉ khiến Spring thử lại một lần; nếu property vẫn thiếu, lần thứ hai cũng thất bại và những lần sau tiếp tục bị skip.

Một tình huống khác là database container khởi động chậm. Nếu context load trước khi container sẵn sàng, lỗi kết nối có thể là nguyên nhân đầu tiên. Hãy bảo đảm container đã start và dynamic property đã trỏ đúng mapped port trước khi Spring tạo datasource. Tăng threshold không thay thế việc quản lý thứ tự khởi động resource.

## 8. Phân biệt failure threshold với context cache max size

Spring TestContext có nhiều thuộc tính liên quan đến cache, nhưng chúng điều khiển những vấn đề khác nhau:

| Thuộc tính | Điều khiển | Không có tác dụng |
|---|---|---|
| `spring.test.context.failure.threshold` | Số lần load thất bại tối đa được chấp nhận cho một cache key trước khi skip lần thử tiếp theo | Không tăng dung lượng cache và không sửa lỗi cấu hình |
| `spring.test.context.cache.maxSize` | Số application context tối đa được giữ trong cache | Không cho phép retry context đã load thất bại |

Tăng `cache.maxSize` không khắc phục lỗi `ApplicationContext failure threshold exceeded`. Tương tự, tăng failure threshold không làm cache giữ được nhiều context hơn.

Nếu suite tạo quá nhiều context khác nhau, hãy xem xét cache statistics, số lượng cấu hình context khác biệt và `spring.test.context.cache.maxSize`. Nếu cùng một cấu hình context load thất bại, hãy tìm lỗi gốc và xem `spring.test.context.failure.threshold`.

## 9. Khi nào nên tăng threshold?

Trong đa số trường hợp, giữ mặc định `1` là phù hợp. Có thể tạm tăng threshold khi cần điều tra một lỗi load có tính tạm thời và muốn quan sát xem lần thử tiếp theo có thành công hay không.

Một số lưu ý:

- Nếu lỗi do thiếu bean hoặc sai property, retry sẽ không giúp ích; sửa cấu hình.
- Nếu lỗi do database hoặc container chưa sẵn sàng, ưu tiên wait strategy và lifecycle rõ ràng.
- Nếu lỗi do port collision, dùng cổng ngẫu nhiên và cleanup server.
- Nếu lỗi chỉ xuất hiện khi chạy đồng thời, cô lập tài nguyên hoặc đồng bộ test thay vì tăng threshold.
- Nếu tăng threshold để chẩn đoán, ghi rõ lý do và trả về mặc định sau khi tìm được nguyên nhân.

Không đặt threshold cực lớn như cấu hình thường trực chỉ để log không còn hiển thị thông báo skip. Điều đó có thể che khuất việc nhiều test đang lặp lại cùng một lỗi khởi tạo context.

## 10. Quy trình chẩn đoán failure threshold

1. Xác nhận phiên bản Spring Framework có hỗ trợ failure threshold (từ 6.1).
2. Tìm thông báo `ApplicationContext failure threshold ... exceeded` trong log.
3. Tìm lần load thất bại đầu tiên của cùng context configuration và đọc root cause.
4. Xác định cache key có được chia sẻ giữa nhiều test hay không bằng cách so sánh cấu hình đã merge.
5. Sửa nguyên nhân: bean, property, profile, initializer, database, port hoặc resource lifecycle.
6. Chạy lại nhóm test liên quan với threshold mặc định để xác nhận context load thành công.
7. Chỉ tăng threshold tạm thời nếu cần chẩn đoán khả năng phục hồi của một lỗi tạm thời; không dùng nó thay cho việc sửa nguyên nhân.

Context failure threshold giúp Spring TestContext dừng những lần thử nạp lặp lại cho một cấu hình đã thất bại. Khi thấy thông báo threshold, hãy xem đó là tín hiệu dẫn tới lần load lỗi ban đầu. Sửa nguyên nhân gốc và giữ cấu hình threshold phù hợp sẽ giúp test suite báo lỗi ngắn gọn, nhanh và dễ chẩn đoán hơn.
