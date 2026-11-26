# Chiến lược chờ mọi kết quả, thất bại sớm và lấy kết quả thành công phù hợp

## 1. Chọn chính sách theo điều kiện hoàn thành của công việc

Structured Concurrency nhóm các tác vụ liên quan vào một phạm vi có chủ sở hữu và vòng đời chung. Khi tách một công việc thành nhiều tác vụ con, cần xác định **bao nhiêu kết quả và loại kết quả nào đủ để kết luận công việc cha**.

Có ba nhu cầu thường gặp:

1. Thu thập kết quả của mọi tác vụ, kể cả kết quả thất bại.
2. Yêu cầu tất cả tác vụ bắt buộc thành công; nếu có lỗi thì kết luận thất bại sớm.
3. Chỉ cần một kết quả thành công đáp ứng điều kiện nghiệp vụ; các ứng viên còn lại có thể hủy.

Đây là kiến thức còn hữu ích khi học các tính năng có mặt ở Java 22. Tuy nhiên, Structured Concurrency trong Java 22 là API preview; API đã tiếp tục thay đổi. **Các ví dụ trong bài dùng JDK 27**, nơi tính năng vẫn là preview lần thứ bảy tại thời điểm đối chiếu 25/11/2026. Không ghép các ví dụ này với cú pháp preview cũ hoặc biên dịch chúng bằng JDK 22. Xem [API Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html) và [ghi chú phát hành JDK 27](https://www.oracle.com/java/technologies/javase/27all-relnotes.html).

Trong JDK 27, mở scope bằng `StructuredTaskScope.open(...)` và chọn chính sách qua `Joiner`. Bài tập trung vào cách ra quyết định và API hiện đại tương ứng, thay vì hướng dẫn những dạng API preview đã được thay thế.

## 2. So sánh ba chiến lược

| Chiến lược | Cần chờ tới khi nào? | Gặp một tác vụ lỗi | Đã có một kết quả thành công | Ví dụ nhu cầu |
| --- | --- | --- | --- | --- |
| Chờ mọi kết quả | Mọi tác vụ đã hoàn tất, trừ khi bị hủy hoặc hết ngân sách thời gian | Ghi nhận lỗi và tiếp tục chờ các tác vụ khác | Vẫn chờ các kết quả còn lại | Báo cáo trạng thái nhiều dịch vụ |
| Thất bại sớm | Tất cả thành công hoặc xuất hiện một thất bại đủ để kết luận | Hủy phần công việc không còn cần thiết | Chưa đủ nếu còn dữ liệu bắt buộc | Ghép hồ sơ và tồn kho bắt buộc |
| Một thành công phù hợp | Có một kết quả đạt yêu cầu hoặc không còn ứng viên có thể thành công | Tiếp tục chờ ứng viên khác | Có thể hủy phần còn lại nếu kết quả đạt yêu cầu | Đọc từ các bản sao tương đương |

Các ánh xạ chính trong **JDK 27**:

| Nhu cầu API | Joiner | Giá trị của `join()` |
| --- | --- | --- |
| Thu mọi kết cục, không dừng vì một tác vụ lỗi | `Joiner.<T>allUntil(task -> false)` | `List<Subtask<T>>` để xem từng trạng thái |
| Tất cả thành công, lấy danh sách kết quả cùng kiểu | `Joiner.<T>allSuccessfulOrThrow()` | `List<T>` |
| Tất cả thành công, giữ riêng các handle kết quả | `Joiner.awaitAllSuccessfulOrThrow()` | `null`; đọc các `Subtask` sau khi join thành công |
| Chỉ cần một thành công | `Joiner.<T>anySuccessfulOrThrow()` | Một kết quả kiểu `T` |

Đặc tả [Joiner của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html) là nguồn đối chiếu tên phương thức và kiểu trả về. Đặc biệt, ví dụ `allSuccessfulOrThrow()` trong bài trả về danh sách giá trị, không dùng kiểu trả về của các vòng preview trước.

### 2.1. Cùng một tập tác vụ, chính sách khác nhau cho kết luận khác nhau

Giả sử các tác vụ gần như bắt đầu cùng lúc và diễn biến như sau:

```text
A: sau khoảng 40 ms  -> lỗi
B: sau khoảng 100 ms -> thành công
C: sau khoảng 300 ms -> thành công
```

- **Chờ mọi kết quả:** cần cả ba kết cục, nên tiếp tục tới khi C hoàn tất.
- **Thất bại sớm:** lỗi của A đủ để kết luận thất bại, nên yêu cầu hủy B và C.
- **Một thành công phù hợp:** lỗi của A chưa quyết định kết quả chung; tiếp tục chờ B hoặc C đạt yêu cầu.

Các mốc thời gian chỉ minh họa điều kiện quyết định, không phải cam kết độ trễ thực tế. Lịch thực thi, thời gian dọn dẹp và việc tác vụ có đáp ứng hủy hay không đều ảnh hưởng thời điểm phương thức trả về.

## 3. Chờ mọi kết quả: giữ lại cả dữ liệu lẫn thông tin lỗi

Chiến lược này phù hợp khi từng tác vụ đóng góp thông tin độc lập. Ví dụ, một trang vận hành cần hiển thị trạng thái của ba dịch vụ. Một dịch vụ lỗi vẫn là dữ liệu hữu ích của báo cáo; lỗi đó không làm hai kết quả còn lại mất ý nghĩa.

Trong ví dụ của bài, `allUntil(task -> false)` có predicate luôn trả về `false`, nên không yêu cầu hủy vì bất kỳ kết cục riêng lẻ nào. Khi không có timeout hoặc hủy từ bên ngoài, scope chờ các tác vụ hoàn tất rồi trả danh sách handle.

Sau `join()`, đọc từng handle theo trạng thái:

| Trạng thái | Cách xử lý |
| --- | --- |
| `SUCCESS` | Lấy giá trị bằng `get()` |
| `FAILED` | Lấy lỗi bằng `exception()` |
| `UNAVAILABLE` | Không có kết quả hoặc lỗi để đọc; phải xử lý riêng |

`get()` không phải lệnh chờ tương đương một `Future.get()`. Trong mã của scope owner, cần join trước và chỉ đọc giá trị ở trạng thái thành công. Xem [hợp đồng Subtask](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.html).

Cách thu thập này cho phép ứng dụng quyết định sau:

- Trả báo cáo đầy đủ có cả mục lỗi.
- Trả dữ liệu một phần kèm danh sách nguồn không khả dụng.
- Kết luận thất bại nếu số kết quả thành công thấp hơn yêu cầu.

Không nên đổi mọi lỗi thành một danh sách rỗng rồi gọi đó là thành công. “Nguồn không có dữ liệu” và “không đọc được nguồn” có thể cần hai cách hiển thị khác nhau.

### 3.1. Chờ hoàn tất khác với yêu cầu tất cả thành công

Tên `allSuccessfulOrThrow()` mô tả yêu cầu thành công của toàn bộ tác vụ. Khi một tác vụ lỗi, chính sách đó không tiếp tục chờ để thu đủ mọi thông tin lỗi.

Ngược lại, chiến lược thu mọi kết cục cần giữ lại thất bại như một phần thông tin của từng tác vụ. Một danh sách handle có đủ phần tử cũng chưa nói rằng tất cả phần tử đều có giá trị thành công.

## 4. Thất bại sớm: dùng khi thiếu một phần bắt buộc thì kết quả chung vô nghĩa

Giả sử cần tải hồ sơ khách hàng và tồn kho để dựng một phản hồi bắt buộc có cả hai phần. Khi tải tồn kho thất bại, việc tiếp tục đợi hồ sơ không giúp tạo ra phản hồi hợp lệ theo hợp đồng này.

Chính sách phù hợp là:

```text
tất cả tác vụ thành công -> trả kết quả tổng hợp
bất kỳ tác vụ bắt buộc nào thất bại -> kết luận lỗi, yêu cầu hủy phần còn lại
```

Nếu các tác vụ trả cùng kiểu dữ liệu, dùng `allSuccessfulOrThrow()` để lấy trực tiếp danh sách giá trị. Nếu trả các kiểu khác nhau, có thể dùng chính sách mặc định của `StructuredTaskScope.open()`, giữ từng handle, gọi `join()`, rồi dựng đối tượng tổng hợp từ các handle thành công.

Ví dụ dạng mã, giả sử `loadProfile()`, `loadStock()` và kiểu `PageData` thuộc ứng dụng:

```java
try (var scope = StructuredTaskScope.open()) {
    var profile = scope.fork(() -> loadProfile());
    var stock = scope.fork(() -> loadStock());

    scope.join();

    return new PageData(profile.get(), stock.get());
}
```

Với chính sách mặc định của JDK 27, `join()` ném `ExecutionException` nếu một tác vụ lỗi, với lỗi tác vụ làm cause. Xem [StructuredTaskScope](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

### 4.1. Chính sách chỉ đúng khi các tác vụ thực sự bắt buộc

Nếu phần gợi ý sản phẩm là tùy chọn, việc hủy toàn bộ yêu cầu vì dịch vụ gợi ý lỗi có thể trái với mục tiêu nghiệp vụ.

Khi đó, có thể:

- Đặt các tác vụ bắt buộc vào nhóm yêu cầu tất cả thành công.
- Mô hình hóa kết cục của tác vụ tùy chọn thành dữ liệu riêng, bao gồm lỗi hoặc thiếu dữ liệu.
- Tổng hợp phần tùy chọn theo một ngân sách thời gian rõ ràng.

Việc phân loại bắt buộc hay tùy chọn phải đến từ hợp đồng của phản hồi. Tên phương thức đồng thời không tự quyết định điều này.

### 4.2. Thất bại sớm không thu gom toàn bộ lỗi

Khi lỗi đầu tiên đủ để dừng, những tác vụ khác có thể chưa hoàn tất hoặc chưa bắt đầu thực thi. Không nên giả định ngoại lệ cuối cùng chứa đầy đủ lỗi của mọi tác vụ.

Nếu mục tiêu là báo cáo toàn bộ lỗi độc lập, hãy chọn chiến lược chờ mọi kết cục ngay từ đầu.

## 5. Một kết quả thành công phù hợp: lỗi sớm chưa phải thất bại chung

Chiến lược này phù hợp khi nhiều tác vụ là những cách thay thế để lấy cùng loại thông tin, và một kết quả đạt yêu cầu đã đủ.

Ví dụ, ba nguồn tìm kiếm cùng có thể trả về một kết quả sử dụng được. Khi một nguồn lỗi, hai nguồn còn lại vẫn có thể thành công.

Cần phân biệt ba mốc:

| Mốc | Ý nghĩa |
| --- | --- |
| Hoàn tất đầu tiên | Có thể là một ngoại lệ |
| Thành công đầu tiên được chấp nhận | Tác vụ trả về bình thường và đạt điều kiện của ứng dụng |
| Kết quả tốt nhất | Cần so sánh nhiều ứng viên theo tiêu chí tối ưu |

`anySuccessfulOrThrow()` phục vụ nhu cầu có một thành công. Nó không tự xếp hạng chất lượng hay bảo đảm chọn nguồn theo thứ tự khai báo.

### 5.1. Xác định “phù hợp” trước khi để tác vụ được tính là thành công

Giả sử một nguồn trả rất nhanh nhưng kết quả có điểm chất lượng dưới ngưỡng. Nếu tác vụ vẫn trả về bình thường, chính sách lấy một thành công có thể chọn ngay kết quả đó.

Một cách tổ chức là kiểm tra kết quả **bên trong tác vụ**, trước khi trả về:

```text
gọi nguồn -> kiểm tra dữ liệu -> đạt yêu cầu thì return
                             -> không đạt thì báo không có ứng viên hợp lệ
```

Các kiểm tra có thể bao gồm dữ liệu không rỗng, đúng phiên bản, đúng ngữ cảnh yêu cầu hoặc đủ ngưỡng chất lượng. Nếu API có thể trả `null`, cần xử lý rõ; trả `null` bình thường không tự trở thành thất bại của tác vụ.

Ví dụ ở phần sau dùng ngoại lệ để loại ứng viên dưới ngưỡng. Đây là quy ước của ví dụ. Nếu “không có ứng viên” là kết cục thường xuyên, có thể mô hình hóa thành dữ liệu và dùng `allUntil` với predicate kiểm tra kết quả phù hợp. Sau đó, bên điều phối vẫn phải chọn một handle thành công đạt điều kiện và xử lý trường hợp không có ứng viên.

Predicate dùng trong `allUntil` cần an toàn khi được gọi đồng thời. Tránh sửa một `ArrayList` dùng chung hoặc bộ đếm thường từ predicate.

### 5.2. Có một thành công không đồng nghĩa đã tối ưu

Nếu chỉ cần điểm từ 80 trở lên, ứng viên đạt 85 có thể đủ để kết luận và hủy ứng viên đang tính điểm 95.

Nếu hợp đồng yêu cầu điểm cao nhất trong mọi nguồn, không thể dùng việc xuất hiện một kết quả hợp lệ để khẳng định tối ưu. Khi đó, cần thu đủ kết quả để so sánh, hoặc có một điều kiện dừng khác chứng minh rằng không ứng viên còn lại nào có thể tốt hơn.

Khi tất cả ứng viên lỗi, chính sách lấy một thành công phải báo lỗi. Khi không có tác vụ nào được fork, JDK 27 báo `ExecutionException` với cause là `NoSuchElementException`; ứng dụng cũng có thể kiểm tra danh sách nguồn rỗng trước khi mở scope.

## 6. Ví dụ hoàn chỉnh bằng JDK 27

Lưu thành `PoliciesDemo.java` nếu muốn thực hành. Mã dùng `Thread.sleep` để mô phỏng độ trễ, không truy cập dịch vụ thật.

```java
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;

public class PoliciesDemo {
    record SearchHit(String source, int score, String text) {}

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        System.out.println("EVERY_OUTCOME = " + collectEveryOutcome());
        System.out.println("ALL_REQUIRED = " + allRequired(false));
        System.out.println("ONE_ACCEPTABLE = " + firstAcceptable());
    }

    static List<String> collectEveryOutcome() throws InterruptedException {
        try (var scope = StructuredTaskScope.open(
                Joiner.<String>allUntil(task -> false))) {
            scope.fork(() -> remote("service-a", 80, false));
            scope.fork(() -> remote("service-b", 30, true));
            scope.fork(() -> remote("service-c", 140, false));

            return scope.join().stream()
                    .map(task -> switch (task.state()) {
                        case SUCCESS -> "SUCCESS: " + task.get();
                        case FAILED -> "FAILED: "
                                + task.exception().getMessage();
                        case UNAVAILABLE -> "UNAVAILABLE";
                    })
                    .toList();
        }
    }

    static List<String> allRequired(boolean inventoryFails)
            throws InterruptedException, ExecutionException {
        try (var scope = StructuredTaskScope.open(
                Joiner.<String>allSuccessfulOrThrow())) {
            scope.fork(() -> remote("profile", 80, false));
            scope.fork(() -> remote("inventory", 40, inventoryFails));
            scope.fork(() -> remote("pricing", 160, false));

            return scope.join();
        }
    }

    static SearchHit firstAcceptable()
            throws InterruptedException, ExecutionException {
        try (var scope = StructuredTaskScope.open(
                Joiner.<SearchHit>anySuccessfulOrThrow())) {
            scope.fork(() -> checkedHit("fast-low-quality", 30, 55));
            scope.fork(() -> checkedHit("source-b", 100, 85));
            scope.fork(() -> checkedHit("source-c", 200, 95));

            return scope.join();
        }
    }

    static String remote(String name, long delayMillis, boolean fail)
            throws InterruptedException {
        Thread.sleep(delayMillis);
        if (fail) {
            throw new IllegalStateException(name + " unavailable");
        }
        return name + "-data";
    }

    static SearchHit checkedHit(String source, long delayMillis, int score)
            throws InterruptedException {
        Thread.sleep(delayMillis);
        var hit = new SearchHit(source, score, "data-from-" + source);
        if (hit.score() < 80 || hit.text().isBlank()) {
            throw new IllegalStateException(source + " not acceptable");
        }
        return hit;
    }
}
```

Biên dịch và chạy bằng **đúng bộ công cụ JDK 27**:

```shell
javac --enable-preview --release 27 PoliciesDemo.java
java --enable-preview PoliciesDemo
```

Cần bật preview ở cả hai bước. Phạm vi sử dụng preview được nêu trong [hướng dẫn Structured Concurrency của Java 27](https://docs.oracle.com/en/java/javase/27/core/structured-concurrency.html).

Các đặc điểm dự kiến:

- `EVERY_OUTCOME` chứa hai mục thành công và một mục lỗi, theo thứ tự fork.
- `ALL_REQUIRED` chứa ba giá trị khi `inventoryFails` là `false`.
- `ONE_ACCEPTABLE` chỉ trả một `SearchHit` có điểm ít nhất 80. Nguồn điểm 55 bị loại dù thường hoàn tất sớm nhất.
- Do lịch chạy thực tế, không dùng các độ trễ giả lập để khẳng định một nguồn luôn thắng. Kết quả được chọn cũng không nhất thiết có điểm cao nhất.

Nếu đổi lời gọi thành `allRequired(true)`, chính sách yêu cầu toàn bộ thành công sẽ báo lỗi. Trong `main` hiện tại, ngoại lệ được truyền ra ngoài nên dòng gọi tiếp theo không chạy.

Các danh sách trong ví dụ phục vụ minh họa. Với báo cáo thật, nên lưu tên nguồn, trạng thái, dữ liệu và lỗi bằng kiểu dữ liệu có cấu trúc thay vì chỉ ghép chuỗi.

## 7. Phân biệt thời điểm có kết luận với thời điểm đã dừng mọi tác vụ

Một nhầm lẫn phổ biến là nghĩ “thất bại sớm” hoặc “có kết quả sớm” luôn khiến phương thức trả về ngay lập tức.

Vòng đời cần nhìn thành hai phần:

```text
fork các tác vụ
      |
      v
join có kết luận theo chính sách
      |
      v
close chờ các luồng tác vụ kết thúc
      |
      v
phương thức thoát khỏi try-with-resources
```

Khi scope bị hủy, các tác vụ chưa hoàn tất được yêu cầu dừng bằng interruption. `close()` vẫn chờ các luồng kết thúc. Vì vậy, nếu một tác vụ bỏ qua interruption hoặc mắc trong một thao tác không đáp ứng hủy, phần dọn dẹp có thể kéo dài dù đã có kết luận.

Đây là lý do cần đọc cả chính sách và hành vi dừng của tác vụ; xem [hợp đồng close()](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html#close()).

### 7.1. Hủy là cơ chế hợp tác

Trong ví dụ, `Thread.sleep` ném `InterruptedException` khi bị interrupt, và các phương thức cho ngoại lệ truyền ra. Điều đó cho phép tác vụ kết thúc khi scope không còn cần nó.

Với vòng lặp tính toán dài, mã tác vụ cần có điểm kiểm tra interruption phù hợp. Khi bắt `InterruptedException`, thường truyền tiếp; nếu chuyển sang cách xử lý khác, cần khôi phục interrupted status theo hợp đồng của lớp bao ngoài. Xem [Thread Interruption](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html#interruption).

Không bắt interruption rồi tiếp tục làm việc như chưa có yêu cầu hủy.

### 7.2. Hủy không hoàn tác tác dụng phụ

Nếu tác vụ đã gửi lệnh ghi ra một hệ thống bên ngoài, việc interrupt luồng Java không chứng minh lệnh đó đã bị rút lại.

Do đó, đua nhiều nguồn phù hợp nhất với các thao tác có thể thay thế nhau và có ngữ nghĩa hủy rõ ràng. Với thao tác ghi, phải phân tích trùng lặp và cơ chế bảo đảm của hệ thống đích. Chính sách của task scope không tạo giao dịch phân tán.

## 8. Thêm ngân sách thời gian mà vẫn giữ đúng chính sách

Ba chiến lược đều cần trả lời câu hỏi: nếu một nguồn không bao giờ trả kết quả thì chờ đến khi nào?

JDK 27 cho phép cấu hình timeout khi mở scope. Ví dụ sau là đoạn mã đặt trong một phương thức của lớp `PoliciesDemo`, có khai báo `throws InterruptedException, ExecutionException`:

```java
try (var scope = StructuredTaskScope.open(
        Joiner.<String>allSuccessfulOrThrow(),
        config -> config.withTimeout(
                java.time.Duration.ofMillis(300)))) {
    scope.fork(() -> remote("profile", 80, false));
    scope.fork(() -> remote("inventory", 1_000, false));

    List<String> results = scope.join();
    return results;
}
```

Timeout bắt đầu tính khi scope mở, không chỉ từ lúc gọi `join()`. Có thể cấu hình theo ngân sách thời gian còn lại của yêu cầu; xem [Configuration.withTimeout](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Configuration.html#withTimeout(java.time.Duration)) và đặc tả scope.

Cách xử lý timeout phụ thuộc chính sách:

| Chính sách JDK 27 dùng trong bài | Khi timeout làm scope bị hủy |
| --- | --- |
| `allSuccessfulOrThrow()` | Báo `ExecutionException` với cause là `CancelledByTimeoutException` |
| `anySuccessfulOrThrow()` | Cũng báo lỗi timeout nếu chưa có thành công để kết luận |
| `allUntil(task -> false)` | Trả danh sách handle, có thể gồm `UNAVAILABLE`; không tự ném lỗi chỉ vì timeout |

`CancelledByTimeoutException` mô tả nguyên nhân hủy do hết thời gian; xem [đặc tả ngoại lệ này](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.CancelledByTimeoutException.html).

Với chiến lược thu kết cục, phải phân biệt “mọi tác vụ đã cho kết quả” và “đã hết thời gian chờ”. `UNAVAILABLE` có thể xuất hiện khi tác vụ chưa hoàn tất, được fork sau khi scope bị hủy hoặc hoàn tất sau thời điểm hủy. Nó không phải một giá trị thành công và cũng không tự cung cấp ngoại lệ của tác vụ; xem [Subtask.State](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.State.html).

Timeout của scope cũng không bảo đảm toàn bộ phương thức kết thúc đúng tại mốc đó, vì còn bước `close()` chờ tác vụ dừng. Nên phối hợp ngân sách tổng với timeout và cơ chế hủy mà các lời gọi bên trong hỗ trợ.

## 9. Cách chọn trong ứng dụng

Có thể bắt đầu bằng một câu hoàn chỉnh mô tả điều kiện đủ:

- “Tôi cần biết kết cục của từng nguồn để lập báo cáo.”
- “Tôi cần đủ mọi phần bắt buộc để tạo phản hồi hợp lệ.”
- “Tôi chỉ cần một ứng viên đạt điều kiện đã định nghĩa.”

Sau đó xác định điều kiện dừng, dữ liệu cần giữ và cách báo lỗi:

| Câu hỏi | Quyết định cần có |
| --- | --- |
| Một nguồn lỗi có làm kết quả chung vô nghĩa không? | Có thì cân nhắc thất bại sớm; không thì giữ kết cục hoặc chờ ứng viên khác |
| Các tác vụ bổ sung cho nhau hay thay thế nhau? | Bổ sung thường cần nhiều kết quả; thay thế có thể chỉ cần một |
| Một giá trị trả về bình thường đã đủ tốt chưa? | Nếu chưa, đặt kiểm tra chấp nhận trước khi kết luận |
| Có cần kết quả tốt nhất hoặc đủ số phiếu không? | Cần thêm điều kiện so sánh hoặc chính sách quorum |
| Cần giữ tất cả lỗi để chẩn đoán không? | Thu từng kết cục thay vì chỉ dựa vào lỗi đầu tiên |
| Hết thời gian thì được trả dữ liệu một phần không? | Định nghĩa cách xử lý các mục chưa có kết quả |
| Tác vụ có dừng khi bị hủy không? | Kiểm tra hợp đồng interruption, I/O và bước dọn dẹp |

Yêu cầu “ít nhất hai trong ba nguồn đồng ý” là một chính sách quorum, không phải lấy một thành công. Yêu cầu “chọn kết quả tốt nhất trước deadline” cũng cần một quy tắc đánh giá riêng. Khi dùng predicate hoặc Joiner tùy chỉnh, trạng thái dùng chung của bộ điều phối phải được thiết kế cho truy cập đồng thời.

Mọi chiến lược đều cần giữ cấu trúc vòng đời: mở scope, fork, join, xử lý kết cục và đóng scope. Điểm khác nhau nằm ở điều kiện đủ để kết luận và thông tin cần giữ lại cho bên gọi.
