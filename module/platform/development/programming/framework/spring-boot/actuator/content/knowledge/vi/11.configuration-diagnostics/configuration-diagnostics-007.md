# Kiểm tra ánh xạ yêu cầu Servlet và Reactive bằng endpoint mappings

## 1. Ánh xạ yêu cầu giúp trả lời câu hỏi nào?

Một ứng dụng có lớp `OrderController` chưa bảo đảm rằng đường dẫn người dùng đang gọi đã được đăng ký đúng. Controller có thể nằm ngoài phạm vi quét; đường dẫn có thể khác dự kiến; yêu cầu có thể đúng URL nhưng sai HTTP method hoặc thiếu điều kiện về header.

**Ánh xạ yêu cầu (request mapping)** là quy tắc nối một yêu cầu HTTP với bộ phận xử lý của ứng dụng. **Bộ phận xử lý (handler)** có thể là phương thức controller, hàm xử lý, bộ phục vụ tài nguyên tĩnh hoặc endpoint Actuator.

Endpoint `mappings` cho biết các ánh xạ được ứng dụng đang chạy mô tả. Ta dùng nó để lần theo chuỗi:

~~~text
Ngữ cảnh ứng dụng
    → bộ điều phối
    → điều kiện khớp yêu cầu
    → phương thức hoặc hàm xử lý
~~~

Ba câu hỏi thực hành của bài:

1. Tuyến cần tìm có được đăng ký trong đúng ứng dụng/ngữ cảnh không?
2. Tuyến đó yêu cầu đường dẫn, HTTP method, tham số, header và kiểu nội dung nào?
3. Kết quả nằm ở nhánh Servlet/MVC hay Reactive/WebFlux, và giới hạn kết luận là gì?

Danh sách ánh xạ là bằng chứng về cấu hình định tuyến. Nó không thay thế việc gửi yêu cầu thật để kiểm tra quyền truy cập, dữ liệu đầu vào và hành vi nghiệp vụ.

## 2. Servlet và Reactive: giống mục đích, khác nhánh dữ liệu

Với **Spring MVC**, bộ điều phối trung tâm là `DispatcherServlet`. Với **Spring WebFlux**, vai trò điều phối do `DispatcherHandler` đảm nhiệm. Cả hai hỗ trợ controller dùng annotation; WebFlux còn có mô hình tuyến hàm `RouterFunction`.

Phản hồi của `GET /actuator/mappings` được nhóm theo ngữ cảnh, sau đó theo loại ánh xạ. Các vị trí cần nhận diện:

| Vị trí trong một mục `contexts.<id>.mappings` | Ý nghĩa thực hành |
| --- | --- |
| `dispatcherServlets.<beanName>[]` | Các ánh xạ qua bộ điều phối Spring MVC. |
| `dispatcherHandlers.<beanName>[]` | Các ánh xạ qua bộ điều phối Spring WebFlux. |
| `servlets[]` | Các Servlet được đăng ký và mẫu URL của chúng. |
| `servletFilters[]` | Các Servlet Filter và phạm vi đăng ký theo URL/tên Servlet. |

`contexts` có khóa là mã ngữ cảnh; một ngữ cảnh có thể có `parentId`. Tên bộ điều phối cũng là dữ liệu, không phải khóa cố định cho mọi dự án. Ví dụ thường gặp là `dispatcherServlet` ở MVC và `webHandler` ở WebFlux.

Xem [hợp đồng phản hồi mappings của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/mappings.html). Chỉ đọc `contexts.application.mappings.dispatcherServlets.dispatcherServlet` sẽ bỏ sót các ứng dụng có tên ngữ cảnh khác, nhiều bộ điều phối hoặc dùng WebFlux.

Không suy ra WebFlux chỉ từ việc một phương thức trả về `Mono`. Spring MVC cũng có hỗ trợ một số kiểu trả về bất đồng bộ/phản ứng; hãy kiểm tra kiểu ứng dụng và nhánh dữ liệu thực tế.

## 3. Bài thực hành Servlet với một controller có nhiều điều kiện

Ví dụ dùng **Java 21, Gradle 8.5 và Spring Boot 3.3.0** để cố định môi trường thực hành. Nội dung cấu hình dưới đây dành cho Boot 3.3; không lấy thuộc tính của dòng Boot mới hơn để thay trực tiếp vào ví dụ.

Tạo dự án độc lập:

~~~text
mappings-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lab/
    │   ├── MappingsLabApplication.java
    │   └── OrderController.java
    └── resources/application.properties
~~~

### 3.1. Tệp cấu hình dự án

Nội dung `settings.gradle`:

~~~groovy
rootProject.name = 'mappings-lab'
~~~

Nội dung `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'lab'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

BOM `spring-boot-dependencies` quản lý phiên bản các thư viện dùng trong ví dụ. Starter Web tạo ứng dụng MVC; Actuator bổ sung endpoint quản trị.

Nội dung `src/main/resources/application.properties`:

~~~properties
spring.application.name=mappings-lab
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,mappings
management.endpoint.mappings.enabled=true
~~~

Trong Boot 3.3, endpoint được bật và endpoint được công bố qua HTTP là hai trạng thái khác nhau. Mặc định chỉ `health` được công bố qua HTTP; đưa `mappings` vào `include` để đọc nó. Nếu `exclude` cũng chứa `mappings`, quy tắc loại trừ được ưu tiên. Xem [bật và công bố endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#exposing-endpoints).

Ví dụ chỉ lắng nghe trên loopback và không thêm Spring Security. Trong ứng dụng có bảo mật, vẫn phải cấp quyền đọc endpoint thích hợp. Dữ liệu này có thể bộc lộ các tuyến nội bộ và tên lớp xử lý.

### 3.2. Lớp khởi động

Nội dung `src/main/java/lab/MappingsLabApplication.java`:

~~~java
package lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(proxyBeanMethods = false)
public class MappingsLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(MappingsLabApplication.class, args);
    }
}
~~~

Lớp khởi động nằm trong gói `lab`, cùng cây gói với controller để việc quét thành phần tìm thấy controller.

### 3.3. Controller cần quan sát

Nội dung `src/main/java/lab/OrderController.java`:

~~~java
package lab;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    @GetMapping(value = "/{id}", produces = "application/json")
    public Map<String, Object> find(@PathVariable("id") long id) {
        return Map.of("id", id, "state", "READY");
    }

    @PostMapping(
            consumes = "application/json",
            produces = "application/json",
            params = "mode=check",
            headers = "X-Lab=on")
    public Map<String, Object> check(@RequestBody Map<String, Object> body) {
        return Map.of("checked", true, "input", body);
    }
}
~~~

Có hai quy tắc:

- `find`: nhận `GET /api/orders/{id}` và tạo phản hồi JSON.
- `check`: nhận `POST /api/orders`, cần tham số `mode=check`, header `X-Lab=on`, thân yêu cầu JSON và khả năng trả JSON cho bên gọi.

Đường dẫn mức lớp và mức phương thức kết hợp thành đường dẫn của thao tác. Ở đây `@PathVariable("id")` chỉ rõ tên biến, nên không phụ thuộc vào việc suy ra tên tham số Java.

### 3.4. Chạy và lấy tài liệu ánh xạ

Với Gradle 8.5 đã cài, tạo wrapper một lần tại thư mục dự án:

~~~powershell
gradle wrapper --gradle-version 8.5
~~~

Chạy trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Trên Linux/macOS, dùng `./gradlew bootRun`. Lần đầu cần tải Gradle và các thư viện. Đây là ứng dụng Spring có phụ thuộc thư viện; không biên dịch một tệp controller bằng `javac` trần rồi mong khởi chạy đủ hệ thống.

Sau khi ứng dụng khởi động, mở PowerShell khác:

~~~powershell
$document = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/mappings'
$document.contexts.PSObject.Properties.Name
~~~

Hoặc lưu phản hồi nguyên bản trên Windows:

~~~powershell
curl.exe --fail --silent --show-error 'http://127.0.0.1:8080/actuator/mappings' --output mappings.json
~~~

Một phần tài liệu MVC của ví dụ có dạng sau. Trích lược này chỉ giữ ánh xạ POST để tập trung vào điều kiện; ứng dụng thực còn có GET, các tuyến Actuator và có thể có tuyến mặc định khác:

~~~json
{
  "contexts": {
    "mappings-lab": {
      "mappings": {
        "dispatcherServlets": {
          "dispatcherServlet": [
            {
              "handler": "lab.OrderController#check(Map)",
              "predicate": "{POST [/api/orders], params [mode=check], headers [X-Lab=on], consumes [application/json], produces [application/json]}",
              "details": {
                "handlerMethod": {
                  "className": "lab.OrderController",
                  "name": "check",
                  "descriptor": "(Ljava/util/Map;)Ljava/util/Map;"
                },
                "requestMappingConditions": {
                  "consumes": [
                    {
                      "mediaType": "application/json",
                      "negated": false
                    }
                  ],
                  "headers": [
                    {
                      "name": "X-Lab",
                      "value": "on",
                      "negated": false
                    }
                  ],
                  "methods": [
                    "POST"
                  ],
                  "params": [
                    {
                      "name": "mode",
                      "value": "check",
                      "negated": false
                    }
                  ],
                  "patterns": [
                    "/api/orders"
                  ],
                  "produces": [
                    {
                      "mediaType": "application/json",
                      "negated": false
                    }
                  ]
                }
              }
            }
          ]
        }
      }
    }
  }
}
~~~

Các trường của bản ghi POST đã được đối chiếu bằng bộ cung cấp dữ liệu mappings của Boot 3.3.0. Thứ tự bản ghi, khóa JSON và cách trình bày chuỗi `predicate` không phải thứ tự ưu tiên định tuyến để công cụ của ta dựa vào.

## 4. Đọc một bản ghi theo điều kiện khớp

Một bản ghi thường có:

- `handler`: mô tả ngắn bộ phận xử lý.
- `predicate`: chuỗi mô tả điều kiện, thuận tiện để đọc.
- `details.handlerMethod`: thông tin lớp, tên và descriptor của phương thức, nếu có.
- `details.requestMappingConditions`: các điều kiện có cấu trúc cho ánh xạ controller, nếu có.

Đối với ánh xạ POST vừa xem, đọc từng nhóm:

| Trường điều kiện | Giá trị ví dụ | Câu hỏi cần kiểm tra ở yêu cầu |
| --- | --- | --- |
| `patterns` | `/api/orders` | Đường dẫn mà bộ điều phối nhận có đúng không? |
| `methods` | `POST` | Có đang gửi đúng HTTP method không? |
| `params` | `mode=check` | Có tham số đúng giá trị không? |
| `headers` | `X-Lab=on` | Có header đúng điều kiện không? |
| `consumes` | `application/json` | `Content-Type` của thân gửi lên có phù hợp không? |
| `produces` | `application/json` | Bên gọi có chấp nhận dạng phản hồi này không, thường qua `Accept`? |

`consumes` nói về nội dung **gửi vào**, còn `produces` nói về nội dung **trả ra**. Đổi header `Accept` không sửa được một lỗi do `Content-Type` sai.

Trong nhóm media type, `negated=true` biểu thị điều kiện phủ định. Ví dụ `!application/xml` không có nghĩa là chỉ chấp nhận JSON. Với tham số/header, cần đọc đồng thời `name`, `value` và `negated`; một điều kiện có thể kiểm tra sự có mặt, vắng mặt hoặc giá trị.

Các nhóm ràng buộc trong ví dụ cần đồng thời thỏa mãn. Không diễn giải mọi mảng thành phép AND: chẳng hạn danh sách HTTP method có thể cho phép một trong các method được liệt kê. Mảng `methods` rỗng của một ánh xạ không giới hạn method không có nghĩa là “không method nào được gọi”.

Xem [RequestMapping của Spring Framework 6.1.8](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html) để đối chiếu ý nghĩa các thuộc tính.

`descriptor` như `(J)Ljava/util/Map;` mô tả chữ ký phương thức ở dạng descriptor; nó không phải schema JSON của yêu cầu hay phản hồi. Cũng không nên tách chuỗi `predicate` bằng dấu phẩy để xây bộ phân tích lâu dài: dùng các trường có cấu trúc khi chúng có mặt.

Một ánh xạ `GET` còn có thể được framework dùng cho yêu cầu `HEAD`; đừng kết luận khả năng xử lý `HEAD` chỉ bằng việc tìm chuỗi `HEAD` trong mảng.

## 5. Chuyển sang Reactive và kiểm tra thêm tuyến hàm

### 5.1. Thay starter, giữ ví dụ controller

Trong `build.gradle`, **thay**:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
~~~

bằng:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-webflux'
~~~

Giữ Actuator, BOM và các tệp Java của ví dụ. Controller trả về `Map` vẫn được WebFlux hỗ trợ cho công việc nhỏ, không chặn luồng như ví dụ này; không bắt buộc phải đổi kiểu trả về thành `Mono` chỉ để quan sát nhánh Reactive.

Không giữ cả hai starter trong thí nghiệm so sánh này. Khi MVC và WebFlux cùng có mặt, Boot thường tự cấu hình MVC theo quy tắc lựa chọn mặc định. Đó là lý do chỉ thêm thư viện WebFlux không chứng minh ứng dụng đã chuyển sang Reactive. Xem [ứng dụng Reactive của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html#web.reactive.webflux).

Dừng tiến trình cũ, chạy lại ứng dụng và lấy **phản hồi mới**. Việc chỉ lọc lại biến `$document` cũ không cập nhật dữ liệu.

Nhánh cần quan sát trở thành `dispatcherHandlers`. Trích lược chỉ giữ GET và một số trường:

~~~json
{
  "contexts": {
    "mappings-lab": {
      "mappings": {
        "dispatcherHandlers": {
          "webHandler": [
            {
              "handler": "lab.OrderController#find(long)",
              "predicate": "{GET /api/orders/{id}, produces [application/json]}",
              "details": {
                "handlerMethod": {
                  "className": "lab.OrderController",
                  "name": "find",
                  "descriptor": "(J)Ljava/util/Map;"
                },
                "requestMappingConditions": {
                  "methods": [
                    "GET"
                  ],
                  "patterns": [
                    "/api/orders/{id}"
                  ]
                }
              }
            }
          ]
        }
      }
    }
  }
}
~~~

Cấu trúc điều kiện của controller vẫn giúp kiểm tra đường dẫn, method và media type. Điểm khác cần nhận diện là nơi nhóm dữ liệu và loại bộ điều phối.

### 5.2. Bổ sung tuyến hàm WebFlux

Chỉ ở biến thể Reactive, thêm `src/main/java/lab/ReactiveRoutes.java`:

~~~java
package lab;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class ReactiveRoutes {
    @Bean
    RouterFunction<ServerResponse> statusRoute() {
        return RouterFunctions.route()
                .GET("/api/status", request -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of("state", "READY")))
                .build();
    }
}
~~~

Sau khi khởi động lại, `GET /api/status` trả về đối tượng JSON có `state` bằng `READY`.

Tuyến này được khai báo bằng hàm, không phải phương thức controller có `@GetMapping`. Trong dữ liệu Boot 3.3.0 của thí nghiệm:

- `predicate` mô tả `(GET && /api/status)`.
- `details.handlerFunction.className` mô tả lớp của hàm xử lý.
- `details.handlerMethod` và `details.requestMappingConditions` không có dữ liệu cho bản ghi tuyến hàm này.

Nếu hàm được tạo bằng lambda, tên lớp sinh ra có thể thay đổi giữa các lần chạy. Đừng dùng toàn bộ tên lớp lambda làm mã định danh ổn định cho tuyến.

Một công cụ chỉ giữ bản ghi có `handlerMethod` sẽ bỏ sót tuyến hàm. Một công cụ chỉ tìm trong `requestMappingConditions.patterns` cũng sẽ bỏ sót ví dụ `/api/status`. Cần giữ lại `predicate` và thông tin `handlerFunction` để khảo sát nhóm này. Xem [mô hình tuyến hàm của WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).

## 6. Lọc cả hai nhánh bằng PowerShell

Các đoạn dưới dùng PowerShell 5.1+ hoặc 7, không bật chế độ StrictMode. Chúng thao tác trên bản JSON vừa lấy, không sửa cấu hình máy chủ.

### 6.1. Chuyển dữ liệu thành các bản ghi dễ lọc

Sau mỗi lần chạy lại ứng dụng, lấy lại:

~~~powershell
$document = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/mappings'
~~~

Rồi chạy:

~~~powershell
$rows = @(
    foreach ($context in $document.contexts.PSObject.Properties) {
        foreach ($kind in @('dispatcherServlets', 'dispatcherHandlers')) {
            $dispatchers = $context.Value.mappings.$kind
            if ($null -eq $dispatchers) { continue }

            foreach ($dispatcher in $dispatchers.PSObject.Properties) {
                foreach ($mapping in @($dispatcher.Value)) {
                    if ($null -eq $mapping) { continue }
                    $conditions = $mapping.details.requestMappingConditions

                    [pscustomobject]@{
                        Context       = $context.Name
                        Kind          = $kind
                        Dispatcher    = $dispatcher.Name
                        Methods       = @($conditions.methods)
                        Patterns      = @($conditions.patterns)
                        Params        = @($conditions.params)
                        Headers       = @($conditions.headers)
                        Consumes      = @($conditions.consumes)
                        Produces      = @($conditions.produces)
                        Handler       = $mapping.handler
                        Predicate     = $mapping.predicate
                        HandlerClass  = $mapping.details.handlerMethod.className
                        HandlerMethod = $mapping.details.handlerMethod.name
                        FunctionClass = $mapping.details.handlerFunction.className
                    }
                }
            }
        }
    }
)
~~~

Đoạn này giữ mã ngữ cảnh, loại nhánh và tên bộ điều phối. Những mục không có chi tiết phương thức vẫn được giữ lại. Nó chỉ tổng hợp hai nhánh dispatcher, không gộp các mục `servlets`/`servletFilters` thành tuyến controller.

### 6.2. Tìm mẫu đường dẫn của controller

~~~powershell
$rows |
    Where-Object { $_.Patterns -ccontains '/api/orders/{id}' } |
    Select-Object Context, Kind, Dispatcher,
        @{Name='Methods'; Expression={ $_.Methods -join ',' }},
        Handler
~~~

Trong ví dụ Servlet có một bản ghi GET tại `dispatcherServlets`; ở biến thể Reactive, bản ghi GET nằm tại `dispatcherHandlers`.

`-ccontains` kiểm tra phần tử chuỗi phân biệt hoa thường. Đây là tìm **mẫu đã đăng ký**, không phải thực hiện thuật toán so khớp URL. Chuỗi `/api/orders/42` không bằng mẫu `/api/orders/{id}`; việc lọc không thấy chuỗi URL cụ thể không chứng minh tuyến bị thiếu.

### 6.3. Xem toàn bộ điều kiện của thao tác POST

~~~powershell
$postMappings = @(
    $rows | Where-Object {
        $_.Patterns -ccontains '/api/orders' -and
        $_.Methods -ccontains 'POST'
    }
)

$postMappings |
    Select-Object Context, Params, Headers, Consumes, Produces |
    ConvertTo-Json -Depth 6
~~~

Đối chiếu bốn dữ kiện: `mode=check`, `X-Lab=on`, nhận JSON và trả JSON. Giữ `-Depth 6` để cấu trúc con được xuất đủ rõ thay vì chỉ thấy tên kiểu đối tượng PowerShell.

Nếu có nhiều ngữ cảnh hoặc bộ điều phối cùng đăng ký một mẫu, hãy lọc thêm `Context`/`Dispatcher` theo dữ liệu thực tế trước khi kết luận.

### 6.4. Tìm theo lớp controller

~~~powershell
$rows |
    Where-Object { $_.HandlerClass -ceq 'lab.OrderController' } |
    Select-Object Context, Kind, HandlerMethod, Predicate
~~~

Ví dụ có hai thao tác `find` và `check`. Không giả định thứ tự chúng xuất hiện là thứ tự Spring lựa chọn.

### 6.5. Giữ lại và khảo sát tuyến hàm

~~~powershell
$rows |
    Where-Object {
        $_.FunctionClass -and $_.Predicate -clike '*/api/status*'
    } |
    Select-Object Context, Kind, Dispatcher, Predicate, FunctionClass
~~~

Trong biến thể Reactive đã thêm `ReactiveRoutes`, truy vấn tìm được tuyến hàm. Tìm chuỗi trong `predicate` ở đây là công cụ khảo sát cho con người, không phải bộ đánh giá điều kiện HTTP tương đương Spring.

### 6.6. Xem Servlet và Filter như một lớp đăng ký khác

Với biến thể Servlet:

~~~powershell
foreach ($context in $document.contexts.PSObject.Properties) {
    Write-Output ('Context: ' + $context.Name)
    $context.Value.mappings.servlets | ConvertTo-Json -Depth 5
    $context.Value.mappings.servletFilters | ConvertTo-Json -Depth 5
}
~~~

Một `DispatcherServlet` được đăng ký cho `/` không có nghĩa là mỗi URL đều có phương thức controller tương ứng. Tương tự, Filter đăng ký cho `/*` chỉ mô tả phạm vi Filter; nó không phải một API nghiệp vụ.

Danh sách Servlet Filter cũng không trình bày đầy đủ các bộ lọc nội bộ trong từng `SecurityFilterChain`. Ứng dụng WebFlux dùng cơ chế lọc khác; vắng `servletFilters` không chứng minh hệ thống không có bảo mật.

## 7. Gửi yêu cầu và đối chiếu kết quả

### 7.1. Yêu cầu thành công

GET bằng PowerShell:

~~~powershell
$getRequest = @{
    Uri = 'http://127.0.0.1:8080/api/orders/42'
    Headers = @{ Accept = 'application/json' }
}
Invoke-RestMethod @getRequest | ConvertTo-Json
~~~

Phản hồi chứa hai giá trị `id=42` và `state=READY`. Không dựa vào thứ tự khóa JSON của `Map`.

POST:

~~~powershell
$postRequest = @{
    Method = 'Post'
    Uri = 'http://127.0.0.1:8080/api/orders?mode=check'
    Headers = @{ 'X-Lab' = 'on'; Accept = 'application/json' }
    ContentType = 'application/json'
    Body = '{"name":"book"}'
}
Invoke-RestMethod @postRequest | ConvertTo-Json -Depth 5
~~~

Kết quả JSON biểu diễn:

~~~json
{
  "checked": true,
  "input": {
    "name": "book"
  }
}
~~~

Phương thức của ví dụ không gắn `@ResponseStatus(CREATED)` hay trả `ResponseEntity` với mã khác, nên yêu cầu POST hợp lệ này trả **200**, không tự động thành 201 chỉ vì dùng POST.

### 7.2. Thay một điều kiện mỗi lần

Các trường hợp dưới đã được kiểm tra bằng yêu cầu giả lập MVC và WebFlux với controller của bài:

| Yêu cầu hoặc thay đổi | Kết quả của ví dụ | Cách lần lại dữ liệu mappings |
| --- | --- | --- |
| `GET /api/orders/42`, chấp nhận JSON | 200 | GET, mẫu `/{id}`, tạo JSON. |
| `PUT /api/orders/42` | 405 | Có mẫu đường dẫn nhưng thao tác được khai báo là GET. |
| `GET /api/orders/42`, `Accept: text/plain` | 406 | Dạng phản hồi chấp nhận không phù hợp `produces`. |
| POST đúng URL, `mode`, header, nhưng `Content-Type: text/plain` và thân `hello` | 415 | `consumes` yêu cầu JSON. |

Ví dụ lệnh xem mã 405 trên Windows:

~~~powershell
curl.exe -i -X PUT 'http://127.0.0.1:8080/api/orders/42'
~~~

Ví dụ mã 406:

~~~powershell
curl.exe -i 'http://127.0.0.1:8080/api/orders/42' -H 'Accept: text/plain'
~~~

Ví dụ mã 415, vẫn giữ đúng tham số và header để chỉ thay kiểu nội dung:

~~~powershell
curl.exe -i -X POST 'http://127.0.0.1:8080/api/orders?mode=check' -H 'X-Lab: on' -H 'Content-Type: text/plain' --data-raw 'hello'
~~~

Các mã trên mô tả ứng dụng mẫu không có bảo mật hoặc bộ xử lý lỗi tùy biến. Trong hệ thống thật, lớp proxy, Filter/WebFilter, cấu hình bảo mật hoặc xử lý ngoại lệ có thể can thiệp trước/sau bước định tuyến.

Đừng quy mọi lỗi thành 404. Ví dụ thiếu điều kiện tham số có thể dẫn đến lỗi yêu cầu không hợp lệ; lỗi chuyển `id` sang số, JSON sai hoặc kiểm tra dữ liệu cũng thuộc các bước khác với việc có mẫu URL. Hãy đối chiếu chính yêu cầu và lỗi trả về.

## 8. Quy trình chẩn đoán khi tuyến không như dự kiến

### Không lấy được tài liệu mappings

Kiểm tra ứng dụng đã khởi động, URL quản trị, việc bật/công bố `mappings`, rồi xác thực và quyền đọc. `401`/`403` không phải bằng chứng controller chưa đăng ký.

Endpoint tích hợp của bài trả tài liệu qua `GET /actuator/mappings`. Không tự giả định có thao tác `/actuator/mappings/orders` hay bộ lọc chuẩn `?path=/api/orders`; lọc phía bên đọc như phần 6.

### Đã có JSON nhưng không thấy tuyến

1. Xem tất cả mã ngữ cảnh và cả hai nhánh dispatcher.
2. Xác định ứng dụng thực sự chạy MVC hay WebFlux.
3. Kiểm tra phạm vi quét, controller có được đăng ký và điều kiện cấu hình có cho phép tạo thành phần đó không.
4. Với tuyến hàm, tìm `handlerFunction`/`predicate` thay vì chỉ tìm `handlerMethod`.
5. Xác nhận đang đọc đúng tiến trình, cổng và dữ liệu mới sau lần chạy lại.

Một tuyến `/**` phục vụ tài nguyên tĩnh không thay thế bằng chứng về controller cần tìm. Có nhiều mục trong tài liệu cũng không đồng nghĩa có nhiều API nghiệp vụ.

### Có mẫu đường dẫn nhưng gọi từ bên ngoài vẫn lỗi

Phân biệt URL bên gọi nhìn thấy với đường dẫn ứng dụng/bộ điều phối dùng để khớp. Những cấu hình thường cần đối chiếu:

| Thành phần | Điều cần xác nhận |
| --- | --- |
| Reverse proxy hoặc gateway | Có bỏ/thêm tiền tố hoặc chuyển tiếp sang dịch vụ khác không? |
| `server.servlet.context-path` | Ứng dụng Servlet có tiền tố ngữ cảnh nào? |
| `spring.mvc.servlet.path` | DispatcherServlet có đường dẫn đăng ký riêng không? |
| `spring.webflux.base-path` | Biến thể WebFlux có đường dẫn gốc nào? |
| `management.endpoints.web.base-path` | Tiền tố Actuator có còn là `/actuator` không? |
| `management.server.port` | API quản trị có dùng cổng riêng không? |

Không mặc định rằng `patterns` luôn là một URL công khai đầy đủ để nối trực tiếp với tên miền. Hãy kiểm tra cấu hình từng lớp và yêu cầu thực sự đến ứng dụng. Xem [đường dẫn và cổng quản trị trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### Thấy hai mục gần giống nhau hoặc ứng dụng không khởi động

Cùng mẫu URL chưa đủ kết luận trùng ánh xạ: hai thao tác có thể khác method, tham số hoặc media type. So sánh đủ điều kiện và lớp xử lý.

Ngược lại, nếu khai báo xung đột khiến Spring không tạo được ngữ cảnh, endpoint của ứng dụng đó chưa sẵn sàng để đọc. Khi ấy dùng lỗi khởi động để xác định hai khai báo xung đột; không chờ mappings giải thích từ một ứng dụng chưa chạy.

### Có ánh xạ không đồng nghĩa đủ bằng chứng vận hành

Tài liệu này không cho biết:

- Người dùng cụ thể có quyền gọi tuyến hay không.
- Tuyến đã nhận bao nhiêu yêu cầu hoặc mất bao lâu.
- Thân JSON cần những trường nghiệp vụ nào, có hợp lệ không.
- Một yêu cầu cụ thể đã qua chuỗi xử lý nào hoặc thất bại ở đâu.
- Mọi quy tắc của bộ định tuyến tùy biến đều có bản mô tả chi tiết.

Kết hợp dữ liệu ánh xạ với yêu cầu kiểm thử, log, quan sát hiệu năng hoặc tài liệu hợp đồng API theo câu hỏi thực tế. Việc đọc mappings không thêm, xóa hay sửa tuyến.

## 9. Bài tập tự kiểm chứng

**Bài 1 — Xác định bộ điều phối.** Chạy lần lượt hai biến thể. Ghi lại `Context`, `Kind` và `Dispatcher` của thao tác `find`.

Đối chiếu: MVC có `dispatcherServlets`; WebFlux có `dispatcherHandlers`. Tên ngữ cảnh/bộ điều phối lấy từ dữ liệu thực tế, không mã hóa cứng trong câu trả lời.

**Bài 2 — Từ điều kiện đến yêu cầu.** Tìm bản ghi POST và tự viết yêu cầu thành công từ sáu nhóm điều kiện.

Đối chiếu: POST đúng đường dẫn; `mode=check`; `X-Lab=on`; thân JSON và chấp nhận JSON. Sau đó thay riêng `Content-Type` để kiểm tra nguyên nhân 415.

**Bài 3 — Đừng bỏ sót tuyến hàm.** Ở biến thể WebFlux, tìm `/api/status` bằng cả truy vấn mẫu controller và truy vấn tuyến hàm.

Đối chiếu: truy vấn chỉ xét `requestMappingConditions.patterns` không tìm được tuyến hàm của ví dụ; truy vấn giữ `predicate` và `FunctionClass` tìm được nó.

**Bài 4 — Đổi đường dẫn có kiểm soát.** Đổi `@RequestMapping("/api/orders")` thành `@RequestMapping("/api/purchases")`, chạy lại, lấy JSON mới và gửi lại yêu cầu GET.

Đối chiếu: mẫu controller đổi thành `/api/purchases/{id}`; `/api/status` của tuyến hàm vẫn độc lập. Cần cập nhật cả yêu cầu kiểm thử và chuỗi mẫu của truy vấn.

**Bài 5 — Giới hạn kết luận.** Một bản ghi tồn tại nhưng bên gọi nhận 403; một ứng dụng khác có trả `Mono` nhưng dữ liệu ở `dispatcherServlets`. Giải thích hai trường hợp.

Đối chiếu: đăng ký tuyến và quyền truy cập là hai lớp khác nhau; kiểu trả về của một phương thức không quyết định một mình lựa chọn MVC/WebFlux của cả ứng dụng.

Mục tiêu hoàn thành bài là đọc được tuyến trong đúng ngữ cảnh và bộ điều phối, dựng yêu cầu từ đủ điều kiện, kiểm tra phản hồi và giữ kết luận trong phạm vi bằng chứng mappings thực sự cung cấp.
