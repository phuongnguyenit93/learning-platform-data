# spring.cloud.function.definition với dấu | hoặc dấu phẩy

## 1. Mục tiêu bài học

Trong Spring Cloud Function, ta có thể xây dựng các bước xử lý nghiệp vụ bằng `Supplier`, `Function` và `Consumer`, rồi kết nối chúng với HTTP, hệ thống sự kiện hoặc môi trường serverless bằng adapter thích hợp. Cùng một hàm có thể được tái sử dụng mà không cần gắn chặt logic nghiệp vụ với giao thức gọi.

Khi ứng dụng có nhiều function bean, thuộc tính `spring.cloud.function.definition` cho biết **hàm nào hoặc tổ hợp hàm nào được chọn để tích hợp**. Hai ký hiệu thường dễ bị nhầm là:

- `|` (dấu gạch đứng): biểu diễn **ghép tuần tự**, đưa đầu ra của hàm trước vào hàm sau.
- `,` (dấu phẩy): trong ngữ cảnh khai báo nhiều định nghĩa được hỗ trợ, biểu diễn **danh sách các function độc lập được chọn**, không tạo chuỗi dữ liệu giữa chúng.

Đây là chủ đề của chương **Ghép hàm**. Sau bài học, bạn sẽ biết cách viết cấu hình, dự đoán đường đi của dữ liệu, kiểm tra hợp đồng kiểu, phân biệt chức năng của `FunctionCatalog` và phát hiện lỗi khi triển khai qua adapter.

> **Phạm vi:** Ví dụ dùng Java 17, Spring Boot và Spring Cloud Function. Cách adapter thực sự công bố các function, đặc biệt khi chọn **nhiều** function, phụ thuộc phiên bản Spring Cloud Function/Spring Cloud Stream và starter đang sử dụng. Với Spring Cloud Stream, dấu `;` là cách khai báo nhiều definition thường gặp trong tài liệu phiên bản; cần đối chiếu tài liệu phiên bản của dự án khi dùng dấu `,`.

## 2. Thuộc tính spring.cloud.function.definition làm gì?

Spring Cloud Function nhận diện và đăng ký các function bean với `FunctionCatalog`. Ví dụ một ứng dụng có ba bean tên `trimText`, `upperText` và `countChars`. Ta có thể chọn một hoặc nhiều định nghĩa cho adapter/framework thông qua `spring.cloud.function.definition`:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText"
~~~

Giá trị này là **tên định nghĩa hàm**, không phải dữ liệu văn bản mà hàm sẽ xử lý. Nó giúp lớp tích hợp chọn function cần dùng. Muốn nhận HTTP request, đọc sự kiện từ broker hoặc chạy serverless, ứng dụng vẫn cần adapter và cấu hình phù hợp.

Có ba câu hỏi tách biệt:

1. **Hàm nào đã được đăng ký?** Các bean `Function`, `Supplier` hoặc `Consumer` được đăng ký và có tên trong `FunctionCatalog`.
2. **Hàm nào được chọn?** Thuộc tính `spring.cloud.function.definition` chỉ ra tên hàm, pipeline hoặc tập định nghĩa cần tích hợp.
3. **Hàm được gọi bằng cách nào?** Adapter HTTP, messaging hay serverless đảm nhiệm đường vào/ra, chuyển đổi payload và cơ chế kích hoạt.

Không nên hiểu chỉ cần thêm property là ứng dụng tự tạo HTTP endpoint hoặc kết nối thành công với message broker.

## 3. Chuẩn bị ba Function bean để quan sát

Ví dụ sau khai báo ba bước biến đổi có hợp đồng rõ ràng:

~~~java
package example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TextFunctions {

    @Bean
    public Function<String, String> trimText() {
        return String::trim;
    }

    @Bean
    public Function<String, String> upperText() {
        return text -> text.toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, Integer> countChars() {
        return String::length;
    }
}
~~~

| Tên function bean | Kiểu đầu vào | Kiểu đầu ra | Ý nghĩa |
|---|---|---|---|
| `trimText` | `String` | `String` | Xóa khoảng trắng đầu/cuối |
| `upperText` | `String` | `String` | Chuyển chữ hoa |
| `countChars` | `String` | `Integer` | Đếm số ký tự UTF-16 trong chuỗi |

Ba hàm độc lập với HTTP, message broker và nền tảng cloud. Chúng chỉ xử lý dữ liệu Java. Các method đánh dấu `@Bean` tạo tên bean mặc định trùng với tên method; vì vậy, cấu hình bên dưới dùng `trimText`, `upperText`, `countChars`.

Trong ứng dụng thực tế, phải bảo đảm lớp cấu hình nằm trong phạm vi Spring component scan và dự án có dependency Spring Cloud Function phù hợp.

## 4. Dấu |: ghép tuần tự thành một pipeline

Khi dùng dấu `|`, các hàm được thực thi **từ trái sang phải**. Đầu ra mỗi bước trở thành đầu vào cho bước bên cạnh.

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText|upperText"
~~~

Sơ đồ:

~~~text
Input "  spring cloud  "
              |
              v
          trimText
              |  "spring cloud"
              v
          upperText
              |  "SPRING CLOUD"
              v
         Output "SPRING CLOUD"
~~~

Tương đương về trình tự xử lý với Java:

~~~java
Function<String, String> pipeline =
        trimText.andThen(upperText);
~~~

Ở dòng Java này, `trimText` và `upperText` là các đối tượng `Function` đã được giữ trong biến. Trong cấu hình Spring Cloud Function, hai chuỗi ký tự là **tên bean đã đăng ký**. Hai cách cùng diễn tả luồng đầu ra bước trước đi vào bước tiếp theo.

Có thể ghép nhiều bước:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText|upperText|countChars"
~~~

Pipeline trên có kiểu tổng thể `String → Integer`:

~~~text
"  spring cloud  "
         |
         v
      trimText      String → String
         |  "spring cloud"
         v
      upperText     String → String
         |  "SPRING CLOUD"
         v
      countChars    String → Integer
         |  12
         v
        12
~~~

Từng function có thể được dùng riêng ở các ngữ cảnh khác, còn pipeline ghép tạo ra một biến đổi nghiệp vụ mới. Việc **ghép tên** qua `|` thường được adapter xử lý như **một định nghĩa đã kết hợp**.

### 4.1. Kiểu đầu ra và đầu vào phải nối được

Giả sử:

~~~java
Function<String, Integer> parseQuantity = Integer::parseInt;
Function<Integer, Long> calculateCost = quantity -> quantity * 75_000L;
~~~

Nếu hai hàm được đăng ký bằng đúng hai tên trên, biểu thức hợp lý là:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseQuantity|calculateCost"
~~~

Kiểu kết quả là `String → Long`. Với input `"4"`, kết quả số là `300000L`.

Ngược lại, `"countChars|trimText"` không có hợp đồng tự nhiên vì `countChars` trả về `Integer` nhưng `trimText` nhận `String`. Đừng tự xem việc đổi kiểu ngầm là một phần nghiệp vụ, dù một số adapter có hỗ trợ chuyển đổi payload. Hãy thiết kế lại thứ tự hoặc thêm một bước biến đổi có ý nghĩa.

### 4.2. Thứ tự không hoán đổi tùy tiện

~~~yaml
# Xóa khoảng trắng trước, sau đó đếm.
spring:
  cloud:
    function:
      definition: "trimText|countChars"
~~~

Input `"  abc  "` có kết quả là `3`. Nếu đổi thành `"countChars|trimText"`, kiểu dữ liệu không còn khớp. Với hai hàm cùng nhận/trả `String` thì chuỗi vẫn có thể ghép nhưng **kết quả nghiệp vụ có thể thay đổi** khi đảo thứ tự.

## 5. Dấu phẩy: chọn nhiều định nghĩa độc lập

Khi môi trường tích hợp và phiên bản Spring Cloud Function hỗ trợ danh sách phân tách bằng dấu phẩy, ta có thể chỉ định **hai hàm riêng biệt**:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText,upperText"
~~~

Ý nghĩa của danh sách là:

~~~text
                 +--> trimText  --> Kết quả riêng của trimText
Chọn hai định nghĩa
                 +--> upperText --> Kết quả riêng của upperText
~~~

Không có cạnh nối dữ liệu `trimText → upperText` chỉ vì hai tên cùng nằm trong một chuỗi phân tách bởi dấu phẩy. Mỗi function giữ hợp đồng kiểu của chính nó.

Ví dụ với chuỗi `"  spring cloud  "`:

| Function được gọi riêng | Kết quả |
|---|---|
| `trimText.apply("  spring cloud  ")` | `"spring cloud"` |
| `upperText.apply("  spring cloud  ")` | `"  SPRING CLOUD  "` |
| Pipeline `trimText|upperText` với cùng input | `"SPRING CLOUD"` |

Dấu phẩy **không có nghĩa chạy trimText trước rồi upperText**. Cũng không có nghĩa một request bất kỳ sẽ tự được nhân đôi để chạy cả hai function; cách định tuyến đầu vào/đầu ra do adapter quyết định.

### 5.1. Lưu ý phiên bản và adapter

Hỗ trợ khai báo nhiều definition và dấu phân tách có thể khác nhau giữa các thành phần Spring Cloud. Đặc biệt, tài liệu Spring Cloud Stream thường thể hiện nhiều function definition dưới dạng:

~~~properties
spring.cloud.function.definition=trimText;upperText
~~~

Trong file `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText;upperText"
~~~

Về mặt khái niệm, dấu `;` cũng biểu diễn **nhiều định nghĩa độc lập** trong những phiên bản/tích hợp hỗ trợ. Điều quan trọng là kiểm tra cú pháp được adapter đang dùng hỗ trợ. Nếu dự án đang dùng dấu phẩy và adapter không tạo được các function/binding mong muốn, hãy đối chiếu tài liệu đúng phiên bản thay vì thay dấu tùy tiện trong code nghiệp vụ.

Chẳng hạn, Spring Cloud Stream cần cấu hình binder, đích input/output và có thể cả tên binding cho từng function. Cấu hình `spring.cloud.function.definition` một mình không quyết định mỗi function sẽ lắng nghe topic nào.

### 5.2. Một ví dụ thực tế cho việc chọn nhiều function

Một dịch vụ xử lý đơn hàng có thể đăng ký:

- `validateOrder: Function<Order, ValidationResult>` để tiếp nhận và kiểm tra đơn.
- `enrichOrder: Function<Order, EnrichedOrder>` để bổ sung thông tin vào đơn.

Nếu đây là **hai đường xử lý độc lập** nhận dữ liệu từ những nguồn khác nhau, việc chọn cả hai định nghĩa là hợp lý khi adapter cho phép cấu hình nhiều function/binding. Nếu mong muốn kết quả của `validateOrder` đi thẳng vào `enrichOrder`, hai hợp đồng hiện tại chưa ghép trực tiếp được: `ValidationResult` không phải `Order`. Khi đó cần thiết kế pipeline mới với kiểu phù hợp, không thể chỉ đổi dấu phân tách.

## 6. So sánh dấu | và dấu phẩy

| Tiêu chí | `"trimText|upperText"` | `"trimText,upperText"` |
|---|---|---|
| Ý nghĩa | Một pipeline ghép tuần tự | Danh sách hai definition riêng, nếu được hỗ trợ |
| Dòng dữ liệu | Kết quả `trimText` đưa vào `upperText` | Không tự nối đầu ra giữa hai hàm |
| Thứ tự | Thứ tự xử lý là quan trọng | Thứ tự liệt kê không biểu diễn pipeline |
| Điều kiện kiểu | Đầu ra bước trước cần phù hợp đầu vào bước sau | Mỗi function có hợp đồng độc lập |
| Số logic được chọn | Một logic hợp thành | Hai logic riêng |
| Ứng dụng thường gặp | Chuẩn hóa → xác thực → chuyển đổi | Công bố/định tuyến nhiều function cho adapter |
| Phụ thuộc adapter | Cách gọi và payload đầu vào/đầu ra | Cách công bố từng function và hỗ trợ dấu phân tách |

Nhớ công thức:

~~~text
A|B  = A rồi B, tạo pipeline A → B

A,B  = liệt kê A và B như hai định nghĩa riêng
       (trong môi trường hỗ trợ cú pháp dấu phẩy)
~~~

Nếu cần pipeline `A → B`, sử dụng `|`. Nếu cần hai function cùng được adapter lựa chọn độc lập, kiểm tra cú pháp danh sách mà adapter hỗ trợ.

## 7. Kết hợp lựa chọn definition với FunctionCatalog.lookup

`FunctionCatalog` cung cấp cơ chế tra cứu những hàm đã đăng ký. Có thể truy cập một hàm riêng hoặc ghép hàm theo tên ngay trong Java:

~~~java
import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class TextPipelineService {

    private final FunctionCatalog catalog;

    public TextPipelineService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public int normalizedLength(String raw) {
        Function<String, Integer> pipeline =
                catalog.lookup("trimText|upperText|countChars");

        if (pipeline == null) {
            throw new IllegalStateException("Khong tim thay text pipeline");
        }

        return pipeline.apply(raw);
    }
}
~~~

`catalog.lookup("trimText|upperText|countChars")` yêu cầu **một function hợp thành** để gọi với `apply`. Trong khi đó, property `spring.cloud.function.definition` chỉ ra những definition được chọn cho hệ thống tích hợp. Chúng có liên hệ với nhau nhưng không thay thế vai trò của nhau.

Ví dụ, nếu trong cấu hình ghi:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText,upperText"
~~~

thì lời gọi Java sau vẫn có thể tra cứu trực tiếp một pipeline theo tên từ các function đã đăng ký:

~~~java
Function<String, String> pipeline =
        catalog.lookup("trimText|upperText");
~~~

Đừng giả định rằng `catalog.lookup("trimText,upperText")` sẽ trả về `Function<String, String>` có tác dụng như `trimText.andThen(upperText)`. Dấu phẩy trong **definition property** không có nghĩa giống dấu `|` của biểu thức composition trong catalog.

### Đối chiếu các nhu cầu

| Nhu cầu | Cách giải quyết |
|---|---|
| Chạy một hàm trong code | `catalog.lookup("trimText")` |
| Chạy nhiều bước liên tiếp trong code | `catalog.lookup("trimText|upperText")` |
| Chọn một pipeline cho adapter | `spring.cloud.function.definition: "trimText|upperText"` |
| Công bố nhiều định nghĩa độc lập | Cấu hình danh sách definition theo cú pháp adapter/phiên bản hỗ trợ |
| Xử lý input đến từ HTTP/sự kiện/serverless | Cấu hình adapter tương ứng, chuyển đổi payload và kiểm thử tích hợp |

## 8. Cú pháp cấu hình trong thực tế

### 8.1. application.yml

Nên đặt giá trị trong dấu ngoặc kép để thể hiện đây là một chuỗi:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText|upperText"
~~~

Hoặc với danh sách dấu phẩy trong môi trường hỗ trợ:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText,upperText"
~~~

Đừng nhầm dấu `|` **bên trong giá trị chuỗi** với ký hiệu `|` ở vị trí **sau dấu hai chấm** trong YAML. Trong YAML, `definition: |` bắt đầu một **block scalar nhiều dòng**; nó không có nghĩa nối hai hàm theo cơ chế Spring Cloud Function.

Ví dụ sau **không diễn tả đúng** cách ghép hai hàm:

~~~yaml
spring:
  cloud:
    function:
      definition: |
        trimText
        upperText
~~~

Giá trị YAML lúc đó là một chuỗi có ký tự xuống dòng, không phải `"trimText|upperText"`.

### 8.2. application.properties

~~~properties
spring.cloud.function.definition=trimText|upperText
~~~

Với danh sách định nghĩa, nếu phiên bản hỗ trợ cú pháp dấu phẩy:

~~~properties
spring.cloud.function.definition=trimText,upperText
~~~

### 8.3. Tham số khi chạy ứng dụng

Có thể truyền property dưới dạng command-line option của Spring Boot. Khi viết lệnh trong shell, nên **quote toàn bộ tham số có dấu `|`** để tránh shell diễn giải dấu này là toán tử pipe:

~~~powershell
java -jar app.jar '--spring.cloud.function.definition=trimText|upperText'
~~~

Tên file `app.jar` chỉ là ví dụ; đường dẫn thực tế tùy dự án. Với môi trường triển khai container, cloud hoặc manifest, cần tuân theo cách quote và escape giá trị của môi trường tương ứng.

## 9. Lựa chọn Function, Supplier và Consumer

Bài học này minh họa `Function<T, R>` để thấy rõ dòng dữ liệu đầu vào/đầu ra, nhưng Spring Cloud Function còn hỗ trợ `Supplier<T>` và `Consumer<T>`.

- **`Supplier<T>`** tạo dữ liệu; không nhận đối số của lời gọi `get`.
- **`Function<T, R>`** biến đổi đầu vào thành đầu ra.
- **`Consumer<T>`** nhận dữ liệu và thực hiện hành động; không có kết quả trả về theo kiểu `Function`.

Khi ghép pipeline bằng `|`, vị trí và hợp đồng của các bước phải có ý nghĩa. Ví dụ, trong trường hợp được framework hỗ trợ, một `Supplier<String>` có thể tạo dữ liệu cho `Function<String, Integer>` phía sau; một `Consumer` thường đóng vai trò điểm cuối xử lý. Không được giả định mọi cách xếp `Supplier`/`Consumer` đều có thể nối như các `Function` thông thường. Hãy kiểm tra hợp đồng composition của phiên bản Spring Cloud Function đang chạy.

Danh sách nhiều definition sử dụng dấu phẩy hoặc `;` không giải quyết vấn đề tương thích kiểu này vì nó không tạo đường nối dữ liệu giữa các thành phần.

## 10. Các lỗi thường gặp

### 10.1. Dùng dấu phẩy khi mục tiêu là ghép liên tiếp

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText,upperText"
~~~

Nếu yêu cầu nghiệp vụ là "xóa khoảng trắng rồi chuyển chữ hoa", hãy viết:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText|upperText"
~~~

Cấu hình đầu chọn những definition độc lập trong môi trường hỗ trợ; cấu hình thứ hai mới mô tả một pipeline.

### 10.2. Dùng dấu | khi cần hai kênh xử lý riêng

Ngược lại, giả sử `validateOrder` và `calculateShipping` cần nhận dữ liệu từ hai luồng sự kiện riêng. Ghép `"validateOrder|calculateShipping"` sẽ nối các bước thành một chuỗi (nếu hợp đồng kiểu cho phép), thay vì chọn hai định nghĩa để adapter kết nối riêng. Hãy khai báo danh sách phù hợp với adapter, rồi cấu hình các binding độc lập.

### 10.3. Đặt sai tên hàm

~~~java
@Bean("normalizePayload")
public Function<String, String> normalize() {
    return String::trim;
}
~~~

Tên bean được đăng ký là `normalizePayload`; không nên mặc định rằng `definition: "normalize"` sẽ tìm thấy bean đó. Kiểm tra `@Bean`, component scan và tên đăng ký thực tế trước khi tìm lỗi ở biểu thức `|` hoặc dấu phẩy.

### 10.4. Hợp đồng kiểu không phù hợp

`"countChars|trimText"` biến `String` thành `Integer` rồi cố chuyển sang bước đòi `String`. Một composition kiểu này có thể bị framework từ chối hoặc lỗi lúc thực thi, tùy runtime và khả năng chuyển đổi dữ liệu. Hãy sửa hợp đồng nghiệp vụ thay vì phụ thuộc vào chuyển kiểu tình cờ.

### 10.5. Nhầm lựa chọn function với tự cấu hình adapter

`spring.cloud.function.definition` không tự cấp URL, đăng ký serverless trigger, thiết lập topic, serializer hoặc listener. Các mục này thuộc adapter và môi trường triển khai. Một pipeline chạy được trong Java không đảm bảo payload HTTP, event headers hoặc JSON schema cũng đã khớp.

### 10.6. Quên khởi chạy lại hoặc kiểm tra cấu hình có hiệu lực

Khi đổi `spring.cloud.function.definition`, hãy xác nhận nguồn cấu hình thực sự được nạp: profile, environment variable và command-line argument có thể ghi đè `application.yml`. Nên kiểm tra log khởi động, danh sách function được công bố và phép thử tích hợp thực tế.

### 10.7. Để client tự quyết định chuỗi definition

Không chuyển trực tiếp tên pipeline tùy ý từ request vào `FunctionCatalog.lookup(...)` rồi thực thi, vì client có thể chọn những bean không được dự định công bố. Khi cần chuyển giữa nhiều pipeline, ánh xạ yêu cầu vào tập tên cho phép ở lớp ứng dụng.

## 11. Kiểm thử hành vi bằng code

### 11.1. Unit test cho tính đúng của ghép tuần tự

Với các `Function` Java thuần, có thể kiểm tra trực tiếp thứ tự:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Locale;
import java.util.function.Function;
import org.junit.jupiter.api.Test;

class TextFunctionTest {

    @Test
    void chainedFunctionsRunInOrder() {
        Function<String, String> trim = String::trim;
        Function<String, String> upper =
                s -> s.toUpperCase(Locale.ROOT);
        Function<String, Integer> length = String::length;

        Function<String, Integer> pipeline =
                trim.andThen(upper).andThen(length);

        assertEquals(12, pipeline.apply("  spring cloud  "));
    }

    @Test
    void independentFunctionsKeepOwnResults() {
        Function<String, String> trim = String::trim;
        Function<String, String> upper =
                s -> s.toUpperCase(Locale.ROOT);

        assertEquals("spring cloud", trim.apply("  spring cloud  "));
        assertEquals("  SPRING CLOUD  ", upper.apply("  spring cloud  "));
    }
}
~~~

Test này xác nhận tính chất biến đổi, nhưng chưa xác nhận việc Spring Cloud Function giải quyết tên function hay adapter đọc `definition`.

### 11.2. Integration test với FunctionCatalog

Khi có một Spring Boot application được cấu hình để quét `TextFunctions` và Spring Cloud Function context, ta có thể kiểm tra pipeline theo tên:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class TextCompositionIntegrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void lookupComposesByPipe() {
        Function<String, Integer> pipeline =
                catalog.lookup("trimText|upperText|countChars");

        assertNotNull(pipeline);
        assertEquals(12, pipeline.apply("  spring cloud  "));
    }

    @Test
    void namesAreLookedUpIndependently() {
        Function<String, String> trim = catalog.lookup("trimText");
        Function<String, String> upper = catalog.lookup("upperText");

        assertNotNull(trim);
        assertNotNull(upper);
        assertEquals("spring cloud", trim.apply("  spring cloud  "));
        assertEquals("  SPRING CLOUD  ",
                upper.apply("  spring cloud  "));
    }
}
~~~

Test trên cần dependency `spring-boot-starter-test` và môi trường Spring Cloud Function được cấu hình tương ứng. Với dấu phẩy hoặc dấu `;`, cần thêm **integration test adapter** để chắc chắn nhiều định nghĩa thật sự được chọn, công bố và kết nối đúng kênh.

### 11.3. Kiểm thử adapter theo mục tiêu triển khai

| Môi trường gọi | Những gì cần kiểm tra |
|---|---|
| HTTP | Endpoint/path thực tế, loại body, kiểu phản hồi, lỗi đầu vào |
| Sự kiện/messaging | Function nào gắn với binding nào, destination, serializer, headers và lỗi |
| Serverless | Event trigger, payload đầu vào, kết quả trả về, cấu hình handler |
| Java nội bộ | Tên `lookup`, kiểu dữ liệu, thứ tự chạy, ngoại lệ |

Không nên kết luận rằng cấu hình đa định nghĩa đã hoạt động chỉ vì unit test cho từng bean đều xanh.

## 12. Tình huống thực tế: một luồng hay hai luồng?

Một ứng dụng có các bước:

- `parseOrder: Function<String, Order>` đọc đơn hàng thô.
- `validateOrder: Function<Order, ValidatedOrder>` kiểm tra quy tắc.
- `calculateTotal: Function<ValidatedOrder, Receipt>` tính tổng tiền.
- `updateCatalog: Function<CatalogEvent, CatalogResult>` cập nhật danh mục.

Nếu mục tiêu là xử lý một đơn hàng từ đầu đến cuối, hãy chọn pipeline:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|calculateTotal"
~~~

Nếu cùng ứng dụng còn nhận một loại sự kiện cập nhật danh mục **độc lập**, có thể cần chọn thêm `updateCatalog` cho adapter hỗ trợ đa định nghĩa. Biểu thức khái niệm là hai nhánh:

~~~text
Nhánh đơn hàng:
  parseOrder → validateOrder → calculateTotal

Nhánh sự kiện danh mục:
  updateCatalog
~~~

Ví dụ khi adapter và phiên bản hỗ trợ danh sách dấu phẩy:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|calculateTotal,updateCatalog"
~~~

Đoạn trên minh họa ý nghĩa **một pipeline và một function riêng**; khả năng phân tích biểu thức trộn `|` với `,` phải được xác nhận ở phiên bản framework/adapter thực tế. Với Spring Cloud Stream, có thể cần dùng cú pháp phân tách nhiều definition mà phiên bản quy định, thường là `;`, đồng thời khai báo binding cho từng nhánh.

Không nên ghép thẳng `"...|updateCatalog"` vì `Receipt` không phải `CatalogEvent` và đó cũng không phải yêu cầu nghiệp vụ.

## 13. Bài tập tự luyện

1. Cho `trimText: String → String`, `upperText: String → String` và `countChars: String → Integer`. Viết giá trị `spring.cloud.function.definition` để tính độ dài chuỗi sau khi trim và chuyển chữ hoa. Xác định đầu ra với `"  java  "`.
2. Bạn cần công bố `findCustomer` và `findInvoice` như **hai hàm độc lập** trong một adapter hỗ trợ đa định nghĩa. Hãy viết danh sách có dấu phẩy và giải thích vì sao `findCustomer|findInvoice` không diễn đạt yêu cầu.
3. Cho `parse: String → Integer` và `format: Long → String`. Vì sao `"parse|format"` chưa có hợp đồng kiểu trực tiếp phù hợp? Đề xuất một bước chuyển đổi có ý nghĩa nghiệp vụ.
4. Một ứng dụng đặt `definition: "trimText,upperText"` nhưng mọi sự kiện lại được đưa vào một binding mà bạn kỳ vọng chạy pipeline. Hãy mô tả cách phân biệt **lỗi cú pháp ghép** và **lỗi cấu hình adapter**.
5. Viết kiểm thử tích hợp gọi `catalog.lookup("trimText|upperText")` và xác minh input `" abc "` trả ra `"ABC"`. Giải thích vì sao kiểm thử này chưa đủ để chứng minh hai function độc lập được công bố qua broker.

**Gợi ý bài 1:** `definition: "trimText|upperText|countChars"`; chuỗi `"JAVA"` có độ dài `4`.

## 14. Ghi nhớ

- `spring.cloud.function.definition` chọn tên hàm hoặc biểu thức hàm mà Spring Cloud Function/adapter sẽ sử dụng.
- Dấu `|` tạo **một pipeline tuần tự**: `A|B` chạy A trước rồi lấy kết quả đưa vào B.
- Dấu phẩy `,` trong môi trường hỗ trợ danh sách định nghĩa dùng để **chọn nhiều hàm độc lập**; không tự truyền dữ liệu từ A sang B. Spring Cloud Stream thường dùng dấu `;` cho nhu cầu này tùy phiên bản.
- `FunctionCatalog.lookup("A|B")` tra cứu một function đã ghép trong Java, còn `spring.cloud.function.definition` chọn logic cho lớp tích hợp.
- Muốn triển khai qua HTTP, sự kiện hoặc serverless, ngoài chọn definition còn cần adapter, hợp đồng dữ liệu và kiểm thử tích hợp thích hợp.
