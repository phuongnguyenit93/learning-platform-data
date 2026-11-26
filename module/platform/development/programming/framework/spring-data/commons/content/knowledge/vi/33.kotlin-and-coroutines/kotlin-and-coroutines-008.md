# Dependency tùy chọn và giới hạn tính năng theo mô-đun

Viết repository bằng Kotlin không đồng nghĩa ứng dụng đã hỗ trợ coroutine. Thêm thư viện coroutine cũng không làm một repository blocking trở thành truy cập dữ liệu non-blocking. Một tính năng chỉ hoạt động khi ngôn ngữ, dependency, hạ tầng Spring, mô-đun lưu trữ và driver cùng hỗ trợ đường thực thi đó.

Trong Spring Data Commons, nhiều abstraction được thiết kế để dùng chung giữa các kho dữ liệu. Tuy nhiên, Commons không cung cấp thay mọi store một bộ máy truy vấn, driver hay transaction manager. Các dependency tùy chọn giúp thư viện phục vụ nhiều kiểu ứng dụng mà không bắt mọi người dùng tải toàn bộ hệ sinh thái Kotlin và coroutine.

Bài học thuộc chương **Kotlin và coroutine**, module **SPRING_DATA_COMMONS**. Nội dung hướng tới việc chọn đúng abstraction Repository, CRUD, truy vấn và metadata cho Kotlin, đồng thời nhận biết giới hạn khi dùng phân trang, projection, auditing hoặc mở rộng repository trên từng store.

## 1. Đọc đúng khái niệm dependency tùy chọn

### 1.1. Tùy chọn đối với thư viện, bắt buộc đối với tính năng

Một ứng dụng Java chỉ dùng repository thông thường không nhất thiết cần runtime coroutine. Vì vậy, một thư viện dùng chung có thể không kéo toàn bộ dependency coroutine một cách bắt buộc cho mọi ứng dụng.

Nhưng khi ứng dụng chủ động sử dụng `suspend`, `Flow` và coroutine repository, những dependency cần cho đường tích hợp đó trở thành yêu cầu của ứng dụng.

Có thể diễn đạt:

```text
Không dùng tính năng Kotlin/coroutine
    -> Có thể không cần các dependency dành riêng cho tính năng đó

Có dùng tính năng Kotlin/coroutine
    -> Phải có đủ dependency, phiên bản và store hỗ trợ tương ứng
```

Không nên hiểu từ “optional” thành “có hoặc không cũng cho cùng một hành vi”. Thiếu thư viện có thể làm một tích hợp không được kích hoạt, hoặc làm lỗi xuất hiện khi Spring tạo repository, đọc metadata hay gọi một phương thức cụ thể.

### 1.2. Dependency của producer khác dependency của consumer

Trong Maven, khi thư viện A khai báo dependency B là optional, ứng dụng C phụ thuộc A thường không tự nhận B theo đường bắc cầu đó. Nếu C cần tính năng dựa trên B, C phải bảo đảm B có mặt bằng khai báo hoặc một đường dependency phù hợp khác.

```text
Ứng dụng C --> Thư viện A -- optional --> Thư viện B

C không nên mặc định rằng B đã có mặt để sử dụng tính năng của A dựa trên B.
```

Đặt `<optional>true</optional>` trong dependency của một ứng dụng cũng không phải công tắc bật/tắt runtime feature cho chính ứng dụng đó. Ý nghĩa chính liên quan đến cách dependency được truyền cho bên phụ thuộc vào artifact này.

Tương tự, một dependency chỉ có trong test hoặc không được đóng gói cho runtime có thể làm bài kiểm tra chạy được nhưng ứng dụng triển khai lại thiếu class.

### 1.3. Thấy class chưa đủ chứng minh tính năng hoàn chỉnh

Có interface `CoroutineCrudRepository` trên classpath chưa chứng minh rằng repository factory của store đang dùng sẽ tạo được một implementation phù hợp.

Có class `Flow` cũng chưa chứng minh rằng truy vấn trả `Flow<Entity>` được module cụ thể hỗ trợ theo mọi dạng query.

Cần kiểm tra toàn bộ chuỗi:

```text
Mã Kotlin và compiler phù hợp
              |
              v
Runtime Kotlin, metadata và reflection khi cần
              |
              v
Coroutine runtime và các cầu nối cần thiết
              |
              v
Tích hợp của Spring Framework và Spring Data Commons
              |
              v
Store module, repository factory và query engine
              |
              v
Driver và khả năng thực tế của kho dữ liệu
```

## 2. Những nhóm dependency cần phân biệt

### 2.1. Kotlin standard library

Artifact thường gặp:

```text
org.jetbrains.kotlin:kotlin-stdlib
```

Standard library cung cấp các thành phần runtime và API nền tảng của Kotlin. Nó không phải bộ máy coroutine và không chứa toàn bộ khả năng reflection cấp cao.

Một dự án viết Kotlin cần một cấu hình compiler/build phù hợp ngoài dependency runtime. Thêm `kotlin-stdlib` vào một dự án chỉ đang biên dịch Java không tự tạo ra bước biên dịch các file Kotlin.

### 2.2. Kotlin reflection

Artifact:

```text
org.jetbrains.kotlin:kotlin-reflect
```

Spring và Spring Data có thể cần thông tin đặc thù của Kotlin để xử lý constructor, tham số, property và nullability theo các tích hợp được hỗ trợ.

`kotlin-reflect` là một dependency runtime liên quan đến những khả năng đó. Nó không phải compiler plugin và không tự biến class Kotlin thành class có thể kế thừa.

Không mặc định Java reflection thuần cung cấp đầy đủ cùng một ngữ nghĩa metadata Kotlin. Khi dùng Kotlin với Spring Data, cần đưa reflection vào cấu hình theo yêu cầu của bộ phiên bản và tính năng đang sử dụng.

### 2.3. Coroutine core

Artifact:

```text
org.jetbrains.kotlinx:kotlinx-coroutines-core
```

Thư viện này cung cấp mô hình coroutine, scope, cancellation và Kotlin `Flow` cùng nhiều primitive liên quan.

Tuy nhiên, chỉ có coroutine core chưa đồng nghĩa đã có toàn bộ adapter từ Reactive Streams hoặc Reactor sang coroutine.

### 2.4. Cầu nối Reactive Streams

Artifact:

```text
org.jetbrains.kotlinx:kotlinx-coroutines-reactive
```

Nhóm tích hợp này phục vụ việc chuyển đổi giữa coroutine/Flow và các publisher theo Reactive Streams trong các API được cung cấp.

Nó không phải reactive driver cho MongoDB, R2DBC hay một store khác. Cầu nối ngôn ngữ không thay thế tầng truy cập dữ liệu.

### 2.5. Cầu nối Reactor

Artifact:

```text
org.jetbrains.kotlinx:kotlinx-coroutines-reactor
```

Thư viện này cung cấp tích hợp chuyên biệt với Reactor, chẳng hạn các extension chờ kết quả của `Mono` và builder coroutine cho các kiểu Reactor, theo API của phiên bản sử dụng.

Với đường tích hợp coroutine repository của Spring Data dựa trên hạ tầng reactive/Reactor, cần bảo đảm bộ dependency coroutine core, reactive và reactor đầy đủ theo yêu cầu của phiên bản. Không suy ra rằng chỉ thêm core là đủ vì compiler đã nhận ra `Flow`.

### 2.6. Bảng trách nhiệm

| Thành phần | Cung cấp | Không tự cung cấp |
| --- | --- | --- |
| Kotlin compiler/build plugin | Biên dịch mã Kotlin | Store implementation |
| `kotlin-stdlib` | Runtime và API nền tảng Kotlin | Reactive driver |
| `kotlin-reflect` | Reflection đặc thù Kotlin | Mở class final hoặc tạo transaction |
| `kotlinx-coroutines-core` | Coroutine và Flow | Mọi adapter Spring/Reactor |
| `kotlinx-coroutines-reactive` | Tích hợp Reactive Streams | Query engine của store |
| `kotlinx-coroutines-reactor` | Tích hợp Reactor/coroutine | Chuyển JPA blocking thành non-blocking |
| Spring Data Commons | Abstraction repository và tích hợp dùng chung | Khả năng giống nhau cho mọi kho dữ liệu |
| Store module và driver | Thực thi mapping, truy vấn và I/O tương ứng | Tự bổ sung mọi tính năng ngoài hợp đồng của module |

## 3. Một cấu hình dependency cần thể hiện giả định rõ ràng

Ví dụ dưới đây chọn **Spring Data MongoDB reactive** làm store và dùng Kotlin coroutine. Đây là một cấu hình minh họa theo hướng Spring Boot, không phải danh sách bắt buộc cho mọi module.

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
    </dependency>

    <dependency>
        <groupId>org.jetbrains.kotlin</groupId>
        <artifactId>kotlin-stdlib</artifactId>
    </dependency>

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
        <artifactId>kotlinx-coroutines-reactive</artifactId>
    </dependency>

    <dependency>
        <groupId>org.jetbrains.kotlinx</groupId>
        <artifactId>kotlinx-coroutines-reactor</artifactId>
    </dependency>
</dependencies>
```

Giả định của đoạn XML:

1. Dự án đã dùng parent/BOM hoặc cơ chế dependency management quản lý được các phiên bản tương thích trong ví dụ.
2. Kotlin compiler và bước biên dịch đã được cấu hình riêng.
3. Ứng dụng đã có cấu hình kết nối MongoDB và phát hiện repository phù hợp.
4. Không có override hoặc exclusion làm mất một thành phần cần thiết.

Đây không phải một `pom.xml` hoàn chỉnh. Nếu không có dependency management phù hợp, không được bỏ version rồi kỳ vọng công cụ build tự chọn đúng bộ thư viện.

Starter có thể kéo nhiều thành phần bắc cầu. Việc liệt kê rõ các dependency tính năng trong ví dụ giúp công bố nhu cầu của ứng dụng; không có nghĩa mọi ứng dụng luôn phải lặp lại toàn bộ dependency mà starter đã quản lý.

Với R2DBC, cần chọn starter/module R2DBC và driver R2DBC của cơ sở dữ liệu tương ứng. Driver JDBC không tự thay thế driver R2DBC. Với JPA hoặc Spring Data JDBC thông thường, phải đánh giá đường blocking của chúng thay vì thay tên starter rồi giữ nguyên mọi giả định coroutine reactive.