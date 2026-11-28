# Kiểm thử gọi song song, dữ liệu dùng chung và giới hạn thời gian đáp ứng của resolver

## Mục tiêu và phạm vi

Bài học thuộc chương **Kiểm chứng resolver** của mô-đun **JAVA_VERSION_JAVA18**. Java 18 giới thiệu cơ chế mở rộng phân giải địa chỉ Internet thông qua `java.net.spi.InetAddressResolverProvider` và `java.net.spi.InetAddressResolver`. Đây vẫn là những API có ý nghĩa khi kiểm chứng cách phân giải tên trên JDK hiện đại, cùng với `InetAddress`, reflection và các hợp đồng API khác được học trong mô-đun.

Một resolver hoạt động đúng khi gọi đơn lẻ chưa chắc đã hoạt động đúng khi nhiều luồng sử dụng chung dữ liệu. Đồng thời, một phép đo nhanh hoặc chậm của `InetAddress.getAllByName` chưa chứng minh được đã có bao nhiêu truy vấn DNS, tầng cache nào đã trả lời hay lời gọi bị chặn ở đâu.

Học xong bài này, bạn có thể:

- Kiểm thử nhiều lời gọi đồng thời với tín hiệu khởi chạy chung, đảm bảo bài kiểm thử thực sự có **các lời gọi chồng lấn**.
- Xác minh trạng thái dùng chung (bộ đếm, cache, bảng yêu cầu đang xử lý) không bị mất cập nhật hoặc lẫn dữ liệu giữa các yêu cầu.
- Kiểm tra cả nhánh trả về địa chỉ và nhánh `UnknownHostException` trong một đợt gọi song song.
- Đặt giới hạn thời gian **cho phía chờ kết quả**, hiểu chính xác ý nghĩa của timeout và hủy `Future`.
- Tách kiểm thử logic resolver khỏi kiểm thử tích hợp qua `InetAddress` và các tầng phân giải của hệ điều hành.
- Diễn giải số liệu theo phạm vi có bằng chứng, tránh phụ thuộc vào hành vi đã lỗi thời hoặc chi tiết triển khai không được API cam kết.

## 1. Ranh giới nào cần kiểm chứng?

Khi ứng dụng gọi:

```java
InetAddress[] addresses = InetAddress.getAllByName("service.example");
```

lời gọi có thể lấy dữ liệu từ cache, cấu hình tên cục bộ, bộ phân giải hệ điều hành hoặc resolver do provider cung cấp. Không có bảo đảm rằng **mỗi lần gọi API tạo một truy vấn DNS trên mạng**. Với địa chỉ IP dạng số, quá trình phân giải tên trên mạng thậm chí có thể không cần thiết.

SPI được bổ sung từ Java 18 cho phép đăng ký một `InetAddressResolverProvider` để cung cấp cách phân giải tên và địa chỉ. Giao diện `InetAddressResolver` có hai hướng trách nhiệm: tìm địa chỉ theo tên (`lookupByName`) và tìm tên theo địa chỉ (`lookupByAddress`). Đối với `lookupByName`, kết quả là luồng `Stream<InetAddress>` và lời gọi có tham số chính sách tra cứu (`LookupPolicy`). Kiểm thử trực tiếp một resolver tùy chỉnh cần xét cả quá trình **tiêu thụ stream**, chứ không chỉ việc tạo ra đối tượng stream.

Phân biệt ba lớp kiểm chứng:

| Lớp kiểm chứng | Câu hỏi phù hợp | Điều không tự chứng minh được |
| --- | --- | --- |
| Logic resolver với nguồn dữ liệu giả | Đáp án đúng không? Trạng thái dùng chung có an toàn dưới tải song song không? Có timeout ở phía gọi không? | Provider đã được JVM lựa chọn hoặc DNS đã được truy vấn |
| Tích hợp với `InetAddress` trên một JVM được cấu hình cho provider | Provider có được nạp không? API công khai trả về kết quả/ngoại lệ mong đợi không? | Mỗi lời gọi API đã đi tới resolver đúng một lần |
| Quan sát hệ thống mạng và DNS | Có gói tin/truy vấn thật không? Thời gian và mã phản hồi tại tầng mạng là gì? | Chỉ nhìn vào thời gian `getAllByName` là đủ để khẳng định nguồn kết quả |

Một bài kiểm thử đáng tin cậy thường bắt đầu từ lớp logic với dữ liệu quyết định được, sau đó mới chạy tích hợp ở tiến trình riêng. Làm như vậy giúp phân biệt lỗi đồng bộ hóa của resolver với tác động của cache và cấu hình máy.

## 2. Các tình huống bắt buộc khi nhiều lời gọi cùng chạy

Một bộ tình huống nhỏ nhưng hữu ích:

| Tình huống | Kỳ vọng có thể xác minh |
| --- | --- |
| Nhiều luồng cùng tra một tên có kết quả | Mỗi bên nhận kết quả đúng; trạng thái dùng chung không bị mất cập nhật |
| Nhiều luồng tra các tên khác nhau | Không lẫn địa chỉ của tên A sang tên B |
| Thành công và `UnknownHostException` cùng xuất hiện | Một yêu cầu lỗi không làm ô nhiễm kết quả yêu cầu khác |
| Một thao tác chờ làm chậm | Có thể nhận biết thời hạn chờ bị vượt; không đánh đồng timeout của bên gọi với kết thúc tác vụ |
| Dữ liệu dùng chung được cập nhật | Số lần thực thi do *test double* ghi lại khớp số lần đã gọi vào chính *test double* |
| Hủy một phép thử sau timeout | Có dọn tài nguyên; cơ chế chặn giả lập có thể giải phóng hoặc phản hồi khi bị ngắt |

**Lưu ý về bộ đếm:** Nếu đo trực tiếp số lần callback của provider trong một bài tích hợp `InetAddress.getAllByName`, không được kỳ vọng giá trị đó luôn bằng số lời gọi API. Cache, cách JVM điều phối phân giải và các cấu hình liên quan có thể làm hai số khác nhau. Chỉ khi kiểm thử **trực tiếp một đối tượng giả hoặc một resolver cụ thể**, với số lời gọi do chính bài kiểm thử kiểm soát, mới có cơ sở để yêu cầu bộ đếm khớp chính xác.

## 3. Mẫu kiểm thử song song bằng nguồn dữ liệu giả

Ví dụ này dùng Java chuẩn, tương thích JDK 18 và các bản JDK hiện đại. Nó kiểm tra một ranh giới `NameLookup` nhỏ, có thể thay bằng bộ điều hợp gọi tới resolver thực tế. Tập dữ liệu giả dùng dải `192.0.2.0/24` dành cho tài liệu, tạo địa chỉ qua `InetAddress.getByAddress(byte[])`; bài thử **không phát sinh tra cứu DNS**.

Lưu tệp `ConcurrentResolverCheck.java`:

```java
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentResolverCheck {
    @FunctionalInterface
    interface NameLookup {
        InetAddress[] resolve(String host) throws UnknownHostException;
    }

    record Observation(String host, String ip, boolean failed, long nanos) {}

    static final class FakeResolver implements NameLookup {
        private final ConcurrentMap<String, AtomicInteger> calls =
                new ConcurrentHashMap<>();
        private final CountDownLatch allEntered;

        FakeResolver(int expectedCalls) {
            allEntered = new CountDownLatch(expectedCalls);
        }

        @Override
        public InetAddress[] resolve(String host) throws UnknownHostException {
            // Giá trị AtomicInteger cũng cần an toàn khi cập nhật đồng thời.
            calls.computeIfAbsent(host, key -> new AtomicInteger())
                    .incrementAndGet();

            // Chỉ khi mọi luồng đã đi vào resolver mới cho phép trả kết quả.
            allEntered.countDown();
            try {
                if (!allEntered.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Not all concurrent calls reached resolver");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Test interrupted", e);
            }

            if (host.equals("absent.test")) {
                throw new UnknownHostException(host);
            }

            int lastOctet = switch (host) {
                case "node-1" -> 1;
                case "node-2" -> 2;
                case "node-3" -> 3;
                default -> throw new IllegalArgumentException(host);
            };

            return new InetAddress[] {
                    InetAddress.getByAddress(
                            new byte[] {(byte) 192, 0, 2, (byte) lastOctet})
            };
        }

        int countFor(String host) {
            AtomicInteger count = calls.get(host);
            return count == null ? 0 : count.get();
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        List<String> inputs = List.of(
                "node-1", "absent.test", "node-2", "node-3",
                "node-1", "absent.test", "node-2", "node-3");

        int parallelism = inputs.size();
        FakeResolver resolver = new FakeResolver(parallelism);
        ExecutorService pool = Executors.newFixedThreadPool(parallelism);
        CountDownLatch ready = new CountDownLatch(parallelism);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Observation>> futures = new ArrayList<>();

        try {
            for (String host : inputs) {
                Callable<Observation> task = () -> {
                    ready.countDown();
                    start.await();

                    long begin = System.nanoTime();
                    try {
                        InetAddress[] result = resolver.resolve(host);
                        return new Observation(
                                host, result[0].getHostAddress(), false,
                                System.nanoTime() - begin);
                    } catch (UnknownHostException e) {
                        return new Observation(
                                host, null, true, System.nanoTime() - begin);
                    }
                };
                futures.add(pool.submit(task));
            }

            require(ready.await(5, TimeUnit.SECONDS),
                    "Workers did not become ready");
            start.countDown();

            // Một deadline chung tránh cộng dồn timeout từng Future.
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
            for (int i = 0; i < inputs.size(); i++) {
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) {
                    throw new TimeoutException("Whole test exceeded deadline");
                }

                Observation seen = futures.get(i).get(
                        remaining, TimeUnit.NANOSECONDS);
                String expectedHost = inputs.get(i);

                require(seen.host().equals(expectedHost),
                        "Host/result mismatch");

                if (expectedHost.equals("absent.test")) {
                    require(seen.failed(), "Expected UnknownHostException");
                } else {
                    require(!seen.failed(), "Unexpected lookup failure");
                    String suffix = expectedHost.substring("node-".length());
                    require(seen.ip().equals("192.0.2." + suffix),
                            "Cross-request result corruption");
                }

                System.out.printf("%s -> %s (%.3f ms)%n",
                        seen.host(),
                        seen.failed() ? "UnknownHostException" : seen.ip(),
                        seen.nanos() / 1_000_000.0);
            }

            // Mỗi tên xuất hiện hai lần trong tập dữ liệu kiểm thử.
            for (String host : List.of(
                    "node-1", "node-2", "node-3", "absent.test")) {
                require(resolver.countFor(host) == 2,
                        "Lost shared-state update for " + host);
            }
            System.out.println("PASS: concurrent calls and shared state");
        } finally {
            // Tránh để luồng chờ start mãi nếu bước chuẩn bị thất bại.
            start.countDown();
            for (Future<Observation> future : futures) {
                future.cancel(true);
            }
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac ConcurrentResolverCheck.java
java ConcurrentResolverCheck
```

### Vì sao kiểm thử này có ý nghĩa?

- `ready` đợi đủ tám tác vụ sẵn sàng trước khi phát tín hiệu `start`. Vì pool cũng có tám worker, đây là một đợt gọi có kiểm soát, thay vì tám lời gọi được thực thi lần lượt.
- `allEntered` nằm **bên trong** resolver giả. Mỗi lời gọi chỉ tiếp tục khi tất cả lời gọi đã đi vào resolver, chứng minh các lời gọi thực sự chồng lấn tại ranh giới đang thử.
- `ConcurrentHashMap` bảo vệ bảng đếm; `AtomicInteger.incrementAndGet()` bảo vệ thao tác tăng của từng giá trị. Chỉ dùng `ConcurrentHashMap<String, Integer>` rồi tính `get + 1` và `put` vẫn có thể mất cập nhật.
- Mỗi kết quả được đối chiếu với hostname của chính tác vụ. Hai lời gọi cùng một tên, nhiều tên khác nhau và một tên thất bại cùng diễn ra trong một đợt.
- `Future.get(remaining, NANOSECONDS)` sử dụng **một mốc hạn chung**. Nếu từng `Future` được chờ tối đa mười giây riêng lẻ, bài kiểm thử có thể kéo dài nhiều lần mức thời gian dự kiến.
- Cơ chế đếm chỉ khẳng định **có đúng hai lần đi vào FakeResolver cho mỗi tên**. Nó không phải số truy vấn DNS hay số lần callback của resolver khi đi qua cache `InetAddress`.
- Giá trị mili giây đo trong ví dụ bao gồm cả thời gian chờ hàng rào `allEntered`. Vì vậy chỉ dùng để quan sát thử nghiệm, **không dùng làm benchmark** độ trễ phân giải của một hệ thống thật.

`CountDownLatch` chỉ được thiết kế dùng một lần. Khi cần lặp hàng trăm lượt kiểm tra, hãy tạo đối tượng giả và các latch mới cho mỗi lượt, đồng thời ghi lại seed và đầu vào để tái hiện lỗi. Với tải lớn hơn, đừng mở số luồng không giới hạn; chọn pool và mức song song phù hợp với môi trường thử nghiệm.

## 4. Kiểm tra giới hạn chờ mà không phụ thuộc DNS hoặc mạng

Một resolver bị chặn có thể làm luồng gọi chờ lâu. `InetAddress.getAllByName(String)` không có tham số timeout cho từng lời gọi. Trong ứng dụng, `Future.get(timeout, unit)` có thể **giới hạn thời gian bên gọi chờ kết quả**, nhưng không tự bảo đảm thao tác phân giải nền đã dừng.

Ví dụ sau chủ động chặn một resolver giả bằng latch. Bài thử xác nhận rằng phía chờ nhận `TimeoutException` dù tác vụ vẫn đang chờ bên trong resolver.

Lưu `ResolverDeadlineCheck.java`:

```java
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ResolverDeadlineCheck {
    @FunctionalInterface
    interface NameLookup {
        InetAddress[] resolve(String host) throws UnknownHostException;
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        NameLookup deliberatelyBlocked = host -> {
            entered.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                // Ngoại lệ thử nghiệm; đừng ngụy trang nó thành lỗi DNS.
                throw new IllegalStateException("Interrupted test resolver", e);
            }
            return new InetAddress[] {
                    InetAddress.getByAddress(
                            new byte[] {(byte) 192, 0, 2, 10})
            };
        };

        ExecutorService pool = Executors.newSingleThreadExecutor();
        Future<InetAddress[]> pending =
                pool.submit(() -> deliberatelyBlocked.resolve("blocked.test"));

        try {
            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Task never entered resolver");
            }

            try {
                pending.get(100, TimeUnit.MILLISECONDS);
                throw new AssertionError("Expected caller-side timeout");
            } catch (TimeoutException expected) {
                System.out.println("PASS: caller stopped waiting at deadline");
                System.out.println("Task was still blocked before cleanup: "
                        + !pending.isDone());
            }
        } finally {
            release.countDown();
            pending.cancel(true);
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac ResolverDeadlineCheck.java
java ResolverDeadlineCheck
```

Từ ví dụ này có thể rút ra ba kết luận được hỗ trợ:

1. `TimeoutException` là kết quả của **`Future.get` hết thời gian chờ**; nó không phải `UnknownHostException` của bộ phân giải.
2. Khi `get` trả về do timeout, tác vụ được gửi vào pool **có thể vẫn tiếp tục chạy**. Không kết luận rằng hệ điều hành, socket hoặc DNS đã bị ngắt.
3. `cancel(true)` là **yêu cầu ngắt**, không phải bảo đảm cắt ngang mọi lời gọi chặn. Resolver giả ở trên hỗ trợ ngắt để việc dọn dẹp có thể dự đoán được; một thao tác I/O hoặc resolver thật có thể cần chính sách timeout, cơ chế hủy và tài nguyên riêng.

Trong sản phẩm thực tế, giới hạn thời gian cần được thiết kế ở **từng tầng có khả năng chặn**, gồm hàng đợi tác vụ, bộ phân giải, I/O và thao tác kết nối tiếp theo. Một timeout ở phía UI hay API không tự động là timeout của truy vấn DNS. Tránh tạo một luồng mới cho mọi yêu cầu rồi bỏ mặc luồng sau khi hết thời gian chờ; sử dụng pool giới hạn và quan sát số tác vụ đang chờ.

## 5. Dữ liệu dùng chung: những lỗi dễ bị che khuất

Resolver tùy chỉnh có thể duy trì cache, bộ đếm, chỉ số hoặc bảng yêu cầu đang phân giải. Khi nhiều luồng cùng gọi vào một instance, tất cả dữ liệu thay đổi được đều cần thiết kế rõ tính nhất quán.

| Thiết kế | Nguy cơ hoặc lợi ích | Cách kiểm chứng |
| --- | --- | --- |
| `HashMap` hoặc `ArrayList` thay đổi trực tiếp từ nhiều luồng | Trạng thái bị race, thiếu phần tử, sai kết quả, hành vi không xác định | Chạy nhiều lời gọi trùng khóa/khác khóa; đối chiếu trạng thái cuối |
| `ConcurrentHashMap` với giá trị mutable không được bảo vệ | Bảng an toàn nhưng chính đối tượng chứa trong bảng vẫn có thể race | Dùng atomic/đồng bộ thích hợp cho từng thao tác |
| Đọc số đếm rồi cộng một và ghi lại | Hai luồng có thể ghi đè cập nhật của nhau | So sánh với `AtomicInteger.incrementAndGet` hoặc `compute` nguyên tử |
| Một bộ đệm kết quả dùng lại cho nhiều yêu cầu | Kết quả A có thể lẫn B nếu trả đối tượng mutable đang dùng chung | Kiểm tra tính độc lập của kết quả theo tên và ngữ cảnh |
| Giữ khóa toàn cục trong khi gọi I/O chậm | Các tên không liên quan có thể chờ nhau | Đo thông lượng, số lời gọi đồng thời, độ trễ đuôi |
| Cache thất bại không có chính sách hết hạn | Kết quả lỗi có thể sống lâu hơn mong muốn | Kiểm thử vòng đời cache với đồng hồ giả hoặc nguồn có thể kiểm soát |
| Kết quả được tạo bằng stream có tác dụng phụ | Lỗi có thể chỉ xuất hiện khi stream được tiêu thụ | Tiêu thụ đầy đủ stream trong phép thử, kiểm tra ngoại lệ tại lúc tiêu thụ |

`volatile` có thể cung cấp quy tắc hiển thị giá trị giữa các luồng, nhưng **không biến biểu thức `counter++` thành thao tác nguyên tử**. Tương tự, tính chất thread-safe của map không mặc nhiên bảo vệ toàn bộ chuỗi thao tác “kiểm tra, tải dữ liệu, ghi cache”.

Nếu resolver thực hiện gộp nhiều yêu cầu cùng khóa (*single-flight*), cần xác định hợp đồng cụ thể: cùng một hostname có được chờ một thao tác phân giải chung không, lỗi có được lan tới tất cả bên chờ không, và việc hủy một bên chờ ảnh hưởng thế nào đến các bên khác. **Không lấy “số lần gọi provider bằng số lần gọi `InetAddress`” làm điều kiện bắt buộc** nếu hệ thống có cache hoặc gộp yêu cầu.

## 6. Đo giới hạn thời gian đáp ứng có ý nghĩa

Có ít nhất bốn khoảng thời gian khác nhau:

```text
Người gọi gửi công việc
    |<-- chờ trong queue -->|
Worker bắt đầu thực thi
    |<-- thực thi resolver + cache/I/O có liên quan -->|
Worker trả kết quả hoặc ngoại lệ
    |<-- chuyển kết quả / xử lý ở caller -->|
Người gọi nhận kết quả
```

Khi đặt một thời hạn chung cho yêu cầu, nên đo toàn bộ thời gian từ lúc gửi đến khi bên gọi nhận kết quả. Khi cần phân tích nguyên nhân chậm, hãy ghi thêm thời gian xếp hàng, thời gian bên trong resolver và thời gian chờ tầng I/O nếu có thể thu thập độc lập.

Dùng `System.nanoTime()` để tính khoảng thời gian bằng phép trừ; không dùng giá trị đó như mốc thời gian lịch. Với các báo cáo log cần đối chiếu nhiều dịch vụ, ghi thêm thời gian lịch bằng `Instant.now()` ở ngoài đoạn đo nhạy cảm. Không đưa việc định dạng, in log hoặc tra tên ngược vào cùng khoảng đo nếu mục tiêu là đo riêng `lookupByName` hay `getAllByName`.

Một bảng kiểm thử độ trễ có thể gồm:

| Loại số liệu | Ý nghĩa | Không nên suy ra |
| --- | --- | --- |
| Tổng số yêu cầu, số thành công, số ngoại lệ | Phân bố kết quả tại API | Tỉ lệ lỗi của DNS server chỉ từ `UnknownHostException` |
| p50, p95, p99 của độ trễ | Độ trễ trung vị và đuôi trong tập quan sát | Cam kết cho mọi máy khi mẫu quá nhỏ |
| Số lượng yêu cầu đang chạy và thời gian chờ queue | Mức cạnh tranh tài nguyên | Mỗi luồng đang chờ chắc chắn có một truy vấn DNS |
| Số lần phía gọi hết hạn chờ | Tần suất vượt deadline ở ứng dụng | Resolver bên dưới đã bị hủy thành công |
| Bộ đếm callback provider | Số lần provider thực sự nhận lời gọi trong thí nghiệm | Số lượng gói DNS trên mạng |

Giới hạn thời gian như **100 ms**, **1 s** hoặc **5 s** chỉ là tham số minh họa trong bài tập. Hãy chọn deadline dựa trên nhu cầu của ứng dụng, đặc điểm mạng và môi trường chạy; tách giới hạn phục vụ người dùng khỏi ngưỡng đánh giá độ ổn định của bài kiểm thử trên CI. Một phép đo đơn lẻ có thể chịu ảnh hưởng của JIT, bộ lập lịch, khởi tạo lớp, cache và tải CPU.

## 7. Khi chuyển từ fake resolver sang `InetAddressResolverProvider` thực tế

Để bài kiểm thử đi tới SPI chứ không dừng ở lớp giả, cần thêm bước tích hợp có kiểm soát:

1. **Cô lập tiến trình JVM cho từng kịch bản.** Provider của `InetAddress` được lựa chọn theo cơ chế cấu hình/dịch vụ của JVM; không nên thử hoán đổi provider liên tục bên trong một tiến trình rồi giả định việc chuyển đổi sẽ có hiệu lực. Cache phân giải cũng có thể ảnh hưởng các lần gọi về sau.
2. **Dùng dữ liệu và chính sách rõ ràng.** Với resolver cụ thể, kiểm tra đúng kết quả, `UnknownHostException`, chính sách tra cứu tên và tra cứu ngược nếu có. Nếu gọi trực tiếp `InetAddressResolver.lookupByName`, phải tiêu thụ toàn bộ `Stream<InetAddress>` để kiểm tra phần thực thi có thể bị hoãn.
3. **Tách kiểm thử đồng thời tại lớp resolver khỏi kiểm thử tích hợp.** Bài kiểm thử `NameLookup` ở trên xác minh cơ chế song song của test double; khi thay bằng bộ điều hợp thật, kiểm tra trạng thái chia sẻ ngay trong resolver. Bài tích hợp qua `InetAddress.getAllByName` kiểm tra cách chương trình nhận kết quả, nhưng có thể không kích hoạt callback mỗi lần vì cache.
4. **Xác nhận provider đã được lựa chọn.** Dùng log hoặc điểm đo có kiểm soát ngay trong provider; bảo đảm không lẫn với số lần gọi `InetAddress`. Với tên có thể phân giải bằng cơ chế cục bộ, càng cần bằng chứng trực tiếp về việc callback nào được gọi.
5. **Quan sát DNS bằng nguồn độc lập nếu đó là câu hỏi.** Chỉ khi có bản ghi ở máy chủ DNS do nhóm kiểm thử kiểm soát hoặc phép đo lưu lượng mạng tương ứng mới có căn cứ về truy vấn trên mạng.
6. **Dọn dẹp hoàn chỉnh.** Giải phóng latch, trả tài nguyên, đóng executor, hạn chế task bị bỏ quên sau timeout và chạy lại mỗi kịch bản trong bối cảnh có thể tái lập.

Đặc biệt, một provider tùy chỉnh cần thiết kế cách sử dụng bộ phân giải nền rõ ràng. Gọi lại `InetAddress.getAllByName` một cách vô điều kiện từ chính đường xử lý phân giải của provider có thể gây vòng lặp tái nhập hoặc lệ thuộc vào hành vi triển khai. Việc ủy quyền, nếu có, phải thông qua cơ chế được SPI cung cấp và được kiểm thử riêng.

### Câu hỏi tự kiểm tra

**Tình huống A.** Tám tác vụ cùng gọi `getAllByName("example.test")` nhưng bộ đếm của provider chỉ tăng một lần. Có kết luận được bảy lời gọi còn lại đã lỗi không?

Không. Nếu tất cả lời gọi trả kết quả đúng, bộ đếm provider khác số lần gọi API có thể liên quan tới cache, hợp nhất yêu cầu hoặc đường đi được JVM chọn. Muốn xác định nguyên nhân, cần thêm dữ liệu tại các tầng tương ứng.

**Tình huống B.** `Future.get(100, MILLISECONDS)` ném `TimeoutException`. Có thể khẳng định việc phân giải đã bị dừng sau 100 ms không?

Không. Chỉ khẳng định luồng đang chờ đã hết thời gian chờ. Cần kiểm tra tình trạng tác vụ bên dưới và khả năng hỗ trợ hủy thực sự.

**Tình huống C.** Sau 1.000 lần gọi song song, map lưu kết quả có đủ khóa, nhưng tổng bộ đếm ít hơn 1.000. Có thể kết luận `ConcurrentHashMap` hỏng không?

Chưa thể. Cần xem cách cập nhật **giá trị bên trong** map. Nếu tăng số nguyên bằng chuỗi `get + 1 + put`, cập nhật có thể bị mất dù map là concurrent; nếu dữ liệu đi qua `InetAddress`, cũng phải kiểm tra liệu 1.000 lời gọi có thực sự tới callback hay không.

**Tình huống D.** Một tên thất bại trả `UnknownHostException` rất nhanh trong các lần gọi sau. Có thể kết luận DNS server lập tức trả NXDOMAIN không?

Không. Kết quả thất bại có thể xuất phát từ cache hoặc resolver cục bộ, cấu hình khác nhau hay một lỗi phân giải không tương đương NXDOMAIN.

## 8. Những nguyên tắc cần giữ

- Kiểm thử song song phải **chứng minh có sự chồng lấn**, ví dụ bằng hai latch `ready/start` và một điểm đợi nằm bên trong resolver, chứ không chỉ nộp nhiều task vào executor.
- Kiểm tra toàn bộ hợp đồng đầu ra theo từng yêu cầu: địa chỉ, ngoại lệ, chính sách tra cứu và trạng thái dùng chung. Không cho phép lỗi ở yêu cầu A làm sai kết quả yêu cầu B.
- Sử dụng cấu trúc dữ liệu đồng thời và thao tác cập nhật nguyên tử phù hợp. Đặc tính thread-safe của container không tự bảo vệ dữ liệu mutable bên trong.
- Phân biệt thời hạn chờ của người gọi với timeout thực sự của bộ phân giải hoặc I/O. `Future.cancel(true)` cũng không bảo đảm mọi thao tác nền đều bị cắt ngang.
- Tách phép thử có dữ liệu giả ổn định khỏi phép thử tích hợp với hệ điều hành, cache và DNS. Chỉ kết luận về hành vi quan sát được, trên đúng JDK và cấu hình đã kiểm chứng.

Nhờ giới hạn ranh giới kiểm thử rõ ràng, chúng ta có thể xác minh cách resolver hoạt động dưới tải song song và có deadline trên JDK hiện đại mà không dựa vào giả định rằng mỗi lời gọi Java luôn tương ứng một truy vấn DNS mới.
