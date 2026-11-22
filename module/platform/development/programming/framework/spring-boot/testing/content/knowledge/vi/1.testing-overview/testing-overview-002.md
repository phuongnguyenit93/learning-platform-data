# Một ca kiểm thử gồm điều kiện ban đầu, hành động và kết quả mong đợi

## 1. Vì sao một ca kiểm thử cần đủ ba phần?

Một **ca kiểm thử (test case)** mô tả một tình huống cụ thể để kiểm chứng hệ thống có hành xử đúng theo yêu cầu hay không. Muốn người khác chạy lại và nhận cùng một kết luận, ca kiểm thử phải trả lời ba câu hỏi:

1. **Điều kiện ban đầu (preconditions / Given / Arrange):** Trước khi thử, dữ liệu, trạng thái, môi trường và các quyền liên quan phải như thế nào?
2. **Hành động (action / When / Act):** Người dùng, chương trình hoặc bài test thực hiện thao tác nào trên hệ thống?
3. **Kết quả mong đợi (expected result / Then / Assert):** Có thể quan sát và kiểm chứng điều gì sau hành động để kết luận đúng hoặc sai?

Công thức dễ nhớ: **Cho trước một trạng thái → thực hiện một hành động → kiểm tra kết quả cụ thể**. Thiếu bất kỳ phần nào, test có thể trở nên mơ hồ: không tái lập được dữ liệu, không biết thao tác cần thử, hoặc chạy xong nhưng không có tiêu chí PASS/FAIL.

Trong Spring Boot, một test case có thể nhắm vào phương thức Java, service, controller HTTP, repository hay luồng tích hợp. Cấu trúc ba phần vẫn giữ nguyên; chỉ có cách thiết lập trạng thái, thực hiện hành động và quan sát kết quả thay đổi.

## 2. Ba thành phần của một test case

| Thành phần | Cần mô tả | Ví dụ: đặt trước hàng trong kho |
| --- | --- | --- |
| **Điều kiện ban đầu** | Trạng thái hệ thống, dữ liệu mẫu, phụ thuộc, cấu hình cần thiết; những gì phải đúng *trước* khi gọi chức năng. | Mặt hàng còn 3 đơn vị, yêu cầu đặt 2 đơn vị; kho test độc lập với các ca khác. |
| **Hành động** | Một thao tác có ý nghĩa nghiệp vụ và dữ liệu đầu vào cụ thể. | Gọi chức năng `reserve(2)`. |
| **Kết quả mong đợi** | Giá trị trả về, trạng thái sau thao tác, tác động phụ hoặc lỗi phải xảy ra; kiểm tra được bằng assertion. | Chấp nhận đặt hàng, kho còn chính xác 1 đơn vị. |

**Điều kiện ban đầu không phải là kết quả mong đợi.** Ví dụ, “kho có 3 sản phẩm” là dữ liệu trước khi thử; “kho còn 1 sản phẩm” là trạng thái phải xác nhận sau hành động. **Hành động cũng không phải là assertion:** gọi API chỉ kích hoạt chức năng, còn kiểm tra mã HTTP, body hoặc trạng thái dữ liệu mới quyết định PASS/FAIL.

Một ca có thể có nhiều assertion nếu chúng cùng chứng minh **một hành vi**. Chẳng hạn một lần đặt hàng thành công cần xác nhận cả kết quả chấp nhận và số lượng tồn sau khi trừ. Không nên trộn nhiều luồng nghiệp vụ độc lập vào một ca vì khi thất bại sẽ khó xác định nguyên nhân.

## 3. Thiết kế tình huống kiểm thử trước khi viết code

Ví dụ yêu cầu nghiệp vụ: “Chỉ cho phép đặt số lượng dương và không vượt quá tồn kho; nếu từ chối thì không thay đổi tồn kho”.

| Mã ca | Điều kiện ban đầu | Hành động | Kết quả mong đợi |
| --- | --- | --- | --- |
| TC-01 — đủ hàng | Tồn kho = 3 | Đặt 2 | Trả về thành công; tồn kho = 1 |
| TC-02 — thiếu hàng | Tồn kho = 1 | Đặt 2 | Trả về thất bại; tồn kho vẫn = 1 |
| TC-03 — số lượng không hợp lệ | Tồn kho = 3 | Đặt 0 | Trả về thất bại; tồn kho vẫn = 3 |
| TC-04 — vừa đủ hàng | Tồn kho = 2 | Đặt 2 | Trả về thành công; tồn kho = 0 |

Các ca trên bao phủ đường đi bình thường, trường hợp bị từ chối và ranh giới. Điều kiện “tồn kho vẫn giữ nguyên” ở ca thất bại rất quan trọng: chỉ kiểm tra giá trị trả về có thể bỏ sót lỗi hệ thống đã trừ kho rồi mới từ chối.

Khi mô tả một test case trong tài liệu hoặc công cụ quản lý test, có thể bổ sung **ID, tên tình huống, yêu cầu liên quan, dữ liệu đầu vào, các bước thực hiện và kết quả thực tế**. Những trường đó hỗ trợ quản lý, nhưng không thay thế ba thành phần cốt lõi.

## 4. Ví dụ Java 17: Arrange – Act – Assert

Ví dụ sau là chương trình Java hoàn chỉnh, không cần Spring Boot hoặc thư viện test. Mỗi ca tạo kho riêng để tránh ảnh hưởng lẫn nhau.

**Tệp: `TestCaseDemo.java`**

~~~java
public class TestCaseDemo {
    static final class Inventory {
        private int stock;

        Inventory(int stock) {
            this.stock = stock;
        }

        boolean reserve(int quantity) {
            if (quantity <= 0 || quantity > stock) {
                return false;
            }
            stock -= quantity;
            return true;
        }

        int remaining() {
            return stock;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        // TC-01 — Arrange: kho có 3, cần đặt 2
        Inventory available = new Inventory(3);

        // Act: gọi chức năng đang kiểm thử
        boolean accepted = available.reserve(2);

        // Assert: cả kết quả trả về và trạng thái sau đó
        check(accepted, "TC-01: phai chap nhan don");
        check(available.remaining() == 1, "TC-01: ton kho phai con 1");
        System.out.println("TC-01: PASS");

        // TC-02 — Arrange: kho chỉ có 1, cần đặt 2
        Inventory insufficient = new Inventory(1);

        // Act
        boolean rejected = insufficient.reserve(2);

        // Assert: từ chối và không trừ kho
        check(!rejected, "TC-02: phai tu choi don");
        check(insufficient.remaining() == 1, "TC-02: ton kho khong duoc doi");
        System.out.println("TC-02: PASS");
    }
}
~~~

Chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

~~~bash
javac TestCaseDemo.java
java TestCaseDemo
~~~

Kết quả chính xác khi hai ca đều đạt:

~~~text
TC-01: PASS
TC-02: PASS
~~~

Hàm `check` ném `AssertionError` nếu điều kiện sai, nên sẽ **không** in dòng PASS của ca bị lỗi. Trong dự án thực tế, JUnit 5 cung cấp các assertion như `assertTrue`, `assertFalse`, `assertEquals` và test runner để quản lý nhiều ca; ví dụ Java thuần ở đây chỉ làm rõ cấu trúc test case.

## 5. Áp dụng vào kiểm thử Spring Boot

Với một controller, ba phần tương ứng với:

- **Arrange:** khởi tạo ứng dụng hoặc phần MVC cần kiểm thử, chuẩn bị request và dữ liệu giả lập, xác định người dùng đăng nhập nếu endpoint yêu cầu xác thực.
- **Act:** gửi request bằng `MockMvc`, `WebTestClient` hoặc một HTTP client phù hợp.
- **Assert:** kiểm tra HTTP status, JSON/body, header và, nếu hợp đồng nghiệp vụ yêu cầu, trạng thái dữ liệu sau request.

Ví dụ Spring Boot 3.x dưới đây kiểm tra một HTTP endpoint trả về tồn kho giả lập. Cần có dependency `spring-boot-starter-web` và `spring-boot-starter-test` trong dự án Spring Boot; hai tệp nằm dưới cùng package.

**Tệp `src/main/java/com/example/testing/StockController.java`:**

~~~java
package com.example.testing;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StockController {
    @GetMapping("/api/stock")
    public Map<String, Object> stock() {
        return Map.of("sku", "SKU-1", "available", 3);
    }
}
~~~

**Tệp `src/test/java/com/example/testing/StockControllerTest.java`:**

~~~java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(StockController.class)
class StockControllerTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void stockEndpointReturnsExpectedResponse() throws Exception {
        // Arrange: MVC test context được khởi tạo;
        // request GET /api/stock không cần body.

        // Act + Assert: gửi request và kiểm tra hợp đồng.
        mockMvc.perform(get("/api/stock"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("SKU-1"))
                .andExpect(jsonPath("$.available").value(3));
    }
}
~~~

Ở ví dụ này:

1. **Điều kiện ban đầu:** `@WebMvcTest(StockController.class)` dựng ngữ cảnh kiểm thử lớp MVC cần thiết; controller được cung cấp và không phụ thuộc database.
2. **Hành động:** `mockMvc.perform(get("/api/stock"))` gửi request giả lập vào tầng MVC.
3. **Kết quả mong đợi:** HTTP 200, trường `sku` bằng `SKU-1`, trường `available` bằng số 3. Một assertion sai khiến test thất bại.

Trong một dự án Gradle Spring Boot đã cấu hình dependency test và task `test`, chạy `./gradlew test` trên macOS/Linux hoặc `gradlew.bat test` trên Windows. Test runner báo PASS/FAIL; đoạn test không tự in các dòng PASS của ví dụ Java thuần.

**Giới hạn ví dụ:** controller cố ý trả về dữ liệu cố định để minh họa hợp đồng HTTP. `@WebMvcTest` kiểm thử một phần MVC, không tự chứng minh việc ghi database hay tích hợp toàn ứng dụng. Với chức năng thật có persistence, hãy chuẩn bị bản ghi test, thực hiện request và xác nhận dữ liệu sau request trong loại kiểm thử có repository/database phù hợp. Nếu dự án bật Spring Security, cần thiết lập ngữ cảnh xác thực/ủy quyền tương ứng; nếu không, request có thể bị từ chối trước khi vào controller.

## 6. Kết quả mong đợi phải đủ rõ để quyết định PASS/FAIL

Một câu như “API hoạt động đúng” không đo được. Nên chuyển thành kiểm chứng quan sát được:

| Mơ hồ | Cụ thể, kiểm chứng được |
| --- | --- |
| “Đặt hàng thành công” | `reserve(2)` trả về `true` và tồn kho giảm từ 3 xuống 1 |
| “API trả về đúng” | HTTP 200; JSON có `sku = "SKU-1"` và `available = 3` |
| “Xử lý lỗi hợp lý” | Yêu cầu vượt tồn trả về từ chối; tồn kho không thay đổi |
| “Dữ liệu lưu đúng” | Sau khi thao tác hoàn tất, truy vấn bản ghi theo ID cho ra các trường đã quy định |

Kết quả mong đợi có thể là **giá trị trả về**, **exception/mã lỗi**, **trạng thái bền vững**, **sự kiện phát ra** hoặc **không xuất hiện tác động phụ**. Chọn điểm quan sát dựa trên hợp đồng nghiệp vụ, tránh ép test phụ thuộc chi tiết cài đặt nội bộ không cần thiết.

Kết quả *thực tế* là giá trị thu được lúc chạy; nó được so với *mong đợi*. Nếu trùng khớp theo mọi assertion cần thiết, ca PASS; nếu sai, ca FAIL và báo vị trí sai. Không viết assertion dựa trên kết quả thực tế vừa nhìn thấy để “làm cho test xanh”.

## 7. Làm sao để ca kiểm thử đáng tin cậy?

**Điều kiện ban đầu phải tái lập được.** Tạo dữ liệu mới, reset fixture hoặc rollback giao dịch khi phù hợp. Tránh giả định rằng database đã có sẵn một bản ghi do người khác tạo. Stub/mock chỉ những phụ thuộc nằm ngoài mục tiêu đang kiểm tra; nếu mock cả logic đang cần chứng minh thì test mất giá trị.

**Hành động phải có đầu vào xác định.** Mô tả rõ tham số, URL, method, body, header, identity và thứ tự các bước cần thiết. Một ca nên tập trung vào một tình huống; các bước chuẩn bị thuộc Arrange, không lẫn với hành động nghiệp vụ đang đo.

**Assertion phải kiểm tra đủ hệ quả quan trọng.** Với thao tác cập nhật, kiểm tra cả response và trạng thái sau đó nếu thuộc phạm vi test. Với ca lỗi, kiểm tra hệ thống có giữ nguyên dữ liệu hay không. Với API, chỉ có HTTP 200 thường là chưa đủ để xác nhận payload đúng.

**Cần độc lập và ổn định.** Tránh dùng dữ liệu chung có thể bị test khác chỉnh sửa, thời gian thực, thứ tự thực thi, mạng ngoài hoặc `Thread.sleep` để làm điều kiện thành công. Khi hành vi bất đồng bộ, chờ theo một điều kiện quan sát được và có timeout xác định thay vì đoán thời gian.

## 8. Các lỗi thường gặp và cách sửa

1. **Thiếu Arrange:** test phụ thuộc dữ liệu có từ lần chạy trước. **Sửa:** tạo fixture ngay trong test/thiết lập test, hoặc cô lập môi trường.
2. **Chỉ Act mà không Assert:** chỉ gọi phương thức hoặc endpoint nên lỗi logic vẫn cho test “xanh”. **Sửa:** xác nhận ít nhất một kết quả cụ thể gắn với yêu cầu.
3. **Assert thiếu:** chỉ kiểm tra `accepted == true` nhưng không kiểm tra tồn kho. **Sửa:** xác nhận cả trạng thái hậu điều kiện khi đó là một phần hợp đồng.
4. **Gộp nhiều tình huống không liên quan:** ca dài, khó biết lỗi ở đâu. **Sửa:** chia thành các test case có tên thể hiện hành vi, mỗi ca có Arrange/Act/Assert riêng.
5. **Mong đợi không xác định:** viết “phản hồi nhanh”, “thành công”, “hợp lý” mà không có tiêu chí. **Sửa:** xác định trạng thái, dữ liệu, giới hạn thời gian hoặc loại lỗi đo được.
6. **Nhầm mức kiểm thử:** dùng `@WebMvcTest` rồi kết luận nghiệp vụ đã ghi vào database. **Sửa:** chọn unit, web slice hay integration test theo loại kết quả cần chứng minh.

## 9. Checklist tự kiểm trước khi chốt test case

- [ ] Tên/ID cho biết rõ hành vi hoặc tình huống.
- [ ] Điều kiện ban đầu chỉ ra dữ liệu, trạng thái và phụ thuộc cần có.
- [ ] Hành động mô tả đúng một thao tác kiểm thử với đầu vào cụ thể.
- [ ] Kết quả mong đợi đo được bằng assertion, bao gồm tác động phụ quan trọng.
- [ ] Có trường hợp hợp lệ, không hợp lệ và giá trị biên phù hợp với quy tắc nghiệp vụ.
- [ ] Chạy lại độc lập không cần trạng thái tồn dư từ ca khác.
- [ ] Khi thất bại, thông báo assertion giúp phân biệt giá trị thực tế và mong đợi.

**Ghi nhớ:** một ca kiểm thử tốt không chỉ “chạy được”. Nó dựng được hoàn cảnh cần thử (**Arrange/Given**), thực hiện đúng thao tác (**Act/When**) và cung cấp bằng chứng rõ ràng cho kết luận (**Assert/Then**).