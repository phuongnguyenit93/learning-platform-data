# Kiểm thử `@PreFilter`, `@PostFilter` và nội dung tập dữ liệu sau lọc

> Phạm vi: Spring Security Method Security trong ứng dụng Spring dùng proxy/AOP, Java 17+, JUnit 5 và `spring-security-test`. Mục tiêu là chứng minh **phần tử nào được phép đi vào phương thức** và **phần tử nào thực sự đến tay người gọi**; chỉ kiểm tra HTTP 200 hoặc số lượng phần tử là chưa đủ.

## 1. Cơ chế cần hiểu trước khi viết test

Khi cấu hình `@EnableMethodSecurity`, Spring Security tạo các interceptor để xử lý annotation trên **bean do Spring quản lý**:

| Annotation | Thời điểm | Dữ liệu bị lọc | Cần khẳng định trong test |
| --- | --- | --- | --- |
| `@PreFilter` | Trước khi chạy thân phương thức | Một đối số dạng tập hợp/array/map/stream phù hợp | Bên trong phương thức chỉ nhìn thấy phần tử thỏa biểu thức |
| `@PostFilter` | Sau khi thân phương thức tạo kết quả, trước khi trả về caller | Các phần tử trong kết quả trả về phù hợp | Caller chỉ nhận được các phần tử được phép, đúng ID/nội dung |
| `@PreAuthorize` | Trước khi chạy phương thức | Quyết định có được gọi hay không | Khi bị từ chối, phát sinh lỗi truy cập thay vì âm thầm loại phần tử |

Ví dụ biểu thức `filterObject.owner == authentication.name` được đánh giá **cho từng phần tử**. `filterObject` là phần tử đang xét; `authentication.name` là tên principal hiện tại trong `SecurityContext`. Với `Map<K,V>`, phần tử để lọc là một entry, vì vậy thường dùng `filterObject.value.owner`. `@PreFilter` có thể chỉ định đối số bằng `filterTarget` khi phương thức có nhiều tham số.

Hai phép lọc **không đồng nghĩa với từ chối toàn bộ request**: một danh sách toàn phần tử không hợp lệ thường trở thành danh sách rỗng; phương thức vẫn có thể được gọi. Muốn từ chối người chưa đăng nhập hoặc thiếu quyền gọi phương thức, hãy dùng thêm quy tắc như `@PreAuthorize("isAuthenticated()")` hay `@PreAuthorize("hasAuthority('document:read')")` theo yêu cầu nghiệp vụ.

Luồng kiểm tra điển hình:

```text
@WithMockUser("alice") tạo SecurityContext
                  |
                  v
Caller -> Spring proxy -> @PreFilter -> service body -> @PostFilter -> Caller
                             |                               |
                   kiểm tra input vào body          kiểm tra output trả về
```

**Ranh giới quan trọng:** Lệnh `new FilterService()` trực tiếp không đi qua Spring proxy; annotation có thể không được áp dụng. Test có giá trị kiểm chứng enforcement phải lấy bean qua ApplicationContext và bật Method Security.

## 2. Thiết kế test từ dữ liệu có thể dự đoán

Giả sử service quản lý các tài liệu `(id, owner)`:

| ID | Owner | Kết quả dự kiến cho `alice` |
| --- | --- | --- |
| `A1` | `alice` | Giữ |
| `B1` | `bob` | Loại |
| `A2` | `alice` | Giữ |

Với cùng tập đầu vào theo thứ tự trên:

- `@PreFilter`: code bên trong `service.accept(...)` phải xử lý **chính xác** `["A1", "A2"]`.
- `@PostFilter`: `service.visibleDocuments()` có thể tạo cả ba đối tượng, nhưng caller chỉ nhận `["A1", "A2"]`.
- Principal `bob` nhận `["B1"]`; principal `charlie` nhận `[]`.
- Khi toàn bộ phần tử được phép, giữ toàn bộ; khi không phần tử nào được phép, trả tập rỗng.
- Nếu trả `Map`, cần kiểm tra **key và value** còn lại, không chỉ độ lớn.

Các assertion kiểu `assertEquals(2, result.size())` có thể bỏ lọt lỗi khi service trả sai 2 đối tượng. Luôn so ID, owner hoặc toàn bộ object đúng theo contract và kiểm tra phần tử nhạy cảm không còn hiện diện.

## 3. Ví dụ tích hợp chạy được (Spring Test, JUnit 5)

Trong dự án Spring Boot dùng Gradle, cần Spring Security, Spring Test/JUnit và `spring-security-test`. Nếu dự án đã có starter tương ứng, không khai báo trùng. Phần `dependencies` điển hình (phiên bản do Spring Boot BOM/plugin quản lý):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo **một file hoàn chỉnh** `src/test/java/com/example/security/MethodFilteringTest.java`. Ví dụ tạo Spring context gọn bằng `@SpringJUnitConfig`; không cần khởi động web server hay controller.

```java
package com.example.security;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(MethodFilteringTest.TestConfig.class)
public class MethodFilteringTest {

    @Autowired
    FilterService service; // Bean do Spring cấp: lời gọi đi qua proxy

    @Test
    @WithMockUser(username = "alice")
    void preFilter_removesOtherOwnersBeforeServiceRuns() {
        List<Document> input = new ArrayList<>(List.of(
                new Document("A1", "alice"),
                new Document("B1", "bob"),
                new Document("A2", "alice")));

        // Hàm accept() tự đọc argument bên trong method body.
        assertEquals(List.of("A1", "A2"), service.accept(input));
    }

    @Test
    @WithMockUser(username = "alice")
    void preFilter_allForeignDocumentsYieldsEmptyInput() {
        List<Document> input = new ArrayList<>(List.of(
                new Document("B1", "bob")));

        assertEquals(List.of(), service.accept(input));
    }

    @Test
    @WithMockUser(username = "alice")
    void preFilter_allOwnedDocumentsAreKept() {
        List<Document> input = new ArrayList<>(List.of(
                new Document("A1", "alice"),
                new Document("A2", "alice")));

        assertEquals(List.of("A1", "A2"), service.accept(input));
    }

    @Test
    @WithMockUser(username = "alice")
    void postFilter_keepsOnlyAliceDocuments() {
        List<Document> result = service.visibleDocuments();

        assertEquals(List.of("A1", "A2"), ids(result));
    }

    @Test
    @WithMockUser(username = "bob")
    void postFilter_changesWithAuthenticatedPrincipal() {
        List<Document> result = service.visibleDocuments();

        assertEquals(List.of("B1"), ids(result));
    }

    @Test
    @WithMockUser(username = "charlie")
    void postFilter_noOwnedDocumentYieldsEmptyResult() {
        List<Document> result = service.visibleDocuments();

        assertEquals(List.of(), ids(result));
    }

    @Test
    @WithMockUser(username = "alice")
    void postFilter_mapRemovesUnauthorizedEntries() {
        Map<String, Document> result = service.visibleMap();

        assertEquals(List.of("first", "third"),
                new ArrayList<>(result.keySet()));
        assertEquals(List.of("A1", "A2"),
                result.values().stream().map(Document::getId).toList());
    }

    private static List<String> ids(List<Document> documents) {
        return documents.stream().map(Document::getId).toList();
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    public static class TestConfig {
        @Bean
        FilterService filterService() {
            return new FilterService();
        }
    }

    public static class FilterService {

        @PreFilter("filterObject.owner == authentication.name")
        public List<String> accept(List<Document> documents) {
            // Đây là dữ liệu service THỰC SỰ nhận sau @PreFilter.
            return documents.stream().map(Document::getId).toList();
        }

        @PostFilter("filterObject.owner == authentication.name")
        public List<Document> visibleDocuments() {
            // Tập kết quả gốc cố ý chứa cả record không được xem.
            return new ArrayList<>(List.of(
                    new Document("A1", "alice"),
                    new Document("B1", "bob"),
                    new Document("A2", "alice")));
        }

        @PostFilter("filterObject.value.owner == authentication.name")
        public Map<String, Document> visibleMap() {
            Map<String, Document> all = new LinkedHashMap<>();
            all.put("first", new Document("A1", "alice"));
            all.put("second", new Document("B1", "bob"));
            all.put("third", new Document("A2", "alice"));
            return all;
        }
    }

    public static class Document {
        private final String id;
        private final String owner;

        public Document(String id, String owner) {
            this.id = id;
            this.owner = owner;
        }

        public String getId() {
            return id;
        }

        public String getOwner() {
            return owner;
        }
    }
}
```

Chạy từ thư mục gốc của dự án đã có Gradle Wrapper:

```bash
./gradlew test --tests "com.example.security.MethodFilteringTest"
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.security.MethodFilteringTest"
```

**Kết quả kỳ vọng:** 7 test xanh. Với các fixture cố định ở ví dụ, các kết quả cần đối chiếu lần lượt là `["A1","A2"]`, `[]`, `["A1","A2"]`, `["A1","A2"]`, `["B1"]`, `[]` và map chỉ còn key `first`, `third`. Đây là **kỳ vọng assertion**, không phải stdout của một chương trình có `main`; JUnit/Gradle hiển thị log khác nhau theo cấu hình.

Giải thích vì sao test thực sự kiểm tra security:

1. `@SpringJUnitConfig` khởi tạo Spring context và lấy `FilterService` bằng `@Autowired`; `@EnableMethodSecurity` kích hoạt interceptor.
2. `@WithMockUser(username = "alice")` dựng `Authentication` cho từng test và Spring Test dọn `SecurityContext` sau test. Không cần đăng nhập thật, tạo JWT hay cấu hình MockMvc chỉ để kiểm tra method security.
3. Trong `accept`, lệnh chuyển thành ID nằm **trong thân phương thức**: nếu `@PreFilter` không chạy, test đầu tiên sẽ trả cả `"B1"` và thất bại.
4. Trong `visibleDocuments`, phương thức cố ý tạo ba tài liệu, còn assertion nằm **sau lời gọi proxy**: nếu `@PostFilter` không chạy, caller nhận cả `"B1"` và test thất bại.
5. `visibleMap` dùng `LinkedHashMap` để quan sát key theo thứ tự chèn; biểu thức map phải truy cập `filterObject.value.owner`.

## 4. Chứng minh đủ nội dung, ranh giới và kết quả sau lọc

Một bộ test mạnh nên dùng cùng cấu trúc **Given–When–Then**:

- **Given:** xác định principal, tập ID và owner; cố ý trộn đối tượng được phép/không được phép và giữ thứ tự đầu vào.
- **When:** gọi **Spring bean qua proxy** với danh sách có thể sửa đổi khi kiểm tra `@PreFilter`, hoặc gọi phương thức trả dữ liệu có cả hai loại khi kiểm tra `@PostFilter`.
- **Then:** assert tập ID/owner/keys **chính xác**, điều kiện rỗng, và không còn đối tượng khác chủ sở hữu. Nếu yêu cầu thứ tự là một phần API contract, assert cả thứ tự.
- **Đối với `@PreFilter`:** ưu tiên trả về hoặc ghi nhận snapshot **ngay trong thân phương thức** (như `accept`) để khẳng định argument đã bị lọc *trước* logic nghiệp vụ. Chỉ assert input ở caller sau lời gọi có thể khiến test phụ thuộc chi tiết mutation của collection.
- **Đối với `@PostFilter`:** so dữ liệu mà caller nhận được, không chỉ dữ liệu mà repository/mock tạo ra. Repository trả đủ ba bản ghi không có nghĩa caller được phép thấy cả ba.

Bảng ca kiểm thử tối thiểu:

| Principal | Đầu vào/kết quả gốc | Điểm kiểm tra | Kỳ vọng |
| --- | --- | --- | --- |
| `alice` | `A1, B1, A2` | Input trong service (`@PreFilter`) | `A1, A2` |
| `alice` | `B1` | Input trong service | Rỗng, phương thức vẫn thực thi |
| `alice` | `A1, A2` | Input trong service | Giữ cả hai |
| `alice` | `A1, B1, A2` | Output caller (`@PostFilter`) | `A1, A2` |
| `bob` | `A1, B1, A2` | Output caller | `B1` |
| `charlie` | `A1, B1, A2` | Output caller | Rỗng |
| `alice` | Map `first→A1, second→B1, third→A2` | Key + value output | Chỉ `first→A1, third→A2` |

Có thể bổ sung test kiểm tra **hai tài liệu trùng owner nhưng ID khác nhau** (đã có `A1`, `A2`) để chắc chắn logic không chỉ giữ phần tử đầu tiên; test bản ghi rỗng/null, nhiều quyền, thuộc tính nhạy cảm và thứ tự nếu nghiệp vụ quy định. Mỗi ca cần có mong đợi rõ ràng; không tự suy ra rằng annotation sẽ ném `AccessDeniedException` chỉ vì tất cả phần tử bị loại.

## 5. Tình huống nâng cao và các giới hạn cần kiểm thử

### Chọn tham số cho `@PreFilter`

Khi phương thức có nhiều tham số, có thể chỉ định rõ đối số:

```java
@PreFilter(value = "filterObject.owner == authentication.name",
           filterTarget = "documents")
public void importBatch(String batchId, List<Document> documents) {
    // documents đã được lọc trước khi phần thân chạy
}
```

Đây là **snippet minh họa trong service**, không phải chương trình độc lập. Để Spring nhận ra tên tham số `documents`, bảo đảm Java được biên dịch với `-parameters` (hoặc dùng cơ chế khai báo tên tham số mà phiên bản Spring Security hiện dùng hỗ trợ). Không đoán tên khi nhiều tập hợp có thể cùng là filter target.

### `Map`, array và `Stream`

Tài liệu Spring Security hiện hành nêu hỗ trợ collection, array, map và stream cho `@PreFilter`/`@PostFilter`; cần xác nhận hành vi theo **phiên bản đang chạy**. Khi lọc `Map`, `filterObject` là entry, nên thường viết `filterObject.value.owner`, như test minh họa. Với `Stream`, chỉ sử dụng stream còn mở và nhớ rằng một stream chỉ được tiêu thụ một lần. Với array, kiểm thử chính xác tập phần tử sau lọc và kiểu trả về của phiên bản sử dụng. Không mở rộng test collection rồi mặc nhiên kết luận mọi container có cùng chi tiết mutation.

### Collection không thể sửa và hiệu ứng phụ

Đối với thử nghiệm `@PreFilter`, tạo `new ArrayList<>(...)` thay vì truyền trực tiếp `List.of(...)` rồi giả định danh sách luôn có thể bị remove: tùy phiên bản/đường xử lý, loại collection không hỗ trợ sửa đổi có thể dẫn đến lỗi. Đối với `@PostFilter`, trả về `new ArrayList<>(...)` trong fixture và khẳng định **kết quả caller nhìn thấy**. Nếu service ghi DB, gửi message hoặc gọi API trước khi `@PostFilter` áp dụng, lọc output **không hoàn tác** những side effect đó. `@PostFilter` cũng không thay thế điều kiện lọc tại repository/query: với tập dữ liệu lớn hoặc pagination, nên đẩy điều kiện phân quyền xuống data layer và kiểm thử cả boundary truy vấn, count và page metadata.

### Principal, phân quyền và proxy

`@WithMockUser` thích hợp khi biểu thức dựa trên tên/authority. Nếu biểu thức dùng principal tùy biến hoặc claims, dùng `@WithUserDetails` hay `@WithSecurityContext` để dựng đúng kiểu `Authentication`. `roles = "ADMIN"` tạo authority `ROLE_ADMIN`, còn `authorities = "document:read"` dùng tên chính xác; không hoán đổi hai cách ghi. Bật `@EnableMethodSecurity` trên cấu hình test, gọi bean qua Spring; lời gọi nội bộ `this.otherSecuredMethod()` trong cùng bean thường bỏ qua interceptor proxy (self-invocation). Kiểm thử call path thực sự được ứng dụng dùng.

### Không nhầm lọc với từ chối truy cập

- Lọc từng phần tử: sai biểu thức khiến phần tử bị bỏ; tập có thể rỗng.
- Chặn cả phương thức: dùng `@PreAuthorize` hay authorization tương ứng để kiểm tra ngoại lệ khi chưa đủ quyền.
- Với trang HTTP, kiểm tra thêm serialization/response nếu muốn bảo đảm JSON không chứa record nhạy cảm; test method security riêng kiểm tra đúng **service boundary**, không tự chứng minh mọi controller mapping đều an toàn.

## 6. Lỗi thường gặp và cách phát hiện

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý/test |
| --- | --- | --- |
| Test vẫn xanh dù xóa `@PreFilter` | Chỉ assert số lượng hoặc giả lập dữ liệu đã lọc | Đưa cả bản ghi `bob` vào input; assert snapshot ID **bên trong** service |
| Test vẫn xanh dù xóa `@PostFilter` | Mock repository chỉ trả tài liệu được phép | Cố ý trả dữ liệu hỗn hợp từ service; assert output caller đúng ID |
| Trả mọi phần tử dù đã gắn annotation | Dùng `new`/gọi nội bộ, thiếu `@EnableMethodSecurity` | Lấy bean Spring qua `@Autowired`; kiểm tra proxy |
| SpEL lỗi khi có nhiều danh sách | Chưa xác định `filterTarget` hoặc mất tên tham số | Chỉ định đúng target, biên dịch `-parameters` |
| `@PreFilter` lỗi với danh sách bất biến | Fixture dùng `List.of(...)` trực tiếp | Dùng `new ArrayList<>(List.of(...))` |
| Map lọc sai | Dùng `filterObject.owner` trên entry | Chọn `filterObject.value.owner`, assert key lẫn value |
| Test nhầm `403` với kết quả rỗng | Coi filtering như authorization phủ định toàn bộ | Tách test `@PreAuthorize` với test `@PreFilter/@PostFilter` |
| Rò thông tin qua count/pagination | Chỉ lọc danh sách ở lớp service sau query | Áp điều kiện quyền ở truy vấn và test metadata/API riêng |

## 7. Checklist nghiệm thu

1. Có `@EnableMethodSecurity`, bean thực sự do Spring tạo, test sử dụng `spring-security-test`.
2. Fixture có ít nhất một phần tử hợp lệ và một phần tử bị loại; có test tất cả hợp lệ, tất cả bị loại.
3. `@PreFilter`: chứng minh dữ liệu **đã lọc khi thân method bắt đầu xử lý**.
4. `@PostFilter`: chứng minh caller nhận **đúng tập ID/owner/map entries** sau lọc.
5. Đổi principal cho cùng fixture làm thay đổi kết quả đúng dự đoán.
6. Không nhầm tập rỗng với access denied, không nhầm unit test gọi trực tiếp đối tượng với test interceptor thật.
7. Test công khai một contract: có kiểm tra thứ tự nếu API hứa thứ tự; với dữ liệu lớn/pagination, kiểm tra phân quyền tại data layer.

## Tài liệu đối chiếu

- [Spring Security — Method Security (lọc tham số và kết quả)](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — `@WithMockUser` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html)
