# Tác vụ kéo dài sau khi bên tiêu thụ hủy đăng ký

Trong một ứng dụng reactive, subscriber có thể hủy subscription trước khi công việc hoàn tất. Người dùng đóng trang, client HTTP ngắt kết nối, timeout xảy ra hoặc một component dừng hoạt động đều có thể khiến downstream không còn nhận kết quả. Tuy nhiên, một tác vụ đã bắt đầu có thể vẫn tiếp tục chạy: thư viện bên ngoài không hỗ trợ hủy, một lời gọi blocking chưa dừng, hoặc công việc đã được chuyển sang một subscription độc lập.

Đây là vấn đề về quyền sở hữu và vòng đời tài nguyên. Cần phân biệt công việc chỉ có ý nghĩa khi subscriber còn chờ kết quả với công việc nghiệp vụ phải tiếp tục dù người gọi đã rời đi. Reactive Streams cung cấp cancellation để yêu cầu dừng một subscription; nó không bảo đảm đảo ngược side effect đã xảy ra hoặc tự động biến một request thành job nền bền vững.

## 1. Hủy subscription có nghĩa gì?

Khi subscriber gọi Subscription.cancel() hoặc mã Reactor gọi Disposable.dispose(), nó yêu cầu publisher ngừng phát tín hiệu cho subscription đó. Đây là tín hiệu điều khiển từ downstream về upstream.

Cancellation có một số đặc điểm quan trọng:

- Publisher và các operator cần tôn trọng yêu cầu hủy, ngừng phát tín hiệu tiếp theo và giải phóng tài nguyên theo khả năng của chúng.
- Cancellation không phải onComplete hay onError; subscriber không nhận một tín hiệu terminal mới chỉ để xác nhận đã hủy.
- Hủy subscription không hoàn tác dữ liệu đã ghi, giao dịch đã commit, thông điệp đã gửi hoặc side effect đã hoàn tất.
- Việc dừng tác vụ đang chạy phụ thuộc nguồn dữ liệu, scheduler, driver và thư viện được gọi có hợp tác với cancellation hay không.
- Cancellation có thể đến trong lúc một callback hoặc thao tác đang thực thi. Không nên giả định mọi công việc dừng ngay tại đúng thời điểm gọi cancel().

Ví dụ, một Mono gọi dịch vụ mạng có thể truyền cancellation đến HTTP client. Nếu client hỗ trợ hủy request, kết nối hoặc thao tác đọc có thể được dừng. Nhưng nếu server từ xa đã xử lý yêu cầu và commit thay đổi, hủy kết nối không làm server tự rollback.

Vì vậy, câu hỏi đầu tiên khi thiết kế một tác vụ dài là: ai sở hữu công việc, và điều kiện nào kết thúc vòng đời của nó?

## 2. Vì sao công việc vẫn có thể chạy sau khi subscriber hủy?

Có một số tình huống thường gặp:

1. **API blocking không hợp tác:** một hàm đồng bộ đang chờ thư viện hoặc hệ điều hành. Hủy subscription không nhất thiết làm lời gọi đó dừng ngay.
2. **Side effect đã được gửi đi:** request đã đến dịch vụ khác, message broker hoặc database. Subscriber chỉ ngừng chờ kết quả; thao tác ở phía xa có thể vẫn tiếp tục.
3. **Subscription độc lập:** ứng dụng gọi subscribe() bên trong một service rồi trả về publisher khác. Subscription tự tạo không còn được quản lý bởi subscriber HTTP ban đầu.
4. **Công việc đã được bàn giao:** một queue, worker hoặc scheduler ứng dụng đã nhận job. Công việc lúc này thuộc vòng đời của worker hoặc hệ thống job.
5. **Tài nguyên có quá trình đóng riêng:** việc hủy yêu cầu cleanup, nhưng đóng kết nối hoặc giải phóng tài nguyên có thể cần thời gian bất đồng bộ.

Không phải mọi trường hợp tiếp tục chạy đều là lỗi. Một báo cáo lớn có thể cần tiếp tục sau khi trình duyệt đóng, nhưng một truy vấn gợi ý chỉ phục vụ response hiện tại thường nên dừng khi response không còn cần thiết. Hành vi đúng phụ thuộc ý nghĩa nghiệp vụ và chủ sở hữu của công việc.

## 3. Phân biệt tác vụ gắn với request và tác vụ nền

Hai loại công việc này có vòng đời khác nhau:

| Đặc điểm | Tác vụ gắn với request | Tác vụ nền |
|---|---|---|
| Chủ sở hữu | Subscription của request | Application service, job worker hoặc hệ thống hàng đợi |
| Khi client ngắt kết nối | Thường nên hủy nếu kết quả không còn cần thiết | Thông thường tiếp tục theo chính sách job |
| Cách báo kết quả | HTTP response hoặc stream đang mở | Job ID, trạng thái, thông báo hoặc kết quả lưu trữ |
| Vòng đời | Ngắn, gắn với request/deadline | Có thể kéo dài qua nhiều request hoặc lần khởi động |
| Phục hồi sau process crash | Không mặc định có | Cần lưu trạng thái và cơ chế tiếp tục/retry |

Một tác vụ chỉ cần tồn tại trong lúc request còn hoạt động nên nằm trong cùng publisher chain. Khi subscriber hủy, cancellation được truyền ngược qua các operator đến nguồn.

Một tác vụ phải sống lâu hơn request cần có chủ sở hữu khác. Thường đó là job được lưu bền vững, đưa vào queue và xử lý bởi worker. Không nên dựa vào một subscription nằm trong bộ nhớ của controller để đại diện cho một công việc nghiệp vụ dài hạn.

## 4. Không tách subscription nền bằng subscribe() tùy tiện

Một lỗi thiết kế phổ biến là gọi subscribe() bên trong service để khởi chạy tác vụ, sau đó trả về Mono báo thành công ngay:

    // Cách làm dễ mất quyền kiểm soát vòng đời.
    Mono<JobAccepted> submit(ReportCommand command) {
        reportService.generate(command)
            .subscribe(
                this::storeReport,
                error -> log.error("Report failed", error)
            );

        return Mono.just(new JobAccepted("accepted"));
    }

Đoạn mã trên tạo hai luồng điều khiển độc lập. Subscription do subscribe() tạo không tự động bị hủy khi subscriber của submit() ngắt kết nối. Nó cũng không cung cấp cơ chế bền vững nếu process dừng, không có trạng thái job đáng tin cậy và khó phối hợp retry hoặc shutdown.

Nếu công việc phải thuộc về request, hãy trả publisher và để framework quản lý subscription:

    Mono<Report> generateForRequest(ReportCommand command) {
        return reportService.generate(command);
    }

Nếu công việc phải tiếp tục sau request, hãy bàn giao nó cho một thành phần sở hữu job. Việc bàn giao cần được ghi nhận rõ ràng trước khi trả lời caller.

## 5. Mô hình job nền có trạng thái bền vững

Một API khởi chạy tác vụ dài thường không giữ HTTP response mở đến khi công việc hoàn tất. Thay vào đó, API ghi nhận yêu cầu, tạo job ID và trả về trạng thái đã tiếp nhận. Worker xử lý job độc lập với subscription của request.

Một luồng điển hình:

    HTTP client
        |
        | POST /reports
        v
    API: validate + persist job
        |
        | commit job + outbox message
        v
    Queue / broker
        |
        v
    Background worker
        |
        +---- update progress/status
        |
        v
    Result store

API có thể trả 202 Accepted cùng job ID. Client dùng một request khác để truy vấn trạng thái hoặc lấy kết quả. Nếu client ngắt kết nối sau khi job đã được commit, job vẫn thuộc về hệ thống nền.

Các trạng thái thường dùng:

| Trạng thái | Ý nghĩa |
|---|---|
| ACCEPTED | Yêu cầu hợp lệ đã được ghi nhận |
| QUEUED | Job đang chờ worker |
| RUNNING | Worker đang xử lý |
| SUCCEEDED | Công việc hoàn tất |
| FAILED | Công việc thất bại |
| CANCEL_REQUESTED | Người dùng hoặc quản trị viên yêu cầu dừng job |
| CANCELLED | Worker đã dừng job và ghi nhận trạng thái hủy |

Không nên đánh dấu CANCELLED chỉ vì HTTP client đóng kết nối. Client disconnect và lệnh hủy job là hai sự kiện khác nhau.

### 5.1. Ghi nhận job trước khi xác nhận

Ví dụ dưới đây minh họa việc tạo job và ghi thông điệp outbox:

    Mono<JobAccepted> submit(ReportCommand command) {
        return jobRepository.insert(Job.accepted(command))
            .flatMap(job ->
                outboxRepository.append(
                    JobRequested.forJob(job.id())
                ).thenReturn(new JobAccepted(job.id()))
            );
    }

Trong production, việc lưu job và outbox message cần nằm trong cùng một transaction để tránh hai tình huống: job đã lưu nhưng không có message đánh thức worker, hoặc message đã gửi nhưng job chưa được commit. Với Spring reactive transaction, có thể dùng transaction manager và TransactionalOperator phù hợp với reactive data access.

Nếu HTTP request bị hủy trước khi transaction commit, caller có thể không biết job đã được tiếp nhận hay chưa. Dùng idempotency key để client gửi lại an toàn và truy vấn cùng một job thay vì tạo nhiều job trùng nhau.

## 6. Worker sở hữu vòng đời của tác vụ

Khi worker nhận job, subscription của worker đại diện cho quá trình thực thi. Vòng đời này không phụ thuộc vào HTTP subscription đã tạo job.

Ví dụ cấu trúc xử lý:

    Mono<Void> execute(ReportJob job) {
        return jobRepository.markRunning(job.id())
            .then(
                reportService.generate(job)
                    .flatMap(result ->
                        resultRepository.save(job.id(), result)
                    )
            )
            .then(jobRepository.markSucceeded(job.id()))
            .onErrorResume(error ->
                jobRepository.markFailed(job.id(), error)
            );
    }

Đây là khung minh họa. Worker thực tế còn cần lease hoặc lock để tránh hai worker cùng chạy một job, checkpoint để tiếp tục sau lỗi, retry có giới hạn và xử lý trường hợp process dừng giữa chừng.

Nếu worker subscription bị hủy do shutdown hoặc mất quyền sở hữu lease, chuỗi có thể kết thúc bằng cancellation chứ không đi vào onErrorResume. Job không nên bị đánh dấu thành công. Hệ thống cần lưu tiến độ ở các điểm an toàn và cho phép lease hết hạn để worker khác tiếp nhận lại.

## 7. Hủy job theo yêu cầu nghiệp vụ

Người dùng có thể muốn hủy một job đã khởi chạy. Đây là một lệnh nghiệp vụ riêng, ví dụ DELETE /jobs/{id} hoặc POST /jobs/{id}/cancel. API cập nhật trạng thái thành CANCEL_REQUESTED; worker quan sát trạng thái đó và dừng ở điểm an toàn.

Không nên dùng việc client ngắt kết nối để đại diện cho lệnh này. Trình duyệt có thể mất mạng trong khi người dùng vẫn muốn báo cáo hoàn tất. Ngược lại, người dùng có thể chủ động hủy job dù không có request HTTP nào đang mở.

Với công việc chia thành các phần nhỏ, worker có thể kiểm tra cancellation token giữa các phần:

    Flux<Page> pages = reportSource.pages(job);

    Mono<Void> processPages(
        ReportJob job,
        CancellationToken cancellation
    ) {
        return pages.concatMap(page ->
            Mono.defer(() -> {
                if (cancellation.isCancellationRequested()) {
                    return Mono.error(new JobCancelledException());
                }
                return processPage(job, page);
            })
        ).then();
    }

CancellationToken và JobCancelledException là abstraction của ứng dụng trong ví dụ. Token có thể được cập nhật từ trạng thái job trong database, tín hiệu nội bộ hoặc message điều khiển. Với job dài, không nên truy vấn database cho từng thao tác nhỏ nếu tần suất cao; có thể cache trạng thái trong một khoảng ngắn hoặc gửi tín hiệu đến worker đang giữ job.

Khi worker nhận yêu cầu hủy, nó nên dừng nhận phần việc mới, hoàn tất hoặc giải phóng phần việc hiện tại theo chính sách, đóng tài nguyên và ghi CANCELLED. Nếu thao tác đang gọi một dịch vụ ngoài hỗ trợ cancellation, hãy truyền yêu cầu hủy đến client đó. Nếu không thể dừng ngay, ghi nhận CANCEL_REQUESTED cho đến khi worker xác nhận đã dừng.

## 8. Tài nguyên của job phải sống cùng job

Một job dài có thể mở cursor, file, kết nối hoặc session. Tài nguyên cần được tạo trong vòng đời của worker và giải phóng khi job hoàn tất, lỗi hoặc bị hủy.

Với tài nguyên bất đồng bộ, Reactor cung cấp usingWhen:

    Mono<Report> generate(ReportJob job) {
        return Mono.usingWhen(
            reportClient.openSession(job),
            session -> session.generateReport(job),
            session -> session.close(),
            (session, error) -> session.close(),
            session -> session.close()
        );
    }

Ba hàm cleanup lần lượt xử lý complete, error và cancel. Nếu close() trả về Mono<Void>, usingWhen có thể chờ quá trình cleanup bất đồng bộ theo semantics của operator. Nhờ vậy, session thuộc về subscription của worker và được đóng khi vòng đời subscription kết thúc.

Không nên mở tài nguyên trước khi tạo publisher rồi quên đóng nó nếu subscriber không đăng ký hoặc hủy sớm. Tạo tài nguyên trong supplier của usingWhen giúp gắn thời điểm cấp phát với subscription thực tế.

Nếu job phải tiếp tục sau khi HTTP subscriber hủy, tài nguyên của job không nên bị sở hữu bởi subscription HTTP. Tài nguyên cần được cấp phát bên trong publisher do worker quản lý.

## 9. Tác vụ blocking và giới hạn của interruption

Chuyển một tác vụ blocking sang Schedulers.boundedElastic() giúp không chặn event loop:

    Mono<Report> generateBlocking(ReportJob job) {
        return Mono.fromCallable(
                () -> legacyReportClient.generate(job)
            )
            .subscribeOn(Schedulers.boundedElastic());
    }

Việc chuyển scheduler chỉ thay đổi nơi thực thi. Nó không tự biến thư viện blocking thành API có khả năng hủy hoàn toàn. Khi subscription bị dispose, tác vụ chưa bắt đầu có thể không được chạy; tác vụ đang chạy có thể nhận interrupt tùy scheduler và thư viện, nhưng không được bảo đảm sẽ dừng.

Nếu tự viết vòng lặp hoặc thuật toán dài, hãy tạo điểm kiểm tra cancellation:

    for (Page page : pages) {
        if (Thread.currentThread().isInterrupted()
                || cancellation.isCancellationRequested()) {
            throw new JobCancelledException();
        }

        process(page);
    }

Khi bắt InterruptedException, khôi phục cờ interrupt bằng Thread.currentThread().interrupt() trước khi thoát hoặc truyền lỗi phù hợp. Không nuốt interruption rồi tiếp tục làm việc như bình thường.

Với thư viện ngoài, hãy tìm API hủy truy vấn, đóng stream hoặc abort request. Nếu thư viện không hỗ trợ, thiết kế timeout, lease và khả năng tiếp tục từ checkpoint để giới hạn hậu quả của tác vụ không thể dừng ngay.

## 10. Không dùng doFinally để khởi chạy cleanup bất đồng bộ rồi bỏ quên

doFinally nhận callback đồng bộ khi subscription complete, error hoặc cancel. Nó phù hợp để ghi metric, log hoặc cập nhật bộ đếm nhanh:

    jobPublisher.doFinally(signal ->
        metrics.recordTermination(jobId, signal)
    );

Callback này không trả về publisher cleanup để Reactor chờ. Đoạn mã sau không bảo đảm thao tác lưu trạng thái hoàn tất:

    // Không bảo đảm hoàn tất việc lưu trạng thái.
    jobPublisher.doFinally(signal ->
        jobRepository.markStopped(jobId).subscribe()
    );

Đây lại là một subscription tách rời, không được chuỗi ban đầu quản lý. Nếu cần một thao tác bất đồng bộ gắn với terminal signal, hãy dùng operator quản lý tài nguyên như usingWhen, hoặc cấu trúc pipeline để trạng thái hoàn tất được ghi trước terminal signal. Với cancellation từ bên ngoài, cần một cơ chế quản lý job riêng vì downstream đã hủy thì chuỗi không thể tiếp tục phát kết quả cleanup.

## 11. Shutdown ứng dụng và job đang chạy

Khi ứng dụng dừng, các subscription nền cũng chịu tác động của lifecycle. Một job bền vững không nên phụ thuộc vào việc process hiện tại sống mãi.

Một quy trình shutdown thường gồm:

1. Ngừng nhận job mới hoặc ngừng lấy message mới từ queue.
2. Cho các job đang chạy một khoảng thời gian để hoàn tất phần việc an toàn.
3. Lưu checkpoint hoặc trạng thái tiến độ.
4. Đóng tài nguyên và xác nhận các job đã hoàn tất hoặc đã dừng.
5. Để lease hết hạn hoặc đưa job chưa hoàn tất về trạng thái có thể được worker khác tiếp nhận.

Nếu thời hạn shutdown hết trước khi job hoàn tất, process có thể bị dừng cưỡng bức. Vì vậy, checkpoint và tính idempotent quan trọng hơn việc chỉ dựa vào hook shutdown để chờ vô hạn.

Với tác vụ chỉ tồn tại trong bộ nhớ, process dừng có thể làm mất công việc. Nếu nghiệp vụ yêu cầu bảo đảm tiếp tục sau restart, cần lưu job và tiến độ ở nơi bền vững, đồng thời có chính sách retry và phục hồi.

## 12. Idempotency và checkpoint khi job có thể chạy lại

Một worker có thể dừng sau khi side effect đã xảy ra nhưng trước khi ghi nhận trạng thái thành công. Khi lease hết hạn, worker khác có thể chạy lại job. Nếu thao tác không idempotent, lần chạy lại có thể tạo báo cáo trùng, gửi email lặp hoặc ghi nhận thanh toán hai lần.

Các kỹ thuật thường dùng:

- Gắn job ID hoặc idempotency key vào mọi side effect cần chống trùng.
- Lưu checkpoint sau mỗi đơn vị công việc đã hoàn tất.
- Ghi kết quả và checkpoint trong cùng transaction khi có thể.
- Dùng outbox/inbox để phối hợp cập nhật dữ liệu với việc phát message.
- Đặt retry có giới hạn, backoff và phân loại lỗi có thể thử lại.
- Ghi rõ trạng thái RUNNING, lease owner và thời điểm lease hết hạn.

Checkpoint không nhất thiết lưu toàn bộ dữ liệu trung gian. Nó chỉ cần đủ để worker xác định phần việc nào đã hoàn tất và phần nào cần tiếp tục. Nếu một bước không thể lặp lại an toàn, phải thiết kế giao thức xác nhận hoặc bù trừ nghiệp vụ riêng.

## 13. Kiểm thử cancellation và vòng đời job

Nên kiểm thử riêng hai hành vi: cancellation của subscription request và lệnh hủy job nghiệp vụ.

### 13.1. Kiểm thử cleanup khi subscription bị hủy

    AtomicBoolean closed = new AtomicBoolean();

    Mono<String> source = Mono.using(
        () -> new AutoCloseableResource(closed),
        resource -> Mono.<String>never(),
        AutoCloseableResource::close
    );

    StepVerifier.create(source)
        .thenCancel()
        .verify();

    assert closed.get();

Ví dụ giả định AutoCloseableResource có constructor nhận cờ và phương thức close() đặt cờ thành true. Trong test JUnit, dùng assertion của framework để xác nhận tài nguyên được đóng khi subscription bị hủy.

### 13.2. Kiểm thử lệnh hủy job

Với job nền, test nên:

1. Tạo job và xác nhận trạng thái QUEUED hoặc RUNNING.
2. Gửi lệnh cancel để chuyển trạng thái sang CANCEL_REQUESTED.
3. Phát tín hiệu cho cancellation token.
4. Xác nhận worker dừng ở điểm kiểm tra an toàn.
5. Xác nhận tài nguyên được đóng và trạng thái cuối là CANCELLED.
6. Xác nhận không có phần việc mới được nhận sau khi lệnh hủy có hiệu lực.

Đồng thời cần kiểm thử trường hợp client HTTP ngắt kết nối sau khi job đã commit: job vẫn được worker xử lý và có thể truy vấn bằng job ID. Trường hợp request bị hủy trước khi commit cần kiểm tra idempotency/retry để caller xác định job có được tiếp nhận hay chưa.

## 14. Chọn cách xử lý theo yêu cầu

| Tình huống | Cách tổ chức phù hợp |
|---|---|
| Kết quả chỉ cần khi HTTP response còn mở | Giữ công việc trong publisher của request và cho cancellation truyền về nguồn |
| Tác vụ phải tiếp tục sau khi client rời đi | Tạo job bền vững, trả job ID và giao worker xử lý |
| Người dùng có thể chủ động hủy tác vụ | Dùng lệnh cancel job riêng và cancellation token cho worker |
| Tác vụ dùng thư viện blocking | Chạy trên scheduler phù hợp, kiểm tra khả năng interrupt và cung cấp checkpoint |
| Tác vụ giữ cursor, session hoặc file | Gắn tài nguyên với subscription của worker và cleanup ở complete/error/cancel |
| Tác vụ phải sống qua restart | Lưu trạng thái, lease, checkpoint và thiết kế retry/idempotency |

Không có một cơ chế cancellation duy nhất giải quyết mọi loại công việc. Cancellation của Reactive Streams quản lý việc phát tín hiệu trong subscription. Vòng đời job quản lý một đơn vị công việc nghiệp vụ. Hai cơ chế cần được kết nối có chủ đích nhưng không nên đánh đồng.

## 15. Checklist thiết kế tác vụ kéo dài

Trước khi triển khai, hãy trả lời:

1. Công việc thuộc về request hiện tại hay phải tiếp tục sau khi caller rời đi?
2. Ai sở hữu subscription thực thi và ai chịu trách nhiệm hủy nó?
3. Client disconnect có nên hủy công việc hay chỉ dừng việc gửi response?
4. Người dùng có lệnh hủy job riêng không, và worker nhận lệnh đó bằng cách nào?
5. Nguồn, driver và thư viện ngoài có hỗ trợ cancellation hoặc interruption không?
6. Tài nguyên được cấp phát và cleanup ở complete, error, cancel như thế nào?
7. Nếu process dừng giữa chừng, job có thể được phục hồi từ checkpoint không?
8. Side effect có idempotent hoặc có cơ chế chống trùng không?
9. Có metric cho job age, thời gian chạy, số lần retry và cancellation không?
10. Kiểm thử đã phân biệt request cancellation với job cancellation chưa?

Khi tách rõ quyền sở hữu của request và job, một subscriber có thể ngừng chờ mà không làm mất công việc nghiệp vụ đã được tiếp nhận. Ngược lại, những tác vụ chỉ phục vụ response vẫn có thể dừng và giải phóng tài nguyên khi không còn người tiêu thụ. Đây là nền tảng để quản lý tác vụ dài an toàn trong các ứng dụng reactive Java.
