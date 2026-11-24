# Đọc dữ liệu lớn theo từng phần thay vì nạp toàn bộ

Khi xử lý một tệp vài gigabyte, một truy vấn trả về hàng triệu bản ghi hoặc một HTTP response có payload lớn, cách đọc toàn bộ dữ liệu vào một List hay byte array có thể làm bộ nhớ tăng nhanh và tạo độ trễ trước khi xử lý bắt đầu. Một pipeline reactive có thể đọc và chuyển tiếp từng phần dữ liệu theo nhu cầu của downstream, nhờ đó giữ lượng dữ liệu đang hoạt động ở mức có thể kiểm soát.

Đọc theo từng phần không chỉ là chia một danh sách lớn thành các danh sách nhỏ sau khi đã nạp xong. Nguồn I/O phải thực sự đọc tăng dần; mỗi phần được chuyển vào pipeline khi có nhu cầu, được xử lý xong rồi mới tiếp tục đọc phần tiếp theo. Với I/O chặn trong Java, cần cô lập thao tác đọc khỏi event loop. Với nguồn reactive không chặn, cần giữ demand xuyên suốt từ subscriber đến driver hoặc hệ thống cung cấp dữ liệu.

Bài học thuộc chương **Tích hợp I/O** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; các kỹ thuật trong bài kết hợp Mono, Flux, toán tử, scheduler, xử lý lỗi và kiểm thử pipeline Java.

Các ví dụ sử dụng Project Reactor và Java hiện đại. Những tên như repository, importService hoặc Record đại diện cho thành phần của ứng dụng; cần bổ sung import, kiểu miền và API lưu trữ tương ứng khi áp dụng vào dự án.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao readAllBytes, readAllLines và collectList không phù hợp với nguồn dữ liệu rất lớn hoặc không giới hạn.
- Tạo Flux đọc tệp theo từng dòng, chỉ mở tài nguyên khi có subscription và đóng khi complete, error hoặc cancel.
- Cô lập I/O chặn bằng boundedElastic và phân biệt nó với I/O reactive không chặn.
- Chia dữ liệu thành batch hữu hạn để ghi hoặc gửi theo nhóm.
- Giới hạn số batch đang xử lý đồng thời và dự đoán bộ nhớ có thể bị giữ.
- Kiểm thử đọc tăng dần, lỗi đọc, cancellation và việc đóng tài nguyên.

## 1. Vì sao nạp toàn bộ dữ liệu dễ gây vấn đề?

Các API tiện dụng như Files.readAllBytes, Files.readAllLines hoặc readString thường trả về toàn bộ nội dung sau khi đọc xong. Tương tự, collectList giữ mọi phần tử của Flux rồi mới phát một List khi nguồn hoàn tất.

~~~java
List<String> allLines = Files.readAllLines(path);

Mono<List<Record>> allRecords =
    repository.findAll()
        .collectList();
~~~

Với dữ liệu nhỏ, cách này đơn giản và có thể hoàn toàn phù hợp. Nhưng khi dữ liệu lớn, nó tạo ra một số vấn đề:

- **Bộ nhớ tăng theo kích thước nguồn:** toàn bộ byte, dòng hoặc object phải tồn tại trong heap cùng lúc.
- **Độ trễ trước khi xử lý:** downstream chỉ bắt đầu làm việc sau khi thao tác đọc hoặc thu thập hoàn tất.
- **Áp lực garbage collection:** nhiều object lớn được tạo và giữ lâu có thể làm tăng thời gian GC.
- **Không phù hợp với nguồn dài hạn:** một Flux không hoàn tất sẽ khiến collectList không phát kết quả và tiếp tục tích lũy.
- **Khó hủy công việc đang đọc:** nếu thao tác đọc đồng bộ đã nạp hết dữ liệu, cancellation đến sau đó không thu hồi được chi phí I/O đã thực hiện.

Đọc theo từng phần giúp pipeline xử lý một lượng dữ liệu nhỏ hơn tại mỗi thời điểm. Tuy nhiên, chỉ thay List bằng Flux chưa đủ. Nếu nguồn vẫn gọi readAllLines trước khi tạo Flux, toàn bộ dữ liệu đã được nạp trước khi backpressure có tác dụng.

## 2. Đọc tệp theo từng dòng với Flux

Một cách đọc tệp tăng dần là mở BufferedReader rồi tạo một Flux phát một dòng mỗi lần được yêu cầu. Reactor cung cấp Flux.generate để tạo tín hiệu đồng bộ từng bước. Kết hợp với using, tài nguyên được mở theo subscription và được đóng khi subscription kết thúc.

~~~java
Flux<String> readLines(Path path) {
    return Flux.using(
        () -> {
            try {
                return Files.newBufferedReader(
                    path,
                    StandardCharsets.UTF_8
                );
            } catch (IOException error) {
                throw new UncheckedIOException(error);
            }
        },
        reader -> Flux.<String>generate(sink -> {
            try {
                String line = reader.readLine();

                if (line == null) {
                    sink.complete();
                } else {
                    sink.next(line);
                }
            } catch (IOException error) {
                sink.error(error);
            }
        }),
        reader -> {
            try {
                reader.close();
            } catch (IOException error) {
                throw new UncheckedIOException(error);
            }
        }
    ).subscribeOn(Schedulers.boundedElastic());
}
~~~

Có ba phần quan trọng:

1. Resource supplier mở một BufferedReader mới khi có subscription. Nếu tệp không mở được, lỗi được chuyển thành lỗi runtime để pipeline phát onError.
2. Source supplier dùng Flux.generate để đọc một dòng trong mỗi lần tạo tín hiệu. Khi readLine trả null, nguồn phát onComplete; nếu đọc lỗi, nguồn phát onError.
3. Cleanup đóng BufferedReader khi nguồn hoàn tất, phát lỗi hoặc bị hủy.

readLine là thao tác I/O chặn. subscribeOn với boundedElastic chuyển việc subscribe và yêu cầu dữ liệu từ nguồn đồng bộ sang scheduler phù hợp với tác vụ có khả năng chặn. Không chạy thao tác đọc tệp chặn trên event loop của WebFlux hoặc một scheduler dành cho xử lý CPU ngắn.

Flux.generate phát từng phần tử theo vòng lặp đồng bộ gắn với demand. Nếu subscriber chỉ yêu cầu một phần tử, nguồn không cần đọc trước toàn bộ tệp. Khi subscriber yêu cầu thêm, generator tiếp tục đọc. Đây là điểm khác biệt cốt lõi so với việc gọi readAllLines trước rồi mới tạo Flux.

### Vì sao phải dùng using?

Nếu chỉ mở BufferedReader bên ngoài rồi đưa vào Flux.generate, tài nguyên có thể không được đóng khi subscriber hủy hoặc khi đọc lỗi. using gắn quyền sở hữu reader với subscription:

- Mỗi subscription mở một reader riêng.
- Complete đóng reader.
- Error đóng reader.
- Cancel đóng reader dù nguồn chưa đọc hết.

Không tái sử dụng cùng một BufferedReader cho nhiều subscriber. Reader là trạng thái mutable, chỉ có thể đọc tuần tự và có vòng đời riêng. Đặt việc mở reader trong resource supplier giúp mỗi lượt đăng ký có tài nguyên độc lập.

### Khi nào dùng Flux.fromStream?

Với Java Stream có hỗ trợ đóng như Files.lines, có thể dùng using để quản lý stream:

~~~java
Flux<String> lines =
    Flux.using(
        () -> {
            try {
                return Files.lines(path, StandardCharsets.UTF_8);
            } catch (IOException error) {
                throw new UncheckedIOException(error);
            }
        },
        Flux::fromStream,
        stream -> stream.close()
    ).subscribeOn(Schedulers.boundedElastic());
~~~

Files.lines đọc lười và Stream phải được đóng. using bảo đảm stream được tạo mới cho mỗi subscription và được đóng theo vòng đời tiêu thụ. Không tạo Files.lines trước khi trả Publisher rồi đóng stream ngay trong khối try-with-resources, vì subscriber sẽ nhận một stream đã đóng.

Dùng BufferedReader với Flux.generate khi muốn thấy rõ từng lần đọc và kiểm soát hành vi đọc. Dùng Files.lines khi xử lý theo dòng là đủ và API Stream đáp ứng yêu cầu. Cả hai ví dụ đều dùng I/O chặn nên cần scheduler phù hợp.

## 3. Demand và backpressure trong quá trình đọc

Trong Reactive Streams, downstream gửi request(n) để báo số phần tử có thể nhận. Nếu nguồn đọc tệp được xây dựng như trên, mỗi lần generator phát một dòng là một phần tử của Flux. Nguồn có thể đọc tăng dần theo demand thay vì nạp toàn bộ tệp.

Có thể quan sát demand:

~~~java
Flux<String> lines =
    readLines(path)
        .doOnRequest(n ->
            log.debug("Số dòng downstream yêu cầu: {}", n)
        );
~~~

Nếu downstream chỉ request 10 dòng rồi cancel, pipeline chỉ cần đọc phần dữ liệu tương ứng với số phần tử đã tiêu thụ, cộng thêm lượng đệm mà các toán tử hoặc tầng I/O có thể sử dụng. Không nên giả định mọi nguồn đều chỉ đọc chính xác n phần tử: một số driver có prefetch, bộ đệm đọc theo byte hoặc queue nội bộ.

Backpressure chỉ có tác dụng nếu nguồn có thể điều tiết việc phát theo request. Với callback push không thể tạm dừng, adapter phải chọn buffer, drop, latest hoặc error theo nghiệp vụ. Đọc tệp bằng Flux.generate là nguồn đồng bộ có thể đáp ứng demand; một SDK callback đẩy dữ liệu liên tục có đặc tính khác.

### limitRate không phải giới hạn bộ nhớ tổng

Có thể dùng limitRate để chia nhỏ các request được truyền upstream:

~~~java
Flux<Record> records =
    repository.findAll()
        .limitRate(128);
~~~

limitRate điều chỉnh cách yêu cầu dữ liệu ở ranh giới toán tử. Nó không tự đặt giới hạn byte cho object, không kiểm soát mọi queue nội bộ của driver và không thay thế giới hạn concurrency ở downstream. Hãy dùng nó như một phần của thiết kế demand, sau đó đo bộ nhớ và hành vi thực tế của nguồn.

## 4. Xử lý dữ liệu theo batch hữu hạn

Nhiều hệ thống đích hoạt động hiệu quả hơn khi nhận dữ liệu theo nhóm: ghi nhiều bản ghi trong một transaction, gửi nhiều dòng trong một request hoặc xử lý một nhóm message. Có thể dùng buffer(n) để gom tối đa n phần tử thành một List:

~~~java
Flux<ImportResult> importResults =
    readLines(path)
        .map(this::parseRecord)
        .buffer(500)
        .concatMap(
            batch -> importRepository.insertBatch(batch),
            1
        );
~~~

Pipeline đọc dòng tăng dần, chuyển thành Record, gom tối đa 500 bản ghi rồi gọi thao tác ghi batch. concatMap chỉ đăng ký batch tiếp theo sau khi Publisher ghi batch hiện tại hoàn tất. Cách này giữ thứ tự xử lý batch và giới hạn số batch đang được gửi đến repository ở mức một cho subscription này.

buffer(500) không đợi đủ 500 phần tử mới hoàn tất toàn bộ pipeline. Khi nguồn hoàn tất, batch cuối chưa đủ 500 phần tử vẫn được phát. Nếu nguồn là luồng dài hạn không hoàn tất, batch chưa đầy sẽ chờ cho đến khi đủ phần tử; khi cần giới hạn thời gian chờ, cân nhắc bufferTimeout.

### Giới hạn đồng thời khi ghi nhiều batch

Nếu repository cho phép ghi song song, có thể dùng flatMap với concurrency hữu hạn:

~~~java
Flux<ImportResult> importResults =
    readLines(path)
        .map(this::parseRecord)
        .buffer(500)
        .flatMap(
            batch -> importRepository.insertBatch(batch),
            4,
            1
        );
~~~

Ví dụ cho phép tối đa bốn Publisher ghi batch hoạt động đồng thời và đặt prefetch của mỗi Publisher con là một phần tử. Tham số prefetch không phải giới hạn byte; mỗi batch vẫn có thể lớn. Điều này có thể tăng throughput khi hệ thống đích xử lý song song tốt, nhưng cũng làm tăng số batch đang được giữ và số connection có thể sử dụng.

Chọn concatMap khi cần thứ tự và tải thấp. Overload concatMap ở trên đặt prefetch bằng một để hạn chế số batch được yêu cầu trước từ upstream. Chọn flatMap với concurrency hữu hạn khi các batch độc lập và hệ thống đích có đủ năng lực. Không dùng concurrency lớn chỉ để làm nguồn đọc nhanh hơn; nếu database hoặc API đích đã quá tải, concurrency cao làm queue và độ trễ tăng.

### Ước lượng bộ nhớ của batch

Một ước lượng đơn giản:

\[
\text{Bộ nhớ payload} \approx
\text{kích thước batch}
\times
\text{kích thước trung bình mỗi bản ghi}
\times
\text{số batch đang hoạt động}
\]

Nếu một batch có 500 bản ghi, mỗi bản ghi chiếm trung bình 2 KB và tối đa bốn batch đang được xử lý, payload có thể vào khoảng 4 MB. Con số thực tế còn bao gồm object header, tham chiếu, chuỗi, cấu trúc List, queue của toán tử, dữ liệu prefetch và bộ nhớ trong driver.

Ngoài số phần tử, hãy kiểm soát kích thước bản ghi. Một dòng CSV hoặc JSON bất thường dài hàng trăm megabyte vẫn có thể chiếm bộ nhớ lớn dù batch chỉ có một phần tử. Nếu kích thước bản ghi không đáng tin cậy, đặt giới hạn độ dài hoặc xử lý theo byte/chunk thay vì đọc nguyên dòng.

## 5. Đọc theo byte hoặc DataBuffer

Không phải dữ liệu nào cũng phù hợp với ranh giới dòng. Tệp nhị phân, video, ảnh hoặc HTTP body có thể được đọc theo từng khối byte. Trong Spring WebFlux, DataBufferUtils có thể đọc một Resource thành Flux<DataBuffer> với kích thước buffer cấu hình được:

~~~java
Flux<DataBuffer> chunks =
    DataBufferUtils.read(
        resource,
        bufferFactory,
        16 * 1024
    );
~~~

Mỗi DataBuffer chứa một phần dữ liệu. Kích thước 16 KB ở đây là kích thước buffer đọc, không phải giới hạn tổng bộ nhớ của toàn pipeline. Nếu downstream xử lý chậm hoặc tạo nhiều queue, nhiều DataBuffer vẫn có thể cùng tồn tại.

DataBuffer có quy tắc quản lý bộ nhớ riêng, đặc biệt khi dùng pooled buffer. Thành phần tiêu thụ cần giải phóng buffer sau khi đọc xong, hoặc retain đúng cách nếu chuyển quyền sở hữu sang bước bất đồng bộ khác. Không giải phóng quá sớm khi một bước sau vẫn cần dữ liệu; cũng không quên release khi xử lý lỗi hoặc cancel. Khi có thể, ưu tiên các API WebFlux đã quản lý vòng đời DataBuffer thay vì tự thao tác ref-count mà không hiểu hợp đồng.

### Ranh giới UTF-8 có thể nằm giữa hai chunk

Khi đọc theo byte, không được giả định mỗi chunk kết thúc đúng ở ranh giới ký tự hoặc dòng. Một ký tự UTF-8 có thể gồm nhiều byte và bị chia giữa hai DataBuffer. Tương tự, một dòng văn bản có thể kéo dài qua nhiều chunk.

Muốn chuyển byte chunk thành văn bản, cần decoder giữ lại các byte chưa hoàn chỉnh giữa các lần đọc, đồng thời xử lý delimiter dòng xuyên ranh giới buffer. Không gọi new String(chunk, UTF_8) độc lập cho từng chunk nếu dữ liệu có thể bị cắt giữa một ký tự. Với tệp văn bản theo dòng thông thường, BufferedReader đã xử lý việc giải mã và ranh giới dòng nên thường đơn giản hơn.

## 6. Đọc kết quả database theo từng phần

Một truy vấn database có thể trả về rất nhiều bản ghi. Nếu driver hỗ trợ reactive và streaming, hãy giữ kết quả ở dạng Flux để demand truyền đến driver:

~~~java
Flux<CustomerRecord> customers =
    customerRepository.findAllActive()
        .map(this::toCustomerRecord);
~~~

Không gọi collectList nếu ứng dụng có thể xử lý từng bản ghi hoặc từng batch. Nếu cần ghi sang hệ thống khác, kết hợp buffer và concatMap/flatMap có giới hạn như phần trước.

Tuy nhiên, chữ ký Flux không tự bảo đảm driver không nạp toàn bộ kết quả vào bộ nhớ. Cần xác minh driver và cấu hình fetch/cursor:

- Driver có thực sự lấy từng phần từ database không?
- Fetch size hoặc cursor có được cấu hình phù hợp không?
- Connection có được giữ mở trong toàn bộ quá trình tiêu thụ không?
- Cancellation có đóng cursor và trả connection về pool không?
- Transaction có còn hiệu lực trong lúc downstream xử lý chậm không?

Với JDBC truyền thống, ResultSet thường là API chặn và cần quản lý connection, statement, cursor. Có thể cô lập nó bằng boundedElastic và đóng các tài nguyên trong using, nhưng phải xác nhận driver thực sự streaming theo fetch size. Bọc một ResultSet đã nạp toàn bộ vào Flux không làm giảm bộ nhớ.

Với R2DBC hoặc reactive driver khác, demand có thể truyền đến nguồn dữ liệu, nhưng vẫn cần xem tài liệu driver về fetch, prefetch và vòng đời transaction. Một pipeline reactive tốt phải quản lý cả resource và lượng dữ liệu được giữ ở driver, không chỉ ở các toán tử Reactor.

## 7. Gửi HTTP response lớn theo luồng

Trong WebFlux, controller có thể trả Flux thay vì tạo một List lớn:

~~~java
@GetMapping(value = "/export", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ExportRow> exportRows() {
    return exportService.streamRows();
}
~~~

WebFlux có thể ghi từng phần tử khi downstream và kết nối mạng sẵn sàng nhận. Điều này giúp tránh tạo một collection toàn bộ trong controller. Với JSON array hoặc định dạng tải tệp, chọn media type và encoder phù hợp với giao thức mà client mong đợi; TEXT_EVENT_STREAM chỉ là ví dụ cho luồng sự kiện, không phải định dạng mặc định cho mọi file export.

Streaming response không bảo đảm toàn bộ chuỗi hệ thống đều có bộ nhớ hữu hạn. Hãy kiểm tra:

- Service có trả Flux thật sự tăng dần hay đã collectList trước đó?
- Encoder có buffer toàn bộ nội dung hay ghi theo từng phần?
- Client đọc chậm thì backpressure có truyền ngược đến nguồn không?
- Proxy hoặc gateway có buffer response không?
- Khi client ngắt kết nối, truy vấn database hoặc đọc tệp có bị hủy và giải phóng không?

Nếu client tải file, cân nhắc stream DataBuffer hoặc byte chunk với quy tắc release rõ ràng. Nếu response cần Content-Length, có thể cần biết kích thước trước; với dữ liệu không biết trước, dùng truyền tải chunked hoặc giao thức streaming phù hợp.

## 8. Xử lý lỗi khi đọc từng phần

Lỗi I/O có thể xảy ra lúc mở tệp, giữa quá trình đọc hoặc khi đóng tài nguyên. Pipeline cần giữ lỗi gốc và xác định liệu một lỗi có làm dừng toàn bộ tác vụ hay chỉ bỏ qua một bản ghi.

Trong ví dụ Flux.generate, lỗi đọc được gửi bằng sink.error. Khi đó using đóng reader và downstream nhận onError. Nếu một dòng không hợp lệ nhưng có thể bỏ qua, hãy xử lý lỗi ở bước parse theo chính sách rõ ràng:

~~~java
Flux<ParsedRecord> parsed =
    readLines(path)
        .index()
        .flatMap(tuple -> {
            long lineNumber = tuple.getT1();
            String line = tuple.getT2();

            return Mono.fromCallable(() -> parse(line))
                .onErrorResume(error -> {
                    log.warn(
                        "Bỏ qua dòng {} do dữ liệu không hợp lệ",
                        lineNumber,
                        error
                    );
                    return Mono.empty();
                });
        });
~~~

Ví dụ này bỏ bản ghi lỗi và tiếp tục với dòng sau. Chỉ dùng khi nghiệp vụ cho phép bỏ dòng lỗi và có nơi lưu lại thông tin để sửa hoặc đối soát. Với dữ liệu tài chính hoặc kiểm toán, có thể cần dừng toàn bộ import hoặc ghi lỗi vào một luồng dead-letter thay vì âm thầm bỏ.

Nếu lỗi đến từ database hoặc network, retry chỉ an toàn khi thao tác có tính idempotent hoặc có khóa chống ghi trùng. Khi batch đã được ghi một phần rồi retry toàn batch, cần hiểu transaction và tính lặp lại của API đích.

## 9. Cancellation phải dừng đọc và giải phóng tài nguyên

Một subscriber có thể không còn cần dữ liệu, ví dụ client đóng kết nối hoặc người dùng hủy import. Cancellation nên truyền ngược qua pipeline để dừng nguồn nếu nguồn hỗ trợ.

Với reader được tạo bằng using, cancellation đóng BufferedReader. Với database cursor, driver cần nhận cancel và giải phóng cursor/connection. Với DataBuffer, buffer đang được giữ phải được release theo đúng quyền sở hữu. Với SDK callback, adapter cần hủy đăng ký.

Không phải mọi thao tác I/O đã bắt đầu đều dừng tức thì. Một lệnh blocking read có thể đang chờ hệ điều hành hoặc driver; việc cancel có thể chỉ được xử lý sau khi thao tác trả về. Đặt timeout và chọn API có khả năng hủy phù hợp nếu độ trễ dừng là yêu cầu quan trọng.

Tránh dùng doOnCancel như cơ chế sở hữu duy nhất cho tài nguyên được tạo bên ngoài pipeline. Dùng using hoặc usingWhen để ràng buộc resource với subscription; dùng hook như doOnCancel để quan sát hoặc ghi metrics bổ sung.

## 10. Kiểm thử đọc tăng dần và giải phóng tài nguyên

Nên kiểm thử ít nhất các trường hợp:

- Đọc hết tệp và nhận complete.
- Tệp rỗng.
- Lỗi mở tệp hoặc lỗi đọc giữa chừng.
- Subscriber chỉ request một số dòng rồi cancel.
- Nhiều subscription mở reader riêng.
- Batch cuối chưa đủ kích thước vẫn được xử lý.
- Downstream chậm và concurrency bị giới hạn.

Có thể kiểm tra demand với một nguồn Flux đơn giản trước khi tích hợp file I/O:

~~~java
AtomicInteger produced = new AtomicInteger();

Flux<Integer> source =
    Flux.range(1, 100)
        .doOnNext(value -> produced.incrementAndGet());

StepVerifier.create(source, 0)
    .thenRequest(3)
    .expectNext(1, 2, 3)
    .thenCancel()
    .verify();

assertEquals(3, produced.get());
~~~

Ví dụ này xác nhận nguồn range chỉ phát ba phần tử khi subscriber request ba phần tử rồi hủy. Với nguồn file thực tế, các tầng buffer hoặc prefetch có thể làm số lần đọc khác với số phần tử được quan sát ở downstream; vì vậy, hãy đo ở đúng ranh giới cần kiểm tra.

### Kiểm tra reader được đóng khi cancel

Có thể tách resource supplier để kiểm thử bằng một reader giả hoặc wrapper theo dõi close:

~~~java
AtomicBoolean closed = new AtomicBoolean();

Flux<String> source = Flux.using(
    () -> new BufferedReader(new StringReader("one\ntwo\nthree")) {
        @Override
        public void close() throws IOException {
            closed.set(true);
            super.close();
        }
    },
    reader -> Flux.<String>generate(sink -> {
        try {
            String line = reader.readLine();
            if (line == null) {
                sink.complete();
            } else {
                sink.next(line);
            }
        } catch (IOException error) {
            sink.error(error);
        }
    }),
    reader -> {
        try {
            reader.close();
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }
);

StepVerifier.create(source)
    .expectNext("one")
    .thenCancel()
    .verify();

assertTrue(closed.get());
~~~

Kiểm thử đọc một dòng rồi hủy. Cờ closed xác nhận cleanup được gọi. Trong test tích hợp, nên dùng tệp tạm thật và xác nhận có thể mở lại hoặc xóa tệp sau cancellation, đặc biệt trên Windows nơi handle còn mở có thể ngăn thao tác xóa.

### Kiểm tra batch cuối

~~~java
StepVerifier.create(
        Flux.range(1, 7)
            .buffer(3)
    )
    .expectNext(List.of(1, 2, 3))
    .expectNext(List.of(4, 5, 6))
    .expectNext(List.of(7))
    .verifyComplete();
~~~

Nguồn có bảy phần tử nên phát hai batch đủ ba phần tử và một batch cuối chỉ có một phần tử khi nguồn hoàn tất. Điều này giúp tránh mất dữ liệu cuối khi batch chưa đầy.

## 11. Các lỗi thường gặp khi đọc dữ liệu lớn

**Tạo Flux sau khi đã nạp toàn bộ nội dung.** Flux.just(Files.readAllLines(path)) vẫn giữ toàn bộ List trong bộ nhớ. Hãy tạo nguồn đọc tăng dần.

**Dùng collectList để chuyển một nguồn lớn thành List.** Chỉ dùng khi có giới hạn rõ ràng và kích thước phù hợp với bộ nhớ.

**Chạy I/O chặn trên event loop.** Đưa thao tác chặn sang boundedElastic hoặc chọn API I/O reactive không chặn.

**Không đóng stream khi cancel.** Quản lý reader, stream, cursor và connection bằng using/usingWhen.

**Dùng buffer lớn mà không tính kích thước phần tử.** Giới hạn số phần tử chưa đủ nếu mỗi phần tử có thể rất lớn; cân nhắc giới hạn byte hoặc kích thước bản ghi.

**Dùng flatMap không giới hạn cho batch ghi.** Concurrency cao có thể làm database, connection pool và bộ nhớ bị quá tải. Chọn giới hạn dựa trên năng lực hệ thống đích.

**Giả định driver có Flux là streaming thật.** Kiểm tra fetch size, cursor, prefetch và việc hủy trong tài liệu driver.

**Giải mã từng chunk độc lập.** Ký tự UTF-8 và dòng văn bản có thể bị chia giữa hai buffer. Dùng decoder giữ trạng thái hoặc API đọc theo dòng.

**Bỏ qua lỗi parse mà không lưu dấu vết.** Ghi số dòng, nguyên nhân và dữ liệu cần đối soát; chỉ bỏ qua khi nghiệp vụ cho phép.

## 12. Quy trình thiết kế pipeline I/O tăng dần

Trước khi triển khai, hãy xác định:

1. **Nguồn thực sự có streaming không?** Kiểm tra API đọc, driver database hoặc HTTP client; tránh tạo List toàn bộ trước khi dựng Flux.
2. **Đơn vị dữ liệu là gì?** Dòng, record, byte chunk, DataBuffer hay batch.
3. **I/O có chặn không?** Dùng boundedElastic để cô lập thao tác chặn; giữ nguyên API reactive nếu nguồn hỗ trợ I/O không chặn.
4. **Ai sở hữu tài nguyên?** Mở theo subscription và đóng trên complete, error, cancel.
5. **Demand truyền đến đâu?** Xem prefetch và queue ở toán tử, driver, client và proxy.
6. **Batch và concurrency được giới hạn thế nào?** Chọn kích thước batch, số tác vụ đồng thời và chính sách khi downstream chậm.
7. **Bộ nhớ tối đa có thể giữ là bao nhiêu?** Tính cả payload, object graph, queue và buffer đang hoạt động.
8. **Lỗi được xử lý ở cấp nào?** Phân biệt lỗi I/O toàn nguồn với lỗi một bản ghi.
9. **Cancellation có dừng công việc thật không?** Kiểm tra khả năng hủy của driver và API bên ngoài.
10. **Đã kiểm thử đường biên chưa?** Tệp rỗng, dòng rất dài, lỗi giữa chừng, batch cuối, cancel và tải chậm.

Đọc theo từng phần là một thuộc tính của toàn pipeline. Nếu bất kỳ tầng nào gom toàn bộ dữ liệu, tạo queue không giới hạn hoặc giữ tài nguyên sau cancellation, lợi ích về bộ nhớ và khả năng dừng sẽ bị mất.

## 13. Bài tập vận dụng

Một dịch vụ cần import tệp CSV 8 GB vào database. Tệp có một dòng tiêu đề, mỗi dòng dữ liệu đại diện một giao dịch. Database có API reactive ghi theo batch; mỗi batch nên có tối đa 400 bản ghi. Client có thể hủy import, và một số dòng có thể sai định dạng.

Hãy thiết kế pipeline đáp ứng yêu cầu:

1. Dùng BufferedReader hoặc Files.lines để đọc tăng dần; giải thích vì sao readAllLines không phù hợp.
2. Bỏ dòng tiêu đề mà không nạp toàn bộ tệp.
3. Parse từng dòng và ghi nhận số dòng nếu parse lỗi.
4. Gom tối đa 400 bản ghi mỗi batch.
5. Chọn concatMap hay flatMap với concurrency hữu hạn để ghi database; giải thích ảnh hưởng đến thứ tự và số batch đang hoạt động.
6. Bảo đảm reader được đóng khi import hoàn tất, lỗi hoặc client hủy.
7. Xác định cách xử lý batch cuối chưa đủ 400 phần tử.
8. Đề xuất metrics: số byte/dòng đã đọc, số bản ghi hợp lệ, số dòng lỗi, số batch ghi thành công, thời gian ghi và số lần cancel.
9. Viết StepVerifier cho tệp nhỏ, lỗi parse và cancellation sau một số dòng.

Một thiết kế tốt phải giữ dữ liệu tăng dần từ nguồn đến database, có giới hạn rõ cho batch và công việc đồng thời, đồng thời giải phóng tài nguyên trên mọi đường kết thúc. Nếu yêu cầu import phải tiếp tục sau khi client ngắt kết nối, hãy tách tác vụ import khỏi vòng đời HTTP request và quản lý nó như một job có trạng thái riêng.

## Kết luận

Đọc dữ liệu lớn theo từng phần giúp tránh tạo một bản sao toàn bộ nguồn trong heap và cho phép downstream bắt đầu xử lý sớm. Với I/O chặn, có thể dùng BufferedReader hoặc Files.lines kết hợp using và boundedElastic; với nguồn reactive, cần xác minh driver thực sự hỗ trợ streaming và demand. buffer tạo batch hữu hạn, còn concatMap hoặc flatMap có concurrency giới hạn kiểm soát số batch đang hoạt động. Quản lý tài nguyên, backpressure, lỗi và cancellation xuyên suốt pipeline mới giúp việc đọc tăng dần hoạt động ổn định trong ứng dụng Java reactive.
