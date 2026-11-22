# Chu trình TDD: thất bại có ý nghĩa, sửa và tái cấu trúc

TDD (Test-Driven Development) là cách phát triển phần mềm trong đó một bài kiểm thử được viết trước phần triển khai mà nó mô tả. Người phát triển lặp lại một chu trình ngắn gồm ba bước: viết một kiểm thử mới và quan sát nó thất bại, thay đổi ít nhất có thể để kiểm thử thành công, rồi tái cấu trúc thiết kế trong khi giữ toàn bộ kiểm thử ở trạng thái xanh.

Chu trình này thường được gọi là **Red – Green – Refactor**:

- **Red:** tạo một kiểm thử diễn đạt hành vi còn thiếu và xác nhận kiểm thử thất bại vì đúng lý do.
- **Green:** viết phần triển khai đơn giản nhất đáp ứng hành vi vừa được mô tả.
- **Refactor:** cải thiện cấu trúc của code kiểm thử và code sản phẩm mà không thay đổi hành vi đã được kiểm chứng.

Trong Spring Framework Testing, TDD giúp biến yêu cầu thành ví dụ có thể chạy, tạo phản hồi sớm về thiết kế và giảm rủi ro khi thay đổi. Tuy nhiên, mỗi vòng lặp cần chọn đúng ranh giới kiểm thử: quy tắc nghiệp vụ, hành vi do Spring container cung cấp, hay tích hợp với hạ tầng ngoài.

## 1. Vì sao TDD bắt đầu bằng một kiểm thử thất bại?

Khi bắt đầu từ code sản phẩm, người phát triển thường phải tự hình dung hành vi cần có rồi mới tìm cách chứng minh nó đúng. TDD đảo thứ tự đó: trước khi thêm hành vi, hãy viết một ví dụ cụ thể thể hiện kết quả mong đợi.

Một kiểm thử mới cần làm rõ ít nhất ba điều:

1. **Điều kiện:** đầu vào hoặc trạng thái ban đầu là gì?
2. **Hành động:** thành phần nào được gọi và với dữ liệu nào?
3. **Kết quả mong đợi:** quan sát được điều gì nếu hành vi đúng?

Ví dụ, một yêu cầu nghiệp vụ nói rằng đơn hàng dưới ngưỡng miễn phí phải trả phí vận chuyển tiêu chuẩn. Thay vì lập tức viết nhánh điều kiện trong calculator, ta diễn đạt yêu cầu đó bằng một test: với subtotal là 250.000 và không chọn giao nhanh, phí vận chuyển phải là 30.000.

Test trở thành một ví dụ có thể thực thi của yêu cầu. Nếu nó thất bại trước khi có phần triển khai tương ứng, ta biết test đã phát hiện khoảng trống cần giải quyết. Nếu test vẫn xanh khi hành vi chưa được triển khai, có thể test chưa đi qua đúng đường xử lý hoặc assertion chưa đủ mạnh.

TDD không đơn thuần là viết thật nhiều test. Giá trị của nó đến từ việc mỗi test mới tạo ra một tín hiệu rõ ràng, sau đó phần triển khai được thay đổi để đáp ứng tín hiệu đó.

## 2. Toàn bộ vòng Red – Green – Refactor

~~~mermaid
flowchart TD
    A["Chọn một hành vi nhỏ"] --> B["RED: viết test"]
    B --> C["Chạy test và quan sát thất bại"]
    C --> D{"Thất bại đúng lý do?"}
    D -->|"Chưa"| E["Sửa test, fixture hoặc cách chạy"]
    E --> C
    D -->|"Đúng"| F["GREEN: triển khai tối thiểu"]
    F --> G["Chạy lại test mới và bộ test liên quan"]
    G --> H{"Tất cả đều xanh?"}
    H -->|"Chưa"| F
    H -->|"Đúng"| I["REFACTOR: cải thiện cấu trúc"]
    I --> J["Chạy lại test"]
    J --> K{"Hành vi vẫn đúng?"}
    K -->|"Chưa"| I
    K -->|"Đúng"| L["Chọn hành vi tiếp theo"]
    L --> A
~~~

Mỗi vòng lặp nên đủ nhỏ để người phát triển hiểu chính xác thay đổi nào làm test chuyển từ đỏ sang xanh. Nếu một vòng kéo dài với nhiều lớp, nhiều quy tắc và nhiều hệ thống ngoài, sẽ khó xác định nguyên nhân khi có lỗi.

### Red — tạo một tín hiệu thất bại đáng tin cậy

Ở bước Red, hãy viết test cho một hành vi chưa được đáp ứng. Sau đó chạy test và xác nhận:

- Test được biên dịch và thực sự được thực thi.
- Assertion thất bại vì kết quả thực tế khác kết quả mong đợi, hoặc vì một ngoại lệ đúng với hành vi đang đặc tả.
- Test đi qua đúng thành phần và đúng đường xử lý cần kiểm tra.
- Lỗi không xuất phát từ cấu hình môi trường, dependency chưa khởi động, tên test sai hoặc một fixture bị hỏng.

Một lỗi biên dịch do chưa khai báo class hoặc method không phải tín hiệu Red tốt để kiểm chứng hành vi. Trước khi đánh giá assertion, cần có bộ khung tối thiểu để test chạy được. Tương tự, nếu test Spring thất bại vì không tìm thấy bean do cấu hình test thiếu, điều đó chưa chứng minh quy tắc nghiệp vụ đang sai.

Hãy đọc nguyên nhân thất bại, không chỉ nhìn màu đỏ trong IDE. Một thông báo như “expected 30000 but was 0” có thể là tín hiệu rõ ràng. Một lỗi kết nối database hoặc lỗi khởi tạo context có thể chỉ là vấn đề thiết lập môi trường.

### Green — thay đổi ít nhất để đáp ứng test

Sau khi có tín hiệu Red đáng tin cậy, triển khai phần code nhỏ nhất làm test chuyển sang xanh.

Mục tiêu ở bước này là đáp ứng hành vi vừa được mô tả, không phải xây dựng trước mọi khả năng tương lai. Tránh thêm nhiều abstraction, cấu hình hoặc nhánh xử lý chưa có yêu cầu và chưa có test tương ứng.

Khi test xanh, chạy lại test mới cùng những test liên quan. Nếu thay đổi làm hỏng một hành vi đã được kiểm chứng, bộ test cần báo ngay. Một test mới chuyển xanh nhưng test cũ chuyển đỏ cho thấy thay đổi chưa hoàn thành.

### Refactor — cải thiện cấu trúc mà không đổi hành vi

Khi các test đang xanh, có thể cải thiện code để dễ đọc và dễ thay đổi hơn:

- Đặt tên class, method, biến và test theo ý nghĩa nghiệp vụ.
- Loại bỏ lặp lại, điều kiện khó hiểu hoặc nhánh không cần thiết.
- Tách trách nhiệm khi một class đang làm quá nhiều việc.
- Đưa các giá trị lặp lại thành hằng số có tên.
- Làm fixture và helper của test rõ ràng, tránh che khuất hành vi đang kiểm tra.
- Xóa code thừa và các abstraction không còn cần thiết.

Sau mỗi thay đổi cấu trúc có ý nghĩa, chạy lại test. Nếu một refactor làm thay đổi kết quả nghiệp vụ, đó không còn là refactor thuần túy; hãy quay lại Red–Green để mô tả và triển khai hành vi mới.

## 3. Ví dụ TDD cho một quy tắc nghiệp vụ

Giả sử cửa hàng có chính sách vận chuyển:

- Giao tiêu chuẩn có phí 30.000.
- Đơn hàng đạt subtotal từ 500.000 trở lên được miễn phí giao tiêu chuẩn.
- Giao nhanh có phí cố định 50.000, không phụ thuộc ngưỡng miễn phí tiêu chuẩn.

Ta muốn xây dựng một class thuần Java tính phí vận chuyển. Quy tắc này không cần Spring container, database hay HTTP để kiểm tra. Vì vậy, vòng TDD đầu tiên có thể dùng JUnit 5 và tạo calculator trực tiếp.

### Vòng đầu tiên: RED

Bắt đầu bằng một test mô tả trường hợp đơn hàng dưới ngưỡng miễn phí:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class ShippingFeeCalculatorTest {

    @Test
    void chargesStandardFeeBelowFreeShippingThreshold() {
        var calculator = new ShippingFeeCalculator();

        BigDecimal actual = calculator.calculate(
                new BigDecimal("250000"),
                false
        );

        assertEquals(new BigDecimal("30000"), actual);
    }
}
~~~

Để test có thể biên dịch và chạy, có thể tạo một implementation ban đầu tối thiểu:

~~~java
import java.math.BigDecimal;

public final class ShippingFeeCalculator {

    public BigDecimal calculate(BigDecimal subtotal, boolean express) {
        return BigDecimal.ZERO;
    }
}
~~~

Chạy test. Kết quả thực tế là 0 trong khi mong đợi là 30.000. Đây là một lần Red có ý nghĩa: test đã chạy đến method cần kiểm tra, nhận được kết quả và chỉ ra hành vi còn thiếu.

Nếu test báo lỗi không tìm thấy class hoặc không chạy được, hãy xử lý vấn đề biên dịch/thiết lập trước. Đừng coi lỗi đó là bằng chứng rằng quy tắc vận chuyển đã được kiểm tra.

### Vòng đầu tiên: GREEN

Thay implementation tối thiểu bằng logic đáp ứng trường hợp vừa mô tả:

~~~java
import java.math.BigDecimal;

public final class ShippingFeeCalculator {

    public BigDecimal calculate(BigDecimal subtotal, boolean express) {
        if (express) {
            return new BigDecimal("50000");
        }

        if (subtotal.compareTo(new BigDecimal("500000")) >= 0) {
            return BigDecimal.ZERO;
        }

        return new BigDecimal("30000");
    }
}
~~~

Chạy lại test. Trường hợp subtotal 250.000 phải nhận phí 30.000 và chuyển sang xanh.

Tại thời điểm này, chưa cần thêm xử lý cho mọi loại đầu vào có thể tưởng tượng. Hãy tiếp tục bằng một hành vi mới có yêu cầu rõ ràng.

### Vòng tiếp theo: thêm hành vi miễn phí giao tiêu chuẩn

Viết test cho đúng ranh giới 500.000:

~~~java
@Test
void waivesStandardFeeAtFreeShippingThreshold() {
    var calculator = new ShippingFeeCalculator();

    BigDecimal actual = calculator.calculate(
            new BigDecimal("500000"),
            false
    );

    assertEquals(BigDecimal.ZERO, actual);
}
~~~

Chạy test trước khi thay đổi code. Nếu test chuyển xanh ngay, hãy kiểm tra xem implementation hiện tại đã tình cờ hỗ trợ hành vi này hay test có thực sự đi qua nhánh dự kiến. Trong ví dụ này, logic ở vòng trước đã có điều kiện ngưỡng nên test mới sẽ xanh ngay. Điều đó vẫn có giá trị: test mới ghi nhận một hành vi quan trọng và bảo vệ nó khỏi các thay đổi tiếp theo.

Tiếp tục viết test cho giao nhanh:

~~~java
@Test
void chargesExpressFeeRegardlessOfSubtotal() {
    var calculator = new ShippingFeeCalculator();

    BigDecimal actual = calculator.calculate(
            new BigDecimal("900000"),
            true
    );

    assertEquals(new BigDecimal("50000"), actual);
}
~~~

Nếu implementation hiện tại trả về 50.000, test chuyển xanh ngay vì nhánh giao nhanh đã được viết ở vòng đầu. Khi viết một test mới, trạng thái đỏ không phải mục tiêu bằng mọi giá. Mục tiêu là có bằng chứng cụ thể cho hành vi; nếu hành vi đã đúng và test có thể thất bại khi quy tắc bị phá vỡ, test vẫn hữu ích.

### Refactor: đặt tên cho chính sách

Sau khi có các test bao phủ ba quy tắc, có thể làm code dễ đọc hơn bằng cách đặt tên cho các mức phí và ngưỡng:

~~~java
import java.math.BigDecimal;

public final class ShippingFeeCalculator {

    private static final BigDecimal STANDARD_FEE =
            new BigDecimal("30000");

    private static final BigDecimal EXPRESS_FEE =
            new BigDecimal("50000");

    private static final BigDecimal FREE_SHIPPING_THRESHOLD =
            new BigDecimal("500000");

    public BigDecimal calculate(BigDecimal subtotal, boolean express) {
        if (express) {
            return EXPRESS_FEE;
        }

        if (subtotal.compareTo(FREE_SHIPPING_THRESHOLD) >= 0) {
            return BigDecimal.ZERO;
        }

        return STANDARD_FEE;
    }
}
~~~

Việc đặt tên giúp người đọc hiểu ý nghĩa của các con số. Các test vẫn phải xanh sau refactor. Ta chưa thêm quy tắc mới; chỉ làm cho implementation thể hiện chính sách hiện có rõ hơn.

### Mở rộng test cho biên

Ngưỡng thường là nơi dễ có lỗi dùng sai toán tử. Nếu chính sách nói “từ 500.000 trở lên”, test cần phân biệt nhỏ hơn ngưỡng và đúng bằng ngưỡng. Có thể dùng parameterized test để thể hiện các ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingFeeBoundaryTest {

    private final ShippingFeeCalculator calculator =
            new ShippingFeeCalculator();

    @ParameterizedTest
    @CsvSource({
        "499999, 30000",
        "500000, 0",
        "500001, 0"
    })
    void calculatesStandardFeeAtThresholdBoundaries(
            String subtotal,
            String expectedFee
    ) {
        BigDecimal actual = calculator.calculate(
                new BigDecimal(subtotal),
                false
        );

        assertEquals(new BigDecimal(expectedFee), actual);
    }
}
~~~

Bộ test này giúp phân biệt điều kiện lớn hơn với lớn hơn hoặc bằng. Khi thay đổi toán tử từ **>=** thành **>**, trường hợp 500.000 sẽ thất bại và chỉ ra lỗi biên.

Các ví dụ trên dùng **BigDecimal** để tránh sai số biểu diễn số thực khi tính tiền. Trong ứng dụng thực tế, quy tắc làm tròn, đơn vị tiền tệ, thuế và cách biểu diễn tiền cũng cần được mô tả bằng yêu cầu và test riêng nếu chúng thuộc phạm vi nghiệp vụ.

## 4. Thế nào là một lần thất bại có ý nghĩa?

Không phải mọi trạng thái test đỏ đều có giá trị như nhau. Một test thất bại có ý nghĩa khi nó chứng minh rằng hành vi được mô tả hiện chưa đáp ứng kết quả mong đợi.

Có thể phân biệt một số tình huống:

| Kết quả khi chạy | Ý nghĩa | Cách xử lý |
|---|---|---|
| Assertion báo expected khác actual | Test đã chạy và quan sát hành vi sai | Xác nhận đây là hành vi mới, rồi triển khai |
| Test không biên dịch | Chưa thể thực thi đặc tả | Sửa import, chữ ký, class hoặc cấu trúc test |
| Không tìm thấy test / không có test nào chạy | Chưa có bằng chứng | Kiểm tra tên, package, bộ lọc và cấu hình chạy |
| Spring không tạo được ApplicationContext | Có thể là lỗi cấu hình test hoặc cấu hình ứng dụng | Đọc nguyên nhân khởi tạo context trước khi kết luận |
| Không kết nối được database/broker | Hạ tầng hoặc cấu hình môi trường chưa sẵn sàng | Kiểm tra service, endpoint, port và dữ liệu test |
| Test thất bại do timeout hoặc dữ liệu còn sót | Kết quả chưa ổn định | Cô lập tài nguyên và loại bỏ phụ thuộc thứ tự |

Một lần Red tốt thường có thông báo lỗi gần với hành vi đang kiểm tra. Nếu test muốn xác nhận phí vận chuyển nhưng thất bại do database không khởi động, test chưa cung cấp tín hiệu về quy tắc đó.

Khi test cần xác nhận một ngoại lệ, ngoại lệ mong đợi phải được thể hiện rõ trong assertion. Ví dụ, nếu đầu vào âm bị cấm theo yêu cầu, test có thể dùng **assertThrows** để xác nhận đúng loại ngoại lệ. Một ngoại lệ bất ngờ từ NullPointerException hoặc lỗi cấu hình không nên bị nhầm thành kết quả mong đợi.

Cũng cần kiểm tra chiều ngược lại: nếu test mới chạy xanh ngay, hãy xem nó có thật sự phân biệt implementation đúng và sai không. Một assertion chỉ kiểm tra object khác null thường không đủ để bảo vệ một quy tắc phức tạp.

## 5. TDD ở các ranh giới kiểm thử trong Spring

TDD là một chu trình phát triển, không phải một annotation hoặc một loại test cố định. Có thể áp dụng Red–Green–Refactor ở nhiều tầng, miễn là test mô tả đúng hành vi của tầng đó.

### Quy tắc nghiệp vụ: ưu tiên vòng lặp nhanh

Với domain model, calculator, validator và application service có dependency qua interface, hãy bắt đầu bằng JUnit thuần. Tạo object trực tiếp và dùng fake/stub/mock để kiểm soát dependency khi cần.

Ưu điểm là vòng phản hồi nhanh, không phải chờ Spring khởi tạo context và test tập trung vào hành vi. Ví dụ calculator phí vận chuyển ở trên thuộc loại này.

Nếu một quy tắc chỉ có thể kiểm tra bằng cách dựng toàn bộ ứng dụng, hãy xem lại dependency của thành phần. Có thể logic nghiệp vụ đang phụ thuộc trực tiếp vào database, clock hệ thống hoặc API khiến việc kiểm thử khó kiểm soát.

### Spring container: kiểm tra hành vi được Spring cung cấp

Khi hành vi cần kiểm tra là dependency injection, conditional bean, profile, property, AOP hoặc transaction proxy, test cần đi qua context Spring.

Có thể viết một test cho cấu hình bean, chạy test để quan sát bean chưa được đăng ký hoặc được inject sai, sau đó sửa cấu hình và chạy lại. Với Spring Boot auto-configuration, **ApplicationContextRunner** cho phép tạo các context nhỏ với từng bộ property và classpath cần thiết.

Trong TDD ở tầng này, điều quan trọng là phân biệt lỗi cấu hình với lỗi nghiệp vụ. Nếu mục tiêu là kiểm tra transaction proxy, test phải lấy bean từ context và gọi method qua bean đó. Tự tạo object bằng **new** sẽ bỏ qua proxy và không thể kiểm tra hành vi này.

### Spring MVC: phát triển endpoint bằng test slice

Với controller, có thể dùng **@WebMvcTest** và MockMvc để mô tả request/response trước khi hoàn thiện controller hoặc mapping. Test có thể xác nhận:

- HTTP method và URL mapping.
- Path variable, query parameter và request body được bind đúng.
- Validation trả về lỗi phù hợp.
- Status code, header và JSON response đúng hợp đồng.
- Exception được chuyển thành HTTP response theo quy ước.

Ví dụ, test cho một endpoint tìm đơn hàng có thể gửi GET request với mã đơn hàng và xác nhận response có status 200 cùng JSON chứa đúng mã. Nếu mapping chưa tồn tại, test thất bại vì không nhận được response mong đợi. Sau đó triển khai controller và cấu hình cần thiết để test xanh.

Một test MVC slice thường thay service bằng mock hoặc cung cấp dependency test riêng. Nó tập trung vào adapter HTTP; nó không chứng minh database thật có dữ liệu hoặc quy tắc nghiệp vụ của service đúng.

### Persistence: phát triển repository theo hành vi dữ liệu

Với JPA repository, **@DataJpaTest** giúp kiểm tra mapping, truy vấn và hành vi persistence trong context phù hợp. Có thể viết test mô tả dữ liệu cần lưu và truy xuất, quan sát truy vấn chưa đáp ứng rồi triển khai repository hoặc mapping.

Nếu ứng dụng phụ thuộc vào dialect, kiểu dữ liệu, locking hoặc tính năng riêng của PostgreSQL/MySQL, hãy chạy test với hệ quản trị tương ứng, chẳng hạn bằng Testcontainers. Một test với H2 chỉ chứng minh hành vi trong môi trường H2 đã cấu hình; không tự động chứng minh tương thích với database production.

### Luồng tích hợp: dùng khi chính sự phối hợp là hành vi cần kiểm tra

Một luồng nghiệp vụ có thể đi qua controller, service, repository và broker. Khi yêu cầu là xác nhận sự phối hợp của nhiều thành phần, có thể dùng test tích hợp rộng hơn như **@SpringBootTest** và các dependency phù hợp.

Vòng Red–Green–Refactor vẫn áp dụng, nhưng phản hồi sẽ chậm hơn. Vì vậy, hãy giữ test tích hợp cho những rủi ro cần kiểm tra ở phạm vi đó, đồng thời mô tả nhiều quy tắc nhỏ hơn bằng test nhanh ở tầng nghiệp vụ.

| Ranh giới | Công cụ Spring/JUnit thường dùng | Hành vi có thể mô tả bằng TDD |
|---|---|---|
| Nghiệp vụ | JUnit 5, fake/stub/mock | Quy tắc, tính toán, quyết định, điều phối |
| Container/configuration | Spring TestContext, ApplicationContextRunner | Bean, profile, property, proxy, auto-configuration |
| MVC adapter | @WebMvcTest, MockMvc | Mapping, binding, validation, HTTP response |
| Persistence | @DataJpaTest, database test | Mapping entity, repository query, transaction dữ liệu |
| Tích hợp ứng dụng | @SpringBootTest, Testcontainers | Sự phối hợp giữa nhiều thành phần và hạ tầng |

## 6. Refactor đúng nghĩa trong TDD

Refactor là thay đổi cấu trúc bên trong mà vẫn giữ hành vi bên ngoài đã được kiểm thử. Bước này giúp code tiếp tục dễ hiểu khi số lượng quy tắc tăng lên.

### Refactor code sản phẩm

Một số dấu hiệu cho thấy code có thể cần refactor:

- Nhiều method lặp lại cùng một điều kiện hoặc phép tính.
- Một method chứa nhiều nhánh không cùng trách nhiệm.
- Tên biến không cho biết ý nghĩa nghiệp vụ.
- Một class cần quá nhiều dependency để thực hiện một hành vi nhỏ.
- Một thay đổi đơn giản buộc phải sửa nhiều vị trí không liên quan.
- Test khó dựng vì class kết hợp logic nghiệp vụ với truy cập hạ tầng.

Có thể tách một policy, đưa giá trị cố định thành hằng số, đổi tên method hoặc chia một class thành các trách nhiệm nhỏ hơn. Mỗi thay đổi cần được bảo vệ bởi test đang xanh.

Không nên dùng bước refactor để thêm quy tắc mới, đổi thông điệp lỗi hoặc thay đổi thứ tự side effect. Những thay đổi đó cần test mới mô tả hành vi mới và một vòng Red–Green riêng.

### Refactor code kiểm thử

Test cũng cần được duy trì như code sản phẩm. Khi test tăng lên, hãy chú ý:

- Mỗi test có tên mô tả điều kiện và kết quả.
- Phần Arrange không che khuất hành động đang kiểm tra.
- Dữ liệu test ngắn gọn và có ý nghĩa.
- Helper dùng chung chỉ được tạo khi thực sự giảm lặp mà vẫn giữ test dễ đọc.
- Không gom quá nhiều hành vi không liên quan vào một test.
- Không tạo abstraction test phức tạp hơn chính logic cần kiểm tra.

Có thể dùng cấu trúc Arrange – Act – Assert:

~~~java
@Test
void waivesStandardFeeAtFreeShippingThreshold() {
    // Arrange
    var calculator = new ShippingFeeCalculator();
    var subtotal = new BigDecimal("500000");

    // Act
    var actual = calculator.calculate(subtotal, false);

    // Assert
    assertEquals(BigDecimal.ZERO, actual);
}
~~~

Cấu trúc này giúp người đọc nhận ra dữ liệu đầu vào, hành động và kết quả. Không cần ép mọi test phải có ba comment nếu tên biến và bố cục đã đủ rõ.

## 7. Các thói quen làm chu trình TDD mất tác dụng

### Viết test nhưng không chạy trước khi triển khai

Nếu test được viết cùng lúc với implementation rồi chỉ chạy một lần ở cuối, ta không biết test có thể phát hiện hành vi thiếu hay không. Có thể assertion vô tình khớp với implementation sai hoặc test không đi qua nhánh cần kiểm tra.

Hãy chạy test ngay sau khi viết và đọc kết quả Red trước khi thêm logic.

### Coi mọi lỗi đỏ là một lần Red thành công

Lỗi biên dịch, lỗi khởi tạo Spring context và lỗi kết nối database đều có thể làm test đỏ. Chúng không nhất thiết nói điều gì về hành vi đang được đặc tả.

Đọc stack trace và xác định lỗi xuất hiện ở bước nào: biên dịch, discovery, setup, thực thi hay assertion. Chỉ chuyển sang Green khi tín hiệu thất bại đúng với mục tiêu của test.

### Viết một test quá lớn cho nhiều hành vi

Một test vừa kiểm tra mapping, tính phí, lưu database, publish message và response HTTP sẽ khó chỉ ra hành vi nào sai. Khi test đỏ, người phát triển phải điều tra nhiều ranh giới cùng lúc.

Tách các hành vi có thể kiểm tra độc lập thành các test phù hợp với từng tầng. Dùng test tích hợp để xác nhận sự phối hợp tổng thể khi đó là mục tiêu cần chứng minh.

### Mock tất cả dependency rồi tưởng rằng tích hợp đã đúng

Mock có thể làm test nhanh và kiểm soát được nhánh xử lý. Nhưng nếu mọi repository, HTTP client và broker đều được mock, test không còn kiểm tra giao thức, SQL hay cấu hình kết nối với hệ thống thật.

Hãy giữ mock ở những ranh giới cần cô lập; bổ sung test adapter/hạ tầng khi tương thích thực tế là rủi ro cần kiểm tra.

### Triển khai quá nhiều trước khi chạy lại

Nếu viết một loạt test, thêm nhiều class và thay đổi nhiều cấu hình rồi mới chạy, lỗi có thể đến từ nhiều nguyên nhân. Vòng lặp ngắn giúp thu hẹp phạm vi thay đổi cần điều tra.

### Refactor khi test chưa xanh

Refactor trên nền test đang đỏ khiến ta không biết thất bại đến từ hành vi chưa hoàn thành hay từ thay đổi cấu trúc. Hãy đưa test liên quan về xanh trước, rồi mới tái cấu trúc.

### Chỉ nhìn coverage để đánh giá chất lượng

Coverage cho biết phần code nào đã được thực thi, nhưng không đảm bảo assertion có thể phát hiện kết quả sai. Một test có thể đi qua mọi dòng mà không kiểm tra điều kiện quan trọng.

Chất lượng của test nằm ở khả năng phân biệt hành vi đúng và sai. Với điều kiện biên, có thể thử thay đổi toán tử hoặc giá trị trả về tạm thời để xem test có thất bại đúng nơi dự kiến hay không. Mutation testing cũng có thể cung cấp thêm bằng chứng về sức mạnh của assertion, nhưng không thay thế việc hiểu yêu cầu.

## 8. Giữ vòng lặp ngắn và phản hồi đáng tin cậy

Để TDD phát huy hiệu quả trong dự án Spring, cần tổ chức việc chạy test theo chi phí và phạm vi:

1. Khi viết test nghiệp vụ, chạy đúng test class hoặc method để có phản hồi nhanh.
2. Sau khi triển khai, chạy lại test mới cùng các test gần với thành phần vừa sửa.
3. Sau refactor, chạy lại các test liên quan để xác nhận hành vi được giữ nguyên.
4. Trước khi hoàn tất thay đổi, chạy bộ test có phạm vi đủ rộng để phát hiện hồi quy ở các thành phần bị ảnh hưởng.
5. Với test phụ thuộc database, broker hoặc dịch vụ ngoài, bảo đảm môi trường test được khởi tạo và dọn dẹp ổn định.

Tốc độ phản hồi quan trọng vì người phát triển cần biết thay đổi vừa thực hiện có tác động gì. Tuy vậy, không nên hy sinh tính đại diện của test hạ tầng chỉ để tất cả test đều chạy nhanh. Một test nhanh với fake và một test chậm với database thật trả lời những câu hỏi khác nhau; cả hai có thể cần thiết.

Một vòng TDD hoàn chỉnh thường để lại ba kết quả:

- Một ví dụ thực thi mô tả hành vi cần có.
- Một implementation đáp ứng ví dụ đó.
- Một cấu trúc code dễ đọc và có thể thay đổi mà không phá vỡ hành vi đã xác nhận.

## 9. Khi nào một vòng TDD được xem là hoàn tất?

Một vòng không kết thúc chỉ vì IDE hiển thị màu xanh. Cần hiểu được bằng chứng mà test tạo ra:

- Test mới đã được chạy và có lần Red đúng lý do, hoặc đã xác nhận hành vi vốn đã được hỗ trợ nhưng trước đó chưa có test bảo vệ.
- Implementation làm test mới chuyển xanh.
- Các test liên quan vẫn xanh sau thay đổi.
- Refactor không thay đổi hành vi quan sát được.
- Test có tên, dữ liệu và assertion thể hiện đúng yêu cầu.
- Dependency được cô lập ở mức phù hợp với ranh giới đang kiểm tra.

Nếu test không thể chạy do môi trường, cần phân biệt rõ trạng thái đó với một test đã thất bại vì hành vi. Không nên tuyên bố vòng Red–Green hoàn tất khi chưa có bằng chứng thực thi.

TDD tạo ra một chuỗi quyết định nhỏ: mô tả hành vi, quan sát khoảng trống, triển khai vừa đủ và cải thiện thiết kế. Với Spring Framework Testing, hãy giữ chu trình này ở đúng ranh giới. Quy tắc nghiệp vụ nên được kiểm tra bằng test nhanh; hành vi do container cung cấp cần context Spring; khả năng tích hợp với hạ tầng cần adapter và dịch vụ phù hợp. Khi mỗi test trả lời một câu hỏi rõ ràng, màu đỏ cho biết điều gì còn thiếu, màu xanh cho biết hành vi đã được đáp ứng, và refactor giúp hệ thống tiếp tục dễ phát triển.

