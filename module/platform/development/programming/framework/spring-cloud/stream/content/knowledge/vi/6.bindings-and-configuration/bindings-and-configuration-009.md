# Điều khiển autoStartup và xử lý lỗi liên kết lúc khởi động

Khi một ứng dụng Spring Cloud Stream khởi động, framework tạo các binding và kết nối chúng với broker thông qua binder. Với binding đầu vào, quá trình này còn liên quan đến việc khởi chạy consumer để nhận message. Nếu broker chưa sẵn sàng, thông tin xác thực sai hoặc tài nguyên chưa được provision, ứng dụng có thể gặp lỗi trước khi xử lý được message đầu tiên.

Spring Cloud Stream cung cấp hai nhóm cấu hình cần phân biệt. `autoStartup` điều khiển việc consumer binding có tự khởi chạy cùng ứng dụng hay không. `bindingRetryInterval` điều khiển khoảng chờ giữa các lần thử bind consumer khi quá trình bind gặp lỗi trong giai đoạn khởi động. Chúng giải quyết hai nhu cầu khác nhau: chủ động trì hoãn việc nhận message và xử lý tình huống binder chưa thể kết nối hoặc tạo binding.

Bài thuộc chương **Binding và cấu hình** của module `SPRING_CLOUD_STREAM`. Module sử dụng mô hình hàm `Supplier`/`Function`/`Consumer`, binding và binder để làm việc với Kafka, RabbitMQ hoặc Pulsar. Nội dung dưới đây tập trung vào vòng đời khởi động của binding, cách chọn chính sách phù hợp và cách chẩn đoán lỗi mà không che giấu một ứng dụng chưa sẵn sàng.

## 1. Điều gì diễn ra khi ứng dụng khởi động?

Một ứng dụng Spring Boot dùng Spring Cloud Stream thường trải qua các bước tổng quát sau:

1. Spring Boot tạo application context và khởi tạo các bean, bao gồm các hàm `Supplier`, `Function` hoặc `Consumer`.
2. Spring Cloud Stream đọc cấu hình binding, destination, group và binder tương ứng.
3. Binder thiết lập kết nối tới broker, kiểm tra hoặc provision tài nguyên cần thiết theo cấu hình và quyền được cấp.
4. Binding đầu vào được nối với destination; consumer endpoint hoặc listener container được chuẩn bị.
5. Nếu consumer được phép tự khởi chạy, nó bắt đầu nhận message.
6. Ứng dụng tiếp tục phục vụ các thành phần khác và báo trạng thái sức khỏe theo cơ chế của ứng dụng.

Trên thực tế, chi tiết thứ tự và cách retry có thể khác nhau theo binder và phiên bản Spring Cloud Stream. Điều quan trọng là phân biệt lỗi tạo application context, lỗi kết nối/provision tài nguyên, lỗi bind và lỗi phát sinh khi xử lý message. Chúng xảy ra ở những giai đoạn khác nhau và cần cách xử lý riêng.

```text
Spring Boot context
       |
       v
Function beans + binding configuration
       |
       v
Binder connection / resource provisioning
       |
       v
Input binding created
       |
       +---- autoStartup=true ----> Consumer starts
       |
       +---- autoStartup=false ---> Consumer remains stopped
                                      until explicitly started
```

## 2. `autoStartup` làm gì?

`autoStartup` là thuộc tính của consumer binding, cho biết consumer có tự động bắt đầu nhận message trong quá trình ứng dụng khởi động hay không. Giá trị mặc định thường là `true`.

- `true`: consumer được khởi chạy tự động khi binding sẵn sàng.
- `false`: consumer binding không tự khởi chạy; ứng dụng hoặc cơ chế quản lý vòng đời phải chủ động khởi động nó khi điều kiện phù hợp.

Ví dụ một dịch vụ thanh toán cần đợi bước nạp cấu hình nghiệp vụ hoàn tất trước khi nhận đơn hàng:

```yaml
spring:
  cloud:
    function:
      definition: processPayment
    stream:
      bindings:
        processPayment-in-0:
          destination: orders.validated
          group: payment-service
          consumer:
            auto-startup: false
```

Khi `auto-startup` là `false`, consumer không bắt đầu tiêu thụ tự động. Điều này hữu ích khi ứng dụng cần hoàn tất một bước chuẩn bị trước khi xử lý message, khi muốn điều khiển thời điểm tiếp nhận tải hoặc khi triển khai một cơ chế bật/tắt consumer có chủ đích.

`autoStartup` không phải công tắc tắt toàn bộ Spring Cloud Stream. Framework vẫn phải đọc cấu hình và tạo các thành phần binding cần thiết; binder có thể vẫn cần khởi tạo hoặc provision tài nguyên tùy cách triển khai. Vì vậy, không nên dựa vào `autoStartup=false` để che lỗi broker, sai credentials hoặc cấu hình destination không hợp lệ.

## 3. Khởi chạy consumer có kiểm soát

Khi tắt tự khởi chạy, ứng dụng cần một thời điểm rõ ràng để bắt đầu consumer. Có thể dùng cơ chế quản lý vòng đời binding do Spring Cloud Stream cung cấp, chẳng hạn controller hoặc endpoint quản trị binding ở những phiên bản hỗ trợ. Tên binding được dùng để điều khiển phải khớp với binding name mà framework tạo ra, ví dụ `processPayment-in-0`.

Một quy trình hợp lý có thể là:

1. Ứng dụng khởi tạo context và nạp cấu hình.
2. Kiểm tra các dependency bắt buộc của nghiệp vụ, chẳng hạn database, bảng tham chiếu hoặc khóa mã hóa.
3. Kiểm tra readiness của ứng dụng và quyền truy cập broker.
4. Khi điều kiện đã đạt, yêu cầu lifecycle controller khởi chạy binding đầu vào.
5. Theo dõi trạng thái consumer và lag sau khi bắt đầu nhận message.

Không nên gọi start ngay khi context vừa được tạo nếu các dependency cần thiết vẫn chưa sẵn sàng. Ngược lại, nếu không có cơ chế nào khởi chạy binding, consumer sẽ tiếp tục ở trạng thái dừng và message có thể tích tụ tại broker.

Nếu dùng actuator để điều khiển binding, chỉ expose endpoint quản trị trên mạng nội bộ có xác thực và phân quyền. Không công khai thao tác start/stop binding cho người dùng cuối. API và trạng thái cụ thể của endpoint phụ thuộc phiên bản Spring Cloud Stream; cần đối chiếu tài liệu đúng phiên bản trước khi viết automation vận hành.

## 4. Xử lý lỗi bind lúc khởi động với `bindingRetryInterval`

Một consumer binding có thể chưa bind được ngay khi ứng dụng khởi động. Ví dụ broker đang khởi động, DNS chưa phân giải được, kết nối mạng tạm thời lỗi hoặc quyền tạo queue/topic chưa sẵn sàng. Spring Cloud Stream có thuộc tính cấp ứng dụng `spring.cloud.stream.bindingRetryInterval` để đặt khoảng chờ giữa các lần thử bind consumer trong giai đoạn startup.

Ví dụ cấu hình khoảng chờ 10 giây:

```yaml
spring:
  cloud:
    stream:
      binding-retry-interval: 10
```

Giá trị được tính bằng giây. Khi bind thất bại, framework chờ khoảng thời gian cấu hình rồi thử lại theo cơ chế của phiên bản đang dùng. Nếu đặt giá trị bằng `0`, ứng dụng chọn hành vi fail-fast: lỗi bind khiến quá trình khởi động thất bại thay vì chờ retry.

Chọn giá trị theo môi trường:

| Môi trường | Cách cân nhắc |
|---|---|
| Local development | Có thể dùng khoảng retry ngắn để chờ broker local vừa khởi động |
| Integration test | Thường nên fail-fast hoặc dùng thời gian chờ ngắn để test phát hiện lỗi cấu hình nhanh |
| Staging | Dùng retry có giới hạn phù hợp với thời gian khởi tạo hạ tầng và kiểm tra readiness rõ ràng |
| Production | Phối hợp retry với health check, timeout triển khai và chính sách restart của nền tảng; không để lỗi cấu hình cố định bị che khuất quá lâu |

`bindingRetryInterval` không thay thế retry khi xử lý message. Nó liên quan đến việc bind consumer destination trong startup. Lỗi xảy ra sau khi consumer đã chạy, ví dụ hàm ném exception khi xử lý payload, thuộc luồng xử lý lỗi runtime và cần cấu hình retry/DLQ phù hợp.

## 5. Phân biệt lỗi startup và lỗi runtime

Không phải mọi lỗi đều nên xử lý bằng cùng một cơ chế:

| Giai đoạn | Ví dụ lỗi | Cách tiếp cận |
|---|---|---|
| Tạo application context | Bean function thiếu dependency, cấu hình YAML sai kiểu, không tìm thấy binder class | Sửa code/dependency/cấu hình; retry thường không giúp |
| Kết nối binder | Broker chưa chạy, DNS hoặc network lỗi, TLS handshake thất bại | Kiểm tra endpoint, network, chứng thư; dùng retry startup nếu lỗi có thể tạm thời |
| Provision hoặc bind destination | Thiếu quyền tạo topic/queue, destination không hợp lệ, topology chưa được khai báo | Sửa quyền hoặc provisioning; tránh retry vô hạn với lỗi cố định |
| Consumer xử lý message | Payload không hợp lệ, database timeout, business rule ném exception | Dùng retry có giới hạn, backoff, DLQ hoặc xử lý lỗi nghiệp vụ |
| Mất kết nối sau startup | Broker restart, connection reset, leader/partition thay đổi | Dựa vào khả năng reconnect của client/binder, theo dõi health và phục hồi consumer |

Ví dụ: nếu tên binder Kafka không có trong classpath, tăng `bindingRetryInterval` không thể tạo ra dependency còn thiếu. Nếu tài khoản broker không có quyền đọc topic, retry liên tục cũng không sửa được quyền. Retry chỉ có ích khi nguyên nhân có khả năng tự hết sau một khoảng thời gian.

## 6. Cấu hình hoàn chỉnh cho consumer có retry bind

Ví dụ dưới đây kết hợp consumer tự khởi chạy và khoảng retry khi bind destination:

```yaml
spring:
  cloud:
    function:
      definition: processPayment
    stream:
      binding-retry-interval: 10
      bindings:
        processPayment-in-0:
          destination: orders.validated
          group: payment-service
          content-type: application/json
          consumer:
            auto-startup: true
```

Với cấu hình này, framework cố gắng bind consumer khi ứng dụng khởi động. Nếu broker hoặc destination tạm thời chưa sẵn sàng, framework chờ khoảng retry đã cấu hình trước khi thử lại. Khi binding sẵn sàng, consumer được tự khởi chạy vì `auto-startup` là `true`.

Nếu thay `auto-startup` thành `false`, consumer không tự bắt đầu nhận message. Thuộc tính retry bind và thuộc tính tự khởi chạy có mục đích khác nhau; hãy kiểm tra cách binder/version cụ thể xử lý việc tạo binding khi consumer không tự khởi chạy.

## 7. Dùng fail-fast hay retry?

Lựa chọn phụ thuộc vào nguyên nhân lỗi và cách nền tảng triển khai ứng dụng:

**Chọn fail-fast** khi cấu hình broker là điều kiện bắt buộc để ứng dụng được xem là đã khởi động. Ví dụ, dịch vụ xử lý thanh toán không thể phục vụ chức năng chính nếu không đọc được sự kiện đơn hàng. Fail-fast giúp nền tảng phát hiện lỗi, ghi log và áp dụng restart/backoff ở cấp deployment.

**Chọn retry startup** khi broker hoặc tài nguyên có thể mất thêm thời gian để sẵn sàng nhưng ứng dụng có thể chờ an toàn. Ví dụ, trong môi trường local hoặc một cụm vừa được triển khai, broker có thể khởi động chậm hơn application container.

Trước khi tăng thời gian retry, hãy trả lời:

- Lỗi có khả năng tự phục hồi không, hay là lỗi cấu hình cố định?
- Ứng dụng có được phép ở trạng thái khởi động kéo dài không?
- Nền tảng có timeout startup hoặc liveness probe ngắn hơn khoảng retry không?
- Nếu consumer chưa chạy, broker có lưu message đủ lâu để chờ không?
- Khi bind thành công, có nguy cơ backlog lớn làm consumer nhận tải đột biến không?
- Ai sẽ nhận cảnh báo nếu ứng dụng retry quá lâu?

Retry quá ngắn có thể làm log nhiễu và tạo áp lực lên broker. Retry quá dài có thể trì hoãn việc phát hiện lỗi credentials hoặc destination. Hãy kết hợp khoảng retry với giới hạn thời gian startup, readiness và cảnh báo.

## 8. Quản lý readiness và health

Một ứng dụng có thể đã tạo được application context nhưng consumer chưa hoạt động. Do đó, trạng thái process còn sống không đồng nghĩa với việc ứng dụng đã sẵn sàng xử lý nghiệp vụ.

Nên phân biệt:

- **Liveness:** tiến trình còn sống và có thể tiếp tục chạy hay không.
- **Readiness:** ứng dụng đã sẵn sàng nhận lưu lượng hoặc message hay chưa.
- **Binding/consumer state:** binding đã được tạo và consumer đã ở trạng thái nhận message hay chưa.
- **Broker health:** binder có kết nối và giao tiếp được với broker hay không.

Nếu consumer bắt buộc để ứng dụng thực hiện chức năng chính, readiness nên phản ánh trạng thái binding và dependency cần thiết. Nếu consumer được chủ ý tắt trong một giai đoạn, readiness cần biểu diễn đúng vai trò của ứng dụng ở giai đoạn đó. Không nên báo ứng dụng sẵn sàng chỉ vì HTTP server đã mở cổng.

Với Spring Boot Actuator, có thể cấu hình health endpoint và exposure theo chính sách vận hành của tổ chức. Một số binder cung cấp health indicator riêng; khả năng và tên indicator tùy binder. Hãy kiểm tra health của binder cùng trạng thái binding thay vì chỉ kiểm tra endpoint `/health` chung chung.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Ứng dụng khởi động rồi thất bại ngay | Fail-fast đang bật hoặc binding không tạo được | Đọc exception gốc, kiểm tra binder, destination và quyền broker |
| Ứng dụng chờ lâu trước khi hoàn tất startup | Binder liên tục thử bind theo `bindingRetryInterval` | Xem log từng lần retry, xác định lỗi tạm thời hay cấu hình cố định |
| Consumer không nhận message dù ứng dụng đang chạy | `auto-startup` đặt `false` và chưa có thao tác start | Kiểm tra trạng thái binding và lifecycle controller |
| Đặt `auto-startup: false` nhưng vẫn thấy kết nối broker | Binding/binder vẫn có thể được khởi tạo dù listener không tự chạy | Phân biệt khởi tạo binding với khởi chạy consumer; xem log binder |
| Retry không giải quyết lỗi | Thiếu binder dependency, sai credentials, sai TLS hoặc thiếu quyền | Sửa dependency, secret, chứng thư hoặc quyền thay vì tăng retry |
| Consumer chạy nhưng xử lý message thất bại | Lỗi runtime ở function hoặc dependency nghiệp vụ | Kiểm tra stack trace, retry runtime, error channel và DLQ |
| Deployment đánh dấu ứng dụng unhealthy trong lúc retry | Startup timeout hoặc probe ngắn hơn thời gian chờ bind | Đồng bộ timeout, readiness và chính sách retry của nền tảng |
| Message tích tụ trong broker | Consumer chưa được start, group sai hoặc consumer không theo kịp tải | Kiểm tra trạng thái binding, lag/backlog, group và concurrency |

Khi điều tra, hãy lấy exception gốc và xác định nó xuất hiện trước hay sau khi binding được tạo. Log chỉ ghi “failed to bind” thường chưa đủ; cần xem nguyên nhân sâu hơn như `UnknownHostException`, lỗi xác thực, timeout, lỗi TLS hoặc từ chối provision tài nguyên.

## 10. Kiểm thử cấu hình startup

Kiểm thử nên bao phủ cả hai giá trị `auto-startup` và các tình huống bind thất bại:

| Kịch bản | Cách kiểm thử | Điều cần xác minh |
|---|---|---|
| Consumer tự khởi chạy | Cấu hình `auto-startup: true`, khởi động broker và ứng dụng | Consumer bắt đầu nhận message sau khi binding sẵn sàng |
| Consumer không tự khởi chạy | Cấu hình `auto-startup: false` | Ứng dụng không tự tiêu thụ message; binding có thể được start qua cơ chế vòng đời được hỗ trợ |
| Broker sẵn sàng trễ | Khởi động ứng dụng trước broker với retry startup phù hợp | Binding thử lại và thành công khi broker sẵn sàng |
| Fail-fast | Đặt `binding-retry-interval: 0` và làm broker không thể truy cập | Ứng dụng báo lỗi startup thay vì chờ retry |
| Lỗi cấu hình cố định | Dùng credentials sai hoặc destination không được phép | Log chỉ ra nguyên nhân; retry không bị hiểu nhầm là đã phục hồi |
| Broker mất kết nối sau startup | Ngắt kết nối sau khi consumer đã chạy | Client/binder phục hồi theo khả năng; health và cảnh báo phản ánh sự cố |
| Consumer bị dừng có chủ đích | Dùng lifecycle control để stop/start nếu phiên bản hỗ trợ | Trạng thái binding và lượng backlog được quan sát chính xác |

Với integration test, dùng binder test hoặc broker thật phù hợp để kiểm tra hành vi khởi tạo. Test chỉ tạo application context với mock bean không chứng minh được broker provision, xác thực hay consumer listener đã thực sự hoạt động.

## 11. Ví dụ lựa chọn cho các môi trường

Một ứng dụng xử lý đơn hàng có thể dùng các chính sách khác nhau:

```yaml
---
spring:
  config:
    activate:
      on-profile: local
  cloud:
    stream:
      binding-retry-interval: 5
      bindings:
        processPayment-in-0:
          consumer:
            auto-startup: true

---
spring:
  config:
    activate:
      on-profile: integration-test
  cloud:
    stream:
      binding-retry-interval: 0
      bindings:
        processPayment-in-0:
          consumer:
            auto-startup: true

---
spring:
  config:
    activate:
      on-profile: controlled-start
  cloud:
    stream:
      binding-retry-interval: 10
      bindings:
        processPayment-in-0:
          consumer:
            auto-startup: false
```

Đây là minh họa cách tách chính sách theo profile; phần destination, group, binder và kết nối broker vẫn cần được khai báo ở cấu hình chung hoặc profile tương ứng. Trong profile `controlled-start`, phải có thao tác lifecycle rõ ràng để start consumer sau khi điều kiện nghiệp vụ đã đạt.

Không nên tạo nhiều profile chỉ để che giấu một broker thiếu ổn định. Profile nên thể hiện mục tiêu vận hành khác nhau: local cần chờ hạ tầng, integration test cần phát hiện lỗi nhanh, còn controlled-start cần một quy trình kích hoạt consumer có kiểm soát.

## 12. Quy trình vận hành đề xuất

Khi triển khai một consumer Spring Cloud Stream:

1. Xác định consumer có bắt buộc chạy ngay khi ứng dụng khởi động hay cần chờ một điều kiện nghiệp vụ.
2. Chọn `auto-startup` phù hợp; nếu tắt tự khởi chạy, xác định rõ thành phần nào sẽ start binding và khi nào.
3. Xác định lỗi bind nào có thể tự phục hồi và lỗi nào cần fail-fast.
4. Đặt `binding-retry-interval` theo khả năng sẵn sàng của broker và timeout của nền tảng.
5. Bảo đảm credentials, TLS, destination, group và quyền provision đã được cấu hình đúng.
6. Cấu hình readiness phản ánh trạng thái consumer và các dependency bắt buộc.
7. Kiểm thử broker khởi động trễ, lỗi cấu hình cố định, mất kết nối runtime và thao tác stop/start.
8. Theo dõi log retry, trạng thái binding, consumer lag và backlog sau khi khởi động.
9. Khi sự cố xảy ra, phân loại lỗi theo giai đoạn trước khi thay đổi retry hoặc restart ứng dụng.

## 13. Tự kiểm tra

- [ ] Giải thích được `autoStartup` điều khiển việc consumer binding tự khởi chạy.
- [ ] Phân biệt việc tạo binding với việc bắt đầu tiêu thụ message.
- [ ] Biết `bindingRetryInterval` áp dụng cho việc thử bind consumer khi startup.
- [ ] Giải thích được ý nghĩa fail-fast khi đặt khoảng retry bằng 0.
- [ ] Phân biệt lỗi tạo context, kết nối binder, provision tài nguyên và lỗi xử lý message runtime.
- [ ] Biết vì sao `autoStartup=false` không đồng nghĩa tắt toàn bộ binder.
- [ ] Thiết kế được readiness và lifecycle control cho consumer bị trì hoãn.
- [ ] Có kịch bản kiểm thử broker khởi động trễ, sai quyền và mất kết nối sau startup.

## Kết luận

`autoStartup` quyết định consumer binding có tự bắt đầu nhận message hay không; `bindingRetryInterval` điều khiển khoảng chờ giữa các lần thử bind consumer khi startup gặp lỗi. Dùng `autoStartup=false` khi cần trì hoãn việc tiêu thụ và phải có cơ chế lifecycle để khởi chạy sau đó. Dùng retry startup khi broker có thể sẵn sàng trễ; dùng fail-fast khi lỗi cần được phát hiện ngay. Cần phân biệt các lỗi startup với lỗi xử lý message runtime, đồng thời kết hợp readiness, health, log và backlog để biết ứng dụng đã thực sự sẵn sàng xử lý sự kiện hay chưa.
