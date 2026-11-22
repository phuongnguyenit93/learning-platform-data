# Kiểm thử tập rỗng, phần tử không có quyền và dữ liệu hỗn hợp trong Spring Security Method Security

## 1. Mục tiêu

Khi dùng **`@PreFilter`** hoặc **`@PostFilter`**, một kết quả rỗng có thể có hai nguyên nhân rất khác nhau: ban đầu không có phần tử, hoặc có phần tử nhưng tất cả đều không vượt qua biểu thức quyền. Trường hợp dữ liệu hỗn hợp còn khó hơn: hệ thống phải **giữ đúng phần tử hợp lệ**, **loại đúng phần tử trái quyền** và **không làm sai thứ tự**.

Bài này tập trung kiểm thử hành vi lọc dữ liệu **ở ranh giới phương thức** thuộc Spring Security Authorization; không đề cập bộ lọc HTTP `SecurityFilterChain`.

Sau khi hoàn thành, bạn có thể:

- Viết test cho **tập rỗng**, **toàn bộ phần tử không có quyền**, **dữ liệu hỗn hợp**, và đối chứng **toàn bộ phần tử có quyền**.
- Phân biệt các assertion cho `@PreFilter` (lọc **đầu vào trước khi thân phương thức chạy**) và `@PostFilter` (lọc **kết quả sau khi thân phương thức chạy**).
- Dùng `@WithMockUser` và Spring Test để thay đổi principal, kiểm tra biểu thức `filterObject`.
- Phát hiện test cho kết quả đúng ngẫu nhiên do thiếu Spring AOP proxy, sai dữ liệu fixture hoặc chỉ kiểm tra kích thước.
- Phân biệt hành vi **lọc phần tử** với **từ chối toàn bộ lời gọi** bằng `@PreAuthorize`.

**Ngữ cảnh kỹ thuật:** Java 17+, Spring Security 6.x, JUnit Jupiter và AssertJ, minh họa với dependency được quản lý bởi Spring Boot 3.3.x. Test chạy trong Spring test context, không cần khởi động web server.

## 2. Hợp đồng kiểm thử trước khi viết code

Giả sử đang đăng nhập với principal `alice`; biểu thức lọc dùng trong cả hai annotation là:

```java
"filterObject.owner() == authentication.name"
```

`filterObject` là **một phần tử** đang được đánh giá; `authentication.name` là tên người dùng đã xác thực. `owner()` là accessor của Java `record Document` trong ví dụ. Nếu dùng JavaBean với `getOwner()`, có thể truy cập `filterObject.owner`.

Dữ liệu fixture gồm:

| ID | Chủ sở hữu | Được phép khi user = alice? |
| --- | --- | --- |
| A | alice | Có |
| B | bob | Không |
| C | alice | Có |
| D | bob | Không |

Ma trận kết quả kỳ vọng:

| Ca test | Đầu vào / kết quả gốc | Sau lọc với Alice | Điều phải xác nhận |
| --- | --- | --- | --- |
| Empty | `[]` | `[]` | Không lỗi, không tạo phần tử mới |
| All-owned | `[A, C]` | `[A, C]` | Không bỏ nhầm phần tử hợp lệ |
| All-unauthorized | `[B, D]` | `[]` | Tất cả phần tử trái quyền bị loại |
| Mixed | `[A, B, C, D]` | `[A, C]` | Giữ đúng ID và thứ tự tương đối |

Một bài test chỉ gọi `service.filter([])` và assert `isEmpty()` rất yếu: **ngay cả khi annotation không hoạt động, service vẫn có thể trả tập rỗng**. Hãy kết hợp bốn lớp đầu vào và kiểm tra **danh tính cụ thể** của phần tử bằng `containsExactly`, thay vì chỉ dùng `size()`.

Có ba trạng thái không được nhầm lẫn:

1. **Phần tử không có quyền**: B và D bị lọc khỏi danh sách của Alice.
2. **Người gọi chưa xác thực**: không có authentication hợp lệ; cần kiểm thử chính sách xác thực riêng.
3. **Người gọi không được phép thực hiện cả thao tác**: một quyết định `@PreAuthorize` có thể ném `AccessDeniedException`.

`@PreFilter` và `@PostFilter` **không mặc định phát sinh** `AccessDeniedException` mỗi khi loại một phần tử. Nếu tất cả phần tử bị lọc, kết quả có thể là danh sách rỗng và thân phương thức vẫn có thể chạy.

## 3. Thiết lập môi trường kiểm thử

Method security cần lời gọi đi **qua bean được Spring quản lý**. Khởi tạo bằng `new Service()` trong unit test bỏ qua Spring proxy, nên annotation không được thực thi. Dùng `@SpringJUnitConfig` tạo `ApplicationContext`, bật `@EnableMethodSecurity`, rồi inject service; `@WithMockUser` đưa principal vào `SecurityContextHolder` cho test.

Đây là ví dụ tự đủ trong một project Gradle nhỏ. Các tệp cần có:

```text
method-filtering-tests/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/MethodFilteringTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'method-filtering-tests'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

`spring-boot-starter-security` cung cấp các thư viện method security, `spring-boot-starter-test` có JUnit/AssertJ/Spring Test, và `spring-security-test` cung cấp `@WithMockUser`. Ví dụ dùng Spring Boot BOM để đồng bộ phiên bản các dependency nhưng **không cần** ứng dụng Spring Boot `main` để chạy test.

## 4. Tệp kiểm thử Java 17+ hoàn chỉnh

Tạo `src/test/java/demo/MethodFilteringTest.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringJUnitConfig(MethodFilteringTest.SecurityConfig.class)
@WithMockUser(username = "alice", roles = "USER")
public class MethodFilteringTest {

    @Autowired
    FilteringService service;

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    public static class SecurityConfig {
        @Bean
        public FilteringService filteringService() {
            return new FilteringService();
        }
    }

    public record Document(String id, String owner) { }

    public static class FilteringService {

        @PreFilter(
            value = "filterObject.owner() == authentication.name",
            filterTarget = "documents"
        )
        public List<String> accept(@P("documents") List<Document> documents) {
            // Nhận danh sách đã bị @PreFilter lọc trước khi vào body.
            return documents.stream().map(Document::id).toList();
        }

        @PostFilter("filterObject.owner() == authentication.name")
        public List<Document> view(List<Document> source) {
            // @PostFilter lọc kết quả mutable, giữ nguyên collection nguồn.
            return new ArrayList<>(source);
        }

        @PreAuthorize("hasRole('EDITOR')")
        public int editorOnlyCount(List<Document> documents) {
            return documents.size();
        }
    }

    private static Document doc(String id, String owner) {
        return new Document(id, owner);
    }

    // -------- @PreFilter --------

    @Test
    void preFilter_emptyCollection() {
        List<Document> input = new ArrayList<>();

        assertThat(service.accept(input)).isEmpty();
        assertThat(input).isEmpty();
    }

    @Test
    void preFilter_allOwned() {
        List<Document> input = new ArrayList<>(List.of(
            doc("A", "alice"),
            doc("C", "alice")
        ));

        assertThat(service.accept(input)).containsExactly("A", "C");
        assertThat(input).extracting(Document::id)
            .containsExactly("A", "C");
    }

    @Test
    void preFilter_allUnauthorized() {
        List<Document> input = new ArrayList<>(List.of(
            doc("B", "bob"),
            doc("D", "bob")
        ));

        assertThat(service.accept(input)).isEmpty();
        assertThat(input).isEmpty();
    }

    @Test
    void preFilter_mixed() {
        List<Document> input = new ArrayList<>(List.of(
            doc("A", "alice"),
            doc("B", "bob"),
            doc("C", "alice"),
            doc("D", "bob")
        ));

        assertThat(service.accept(input)).containsExactly("A", "C");
        assertThat(input).extracting(Document::id)
            .containsExactly("A", "C");
    }

    // -------- @PostFilter --------

    @Test
    void postFilter_emptyCollection() {
        List<Document> source = List.of();

        assertThat(service.view(source)).isEmpty();
        assertThat(source).isEmpty();
    }

    @Test
    void postFilter_allOwned() {
        List<Document> source = List.of(
            doc("A", "alice"),
            doc("C", "alice")
        );

        assertThat(service.view(source)).extracting(Document::id)
            .containsExactly("A", "C");
        assertThat(source).extracting(Document::id)
            .containsExactly("A", "C");
    }

    @Test
    void postFilter_allUnauthorized() {
        List<Document> source = List.of(
            doc("B", "bob"),
            doc("D", "bob")
        );

        assertThat(service.view(source)).isEmpty();
        assertThat(source).extracting(Document::id)
            .containsExactly("B", "D");
    }

    @Test
    void postFilter_mixed() {
        List<Document> source = List.of(
            doc("A", "alice"),
            doc("B", "bob"),
            doc("C", "alice"),
            doc("D", "bob")
        );

        assertThat(service.view(source)).extracting(Document::id)
            .containsExactly("A", "C");
        assertThat(source).extracting(Document::id)
            .containsExactly("A", "B", "C", "D");
    }

    // -------- Đối chứng principal và chặn toàn phương thức --------

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void sameMixedData_changesWithPrincipal() {
        List<Document> input = new ArrayList<>(List.of(
            doc("A", "alice"),
            doc("B", "bob"),
            doc("C", "alice")
        ));

        assertThat(service.accept(input)).containsExactly("B");
        assertThat(service.view(List.of(
            doc("A", "alice"),
            doc("B", "bob"),
            doc("C", "alice")
        ))).extracting(Document::id).containsExactly("B");
    }

    @Test
    void wholeMethodDenied_isDifferentFromElementFiltering() {
        assertThatThrownBy(() -> service.editorOnlyCount(
            List.of(doc("A", "alice"))
        )).isInstanceOf(AccessDeniedException.class);
    }
}
```

Tệp này là một **test class hoàn chỉnh**, gồm fixture Java `record`, Spring configuration và service test được đặt chung trong một file để có thể chạy độc lập. Chỉ có một test class công khai mang tên trùng tệp.

### Vai trò của các thành phần

- `@EnableMethodSecurity` kích hoạt các interceptor cho `@PreFilter`, `@PostFilter` và `@PreAuthorize`.
- `@SpringJUnitConfig` và `@Autowired` bảo đảm test gọi bean Spring; kiểm thử một service tạo thủ công bằng `new` sẽ không chứng minh annotation hoạt động.
- `@WithMockUser(username="alice")` tạo principal Alice cho các test thường. Test Bob ghi đè annotation trên lớp; bộ lọc phải đổi kết quả đúng theo principal thay vì một tên cứng.
- `@PreFilter(filterTarget="documents")` chỉ định tham số cần lọc; `@P("documents")` đảm bảo Spring Security nhận diện được tên kể cả khi mã biên dịch không có cờ `-parameters`.
- `filterObject.owner()` gọi accessor công khai của `record Document` và so với tên người dùng.
- `accept` trả các ID tới **thân phương thức**; `@PreFilter` lọc trực tiếp một `ArrayList` mutable. Test kiểm tra cả giá trị trả về lẫn nội dung danh sách sau gọi.
- `view` tạo `new ArrayList<>(source)`; `@PostFilter` chỉ thay đổi danh sách **được trả về**, không sửa danh sách bất biến `source` của người gọi.
- `editorOnlyCount` là đối chứng dùng **`@PreAuthorize`**, vì kết quả bị từ chối cả lời gọi là exception, không phải tập được lọc.

### Cách chạy và kết quả mong đợi

Tại thư mục chứa `build.gradle`:

```bash
gradle test --tests demo.MethodFilteringTest
```

Nếu có Gradle Wrapper: Linux/macOS dùng `./gradlew test --tests demo.MethodFilteringTest`, Windows dùng `./gradlew.bat test --tests demo.MethodFilteringTest`.

Kỳ vọng **10 test thành công** và lệnh Gradle kết thúc bằng `BUILD SUCCESSFUL`. Đây là kết quả **kỳ vọng**, không phải stdout đã thu thập từ máy chạy thực tế. Mở `build/reports/tests/test/index.html` để xem kết quả và stack trace của test lỗi. Với dự án đã tồn tại, chỉ thêm class test và các dependency còn thiếu; không cần tạo lại project.

## 5. Giải thích từng trạng thái dữ liệu

### 5.1. Tập rỗng

Với input `[]`, không có phần tử nào để đánh giá biểu thức, do đó `@PreFilter` truyền danh sách rỗng vào method và `@PostFilter` trả danh sách rỗng. Không có phần tử “tự sinh”. Điều này không chứng minh quyền được cấu hình đúng, vì cùng kết quả có thể xảy ra khi method security bị vô hiệu. Bắt buộc chạy thêm test all-unauthorized và mixed.

Cần tách yêu cầu nghiệp vụ: **chấp nhận batch rỗng** hay **từ chối batch rỗng**. Spring Security không thay thế validation của nghiệp vụ. Tập ban đầu rỗng khác tập trở nên rỗng vì bị lọc hết; ở cả hai trường hợp, service có thể nhận `[]`, nên nếu cần phân biệt, phải thiết kế hợp đồng/validation phù hợp trước khi xử lý.

### 5.2. Toàn bộ phần tử không có quyền

Alice gọi với `[B(bob), D(bob)]`. Kết quả lọc là `[]`:

- `@PreFilter`: phần tử bị loại **trước khi vào body**; body có thể vẫn chạy với danh sách rỗng.
- `@PostFilter`: body **đã chạy**, có thể đã truy vấn database hoặc thực hiện tác dụng phụ, trước khi kết quả bị lọc để trả về caller.

Trong cả hai, **không mặc định ném `AccessDeniedException`** chỉ vì không còn phần tử. Nếu yêu cầu phải fail toàn batch khi xuất hiện bất kỳ bản ghi trái quyền, dùng policy kiểm tra quyền toàn danh sách và chặn thao tác sớm, chẳng hạn một `@PreAuthorize`/service guard phù hợp.

### 5.3. Dữ liệu hỗn hợp

Alice gọi `[A, B, C, D]`. Hai bản ghi A và C đủ quyền, B và D không đủ quyền; output phải đúng `[A, C]`, theo thứ tự ban đầu. Kiểm tra **cả ID và thứ tự**, không chỉ `hasSize(2)`: `[B, D]` hoặc `[A, A]` cũng có hai phần tử nhưng vi phạm quyền.

Đây là ca có sức phát hiện lỗi cao: interceptor không chạy sẽ trả cả bốn phần tử; biểu thức sai có thể lọc hết hoặc giữ phần tử của Bob; implementation thao tác sai có thể đảo thứ tự hoặc nhân đôi kết quả.

### 5.4. Tất cả phần tử có quyền

Input `[A, C]` cho Alice phải giữ trọn `[A, C]`. Ca này bắt lỗi policy quá khắt khe, sai thuộc tính `owner` hoặc thiếu principal. Sự có mặt của ca này giúp test all-unauthorized không pass vì code cứng luôn trả rỗng.

### 5.5. Đổi principal và chặn thao tác

Test `sameMixedData_changesWithPrincipal` chạy với Bob trên cùng dữ liệu A/Alice, B/Bob, C/Alice. Expected là chỉ B. Nó buộc kết quả thay đổi theo `authentication.name`.

Test `wholeMethodDenied_isDifferentFromElementFiltering` dùng role USER gọi method yêu cầu EDITOR và kiểm tra `AccessDeniedException`. Đây là **authorization cho toàn phương thức**, khác hẳn việc giữ một tập con. Nếu cần kiểm thử status HTTP 403, thực hiện ở lớp web với mock request hoặc token thích hợp; method test không tự trả HTTP response.

## 6. Mở rộng các ca biên để tránh lỗ hổng

Khi hệ thống thực có thêm dữ liệu hoặc kiểu container phức tạp, bổ sung test theo bảng dưới đây.

| Ca bổ sung | Rủi ro muốn phát hiện | Assertion cần có |
| --- | --- | --- |
| Xen kẽ `[B,A,D,C]` | Chỉ lọc sai phần tử đầu/cuối, mất thứ tự | Output `[A,C]` |
| Trùng ID, khác tenant/owner | Chỉ kiểm tra ID mà bỏ qua phạm vi quyền | Chỉ giữ record thuộc tenant và principal hợp lệ |
| Không phần tử nào khớp user thứ ba | Policy hardcode hoặc dùng sai SecurityContext | Result rỗng, không có dữ liệu của Alice/Bob |
| Phần tử `null` trong collection | SpEL gọi `owner()` trên null | Có policy rõ: guard để loại hoặc validation từ chối |
| Đối số đích lọc bằng `null` | Nhầm null với empty list | Assertion theo validation/hợp đồng; không mặc định xem là `[]` |
| `List.of(...)` truyền vào `@PreFilter` | Collection không hỗ trợ `remove` | Kiểm chứng lỗi hoặc copy sang `ArrayList` trước khi gọi |
| Nhiều tham số `List` | Lọc sai danh sách | `filterTarget` trỏ đúng tên và tham số còn lại không bị đổi |
| `Map`, array, `Stream` | Khác biệt cách lọc, phần tử và lifecycle | Viết fixture/assertion riêng đúng kiểu thực tế |
| Self-invocation `this.method()` | Gọi không qua AOP proxy | Kiểm thử đường gọi production qua Spring bean |
| Result phân trang hoặc nhiều dữ liệu | `@PostFilter` lọc sau khi query khiến tổng/trang sai | Kiểm tra ID, số trang, total count và query có ràng buộc quyền |

Ví dụ nếu yêu cầu **loại bỏ phần tử null**, thay biểu thức lọc bằng:

```java
@PreFilter(
    value = "filterObject != null and filterObject.owner() == authentication.name",
    filterTarget = "documents"
)
```

Đây là đoạn **annotation minh họa**, không phải chương trình Java độc lập. Nó thay đổi chính sách so với ví dụ gốc: trước khi thêm phải xác định nghiệp vụ muốn **bỏ** `null` hay **báo lỗi**. Tương tự, nếu một tài liệu mang `owner` do client tự khai báo, so sánh đơn thuần với field này không đủ bảo đảm quyền; kiểm tra dữ liệu đáng tin từ phía server.

## 7. Cách kiểm thử ở các lớp của ứng dụng

**Service integration test** là lớp chính để kiểm tra method security. Giữ fixture nhỏ, xác định rõ owner, và gọi service đã được Spring inject. Nếu cần kiểm tra side effect, dùng mock/repository spy hoặc database test để khẳng định:

- Dữ liệu không được phép **không đến phần nghiệp vụ ghi** khi dùng `@PreFilter`.
- Dữ liệu được trả cho caller đã qua `@PostFilter`; trường hợp có tác dụng phụ trước lọc phải được kiểm soát riêng.
- Một lần chạy với Alice không làm thay đổi kết quả của lần chạy với Bob qua cache hoặc state chia sẻ.

**HTTP/MockMvc test** là lớp bổ sung để xác thực cách endpoint biến result thành JSON và exception thành status. `@WithMockUser` chỉ đặt `SecurityContext` trên thread của test; nếu test gửi HTTP đến server thật chạy thread khác, phải xác thực **request** bằng cơ chế phù hợp. Không dựa vào `@WithMockUser` trên method test để suy ra token HTTP đã được gửi.

**Repository/tenant test** cần kiểm tra giới hạn dữ liệu ngay từ truy vấn. `@PostFilter` là lọc trong bộ nhớ **sau khi method có kết quả**, nên không thay thế query ràng buộc owner/tenant; nó có thể làm sai số liệu phân trang và khiến tải dữ liệu thừa. Với dữ liệu nhạy cảm, kiểm tra đồng thời điều kiện tại database, service và response.

## 8. Lỗi kiểm thử phổ biến

| Hiện tượng | Nguyên nhân có thể | Khắc phục |
| --- | --- | --- |
| Empty test pass nhưng unauthorized vẫn lọt | Empty không chứng minh interceptor chạy | Thêm mixed, all-owned và all-unauthorized |
| Annotation không lọc | Thiếu `@EnableMethodSecurity`, dùng `new`, self-invocation | Dùng Spring context và bean proxy |
| `UnsupportedOperationException` | `@PreFilter` cần xóa phần tử khỏi collection bất biến | Dùng `new ArrayList<>(...)` |
| Lỗi SpEL `owner()` | Sai kiểu phần tử, accessor không tồn tại hoặc giá trị null | Điều chỉnh biểu thức/fixture và policy null |
| Test chỉ assert `size() == 2` | Hai phần tử được giữ có thể là B và D | Assert `containsExactly("A", "C")` |
| Dữ liệu trả đúng nhưng input nguồn đổi ngoài ý muốn | `@PostFilter` lọc collection shared | Trả bản sao mutable khi muốn giữ nguyên nguồn |
| Mong có `AccessDeniedException` cho từng record bị loại | Nhầm lọc phần tử với deny method | Thiết kế test authorization toàn method riêng |
| Test pass với Alice, thất bại với Bob | Policy hardcode hoặc context sai | Test principal thứ hai; kiểm tra authentication name |
| Data API trả rỗng nhưng thao tác ghi vẫn xảy ra | `@PostFilter` chạy sau thân method | Chặn ghi trước khi có side effect |
| HTTP test không có principal mong muốn | Test auth không gắn vào request thật | Dùng cơ chế auth của MockMvc/client/request |

## 9. Checklist nghiệm thu

1. Bộ test có **empty, all-authorized, all-unauthorized và mixed** cho từng annotation cần sử dụng.
2. Có ít nhất **hai principal**, dữ liệu gắn owner/tenant rõ ràng và assertion theo **ID + thứ tự**, không chỉ số lượng.
3. `@PreFilter` dùng collection mutable, kiểm tra nội dung thực sự đến thân method; `@PostFilter` kiểm tra kết quả caller nhận và tình trạng dữ liệu nguồn.
4. Test lấy **Spring-managed bean** qua injection, bật `@EnableMethodSecurity`, và dùng `@WithMockUser` hoặc test security context tương đương.
5. Nếu nghiệp vụ yêu cầu chặn toàn thao tác, có test riêng cho `@PreAuthorize`/policy với exception đúng; không mong annotation lọc tự trả 403.
6. Những đặc điểm thực tế như null, immutable, tenant, nhiều danh sách, phân trang và side effect có ca kiểm thử thích hợp.

**Ghi nhớ:** Tập rỗng xác nhận xử lý biên, tập toàn trái quyền xác nhận loại bỏ, tập toàn hợp lệ xác nhận không lọc quá mức, còn tập hỗn hợp xác nhận **đồng thời** cả hai chiều. Bốn tình huống phải đi cùng nhau để chứng minh lọc phương thức đang thực thi đúng dưới một principal thật trong Spring Test.

## Tham khảo

- Spring Security Reference — Method Security, `@PreFilter` và `@PostFilter`: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security Reference — Testing Method Security và `@WithMockUser`: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security API — `@PreFilter`, `filterTarget`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PreFilter.html
