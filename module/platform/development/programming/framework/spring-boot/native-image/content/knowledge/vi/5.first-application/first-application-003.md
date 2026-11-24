# Tạo một endpoint hoặc tác vụ có đầu vào, đầu ra dễ xác nhận

## 1. Mục tiêu của ứng dụng đầu tiên

Khi bắt đầu module **SPRING_BOOT_NATIVE_IMAGE**, nên chọn một chức năng nhỏ có **đầu vào xác định, đầu ra dự đoán được** để kiểm tra cùng một hành vi trên Spring Boot chạy bằng JVM và trên **GraalVM Native Image**. Chúng ta sẽ xây dựng một REST endpoint tính tổng tiền đơn hàng. Ví dụ không cần cơ sở dữ liệu, tài khoản hay dịch vụ ngoài, nên dễ cô lập lỗi từ mã ứng dụng, Spring AOT, quá trình biên dịch native và môi trường chạy.

Sau bài này, bạn có thể:

1. Tạo một Spring Boot API nhận hai tham số số nguyên và trả JSON chứa phép tính, với quy tắc kiểm tra đầu vào rõ ràng.
2. Chạy API trên JVM, kiểm tra kết quả đúng và trường hợp lỗi bằng `curl` hoặc test tự động.
3. Build cùng ứng dụng thành executable native thông qua Spring AOT và GraalVM Native Image với Maven hoặc Gradle.
4. Chạy lại đúng bộ kiểm thử trên executable native, so sánh kết quả một cách có kiểm soát.
5. Ghi nhận thời gian khởi động và bộ nhớ trước khi mở rộng sang reflection, resource, container và vận hành production.

```mermaid
flowchart LR
    A[HTTP GET + tham số] --> B[Spring MVC Controller]
    B --> C[Kiểm tra dữ liệu]
    C --> D[Tính tổng an toàn]
    D --> E[JSON có cấu trúc]
    E --> F[Test JVM và native]
```

**Hợp đồng ví dụ:** yêu cầu `GET /api/orders/quote?unitPrice=12000&quantity=3` trả HTTP 200 với `unitPrice=12000`, `quantity=3`, `total=36000`. Số tiền trong ví dụ là **đơn vị nguyên nhỏ nhất do hệ thống quy ước**, không dùng số thực để mô phỏng tiền. Endpoint chỉ tính toán; không tạo giao dịch thanh toán.

## 2. Tạo project Spring Boot tối thiểu

Bạn có thể tạo project bằng Spring Initializr hoặc công cụ tạo project tương đương, chọn phiên bản Spring Boot được GraalVM và Native Build Tools hỗ trợ, Java phù hợp và dependency:

- **Spring Web**: xây dựng REST controller, ánh xạ request và trả JSON.
- **Spring Boot Test**: viết test kiểm tra JSON và HTTP status.

Không bắt buộc Spring Data, database, security hoặc templating cho ví dụ này. Với Maven, hãy xác nhận project có Spring Boot Maven Plugin và cấu hình native profile/Native Build Tools đúng phiên bản. Với Gradle, dùng Spring Boot plugin và GraalVM Native Build Tools plugin tương thích. Lệnh build ở các phần sau giả định project đã có cấu hình đó.

Cấu trúc minh họa:

```text
src/
  main/
    java/com/example/quote/
      QuoteApplication.java
      QuoteController.java
    resources/
      application.properties
  test/
    java/com/example/quote/
      QuoteControllerTest.java
```

File `QuoteApplication.java`:

```java
package com.example.quote;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteApplication {
    public static void main(String[] args) {
        SpringApplication.run(QuoteApplication.class, args);
    }
}
```

Đặt controller cùng package hoặc package con để cơ chế component scanning mặc định phát hiện đúng. Nếu đổi package, phải kiểm tra lại phạm vi quét thành phần.

## 3. Thiết kế endpoint với kết quả có thể kiểm tra ngay

Tạo `QuoteController.java`:

```java
package com.example.quote;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class QuoteController {

    @GetMapping("/api/orders/quote")
    public Quote quote(
            @RequestParam long unitPrice,
            @RequestParam long quantity) {

        if (unitPrice < 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "unitPrice must be >= 0");
        }
        if (quantity <= 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "quantity must be > 0");
        }

        final long total;
        try {
            total = Math.multiplyExact(unitPrice, quantity);
        } catch (ArithmeticException ex) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "total exceeds supported range", ex);
        }

        return new Quote(unitPrice, quantity, total);
    }

    public record Quote(long unitPrice, long quantity, long total) {}
}
```

Ở đây:

- `@RestController` biến giá trị trả về thành HTTP response được serialize, thông thường là JSON khi có Jackson qua Spring Web.
- `@GetMapping` chỉ định URL và HTTP method. `@RequestParam` ánh xạ query string vào số nguyên `long`.
- `Math.multiplyExact` ném `ArithmeticException` khi phép nhân vượt phạm vi `long`, tránh âm thầm tràn số.
- `ResponseStatusException` dùng HTTP 400 cho đầu vào không hợp lệ. Cấu trúc JSON lỗi có thể khác giữa các phiên bản/cấu hình Spring Boot; bài học chỉ yêu cầu xác minh **HTTP status** của trường hợp lỗi.
- Java `record` thể hiện kiểu kết quả bất biến, thuận tiện cho serialization. Chương trình dùng Java phiên bản hỗ trợ `record`.

Chọn `long` thay vì `double` để ví dụ có phép tính chính xác trong phạm vi số nguyên. Với hệ thống tiền tệ thực, cần định nghĩa currency, đơn vị tối thiểu, quy tắc làm tròn và giới hạn nghiệp vụ; ví dụ này chỉ tập trung vào kiểm thử đường dữ liệu.

### Ví dụ đầu vào và đầu ra

| Request | Kết quả mong đợi | HTTP status |
|---|---|---|
| `?unitPrice=12000&quantity=3` | `{"unitPrice":12000,"quantity":3,"total":36000}` | 200 |
| `?unitPrice=0&quantity=2` | `{"unitPrice":0,"quantity":2,"total":0}` | 200 |
| `?unitPrice=-1&quantity=2` | Lỗi đầu vào | 400 |
| `?unitPrice=5&quantity=0` | Lỗi đầu vào | 400 |
| `?unitPrice=9223372036854775807&quantity=2` | Lỗi tràn số | 400 |
| `?unitPrice=abc&quantity=2` | Lỗi chuyển kiểu tham số | 400 |
| Thiếu `quantity` | Thiếu tham số bắt buộc | 400 |

Không nên kiểm tra bằng so sánh nguyên văn toàn bộ JSON vì thứ tự trường và định dạng whitespace không phải bản chất hợp đồng. Kiểm tra theo tên trường và giá trị sẽ bền vững hơn.

## 4. Chạy trên JVM và kiểm tra thủ công

Chạy từ thư mục project Maven:

```bash
./mvnw spring-boot:run
```

Hoặc Gradle:

```bash
./gradlew bootRun
```

Nếu dùng Windows, thay `./mvnw` bằng `mvnw.cmd` hoặc `./gradlew` bằng `gradlew.bat` trong terminal tương ứng.

Khi ứng dụng sẵn sàng trên cổng mặc định 8080, gọi:

```bash
curl -i "http://localhost:8080/api/orders/quote?unitPrice=12000&quantity=3"
```

Phần quan trọng của phản hồi:

```http
HTTP/1.1 200

{"unitPrice":12000,"quantity":3,"total":36000}
```

Các header thực tế, định dạng lỗi và thứ tự trường có thể khác. Thử tiếp một trường hợp hợp lệ và hai trường hợp lỗi:

```bash
curl -i "http://localhost:8080/api/orders/quote?unitPrice=0&quantity=2"
curl -i "http://localhost:8080/api/orders/quote?unitPrice=-1&quantity=2"
curl -i "http://localhost:8080/api/orders/quote?unitPrice=5&quantity=0"
```

Kết quả mong đợi lần lượt là 200, 400 và 400. Nếu cổng 8080 bị chiếm, cấu hình `server.port` hoặc dừng ứng dụng khác; khi so sánh JVM/native, ghi lại chính xác URL được dùng.

## 5. Viết kiểm thử hợp đồng có thể tái sử dụng

Kiểm thử tự động giúp phát hiện lỗi logic trước khi mất thời gian build native. Ví dụ sau sử dụng `MockMvc` trên ứng dụng Spring Boot và JUnit 5.

```java
package com.example.quote;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QuoteControllerTest {
    @Autowired MockMvc mvc;

    @Test
    void computesTotal() throws Exception {
        mvc.perform(get("/api/orders/quote")
                .param("unitPrice", "12000")
                .param("quantity", "3"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.unitPrice").value(12000))
            .andExpect(jsonPath("$.quantity").value(3))
            .andExpect(jsonPath("$.total").value(36000));
    }

    @Test
    void rejectsNegativePrice() throws Exception {
        mvc.perform(get("/api/orders/quote")
                .param("unitPrice", "-1")
                .param("quantity", "2"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsOverflow() throws Exception {
        mvc.perform(get("/api/orders/quote")
                .param("unitPrice", Long.toString(Long.MAX_VALUE))
                .param("quantity", "2"))
            .andExpect(status().isBadRequest());
    }
}
```

**Lưu ý về version:** tùy bản Spring Boot, package import và starter test cho MockMvc có thể thay đổi. Cần đối chiếu API với phiên bản Spring Boot của dự án; nguyên tắc là giữ cùng request và expected response cho cả JVM và native.

Chạy Maven test:

```bash
./mvnw test
```

Hoặc:

```bash
./gradlew test
```

Các bài test MockMvc chứng minh đường Spring MVC và logic ứng dụng trong môi trường kiểm thử JVM. Chúng **không thay thế** việc gọi HTTP thật trên executable native sau khi biên dịch.

## 6. Biên dịch thành GraalVM Native Image

Spring AOT phân tích bean configuration, tạo mã và Runtime Hints hỗ trợ các cơ chế động; GraalVM Native Image sau đó phân tích reachability và tạo executable máy. Với controller đơn giản này, cấu hình Spring chuẩn thường đã có hỗ trợ AOT, nên không cần khai báo reflection hint thủ công chỉ vì có `@RestController` hoặc `record` trả JSON.

### Maven

Với project có native profile và GraalVM Native Build Tools:

```bash
./mvnw -Pnative native:compile
```

### Gradle

Với project có plugin Native Build Tools phù hợp:

```bash
./gradlew nativeCompile
```

Biên dịch native thường tốn thời gian và RAM build nhiều hơn biên dịch JAR thông thường. Kiểm tra **log build hoàn tất**, exit code và file executable được tạo mới, thay vì chỉ thấy bước `processAot` thành công.

Artifact điển hình nằm ở `target/` với Maven hoặc `build/native/nativeCompile/` với Gradle; tên file phụ thuộc `artifactId`, tên project và cấu hình. Trên Windows, executable thường có đuôi `.exe` và yêu cầu MSVC/Windows SDK tương thích; trên Linux cần toolchain phù hợp môi trường Linux. Không sao chép executable Windows sang image Linux để chạy trực tiếp.

### Chạy native và lặp lại request

Giả sử file build tên `quote` trong `target/` trên Linux:

```bash
./target/quote
```

Ở terminal khác:

```bash
curl -i "http://localhost:8080/api/orders/quote?unitPrice=12000&quantity=3"
curl -i "http://localhost:8080/api/orders/quote?unitPrice=-1&quantity=2"
curl -i "http://localhost:8080/api/orders/quote?unitPrice=9223372036854775807&quantity=2"
```

Kết quả mong đợi lần lượt là HTTP 200 với `total=36000`, HTTP 400 và HTTP 400. Hãy dừng phiên bản JVM trước khi chạy native trên cùng cổng 8080, hoặc chọn hai cổng khác nhau. Nếu gặp 404, trước hết xác minh đúng executable và URL; nếu gặp lỗi khởi động, xem profile và log.

## 7. Kiểm thử JVM và native bằng cùng một bảng đối chiếu

| Tiêu chí | JVM | Native | Cách kết luận |
|---|---|---|---|
| HTTP status của request hợp lệ | 200 | 200 | PASS nếu bằng nhau |
| JSON `unitPrice`, `quantity`, `total` | Giá trị dự kiến | Giá trị dự kiến | PASS nếu cùng nội dung |
| Giá âm hoặc quantity bằng 0 | 400 | 400 | PASS nếu giữ quy tắc validation |
| Phép nhân tràn | 400 | 400 | PASS nếu không có kết quả sai |
| Tham số sai kiểu hoặc thiếu | 400 | 400 | PASS nếu xử lý lỗi phù hợp |
| Ứng dụng khởi động | Không lỗi | Không lỗi | PASS khi server thực sự sẵn sàng |
| Thời gian khởi động và RSS | Đo | Đo | Thông số hiệu năng, không phải đúng/sai hợp đồng |

Bảng này là **mẫu tiêu chí**, không phải số liệu benchmark đã đo. Với test tích hợp, bạn có thể chạy một script gọi `curl` và phân tích JSON bằng công cụ phù hợp trên cả hai biến thể. Khi chỉ đổi JVM sang native, không sửa phép tính hay bộ dữ liệu kiểm tra.

Khi kiểm thử container native, dùng chính các request như trên sau khi map cổng và cấu hình môi trường. Nếu muốn thêm trường hợp resource hoặc reflection để thực hành compatibility, hãy tách thành bước mở rộng riêng để luôn có một baseline đơn giản hoạt động đúng.

## 8. Đánh giá startup và bộ nhớ theo cách có thể tái hiện

Mục tiêu module là đánh giá lợi ích về thời gian khởi động và bộ nhớ, nhưng phải tách **tính đúng chức năng** khỏi **hiệu năng**. Sau khi kết quả JVM/native giống nhau:

1. Chạy từng biến thể trên cùng máy hoặc môi trường được mô tả rõ; tránh hai ứng dụng cùng tranh CPU và RAM.
2. Xác định startup là khoảng thời gian từ bắt đầu process đến khi endpoint sẵn sàng phục vụ, không chỉ thời điểm một dòng log xuất hiện.
3. Đo RSS/working set khi idle ổn định và dưới tải tương đương. Bộ nhớ peak của quá trình **build** là số đo riêng, không phải bộ nhớ cần cho ứng dụng native khi chạy.
4. Lặp phép đo nhiều lần, ghi phiên bản JDK/GraalVM, plugin, OS, cấu hình heap, profile và tải để giải thích kết quả.
5. Quan sát latency/throughput cùng với RSS: một ứng dụng khởi động nhanh chưa chắc đáp ứng mọi kịch bản tải tốt hơn.

Mẫu bảng ghi kết quả, để trống cho số đo thực tế:

| Chỉ số | Spring Boot JVM | Spring Boot Native |
|---|---:|---:|
| Startup đến khi sẵn sàng | … ms | … ms |
| RSS sau khi ổn định | … MiB | … MiB |
| Peak RSS khi 100 request/giây | … MiB | … MiB |
| p95 latency ở cùng tải | … ms | … ms |
| Peak RAM của quá trình build | … MiB | … MiB |

Không kết luận “Native Image tiết kiệm x% RAM” khi chưa có dữ liệu và phương pháp đo. Tùy application, native image có thể giảm đáng kể thời gian startup, nhưng cũng có trade-off về build time, kích thước artifact, throughput hoặc hỗ trợ thư viện.

## 9. Xử lý một số lỗi thường gặp

| Triệu chứng | Bước cần kiểm tra |
|---|---|
| HTTP 404 tại `/api/orders/quote` | Package controller có được Spring scan; URL và cổng có đúng |
| HTTP 400 với `unitPrice=abc` | Đây là kết quả mong đợi vì Spring không chuyển được tham số sang `long` |
| HTTP 500 khi nhân số rất lớn | Kiểm tra có sử dụng `Math.multiplyExact` và catch để chuyển sang HTTP 400 |
| AOT lỗi khởi tạo bean | Kiểm tra `@SpringBootApplication`, cấu hình component, profile, properties |
| Native build thiếu compiler/linker | Kiểm tra GraalVM, C toolchain/MSVC, OS/kiến trúc target |
| Native chạy lỗi reflection/resource | Kiểm tra Spring AOT hints, thư viện liên quan và stack trace; đừng thêm metadata tràn lan |
| Port 8080 đã được dùng | Dừng phiên bản đang chạy hoặc đổi `server.port` |
| Kết quả native khác JVM | Kiểm tra cùng code commit, cấu hình, input và version; tái hiện bằng test nhỏ nhất |

Nếu ứng dụng native build thành công nhưng chỉ một luồng nghiệp vụ lỗi, đó là vấn đề tương thích runtime cần điều tra riêng. Biên dịch thành công không đồng nghĩa mọi đường gọi và resource đều hoạt động, nhất là khi project bắt đầu sử dụng reflection tùy biến, dynamic proxy, JNI hoặc các thư viện tạo bytecode lúc runtime.

## 10. Mở rộng bài tập

Sau khi bản tối thiểu hoạt động, có thể tăng độ khó mà vẫn giữ kết quả dễ xác minh:

- Bổ sung endpoint `/api/orders/discount` nhận `unitPrice`, `quantity` và `discountPercent` nguyên trong khoảng 0–100; kiểm tra tràn số và quy tắc làm tròn.
- Đọc một file `templates/receipt.txt` qua classpath rồi trả nội dung; xác minh resource được đóng gói trong executable native.
- Tạo phương án `@ConfigurationProperties` cho giới hạn `maxQuantity`, quan sát ảnh hưởng của property/configuration khi build và chạy native.
- Đóng gói native executable vào Linux container bằng pipeline Linux, sau đó chạy cùng bảng request trên cổng được publish.

Với mỗi bước mở rộng, bổ sung test JVM và kiểm thử native tương ứng; ghi rõ thay đổi nào yêu cầu Spring Runtime Hints hoặc metadata của GraalVM. Không giả định việc có thêm file resource hoặc gọi reflection động luôn tự được phân tích.

## 11. Câu hỏi tự kiểm tra

1. Vì sao nên chọn endpoint có input/output xác định trước khi triển khai database và dependency bên ngoài?
2. Tại sao `Math.multiplyExact` hữu ích hơn phép `unitPrice * quantity` trong trường hợp test này?
3. Test MockMvc chạy trên JVM có đủ để kết luận executable native phục vụ HTTP đúng không? Vì sao?
4. Khi `spring-boot:process-aot` thành công nhưng `native:compile` thất bại, bạn cần kiểm tra thêm những giai đoạn nào?
5. Ba trường hợp lỗi đầu vào nào giúp xác nhận validation hoạt động giống nhau trên JVM và native?
6. Khi so sánh thời gian startup và RSS, bạn cần giữ cố định hoặc ghi nhận những điều kiện nào?

**Ghi nhớ:** ứng dụng Spring Boot native đầu tiên nên có một **hợp đồng HTTP nhỏ, có thể xác nhận**. Chạy test trên JVM, biên dịch thông qua Spring AOT và GraalVM Native Image, rồi lặp chính các request ấy trên executable native. Khi cả hai đúng chức năng, mới đo startup và bộ nhớ, sau đó mở rộng sang reflection, resource, container và các vấn đề tương thích thực tế.
