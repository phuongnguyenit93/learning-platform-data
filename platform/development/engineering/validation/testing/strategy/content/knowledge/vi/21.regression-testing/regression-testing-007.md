# Hồi quy: Thêm hồi quy cho lỗi thực tế ở tầng phát hiện phù hợp

## 1. Vì sao mỗi lỗi thực tế cần tạo ra một lớp bảo vệ?

Khi một defect được phát hiện trong quá trình phát triển, kiểm thử, UAT hoặc production, việc sửa mã nguồn chỉ giải quyết lần xuất hiện hiện tại. Nếu không bổ sung kiểm thử hồi quy phù hợp, cùng nguyên nhân có thể quay lại trong lần refactor, thay đổi cấu hình, nâng cấp dependency hoặc mở rộng tính năng tiếp theo.

Regression test là kiểm thử được giữ lại để phát hiện hành vi đã từng sai nếu lỗi tái xuất hiện. Một regression test có giá trị cần tái hiện được điều kiện gây lỗi, kiểm tra kết quả đúng theo yêu cầu và chạy ổn định ở tầng phù hợp.

Trong **VALIDATION_TESTING_STRATEGY**, mục tiêu không phải tạo một E2E test cho mọi defect. Cần xác định lỗi nằm ở đâu, điều kiện nào làm lỗi xuất hiện và tầng nào có thể bắt được lỗi với chi phí, độ tin cậy và phạm vi phù hợp:

- Lỗi trong một quy tắc tính toán thường được bảo vệ bằng unit test.
- Lỗi trong một thành phần và cách nó quản lý trạng thái có thể cần component test.
- Lỗi ở giao tiếp giữa hai dịch vụ cần integration hoặc contract test.
- Lỗi trong hành vi API có thể cần API/system test.
- Lỗi chỉ xuất hiện qua hành trình người dùng xuyên nhiều ranh giới có thể cần E2E test.

Tầng phát hiện phù hợp là tầng có thể tái hiện nguyên nhân hoặc điều kiện gây lỗi một cách đáng tin cậy, đồng thời kiểm tra được hợp đồng bị vi phạm. Nơi người dùng nhìn thấy triệu chứng không nhất thiết là nơi nên đặt toàn bộ kiểm thử hồi quy.

## 2. Phân biệt nơi phát hiện, nguyên nhân và tầng kiểm thử

### 2.1. Triệu chứng không luôn chỉ ra nguyên nhân

Một lỗi có thể được báo ở giao diện nhưng nguyên nhân nằm trong API, database, event consumer hoặc quy tắc nghiệp vụ. Ví dụ, người dùng không thấy lịch đã thanh toán có thể do:

- UI không làm mới dữ liệu.
- API lọc sai trạng thái.
- Worker không xử lý event xác nhận.
- Transaction được ghi nhưng event không được phát.
- Quy tắc chuyển trạng thái từ PAYMENT_PENDING sang CONFIRMED bị sai.

Nếu chỉ thêm một E2E test kiểm tra trang hiển thị lịch, test có thể phát hiện triệu chứng nhưng chưa giúp xác định chính xác ranh giới bị lỗi. Khi nguyên nhân đã rõ, nên thêm kiểm thử ở tầng có thể cô lập điều kiện gây lỗi.

### 2.2. Bốn khái niệm cần ghi riêng

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Nơi phát hiện (detection point) | Hoạt động hoặc môi trường nơi lỗi được nhìn thấy | UAT phát hiện lịch đã thanh toán không hiển thị |
| Triệu chứng (symptom) | Hành vi quan sát được không đúng | Người dùng thấy trạng thái PAYMENT_PENDING quá lâu |
| Nguyên nhân gốc (root cause) | Điều kiện hoặc lỗi thiết kế/triển khai tạo ra triệu chứng | Consumer bỏ qua event do sai mapping enum |
| Tầng regression | Tầng test phù hợp để bảo vệ nguyên nhân hoặc hợp đồng bị vi phạm | Integration test cho event mapping và trạng thái cuối |

Không nên chọn tầng regression chỉ dựa trên nơi lỗi được báo. Hãy truy vết từ triệu chứng về điều kiện, ranh giới và quy tắc bị vi phạm.

### 2.3. Mục tiêu của một regression test tốt

Một regression test nên:

- Thất bại khi lỗi cũ còn tồn tại.
- Thành công khi lỗi đã được sửa đúng.
- Kiểm tra hợp đồng hoặc bất biến có ý nghĩa.
- Có dữ liệu và điều kiện tái lập được.
- Không phụ thuộc vào thứ tự chạy hoặc dữ liệu của test khác.
- Có thông báo đủ rõ để chẩn đoán nếu lỗi tái xuất hiện.
- Chạy ở suite phù hợp với tốc độ phản hồi cần thiết.

Một test chỉ xác nhận mã HTTP 200 trong khi lỗi nằm ở dữ liệu cuối cùng có thể không đủ nhạy. Ngược lại, kiểm tra quá nhiều chi tiết nội bộ không liên quan có thể làm test giòn khi code được refactor.

## 3. Quy trình biến defect thực tế thành regression test

### 3.1. Bước 1 — Thu thập bằng chứng và mô tả lỗi

Trước khi sửa, ghi nhận:

- Phiên bản ứng dụng, commit hoặc release bị ảnh hưởng.
- Môi trường và cấu hình.
- Vai trò người dùng hoặc service identity.
- Dữ liệu đầu vào và trạng thái ban đầu.
- Các bước hoặc chuỗi sự kiện dẫn tới lỗi.
- Kết quả mong đợi và kết quả thực tế.
- Log, trace, request ID, transaction ID hoặc ảnh chụp phù hợp.
- Tần suất và phạm vi ảnh hưởng nếu đã biết.

Mô tả cần đủ cụ thể để một người khác có thể hiểu điều kiện gây lỗi. Tránh ghi đơn giản “đôi lúc không đặt được lịch” nếu có thể bổ sung khung giờ, trạng thái thanh toán, thời điểm callback và mã tham chiếu.

### 3.2. Bước 2 — Tái hiện lỗi có kiểm soát

Tái hiện giúp xác nhận triệu chứng và loại trừ các nguyên nhân do môi trường hoặc dữ liệu. Hãy:

1. Dùng phiên bản bị lỗi hoặc một nhánh có thể tái tạo trạng thái đó.
2. Chuẩn bị dữ liệu và quyền giống điều kiện gây lỗi.
3. Thực hiện các bước theo đúng thứ tự.
4. Quan sát cùng một oracle đã dùng để nhận diện lỗi.
5. Lặp lại khi lỗi phụ thuộc thời gian, concurrency hoặc event bất đồng bộ.
6. Lưu lại bằng chứng và seed/dữ liệu để tái tạo.

Không phải defect nào cũng tái hiện được ngay. Với lỗi hiếm hoặc chỉ xuất hiện ở production, có thể cần tạo test harness, mô phỏng event, khôi phục snapshot đã được phê duyệt hoặc bổ sung telemetry. Nếu chưa tái hiện được, ghi rõ mức độ chắc chắn và điều kiện còn thiếu.

### 3.3. Bước 3 — Xác định nguyên nhân và hợp đồng bị vi phạm

Phân tích:

- Quy tắc nghiệp vụ nào không được thực hiện đúng?
- Thành phần nào tạo ra kết quả sai?
- Lỗi nằm trong logic, dữ liệu, trạng thái, cấu hình hay tương tác?
- Có ranh giới nào giữa các thành phần bị vi phạm không?
- Điều kiện nào là cần thiết để lỗi xuất hiện?
- Có trường hợp tương tự ở đường đi khác không?

Root cause nên được mô tả bằng điều kiện kỹ thuật hoặc quy tắc cụ thể. Ví dụ: “consumer chuyển đổi trường payment_status không nhận enum SETTLED” rõ hơn “lỗi đồng bộ thanh toán”.

### 3.4. Bước 4 — Chọn tầng kiểm thử

Chọn tầng thấp nhất có thể tái hiện và xác nhận đáng tin cậy nguyên nhân. Nếu lỗi xuất phát từ tương tác giữa các thành phần, cần kiểm tra ranh giới đó; không cố ép nó vào unit test bằng cách mock chính hành vi đang bị lỗi.

### 3.5. Bước 5 — Viết test trước hoặc cùng lúc với bản sửa

Khi có thể, tạo regression test trên phiên bản còn lỗi và xác nhận test thất bại vì đúng nguyên nhân. Sau đó áp dụng bản sửa và xác nhận test thành công.

Chu trình này chứng minh test có khả năng phát hiện defect. Nếu test chỉ được viết sau khi sửa mà chưa từng chạy trên trạng thái lỗi, cần kiểm tra lại dữ liệu, oracle và độ nhạy của nó.

### 3.6. Bước 6 — Chạy kiểm tra liên quan và tích hợp vào suite

Sau khi regression test pass:

- Chạy test mới độc lập.
- Chạy test liên quan ở cùng module hoặc ranh giới.
- Chạy suite phù hợp để phát hiện tác động phụ.
- Xác nhận test chạy lại ổn định.
- Gắn test với defect, yêu cầu hoặc risk record nếu có cơ chế truy vết.
- Đặt test vào pipeline đúng tầng để phản hồi đủ nhanh.

~~~mermaid
flowchart TD
    A["Defect thực tế được ghi nhận"] --> B["Thu thập điều kiện và bằng chứng"]
    B --> C["Tái hiện triệu chứng"]
    C --> D["Phân tích root cause và hợp đồng bị vi phạm"]
    D --> E["Chọn tầng regression phù hợp"]
    E --> F["Viết test trên trạng thái còn lỗi"]
    F --> G{"Test bắt đúng lỗi?"}
    G -->|"Không"| H["Rà soát dữ liệu, oracle và tầng test"]
    H --> F
    G -->|"Có"| I["Áp dụng bản sửa"]
    I --> J["Chạy test và suite liên quan"]
    J --> K["Gắn truy vết và đưa vào CI"]
~~~

## 4. Chọn tầng regression theo bản chất lỗi

### 4.1. Unit test — lỗi trong logic cô lập

Dùng unit test khi nguyên nhân nằm trong một hàm, lớp hoặc quy tắc có thể kiểm tra độc lập.

Phù hợp với:

- Điều kiện so sánh sai.
- Công thức tính phí hoặc thuế sai.
- Xử lý null, giá trị biên hoặc timezone sai trong một hàm.
- Nhánh xử lý ngoại lệ bị bỏ sót.
- Chuyển đổi dữ liệu hoặc enum sai trong một module.

Ví dụ: phí hủy bằng 0 khi thời gian còn lại đúng 24 giờ do toán tử lớn hơn được dùng thay cho lớn hơn hoặc bằng. Regression test cần kiểm tra ngay dưới, đúng tại và ngay trên ngưỡng theo độ chính xác thời gian được hỗ trợ.

Unit test nên kiểm tra quy tắc với dữ liệu đầu vào và kết quả cụ thể. Không cần dựng UI hoặc database nếu các thành phần đó không tham gia nguyên nhân.

### 4.2. Component test — lỗi trong hành vi của một thành phần

Dùng component test khi lỗi nằm trong cách một thành phần quản lý trạng thái, persistence hoặc phối hợp các lớp nội bộ.

Phù hợp với:

- Một service ghi sai trạng thái vào database.
- Một worker xử lý sai message trong ranh giới component.
- Một repository bỏ sót điều kiện lọc.
- Một thành phần không thực hiện rollback khi thao tác thất bại.

Ví dụ: booking service cho phép xác nhận hai lịch cùng một slot do kiểm tra availability và ghi booking không nằm trong transaction phù hợp. Component test có thể chạy service cùng database thật trong container và gửi hai yêu cầu cạnh tranh.

### 4.3. Integration hoặc contract test — lỗi ở ranh giới thành phần

Dùng integration test khi nguyên nhân liên quan đến giao tiếp giữa các thành phần hoặc cách hai bên hiểu hợp đồng.

Phù hợp với:

- JSON field hoặc enum mapping sai.
- Schema event thay đổi nhưng consumer chưa cập nhật.
- Sai header, authentication scope hoặc serialization.
- Transaction và event không nhất quán.
- Retry hoặc idempotency giữa producer và consumer không đúng.

Ví dụ: producer phát event PaymentSettled, nhưng consumer chỉ nhận PaymentSucceeded. Regression test nên xác nhận event thực tế qua broker hoặc contract phù hợp và trạng thái cuối được cập nhật.

### 4.4. API hoặc system test — lỗi ở hợp đồng dịch vụ

Dùng API/system test khi defect biểu hiện qua hợp đồng dịch vụ hoặc cần nhiều thành phần trong một hệ thống để tái hiện.

Phù hợp với:

- Endpoint trả sai status hoặc response schema.
- Phân quyền API không đúng.
- Trạng thái cuối hoặc tác dụng phụ sai qua nhiều module.
- Filter, pagination hoặc transaction behavior sai trong hệ thống đã triển khai.

Ví dụ: API cho phép người dùng tenant A đọc lịch của tenant B. Regression test gọi endpoint bằng hai danh tính riêng và xác nhận dữ liệu bị từ chối theo hợp đồng, đồng thời không để lộ nội dung bản ghi.

### 4.5. E2E test — lỗi chỉ xuất hiện trong hành trình xuyên nhiều ranh giới

Dùng E2E khi nguyên nhân phụ thuộc vào phối hợp của nhiều thành phần hoặc một luồng người dùng mà các tầng thấp hơn không thể đại diện đầy đủ.

Phù hợp với:

- Điều hướng UI, API và worker phối hợp sai.
- Session hoặc cookie mất trong hành trình.
- Một thay đổi cấu hình khiến luồng người dùng không hoàn tất.
- Chuỗi thao tác nhiều bước tạo trạng thái cuối sai mà không thể cô lập ở tầng thấp hơn.

Ví dụ: người dùng hoàn tất thanh toán nhưng UI vẫn hiển thị bước thanh toán chưa hoàn tất vì redirect và callback không phối hợp đúng. Có thể cần một E2E test đại diện, đồng thời thêm test thấp hơn cho logic callback nếu root cause đã được xác định.

### 4.6. Bảng chọn tầng nhanh

| Dạng defect | Tầng thường phù hợp | Oracle cần kiểm tra |
| --- | --- | --- |
| Sai điều kiện hoặc công thức | Unit | Kết quả và giá trị biên |
| Sai trạng thái trong một service | Component | Trạng thái lưu và bất biến |
| Sai schema hoặc mapping giữa service | Contract/integration | Payload, schema và trạng thái consumer |
| Race condition ở persistence | Component/integration | Chỉ một kết quả hợp lệ, transaction và dữ liệu cuối |
| Sai quyền qua API | API/system | Response, dữ liệu không bị lộ và audit |
| Lỗi hành trình nhiều bước | E2E/system | Kết quả người dùng và tác dụng phụ cuối |
| Lỗi hiển thị riêng ở browser/device | UI/component hoặc E2E theo phạm vi | Nội dung, trạng thái và hành vi trên nền tảng |
| Lỗi hiệu năng tái diễn | Performance regression ở môi trường đo phù hợp | Latency, throughput, error rate và tài nguyên |

## 5. Tầng phát hiện không đồng nghĩa với tầng duy nhất cần kiểm thử

Một defect có thể cần nhiều bằng chứng nếu có các rủi ro khác nhau:

- Một unit test bảo vệ logic gốc.
- Một integration test bảo vệ hợp đồng giữa producer và consumer.
- Một E2E test đại diện bảo vệ hành trình người dùng quan trọng.

Tuy nhiên, không nên nhân bản cùng một kịch bản ở mọi tầng nếu chúng không thêm giá trị. Nhiều test giống nhau làm tăng thời gian chạy, chi phí bảo trì và nguy cơ flaky.

Hãy tách mục tiêu:

| Tầng | Câu hỏi cần trả lời |
| --- | --- |
| Unit | Quy tắc có tính đúng trong các điều kiện đã xác định không? |
| Component | Thành phần có duy trì trạng thái và bất biến đúng không? |
| Integration | Các thành phần có hiểu và thực hiện đúng hợp đồng không? |
| E2E | Người dùng có hoàn tất hành trình quan trọng và nhận kết quả đúng không? |

Nếu một lỗi phát hiện ở production do hai dịch vụ không tương thích, unit test cho parser có thể bảo vệ một phần logic, nhưng integration/contract test mới xác nhận được hợp đồng giữa hai dịch vụ. Chọn test theo rủi ro được bảo vệ, không theo số lượng tầng.

## 6. Thiết kế regression test có khả năng bắt lỗi

### 6.1. Tái hiện điều kiện tối thiểu nhưng đủ

Tạo dữ liệu nhỏ nhất có thể làm lỗi xuất hiện, đồng thời giữ lại các điều kiện cần thiết:

- Trạng thái ban đầu.
- Vai trò và quyền.
- Dữ liệu đầu vào hoặc quan hệ.
- Thứ tự hành động/sự kiện.
- Thời gian, timezone hoặc concurrency nếu có.
- Cấu hình và phiên bản dependency liên quan.

Giảm bớt các yếu tố không liên quan giúp test nhanh và dễ chẩn đoán. Nhưng nếu loại bỏ điều kiện quan trọng, test có thể không còn tái hiện đúng nguyên nhân.

### 6.2. Xác định oracle theo hợp đồng bị vi phạm

Oracle cần kiểm tra điều mà defect đã phá vỡ. Tùy lỗi, có thể là:

- Giá trị trả về hoặc mã lỗi.
- Trạng thái cuối trong database.
- Bất biến giữa nhiều bản ghi.
- Event được phát hoặc được tiêu thụ đúng.
- Số lần tác dụng phụ được thực hiện.
- Dữ liệu không bị lộ hoặc thay đổi ngoài quyền.
- Hành trình người dùng hoàn tất đúng.

Không chỉ xác nhận test không còn crash. Một defect có thể được “sửa” theo cách che lỗi nhưng vẫn tạo ra dữ liệu sai hoặc tác dụng phụ trùng lặp.

### 6.3. Kiểm tra cả điều kiện gây lỗi và trường hợp lân cận

Một regression test tập trung vào một điều kiện có thể bỏ sót lỗi ở biên. Khi phù hợp, thêm các trường hợp lân cận:

- Ngay dưới, đúng tại và ngay trên ngưỡng.
- Trạng thái trước và sau chuyển tiếp.
- Vai trò được phép và không được phép.
- Event hợp lệ, lặp, trễ và sai thứ tự.
- Giá trị bình thường và giá trị cực trị.

Không mở rộng test vô hạn. Chọn các trường hợp lân cận theo cùng quy tắc và rủi ro liên quan.

### 6.4. Dùng assertion cụ thể

Ví dụ kém nhạy:

~~~ts
expect(response.ok).toBe(true);
~~~

Nếu lỗi nằm ở việc ghi trùng thanh toán, assertion trên có thể vẫn pass. Một oracle cụ thể hơn:

~~~ts
expect(response.status).toBe(202);
await waitForPaymentState(paymentId, "SETTLED");
expect(await countLedgerEntries(paymentId)).toBe(1);
~~~

Đoạn mã minh họa. Cần điều chỉnh status, trạng thái cuối và số lượng bản ghi theo hợp đồng thực tế của hệ thống.

### 6.5. Tránh phụ thuộc vào chi tiết triển khai

Regression test nên thất bại khi lỗi cũ quay lại, không nhất thiết thất bại khi code được tái cấu trúc mà hợp đồng vẫn giữ nguyên.

Ưu tiên:

- Kiểm tra API contract thay vì private method không công khai.
- Kiểm tra trạng thái và tác dụng phụ thay vì thứ tự gọi hàm nội bộ.
- Kiểm tra quyền truy cập và kết quả thay vì tên biến hoặc cấu trúc lớp.
- Dùng selector UI ổn định theo vai trò/nhãn thay vì vị trí DOM.

## 7. Ví dụ thực tế theo từng tầng

### 7.1. Defect: sai ngưỡng phí hủy

**Triệu chứng:** lịch được hủy đúng tại mốc 24 giờ nhưng hệ thống tính phí sai.

**Nguyên nhân:** code dùng điều kiện lớn hơn thay vì lớn hơn hoặc bằng.

**Regression phù hợp:** unit test cho quy tắc tính phí.

~~~ts
describe("cancellation fee boundary", () => {
  test("waives the fee at exactly 24 hours before appointment", () => {
    const now = instant("2026-05-10T10:00:00Z");
    const appointmentAt = instant("2026-05-11T10:00:00Z");

    expect(cancellationFee(now, appointmentAt)).toBe(0);
  });
});
~~~

Nên bổ sung trường hợp ngay dưới và ngay trên ngưỡng theo độ chính xác hệ thống. Không cần E2E nếu lỗi chỉ nằm trong hàm quyết định và không phụ thuộc UI hoặc tích hợp.

### 7.2. Defect: event thanh toán không được consumer nhận

**Triệu chứng:** giao dịch đã thanh toán nhưng đơn vẫn ở trạng thái chờ.

**Nguyên nhân:** producer và consumer dùng tên event hoặc enum không tương thích.

**Regression phù hợp:** contract/integration test.

~~~ts
test("consumer confirms an order for a settled payment event", async () => {
  const order = await createOrderInPaymentPendingState();

  await publishPaymentEvent({
    type: "PaymentSettled",
    orderId: order.id,
    paymentId: "pay-test-42"
  });

  await waitForOrderState(order.id, "CONFIRMED");
  expect(await countPaymentRecords(order.id)).toBe(1);
});
~~~

Test cần dùng schema và broker phù hợp với ranh giới đang bảo vệ. Nếu chỉ gọi trực tiếp hàm consumer với object dựng sẵn, nó có thể không bắt được lỗi serialization hoặc routing.

### 7.3. Defect: người dùng đọc được lịch của tenant khác

**Triệu chứng:** tài khoản tenant A có thể truy cập lịch thuộc tenant B.

**Nguyên nhân:** API truy vấn theo appointment ID nhưng thiếu điều kiện tenant/ownership.

**Regression phù hợp:** API/system test với hai danh tính và dữ liệu thuộc hai tenant.

~~~ts
test("user cannot read an appointment owned by another tenant", async () => {
  const tenantA = await createTenantAndUser();
  const tenantB = await createTenantAndUser();
  const appointment = await createAppointment({ tenantId: tenantB.id });

  const response = await apiAs(tenantA.user).get(
    "/appointments/" + appointment.id
  );

  expect(response.status).toBe(404);
  expect(response.body).not.toHaveProperty("customerDetails");
});
~~~

Mã trạng thái cụ thể phụ thuộc chính sách che giấu tài nguyên và API contract. Test phải xác nhận cả quyền truy cập và việc không tiết lộ dữ liệu.

### 7.4. Defect: UI không hoàn tất hành trình sau redirect

**Triệu chứng:** người dùng thanh toán thành công nhưng trang vẫn ở bước thanh toán.

**Nguyên nhân:** callback và redirect cập nhật trạng thái theo thứ tự khác nhau; UI không làm mới khi trạng thái cuối đến muộn.

**Regression phù hợp:** một E2E test đại diện cho hành trình, cộng test thấp hơn nếu có root cause cụ thể ở callback hoặc state update.

Test E2E nên xác nhận:

- Người dùng bắt đầu đặt lịch.
- Sandbox trả kết quả thanh toán thành công.
- Hành trình quay lại ứng dụng.
- UI cuối cùng hiển thị xác nhận.
- API hoặc trạng thái nguồn xác nhận lịch đã được tạo đúng.

Không chỉ kiểm tra thông báo “Thành công” nếu trạng thái lưu và lịch thực tế có thể chưa được xác nhận.

## 8. Đưa regression test vào pipeline

### 8.1. Chạy ở suite có tốc độ phù hợp

| Suite | Nội dung regression | Thời điểm gợi ý |
| --- | --- | --- |
| Unit/fast | Quy tắc logic, giá trị biên, lỗi đã cô lập | Mỗi commit hoặc pull request |
| Component | Trạng thái và hành vi trong một thành phần | Mỗi pull request hoặc pipeline liên quan |
| Contract/integration | Schema, API, database, event và dependency | Khi thay đổi ranh giới hoặc theo lịch CI |
| System/API | Hợp đồng dịch vụ và hành vi hệ thống | Pull request quan trọng, build candidate |
| E2E/smoke | Hành trình nghiệp vụ rủi ro cao | Build candidate, staging hoặc lịch chạy phù hợp |
| Performance/security | Hồi quy thuộc tính phi chức năng | Pipeline chuyên biệt, theo thay đổi và lịch |

Đây là gợi ý tổ chức. Tần suất cần dựa trên thời gian chạy, độ ổn định, chi phí môi trường và mức rủi ro.

### 8.2. Tránh đưa mọi test vào đường phản hồi nhanh

Nếu một regression test cần nhiều dịch vụ và thời gian dài, có thể đặt nó ở suite integration hoặc E2E. Tuy nhiên, nếu có thể tạo một test nhỏ hơn bắt đúng nguyên nhân, nên dùng test đó làm lớp phản hồi nhanh và giữ thêm kiểm tra hành trình nếu nó bảo vệ một rủi ro riêng.

Không bỏ regression test chỉ vì nó chậm. Hãy xem xét:

- Tối ưu setup và dữ liệu.
- Dùng environment riêng hoặc ephemeral.
- Chạy theo change impact hoặc tag.
- Tách phần kiểm tra nhanh và phần kiểm tra sâu.
- Chạy song song khi test độc lập và tài nguyên được cô lập.

### 8.3. Gắn nhãn và truy vết

Mỗi regression test nên liên kết với một hoặc nhiều thông tin:

- Defect ID hoặc incident ID.
- Yêu cầu, acceptance criteria hoặc risk.
- Thành phần và tầng kiểm thử.
- Suite hoặc tag CI.
- Người sở hữu khi test cần bảo trì.

Liên kết này giúp nhóm hiểu tại sao test tồn tại. Tránh chỉ đặt tên chung như regression_123 mà không có mô tả hành vi.

## 9. Xử lý regression test không ổn định

### 9.1. Không coi retry là cách sửa

Nếu test pass lúc có lúc không, cần phân loại:

- Điều kiện race hoặc event bất đồng bộ.
- Dữ liệu dùng chung giữa test.
- Clock hoặc timezone không được kiểm soát.
- Dependency hoặc sandbox không ổn định.
- Timeout không phù hợp.
- Oracle dựa vào thời điểm hoặc thứ tự không bảo đảm.

Ghi lại lần thất bại đầu, môi trường và bằng chứng. Retry có thể giúp phân biệt lỗi tạm thời, nhưng không được làm mất dấu lỗi ban đầu.

### 9.2. Sửa test hay sửa sản phẩm?

Khi regression test mới thất bại sau một thay đổi, xác định:

1. Hợp đồng hoặc yêu cầu có thay đổi được phê duyệt không?
2. Sản phẩm có tái tạo defect cũ không?
3. Dữ liệu test có còn hợp lệ với schema mới không?
4. Oracle có phản ánh đúng quy tắc hiện tại không?
5. Môi trường và dependency có tương thích không?

Không thay expected result chỉ để pipeline xanh. Nếu yêu cầu thay đổi, cập nhật tiêu chí và truy vết; nếu hành vi sai, sửa sản phẩm.

### 9.3. Khi nào được loại bỏ một regression test?

Chỉ cân nhắc bỏ khi:

- Hành vi đã được bảo vệ ở một tầng khác có độ tin cậy tương đương hoặc tốt hơn.
- Test trùng lặp mà không tăng coverage hoặc tín hiệu.
- Tính năng đã bị loại bỏ và không còn hợp đồng cần bảo vệ.
- Test dựa trên chi tiết triển khai không còn phù hợp và đã được thay thế.

Trước khi bỏ, xác định defect/risk mà test đang bảo vệ và ghi nhận test thay thế nếu có. Không xóa test chỉ vì nó thường xuyên làm pipeline đỏ mà chưa tìm nguyên nhân.

## 10. Đo lường chất lượng regression suite

Số lượng regression test không phản ánh trực tiếp khả năng ngăn lỗi tái xuất hiện. Có thể theo dõi:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Defect có regression test | Cho biết lỗi thực tế đã được chuyển thành kiểm tra tự động ở phạm vi nào |
| Regression test fail-before-fix | Bằng chứng test có thể bắt đúng lỗi khi tái hiện được |
| Tỷ lệ flaky | Độ ổn định của suite |
| Thời gian phản hồi theo suite | Chi phí nhận tín hiệu lỗi |
| Defect tái xuất hiện | Tín hiệu về khoảng trống trong test hoặc quy trình |
| Regression theo rủi ro/thành phần | Khu vực quan trọng đã có lớp bảo vệ hay chưa |
| Test không còn giá trị | Test trùng lặp, không có oracle hoặc không còn liên quan |

Không dùng một chỉ số đơn lẻ làm mục tiêu. Ví dụ, tăng số test có thể làm suite chậm và trùng lặp. Tỷ lệ defect có test cũng cần diễn giải theo khả năng tái hiện và mức rủi ro, không chỉ đếm số lượng.

## 11. Mẫu ghi nhận regression test cho defect

~~~text
Defect / incident ID:
Tên hành vi cần bảo vệ:
Phiên bản phát hiện:
Môi trường:

Triệu chứng:
Kết quả mong đợi:
Kết quả thực tế:
Điều kiện tái hiện:
- Dữ liệu:
- Vai trò:
- Trạng thái ban đầu:
- Thứ tự hành động/sự kiện:
- Cấu hình/phụ thuộc:

Root cause:
Hợp đồng hoặc bất biến bị vi phạm:
Tầng regression được chọn:
Lý do chọn tầng:
Oracle / assertion:

Test thất bại trên phiên bản còn lỗi:
Kết quả sau bản sửa:
Suite / pipeline:
Liên kết yêu cầu hoặc risk:
Giới hạn và phần chưa được bảo vệ:
~~~

## 12. Checklist thêm regression cho lỗi thực tế

- [ ] Defect có mô tả triệu chứng, môi trường và phiên bản.
- [ ] Dữ liệu, vai trò, trạng thái và thứ tự sự kiện gây lỗi được ghi lại.
- [ ] Lỗi đã được tái hiện hoặc giới hạn chưa tái hiện được đã được nêu rõ.
- [ ] Root cause và hợp đồng bị vi phạm đã được xác định ở mức đủ cụ thể.
- [ ] Tầng regression được chọn theo nguyên nhân và ranh giới cần bảo vệ.
- [ ] Test có dữ liệu tối thiểu nhưng vẫn tái hiện đúng điều kiện.
- [ ] Oracle kiểm tra kết quả nghiệp vụ, trạng thái hoặc tác dụng phụ liên quan.
- [ ] Test thất bại trên trạng thái còn lỗi khi có thể tái hiện.
- [ ] Test pass sau bản sửa và chạy ổn định khi lặp lại.
- [ ] Các trường hợp biên hoặc lân cận quan trọng đã được xem xét.
- [ ] Test không phụ thuộc vào thứ tự, dữ liệu dùng chung hoặc chi tiết nội bộ không cần thiết.
- [ ] Regression test được đặt vào suite/pipeline có tốc độ phù hợp.
- [ ] Test được liên kết với defect, yêu cầu hoặc risk.
- [ ] Những rủi ro chưa được bảo vệ ở tầng khác được ghi nhận.

Thêm regression cho lỗi thực tế là cách chuyển kinh nghiệm từ một lần thất bại thành bằng chứng có thể kiểm tra lại trong tương lai. Khi phân biệt triệu chứng với nguyên nhân, chọn đúng tầng, xác nhận test bắt được lỗi và đặt nó vào pipeline phù hợp, nhóm giảm khả năng tái diễn mà không làm bộ kiểm thử phình to bởi các E2E trùng lặp.
