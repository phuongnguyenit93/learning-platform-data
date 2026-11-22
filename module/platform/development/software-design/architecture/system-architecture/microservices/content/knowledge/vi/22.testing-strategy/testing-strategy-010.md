# Giới hạn kiểm thử đầu cuối và giảm lỗi không ổn định trong Microservices

## Mục tiêu học tập

Sau bài này, người học có thể giải thích kiểm thử đầu cuối (end-to-end, E2E) kiểm chứng điều gì trong một hệ thống microservices; xác định lý do không nên đẩy mọi tình huống kiểm thử lên tầng E2E; lựa chọn kịch bản E2E có giá trị; nhận diện nguyên nhân gây lỗi không ổn định (flaky test); và thiết kế cách tổ chức môi trường, dữ liệu, đồng bộ bất đồng bộ, khả năng quan sát và pipeline CI để kết quả kiểm thử đáng tin cậy hơn.

## 1. Bản chất của kiểm thử E2E trong Microservices

Kiểm thử E2E bắt đầu từ một điểm vào gần với người dùng hoặc hệ thống bên ngoài (UI, API gateway, public API), sau đó quan sát kết quả cuối cùng của một luồng nghiệp vụ đi qua nhiều thành phần. Ví dụ, một yêu cầu đặt hàng có thể đi qua Order Service, Payment Service, Inventory Service, message broker và cơ sở dữ liệu riêng của từng dịch vụ.

Một E2E tốt trả lời câu hỏi: **“Khi các dịch vụ được kết nối như môi trường thực tế, hành trình nghiệp vụ quan trọng có hoàn thành và tạo ra kết quả mà người dùng mong đợi hay không?”** Đây là loại bằng chứng khác với việc một phương thức Java trả đúng giá trị, một service truy cập database thành công, hoặc hai dịch vụ tuân thủ hợp đồng API.

Giả sử luồng mua hàng có dạng:

```text
Client -> API Gateway -> Order Service
                            |
                            v
                         OrderCreated event
                            |
                 +----------+----------+
                 |                     |
                 v                     v
          Payment Service        Inventory Service
                 |                     |
                 +----------+----------+
                            |
                            v
                    Order status: CONFIRMED
```

E2E có thể xác nhận rằng khách hàng tạo đơn thành công, thanh toán được ghi nhận, hàng tồn kho được giữ đúng, và trạng thái cuối của đơn chuyển sang CONFIRMED. Nhưng chỉ một lần chạy thành công không chứng minh được mọi nhánh lỗi, mọi thứ tự sự kiện, mọi điều kiện tranh chấp hay mọi hợp đồng giữa các dịch vụ đều đúng.

## 2. Giới hạn cố hữu của E2E

**Phạm vi lớn khiến chẩn đoán khó.** Khi một kịch bản thất bại, nguyên nhân có thể nằm ở client, gateway, xác thực, mạng, cấu hình, dịch vụ đích, message broker, dữ liệu, hoặc hệ thống bên thứ ba. Một thông báo “checkout failed” thường chưa đủ để biết sai ở đâu.

**Chi phí và thời gian cao.** E2E cần khởi tạo nhiều thành phần, dữ liệu và môi trường. Khi hàng trăm kịch bản cùng phụ thuộc một cụm dịch vụ, bộ kiểm thử dễ chạy chậm, khó song song và khiến vòng phản hồi của lập trình viên kéo dài.

**Khả năng tái lập thấp hơn kiểm thử cục bộ.** Đồng hồ, lịch chạy của consumer, độ trễ mạng, hàng đợi, kết nối tài nguyên dùng chung, retry và eventual consistency làm cho thời điểm quan sát kết quả thay đổi giữa các lần chạy.

**Không thể bao phủ tổ hợp trạng thái.** Microservices có nhiều phiên bản API, kiểu lỗi, thứ tự xử lý sự kiện, phân vùng dữ liệu và trạng thái phân tán. Số tổ hợp tăng nhanh; cố kiểm tra tất cả bằng E2E là không thực tế.

**Phụ thuộc môi trường.** Một test có thể đỏ vì môi trường staging thiếu tài nguyên, hết quota, cấu hình chưa đồng nhất hoặc dịch vụ bên ngoài bị gián đoạn, dù thay đổi mã nguồn đang xét không gây ra lỗi.

**E2E không thay thế kiểm tra phi chức năng.** Một luồng E2E thành công không tự chứng minh hiệu năng tải lớn, khả năng chịu lỗi kéo dài, bảo mật, kiểm soát phân quyền từng API hay tính đúng đắn của toàn bộ dữ liệu.

Vì vậy, E2E nên là **lớp xác nhận các hành trình quan trọng và sự phối hợp xuyên dịch vụ**, không phải nơi đặt mọi kiểm tra đầu vào, quy tắc nghiệp vụ và trường hợp biên.

## 3. Chọn đúng tầng kiểm thử

| Tầng kiểm thử | Câu hỏi chính | Ví dụ phù hợp |
| --- | --- | --- |
| Unit test | Quy tắc cục bộ có đúng không? | Tính tiền, áp mã giảm giá, quy tắc chuyển trạng thái |
| Component/service test | Một dịch vụ hoạt động đúng với dependency được kiểm soát không? | Order Service với database thực trong Testcontainers và Payment API giả lập |
| Integration test | Tích hợp kỹ thuật có đúng không? | Repository, Kafka producer/consumer, transaction, serialization |
| Contract test | Hai bên giao tiếp có thống nhất cấu trúc và ngữ nghĩa không? | Trường bắt buộc của REST response, schema sự kiện, mã lỗi |
| E2E test | Luồng nghiệp vụ xuyên dịch vụ có hoàn thành không? | Đặt hàng → thanh toán → giữ kho → xác nhận |

Một quy tắc tính phí có 25 trường hợp biên nên được thử chủ yếu bằng unit/component test. Một hợp đồng API với nhiều trạng thái nên được kiểm chứng bằng contract test. E2E chỉ cần một số hành trình tiêu biểu chứng minh các dịch vụ thực sự nối với nhau đúng cách.

Không có tỷ lệ unit/integration/E2E cố định cho mọi dự án. Nguyên tắc là đặt kiểm thử ở tầng **nhỏ nhất vẫn chứng minh được rủi ro cần kiểm soát**, rồi dùng ít E2E hơn để xác nhận tích hợp toàn hệ thống.

### Tiêu chí chọn một kịch bản E2E

Ưu tiên khi kịch bản đồng thời có giá trị nghiệp vụ cao, thực sự đi qua nhiều dịch vụ, có điểm bắt đầu và điều kiện thành công rõ ràng, khó chứng minh đầy đủ bằng tầng thấp hơn, và có thể thiết lập dữ liệu đầu vào lặp lại được.

Những ứng viên thường tốt gồm: đăng nhập và ủy quyền xuyên gateway; mua hàng hoặc thanh toán; xử lý đơn có sự kiện bất đồng bộ; giao dịch saga với bù trừ khi lỗi; đường đi idempotency để yêu cầu bị gửi lặp không gây tác động kép; một đường hồi phục quan trọng sau khi dependency tạm thời không sẵn sàng.

Những ứng viên thường không đáng đẩy lên E2E gồm: hàng chục tổ hợp định dạng email, tất cả trường hợp validation đơn giản, từng nhánh tính thuế, từng HTTP status trong một adapter, hay chi tiết mapping database nội bộ.

## 4. Flaky test là gì và vì sao nguy hiểm?

Một kiểm thử bị xem là *flaky* khi **cùng mã nguồn và cùng kỳ vọng**, kết quả có thể PASS hoặc FAIL giữa các lần chạy mà không có thay đổi có chủ đích đối với hành vi được kiểm thử. Kết quả thay đổi do yếu tố thời gian, môi trường, thứ tự hoặc trạng thái ngoài ý muốn.

Flaky test có hai tác hại trực tiếp:

1. Báo động giả làm đội ngũ mất thời gian điều tra, chạy lại pipeline và bắt đầu bỏ qua tín hiệu đỏ.
2. Che giấu lỗi thật: khi mọi người quen với việc “chạy lại là xanh”, một regression nghiêm trọng có thể bị xem nhầm là lỗi hạ tầng.

Không phải test đỏ nào cũng flaky. Nếu cùng một điều kiện luôn gây ra FAIL do logic sai, đó là lỗi có thể tái lập. Nếu mạng bên ngoài thực sự bị ngắt và hệ thống phải xử lý an toàn, bài kiểm thử thất bại cũng có thể là phát hiện hợp lệ. Cần giữ bằng chứng để phân biệt.

### Những nguồn gây flaky phổ biến

| Nguồn | Biểu hiện thường thấy | Biện pháp chính |
| --- | --- | --- |
| Race condition | Thỉnh thoảng đọc dữ liệu trước khi consumer xử lý xong | Chờ theo trạng thái có timeout thay vì chờ cố định |
| Eventual consistency | API trả dữ liệu cũ ngay sau một event | Assertion eventual consistency với giới hạn thời gian |
| Dữ liệu dùng chung | Chạy một mình xanh, chạy song song đỏ | Namespace/ID riêng cho mỗi test, dữ liệu độc lập |
| Thứ tự chạy | Test B chỉ xanh nếu A đã chạy | Thiết lập và teardown hoàn chỉnh cho từng test |
| Đồng hồ, timezone | Lỗi gần nửa đêm, cuối tháng hoặc đổi múi giờ | Clock được kiểm soát, thời gian chuẩn UTC, thời điểm cố định khi có thể |
| Hạ tầng quá tải | Timeout vào giờ cao điểm CI | Resource quota hợp lý, giới hạn concurrency, đo độ trễ |
| Phụ thuộc bên thứ ba | Lỗi ngẫu nhiên do sandbox, quota, rate limit | Fake/sandbox ổn định ở tầng thấp hơn; E2E ngoài hệ thống chọn lọc |
| Test selector không ổn định | UI đổi layout thì test không tìm thấy phần tử | Locator theo vai trò, nhãn hoặc test-id ổn định |
| Retry và duplicate event | Số bản ghi đôi khi tăng bất thường | Khóa idempotency, assertion theo trạng thái nghiệp vụ |
| Cleanup chưa hoàn tất | Lần chạy sau đọc dữ liệu còn sót | Cleanup có xác nhận, TTL và định danh duy nhất |

## 5. Thiết kế kịch bản E2E ổn định theo một cấu trúc rõ ràng

Một kịch bản nên đi qua năm phần:

1. **Arrange:** thiết lập tiền điều kiện biết trước, chẳng hạn tạo khách hàng thử nghiệm, một sản phẩm còn hàng và payment simulator có phản hồi xác định.
2. **Act:** gửi yêu cầu thông qua public API/UI giống điểm vào dự kiến của người dùng.
3. **Observe:** truy vấn trạng thái nghiệp vụ cuối cùng qua API công khai hoặc điểm quan sát đã định nghĩa.
4. **Assert:** đối chiếu những bất biến quan trọng, ví dụ một đơn hàng, một giao dịch thanh toán, số lượng kho được trừ một lần.
5. **Cleanup:** giải phóng tài nguyên và dữ liệu do test sở hữu, đồng thời bảo đảm các sự kiện xử lý muộn không ảnh hưởng bài tiếp theo.

Ví dụ một ca “khách hàng đặt hàng thành công”:

- Tiền điều kiện: người dùng được ủy quyền; hàng hóa có đủ tồn kho; payment simulator trả APPROVED; mỗi lần chạy có order ID hoặc request ID mới.
- Hành động: POST tạo đơn qua gateway kèm idempotency key duy nhất.
- Kỳ vọng cuối: đơn ở trạng thái CONFIRMED, số tiền đúng, thanh toán ghi nhận đúng một lần và lượng tồn kho giảm đúng một lần.
- Điều kiện thời gian: kết quả hoàn tất trong deadline phù hợp với cam kết xử lý của hệ thống.
- Bằng chứng khi lỗi: request/correlation ID, log theo trace, trạng thái các dịch vụ và thời điểm event được phát/nhận.

Hãy assert trên kết quả nghiệp vụ quan sát được. Không nên assert số lần một phương thức private được gọi trong bài E2E, vì điều đó khóa kiểm thử vào chi tiết triển khai và làm bài dễ gãy khi refactor hợp lệ.

## 6. Loại bỏ việc ngủ cố định và xử lý bất đồng bộ đúng cách

Đây là một trong các nguồn flaky phổ biến nhất của hệ thống dùng message broker:

```java
// Dễ flaky: giả định consumer luôn hoàn thành trong 2 giây.
api.createOrder(request);
Thread.sleep(2_000);
assertThat(api.getOrder(orderId).status()).isEqualTo("CONFIRMED");
```

Nếu consumer cần 2,1 giây, test FAIL dù nghiệp vụ vẫn đúng. Nếu consumer chỉ cần 100 ms, test mất 1,9 giây vô ích. Tăng sleep lên 10 giây không giải quyết gốc rễ và làm bộ test chậm hơn.

Thay bằng polling có giới hạn và assertion eventual consistency, ví dụ với JUnit 5, AssertJ và Awaitility (mã minh họa; adapter API phải được dự án cung cấp):

```java
@Test
void orderIsEventuallyConfirmed() {
    String requestId = UUID.randomUUID().toString();
    OrderResponse created = api.createOrder(validRequest(requestId));

    await()
        .atMost(Duration.ofSeconds(30))
        .pollInterval(Duration.ofMillis(500))
        .untilAsserted(() -> {
            OrderResponse current = api.getOrder(created.id());
            assertThat(current.status()).isEqualTo("CONFIRMED");
        });

    assertThat(api.countPaymentsForOrder(created.id())).isEqualTo(1);
}
```

Chọn deadline theo SLO và độ trễ thực tế của môi trường test; không tăng bừa chỉ để làm xanh pipeline. Poll phải là thao tác đọc, tránh vô tình phát sinh thêm side effect. Với eventual consistency, nên kiểm tra **trạng thái cuối ổn định** và bất biến liên quan; nếu hệ thống có trạng thái trung gian PENDING → PROCESSING → CONFIRMED thì test không nên thất bại chỉ vì quan sát thấy trạng thái trung gian hợp lệ.

Đối với stream hoặc sự kiện có thứ tự không chắc chắn, tránh assert “event A nhất thiết phải xuất hiện trước B” trừ khi hợp đồng nghiệp vụ thực sự yêu cầu điều đó. Khi cần kiểm tra hiệu lực một lần, assert vào invariant như “không có thanh toán trùng” thay vì dựa vào số lần broker gửi message.

## 7. Kiểm soát dữ liệu và cô lập các lần chạy

Mỗi bài E2E nên tự tạo dữ liệu đủ dùng bằng API hoặc fixture có kiểm soát. Không nên phụ thuộc vào “tài khoản test mặc định còn dư số tiền” hay “sản phẩm ID=42 luôn tồn tại” nếu các worker CI cùng có thể thay đổi chúng.

Kỹ thuật thực tế:

- Gắn run ID/test ID duy nhất vào resource, idempotency key, queue consumer group hoặc namespace khi phù hợp. Không dùng chung user/cart/order có thể thay đổi bởi ca khác.
- Test độc lập về thứ tự: chạy riêng, chạy ngược hoặc chạy song song vẫn có cùng tiền điều kiện.
- Dữ liệu seed phải có version, ngữ nghĩa rõ ràng và gắn với môi trường được phép.
- Cleanup trong finally hoặc teardown; tài nguyên có thể còn xử lý event sau teardown thì cần namespace và TTL để không va chạm.
- Nếu một dependency không thể cô lập, đặt giới hạn chạy song song cho đúng nhóm test và ghi rõ lý do; không khóa toàn bộ suite tùy tiện.
- Không truy vấn “bản ghi mới nhất” của cả môi trường để assert kết quả của một test; luôn lọc bằng định danh của chính lần chạy.

Với microservices, transaction rollback ở tiến trình chạy test **không** rollback được các transaction độc lập trong Order, Payment và Inventory Service. Vì vậy phải có chiến lược cleanup xuyên dịch vụ hoặc một môi trường tạm thời có thể hủy sau chạy.

## 8. Làm môi trường kiểm thử đủ thực tế nhưng có kiểm soát

Chọn môi trường phù hợp với mục tiêu:

**Service/component tests:** một dịch vụ thật cùng database/broker thực qua Testcontainers, còn dependency bên ngoài được mô phỏng có kiểm soát. Cách này tạo vòng phản hồi nhanh và cho phép kiểm tra phần lớn trường hợp lỗi mà không cần dựng toàn hệ thống.

**Contract tests:** kiểm tra định dạng request/response, schema event, thuộc tính bắt buộc, khả năng tương thích phiên bản và cách diễn giải mã lỗi giữa consumer/provider. Contract test phát hiện thay đổi phá vỡ kết nối sớm hơn E2E.

**E2E môi trường tạm thời hoặc staging:** triển khai những dịch vụ bắt buộc cho hành trình nghiệp vụ, dùng version và cấu hình rõ ràng. Môi trường nên có điểm vào tương tự production, nhưng dùng dữ liệu thử nghiệm và tích hợp thanh toán/email giả hoặc sandbox có hành vi kiểm soát được.

**Một số kiểm thử với hệ thống thật bên ngoài:** chỉ dành cho tích hợp trọng yếu cần bằng chứng ngoài phạm vi tổ chức; chạy thưa hơn, tránh ảnh hưởng dữ liệu thật và có cách phân biệt lỗi của đối tác với regression nội bộ.

Cố định image/tag, migration, cấu hình feature flag và seed data của môi trường theo một test run giúp điều tra dễ hơn. Dùng resource limit, health/readiness check và kiểm tra dependency đã sẵn sàng trước khi bắt đầu. Một TCP port mở chưa chắc nghĩa là database migration, consumer subscription hoặc ứng dụng đã sẵn sàng xử lý nghiệp vụ.

## 9. Retry: dùng có mục đích, không che lỗi

Cần phân biệt ba loại retry:

1. **Retry của ứng dụng:** cơ chế vận hành thực tế khi gặp lỗi tạm thời. Phải thử riêng behavior, timeout, backoff, idempotency và giới hạn số lần.
2. **Polling trong assertion:** đọc lại trạng thái cho tới khi đạt điều kiện hoặc hết deadline. Đây là cách đúng cho eventual consistency.
3. **Rerun toàn bài test vì FAIL:** có thể giúp thu thập bằng chứng về tính không ổn định, nhưng nếu tự động biến FAIL đầu tiên thành PASS cuối cùng rồi bỏ qua thì rất dễ che lỗi.

Nếu pipeline cho phép rerun, vẫn phải lưu lần thất bại ban đầu, số lần thử, trace ID và nguyên nhân; báo cáo ca đó là “passed on retry” hoặc “flaky suspected”, không đánh đồng với pass ổn định. Chỉ tạm cách ly một test khi có người phụ trách, issue theo dõi, tiêu chí phục hồi và thời hạn rà soát; không nên xóa âm thầm.

Tránh retry một POST không idempotent chỉ để test đi tiếp. Với thao tác tạo đơn/thanh toán, retry phải gắn với idempotency key hoặc cơ chế chống tác động kép đã được thiết kế.

## 10. Chẩn đoán lỗi bằng khả năng quan sát

Một bài E2E muốn đáng tin cần trả lời được **lỗi xảy ra ở dịch vụ nào và vào thời điểm nào**. Khi bắt đầu test, tạo test run ID hoặc correlation ID; đưa vào request header hoặc metadata của event khi kiến trúc hỗ trợ. Các dịch vụ nên phát tán trace context qua HTTP và message broker.

Khi FAIL, lưu tối thiểu:

- Tên test, phiên bản code/image/config, môi trường, thời gian bắt đầu và deadline.
- Request ID, order ID, trace/correlation ID và các trạng thái đã quan sát.
- HTTP status, payload lỗi đã loại bỏ bí mật, latency, tên dependency gây timeout.
- Log/trace của các dịch vụ liên quan; event publish/consume và retry/dead-letter nếu áp dụng.
- Với UI test: screenshot hoặc snapshot ở thời điểm lỗi, cùng locator đã dùng.

Một lỗi “không thấy CONFIRMED sau 30 giây” có thể là business logic sai, event chưa tới consumer, consumer retry, hàng đợi backlog hoặc một timeout hạ tầng. Trace và trạng thái trung gian giúp chuyển lỗi từ “không rõ, chạy lại thử” thành một sự kiện có thể phân loại và sửa đúng nơi.

Không nhúng token, mật khẩu, thông tin thanh toán hay dữ liệu cá nhân vào artifact CI. Cần che các trường nhạy cảm khi lưu request/response.

## 11. Xây dựng pipeline kiểm thử hợp lý

Có thể phân tầng pipeline như sau:

| Thời điểm | Bộ kiểm thử | Kỳ vọng phản hồi |
| --- | --- | --- |
| Trên máy lập trình viên và mỗi commit | Unit, component/integration nhanh, contract test | Phát hiện logic và sai hợp đồng sớm |
| Trên pull request | Một nhóm E2E smoke cho hành trình quan trọng; có thể chạy song song an toàn | Bảo đảm các dịch vụ phối hợp cơ bản |
| Trước phát hành hoặc theo lịch | E2E mở rộng, kiểm thử lỗi/khôi phục, tương thích phiên bản | Đánh giá hành trình có rủi ro cao |
| Sau triển khai có kiểm soát | Synthetic checks hoặc kiểm tra sức khỏe nghiệp vụ an toàn | Xác nhận đường đi quan trọng đang hoạt động |

Không cần dồn tất cả E2E vào mỗi commit nếu chi phí lớn và khả năng phản hồi chậm. Tuy nhiên, đường đi nào là điều kiện phát hành bắt buộc thì cần có gate rõ ràng và kế hoạch ứng phó khi fail.

Gợi ý tiêu chí hoàn thành một E2E smoke: tiền điều kiện tạo được, thời gian chạy nằm trong giới hạn đã thống nhất, có timeout hữu hạn, có trace/ID khi fail, dữ liệu độc lập, cleanup có kiểm soát, và assertion dựa trên kết quả nghiệp vụ. Những ngưỡng cụ thể phải lấy từ yêu cầu hệ thống và số liệu vận hành, không sao chép máy móc giữa các đội.

## 12. Đo lường và xử lý flaky test như một khoản nợ kỹ thuật

Theo dõi từng test và toàn bộ suite bằng các chỉ số:

- **Tỷ lệ không ổn định:** số lần có kết quả mâu thuẫn khi chạy lại trên cùng code/điều kiện chia cho số nhóm lần chạy đủ điều kiện quan sát. Công thức đo phải được thống nhất; không coi mọi FAIL là flaky.
- **Tỷ lệ fail và pass-on-retry:** phản ánh mức nhiễu của pipeline và nguy cơ đang che giấu lỗi.
- **Thời gian p50/p95/p99 và timeout:** cho biết test đang chậm dần hay môi trường thiếu tài nguyên.
- **Thời gian tìm nguyên nhân và sửa lỗi:** cho biết logging/tracing có hỗ trợ điều tra được hay không.
- **Top nguyên nhân:** race, test data, quota, UI selector, dependency, app regression… để ưu tiên sửa đúng nhóm.

Quy trình xử lý một test nghi flaky:

1. Thu thập commit, cấu hình, run ID và artifact của lần FAIL; không xóa mất bằng chứng.
2. Tái hiện có kiểm soát trên cùng revision; thử chạy độc lập và chạy song song để phát hiện va chạm dữ liệu.
3. Phân loại: logic thực sự sai, trạng thái eventual consistency, thời gian/đồng hồ, môi trường, phụ thuộc ngoài, hoặc test code.
4. Sửa nguyên nhân: chờ theo điều kiện, cô lập dữ liệu, ổn định dependency, tăng khả năng quan sát, hoặc chuyển ca xuống tầng phù hợp.
5. Chạy lại đủ để xác nhận tính ổn định theo chính sách của nhóm, khôi phục gate và tiếp tục đo.

Chỉ tăng timeout khi dữ liệu cho thấy timeout cũ nhỏ hơn giới hạn hợp lệ của hệ thống. Nếu timeout mới quá lớn, bài kiểm thử có thể phản ánh suy giảm hiệu năng thật cần được giải quyết.

## 13. Ví dụ quyết định phạm vi kiểm thử cho luồng đặt hàng

Giả sử Product Catalog, Order, Payment và Inventory là bốn microservices riêng, giao tiếp qua REST và sự kiện bất đồng bộ.

| Rủi ro cần chứng minh | Tầng ưu tiên | Vì sao |
| --- | --- | --- |
| Tổng tiền có nhiều tổ hợp thuế, phí, chiết khấu | Unit/component | Nhiều trường hợp biên, chạy nhanh và xác định |
| Payment API đổi tên trường hoặc mã lỗi | Contract | Phát hiện phá vỡ giao tiếp ở ranh giới |
| Consumer đọc event, cập nhật DB và xử lý duplicate | Integration/component | Kiểm soát broker, DB và event trùng lặp |
| Đặt hàng thành công từ gateway đến trạng thái CONFIRMED | E2E smoke | Kiểm chứng đường đi xuyên dịch vụ |
| Thanh toán bị từ chối thì đơn không xác nhận, kho được hoàn | E2E chọn lọc và component cho nhiều nhánh lỗi | Kiểm chứng phối hợp/bù trừ quan trọng |
| Mười kiểu email khách hàng không hợp lệ | Unit/API component | Không cần dựng nhiều dịch vụ |
| Hệ thống phục hồi sau broker outage kéo dài | Resilience/integration chuyên biệt và một E2E có kiểm soát | Cần kịch bản lỗi với giới hạn rõ |

Một bộ E2E nhỏ nhưng chứng minh được các điểm nối quan trọng thường mang lại tín hiệu phát hành tốt hơn một bộ kiểm thử rất lớn, chậm và phụ thuộc trạng thái dùng chung.

## 14. Những sai lầm cần tránh

- Viết hàng trăm E2E cho các nhánh validation đơn giản rồi bỏ qua unit/contract test.
- Dùng `Thread.sleep` với thời gian tùy ý cho mọi event bất đồng bộ.
- Dùng chung tài khoản, đơn hàng hoặc dữ liệu cố định giữa nhiều worker CI.
- Để test phụ thuộc thứ tự chạy hoặc phụ thuộc test khác tạo dữ liệu.
- Tự động rerun cho tới khi xanh và không lưu lần lỗi ban đầu.
- Coi mọi timeout là lỗi hạ tầng hoặc tăng timeout mà không có số liệu.
- Giả định rollback transaction của test khôi phục được nhiều database/service.
- Assert chi tiết triển khai nội bộ thay vì trạng thái nghiệp vụ.
- Cách ly một test flaky vô thời hạn mà không có người sở hữu.
- Chỉ báo “E2E failed” mà không có request ID, trace và trạng thái liên quan.

## 15. Checklist áp dụng trước khi đưa E2E vào CI

- [ ] Kịch bản bảo vệ một hành trình nghiệp vụ quan trọng, thực sự cần kiểm thử xuyên dịch vụ.
- [ ] Logic và hợp đồng đơn giản đã được thử ở tầng thấp hơn.
- [ ] Có tiền điều kiện và dữ liệu riêng cho mỗi lần chạy.
- [ ] Assertion dựa trên kết quả có thể quan sát, có deadline hữu hạn.
- [ ] Bất đồng bộ được chờ theo trạng thái, không phụ thuộc sleep cố định.
- [ ] Rerun không che lần FAIL đầu tiên; thao tác có side effect dùng idempotency đúng cách.
- [ ] Có correlation ID, log/trace và artifact đủ để chẩn đoán.
- [ ] Các test độc lập thứ tự và có giới hạn song song hợp lý.
- [ ] Cleanup/TTL và xử lý event đến muộn được định nghĩa.
- [ ] Vị trí trong pipeline, chủ sở hữu và tiêu chí xử lý flaky được thống nhất.

## Kết luận

Trong microservices, E2E là bằng chứng quan trọng rằng các dịch vụ kết hợp được thành một hành trình nghiệp vụ hoàn chỉnh, nhưng phạm vi rộng khiến nó chậm, khó chẩn đoán và dễ bị tác động bởi thời gian, dữ liệu cùng môi trường. Cách tiếp cận bền vững là giữ E2E cho các hành trình giá trị cao; dùng unit, component, integration và contract test cho phần lớn trường hợp; thiết kế dữ liệu độc lập; chờ theo trạng thái có timeout; và gắn quan sát, phân loại lỗi cùng số liệu flaky vào CI. Khi đó, một kết quả đỏ thực sự có ý nghĩa và đội ngũ có thể tin tưởng hơn vào tín hiệu phát hành.
