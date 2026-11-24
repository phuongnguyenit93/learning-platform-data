# Ghép theo tên bằng FunctionCatalog.lookup

## 1. Vì sao cần ghép hàm theo tên?

Spring Cloud Function hướng đến việc viết logic nghiệp vụ dưới dạng **`Supplier`, `Function` và `Consumer` có thể tái sử dụng**, tách khỏi giao thức mà hệ thống sử dụng để gọi logic đó. Cùng một hàm có thể tham gia một luồng xử lý nội bộ và được kết nối với adapter HTTP, sự kiện hoặc serverless khi ứng dụng được cấu hình phù hợp.

Trong Java thuần, ta có thể ghép hai `Function` trực tiếp:

~~~java
Function<String, String> normalize = String::trim;
Function<String, Integer> measure = String::length;
Function<String, Integer> pipeline = normalize.andThen(measure);
~~~

Tuy nhiên, khi ứng dụng Spring có nhiều hàm được đăng ký sẵn, đôi khi ta muốn **chọn và ghép chúng bằng tên** để thay đổi pipeline qua cấu hình hoặc lấy một tổ hợp tại runtime. Đó là vai trò của `FunctionCatalog`.

Bài học này thuộc chương **Ghép hàm**, tập trung vào cách tra cứu và ghép hàm bằng `FunctionCatalog.lookup(...)`.

Sau bài học, bạn có thể:

- Mô tả cách Spring Cloud Function phát hiện, đăng ký và tra cứu các bean `Function` trong `FunctionCatalog`.
- Dùng `lookup("tenHam")` lấy một hàm và `lookup("hamA|hamB")` lấy một chuỗi hàm.
- Đọc đúng thứ tự thực thi, kiểm tra tương thích kiểu đầu ra/đầu vào và lựa chọn tên bean phù hợp.
- Phân biệt `lookup` trong code với cấu hình `spring.cloud.function.definition` dành cho môi trường tích hợp.
- Xử lý trường hợp không tìm thấy hàm, ghép sai hợp đồng kiểu và kiểm thử pipeline bằng Spring context.

## 2. FunctionCatalog là gì?

`FunctionCatalog` là giao diện của Spring Cloud Function giúp tra cứu các hàm đã được hệ thống đăng ký. Các bean kiểu `java.util.function.Function`, `Supplier` và `Consumer` được Spring Cloud Function phát hiện và cung cấp thông qua catalog theo quy tắc đăng ký của framework.

Import cần dùng:

~~~java
import org.springframework.cloud.function.context.FunctionCatalog;
~~~

Cách sử dụng cốt lõi:

~~~java
Function<String, String> one =
        catalog.lookup("normalizeSku");

Function<String, Boolean> composed =
        catalog.lookup("normalizeSku|validateSku");
~~~

Ở ví dụ này, `normalizeSku` và `validateSku` phải là các tên hàm đã được catalog đăng ký. Dấu `|` biểu thị thứ tự chạy **từ trái sang phải**:

~~~text
catalog.lookup("normalizeSku|validateSku")

                  String đầu vào
                       |
                       v
                  normalizeSku
                  String → String
                       |
                       v
                   validateSku
                  String → Boolean
                       |
                       v
                  Boolean đầu ra
~~~

Về ý nghĩa nghiệp vụ, chuỗi trên tương đương với:

~~~java
normalizeSku.andThen(validateSku)
~~~

Khác biệt chính là cách có được hàm: `andThen` nối các đối tượng `Function` đã có trong code, còn `FunctionCatalog.lookup` **giải quyết tên đã đăng ký** và cung cấp hàm hoặc chuỗi hàm để gọi.

> `FunctionCatalog` thuộc Spring Cloud Function. Nó không phải là `ApplicationContext.getBean(...)`: catalog cung cấp lớp trừu tượng cho việc tra cứu, composition và những cơ chế thích ứng kiểu/thông điệp của framework. Vì vậy, một đối tượng do catalog trả về có thể là wrapper do Spring Cloud Function quản lý.

## 3. Tạo các Function bean có tên rõ ràng

Xét nghiệp vụ tiếp nhận mã sản phẩm từ nhiều nguồn. Mã có thể có khoảng trắng và chữ thường; hệ thống cần chuẩn hóa mã trước khi kiểm tra mẫu `SKU-<số>`.

Ta định nghĩa hai hàm độc lập:

~~~java
package example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SkuFunctions {

    @Bean
    public Function<String, String> normalizeSku() {
        return value -> value.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, Boolean> validateSku() {
        return value -> value.matches("SKU-[0-9]+");
    }
}
~~~

Các điểm cần chú ý:

1. `@Bean` đưa hàm vào Spring application context. Khi dự án có Spring Cloud Function và cấu hình quét bean phù hợp, framework đăng ký chúng vào function catalog.
2. Theo mặc định, tên bean từ hai phương thức là `normalizeSku` và `validateSku`. Đây là các tên dùng trong biểu thức `lookup`.
3. `normalizeSku` có hợp đồng `Function<String, String>`; `validateSku` có hợp đồng `Function<String, Boolean>`. Vì đầu ra của hàm trước phù hợp với đầu vào hàm sau, có thể nối chúng.
4. `Locale.ROOT` giúp chuẩn hóa chữ hoa độc lập với locale của máy chủ. Biểu thức chính quy trong ví dụ chỉ cho phép mã dạng `SKU-` theo sau bởi một hoặc nhiều chữ số.

Nếu muốn một tên bean khác với tên phương thức, có thể chỉ định tên trực tiếp:

~~~java
@Bean("skuNormalizer")
public Function<String, String> normalizeSku() {
    return value -> value.trim().toUpperCase(Locale.ROOT);
}
~~~

Khi đó, hãy tra cứu bằng tên được đăng ký `skuNormalizer`:

~~~java
catalog.lookup("skuNormalizer|validateSku");
~~~

Đừng giả định rằng tên lớp, mô tả nghiệp vụ hoặc tên biến Java chính là tên trong catalog. Với `@Bean`, hãy xuất phát từ tên bean thực tế được Spring đăng ký.

## 4. Tra cứu và chạy một pipeline bằng lookup

Ví dụ sau sử dụng `ApplicationRunner` để chạy một lượt kiểm tra sau khi ứng dụng Spring Boot khởi động. Giả sử `SkuFunctions` ở mục 3 nằm trong phạm vi component scan và ứng dụng đã có dependency Spring Cloud Function phù hợp.

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class SkuDemoRunner implements ApplicationRunner {

    private final FunctionCatalog catalog;

    public SkuDemoRunner(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public void run(ApplicationArguments args) {
        Function<String, Boolean> checkSku =
                catalog.lookup("normalizeSku|validateSku");

        if (checkSku == null) {
            throw new IllegalStateException(
                    "Khong tim thay pipeline kiem tra SKU");
        }

        System.out.println(checkSku.apply(" sku-42 "));  // true
        System.out.println(checkSku.apply("invalid"));   // false
    }
}
~~~

Trong lời gọi đầu tiên:

1. Catalog tra cứu `normalizeSku` và `validateSku` theo tên.
2. Catalog tạo/lấy một biểu diễn thực thi chuỗi `normalizeSku|validateSku` phù hợp với cơ chế composition của framework.
3. Khi `checkSku.apply(" sku-42 ")` chạy, bước chuẩn hóa trả `"SKU-42"`.
4. Bước kiểm tra nhận `"SKU-42"` rồi trả `true`.

Lời gọi `lookup` **lấy hàm để thực thi**; tác vụ xử lý dữ liệu xảy ra khi gọi `apply`. Việc khởi tạo pipeline có thể cần kiểm tra và tạo wrapper tùy cách framework quản lý danh mục hàm; không nên dựa vào giả định rằng `lookup` luôn tạo một đối tượng Java mới hay luôn trả về đúng instance bean ban đầu.

### Tra cứu một hàm đơn

Có thể lấy từng hàm riêng lẻ, hữu ích khi kiểm thử hoặc muốn chạy một bước:

~~~java
Function<String, String> normalizer = catalog.lookup("normalizeSku");

if (normalizer == null) {
    throw new IllegalStateException("Thieu normalizeSku");
}

System.out.println(normalizer.apply(" sku-07 ")); // SKU-07
~~~

`lookup("normalizeSku")` trả về một hàm có thể gọi; `lookup("normalizeSku|validateSku")` trả về chuỗi biến đổi. **Tên tra cứu là đầu vào mô tả hàm cần lấy**, không phải dữ liệu đầu vào cho nghiệp vụ. Dữ liệu thực tế được truyền qua `apply`.

## 5. Cách viết biểu thức ghép theo tên

Dạng cơ bản:

~~~text
"functionName1|functionName2|functionName3"
~~~

Mỗi dấu `|` nối đầu ra của hàm bên trái với đầu vào của hàm bên phải. Ví dụ, ta bổ sung một bước lấy mã số từ chuỗi SKU đã hợp lệ:

~~~java
@Bean
public Function<String, String> trimSku() {
    return String::trim;
}

@Bean
public Function<String, String> uppercaseSku() {
    return value -> value.toUpperCase(Locale.ROOT);
}

@Bean
public Function<String, String> stripPrefix() {
    return value -> value.replaceFirst("^SKU-", "");
}
~~~

Tra cứu:

~~~java
Function<String, String> getSkuNumber =
        catalog.lookup("trimSku|uppercaseSku|stripPrefix");

System.out.println(getSkuNumber.apply(" sku-123 ")); // 123
~~~

Thứ tự xử lý tương ứng:

~~~text
" sku-123 "
   |
   v
trimSku            → "sku-123"
   |
   v
uppercaseSku       → "SKU-123"
   |
   v
stripPrefix        → "123"
~~~

Ở đây, các bước đều nhận/trả `String` nên dễ ghép. Nhưng tính tương thích kiểu chỉ là điều kiện cần: chẳng hạn `stripPrefix` xử lý một chuỗi không bắt đầu bằng `"SKU-"` vẫn trả về giá trị, có thể khiến ứng dụng chấp nhận mã không hợp lệ nếu thiếu bước xác thực. Với dữ liệu thực tế, hãy thiết kế điều kiện hợp lệ trước khi bỏ tiền tố hoặc chuyển đổi sang kiểu khác.

### Ghép qua kiểu dữ liệu khác nhau

Giả sử có:

~~~java
Function<String, Integer> parseAmount = Integer::parseInt;
Function<Integer, Long> calculateTotal = qty -> qty * 125_000L;
~~~

Nếu các hàm này được đăng ký với tên tương ứng, chuỗi `"parseAmount|calculateTotal"` có hợp đồng tổng thể `String → Long`.

Ngược lại, một `Function<String, Integer>` không thể nối trực tiếp với `Function<Boolean, String>` vì `Integer` không phù hợp với `Boolean`. Trong Java thuần, `andThen` thường báo lỗi biên dịch khi generic không tương thích; biểu thức tên qua catalog được giải quyết ở runtime nên cần kiểm thử việc tra cứu và áp dụng hàm.

## 6. lookup khác gì với spring.cloud.function.definition?

Có hai nhu cầu liên quan nhưng khác nhau:

| Nhu cầu | Cách làm | Điều cần nhớ |
|---|---|---|
| Code Java cần lấy một hàm cụ thể ngay lúc chạy | `catalog.lookup("normalizeSku")` | Trả về hàm có thể gọi từ code |
| Code Java cần lấy một tổ hợp theo tên | `catalog.lookup("normalizeSku|validateSku")` | Trả về pipeline, gọi qua `apply` |
| Ứng dụng/adapter cần chọn hàm để công bố hoặc kết nối | `spring.cloud.function.definition` | Khai báo tên hoặc chuỗi hàm được chọn trong cấu hình |
| Code đã giữ các đối tượng `Function` cần ghép trực tiếp | `first.andThen(second)` | API Java, không cần tra cứu bean theo tên |

Cấu hình ví dụ trong `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeSku|validateSku"
~~~

Thuộc tính `spring.cloud.function.definition` cho phép adapter hoặc phần tích hợp Spring Cloud Function chọn tổ hợp hàm đã khai báo. Nó **không tự khởi chạy xử lý nghiệp vụ** và cũng không tự tạo endpoint HTTP hay binding sự kiện. Để nhận request hoặc message thật, ứng dụng phải có adapter và thiết lập tương ứng, ví dụ tích hợp Spring Cloud Function Web hoặc Spring Cloud Stream.

Nếu code **đã** gọi `catalog.lookup("normalizeSku|validateSku")`, lời gọi đó yêu cầu pipeline theo tên rõ ràng mà không cần đổi property nói trên. Ngược lại, thay đổi `spring.cloud.function.definition` không đồng nghĩa mọi lời gọi `lookup("tenKhac")` trong code sẽ tự chuyển sang tên mới.

Khi có nhiều function bean, nên chọn tên cụ thể để tránh nhầm lẫn. Không nên dựa vào suy luận "chỉ có một hàm nên framework sẽ tự chọn đúng" khi xây dựng ví dụ hoặc ứng dụng cần hoạt động ổn định qua các môi trường.

## 7. FunctionCatalog trong mô hình độc lập giao thức

Bản thân catalog xử lý **việc lựa chọn và kết nối logic**, không quyết định transport. Các adapter phụ trách cách đưa đầu vào và phát hành kết quả. Có thể hình dung:

~~~text
                     Tên pipeline
               "normalizeSku|validateSku"
                            |
                            v
                       FunctionCatalog
                            |
                            v
                       Function đã ghép
                       String → Boolean
                            ^
                            |
             +--------------+--------------+
             |              |              |
          HTTP Web        Sự kiện       Serverless
           adapter        adapter         adapter
             |              |              |
        HTTP payload   Message/payload  Event payload
~~~

Đây là sơ đồ khái niệm, không khẳng định cùng một ứng dụng sẽ tự động có ba adapter. Việc hiện thực cần dependency, cấu hình và cơ chế ánh xạ dữ liệu phù hợp từng adapter.

Khi dùng thông điệp (`Message<T>`), metadata như headers và kiểu payload cần được xem xét thêm. Spring Cloud Function có khả năng thích ứng và chuyển đổi thông điệp theo thông tin kiểu và cấu hình, nhưng đừng giả định mọi phép ghép đều giữ nguyên headers hoặc chuyển JSON tùy ý. Với pipeline xử lý sự kiện, hãy kiểm thử trên kiểu dữ liệu được adapter thực sự cung cấp.

### Một cách tổ chức dễ bảo trì

Tổ chức các bước theo nhiệm vụ độc lập:

- `normalizeSku`: chuẩn hóa ký tự và khoảng trắng.
- `validateSku`: xác thực định dạng.
- `enrichSku`: bổ sung dữ liệu khi cần và khi hợp đồng kiểu phù hợp.
- `publishResult`: gửi kết quả đến hệ thống khác (nếu thiết kế pipeline cho phép bước có tác dụng phụ).

Tên hàm nên ổn định, dễ đọc và không trùng nhau. Pipeline được ghép theo tên hoạt động tốt nhất khi đầu ra, đầu vào và lỗi của từng bước được mô tả tường minh.

## 8. Xử lý lỗi khi tra cứu và ghép hàm

### 8.1. Không tìm thấy tên đã đăng ký

~~~java
Function<String, Boolean> pipeline =
        catalog.lookup("normalizeSku|unknownStep");

if (pipeline == null) {
    throw new IllegalArgumentException(
            "Pipeline chua duoc dang ky");
}
~~~

Tùy phiên bản và trường hợp, lỗi ghép có thể được phát hiện khi `lookup` hoặc khi thực thi. Vì vậy, kiểm tra `null` chỉ là bước phòng vệ đầu tiên; đừng coi nó là cách duy nhất phát hiện mọi cấu hình sai. Khi gặp lỗi, kiểm tra tên bean thực tế, phạm vi component scan, dependency Spring Cloud Function và log lúc ứng dụng khởi động.

### 8.2. Kiểu đầu ra/đầu vào không phù hợp

Giả sử `loadOrder` trả `Order`, còn `verifyToken` cần `String`. Biểu thức `"loadOrder|verifyToken"` không có hợp đồng nối trực tiếp phù hợp dù cả hai hàm có thể tồn tại trong catalog.

Giải pháp là thiết kế một bước chuyển đổi có ý nghĩa nghiệp vụ, ví dụ `extractToken: Order → String`, rồi ghép `"loadOrder|extractToken|verifyToken"`; hoặc thay đổi hợp đồng hàm nếu đầu ra thực sự cần được giữ là `Order`.

Không nên chèn phép chuyển thành `String` tùy tiện chỉ để qua lỗi kiểu, vì điều này che giấu vấn đề thiết kế dữ liệu.

### 8.3. Dữ liệu hợp kiểu nhưng sai nội dung

~~~java
Function<String, Integer> parseQuantity = Integer::parseInt;
~~~

Chuỗi `"abc"` vẫn là `String` nhưng `parseQuantity.apply("abc")` ném `NumberFormatException`. Catalog không tự hiểu đó là lỗi nghiệp vụ và không tự xây dựng phản hồi JSON thân thiện. Cần xác định rõ tầng chịu trách nhiệm validation, ánh xạ ngoại lệ và chính sách retry của ứng dụng.

### 8.4. Thiếu xác thực dữ liệu và tác dụng phụ

Nếu một bước gửi email, ghi database hoặc phát sự kiện, mỗi lần gọi `apply` có thể tạo ra tác dụng phụ. Ghép hàm theo tên không tự cung cấp giao dịch, idempotency, retry, timeout hay thực thi song song. Các cơ chế này phải được thiết kế riêng khi dùng adapter hoặc tích hợp với hệ thống bên ngoài.

### 8.5. Tên pipeline lấy trực tiếp từ người gọi

Không nên để client bên ngoài gửi một chuỗi bất kỳ rồi chuyển thẳng đến `catalog.lookup(userInput)`. Điều đó có thể vô tình cho phép gọi những function mà API không có ý định công bố. Nếu cần thay đổi pipeline theo ngữ cảnh, hãy ánh xạ lựa chọn hợp lệ qua một **danh sách cho phép** ở lớp ứng dụng.

Ví dụ:

~~~java
String selected = switch (requestType) {
    case "sku-check" -> "normalizeSku|validateSku";
    case "sku-normalize" -> "normalizeSku";
    default -> throw new IllegalArgumentException("Loai yeu cau khong ho tro");
};
~~~

Đây là lựa chọn trong code Java 17+, minh họa cách chọn từ tập tên đã được phê duyệt. Kiểu trả về của từng pipeline có thể khác nhau (`Boolean` so với `String`); khi dùng chung một luồng xử lý, cần thiết kế kiểu kết quả hoặc phân nhánh tương ứng thay vì ép cả hai về cùng một generic sai.

## 9. Kiểm thử FunctionCatalog.lookup

Để kiểm tra tra cứu theo tên, phải khởi động **Spring application context** có đủ các function bean và Spring Cloud Function. Chỉ tạo một đối tượng `new SkuFunctions()` không chứng minh rằng catalog đăng ký được tên đúng.

Ví dụ JUnit 5 và Spring Boot Test, đặt trong cùng ứng dụng đang quét `SkuFunctions`:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class SkuCompositionTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void catalogLooksUpNamedComposition() {
        Function<String, Boolean> pipeline =
                catalog.lookup("normalizeSku|validateSku");

        assertNotNull(pipeline);
        assertTrue(pipeline.apply(" sku-42 "));
        assertFalse(pipeline.apply(" invalid "));
    }
}
~~~

Kiểm thử trên cần một lớp ứng dụng Spring Boot hợp lệ trong cấu hình kiểm thử và dependency test phù hợp. Nếu kết quả trả về khác kiểu dự kiến vì chuyển đổi thông điệp của một adapter, hãy kiểm tra hợp đồng đầu ra/đầu vào thực tế trước khi chỉnh assertion.

Có thể bổ sung kiểm thử theo từng lớp:

1. **Unit test từng bean:** xác nhận chuẩn hóa và kiểm tra mã với đầu vào hợp lệ, rỗng, có khoảng trắng hoặc sai mẫu.
2. **Integration test catalog:** xác nhận `lookup` tìm đúng tên và thực hiện đúng thứ tự, đầu ra.
3. **Adapter test:** khi có HTTP/event/serverless, kiểm tra payload, headers, định dạng lỗi và kiểu kết quả ở ranh giới thực tế.

Những kiểm thử này giúp phát hiện lỗi có thể lọt qua kiểm tra kiểu Java, ví dụ typo trong chuỗi tên hoặc thay đổi tên bean mà chưa cập nhật cấu hình.

## 10. Phân biệt những khái niệm dễ nhầm

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| `@Bean` | Đăng ký một function vào Spring context | `normalizeSku()` |
| Tên bean | Định danh mà catalog có thể tra cứu | `"normalizeSku"` |
| `FunctionCatalog` | Cổng tra cứu function đã đăng ký và composition | `catalog.lookup(...)` |
| Chuỗi composition | Mô tả thứ tự các function theo tên | `"normalizeSku|validateSku"` |
| `Function.apply` | Cung cấp input và thực thi pipeline | `pipeline.apply(" sku-42 ")` |
| `spring.cloud.function.definition` | Chọn function/pipeline cho tích hợp theo cấu hình | `"normalizeSku|validateSku"` |
| Adapter | Kết nối logic với HTTP, messaging hay serverless | Spring Cloud Function Web, Stream adapter hoặc adapter cloud |

Nhớ sự khác biệt giữa **chuỗi định danh** và **giá trị nghiệp vụ**:

~~~java
// "normalizeSku|validateSku" là cách tìm pipeline.
Function<String, Boolean> pipeline =
        catalog.lookup("normalizeSku|validateSku");

// " sku-42 " là dữ liệu mà pipeline xử lý.
Boolean accepted = pipeline.apply(" sku-42 ");
~~~

## 11. Bài tập thực hành

### Bài 1: Pipeline phân tích số lượng

Tạo ba function bean:

- `trimInput: String → String`: loại bỏ khoảng trắng đầu/cuối.
- `parseQuantity: String → Integer`: chuyển chuỗi thành số.
- `calculateCost: Integer → Long`: nhân số lượng với đơn giá `75_000L`.

Hãy viết câu lệnh `lookup` để tạo `Function<String, Long>` rồi tính tổng tiền với input `" 4 "`. Kết quả mong đợi: `300000L`.

### Bài 2: Đổi tên bean

Đổi tên bean `trimInput` thành `quantityTrimmer` bằng `@Bean("quantityTrimmer")` mà vẫn giữ tên phương thức Java. Sau đó cập nhật biểu thức ghép cho đúng. Giải thích vì sao chuỗi chứa `trimInput` cũ không còn đáng tin cậy.

### Bài 3: Pipeline sai kiểu

Cho `parseQuantity: String → Integer` và `isSku: String → Boolean`, xác định vì sao `"parseQuantity|isSku"` sai. Đề xuất một chức năng tiếp theo có đầu vào `Integer` phù hợp hơn để hoàn thành một pipeline xử lý số lượng.

### Bài 4: Triển khai qua adapter

Cấu hình `spring.cloud.function.definition` chọn `"normalizeSku|validateSku"`. Giải thích:

1. Chỉ thêm property trên có tạo một HTTP endpoint hay không?
2. Khi dùng thêm adapter HTTP, những điểm nào của payload đầu vào và kiểu kết quả phải kiểm thử?
3. Vì sao vẫn cần kiểm tra trực tiếp `FunctionCatalog.lookup` trong integration test?

**Gợi ý bài 1:**

~~~java
Function<String, Long> totalCost =
        catalog.lookup("trimInput|parseQuantity|calculateCost");

System.out.println(totalCost.apply(" 4 ")); // 300000
~~~

## 12. Ghi nhớ

- `FunctionCatalog.lookup("functionName")` lấy một hàm đã được Spring Cloud Function đăng ký theo tên.
- `FunctionCatalog.lookup("first|second")` ghép hai hàm theo thứ tự **first rồi second**; nhiều bước tiếp tục được phân cách bằng `|`.
- Đầu ra mỗi bước phải tương thích với đầu vào bước tiếp theo, đồng thời phù hợp với ý nghĩa nghiệp vụ.
- `lookup` lựa chọn logic có thể gọi từ Java; `spring.cloud.function.definition` giúp adapter/integration lựa chọn logic qua cấu hình.
- Việc ghép hàm theo tên chỉ là một phần của hệ thống: muốn cùng logic hoạt động qua HTTP, sự kiện hoặc serverless, cần adapter, dữ liệu đầu vào/đầu ra và kiểm thử tích hợp tương ứng.
