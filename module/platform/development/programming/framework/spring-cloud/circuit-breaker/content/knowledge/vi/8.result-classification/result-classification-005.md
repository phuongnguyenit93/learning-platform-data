# Đánh giá kết quả trả về bằng predicate khi phiên bản hỗ trợ

Trong nhiều hệ thống, một lời gọi đến dependency có thể trả về HTTP response hoặc một đối tượng kết quả hợp lệ về mặt kỹ thuật nhưng mang ý nghĩa nghiệp vụ không thành công. Ví dụ, dịch vụ đối tác trả HTTP 503 trong một response object, API thanh toán trả trạng thái TEMPORARY_UNAVAILABLE, hoặc dịch vụ tồn kho trả một kết quả thể hiện dữ liệu chưa thể cung cấp.

Nếu lời gọi kết thúc bình thường và trả về một giá trị, Circuit Breaker thường xem đó là thành công. Tuy nhiên, trong một số phiên bản và API của Resilience4j, có thể dùng **result predicate** để đánh giá chính giá trị trả về. Predicate quyết định kết quả nào cần được ghi nhận là thất bại dựa trên nội dung của đối tượng kết quả.

Cần phân biệt result predicate với exception predicate. Result predicate kiểm tra giá trị được trả về; exception predicate phân loại lỗi được ném ra. Result predicate chỉ thay đổi cách Circuit Breaker ghi nhận phép đo, không tự biến response thành exception, không thay thế response và không tự kích hoạt fallback. Khả năng cấu hình qua YAML hoặc qua adapter reactive còn phụ thuộc phiên bản Resilience4j và Spring Cloud CircuitBreaker đang sử dụng.

## 1. Vì sao cần đánh giá giá trị trả về?

Mặc định, Circuit Breaker phân loại một lần gọi dựa trên việc thao tác hoàn tất bình thường hay phát sinh exception. Cách này phù hợp với phần lớn lời gọi mạng: lỗi kết nối, timeout hoặc exception từ client thường là tín hiệu thất bại.

Nhưng đôi khi client nhận được response hợp lệ mà nội dung response cho biết dependency không thể phục vụ yêu cầu. Ví dụ:

~~~java
public record PartnerResponse(int statusCode, String message) {
}
~~~

Một lời gọi có thể trả về:

| HTTP status | Kết quả từ client | Ý nghĩa vận hành |
|---|---|---|
| 200 | PartnerResponse(200, "OK") | Lời gọi thành công |
| 404 | PartnerResponse(404, "Not found") | Có thể là kết quả nghiệp vụ bình thường |
| 429 | PartnerResponse(429, "Rate limited") | Dependency hoặc quota đang giới hạn lưu lượng |
| 503 | PartnerResponse(503, "Unavailable") | Dependency tạm thời không thể phục vụ |

Nếu tất cả các response trên đều được trả về bình thường, Circuit Breaker có thể xem chúng là thành công. Khi đó, tỷ lệ lỗi thống kê không phản ánh đúng tình trạng dependency. Result predicate cho phép xác định một số giá trị response cụ thể cần được ghi nhận là thất bại.

Không nên mặc định mọi mã HTTP khác 2xx đều là lỗi hạ tầng. 404 có thể là kết quả nghiệp vụ hợp lệ; 409 có thể biểu thị xung đột do yêu cầu; 429 hoặc 503 thường là tín hiệu cần điều tra về tải hoặc khả năng phục vụ. Quy tắc phân loại phải phù hợp với hợp đồng API và ý nghĩa của nghiệp vụ.

## 2. Result predicate hoạt động như thế nào?

Predicate là một hàm nhận một giá trị và trả về boolean. Với API cấu hình hỗ trợ result predicate, Resilience4j dùng kết quả của hàm để quyết định phép đo của lời gọi được ghi nhận là thành công hay thất bại.

Quy tắc khái quát:

- Predicate trả về **true**: kết quả được ghi nhận là thất bại.
- Predicate trả về **false**: kết quả được ghi nhận là thành công.
- Lời gọi ném exception: được xử lý theo chính sách phân loại exception, không đi qua result predicate như một response bình thường.

Ví dụ, chỉ coi response có status từ 500 trở lên là thất bại:

~~~java
Predicate<Object> recordServerErrors = result ->
        result instanceof PartnerResponse response
                && response.statusCode() >= 500;
~~~

Với response status 200, predicate trả về false. Với response status 503, predicate trả về true. Với một kiểu kết quả không phải PartnerResponse, biểu thức instanceof trả về false.

Luồng xử lý khái quát:

~~~mermaid
flowchart TD
    A[Lời gọi dependency] --> B{Kết thúc thế nào?}
    B -- Ném exception --> C[Phân loại bằng exception policy]
    B -- Trả về giá trị --> D{Result predicate được hỗ trợ?}
    D -- Không --> E[Áp dụng quy tắc mặc định của API]
    D -- Có --> F[Đánh giá giá trị trả về]
    F -- true --> G[Ghi nhận là thất bại]
    F -- false --> H[Ghi nhận là thành công]
    C --> I[Cập nhật thống kê Circuit Breaker]
    G --> I
    H --> I
    E --> I
~~~

Result predicate tham gia vào việc ghi nhận kết quả của lần gọi. Sau khi phép đo được cập nhật, Circuit Breaker tính failure rate và slow call rate theo sliding window, rồi có thể chuyển trạng thái nếu ngưỡng cấu hình đã đạt.

## 3. Cấu hình result predicate bằng Java khi API hỗ trợ

Resilience4j có API cấu hình chương trình cho CircuitBreakerConfig với phương thức **recordResult(Predicate<Object>)** ở các phiên bản cung cấp tính năng này.

Ví dụ:

~~~java
import java.time.Duration;
import java.util.function.Predicate;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

public class PartnerCircuitBreakerConfiguration {

    public CircuitBreakerConfig createConfig() {
        Predicate<Object> recordServerErrors = result ->
                result instanceof PartnerResponse response
                        && response.statusCode() >= 500;

        return CircuitBreakerConfig.custom()
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(10))
                .recordResult(recordServerErrors)
                .build();
    }
}
~~~

Đoạn code minh họa cách tạo cấu hình trực tiếp từ builder. Kiểu enum và chữ ký API cần khớp với phiên bản Resilience4j được quản lý trong dự án; hãy kiểm tra Javadoc hoặc API của dependency thực tế trước khi sử dụng.

Khi tích hợp với Spring Cloud CircuitBreaker, có thể cung cấp CircuitBreakerConfig đã tạo thông qua cơ chế cấu hình hoặc customizer của implementation Resilience4j tương ứng. Cách đăng ký cụ thể phụ thuộc phiên bản Spring Cloud và starter đang dùng. Mục tiêu là bảo đảm factory sử dụng cấu hình có result predicate cho đúng ID instance.

Nếu phiên bản đang dùng không có **recordResult**, không nên cố gọi một method không tồn tại hoặc cho rằng một thuộc tính YAML chưa được binder hỗ trợ sẽ tự hoạt động. Khi đó, có thể chuyển kết quả nghiệp vụ cần coi là lỗi thành exception trước khi kết quả đi qua Circuit Breaker; cách này sử dụng chính sách phân loại exception phổ biến hơn.

## 4. Cấu hình predicate qua application.yml khi binder hỗ trợ

Một số phiên bản của tích hợp Spring Boot Resilience4j có thể cho phép cấu hình predicate bằng tên lớp triển khai thông qua thuộc tính **recordResultPredicate**. Khả năng bind thuộc tính này phụ thuộc phiên bản. Cần xác nhận tài liệu và metadata cấu hình của đúng phiên bản đang chạy trước khi sử dụng.

Nếu binder hỗ trợ, cấu hình có dạng khái quát:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      partner:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        recordResultPredicate: com.example.resilience.RecordPartnerResultAsFailure
~~~

Lớp predicate cần triển khai interface mà phiên bản binder yêu cầu. Ví dụ minh họa một predicate kiểm tra response:

~~~java
package com.example.resilience;

import java.util.function.Predicate;

public class RecordPartnerResultAsFailure
        implements Predicate<Object> {

    @Override
    public boolean test(Object result) {
        if (!(result instanceof PartnerResponse response)) {
            return false;
        }

        return response.statusCode() >= 500;
    }
}
~~~

Tên package, constructor và interface cần phù hợp với cơ chế khởi tạo predicate của phiên bản đang dùng. Nếu binder không hỗ trợ thuộc tính này, cấu hình YAML có thể bị bỏ qua hoặc không được ánh xạ như mong muốn. Không nên suy luận rằng mọi phiên bản Spring Cloud CircuitBreaker đều hỗ trợ **recordResultPredicate** chỉ vì Resilience4j core có API **recordResult**.

Một cách kiểm tra thực tế là khởi động ứng dụng với cấu hình, quan sát log binding và kiểm thử một response mà predicate phải đánh dấu thất bại. Chỉ xem file YAML không đủ để xác nhận predicate đã được đăng ký vào Circuit Breaker.

## 5. Phân biệt result predicate và exception predicate

Hai loại predicate xử lý hai loại đầu vào khác nhau:

| Tiêu chí | Result predicate | Exception predicate |
|---|---|---|
| Đầu vào | Giá trị được trả về | Throwable được ném ra |
| Mục đích | Đánh giá response có mang ý nghĩa thất bại hay không | Đánh giá exception có cần tính là thất bại hay bỏ qua |
| Ví dụ | Response có status 503 | TimeoutException hoặc IOException |
| API core thường gặp | recordResult(Predicate<Object>) | recordException(Predicate<Throwable>) |
| Có thay đổi giá trị trả về không? | Không | Không |
| Có tự tạo fallback không? | Không | Không |

Ví dụ kết hợp hai chính sách ở cấp cấu hình core:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .recordResult(result ->
                result instanceof PartnerResponse response
                        && response.statusCode() >= 500)
        .recordException(error ->
                error instanceof java.io.IOException
                        || error instanceof java.util.concurrent.TimeoutException)
        .build();
~~~

Đoạn code trên minh họa ý tưởng phân loại độc lập. Nếu sử dụng **recordException** tùy biến, cần xem lại quy tắc mặc định và cấu hình ignore exception của phiên bản Resilience4j đang dùng. Một exception bị bỏ qua sẽ không được tính như một lần gọi thành công để làm giảm failure rate.

Không nên dùng result predicate để thay thế exception predicate. Nếu WebClient ném WebClientResponseException cho response HTTP lỗi, Circuit Breaker nhận exception chứ không nhận PartnerResponse. Khi đó, exception policy mới là nơi phân loại lỗi, trừ khi ứng dụng chuyển lỗi thành một giá trị response trước khi gọi Circuit Breaker.

## 6. Predicate chỉ phân loại thống kê, không tự biến kết quả thành lỗi cho caller

Đây là điểm dễ gây nhầm lẫn. Khi result predicate trả về true, Resilience4j ghi nhận kết quả đó là thất bại trong thống kê Circuit Breaker. Điều này không đồng nghĩa response ban đầu tự động bị thay thế bằng exception hoặc fallback.

Ví dụ, nếu lời gọi trả PartnerResponse với status 503 và predicate đánh dấu là thất bại, caller vẫn có thể nhận được chính PartnerResponse đó. Circuit Breaker đã ghi nhận một phép đo thất bại, nhưng response không nhất thiết bị đổi thành lỗi.

Result predicate không thực hiện các hành động sau:

- Không tự ném exception cho caller.
- Không tự chuyển response thành một kiểu dữ liệu khác.
- Không tự gọi fallback của Spring Cloud CircuitBreaker chỉ vì predicate trả true.
- Không tự retry lời gọi.
- Không tự thay đổi HTTP status trả về cho client cuối.

Nếu nghiệp vụ yêu cầu response 503 phải chuyển thành exception để fallback được gọi, cần chuyển đổi response thành lỗi một cách tường minh trước khi đi qua Circuit Breaker, hoặc xử lý sau lời gọi theo thiết kế phù hợp.

Ví dụ chuyển response lỗi thành exception:

~~~java
Mono<PartnerResponse> remoteCall = webClient.get()
        .uri("/partner")
        .exchangeToMono(response ->
                response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .map(body -> new PartnerResponse(
                                response.statusCode().value(),
                                body))
        )
        .flatMap(result -> {
            if (result.statusCode() >= 500) {
                return Mono.error(
                        new PartnerUnavailableException(result.message()));
            }
            return Mono.just(result);
        });

return circuitBreaker.run(
        remoteCall,
        error -> fallbackPartnerResponse()
);
~~~

Trong ví dụ này, status từ 500 trở lên được chuyển thành exception. Reactive Circuit Breaker có thể xử lý exception theo cơ chế fallback của publisher. Đây là cách xử lý luồng reactive bằng exception; không nên nhầm nó với việc result predicate của API đồng bộ được tự động áp dụng cho mọi phần tử Mono hoặc Flux.

## 7. Cẩn trọng với WebClient và response status

WebClient có nhiều cách xử lý HTTP response. Với **retrieve()**, các response 4xx và 5xx mặc định được chuyển thành lỗi WebClientResponseException, trừ khi ứng dụng tùy chỉnh cách xử lý status.

Ví dụ:

~~~java
Mono<PartnerResponse> result = webClient.get()
        .uri("/partner")
        .retrieve()
        .bodyToMono(PartnerResponse.class);
~~~

Trong trường hợp này, nếu server trả 503, publisher thường phát lỗi thay vì phát một PartnerResponse có statusCode bằng 503. Result predicate không nhận được response đó như một giá trị bình thường.

Nếu muốn đánh giá status như một giá trị, có thể dùng **exchangeToMono** hoặc một cơ chế mapping response phù hợp để chuyển status và body thành kiểu kết quả nghiệp vụ. Sau đó, tùy adapter và phiên bản, phải xác minh Circuit Breaker có thực sự áp dụng result predicate cho kiểu thực thi đó hay không.

Đối với reactive adapter, không nên mặc định rằng result predicate của CircuitBreakerConfig sẽ đánh giá từng phần tử **onNext** của Flux hoặc giá trị **onNext** của Mono. Một số adapter reactive ghi nhận thành công khi publisher hoàn tất và thất bại khi publisher phát **onError**; việc đánh giá từng giá trị trả về có thể không được hỗ trợ giống API đồng bộ. Nếu cần phân loại response trong luồng reactive, cách rõ ràng và dễ kiểm soát là chuyển response nghiệp vụ cần coi là lỗi thành exception trước khi đưa publisher vào **ReactiveCircuitBreaker.run**.

## 8. Thiết kế predicate theo ý nghĩa nghiệp vụ

Predicate nên ngắn, xác định và ổn định. Tránh viết quy tắc dựa trên chuỗi message không ổn định hoặc dữ liệu có thể thay đổi theo ngôn ngữ.

Ví dụ, với response của dịch vụ thanh toán:

~~~java
Predicate<Object> recordPaymentFailure = result ->
        result instanceof PaymentResponse response
                && (response.status() == PaymentStatus.TEMPORARY_UNAVAILABLE
                    || response.status() == PaymentStatus.PROCESSING_ERROR);
~~~

Một số nguyên tắc khi thiết kế:

- Chỉ phân loại các kết quả thể hiện dependency không thể phục vụ hoặc đang suy giảm.
- Không coi lỗi nghiệp vụ bình thường như không tìm thấy sản phẩm hoặc từ chối giao dịch là lỗi hạ tầng nếu hợp đồng API xác định chúng là kết quả hợp lệ.
- Không dùng nội dung message tự do làm tiêu chí chính nếu response đã có status code hoặc enum ổn định.
- Xử lý an toàn kiểu dữ liệu không mong đợi và giá trị null.
- Giữ predicate thuần, không gọi mạng, truy vấn cơ sở dữ liệu hoặc thực hiện thao tác có side effect.
- Không ghi log toàn bộ body hoặc dữ liệu nhạy cảm trong predicate.
- Viết tài liệu cho từng quy tắc để nhóm vận hành hiểu vì sao một response bị tính là thất bại.

Một predicate không nên phụ thuộc vào trạng thái thay đổi bên ngoài như biến toàn cục hoặc kết quả gọi dịch vụ khác. Nếu việc đánh giá kết quả cần thêm dữ liệu nghiệp vụ, hãy chuẩn hóa dữ liệu đó vào response hoặc chuyển logic phân loại thành một bước xử lý rõ ràng trước Circuit Breaker.

## 9. Ảnh hưởng đến sliding window và trạng thái Circuit Breaker

Khi result predicate đánh dấu một response là thất bại, phép đo thất bại đó tham gia vào thống kê cửa sổ. Nếu failure rate đạt ngưỡng và đã đủ minimumNumberOfCalls, Circuit Breaker có thể chuyển từ CLOSED sang OPEN.

Ví dụ:

- slidingWindowSize là 10 lời gọi gần nhất.
- minimumNumberOfCalls là 5.
- failureRateThreshold là 50%.
- Có 5 lời gọi đã được ghi nhận, trong đó 3 response được predicate đánh dấu là thất bại.

Failure rate là:

\[
\frac{3}{5}\times100\%=60\%
\]

Tỷ lệ 60% vượt ngưỡng 50%, vì vậy Circuit Breaker có thể mở mạch. Response của lần gọi thứ năm vẫn có thể được trả cho caller theo cách thực thi bình thường; quyết định chuyển trạng thái ảnh hưởng đến các lời gọi tiếp theo.

Cũng cần theo dõi slow call rate. Một response được predicate đánh dấu thành công vẫn có thể là lời gọi chậm nếu thời gian thực thi vượt **slowCallDurationThreshold**. Ngược lại, một response được predicate đánh dấu thất bại không nhất thiết phải chậm.

## 10. Kiểm thử predicate và quan sát vận hành

Predicate là logic phân loại quan trọng, nên cần kiểm tra với cả kết quả được xem là thành công và kết quả được xem là thất bại.

Bảng tình huống kiểm thử ví dụ:

| Đầu vào | Predicate mong đợi | Kết quả thống kê |
|---|---:|---|
| PartnerResponse status 200 | false | Thành công |
| PartnerResponse status 404 | false theo chính sách ví dụ | Thành công |
| PartnerResponse status 429 | false theo chính sách ví dụ | Thành công, cần theo dõi riêng quota |
| PartnerResponse status 503 | true | Thất bại |
| Đối tượng kết quả khác kiểu | false | Thành công |
| IOException | Không gọi result predicate | Theo exception policy |

Bảng trên chỉ phản ánh predicate ví dụ coi response từ 500 trở lên là thất bại. Nếu hợp đồng API xác định 429 là tín hiệu dependency không thể phục vụ, cần thay đổi quy tắc tương ứng.

Nên theo dõi:

- Failure rate và số lời gọi bị predicate ghi nhận là thất bại.
- Số lượng response theo từng nhóm status nghiệp vụ.
- Số lần Circuit Breaker chuyển OPEN và HALF_OPEN.
- Số exception được ghi nhận hoặc bỏ qua.
- Số lần fallback thực tế.
- Chênh lệch giữa response được trả cho caller và kết quả thống kê của Circuit Breaker.

Để tránh dashboard gây hiểu nhầm, nên có metric nghiệp vụ riêng cho response status. Failure rate của Circuit Breaker không thay thế báo cáo HTTP status hoặc tỷ lệ giao dịch thành công của nghiệp vụ.

## 11. Các lỗi thường gặp

- **Cho rằng mọi response bình thường đều là thành công về nghiệp vụ**: response có thể mang trạng thái tạm thời không khả dụng dù không phát sinh exception.
- **Cho rằng result predicate tự gọi fallback**: predicate chỉ phân loại phép đo; muốn fallback cần lỗi hoặc cơ chế xử lý thay thế rõ ràng.
- **Nhầm result predicate với exception predicate**: một predicate nhận kết quả trả về, predicate kia nhận Throwable.
- **Cho rằng thuộc tính YAML luôn được hỗ trợ**: binder và adapter thay đổi theo phiên bản; phải kiểm tra đúng phiên bản.
- **Dùng result predicate cho reactive publisher mà không xác minh**: adapter có thể chỉ ghi nhận onComplete/onError, không đánh giá từng giá trị onNext.
- **Không xét hành vi mặc định của WebClient.retrieve()**: response 4xx/5xx thường trở thành exception, vì vậy result predicate có thể không nhận được đối tượng response.
- **Coi mọi status khác 2xx là lỗi hạ tầng**: 404 hoặc 409 có thể là kết quả nghiệp vụ bình thường.
- **Viết predicate có side effect**: gọi mạng hoặc truy vấn dữ liệu trong predicate làm tăng độ trễ và khiến việc phân loại khó dự đoán.
- **Không kiểm thử kiểu dữ liệu khác hoặc null**: predicate có thể phát sinh exception khi gặp kết quả ngoài dự kiến.

## 12. Quy trình áp dụng

Khi muốn đánh giá kết quả trả về bằng predicate trong Spring Cloud CircuitBreaker với Resilience4j, hãy thực hiện theo trình tự:

1. Xác định response nào là thành công về mặt kỹ thuật và nghiệp vụ.
2. Phân biệt response mang trạng thái lỗi với exception được client ném ra.
3. Kiểm tra phiên bản Resilience4j core có hỗ trợ **recordResult** và adapter đang dùng có áp dụng tính năng đó hay không.
4. Nếu dùng YAML, kiểm tra binder của phiên bản Spring Boot Resilience4j có hỗ trợ **recordResultPredicate**.
5. Viết predicate thuần, có kiểm tra kiểu dữ liệu và quy tắc rõ ràng.
6. Kiểm thử response thành công, response bị phân loại thất bại, exception và kiểu kết quả không mong đợi.
7. Xác minh failure rate, trạng thái Circuit Breaker và response thực tế mà caller nhận được.
8. Nếu API hoặc adapter không hỗ trợ result predicate, chuyển kết quả nghiệp vụ cần coi là lỗi thành exception trước Circuit Breaker và xử lý bằng exception policy/fallback.

Result predicate giúp Circuit Breaker đánh giá sâu hơn nội dung kết quả trả về khi phiên bản và API đang sử dụng hỗ trợ. Nó bổ sung cho chính sách phân loại exception, đồng thời ảnh hưởng đến failure rate trong sliding window. Khi hiểu rõ giới hạn của predicate, cách WebClient xử lý status và hành vi của adapter reactive, nhóm phát triển có thể phân loại đúng tình trạng dependency mà không nhầm lẫn giữa thống kê lỗi, response trả cho caller và cơ chế fallback.
