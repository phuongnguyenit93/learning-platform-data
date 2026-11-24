# Phân biệt tài liệu bản ổn định với preview và snapshot trong Spring Cloud Gateway

Một trang tài liệu Spring Cloud Gateway có thể mô tả bản **ổn định (stable/GA)**, bản **xem trước (preview)** hoặc bản **phát triển (snapshot)**. Ba nhãn này cho biết mức độ hoàn thiện và khả năng thay đổi của nội dung. Chọn sai nhánh tài liệu có thể khiến ứng dụng cấu hình route không hoạt động, dùng nhầm tên predicate/filter, tích hợp sai Spring Security hoặc đưa một hành vi chưa phát hành vào hệ thống production.

Bài học thuộc chủ đề **Phiên bản và biến thể**, tập trung vào cách đọc đúng tài liệu khi xây dựng API Gateway cho microservices. Các ví dụ liên hệ trực tiếp đến route predicate, filter chain, sửa đường dẫn/header, khám phá dịch vụ, xác thực, rate limiting, circuit breaker, retry, TLS và quan sát request.

## 1. Vì sao phải nhận diện loại tài liệu?

Giả sử một nhóm đang vận hành Gateway ổn định, có route đến dịch vụ đơn hàng, filter chuyển tiếp token và cơ chế giới hạn lưu lượng. Khi tìm kiếm cách cấu hình một filter mới, nhóm mở trang “latest” rồi sao chép ví dụ. Dự án vẫn biên dịch nhưng route trả về 404 hoặc thuộc tính cấu hình không được đọc. Nguyên nhân có thể là trang đang mô tả một nhánh phát triển khác với thư viện đang chạy.

Có **ba thứ cần phân biệt**:

1. **Phiên bản thư viện đang chạy**: artifact Spring Cloud Gateway thực tế được Maven/Gradle giải quyết và đóng gói vào ứng dụng.
2. **Nhánh tài liệu đang đọc**: stable, preview hay snapshot; có thể khác hẳn thư viện thực tế.
3. **Biến thể Gateway**: chẳng hạn Gateway Server WebFlux và Gateway Server MVC. Hai biến thể có cách cấu hình, cơ chế xử lý request và khả năng tích hợp khác nhau; nhãn stable không làm cho ví dụ của biến thể này tự động dùng được cho biến thể kia.

Vì vậy, một bài viết được gắn “stable” vẫn có thể **không phù hợp** nếu nó thuộc dòng Gateway mới hơn hoặc thuộc biến thể khác với dự án.

## 2. Stable, preview và snapshot có nghĩa gì?

| Tiêu chí | Stable / GA | Preview (milestone, RC, bản xem trước) | Snapshot |
|---|---|---|---|
| Ý nghĩa | Phiên bản đã được phát hành chính thức (General Availability) | Phiên bản phát hành trước GA để trải nghiệm và kiểm chứng | Bản dựng trong quá trình phát triển, thường từ nhánh mã chưa phát hành |
| Ký hiệu thường gặp | X.Y.Z, ví dụ 4.2.2 | X.Y.Z-M1, X.Y.Z-RC1 hoặc nhãn preview | X.Y.Z-SNAPSHOT |
| Mức ổn định của API/cấu hình | Có cam kết phát hành cụ thể; thay đổi được ghi nhận theo release | Có thể còn điều chỉnh trước GA | Có thể thay đổi theo commit, bản dựng hoặc thời điểm |
| Khả năng lặp lại kết quả | Có thể khóa dependency vào phiên bản đã phát hành | Có thể khóa vào đúng mốc M/RC đã phát hành | Cùng một tọa độ SNAPSHOT có thể nhận bản dựng khác nhau theo thời gian |
| Nguồn artifact thường gặp | Kho release như Maven Central | Kho milestone/release candidate, tùy cách dự án phát hành | Kho snapshot dành cho phát triển |
| Mục đích sử dụng tài liệu | Phát triển, nâng cấp và vận hành phiên bản tương ứng | Đánh giá thay đổi sắp ra mắt, thử nghiệm nâng cấp | Theo dõi tính năng đang làm, thử nghiệm hoặc đóng góp phát triển |
| Mức phù hợp cho production | Có thể dùng sau khi xét tương thích và vòng đời hỗ trợ | Thông thường không chọn nếu chưa có chính sách chấp nhận rủi ro rõ ràng | Không nên dùng làm nền tảng production thông thường |

**Stable không đồng nghĩa “mọi bản stable đều còn được hỗ trợ”.** Một phiên bản GA cũ có thể đã hết giai đoạn hỗ trợ bảo trì hoặc bảo mật. Phải kiểm tra chính sách hỗ trợ và release notes của đúng dòng phiên bản.

**Preview không phải một hậu tố phiên bản duy nhất.** Trang tài liệu có thể dùng chữ “preview” để chỉ nhánh tài liệu phát hành trước; artifact cụ thể có thể là milestone (M), release candidate (RC), hoặc một tính năng được đánh dấu thử nghiệm ngay trong bản GA. Cần đọc **phiên bản và trạng thái được ghi rõ trên trang**. Một bản RC là mốc phát hành cụ thể, không phải SNAPSHOT chỉ vì nó chưa GA.

**SNAPSHOT là tọa độ phát triển có thể thay đổi.** Với hệ sinh thái Maven, bản dựng snapshot có thể được lưu dưới tên timestamp riêng nhưng khi yêu cầu phụ thuộc X.Y.Z-SNAPSHOT, công cụ build có thể lấy bản mới hơn theo metadata/cơ chế cache. Tài liệu snapshot và artifact snapshot cũng không bảo đảm được xây từ cùng một commit.

> Các số phiên bản trong bài chỉ dùng để minh họa cách nhận diện nhãn; không khẳng định đó là bản stable/preview hiện hành tại thời điểm đọc.

## 3. Nhìn đúng “phiên bản” trong hệ sinh thái Spring

Ứng dụng Spring Cloud Gateway chịu ảnh hưởng của nhiều tầng phát hành:

| Tầng | Cần xác định gì? | Tại sao quan trọng? |
|---|---|---|
| Java và Spring Boot | Phiên bản JDK, Spring Boot | Điều kiện chạy, dependency nền và các thay đổi của framework |
| Spring Cloud release train | Phiên bản BOM spring-cloud-dependencies | Quản lý tập phiên bản tương thích giữa các dự án Spring Cloud |
| Spring Cloud Gateway | Phiên bản artifact Gateway thực tế | Quyết định API, filter, predicate và cấu hình có sẵn |
| Biến thể Gateway | Server WebFlux hay Server MVC | Quyết định cách thực thi và vị trí cấu hình phù hợp |
| Nhánh tài liệu | Stable/preview/snapshot và số phiên bản hiển thị | Quyết định đoạn hướng dẫn có được viết cho runtime trên hay không |

Spring Cloud sử dụng **release train** để quản lý nhiều thư viện liên quan. Do đó, số phiên bản BOM Spring Cloud **không nhất thiết trùng** với số phiên bản artifact Spring Cloud Gateway. Không được suy ra “Gateway phiên bản X” chỉ bằng cách nhìn tên release train; phải kiểm tra cây dependency hoặc dependency resolution thực tế.

Tương tự, hai tài liệu cùng ghi “stable” nhưng một trang dành cho **Gateway Server WebFlux** và trang kia dành cho **Gateway Server MVC** vẫn có thể khác về starter, package, đặc điểm request processing và cách khai báo route. Hãy xác định biến thể trước khi sao chép cấu hình.

## 4. Quy trình chọn tài liệu đúng

~~~mermaid
flowchart TD
    A["Xem phiên bản Gateway và biến thể thực tế"] --> B["Đối chiếu Spring Boot và Spring Cloud BOM"]
    B --> C{"Artifact đang dùng thuộc loại nào?"}
    C -->|"GA / release"| D["Mở tài liệu stable của đúng dòng phiên bản"]
    C -->|"Milestone / RC"| E["Mở tài liệu preview cùng mốc phát hành"]
    C -->|"SNAPSHOT"| F["Mở tài liệu snapshot và đối chiếu commit/build"]
    D --> G["Kiểm tra release notes, hỗ trợ và cấu hình"]
    E --> G
    F --> G
    G --> H["Thử route, filter và tích hợp trên môi trường kiểm thử"]
~~~

### Bước 1 — Xác định phiên bản từ dự án, không từ trình duyệt

Xem file build để biết dự án khai báo Spring Boot, Spring Cloud BOM và starter Gateway nào. Sau đó kiểm tra **dependency đã được giải quyết**, bởi dependency management hoặc dependency bắc cầu có thể khiến phiên bản chạy khác với suy nghĩ ban đầu.

Ví dụ lệnh kiểm tra (chọn công cụ build mà dự án sử dụng):

~~~bash
# Maven Wrapper: liệt kê dependency Spring Cloud đã giải quyết
./mvnw dependency:tree -Dincludes=org.springframework.cloud:*

# Gradle Wrapper: xem lý do chọn một dependency Gateway
./gradlew dependencyInsight --dependency spring-cloud-gateway --configuration runtimeClasspath
~~~

Nếu dự án có nhiều cấu hình hoặc module, chạy lệnh tại module thực sự đóng gói Gateway. Với Gradle, tên dependency và configuration cần đổi theo starter/biến thể được dùng; với Maven, đối chiếu thêm effective POM khi có kế thừa BOM phức tạp.

**Ghi lại tối thiểu**: Spring Boot, Spring Cloud BOM, artifact Gateway và phiên bản đã resolve, WebFlux/MVC, JDK. Đây là danh tính kỹ thuật để tìm đúng trang tài liệu.

### Bước 2 — Đọc version selector và đường dẫn trang

Trên tài liệu chính thức, hãy tìm phần chọn phiên bản, tiêu đề nhánh và URL. Một liên kết có chữ “latest”, “current”, “preview” hay “snapshot” **không đủ để kết luận** nó khớp phiên bản ứng dụng. Các alias như “current” có thể thay đổi đích sau một đợt phát hành.

Kiểm tra cùng lúc:

- Trang đang trình bày **số phiên bản nào**, ở trạng thái GA, M/RC hay snapshot?
- Đây là tài liệu **Gateway Server WebFlux** hay **Server MVC**?
- Trang có ghi “applies to”, “since”, “deprecated”, “removed” hoặc điều kiện hỗ trợ theo phiên bản không?
- Ví dụ sử dụng **tên starter, namespace cấu hình, predicate/filter** có hiện diện trong phiên bản mà dự án resolve không?
- Với trang snapshot: có thông tin nhánh, commit, ngày dựng docs hoặc dấu vết đủ để khớp với artifact thử nghiệm không?

Hãy lưu URL đã cố định theo phiên bản hoặc revision nếu có thể. Một bookmark trỏ tới alias “latest” không phải bằng chứng đủ để tái lập lần triển khai trước.

### Bước 3 — Đối chiếu release notes và bảng tương thích

Đối chiếu ghi chú phát hành của **Gateway**, release train của **Spring Cloud** và ma trận tương thích **Spring Boot ↔ Spring Cloud** ở thời điểm triển khai. Chú ý mục yêu cầu phiên bản Java, thay đổi configuration properties, deprecation, nâng cấp bảo mật và hành vi của filter. Không giả định rằng chỉ cần nâng một artifact Gateway độc lập là đủ.

Tài liệu là một nguồn hướng dẫn; **artifact, release notes và trạng thái hỗ trợ** giúp quyết định hướng dẫn đó có áp dụng được cho hệ thống đang chạy hay không.

### Bước 4 — Chạy smoke test sát với hành vi thật

Với gateway, kiểm tra tối thiểu các luồng mà dự án thực sự dùng: route predicate có match đúng không, filter có chạy theo thứ tự dự kiến không, đường dẫn/header khi đi qua gateway có đúng không, xác thực và phân quyền có từ chối request sai hay không. Nếu có sử dụng, bổ sung kiểm tra service discovery, giới hạn lưu lượng (429), circuit breaker/fallback, retry, TLS và tracing/metrics/logging.

Một ví dụ tài liệu có thể biên dịch thành công nhưng vẫn **không chứng minh** filter chain xử lý đúng trong runtime.

## 5. Ví dụ thực hành: ba trang gần giống nhau nhưng dành cho ba mục tiêu

Giả định một nhóm vận hành API Gateway bằng **Gateway 4.2.2 GA** trên một release train và Spring Boot đã được đối chiếu tương thích. Trong lúc tìm hướng dẫn route, nhóm thấy ba trang:

| Trang tìm thấy | Nhãn ví dụ | Quyết định |
|---|---|---|
| Tài liệu đúng dòng Gateway 4.2.x (stable) | 4.2.x | Ưu tiên để áp dụng cho hệ thống đang chạy, kiểm tra khác biệt patch nếu có |
| Tài liệu Gateway 5.0.0-M1 (preview) | 5.0.0-M1 | Chỉ dùng để đánh giá nâng cấp/lab; không sao chép mặc định vào hệ thống 4.2.2 |
| Tài liệu Gateway 5.0.0-SNAPSHOT | 5.0.0-SNAPSHOT | Chỉ tham khảo hành vi đang phát triển; xác minh commit và artifact trước khi thử |

Ví dụ route YAML dưới đây minh họa cú pháp thường gặp trong **một số dòng Gateway Server WebFlux 4.x**. Đây là ví dụ gắn ngữ cảnh phiên bản, **không phải đoạn cấu hình được cam kết hoạt động nguyên vẹn trên mọi nhánh WebFlux/MVC hoặc các bản mới hơn**:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: order-service
          uri: http://order-service:8080
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
~~~

Trong cấu hình minh họa này, predicate Path nhận đường dẫn bắt đầu bằng /api/orders/, sau đó StripPrefix=1 bỏ phân đoạn đầu của đường dẫn trước khi chuyển tiếp. Khi gọi GET /api/orders/42, dịch vụ đích được kỳ vọng nhận GET /orders/42 nếu không có filter hoặc proxy nào khác thay đổi đường dẫn.

**Nếu đọc nhầm tài liệu preview/snapshot**, người học có thể sao chép một tên thuộc tính hay cấu trúc dành cho nhánh mới, rồi quan sát thấy route không được tạo hoặc request đi sai đích. Cách chẩn đoán đúng là kiểm tra namespace cấu hình của **đúng phiên bản và đúng biến thể** trong tài liệu, metadata cấu hình được đóng gói cùng thư viện, log đăng ký route và kết quả smoke test. Không đoán cú pháp dựa vào việc cả hai trang đều có tiêu đề “Gateway”.

## 6. Những điểm dễ sai nhất khi đối chiếu tài liệu Gateway

### 6.1 Route predicate và filter chain

Tên factory, cách truyền tham số, thứ tự filter và default filter có thể khác giữa các nhánh. Khi cần RewritePath, StripPrefix, AddRequestHeader hay RemoveRequestHeader, hãy tìm trang của đúng phiên bản và xác nhận path đầu vào/đầu ra bằng request thử.

Đặc biệt, thứ tự thực thi filter có thể thay đổi kết quả xác thực, retry và biến đổi header. Một ví dụ trên preview không bảo đảm tương thích nhị phân hoặc ngữ nghĩa với stable cũ.

### 6.2 Xác thực, phân quyền và TLS

Tài liệu về Spring Security, OAuth2 Resource Server, Token Relay hoặc TLS thường có điều kiện riêng theo Spring Boot, Spring Security và biến thể Gateway. Cần đối chiếu các điều kiện này với release train, thay vì chỉ nhìn số phiên bản Gateway. Trong bản xem trước, phần API/bộ lọc có thể vẫn được chỉnh sửa; với snapshot, tài liệu có thể đã mô tả API chưa hiện diện trong binary bạn tải.

### 6.3 Rate limiter, circuit breaker, retry và discovery

Một mẫu RateLimiter, CircuitBreaker, Retry hoặc load-balanced URI phụ thuộc thêm vào thư viện tích hợp, hệ thống dữ liệu hoặc service discovery. Bản tài liệu ở nhánh khác có thể dùng phiên bản phụ thuộc khác. Sau khi chọn đúng tài liệu, xác nhận dependency bổ sung, điều kiện kích hoạt, giới hạn retry để tránh nhân đôi request và hành vi fallback khi service không sẵn sàng.

### 6.4 Quan sát request và vận hành

Tên metric/tag, cơ chế actuator endpoint, distributed tracing, access log và cấu hình quan sát có thể đổi qua các dòng Spring Boot/Spring Cloud. Trước khi đưa tài liệu vào runbook, kiểm tra metric/log thực tế từ artifact đang chạy. Trang snapshot không nên là nguồn duy nhất để đặt alert hoặc viết hướng dẫn xử lý sự cố production.

## 7. Khi nào nên dùng từng loại?

**Chọn stable** khi đang phát triển tính năng cho môi trường thực, xử lý lỗi, viết runbook, kiểm thử tương thích hoặc nâng cấp trong phạm vi phiên bản đã phát hành. Chọn đúng dòng artifact đang chạy; nếu dòng cũ đã hết hỗ trợ, lập kế hoạch nâng cấp thay vì mặc định dùng tài liệu stable mới nhất.

**Chọn preview** khi đánh giá breaking change, kiểm tra tính năng dự kiến sẽ ra trong phiên bản kế tiếp hoặc thử nghiệm kế hoạch nâng cấp. Tạo nhánh thử nghiệm riêng, ghi rõ milestone/RC, BOM tương ứng, điểm khác biệt so với stable và kết quả test. Khi GA được công bố, kiểm tra lại release notes và tài liệu GA vì nội dung preview có thể đã thay đổi.

**Chọn snapshot** khi cần kiểm chứng một sửa lỗi/chức năng chưa phát hành hoặc tái hiện một vấn đề theo commit. Ghi **commit hoặc timestamp build**, tọa độ dependency, repository sử dụng, ngày dựng tài liệu và kết quả test. Dùng cache/lock/pin phù hợp để giảm rủi ro bản dựng thay đổi giữa hai lần thử. Tránh đưa snapshot vào production theo cách tự động cập nhật không kiểm soát.

Đối với Maven/Gradle, artifact GA thường sẵn có qua kho release; artifact milestone hoặc snapshot có thể yêu cầu kho riêng được chỉ định trong hướng dẫn của đúng phiên bản. **Không thêm kho snapshot vào dự án production chỉ để một ví dụ từ trang snapshot có thể resolve dependency.**

## 8. Một bài kiểm tra chọn tài liệu có thể tái lập

Giả sử nhóm cần thêm rate limiting vào một gateway đang chạy ổn định. Quy trình thực hành:

1. **Chốt hiện trạng**: ghi phiên bản Gateway đã resolve, Boot, Cloud BOM, JDK và WebFlux/MVC; xác nhận gateway hiện đang nhận route qua cấu hình hoặc Java DSL nào.
2. **Mở tài liệu cùng dòng**: chọn rate limiter/filter reference cho đúng phiên bản stable và biến thể; không dùng kết quả tìm kiếm nếu trang được mở dẫn đến snapshot.
3. **Xác nhận phụ thuộc**: đọc yêu cầu thư viện tích hợp, backend lưu trữ nếu có và các điều kiện cấu hình được nêu trong tài liệu cùng dòng.
4. **Thử hành vi**: dựng route kiểm thử, gửi request dưới/trên giới hạn, xác nhận status code, header hoặc metric dự kiến và kiểm tra các trường hợp lỗi backend.
5. **Ghi bằng chứng**: lưu version và URL tài liệu đã đối chiếu, cấu hình dùng trong test, kết quả và phần cần kiểm tra lại khi nâng cấp.

Nếu đang khám phá một tính năng **chỉ xuất hiện trên preview**, ghi rõ “chưa có trong bản GA đang chạy”, dựng môi trường thử nghiệm có BOM tương thích và không đưa ví dụ đó vào hướng dẫn production hiện tại.

Có thể lưu biên bản nhỏ ngay trong tài liệu kỹ thuật của dự án:

~~~text
Runtime: Gateway <artifact + resolved version>, WebFlux hoặc MVC
Platform: Spring Boot <version>, Spring Cloud BOM <train>, JDK <version>
Docs: <URL nhánh và phiên bản cố định>
Loại docs: stable | preview (M/RC) | snapshot (commit/build)
Điểm đối chiếu: route, predicate/filter, security, observability
Kết quả thử nghiệm: <test case và kết quả>
Quyết định: áp dụng | thử nghiệm tiếp | chưa áp dụng
~~~

Các dấu ngoặc nhọn là chỗ điền thông tin, không phải tên phiên bản hay thuộc tính cấu hình thật.

## 9. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “Latest” luôn là bản nên chạy trên production | “Latest” có thể là alias của trang mới nhất hoặc nhánh phát triển; cần kiểm tra nhãn phiên bản và chính sách hỗ trợ |
| “Stable” nghĩa là tài liệu khớp mọi bản stable | Stable phải khớp **dòng phiên bản** và **biến thể** của artifact |
| Release train Spring Cloud và Gateway có cùng version | BOM quản lý nhiều artifact; xem dependency thực tế để biết version Gateway |
| Preview và snapshot là một | M/RC là mốc tiền phát hành định danh được; SNAPSHOT thường là bản dựng phát triển có thể thay đổi |
| Trang snapshot mới nhất chắc chắn khớp SNAPSHOT trong máy | Docs và artifact có thể được build từ thời điểm/commit khác nhau |
| Chạy qua một request là đủ chứng minh tương thích | Cần kiểm tra filter order, lỗi backend, bảo mật, rate limit và quan sát theo hành vi dự án dùng |
| Gateway WebFlux và Gateway MVC dùng chung mọi ví dụ | Mỗi biến thể có starter, môi trường thực thi và cấu hình riêng |
| Bản GA cũ vẫn được bảo trì vô thời hạn | Trạng thái GA và trạng thái còn được hỗ trợ là hai câu hỏi khác nhau |

## 10. Checklist trước khi sao chép một ví dụ từ tài liệu

- [ ] Tôi biết **artifact Gateway đã resolve**, release train Spring Cloud, Spring Boot và JDK.
- [ ] Tôi biết dự án đang dùng **Server WebFlux** hay **Server MVC**.
- [ ] Tôi đọc **nhãn phiên bản thực tế** của trang, không chỉ “latest/current”.
- [ ] Tôi đã phân loại trang là **GA**, **M/RC** hay **SNAPSHOT**.
- [ ] Tôi đã xem yêu cầu tương thích, release notes và trạng thái hỗ trợ tương ứng.
- [ ] Tôi đã đối chiếu starter, namespace cấu hình, tên predicate/filter và dependency bổ sung.
- [ ] Tôi đã thử request thành công và các tình huống lỗi/bảo mật/quan sát liên quan.
- [ ] Tôi lưu phiên bản cùng URL tài liệu cụ thể để người khác có thể kiểm tra lại.

## Nguồn chính thức để đối chiếu

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — bắt đầu tại tài liệu chính thức, sau đó chọn **đúng phiên bản và biến thể**.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — thông tin dự án và các điểm dẫn đến tài liệu/phát hành.
- [Spring Cloud project](https://spring.io/projects/spring-cloud) — release train, tương thích và vòng đời hỗ trợ.
- [Spring Boot project](https://spring.io/projects/spring-boot) — đối chiếu phiên bản Boot và nền tảng liên quan.

**Quy tắc cốt lõi:** trước khi áp dụng một dòng cấu hình Gateway, xác định **artifact thực chạy → biến thể → Spring Boot/Cloud BOM → nhánh tài liệu cùng phiên bản → thử nghiệm hành vi**. Stable là điểm xuất phát cho hệ thống đang vận hành; preview và snapshot có giá trị nghiên cứu nhưng đòi hỏi đối chiếu và kiểm chứng chặt chẽ hơn.
