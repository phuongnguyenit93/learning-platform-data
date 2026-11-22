# Đọc log thống kê context cache

Spring TestContext có thể tái sử dụng một `ApplicationContext` giữa nhiều test class có cùng cấu hình. Cơ chế này giảm thời gian khởi động ứng dụng trong suite kiểm thử. Khi suite chạy chậm hoặc liên tục tạo context mới, log thống kê cache giúp xác định Spring đang tái sử dụng context hiệu quả đến đâu.

Thống kê cho biết số context hiện có trong cache, giới hạn cache và số lần tra cứu thành công hoặc không tìm thấy context. Đọc đúng các con số này giúp phân biệt lần tải context đầu tiên với việc cấu hình test vô tình tạo ra nhiều cache key khác nhau, context bị loại bởi `@DirtiesContext` hoặc cache bị tràn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Bật log DEBUG cho Spring TestContext cache.
- Nhận biết dòng thống kê cache trong output của test.
- Giải thích `size`, `maxSize`, `parentContextCount`, `hitCount` và `missCount`.
- Đọc xu hướng hit/miss để tìm nguyên nhân context bị tải lặp lại.
- Liên hệ cache miss với profile, property source, context customizer và context hierarchy.
- Hiểu tác động của `@DirtiesContext`, giới hạn cache và JVM fork.
- Điều chỉnh cache size khi có bằng chứng phù hợp.
- Dùng log để điều tra suite chậm mà không kết luận sai từ một dòng thống kê đơn lẻ.

## 1. Vì sao cần đọc thống kê context cache?

Một context Spring có thể cần component scan, auto-configuration, tạo bean, thiết lập datasource, khởi tạo web server và kết nối các dependency. Những bước này thường tốn thời gian hơn việc chạy một test method thông thường.

Spring TestContext giữ các context đã tải trong một cache. Khi test tiếp theo yêu cầu context có cùng cấu hình, framework có thể lấy lại context đã tồn tại. Khi cấu hình khác hoặc context đã bị loại khỏi cache, framework phải tải context khác.

Ví dụ một suite có 80 test method nhưng chỉ cần hai cấu hình ứng dụng. Nếu các test tương thích dùng lại hai context, chi phí khởi động có thể được chia sẻ. Nếu mỗi test class vô tình tạo một cấu hình khác nhau, Spring có thể phải khởi động ứng dụng nhiều lần.

Thống kê cache giúp trả lời các câu hỏi:

- Có bao nhiêu context đang được giữ?
- Cache có thường xuyên tìm thấy context cần dùng không?
- Có nhiều lần cache miss bất thường không?
- Cache đã đạt giới hạn kích thước chưa?
- Có context hierarchy cần được tính đến không?
- Việc thay đổi profile hoặc property có đang tạo thêm context không?

Thống kê là tín hiệu chẩn đoán. Một cache miss không tự động là lỗi: lần đầu dùng một cấu hình mới cần tải context là hành vi bình thường. Cần đọc chuỗi log và đối chiếu với cấu hình test để hiểu nguyên nhân.

## 2. Bật log DEBUG cho context cache

Logger của Spring TestContext cache nằm trong package:

~~~text
org.springframework.test.context.cache
~~~

Hãy bật mức DEBUG cho logger này để Spring ghi lại các lần truy cập và thống kê cache.

### Với Spring Boot

Có thể thêm vào `src/test/resources/application-test.yml`:

~~~yaml
logging:
  level:
    org.springframework.test.context.cache: DEBUG
~~~

Nếu test đang dùng profile `test`, Spring Boot sẽ nạp cấu hình logging này cùng cấu hình profile tương ứng.

Một lựa chọn khác là đặt logging level trong cấu hình test riêng:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Dùng một nguồn cấu hình phù hợp với cách dự án tổ chức test. Không cần bật DEBUG cho toàn bộ package Spring nếu mục tiêu chỉ là theo dõi cache.

### Với Logback XML

Trong dự án cấu hình logging bằng Logback, có thể khai báo logger:

~~~xml
<configuration>
    <logger
        name="org.springframework.test.context.cache"
        level="DEBUG"
    />
</configuration>
~~~

Đặt logger trong file cấu hình logging mà test thực sự sử dụng, ví dụ `logback-test.xml`.

### Với JVM system property

Có thể bật logger thông qua cấu hình logging tương ứng của framework logging đang dùng. Nếu dự án sử dụng Spring Boot, thuộc tính `logging.level...` thường là cách ngắn gọn nhất.

Sau khi bật DEBUG, chạy một test class hoặc một nhóm test có dùng Spring context. Tìm các dòng chứa cụm:

~~~text
Spring test ApplicationContext cache statistics
~~~

Nếu không thấy log, kiểm tra logging configuration có được nạp trong test hay không, logger có bị cấu hình ở mức cao hơn không, và test có thực sự dùng Spring TestContext hay chỉ là JUnit unit test thuần Java.

## 3. Nhận diện một dòng thống kê cache

Một dòng log minh họa có thể có dạng:

~~~text
Spring test ApplicationContext cache statistics:
[DefaultContextCache@4a7c1d2f size = 3, maxSize = 32,
 parentContextCount = 0, hitCount = 42, missCount = 3]
~~~

Định dạng chính xác và các trường hiển thị có thể khác giữa các phiên bản Spring Framework. Ví dụ trên dùng để giải thích những trường thống kê phổ biến.

| Trường | Ý nghĩa |
|---|---|
| `size` | Số context hiện đang được giữ trong cache |
| `maxSize` | Số context tối đa cache được phép giữ |
| `parentContextCount` | Số context cha được theo dõi trong các context hierarchy |
| `hitCount` | Số lần tra cứu tìm thấy context phù hợp trong cache |
| `missCount` | Số lần tra cứu không tìm thấy context phù hợp trong cache |

Hãy đọc các trường theo đúng vai trò của chúng. `size` mô tả số context đang có tại thời điểm log được ghi; `hitCount` và `missCount` là bộ đếm tra cứu tích lũy trong vòng đời cache của JVM đó.

## 4. Hiểu từng chỉ số

### size: số context hiện đang được cache

Ví dụ:

~~~text
size = 3
~~~

Có ba context hiện đang được giữ trong cache. Điều này không có nghĩa suite chỉ có ba test class hoặc ba test method. Nhiều test class có thể dùng chung một context nếu cấu hình tương thích.

`size` có thể tăng khi Spring tải thêm context mới. Nó có thể giảm khi context bị loại khỏi cache do `@DirtiesContext` hoặc chính sách eviction khi cache đạt giới hạn.

### maxSize: giới hạn số context

Ví dụ:

~~~text
maxSize = 32
~~~

Cache mặc định của Spring TestContext có giới hạn kích thước 32 context trong các cấu hình Spring Framework phổ biến. Có thể thay đổi giới hạn bằng system property `spring.test.context.cache.maxSize`.

Nếu suite có nhiều context key khác nhau, cache có thể đạt giới hạn và phải loại bỏ context cũ để dành chỗ cho context mới. Khi context đã bị loại, test cần lại cấu hình đó có thể phải tải context một lần nữa.

Đừng tăng `maxSize` chỉ vì thấy `size` lớn. Trước hết hãy xác định số context khác nhau có thực sự cần thiết hay đang phát sinh do profile, property hoặc customizer không thống nhất.

### parentContextCount: context cha trong hierarchy

Spring hỗ trợ context hierarchy, trong đó một context con có thể kế thừa bean hoặc cấu hình từ context cha. Khi test dùng `@ContextHierarchy`, cache phải quản lý quan hệ cha-con.

Ví dụ:

~~~java
@ContextHierarchy({
    @ContextConfiguration(classes = RootTestConfiguration.class),
    @ContextConfiguration(classes = WebTestConfiguration.class)
})
class WebLayerIntegrationTest {
}
~~~

Trong tình huống này, `parentContextCount` giúp phản ánh context cha được theo dõi trong cache hierarchy. Với suite không dùng context hierarchy, giá trị này thường là 0.

Đừng hiểu `parentContextCount` là tổng số bean hoặc số test class. Nó liên quan tới cấu trúc context cha-con.

### hitCount: số lần tìm thấy context

Ví dụ:

~~~text
hitCount = 42
~~~

Cache đã phục vụ thành công 42 lần tra cứu context. Khi test yêu cầu một context có cache key đã tồn tại và context vẫn còn trong cache, đó là cache hit.

Hit thường cho thấy nhiều test đang tái sử dụng cùng cấu hình. Số hit tăng là dấu hiệu tốt khi suite có nhiều test class cần chung context.

### missCount: số lần không tìm thấy context

Ví dụ:

~~~text
missCount = 3
~~~

Có ba lần tra cứu không tìm thấy context phù hợp trong cache. Spring có thể cần tải context mới cho các cache key đó.

Miss thường xuất hiện khi:

- Một cấu hình context được dùng lần đầu.
- Test class có active profile khác.
- Property source hoặc dynamic property khác.
- Context customizer khác, ví dụ cấu hình mock bean khác.
- Test đánh dấu context dirty và context bị loại khỏi cache.
- Context cũ đã bị eviction vì cache đạt giới hạn.
- Test chạy trong JVM khác và JVM đó chưa có context trong cache.

Một miss đơn lẻ là bình thường. Điều cần tìm là các miss lặp lại cho những test tưởng như phải dùng chung cấu hình.

## 5. Đọc hit và miss qua một ví dụ

Giả sử suite chạy ba nhóm test:

- Nhóm A dùng profile `test` và cấu hình database kiểm thử.
- Nhóm B có cùng cấu hình như nhóm A.
- Nhóm C dùng profile `postgres` để kiểm tra tích hợp với PostgreSQL.

Diễn biến đơn giản:

~~~mermaid
flowchart TD
    A["Nhóm A yêu cầu context test"] --> B["Cache miss"]
    B --> C["Spring tải context test"]
    C --> D["Nhóm B yêu cầu cùng cache key"]
    D --> E["Cache hit"]
    E --> F["Nhóm C yêu cầu context postgres"]
    F --> G["Cache miss"]
    G --> H["Spring tải context postgres"]
    H --> I["Test tiếp theo dùng lại context postgres"]
    I --> J["Cache hit"]
~~~

Một chuỗi thống kê minh họa:

| Thời điểm | size | hitCount | missCount | Diễn giải |
|---|---:|---:|---:|---|
| Sau khi nhóm A tải context | 1 | 0 | 1 | Cấu hình đầu tiên chưa có trong cache |
| Nhóm B dùng context của A | 1 | 1 | 1 | Tái sử dụng context |
| Nhóm C dùng profile khác | 2 | 1 | 2 | Cần context thứ hai |
| Test tiếp theo dùng profile postgres | 2 | 2 | 2 | Tái sử dụng context thứ hai |

Bảng này mô tả luồng đơn giản để giải thích chỉ số. Trong suite thực tế, Spring có thể tra cứu cache ở nhiều giai đoạn và log nhiều lần trong quá trình chuẩn bị test. Vì vậy, không nên ánh xạ một dòng thống kê với đúng một test method.

## 6. Đánh giá xu hướng hit/miss

Một cách nhìn nhanh là so sánh số hit với tổng số lần tra cứu:

\[
\text{Hit ratio} =
\frac{\text{hitCount}}
{\text{hitCount} + \text{missCount}}
\times 100\%
\]

Ví dụ với 42 hit và 3 miss:

\[
\frac{42}{42 + 3} \times 100\%
\approx 93.3\%
\]

Tỷ lệ này cho biết phần lớn lần tra cứu đã tìm thấy context. Nó là chỉ số tham khảo, không phải tiêu chuẩn pass/fail của Spring.

Một số cách diễn giải:

- **Hit tăng đều, miss chỉ tăng khi xuất hiện cấu hình mới:** cache đang được dùng theo cách dự kiến.
- **Miss tăng gần như mỗi test class:** có thể mỗi class tạo cache key khác nhau hoặc context liên tục bị loại.
- **Size thường xuyên chạm maxSize:** suite có nhiều context đồng thời hoặc giới hạn cache đang thấp so với nhu cầu.
- **Hit thấp sau khi context bị dirty:** kiểm tra vị trí và phạm vi dùng `@DirtiesContext`.
- **Một nhóm test tải context nhiều lần:** so sánh profile, property, configuration class và context customizer của các class đó.

Tỷ lệ hit cao không chứng minh test độc lập hoặc đúng nghiệp vụ. Nó chỉ mô tả hiệu quả tìm kiếm context. Tương tự, tỷ lệ hit thấp có thể là hợp lý nếu suite cố ý kiểm tra nhiều môi trường độc lập.

## 7. Liên hệ cache miss với cấu hình test

Spring TestContext tạo cache key từ metadata cấu hình context. Một số thành phần thường làm cache key khác nhau:

- `@ContextConfiguration` với class hoặc resource khác.
- Context initializer khác nhau.
- Context loader hoặc context hierarchy khác.
- `@ActiveProfiles` khác nhau.
- `@TestPropertySource` với property khác.
- `@DynamicPropertySource` cung cấp giá trị khác.
- Context customizer khác, ví dụ cấu hình bean mock hoặc import bổ sung.
- Web resource base path khác.

Ví dụ hai test class:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceTest {
}
~~~

~~~java
@SpringBootTest
@ActiveProfiles("integration")
class OrderControllerTest {
}
~~~

Hai class có active profile khác nhau nên thông thường cần context riêng. Một cache miss khi class thứ hai bắt đầu là hợp lý.

Nếu cả hai class đều dùng profile `test` nhưng vẫn tạo context riêng, hãy so sánh các metadata khác. Ví dụ, một class có `@TestPropertySource` riêng hoặc khai báo mock bean khác có thể tạo cache key khác.

Đối với Spring Boot, các annotation mock bean có thể tác động đến context customizer. Ở các phiên bản mới, dự án có thể dùng `@MockitoBean`; ở phiên bản cũ hơn có thể gặp `@MockBean`. Khi nhiều test class khai báo tập mock khác nhau, context có thể không được tái sử dụng.

Không nên xóa cấu hình cần thiết chỉ để tăng hit ratio. Mục tiêu là hiểu vì sao context khác nhau và chỉ thống nhất cấu hình khi các test thực sự cần cùng môi trường.

## 8. Nhận biết tác động của @DirtiesContext

`@DirtiesContext` đánh dấu context cần loại khỏi cache. Sau khi context bị loại và đóng, một test khác yêu cầu cùng cấu hình có thể làm Spring tải context mới.

Ví dụ:

~~~java
@SpringBootTest
class ContextMutationTest {

    @Test
    @DirtiesContext
    void changesContextState() {
        // Thay đổi trạng thái bean khiến context không thể tái sử dụng.
    }
}
~~~

Nếu nhiều test dùng `@DirtiesContext` ở phạm vi method, số miss và số lần khởi động context có thể tăng đáng kể.

Hãy xem:

- Annotation đặt ở method hay class.
- `methodMode` hoặc `classMode` có phù hợp không.
- Test có thực sự thay đổi trạng thái context không thể khôi phục không.
- Trạng thái bị thay đổi có thể reset qua API hoặc fixture riêng không.

`@DirtiesContext` không phải công cụ dọn mọi dữ liệu. Nếu vấn đề nằm trong database, file hoặc message broker, hãy dọn đúng tài nguyên đó. Tải lại context chỉ nên được dùng khi context hoặc bean được quản lý đã bị thay đổi theo cách không an toàn để tái sử dụng.

## 9. Khi cache đạt maxSize và eviction xảy ra

Cache có giới hạn kích thước. Khi cần thêm context mà cache đã đạt giới hạn, Spring sử dụng chính sách loại bỏ context ít được sử dụng gần đây để giải phóng chỗ. Context bị loại sẽ được đóng.

Ví dụ:

~~~text
size = 32, maxSize = 32
~~~

Đây là dấu hiệu cache đang ở giới hạn tại thời điểm log. Nó chưa tự chứng minh có eviction, nhưng nếu sau đó xuất hiện nhiều context mới và các context cũ phải được tải lại, cache churn có thể đang xảy ra.

Một chuỗi hành vi có thể là:

1. Suite tải nhiều cấu hình khác nhau.
2. Cache đạt `maxSize`.
3. Spring loại một context cũ.
4. Test sau đó cần lại cấu hình đã bị loại.
5. Spring ghi nhận miss và tải context đó lần nữa.

Trong tình huống này, `missCount` có thể tăng dù các test đã từng dùng context tương ứng trước đó.

Có thể tăng giới hạn cache bằng system property:

~~~text
-Dspring.test.context.cache.maxSize=64
~~~

Ví dụ, thêm JVM system property vào cấu hình chạy test của build tool. Với Gradle, có thể cấu hình cho task test:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty "spring.test.context.cache.maxSize", "64"
}
~~~

Với Maven Surefire, có thể truyền system property qua cấu hình plugin hoặc tham số JVM phù hợp với cấu hình dự án.

Chỉ tăng giới hạn sau khi log cho thấy eviction gây tải context lặp lại và máy chạy có đủ bộ nhớ. Mỗi context có thể giữ nhiều bean, connection pool và tài nguyên. Giữ nhiều context đồng thời làm tăng mức sử dụng heap và tài nguyên bên ngoài.

## 10. Phân biệt cache miss với lỗi tải context

Cache miss có nghĩa là không tìm thấy context phù hợp trong cache. Nó không đồng nghĩa context tải thất bại.

Khi context tải thành công, Spring đưa context vào cache để có thể dùng lại. Khi tải thất bại, log lỗi khởi tạo context và exception gốc sẽ cung cấp thông tin quan trọng hơn dòng thống kê cache.

Trong các phiên bản Spring Framework mới có cơ chế failure threshold để hạn chế việc thử tải lại cùng một context bị lỗi nhiều lần. Khi gặp lỗi này, hãy tìm exception đầu tiên trong log. Các lần bỏ qua tiếp theo có thể chỉ là hệ quả của lần tải thất bại ban đầu.

Không nên sửa cache size để xử lý lỗi bean creation, cấu hình sai, datasource không kết nối được hoặc property thiếu. Hãy đọc stack trace đầu tiên và xử lý nguyên nhân khiến context không khởi tạo được.

## 11. Context cache tồn tại trong phạm vi JVM

Cache của Spring TestContext nằm trong bộ nhớ của tiến trình JVM. Nếu build tool chạy test trong nhiều fork JVM, mỗi tiến trình có cache riêng.

Ví dụ:

~~~text
Test JVM 1:
  tải context test
  tái sử dụng context trong JVM 1

Test JVM 2:
  khởi động riêng
  cần tải context test của JVM 2
~~~

Vì vậy, log của hai JVM có thể cùng bắt đầu với `size = 0`, `hitCount = 0` và `missCount = 0`. Đây là hành vi bình thường vì cache không được chia sẻ giữa các tiến trình.

Nếu build tool chạy nhiều test task hoặc module trong tiến trình riêng, không nên cộng các bộ đếm của từng JVM như thể chúng thuộc một cache duy nhất.

Khi phân tích log, hãy ghi nhận test task, fork và PID nếu output có cung cấp. So sánh thống kê trong cùng một tiến trình để hiểu xu hướng hit/miss chính xác hơn.

## 12. Quy trình điều tra khi test suite khởi động context quá nhiều lần

Khi suite chậm và nghi ngờ context cache không hoạt động hiệu quả, hãy thực hiện theo thứ tự:

1. Bật DEBUG cho `org.springframework.test.context.cache`.
2. Chạy đúng nhóm test đang chậm và lưu log đầy đủ.
3. Tìm các dòng `Spring test ApplicationContext cache statistics`.
4. Ghi lại `size`, `maxSize`, `hitCount` và `missCount` tại các thời điểm quan trọng.
5. Xác định các lần miss đầu tiên tương ứng với cấu hình test nào.
6. So sánh `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, configuration class và context customizer giữa các test class.
7. Tìm `@DirtiesContext` và xác định test có thực sự cần loại context không.
8. Kiểm tra cache có thường xuyên đạt `maxSize` và có dấu hiệu eviction hay không.
9. Xác định test đang chạy trong một JVM hay nhiều fork.
10. Chỉ thay đổi cache size hoặc cấu hình test sau khi đã xác định nguyên nhân.

Khi so sánh hai test class, hãy lập bảng metadata:

| Thuộc tính | Test A | Test B |
|---|---|---|
| Configuration classes | `ApplicationConfig` | `ApplicationConfig` |
| Active profiles | `test` | `test` |
| Test properties | Không có | `feature.enabled=true` |
| Dynamic properties | PostgreSQL container A | PostgreSQL container B |
| Mock bean configuration | Một mock | Hai mock |
| Context hierarchy | Không | Không |

Bảng này giúp tìm khác biệt có thể làm cache key thay đổi. Những giá trị dynamic như cổng container hoặc URL ngẫu nhiên cần được hiểu theo cách Spring tạo context customizer; đừng giả định chỉ vì tên property giống nhau thì cache key chắc chắn giống nhau.

## 13. Những lỗi thường gặp khi đọc log

- **Coi mọi cache miss là lỗi:** context mới cần miss ở lần đầu; chỉ điều tra khi miss lặp lại ngoài dự kiến.
- **Coi `size` là số test:** đây là số context hiện đang cache.
- **Coi `maxSize` là số context đã tải trong toàn suite:** đây là giới hạn số context được giữ đồng thời.
- **Cho rằng `hitCount` bằng số test method dùng lại context:** framework có thể tra cứu cache ở nhiều giai đoạn, nên bộ đếm phản ánh hoạt động cache.
- **So sánh bộ đếm của hai JVM như một cache:** mỗi JVM có cache riêng.
- **Tăng `maxSize` ngay khi thấy miss:** miss có thể do cấu hình khác nhau hoặc `@DirtiesContext`, không phải do cache quá nhỏ.
- **Bỏ qua profile và property:** các metadata này có thể làm cache key khác nhau.
- **Nhầm miss với context load failure:** miss là không tìm thấy context trong cache; lỗi tải context có exception riêng.
- **Bật DEBUG cho toàn bộ Spring:** log có thể quá nhiều và khó tìm thống kê; hãy bật đúng package cache.
- **Kết luận suite nhanh hơn chỉ từ hit ratio:** thời gian khởi động, số bean, database, web server và tài nguyên ngoài cũng ảnh hưởng tổng thời gian chạy.

## 14. Bài tập đọc thống kê

Giả sử cuối một lần chạy test có dòng:

~~~text
size = 4, maxSize = 32, parentContextCount = 0,
hitCount = 76, missCount = 4
~~~

Có thể đọc như sau:

- Có bốn context đang được giữ trong cache.
- Cache chưa chạm giới hạn 32.
- Không có context cha được ghi nhận trong hierarchy.
- Có 76 lần tra cứu tìm thấy context.
- Có bốn lần tra cứu không tìm thấy context.

Tỷ lệ hit tham khảo:

\[
\frac{76}{76 + 4} \times 100\% = 95\%
\]

Một kết quả như vậy cho thấy cache đang tái sử dụng context khá nhiều. Tuy nhiên, nếu một trong bốn miss xảy ra liên tục ở nhóm test quan trọng, vẫn cần tìm nguyên nhân. Tỷ lệ tổng thể có thể che khuất một nhóm test tải context lặp lại.

Một tình huống khác:

~~~text
size = 32, maxSize = 32, hitCount = 30, missCount = 45
~~~

Cache đang ở giới hạn và số miss lớn hơn số hit. Hãy kiểm tra eviction, cấu hình context khác nhau, profile, property source, mock bean và các JVM fork. Chỉ sau khi xác nhận cache churn mới cân nhắc tăng giới hạn.

## Kết luận

Log thống kê context cache cho biết Spring TestContext đang tái sử dụng `ApplicationContext` như thế nào. `hitCount` phản ánh số lần tìm thấy context, `missCount` phản ánh số lần không tìm thấy, `size` cho biết số context đang giữ và `maxSize` đặt giới hạn cache. `parentContextCount` cung cấp thêm thông tin khi dùng context hierarchy.

Bật DEBUG cho `org.springframework.test.context.cache`, đọc các dòng thống kê trong cùng một JVM và đối chiếu cache miss với profile, property, context customizer, `@DirtiesContext` và eviction. Khi hiểu nguồn gốc của các lần tải context, bạn có thể giảm thời gian suite mà vẫn giữ đúng cấu hình kiểm thử.

