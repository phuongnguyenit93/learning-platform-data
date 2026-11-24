# Ghi Duration hoặc lượng thời gian kèm TimeUnit

Micrometer Timer ghi nhận thời lượng của một hoạt động cùng số lần hoạt động được đo. Khi đã có một đối tượng **Duration**, có thể truyền trực tiếp Duration cho Timer. Khi thời lượng được biểu diễn bằng một con số, cần truyền thêm **TimeUnit** để chỉ rõ đơn vị của con số đó. Hai cách ghi này đều đưa thời lượng vào cùng một Timer và để registry chuyển đổi sang đơn vị cơ sở phù hợp khi xuất metrics.

Chọn đúng API giúp tránh lỗi phổ biến như ghi 250 microsecond thành 250 millisecond, làm mất độ chính xác khi chuyển Duration sang số nguyên hoặc đo thời gian bằng đồng hồ lịch có thể bị điều chỉnh. Bài này tập trung vào cách ghi thời lượng đã có, cách đo một đoạn mã trực tiếp và cách chọn cách ghi phù hợp với ranh giới nghiệp vụ.

## 1. Timer lưu những thông tin nào?

Timer là meter dành cho những hoạt động có thời lượng. Mỗi lần ghi nhận thường đóng góp vào ít nhất hai thông tin:

- **count**: số lần hoạt động được ghi nhận.
- **total time**: tổng thời lượng của các lần đã ghi.

Tùy registry và cấu hình, Timer còn có thể cung cấp giá trị lớn nhất, phân phối thời lượng, histogram và percentile. Những dữ liệu này giúp trả lời các câu hỏi như một thao tác được thực hiện bao nhiêu lần, tổng thời gian tiêu tốn là bao nhiêu, và phần lớn hoặc một nhóm nhỏ thao tác mất bao lâu.

Ví dụ, một Timer cho thao tác thanh toán có thể ghi nhận mỗi lần gọi dịch vụ thanh toán. Nếu có 100 lần gọi và tổng thời lượng là 12 giây, count là 100 và total time là 12 giây. Trung bình có thể suy ra bằng tổng thời lượng chia cho count, nhưng trung bình không cho biết các trường hợp chậm bất thường; muốn phân tích đuôi phân phối cần cấu hình và đọc histogram hoặc percentile phù hợp.

Timer thường phù hợp với một thao tác có thời điểm bắt đầu và kết thúc rõ ràng: truy vấn cơ sở dữ liệu, gọi HTTP, xử lý message, tạo đơn hàng hoặc chạy một batch.

## 2. Ghi trực tiếp bằng Duration

**java.time.Duration** biểu diễn một khoảng thời gian. Nó mang theo ý nghĩa thời lượng mà không cần truyền một tham số đơn vị riêng. Khi mã ứng dụng đã có Duration, dùng overload **Timer.record(Duration)** là cách ghi rõ ràng:

~~~java
Timer paymentTimer = Timer.builder("payment.request.duration")
    .description("Thời lượng gọi dịch vụ thanh toán")
    .register(meterRegistry);

Duration elapsed = Duration.ofMillis(250);

paymentTimer.record(elapsed);
~~~

Ở đây, Timer ghi nhận một lần đo có thời lượng 250 millisecond. Đối tượng Duration tự mô tả đơn vị thời gian, vì vậy người đọc không phải suy luận một con số rời rạc đang là nanosecond, millisecond hay second.

Duration có thể được tạo từ nhiều đơn vị:

~~~java
Duration.ofNanos(750_000);
Duration.ofMillis(250);
Duration.ofSeconds(2);
Duration.ofMinutes(1);
Duration.ofHours(3);
~~~

Các factory method giúp mã thể hiện ý định. Khi nhận thời lượng từ một API khác dưới dạng Duration, có thể chuyển thẳng cho Timer mà không cần đổi sang số nguyên trung gian.

Nếu Duration có thể âm do dữ liệu đầu vào hoặc do phép tính sai, hãy kiểm tra trước khi ghi. Thời lượng đo của một hoạt động đã hoàn tất cần không âm; Duration âm thường là dấu hiệu sai lệch trong cách xác định mốc thời gian hoặc dữ liệu đầu vào.

## 3. Ghi lượng thời gian bằng số và TimeUnit

Một số API cũ hoặc thư viện bên ngoài trả thời lượng dưới dạng số. Khi đó dùng overload **Timer.record(long amount, TimeUnit unit)**:

~~~java
Timer remoteCallTimer = registry.timer("remote.call.duration");

long elapsedMicros = 250_000L;

remoteCallTimer.record(elapsedMicros, TimeUnit.MICROSECONDS);
~~~

Giá trị 250.000 trong ví dụ được hiểu là 250.000 microsecond, tương đương 250 millisecond. Đối số TimeUnit là một phần bắt buộc của ý nghĩa dữ liệu. Nếu truyền cùng con số nhưng chọn MILLISECONDS, thời lượng được ghi sẽ lớn hơn 1.000 lần.

Các đơn vị thường gặp trong Java gồm:

| TimeUnit | Quan hệ quy đổi |
|---|---:|
| **NANOSECONDS** | 1 giây = 1.000.000.000 nanosecond |
| **MICROSECONDS** | 1 giây = 1.000.000 microsecond |
| **MILLISECONDS** | 1 giây = 1.000 millisecond |
| **SECONDS** | Đơn vị giây |
| **MINUTES** | 1 phút = 60 giây |
| **HOURS** | 1 giờ = 3.600 giây |
| **DAYS** | 1 ngày = 86.400 giây |

Tên biến nên nói rõ đơn vị khi giữ một lượng thời gian dạng số, ví dụ **elapsedNanos**, **elapsedMillis** hoặc **timeoutSeconds**. Tránh tên chung chung như **time** hoặc **durationValue**, vì người đọc có thể truyền nhầm TimeUnit.

## 4. So sánh Duration và long kèm TimeUnit

Hai overload đều hợp lệ, nhưng phù hợp với những dạng dữ liệu đầu vào khác nhau.

| Tiêu chí | **record(Duration)** | **record(long, TimeUnit)** |
|---|---|---|
| Dữ liệu đầu vào | Đối tượng Duration | Số nguyên và đơn vị riêng |
| Ý nghĩa đơn vị | Được mang trong Duration | Được xác định bởi TimeUnit |
| Khả năng đọc mã | Rõ ràng khi hệ thống dùng java.time | Rõ ràng khi API nguồn trả số cùng đơn vị |
| Chuyển đổi trung gian | Thường không cần | Không cần nếu đã có đúng amount và unit |
| Rủi ro thường gặp | Duration âm hoặc tạo sai khoảng thời gian | Gắn nhầm TimeUnit, đặt tên biến không rõ đơn vị |
| Trường hợp phù hợp | Logic ứng dụng dùng java.time | API thư viện, callback hoặc dữ liệu đo dạng số |

Ví dụ, nếu mã nguồn đã có **Duration elapsed**, hãy ghi trực tiếp:

~~~java
timer.record(elapsed);
~~~

Nếu thư viện trả về số nanosecond:

~~~java
long elapsed = client.lastOperationTimeNanos();
timer.record(elapsed, TimeUnit.NANOSECONDS);
~~~

Không nên chuyển Duration sang millisecond chỉ để gọi overload số nếu không có lý do. Việc lấy **toMillis()** trả về số nguyên millisecond và có thể làm mất phần nhỏ hơn millisecond. Khi cần giữ độ phân giải cao hơn, truyền Duration trực tiếp hoặc giữ giá trị số cùng TimeUnit chính xác.

## 5. Tránh nhầm lẫn khi chuyển đổi đơn vị

Lỗi đơn vị thường không làm chương trình biên dịch thất bại. Timer vẫn nhận một giá trị hợp lệ về kiểu dữ liệu, nhưng số đo có thể sai nhiều bậc độ lớn.

Ví dụ sai:

~~~java
long elapsedMicros = 250_000L;

// Sai: con số là microsecond nhưng lại khai báo millisecond.
timer.record(elapsedMicros, TimeUnit.MILLISECONDS);
~~~

Ví dụ đúng:

~~~java
long elapsedMicros = 250_000L;
timer.record(elapsedMicros, TimeUnit.MICROSECONDS);
~~~

Nếu buộc phải chuyển Duration thành số, hãy dùng đúng đơn vị ở cả phép chuyển và lúc ghi:

~~~java
Duration elapsed = Duration.ofNanos(875_000);

long elapsedNanos = elapsed.toNanos();
timer.record(elapsedNanos, TimeUnit.NANOSECONDS);
~~~

Tuy nhiên, nếu không cần một API nhận số, **timer.record(elapsed)** ngắn gọn và tránh được bước chuyển đổi. Một lỗi khác là lấy **toMillis()** rồi truyền NANOSECONDS; con số millisecond sẽ bị hiểu là nanosecond và thời lượng trở nên nhỏ hơn một triệu lần.

## 6. Đo một đoạn mã bằng Timer.record

Nếu mục tiêu là đo thời gian thực thi một đoạn mã đồng bộ, không cần tự tạo Duration. Timer có thể đo trực tiếp đoạn mã và tự ghi nhận thời lượng khi đoạn mã kết thúc:

~~~java
Timer createOrderTimer = registry.timer("orders.create.duration");

createOrderTimer.record(() -> {
    orderService.create(command);
});
~~~

Cách này có lợi vì Timer quản lý việc lấy thời điểm bắt đầu, kết thúc và ghi nhận thời lượng. Nếu đoạn mã ném exception, thao tác đo vẫn được kết thúc khi lời gọi thoát khỏi hàm record; exception tiếp tục được truyền cho caller theo hợp đồng của phương thức.

Nếu đoạn mã trả về kết quả, có thể dùng overload nhận Supplier:

~~~java
Order order = createOrderTimer.record(
    () -> orderService.create(command)
);
~~~

Giá trị trả về được giữ nguyên để caller tiếp tục sử dụng. Đây là cách phù hợp khi muốn đo toàn bộ lời gọi đồng bộ mà không cần quan tâm đến giá trị thời lượng.

Chỉ nên bọc phần công việc cần đo. Nếu đặt các bước chuẩn bị không liên quan bên trong đoạn record, thời lượng sẽ bao gồm cả các bước đó. Tên Timer và ranh giới đo cần thống nhất để so sánh các lần thực thi có cùng ý nghĩa.

## 7. Dùng Timer.Sample khi cần chọn Timer sau khi hoàn tất

Có trường hợp chỉ biết kết quả hoặc tag cần gắn sau khi thao tác kết thúc. Ví dụ, cần ghi thời lượng theo **success**, **failure** hoặc **rejected**. **Timer.Sample** cho phép lấy mốc bắt đầu trước, rồi chọn Timer đích khi dừng sample:

~~~java
Timer.Sample sample = Timer.start(registry);
String result = "failure";

try {
    orderService.create(command);
    result = "success";
} catch (OrderRejectedException exception) {
    result = "rejected";
    throw exception;
} finally {
    sample.stop(
        registry.timer(
            "orders.create.duration",
            "result", result
        )
    );
}
~~~

Sample ghi nhớ mốc bắt đầu theo clock của registry. Khi gọi **stop(timer)**, nó tính thời gian đã trôi qua và ghi vào Timer được truyền vào. Nhờ đó, ứng dụng có thể quyết định tag dựa trên kết quả cuối cùng mà vẫn đo toàn bộ khoảng thời gian.

Các nhánh cần được thiết kế sao cho mỗi sample được dừng đúng một lần. Không gọi stop ở nhiều nhánh rồi tiếp tục gọi trong finally, vì như vậy có thể ghi nhận trùng. Đặt thao tác dừng tại một điểm kết thúc chung thường dễ kiểm soát hơn.

**Timer.Sample** cũng hữu ích khi Timer đích phụ thuộc vào trạng thái cuối, loại kết quả hoặc một chiều phân loại chỉ xác định được sau khi xử lý xong. Các tag vẫn phải có tập giá trị hữu hạn và tập khóa ổn định.

## 8. Đo thời gian thủ công bằng System.nanoTime

Khi cần tích hợp với API đo thời gian dạng số hoặc cần đặt ranh giới đo theo cách riêng, có thể dùng đồng hồ monotonic của JVM:

~~~java
long startedAt = System.nanoTime();

try {
    dependencyClient.call();
} finally {
    long elapsedNanos = System.nanoTime() - startedAt;
    dependencyTimer.record(elapsedNanos, TimeUnit.NANOSECONDS);
}
~~~

**System.nanoTime()** phù hợp để đo khoảng thời gian trôi qua. Không dùng **System.currentTimeMillis()** để đo elapsed time vì đồng hồ lịch có thể được điều chỉnh bởi đồng bộ thời gian hoặc thay đổi thời gian hệ thống. Đồng hồ monotonic được thiết kế cho phép so sánh khoảng thời gian trong cùng tiến trình.

Phép trừ hai giá trị nanoTime là cách dùng được khuyến nghị cho đo elapsed time; không cần chuyển giá trị tuyệt đối của nanoTime thành một timestamp. Giá trị trả về không có ý nghĩa là thời điểm lịch, chỉ có ý nghĩa khi so sánh hiệu giữa hai lần đọc.

Nếu không có yêu cầu đặc biệt, **Timer.record(Runnable)**, **Timer.record(Supplier)** hoặc **Timer.Sample** thường ít mã hơn và giảm nguy cơ quên ghi nhận khi exception xảy ra.

## 9. Đơn vị nội bộ và đơn vị xuất ra backend

Mã ứng dụng có thể ghi Duration hoặc số kèm TimeUnit, còn đơn vị xuất dữ liệu phụ thuộc registry. Micrometer chọn base time unit phù hợp với backend và chuyển đổi giá trị khi xuất.

Ví dụ, một registry có thể xuất thời lượng theo giây trong khi backend khác biểu diễn theo millisecond. Điều này không làm thay đổi thời lượng thực tế đã ghi; nó chỉ thay đổi đơn vị biểu diễn. Vì vậy, khi kiểm tra metrics ở backend, hãy đọc metadata hoặc quy ước của registry thay vì giả định mọi hệ thống đều xuất cùng đơn vị.

Trong mã Java, các phép đọc như **timer.totalTime(TimeUnit.SECONDS)** cho phép lấy tổng thời lượng theo đơn vị mong muốn:

~~~java
double totalSeconds = timer.totalTime(TimeUnit.SECONDS);
double maxMillis = timer.max(TimeUnit.MILLISECONDS);
long measurements = timer.count();
~~~

Ở đây, **totalSeconds** và **maxMillis** chỉ là cách đọc cùng dữ liệu Timer theo hai đơn vị khác nhau. Không cộng trực tiếp hai giá trị nếu chưa quy đổi về cùng đơn vị. Khi hiển thị trong dashboard, hãy kiểm tra đơn vị của metric và nhãn trục để tránh diễn giải millisecond thành second hoặc ngược lại.

## 10. Kiểm thử việc ghi Duration và TimeUnit

Có thể dùng SimpleMeterRegistry để kiểm tra count và total time. Ví dụ dưới đây ghi một Duration 250 millisecond và một giá trị 250 millisecond qua TimeUnit:

~~~java
@Test
void recordsDurationAndExplicitTimeUnit() {
    try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
        Timer timer = registry.timer("sample.operation.duration");

        timer.record(Duration.ofMillis(250));
        timer.record(250, TimeUnit.MILLISECONDS);

        assertEquals(2, timer.count());
        assertEquals(
            0.5,
            timer.totalTime(TimeUnit.SECONDS),
            0.0001
        );
    }
}
~~~

Bài kiểm thử xác nhận cả hai cách ghi đều tạo một lần đo và tổng thời lượng là nửa giây. Trong kiểm thử thực tế, có thể thêm các trường hợp microsecond, nanosecond và duration lớn hơn để phát hiện lỗi chuyển đổi đơn vị.

Nên kiểm tra thêm:

- **count()** tăng đúng một lần cho mỗi lần record.
- **totalTime** tương đương khi cùng thời lượng được ghi bằng Duration hoặc amount và TimeUnit.
- Đoạn mã ném exception vẫn được ghi nhận khi dùng **Timer.record(Runnable)** hoặc **Timer.Sample** trong finally.
- Không ghi Duration âm hoặc giá trị đầu vào sai đơn vị.
- Tag của Timer được giữ ổn định giữa các nhánh kết quả.
- Đơn vị hiển thị trong backend phù hợp với cấu hình registry.

Kiểm thử bằng SimpleMeterRegistry xác nhận hành vi Timer trong bộ nhớ. Nếu cần xác minh đơn vị xuất thực tế, cần kiểm thử tích hợp với registry/backend đang sử dụng.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Ghi microsecond nhưng truyền **MILLISECONDS** | Thời lượng bị phóng đại 1.000 lần | Dùng đúng TimeUnit của giá trị nguồn |
| Chuyển Duration sang millisecond rồi truyền **NANOSECONDS** | Thời lượng bị thu nhỏ rất nhiều | Giữ Duration hoặc chuyển và ghi cùng đơn vị |
| Dùng **currentTimeMillis()** để đo elapsed time | Bị ảnh hưởng bởi điều chỉnh đồng hồ lịch | Dùng **System.nanoTime()** hoặc Timer.Sample |
| Quên ghi nhận khi có exception | Thiếu các lần xử lý lỗi trong phân phối thời lượng | Dùng **Timer.record** hoặc finally |
| Dừng một Timer.Sample nhiều lần | Một thao tác có thể bị ghi nhận lặp | Chỉ dừng sample một lần |
| So sánh số đo có đơn vị khác nhau | Dashboard hoặc log hiển thị sai | Quy đổi về cùng đơn vị trước khi so sánh |
| Đo cả phần chuẩn bị không liên quan | Thời lượng không phản ánh đúng thao tác cần theo dõi | Chọn ranh giới đo rõ ràng |

## 12. Checklist chọn cách ghi thời lượng

- [ ] Đã có **Duration**: dùng **Timer.record(Duration)**.
- [ ] Có số nguyên cùng đơn vị nguồn: dùng **Timer.record(long, TimeUnit)**.
- [ ] Muốn đo đoạn mã đồng bộ: dùng **Timer.record(Runnable)** hoặc **Timer.record(Supplier)**.
- [ ] Cần chọn tag hoặc Timer sau khi xử lý: dùng **Timer.Sample**.
- [ ] Cần đo thủ công: dùng **System.nanoTime()** và ghi đúng **TimeUnit**.
- [ ] Không chuyển đổi sang đơn vị ít chính xác hơn nếu không cần thiết.
- [ ] Kiểm tra giá trị âm và đơn vị đầu vào.
- [ ] Đảm bảo exception không làm mất lần đo.
- [ ] Đọc số liệu theo base unit mà registry xuất ra.
- [ ] Kiểm thử count và total time bằng SimpleMeterRegistry.

Duration phù hợp khi ứng dụng đã làm việc với kiểu thời gian của Java; số kèm TimeUnit phù hợp khi dữ liệu đo đến từ API trả về một lượng và đơn vị cụ thể. Với thao tác đồng bộ, Timer có thể tự đo trực tiếp; với kết quả hoặc tag chỉ xác định sau khi xử lý, Timer.Sample giúp chọn Timer đích ở thời điểm kết thúc. Dù chọn cách nào, hãy giữ đúng đơn vị và ranh giới đo để số liệu thời lượng có thể so sánh và diễn giải chính xác.

