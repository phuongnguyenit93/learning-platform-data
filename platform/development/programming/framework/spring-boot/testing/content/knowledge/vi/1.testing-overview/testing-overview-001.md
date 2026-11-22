# Kiểm thử tự động giải quyết vấn đề gì khi phát triển ứng dụng Spring Boot?

## 1. Vấn đề cốt lõi: thay đổi mã nguồn luôn kéo theo rủi ro

Một ứng dụng Spring Boot thường có nhiều phần phối hợp: HTTP controller tiếp nhận yêu cầu, service xử lý nghiệp vụ, repository truy cập cơ sở dữ liệu, Spring quản lý dependency injection và cấu hình, còn các hệ thống bên ngoài cung cấp dịch vụ bổ sung. Một thay đổi nhỏ ở một phần có thể làm sai hành vi của phần khác.

Ví dụ, nhóm phát triển sửa cách tính phí giao hàng để miễn phí khi đơn hàng đạt 500.000 đồng. Nếu chỉ mở ứng dụng, gọi thử một đơn hàng 600.000 đồng rồi thấy kết quả đúng, nhóm vẫn có thể bỏ sót các lỗi: đơn hàng 499.999 đồng bị miễn phí; số tiền âm không bị từ chối; API trả sai mã HTTP; hoặc một refactor sau đó làm hỏng quy tắc vừa sửa.

**Kiểm thử tự động** là việc viết các chương trình kiểm tra đầu vào, hành vi và kết quả mong đợi; những chương trình đó được chạy lặp lại bằng công cụ như JUnit, Spring Test, Maven/Gradle và pipeline CI. Khi kết quả thực tế khác kết quả mong đợi, phép thử báo lỗi. Mục tiêu không chỉ là “có nhiều test”, mà là tạo **phản hồi sớm, lặp lại được và đủ tin cậy** về những hành vi quan trọng.

## 2. Những vấn đề kiểm thử tự động trực tiếp giải quyết

### 2.1. Phát hiện lỗi logic trước khi lỗi đến người dùng

- **Vấn đề:** Lập trình viên dễ bỏ sót điều kiện biên, nhánh ngoại lệ, dữ liệu rỗng hoặc tính toán sai khi chỉ chạy thử vài tình huống bằng tay.
- **Kiểm thử giúp gì:** Mỗi test xác định rõ đầu vào, thao tác và kết quả mong đợi. Bộ test có thể kiểm tra cả trường hợp bình thường lẫn giá trị ngay sát ngưỡng, dữ liệu không hợp lệ và lỗi phụ thuộc.
- **Ví dụ:** Quy tắc “từ 500.000 đồng thì miễn phí giao hàng” nên được kiểm tra ít nhất với 499.999, 500.000, 500.001 và số tiền âm. Giá trị 500.000 là trường hợp biên dễ gây lỗi `>` thay vì `>=`.

### 2.2. Ngăn lỗi hồi quy khi sửa lỗi, nâng cấp hoặc refactor

- **Vấn đề:** Sửa một hàm, đổi cấu trúc package, thay repository hay nâng cấp thư viện có thể làm hỏng tính năng vốn chạy đúng.
- **Kiểm thử giúp gì:** Các test đã viết trở thành “hàng rào hồi quy”: sau mỗi thay đổi, bộ kiểm thử chạy lại những hành vi cũ. Nếu hành vi bị phá vỡ, nhóm biết sớm trước khi merge hoặc phát hành.
- **Ví dụ:** Khi chuyển công thức tính phí sang một service mới, những test về ngưỡng phí vẫn phải xanh. Nếu không, refactor chưa bảo toàn hợp đồng nghiệp vụ.

### 2.3. Phát hiện lỗi liên kết giữa các thành phần Spring Boot

- **Vấn đề:** Mã Java có thể biên dịch nhưng ứng dụng vẫn khởi động lỗi do thiếu bean, injection không khớp, cấu hình sai, điều kiện khởi tạo bean không thỏa hoặc các thành phần không tích hợp được với nhau.
- **Kiểm thử giúp gì:** Test có khởi tạo Spring context, chẳng hạn `@SpringBootTest`, có thể phát hiện một số lỗi cấu hình và wiring trong môi trường kiểm thử. Test theo từng lớp chức năng (test slice) kiểm tra một phần cấu hình cần thiết mà không phải nạp toàn bộ ứng dụng.
- **Giới hạn:** Một test chỉ khởi động context thành công chưa chứng minh API và nghiệp vụ đúng. Cần assertion thực sự kiểm tra hành vi.

### 2.4. Bảo vệ hợp đồng HTTP và xử lý lỗi

- **Vấn đề:** Controller có thể trả đúng dữ liệu trong service nhưng sai URL, tham số, JSON, HTTP status, validation hoặc quy tắc ủy quyền.
- **Kiểm thử giúp gì:** Test tầng web có thể gửi request giả lập bằng `MockMvc`, rồi kiểm tra status, response body, content type và thông điệp lỗi. `@WebMvcTest` phù hợp để tập trung vào MVC; cộng tác viên của controller thường được thay bằng mock hoặc cấu hình phù hợp.
- **Ví dụ:** `POST /orders` với dữ liệu không hợp lệ phải trả lỗi 400 theo hợp đồng đã thiết kế; API cần bảo vệ không được vô tình trả 200 cho yêu cầu chưa xác thực.

### 2.5. Kiểm tra truy vấn, ánh xạ dữ liệu và ranh giới tích hợp

- **Vấn đề:** Repository có thể truy vấn sai, ánh xạ entity sai, transaction không hoạt động như kỳ vọng hoặc kết quả khác nhau giữa môi trường máy cá nhân và môi trường triển khai.
- **Kiểm thử giúp gì:** `@DataJpaTest` tập trung kiểm tra lớp JPA/repository. Test tích hợp có thể dùng database thử nghiệm được quản lý độc lập, ví dụ qua Testcontainers, để kiểm tra hành vi gần với hệ quản trị dữ liệu thật.
- **Lưu ý:** Cơ sở dữ liệu in-memory không phải lúc nào cũng có ngữ nghĩa SQL giống database production. Hãy chọn môi trường test theo rủi ro cần xác minh.

### 2.6. Giảm kiểm tra lặp đi lặp lại và rút ngắn vòng phản hồi

- **Vấn đề:** Mỗi lần sửa code, việc mở ứng dụng, nhập dữ liệu và kiểm tra thủ công nhiều luồng mất thời gian, khó lặp lại đồng nhất và dễ bỏ sót.
- **Kiểm thử giúp gì:** Bộ test có thể chạy bằng một lệnh sau mỗi lần sửa hoặc tự chạy trong CI khi tạo pull request. Nếu pipeline được cấu hình để chặn khi test thất bại, lỗi được phát hiện trước khi merge/deploy.
- **Kết quả:** Phần lớn phép kiểm tra có tính quyết định được tự động hóa; thời gian kiểm thử thủ công được dành cho những tình huống khó mô phỏng như trải nghiệm người dùng hoặc khám phá yêu cầu mới.

### 2.7. Ghi lại kỳ vọng nghiệp vụ để làm việc nhóm

Một test có tên rõ ràng và assertion tốt cho biết hệ thống **phải hành xử thế nào**. Ví dụ, tên `freeShippingAtThreshold` cho người đọc biết đúng tại ngưỡng thì phí phải bằng 0. Khi yêu cầu thay đổi, nhóm có thể cập nhật test cùng với quy tắc mới. Test giúp trao đổi về yêu cầu và làm cơ sở cho review, nhưng không thay thế đặc tả nghiệp vụ được thống nhất.

## 3. Chọn đúng cấp độ kiểm thử để giải quyết đúng rủi ro

| Loại kiểm thử | Câu hỏi nó trả lời | Cách làm thường gặp trong Spring Boot | Đặc tính |
|---|---|---|---|
| Unit test | Một hàm/service có cho kết quả đúng với các đầu vào đã chọn không? | JUnit 5, assertion, Mockito khi có phụ thuộc cần cô lập; thường **không** tạo Spring context | Nhanh, chỉ ra lỗi logic khá chính xác |
| Test theo lát cắt (slice) | Một lớp chức năng có tuân thủ hợp đồng không? | `@WebMvcTest` + `MockMvc`, `@DataJpaTest` | Nhẹ hơn full context; tập trung MVC hoặc JPA |
| Integration test | Các thành phần và phụ thuộc thực sự phối hợp đúng không? | `@SpringBootTest`, database thử nghiệm, Testcontainers khi cần | Bao phủ ranh giới hệ thống nhưng thường chậm hơn |
| End-to-end test | Luồng sử dụng từ điểm vào đến đầu ra cuối cùng có hoạt động không? | Gọi API qua HTTP hoặc chạy trình duyệt với môi trường được kiểm soát | Bao phủ rộng, chi phí và độ nhạy với môi trường cao hơn |

Không cần viết tất cả các cấp độ cho mọi trường hợp. Quy tắc nghiệp vụ thuần túy nên ưu tiên unit test. Với hợp đồng API, thêm web test. Với truy vấn và việc ghép nhiều thành phần, thêm integration test. Dành end-to-end test cho những luồng đặc biệt quan trọng, vì chúng thường chậm và khó chẩn đoán hơn.

**Phân biệt hai ý thường bị nhầm:** `@SpringBootTest` giúp nạp application context, nhưng mặc định không có nghĩa là một HTTP server thực đã được mở. Muốn kiểm tra qua cổng HTTP thật, cần cấu hình môi trường web phù hợp, ví dụ `webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT`.

## 4. Ví dụ Java 17+: kiểm chứng quy tắc phí giao hàng

Giả sử ứng dụng có quy tắc:
- Tổng tiền nhỏ hơn 0 là không hợp lệ.
- Từ 500.000 đồng trở lên, phí giao hàng bằng 0.
- Dưới 500.000 đồng, phí giao hàng là 30.000 đồng.

**Mã production** — tệp `src/main/java/com/example/demo/ShippingFeeService.java`:

```java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class ShippingFeeService {
    public int calculate(int subtotal) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }
        return subtotal >= 500_000 ? 0 : 30_000;
    }
}
```

**Mã kiểm thử** — tệp `src/test/java/com/example/demo/ShippingFeeServiceTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingFeeServiceTest {
    private final ShippingFeeService service = new ShippingFeeService();

    @Test
    void chargesShippingBelowThreshold() {
        assertEquals(30_000, service.calculate(499_999));
    }

    @Test
    void freeShippingAtThreshold() {
        assertEquals(0, service.calculate(500_000));
    }

    @Test
    void freeShippingAboveThreshold() {
        assertEquals(0, service.calculate(500_001));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> service.calculate(-1));
    }
}
```

Hai tệp là các lớp Java hoàn chỉnh trong package `com.example.demo`, dùng được trong một **dự án Spring Boot đã cấu hình Java 17+ và dependency kiểm thử `spring-boot-starter-test`**. Test dùng JUnit Jupiter; nó tạo service trực tiếp, vì vậy không cần khởi động Spring context chỉ để kiểm tra một phép tính.

Chạy bằng công cụ build của dự án:
- Gradle wrapper trên Linux/macOS: `./gradlew test`; trên Windows: `.\gradlew.bat test`.
- Maven wrapper trên Linux/macOS: `./mvnw test`; trên Windows: `.\mvnw.cmd test`.

Khi cả bốn assertion đúng, bốn test này đạt. Không nên dự đoán một chuỗi stdout duy nhất vì output của Maven/Gradle phụ thuộc phiên bản, cấu hình logging và runner. Nếu ai đó vô tình đổi `>= 500_000` thành `> 500_000`, test `freeShippingAtThreshold` sẽ thất bại và chỉ rõ hành vi bị hồi quy.

Ví dụ mới xác minh quy tắc tính phí. Nó **chưa** xác minh URL, JSON, xác thực, truy vấn database hoặc cấu hình bean; những rủi ro đó cần test ở các cấp độ tương ứng.

## 5. Đưa kiểm thử vào quy trình phát triển

Một vòng phát triển thực tế có thể diễn ra như sau:

1. **Xác định hành vi cần bảo vệ.** Viết các trường hợp thành công, thất bại và giá trị biên từ yêu cầu nghiệp vụ. Đầu vào và kết quả mong đợi cần cụ thể.
2. **Viết test tại cấp độ thấp nhất đủ chứng minh hành vi.** Đối với công thức phí, viết unit test; đối với URL và HTTP status, viết web test; đối với SQL và transaction, viết integration test.
3. **Chạy lại khi sửa code.** Một lần test đỏ cần được điều tra: có thể là lỗi production, assertion lỗi thời do yêu cầu thay đổi, hoặc môi trường test không ổn định.
4. **Tự động chạy trong CI.** Pipeline dùng cùng lệnh build như nhóm phát triển và báo thất bại khi test không đạt; nhóm có thể thiết lập điều kiện merge theo kết quả đó.
5. **Bảo trì bộ test cùng mã nguồn.** Khi hợp đồng thay đổi có chủ đích, cập nhật test và code dựa trên yêu cầu mới. Giữ các test quan trọng độc lập, dễ đọc và đáng tin.

Ví dụ chọn bài test theo loại thay đổi:

| Thay đổi | Rủi ro chính | Test nên ưu tiên |
|---|---|---|
| Sửa công thức giảm giá/phí vận chuyển | Điều kiện biên và phép tính sai | Unit test các nhánh và ngưỡng |
| Thêm validation cho request DTO | API chấp nhận dữ liệu sai hoặc trả sai status | Web MVC test với request hợp lệ/không hợp lệ |
| Sửa query lấy đơn hàng | Lọc, sắp xếp, quan hệ entity sai | Repository integration test |
| Thêm bean hoặc chỉnh profile/cấu hình | Context không khởi tạo hoặc dependency thiếu | Context/integration test với profile liên quan |
| Thay đổi kết nối với dịch vụ ngoài | Sai request, timeout, lỗi phản hồi hoặc mapping | Contract/integration test với fake, stub hoặc môi trường kiểm thử phù hợp |

## 6. Kiểm thử tự động không giải quyết được mọi vấn đề

- **Test chỉ kiểm tra những điều được mô tả trong test.** Test xanh không chứng minh không còn lỗi; nếu kỳ vọng hoặc dữ liệu test thiếu thì lỗi vẫn lọt.
- **Mock quá mức dễ tạo niềm tin giả.** Mock một dependency có thể tốt cho unit test, nhưng chỉ mock mà không có test tích hợp sẽ không phát hiện lỗi wiring, SQL hoặc giao tiếp thực.
- **Test dễ dao động (flaky) làm mất giá trị cảnh báo.** Phụ thuộc giờ hệ thống, thứ tự chạy, dữ liệu dùng chung, mạng thật hay phép chờ cố định có thể khiến cùng code lúc xanh lúc đỏ. Cần dữ liệu độc lập, đồng hồ giả lập khi cần và môi trường kiểm soát được.
- **Chạy full context cho mọi phép tính khiến suite chậm.** Test cần Spring context chỉ khi rủi ro cần Spring. Tách unit test nhanh và integration test có chi phí cao hơn.
- **Chỉ kiểm tra “happy path” là chưa đủ.** Phải cân nhắc giá trị biên, lỗi validation, ngoại lệ, transaction rollback và kiểm soát truy cập tùy tính năng.
- **Không thay thế hoàn toàn kiểm thử thủ công, review, giám sát production hay kiểm tra hiệu năng/bảo mật.** Mỗi hoạt động phát hiện một nhóm rủi ro khác nhau.

## 7. Khi nào có thể nói bộ test đang tạo ra giá trị?

Hãy tự kiểm tra:
- Những quy tắc nghiệp vụ quan trọng có test với trường hợp bình thường và điều kiện biên chưa?
- Khi sửa code làm sai một hành vi từng đúng, liệu test liên quan có đỏ không?
- Với thay đổi ở controller, repository hoặc wiring, có test ở đúng ranh giới tương ứng không?
- Developer và CI có chạy test thường xuyên; lỗi có hiển thị rõ và dễ tái hiện không?
- Các test có độc lập, đủ nhanh và ít dao động để mọi người tin vào tín hiệu đỏ/xanh không?

**Kết luận:** Kiểm thử tự động giúp Spring Boot phát triển an toàn hơn bằng cách phát hiện sai lệch hành vi sớm, ngăn hồi quy, kiểm tra hợp đồng giữa các thành phần và rút ngắn vòng phản hồi sau thay đổi. Giá trị của nó nằm ở **đúng rủi ro được kiểm chứng bằng assertion có ý nghĩa**, kết hợp nhiều cấp độ test phù hợp và được chạy đều đặn trong quy trình phát triển.