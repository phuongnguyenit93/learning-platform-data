# ReactiveFindByIndexNameSessionRepository và khả năng tra cứu phản ứng

Trong ứng dụng Spring WebFlux, một người dùng có thể đăng nhập trên nhiều trình duyệt hoặc thiết bị, vì vậy hệ thống đôi khi cần tìm tất cả phiên thuộc về một principal để hiển thị danh sách phiên đang hoạt động, giới hạn số phiên đồng thời hoặc thu hồi các phiên cũ. `ReactiveFindByIndexNameSessionRepository` cung cấp hợp đồng tra cứu phiên theo một chỉ mục và trả kết quả dưới dạng `Flux`, phù hợp với luồng xử lý reactive.

Spring Session có thể lưu phiên ở kho dùng chung để nhiều instance ứng dụng cùng truy cập. Ở tầng WebFlux, phiên được biểu diễn qua `WebSession`; repository reactive là lớp lưu trữ phía dưới. API tra cứu theo index cho phép tìm các phiên theo một giá trị như tên principal mà không buộc mã ứng dụng phải quét toàn bộ kho dữ liệu. Khả năng tra cứu thực tế phụ thuộc vào repository triển khai và các index mà repository đó hỗ trợ.

## 1. Vai trò của ReactiveFindByIndexNameSessionRepository

`ReactiveFindByIndexNameSessionRepository<S extends Session>` là một hợp đồng repository trong Spring Session. Nó mở rộng `ReactiveSessionRepository<S>` và bổ sung phương thức tìm phiên theo tên index và giá trị index:

```java
Flux<S> findByIndexNameAndIndexValue(String indexName, String indexValue);
```

Hai tham số có ý nghĩa như sau:

- `indexName` xác định loại dữ liệu được dùng làm khóa tra cứu, ví dụ chỉ mục tên principal.
- `indexValue` là giá trị cần tìm trong chỉ mục, ví dụ username đã chuẩn hóa của người dùng.

Kết quả là `Flux<S>` vì một principal có thể gắn với nhiều phiên. Nếu không có phiên phù hợp, publisher hoàn tất mà không phát phần tử nào. Đây là một luồng dữ liệu có thể có không, một hoặc nhiều phần tử, không phải một `Mono` chứa duy nhất một phiên.

Repository reactive cơ bản còn cung cấp các thao tác vòng đời phiên qua `ReactiveSessionRepository`, thường gồm tạo phiên, tìm theo ID, lưu và xóa theo ID. Có thể hình dung các trách nhiệm như sau:

| API | Mục đích | Kiểu kết quả reactive |
| --- | --- | --- |
| `createSession()` | Tạo một đối tượng phiên mới | `Mono<S>` |
| `findById(id)` | Tìm một phiên theo session ID | `Mono<S>` |
| `save(session)` | Lưu phiên hoặc cập nhật trạng thái phiên | `Mono<Void>` |
| `deleteById(id)` | Xóa phiên theo session ID | `Mono<Void>` |
| `findByIndexNameAndIndexValue(name, value)` | Tìm các phiên theo một chỉ mục | `Flux<S>` |

Tên và kiểu trả về cụ thể cần được đối chiếu với phiên bản Spring Session mà dự án sử dụng, nhưng điểm cốt lõi không đổi: API index trả về một luồng nhiều phiên và các thao tác repository được biểu diễn bằng publisher của Reactor.

Không nhầm `ReactiveFindByIndexNameSessionRepository` với `FindByIndexNameSessionRepository`. Hai interface có mục đích tương tự, nhưng bản blocking trả kết quả đồng bộ (thường là `Map<String, S>`), còn bản reactive trả `Flux<S>`. Ứng dụng Servlet truyền thống thường sử dụng API blocking; ứng dụng WebFlux cần repository reactive tương thích. Một repository JDBC blocking không tự trở thành reactive chỉ vì được gọi từ controller WebFlux. Hãy chọn implementation thực sự hỗ trợ reactive session.

## 2. Chỉ mục principal và tên index chuẩn

Trường hợp sử dụng phổ biến nhất là tìm tất cả phiên của một người dùng. Spring Session định nghĩa hằng số `PRINCIPAL_NAME_INDEX_NAME` trong `FindByIndexNameSessionRepository` để các thành phần dùng chung một tên index chuẩn:

```java
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.ReactiveFindByIndexNameSessionRepository;

repository.findByIndexNameAndIndexValue(
    FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
    principalName
);
```

Ví dụ, nếu `principalName` là `linh.nguyen`, repository trả về các phiên có principal index khớp với giá trị đó. Tên principal phải nhất quán giữa lúc lưu và lúc tra cứu. Nếu hệ thống chuẩn hóa username thành chữ thường khi xác thực, phần tra cứu cũng phải sử dụng cùng quy tắc; khác biệt về chữ hoa, chữ thường hoặc khoảng trắng có thể khiến kết quả rỗng.

Một index chỉ có ích khi repository biết cách xây dựng và duy trì index đó. Với Spring Security, khi `SecurityContext` được lưu trong phiên và implementation có resolver principal tương ứng, repository có thể suy ra tên principal từ ngữ cảnh bảo mật. Điều này phụ thuộc vào cấu hình và implementation cụ thể. Với cơ chế xác thực tùy biến, cần xác nhận principal thực sự được đưa vào index. Một cách phổ biến là lưu giá trị theo khóa chuẩn trước khi lưu phiên:

```java
session.setAttribute(
    FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
    principalName
);
```

Đoạn mã trên chỉ minh họa việc gắn giá trị principal vào phiên. Ứng dụng vẫn phải lưu phiên qua repository reactive và tuân theo cơ chế index của implementation. Không lưu mật khẩu, access token hoặc bí mật xác thực làm index value.

Interface nhận một `indexName` tổng quát, nhưng điều đó không có nghĩa mọi thuộc tính phiên đều tự động trở thành index. Ví dụ, việc thêm thuộc tính `department` vào session không bảo đảm có thể gọi `findByIndexNameAndIndexValue("department", "sales")`. Implementation phải hỗ trợ index đó và được cấu hình để tạo, cập nhật, xóa index tương ứng. Nếu cần index tùy chỉnh, hãy xem tài liệu của repository đang dùng và kiểm tra cách khai báo resolver/index trước khi xây dựng chức năng dựa trên nó.

## 3. Repository reactive và WebFlux

Trong Spring WebFlux, `WebSession` cung cấp phiên gắn với request. Spring Session tích hợp repository reactive để lưu trạng thái của phiên này vào kho dữ liệu dùng chung. Với Redis, cấu hình reactive thường sử dụng implementation hỗ trợ index như `ReactiveRedisIndexedSessionRepository` và cấu hình WebFlux tương ứng, chẳng hạn `@EnableRedisWebSession` khi ứng dụng tự cấu hình Spring Session. Spring Boot có thể cung cấp cấu hình tự động tùy dependency và phiên bản; không nên khai báo thêm một repository thủ công nếu ứng dụng đã có bean phù hợp.

Một số điểm cần xác minh khi cấu hình:

1. Ứng dụng đang chạy WebFlux và dùng loại session reactive (`WebSession`), không phải chỉ dùng `HttpSession` của Servlet.
2. Dependency và repository implementation thực sự triển khai `ReactiveFindByIndexNameSessionRepository`.
3. Các instance dùng cùng kho phiên, namespace và cấu hình serializer tương thích.
4. Principal index được tạo bởi resolver hoặc được ghi vào session theo quy ước của repository.
5. Security context được lưu vào WebSession nếu chức năng tra cứu dựa vào principal được xác thực.

Ví dụ sau minh họa một service phụ thuộc vào interface reactive thay vì phụ thuộc trực tiếp vào lớp Redis cụ thể. Kiểu `Session` cung cấp metadata cần thiết để dựng kết quả an toàn cho tầng API:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.List;

import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.ReactiveFindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class UserSessionQueryService {

    private final ReactiveFindByIndexNameSessionRepository<? extends Session>
            sessionRepository;

    public UserSessionQueryService(
            ReactiveFindByIndexNameSessionRepository<? extends Session> sessionRepository) {
        this.sessionRepository = sessionRepository;
    }

    public Mono<List<SessionSummary>> findSessions(String principalName) {
        return sessionRepository.findByIndexNameAndIndexValue(
                    FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                    principalName)
                .map(session -> new SessionSummary(
                        session.getId(),
                        session.getCreationTime(),
                        session.getLastAccessedTime(),
                        session.getMaxInactiveInterval()))
                .collectList();
    }

    public record SessionSummary(
            String id,
            Instant createdAt,
            Instant lastAccessedAt,
            Duration maxInactiveInterval) {
    }
}
```

Service chỉ chuyển những trường metadata cần thiết thành `SessionSummary`. Không nên trả toàn bộ đối tượng session hoặc tất cả session attributes ra API vì trong đó có thể chứa `SecurityContext`, dữ liệu nội bộ hay thông tin nhạy cảm. Trong hệ thống thực tế, có thể loại bỏ session ID khỏi response công khai hoặc chỉ cung cấp một định danh đã được kiểm soát nếu giao diện cần chọn phiên để thu hồi.

Controller WebFlux có thể lấy principal hiện tại từ request rồi gọi service:

```java
@RestController
@RequestMapping("/api/me/sessions")
class MySessionsController {

    private final UserSessionQueryService sessionQueryService;

    MySessionsController(UserSessionQueryService sessionQueryService) {
        this.sessionQueryService = sessionQueryService;
    }

    @GetMapping
    Mono<List<UserSessionQueryService.SessionSummary>> list(Mono<Principal> principal) {
        return principal.flatMap(current ->
                sessionQueryService.findSessions(current.getName()));
    }
}
```

Endpoint này phải được bảo vệ bởi Spring Security để chỉ người đã xác thực mới truy vấn được. Quan trọng hơn, service nhận principal từ ngữ cảnh bảo mật của request. Nếu endpoint cho phép truyền username tùy ý từ query parameter mà không kiểm tra quyền, người gọi có thể dò hoặc đọc thông tin phiên của tài khoản khác.

## 4. Tính chất của Flux và cách xử lý kết quả

`Flux<S>` là publisher nhiều phần tử. Nó mô tả một phép tính reactive; truy vấn thường chỉ được thực thi khi có subscriber đăng ký. Vì vậy, gọi phương thức repository rồi bỏ publisher đi sẽ không tạo ra kết quả hữu ích. Cần trả publisher cho WebFlux hoặc kết hợp nó với một pipeline reactive khác.

Các phép toán Reactor thường dùng khi làm việc với kết quả tra cứu:

| Toán tử | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| `map` | Chuyển từng session thành DTO hoặc giá trị khác | Ẩn chi tiết repository khỏi API |
| `filter` | Giữ các phần tử thỏa điều kiện | Lọc bổ sung khi điều kiện không có index hỗ trợ |
| `take(n)` | Chỉ nhận tối đa `n` phần tử đầu tiên | Giới hạn kết quả hoặc tải xử lý |
| `collectList()` | Thu toàn bộ phần tử thành `Mono<List<T>>` | Danh sách dự kiến nhỏ và cần response dạng mảng |
| `next()` | Lấy phần tử đầu tiên rồi hoàn tất | Chỉ khi nghiệp vụ thực sự cần một kết quả |
| `flatMap` | Chuyển từng phần tử thành một publisher khác | Gọi repository để xử lý từng session |
| `then()` | Bỏ các giá trị phát ra, chỉ chờ hoàn tất | Hoàn thành một chuỗi thao tác không cần trả dữ liệu |

Không nên mặc định dùng `collectList()` cho tài khoản có thể có số lượng phiên rất lớn. Toán tử này giữ tất cả phần tử trong bộ nhớ cho tới khi luồng hoàn tất. Nếu nghiệp vụ chỉ cần số lượng giới hạn, dùng `take(n)` hoặc thiết kế API phân trang dựa trên khả năng của repository. `ReactiveFindByIndexNameSessionRepository` không tự đảm bảo có cursor hay phân trang theo trang; không tự tạo phân trang bằng cách giả định `Flux` có thứ tự ổn định.

Không giả định kết quả được sắp xếp theo thời gian đăng nhập hoặc thời điểm truy cập. Nếu giao diện cần thứ tự, hãy xác định rõ trường sắp xếp và thực hiện theo cơ chế mà implementation hỗ trợ; với tập kết quả nhỏ có thể thu thập rồi sắp xếp ở tầng ứng dụng. Nếu cần thứ tự và phân trang cho tập dữ liệu lớn, nên chọn kho hoặc mô hình index hỗ trợ trực tiếp yêu cầu đó.

Tránh gọi `.block()` trong controller hoặc service chạy trên event-loop của WebFlux. `block()` biến lời gọi reactive thành chờ đồng bộ, có thể làm nghẽn luồng xử lý và phá vỡ lợi ích của mô hình non-blocking. Hãy trả `Mono`/`Flux` từ tầng service tới WebFlux hoặc kết hợp bằng các toán tử Reactor. Nếu bắt buộc tích hợp thư viện blocking, cô lập nó trên scheduler phù hợp và kiểm soát số luồng; không biến repository blocking thành reactive bằng cách chỉ bọc lời gọi trong `Mono.just`.

## 5. Thu hồi nhiều phiên theo principal

Tra cứu theo principal thường được dùng để đăng xuất các phiên khác khi người dùng đổi mật khẩu, yêu cầu đăng xuất mọi thiết bị hoặc quản trị viên thu hồi phiên bị nghi ngờ. Có thể kết hợp luồng tìm kiếm với thao tác xóa theo session ID:

```java
public Mono<Void> revokeAllSessions(String principalName) {
    return sessionRepository.findByIndexNameAndIndexValue(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                principalName)
            .concatMap(session -> sessionRepository.deleteById(session.getId()))
            .then();
}
```

Ví dụ dùng `concatMap` để thực hiện lần lượt thao tác xóa và chỉ hoàn tất khi các publisher xóa đã hoàn tất. Nếu số lượng phiên lớn và repository chịu được xử lý song song, có thể dùng `flatMap` với giới hạn concurrency phù hợp. Không mở concurrency không giới hạn chỉ vì API trả `Flux`.

Khi triển khai chức năng này, cần lưu ý:

- Xác định principal từ danh tính đã được xác thực hoặc từ quyền quản trị được kiểm tra rõ ràng. Không cho người dùng thông thường tùy ý chọn principal khác.
- Nếu chỉ muốn đăng xuất các thiết bị khác, cần nhận diện phiên hiện tại và loại phiên đó khỏi danh sách trước khi xóa.
- Xóa phiên trong kho chia sẻ để mọi instance đều nhìn thấy việc thu hồi ở request tiếp theo.
- Xử lý trường hợp phiên hết hạn hoặc bị xóa giữa lúc tra cứu và lúc xóa. Dữ liệu kết quả truy vấn chỉ là ảnh chụp tại thời điểm đọc.
- Ghi audit cho hành động thu hồi theo chính sách, nhưng không ghi session ID thô hoặc nội dung nhạy cảm của session attributes.

Xóa session bằng repository là thao tác ở tầng lưu trữ. Với phiên hiện tại của request WebFlux, cơ chế `WebSession.invalidate()` là cách diễn đạt ý định vô hiệu hóa phiên trong ngữ cảnh WebFlux. Hãy phối hợp với cấu hình Spring Security và xử lý cookie tương ứng để response đăng xuất hoàn chỉnh. Việc xóa bản ghi trong kho dữ liệu mà không xử lý response cookie có thể khiến trình duyệt tiếp tục gửi một ID cũ; server vẫn phải từ chối ID đó.

## 6. Index được duy trì như thế nào?

Index là cấu trúc phụ trợ để ánh xạ một giá trị như principal name tới một hoặc nhiều session ID. Khi session được tạo, cập nhật thuộc tính principal hoặc bị xóa/hết hạn, implementation phải duy trì cấu trúc này. Với Redis indexed repository, dữ liệu phiên và các cấu trúc index được quản lý trong Redis theo namespace của repository. Chi tiết key, TTL và cách dọn index là chi tiết triển khai; ứng dụng nên dùng API repository thay vì tự sửa key Redis nội bộ.

Một số nguyên tắc quan trọng:

1. **Index không thay thế session ID.** Dùng `findById` khi đã có ID; dùng tìm kiếm theo index khi chỉ biết giá trị principal hoặc một thuộc tính được hỗ trợ.
2. **Index không phải truy vấn tùy ý trên mọi attribute.** Chỉ các index được implementation hỗ trợ và cấu hình mới có thể tra cứu hiệu quả.
3. **Giá trị index phải nhất quán.** Principal name thay đổi cách chuẩn hóa hoặc cách ánh xạ giữa các instance có thể làm kết quả tra cứu không khớp.
4. **Vòng đời index gắn với vòng đời phiên.** Xóa phiên qua repository để implementation cập nhật dữ liệu index; tránh xóa key session trực tiếp trong Redis.
5. **Kết quả có thể thay đổi ngay sau khi đọc.** Phiên có thể hết hạn, bị thu hồi hoặc được cập nhật bởi request đồng thời trước khi service xử lý xong danh sách.

Nếu sử dụng nhiều ứng dụng chung một Redis, đặt namespace khác nhau cho từng ứng dụng hoặc môi trường để tránh xung đột key và index. Mọi instance của cùng một ứng dụng phải thống nhất namespace, cấu trúc dữ liệu và phiên bản tương thích trong quá trình rolling deployment. Khi nâng cấp Spring Session hoặc thay đổi cách serialize session, cần đánh giá khả năng đọc dữ liệu cũ và ảnh hưởng tới index trước khi triển khai đồng thời các phiên bản.

## 7. Xử lý lỗi và quan sát hoạt động

Trong reactive pipeline, lỗi từ repository được truyền thành tín hiệu `onError`. Có thể xử lý lỗi ở tầng phù hợp bằng `onErrorMap`, `onErrorResume` hoặc cơ chế xử lý lỗi tập trung của WebFlux. Không nên biến mọi lỗi kết nối Redis thành danh sách rỗng: làm vậy khiến hệ thống nhầm sự cố kho dữ liệu với trường hợp người dùng không có phiên.

Phân biệt các tình huống sau:

| Tình huống | Cách hiểu và xử lý |
| --- | --- |
| `Flux` hoàn tất mà không có phần tử | Không có phiên khớp index tại thời điểm tra cứu; trả danh sách rỗng nếu đó là hành vi nghiệp vụ mong muốn |
| Lỗi kết nối hoặc timeout kho dữ liệu | Đây là lỗi hạ tầng; ghi nhận, trả lỗi phù hợp và áp dụng retry có giới hạn nếu thao tác an toàn |
| Phiên hết hạn trong lúc xử lý | Bỏ qua hoặc xử lý theo nghiệp vụ; không coi snapshot cũ là trạng thái hiện tại |
| Không tìm thấy principal index | Kiểm tra giá trị principal, việc lưu SecurityContext, index resolver và khả năng index của repository |
| Chỉ một instance không tra cứu được | So sánh namespace, cấu hình repository, serializer và phiên bản ứng dụng giữa các instance |

Retry cần được dùng có chủ đích. Tra cứu đọc thường có thể retry giới hạn với backoff khi gặp lỗi tạm thời. Với chuỗi thao tác thu hồi nhiều phiên, cần xác định thao tác xóa có tính idempotent theo implementation và xử lý trường hợp một phần phiên đã bị xóa trước khi lỗi xảy ra. Không retry vô hạn hoặc che giấu lỗi để API báo thành công khi chưa biết trạng thái thực tế.

Các chỉ số hữu ích gồm thời gian truy vấn index, số session trả về, tỷ lệ truy vấn rỗng, lỗi/timeout repository, số phiên được thu hồi và độ trễ thao tác xóa. Log nên ghi loại index, mã tương quan và kết quả tổng quát; tránh ghi principal nhạy cảm hoặc session ID đầy đủ nếu chính sách bảo mật không cho phép. Khi cần điều tra một tài khoản cụ thể, dùng audit có kiểm soát quyền truy cập thay vì bật log toàn bộ session attributes.

## 8. Kiểm thử repository reactive

Kiểm thử nên bao phủ cả hợp đồng reactive và hành vi index của implementation thực tế. Một số trường hợp cơ bản:

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Principal có một phiên | `Flux` phát đúng phiên đó |
| Principal có nhiều phiên | Trả đủ các phiên thuộc principal |
| Principal chưa có phiên | `Flux` hoàn tất rỗng, không phát `null` |
| Hai principal khác nhau | Không trả chéo phiên giữa các tài khoản |
| Phiên bị xóa | Phiên không còn xuất hiện trong truy vấn index tiếp theo |
| Phiên hết hạn | Repository không trả phiên đã hết hạn theo chính sách implementation |
| Principal thay đổi hoặc index tùy chỉnh | Index cũ được cập nhật và tra cứu theo giá trị mới đúng quy ước |
| Lỗi kho dữ liệu | Lỗi được truyền hoặc chuyển đổi đúng, không bị giả thành kết quả rỗng |

Với Reactor Test, `StepVerifier` giúp kiểm tra publisher mà không cần gọi `block()`:

```java
StepVerifier.create(
        repository.findByIndexNameAndIndexValue(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                "linh.nguyen"))
    .expectNextMatches(session -> session.getId() != null)
    .verifyComplete();
```

Đoạn kiểm thử trên chỉ minh họa một phiên. Nếu kỳ vọng nhiều phiên, hãy kiểm tra số phần tử và định danh; nếu không có phiên, dùng `verifyComplete()` mà không yêu cầu `expectNext`. Dùng repository thật trong kiểm thử tích hợp (ví dụ Redis chạy bằng Testcontainers) để xác minh index, TTL và xóa phiên. Mock interface hữu ích cho kiểm thử service nhưng không chứng minh implementation đã tạo và dọn index đúng.

Đối với ứng dụng nhiều instance, tạo phiên hoặc đăng nhập qua instance A, sau đó truy vấn index qua instance B. Tiếp tục xóa phiên ở một instance và xác minh instance còn lại không tìm thấy phiên đó trong truy vấn tiếp theo. Kiểm thử này xác nhận dữ liệu index và session thực sự được chia sẻ thay vì chỉ tồn tại trong bộ nhớ của một tiến trình.

## 9. Lỗi thường gặp và cách chẩn đoán

**Truy vấn principal luôn trả về rỗng.** Xác minh ứng dụng đang dùng implementation có hỗ trợ index, đã lưu `SecurityContext` hoặc principal index, và đang truyền đúng `PRINCIPAL_NAME_INDEX_NAME`. So sánh chính xác giá trị principal được lưu với giá trị tìm kiếm. Nếu dùng xác thực tùy biến, kiểm tra resolver thay vì giả định repository tự biết username.

**Đã có phiên nhưng không tra cứu được bằng index tùy chỉnh.** Việc đặt một attribute tùy ý vào session không tự tạo index. Xem implementation có hỗ trợ index đó không và resolver có được cấu hình để trích xuất giá trị không. Nếu không, dùng index chuẩn có sẵn hoặc thiết kế repository/index riêng phù hợp với yêu cầu.

**Controller WebFlux bị treo hoặc độ trễ tăng.** Tìm các lời gọi `.block()`, thao tác JDBC/JPA blocking hoặc I/O đồng bộ trong event-loop. Trả publisher từ service và sử dụng client/repository reactive thực sự. Bọc một thao tác blocking bằng `Mono.just` không làm thao tác đó non-blocking.

**Tra cứu lúc có lúc không giữa các instance.** So sánh namespace, kết nối Redis, serializer, cấu hình index và phiên bản Spring Session. Xác nhận request đi tới các instance đang dùng chung kho phiên. Đừng chỉ dựa vào sticky session để che giấu cấu hình repository không đồng nhất.

**Thu hồi phiên chỉ có tác dụng trên một node.** Xác nhận thao tác xóa đi qua repository chia sẻ và session ID cũ không còn được chấp nhận ở node khác. Nếu chỉ xóa cookie ở một trình duyệt, các bản sao cookie khác vẫn có thể gửi ID cũ; cần thu hồi phía server.

**Tải tăng khi một principal có quá nhiều phiên.** Không thu toàn bộ phiên vào bộ nhớ nếu chỉ cần một phần kết quả. Giới hạn số phần tử, giới hạn concurrency khi thu hồi, theo dõi kích thước index và đặt chính sách giới hạn phiên phù hợp. Với nhu cầu phân trang hoặc truy vấn phức tạp, đánh giá khả năng của kho dữ liệu và thiết kế index chuyên biệt.

## 10. Checklist thiết kế

- Chọn API reactive cho WebFlux và API blocking cho Servlet stack tương ứng.
- Dùng `ReactiveFindByIndexNameSessionRepository` khi cần tra cứu nhiều phiên theo index; dùng `findById` khi đã có session ID.
- Dùng `FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME` cho principal index và bảo đảm giá trị principal được lưu nhất quán.
- Kiểm tra repository implementation có hỗ trợ index đang truy vấn; không giả định mọi session attribute đều có thể tìm kiếm.
- Xử lý `Flux` theo cách reactive, giới hạn việc thu thập toàn bộ kết quả và tránh `.block()` trên event-loop.
- Chỉ cho phép người dùng xem hoặc thu hồi phiên theo principal mà họ được phép quản lý.
- Dùng repository để xóa phiên nhằm duy trì index và xác minh thu hồi giữa nhiều instance.
- Kiểm thử trường hợp nhiều phiên, index rỗng, hết hạn, xóa, lỗi kho dữ liệu và truy vấn chéo instance.

Khi được cấu hình đúng, `ReactiveFindByIndexNameSessionRepository` giúp ứng dụng WebFlux tìm và quản lý tập phiên theo principal trong một pipeline non-blocking. Chất lượng của chức năng phụ thuộc vào việc repository duy trì index đúng, principal được ghi nhất quán và ứng dụng xử lý kết quả reactive cũng như lỗi kho dữ liệu một cách có kiểm soát.
