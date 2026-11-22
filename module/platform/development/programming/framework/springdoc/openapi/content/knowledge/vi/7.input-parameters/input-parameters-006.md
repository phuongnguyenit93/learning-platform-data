# Vai trò của tùy chọn biên dịch -parameters

Khi viết controller Spring Boot, ta thường khai báo tham số như **@RequestParam String keyword** hoặc **@PathVariable UUID bookId** mà không ghi tên trong annotation. Spring có thể lấy tên từ tham số Java nếu tên đó được lưu trong file **.class**. Tùy chọn biên dịch **-parameters** yêu cầu trình biên dịch Java lưu metadata tên tham số để reflection và các framework như Spring có thể đọc được.

Với **springdoc-openapi**, metadata này cũng hữu ích khi thư viện phân tích chữ ký controller để tạo parameter trong đặc tả OpenAPI. Nếu tên tham số không có trong bytecode và annotation Spring MVC cũng không khai báo tên tường minh, ứng dụng có thể không bind được request như mong muốn hoặc tài liệu có thể hiển thị tên không hữu ích.

Bài này giải thích **-parameters** hoạt động ở đâu, vì sao nó quan trọng với Spring MVC và springdoc-openapi, cách bật trong Maven và Gradle, và cách xác minh file **.class** sau khi biên dịch.

## 1. Tên tham số trong mã nguồn và trong bytecode

Xét method Java:

~~~java
public class BookController {

    public void search(String keyword, int page) {
        // ...
    }
}
~~~

Trong mã nguồn, tên **keyword** và **page** luôn hiện diện. Nhưng sau khi biên dịch, file **.class** không mặc nhiên phải lưu các tên này theo cách Java Reflection có thể đọc. Nếu không có metadata tên tham số, reflection có thể chỉ trả về tên tổng quát như **arg0**, **arg1**.

Khi biên dịch với **-parameters**, **javac** ghi thông tin tên tham số vào thuộc tính **MethodParameters** của class file. Java Reflection có thể đọc thông tin đó qua **java.lang.reflect.Parameter**.

~~~java
Method method = BookController.class.getMethod(
    "search",
    String.class,
    int.class
);

for (Parameter parameter : method.getParameters()) {
    System.out.printf(
        "name=%s, present=%s%n",
        parameter.getName(),
        parameter.isNamePresent()
    );
}
~~~

Kết quả điển hình:

| Cách biên dịch | getName() | isNamePresent() |
|---|---|---|
| Không bật -parameters | arg0, arg1 | false |
| Có bật -parameters | keyword, page | true |

**Parameter.isNamePresent()** là cách kiểm tra trực tiếp xem tên tham số có sẵn trong metadata reflection hay không. Đây là dấu hiệu đáng tin cậy hơn việc chỉ nhìn thấy tên biến trong source code hoặc debug log.

### -parameters khác thông tin debug

Java có các tùy chọn biên dịch phục vụ mục đích khác nhau:

- **-parameters** lưu tên tham số method và constructor để reflection đọc được.
- **-g** tạo thông tin debug, chẳng hạn số dòng và thông tin biến cục bộ.
- **-g:vars** yêu cầu thông tin debug về biến cục bộ.

Thông tin biến cục bộ trong **LocalVariableTable** không đồng nghĩa với thuộc tính **MethodParameters**. Một framework dùng reflection chuẩn không thể mặc định lấy tên tham số từ thông tin debug.

Đặc biệt với Spring Framework 6.1 trở lên, không nên dựa vào việc đọc tên tham số từ **LocalVariableTable**: cách khám phá tên dựa trên bảng biến cục bộ đã bị loại bỏ sau thời gian deprecated. Hãy bật **-parameters** để tên tham số Java có sẵn cho reflection.

## 2. Vì sao Spring MVC cần tên tham số?

Spring MVC phải ánh xạ dữ liệu HTTP vào tham số của method controller. Khi annotation không chỉ rõ tên, Spring có thể cần lấy tên tham số Java để biết giá trị nào cần đọc.

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping("/search")
    public List<BookResponse> search(
        @RequestParam String keyword,
        @RequestParam(defaultValue = "0") int page
    ) {
        // Tìm sách theo keyword và page
        return List.of();
    }

    @GetMapping("/{bookId}")
    public BookResponse findById(
        @PathVariable UUID bookId
    ) {
        // Tìm sách theo bookId
        return null;
    }
}
~~~

Spring cần biết:

- **keyword** lấy từ query parameter có tên **keyword**.
- **page** lấy từ query parameter có tên **page**.
- **bookId** lấy từ path variable có tên **bookId**.

Nếu các annotation không khai báo **name** hoặc **value**, Spring có thể suy ra tên từ metadata tham số. Khi tên không có sẵn, việc bind có thể thất bại với thông báo cho biết tên tham số không được chỉ định và không có thông tin tên qua reflection.

Đối với các annotation nhận dữ liệu theo tên, có thể khai báo tên tường minh:

~~~java
@GetMapping("/search")
public List<BookResponse> search(
    @RequestParam(name = "keyword") String searchText,
    @RequestParam(name = "page", defaultValue = "0") int page
) {
    // ...
    return List.of();
}
~~~

Trong trường hợp này, Spring bind **searchText** từ query key **keyword**. Tên biến Java có thể khác tên parameter HTTP vì annotation đã cung cấp tên rõ ràng.

Các annotation thường gặp có thuộc tính tên:

| Annotation | Thuộc tính khai báo tên | Vị trí dữ liệu |
|---|---|---|
| @RequestParam | name hoặc value | Query string hoặc form parameter |
| @PathVariable | name hoặc value | Path segment |
| @RequestHeader | name hoặc value | HTTP header |
| @CookieValue | name hoặc value | Cookie |

**-parameters** giúp Spring suy ra tên khi annotation bỏ trống. Tên khai báo tường minh trong annotation giúp hợp đồng binding rõ ràng và ít phụ thuộc vào metadata của bytecode.

## 3. Tác động tới springdoc-openapi

springdoc-openapi đọc metadata Spring MVC, chữ ký handler method và annotation OpenAPI để tạo operation cùng danh sách parameter. Với một tham số được khai báo như **@RequestParam String keyword**, tên **keyword** là thông tin quan trọng để tạo parameter có **name: keyword** trong OpenAPI.

Ví dụ đặc tả mong muốn:

~~~yaml
paths:
  /api/books/search:
    get:
      parameters:
        - name: keyword
          in: query
          required: true
          schema:
            type: string
        - name: page
          in: query
          required: false
          schema:
            type: integer
            format: int32
            default: 0
      responses:
        "200":
          description: Danh sách sách
~~~

Khi metadata tên tham số có sẵn, springdoc có thể tạo tên parameter có ý nghĩa. Khi metadata bị thiếu và annotation không cung cấp tên, kết quả suy luận có thể không đúng kỳ vọng hoặc quá trình phân tích có thể gặp lỗi tùy phiên bản, loại tham số và cấu hình.

Điều quan trọng là phân biệt ba vai trò:

- **-parameters** lưu tên tham số trong bytecode để reflection và framework đọc được.
- **@Parameter** của swagger-annotations bổ sung mô tả cho tài liệu OpenAPI.
- **@RequestParam(name = "...")**, **@PathVariable(name = "...")** và các annotation Spring tương ứng quyết định tên Spring MVC dùng để bind request.

Chỉ đặt **@Parameter(name = "keyword")** không tự làm cho Spring MVC bind query key **keyword**. Nếu controller cần bind theo tên đó, hãy khai báo tên trong annotation Spring MVC hoặc đảm bảo tên tham số được lưu bằng **-parameters**.

Ví dụ kết hợp:

~~~java
@Operation(summary = "Tìm kiếm sách")
@GetMapping("/search")
public List<BookResponse> search(
    @Parameter(description = "Từ khóa tìm kiếm", example = "Spring")
    @RequestParam(name = "keyword")
    String searchText
) {
    // ...
    return List.of();
}
~~~

Ở đây, Spring MVC dùng tên **keyword** để bind; **@Parameter** cung cấp description và example cho tài liệu. Biến Java **searchText** không cần trùng tên query parameter.

## 4. Bật -parameters trong Maven

Với Maven, tùy chọn được cấu hình trong **maven-compiler-plugin**. Có thể thêm cấu hình sau vào phần **build/plugins** của **pom.xml**:

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

Nếu dự án dùng **spring-boot-starter-parent**, có thể kế thừa phiên bản plugin từ parent và bổ sung cấu hình vào plugin đang được quản lý. Tránh khai báo một phiên bản plugin cũ chỉ để bật một tùy chọn nếu dự án đã có quản lý phiên bản tập trung.

Một cách khác là đặt property mà Maven Compiler Plugin hỗ trợ:

~~~xml
<properties>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
~~~

Hãy xác nhận phiên bản **maven-compiler-plugin** của dự án hỗ trợ property này. Cấu hình trực tiếp **<parameters>true</parameters>** trong plugin là cách thể hiện rõ mục đích và dễ đọc khi kiểm tra **pom.xml**.

Sau khi cập nhật, chạy build để biên dịch lại:

~~~bash
mvn clean compile
~~~

**clean** quan trọng khi cần xác minh tùy chọn mới: nó loại bỏ class file cũ có thể chưa chứa **MethodParameters**, sau đó biên dịch lại source với cấu hình hiện tại.

## 5. Bật -parameters trong Gradle

Với Gradle Groovy DSL (**build.gradle**), cấu hình cho mọi task JavaCompile:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Với Gradle Kotlin DSL (**build.gradle.kts**):

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Nếu file build chưa nhận diện **JavaCompile**, có thể thêm import:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
~~~

Sau đó biên dịch lại:

~~~bash
./gradlew clean compileJava
~~~

Trên Windows có thể dùng **gradlew.bat clean compileJava**. Trong dự án multi-module, hãy xác nhận cấu hình áp dụng cho module chứa controller và cho các module chứa class mà framework cần đọc tên tham số. Cấu hình ở một module không tự động thay đổi các file **.class** đã được biên dịch trong module khác.

### Kiểm tra cấu hình có áp dụng cho đúng task

Không chỉ kiểm tra file build có chứa chuỗi **-parameters**. Cần xác minh task biên dịch Java thực sự nhận tùy chọn này. Với Gradle, có thể xem log task hoặc cấu hình task; với Maven, kiểm tra effective POM và log compiler nếu cần. Sau đó kiểm tra bytecode đầu ra để xác nhận.

Một số plugin hoặc convention plugin có thể cấu hình lại compiler arguments. Nếu dự án có nhiều module hoặc nhiều source set, hãy kiểm tra đúng task tạo class file của controller đang gặp vấn đề.

## 6. Xác minh bằng Java Reflection

Có thể tạo một method đơn giản để kiểm tra:

~~~java
public class ParameterNameProbe {
    public void search(String keyword, int page) {
    }
}
~~~

Chạy đoạn kiểm tra:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class InspectParameterNames {
    public static void main(String[] args) throws Exception {
        Method method = ParameterNameProbe.class.getMethod(
            "search",
            String.class,
            int.class
        );

        for (Parameter parameter : method.getParameters()) {
            System.out.printf(
                "%s: %s (present=%s)%n",
                parameter.getType().getSimpleName(),
                parameter.getName(),
                parameter.isNamePresent()
            );
        }
    }
}
~~~

Khi biên dịch class probe bằng **-parameters**, kết quả cần cho thấy:

~~~text
String: keyword (present=true)
int: page (present=true)
~~~

Nếu kết quả là **arg0 (present=false)** và **arg1 (present=false)**, class đang kiểm tra không có metadata tên tham số theo reflection. Hãy kiểm tra compiler option, task đã chạy và đường dẫn class file được nạp.

### Kiểm tra trực tiếp bằng javap

JDK cung cấp **javap** để xem bytecode. Chạy:

~~~bash
javap -v -p target/classes/com/example/ParameterNameProbe.class
~~~

Với Gradle, class thường nằm dưới **build/classes/java/main/...**. Trong kết quả, tìm phần **MethodParameters** và các tên **keyword**, **page**.

Ví dụ phần đầu ra mong đợi có dạng:

~~~text
MethodParameters:
  Name                           Flags
  keyword
  page
~~~

Tên và định dạng hiển thị chính xác có thể khác theo JDK, nhưng cần thấy thuộc tính MethodParameters chứa tên tham số. Nếu chỉ thấy **LocalVariableTable**, điều đó chưa chứng minh **-parameters** đã được áp dụng.

## 7. Kiểm tra trong ứng dụng Spring Boot và tài liệu OpenAPI

Sau khi bật tùy chọn và biên dịch lại, kiểm tra cả binding runtime lẫn tài liệu được sinh ra.

Controller mẫu:

~~~java
@RestController
@RequestMapping("/api/books")
@Tag(name = "Books")
public class BookController {

    @Operation(summary = "Tìm kiếm sách")
    @GetMapping("/search")
    public List<BookResponse> search(
        @RequestParam String keyword,
        @RequestParam(defaultValue = "0") int page,
        @RequestHeader(required = false) String requestId
    ) {
        // ...
        return List.of();
    }
}
~~~

Gọi thử endpoint:

~~~http
GET /api/books/search?keyword=spring&page=1
X-Request-Id: req-123
~~~

Xác minh:

1. Request được Spring bind đúng **keyword**, **page** và **requestId**.
2. Endpoint **/v3/api-docs** có operation **GET /api/books/search**.
3. Parameter được mô tả với tên **keyword**, **page** và **requestId**.
4. Vị trí lần lượt là query, query và header.
5. **page** có default phù hợp và **requestId** được mô tả là tùy chọn.

Nếu ứng dụng bind thành công nhưng tài liệu sai tên, kiểm tra annotation OpenAPI và cách springdoc đọc metadata. Nếu tài liệu hiển thị đúng nhưng request thật thất bại, kiểm tra tên được khai báo trong annotation Spring MVC, compiler option và class file thực tế đang chạy.

## 8. Tình huống dễ nhầm và cách xử lý

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tên biến đúng trong source nhưng Spring báo không tìm thấy tên parameter | Tên không được lưu trong class file | Bật **-parameters** và clean compile |
| Reflection trả **arg0** | Class được biên dịch không có MethodParameters | Kiểm tra task compiler và đúng classpath |
| Chỉ bật **-g** nhưng vẫn không có tên reflection | Debug metadata khác MethodParameters | Bật **-parameters** |
| Dùng **@Parameter(name = "...")** nhưng Spring vẫn bind sai | Annotation OpenAPI không quyết định binding | Khai báo **name** trong annotation Spring MVC |
| Máy local chạy được nhưng môi trường triển khai lỗi | Artifact trên server được build từ cấu hình hoặc module khác | Kiểm tra class file trong artifact đã triển khai |
| Đã thêm tùy chọn nhưng kết quả chưa đổi | Build incremental còn dùng class file cũ hoặc cấu hình không áp dụng | Clean và biên dịch lại đúng module |
| Controller Java có tên, nhưng dependency bên ngoài không có | Thư viện được biên dịch riêng mà không lưu metadata | Cấu hình compiler cho module tạo dependency hoặc khai báo tên tường minh tại API cần thiết |

Với endpoint công khai, nên cân nhắc khai báo tên rõ ràng trong annotation Spring MVC cho các parameter quan trọng. Cách này giúp hợp đồng HTTP ổn định ngay cả khi tên biến Java được đổi để refactor nội bộ.

## 9. Khi nào nên dùng tên tường minh và khi nào cần -parameters?

Hai cách bổ trợ cho nhau:

| Lựa chọn | Phù hợp khi | Ưu điểm |
|---|---|---|
| Bật **-parameters** | Dự án Spring dùng tên tham số để bind hoặc phân tích metadata ở nhiều nơi | Cấu hình một lần cho các class được biên dịch trong module |
| Khai báo **name** trong annotation Spring MVC | Tên HTTP là một phần hợp đồng cần ổn định hoặc muốn tên Java khác tên HTTP | Rõ ràng ngay tại điểm bind, không phụ thuộc tên biến |
| Kết hợp cả hai | Dự án dùng reflection rộng rãi và API cần tên HTTP ổn định | Có metadata reflection đồng thời giữ tên binding tường minh |

Đối với API được tài liệu hóa bằng springdoc-openapi, một quy ước thực tế là bật **-parameters** cho toàn bộ module Java và khai báo tên tường minh cho những parameter có ý nghĩa công khai hoặc có tên khác với biến Java. Dùng **@Parameter** để bổ sung mô tả, ví dụ và schema; không dùng nó thay cho annotation bind của Spring MVC.

## 10. Checklist trước khi kết luận đã cấu hình đúng

- [ ] Maven hoặc Gradle đã bật **-parameters** cho task biên dịch Java phù hợp.
- [ ] Đã clean và biên dịch lại class file sau khi thay đổi cấu hình.
- [ ] Reflection trả về tên tham số mong muốn và **isNamePresent()** là **true**.
- [ ] **javap -v** cho thấy **MethodParameters** chứa các tên mong đợi.
- [ ] Controller bind đúng query, path, header hoặc cookie khi gửi request thật.
- [ ] OpenAPI JSON tại **/v3/api-docs** có tên và vị trí parameter chính xác.
- [ ] Các tên được khai báo trong annotation Spring MVC khớp với hợp đồng HTTP.
- [ ] Artifact triển khai được tạo từ đúng cấu hình compiler đã xác minh.

## Kết luận

**-parameters** là tùy chọn của trình biên dịch Java giúp lưu tên tham số trong thuộc tính **MethodParameters** của file **.class**. Spring MVC có thể dùng metadata này khi annotation bind không khai báo tên tường minh; springdoc-openapi cũng có thể dựa vào tên tham số khi tạo parameter trong đặc tả. Bật tùy chọn trong Maven hoặc Gradle, biên dịch lại và xác minh bằng Reflection hoặc **javap** để bảo đảm tên có mặt trong bytecode. Với tên HTTP cần ổn định, hãy khai báo rõ **name** trong annotation Spring MVC và dùng annotation OpenAPI riêng cho phần mô tả tài liệu.
