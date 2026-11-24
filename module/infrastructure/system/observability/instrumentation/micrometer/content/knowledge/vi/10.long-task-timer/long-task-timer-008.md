# Đọc dữ liệu công bố và kiểm chứng khi tác vụ kết thúc hoặc bị lỗi

Micrometer LongTaskTimer theo dõi những tác vụ có thể chạy đủ lâu để cần quan sát ngay trong lúc chúng vẫn đang hoạt động. Khác với Timer thông thường, LongTaskTimer công bố số tác vụ đang chạy, tổng thời gian đã trôi qua của các tác vụ đang chạy và thời gian của tác vụ đang chạy lâu nhất. Khi một tác vụ kết thúc, mã ứng dụng phải dừng sample để LongTaskTimer loại tác vụ đó khỏi tập đang hoạt động.

Dữ liệu LongTaskTimer mô tả **trạng thái của các tác vụ đang chạy tại thời điểm đọc**. Nó không giữ lịch sử thời lượng của những tác vụ đã hoàn tất. Muốn phân tích thời lượng sau khi hoàn tất, cần ghi thêm vào Timer thông thường. Khi tác vụ kết thúc bằng exception, bị từ chối hoặc bị hủy, sample vẫn cần được dừng trong nhánh cleanup để số tác vụ đang chạy không bị giữ lại sai lệch.

## 1. LongTaskTimer công bố những số liệu nào?

LongTaskTimer phù hợp với công việc có thời gian thực thi dài hoặc không xác định trước, chẳng hạn tạo báo cáo, đồng bộ dữ liệu, xử lý batch, chạy migration hoặc thực hiện một quy trình nền. Trong lúc công việc còn chạy, meter cung cấp ba phép đo chính:

| Phép đo | API | Ý nghĩa |
|---|---|---|
| Số tác vụ đang hoạt động | **activeTasks()** | Số sample đã bắt đầu và chưa dừng |
| Tổng thời gian đang chạy | **duration(TimeUnit)** | Tổng thời lượng đã trôi qua của tất cả tác vụ đang hoạt động |
| Tác vụ đang chạy lâu nhất | **max(TimeUnit)** | Thời lượng lớn nhất trong số các tác vụ đang hoạt động |

Ví dụ, tại một thời điểm có ba báo cáo đang được tạo. Chúng đã chạy lần lượt 10 giây, 15 giây và 20 giây. LongTaskTimer có thể công bố:

- **activeTasks()** bằng 3.
- **duration(TimeUnit.SECONDS)** xấp xỉ 45 giây.
- **max(TimeUnit.SECONDS)** xấp xỉ 20 giây.

Các giá trị thời lượng tiếp tục tăng khi tác vụ còn chạy. Nếu tác vụ 20 giây hoàn tất và sample được dừng, số tác vụ hoạt động giảm còn 2; tổng thời gian hoạt động và giá trị max được tính lại trên hai tác vụ còn lại. Các giá trị này không phải tổng lịch sử của mọi tác vụ từng chạy.

## 2. Đăng ký LongTaskTimer và bắt đầu một sample

LongTaskTimer được đăng ký vào MeterRegistry như các meter khác. Mỗi lần bắt đầu một tác vụ cần gọi **start()** để nhận một Sample đại diện cho lần chạy đó.

~~~java
LongTaskTimer reportTimer = LongTaskTimer.builder("reports.generation")
    .description("Theo dõi các tác vụ tạo báo cáo đang chạy")
    .register(meterRegistry);

LongTaskTimer.Sample sample = reportTimer.start();
~~~

Lời gọi start làm xuất hiện một tác vụ đang hoạt động trong LongTaskTimer. Nếu cùng lúc có nhiều báo cáo, mỗi lần chạy cần có Sample riêng. **activeTasks()** đếm các Sample chưa được dừng, không phải số loại tác vụ hay số meter đã đăng ký.

Một cách sử dụng đầy đủ:

~~~java
public void generateReport(ReportRequest request) {
    LongTaskTimer.Sample sample = reportTimer.start();

    try {
        reportGenerator.generate(request);
    } finally {
        sample.stop();
    }
}
~~~

Khối finally bảo đảm sample được dừng khi phương thức kết thúc bình thường hoặc khi exception truyền ra ngoài. Nếu bỏ qua **stop()**, LongTaskTimer tiếp tục xem sample đó là đang hoạt động và thời lượng của nó tiếp tục tăng, dù phần công việc thực tế đã kết thúc.

Mỗi lần gọi start phải có một điểm kết thúc tương ứng. Không chia sẻ một Sample cho nhiều lần thực thi độc lập và không gọi stop nhiều lần cho cùng một lần chạy.

## 3. Đọc các phép đo khi tác vụ còn chạy

Ứng dụng có thể đọc trực tiếp các phép đo từ LongTaskTimer. Đây là số liệu tổng hợp của tất cả sample đang hoạt động tại thời điểm gọi:

~~~java
long active = reportTimer.activeTasks();

double totalActiveSeconds =
    reportTimer.duration(TimeUnit.SECONDS);

double longestActiveSeconds =
    reportTimer.max(TimeUnit.SECONDS);
~~~

Ba giá trị trả về có cách diễn giải khác nhau:

- **active** cho biết hiện có bao nhiêu tác vụ chưa hoàn tất theo instrumentation.
- **totalActiveSeconds** cộng thời gian đã trôi qua của tất cả tác vụ đang chạy.
- **longestActiveSeconds** cho biết tác vụ đang chạy lâu nhất đã tồn tại bao lâu.

Không đọc duration như tổng thời gian đã tiêu tốn trong cả ngày hoặc tổng thời lượng của các báo cáo đã hoàn tất. Khi không còn sample hoạt động, số tác vụ hoạt động và các phép đo thời lượng của tập đang chạy trở về 0.

Nếu có nhiều loại công việc, nên dùng tên meter riêng hoặc tag có tập giá trị giới hạn để phân biệt. Ví dụ, **reports.generation** có thể theo dõi tác vụ tạo báo cáo, còn **imports.execution** theo dõi tác vụ nhập dữ liệu. Không gắn ID của từng báo cáo hoặc từng lần chạy làm tag vì các ID này có cardinality cao.

## 4. Dữ liệu được công bố trong lúc chạy và sau khi dừng

LongTaskTimer thường xuất các phép đo đang hoạt động qua registry hoặc exporter. Backend có thể chuyển tên và đơn vị theo quy ước riêng, vì vậy tên metric cụ thể có thể khác nhau giữa các hệ thống. Với Prometheus registry, các phép đo thường được xuất thành những chuỗi riêng cho số tác vụ hoạt động, tổng thời lượng hoạt động và thời lượng hoạt động lớn nhất.

Có thể quan sát dữ liệu theo vòng đời:

| Thời điểm | activeTasks | duration | max |
|---|---:|---:|---:|
| Chưa có tác vụ | 0 | 0 | 0 |
| Một tác vụ chạy 8 giây | 1 | khoảng 8 giây | khoảng 8 giây |
| Tác vụ thứ hai chạy thêm 5 giây | 2 | khoảng 13 giây | khoảng 8 giây |
| Tác vụ đầu tiên dừng | 1 | khoảng 5 giây | khoảng 5 giây |
| Tác vụ thứ hai dừng | 0 | 0 | 0 |

Đây là ví dụ minh họa tại các thời điểm đọc. Giá trị thực tế có thể lệch một chút do thời điểm scrape và độ trễ xuất dữ liệu.

Khi tác vụ dừng, sample không còn thuộc tập đang hoạt động. Vì vậy, dashboard không thể dùng LongTaskTimer để xem lại thời lượng của tác vụ đã kết thúc. Nếu cần lịch sử thời lượng, hãy ghi nhận kết quả vào một Timer riêng.

## 5. Dừng sample khi thành công, exception hoặc bị từ chối

Sample phải được dừng bất kể tác vụ kết thúc theo đường đi nào. Cách đơn giản nhất là đặt **sample.stop()** trong finally:

~~~java
public void runImport(ImportRequest request) {
    LongTaskTimer.Sample sample = importLongTaskTimer.start();

    try {
        importService.execute(request);
    } finally {
        sample.stop();
    }
}
~~~

Nếu muốn phân loại outcome, có thể giữ trạng thái kết quả trong một biến có tập giá trị hữu hạn rồi ghi Counter hoặc Timer sau khi dừng sample:

~~~java
public void runImport(ImportRequest request) {
    LongTaskTimer.Sample sample = importLongTaskTimer.start();
    String result = "failure";

    try {
        importService.execute(request);
        result = "success";
    } catch (ImportRejectedException exception) {
        result = "rejected";
        throw exception;
    } finally {
        long elapsedNanos = sample.stop();

        meterRegistry.timer("imports.execution.duration", "result", result)
            .record(elapsedNanos, TimeUnit.NANOSECONDS);
    }
}
~~~

Trong ví dụ, LongTaskTimer theo dõi import trong khi chạy. Khi kết thúc, **sample.stop()** trả về thời lượng đã trôi qua tính bằng nanosecond. Thời lượng đó được ghi vào Timer thông thường với tag outcome để có thể phân tích sau khi tác vụ hoàn tất.

Đoạn mã minh họa cần được đặt trong component có **importLongTaskTimer** và **MeterRegistry** được inject. Timer được lấy từ registry sau khi đã xác định outcome. Trong thực tế, có thể dùng Timer.Sample hoặc một phương thức tiện ích riêng nếu cần chọn Timer đích sau khi biết kết quả. Dù chọn cách nào, vẫn phải bảo đảm sample của LongTaskTimer được dừng đúng một lần.

Nếu exception cần được xử lý hoặc chuyển tiếp, hãy ghi nhận outcome trước khi ném lại exception. Không để nhánh exception bỏ qua cleanup. Với tác vụ bị từ chối trước khi thực sự bắt đầu, không gọi start; nếu sample đã được tạo, phải dừng sample khi quyết định không thực thi tiếp.

## 6. Xử lý cancellation và interruption

Tác vụ nền có thể bị hủy bởi người dùng, timeout, shutdown của ứng dụng hoặc thread interruption. Khi mã tác vụ thoát qua finally, sample được dừng và không còn được tính vào **activeTasks()**.

~~~java
public void executeWithCancellation() {
    LongTaskTimer.Sample sample = backgroundTaskTimer.start();

    try {
        worker.run();
    } catch (CancellationException exception) {
        throw exception;
    } finally {
        sample.stop();
    }
}
~~~

Nếu tác vụ dùng interrupt để yêu cầu dừng, không được nuốt tín hiệu interrupt. Khi bắt InterruptedException, thường cần khôi phục trạng thái interrupt sau khi thực hiện cleanup:

~~~java
public void executeInterruptibly() {
    LongTaskTimer.Sample sample = backgroundTaskTimer.start();

    try {
        worker.runInterruptibly();
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Tác vụ bị ngắt", exception);
    } finally {
        sample.stop();
    }
}
~~~

Ví dụ trên chuyển InterruptedException thành exception của ứng dụng sau khi khôi phục interrupt flag. Tùy hợp đồng của API, có thể khai báo ném InterruptedException trực tiếp thay vì bọc exception. Điểm cốt lõi là mọi đường thoát có kiểm soát đều đi qua finally.

Không có cơ chế cleanup trong Java nào bảo đảm chạy khi tiến trình bị kill cưỡng bức, máy chủ mất điện hoặc JVM crash. Trong những tình huống đó, tiến trình và registry kết thúc; backend có thể giữ các mẫu đã scrape trước đó cho đến khi chúng hết hạn hoặc bị đánh dấu stale theo quy tắc của backend. LongTaskTimer không phải kho lưu trữ bền vững cho trạng thái tác vụ.

## 7. Kết hợp LongTaskTimer với Timer để có cả trạng thái và lịch sử

LongTaskTimer và Timer giải quyết hai câu hỏi khác nhau:

| Nhu cầu | LongTaskTimer | Timer |
|---|---|---|
| Biết hiện có bao nhiêu tác vụ đang chạy | Có, qua activeTasks | Không trực tiếp |
| Theo dõi tổng thời lượng của các tác vụ đang chạy | Có, qua duration | Không |
| Tìm tác vụ đang chạy lâu nhất | Có, qua max | Không |
| Ghi nhận thời lượng sau khi tác vụ hoàn tất | Không lưu lịch sử hoàn tất | Có |
| Phân tích histogram/percentile của tác vụ hoàn tất | Không phải mục tiêu của meter này | Có thể, tùy cấu hình |
| Đo đoạn mã ngắn, thường xuyên | Có thể, nhưng không phải lựa chọn phù hợp nhất | Phù hợp |

Nếu dashboard cần biết một batch đang chạy bao lâu và sau khi kết thúc cần phân tích phân phối thời lượng, hãy dùng cả hai meter. LongTaskTimer cung cấp tín hiệu trong khi batch hoạt động; Timer ghi lại thời lượng khi batch kết thúc.

~~~java
public void runBatch(Batch batch) {
    LongTaskTimer.Sample activeSample = batchLongTaskTimer.start();
    Timer.Sample completedSample = Timer.start(meterRegistry);
    String result = "failure";

    try {
        batchProcessor.process(batch);
        result = "success";
    } catch (BatchRejectedException exception) {
        result = "rejected";
        throw exception;
    } finally {
        activeSample.stop();

        completedSample.stop(
            meterRegistry.timer("batch.execution.duration", "result", result)
        );
    }
}
~~~

Ví dụ dùng LongTaskTimer để công bố trạng thái đang chạy và Timer.Sample để ghi thời lượng hoàn tất theo kết quả. Timer.Sample không thay thế LongTaskTimer; hai sample có mục đích và vòng đời riêng. Với meter **batch.execution.duration**, cần giữ tập khóa tag ổn định và giới hạn giá trị của khóa **result**.

Nếu chỉ cần thời lượng của công việc sau khi hoàn tất, Timer thường là đủ. Không cần đăng ký LongTaskTimer cho mọi phương thức ngắn hoặc mọi request nếu không có nhu cầu quan sát tác vụ đang hoạt động.

## 8. Đọc dữ liệu trong Spring Boot và backend giám sát

Trong ứng dụng Spring Boot có Actuator, các meter được đăng ký trong MeterRegistry có thể được xem qua endpoint metrics khi endpoint được bật và được phép truy cập. Endpoint tổng quan có thể liệt kê tên meter; endpoint chi tiết nhận tên meter để trả các phép đo và tag tương ứng. Tên metric hiển thị và cấu trúc phản hồi phụ thuộc phiên bản Spring Boot, registry và cấu hình.

Khi kiểm chứng LongTaskTimer, hãy xác nhận:

1. Meter đã được đăng ký với tên mong đợi.
2. Khi bắt đầu tác vụ, activeTasks tăng.
3. Khi tác vụ còn chạy, duration tăng theo thời gian và max phản ánh tác vụ hoạt động lâu nhất.
4. Khi tác vụ kết thúc hoặc phát sinh exception, activeTasks giảm sau khi sample dừng.
5. Khi không còn tác vụ, các phép đo của tập active trở về 0.
6. Nếu có Timer bổ sung, count và total time của Timer tăng sau khi tác vụ hoàn tất.

Với hệ thống scrape định kỳ, không phải mọi thay đổi đều xuất hiện ngay trên dashboard. Nếu một tác vụ bắt đầu và kết thúc giữa hai lần scrape, backend có thể không quan sát được trạng thái active của tác vụ đó. Đây là giới hạn lấy mẫu thời gian của hệ thống giám sát, không nhất thiết là lỗi instrumentation. Với tác vụ ngắn, Timer phù hợp hơn để lưu lại thời lượng hoàn tất.

Không truy cập endpoint quản trị metrics công khai mà không có kiểm soát. Endpoint có thể tiết lộ tên thành phần, cấu trúc hoạt động và thông tin vận hành; hãy giới hạn exposure và quyền truy cập theo cấu hình triển khai.

## 9. Kiểm thử lifecycle của LongTaskTimer

Kiểm thử nên xác nhận cả thời điểm bắt đầu, trạng thái đang chạy và thời điểm dừng. Với SimpleMeterRegistry, có thể kiểm tra **activeTasks()** trực tiếp:

~~~java
@Test
void activeTaskIsRemovedAfterSampleStops() {
    try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
        LongTaskTimer timer = LongTaskTimer.builder("batch.execution")
            .register(registry);

        LongTaskTimer.Sample sample = timer.start();

        assertEquals(1, timer.activeTasks());

        sample.stop();

        assertEquals(0, timer.activeTasks());
        assertEquals(0.0, timer.duration(TimeUnit.SECONDS), 0.0001);
        assertEquals(0.0, timer.max(TimeUnit.SECONDS), 0.0001);
    }
}
~~~

Bài kiểm thử xác nhận sample đang chạy được tính vào active task và bị loại khỏi tập active sau stop. Không nên khẳng định thời lượng của tác vụ đã hoàn tất vẫn được giữ trong LongTaskTimer; nếu cần xác minh lịch sử, hãy kiểm tra Timer riêng.

Cũng nên kiểm tra đường đi lỗi:

~~~java
@Test
void activeTaskIsRemovedWhenWorkFails() {
    try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
        LongTaskTimer timer = LongTaskTimer.builder("batch.execution")
            .register(registry);

        assertThrows(
            IllegalStateException.class,
            () -> runWithLongTaskTimer(timer, () -> {
                throw new IllegalStateException("processing failed");
            })
        );

        assertEquals(0, timer.activeTasks());
    }
}

private void runWithLongTaskTimer(
        LongTaskTimer timer,
        Runnable work) {

    LongTaskTimer.Sample sample = timer.start();
    try {
        work.run();
    } finally {
        sample.stop();
    }
}
~~~

Trong bài kiểm thử thực tế, có thể bổ sung các tình huống cancellation, interruption và nhiều sample đồng thời. Khi kiểm thử thời lượng tăng theo thời gian, tránh phụ thuộc vào sleep dài hoặc giá trị chính xác đến từng nanosecond; hãy kiểm tra quan hệ tăng hoặc dùng clock có thể kiểm soát nếu implementation và cấu hình cho phép.

## 10. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không gọi **sample.stop()** | Tác vụ đã xong vẫn bị tính là active, duration tiếp tục tăng | Dừng sample trong finally |
| Chỉ dừng sample ở nhánh thành công | Exception hoặc cancellation làm rò rỉ trạng thái active | Dùng một điểm cleanup chung |
| Gọi stop nhiều lần cho một sample | Có thể gây ghi nhận sai hoặc hành vi không mong muốn | Mỗi lần start có đúng một lần stop |
| Đọc duration như tổng lịch sử | Dashboard mất dữ liệu sau khi tác vụ kết thúc | Dùng Timer cho lịch sử thời lượng |
| Dùng LongTaskTimer cho mọi request ngắn | Tạo thêm sample và overhead không cần thiết | Dùng Timer cho thao tác ngắn, phổ biến |
| Dùng ID tác vụ làm tag | Cardinality tăng theo số lần chạy | Dùng nhóm tác vụ có tập giá trị hữu hạn |
| Giả định backend thấy mọi tác vụ | Tác vụ ngắn có thể kết thúc giữa hai lần scrape | Kết hợp Timer để ghi thời lượng hoàn tất |
| Cho rằng finally chạy khi JVM bị kill | Có thể giả định sai về cleanup | Thiết kế hệ thống không phụ thuộc metrics như kho trạng thái bền vững |

## 11. Checklist triển khai

- [ ] Dùng LongTaskTimer cho tác vụ có thời gian chạy đủ dài để cần quan sát khi đang hoạt động.
- [ ] Mỗi lần chạy gọi start và giữ Sample riêng.
- [ ] Đọc activeTasks, duration(TimeUnit) và max(TimeUnit) theo đúng ngữ nghĩa active.
- [ ] Gọi sample.stop() trong finally để xử lý thành công, exception, cancellation và interruption.
- [ ] Không dừng một sample nhiều lần.
- [ ] Dùng Timer bổ sung nếu cần lịch sử thời lượng sau khi tác vụ hoàn tất.
- [ ] Giữ tag có tập giá trị hữu hạn; không đưa ID từng lần chạy vào tag.
- [ ] Kiểm thử cả đường đi thành công lẫn lỗi và xác nhận active task trở về 0.
- [ ] Xem xét khoảng scrape khi giải thích vì sao tác vụ ngắn không xuất hiện trên dashboard.
- [ ] Không dùng LongTaskTimer làm kho lưu trạng thái hoặc lịch sử nghiệp vụ.

LongTaskTimer cho biết công việc nào vẫn đang diễn ra và chúng đã chạy bao lâu tại thời điểm đọc. Khi tác vụ kết thúc, dừng sample để số liệu active được cập nhật; nếu cần phân tích thời lượng đã hoàn tất, ghi thêm vào Timer. Đặt cleanup trong finally và kiểm thử cả thành công lẫn lỗi để dữ liệu công bố phản ánh đúng vòng đời thực tế của tác vụ.

