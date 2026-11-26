# Gatherers.scan để tạo dãy kết quả tích lũy theo từng phần tử

`Gatherers.scan` tạo ra một pipeline tích lũy: với mỗi phần tử đầu vào, nó kết hợp phần tử đó với trạng thái tích lũy trước đó rồi phát ra trạng thái mới. Kết quả là một dãy các giá trị tiền tố (*prefix results*), thay vì chỉ một kết quả cuối cùng.

Ví dụ, từ dãy `1, 2, 3, 4` và phép cộng, `scan` tạo ra `1, 3, 6, 10`. Tính năng này hữu ích khi cần tính số dư sau từng giao dịch, tổng chạy, số lượng tích lũy hoặc trạng thái tiến triển qua từng sự kiện.

Stream Gatherers được giới thiệu ở dạng preview trong Java 22 và trở thành API chính thức từ JDK 24 theo JEP 485. Các ví dụ trong bài dùng API đã hoàn thiện trong `java.util.stream`, không cần bật preview trên JDK 24 trở lên.

## 1. Cú pháp và cách hoạt động

Phương thức có dạng:

```java
Gatherers.scan(Supplier<R> initial, BiFunction<? super R, ? super T, ? extends R> scanner)
```

Trong đó:

- `initial` cung cấp trạng thái tích lũy ban đầu kiểu `R`.
- `scanner` nhận trạng thái tích lũy trước đó và phần tử đầu vào kiểu `T`, sau đó trả về trạng thái mới kiểu `R`.
- Mỗi trạng thái mới được phát ra thành một phần tử của stream kết quả.

`scan` là một gatherer trung gian, được sử dụng với `Stream.gather(...)`. Nó không phát ra giá trị khởi tạo; phần tử đầu tiên được phát ra là kết quả của việc áp dụng `scanner` lên trạng thái ban đầu và phần tử đầu tiên của stream.

## 2. Ví dụ đơn giản: tổng tích lũy

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class RunningTotal {
    public static void main(String[] args) {
        List<Integer> totals = Stream.of(1, 2, 3, 4)
                .gather(Gatherers.scan(() -> 0, Integer::sum))
                .toList();

        System.out.println(totals);
    }
}
```

Kết quả:

```text
[1, 3, 6, 10]
```

Quá trình tích lũy diễn ra như sau:

| Phần tử đầu vào | Trạng thái trước đó | Phép tính | Kết quả được phát ra |
| ---: | ---: | --- | ---: |
| `1` | `0` | `0 + 1` | `1` |
| `2` | `1` | `1 + 2` | `3` |
| `3` | `3` | `3 + 3` | `6` |
| `4` | `6` | `6 + 4` | `10` |

Giá trị `0` chỉ là seed cho phép tính đầu tiên, không xuất hiện trong danh sách kết quả. Nếu stream đầu vào rỗng, không có trạng thái tích lũy nào được phát ra nên kết quả cũng rỗng.

## 3. Trạng thái tích lũy có kiểu khác phần tử đầu vào

Kiểu `T` của phần tử đầu vào không cần giống kiểu `R` của trạng thái tích lũy. Chẳng hạn, đầu vào là các khoản thanh toán, còn kết quả sau mỗi phần tử là số giao dịch và tổng tiền đã nhận.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

record Payment(String description, long amountInCents) {}
record Balance(int paymentCount, long totalInCents) {}

public class PaymentSummary {
    public static void main(String[] args) {
        List<Payment> payments = List.of(
                new Payment("Đơn hàng A", 125_00),
                new Payment("Đơn hàng B", 80_00),
                new Payment("Đơn hàng C", 45_00)
        );

        List<Balance> history = payments.stream()
                .gather(Gatherers.scan(
                        () -> new Balance(0, 0),
                        (balance, payment) -> new Balance(
                                balance.paymentCount() + 1,
                                balance.totalInCents() + payment.amountInCents()
                        )
                ))
                .toList();

        history.forEach(System.out::println);
    }
}
```

Kết quả:

```text
Balance[paymentCount=1, totalInCents=12500]
Balance[paymentCount=2, totalInCents=20500]
Balance[paymentCount=3, totalInCents=25000]
```

Ở đây, mỗi phần tử đầu vào là `Payment`, nhưng `scan` phát ra `Balance`. Trạng thái ban đầu là `Balance(0, 0)`; sau mỗi khoản thanh toán, scanner tạo một `Balance` mới chứa số giao dịch và tổng tiền đã cập nhật.

## 4. Vai trò của Supplier và vòng đời trạng thái

Tham số đầu tiên là `Supplier<R>`, không phải một đối tượng trạng thái được tạo sẵn. Supplier cung cấp trạng thái ban đầu khi gatherer được khởi tạo cho một lần xử lý stream. Vì vậy, nếu trạng thái là mutable object, hãy tạo đối tượng mới trong supplier thay vì dùng chung một instance bên ngoài. Ví dụ, `ArrayList<String>::new` tạo một danh sách mới mỗi khi supplier được gọi.

Tuy nhiên, việc trả về cùng một mutable object sau mỗi lần cập nhật có thể khiến mọi phần tử trong kết quả cùng tham chiếu tới một đối tượng đã bị thay đổi nhiều lần. Khi thu thập các trạng thái để dùng về sau, nên ưu tiên trạng thái bất biến hoặc tạo snapshot mới cho mỗi bước.

Ví dụ dưới đây tạo một danh sách mới ở mỗi bước:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<String>> history = Stream.of("A", "B", "C")
        .gather(Gatherers.scan(
                () -> List.<String>of(),
                (previous, current) -> {
                    List<String> next = new ArrayList<>(previous);
                    next.add(current);
                    return List.copyOf(next);
                }
        ))
        .toList();

System.out.println(history);
// [[A], [A, B], [A, B, C]]
```

Ví dụ này minh họa snapshot độc lập, nhưng mỗi bước phải sao chép danh sách trước đó nên chi phí tăng theo kích thước dữ liệu. Với dữ liệu lớn, hãy chọn một kiểu trạng thái phù hợp hơn, chẳng hạn record chứa các bộ đếm hoặc tổng số thay vì lưu toàn bộ lịch sử.

## 5. Dùng scan trong pipeline Stream

Vì `scan` là intermediate gatherer, có thể nối nó với các thao tác Stream khác trước hoặc sau `gather`.

Ví dụ, tính tổng chạy rồi chỉ lấy các mốc tổng lớn hơn 100:

```java
List<Integer> milestones = Stream.of(30, 40, 50, 20)
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .filter(total -> total > 100)
        .toList();

System.out.println(milestones); // [120, 140]
```

Có thể lọc đầu vào trước khi tích lũy:

```java
List<Integer> totals = Stream.of(10, -5, 20, -3, 8)
        .filter(amount -> amount > 0)
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList();

System.out.println(totals); // [10, 30, 38]
```

Vị trí của các thao tác có ý nghĩa. `filter` đặt trước `scan` làm cho phần tử bị loại không tham gia cập nhật trạng thái. Nếu đặt `filter` sau `scan`, mọi phần tử vẫn được tính vào trạng thái, nhưng một số trạng thái kết quả có thể bị loại khỏi stream đầu ra.

## 6. Phân biệt scan với reduce

Cả `scan` và `reduce` đều kết hợp nhiều phần tử bằng một phép tích lũy, nhưng chúng phục vụ mục đích khác nhau:

| Tiêu chí | `Gatherers.scan` | `Stream.reduce` |
| --- | --- | --- |
| Loại thao tác | Trung gian qua `gather` | Kết thúc stream |
| Kết quả | Một dãy trạng thái sau từng phần tử | Một kết quả tổng hợp cuối cùng |
| Có thể nối thao tác Stream tiếp theo | Có | Không, vì pipeline đã kết thúc |
| Trường hợp sử dụng | Số dư theo từng giao dịch, tổng chạy, trạng thái tiến triển | Tổng, tích hoặc một kết quả gộp duy nhất |

Ví dụ cùng phép cộng:

```java
Stream<Integer> values = Stream.of(1, 2, 3, 4);

List<Integer> prefixes = values.gather(
        Gatherers.scan(() -> 0, Integer::sum)
).toList();
// [1, 3, 6, 10]

int total = Stream.of(1, 2, 3, 4)
        .reduce(0, Integer::sum);
// 10
```

Chọn `scan` khi các trạng thái trung gian là một phần của dữ liệu cần xử lý. Chọn `reduce` khi chỉ cần kết quả cuối cùng.

## 7. Các lưu ý khi sử dụng

- **Seed không được phát ra:** `scan(() -> 0, ...)` với đầu vào `[1, 2]` tạo `[1, 3]`, không phải `[0, 1, 3]`. Nếu cần hiển thị seed, có thể nối seed vào kết quả một cách tường minh bằng pipeline khác.
- **Supplier tạo trạng thái ban đầu:** Không dùng supplier trả về một mutable instance dùng chung giữa nhiều lần xử lý.
- **Scanner nhận trạng thái trước và phần tử hiện tại:** Đừng nhầm thứ tự hai tham số; chữ ký là `(state, element)`, không phải `(element, state)`.
- **Ưu tiên trạng thái bất biến:** Trạng thái mới cho mỗi bước giúp kết quả đã phát ra không bị thay đổi ngoài ý muốn.
- **Encounter order:** Tổng chạy hoặc số dư theo từng phần tử phụ thuộc thứ tự đầu vào. Với dữ liệu có thứ tự nghiệp vụ, giữ nguồn có encounter order và không loại bỏ thứ tự trước khi gọi `scan`.
- **Không thay thế reduce trong mọi trường hợp:** `scan` tạo ra nhiều kết quả trung gian và có thể tốn bộ nhớ hơn nếu thu thập toàn bộ lịch sử.
- **Dùng API chính thức:** `Gatherers.scan` và `Stream.gather` là API ổn định từ JDK 24. Không cần `--enable-preview` trên JDK 24 trở lên.

## 8. Khi nào nên dùng Gatherers.scan?

Sử dụng `scan` khi mỗi bước xử lý cần biết trạng thái đã tích lũy đến thời điểm hiện tại, ví dụ:

- Tính số dư tài khoản sau từng giao dịch.
- Theo dõi tổng doanh thu hoặc số lượng đơn hàng theo thứ tự sự kiện.
- Tính số lượng phần tử đã xử lý đến từng vị trí.
- Xây dựng trạng thái tiến triển từ chuỗi sự kiện.
- Tạo các giá trị tiền tố để tiếp tục lọc, ánh xạ hoặc phân tích trong cùng pipeline.

Nếu chỉ cần một giá trị tổng hợp cuối cùng, `reduce` thường đơn giản hơn. Nếu cần phát ra một kết quả sau mỗi phần tử, `Gatherers.scan` diễn đạt đúng ý định và cho phép tiếp tục xử lý các trạng thái trung gian bằng Stream API.

## 9. Tài liệu tham khảo

- [JEP 485: Stream Gatherers](https://openjdk.org/jeps/485) — Stream Gatherers trở thành tính năng chính thức trong JDK 24.
- [Java SE 24 — Gatherers](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html) — tài liệu API cho `Gatherers.scan` và các gatherer dựng sẵn.
- [Java SE 24 — Stream.gather](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html#gather(java.util.stream.Gatherer)) — cách đưa gatherer vào pipeline Stream.
- [Java SE 22 — JEP 461: Stream Gatherers (Preview)](https://openjdk.org/jeps/461) — bối cảnh giới thiệu Stream Gatherers trong Java 22.
