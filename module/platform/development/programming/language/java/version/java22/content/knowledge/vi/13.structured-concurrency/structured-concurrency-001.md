# JEP 462 trong Java 22 và lộ trình Structured Concurrency trên các JDK tiếp theo

Structured Concurrency (đồng thời có cấu trúc) đưa các tác vụ chạy đồng thời vào một phạm vi có vòng đời rõ ràng. Tác vụ cha tạo các tác vụ con, chờ kết quả và xử lý lỗi hoặc hủy chúng như một nhóm. Cách tổ chức này giúp chương trình dễ theo dõi hơn khi một yêu cầu cần gọi nhiều dịch vụ độc lập cùng lúc.

JEP 462 đưa Structured Concurrency vào Java 22 ở lần preview thứ hai. Ý tưởng của JEP vẫn còn nguyên giá trị, nhưng API đã được thiết kế lại đáng kể từ JDK 25. Vì vậy, bài này giải thích mốc Java 22 để hiểu quá trình phát triển, đồng thời dùng API ở JDK 27 làm ví dụ thực hành mới nhất có thể sử dụng trước khi tính năng trở thành API chính thức trong JDK 28.

> **Mốc phiên bản trong bài:** thông tin trạng thái được cập nhật đến ngày 24/11/2026. JDK 27 là bản phát hành GA mới nhất tại thời điểm này và Structured Concurrency vẫn là preview trong JDK 27. JEP 543 đã được tích hợp vào JDK 28; JDK 28 chưa phát hành GA và lịch phát hành dự kiến là tháng 03/2027.

## 1. Vấn đề mà Structured Concurrency giải quyết

Giả sử một API tạo trang tổng quan cần lấy thông tin người dùng, đơn hàng và số dư tài khoản. Ba lời gọi này độc lập, nên có thể chạy đồng thời để giảm thời gian phản hồi. Nếu mỗi lời gọi tự tạo một thread hoặc một `CompletableFuture`, tác vụ cha phải tự quản lý nhiều vấn đề:

- Chờ tất cả tác vụ hoàn tất trước khi trả response.
- Xử lý trường hợp một tác vụ thất bại trong khi các tác vụ khác vẫn chạy.
- Hủy các tác vụ còn lại khi kết quả của chúng không còn cần thiết.
- Bảo đảm không để tác vụ con tiếp tục chạy sau khi yêu cầu cha đã kết thúc.
- Giữ được mối quan hệ giữa yêu cầu cha và các công việc phát sinh từ yêu cầu đó khi theo dõi lỗi hoặc chẩn đoán hệ thống.

Nếu thiếu một quy tắc quản lý vòng đời chung, tác vụ con có thể trở thành công việc mồ côi: request đã timeout hoặc trả lỗi nhưng một số lời gọi mạng vẫn chạy nền, tiếp tục chiếm thread và tài nguyên.

Structured Concurrency mô hình hóa các tác vụ liên quan thành một cây. Tác vụ cha mở một scope, fork các tác vụ con, chờ kết quả và đóng scope. Một tác vụ con có vòng đời nằm trong scope của cha; scope không đóng cho đến khi các thread con kết thúc. Nhờ đó, luồng điều khiển của chương trình thể hiện được quan hệ cha-con của công việc đồng thời.

## 2. Các nguyên tắc cốt lõi

### 2.1. Một scope đại diện cho một nhóm tác vụ liên quan

`StructuredTaskScope` đại diện cho một nhóm tác vụ con được tạo để hoàn thành một công việc cha. Ví dụ, các tác vụ lấy hồ sơ, đơn hàng và quyền truy cập đều thuộc cùng một yêu cầu tải trang tổng quan. Chúng có thể chạy song song, nhưng kết quả của chúng được phối hợp tại một điểm trong tác vụ cha.

Scope tạo ra ranh giới vòng đời rõ ràng. Khi scope đóng, tất cả thread được tạo để chạy các tác vụ con trong scope phải kết thúc. Điều này ngăn tác vụ con tiếp tục tồn tại ngoài phạm vi công việc đã tạo ra nó.

### 2.2. Tác vụ cha chịu trách nhiệm phối hợp

Thread mở scope là *owner* của scope. Theo API hiện hành, chỉ owner mới được gọi các thao tác điều khiển như `fork`, `join` và đóng scope. Tác vụ con tập trung thực hiện công việc của nó; owner quyết định khi nào bắt đầu, chờ và sử dụng kết quả.

Trình tự thường gặp là:

1. Mở scope bằng `StructuredTaskScope.open(...)`.
2. Gọi `fork(...)` cho từng công việc độc lập.
3. Gọi `join()` để chờ kết quả theo chính sách đã chọn.
4. Đọc kết quả sau khi `join()` hoàn tất thành công.
5. Đóng scope tự động bằng `try-with-resources`.

### 2.3. Lỗi và hủy được phối hợp theo chính sách

Khi một tác vụ thất bại hoặc một điều kiện hoàn thành được đáp ứng, scope có thể hủy các tác vụ còn lại. Việc hủy thường được thực hiện bằng interrupt thread đang chạy tác vụ con. Vì vậy, tác vụ con cần phản hồi interrupt đúng cách; Java không cưỡng bức dừng thread một cách an toàn.

Chính sách cụ thể phụ thuộc vào `Joiner`. Chẳng hạn, một nhóm cần tất cả kết quả có thể hủy các tác vụ còn lại ngay khi có lỗi. Một nhóm chỉ cần một kết quả thành công có thể dừng các tác vụ khác ngay khi tìm được kết quả đầu tiên.

### 2.4. Structured Concurrency bổ trợ cho virtual threads

Virtual threads giúp tạo nhiều thread nhẹ để phục vụ các tác vụ đồng thời, đặc biệt là công việc chờ I/O. Structured Concurrency quản lý quan hệ và vòng đời của nhóm tác vụ đó. Hai tính năng bổ trợ nhau nhưng không đồng nghĩa với nhau:

- Virtual threads trả lời câu hỏi: chạy tác vụ trên thread nào và tạo nhiều thread với chi phí thấp ra sao?
- Structured Concurrency trả lời câu hỏi: các tác vụ nào thuộc cùng một công việc, chờ chúng thế nào và hủy chúng ra sao?

Một scope mặc định trong API hiện hành tạo virtual thread cho các tác vụ được fork. Có thể cấu hình `ThreadFactory` khác khi trường hợp sử dụng yêu cầu.

## 3. JEP 462 trong Java 22

JEP 462, *Structured Concurrency (Second Preview)*, được phát hành cùng JDK 22. Đây là lần preview thứ hai sau JEP 453 trong JDK 21. Mục tiêu là giúp lập trình đồng thời dễ quản lý hơn bằng cách coi một nhóm tác vụ con là một đơn vị công việc.

Ở phiên bản Java 22, API nằm trong package `java.util.concurrent` và sử dụng lớp `StructuredTaskScope<T>`. Các thao tác quan trọng khi đó gồm:

| Thành phần ở JDK 22 | Vai trò |
| --- | --- |
| `StructuredTaskScope<T>` | Đại diện cho phạm vi quản lý các tác vụ con. |
| `fork(Callable)` | Tạo tác vụ con chạy đồng thời và trả về đối tượng đại diện cho tác vụ đó. |
| `join()` / `joinUntil(Instant)` | Chờ các tác vụ con hoàn thành, có thể đặt thời hạn chờ với `joinUntil`. |
| `close()` | Đóng scope và chờ các thread con kết thúc. |
| `ShutdownOnFailure` | Chính sách dừng scope khi có tác vụ thất bại; phù hợp khi cần kết quả của tất cả tác vụ. |
| `ShutdownOnSuccess` | Chính sách dừng scope khi có tác vụ hoàn thành thành công; phù hợp khi chỉ cần một kết quả. |

Hai lớp `ShutdownOnFailure` và `ShutdownOnSuccess` thể hiện hai chính sách thường gặp: *invoke all* và *invoke any*. Với `ShutdownOnFailure`, khi một tác vụ thất bại, scope yêu cầu dừng các tác vụ chưa hoàn thành; owner có thể kiểm tra và chuyển lỗi bằng `throwIfFailed()`. Với `ShutdownOnSuccess`, kết quả thành công đầu tiên được giữ lại và các tác vụ còn lại bị yêu cầu dừng.

API Java 22 là preview API. Để thử nghiệm trên JDK 22, cần bật preview khi biên dịch và chạy:

```bash
javac --release 22 --enable-preview Main.java
java --enable-preview Main
```

Đây là mô tả lịch sử về hình dạng API của JEP 462. Các constructor và lớp chính sách kể trên đã được thay thế trong quá trình phát triển tiếp theo. Không dùng mẫu API Java 22 làm cơ sở cho code mới; hãy chọn API theo JDK mục tiêu.

## 4. Lộ trình từ JDK 19 đến JDK 28

Structured Concurrency trải qua nhiều vòng thử nghiệm. Các vòng preview cho phép nhóm phát triển Java thu thập phản hồi và điều chỉnh API trước khi đưa vào nền tảng chính thức.

| JDK | JEP | Giai đoạn | Điểm cần nhớ |
| --- | --- | --- | --- |
| 19 | 428 | Incubator | Đưa ý tưởng Structured Concurrency vào JDK để thử nghiệm. |
| 20 | 437 | Incubator lần hai | Tiếp tục tinh chỉnh thiết kế trong giai đoạn incubator. |
| 21 | 453 | Preview lần một | API trở thành preview feature. |
| 22 | 462 | Preview lần hai | Mốc được giới thiệu trong bài học Java 22; thiết kế về cơ bản tiếp tục từ JDK 21. |
| 23 | 480 | Preview lần ba | Tiếp tục preview. |
| 24 | 499 | Preview lần bốn | Tiếp tục preview trước đợt thay đổi API lớn ở JDK 25. |
| 25 | 505 | Preview lần năm | Thiết kế API thay đổi đáng kể: chuyển sang factory `open(...)` và chính sách `Joiner`. |
| 26 | 525 | Preview lần sáu | Tiếp tục hoàn thiện `Joiner`, cấu hình scope và cách biểu diễn kết quả/lỗi. |
| 27 | 533 | Preview lần bảy | API tiếp tục được hoàn thiện; đây là API preview mới nhất có trong bản JDK GA tại ngày 24/11/2026. |
| 28 | 543 | Tích hợp API chính thức | Structured Concurrency được tích hợp thành API không còn preview; JDK 28 chưa GA tại ngày 24/11/2026. |

Thay đổi quan trọng nhất đối với người viết code xảy ra ở JDK 25. Thay vì tạo scope bằng constructor và chọn lớp con `ShutdownOnFailure` hoặc `ShutdownOnSuccess`, API mới mở scope bằng phương thức tĩnh `StructuredTaskScope.open(...)`. Chính sách phối hợp được biểu diễn bằng `Joiner`. Các JDK sau đó tiếp tục bổ sung và điều chỉnh factory, cấu hình, kiểu kết quả và kiểu ngoại lệ.

Đến JDK 27, `StructuredTaskScope` là interface có ba tham số kiểu tổng quát: kiểu kết quả của tác vụ con (`T`), kiểu kết quả của `join()` (`R`) và kiểu ngoại lệ mà `join()` có thể ném (`R_X`). Không cần khai báo trực tiếp ba tham số này trong code thông thường; trình biên dịch thường suy luận kiểu từ `open(...)` và `Joiner`.

Tính đến ngày 24/11/2026:

- JDK 27 đã phát hành GA ngày 15/09/2026; Structured Concurrency vẫn là preview lần bảy theo JEP 533. Cần bật preview khi biên dịch và chạy.
- JEP 543 đã được tích hợp vào JDK 28 và loại bỏ đánh dấu preview khỏi API. API ở JDK 28 được phát triển tiếp từ thiết kế preview lần bảy của JDK 27.
- JDK 28 chưa phát hành GA. Lịch phát hành Java công bố mốc dự kiến tháng 03/2027, vì vậy không nên coi JDK 28 là bản phát hành phổ thông đã sẵn sàng tại thời điểm cập nhật bài này.

## 5. Hình dạng API hiện hành: `open`, `fork`, `join` và `Joiner`

Ví dụ dưới đây sử dụng API của JDK 27. Ví dụ vẫn áp dụng cho API đã được tích hợp trong JDK 28; điểm khác biệt quan trọng là JDK 27 yêu cầu bật preview, còn bản JDK 28 có JEP 543 chính thức không yêu cầu bật preview cho Structured Concurrency.

Giả sử một trang tổng quan cần tải hồ sơ người dùng và danh sách đơn hàng. Hai thao tác độc lập nên có thể được fork trong cùng một scope:

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

        // Chờ tất cả tác vụ thành công; nếu một tác vụ lỗi,
        // scope hủy các tác vụ còn lại và join() ném ExecutionException.
        scope.join();

        // Chỉ đọc kết quả sau khi join() hoàn tất thành công.
        return new Dashboard(userTask.get(), ordersTask.get());
    }
}
```

`User`, `Order`, `findUser` và `findOrders` là kiểu dữ liệu và phương thức do ứng dụng định nghĩa. Ví dụ tập trung vào cách phối hợp tác vụ:

1. `open()` mở scope với cấu hình mặc định.
2. Mỗi lần `fork(...)` khởi chạy một tác vụ con trong thread riêng; mặc định là virtual thread.
3. `join()` chờ các tác vụ theo chính sách mặc định: tất cả phải thành công, nếu có lỗi thì hủy scope và ném `ExecutionException`.
4. Sau khi `join()` thành công, `Subtask.get()` trả về kết quả của từng tác vụ.
5. `try-with-resources` đóng scope. Scope bảo đảm các thread con kết thúc trước khi luồng điều khiển đi ra ngoài khối `try`.

Với API JDK 27, `StructuredTaskScope.open()` dùng chính sách mặc định tương đương chờ tất cả tác vụ thành công hoặc dừng khi có tác vụ thất bại. Khi cần chính sách khác, truyền một `Joiner` vào `open(...)`.

### 5.1. Chọn chính sách qua `Joiner`

Các `Joiner` dựng sẵn đáp ứng một số tình huống phổ biến:

| Joiner | Kết quả của `join()` | Trường hợp sử dụng |
| --- | --- | --- |
| `awaitAllSuccessfulOrThrow()` | Chờ tất cả thành công; trả về `null`; ném lỗi nếu có tác vụ thất bại. | Cần kết quả từng tác vụ qua các đối tượng `Subtask`, có thể khác kiểu dữ liệu. |
| `allSuccessfulOrThrow()` | Trả về danh sách kết quả theo thứ tự fork nếu tất cả thành công; ném lỗi nếu có tác vụ thất bại. | Các tác vụ trả về cùng một kiểu và cần gom kết quả thành danh sách. |
| `anySuccessfulOrThrow()` | Trả về kết quả của một tác vụ thành công; hủy các tác vụ còn lại; ném lỗi nếu tất cả thất bại. | Gọi nhiều replica hoặc nhiều nguồn tương đương, chỉ cần một kết quả. |
| `allUntil(predicate)` | Trả về danh sách các `Subtask` khi tất cả hoàn tất hoặc điều kiện predicate yêu cầu hủy scope. | Cần chính sách dừng tùy biến dựa trên trạng thái tác vụ. |

Ví dụ sau chỉ cần kết quả thành công từ một trong hai replica:

```java
import java.util.concurrent.StructuredTaskScope;

String readFromAnyReplica(String key)
        throws InterruptedException, java.util.concurrent.ExecutionException {
    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>anySuccessfulOrThrow())) {
        scope.fork(() -> readReplica("replica-a", key));
        scope.fork(() -> readReplica("replica-b", key));

        // Trả về kết quả thành công; scope hủy tác vụ còn lại.
        return scope.join();
    }
}
```

Không nên chọn `anySuccessfulOrThrow()` chỉ vì muốn chương trình chạy nhanh hơn. Chính sách này phù hợp khi mọi kết quả đều có thể thay thế cho nhau. Nếu cần kết hợp hồ sơ, đơn hàng và quyền truy cập thành một response nhất quán, phải chờ đủ các kết quả bắt buộc.

### 5.2. Cấu hình timeout cho scope

API mới cho phép cấu hình thời hạn của scope. Ví dụ, có thể mở scope với một `Joiner` và cấu hình timeout:

```java
import java.time.Duration;
import java.util.concurrent.StructuredTaskScope;

var timeout = Duration.ofSeconds(2);

try (var scope = StructuredTaskScope.open(
        StructuredTaskScope.Joiner.<String>anySuccessfulOrThrow(),
        config -> config.withTimeout(timeout))) {
    scope.fork(() -> readReplica("replica-a", key));
    scope.fork(() -> readReplica("replica-b", key));

    String value = scope.join();
}
```

Timeout của scope giới hạn khoảng thời gian phối hợp các tác vụ. Ứng dụng vẫn cần đặt timeout phù hợp cho lời gọi mạng, truy vấn cơ sở dữ liệu và thư viện bên dưới. Khi timeout kích hoạt, scope yêu cầu hủy các tác vụ; tác vụ con phải phản hồi interrupt để giải phóng tài nguyên sớm.

## 6. Bật preview và chọn JDK phù hợp

Với JDK 27, Structured Concurrency vẫn là preview API. Cần dùng đúng JDK 27 và bật preview ở cả bước biên dịch lẫn chạy:

```bash
javac --release 27 --enable-preview -d out src/Main.java
java --enable-preview -cp out Main
```

Preview feature có thể thay đổi hoặc bị loại bỏ giữa các phiên bản JDK. Vì API đã thay đổi đáng kể ở JDK 25 và tiếp tục được tinh chỉnh ở JDK 26–27, không nên lấy source code từ JDK 22 rồi kỳ vọng nó biên dịch nguyên trạng trên JDK mới. Cần kiểm tra Javadoc của đúng JDK đích và giữ các cờ preview nhất quán giữa compiler, test runner và runtime.

Khi dùng JDK 28 có chứa JEP 543, Structured Concurrency là API chính thức và không cần `--enable-preview` riêng cho tính năng này. Tuy nhiên, tại ngày 24/11/2026, JDK 28 chưa GA; chỉ nên dùng bản Early Access để đánh giá và chuẩn bị nâng cấp. Khi JDK 28 phát hành GA, hãy kiểm tra lại release notes và Javadoc của bản phát hành cụ thể trước khi chuyển môi trường production.

## 7. Những điểm cần chú ý khi triển khai

### 7.1. Tác vụ con phải hợp tác với cơ chế hủy

Structured Concurrency không thể cưỡng bức kết thúc một thread đang chạy. Khi scope hủy tác vụ, thread con nhận interrupt. Code tác vụ nên:

- Dùng API có hỗ trợ interrupt khi chờ hoặc thực hiện I/O.
- Không nuốt `InterruptedException`. Nếu không thể ném tiếp ngoại lệ, khôi phục trạng thái interrupt bằng `Thread.currentThread().interrupt()` sau khi xử lý phù hợp.
- Dừng sớm khi nhận thấy thread bị interrupt.
- Đặt timeout cho các thao tác I/O có thể chờ lâu.

Nếu tác vụ con bỏ qua interrupt hoặc mắc kẹt trong thao tác không thể hủy, `close()` có thể phải chờ rất lâu. Đây là lý do scope không tự ý bỏ lại thread con đang chạy khi khối `try` kết thúc.

### 7.2. Chỉ đọc kết quả sau `join()`

`Subtask` có thể chưa có kết quả khi tác vụ vẫn đang chạy. Hãy gọi `join()` trước, sau đó mới đọc kết quả của những tác vụ thành công. Nếu `join()` ném lỗi, xử lý lỗi ở tầng tác vụ cha và để scope thực hiện quy trình đóng.

### 7.3. Không nhầm Structured Concurrency với virtual threads

Dùng virtual threads không tự động tạo ra cấu trúc cha-con cho các tác vụ. Nếu mỗi thành phần tự tạo thread hoặc submit công việc vào executor dùng chung, ứng dụng vẫn phải tự thiết kế việc chờ, hủy và xử lý lỗi. Structured Concurrency bổ sung ranh giới quản lý cho một nhóm công việc liên quan.

Ngược lại, Structured Concurrency không làm một tác vụ CPU-bound chạy nhanh hơn số lõi CPU hiện có. Lợi ích rõ nhất thường xuất hiện khi nhiều tác vụ độc lập cùng chờ I/O. Với công việc tính toán nặng, cần đo đạc và kiểm soát mức độ song song phù hợp.

### 7.4. Chọn đúng phạm vi công việc

Structured Concurrency phù hợp khi các tác vụ con cùng phục vụ một công việc cha và phải kết thúc trước khi công việc cha hoàn thành. Với công việc nền sống độc lập sau khi request kết thúc, lịch chạy định kỳ hoặc thông điệp cần được xử lý bền vững, hãy dùng cơ chế hàng đợi, scheduler hoặc dịch vụ nền phù hợp với yêu cầu vòng đời đó.

### 7.5. Scope không loại bỏ data race

Các tác vụ con vẫn có thể truy cập cùng dữ liệu mutable. Cấu trúc vòng đời giúp quản lý thời gian chạy, lỗi và hủy; nó không tự làm cho dữ liệu dùng chung trở nên thread-safe. Ưu tiên dữ liệu bất biến, truyền đầu vào riêng cho từng tác vụ hoặc dùng cơ chế đồng bộ phù hợp khi thật sự cần chia sẻ trạng thái mutable.

## 8. Khi nào nên dùng?

Nên cân nhắc Structured Concurrency khi một thao tác cần chia thành một nhóm tác vụ độc lập, ví dụ:

- Một request cần gọi đồng thời nhiều dịch vụ nội bộ rồi kết hợp kết quả.
- Một thao tác tìm dữ liệu từ nhiều replica và chỉ cần kết quả thành công đầu tiên.
- Một quy trình cần chạy nhiều bước độc lập, nhưng phải hủy phần còn lại khi một bước bắt buộc thất bại.
- Một tác vụ cha cần giới hạn thời gian và quản lý tập trung các công việc con.

Không cần tạo scope cho mọi lời gọi bất đồng bộ. Nếu tác vụ không có quan hệ vòng đời với tác vụ cha, cần tồn tại lâu hơn request, hoặc chỉ là một bước trong pipeline bất đồng bộ đã được quản lý tốt bằng công cụ khác, hãy chọn cơ chế phù hợp hơn.

## 9. Ghi nhớ

- JEP 462 là lần preview thứ hai của Structured Concurrency trong JDK 22. Ý tưởng cốt lõi là tổ chức các tác vụ liên quan thành một nhóm có vòng đời nằm trong tác vụ cha.
- API Java 22 dùng `StructuredTaskScope` cùng các lớp chính sách `ShutdownOnFailure` và `ShutdownOnSuccess`; đây là hình dạng API lịch sử, không phải API hiện hành.
- Từ JDK 25, API chuyển sang `StructuredTaskScope.open(...)` và `Joiner`. JDK 27 vẫn preview, còn JEP 543 đưa API ra khỏi preview trong JDK 28.
- `fork()` khởi chạy tác vụ con, `join()` phối hợp kết quả và `close()` bảo đảm các tác vụ con kết thúc trước khi scope đóng.
- Hủy tác vụ dựa trên interrupt. Code tác vụ con phải phản hồi interrupt và nên giới hạn thời gian cho các thao tác I/O.
- Virtual threads và Structured Concurrency bổ trợ nhau: một bên giúp tạo nhiều thread nhẹ, bên kia quản lý quan hệ và vòng đời của nhóm tác vụ.

## Tài liệu tham khảo

- [JEP 462: Structured Concurrency (Second Preview)](https://openjdk.org/jeps/462)
- [JEP 505: Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505)
- [JEP 525: Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525)
- [JEP 533: Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533)
- [JEP 543: Structured Concurrency](https://openjdk.org/jeps/543)
- [Java SE 27 API: `StructuredTaskScope`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [Java SE 27 API: `StructuredTaskScope.Joiner`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html)
- [Oracle: Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
- [Java Release Timeline](https://ops.java/releases/)
