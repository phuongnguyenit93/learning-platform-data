# Quản lý dependency tùy chọn cho reactive, Querydsl, web và Kotlin

Spring Data Commons cung cấp nhiều abstraction dùng chung, nhưng một ứng dụng không nhất thiết sử dụng tất cả các nhánh tích hợp của nó. Ứng dụng Java đồng bộ có thể không cần coroutine; một tác vụ chạy nền có thể không cần web; repository dùng derived queries có thể không cần Querydsl.

Quản lý dependency tùy chọn là xác định tính năng nào thực sự cần, thành phần nào cung cấp tính năng đó, dependency nào phải có lúc build hoặc lúc chạy và nguồn nào quản lý phiên bản. Việc một API có mặt trong Commons không tự biến mọi store module thành một implementation của API đó.

Bài học thuộc chương **Phụ thuộc và phiên bản**, tập trung vào bốn nhóm tích hợp: reactive, Querydsl, web và Kotlin. Các đoạn cấu hình là những phần minh họa cho từng nhu cầu; phiên bản phải được quản lý theo bộ dependency và module thực tế của dự án.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt tính năng tùy chọn với dependency bắt buộc khi đã chọn tính năng đó.
- Phân biệt Maven `optional`, scope dependency và cách khai báo theo configuration của Gradle.
- Xác định vai trò của Reactor, reactive store module và driver.
- Tách dependency Querydsl dùng lúc chạy khỏi annotation processor dùng để sinh kiểu truy vấn.
- Xác định những gì web support của Spring Data hỗ trợ và những gì ứng dụng phải cấu hình riêng.
- Chọn dependency Kotlin cơ bản, reflection và coroutine theo đúng nhu cầu.
- Nhận diện lỗi do thiếu dependency, sai classpath, code generation hoặc sai khả năng hỗ trợ của store.

## 2. “Tùy chọn” có nhiều nghĩa khác nhau

### 2.1. Tùy chọn đối với người không dùng tính năng

Một ứng dụng chỉ dùng repository đồng bộ không cần thêm Reactor chỉ vì Commons có các API reactive. Một ứng dụng không phục vụ HTTP không cần thêm web stack chỉ để dùng `PageRequest` hoặc `Sort` trong service.

Nhưng khi ứng dụng đã sử dụng một public API có kiểu `Mono`, `Predicate` của Querydsl hoặc `Flow`, thư viện định nghĩa kiểu đó phải có ở những classpath liên quan. Đối với tính năng đã chọn, dependency này không còn là thứ có thể bỏ tùy ý.

### 2.2. Dependency tùy chọn trong metadata của thư viện

Trong Maven, `<optional>true</optional>` diễn đạt rằng dependency không được kéo bắc cầu tới dự án tiêu thụ theo cách mặc định như một dependency thông thường. Nó không có nghĩa là dependency ấy không cần thiết khi tính năng tương ứng được sử dụng.

Ví dụ sau có thể xuất hiện trong một thư viện cung cấp phần tích hợp Reactor. Giả định dependency management của thư viện đã cung cấp phiên bản Reactor phù hợp:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-core</artifactId>
    <optional>true</optional>
</dependency>
```

Thư viện vẫn cần Reactor để biên dịch phần mã sử dụng Reactor. Ứng dụng tiêu thụ muốn dùng phần tích hợp đó phải có dependency cần thiết trong cấu hình của mình.

Nếu public API của thư viện trả về `Mono<Customer>`, ứng dụng tiêu thụ API đó cần nhìn thấy cả kiểu `Mono`. Đánh dấu dependency là optional không che được sự phụ thuộc đã thể hiện trong chữ ký phương thức.

### 2.3. Dependency chỉ có lúc biên dịch là một lựa chọn khác

| Cơ chế | Ý nghĩa chính | Điều không được suy ra |
| --- | --- | --- |
| Maven `optional` | Giới hạn việc truyền dependency bắc cầu tới bên tiêu thụ | Tính năng vẫn chạy được khi thiếu thư viện lúc runtime |
| Maven `provided` | Biên dịch với dependency, kỳ vọng môi trường cung cấp khi chạy | Mọi môi trường triển khai đều tự có dependency đó |
| Gradle `implementation` | Dependency tham gia implementation và runtime theo mô hình configuration | Phiên bản đã tự tương thích với toàn bộ hệ thống |
| Gradle `api` | Trong mô hình Java Library, dependency còn được công bố cho bên tiêu thụ API | Chỉ cần có kiểu là implementation tương ứng đã tồn tại |
| Gradle `compileOnly` | Dependency có ở compile classpath, không mặc định đi vào runtime | Tương đương hoàn toàn với Maven `optional` |
| Annotation processor hoặc công cụ sinh mã | Chạy trong quá trình build để tạo mã hoặc metadata | Thay thế dependency API/runtime được mã sinh ra sử dụng |
| Dependency test | Phục vụ kiểm thử theo scope hoặc configuration | Ứng dụng đóng gói cũng có dependency đó |

Đặc biệt, không dùng `compileOnly` để làm một dependency “có vẻ tùy chọn” nếu mã runtime luôn trực tiếp sử dụng nó. Việc biên dịch thành công có thể chỉ trì hoãn lỗi đến lúc chạy.

## 3. Lập bản đồ tính năng trước khi thêm thư viện

| Nhóm tính năng | Các thành phần thường liên quan | Cần quyết định trước |
| --- | --- | --- |
| Reactive | API reactive trong Commons, Reactor hoặc thư viện kiểu reactive liên quan, reactive store module, driver | Store có đường truy cập reactive phù hợp không? |
| Querydsl | API Querydsl, tích hợp của store, kiểu Q được sinh và công cụ sinh mã | Cần module Querydsl nào, processor nào và namespace nào? |
| Web | Spring MVC hoặc WebFlux, hỗ trợ argument binding, có thể thêm HATEOAS hoặc Querydsl web binding | Cần tính năng web nào, trên stack nào? |
| Kotlin | Kotlin standard library, reflection khi cần, compiler/plugin; coroutine nếu sử dụng | Chỉ viết Kotlin hay còn dùng repository coroutine? |

Mỗi nhánh có ba điều kiện độc lập:

1. **Có dependency:** các lớp cần thiết xuất hiện ở classpath phù hợp.
2. **Có implementation và khả năng hỗ trợ:** module đã chọn thực hiện tính năng đó.
3. **Có cấu hình:** ứng dụng kích hoạt, ánh xạ và kết nối các thành phần đúng cách.

Thiếu một trong ba điều kiện vẫn có thể làm tính năng không hoạt động. Không nên phản ứng với mọi lỗi bằng cách thêm một JAR bất kỳ có tên gần giống API đang thiếu.

## 4. Reactive: kiểu dữ liệu không thay thế đường truy cập dữ liệu

### 4.1. Những lớp thành phần cần phân biệt

Trong một ứng dụng Spring Data dùng Reactor, có thể gặp:

- Các abstraction repository reactive của Spring Data Commons.
- Các kiểu như `Mono` và `Flux` của Reactor.
- Store module hỗ trợ repository reactive.
- Driver và cơ chế truy cập dữ liệu reactive phù hợp.
- WebFlux nếu ứng dụng còn cần tầng HTTP theo mô hình đó.

Reactor cung cấp kiểu dữ liệu và toán tử reactive; Reactor không tự cung cấp khả năng lưu MongoDB, truy cập SQL hoặc tạo repository cho mọi store.

Tương tự, `ReactiveCrudRepository` là hợp đồng repository. Để tạo bean thực thi hợp đồng, ứng dụng cần store module có hỗ trợ, mapping và cấu hình tương ứng.

### 4.2. Chọn dependency theo đường sử dụng

Với ứng dụng Boot cần repository MongoDB reactive, một khai báo Maven có thể là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
```

Giả định dependency management của Boot đã được cấu hình. Starter đưa vào bộ dependency phục vụ hướng tích hợp đó; hãy xem dependency graph để xác nhận các thành phần thực tế và phiên bản.

Nếu ứng dụng là worker đọc ghi dữ liệu mà không cung cấp HTTP, không cần thêm starter web chỉ để có repository reactive. Nếu ứng dụng cần endpoint WebFlux, tầng web là một lựa chọn bổ sung với cấu hình riêng.

Với dữ liệu quan hệ, cần phân biệt hướng JPA/JDBC đồng bộ với hướng truy cập reactive được module phù hợp hỗ trợ, chẳng hạn R2DBC. Thêm Reactor bên cạnh JPA không làm JPA tự trở thành một persistence API non-blocking.

### 4.3. Bọc mã đồng bộ không tạo driver reactive

Xét ý tưởng sau:

```java
Mono<Customer> result = Mono.fromCallable(
        () -> blockingRepository.findById(id).orElseThrow());
```

Đây vẫn là thao tác repository đồng bộ được đặt trong một publisher. Khi được thực thi, nó vẫn có thể chặn thread. Muốn sử dụng cách thích nghi này có chủ đích, ứng dụng phải quản lý scheduler và tài nguyên phù hợp; nó không tương đương thay persistence layer bằng driver reactive.

Việc đổi kiểu trả về của service sang `Mono` cũng không chứng minh giao dịch, propagation ngữ cảnh và auditing đã chuyển đúng sang mô hình reactive.

### 4.4. Kiểm tra cả ngữ cảnh thực thi

Nếu ứng dụng dùng auditing chủ thể trong luồng reactive, cần cơ chế cung cấp chủ thể phù hợp với luồng đó. Không mặc định cách lấy người dùng qua thread-local của một luồng đồng bộ sẽ hoạt động nguyên trạng trong mọi pipeline reactive.

Nếu dùng giao dịch reactive, phải có hỗ trợ và transaction manager phù hợp với tài nguyên reactive. Sự hiện diện của annotation giao dịch chưa đủ để kết luận mọi publisher được gọi đã nằm trong ranh giới giao dịch mong muốn.

## 5. Querydsl: tách API, tích hợp store và mã được sinh

### 5.1. Querydsl phục vụ điều gì?

Querydsl cho phép biểu diễn truy vấn bằng các kiểu Java thay vì chỉ nối chuỗi. Trong cách sử dụng phổ biến với mô hình miền, quá trình build sinh ra các kiểu Q, chẳng hạn `QCustomer`, chứa các đường dẫn thuộc tính có kiểu.

Một số module Spring Data tích hợp Querydsl qua các abstraction như `QuerydslPredicateExecutor`. Commons cung cấp phần hợp đồng và hạ tầng liên quan, còn mức hỗ trợ thực tế phụ thuộc store module và phiên bản.

Không mặc định mọi repository đều có thể thêm `QuerydslPredicateExecutor` rồi chạy đầy đủ mọi phép truy vấn Querydsl.

### 5.2. Ba nhóm dependency cần quản lý riêng

| Nhóm | Vai trò | Ví dụ nội dung |
| --- | --- | --- |
| API và thư viện truy vấn | Cung cấp các kiểu được mã ứng dụng, tích hợp và mã sinh ra sử dụng | `Predicate`, đường dẫn kiểu dữ liệu và API Querydsl theo công nghệ |
| Tích hợp store | Chuyển predicate và thao tác repository thành truy vấn phù hợp | Implementation Querydsl mà module Spring Data hỗ trợ |
| Sinh mã | Tạo các kiểu Q từ mô hình nguồn | Annotation processor, cấu hình build và thư mục generated sources |

Với JPA, các artifact thường được xem xét gồm `querydsl-jpa` và `querydsl-apt`, cùng API liên quan. Artifact, namespace, classifier và processor cụ thể phải phù hợp dòng Querydsl, JPA và công cụ build đang dùng.

Không sao chép nguyên cấu hình processor từ một dự án khác khi dự án đang sử dụng namespace hoặc thế hệ nền tảng khác. Bộ xử lý dành cho một mô hình annotation không tự nhận biết mọi mô hình còn lại.

### 5.3. Vì sao có dependency mà vẫn thiếu `QCustomer`?

`QCustomer` thường không phải lớp được tải từ dependency Commons. Nó được tạo từ mô hình `Customer` của chính dự án.

Nếu trình biên dịch báo không tìm thấy `QCustomer`, hãy kiểm tra:

1. Processor có được khai báo ở đúng cấu hình dành cho annotation processing không?
2. Processor có hỗ trợ annotation và namespace của mô hình không?
3. Mô hình cần xử lý có nằm trong source set hoặc module mà processor nhìn thấy không?
4. Build có thực sự chạy bước sinh mã không?
5. Generated sources có tham gia bước biên dịch cần dùng chúng không?
6. IDE và CI có thống nhất cách sinh mã không?

Chỉ thêm thư viện Querydsl runtime không bảo đảm processor sẽ tự chạy. Ngược lại, chỉ có processor cũng không bảo đảm ứng dụng runtime có các lớp mà mã Q hoặc tích hợp store cần sử dụng.

### 5.4. Ví dụ ý nghĩa của mã truy vấn

Giả sử store module hỗ trợ tích hợp Querydsl, repository có `QuerydslPredicateExecutor<Customer>` và build đã sinh `QCustomer` với thuộc tính boolean `active`:

```java
QCustomer customer = QCustomer.customer;

Iterable<Customer> activeCustomers =
        customerRepository.findAll(customer.active.isTrue());
```

Đoạn mã cho thấy predicate được xây dựng từ kiểu Q. Nó không thay thế cấu hình mapping, chỉ mục hoặc dependency tích hợp của store.

Khi đổi mô hình miền, các kiểu Q phải được sinh lại. Nếu mã Q cũ chỉ còn trong máy của một thành viên, IDE có thể chạy được trong khi clean build trên CI thất bại. Vì vậy, quy trình build phải tự tạo được các đầu ra cần thiết từ mã nguồn và cấu hình đã lưu.

### 5.5. Querydsl với Kotlin cần xem cả chuỗi sinh mã

Nếu mô hình nguồn viết bằng Kotlin, annotation processor Java không mặc định xử lý trực tiếp mã Kotlin theo cùng cách xử lý Java. Cần chọn cơ chế phù hợp, chẳng hạn cấu hình kapt khi bộ processor và dự án hỗ trợ cách đó.

Không coi kapt và KSP là hai tên thay thế cho cùng một công cụ. KSP cần processor hoặc tích hợp tương thích với nó. Hãy kiểm tra khả năng của bộ sinh mã đã chọn trước khi thay cấu hình build.

## 6. Web: tách kiểu phân trang khỏi tích hợp HTTP

### 6.1. Dùng `Pageable` không bắt buộc phải có web

`Pageable`, `PageRequest`, `Page`, `Slice` và `Sort` có thể được sử dụng trực tiếp trong service hoặc tác vụ nền. Chúng không yêu cầu ứng dụng phải cung cấp HTTP endpoint.

Web support là tầng thích nghi bổ sung. Ví dụ, một argument resolver có thể chuyển các tham số HTTP như `page`, `size` và `sort` thành `Pageable` hoặc `Sort` cho controller.

```text
Tham số HTTP
    |
    v
Argument resolver của web stack
    |
    v
Pageable / Sort
    |
    v
Service hoặc repository hỗ trợ thao tác tương ứng
```

Có kiểu `Pageable` trên classpath chưa chứng minh web stack đã đăng ký resolver để tạo ra nó từ request.

### 6.2. Chọn đúng Spring MVC hoặc WebFlux

Một controller Spring MVC và một handler WebFlux hoạt động trên hạ tầng khác nhau. Cần sử dụng cơ chế cấu hình và resolver phù hợp với stack, module và phiên bản của ứng dụng.

Trong hướng tích hợp Spring MVC, có thể gặp annotation `@EnableSpringDataWebSupport` để bật hỗ trợ web của Spring Data. Với ứng dụng Boot, một phần cấu hình có thể được cung cấp qua auto-configuration khi đáp ứng các điều kiện liên quan.

Hãy xác định ứng dụng đang dựa vào auto-configuration hay cấu hình tường minh trước khi thêm annotation hoặc resolver thủ công. Việc đăng ký lại thành phần có thể thay đổi hoặc trùng cấu hình mặc định. Với WebFlux, kiểm tra riêng cơ chế hỗ trợ tương ứng; không suy ra một cấu hình MVC được áp dụng nguyên trạng cho reactive web stack.

### 6.3. Ví dụ controller nhận phân trang

Giả sử ứng dụng MVC đã cấu hình argument resolver, repository hỗ trợ truy vấn và có kiểu projection `CustomerSummary`:

```java
@GetMapping("/customers")
public Page<CustomerSummary> list(Pageable pageable) {
    return customerRepository.findByActiveTrue(pageable);
}
```

Một request có thể mang ý nghĩa:

```text
GET /customers?page=0&size=20&sort=email,asc
```

Các tên tham số và cách đánh số trang cần được đối chiếu cấu hình thực tế. Hỗ trợ binding không tự xác định toàn bộ hợp đồng API của ứng dụng.

Cần quyết định giới hạn kích thước trang, trường sắp xếp cho phép và cách xử lý đầu vào không hợp lệ. Phần này vừa bảo vệ tính nhất quán của API vừa tránh để client phụ thuộc vào mọi thuộc tính persistence.

Khi trả kết quả phân trang qua HTTP, hãy chọn hình dạng phản hồi có chủ đích, chẳng hạn DTO của ứng dụng hoặc cơ chế biểu diễn được phiên bản thư viện hỗ trợ. Không nên coi mọi chi tiết JSON của một implementation nội bộ như `PageImpl` là hợp đồng bất biến giữa các lần nâng cấp.

### 6.4. Spring Data web support không đồng nghĩa Spring Data REST

Web support có thể cung cấp chuyển đổi kiểu và binding đối số. Spring Data REST là một hướng tích hợp khác để đưa repository ra tài nguyên HTTP theo cơ chế của nó.

Chỉ thêm Commons và bật web support không tự tạo toàn bộ CRUD endpoint cho mọi repository. Tương tự, không cần đưa Spring Data REST vào ứng dụng chỉ để nhận `Pageable` trong một controller do ứng dụng tự viết.

Nếu cần biểu diễn liên kết và tài nguyên theo HATEOAS, đó là nhu cầu bổ sung cần dependency và cấu hình phù hợp. Không thêm toàn bộ nhóm web mở rộng khi ứng dụng chỉ cần một chức năng binding nhỏ.

### 6.5. Domain conversion và Querydsl web binding là các lựa chọn bổ sung

Một số cấu hình web hỗ trợ chuyển giá trị ID thành đối tượng miền hoặc binding request thành Querydsl predicate. Những khả năng này phụ thuộc điều kiện hỗ trợ và cấu hình cụ thể.

Cần phân biệt:

- Chuyển ID thành đối tượng không tự thực hiện kiểm tra quyền truy cập đối tượng.
- Bind request thành predicate không tự xác định danh sách trường mà client được phép tìm kiếm.
- Có Querydsl trên classpath không chứng minh store module thực thi được mọi predicate mà tầng web tạo ra.

Nếu tính năng chỉ cần vài bộ lọc nghiệp vụ cố định, DTO đầu vào và logic chuyển điều kiện tường minh có thể tạo hợp đồng rõ ràng hơn. Nếu dùng Querydsl binding, hãy cấu hình phạm vi thuộc tính và quy tắc binding theo đúng nhu cầu.

## 7. Kotlin: tách ngôn ngữ, reflection và coroutine

### 7.1. Kotlin cơ bản không đồng nghĩa reactive

Một ứng dụng viết bằng Kotlin vẫn có thể dùng repository đồng bộ. Không cần thêm coroutine hoặc WebFlux chỉ vì mã nguồn có đuôi `.kt`.

Các thành phần thường cần xem xét là:

| Thành phần | Vai trò |
| --- | --- |
| Kotlin compiler và plugin build | Biên dịch mã Kotlin, quản lý các tùy chọn ngôn ngữ và JVM target |
| Kotlin standard library | Cung cấp các kiểu và tiện ích runtime của Kotlin |
| `kotlin-reflect` | Cung cấp reflection Kotlin cho những cơ chế introspection cần nó |
| Plugin theo nhu cầu framework | Hỗ trợ các yêu cầu như mở lớp hoặc tạo constructor trong những trường hợp phù hợp |
| Coroutine libraries | Cung cấp `Flow`, coroutine và khả năng tích hợp reactive khi sử dụng |

Trong mô hình Kotlin mà Spring Data dùng reflection để hiểu constructor, thuộc tính hoặc thông tin kiểu, cần cung cấp `kotlin-reflect` theo yêu cầu của dòng tích hợp đang dùng. Có compiler Kotlin không đồng nghĩa runtime đã có thư viện reflection.

Các plugin phục vụ Spring hoặc JPA là những lựa chọn giải quyết yêu cầu cụ thể. Không áp dụng nguyên cấu hình JPA cho mọi loại store chỉ vì cùng viết bằng Kotlin.

### 7.2. Constructor, nullability và mapping vẫn là công việc của store

Kotlin cho phép thể hiện thuộc tính nullable, giá trị mặc định và mô hình bất biến. Spring Data có các cơ chế hỗ trợ mô hình Kotlin, nhưng việc khởi tạo và ánh xạ đối tượng còn phụ thuộc metadata và store module.

Khi dùng một `data class` hoặc constructor có giá trị mặc định, hãy kiểm tra cách dữ liệu thiếu trường, giá trị `null`, ID và các trường auditing được ánh xạ. Đừng suy ra mọi constructor Kotlin đều có cùng hành vi trên mọi store.

Một thuộc tính khai báo non-null cũng không tự sửa dữ liệu `null` đã tồn tại trong kho. Ràng buộc mô hình nguồn cần đi cùng dữ liệu và quy tắc mapping tương ứng.

### 7.3. Coroutine repository cần thêm một lớp tích hợp

Các abstraction như `CoroutineCrudRepository` cho phép diễn đạt thao tác bằng `suspend` và các kiểu coroutine. Chúng cần module có hỗ trợ phù hợp; việc đổi interface không tự tạo đường truy cập dữ liệu coroutine cho mọi store.

Ví dụ khai báo, giả định module hỗ trợ repository coroutine và các derived query tương ứng:

```kotlin
import kotlinx.coroutines.flow.Flow
import org.springframework.data.repository.kotlin.CoroutineCrudRepository

interface CustomerRepository : CoroutineCrudRepository<Customer, String> {
    suspend fun findByEmail(email: String): Customer?

    fun findByActiveTrue(): Flow<Customer>
}
```

Ở đây:

- `suspend` là đặc tính của phương thức Kotlin, không phải bằng chứng một driver bất kỳ đã non-blocking.
- `Flow` đến từ thư viện coroutine.
- Cách thực thi và tích hợp với dữ liệu reactive cần các thành phần tương ứng của module.
- Kiểu `Customer?` diễn đạt khả năng không tìm thấy trong hợp đồng Kotlin.

### 7.4. Dependency coroutine theo nhu cầu

Các artifact thường liên quan gồm:

- `org.jetbrains.kotlinx:kotlinx-coroutines-core` cho coroutine và `Flow`.
- `org.jetbrains.kotlinx:kotlinx-coroutines-reactor` khi cần tích hợp coroutine với Reactor.
- `org.jetbrains.kotlin:kotlin-reflect` cho reflection Kotlin cần thiết theo cấu hình.

Trong dự án đã có dependency management phù hợp, phần khai báo Maven có thể là:

```xml
<dependency>
    <groupId>org.jetbrains.kotlin</groupId>
    <artifactId>kotlin-reflect</artifactId>
</dependency>
<dependency>
    <groupId>org.jetbrains.kotlinx</groupId>
    <artifactId>kotlinx-coroutines-core</artifactId>
</dependency>
<dependency>
    <groupId>org.jetbrains.kotlinx</groupId>
    <artifactId>kotlinx-coroutines-reactor</artifactId>
</dependency>
```

Đây không phải toàn bộ build Kotlin. Vẫn cần compiler/plugin, standard library và module dữ liệu theo nhu cầu. Kiểm tra dependency graph để biết thành phần nào đã được starter hoặc dependency khác cung cấp, đồng thời xác nhận version của các thành phần ngoài phạm vi quản lý hiện có.

Phiên bản plugin Kotlin, Kotlin runtime libraries, coroutines và JVM target có quan hệ nhưng không phải cùng một số phiên bản dùng cho tất cả. Hãy đối chiếu yêu cầu của bộ tích hợp thay vì chép một giá trị cho mọi artifact.

## 8. Quản lý phiên bản theo nhóm trách nhiệm

Nếu ứng dụng dùng Spring Boot, dependency management của Boot là điểm xuất phát hợp lý cho những dependency nằm trong phạm vi nó quản lý. Nếu không dùng Boot, phải xác định nguồn quản lý tương ứng cho Spring Data và các hệ sinh thái bổ sung.

BOM Spring Data không phải lời hứa rằng mọi version của Reactor, Querydsl, Kotlin compiler, coroutines, web stack và công cụ sinh mã đều đã được cấu hình cho dự án. Hãy xem nội dung quản lý có hiệu lực của đúng bộ đang sử dụng.

| Nhóm | Những gì nên đối chiếu cùng nhau |
| --- | --- |
| Spring Data | Commons, store module, phạm vi hỗ trợ tính năng |
| Reactive | Reactor, thư viện reactive liên quan, reactive module và driver |
| Querydsl | API/runtime, module theo công nghệ, processor, classifier hoặc namespace |
| Web | Spring Framework web stack, resolver, tích hợp HATEOAS hoặc REST nếu dùng |
| Kotlin | Compiler/plugin, standard library, reflection, coroutine và JVM target |

Cần đặc biệt chú ý version của plugin build và annotation processor. Dependency management của thư viện runtime không phải lúc nào cũng tự áp dụng lên cấu hình plugin hoặc processor theo cùng cách. Chỉ ra nguồn cấp version cho từng vị trí giúp tránh hai phiên bản khác nhau bị đưa vào quá trình build và runtime.

## 9. Thiết kế thư viện có tích hợp tùy chọn

Khi xây dựng một thư viện dùng Commons, tính tùy chọn cần được thể hiện cả trong cấu trúc mã, không chỉ trong file build.

Một cách tổ chức có thể là:

```text
Thành phần lõi
    +-- hợp đồng chung cần cho mọi bên tiêu thụ

Phần tích hợp reactive
    +-- API và cấu hình riêng cho Reactor/reactive

Phần tích hợp web
    +-- resolver hoặc adapter web

Phần tích hợp Querydsl
    +-- binding hoặc thao tác predicate
```

Có thể tách thành các artifact khi ranh giới dependency có giá trị thực tế. Nếu giữ chung một artifact, cần bảo đảm mã của nhánh không được sử dụng không bị khởi tạo hoặc nạp theo cách bắt buộc phải có dependency tùy chọn.

Trong thư viện tích hợp Boot, điều kiện như `@ConditionalOnClass` có thể hỗ trợ đăng ký cấu hình khi dependency phù hợp có mặt. Tuy nhiên, cách đặt điều kiện và tham chiếu kiểu trong cấu hình phải tuân theo cơ chế xử lý của framework. Chỉ thêm một annotation không tự bảo đảm mọi đường nạp lớp đều an toàn khi thiếu thư viện.

Hợp đồng công bố cũng phải rõ ràng: nếu một API public luôn trả về `Mono`, nó đã là API phụ thuộc Reactor. Đừng mô tả API đó là độc lập reactive chỉ vì dependency được đánh dấu optional trong Maven.

## 10. Chọn tập dependency cho những ứng dụng cụ thể

### Trường hợp A: tác vụ Java đồng bộ, không phục vụ HTTP

Tác vụ đọc khách hàng theo trang và ghi kết quả xử lý. Dùng store module đồng bộ cùng các kiểu `Pageable`, `PageRequest` hoặc `Sort` cần thiết.

Không cần đưa vào web stack chỉ để tạo yêu cầu phân trang. Không cần Querydsl nếu derived queries hoặc phương thức truy vấn hiện có đã đáp ứng nhu cầu. Không cần Kotlin hoặc coroutine khi không có mã hay API liên quan.

### Trường hợp B: dịch vụ MongoDB reactive có HTTP API

Cần đường dữ liệu reactive của MongoDB, các kiểu reactive và tầng HTTP phù hợp như WebFlux nếu thiết kế chọn stack đó.

Kiểm tra riêng binding phân trang hoặc bộ lọc trên web stack. Không mặc định reactive repository sẽ tự tạo argument resolver cho mọi controller.

### Trường hợp C: ứng dụng JPA có bộ lọc động bằng Querydsl

Cần store module JPA phù hợp, các thư viện Querydsl liên quan và cấu hình processor tạo Q-type từ entity. Nếu expose bộ lọc qua HTTP, phần web binding là lựa chọn bổ sung.

Một clean build phải tự sinh được Q-type cần dùng. Một lần chạy từ IDE có lớp Q cũ không đủ xác nhận cấu hình build đã hoàn chỉnh.

### Trường hợp D: ứng dụng Kotlin dùng repository đồng bộ

Cần chuỗi build Kotlin, runtime và reflection theo yêu cầu mapping. Không cần coroutine chỉ để gọi một repository đồng bộ từ mã Kotlin.

Nếu sau này chuyển sang repository coroutine, đánh giá lại store module, các dependency coroutine, bridge reactive và cách truyền ngữ cảnh. Đây là thay đổi về đường thực thi, không chỉ là thêm từ khóa `suspend`.

## 11. Quy trình thêm một nhóm dependency tùy chọn

1. **Mô tả tính năng cần dùng.** Ví dụ, “controller nhận `Pageable` từ request” cụ thể hơn “thêm hỗ trợ web”.
2. **Xác định API và implementation.** Chỉ ra kiểu do thư viện nào định nghĩa, module nào thực thi và store nào hỗ trợ.
3. **Chia theo thời điểm sử dụng.** Tách compiler/plugin, processor, compile API, runtime và test.
4. **Chọn nguồn quản lý phiên bản.** Dùng bộ đang được điều phối; ghi rõ thành phần ngoài phạm vi quản lý.
5. **Khai báo tối thiểu đủ cho tính năng.** Kiểm tra dependency bắc cầu trước khi thêm những khai báo trùng không cần thiết.
6. **Đọc dependency graph đã resolve.** Xác nhận dependency runtime, processor và framework không bị chọn lệch ngoài dự kiến.
7. **Kiểm tra đúng đường chạy.** Gọi repository, thử binding HTTP, sinh Q-type hoặc chạy coroutine theo tính năng đã thêm.
8. **Giữ tính tùy chọn có ý nghĩa.** Với thư viện, kiểm tra cả trường hợp không có dependency của nhánh tích hợp không sử dụng.

Ví dụ, kiểm tra Querydsl nên bao gồm clean build và thực thi một truy vấn trên store thích hợp. Kiểm tra web support nên gửi request để xác nhận resolver và quy tắc giới hạn trang. Chỉ kiểm tra application context khởi động có thể chưa đi qua những đường này.

## 12. Chẩn đoán thiếu dependency theo triệu chứng

| Triệu chứng | Cần điều tra trước |
| --- | --- |
| Không tìm thấy `Mono` hoặc `Flux` khi biên dịch | Reactor có trong compile classpath của module chứa mã hay không |
| Runtime thiếu lớp reactive dù compile được | Scope/configuration, dependency optional của thư viện và gói runtime |
| Repository reactive không được tạo | Store module có hỗ trợ không, phạm vi scan và cấu hình repository |
| Không tìm thấy `QCustomer` | Processor, namespace, source set, bước sinh mã và generated sources |
| Có Q-type nhưng thiếu lớp Querydsl khi chạy | Dependency API/runtime mà mã sinh ra hoặc tích hợp store cần |
| Controller không bind được `Pageable` | Web stack, argument resolver, auto-configuration và cấu hình tường minh |
| Thêm web support nhưng không có CRUD endpoint | Có nhầm web argument binding với Spring Data REST hay không |
| Lỗi introspection mô hình Kotlin | Kotlin runtime/reflection, constructor và metadata mapping |
| Không tìm thấy `Flow` hoặc lớp bridge coroutine | Dependency coroutines-core và bridge cần cho đường tích hợp đang dùng |
| Có `NoSuchMethodError` sau khi thêm tính năng | Version thực tế của các dependency runtime so với bộ đang quản lý |

Triệu chứng không xác định duy nhất một nguyên nhân. Hãy đọc toàn bộ chuỗi lỗi và classpath thực tế trước khi thay phiên bản hoặc thêm dependency. Nếu lỗi do module không hỗ trợ một khả năng, bổ sung thư viện định nghĩa kiểu chưa chắc giải quyết được.

## 13. Bài tập tự kiểm tra

### Câu 1

Một service không có HTTP endpoint nhưng dùng `PageRequest` để đọc dữ liệu từng trang. Nó có bắt buộc cần Spring MVC không?

**Gợi ý trả lời:** Không. Tạo mô tả phân trang trong mã không cần web argument binding. Chỉ thêm tầng web khi có nhu cầu web cụ thể.

### Câu 2

Một thư viện đánh dấu Reactor là Maven optional và công bố phương thức trả về `Mono<Customer>`. Ứng dụng sử dụng phương thức đó có thể bỏ Reactor không?

**Gợi ý trả lời:** Không. Optional giới hạn truyền dependency bắc cầu; nó không loại bỏ kiểu Reactor khỏi hợp đồng API. Bên sử dụng cần các dependency phù hợp để biên dịch và chạy đường tích hợp đó.

### Câu 3

Đã thêm thư viện Querydsl nhưng clean build vẫn báo không có `QCustomer`. Nên kiểm tra gì?

**Gợi ý trả lời:** Kiểm tra annotation processor, namespace hoặc classifier phù hợp, nguồn mô hình, cấu hình sinh mã và việc đưa generated sources vào biên dịch. Dependency runtime không tự thay thế bước sinh Q-type.

### Câu 4

Thêm `reactor-core` bên cạnh repository JPA có làm mọi thao tác lưu trở thành non-blocking không?

**Gợi ý trả lời:** Không. Cần đường truy cập dữ liệu và driver hỗ trợ mô hình đó. Bọc lời gọi đồng bộ trong publisher vẫn giữ bản chất chặn của thao tác bên trong.

### Câu 5

Ứng dụng viết bằng Kotlin có bắt buộc dùng coroutine repository không?

**Gợi ý trả lời:** Không. Kotlin có thể dùng repository đồng bộ. Coroutine là lựa chọn riêng, cần abstraction, dependency và hỗ trợ store phù hợp.

### Câu 6

Một dự án đã quản lý Commons và store module bằng BOM. Có thể mặc định version của Kotlin plugin và Querydsl processor cũng đã được chọn đúng không?

**Gợi ý trả lời:** Không. Phải kiểm tra phạm vi quản lý có hiệu lực và cách công cụ build cấp version cho từng plugin, processor hoặc dependency runtime.

### Câu 7

Điều gì chứng minh một phần tích hợp thực sự tùy chọn đối với bên không dùng nó?

**Gợi ý trả lời:** API lõi, dependency công bố và cách khởi tạo cấu hình không bắt buộc kéo theo hoặc nạp các lớp của phần tích hợp đó. Đồng thời, tài liệu phải chỉ rõ dependency cần thêm khi bên tiêu thụ chủ động sử dụng tính năng.