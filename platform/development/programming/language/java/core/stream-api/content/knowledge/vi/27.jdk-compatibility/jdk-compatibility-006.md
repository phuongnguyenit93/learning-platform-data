# Phân biệt Gatherer thử nghiệm và API chính thức từ Java 24

**Stream Gatherers** mở rộng Java Stream API bằng khả năng định nghĩa **thao tác trung gian tùy chỉnh** (*custom intermediate operation*). Nếu `filter` và `map` xử lý từng phần tử, còn `collect` tổng hợp ở cuối pipeline, một `Gatherer` có thể duy trì trạng thái, tạo cửa sổ, phát nhiều kết quả, dừng sớm hoặc biến đổi đầu ra theo một cách không thuận tiện với các thao tác trung gian có sẵn.

Tuy nhiên, khi học hoặc triển khai `Stream.gather(...)`, **phiên bản JDK là một phần của tính đúng**. Stream Gatherers xuất hiện dưới dạng **preview API trong Java 22**, được đưa vào **preview lần hai trong Java 23**, rồi trở thành **API chính thức trong Java 24**. Ba giai đoạn này không có cùng yêu cầu biên dịch, chạy chương trình và bảo đảm tương thích.

Bài thuộc chương **Khả năng tương thích JDK** của mô-đun **JAVA_STREAM_API**. Ngoài phân biệt các mốc JDK, chúng ta sẽ xây các pipeline với `Gatherers.windowFixed`, `windowSliding`, `scan`, `fold` và `mapConcurrent`; xem cách viết custom Gatherer; xác định chiến lược triển khai cho ứng dụng vẫn chạy Java 17/21; đồng thời đánh giá tính lazy, xử lý song song, tài nguyên, trạng thái và hiệu năng.

## 1. Bản đồ phiên bản: Java 22, 23 và 24

| JDK | Trạng thái Stream Gatherers | JEP | Biên dịch mã sử dụng Gatherer | Chạy chương trình |
| --- | --- | --- | --- | --- |
| Java 8–21 | **Chưa có API Stream Gatherers chuẩn** | — | Không thể sử dụng trực tiếp `java.util.stream.Gatherer` từ JDK này | Cần giải pháp thay thế hoặc nâng JDK |
| Java 22 | **Preview lần đầu** | [JEP 461](https://openjdk.org/jeps/461) | JDK 22, bật `--enable-preview` với `--release 22` | JDK 22, bật `--enable-preview` |
| Java 23 | **Second preview** | [JEP 473](https://openjdk.org/jeps/473) | JDK 23, bật `--enable-preview` với `--release 23` | JDK 23, bật `--enable-preview` |
| Java 24 | **API chính thức, không còn preview** | [JEP 485](https://openjdk.org/jeps/485) | JDK 24, biên dịch bình thường | JDK 24, chạy bình thường |
| Java 25 | **Tiếp tục có API chính thức** | Được chuẩn hóa từ JDK 24 | Dùng JDK và cấu hình build phù hợp với target | Runtime phải hỗ trợ API mà ứng dụng dùng |

Từ Java 24, `Stream.gather`, `Gatherer` và `Gatherers` trở thành một phần chính thức của thư viện chuẩn `java.base`. **Không cần `--enable-preview` chỉ để sử dụng Stream Gatherers trên Java 24.** Nếu một ứng dụng Java 24 đồng thời dùng **tính năng preview khác**, yêu cầu bật preview của tính năng đó là chuyện riêng.

Ba điểm dễ nhầm cần phân biệt:

1. **“Có API”**: JDK chứa các lớp và phương thức cần dùng.
2. **“Được phép gọi API”**: ở JDK 22/23 cần bật preview; ở JDK 24 thì không.
3. **“Chạy được trên máy khác”**: phụ thuộc phiên bản JDK runtime và bytecode mà ứng dụng được biên dịch ra; một JDK mới **không tự làm ứng dụng tương thích ngược với JDK cũ**.

### Dòng thời gian

```text
Java 21         Java 22               Java 23               Java 24
   |               |                     |                     |
   |      JEP 461: Preview       JEP 473: Preview 2    JEP 485: Final
   |               |                     |                     |
Không có      --enable-preview     --enable-preview      Không cần flag
Gatherer      lúc compile/run      lúc compile/run      cho Gatherer
   |               |                     |                     |
   +---------------+---------------------+--------------------->
            Chuyển từ thử nghiệm sang API chính thức
```

**Kết luận về phạm vi phiên bản:** Người học dùng **Java 17/21** có thể học lý thuyết và các phép Stream thông thường, nhưng **không thể chạy trực tiếp ví dụ `Stream.gather` chuẩn** nếu chưa chuyển sang một JDK cung cấp API đó.

## 2. Preview API có nghĩa gì?

Trong Java, *preview feature* là một cơ chế cho phép lập trình viên trải nghiệm tính năng đã có thiết kế và triển khai nhưng **chưa được chuẩn hóa vĩnh viễn**. Mục tiêu của preview là nhận phản hồi thực tế trước khi API được hoàn thiện hoặc thay đổi.

Điểm quan trọng: **preview không đồng nghĩa API thử nghiệm tùy tiện không có hợp đồng**. JDK vẫn có tài liệu API và quy tắc sử dụng. Tuy nhiên, người dùng preview cần chấp nhận khả năng những phiên bản tiếp theo có thay đổi về bề mặt API, cách hoạt động hoặc khả năng tồn tại của tính năng.

| Khái niệm | Ý nghĩa đối với Gatherer |
| --- | --- |
| `preview` (Java 22/23) | API có trong JDK nhưng phải được bật tường minh; chưa là phần ổn định vĩnh viễn của nền tảng |
| `second preview` (Java 23) | Thêm một vòng lấy phản hồi trước khi chuẩn hóa; **vẫn** cần bật preview |
| `final` (Java 24) | API trở thành thành phần chính thức của Java SE; không cần flag preview riêng |
| `incubator` | Cơ chế thử nghiệm khác của Java; **không phải** trạng thái của Stream Gatherers trong các JDK 22/23 |
| `deprecated` | API được đánh dấu hạn chế/khuyến nghị tránh dùng; **không đồng nghĩa** với preview |
| `LTS` | Chính sách hỗ trợ một bản JDK, **khác** với trạng thái preview/final của API |

Đặc biệt, “Java 24 đã final Gatherers” **không có nghĩa** mọi thao tác Gatherer tùy chỉnh của ứng dụng đều tự động đúng, tối ưu hoặc an toàn khi song song. Đây là khẳng định về **trạng thái API trong nền tảng**, không phải kết quả kiểm thử mã nghiệp vụ.

### 2.1. Tại sao có hai vòng preview?

Java 22 đưa Stream Gatherers vào để người dùng thử cách định nghĩa thao tác trung gian có trạng thái. Java 23 giữ tính năng ở trạng thái preview lần hai để thu thập thêm phản hồi và tiếp tục hoàn thiện. Java 24 chuẩn hóa cơ chế này thành API chính thức.

Ngay cả khi một ví dụ sử dụng các factory có cùng tên giữa Java 22 và Java 24, không nên suy rằng **mọi mã dùng triển khai custom Gatherer hoặc mọi file class preview cũ** có thể được tái sử dụng nguyên trạng mà không kiểm tra.

## 3. Lệnh biên dịch và chạy đúng theo từng phiên bản

Ta sử dụng một chương trình nhỏ tên `GathererVersionDemo.java`. Chương trình dùng `windowFixed(3)` để gom các số thành cửa sổ ba phần tử.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GathererVersionDemo {
    public static void main(String[] args) {
        List<List<Integer>> batches = Stream
            .of(1, 2, 3, 4, 5, 6, 7)
            .gather(Gatherers.windowFixed(3))
            .toList();

        System.out.println(batches);
        // [[1, 2, 3], [4, 5, 6], [7]]
    }
}
```

Ví dụ này dùng những tên API cơ bản đã có ở các vòng preview và trong JDK 24. Tuy nhiên, **phải biên dịch riêng với JDK của phiên bản đích** và áp dụng flags theo từng trường hợp.

### 3.1. Java 22 — Preview theo JEP 461

Dùng đúng `javac` và `java` của **JDK 22**:

```bash
javac --enable-preview --release 22 GathererVersionDemo.java
java --enable-preview GathererVersionDemo
```

Ở đây:

- `--release 22` chỉ định API và bytecode mục tiêu của Java 22.
- `--enable-preview` cho phép sử dụng các preview feature thuộc **bản phát hành 22**.
- Khi chạy, `java --enable-preview` phải được cung cấp cùng môi trường JDK 22 thích hợp.

Không thử thay `--release 22` bằng `--release 21` để “vẫn dùng API của Java 22 nhưng chạy trên Java 21”: Java 21 chưa có các API đó.

### 3.2. Java 23 — Second preview theo JEP 473

Dùng JDK 23:

```bash
javac --enable-preview --release 23 GathererVersionDemo.java
java --enable-preview GathererVersionDemo
```

**Preview lần hai không tự bật.** Các lớp `Gatherer` và `Gatherers` trong JDK 23 vẫn được đánh dấu preview. Không được bỏ `--enable-preview` chỉ vì API đã trải qua một vòng xem xét.

Khi nâng dự án từ Java 22 lên 23, hãy **biên dịch lại** bằng JDK 23 và kiểm tra tất cả cách dùng preview API, đặc biệt nếu dự án tự triển khai `Gatherer<T,A,R>`, `Integrator`, `combiner` hoặc `finisher`. Không dựa vào việc có tên API giống nhau để bảo đảm tương thích nhị phân.

### 3.3. Java 24 — API chính thức theo JEP 485

Dùng JDK 24:

```bash
javac --release 24 GathererVersionDemo.java
java GathererVersionDemo
```

Hoặc, khi đã chắc chắn `javac` và `java` thuộc đúng JDK 24:

```bash
javac GathererVersionDemo.java
java GathererVersionDemo
```

**Không cần** `--enable-preview` cho Stream Gatherers. Nếu thử biên dịch bằng JDK 21 hoặc cấu hình `--release 21` thì mã vẫn không tương thích, bởi `Gatherer` chưa có trong Java 21.

### 3.4. Bảng lệnh đối chiếu

| Môi trường | Lệnh `javac` | Lệnh `java` | Có dùng Gatherer chuẩn? |
| --- | --- | --- | --- |
| JDK 21 | `javac --release 21 ...` | `java ...` | Không |
| JDK 22 | `javac --enable-preview --release 22 ...` | `java --enable-preview ...` | Có, bản preview |
| JDK 23 | `javac --enable-preview --release 23 ...` | `java --enable-preview ...` | Có, bản preview 2 |
| JDK 24 | `javac --release 24 ...` | `java ...` | Có, bản chính thức |

Ba dấu chấm `...` trong bảng là tên tệp nguồn hoặc tên lớp cụ thể của ứng dụng, không phải tham số shell cần nhập nguyên văn.

## 4. Vì sao `--enable-preview` không giải quyết mọi lỗi phiên bản?

`--enable-preview` chỉ bật **những preview feature được cung cấp trong JDK đang dùng**, không phải một công tắc tải thêm bất kỳ tính năng nào từ phiên bản Java tương lai.

Các trường hợp cần phân biệt:

- **JDK 21 + `--enable-preview`:** vẫn không có `Gatherers` chuẩn. Java 21 không cung cấp JEP 461.
- **JDK 22 + không bật preview:** sử dụng Gatherers sẽ bị compiler từ chối do API đang ở trạng thái preview.
- **JDK 23 + `--release 22` và bật preview:** không phải cách dùng preview Java 22 trên compiler JDK 23. Preview được gắn với **bản phát hành hiện tại** của compiler.
- **JDK 24 + `--release 21`:** không thể dùng `Stream.gather` của Java 24 để tạo artifact tuyên bố tương thích Java 21.
- **JDK 24 + `--release 24`:** dùng API Gatherer chính thức mà không cần flag preview.

### 4.1. Preview bytecode cần được xem là ràng buộc triển khai

Các phiên bản Java có cách đánh dấu và kiểm tra class file sử dụng preview feature. Khi nâng từ JDK preview cũ, **đừng chuyển thẳng các class file/build artifact cũ sang JDK mới rồi cho rằng chúng sẽ chạy**. Chiến lược an toàn là:

1. Chọn JDK mục tiêu mới.
2. Làm sạch output biên dịch cũ.
3. Biên dịch lại toàn bộ phần mã dùng Gatherer dưới JDK đó.
4. Chạy kiểm thử ngữ nghĩa, bao gồm trường hợp rỗng, dừng sớm và song song.
5. Kiểm tra runtime thật của môi trường deploy.

Các source file dùng preview API ở JDK 22/23 có thể cần điều chỉnh khi chuyển sang JDK 24, nhất là phần custom Gatherer; **không khẳng định tương thích nhị phân chỉ từ việc chương trình biên dịch được tại một mốc trước đó**.

### 4.2. JDK, Java runtime và `--release` không phải một thứ

Chạy:

```bash
java -version
javac -version
```

để xác định hai chương trình có thuộc cùng phiên bản JDK mong muốn hay không. `--release` điều khiển mục tiêu biên dịch, nhưng **không cài đặt JDK/runtime trên máy chủ**.

Một ứng dụng được biên dịch ra bytecode Java 24 cũng không chạy được trên runtime Java 17 hoặc 21 chỉ bằng cách điều chỉnh flags. Điều này độc lập với logic Gatherer.

## 5. API chính thức từ Java 24 gồm những gì?

Ba điểm vào quan trọng nằm trong `java.base`, package `java.util.stream`:

| Thành phần | Vai trò |
| --- | --- |
| `Stream.gather(Gatherer)` | Áp dụng một thao tác trung gian Gatherer cho pipeline |
| `Gatherer<T, A, R>` | Hợp đồng của một thao tác trung gian có thể có trạng thái, phát đầu ra và xử lý cuối nguồn |
| `Gatherers` | Các Gatherer dựng sẵn cho cửa sổ, tổng tích lũy, fold và ánh xạ đồng thời |

Các factory quan trọng của `Gatherers` trên Java 24:

| Factory | Kết quả | Bài toán |
| --- | --- | --- |
| `windowFixed(k)` | `Stream<List<T>>` gồm các lô không chồng lấn | Gom mỗi `k` phần tử, kể cả lô cuối ngắn |
| `windowSliding(k)` | `Stream<List<T>>` gồm các cửa sổ trượt | Theo dõi `k` phần tử gần nhất |
| `scan(initial, scanner)` | Phát **kết quả tích lũy sau từng phần tử** | Running total, prefix scan |
| `fold(initial, folder)` | Phát **một kết quả** sau khi giảm toàn bộ nguồn | Gom về một giá trị với quy tắc có trạng thái/thứ tự |
| `mapConcurrent(maxConcurrency, mapper)` | Ánh xạ với mức đồng thời giới hạn và giữ thứ tự kết quả | Các công việc có thể thực hiện song song bằng virtual threads |

Java 24 có thêm các phương thức hỗ trợ định nghĩa Gatherer tùy chỉnh, như `Gatherer.of(...)`, `Gatherer.ofSequential(...)`, `Gatherer.Integrator`, `Gatherer.Downstream` và `Gatherer.andThen(...)`.

### 5.1. `Gatherer` không thay thế `Collector`

Ví dụ:

```text
Stream<Order>
   |
   +-- filter(...)     : chọn phần tử
   |
   +-- map(...)        : biến đổi từng phần tử
   |
   +-- gather(...)     : thao tác TRUNG GIAN tùy chỉnh
   |                     có thể nhận nhiều phần tử,
   |                     duy trì trạng thái và phát nhiều kết quả
   |
   +-- collect(...)    : TERMINAL operation tổng hợp kết quả cuối
   v
Report
```

`Collector` (đã có từ Java 8) là cơ chế thu thập ở **cuối pipeline**. `Gatherer` (preview 22/23, chính thức 24) mở rộng danh mục **thao tác trung gian**. Một Gatherer có thể tạo ra `Stream<List<Order>>` trước khi một collector nhóm hoặc tổng hợp các chỉ số.

Không nên thay `reduce` hoặc `collect` bằng custom Gatherer khi công cụ có sẵn đã diễn đạt trực tiếp kết quả và đơn giản hơn.

## 6. Ví dụ Java 24 hoàn chỉnh: hai loại cửa sổ và tổng chạy

Chương trình sau biên dịch bằng **JDK 24** mà không bật preview:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GatherersFinalDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(10, 20, 30, 40, 50);

        List<List<Integer>> fixed = numbers.stream()
            .gather(Gatherers.windowFixed(3))
            .toList();

        List<List<Integer>> sliding = numbers.stream()
            .gather(Gatherers.windowSliding(3))
            .toList();

        List<Long> running = numbers.stream()
            .map(Integer::longValue)
            .gather(Gatherers.scan(
                () -> 0L,
                Long::sum
            ))
            .toList();

        String combined = Stream.of("A", "B", "C")
            .gather(Gatherers.fold(
                () -> "",
                String::concat
            ))
            .findFirst()
            .orElseThrow();

        System.out.println("fixed = " + fixed);
        System.out.println("sliding = " + sliding);
        System.out.println("running = " + running);
        System.out.println("fold = " + combined);
    }
}
```

Kết quả:

```text
fixed = [[10, 20, 30], [40, 50]]
sliding = [[10, 20, 30], [20, 30, 40], [30, 40, 50]]
running = [10, 30, 60, 100, 150]
fold = ABC
```

Chạy:

```bash
javac --release 24 GatherersFinalDemo.java
java GatherersFinalDemo
```

Ví dụ cho thấy:

- `windowFixed(3)` có lô cuối **ít hơn ba phần tử**.
- `windowSliding(3)` tạo các cửa sổ chồng lấn theo encounter order.
- `scan` phát giá trị tích lũy **sau mỗi phần tử**; nó không loại phần tử cũ khỏi tổng như cửa sổ trượt.
- `fold` tạo một kết quả từ toàn bộ nguồn, khác với `scan` phát chuỗi kết quả trung gian.
- Mỗi lời gọi `numbers.stream()` tạo một Stream mới vì một Stream đã đi qua terminal operation **không sử dụng lại được**.

Các quy tắc dữ liệu và phiên bản JDK là hai chuyện riêng: khi chuyển từ preview sang final, vẫn phải kiểm thử giá trị đầu ra, xử lý nguồn rỗng và thứ tự.

## 7. Các trường hợp biên quan trọng của cửa sổ

Đặc tả Java 24 có các quy tắc cụ thể cần đưa vào test. Với `k = 3`:

| Dữ liệu đầu vào | `windowFixed(3)` | `windowSliding(3)` |
| --- | --- | --- |
| `[]` | `[]` | `[]` |
| `[1]` | `[[1]]` | `[[1]]` |
| `[1,2]` | `[[1,2]]` | `[[1,2]]` |
| `[1,2,3]` | `[[1,2,3]]` | `[[1,2,3]]` |
| `[1,2,3,4]` | `[[1,2,3],[4]]` | `[[1,2,3],[2,3,4]]` |
| `[1,2,3,4,5]` | `[[1,2,3],[4,5]]` | `[[1,2,3],[2,3,4],[3,4,5]]` |

Hai factory đều yêu cầu kích thước dương; truyền `k < 1` gây `IllegalArgumentException`.

Trên nguồn có thứ tự:

- `windowFixed(k)` phát cửa sổ cuối ngắn nếu tổng số phần tử không chia hết cho `k`.
- `windowSliding(k)` với `0 < N < k` phát **một** cửa sổ ngắn chứa toàn bộ nguồn.
- Khi `N >= k`, `windowSliding(k)` phát `N-k+1` cửa sổ đầy đủ.
- Mỗi danh sách cửa sổ của các factory chuẩn là **không thể sửa**, không nên gọi `add` hoặc `remove`.

Đây là ngữ nghĩa của API, không phải đặc điểm riêng của giai đoạn preview. Nếu ứng dụng yêu cầu chỉ xử lý các cửa sổ đủ kích thước, hãy bổ sung điều kiện nghiệp vụ:

```java
List<List<Integer>> fullWindows = Stream.of(1, 2)
    .gather(Gatherers.windowSliding(3))
    .filter(window -> window.size() == 3)
    .toList();

System.out.println(fullWindows); // []
```

## 8. Custom Gatherer trên Java 24: cách đọc hợp đồng

Một `Gatherer<T, A, R>` có ba kiểu:

- **`T`**: kiểu phần tử đầu vào.
- **`A`**: kiểu trạng thái tích lũy bên trong (*state*).
- **`R`**: kiểu phần tử được phát ra downstream.

Các vai trò thường gặp:

| Thành phần | Mục đích |
| --- | --- |
| `initializer` | Tạo trạng thái mới cho một lượt tích lũy |
| `integrator` | Nhận phần tử, cập nhật trạng thái và có thể phát kết quả |
| `combiner` | Ghép trạng thái các nhánh nếu Gatherer được thiết kế để parallelize |
| `finisher` | Phát kết quả bổ sung ở cuối nguồn nếu cần |

Trong các tình huống chỉ có một trạng thái **phụ thuộc thứ tự**, thường bắt đầu với `Gatherer.ofSequential(...)`. Nếu muốn Gatherer có thể phân chia song song, cần **một combiner hợp lệ**, không chỉ thêm `parallel()` bên ngoài.

### 8.1. Ví dụ custom Gatherer phát tổng sau từng phần tử

```java
import java.util.List;
import java.util.stream.Gatherer;

public class CustomGatherer24Demo {

    static Gatherer<Integer, int[], Integer> runningSum() {
        return Gatherer.<Integer, int[], Integer>ofSequential(
            () -> new int[] {0},
            (state, value, downstream) -> {
                state[0] = Math.addExact(state[0], value);
                return downstream.push(state[0]);
            }
        );
    }

    public static void main(String[] args) {
        List<Integer> output = List.of(3, 5, 7)
            .stream()
            .gather(runningSum())
            .toList();

        System.out.println(output); // [3, 8, 15]
    }
}
```

Ví dụ có chủ đích dùng `int[]` làm trạng thái mutable nội bộ để thấy rõ vai trò của `initializer` và `integrator`. Trạng thái **không được lưu vào biến static dùng chung** giữa các lượt xử lý.

Trong nghiệp vụ chỉ cần tổng chạy thông thường, `Gatherers.scan(() -> 0, Integer::sum)` thường ngắn và dễ bảo trì hơn. Custom Gatherer có ích khi phép chuyển đổi hoặc quy tắc dừng/phát kết quả không được mô tả trực tiếp bởi factory sẵn có.

### 8.2. Tại sao mã custom cần được kiểm tra lại khi nâng JDK?

Bản preview cung cấp hợp đồng và công cụ để xây Gatherer, nhưng chi tiết API có thể được hoàn thiện qua các vòng preview. Vì thế khi chuyển lên Java 24 cần:

1. Đọc lại chữ ký trong Java 24 `Gatherer`/`Gatherer.Integrator`.
2. Kiểm tra có dùng initializer/combiner/finisher theo hợp đồng mới hay không.
3. Đảm bảo integrator tôn trọng tín hiệu `downstream.push(...)` trả về.
4. So sánh kết quả tuần tự/song song và trường hợp short-circuit.
5. Dùng `ofSequential` khi thao tác không có combiner đúng.

Việc mã dùng `Gatherers.windowFixed(3)` vẫn gần như y hệt qua các bản JDK **không bảo đảm** tất cả custom Gatherer đã viết lúc preview đều có hành vi đúng mà không cần thử lại.

## 9. Có thể giữ Java 17/21 mà dùng Gatherer chính thức không?

**Không thể gọi trực tiếp Stream Gatherers chuẩn trên Java 17/21.** Cả `java.util.stream.Gatherer`, `Gatherers` và `Stream.gather` đều không thuộc API của những bản phát hành đó. Bật `--enable-preview` không làm chúng xuất hiện.

Nếu hệ thống buộc phải hỗ trợ Java 17/21, có các hướng thiết kế:

| Hướng | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Tiếp tục dùng `filter/map/reduce/collect` | Tương thích JDK cũ, ít thay đổi | Một số biến đổi có trạng thái khó biểu diễn |
| Dùng vòng lặp, `Iterator` hoặc `Spliterator` tự viết | Chủ động quản lý cửa sổ/trạng thái | Phải tự kiểm thử edge cases và tài nguyên |
| Tách một mô-đun yêu cầu Java 24+ | Cho phép dùng Gatherer chính thức trong phần mới | Có yêu cầu triển khai/runtime riêng |
| Nâng minimum supported JDK lên 24+ | Dùng API chính thức trực tiếp | Ảnh hưởng máy chủ, CI, thư viện và vận hành |
| Sử dụng thư viện bên ngoài cung cấp cơ chế tương đương | Có thể giảm công viết tay | Không đồng nhất với `java.util.stream.Gatherer` chuẩn, phụ thuộc nhà cung cấp |

Đừng gọi API của một thư viện hỗ trợ khác là “chính là Java 24 Gatherer” nếu hợp đồng của thư viện chỉ mô phỏng ý tưởng. Tên gần giống không tạo tương thích kiểu hoặc hành vi tự động.

### 9.1. Ví dụ thay `windowFixed` bằng vòng lặp trên Java 17

Với dữ liệu đã nằm trong `List`, có thể gom thành nhóm không chồng lấn bằng code tương thích Java 17:

```java
import java.util.ArrayList;
import java.util.List;

public class FixedWindows17 {
    static <T> List<List<T>> fixedWindows(List<T> data, int width) {
        if (width < 1) {
            throw new IllegalArgumentException("width must be >= 1");
        }

        List<List<T>> result = new ArrayList<>();

        for (int start = 0; start < data.size();) {
            int end = start + Math.min(width, data.size() - start);

            result.add(List.copyOf(data.subList(start, end)));
            start = end;
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println(fixedWindows(
            List.of(1, 2, 3, 4, 5), 3
        )); // [[1, 2, 3], [4, 5]]
    }
}
```

Đây là **giải pháp tương đương theo kết quả cho nguồn `List` hữu hạn**, không phải phiên bản `Gatherer` của Java 17. Cách làm vật hóa toàn bộ danh sách cửa sổ và không tự trở thành intermediate operation lazy.

**Lưu ý độ an toàn số học:** Ví dụ tính cận cuối bằng `start + Math.min(width, data.size() - start)` để tránh cộng một `width` quá lớn rồi tràn `int`; đồng thời dùng `start = end` để luôn tiến về phía trước. Với chương trình ứng dụng thực, cần kiểm tra kích thước đầu vào, kiểu dữ liệu và trường hợp chứa `null`; `List.copyOf` không chấp nhận phần tử `null`.

### 9.2. Ví dụ thay `windowSliding` bằng vòng lặp trên Java 17

```java
import java.util.ArrayList;
import java.util.List;

public class SlidingWindows17 {
    static <T> List<List<T>> slidingWindows(List<T> data, int width) {
        if (width < 1) {
            throw new IllegalArgumentException("width must be >= 1");
        }

        if (data.isEmpty()) {
            return List.of();
        }

        if (data.size() < width) {
            return List.of(List.copyOf(data));
        }

        List<List<T>> result = new ArrayList<>();

        for (int start = 0; start <= data.size() - width; start++) {
            result.add(List.copyOf(
                data.subList(start, start + width)
            ));
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println(slidingWindows(
            List.of(1, 2, 3, 4, 5), 3
        )); // [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
    }
}
```

Bản thay thế này mô phỏng **ngữ nghĩa đầu ra** của `windowSliding` với nguồn hữu hạn, có thứ tự, không chứa `null`. Nó **không** mang tất cả bảo đảm về laziness, short-circuiting, xử lý song song hoặc loại danh sách triển khai của Gatherer chuẩn. Điều đó phải được ghi rõ trong tài liệu tương thích.

## 10. Chiến lược nâng cấp dự án từ preview sang Java 24

Khi dự án đã thử Stream Gatherers ở Java 22 hoặc 23, không nên xem nâng cấp như việc “xóa một flag” đơn lẻ. Có ba lớp công việc:

### 10.1. Cập nhật toolchain và runtime

- Chọn JDK 24 hoặc bản JDK mới hơn có Gatherer chính thức và phù hợp chính sách hỗ trợ của dự án.
- Kiểm tra phiên bản thực của `javac`, `java`, IDE và CI.
- Cập nhật cấu hình `--release` hoặc Java toolchain theo phiên bản đích.
- Bỏ flag `--enable-preview` **nếu không còn dùng tính năng preview khác**.
- Đảm bảo server, container và image deploy chạy một runtime đáp ứng version target.

Nếu môi trường CI vẫn dùng JDK 23 trong khi máy phát triển dùng JDK 24, việc mã chạy cục bộ không chứng minh bản build trên CI sẽ thành công.

### 10.2. Biên dịch lại và xử lý API

- Biên dịch sạch thay vì dùng class file hoặc JAR đã tạo bởi compiler preview cũ.
- Kiểm tra import `java.util.stream.Gatherer` và `java.util.stream.Gatherers`.
- Kiểm tra overload `Gatherer.of`/`ofSequential` và kiểu của các lambda.
- Loại bỏ code workaround chỉ còn cần thiết cho preview nếu đã có API chính thức thay thế.
- So sánh API mục tiêu với bản preview nếu ứng dụng tự cài đặt Gatherer nhiều trạng thái.

Không sửa mã chỉ để “đúng cú pháp” mà bỏ qua điều kiện phải giữ hành vi cũ cho nghiệp vụ.

### 10.3. Kiểm thử ngữ nghĩa và hiệu năng

Các test quan trọng:

1. Stream rỗng và nguồn chỉ có một phần tử.
2. Kích thước nguồn nhỏ hơn, bằng, lớn hơn `windowSize`.
3. `windowFixed` có lô cuối thiếu phần tử.
4. `windowSliding` với cửa sổ chồng lấn và encounter order.
5. Integrator có điều kiện dừng sớm, downstream ngừng nhận.
6. Tác dụng phụ, trạng thái chia sẻ và hoạt động song song.
7. Nguồn `Files.lines` hoặc cursor I/O có trách nhiệm đóng rõ ràng.
8. Số học tràn và sai số dấu phẩy động.
9. Chi phí cấp phát bộ nhớ cho cửa sổ lớn và throughput khi chạy thật.

**Tình trạng final của API không thay thế kiểm thử phần mềm.**

## 11. Cấu hình Maven và Gradle: phải phản ánh đúng JDK đích

Không chạy build trong bước soạn bài này; các đoạn dưới đây chỉ minh họa cách cấu hình một dự án Java khi chuyển sang Gatherer chính thức.

### 11.1. Maven — mục tiêu Java 24

Trong `pom.xml`:

```xml
<properties>
    <maven.compiler.release>24</maven.compiler.release>
</properties>
```

Phải dùng một Maven runtime/compiler hoặc toolchain có **JDK hỗ trợ Java 24**. Thuộc tính `maven.compiler.release` không tự cài JDK 24. Các phiên bản plugin Maven Compiler và cấu hình toolchain cũng cần phù hợp môi trường.

Nếu trước đây sử dụng các flag preview cho JDK 23, hãy rà lại cấu hình cả **compiler, test runner, JVM của IDE và môi trường deploy**. Không giữ `--enable-preview` một cách máy móc nếu dự án đã chuyển hoàn toàn sang các API chính thức.

### 11.2. Gradle — Java toolchain 24

Ví dụ bằng Gradle Groovy DSL:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 24
}
```

Phiên bản Gradle đang dùng phải hỗ trợ toolchain Java đã chọn. Cần bảo đảm JDK phù hợp có sẵn hoặc được cấu hình tải qua cơ chế toolchain.

**Lưu ý:** `toolchain` chọn trình biên dịch/runtime cho tác vụ build, còn `options.release` hạn chế API/bytecode mục tiêu. Thiết lập `release = 21` trên công cụ JDK 24 **không** cho phép tham chiếu các API Stream Gatherers của Java 24 trong đoạn mã được biên dịch với release 21.

### 11.3. Nếu vẫn phải xây cho Java 22/23 preview

Các hệ thống build tương ứng phải truyền đúng `--enable-preview` vào compiler **và** JVM thực thi bài test/ứng dụng trên chính phiên bản JDK preview đó. Không nên copy đoạn cấu hình preview từ Java 22 sang môi trường Java 24 mà không rà lại toàn bộ flags.

## 12. Khi cần một mã nguồn hỗ trợ nhiều JDK

Giả sử thư viện có khách hàng dùng Java 17 và khách hàng dùng Java 24. Có hai yêu cầu khác nhau:

- **Khả năng chạy trên Java 17:** phần code được nạp ở runtime Java 17 không được yêu cầu API vắng mặt.
- **Khả năng tận dụng Gatherer trên Java 24:** có thể cung cấp một implementation mới ở module/biến thể phù hợp.

Một kiến trúc tương đối rõ ràng:

```text
API nghiệp vụ chung
      |
      +-- Implementation Java 17
      |      vòng lặp, Iterator hoặc Stream/Collector có sẵn
      |
      +-- Implementation Java 24+
             Stream.gather / Gatherers chính thức
```

Dùng test chung để so sánh kết quả hai implementation. Có thể đóng gói thành các artifact riêng và chọn dependency theo runtime hỗ trợ, hoặc cân nhắc cấu trúc phát hành nâng cao nếu đội ngũ thật sự có nhu cầu.

**Đừng chỉ biên dịch JAR trên JDK 24 rồi tuyên bố “hỗ trợ Java 17”** nếu các class bắt buộc có liên kết tới `Stream.gather` hoặc `Gatherers`. Việc bytecode được target xuống phiên bản thấp nhưng sử dụng API mới cũng không được giải quyết bằng tùy chọn `--release`.

Nếu dùng reflection để dò API mới, cần thiết kế rất kỹ thời điểm liên kết/nạp class, kiểu dữ liệu ở public API và cách fallback; reflection không tự biến một chương trình yêu cầu Java 24 thành tương thích Java 17. Với dự án học tập hoặc ứng dụng thông thường, hai implementation rõ ràng thường dễ bảo trì hơn.

## 13. `mapConcurrent` trong Gatherers khác với `parallelStream`

`Gatherers.mapConcurrent(maxConcurrency, mapper)` là một Gatherer dựng sẵn sử dụng **virtual threads** để thực hiện mapper đồng thời tới giới hạn được chỉ định. Nó cố gắng bảo toàn **thứ tự kết quả** của Stream.

```java
import java.util.List;
import java.util.stream.Gatherers;

public class ConcurrentGatherer24Demo {
    public static void main(String[] args) {
        List<Integer> lengths = List.of("A", "Java", "Stream")
            .stream()
            .gather(Gatherers.mapConcurrent(
                3,
                String::length
            ))
            .toList();

        System.out.println(lengths); // [1, 4, 6]
    }
}
```

Điều này khác với:

```java
List<Integer> lengths = List.of("A", "Java", "Stream")
    .parallelStream()
    .map(String::length)
    .toList();
```

Hai cách có thể cho **cùng kết quả** trong ví dụ, nhưng mô hình lập lịch, giới hạn đồng thời và tác động hiệu năng **không đồng nhất**.

- `mapConcurrent` có tham số giới hạn `maxConcurrency` và sử dụng virtual threads theo hợp đồng API.
- `parallelStream` sử dụng cơ chế thực thi song song của Stream, không có tham số `maxConcurrency` tương đương ngay trong `parallel()`.
- Giữ thứ tự đầu ra **không có nghĩa** các tác vụ con thực thi theo thứ tự tuần tự.
- Mỗi mapper vẫn phải có hợp đồng an toàn cho trạng thái, ngoại lệ, I/O và tài nguyên.
- Không mặc định rằng tăng concurrency luôn nhanh, đặc biệt với tải CPU-bound hoặc khi hệ thống đích có giới hạn kết nối.

Một chương trình chuyển từ preview sang Java 24 nên đo lại `mapConcurrent` trên tải đại diện, không chỉ nhìn kết quả của ví dụ nhỏ.

## 14. Gatherer, trạng thái và xử lý song song

Bản final không loại bỏ các quy tắc nền tảng của Stream:

- **Non-interference:** không sửa nguồn trong khi pipeline đang duyệt, trừ trường hợp nguồn hỗ trợ theo hợp đồng.
- **Stateless behavior:** với `map`, `filter` và nhiều lambda xử lý phần tử, tránh phụ thuộc trạng thái mutable bên ngoài.
- **Confinement:** trạng thái nội bộ của một Gatherer tuần tự không được biến thành biến global có nhiều pipeline cùng sửa.
- **Combiner correctness:** nếu tự thiết kế Gatherer có thể song song, combiner phải hợp nhất trạng thái đúng theo thứ tự và ý nghĩa nghiệp vụ.
- **Short-circuit:** một terminal operation như `findFirst` hoặc `limit` có thể không yêu cầu toàn bộ phần tử đầu vào.

Ví dụ nên tránh:

```java
// Không nên làm: dùng List mutable bên ngoài để thu mọi kết quả.
List<Integer> shared = new java.util.ArrayList<>();

Stream.of(1, 2, 3, 4)
    .parallel()
    .gather(Gatherers.scan(() -> 0, Integer::sum))
    .forEach(shared::add);
```

`ArrayList` không an toàn cho nhiều luồng cùng ghi; thêm nữa, `forEach` trên Stream song song không bảo đảm encounter order của side effect. Cách phù hợp là:

```java
List<Integer> running = Stream.of(1, 2, 3, 4)
    .gather(Gatherers.scan(() -> 0, Integer::sum))
    .toList();

System.out.println(running); // [1, 3, 6, 10]
```

Một phần có thể được xử lý tuần tự do đặc tính của Gatherer. Điều đó **không nên được dùng** để biện hộ cho side effect vào trạng thái ngoài pipeline: khi thay đổi implementation hoặc loại Gatherer, lỗi có thể xuất hiện trở lại.

## 15. Tài nguyên I/O và tính lazy không thay đổi vì API đã final

`Stream.gather(...)` là intermediate operation. Nếu nguồn là `Files.lines(path)`, tài nguyên tệp vẫn phải được đóng ở đúng phạm vi sở hữu, kể cả khi chương trình chạy Java 24.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FileGatherer24Demo {
    public static List<List<String>> readBatches(Path path)
            throws IOException {
        try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                .filter(line -> !line.isBlank())
                .gather(Gatherers.windowFixed(100))
                .toList();
        }
    }
}
```

**Lưu ý:**

- `try-with-resources` đóng `Files.lines` khi thoát khối, kể cả khi `map`/`filter`/terminal operation ném ngoại lệ.
- `gather` và `toList()` không tự thay `close()` cho nguồn I/O.
- `toList()` lưu toàn bộ cửa sổ kết quả, có thể gây tốn bộ nhớ nếu tệp rất lớn.
- `filter` trước `gather` làm thay đổi cách các phần tử được phân chia cửa sổ. Nếu mục tiêu là nhóm **100 dòng gốc** thay vì 100 dòng không trống, phải đổi thứ tự thao tác.

Trong ứng dụng vừa nâng từ preview, cần kiểm tra thêm các nguồn I/O tự viết, close handlers và behavior khi dừng sớm. Việc chuẩn hóa API không làm cho tài nguyên tự được giải phóng.

## 16. Bộ kiểm tra tương thích tối thiểu trước khi phát hành

Một ma trận kiểm thử giúp tránh nhầm “compile được trên một máy” với “sản phẩm hỗ trợ đúng bản JDK”.

| Hạng mục | JDK 22 preview | JDK 23 preview | JDK 24 final |
| --- | --- | --- | --- |
| Dùng đúng JDK compiler | Kiểm tra | Kiểm tra | Kiểm tra |
| Bật preview khi biên dịch | **Có** | **Có** | **Không** cho Gatherer |
| Bật preview khi chạy | **Có** | **Có** | **Không** cho Gatherer |
| Kiểm tra `windowFixed`/`windowSliding` | Có | Có | Có |
| Kiểm tra custom `Gatherer` | Theo JDK 22 | Theo JDK 23 | Theo JDK 24 |
| Kiểm tra input rỗng/thiếu mẫu | Có | Có | Có |
| Kiểm tra thứ tự và parallel behavior | Có | Có | Có |
| Kiểm tra cleanup nguồn I/O | Có | Có | Có |
| Kiểm tra artifact build mới, không dùng class preview cũ | Có | Có | Có |

### 16.1. Bộ test minh họa trên JDK 24

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GathererContractCheck24 {
    public static void main(String[] args) {
        var fixed = Stream.of(1, 2, 3, 4, 5)
            .gather(Gatherers.windowFixed(3))
            .toList();

        var sliding = Stream.of(1, 2, 3, 4, 5)
            .gather(Gatherers.windowSliding(3))
            .toList();

        var shortInput = Stream.of(1, 2)
            .gather(Gatherers.windowSliding(3))
            .toList();

        var empty = Stream.<Integer>empty()
            .gather(Gatherers.windowFixed(3))
            .toList();

        if (!fixed.equals(List.of(
                List.of(1, 2, 3),
                List.of(4, 5)))) {
            throw new AssertionError("fixed windows mismatch");
        }

        if (!sliding.equals(List.of(
                List.of(1, 2, 3),
                List.of(2, 3, 4),
                List.of(3, 4, 5)))) {
            throw new AssertionError("sliding windows mismatch");
        }

        if (!shortInput.equals(List.of(List.of(1, 2)))) {
            throw new AssertionError("short input mismatch");
        }

        if (!empty.isEmpty()) {
            throw new AssertionError("empty stream mismatch");
        }

        System.out.println("Gatherer contract checks passed");
    }
}
```

Các assertion kiểm tra **ngữ nghĩa công khai** của các Gatherer dựng sẵn. Không kiểm tra tên lớp nội bộ hoặc số lần gọi integrator, vì việc triển khai có quyền tối ưu pipeline.

### 16.2. Quy tắc đối chiếu kết quả giữa hai implementation

Nếu duy trì đồng thời fallback Java 17 và Gatherer Java 24:

1. Kiểm tra cùng một bộ dữ liệu đầu vào có thứ tự.
2. Kiểm tra cùng kích thước cửa sổ và cùng quy tắc với phần cuối ngắn.
3. So sánh **danh sách kết quả**, không so sánh tên lớp Map/List cụ thể.
4. Kiểm tra cả giá trị `null` hoặc trường hợp đầu vào không hợp lệ theo hợp đồng mỗi implementation.
5. Kiểm tra việc tiêu thụ bộ nhớ và lượng dữ liệu được vật hóa.
6. Chỉ kết luận tương đương nếu các điều kiện nghiệp vụ thật sự giống nhau.

Một fallback dùng vòng lặp trên `List` có thể cho kết quả giống Gatherer trên dữ liệu mẫu nhưng khác về tính lazy và xử lý nguồn vô hạn. **Tương đương kết quả trên tập hữu hạn không đồng nghĩa tương đương mọi đặc tính API.**

## 17. Bảng lỗi thường gặp khi di chuyển giữa các JDK

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `cannot find symbol: Gatherers` trên JDK 17/21 | API chưa tồn tại | Nâng JDK hoặc dùng giải pháp thay thế |
| Compiler nói Gatherer là preview API | Dùng JDK 22/23 nhưng chưa bật preview | Bật `--enable-preview` và release đúng cùng JDK |
| Chạy trên JDK 22/23 báo preview bị tắt | Runtime chưa bật preview hoặc build sai cấu hình | Chạy `java --enable-preview` trên đúng JDK |
| Cố biên dịch preview 22 bằng JDK 23 với `--release 22` | Preview gắn với bản JDK hiện hành | Biên dịch bằng đúng JDK 22 hoặc nâng target lên 23 và kiểm thử |
| Java 24 vẫn mang flag preview cũ khắp CI/test | Cấu hình chưa dọn sạch hoặc còn dùng preview khác | Rà từng tính năng và chỉ giữ flag khi thật sự cần |
| Biên dịch `--release 21` mà dùng `Stream.gather` | API Java 24 không thuộc release 21 | Nâng target hoặc tách implementation |
| Build chạy ở IDE nhưng CI thất bại | JDK/toolchain khác nhau | Khóa và kiểm tra toolchain ở mọi môi trường |
| Artifact tạo bằng preview cũ gặp lỗi khi nâng runtime | Không bảo đảm tương thích artifact preview xuyên JDK | Clean build và biên dịch lại ở JDK đích |
| `windowFixed(k)` còn cửa sổ ngắn cuối | Hợp đồng bình thường của API | Lọc cửa sổ đủ mẫu nếu bài toán yêu cầu |
| `windowSliding(k)` trên nguồn ngắn vẫn phát một cửa sổ | Hợp đồng bình thường của API | Chọn chính sách warm-up/full-window |
| Thử gọi `gather` trực tiếp trên `IntStream` | API `gather` ở `Stream<T>` đối tượng | Chuyển sang `boxed()` hoặc chọn thuật toán primitive phù hợp |
| Custom Gatherer tự sửa biến global | State sharing không an toàn | Dùng initializer tạo trạng thái riêng |
| Thêm `parallel()` rồi mặc định nhanh | Chi phí chia/gộp/trạng thái có thể lớn | Benchmark và kiểm tra thứ tự |
| Bỏ `close()` của nguồn tệp sau `gather` | Rò rỉ tài nguyên | Đóng bằng `try-with-resources` |
| Gọi API final và cho rằng nó tự “chuẩn hóa” dữ liệu | Nhầm ổn định API với tính đúng nghiệp vụ | Kiểm tra quy tắc lọc, trạng thái, kiểu số và kết quả |

### 17.1. Trường hợp Primitive Stream

`Stream.gather` được khai báo trên `Stream<T>` (đối tượng). Nếu có một `IntStream`, có thể chuyển sang `Stream<Integer>` để dùng Gatherer:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<List<Integer>> windows = IntStream.rangeClosed(1, 5)
    .boxed()
    .gather(Gatherers.windowFixed(2))
    .toList();

System.out.println(windows); // [[1, 2], [3, 4], [5]]
```

`boxed()` có thể tạo chi phí boxing; với khối lượng dữ liệu số rất lớn cần benchmark và cân nhắc giải pháp primitive tùy chỉnh nếu Gatherer thực sự là điểm nghẽn.

## 18. Bài tập thực hành

### Bài 1: Xác định trạng thái API

Hãy lập bảng cho Java 17, 21, 22, 23 và 24: có `Stream.gather` không, có cần bật preview không, nên dùng JEP nào làm tài liệu gốc? Giải thích vì sao Java 23 vẫn không được coi là bản final.

### Bài 2: Viết đúng lệnh CLI

Với `GathererVersionDemo.java`, viết lệnh compile/run ở JDK 22, JDK 23 và JDK 24. Giải thích vai trò khác nhau của `--enable-preview` và `--release`.

### Bài 3: Phát hiện lỗi tương thích ngược

Một thư viện build với JDK 24 và gọi `Gatherers.windowFixed` nhưng vẫn tuyên bố hỗ trợ runtime Java 17. Phân tích điểm mâu thuẫn và đề xuất hai chiến lược khắc phục.

### Bài 4: So sánh fallback

Viết vòng lặp Java 17 tạo cửa sổ cố định ba phần tử và so sánh đầu ra với `windowFixed(3)` trong Java 24. Thử `N=0`, `N=2`, `N=3`, `N=5`. Vì sao hai giải pháp vẫn có thể khác về laziness?

### Bài 5: Chính sách cửa sổ trượt

Với dữ liệu `[10, 20]` và `k=3`, `windowSliding` phát gì? Viết pipeline chỉ phát cửa sổ đầy đủ. Giải thích khi nào cho phép một chỉ số “warm-up” và khi nào phải chờ đủ mẫu.

### Bài 6: `scan` và `fold`

Dùng `Gatherers.scan` tạo tổng chạy của `[2, 3, 5]`. Dùng `Gatherers.fold` tạo một tổng cuối. Phân biệt số phần tử đầu ra và thời điểm phát kết quả; kiểm tra cả Stream rỗng.

### Bài 7: Custom Gatherer và trạng thái

Tạo `Gatherer.ofSequential` phát tổng sau mỗi phần tử. Vì sao trạng thái không được đặt trong một `int[]` static dùng chung? Khi nào cần một combiner để xử lý song song?

### Bài 8: Cấu hình CI

Giả sử máy dev dùng JDK 24, runner CI dùng JDK 23 và server dùng Java 21. Viết một kế hoạch nâng cấp có thứ tự: chọn target, điều chỉnh flags, nâng runtime, clean build và kiểm thử hồi quy.

### Bài 9: `mapConcurrent` và thứ tự

Trên Java 24, dùng `Gatherers.mapConcurrent` để ánh xạ danh sách chuỗi thành độ dài. So sánh kết quả với `parallelStream().map(...)`. Giải thích vì sao cùng kết quả không có nghĩa cùng mô hình concurrency hoặc cùng hiệu năng.

### Bài 10: Bản phát hành chính thức có thay logic nghiệp vụ không?

Giả sử một custom Gatherer preview dùng để tạo alert từ cửa sổ nhiệt độ. Sau khi nâng JDK 24 và bỏ `--enable-preview`, những kiểm thử nào vẫn cần thực hiện? Nhấn mạnh ngưỡng cảnh báo, dữ liệu rỗng, cửa sổ ngắn, nguồn không có thứ tự và ngoại lệ I/O.

## 19. Tự kiểm tra kiến thức

- Gatherers ra mắt preview ở JDK nào và được chuẩn hóa ở JDK nào?
- JEP 461, 473 và 485 tương ứng với ba giai đoạn gì?
- Vì sao `--enable-preview` cần thiết trên JDK 22/23 nhưng không cần cho Gatherers trên JDK 24?
- Vì sao bật preview ở JDK 21 không tạo ra `java.util.stream.Gatherers`?
- `--release 21` có cho phép dùng API Java 24 khi compiler chạy trên JDK 24 không?
- `Stream.gather` là intermediate hay terminal operation?
- `Gatherers.windowFixed` và `windowSliding` có xử lý nguồn ngắn giống nhau không?
- `Gatherers.scan` khác `Gatherers.fold` ở số lượng đầu ra như thế nào?
- Khi nào nên ưu tiên `Gatherer.ofSequential` thay vì tự khai báo combiner?
- Vì sao class file preview cũ cần được rebuild và kiểm thử lại khi nâng JDK?
- Có nên dùng một `ArrayList` global để nhận kết quả của Gatherer trong parallel Stream không?
- Vì sao `mapConcurrent` khác `parallelStream` dù cả hai có thể chạy nhiều tác vụ?
- Nếu ứng dụng phải hỗ trợ Java 17, có những lựa chọn nào ngoài việc nâng toàn bộ hệ thống?
- Tại sao API đã final không tự đảm bảo code chính xác, thread-safe hay hiệu năng cao?

## 20. Tài liệu tham khảo chính thức

1. [JEP 461 — Stream Gatherers (Preview)](https://openjdk.org/jeps/461): lần preview đầu tiên trong JDK 22.
2. [JEP 473 — Stream Gatherers (Second Preview)](https://openjdk.org/jeps/473): lần preview thứ hai trong JDK 23.
3. [JEP 485 — Stream Gatherers](https://openjdk.org/jeps/485): chuẩn hóa API trong JDK 24.
4. [Oracle Java SE 22 — Gatherers API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/stream/Gatherers.html): tài liệu đánh dấu preview và các factory trong JDK 22.
5. [Oracle Java SE 23 — Gatherers API](https://docs.oracle.com/en/java/javase/23/docs/api/java.base/java/util/stream/Gatherers.html): tài liệu API vẫn được đánh dấu preview.
6. [Oracle Java SE 24 — Gatherers API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html): các factory chính thức.
7. [Oracle Java SE 24 — Gatherer API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): hợp đồng initializer/integrator/combiner/finisher.
8. [Oracle Java SE 24 — Stream Gatherers Guide](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html): ví dụ và cách áp dụng Gatherer.
9. [Oracle Java SE 22 — Preview Features](https://docs.oracle.com/en/java/javase/22/language/preview-language-and-vm-features.html): quy tắc bật preview ở compiler và runtime.
10. [Oracle JDK 24 Release Notes](https://www.oracle.com/java/technologies/javase/24-relnote-issues.html): thông tin Stream Gatherers được đưa vào nhóm thư viện chuẩn.

**Ghi nhớ:** **Java 22 = preview (JEP 461), Java 23 = second preview (JEP 473), Java 24 = API chính thức (JEP 485).** Trên Java 22/23 phải bật preview khi biên dịch và chạy đúng JDK; trên Java 24 không cần flag này chỉ để dùng Gatherers. **API đã chính thức không có nghĩa mã chạy được trên JDK cũ, không loại bỏ trách nhiệm quản lý trạng thái/tài nguyên và không thay thế kiểm thử.** Khi nâng phiên bản, hãy chọn một toolchain nhất quán, clean build, xác minh runtime đích và kiểm tra đầy đủ ngữ nghĩa pipeline.
