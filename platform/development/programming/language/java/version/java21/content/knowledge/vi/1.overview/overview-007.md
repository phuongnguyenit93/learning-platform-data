# Lựa chọn tính năng theo bài toán thay vì thay đổi mã chỉ vì có cú pháp mới

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), mục tiêu là chọn đúng tính năng để giải quyết một vấn đề cụ thể về khả năng xử lý đồng thời, độ rõ ràng của mô hình dữ liệu, cách thao tác với tập hợp có thứ tự hoặc chi phí vận hành JVM. Java 21 là một bản phát hành LTS, nhưng việc một tính năng mới xuất hiện không có nghĩa mọi dự án đều cần áp dụng nó.

Một thay đổi đáng làm khi nó cải thiện kết quả có thể quan sát được, phù hợp với phiên bản JDK triển khai và giúp mã dễ duy trì hơn. Nếu mã hiện tại đã đơn giản, dễ hiểu và đáp ứng yêu cầu, giữ nguyên cũng là một quyết định kỹ thuật hợp lý.

## Bắt đầu từ vấn đề cần giải quyết

| Vấn đề trong hệ thống | Tính năng Java 21 có thể cân nhắc | Khi nào phù hợp | Khi nào chưa phù hợp |
| --- | --- | --- | --- |
| Nhiều tác vụ đồng thời chủ yếu chờ I/O, chẳng hạn gọi HTTP hoặc truy vấn dịch vụ khác | Virtual Threads (JEP 444) | Cần xử lý nhiều tác vụ chờ mà mô hình lập trình đồng bộ theo từng tác vụ vẫn dễ hiểu | Công việc chủ yếu tiêu thụ CPU, hoặc nút thắt nằm ở cơ sở dữ liệu, giới hạn kết nối hay dịch vụ bên ngoài |
| Nhiều nhánh xử lý dựa trên kiểu của một mô hình miền có tập kiểu đóng | Pattern Matching for `switch` và Record Patterns (JEP 441, JEP 440) | Muốn thể hiện rõ từng trường hợp và lấy dữ liệu từ record ngay trong nhánh xử lý | Một lời gọi đa hình hoặc một cấu trúc điều kiện đơn giản đã diễn đạt vấn đề rõ ràng hơn |
| Mã thường xuyên lấy phần tử đầu, cuối hoặc duyệt ngược một tập hợp có thứ tự | Sequenced Collections (JEP 431) | Thứ tự gặp phần tử là một phần của hợp đồng nghiệp vụ hoặc API | Tập hợp không có thứ tự có ý nghĩa, hoặc mã chỉ cần thao tác mà kiểu hiện tại đã hỗ trợ tốt |
| Độ trễ tạm dừng hoặc chi phí thu gom rác đang ảnh hưởng đến mục tiêu vận hành | Generational ZGC (JEP 439) | Dữ liệu đo từ GC, JFR và kiểm thử tải cho thấy cần đánh giá một cấu hình GC khác | Chưa có số liệu chứng minh GC là nút thắt, hoặc cấu hình mới làm tăng chi phí tài nguyên mà không cải thiện SLO |

Các tính năng trên giải quyết những nhóm vấn đề khác nhau. Hãy xác định vấn đề trước, sau đó mới chọn tính năng và kiểm chứng hiệu quả.

## Chọn Virtual Threads cho tác vụ chờ I/O

Virtual thread là luồng nhẹ do JVM quản lý. Java 21 cung cấp API ổn định để tạo virtual thread, giúp chương trình có thể giữ cách viết đồng bộ quen thuộc trong khi xử lý số lượng lớn tác vụ đồng thời chủ yếu chờ I/O.

Ví dụ, một màn hình tổng hợp cần tải thông tin khách hàng và danh sách đơn hàng từ hai dịch vụ độc lập:

```java
record CustomerView(String customer, List<Order> orders) {}

CustomerView loadView(String customerId)
        throws InterruptedException, ExecutionException {
    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
        Future<String> customer = executor.submit(
                () -> loadCustomerFromService(customerId));
        Future<List<Order>> orders = executor.submit(
                () -> loadOrdersFromService(customerId));

        return new CustomerView(customer.get(), orders.get());
    }
}
```

Trong ví dụ này, hai lời gọi dịch vụ có thể chờ độc lập. Virtual thread giúp mô hình một tác vụ trên một luồng trở nên khả thi ở quy mô đồng thời lớn hơn mà không cần tự quản lý một lượng lớn platform thread. Các hàm tải dữ liệu là phần I/O đồng bộ được minh họa; mã thực tế cần xử lý lỗi, timeout và hủy tác vụ theo hợp đồng của dịch vụ.

Nên cân nhắc virtual thread khi:

- Mỗi yêu cầu thực hiện nhiều thao tác I/O có thể chờ độc lập.
- Mã đồng bộ hiện tại dễ đọc và việc chuyển sang callback hoặc reactive làm tăng độ phức tạp.
- Hệ thống cần tăng số tác vụ đồng thời và đã kiểm tra giới hạn của các tài nguyên phía sau.

Không nên kỳ vọng virtual thread làm phép tính CPU-bound chạy nhanh hơn. Chúng cũng không làm cơ sở dữ liệu hoặc dịch vụ bên ngoài tự tăng năng lực. Nếu cần giới hạn số truy vấn đồng thời, hãy giới hạn tại tài nguyên cần bảo vệ bằng connection pool, semaphore, rate limiter hoặc cơ chế back-pressure phù hợp. Không tạo một pool để tái sử dụng virtual thread; thông thường nên tạo một virtual thread cho mỗi tác vụ.

Với Java 21, cần chú ý hiện tượng *pinning*: virtual thread có thể bị ghim vào carrier thread khi thực hiện thao tác chặn trong vùng `synchronized` hoặc trong mã native. Điều này có thể làm giảm khả năng mở rộng nếu vùng chặn kéo dài. Khi có dấu hiệu nghẽn, dùng Java Flight Recorder để kiểm tra sự kiện `jdk.VirtualThreadPinned`, rồi xử lý đúng điểm nóng. Không cần thay toàn bộ `synchronized` chỉ vì sử dụng virtual thread.

## Chọn pattern matching và record patterns cho mô hình kiểu rõ ràng

Pattern matching for `switch` cho phép phân nhánh theo kiểu và kiểm tra tính đầy đủ của các trường hợp. Record patterns cho phép tách các thành phần của record ngay trong nhánh tương ứng. Hai tính năng này hữu ích khi mô hình miền có một tập kiểu xác định, chẳng hạn một sealed interface với các record triển khai nó.

```java
sealed interface Payment permits CardPayment, CashPayment {}

record CardPayment(String lastFour, long amountInCents)
        implements Payment {}

record CashPayment(long amountInCents) implements Payment {}

static String describe(Payment payment) {
    return switch (payment) {
        case null -> "Chưa có phương thức thanh toán";
        case CardPayment(var lastFour, var amount) ->
                "Thẻ kết thúc bằng " + lastFour + ", số tiền " + amount;
        case CashPayment(var amount) -> "Tiền mặt, số tiền " + amount;
    };
}
```

Vì `Payment` là sealed và liệt kê các kiểu triển khai được phép, trình biên dịch có thể kiểm tra các trường hợp đã được xử lý. Khi thêm một kiểu thanh toán mới vào danh sách `permits`, những switch expression không còn đầy đủ sẽ cần được cập nhật. Nhánh `case null` thể hiện rõ cách xử lý dữ liệu rỗng; nếu hợp đồng của ứng dụng cấm `null`, có thể kiểm tra và từ chối giá trị đó ở ranh giới đầu vào.

Hãy chọn cách này khi việc phân nhánh theo kiểu là một phần tự nhiên của nghiệp vụ, và việc nhìn thấy mọi trường hợp trong cùng một biểu thức giúp người đọc hiểu luồng xử lý. Nếu mỗi kiểu đã có hành vi riêng phù hợp, đa hình qua phương thức có thể gọn hơn. Với hệ phân cấp mở hoặc có kiểu mới đến từ bên ngoài, cần cân nhắc nhánh mặc định và cách bảo đảm tính đầy đủ khi mở rộng.

## Chọn Sequenced Collections khi thứ tự là một phần của hợp đồng

Java 21 bổ sung các interface `SequencedCollection`, `SequencedSet` và `SequencedMap`. Chúng cung cấp một cách thống nhất để thao tác với tập hợp có thứ tự gặp phần tử, gồm lấy phần tử đầu/cuối và xem tập hợp theo thứ tự đảo ngược.

```java
List<String> events = new ArrayList<>(List.of("created", "paid", "shipped"));

String firstEvent = events.getFirst();
String latestEvent = events.getLast();
List<String> newestFirst = events.reversed();

events.addFirst("received");
events.addLast("delivered");
```

`List` trong Java 21 kế thừa khả năng của `SequencedCollection`, nên không cần đổi sang một kiểu collection mới chỉ để gọi các phương thức này. `reversed()` trả về một view theo thứ tự đảo ngược của collection gốc, không phải bản sao độc lập. Vì vậy, thay đổi trên collection gốc có thể được nhìn thấy qua view và ngược lại nếu thao tác đó được hỗ trợ. Các phương thức lấy phần tử đầu/cuối sẽ ném `NoSuchElementException` nếu collection rỗng; hãy kiểm tra điều kiện rỗng khi dữ liệu đầu vào không bảo đảm có phần tử.

Với map có thứ tự, `SequencedMap` cung cấp các thao tác như `firstEntry()`, `lastEntry()`, `putFirst()` và `putLast()`. Chẳng hạn, `LinkedHashMap` có thể được dùng như một `SequencedMap` khi thứ tự duyệt khóa là một phần của yêu cầu. Hãy dùng các API này khi thứ tự có ý nghĩa với người gọi hoặc nghiệp vụ; đừng chuyển một `HashMap` thành cấu trúc có thứ tự nếu thứ tự không phải yêu cầu thực sự.

## Chỉ thay đổi cấu hình GC khi số liệu chỉ ra nhu cầu

Generational ZGC là lựa chọn runtime được bổ sung trong Java 21. Chế độ này chia heap thành các thế hệ để tận dụng đặc điểm nhiều đối tượng có vòng đời ngắn trong một số ứng dụng. Với JDK 21, có thể đánh giá bằng cấu hình:

```shell
java -XX:+UseZGC -XX:+ZGenerational -jar application.jar
```

Đây là một quyết định vận hành JVM, không phải lý do để sửa mã nghiệp vụ. Trước khi đổi GC, hãy thu thập dữ liệu từ GC log, Java Flight Recorder và kiểm thử tải để xác định thời gian tạm dừng, thông lượng, mức dùng CPU và bộ nhớ hiện tại. Sau khi đổi, chạy lại cùng kịch bản và so sánh với mục tiêu độ trễ, thông lượng và chi phí tài nguyên. Không có một bộ thu gom rác phù hợp nhất cho mọi ứng dụng.

## Phân biệt API ổn định với preview và incubator

Java 21 có một số tính năng ở trạng thái preview hoặc incubator, ví dụ String Templates, Structured Concurrency, Scoped Values, Unnamed Patterns and Variables, Foreign Function & Memory API và Vector API. Không xem các tính năng này là API ổn định mặc định cho ứng dụng production chạy Java 21.

Preview feature cần được bật rõ ràng bằng `--enable-preview` khi biên dịch và chạy, đồng thời có thể thay đổi hoặc bị loại bỏ ở bản JDK khác. API incubator cũng có trạng thái thử nghiệm và cách sử dụng riêng. Nếu cần khảo sát chúng, hãy tạo thử nghiệm giới hạn, xác nhận trạng thái trên đúng JDK mục tiêu và đánh giá chi phí nâng cấp trước khi đưa vào sản phẩm. Không trộn mã preview vào nền tảng dùng chung khi các module triển khai không thể bảo đảm cùng phiên bản JDK.

## Quy trình ra quyết định trước khi áp dụng

1. **Mô tả vấn đề bằng dữ liệu hoặc ví dụ cụ thể.** Chẳng hạn, số lượng lời gọi I/O đồng thời tăng, switch expression khó kiểm tra tính đầy đủ, hoặc thứ tự phần tử đang phải xử lý bằng mã thủ công.
2. **Chọn tính năng khớp với vấn đề.** Xác định lợi ích dự kiến và phần mã sẽ thay đổi. Không gom nhiều thay đổi độc lập vào cùng một lần chỉ để sử dụng nhiều tính năng mới.
3. **Kiểm tra môi trường triển khai.** Xác nhận JDK toolchain, runtime, framework, thư viện, image container và pipeline CI hỗ trợ Java 21. Có thể đặt mức biên dịch bằng `--release 21` để kiểm soát API và ngôn ngữ mục tiêu; tùy chọn này không tự bật preview feature.
4. **Thử nghiệm trong phạm vi nhỏ.** Dùng kiểm thử chức năng, kiểm thử tải hoặc benchmark phù hợp. Với thay đổi đồng thời, kiểm tra cả timeout, lỗi, hủy tác vụ và giới hạn tài nguyên; với thay đổi GC, dùng cùng dữ liệu và tải để so sánh.
5. **Đánh giá khả năng duy trì.** Người khác có hiểu được lý do chọn tính năng và cách vận hành nó không? Nếu cú pháp mới làm mã khó đọc hơn mà không đem lại lợi ích đo được, hãy giữ cách triển khai đơn giản hơn.
6. **Theo dõi sau khi triển khai.** Đối chiếu kết quả với mục tiêu ban đầu bằng log, metric, trace hoặc JFR. Nếu lợi ích không xuất hiện hoặc rủi ro vận hành tăng, điều chỉnh hay hoàn tác thay đổi.

## Checklist lựa chọn

- Vấn đề cần giải quyết đã được mô tả rõ và có cách kiểm chứng.
- Tính năng được chọn ở trạng thái ổn định trên JDK mục tiêu.
- Ứng dụng, thư viện và môi trường triển khai tương thích.
- Có kiểm thử phù hợp để so sánh trước và sau thay đổi.
- Nhóm phát triển hiểu được tác động đến lỗi, hiệu năng và vận hành.

Hãy chọn tính năng Java 21 khi nó giải quyết đúng vấn đề và cải thiện chất lượng hệ thống theo cách kiểm chứng được. Cú pháp mới chỉ là phương tiện; tính đúng đắn, khả năng tương thích và khả năng bảo trì mới là tiêu chí quyết định.
