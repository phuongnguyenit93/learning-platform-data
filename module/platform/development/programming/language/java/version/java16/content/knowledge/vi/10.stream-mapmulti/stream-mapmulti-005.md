# mapMulti khi số phần tử phát ra nhỏ và logic sinh dữ liệu dạng mệnh lệnh

`Stream.mapMulti` phù hợp khi mỗi phần tử nguồn chỉ cần phát ra một số lượng nhỏ kết quả, có thể là không, một hoặc vài phần tử, và việc tạo kết quả được diễn đạt tự nhiên bằng vòng lặp hoặc các nhánh điều kiện. Thay vì tạo một Stream con cho từng phần tử như `flatMap`, mapper nhận một Consumer rồi gọi `accept` để gửi từng giá trị xuống pipeline.

Đây là định hướng sử dụng được mô tả trong API Stream từ Java 16 và vẫn áp dụng trong Java hiện đại. "Số lượng nhỏ" không phải một ngưỡng cố định; điều quan trọng là số kết quả trên mỗi phần tử có giới hạn hợp lý và không tăng thành một luồng dữ liệu rất lớn hoặc không giới hạn.

## 1. Hai tình huống mapMulti phát huy tác dụng

Javadoc của `mapMulti` nêu hai tình huống phù hợp:

- Mỗi phần tử nguồn được thay bằng một số lượng nhỏ phần tử kết quả, có thể bằng không. Cách này tránh phải tạo một đối tượng Stream con cho từng phần tử như cách thường viết với `flatMap`.
- Logic tạo kết quả dễ diễn đạt bằng cách mệnh lệnh, chẳng hạn vòng lặp và nhiều nhánh điều kiện, hơn là xây dựng một hàm trả về Stream.

Ví dụ, một bản ghi cảm biến có thể tạo ra tối đa hai cảnh báo: cảnh báo nhiệt độ cao và cảnh báo áp suất cao. Nếu cả hai chỉ số bình thường, bản ghi không tạo cảnh báo nào. Nếu một chỉ số vượt ngưỡng, nó tạo một cảnh báo; nếu cả hai vượt ngưỡng, nó tạo hai cảnh báo.

Mô hình này vừa có số lượng kết quả nhỏ, vừa có logic phát kết quả theo điều kiện. Đây là một trường hợp tự nhiên cho `mapMulti`.

## 2. Hiểu "số lượng nhỏ" theo nghiệp vụ

Không có con số chung như hai, năm hay mười phần tử để quyết định có nên dùng `mapMulti`. Hãy xem xét giới hạn của dữ liệu và quy tắc nghiệp vụ:

- Mỗi phần tử thường tạo ra không hoặc vài kết quả.
- Số kết quả có giới hạn rõ ràng theo cấu trúc đầu vào hoặc quy tắc xử lý.
- Mapper có thể phát từng giá trị trực tiếp mà không cần xây dựng một pipeline con phức tạp.
- Người đọc có thể hiểu số lần phát kết quả bằng cách quan sát một vòng lặp ngắn hoặc vài nhánh điều kiện.

Ví dụ một sản phẩm có tối đa hai tên hiển thị thay thế là trường hợp có giới hạn rõ. Một phần tử đại diện cho một trang dữ liệu có thể chứa hàng trăm nghìn bản ghi con thì không còn là trường hợp "số lượng nhỏ" theo ý định thiết kế này.

Số lượng thực tế còn phụ thuộc ứng dụng. Một vài phần tử có thể là nhỏ với một pipeline xử lý metadata, nhưng đã quá lớn với một thao tác được gọi hàng triệu lần. Hãy xem xét cả số kết quả trên mỗi phần tử và tổng khối lượng dữ liệu.

## 3. Ví dụ: phát không, một hoặc hai cảnh báo

Mỗi phép đo có nhiệt độ và áp suất. Ta phát cảnh báo tương ứng với chỉ số vượt ngưỡng:

```java
import java.util.List;

record Measurement(
    String sensorId,
    double temperature,
    double pressure
) {}

List<Measurement> measurements = List.of(
    new Measurement("S-01", 24.5, 1.0),
    new Measurement("S-02", 82.0, 1.1),
    new Measurement("S-03", 35.0, 2.4),
    new Measurement("S-04", 95.0, 2.8)
);

List<String> alerts = measurements.stream()
    .<String>mapMulti((measurement, emit) -> {
        if (measurement.temperature() > 80.0) {
            emit.accept(
                measurement.sensorId() + ": high temperature"
            );
        }

        if (measurement.pressure() > 2.0) {
            emit.accept(
                measurement.sensorId() + ": high pressure"
            );
        }
    })
    .toList();
```

Kết quả:

```text
[
  S-02: high temperature,
  S-03: high pressure,
  S-04: high temperature,
  S-04: high pressure
]
```

Mỗi phép đo phát tối đa hai cảnh báo. Cả hai điều kiện được kiểm tra độc lập, vì vậy một phép đo có thể phát hai kết quả. Phép đo bình thường không gọi `emit.accept` và không đóng góp phần tử đầu ra.

Đây là logic mệnh lệnh ngắn: đọc một bản ghi, kiểm tra các điều kiện rồi phát giá trị khi cần. Việc tạo một Stream con cho mỗi phép đo không đem lại lợi ích rõ ràng.

## 4. Ví dụ: duyệt một số ít giá trị con

Một bản ghi cấu hình có thể chứa một số ít alias cần công bố. Ta muốn phát các alias hợp lệ:

```java
import java.util.List;

record ServiceConfig(String serviceName, List<String> aliases) {}

List<ServiceConfig> configs = List.of(
    new ServiceConfig("billing", List.of("payment", "invoice")),
    new ServiceConfig("search", List.of("lookup")),
    new ServiceConfig("catalog", List.of())
);

List<String> publicNames = configs.stream()
    .<String>mapMulti((config, emit) -> {
        emit.accept(config.serviceName());

        for (String alias : config.aliases()) {
            if (alias != null && !alias.isBlank()) {
                emit.accept(alias.trim());
            }
        }
    })
    .toList();
```

Kết quả:

```text
[billing, payment, invoice, search, lookup, catalog]
```

Mỗi cấu hình phát tên dịch vụ và một số ít alias. Vòng lặp diễn đạt trực tiếp quy tắc phát dữ liệu; không cần chuyển danh sách alias thành Stream chỉ để làm phẳng nó.

Trong ví dụ này, số alias cần nhỏ và được giới hạn bởi quy tắc cấu hình. Nếu danh sách alias có thể rất lớn hoặc được nạp từ một nguồn dữ liệu không giới hạn, hãy xem xét cách xử lý phù hợp hơn với khối lượng dữ liệu đó.

## 5. Ví dụ: logic phát dữ liệu theo nhiều nhánh

Một phần tử có thể tạo ra các thông báo khác nhau tùy trạng thái. Có thể phát tối đa một hoặc hai thông báo cho mỗi tác vụ:

```java
import java.util.List;

record JobResult(
    String jobId,
    boolean succeeded,
    boolean retried
) {}

List<JobResult> jobResults = List.of(
    new JobResult("J-01", true, false),
    new JobResult("J-02", true, true),
    new JobResult("J-03", false, true),
    new JobResult("J-04", false, false)
);

List<String> summaries = jobResults.stream()
    .<String>mapMulti((job, emit) -> {
        if (job.succeeded()) {
            emit.accept(job.jobId() + ": completed");

            if (job.retried()) {
                emit.accept(job.jobId() + ": completed after retry");
            }

            return;
        }

        emit.accept(job.jobId() + ": failed");

        if (job.retried()) {
            emit.accept(job.jobId() + ": retry exhausted");
        }
    })
    .toList();
```

Mỗi nhánh nghiệp vụ phát một số thông báo nhỏ. `return` kết thúc lần gọi mapper của tác vụ hiện tại sau khi đã phát các thông báo cần thiết. Nó không dừng toàn bộ Stream.

Khi logic gồm nhiều nhánh và mỗi nhánh phát một vài giá trị, cách viết này thường rõ ràng hơn việc tạo nhiều Stream con rồi ghép chúng lại.

## 6. So sánh với flatMap trên cùng dữ liệu

Cùng ví dụ cấu hình dịch vụ, ta có thể viết bằng `flatMap`:

```java
import java.util.stream.Stream;

List<String> publicNames = configs.stream()
    .flatMap(config -> Stream.concat(
        Stream.of(config.serviceName()),
        config.aliases().stream()
            .filter(alias -> alias != null && !alias.isBlank())
            .map(String::trim)
    ))
    .toList();
```

Hoặc dùng `mapMulti`:

```java
List<String> publicNames = configs.stream()
    .<String>mapMulti((config, emit) -> {
        emit.accept(config.serviceName());

        for (String alias : config.aliases()) {
            if (alias != null && !alias.isBlank()) {
                emit.accept(alias.trim());
            }
        }
    })
    .toList();
```

Hai cách đều làm phẳng tên dịch vụ và alias thành một Stream. Với logic duyệt một danh sách nhỏ rồi phát giá trị, `mapMulti` diễn đạt trực tiếp hơn: mapper phát từng kết quả qua Consumer mà không cần tạo danh sách trung gian rồi gọi `stream()` trên danh sách đó.

Tuy vậy, nếu dữ liệu con vốn đã được biểu diễn bằng Stream và phép biến đổi được viết tự nhiên bằng các thao tác Stream, `flatMap` có thể dễ đọc hơn:

```java
List<String> publicNames = configs.stream()
    .flatMap(config ->
        config.aliases().stream()
            .filter(alias -> alias != null && !alias.isBlank())
            .map(String::trim)
    )
    .toList();
```

Hãy chọn cách thể hiện rõ nhất ý định xử lý. `mapMulti` là một công cụ bổ sung cho `flatMap`, không phải phương thức cần thay thế `flatMap` trong mọi pipeline.

## 7. Khi số lượng đầu ra lớn hoặc không giới hạn

Javadoc lưu ý `mapMulti` có thể không phù hợp nếu mapper tạo ra một số lượng lớn, thậm chí không giới hạn, phần tử cho mỗi đầu vào.

Một ví dụ không phù hợp là mỗi phần tử nguồn đại diện cho một khoảng số nguyên có thể rất lớn, rồi mapper phát tất cả số trong khoảng:

Ví dụ dưới đây giả định `end` không nhỏ hơn `start`:

```java
import java.util.List;
import java.util.stream.Stream;

record LongRange(long start, long end) {}

List<LongRange> ranges = List.of(
    new LongRange(0, 1_000_000_000L)
);

// Không nên dùng mapMulti cho một khoảng có thể rất lớn.
Stream<Long> expanded = ranges.stream()
    .<Long>mapMulti((range, emit) -> {
        for (long value = range.start(); ; value++) {
            emit.accept(value);
            if (value == range.end()) {
                break;
            }
        }
    });
```

Vòng lặp có thể chạy rất lâu và phát lượng dữ liệu lớn trong một lần gọi mapper. Consumer không phải một cơ chế demand/backpressure để downstream yêu cầu từng phần tử rồi tạm dừng vòng lặp tùy ý.

Vì vậy, không nên kỳ vọng thêm `limit(10)` ở phía sau sẽ tự ngắt vòng lặp bên trong mapper sau mười lần gọi `accept`. Nếu một phần tử có thể tạo ra rất nhiều kết quả và việc dừng sớm là quan trọng, một Stream con qua `flatMap` thường phù hợp hơn.

Nếu mỗi khoảng có thể chứa nhiều giá trị, hãy cân nhắc `flatMap` với một Stream con biểu diễn khoảng đó. Cách này giữ logic sinh dãy trong một nguồn Stream riêng và phù hợp hơn khi cần mô tả dữ liệu theo dạng Stream.

```java
import java.util.List;
import java.util.stream.LongStream;

record LongRange(long start, long end) {}

List<LongRange> ranges = List.of(
    new LongRange(1, 1_000_000_000L)
);

LongStream values = ranges.stream()
    .flatMapToLong(range ->
        LongStream.rangeClosed(range.start(), range.end())
    );
```

Ví dụ trên giả định `end` không nhỏ hơn `start` và khoảng giá trị nằm trong phạm vi mà ứng dụng có thể xử lý. Với dữ liệu rất lớn, không nên thu toàn bộ kết quả vào một List; hãy chọn terminal operation hoặc cách xử lý theo từng phần phù hợp với nhu cầu.

## 8. Đừng chọn mapMulti chỉ vì muốn tránh Stream con

Một lý do hợp lý để cân nhắc `mapMulti` là tránh tạo một Stream con cho từng phần tử trong trường hợp fan-out nhỏ. Tuy nhiên, không nên biến điều đó thành quy tắc "mapMulti luôn nhanh hơn flatMap".

Hiệu năng thực tế phụ thuộc vào:

- Số phần tử nguồn và số kết quả trung bình trên mỗi phần tử.
- Chi phí của logic mapper.
- Cách tạo dữ liệu con.
- Phiên bản JDK và cách triển khai Stream.
- Các thao tác tiếp theo và terminal operation.

Hợp đồng API cho phép triển khai Stream lựa chọn cách thực thi phù hợp. Vì vậy, không nên dựa vào giả định rằng Consumer luôn ghi thẳng kết quả xuống terminal operation hoặc rằng mọi triển khai đều không có vùng đệm trung gian.

Trước hết, hãy chọn phương thức làm mã dễ đọc và đúng mô hình dữ liệu. Khi có yêu cầu hiệu năng cụ thể, hãy đo bằng benchmark đại diện cho workload thực tế trên JDK mà ứng dụng sử dụng.

## 9. Giữ mapper ngắn và giới hạn tác dụng phụ

`mapMulti` phù hợp với logic mệnh lệnh ngắn, nhưng mapper vẫn nên tập trung vào việc quyết định và phát kết quả. Nếu một mapper có nhiều bước nghiệp vụ, nhiều nhánh lồng nhau hoặc cần truy cập dịch vụ bên ngoài, hãy tách phần xử lý thành phương thức có tên rõ ràng.

Ví dụ tách logic tạo nhãn:

```java
import java.util.List;
import java.util.function.Consumer;

record Device(String id, boolean online, boolean maintenance) {}

class DeviceLabels {
    static void emitDeviceLabels(
        Device device,
        Consumer<String> emit
    ) {
        if (!device.online()) {
            emit.accept(device.id() + ": offline");
            return;
        }

        emit.accept(device.id() + ": online");

        if (device.maintenance()) {
            emit.accept(device.id() + ": maintenance");
        }
    }

    public static void main(String[] args) {
        List<Device> devices = List.of(
            new Device("D-01", true, false),
            new Device("D-02", true, true),
            new Device("D-03", false, false)
        );

        List<String> labels = devices.stream()
            .<String>mapMulti((device, emit) ->
                emitDeviceLabels(device, emit)
            )
            .toList();
    }
}
```

Phương thức `emitDeviceLabels` nêu rõ quy tắc phát nhãn. Lambda trong pipeline chỉ kết nối phần tử nguồn với quy tắc đó.

Tránh cập nhật collection mutable dùng chung từ mapper, đặc biệt khi Stream chạy song song. Hãy dùng Consumer để phát kết quả và terminal operation hoặc collector để thu thập chúng. Không lưu Consumer để gọi sau khi mapper kết thúc hoặc chuyển nó sang tác vụ bất đồng bộ.

## 10. Danh sách kiểm tra trước khi chọn mapMulti

Trước khi dùng `mapMulti`, hãy tự kiểm tra:

1. Mỗi phần tử nguồn chỉ tạo ra không hoặc một số ít kết quả?
2. Số kết quả có giới hạn hợp lý theo dữ liệu hoặc nghiệp vụ?
3. Vòng lặp hay các nhánh điều kiện diễn đạt logic rõ hơn một hàm trả về Stream?
4. Mapper có thể phát kết quả trực tiếp mà không cần tạo collection trung gian?
5. Mapper không phụ thuộc vào tác dụng phụ trên trạng thái dùng chung?
6. Nếu số kết quả có thể lớn hoặc không giới hạn, đã cân nhắc một Stream con bằng `flatMap` chưa?

Nếu các câu trả lời phù hợp với mô hình phát kết quả nhỏ và mệnh lệnh, `mapMulti` là lựa chọn đáng cân nhắc.

## 11. Ghi nhớ

- `mapMulti` đặc biệt phù hợp khi mỗi phần tử nguồn phát ra một số lượng nhỏ kết quả, có thể bằng không.
- Vòng lặp ngắn và nhiều nhánh điều kiện là những dạng logic mệnh lệnh phù hợp với mapper.
- Không có ngưỡng số lượng cố định cho khái niệm "nhỏ"; hãy xét giới hạn nghiệp vụ và tổng khối lượng dữ liệu.
- Với số lượng kết quả lớn hoặc không giới hạn, cân nhắc `flatMap` và một Stream con phù hợp.
- Không giả định `mapMulti` luôn nhanh hơn `flatMap` hoặc luôn tránh mọi vùng đệm trung gian.
- Giữ mapper tập trung, không dùng Consumer như cơ chế bất đồng bộ hay collection dùng chung.

Khi số kết quả trên mỗi phần tử nhỏ và logic phát dữ liệu tự nhiên theo cách mệnh lệnh, `mapMulti` giúp biểu đạt phép biến đổi một-nhiều trực tiếp và gọn gàng trong Stream pipeline.

