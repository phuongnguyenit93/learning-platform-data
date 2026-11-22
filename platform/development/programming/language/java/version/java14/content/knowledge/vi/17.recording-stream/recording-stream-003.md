# Thay thế tập cấu hình qua `RecordingStream.setSettings(Map<String,String>)` (Java 14+)

> Bài học thuộc nhóm `RecordingStream` của Java Flight Recorder (JFR). Trọng tâm là **`setSettings` thay thế trọn bộ settings**, không phải thêm hoặc chỉ sửa vài khóa; cách giữ các thiết lập cần thiết khi chuyển cấu hình ngay cả khi stream đang chạy. API có từ Java 14 và vẫn tồn tại trong Java SE 17/21/26; ví dụ biên dịch bằng JDK 17+ mà không dùng kỹ thuật legacy hay preview.

## 1. `RecordingStream` và settings điều khiển những gì?

`jdk.jfr.consumer.RecordingStream` là API trong module `jdk.jfr`, cho phép ứng dụng **theo dõi sự kiện JFR từ chính JVM hiện tại** và nhận chúng qua callback `onEvent(...)`. Những sự kiện đó có thể là GC, CPU load, method profiling, monitor contention hoặc custom event do ứng dụng phát ra.

Có hai khía cạnh tách biệt cần nhớ:

- **Recording settings** quyết định loại event nào được bật, tần suất ghi, threshold, stack trace và những tùy chọn được hỗ trợ riêng bởi từng event.
- **Event handlers** đăng ký bằng `onEvent(...)` quyết định callback nào sẽ xử lý một event được stream phát ra. Việc đăng ký callback không đồng nghĩa tự động bật loại event đó.

Mỗi setting của JFR được biểu diễn bằng **một cặp String–String** trong `Map<String,String>`. Tên setting có dạng:

```text
<event-name>#<setting-name> = <setting-value>
```

Ví dụ:

```java
Map<String, String> settings = Map.of(
    "jdk.CPULoad#enabled", "true",
    "jdk.CPULoad#period", "1 s",
    "jdk.JavaMonitorEnter#enabled", "false"
);
```

Đây là **snippet minh họa** cần `import java.util.Map;` và đặt trong phương thức. `jdk.CPULoad` và `jdk.JavaMonitorEnter` là các tên event JFR chuẩn có ở JDK thông dụng. Các setting như `enabled`, `period` và `threshold` chỉ nên áp dụng cho event hỗ trợ chúng; không phải event nào cũng có `period` hoặc `threshold`.

**`Map` chứa các chuỗi cấu hình**, không phải danh sách callback, không phải danh sách tất cả event đã thu thập, và không phải cấu hình JVM toàn cục.

## 2. Hợp đồng chính xác của `setSettings`

Chữ ký API:

```java
void setSettings(Map<String, String> settings)
```

JavaDoc Oracle định nghĩa `setSettings` là **“Replaces all settings for this recording stream”** — nghĩa là thay **toàn bộ** settings của chính stream đó.

Điều này có hệ quả quan trọng:

1. Một lần gọi `stream.setSettings(newSettings)` thiết lập **tập setting mới** cho stream, thay vì chỉ ghi thêm cặp key–value vào tập cũ.
2. Các **setting tường minh** có trong tập trước nhưng **vắng mặt trong map mới** không được tự động giữ lại.
3. Nếu muốn giữ lại những setting đang cần, phải **tạo một map đầy đủ** bao gồm chúng rồi truyền cả map cho `setSettings`.
4. Tập thay thế chỉ áp dụng cho **recording stream hiện tại**. Nó không đồng nghĩa sửa `Configuration` nguồn trên disk, không tái cấu hình tất cả recording khác và không thay callback `onEvent`.
5. Không suy luận rằng **mọi event vắng mặt trong map mới đều chắc chắn bị disable**. Khi không có cấu hình tường minh, trạng thái hiệu dụng còn tùy default và đặc tả setting của event/JFR. Điều chắc chắn từ hợp đồng API là **các entry cũ không được tự động merge**.

### Trước và sau: minh họa map

```text
Lần 1:
  jdk.CPULoad#enabled    = true
  jdk.CPULoad#period     = 1 s

Lần 2:
  jdk.JavaMonitorEnter#enabled   = true
  jdk.JavaMonitorEnter#threshold = 0 ms

Sau lần 2, map cũ không được trộn vào map mới.
```

Không hiểu lần 2 là `putAll` vào map lần 1. `setSettings` không có tham số thể hiện “merge” hay “patch”; chữ ký và tài liệu chỉ mô tả **replacement**.

## 3. Cách viết code: replace toàn bộ versus đổi một setting

### 3.1. Muốn **thay hoàn toàn**: dùng `setSettings`

```java
stream.setSettings(Map.of(
    "jdk.CPULoad#enabled", "true",
    "jdk.CPULoad#period", "1 s"
));

// Sau này chuyển sang tập setting khác:
stream.setSettings(Map.of(
    "jdk.JavaMonitorEnter#enabled", "true",
    "jdk.JavaMonitorEnter#threshold", "0 ms"
));
```

Đây là snippet trong phương thức đã có biến `RecordingStream stream`. Lần hai **không kế thừa** entry `jdk.CPULoad#period` của lần một. Dù entry ở map ban đầu là `enabled=true`, không nên mặc định tính năng CPULoad tiếp tục bật theo setting cũ sau khi thay tập.

**Không dùng `setSettings` như API “đổi riêng một khóa”** nếu mục đích là giữ nguyên mọi tùy chọn hiện tại.

### 3.2. Muốn điều chỉnh một event trong stream: `enable`/`disable`

`RecordingStream` còn có phương thức chuyên dụng để thay đổi điều khiển event:

```java
stream.enable("jdk.CPULoad")
      .withPeriod(java.time.Duration.ofSeconds(2));
stream.disable("jdk.JavaMonitorEnter");
```

`enable` trả về `EventSettings` để tiếp tục cấu hình các thuộc tính được event hỗ trợ; `disable` cũng là API chuyên dụng. Đây là cách dễ đọc để cấu hình có mục tiêu **một event** mà không phải tự xây map đầy đủ. **Không chạy `setSettings` với map nhỏ ngay sau đó rồi nghĩ rằng toàn bộ thiết lập tạo bởi `enable` được giữ lại.**

Các callback như `stream.onEvent("jdk.CPULoad", event -> {...})` là mặt xử lý dữ liệu của stream; việc gọi `disable` hay `setSettings` không có nghĩa tự hủy đăng ký listener đó.

### 3.3. Muốn “gộp thay đổi” nhưng chỉ có API replacement

Vì `RecordingStream` không cung cấp một getter công khai tên `getSettings()` để lấy lại toàn bộ settings đang áp dụng, ứng dụng nên **giữ một bản map cấu hình mà chính nó quản lý**:

```java
import java.util.HashMap;
import java.util.Map;

Map<String, String> current = new HashMap<>();
current.put("jdk.CPULoad#enabled", "true");
current.put("jdk.CPULoad#period", "1 s");
stream.setSettings(current);

// Tạo bản trạng thái mong muốn mới:
Map<String, String> next = new HashMap<>(current);
next.put("jdk.CPULoad#period", "2 s");
next.put("jdk.JavaMonitorEnter#enabled", "true");

// Gọi lại bằng TOÀN BỘ map, không chỉ các khóa vừa thay:
stream.setSettings(next);
current = next;
```

Đây là **snippet trình bày thuật toán**: các import nằm ở đầu tệp, các câu lệnh phải ở một phương thức có biến `stream`. Nếu cần cấu hình bất biến giữa nhiều thread, hãy lưu snapshot bằng `Map.copyOf(next)` (chỉ khi không có null key/value) và đồng bộ thao tác cập nhật trạng thái/áp dụng theo chiến lược của ứng dụng.

**Phân biệt quan trọng:** sử dụng `new HashMap<>(current)` tạo một map Java mới và `put` các thay đổi; còn **`setSettings` vẫn là replacement**. Việc merge xảy ra ở **mã của bạn trước lời gọi**, không phải bên trong API `RecordingStream`.

## 4. Chuyển giữa các cấu hình JFR `default` và `profile`

`jdk.jfr.Configuration` đại diện một cấu hình JFR có tên và settings. JDK thường cung cấp các cấu hình chuẩn `default` và `profile`, vốn khác nhau về số lượng, chi phí và loại dữ liệu quan sát. Có thể đọc settings bằng `Configuration.getSettings()`:

```java
import jdk.jfr.Configuration;
import jdk.jfr.consumer.RecordingStream;

Configuration defaultConfig = Configuration.getConfiguration("default");
Configuration profileConfig = Configuration.getConfiguration("profile");

try (RecordingStream stream = new RecordingStream(defaultConfig)) {
    stream.onEvent("jdk.CPULoad", event -> {
        // Xử lý event với API RecordedEvent theo nhu cầu.
    });
    stream.startAsync();
    Thread.sleep(1_000);
    stream.setSettings(profileConfig.getSettings());
    Thread.sleep(1_000);
}
```

Đây là **snippet nằm trong phương thức có `throws Exception` hoặc xử lý `IOException`, `ParseException`, `InterruptedException`**; chương trình hoàn chỉnh độc lập có ở mục 7.

- Constructor `RecordingStream(defaultConfig)` khởi tạo stream với settings của profile `default`.
- `startAsync()` khởi chạy xử lý bất đồng bộ để code điều khiển tiếp tục chạy trên thread gọi.
- `setSettings(profileConfig.getSettings())` **thay toàn bộ** tập settings của stream đang hoạt động bằng tập `profile`; không cần đóng rồi tạo stream mới để chuyển profile.
- `Thread.sleep(...)` trong snippet chỉ giữ chương trình sống để quan sát chuyển đổi, **không phải cơ chế đồng bộ bảo đảm mọi event đã được tiêu thụ**.
- `try-with-resources` tự `close()` để giải phóng tài nguyên JFR sau đoạn thí nghiệm.

**Có thể sửa một profile chuẩn trước khi áp dụng** bằng cách sao chép settings sang `HashMap`:

```java
Map<String, String> profileWithExtra =
    new java.util.HashMap<>(profileConfig.getSettings());
profileWithExtra.put("jdk.CPULoad#enabled", "true");
stream.setSettings(profileWithExtra);
```

`Configuration.getSettings()` trả settings của profile; việc sửa riêng đối tượng Map nhận được **không làm đổi cấu hình `Configuration`**. Tạo bản sao bằng `HashMap` làm ý đồ rõ ràng và tránh giả định map nguồn có thể chỉnh sửa.

### Không nhầm JFR profile với setting duy nhất

Một map chỉ có `"jdk.CPULoad#enabled"` **không tương đương** preset `default` hoặc `profile`, vốn gồm nhiều entry cho nhiều sự kiện. Nếu cần giữ tất cả settings preset và chỉ sửa một điều kiện, hãy bắt đầu từ `getSettings()` của preset rồi bổ sung entry trước khi gọi `setSettings`.

**Không gọi `setSettings(Map.of())` để “khôi phục mặc định”.** Hợp đồng là thay tập settings bằng map rỗng; nó không hứa nạp lại `default.jfc`. Muốn quay về preset, hãy gọi `setSettings(defaultConfig.getSettings())`.

## 5. Chi tiết về khóa và giá trị trong `Map<String,String>`

| Thành phần | Ý nghĩa / ví dụ | Lưu ý |
|---|---|---|
| `jdk.CPULoad` | Tên event JFR | Nên dùng tên thật được JFR hỗ trợ; với custom event có thể đặt bằng `@Name` |
| `#enabled` | Bật/tắt event, ví dụ `"true"`, `"false"` | Là một setting, không phải lời gọi handler |
| `#period` | Chu kỳ sample, ví dụ `"1 s"` | Chỉ dùng với event có setting period |
| `#threshold` | Ngưỡng thời lượng, ví dụ `"0 ms"` | Phù hợp với event hỗ trợ threshold |
| `#stackTrace` | Có thu thập stack trace hay không | Có thể tăng dung lượng và overhead |
| `Map<String,String>` | Các khóa/giá trị dạng String | `setSettings` yêu cầu argument map **không được null** |

Có thể tìm chính xác tên event và settings hỗ trợ bằng `jdk.jfr.FlightRecorder.getFlightRecorder().getEventTypes()` và `EventType.getSettingDescriptors()` khi cần cấu hình động; với tên trùng giữa class loaders, API `enable(Class)` hoặc ID của event có thể tránh nhập nhằng.

**Không tự chế đặt tất cả mọi setting cho một event** rồi trông đợi chúng luôn có hiệu lực. Một event như `jdk.CPULoad` có thể hỗ trợ `period` trong khi event khác chủ yếu có `threshold`. Khi triển khai, kiểm tra trên **JDK thực tế** và dùng cấu hình JFR có sẵn hoặc `EventSettings` để giảm lỗi nhập tên.

`Map` được truyền vào là một tập settings, **không phải** một command “upsert”. JavaDoc yêu cầu `settings != null`; không gọi `setSettings(null)`. Các key/value nên là chuỗi hợp lệ theo mô tả JFR (đơn vị thời gian, giá trị boolean, tên event và setting), và tránh truyền dữ liệu người dùng không kiểm soát vào cấu hình profiling.

## 6. Thay settings trong lúc stream chạy: tác dụng và giới hạn

Oracle minh họa chuyển `default` sang `profile` **sau `startAsync()`**, nên việc cập nhật settings ngay khi stream đang chạy là tình huống API hỗ trợ.

Tuy vậy, phải phân biệt **thay đổi cấu hình recording** với **thời điểm event đến callback**:

1. `setSettings` thay thế các thiết lập để ghi sự kiện; các sự kiện mới có thể được sản xuất theo cấu hình mới.
2. JFR ghi vào buffer và chuyển dữ liệu tới stream theo cơ chế bất đồng bộ. Callback `onEvent` có thể còn nhận những event **đã được ghi trước lúc chuyển cấu hình**.
3. Không đảm bảo gọi `setSettings` xong thì mọi callback được gọi ngay sau đó chỉ thuộc “pha mới”, hoặc có đúng một số event xác định trong vài trăm ms.
4. Nếu cần phân tách giai đoạn đo chính xác, ứng dụng phải thiết kế cơ chế nhận diện thời gian/phase thích hợp và đồng bộ theo hợp đồng có thể kiểm chứng, không dùng mỗi `Thread.sleep` làm “barrier”.
5. Profile `profile` có thể thu thập nhiều dữ liệu và tăng overhead so với `default`; phải cân nhắc tài nguyên CPU, buffer, lưu trữ, tần suất sự kiện và bảo mật khi bật profiling sâu trong production.

`setSettings` **không đổi** callbacks đăng ký trước đó qua `onEvent` và không tự đóng stream. Dùng `close()` hoặc `try-with-resources` đúng vòng đời. Ngược lại, việc không thấy event sau khi đổi cấu hình **không chứng minh** listener đã bị xóa; có thể event không được enabled, chưa phát sinh, hoặc chưa flush ra stream.

## 7. Ví dụ Java 17+ hoàn chỉnh, kết quả xác định và đã kiểm chứng

Tệp **`RecordingStreamSettingsDemo.java`** sau chạy trên HotSpot OpenJDK 24 và dùng API chuẩn hiện đại. Chương trình tạo hai tập settings không giao nhau, gọi `setSettings` hai lần **trên cùng một stream**, và in **các key từ map do ứng dụng truyền vào** để tránh nhầm chúng với số lượng event JFR đến bất đồng bộ.

```java
import java.util.Map;
import java.util.TreeSet;
import jdk.jfr.consumer.RecordingStream;

public class RecordingStreamSettingsDemo {
    public static void main(String[] args) throws Exception {
        Map<String, String> first = Map.of(
            "jdk.CPULoad#enabled", "true",
            "jdk.CPULoad#period", "1 s"
        );
        Map<String, String> second = Map.of(
            "jdk.JavaMonitorEnter#enabled", "true",
            "jdk.JavaMonitorEnter#threshold", "0 ms"
        );
        try (RecordingStream stream = new RecordingStream()) {
            stream.onEvent("jdk.CPULoad", event -> {});
            stream.onEvent("jdk.JavaMonitorEnter", event -> {});
            stream.setSettings(first);
            stream.startAsync();
            Thread.sleep(350);
            stream.setSettings(second);
            Thread.sleep(350);
            System.out.println("firstKeys=" + new TreeSet<>(first.keySet()));
            System.out.println("secondKeys=" + new TreeSet<>(second.keySet()));
            System.out.println("oldKeyInSecond=" +
                second.containsKey("jdk.CPULoad#enabled"));
            System.out.println("sameStream=true");
        }
    }
}
```

Biên dịch và chạy (JDK 17+ có module `jdk.jfr`):

```bash
javac -encoding UTF-8 RecordingStreamSettingsDemo.java
java RecordingStreamSettingsDemo
```

**Stdout chính xác đã xác minh trên OpenJDK 24**:

```text
firstKeys=[jdk.CPULoad#enabled, jdk.CPULoad#period]
secondKeys=[jdk.JavaMonitorEnter#enabled, jdk.JavaMonitorEnter#threshold]
oldKeyInSecond=false
sameStream=true
```

**Diễn giải chính xác kết quả:**

- `firstKeys` là hai key `jdk.CPULoad` ban đầu mà chương trình đưa vào `setSettings(first)`.
- `secondKeys` là hai key `jdk.JavaMonitorEnter` được đưa vào `setSettings(second)`.
- `oldKeyInSecond=false` khẳng định **map mới trong mã** không chứa entry `jdk.CPULoad#enabled`, vì `Map.of(...)` tạo hai map riêng.
- Theo **hợp đồng `setSettings` của Oracle**, lời gọi thứ hai dùng map `second` làm **tập settings mới thay thế** cho stream, không merge với `first`.
- `sameStream=true` là nhãn thông báo chủ động của ví dụ, thể hiện code sử dụng cùng biến `stream` trong cả hai lần gọi; đây **không phải một phép đo runtime về event stream**.
- Chương trình cố ý dùng callback rỗng; nó kiểm thử đường gọi API và kết quả map một cách ổn định, **không** khẳng định thu được hay mất đi một số lượng event nhất định.

`Thread.sleep(350)` chỉ giữ stream còn sống đủ để minh họa chuyển settings khi hoạt động. Trong CI hoặc môi trường container hạn chế JFR, nếu JVM không hỗ trợ Flight Recorder hoặc không tạo được repository thì constructor có thể báo lỗi; đây là **yêu cầu môi trường**, không phải vấn đề biên dịch. Khi chạy thử nghiệp vụ thật, hãy dùng JVM hỗ trợ JFR.

## 8. Sai lầm phổ biến khi dùng `setSettings`

### Sai 1 — tưởng map mới là bản vá nhỏ

```java
stream.enable("jdk.CPULoad").withPeriod(java.time.Duration.ofSeconds(1));
stream.setSettings(Map.of("jdk.JavaMonitorEnter#enabled", "true"));
```

Nếu ý định giữ period/enable của `jdk.CPULoad`, cách viết này **sai về ý đồ**: lần `setSettings` cuối đã **thay toàn bộ** tập settings, không được đảm bảo giữ thiết lập CPULoad cũ. Sửa bằng cách tạo đầy đủ map mong muốn rồi gọi một lần `setSettings`, hoặc dùng `enable`/`disable` cho thay đổi có mục tiêu.

### Sai 2 — chỉ giữ một phần profile

```java
Configuration profile = Configuration.getConfiguration("profile");
stream.setSettings(Map.of("jdk.CPULoad#enabled", "true"));
```

Đoạn này không áp dụng profile `profile`. Việc có biến `profile` không đủ: bạn đã truyền vào map chỉ có **một** entry. Sửa:

```java
Map<String, String> desired =
    new java.util.HashMap<>(profile.getSettings());
desired.put("jdk.CPULoad#enabled", "true");
stream.setSettings(desired);
```

Cả ba snippet ở mục này là mã **minh họa** trong phương thức có biến `stream` và import tương ứng; không phải các chương trình độc lập.

### Sai 3 — nghĩ `Map.of()` mặc định rỗng chính là `default.jfc`

```java
stream.setSettings(Map.of());
```

Map rỗng **không** được API định nghĩa là yêu cầu nạp preset. Dùng `Configuration.getConfiguration("default").getSettings()` nếu muốn thay bằng đúng cấu hình JFR `default`.

### Sai 4 — muốn đo chính xác thời điểm chuyển chỉ bằng `Thread.sleep`

Sau `setSettings`, event đã phát sinh từ trước có thể vẫn được chuyển đến callback. Không nên dùng một lần `sleep(100)` và kết luận toàn bộ event callback tiếp theo chỉ phản ánh tập settings mới. Hãy đánh dấu thời điểm/correlation ID trong event nghiệp vụ và có phương pháp đo phù hợp.

### Sai 5 — dùng `getSettings()` tưởng là getter của `RecordingStream`

`Configuration` có `getSettings()`; `jdk.jfr.Recording` cũng có API getter settings riêng. **`RecordingStream` không công bố `getSettings()` trong các API JDK 17/26 tương ứng**. Để cập nhật có kiểm soát, giữ map cấu hình mong muốn trong ứng dụng, hoặc đọc từ `Configuration` rồi tạo map mới như mục 3.

### Sai 6 — nhầm configuration với callback

`stream.onEvent("jdk.CPULoad", consumer)` là đăng ký **cách xử lý** event. Muốn thấy event, còn cần event được JFR ghi và phát sinh thật. `setSettings` là cơ chế cấu hình **cách ghi**; không phải đăng ký hoặc hủy `consumer`.

### Sai 7 — set settings quá tốn tài nguyên trong production

Bật quá nhiều event, hạ threshold thấp hoặc đặt period quá dày có thể làm tăng chi phí ghi, kích thước dữ liệu và áp lực xử lý callback. Cần benchmark, điều chỉnh `setMaxAge`/`setMaxSize` khi phù hợp và bảo vệ dữ liệu nhạy cảm có trong recording. Không chạy profiling nặng vô hạn chỉ vì có thể chỉnh settings động.

## 9. Checklist trước khi áp dụng vào dịch vụ đang chạy

1. Xác định rõ mục tiêu là **thay toàn bộ tập settings** hay chỉ sửa một event. Với trường hợp sau, cân nhắc `enable()`/`disable()` hoặc merge map trong ứng dụng.
2. Đảm bảo map truyền cho `setSettings` gồm **tất cả entry bạn muốn duy trì**; không trông đợi API tự giữ entry cũ.
3. Dùng tên event + `#setting` hợp lệ và giá trị `String` đúng định dạng của JFR trên JDK mục tiêu.
4. Nếu bắt đầu từ `default`/`profile`, lấy `Configuration.getSettings()` rồi thêm/sửa bằng bản sao `HashMap` nếu cần.
5. Tránh dùng `Map.of()` để giả định tự khôi phục preset; muốn khôi phục, truyền rõ `defaultConfig.getSettings()`.
6. Cấu hình callback `onEvent` riêng; không giả định nó bật event hoặc `setSettings` xóa listener.
7. Nếu dùng `startAsync` và chỉnh settings trong lúc hoạt động, phân biệt event được ghi **trước** và **sau** thời điểm đổi, lưu ý buffering.
8. Khi thử nghiệm, đừng assert số event đến đúng theo một thời gian `sleep` cố định; test riêng cấu trúc settings và luồng callback có đồng bộ thích hợp.
9. Đảm bảo xử lý lỗi môi trường JFR, exception từ callback, vòng đời `close()` và giải phóng stream.
10. Theo dõi overhead CPU, event throughput, repository/buffer và chính sách bảo vệ dữ liệu khi thay profile.
11. Dùng API JDK hiện đại (`jdk.jfr`, JDK 17+), không dựa vào tài liệu preview hoặc công cụ JFR cũ đã lỗi thời.

## Nguồn tham khảo chính thức

- Oracle Java SE 26 API, `jdk.jfr.consumer.RecordingStream` — `setSettings`: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html
- Oracle Java SE 17 API, `RecordingStream` — `enable`, `disable`, `startAsync`, `setSettings`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html
- Oracle Java SE 17 API, `jdk.jfr.Configuration` — `getConfiguration`, `getSettings`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Configuration.html
- Oracle Java SE 17 API, `jdk.jfr.Recording` — `getSettings` và `setSettings` của recording thường: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html
- Oracle Java SE 17 API, `EventSettings` — cấu hình từng event: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/EventSettings.html
