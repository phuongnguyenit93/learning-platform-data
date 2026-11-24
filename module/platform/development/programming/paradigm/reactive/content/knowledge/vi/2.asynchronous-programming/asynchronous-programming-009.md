# Luồng ảo Java: mối liên hệ với I/O chặn và mô hình phản ứng

Trong lập trình máy chủ, một yêu cầu thường phải chờ nhiều thao tác I/O: truy vấn cơ sở dữ liệu, gọi dịch vụ HTTP, đọc tệp hoặc nhận dữ liệu từ socket. Trong lúc chờ, CPU có thể rảnh nhưng luồng thực thi vẫn bị chiếm dụng. Đây là điểm giao nhau giữa ba cách tổ chức xử lý bất đồng bộ: luồng nền tảng truyền thống, luồng ảo của Java và mô hình phản ứng dựa trên luồng dữ liệu.

Bài học thuộc chương **Bất đồng bộ** của module **REACTIVE_PROGRAMMING**. Module giúp người học hiểu các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams, đồng thời thực hành Mono, Flux, toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Luồng ảo là một lựa chọn ở tầng thực thi có thể giúp mã xử lý I/O chặn mở rộng tốt hơn; chúng có quan hệ với mô hình phản ứng ở cách giải quyết bài toán chờ I/O, nhưng hai khái niệm không thay thế trực tiếp cho nhau.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao I/O chặn làm giới hạn khả năng phục vụ đồng thời khi mỗi yêu cầu chiếm một luồng nền tảng.
- Mô tả cách JVM lập lịch luồng ảo trên các luồng nền tảng và vì sao một luồng ảo có thể nhường luồng nền tảng trong lúc chờ.
- Dùng executor tạo một luồng ảo cho mỗi tác vụ I/O chặn.
- Phân biệt khả năng mở rộng nhờ luồng ảo với backpressure của Reactive Streams.
- Chọn cách tiếp cận phù hợp cho hệ thống dùng thư viện chặn, hệ thống reactive và hệ thống kết hợp cả hai.

## 1. Vì sao I/O chặn gây áp lực lên luồng?

Hãy xét một yêu cầu cần lấy thông tin khách hàng và danh sách đơn hàng:

~~~java
Customer customer = customerRepository.findById(customerId);
List<Order> orders = orderRepository.findByCustomerId(customerId);
return new Dashboard(customer, orders);
~~~

Hai lời gọi repository có thể phải chờ cơ sở dữ liệu phản hồi. Với API JDBC chặn, luồng gọi sẽ dừng tại lời gọi truy vấn cho đến khi có kết quả, xảy ra lỗi hoặc hết thời gian chờ. Nếu hai truy vấn độc lập, việc gọi tuần tự còn làm tăng tổng thời gian phản hồi; ta có thể cho chúng chạy đồng thời, nhưng cách tổ chức luồng quyết định hệ thống chịu được bao nhiêu yêu cầu cùng lúc.

Trong mô hình truyền thống, mỗi yêu cầu thường được xử lý bởi một luồng nền tảng (platform thread). Luồng nền tảng gắn với tài nguyên của hệ điều hành và có chi phí tạo, duy trì stack cùng chuyển đổi ngữ cảnh. Khi số yêu cầu đồng thời tăng cao, tạo quá nhiều luồng nền tảng có thể tiêu thụ bộ nhớ và làm bộ lập lịch của hệ điều hành chịu thêm áp lực.

Một thread pool giới hạn số luồng nền tảng để kiểm soát tài nguyên. Tuy nhiên, khi tất cả luồng trong pool đều đang chờ I/O, tác vụ mới phải xếp hàng dù CPU có thể đang rảnh. Tăng kích thước pool chỉ đẩy giới hạn đi xa hơn và có thể khiến tài nguyên phía cơ sở dữ liệu hoặc dịch vụ phụ thuộc bị quá tải.

Vấn đề cốt lõi không phải là thao tác chờ luôn xấu. Vấn đề là một thao tác chờ đang giữ một tài nguyên thực thi đắt đỏ trong toàn bộ thời gian chờ.

## 2. Luồng ảo giải quyết thời gian chờ như thế nào?

Luồng ảo (virtual thread) là luồng nhẹ do JVM quản lý, được chuẩn hóa từ Java 21. JVM lập lịch nhiều luồng ảo lên một tập nhỏ hơn các luồng nền tảng, còn gọi là carrier thread. Vì vậy, một luồng ảo không cần gắn cố định với một luồng hệ điều hành trong suốt vòng đời của nó.

Khi một luồng ảo thực hiện thao tác chặn được JDK hỗ trợ, chẳng hạn một số thao tác I/O hoặc thao tác chờ, JVM có thể tháo (unmount) luồng ảo khỏi carrier thread. Carrier thread sau đó có thể chạy một luồng ảo khác trong khi luồng trước tiếp tục chờ. Khi kết quả sẵn sàng, luồng ảo được lập lịch để tiếp tục từ điểm đã tạm dừng.

Điều này cho phép giữ phong cách lập trình tuần tự quen thuộc:

~~~java
String response = httpClient.send(
    request,
    HttpResponse.BodyHandlers.ofString()
).body();

Customer customer = customerRepository.findById(customerId);
~~~

Nếu các lời gọi chặn này chạy trên luồng ảo và đường gọi sử dụng các API có khả năng nhường carrier thread, JVM có thể quản lý số lượng lớn tác vụ đang chờ mà không cần một luồng nền tảng riêng cho từng tác vụ.

### Tạo một luồng ảo cho mỗi tác vụ

Java cung cấp **Executors.newVirtualThreadPerTaskExecutor()** để tạo executor khởi chạy một luồng ảo cho mỗi tác vụ được gửi vào:

~~~java
ExecutorService ioExecutor =
    Executors.newVirtualThreadPerTaskExecutor();

try {
    Future<Customer> customerFuture = ioExecutor.submit(
        () -> customerRepository.findById(customerId)
    );

    Future<List<Order>> ordersFuture = ioExecutor.submit(
        () -> orderRepository.findByCustomerId(customerId)
    );

    // Hai truy vấn đã được gửi đi và có thể chạy đồng thời.
    Customer customer = customerFuture.get();
    List<Order> orders = ordersFuture.get();

    return new Dashboard(customer, orders);
} finally {
    ioExecutor.close();
}
~~~

Ví dụ giả định hai repository sử dụng API chặn và các kiểu dữ liệu đã được khai báo. Hai tác vụ được gửi đi trước khi lấy kết quả, do đó chúng có thể tiến hành đồng thời. **Future.get()** chờ kết quả của từng tác vụ; nếu luồng gọi cũng là luồng ảo, thao tác chờ có thể nhường carrier thread theo cơ chế lập lịch của JVM.

Trong ứng dụng thực tế, hãy quản lý vòng đời executor theo vòng đời thành phần hoặc ứng dụng. Không cần tạo một executor mới cho từng yêu cầu HTTP. Đóng executor khi thành phần sở hữu nó dừng hoạt động để các tác vụ được xử lý và tài nguyên được giải phóng đúng lúc.

Một điểm quan trọng: executor này không tạo một pool nhỏ để tái sử dụng các luồng ảo. Nó tạo luồng ảo mới cho từng tác vụ. Mô hình đó phù hợp với nguyên tắc **mỗi tác vụ một luồng**; không nên áp dụng thói quen điều chỉnh kích thước thread pool nền tảng một cách máy móc cho luồng ảo.

### Luồng ảo không làm CPU chạy nhanh hơn

Luồng ảo chủ yếu giúp tổ chức nhiều tác vụ có thời gian chờ I/O. Chúng không làm một phép tính CPU-bound chạy nhanh hơn và không tạo thêm năng lực xử lý CPU. Nếu tác vụ chủ yếu tính toán, số tác vụ chạy đồng thời vẫn cần được điều phối phù hợp với số lõi CPU và đặc điểm tải.

Cũng không nên hiểu rằng có thể tạo vô hạn tác vụ mà không cần giới hạn. Bản thân luồng ảo nhẹ hơn luồng nền tảng, nhưng mỗi tác vụ vẫn tiêu thụ bộ nhớ và có thể giữ tài nguyên ứng dụng. Đặc biệt, cơ sở dữ liệu, connection pool, API bên ngoài và giới hạn quota vẫn có dung lượng hữu hạn.

## 3. Giới hạn tài nguyên khi dùng luồng ảo

Luồng ảo giúp giảm chi phí của việc chờ, nhưng không tự động bảo vệ các hệ thống phía sau. Nếu một dịch vụ có thể xử lý tối đa 40 lời gọi đồng thời, gửi 5.000 tác vụ đến dịch vụ đó vẫn có thể gây nghẽn dù 5.000 tác vụ đang chạy trên luồng ảo.

Hãy giới hạn tài nguyên tại đúng điểm bị giới hạn. Ví dụ sau dùng **Semaphore** để giới hạn số lời gọi đồng thời đến một dịch vụ phụ thuộc:

~~~java
private final Semaphore partnerPermits = new Semaphore(40);

String callPartner(Request request) throws InterruptedException {
    partnerPermits.acquire();
    try {
        return blockingPartnerClient.call(request);
    } finally {
        partnerPermits.release();
    }
}
~~~

Mỗi tác vụ vẫn có thể chạy trên một luồng ảo, nhưng chỉ tối đa 40 tác vụ đi qua vùng gọi dịch vụ cùng lúc. Trong ứng dụng thực, cần kết hợp giới hạn đồng thời với timeout, xử lý hủy tác vụ và chính sách lỗi phù hợp. Nếu dùng connection pool, hãy hiểu kích thước pool và thời gian giữ connection để tránh tạo hàng đợi quá lớn trước pool.

Một số điểm cần quan sát khi vận hành:

- **Thread-local:** luồng ảo hỗ trợ **ThreadLocal**, nhưng tạo một giá trị lớn cho mỗi luồng có thể làm tăng bộ nhớ khi có rất nhiều luồng ảo. Tránh dùng **ThreadLocal** để giữ các đối tượng nặng hoặc tài nguyên dùng chung theo cách vốn được thiết kế cho một pool nhỏ.
- **Pinning:** trong một số phiên bản JDK cũ, luồng ảo có thể giữ carrier thread khi bị chặn bên trong vùng **synchronized**; hiện tượng này được gọi là pinning. JDK 24 cải thiện hành vi với monitor, nhưng lời gọi native hoặc foreign function vẫn có thể giữ carrier. Khi nghi ngờ pinning, hãy kiểm tra bằng công cụ quan sát phù hợp với phiên bản JDK đang chạy.
- **Timeout và hủy:** luồng ảo không thay thế timeout cho HTTP, JDBC hoặc các lời gọi từ xa. Hãy đặt timeout ở tầng giao tiếp và xác định rõ cách dừng công việc khi yêu cầu của người dùng bị hủy.
- **Áp lực lên hệ thống phụ thuộc:** theo dõi số connection đang dùng, hàng đợi, giới hạn đồng thời, tỷ lệ lỗi và độ trễ của cơ sở dữ liệu cũng như dịch vụ ngoài.

Không nên bọc một lời gọi I/O dài trong khối **synchronized** nếu không cần thiết. Ngoài nguy cơ pinning trên một số JDK, việc giữ khóa trong thời gian chờ còn làm các luồng khác không thể tiến vào vùng bảo vệ.

## 4. Mô hình phản ứng giải quyết bài toán ở tầng nào?

Mô hình phản ứng (reactive model) tổ chức dữ liệu và sự kiện thành các luồng bất đồng bộ. Thay vì viết một lời gọi đồng bộ rồi chờ kết quả, chương trình mô tả cách dữ liệu đi qua một pipeline và cách các thành phần phối hợp khi có dữ liệu, lỗi hoặc tín hiệu hoàn tất.

Reactive Streams định nghĩa hợp đồng Publisher–Subscriber với bốn vai trò chính:

- **Publisher:** phát dữ liệu cho subscriber đã đăng ký.
- **Subscriber:** nhận tín hiệu đăng ký, dữ liệu, lỗi hoặc hoàn tất.
- **Subscription:** kết nối publisher với subscriber và cho phép subscriber yêu cầu dữ liệu hoặc hủy đăng ký.
- **Processor:** vừa là subscriber vừa là publisher, thường dùng để biến đổi hoặc chuyển tiếp luồng dữ liệu.

Trình tự tín hiệu cơ bản là:

1. Subscriber gọi **subscribe** trên Publisher.
2. Publisher gọi **onSubscribe** và cung cấp một Subscription.
3. Subscriber gọi **request(n)** để báo rằng nó sẵn sàng nhận tối đa **n** phần tử.
4. Publisher phát dữ liệu bằng **onNext** theo nhu cầu đã được yêu cầu, hoặc kết thúc bằng **onComplete** hay **onError**.

Subscriber cũng có thể gọi **cancel()** để dừng việc nhận thêm dữ liệu. Sau tín hiệu kết thúc, publisher không được tiếp tục phát **onNext** cho subscription đó.

### Backpressure là điểm khác biệt quan trọng

Backpressure là cơ chế để bên tiêu thụ điều tiết lượng dữ liệu mà bên phát được phép gửi. Subscriber có thể yêu cầu từng phần dữ liệu theo khả năng xử lý của mình, thay vì để producer đẩy dữ liệu nhanh hơn consumer có thể tiếp nhận.

Trong Project Reactor, **Mono<T>** biểu diễn tối đa một phần tử, còn **Flux<T>** biểu diễn từ không đến nhiều phần tử. Cả hai triển khai các hợp đồng Reactive Streams và cung cấp toán tử để kết hợp, biến đổi, lọc hoặc xử lý lỗi.

Ví dụ, nếu hai repository trả về **Mono**, có thể kết hợp kết quả mà không gọi API chặn:

~~~java
Mono<Dashboard> dashboard =
    Mono.zip(
        customerRepository.findById(customerId),
        orderRepository.findByCustomerId(customerId)
    )
    .map(tuple ->
        new Dashboard(tuple.getT1(), tuple.getT2())
    );
~~~

**Mono.zip** đăng ký vào hai nguồn và tạo kết quả tổng hợp khi cả hai nguồn cung cấp giá trị. Ví dụ giả định repository là reactive repository và trả về **Mono<Customer>** cùng **Mono<List<Order>>**. Nếu repository thực tế dùng JDBC chặn, đoạn mã trên không tự biến JDBC thành I/O không chặn.

Với một luồng nhiều phần tử, có thể giới hạn số tác vụ con đang được xử lý đồng thời:

~~~java
Flux<Customer> customers =
    Flux.fromIterable(customerIds)
        .flatMap(customerClient::findById, 32);
~~~

Tham số **32** giới hạn số inner publisher được **flatMap** đăng ký đồng thời. Đây là một cách kiểm soát mức đồng thời trong pipeline; backpressure tiếp tục truyền nhu cầu qua các toán tử theo hợp đồng Reactive Streams. Giới hạn đồng thời vẫn cần được chọn theo năng lực của dịch vụ phía sau.

## 5. Luồng ảo và reactive: giống nhau và khác nhau

Cả hai cách tiếp cận đều hữu ích khi ứng dụng có nhiều thao tác I/O và cần phục vụ nhiều công việc cùng lúc. Khác biệt nằm ở cách biểu diễn công việc và cơ chế điều tiết.

| Khía cạnh | Luồng ảo | Mô hình reactive |
|---|---|---|
| Cách viết | Tuần tự, mệnh lệnh; mỗi tác vụ có thể chạy trên một luồng ảo | Khai báo pipeline bất đồng bộ bằng Publisher và các toán tử |
| I/O chặn | Có thể giữ cách gọi chặn quen thuộc; JVM nhường carrier khi API hỗ trợ | Thường dùng API I/O không chặn để không giữ luồng xử lý trong lúc chờ |
| Điều tiết dữ liệu | Không có backpressure tự động; cần semaphore, giới hạn đồng thời, queue hoặc cơ chế admission | Reactive Streams có **request(n)** và **cancel()** để truyền nhu cầu và hủy |
| Mô hình lỗi | Exception, **try/catch**, **Future** hoặc cơ chế hủy tác vụ | Tín hiệu **onError** và toán tử xử lý lỗi trong pipeline |
| Tích hợp thư viện | Thuận tiện với thư viện đồng bộ như JDBC hoặc client chặn | Phù hợp với thư viện hỗ trợ reactive và pipeline dữ liệu liên tục |
| Điểm cần chú ý | Giới hạn tài nguyên phụ thuộc, ThreadLocal, pinning và vòng đời executor | Scheduler, hủy subscription, backpressure, xử lý lỗi và tránh gọi chặn trên event loop |

Có thể hình dung luồng ảo giúp giảm chi phí của việc **chờ trong một tác vụ**, còn reactive cung cấp một hợp đồng để **truyền dữ liệu và nhu cầu qua cả pipeline**. Hai hướng có thể cùng xuất hiện trong một hệ thống, nhưng cần xác định ranh giới rõ ràng.

### Khi nào nên chọn luồng ảo?

Luồng ảo thường phù hợp khi:

- Ứng dụng hiện tại dùng JDBC, thư viện HTTP chặn hoặc API đồng bộ khác.
- Mỗi yêu cầu có quy trình xử lý dễ diễn đạt bằng các bước tuần tự.
- Đội ngũ muốn tăng khả năng phục vụ đồng thời mà không phải chuyển toàn bộ mã sang chuỗi callback hoặc pipeline reactive.
- Tác vụ chủ yếu chờ I/O và các dịch vụ phụ thuộc có thể được bảo vệ bằng giới hạn đồng thời, timeout và connection pool.

### Khi nào nên chọn reactive?

Reactive thường phù hợp khi:

- Dữ liệu đến liên tục, cần xử lý theo luồng hoặc kết hợp nhiều nguồn sự kiện.
- Hệ thống cần backpressure xuyên suốt để điều tiết producer và consumer.
- Các thư viện giao tiếp, truy cập dữ liệu và thành phần trong pipeline đều hỗ trợ I/O không chặn.
- Việc kết hợp, biến đổi, retry, timeout, hủy và xử lý lỗi trên một luồng dữ liệu là phần trọng tâm của nghiệp vụ.

Không có lựa chọn nào luôn tốt hơn trong mọi trường hợp. Hãy xem xét kiểu tải, thư viện hiện có, yêu cầu về luồng dữ liệu, năng lực hệ thống phụ thuộc và khả năng vận hành của đội ngũ.

## 6. Kết hợp luồng ảo với hệ sinh thái reactive

Một ứng dụng có thể có cả mã chặn và mã reactive. Điều cần tránh là chạy thao tác chặn tùy tiện trên event loop của framework reactive. Nếu event loop bị giữ trong một truy vấn JDBC lâu, nó không thể xử lý các sự kiện khác đúng hạn và có thể làm độ trễ tăng trên diện rộng.

Nếu buộc phải gọi thư viện chặn từ Reactor, hãy cô lập lời gọi đó trên scheduler dành cho công việc chặn:

~~~java
Mono<Customer> customer =
    Mono.fromCallable(() -> blockingCustomerRepository.findById(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

**fromCallable** trì hoãn lời gọi đến lúc có subscription; **subscribeOn** chỉ định scheduler chạy phần nguồn của pipeline. **boundedElastic** được thiết kế để cô lập công việc có khả năng chặn với giới hạn tài nguyên riêng. Cách này giúp tránh chiếm event loop, nhưng không biến thao tác JDBC thành I/O không chặn và cũng không cung cấp backpressure cho chính cơ sở dữ liệu.

Nếu toàn bộ đường xử lý đang dùng API chặn và nghiệp vụ được mô tả tự nhiên theo kiểu tuần tự, có thể cân nhắc dùng luồng ảo xuyên suốt tầng xử lý đó. Nếu hệ thống đã có reactive driver và pipeline cần điều tiết luồng dữ liệu, giữ pipeline reactive thường đơn giản hơn. Hãy tránh chuyển qua lại giữa hai mô hình ở quá nhiều tầng vì việc chuyển ngữ cảnh làm khó theo dõi lỗi, hủy tác vụ và thời gian chờ.

## 7. Cách đánh giá lựa chọn trong một hệ thống thực tế

Khi đánh giá một thay đổi, hãy bắt đầu từ đường đi của một yêu cầu cụ thể:

1. Liệt kê các thao tác I/O và xác định thao tác nào đang chặn.
2. Xác định thư viện đang dùng là đồng bộ hay reactive; kiểm tra xem có API không chặn thực sự hay chỉ có một wrapper quanh API chặn.
3. Đo thời gian chờ, thời gian CPU, số yêu cầu đồng thời và mức sử dụng connection pool.
4. Nếu dùng luồng ảo, kiểm tra số tác vụ đang chờ và đặt giới hạn cho dịch vụ phụ thuộc.
5. Nếu dùng reactive, kiểm tra nhu cầu được truyền qua pipeline, scheduler đang chạy từng đoạn và có thao tác chặn nào lọt vào event loop không.
6. Thử tải với cả trường hợp bình thường lẫn tình huống phụ thuộc chậm, lỗi hoặc hết connection.

Các chỉ số hữu ích gồm throughput, độ trễ p50/p95/p99, mức sử dụng CPU và heap, số lượng luồng, số connection đang dùng, độ dài hàng đợi, tỷ lệ timeout và lỗi. Đừng chỉ dựa vào số lượng luồng để kết luận hệ thống đã mở rộng tốt: một hệ thống có thể tạo được rất nhiều luồng ảo nhưng vẫn nghẽn ở connection pool hoặc API phía sau.

## 8. Những hiểu lầm thường gặp

**“Luồng ảo là reactive.”** Không. Luồng ảo là cơ chế thực thi và lập lịch luồng do JVM quản lý. Reactive là mô hình lập trình dựa trên luồng dữ liệu bất đồng bộ và hợp đồng Publisher–Subscriber.

**“Dùng luồng ảo thì không cần giới hạn đồng thời.”** Không đúng. Luồng ảo giảm chi phí chờ, nhưng không tăng dung lượng của cơ sở dữ liệu, API bên ngoài hay bộ nhớ. Vẫn cần giới hạn tài nguyên tại các điểm nghẽn.

**“Có thể dùng thư viện chặn ở bất kỳ đâu trong ứng dụng reactive.”** Không nên. Lời gọi chặn trên event loop có thể giữ luồng xử lý và làm chậm nhiều request khác. Cần dùng API reactive hoặc cô lập phần chặn trên scheduler phù hợp.

**“Reactive luôn nhanh hơn luồng ảo.”** Không thể kết luận như vậy nếu chưa đo. Hiệu quả phụ thuộc vào loại tải, cách triển khai, thư viện, độ trễ của phụ thuộc và chi phí vận hành mã nguồn.

**“Luồng ảo làm phép tính CPU-bound nhanh hơn.”** Không. Chúng giúp tận dụng luồng nền tảng tốt hơn trong lúc tác vụ chờ. Với công việc tính toán nặng, cần điều phối theo năng lực CPU.

## 9. Bài tập vận dụng

Một endpoint cần gọi ba dịch vụ: hồ sơ khách hàng, lịch sử thanh toán và danh sách giao hàng. Cả ba dịch vụ hiện chỉ cung cấp HTTP client đồng bộ. Mỗi lời gọi mất trung bình 150 ms, nhưng đôi khi một dịch vụ mất đến 2 giây. Hệ thống có giới hạn 60 kết nối đồng thời đến mỗi dịch vụ.

Hãy thiết kế hai phương án:

- **Phương án A:** dùng luồng ảo, gửi ba lời gọi độc lập đồng thời, tổng hợp kết quả và đặt giới hạn phù hợp cho từng dịch vụ.
- **Phương án B:** dùng WebClient hoặc client reactive tương đương, kết hợp ba nguồn bằng các toán tử Reactor.

Khi so sánh, hãy trả lời:

1. Trong mỗi phương án, thao tác nào chờ I/O và luồng nào bị giữ trong lúc chờ?
2. Giới hạn 60 kết nối được thực thi ở đâu? Điều gì xảy ra nếu có 500 yêu cầu endpoint đồng thời?
3. Nếu lịch sử thanh toán phản hồi chậm, cách nào giúp điều tiết số công việc đang chờ và cách nào giúp truyền backpressure?
4. Khi một yêu cầu HTTP bị hủy hoặc hết thời gian chờ, các lời gọi con được dừng như thế nào?
5. Bạn sẽ đo những chỉ số nào để xác nhận phương án đã cải thiện độ trễ mà không làm quá tải dịch vụ phụ thuộc?

Một phương án tốt cần giải thích được cả mô hình thực thi lẫn giới hạn tài nguyên. Hãy chọn dựa trên đặc điểm của hệ thống và kết quả đo tải, thay vì chỉ dựa vào số lượng luồng hoặc số lượng toán tử trong mã nguồn.

## Kết luận

Luồng ảo cho phép Java xử lý nhiều tác vụ I/O chặn bằng mã tuần tự quen thuộc, trong khi JVM quản lý việc nhường và sử dụng lại carrier thread. Reactive Streams tổ chức dữ liệu thành pipeline bất đồng bộ và bổ sung backpressure để subscriber điều tiết lượng dữ liệu cần nhận. Khi hiểu rõ hai tầng này, bạn có thể chọn luồng ảo cho hệ thống dựa trên thư viện chặn, chọn reactive cho pipeline dữ liệu cần điều tiết, hoặc kết hợp chúng ở những ranh giới được kiểm soát rõ ràng.
