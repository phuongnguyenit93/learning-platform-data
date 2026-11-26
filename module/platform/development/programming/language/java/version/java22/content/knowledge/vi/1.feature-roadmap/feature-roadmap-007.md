# Structured Concurrency và Vector API: học theo trạng thái cùng API của JDK đang sử dụng

Java 22 giới thiệu hai hướng phát triển quan trọng cho chương trình Java hiện đại: Structured Concurrency giúp quản lý vòng đời của các tác vụ chạy đồng thời; Vector API giúp diễn đạt phép tính trên nhiều phần tử cùng lúc để tận dụng lệnh SIMD của CPU. Cả hai vẫn đáng học, nhưng trạng thái phát triển và cách sử dụng hiện nay rất khác nhau.

Bài này lấy Java 22 làm mốc lịch sử, sau đó hướng dẫn chọn nội dung học và API theo JDK thực tế. Không nên sao chép nguyên ví dụ preview hoặc incubator của JDK 22 sang JDK mới: Structured Concurrency đã thay đổi API và tiến gần đến trạng thái chính thức, trong khi Vector API vẫn đang ở giai đoạn incubator.

> **Mốc trạng thái:** nội dung được cập nhật đến ngày 24/11/2026. JDK 27 là bản feature release GA mới nhất; JDK 25 là bản LTS mới nhất. JDK 28 đang được phát triển và dự kiến GA vào tháng 03/2027. Vì thế, các trạng thái của JDK 28 trong bài là trạng thái của nhánh phát triển, không phải một bản GA đã phát hành.

## 1. Hai tính năng, hai bài toán khác nhau

| Tính năng | Bài toán chính | Nên quan tâm khi |
| --- | --- | --- |
| Structured Concurrency | Quản lý nhóm tác vụ con, kết quả, lỗi, timeout và hủy trong cùng vòng đời của tác vụ cha. | Một request hoặc một công việc cần gọi nhiều dịch vụ độc lập, phối hợp kết quả rồi mới hoàn tất. |
| Vector API | Biểu diễn phép toán theo từng lane để JVM có thể sử dụng SIMD trên phần cứng hỗ trợ. | Ứng dụng có đoạn tính toán số học trên mảng hoặc dữ liệu lớn, đã đo đạc và xác định đây là điểm nghẽn hiệu năng. |

Structured Concurrency thuộc lĩnh vực đồng thời ở cấp tác vụ. Vector API thuộc lĩnh vực tính toán dữ liệu ở cấp phần tử. Hai tính năng không thay thế nhau và cũng không bắt buộc phải học cùng lúc. Với ứng dụng backend thông thường, Structured Concurrency thường gần với nhu cầu hằng ngày hơn. Vector API phù hợp với các bài toán chuyên biệt như xử lý tín hiệu, ảnh, mô phỏng, phân tích dữ liệu hoặc một số bước tính toán trong AI.

## 2. Đọc trạng thái JDK trước khi học API

Ba trạng thái cần phân biệt:

- **API chính thức (final):** đã trở thành một phần ổn định của Java SE. Có thể dùng mà không cần cờ preview hoặc module incubator.
- **Preview:** API hoặc ngôn ngữ được cung cấp để thử nghiệm và nhận phản hồi. Cần bật preview khi biên dịch và chạy; chữ ký hoặc hành vi vẫn có thể thay đổi trước khi chính thức hóa.
- **Incubator:** module/API thử nghiệm độc lập. Phạm vi thay đổi có thể lớn hơn preview và API có thể bị loại bỏ. Cần thêm module khi biên dịch và chạy; không nên coi đây là hợp đồng API ổn định cho thư viện hoặc ứng dụng production.

### 2.1. Structured Concurrency qua các JDK

| JDK | JEP | Trạng thái | Ý nghĩa đối với người học |
| --- | --- | --- | --- |
| 19 | 428 | Incubator lần đầu | Mốc khởi đầu của Structured Concurrency. |
| 20 | 437 | Incubator lần hai | Tiếp tục thử nghiệm trước khi trở thành preview. |
| 21 | 453 | Preview lần một | Đưa API vào giai đoạn preview. |
| 22 | 462 | Preview lần hai | Mốc của module Java 22 này; ý tưởng và API lúc đó chưa phải API cuối. |
| 23 | 480 | Preview lần ba | Tiếp tục tinh chỉnh. |
| 24 | 499 | Preview lần bốn | Tiếp tục preview. |
| 25 | 505 | Preview lần năm | Thiết kế API thay đổi đáng kể: dùng `StructuredTaskScope.open(...)` và `Joiner` thay cho cách tạo scope bằng constructor cùng các lớp chính sách cũ. |
| 26 | 525 | Preview lần sáu | Tiếp tục hoàn thiện chính sách phối hợp và kết quả. |
| 27 | 533 | Preview lần bảy | API có dạng gần với bản chính thức, gồm kiểu ngoại lệ riêng cho `join()`. |
| 28 | 543 | Đã tích hợp API chính thức vào nhánh phát triển | Không còn preview trong JDK 28; API giữ nguyên hình dạng của lần preview thứ bảy. JDK 28 chưa GA tại ngày cập nhật. |

JEP 462 là mốc lịch sử cần biết khi học Java 22. Với code mới, nên học API của JDK 27 hoặc bản JDK 28 đã tích hợp JEP 543. Không dùng các lớp `ShutdownOnFailure` và `ShutdownOnSuccess` từ API preview cũ như mẫu cho code mới; chính sách hiện hành được biểu diễn bằng `Joiner`.

JDK 27 vẫn yêu cầu bật preview cho Structured Concurrency. Trên nhánh JDK 28 đã tích hợp JEP 543, API đã trở thành API chính thức và không cần cờ preview riêng cho tính năng này. Tuy vậy, JDK 28 chỉ nên được dùng để đánh giá trên bản Early Access cho đến khi có bản GA.

### 2.2. Vector API qua các JDK

| JDK | JEP | Trạng thái | Ý nghĩa đối với người học |
| --- | --- | --- | --- |
| 16 | 338 | Incubator lần một | Giới thiệu Vector API. |
| 17 | 414 | Incubator lần hai | Tiếp tục hoàn thiện. |
| 18 | 417 | Incubator lần ba | Tiếp tục hoàn thiện. |
| 19 | 426 | Incubator lần bốn | Tiếp tục hoàn thiện. |
| 20 | 438 | Incubator lần năm | Tiếp tục hoàn thiện. |
| 21 | 448 | Incubator lần sáu | Tiếp tục hoàn thiện. |
| 22 | 460 | Incubator lần bảy | Mốc của module Java 22 này. |
| 23 | 469 | Incubator lần tám | Tiếp tục hoàn thiện. |
| 24 | 489 | Incubator lần chín | Tiếp tục hoàn thiện. |
| 25 | 508 | Incubator lần mười | Vẫn là API incubator. |
| 26 | 529 | Incubator lần mười một | Vẫn là API incubator. |
| 27 | 537 | Incubator lần mười hai | Đây là trạng thái trong bản JDK GA mới nhất tại ngày cập nhật. |
| 28 | 548 | Candidate cho lần incubator thứ mười ba | Đề xuất bổ sung vector cho `Float16`; tại ngày cập nhật mới ở trạng thái Candidate, chưa được tích hợp hoặc xác nhận là tính năng của JDK 28. |

Vector API đã trải qua nhiều vòng incubator nhưng chưa trở thành API chính thức. Điều này không có nghĩa ý tưởng SIMD đã lỗi thời: SIMD vẫn là cách phần cứng xử lý nhiều dữ liệu song song. Điều chưa ổn định là hợp đồng API Java đang được thử nghiệm. JEP 548 tiếp tục phụ thuộc vào các khả năng của Project Valhalla trước khi nhóm phát triển có thể đưa Vector API sang giai đoạn preview.

Vì vậy, có thể học khái niệm SIMD và thực hành Vector API để hiểu cách tối ưu phép tính. Với ứng dụng cần một hợp đồng Java SE ổn định, hãy dùng kiểu dữ liệu nguyên thủy và vòng lặp Java thông thường; để JVM tối ưu khi có thể. Chỉ đưa Vector API incubator vào một phần mã được cô lập khi đã chấp nhận việc nâng cấp JDK có thể cần sửa đổi.

## 3. Chọn đường học theo JDK mục tiêu

Trước khi bắt đầu, xác định JDK dùng để biên dịch, chạy kiểm thử và triển khai. Một máy phát triển có thể cài nhiều JDK; vì vậy hãy kiểm tra cả `java -version` và `javac -version`, sau đó bảo đảm IDE, build tool, test runner và runtime đang dùng đúng toolchain.

| JDK mục tiêu | Structured Concurrency | Vector API | Cách học phù hợp |
| --- | --- | --- | --- |
| JDK 22 | Preview lần hai, API lịch sử | Incubator lần bảy | Dùng để hiểu mốc giới thiệu và so sánh quá trình phát triển. Không chọn làm baseline mới: JDK 22 là feature release không LTS và đã qua mốc hỗ trợ của Oracle. |
| JDK 25 LTS | Preview lần năm; API khác với JDK 27 | Incubator lần mười | Có thể học trên JDK LTS đang được sử dụng, nhưng giữ mã preview/incubator trong thử nghiệm và kiểm tra đúng Javadoc JDK 25. |
| JDK 27 GA | Preview lần bảy | Incubator lần mười hai | Môi trường GA mới nhất tại ngày cập nhật để học API Structured Concurrency gần với bản chính thức và Vector API mới nhất đã phát hành. |
| JDK 28 Early Access | JEP 543 đã tích hợp API chính thức trong nhánh phát triển | JEP 548 mới là Candidate | Dùng để thử và chuẩn bị nâng cấp. Chưa coi JDK 28 là baseline production trước khi phát hành GA. |

Nếu dự án cần API ổn định ngay hôm nay, đừng đưa Structured Concurrency preview hoặc Vector API incubator vào bề mặt API công khai. Trên JDK 25 LTS, có thể dùng virtual threads cùng `ExecutorService`, `Future` hoặc `CompletableFuture` để tổ chức công việc; cần tự quản lý việc chờ, lỗi và hủy theo đúng vòng đời ứng dụng. Với tính toán số học, bắt đầu bằng mảng primitive và vòng lặp đơn giản để JVM có cơ hội tối ưu.

## 4. Lộ trình học Structured Concurrency

### 4.1. Ôn nền tảng cần thiết

Trước khi mở scope, cần hiểu các khái niệm sau:

- Thread, task, `Callable`, `Future` và `ExecutorService`.
- Virtual threads, được chính thức hóa từ Java 21, và sự khác nhau giữa thread nhẹ với cách quản lý vòng đời tác vụ.
- Interrupt, `InterruptedException`, timeout và cách một tác vụ hợp tác với yêu cầu hủy.
- Exception propagation: lỗi xảy ra ở tác vụ con được chuyển về tác vụ cha như thế nào.

Structured Concurrency không thay thế kiến thức về thread. Nó cung cấp cách biểu diễn quan hệ cha-con và phối hợp kết quả rõ ràng hơn.

### 4.2. Học vòng đời của một scope

Một scope có owner là thread tạo scope. Owner tạo tác vụ con bằng `fork`, chờ kết quả bằng `join`, xử lý kết quả và đóng scope. Các thread con phải kết thúc trước khi luồng điều khiển rời khỏi scope.

Ví dụ dưới đây dùng API JDK 27; cùng hình dạng API này đã được JEP 543 tích hợp vào JDK 28:

```java
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;

record Dashboard(User user, List<Order> orders) {}

Dashboard loadDashboard(String userId)
        throws InterruptedException, ExecutionException {
    try (var scope = StructuredTaskScope.open()) {
        var userTask = scope.fork(() -> findUser(userId));
        var ordersTask = scope.fork(() -> findOrders(userId));

        // join() chờ tất cả tác vụ thành công hoặc dừng khi có tác vụ lỗi.
        scope.join();

        // Đọc kết quả sau khi join() hoàn tất thành công.
        return new Dashboard(userTask.get(), ordersTask.get());
    }
}
```

`User`, `Order`, `findUser` và `findOrders` là các kiểu dữ liệu/phương thức do ứng dụng định nghĩa. Trong ví dụ:

1. `open()` tạo scope với chính sách mặc định.
2. Mỗi `fork(...)` khởi chạy một thread mới, mặc định là virtual thread.
3. `join()` chờ các tác vụ hoàn tất. Nếu một tác vụ thất bại, scope hủy các tác vụ còn lại và `join()` ném `ExecutionException`.
4. Sau khi `join()` thành công, owner có thể lấy kết quả bằng `Subtask.get()`.
5. `try-with-resources` đóng scope; chương trình không rời khỏi scope khi các thread con vẫn còn chạy.

### 4.3. Học chính sách `Joiner`

`Joiner` quyết định scope coi điều kiện nào là hoàn thành. Một số chính sách dựng sẵn:

| Joiner | Dùng khi |
| --- | --- |
| `awaitAllSuccessfulOrThrow()` | Cần tất cả tác vụ thành công; sau đó lấy kết quả từ từng `Subtask`. |
| `allSuccessfulOrThrow()` | Các tác vụ cùng kiểu kết quả và muốn `join()` trả về danh sách kết quả. |
| `anySuccessfulOrThrow()` | Các tác vụ có thể thay thế cho nhau và chỉ cần một kết quả thành công. |
| `allUntil(predicate)` | Cần dừng theo một điều kiện tùy biến trên trạng thái/kết quả tác vụ. |

Ví dụ khi chỉ cần dữ liệu từ một replica:

```java
String readFromAnyReplica(String key)
        throws InterruptedException, ExecutionException {
    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>anySuccessfulOrThrow())) {
        scope.fork(() -> readReplica("replica-a", key));
        scope.fork(() -> readReplica("replica-b", key));
        return scope.join();
    }
}
```

Chỉ dùng chính sách này khi kết quả của các replica thực sự tương đương. Không dùng nó cho các tác vụ mà tất cả kết quả đều cần thiết, chẳng hạn lấy hồ sơ người dùng và danh sách đơn hàng để ghép thành một response.

### 4.4. Học timeout, hủy và quan sát

Sau khi hiểu `open`, `fork`, `join` và `Joiner`, hãy thực hành:

- Cấu hình timeout bằng `Configuration.withTimeout(Duration)`.
- Đặt tên scope và cấu hình `ThreadFactory` khi cần theo dõi hoặc tùy chỉnh thread.
- Phân biệt lỗi từ tác vụ con với lỗi do timeout.
- Kiểm tra hành vi khi một tác vụ chậm, một tác vụ lỗi hoặc thread bị interrupt.
- Truyền ngữ cảnh bất biến giữa các tác vụ bằng Scoped Values khi phù hợp; không dùng thread-local mutable như một cách chia sẻ trạng thái tùy tiện.

Hủy tác vụ không phải lệnh dừng cưỡng bức. Scope gửi interrupt đến thread con chưa hoàn thành. Tác vụ con phải phản hồi interrupt, giải phóng tài nguyên và không được nuốt `InterruptedException` một cách im lặng. Nếu lời gọi mạng hoặc thư viện bên dưới không thể hủy, cần có timeout riêng ở tầng đó.

### 4.5. Chọn cách biên dịch theo trạng thái

Trên JDK 27, Structured Concurrency là preview. Cần bật preview ở cả compiler và runtime:

```bash
javac --release 27 --enable-preview -d out src/Main.java
java --enable-preview -cp out Main
```

Trên JDK 28 sau khi dùng bản có JEP 543, Structured Concurrency là API chính thức nên không cần `--enable-preview` cho tính năng này. Trước khi JDK 28 GA, chỉ nên dùng bản Early Access để thử nghiệm. Với JDK 25, hãy dùng Javadoc và cờ của JDK 25; API ở đó là preview lần năm và không thể mặc định tương thích với ví dụ JDK 27.

## 5. Lộ trình học Vector API

### 5.1. Hiểu SIMD trước khi viết vector code

SIMD là viết tắt của *Single Instruction, Multiple Data*. Một lệnh vector có thể áp dụng cùng một phép toán lên nhiều lane dữ liệu. Ví dụ, thay vì cộng hai phần tử một lần, một phép cộng vector có thể cộng nhiều cặp phần tử trong cùng một thao tác phần cứng.

Vector API cung cấp các kiểu như `IntVector`, `LongVector`, `FloatVector` và `DoubleVector`. Một vector có số lane cố định theo `VectorSpecies`; các phép toán như `add`, `mul`, so sánh, mask và shuffle thao tác trên các lane đó. `SPECIES_PREFERRED` cho phép chọn dạng vector được nền tảng hiện tại ưu tiên, thay vì cố định một kích thước phần cứng trong code.

API vẫn chạy đúng trên nền tảng không có phần cứng SIMD phù hợp, nhưng không nhất thiết đem lại lợi ích hiệu năng. Khả năng tối ưu thực tế còn phụ thuộc kiến trúc CPU, JDK, dữ liệu và dạng phép toán.

### 5.2. Thực hành với phép cộng mảng

Ví dụ sau dùng Vector API của JDK 27 để cộng hai mảng `float`. Vòng lặp vector xử lý các khối đầy đủ; vòng lặp scalar cuối xử lý phần tử còn dư:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

final class VectorAdd {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    static void add(float[] left, float[] right, float[] result) {
        if (left.length != right.length || left.length != result.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }

        int i = 0;
        int bound = SPECIES.loopBound(left.length);

        for (; i < bound; i += SPECIES.length()) {
            var a = FloatVector.fromArray(SPECIES, left, i);
            var b = FloatVector.fromArray(SPECIES, right, i);
            a.add(b).intoArray(result, i);
        }

        // Xử lý phần đuôi không đủ một vector.
        for (; i < left.length; i++) {
            result[i] = left[i] + right[i];
        }
    }
}
```

Các thành phần chính:

- `FloatVector.SPECIES_PREFERRED`: chọn species được nền tảng ưu tiên cho phần tử `float`.
- `SPECIES.length()`: số lane trong một vector.
- `SPECIES.loopBound(length)`: tìm giới hạn lớn nhất để vòng lặp chỉ đọc các khối đủ lane.
- `FloatVector.fromArray(...)`: nạp dữ liệu từ mảng vào vector.
- `add(...)`: cộng theo từng lane.
- `intoArray(...)`: ghi các lane kết quả về mảng.

Phần đuôi scalar rất quan trọng: độ dài mảng bất kỳ không nhất thiết chia hết cho số lane. Có thể dùng masked operation để xử lý phần đuôi bằng vector, nhưng hãy bắt đầu bằng vòng lặp scalar vì dễ kiểm tra tính đúng đắn.

### 5.3. Bật module incubator

Trên JDK 27, Vector API thuộc module `jdk.incubator.vector`. Đây là incubator API, không phải preview feature; do đó cần thêm module khi biên dịch và chạy:

```bash
javac --add-modules jdk.incubator.vector -d out src/VectorAdd.java
java --add-modules jdk.incubator.vector -cp out app.Main
```

Trong lệnh chạy, `app.Main` là lớp có `main()` của ứng dụng và gọi `VectorAdd.add(...)`; thay tên này bằng entry point thực tế của dự án.

Không dùng `--enable-preview` chỉ để bật Vector API. Cờ preview dành cho preview features như Structured Concurrency trên JDK 27; cờ `--add-modules` dành cho module incubator. Nếu một ứng dụng dùng cả hai tính năng trên JDK 27, phải cấu hình cả hai loại cờ tương ứng.

### 5.4. Đo hiệu năng trước khi quyết định

Vector API không đảm bảo mọi vòng lặp đều nhanh hơn. Trước khi giữ lại code vector:

1. Viết phiên bản scalar dễ đọc và kiểm tra kết quả.
2. Đo bằng benchmark có warmup, nhiều lần chạy và dữ liệu đại diện; JMH là lựa chọn phù hợp cho microbenchmark JVM.
3. So sánh trên đúng JDK, CPU, hệ điều hành và kích thước dữ liệu mục tiêu.
4. Kiểm tra cả dữ liệu nhỏ, dữ liệu lớn, phần đuôi mảng và các trường hợp biên.
5. Giữ phiên bản scalar nếu vector hóa không cải thiện đủ để bù chi phí phức tạp và rủi ro nâng cấp.

Đừng suy luận hiệu năng chỉ từ số lane. Truy cập bộ nhớ, cache, băng thông, nhánh điều kiện, cách bố trí dữ liệu và khả năng tối ưu của JIT đều ảnh hưởng kết quả. Với nhiều vòng lặp scalar đơn giản, JIT có thể tự vector hóa mà không cần gọi Vector API.

### 5.5. Hiểu giới hạn của incubator

JDK 27 công bố Vector API ở JEP 537, lần incubator thứ mười hai. JEP 548 là đề xuất lần thứ mười ba, mới ở trạng thái Candidate tại ngày 24/11/2026; thay đổi đáng chú ý được đề xuất là hỗ trợ vector có lane `Float16` theo định dạng IEEE 754 binary16. Không viết code phụ thuộc phần bổ sung này cho đến khi có JDK phát hành chính thức chứa API tương ứng và Javadoc xác nhận chữ ký cuối cùng.

Vì Vector API chưa ổn định, nên:

- Không để kiểu incubator xuất hiện trong API công khai của thư viện dùng chung.
- Cô lập code vector trong một module hoặc lớp nội bộ để có thể thay thế.
- Giữ đường chạy scalar làm phương án đúng đắn và dễ kiểm chứng.
- Kiểm tra release notes và Javadoc ở mỗi lần nâng JDK; không giả định mã incubator sẽ tương thích nhị phân hoặc source giữa các phiên bản.

## 6. Thứ tự học được khuyến nghị

Một lộ trình thực tế có thể đi theo thứ tự sau:

| Bước | Nội dung | Kết quả cần đạt |
| --- | --- | --- |
| 1 | Xác định JDK/toolchain và phân biệt final, preview, incubator. | Biết ví dụ nào biên dịch được trên JDK dự án đang dùng và cần cờ nào. |
| 2 | Ôn thread, virtual threads, `ExecutorService`, `Future`, interrupt và timeout. | Hiểu cách tác vụ chạy, chờ, lỗi và hủy. |
| 3 | Học Structured Concurrency với `open`, `fork`, `join`, `close` và `Joiner`. | Xây được một request gọi nhiều dịch vụ và phối hợp kết quả an toàn. |
| 4 | Thử timeout, cancellation, lỗi đồng thời, observability và Scoped Values. | Biết xử lý các tình huống vận hành, không chỉ trường hợp thành công. |
| 5 | Ôn mảng primitive, locality, cache, SIMD và phép toán số học. | Nhận diện đoạn code có thể hưởng lợi từ vector hóa. |
| 6 | Học `VectorSpecies`, vector lanes, lane-wise operations, masks và phần đuôi mảng. | Viết được một kernel vector có kết quả tương đương phiên bản scalar. |
| 7 | Benchmark, kiểm tra nhiều nền tảng và đánh giá trạng thái JEP. | Chỉ giữ code vector khi có lợi ích đo được và chấp nhận được chi phí incubator. |

Với công việc backend, có thể dừng sau bước 4 và áp dụng Structured Concurrency khi JDK mục tiêu đã có API chính thức. Với công việc xử lý số liệu hoặc tính toán hiệu năng cao, tiếp tục các bước 5–7. Không cần học Vector API chỉ vì nó được giới thiệu trong Java 22.

## 7. Những điều không nên mang từ ví dụ cũ sang dự án mới

- Không dùng API `StructuredTaskScope` cũ với constructor và các lớp `ShutdownOnFailure`/`ShutdownOnSuccess` như thể đó là API hiện hành.
- Không giả định Structured Concurrency đã là API chính thức trên JDK 25 hoặc JDK 27. Trạng thái phụ thuộc đúng JDK: preview trên các bản đó, final trong nhánh JDK 28 đã tích hợp JEP 543.
- Không nhầm Vector API incubator với preview API hoặc API chính thức. Cờ kích hoạt và mức độ ổn định khác nhau.
- Không dùng JDK 22 làm baseline mới chỉ vì đây là phiên bản xuất hiện trong tên module học. JDK 22 là feature release không LTS; hãy chọn một bản JDK còn được nhà cung cấp hỗ trợ, ưu tiên bản LTS nếu dự án cần vòng đời dài.
- Không đưa preview/incubator vào production mà chưa có quyết định rõ ràng về nâng cấp JDK, kiểm thử hồi quy và khả năng thay thế.
- Không tuyên bố code vector nhanh hơn nếu chưa benchmark trên workload thực tế.

## 8. Tự kiểm tra sau khi học

Bạn đã nắm được lộ trình khi có thể trả lời các câu hỏi sau:

1. Structured Concurrency giải quyết vấn đề vòng đời nào mà việc tạo nhiều thread hoặc `Future` riêng lẻ chưa tự giải quyết?
2. Vì sao `join()` phải được gọi trước khi đọc kết quả của `Subtask`?
3. `Joiner.awaitAllSuccessfulOrThrow()` khác `Joiner.anySuccessfulOrThrow()` ở điều kiện hoàn thành nào?
4. Vì sao hủy một scope cần tác vụ con phản hồi interrupt?
5. Trên JDK 27, vì sao Structured Concurrency cần `--enable-preview`, còn Vector API cần `--add-modules jdk.incubator.vector`?
6. `VectorSpecies` và `SPECIES_PREFERRED` giúp code thích ứng với nền tảng như thế nào?
7. Vì sao vòng lặp vector cần xử lý phần đuôi khi độ dài mảng không chia hết cho số lane?
8. Cần đo những yếu tố nào trước khi kết luận Vector API đem lại lợi ích hiệu năng?

Nếu chưa trả lời được câu 1–4, hãy quay lại phần Structured Concurrency. Nếu chưa trả lời được câu 5–8, hãy ôn trạng thái module và phần thực hành Vector API.

## 9. Tài liệu tham khảo

**Structured Concurrency**

- [JEP 462: Structured Concurrency (Second Preview, JDK 22)](https://openjdk.org/jeps/462)
- [JEP 505: Structured Concurrency (Fifth Preview, JDK 25)](https://openjdk.org/jeps/505)
- [JEP 525: Structured Concurrency (Sixth Preview, JDK 26)](https://openjdk.org/jeps/525)
- [JEP 533: Structured Concurrency (Seventh Preview, JDK 27)](https://openjdk.org/jeps/533)
- [JEP 543: Structured Concurrency (JDK 28)](https://openjdk.org/jeps/543)
- [Java SE 27 API: `StructuredTaskScope`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)

**Vector API**

- [JEP 460: Vector API (Seventh Incubator, JDK 22)](https://openjdk.org/jeps/460)
- [JEP 508: Vector API (Tenth Incubator, JDK 25)](https://openjdk.org/jeps/508)
- [JEP 529: Vector API (Eleventh Incubator, JDK 26)](https://openjdk.org/jeps/529)
- [JEP 537: Vector API (Twelfth Incubator, JDK 27)](https://openjdk.org/jeps/537)
- [JEP 548: Vector API (Thirteenth Incubator, Candidate)](https://openjdk.org/jeps/548)
- [Java SE 27 API: `jdk.incubator.vector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html)
- [Java SE 27 API: `VectorSpecies`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html)

**Phiên bản và hỗ trợ JDK**

- [JDK Releases: lịch phát hành và vòng đời hỗ trợ](https://ops.java/releases/)
- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
