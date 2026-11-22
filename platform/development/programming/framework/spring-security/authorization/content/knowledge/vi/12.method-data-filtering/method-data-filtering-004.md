# Collection, array, map, stream và khả năng hỗ trợ theo phiên bản

> Chủ đề: Spring Security – authorization. Nhánh kiến thức: **Lọc dữ liệu phương thức**. Ví dụ dùng Java 17+ và cơ chế Method Security của Spring Security. Nội dung phân biệt khả năng mà tài liệu công bố với điều kiện vận hành thực tế của từng phiên bản.

## 1. Bài toán và mô hình hoạt động

Giả sử phương thức nhận hoặc trả về ba tài liệu: A thuộc về `alice`, B thuộc về `bob`, C thuộc về `alice`. Khi `alice` gọi phương thức, yêu cầu nghiệp vụ là chỉ A và C được đi qua ranh giới tương ứng. Trong Spring Security, hai annotation dùng để lọc **từng phần tử** là:

- **`@PreFilter`**: đánh giá biểu thức trước khi phương thức chạy, nhằm loại phần tử không thỏa điều kiện khỏi **tham số đầu vào được chọn**.
- **`@PostFilter`**: đánh giá biểu thức sau khi phương thức tạo kết quả, nhằm loại phần tử không thỏa điều kiện khỏi **giá trị trả về**.

Biểu thức sử dụng Spring Expression Language (SpEL). Biến `filterObject` biểu thị phần tử đang xét; `authentication.name` là tên của người dùng đang xác thực. Ví dụ `filterObject.owner == authentication.name` giữ lại đối tượng có thuộc tính `owner` bằng tên người dùng. Với `Map`, `filterObject` là một mục `Map.Entry`, vì vậy cần truy cập `filterObject.value.owner` (hoặc `filterObject.key` nếu chính khóa là điều kiện).

Luồng xử lý điển hình:

~~~text
Caller -> Spring AOP proxy
       -> @PreFilter (lọc đối số, nếu có)
       -> phương thức nghiệp vụ
       -> @PostFilter (lọc kết quả, nếu có)
       -> Caller nhận kết quả đã lọc
~~~

Đây là **lọc phần tử**, không phải phép kiểm tra cho phép/từ chối toàn bộ lời gọi: `@PreAuthorize` và `@PostAuthorize` dùng cho quyết định ủy quyền theo điều kiện; `@PreFilter` và `@PostFilter` điều chỉnh tập phần tử. Chúng có thể kết hợp với nhau khi cả kiểm soát lời gọi lẫn giới hạn dữ liệu đều cần thiết. `@PostFilter` không ngăn phương thức đọc dữ liệu nhạy cảm trước khi kết quả bị lọc.

## 2. Bật Method Security đúng cách

Trong ứng dụng Spring Boot dùng Spring Security 6.x hoặc 7.x, thêm `@EnableMethodSecurity` vào một lớp cấu hình. Annotation này bật xử lý pre/post mặc định. Chỉ thêm `spring-boot-starter-security` chưa tự kích hoạt bảo mật ở cấp phương thức.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Điều kiện cần: phương thức được gọi **qua Spring bean/proxy**. Nếu dùng `new MyService()`, gọi nội bộ từ phương thức khác cùng đối tượng (`this.read()`), hoặc đặt điểm chặn ở phương thức không được proxy áp dụng, annotation có thể không chạy. Viết kiểm thử gọi bean lấy từ Spring Context; không chỉ kiểm thử đối tượng tự tạo.

Với dự án cũ dùng `@EnableGlobalMethodSecurity(prePostEnabled = true)`, cần xem xét chuyển sang `@EnableMethodSecurity`. Hai cơ chế có thể dùng đường đi interceptor khác nhau; đừng suy luận hành vi của bản cũ chỉ từ mã ví dụ dành cho bản mới.

## 3. Collection, array, map, stream khác nhau ở đâu?

| Kiểu dữ liệu | `filterObject` đại diện cho | Cách lọc và điều phải nhớ |
| --- | --- | --- |
| `Collection<T>`, `List<T>`, `Set<T>` | Một `T` | Với bộ sưu tập có thể sửa, nhiều phiên bản lọc bằng cách thay đổi chính bộ sưu tập (`clear` rồi thêm lại). Dùng `ArrayList`/`LinkedHashSet` có thể sửa cho `@PreFilter`. |
| `T[]`, bao gồm tham số varargs `T...` | Một phần tử `T` | Bộ xử lý biểu thức tạo **mảng mới** sau lọc. `@PostFilter` trên mảng đối tượng là hướng rõ ràng; `@PreFilter` trên mảng có khác biệt giữa tài liệu và đường đi interceptor, nên phải kiểm thử đúng bản chạy. Không mặc định áp dụng cho mảng nguyên thủy `int[]`. |
| `Map<K,V>` | Một `Map.Entry<K,V>` | So sánh thuộc tính giá trị qua `filterObject.value.owner`; khóa qua `filterObject.key`. Có thể sửa/giữ lại các cặp khóa–giá trị. Với `@PreFilter`, chuyển thành bản sao `LinkedHashMap` có thể sửa trước khi truyền vào. |
| `Stream<T>` | Một `T` khi luồng được tiêu thụ | Phép lọc là **lazy**: việc đánh giá có thể diễn ra lúc có terminal operation như `toList()`, không nhất thiết tại thời điểm trả về phương thức. Chỉ sử dụng stream còn mở, chưa tiêu thụ và cần quản lý đóng tài nguyên. |

**Sự khác biệt quan trọng:** “bộ xử lý biểu thức hỗ trợ một kiểu” không đồng nghĩa mọi đường đi `@PreFilter` đều thay được tham số bằng giá trị mới. Với `Collection`/`Map` không thể sửa, mảng hoặc `Stream`, cần kiểm tra chính interceptor của phiên bản đang dùng. Ưu tiên **`List` có thể sửa** cho đầu vào `@PreFilter`; ưu tiên kết quả `List`/`Map` mới được tạo và có thể sửa cho `@PostFilter` khi cần khả năng tương thích rộng.

### 3.1. Collection: tham chiếu và khả năng thay đổi

~~~java
@PreFilter("filterObject.owner == authentication.name")
public void process(List<Doc> docs) {
    // docs chỉ nên chứa các phần tử được phép
}

@PostFilter("filterObject.owner == authentication.name")
public List<Doc> findDocs() {
    return new ArrayList<>(repository.findAll()); // bản sao có thể sửa
}
~~~

Ví dụ này minh họa trong một service Spring; `Doc` có phương thức getter `getOwner()`. Với `@PreFilter` trên danh sách có thể sửa, người gọi có thể quan sát danh sách ban đầu đã bị lọc ngay cả khi phương thức `process` chưa chỉnh sửa nó. Vì vậy, nếu người gọi còn cần toàn bộ đầu vào, hãy tạo `new ArrayList<>(source)` **trước khi gọi qua proxy**.

`List.of(...)`, `List.copyOf(...)`, `Stream.toList()` và `Collections.unmodifiableList(...)` trả về danh sách không cho thay đổi cấu trúc. `Arrays.asList(...)` cho phép thay phần tử nhưng không cho `clear()`. Với `@PreFilter`, dùng những danh sách này có thể gây `UnsupportedOperationException` ở một số bản, hoặc dẫn tới hành vi lọc không tác động lên tham số gốc trong đường đi khác. **Không đưa danh sách bất biến vào phương thức dựa vào `@PreFilter` như một ranh giới bảo mật.**

Với `@PostFilter`, cũng không nên trả về trực tiếp danh sách cache hoặc danh sách dùng chung: nếu bộ lọc sửa tại chỗ, dữ liệu dùng chung có thể bị thay đổi cho những lần gọi tiếp theo. Hãy tạo bản sao trước khi trả về.

### 3.2. Array: vì sao phải phân biệt pre/post

~~~java
@PostFilter("filterObject.owner == authentication.name")
public Doc[] findAsArray() {
    return new Doc[] {new Doc("A", "alice"), new Doc("B", "bob")};
}
~~~

Khi `alice` gọi qua proxy, kỳ vọng kết quả chỉ còn mảng chứa A; mảng mới có độ dài 1. Việc lọc mảng không thể “xóa” phần tử khỏi mảng gốc vì kích thước mảng Java là cố định.

Tài liệu Method Security 6.5/7.x liệt kê `T[]` và cả varargs trong những dạng lọc được, nhưng Javadoc `@PreFilter` ở một số bản vẫn ghi không hỗ trợ mảng. Một số đường đi interceptor trước lời gọi có giới hạn khi xác định hoặc thay tham số dạng mảng. Vì vậy:

- **`@PostFilter` với `T[]`:** dùng khi đã kiểm thử hợp đồng trả về của bản đang chạy.
- **`@PreFilter` với `T[]`:** không dựa riêng vào lời khẳng định chung “arrays supported”. Nếu đầu vào là mảng, chuyển thành `new ArrayList<>(Arrays.asList(input))` tại ranh giới bên ngoài rồi gọi phương thức nhận `List<T>` có thể sửa.
- **`int[]`, `long[]`, ...:** không tự coi là tương đương `Integer[]`/`Long[]`; nhiều bộ xử lý lọc mảng dựa vào `Object[]`.

### 3.3. Map: kiểm tra Entry, không nhầm Key với Value

~~~java
@PostFilter("filterObject.value.owner == authentication.name")
public Map<String, Doc> findAsMap() {
    Map<String, Doc> result = new LinkedHashMap<>();
    result.put("a", new Doc("A", "alice"));
    result.put("b", new Doc("B", "bob"));
    return result;
}
~~~

Đối với `alice`, kết quả chỉ còn khóa `a` và đối tượng A. `filterObject.owner` ở đây không đúng ý định, vì `filterObject` là `Map.Entry`, không phải `Doc`. Nếu quy tắc bảo mật nằm ở khóa, có thể dùng biểu thức như `filterObject.key == authentication.name` khi khóa thật sự là tên chủ sở hữu.

Với `@PreFilter` trên `Map`, đầu vào phải là bản có thể sửa khi dựa vào lọc tại chỗ. Tránh `Map.of(...)` hoặc bản đồ dùng chung. Tính toàn vẹn quan hệ khóa–giá trị được giữ khi lọc theo entry; không lọc riêng `keySet()` rồi ghép lại các giá trị.

### 3.4. Stream: lazy, một lần sử dụng và vòng đời tài nguyên

~~~java
@PostFilter("filterObject.owner == authentication.name")
public Stream<Doc> findAsStream() {
    return Stream.of(new Doc("A", "alice"), new Doc("B", "bob"));
}
~~~

~~~java
try (Stream<Doc> visible = service.findAsStream()) {
    List<Doc> result = visible.toList(); // điểm tiêu thụ và áp dụng lọc
}
~~~

`Stream` chỉ được tiêu thụ một lần. Nếu stream đến từ JDBC/JPA hoặc nguồn giữ tài nguyên, trả stream qua ranh giới transaction/security context cần được xem xét cẩn thận: lúc người gọi duyệt có thể đã ngoài transaction hoặc phạm vi xác thực mong đợi. Không tự dùng `parallel()` cho một biểu thức truy cập trạng thái xác thực và `filterObject`; cần kiểm thử cách context được truyền qua luồng. Với dữ liệu nghiệp vụ, thường dễ kiểm soát hơn khi truy vấn theo quyền và trả một `List` đã materialize trong tầng service.

## 4. Ví dụ hoàn chỉnh có thể chạy trong Spring Boot

Ví dụ dùng Java 17+, Spring Boot đã cấu hình Gradle, `spring-boot-starter-security` và Spring Security Test. Nếu dự án đã có các dependency thì giữ nguyên; để Spring Boot quản lý phiên bản Spring Security tương thích.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Tạo ba tệp trong `src/main/java/demo/filter/` và tệp kiểm thử trong `src/test/java/demo/filter/`.

**`DemoApplication.java`**

~~~java
package demo.filter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**`Doc.java`**

~~~java
package demo.filter;

public final class Doc {
    private final String id;
    private final String owner;

    public Doc(String id, String owner) {
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
~~~

**`DocumentService.java`**

~~~java
package demo.filter;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private Doc a() { return new Doc("A", "alice"); }
    private Doc b() { return new Doc("B", "bob"); }

    // Chỉ dùng danh sách đầu vào có thể sửa.
    @PreFilter("filterObject.owner == authentication.name")
    public List<Doc> accept(List<Doc> docs) {
        return new ArrayList<>(docs);
    }

    @PostFilter("filterObject.owner == authentication.name")
    public List<Doc> asList() {
        return new ArrayList<>(List.of(a(), b()));
    }

    @PostFilter("filterObject.owner == authentication.name")
    public Doc[] asArray() {
        return new Doc[] {a(), b()};
    }

    @PostFilter("filterObject.value.owner == authentication.name")
    public Map<String, Doc> asMap() {
        Map<String, Doc> result = new LinkedHashMap<>();
        result.put("A", a());
        result.put("B", b());
        return result;
    }

    @PostFilter("filterObject.owner == authentication.name")
    public Stream<Doc> asStream() {
        return Stream.of(a(), b());
    }
}
~~~

**`DocumentServiceTest.java`**

~~~java
package demo.filter;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class DocumentServiceTest {
    @Autowired
    DocumentService service;

    @Test
    @WithMockUser(username = "alice")
    void aliceSeesOnlyHerDocuments() {
        List<Doc> input = new ArrayList<>(List.of(
                new Doc("A", "alice"), new Doc("B", "bob")));

        assertEquals(List.of("A"),
                service.accept(input).stream().map(Doc::getId).toList());

        // @PreFilter cũng thay đổi chính danh sách mutable do caller truyền vào.
        assertEquals(List.of("A"), input.stream().map(Doc::getId).toList());

        assertEquals(List.of("A"),
                service.asList().stream().map(Doc::getId).toList());

        assertArrayEquals(new String[] {"A"}, Arrays.stream(service.asArray())
                .map(Doc::getId).toArray(String[]::new));

        assertEquals(List.of("A"), new ArrayList<>(service.asMap().keySet()));

        try (Stream<Doc> stream = service.asStream()) {
            assertEquals(List.of("A"), stream.map(Doc::getId).toList());
        }
    }

    @Test
    @WithMockUser(username = "bob")
    void bobDoesNotSeeAlicesDocuments() {
        assertEquals(List.of("B"),
                service.asList().stream().map(Doc::getId).toList());
    }
}
~~~

Chạy từ thư mục dự án Spring Boot với JDK 17+:

~~~text
./gradlew test --tests demo.filter.DocumentServiceTest
~~~

Trên Windows dùng `gradlew.bat test --tests demo.filter.DocumentServiceTest`. Kết quả kiểm chứng cần đạt: bài kiểm thử của `alice` chỉ nhận ID A cho danh sách, mảng, map và stream; bài kiểm thử của `bob` chỉ nhận B. Mã kiểm thử không in stdout; thành công được thể hiện bằng các assertion đều đạt và tác vụ Gradle `test` thành công. Nếu dependency, cấu hình Gradle hoặc phiên bản dự án khác với giả định, điều chỉnh môi trường trước khi kết luận về tính đúng của tính năng.

Tại đây, `List` đầu vào được cố ý tạo bằng `new ArrayList<>(...)` và danh sách/map đầu ra cũng là các đối tượng mới. Điều này tránh nhầm lẫn do bất biến hoặc dữ liệu dùng chung; đồng thời kiểm thử gọi **bean có proxy**, thay vì khởi tạo `DocumentService` bằng `new`.

## 5. Đa tham số: `filterTarget` phải chỉ rõ đối số

Khi phương thức có nhiều đối số, nên nêu rõ tham số nào cần lọc. Đoạn sau là **minh họa chữ ký riêng**, không phải đoạn cần dán thêm vào `DocumentService` ở trên:

~~~java
@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "docs"
)
public void acceptBatch(List<Doc> docs, String requestId) {
    // Chỉ xử lý docs sau khi được lọc.
}
~~~

Tên `docs` phải được Spring Security phân giải đúng từ metadata tên tham số Java. Bật cờ biên dịch `-parameters` hoặc dùng cách đặt tên tham số mà bản Spring Security hiện hành hỗ trợ (ví dụ `@P("docs")`); nếu không, việc tìm đối số có thể thất bại khi chạy. Chỉ một tham số kiểu lọc được thì thường có thể bỏ `filterTarget`. Khi có nhiều tham số, kiểm thử cả tình huống có dữ liệu trái quyền; đừng chỉ kiểm thử danh sách trống.

## 6. Khả năng hỗ trợ theo phiên bản: đọc cả tài liệu lẫn hành vi thực tế

| Dòng phiên bản | Điều có thể xác nhận | Lưu ý triển khai |
| --- | --- | --- |
| **Spring Security 5.8.x** | Mã nguồn `DefaultMethodSecurityExpressionHandler.filter` đã phân nhánh cho `Collection`, mảng đối tượng, `Map` và `Stream`. | Javadoc `@PreFilter` cùng dòng vẫn mô tả tham số `Collection` có thể sửa và nói không hỗ trợ array. Vì vậy **không được đồng nhất khả năng của handler với bảo đảm của mọi interceptor `@PreFilter`**. |
| **Spring Security 6.5.x** | Tài liệu tham chiếu Method Security nêu `@PreFilter` và `@PostFilter` với array, collection, map, stream (stream còn mở). `@EnableMethodSecurity` là cách bật khuyến nghị. | Kiểm tra tính có thể sửa, vòng đời stream, proxy và thử nghiệm cả pre/post với đúng signature sử dụng. |
| **Spring Security 7.0–7.1.x** | Tài liệu tham chiếu tiếp tục liệt kê bốn họ kiểu dữ liệu. | Cách xử lý collection/map bất biến có thể khác bản cũ; trong một số đường đi, handler trả bản mới nhưng `@PreFilter` không thay tham số gốc. Không dùng đầu vào bất biến làm ranh giới cấp quyền khi chưa kiểm thử hành vi thực. |
| **Các bản cũ hơn hoặc custom expression handler** | Không thể suy ra tương thích đầy đủ từ bảng trên. | Đọc đúng reference/Javadoc/source của phiên bản khóa trong dự án và viết kiểm thử tích hợp cho từng dạng đầu vào/đầu ra. |

**Quy tắc chọn an toàn, áp dụng xuyên phiên bản:**

1. Với đầu vào `@PreFilter`, dùng `List`/`Map` **có thể sửa** và tạo bản sao trước khi chuyển cho service. Nếu nhận mảng/stream từ API, chuyển thành danh sách có thể sửa bên ngoài proxy nếu không có kiểm thử đặc thù cho prefilter của loại đó.
2. Với đầu ra `@PostFilter`, ưu tiên `List` hoặc `Map` mới tạo. `T[]` và `Stream<T>` có thể dùng khi đã xác minh bằng kiểm thử; stream yêu cầu quản lý thời điểm duyệt và đóng.
3. Không dùng `@PostFilter` làm cơ chế duy nhất cho truy vấn nhiều bản ghi, phân trang hay dữ liệu cần bảo vệ ngay từ database. Số phần tử sau lọc cũng không đại diện chính xác cho tổng số bản ghi được phép trong truy vấn phân trang.

Nếu đọc tài liệu thấy xung đột (ví dụ reference 6.5/7.x đưa ví dụ array trong `@PreFilter`, nhưng Javadoc annotation vẫn ghi không hỗ trợ), đây là tín hiệu phải **thử trên đúng bản thư viện và kiểu tham số**, không tự chọn một câu làm bảo đảm tuyệt đối. Giữ test ngăn truy cập trái quyền trong quy trình nâng cấp dependency.

## 7. Lỗi thường gặp và cách nhận biết

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Phương thức nhận cả A và B dù `@PreFilter` tồn tại | Bỏ qua proxy, Method Security chưa bật, hoặc input bất biến/kiểu không được interceptor xử lý như dự kiến | Bật `@EnableMethodSecurity`, gọi bean thật, truyền danh sách có thể sửa, viết test với hai chủ sở hữu |
| `UnsupportedOperationException` khi lọc | Lọc tại chỗ trên `List.of`, `Map.of`, `Arrays.asList` hoặc collection không cho sửa | Dùng bản sao `new ArrayList<>(...)` / `new LinkedHashMap<>(...)` ở đúng ranh giới |
| Map không lọc đúng | Dùng `filterObject.owner` dù đối tượng hiện tại là `Map.Entry` | Dùng `filterObject.value.owner` hoặc biểu thức có chủ đích với `key` |
| `IllegalArgumentException` cho giá trị trả về | Kiểu không thuộc bốn dạng được handler hỗ trợ, ví dụ `Optional<T>`, `Page<T>`, một `Iterable` tùy biến | Tự lọc qua tầng dữ liệu hoặc chuyển sang kiểu được hỗ trợ; không giả định `Page` tự được lọc |
| `IllegalStateException` ở `@PreFilter` | Có nhiều đối số nhưng không tìm được tham số cần lọc; một số signature array không được hỗ trợ bởi interceptor | Đặt `filterTarget`, giữ metadata tên tham số; với array cân nhắc chuyển sang `List` và test |
| Trả danh sách thấy thiếu dữ liệu ở các lần gọi sau | `@PostFilter` đã thay đổi collection/map dùng chung | Không trả lại trực tiếp cache, singleton state hoặc entity collection dùng chung; tạo bản sao |
| Stream lỗi đóng / thiếu dữ liệu / lỗi ngoài transaction | Đã tiêu thụ hoặc đóng stream; deferred filtering vượt qua vòng đời transaction/context | Materialize khi còn transaction, đóng đúng cách, tránh song song nếu chưa kiểm chứng |
| Unit test gọi service trực tiếp vẫn trả toàn bộ | Tạo đối tượng bằng `new` nên không qua advisor bảo mật | Kiểm thử với `@SpringBootTest` và `@WithMockUser` hoặc context bảo mật tương đương |

Hãy kiểm tra thêm các trường hợp `null` ở tham số/giá trị, phần tử không có owner, chủ sở hữu không khớp, collection trống, nhiều người dùng, và vai trò khác nhau. Đừng để lỗi xử lý `null` vô tình biến thành việc bỏ qua kiểm tra. Với điều kiện phức tạp, có thể đưa quyết định cấp quyền vào bean chuyên dụng và gọi từ SpEL, sau đó kiểm thử độc lập.

## 8. Khi nào nên lọc ở tầng dữ liệu?

`@PostFilter` đọc kết quả **trước**, rồi mới xét từng phần tử: nếu lấy 100.000 bản ghi để trả 20 bản ghi hợp lệ, chi phí tải dữ liệu và thực thi truy vấn đã phát sinh. Khi có `Page<Doc>`, việc lọc sau cũng làm sai số phần tử của trang và tổng bản ghi; `Page` không phải là `Collection` thông thường mà handler mặc định tự hiểu.

Hướng thực tế với dữ liệu lớn: đưa điều kiện chủ sở hữu/tenant/quyền xem vào truy vấn repository, thêm ràng buộc method authorization ở service khi cần, sau đó kiểm thử không có rò rỉ giữa tenant. Chỉ dùng `@PostFilter` cho tập dữ liệu nhỏ đã được xử lý trong bộ nhớ hoặc khi nó thực sự phù hợp với thiết kế bảo mật.

## 9. Bài tập tự kiểm chứng

Cho danh sách A(owner=alice), B(owner=bob), C(owner=alice) và tài khoản `alice`:

1. Qua `@PreFilter` trên `new ArrayList<>(...)`, phương thức xử lý còn A và C; quan sát xem danh sách do caller giữ có bị thay đổi không.
2. Qua `@PostFilter` trên `LinkedHashMap` gồm khóa `a`→A, `b`→B, `c`→C, kết quả còn khóa `a` và `c` khi dùng `filterObject.value.owner`.
3. Qua `@PostFilter` trên `Doc[]`, kết quả có hai phần tử A và C; mảng đầu ra là mảng mới có độ dài 2.
4. Qua `@PostFilter` trên `Stream<Doc>`, so sánh thời điểm gọi phương thức với lúc thực thi `toList()`; xác nhận stream chỉ được tiêu thụ một lần.
5. Đổi đầu vào prefilter sang `List.of(...)` hoặc dùng chữ ký nhận `Doc[]`, chạy test chống lộ B trên **chính phiên bản được khóa**. Nếu test thất bại hoặc phát hiện B lọt qua, dùng `List` có thể sửa và cập nhật thiết kế trước khi triển khai.

**Tiêu chí hoàn thành:** giải thích được `filterObject` theo từng kiểu; chọn đúng pre/post và đúng thời điểm lọc; không cho đầu vào bất biến khiến `@PreFilter` vô hiệu; chủ động kiểm thử các khác biệt giữa phiên bản thay vì chỉ dựa vào tên annotation.

## Tài liệu tham khảo chính

- Spring Security 6.5 – Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 7.0 – Method Security: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html
- Mã nguồn `DefaultMethodSecurityExpressionHandler` 5.8.x: https://raw.githubusercontent.com/spring-projects/spring-security/5.8.x/core/src/main/java/org/springframework/security/access/expression/method/DefaultMethodSecurityExpressionHandler.java
- API `PreFilter` 7.0 (đối chiếu mô tả cũ về array): https://www.springframework.org/spring-security/reference/7.0/api/java/org/springframework/security/access/prepost/PreFilter.html
- Mã nguồn handler trên nhánh hiện hành (đối chiếu xử lý collection/map bất biến): https://raw.githubusercontent.com/spring-projects/spring-security/main/core/src/main/java/org/springframework/security/access/expression/method/DefaultMethodSecurityExpressionHandler.java
