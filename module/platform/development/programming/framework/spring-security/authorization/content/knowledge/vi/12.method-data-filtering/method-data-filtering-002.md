# filterObject, filterTarget và lựa chọn tham số cần lọc

## Mục tiêu học tập

Sau bài này, bạn có thể: (1) giải thích `filterObject` trong biểu thức lọc của Spring Security Method Security; (2) phân biệt `filterTarget` với một biến SpEL; (3) chọn đúng tham số khi phương thức nhận nhiều danh sách; (4) kiểm tra kết quả của `@PreFilter` và `@PostFilter`; (5) nhận ra những tình huống lọc phần tử không thay thế được kiểm tra quyền cho cả thao tác.

**Phạm vi:** Spring Security Method Security trên Spring-managed bean, minh họa với Java 17+ và Spring Boot 3 / Spring Security 6. Nội dung tập trung vào lọc phần tử ở ranh giới phương thức, không phải bộ lọc HTTP (`SecurityFilterChain`) hay lọc truy vấn cơ sở dữ liệu.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Nó là gì? | Dùng ở đâu? | Ví dụ |
| --- | --- | --- | --- |
| `filterObject` | Tên biến đặc biệt trong ngữ cảnh đánh giá SpEL, lần lượt trỏ đến **một phần tử hiện tại** của tập được lọc. | Biểu thức của `@PreFilter` và `@PostFilter`. | `filterObject.owner == authentication.name` |
| `filterTarget` | **Thuộc tính của annotation `@PreFilter`**, chứa tên tham số đầu vào cần lọc. | Khi chọn tham số cho `@PreFilter`, đặc biệt nếu có nhiều đối số có thể lọc. | `@PreFilter(value = "...", filterTarget = "documents")` |
| Tên tham số phương thức | Tên hoặc bí danh được Spring Security phát hiện, dùng để xác định đúng đối số thực tế. | Khai báo phương thức và ánh xạ tham số. | `@P("documents") List<Document> documents` |

Ví dụ:

```java
@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "documents"
)
public void process(@P("documents") List<Document> documents,
                    List<String> labels) {
    // Chỉ documents là tập cần lọc; labels không bị lọc.
}
```

Trong đoạn này, `documents` chỉ **tập đầu vào**; `filterObject` lần lượt là từng `Document` trong tập ấy. Chuỗi `"documents"` là tên tham số, **không phải** biểu thức `#documents`, tên field của `Document`, hoặc một phần tử cụ thể. Không khai báo tham số có tên `filterObject` để “kích hoạt” biến này: Spring Security tự cung cấp nó trong lúc lọc.

## 2. Spring Security lọc lúc nào?

Bật method security bằng `@EnableMethodSecurity` trên cấu hình Spring. Annotation này kích hoạt các cơ chế `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` mặc định; riêng dependency Spring Security không tự làm method security có hiệu lực.

Một lời gọi đi **qua Spring proxy** thường có luồng khái niệm:

1. Caller gọi phương thức trên bean do Spring quản lý.
2. Với `@PreFilter`, interceptor lấy tham số đích và đánh giá biểu thức **cho từng phần tử trước khi vào thân phương thức**.
3. Biểu thức trả về `true` thì giữ phần tử; `false` thì loại phần tử khỏi tập đi vào phương thức.
4. Phương thức thực hiện công việc với đầu vào đã lọc.
5. Với `@PostFilter`, interceptor đánh giá từng phần tử **trong giá trị trả về** và chỉ đưa những phần tử phù hợp về caller.

| Annotation | Dữ liệu bị lọc | Thời điểm | Có `filterTarget`? |
| --- | --- | --- | --- |
| `@PreFilter` | Một đối số đầu vào dạng tập hợp/tập phần tử được hỗ trợ | Trước thân phương thức | **Có** |
| `@PostFilter` | Giá trị trả về dạng tập hợp/tập phần tử được hỗ trợ | Sau thân phương thức | **Không** |
| `@PreAuthorize` | Quyết định có cho gọi cả phương thức hay không | Trước thân phương thức | Không |
| `@PostAuthorize` | Quyết định có cho trả kết quả phương thức hay không | Sau thân phương thức | Không |

**Quan trọng:** Một phần tử bị `@PreFilter` loại đi thường **không** tạo ra `AccessDeniedException`; phương thức có thể vẫn chạy với danh sách rỗng. Nếu nghiệp vụ đòi hỏi “có một phần tử trái quyền thì từ chối toàn bộ yêu cầu”, hãy dùng kiểm tra quyền/validation riêng cho cả thao tác, chẳng hạn `@PreAuthorize` gọi bean kiểm tra danh sách.

## 3. Chọn đúng tham số cho `@PreFilter`

### 3.1. Một tập đầu vào rõ ràng: có thể bỏ `filterTarget`

```java
@PreFilter("filterObject.owner == authentication.name")
public void save(List<Document> documents) {
    // documents chỉ còn các phần tử đạt điều kiện.
}
```

Khi chỉ có một đối số ứng viên thích hợp, Spring Security có thể suy ra đích lọc. Nếu một phương thức có nhiều tham số nhưng chỉ một tham số là tập có thể lọc, vẫn nên ghi rõ `filterTarget` khi việc đó giúp hợp đồng phương thức dễ đọc và không phụ thuộc vào suy luận.

### 3.2. Nhiều tập đầu vào: chỉ định `filterTarget`

```java
@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "pending"
)
public void merge(@P("pending") List<Document> pending,
                  @P("existing") List<Document> existing) {
    // pending được lọc theo owner; existing vẫn nguyên.
}
```

Không khai báo `filterTarget` khi có nhiều đối số ứng viên có thể khiến Spring Security không xác định được đích và báo lỗi trong lúc gọi. `filterTarget = "pending"` chọn **một** đối số; nó không có nghĩa lọc cả `pending` và `existing`. Nếu hai tập cần quy tắc khác nhau, thực hiện kiểm tra/lọc riêng có chủ đích, đừng coi một `@PreFilter` là bộ lọc tự động cho mọi tham số.

### 3.3. Tên tham số phải được phát hiện đúng

Khi Java không giữ tên tham số trong bytecode, `filterTarget = "pending"` có thể không ánh xạ tới tham số cần lọc. Các cách ổn định:

- Đánh dấu tham số bằng `@P("pending")` từ `org.springframework.security.access.method.P` (như ví dụ). Bí danh dùng trong annotation và `@P` phải khớp chính xác.
- Biên dịch Java với cờ `-parameters` để giữ tên tham số trong bytecode, ví dụ Gradle: `tasks.withType(JavaCompile).configureEach { options.compilerArgs += '-parameters' }`. Khi đó có thể dùng tên khai báo `pending` mà không cần `@P`, nếu cơ chế phát hiện tên của dự án sử dụng được.
- Với môi trường tương ứng, Spring Security còn hỗ trợ tên từ một số annotation như Spring Data `@Param`; chỉ dùng khi thực sự thuộc hợp đồng của dự án.

Phân biệt ba cú pháp:

```java
filterTarget = "pending"         // ĐÚNG: tên đích, là chuỗi thuộc tính annotation.
filterTarget = "#pending"        // SAI: không dùng tiền tố # ở đây.
value = "filterObject.owner == authentication.name" // Biểu thức cho MỖI phần tử.
```

Cú pháp `#pending` có thể xuất hiện **trong biểu thức SpEL** khi bạn muốn tham chiếu một biến tham số được phát hiện, nhưng không phải giá trị hợp lệ để chọn đích `filterTarget`.

### 3.4. Chọn theo ý nghĩa nghiệp vụ

Giả sử API nhận `documents` (danh sách tài liệu sẽ xử lý), `watchers` (người nhận thông báo) và `options` (cấu hình). Chỉ chọn tham số chứa **các phần tử bạn chủ ý cho phép/bỏ qua theo quyền**. Không chọn danh sách vì nó đứng đầu hay vì cùng là `List`. Nếu lọc `documents` nhưng hành động phụ vẫn dùng `watchers`, kiểm tra riêng việc gửi thông báo để tránh rò rỉ dữ liệu qua tác dụng phụ.

## 4. Viết điều kiện với `filterObject`

Mỗi lần đánh giá, `filterObject` là một phần tử; các biến bảo mật như `authentication` cung cấp thông tin người đang đăng nhập.

```java
@PreFilter("filterObject.owner == authentication.name")
public void update(List<Document> documents) { /* ... */ }

@PostFilter("filterObject.owner == authentication.name")
public List<Document> findAll() { /* ... */ }
```

Ở đây `owner` được Spring Expression Language truy cập như thuộc tính JavaBean (ví dụ qua `getOwner()`). Nếu danh sách có phần tử `null`, biểu thức truy cập thuộc tính trực tiếp có thể lỗi; một điều kiện phòng vệ là `filterObject != null and filterObject.owner == authentication.name`.

Điều kiện có thể dùng các phép toán SpEL như `and`, `or`, `==`, hoặc gọi bean ủy quyền kiểm tra quyền:

```java
@PreFilter("@documentPolicy.canEdit(authentication, filterObject)")
public void update(List<Document> documents) { /* ... */ }
```

`documentPolicy` ở đây là **bean ứng dụng phải tự cung cấp** (mã trên chỉ minh họa cách gọi bean, không phải ví dụ chạy độc lập). Dùng bean khi luật phức tạp, cần tái sử dụng hay kiểm thử độc lập. Không tin một trường `owner` do client tự gửi nếu đó không phải dữ liệu sở hữu đáng tin: đối chiếu quyền với dữ liệu phía server khi cần.

Với `Map<K,V>`, tài liệu Spring Security mô tả `filterObject` là một `Map.Entry`: có thể viết `filterObject.key` hoặc `filterObject.value.owner`, tùy đối tượng nào cần kiểm tra. Đối với `@PostFilter`, tập được duyệt là **kết quả trả về**, nên `filterObject` ở đó không tự động là phần tử của một tham số đầu vào.

## 5. Ví dụ Java 17+ chạy trong Spring Boot

Chuẩn bị dự án Spring Boot 3.x có hai dependency `spring-boot-starter` và `spring-boot-starter-security` (đồng thời có plugin Boot để chạy `bootRun`). Đặt **toàn bộ** mã dưới đây vào `src/main/java/demo/FilteringDemoApplication.java`. Các class không `public` ở cuối cùng nằm chung tệp để ví dụ tự đủ. Truy cập bean `DocumentService` qua Spring injection giúp interceptor hoạt động.

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableMethodSecurity
public class FilteringDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilteringDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(DocumentService service) {
        return args -> {
            var auth = new UsernamePasswordAuthenticationToken(
                "alice", "n/a", List.of(new SimpleGrantedAuthority("ROLE_USER")));
            SecurityContextHolder.getContext().setAuthentication(auth);

            try {
                var documents = new ArrayList<>(List.of(
                    new Document("A", "alice"),
                    new Document("B", "bob"),
                    new Document("C", "alice")
                ));
                var labels = new ArrayList<>(List.of("draft", "urgent"));

                System.out.println("Before: " + documents);
                System.out.println("Accepted: " + service.accept(documents, labels));
                System.out.println("Input after: " + documents);
                System.out.println("Labels: " + labels);
                System.out.println("Visible: " + service.readAll());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }
}

@Service
class DocumentService {
    @PreFilter(
        value = "filterObject.owner == authentication.name",
        filterTarget = "documents"
    )
    public List<String> accept(@P("documents") List<Document> documents,
                               List<String> labels) {
        // Bên trong method: documents đã được lọc; labels không bị thay đổi.
        return documents.stream().map(Document::getId).toList();
    }

    @PostFilter("filterObject.owner == authentication.name")
    public List<Document> readAll() {
        return new ArrayList<>(List.of(
            new Document("A", "alice"),
            new Document("B", "bob"),
            new Document("C", "alice")
        ));
    }
}

final class Document {
    private final String id;
    private final String owner;

    Document(String id, String owner) {
        this.id = id;
        this.owner = owner;
    }

    public String getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }

    @Override
    public String toString() {
        return id;
    }
}
```

Trong dự án Gradle Spring Boot đã cấu hình, chạy:

```bash
./gradlew bootRun
```

Các dòng do `System.out.println` trong ví dụ in ra (ngoài log khởi động của Spring Boot):

```text
Before: [A, B, C]
Accepted: [A, C]
Input after: [A, C]
Labels: [draft, urgent]
Visible: [A, C]
```

**Giải thích từng bước:** `authentication.name` là `alice`. `@PreFilter` duyệt ba `Document`: A giữ, B bị loại vì `owner = bob`, C giữ. Phương thức `accept` nhìn thấy A và C; `labels` không phải `filterTarget` nên vẫn là `[draft, urgent]`. Ở ví dụ dùng `ArrayList` có thể sửa đổi, tập `documents` ban đầu cũng còn A và C sau khi lọc. `readAll` tạo ba bản ghi, nhưng `@PostFilter` chỉ cho caller thấy A và C.

Ví dụ cố ý đặt `@P("documents")` để việc xác định đích không phụ thuộc vào thiết lập `-parameters`. Token đăng nhập được tạo trong `ApplicationRunner` **chỉ để minh họa**; trong ứng dụng thật, `Authentication` phải đến từ luồng xác thực đáng tin cậy của Spring Security.

## 6. Kiểu dữ liệu và tác động lên bộ sưu tập

Tài liệu Method Security của Spring Security 6.5 mô tả hỗ trợ lọc `Collection`, array, `Map` và `Stream` (stream phải còn khả dụng); chi tiết thao tác nội bộ và lỗi đối với từng kiểu nên được kiểm chứng trên đúng phiên bản thư viện đang dùng. Khi mới học, chọn `ArrayList` có thể sửa đổi để thấy rõ sự khác nhau giữa **lọc đầu vào** và **lọc kết quả**.

- **Mutable vs immutable:** `List.of(...)` hoặc `Collections.unmodifiableList(...)` không cho xóa phần tử. Với `@PreFilter` trên `Collection`, nếu cơ chế lọc cần thao tác xóa, tập bất biến có thể gây `UnsupportedOperationException`. Tạo bản sao `new ArrayList<>(input)` tại ranh giới thích hợp.
- **Array:** array có kích thước cố định; không suy luận rằng nó sẽ bị xóa tại chỗ giống `ArrayList`. Kiểm tra hành vi thực tế theo phiên bản và kiểu chữ ký.
- **Map:** biểu thức nhắm đến `Map.Entry` và dùng `filterObject.value` để truy cập đối tượng giá trị.
- **Stream:** tránh stream đã tiêu thụ/đóng, và lưu ý thời điểm đánh giá/lazy execution trong kiểm thử.
- **Null:** đối số đích `null` không phải “danh sách rỗng”; xử lý/chuẩn hóa trước lời gọi nếu hợp đồng cho phép.

Các quy tắc này đặc biệt quan trọng với các API nhận đối tượng từ controller, danh sách được cache hoặc tập immutable do thư viện trả về.

## 7. Lựa chọn đúng cơ chế theo mục tiêu

| Yêu cầu nghiệp vụ | Công cụ thường phù hợp | Lý do |
| --- | --- | --- |
| Chỉ chuyển các phần tử hợp lệ đến service, cho phép bỏ qua phần tử khác | `@PreFilter` | Lọc trước khi xử lý. |
| Chỉ trả về những phần tử người gọi được xem | `@PostFilter` hoặc lọc tại query | Lọc tập kết quả; với dữ liệu lớn ưu tiên query có ràng buộc quyền. |
| Một phần tử sai quyền thì hủy toàn bộ thao tác | `@PreAuthorize`, policy/validation cho cả danh sách | Lọc im lặng có thể phá vỡ tính nguyên tử hoặc che giấu lỗi đầu vào. |
| Một id/đối tượng đơn cần kiểm tra quyền | `@PreAuthorize` / `@PostAuthorize` / policy | `filterObject` dành cho lọc từng phần tử của tập; không phải biến cho đối số scalar bất kỳ. |
| Nhiều tập đầu vào, chỉ một tập cần lọc | `@PreFilter(filterTarget = "...")` | Xác định đích theo tên tham số, không phụ thuộc thứ tự. |

`@PostFilter` lọc **sau** khi code đọc dữ liệu, nên không thay thế được truy vấn có giới hạn tenant/owner ở database. Phân trang sau khi lọc trong bộ nhớ dễ làm sai tổng số phần tử và số trang. Nếu biểu thức gọi database hoặc remote service cho mỗi phần tử, cần tránh chi phí N+1. Với quyền nhạy cảm hoặc cập nhật dữ liệu, đặt ràng buộc tại nguồn dữ liệu và service để bảo vệ cả những đường gọi không đi qua endpoint dự kiến.

## 8. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `filterObject` không tồn tại ở chỗ khác | Nó chỉ được cung cấp trong ngữ cảnh lọc mỗi phần tử. | Dùng trong biểu thức `@PreFilter`/`@PostFilter`, không coi là biến Java toàn cục. |
| Không rõ phải lọc `List` nào | Nhiều đối số có thể lọc nhưng chưa chỉ định đích. | Thêm `filterTarget` và kiểm chứng đúng tên. |
| `filterTarget` không tìm thấy tham số | Tên bytecode không có, bí danh sai, viết `#documents` hoặc sai hoa/thường. | Dùng `@P` hoặc `-parameters`; tên phải khớp chính xác. |
| Biểu thức `owner` báo lỗi | Phần tử `null`, không có getter hợp lệ hoặc kiểu phần tử khác dự kiến. | Kiểm tra kiểu thực, JavaBean getter và null guard. |
| Lỗi khi lọc `List.of` | Tập không hỗ trợ xóa phần tử. | Dùng bản sao mutable trước khi gọi. |
| Gọi phương thức nhưng không hề lọc | Thiếu `@EnableMethodSecurity`, method không đi qua Spring proxy hoặc self-invocation. | Gọi từ một bean khác qua bean được Spring injection; kiểm tra cấu hình và test integration. |
| Danh sách trả về đúng nhưng vẫn rò rỉ | Service đã chạy tác dụng phụ/đọc quá nhiều dữ liệu trước `@PostFilter`. | Chặn thao tác từ trước và ràng buộc query theo quyền. |
| Mong đợi lỗi 403 nhưng nhận danh sách rỗng | `@PreFilter`/`@PostFilter` loại phần tử, không phải cơ chế từ chối cả lời gọi. | Dùng authorization cho cả request khi cần fail-closed. |

**Lưu ý proxy:** một lời gọi `this.accept(...)` từ phương thức khác trong cùng bean thường không qua proxy của Spring AOP, nên annotation trên `accept` có thể bị bỏ qua. Kiểm thử bằng cách gọi qua bean được Spring quản lý; không chỉ gọi trực tiếp đối tượng tạo với `new`.

## 9. Checklist kiểm thử cho bài này

Với service ở ví dụ trên, nên có các tình huống kiểm thử integration bằng `@SpringBootTest` kết hợp `spring-security-test`/`@WithMockUser` (nếu thêm dependency test):

1. **Người dùng alice, dữ liệu A/alice, B/bob, C/alice:** phần được giữ là A và C; danh sách `labels` không đổi.
2. **Người dùng bob:** chỉ B được giữ, kiểm tra cả `@PreFilter` và `@PostFilter`.
3. **Không có phần tử phù hợp:** kết quả là tập rỗng, xác nhận nghiệp vụ có chấp nhận xử lý một batch rỗng không.
4. **Hai tham số `List`:** đổi thứ tự tham số hoặc thêm tham số mới vẫn chỉ lọc đúng tên khai báo trong `filterTarget`.
5. **Đối số immutable/null:** xác định chính xác cơ chế xử lý lỗi và chuẩn hóa đầu vào; không mặc định mọi kiểu collection đều sửa được.
6. **Gọi nội bộ cùng bean và gọi qua bean proxy:** xác minh method security thực sự được kích hoạt trên đường chạy production.

Bài tập: thêm tham số `@P("reviewers") List<Document> reviewers` vào phương thức `accept`. Vẫn giữ `filterTarget = "documents"`, kiểm tra `reviewers` không đổi. Sau đó đổi đích thành `"reviewers"` và quan sát tập nào bị lọc. Cuối cùng, thử trường hợp toàn bộ `documents` đều có owner khác người dùng, rồi quyết định xem nghiệp vụ cần trả danh sách rỗng hay phải từ chối toàn bộ thao tác.

## 10. Ghi nhớ

- `filterObject` = **phần tử đang được kiểm tra**, tồn tại trong biểu thức lọc.
- `filterTarget` = **tên tham số đầu vào được chọn** cho `@PreFilter`.
- `@PreFilter` lọc **trước**, `@PostFilter` lọc **sau** và **không có** `filterTarget`.
- Khi có nhiều tập, ghi `filterTarget` rõ ràng; để tên ổn định, dùng `@P` hoặc build với `-parameters`.
- Lọc phần tử không thay thế kiểm tra quyền cho cả hành động, truy vấn giới hạn dữ liệu, hay kiểm thử qua Spring proxy.

## Tài liệu tham khảo

- Spring Security Reference, Method Security (gồm `@PreFilter`, `@PostFilter`, tham số và proxy): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security API, annotation `@PreFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PreFilter.html
