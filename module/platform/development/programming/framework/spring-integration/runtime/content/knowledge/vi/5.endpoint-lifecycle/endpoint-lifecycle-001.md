# AbstractEndpoint và lifecycle contract

Trong Spring Integration, endpoint là thành phần nối một message handler với channel và điều khiển cách handler nhận message. Endpoint không chỉ mô tả một bước xử lý; nó còn có vòng đời: được khởi tạo, bắt đầu nhận message, tạm dừng hoặc dừng khi ứng dụng shutdown. `AbstractEndpoint` là lớp nền trong mô hình endpoint của Spring Integration, tích hợp với lifecycle contract của Spring để ApplicationContext có thể quản lý các bước này.

Hiểu `AbstractEndpoint` và `SmartLifecycle` giúp phân biệt việc một endpoint đã được tạo thành bean với việc endpoint thực sự đang hoạt động. Đây là cơ sở để cấu hình `autoStartup`, sắp xếp thứ tự khởi động bằng `phase`, chủ động start/stop endpoint và chẩn đoán trường hợp message không được tiêu thụ dù flow đã có trong cấu hình.

Sau bài này, bạn có thể:

- Giải thích vai trò của endpoint và vị trí của `AbstractEndpoint` trong Spring Integration.
- Hiểu contract `Lifecycle` và `SmartLifecycle` mà endpoint tham gia.
- Phân biệt khởi tạo bean, start, stop và destroy.
- Cấu hình `autoStartup` và `phase` để điều khiển vòng đời endpoint.
- Phân biệt hành vi lifecycle của event-driven consumer và polling consumer.
- Quan sát trạng thái endpoint và chẩn đoán vấn đề khi start/stop.

## 1. Endpoint làm gì trong message flow?

Một message flow thường có channel để vận chuyển message và handler để thực hiện công việc. Endpoint kết nối hai phần này: nó đăng ký handler với channel hoặc tổ chức việc lấy message theo lịch, tùy loại endpoint.

```text
Producer
   |
   v
Input Channel ---> Consumer Endpoint ---> Message Handler
                         |
                         +-- lifecycle: start / stop
```

Ví dụ, một service activator có thể gọi phương thức của service nghiệp vụ. Service là nơi thực hiện xử lý; consumer endpoint chịu trách nhiệm kết nối service đó với input channel và điều khiển cách message được chuyển đến service.

Không nên đồng nhất endpoint với handler:

- **Message handler** thực hiện một hành động trên message, chẳng hạn gọi service, biến đổi payload hoặc định tuyến.
- **Channel** là điểm truyền message và quyết định cách message được phân phối hoặc lưu đệm.
- **Endpoint** nối handler với channel và quản lý cơ chế tiêu thụ message.
- **Lifecycle contract** cho phép Spring và ứng dụng điều khiển khi endpoint bắt đầu hoặc ngừng hoạt động.

Vì vậy, một handler có thể tồn tại như bean mà endpoint kết nối với nó chưa start. Khi đó handler vẫn được tạo trong ApplicationContext, nhưng endpoint có thể chưa đăng ký subscriber hoặc chưa schedule poller.

## 2. AbstractEndpoint và lifecycle contract của Spring

`org.springframework.integration.endpoint.AbstractEndpoint` là lớp nền cho các endpoint tiêu thụ message trong Spring Integration. Lớp này tích hợp với cơ chế lifecycle của Spring, trong đó contract quan trọng là `SmartLifecycle`.

Spring Framework cung cấp hai mức contract thường gặp:

| Contract | Vai trò |
|---|---|
| `Lifecycle` | Khai báo `start()`, `stop()` và `isRunning()` để một component có thể được bật, dừng và truy vấn trạng thái. |
| `SmartLifecycle` | Mở rộng `Lifecycle`, bổ sung tự khởi động, thứ tự lifecycle bằng `phase` và callback cho thao tác stop. |

`SmartLifecycle` kế thừa ý tưởng về vòng đời component và bổ sung các phương thức quan trọng:

```java
public interface SmartLifecycle extends Lifecycle, Phased {

    boolean isAutoStartup();

    void stop(Runnable callback);
}
```

Đây là phần contract cốt lõi cần nhớ. Ngoài ra, `getPhase()` đến từ `Phased`; `start()`, `stop()` và `isRunning()` đến từ `Lifecycle`.

Trong mô hình endpoint, `AbstractEndpoint` cung cấp nền tảng để các endpoint cụ thể tham gia contract này. Endpoint con quyết định hành động cần thực hiện khi bắt đầu hoặc dừng, ví dụ đăng ký/hủy đăng ký handler với channel hoặc khởi động/dừng tác vụ polling. Người sử dụng Spring Integration thường cấu hình và điều khiển endpoint thông qua DSL, XML, thuộc tính endpoint hoặc bean lifecycle; không cần tự tạo subclass `AbstractEndpoint` cho các flow thông thường.

## 3. Vòng đời: khởi tạo khác với start

Vòng đời endpoint có nhiều mốc. Phân biệt chúng giúp tránh kết luận sai khi debug:

```text
Bean definition
      |
      v
Bean instantiated and configured
      |
      v
Initialized in ApplicationContext
      |
      v
Lifecycle start (if autoStartup is enabled)
      |
      v
Running <-------> Stopped
      |
      v
ApplicationContext shutdown / bean destruction
```

**Khởi tạo (initialization)** tạo đối tượng, inject dependency, áp dụng cấu hình và thực hiện các bước khởi tạo nội bộ. Endpoint đã được khởi tạo có thể xuất hiện trong ApplicationContext nhưng chưa nhận message.

**Start** chuyển endpoint sang trạng thái hoạt động theo contract. Tùy loại endpoint, thao tác này có thể đăng ký handler làm subscriber hoặc kích hoạt lịch polling.

**Stop** yêu cầu endpoint ngừng nhận công việc mới theo cơ chế của nó. Bean vẫn còn trong ApplicationContext và có thể được start lại.

**Destroy** thuộc giai đoạn hủy bean/registration và giải phóng tài nguyên. Stop không đồng nghĩa destroy: dừng endpoint không xóa bean khỏi context và cũng không tự động xóa message đang nằm trong queue.

Spring quản lý các bean `SmartLifecycle` trong quá trình refresh và đóng ApplicationContext. Những bean cho phép auto startup sẽ được start theo phase. Khi context shutdown, Spring yêu cầu chúng stop theo thứ tự phase đảo ngược và hoàn tất các callback lifecycle cần thiết.

## 4. Các phương thức quan trọng của SmartLifecycle

| Phương thức | Ý nghĩa vận hành |
|---|---|
| `start()` | Yêu cầu endpoint bắt đầu hoạt động. Có thể được gọi tự động khi context khởi động hoặc được gọi thủ công. |
| `stop()` | Yêu cầu endpoint dừng. Bean vẫn tồn tại và có thể được start lại. |
| `stop(Runnable callback)` | Yêu cầu dừng và thông báo qua callback khi quá trình stop hoàn tất. Hữu ích cho component cần dừng bất đồng bộ. |
| `isRunning()` | Cho biết trạng thái lifecycle hiện tại của component. |
| `isAutoStartup()` | Cho Spring biết có tự start component trong giai đoạn khởi động context hay không. |
| `getPhase()` | Trả về phase dùng để sắp thứ tự start/stop giữa các component. |

Các thao tác start/stop được thiết kế để điều khiển trạng thái component; ứng dụng không nên giả định gọi `start()` nhiều lần sẽ tạo nhiều consumer hoặc gọi `stop()` sẽ xóa dữ liệu message. Hành vi cụ thể khi có thao tác đồng thời cần tuân theo contract và implementation của endpoint ở phiên bản đang dùng.

`isRunning()` chỉ phản ánh trạng thái lifecycle. Nó không cho biết endpoint đã xử lý bao nhiêu message, handler có lỗi hay không, queue có bị nghẽn không, hoặc downstream có sẵn sàng không. Để đánh giá sức khỏe flow, cần kết hợp trạng thái lifecycle với log, metrics, queue depth và tracing.

## 5. autoStartup: endpoint có tự chạy cùng ApplicationContext không?

`autoStartup` quyết định endpoint có được Spring tự khởi động trong giai đoạn khởi động context hay không. Với endpoint cần chờ tài nguyên, tenant, cấu hình hoặc điều kiện nghiệp vụ sẵn sàng, có thể tắt auto startup rồi chủ động start sau.

Ví dụ cấu hình một endpoint trong Java DSL:

```java
@Bean
IntegrationFlow ordersFlow(OrderHandler handler) {
    return IntegrationFlow.from("ordersInput")
            .handle(handler, endpoint -> endpoint
                    .id("ordersConsumer")
                    .autoStartup(false))
            .get();
}
```

Ở đây, cấu hình `autoStartup(false)` gắn với endpoint được tạo cho bước xử lý. Flow và các bean liên quan vẫn được đăng ký; endpoint không tự start theo cơ chế auto startup của context. Sau khi điều kiện cần thiết đã sẵn sàng, ứng dụng có thể điều khiển lifecycle endpoint qua bean runtime tương ứng hoặc cơ chế quản trị được cấu hình.

Tên bean runtime của endpoint có thể được tạo từ ID và cấu trúc DSL. Không nên đoán tên bean chỉ từ tên phương thức `@Bean` trả về `IntegrationFlow`. Khi cần điều khiển thủ công, hãy xác định bean endpoint thực tế qua cấu hình ID, ApplicationContext hoặc công cụ quan sát đang bật.

Ví dụ về thao tác với một bean endpoint đã xác định:

```java
Lifecycle endpoint = applicationContext.getBean(
        "configuredEndpointBeanName", Lifecycle.class);

if (!endpoint.isRunning()) {
    endpoint.start();
}

// Khi cần ngừng nhận message mới:
endpoint.stop();
```

`configuredEndpointBeanName` là tên bean endpoint thực tế trong ứng dụng, không phải tên cố định áp dụng cho mọi flow. Trong ứng dụng production, nên đóng gói thao tác này trong một component quản lý lifecycle thay vì để nhiều service tùy ý start/stop endpoint.

## 6. phase: điều khiển thứ tự start và stop

`phase` là số nguyên do `Phased` cung cấp. Spring dùng phase để sắp xếp component triển khai `SmartLifecycle`:

- Phase thấp hơn được start trước.
- Phase cao hơn được start sau.
- Khi shutdown, thứ tự stop được đảo ngược: phase cao hơn được stop trước.

Điều này hữu ích khi các endpoint có quan hệ phụ thuộc về mặt vận hành. Ví dụ, khi khởi động muốn downstream consumer sẵn sàng trước khi upstream producer bắt đầu phát message. Có thể đặt consumer ở phase thấp hơn và producer ở phase cao hơn. Khi shutdown, producer sẽ được yêu cầu dừng trước consumer, giúp hạn chế việc tiếp tục phát message vào một consumer đã dừng.

```text
Khởi động (phase tăng dần):
Consumer / downstream  --->  Producer / upstream
       phase thấp             phase cao

Shutdown (phase giảm dần):
Producer / upstream  --->  Consumer / downstream
       phase cao             phase thấp
```

Không nên đặt phase tùy tiện hoặc coi phase là mức ưu tiên xử lý message. Phase chỉ điều khiển thứ tự lifecycle giữa các component được quản lý theo cơ chế này; nó không quyết định thứ tự message, số thread, throughput hoặc độ ưu tiên của task trong executor.

Khi có nhiều endpoint, hãy chọn phase dựa trên quan hệ phụ thuộc thực tế. Tránh tạo quá nhiều nhóm phase khiến việc vận hành khó hiểu. Nếu không có yêu cầu thứ tự đặc biệt, giữ cấu hình đơn giản và dựa vào thứ tự mặc định của hệ thống.

## 7. Event-driven endpoint và polling endpoint

Lifecycle contract giống nhau ở mức start/stop, nhưng công việc được thực hiện khi start khác nhau tùy loại endpoint.

### 7.1. EventDrivenConsumer

Với `SubscribableChannel` như `DirectChannel`, endpoint event-driven đăng ký message handler làm subscriber. Khi endpoint start, handler được đăng ký để nhận message. Khi endpoint stop, endpoint hủy đăng ký subscriber theo implementation.

```text
DirectChannel ---> EventDrivenConsumer ---> MessageHandler
                       |
                    start: subscribe
                    stop: unsubscribe
```

Vì `DirectChannel` thường gọi subscriber trong thread gửi, event-driven endpoint không có nghĩa là luôn tạo một thread nền riêng. Thread thực thi phụ thuộc channel và các thành phần điều phối tiếp theo.

Nếu endpoint dừng, message gửi vào channel không được endpoint đó xử lý. `DirectChannel` không phải queue để giữ message chờ endpoint chạy lại. Kết quả gửi phụ thuộc subscriber và cấu hình channel; producer nên kiểm tra kết quả gửi hoặc xử lý lỗi phù hợp.

### 7.2. PollingConsumer

Với `PollableChannel` như `QueueChannel`, polling endpoint dùng poller để lấy message theo lịch. Khi start, endpoint kích hoạt cơ chế polling; khi stop, tác vụ polling được dừng hoặc hủy theo lifecycle.

```text
QueueChannel ---> PollingConsumer ---> MessageHandler
                       |
                    start: schedule poll
                    stop: cancel polling
```

Message đã nằm trong queue thường vẫn còn sau khi endpoint stop và có thể được lấy khi endpoint start lại. Stop endpoint không phải purge queue. Nếu message được lưu trong `MessageStore`, thời gian lưu và việc khôi phục còn phụ thuộc store, cấu hình và chính sách của ứng dụng.

Poller có thể chạy theo fixed delay, fixed rate hoặc cron trigger, và có thể giới hạn số message mỗi lần poll. Những thuộc tính đó quyết định nhịp lấy message; chúng không thay đổi ý nghĩa của lifecycle contract.

## 8. Stop, callback và graceful shutdown

Khi Spring shutdown ApplicationContext, lifecycle processor yêu cầu các `SmartLifecycle` component dừng theo thứ tự phase. Với component có thể dừng bất đồng bộ, `stop(Runnable callback)` cho phép báo cho Spring khi việc dừng đã hoàn tất.

Một endpoint stop thường ngừng tiếp nhận công việc mới theo cơ chế của endpoint. Tuy nhiên, không nên mặc định rằng mọi message hoặc task đã được nhận trước thời điểm stop đều bị hủy ngay. Handler có thể đang thực hiện I/O, executor có thể đã nhận task, hoặc transaction có thể đang trong quá trình hoàn tất.

Để shutdown có kiểm soát, hãy xác định rõ:

- Cần dừng producer trước consumer ở những phase nào.
- Endpoint có đang dùng polling hay event-driven subscription.
- Task đã được giao cho executor sẽ được hoàn tất, chờ hay hủy theo chính sách nào.
- Queue và message store giữ message ra sao trong lúc shutdown.
- Transaction, retry và error flow xử lý message đang dở như thế nào.
- Thời gian chờ shutdown có phù hợp với thời gian xử lý tối đa của handler hay không.

`stop()` không đồng nghĩa `destroy()`, và cả hai đều không tự động có nghĩa là xóa message đang chờ. Nếu ứng dụng cần drain queue hoặc loại bỏ message, hãy triển khai chính sách riêng có kiểm soát và phù hợp với yêu cầu nghiệp vụ.

## 9. Điều khiển endpoint khi ứng dụng đang chạy

Trong môi trường vận hành, có thể cần tạm dừng một endpoint để bảo trì downstream, thay đổi cấu hình hoặc kiểm soát tải. Nên gom thao tác điều khiển vào một component quản lý thay vì để các service nghiệp vụ phụ thuộc trực tiếp vào endpoint.

Một component quản lý có thể nhận `ApplicationContext` hoặc một registry phù hợp để tìm endpoint theo bean name/ID đã được xác định, sau đó gọi lifecycle API. Với flow đăng ký động, `IntegrationFlowContext` và `IntegrationFlowRegistration` cung cấp handle quản lý registration; cần phân biệt việc stop registration với destroy registration.

Spring Integration cũng hỗ trợ Control Bus để gửi lệnh quản trị đến các integration component khi tính năng này được cấu hình. Control Bus có thể hữu ích để start/stop endpoint qua thông điệp quản trị, nhưng cần giới hạn quyền truy cập và chỉ expose những thao tác được phép trong môi trường triển khai.

Integration Graph và các công cụ quản trị có thể giúp xác định component và quan hệ kết nối. Tuy nhiên, graph mô tả topology; trạng thái `isRunning()` và metrics mới giúp xác định endpoint đang hoạt động ra sao. Không nên dùng một nguồn quan sát duy nhất để kết luận toàn flow khỏe mạnh.

## 10. Chẩn đoán lỗi lifecycle thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Bean endpoint tồn tại nhưng không nhận message | `autoStartup=false`, endpoint đã bị stop hoặc chưa start. | Kiểm tra `isRunning()` và cơ chế start. |
| Polling endpoint không lấy message khỏi queue | Poller chưa chạy, scheduler không hoạt động, trigger sai hoặc endpoint stopped. | Kiểm tra lifecycle, scheduler, trigger và log poll. |
| Event-driven endpoint không nhận message | Handler chưa subscribe, sai input channel hoặc endpoint đã stop. | Kiểm tra subscriber, channel wiring và lifecycle. |
| Endpoint running nhưng message vẫn bị lỗi | Handler exception, downstream lỗi, transaction/retry hoặc error channel. | Kiểm tra log, error flow, retry và dependency. |
| Shutdown kéo dài | Handler đang xử lý lâu, executor còn task hoặc callback stop chưa hoàn tất. | Kiểm tra in-flight work, timeout và cơ chế graceful shutdown. |
| Message còn trong queue sau khi stop | Stop không purge queue. | Kiểm tra queue depth và quyết định khi nào start lại hoặc drain theo chính sách. |

Quy trình kiểm tra nên đi từ trạng thái đến dữ liệu:

1. Xác định đúng endpoint bean và đọc `isRunning()`.
2. Kiểm tra `isAutoStartup()` và `getPhase()` nếu endpoint triển khai `SmartLifecycle`.
3. Xác định endpoint event-driven hay polling; kiểm tra subscriber hoặc scheduler tương ứng.
4. Kiểm tra channel, queue depth, executor và các message đang in-flight.
5. Đọc log, error channel, retry và transaction để tìm lỗi xử lý.
6. Sau khi sửa, kiểm tra start/stop và gửi message thử để xác nhận endpoint nhận đúng message.

## 11. Mở rộng: khi nào nên kế thừa AbstractEndpoint?

Hầu hết ứng dụng nên dùng endpoint có sẵn thông qua Java DSL hoặc XML: service activator, transformer, filter, router, inbound/outbound adapter và các consumer endpoint tương ứng. Những abstraction này đã tích hợp với lifecycle của Spring Integration.

Chỉ cân nhắc kế thừa `AbstractEndpoint` khi đang phát triển một loại endpoint hạ tầng mới mà các endpoint có sẵn không đáp ứng được. Khi đó, implementation cần xác định rõ hành động start/stop, quản lý subscription hoặc scheduler, xử lý tài nguyên được tạo ra, bảo đảm không đăng ký lặp và dọn dẹp đúng lúc. Cũng cần xác định hành vi khi start/stop nhiều lần và khi ApplicationContext shutdown.

Không nên kế thừa `AbstractEndpoint` chỉ để thêm logic nghiệp vụ. Logic nghiệp vụ thuộc handler/service; endpoint chịu trách nhiệm kết nối và lifecycle. Tách hai vai trò giúp endpoint dễ kiểm thử và không biến vòng đời hạ tầng thành một phần của nghiệp vụ.

## 12. Tự kiểm tra

**Tình huống:** Một `PollingConsumer` đã được tạo thành bean nhưng cấu hình `autoStartup=false`. Ứng dụng gửi message vào `QueueChannel`, queue tăng dần và handler không được gọi.

1. Vì sao bean tồn tại nhưng handler chưa nhận message?
2. Khi gọi `start()` cho endpoint, cơ chế nào được kích hoạt?
3. Nếu stop endpoint sau khi queue có 20 message, 20 message đó có tự bị xóa không?
4. Nếu có một producer endpoint cần dừng trước consumer khi shutdown, nên xem xét thuộc tính nào?

**Gợi ý trả lời:** (1) Khởi tạo bean không đồng nghĩa endpoint đã start; `autoStartup=false` khiến Spring không tự khởi động endpoint. (2) Polling endpoint kích hoạt lịch poll để lấy message từ channel. (3) Không; stop dừng polling, queue thường vẫn giữ message theo chính sách lưu trữ. (4) Dùng `phase` để sắp xếp thứ tự start và stop giữa các `SmartLifecycle` component.

**Bài tập thực hành:** Tạo một flow nhận message từ `QueueChannel` bằng polling endpoint. Thử cấu hình `autoStartup=false`, quan sát queue depth, sau đó start endpoint và theo dõi message được xử lý. Tiếp tục stop endpoint khi queue còn message, xác minh message vẫn còn và start lại để xử lý tiếp. Cuối cùng, thay bằng `DirectChannel` và so sánh hành vi khi endpoint dừng.

## Tài liệu tham khảo

- [Spring Integration Reference — Endpoint](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Javadoc — AbstractEndpoint](https://docs.spring.io/spring-integration/api/org/springframework/integration/endpoint/AbstractEndpoint.html)
- [Spring Framework Javadoc — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Spring Framework Reference — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-lifecycle)
- [Spring Integration Reference — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html)
