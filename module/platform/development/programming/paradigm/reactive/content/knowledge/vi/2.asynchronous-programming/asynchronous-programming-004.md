# Vòng lặp sự kiện và mô hình xử lý dựa trên thông báo

Trong một ứng dụng reactive, dữ liệu thường đến từ nhiều nguồn và vào những thời điểm không thể dự đoán: socket nhận dữ liệu, bộ hẹn giờ phát tín hiệu, người dùng gửi yêu cầu hoặc một dịch vụ khác phát sinh sự kiện. Nếu mỗi thao tác đều phải chờ thao tác trước hoàn tất, ứng dụng dễ lãng phí tài nguyên và phản hồi chậm khi tải tăng.

Hai cách tổ chức xử lý bất đồng bộ thường gặp là **vòng lặp sự kiện (event loop)** và **mô hình xử lý dựa trên thông báo (message-driven)**. Vòng lặp sự kiện quyết định cách một luồng thực thi tiếp nhận và phân phối công việc. Mô hình dựa trên thông báo quyết định cách các thành phần gửi, nhận và xử lý công việc thông qua thông điệp. Chúng có thể được dùng cùng nhau: một event loop có thể phân phối các thông điệp đến handler, còn một consumer xử lý thông điệp có thể chạy trên worker thread.

Trong hệ sinh thái Java, các khái niệm này xuất hiện trong Java NIO, Netty, Vert.x, Spring WebFlux và các hệ thống dùng message broker. Hiểu đúng vai trò của chúng giúp ta tổ chức pipeline reactive, tránh chặn luồng xử lý I/O và kiểm soát lượng công việc đang chờ.

## 1. Vì sao cần tổ chức xử lý bất đồng bộ?

Giả sử một máy chủ đang phục vụ hàng nghìn kết nối. Một yêu cầu có thể phải chờ dữ liệu từ mạng, gọi dịch vụ khác hoặc ghi kết quả xuống kho dữ liệu. Thời gian chờ I/O thường dài hơn nhiều so với thời gian CPU thực hiện một phép tính đơn giản.

Nếu giữ một thread riêng cho mỗi kết nối và để thread đó chờ I/O, số thread có thể tăng cao. Mỗi thread tiêu tốn bộ nhớ stack và tạo thêm chi phí lập lịch cho hệ điều hành. Một hướng tiếp cận khác là đăng ký thao tác I/O không chặn, rồi tiếp tục xử lý khi hệ điều hành báo rằng thao tác đã sẵn sàng hoặc hoàn tất.

Mô hình event loop tận dụng cách tiếp cận này. Thay vì để thread ngồi chờ từng kết nối, một hoặc một nhóm event loop theo dõi nhiều nguồn sự kiện và gọi handler khi có công việc cần xử lý. Mô hình message-driven bổ sung cách tách bên gửi khỏi bên nhận: bên gửi đưa thông điệp vào một kênh, bên nhận lấy thông điệp và xử lý theo khả năng của mình.

Hai mô hình giải quyết các phần khác nhau của bài toán:

- Event loop tổ chức việc thực thi các callback hoặc task trên một hay nhiều luồng.
- Message-driven tổ chức việc trao đổi công việc và dữ liệu giữa các thành phần.
- Reactive Streams quy định hợp đồng truyền tín hiệu giữa Publisher và Subscriber, trong đó Subscription.request(n) cho phép bên nhận biểu thị nhu cầu.

## 2. Vòng lặp sự kiện hoạt động như thế nào?

Một event loop là một vòng lặp liên tục nhận biết công việc đã sẵn sàng, chọn công việc cần chạy và gọi handler tương ứng. Tùy framework, nguồn công việc có thể là sự kiện socket, timer, callback được đưa vào hàng đợi hoặc task được gửi từ thread khác.

Một chu kỳ điển hình có thể diễn ra như sau:

1. Đăng ký các nguồn sự kiện, chẳng hạn socket hoặc timer.
2. Chờ hoặc kiểm tra sự kiện I/O bằng cơ chế không chặn của nền tảng.
3. Đưa những callback hoặc task đã sẵn sàng vào hàng đợi thực thi.
4. Lấy task ra và chạy handler trên event loop thread.
5. Handler xử lý nhanh, đăng ký thao tác tiếp theo hoặc chuyển công việc phù hợp sang worker.
6. Quay lại theo dõi sự kiện mới.

Luồng khái quát: **Socket / Timer / Task → Sự kiện sẵn sàng → Hàng đợi callback hoặc task → Event loop thread → Handler ngắn, không chặn → Đăng ký I/O hoặc gửi task → Theo dõi sự kiện tiếp theo.** Nếu handler cần thao tác chặn, công việc đó được chuyển sang worker phù hợp.

### 2.1. Event loop thread và handler

Trong một event loop đơn, các handler thường được chạy tuần tự trên cùng một thread. Khi handler đang chạy, event loop đó chưa thể chạy handler tiếp theo. Vì vậy, handler cần hoàn tất nhanh và tránh chờ một thao tác chặn.

Điều này không có nghĩa toàn bộ ứng dụng chỉ có một thread. Một framework có thể tạo nhiều event loop thread, mỗi thread quản lý một nhóm kết nối. Ứng dụng cũng có thể có worker pool cho công việc cần chờ hoặc cần nhiều CPU. Ranh giới quan trọng là thread nào đang sở hữu event loop và công việc nào được phép chạy trên thread đó.

Ví dụ, một handler nhận yêu cầu HTTP có thể kiểm tra dữ liệu đầu vào, gọi một API bất đồng bộ và đăng ký callback xử lý kết quả. Trong thời gian chờ phản hồi mạng, event loop tiếp tục phục vụ kết nối khác.

### 2.2. Vì sao không được chặn event loop?

Giả sử một handler gọi Thread.sleep, thực hiện truy vấn JDBC đồng bộ hoặc đọc một file lớn theo cách chặn. Event loop thread sẽ bị giữ lại cho đến khi thao tác đó kết thúc. Trong thời gian này, những kết nối khác được quản lý bởi cùng event loop có thể phải chờ dù dữ liệu của chúng đã sẵn sàng.

Hậu quả thường thấy là độ trễ tăng đồng loạt, thông lượng giảm và hàng đợi task phình to. Một thao tác chặn kéo dài có thể ảnh hưởng đến nhiều request không liên quan.

Các công việc nên giữ ngoài event loop gồm:

- Gọi API hoặc cơ sở dữ liệu bằng client đồng bộ.
- Đọc/ghi file theo API chặn.
- Chờ khóa có khả năng tranh chấp hoặc chờ Future.get() / Thread.join().
- Tính toán CPU nặng kéo dài.

Với I/O chặn, hãy chuyển thao tác sang worker phù hợp. Với phép tính CPU, dùng pool dành cho công việc tính toán. Sau khi hoàn tất, kết quả có thể được đưa trở lại pipeline để xử lý tiếp. Việc chuyển luồng cần có chủ đích vì nó cũng tạo thêm chi phí lập lịch và truyền dữ liệu giữa các thread.

### 2.3. Event loop trong Java

Java NIO cung cấp Selector để một thread theo dõi trạng thái sẵn sàng của nhiều channel. Các framework như Netty xây dựng event loop trên những cơ chế I/O này và tổ chức việc đăng ký channel, nhận sự kiện cùng thực thi task.

Trong Netty, một EventLoopGroup quản lý nhiều EventLoop. Một channel thường được gắn với một event loop trong suốt vòng đời đăng ký của nó, nhờ vậy các sự kiện của channel được xử lý có trật tự trên event loop tương ứng. Một event loop có thể phục vụ nhiều channel.

Vert.x cũng sử dụng event loop để thực thi handler. Spring WebFlux khi chạy trên Reactor Netty thường dùng các event loop thread để xử lý I/O mạng. Trong khi đó, ứng dụng Spring MVC truyền thống thường xử lý request trên servlet thread. Lựa chọn framework không tự động làm cho mọi đoạn code trở thành bất đồng bộ: một lời gọi đồng bộ vẫn có thể chặn thread đang thực thi nó.

## 3. Mô hình xử lý dựa trên thông báo

Trong mô hình message-driven, thành phần gửi tạo một thông điệp và chuyển nó vào một kênh nhận. Thành phần nhận lấy thông điệp rồi thực hiện công việc. Hai phía giao tiếp thông qua hợp đồng của thông điệp thay vì gọi trực tiếp phương thức nội bộ của nhau.

Các vai trò cơ bản gồm:

- **Producer** tạo và gửi thông điệp.
- **Channel, queue hoặc broker** tiếp nhận, lưu tạm, định tuyến và có thể lưu bền vững thông điệp.
- **Consumer** nhận thông điệp và thực hiện công việc.
- **Handler** chứa logic xử lý một loại thông điệp.

Kênh có thể chỉ là một hàng đợi trong bộ nhớ của một tiến trình, hoặc là hệ thống trung gian như Apache Kafka, RabbitMQ hay một dịch vụ messaging khác. Hàng đợi trong bộ nhớ thường đơn giản và nhanh nhưng không tự bảo đảm thông điệp tồn tại sau khi tiến trình dừng. Broker có thể cung cấp lưu trữ bền vững, phân phối giữa nhiều tiến trình và cơ chế xác nhận, tùy cấu hình.

### 3.1. Phân biệt command, event và message

Message là khái niệm chung cho dữ liệu được gửi qua một kênh. Hai loại thông điệp thường gặp là:

- **Command** yêu cầu một thành phần thực hiện hành động, ví dụ ChargePayment. Command thường hướng đến một nơi xử lý có trách nhiệm thực hiện yêu cầu.
- **Event** mô tả một sự việc đã xảy ra, ví dụ OrderPlaced. Event thường được phát ra để các thành phần quan tâm có thể phản ứng.

Tên và nội dung nên thể hiện rõ ý nghĩa nghiệp vụ. CreateOrder thường là command vì nó yêu cầu tạo đơn. OrderCreated là event vì nó ghi nhận đơn đã được tạo thành công.

Một thông điệp thực tế có thể có các trường như:

| Trường | Mục đích |
|---|---|
| messageId | Nhận diện duy nhất một thông điệp |
| type / schemaVersion | Xác định loại và phiên bản cấu trúc |
| key | Chọn nhóm xử lý hoặc phân vùng có thứ tự |
| payload | Dữ liệu nghiệp vụ |
| occurredAt | Thời điểm sự kiện xảy ra |
| correlationId | Liên kết các thông điệp trong cùng một luồng nghiệp vụ |
| headers | Metadata phục vụ định tuyến, tracing hoặc chính sách xử lý |

Không phải hệ thống nào cũng cần đủ các trường trên. Hãy xác định hợp đồng tối thiểu mà producer và consumer cùng hiểu, đồng thời có kế hoạch tương thích khi cấu trúc thông điệp thay đổi.

### 3.2. Ví dụ hàng đợi trong bộ nhớ bằng Java

Ví dụ sau minh họa producer gửi sự kiện đơn hàng vào một hàng đợi có giới hạn và consumer xử lý tuần tự. Đây là cách minh họa message-driven trong một tiến trình; nó chưa phải một broker phân tán và không có lưu trữ bền vững.

    import java.math.BigDecimal;
    import java.util.concurrent.ArrayBlockingQueue;
    import java.util.concurrent.BlockingQueue;

    record OrderPlaced(String orderId, BigDecimal total) {}

    BlockingQueue<OrderPlaced> inbox = new ArrayBlockingQueue<>(1024);

    // Producer: offer không chờ nếu hàng đợi đã đầy.
    boolean accepted = inbox.offer(
        new OrderPlaced("order-42", new BigDecimal("125.00"))
    );

    if (!accepted) {
        // Chọn chính sách phù hợp: từ chối, thử lại có giới hạn,
        // hoặc lưu bền vững để xử lý sau.
    }

    // Consumer: chạy đoạn này trên một worker thread.
    try {
        while (!Thread.currentThread().isInterrupted()) {
            OrderPlaced event = inbox.take();
            processIdempotently(event);
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    }

ArrayBlockingQueue giới hạn số thông điệp đang chờ. offer cho phép producer biết ngay khi hàng đợi không nhận thêm được; take chờ trên worker thread cho đến khi có thông điệp. Trong ứng dụng thực tế, consumer cần xử lý lỗi từng thông điệp, ghi nhận kết quả và có chiến lược thử lại hoặc đưa thông điệp lỗi sang nơi cách ly. Không nên để một ngoại lệ ngoài dự kiến âm thầm kết thúc worker.

### 3.3. Tách rời producer và consumer

Producer không cần biết consumer đang chạy ở máy nào, có bao nhiêu instance hoặc xử lý mất bao lâu. Consumer có thể tăng số lượng instance khi lượng thông điệp tăng. Kênh trung gian giúp hấp thụ những đợt tải ngắn và cho phép hai phía triển khai độc lập hơn.

Sự tách rời này cũng tạo ra các vấn đề cần thiết kế:

- **Thông điệp trùng lặp:** một consumer có thể nhận lại thông điệp nếu lần xử lý trước đã thành công nhưng xác nhận chưa được ghi nhận.
- **Thứ tự:** nhiều consumer hoặc nhiều partition có thể xử lý song song; không nên mặc định mọi thông điệp đều có thứ tự toàn cục.
- **Lỗi tạm thời:** cần retry có giới hạn và khoảng lùi phù hợp để tránh tạo vòng lặp quá tải.
- **Thông điệp lỗi lâu dài:** có thể chuyển sang dead-letter queue để điều tra và xử lý riêng.
- **Tương thích dữ liệu:** producer và consumer có thể được triển khai ở những thời điểm khác nhau, nên cần quản lý phiên bản schema.

Với mô hình giao nhận at-least-once, consumer phải sẵn sàng nhận một thông điệp nhiều lần. Một cách phổ biến là xử lý idempotent: cùng một messageId được gửi lại không làm nghiệp vụ bị thực hiện lặp. Có thể lưu dấu thông điệp đã xử lý cùng thay đổi nghiệp vụ trong một transaction phù hợp. Tính nhất quán đầu-cuối giữa nhiều hệ thống không tự xuất hiện chỉ vì dùng broker; cần thiết kế transaction, outbox/inbox hoặc cơ chế tương đương theo yêu cầu.

## 4. Event loop và message-driven khác nhau ở đâu?

| Khía cạnh | Event loop | Message-driven |
|---|---|---|
| Trọng tâm | Lập lịch và thực thi sự kiện/task | Trao đổi công việc qua thông điệp |
| Đơn vị xử lý | Callback, handler hoặc task | Message, command hoặc event |
| Thành phần chính | Event loop thread, bộ theo dõi I/O, task queue | Producer, channel/broker, consumer |
| Mục tiêu thường gặp | Phục vụ nhiều I/O đồng thời với ít thread chờ | Giảm phụ thuộc trực tiếp và phân phối công việc |
| Cách mở rộng | Thêm event loop hoặc worker phù hợp | Thêm consumer, partition hoặc năng lực broker |
| Rủi ro cần quản lý | Handler chặn loop, task queue tăng, tranh chấp tài nguyên | Message trùng lặp, thứ tự, retry, schema và tồn đọng queue |

Một hệ thống có thể kết hợp cả hai. Chẳng hạn, Reactor Netty nhận dữ liệu socket trên event loop, sau đó pipeline chuyển một số công việc sang scheduler phù hợp. Ở một tầng khác, ứng dụng phát OrderPlaced lên broker để dịch vụ hóa đơn và dịch vụ kho xử lý độc lập.

## 5. Liên hệ với Reactive Streams, Publisher và Subscriber

Reactive Streams định nghĩa hợp đồng truyền tín hiệu bất đồng bộ có kiểm soát nhu cầu. Bốn thành phần cốt lõi là:

- Publisher<T> phát dữ liệu.
- Subscriber<T> nhận dữ liệu.
- Subscription nối hai phía và cho phép subscriber gọi request(n) hoặc cancel().
- onNext, onError và onComplete là các tín hiệu mà publisher gửi đến subscriber sau khi thiết lập subscription.

Sau onSubscribe, subscriber có thể yêu cầu số phần tử mà nó sẵn sàng nhận. Publisher chỉ được phát tối đa lượng phần tử đã được yêu cầu cho subscription đó. Cơ chế này gọi là **backpressure**. Nó giúp pipeline phối hợp tốc độ giữa bên phát và bên nhận, thay vì mặc định đẩy dữ liệu không giới hạn.

Event loop, message queue và Reactive Streams có liên quan nhưng không đồng nghĩa:

- Event loop quyết định callback hoặc task chạy trên thread nào và vào thời điểm nào.
- Message queue giữ thông điệp chờ consumer; giới hạn dung lượng queue là một cách kiểm soát lượng dữ liệu đang tồn đọng.
- Backpressure là giao thức nhu cầu giữa publisher và subscriber. Nó chỉ kiểm soát nguồn bên ngoài khi adapter hoặc connector chuyển tiếp được nhu cầu đó đến nguồn.

Nếu một nguồn sự kiện không thể tạm dừng, ứng dụng phải chọn chính sách khi subscriber tiêu thụ chậm: buffer có giới hạn, bỏ phần tử, giữ phần tử mới nhất, từ chối hoặc ghi dữ liệu ra nơi lưu trữ khác. Buffer không giới hạn có thể biến tình trạng consumer chậm thành lỗi cạn bộ nhớ.

### 5.1. Chọn scheduler trong pipeline Reactor

Trong Reactor, publishOn chuyển việc xử lý các tín hiệu ở phía sau toán tử đó sang scheduler được chọn. subscribeOn ảnh hưởng đến nơi thực hiện quá trình subscribe và việc khởi chạy nguồn. Chúng không phải tên gọi khác của event loop; chúng là cách điều khiển thực thi trong pipeline.

Ví dụ dưới đây giả sử paymentEvents() phát các sự kiện thanh toán, legacyRiskClient.check là lời gọi đồng bộ có thể chặn, còn decisionRepository.save trả về Mono và thực hiện I/O bất đồng bộ:

    Flux<PaymentEvent> paymentEvents = paymentEvents();

    paymentEvents
        .filter(PaymentEvent::isValid)
        .flatMap(event ->
            Mono.fromCallable(() -> legacyRiskClient.check(event))
                .subscribeOn(Schedulers.boundedElastic())
                .map(risk -> new RiskChecked(event, risk)),
            32, 8
        )
        .publishOn(Schedulers.parallel())
        .map(this::toDecision)
        .flatMap(decisionRepository::save)
        .subscribe(
            saved -> log.info("Saved decision for {}", saved.paymentId()),
            error -> log.error("Payment pipeline failed", error)
        );

Trong ví dụ:

- Mono.fromCallable biến lời gọi đồng bộ thành một nguồn Mono.
- subscribeOn(Schedulers.boundedElastic()) đưa lời gọi có khả năng chặn sang scheduler phù hợp cho tác vụ blocking.
- flatMap giới hạn tối đa 32 tác vụ kiểm tra rủi ro đồng thời; tham số 8 đặt mức prefetch cho mỗi inner publisher.
- publishOn(Schedulers.parallel()) chuyển các bước phía sau sang scheduler dành cho công việc tính toán.
- flatMap(decisionRepository::save) ghép các thao tác lưu bất đồng bộ vào pipeline.

Nếu nguồn ban đầu được gọi từ một event loop, đoạn blocking được bọc trong fromCallable sẽ chạy trên boundedElastic thay vì giữ event loop chờ kết quả. Các bước khác vẫn cần được đánh giá theo bản chất của chúng: không nên chuyển một lời gọi blocking sang parallel rồi xem như đã giải quyết vấn đề. Trong ứng dụng thực tế, cần quản lý vòng đời của subscription, giới hạn concurrency theo năng lực hệ thống và xác định chính sách retry/lỗi cho từng loại nghiệp vụ.

## 6. Kiểm soát tải và lỗi trong hai mô hình

Khi tốc độ tạo công việc cao hơn tốc độ xử lý, công việc sẽ tích tụ ở task queue, message queue hoặc buffer của pipeline. Nếu không có giới hạn, bộ nhớ và độ trễ có thể tăng liên tục.

Một số nguyên tắc thực hành:

1. Đặt giới hạn cho queue và buffer; xác định rõ hành vi khi đạt giới hạn.
2. Giới hạn số tác vụ đồng thời theo khả năng của downstream, chẳng hạn connection pool hoặc dịch vụ được gọi.
3. Giữ handler trên event loop ngắn; chuyển tác vụ blocking sang worker.
4. Dùng timeout cho thao tác I/O và retry có giới hạn, có backoff.
5. Thiết kế consumer idempotent nếu thông điệp có thể được giao lại.
6. Theo dõi queue depth, thời gian chờ, thời gian xử lý, số lần retry và số thông điệp bị loại bỏ.
7. Gắn correlation ID để lần theo một luồng xử lý qua nhiều thành phần.

Với Reactor, có thể chọn các toán tử backpressure như onBackpressureBuffer, onBackpressureDrop hoặc onBackpressureLatest tùy ý nghĩa dữ liệu. Nếu dùng buffer, nên đặt giới hạn và định nghĩa rõ cách xử lý khi buffer đầy. Bỏ dữ liệu phù hợp với một số luồng cập nhật trạng thái mà chỉ giá trị mới nhất quan trọng; nó không phù hợp với sự kiện nghiệp vụ cần được lưu nhận đầy đủ.

Khi consumer xử lý lỗi, hãy phân biệt lỗi tạm thời (có thể retry) và lỗi dữ liệu hoặc nghiệp vụ (cần cách ly hoặc trả kết quả lỗi). Retry vô hạn có thể giữ một thông điệp lỗi trong hệ thống và làm tăng tải. Với event loop, một exception trong handler cần được xử lý tại ranh giới phù hợp để không làm hỏng vòng đời của luồng xử lý. Với Reactor, lỗi thường là tín hiệu kết thúc pipeline; muốn tiếp tục theo chính sách cụ thể, hãy đặt toán tử xử lý lỗi ở đúng phạm vi.

## 7. Cách chọn mô hình cho một tình huống

Hãy dùng event loop khi bài toán chủ yếu là quản lý nhiều kết nối hoặc nguồn I/O không chặn, và handler có thể hoàn thành nhanh. Đây là lựa chọn phù hợp cho máy chủ mạng, gateway hoặc tầng nhận request có lưu lượng lớn.

Hãy dùng message-driven khi các thành phần cần độc lập về thời điểm triển khai, tốc độ xử lý hoặc khả năng mở rộng; khi công việc có thể được xếp hàng và xử lý sau; hoặc khi nhiều consumer cần phản ứng với cùng một event. Đây là lựa chọn phổ biến cho xử lý đơn hàng, gửi thông báo, cập nhật kho và tích hợp giữa dịch vụ.

Kết hợp cả hai khi ứng dụng vừa cần xử lý I/O hiệu quả vừa cần phân phối công việc qua các thành phần. Ví dụ: API nhận yêu cầu trên event loop, kiểm tra dữ liệu nhanh, phát command vào broker, sau đó consumer xử lý nghiệp vụ và phát event kết quả. Mỗi tầng cần giới hạn tải và hợp đồng lỗi riêng.

Khi thiết kế, hãy trả lời ba câu hỏi: công việc đang chờ ở đâu, thread nào thực thi handler, và cơ chế nào ngăn lượng công việc vượt quá khả năng xử lý? Ba câu trả lời này giúp xác định event loop, queue và backpressure đang phối hợp ra sao trong toàn bộ luồng bất đồng bộ.
