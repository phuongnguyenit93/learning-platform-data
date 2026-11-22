# Tham số bị mất tên và cấu hình biên dịch -parameters

Springdoc-openapi đọc mapping của Spring MVC/WebFlux và metadata của method controller để tạo OpenAPI Parameter Object. Nếu tên tham số Java không được giữ trong bytecode, tài liệu có thể thiếu tên, dùng tên thay thế hoặc không khớp với tên mà client mong đợi. Tình trạng này thường xuất hiện sau khi nâng JDK, Spring Framework hoặc chuyển sang Spring Boot 3.

Giải pháp nền tảng là biên dịch source Java với tùy chọn -parameters để javac ghi tên tham số vào thuộc tính MethodParameters trong file class. Ngoài ra, có thể khai báo tên rõ ràng trong annotation Spring như PathVariable, RequestParam hoặc RequestHeader. Với API công khai, tên tường minh giúp hợp đồng ổn định ngay cả khi tên biến Java được refactor.

## 1. Triệu chứng thường gặp

Một controller có thể được viết như sau:

~~~java
@GetMapping("/orders")
List<OrderResponse> findOrders(
        @RequestParam String status,
        @RequestParam Integer page) {
    // ...
}
~~~

Developer mong đợi OpenAPI document có hai query parameter tên status và page. Tuy nhiên, nếu tên tham số không được lưu trong bytecode hoặc framework không thể khám phá chúng, document có thể:

- Thiếu tên parameter hoặc không tạo đúng parameter.
- Hiển thị tên thay thế như arg0 hoặc arg1.
- Sinh tên không ổn định giữa các lần build.
- Không khớp với tên query parameter mà Spring runtime thực sự nhận.
- Khiến Spring báo lỗi lúc bind request nếu annotation dựa vào tên tham số nhưng metadata tên không có.

Triệu chứng chính xác phụ thuộc phiên bản Spring, cách khai báo annotation, compiler và phiên bản springdoc. Không giả định mọi dự án đều hiển thị arg0; hãy kiểm tra OpenAPI JSON và bytecode của chính ứng dụng.

## 2. Vì sao tên tham số có thể biến mất?

Trong source Java, compiler biết tên biến như status hoặc page. Tuy nhiên, file .class không mặc định phải lưu tên tham số method theo cách reflection có thể truy cập.

Tùy chọn javac -parameters yêu cầu compiler ghi tên tham số vào metadata MethodParameters. Khi chạy, Java Reflection có thể đọc tên qua java.lang.reflect.Parameter.getName() và kiểm tra tên có hiện diện bằng isNamePresent().

Nếu không có metadata này, getName() có thể trả về tên tổng hợp như arg0 và isNamePresent() trả false. Spring Framework và springdoc có thể không suy ra được tên cần dùng từ method signature.

Spring Framework 6.1 loại bỏ cơ chế dự phòng khám phá tên tham số từ LocalVariableTable của bytecode. Vì vậy, với ứng dụng dùng Spring Framework 6.1 trở lên, cần biên dịch với -parameters nếu muốn framework suy luận tên method parameter. Đây là điểm cần chú ý khi nâng lên các bản Spring Boot quản lý Spring Framework 6.1.

## 3. Phân biệt tên method parameter và tên property trong DTO

Không phải mọi tên xuất hiện trong OpenAPI đều lấy từ MethodParameters.

| Loại tên | Ví dụ | Nguồn metadata chính |
|---|---|---|
| Path parameter | orderId trong /orders/{orderId} | Mapping và PathVariable |
| Query parameter | page trong ?page=2 | RequestParam hoặc tên method parameter |
| Header parameter | X-Tenant | RequestHeader |
| Cookie parameter | sessionId | CookieValue |
| Field trong request body | customerCode trong JSON | DTO, Jackson, record component, Schema |
| Field trong response body | createdAt trong JSON | DTO, Jackson, record component, Schema |

Tùy chọn -parameters chủ yếu ảnh hưởng tên tham số của method. Nó không đổi tên property của DTO và không thay thế Jackson annotation như JsonProperty.

Ví dụ:

~~~java
public record SearchRequest(
        String customerCode,
        Integer page
) {}

@PostMapping("/orders/search")
Mono<List<OrderResponse>> search(@RequestBody SearchRequest request) {
    // ...
}
~~~

Tên customerCode và page trong schema request body được suy ra từ cấu trúc DTO/record và cấu hình serialization. Nếu chỉ các property của DTO bị sai tên, hãy kiểm tra Jackson, JsonProperty, getter/field access và Schema thay vì chỉ bật -parameters.

## 4. Kiểm tra annotation có dựa vào tên suy luận hay không

Các annotation Spring có thể nhận tên tường minh hoặc để framework suy luận từ tên method parameter.

Ví dụ dựa vào suy luận:

~~~java
@GetMapping("/orders")
List<OrderResponse> findOrders(
        @RequestParam String status,
        @RequestHeader String tenant) {
    // ...
}
~~~

Ví dụ khai báo tường minh:

~~~java
@GetMapping("/orders")
List<OrderResponse> findOrders(
        @RequestParam(name = "status") String state,
        @RequestHeader(name = "X-Tenant") String tenant) {
    // ...
}
~~~

Ở ví dụ thứ hai, tên biến Java state không quyết định tên query parameter. Spring sử dụng name được khai báo trong RequestParam là status. Header được công bố là X-Tenant dù biến Java tên tenant.

Các annotation thường có thuộc tính name hoặc value để khai báo rõ:

| Annotation | Ví dụ khai báo |
|---|---|
| PathVariable | PathVariable("orderId") |
| RequestParam | RequestParam(name = "page") |
| RequestHeader | RequestHeader(name = "X-Tenant") |
| CookieValue | CookieValue(name = "sessionId") |

Tên tường minh giảm phụ thuộc vào compiler metadata và giữ hợp đồng HTTP ổn định khi đổi tên biến Java.

## 5. Bật -parameters trong Maven

Với Maven Compiler Plugin, cấu hình parameters là true:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Nếu project đã quản lý compiler plugin ở parent POM hoặc pluginManagement, đặt cấu hình vào đúng nơi đang được kế thừa. Không khai báo thêm một plugin version tùy tiện nếu Spring Boot parent đã quản lý phiên bản tương thích.

Có thể kiểm tra cấu hình hiệu lực bằng:

~~~bash
mvn help:effective-pom
~~~

Tìm phần maven-compiler-plugin và xác nhận parameters được bật. Sau đó clean compile để các file class cũ được tạo lại:

~~~bash
mvn clean test
~~~

Chỉ sửa pom.xml mà không biên dịch lại module chứa controller thì file class cũ vẫn có thể thiếu MethodParameters.

## 6. Bật -parameters trong Gradle Kotlin DSL

Với build.gradle.kts:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Cấu hình này áp dụng cho các task JavaCompile trong project hiện tại, bao gồm compileJava và các source set Java khác. Nếu controller nằm trong module riêng, cần đặt cấu hình ở module thực sự biên dịch controller hoặc cấu hình dùng chung được các module đó áp dụng.

Sau khi thay đổi:

~~~bash
./gradlew clean test
~~~

## 7. Bật -parameters trong Gradle Groovy DSL

Với build.gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

Nếu dự án dùng convention plugin, đưa cấu hình vào convention plugin để mọi module Java liên quan dùng cùng quy tắc. Tránh chỉ cấu hình module ứng dụng trong khi controller được biên dịch từ một module thư viện khác.

Sau khi cập nhật:

~~~bash
./gradlew clean test
~~~

## 8. Bảo đảm cấu hình áp dụng cho đúng module

Trong dự án multi-module, module chứa controller có thể được build độc lập rồi đóng gói thành JAR. Khi đó, bật -parameters chỉ ở module boot application không thay đổi bytecode đã biên dịch của module controller.

Kiểm tra:

1. Xác định class controller được nạp từ module hoặc JAR nào.
2. Bật -parameters trong cấu hình compile của module đó.
3. Clean và build lại module chứa controller.
4. Nếu module được publish thành artifact nội bộ, publish lại artifact đã build với metadata mới.
5. Cập nhật dependency của ứng dụng để dùng đúng artifact mới.
6. Kiểm tra bytecode từ đúng JAR đang được ứng dụng sử dụng.

Không nhầm class trong target/classes của workspace với class thực sự được nạp từ một JAR cũ trong runtime classpath.

## 9. Khai báo tên tường minh cho path parameter

Với path parameter, OpenAPI yêu cầu tên parameter khớp placeholder trong path. Nên khai báo rõ cả mapping và annotation:

~~~java
@GetMapping("/orders/{orderId}")
OrderResponse getOrder(
        @PathVariable("orderId") UUID id) {
    // ...
}
~~~

Tên biến Java là id, còn tên trên HTTP path là orderId. Annotation làm rõ ranh giới này. OpenAPI document cần có path /orders/{orderId} và parameter:

~~~yaml
name: orderId
in: path
required: true
schema:
  type: string
  format: uuid
~~~

Nếu chỉ đổi tên biến Java mà giữ annotation tường minh, URL công khai không đổi. Đây là cách giữ ổn định hợp đồng khi refactor code.

## 10. Khai báo tên tường minh cho query parameter

Ví dụ API phân trang:

~~~java
@GetMapping("/orders")
List<OrderResponse> findOrders(
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int pageSize) {
    // ...
}
~~~

OpenAPI cần mô tả query parameter page và size. Tên biến pageSize không được dùng làm tên HTTP parameter vì annotation đã chỉ định size.

Nếu bỏ thuộc tính name:

~~~java
@RequestParam int page
~~~

Spring cần khám phá tên method parameter để suy luận page. Với bytecode thiếu metadata, việc bind request có thể thất bại hoặc tài liệu không có tên như mong muốn.

## 11. Khai báo tên tường minh cho header và cookie

Header:

~~~java
@GetMapping("/orders")
List<OrderResponse> findOrders(
        @RequestHeader(name = "X-Tenant") String tenantId) {
    // ...
}
~~~

Cookie:

~~~java
@GetMapping("/profile")
ProfileResponse getProfile(
        @CookieValue(name = "sessionId") String session) {
    // ...
}
~~~

Tên biến tenantId và session là chi tiết nội bộ của Java. Tên giao tiếp HTTP vẫn là X-Tenant và sessionId.

Với header chuẩn hoặc header riêng, giữ đúng cách viết tên đã thống nhất trong API contract. Tên header không phân biệt chữ hoa/chữ thường theo HTTP, nhưng document nên dùng một cách viết ổn định.

## 12. Phân biệt @Parameter với annotation Spring

Springdoc có thể dùng annotation OpenAPI như Parameter để bổ sung mô tả tài liệu:

~~~java
@GetMapping("/orders")
List<OrderResponse> findOrders(
        @Parameter(description = "Lọc theo trạng thái đơn hàng")
        @RequestParam(name = "status") String state) {
    // ...
}
~~~

RequestParam điều khiển cách Spring bind query parameter ở runtime. Parameter bổ sung metadata OpenAPI như description, example, schema hoặc cách hiển thị.

Không dùng Parameter để thay thế RequestParam, PathVariable hoặc RequestHeader. Nếu chỉ viết Parameter(name = "status") nhưng mapping Spring không khai báo tên query parameter tương ứng, tài liệu có thể đúng trong khi runtime vẫn bind sai.

Khi dùng cả hai annotation, giữ tên thống nhất. Ví dụ RequestParam(name = "status") và Parameter(name = "state") tạo ra nguy cơ tài liệu mô tả một tên còn server chờ tên khác. Nếu cần override tên trong OpenAPI, hãy xác nhận rằng thay đổi đó phản ánh đúng giao thức HTTP thật.

## 13. Kiểm tra bytecode bằng javap

Sau khi clean build, dùng javap để xem class controller:

~~~bash
javap -v -p target/classes/com/example/api/OrderController.class
~~~

Thay đường dẫn class bằng package và tên controller thực tế. Tìm phần MethodParameters của method cần kiểm tra.

Khi biên dịch với -parameters, output thường có phần tương tự:

~~~text
MethodParameters:
  Name
  status
  page
~~~

Nếu phần MethodParameters không có hoặc tên không hiện diện, kiểm tra:

- Maven/Gradle có thực sự truyền -parameters cho javac không.
- File class đang xem có phải output của lần build mới nhất không.
- Controller có được biên dịch trong module khác không.
- Runtime có đang nạp một JAR cũ từ dependency cache hoặc repository nội bộ không.

Không kết luận chỉ từ LocalVariableTable. Metadata local variable và MethodParameters là hai thuộc tính bytecode khác nhau. Spring Framework hiện đại cần tên tham số được giữ theo cơ chế reflection tiêu chuẩn.

## 14. Kiểm tra bằng Java Reflection

Có thể viết một đoạn test nhỏ để xác nhận tên parameter trong class đã biên dịch:

~~~java
import java.lang.reflect.Method;

class ParameterMetadataCheck {

    static void inspect() throws NoSuchMethodException {
        Method method = OrderController.class.getDeclaredMethod(
                "findOrders", String.class, Integer.class);

        for (java.lang.reflect.Parameter parameter : method.getParameters()) {
            System.out.println(
                    parameter.getName() + " / " + parameter.isNamePresent());
        }
    }
}
~~~

Nếu metadata được lưu, isNamePresent() trả true và getName() trả tên source như status hoặc page. Nếu không, getName() có thể trả arg0, arg1 và isNamePresent() trả false.

Điều chỉnh danh sách kiểu tham số trong getDeclaredMethod cho đúng chữ ký method của dự án. Nếu method overload, chọn đúng overload bằng kiểu tham số.

Có thể đặt assertion trong JUnit để ngăn lỗi quay lại:

~~~java
@Test
void controllerParameterNamesArePresent() throws Exception {
    Method method = OrderController.class.getDeclaredMethod(
            "findOrders", String.class, Integer.class);

    assertThat(method.getParameters())
            .allMatch(java.lang.reflect.Parameter::isNamePresent);
}
~~~

Test này kiểm tra metadata của class trong test runtime. Nó không thay thế việc kiểm tra OpenAPI document hoặc request binding thực tế.

## 15. Kiểm tra tên parameter trong OpenAPI JSON

Sau khi ứng dụng khởi động, tải OpenAPI document:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Kiểm tra parameter của operation:

~~~bash
jq '.paths["/orders"].get.parameters' openapi.json
~~~

Nếu path thực tế có prefix hoặc tên khác, thay key /orders bằng path trong document. Kết quả cần phản ánh đúng tên public, vị trí parameter và schema.

Ví dụ cấu trúc mong đợi:

~~~json
[
  {
    "name": "status",
    "in": "query",
    "required": false,
    "schema": {
      "type": "string"
    }
  },
  {
    "name": "page",
    "in": "query",
    "required": false,
    "schema": {
      "type": "integer",
      "format": "int32"
    }
  }
]
~~~

Nếu document không có parameter, kiểm tra method mapping, annotation Spring, filter operation, package scan và cấu hình springdoc. Nếu parameter xuất hiện nhưng tên sai, kiểm tra MethodParameters và thuộc tính name/value của annotation.

## 16. Kiểm tra cả request runtime

OpenAPI document chỉ là mô tả. Cần gửi request thật để xác nhận Spring bind đúng tên:

~~~bash
curl -i "http://localhost:8080/orders?status=PAID&page=2"
~~~

Với path parameter:

~~~bash
curl -i "http://localhost:8080/orders/7f7d3c4a-1e5a-4d6e-9b4f-1e4d1f6a2b30"
~~~

Với header:

~~~bash
curl -i -H "X-Tenant: tenant-a" http://localhost:8080/orders
~~~

Nếu OpenAPI ghi status nhưng runtime chỉ nhận state, hoặc document ghi X-Tenant nhưng controller bind tenantId theo tên suy luận khác, hợp đồng và implementation không đồng bộ. Dùng annotation Spring tường minh để chốt tên wire-format.

## 17. Phân biệt lỗi suy luận tên với lỗi filter hoặc customizer

Không phải mọi parameter bị thiếu đều do thiếu -parameters.

| Dấu hiệu | Hướng kiểm tra |
|---|---|
| Nhiều method parameter thành arg0/arg1 | Compiler metadata và -parameters |
| Chỉ một parameter không có tên | Annotation Spring, method signature hoặc custom resolver |
| Parameter biến mất hoàn toàn | Mapping, hidden/filter, operation customizer hoặc package scan |
| DTO property bị sai tên | Jackson, record component, getter/setter hoặc JsonProperty |
| Tên trong tài liệu đúng nhưng request bind sai | Annotation OpenAPI và annotation Spring không đồng nhất |
| Local đúng nhưng CI sai | Cấu hình compiler plugin, module build hoặc artifact cache khác nhau |

Nếu parameter bị loại bởi OperationCustomizer hoặc OpenApiCustomizer, bật -parameters không khôi phục nó. Kiểm tra các customizer và filter đang thay đổi operation.

## 18. Kiểm tra khi dùng Spring Framework 6.1 trở lên

Với Spring Framework 6.1, cơ chế dự phòng đọc tên parameter từ LocalVariableTable đã bị loại bỏ. Do đó, dự án cần giữ tên tham số trong bytecode bằng tùy chọn compiler -parameters nếu đang dựa vào suy luận tên.

Khi nâng Spring Boot, xem phiên bản Spring Framework được quản lý bởi Spring Boot BOM. Đừng chỉ kiểm tra phiên bản springdoc; việc đổi Spring Boot có thể thay đổi cách Spring khám phá tên parameter ngay cả khi source controller không đổi.

Nếu project cần chạy trên nhiều nhánh Spring Boot, bật -parameters ở build để giữ hành vi nhất quán. Đồng thời dùng tên tường minh trong annotation cho những parameter thuộc public contract quan trọng.

## 19. Làm mới build output và dependency cache

Sau khi bật compiler flag, clean build module chứa controller:

~~~bash
mvn clean verify
~~~

Hoặc:

~~~bash
./gradlew clean test
~~~

Nếu ứng dụng dùng JAR nội bộ, build và publish lại module đó, sau đó cập nhật version dependency trong ứng dụng. Khi cần xác minh, mở chính JAR đang được runtime sử dụng và kiểm tra class bên trong.

Không xóa toàn bộ Maven hoặc Gradle cache ngay từ đầu. Trước tiên xác nhận dependency resolution và output path. Chỉ làm mới cache có mục tiêu nếu bằng chứng cho thấy build đang dùng artifact cũ.

## 20. Giữ compiler flag nhất quán trong CI

Lỗi thường xuất hiện khi máy developer có cấu hình compiler riêng nhưng pipeline CI không dùng cùng cấu hình. Hãy lưu cờ -parameters trong pom.xml, build.gradle hoặc convention plugin được commit vào repository.

Kiểm tra:

- Build local và CI gọi cùng Maven/Gradle wrapper.
- Module chứa controller nhận compiler flag.
- CI thực hiện clean build khi thay đổi compiler options.
- Artifact được publish từ build mới, không dùng lại JAR cũ.
- Test kiểm tra isNamePresent hoặc OpenAPI parameter name được chạy trong pipeline.

Không chỉ thêm compiler flag vào một lệnh chạy cục bộ rồi bỏ quên cấu hình build chính thức.

## 21. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| OpenAPI hiển thị arg0 thay vì tên mong muốn | Bytecode không có MethodParameters | Bật -parameters và clean build module controller |
| Spring báo không thể suy luận tên argument | Annotation không có name/value và reflection không có tên | Bật -parameters hoặc khai báo tên tường minh |
| Local đúng nhưng CI sai | Compiler configuration hoặc artifact khác nhau | Kiểm tra effective POM, Gradle task và JAR được publish |
| Chỉ controller trong một module bị lỗi | Module đó không nhận compiler flag | Cấu hình JavaCompile/Maven compiler cho đúng module |
| Tên parameter trong OpenAPI khác query string | Parameter annotation và RequestParam không đồng nhất | Đồng bộ tên wire-format trong annotation Spring và OpenAPI |
| @Parameter có tên đúng nhưng request không bind | Chỉ metadata OpenAPI được khai báo | Đặt tên trong RequestParam/PathVariable/RequestHeader |
| Field DTO sai tên | Không phải lỗi MethodParameters | Kiểm tra Jackson, JsonProperty, record component và Schema |
| Bật -parameters nhưng tài liệu vẫn cũ | Chưa clean build hoặc app đang nạp JAR cũ | Xác định class runtime và build/publish lại artifact |
| Parameter không xuất hiện | Operation filter, hidden annotation hoặc customizer loại bỏ | Kiểm tra mapping, group filter và customizer |
| MethodParameters có tên nhưng Spring vẫn lỗi | Annotation hoặc method overload không khớp | Kiểm tra chữ ký method và tên khai báo trong annotation |

## 22. Quy trình chẩn đoán theo thứ tự

1. Tải OpenAPI JSON và xác định operation bị lỗi.
2. Xem tên, vị trí và schema của parameter trong paths.
3. Đối chiếu path/method với mapping của controller.
4. Kiểm tra annotation Spring có name/value tường minh hay đang dựa vào suy luận.
5. Dùng javap kiểm tra MethodParameters trong class controller.
6. Nếu thiếu metadata, bật -parameters trong compiler của module chứa controller.
7. Clean build và xác minh lại bytecode.
8. Khởi động đúng artifact mới và tải lại OpenAPI JSON.
9. Gửi request runtime với tên parameter được công bố.
10. Nếu tài liệu vẫn sai, kiểm tra OpenApiCustomizer, OperationCustomizer, group filter và package scan.

Không đổi đồng thời annotation, compiler configuration và customizer trong cùng một lần thử nếu chưa biết nguyên nhân. Thay từng yếu tố giúp xác định chính xác điều gì sửa được lỗi.

## 23. Kiểm tra bằng integration test

Có thể kiểm tra OpenAPI document trong test bằng WebTestClient hoặc MockMvc tùy web stack. Ví dụ đọc JSON document và xác nhận tên query parameter:

~~~java
@Test
void orderSearchDocumentsStableQueryNames() {
    webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody(JsonNode.class)
            .value(document -> {
                JsonNode parameters = document.at(
                        "/paths/~1orders/get/parameters");

                assertThat(parameters.toString()).contains("\"status\"");
                assertThat(parameters.toString()).contains("\"page\"");
            });
}
~~~

Đây là assertion minh họa cho tên parameter. Trong test của dự án, nên duyệt từng phần tử và kiểm tra cả name, in, required và schema để tránh test pass chỉ vì một chuỗi xuất hiện ở vị trí khác trong JSON.

Có thể kết hợp test runtime:

~~~java
@Test
void orderSearchAcceptsDocumentedQueryNames() {
    webTestClient.get()
            .uri(uriBuilder -> uriBuilder
                    .path("/orders")
                    .queryParam("status", "PAID")
                    .queryParam("page", 2)
                    .build())
            .exchange()
            .expectStatus().isOk();
}
~~~

Điều chỉnh response assertion theo API thật. Mục tiêu là khóa đồng thời tên được công bố và tên được Spring bind.

## 24. Checklist trước khi đóng lỗi

- [ ] Đã xác định parameter là method parameter hay property trong DTO.
- [ ] Đã kiểm tra annotation Spring đang suy luận tên hay có name/value rõ ràng.
- [ ] Module chứa controller được biên dịch với -parameters.
- [ ] Bytecode có MethodParameters và isNamePresent() trả true.
- [ ] Đã clean build sau khi thay compiler option.
- [ ] Runtime đang dùng đúng JAR/class mới.
- [ ] OpenAPI JSON hiển thị đúng name và in.
- [ ] Request runtime dùng đúng tên query/path/header/cookie.
- [ ] @Parameter không bị dùng thay cho annotation binding của Spring.
- [ ] Customizer/filter/group không loại hoặc đổi parameter ngoài ý muốn.
- [ ] CI áp dụng cùng compiler configuration với local.
- [ ] Có test bảo vệ tên parameter của public contract.

## 25. Nguyên tắc thiết kế

- Bật -parameters trong compiler cho các module Java có controller dựa vào tên method parameter.
- Ưu tiên khai báo name/value tường minh cho path, query, header và cookie parameter thuộc public API.
- Phân biệt metadata OpenAPI từ @Parameter với runtime binding từ RequestParam, PathVariable, RequestHeader và CookieValue.
- Không nhầm tên method parameter với tên property trong DTO.
- Dùng javap và Java Reflection để xác nhận bytecode thay vì đoán từ source.
- Clean build và kiểm tra đúng artifact runtime sau khi thay compiler option.
- Xác minh cả OpenAPI JSON lẫn request thực tế.
- Kiểm tra customizer và group filter nếu metadata đã có nhưng document vẫn thiếu.
- Đưa compiler flag và test regression vào build chính thức để local/CI nhất quán.

## Kết luận

Tham số bị mất tên thường xuất phát từ việc bytecode không lưu metadata MethodParameters hoặc từ annotation Spring để framework tự suy luận tên. Bật tùy chọn compiler -parameters trong Maven hoặc Gradle để giữ tên method parameter; với API công khai, nên khai báo rõ name/value trong PathVariable, RequestParam, RequestHeader và CookieValue. Phân biệt lỗi này với tên property DTO, vốn chịu ảnh hưởng của Jackson và schema metadata. Chẩn đoán theo thứ tự từ OpenAPI JSON, annotation Spring, bytecode javap, Java Reflection đến request runtime. Sau cùng, giữ cấu hình compiler trong repository và thêm test để tên parameter không biến mất khi build trên CI.

## Tài liệu tham khảo

- [Java Compiler: javac options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Java Reflection: Parameter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html)
- [Spring Framework 6.1 Reference](https://docs.spring.io/spring-framework/reference/overview.html)
- [springdoc-openapi documentation](https://springdoc.org/)
