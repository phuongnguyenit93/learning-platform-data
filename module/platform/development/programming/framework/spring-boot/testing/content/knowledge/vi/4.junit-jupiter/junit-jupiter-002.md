# JUnit Jupiter: @BeforeEach, @AfterEach, @BeforeAll và @AfterAll

## 1. Lifecycle callbacks là gì?

Trong JUnit Jupiter (JUnit 5), **lifecycle callbacks** là các phương thức được JUnit tự gọi tại những thời điểm xác định trong vòng đời kiểm thử. Bốn annotation thường gặp là:

- `@BeforeEach`: chuẩn bị trạng thái **trước mỗi lượt thực thi test**.
- `@AfterEach`: dọn dẹp hoặc kiểm tra hậu điều kiện **sau mỗi lượt thực thi test**.
- `@BeforeAll`: chuẩn bị tài nguyên **một lần trước các test của lớp**.
- `@AfterAll`: giải phóng tài nguyên **một lần sau các test của lớp**.

Chúng giúp tách phần **thiết lập điều kiện**, **chạy hành vi cần kiểm thử** và **dọn dẹp**. Nhờ đó, test ngắn hơn, ít phụ thuộc lẫn nhau và dễ tái lập.

Ví dụ: mỗi test cần một giỏ hàng rỗng mới, nhưng mọi test trong lớp dùng chung một cấu hình chỉ đọc. Có thể khởi tạo cấu hình một lần ở `@BeforeAll`, tạo giỏ hàng mới trong `@BeforeEach`, dọn giỏ hàng trong `@AfterEach` và đóng tài nguyên được tạo ở `@BeforeAll` bằng `@AfterAll`.

**Phân biệt:** các annotation này do **JUnit Jupiter** điều phối. Chúng không phải annotation của Spring Boot, dù thường xuất hiện trong dự án Spring Boot sử dụng `spring-boot-starter-test`.

## 2. So sánh bốn annotation

| Annotation | Khi nào JUnit gọi? | Số lần đối với N lượt test | Dùng cho việc gì? | `static` mặc định? |
| --- | --- | --- | --- | --- |
| `@BeforeAll` | Trước khi thực thi các test thuộc lớp/container đó | Thường 1 | Mở tài nguyên chia sẻ, chuẩn bị fixture dùng chung | **Có** đối với lớp dùng lifecycle mặc định `PER_METHOD` |
| `@BeforeEach` | Trước từng lượt test | N | Khởi tạo dữ liệu và trạng thái độc lập cho từng test | **Không** |
| `@AfterEach` | Sau từng lượt test | N | Dọn tài nguyên của riêng test, reset những gì cần thiết | **Không** |
| `@AfterAll` | Sau các test thuộc lớp/container đó | Thường 1 | Đóng tài nguyên chia sẻ đã tạo từ đầu | **Có** đối với lớp dùng lifecycle mặc định `PER_METHOD` |

“N lượt test” là N **invocation**, không nhất thiết là N phương thức. Một `@ParameterizedTest` có ba bộ dữ liệu thường tạo ba invocation và chạy `@BeforeEach`/`@AfterEach` ba lần. `@RepeatedTest` cũng chạy callbacks theo mỗi lượt lặp.

`@BeforeAll` và `@AfterAll` gắn với **lớp hoặc test container tương ứng**; không nên hiểu là “một lần cho toàn bộ dự án” hay “một lần duy nhất cho tất cả lớp trong test suite”.

### Chu trình gọi thông thường

Giả sử một lớp có hai test độc lập A và B, thứ tự A/B trong sơ đồ chỉ là ví dụ:

~~~text
@BeforeAll
  @BeforeEach
    @Test A
  @AfterEach
  @BeforeEach
    @Test B
  @AfterEach
@AfterAll
~~~

Nếu JUnit chạy B trước A, cấu trúc bao quanh mỗi test vẫn như vậy. **Đừng dựa vào thứ tự mặc định của các phương thức test.** JUnit có cơ chế xác định thứ tự riêng, nhưng test đúng phải chạy được độc lập, không cần một test khác chạy trước.

Trong thực tế, extension của JUnit/Spring cũng có callback ở các giai đoạn tương ứng. Sơ đồ trên chỉ minh họa bốn annotation được hỏi, không phải toàn bộ sự kiện nội bộ của test engine.

## 3. @BeforeEach: tạo trạng thái sạch cho từng test

Phương thức có `@BeforeEach` chạy trước **mỗi lượt test**, phù hợp để:

- Tạo đối tượng service hoặc dữ liệu giả cho đúng một test.
- Tạo fixture: giỏ hàng rỗng, tài khoản mẫu, request object hoặc mock mặc định.
- Đưa trạng thái có thể thay đổi về điểm bắt đầu xác định.
- Chuẩn bị điều kiện chung được nhiều test sử dụng.

Ví dụ:

~~~java
private List<String> cart;

@BeforeEach
void setUp() {
    cart = new ArrayList<>();
}
~~~

Đây là **đoạn mã minh họa đặt bên trong một lớp test**, cần import `List`, `ArrayList` và `BeforeEach`. Mỗi lần test chạy, `cart` được gán một danh sách rỗng mới. Dù JUnit mặc định tạo instance lớp test mới cho mỗi test, `@BeforeEach` vẫn hữu ích để biểu đạt rõ fixture và áp dụng nhất quán khi thay đổi test instance lifecycle.

**Không nên** biến `@BeforeEach` thành một thủ tục dài luôn tạo database, khởi động server hoặc tải dữ liệu nặng nếu phần lớn test không cần. Fixture quá lớn khiến test chậm và che giấu điều kiện quan trọng của từng ca.

## 4. @AfterEach: dọn dẹp sau từng test

Phương thức `@AfterEach` chạy ở giai đoạn sau mỗi invocation để dọn tài nguyên thuộc riêng test hoặc hoàn tất kiểm tra liên quan. Ví dụ:

~~~java
private AutoCloseable temporaryClient;

@AfterEach
void tearDown() throws Exception {
    if (temporaryClient != null) {
        temporaryClient.close();
    }
}
~~~

Đây là **đoạn minh họa**, giả sử `temporaryClient` đã được khởi tạo trong Arrange/`@BeforeEach` hoặc trong test. Phần kiểm tra null giúp tránh lỗi khi quá trình khởi tạo không hoàn tất.

Trong những lỗi kiểm thử thông thường như assertion thất bại, JUnit vẫn thực hiện cơ chế teardown, nên `@AfterEach` là vị trí thích hợp để dọn dẹp. Tuy nhiên, không có lời hứa rằng teardown chắc chắn chạy nếu JVM bị buộc dừng, tiến trình bị kill hoặc hạ tầng gặp lỗi nghiêm trọng.

**Lưu ý:** tránh xóa dữ liệu chung hoặc đóng tài nguyên dùng bởi test khác. Nếu dùng `@TempDir` hoặc một resource quản lý tự động, không cần tự viết cleanup tương đương; nếu dùng `try-with-resources` cho tài nguyên chỉ cần trong một phương thức, có thể đóng ngay trong test.

## 5. @BeforeAll và @AfterAll: chuẩn bị và đóng tài nguyên dùng chung

Hai annotation này dùng cho công việc mang tính **lớp test**:

- `@BeforeAll`: khởi tạo một lần tài nguyên nặng hoặc cấu hình dùng chung.
- `@AfterAll`: đóng đúng tài nguyên đã khởi tạo ở phạm vi lớp.

Trong lifecycle mặc định `TestInstance.Lifecycle.PER_METHOD`, phương thức `@BeforeAll` và `@AfterAll` của lớp test thông thường phải khai báo `static`, vì mỗi test có thể sử dụng một instance khác nhau.

~~~java
private static SomeResource sharedResource;

@BeforeAll
static void startResource() {
    sharedResource = new SomeResource();
}

@AfterAll
static void stopResource() {
    if (sharedResource != null) {
        sharedResource.close();
    }
}
~~~

Đoạn trên **minh họa cú pháp**, `SomeResource` là tên tượng trưng, không phải lớp Java/JUnit có sẵn; không sao chép riêng khối này để biên dịch. Ví dụ **đầy đủ, chạy được** ở phần tiếp theo chỉ sử dụng API Java và JUnit thực.

Tài nguyên chung cần được thiết kế an toàn: các test không nên sửa state chung làm cho kết quả phụ thuộc vào thứ tự hay chạy song song. Nếu chỉ dùng một danh sách, đối tượng hoặc mock cho từng test, ưu tiên `@BeforeEach` thay vì chia sẻ bằng `static`.

Với Spring Boot, **Spring TestContext** quản lý vòng đời và cache `ApplicationContext` theo cấu hình test. `@BeforeAll` của JUnit không đồng nghĩa “Spring context được tạo tại đây”, và `@AfterAll` không phải nơi tự ý đóng một `ApplicationContext` được Spring quản lý.

## 6. Ví dụ hoàn chỉnh bằng Java 17 và JUnit Jupiter

Ví dụ sau có đủ **bốn annotation**, một phương thức `@Test` và đầu ra dễ đối chiếu. Test kiểm tra thao tác cộng hai số sau khi thiết lập dữ liệu. Đây là **unit test Java thuần dùng JUnit 5**, không cần chạy Spring Boot ApplicationContext.

**Tệp `src/test/java/com/example/testing/LifecycleHooksTest.java`:**

~~~java
package com.example.testing;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LifecycleHooksTest {
    private static String sharedMode;
    private List<Integer> numbers;

    @BeforeAll
    static void beforeAll() {
        sharedMode = "ready";
        System.out.println("1 beforeAll");
    }

    @BeforeEach
    void beforeEach() {
        numbers = new ArrayList<>();
        numbers.add(1);
        System.out.println("2 beforeEach");
    }

    @Test
    void sum_whenAddingTwo_returnsThree() {
        assertEquals("ready", sharedMode);

        numbers.add(2);
        int sum = numbers.stream().mapToInt(Integer::intValue).sum();

        assertEquals(3, sum);
        System.out.println("3 test");
    }

    @AfterEach
    void afterEach() {
        numbers.clear();
        System.out.println("4 afterEach");
    }

    @AfterAll
    static void afterAll() {
        sharedMode = null;
        System.out.println("5 afterAll");
    }
}
~~~

### Cấu hình và cách chạy

Trong dự án Gradle dùng Spring Boot và JUnit Jupiter, cần có `spring-boot-starter-test` (chứa JUnit Jupiter trong các phiên bản Spring Boot 3.x thông dụng) và chạy test trên JUnit Platform. Ví dụ phần cấu hình liên quan trong `build.gradle` (Groovy DSL):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        showStandardStreams = true
    }
}
~~~

Ví dụ này giả định dự án **đã có Spring Boot Gradle plugin, repositories và toolchain/JDK Java 17+**; khối trên không phải toàn bộ tệp build. Nếu dự án đã có các mục tương ứng, không thêm trùng lặp.

Từ thư mục dự án có Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.testing.LifecycleHooksTest"
~~~

Trên Windows, dùng `gradlew.bat test --tests "com.example.testing.LifecycleHooksTest"`.

Nếu test thành công, **năm dòng do `System.out.println` của ví dụ phát ra** có thứ tự chính xác:

~~~text
1 beforeAll
2 beforeEach
3 test
4 afterEach
5 afterAll
~~~

Gradle có thể thêm tên test, tiêu đề task và thông tin build quanh các dòng trên; cấu hình `showStandardStreams = true` giúp quan sát stdout test. Đây là nội dung được in bởi chương trình, **không phải toàn bộ stdout cố định của Gradle**.

### Giải thích từng bước

1. JUnit gọi `beforeAll()` **một lần** để đặt `sharedMode = "ready"`.
2. Trước test, `beforeEach()` tạo `ArrayList` mới với phần tử `1`.
3. `sum_whenAddingTwo_returnsThree()` kiểm tra cấu hình, thêm `2`, tính tổng `3` và assert bằng `assertEquals`.
4. Sau test, `afterEach()` dọn danh sách đang dùng.
5. Sau khi các test trong lớp hoàn thành, `afterAll()` bỏ trạng thái dùng chung.

Ở đây có một `@Test` nên không tồn tại rủi ro nhầm thứ tự giữa nhiều test. Nếu thêm một `@Test` khác vào cùng lớp, JUnit sẽ chạy `@BeforeEach` và `@AfterEach` thêm một lần cho test mới, còn `@BeforeAll` và `@AfterAll` vẫn thuộc phạm vi lớp.

**Phân biệt trách nhiệm:** kết quả PASS được xác định bởi `assertEquals`. Năm dòng log chỉ giúp quan sát vòng đời; không nên dùng việc “có log” làm bằng chứng thay cho assertion về nghiệp vụ.

## 7. Vì sao @BeforeAll/@AfterAll thường phải static?

JUnit Jupiter mặc định sử dụng `@TestInstance(TestInstance.Lifecycle.PER_METHOD)`: mỗi test method thông thường nhận một **instance mới** của lớp test. Vì không có một instance duy nhất đại diện cho toàn bộ lớp, `@BeforeAll` và `@AfterAll` trên lớp test mặc định phải là phương thức `static`.

Có thể đổi lifecycle của lớp sang **`PER_CLASS`**:

~~~java
package com.example.testing;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import static org.junit.jupiter.api.Assertions.assertEquals;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class PerClassLifecycleTest {
    private List<String> sharedLabels;

    @BeforeAll
    void beforeAll() {
        // Hợp lệ không cần static nhờ PER_CLASS.
        sharedLabels = new ArrayList<>();
        sharedLabels.add("default");
    }

    @BeforeEach
    void beforeEach() {
        // Reset dữ liệu biến đổi trước từng test.
        sharedLabels.clear();
        sharedLabels.add("default");
    }

    @Test
    void labels_whenPrepared_containsOnlyDefault() {
        assertEquals(List.of("default"), sharedLabels);
        sharedLabels.add("changed");
    }

    @AfterAll
    void afterAll() {
        sharedLabels.clear();
    }
}
~~~

Đây là **tệp lớp test Java độc lập**, cũng có thể chạy bằng JUnit 5 khi đặt đúng package/source set và dependency. Với `PER_CLASS`, tất cả test trong lớp dùng **cùng một instance**, nên các instance field có thể giữ trạng thái từ test trước. Ví dụ cố ý reset `sharedLabels` trong `@BeforeEach` để tránh rò rỉ trạng thái.

Chỉ chọn `PER_CLASS` khi thực sự cần (chẳng hạn sử dụng instance lifecycle methods, test interface hoặc fixture phù hợp). Đổi lifecycle chỉ để bỏ chữ `static` có thể làm test khó cô lập, nhất là khi dự án cho phép chạy test song song.

**Quy tắc:** với `PER_METHOD` thông thường, `@BeforeAll`/`@AfterAll` là `static`; `@BeforeEach`/`@AfterEach` là instance methods. Với `PER_CLASS`, hai hook cấp lớp có thể là instance methods. JUnit cũng hỗ trợ mở rộng khác như test interfaces và extensions, nhưng cấu hình test instance là điểm cần hiểu trước tiên.

## 8. Nếu có nhiều test hoặc nhiều hook thì điều gì xảy ra?

### Nhiều phương thức @Test

Với ba test method thông thường, mỗi method thực thi một lần, lớp test thường có:

- 1 lượt `@BeforeAll`.
- 3 lượt `@BeforeEach`, mỗi lượt gắn với một test.
- 3 lượt `@AfterEach`.
- 1 lượt `@AfterAll`.

Nếu các test chạy song song, không thể dùng “đã chạy test A” làm điều kiện của test B. Mỗi fixture phải độc lập hoặc dữ liệu chia sẻ phải có cơ chế đồng bộ an toàn.

### Parameterized và repeated tests

`@ParameterizedTest` với bốn bộ dữ liệu là bốn **lượt gọi test**: `@BeforeEach` và `@AfterEach` chạy cho từng lượt. `@RepeatedTest(3)` cũng được bao quanh theo từng lượt lặp. Đó là lý do tên “Each” chính xác hơn cách hiểu “trước mỗi phương thức được khai báo trong file”.

Một ngoại lệ cần phân biệt: với `@TestFactory` tạo **dynamic tests**, JUnit chạy `@BeforeEach`/`@AfterEach` quanh **factory method** chứ không tự động bao quanh riêng từng dynamic test con. Nếu mỗi dynamic test cần setup/cleanup riêng, hãy thiết kế logic tương ứng hoặc dùng parameterized tests khi phù hợp.

### Kế thừa và @Nested

Với lớp test kế thừa, những lifecycle method hợp lệ trong superclass có thể được thừa hưởng. Về thứ tự thông thường: setup từ **superclass trước subclass**, teardown từ **subclass trước superclass**. Với lớp test `@Nested`, các hook bên ngoài và bên trong cũng được phối hợp theo cấp lồng nhau.

Nếu khai báo **nhiều phương thức cùng một annotation trong cùng một lớp**, JUnit sử dụng quy tắc sắp xếp xác định nhưng không nên dựa vào thứ tự trông thấy trong mã nguồn. Các phương thức `@AfterEach` cũng không nhất thiết được ghép đảo ngược 1–1 với các phương thức `@BeforeEach`. Thực hành dễ bảo trì là **một hook cho mỗi loại công việc ở một lớp**, rồi gọi các hàm helper theo đúng thứ tự chủ động mong muốn.

Không dùng `@TestMethodOrder` hoặc `@Order` của test để giải quyết việc thiếu cô lập dữ liệu; thứ tự test và lifecycle setup là hai vấn đề khác nhau.

## 9. Kết hợp lifecycle callbacks với Spring Boot Test

Khi dùng `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest` hoặc các test slice khác, JUnit Jupiter vẫn gọi các hook như trên, còn **Spring TestContext Framework** phụ trách tạo/tiêm bean và quản lý ngữ cảnh theo cấu hình của loại test.

| Nhu cầu trong Spring Boot | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Mỗi test cần request DTO hoặc dữ liệu đầu vào mới | `@BeforeEach` | Mỗi ca có trạng thái đầu vào riêng |
| Mỗi test cần stub dependency theo tình huống | `@BeforeEach` hoặc phần Arrange trong test | Phụ thuộc mock phản ánh đúng ca cụ thể |
| Dùng chung cấu hình hằng/fixture chỉ đọc | `@BeforeAll` nếu cần tạo một lần | Tránh setup lặp lại không cần thiết |
| Đóng file/client/server **tự khởi tạo** cho cả lớp | `@AfterAll` | Dọn tài nguyên do lớp sở hữu |
| Dọn tài nguyên file/client **từng test tự tạo** | `@AfterEach` hoặc resource tự quản lý | Không ảnh hưởng test khác |
| Kiểm thử dữ liệu database với Spring transaction | Theo cơ chế transaction/rollback của test, cộng fixture thích hợp | Tránh xóa thủ công khi cơ chế của framework đã xử lý |

Không giả định rằng bean `@Autowired` đã có thể được truy cập qua một **trường instance** bên trong phương thức `static @BeforeAll`. Nếu setup cần bean, cân nhắc `@BeforeEach` sau khi test instance được chuẩn bị hoặc cơ chế injection tham số do extension hỗ trợ, thay vì tự tạo một Spring context thứ hai.

Ví dụ: trong `@WebMvcTest`, `@BeforeEach` có thể chuẩn bị đầu vào và stub service được mock; sau đó `MockMvc` thực thi request và assertion kiểm tra HTTP status/body. Không đặt logic “gọi endpoint cần kiểm tra” trong `@BeforeEach`, vì như vậy mọi test đều thực hiện cùng hành động mà tên test có thể không phản ánh.

Với `@DataJpaTest` và các test có giao dịch do Spring TestContext quản lý, cơ chế rollback mặc định trong trường hợp tương ứng giúp cô lập database. Nhưng rollback đó **không tự dọn** tệp, tài nguyên bên ngoài, thông điệp gửi ra hệ thống khác hoặc thay đổi xảy ra ngoài transaction; cần chọn cleanup theo tài nguyên thực sự sở hữu.

Một số Spring Boot test dùng Testcontainers hoặc dịch vụ test chạy tốn thời gian. Quyết định container được quản lý theo lớp hay theo framework (ví dụ hỗ trợ Testcontainers lifecycle) phải rõ ràng; đừng đóng container do lớp khác hoặc framework đang dùng chung.

## 10. Khi test thất bại, hook có còn chạy không?

Với một **assertion failure** hay exception thông thường trong phương thức test, JUnit vẫn tiến hành các callback cleanup sau test, vì `@AfterEach` không chỉ dành cho đường đi thành công. Vì vậy đặt thao tác dọn state tại đó phù hợp hơn việc viết câu lệnh cleanup ở dòng cuối thân test: nếu assertion ném lỗi trước dòng cuối, cleanup trực tiếp sẽ bị bỏ qua.

Tuy nhiên, một số trường hợp không nên khẳng định cleanup luôn chạy:

- JVM/tiến trình bị chấm dứt bất ngờ.
- Hệ thống hỏng trước khi JUnit thực thi callback.
- Chính lifecycle method bị lỗi; khi đó test cũng có thể fail và quá trình xử lý lỗi tuân theo JUnit engine.
- Test bị `@Disabled` có thể không có invocation để chạy `@BeforeEach`/`@AfterEach`.

Khi `@BeforeEach` thất bại, thân test có thể không được chạy; JUnit vẫn có cơ chế kết thúc invocation và chạy các callback dọn dẹp phù hợp, nên `@AfterEach` phải đủ an toàn nếu fixture mới được tạo **một phần** (ví dụ kiểm tra null).

Không dùng `@AfterAll` để “cứu” kết quả test thất bại hoặc thay đổi assertion. Mục tiêu của teardown là bảo toàn môi trường và giải phóng tài nguyên, không biến test đỏ thành xanh.

## 11. Lỗi phổ biến và cách khắc phục

1. **Nhầm `@BeforeAll` với `@BeforeEach`:** muốn một giỏ hàng mới cho mỗi test nhưng chỉ tạo một lần. **Khắc phục:** tạo dữ liệu có thể biến đổi trong `@BeforeEach` để từng ca độc lập.
2. **Quên `static` ở `@BeforeAll` hoặc `@AfterAll` khi đang dùng `PER_METHOD`:** JUnit báo lỗi lifecycle method không hợp lệ. **Khắc phục:** thêm `static` hoặc khai báo `@TestInstance(PER_CLASS)` có chủ đích.
3. **Chia sẻ đối tượng mutable giữa các test:** một test thay đổi dữ liệu rồi test khác thất bại tùy thứ tự chạy. **Khắc phục:** dùng fixture riêng, reset đầy đủ hoặc chọn state bất biến.
4. **Setup rất nặng ở `@BeforeEach`:** database/container được khởi tạo nhiều lần, test suite chậm. **Khắc phục:** xem tài nguyên nào có thể dùng chung an toàn hoặc để framework quản lý; giữ dữ liệu riêng cho mỗi test.
5. **Cleanup chỉ ở cuối phương thức `@Test`:** assertion fail sớm làm bỏ qua cleanup. **Khắc phục:** dùng `@AfterEach` hay `try-with-resources` phù hợp phạm vi.
6. **Đóng Spring ApplicationContext thủ công trong `@AfterAll`:** phá vỡ cache/context lifecycle do Spring TestContext quản lý. **Khắc phục:** chỉ đóng tài nguyên chính test đã tạo và sở hữu.
7. **Phụ thuộc vào thứ tự thực hiện test:** test B cần trạng thái do test A tạo. **Khắc phục:** Arrange cho B phải tự đủ điều kiện; không dùng thứ tự để chia sẻ trạng thái.
8. **Có nhiều lifecycle method cùng loại và giả định thứ tự theo vị trí trong file:** dẫn đến setup/teardown khó đoán. **Khắc phục:** dùng một method callback và gọi helper theo thứ tự rõ ràng.
9. **Xóa hoặc rollback sai phạm vi:** cleanup của một test làm mất fixture chung hoặc dữ liệu phục vụ test khác. **Khắc phục:** phân biệt tài nguyên per-test, per-class và tài nguyên do framework quản lý.

## 12. Chọn đúng hook: quy trình ngắn

Trước khi viết một lifecycle method, trả lời ba câu hỏi:

1. **Tài nguyên phục vụ bao nhiêu test?** Chỉ một lượt test thì ưu tiên `@BeforeEach`/`@AfterEach` hoặc setup trực tiếp trong test. Cả lớp thì cân nhắc `@BeforeAll`/`@AfterAll`.
2. **Tài nguyên có thể thay đổi không?** Nếu có, dùng dữ liệu độc lập cho từng test hoặc reset thật rõ; hạn chế dùng state tĩnh dùng chung.
3. **Ai sở hữu việc đóng/dọn?** Nếu Spring, JUnit, `@TempDir` hoặc thư viện quản lý vòng đời đã chịu trách nhiệm, không tự dọn trùng; nếu test mở file/socket/client riêng, phải bảo đảm teardown thích hợp.

Checklist trước khi hoàn thiện lớp test:

- [ ] Mỗi test có trạng thái ban đầu rõ ràng và chạy độc lập.
- [ ] `@BeforeEach` tạo/đặt lại fixture cần thiết cho **mỗi lượt**.
- [ ] `@AfterEach` an toàn cả khi test fail hoặc setup chưa hoàn chỉnh.
- [ ] `@BeforeAll`/`@AfterAll` chỉ xử lý công việc thực sự dùng chung ở cấp lớp.
- [ ] Các phương thức cấp lớp thỏa điều kiện `static` hoặc `PER_CLASS`.
- [ ] Không giữ state mutable gây phụ thuộc thứ tự/parallel test.
- [ ] Không đóng tài nguyên được Spring/JUnit hoặc lớp khác quản lý.
- [ ] Assertions nằm trong test và đo đúng kết quả nghiệp vụ; lifecycle không thay thế kiểm chứng.

**Ghi nhớ:** `@BeforeAll`/**một lần trước lớp**, `@BeforeEach`/**trước từng lượt**, `@AfterEach`/**sau từng lượt**, `@AfterAll`/**một lần sau lớp**. Chọn callback theo **phạm vi sống của dữ liệu và tài nguyên**, đồng thời giữ từng test độc lập, có thể chạy lại và đáng tin cậy.