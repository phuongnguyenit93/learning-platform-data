# Tính lũy đẳng và tác động khi gửi lại yêu cầu

Trong giao tiếp giữa các microservice, một request có thể được gửi lại khi client gặp timeout, mất kết nối hoặc nhận lỗi tạm thời. Spring Cloud LoadBalancer cũng có thể thử một instance khác khi chính sách retry được bật. Tuy nhiên, client thường không biết chắc request trước đã được server xử lý hay chưa. Nếu thao tác tạo đơn hàng hoặc thanh toán bị thực hiện hai lần, việc retry có thể gây ra dữ liệu trùng và tác động nghiệp vụ nghiêm trọng.

**Tính lũy đẳng (idempotency)** là thuộc tính giúp một thao tác có cùng kết quả nghiệp vụ cuối cùng dù được thực hiện một lần hay nhiều lần với cùng đầu vào. Đây là nền tảng để thiết kế API có thể retry an toàn. Bài học tập trung vào ngữ nghĩa HTTP, tình huống gửi lại request và cách triển khai idempotency key ở phía ứng dụng.

## 1. Tính lũy đẳng là gì?

Một thao tác được gọi là lũy đẳng nếu thực hiện nó nhiều lần tạo ra cùng trạng thái nghiệp vụ cuối cùng như thực hiện một lần. Có thể biểu diễn khái niệm này bằng:

\[
f(f(x)) = f(x)
\]

Trong đó, \(x\) là trạng thái ban đầu và \(f\) là thao tác. Nếu gọi thao tác thêm lần nữa trên trạng thái đã được cập nhật, trạng thái nghiệp vụ vẫn giữ nguyên.

Ví dụ:

- Đặt trạng thái đơn hàng thành **CANCELLED** là lũy đẳng nếu mọi lần gọi đều đưa đơn hàng về cùng trạng thái đó.
- Xóa một tài nguyên theo ID thường có tính lũy đẳng về mặt trạng thái: sau lần xóa đầu tiên, tài nguyên đã không còn tồn tại; lần xóa tiếp theo không làm trạng thái thay đổi thêm.
- Tăng số dư ví thêm 100.000 đồng không lũy đẳng: gọi hai lần làm số dư tăng 200.000 đồng.
- Tạo một đơn hàng mới thường không lũy đẳng: mỗi lần gọi có thể tạo thêm một đơn hàng.

Tính lũy đẳng nói về **tác động dự kiến lên trạng thái nghiệp vụ**, không yêu cầu mọi phản hồi HTTP phải giống hệt nhau. Ví dụ, lần DELETE đầu tiên có thể trả về 204 No Content, lần tiếp theo có thể trả về 404 Not Found vì tài nguyên đã bị xóa. Trạng thái cuối cùng vẫn giống nhau.

Một API lũy đẳng vẫn có thể ghi log, tăng bộ đếm giám sát hoặc lưu lịch sử từng lần gọi. Những hoạt động phụ này không làm thay đổi kết luận về tác động nghiệp vụ chính, nhưng cần được thiết kế để không tạo ra side effect ngoài ý muốn.

## 2. Phân biệt safe method và idempotent method trong HTTP

HTTP định nghĩa ngữ nghĩa của từng method để client và server hiểu loại tác động mà request hướng tới. Hai khái niệm quan trọng là **safe** và **idempotent**:

- **Safe method:** client yêu cầu đọc hoặc truy xuất thông tin; server không được hiểu request đó là yêu cầu thay đổi trạng thái nghiệp vụ.
- **Idempotent method:** nhiều request giống nhau có cùng tác động dự kiến lên trạng thái của server như một request.

Theo RFC 9110, các safe method cũng là idempotent. Một method idempotent vẫn có thể thay đổi trạng thái, ví dụ PUT và DELETE.

| HTTP method | Safe | Idempotent theo ngữ nghĩa HTTP | Ý nghĩa khi retry |
| --- | --- | --- | --- |
| GET | Có | Có | Thường có thể retry khi lỗi tạm thời |
| HEAD | Có | Có | Thường có thể retry khi lỗi tạm thời |
| OPTIONS | Có | Có | Thường có thể retry khi lỗi tạm thời |
| TRACE | Có | Có | Có ngữ nghĩa safe và idempotent; thường bị hạn chế trong ứng dụng thực tế |
| PUT | Không | Có | Có thể gửi lại cùng nội dung để đặt tài nguyên về cùng trạng thái |
| DELETE | Không | Có | Có thể gửi lại yêu cầu xóa cùng tài nguyên |
| POST | Không | Không được bảo đảm | Chỉ retry an toàn khi API có cơ chế chống xử lý trùng hoặc nghiệp vụ vốn idempotent |
| PATCH | Không | Không được bảo đảm | Phải xem xét ý nghĩa của patch cụ thể và hợp đồng API |

### 2.1. PUT và DELETE

PUT thường biểu diễn việc tạo hoặc thay thế trạng thái của một tài nguyên tại URI đã biết. Gửi cùng một representation đến cùng URI nhiều lần phải có cùng tác động dự kiến.

~~~http
PUT /api/customers/42/address
Content-Type: application/json

{
  "street": "12 Nguyen Hue",
  "city": "Ho Chi Minh City"
}
~~~

Nếu request trên được gửi lại, địa chỉ của khách hàng vẫn được đặt thành cùng một giá trị. API không nên diễn giải mỗi lần PUT là một lệnh tạo thêm địa chỉ mới.

DELETE yêu cầu xóa tài nguyên được xác định bởi URI:

~~~http
DELETE /api/orders/ORD-2026-001
~~~

Lần đầu server có thể xóa đơn hàng hoặc đánh dấu đơn hàng đã bị xóa. Lần sau, tài nguyên đã ở trạng thái không tồn tại hoặc đã xóa. Phản hồi có thể khác nhau, nhưng tác động dự kiến vẫn là tài nguyên đó không còn tồn tại.

### 2.2. POST và PATCH

POST thường yêu cầu server thực hiện một thao tác theo ngữ nghĩa của tài nguyên đích. Ví dụ tạo đơn hàng:

~~~http
POST /api/orders
Content-Type: application/json

{
  "customerId": "CUS-42",
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    }
  ]
}
~~~

Nếu mỗi lần nhận POST server đều tạo một bản ghi đơn hàng mới, việc gửi lại request sẽ tạo đơn trùng. HTTP không tự cung cấp bảo đảm chống trùng cho POST.

PATCH áp dụng một phần thay đổi lên tài nguyên. Tác động của nó phụ thuộc vào nội dung patch:

- Đặt trường trạng thái thành giá trị cụ thể, chẳng hạn **status = "CANCELLED"**, có thể được thiết kế lũy đẳng.
- Tăng một trường số lượng thêm 1 là không lũy đẳng nếu mỗi lần áp dụng đều tăng thêm.
- Một patch chứa phép thêm phần tử vào danh sách có thể tạo phần tử trùng khi gửi lại.

Do đó, không thể kết luận mọi PATCH đều an toàn hoặc mọi POST đều không thể lũy đẳng. Điều quyết định là ngữ nghĩa và hợp đồng của API cụ thể. Tuy nhiên, client không nên tự giả định một POST hoặc PATCH là lũy đẳng nếu server chưa công bố và triển khai bảo đảm đó.

## 3. Vì sao timeout khiến retry trở nên nguy hiểm?

Một lỗi kết nối không cho biết chắc server đã thực hiện nghiệp vụ hay chưa. Xét luồng tạo đơn hàng:

~~~mermaid
sequenceDiagram
    participant C as Order Client
    participant L as LoadBalancer
    participant A as Order Service instance A
    participant B as Order Service instance B
    C->>L: POST /orders
    L->>A: Chuyển request
    A->>A: Lưu đơn hàng thành công
    A--xC: Response bị mất trên mạng
    C->>C: Hết thời gian chờ
    C->>L: Retry request
    L->>B: Chọn instance B
    B->>B: Tạo đơn hàng lần nữa
    B-->>C: Trả về đơn hàng thứ hai
~~~

Client chỉ nhìn thấy timeout. Trong thực tế có ít nhất ba khả năng:

1. Request chưa đến được server, nên nghiệp vụ chưa được thực hiện.
2. Server đã nhận request nhưng chưa thực hiện xong.
3. Server đã hoàn thành nghiệp vụ và gửi response, nhưng response bị mất hoặc đến sau deadline của client.

Nếu client retry ở trường hợp thứ nhất, request thứ hai có thể giúp hoàn thành nghiệp vụ. Nếu retry ở trường hợp thứ ba mà API không chống trùng, thao tác có thể được thực hiện hai lần.

Đây là lý do không thể suy ra “server chưa xử lý” chỉ từ việc client không nhận được response. Timeout mô tả điều client quan sát được, không phải bằng chứng về trạng thái giao dịch phía server.

### 3.1. Những thời điểm lỗi thường gặp

| Thời điểm xảy ra lỗi | Điều client biết | Rủi ro khi retry |
| --- | --- | --- |
| Không phân giải được service ID hoặc không chọn được instance | Request chưa được gửi đến instance nghiệp vụ | Thường chưa có side effect từ service đích |
| Lỗi kết nối trước khi gửi request | Có thể request chưa đến server | Cần xem lỗi xảy ra ở giai đoạn nào của HTTP client và proxy |
| Kết nối đã gửi request nhưng client hết read timeout | Không biết server đã commit hay chưa | Có thể tạo side effect trùng |
| Server trả 503 hoặc 504 sau khi một thành phần phía sau đã xử lý | Chỉ biết nhận được mã lỗi | Có thể nghiệp vụ đã hoàn tất ở một dependency |
| Client nhận response thành công | Biết kết quả được trả về | Không cần retry thao tác đó |

Không phải mọi lỗi 5xx đều có nghĩa thao tác chưa được thực hiện. Một proxy có thể trả 504 trong khi service đích vẫn hoàn thành giao dịch. Chính sách retry phải dựa vào ngữ nghĩa API và khả năng chống trùng, không chỉ dựa trên mã trạng thái.

## 4. Idempotency key cho các thao tác không tự lũy đẳng

Với một thao tác như tạo đơn hàng hoặc thanh toán, client có thể gửi một **idempotency key** để định danh một lần thực hiện nghiệp vụ logic. Server lưu key cùng kết quả xử lý. Nếu request được gửi lại với cùng key và cùng nội dung, server nhận diện đây là lần thử lại của thao tác cũ và trả lại kết quả đã lưu.

Header có thể được thiết kế như sau:

~~~http
POST /api/payments
Idempotency-Key: 9a91f8e2-7c31-4f89-a88c-1c5c9fd4d207
Content-Type: application/json

{
  "orderId": "ORD-2026-001",
  "amount": 250000,
  "currency": "VND"
}
~~~

Tên header và cách diễn giải key là một phần của hợp đồng API mà hệ thống phải thống nhất. Chỉ gửi header không tự tạo ra tính lũy đẳng; server phải lưu và kiểm tra key một cách có phối hợp giữa các instance.

### 4.1. Vòng đời của key

Một key đại diện cho **một thao tác nghiệp vụ logic**, không phải cho một lần gửi HTTP. Client phải tạo key trước lần gửi đầu tiên và tái sử dụng key đó cho tất cả lần retry của cùng thao tác.

~~~mermaid
flowchart TD
    A["Client tạo thao tác thanh toán"] --> B["Tạo một Idempotency-Key"]
    B --> C["Gửi request cùng key"]
    C --> D["Server kiểm tra key và fingerprint"]
    D --> E{"Key đã tồn tại?"}
    E -->|Chưa| F["Đăng ký key một cách nguyên tử"]
    F --> G["Thực hiện nghiệp vụ"]
    G --> H["Lưu kết quả và trạng thái COMPLETED"]
    H --> I["Trả response"]
    E -->|Đã hoàn tất, cùng nội dung| J["Trả lại response đã lưu"]
    E -->|Đang xử lý| K["Trả trạng thái đang xử lý theo hợp đồng"]
    E -->|Cùng key, khác nội dung| L["Từ chối request không nhất quán"]
    I --> M["Client retry cùng key nếu cần"]
    J --> M
    M --> D
~~~

Ví dụ: người dùng bấm nút thanh toán một lần, ứng dụng tạo key **PAY-CUS42-ORDER001-01**. Nếu lần gửi đầu bị timeout, lần gửi sau phải sử dụng lại chính key đó. Nếu tạo UUID mới cho mỗi lần thử, server sẽ xem chúng là hai thao tác khác nhau và không thể phát hiện request trùng.

### 4.2. Phạm vi định danh và fingerprint

Chỉ dùng key làm khóa tra cứu có thể gây xung đột giữa người dùng hoặc endpoint. Server nên xác định phạm vi key bằng các thành phần phù hợp, chẳng hạn:

- Danh tính người dùng, tenant hoặc tài khoản đã xác thực.
- Tên thao tác hoặc endpoint nghiệp vụ.
- Idempotency key do client cung cấp.

Server cũng nên tạo **request fingerprint** từ dữ liệu có ý nghĩa nghiệp vụ, ví dụ hash của payload đã chuẩn hóa cùng loại thao tác. Mục tiêu là phát hiện trường hợp client vô tình tái sử dụng cùng key cho nội dung khác.

| Tình huống | Hành vi nên có |
| --- | --- |
| Cùng người dùng, cùng thao tác, cùng key, cùng nội dung, đã hoàn tất | Trả lại kết quả đã lưu |
| Cùng key nhưng payload hoặc tham số nghiệp vụ khác | Từ chối, thường dùng 409 Conflict theo hợp đồng API |
| Cùng key đang được request khác xử lý | Trả trạng thái đang xử lý hoặc hướng dẫn client kiểm tra lại |
| Key thuộc người dùng hoặc tenant khác | Không chia sẻ kết quả giữa hai phạm vi bảo mật |
| Key đã hết thời hạn lưu | Xử lý theo chính sách hết hạn được công bố |

Không đưa dữ liệu bí mật hoặc thông tin cá nhân không cần thiết vào chính key. Key nên khó đoán, có đủ entropy và không chứa access token.

## 5. Triển khai chống xử lý trùng ở server

### 5.1. Lưu trạng thái idempotency dùng chung

Vì Spring Cloud LoadBalancer có thể chuyển lần retry sang instance khác, trạng thái idempotency phải được chia sẻ giữa các instance. Lưu key trong biến static hoặc bộ nhớ riêng của từng tiến trình là không đủ: instance A có thể đã xử lý request nhưng instance B không biết key đó.

Một bảng lưu trữ có thể gồm các trường:

| Trường | Mục đích |
| --- | --- |
| scope | Người dùng, tenant hoặc phạm vi API |
| operation | Loại thao tác nghiệp vụ |
| idempotency_key | Key do client gửi |
| request_hash | Fingerprint của nội dung request |
| state | Trạng thái như IN_PROGRESS hoặc COMPLETED |
| response_status | Mã HTTP của kết quả đã xử lý |
| response_body | Nội dung response có thể phát lại |
| created_at, expires_at | Thời điểm tạo và thời hạn giữ key |

Tạo unique constraint trên bộ khóa gồm scope, operation và idempotency_key. Unique constraint là lớp bảo vệ quan trọng khi hai request giống nhau đến hai instance gần như đồng thời.

Ví dụ DDL rút gọn cho PostgreSQL:

~~~sql
CREATE TABLE idempotency_record (
    scope             VARCHAR(160) NOT NULL,
    operation         VARCHAR(120) NOT NULL,
    idempotency_key   VARCHAR(200) NOT NULL,
    request_hash      CHAR(64) NOT NULL,
    state             VARCHAR(20) NOT NULL,
    response_status   INTEGER,
    response_body     JSONB,
    created_at        TIMESTAMPTZ NOT NULL,
    expires_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scope, operation, idempotency_key)
);
~~~

Kiểu dữ liệu và cấu trúc response cần điều chỉnh theo hệ quản trị cơ sở dữ liệu và yêu cầu của API. Không nên lưu các header nhạy cảm như Authorization trong response đã ghi nhận.

### 5.2. Xử lý request theo cách nguyên tử

Một quy trình xử lý tổng quát:

1. Xác thực caller và xác định scope, operation.
2. Kiểm tra định dạng key và validate request.
3. Chuẩn hóa dữ liệu cần thiết rồi tính request fingerprint.
4. Thử đăng ký key bằng thao tác nguyên tử được bảo vệ bởi unique constraint.
5. Nếu key đã tồn tại, so sánh fingerprint. Nếu khác, từ chối request. Nếu giống và đã hoàn tất, trả kết quả đã lưu.
6. Nếu key đang được xử lý, trả trạng thái theo hợp đồng API, không thực hiện nghiệp vụ lần thứ hai.
7. Với key mới, thực hiện thay đổi nghiệp vụ và lưu trạng thái hoàn tất cùng kết quả.
8. Trả response cho client.

Ví dụ dưới đây minh họa luồng ở mức service; phần xử lý tranh chấp unique constraint, transaction và mapping response cần được triển khai trong repository/service phù hợp:

~~~java
public PaymentResponse createPayment(
        String idempotencyKey,
        CreatePaymentRequest request) {

    String scope = currentCustomerId();
    String operation = "CREATE_PAYMENT";
    String requestHash = fingerprint(request);

    IdempotencyRecord existing =
            idempotencyRepository.find(scope, operation, idempotencyKey);

    if (existing != null) {
        if (!existing.requestHash().equals(requestHash)) {
            throw new IdempotencyConflictException(
                    "The key was used with a different request");
        }

        if (existing.isCompleted()) {
            return existing.toPaymentResponse();
        }

        throw new RequestStillProcessingException();
    }

    // Claim the key atomically before performing the business operation.
    idempotencyRepository.insertInProgress(
            scope, operation, idempotencyKey, requestHash);

    Payment payment = paymentRepository.create(request);
    PaymentResponse response = PaymentResponse.from(payment);

    idempotencyRepository.complete(
            scope, operation, idempotencyKey, response);

    return response;
}
~~~

Đây là pseudocode để thể hiện trình tự, không phải một implementation hoàn chỉnh có thể sao chép nguyên trạng. Trong ứng dụng thật, hai request đồng thời có thể cùng đọc thấy key chưa tồn tại. Vì vậy, bước đăng ký key phải là thao tác nguyên tử; không thể chỉ dựa vào câu lệnh SELECT rồi INSERT thông thường mà không xử lý tranh chấp.

Nếu thay đổi nghiệp vụ và bản ghi idempotency cùng nằm trong một database, hãy dùng transaction để commit chúng cùng nhau. Khi insert key bị vi phạm unique constraint, request thua cuộc phải đọc lại bản ghi đã tồn tại và xử lý theo state/fingerprint. Cần chú ý transaction đã bị đánh dấu rollback-only sau lỗi constraint; có thể phải xử lý xung đột ở transaction boundary riêng.

### 5.3. Tránh cửa sổ lỗi giữa nghiệp vụ và bản ghi key

Giả sử server tạo giao dịch thanh toán thành công rồi mới ghi trạng thái COMPLETED. Nếu tiến trình dừng giữa hai bước, lần retry có thể thấy key vẫn IN_PROGRESS hoặc chưa có kết quả và tạo giao dịch lần nữa. Ngược lại, nếu ghi COMPLETED trước khi giao dịch thật hoàn thành, server có thể phát lại một kết quả thành công không đúng thực tế.

Với dữ liệu trong cùng database, nên ghi thay đổi nghiệp vụ và kết quả idempotency trong cùng transaction. Với side effect ở hệ thống ngoài, ví dụ cổng thanh toán, database transaction của ứng dụng không thể tự bao trọn giao dịch bên ngoài. Khi đó:

- Truyền một khóa chống trùng ổn định sang nhà cung cấp thanh toán nếu họ hỗ trợ.
- Lưu trạng thái lệnh gửi đi và kết quả nhận về để có thể đối soát.
- Dùng transactional outbox để ghi sự kiện cần gửi cùng transaction với dữ liệu nghiệp vụ.
- Thiết kế consumer hoặc workflow có khả năng nhận lại thông điệp mà không lặp side effect.
- Có quy trình đối soát khi trạng thái không xác định, thay vì tự động tạo giao dịch mới.

Idempotency ở một service không tự bảo đảm side effect của mọi dependency phía sau cũng chỉ xảy ra một lần. Mỗi ranh giới hệ thống cần có hợp đồng và cơ chế xử lý trùng tương ứng. Cơ chế này cũng không biến mạng thành kênh truyền “exactly once”: request hoặc message vẫn có thể được chuyển nhiều lần. Mục tiêu thực tế là làm cho tác động nghiệp vụ được khử trùng trong một phạm vi key và khoảng thời gian đã xác định.

### 5.4. Thời hạn lưu key

Không thể lưu key vô thời hạn trong mọi hệ thống. Server thường đặt thời hạn dựa trên thời gian client có thể retry, thời gian xử lý bất đồng bộ và yêu cầu đối soát. TTL phải dài hơn cửa sổ retry được công bố.

Khi xóa bản ghi key quá sớm, một request cũ đến muộn có thể bị hiểu thành thao tác mới. Với nghiệp vụ tài chính, thời hạn lưu và khả năng đối soát có thể cần dài hơn nhiều so với timeout HTTP thông thường.

Chính sách hết hạn cần được ghi trong hợp đồng API. Client không nên gửi lại cùng thao tác sau khi key đã hết hạn mà không kiểm tra trạng thái nghiệp vụ trước.

## 6. Gửi idempotency key từ Spring HTTP client

### 6.1. RestClient

Tạo key một lần ở ranh giới thao tác nghiệp vụ, sau đó truyền key đó vào client. Không tạo key mới bên trong từng lần retry:

~~~java
public PaymentResponse createPayment(
        String idempotencyKey,
        CreatePaymentRequest request) {

    return restClient.post()
            .uri("http://payment-service/api/payments")
            .header("Idempotency-Key", idempotencyKey)
            .contentType(MediaType.APPLICATION_JSON)
            .body(request)
            .retrieve()
            .body(PaymentResponse.class);
}
~~~

Khi HTTP client hoặc tầng retry gửi lại request, cùng key phải được giữ nguyên. Service đích phải lưu key trong kho dùng chung và thực hiện kiểm tra như phần trước.

### 6.2. WebClient

Với WebClient, có thể truyền header theo cùng nguyên tắc:

~~~java
public Mono<PaymentResponse> createPayment(
        String idempotencyKey,
        CreatePaymentRequest request) {

    return webClient.post()
            .uri("http://payment-service/api/payments")
            .header("Idempotency-Key", idempotencyKey)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(PaymentResponse.class);
}
~~~

Publisher có thể được subscribe hoặc retry lại theo cách ứng dụng thiết kế. Hãy bảo đảm mọi lần subscribe cho cùng một thao tác nghiệp vụ vẫn dùng cùng key và payload. Không tạo key ngẫu nhiên bên trong một đoạn code được thực thi lại mỗi lần subscribe.

### 6.3. OpenFeign

Với Feign, khai báo header như một tham số của client:

~~~java
@FeignClient(name = "payment-service")
interface PaymentFeignClient {

    @PostMapping("/api/payments")
    PaymentResponse createPayment(
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestBody CreatePaymentRequest request);
}
~~~

Caller phải truyền cùng key khi gọi lại phương thức cho cùng một thao tác. Feign không tự tạo idempotency key và cũng không tự làm cho POST trở thành lũy đẳng.

## 7. Phối hợp idempotency với retry của Spring Cloud LoadBalancer

Spring Cloud LoadBalancer có thể thử lại request trên cùng instance hoặc một instance kế tiếp, tùy cấu hình và loại HTTP client. Khi retry chuyển sang instance khác, instance mới phải nhìn thấy cùng trạng thái idempotency của request trước. Điều này đòi hỏi kho lưu trữ dùng chung hoặc một cơ chế phối hợp nhất quán giữa các instance.

Ví dụ cấu hình giới hạn số lần retry ở tầng LoadBalancer:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retryable-status-codes:
          - 502
          - 503
          - 504
~~~

Cấu hình này chỉ minh họa giới hạn số lần thử và một nhóm status code. Khả năng retry thực tế phụ thuộc vào HTTP client, adapter và phiên bản Spring Cloud. Bật retry không tạo ra idempotency key, không lưu kết quả và không bảo đảm request POST không bị xử lý hai lần.

Một chính sách retry nên đáp ứng các nguyên tắc:

1. Ưu tiên retry safe method hoặc method idempotent theo hợp đồng API.
2. Với POST hoặc PATCH có side effect, chỉ retry khi server có cơ chế chống trùng đã được kiểm chứng.
3. Chỉ retry lỗi có khả năng tạm thời; tôn trọng Retry-After khi server trả 429 hoặc 503 kèm chỉ dẫn phù hợp.
4. Giới hạn số lần thử, áp dụng backoff và jitter, đồng thời tuân thủ deadline của request gốc.
5. Tránh bật retry chồng lặp ở nhiều tầng mà không tính tổng số lần gọi. Ví dụ, hai tầng đều cho phép ba lần thử có thể tạo ra tối đa chín lần gọi đến dependency.
6. Ghi nhận số lần retry và tỷ lệ request trùng được phát hiện để phát hiện retry storm hoặc lỗi cấu hình.

Không nên mặc định retry mọi lỗi 5xx. Một lỗi 500 có thể được trả về sau khi nghiệp vụ đã commit. Với thao tác không lũy đẳng, idempotency key phải được server thực thi trước khi caller dựa vào retry để phục hồi.

### 7.1. Ví dụ luồng thanh toán qua hai instance

Giả sử Payment Service có hai instance A và B:

1. Order Service tạo key cho thao tác thanh toán của đơn hàng.
2. LoadBalancer chuyển POST đến instance A.
3. A đăng ký key trong kho dùng chung, thực hiện giao dịch và lưu kết quả COMPLETED.
4. Response bị mất nên Order Service timeout.
5. LoadBalancer chuyển lần retry đến instance B với cùng key và payload.
6. B tìm thấy key đã hoàn tất, xác nhận fingerprint trùng và trả lại kết quả đã lưu.
7. Chỉ có một giao dịch thanh toán được tạo.

Nếu A và B lưu key trong bộ nhớ riêng, bước 6 có thể thất bại vì B không biết A đã xử lý. Nếu client tạo key mới ở bước 5, server cũng xem đây là một thao tác khác. Cả hai trường hợp đều làm mất bảo đảm chống trùng.

## 8. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tạo key mới ở mỗi lần retry | Mỗi request được xem là thao tác mới | Tạo key ở đầu thao tác nghiệp vụ và tái sử dụng |
| Chỉ lưu key trong memory của instance | Retry sang instance khác không nhận ra request cũ | Dùng kho chia sẻ có unique constraint hoặc cơ chế phối hợp tương đương |
| Chỉ kiểm tra key bằng SELECT rồi mới INSERT | Hai request đồng thời có thể cùng vượt qua bước kiểm tra | Đăng ký key nguyên tử và xử lý unique conflict |
| Không kiểm tra request fingerprint | Cùng key có thể bị dùng cho nội dung khác | Lưu hash của payload đã chuẩn hóa và từ chối mismatch |
| Lưu key sau khi side effect đã xảy ra | Tiến trình có thể dừng trước khi ghi key, khiến retry tạo side effect lần nữa | Commit dữ liệu nghiệp vụ và record cùng transaction hoặc dùng cơ chế idempotency ở dependency |
| Xóa key quá sớm | Request cũ đến muộn có thể tạo thao tác mới | Chọn TTL theo cửa sổ retry và yêu cầu nghiệp vụ |
| Retry mọi POST hoặc mọi lỗi 5xx | Tạo dữ liệu trùng hoặc tăng tải khi dependency đang lỗi | Retry có điều kiện, có giới hạn và dựa trên hợp đồng idempotency |
| Dùng idempotency key thay cho xác thực | Người khác có thể đoán hoặc dùng lại key để xem kết quả | Ràng buộc key với principal/tenant và kiểm tra quyền trên từng request |

## 9. Kiểm thử tính lũy đẳng và retry

Không nên chỉ kiểm tra trường hợp request thành công bình thường. Các lỗi quan trọng nhất thường xuất hiện khi response bị mất hoặc nhiều request cùng đến trong một khoảng thời gian ngắn.

| Kịch bản kiểm thử | Cách thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Gửi cùng key hai lần tuần tự | Gửi hai POST có cùng key và payload | Chỉ tạo một nghiệp vụ; lần sau nhận lại kết quả đã lưu |
| Gửi cùng key đồng thời | Phát hai request gần như cùng lúc đến hai instance | Chỉ một request claim được key và thực hiện nghiệp vụ |
| Cùng key, payload khác | Thay amount hoặc order ID nhưng giữ nguyên key | Server từ chối request không nhất quán |
| Mất response sau commit | Cho server commit rồi cố tình cắt kết nối trước khi client nhận response | Client retry cùng key và nhận lại kết quả cũ |
| Retry sang instance khác | Lần đầu đến A, lần sau đến B | B nhận ra key từ kho dùng chung và không lặp side effect |
| Instance khởi động lại | Restart instance sau khi xử lý thành công | Retry vẫn được nhận diện từ kho bền vững |
| Key hết hạn | Gửi lại request sau TTL đã công bố | Hành vi đúng với chính sách hết hạn; không tạo giao dịch ngoài dự kiến |
| Retry vượt deadline | Làm dependency phản hồi chậm hơn deadline caller | Caller dừng thử lại và ghi nhận trạng thái không xác định để đối soát |

Với thao tác thanh toán, hãy dùng sandbox hoặc dependency giả lập. Đối chiếu cả số bản ghi nghiệp vụ, số lần gọi dependency và response được trả lại; chỉ nhìn HTTP status chưa đủ để chứng minh không có side effect trùng.

## 10. Checklist khi thiết kế API có thể retry

- [ ] Xác định method và ngữ nghĩa của thao tác: safe, idempotent hay có side effect không lũy đẳng.
- [ ] Ghi rõ API có cho phép retry hay không và nhóm lỗi nào có thể retry.
- [ ] Với thao tác tạo mới hoặc thanh toán, định nghĩa idempotency key và phạm vi key.
- [ ] Yêu cầu client tái sử dụng key cùng payload cho mọi lần thử của một thao tác.
- [ ] Lưu fingerprint để phát hiện key bị tái sử dụng với nội dung khác.
- [ ] Dùng unique constraint hoặc thao tác nguyên tử để xử lý request đồng thời.
- [ ] Chia sẻ trạng thái idempotency giữa tất cả instance có thể nhận request.
- [ ] Lưu kết quả đủ để phát lại response theo hợp đồng API.
- [ ] Đồng bộ transaction của nghiệp vụ và record idempotency; xử lý riêng side effect ở hệ thống ngoài.
- [ ] Đặt TTL dài hơn cửa sổ retry và có quy trình đối soát khi trạng thái không rõ.
- [ ] Giới hạn retry theo số lần, backoff, jitter và deadline; tránh retry chồng nhiều tầng.
- [ ] Kiểm thử response bị mất sau commit, request đồng thời và retry sang instance khác.

## 11. Kết luận

Tính lũy đẳng là thuộc tính của thao tác nghiệp vụ và hợp đồng API. HTTP quy định GET, HEAD, OPTIONS, TRACE, PUT và DELETE có ngữ nghĩa idempotent; POST và PATCH cần được xem xét theo cách ứng dụng triển khai. Khi một thao tác không tự lũy đẳng nhưng cần retry, idempotency key giúp server nhận diện các lần gửi thuộc cùng một thao tác.

Trong hệ thống Spring Cloud, retry có thể đưa request đến một instance khác. Vì vậy, mọi instance phải dùng chung cơ chế chống trùng và phải xử lý tranh chấp một cách nguyên tử. Timeout, retry và idempotency cần được thiết kế cùng nhau để hệ thống phục hồi khi mạng không ổn định mà không lặp lại side effect nghiệp vụ.

## 12. Tài liệu tham khảo

- [RFC 9110 - HTTP Semantics, mục 9.2.2 Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2): định nghĩa method idempotent và ý nghĩa đối với retry.
- [RFC 9110 - HTTP Semantics, mục 9.2.1 Safe Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.1): ngữ nghĩa safe method.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): lựa chọn instance, retry và cấu hình LoadBalancer.
- [Spring Framework - REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): sử dụng RestClient và WebClient.
