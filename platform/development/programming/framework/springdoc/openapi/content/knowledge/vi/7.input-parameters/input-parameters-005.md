# Tên hiển thị, tên binding và cơ chế khám phá tên tham số

Khi springdoc-openapi tạo tài liệu cho một endpoint Spring Boot, tên tham số xuất hiện trong OpenAPI cần phản ánh đúng tên mà client phải gửi. Tuy nhiên, trong mã Java có thể đồng thời tồn tại ba tên khác nhau: tên biến tham số Java, tên binding mà Spring dùng để đọc dữ liệu HTTP và tên hiển thị trong tài liệu OpenAPI.

Ba tên này thường giống nhau trong ví dụ đơn giản, nhưng không phải lúc nào cũng đồng nhất. Hiểu rõ nguồn lấy tên giúp tránh lỗi khi đổi tên biến, biên dịch thiếu metadata hoặc dùng annotation tài liệu để mô tả khác với hành vi binding thực tế.

## 1. Ba loại tên cần phân biệt

Xét endpoint tìm kiếm khách hàng:

~~~java
@GetMapping("/customers")
List<CustomerResponse> searchCustomers(
        @RequestParam(name = "keyword") String query) {
    // ...
}
~~~

Trong ví dụ:

- <code>query</code> là tên tham số trong mã Java.
- <code>keyword</code> là tên binding. Spring đọc giá trị từ query parameter có tên <code>keyword</code>.
- <code>keyword</code> cũng là tên được công bố trong OpenAPI để client gửi request đúng.

| Loại tên | Được dùng ở đâu? | Ví dụ |
|---|---|---|
| Tên biến Java | Trong chữ ký method và phần triển khai | <code>query</code> |
| Tên binding Spring | Đọc giá trị từ path, query, header hoặc cookie | <code>keyword</code> |
| Tên hiển thị OpenAPI | Công bố cho người dùng tài liệu và client generator | <code>keyword</code> |

Tên biến Java có thể đổi khi refactor mà không làm thay đổi HTTP contract, miễn là tên binding được giữ nguyên. Tên hiển thị OpenAPI phải khớp với hợp đồng thực tế: nếu tài liệu nói client gửi <code>keyword</code> nhưng controller lại đọc <code>q</code>, người gọi API có thể gửi đúng theo tài liệu mà vẫn nhận kết quả sai hoặc lỗi.

## 2. Tên binding được xác định từ đâu?

Trong Spring MVC và Spring WebFlux, các annotation như <code>@RequestParam</code>, <code>@PathVariable</code>, <code>@RequestHeader</code> và <code>@CookieValue</code> cho phép khai báo tên binding bằng thuộc tính <code>name</code> hoặc bí danh <code>value</code>.

### 2.1. Khai báo tên binding tường minh

~~~java
@GetMapping("/customers/{customerId}")
CustomerResponse getCustomer(
        @PathVariable(name = "customerId") String id,
        @RequestParam(name = "includeOrders", required = false) Boolean includeOrders,
        @RequestHeader(name = "X-Tenant-Id") String tenantId,
        @CookieValue(name = "locale", required = false) String locale) {
    // ...
}
~~~

Các tên binding trong ví dụ lần lượt là:

| Annotation | Vị trí HTTP | Tên binding |
|---|---|---|
| <code>@PathVariable(name = "customerId")</code> | Path | <code>customerId</code> |
| <code>@RequestParam(name = "includeOrders")</code> | Query | <code>includeOrders</code> |
| <code>@RequestHeader(name = "X-Tenant-Id")</code> | Header | <code>X-Tenant-Id</code> |
| <code>@CookieValue(name = "locale")</code> | Cookie | <code>locale</code> |

Tên biến Java là chi tiết nội bộ. Trong ví dụ, biến <code>id</code> được bind từ path variable <code>customerId</code>, còn biến <code>tenantId</code> được bind từ header <code>X-Tenant-Id</code>.

Khai báo tên tường minh có hai lợi ích: Spring luôn biết chính xác trường HTTP cần đọc, và người bảo trì có thể đổi tên biến Java mà không làm thay đổi tên client phải gửi.

### 2.2. Thuộc tính name và value

Nhiều annotation binding của Spring định nghĩa <code>name</code> và <code>value</code> như hai bí danh cho cùng một ý nghĩa. Hai cách dưới đây tương đương:

~~~java
@RequestParam(name = "page") int pageNumber

@RequestParam(value = "page") int pageNumber
~~~

Có thể dùng dạng rút gọn khi annotation chỉ có một thuộc tính giá trị:

~~~java
@RequestParam("page") int pageNumber
@PathVariable("customerId") String id
~~~

Trong dự án có quy ước thống nhất, nên chọn một kiểu viết và áp dụng xuyên suốt. Dùng <code>name</code> thường giúp người đọc nhận ra rõ mục đích của giá trị.

## 3. Khi bỏ tên binding tường minh, Spring khám phá tên tham số Java

Spring cho phép viết ngắn bằng cách bỏ tên trong annotation:

~~~java
@GetMapping("/customers")
List<CustomerResponse> searchCustomers(
        @RequestParam String keyword) {
    // ...
}
~~~

Trong trường hợp này, Spring cần khám phá tên tham số Java để biết query parameter có tên <code>keyword</code>. Việc khám phá dựa trên metadata có trong bytecode, đặc biệt là tên tham số được lưu bởi trình biên dịch Java.

Java có thể lưu tên tham số trong class file khi biên dịch với tùy chọn <code>-parameters</code>. Nếu class được biên dịch không có metadata này, reflection có thể chỉ trả về tên tổng quát như <code>arg0</code> và không xác định được tên nguồn. Khi đó, những annotation cần suy ra tên có thể không hoạt động như mong đợi.

### 3.1. Bật metadata tên tham số trong Maven

Với Maven Compiler Plugin, có thể bật tùy chọn <code>parameters</code>:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Nếu dự án dùng Spring Boot parent hoặc BOM/plugin quản lý sẵn cấu hình compiler, hãy kiểm tra cấu hình hiệu lực trước khi thêm cấu hình trùng. Điều quan trọng là class được đóng gói phải có metadata tên tham số mà Spring cần.

### 3.2. Bật metadata tên tham số trong Gradle

Với Gradle Java plugin, có thể thêm compiler argument:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Sau khi đổi cấu hình compiler, cần build lại class và triển khai artifact mới. Thay đổi cấu hình không bổ sung metadata cho các file class đã được biên dịch trước đó.

### 3.3. Khi nào nên dùng cơ chế khám phá?

Khám phá tên tham số giúp mã ngắn gọn và có thể phù hợp với dự án đã bật <code>-parameters</code> một cách nhất quán. Tuy nhiên, nó làm cho binding phụ thuộc vào metadata compiler. Với endpoint công khai hoặc hợp đồng cần ổn định, khai báo tên binding rõ ràng thường dễ bảo trì hơn.

Không nên dựa vào tên tham số được giữ lại trong debug information như một bảo đảm chung. Metadata dùng cho debug và metadata tên tham số phục vụ reflection là những cơ chế khác nhau.

## 4. Tên hiển thị trong OpenAPI bằng springdoc-openapi

springdoc-openapi đọc các mapping và annotation Spring để tạo Parameter Object trong OpenAPI. Thông thường, tên binding từ annotation Spring được dùng làm tên tham số trong tài liệu.

Annotation <code>@Parameter</code> của Swagger Core cho phép bổ sung hoặc điều chỉnh metadata mô tả OpenAPI như tên, mô tả, vị trí, ví dụ và trạng thái bắt buộc:

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerSearchController {

    @GetMapping("/customers")
    List<CustomerResponse> search(
            @Parameter(
                description = "Từ khóa tìm kiếm theo tên hoặc email",
                example = "lan@example.com"
            )
            @RequestParam(name = "keyword") String query) {
        // ...
    }
}
~~~

Trong ví dụ, <code>@RequestParam(name = "keyword")</code> xác định tên binding runtime. <code>@Parameter</code> bổ sung mô tả và ví dụ cho tham số trong tài liệu. Đây là cách tốt để tách hành vi HTTP khỏi nội dung giải thích dành cho người đọc.

Nếu thật sự cần chỉ định tên OpenAPI bằng <code>@Parameter(name = "...")</code>, hãy bảo đảm tên đó khớp với tên binding Spring. <code>@Parameter</code> chỉ mô tả hợp đồng; nó không thay đổi cách Spring lấy dữ liệu từ request.

Ví dụ cấu hình không nhất quán:

~~~java
@Parameter(name = "customerId")
@PathVariable("id") String id
~~~

Ở đây Spring binding dùng tên <code>id</code>, trong khi metadata OpenAPI lại công bố <code>customerId</code>. Client gửi <code>customerId</code> theo tài liệu có thể không được Spring bind vào path variable. Cách sửa là thống nhất cả hai:

~~~java
@Parameter(name = "customerId")
@PathVariable("customerId") String id
~~~

Khi annotation Spring đã khai báo đúng tên binding, thường không cần lặp lại <code>name</code> trong <code>@Parameter</code>. Chỉ thêm khi có lý do rõ ràng và luôn kiểm tra tài liệu được sinh ra.

## 5. Ví dụ cho từng loại tham số

### 5.1. Path variable

Tên placeholder trong mapping và tên binding phải tương ứng:

~~~java
@Operation(summary = "Lấy thông tin khách hàng")
@GetMapping("/customers/{customerId}")
CustomerResponse getCustomer(
        @PathVariable("customerId") String id) {
    // ...
}
~~~

OpenAPI cần công bố tham số ở vị trí <code>path</code>, tên <code>customerId</code> và <code>required: true</code>. Path parameter luôn bắt buộc theo quy tắc OpenAPI.

Không đổi tên placeholder thành <code>{id}</code> nhưng vẫn để binding là <code>customerId</code> nếu không có mapping tương ứng. Placeholder path là một phần của URL template mà Spring xử lý.

### 5.2. Query parameter

~~~java
@GetMapping("/orders")
List<OrderResponse> listOrders(
        @RequestParam(name = "status", required = false) String orderStatus,
        @RequestParam(name = "page", defaultValue = "0") int pageNumber) {
    // ...
}
~~~

Tên công bố là <code>status</code> và <code>page</code>, không phải <code>orderStatus</code> hay <code>pageNumber</code>. Tham số <code>status</code> có thể vắng mặt; <code>page</code> có giá trị mặc định do Spring áp dụng khi client không gửi.

### 5.3. Header và cookie

~~~java
@GetMapping("/profile")
ProfileResponse getProfile(
        @RequestHeader(name = "X-Request-Id", required = false) String requestId,
        @CookieValue(name = "session", required = false) String sessionToken) {
    // ...
}
~~~

Trong tài liệu, header được đặt ở vị trí <code>header</code> với tên <code>X-Request-Id</code>; cookie được đặt ở vị trí <code>cookie</code> với tên <code>session</code>. Tên biến Java chỉ giúp code dễ đọc và không thay thế tên HTTP.

## 6. Tổ chức quy ước đặt tên

Nên áp dụng quy ước rõ ràng để giảm khác biệt giữa controller, OpenAPI và tài liệu tích hợp:

| Vị trí | Quy ước gợi ý | Ví dụ |
|---|---|---|
| Path variable | camelCase, mô tả tài nguyên | <code>customerId</code> |
| Query parameter | camelCase, mô tả bộ lọc hoặc phân trang | <code>pageSize</code>, <code>sortBy</code> |
| Header | Theo quy ước header HTTP của hệ thống | <code>X-Request-Id</code> |
| Cookie | Tên ngắn, ổn định theo chức năng | <code>session</code> |
| Biến Java | camelCase theo quy ước Java | <code>customerId</code>, <code>pageSize</code> |

Không nhất thiết tên biến Java phải giống tên HTTP. Ví dụ, header <code>X-Request-Id</code> thường được ánh xạ vào biến Java <code>requestId</code>. Điều cần nhất quán là binding annotation và tên được công bố trong OpenAPI.

Với tên query hoặc header có quy ước riêng, hãy khai báo tường minh. Đừng để client phải đoán tên từ tên biến trong mã nguồn hoặc từ cách generator đặt tên.

## 7. Kiểm tra kết quả OpenAPI được sinh ra

Sau khi viết controller và annotation, kiểm tra tài liệu JSON tại endpoint mặc định:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Ví dụ một phần tài liệu mong đợi:

~~~yaml
paths:
  /customers:
    get:
      parameters:
        - name: keyword
          in: query
          required: true
          description: Từ khóa tìm kiếm theo tên hoặc email
          schema:
            type: string
~~~

Giá trị <code>required</code> trong ví dụ phụ thuộc vào cấu hình binding thực tế. Nếu <code>@RequestParam</code> là bắt buộc và không có default value, tài liệu thường thể hiện tham số là bắt buộc. Nếu khai báo <code>required = false</code> hoặc có giá trị mặc định, hãy xác minh kết quả sinh ra tương ứng.

Khi kiểm tra, đối chiếu các điểm:

1. Tên trong <code>parameters[].name</code> có khớp với tên client phải gửi không?
2. <code>in</code> có đúng là <code>path</code>, <code>query</code>, <code>header</code> hoặc <code>cookie</code> không?
3. Path parameter có đúng tên placeholder và được đánh dấu bắt buộc không?
4. Mô tả, ví dụ, kiểu dữ liệu và trạng thái bắt buộc có đúng với hành vi endpoint không?
5. Đổi tên biến Java có vô tình làm đổi tên hiển thị hoặc binding không?

Nếu tài liệu dùng tên tổng quát như <code>arg0</code>, <code>arg1</code> hoặc thiếu tên tham số, hãy kiểm tra annotation binding đã khai báo tên chưa và class đã được biên dịch với <code>-parameters</code> hay chưa.

## 8. Lỗi thường gặp và cách xử lý

**Đổi tên biến Java làm thay đổi tên query parameter.** Nếu annotation không khai báo tên rõ ràng, Spring có thể suy ra tên từ bytecode. Khai báo <code>@RequestParam("keyword")</code> hoặc bật metadata <code>-parameters</code> theo quy ước dự án.

**Tài liệu có tên khác với tên Spring binding.** Kiểm tra <code>@Parameter(name = ...)</code> và annotation binding. Hai giá trị phải nhất quán vì annotation OpenAPI không điều khiển việc bind request.

**Không khám phá được tên tham số khi chạy ứng dụng.** Kiểm tra compiler option <code>-parameters</code>, build lại module và bảo đảm artifact triển khai là bản mới. Với API quan trọng, có thể loại bỏ sự phụ thuộc này bằng tên binding tường minh.

**Nhầm tên biến với tên header.** Tên Java như <code>requestId</code> không có nghĩa client gửi header <code>requestId</code>. Nếu hợp đồng yêu cầu <code>X-Request-Id</code>, hãy ghi đúng tên trong <code>@RequestHeader</code>.

**Path placeholder và @PathVariable không khớp.** Kiểm tra chuỗi trong <code>@GetMapping</code> hoặc mapping tương ứng cùng giá trị <code>@PathVariable</code>. Tên placeholder phải được bind chính xác.

## 9. Danh sách rà soát trước khi công bố

- [ ] Từng tham số có tên binding rõ ràng và phù hợp với giao thức HTTP.
- [ ] Tên được công bố trong OpenAPI khớp với tên Spring thực sự đọc.
- [ ] Tên biến Java được xem là chi tiết nội bộ, có thể refactor độc lập khi binding tường minh.
- [ ] Nếu dựa vào khám phá tên, build đã bật <code>-parameters</code> và artifact được biên dịch lại.
- [ ] Path placeholder khớp với tên binding của <code>@PathVariable</code>.
- [ ] Header, cookie và query parameter có đúng vị trí, tên và trạng thái bắt buộc.
- [ ] <code>@Parameter</code> chỉ bổ sung metadata mô tả, không bị dùng nhầm để thay đổi binding runtime.
- [ ] Đã kiểm tra <code>/v3/api-docs</code> sau khi thay đổi controller hoặc compiler config.

## Tài liệu tham khảo

- [Spring Framework – StandardReflectionParameterNameDiscoverer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/StandardReflectionParameterNameDiscoverer.html): khám phá tên tham số từ metadata reflection của Java.
- [Spring Framework – @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html): cách bind query parameter trong Spring MVC.
- [Spring Framework – @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): binding tham số method với biến trong URI template.
- [Java Compiler – javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): tùy chọn <code>-parameters</code> để lưu metadata tên tham số.
- [Swagger Core – Parameter annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/Parameter.html): metadata OpenAPI cho tham số.
- [springdoc-openapi](https://springdoc.org/): sinh tài liệu OpenAPI từ ứng dụng Spring Boot.
