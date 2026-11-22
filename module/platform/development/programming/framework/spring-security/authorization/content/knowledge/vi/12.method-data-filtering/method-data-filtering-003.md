# @PostFilter trong Spring Security: lọc tập kết quả theo quyền của từng phần tử

## 1. Mục tiêu và tình huống sử dụng

Trong ứng dụng đa người dùng, một phương thức service có thể trả về nhiều bản ghi nhưng mỗi người chỉ được phép xem một phần. Ví dụ, `DocumentService.findAll()` trả về ba tài liệu: tài liệu 1 và 3 thuộc `alice`, tài liệu 2 thuộc `bob`. Khi `alice` gọi phương thức, kết quả hợp lệ chỉ gồm tài liệu 1 và 3.

`@PostFilter` là annotation của **Spring Security Method Security** dùng để **lọc từng phần tử của giá trị trả về sau khi phương thức đã thực thi**. Mỗi phần tử được kiểm tra bằng một biểu thức Spring Expression Language (SpEL). Phần tử cho kết quả `true` được giữ lại; phần tử cho `false` bị loại khỏi tập kết quả mà bên gọi nhận được.

Đây là một dạng **ủy quyền theo từng phần tử** (element-level authorization), thường gặp với danh sách tài liệu, đơn hàng, hồ sơ, tài nguyên thuộc chủ sở hữu, hoặc dữ liệu phân vùng theo tenant.

**Phân biệt ba câu hỏi:**
- “Người dùng có được gọi phương thức này không?” → `@PreAuthorize`, đánh giá trước khi chạy.
- “Người dùng có được nhận toàn bộ đối tượng đơn lẻ này không?” → `@PostAuthorize`, đánh giá kết quả và có thể từ chối.
- “Trong tập kết quả, người dùng được nhận phần tử nào?” → `@PostFilter`, giữ những phần tử thỏa điều kiện.

`@PostFilter` **không biến kết quả không hợp lệ thành lỗi 403 cho từng phần tử**. Nếu không có phần tử nào được phép xem, danh sách sau lọc thường rỗng. Nếu phải từ chối toàn bộ lời gọi, hãy kết hợp một kiểm tra như `@PreAuthorize`.

## 2. Cơ chế hoạt động và biểu thức SpEL

Để dùng annotation trong ứng dụng Spring Security servlet theo mô hình proxy, bật Method Security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

`@EnableMethodSecurity` cho phép dùng `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` mặc định. Chỉ thêm Spring Security dependency **không tự động bật Method Security** trong Spring Boot. Nếu đã đặt `@EnableMethodSecurity` trên class `@SpringBootApplication` thì không cần tạo config thứ hai.

Ví dụ cú pháp cơ bản:

```java
@PostFilter("filterObject.owner == authentication.name")
public List<Document> findAll() {
    // Trả về danh sách các Document để bộ lọc xét từng phần tử.
}
```

Đây là **đoạn minh họa chữ ký phương thức**, chưa phải class Java độc lập. Trong biểu thức:
- `filterObject`: **phần tử hiện tại** khi Spring Security duyệt kết quả. Với một `List<Document>`, đó là từng `Document`.
- `filterObject.owner`: đọc thuộc tính JavaBean `owner` (thường qua `getOwner()`) của phần tử hiện tại.
- `authentication`: đối tượng `Authentication` từ `SecurityContext` tại thời điểm ủy quyền.
- `authentication.name`: tên định danh người đã xác thực, chẳng hạn `alice`.
- `hasRole('ADMIN')`, `hasAuthority('DOCUMENT_READ')`, `hasPermission(...)`: các biểu thức ủy quyền khác; `hasRole('ADMIN')` thường kiểm tra authority `ROLE_ADMIN`.

Luồng thực thi đơn giản:

1. Caller gọi **Spring-managed bean thông qua AOP proxy**.
2. Nếu có `@PreAuthorize`, điều kiện tiền kiểm được xét trước.
3. Service chạy và trả về kết quả gốc.
4. `PostFilterAuthorizationMethodInterceptor` đánh giá SpEL cho từng phần tử bằng `filterObject` và authentication đang có.
5. Bộ lọc loại phần tử không đạt điều kiện; caller nhận kết quả đã lọc.

Ví dụ đối chiếu:

| Phần tử | `owner` | User `alice` | Kết quả |
|---|---|---|---|
| Document 1 | `alice` | `alice` | Giữ |
| Document 2 | `bob` | `alice` | Loại |
| Document 3 | `alice` | `alice` | Giữ |

Biểu thức áp dụng **tại thời điểm trả về**, vì vậy mọi truy vấn, tính toán hoặc tác dụng phụ bên trong phương thức đã xảy ra trước khi quá trình lọc bắt đầu.

## 3. Ví dụ chạy được với Java 17, Spring Boot 3 và JUnit 5

Ví dụ dưới đây tạo service trả về dữ liệu thử và kiểm thử quyền của hai user. Dùng Java 17+, Spring Boot 3.x/Spring Security 6.x, Maven. Bốn file Java có cùng package `com.example.postfilter`; đặt file test trong `src/test/java` và ba file ứng dụng trong `src/main/java`.

**`pom.xml`** (ví dụ dùng Spring Boot 3.5.6):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>postfilter-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/com/example/postfilter/PostFilterApplication.java`**

```java
package com.example.postfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class PostFilterApplication {
    public static void main(String[] args) {
        SpringApplication.run(PostFilterApplication.class, args);
    }
}
```

**`src/main/java/com/example/postfilter/Document.java`**

```java
package com.example.postfilter;

public record Document(long id, String owner) {
    // JavaBean getter để SpEL truy cập được thuộc tính "owner".
    public String getOwner() {
        return owner;
    }
}
```

**`src/main/java/com/example/postfilter/DocumentService.java`**

```java
package com.example.postfilter;

import java.util.ArrayList;
import java.util.List;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    @PreAuthorize("isAuthenticated()")
    @PostFilter("filterObject.owner == authentication.name")
    public List<Document> findAll() {
        // Trả về bản sao mutable, tránh sửa một collection dùng chung.
        return new ArrayList<>(List.of(
            new Document(1L, "alice"),
            new Document(2L, "bob"),
            new Document(3L, "alice")
        ));
    }
}
```

**`src/test/java/com/example/postfilter/DocumentServiceTest.java`**

```java
package com.example.postfilter;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class DocumentServiceTest {
    @Autowired
    private DocumentService service;

    @Test
    @WithMockUser(username = "alice")
    void aliceOnlySeesHerDocuments() {
        List<Long> ids = service.findAll()
            .stream().map(Document::id).toList();
        assertEquals(List.of(1L, 3L), ids);
    }

    @Test
    @WithMockUser(username = "bob")
    void bobOnlySeesHisDocument() {
        List<Long> ids = service.findAll()
            .stream().map(Document::id).toList();
        assertEquals(List.of(2L), ids);
    }

    @Test
    @WithMockUser(username = "charlie")
    void userWithNoOwnershipGetsEmptyList() {
        assertTrue(service.findAll().isEmpty());
    }
}
```

Tại thư mục chứa `pom.xml`, chạy:

```bash
mvn test
```

Kỳ vọng **cả 3 test đều pass**: `alice → [1, 3]`, `bob → [2]`, `charlie → []`. Dòng log Maven/Spring không cố định nên không coi là stdout chuẩn của ví dụ. Trọng tâm kiểm thử là **kết quả của method security trên bean được proxy**, không chỉ kiểm tra biểu thức bằng cách gọi một phương thức Java thông thường.

Trong ứng dụng web thực tế, `Authentication` thường được thiết lập bởi cơ chế đăng nhập/JWT filter; service trên dùng lại ngữ cảnh ấy. Các tài liệu ví dụ không được lấy từ database để tránh che khuất cách hoạt động của `@PostFilter`.

## 4. Viết chính sách lọc theo quyền thực tế

### 4.1. Chủ sở hữu hoặc quản trị viên

```java
@PreAuthorize("isAuthenticated()")
@PostFilter("hasRole('ADMIN') or filterObject.owner == authentication.name")
public List<Document> findVisibleDocuments() {
    return loadDocumentsAsMutableList();
}
```

Đây là **mẫu phương thức**: `loadDocumentsAsMutableList()` đại diện hàm truy vấn do ứng dụng cung cấp, chưa phải chương trình chạy riêng. `ROLE_ADMIN` có thể nhận toàn bộ các tài liệu phương thức đã tải; user thông thường chỉ thấy tài liệu của mình. Đừng coi `hasRole` là phép gán role: role phải được cấp thực sự trong `Authentication`.

### 4.2. Phải có quyền đọc chung trước khi lọc

```java
@PreAuthorize("hasAuthority('DOCUMENT_READ')")
@PostFilter("filterObject.owner == authentication.name")
public List<Document> findReadableDocuments() {
    return loadDocumentsAsMutableList();
}
```

`@PreAuthorize` yêu cầu quyền `DOCUMENT_READ` **trước khi thực thi**; `@PostFilter` tiếp tục giới hạn theo chủ sở hữu **sau khi có kết quả**. Hai annotation giải quyết hai mức quyết định khác nhau, không thay thế nhau. Phương thức trên là mẫu tích hợp, phụ thuộc vào hàm tải dữ liệu của ứng dụng.

### 4.3. Chính sách phức tạp đặt trong bean riêng

Khi chính sách có nhiều điều kiện (tenant, trạng thái tài liệu, ACL, nhóm, quyền chia sẻ), đẩy logic sang một bean để dễ kiểm thử:

```java
@Component("documentAccess")
public class DocumentAccess {
    public boolean canRead(Authentication auth, Document doc) {
        if (auth == null || doc == null) {
            return false;
        }
        boolean admin = auth.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
        return admin || doc.getOwner().equals(auth.getName());
    }
}
```

```java
@PreAuthorize("isAuthenticated()")
@PostFilter("@documentAccess.canRead(authentication, filterObject)")
public List<Document> findVisibleDocuments() {
    return loadDocumentsAsMutableList();
}
```

Hai đoạn trên là **mẫu tích hợp** (cần imports Spring Security, bean/service và hàm truy vấn của ứng dụng). Logic `canRead` minh họa ownership/admin; nếu hệ thống có nhiều tenant, cần **kiểm tra tenant trước khi xét ownership hoặc role admin tùy chính sách**, tránh vô tình cho admin của một tenant thấy dữ liệu tenant khác. Với chính sách dựa trên ACL, có thể dùng `hasPermission(filterObject, 'read')` sau khi đã cấu hình `PermissionEvaluator` phù hợp; Spring Security không tự biết ACL nghiệp vụ của từng `Document`.

### 4.4. Lọc Map, mảng và Stream

Spring Security hỗ trợ lọc **collection, array, map và stream** (stream phải còn mở). Ý nghĩa của `filterObject` thay đổi theo kiểu:

| Giá trị trả về | `filterObject` trong biểu thức | Ví dụ điều kiện |
|---|---|---|
| `List<Document>` / `Collection<Document>` | Một `Document` | `filterObject.owner == authentication.name` |
| `Document[]` | Một `Document` | `filterObject.owner == authentication.name` |
| `Map<String, Document>` | Một `Map.Entry` | `filterObject.value.owner == authentication.name` |
| `Stream<Document>` | Một `Document` | `filterObject.owner == authentication.name` |

Ví dụ với Map:

```java
@PostFilter("filterObject.value.owner == authentication.name")
public Map<String, Document> findByCode() {
    Map<String, Document> results = new LinkedHashMap<>();
    results.put("d1", new Document(1L, "alice"));
    results.put("d2", new Document(2L, "bob"));
    return results;
}
```

Đoạn trên đặt trong Spring-managed service, cần import `java.util.Map`, `java.util.LinkedHashMap` và `@PostFilter`. Với `alice`, chỉ entry `d1` được giữ. Map phải hỗ trợ xóa entry trong quá trình lọc; với stream, cần chú ý thời điểm tiêu thụ stream, vòng đời tài nguyên và `SecurityContext`. Đừng giả định kiểu bất kỳ triển khai `Iterable` (ví dụ `Page<T>`) đều được `@PostFilter` hỗ trợ như một `Collection`.

## 5. Giới hạn, hiệu năng và ranh giới bảo mật

**Lọc trong bộ nhớ sau truy vấn.** `@PostFilter` không tự thêm điều kiện `WHERE` vào SQL và không biến truy vấn database thành truy vấn phân quyền. Nếu service tải 100.000 hàng rồi trả về 5 hàng, chi phí đọc/chuyển đối tượng/kiểm tra quyền đã phát sinh cho số hàng ban đầu. Khi lượng dữ liệu lớn, hãy đưa điều kiện quyền/tenant vào repository query hoặc chính sách bảo mật tại tầng dữ liệu, rồi có thể dùng `@PostFilter` như một lớp kiểm tra bổ sung.

**Phân trang phải tính quyền trước khi phân trang.** Nếu repository trả về 20 phần tử rồi `@PostFilter` loại 15, trang còn 5 phần tử dù những trang sau có thể có nhiều mục hợp lệ. Các thông tin `totalElements`, `hasNext` cũng có thể sai về mặt quyền người dùng. Ưu tiên lọc trong truy vấn trước `LIMIT/OFFSET` hoặc cursor pagination; không coi `Page<T>` là kiểu được hậu lọc tự động.

**Tập trả về cần cho phép xóa phần tử.** Bộ lọc collection có thể xóa các phần tử không hợp lệ bằng iterator. `List.of(...)`, `List.copyOf(...)` và kết quả `stream.toList()` thường là **unmodifiable**; chúng có thể gây `UnsupportedOperationException` khi bộ lọc cần loại phần tử. Trả về một `ArrayList` độc lập như ví dụ. Đồng thời tránh trả về trực tiếp collection do cache chia sẻ, collection có quan hệ ORM được quản lý, hoặc dữ liệu mà thao tác lọc sẽ làm biến đổi trạng thái hệ thống.

**Không ngăn được tác dụng phụ trước hậu kiểm.** `@PostFilter` chạy sau method, vì vậy không dùng nó để bảo vệ hành vi ghi/xóa/cập nhật hoặc ngăn truy vấn nhạy cảm đã xảy ra. Dùng `@PreAuthorize` hoặc kiểm tra quyền trước tác vụ có tác dụng phụ. Log, message, cache và sự kiện đã phát ra từ service không được `@PostFilter` “thu hồi”.

**Chi phí kiểm tra theo phần tử.** Mỗi phần tử gọi lại biểu thức. Nếu biểu thức gọi ACL service hoặc database để kiểm tra quyền từng phần tử, rất dễ tạo mẫu truy vấn **N+1**. Có thể tối ưu bằng truy vấn phân quyền theo lô, projection hoặc filter tại repository.

**Chú ý dữ liệu null và thuộc tính.** Nếu collection chứa `null` mà biểu thức truy cập `filterObject.owner`, có thể xảy ra lỗi SpEL. Dọn dữ liệu đầu vào, hoặc dùng biểu thức phòng vệ:

```java
@PostFilter("filterObject != null and filterObject.owner == authentication.name")
```

Phải xác định rõ thuộc tính SpEL thực sự truy cập được (JavaBean getter, method hợp lệ) và không giả định rằng tên field private luôn được resolve ở mọi kiểu đối tượng.

**Ranh giới proxy.** Method Security mặc định dựa trên Spring AOP proxy. Lời gọi từ một bean khác thông qua proxy được áp dụng interceptor; lời gọi `this.findAll()` từ chính class đó có thể **bỏ qua annotation** (self-invocation). Phương thức `private`, `final` hoặc class không được Spring quản lý cũng có thể làm advice không áp dụng. Đặt quy tắc ở service bean có thể proxy, gọi qua Spring-injected bean và kiểm thử trực tiếp trên bean do Spring cung cấp.

**Không thay thế kiểm tra truy cập mọi nơi.** Nếu một endpoint khác, scheduled job hoặc repository path có thể lấy dữ liệu không qua service được bảo vệ, `@PostFilter` tại service này không bảo vệ đường đi đó. Đặt ranh giới phân quyền ở nơi các caller bắt buộc phải đi qua; bảo vệ truy cập trực tiếp theo ID bằng `@PostAuthorize`/kiểm tra quyền tương ứng, tránh lỗi IDOR.

## 6. So sánh ngắn các annotation liên quan

| Annotation | Khi nào kiểm tra? | Đối tượng kiểm tra | Hành vi điển hình |
|---|---|---|---|
| `@PreAuthorize` | Trước khi gọi method | Toàn bộ lời gọi | Chặn nếu điều kiện sai |
| `@PostAuthorize` | Sau khi method trả về | Kết quả lời gọi, thường một object | Từ chối trả kết quả nếu điều kiện sai |
| `@PreFilter` | Trước khi method xử lý | Từng phần tử đầu vào collection/array/map/stream | Loại đầu vào không hợp lệ |
| **`@PostFilter`** | **Sau khi method xử lý** | **Từng phần tử kết quả** | **Loại phần tử không hợp lệ** |

Ví dụ `@PostAuthorize("returnObject.owner == authentication.name")` dành cho một `Document` trả về; `returnObject` là **giá trị trả về tổng thể**. Trong `@PostFilter`, dùng `filterObject` để nói về **phần tử riêng lẻ**; thay nhầm `filterObject` bằng `returnObject` thường dẫn đến kiểm tra sai đối tượng hoặc biểu thức không hợp lệ.

## 7. Checklist áp dụng và kiểm thử

1. Đã bật `@EnableMethodSecurity` và annotation đặt trên Spring-managed service bean.
2. Chính sách đọc từng phần tử rõ ràng: ownership, tenant, authority, nhóm hoặc ACL; kiểm tra theo nguyên tắc ít quyền nhất.
3. Nếu cần quyền truy cập chung, đặt `@PreAuthorize` trước khi method thực thi.
4. Kiểu dữ liệu trả về được Spring Security hỗ trợ; collection/map không bị khóa sửa khi cần loại phần tử; không dùng collection chia sẻ dễ bị biến đổi.
5. Có test ít nhất ba tình huống: user có một số phần tử hợp lệ, user không có phần tử hợp lệ, và user có quyền đặc biệt nếu nghiệp vụ cho phép.
6. Kiểm thử qua bean được Spring proxy (chẳng hạn `@SpringBootTest` + `@WithMockUser`), không bỏ qua interceptor do self-invocation.
7. Với dữ liệu lớn hoặc phân trang, lọc quyền ngay trong truy vấn; tránh N+1 khi gọi permission service.
8. Kiểm tra các đường truy cập khác (detail by ID, export, background job, cache, event) để không rò dữ liệu ngoài luồng được lọc.

## 8. Ghi nhớ

`@PostFilter` giúp viết chính sách **“trả về chỉ những phần tử mà người dùng có quyền xem”** ngay tại ranh giới method. Nó phù hợp với danh sách kết quả nhỏ/vừa, khi cần một quy tắc ủy quyền theo từng đối tượng dễ đọc và kiểm thử. Với dữ liệu lớn, phân trang hoặc phân tách tenant nghiêm ngặt, hãy thiết kế truy vấn có điều kiện quyền ngay từ nguồn và dùng Method Security như lớp bảo vệ bổ sung.

**Tài liệu chính thức:** [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html), mục “Filtering Method Results with @PostFilter”.