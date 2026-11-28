# Bài toán quản lý vòng đời nhóm tác vụ liên quan

Một request tổng hợp thường cần gọi nhiều dịch vụ độc lập: lấy hồ sơ khách hàng, danh sách đơn hàng và quyền truy cập. Các lời gọi có thể chạy đồng thời để giảm thời gian chờ. Nhưng khi một lời gọi lỗi, request hết thời gian hoặc người dùng hủy request, ứng dụng phải biết những tác vụ còn lại đang chạy ở đâu, dừng chúng như thế nào và chờ chúng kết thúc trước khi trả quyền điều khiển về tầng gọi.

Nếu tạo thread hoặc gửi task vào executor rồi chỉ giữ từng Future rời rạc, mối quan hệ cha-con của các tác vụ dễ bị mất. Một phương thức có thể trả về trong khi task con vẫn chạy nền; exception có thể chỉ xuất hiện khi một Future được đọc; việc hủy một Future không tự bảo đảm các task khác cũng được hủy. Structured Concurrency giải quyết bài toán này bằng cách xem nhóm tác vụ liên quan như một đơn vị công việc có phạm vi và vòng đời rõ ràng.

Trong Java 26, API StructuredTaskScope là preview lần thứ sáu theo JEP 525. Bài học dùng đúng API của JDK 26 để thực hành. Đến ngày 27-11-2026, JDK 27 đã tiếp tục preview lần thứ bảy theo JEP 533; JEP 543 đã được tích hợp vào nhánh phát triển JDK 28 để hoàn tất API. JDK 28 chưa phải bản phát hành GA tại thời điểm này, vì vậy cần phân biệt API preview trong các JDK đã phát hành với trạng thái final đang được chuẩn bị cho JDK 28.

## 1. Nhận diện bài toán vòng đời tác vụ

Giả sử một API cần trả về Dashboard của khách hàng. Để dựng kết quả, nó gọi ba dịch vụ độc lập:

- fetchProfile: lấy hồ sơ khách hàng.
- fetchOrders: lấy danh sách đơn hàng.
- fetchPermissions: lấy quyền truy cập.

Các tác vụ có thể bắt đầu cùng lúc. Request chỉ trả về khi đã có đủ dữ liệu cần thiết. Nếu một tác vụ thất bại, request không thể tạo Dashboard hoàn chỉnh; hai tác vụ còn lại nên được yêu cầu dừng sớm để tiết kiệm tài nguyên.

Nếu dùng mô hình tạo task rời rạc, các câu hỏi sau phải được xử lý thủ công:

1. Ai sở hữu các task và chịu trách nhiệm chờ chúng hoàn tất?
2. Nếu task cha bị hủy thì task con có được yêu cầu dừng không?
3. Nếu một task lỗi, những task còn lại có tiếp tục chạy không?
4. Khi task cha trả về, có task con nào vẫn còn chạy không?
5. Exception của task con được truyền về task cha ở thời điểm nào?
6. Có thể quan sát nhóm tác vụ như một đơn vị trong thread dump hay không?

Một nhóm tác vụ có cấu trúc đặt tất cả câu trả lời này trong cùng một phạm vi. Task cha mở scope, fork các task con, join để lấy kết quả hoặc lỗi, rồi đóng scope. Các task con không được sống vượt ra ngoài vòng đời của scope chứa chúng.

## 2. Các thành phần của StructuredTaskScope

StructuredTaskScope trong JDK 26 thuộc package java.util.concurrent. Mô hình cơ bản gồm:

| Thành phần | Vai trò |
|---|---|
| open() | Mở một scope và xác định thread hiện tại là owner |
| fork(Callable/Runnable) | Khởi chạy một subtask trong scope |
| Subtask | Handle đại diện cho kết quả và trạng thái của một subtask |
| join() | Chờ các subtask theo chính sách của Joiner và trả kết quả hoặc ném lỗi |
| Joiner | Chọn cách xử lý khi subtask hoàn tất, thất bại hoặc đạt điều kiện hủy |
| close() | Hủy các subtask chưa hoàn tất nếu cần, rồi chờ tất cả thread con kết thúc |

Mặc định, fork tạo một virtual thread cho mỗi subtask. Có thể cấu hình ThreadFactory khác khi cần đặt tên thread hoặc dùng cách tạo thread khác. Mặc định scope không đặt timeout và không đặt tên để giám sát.

Scope được thiết kế để dùng với try-with-resources:

~~~java
try (var scope = StructuredTaskScope.open()) {
    // fork các subtask
    scope.join();
    // xử lý kết quả sau khi join
}
~~~

Owner là thread đã gọi open(). Chỉ owner được gọi fork, join và close. Không chuyển scope cho thread con để thread con tự fork thêm tác vụ trong cùng scope. Nếu task con cần tạo nhóm tác vụ riêng, nó mở scope lồng nhau và tự sở hữu scope đó.

Các lời gọi fork phải diễn ra trước join. Trong một scope, join chỉ được gọi một lần để lấy outcome; sau khi join, không fork thêm subtask. Những quy tắc này giúp giới hạn vòng đời tác vụ và làm cho luồng điều khiển dễ kiểm tra.

## 3. Vòng đời từ open đến close

Một scope đi qua các giai đoạn sau:

~~~text
Owner thread
    |
    v
open() --------------> Tạo scope, owner được xác định
    |
    v
fork(task A) --------> Virtual thread A bắt đầu
fork(task B) --------> Virtual thread B bắt đầu
fork(task C) --------> Virtual thread C bắt đầu
    |
    v
join() --------------> Chờ theo chính sách Joiner
    |
    +---- success ----> Nhận kết quả hoặc đọc Subtask.get()
    |
    +---- failure ----> Joiner có thể hủy các task còn lại
    |
    +---- timeout ----> Hủy task chưa hoàn tất nếu timeout được cấu hình
    |
    v
close() -------------> Chờ mọi thread trong scope kết thúc
    |
    v
Owner tiếp tục ngoài scope
~~~

Các nguyên tắc quan trọng:

- Owner không tiếp tục qua close khi thread chạy subtask vẫn chưa kết thúc.
- close hủy scope nếu scope chưa được hủy trước đó; các subtask chưa hoàn tất nhận interrupt.
- close luôn chờ các thread con kết thúc, kể cả khi scope đã bị hủy.
- Nếu owner fork task rồi rời scope mà không thử gọi join, close vẫn hủy và chờ các task kết thúc, sau đó báo lỗi sử dụng scope.
- Nếu join bị ngắt bởi InterruptedException, scope sẽ được đóng và các task chưa hoàn tất được yêu cầu dừng.

Structured concurrency không giết thread ngay lập tức. Hủy scope là tín hiệu cancellation, thường được truyền qua interrupt. Task con phải hợp tác bằng cách sử dụng API có thể bị interrupt, kiểm tra trạng thái interrupt hoặc kết thúc sớm khi nhận yêu cầu hủy.

## 4. Thực hành: gom nhiều tác vụ để tạo một kết quả

Ví dụ sau gọi hai dịch vụ độc lập: lấy hồ sơ và lấy đơn hàng. Cả hai phải thành công trước khi tạo Dashboard.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.concurrent.StructuredTaskScope;

record UserProfile(String id, String name) { }
record Order(String id, long amount) { }
record Dashboard(UserProfile profile, List<Order> orders) { }

final class DashboardService {

    Dashboard load(String customerId) throws InterruptedException {
        try (var scope = StructuredTaskScope.open()) {
            var profileTask = scope.fork(
                () -> fetchProfile(customerId)
            );

            var ordersTask = scope.fork(
                () -> fetchOrders(customerId)
            );

            // Chờ cả hai thành công; nếu một task lỗi thì hủy task còn lại.
            scope.join();

            // Chỉ đọc kết quả sau khi join thành công.
            return new Dashboard(
                profileTask.get(),
                ordersTask.get()
            );

        } catch (StructuredTaskScope.FailedException e) {
            Throwable cause = e.getCause();

            if (cause instanceof IOException io) {
                throw new UncheckedIOException(io);
            }

            throw new IllegalStateException(
                "Không thể tạo Dashboard",
                cause
            );
        }
    }

    private UserProfile fetchProfile(String customerId)
            throws IOException, InterruptedException {
        // Gọi dịch vụ hồ sơ.
        throw new UnsupportedOperationException("Ví dụ minh họa");
    }

    private List<Order> fetchOrders(String customerId)
            throws IOException, InterruptedException {
        // Gọi dịch vụ đơn hàng.
        throw new UnsupportedOperationException("Ví dụ minh họa");
    }
}
~~~

Trong ví dụ:

1. Owner mở scope.
2. Hai lời gọi độc lập được fork, mỗi lời gọi chạy trong một virtual thread.
3. join chờ cả hai hoàn tất thành công hoặc dừng sớm khi một task thất bại.
4. Nếu join thành công, get() lấy kết quả của từng subtask.
5. Nếu một subtask thất bại, join ném FailedException với exception của subtask thất bại làm cause; các subtask còn lại bị yêu cầu dừng.
6. try-with-resources đóng scope và chờ các thread con kết thúc trước khi phương thức thoát.

Subtask.get() chỉ nên được gọi sau khi join đã hoàn tất thành công. Nếu gọi trước khi subtask hoàn tất, hoặc subtask không ở trạng thái SUCCESS, phương thức sẽ báo lỗi trạng thái.

## 5. Chọn chính sách Joiner theo mục tiêu

Joiner quyết định khi nào scope xem công việc đã đủ điều kiện kết thúc và join() trả về dữ liệu gì. Không nên chọn một policy theo thói quen; hãy chọn theo ý nghĩa nghiệp vụ của nhóm task.

| Joiner trong JDK 26 | Hành vi | Trường hợp sử dụng |
|---|---|---|
| awaitAllSuccessfulOrThrow() | Chờ tất cả thành công; nếu một task lỗi thì hủy các task còn lại và ném lỗi | Các task trả kết quả khác kiểu, tất cả đều bắt buộc |
| allSuccessfulOrThrow() | Trả về List kết quả theo thứ tự fork nếu tất cả thành công; hủy và ném lỗi khi có task thất bại | Nhiều task cùng kiểu kết quả, tất cả đều bắt buộc |
| anySuccessfulOrThrow() | Trả về kết quả của task đầu tiên thành công; hủy các task chưa hoàn tất; ném lỗi nếu tất cả đều thất bại | Gọi nhiều replica hoặc nhiều nguồn dự phòng, chỉ cần một kết quả |
| awaitAll() | Chờ tất cả task kết thúc, không tự hủy scope chỉ vì một task thất bại; join trả về null | Task thực hiện side effect hoặc cần kiểm tra từng trạng thái sau đó |
| allUntil(predicate) | Thu thập trạng thái subtask và hủy scope khi predicate trả true | Chính sách hủy tùy chỉnh, ví dụ đủ số kết quả hoặc vượt ngưỡng lỗi |

Nếu tự cài Joiner hoặc dùng predicate của allUntil, phải thiết kế phần callback an toàn khi nhiều subtask hoàn tất đồng thời. onComplete có thể được gọi từ nhiều thread; không chia sẻ bộ đếm hoặc collection mutable giữa các callback nếu chưa có cơ chế đồng bộ thích hợp. Tạo một Joiner mới cho mỗi scope và giữ logic nghiệp vụ chính ở code xử lý kết quả sau join.

### 5.1. Chờ mọi task thành công

Đây là policy mặc định của StructuredTaskScope.open() trong JDK 26. Có thể chỉ rõ bằng Joiner.awaitAllSuccessfulOrThrow() khi muốn thể hiện rõ ý định:

~~~java
try (var scope = StructuredTaskScope.open(
        StructuredTaskScope.Joiner.awaitAllSuccessfulOrThrow())) {

    var user = scope.fork(() -> fetchUser());
    var settings = scope.fork(() -> fetchSettings());

    scope.join();

    return new AccountView(user.get(), settings.get());
}
~~~

Policy này phù hợp khi kết quả có kiểu khác nhau và tất cả đều bắt buộc. Nếu một task thất bại, scope được hủy và join ném FailedException.

### 5.2. Chỉ cần một task thành công

Ví dụ một dịch vụ có hai replica độc lập. Ứng dụng chỉ cần phản hồi đầu tiên thành công:

~~~java
import java.util.concurrent.StructuredTaskScope;

String lookup(String key) throws InterruptedException {
    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>anySuccessfulOrThrow())) {

        scope.fork(() -> lookupPrimary(key));
        scope.fork(() -> lookupReplica(key));

        return scope.join();
    }
}
~~~

Khi một subtask thành công, Joiner trả kết quả đó và yêu cầu các task còn lại dừng. Nếu mọi task đều thất bại, join ném FailedException.

Kết quả là task hoàn tất đầu tiên thành công, không nhất thiết là task được fork đầu tiên. Nếu hai nguồn có dữ liệu không đồng nhất hoặc có mức độ tin cậy khác nhau, không nên dùng policy này một cách máy móc; hãy cân nhắc kiểm tra chất lượng kết quả trong chính subtask hoặc thiết kế policy phù hợp.

### 5.3. Lấy kết quả của tất cả task cùng kiểu

~~~java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;

List<String> searchAll(List<String> endpoints)
        throws InterruptedException {

    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>allSuccessfulOrThrow())) {

        for (String endpoint : endpoints) {
            scope.fork(() -> search(endpoint));
        }

        return scope.join();
    }
}
~~~

allSuccessfulOrThrow() trả về List kết quả theo thứ tự fork, không phải thứ tự hoàn thành. Nếu một task thất bại, các task còn lại bị hủy và join ném FailedException.

Không fork số lượng task không giới hạn chỉ vì mặc định dùng virtual thread. Với danh sách đầu vào rất lớn, cần chia lô, giới hạn concurrency hoặc áp dụng backpressure để bảo vệ dịch vụ phụ thuộc và tài nguyên hệ thống.

### 5.4. Chờ tất cả kể cả khi có lỗi

awaitAll() không hủy scope khi một subtask thất bại. Sau khi join, owner có thể kiểm tra trạng thái từng subtask để tổng hợp thành công và lỗi.

Policy này phù hợp khi mỗi task thực hiện một side effect độc lập, hoặc ứng dụng cần thu thập tất cả kết quả lỗi để báo cáo. Không gọi get() trên một subtask chưa thành công; hãy kiểm tra trạng thái trước.

## 6. Timeout và giới hạn thời gian của nhóm tác vụ

Có thể đặt timeout khi mở scope bằng cấu hình:

~~~java
import java.time.Duration;
import java.util.concurrent.StructuredTaskScope;

String lookupWithTimeout(String key) throws InterruptedException {
    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>anySuccessfulOrThrow(),
            config -> config.withTimeout(Duration.ofSeconds(2)))) {

        scope.fork(() -> lookupPrimary(key));
        scope.fork(() -> lookupReplica(key));

        return scope.join();
    }
}
~~~

Timeout bắt đầu khi scope được mở, không phải chỉ khi join được gọi. Nếu timeout hết trước hoặc trong lúc join chờ, scope bị hủy và Joiner được thông báo qua onTimeout(). Với Joiner mặc định, join ném StructuredTaskScope.TimeoutException.

Timeout của scope là giới hạn cho toàn bộ nhóm công việc. Nó không thay thế timeout của từng thao tác I/O. Ví dụ, HTTP client, database driver hoặc socket vẫn nên có timeout riêng để tác vụ con có thể giải phóng tài nguyên và phản hồi cancellation đúng hạn.

Timeout cũng không phải cơ chế kill thread. Nếu task con đang gọi một API không phản hồi interrupt hoặc bị chặn trong thao tác không thể hủy, close có thể phải chờ rất lâu. Vì vậy, thiết kế timeout cần đi cùng API I/O có timeout và mã xử lý interrupt đúng cách.

## 7. Xử lý lỗi và interrupt

Có ba tình huống cần phân biệt:

| Tình huống | Biểu hiện trong JDK 26 | Cách xử lý |
|---|---|---|
| Một subtask thất bại | join ném StructuredTaskScope.FailedException; cause là lỗi từ subtask | Xử lý theo loại cause, ghi log ở ranh giới phù hợp và để scope dừng các task còn lại |
| Owner bị interrupt khi đang join | join ném InterruptedException | Để exception truyền lên nếu chữ ký cho phép; nếu bắt và không truyền tiếp thì khôi phục interrupt bằng Thread.currentThread().interrupt() |
| Timeout của scope hết hạn | join ném StructuredTaskScope.TimeoutException nếu Joiner không tạo kết quả thay thế | Trả timeout hoặc fallback theo chính sách dịch vụ; scope vẫn phải chờ task con kết thúc khi close |

Không nên nuốt InterruptedException:

~~~java
try {
    performBlockingWork();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Nếu method có thể khai báo throws InterruptedException, thường nên để exception truyền lên. Nếu cần bắt để chuyển đổi thành lỗi nghiệp vụ, phải giữ lại trạng thái interrupt hoặc bảo đảm caller nhận được tín hiệu hủy tương đương.

Task con nên sử dụng các API có thể bị interrupt. Nếu có vòng lặp tính toán dài, có thể kiểm tra Thread.currentThread().isInterrupted() định kỳ và kết thúc sớm. Không bắt InterruptedException rồi tiếp tục làm việc như thể không có yêu cầu hủy.

## 8. Nested scope: nhóm tác vụ có thể có cấu trúc phân cấp

Một subtask có thể mở scope riêng để fork các subtask nhỏ hơn. Khi đó, vòng đời tạo thành cây:

~~~text
Request
  |
  +-- Scope: Dashboard
        |
        +-- Subtask: Load profile
        |
        +-- Subtask: Load orders
        |      |
        |      +-- Scope: Order details
        |              |
        |              +-- Subtask: Load items
        |              +-- Subtask: Load shipment
        |
        +-- Subtask: Load permissions
~~~

Khi task Load orders kết thúc, scope con của nó phải đóng trước khi subtask đó hoàn tất. Scope cha chỉ có thể kết thúc sau khi các task con trực tiếp của nó kết thúc. Nhờ vậy, các tác vụ lồng nhau có vòng đời phù hợp với quan hệ phụ thuộc trong nghiệp vụ.

Không nên mở scope lồng nhau từ một thread không sở hữu scope cha rồi cố dùng scope cha từ thread đó. Mỗi scope có owner riêng và các thao tác fork, join, close chỉ được thực hiện bởi owner của scope tương ứng.

StructuredTaskScope cũng kế thừa các binding của ScopedValue tại thời điểm mở scope. Điều này hữu ích để truyền context bất biến như request ID, user ID hoặc trace context xuống các subtask mà không cần thêm tham số vào mọi lời gọi. Nếu giá trị được chia sẻ có thể mutable, vẫn phải bảo đảm đồng bộ hoặc dùng dữ liệu bất biến.

## 9. Vì sao close phải chờ task con kết thúc?

Một bảo đảm quan trọng của structured concurrency là task cha không tiếp tục ra ngoài phạm vi scope khi các task con còn chạy. close hủy các task chưa hoàn tất rồi chờ các thread đó kết thúc.

Điều này ngăn các tình huống như:

- Phương thức trả response trong khi task con vẫn dùng dữ liệu request đã hết hiệu lực.
- Tài nguyên hoặc transaction bị đóng trong khi task con vẫn đang sử dụng.
- Exception của task con xảy ra sau khi caller đã nhận kết quả và không còn ai quan sát.
- Task con tiếp tục giữ socket, file handle hoặc connection pool sau khi request bị hủy.

Tuy nhiên, close không bảo đảm thời gian chờ hữu hạn. Nếu task con bỏ qua interrupt, bị kẹt trong native call hoặc chờ một thao tác I/O không có timeout, scope cha cũng phải chờ. Đây là lý do cancellation cooperation là một phần bắt buộc của thiết kế task.

Một task con nên:
- Dùng API có thể interrupt hoặc có timeout.
- Đóng tài nguyên trong try-with-resources.
- Không giữ lock lâu khi chờ I/O.
- Không nuốt tín hiệu interrupt.
- Không tạo thread detached để tiếp tục công việc sau khi subtask kết thúc.

## 10. Quan sát và chẩn đoán vòng đời tác vụ

Structured concurrency giúp biểu diễn quan hệ cha-con trong mã nguồn và cải thiện khả năng quan sát. Khi cần điều tra task bị chậm hoặc chưa dừng, hãy xem thread dump để xác định:

- Owner thread đang chờ join hay đang xử lý kết quả.
- Subtask nào còn chạy và đang chờ ở API nào.
- Có task nào bị interrupt nhưng chưa thoát hay không.
- Scope lồng nhau nào đang giữ các thread con.
- Có tác vụ nào đang giữ lock hoặc chờ tài nguyên bên ngoài.

Trong JDK 26, scope có thể được cấu hình với tên để phục vụ monitoring và management. Có thể cấu hình ThreadFactory để đặt tên cho virtual thread. Tên thread và scope nên gắn với request hoặc nghiệp vụ đủ rõ để truy vết, nhưng không chứa dữ liệu nhạy cảm.

Không dùng số lượng thread đang chạy làm chỉ số duy nhất để đánh giá sức khỏe. Hãy theo dõi thêm thời gian join, số lần cancellation, tỷ lệ task thất bại, thời gian từ interrupt đến khi task kết thúc và tỷ lệ timeout theo loại phụ thuộc.

## 11. Trạng thái API qua các phiên bản Java

StructuredTaskScope đã trải qua nhiều vòng thay đổi. Điều quan trọng khi nâng cấp là dùng đúng API của JDK mục tiêu, không sao chép code từ một bản preview cũ.

| Phiên bản | Trạng thái | Ý nghĩa khi sử dụng |
|---|---|---|
| JDK 19–20 | Incubator (JEP 428, JEP 437) | Các API thử nghiệm ban đầu |
| JDK 21–24 | Preview qua nhiều JEP | API đã thay đổi giữa các vòng preview |
| JDK 25 | Fifth Preview (JEP 505) | Chuyển sang thiết kế open/fork/join/Joiner |
| JDK 26 | Sixth Preview (JEP 525) | API được dùng trong các ví dụ của bài học này; vẫn cần bật preview |
| JDK 27 | Seventh Preview (JEP 533) | Thay đổi kiểu exception của join và một số API; không dùng class file preview JDK 26 |
| JDK 28 development | JEP 543 finalises Structured Concurrency | API được tích hợp để trở thành tính năng chính thức; JDK 28 chưa GA tại thời điểm 27-11-2026 |

Trong các vòng preview cũ có những ví dụ dùng các lớp ShutdownOnFailure hoặc ShutdownOnSuccess. Các lớp đó thuộc thiết kế preview trước khi API được tái cấu trúc. Khi viết code cho JDK 26, dùng StructuredTaskScope.open() và Joiner thay cho các ví dụ cũ.

JDK 26 yêu cầu bật preview. JDK 27 vẫn là preview nhưng API đã thay đổi: StructuredTaskScope có thêm tham số kiểu exception R_X và join mặc định sử dụng ExecutionException thay cho FailedException. JDK 28 tích hợp JEP 543 để finalise API sau JDK 27; khi chuyển sang JDK 28 cần biên dịch lại theo API final và bỏ cờ preview khi dùng bản JDK 28 đã phát hành.

## 12. Biên dịch và chạy trên JDK 26

Với mã sử dụng StructuredTaskScope trong JDK 26, phải bật preview ở cả compiler và JVM:

~~~sh
javac --enable-preview --release 26 -d out DashboardService.java Main.java
java --enable-preview -cp out Main
~~~

Lệnh java minh họa một entry point Main của project gọi DashboardService; DashboardService trong phần ví dụ là một thành phần dịch vụ, không phải lớp khởi chạy độc lập. Không dùng class file được biên dịch bằng preview của JDK 26 để chạy trên JDK 27 hoặc JDK 28. Hãy biên dịch lại bằng đúng JDK mục tiêu, kiểm tra lại kiểu exception và các method của Joiner.

Với JDK 26, các điểm cần nhớ:
- StructuredTaskScope, Joiner, Subtask và các kiểu liên quan là preview API.
- Joiner.anySuccessfulOrThrow() trả về kết quả đầu tiên thành công.
- Joiner.allSuccessfulOrThrow() trả về List kết quả theo thứ tự fork.
- Joiner.awaitAllSuccessfulOrThrow() phù hợp khi các subtask trả về các kiểu khác nhau.
- FailedException chứa cause của subtask thất bại.
- TimeoutException được ném khi timeout hết và Joiner không tạo kết quả thay thế.

## 13. Phương án ổn định khi không dùng preview

Nếu ứng dụng phải chạy trên JDK 26 hoặc JDK 27 và không chấp nhận preview API, vẫn có thể dùng ExecutorService với virtual thread đã chính thức từ Java 21:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

Dashboard load(String customerId) throws InterruptedException {
    try (ExecutorService executor =
            Executors.newVirtualThreadPerTaskExecutor()) {

        Future<UserProfile> profile =
            executor.submit(() -> fetchProfile(customerId));

        Future<List<Order>> orders =
            executor.submit(() -> fetchOrders(customerId));

        try {
            return new Dashboard(profile.get(), orders.get());
        } catch (InterruptedException e) {
            profile.cancel(true);
            orders.cancel(true);
            throw e;
        } catch (ExecutionException e) {
            profile.cancel(true);
            orders.cancel(true);
            throw new IllegalStateException(
                "Không thể tạo Dashboard",
                e.getCause()
            );
        }
    }
}
~~~

ExecutorService là API ổn định. Ví dụ dùng Future để lấy kết quả và hủy các task khi một kết quả thất bại. try-with-resources đóng executor và chờ các task kết thúc. Tuy nhiên, caller phải tự quản lý quan hệ task, chính sách lỗi, cancellation và việc chờ hoàn tất; StructuredTaskScope gói các quy tắc đó thành một scope và Joiner.

Nếu một nhóm tác vụ cần nhiều chính sách cancellation hoặc có quan hệ cha-con rõ ràng, StructuredTaskScope giúp thể hiện ý định trực tiếp hơn. Nếu chỉ cần gửi một số tác vụ độc lập vào executor và quản lý Future thủ công là đủ, ExecutorService vẫn là lựa chọn hợp lệ, không phải API lỗi thời.

## 14. Lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Task con còn chạy sau khi phương thức cha trả về | Tạo task rời rạc và không chờ hoặc đóng executor đúng cách | Đặt nhóm task trong một scope hoặc quản lý executor có vòng đời rõ |
| Gọi get() trước join() | Subtask chưa chắc đã hoàn tất | Gọi join trước, rồi chỉ get kết quả khi trạng thái thành công |
| Fork sau join() | Scope đã chuyển sang giai đoạn nhận outcome | Hoàn thành toàn bộ việc fork trước join |
| Gọi fork/join/close từ thread khác | Vi phạm quyền sở hữu scope | Chỉ owner thread thao tác scope |
| Một task lỗi nhưng task khác tiếp tục chạy | Chọn Joiner không hủy khi lỗi hoặc dùng policy awaitAll | Chọn policy phù hợp với nghiệp vụ |
| Task bị interrupt nhưng không dừng | Task nuốt InterruptedException hoặc dùng API không interruptible | Thiết kế task hợp tác với cancellation và đặt timeout I/O |
| close() chờ quá lâu | Subtask không kết thúc sau cancellation | Kiểm tra thread dump, blocking call, lock và I/O timeout |
| Mọi task đều bị hủy dù một kết quả đã đủ | Chọn policy chờ tất cả | Dùng anySuccessfulOrThrow nếu chỉ cần kết quả đầu tiên thành công |
| Dùng FailedException trên JDK 27/28 | Sao chép code preview JDK 26 sang API đã đổi | Dùng kiểu exception của đúng JDK mục tiêu và biên dịch lại |
| Code JDK 26 không chạy vì preview disabled | Thiếu cờ preview khi compile hoặc run | Dùng --enable-preview cho cả javac và java với JDK 26 |

## 15. Checklist thiết kế nhóm tác vụ

- [ ] Xác định các task có thực sự độc lập và có thể chạy đồng thời hay không.
- [ ] Xác định task nào là bắt buộc, task nào có thể dùng kết quả đầu tiên thành công.
- [ ] Một owner rõ ràng mở, fork, join và đóng mỗi scope.
- [ ] Fork tất cả task trước khi gọi join.
- [ ] Chọn Joiner phù hợp với mục tiêu nghiệp vụ.
- [ ] Chỉ gọi Subtask.get() sau khi join và khi subtask thành công.
- [ ] Xử lý riêng lỗi subtask, interrupt của owner và timeout.
- [ ] Task con phản hồi interrupt và có timeout cho thao tác I/O.
- [ ] close được phép chờ task con kết thúc; không giả định cancellation là kill ngay.
- [ ] Scope lồng nhau được đóng theo đúng thứ tự.
- [ ] Không fork vô hạn chỉ vì mỗi subtask dùng virtual thread.
- [ ] Kiểm tra đúng phiên bản JDK, trạng thái preview/final và kiểu exception của API.
- [ ] Nếu không chấp nhận preview trong JDK 26/27, dùng ExecutorService và quản lý Future theo cách tường minh.
- [ ] Khi dùng JDK 28 đã phát hành, biên dịch với API final và bỏ cờ preview.

## Tài liệu tham khảo

- [Java SE 26 StructuredTaskScope API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): open, fork, join, close, owner, cancellation và cấu hình timeout.
- [Java SE 26 StructuredTaskScope.Joiner API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html): các chính sách awaitAllSuccessfulOrThrow, allSuccessfulOrThrow, anySuccessfulOrThrow, awaitAll và allUntil.
- [Java SE 26 Structured Concurrency Guide](https://docs.oracle.com/en/java/javase/26/core/structured-concurrency.html): quy trình sử dụng, kết quả, Joiner và xử lý exception.
- [JEP 525 — Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525): trạng thái Structured Concurrency trong JDK 26.
- [JEP 533 — Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533): thay đổi trong JDK 27.
- [JEP 543 — Structured Concurrency](https://openjdk.org/jeps/543): hoàn tất tính năng trong nhánh phát triển JDK 28.
- [Java SE 27 StructuredTaskScope API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): API preview và kiểu exception của JDK 27.
- [OpenJDK review: Implement JEP 543](https://www.mail-archive.com/core-libs-dev@openjdk.org/msg75715.html): thay đổi để đưa Structured Concurrency thành API chính thức trong JDK 28.
- [Java SE 26 ExecutorService API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html): phương án ổn định để quản lý executor và vòng đời task.

