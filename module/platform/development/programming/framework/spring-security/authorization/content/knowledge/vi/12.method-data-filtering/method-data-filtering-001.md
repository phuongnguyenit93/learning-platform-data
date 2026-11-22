# `@PreFilter` — lọc phần tử đầu vào trước khi xử lý

## 1. Mục tiêu và bài toán

Giả sử một API nhận nhiều tài liệu để cập nhật. Người dùng `alice` gửi ba tài liệu: `#1` thuộc `alice`, `#2` thuộc `bob`, `#3` thuộc `alice`. Tầng service chỉ nên **nhận các phần tử mà người gọi được phép xử lý**. Nếu nghiệp vụ cho phép xử lý một phần lô, Spring Security cung cấp `@PreFilter` để loại phần tử không đạt điều kiện **trước khi thân phương thức chạy**.

Sau bài này, bạn có thể:

- Giải thích cách Spring AOP/Method Security chặn lời gọi và lọc tham số.
- Viết biểu thức SpEL dựa trên `filterObject`, `authentication` và quy tắc phân quyền.
- Chọn đúng tham số bằng `filterTarget`; hiểu cách lọc `Collection`, `Map`, mảng và `Stream`.
- Tránh lỗi collection bất biến, bỏ qua proxy, dùng dữ liệu người dùng tự khai làm bằng chứng sở hữu.
- Kiểm thử kết quả thực tế khi lời gọi đi qua Spring bean.

**Phạm vi:** `@PreFilter` của Spring Security cho lời gọi phương thức; đây không phải Servlet Filter trong chuỗi HTTP và cũng không tự động lọc dữ liệu ngay trong truy vấn SQL.

## 2. `@PreFilter` làm gì?

Ví dụ ý tưởng:

```java
@PreFilter("filterObject.owner() == authentication.name")
public List<Document> process(List<Document> documents) {
    // documents chỉ còn các Document vượt qua biểu thức lọc
    return List.copyOf(documents);
}
```

Với danh sách `[Doc(1, alice), Doc(2, bob), Doc(3, alice)]` và người dùng đang đăng nhập là `alice`, phương thức nhận danh sách tương ứng `[Doc(1, alice), Doc(3, alice)]`.

- `@PreFilter` nằm trên phương thức được Spring quản lý. Nó yêu cầu một **biểu thức SpEL trả về boolean** cho mỗi phần tử.
- `filterObject` đại diện **phần tử hiện tại** đang được xét.
- `authentication` là đối tượng `Authentication` trong ngữ cảnh bảo mật của lời gọi; `authentication.name` là tên người dùng đăng nhập.
- Kết quả `true`: giữ phần tử. Kết quả `false`: loại phần tử khỏi đầu vào chuyển đến phương thức.
- Phương thức **vẫn được gọi** với tập phần tử còn lại, kể cả khi danh sách rỗng. Việc loại một phần tử **không đồng nghĩa** ném `AccessDeniedException` cho cả lời gọi.

Sự khác nhau cần nhớ:

| Công cụ | Thời điểm | Hành vi chính |
| --- | --- | --- |
| `@PreFilter` | Trước khi chạy thân phương thức | Lọc các phần tử của **tham số đầu vào** |
| `@PreAuthorize` | Trước khi chạy thân phương thức | Cho phép hoặc từ chối **toàn bộ lời gọi** |
| `@PostFilter` | Sau khi thân phương thức trả về | Lọc các phần tử trong **giá trị trả về** |
| `@PostAuthorize` | Sau khi thân phương thức chạy | Kiểm tra quyền đối với **kết quả/lời gọi** |

Chẳng hạn, nếu **mọi** tài liệu trong lô bắt buộc đều được phép cập nhật, hãy thiết kế cơ chế từ chối cả lô bằng kiểm tra quyền phù hợp. Nếu API chấp nhận xử lý một phần, `@PreFilter` phù hợp hơn, nhưng cần công bố rõ hành vi bỏ qua phần tử.

## 3. Luồng thực thi

```text
Controller / service khác
         |
         v
Spring AOP proxy của service
         |
         v
Interceptor @PreFilter
   - xác định tham số cần lọc
   - lấy Authentication
   - duyệt phần tử, đặt filterObject
   - tính SpEL, giữ phần tử đạt điều kiện
         |
         v
Thân phương thức service
   (đã nhận đầu vào sau lọc)
         |
         v
Kết quả / các interceptor tiếp theo
```

Khi bật `@EnableMethodSecurity`, Spring đăng ký cơ chế method security. Trong mô hình mặc định, `@PreFilter` được xử lý bởi `PreFilterAuthorizationMethodInterceptor` trong chuỗi Spring AOP. Điểm quan trọng là **lời gọi phải đi qua proxy**: gọi `this.process(...)` từ phương thức khác trong cùng bean thường không đi qua interceptor kiểu proxy và vì vậy có thể bỏ qua annotation.

`@PreFilter` không thay thế xác thực: cần có `Authentication` phù hợp trong security context. Ở HTTP request, Spring Security thường thiết lập ngữ cảnh này từ cơ chế đăng nhập/token. Khi gọi từ job, sự kiện hoặc kiểm thử, phải xác định ngữ cảnh bảo mật tương ứng.

## 4. Kích hoạt Method Security

Thêm Spring Security vào ứng dụng Spring Boot và bật method security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

Có thể đặt `@EnableMethodSecurity` ngay trên lớp `@SpringBootApplication` như ví dụ đầy đủ ở mục tiếp theo. Chỉ thêm dependency Spring Security **chưa tự bật** method security. Với cấu hình mặc định, nhóm annotation `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` được hỗ trợ. API cũ `@EnableGlobalMethodSecurity` thuộc cách cấu hình trước đây.

Đặt annotation trên phương thức của Spring bean, ưu tiên method `public` và gọi thông qua bean do Spring tiêm vào. Việc tự `new DocumentService()` không tạo proxy bảo mật.

## 5. Ví dụ chạy được với Java 17+ và Spring Boot 3.x

Ví dụ dưới đây mô phỏng xử lý lô tài liệu, không cần HTTP server hay cơ sở dữ liệu. Nó tạo `Authentication` thử nghiệm trong `CommandLineRunner`, sau đó gọi **service do Spring quản lý**. Bản minh họa dùng Spring Boot `3.3.13` để cố định dependency; dự án thực tế nên chọn nhánh Spring Boot còn được hỗ trợ.

Tạo dự án Gradle có cấu trúc:

```text
prefilter-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── PrefilterDemoApplication.java
    │   └── DocumentService.java
    └── test/java/demo/
        └── DocumentServiceTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'prefilter-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import java.util.List;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;

record Document(long id, String owner) {}

@Service
public class DocumentService {

    @PreFilter("filterObject.owner() == authentication.name")
    public List<Document> accept(List<Document> documents) {
        // Chỉ làm việc với các phần tử đã qua kiểm tra.
        return List.copyOf(documents);
    }
}
```

`Document` là Java record: `owner()` trả về chủ sở hữu, `id()` trả về mã tài liệu. Trong SpEL, `filterObject.owner()` gọi accessor của record. Không nên giả định một trường `owner` trong DTO do client tự gửi là bằng chứng quyền sở hữu; mục 9 giải thích giới hạn này.

**`src/main/java/demo/PrefilterDemoApplication.java`:**

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class PrefilterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PrefilterDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DocumentService service) {
        return args -> {
            var auth = new UsernamePasswordAuthenticationToken(
                "alice",
                "demo-only",
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            );
            SecurityContextHolder.getContext().setAuthentication(auth);

            try {
                List<Document> submitted = new ArrayList<>(List.of(
                    new Document(1, "alice"),
                    new Document(2, "bob"),
                    new Document(3, "alice")
                ));

                List<Document> accepted = service.accept(submitted);
                System.out.println("Accepted IDs: "
                    + accepted.stream().map(Document::id).toList());
                System.out.println("Remaining input IDs: "
                    + submitted.stream().map(Document::id).toList());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }
}
```

Chạy trong dự án có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell dùng `.\gradlew.bat bootRun`; nếu chưa có Wrapper nhưng đã cài Gradle, có thể dùng `gradle bootRun`. Hai dòng do mã demo in ra (ngoài log Spring Boot) là:

```text
Accepted IDs: [1, 3]
Remaining input IDs: [1, 3]
```

Giải thích: interceptor đánh giá ba phần tử trước khi `accept` chạy. `#2` không có owner bằng `authentication.name`, nên bị loại. `ArrayList` ban đầu trong ví dụ cũng bị thay đổi bởi quá trình lọc; đây là chi tiết cần tính đến khi dữ liệu đầu vào được tái sử dụng.

**Đừng sử dụng `UsernamePasswordAuthenticationToken` tự tạo như trên để xác thực yêu cầu từ client.** Mục đích của nó chỉ là dựng security context trong chương trình mô phỏng; ở ứng dụng thật phải sử dụng luồng xác thực được Spring Security cấu hình và kiểm tra.

## 6. Cú pháp SpEL và chọn tham số lọc

### 6.1. Điều kiện trên từng phần tử

Ví dụ với phương thức có tham số `List<Document>`:

```java
@PreFilter("filterObject.owner() == authentication.name")
public void process(List<Document> documents) {
    // ...
}
```

Có thể kết hợp điều kiện để chỉ giữ phần tử hợp lệ:

```java
@PreFilter(
    "filterObject != null and " +
    "filterObject.owner() == authentication.name"
)
public void process(List<Document> documents) {
    // ...
}
```

Biểu thức cần trả về giá trị boolean. Nếu dereference thuộc tính trên `null`, gọi method sai tên hoặc ném exception khi đánh giá SpEL, lời gọi có thể thất bại; nó không tự động chuyển lỗi lập trình thành một quyết định bảo mật an toàn. Biểu thức phải đơn giản, kiểm thử được và không có tác dụng phụ.

`hasAuthority('documents:write')` và `hasRole('ADMIN')` có thể xuất hiện trong biểu thức bảo mật, nhưng dùng `@PreAuthorize` riêng để **từ chối lời gọi thiếu quyền tổng thể** thường rõ ràng hơn việc lọc sạch mọi phần tử rồi vẫn chạy method.

### 6.2. Có nhiều tham số: dùng `filterTarget`

Nếu method có nhiều tham số, đặc biệt nhiều danh sách, phải xác định rõ danh sách cần lọc bằng `filterTarget`. Bảo đảm Spring tìm được tên tham số qua cấu hình biên dịch `-parameters` hoặc annotation đặt tên như `@P`:

```java
import java.util.List;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreFilter;

@PreFilter(
    value = "filterObject.owner() == authentication.name",
    filterTarget = "documents"
)
public List<Document> acceptBatch(
        String batchId,
        @P("documents") List<Document> documents) {
    return List.copyOf(documents);
}
```

`batchId` không bị lọc, còn `documents` là đích. Khi không xác định được tham số hoặc có nhiều đối tượng có thể lọc và không chỉ rõ đích, cấu hình có thể gặp lỗi lúc gọi. Không nên dựa vào tên tham số bị loại bỏ khi biên dịch.

### 6.3. `Collection`, `Map`, mảng, `Stream`

Tài liệu Spring Security hiện đại mô tả hỗ trợ `Collection`, array, `Map` và `Stream` còn mở. Cần phân biệt hình dạng phần tử được duyệt:

| Kiểu đầu vào | `filterObject` đại diện | Ví dụ biểu thức |
| --- | --- | --- |
| `List<Document>` / `Collection<Document>` | Một `Document` | `filterObject.owner() == authentication.name` |
| `Document[]` | Một `Document` | `filterObject.owner() == authentication.name` |
| `Map<String, Document>` | Một `Map.Entry` | `filterObject.value.owner() == authentication.name` |
| `Stream<Document>` còn sử dụng được | Một `Document` | `filterObject.owner() == authentication.name` |

Với `Map`, phải kiểm tra `filterObject.value` (hoặc `key` nếu chính sách gắn với key) vì phần tử xét là entry:

```java
@PreFilter("filterObject.value.owner() == authentication.name")
public void saveByCode(java.util.Map<String, Document> byCode) {
    // Các entry không đạt điều kiện đã bị loại.
}
```

Đối với `Collection` và `Map`, hãy ưu tiên cấu trúc **có thể thay đổi** như `ArrayList` hoặc `LinkedHashMap`; quy trình lọc có thể cần xóa phần tử/entry. `List.of(...)`, `Stream.toList()`, `Collections.unmodifiableList(...)`, `Map.of(...)` và danh sách kích thước cố định từ `Arrays.asList(...)` không phải là đầu vào an toàn khi cần loại phần tử; chúng có thể gây `UnsupportedOperationException`. Đừng giả định array/stream có cùng đặc tính thay đổi đối tượng gốc như `ArrayList`; kiểm thử theo đúng phiên bản Spring Security đang chạy, và không tái sử dụng một `Stream` đã bị tiêu thụ/đóng.

### 6.4. Khi nào cần kết hợp annotation?

Một service có thể yêu cầu quyền thao tác chung **và** lọc quyền trên phần tử:

```java
@PreAuthorize("hasAuthority('documents:write')")
@PreFilter("filterObject.owner() == authentication.name")
public void updateAllowed(List<Document> documents) {
    // ...
}
```

`@PreAuthorize` kiểm tra quyền của lời gọi, còn `@PreFilter` giới hạn dữ liệu đầu vào. Chúng là các interceptor riêng; trong chuỗi advisor mặc định, interceptor `@PreFilter` có thứ tự sớm hơn `@PreAuthorize`, nên không được dựa vào giả định rằng việc từ chối toàn bộ lời gọi sẽ luôn xảy ra trước mọi thay đổi lên collection đầu vào. Nếu tính nguyên tử và không thay đổi đầu vào khi bị từ chối là yêu cầu cứng, hãy thiết kế và kiểm thử ranh giới này một cách rõ ràng.

## 7. Kiểm thử qua Spring proxy

Đặt file **`src/test/java/demo/DocumentServiceTest.java`**:

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class DocumentServiceTest {

    @Autowired
    DocumentService service;

    @Test
    @WithMockUser(username = "alice")
    void removesOtherOwnersBeforeServiceRuns() {
        var input = new ArrayList<>(List.of(
            new Document(1, "alice"),
            new Document(2, "bob"),
            new Document(3, "alice")
        ));

        var result = service.accept(input);

        assertEquals(List.of(1L, 3L),
            result.stream().map(Document::id).toList());
        assertEquals(List.of(1L, 3L),
            input.stream().map(Document::id).toList());
    }

    @Test
    @WithMockUser(username = "alice")
    void invokesServiceWithEmptyListWhenNothingMatches() {
        var input = new ArrayList<>(List.of(
            new Document(4, "bob")
        ));

        assertTrue(service.accept(input).isEmpty());
        assertTrue(input.isEmpty());
    }
}
```

Chạy:

```bash
./gradlew test
```

`@WithMockUser` đến từ `spring-security-test`, tạo ngữ cảnh bảo mật trong test. Dùng `@Autowired DocumentService` bảo đảm lời gọi đi qua Spring bean/proxy. `new DocumentService().accept(...)` sẽ chỉ kiểm tra Java thuần và **không kiểm thử** cơ chế `@PreFilter`.

Ngoài hai ca trên, nên kiểm thử người dùng khác nhau, danh sách rỗng, collection bất biến, giá trị `null`, nhiều tham số với `filterTarget`, người dùng không đủ quyền khi ghép `@PreAuthorize`, và self-invocation nếu kiến trúc có lời gọi nội bộ.

## 8. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Tất cả phần tử vẫn tới service | Quên `@EnableMethodSecurity`; gọi `new` hoặc gọi nội bộ qua `this` | Bật method security, gọi qua Spring bean/proxy |
| Ném `UnsupportedOperationException` | Truyền `List.of`, `Stream.toList`, `Arrays.asList` hoặc collection không cho xóa | Tạo bản sao `new ArrayList<>(input)` ở ranh giới gọi |
| Không chọn được tham số | Nhiều tham số kiểu collection hoặc tên tham số không xác định | Chỉ rõ `filterTarget`; dùng `@P` hoặc biên dịch `-parameters` |
| Lỗi đánh giá SpEL | Sai accessor, phần tử `null`, kiểu dữ liệu không như dự kiến | Kiểm tra expression trên phần tử thật; xử lý `null` |
| Chạy cả khi không có phần tử được phép | `@PreFilter` lọc, không mặc định từ chối toàn bộ request | Quy định rõ xử lý lô rỗng; dùng quyền toàn lời gọi nếu cần |
| Kết quả bị lọc nhưng dữ liệu đã xử lý trước đó | Nhầm `@PostFilter` với `@PreFilter` | Dùng `@PreFilter` cho tham số đầu vào; không dùng `@PostFilter` làm lá chắn chống ghi trái phép |
| Mất dữ liệu ngoài ý muốn ở biến caller | Collection đầu vào bị thay đổi khi lọc | Dùng bản sao mutable và xét kỹ contract của API |

Một sai lầm đặc biệt nguy hiểm là gọi `@PreFilter("filterObject.owner() == authentication.name")` trên DTO do **client tự đặt** trường `owner`, rồi coi đó là bảo đảm quyền ghi bản ghi thực. Kẻ tấn công có thể gửi `owner="alice"` dù ID trỏ tới tài liệu của người khác. Quyết định cấp quyền phải dựa trên nguồn dữ liệu đáng tin cậy (quyền trong hệ thống, bản ghi lấy từ database hoặc service phân quyền), và tầng cập nhật phải ràng buộc lại ID với chủ thể được quyền thao tác.

## 9. Thiết kế an toàn và hiệu năng

1. **Chọn hành vi xử lý lô:** Nếu chỉ được xử lý toàn bộ hoặc thất bại, từ chối cả lô bằng cơ chế authorization thích hợp. Nếu cho phép xử lý một phần, ghi rõ cách API báo những phần tử được chấp nhận/bỏ qua. Không để việc lọc âm thầm tạo hiểu nhầm rằng mọi mục đã cập nhật.
2. **Không tin dữ liệu tự khai:** Với cập nhật bằng ID, kiểm tra ACL/ownership trên dữ liệu server quản lý, ví dụ biểu thức gọi bean phân quyền `@documentAcl.mayWrite(authentication, filterObject.id())` (đây là ý tưởng tích hợp; cần tự định nghĩa bean và method tương ứng). Tốt hơn nữa, ràng buộc chủ sở hữu ngay trong lệnh truy vấn/cập nhật khi thích hợp.
3. **Quản lý collection:** Tạo bản sao mutable nếu caller vẫn cần danh sách gốc, ví dụ `new ArrayList<>(request.documents())`. Nếu dữ liệu không được phép biến đổi, thiết kế API trả kết quả kiểm tra tách biệt thay vì dựa trên mutation.
4. **Không coi lọc là kiểm tra dữ liệu đầu vào:** Bean Validation, giới hạn kích thước batch, phát hiện ID trùng, transaction và xử lý lỗi là các trách nhiệm khác.
5. **Đánh giá chi phí:** SpEL chạy với mỗi phần tử. Gọi database hoặc dịch vụ bên ngoài cho từng `filterObject` có thể gây vấn đề N+1; với batch lớn, cân nhắc truy vấn theo owner/quyền hoặc phân quyền theo lô.
6. **Kiểm thử qua đường đi thật:** Kiểm tra `Authentication`, proxy, thứ tự annotation, danh sách đầu vào bị thay đổi, và bảo vệ ở tầng dữ liệu. `@PreFilter` không tự cung cấp isolation hay transaction.
7. **Phân biệt lớp web và method:** Quy tắc HTTP (`SecurityFilterChain`) kiểm tra request/route; method security bảo vệ operation ở service. Nên đặt chính sách ở lớp thích hợp, có thể dùng kết hợp.

## 10. Tự kiểm tra kiến thức

1. Người dùng `alice` gửi ba tài liệu với owner `alice`, `bob`, `alice`. Điều kiện `filterObject.owner() == authentication.name` cho kết quả gì? **Chỉ hai tài liệu thuộc `alice` đi vào thân phương thức.**
2. Nếu không có phần tử nào thỏa biểu thức, phương thức có tự động trả HTTP 403 không? **Không.** Phương thức được gọi với đầu vào đã lọc (thường là rỗng), trừ khi cơ chế khác từ chối lời gọi hoặc phát sinh lỗi.
3. Vì sao `List.of(...)` có thể làm hỏng lời gọi? **Nó là danh sách không cho xóa phần tử**, trong khi thao tác lọc collection có thể cần loại phần tử.
4. Khi truyền `Map<String, Document>`, nên tham chiếu gì? **`filterObject.value`** để lấy `Document` từ từng `Map.Entry`.
5. Vì sao kiểm tra `owner` do client tự gửi không đủ bảo mật? **Client có thể giả mạo trường đó**; phân quyền phải dựa vào thông tin sở hữu/quyền được xác minh từ phía server.

## Tài liệu tham khảo

- [Spring Security — Method Security (tài liệu chính thức)](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html), mục *Filtering Method Parameters with `@PreFilter`*.
- [Spring Security — `@PreFilter` API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/access/prepost/PreFilter.html).
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html).

**Ghi nhớ:** `@PreFilter` là bộ lọc **đầu vào của phương thức** dựa trên SpEL, hoạt động qua Spring Method Security, có thể thay đổi collection và thường vẫn cho method chạy sau khi loại phần tử. Dùng nó khi quy tắc nghiệp vụ thực sự chấp nhận lọc một phần; đối với quyền ghi dữ liệu, luôn đối chiếu quyền với nguồn đáng tin cậy.